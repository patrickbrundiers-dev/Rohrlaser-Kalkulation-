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
| 6 | Menüband, neuer Auftrag, Ablage, PDF-Ausgabe, exakte Optimierung kleiner Gruppen | erledigt |
| 7 | Sätze und Staffelpreise | erledigt |
| 8 | Stangenbild (Verschachtelung), Schaltflächen in Excel sichtbar | erledigt |
| P1 | Eigenes Windows-Programm: Gerüst, Datenbank, Stammdaten, Übernahme aus der Mappe | erledigt |
| P2 | Programm: Aufträge, STEP-Import, Optimierung, Kalkulation, Stangenbild | erledigt |
| P3 | Programm: PDF-Ausgabe, Staffelpreise, Auftragsablage, Excel-Export | offen |
| P4 | Programm: Abnahme gegen die Mappe | offen |

## Benutzung (ohne Installation)

1. Unter **Releases → aktuell** `Rohrlaser-Kalkulation.zip` herunterladen und entpacken. Darin liegen die Mappe `Rohrlaser_Kalkulation_v02.xlsm` und der Ordner `STEP-Import` (mit `STEP-Import.exe`). Beide müssen nebeneinander liegen bleiben.
2. Mappe in Excel öffnen und Makros aktivieren („Inhalt aktivieren“). Sperrt Windows die Datei als Download, unter Eigenschaften „Zulassen“ anhaken oder den Ordner als vertrauenswürdigen Speicherort eintragen.
3. Registerkarte **Rohrlaser** im Menüband (oder Schaltflächenleiste im Blatt „Auftrag“, Zeile 11 über den Spaltenköpfen):
   - **Neuer Auftrag**: leert Positionen und Ergebnisse, zählt die Auftragsnummer hoch, setzt das Datum. Stammdaten, Maschine und Stangenlänge bleiben. Fragt vorher, ob der bisherige Auftrag gespeichert werden soll.
   - **STEP importieren**: STEP-Dateien wählen, optional Werkstoff und Stückzahl für alle Teile angeben. Fehlen Profile in den Stammdaten oder stehen Artikel schon im Auftrag, fragt die Mappe nach.
   - **Optimieren**: füllt Schnittplan, Stangenbelegung, Auswertung und Stangenbild. „Stand Optimierung“ (Auftrag C10) zeigt VERALTET, sobald sich danach Auftrag, Profile, Werkstoffe oder Maschinen ändern.
   - **Stangenbild**: Verschachtelung je Stange als maßstäblicher Balken (Endbeschnitt grau, Teile farbig mit Pos. und Länge, dicke Linie = Schnitt, Rest hellgrau, Greiferrest rot). Gleich belegte Stangen stehen einmal da.
   - **Werkstattpapiere / Angebot / Kalkulation** (PDF): erzeugt die PDF-Datei im Ordner `Aufträge` neben der Mappe und öffnet sie. Werkstattpapiere = Materialliste und je Stange die Teile in Schnittreihenfolge (gleich belegte Stangen zusammengefasst), dahinter das Stangenbild.
   - **Staffelpreise rechnen**: rechnet jede Mengenstufe aus dem Blatt „Staffeln“ als eigenen Auftrag neu und schreibt sie ins Blatt „Staffelpreise“ und unter die Angebotspositionen. Danach steht der ursprüngliche Auftrag wieder da.
   - **Auftrag speichern als**: Kopie der Mappe als `<Auftragsnummer> <Kunde>.xlsm` im Ordner `Aufträge`. Die geöffnete Mappe bleibt die Vorlage.
   - **Stammdaten übernehmen**: Profile, Werkstoffe, Preise, Maschinen, Schneiddaten, Gewinde, Zuschläge und Angebotskopf aus einer anderen Mappe (z. B. der gepflegten Vorlage) in eine abgelegte Auftragsmappe kopieren.

Die Mappe bleibt dabei geöffnet. Python wird nur zum Entwickeln gebraucht, nicht für die Benutzung.

## Eigenes Programm (im Aufbau)

Das Programm `Rohrlaser-Kalkulation.exe` soll die Mappe ablösen (Entscheidung 18.10.2026). Stammdaten und Aufträge (Positionen, STEP-Import, Optimierung, Kalkulation, Schnittplan, Stangenbild) sind fertig. PDF-Ausgabe, Staffelpreise, Ablage und Excel-Export folgen; bis dahin entstehen Angebote und Werkstattpapiere noch in der Mappe.

