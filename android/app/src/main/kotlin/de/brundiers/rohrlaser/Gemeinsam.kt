package de.brundiers.rohrlaser

import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** Seitenrahmen: Titelleiste (mit „Zurück“, wenn es eine Ebene höher gibt) und Inhalt. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Rahmen(titel: String, zurueck: (() -> Unit)?, inhalt: @Composable (PaddingValues) -> Unit) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(titel) },
                navigationIcon = {
                    if (zurueck != null) TextButton(onClick = zurueck) { Text("‹ Zurück", color = Color.White) }
                },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = BLAU, titleContentColor = Color.White)
            )
        },
        content = inhalt
    )
}
