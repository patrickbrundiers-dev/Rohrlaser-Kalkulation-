package de.brundiers.rohrlaser.kern

import java.math.BigDecimal
import java.math.RoundingMode
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.cos
import kotlin.math.floor
import kotlin.math.hypot
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.sin
import kotlin.math.tan

/**
 * Stangenoptimierung – Übertragung von programm/rohrlaser/optimierung.py (PC-Programm) nach Kotlin.
 *
 * Gleiche Regeln, gleiches Verfahren, gleiche Reihenfolgen: Die Ergebnisse müssen Stange für Stange mit dem
 * PC-Programm übereinstimmen (Gleichheitstest gegen tests/android_paritaet.py). Jede Änderung an optimierung.py
 * muss hier nachgezogen werden. Kommentare zu den Regeln stehen ausführlich in optimierung.py.
 */
object Optimierung {
    const val EPS = 1e-6
    const val EXAKT_MAX_TEILE = 60
    const val EXAKT_MAX_KNOTEN = 20000
    const val MUSTER_MAX_RUNDEN = 300
    const val MUSTER_MAX_KNOTEN = 50000
    const val FREI = "frei"
    const val FEST = "fest"
    const val UNBEKANNT = "unbekannt"
    const val ZUSCHNITT_TEILUNG = 6

    /** Python-Rest (Ergebnis hat das Vorzeichen des Teilers), ohne −0,0. */
    fun pmod(a: Double, b: Double): Double {
        val m = a % b
        return (if (m != 0.0 && (m < 0) != (b < 0)) m + b else m) + 0.0
    }

    /** round(x, 6) wie Python (exakter Binärwert, halbe Stelle zur geraden Ziffer). */
    private fun runde6(x: Double): Double =
        if (x.isFinite()) BigDecimal(x).setScale(6, RoundingMode.HALF_EVEN).toDouble() else x

    private fun ceilInt(x: Double): Int = ceil(x).toInt()
    private fun floorInt(x: Double): Int = floor(x).toInt()

    // -------------------------------------------------------------- Drehung um die eigene Achse
    fun raster(g: Gruppe): Int {
        val q = g.querschnitt ?: return 360
        if (q.art == "Kasten" && abs(q.a - q.b) > EPS) return 180
        return 90
    }

    fun drehungen(g: Gruppe, t: Teil, nahtStange: Double = 0.0): List<Double> {
        val r = raster(g)
        if (t.drehung == FREI) return (0 until 360 step r).map { it.toDouble() }
        if (t.drehung == FEST && t.naht != null && r < 360) {
            if (g.querschnitt!!.art == "Rund") return listOf(pmod(nahtStange - t.naht, 360.0))
            return listOf(pmod(nahtStange - Math.rint(t.naht / 90) * 90, 360.0).toInt().toDouble())
        }
        return listOf(0.0)
    }

    fun nahtLagen(g: Gruppe, teile: List<Teil>): List<Double> {
        val fest = teile.filter { it.drehung == FEST && it.naht != null }
        if (fest.isEmpty() || raster(g) == 360) return listOf(0.0)
        if (raster(g) == 180) {
            val seiten = fest.map { Math.floorMod(Math.rint(it.naht!! / 90).toLong(), 2L) }.toSet()
            if (seiten.size > 1) return emptyList()
            val seite = seiten.first()
            return listOf(0, 90, 180, 270).filter { (it / 90 % 2).toLong() == seite }.map { it.toDouble() }
        }
        return listOf(0.0, 90.0, 180.0, 270.0)
    }

    private fun stuetz(g: Gruppe, vx: Double, vy: Double): Double {
        val q = g.querschnitt!!
        if (q.art == "Rund") return q.a * hypot(vx, vy)
        return q.a / 2 * abs(vx) + q.b / 2 * abs(vy)
    }

    private fun richtung(winkel: Double): Pair<Double, Double> {
        val w = Math.toRadians(winkel)
        return Pair(sin(w), cos(w))
    }

    fun gehrungTiefe(g: Gruppe, geh: Gehrung?): Double {
        if (geh == null || g.querschnitt == null) return 0.0
        val (x, y) = richtung(geh.richtung)
        return tan(Math.toRadians(geh.winkel)) * stuetz(g, x, y)
    }

    fun gehrungTrennung(g: Gruppe, bGeh: Gehrung, r1: Double, aGeh: Gehrung, r2: Double): Double {
        val t1 = tan(Math.toRadians(bGeh.winkel))
        val t2 = tan(Math.toRadians(aGeh.winkel))
        val (x1, y1) = richtung(bGeh.richtung + r1)
        val (x2, y2) = richtung(aGeh.richtung + r2)
        val abstand = (2 * g.kerf + g.abstand) / cos(Math.toRadians(max(bGeh.winkel, aGeh.winkel)))
        return (abstand + stuetz(g, t1 * x1 + t2 * x2, t1 * y1 + t2 * y2) - t1 * stuetz(g, x1, y1)
            - t2 * stuetz(g, x2, y2))
    }

    /** Rücksprung der Schnittkante eines schrägen Endes in der Ansicht (oben, unten) [mm]. */
    fun kante(g: Gruppe, geh: Gehrung?, drehung: Double, oben: Int = 0): Pair<Double, Double> {
        val q = g.querschnitt
        if (geh == null || q == null) return Pair(0.0, 0.0)
        val t = tan(Math.toRadians(geh.winkel))
        val c = cos(Math.toRadians(geh.richtung + drehung - oben))
        if (q.art == "Rund") return Pair(t * q.a * (1 - c), t * q.a * (1 + c))
        val hh = (if (oben % 180 == 0) q.b else q.a) / 2
        return Pair(t * hh * (abs(c) - c), t * hh * (abs(c) + c))
    }

