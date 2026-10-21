// Protocol codes as words in the current language (the desktop's i18n state_name, action_text, gnss_quality,
// health_name, inhibit_name, lamp_name). The screen never shows a raw code such as KEEP_STILL_REQUIRED;
// acronyms (GNSS, ZUPT), units and packet ids stay as they are.

package com.lemongrass.aionav.ui

import android.content.res.Resources
import androidx.annotation.ArrayRes
import com.lemongrass.aionav.R
import com.lemongrass.aionav.core.Aio
import com.lemongrass.aionav.core.Reason
import com.lemongrass.aionav.core.Verdict

object Words {
    private fun pick(res: Resources, @ArrayRes table: Int, code: Int): String =
        res.getStringArray(table).getOrNull(code) ?: "#$code"

    fun state(res: Resources, code: Int) = pick(res, R.array.state_names, code)

    /** A state by its protocol name (the timeline keeps names); NO_STATUS has its own words. */
    fun stateByName(res: Resources, name: String): String = when (name) {
        "NO_STATUS" -> res.getString(R.string.legend_no_status)
        "USABLE" -> res.getString(R.string.usable)
        "BLOCKED" -> res.getString(R.string.blocked)
        else -> Aio.STATES.indexOf(name).takeIf { it >= 0 }?.let { state(res, it) } ?: name
    }

    fun action(res: Resources, code: Int) = pick(res, R.array.action_texts, code)

    /** What the operator should do; null for NONE (nothing to show). */
    fun instruction(res: Resources, code: Int): String? = if (code == 0) null else action(res, code)

    fun gnssQuality(res: Resources, code: Int) = pick(res, R.array.gnss_quality_names, code)

    fun health(res: Resources, bit: Int) = pick(res, R.array.health_names, bit)

    fun inhibit(res: Resources, bit: Int) = pick(res, R.array.inhibit_names, bit)

    fun lamp(res: Resources, flag: String): String = when (flag) {
        "ALIGN" -> res.getString(R.string.lamp_align)
        "HEADING" -> res.getString(R.string.lamp_heading)
        "FINE" -> res.getString(R.string.lamp_fine)
        else -> flag
    }

    fun bits(mask: Long, count: Int): List<Int> = (0 until count).filter { mask shr it and 1L == 1L }

    fun healthList(res: Resources, mask: Long) = bits(mask, Aio.HEALTH_BITS.size).map { health(res, it) }

    fun inhibitList(res: Resources, mask: Long) = bits(mask, Aio.INHIBIT_BITS.size).map { inhibit(res, it) }

    fun joined(res: Resources, items: List<String>): String = items.joinToString(res.getString(R.string.list_separator))

    /** Reason shown when blocked, in the order the rules are checked. */
    fun reason(res: Resources, v: Verdict): String = res.getString(when (v.reason) {
        Reason.USABLE -> R.string.reason_usable
        Reason.NO_STATUS -> R.string.reason_no_status
        Reason.NOT_READY -> R.string.reason_not_ready
        Reason.READY_NOT_STABLE -> R.string.reason_ready_not_stable
        Reason.NAV_STALE -> R.string.reason_nav_stale
        Reason.NAV_TIME_NOT_FORWARD -> R.string.reason_nav_time
        Reason.NAV_NOT_ALIGNED -> R.string.reason_not_aligned
        Reason.NAV_NOT_FINITE -> R.string.reason_not_finite
    })

    /** For "not ready": the state and the blocking conditions, e.g. 保持靜止（需要保持靜止、需要精對準）. */
    fun reasonDetail(res: Resources, v: Verdict): String? {
        if (v.reason != Reason.NOT_READY) return null
        val inhibit = joined(res, inhibitList(res, v.inhibit)).ifEmpty { "—" }
        return res.getString(R.string.not_ready_detail, state(res, v.state ?: 0), inhibit)
    }
}
