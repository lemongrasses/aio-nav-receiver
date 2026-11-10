// Layout C: road-signage colours that only ever carry meaning (docs/UI-PHONE-C.zh-TW.md section 1; the desktop's
// ui/theme.py is the same set), and the parts the four tabs share: the signal mast, the instruction plate, chips,
// the expandable rows and the dark page header. Light only (decision D2): the signal colours are tuned for white.

package com.lemongrass.aionav.ui

import android.provider.Settings
import androidx.annotation.StringRes
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.lemongrass.aionav.R
import java.util.Locale

/** The colour tokens (section 1.1). Meaning only, never decoration. */
object C {
    val Asphalt = Color(0xFF1D252C)       // text, the mast, tab bar, headers
    val Kerb = Color(0xFFE9ECEE)          // page background
    val Panel = Color(0xFFFFFFFF)
    val Text2 = Color(0xFF3B454E)
    val Muted = Color(0xFF56616B)         // labels and hints
    val Faint = Color(0xFF6B757E)         // not received yet, future stations, out-of-date values (4.5:1 on white)
    val Line = Color(0xFFD5DADF)          // rules and outlines, never text
    val Rule = Color(0xFFEEF0F2)          // between settings rows
    val Go = Color(0xFF1E7B45)
    val Wait = Color(0xFFF2B705)          // dark text on it
    val Stop = Color(0xFFB3261E)
    val Idle = Color(0xFF5F6A73)
    val Info = Color(0xFF1B4F9C)          // what to do now; the apply bar
    val InfoInk = Color(0xFFE3ECF9)
    val LampOff = Color(0xFF2B353D)
    val LampRingOff = Color(0xFF46525C)
    val LampTextOff = Color(0xFF9AA4AC)
    val GoTint = Color(0xFFDDEFE3)        // an aiding update this epoch
    val GoInk = Color(0xFF145A32)
    val Amber = Color(0xFF8A5A00)         // counters worth a look; the wait colour where yellow would not read
    val AmberInk = Color(0xFF6B4600)
    val TabOff = Color(0xFFAEB6BD)
    val HeaderInk2 = Color(0xFFC9D0D6)
    val InputLine = Color(0xFF8A949C)
    val Warning = Color(0xFF8A3B00)
    val BlockedTrack = Color(0xFF7B858E)
    val Empty = Color(0xFFF1F3F5)         // signal history: a lamp that was off

    data class ChipStyle(val bg: Color, val ink: Color, val line: Color)

    val ChipExpected = ChipStyle(Color(0xFFFFF1BF), AmberInk, Color(0xFFE5C44D))    // a normal alignment step
    val ChipProblem = ChipStyle(Color(0xFFFBE4E2), Stop, Color(0xFFE6A39E))
    val ChipAid = ChipStyle(GoTint, GoInk, GoTint)
    val ChipAidOff = ChipStyle(Panel, Faint, Line)

    fun signal(kind: Kind) = when (kind) {
        Kind.GO -> Go
        Kind.WAIT -> Wait
        Kind.STOP -> Stop
        Kind.IDLE -> Idle
    }

    /** Text on a signal-coloured background: yellow takes dark text. */
    fun onSignal(kind: Kind) = if (kind == Kind.WAIT) Asphalt else Color.White
}

/** Numbers in tabular figures (decision D5: the system font, no embedded typeface). */
val Num = TextStyle(fontFeatureSettings = "tnum")

@Composable
fun AioTheme(content: @Composable () -> Unit) {
    val colors = lightColorScheme(
        primary = C.Asphalt, onPrimary = Color.White, background = C.Kerb, surface = C.Panel,
        onSurface = C.Asphalt, onSurfaceVariant = C.Muted, outline = C.InputLine, outlineVariant = C.Line,
        error = C.Stop, surfaceContainer = C.Panel,
    )
    MaterialTheme(colorScheme = colors, content = content)
}

@Composable
fun Txt.text(): String = resolve(LocalResources.current)