    fun ansicht(g: Gruppe, folge: List<Lage>): Int {
        if (g.querschnitt == null || g.querschnitt.art == "Rund") return 0
        val w = linkedMapOf(0 to 0.0, 270 to 0.0)
        for ((t, d) in folge) {
            for (geh in listOf(t.aGehrung, t.bGehrung)) {
                for (oben in w.keys.toList()) {
                    val k = kante(g, geh, d, oben)
                    w[oben] = w[oben]!! + Py.summe(listOf(k.first, k.second))
                }
            }
        }
        return if (w[270]!! > w[0]!! + EPS) 270 else 0
    }

    fun verschachtelbar(g: Gruppe, t: Teil): Boolean =
        g.querschnitt != null && (t.aGehrung != null || t.bGehrung != null)

    // -------------------------------------------------------------- Belegung einer Stange
    fun trennung(kerf: Double, abstand: Double, endeGerade: Boolean, anfangGerade: Boolean): Double =
        if (endeGerade && anfangGerade) kerf else 2 * kerf + abstand

    private data class SpeicherGruppe(val querschnitt: Querschnitt?, val kerf: Double, val abstand: Double)
    private data class SpeicherSchluessel(val b: Gehrung, val a: Gehrung, val r1: Double, val dr: Double)

    private val speicher = HashMap<SpeicherGruppe, HashMap<SpeicherSchluessel, Double>>()

    fun trennungTeile(g: Gruppe, t1: Teil, r1: Double, t2: Teil, r2: Double): Double {
        val normal = trennung(g.kerf, g.abstand, t1.bGerade, t2.aGerade)
        if (t1.bGerade && t2.aGerade || t1.bGehrung == null || t2.aGehrung == null || g.querschnitt == null) {
            return normal
        }
        val schluessel = SpeicherSchluessel(
            t1.bGehrung, t2.aGehrung,
            if (g.querschnitt.art == "Kasten") pmod(r1, raster(g).toDouble()) else 0.0, pmod(r2 - r1, 360.0)
        )
        val sp = synchronized(speicher) {
            speicher.getOrPut(SpeicherGruppe(g.querschnitt, g.kerf, g.abstand)) { HashMap() }
        }
        synchronized(sp) {
            return sp.getOrPut(schluessel) { min(normal, gehrungTrennung(g, t1.bGehrung, r1, t2.aGehrung, r2)) }
        }
    }

    fun ineinander(g: Gruppe, t1: Teil, r1: Double, t2: Teil, r2: Double): Boolean =
        !(t1.bGerade && t2.aGerade) &&
            trennungTeile(g, t1, r1, t2, r2) < trennung(g.kerf, g.abstand, false, false) - EPS

    private fun ketteGerade(teile: List<Teil>): List<Teil> {
        val ss = teile.filter { it.aGerade && it.bGerade }
        val ns = teile.filter { !it.aGerade && it.bGerade }.toMutableList()
        val sn = teile.filter { it.aGerade && !it.bGerade }.toMutableList()
        val nn = teile.filter { !it.aGerade && !it.bGerade }
        val folge = ArrayList<Teil>()
        if (ns.isNotEmpty()) folge.add(ns.removeAt(0))
        folge += ss
        if (sn.isNotEmpty()) folge.add(sn.removeAt(0))
        while (ns.isNotEmpty() && sn.isNotEmpty()) {
            folge.add(ns.removeAt(0))
            folge.add(sn.removeAt(0))
        }
        return folge + nn + ns + sn
    }

    private fun drehungenWaehlen(g: Gruppe, folge: List<Teil>, nahtStange: Double): Pair<Double, List<Double>> {
        val stufen = ArrayList<LinkedHashMap<Double, Pair<Double, Double?>>>()
        for ((i, t) in folge.withIndex()) {
            val moegl = drehungen(g, t, nahtStange)
            if (i == 0) {
                stufen.add(LinkedHashMap<Double, Pair<Double, Double?>>().apply { moegl.forEach { put(it, Pair(0.0, null)) } })
                continue
            }
            val vorher = stufen.last()
            val stufe = LinkedHashMap<Double, Pair<Double, Double?>>()
            for (r in moegl) {
                var beste: Pair<Double, Double>? = null
                for ((rv, v) in vorher) {
                    val kand = Pair(v.first + trennungTeile(g, folge[i - 1], rv, t, r), rv)
                    if (beste == null) {
                        beste = kand
                    } else {
                        val c = runde6(kand.first).compareTo(runde6(beste.first)).let { if (it != 0) it else kand.second.compareTo(beste.second) }
                        if (c < 0) beste = kand
                    }
                }
                stufe[r] = Pair(beste!!.first, beste.second)
            }
            stufen.add(stufe)
        }
        if (stufen.isEmpty()) return Pair(0.0, emptyList())
        val letzte = stufen.last()
        var r = letzte.keys.minWith(Comparator { a, b ->
            val c = letzte[a]!!.first.compareTo(letzte[b]!!.first)
            if (c != 0) c else a.compareTo(b)
        })
        val summe = letzte[r]!!.first
        val wahl = arrayListOf(r)
        for (i in stufen.size - 1 downTo 1) {
            r = stufen[i][r]!!.second!!
            wahl.add(r)
        }
        return Pair(summe, wahl.reversed())
    }

