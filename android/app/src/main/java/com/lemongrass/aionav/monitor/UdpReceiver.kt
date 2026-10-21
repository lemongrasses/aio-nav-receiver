package com.lemongrass.aionav.monitor

import android.os.Process
import android.os.SystemClock
import android.system.ErrnoException
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.Inet4Address
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.NetworkInterface
import java.net.SocketException
import java.net.SocketTimeoutException

/**
 * Listens on one or two UDP ports, one thread each, so 100 Hz 0x04 traffic is never dropped because
 * the UI is busy. Every datagram goes to `handler` with the sender's IPv4 address and the arrival
 * time on the monotonic clock (elapsedRealtime, which keeps counting in deep sleep).
 */
class UdpReceiver(ports: List<Int>, private val handler: (ByteArray, String?, Double) -> Unit) {
    /** `errno` from the system (android.system.OsConstants), when the exception carries one. */
    class BindError(val port: Int, val errno: Int?, cause: Exception) : Exception("UDP $port: ${cause.message}", cause)

    @Volatile private var running = true
    private val sockets: List<DatagramSocket>
    private val threads: List<Thread>

    init {
        val opened = ArrayList<DatagramSocket>()
        for (port in ports.distinct().sorted()) {
            try {
                opened += DatagramSocket(null).apply {
                    reuseAddress = true
                    receiveBufferSize = 1 shl 20
                    soTimeout = 200
                    bind(InetSocketAddress(InetAddress.getByName("0.0.0.0"), port))   // IPv4 only
                }
            } catch (e: Exception) {
                opened.forEach { it.close() }
                throw BindError(port, errnoOf(e), e)
            }
        }
        sockets = opened
        threads = sockets.map { s ->
            Thread({ receiveLoop(s) }, "UdpReceiver-${s.localPort}").apply {
                isDaemon = true
                start()
            }
        }
    }

    private fun receiveLoop(socket: DatagramSocket) {
        Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_DISPLAY)
        val buffer = ByteArray(2048)
        val packet = DatagramPacket(buffer, buffer.size)
        try {
            while (running) {
                try {
                    packet.length = buffer.size
                    socket.receive(packet)
                } catch (_: SocketTimeoutException) {
                    continue
                }
                val arrival = SystemClock.elapsedRealtimeNanos() / 1e9
                val sender = (packet.address as? Inet4Address)?.hostAddress
                handler(buffer.copyOf(packet.length), sender, arrival)
            }
        } catch (_: SocketException) {
            // closed by stop()
        } finally {
            socket.close()
        }
    }

    /** Stops the threads and closes the sockets at once, so the ports can be bound again. */
    fun stop() {
        running = false
        sockets.forEach { it.close() }
    }

    companion object {
        private fun errnoOf(e: Throwable): Int? =
            generateSequence(e) { it.cause }.filterIsInstance<ErrnoException>().firstOrNull()?.errno

        /** Monotonic seconds, the same clock the receive times use. */
        fun now(): Double = SystemClock.elapsedRealtimeNanos() / 1e9

        /** IPv4 addresses of this phone's network interfaces (Wi-Fi first), to give the Jetson relay. */
        fun localAddresses(): List<Pair<String, String>> = try {
            NetworkInterface.getNetworkInterfaces().toList()
                .filter { it.isUp && !it.isLoopback }
                .flatMap { nif -> nif.inetAddresses.toList().filterIsInstance<Inet4Address>().map { nif.name to it.hostAddress!! } }
                .sortedWith(compareBy({ !it.first.startsWith("wlan") }, { it.first }))
        } catch (_: SocketException) {
            emptyList()
        }
    }
}
