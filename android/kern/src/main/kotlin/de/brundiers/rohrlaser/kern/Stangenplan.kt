package de.brundiers.rohrlaser.kern

/** Maschinen- und Stangenwerte für einen Stangenplan [mm]. Vorgabe: Maschine T11 der Beispieldaten. */
data class Stangenwerte(
    val stange: Double = 6000.0,
    val endbeschnitt: Double = 10.0,
    val greiferrest: Double = 142.0,
    val schnittverlust: Double = 0.2,
    val abstand: Double = 2.0,
)

/** Eine Eingabezeile: Teil mit Länge, Stückzahl und Enden (gerade = senkrechter Schnitt). */
data class Teileingabe(
    val bezeichnung: String,
    val laenge: Double,
    val stueck: Int,
    val aGerade: Boolean = true,
    val bGerade: Boolean = true,
)

/** Eine Stange im Ergebnis: Teile in Schnittreihenfolge, belegte Länge (inkl. Endbeschnitt und Schnitten), Rest. */
data class PlanStange(val folge: List<Lage>, val belegt: Double, val rest: Double, val gemeinsameSchnitte: Int)

data class Stangenplan(
    val werte: Stangenwerte,
    val eingaben: List<Teileingabe>,
    val stangen: List<PlanStange>,
    val nichtEingeplant: List<Teileingabe>,
    val untergrenze: Int,
    val bewertung: String,
    val manuell: Int,
) {
    /** Summe der Teilelängen auf den Stangen. */
    val nutzlaenge: Double get() = Py.summe(stangen.flatMap { s -> s.folge.map { it.teil.laenge } })
    val materiallaenge: Double get() = stangen.size * werte.stange
    val verschnitt: Double get() = materiallaenge - nutzlaenge
    val ausnutzung: Double get() = if (materiallaenge > 0) nutzlaenge / materiallaenge else 0.0
}

/** Stangenplan für eine Profilabmessung: Optimierung wie im PC-Programm, danach unabhängige Kontrolle. */
object Stangenplanung {
    fun rechne(werte: Stangenwerte, eingaben: List<Teileingabe>): Stangenplan {
        val g = Gruppe("", "", werte.stange, werte.endbeschnitt, werte.greiferrest, werte.schnittverlust, werte.abstand)
        val nicht = ArrayList<Teileingabe>()
        for ((zeile, e) in eingaben.withIndex()) {
            if (e.laenge <= 0 || e.stueck <= 0) continue
            val teile = (1..e.stueck).map { nr ->
                Teil(zeile, null, e.bezeichnung, nr, e.laenge, e.aGerade, e.bGerade, 0.0, 0.0)
            }
            // ein Teil, das allein nicht auf eine Stange passt, wird nicht eingeplant (wie im PC-Programm)
            if (!Optimierung.passt(g, listOf(teile[0]))) nicht += e else g.teile.addAll(teile)
        }
        val folgen = if (g.teile.isEmpty()) mutableListOf() else Optimierung.optimiere(g)
        Optimierung.pruefe(listOf(g), listOf(folgen))
        val stangen = folgen.map { f ->
            val belegt = Optimierung.verbrauch(g, f)
            PlanStange(f, belegt, werte.stange - belegt, Optimierung.gemeinsameSchnitte(f))
        }
        return Stangenplan(werte, eingaben, stangen, nicht, Optimierung.untergrenze(g),
            if (stangen.isEmpty()) "" else Optimierung.bewertung(g, stangen.size),
            if (g.teile.isEmpty()) 0 else Optimierung.manuell(g).size)
    }
}
