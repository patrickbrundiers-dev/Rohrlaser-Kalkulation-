// Rechenkern der Android-App: reines Kotlin ohne Android, damit er überall (auch ohne Android-SDK) gebaut und gegen
// das PC-Programm getestet werden kann. Die App bindet ihn als eingebundenen Build ein (app/settings.gradle.kts).
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
dependencyResolutionManagement {
    repositories {
        mavenCentral()
        gradlePluginPortal()
    }
}
rootProject.name = "kern"
