package com.lemongrass.aionav.monitor

import android.content.Context
import androidx.core.content.edit
import com.lemongrass.aionav.core.Aio
import com.lemongrass.aionav.core.GateConfig

/** Receiver settings (spec "設定"); stored in SharedPreferences. */
data class MonitorSettings(
    /** Must match the port the Jetson relay (or output_udp) sends 0x04 to. */
    val navPort: Int = 9000,
    /** Only when status_udp.destination points at another port; null = same as navPort. */
    val statusPort: Int? = null,
    /** status_udp.message_id. */
    val statusMessageId: Int = Aio.STATUS_ID,
    /** Only packets from this IPv4 address are used; others are only counted. Empty = any. */
    val allowedSourceIp: String = "",
    val statusTimeout: Double = 3.0,
    val readyStable: Double = 2.0,
    val navMaxAge: Double = 0.5,
    val keepScreenOn: Boolean = true,
    /** Keep receiving in a foreground service while the app is not on screen. */
    val background: Boolean = true,
) {
    val ports: List<Int> get() = listOf(navPort, statusPort ?: navPort).distinct().sorted()

    val allowedSource: String? get() = allowedSourceIp.trim().ifEmpty { null }

    fun gateConfig() = GateConfig(statusMessageId, allowedSource, statusTimeout, readyStable, navMaxAge)

    /** Settings whose change needs a new receiver and gate (and so clears the history). */
    fun needsRestart(other: MonitorSettings): Boolean =
        copy(keepScreenOn = false, background = false) != other.copy(keepScreenOn = false, background = false)

    val isValid: Boolean
        get() = navPort in 1..65535 && (statusPort ?: 1) in 1..65535 && statusMessageId in 1..255 &&
            (allowedSource?.let(::isIPv4) ?: true)

    fun save(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit {
            putInt("navPort", navPort)
            putInt("statusPort", statusPort ?: 0)
            putInt("statusMessageId", statusMessageId)
            putString("allowedSourceIp", allowedSourceIp.trim())
            putFloat("statusTimeout", statusTimeout.toFloat())
            putFloat("readyStable", readyStable.toFloat())
            putFloat("navMaxAge", navMaxAge.toFloat())
            putBoolean("keepScreenOn", keepScreenOn)
            putBoolean("background", background)
        }
    }

    companion object {
        private const val PREFS = "monitorSettings"

        fun load(context: Context): MonitorSettings {
            val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            val d = MonitorSettings()
            // Stored as Float: round back to the 0.1 s steps the screen offers.
            fun seconds(key: String, default: Double) =
                Math.round(p.getFloat(key, default.toFloat()) * 10.0) / 10.0
            return MonitorSettings(
                navPort = p.getInt("navPort", d.navPort),
                statusPort = p.getInt("statusPort", 0).takeIf { it > 0 },
                statusMessageId = p.getInt("statusMessageId", d.statusMessageId),
                allowedSourceIp = p.getString("allowedSourceIp", d.allowedSourceIp) ?: "",
                statusTimeout = seconds("statusTimeout", d.statusTimeout),
                readyStable = seconds("readyStable", d.readyStable),
                navMaxAge = seconds("navMaxAge", d.navMaxAge),
                keepScreenOn = p.getBoolean("keepScreenOn", d.keepScreenOn),
                background = p.getBoolean("background", d.background),
            ).takeIf { it.isValid } ?: d
        }

        /** Dotted-quad IPv4, four numbers 0-255 (what the gate compares the sender with). */
        fun isIPv4(text: String): Boolean {
            val parts = text.split(".")
            return parts.size == 4 && parts.all { p ->
                p.length in 1..3 && p.all(Char::isDigit) && p.toInt() <= 255 && (p.length == 1 || p[0] != '0')
            }
        }
    }
}
