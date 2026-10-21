// The rules are shared with the desktop and iOS apps through the repository's fixtures/ folder:
// - gate_vectors.json: a scripted packet stream with the desktop gate's verdict and counters at every step
//   (tools/make_gate_vectors.py);
// - real_*.bin.gz + .expected.json: real Jetson recordings with the verdict transitions the desktop expects
//   (tests/test_regression.py checks the same files).
// JVM tests: they read ../fixtures from the source tree (the fixtures.dir property set in app/build.gradle.kts).

package com.lemongrass.aionav.core

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

object Fixtures {
    val folder = File(System.getProperty("fixtures.dir") ?: "../../fixtures")

    fun bytes(name: String): ByteArray = File(folder, name).readBytes()

    fun json(name: String): JSONObject = JSONObject(File(folder, name).readText())

    fun vectors(): JSONObject = json("gate_vectors.json")
}

fun hex(s: String): ByteArray = ByteArray(s.length / 2) { s.substring(2 * it, 2 * it + 2).toInt(16).toByte() }

/** The names make_gate_vectors.py writes for each Reason (the iOS VehicleGate.Verdict case names). */
val Reason.kind: String
    get() = when (this) {
        Reason.USABLE -> "usable"
        Reason.NO_STATUS -> "noStatus"
        Reason.NOT_READY -> "notReady"
        Reason.READY_NOT_STABLE -> "readyNotStable"
        Reason.NAV_STALE -> "navTooOld"
        Reason.NAV_TIME_NOT_FORWARD -> "navTimeBackwards"
        Reason.NAV_NOT_ALIGNED -> "notAligned"
        Reason.NAV_NOT_FINITE -> "notFinite"
    }

private fun withChecksum(p: ByteArray): ByteArray {
    var sum = 0
    for (i in 2 until p.size - 1) sum += p[i].toInt() and 0xFF
    p[p.size - 1] = sum.toByte()
    return p
}

class StatusPacketTest {
    @Test
    fun decodesGoldenVector() {
        val packet = Fixtures.vectors().getString("golden_status")
        assertTrue(packet.endsWith("5c"))                      // the checksum printed in the spec
        val s = Aio.decodeStatus(hex(packet))!!
        assertEquals("READY", s.stateName)
        assertEquals("NONE", s.actionName)
        assertEquals("RTK float", s.gnssQualityName)
        assertEquals(0x12345678L, s.session)
        assertEquals(482L, s.sequence)
        assertEquals(123456789L, s.uptimeMs)
        assertEquals(0x10FFFL, s.health)
        assertEquals(0L, s.inhibit)
        assertEquals(0xE8, s.navFlags)
        assertEquals(100.0, s.navRateHz, 0.0)
        assertEquals(12, s.navAgeMs)
        assertEquals(13, s.healthNames.size)
        assertEquals("NO_DUPLICATE_PROCESS", s.healthNames.last())
    }

    @Test
    fun rejectsBadChecksumVersionAndLength() {
        val good = hex(Fixtures.vectors().getString("golden_status"))
        assertNull(Aio.decodeStatus(good.copyOf().also { it[20] = (it[20].toInt() xor 1).toByte() }))
        assertNull(Aio.decodeStatus(withChecksum(good.copyOf().also { it[5] = 2 })))
        assertNull(Aio.decodeStatus(good.copyOf(41)))
        assertNull(Aio.decodeStatus(good + byteArrayOf(0)))    // exact length only, like the desktop
        assertNull(Aio.decodeStatus(good, msgId = 0x06))
        assertEquals(Aio.STATUS_LEN, good.size)
    }

    @Test
    fun encoderRoundTrips() {
        val p = Aio.encodeStatus(6, 0, 0x12345678, 482, gnssQuality = 3, uptimeMs = 123456789, health = 0x10FFF,
            navFlags = 0xE8, navRateDhz = 1000, navAgeMs = 12)
        assertEquals(Fixtures.vectors().getString("golden_status"), p.joinToString("") { "%02x".format(it) })
    }
}

class NavPacketTest {
    @Test
    fun decodesReferenceEncoderOutput() {
        val n = Aio.decodeNav(hex(Fixtures.vectors().getString("nav_example")))!!
        assertEquals(345678.123456, n.timeS, 1e-9)
        assertEquals(22.99690123, n.lat, 0.0)
        assertEquals(120.22180456, n.lon, 0.0)
        assertEquals(35.25f, n.height)
        assertEquals(1.5f, n.vn); assertEquals(-2.0f, n.ve); assertEquals(0.25f, n.vu)
        assertEquals(1.25f, n.roll); assertEquals(-2.5f, n.pitch)
        assertEquals(-90f, n.heading)
        assertEquals(270.0, n.heading360, 0.0)                 // negative headings show as 0..360
        assertEquals(2.5, n.groundSpeed, 0.0)
        assertEquals(0.05f, n.posNStd); assertEquals(0.3f, n.headingStd)
        assertTrue(n.gyroBias.contentEquals(floatArrayOf(1.5f, -0.7f, 2.1f)))
        assertTrue(n.accelScale.contentEquals(floatArrayOf(200f, 150f, -90f)))
        assertEquals(1.01f, n.odoScale); assertEquals(-1.5f, n.mountYaw)
        assertTrue(n.hasFlag("ZUPT") && n.hasFlag("GNSS") && !n.hasFlag("NHC"))
        assertTrue(n.isAligned)
        assertTrue(n.isFinite)
    }

