package de.brundiers.rohrlaser

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import de.brundiers.rohrlaser.kern.Anzeige
import de.brundiers.rohrlaser.kern.Stammdaten

@Composable
fun StartSeite(stammdaten: Stammdaten?, ablage: StammdatenAblage, onEingelesen: (Stammdaten) -> Unit,
               onSeite: (Seite) -> Unit) {
    val context = LocalContext.current
    var meldung by remember { mutableStateOf("") }
    var fehler by remember { mutableStateOf(false) }
    val waehlen = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        try {
            val text = context.contentResolver.openInputStream(uri)!!.use { it.readBytes().toString(Charsets.UTF_8) }
            val s = ablage.speichern(text)
            onEingelesen(s)
            meldung = "Stammdaten eingelesen: ${s.tabelle("profile")?.zeilen?.size ?: 0} Profile, " +
                "${s.maschinen().size} Maschinen, ${s.tabelle("kunden")?.zeilen?.size ?: 0} Kunden."
            fehler = false
        } catch (e: IllegalArgumentException) {
            meldung = e.message ?: "Die Datei lässt sich nicht lesen."
            fehler = true
        } catch (e: Exception) {
            meldung = "Die Datei lässt sich nicht lesen: ${e.message}"
            fehler = true
        }
    }
    Rahmen("Rohrlaser", null) { innen ->
        Column(
            Modifier.fillMaxSize().padding(innen).padding(16.dp).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Button(onClick = { onSeite(Seite.Stangen) }, modifier = Modifier.fillMaxWidth()) { Text("Stangen optimieren") }
            Card(Modifier.fillMaxWidth()) {
                Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Stammdaten", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
                    if (stammdaten == null) {
                        Text("Noch keine Stammdaten. Am PC unter Datei → „Stammdaten fürs Handy exportieren …“ eine Datei " +
                            "erstellen, aufs Handy bringen (z. B. per E-Mail) und hier einlesen.")
                    } else {
                        Text("Stand ${Anzeige.zeit(stammdaten.erstellt)} vom PC-Programm ${stammdaten.programm}. " +
                            "Nur zum Ansehen; geändert wird am PC, danach neu einlesen.")
                        OutlinedButton(onClick = { onSeite(Seite.Stammdatenliste) }, modifier = Modifier.fillMaxWidth()) {
                            Text("Stammdaten ansehen")
                        }
                    }
                    Button(onClick = { waehlen.launch(arrayOf("application/json", "text/plain", "application/octet-stream")) },
                        modifier = Modifier.fillMaxWidth()) {
                        Text(if (stammdaten == null) "Stammdaten einlesen" else "Stammdaten neu einlesen (ersetzt alle)")
                    }
                    if (meldung.isNotEmpty()) Text(meldung, color = if (fehler) ROT else BLAU)
                }
            }
            Spacer(Modifier.height(8.dp))
            Text("Testversion: Angebote, Kalkulation und PDFs folgen in den nächsten Schritten.",
                style = MaterialTheme.typography.bodySmall)
        }
    }
}
