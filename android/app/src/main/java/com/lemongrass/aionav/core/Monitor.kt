// Feeds a Gate in time order and keeps what the screen needs. A port of the desktop app's
// src/aio_receiver/core/monitor.py.
//
// The verdict changes only when a packet arrives or a gate deadline passes. advance() evaluates just after
// each deadline and feed() evaluates at each packet, so transition times and the usable total are exact
// and do not depend on how often anyone looks. Time always comes from the caller: the receive clock live,
// the recorded times in a replay. Not thread-safe: the caller serialises access.

package com.lemongrass.aionav.core

data class Transition(val t: Double, val verdict: Verdict)

class Monitor(cfg: GateConfig) {
    val gate = Gate(cfg)

    /** null until the first evaluation. */
    var verdict: Verdict? = null; private set
    /** When the verdict last changed. */
    var changedAt = Double.NEGATIVE_INFINITY; private set
    /** Time of the last evaluation. */
    var t = Double.NEGATIVE_INFINITY; private set
    var usableTotal = 0.0; private set
    var navSender: String? = null; private set
    var statusSender: String? = null; private set
    private val navTimes = ArrayDeque<Double>()
    private val statusTimes = ArrayDeque<Double>()

    private fun evaluate(at: Double, out: MutableList<Transition>) {
        val v = gate.verdict(at)
        if (verdict?.usable == true) usableTotal += at - t
        t = at
        if (v != verdict) {
            verdict = v
            changedAt = at
            out += Transition(at, v)
        }
    }

    /** Bring the verdict up to `now`, through every deadline on the way. */
    fun advance(now: Double): List<Transition> {
        val out = ArrayList<Transition>(0)
        while (true) {
            val d = gate.nextDeadline(t) ?: break
            if (d + DEADLINE_EPS > now) break
            evaluate(d + DEADLINE_EPS, out)
        }
        if (now >= t) evaluate(now, out)
        return out
    }

    /** One datagram received at `time`. A time before the last evaluation is taken as that time. */
    fun feed(pkt: ByteArray, time: Double, sender: String?): Pair<PacketKind?, List<Transition>> {
        val now = maxOf(time, t)
        val out = advance(now).toMutableList()
        val kind = gate.feed(pkt, now, sender)
        evaluate(now, out)                          // even an invalid 0x05 changes the verdict: it clears it
        when (kind) {
            PacketKind.NAV -> {
                navSender = sender
                window(navTimes, now, RATE_WINDOW)
            }
            PacketKind.STATUS -> {
                statusSender = sender
                window(statusTimes, now, STATUS_RATE_WINDOW)
            }
            null -> Unit
        }
        return kind to out
    }

    fun navRate(now: Double): Double = rate(navTimes, now, RATE_WINDOW)

    fun statusRate(now: Double): Double = rate(statusTimes, now, STATUS_RATE_WINDOW)

    companion object {
        /** Judge this long after a deadline: past it beyond any float rounding. */
        const val DEADLINE_EPS = 1e-6
        /** Seconds of 0x04 arrivals used for its rate. */
        const val RATE_WINDOW = 3.0
        /** 0x05 comes at 2 Hz: a longer window keeps its rate steady. */
        const val STATUS_RATE_WINDOW = 5.0

        /** Packets per second from their spacing in the last `span`: right from the second packet on. */
        private fun rate(times: ArrayDeque<Double>, now: Double, span: Double): Double {
            val recent = times.filter { it >= now - span }
            if (recent.size < 2 || recent.last() <= recent.first()) return 0.0
            return (recent.size - 1) / (recent.last() - recent.first())
        }

        /** Append `now` and drop the times older than `span`. */
        private fun window(times: ArrayDeque<Double>, now: Double, span: Double) {
            times.addLast(now)
            while (times.first() < now - span) times.removeFirst()
        }
    }
}
