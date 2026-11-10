// The settings tab, layout C (docs/UI-PHONE-C.zh-TW.md 4.4): "Everyday" (never changes the verdict) and
// "Advanced: receiving and rules" (must match the device), the rules in a red box. The behaviour is the earlier one:
// a draft that takes effect with Apply (the blue bar above the tabs lists what is pending), the language at once,
// "Restore defaults" changes only the draft, "Clear charts and statistics" clears at once (decision D1).

package com.lemongrass.aionav.ui

import androidx.annotation.StringRes
import androidx.appcompat.app.AppCompatDelegate
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
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
    val pending = pendingFields(candidate, settings).map { stringResource(it) }

    Box(Modifier.fillMaxSize()) {
        Column(Modifier.fillMaxSize()) {
            PageHeader(stringResource(R.string.tab_settings), kind = null)
            Column(Modifier.verticalScroll(rememberScrollState()).padding(bottom = if (pending.isNotEmpty()) 76.dp else 16.dp)) {
                Section(R.string.set_sec_everyday, R.string.set_everyday_sub) {
                    SelectionContainer {
                        Column {
                            if (addresses.isEmpty()) ValueRow(stringResource(R.string.this_phone), stringResource(R.string.not_connected))
                            addresses.forEach { (nif, ip) -> ValueRow(stringResource(R.string.this_phone) + " " + nif, ip, number = true) }
                        }
                    }
                    ValueRow(stringResource(R.string.wifi), stringResource(when {
                        !wifi.connected -> R.string.wifi_off
                        wifi.noInternet -> R.string.wifi_no_internet
                        else -> R.string.wifi_connected
                    }))
                    ValueRow(stringResource(R.string.receiving), "● " + stringResource(if (listening) R.string.yes else R.string.no),
                        color = if (listening) C.Go else C.Stop)
                    ValueRow(stringResource(R.string.version), appVersion(), number = true)
                    Foot(R.string.this_phone_footer)
                    LanguageRow()
                    SwitchRow(R.string.keep_screen_on, draft.keepScreenOn) { draft = draft.copy(keepScreenOn = it) }
                    SwitchRow(R.string.background, draft.background) { draft = draft.copy(background = it) }
                    Foot(R.string.display_footer)
                    if (notificationsOff) {
                        Text(stringResource(R.string.notifications_off), Modifier.padding(top = 6.dp), color = C.Warning,
                            fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                    }
                }

                Section(R.string.set_sec_advanced, R.string.set_advanced_sub) {
                    FieldRow(R.string.port_04) { NumberField(navPortText, portBad(navPortText)) { navPortText = it } }
                    SwitchRow(R.string.separate_05_port, draft.statusPort != null) { on ->
                        val p = (navPort ?: 9000) + 1
                        draft = draft.copy(statusPort = if (on) p else null)
                        statusPortText = if (on) p.toString() else ""
                    }
                    if (draft.statusPort != null) {
                        FieldRow(R.string.port_05) { NumberField(statusPortText, portBad(statusPortText)) { statusPortText = it } }
                    }
                    FieldRow(R.string.message_id_05) {
                        Stepper(String.format(Locale.ROOT, "0x%02X", draft.statusMessageId),
                            onMinus = { draft = draft.copy(statusMessageId = (draft.statusMessageId - 1).coerceAtLeast(1)) },
                            onPlus = { draft = draft.copy(statusMessageId = (draft.statusMessageId + 1).coerceAtMost(255)) })
                    }
                    FieldRow(R.string.accept_only_ip) {
                        TextInput(draft.allowedSourceIp, draft.allowedSource?.let { !MonitorSettings.isIPv4(it) } ?: false,
                            KeyboardType.Decimal, 150.dp, placeholder = stringResource(R.string.any)) {
                            draft = draft.copy(allowedSourceIp = it.trim())
                        }
                    }
                    Foot(R.string.receiving_footer)
                    Column(Modifier.padding(top = 12.dp).fillMaxWidth().border(2.dp, C.Stop).padding(start = 12.dp, end = 12.dp, top = 6.dp, bottom = 10.dp)) {
                        Text(stringResource(R.string.set_rules_title), Modifier.padding(vertical = 4.dp), color = C.Stop,
                            fontSize = 14.sp, fontWeight = FontWeight.Bold)
                        SecondsRow(R.string.status_timeout, draft.statusTimeout, 0.5..30.0, 0.5) { draft = draft.copy(statusTimeout = it) }
                        SecondsRow(R.string.ready_stable, draft.readyStable, 0.0..30.0, 0.5) { draft = draft.copy(readyStable = it) }
                        SecondsRow(R.string.max_nav_age, draft.navMaxAge, 0.1..5.0, 0.1) { draft = draft.copy(navMaxAge = it) }
                        Foot(R.string.rules_defaults)
                    }
                }

                Column(Modifier.padding(top = 12.dp).fillMaxWidth().background(C.Panel).padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    ActionRow(R.string.restore_hint, R.string.restore_defaults, C.Asphalt) {
                        draft = MonitorSettings()
                        navPortText = draft.navPort.toString()
                        statusPortText = ""
                    }
                    HorizontalDivider(color = C.Rule)
                    ActionRow(R.string.clear_hint, R.string.clear_history, C.Stop, onClear)
                }
            }
        }
        if (pending.isNotEmpty()) {
            ApplyBar(pending, valid, Modifier.align(Alignment.BottomCenter)) { onApply(candidate) }
        }
    }
}