    private fun ketteGehrung(g: Gruppe, teile: List<Teil>, nahtStange: Double): List<Teil> {
        val n = teile.size
        data class Kante(val c: Double, val i: Int, val j: Int)
        val kosten = ArrayList<Kante>()
        for ((i, t1) in teile.withIndex()) {
            for ((j, t2) in teile.withIndex()) {
                if (i != j) {
                    var c = Double.POSITIVE_INFINITY
                    for (r1 in drehungen(g, t1, nahtStange)) for (r2 in drehungen(g, t2, nahtStange)) {
                        c = min(c, trennungTeile(g, t1, r1, t2, r2))
                    }
                    kosten.add(Kante(c, i, j))
                }
            }
        }
        kosten.sortWith(compareBy<Kante>({ it.c }, { it.i }, { it.j }))
        val nach = arrayOfNulls<Int>(n)
        val vor = arrayOfNulls<Int>(n)
        val kopf = IntArray(n) { it }
        fun wurzel(start: Int): Int {
            var i = start
            while (kopf[i] != i) {
                kopf[i] = kopf[kopf[i]]
                i = kopf[i]
            }
            return i
        }
        val normal = trennung(g.kerf, g.abstand, false, false)
        for ((c, i, j) in kosten) {
            if (c >= normal - EPS && !(teile[i].bGerade && teile[j].aGerade)) continue
            if (nach[i] == null && vor[j] == null && wurzel(i) != wurzel(j)) {
                nach[i] = j
                vor[j] = i
                kopf[wurzel(j)] = wurzel(i)
            }
        }
        val folge = ArrayList<Teil>()
        for (start in 0 until n) {
            if (vor[start] == null) {
                var i: Int? = start
                while (i != null) {
                    folge.add(teile[i])
                    i = nach[i]
                }
            }
        }
        return folge
    }

    /** Reihenfolge und Drehung um die eigene Achse (siehe optimierung.anordnen). */
    fun anordnen(teile: List<Teil>, g: Gruppe? = null): List<Lage> {
        val gerade = ketteGerade(teile)
        if (g == null || g.querschnitt == null ||
            teile.count { verschachtelbar(g, it) } < 2 && teile.none { it.drehung == FEST }
        ) {
            return gerade.map { Lage(it, 0.0) }
        }
        var beste: Pair<Double, List<Lage>>? = null
        for (nahtStange in nahtLagen(g, teile).ifEmpty { listOf(0.0) }) {
            for (folge in listOf(gerade, ketteGehrung(g, teile, nahtStange))) {
                val (summe, wahl) = drehungenWaehlen(g, folge, nahtStange)
                if (beste == null || summe < beste.first - EPS) {
                    beste = Pair(summe, folge.zip(wahl) { t, r -> Lage(t, r) })
                }
            }
        }
        return beste!!.second
    }

    fun verbrauch(g: Gruppe, folge: List<Lage>): Double {
        var pos = g.endbeschnitt
        var vorher: Lage? = null
        for (l in folge) {
            if (vorher != null) pos += trennungTeile(g, vorher.teil, vorher.drehung, l.teil, l.drehung)
            pos += l.teil.laenge
            vorher = l
        }
        return pos + (if (folge.isNotEmpty()) g.kerf else 0.0)
    }

    fun vertraeglich(g: Gruppe, teile: List<Teil>): Boolean = nahtLagen(g, teile).isNotEmpty()

    fun passt(g: Gruppe, teile: List<Teil>): Boolean =
        vertraeglich(g, teile) && verbrauch(g, anordnen(teile, g)) <= g.nutzbarBis + EPS

    fun mindestbedarf(g: Gruppe, t: Teil): Double =
        t.laenge + g.kerf - gehrungTiefe(g, t.aGehrung) - gehrungTiefe(g, t.bGehrung)

    // -------------------------------------------------------------- Packverfahren
    fun sortiert(teile: List<Teil>): List<Teil> =
        teile.sortedWith(compareBy<Teil>({ -it.laenge }, { it.zeile }, { it.nr }))

    fun firstFit(g: Gruppe, teile: List<Teil>): MutableList<MutableList<Teil>> {
        val stangen = ArrayList<MutableList<Teil>>()
        for (t in sortiert(teile)) {
            val s = stangen.firstOrNull { passt(g, it + t) }
            if (s != null) s.add(t) else stangen.add(arrayListOf(t))
        }
        return stangen
    }

    fun bestFit(g: Gruppe, teile: List<Teil>): MutableList<MutableList<Teil>> {
        val stangen = ArrayList<MutableList<Teil>>()
        for (t in sortiert(teile)) {
            var beste: MutableList<Teil>? = null
            var restMin: Double? = null
            for (s in stangen) {
                if (!vertraeglich(g, s + t)) continue
                val v = verbrauch(g, anordnen(s + t, g))
                if (v <= g.nutzbarBis + EPS && (restMin == null || g.nutzbarBis - v < restMin)) {
                    beste = s
                    restMin = g.nutzbarBis - v
                }
            }
            if (beste == null) stangen.add(arrayListOf(t)) else beste.add(t)
        }
        return stangen
    }

