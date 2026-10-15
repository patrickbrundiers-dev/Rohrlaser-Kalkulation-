# Rohrlaser-Kalkulation

Excel-Arbeitsmappe zur Kalkulation und Materialoptimierung von Rohrlaserteilen.

## Stand

| Schritt | Inhalt | Status |
|---|---|---|
| 1 | Grundstruktur der Mappe (Stammdaten, Auftragseingabe, Eingabeprüfungen) | erledigt |
| 2 | STEP-Import (Teilelänge, Schneidweg) mit Python | offen |
| 3 | Stangenoptimierung per VBA | offen |
| 4 | Kalkulation (Material, Laserzeit) und Auswertung | offen |

## Inhalt

- `mappe/Rohrlaser_Kalkulation_v01.xlsx`: aktuelle Mappe. Bedienung und Annahmen stehen im Blatt „Anleitung“.
- `tools/build_mappe.py`: erzeugt die Mappe neu (`python3 tools/build_mappe.py`, benötigt `openpyxl`).

Alle Stammdaten in der Mappe sind Beispielwerte.
