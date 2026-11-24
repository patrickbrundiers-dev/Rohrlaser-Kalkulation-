# CAD- und Kalkulationskern 3.0 – Entwicklungs- und Performancebericht (24.11.2026)

Master-Auftrag Patrick 24.11.2026 („CAD Engine 3.0 und Calculation Engine 3.0“). Stand main 0.9.474 (6943194f).
Abgegrenzt gegen die parallelen Threads: Booleans/Staffeln (#643), CAD-Importkern/Geometrieprüfung, Abwicklung →
2D-Schnittweg → Rückprojektion (eigener Thread, Punkt 5 des Auftrags), Schnellimport (#647), Generalüberholung (#648).

Alle Zahlen sind gemessen (Container: 4 Kerne, 15 GB, Python 3.13, OCP 8.0.1.1), keine Schätzungen. Werkzeug
`werkzeuge/step_benchmark.py` (neu: `--lesecache`, `--lesecache-ab`), Messwerte ungerundet verglichen (Toleranz 0).

## 1. Gefundene Engpässe

| Bereich | Befund | Messung |
|---|---|---|
| STEP lesen großer Baugruppen | 97 % der Lesezeit in `ShapeFix_Edge::FixAddPCurve` → `ShapeConstruct_ProjectCurveOnSurface` → `Extrema_GenExtPS` (Flächenkurven auf Freiformflächen ergänzen), davon 62 % `BuildGrid` | U_29MB.step: Lesen 297 s (Datei einlesen 1,3 s, Übertragen/Heilen 294,6 s); py-spy mit C++-Stapeln, 15.877 Proben |
| Ursache | 529 BSpline-Flächen von 8.166 Flächen, die größten sind Gewindeflächen der Gewindestange „Esparrago“ (5 × 1.169 Pole); die Datei enthält keine PCURVE-Einträge, OpenCascade muss jede Kante auf jede Freiformfläche projizieren | Zählung im STEP-Text und an den gelesenen Körpern |
| Wiederholteile | OpenCascade heilt ein Produkt nur einmal, die Instanzen teilen die Geometrie (TShape) | U_29MB: 436 verschobene + 289 gedrehte Kopien, 3 Esparrago-Instanzen = 1 Heilung |
| Kopiensuche | Jeder Körper mit jedem früheren verglichen (n²) | synthetisch 6.000 Körper: 2,75 s |
| Nahtkandidaten | Hüllquader jeder mit jedem (n²/2 `IsOut` in Python) | synthetisch 6.000 Körper: 25,7 s |
| Anbauteile | Hüllquader jedes Nicht-Rohrs für jedes Rohr neu berechnet (Rohre × Teile × BRepBndLib) | doppelte Arbeit, Ergebnis gleich |
| Programmstart Messung | `import OCP` (eine große Erweiterung) 0,54 s je Messprozess | bei Einzelteilen ~1 s von 1,2 s |
| Kalkulation | Merker greifen bereits: gleiche Eingaben rechnen nicht neu | 8 Abnahme-Angebote: kalt 259 ms, gleich 14 ms, eine Position geändert 104 ms |

### OpenCascade/OCP und DESTEP_Parameters

- OCP 8.0.1.1 bietet `STEPControl_Reader.ReadFile(name, DESTEP_Parameters)`, der Typ `DESTEP_Parameters` ist aber
  nicht übersetzt (kein Modul `OCP.DESTEP`), ebenso `SetShapeProcessFlags` (std::bitset). Eigene Reader-Parameter
  gehen in dieser Version nur über `SetShapeFixParameters` am einzelnen Leser – genau so liest das Programm schon
  (`_grosse_datei_einstellen`, je Leser). Das Lesen benutzt **kein** `Interface_Static` (Test prüft das).
- Globale Werte gab es nur beim **Schreiben** (`write.step.schema/unit/product.name`): jetzt unter einer Sperre,
  damit zwei Threads sich die Werte nicht umstellen (`step_schreiben._step_schreiben`, Test mit zwei Threads).
- Abschalten der Kurvenergänzung ist keine Option (die Kurven sind für gültige Körper nötig); `FixEdgeCurvesMode=0`
  ändert die Dauer ohnehin nicht (281 s), OpenCascade ergänzt sie trotzdem.

## 2. Umgesetzt

| Nr | Änderung | Dateien | Ergebnis |
|---|---|---|---|
| A | **Lese-Zwischenspeicher** (neu): gelesene und geheilte Körper mit Info, Struktur, Kopien als BinTools-Datei je Dateiinhalt + Name; Einstellung `step_cache` = „ja, mit gelesenen Körpern“ | `step_messung/step_lesecache.py`, `step_geometrie.datei_lesen`, `step_messen` (`--lesecache`), `rohrlaser/stammdaten.py`, `step_einstellungen.py` | U_29MB: Lesen 297,1 s → **0,23 s** |
| B | Schnappschuss der verteilten Messung nutzt denselben Code | `step_messen._schnappschuss_*` | gleiches Format, ein Code |
| C | Kopiensuche je Fach (Streuwert der Teilgeometrie), dann `IsPartner` wie bisher | `step_geometrie._instanzen/_gedrehte/_teilform` | 6.000 Körper 2,75 s → **0,06 s**, gleiche Zuordnung |
| D | Räumliche Paarsuche (Sweep nach x, dann exakt `IsOut`), gleiche Reihenfolge der Paare | `step_geometrie._ueberlappende_paare`, `_nahtkandidaten` | 6.000 Körper 25,7 s → **0,18 s**, gleiche Paare und Reihenfolge |
| E | Hüllquader der Anbauteil-Kandidaten einmal je Körper | `step_geometrie._beruehrende_anbauteile` | doppelte Rechnung weg, Ergebnis gleich |
| F | STEP-Schreiben threadsicher | `step_schreiben.py` | Test mit 2 Threads |
| G | Benchmark mit Lese-Zwischenspeicher | `werkzeuge/step_benchmark.py` | `--lesecache DIR [--lesecache-ab S]` |

## 3. Bitgleichheit und die Entscheidung zum Lese-Zwischenspeicher

BinTools speichert Richtungen (gp_Dir, gp_Dir2d, auch in den Flächenkurven) als Zahlen und normiert sie beim Lesen
neu. Gemessen: Flächenkurven einer Kante um 1e-16 anders (2,043432090204065e-10 → 2,043698543729975e-10 in u).
Die Messung reagiert an einigen Stellen darauf:

| Vergleich (126 Prüf-STEPs, ungerundet) | Ergebnis |
|---|---|
| neuer Stand, Speicher aus, gegen main 0.9.474 | **126/126 bitgleich** |
| Speicher an: erstes Lesen gegen Wiedereinlesen aus dem Speicher | **126/126 bitgleich** |
| Speicher an gegen main 0.9.474 | 123/126 bitgleich; RP02, RP03, K08: z-Lagen der Wandstärken-Einzelmessungen (Wandstärke gleich), K08 zusätzlich Umriss einer Kontur der Auswahl „geschlossen“ bis 0,23 mm |

Deshalb misst das Programm bei eingeschaltetem Speicher schon beim ersten Lesen die gemerkte Form. Wichtig: dieselbe
Umwandlung steckt seit 06.11.2026 im Schnappschuss der verteilten Messung (große Baugruppen auf mehrere Prozesse).
Ohne Lese-Zwischenspeicher hängen die letzten Stellen dort davon ab, welcher Prozess einen Körper misst (der lesende
Prozess misst die Form im Speicher, die anderen die geladene). Mit Speicher rechnen alle Prozesse mit derselben Form.

Vorgabe bleibt „ja“ (wie bisher, bitgleich). Patrick entscheidet, ob „ja, mit gelesenen Körpern“ Vorgabe wird.

## 4. Benchmark vorher/nachher

### 126 Prüf-STEPs (`tests/`, ein Messprozess)

| Kennzahl | Vorher (main 0.9.474) | Nachher, Speicher aus | Nachher, Speicher an (1. Lauf) | Nachher, Speicher an (2. Lauf) |
|---|---:|---:|---:|---:|
| Gesamtdauer | 284,0 s | 289,3 s | 284,4 s | 281,4 s |
| davon Körper messen | 157,0 s | – | – | – |
| RAM-Spitze | 302 MB | 288,5 MB | 288,2 MB | 288,5 MB |
| Messwertgleichheit | Referenz | 126/126 | 126/126 gegen 2. Lauf | 123/126 gegen Referenz |

Die Prüf-STEPs lesen in 0,01–0,3 s; dort bestimmen Prozessstart (0,54 s `import OCP`) und Messung die Zeit, der
Speicher kann dort nichts bringen. Schwankung zwischen Läufen ±2 %.

### Echte Baugruppe U_29MB.step (870 Körper, 29,5 MB, AP214)

| Kennzahl | Vorher | Nachher (Speicher an, Wiedereinlesen) |
|---|---:|---:|
| STEP-Ladezeit (ReadFile) | 1,3 s | – (nicht nötig) |
| Formheilung (Übertragen) | 294,6 s | – (aus dem Speicher) |
| Laden aus dem Speicher | – | 0,23 s |
| Kopien suchen | 0,08 s | – (gemerkt) |
| Geometrieanalyse (Körper messen) | siehe Lauf | siehe Lauf |
| Gesamtdauer | U29_ALT | U29_NEU |
| RAM-Spitze | U29_RAM_ALT | U29_RAM_NEU |
| Messwertgleichheit | Referenz | U29_GLEICH |

Abwicklung: im Ablauf von „Körper messen“ enthalten; wird im Thread „STEP-Schnittwege über Abwicklung“ neu gebaut.

### Große Baugruppen (synthetisch, `tests/test_cad_kern_3_2411.py`)

| Kennzahl | Vorher | Nachher | Gleich |
|---|---:|---:|---|
| Kopiensuche 1.500 / 6.000 Körper | 0,19 s / 2,75 s | 0,01 s / 0,06 s | Prüfsumme gleich |
| Paarsuche Nähte 300 / 2.000 / 6.000 Körper | 0,06 / 2,74 / 25,7 s | 0,001 / 0,022 / 0,178 s | gleiche Paare, gleiche Reihenfolge |

### Kalkulation (8 Abnahme-Angebote, optimieren + kalkulieren)

| Lauf | optimieren | kalkulieren |
|---|---:|---:|
| kalt (Merker leer) | 87 ms | 259 ms |
| gleiche Eingaben | 29 ms | 14 ms |
| eine Position geändert | 71 ms | 104 ms |

Nur geänderte Eingaben lösen Neuberechnung aus (Rechenmerker, Dauermerker, Angebots-Cache). 20 feste
Angebotsregressionen (`tests/test_regression_ergebnisse.py`) grün, zweimal gerechnet bitgleich, dritter Lauf aus dem
Cache typgenau gleich. Einheitliche Übergabe CAD → Kalkulation besteht schon (versioniertes JSON `step_ergebnis`,
Zeilen im TSV). Hier wurde nichts geändert: kein messbarer Engpass, der ohne Risiko kleiner wird.

## 5. Tests

- `tests/test_cad_kern_3_2411.py` (neu, in `tests/alle.py`): Speicher-Roundtrip bitgleich (U-Profil K08,
  Baugruppe mit Unterbaugruppe und Wiederholteilen, verschachteltes Gestell, Flächenmodell), Kopien/Struktur/Namen,
  Schlüssel (Inhalt + Name, nicht Ordner), Wächter über den Lesecode (LESER_STAND), kein Interface_Static beim
  Lesen, Begrenzen, große Baugruppen (Kopiensuche, Paarsuche gegen jeder-mit-jedem), Schreiben aus zwei Threads.
- 126 Prüf-STEPs bitgleich (siehe oben), 20 Angebotsregressionen grün, test_step_benchmark, test_zwischenspeicher,
  test_step_neu, test_einstellungen_ordnung grün.

## 6. Offene Punkte und nächste Möglichkeiten

1. **Erstes Einlesen großer Freiform-Baugruppen** bleibt so lang wie OpenCascade heilt (U_29MB 297 s). Bitgleich
   schneller ginge nur in OpenCascade selbst (Gitter von `Extrema_GenExtPS` je Fläche wiederverwenden) oder durch
   paralleles Heilen je Produkt in mehreren Prozessen; Letzteres braucht den Umbau der XCAF-Übertragung und bringt
   dieselbe Normierungsfrage wie oben. Empfehlung: erst nach der Entscheidung zu Abschnitt 3.
2. **OCP-Update**, sobald `DESTEP_Parameters` übersetzt ist: dann Schreiben ohne globale Werte.
3. **Normteile vor dem Heilen erkennen** (Gewindestangen machen den Großteil der 297 s aus): bräuchte Namen vor der
   Übertragung und ändert die Messung dieser Teile – nur mit Patricks Freigabe.
4. Geometriegleiche Körper ohne gemeinsame TShape (anders exportierte Wiederholteile) weiter einzeln messen – die
   Übernahme wurde am 21.11. abgelehnt (nicht bitgleich).
