package com.lemongrass.aionav.monitor

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.content.res.Configuration
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.LocaleList
import android.os.PowerManager
import android.util.Log
import androidx.appcompat.app.AppCompatDelegate
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.lemongrass.aionav.MainActivity
import com.lemongrass.aionav.R
import com.lemongrass.aionav.core.Verdict
import com.lemongrass.aionav.ui.Kind
import com.lemongrass.aionav.ui.Presentation
import com.lemongrass.aionav.ui.Words
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

/**
 * Keeps monitoring while the app is not on screen (iOS cannot do this): a foreground service of type
 * connectedDevice (the phone receives from an external device, the Jetson, over Wi-Fi) with an ongoing
 * notification that shows 可用 / 不可用. A partial wake lock and a Wi-Fi lock keep 100 Hz arriving with the
 * screen off.
 */
/** What the notification says: it is re-posted only when this changes. */
private data class NotificationKey(val verdict: Verdict, val state: Int?, val action: Int?, val kind: Kind)

class MonitorService : Service() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private var wifi: WifiKeeper? = null
    private var started = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }
        if (intent?.action == ACTION_REFRESH && started) {      // the language changed
            getSystemService(NotificationManager::class.java).notify(NOTIFICATION_ID, notification(MonitorStore.snapshot.value))
            return START_STICKY
        }
        MonitorStore.init(this)
        ServiceCompat.startForeground(this, NOTIFICATION_ID, notification(MonitorStore.snapshot.value),
            if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE else 0)
        if (!started) {
            started = true
            acquireLocks()
            wifi = WifiKeeper(this).also { it.start() }
            MonitorStore.start()
            val nm = getSystemService(NotificationManager::class.java)
            scope.launch {
                // Re-post only when what the notification says changes.
                MonitorStore.snapshot
                    .map { NotificationKey(it.verdict, it.status?.state, it.status?.action, Presentation.band(it).kind) }
                    .distinctUntilChanged()
                    .collect { key ->
                        Log.i(TAG, "verdict ${key.verdict.reason} ${key.verdict.legacyText} (state ${key.state ?: "-"}, ${key.kind})")
                        nm.notify(NOTIFICATION_ID, notification(MonitorStore.snapshot.value))
                    }
            }
        }
        return START_STICKY
    }

    override fun onDestroy() {
        scope.cancel()
        MonitorStore.stop()
        wifi?.stop()
        wakeLock?.takeIf { it.isHeld }?.release()
        wifiLock?.takeIf { it.isHeld }?.release()
        super.onDestroy()
    }

    @SuppressLint("WakelockTimeout")
    private fun acquireLocks() {
        wakeLock = getSystemService(PowerManager::class.java)
            .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "aionav:monitor").apply { acquire() }
        @Suppress("DEPRECATION")
        wifiLock = getSystemService(WifiManager::class.java)
            .createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "aionav:monitor").apply { acquire() }
    }

    /** This context in the language chosen in Settings (before Android 13 a service does not get it by itself). */
    private fun localized(): Context {
        val chosen = AppCompatDelegate.getApplicationLocales()
        if (chosen.isEmpty) return this
        val config = Configuration(resources.configuration)
        config.setLocales(LocaleList.forLanguageTags(chosen.toLanguageTags()))
        return createConfigurationContext(config)
    }

    private fun notification(snap: MonitorSnapshot): Notification {
        ensureChannel(this)
        val ctx = localized()
        val res = ctx.resources
        val usable = snap.verdict.usable
        val open = PendingIntent.getActivity(this, 0, Intent(this, MainActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 1, Intent(this, MonitorService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE)
        val title = res.getString(if (usable) R.string.usable else R.string.blocked) +
            (snap.status?.let { " · ${Words.state(res, it.state)}" } ?: "")
        val lines = listOfNotNull(
            if (usable) null else Words.reason(res, snap.verdict),
            snap.status?.let { Words.instruction(res, it.action) },
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(if (usable) R.drawable.ic_stat_usable else R.drawable.ic_stat_blocked)
            .setContentTitle(title)
            .setContentText(lines.joinToString(" — "))
            .setStyle(NotificationCompat.BigTextStyle().bigText(lines.joinToString("\n")))
            // The four signal classes, as on the screen (layout C, decision D4: only the colour changes).
            .setColor(ContextCompat.getColor(this, when (Presentation.band(snap).kind) {
                Kind.GO -> R.color.signal_go
                Kind.WAIT -> R.color.signal_wait
                Kind.STOP -> R.color.signal_stop
                Kind.IDLE -> R.color.signal_idle
            }))
            .setColorized(true)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setSilent(true)
            .setCategory(NotificationCompat.CATEGORY_STATUS)
            .setForegroundServiceBehavior(NotificationCompat.FOREGROUND_SERVICE_IMMEDIATE)
            .setContentIntent(open)
            .addAction(0, res.getString(R.string.stop_monitoring), stop)
            .build()
    }

    companion object {
        private const val TAG = "AioNav"
        private const val CHANNEL_ID = "monitor"
        private const val NOTIFICATION_ID = 1
        private const val ACTION_STOP = "com.lemongrass.aionav.STOP"
        private const val ACTION_REFRESH = "com.lemongrass.aionav.REFRESH"

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, MonitorService::class.java))
        }

        /** Re-post the notification, e.g. in a newly chosen language (only if the service runs). */
        fun refresh(context: Context) {
            if (MonitorStore.isRunning) {
                context.startService(Intent(context, MonitorService::class.java).setAction(ACTION_REFRESH))
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, MonitorService::class.java))
        }

        private fun ensureChannel(context: Context) {
            val nm = context.getSystemService(NotificationManager::class.java)
            if (nm.getNotificationChannel(CHANNEL_ID) != null) return
            nm.createNotificationChannel(NotificationChannel(CHANNEL_ID, context.getString(R.string.channel_monitor),
                NotificationManager.IMPORTANCE_LOW).apply {
                description = context.getString(R.string.channel_monitor_description)
                setShowBadge(false)
            })
        }
    }
}
