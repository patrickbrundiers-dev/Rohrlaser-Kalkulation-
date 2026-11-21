# Rechenkerne und Systemstabilität (Auftrag 21.11.2026)

Master-Prompt von Patrick vom 21.11.2026: Rechenkerne, Tempo und Stabilität messbar verbessern, umgesetzt und mit
Messwerten belegt. Dieser Bericht baut auf den früheren Prüfungen auf und wiederholt sie nicht (Systemprüfung 17.11.
#545–#553, Stabilität 18.11. #561/#566/#567, System-Update 19.11. #572, Angebots-Cache #574, Pre-Update-Systemcheck
#583, PostgreSQL #515/#589). Der CAD-/Geometrie-Kern, der STEP-Import, die Mess-Engine und die Normteil-Erkennung
laufen im Thread „STEP-Import extrem beschleunigen“ (docs/performance/README.md) und sind hier ausgenommen.

Regeln: keine Änderung an Formeln oder Ergebnissen, keine übersprungenen Rechenschritte, jede Optimierung bitgleich
nachgewiesen.

## 1. Bestandsaufnahme: Rechenkerne und was es schon gibt

| Rechenkern (Master-Prompt) | Module | Bereits vorhanden |
|---|---|---|
| CAD Processing / Geometry / Feature Recognition | step_messung/*, step.py, mess_kern.py, zukaufteile.py | eigener Thread (Benchmark step_benchmark.py) |
| Calculation Engine | rechnen.py (kalkulation, position_werte, _laserzeit), preisschicht.py, zusatz_* | Merker je Rechenlauf, Kalkulations-Merker, Angebots-Cache, Regressionstest 20 Angebote |
| Cutting Optimization Engine | optimierung.py, parallel.py | Hilfsprozesse ab 1.500 Teilen, Gruppen-Merker, unabhängige Prüfung `pruefe` (keine Stange überbelegt) |
| Schneidfolge / Dynamik | dynamik.py, schneidfolge.py, zeit_zusatz.py | Merker über Neustart (dauermerker) |
| Welding Calculation Engine | naht.py, baugruppe.py, bg_kosten.py, vorkalk.py | Tests BG-Editor 2.0 |
| Material Calculation Engine | rechnen.stangen_werte, materialbedarf.py | Merker je Rechenlauf |
| Database Engine | datenbank.py, db_verbindung.py, pg_lokal.py, teilen.py | Wiederverbinden, statement_timeout 30 s, Advisory-Lock, Lasttest 25 Plätze, Versionsnummern, Probe-Wiederherstellung |
| Background Job Engine | parallel.py, Fäden in angebot_fenster/staffel_seite/datenbank | Hänger-Schutz der Oberfläche (tempo.py) |
| Diagnose | diagnose.py, tempo.py, protokoll.py, systemcheck.py | Rechenzähler, tempo.log, absturz.log, Systemcheck |

Die Rechenkerne sind als Module mit Funktionsschnittstellen getrennt (z. B. `rechnen.optimieren`,
`rechnen.kalkulation`, `staffeln.rechnen_alle`, `maschinen_vergleich.vergleich`). Ein Umbau in neue Pakete wurde
bewusst nicht gemacht: er brächte keine Messbarkeit oder Geschwindigkeit, gefährdet bitgleiche Ergebnisse und
erzeugt Konflikte mit den laufenden Threads (Regel „keine unnötigen Komplettumbauten“).

## 2. Messung: wo die Zeit hingeht

Neues Werkzeug `werkzeuge/rechen_benchmark.py` (alt gegen neu, je Rechenkern, kalt/warm, CPU, RAM, Fingerabdruck über
das ungerundete Ergebnis) mit festen Testangeboten `tests/testangebote_gross.py` (S 5, M 50, L 200, XL 500
Positionen; Konturen, Gehrungen, Sätze, Zusatzarbeiten, 6 Staffeln).

Befund (Profil, main 0.9.447): Bei großen Angeboten bestimmt die **Schnittmuster-Optimierung** die Zeit. Im Angebot XL
(5.224 Teile) entfielen von 18 s Rechenzeit 12 s auf den Simplex der Spaltengenerierung und 4 s auf die Mustersuche.
Die Kalkulation selbst hat keinen einzelnen Engpass mehr (die großen Doppelrechnungen sind seit #561–#574 weg).

## 3. Umgesetzt

| Nr. | Bereich | Änderung | Datei |
|---|---|---|---|
| R1 | Schnittoptimierung | Jede Runde der Spaltengenerierung löst dasselbe LP mit einem Muster mehr. Der Simplex übernimmt die Schritte der Vorrunde, solange die neue Zeile in keinem Schritt Pivotzeile wird – bis dahin ist jede Zahl gleich. Zwischenstände alle 3 Schritte, höchstens 32 (Speicher). | optimierung.py (`simplex_max`, `SimplexVerlauf`) |
| R2 | Mustersuche | Anzahl je Endenart als eine Zahl statt Liste: zwei Listenkopien je Suchknoten weniger, gleiche Suche und Knotenzahl. | optimierung.py (`bestes_muster`) |
| S1 | Ergebnisprüfung | Nach jeder Kalkulation: jede Zahl in Zeilen und Summen endlich (kein NaN/∞). Sonst `summen["rechenfehler"]`, FEHLER im Angebots-Check (blockiert das PDF, übergehen nur mit Begründung), Warnung im Protokoll, Diagnose ROT. Gültige Ergebnisse unverändert. Kosten ~1 ms bei 200 Positionen. | rechenpruefung.py, rechnen.py, angebot_check.py |
| S2 | Wiederherstellung | Bricht die Kalkulation mit einem Fehler ab, einmal ohne alle Merker neu rechnen (beschädigter Zwischenstand); gelingt es, gilt das Ergebnis, sonst wird der ursprüngliche Fehler gemeldet. | rechnen.py (`kalkulation`) |
| D1 | Diagnose | Befunde mit Stufe und Handlungsempfehlung: ungültige Ergebnisse, lange/oft langsame Rechnungen, Doppelrechnungen, Speicher, langsame Datenbank, Fehler, gestörter Merker, lange Hintergrundaufgaben, Hänger. | diagnose.py |
| D2 | Monitoring | Datenbank-Antwortzeiten in Stufen und längste Anweisung, Rechenzeit der Staffeln, fehlgeschlagene Berechnungen, Hänger-Zähler. | diagnose.py, staffeln.py, tempo.py |
| D3 | Hintergrundaufgaben | Optimieren, Staffelpreise, Maschinenvergleich, Wiederholteile und Sicherung melden ihren Faden; Diagnose zeigt was läuft und seit wann, fertige Läufe, Befund ab 10 min. | hintergrund.py |

## 4. Ergebnisse bleiben gleich

- `tests/test_rechenkerne_2111.py` enthält den bisherigen Simplex und die bisherige Mustersuche unverändert als
  Referenz: 60 zufällige Spaltengenerierungen (auch mit sehr wenigen Zwischenständen) sind Zahl für Zahl gleich
  (`repr`), jede Mustersuche beim Optimieren der Testangebote M und L ebenso, der Schnittplan ist mit und ohne
  Fortsetzung bitgleich.
- 979 aufgezeichnete Simplex-Läufe und 1.209 Mustersuchen aus M/L/XL: alle gleich.
- `rechen_benchmark.py vergleich`: Fingerabdruck aller Messungen (Optimieren, Kalkulation, Stangenwerte, Staffeln,
  Maschinenvergleich, S bis XL) alt = neu.
- `tests/test_regression_ergebnisse.py` (20 feste Angebote): unverändert grün, Stand nicht neu geschrieben.

## 5. Leistung vorher/nachher

Container, 4 Kerne, PostgreSQL 16, Median aus 3 Läufen, je Lauf alle Merker und Hilfsprozesse neu (kalt).
Schwankung ±10–30 % bei kurzen Messungen.

| Messung | Teile | 0.9.447 | neu | Faktor | gleich |
|---|---:|---:|---:|---:|---|
| Optimieren XL (Programm, mit Hilfsprozessen) | 5.224 | 8,78 s | 4,60 s | 1,9 | ja |
| Optimieren XL (ein Prozess, reine Rechenzeit) | 5.224 | 16,73 s | 8,85 s | 1,9 | ja |
| Optimieren L (ein Prozess) | 2.091 | 0,87 s | 0,54 s | 1,6 | ja |
| Simplex allein (979 Läufe aus M/L/XL) | | 11,0 s | 3,9–4,4 s | 2,6 | ja |
| Mustersuche allein (1.209 Suchen) | | 4,4 s | 3,0 s | 1,5 | ja |
| Kalkulation kalt L (A/B im selben Ablauf) | 2.091 | 0,33 s | 0,26 s | ≈ gleich | ja |
| Optimieren/Kalkulation M, Staffeln, Maschinenvergleich | | | | ≈ gleich (Schwankung) | ja |

Arbeitsspeicher: höchstens +4 MB (Zwischenstände des Simplex, begrenzt).

Ziele für die nächsten Schritte: Optimieren XL unter 3 s; Kalkulation 500 Positionen kalt unter 0,5 s; jede
Rechnung, die die Oberfläche blockiert, unter 1 s (Zeitwächter meldet darüber).

## 6. Bewusst nicht umgesetzt

- **GPU**: Rechenkern ist reines Python ohne numpy im Programmpaket; Simplex-Größen (≤ 300 Zeilen) lohnen keine GPU.
- **Warmstart des Simplex nach anderer Pivotregel**: wäre schneller, kann aber bei Gleichständen andere Muster und
  damit andere Schnittpläne ergeben – nicht bitgleich.
- **Datenbank-Umbau (Pooling, zentraler Server)**: jeder PC hat sein eigenes PostgreSQL; Lasttest bis 25 Plätze,
  Wiederverbinden und Zeitlimit sind vorhanden (#514, #589). Neu ist nur die Messung der Antwortzeiten.
- **Neue Paketstruktur der Engines**: siehe Abschnitt 1.

## 7. Werkzeuge

```
python werkzeuge/mit_pg.py -- python werkzeuge/rechen_benchmark.py lauf BAUM_ALT alt.json
python werkzeuge/mit_pg.py -- python werkzeuge/rechen_benchmark.py lauf BAUM_NEU neu.json
python werkzeuge/rechen_benchmark.py vergleich alt.json neu.json --bericht bericht.md
```
