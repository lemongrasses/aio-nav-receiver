// What the screen says for each situation: the desktop's tests/test_presentation.py, case by case, on the same
// packet streams. The text is rendered from values-zh-rTW/strings.xml, so the sentences are compared as shown.

package com.lemongrass.aionav.ui

import com.lemongrass.aionav.R
import com.lemongrass.aionav.core.Aio
import com.lemongrass.aionav.core.GateConfig
import com.lemongrass.aionav.monitor.MonitorEngine
import com.lemongrass.aionav.monitor.MonitorSnapshot
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element
import java.io.File
import java.util.Locale
import javax.xml.parsers.DocumentBuilderFactory

/** Txt rendered as the app shows it in 繁體中文, from the resource files (no Android runtime in a unit test). */
object Zh {
    private val doc = DocumentBuilderFactory.newInstance().newDocumentBuilder()
        .parse(File("src/main/res/values-zh-rTW/strings.xml"))

    private fun elements(tag: String) = doc.getElementsByTagName(tag).let { n -> (0 until n.length).map { n.item(it) as Element } }

    private fun shown(raw: String) = raw.removeSurrounding("\"").replace("\\'", "'").replace("\\\"", "\"")

    private val strings = elements("string").associate { it.getAttribute("name") to shown(it.textContent) }
    private val arrays = elements("string-array").associate { a ->
        a.getAttribute("name") to a.getElementsByTagName("item").let { n -> (0 until n.length).map { shown(n.item(it).textContent) } }
    }
    private val stringNames = R.string::class.java.fields.associate { it.getInt(null) to it.name }
    private val arrayNames = R.array::class.java.fields.associate { it.getInt(null) to it.name }

    fun text(t: Txt): String = when (t) {
        is Txt.Res -> {
            val pattern = strings.getValue(stringNames.getValue(t.id))
            if (t.args.isEmpty()) pattern
            else String.format(Locale.ROOT, pattern, *t.args.map { if (it is Txt) text(it) else it }.toTypedArray())
        }
        is Txt.Item -> arrays.getValue(arrayNames.getValue(t.id))[t.index]
    }
}

class PresentationTest {
    private val aligned = 0b1110_0000

    private fun nav(t: Double) = Aio.encodeNav(t, 23.0, 120.0, flags = aligned)

    private fun status(seq: Long, state: Int = Aio.READY, inhibit: Long = 0, action: Int = 0) =
        Aio.encodeStatus(state, action, session = 1, sequence = seq, inhibit = inhibit)

    /** The desktop's ready_monitor: 0x05 in `state` (asking for `action`) at 2 Hz and 0x04 at 100 Hz from t=0. */
    private fun readyEngine(seconds: Double = 3.0, state: Int = 6, action: Int = 0): MonitorEngine {
        val e = MonitorEngine(GateConfig())
        for (i in 0 until (seconds * 100).toInt()) {
            val t = i / 100.0
            if (i % 50 == 0) e.ingest(status(i / 50 + 1L, state = state, action = action), "192.168.116.1", t)
            e.ingest(nav(10.0 + t), "192.168.116.1", t)
        }
        return e
    }

    private fun empty(): MonitorSnapshot = MonitorEngine(GateConfig()).snapshot(0.0)

    private fun Presentation.Band.shown() = Triple(kind, Zh.text(word), Zh.text(headline))

    @Test
    fun bandKinds() {
        assertEquals(Triple(Kind.IDLE, "不可用", "還沒收到任何封包"), Presentation.band(empty()).shown())
        assertEquals(Kind.GO, Presentation.band(readyEngine().snapshot(2.99)).kind)
        for ((state, kind) in listOf("KEEP_STILL" to Kind.WAIT, "REFINING" to Kind.WAIT, "BOOTING" to Kind.WAIT,
                "DEGRADED" to Kind.STOP, "FAULT" to Kind.STOP, "MAINTENANCE" to Kind.IDLE)) {
            assertEquals(state, kind, Presentation.band(readyEngine(state = Aio.STATES.indexOf(state)).snapshot(2.99)).kind)
        }
        assertEquals(Triple(Kind.WAIT, "不可用", "就緒確認中（需穩定 2 秒）"),
            Presentation.band(readyEngine(1.5).snapshot(1.49)).shown())
        val stale = Presentation.band(readyEngine().snapshot(3.6))
        assertTrue(stale.kind == Kind.STOP && "0x04 中斷" in Zh.text(stale.headline))
        val lost = Presentation.band(readyEngine().snapshot(8.0))
        assertTrue(lost.kind == Kind.STOP && "0x05 中斷超過 3 秒" in Zh.text(lost.headline))
        // The desktop's band(snap, failure) case: Android shows a bind failure beside the verdict instead.
    }

    @Test
    fun navWithoutStatus() {
        val e = MonitorEngine(GateConfig())
        e.ingest(nav(1.0), "a", 0.0)
        assertEquals(Triple(Kind.STOP, "不可用", "沒有狀態封包 0x05"), Presentation.band(e.snapshot(0.1)).shown())
    }