    fun aufloesen(g: Gruppe, eingabe: List<List<Teil>>): MutableList<MutableList<Teil>> {
        var stangen: MutableList<MutableList<Teil>> = eingabe.map { it.toMutableList() }.toMutableList()
        var geaendert = true
        while (geaendert && stangen.size > 1) {
            geaendert = false
            for (s in stangen.sortedBy { st -> Py.summe(st.map { it.laenge }) }) {
                val andere = stangen.filter { it !== s }.map { it.toMutableList() }.toMutableList()
                var ok = true
                for (t in sortiert(s)) {
                    val ziel = andere.sortedBy { -verbrauch(g, anordnen(it, g)) }.firstOrNull { passt(g, it + t) }
                    if (ziel == null) {
                        ok = false
                        break
                    }
                    ziel.add(t)
                }
                if (ok) {
                    stangen = andere
                    geaendert = true
                    break
                }
            }
        }
        return stangen
    }

    fun gemeinsameSchnitte(folge: List<Lage>): Int =
        folge.zipWithNext().count { (a, b) -> a.teil.bGerade && b.teil.aGerade }

    fun gehrungenIneinander(g: Gruppe, folge: List<Lage>): Int =
        folge.zipWithNext().count { (a, b) -> ineinander(g, a.teil, a.drehung, b.teil, b.drehung) }

    fun gleichartig(a: Teil, b: Teil): Boolean =
        a.laenge == b.laenge && a.aGerade == b.aGerade && a.bGerade == b.bGerade &&
            a.aGehrung == b.aGehrung && a.bGehrung == b.bGehrung && a.drehung == b.drehung && a.naht == b.naht

    /** Exakte Suche (Branch and Bound) nach weniger als [ziel] Stangen: (Stangen oder null, Suche vollständig). */
    fun exakt(g: Gruppe, ziel: Int): Pair<List<List<Teil>>?, Boolean> {
        val teile = sortiert(g.teile)
        val n = teile.size
        val nutz = g.nutzbarBis - g.endbeschnitt
        val bedarf = teile.map { mindestbedarf(g, it) }
        val rest = DoubleArray(n + 1)
        for (i in n - 1 downTo 0) rest[i] = rest[i + 1] + bedarf[i]
        val ug = untergrenze(g)
        val stangen = ArrayList<MutableList<Teil>>()
        val belegt = ArrayList<Double>()
        val zu = IntArray(n)
        var beste: List<List<Teil>>? = null
        var besteN = ziel
        var knoten = 0
        var abbruch = false

        fun suche(i: Int) {
            if (i == n) {
                beste = stangen.map { it.toList() }
                besteN = stangen.size
                return
            }
            knoten += 1
            if (knoten > EXAKT_MAX_KNOTEN) {
                abbruch = true
                return
            }
            var frei = 0.0
            for (b in belegt) frei += nutz - b
            var neu = 0
            if (rest[i] > frei + EPS) neu = ceilInt((rest[i] - frei) / nutz - EPS)
            if (stangen.size + neu >= besteN) return
            val t = teile[i]
            val start = if (i > 0 && gleichartig(teile[i - 1], t)) zu[i - 1] else 0
            for (s in start until stangen.size) {
                if (belegt[s] + bedarf[i] > nutz + EPS || !passt(g, stangen[s] + t)) continue
                stangen[s].add(t)
                belegt[s] += bedarf[i]
                zu[i] = s
                suche(i + 1)
                stangen[s].removeAt(stangen[s].size - 1)
                belegt[s] -= bedarf[i]
                if (abbruch || besteN <= ug) return
            }
            if (stangen.size + 1 < besteN) {
                stangen.add(arrayListOf(t))
                belegt.add(bedarf[i])
                zu[i] = stangen.size - 1
                suche(i + 1)
                stangen.removeAt(stangen.size - 1)
                belegt.removeAt(belegt.size - 1)
            }
        }
        suche(0)
        return Pair(beste, !abbruch || besteN <= ug)
    }

    private fun summeVerbrauch(g: Gruppe, folgen: List<List<Lage>>): Double = Py.summe(folgen.map { verbrauch(g, it) })

    /** Ergebnis: Stangen, je Stange die angeordnete Folge. Setzt g.bewiesen und g.schranke. */
    fun optimiere(g: Gruppe): MutableList<List<Lage>> {
        data class Kandidat(val n: Int, val summe: Double, val folgen: List<List<Lage>>)
        val kandidaten = ArrayList<Kandidat>()
        for (verfahren in listOf(::firstFit, ::bestFit)) {
            val st = aufloesen(g, verfahren(g, g.teile))
            val folgen = st.map { anordnen(it, g) }
            kandidaten.add(Kandidat(folgen.size, summeVerbrauch(g, folgen), folgen))
        }
        var folgen = kandidaten.sortedWith(compareBy<Kandidat>({ it.n }, { it.summe }))[0].folgen
        g.schranke = untergrenze(g)
        g.bewiesen = folgen.size <= g.schranke
        if (!g.bewiesen) {
            val (st, schranke) = musterOptimierung(g)
            g.schranke = max(g.schranke, schranke)
            val neu = st.map { anordnen(it, g) }
            if (st.sumOf { it.size } == g.teile.size) {
                val a = summeVerbrauch(g, neu) + EPS
                val b = summeVerbrauch(g, folgen)
                if (neu.size < folgen.size || neu.size == folgen.size && a < b) folgen = neu
            }
            g.bewiesen = folgen.size <= g.schranke
        }
        if (!g.bewiesen && g.teile.size <= EXAKT_MAX_TEILE) {
            val (st, bewiesen) = exakt(g, folgen.size)
            g.bewiesen = bewiesen
            if (st != null) folgen = st.map { anordnen(it, g) }
        }
        return folgen.sortedWith(compareBy<List<Lage>>({ -verbrauch(g, it) }, { it[0].teil.zeile })).toMutableList()
    }

