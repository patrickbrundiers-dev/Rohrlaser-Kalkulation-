package de.brundiers.rohrlaser.kern

import kotlin.math.abs
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue
import kotlin.test.fail

/**
 * Gleichheitstest gegen das PC-Programm: tests/android_paritaet.py schreibt Eingaben und Ergebnisse von
 * optimierung.py nach optimierung_faelle.json; der Kotlin-Rechenkern muss jede Stange gleich belegen
 * (gleiche Teile, gleiche Reihenfolge, gleiche Drehung) und dieselben Kennzahlen liefern.
 */
class OptimierungGleichheitTest {
    @Suppress("UNCHECKED_CAST")
    private val faelle = Json.lies(
        javaClass.getResource("/optimierung_faelle.json")!!.readText()
    ) as Map<String, Any?>

    private fun d(v: Any?) = (v as Number).toDouble()
    private fun i(v: Any?) = (v as Number).toInt()

    @Suppress("UNCHECKED_CAST")
    private fun gehrung(v: Any?): Gehrung? = (v as List<Any?>?)?.let { Gehrung(d(it[0]), d(it[1])) }

    @Suppress("UNCHECKED_CAST")
    private fun gruppe(m: Map<String, Any?>): Gruppe {
        val q = m["querschnitt"] as List<Any?>
        val querschnitt = when {
            q.isEmpty() -> null
            q[0] == "Rund" -> Querschnitt("Rund", d(q[1]))
            else -> Querschnitt(q[0] as String, d(q[1]), d(q[2]))
        }
        val g = Gruppe(m["profil"] as String, m["werkstoff"] as String, d(m["stange"]), d(m["endbeschnitt"]),
            d(m["greiferrest"]), d(m["kerf"]), d(m["abstand"]), querschnitt = querschnitt)
        g.teile = (m["teile"] as List<Map<String, Any?>>).map { t ->
            Teil(i(t["zeile"]), null, t["artikel"] as String, i(t["nr"]), d(t["laenge"]), t["a_gerade"] as Boolean,
                t["b_gerade"] as Boolean, d(t["a_schnitt"]), d(t["b_schnitt"]), gehrung(t["a_gehrung"]),
                gehrung(t["b_gehrung"]), t["drehung"] as String, (t["naht"] as Number?)?.toDouble())
        }.toMutableList()
        return g
    }

    private fun folge(f: List<Lage>): List<List<Double>> =
        f.map { listOf(it.teil.zeile.toDouble(), it.teil.nr.toDouble(), it.drehung) }

    @Suppress("UNCHECKED_CAST")
    private fun soll(f: Any?): List<List<Double>> = (f as List<List<Any?>>).map { e -> e.map { d(it) } }

    private fun gleich(a: Double, b: Double) = abs(a - b) <= 1e-6

