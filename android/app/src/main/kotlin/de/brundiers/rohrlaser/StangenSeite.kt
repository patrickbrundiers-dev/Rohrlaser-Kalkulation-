package de.brundiers.rohrlaser

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import de.brundiers.rohrlaser.kern.Stangenplan
import de.brundiers.rohrlaser.kern.Stangenplanung
import de.brundiers.rohrlaser.kern.Stangenwerte
import de.brundiers.rohrlaser.kern.Teileingabe
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Eingabezeile der Teileliste (Texte, damit Komma-Eingaben erhalten bleiben). */
class Zeile(bez: String = "", laenge: String = "", stueck: String = "1", a: Boolean = true, b: Boolean = true) {
    var bezeichnung by mutableStateOf(bez)
    var laenge by mutableStateOf(laenge)
    var stueck by mutableStateOf(stueck)
    var aGerade by mutableStateOf(a)
    var bGerade by mutableStateOf(b)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun StangenSeite() {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var stange by remember { mutableStateOf("6000") }
    var end by remember { mutableStateOf("10") }
    var greifer by remember { mutableStateOf("142") }
    var kerf by remember { mutableStateOf("0,2") }
    var abstand by remember { mutableStateOf("2") }
    val zeilen = remember {
        mutableStateListOf(
            Zeile("Handlauf", "3480", "6", a = false, b = false),
            Zeile("Pfosten", "1050", "24", b = false),
            Zeile("Knieleiste", "1180", "18"),
            Zeile("Wandhalter", "95", "30"),
        )
    }
    var plan by remember { mutableStateOf<Stangenplan?>(null) }
    var fehler by remember { mutableStateOf("") }
    var rechnet by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Stangen optimieren") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = BLAU, titleContentColor = Color.White
                )
            )
        }
    ) { innen ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(innen).padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            item {
                Spacer(Modifier.height(8.dp))
                Text("Stange und Maschine [mm]", style = MaterialTheme.typography.titleMedium)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Feld("Stangenlänge", stange, Modifier.weight(1f)) { stange = it }
                    Feld("Endbeschnitt", end, Modifier.weight(1f)) { end = it }
                    Feld("Greiferrest", greifer, Modifier.weight(1f)) { greifer = it }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Feld("Schnittverlust", kerf, Modifier.weight(1f)) { kerf = it }
                    Feld("Abstand 2 Schnitte", abstand, Modifier.weight(1f)) { abstand = it }
                }
                Spacer(Modifier.height(8.dp))
                Text("Teile (eine Profilabmessung)", style = MaterialTheme.typography.titleMedium)
            }
            itemsIndexed(zeilen) { i, z ->
                TeilKarte(z, onEntfernen = { zeilen.removeAt(i) })
            }
            item {
                OutlinedButton(onClick = { zeilen.add(Zeile()) }) { Text("+ Teil") }
                Spacer(Modifier.height(8.dp))
                Button(
                    enabled = !rechnet,
                    modifier = Modifier.fillMaxWidth(),
                    onClick = {
                        val werte = Stangenwerte(
                            liesZahl(stange) ?: 0.0, liesZahl(end) ?: 0.0, liesZahl(greifer) ?: 0.0,
                            liesZahl(kerf) ?: 0.0, liesZahl(abstand) ?: 0.0
                        )
                        val eingaben = zeilen.mapIndexed { i, z ->
                            Teileingabe(z.bezeichnung.ifBlank { "Teil ${i + 1}" }, liesZahl(z.laenge) ?: 0.0,
                                liesZahl(z.stueck)?.toInt() ?: 0, z.aGerade, z.bGerade)
                        }
                        fehler = when {
                            werte.stange <= werte.greiferrest + werte.endbeschnitt -> "Stangenlänge zu kurz."
                            eingaben.none { it.laenge > 0 && it.stueck > 0 } -> "Bitte mindestens ein Teil mit Länge und Stückzahl."
                            else -> ""
                        }
                        if (fehler.isEmpty()) {
                            rechnet = true
                            scope.launch {
                                plan = withContext(Dispatchers.Default) { Stangenplanung.rechne(werte, eingaben) }
                                rechnet = false
                            }
                        }
                    }
                ) { Text("Optimieren") }
                if (rechnet) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(Modifier.padding(8.dp))
                        Text("rechnet …")
                    }
                }
                if (fehler.isNotEmpty()) Text(fehler, color = Color(0xFFB00020))
            }
            plan?.let { p ->
                item { Auswertung(p, onTeilen = { teilePdf(context, p) }) }
                itemsIndexed(p.stangen) { i, s -> StangenKarte(i + 1, p, s) }
                item { Spacer(Modifier.height(24.dp)) }
            }
        }
    }
}

