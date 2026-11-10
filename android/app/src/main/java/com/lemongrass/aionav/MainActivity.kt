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
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.PathParser
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.core.view.WindowCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LifecycleEventEffect
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.lemongrass.aionav.monitor.MonitorService
import com.lemongrass.aionav.monitor.MonitorStore
import com.lemongrass.aionav.monitor.UdpReceiver
import com.lemongrass.aionav.monitor.WifiKeeper
import com.lemongrass.aionav.ui.AioTheme
import com.lemongrass.aionav.ui.C
import com.lemongrass.aionav.ui.ChartsScreen
import com.lemongrass.aionav.ui.Kind
import com.lemongrass.aionav.ui.Presentation
import com.lemongrass.aionav.ui.SettingsScreen
import com.lemongrass.aionav.ui.StatusScreen
import com.lemongrass.aionav.ui.TrackScreen

/** A tab icon from the design's 22×22 stroke drawings (docs/UI-PHONE-C.zh-TW.md 4.0). */
private fun tabIcon(name: String, strokes: List<String>, fills: List<String> = emptyList()): ImageVector =
    ImageVector.Builder(name, 24.dp, 24.dp, 22f, 22f).apply {
        strokes.forEach {
            addPath(PathParser().parsePathString(it).toNodes(), stroke = SolidColor(Color.Black), strokeLineWidth = 2f,
                strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round)
        }
        fills.forEach { addPath(PathParser().parsePathString(it).toNodes(), fill = SolidColor(Color.Black)) }
    }.build()

private fun dot(x: Float, y: Float, r: Float) = "M${x - r},$y a$r,$r 0 1,0 ${2 * r},0 a$r,$r 0 1,0 ${-2 * r},0 Z"

/** The status tab: a signal mast, three lamps stacked. */
private val MastIcon = tabIcon("Mast", listOf("M9,1.5 H13 A3,3 0 0 1 16,4.5 V17.5 A3,3 0 0 1 13,20.5 H9 A3,3 0 0 1 6,17.5 V4.5 A3,3 0 0 1 9,1.5 Z"),
    listOf(dot(11f, 6.5f, 2f), dot(11f, 11f, 2f), dot(11f, 15.5f, 2f)))
private val ChartIcon = tabIcon("Chart", listOf("M3,17 L8,11 L12,14 L19,5"))
private val TrackIcon = tabIcon("Track", listOf("M11,20 C11,20 4,13 4,8.5 A7,7 0 0 1 18,8.5 C18,13 11,20 11,20 Z"), listOf(dot(11f, 8.5f, 2.5f)))
private val SettingsIcon = tabIcon("Settings", listOf(dot(11f, 11f, 3f),
    "M11,2 V5 M11,17 V20 M2,11 H5 M17,11 H20 M4.6,4.6 L6.7,6.7 M15.3,15.3 L17.4,17.4 M4.6,17.4 L6.7,15.3 M15.3,6.7 L17.4,4.6"))

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
    STATUS(R.string.tab_status, MastIcon),
    CHARTS(R.string.tab_charts, ChartIcon),
    TRACK(R.string.tab_track, TrackIcon),
    SETTINGS(R.string.tab_settings, SettingsIcon),
}

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
    val kind = Presentation.band(snapshot).kind
    // The status tab's top is the signal colour: dark status-bar icons on yellow only; the other tabs' headers are dark.
    val view = LocalView.current
    SideEffect {
        WindowCompat.getInsetsController(window, view).apply {
            isAppearanceLightStatusBars = Tab.entries[tab] == Tab.STATUS && kind == Kind.WAIT
            isAppearanceLightNavigationBars = false
        }
    }

    // No top bar: the status tab's verdict band is its header, the other tabs draw a dark one (PageHeader).
    Scaffold(
        containerColor = C.Kerb,
        bottomBar = {
            NavigationBar(containerColor = C.Asphalt) {
                Tab.entries.forEachIndexed { i, t ->
                    NavigationBarItem(
                        selected = tab == i, onClick = { tab = i },
                        icon = { Icon(t.icon, null) },
                        label = { Text(stringResource(t.label), fontWeight = if (tab == i) FontWeight.Bold else FontWeight.Normal) },
                        colors = NavigationBarItemDefaults.colors(
                            selectedIconColor = Color.White, selectedTextColor = Color.White, indicatorColor = C.LampOff,
                            unselectedIconColor = C.TabOff, unselectedTextColor = C.TabOff,
                        ),
                    )
                }
            }
        },
    ) { padding ->
        Box(Modifier.padding(bottom = padding.calculateBottomPadding())) {
            when (Tab.entries[tab]) {
                Tab.STATUS -> StatusScreen(snapshot, settings, listening, listenError, addresses.firstOrNull()) {
                    MonitorService.start(this@App)
                }
                Tab.CHARTS -> ChartsScreen(history, snapshot, kind)
                Tab.TRACK -> TrackScreen(history.nav, snapshot, kind)
                Tab.SETTINGS -> SettingsScreen(settings, listening, addresses, wifi, !notificationsGranted,
                    onApply = { MonitorStore.apply(it) }, onClear = { MonitorStore.reset() })
            }
        }
    }
}
