// One language at a time, like the desktop 1.2.0 (tests/test_i18n.py): both languages hold the same texts
// with the same arguments, the protocol vocabulary is complete, English shows no Chinese, and the screen
// never shows a raw protocol code such as KEEP_STILL_REQUIRED.

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

    private fun load(folder: String): Table {
        val doc = DocumentBuilderFactory.newInstance().newDocumentBuilder()
            .parse(File("src/main/res/$folder/strings.xml"))
        fun elements(tag: String) = doc.getElementsByTagName(tag).let { n -> (0 until n.length).map { n.item(it) as Element } }
        return Table(
            elements("string").associate { it.getAttribute("name") to it.textContent },
            elements("string-array").associate { a ->
                a.getAttribute("name") to a.getElementsByTagName("item").let { n -> (0 until n.length).map { n.item(it).textContent } }
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