/** "Reduce motion": the animator duration scale set to 0 in the developer or accessibility settings. */
@Composable
fun reduceMotion(): Boolean {
    val resolver = LocalContext.current.contentResolver
    return remember { Settings.Global.getFloat(resolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f }
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

// ----------------------------------------------------------------------------------- the signal mast

@StringRes
fun mastDescription(kind: Kind) = when (kind) {
    Kind.GO -> R.string.mast_a11y_go
    Kind.WAIT -> R.string.mast_a11y_wait
    Kind.STOP -> R.string.mast_a11y_stop
    Kind.IDLE -> R.string.mast_a11y_idle
}

/**
 * Three lamps, red on top (a problem), yellow (wait, as expected), green at the bottom (usable): the position says
 * the meaning, so it reads without colour. All dark for IDLE. `dim` turns the lit lamp off (the flash).
 */
@Composable
fun SignalMast(kind: Kind, vertical: Boolean, lamp: Dp, modifier: Modifier = Modifier, dim: Boolean = false) {
    val gap = if (vertical) 5.dp else 6.dp
    val long = lamp * 3 + gap * 2
    val description = stringResource(mastDescription(kind))
    Canvas(
        modifier
            .size(if (vertical) lamp else long, if (vertical) long else lamp)
            .semantics { contentDescription = description },
    ) {
        val r = lamp.toPx() / 2
        val ring = 2.dp.toPx()
        listOf(Kind.STOP, Kind.WAIT, Kind.GO).forEachIndexed { i, k ->
            val along = r + i * (lamp + gap).toPx()
            val center = if (vertical) Offset(r, along) else Offset(along, r)
            val on = k == kind && !dim
            drawCircle(if (on) C.signal(k) else C.LampOff, r, center)
            drawCircle(if (on) Color.White else C.LampRingOff, r - ring / 2, center, style = Stroke(ring))
            if (lamp >= 34.dp) {                            // the icons, drawn: every font has them
                val ink = if (on) C.onSignal(k) else C.LampRingOff
                val q = r / 48f                 // the desktop's icon scale
                when (k) {
                    Kind.STOP -> {
                        drawLine(ink, center + Offset(0f, -13 * q), center + Offset(0f, 3 * q), 6 * q, StrokeCap.Round)
                        drawCircle(ink, 4 * q, center + Offset(0f, 13 * q))
                    }
                    Kind.WAIT -> {
                        drawCircle(ink, 17 * q, center, style = Stroke(4.5f * q))
                        drawPath(Path().apply {
                            moveTo(center.x, center.y - 10 * q); lineTo(center.x, center.y + q)
                            lineTo(center.x + 7 * q, center.y + 6 * q)
                        }, ink, style = Stroke(4.5f * q, cap = StrokeCap.Round, join = StrokeJoin.Round))
                    }
                    else -> drawPath(Path().apply {
                        moveTo(center.x - 12 * q, center.y + q); lineTo(center.x - 3 * q, center.y + 10 * q)
                        lineTo(center.x + 13 * q, center.y - 9 * q)
                    }, ink, style = Stroke(6 * q, cap = StrokeCap.Round, join = StrokeJoin.Round))
                }
            }
        }
    }
}

@StringRes
fun mastWord(kind: Kind) = when (kind) {
    Kind.GO -> R.string.mast_go
    Kind.WAIT -> R.string.mast_wait
    Kind.STOP -> R.string.mast_stop
    Kind.IDLE -> R.string.link_none
}

/** The dark header of the Charts, Track and Settings tabs: title, and the small mast with its word. */
@Composable
fun PageHeader(title: String, kind: Kind?, extra: (@Composable ColumnScope.() -> Unit)? = null) {
    Column(
        Modifier.fillMaxWidth().background(C.Asphalt).statusBarsPadding().padding(start = 16.dp, end = 16.dp, top = 12.dp,
            bottom = if (extra != null) 14.dp else 12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, Modifier.weight(1f), color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold)
            if (kind != null) {
                SignalMast(kind, vertical = false, lamp = 14.dp)
                Text(stringResource(mastWord(kind)), Modifier.padding(start = 6.dp), color = Color.White, fontSize = 13.sp)
            }
        }
        extra?.invoke(this)
    }
}

// ---------------------------------------------------------------------------------- the glance zone

/**
 * The road-sign plate with what to do now: blue (mandatory), red for SAFE_STOP / SERVICE_REQUIRED.
 * A 2 dp outer line, 3 dp white, then the plate, like a real sign.
 */
@Composable
fun InstructionPlate(title: String, sub: String?, danger: Boolean, modifier: Modifier = Modifier, person: Boolean = true) {
    val color = if (danger) C.Stop else C.Info
    val shape = RoundedCornerShape(8.dp)
    Box(modifier.fillMaxWidth().border(2.dp, color, shape).padding(2.dp).background(Color.White, RoundedCornerShape(6.dp))
        .padding(3.dp).background(color, RoundedCornerShape(5.dp)).padding(horizontal = 12.dp, vertical = 10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            if (person) Icon(Icons.Filled.Person, null, Modifier.size(24.dp), tint = Color.White)
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(title, color = Color.White, fontSize = if (sub == null) 21.sp else 18.sp, fontWeight = FontWeight.Bold,
                    lineHeight = if (sub == null) 27.sp else 24.sp)
                if (sub != null) Text(sub, color = C.InfoInk, fontSize = 13.sp, lineHeight = 18.sp)
            }
        }
    }
}

