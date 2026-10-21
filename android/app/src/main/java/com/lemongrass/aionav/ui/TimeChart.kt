// Small time-series charts drawn with Compose Canvas (no chart library): lines broken at gaps, points,
// step lines, an area fill and a dashed limit line, plus the two-lane status timeline.

package com.lemongrass.aionav.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextMeasurer
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.log10
import kotlin.math.pow

/** `run` changes after a gap in the data, so the line breaks instead of bridging it. */
class ChartPoint(val time: Long, val value: Double, val run: Int = 0)

class ChartSeries(val name: String, val color: Color, val points: List<ChartPoint>)

private val AXIS_LEFT = 44.dp
private val AXIS_BOTTOM = 18.dp

/** Tick spacing for the time axis, by window length. */
private fun timeStep(spanMs: Long): Long = when {
    spanMs <= 2 * 60_000L -> 15_000L
    spanMs <= 6 * 60_000L -> 60_000L
    else -> 120_000L
}

/** About `count` round values covering lo..hi. */
private fun niceTicks(lo: Double, hi: Double, count: Int = 4): List<Double> {
    val span = (hi - lo).takeIf { it > 0 } ?: 1.0
    val raw = span / count
    val mag = 10.0.pow(floor(log10(raw)))
    val step = listOf(1.0, 2.0, 2.5, 5.0, 10.0).map { it * mag }.first { it >= raw }
    val out = ArrayList<Double>()
    var v = ceil(lo / step) * step
    while (v <= hi + step * 1e-6) {
        out += if (abs(v) < step * 1e-9) 0.0 else v
        v += step
    }
    return out
}

private fun tickLabel(v: Double): String =
    if (v == floor(v) && abs(v) < 1e6) v.toLong().toString() else String.format(Locale.ROOT, "%.2g", v)

@Composable
fun TimeChart(
    series: List<ChartSeries>,
    start: Long,
    end: Long,
    modifier: Modifier = Modifier,
    yDomain: ClosedFloatingPointRange<Double>? = null,
    yTicks: List<Double>? = null,
    points: Boolean = false,
    step: Boolean = false,
    area: Boolean = false,
    limit: Double? = null,
    limitLabel: String? = null,
    height: Dp = 150.dp,
) {
    val measurer = rememberTextMeasurer()
    val axisColor = MaterialTheme.colorScheme.onSurfaceVariant
    val gridColor = MaterialTheme.colorScheme.outlineVariant
    val labelStyle = TextStyle(fontSize = 10.sp, color = axisColor, fontFamily = FontFamily.Monospace)
    Column(modifier) {
        Canvas(Modifier.fillMaxWidth().height(height)) {
            val left = AXIS_LEFT.toPx()
            val bottom = size.height - AXIS_BOTTOM.toPx()
            val w = size.width - left
            val visible = series.map { s -> s.points.filter { it.time in start..end } }
            val values = visible.flatten().map { it.value } + listOfNotNull(limit)
            var lo = yDomain?.start ?: (values.minOrNull() ?: 0.0)
            var hi = yDomain?.endInclusive ?: (values.maxOrNull() ?: 1.0)
            if (yDomain == null) {
                if (lo > 0 && lo <= hi * 0.6) lo = 0.0          // start at 0 when that costs little
                val pad = ((hi - lo).takeIf { it > 0 } ?: maxOf(abs(hi) * 0.1, 1.0)) * 0.08
                lo -= if (lo == 0.0) 0.0 else pad
                hi += pad
            }
            val ticks = yTicks ?: niceTicks(lo, hi)
            if (yDomain == null && ticks.isNotEmpty()) {
                lo = minOf(lo, ticks.first())
                hi = maxOf(hi, ticks.last())
            }
            fun x(t: Long) = left + (t - start).toFloat() / (end - start).coerceAtLeast(1) * w
            fun y(v: Double) = (bottom - (v - lo) / (hi - lo).coerceAtLeast(1e-12) * bottom).toFloat()

            for (v in ticks) {
                val yy = y(v)
                drawLine(gridColor, Offset(left, yy), Offset(size.width, yy), 1f)
                label(measurer, tickLabel(v), labelStyle, Offset(left - 4.dp.toPx(), yy), alignRight = true)
            }
            timeTicks(measurer, labelStyle, gridColor, start, end, left, bottom) { x(it) }

            if (limit != null) {
                val yy = y(limit)
                drawLine(BlockedRed, Offset(left, yy), Offset(size.width, yy), 1.5f,
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 6f)))
                limitLabel?.let {
                    label(measurer, it, labelStyle.copy(color = BlockedRed), Offset(left + 4.dp.toPx(), yy - 7.dp.toPx()))
                }
            }

            series.forEachIndexed { i, s ->
                val pts = visible[i]
                if (points) {
                    pts.forEach { drawCircle(s.color, 2.dp.toPx(), Offset(x(it.time), y(it.value))) }
                    return@forEachIndexed
                }
                for (runPoints in pts.groupConsecutiveBy { it.run }) {
                    val line = Path()
                    runPoints.forEachIndexed { k, p ->
                        val px = x(p.time)
                        val py = y(p.value)
                        if (k == 0) line.moveTo(px, py)
                        else {
                            if (step) line.lineTo(px, y(runPoints[k - 1].value))
                            line.lineTo(px, py)
                        }
                    }
                    if (area && runPoints.size > 1) {
                        val fill = Path().apply {
                            addPath(line)
                            lineTo(x(runPoints.last().time), y(maxOf(lo, 0.0)))
                            lineTo(x(runPoints.first().time), y(maxOf(lo, 0.0)))
                            close()
                        }
                        drawPath(fill, s.color.copy(alpha = 0.25f))
                    }
                    if (runPoints.size == 1) drawCircle(s.color, 2.dp.toPx(), Offset(x(runPoints[0].time), y(runPoints[0].value)))
                    drawPath(line, s.color, style = Stroke(2.dp.toPx()))
                }
            }
        }
        if (series.size > 1) Legend(series.map { it.name to it.color })
    }
}

