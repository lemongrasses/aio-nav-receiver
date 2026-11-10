// The status tab, layout C without scrolling (docs/UI-PHONE-C.zh-TW.md 4.1): ① the verdict band with the mast,
// ② the one instruction, ③ the alignment route, ④ the two packet streams, ⑤ three rows of detail that open one at a
// time, ⑥ where it listens. Collapsed, a 390×844 phone shows it all; the column still scrolls for small phones,
// large text and open rows. Every value of the earlier status tab is in the open rows.

package com.lemongrass.aionav.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.lemongrass.aionav.R
import com.lemongrass.aionav.core.Aio
import com.lemongrass.aionav.monitor.ListenFailure
import com.lemongrass.aionav.monitor.MonitorSettings
import com.lemongrass.aionav.monitor.MonitorSnapshot
import kotlinx.coroutines.delay
import java.util.Locale

@Composable
fun StatusScreen(
    snapshot: MonitorSnapshot,
    settings: MonitorSettings,
    listening: Boolean,
    listenError: ListenFailure?,
    address: Pair<String, String>?,
    onStart: () -> Unit,
) {
    val band = Presentation.band(snapshot)
    val nothing = Presentation.nothingReceived(snapshot)
    Column(Modifier.fillMaxSize().background(C.Panel).verticalScroll(rememberScrollState())) {
        VerdictBand(snapshot, band)
        val guide = Presentation.guide(snapshot)
        if (listenError != null || guide != null || !nothing) Column(Modifier.padding(horizontal = 16.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (listenError != null) {
                BindAlert(listenError)
                InstructionPlate(stringResource(R.string.bind_plate), null, danger = false, person = false)
            } else {
                guide?.let { Guidance(it) }
            }
            if (!nothing) AlignmentRoute(snapshot)
        }
        Streams(snapshot)
        Details(snapshot)
        ListeningInfo(settings, listening, address, onStart)
    }
}

// ----------------------------------------------------------------------------------- ① the verdict

@Composable
private fun VerdictBand(s: MonitorSnapshot, band: Presentation.Band) {
    val kind = band.kind
    val ink = C.onSignal(kind)
    // Usable just ended: the lit lamp blinks three times so a glance from the vehicle catches it.
    var dim by remember { mutableStateOf(false) }
    var flashing by remember { mutableStateOf(false) }
    var previous by remember { mutableStateOf(kind) }
    val still = reduceMotion()
    LaunchedEffect(kind) {
        if (previous == Kind.GO && kind != Kind.GO && !still) {
            flashing = true
            repeat(3) {
                dim = true; delay(160)
                dim = false; delay(160)
            }
            flashing = false
        }
        previous = kind
    }
    Row(
        Modifier.fillMaxWidth().background(C.signal(kind)).statusBarsPadding()
            .padding(start = 16.dp, end = 16.dp, top = 10.dp, bottom = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.background(C.Asphalt, RoundedCornerShape(8.dp)).padding(6.dp)) {
            SignalMast(if (flashing && kind == Kind.IDLE) Kind.STOP else kind, vertical = true, lamp = 20.dp, dim = dim)
        }
        Spacer(Modifier.width(14.dp))
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.app_name), Modifier.weight(1f), color = ink, fontSize = 13.sp)
                s.verdictFor?.let {
                    Text(stringResource(R.string.band_since, Presentation.fmtAge(it).text()), color = ink, fontSize = 15.sp,
                        fontWeight = FontWeight.SemiBold, style = Num)
                }
            }
            Text(band.word.text(), Modifier.semantics { heading() }, color = ink, fontSize = 34.sp,
                fontWeight = FontWeight.Bold, lineHeight = 40.sp)
            Text(band.headline.text(), color = ink, fontSize = 16.sp, fontWeight = FontWeight.SemiBold, maxLines = 2,
                lineHeight = 21.sp)
        }
    }
}

// --------------------------------------------------------------------------------- ② what to do now

@Composable
private fun Guidance(g: Presentation.Guide) {
    when (g.kind) {
        Presentation.GuideKind.QUIET -> Text(g.title.text(), color = C.Muted, fontSize = 15.sp)
        else -> InstructionPlate(g.title.text(), g.sub?.text(), danger = g.kind == Presentation.GuideKind.DANGER)
    }
}

