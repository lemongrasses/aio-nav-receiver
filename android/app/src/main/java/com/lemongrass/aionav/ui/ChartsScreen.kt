// The charts tab, layout C (docs/UI-PHONE-C.zh-TW.md 4.2): the last 1, 5 or 10 minutes. The signal history shows
// each lamp of the mast as its own row, so it reads without colour; then navigation quality and motion.

package com.lemongrass.aionav.ui

import androidx.annotation.StringRes
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.lemongrass.aionav.R
import com.lemongrass.aionav.monitor.History
import com.lemongrass.aionav.monitor.MonitorSnapshot
import com.lemongrass.aionav.monitor.MonitorStore
import com.lemongrass.aionav.monitor.NavSample
import com.lemongrass.aionav.monitor.TimelineSegment
import kotlinx.coroutines.delay

/** The dashboard-state lane: the alignment in yellows that darken step by step, then the rest. */
val StateColors = linkedMapOf(
    "BOOTING" to Color(0xFF9FA8B0), "CHECKING" to Color(0xFF8A949C), "NAV_STARTING" to Color(0xFF6B757E),
    "KEEP_STILL" to C.Wait, "MOVE_STRAIGHT" to Color(0xFFD99A00), "REFINING" to Color(0xFFA87700),
    "READY" to C.Go, "DEGRADED" to Color(0xFFD9822B), "FAULT" to C.Stop, "MAINTENANCE" to C.LampRingOff,
    "NO_STATUS" to C.TabOff,
)

private val North = C.Info
private val East = Color(0xFFC25E00)
private val Down = Color(0xFF6A3DAD)
private val AgeArea = Color(0xFFFCE3CF)

/** Joins neighbouring segments with the same key into one run: (key, start, end). */
fun merged(segments: List<TimelineSegment>, key: (TimelineSegment) -> String): List<Triple<String, Long, Long>> {
    val runs = ArrayList<Triple<String, Long, Long>>()
    for (s in segments) {
        val k = key(s)
        val last = runs.lastOrNull()
        if (last != null && last.first == k) runs[runs.size - 1] = Triple(k, last.second, s.end)
        else runs += Triple(k, s.start, s.end)
    }
    return runs
}

@Composable
fun ChartsScreen(history: History, snapshot: MonitorSnapshot, kind: Kind) {
    var minutes by rememberSaveable { mutableIntStateOf(5) }          // not remembered across launches, as before
    // Redrawn every 0.5 s so the time axis keeps moving even when nothing arrives.
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(Unit) {
        while (true) {
            now = System.currentTimeMillis()
            delay(MonitorStore.SAMPLE_MS)
        }
    }
    val start = now - minutes * 60_000L
    val nav = history.nav.filter { it.time >= start }
    val link = history.link.filter { it.time >= start }

    fun metric(name: String, color: Color, dash: List<Float>? = null, value: (NavSample) -> Double) =
        ChartSeries(name, color, nav.map { ChartPoint(it.time, value(it), it.run) }, dash)

    Column(Modifier.fillMaxSize()) {
        PageHeader(stringResource(R.string.tab_charts), kind) { WindowPicker(minutes) { minutes = it } }
        Column(Modifier.verticalScroll(rememberScrollState()).padding(top = 10.dp, bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)) {
            SignalHistory(history.timeline.filter { it.end >= start }, start, now, minutes)

            Group(R.string.section_quality)
            val last = nav.lastOrNull()
            ChartCard(R.string.position_sigma, "m",
                last?.let { listOf(it.sigmaN, it.sigmaE, it.sigmaD).joinToString(" / ") { v -> Format.number(v, 2) } }, nav.isEmpty()) {
                TimeChart(listOf(
                    metric(stringResource(R.string.north), North) { it.sigmaN },
                    metric(stringResource(R.string.east), East, listOf(6f, 3f)) { it.sigmaE },
                    metric(stringResource(R.string.down), Down, listOf(2f, 3f)) { it.sigmaD },
                ), start, now)
            }
            ChartCard(R.string.heading_sigma, "°", last?.let { Format.number(it.sigmaHeading, 2) }, nav.isEmpty()) {
                TimeChart(listOf(metric("σ", North) { it.sigmaHeading }), start, now)
            }
            val ages = link.filter { it.navAgeMs != null }
            val limitMs = snapshot.cfg.navMaxAge * 1000
            ChartCard(R.string.data_age_04, "ms", ages.lastOrNull()?.navAgeMs?.let { Format.number(it, 0) }, ages.isEmpty()) {
                TimeChart(listOf(ChartSeries("ms", East, ages.map { ChartPoint(it.time, it.navAgeMs!!) })), start, now,
                    area = AgeArea, limit = limitMs, limitLabel = stringResource(R.string.chart_limit, Format.number(limitMs, 0)))
            }
            ChartCard(R.string.receive_rate, "Hz", link.lastOrNull()?.let { Format.number(it.rateHz, 1) }, link.isEmpty()) {
                TimeChart(listOf(ChartSeries("Hz", North, link.map { ChartPoint(it.time, it.rateHz) })), start, now, step = true)
            }

            Group(R.string.section_motion)
            ChartCard(R.string.speed, "m/s", last?.let { Format.number(it.speed, 2) }, nav.isEmpty()) {
                TimeChart(listOf(metric("m/s", North) { it.speed }), start, now)
            }
            ChartCard(R.string.heading, "°", last?.let { Format.number(it.heading, 1) }, nav.isEmpty()) {
                TimeChart(listOf(metric("°", North) { it.heading }), start, now, yDomain = 0.0..360.0, points = true)
            }
            ChartCard(R.string.height, "m", last?.let { Format.number(it.height, 2) }, nav.isEmpty()) {
                TimeChart(listOf(metric("m", North) { it.height }), start, now)
            }
        }
    }
}