@Composable
private fun Feld(titel: String, wert: String, modifier: Modifier, onWert: (String) -> Unit) {
    OutlinedTextField(
        value = wert, onValueChange = onWert, label = { Text(titel, maxLines = 1) }, singleLine = true,
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = modifier
    )
}

@Composable
private fun TeilKarte(z: Zeile, onEntfernen: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                OutlinedTextField(
                    value = z.bezeichnung, onValueChange = { z.bezeichnung = it }, label = { Text("Bezeichnung") },
                    singleLine = true, modifier = Modifier.weight(1f)
                )
                TextButton(onClick = onEntfernen) { Text("Entfernen") }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Feld("Länge [mm]", z.laenge, Modifier.weight(1f)) { z.laenge = it }
                Feld("Stück", z.stueck, Modifier.weight(1f)) { z.stueck = it }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked = z.aGerade, onCheckedChange = { z.aGerade = it })
                Text("Ende A gerade")
                Spacer(Modifier.width(12.dp))
                Checkbox(checked = z.bGerade, onCheckedChange = { z.bGerade = it })
                Text("Ende B gerade")
            }
        }
    }
}

@Composable
private fun Auswertung(p: Stangenplan, onTeilen: () -> Unit) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("${p.stangen.size} Stangen à ${zahl(p.werte.stange, 0)} mm",
                style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold)
            Text(p.bewertung)
            Text("Untergrenze ${p.untergrenze} · einfache Einteilung ${p.manuell} Stangen")
            Text("Nutzlänge ${zahl(p.nutzlaenge / 1000, 2)} m · Verschnitt ${zahl(p.verschnitt / 1000, 2)} m")
            Text("Materialausnutzung ${prozent(p.ausnutzung)}")
            if (p.nichtEingeplant.isNotEmpty()) {
                Text("Nicht eingeplant (passt nicht auf eine Stange): " +
                    p.nichtEingeplant.joinToString { it.bezeichnung }, color = Color(0xFFB00020))
            }
            Button(onClick = onTeilen, modifier = Modifier.fillMaxWidth()) { Text("Schnittplan als PDF teilen") }
        }
    }
}

private val TEILFARBEN = listOf(
    Color(0xFF4E79A7), Color(0xFFF28E2B), Color(0xFF59A14F), Color(0xFFB07AA1), Color(0xFF76B7B2),
    Color(0xFFEDC948), Color(0xFFE15759), Color(0xFF9C755F)
)

fun teilfarbe(zeile: Int) = TEILFARBEN[zeile % TEILFARBEN.size]

@Composable
private fun StangenKarte(nr: Int, p: Stangenplan, s: de.brundiers.rohrlaser.kern.PlanStange) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(12.dp)) {
            Text("Stange $nr · Rest ${zahl(s.rest)} mm", fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(6.dp))
            Canvas(Modifier.fillMaxWidth().height(28.dp)) {
                val mm = size.width / p.werte.stange.toFloat()
                drawRect(Color(0xFFDDE3EA), size = size)
                var x = p.werte.endbeschnitt.toFloat()
                for ((i, l) in s.folge.withIndex()) {
                    if (i > 0) {
                        val vorher = s.folge[i - 1].teil
                        x += if (vorher.bGerade && l.teil.aGerade) p.werte.schnittverlust.toFloat()
                        else (2 * p.werte.schnittverlust + p.werte.abstand).toFloat()
                    }
                    drawRect(teilfarbe(l.teil.zeile), Offset(x * mm, 0f), Size(l.teil.laenge.toFloat() * mm, size.height))
                    x += l.teil.laenge.toFloat()
                }
                val greifer = (p.werte.stange - p.werte.greiferrest).toFloat() * mm
                drawRect(Color(0xFF8A9BB0), Offset(greifer, 0f), Size(size.width - greifer, size.height))
            }
            Spacer(Modifier.height(6.dp))
            val anzahl = LinkedHashMap<String, Int>()
            for (l in s.folge) {
                val k = "${l.teil.artikel} ${zahl(l.teil.laenge)} mm"
                anzahl[k] = (anzahl[k] ?: 0) + 1
            }
            for ((k, n) in anzahl) Text("$n × $k", style = MaterialTheme.typography.bodyMedium)
            if (s.gemeinsameSchnitte > 0) {
                Text("${s.gemeinsameSchnitte} gemeinsame Schnitte", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

private fun teilePdf(context: Context, p: Stangenplan) {
    val datei = SchnittplanPdf.schreibe(context, p)
    val uri = FileProvider.getUriForFile(context, context.packageName + ".dateien", datei)
    val senden = Intent(Intent.ACTION_SEND).apply {
        type = "application/pdf"
        putExtra(Intent.EXTRA_STREAM, uri)
        putExtra(Intent.EXTRA_SUBJECT, "Schnittplan")
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(Intent.createChooser(senden, "Schnittplan teilen"))
}