    @Test
    @Suppress("UNCHECKED_CAST")
    fun optimierungWieImPcProgramm() {
        val liste = faelle["optimierung"] as List<Map<String, Any?>>
        assertTrue(liste.size >= 100, "zu wenige Fälle")
        val fehler = ArrayList<String>()
        for ((nr, fall) in liste.withIndex()) {
            val g = gruppe(fall["gruppe"] as Map<String, Any?>)
            val e = fall["ergebnis"] as Map<String, Any?>
            val folgen = Optimierung.optimiere(g)
            Optimierung.pruefe(listOf(g), listOf(folgen))
            val sollFolgen = (e["folgen"] as List<Any?>).map { soll(it) }
            val ist = folgen.map { folge(it) }
            if (ist != sollFolgen) {
                fehler += "Fall $nr: Stangen verschieden\n  PC:      $sollFolgen\n  Android: $ist"
                continue
            }
            val verbrauch = (e["verbrauch"] as List<Any?>).map { d(it) }
            if (!folgen.indices.all { gleich(Optimierung.verbrauch(g, folgen[it]), verbrauch[it]) }) fehler += "Fall $nr: Verbrauch"
            if (g.bewiesen != e["bewiesen"]) fehler += "Fall $nr: bewiesen ${g.bewiesen} statt ${e["bewiesen"]}"
            if (g.schranke != i(e["schranke"])) fehler += "Fall $nr: Schranke ${g.schranke} statt ${e["schranke"]}"
            if (Optimierung.untergrenze(g) != i(e["untergrenze"])) fehler += "Fall $nr: Untergrenze"
            if (Optimierung.bewertung(g, folgen.size) != e["bewertung"]) fehler += "Fall $nr: Bewertung"
            if (Optimierung.manuell(g).size != i(e["manuell"])) fehler += "Fall $nr: manuelle Einteilung"
            val ohne = Optimierung.ohneDrehung(g)
            if (ohne != (e["ohne_drehung"] as Number?)?.toInt()) fehler += "Fall $nr: ohne Drehung $ohne statt ${e["ohne_drehung"]}"
            if (folgen.map { Optimierung.gemeinsameSchnitte(it) } != (e["gemeinsame_schnitte"] as List<Any?>).map { i(it) }) fehler += "Fall $nr: gemeinsame Schnitte"
            if (folgen.map { Optimierung.gehrungenIneinander(g, it) } != (e["ineinander"] as List<Any?>).map { i(it) }) fehler += "Fall $nr: Gehrungen ineinander"
            if (folgen.map { Optimierung.ansicht(g, it) } != (e["ansicht"] as List<Any?>).map { i(it) }) fehler += "Fall $nr: Ansicht"
        }
        if (fehler.isNotEmpty()) fail("${fehler.size} Abweichung(en) vom PC-Programm:\n" + fehler.joinToString("\n"))
    }

    @Test
    @Suppress("UNCHECKED_CAST")
    fun zuschnittWieImPcProgramm() {
        val liste = faelle["zuschnitt"] as List<Map<String, Any?>>
        for ((nr, fall) in liste.withIndex()) {
            val g = gruppe(fall["gruppe"] as Map<String, Any?>)
            val st = Optimierung.zuschnitt(g, d(fall["lieferlaenge"]), d(fall["max_werkstueck"]), d(fall["saege"]),
                d(fall["min_werkstueck"]), d(fall["puffer"]))
            val sollSt = fall["ergebnis"] as List<List<List<Any?>>>?
            if (sollSt == null) {
                assertEquals(null, st, "Fall $nr")
                continue
            }
            Optimierung.pruefeZuschnitt(g, st!!, d(fall["lieferlaenge"]), d(fall["max_werkstueck"]), d(fall["saege"]),
                d(fall["min_werkstueck"]))
            val ist = st.map { s -> s.map { w -> listOf(w.laenge.toDouble(), folge(w.folge)) } }
            val soll = sollSt.map { s -> s.map { w -> listOf(d(w[0]), soll(w[1])) } }
            assertEquals(soll, ist, "Zuschnitt Fall $nr")
        }
    }

    @Test
    @Suppress("UNCHECKED_CAST")
    fun profileWieImPcProgramm() {
        for (p in faelle["profile"] as List<Map<String, Any?>>) {
            val form = p["form"] as String
            val args = listOf(p["a"], p["b"], p["wand"], p["flaeche"]).map { (it as Number?)?.toDouble() }
            assertTrue(gleich(Optimierung.umfang(form, args[0]!!, args[1], args[2], args[3]), d(p["umfang"])), form)
            assertTrue(gleich(Optimierung.schnittlaenge(form, args[0]!!, args[1], args[2], args[3]), d(p["schnittlaenge"])), form)
        }
    }

    @Test
    fun jsonHinUndZurueck() {
        val w = mapOf("a" to listOf(1, 2.5, true, null, "ä\"\n"), "b" to emptyMap<String, Any>())
        assertEquals(mapOf("a" to listOf(1.0, 2.5, true, null, "ä\"\n"), "b" to emptyMap<String, Any>()), Json.lies(Json.schreibe(w)))
    }
}