    @Test
    fun flagsAreBitReversedOnTheWire() {
        assertEquals(0b1000_0000, Aio.reverseBits8(0b0000_0001))
        assertEquals(0x17, Aio.reverseBits8(0xE8))
        assertEquals(0x5A, Aio.reverseBits8(Aio.reverseBits8(0x5A)))
        val n = Aio.decodeNav(hex(Fixtures.vectors().getString("nav_example")))!!
        assertEquals(Aio.reverseBits8(n.flags), n.flagsWire and 0xFF)
    }

    @Test
    fun rejectsWrongLengthOrChecksum() {
        val good = hex(Fixtures.vectors().getString("nav_example"))
        assertEquals(Aio.NAV_LEN, good.size)
        assertNull(Aio.decodeNav(good.copyOf(155)))
        assertNull(Aio.decodeNav(good + byteArrayOf(0)))
        assertNull(Aio.decodeNav(good.copyOf().also { it[155] = (it[155] + 1).toByte() }))
    }

    @Test
    fun encoderMatchesDesktop() {
        val p = Aio.encodeNav(345678.123456, 22.99690123, 120.22180456, height = 35.25f, vn = 1.5f, ve = -2.0f,
            vu = 0.25f, roll = 1.25f, pitch = -2.5f, heading = -90f, flags = 0b1110_1001,
            stds = floatArrayOf(0.05f, 0.05f, 0.1f, 0.02f, 0.02f, 0.03f, 0.05f, 0.05f, 0.3f),
            imu = floatArrayOf(1.5f, -0.7f, 2.1f, 0.3f, -0.2f, 0.5f, 120f, -80f, 40f, 200f, 150f, -90f),
            odoScale = 1.01f, mountPitch = 0.5f, mountYaw = -1.5f)
        assertEquals(Fixtures.vectors().getString("nav_example"), p.joinToString("") { "%02x".format(it) })
    }
}

class GateTest {
    /** The shared contract: the same packet stream must give the desktop gate's verdict and counters. */
    @Test
    fun matchesDesktopGateAtEveryStep() {
        val steps = Fixtures.vectors().getJSONArray("steps")
        assertEquals(460, steps.length())
        val gate = Gate()
        for (i in 0 until steps.length()) {
            val step = steps.getJSONObject(i)
            val t = step.getDouble("t")
            val packets = step.getJSONArray("packets")
            for (j in 0 until packets.length()) gate.feed(hex(packets.getString(j)), t, null)
            val v = gate.verdict(t)
            val at = "t=$t"
            assertEquals(at, step.getString("reason"), v.reason.kind)
            assertEquals(at, step.getBoolean("usable"), v.usable)
            assertEquals(at, step.getInt("nav"), gate.count.nav)
            assertEquals(at, step.getInt("status"), gate.count.status)
            assertEquals(at, step.getLong("lost"), gate.count.lost)
            assertEquals(at, step.getInt("reordered"), gate.count.reordered)
            assertEquals(at, step.getInt("conflicts"), gate.count.conflicts)
            assertEquals(at, step.getInt("bad"), gate.count.bad)
        }
        assertEquals(1, gate.count.conflicts)
    }

    @Test
    fun secondSenderClearsAuthorisation() {
        val golden = hex(Fixtures.vectors().getString("golden_status"))
        val nav = hex(Fixtures.vectors().getString("nav_example"))
        val gate = Gate()
        gate.feed(golden, 0.0, null)
        gate.feed(nav, 2.0, null)
        assertEquals(Verdict.USABLE, gate.verdict(2.0))
        // The same session going back 10: a second sender. Start over from that packet.
        val older = withChecksum(golden.copyOf().also { it[13] = 0xD8.toByte() })   // 472 = 0x1D8 (482 = 0x1E2)
        assertEquals(472L, Aio.decodeStatus(older)!!.sequence)
        gate.feed(older, 2.1, null)
        assertEquals(1, gate.count.conflicts)
        assertEquals(Reason.READY_NOT_STABLE, gate.verdict(2.1).reason)
        assertEquals(Reason.NAV_STALE, gate.verdict(4.2).reason)   // READY settled again; nav is old by now
    }

    @Test
    fun reorderedWithinWindowIsIgnored() {
        val golden = hex(Fixtures.vectors().getString("golden_status"))
        val gate = Gate()
        gate.feed(golden, 0.0, null)
        val back5 = withChecksum(golden.copyOf().also { it[13] = 0xDD.toByte() })   // 477: 5 back
        gate.feed(back5, 0.5, null)
        assertEquals(1, gate.count.reordered)
        assertEquals(0, gate.count.conflicts)
        assertEquals(0.0, gate.statusAt, 0.0)                  // its content was ignored
        assertEquals(0.0, gate.readySince!!, 0.0)
    }

