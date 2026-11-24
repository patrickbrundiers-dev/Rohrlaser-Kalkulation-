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
| 7 | **Staffeln** | staffeln.rechnen_alle | L mit 6 Stufen: 1,47 s; je Stufe eine volle Kalkulation; die Schnittzeiten je Position rechnete jede Stufe neu, obwohl sie nicht von der Stückzahl abhängen |
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
| 2 | Staffeln rechnen die Schnittzeiten je Stufe neu | mittel | – | klein | gering (Feldzugriffe nachgewiesen) | hoch | **umgesetzt (R1)** |
| 3 | Kein Monitoring mit Median/Perzentilen, CPU, RAM je Schritt | – | mittel | klein | keins | hoch | **umgesetzt (M1)** |
| 4 | Benchmarks nur mit Median bzw. einem Lauf | – | – | klein | keins | mittel | **umgesetzt (M2)** |
| 5 | Ebenenschnitte (`_schnitt`) zur Querschnittsuche: BRepAlgoAPI_Section je Lage | gering | – | mittel | mittel | gering | **Paket 2 untersucht: nur 1,6 % der Zeit (K08), Flächenfilter ab 150 Flächen besteht schon – kein Umbau** |
| 6 | Maschinenvergleich: Schnittzeiten je Maschine, Optimieren je Maschine | gering | – | mittel | mittel | gering | **Paket 2 untersucht: alle Teile der Schnittzeit lesen die Maschine; Schneidfolge und Schnittpläne sind schon je Eingabe gemerkt – nichts bitgleich teilbar** |
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
| Parasolid (Siemens) | sehr robuste Booleans und Healing, Industriestandard | kommerziell (Lizenz + Laufzeitgebühren je Platz) | kompletter Wechsel des Geometriekerns, keine offizielle Python-Anbindung; alle Messfunktionen neu | hoch | **nicht empfohlen**; **Patrick 24.11.2026 18:22 UTC: „Open Cascade bleiben“** – kein Wechsel |
| HOOPS Exchange (Tech Soft 3D) | liest >30 CAD-Formate inkl. nativer (SolidWorks, Inventor, CATIA), PMI | kommerziell, Preis auf Anfrage | nur als zusätzlicher Leser vor OCCT denkbar (Übergabe als B-Rep); C/C++-SDK | Leser schnell, Messung bleibt OCCT | entfällt (Entscheidung „Open Cascade bleiben“) |
| STEP Tools (ST-Developer) | sehr genaue AP242-Unterstützung (PMI, Toleranzen) | kommerziell | zusätzlicher Leser, C++ | – | nicht nötig (unsere Messung braucht B-Rep, kein PMI) |
| CAD Exchanger | Leser/Konverter, intern OCCT-nah | kommerziell | zusätzlicher Leser | – | kein Mehrwert gegenüber OCCT 8.0.1 |
| numpy / Vektorisierung | schnellere Punkt-/Rastersuchen in Python | BSD | im Messprozess vorhanden, **nicht** im Hauptprogramm (bewusst ausgeschlossen, rohrlaser.spec) | mittel | nur im Messprozess, nur wo bitgleich (Gleitkomma-Reihenfolge!) |
| Multithreading in Python | – | – | GIL: reine Python-Rechnung profitiert nicht; OCCT gibt die GIL in C++ frei | – | Parallelität über OCCT-Parallelmodus und Messprozesse (wie bisher), keine geteilten OCCT-Objekte zwischen Fäden |
| GPU für Visualisierung | flüssigere 3D-Ansicht großer Baugruppen | – | Qt/OpenGL schon im Einsatz; Instancing gleicher Körper ist im Thread #642 vorgemerkt | – | dort |

Thread-Sicherheit: Jede STEP-Messung läuft in eigenen Prozessen; ein Prozess teilt keine OCCT-Objekte zwischen
Fäden. Der Parallelmodus der Booleschen Operationen verteilt intern nur die Schnitte der Flächenpaare einer einzigen
Operation (OCCT verbindet sie danach in fester Reihenfolge) – daher dasselbe Ergebnis. Bekannte Abstürze beim
gleichzeitigen Lesen mehrerer STEP-Dateien in Fäden (OCCT-Forum, 7.9.0) betreffen uns nicht (ein Leser je Prozess).

## 4. Umgesetzt in Teil 1 (0.9.476, kein Schema-Sprung)

