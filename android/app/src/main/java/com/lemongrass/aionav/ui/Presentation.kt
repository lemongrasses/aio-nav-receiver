// What the screen says, as pure functions of a MonitorSnapshot: a port of the desktop's
// src/aio_receiver/ui/presentation.py (layout C), checked by PresentationTest with the desktop's cases.
// Text comes back as Txt (a string resource and its arguments), resolved in the current language when shown.
//
// Colour carries meaning only:
//   GO    可用 - the output may be used
//   WAIT  不可用, but as expected: alignment in progress or ready still settling; follow the instruction
//   STOP  不可用 because something is wrong: data lost, fault, stale, flags
//   IDLE  不可用 with nothing to judge yet, or AIO NAV stopped on purpose

package com.lemongrass.aionav.ui

import android.content.res.Resources
import androidx.annotation.ArrayRes
import androidx.annotation.StringRes
import com.lemongrass.aionav.R
import com.lemongrass.aionav.core.Aio
import com.lemongrass.aionav.core.Reason
import com.lemongrass.aionav.monitor.MonitorSnapshot
import java.math.BigDecimal

/** Text to show: a string resource with its arguments (which may be Txt themselves), or a table entry. */
sealed interface Txt {
    data class Res(@StringRes val id: Int, val args: List<Any> = emptyList()) : Txt
    data class Item(@ArrayRes val id: Int, val index: Int) : Txt
}

fun txt(@StringRes id: Int, vararg args: Any): Txt = Txt.Res(id, args.toList())

fun Txt.resolve(res: Resources): String = when (this) {
    is Txt.Res -> if (args.isEmpty()) res.getString(id)
    else res.getString(id, *args.map { if (it is Txt) it.resolve(res) else it }.toTypedArray())
    is Txt.Item -> res.getStringArray(id).getOrNull(index) ?: "#$index"
}

enum class Kind { GO, WAIT, STOP, IDLE }

object Presentation {
    val STARTUP = setOf("BOOTING", "CHECKING", "NAV_STARTING")
    val ALIGNING = setOf("KEEP_STILL", "MOVE_STRAIGHT", "REFINING")
    /** Blocking conditions that are simply the next alignment steps while AIO NAV starts or aligns. */
    val STEP_BITS = setOf("BOOT_IN_PROGRESS", "KEEP_STILL_REQUIRED", "MOVE_STRAIGHT_REQUIRED", "FINE_ALIGNMENT_REQUIRED")
    val DANGER_ACTIONS = setOf("SAFE_STOP", "SERVICE_REQUIRED")

    /** The alignment as a route: (label, states at that station). The last station is READY. */
    val STATIONS = listOf(
        R.string.station_start to STARTUP, R.string.station_still to setOf("KEEP_STILL"),
        R.string.station_straight to setOf("MOVE_STRAIGHT"), R.string.station_fine to setOf("REFINING"),
        R.string.station_usable to setOf("READY"),
    )

    private val STATE_HEADLINE = mapOf(
        "BOOTING" to R.string.band_startup, "CHECKING" to R.string.band_startup, "NAV_STARTING" to R.string.band_startup,
        "KEEP_STILL" to R.string.band_stage1, "MOVE_STRAIGHT" to R.string.band_stage2, "REFINING" to R.string.band_stage3,
        "READY" to R.string.band_ready_inhibit, "DEGRADED" to R.string.band_degraded, "FAULT" to R.string.band_fault,
        "MAINTENANCE" to R.string.band_maintenance,
    )

    // ------------------------------------------------------------------------------ snapshot facts

    fun nothingReceived(s: MonitorSnapshot) = s.counts.nav == 0 && s.counts.status == 0

    /** A valid 0x05 that is no older than the status timeout. */
    fun statusFresh(s: MonitorSnapshot) = s.status != null && (s.statusAge ?: Double.POSITIVE_INFINITY) <= s.cfg.statusTimeout

    /** The 0x05 state's protocol name (READY, KEEP_STILL, ...), or null before any 0x05. */
    fun stateName(s: MonitorSnapshot): String? = s.status?.let { Aio.nameOf(it.state, Aio.STATES) }

