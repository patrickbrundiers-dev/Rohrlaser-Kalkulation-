package de.brundiers.rohrlaser.kern

/** Ebene Gehrung eines Endes: Winkel gegen den geraden Schnitt [°] und Richtung, in der das Teil am längsten ist [°]. */
data class Gehrung(val winkel: Double, val richtung: Double) {
    fun alsListe(): List<Any> = listOf(winkel, richtung)
}

/** Querschnitt für das Ineinanderlegen von Gehrungen: art "Kasten" (a = Breite, b = Höhe) oder "Rund" (a = Radius). */
data class Querschnitt(val art: String, val a: Double, val b: Double = 0.0)

/** Ein Teil auf der Stange (wie optimierung.Teil). Gleichheit = dasselbe Teil (Identität), nicht gleiche Werte. */
class Teil(
    val zeile: Int,
    val pos: String?,
    val artikel: String,
    val nr: Int,
    val laenge: Double,
    val aGerade: Boolean,
    val bGerade: Boolean,
    val aSchnitt: Double,
    val bSchnitt: Double,
    val aGehrung: Gehrung? = null,
    val bGehrung: Gehrung? = null,
    val drehung: String = Optimierung.FREI,
    val naht: Double? = null,
) {
    fun kopie(
        laenge: Double = this.laenge,
        aGehrung: Gehrung? = this.aGehrung,
        bGehrung: Gehrung? = this.bGehrung,
        drehung: String = this.drehung,
        naht: Double? = this.naht,
    ) = Teil(zeile, pos, artikel, nr, laenge, aGerade, bGerade, aSchnitt, bSchnitt, aGehrung, bGehrung, drehung, naht)

    override fun toString() = "Teil($zeile/$nr, $laenge)"
}

/** Teile einer Abmessung (Profil + Werkstoff + Stangenlänge + Oberfläche + Beistellung) mit den Maschinenwerten. */
class Gruppe(
    val profil: String,
    val werkstoff: String,
    val stange: Double,
    val endbeschnitt: Double,
    val greiferrest: Double,
    val kerf: Double,
    val abstand: Double,
    val oberflaeche: String = "",
    var teile: MutableList<Teil> = ArrayList(),
    var bewiesen: Boolean = false,
    var schranke: Int = 0,
    val beistellung: String = "",
    val querschnitt: Querschnitt? = null,
) {
    val nutzbarBis: Double get() = stange - greiferrest

    fun kopie(
        stange: Double = this.stange,
        teile: MutableList<Teil> = this.teile,
        bewiesen: Boolean = this.bewiesen,
        schranke: Int = this.schranke,
    ) = Gruppe(profil, werkstoff, stange, endbeschnitt, greiferrest, kerf, abstand, oberflaeche, teile, bewiesen,
        schranke, beistellung, querschnitt)
}

/** Teil in seiner Lage auf der Stange: Drehung um die eigene Achse [°]. */
data class Lage(val teil: Teil, val drehung: Double)

/** Vergleich wie bei Python-Tupeln (für gleiche Sortierungen wie im PC-Programm). */
object Py {
    /** sum() wie Python ab 3.12: kompensierte Summe nach Neumaier (gleiche Rundung wie das PC-Programm). */
    fun summe(werte: Iterable<Double>): Double {
        var f = 0.0
        var c = 0.0
        for (x in werte) {
            val t = f + x
            c += if (Math.abs(f) >= Math.abs(x)) (f - t) + x else (x - t) + f
            f = t
        }
        return if (c != 0.0 && c.isFinite()) f + c else f
    }

    fun vergleiche(a: Any?, b: Any?): Int = when {
        a is Number && b is Number -> a.toDouble().compareTo(b.toDouble()).let { if (a.toDouble() == b.toDouble()) 0 else it }
        a is Boolean && b is Boolean -> a.compareTo(b)
        a is String && b is String -> a.compareTo(b)
        a is List<*> && b is List<*> -> {
            var c = 0
            for (i in 0 until minOf(a.size, b.size)) {
                c = vergleiche(a[i], b[i])
                if (c != 0) break
            }
            if (c != 0) c else a.size.compareTo(b.size)
        }
        else -> throw IllegalArgumentException("nicht vergleichbar: $a, $b")
    }
}
