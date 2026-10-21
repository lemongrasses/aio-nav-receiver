package com.lemongrass.aionav.monitor

import android.content.Context
import com.lemongrass.aionav.core.Counters
import com.lemongrass.aionav.core.GateConfig
import com.lemongrass.aionav.core.Monitor
import com.lemongrass.aionav.core.NavPacket
import com.lemongrass.aionav.core.StatusPacket
import com.lemongrass.aionav.core.Verdict
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

data class MonitorSnapshot(
    val verdict: Verdict = Verdict.NO_STATUS,
    val nav: NavPacket? = null,
    val navAge: Double? = null,
    val status: StatusPacket? = null,
    val statusAge: Double? = null,
    val counts: Counters = Counters(),
    val navSender: String? = null,
    val statusSender: String? = null,
    val navRateHz: Double = 0.0,
    val statusRateHz: Double = 0.0,
    /** Exact: the Monitor sums it between verdict changes. */
    val usableSeconds: Double = 0.0,
)

/** A port that could not be bound; the screen words it in the current language (ui/Words.bindError). */
data class ListenFailure(val port: Int, val errno: Int?, val text: String)

/** `start`/`end` in wall-clock milliseconds. `state` is the dashboard state, or NO_STATUS. */
data class TimelineSegment(val start: Long, val end: Long, val usable: Boolean, val state: String)

/** Navigation values sampled at 2 Hz while 0x04 is arriving. */
data class NavSample(
    val time: Long,
    /** Increases after a gap so chart lines break instead of bridging it. */
    val run: Int,
    val lat: Double,
    val lon: Double,
    val height: Double,
    val speed: Double,
    val heading: Double,
    val sigmaN: Double,
    val sigmaE: Double,
    val sigmaD: Double,
    val sigmaHeading: Double,
    val usable: Boolean,
)

/** Link health sampled at 2 Hz whether or not anything arrives. */
data class LinkSample(val time: Long, val rateHz: Double, val navAgeMs: Double?)

data class History(
    val timeline: List<TimelineSegment> = emptyList(),
    val nav: List<NavSample> = emptyList(),
    val link: List<LinkSample> = emptyList(),
)

/** The gate behind a lock: the receiver threads feed it, the tick reads it. */
class MonitorEngine(cfg: GateConfig) {
    private val monitor = Monitor(cfg)

    fun ingest(bytes: ByteArray, sender: String?, arrival: Double) {
        synchronized(this) { monitor.feed(bytes, arrival, sender) }
    }

    fun snapshot(now: Double): MonitorSnapshot = synchronized(this) {
        monitor.advance(now)
        val g = monitor.gate
        MonitorSnapshot(
            verdict = monitor.verdict ?: Verdict.NO_STATUS,
            nav = g.nav, navAge = g.nav?.let { now - g.navAt },
            status = g.status, statusAge = g.status?.let { now - g.statusAt },
            counts = g.count.copy(), navSender = monitor.navSender, statusSender = monitor.statusSender,
            navRateHz = monitor.navRate(now), statusRateHz = monitor.statusRate(now),
            usableSeconds = monitor.usableTotal,
        )
    }
}

/**
 * The app's one monitor: receiver, gate, a snapshot every 100 ms (spec: recompute the verdict every
 * 100 ms) and the last ten minutes of history for the charts and the track. MonitorService starts and
 * stops it; the screens only read the flows.
 */
object MonitorStore {
    const val HISTORY_MS = 10 * 60 * 1000L
    const val TICK_MS = 100L
    const val SAMPLE_MS = 500L

    private lateinit var appContext: Context
    private val _settings = MutableStateFlow(MonitorSettings())
    private val _snapshot = MutableStateFlow(MonitorSnapshot())
    private val _history = MutableStateFlow(History())
    private val _listening = MutableStateFlow(false)
    private val _listenError = MutableStateFlow<ListenFailure?>(null)

    val settings: StateFlow<MonitorSettings> = _settings.asStateFlow()
    val snapshot: StateFlow<MonitorSnapshot> = _snapshot.asStateFlow()
    val history: StateFlow<History> = _history.asStateFlow()
    val listening: StateFlow<Boolean> = _listening.asStateFlow()
    val listenError: StateFlow<ListenFailure?> = _listenError.asStateFlow()