    fun bewertung(g: Gruppe, nStangen: Int): String = when {
        nStangen <= untergrenze(g) -> "optimal (Untergrenze erreicht)"
        nStangen <= g.schranke -> "optimal (Schranke der Schnittmuster erreicht)"
        g.bewiesen -> "optimal (alle Einteilungen geprüft)"
        else -> "nicht bewiesen (Suche begrenzt)"
    }

    // -------------------------------------------------------------- Schnittmuster (Spaltengenerierung)
    /** Gleiche Teile sind für die Schnittmuster ein Typ; Vergleich wie Python-Tupel. */
    fun typ(t: Teil): List<Any> = listOf(
        t.laenge, t.aGerade, t.bGerade, t.aSchnitt, t.bSchnitt,
        t.aGehrung?.alsListe() ?: emptyList<Any>(), t.bGehrung?.alsListe() ?: emptyList<Any>(),
        t.drehung, t.naht ?: -1.0
    )

    private fun typSchluessel(gruppen: Map<List<Any>, List<Teil>>): List<List<Any>> =
        gruppen.keys.sortedWith(Comparator { a, b ->
            val c = (-(a[0] as Double)).compareTo(-(b[0] as Double))
            if (c != 0) c else Py.vergleiche(a, b)
        })

    private fun typGruppen(g: Gruppe): LinkedHashMap<List<Any>, MutableList<Teil>> {
        val gruppen = LinkedHashMap<List<Any>, MutableList<Teil>>()
        for (t in sortiert(g.teile)) gruppen.getOrPut(typ(t)) { ArrayList() }.add(t)
        return gruppen
    }

    fun bestesMuster(g: Gruppe, typen: List<Teil>, bedarf: IntArray, wert: DoubleArray): Pair<IntArray?, Boolean> {
        val n = typen.size
        var beste: IntArray? = null
        var besteW = -1.0
        val zahl = IntArray(n)
        var knoten = 0
        val qAb = DoubleArray(n + 1) { i ->
            val werte = (i until n).filter { bedarf[it] != 0 }.map { wert[it] / typen[it].laenge }
            if (werte.isEmpty()) 0.0 else werte.max()
        }
        val arten = listOf(Pair(true, true), Pair(false, true), Pair(true, false), Pair(false, false))
        val art = typen.map { arten.indexOf(Pair(it.aGerade, it.bGerade)) }
        val vertreter = HashMap<Int, Teil>()
        for (a in art.toSet()) {
            vertreter[a] = typen[art.indexOf(a)].kopie(laenge = 0.0, aGehrung = null, bGehrung = null, drehung = FREI, naht = null)
        }
        val zuschlag = HashMap<List<Int>, Double>()

        fun passtZahl(anz: List<Int>, laenge: Double): Boolean {
            val z = zuschlag.getOrPut(anz) {
                val nullTeile = ArrayList<Teil>()
                for (a in 0 until 4) repeat(anz[a]) { nullTeile.add(vertreter[a]!!) }
                verbrauch(g, anordnen(nullTeile))
            }
            return z + laenge <= g.nutzbarBis + EPS
        }

        fun suche(i: Int, w: Double, laenge: Double) {
            knoten += 1
            if (w > besteW + 1e-9) {
                beste = zahl.copyOf()
                besteW = w
            }
            if (i == n || knoten > MUSTER_MAX_KNOTEN) return
            if (w + qAb[i] * (g.nutzbarBis - g.endbeschnitt - laenge) <= besteW + 1e-9) return
            val anz = IntArray(4)
            for (j in 0 until i) anz[art[j]] += zahl[j]
            while (zahl[i] < bedarf[i]) {
                anz[art[i]] += 1
                if (!passtZahl(anz.toList(), laenge + typen[i].laenge * (zahl[i] + 1))) break
                zahl[i] += 1
            }
            while (true) {
                suche(i + 1, w + wert[i] * zahl[i], laenge + typen[i].laenge * zahl[i])
                if (zahl[i] == 0) break
                zahl[i] -= 1
            }
        }
        suche(0, 0.0, 0.0)
        return Pair(beste, knoten <= MUSTER_MAX_KNOTEN)
    }

    data class SimplexErgebnis(val y: DoubleArray, val wert: Double, val preise: DoubleArray, val geloest: Boolean)

