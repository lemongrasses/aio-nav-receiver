package com.lemongrass.aionav.ui

import androidx.annotation.StringRes
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.lemongrass.aionav.R
import com.lemongrass.aionav.core.Aio
import com.lemongrass.aionav.core.Reason
import com.lemongrass.aionav.core.Verdict
import java.util.Locale

val UsableGreen = Color(0xFF2E7D32)
val BlockedRed = Color(0xFFC62828)
val InfoBlue = Color(0xFF1565C0)
val WarningOrange = Color(0xFFE65100)

@Composable
fun AioTheme(content: @Composable () -> Unit) {
    val colors = if (isSystemInDarkTheme()) darkColorScheme() else lightColorScheme()
    MaterialTheme(colorScheme = colors, content = content)
}

/** Reason shown when blocked, in the order the rules are checked. */
@StringRes
fun reasonTitle(reason: Reason): Int = when (reason) {
    Reason.USABLE -> R.string.reason_usable
    Reason.NO_STATUS -> R.string.reason_no_status
    Reason.NOT_READY -> R.string.reason_not_ready
    Reason.READY_NOT_STABLE -> R.string.reason_ready_not_stable
    Reason.NAV_STALE -> R.string.reason_nav_stale
    Reason.NAV_TIME_NOT_FORWARD -> R.string.reason_nav_time
    Reason.NAV_NOT_ALIGNED -> R.string.reason_not_aligned
    Reason.NAV_NOT_FINITE -> R.string.reason_not_finite
}

/** For "not READY": the state and the inhibit bit names. */
fun verdictDetail(v: Verdict): String? {
    if (v.reason != Reason.NOT_READY) return null
    val names = Aio.bitNames(v.inhibit, Aio.INHIBIT_BITS)
    return Aio.nameOf(v.state ?: 0, Aio.STATES) + " · inhibit " + names.ifEmpty { listOf("0") }.joinToString(", ")
}

/** What the operator should do (readiness ACTION_TEXT); null for NONE or an unknown code. */
@StringRes
fun actionText(action: Int): Int? = when (Aio.ACTIONS.getOrNull(action)) {
    "HOLD_STILL" -> R.string.action_hold_still
    "DRIVE_STRAIGHT" -> R.string.action_drive_straight
    "KEEP_DRIVING" -> R.string.action_keep_driving
    "SAFE_STOP" -> R.string.action_safe_stop
    "SERVICE_REQUIRED" -> R.string.action_service_required
    "MAINTENANCE_HOLD" -> R.string.action_maintenance_hold
    else -> null
}

object Format {
    fun number(value: Double, digits: Int, unit: String = ""): String {
        if (!value.isFinite()) return "—"
        return String.format(Locale.ROOT, "%.${digits}f", value) + if (unit.isEmpty()) "" else " $unit"
    }

    fun duration(seconds: Double): String {
        val s = seconds.toLong()
        return String.format(Locale.ROOT, "%d:%02d:%02d", s / 3600, s / 60 % 60, s % 60)
    }
}

/** A rounded section on a page. */
@Composable
fun Card(title: String, modifier: Modifier = Modifier, tint: Color? = null, content: @Composable ColumnScope.() -> Unit) {
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(20.dp),
        color = MaterialTheme.colorScheme.surfaceContainer,
    ) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold,
                color = tint ?: MaterialTheme.colorScheme.onSurface)
            content()
        }
    }
}

@Composable
fun InfoRow(@StringRes label: Int, value: String) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top) {
        Text(stringResource(label), style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.weight(1f).width(12.dp))
        Text(value, style = MaterialTheme.typography.bodyMedium, textAlign = TextAlign.End,
            fontFamily = FontFamily.Monospace)
    }
}

@Composable
fun SubTitle(@StringRes text: Int) {
    Text(stringResource(text), style = MaterialTheme.typography.labelLarge,
        color = MaterialTheme.colorScheme.onSurfaceVariant)
}

/** A flag or bit name; dimmed when off. */
@Composable
fun Chip(text: String, tint: Color = UsableGreen, on: Boolean = true) {
    Text(
        text,
        modifier = Modifier
            .background(if (on) tint else MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(50))
            .padding(horizontal = 8.dp, vertical = 4.dp),
        style = MaterialTheme.typography.labelSmall,
        fontFamily = FontFamily.Monospace,
        fontWeight = FontWeight.SemiBold,
        color = if (on) Color.White else MaterialTheme.colorScheme.onSurfaceVariant,
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ChipRow(content: @Composable () -> Unit) {
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        content()
    }
}
