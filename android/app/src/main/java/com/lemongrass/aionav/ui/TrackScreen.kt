// The vehicle's recent track (last 10 minutes) drawn on a Compose Canvas in local east/north metres, so no
// map tiles or API key are needed (layout C, docs/UI-PHONE-C.zh-TW.md 4.3): a wide green line where the gate said
// usable, a thin dashed grey one where blocked, the vehicle in the signal colour, graph paper and a scale bar.
// North is up. Drag or pinch to look around; "Follow vehicle" fits it again.

package com.lemongrass.aionav.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.lemongrass.aionav.R
import com.lemongrass.aionav.core.TrackMath
import com.lemongrass.aionav.monitor.MonitorSnapshot
import com.lemongrass.aionav.monitor.NavSample
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.min

@Composable
fun TrackScreen(samples: List<NavSample>, snapshot: MonitorSnapshot, kind: Kind) {
    var follow by remember { mutableStateOf(true) }
    var size by remember { mutableStateOf(IntSize.Zero) }
    // Everything is drawn in metres east / north of a fixed reference point, so a panned view stays put
    // while the vehicle moves. It is the first position seen (again after a jump of more than 50 km).
    var ref by remember { mutableStateOf<Pair<Double, Double>?>(null) }
    // The view: its centre in metres from the reference point, and metres per pixel.
    var cx by remember { mutableDoubleStateOf(0.0) }
    var cy by remember { mutableDoubleStateOf(0.0) }
    var mpp by remember { mutableDoubleStateOf(1.0) }

    val current = snapshot.nav?.takeIf { (snapshot.navAge ?: Double.POSITIVE_INFINITY) < 1.0 && it.isFinite }
    val newest = current?.let { it.lat to it.lon } ?: samples.lastOrNull()?.let { it.lat to it.lon }
    val ky = Math.toRadians(1.0) * TrackMath.EARTH_R
    val r = ref
    if (newest != null && (r == null || abs(newest.first - r.first) * ky > 50_000 ||
            abs(newest.second - r.second) * ky * cos(Math.toRadians(r.first)) > 50_000)) {
        ref = newest
    }
    val (lat0, lon0) = ref ?: (0.0 to 0.0)
    val kx = ky * cos(Math.toRadians(lat0))
    val xs = samples.map { (it.lon - lon0) * kx }
    val ys = samples.map { (it.lat - lat0) * ky }
    val vx = current?.let { (it.lon - lon0) * kx }
    val vy = current?.let { (it.lat - lat0) * ky }

    if (follow && size.width > 0 && newest != null) {
        val allX = xs + listOfNotNull(vx)
        val allY = ys + listOfNotNull(vy)
        cx = (allX.max() + allX.min()) / 2
        cy = (allY.max() + allY.min()) / 2
        val span = maxOf(allX.max() - allX.min(), allY.max() - allY.min(), TrackMath.MIN_SPAN_M)
        mpp = span * 1.25 / min(size.width, size.height)
    }

    val measurer = rememberTextMeasurer()

    Column(Modifier.fillMaxSize()) {
        PageHeader(stringResource(R.string.tab_track), kind)
        Box(Modifier.fillMaxWidth().weight(1f)) {
            Canvas(
                Modifier.fillMaxSize()
                    .background(C.Panel)
                    .onSizeChanged { size = it }
                    .pointerInput(Unit) {
                        detectTransformGestures { _, pan, zoom, _ ->
                            follow = false
                            mpp = (mpp / zoom).coerceIn(0.01, 500.0)
                            cx -= pan.x * mpp
                            cy += pan.y * mpp
                        }
                    },
            ) {
                val w = this.size.width
                val h = this.size.height
                fun sx(x: Double) = (w / 2 + (x - cx) / mpp).toFloat()
                fun sy(y: Double) = (h / 2 - (y - cy) / mpp).toFloat()

                // Graph paper at the scale bar's spacing.
                val bar = TrackMath.niceLength(w * 0.3 * mpp)
                val left = cx - w / 2 * mpp
                val bottom = cy - h / 2 * mpp
                var gx = floor(left / bar) * bar
                while (gx <= cx + w / 2 * mpp) {
                    drawLine(C.Line, Offset(sx(gx), 0f), Offset(sx(gx), h), 1f)
                    gx += bar
                }
                var gy = floor(bottom / bar) * bar
                while (gy <= cy + h / 2 * mpp) {
                    drawLine(C.Line, Offset(0f, sy(gy)), Offset(w, sy(gy)), 1f)
                    gy += bar
                }

                // The track: usable a wide green line, blocked a thin grey dashed one, so it reads without colour.
                // Each pair of samples takes the verdict of the later one; runs of the same kind are one path.
                var i = 1
                while (i < samples.size) {
                    if (samples[i].run != samples[i - 1].run) { i++; continue }
                    val usable = samples[i].usable
                    val path = Path().apply { moveTo(sx(xs[i - 1]), sy(ys[i - 1])) }
                    while (i < samples.size && samples[i].run == samples[i - 1].run && samples[i].usable == usable) {
                        path.lineTo(sx(xs[i]), sy(ys[i]))
                        i++
                    }
                    if (usable) drawPath(path, C.Go, style = Stroke(7.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
                    else drawPath(path, C.BlockedTrack, style = Stroke(4.dp.toPx(), cap = StrokeCap.Butt, join = StrokeJoin.Round,
                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(9.dp.toPx(), 8.dp.toPx()))))
                }

                // The vehicle: a dark disc with the signal colour, and an arrow along the heading.
                if (current != null && vx != null && vy != null) {
                    val at = Offset(sx(vx), sy(vy))
                    drawCircle(C.Asphalt, 18.dp.toPx(), at)
                    drawCircle(C.signal(kind), 13.dp.toPx(), at)
                    rotate(current.heading360.toFloat(), at) {
                        val a = 8.dp.toPx()
                        drawPath(Path().apply {
                            moveTo(at.x, at.y - a)
                            lineTo(at.x + a * 0.7f, at.y + a * 0.8f)
                            lineTo(at.x, at.y + a * 0.35f)
                            lineTo(at.x - a * 0.7f, at.y + a * 0.8f)
                            close()
                        }, C.onSignal(kind))
                    }
                }

                // North (right, under the follow button) and the scale bar (left, above the position bar).
                val ink = C.Asphalt
                val nx = w - 26.dp.toPx()
                val ny = 96.dp.toPx()
                drawLine(ink, Offset(nx, ny + 12.dp.toPx()), Offset(nx, ny - 14.dp.toPx()), 3.dp.toPx(), StrokeCap.Round)
                drawPath(Path().apply {
                    moveTo(nx - 8.dp.toPx(), ny - 4.dp.toPx()); lineTo(nx, ny - 14.dp.toPx()); lineTo(nx + 8.dp.toPx(), ny - 4.dp.toPx())
                }, ink, style = Stroke(3.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
                val nText = measurer.measure("N", TextStyle(fontSize = 15.sp, fontWeight = FontWeight.Bold, color = ink))
                drawText(nText, topLeft = Offset(nx - nText.size.width / 2f, ny + 14.dp.toPx()))
                val barPx = (bar / mpp).toFloat()
                val y0 = h - 104.dp.toPx()
                val x0 = 20.dp.toPx()
                val tick = 8.dp.toPx()
                drawLine(ink, Offset(x0, y0), Offset(x0 + barPx, y0), 3.dp.toPx())
                drawLine(ink, Offset(x0, y0 - tick), Offset(x0, y0 + tick), 3.dp.toPx())
                drawLine(ink, Offset(x0 + barPx, y0 - tick), Offset(x0 + barPx, y0 + tick), 3.dp.toPx())
                val barText = if (bar >= 1000) "${Format.number(bar / 1000, if (bar % 1000 == 0.0) 0 else 1)} km"
                else "${Format.number(bar, if (bar >= 1) 0 else 2)} m"
                val t = measurer.measure(barText, TextStyle(fontSize = 15.sp, fontWeight = FontWeight.SemiBold, color = ink,
                    fontFeatureSettings = "tnum"))
                drawText(t, topLeft = Offset(x0 + barPx + 8.dp.toPx(), y0 - t.size.height / 2f))
            }

            Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.Top) {
                Legend()
                Spacer(Modifier.weight(1f))
                FollowButton(follow) { follow = !follow }
            }

            Column(Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(12.dp).background(C.Asphalt)
                .padding(horizontal = 14.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                if (current != null) {
                    Row {
                        val style = TextStyle(fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = Color.White, fontFeatureSettings = "tnum")
                        Text(Format.number(current.lat, 6) + ", " + Format.number(current.lon, 6), Modifier.weight(1f), style = style, maxLines = 1)
                        Text(Format.number(current.heading360, 0, "°"), Modifier.padding(horizontal = 10.dp), style = style)
                        Text(Format.number(current.groundSpeed * 3.6, 1, "km/h"), style = style)
                    }
                } else {
                    Text(stringResource(R.string.no_position), color = Color.White, fontSize = 15.sp)
                }
                if (!follow) Text(stringResource(R.string.track_hint), color = C.HeaderInk2, fontSize = 12.5.sp)
            }
        }
    }
}

/** Usable: wide solid green. Blocked: thin dashed grey. */
@Composable
private fun Legend() {
    Column(
        Modifier.background(Color.White.copy(alpha = 0.94f)).border(1.dp, C.Line).padding(horizontal = 10.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        listOf(true to R.string.track_usable, false to R.string.track_blocked).forEach { (usable, label) ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Canvas(Modifier.size(24.dp, 8.dp)) {
                    val y = size.height / 2
                    if (usable) drawLine(C.Go, Offset(2.dp.toPx(), y), Offset(size.width - 2.dp.toPx(), y), 5.dp.toPx(), StrokeCap.Round)
                    else drawLine(C.BlockedTrack, Offset(2.dp.toPx(), y), Offset(size.width - 2.dp.toPx(), y), 3.dp.toPx(),
                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(5.dp.toPx(), 4.dp.toPx())))
                }
                Text(" " + stringResource(label), fontSize = 13.sp, color = C.Text2)
            }
        }
    }
}

/** On: dark with white text. Off: white with a dark outline. */
@Composable
private fun FollowButton(on: Boolean, onClick: () -> Unit) {
    Row(
        Modifier.heightIn(min = 44.dp).background(if (on) C.Asphalt else Color.White, RoundedCornerShape(6.dp))
            .border(2.dp, C.Asphalt, RoundedCornerShape(6.dp))
            .toggleable(value = on, role = Role.Switch, onValueChange = { onClick() })
            .padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        val ink = if (on) Color.White else C.Asphalt
        Canvas(Modifier.size(18.dp)) {
            drawCircle(ink, 6.5.dp.toPx(), style = Stroke(2.dp.toPx()))
            drawCircle(ink, 2.dp.toPx())
        }
        Text(stringResource(R.string.follow_vehicle), color = ink, fontSize = 15.sp, fontWeight = FontWeight.Bold)
    }
}
