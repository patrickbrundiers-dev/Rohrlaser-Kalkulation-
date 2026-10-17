# Rohrlaser-Kalkulation

Excel-Arbeitsmappe zur Kalkulation und Materialoptimierung von Rohrlaserteilen.

## Stand

| Schritt | Inhalt | Status |
|---|---|---|
| 1 | Grundstruktur der Mappe (Stammdaten, Auftragseingabe, Eingabeprüfungen) | erledigt |
| 2 | STEP-Import (Teilelänge, Schneidweg) mit Python | erledigt |
| 3 | Stangenoptimierung (Python) | erledigt |
| 4 | Kalkulation (Material, Laserzeit, Rüsten, Preis) und Auswertung | erledigt |

## Inhalt

- `mappe/Rohrlaser_Kalkulation_v01.xlsx`: aktuelle Mappe. Bedienung und Annahmen stehen im Blatt „Anleitung“.
- `tools/build_mappe.py`: erzeugt die Mappe neu (`python3 tools/build_mappe.py`, benötigt `openpyxl`).

- `tools/step_import.py`: STEP-Import in die Mappe, `tools/step_geometrie.py`: Geometrieauswertung.
- `tools/optimierung.py`: Stangenoptimierung, schreibt Schnittplan, Stangenbelegung und Auswertung.
- `tests/`: Testteile mit bekannten Sollwerten und Prüfskripte (`python tests/test_step_import.py`, `python tests/test_optimierung.py`).

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

Je Volumenkörper wird eine Position angelegt: Artikelnummer = Dateiname, Profil-ID (Abgleich mit „Profile“ über Form und Maße, ±0,15 mm), Teilelänge, Schneidweg, Einstiche, Anfangs- und Endschnitt (gerade ja/nein, Länge), Innenkonturen (gesamt und nach klein/mittel/groß), Gravur, Bohrungen und Gewinde-Vorschlag. Alle Messwerte stehen zusätzlich im Blatt „STEP-Import“. Vor dem Schreiben wird `*.bak.xlsx` als Sicherung angelegt.

Messregeln und Annahmen:
- Gerade Rohre mit konstantem Querschnitt (keine Biegeteile).
- Teilelänge = größte Ausdehnung entlang der Rohrachse (bei Gehrung die lange Seite).
- Konturen werden nach Art getrennt: Anfangsschnitt, Endschnitt, Innenkonturen (Bohrungen, Ausschnitte) und Gravuren. Eine Kontur, die bis ans Rohrende reicht (z. B. Ausklinkung), gehört zum Anfangs- bzw. Endschnitt; das Ende gilt dann als nicht gerade.
- Konturgröße: Jede Innenkontur wird nach ihrem größten Hüllmaß als klein, mittel oder groß eingestuft. Die Grenzen stehen je Maschine im Blatt „Maschinen“ (Vorgabe klein ≤ 10 mm, mittel ≤ 50 mm). Es gilt die im Auftragskopf gewählte Maschine.
- Gravur = Kontur, die nicht durch die Wand geht. Sie wird separat ausgewiesen und ist nicht im Schneidweg enthalten.
- Schneidweg = Anfangsschnitt + Endschnitt + Innenkonturen, gemessen auf der Außenhaut. Beide Endschnitte zählen voll je Teil.
- Einstiche = Anzahl getrennter Schnittkonturen ohne Gravuren.
- Gewinde: Durchgehende Rundbohrungen werden je Durchmesser gezählt. Passt der Durchmesser zu einem Kernloch im Blatt „Gewinde“ (±0,05 mm), wird ein Gewinde vorgeschlagen (z. B. 4× Ø5 → 4xM6). Gerechnet wird nur, was nach manueller Prüfung in „Gewinde geprüft“ eingetragen ist.
- Je Ende wird erkannt, ob der Schnitt gerade (senkrecht zur Achse) ist, und die Schnittlänge des Endes gemessen (Spalten Y–AB im Auftrag). Regel für die Optimierung (Schritt 3): zwei benachbarte Teile mit geraden zugewandten Enden teilen sich einen Schnitt, sonst werden zwei Schnitte gerechnet.
- Profilform aus dem Querschnitt: Rund-, Quadrat-, Rechteckrohr; alles andere wird als Sonderprofil mit Hinweis gemeldet.

## Stangenoptimierung und Kalkulation

Ablauf: Stammdaten pflegen, Auftrag erfassen (von Hand oder per STEP-Import), Excel schließen, `Optimierung.bat` doppelklicken (oder `python tools/optimierung.py mappe/Rohrlaser_Kalkulation_v01.xlsx`), Mappe öffnen. Nach jeder Änderung am Auftrag die Optimierung erneut starten; alte Ergebnisse werden überschrieben, vorher wird `*.bak.xlsx` angelegt.

Regeln:
- Optimiert wird je Profil + Werkstoff + Stangenlänge, ohne Vermischung.
- Belegung je Stange = Endbeschnitt + Teile + Trennungen + Schnittverlust des letzten Schnitts. Frei bleiben muss der Greiferrest. Python prüft jede Stange vor dem Schreiben, die Mappe prüft im Schnittplan (Spalte „Prüfung“) zusätzlich per Formel.
- Trennung: Sind beide zugewandten Enden gerade, gibt es einen gemeinsamen Schnitt (1 × Schnittverlust, 1 Einstich und eine Endschnittlänge gespart). Sonst zwei Schnitte (2 × Schnittverlust + „Abstand getrennte Schnitte“ aus „Maschinen“).
- Teile werden bei Bedarf gedreht, damit gerade Enden aneinanderliegen; schräge Enden kommen an Stangenanfang oder -ende.
- Keine Restverwaltung: Reste zählen als Verschnitt.
- Teile, die nicht auf eine Stange passen oder unvollständige Daten haben, stehen in „Auswertung“ unter „Nicht eingeplante Teile“ und im Auftrag als Warnung.
- Verfahren: First-Fit- und Best-Fit-Decreasing, danach werden schwach belegte Stangen aufgelöst. Die Auswertung zeigt je Gruppe die Untergrenze und den Vergleich mit einer manuellen Einteilung (Eingabereihenfolge, Stange voll, dann nächste).

Kalkulation (Blatt „Kalkulation“):
- Material: Kosten der Stangen laut Schnittplan (€/kg oder €/Stange aus „Preise“), je Gruppe nach Längenanteil auf die Positionen verteilt. Verschnitt ist damit enthalten.
- Laserzeit: Schneidweg je Konturklasse durch den Vorschub der Klasse, Gravur mit eigenem Vorschub, plus Einstiche × Einstechzeit. Gemeinsame Schnitte werden abgezogen.
- Gewinde: aus „Gewinde geprüft“ (z. B. `4xM6; 2xM8`) mit der Zeit je Gewinde aus „Gewinde“.
- Rüstzeit je Auftrag und Stangenwechsel je Stange aus „Maschinen“, gleichmäßig auf alle Teile verteilt.
- Herstellkosten = Material × (1 + Zuschlag Material) + Fertigung × (1 + Zuschlag Fertigung); Verkaufspreis = Herstellkosten × (1 + Gewinn).
