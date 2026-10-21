// One language at a time, like the desktop 1.2.0 (tests/test_i18n.py): both languages hold the same texts
// with the same arguments, the protocol vocabulary is complete and worded exactly as the desktop's
// src/aio_receiver/i18n.py (read from the source tree, like the iOS VocabularyTests), English shows no
// Chinese, and the screen never shows a raw protocol code such as KEEP_STILL_REQUIRED.

package com.lemongrass.aionav

import com.lemongrass.aionav.core.Aio
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory

class StringsTest {
    private class Table(val strings: Map<String, String>, val arrays: Map<String, List<String>>) {
        val all: Map<String, String>
            get() = strings + arrays.flatMap { (k, v) -> v.mapIndexed { i, s -> "$k[$i]" to s } }
    }

    /** The text as the app shows it: Android's resource escapes and surrounding quotes removed. */
    private fun shown(raw: String) = raw.removeSurrounding("\"").replace("\\'", "'").replace("\\\"", "\"")

    private fun load(folder: String): Table {
        val doc = DocumentBuilderFactory.newInstance().newDocumentBuilder()
            .parse(File("src/main/res/$folder/strings.xml"))
        fun elements(tag: String) = doc.getElementsByTagName(tag).let { n -> (0 until n.length).map { n.item(it) as Element } }
        return Table(
            elements("string").associate { it.getAttribute("name") to shown(it.textContent) },
            elements("string-array").associate { a ->
                a.getAttribute("name") to a.getElementsByTagName("item").let { n -> (0 until n.length).map { shown(n.item(it).textContent) } }
            },
        )
    }

    private val en = load("values")
    private val zh = load("values-zh-rTW")

    private fun args(s: String) = Regex("%\\d+\\$[sd]").findAll(s).map { it.value }.toSortedSet()

    @Test
    fun bothLanguagesHaveTheSameTextsAndArguments() {
        assertEquals(en.strings.keys, zh.strings.keys)
        assertEquals(en.arrays.mapValues { it.value.size }, zh.arrays.mapValues { it.value.size })
        for ((key, text) in en.strings) assertEquals(key, args(text), args(zh.strings.getValue(key)))
    }

    /** The desktop's i18n.py, the authority for the wording. */
    private object Desktop {
        private val dir = File(System.getProperty("fixtures.dir") ?: "../../fixtures").parentFile
        val source = File(dir, "src/aio_receiver/i18n.py").readText()
        private val pair = Regex("\\(\"((?:[^\"\\\\]|\\\\.)*)\",\\s*\"((?:[^\"\\\\]|\\\\.)*)\"\\)")

        /** The (zh, en) pairs of a table such as `_HEALTH = (...)` or `_STATES = {...}`, in source order. */
        fun table(name: String): List<Pair<String, String>> {
            val start = source.indexOf("\n$name = ")
            check(start >= 0) { "$name not in i18n.py" }
            // The table ends at a blank line or at the next top-level name.
            val end = Regex("\n\n|\n_").find(source, start + 1)?.range?.first ?: source.length
            return pair.findAll(source.substring(start, end)).map { it.groupValues[1] to it.groupValues[2] }.toList()
        }

        /** One _T message, with its {name} arguments turned into Android's %1$s, %2$s in order. */
        fun message(key: String): Pair<String, String> {
            val m = Regex("\"${Regex.escape(key)}\": " + pair.pattern).find(source) ?: error("$key not in i18n.py")
            fun android(t: String): String {
                var n = 0
                return Regex("\\{\\w+\\}").replace(t) { "%${++n}\$s" }
            }
            return android(m.groupValues[1]) to android(m.groupValues[2])
        }
    }

