package de.brundiers.rohrlaser

import java.text.DecimalFormat
import java.text.DecimalFormatSymbols
import java.util.Locale

private val DE = DecimalFormatSymbols(Locale.GERMANY)

/** Zahl deutsch mit höchstens [stellen] Nachkommastellen, z. B. 1.234,5. */
fun zahl(x: Double, stellen: Int = 1): String =
    DecimalFormat("#,##0" + if (stellen > 0) "." + "#".repeat(stellen) else "", DE).format(x)

fun prozent(x: Double): String = DecimalFormat("0.0", DE).format(x * 100) + " %"

/** Eingabe deutsch (1.234,5) oder mit Punkt als Dezimalzeichen (0.2); leer oder ungültig = null. */
fun liesZahl(text: String): Double? {
    val t = text.trim()
    return (if (',' in t) t.replace(".", "").replace(',', '.') else t).toDoubleOrNull()
}
