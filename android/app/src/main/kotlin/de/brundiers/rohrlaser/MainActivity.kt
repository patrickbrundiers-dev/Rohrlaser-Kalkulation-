package de.brundiers.rohrlaser

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.graphics.Color
import de.brundiers.rohrlaser.kern.Stammdaten

/** Seiten der App; zurück führt immer eine Ebene höher. */
sealed class Seite(val zurueck: Seite?) {
    data object Start : Seite(null)
    data object Stangen : Seite(Start)
    data object Stammdatenliste : Seite(Start)
    data class Tabelle(val name: String) : Seite(Stammdatenliste)
    data object Einstellungen : Seite(Stammdatenliste)
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val ablage = StammdatenAblage(filesDir)
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = BLAU, secondary = ORANGE)) {
                var seite by remember { mutableStateOf<Seite>(Seite.Start) }
                var stammdaten by remember { mutableStateOf(ablage.laden()) }
                BackHandler(enabled = seite.zurueck != null) { seite = seite.zurueck!! }
                val zurueck = { seite = seite.zurueck ?: Seite.Start }
                when (val s = seite) {
                    Seite.Start -> StartSeite(stammdaten, ablage, onEingelesen = { stammdaten = it }, onSeite = { seite = it })
                    Seite.Stangen -> StangenSeite(stammdaten, zurueck)
                    Seite.Stammdatenliste -> StammdatenSeite(stammdaten!!, zurueck, onSeite = { seite = it })
                    is Seite.Tabelle -> TabellenSeite(stammdaten!!.tabelle(s.name)!!, zurueck)
                    Seite.Einstellungen -> EinstellungenSeite(stammdaten!!, zurueck)
                }
            }
        }
    }
}

val BLAU = Color(0xFF1F3A5F)
val ORANGE = Color(0xFFE8792B)
val ROT = Color(0xFFB00020)

/** Stammdaten im App-Speicher: die zuletzt eingelesene Datei unverändert. */
class StammdatenAblage(ordner: java.io.File) {
    private val datei = java.io.File(ordner, "stammdaten.json")

    fun laden(): Stammdaten? = try {
        if (datei.exists()) Stammdaten.lies(datei.readText()) else null
    } catch (e: IllegalArgumentException) {
        null
    }

    /** Text prüfen und speichern; Ergebnis die gelesenen Stammdaten (sonst IllegalArgumentException). */
    fun speichern(text: String): Stammdaten {
        val s = Stammdaten.lies(text)
        val neu = java.io.File(datei.path + ".neu")
        neu.writeText(text)
        if (!neu.renameTo(datei)) {
            datei.delete()
            neu.renameTo(datei)
        }
        return s
    }
}