| Nr. | Änderung | Datei | Nachweis |
|---|---|---|---|
| B1 | Boolesche Operationen (Schnitt, Vereinigung, Differenz) im Parallelmodus von OpenCascade, wie es `_schnitt` schon war. Schalter `RL_BOOLESCH_SEQ=1` zur Fehlersuche. | step_messung/step_geometrie.py (`boolesch`, `BOOLESCH_PARALLEL`) | 126 von 126 Prüf-STEPs bitgleich; Test vergleicht JSON, Messtabelle und 3D-Netze eines offenen U-Profils |
| R1 | Staffeln: die Schnittzeit je Position gilt für alle Stufen (Schlüssel: Position ohne `stueck`/`abruf_basis`, Kopf ohne `KOPF_OHNE_SCHNITTZEIT`, Wand, Stammdaten-Objekte). Schalter `rechnen.SCHNITTZEITEN_TEILEN`. | rechnen.py (`schnittzeiten_teilen`, `_schneidzeit_teile`), staffeln.py | Test verfolgt jeden Feldzugriff der Schnittzeit über S/M/L-Staffeln und die Kontur-Angebote des Regressionstests: nie Stückzahl, nie ausgenommene Kopffelder, nie die ganze Position; Staffeln S/M/L mit/ohne Teilen `repr`-gleich (L: 1.200 → 204 Schnittzeit-Rechnungen); Regressionstest 20 Angebote unverändert |
| M1 | Performance-Monitoring je Verarbeitungsschritt: Anzahl, Start/Ende, Median, 90/95/99 %, längster Lauf, CPU-Zeit und -Auslastung, RAM und größter Zuwachs, Zählwerte, Fehler, Warnungen. Erfasst: alle Rechnungen über `diagnose.messen` (Optimieren, Kalkulation, Staffeln, Maschinenvergleich, Nesting-Vergleich), STEP-Import gesamt und 7 Teilschritte aus der ZEITEN-Zeile, PDF Angebot/Werkstatt/Kalkulation/Angebotsakte. Entwickleransicht: Abschnitt im Diagnose-Bericht (Hauptadmin → Diagnose, diagnose.txt im Support-Paket). | rohrlaser/leistung.py (neu), diagnose.py, angebot_fenster.py, pdf.py, akte_pdf.py | tests/test_rechenkern_2411.py (Perzentile = statistics.quantiles inclusive, Fehler, Zählwerte, STEP-Schritte, Bericht) |
| M2 | Benchmarks mit Median **und** 90/95 % und längstem Lauf: `rechen_benchmark.py lauf --wdh N --wdh-lang N` (auch Staffeln/Maschinenvergleich mehrfach), `step_benchmark.py lauf --wdh N` (prüft zusätzlich, dass jede Wiederholung dieselben Messwerte liefert). | werkzeuge/rechen_benchmark.py, werkzeuge/step_benchmark.py | – |

## 5. Messergebnisse (gleiche Testdaten, gleicher Rechner, alt und neu nacheinander ohne andere Last)

Vorher = `main` 8131fe69 (0.9.469), nachher = dieser Stand. Erste Messungen mit eingeschaltetem Profiler bzw. neben
anderen Läufen sind **nicht** verwendet (cProfile macht den Rechenkern etwa 3× langsamer: Staffeln L erschienen dort
mit 4,7 s statt 1,5 s).

### 5.1 STEP-Import, 126 Prüf-STEPs (je ein Messprozess, `step_benchmark.py lauf --prozesse 1`)

Messwerte **126 von 126 gleich** (Toleranz 0: jede Zahl, jeder Text, jede Liste des JSON).

| Gruppe | Dateien | vorher s | nachher s | Faktor |
|---|---:|---:|---:|---:|
| Konturen (K…) | 10 | 66,4 | 54,7 | 1,21 |
| Referenz (REF…) | 18 | 41,7 | 35,3 | 1,18 |
| RP-Profile | 6 | 36,0 | 35,0 | 1,03 |
| Profile (P…) | 10 | 35,0 | 29,8 | 1,17 |
| Bleche | 18 | 30,7 | 29,2 | 1,05 |
| Importengine (Baugruppen, ZIP …) | 10 | 29,7 | 31,3 | 0,95 |
| Regression | 8 | 27,2 | 25,3 | 1,07 |
| Offene Profile (OR…) | 4 | 27,2 | 23,7 | 1,15 |
| Anbau | 11 | 24,0 | 22,3 | 1,07 |
| Träger | 9 | 16,4 | 14,1 | 1,16 |
| übrige | 22 | 41,0 | 37,4 | 1,10 |
| **alle 126** | 126 | **375,3** | **338,0** | **1,11** |

### 5.2 STEP-Import, 10 typische Dateien je 5 Läufe (Median, 95 %)