@Composable
private fun BindAlert(f: ListenFailure) {
    Column(
        Modifier.fillMaxWidth().border(2.dp, C.Stop).semantics { liveRegion = LiveRegionMode.Assertive }
            .padding(horizontal = 14.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(stringResource(R.string.cannot_listen), color = C.Stop, fontSize = 16.sp, fontWeight = FontWeight.Bold)
        Text(Words.bindError(LocalResources.current, f), color = C.Asphalt, fontSize = 15.sp, lineHeight = 21.sp)
    }
}

// ----------------------------------------------------------------------------- ③ the alignment route

@Composable
private fun AlignmentRoute(s: MonitorSnapshot) {
    val rail = Presentation.rail(s)
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        StationRail(rail)
        // Under the route, one thing only: a real problem, else how many steps are left, else the note.
        val chips = Presentation.blocking(s)
        val problems = chips?.filter { !it.expected }.orEmpty()
        val stable = s.cfg.readyStable
        when {
            problems.isNotEmpty() -> ChipRow { problems.forEach { SignChip(it.text.text(), C.ChipProblem) } }
            !chips.isNullOrEmpty() ->
                Text(pluralStringResource(R.plurals.rail_steps_left, chips.size, chips.size), color = C.AmberInk, fontSize = 13.sp)
            rail.at == 4 && rail.mode == Presentation.RailMode.PROGRESS && rail.fraction > 0 ->
                Text(stringResource(R.string.station_confirming, rail.fraction * stable, Presentation.g(stable)),
                    color = C.Asphalt, fontSize = 13.sp, style = Num)
            rail.note != null -> Text(rail.note.text(), fontSize = 13.sp,
                color = if (rail.mode == Presentation.RailMode.FAULT || rail.mode == Presentation.RailMode.LOST) C.Stop else C.Muted)
        }
    }
}

/** Start, 1 still, 2 straight, 3 fine, usable: the alignment as a road with stations (the desktop's AlignmentRail). */
@Composable
private fun StationRail(r: Presentation.Rail) {
    val labels = Presentation.STATIONS.map { stringResource(it.first) }
    val measurer = rememberTextMeasurer()
    Canvas(Modifier.fillMaxWidth().height(56.dp)) {
        val n = labels.size
        val half = 15.dp.toPx()
        val x0 = half + 1
        val x1 = size.width - half - 1
        val y = half + 1
        val xs = List(n) { x0 + (x1 - x0) * it / (n - 1) }
        val road = 10.dp.toPx()
        drawLine(C.Line, Offset(x0, y), Offset(x1, y), road, StrokeCap.Round)
        if (r.at > 0) drawLine(C.Asphalt, Offset(x0, y), Offset(xs[r.at], y), road, StrokeCap.Round)
        val bw = 2.5.dp.toPx()
        for (i in 0 until n) {
            val last = i == n - 1
            val state = when {
                r.at >= 0 && i < r.at -> "done"
                i == r.at -> when (r.mode) {
                    Presentation.RailMode.DONE -> "go"
                    Presentation.RailMode.LOST -> "lost"
                    else -> "now"
                }
                else -> "future"
            }
            val (fill, ink, outline) = when (state) {
                "done" -> Triple(C.Asphalt, Color.White, C.Asphalt)
                "now" -> Triple(C.Wait, C.Asphalt, C.Asphalt)
                "go" -> Triple(C.Go, Color.White, C.Go)
                "lost" -> Triple(C.Stop, Color.White, C.Stop)
                else -> Triple(C.Panel, C.Faint, C.TabOff)
            }
            val x = xs[i]
            if (last) {                                      // the destination: a sign plate
                val corner = CornerRadius(6.dp.toPx())
                val topLeft = Offset(x - half, y - half)
                val box = Size(2 * half, 2 * half)
                if (state == "now") {                        // ready settling: the plate fills from the bottom
                    drawRoundRect(C.Panel, topLeft, box, corner)
                    if (r.fraction > 0) {
                        val h = (2 * half - 2 * bw) * r.fraction.toFloat()
                        drawRect(C.Wait, Offset(x - half + bw, y + half - bw - h), Size(2 * half - 2 * bw, h))
                    }
                    drawRoundRect(C.Asphalt, topLeft, box, corner, style = Stroke(bw))
                } else {
                    drawRoundRect(fill, topLeft, box, corner)
                    drawRoundRect(outline, topLeft, box, corner, style = Stroke(bw))
                }
                val k = half / 27
                if (state == "go") {
                    drawPath(Path().apply {
                        moveTo(x - 11 * k, y); lineTo(x - 3 * k, y + 9 * k); lineTo(x + 12 * k, y - 9 * k)
                    }, ink, style = Stroke(5 * k, cap = StrokeCap.Round, join = StrokeJoin.Round))
                } else if (state == "lost") {
                    drawLine(ink, Offset(x, y - 9 * k), Offset(x, y + 3 * k), 5 * k, StrokeCap.Round)
                    drawCircle(ink, 3 * k, Offset(x, y + 10 * k))
                }
            } else {
                drawCircle(fill, half, Offset(x, y))
                drawCircle(outline, half - bw / 2, Offset(x, y), style = Stroke(bw))
                if (i > 0) {                                 // start is a marker, not a step
                    val t = measurer.measure("$i", TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Bold, color = ink))
                    drawText(t, topLeft = Offset(x - t.size.width / 2f, y - t.size.height / 2f))
                }
            }
            val current = state in setOf("now", "go", "lost")
            val label = measurer.measure(labels[i], TextStyle(fontSize = 12.sp,
                fontWeight = if (current) FontWeight.Bold else FontWeight.Normal,
                color = if (current || state == "done") C.Asphalt else C.Faint))
            // The ends line up with their markers, so a label never runs off the edge.
            val lx = when (i) {
                0 -> x - half
                n - 1 -> x + half - label.size.width
                else -> x - label.size.width / 2f
            }
            drawText(label, topLeft = Offset(lx, y + half + 4.dp.toPx()))
        }
    }
}