    @Test
    fun singleLostStatusNeverBlocksButTimeoutDoes() {
        val golden = hex(Fixtures.vectors().getString("golden_status"))
        val nav = hex(Fixtures.vectors().getString("nav_example"))
        val gate = Gate()
        gate.feed(golden, 0.0, null)
        assertEquals(Reason.READY_NOT_STABLE, gate.verdict(1.9).reason)
        gate.feed(nav, 2.0, null)
        assertEquals(Verdict.USABLE, gate.verdict(2.0))
        assertEquals(Verdict.USABLE, gate.verdict(2.4))
        assertEquals(Reason.NAV_STALE, gate.verdict(2.6).reason)
        gate.feed(nav, 2.7, null)                               // same time stamp: not forward
        assertEquals(Reason.NAV_TIME_NOT_FORWARD, gate.verdict(2.7).reason)
        assertEquals(Reason.NO_STATUS, gate.verdict(3.01).reason)
        assertEquals(3.0, gate.nextDeadline(2.7)!!, 0.0)
        assertNotNull(gate.readySince)                          // a 0x05 timeout does not clear readySince
        assertEquals(3.2, gate.nextDeadline(3.0)!!, 1e-12)      // then the nav age
        assertNull(gate.nextDeadline(3.2))
    }

    @Test
    fun sourceFilterCountsForeign() {
        val golden = hex(Fixtures.vectors().getString("golden_status"))
        val gate = Gate(GateConfig(allowedFrom = "10.42.0.1"))
        assertNull(gate.feed(golden, 0.0, "10.42.0.99"))
        assertEquals(1, gate.count.foreign)
        assertEquals(PacketKind.STATUS, gate.feed(golden, 0.0, "10.42.0.1"))
        assertEquals(PacketKind.STATUS, gate.feed(golden, 0.1, null))   // unknown sender: filter cannot apply
    }
}

/** The desktop's regression test (tests/test_regression.py) on the same real recordings. */
class RealRecordingTest {
    private fun replay(name: String) {
        val rec = Recording.parse(Recording.gunzip(Fixtures.bytes("$name.bin.gz")))
        val expected = Fixtures.json("$name.expected.json")
        val packets = rec.records
        assertFalse(packets.isEmpty())
        assertEquals(name == "real_ready_v2", rec.hasSenders)

        // analysis.analyse(): advance to the first packet, feed every packet, advance to the last.
        val mon = Monitor(GateConfig())
        val got = ArrayList(mon.advance(packets.first().t))
        for (p in packets) got += mon.feed(p.data, p.t, p.sender).second
        got += mon.advance(packets.last().t)

        val want: JSONArray = expected.getJSONArray("transitions")
        assertEquals(want.length(), got.size)
        for (i in 0 until want.length()) {
            val row = want.getJSONArray(i)
            val t = row.getDouble(0)
            assertEquals("t=$t", t, got[i].t, 1e-9)
            assertEquals("t=$t", row.getBoolean(1), got[i].verdict.usable)
            assertEquals("t=$t", row.getString(2), got[i].verdict.desktopText)
        }
        assertEquals(expected.getDouble("usable_s"), mon.usableTotal, 1e-6)
        val c = expected.getJSONObject("count")
        val count = mon.gate.count
        assertEquals(c.getInt("nav"), count.nav)
        assertEquals(c.getInt("status"), count.status)
        assertEquals(c.getLong("lost"), count.lost)
        assertEquals(c.getInt("reordered"), count.reordered)
        assertEquals(c.getInt("bad"), count.bad)
        assertEquals(c.getInt("conflicts"), count.conflicts)
        assertEquals(c.getInt("foreign"), count.foreign)
        assertEquals(7, c.length())                             // no desktop counter left unchecked
    }

    @Test
    fun restartV1() = replay("real_restart_v1")

    @Test
    fun readyV2() = replay("real_ready_v2")

    @Test
    fun sourceFilterAppliesToV2Replay() {
        val rec = Recording.parse(Recording.gunzip(Fixtures.bytes("real_ready_v2.bin.gz")))
        val mon = Monitor(GateConfig(allowedFrom = "10.0.0.1"))
        mon.advance(rec.records.first().t)
        for (p in rec.records) mon.feed(p.data, p.t, p.sender)
        mon.advance(rec.records.last().t)
        assertEquals(rec.records.size, mon.gate.count.foreign)
        assertEquals(0.0, mon.usableTotal, 0.0)
        assertEquals("192.168.116.1", rec.records.first().sender)
    }
}

/** The core package must stay pure Kotlin, so the same code can be checked off-device. */
class CoreIsPureTest {
    @Test
    fun noAndroidImports() {
        val dir = File("src/main/java/com/lemongrass/aionav/core")
        val files = dir.listFiles { f -> f.extension == "kt" }.orEmpty()
        assertTrue("core sources not found in ${dir.absolutePath}", files.isNotEmpty())
        for (f in files) {
            val bad = f.readLines().filter { it.startsWith("import android") || it.startsWith("import androidx") }
            assertTrue("${f.name}: $bad", bad.isEmpty())
        }
    }
}
