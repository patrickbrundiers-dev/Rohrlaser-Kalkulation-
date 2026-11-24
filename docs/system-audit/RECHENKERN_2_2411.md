# Rechenkern, Importlogik und Geometrieverarbeitung 2.0 (Auftrag 24.11.2026)

Master-Entwicklungsauftrag von Patrick vom 24.11.2026, 17:40 UTC. Dieser Bericht ist Phase 1 (Analyse, Messung,
Recherche, Plan) und der erste Umsetzungsteil. Er baut auf den früheren Berichten auf und wiederholt sie nicht:
STEP-Tempo #616–#621 (`docs/performance/README.md`), Rechenkerne #618 (`RECHENKERNE_2111.md`), Stabilität
#561–#567, Systemprüfung (`PERFORMANCE_REPORT.md`), Angebots-Cache #574.

Regeln dieses Auftrags: Beschleunigungen **nur bitgleich** (jede Zahl, jeder Text gleich; Patrick lehnte am 21.11.
eine nicht bitgleiche Abkürzung ab), Konturen 100 % lagegenau zur STEP, kein Fremdcode, kein Bibliothekswechsel und
keine Datenbank-Architekturänderung ohne Patricks Freigabe, nichts doppelt zu den laufenden Threads bauen.

Abgrenzung zu den parallel laufenden Arbeiten (am 24.11. abgeglichen):

| Thread / PR | macht | hier deshalb nicht |
|---|---|---|
| Schnellimport (Modus A) | STEP nur mit Linien statt Netz, Übersicht statt Prüfdialog | Importmodus A |
| STEP Import Engine 2.0 #642 | eigener STEP-Viewer, Konturnummer je 3D-Linie, Experten-Netz (Modus C) | Viewer, Modus B/C |
| Generalüberholung #641 | Oberfläche, Öffnen/Schreiben der Datenbank, leere Tabellen | UI, Datenbank-Schreibweg |
| Nesting-Arbeitsplatz 2.0 #639 | Nesting-Fenster, Verschachteln von Hand, Machbarkeit | Nesting-Algorithmen |
| 12-m-Zuschnitt #637, Staffel = Angebot #636 | Längenwahl, Staffel als Angebotskalkulation | – |
| Produktionsdaten LST/BPF #640 | Zeitmodell aus Maschinendaten | – |

## 1. Datenfluss und wo die Zeit hingeht

Gemessen im Linux-Container (4 Kerne, 15 GB, Python 3.13, OCCT 8.0.1), `main` 8131fe69 (0.9.469). Testdaten: die
126 Prüf-STEPs unter `tests/` (Rohre, Profile, offene Profile, Bleche, Baugruppen bis 48 Teile, RP-Profile,
Freiform), die Testangebote S/M/L (5/50/200 Positionen, `tests/testangebote_gross.py`) und die 20 Angebote des
Regressionstests. Profile mit `py-spy` (inkl. Messprozesse und OpenCascade) bzw. `cProfile`.