// --------------------------------------------------------------------------------- ④ the two streams

@Composable
private fun Streams(s: MonitorSnapshot) {
    val label = stringResource(R.string.streams_label)
    Row(Modifier.fillMaxWidth().background(C.Line).padding(top = 1.dp).semantics(mergeDescendants = true) { contentDescription = label }) {
        StreamCell("0x04", Presentation.navLink(s), Modifier.weight(1f))
        Spacer(Modifier.width(1.dp))
        StreamCell("0x05", Presentation.statusLink(s), Modifier.weight(1f))
    }
}

@Composable
private fun StreamCell(label: String, link: Presentation.Link, modifier: Modifier) {
    val lost = link.kind == Kind.STOP
    Column(
        modifier.background(C.Panel).then(if (lost) Modifier.border(2.dp, C.Stop) else Modifier)
            .padding(horizontal = 12.dp, vertical = 8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            val dot = when (link.kind) {
                Kind.GO -> C.Go
                Kind.STOP -> C.Stop
                else -> C.Faint
            }
            Box(Modifier.size(10.dp).background(dot, CircleShape))
            Text(label, color = C.Muted, fontSize = 12.sp)
        }
        Text(link.text.text(), color = if (lost) C.Stop else C.Asphalt, fontSize = 14.sp, fontWeight = FontWeight.Medium,
            style = Num, maxLines = 1)
    }
}

// --------------------------------------------------------------------------------- ⑤ the detail rows

@Composable
private fun Details(s: MonitorSnapshot) {
    var open by rememberSaveable { mutableStateOf<Int?>(null) }
    fun toggle(i: Int) {
        open = if (open == i) null else i
    }
    NavRow(s, open == 0) { toggle(0) }
    StatusRow(s, open == 1) { toggle(1) }
    StatsRow(s, open == 2) { toggle(2) }
}

