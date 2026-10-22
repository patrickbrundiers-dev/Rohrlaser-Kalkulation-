package de.brundiers.rohrlaser

import android.content.Context
import android.graphics.Paint
import android.graphics.Typeface
import android.graphics.pdf.PdfDocument
import androidx.compose.ui.graphics.toArgb
import de.brundiers.rohrlaser.kern.Stangenplan
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Schnittplan als PDF (A4 hoch) mit dem Android-eigenen PDF-Erzeuger: Kennzahlen und je Stange Bild und Teile. */
object SchnittplanPdf {
    private const val BREITE = 595      // A4 in Punkt (1/72 Zoll)
    private const val HOEHE = 842
    private const val RAND = 40f

    fun schreibe(context: Context, p: Stangenplan): File {
        val doc = PdfDocument()
        val titel = Paint().apply { textSize = 18f; typeface = Typeface.DEFAULT_BOLD; color = BLAU.toArgb() }
        val fett = Paint().apply { textSize = 10f; typeface = Typeface.DEFAULT_BOLD }
        val text = Paint().apply { textSize = 10f }
        val flaeche = Paint().apply { style = Paint.Style.FILL }
        var seiteNr = 0
        var seite: PdfDocument.Page? = null
        var y = 0f

        fun neueSeite() {
            seite?.let { doc.finishPage(it) }
            seiteNr += 1
            seite = doc.startPage(PdfDocument.PageInfo.Builder(BREITE, HOEHE, seiteNr).create())
            y = RAND
            val c = seite!!.canvas
            c.drawText("Schnittplan", RAND, y + 14, titel)
            c.drawText(SimpleDateFormat("dd.MM.yyyy", Locale.GERMANY).format(Date()) + " · Seite $seiteNr",
                BREITE - RAND - 120, y + 14, text)
            y += 34
        }

        fun platz(h: Float) {
            if (seite == null || y + h > HOEHE - RAND) neueSeite()
        }

        neueSeite()
        val c0 = seite!!.canvas
        val w = p.werte
        for (zeile in listOf(
            "${p.stangen.size} Stangen à ${zahl(w.stange, 0)} mm  ·  ${p.bewertung}",
            "Endbeschnitt ${zahl(w.endbeschnitt)} mm, Greiferrest ${zahl(w.greiferrest)} mm, Schnittverlust " +
                "${zahl(w.schnittverlust)} mm, Abstand getrennte Schnitte ${zahl(w.abstand)} mm",
            "Nutzlänge ${zahl(p.nutzlaenge / 1000, 2)} m, Verschnitt ${zahl(p.verschnitt / 1000, 2)} m, " +
                "Materialausnutzung ${prozent(p.ausnutzung)}",
            "Untergrenze ${p.untergrenze} Stangen, einfache Einteilung ${p.manuell} Stangen",
        )) {
            c0.drawText(zeile, RAND, y, text)
            y += 14
        }
        if (p.nichtEingeplant.isNotEmpty()) {
            c0.drawText("Nicht eingeplant: " + p.nichtEingeplant.joinToString { it.bezeichnung }, RAND, y, fett)
            y += 14
        }
        y += 10
        val bildBreite = BREITE - 2 * RAND
        for ((i, s) in p.stangen.withIndex()) {
            val anzahl = LinkedHashMap<String, Int>()
            for (l in s.folge) {
                val k = "${l.teil.artikel} ${zahl(l.teil.laenge)} mm"
                anzahl[k] = (anzahl[k] ?: 0) + 1
            }
            platz(40f + 13f * anzahl.size)
            val c = seite!!.canvas
            c.drawText("Stange ${i + 1}  ·  Rest ${zahl(s.rest)} mm", RAND, y, fett)
            y += 6
            val mm = bildBreite / w.stange.toFloat()
            flaeche.color = 0xFFDDE3EA.toInt()
            c.drawRect(RAND, y, RAND + bildBreite, y + 14, flaeche)
            var x = w.endbeschnitt.toFloat()
            for ((j, l) in s.folge.withIndex()) {
                if (j > 0) {
                    val vorher = s.folge[j - 1].teil
                    x += if (vorher.bGerade && l.teil.aGerade) w.schnittverlust.toFloat()
                    else (2 * w.schnittverlust + w.abstand).toFloat()
                }
                flaeche.color = teilfarbe(l.teil.zeile).toArgb()
                c.drawRect(RAND + x * mm, y, RAND + (x + l.teil.laenge.toFloat()) * mm, y + 14, flaeche)
                x += l.teil.laenge.toFloat()
            }
            flaeche.color = 0xFF8A9BB0.toInt()
            c.drawRect(RAND + (w.stange - w.greiferrest).toFloat() * mm, y, RAND + bildBreite, y + 14, flaeche)
            y += 26
            for ((k, n) in anzahl) {
                c.drawText("$n × $k", RAND + 8, y, text)
                y += 13
            }
            y += 8
        }
        seite?.let { doc.finishPage(it) }
        val ordner = File(context.cacheDir, "pdf").apply { mkdirs() }
        val datei = File(ordner, "Schnittplan.pdf")
        datei.outputStream().use { doc.writeTo(it) }
        doc.close()
        return datei
    }
}
