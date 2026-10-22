import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application") version "8.10.1"
    id("org.jetbrains.kotlin.android") version "2.1.21"
    id("org.jetbrains.kotlin.plugin.compose") version "2.1.21"
}

// Versionsnummer der App (unabhängig vom PC-Programm); versionCode muss bei jeder ausgelieferten APK steigen.
val appVersion = "0.1.0"
val appVersionCode = 1

android {
    namespace = "de.brundiers.rohrlaser"
    compileSdk = 35

    defaultConfig {
        applicationId = "de.brundiers.rohrlaser"
        minSdk = 26
        targetSdk = 35
        versionCode = appVersionCode
        versionName = appVersion
    }

    // Signatur aus Umgebungsvariablen (Workflow Android: Secret ANDROID_SIGNATUR oder ein Testschlüssel).
    val schluessel = System.getenv("ANDROID_SIGNATUR_DATEI")
    signingConfigs {
        if (schluessel != null) {
            create("freigabe") {
                storeFile = file(schluessel)
                storePassword = System.getenv("ANDROID_SIGNATUR_PASSWORT")
                keyAlias = System.getenv("ANDROID_SIGNATUR_ALIAS") ?: "rohrlaser"
                keyPassword = System.getenv("ANDROID_SIGNATUR_PASSWORT")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (schluessel != null) signingConfig = signingConfigs.getByName("freigabe")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
    }
}

kotlin {
    compilerOptions { jvmTarget.set(JvmTarget.JVM_17) }
}

dependencies {
    implementation("de.brundiers.rohrlaser:kern:0.1.0")
    implementation(platform("androidx.compose:compose-bom:2025.05.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.core:core-ktx:1.16.0")
}