/** The fields whose draft differs from what is in force, by their labels. The language is not one: it applies at once. */
private fun pendingFields(d: MonitorSettings, s: MonitorSettings): List<Int> = buildList {
    if (d.navPort != s.navPort) add(R.string.port_04)
    if ((d.statusPort == null) != (s.statusPort == null)) add(R.string.separate_05_port)
    else if (d.statusPort != s.statusPort) add(R.string.port_05)
    if (d.statusMessageId != s.statusMessageId) add(R.string.message_id_05)
    if (d.allowedSourceIp.trim() != s.allowedSourceIp.trim()) add(R.string.accept_only_ip)
    if (d.statusTimeout != s.statusTimeout) add(R.string.status_timeout)
    if (d.readyStable != s.readyStable) add(R.string.ready_stable)
    if (d.navMaxAge != s.navMaxAge) add(R.string.max_nav_age)
    if (d.keepScreenOn != s.keepScreenOn) add(R.string.keep_screen_on)
    if (d.background != s.background) add(R.string.background)
}

private fun portBad(text: String) = text.toIntOrNull()?.let { it !in 1..65535 } ?: true

/** Blue: what is not applied yet, and Apply. Red with no button while the draft has an error. */
@Composable
private fun ApplyBar(pending: List<String>, valid: Boolean, modifier: Modifier, onApply: () -> Unit) {
    Row(
        modifier.fillMaxWidth().background(if (valid) C.Info else C.Stop).padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (valid) {
            Text(pluralStringResource(R.plurals.apply_pending, pending.size, pending.size,
                pending.joinToString(stringResource(R.string.list_separator))),
                Modifier.weight(1f), color = Color.White, fontSize = 14.sp, lineHeight = 19.sp)
            Box(
                Modifier.heightIn(min = 44.dp).background(Color.White, RoundedCornerShape(4.dp))
                    .clickable(role = Role.Button, onClick = onApply).padding(horizontal = 22.dp),
                contentAlignment = Alignment.Center,
            ) { Text(stringResource(R.string.apply), color = C.Info, fontSize = 15.sp, fontWeight = FontWeight.Bold) }
        } else {
            Text(stringResource(R.string.check_settings), Modifier.weight(1f).heightIn(min = 44.dp).padding(vertical = 12.dp),
                color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun Section(@StringRes title: Int, @StringRes sub: Int, content: @Composable ColumnScope.() -> Unit) {
    Column(Modifier.padding(start = 16.dp, end = 16.dp, top = 18.dp, bottom = 8.dp)) {
        Text(stringResource(title), color = C.Asphalt, fontSize = 17.sp, fontWeight = FontWeight.Bold)
        Text(stringResource(sub), color = C.Muted, fontSize = 13.sp)
    }
    Column(Modifier.fillMaxWidth().background(C.Panel).padding(start = 16.dp, end = 16.dp, top = 4.dp, bottom = 12.dp), content = content)
}

/** A settings line: at least 50 dp, a rule above it, the value on the right. */
@Composable
private fun Line(content: @Composable RowScope.() -> Unit) {
    Column {
        HorizontalDivider(color = C.Rule)
        Row(Modifier.fillMaxWidth().heightIn(min = 50.dp).padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp), content = content)
    }
}

@Composable
private fun ValueRow(label: String, value: String, color: Color = C.Asphalt, number: Boolean = false) {
    Line {
        Text(label, Modifier.weight(1f), color = C.Asphalt, fontSize = 15.sp)
        Text(value, color = color, fontSize = if (number) 17.sp else 15.sp, fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.End, style = Num)
    }
}

@Composable
private fun FieldRow(@StringRes label: Int, field: @Composable () -> Unit) {
    Line {
        Text(stringResource(label), Modifier.weight(1f), color = C.Asphalt, fontSize = 15.sp)
        field()
    }
}

@Composable
private fun Foot(@StringRes text: Int) {
    Text(stringResource(text), Modifier.padding(top = 6.dp), color = C.Muted, fontSize = 13.sp, lineHeight = 19.sp)
}

@Composable
private fun SwitchRow(@StringRes label: Int, checked: Boolean, onChange: (Boolean) -> Unit) {
    Line {
        Text(stringResource(label), Modifier.weight(1f), color = C.Asphalt, fontSize = 15.sp)
        Switch(checked = checked, onCheckedChange = onChange, colors = SwitchDefaults.colors(
            checkedTrackColor = C.Asphalt, checkedThumbColor = Color.White,
            uncheckedTrackColor = C.InputLine, uncheckedThumbColor = Color.White, uncheckedBorderColor = C.InputLine))
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
    Line {
        Column(Modifier.weight(1f)) {
            Text(stringResource(R.string.language), color = C.Asphalt, fontSize = 15.sp)
            Text(stringResource(R.string.language_hint), color = C.Muted, fontSize = 12.5.sp)
        }
        Row(Modifier.selectableGroup().border(1.5.dp, C.Asphalt, RoundedCornerShape(4.dp))) {
            options.forEach { (tag, label) ->
                val on = selected == tag
                Box(
                    Modifier.heightIn(min = 40.dp).background(if (on) C.Asphalt else Color.White)
                        .selectable(on, role = Role.RadioButton) {
                            AppCompatDelegate.setApplicationLocales(
                                if (tag.isEmpty()) LocaleListCompat.getEmptyLocaleList() else LocaleListCompat.forLanguageTags(tag))
                            MonitorService.refresh(context)
                        }
                        .padding(horizontal = 10.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Text(stringResource(label), color = if (on) Color.White else C.Asphalt, fontSize = 13.5.sp,
                        fontWeight = FontWeight.SemiBold, maxLines = 1)
                }
            }
        }
    }
}

/** versionName (versionCode), e.g. 1.2.1 (10201). */
@Composable
private fun appVersion(): String {
    val context = LocalContext.current
    return remember {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        "${info.versionName} (${PackageInfoCompat.getLongVersionCode(info)})"
    }
}

@Composable
private fun TextInput(value: String, error: Boolean, keyboard: KeyboardType, width: Dp, placeholder: String? = null,
                      onChange: (String) -> Unit) {
    BasicTextField(
        value = value, onValueChange = onChange, singleLine = true,
        textStyle = TextStyle(fontSize = 17.sp, fontWeight = FontWeight.SemiBold, color = C.Asphalt, textAlign = TextAlign.End,
            fontFeatureSettings = "tnum"),
        keyboardOptions = KeyboardOptions(keyboardType = keyboard),
        cursorBrush = SolidColor(C.Asphalt),
        decorationBox = { inner ->
            Box(
                Modifier.width(width).heightIn(min = 42.dp)
                    .border(if (error) 2.dp else 1.5.dp, if (error) C.Stop else C.InputLine, RoundedCornerShape(4.dp))
                    .padding(horizontal = 10.dp),
                contentAlignment = Alignment.CenterEnd,
            ) {
                if (value.isEmpty() && placeholder != null) Text(placeholder, color = C.Faint, fontSize = 17.sp)
                inner()
            }
        },
    )
}

@Composable
private fun NumberField(value: String, error: Boolean, onChange: (String) -> Unit) {
    TextInput(value, error, KeyboardType.Number, 120.dp) { t -> onChange(t.filter(Char::isDigit).take(5)) }
}

/** − value +, the buttons 44 × 44 with a dark outline. */
@Composable
private fun Stepper(value: String, onMinus: () -> Unit, onPlus: () -> Unit) {
    val less = stringResource(R.string.decrease)
    val more = stringResource(R.string.increase)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        StepButton("−", less, onMinus)
        Text(value, Modifier.widthIn(min = 54.dp), color = C.Asphalt, fontSize = 17.sp, fontWeight = FontWeight.SemiBold,
            textAlign = TextAlign.Center, style = Num)
        StepButton("+", more, onPlus)
    }
}

@Composable
private fun StepButton(glyph: String, description: String, onClick: () -> Unit) {
    Box(
        Modifier.size(44.dp).border(1.5.dp, C.Asphalt, RoundedCornerShape(6.dp))
            .clickable(role = Role.Button, onClick = onClick).semantics { contentDescription = description },
        contentAlignment = Alignment.Center,
    ) { Text(glyph, color = C.Asphalt, fontSize = 22.sp, fontWeight = FontWeight.Bold) }
}

@Composable
private fun SecondsRow(@StringRes label: Int, value: Double, range: ClosedFloatingPointRange<Double>, step: Double,
                       onChange: (Double) -> Unit) {
    // Keep the value on the step grid (0.1 s) so repeated presses do not drift.
    fun snap(v: Double) = (v * 10).roundToInt() / 10.0
    FieldRow(label) {
        Stepper(Format.number(value, 1, "s"),
            onMinus = { onChange(snap((value - step).coerceIn(range.start, range.endInclusive))) },
            onPlus = { onChange(snap((value + step).coerceIn(range.start, range.endInclusive))) })
    }
}

/** A hint on the left, its button on the right (outlined in `color`). */
@Composable
private fun ActionRow(@StringRes hint: Int, @StringRes button: Int, color: Color, onClick: () -> Unit) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(stringResource(hint), Modifier.weight(1f), color = C.Text2, fontSize = 14.sp, lineHeight = 19.sp)
        Box(
            Modifier.heightIn(min = 44.dp).border(1.5.dp, color, RoundedCornerShape(4.dp))
                .clickable(role = Role.Button, onClick = onClick).padding(horizontal = 12.dp),
            contentAlignment = Alignment.Center,
        ) { Text(stringResource(button), color = color, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1) }
    }
}

