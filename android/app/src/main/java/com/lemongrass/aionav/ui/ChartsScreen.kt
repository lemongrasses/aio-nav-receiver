// Live charts over the last 1, 5 or 10 minutes: when and why the gate changed, the navigation quality
// and the vehicle's motion (the iOS ChartsView).

package com.lemongrass.aionav.ui

import androidx.annotation.StringRes
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.lemongrass.aionav.R
import com.lemongrass.aionav.monitor.History
import com.lemongrass.aionav.monitor.MonitorStore
import com.lemongrass.aionav.monitor.NavSample
import com.lemongrass.aionav.monitor.TimelineSegment
import kotlinx.coroutines.delay

private val SeriesColors = listOf(Color(0xFF1E88E5), Color(0xFF43A047), Color(0xFFFB8C00))

/** Colours of the status timeline: the gate lane and the dashboard state lane. */
val StateColors = linkedMapOf(
    "USABLE" to UsableGreen, "BLOCKED" to BlockedRed, "NO_STATUS" to Color(0xFF9E9E9E),
    "BOOTING" to Color(0xFF3F51B5), "CHECKING" to Color(0xFF8E24AA), "NAV_STARTING" to Color(0xFF1E88E5),
    "KEEP_STILL" to Color(0xFF00ACC1), "MOVE_STRAIGHT" to Color(0xFF00897B), "REFINING" to Color(0xFF66BB6A),
    "READY" to UsableGreen, "DEGRADED" to Color(0xFFFDD835), "FAULT" to BlockedRed, "MAINTENANCE" to Color(0xFF795548),
)

/** Joins neighbouring segments with the same key into one bar. */
fun merged(segments: List<TimelineSegment>, key: (TimelineSegment) -> String): List<LaneRun> {
    val runs = ArrayList<LaneRun>()
    for (s in segments) {
        val k = key(s)
        val last = runs.lastOrNull()
        if (last != null && last.key == k) runs[runs.size - 1] = LaneRun(k, last.start, s.end)
        else runs += LaneRun(k, s.start, s.end)
    }
    return runs
}

@Composable
fun ChartsScreen(history: History, navMaxAge: Double) {
    var minutes by rememberSaveable { mutableIntStateOf(5) }
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

    fun metric(name: String, color: Color, value: (NavSample) -> Double) =
        ChartSeries(name, color, nav.map { ChartPoint(it.time, value(it), it.run) })

    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        val options = listOf(1 to R.string.window_1, 5 to R.string.window_5, 10 to R.string.window_10)
        SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
            options.forEachIndexed { i, (m, label) ->
                SegmentedButton(selected = minutes == m, onClick = { minutes = m },
                    shape = SegmentedButtonDefaults.itemShape(i, options.size)) { Text(stringResource(label)) }
            }
        }

        val visible = history.timeline.filter { it.end >= start }
        Card(stringResource(R.string.status_timeline)) {
            LaneChart(
                listOf(
                    stringResource(R.string.lane_gate) to merged(visible) { if (it.usable) "USABLE" else "BLOCKED" },
                    stringResource(R.string.lane_state) to merged(visible) { it.state },
                ),
                colors = { StateColors[it] ?: Color.Gray }, start = start, end = now,
            )
            val shown = visible.map { it.state }.toSet() + setOf("USABLE", "BLOCKED")
            Legend(StateColors.filterKeys { it in shown }.map { it.key to it.value })
        }

        SectionTitle(R.string.section_quality)
        ChartCard(R.string.position_sigma, "m", nav.isEmpty()) {
            TimeChart(listOf(metric("N", SeriesColors[0]) { it.sigmaN }, metric("E", SeriesColors[1]) { it.sigmaE },
                metric("D", SeriesColors[2]) { it.sigmaD }), start, now)
        }
        ChartCard(R.string.heading_sigma, "°", nav.isEmpty()) {
            TimeChart(listOf(metric("σ", SeriesColors[0]) { it.sigmaHeading }), start, now)
        }
        val ages = link.filter { it.navAgeMs != null }
        ChartCard(R.string.data_age_04, "ms", ages.isEmpty()) {
            TimeChart(listOf(ChartSeries("ms", WarningOrange, ages.map { ChartPoint(it.time, it.navAgeMs!!) })),
                start, now, area = true, limit = navMaxAge * 1000, limitLabel = stringResource(R.string.limit))
        }
        ChartCard(R.string.receive_rate, "Hz", link.isEmpty()) {
            TimeChart(listOf(ChartSeries("Hz", InfoBlue, link.map { ChartPoint(it.time, it.rateHz) })), start, now, step = true)
        }

        SectionTitle(R.string.section_motion)
        ChartCard(R.string.speed, "m/s", nav.isEmpty()) {
            TimeChart(listOf(metric("m/s", SeriesColors[0]) { it.speed }), start, now)
        }
        ChartCard(R.string.heading, "°", nav.isEmpty()) {
            TimeChart(listOf(metric("°", SeriesColors[0]) { it.heading }), start, now, yDomain = 0.0..360.0,
                yTicks = listOf(0.0, 90.0, 180.0, 270.0, 360.0), points = true)
        }
        ChartCard(R.string.height, "m", nav.isEmpty()) {
            TimeChart(listOf(metric("m", SeriesColors[0]) { it.height }), start, now)
        }
    }
}

@Composable
private fun SectionTitle(@StringRes text: Int) {
    Text(stringResource(text), Modifier.padding(top = 8.dp), style = MaterialTheme.typography.titleLarge,
        fontWeight = FontWeight.Bold)
}

@Composable
private fun ChartCard(@StringRes title: Int, unit: String, empty: Boolean, content: @Composable () -> Unit) {
    Card(stringResource(title) + "  ($unit)") {
        if (empty) EmptyChart(stringResource(R.string.no_data_window)) else content()
    }
}
