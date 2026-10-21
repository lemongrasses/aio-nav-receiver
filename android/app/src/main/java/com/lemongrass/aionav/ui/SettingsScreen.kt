package com.lemongrass.aionav.ui

import androidx.annotation.StringRes
import androidx.appcompat.app.AppCompatDelegate
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material3.Button
import androidx.compose.material3.FilledTonalIconButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.core.content.pm.PackageInfoCompat
import androidx.core.os.LocaleListCompat
import com.lemongrass.aionav.R
import com.lemongrass.aionav.monitor.MonitorService
import com.lemongrass.aionav.monitor.MonitorSettings
import com.lemongrass.aionav.monitor.WifiState
import java.util.Locale
import kotlin.math.roundToInt

@Composable
fun SettingsScreen(
    settings: MonitorSettings,
    listening: Boolean,
    addresses: List<Pair<String, String>>,
    wifi: WifiState,
    notificationsOff: Boolean,
    onApply: (MonitorSettings) -> Unit,
    onClear: () -> Unit,
) {
    var draft by remember { mutableStateOf(settings) }
    // Port fields are text while typing; parsed into the draft.
    var navPortText by remember { mutableStateOf(settings.navPort.toString()) }
    var statusPortText by remember { mutableStateOf(settings.statusPort?.toString() ?: "") }
    LaunchedEffect(settings) {
        draft = settings
        navPortText = settings.navPort.toString()
        statusPortText = settings.statusPort?.toString() ?: ""
    }
    val navPort = navPortText.toIntOrNull()
    val statusPort = if (draft.statusPort == null) null else statusPortText.toIntOrNull()
    val candidate = draft.copy(navPort = navPort ?: 0, statusPort = statusPort ?: draft.statusPort?.let { 0 })
    val valid = candidate.isValid

    Column(
        Modifier.verticalScroll(rememberScrollState()).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Card(stringResource(R.string.this_phone)) {
            if (addresses.isEmpty()) {
                Text(stringResource(R.string.not_connected), color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            SelectionContainer {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    addresses.forEach { (nif, ip) -> ValueRow(nif, ip) }
                }
            }
            ValueRow(stringResource(R.string.wifi), stringResource(when {
                !wifi.connected -> R.string.wifi_off
                wifi.noInternet -> R.string.wifi_no_internet
                else -> R.string.wifi_connected
            }))
            ValueRow(stringResource(R.string.receiving), stringResource(if (listening) R.string.yes else R.string.no),
                color = if (listening) UsableGreen else BlockedRed)
            ValueRow(stringResource(R.string.version), appVersion())
            Footer(R.string.this_phone_footer)
        }

        Card(stringResource(R.string.section_receiving)) {
            NumberField(R.string.port_04, navPortText) { navPortText = it }
            SwitchRow(R.string.separate_05_port, draft.statusPort != null) { on ->
                val p = (navPort ?: 9000) + 1
                draft = draft.copy(statusPort = if (on) p else null)
                statusPortText = if (on) p.toString() else ""
            }
            if (draft.statusPort != null) {
                NumberField(R.string.port_05, statusPortText) { statusPortText = it }
            }
            Stepper(R.string.message_id_05, String.format(Locale.ROOT, "0x%02X", draft.statusMessageId),
                onMinus = { draft = draft.copy(statusMessageId = (draft.statusMessageId - 1).coerceAtLeast(1)) },
                onPlus = { draft = draft.copy(statusMessageId = (draft.statusMessageId + 1).coerceAtMost(255)) })
            OutlinedTextField(
                value = draft.allowedSourceIp,
                onValueChange = { draft = draft.copy(allowedSourceIp = it.trim()) },
                label = { Text(stringResource(R.string.accept_only_ip)) },
                placeholder = { Text(stringResource(R.string.any)) },
                singleLine = true,
                isError = draft.allowedSource?.let { !MonitorSettings.isIPv4(it) } ?: false,
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.fillMaxWidth(),
            )
            Footer(R.string.receiving_footer)
        }

        Card(stringResource(R.string.section_rules)) {
            SecondsStepper(R.string.status_timeout, draft.statusTimeout, 0.5..30.0, 0.5) { draft = draft.copy(statusTimeout = it) }
            SecondsStepper(R.string.ready_stable, draft.readyStable, 0.0..30.0, 0.5) { draft = draft.copy(readyStable = it) }
            SecondsStepper(R.string.max_nav_age, draft.navMaxAge, 0.1..5.0, 0.1) { draft = draft.copy(navMaxAge = it) }
            Footer(R.string.rules_footer)
        }

        Card(stringResource(R.string.section_display)) {
            SwitchRow(R.string.keep_screen_on, draft.keepScreenOn) { draft = draft.copy(keepScreenOn = it) }
            SwitchRow(R.string.background, draft.background) { draft = draft.copy(background = it) }
            Footer(R.string.display_footer)
            LanguageRow()
            if (notificationsOff) {
                Text(stringResource(R.string.notifications_off), style = MaterialTheme.typography.bodySmall, color = WarningOrange)
            }
        }

        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Button(onClick = { onApply(candidate) }, enabled = valid && candidate != settings, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.apply))
            }
            OutlinedButton(onClick = {
                draft = MonitorSettings()
                navPortText = draft.navPort.toString()
                statusPortText = ""
            }, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.restore_defaults))
            }
            TextButton(onClick = onClear, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.clear_history), color = BlockedRed)
            }
            if (!valid) {
                Text(stringResource(R.string.check_settings), color = BlockedRed, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

/**
 * Follow system / 繁體中文 / English, like the desktop's Settings → Display → Language. Applies at once (the
 * screen is redrawn in the new language) and never restarts receiving.
 */
@Composable
private fun LanguageRow() {
    val context = LocalContext.current
    val current = AppCompatDelegate.getApplicationLocales().toLanguageTags()
    val options = listOf("" to R.string.language_system, "zh-TW" to R.string.language_zh, "en" to R.string.language_en)
    val selected = when {
        current.startsWith("zh") -> "zh-TW"
        current.startsWith("en") -> "en"
        else -> ""
    }
    Text(stringResource(R.string.language))
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
        options.forEachIndexed { i, (tag, label) ->
            SegmentedButton(
                selected = selected == tag,
                onClick = {
                    AppCompatDelegate.setApplicationLocales(
                        if (tag.isEmpty()) LocaleListCompat.getEmptyLocaleList() else LocaleListCompat.forLanguageTags(tag))
                    MonitorService.refresh(context)
                },
                shape = SegmentedButtonDefaults.itemShape(i, options.size),
            ) { Text(stringResource(label), maxLines = 1) }
        }
    }
}

/** versionName (versionCode), e.g. 1.2.0 (10200). */
@Composable
private fun appVersion(): String {
    val context = LocalContext.current
    return remember {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        "${info.versionName} (${PackageInfoCompat.getLongVersionCode(info)})"
    }
}

@Composable
private fun ValueRow(label: String, value: String, color: androidx.compose.ui.graphics.Color? = null) {
    Row(Modifier.fillMaxWidth()) {
        Text(label, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.weight(1f).width(12.dp))
        Text(value, fontFamily = FontFamily.Monospace, textAlign = TextAlign.End,
            color = color ?: MaterialTheme.colorScheme.onSurface)
    }
}

@Composable
private fun Footer(@StringRes text: Int) {
    Text(stringResource(text), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun SwitchRow(@StringRes label: Int, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(stringResource(label), Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = onChange)
    }
}

@Composable
private fun NumberField(@StringRes label: Int, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = { t -> onChange(t.filter(Char::isDigit).take(5)) },
        label = { Text(stringResource(label)) },
        singleLine = true,
        isError = value.toIntOrNull()?.let { it !in 1..65535 } ?: true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
        modifier = Modifier.fillMaxWidth(),
    )
}

@Composable
private fun Stepper(@StringRes label: Int, value: String, onMinus: () -> Unit, onPlus: () -> Unit) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(stringResource(label), Modifier.weight(1f))
        Text(value, Modifier.widthIn(min = 64.dp), fontFamily = FontFamily.Monospace, textAlign = TextAlign.End)
        Spacer(Modifier.width(8.dp))
        FilledTonalIconButton(onClick = onMinus) {
            Icon(Icons.Filled.KeyboardArrowDown, stringResource(R.string.decrease))
        }
        FilledTonalIconButton(onClick = onPlus) {
            Icon(Icons.Filled.KeyboardArrowUp, stringResource(R.string.increase))
        }
    }
}

@Composable
private fun SecondsStepper(@StringRes label: Int, value: Double, range: ClosedFloatingPointRange<Double>, step: Double,
                           onChange: (Double) -> Unit) {
    // Keep the value on the step grid (0.1 s) so repeated presses do not drift.
    fun snap(v: Double) = (v * 10).roundToInt() / 10.0
    Stepper(label, Format.number(value, 1, "s"),
        onMinus = { onChange(snap((value - step).coerceIn(range.start, range.endInclusive))) },
        onPlus = { onChange(snap((value + step).coerceIn(range.start, range.endInclusive))) })
}
