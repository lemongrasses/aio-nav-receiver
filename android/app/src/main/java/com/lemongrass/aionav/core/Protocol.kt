// AIO NAV UDP packet formats: 0x04 navigation solution and 0x05 readiness status.
// A port of the desktop app's src/aio_receiver/core/protocol.py (the reference). Pure Kotlin: no Android imports.
//
// Both share one frame (little-endian):  55 AA | msg_id u8 | payload_len u16 | payload | checksum u8
// checksum = 8-bit sum of the bytes from msg_id to the end of the payload.

package com.lemongrass.aionav.core

import java.nio.ByteBuffer
import java.nio.ByteOrder

object Aio {
    const val SYNC0 = 0x55
    const val SYNC1 = 0xAA
    const val NAV_ID = 0x04
    const val STATUS_ID = 0x05
    const val STATUS_VERSION = 1

    const val HEADER_SIZE = 5
    const val NAV_PAYLOAD = 150                         // struct "<Qdd28fH3f"
    const val NAV_LEN = HEADER_SIZE + NAV_PAYLOAD + 1   // 156
    const val STATUS_PAYLOAD = 36                       // struct "<BBBBIIQIIBBHHH"
    const val STATUS_LEN = HEADER_SIZE + STATUS_PAYLOAD + 1  // 42
    const val NAV_AGE_UNKNOWN = 0xFFFF

    val FLAG_NAMES = listOf("ZUPT", "ZIHR", "NHC", "GNSS", "VUPT", "ALIGN", "HEADING", "FINE")
    val AIDING_FLAGS = listOf("GNSS", "ZUPT", "ZIHR", "NHC", "VUPT")
    val ALIGNMENT_FLAGS = listOf("ALIGN", "HEADING", "FINE")
    const val ALIGN_MASK = 0b1110_0000                  // ALIGN | HEADING | FINE

    val STATES = listOf("BOOTING", "CHECKING", "NAV_STARTING", "KEEP_STILL", "MOVE_STRAIGHT", "REFINING",
        "READY", "DEGRADED", "FAULT", "MAINTENANCE")
    val READY = STATES.indexOf("READY")
    val ACTIONS = listOf("NONE", "HOLD_STILL", "DRIVE_STRAIGHT", "KEEP_DRIVING", "SAFE_STOP", "SERVICE_REQUIRED",
        "MAINTENANCE_HOLD")
    val GNSS_QUALITY = listOf("Unknown", "None", "SPP", "RTK float", "RTK fix")
    val HEALTH_BITS = listOf("DASHBOARD_OK", "CONFIG_OK", "IMU_STREAM_OK", "GNSS_STREAM_OK", "GNSS_QUALITY_OK",
        "NAV_PROCESS_OK", "NAV_OUTPUT_OK", "ALIGNMENT_OK", "HEADING_OK", "FINE_ALIGNMENT_OK",
        "DSO_OK", "EXTERNAL_ROUTE_OK", "RTK_CORRECTION_OK", "STORAGE_OK", "VEHICLE_ACK_OK",
        "TIME_SYNC_OK", "NO_DUPLICATE_PROCESS", "WIFI_OK")
    val INHIBIT_BITS = listOf("BOOT_IN_PROGRESS", "CONFIG_INVALID", "IMU_MISSING_OR_STALE", "GNSS_MISSING_OR_STALE",
        "GNSS_QUALITY_LOW", "NAV_NOT_RUNNING", "NAV_OUTPUT_STALE", "KEEP_STILL_REQUIRED",
        "MOVE_STRAIGHT_REQUIRED", "FINE_ALIGNMENT_REQUIRED", "DSO_NOT_READY", "EXTERNAL_ROUTE_DOWN",
        "RTK_CORRECTION_LOST", "STORAGE_NOT_WRITABLE", "MAINTENANCE_HOLD", "STARTUP_TIMEOUT",
        "OWNERSHIP_CONFLICT", "INTERNAL_FAULT")

    /** Names of the bits that are set, in bit order. */
    fun bitNames(bits: Long, table: List<String>): List<String> =
        table.indices.filter { bits shr it and 1L == 1L }.map { table[it] }

    /** The table entry, or "#code" when the code is outside the table (desktop name_of). */
    fun nameOf(code: Int, table: List<String>): String = table.getOrNull(code) ?: "#$code"

    fun reverseBits8(x: Int): Int {
        var r = 0
        for (i in 0 until 8) if (x shr i and 1 == 1) r = r or (1 shl (7 - i))
        return r
    }

