package com.lemongrass.aionav.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Person
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.lemongrass.aionav.R
import com.lemongrass.aionav.core.Aio
import com.lemongrass.aionav.monitor.MonitorSettings
import com.lemongrass.aionav.monitor.MonitorSnapshot
import java.util.Locale

@Composable
fun StatusScreen(
    snapshot: MonitorSnapshot,
    settings: MonitorSettings,
    listening: Boolean,
    listenError: String?,
    address: Pair<String, String>?,
    onStart: () -> Unit,
) {
    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        VerdictBanner(snapshot)
        if (listenError != null) {
            Card(stringResource(R.string.cannot_listen), tint = WarningOrange) {
                Text(listenError, fontFamily = FontFamily.Monospace, color = WarningOrange)
                Text(stringResource(R.string.cannot_listen_hint), style = MaterialTheme.typography.bodySmall)
            }
        }
        NavigationCard(snapshot)
        StatusPacketCard(snapshot)
        StatisticsCard(snapshot)
        ListeningFooter(snapshot, settings, listening, address, onStart)
    }
}

@Composable
fun VerdictBanner(snapshot: MonitorSnapshot) {
    val res = LocalResources.current
    val usable = snapshot.verdict.usable
    val color by animateColorAsState(if (usable) UsableGreen else BlockedRed, label = "banner")
    Column(
        Modifier.fillMaxWidth().background(color, RoundedCornerShape(24.dp)).padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(if (usable) Icons.Filled.CheckCircle else Icons.Filled.Close, null, Modifier.size(40.dp), tint = Color.White)
            Spacer(Modifier.width(10.dp))
            Text(stringResource(if (usable) R.string.usable else R.string.blocked),
                Modifier.semantics { heading() }, style = MaterialTheme.typography.displaySmall,
                fontWeight = FontWeight.Bold, color = Color.White)
            Spacer(Modifier.weight(1f))
            snapshot.status?.let {
                Text(Words.state(res, it.state),
                    Modifier.background(Color.White.copy(alpha = 0.22f), RoundedCornerShape(50))
                        .padding(horizontal = 10.dp, vertical = 5.dp),
                    fontWeight = FontWeight.SemiBold, color = Color.White, style = MaterialTheme.typography.labelLarge)
            }
        }
        if (!usable) {
            Text(Words.reason(res, snapshot.verdict), style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.SemiBold, color = Color.White)
            Words.reasonDetail(res, snapshot.verdict)?.let {
                Text(it, style = MaterialTheme.typography.bodyMedium, color = Color.White)
            }
        }
        snapshot.status?.let { Words.instruction(res, it.action) }?.let {
            Row(Modifier.padding(top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Icon(Icons.Filled.Person, null, tint = Color.White)
                Spacer(Modifier.width(8.dp))
                Text(it, style = MaterialTheme.typography.titleMedium, color = Color.White)
            }
        }
    }
}

@Composable
private fun NavigationCard(snapshot: MonitorSnapshot) {
    val res = LocalResources.current
    Card(stringResource(R.string.card_nav)) {
        val n = snapshot.nav
        if (n == null) {
            Text(stringResource(R.string.no_nav), color = MaterialTheme.colorScheme.onSurfaceVariant)
            return@Card
        }
        InfoRow(R.string.latitude, Format.number(n.lat, 8, "°"))
        InfoRow(R.string.longitude, Format.number(n.lon, 8, "°"))
        InfoRow(R.string.height, Format.number(n.height.toDouble(), 2, "m"))
        InfoRow(R.string.heading, Format.number(n.heading360, 1, "°"))
        InfoRow(R.string.speed, Format.number(n.groundSpeed, 2, "m/s") + "  (" + Format.number(n.groundSpeed * 3.6, 1, "km/h") + ")")
        InfoRow(R.string.roll_pitch, Format.number(n.roll.toDouble(), 2) + " / " + Format.number(n.pitch.toDouble(), 2, "°"))
        InfoRow(R.string.position_sigma_ned,
            listOf(n.posNStd, n.posEStd, n.posDStd).joinToString(" / ") { Format.number(it.toDouble(), 3) } + " m")
        InfoRow(R.string.heading_sigma, Format.number(n.headingStd.toDouble(), 3, "°"))
        InfoRow(R.string.data_age, snapshot.navAge?.let { Format.number(it * 1000, 0, "ms") } ?: "—")
        InfoRow(R.string.receive_rate, Format.number(snapshot.navRateHz, 1, "Hz"))
        HorizontalDivider()
        SubTitle(R.string.alignment)
        ChipRow { Aio.ALIGNMENT_FLAGS.forEach { Chip(Words.lamp(res, it), on = n.hasFlag(it)) } }
        SubTitle(R.string.aiding)
        ChipRow { Aio.AIDING_FLAGS.forEach { Chip(it, tint = InfoBlue, on = n.hasFlag(it)) } }
    }
}