| Datei | Median vorher s | Median nachher s | 95 % vorher s | 95 % nachher s | Faktor (Median) | RAM vorher/nachher MB |
|---|---:|---:|---:|---:|---:|---|
| K08 U80x40x4 viele Konturen | 21,37 | 16,69 | 21,82 | 20,04 | 1,28 | 301 / 299 |
| K06 U60x30x4 Senkung/Fließloch | 13,51 | 10,36 | 13,71 | 10,48 | 1,30 | 301 / 299 |
| P01 U50x30x3 | 12,53 | 9,81 | 12,85 | 10,35 | 1,28 | 301 / 298 |
| OR2 offenes U mit Laschen | 11,06 | 9,00 | 11,70 | 9,25 | 1,23 | 301 / 298 |
| I05 Baugruppe 48 Teile | 13,15 | 13,25 | 14,05 | 13,65 | 0,99 | 302 / 300 |
| RP04 Sonderprofil | 5,81 | 5,61 | 6,09 | 5,68 | 1,04 | 302 / 298 |
| T02 Rundrohr mit Bohrungen | 1,79 | 1,64 | 1,81 | 1,76 | 1,09 | 302 / 298 |
| R05 Freiform | 6,71 | 6,48 | 6,76 | 7,01 | 1,03 | 302 / 299 |
| B14 Rohr mit 2 Blechen | 2,13 | 2,09 | 2,18 | 2,31 | 1,02 | 302 / 298 |
| A07 Gehrung mit Anbau | 2,41 | 2,31 | 2,44 | 2,48 | 1,04 | 302 / 299 |
| **Summe** | **90,5** | **77,2** | | | **1,17** | |

Alle Wiederholungen lieferten dieselben Messwerte (reproduzierbar), alt gegen neu 10/10 gleich. Gewinn vor allem bei
offenen U-Profilen (Boolesche Operationen); bei Rohren mit Bohrungen, Blechen und Baugruppen bestimmen der Start des
Messprozesses, das Lesen und die Ebenenschnitte die Zeit (Paket 2). CPU-Auslastung des Messprozesses bei U-Profilen
jetzt ~1,5 statt 1,0 (mehrere Kerne).

### 5.3 Rechenkern, Testangebote S/M/L je 7 Läufe (PostgreSQL wie im Programm, alle Fingerabdrücke gleich)

| Messung | Median vorher s | Median nachher s | 95 % vorher s | 95 % nachher s | Faktor |
|---|---:|---:|---:|---:|---:|
| Staffeln L (200 Pos., 6 Stufen) | 1,47 | 1,24 | 1,53 | 1,29 | 1,18 |
| Staffeln M (50 Pos.) | 0,44 | 0,36 | 0,50 | 0,44 | 1,22 |
| Staffeln S (5 Pos.) | 0,12 | 0,11 | 0,17 | 0,12 | 1,11 |
| Kalkulation kalt L | 0,31 | 0,31 | 0,37 | 0,37 | 1,00 |
| Optimieren kalt L | 0,40 | 0,37 | 0,45 | 0,41 | 1,07 (Schwankung) |
| Maschinenvergleich L | 1,75 | 1,79 | 1,82 | 1,90 | 0,98 (unverändert) |

Arbeitsspeicher gleich (L: 106 / 106 MB). Kalkulation, Optimieren und Maschinenvergleich sind unverändert (nicht
angefasst; Unterschiede ±7 % sind Schwankung).

## 6. Plan der nächsten Pakete