    // Touched on the tick thread only (and under `this` for start/stop/reset).
    private var engine = MonitorEngine(GateConfig())
    private var receiver: UdpReceiver? = null
    private var executor: ScheduledExecutorService? = null
    private var tick: ScheduledFuture<*>? = null
    private val timeline = ArrayList<TimelineSegment>()
    private val navSamples = ArrayDeque<NavSample>()
    private val linkSamples = ArrayDeque<LinkSample>()
    private var lastSampleAt = 0L
    private var run = 0

    @Synchronized
    fun init(context: Context) {
        if (::appContext.isInitialized) return
        appContext = context.applicationContext
        _settings.value = MonitorSettings.load(appContext)
        engine = MonitorEngine(_settings.value.gateConfig())
    }

    @Synchronized
    fun start() {
        if (tick != null) return
        val e = engine
        try {
            receiver = UdpReceiver(_settings.value.ports) { bytes, sender, arrival -> e.ingest(bytes, sender, arrival) }
            _listening.value = true
            _listenError.value = null
        } catch (err: UdpReceiver.BindError) {
            _listening.value = false
            _listenError.value = ListenFailure(err.port, err.errno, err.cause?.message ?: "")
        }
        val ex = executor ?: Executors.newSingleThreadScheduledExecutor { r -> Thread(r, "MonitorTick") }
        executor = ex
        tick = ex.scheduleWithFixedDelay(::onTick, 0, TICK_MS, TimeUnit.MILLISECONDS)
    }

    @Synchronized
    fun stop() {
        receiver?.stop()
        receiver = null
        tick?.cancel(false)
        tick = null
        _listening.value = false
    }

    val isRunning: Boolean @Synchronized get() = tick != null

    /** Saves new settings; a change to ports, ids, source or rules restarts with a fresh gate. */
    @Synchronized
    fun apply(new: MonitorSettings) {
        val restart = new.needsRestart(_settings.value)
        _settings.value = new
        new.save(appContext)
        if (restart) reset()
    }

    /** Starts over with a fresh gate, statistics and history (and keeps running if it was). */
    @Synchronized
    fun reset() {
        val wasRunning = tick != null
        stop()
        executor?.submit {}?.get()                  // let a tick in progress finish first
        engine = MonitorEngine(_settings.value.gateConfig())
        timeline.clear()
        navSamples.clear()
        linkSamples.clear()
        run += 1
        _history.value = History()
        _snapshot.value = MonitorSnapshot()
        if (wasRunning) start()
    }

    private fun onTick() {
        val now = UdpReceiver.now()
        val wall = System.currentTimeMillis()
        val snap = engine.snapshot(now)
        _snapshot.value = snap
        recordTimeline(snap, wall)
        if (wall - lastSampleAt >= SAMPLE_MS) {
            lastSampleAt = wall
            recordSamples(snap, wall)
            val cutoff = wall - HISTORY_MS
            timeline.removeAll { it.end < cutoff }
            while (navSamples.firstOrNull()?.let { it.time < cutoff } == true) navSamples.removeFirst()
            while (linkSamples.firstOrNull()?.let { it.time < cutoff } == true) linkSamples.removeFirst()
            _history.value = History(timeline.toList(), navSamples.toList(), linkSamples.toList())
        }
    }

    private fun recordTimeline(snap: MonitorSnapshot, wall: Long) {
        val usable = snap.verdict.usable
        val state = if (snap.verdict == Verdict.NO_STATUS) "NO_STATUS" else snap.status?.stateName ?: "NO_STATUS"
        val last = timeline.lastOrNull()
        if (last != null && last.usable == usable && last.state == state) {
            timeline[timeline.size - 1] = last.copy(end = wall)
        } else {
            timeline += TimelineSegment(last?.end ?: wall, wall, usable, state)
        }
    }

    private fun recordSamples(snap: MonitorSnapshot, wall: Long) {
        linkSamples += LinkSample(wall, snap.navRateHz, snap.navAge?.let { minOf(it * 1000, 5000.0) })
        val n = snap.nav ?: return
        val age = snap.navAge ?: return
        if (age >= 1.0 || !n.isFinite || Math.abs(n.lat) > 90 || Math.abs(n.lon) > 180) return
        val last = navSamples.lastOrNull()
        if (last != null && wall - last.time > 3 * SAMPLE_MS) run += 1
        navSamples += NavSample(
            wall, run, n.lat, n.lon, n.height.toDouble(), n.groundSpeed, n.heading360,
            n.posNStd.toDouble(), n.posEStd.toDouble(), n.posDStd.toDouble(), n.headingStd.toDouble(),
            snap.verdict.usable,
        )
    }
}