    @Test
    fun rail() {
        val straight = Presentation.rail(readyEngine(state = Aio.STATES.indexOf("MOVE_STRAIGHT")).snapshot(2.99))
        assertEquals(2 to Presentation.RailMode.PROGRESS, straight.at to straight.mode)
        val done = Presentation.rail(readyEngine().snapshot(2.99))
        assertEquals(4 to Presentation.RailMode.DONE, done.at to done.mode)
        val settling = Presentation.rail(readyEngine(1.5).snapshot(1.49))
        assertTrue(settling.at == 4 && settling.mode == Presentation.RailMode.PROGRESS && Math.abs(settling.fraction - 0.745) < 0.01)
        val degraded = Presentation.rail(readyEngine(state = Aio.STATES.indexOf("DEGRADED")).snapshot(2.99))
        assertEquals(4 to Presentation.RailMode.LOST, degraded.at to degraded.mode)
        val fault = Presentation.rail(readyEngine(state = Aio.STATES.indexOf("FAULT")).snapshot(2.99))
        assertEquals(-1 to Presentation.RailMode.FAULT, fault.at to fault.mode)
        assertEquals(Presentation.RailMode.NONE, Presentation.rail(readyEngine().snapshot(8.0)).mode)   // 0x05 timed out
        assertNull(Presentation.rail(empty()).note)                                                     // nothing yet: no note
    }

    @Test
    fun linksAndAges() {
        val s = readyEngine().snapshot(2.99)
        val nav = Presentation.navLink(s)
        assertTrue(nav.kind == Kind.GO && "Hz" in Zh.text(nav.text))
        assertEquals(Kind.GO to "2.0 Hz   0.5 秒前", Presentation.statusLink(s).let { it.kind to Zh.text(it.text) })
        val gone = s.copy(navAge = s.navAge!! + 75)
        assertEquals(Kind.STOP to "中斷 1 分 15 秒", Presentation.navLink(gone).let { it.kind to Zh.text(it.text) })
        assertEquals(Kind.IDLE to "沒有資料",
            Presentation.statusLink(s.copy(status = null, statusAge = null)).let { it.kind to Zh.text(it.text) })
        val e = MonitorEngine(GateConfig())
        e.ingest(status(1), "a", 0.0)
        assertEquals(Kind.IDLE to "沒有資料", Presentation.navLink(e.snapshot(0.1)).let { it.kind to Zh.text(it.text) })
        assertEquals("1 小時 6 分", Zh.text(Presentation.fmtAge(4000.0)))
        assertEquals("1:02:05", Format.duration(3725.0))
    }

    @Test
    fun guideTellsNeverFromLost() {
        assertNull(Presentation.guide(empty()))                      // nothing yet: no plate (setup is in Settings)
        val e = MonitorEngine(GateConfig())
        e.ingest(nav(1.0), "a", 0.0)
        val never = e.snapshot(0.1)
        val g = Presentation.guide(never)!!
        assertEquals(Presentation.GuideKind.PLATE to "開啟儀表板的 0x05", g.kind to Zh.text(g.title))
        assertEquals(Kind.STOP to "從未收到", Presentation.statusLink(never).let { it.kind to Zh.text(it.text) })
        val lost = Presentation.guide(readyEngine().snapshot(8.0))!!
        val sub = Zh.text(lost.sub!!)
        assertTrue(Zh.text(lost.title) == "檢查儀表板與網路" && "已中斷 5.5 秒" in sub && "收到 6 包" in sub)
        val quiet = Presentation.guide(readyEngine().snapshot(2.99))!!
        assertEquals(Triple(Presentation.GuideKind.QUIET, "不需動作", null),
            Triple(quiet.kind, Zh.text(quiet.title), quiet.sub))
        assertEquals(Presentation.GuideKind.DANGER,
            Presentation.guide(readyEngine(state = Aio.STATES.indexOf("FAULT"), action = 4).snapshot(2.99))!!.kind)
    }

    @Test
    fun blockingConditions() {
        assertNull(Presentation.blocking(readyEngine().snapshot(8.0)))       // no current 0x05: unknown
        assertEquals(emptyList<Presentation.Chip>(), Presentation.blocking(readyEngine().snapshot(2.99)))
        val still = 1L shl Aio.INHIBIT_BITS.indexOf("KEEP_STILL_REQUIRED") or (1L shl Aio.INHIBIT_BITS.indexOf("FINE_ALIGNMENT_REQUIRED"))
        val e = MonitorEngine(GateConfig())
        e.ingest(status(1, state = Aio.STATES.indexOf("KEEP_STILL"), inhibit = still), "a", 0.0)
        assertEquals(listOf("需要保持靜止" to true, "需要精對準" to true),
            Presentation.blocking(e.snapshot(0.1))!!.map { Zh.text(it.text) to it.expected })
        val rtk = still or (1L shl Aio.INHIBIT_BITS.indexOf("RTK_CORRECTION_LOST"))
        e.ingest(status(2, state = Aio.STATES.indexOf("DEGRADED"), inhibit = rtk), "a", 0.2)
        assertEquals(listOf(false, false, false), Presentation.blocking(e.snapshot(0.3))!!.map { it.expected })
    }

    @Test
    fun conditionsUnmetFirst() {
        assertEquals(emptyList<Pair<Txt, Boolean>>(), Presentation.conditions(empty()))
        val rows = Presentation.conditions(readyEngine().snapshot(2.99))
        assertEquals(Aio.HEALTH_BITS.size, rows.size)
        val met = rows.map { it.second }
        assertEquals(met.sorted(), met)                                  // every unmet before every met
    }

    @Test
    fun snapshotCarriesTheDisplayFacts() {
        val s = readyEngine(1.5).snapshot(1.49)
        assertEquals(1.49, s.readyFor!!, 1e-9)                           // READY since t=0
        assertTrue(s.verdictFor!! in 0.0..1.49)
        assertNull(empty().readyFor)
        assertEquals(GateConfig(), s.cfg)
    }
}
