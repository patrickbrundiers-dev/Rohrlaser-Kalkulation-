// Android-App „Rohrlaser Angebotskalkulation“ (nur Handy). Rechenkern aus ../kern (eingebundener Build).
// Gebaut wird nur im Linux-Check auf GitHub (Workflow Android), dort ist das Android-SDK installiert.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "RohrlaserApp"
includeBuild("../kern")
