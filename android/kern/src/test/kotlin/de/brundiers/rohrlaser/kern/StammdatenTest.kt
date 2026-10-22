package de.brundiers.rohrlaser.kern

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

/** Liest die Beispiel-Stammdaten, wie das PC-Programm sie fürs Handy exportiert (tests/android_paritaet.py). */
class StammdatenTest {
    private val s = Stammdaten.lies(javaClass.getResource("/stammdaten_beispiel.json")!!.readText())

    @Test
    fun tabellenUndGruppen() {
        assertEquals(28, s.tabellen.size)
        // jede exportierte Tabelle ist genau einer Gruppe zugeordnet (sonst wäre sie in der App unsichtbar)
        assertEquals(s.tabellen.keys.sorted(), Stammdaten.GRUPPEN.flatMap { it.second }.sorted())
        val profile = s.tabelle("profile")!!
        assertEquals("Profile", profile.titel)
        assertTrue(profile.zeilen.isNotEmpty())
        assertTrue(profile.felder.any { it.name == "profil_id" })
        assertEquals("22.10.2026 12:00", Anzeige.zeit(s.erstellt))
    }

    @Test
    fun maschinenUndStangenwerte() {
        val m = s.maschinen()
        assertTrue(m.map { it.id }.containsAll(listOf("T03", "T11", "LT7")), m.toString())
        val t11 = m.first { it.id == "T11" }
        val w = s.stangenwerte(t11)
        assertEquals(Stangenwerte(6000.0, 10.0, 142.0, 0.2, w.abstand), w)
        assertEquals("T03", s.standardMaschine)
    }

    @Test
    fun einstellungenOhnePasswort() {
        assertTrue("passwort" !in s.einstellungen)
        assertTrue(s.beschreibung.none { it.art == "passwort" })
        assertEquals(6000.0, s.standardStange)
    }

    @Test
    fun falscheDatei() {
        assertFailsWith<IllegalArgumentException> { Stammdaten.lies("kein json") }
        assertFailsWith<IllegalArgumentException> { Stammdaten.lies("""{"format":"anders"}""") }
        val e = assertFailsWith<IllegalArgumentException> { Stammdaten.lies("""{"format":"rohrlaser-stammdaten","version":9}""") }
        assertTrue("aktualisieren" in e.message!!)
    }

    @Test
    fun anzeige() {
        assertEquals("1.234,5", Anzeige.wert("zahl", null, 1234.5))
        assertEquals("0,20", Anzeige.wert("zahl", 2, 0.2))
        assertEquals("15,0 %", Anzeige.wert("anteil", null, 0.15))
        assertEquals("6.000", Anzeige.wert("ganz", null, 6000.0))
        assertEquals("", Anzeige.wert("text", null, null))
    }
}
