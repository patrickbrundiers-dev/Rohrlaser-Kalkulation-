# Rohrlaser-Kalkulation

Excel-Arbeitsmappe zur Kalkulation und Materialoptimierung von Rohrlaserteilen.

## Stand

| Schritt | Inhalt | Status |
|---|---|---|
| 1 | Grundstruktur der Mappe (Stammdaten, Auftragseingabe, Eingabeprüfungen) | erledigt |
| 2 | STEP-Import (Teilelänge, Schneidweg) | erledigt |
| 3 | Stangenoptimierung | erledigt |
| 4 | Kalkulation (Material, Laserzeit, Rüsten, Preis) und Auswertung | erledigt |
| 5 | Betrieb ohne .bat-Dateien und ohne Installation (VBA + portable STEP-Import.exe) | erledigt |

## Benutzung (ohne Installation)

1. Unter **Releases → aktuell** `Rohrlaser-Kalkulation.zip` herunterladen und entpacken. Darin liegen die Mappe `Rohrlaser_Kalkulation_v02.xlsm` und der Ordner `STEP-Import` (mit `STEP-Import.exe`). Beide müssen nebeneinander liegen bleiben.
2. Mappe in Excel öffnen und Makros aktivieren („Inhalt aktivieren“). Sperrt Windows die Datei als Download, unter Eigenschaften „Zulassen“ anhaken oder den Ordner als vertrauenswürdigen Speicherort eintragen.
3. Im Blatt „Auftrag“:
   - **STEP importieren**: STEP-Dateien wählen, optional Werkstoff und Stückzahl für alle Teile angeben. Fehlen Profile in den Stammdaten oder stehen Artikel schon im Auftrag, fragt die Mappe nach.
   - **Optimieren**: füllt Schnittplan, Stangenbelegung und Auswertung. Alte Ergebnisse werden überschrieben.

Die Mappe bleibt dabei geöffnet. Python wird nur zum Entwickeln gebraucht, nicht für die Benutzung.

## Inhalt

- `mappe/Rohrlaser_Kalkulation_v02.xlsm`: aktuelle Mappe mit Makros. Bedienung und Annahmen stehen im Blatt „Anleitung“.
- `vba/Optimierung.bas`, `vba/StepImport.bas`: Quelltext der Makros (Stangenoptimierung, Übernahme der STEP-Messwerte).
- `tools/build_mappe.py`: erzeugt die Mappe neu und bettet die Makros ein (`python3 tools/build_mappe.py`, benötigt `openpyxl`). Das VBA-Projekt schreibt `tools/vba_projekt.py` direkt aus dem Quelltext; Excel übersetzt es beim ersten Öffnen.
- `tools/step_messen.py`: STEP-Messung (OpenCascade), wird als `STEP-Import.exe` ausgeliefert. `tools/step_geometrie.py`: Geometrieauswertung.
- `tools/optimierung.py`, `tools/step_import.py`: Python-Fassungen von Optimierung und Import. Sie sind die Referenz für die Tests der Makros.
- `.github/workflows/paket.yml`: baut `STEP-Import.exe` auf Windows (PyInstaller), prüft sie gegen die Python-Messung, packt sie mit der Mappe und veröffentlicht das Paket auf `main` als Release „aktuell“.
- `tests/`: Testteile mit bekannten Sollwerten und Prüfskripte:
  - `python tests/test_step_import.py`, `python tests/test_optimierung.py`: Python-Fassungen.
  - `python tests/test_vba.py`: führt die Makros in LibreOffice aus und vergleicht sie mit den Python-Fassungen (27 Testaufträge für die Optimierung, 5 Importfälle).

Alle Stammdaten in der Mappe sind Beispielwerte.

## STEP-Import

Ablauf: Die Schaltfläche startet `STEP-Import.exe`, das die gewählten Dateien misst und die Werte in eine Textdatei im Temp-Ordner schreibt. Das Makro übernimmt sie in den Auftrag und protokolliert alles im Blatt „STEP-Import“. Die Messung lässt sich auch direkt aufrufen:

```
STEP-Import.exe --ausgabe messwerte.txt ORDNER_ODER_DATEIEN
python tools/step_messen.py --ausgabe messwerte.txt ORDNER_ODER_DATEIEN
```

Je Volumenkörper wird eine Position angelegt: Artikelnummer = Dateiname, Profil-ID (Abgleich mit „Profile“ über Form und Maße, ±0,15 mm), Teilelänge, Schneidweg, Einstiche, Anfangs- und Endschnitt (gerade ja/nein, Länge), Innenkonturen (gesamt und nach klein/mittel/groß), Gravur, Bohrungen und Gewinde-Vorschlag. Alle Messwerte stehen zusätzlich im Blatt „STEP-Import“.

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

Ablauf: Stammdaten pflegen, Auftrag erfassen (von Hand oder per STEP-Import), im Blatt „Auftrag“ auf **Optimieren** klicken. Nach jeder Änderung am Auftrag erneut optimieren; alte Ergebnisse werden überschrieben (wer den alten Stand braucht, speichert vorher eine Kopie).

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

## Grenzen und Annahmen der Makro-Fassung

- Excel unter Windows. `STEP-Import.exe` ist ein Windows-Programm; die Optimierung läuft auch ohne sie.
- Getestet wird automatisch in LibreOffice, nicht in Excel. LibreOffice ist bei manchen Fehlern nachsichtiger als Excel, deshalb vor dem ersten produktiven Einsatz einmal Beispielauftrag optimieren und ein STEP-Teil importieren.
- Python und VBA runden Grenzfälle (z. B. 128,95 auf eine Stelle) unterschiedlich; Abweichungen von einer Stelle in gerundeten Anzeigewerten sind möglich, an der Einteilung ändert das nichts.
- Startet `STEP-Import.exe` nicht (z. B. durch eine Firmenrichtlinie gesperrt), muss die IT den Ordner `STEP-Import` freigeben.