    /** max c·y unter a·y ≤ b, y ≥ 0, b ≥ 0 (Tableau, Regel von Bland). */
    fun simplexMax(c: DoubleArray, a: List<DoubleArray>, b: DoubleArray): SimplexErgebnis {
        val m = a.size
        val n = c.size
        val tab = Array(m) { i -> DoubleArray(n + m + 1) { j -> if (j < n) a[i][j] else if (j < n + m) (if (j - n == i) 1.0 else 0.0) else b[i] } }
        var z = DoubleArray(n + m + 1) { j -> if (j < n) -c[j] else 0.0 }
        val basis = IntArray(m) { n + it }
        var geloest = false
        for (runde in 0 until 20 * (m + n) + 100) {
            val e = (0 until n + m).firstOrNull { z[it] < -1e-9 }
            if (e == null) {
                geloest = true
                break
            }
            var r: Int? = null
            var best: Double? = null
            for (i in 0 until m) {
                if (tab[i][e] > 1e-9) {
                    val q = tab[i][n + m] / tab[i][e]
                    if (best == null || q < best - 1e-12 || (abs(q - best) <= 1e-12 && basis[i] < basis[r!!])) {
                        r = i
                        best = q
                    }
                }
            }
            if (r == null) break
            val p = tab[r][e]
            tab[r] = DoubleArray(n + m + 1) { tab[r][it] / p }
            for (i in 0 until m) {
                if (i != r && abs(tab[i][e]) > 1e-12) {
                    val f = tab[i][e]
                    val zeile = tab[i]
                    tab[i] = DoubleArray(n + m + 1) { zeile[it] - f * tab[r][it] }
                }
            }
            val f = z[e]
            val alt = z
            z = DoubleArray(n + m + 1) { alt[it] - f * tab[r][it] }
            basis[r] = e
        }
        val y = DoubleArray(n)
        for ((i, bi) in basis.withIndex()) if (bi < n) y[bi] = tab[i][n + m]
        return SimplexErgebnis(y, z[n + m], z.copyOfRange(n, n + m), geloest)
    }

    /** Schnittmuster-Optimierung (Gilmore-Gomory): (Stangen als Teilelisten, Schranke). */
    fun musterOptimierung(g: Gruppe): Pair<List<List<Teil>>, Int> {
        if (!vertraeglich(g, g.teile)) return Pair(emptyList(), 0)
        val gruppen = typGruppen(g)
        val keys = typSchluessel(gruppen)
        val typen = keys.map { gruppen[it]!![0] }
        val bedarf = IntArray(keys.size) { gruppen[keys[it]]!!.size }
        val n = typen.size
        val muster = ArrayList<List<Int>>()
        for (i in 0 until n) {
            var k = 0
            while (k < bedarf[i] && passt(g, List(k + 1) { typen[i] })) k += 1
            if (k == 0) return Pair(emptyList(), 0)
            muster.add(List(n) { j -> if (j == i) k else 0 })
        }
        var vollstaendig = false
        var ergebnis: SimplexErgebnis? = null
        for (runde in 0 until MUSTER_MAX_RUNDEN) {
            val e = simplexMax(DoubleArray(n) { bedarf[it].toDouble() },
                muster.map { m -> DoubleArray(n) { m[it].toDouble() } }, DoubleArray(muster.size) { 1.0 })
            ergebnis = e
            if (!e.geloest) break
            val (m, ganz) = bestesMuster(g, typen, bedarf, DoubleArray(n) { max(e.y[it], 0.0) })
            val s = if (m == null) 0.0 else Py.summe((0 until n).map { e.y[it] * m[it] })
            if (m == null || s <= 1 + 1e-7) {
                vollstaendig = ganz
                break
            }
            if (muster.contains(m.toList())) break
            muster.add(m.toList())
        }
        val e = ergebnis!!
        val schranke = if (vollstaendig && e.geloest && g.teile.none { verschachtelbar(g, it) }) ceilInt(e.wert - 1e-6) else 0
        var rest = bedarf.copyOf()
        val vorrat = LinkedHashMap<List<Any>, MutableList<Teil>>()
        for ((k, v) in gruppen) vorrat[k] = v.toMutableList()
        val stangen = ArrayList<List<Teil>>()
        // wie zip() in Python: nach der letzten Runde kann ein Muster mehr da sein als Schattenpreise
        val paare = (0 until min(muster.size, e.preise.size)).map { Pair(muster[it], e.preise[it]) }
            .sortedWith(Comparator { a, b ->
                val c = (-a.second).compareTo(-b.second)
                if (c != 0) c else Py.vergleiche(a.first, b.first)
            })
        for ((m, xp) in paare) {
            for (wdh in 0 until floor(xp + 1e-9).toInt()) {
                if ((0 until n).any { rest[it] < m[it] }) break
                val st = ArrayList<Teil>()
                for (i in 0 until n) repeat(m[i]) { val v = vorrat[keys[i]]!!; st.add(v.removeAt(v.size - 1)) }
                stangen.add(st)
                rest = IntArray(n) { rest[it] - m[it] }
            }
        }
        val uebrig = keys.flatMap { vorrat[it]!! }
        if (uebrig.isNotEmpty()) {
            val h = g.kopie(teile = uebrig.toMutableList(), bewiesen = false, schranke = 0)
            val wahl = listOf(aufloesen(h, bestFit(h, uebrig)), aufloesen(h, firstFit(h, uebrig)), musterFolge(h))
            stangen += wahl.minBy { it.size }
        }
        return Pair(aufloesen(g, stangen), schranke)
    }