| # | Schritt im Datenfluss | Modul | Befund (gemessen) |
|---|---|---|---|
| 1 | Datei einlesen, umwandeln, heilen, nähen | step_geometrie.datei_lesen | 7 % der Baugruppe I05 (48 Teile); STEP-Leser von OCCT, nicht parallel |
| 2 | Geometrieerkennung je Körper (Lage, Querschnitt, Profil) | step_geometrie._lage/_regelquerschnitt/_profil_messen | Rohre: Ebenenschnitte (`_schnitt`) 33 %, Flächeneigenschaften 10 %; gleiche Lagen werden schon nur einmal geschnitten (seit 10.11.) |
| 3 | Offene Profile schließen (U, C, L mit Laschen) | step_offenes_rohr.schliessen | **60 % der Messzeit in Booleschen Operationen** (K08 U80x40x4: 14 von 23 s); liefen auf einem Kern |
| 4 | Schweißnaht-/Anbaukörper | step_geometrie._analysiere_naht, step_knickrahmen | I05: Nachbarsuche über Hüllen und Raster ~15 %; seit #617 auf Flächen in der Hülle begrenzt |
| 5 | Schneidweg, Konturen, Zusatzarbeiten | step_messen, schneidweg.rechnen | aus der Messung; kein eigener Engpass |
| 6 | Kalkulation je Angebot | rechnen.kalkulation | L (200 Pos.): 0,34 s kalt, 0,03 s warm – kein Engpass |
| 7 | **Staffeln** | staffeln.rechnen_alle | L mit 6 Stufen: **4,7 s**; je Stufe eine volle Kalkulation, davon ~40 % Schnittzeiten je Position, die jede Stufe neu rechnete, obwohl sie nicht von der Stückzahl abhängen |
| 8 | Maschinenvergleich | maschinen_vergleich.vergleich | L: 1,8–4,2 s; je Maschine eigene Schnittzeit (fachlich nötig) |
| 9 | Optimieren / Nesting | rechnen.optimieren, optimierung.py | L: 0,38 s kalt; XL seit #618 4,6 s; Hilfsprozesse ab 1.500 Teilen |
| 10 | Datenbank | db_verbindung, datenbank.py | Alltag < 20 ms (PG), Abgleich 25 PCs < 0,5 s (`PERFORMANCE_REPORT.md`); Öffnen/Schreiben im Thread #641 |
| 11 | Speicher | – | STEP-Messprozess ~300 MB je Prozess (OCCT geladen), Hauptprogramm ~250 MB; kein Leck gefunden |
| 12 | Hintergrund | parallel.py, hintergrund.py, QProcess | STEP-Messung läuft als eigener Prozess, Optimieren/Staffeln/Maschinenvergleich in Fäden; Oberfläche bleibt bedienbar |

## 2. Engpässe bewertet und priorisiert

Bewertung: Geschwindigkeit / Stabilität (Wirkung), Aufwand, Risiko für bestehende Funktionen, Nutzen. Reihenfolge =
Nutzen ÷ (Aufwand × Risiko).

| Prio | Engpass | Geschw. | Stabilität | Aufwand | Risiko | Nutzen | Stand |
|---|---|---|---|---|---|---|---|
| 1 | Boolesche Operationen auf einem Kern (offene Profile, Anbau, Abwicklung) | hoch | – | klein | gering (Ergebnis geprüft gleich) | hoch | **umgesetzt (B1)** |
| 2 | Staffeln rechnen die Schnittzeiten je Stufe neu | hoch | – | klein | gering (Feldzugriffe nachgewiesen) | hoch | **umgesetzt (R1)** |
| 3 | Kein Monitoring mit Median/Perzentilen, CPU, RAM je Schritt | – | mittel | klein | keins | hoch | **umgesetzt (M1)** |
| 4 | Benchmarks nur mit Median bzw. einem Lauf | – | – | klein | keins | mittel | **umgesetzt (M2)** |
| 5 | Ebenenschnitte (`_schnitt`) zur Querschnittsuche: BRepAlgoAPI_Section je Lage | mittel | – | mittel | mittel | mittel | Paket 2 (Untersuchung: Schnitt an Flächen statt am ganzen Körper ist bereits ab 150 Flächen aktiv) |
| 6 | Maschinenvergleich: Schnittzeiten je Maschine, Optimieren je Maschine | mittel | – | mittel | mittel | mittel | Paket 2 (gleiches Muster wie R1 für Felder, die nicht von der Maschine abhängen, nur mit Nachweis) |
| 7 | Mehrere Messprozesse × Parallelmodus: Überbelegung der Kerne | gering | gering | klein | gering | gering | beobachten (I05 mit 3 Prozessen trotzdem 14 % schneller) |
| 8 | STEP-Leser selbst (Datei lesen/übertragen) | gering–mittel | – | – | – | gering | OCCT 8.0 bringt hier schon bis 75 % gegenüber 7.7 (wir sind auf 8.0.1) |
| 9 | Datenbank für 10–25 Benutzer | – | mittel | groß | hoch | – | bleibt: PostgreSQL je PC + Abgleich über Ordner (gemessen bis 25 PCs < 0,5 s); keine Architekturänderung ohne Freigabe |