    /** The frame's message id, or null when the datagram does not start with the sync bytes. */
    fun messageId(pkt: ByteArray): Int? =
        if (pkt.size >= 3 && pkt.u8(0) == SYNC0 && pkt.u8(1) == SYNC1) pkt.u8(2) else null

    internal fun frameOk(pkt: ByteArray, msgId: Int, total: Int, payload: Int): Boolean {
        if (pkt.size != total || pkt.u8(0) != SYNC0 || pkt.u8(1) != SYNC1 || pkt.u8(2) != msgId) return false
        if ((pkt.u8(3) or (pkt.u8(4) shl 8)) != payload) return false
        var sum = 0
        for (i in 2 until total - 1) sum += pkt.u8(i)
        return pkt.u8(total - 1) == sum and 0xFF
    }

    fun decodeNav(pkt: ByteArray): NavPacket? {
        if (!frameOk(pkt, NAV_ID, NAV_LEN, NAV_PAYLOAD)) return null
        val b = ByteBuffer.wrap(pkt).order(ByteOrder.LITTLE_ENDIAN)
        val f = FloatArray(28) { b.getFloat(29 + 4 * it) }
        return NavPacket(
            timeUs = b.getLong(5), lat = b.getDouble(13), lon = b.getDouble(21), floats = f,
            flagsWire = b.getShort(141).toInt() and 0xFFFF,
            odoScale = b.getFloat(143), mountPitch = b.getFloat(147), mountYaw = b.getFloat(151),
        )
    }

    fun decodeStatus(pkt: ByteArray, msgId: Int = STATUS_ID): StatusPacket? {
        if (!frameOk(pkt, msgId, STATUS_LEN, STATUS_PAYLOAD)) return null
        val b = ByteBuffer.wrap(pkt).order(ByteOrder.LITTLE_ENDIAN)
        val s = StatusPacket(
            version = pkt.u8(5), state = pkt.u8(6), action = pkt.u8(7), gnssQuality = pkt.u8(8),
            session = b.getInt(9).toLong() and 0xFFFFFFFFL, sequence = b.getInt(13).toLong() and 0xFFFFFFFFL,
            uptimeMs = b.getLong(17), health = b.getInt(25).toLong() and 0xFFFFFFFFL,
            inhibit = b.getInt(29).toLong() and 0xFFFFFFFFL, navFlags = pkt.u8(33),
            navRateDhz = b.getShort(35).toInt() and 0xFFFF, navAgeMs = b.getShort(37).toInt() and 0xFFFF,
        )
        return if (s.version == STATUS_VERSION) s else null
    }

    // ---------------------------------------------------------------- encoders (tests, previews)

    fun frame(msgId: Int, payload: ByteArray): ByteArray {
        val out = ByteArray(HEADER_SIZE + payload.size + 1)
        out[0] = SYNC0.toByte(); out[1] = SYNC1.toByte(); out[2] = msgId.toByte()
        out[3] = payload.size.toByte(); out[4] = (payload.size shr 8).toByte()
        payload.copyInto(out, HEADER_SIZE)
        var sum = 0
        for (i in 2 until out.size - 1) sum += out.u8(i)
        out[out.size - 1] = sum.toByte()
        return out
    }

    /** Build a 0x04 packet. `flags` is in C-side bit order (the desktop's encode_nav). */
    fun encodeNav(
        timeS: Double, lat: Double, lon: Double, height: Float = 0f, vn: Float = 0f, ve: Float = 0f,
        vu: Float = 0f, roll: Float = 0f, pitch: Float = 0f, heading: Float = 0f, flags: Int = 0,
        stds: FloatArray = FloatArray(9), imu: FloatArray = FloatArray(12), odoScale: Float = 1f,
        mountPitch: Float = 0f, mountYaw: Float = 0f,
    ): ByteArray {
        val b = ByteBuffer.allocate(NAV_PAYLOAD).order(ByteOrder.LITTLE_ENDIAN)
        b.putLong(Math.round(timeS * 1e6)).putDouble(lat).putDouble(lon)
        for (v in floatArrayOf(height, vn, ve, vu, roll, pitch, heading)) b.putFloat(v)
        stds.forEach { b.putFloat(it) }
        imu.forEach { b.putFloat(it) }
        b.putShort(reverseBits8(flags).toShort()).putFloat(odoScale).putFloat(mountPitch).putFloat(mountYaw)
        return frame(NAV_ID, b.array())
    }