@Composable
private fun NavRow(s: MonitorSnapshot, expanded: Boolean, onToggle: () -> Unit) {
    val n = s.nav
    val stale = (s.navAge ?: Double.POSITIVE_INFINITY) > s.cfg.navMaxAge
    val sigma = n?.let { listOf(it.posNStd, it.posEStd, it.posDStd).joinToString("/") { v -> Format.number(v.toDouble(), 2) } }
    ExpandRow(stringResource(R.string.card_nav), expanded, onToggle, summary = {
        Summary(if (n == null) stringResource(R.string.no_nav)
        else stringResource(if (n.isAligned) R.string.nav_summary_aligned else R.string.nav_summary_not_aligned, sigma!!))
    }) {
        if (n == null) {
            Text(stringResource(R.string.no_nav), color = C.Muted, fontSize = 14.sp)
            return@ExpandRow
        }
        ValueGrid(listOf(
            stringResource(R.string.data_age) to (s.navAge?.let { Format.number(it * 1000, 0, "ms") } ?: "—"),
            stringResource(R.string.receive_rate) to Format.number(s.navRateHz, 1, "Hz"),
            stringResource(R.string.position_sigma_ned) to "$sigma m",
            stringResource(R.string.heading_sigma) to Format.number(n.headingStd.toDouble(), 3, "°"),
            stringResource(R.string.latitude) to Format.number(n.lat, 8, "°"),
            stringResource(R.string.longitude) to Format.number(n.lon, 8, "°"),
            stringResource(R.string.height) to Format.number(n.height.toDouble(), 2, "m"),
            stringResource(R.string.heading) to Format.number(n.heading360, 1, "°"),
            stringResource(R.string.speed) to Format.number(n.groundSpeed, 2, "m/s") + " (" + Format.number(n.groundSpeed * 3.6, 1, "km/h") + ")",
            stringResource(R.string.roll_pitch) to Format.number(n.roll.toDouble(), 2) + " / " + Format.number(n.pitch.toDouble(), 2, "°"),
        ), faint = stale)
        SubTitle(stringResource(R.string.alignment))
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            val res = LocalResources.current
            Aio.ALIGNMENT_FLAGS.forEach { flag ->
                val on = n.hasFlag(flag) && !stale
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Box(Modifier.size(12.dp).background(if (on) C.Go else C.Panel, CircleShape)
                        .border(2.dp, if (on) C.Go else C.InputLine, CircleShape))
                    Text(Words.lamp(res, flag), color = if (on) C.Asphalt else C.Faint, fontSize = 13.sp,
                        fontWeight = if (on) FontWeight.Bold else FontWeight.Normal)
                }
            }
        }
        SubTitle(stringResource(R.string.aiding))
        ChipRow { Aio.AIDING_FLAGS.forEach { SignChip(it, if (n.hasFlag(it) && !stale) C.ChipAid else C.ChipAidOff) } }
    }
}