/** A blocking condition, a health condition or an aiding flag, as a small sign. */
@Composable
fun SignChip(text: String, style: C.ChipStyle) {
    Text(
        text,
        Modifier.background(style.bg, RoundedCornerShape(4.dp)).border(1.dp, style.line, RoundedCornerShape(4.dp))
            .padding(horizontal = 8.dp, vertical = 4.dp),
        color = style.ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold,
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ChipRow(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    FlowRow(modifier, horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        content()
    }
}

// --------------------------------------------------------------------------------- the detail zone

/**
 * A row of the status tab's detail: title, a one-line summary and a chevron; the content shows when open.
 * At least 48 dp high; TalkBack reads "expanded" / "collapsed".
 */
@Composable
fun ExpandRow(
    title: String,
    expanded: Boolean,
    onToggle: () -> Unit,
    summary: @Composable () -> Unit,
    content: @Composable ColumnScope.() -> Unit,
) {
    val state = stringResource(if (expanded) R.string.expanded else R.string.collapsed)
    Column(Modifier.fillMaxWidth().background(C.Panel)) {
        HorizontalDivider(color = C.Line)
        Row(
            Modifier.fillMaxWidth().heightIn(min = 48.dp)
                .clickable(role = Role.Button, onClick = onToggle)
                .semantics { stateDescription = state }
                .padding(horizontal = 16.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(title, fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = C.Asphalt)
            Spacer(Modifier.width(12.dp))
            Box(Modifier.weight(1f), contentAlignment = Alignment.CenterEnd) { summary() }
            Icon(if (expanded) Icons.Filled.KeyboardArrowUp else Icons.Filled.KeyboardArrowDown, null, tint = C.Muted)
        }
        if (expanded) {
            Column(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, bottom = 14.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp), content = content)
        }
    }
}

/** A summary on the right of an expandable row: one line, ellipsised. */
@Composable
fun Summary(text: String, color: Color = C.Muted) {
    Text(text, color = color, fontSize = 13.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, style = Num)
}

/** Label / value pairs in two columns (label 12 Muted, value 14). Out-of-date values are Faint. */
@Composable
fun ValueGrid(rows: List<Pair<String, String>>, faint: Boolean = false) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        rows.chunked(2).forEach { pair ->
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                pair.forEach { (label, value) ->
                    Column(Modifier.weight(1f)) {
                        Text(label, color = C.Muted, fontSize = 12.sp)
                        Text(value, color = if (faint) C.Faint else C.Asphalt, fontSize = 14.sp, fontWeight = FontWeight.Medium,
                            style = Num)
                    }
                }
                if (pair.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
fun SubTitle(text: String, color: Color = C.Muted, trailing: String? = null) {
    Row(Modifier.fillMaxWidth()) {
        Text(text, Modifier.weight(1f), color = color, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        if (trailing != null) Text(trailing, color = color, fontSize = 12.sp, style = Num)
    }
}
