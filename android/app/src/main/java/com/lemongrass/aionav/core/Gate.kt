// May the 0x04 navigation data be used? A port of the desktop app's src/aio_receiver/core/gate.py, the
// reference for the rules; fixtures/gate_vectors.json and the real recordings hold this port to it.
//
// Blocked by default. Usable only when all hold:
// 1. a valid 0x05 arrived within statusTimeout (bad checksum / version / new session clears it);
// 2. state READY and inhibit 0, continuously for readyStable in one session;
// 3. newest 0x04 at most navMaxAge old;  4. its time moved forward;
// 5. ALIGN, HEADING and FINE set;  6. every float finite.
//
// Pure: the caller passes the receive time of each packet (a monotonic clock) and the time to judge at.
// Rules 1-3 also change with no packet at all, when a limit runs out; nextDeadline() says when.

package com.lemongrass.aionav.core

enum class PacketKind { NAV, STATUS }

enum class Reason {
    USABLE, NO_STATUS, NOT_READY, READY_NOT_STABLE, NAV_STALE, NAV_TIME_NOT_FORWARD, NAV_NOT_ALIGNED, NAV_NOT_FINITE,
}

/** `state` and `inhibit` are set for NOT_READY only: the 0x05 behind it. */
data class Verdict(val reason: Reason, val state: Int? = null, val inhibit: Long = 0) {
    val usable: Boolean get() = reason == Reason.USABLE

    /** The desktop's Verdict.text, which its logs and the .expected.json files record. */
    val desktopText: String
        get() = when (reason) {
            Reason.USABLE -> "可用"
            Reason.NO_STATUS -> "沒有最新的狀態封包 (0x05)"
            Reason.NOT_READY -> {
                val inh = Aio.bitNames(inhibit, Aio.INHIBIT_BITS).joinToString(", ").ifEmpty { "—" }
                "狀態不是 READY：${Aio.nameOf(state ?: 0, Aio.STATES)}（$inh）"
            }
            Reason.READY_NOT_STABLE -> "READY 尚未穩定"
            Reason.NAV_STALE -> "導航資料太舊 (0x04)"
            Reason.NAV_TIME_NOT_FORWARD -> "導航時間沒有往前"
            Reason.NAV_NOT_ALIGNED -> "導航旗標未對準"
            Reason.NAV_NOT_FINITE -> "導航資料不是有限值"
        }

    companion object {
        val USABLE = Verdict(Reason.USABLE)
        val NO_STATUS = Verdict(Reason.NO_STATUS)
    }
}

data class GateConfig(
    val statusId: Int = Aio.STATUS_ID,
    /** Accept packets from this IPv4 only (null = any). */
    val allowedFrom: String? = null,
    val statusTimeout: Double = 3.0,
    val readyStable: Double = 2.0,
    val navMaxAge: Double = 0.5,
)

data class Counters(
    var nav: Int = 0,
    var status: Int = 0,
    var lost: Long = 0,
    var reordered: Int = 0,
    var bad: Int = 0,
    /** 0x05 more than REORDER_WINDOW behind: a second sender in one session. Each one clears. */
    var conflicts: Int = 0,
    /** Datagrams from a source other than allowedFrom; counted, never used. */
    var foreign: Int = 0,
)

class Gate(val cfg: GateConfig = GateConfig()) {
    var status: StatusPacket? = null; private set
    var statusAt = 0.0; private set
    var readySince: Double? = null; private set
    var session: Long? = null; private set
    var nav: NavPacket? = null; private set
    var navAt = 0.0; private set
    var navBackwards = false; private set
    val count = Counters()

    private fun clear() {
        status = null
        readySince = null
        session = null
    }

    /**
     * Take one datagram received at `now`. Returns NAV, STATUS or null (ignored or invalid).
     * `sender` null means unknown (an old recording): the source filter cannot apply.
     */
    fun feed(pkt: ByteArray, now: Double, sender: String?): PacketKind? {
        val allowed = cfg.allowedFrom
        if (!allowed.isNullOrEmpty() && sender != null && sender != allowed) {
            count.foreign += 1
            return null
        }
        val mid = Aio.messageId(pkt)
        if (mid == cfg.statusId) return feedStatus(pkt, now)
        if (mid == Aio.NAV_ID) {
            val n = Aio.decodeNav(pkt)
            if (n == null) {
                count.bad += 1
                return null
            }
            count.nav += 1
            val previous = nav
            navBackwards = previous != null && java.lang.Long.compareUnsigned(n.timeUs, previous.timeUs) <= 0
            nav = n
            navAt = now
            return PacketKind.NAV
        }
        count.bad += 1
        return null
    }

    private fun feedStatus(pkt: ByteArray, now: Double): PacketKind? {
        val s = Aio.decodeStatus(pkt, cfg.statusId)
        if (s == null) {
            count.bad += 1
            clear()                                 // broken or unknown status: stop trusting
            return null
        }
        count.status += 1
        val previous = status
        if (session != null && s.session != session) {
            clear()                                 // the dashboard restarted
        } else if (previous != null) {
            val gap = (s.sequence - previous.sequence) and 0xFFFFFFFFL
            if (gap == 0L || gap > 0x7FFFFFFFL) {
                val back = (previous.sequence - s.sequence) and 0xFFFFFFFFL
                if (back <= REORDER_WINDOW) {
                    count.reordered += 1
                    return PacketKind.STATUS        // old or duplicate: ignore its content
                }
                count.conflicts += 1
                clear()                             // two senders in one session: start over from this one
            } else {
                count.lost += gap - 1
            }
        }
        session = s.session
        status = s
        statusAt = now
        if (s.state == Aio.READY && s.inhibit == 0L) {
            if (readySince == null) readySince = now
        } else {
            readySince = null
        }
        return PacketKind.STATUS
    }

    fun verdict(now: Double): Verdict {
        val s = status
        if (s == null || now - statusAt > cfg.statusTimeout) return Verdict.NO_STATUS
        val ready = readySince ?: return Verdict(Reason.NOT_READY, s.state, s.inhibit)
        if (now - ready < cfg.readyStable) return Verdict(Reason.READY_NOT_STABLE)
        val n = nav
        if (n == null || now - navAt > cfg.navMaxAge) return Verdict(Reason.NAV_STALE)
        if (navBackwards) return Verdict(Reason.NAV_TIME_NOT_FORWARD)
        if (!n.isAligned) return Verdict(Reason.NAV_NOT_ALIGNED)
        if (!n.isFinite) return Verdict(Reason.NAV_NOT_FINITE)
        return Verdict.USABLE
    }

    /** The earliest time > `after` at which the verdict can change without a new packet. */
    fun nextDeadline(after: Double): Double? {
        val times = ArrayList<Double>(3)
        if (status != null) {
            times += statusAt + cfg.statusTimeout
            readySince?.let { times += it + cfg.readyStable }
        }
        if (nav != null) times += navAt + cfg.navMaxAge
        return times.filter { it > after }.minOrNull()
    }

    companion object {
        /** A 0x05 sequence going back more than this = a second sender (spec). */
        const val REORDER_WINDOW = 5L
    }
}
