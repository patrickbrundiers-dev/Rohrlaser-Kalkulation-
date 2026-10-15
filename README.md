# Rohrlaser-Kalkulation

Excel-Arbeitsmappe zur Kalkulation und Materialoptimierung von Rohrlaserteilen.

## Stand

| Schritt | Inhalt | Status |
|---|---|---|
| 1 | Grundstruktur der Mappe (Stammdaten, Auftragseingabe, Eingabeprüfungen) | erledigt |
| 2 | STEP-Import (Teilelänge, Schneidweg) mit Python | erledigt |
| 3 | Stangenoptimierung per VBA | offen |
| 4 | Kalkulation (Material, Laserzeit) und Auswertung | offen |

## Inhalt

- `mappe/Rohrlaser_Kalkulation_v01.xlsx`: aktuelle Mappe. Bedienung und Annahmen stehen im Blatt „Anleitung“.
- `tools/build_mappe.py`: erzeugt die Mappe neu (`python3 tools/build_mappe.py`, benötigt `openpyxl`).

- `tools/step_import.py`: STEP-Import in die Mappe, `tools/step_geometrie.py`: Geometrieauswertung.
- `tests/`: Testteile mit bekannten Sollwerten und Prüfskript (`python tests/test_step_import.py`).

Alle Stammdaten in der Mappe sind Beispielwerte.

## STEP-Import

Einmalig: Python 3.10+ installieren, dann `pip install -r requirements.txt`.

Excel-Mappe schließen, dann STEP-Dateien (oder einen Ordner) auf `STEP-Import.bat` ziehen, oder:

```
python tools/step_import.py mappe/Rohrlaser_Kalkulation_v01.xlsx ORDNER_ODER_DATEIEN --werkstoff S235-10219 --stueck 10
```

| Option | Wirkung |
|---|---|
| `--werkstoff ID` | Werkstoff-ID für alle importierten Teile |
| `--stueck N` | Stückzahl für alle importierten Teile |
| `--neue-profile` | Fehlende Profile im Blatt „Profile“ anlegen (mit gemessener Fläche) |
| `--erneut` | Artikel auch eintragen, wenn er schon im Auftrag steht |

Je Volumenkörper wird eine Position angelegt: Artikelnummer = Dateiname, Profil-ID (Abgleich mit „Profile“ über Form und Maße, ±0,15 mm), Teilelänge, Schneidweg und Einstiche. Alle Messwerte stehen zusätzlich im Blatt „STEP-Import“. Vor dem Schreiben wird `*.bak.xlsx` als Sicherung angelegt.

Messregeln und Annahmen:
- Gerade Rohre mit konstantem Querschnitt (keine Biegeteile).
- Teilelänge = größte Ausdehnung entlang der Rohrachse (bei Gehrung die lange Seite).
- Schneidweg = Länge aller Schnittkonturen auf der Außenhaut. Beide Endschnitte zählen voll je Teil (kein gemeinsamer Trennschnitt).
- Einstiche = Anzahl getrennter Schnittkonturen (Enden und jede Bohrung/jeder Ausschnitt).
- Profilform aus dem Querschnitt: Rund-, Quadrat-, Rechteckrohr; alles andere wird als Sonderprofil mit Hinweis gemeldet.