| Paket | Inhalt | Phase des Auftrags |
|---|---|---|
| 2 | Maschinenvergleich: Teile der Schnittzeit, die nicht von der Maschine abhängen, einmal (nur mit Feldzugriffs-Nachweis wie R1); Querschnittsuche (`_schnitt`): Flächenvorauswahl je Lage mit räumlichem Index der Flächen-Hüllen (gleiche Flächen, gleicher Schnitt) | 2 + 4 |
| 3 | Gemeinsame Geometriedaten für Modus A/B/C: eine Messung, daraus Kalkulation (A), Vorschau (B), Editor (C) – abgestimmt mit Schnellimport und #642, damit nichts doppelt entsteht | 3 |
| 4 | Fehlerresistenz Import: ein defekter Körper bricht die Baugruppe nicht ab (heute schon je Körper isoliert gemessen, mit Zeitlimit); Prüfung mit beschädigten Test-STEPs, Endlosschleifen-Schutz je Schritt | 3 + 11 |
| 5 | Zentrale Kalkulation: Liste aller Stellen, die Preise/Zeiten außerhalb von `rechnen.kalkulation` rechnen (Staffeln seit #636 schon zentral; Rahmenaufträge, Nachkalkulation, Schweißbaugruppen prüfen), doppelte Logik entfernen nur mit Regressionstest bitgleich | 5 |
| 6 | Last- und Speichertests (große Baugruppen, 10.000 Angebote, viele Benutzer über den Austauschordner), Abschlussbericht mit Vorher/Nachher | 6 |

## 7. Paket 2: Untersuchung und Ergebnis (24.11.2026)

Gemessen mit py-spy (Stichproben, alle Fäden) und cProfile; Zeiten ohne Profiler aus den Benchmarks.

**Maschinenvergleich L (200 Positionen, 3 Maschinen, 1,75 s):** je Maschine einmal optimieren und kalkulieren.
In der Kalkulation steckt die Zeit in `_schneidzeit_teile_rechnen` (Schneiddaten, Vorschübe, Dynamik mit Last,
Ecken, Leerwege, Kopfweg, Beladung). Jeder dieser Schritte liest die Maschine (`m`, Beschleunigung, Eilgang,
Drehzahl, Kopfhub). Was nicht von der Maschine abhängt (Lage der Konturen, Anzahl), kostet unter 1 %. Die
teuren Teile sind schon gemerkt: Schneidfolge je Eingabe (`dynamik._FOLGE_MERK` + Angebots-Cache), Schnittpläne je
Gruppe (`optimierung.gemerkt`), der ganze Vergleich je Eingabe (`maschinen_vergleich._MERK`). Fäden bringen nichts
(GIL), Hilfsprozesse sind nicht bitgleich beweisbar (Hash-Reihenfolge, siehe oben). **Ergebnis: kein Umbau.**

**STEP-Messung, langsamste Datei K08 (U-Profil 80×40×4, 17 s):** 92 % im Schließen des offenen Profils
(`step_offenes_rohr._kasten_schliessen`), davon ~48 % Boolesche Operationen (seit B1 parallel), 27 % die Messung
des geschlossenen Profils, 20 % die Ringe an den Enden (drei verschiedene Ringe: Steg 2 mm, Prüfring 0,3 mm,
Anzeige-Ring – verschiedene Eingaben, nichts doppelt). Die Querschnittsuche `_schnitt` hat nur 1,6 %.
Geprüft: OCP gibt während `Build()` den GIL nicht frei (zwei Booleans in zwei Fäden: 21,1 s statt 18,7 s
nacheinander) – Booleans in Fäden parallel bringen nichts.

Umgesetzt: In `_kasten_schliessen` lief die Vereinigung Körper ∪ ergänzte Wände ein zweites Mal mit genau denselben
Eingaben; jetzt wird das Ergebnis `voll` von oben verwendet. 126 von 126 Prüf-STEPs bitgleich. Der Gewinn
(~1 % bei Profilen mit Fenster) liegt in der Messschwankung, daher keine Tempo-Angabe.

Baugruppe I05 (48 Körper): im Programm (mit Zeitlimit) wird die Datei auf 3 Messprozesse verteilt, 7,1 s statt
13–15 s im Benchmark mit `--prozesse 1` – kein Engpass.

**Folgerung:** Nach B1 und R1 gibt es in Rechenkern und STEP-Messung keine großen bitgleichen Gewinne mehr ohne einen
anderen Geometriekern (Patrick 24.11.: „Open Cascade bleiben“). Paket 5 (zentrale Kalkulation) ist mit dieser
Untersuchung erledigt: alle 40+ Stellen, die Preise brauchen, rufen `rechnen.kalkulation`; Staffeln (#636) und
Rahmenaufträge (`rahmen_kalk`, über `staffeln.stufe_lauf`/`marge_anhebung`) und die Baugruppen-Kostenübersicht
(`bg_kosten`) rechnen nichts selbst; Dreh-/Frästeil-Richtpreise sind EK-Vorschläge für Zukaufteile (gewollt eigene
Rechnung). Weiter mit Paket 4 (Fehlerresistenz des Imports) und Paket 6 (Last/Speicher).

## 8. Paket 4: Fehlerresistenz des Imports (24.11.2026)

Neues Prüfwerkzeug `werkzeuge/step_robust.py`: macht aus guten STEP-Dateien beschädigte Fassungen (abgeschnitten
bei 50/90 %, jede 7. Zeile weg, 200 Bytes gekippt, Unsinn-Koordinaten 1E308, ohne Kopf, nur Zufallsbytes, doppelte
Entitätsnummern, ein einzelner Körper einer Baugruppe unbrauchbar) und misst jede wie im Programm (eigener Prozess,
Zeitlimit je Körper). Geprüft: nichts hängt, jede Messung liefert ein Ergebnis, die übrigen Körper einer Baugruppe
werden weiter gemessen.

Ergebnis mit I05 (Baugruppe 48 Teile), T02 (Rundrohr), RP06 (Verbund 2 Körper), K08 (U-Profil): 34 Messungen, keine
hängt, jede in 1–7 s fertig, jede mit Ergebnis. Unlesbare Dateien kommen als „STEP-Datei nicht lesbar
(Syntaxfehler) …“, Abstürze des OpenCascade-Lesers (gekippte Bytes, doppelte Nummern) fängt die Aufsicht ab
(„Messung abgebrochen (Absturz beim Lesen der Datei …)“), das Programm läuft weiter.

**Gefunden und behoben:** Ein beschädigter Körper in einer Baugruppe fiel still weg (47 statt 48 Teile, Status
„gelesen“, kein Hinweis). Jetzt zählt `step_geometrie._fehlende_koerper` die Volumenkörper-Einträge im Modell
(`xst-type(ManifoldSolidBrep)`, ~15 ms bei 54.000 Entitäten) und meldet „1 von 48 Volumenkörpern der Datei nicht
lesbar (beschädigt?) – er fehlt in der Liste, Datei prüfen oder neu exportieren“ als erste Lesermeldung (steht als
Hinweis bei jedem Körper, Status „gelesen mit Meldungen“). Nur Hinweis, Messwerte unverändert; bei allen 124
lesbaren Prüf-STEPs kein Hinweis (keine Fehlalarme). Test: `tests/test_rechenkern_2411.py` Teil 5.

Grenze: Mit Zeitlimit 0 (Einstellung „ohne“) misst `step_messen` ohne Aufsicht; ein Absturz des Lesers beendet dann
die Messung ohne Ergebnis (das Programm meldet den Fehler des Messprozesses). Vorgabe ist 600 s, also mit Aufsicht.

## 9. Paket 6: Speicher-Dauerlauf (24.11.2026)

Neues Werkzeug `werkzeuge/speicher_dauerlauf.py`: rechnet viele Runden mit je Runde anderen Eingaben (geänderte
Teilelänge, Stückzahl im Wechsel, Angebot bleibt gleich groß): optimieren, kalkulieren, Staffeln, Maschinenvergleich.
Gemessen je Runde: Arbeitsspeicher (RSS), Python-Speicherblöcke, Dauer; optional Länge aller Merker auf Modulebene
(`--behaelter`) und tracemalloc (`--spur`, langsam).

Ergebnis Testangebot M (50 Positionen), 500 Runden, PostgreSQL wie im Programm:

| Stand | RSS nach 250 Runden | RSS nach 500 Runden | Zuwachs je Runde (2. Hälfte) | Dauer Median / 95 % |
|---|---|---|---|---|
| 0.9.476 | 149,1 MB | 152,9 MB | 0,015 MB (Messrauschen) | 0,74 / 0,89 s |
| neu | 135,2 MB | 139,8 MB | 0,019 MB (Messrauschen) | 0,73 / 0,84 s |

Kein Speicherleck: alle Merker sind begrenzt (Kalkulation 32, Maschinenvergleich 16, Schnittpläne 400 Gruppen,
Schneidfolge 5.000, Konturlagen 4.000) und füllen sich nur bis zur Grenze. Ein erster Lauf, in dem die Stückzahl je
Runde stieg, wuchs scheinbar um 0,4 MB je Runde: das Testangebot selbst wurde größer, kein Fehler im Programm.

Umgesetzt: Der Merker der Schnittpläne (`optimierung._merker`) hatte als Schlüssel den ganzen Text der Gruppe (alle
Teile mit allen Feldern); jetzt eine BLAKE2b-Prüfsumme (256 Bit) des Texts samt Länge. Gleiche Gruppe, gleicher
Schlüssel, gleiche Pläne (Regressionstest 20 Angebote, test_optimierung, test_performance_1011 grün). Spart ~13 MB
beim Testangebot M, bei großen Gruppen (viele Teile) entsprechend mehr.

Datenbank für 10–25 Benutzer: bereits gemessen mit `werkzeuge/last_messung.py` (Teil A: 1/5/10/25 gleichzeitige
Benutzer, Teil B: Abgleich über den Ordner mit bis 25 Plätzen < 0,5 s); unverändert, kein Umbau.