@Composable
private fun StatusPacketCard(snapshot: MonitorSnapshot) {
    val res = LocalResources.current
    Card(stringResource(R.string.card_status)) {
        val s = snapshot.status
        if (s == null) {
            Text(stringResource(R.string.no_status), color = MaterialTheme.colorScheme.onSurfaceVariant)
            return@Card
        }
        InfoRow(R.string.state, Words.state(res, s.state))
        InfoRow(R.string.requested_action, Words.action(res, s.action))
        InfoRow(R.string.gnss_quality, Words.gnssQuality(res, s.gnssQuality))
        InfoRow(R.string.session, String.format(Locale.ROOT, "0x%08X", s.session))
        InfoRow(R.string.sequence, "${s.sequence}")
        InfoRow(R.string.uptime, Format.duration(s.uptimeMs.toULong().toDouble() / 1000))
        InfoRow(R.string.nav_rate_dashboard, Format.number(s.navRateHz, 1, "Hz"))
        InfoRow(R.string.nav_age_dashboard, if (s.navAgeMs == Aio.NAV_AGE_UNKNOWN) "—" else "${s.navAgeMs} ms")
        InfoRow(R.string.status_age, snapshot.statusAge?.let { Format.number(it, 1, "s") } ?: "—")
        HorizontalDivider()
        SubTitle(R.string.inhibit)
        val inhibit = Words.inhibitList(res, s.inhibit)
        if (inhibit.isEmpty()) Text(stringResource(R.string.none)) else ChipRow { inhibit.forEach { Chip(it, tint = BlockedRed) } }
        SubTitle(R.string.health)
        ChipRow { Words.healthList(res, s.health).forEach { Chip(it) } }
    }
}

@Composable
private fun StatisticsCard(snapshot: MonitorSnapshot) {
    val c = snapshot.counts
    Card(stringResource(R.string.card_statistics)) {
        InfoRow(R.string.packets_04, "${c.nav}")
        InfoRow(R.string.packets_05, "${c.status}")
        InfoRow(R.string.lost_05, "${c.lost}")
        InfoRow(R.string.out_of_order, "${c.reordered}")
        InfoRow(R.string.two_senders, "${c.conflicts}")
        InfoRow(R.string.invalid, "${c.bad}")
        InfoRow(R.string.other_sources, "${c.foreign}")
        InfoRow(R.string.time_usable, Format.duration(snapshot.usableSeconds))
    }
}

@Composable
private fun ListeningFooter(snapshot: MonitorSnapshot, settings: MonitorSettings, listening: Boolean,
                            address: Pair<String, String>?, onStart: () -> Unit) {
    val style = MaterialTheme.typography.bodySmall
    val color = MaterialTheme.colorScheme.onSurfaceVariant
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (listening) {
            Text(stringResource(R.string.listening_on, settings.ports.joinToString(", ")), style = style, color = color)
        } else {
            Text(stringResource(R.string.not_listening), style = style, color = color)
            OutlinedButton(onClick = onStart) { Text(stringResource(R.string.start_monitoring)) }
        }
        address?.let { (nif, ip) ->
            Text(stringResource(R.string.this_phone) + "  $ip ($nif)", style = style, color = color)
        }
        (snapshot.navSender ?: snapshot.statusSender)?.let {
            Text(stringResource(R.string.last_sender) + "  $it", style = style, color = color)
        }
    }
}
