package de.brundiers.rohrlaser.kern

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertTrue

class StangenplanTest {
    @Test
    fun beispielGelaender() {
        // ABN-01 der Abnahme (RR 42,4x2,0 auf T11): Handlauf schräg/schräg, Pfosten mit schrägem Ende B
        val plan = Stangenplanung.rechne(
            Stangenwerte(),
            listOf(
                Teileingabe("Handlauf", 3480.0, 6, aGerade = false, bGerade = false),
                Teileingabe("Pfosten", 1050.0, 24, bGerade = false),
                Teileingabe("Knieleiste", 1180.0, 18),
                Teileingabe("Wandhalter", 95.0, 30),
            )
        )
        assertEquals(78, plan.stangen.sumOf { it.folge.size })
        assertTrue(plan.stangen.size >= plan.untergrenze)
        assertTrue(plan.stangen.size <= plan.manuell)
        assertTrue(plan.stangen.all { it.belegt <= 6000 - 142 + 1e-6 })
        assertTrue(plan.ausnutzung in 0.5..1.0)
        assertEquals(plan.materiallaenge, plan.nutzlaenge + plan.verschnitt, 1e-6)
    }

    @Test
    fun zuLangesTeilNichtEingeplant() {
        val plan = Stangenplanung.rechne(Stangenwerte(), listOf(Teileingabe("lang", 5900.0, 2), Teileingabe("kurz", 500.0, 3)))
        assertEquals(listOf("lang"), plan.nichtEingeplant.map { it.bezeichnung })
        assertEquals(1, plan.stangen.size)
    }
}
