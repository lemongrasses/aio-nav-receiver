// Small time-series charts drawn with Compose Canvas (no chart library), in the layout C style: only the
// minimum and maximum on the left, lines told apart by their dash as well as their colour, an area fill and a
// dashed limit line. Not interactive; the screen redraws them every 0.5 s.

package com.lemongrass.aionav.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.util.Locale
import kotlin.math.abs

/** `run` changes after a gap in the data, so the line breaks instead of bridging it. */
class ChartPoint(val time: Long, val value: Double, val run: Int = 0)

/** `dash`: on/off lengths in dp, null for a solid line. */
class ChartSeries(val name: String, val color: Color, val points: List<ChartPoint>, val dash: List<Float>? = null)

private val GUTTER = 30.dp
private val Guide = Color(0xFFE4E7EA)

private fun label(v: Double): String = when {
    abs(v) >= 100 || v == Math.floor(v) -> String.format(Locale.ROOT, "%.0f", v)
    abs(v) >= 10 -> String.format(Locale.ROOT, "%.1f", v)
    else -> String.format(Locale.ROOT, "%.2f", v)
}

@Composable
fun TimeChart(
    series: List<ChartSeries>,
    start: Long,
    end: Long,
    yDomain: ClosedFloatingPointRange<Double>? = null,
    points: Boolean = false,
    step: Boolean = false,
    area: Color? = null,
    limit: Double? = null,
    limitLabel: String? = null,
    height: Dp = 86.dp,
) {
    val measurer = rememberTextMeasurer()
    val labelStyle = TextStyle(fontSize = 11.5.sp, color = C.Muted, fontFeatureSettings = "tnum")
    Column {
        Canvas(Modifier.fillMaxWidth().height(height)) {
            val left = GUTTER.toPx()
            val top = 6.dp.toPx()
            val bottom = size.height - 4.dp.toPx()
            val w = size.width - left
            val visible = series.map { s -> s.points.filter { it.time in start..end } }
            val values = visible.flatten().map { it.value } + listOfNotNull(limit)
            var lo = yDomain?.start ?: (values.minOrNull() ?: 0.0)
            var hi = yDomain?.endInclusive ?: (values.maxOrNull() ?: 1.0)
            if (yDomain == null) {
                if (lo > 0 && lo <= hi * 0.6) lo = 0.0                  // start at 0 when that costs little
                if (hi - lo < 1e-9) {                                    // a flat line: give it some room
                    val pad = maxOf(abs(hi) * 0.002, 0.01)
                    lo -= pad
                    hi += pad
                }
            }
            fun x(t: Long) = left + (t - start).toFloat() / (end - start).coerceAtLeast(1) * w
            fun y(v: Double) = (bottom - (v - lo) / (hi - lo) * (bottom - top)).toFloat()

            drawLine(Guide, Offset(left, top), Offset(size.width, top), 1f)
            drawLine(Guide, Offset(left, bottom), Offset(size.width, bottom), 1f)
            drawText(measurer.measure(label(hi), labelStyle), topLeft = Offset(0f, top - 7.dp.toPx()))
            val minText = measurer.measure(label(lo), labelStyle)
            drawText(minText, topLeft = Offset(0f, bottom - minText.size.height + 3.dp.toPx()))

            series.forEachIndexed { i, s ->
                val pts = visible[i]
                if (points) {
                    pts.forEach { drawCircle(s.color, 1.8.dp.toPx(), Offset(x(it.time), y(it.value))) }
                    return@forEachIndexed
                }
                for (run in pts.groupConsecutiveBy { it.run }) {
                    val line = Path()
                    run.forEachIndexed { k, p ->
                        val px = x(p.time)
                        val py = y(p.value)
                        if (k == 0) line.moveTo(px, py)
                        else {
                            if (step) line.lineTo(px, y(run[k - 1].value))
                            line.lineTo(px, py)
                        }
                    }
                    if (area != null && run.size > 1) {
                        val base = y(maxOf(lo, 0.0))
                        drawPath(Path().apply {
                            addPath(line)
                            lineTo(x(run.last().time), base)
                            lineTo(x(run.first().time), base)
                            close()
                        }, area)
                    }
                    if (run.size == 1) drawCircle(s.color, 2.dp.toPx(), Offset(x(run[0].time), y(run[0].value)))
                    drawPath(line, s.color, style = Stroke(2.2.dp.toPx(), join = StrokeJoin.Round,
                        pathEffect = s.dash?.let { d -> PathEffect.dashPathEffect(d.map { it.dp.toPx() }.toFloatArray()) }))
                }
            }

            if (limit != null) {
                val ly = y(limit)
                drawLine(C.Stop, Offset(left, ly), Offset(size.width, ly), 1.8.dp.toPx(),
                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 4.dp.toPx())))
                limitLabel?.let {
                    val t = measurer.measure(it, TextStyle(fontSize = 11.5.sp, color = C.Stop, fontWeight = FontWeight.Bold))
                    val below = ly + 3.dp.toPx()
                    drawText(t, topLeft = Offset(size.width - t.size.width, if (below + t.size.height < bottom) below else ly - t.size.height - 2.dp.toPx()))
                }
            }
        }
        if (series.size > 1) LineLegend(series)
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

/** The series by their line, so the dash says which is which without colour. */
@Composable
private fun LineLegend(series: List<ChartSeries>) {
    ChipRow {
        series.forEach { s ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Canvas(Modifier.size(22.dp, 6.dp)) {
                    drawLine(s.color, Offset(1f, size.height / 2), Offset(size.width - 1f, size.height / 2), 2.5.dp.toPx(),
                        StrokeCap.Butt, s.dash?.let { d -> PathEffect.dashPathEffect(d.map { it.dp.toPx() }.toFloatArray()) })
                }
                Text(" ${s.name}", fontSize = 12.5.sp, color = C.Text2)
            }
        }
    }
}

@Composable
fun EmptyChart(text: String, height: Dp = 86.dp) {
    Box(Modifier.fillMaxWidth().height(height), contentAlignment = Alignment.Center) {
        Text(text, fontSize = 14.sp, color = C.Muted)
    }
}