    /** Python's `{x:g}` for the thresholds: 3.0 → "3", 0.5 → "0.5". */
    fun g(x: Double): String = BigDecimal.valueOf(x).stripTrailingZeros().toPlainString()

    // ------------------------------------------------------------------------------------- band

    data class Band(val kind: Kind, val word: Txt, val headline: Txt)

    fun band(s: MonitorSnapshot): Band {
        val usable = txt(R.string.usable)
        val blocked = txt(R.string.blocked)
        val v = s.verdict
        if (v.usable) return Band(Kind.GO, usable, txt(R.string.band_usable))
        return when (v.reason) {
            Reason.NO_STATUS -> when {
                nothingReceived(s) -> Band(Kind.IDLE, blocked, txt(R.string.band_nothing))
                s.counts.status == 0 -> Band(Kind.STOP, blocked, txt(R.string.band_no_status))
                else -> Band(Kind.STOP, blocked, txt(R.string.band_status_lost, g(s.cfg.statusTimeout)))
            }
            Reason.NOT_READY -> {
                val name = Aio.nameOf(v.state ?: 0, Aio.STATES)
                val headline = STATE_HEADLINE[name]?.let { txt(it) } ?: txt(R.string.band_state, name)
                when (name) {
                    "MAINTENANCE" -> Band(Kind.IDLE, blocked, headline)
                    in STARTUP, in ALIGNING -> Band(Kind.WAIT, blocked, headline)
                    else -> Band(Kind.STOP, blocked, headline)
                }
            }
            Reason.READY_NOT_STABLE -> Band(Kind.WAIT, blocked, txt(R.string.band_settling, g(s.cfg.readyStable)))
            Reason.NAV_STALE ->
                if (s.nav == null) Band(Kind.STOP, blocked, txt(R.string.band_no_nav))
                else Band(Kind.STOP, blocked, txt(R.string.band_nav_lost, g(s.cfg.navMaxAge)))
            Reason.NAV_TIME_NOT_FORWARD -> Band(Kind.STOP, blocked, txt(R.string.band_nav_backwards))
            Reason.NAV_NOT_ALIGNED -> Band(Kind.STOP, blocked, txt(R.string.band_not_aligned))
            else -> Band(Kind.STOP, blocked, txt(R.string.band_not_finite))
        }
    }

    // ------------------------------------------------------------------------------------- rail

    enum class RailMode { PROGRESS, DONE, LOST, FAULT, STOPPED, NONE }

    /** Where the alignment stands. `at` is the current station (-1 = off the route). */
    data class Rail(val at: Int, val mode: RailMode, val fraction: Double, val note: Txt?)

    fun rail(s: MonitorSnapshot): Rail {
        if (!statusFresh(s)) {
            return Rail(-1, RailMode.NONE, 0.0, if (nothingReceived(s)) null else txt(R.string.rail_no_status))
        }
        val name = stateName(s)
        if (name == "READY") {
            val readyFor = s.readyFor ?: return Rail(4, RailMode.PROGRESS, 0.0, txt(R.string.rail_ready_inhibit))
            val stable = s.cfg.readyStable
            val f = if (stable <= 0) 1.0 else (readyFor / stable).coerceIn(0.0, 1.0)
            return Rail(4, if (f >= 1.0) RailMode.DONE else RailMode.PROGRESS, f, null)
        }
        STATIONS.forEachIndexed { i, (_, states) -> if (name in states) return Rail(i, RailMode.PROGRESS, 0.0, null) }
        return when (name) {
            "DEGRADED" -> Rail(4, RailMode.LOST, 0.0, txt(R.string.rail_degraded))
            "FAULT" -> Rail(-1, RailMode.FAULT, 0.0, txt(R.string.rail_fault))
            "MAINTENANCE" -> Rail(-1, RailMode.STOPPED, 0.0, txt(R.string.rail_stopped))
            else -> Rail(-1, RailMode.NONE, 0.0, txt(R.string.rail_unknown, name ?: "?"))
        }
    }