1. Unter **Releases → aktuell** `Rohrlaser-Programm.zip` herunterladen und in einen Ordner entpacken, in dem man schreiben darf (z. B. `C:\Rohrlaser` oder ein Netzlaufwerk-Ordner nur für diesen Arbeitsplatz, nicht `C:\Programme`).
2. `Rohrlaser-Kalkulation.exe` starten. Beim ersten Start legt es den Ordner `Daten` mit `rohrlaser.db` (Stammdaten, Einstellungen) und Beispieldaten an.
3. **Datei → Stammdaten aus Excel-Mappe übernehmen**: liest Profile, Werkstoffe, Preise, Maschinen, Schneiddaten, Gewinde, Zuschläge, Angebotskopf und Auftragsvorgaben aus der gepflegten Mappe (Vorlage oder abgelegte Auftragsmappe). Vorher wird eine Sicherung angelegt. Doppelte Zeilen oder unlesbare Werte meldet das Programm vor der Übernahme.
4. Stammdaten lassen sich in den Reitern direkt bearbeiten (Doppelklick oder lostippen, Zahlen mit Komma). Jede Änderung wird sofort gespeichert. Die Spalte **Prüfung** zeigt wie in der Mappe OK, WARNUNG oder FEHLER. Wird eine Profil-, Werkstoff- oder Maschinen-ID umbenannt, ändern sich die Verweise in Preisen und Schneiddaten mit.

5. Reiter **Aufträge**: neuen Auftrag anlegen (Nummer zählt hoch), kopieren, löschen, suchen (auch nach Artikel) oder **Auftrag aus Excel-Mappe übernehmen** (Kopf und Positionen einer Auftragsmappe). Doppelklick öffnet den Auftrag in einem eigenen Reiter.
6. Im Auftrag: Kopf oben, Positionen wie im Blatt „Auftrag“ bearbeiten (Häkchen **Berechnete Werte** und **STEP-Werte** blenden die übrigen Spalten ein). **STEP importieren** misst die gewählten Dateien mit `STEP-Import.exe` (Ordner `STEP-Import` neben dem Programm, ist im ZIP enthalten) und legt die Positionen an; die Messwerte stehen im Reiter STEP-Protokoll. **Optimieren** plant die Stangen; danach zeigen die Reiter Kalkulation, Schnittplan (Klick auf eine Stange zeigt die Teile), Stangenbild und Auswertung (mit nicht eingeplanten Teilen) die Ergebnisse. Nach jeder Änderung am Auftrag oder an den Stammdaten zeigt die Übersicht „VERALTET“, bis neu optimiert wird.

Optimierung, Status, Schnittplan und Kalkulation rechnen genau wie die Mappe v02: `tests/test_programm_mappe.py` vergleicht 13 Testaufträge Zelle für Zelle mit der von LibreOffice berechneten Mappe. Einzige bewusste Abweichung: Positionen ohne Pos.-Nr. rechnet das Programm wie Excel (LibreOffice weicht dort ab).

Sicherung: beim ersten Start jedes Tages und vor jeder Übernahme eine Kopie nach `Daten/Sicherung` (die letzten 30 bleiben). Zum Umziehen auf einen anderen Rechner den ganzen Programmordner kopieren.

Entwicklung: `pip install -r programm/requirements.txt`, Start mit `python -m rohrlaser` im Ordner `programm`, Tests mit `python tests/test_programm.py` und `python tests/test_programm_mappe.py` (braucht LibreOffice). Der Build (`pyinstaller programm/rohrlaser.spec`) läuft in GitHub Actions auf Windows und prüft die fertige .exe mit `--selbsttest` (Stammdaten und Auftrag aus der Mappe übernehmen, optimieren, die Testteile per STEP-Import einlesen).

## Inhalt

- `mappe/Rohrlaser_Kalkulation_v02.xlsm`: aktuelle Mappe mit Makros. Bedienung und Annahmen stehen im Blatt „Anleitung“.
- `vba/Optimierung.bas`, `vba/StepImport.bas`: Quelltext der Makros (Stangenoptimierung, Übernahme der STEP-Messwerte). `vba/Bedienung.bas`: Menüband, neuer Auftrag, Ablage, Stammdaten, Merker „Optimierung veraltet“. `vba/Ausgabe.bas`: Werkstattpapiere, Angebot, PDF.
- `tools/build_mappe.py`: erzeugt die Mappe neu und bettet die Makros ein (`python3 tools/build_mappe.py`, benötigt `openpyxl`). Das VBA-Projekt schreibt `tools/vba_projekt.py` direkt aus dem Quelltext; Excel übersetzt es beim ersten Öffnen.
- `tools/step_messen.py`: STEP-Messung (OpenCascade), wird als `STEP-Import.exe` ausgeliefert. `tools/step_geometrie.py`: Geometrieauswertung.
- `vba/Staffel.bas`: Staffelpreise (Rechenlauf je Mengenstufe). `tools/staffeln.py`: Python-Fassung der Mengenlogik, Referenz für den Test.
- `tools/optimierung.py`, `tools/step_import.py`: Python-Fassungen von Optimierung und Import. Sie sind die Referenz für die Tests der Makros.
- `.github/workflows/paket.yml`: baut `STEP-Import.exe` auf Windows (PyInstaller), prüft sie gegen die Python-Messung, packt sie mit der Mappe und veröffentlicht das Paket auf `main` als Release „aktuell“.
- `tests/`: Testteile mit bekannten Sollwerten und Prüfskripte:
  - `python tests/test_step_import.py`, `python tests/test_optimierung.py`: Python-Fassungen.
  - `python tests/test_vba.py`: führt die Makros in LibreOffice aus und vergleicht sie mit den Python-Fassungen (39 Testaufträge für die Optimierung, 5 Importfälle) und prüft Werkstattpapier, Angebot, neuen Auftrag, Stammdatenübernahme und die Staffelpreise.

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
- Verfahren: First-Fit- und Best-Fit-Decreasing, danach werden schwach belegte Stangen aufgelöst. Liegt das Ergebnis über der Untergrenze und hat die Gruppe höchstens 60 Teile, sucht eine exakte Suche (Branch and Bound, höchstens 20.000 Suchschritte je Gruppe) eine Einteilung mit weniger Stangen. Die Auswertung zeigt je Gruppe die Untergrenze, den Abstand dazu, ob das Ergebnis nachweislich optimal ist, und den Vergleich mit einer manuellen Einteilung (Eingabereihenfolge, Stange voll, dann nächste).

