# Pre-Update-Systemcheck (Auftrag Patrick 19.11.2026, Version 0.9.412)

Auftrag: vor dem nächsten Sammel-Update alle Abläufe messen (Zeit, CPU, RAM, Datenbank, unnötige Rechnungen),
Engpässe nach Priorität beheben, jede Änderung mit Messwerten und Regressionstests belegen. Ergebnisse, Funktionen
und Datenbank bleiben unverändert. Der Bericht baut auf SYSTEM_UPDATE_1911.md (#572) und ANGEBOTS_CACHE_1911.md
(#574) auf.

## Phase 1: Sicherung und Messwerkzeug

- Ausgangsstand: main 0.9.408 (7122f7e, mit #575 „nur PostgreSQL“ und Messsystem M1/M2).
- Neues Werkzeug `werkzeuge/systemcheck.py`: misst jeden Ablauf im echten Hauptfenster (Qt offscreen, PostgreSQL
  je Messung neu) mit Zeit, Prozessorzeit, Arbeitsspeicher (aktuell und Spitze), Anzahl und Dauer der
  Datenbank-Anweisungen und doppelten Rechnungen (diagnose). Ein **Fingerabdruck** über alle Kalkulationen und
  Positionswerte am Anfang und am Ende belegt, dass die Ergebnisse gleich bleiben. `--vergleich ALT NEU` zeigt
  die Tabelle vorher/nachher, `--profil` schreibt Profile je Ablauf.
- Messdaten: echtes Angebot aus einem Support-Paket (33 STEP-Dateien, 38 Positionen). Die Kundendateien liegen
  nicht im Repository.
- Fairer Vergleich: alter und neuer Stand jeweils als eigene Kopie mit vorab übersetzten Python-Dateien, gleicher
  Rechner (4 Kerne), gleiche Reihenfolge.

## Phase 2: Basismessung (0.9.408)

| Ablauf | Zeit | CPU | RAM danach | SQL |
|---|---:|---:|---:|---:|
| Programmstart (Module laden) | 0,41 s | | | |
| Datendatei öffnen (neu, mit Grunddaten) | 1,20 s | 0,57 s | 126 MB | 1.944 |
| Hauptfenster aufbauen | 1,32 s | 1,25 s | 274 MB | 359 |
| STEP-Import 33 Dateien | 204 s | 17,8 s* | 447 MB | 693 |
| Angebot öffnen (kalt) | 0,62 s | 0,57 s | 458 MB | 101 |
| Angebot neu laden (warm) | 0,36 s | 0,39 s | 469 MB | 52 |
| Wechsel Liste ↔ Angebot | 0,005 s | | | 4 |
| Zelle ändern mit Prüfung | 1,17 s | 1,61 s | 512 MB | 135 |
| Optimieren | 0,54 s | 0,52 s | 538 MB | 59 |
| Gesamtkalkulation | 0,018 s | | | 4 |
| Unterreiter durchklicken | 0,09 s | | | 4 |
| Angebotsliste laden / suchen | 0,002 s / 0,000 s | | | 4 / 0 |
| 3D-Ansicht öffnen | 0,08 s | | 555 MB | 1 |
| 3D: zehn Teile zeigen | 1,78 s | 1,76 s | 569 MB | 52 |
| 3D: 360° drehen (36 Bilder) | 6,4 s (178 ms/Bild) | 6,4 s | 575 MB | 0 |
| 3D: zoomen (20 Bilder) | 0,97 s | | | 0 |
| Messen (Körper, Flächen, Volumen) | 0,54 s | | 587 MB | 0 |
| Rohr-Editor öffnen | 1,11 s | | 664 MB | 6 |
| Angebots-PDF | 1,30 s | | 686 MB | 142 |
| Werkstatt-PDF | 1,74 s | | 714 MB | 49 |

\* Der STEP-Import rechnet in Hilfsprozessen; im Programm selbst laufen nur 17,8 s der 204 s.

Doppelte Rechnungen: in allen Abläufen **0**. Datenbank-Zeit ist überall klein (höchstens 0,4 s beim Import,
sonst unter 0,07 s je Ablauf): die Datenbank ist kein Engpass.

## Phase 3: Fehler, Ursachen und Behebung

### P1 – Speicherleck beim Schließen eines Angebots (behoben)

- **Befund:** Jedes Öffnen und Schließen eines Angebots ließ die ganze Seite im Speicher (Positionen, Ergebnisse,
  3D-Netze): +8 bis 12 MB je Mal beim Angebot mit 33 Teilen, nach 15 Mal 16 tote Seiten und 586 statt 459 MB.
  An einem Arbeitstag mit vielen Angeboten wächst das Programm so um Hunderte MB und wird langsamer, weil die
  toten Seiten noch an Signalen hängen.
- **Ursache:** Die Qt-Objekte der Seite werden gelöscht, ihre Python-Hüllen bleiben in Ringen stehen
  (Seite → Tabellenmodell → Seite), die Pythons Speicherbereinigung bei PySide nicht abräumt. Dazu kamen
  Tabellenmodelle (Positionen, Staffeln, Zeiten, Listen) und der Bote der Staffeln ohne Qt-Eltern, die nie
  gelöscht wurden.
- **Behebung:** neues Modul `freigeben.py`, aufgerufen in `angebot_schliessen` vor `deleteLater`: Modelle ohne
  Eltern bekommen die Seite als Eltern, nach dem Löschen werden die Attribute der nun gelöschten Hüllen geleert.
  Ein noch lebendes Objekt wird nie angefasst (Prüfung `shiboken6.isValid`).
- **Nachweis:** 15× Öffnen/Schließen: alt 459 → 586 MB, 16 Seiten lebend; neu **472 → 472 MB, 1 Seite** (die
  offene). Zuwachs an lebenden Qt-Hüllen alt 90 je 5 Runden, neu 0. Test `tests/test_freigeben.py`.

### P2 – Bauteildaten mehrfach eingelesen (behoben)

- **Befund:** Beim Ändern einer Zelle las das Programm dieselben Bauteildaten (Spalte technik, bis mehrere hundert
  KB je Teil) über 1.200-mal neu ein; 0,41 s der Zelle-Zeit war nur JSON-Lesen.
- **Behebung:** `json_lesen.nur_lesen` merkt sich das Ergebnis je Text (höchstens 2.048 Einträge) und wird nur dort
  benutzt, wo das Ergebnis nachweislich nur gelesen wird: Spiegeln, Handänderungen, Verbindungselemente und die
  3D-Prüfung „aktiv“. Alle Stellen, die das Ergebnis verändern, lesen weiter frisch.
- **Nachweis:** JSON-Zeit bei 4× Zelle 0,41 → 0,26 s; Zeitgewinn siehe Vergleich.

### P2b – Kopftext je Position durchsucht (behoben, nach dem ersten Bericht)

- **Befund:** tests/test_angebot_leistung.py (200 Positionen) war in CI und lokal zeitweise rot: Zelle ändern
  1,08 bis 1,16 s bei 1,0 s Grenze. Das Profil zeigte 1.200 Aufrufe der Schnittzeit-Abfrage mit je 1 ms, obwohl alle
  aus dem Merker kamen.
- **Ursache:** Vor jedem Merker-Zugriff wurde der ganze Text des Angebotskopfs (mit dem gespeicherten Ergebnis, bei
  200 Positionen sehr lang) nach „ at 0x“ durchsucht, je Position erneut.
- **Behebung:** Die Suche läuft je Rechenlauf und Kopf einmal (rechnen._schneidzeit_teile, Merker
  repr_kopf_adresse). Gleicher Schlüssel, gleiche Werte.
- **Nachweis:** Leistungstest Zelle 1,08–1,16 → 0,53–0,62 s, Öffnen 1,19 → 0,68–0,82 s. Fingerabdruck gleich,
  test_regression_ergebnisse, test_angebots_cache, test_kalk_merker_1811 bestanden.

### P3 – Maschinenvergleich in der Prüfung (gemessen, nicht geändert)

Der Maschinenvergleich (alle Maschinen nebeneinander) kostet beim ersten Mal bis 3,0 s je Angebot und läuft mit der
Prüfung. Er ist seit #569 abschaltbar und wird danach gemerkt (55 % Treffer im Lauf). Ihn in den Hintergrund zu
legen wäre eine Umbau-Änderung am Ablauf der Prüfung; nach dem Auftrag („keine unnötigen Architekturänderungen“)
bleibt er wie er ist und steht unter „verbleibende Punkte“.

### P4 – 3D-Drehen ohne Grafikkarte (gemessen, nicht geändert)

178 ms je Bild gilt nur für die Ersatzdarstellung ohne OpenGL (Remote Desktop), die der Container allein messen kann.
Auf den Arbeitsplätzen läuft standardmäßig OpenGL („Automatisch“).

## Phase 4: Stabilisierung

- **Langzeitlauf Zelle ändern (30 Runden, ein Angebot):** Speicher steigt bis Runde 24 auf 654 MB und bleibt dann
  stehen; die Zahl der Python-Objekte wächst in 30 Runden nur um 0,2 % (Listen/Zahlen der begrenzten Merker).
  Das sind volle Zwischenspeicher mit fester Obergrenze, kein Leck.
- **Langzeitlauf Schließen/Öffnen/Ändern im Systemcheck (12 Runden):** neu 1,27 s je Runde statt 1,93 s.
- **Fehler und Warnungen:** in keinem Ablauf ein unerwarteter Fehler im Protokoll.

## Vergleich vorher/nachher (gleiche Bedingungen)

| Ablauf | vorher | nachher | Faktor |
|---|---:|---:|---:|
| Angebot öffnen (kalt) | 0,62 s | 0,45 s | 1,4× |
| Angebot neu laden (warm) | 0,36 s | 0,21 s | 1,7× |
| Zelle ändern mit Prüfung | 1,17 s | 0,81 s | 1,5× |
| Optimieren | 0,54 s | 0,32 s | 1,7× |
| Unterreiter durchklicken | 0,09 s | 0,07 s | 1,4× |
| 3D: zehn Teile zeigen | 1,78 s | 1,33 s | 1,3× |
| 3D: zoomen | 0,97 s | 0,80 s | 1,2× |
| Rohr-Editor öffnen | 1,11 s | 0,97 s | 1,2× |
| Angebots-PDF | 1,30 s | 0,86 s | 1,5× |
| Werkstatt-PDF | 1,74 s | 1,50 s | 1,2× |
| Langzeit je Runde | 1,93 s | 1,27 s | 1,5× |
| Speicher nach 15× Öffnen/Schließen | +127 MB | +0 MB | |
| Programmstart, Datei öffnen, Hauptfenster, STEP-Import, Kalkulation, Liste, 3D drehen, Messen | gleich (±10 %, Messschwankung) | | |

Datenbank-Anweisungen je Ablauf: unverändert. Doppelte Rechnungen: 0 / 0.
Fingerabdruck der Ergebnisse: Anfang `d9396dfb8e9745f6`, Ende `5d3b9e57a7ecd0a3`, **vorher und nachher gleich**.

Die Gewinne in Abläufen ohne eigene Änderung (Optimieren, PDF) kommen daher, dass vorher die geschlossenen
Seiten aus früheren Schritten noch lebten und bei jeder Änderung mitrechneten bzw. Speicher banden.

## Mehrbenutzer (Lasttest)

Es gibt keinen Webserver und keine API: jeder PC hat sein eigenes PostgreSQL, Kollegen gleichen über den
gemeinsamen Ordner ab. Gemessen mit `werkzeuge/last_messung.py` (seit 0.9.407 ohne SQLite-Teil, angepasst):

**Teil A – gleichzeitige Zugriffe auf eine Datenbank** (2.000 Angebote, je Benutzer 30 Vorgänge, eigene Verbindung
je Benutzer; das ist mehr als im Betrieb, wo auf einem PC nur dessen Fenster gleichzeitig arbeiten):

| Benutzer | Liste (Median/95 %) | Suche | Öffnen | Ändern | Neues Angebot | Fehler | doppelte Nummern |
|---:|---|---|---|---|---|---:|---:|
| 1 | 23 / 33 ms | 8 / 14 ms | 1 / 2 ms | 3 / 12 ms | 24 / 33 ms | 0 | 0 |
| 5 | 34 / 65 ms | 12 / 20 ms | 4 / 17 ms | 18 / 29 ms | 185 / 284 ms | 0 | 0 |
| 10 | 62 / 146 ms | 16 / 40 ms | 9 / 32 ms | 44 / 88 ms | 491 / 1.035 ms | 0 | 0 |
| 25 | 122 / 423 ms | 29 / 126 ms | 20 / 74 ms | 108 / 187 ms | 1.666 / 4.413 ms | 1 von 99 | 0 |

Bei 25 gleichzeitigen „Neues Angebot“ auf derselben Datenbank brach eines mit „Angebotsnummer gibt es schon“ ab
(nichts doppelt gespeichert, der Benutzer würde es erneut anlegen). Im Betrieb kommt das nicht vor (jeder PC eigene
Datenbank, Nummern aus dem Nummernvorrat); der Punkt geht an den Datenbank-Umbau (Schritt 3, Versionsnummern).

**Teil B – Abgleich über den gemeinsamen Ordner:**

| Plätze | Abgleich (Median/95 %) | gleicher Stand | alle Feldänderungen da | doppelte Nummern | Konflikte gemeldet |
|---:|---|---|---|---:|---:|
| 1 | 140 ms | ja | ja | 0 | 0 |
| 5 | 378 / 414 ms | ja | ja | 0 | 0 |
| 10 | 494 / 544 ms | ja | ja | 0 | 3 |
| 25 | 896 / 990 ms | ja | ja | 0 | 18 |

Konflikte sind gewollt: im Test ändern mehrere Plätze dasselbe Feld derselben Zeile; sie werden gemeldet, alle
Plätze haben danach denselben Stand.

## Regressionstests

Bestanden (lokal unter PostgreSQL): test_freigeben (neu), test_regression_ergebnisse (20 feste Angebote wie
gespeichert, auch aus dem Cache), test_angebots_cache, test_anleitung, test_protokoll_kontext, test_spiegel, test_3d,
test_zusatz_3d, test_bohrbild, test_import_erkennung, test_steckverbindung, test_satz3d, test_normteile_preis,
test_normteile_ohne_preis; ruff ohne Befund. Die volle Testreihe läuft im Check `tests` des Pull Requests.

## Abschluss (12 Punkte)

1. **Ausgangsperformance:** siehe Phase 2; Alltagsabläufe 0,1 bis 1,8 s, STEP-Import 204 s für 33 Dateien.
2. **Gefundene Fehler:** Speicherleck beim Schließen eines Angebots (P1); unnötiges Mehrfach-Einlesen (P2);
   Lasttest-Werkzeug lief seit 0.9.407 noch mit SQLite-Teil (angepasst); 1 von 99 neuen Angeboten bei 25
   gleichzeitigen Benutzern auf einer Datenbank (nur im Test, an Datenbank-Umbau übergeben).
3. **Langsamste Abläufe:** STEP-Import (Geometrie in Hilfsprozessen), 3D-Drehen ohne OpenGL, Werkstatt-PDF,
   Zelle ändern mit Prüfung (Maschinenvergleich beim ersten Mal).
4. **Ursachen:** Python-Hüllen in Ringen und Modelle ohne Eltern (P1), JSON-Lesen ohne Merker (P2),
   Maschinenvergleich in der Prüfung (P3), Software-Darstellung ohne Grafikkarte (P4).
5. **Optimierungen:** freigeben.py, json_lesen.py (nur reine Lesestellen), Kopfsuche einmal je Rechenlauf, Lasttest-Werkzeug auf PostgreSQL.
6. **Stabilitätsprobleme:** nur das Speicherleck; behoben, Langzeit flach.
7. **RAM/CPU:** CPU bei Zelle 1,61 → 1,11 s; RAM nach vielen Angeboten stabil statt +8 bis 12 MB je Angebot.
8. **Datenbank:** kein Engpass, Anzahl und Zeit der Anweisungen unverändert; Lasttest siehe oben.
9. **3D:** öffnen 0,08 s, zehn Teile 1,78 → 1,33 s, Messen 0,54 s; Drehen ohne OpenGL 178 ms/Bild (nur Ersatz).
10. **Vorher/nachher:** Tabelle oben, Ergebnisse identisch (Fingerabdruck).
11. **Verbleibende Punkte:** Maschinenvergleich beim ersten Prüfen bis 3 s (abschaltbar); STEP-Import großer
    Mengen; 3D-Ersatzdarstellung ohne OpenGL; Echttest auf Windows-Arbeitsplätzen im Sammel-Update.
12. **Freigabeempfehlung:** **Freigabe für das Sammel-Update.** Keine offenen Fehler mit Folgen für den Betrieb, Ergebnisse
nachweislich gleich, Speicher stabil, Mehrbenutzer und Abgleich ohne doppelte Nummern und mit gleichem Stand.