    fun encodeStatus(
        state: Int, action: Int, session: Long, sequence: Long, gnssQuality: Int = 0, uptimeMs: Long = 0,
        health: Long = 0, inhibit: Long = 0, navFlags: Int = 0, navRateDhz: Int = 0,
        navAgeMs: Int = NAV_AGE_UNKNOWN, msgId: Int = STATUS_ID,
    ): ByteArray {
        val b = ByteBuffer.allocate(STATUS_PAYLOAD).order(ByteOrder.LITTLE_ENDIAN)
        b.put(STATUS_VERSION.toByte()).put(state.toByte()).put(action.toByte()).put(gnssQuality.toByte())
        b.putInt(session.toInt()).putInt(sequence.toInt()).putLong(uptimeMs).putInt(health.toInt())
        b.putInt(inhibit.toInt()).put(navFlags.toByte()).put(0).putShort(navRateDhz.toShort())
        b.putShort(navAgeMs.toShort()).putShort(0)
        return frame(msgId, b.array())
    }
}

internal fun ByteArray.u8(i: Int): Int = this[i].toInt() and 0xFF

/** One 0x04 packet. `floats` holds the 28 f32 fields in wire order, from height to accel_scale_z. */
class NavPacket(
    val timeUs: Long,
    val lat: Double,
    val lon: Double,
    val floats: FloatArray,
    /** Low byte bit-reversed on the wire. */
    val flagsWire: Int,
    val odoScale: Float,
    val mountPitch: Float,
    val mountYaw: Float,
) {
    val height get() = floats[0]
    val vn get() = floats[1]
    val ve get() = floats[2]
    val vu get() = floats[3]
    val roll get() = floats[4]
    val pitch get() = floats[5]
    /** Degrees as sent; may be -180..180. Use [heading360] for display. */
    val heading get() = floats[6]
    val posNStd get() = floats[7]
    val posEStd get() = floats[8]
    val posDStd get() = floats[9]
    val velNStd get() = floats[10]
    val velEStd get() = floats[11]
    val velDStd get() = floats[12]
    val rollStd get() = floats[13]
    val pitchStd get() = floats[14]
    val headingStd get() = floats[15]
    val gyroBias get() = floats.copyOfRange(16, 19)
    val accelBias get() = floats.copyOfRange(19, 22)
    val gyroScale get() = floats.copyOfRange(22, 25)
    val accelScale get() = floats.copyOfRange(25, 28)

    /** Flags in C-side bit order: bit i is FLAG_NAMES[i]. */
    val flags: Int get() = Aio.reverseBits8(flagsWire)

    /** GPS seconds of week (the wire value is microseconds, unsigned). */
    val timeS: Double get() = timeUs.toULong().toDouble() / 1e6

    fun hasFlag(name: String): Boolean = flags shr Aio.FLAG_NAMES.indexOf(name) and 1 == 1

    /** ALIGN, HEADING and FINE all set. */
    val isAligned: Boolean get() = flags and Aio.ALIGN_MASK == Aio.ALIGN_MASK

    /** Every floating-point field is neither NaN nor ±Inf. */
    val isFinite: Boolean
        get() = lat.isFinite() && lon.isFinite() && floats.all { it.isFinite() } &&
            odoScale.isFinite() && mountPitch.isFinite() && mountYaw.isFinite()

    val heading360: Double
        get() {
            val h = heading.toDouble() % 360.0
            return if (h < 0) h + 360.0 else h
        }

    val groundSpeed: Double get() = Math.hypot(vn.toDouble(), ve.toDouble())
}

/** One 0x05 packet (version 1). Unsigned 32-bit fields are held in a Long. */
data class StatusPacket(
    val version: Int,
    val state: Int,
    val action: Int,
    val gnssQuality: Int,
    val session: Long,
    val sequence: Long,
    val uptimeMs: Long,
    val health: Long,
    val inhibit: Long,
    /** 0x04 flags in C-side bit order (not reversed). */
    val navFlags: Int,
    val navRateDhz: Int,
    /** Age of the last 0x04 at the dashboard; 65535 = none or older. */
    val navAgeMs: Int,
) {
    val stateName: String get() = Aio.nameOf(state, Aio.STATES)
    val actionName: String get() = Aio.nameOf(action, Aio.ACTIONS)
    val gnssQualityName: String get() = Aio.GNSS_QUALITY.getOrNull(gnssQuality) ?: "$gnssQuality"
    val healthNames: List<String> get() = Aio.bitNames(health, Aio.HEALTH_BITS)
    val inhibitNames: List<String> get() = Aio.bitNames(inhibit, Aio.INHIBIT_BITS)
    val navRateHz: Double get() = navRateDhz / 10.0
}