Bewusst **nicht** gemacht (verstößt gegen die Regeln oder bringt keine Bitgleichheit):

- Parallele Kalkulation der Staffelstufen in Hilfsprozessen: die Hilfsprozesse haben eine andere Hash-Reihenfolge
  (PYTHONHASHSEED); Iterationen über Mengen von Texten könnten die Reihenfolge von Gleitkomma-Summen ändern. Nicht
  beweisbar bitgleich, daher nein. Die Schnittoptimierung in Hilfsprozessen (seit 23.10.) ist davon nicht betroffen
  (geprüft bitgleich).
- Messwerte gleicher Geometrie übernehmen, wenn sie nur „fast“ gleich ist (am 21.11. abgelehnt).
- Gröbere Netze, weniger Querschnittlagen, Toleranzen lockern: würden Werte verändern.

## 3. Technologievergleich (Recherche 24.11.2026)

| Technologie | Mehrwert für uns | Lizenz | Kompatibilität / Migration | Performance | Entscheidung |
|---|---|---|---|---|---|
| **Open CASCADE (OCCT) 8.0.1** über `cadquery-ocp` 8.0.1.1.0 | ist unser Kern; 8.0.0 (Mai 2026) brachte stream-basierte STEP-Leser/-Schreiber, thread-sicheres STEP-Lesen mit einer Instanz je Faden, schnellere Hüllquader (GeomBndLib), BVH für Polyeder-Schnitte; 8.0.1 (30.07.2026) u. a. BRepCheck_Face 2.000 Bohrungen 9,2 → 1,1 s, Fixes in ShapeFix/BRepMesh/Booleschen Operationen | LGPL 2.1 mit Ausnahme, kostenlos | **schon im Einsatz, aktuelle Wartungsversion** | Parallelmodus der Booleschen Operationen und Schnitte nutzbar (umgesetzt) | behalten; jedes künftige OCCT-Update nur per PR mit Benchmark alt/neu (bitgleich oder Abweichung fachlich erklärt) |
| OCCT XDE / STEPCAFControl | Baugruppen, Namen, Farben, Ebenen | wie OCCT | nutzen wir für Struktur und Namen | – | behalten |
| OCCT Shape Healing (ShapeFix, ShapeUpgrade) | Reparatur defekter Flächen | wie OCCT | im Einsatz (umwandeln/heilen) | 8.0.1 behebt Abstürze in ShapeFix_Face | behalten |
| OCCT BRepMesh | 3D-Netz für Viewer/Editor | wie OCCT | im Einsatz; im Schnellimport entfällt es | parallel möglich | Netz bleibt außerhalb der Kalkulation (Modus A ohne Netz) |
| Parasolid (Siemens) | sehr robuste Booleans und Healing, Industriestandard | kommerziell (Lizenz + Laufzeitgebühren je Platz) | kompletter Wechsel des Geometriekerns, keine offizielle Python-Anbindung; alle Messfunktionen neu | hoch | **nicht empfohlen** (Aufwand Monate, Ergebnisse wären nicht bitgleich, laufende Kosten) – nur auf Patricks Wunsch weiter prüfen |
| HOOPS Exchange (Tech Soft 3D) | liest >30 CAD-Formate inkl. nativer (SolidWorks, Inventor, CATIA), PMI | kommerziell, Preis auf Anfrage | nur als zusätzlicher Leser vor OCCT denkbar (Übergabe als B-Rep); C/C++-SDK | Leser schnell, Messung bleibt OCCT | **Empfehlung nur für native Formate**, falls Kunden statt STEP native Dateien schicken – Patricks Entscheidung |
| STEP Tools (ST-Developer) | sehr genaue AP242-Unterstützung (PMI, Toleranzen) | kommerziell | zusätzlicher Leser, C++ | – | nicht nötig (unsere Messung braucht B-Rep, kein PMI) |
| CAD Exchanger | Leser/Konverter, intern OCCT-nah | kommerziell | zusätzlicher Leser | – | kein Mehrwert gegenüber OCCT 8.0.1 |
| numpy / Vektorisierung | schnellere Punkt-/Rastersuchen in Python | BSD | im Messprozess vorhanden, **nicht** im Hauptprogramm (bewusst ausgeschlossen, rohrlaser.spec) | mittel | nur im Messprozess, nur wo bitgleich (Gleitkomma-Reihenfolge!) |
| Multithreading in Python | – | – | GIL: reine Python-Rechnung profitiert nicht; OCCT gibt die GIL in C++ frei | – | Parallelität über OCCT-Parallelmodus und Messprozesse (wie bisher), keine geteilten OCCT-Objekte zwischen Fäden |
| GPU für Visualisierung | flüssigere 3D-Ansicht großer Baugruppen | – | Qt/OpenGL schon im Einsatz; Instancing gleicher Körper ist im Thread #642 vorgemerkt | – | dort |