/** 1 / 5 / 10 minutes, in the dark header: the chosen one white. */
@Composable
private fun WindowPicker(minutes: Int, onPick: (Int) -> Unit) {
    val options = listOf(1 to R.string.window_1, 5 to R.string.window_5, 10 to R.string.window_10)
    Row(Modifier.fillMaxWidth().selectableGroup()) {
        options.forEach { (m, label) ->
            val on = m == minutes
            Box(
                Modifier.weight(1f).heightIn(min = 40.dp)
                    .background(if (on) Color.White else Color.Transparent)
                    .border(1.5.dp, if (on) Color.White else C.LampRingOff)
                    .semantics { selected = on }
                    .clickable(role = Role.Tab) { onPick(m) },
                contentAlignment = Alignment.Center,
            ) {
                Text(stringResource(label), color = if (on) C.Asphalt else C.HeaderInk2, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun Group(@StringRes title: Int) {
    Text(stringResource(title), Modifier.padding(start = 16.dp, top = 4.dp), color = C.Muted, fontSize = 13.sp,
        fontWeight = FontWeight.Bold)
}

@Composable
private fun ChartCard(@StringRes title: Int, unit: String, now: String?, empty: Boolean, content: @Composable () -> Unit) {
    Column(Modifier.fillMaxWidth().background(C.Panel).padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text(stringResource(title), fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = C.Asphalt)
            Text(" $unit", fontSize = 14.sp, fontWeight = FontWeight.Medium, color = C.Muted)
            Spacer(Modifier.weight(1f))
            Text(now ?: "—", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = C.Asphalt, style = Num)
        }
        if (empty) EmptyChart(stringResource(R.string.no_data_window)) else content()
    }
}

/** Each lamp is a row; the times it was lit are filled, the rest light grey. Then the dashboard state. */
@Composable
private fun SignalHistory(segments: List<TimelineSegment>, start: Long, end: Long, minutes: Int) {
    val res = LocalResources.current
    Column(Modifier.fillMaxWidth().background(C.Panel).padding(horizontal = 16.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(stringResource(R.string.chart_signal_title), fontSize = 15.sp, fontWeight = FontWeight.Bold, color = C.Asphalt)
        Text(stringResource(R.string.chart_signal_hint), fontSize = 12.5.sp, color = C.Muted, lineHeight = 17.sp)
        Column(Modifier.padding(top = 4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            listOf(Kind.STOP to R.string.mast_stop, Kind.WAIT to R.string.mast_wait, Kind.GO to R.string.mast_go).forEach { (k, label) ->
                Lane(stringResource(label), start, end) {
                    merged(segments) { it.kind.name }.filter { it.first == k.name }.forEach { (_, s, e) -> fill(s, e, C.signal(k)) }
                }
            }
            Lane(stringResource(R.string.lane_state), start, end, background = Color.Transparent) {
                merged(segments) { it.state }.forEach { (state, s, e) -> fill(s, e, StateColors[state] ?: C.TabOff) }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Spacer(Modifier.width(54.dp))
                Text(stringResource(R.string.chart_minutes_ago, minutes), Modifier.weight(1f), fontSize = 12.sp, color = C.Muted, style = Num)
                Text(stringResource(R.string.chart_now), fontSize = 12.sp, color = C.Muted, style = Num)
            }
        }
        val shown = segments.map { it.state }.toSet()
        ChipRow {
            StateColors.filterKeys { it in shown }.forEach { (state, color) ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(12.dp, 10.dp).background(color))
                    Text(" " + Words.stateByName(res, state), fontSize = 12.5.sp, color = C.Text2)
                }
            }
        }
    }
}

private class LaneFill(val start: Long, val end: Long, val color: Color)

private class LaneBuilder {
    val fills = ArrayList<LaneFill>()
    fun fill(start: Long, end: Long, color: Color) {
        fills += LaneFill(start, end, color)
    }
}

@Composable
private fun Lane(label: String, start: Long, end: Long, background: Color = C.Empty, build: LaneBuilder.() -> Unit) {
    val fills = LaneBuilder().apply(build).fills
    Row(verticalAlignment = Alignment.CenterVertically) {
        Text(label, Modifier.width(54.dp), fontSize = 12.5.sp, color = C.Text2, maxLines = 1)
        Canvas(Modifier.weight(1f).height(16.dp)) {
            drawRect(background)
            val span = (end - start).coerceAtLeast(1).toFloat()
            for (f in fills) {
                if (f.end < start || f.start > end) continue
                val x0 = (f.start.coerceIn(start, end) - start) / span * size.width
                val x1 = maxOf((f.end.coerceIn(start, end) - start) / span * size.width, x0 + 1f)
                drawRect(f.color, Offset(x0, 0f), Size(x1 - x0, size.height))
            }
        }
    }
}