/** Splits into runs of neighbouring elements with the same key. */
private fun <T, K> List<T>.groupConsecutiveBy(key: (T) -> K): List<List<T>> {
    val out = ArrayList<List<T>>()
    var cur = ArrayList<T>()
    for (e in this) {
        if (cur.isNotEmpty() && key(cur.last()) != key(e)) {
            out += cur
            cur = ArrayList()
        }
        cur += e
    }
    if (cur.isNotEmpty()) out += cur
    return out
}

private fun DrawScope.label(measurer: TextMeasurer, text: String, style: TextStyle, at: Offset, alignRight: Boolean = false,
                            center: Boolean = false) {
    val layout = measurer.measure(text, style)
    val dx = when {
        alignRight -> -layout.size.width.toFloat()
        center -> -layout.size.width / 2f
        else -> 0f
    }
    val dy = if (center) 0f else -layout.size.height / 2f
    drawText(layout, topLeft = Offset(at.x + dx, at.y + dy))
}

private fun DrawScope.timeTicks(measurer: TextMeasurer, style: TextStyle, grid: Color, start: Long, end: Long,
                                left: Float, bottom: Float, x: (Long) -> Float) {
    val stepMs = timeStep(end - start)
    val fmt = SimpleDateFormat(if (stepMs < 60_000L) "HH:mm:ss" else "HH:mm", Locale.ROOT)
    var t = (start / stepMs + 1) * stepMs
    while (t <= end) {
        val xx = x(t)
        drawLine(grid, Offset(xx, 0f), Offset(xx, bottom), 1f)
        val layout = measurer.measure(fmt.format(Date(t)), style)
        val lx = (xx - layout.size.width / 2f).coerceIn(left, size.width - layout.size.width)
        drawText(layout, topLeft = Offset(lx, bottom + 3.dp.toPx()))
        t += stepMs
    }
    drawLine(grid, Offset(left, bottom), Offset(size.width, bottom), 1f)
}

@Composable
fun Legend(items: List<Pair<String, Color>>) {
    ChipRow {
        items.forEach { (name, color) ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(10.dp).background(color, RoundedCornerShape(2.dp)))
                Text(" $name", style = MaterialTheme.typography.labelSmall)
            }
        }
    }
}

/** One coloured bar on a timeline lane. */
class LaneRun(val key: String, val start: Long, val end: Long)

/** Lanes of coloured bars over the same time axis (gate verdict, dashboard state). */
@Composable
fun LaneChart(lanes: List<Pair<String, List<LaneRun>>>, colors: (String) -> Color, start: Long, end: Long) {
    val measurer = rememberTextMeasurer()
    val axisColor = MaterialTheme.colorScheme.onSurfaceVariant
    val gridColor = MaterialTheme.colorScheme.outlineVariant
    val labelStyle = TextStyle(fontSize = 10.sp, color = axisColor)
    Canvas(Modifier.fillMaxWidth().height((28 * lanes.size + 18).dp)) {
        val left = AXIS_LEFT.toPx()
        val bottom = size.height - AXIS_BOTTOM.toPx()
        val laneH = bottom / lanes.size
        fun x(t: Long) = left + (t.coerceIn(start, end) - start).toFloat() / (end - start).coerceAtLeast(1) * (size.width - left)
        timeTicks(measurer, labelStyle.copy(fontFamily = FontFamily.Monospace), gridColor, start, end, left, bottom) { x(it) }
        lanes.forEachIndexed { i, (name, runs) ->
            val top = i * laneH + laneH * 0.15f
            label(measurer, name, labelStyle, Offset(left - 4.dp.toPx(), top + laneH * 0.35f), alignRight = true)
            for (r in runs) {
                if (r.end < start || r.start > end) continue
                val x0 = x(r.start)
                val x1 = maxOf(x(r.end), x0 + 1f)
                drawRect(colors(r.key), Offset(x0, top), Size(x1 - x0, laneH * 0.7f))
            }
        }
    }
}

@Composable
fun EmptyChart(text: String, height: Dp = 150.dp) {
    Box(Modifier.fillMaxWidth().height(height), contentAlignment = Alignment.Center) {
        Text(text, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