Thread-Sicherheit: Jede STEP-Messung läuft in eigenen Prozessen; ein Prozess teilt keine OCCT-Objekte zwischen
Fäden. Der Parallelmodus der Booleschen Operationen verteilt intern nur die Schnitte der Flächenpaare einer einzigen
Operation (OCCT verbindet sie danach in fester Reihenfolge) – daher dasselbe Ergebnis. Bekannte Abstürze beim
gleichzeitigen Lesen mehrerer STEP-Dateien in Fäden (OCCT-Forum, 7.9.0) betreffen uns nicht (ein Leser je Prozess).

## 4. Umgesetzt in Teil 1 (0.9.474, kein Schema-Sprung)

| Nr. | Änderung | Datei | Nachweis |
|---|---|---|---|
| B1 | Boolesche Operationen (Schnitt, Vereinigung, Differenz) im Parallelmodus von OpenCascade, wie es `_schnitt` schon war. Schalter `RL_BOOLESCH_SEQ=1` zur Fehlersuche. | step_messung/step_geometrie.py (`boolesch`, `BOOLESCH_PARALLEL`) | 124 von 124 messbaren Prüf-STEPs bitgleich (2 absichtlich defekte/leere Dateien ohne Messwerte, wie vorher); Test vergleicht JSON, Messtabelle und 3D-Netze eines offenen U-Profils |
| R1 | Staffeln: die Schnittzeit je Position gilt für alle Stufen (Schlüssel: Position ohne `stueck`/`abruf_basis`, Kopf ohne `KOPF_OHNE_SCHNITTZEIT`, Wand, Stammdaten-Objekte). Schalter `rechnen.SCHNITTZEITEN_TEILEN`. | rechnen.py (`schnittzeiten_teilen`, `_schneidzeit_teile`), staffeln.py | Test verfolgt jeden Feldzugriff der Schnittzeit über S/M/L-Staffeln und die Kontur-Angebote des Regressionstests: nie Stückzahl, nie ausgenommene Kopffelder, nie die ganze Position; Staffeln S/M/L mit/ohne Teilen `repr`-gleich; Regressionstest 20 Angebote unverändert |
| M1 | Performance-Monitoring je Verarbeitungsschritt: Anzahl, Start/Ende, Median, 90/95/99 %, längster Lauf, CPU-Zeit und -Auslastung, RAM und größter Zuwachs, Zählwerte, Fehler, Warnungen. Erfasst: alle Rechnungen über `diagnose.messen` (Optimieren, Kalkulation, Staffeln, Maschinenvergleich, Nesting-Vergleich), STEP-Import gesamt und 7 Teilschritte aus der ZEITEN-Zeile, PDF Angebot/Werkstatt/Kalkulation/Angebotsakte. Entwickleransicht: Abschnitt im Diagnose-Bericht (Hauptadmin → Diagnose, diagnose.txt im Support-Paket). | rohrlaser/leistung.py (neu), diagnose.py, angebot_fenster.py, pdf.py, akte_pdf.py | tests/test_rechenkern_2411.py (Perzentile = statistics.quantiles inclusive, Fehler, Zählwerte, STEP-Schritte, Bericht) |
| M2 | Benchmarks mit Median **und** 90/95 % und längstem Lauf: `rechen_benchmark.py lauf --wdh N --wdh-lang N` (auch Staffeln/Maschinenvergleich mehrfach), `step_benchmark.py lauf --wdh N` (prüft zusätzlich, dass jede Wiederholung dieselben Messwerte liefert). | werkzeuge/rechen_benchmark.py, werkzeuge/step_benchmark.py | – |

