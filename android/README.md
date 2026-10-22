# Android-App (Rohrlaser Angebotskalkulation für das Handy)

Neubau in Kotlin (Jetpack Compose), nur Handy, ohne STEP-Import und ohne Datenabgleich mit dem PC
(Plan und Entscheidungen: Projektordner `kalkulation/android/Plan_Android.md`).

- `kern/` – Rechenkern in reinem Kotlin, ohne Android. Übertragung der Rechnung aus `programm/rohrlaser`.
  Tests: `./gradlew -p kern test` (geht ohne Android-SDK).
- `app/` – die App. Bindet `kern` als eingebundenen Build ein. Bauen: `./gradlew -p app assembleRelease`
  (braucht das Android-SDK; auf GitHub im Workflow Android).

## Gleich rechnen wie das PC-Programm

`tests/android_paritaet.py` schreibt Eingaben und Ergebnisse des PC-Programms nach
`kern/src/test/resources/optimierung_faelle.json`; die Kotlin-Tests müssen jede Stange gleich belegen.
Der Linux-Check des PC-Programms prüft, ob die Datei zur aktuellen Python-Rechnung passt. Ändert sich die Rechnung:

1. `python tests/android_paritaet.py --schreiben`
2. dieselbe Änderung in `kern/` nachziehen, bis `./gradlew -p kern test` grün ist.

Python ab 3.12 rechnet `sum()` kompensiert (Neumaier); der Kern macht das mit `Py.summe` nach, sonst kippen
Gleichstände zwischen zwei gleich guten Einteilungen.

## Stand

Schritt 1 (Machbarkeitsprobe): Stangenoptimierung samt Zuschnitt langer Lieferstangen, Seite „Stangen optimieren“,
Schnittplan als PDF teilen.