Kalkulation (Blatt „Kalkulation“):
- Material: Kosten der Stangen laut Schnittplan, je Gruppe nach Längenanteil auf die Positionen verteilt. Verschnitt ist damit enthalten. Der Preis kommt in dieser Reihenfolge: Spalte AP im Auftrag (€/m, nur dieser Auftrag), dann Blatt „Preise“ (€/kg, €/m oder €/Stange), dann der Tonnenpreis des Werkstoffs (Blatt „Werkstoffe“, €/t).
- Laserzeit: Schneidweg je Konturklasse durch den Vorschub der Klasse, Gravur mit eigenem Vorschub, plus Einstiche × Einstechzeit. Gemeinsame Schnitte werden abgezogen.
- Gewinde: aus „Gewinde geprüft“ (z. B. `4xM6; 2xM8`) mit der Zeit je Gewinde aus „Gewinde“.
- Rüstzeit je Auftrag und Stangenwechsel je Stange aus „Maschinen“, gleichmäßig auf alle Teile verteilt.
- Herstellkosten = Material × (1 + Zuschlag Material) + Fertigung × (1 + Zuschlag Fertigung); Verkaufspreis = Herstellkosten × (1 + Gewinn).

## Sätze und Staffelpreise

Satz (Auftrag Spalten AQ/AR):
- Positionen mit gleichem Eintrag in **AQ („Satz“)** gehören zusammen. **AR („Stück je Satz“)** sagt, wie oft ein Teil in einem Satz steckt; leer = 1.
- Die Stückzahl in Spalte G bleibt immer die Gesamtmenge. Anzahl Sätze = G / AR; passt das nicht auf, warnt die Statusspalte.
- Im Angebot steht der Satz als ein Block: eine Zeile „Satz <Name>“ mit Anzahl, Satzpreis und Gesamtpreis, darunter die Teile mit „<Stück je Satz> x <Bezeichnung>“ ohne eigenen Preis. Gerechnet wird weiter je Teil – ein Satz ändert die Optimierung nicht.

Staffelpreise (Blätter „Staffeln“ und „Staffelpreise“):
- Im Blatt „Staffeln“ je Zeile einen Schlüssel (Satzbezeichnung aus AQ oder Positionsnummer aus Spalte A) und eine Menge eintragen. Für einen Satz ist die Menge die Anzahl Sätze, für eine Position die Stückzahl.
- **Staffelpreise rechnen** rechnet jede Stufe als eigenen Auftrag: nur die Positionen dieser Staffel sind besetzt, die Stückzahlen entsprechen der Stufe. Deshalb fallen Rüstzeit, Stangenwechsel und Verschnitt je Stufe neu an und der Preis je Einheit sinkt mit der Menge.
- Ergebnis je Stufe: Teile, Stangen, Material, Laser + Gewinde, Rüsten + Stangenwechsel, Herstellkosten, Herstellkosten und Verkaufspreis je Einheit, Gesamtpreis. Danach wird der ursprüngliche Auftrag wiederhergestellt und neu optimiert.
- Die Stufen sind unabhängig voneinander kalkuliert: Mengen anderer Staffeln werden nicht mitgerechnet.

## Grenzen und Annahmen der Makro-Fassung

- Excel unter Windows. `STEP-Import.exe` ist ein Windows-Programm; die Optimierung läuft auch ohne sie.
- Getestet wird automatisch in LibreOffice, nicht in Excel. LibreOffice ist bei manchen Fehlern nachsichtiger als Excel, deshalb vor dem ersten produktiven Einsatz einmal Beispielauftrag optimieren und ein STEP-Teil importieren.
- Python und VBA runden Grenzfälle (z. B. 128,95 auf eine Stelle) unterschiedlich; Abweichungen von einer Stelle in gerundeten Anzeigewerten sind möglich, an der Einteilung ändert das nichts.
- Das Menüband „Rohrlaser“ ist ohne Verweis auf die Office-Bibliothek gebaut (Rückruf mit `control As Object`). Fehlt die Registerkarte, funktionieren die Schaltflächen im Blatt „Auftrag“ und alle Makros über Alt+F8 weiter.
- Startet `STEP-Import.exe` nicht (z. B. durch eine Firmenrichtlinie gesperrt), muss die IT den Ordner `STEP-Import` freigeben.
