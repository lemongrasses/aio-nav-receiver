// The vehicle's recent track (last 10 minutes) drawn on a Compose Canvas in local east/north metres, so no
// map tiles or API key are needed: green where the gate said usable, red where blocked, a heading arrow,
// a grid and a scale bar. North is up. Drag or pinch to look around; "Follow vehicle" fits it again.

package com.lemongrass.aionav.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
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
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.rotate
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontFamily
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
fun TrackScreen(samples: List<NavSample>, snapshot: MonitorSnapshot) {
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
    val gridColor = MaterialTheme.colorScheme.outlineVariant
    val textColor = MaterialTheme.colorScheme.onSurfaceVariant
    val usable = snapshot.verdict.usable

    Box(Modifier.fillMaxSize()) {
        Canvas(
            Modifier.fillMaxSize()
                .background(MaterialTheme.colorScheme.surfaceContainerLowest)
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

            // Grid at the scale bar's spacing.
            val bar = TrackMath.niceLength(w * 0.3 * mpp)
            val left = cx - w / 2 * mpp
            val bottom = cy - h / 2 * mpp
            var gx = floor(left / bar) * bar
            while (gx <= cx + w / 2 * mpp) {
                drawLine(gridColor, Offset(sx(gx), 0f), Offset(sx(gx), h), 1f)
                gx += bar
            }
            var gy = floor(bottom / bar) * bar
            while (gy <= cy + h / 2 * mpp) {
                drawLine(gridColor, Offset(0f, sy(gy)), Offset(w, sy(gy)), 1f)
                gy += bar
            }

            // Track, one segment per pair of samples, coloured by the verdict at the later one.
            for (i in 1 until samples.size) {
                if (samples[i].run != samples[i - 1].run) continue
                drawLine(if (samples[i].usable) UsableGreen else BlockedRed,
                    Offset(sx(xs[i - 1]), sy(ys[i - 1])), Offset(sx(xs[i]), sy(ys[i])), 4.dp.toPx(), StrokeCap.Round)
            }

            // Vehicle: an arrow pointing along the heading.
            if (current != null && vx != null && vy != null) {
                val at = Offset(sx(vx), sy(vy))
                drawCircle(Color.White, 16.dp.toPx(), at)
                drawCircle(if (usable) UsableGreen else BlockedRed, 14.dp.toPx(), at)
                rotate(current.heading360.toFloat(), at) {
                    val s = 8.dp.toPx()
                    val arrow = Path().apply {
                        moveTo(at.x, at.y - s)
                        lineTo(at.x + s * 0.7f, at.y + s * 0.8f)
                        lineTo(at.x, at.y + s * 0.35f)
                        lineTo(at.x - s * 0.7f, at.y + s * 0.8f)
                        close()
                    }
                    drawPath(arrow, Color.White)
                }
            }

            // Scale bar (bottom left) and north (top right).
            val style = TextStyle(fontSize = 11.sp, color = textColor, fontFamily = FontFamily.Monospace)
            val barPx = (bar / mpp).toFloat()
            val y0 = h - 76.dp.toPx()                // above the position pill
            val x0 = 16.dp.toPx()
            drawLine(textColor, Offset(x0, y0), Offset(x0 + barPx, y0), 3f)
            drawLine(textColor, Offset(x0, y0 - 6), Offset(x0, y0 + 6), 3f)
            drawLine(textColor, Offset(x0 + barPx, y0 - 6), Offset(x0 + barPx, y0 + 6), 3f)
            val barText = if (bar >= 1000) "${Format.number(bar / 1000, if (bar % 1000 == 0.0) 0 else 1)} km"
            else "${Format.number(bar, if (bar >= 1) 0 else 2)} m"
            drawText(measurer.measure(barText, style), topLeft = Offset(x0, y0 - 22.dp.toPx()))
            val nx = w - 28.dp.toPx()
            val ny = 64.dp.toPx()
            drawLine(textColor, Offset(nx, ny + 14.dp.toPx()), Offset(nx, ny - 10.dp.toPx()), 3f)
            drawPath(Path().apply {
                moveTo(nx, ny - 16.dp.toPx()); lineTo(nx - 6.dp.toPx(), ny - 6.dp.toPx()); lineTo(nx + 6.dp.toPx(), ny - 6.dp.toPx()); close()
            }, textColor)
            val n = measurer.measure("N", style)
            drawText(n, topLeft = Offset(nx - n.size.width / 2f, ny + 16.dp.toPx()))
        }

        FilterChip(
            selected = follow,
            onClick = { follow = !follow },
            label = { Text(stringResource(R.string.follow_vehicle)) },
            leadingIcon = { Icon(Icons.Filled.LocationOn, null) },
            modifier = Modifier.align(Alignment.TopStart).padding(12.dp),
        )

        Column(Modifier.align(Alignment.BottomCenter).padding(bottom = 12.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            val pill = Modifier.background(MaterialTheme.colorScheme.surfaceContainerHigh.copy(alpha = 0.92f), RoundedCornerShape(50))
                .padding(horizontal = 14.dp, vertical = 8.dp)
            if (current != null) {
                Row(pill, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    val style = MaterialTheme.typography.bodySmall
                    Text(Format.number(current.lat, 6) + ", " + Format.number(current.lon, 6), style = style, fontFamily = FontFamily.Monospace)
                    Text(Format.number(current.heading360, 0, "°"), style = style, fontFamily = FontFamily.Monospace)
                    Text(Format.number(current.groundSpeed * 3.6, 1, "km/h"), style = style, fontFamily = FontFamily.Monospace)
                }
            } else {
                Text(stringResource(R.string.no_position), pill, style = MaterialTheme.typography.bodySmall)
            }
            if (!follow) {
                Text(stringResource(R.string.track_hint), style = MaterialTheme.typography.labelSmall, color = textColor)
            }
        }
    }
}
