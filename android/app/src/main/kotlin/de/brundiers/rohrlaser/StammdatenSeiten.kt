package de.brundiers.rohrlaser

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import de.brundiers.rohrlaser.kern.Anzeige
import de.brundiers.rohrlaser.kern.StammTabelle
import de.brundiers.rohrlaser.kern.Stammdaten

@Composable
fun StammdatenSeite(s: Stammdaten, zurueck: () -> Unit, onSeite: (Seite) -> Unit) {
    Rahmen("Stammdaten", zurueck) { innen ->
        LazyColumn(Modifier.fillMaxSize().padding(innen).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)) {
            item {
                Spacer(Modifier.height(8.dp))
                Text("Stand ${Anzeige.zeit(s.erstellt)} · nur ansehen", style = MaterialTheme.typography.bodySmall)
            }
            for ((gruppe, namen) in Stammdaten.GRUPPEN) {
                val tabellen = namen.mapNotNull { s.tabelle(it) }
                if (tabellen.isEmpty()) continue
                item { Text(gruppe, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 8.dp)) }
                items(tabellen) { t ->
                    Eintrag(t.titel, "${t.zeilen.size}") { onSeite(Seite.Tabelle(t.name)) }
                }
            }
            item { Text("Programm", style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 8.dp)) }
            item { Eintrag("Einstellungen", "${s.beschreibung.size}") { onSeite(Seite.Einstellungen) } }
            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}

@Composable
private fun Eintrag(titel: String, zahl: String, onClick: () -> Unit) {
    Card(Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Row(Modifier.padding(14.dp)) {
            Text(titel, modifier = Modifier.weight(1f))
            Text(zahl, fontWeight = FontWeight.Bold)
        }
    }
}

/** Eine Tabelle: je Zeile eine Karte, Überschrift = Schlüssel (erstes Feld), darunter alle gefüllten Felder. */
@Composable
fun TabellenSeite(t: StammTabelle, zurueck: () -> Unit) {
    var suche by remember { mutableStateOf("") }
    val zeilen = remember(t.name, suche) {
        val q = suche.trim().lowercase()
        if (q.isEmpty()) t.zeilen
        else t.zeilen.filter { z -> t.felder.any { f -> Anzeige.wert(f.art, f.stellen, z[f.name]).lowercase().contains(q) } }
    }
    Rahmen(t.titel, zurueck) { innen ->
        LazyColumn(Modifier.fillMaxSize().padding(innen).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item {
                OutlinedTextField(value = suche, onValueChange = { suche = it }, label = { Text("Suchen") },
                    singleLine = true, modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
                Text("${zeilen.size} von ${t.zeilen.size}", style = MaterialTheme.typography.bodySmall)
            }
            if (zeilen.isEmpty()) item { Text("Keine Einträge.") }
            items(zeilen) { z ->
                Card(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        val kopf = t.felder.firstOrNull()
                        Text(kopf?.let { Anzeige.wert(it.art, it.stellen, z[it.name]) }.orEmpty().ifEmpty { "–" },
                            fontWeight = FontWeight.Bold)
                        for (f in t.felder.drop(1)) {
                            val w = Anzeige.wert(f.art, f.stellen, z[f.name])
                            if (w.isNotEmpty()) Text("${f.titel}: $w", style = MaterialTheme.typography.bodyMedium)
                        }
                    }
                }
            }
            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}

@Composable
fun EinstellungenSeite(s: Stammdaten, zurueck: () -> Unit) {
    Rahmen("Einstellungen", zurueck) { innen ->
        LazyColumn(Modifier.fillMaxSize().padding(innen).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for ((gruppe, liste) in s.beschreibung.groupBy { it.gruppe }) {
                item { Text(gruppe, style = MaterialTheme.typography.titleMedium, modifier = Modifier.padding(top = 10.dp)) }
                items(liste) { e ->
                    Column {
                        Text(e.titel, style = MaterialTheme.typography.bodySmall)
                        Text(Anzeige.wert(e.art, null, s.einstellungen[e.name]).ifEmpty { "–" })
                    }
                }
            }
            item { Spacer(Modifier.height(16.dp)) }
        }
    }
}