@Composable
private fun StatusRow(s: MonitorSnapshot, expanded: Boolean, onToggle: () -> Unit) {
    val res = LocalResources.current
    val st = s.status
    val fresh = Presentation.statusFresh(s)
    val rows = Presentation.conditions(s)
    val unmet = rows.count { !it.second }
    ExpandRow(stringResource(R.string.card_status), expanded, onToggle, summary = {
        when {
            st == null -> Summary(stringResource(R.string.no_status))
            fresh -> Summary(stringResource(R.string.status_summary, Words.state(res, st.state), unmet, rows.size))
            else -> Summary(stringResource(R.string.status_summary_stale, Words.state(res, st.state)), C.Stop)
        }
    }) {
        if (st == null) {
            Text(stringResource(R.string.no_status), color = C.Muted, fontSize = 14.sp)
            return@ExpandRow
        }
        ValueGrid(listOf(
            stringResource(R.string.state) to Words.state(res, st.state),
            stringResource(R.string.requested_action) to Words.action(res, st.action),
            stringResource(R.string.gnss_quality) to Words.gnssQuality(res, st.gnssQuality),
            stringResource(R.string.session) to String.format(Locale.ROOT, "0x%08X", st.session),
            stringResource(R.string.sequence) to "${st.sequence}",
            stringResource(R.string.uptime) to Format.duration(st.uptimeMs.toULong().toDouble() / 1000),
            stringResource(R.string.nav_rate_dashboard) to Format.number(st.navRateHz, 1, "Hz"),
            stringResource(R.string.nav_age_dashboard) to if (st.navAgeMs == Aio.NAV_AGE_UNKNOWN) "—" else "${st.navAgeMs} ms",
            stringResource(R.string.status_age) to (s.statusAge?.let { Format.number(it, 1, "s") } ?: "—"),
        ), faint = !fresh)
        // Blocking conditions: every one, the alignment steps amber, the rest red. Out of date: all faint, never green.
        SubTitle(stringResource(R.string.block_title))
        val aligning = Aio.nameOf(st.state, Aio.STATES) in Presentation.STARTUP + Presentation.ALIGNING
        val bits = Words.bits(st.inhibit, Aio.INHIBIT_BITS.size)
        if (!fresh) Text(stringResource(R.string.block_unknown), color = C.Stop, fontSize = 13.sp)
        if (bits.isEmpty()) {
            Text(stringResource(R.string.none), color = if (fresh) C.Go else C.Faint, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
        } else {
            ChipRow {
                bits.forEach { b ->
                    val expected = aligning && Aio.INHIBIT_BITS[b] in Presentation.STEP_BITS
                    SignChip(Words.inhibit(res, b), if (!fresh) C.ChipAidOff else if (expected) C.ChipExpected else C.ChipProblem)
                }
            }
            if (fresh && aligning && bits.any { Aio.INHIBIT_BITS[it] in Presentation.STEP_BITS }) {
                Text(stringResource(R.string.block_expected), color = C.AmberInk, fontSize = 12.sp)
            }
        }
        SubTitle(stringResource(R.string.status_health) + if (fresh) "" else stringResource(R.string.status_out_of_date),
            color = if (fresh) C.Muted else C.Stop,
            trailing = stringResource(R.string.status_met, rows.size - unmet, rows.size))
        Conditions(rows, fresh)
    }
}

/** The 18 health conditions in two columns, the unmet first (● met, ○ unmet). */
@Composable
private fun Conditions(rows: List<Pair<Txt, Boolean>>, fresh: Boolean) {
    val half = (rows.size + 1) / 2
    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        listOf(rows.take(half), rows.drop(half)).forEach { column ->
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                column.forEach { (name, met) ->
                    Text((if (met) "● " else "○ ") + name.text(), fontSize = 13.sp, lineHeight = 17.sp,
                        color = if (!fresh) C.Faint else if (met) C.Go else C.Asphalt,
                        fontWeight = if (met) FontWeight.Normal else FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun StatsRow(s: MonitorSnapshot, expanded: Boolean, onToggle: () -> Unit) {
    val c = s.counts
    val usable = Format.duration(s.usableSeconds)
    val problems = listOf(
        Triple(R.string.lost_05, c.lost, C.Amber), Triple(R.string.out_of_order, c.reordered.toLong(), C.Amber),
        Triple(R.string.two_senders, c.conflicts.toLong(), C.Stop), Triple(R.string.invalid, c.bad.toLong(), C.Stop),
        Triple(R.string.other_sources, c.foreign.toLong(), C.Stop),
    ).filter { it.second > 0 }
    val separator = stringResource(R.string.list_separator)
    val labels = problems.map { stringResource(it.first) }
    val okText = stringResource(R.string.stats_ok)
    val total = stringResource(R.string.band_total)
    ExpandRow(stringResource(R.string.card_statistics), expanded, onToggle, summary = {
        Text(buildAnnotatedString {
            if (problems.isEmpty()) append(okText)
            problems.forEachIndexed { i, (_, n, color) ->
                if (i > 0) append(separator)
                withStyle(SpanStyle(color = color, fontWeight = FontWeight.SemiBold)) { append("${labels[i]} $n") }
            }
            append("  $total $usable")
        }, color = C.Muted, fontSize = 13.sp, maxLines = 1, style = Num, textAlign = TextAlign.End,
            overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
    }) {
        ValueGrid(listOf(
            stringResource(R.string.packets_04) to "${c.nav}",
            stringResource(R.string.packets_05) to "${c.status}",
            stringResource(R.string.lost_05) to "${c.lost}",
            stringResource(R.string.out_of_order) to "${c.reordered}",
            stringResource(R.string.two_senders) to "${c.conflicts}",
            stringResource(R.string.invalid) to "${c.bad}",
            stringResource(R.string.other_sources) to "${c.foreign}",
            stringResource(R.string.time_usable) to usable,
            stringResource(R.string.last_sender) to ((s.navSender ?: s.statusSender) ?: "—"),
        ))
    }
}

// ---------------------------------------------------------------------------------- ⑥ where it listens

@Composable
private fun ListeningInfo(settings: MonitorSettings, listening: Boolean, address: Pair<String, String>?, onStart: () -> Unit) {
    Column(
        Modifier.fillMaxWidth().background(C.Kerb).padding(horizontal = 16.dp, vertical = 12.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        val where = address?.let { (nif, ip) -> stringResource(R.string.this_phone) + " $ip ($nif)" }
        Text(
            listOfNotNull(
                if (listening) stringResource(R.string.listening_on, settings.ports.joinToString(", "))
                else stringResource(R.string.not_listening),
                where,
            ).joinToString("　"),
            color = C.Muted, fontSize = 12.sp, textAlign = TextAlign.Center, style = Num,
        )
        if (!listening) {
            OutlinedButton(onClick = onStart, Modifier.heightIn(min = 48.dp), shape = RoundedCornerShape(4.dp),
                border = BorderStroke(2.dp, C.Asphalt), colors = ButtonDefaults.outlinedButtonColors(containerColor = C.Panel)) {
                Text(stringResource(R.string.start_monitoring), color = C.Asphalt, fontSize = 16.sp, fontWeight = FontWeight.Bold)
            }
        }
    }
}
