// Reads the desktop app's .bin recordings (src/aio_receiver/io/recording.py). Pure Kotlin.
//
// v2:  "AIONREC\0" u16 version u32 header_len header(JSON)  then per packet
//      f64 rx_time  u16 length  4s sender IPv4  u16 sender port  bytes[length]
// v1:  no header; per packet  f64 rx_time  u16 length  bytes[length]
// rx_time is the receiver's monotonic clock in seconds. A truncated or out-of-order tail is not a record.

package com.lemongrass.aionav.core

import java.io.ByteArrayInputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.zip.GZIPInputStream

class Record(val t: Double, val sender: String?, val port: Int, val data: ByteArray)

class Recording(val version: Int, val records: List<Record>) {
    val hasSenders: Boolean get() = version >= 2

    companion object {
        private val MAGIC = "AIONREC\u0000".toByteArray(Charsets.US_ASCII)

        fun gunzip(gz: ByteArray): ByteArray = GZIPInputStream(ByteArrayInputStream(gz)).use { it.readBytes() }

        fun parse(bytes: ByteArray): Recording {
            val b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
            var version = 1
            var i = 0
            if (bytes.size >= 14 && bytes.copyOfRange(0, 8).contentEquals(MAGIC)) {
                version = b.getShort(8).toInt() and 0xFFFF
                require(version == 2) { "unsupported recording version $version" }
                i = 14 + b.getInt(10)
            }
            val head = if (version == 2) 16 else 10
            val out = ArrayList<Record>()
            var last = Double.NEGATIVE_INFINITY
            while (i + head <= bytes.size) {
                val t = b.getDouble(i)
                val n = b.getShort(i + 8).toInt() and 0xFFFF
                if (i + head + n > bytes.size) break            // truncated last record
                if (!(t.isFinite() && t >= last)) break         // receive times only go forward
                last = t
                val sender = if (version == 2) (10 until 14).joinToString(".") { bytes.u8(i + it).toString() } else null
                val port = if (version == 2) b.getShort(i + 14).toInt() and 0xFFFF else 0
                out += Record(t, sender, port, bytes.copyOfRange(i + head, i + head + n))
                i += head + n
            }
            return Recording(version, out)
        }
    }
}
