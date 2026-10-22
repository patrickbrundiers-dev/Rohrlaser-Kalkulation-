package de.brundiers.rohrlaser

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.ui.graphics.Color

/** Machbarkeitsprobe der Android-App: eine Seite „Stangen optimieren“ mit dem Rechenkern des PC-Programms. */
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            MaterialTheme(colorScheme = lightColorScheme(primary = BLAU, secondary = ORANGE)) {
                StangenSeite()
            }
        }
    }
}

val BLAU = Color(0xFF1F3A5F)
val ORANGE = Color(0xFFE8792B)
