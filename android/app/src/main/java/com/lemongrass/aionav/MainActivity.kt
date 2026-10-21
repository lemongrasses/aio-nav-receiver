package com.lemongrass.aionav

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.appcompat.app.AppCompatActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.LocationOn
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.materialIcon
import androidx.compose.material.icons.materialPath
import androidx.compose.material3.CenterAlignedTopAppBar
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.res.stringResource
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.lemongrass.aionav.monitor.MonitorService
import com.lemongrass.aionav.monitor.MonitorStore
import com.lemongrass.aionav.monitor.UdpReceiver
import com.lemongrass.aionav.monitor.WifiKeeper
import com.lemongrass.aionav.ui.AioTheme
import com.lemongrass.aionav.ui.ChartsScreen
import com.lemongrass.aionav.ui.SettingsScreen
import com.lemongrass.aionav.ui.StatusScreen
import com.lemongrass.aionav.ui.TrackScreen

/** Material "show_chart" (not in the core icon set). */
private val ChartIcon: ImageVector = materialIcon("ShowChart") {
    materialPath {
        moveTo(3.5f, 18.49f); lineTo(9.5f, 12.48f); lineTo(13.5f, 16.48f); lineTo(22f, 6.92f)
        lineTo(20.59f, 5.51f); lineTo(13.5f, 13.48f); lineTo(9.5f, 9.48f); lineTo(2f, 16.99f); close()
    }
}

class MainActivity : AppCompatActivity() {
    private val notificationPermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted -> notificationsGranted.value = granted }
    private val notificationsGranted = mutableStateOf(true)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        MonitorStore.init(this)
        if (Build.VERSION.SDK_INT >= 33 &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            notificationPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
        }
        setContent { AioTheme { App(notificationsGranted.value) } }
    }

    override fun onStart() {
        super.onStart()
        MonitorService.start(this)
        notificationsGranted.value = NotificationManagerCompat.from(this).areNotificationsEnabled()
    }

    override fun onStop() {
        super.onStop()
        // Without background monitoring, behave like the iOS app: receive only while on screen.
        if (!MonitorStore.settings.value.background && !isChangingConfigurations) MonitorService.stop(this)
    }

    fun setKeepScreenOn(on: Boolean) {
        if (on) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }
}

private enum class Tab(val label: Int, val icon: ImageVector) {
    STATUS(R.string.tab_status, Icons.Filled.CheckCircle),
    CHARTS(R.string.tab_charts, ChartIcon),
    TRACK(R.string.tab_track, Icons.Filled.LocationOn),
    SETTINGS(R.string.tab_settings, Icons.Filled.Settings),
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun MainActivity.App(notificationsGranted: Boolean) {
    var tab by rememberSaveable { mutableIntStateOf(0) }
    val settings by MonitorStore.settings.collectAsStateWithLifecycle()
    val snapshot by MonitorStore.snapshot.collectAsStateWithLifecycle()
    val history by MonitorStore.history.collectAsStateWithLifecycle()
    val listening by MonitorStore.listening.collectAsStateWithLifecycle()
    val listenError by MonitorStore.listenError.collectAsStateWithLifecycle()
    val wifi by WifiKeeper.state.collectAsStateWithLifecycle()
    // Re-read the interface addresses when the network or the receiver changes, and on return to the app.
    var resumed by remember { mutableIntStateOf(0) }
    LifecycleEventEffect(Lifecycle.Event.ON_RESUME) { resumed++ }
    val addresses = remember(wifi, listening, resumed) { UdpReceiver.localAddresses() }
    setKeepScreenOn(settings.keepScreenOn && listening)

    Scaffold(
        topBar = { CenterAlignedTopAppBar(title = { Text(stringResource(if (tab == 0) R.string.app_name else Tab.entries[tab].label)) }) },
        bottomBar = {
            NavigationBar {
                Tab.entries.forEachIndexed { i, t ->
                    NavigationBarItem(selected = tab == i, onClick = { tab = i },
                        icon = { Icon(t.icon, null) }, label = { Text(stringResource(t.label)) })
                }
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding)) {
            when (Tab.entries[tab]) {
                Tab.STATUS -> StatusScreen(snapshot, settings, listening, listenError, addresses.firstOrNull()) {
                    MonitorService.start(this@App)
                }
                Tab.CHARTS -> ChartsScreen(history, settings.navMaxAge)
                Tab.TRACK -> TrackScreen(history.nav, snapshot)
                Tab.SETTINGS -> SettingsScreen(settings, listening, addresses, wifi, !notificationsGranted,
                    onApply = { MonitorStore.apply(it) }, onClear = { MonitorStore.reset() })
            }
        }
    }
}