## 5. Messergebnisse (gleiche Testdaten, gleicher Rechner, nacheinander)

### STEP-Import, 126 Prüf-STEPs (je ein Messprozess, wie `step_benchmark.py lauf --prozesse 1`)

| Gruppe | Dateien | vorher s | nachher s | Faktor |
|---|---:|---:|---:|---:|
| Konturen (K…) | 10 | 69,6 | 56,3 | 1,24 |
| Profile (P…) | 10 | 36,5 | 29,8 | 1,22 |
| Offene Profile (OR…) | 4 | 27,1 | 23,0 | 1,18 |
| Referenz (REF…) | 18 | 40,3 | 35,3 | 1,14 |
| Bleche | 18 | 30,8 | 27,5 | 1,12 |
| Importengine (Baugruppen, ZIP …) | 10 | 32,4 | 29,0 | 1,11 |
| RP-Profile | 6 | 33,8 | 33,4 | 1,01 |
| **alle 126** | 126 | **366,4** | **322,8** | **1,14** |

Einzelne: K08 U80x40x4 23,2 → 17,8 s, K07 20,7 → 16,6 s, K06 14,3 → 11,1 s, P01 U50x30x3 13,1 → 9,9 s; Baugruppe
I05 (48 Körper) zusammen mit drei U-Profilen in 3 Messprozessen 50,7 → 43,8 s. Messwerte 124/124 gleich (Toleranz 0).

Median/95 % aus Wiederholungsläufen: siehe Abschnitt 5.3.

### 5.2 Rechenkern (Testangebote, PostgreSQL wie im Programm)

Siehe Abschnitt 5.3 (Läufe nacheinander, jeweils Median und 95 %).

### 5.3 Wiederholungsläufe mit Median und 95 %

(wird mit den Werten der ruhigen Läufe ergänzt)

## 6. Plan der nächsten Pakete

| Paket | Inhalt | Phase des Auftrags |
|---|---|---|
| 2 | Maschinenvergleich: Teile der Schnittzeit, die nicht von der Maschine abhängen, einmal (nur mit Feldzugriffs-Nachweis wie R1); Querschnittsuche (`_schnitt`): Flächenvorauswahl je Lage mit räumlichem Index der Flächen-Hüllen (gleiche Flächen, gleicher Schnitt) | 2 + 4 |
| 3 | Gemeinsame Geometriedaten für Modus A/B/C: eine Messung, daraus Kalkulation (A), Vorschau (B), Editor (C) – abgestimmt mit Schnellimport und #642, damit nichts doppelt entsteht | 3 |
| 4 | Fehlerresistenz Import: ein defekter Körper bricht die Baugruppe nicht ab (heute schon je Körper isoliert gemessen, mit Zeitlimit); Prüfung mit beschädigten Test-STEPs, Endlosschleifen-Schutz je Schritt | 3 + 11 |
| 5 | Zentrale Kalkulation: Liste aller Stellen, die Preise/Zeiten außerhalb von `rechnen.kalkulation` rechnen (Staffeln seit #636 schon zentral; Rahmenaufträge, Nachkalkulation, Schweißbaugruppen prüfen), doppelte Logik entfernen nur mit Regressionstest bitgleich | 5 |
| 6 | Last- und Speichertests (große Baugruppen, 10.000 Angebote, viele Benutzer über den Austauschordner), Abschlussbericht mit Vorher/Nachher | 6 |