    fun musterFolge(g: Gruppe): MutableList<MutableList<Teil>> {
        val gruppen = typGruppen(g)
        val keys = typSchluessel(gruppen)
        val typen = keys.map { gruppen[it]!![0] }
        var bedarf = IntArray(keys.size) { gruppen[keys[it]]!!.size }
        val wert = DoubleArray(typen.size) { typen[it].laenge.pow(1.2) }
        val stangen = ArrayList<List<Teil>>()
        while (bedarf.sum() != 0) {
            val (m, _) = bestesMuster(g, typen, bedarf, wert)
            if (m == null || m.sum() == 0) {
                for (k in keys) for (t in gruppen[k]!!) stangen.add(listOf(t))
                break
            }
            val wdh = m.indices.filter { m[it] != 0 }.minOf { bedarf[it] / m[it] }
            repeat(wdh) {
                val st = ArrayList<Teil>()
                for (i in m.indices) repeat(m[i]) { val v = gruppen[keys[i]]!!; st.add(v.removeAt(v.size - 1)) }
                stangen.add(st)
                bedarf = IntArray(bedarf.size) { bedarf[it] - m[it] }
            }
        }
        return aufloesen(g, stangen)
    }

    /** Einfache manuelle Einteilung: Eingabereihenfolge, keine Drehung, Stange voll, dann nächste. */
    fun manuell(g: Gruppe): List<List<Teil>> {
        val stangen = ArrayList<List<Teil>>()
        var aktuell = ArrayList<Teil>()
        for (t in g.teile.sortedWith(compareBy<Teil>({ it.zeile }, { it.nr }))) {
            if (aktuell.isNotEmpty() && verbrauch(g, (aktuell + t).map { Lage(it, 0.0) }) > g.nutzbarBis + EPS) {
                stangen.add(aktuell)
                aktuell = ArrayList()
            }
            aktuell.add(t)
        }
        if (aktuell.isNotEmpty()) stangen.add(aktuell)
        return stangen
    }

    /** Stangen, wenn kein Teil gedreht werden dürfte; null = keine drehbaren Teile mit Gehrung. */
    fun ohneDrehung(g: Gruppe): Int? {
        if (g.teile.none { verschachtelbar(g, it) && drehungen(g, it).size > 1 }) return null
        val h = g.kopie(
            teile = g.teile.map { if (it.drehung == FREI) it.kopie(drehung = UNBEKANNT) else it }.toMutableList(),
            bewiesen = false, schranke = 0
        )
        return optimiere(h).size
    }

    fun untergrenze(g: Gruppe): Int {
        if (g.teile.isEmpty()) return 0
        val nutz = g.nutzbarBis - g.endbeschnitt
        return ceilInt(Py.summe(g.teile.map { mindestbedarf(g, it) }) / nutz - EPS)
    }

    // -------------------------------------------------------------- Zuschnitt langer Lieferstangen
    fun werkstueckLaenge(g: Gruppe, folge: List<Lage>): Int = ceilInt(verbrauch(g, folge) + g.greiferrest - EPS)

    fun zuschnittBelegt(laengen: List<Int>, saege: Double): Double =
        laengen.sum() + saege * max(laengen.size - 1, 0)

    fun zuschnittZiele(g: Gruppe, lieferlaenge: Double, maxWerkstueck: Double, saege: Double,
                       minWerkstueck: Double = 0.0, puffer: Double = 0.0): List<Int> {
        val noetig = max(g.endbeschnitt + g.teile.maxOf { it.laenge } + g.kerf + g.greiferrest + puffer, minWerkstueck)
        val ziele = (1..ZUSCHNITT_TEILUNG).map {
            min(maxWerkstueck, floorInt((lieferlaenge - (it - 1) * saege) / it + EPS).toDouble()).toInt()
        }.toSet()
        return ziele.filter { it + EPS >= noetig }.sortedDescending()
    }

    data class Werkstueck(val laenge: Int, val folge: List<Lage>)

    /** Zweistufige Planung langer Lieferstangen; null, wenn ein Teil in kein Werkstück passt. */
    fun zuschnitt(g: Gruppe, lieferlaenge: Double, maxWerkstueck: Double, saege: Double,
                  minWerkstueck: Double = 0.0, puffer: Double = 0.0): List<List<Werkstueck>>? {
        if (g.teile.isEmpty()) return emptyList()
        var beste: Pair<List<Int>, List<List<Werkstueck>>>? = null
        val mindest = ceilInt(minWerkstueck - EPS)
        val puf = ceilInt(puffer - EPS)
        for (ziel in zuschnittZiele(g, lieferlaenge, maxWerkstueck, saege, mindest.toDouble(), puf.toDouble())) {
            val h = g.kopie(stange = (ziel - puf).toDouble(), teile = g.teile.toMutableList())
            val folgen = optimiere(h)
            val laengen = folgen.map { max(werkstueckLaenge(g, it) + puf, mindest) }
            val p = Gruppe(g.profil, g.werkstoff, lieferlaenge + saege, 0.0, 0.0, saege, 0.0, g.oberflaeche)
            p.teile = laengen.mapIndexed { i, l -> Teil(i, null, "", 1, l.toDouble(), true, true, 0.0, 0.0) }.toMutableList()
            if (laengen.any { it > lieferlaenge + EPS }) continue
            val verteilt = optimiere(p)
            val stangen = verteilt.map { f ->
                f.sortedWith(compareBy<Lage>({ -it.teil.laenge }, { it.teil.zeile }))
                    .map { Werkstueck(laengen[it.teil.zeile], folgen[it.teil.zeile]) }
            }
            val wert = listOf(stangen.size, folgen.size, -folgen.sumOf { gemeinsameSchnitte(it) }, -ziel)
            if (beste == null || Py.vergleiche(wert, beste.first) < 0) beste = Pair(wert, stangen)
        }
        return beste?.let { restlaengeAnhaengen(it.second, lieferlaenge, maxWerkstueck, saege) }
    }

