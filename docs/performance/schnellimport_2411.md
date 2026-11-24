# Schnellimport STEP: vollständig gegen Schneidweg & Zusatzarbeiten (24.11.2026)

Master-Prompt Patrick 24.11.2026 „Schnellimport und Schneidweg-Kalkulation ohne editierbare 3D-Geometrie“,
Abschnitte 7, 8 und 12. Gemessen auf dem Entwicklungsrechner (Linux, 1 Messprozess, Qt offscreen, PostgreSQL),
Werkzeuge `werkzeuge/step_benchmark.py lauf --schnell` und `werkzeuge/schnellimport_vergleich.py`.

## Ergebnis in einem Satz

Der Schnellmodus liefert **in allen Dateien dieselben Werte bis auf die letzte Stelle** (126/126 Test-STEPs
bitgleich, 8/8 echte Dateien mit gleichen Positionen und gleicher Kalkulation), braucht **bis zu 68 % weniger
Arbeitsspeicher**, speichert **keine 3D-Netze** mehr und ist vom Import bis zur fertigen Kalkulation **im Mittel 5 %,
bei einzelnen Dateien bis 16 % schneller**. Mehr ist an Zeit nicht drin, ohne die Genauigkeit anzufassen: der
Schneidweg kommt aus derselben exakten Geometrie (Booleans, Querschnitte), und genau diese Rechnung ist fast die
ganze Importzeit. Abkürzungen, die nicht bitgleich sind, hat Patrick am 21.11.2026 abgelehnt.

## Was der Schnellmodus weglässt

| Schritt | vollständig | Schnellkalkulation |
|---|---|---|
| Datei lesen, Körper zerlegen, Profil/Wand/Länge | ja | ja (gleich) |
| Schneidweg, Konturen, Einstiche, Enden, Bohrungen, Gewinde-Vorschlag, Senkungen, Fließlöcher, Gravur | ja | ja (gleich) |
| 3D-Gegenprobe (Linienzüge gegen Editor-Modell) | ja | ja (gleich) |
| Dreiecksnetz der Flächen (BRepMesh) + Flächenkatalog für 3D-Editor | ja | **nein** (Bleche behalten es für die Kantteil-Gegenprobe) |
| 3D-Netz je Position speichern | ja | **nein** (später „3D aus STEP nachladen …“) |
| Prüfdialog mit 3D-Ansicht | ja | **nein**, kompakte Ergebnisübersicht |

## Nur Messung (126 Test-STEPs aus tests/step*, `step_benchmark.py lauf`)

| | vollständig | schnell |
|---|---:|---:|
| Messzeit gesamt | 368,0 s | 361,6 s |
| Messwerte bitgleich | – | 126/126 |
| Linienzüge und Lage der Netze gleich | – | 214/214 |
| Netzdaten | 13,6 MB | 1,6 MB |

## Import bis fertige Kalkulation (echte Dateien, je Modus ein eigener Programmprozess)

„Werte gleich“ = alle Felder aller neuen Positionen und jede Zahl der Kalkulationszeilen und -summen ungerundet
gleich (ohne Datenbank-IDs, Zeitstempel und die Importdaten des Schnellmodus).