    @Test
    fun wordingIsTheDesktops() {
        fun same(array: String, table: String) {
            val want = Desktop.table(table)
            assertEquals(array, want.map { it.first }, zh.arrays.getValue(array))
            assertEquals(array, want.map { it.second }, en.arrays.getValue(array))
        }
        same("state_names", "_STATES")              // dict order = protocol order (checked below)
        same("action_texts", "_ACTIONS")
        same("gnss_quality_names", "_GNSS_QUALITY")
        same("health_names", "_HEALTH")
        same("inhibit_names", "_INHIBIT")
        assertEquals(Aio.STATES, Regex("\"(\\w+)\": \\(").findAll(Desktop.source.substringAfter("_STATES = {")
            .substringBefore("}")).map { it.groupValues[1] }.toList())
        val lamps = Desktop.table("_LAMPS")
        listOf("lamp_align", "lamp_heading", "lamp_fine").forEachIndexed { i, key ->
            assertEquals(key, lamps[i].first, zh.strings[key])
            assertEquals(key, lamps[i].second, en.strings[key])
        }
        val messages = mapOf(
            "usable" to "word.usable", "blocked" to "word.blocked", "reason_usable" to "reason.usable",
            "reason_no_status" to "reason.no_status", "reason_not_ready" to "reason.not_ready",
            "reason_ready_not_stable" to "reason.ready_not_stable", "reason_nav_stale" to "reason.nav_stale",
            "reason_nav_time" to "reason.nav_time_not_forward", "reason_not_aligned" to "reason.nav_not_aligned",
            "reason_not_finite" to "reason.nav_not_finite", "none" to "none", "legend_no_status" to "band.no_status",
            "fail_bind" to "fail.bind", "os_in_use" to "os.in_use", "os_denied" to "os.denied",
            "os_no_address" to "os.no_address", "os_other" to "os.other",
        )
        for ((key, desktop) in messages) {
            val (wantZh, wantEn) = Desktop.message(desktop)
            assertEquals(key, wantZh, zh.strings[key])
            assertEquals(key, wantEn, en.strings[key])
        }
        assertEquals("、", zh.strings["list_separator"])        // i18n.joined
        assertEquals(", ", en.strings["list_separator"])       // quoted in the XML to keep the space
    }

    @Test
    fun vocabularyCoversEveryCode() {
        for (t in listOf(en, zh)) {
            assertEquals(Aio.STATES.size, t.arrays.getValue("state_names").size)
            assertEquals(Aio.ACTIONS.size, t.arrays.getValue("action_texts").size)
            assertEquals(Aio.GNSS_QUALITY.size, t.arrays.getValue("gnss_quality_names").size)
            assertEquals(Aio.HEALTH_BITS.size, t.arrays.getValue("health_names").size)
            assertEquals(Aio.INHIBIT_BITS.size, t.arrays.getValue("inhibit_names").size)
        }
    }

    @Test
    fun englishHasNoChinese() {
        val han = Regex("\\p{IsHan}")
        // A language's own name is written in that language.
        val bad = en.all.filter { (k, v) -> k != "language_zh" && han.containsMatchIn(v) }
        assertTrue("$bad", bad.isEmpty())
    }

    @Test
    fun chineseHasNoEnglishSentences() {
        // Acronyms, product names, units and config keys stay; English words of three or more lower-case letters
        // in a row (outside config keys like status_udp.enabled) mean an untranslated phrase.
        val keep = setOf("dashboard", "relay")
        val words = Regex("(?<![\\w.])[a-z]{3,}(?![\\w.])")
        val bad = zh.all.filter { (k, v) -> k != "language_en" && words.findAll(v).any { it.value !in keep } }
            .filterValues { !it.contains("web_monitor") }
        assertTrue("$bad", bad.isEmpty())
    }

    @Test
    fun noRawProtocolCodes() {
        val codes = (Aio.STATES + Aio.ACTIONS + Aio.HEALTH_BITS + Aio.INHIBIT_BITS).toSet()
        for (t in listOf(en, zh)) {
            val bad = t.all.filter { (_, v) -> Regex("[A-Z][A-Z_]+").findAll(v).any { it.value in codes } }
            assertTrue("$bad", bad.isEmpty())
        }
        // The screens and the notification turn codes into words (ui/Words.kt) instead of showing the names.
        val sources = File("src/main/java/com/lemongrass/aionav/ui").listFiles().orEmpty().toList() +
            File("src/main/java/com/lemongrass/aionav/monitor/MonitorService.kt")
        val raw = Regex("\\.(stateName|actionName|gnssQualityName|healthNames|inhibitNames)\\b")
        val uses = sources.flatMap { f -> f.readLines().filter { raw.containsMatchIn(it) }.map { "${f.name}: ${it.trim()}" } }
        assertTrue("$uses", uses.isEmpty())
    }
}