    fun restlaengeAnhaengen(stangen: List<List<Werkstueck>>, lieferlaenge: Double, maxWerkstueck: Double,
                            saege: Double): List<List<Werkstueck>> = stangen.map { s ->
        val rest = lieferlaenge - zuschnittBelegt(s.map { it.laenge }, saege)
        if (s.isNotEmpty() && rest > EPS) {
            val letzte = s.last()
            val neu = floorInt(letzte.laenge + rest + EPS)
            if (neu <= maxWerkstueck + EPS) s.dropLast(1) + Werkstueck(neu, letzte.folge) else s
        } else s
    }

    fun pruefeZuschnitt(g: Gruppe, stangen: List<List<Werkstueck>>, lieferlaenge: Double, maxWerkstueck: Double,
                        saege: Double, minWerkstueck: Double = 0.0) {
        val ids = stangen.flatMap { s -> s.flatMap { w -> w.folge.map { Pair(it.teil.zeile, it.teil.nr) } } }
            .sortedWith(compareBy({ it.first }, { it.second }))
        val soll = g.teile.map { Pair(it.zeile, it.nr) }.sortedWith(compareBy({ it.first }, { it.second }))
        if (ids != soll) throw AssertionError("${g.profil}: Teile fehlen oder doppelt (Zuschnitt)")
        for (s in stangen) {
            for (w in s) {
                if (w.laenge > maxWerkstueck + EPS) throw AssertionError("${g.profil}: Werkstück zu lang")
                if (minWerkstueck != 0.0 && w.laenge + EPS < minWerkstueck) throw AssertionError("${g.profil}: Werkstück zu kurz")
                if (verbrauch(g, w.folge) + g.greiferrest > w.laenge + EPS) throw AssertionError("${g.profil}: Werkstück überbelegt")
            }
            if (zuschnittBelegt(s.map { it.laenge }, saege) > lieferlaenge + EPS) {
                throw AssertionError("${g.profil}: Lieferstange überbelegt")
            }
        }
    }

    // -------------------------------------------------------------- Profile
    val OFFEN = setOf("U-Profil", "C-Profil", "L-Profil", "Flachstahl", "I-/H-Träger", "T-Profil")

    fun umfang(form: String, a: Double, b: Double?, wand: Double? = null, flaeche: Double? = null): Double = when {
        form == "Rundrohr" -> Math.PI * a
        form == "Quadratrohr" -> 4 * a
        form == "Rechteckrohr" -> 2 * (a + (if (b == null || b == 0.0) a else b))
        form == "I-/H-Träger" && b != null && b != 0.0 -> 2 * a + 4 * b - 2 * (wand ?: 0.0)
        form == "T-Profil" && b != null && b != 0.0 -> 2 * a + 2 * b
        form in OFFEN && wand != null && wand != 0.0 && flaeche != null && flaeche != 0.0 -> 2 * flaeche / wand + 2 * wand
        else -> 0.0
    }

    fun schnittlaenge(form: String, a: Double, b: Double?, wand: Double? = null, flaeche: Double? = null): Double {
        val u = umfang(form, a, b, wand, flaeche)
        return if (form in OFFEN) u / 2 else u
    }

    // -------------------------------------------------------------- Kontrolle
    /** Unabhängige Kontrolle: keine Stange überbelegt, jedes Teil genau einmal eingeplant. */
    fun pruefe(gruppen: List<Gruppe>, ergebnisse: List<List<List<Lage>>>) {
        for ((g, folgen) in gruppen.zip(ergebnisse)) {
            val ids = folgen.flatMap { f -> f.map { Pair(it.teil.zeile, it.teil.nr) } }.sortedWith(compareBy({ it.first }, { it.second }))
            val soll = g.teile.map { Pair(it.zeile, it.nr) }.sortedWith(compareBy({ it.first }, { it.second }))
            if (ids != soll) throw AssertionError("${g.profil}: Teile fehlen oder doppelt")
            for (f in folgen) {
                if (verbrauch(g, f) > g.nutzbarBis + EPS) throw AssertionError("${g.profil}: Stange überbelegt")
                pruefeDrehungen(g, f)
            }
        }
    }

    fun pruefeDrehungen(g: Gruppe, folge: List<Lage>) {
        val lagen = nahtLagen(g, folge.map { it.teil })
        if (lagen.isEmpty()) throw AssertionError("${g.profil}: feste Naht auf Breit- und Schmalseite auf einer Stange")
        if (lagen.none { s -> folge.all { it.drehung in drehungen(g, it.teil, s) } }) {
            throw AssertionError("${g.profil}: unzulässige Drehung um die Längsachse")
        }
        for ((a, b) in folge.zipWithNext()) {
            if (a.teil.bGehrung != null && b.teil.aGehrung != null && g.querschnitt != null &&
                !(a.teil.bGerade && b.teil.aGerade) && ineinander(g, a.teil, a.drehung, b.teil, b.drehung)
            ) {
                if (gehrungTrennung(g, a.teil.bGehrung, a.drehung, b.teil.aGehrung, b.drehung) <
                    trennungTeile(g, a.teil, a.drehung, b.teil, b.drehung) - EPS
                ) throw AssertionError("${g.profil}: Gehrungen enger als der Abstand")
            }
        }
    }
}