    // ------------------------------------------------------------------------------------ guide

    enum class GuideKind { PLATE, DANGER, QUIET }

    /** The one thing the operator does now, under the verdict; null before anything arrives. */
    data class Guide(val kind: GuideKind, val title: Txt, val sub: Txt?)

    fun guide(s: MonitorSnapshot): Guide? {
        if (nothingReceived(s)) return null
        if (!statusFresh(s)) {
            val status = s.status
            if (s.counts.status == 0 || status == null) {       // 0x04 arrives, 0x05 never has: setup
                return Guide(GuideKind.PLATE, txt(R.string.guide_no_status), txt(R.string.guide_no_status_sub))
            }
            return Guide(GuideKind.PLATE, txt(R.string.guide_status_lost),   // it worked before: dashboard or network
                txt(R.string.guide_status_lost_sub, fmtAge(s.statusAge ?: 0.0), s.counts.status))
        }
        val action = s.status!!.action
        val name = Aio.nameOf(action, Aio.ACTIONS)
        val text = Txt.Item(R.array.action_texts, action)
        return when (name) {
            "NONE" -> Guide(GuideKind.QUIET, text, null)
            in DANGER_ACTIONS -> Guide(GuideKind.DANGER, text, null)
            else -> Guide(GuideKind.PLATE, text, null)
        }
    }

    // -------------------------------------------------------------- blocking and met conditions

    /** `expected`: a normal alignment step (amber), not a problem (red). */
    data class Chip(val text: Txt, val expected: Boolean)

    /** The 0x05 blocking conditions, or null when there is no current 0x05 to say. */
    fun blocking(s: MonitorSnapshot): List<Chip>? {
        if (!statusFresh(s)) return null
        val status = s.status!!
        val aligning = Aio.nameOf(status.state, Aio.STATES) in STARTUP + ALIGNING
        return Aio.INHIBIT_BITS.indices.filter { status.inhibit shr it and 1L == 1L }
            .map { Chip(Txt.Item(R.array.inhibit_names, it), aligning && Aio.INHIBIT_BITS[it] in STEP_BITS) }
    }

    /** (condition, met) for every 0x05 health flag, the unmet first; empty before any 0x05. */
    fun conditions(s: MonitorSnapshot): List<Pair<Txt, Boolean>> {
        val status = s.status ?: return emptyList()
        return Aio.HEALTH_BITS.indices
            .map { Txt.Item(R.array.health_names, it) as Txt to (status.health shr it and 1L == 1L) }
            .sortedBy { it.second }                         // stable: bit order within each group
    }

    // ---------------------------------------------------------------------------- stream links

    data class Link(val kind: Kind, val text: Txt)

    fun navLink(s: MonitorSnapshot): Link {
        val age = s.navAge
        if (s.nav == null || age == null) return Link(Kind.IDLE, txt(R.string.link_none))
        if (age > s.cfg.navMaxAge) return Link(Kind.STOP, txt(R.string.link_lost, fmtAge(age)))
        return Link(Kind.GO, txt(R.string.link_nav, s.navRateHz, age * 1000))
    }

    fun statusLink(s: MonitorSnapshot): Link {
        val age = s.statusAge
        if (s.status == null || age == null) {
            if (s.nav != null && s.counts.status == 0) return Link(Kind.STOP, txt(R.string.link_never))
            return Link(Kind.IDLE, txt(R.string.link_none))
        }
        if (age > s.cfg.statusTimeout) return Link(Kind.STOP, txt(R.string.link_lost, fmtAge(age)))
        return Link(Kind.GO, txt(R.string.link_status, s.statusRateHz, age))
    }

    fun fmtAge(seconds: Double): Txt = when {
        seconds < 60 -> txt(R.string.age_s, seconds)
        seconds < 3600 -> txt(R.string.age_ms, (seconds / 60).toInt(), (seconds % 60).toInt())
        else -> txt(R.string.age_hm, (seconds / 3600).toInt(), (seconds % 3600 / 60).toInt())
    }
}