| Datei | Pos. | Import bis Kalkulation voll / schnell [s] | Faktor | Messung voll / schnell [s] | Prüfdialog bzw. Übersicht [s] | RAM Programm voll / schnell [MB] | RAM Messung [MB] | 3D-Netze [KB] | Werte gleich |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A_2MB.step | 16 | 22,0 / 22,5 | 0,98 | 19,6 / 20,2 | 1,3 / 1,4 | 402 / 367 | 335 / 335 | 186 / 0 | ja |
| B_3MB.step | 21 | 41,1 / 37,8 | 1,09 | 39,0 / 35,7 | 1,1 / 1,1 | 386 / 374 | 335 / 335 | 99 / 0 | ja |
| C_6MB.step | 12 | 76,0 / 65,8 | 1,16 | 72,0 / 62,2 | 1,9 / 1,6 | 434 / 392 | 335 / 335 | 135 / 0 | ja |
| D_1MB.step | 1 | 10,1 / 9,0 | 1,13 | 6,9 / 6,0 | 1,5 / 1,4 | 396 / 383 | 334 / 334 | 78 / 0 | ja |
| Pizza_oven.STEP | 0 | 226,5 / 222,0 | 1,02 | 191,4 / 187,6 | 34,2 / 31,8 | 887 / 574 | 411 / 335 | 0 / 0 | ja |
| power_rack_last_rev.stp | 12 | 78,5 / 77,2 | 1,02 | 71,7 / 72,1 | 3,5 / 3,2 | 575 / 402 | 358 / 335 | 710 / 0 | ja |
| roof.stp | 6 | 122,9 / 106,9 | 1,15 | 110,7 / 103,2 | 11,5 / 2,4 | 1229 / 399 | 523 / 380 | 45 / 0 | ja |
| Кузов.STEP | 21 | 148,4 / 147,6 | 1,01 | 95,6 / 94,6 | 3,8 / 3,1 | 636 / 448 | 359 / 342 | 201 / 0 | ja |
| **Summe** | | **725,6 / 688,8** | **1,05** | | | | | | |

Hinweise zu den Zahlen:

- Die Messzeiten schwanken zwischen zwei Läufen derselben Datei um etwa ±5 % (A_2MB war im Schnellmodus 0,6 s
  langsamer, obwohl dort weniger gerechnet wird).
- Pizza_oven: 0 Positionen, weil kein Teil ohne Haken übernommen wird (Bleche/Normteile, die der Prüfdialog nur
  nach Haken übernimmt); die Zeiten zeigen trotzdem Messung und Dialogaufbau.
- Кузов: rund 45 s zwischen Messung und Kalkulation sind die Nachmessung langsamer Körper (N4), die beide Modi
  gleich abwarten.
- Die Zeit des Menschen im Prüfdialog (3D drehen, prüfen, Haken) ist nicht gemessen und fällt im Schnellmodus
  weitgehend weg; sie ist im Alltag der größte Gewinn.

## Wo die Zeit hingeht (Schritte je Import)

Gemessen mit den Abschnitten von `tempo.abschnitt` (Spalte „Prüfdialog bzw. Übersicht“) und den Schrittzeiten der
Messung (`ZEITEN`). Lesen der Datei 2–10 %, Messen der Körper (Booleans, Querschnitte, Konturen) 80–90 %,
Dreiecksnetz 2–5 % (bei Rohren mit vielen Konturen bis 13 %), Übernehmen und Kalkulation unter 1 %.

## Zusätzlich beschleunigt: Kantteil-Gegenprobe (beide Modi)

Die Spalte „Prüfdialog bzw. Übersicht“ zeigte bei Pizza_oven 32–34 s. Das Profil (cProfile) ergab: fast alles ist
die 3D-Gegenprobe der Kantteile (`step.kantteile_gegenprobe` → `blech3d.netz`, 30 Kantteile), und dort zu zwei
Dritteln `blech3d._teilen` (5 Mio. Aufrufe: jedes Flächenstück wird an jeder Biegelinie geteilt, auch wenn es ganz
auf einer Seite liegt, und jedes Mal wird seine Fläche neu gerechnet). Neu: liegt ein schon geprüftes Stück ganz
auf einer Seite, kommt es unverändert zurück – dieselben Punkte in derselben Reihenfolge.

| Prüfung | Ergebnis |
|---|---|
| Netze alt/neu auf 5 echten Dateien (147 Kantteile), JSON-Vergleich | 147/147 gleich |
| Zeit `blech3d.netz` für diese 147 Teile | 31,8 s → 20,6 s (−35 %) |

## Nachprüfen

```
python werkzeuge/step_benchmark.py lauf . /tmp/voll tests/step tests/step_konturen
python werkzeuge/step_benchmark.py lauf --schnell . /tmp/schnell tests/step tests/step_konturen
python werkzeuge/step_benchmark.py vergleich /tmp/voll /tmp/schnell
python werkzeuge/schnellimport_vergleich.py /tmp/vergleich DATEI_ODER_ORDNER --bericht bericht.md
```
