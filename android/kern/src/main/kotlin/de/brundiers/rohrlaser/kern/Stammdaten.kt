package de.brundiers.rohrlaser.kern

import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.util.Locale

data class StammFeld(val name: String, val titel: String, val art: String, val stellen: Int?)

data class StammTabelle(
    val name: String,
    val titel: String,
    val felder: List<StammFeld>,
    val zeilen: List<Map<String, Any?>>,
)

data class EinstellungInfo(val name: String, val titel: String, val gruppe: String, val art: String)

data class Maschine(
    val id: String,
    val bezeichnung: String,
    val endbeschnitt: Double,
    val greiferrest: Double,
    val schnittverlust: Double,
    val abstand: Double,
    val maxStange: Double?,
)

/**
 * Stammdaten vom PC (Datei → Stammdaten fürs Handy exportieren, programm/rohrlaser/handy_export.py).
 * Auf dem Handy nur zum Ansehen und Rechnen; neu einlesen ersetzt alles (kein Abgleich).
 */
class Stammdaten(
    val programm: String,
    val schema: Int,
    val erstellt: String,
    val tabellen: Map<String, StammTabelle>,
    val einstellungen: Map<String, Any?>,
    val beschreibung: List<EinstellungInfo>,
) {
    fun tabelle(name: String): StammTabelle? = tabellen[name]

    fun maschinen(): List<Maschine> = (tabelle("maschinen")?.zeilen ?: emptyList()).mapNotNull { z ->
        val id = z["maschinen_id"] as? String ?: return@mapNotNull null
        Maschine(id, z["bezeichnung"] as? String ?: "", zahl(z["endbeschnitt"]), zahl(z["greiferrest"]),
            zahl(z["schnittverlust"]), zahl(z["abstand"]), (z["max_stange"] as? Number)?.toDouble())
    }

    val standardMaschine: String? get() = einstellungen["standard_maschine"] as? String
    val standardStange: Double get() = (einstellungen["standard_stange"] as? Number)?.toDouble() ?: 6000.0

    /** Werte für den Stangenplan mit einer Maschine; Stangenlänge = Standard, höchstens die max. Stangenlänge. */
    fun stangenwerte(m: Maschine): Stangenwerte {
        val stange = m.maxStange?.takeIf { it > 0 }?.let { minOf(it, standardStange) } ?: standardStange
        return Stangenwerte(stange, m.endbeschnitt, m.greiferrest, m.schnittverlust, m.abstand)
    }

    companion object {
        const val FORMAT = "rohrlaser-stammdaten"
        const val VERSION = 1

        /** Tabellen in Gruppen wie im PC-Programm (Reiter Kunden, Stammdaten, Frachtkosten, Zukauf). */
        val GRUPPEN = listOf(
            "Kunden" to listOf("kunden"),
            "Material" to listOf("profile", "werkstoffe", "oberflaechen", "preise", "lieferlaengen"),
            "Fertigung" to listOf("maschinen", "schneiddaten", "gewinde", "zusatzarbeiten", "stundensaetze", "arbeitsschritte"),
            "Frachtkosten" to listOf("fracht_laender", "fracht_zonen", "fracht_plz", "fracht_dienstleister", "fracht_tarife",
                "fracht_preise", "fracht_lht", "fracht_zuschlaege", "fracht_dieselpreise", "fracht_dieselstaffel",
                "fracht_waehrungen"),
            "Zukauf" to listOf("zukauf_artikel", "zukauf_kategorien", "zukauf_lieferanten", "zukauf_bezug", "zukauf_historie"),
        )

        private fun zahl(v: Any?) = (v as? Number)?.toDouble() ?: 0.0

        /** Datei lesen; IllegalArgumentException mit verständlicher Meldung, wenn es keine Stammdaten-Datei ist. */
        @Suppress("UNCHECKED_CAST")
        fun lies(text: String): Stammdaten {
            val d = try {
                Json.lies(text) as? Map<String, Any?>
            } catch (e: Exception) {
                null
            } ?: throw IllegalArgumentException("Die Datei ist keine Stammdaten-Datei des PC-Programms.")
            require(d["format"] == FORMAT) { "Die Datei ist keine Stammdaten-Datei des PC-Programms." }
            val version = (d["version"] as? Number)?.toInt() ?: 0
            require(version <= VERSION) { "Die Datei ist neuer als diese App. Bitte die App aktualisieren." }
            val tabellen = LinkedHashMap<String, StammTabelle>()
            for ((name, t) in d["tabellen"] as Map<String, Any?>) {
                t as Map<String, Any?>
                val felder = (t["felder"] as List<Map<String, Any?>>).map {
                    StammFeld(it["name"] as String, it["titel"] as String, it["art"] as String, (it["stellen"] as? Number)?.toInt())
                }
                tabellen[name] = StammTabelle(name, t["titel"] as String, felder, t["zeilen"] as List<Map<String, Any?>>)
            }
            val beschreibung = (d["einstellungen_beschreibung"] as? List<Map<String, Any?>> ?: emptyList()).map {
                EinstellungInfo(it["name"] as String, it["titel"] as String, it["gruppe"] as String, it["art"] as String)
            }
            return Stammdaten(d["programm"] as? String ?: "", (d["schema"] as? Number)?.toInt() ?: 0,
                d["erstellt"] as? String ?: "", tabellen, d["einstellungen"] as? Map<String, Any?> ?: emptyMap(), beschreibung)
        }
    }
}

/** Werte deutsch anzeigen (Dezimalkomma, Tausenderpunkt). */
object Anzeige {
    private val DE = DecimalFormatSymbols(Locale.GERMANY)

    fun zahl(x: Double, stellen: Int? = null): String {
        val muster = when {
            stellen == null -> "#,##0.###"
            stellen > 0 -> "#,##0." + "0".repeat(stellen)
            else -> "#,##0"
        }
        return DecimalFormat(muster, DE).format(x)
    }

    /** Wert eines Felds (art wie im PC-Programm: text, zahl, ganz, anteil, datum, auswahl …); leer = "". */
    fun wert(art: String, stellen: Int?, w: Any?): String = when {
        w == null -> ""
        w is Boolean -> if (w) "ja" else "nein"
        art == "anteil" && w is Number -> zahl(w.toDouble() * 100, stellen ?: 1) + " %"
        art == "ganz" && w is Number -> zahl(w.toDouble(), 0)
        w is Number -> zahl(w.toDouble(), stellen)
        art == "bild" -> if ((w as? String).isNullOrEmpty()) "" else "(Bild)"
        else -> w.toString()
    }

    /** Datum/Zeit aus ISO (2026-10-22T12:00:00) als 22.10.2026 12:00. */
    fun zeit(iso: String): String {
        val m = Regex("""(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?""").find(iso) ?: return iso
        val (j, mo, t, h, mi) = m.destructured
        return "$t.$mo.$j" + if (h.isNotEmpty()) " $h:$mi" else ""
    }
}
