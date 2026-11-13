# Roadmap: Erweiterungen der Rohrlaser-Angebotskalkulation

Stand: 12.11.2026 · Grundlage: Repository `main` Version 0.9.293 (Schema 82), offene Entwurfs-PRs #450, #451, #452 (#358) und drei Handbücher von TOL Computersysteme. Kompakte Aufgabenliste: [FEATURE_BACKLOG_KALKULATION.md](FEATURE_BACKLOG_KALKULATION.md).

> **Nur Analyse und Dokumentation.** Es wurde kein Programmcode, keine Berechnung und keine Datenbank geändert. Jede Umsetzung erfolgt erst nach Freigabe durch Patrick.

**Kennzeichnung in diesem Dokument**

- **[Handbuch]** Aussage aus einem Handbuch, mit Datei und Seite. Seitenzahl = Seite im PDF (bei Manual-2.pdf liegt die gedruckte Seitenzahl eine Seite niedriger).
  - **M1** = `Manual-1.pdf` (PROfirst Kalkulationsprogramm für Schneid-/Kantteile, 109 Seiten)
  - **M2** = `Manual-2.pdf` (PROfirst CAM, Programmiersystem mit Verschachtelung, 102 Seiten)
  - **LT** = `LogiTRACE-Manual-D.pdf` (LogiTRACE Blechabwicklungen V15, 93 Seiten)
- **[Repo]** Erkenntnis aus dem Repository (Datei/Modul angegeben). Geprüft am Code, nicht aus dem Gedächtnis.
- **[Vorschlag]** eigene Idee; noch nicht abgestimmt und nicht gebaut.
- Annahmen sind als solche benannt.

## Inhalt

1. Zusammenfassung der Analyse
2. Vergleich der drei Handbücher mit unserem System
3. Bestandsaufnahme der vorhandenen Funktionen
4. Alle Verbesserungsvorschläge
5. Neue Funktionsideen
6. Intelligente Verknüpfungen
7. Technische Voraussetzungen
8. Wirtschaftlicher Nutzen
9. Priorisierung
10. Abhängigkeiten
11. Risiken
12. Konkrete Umsetzungsempfehlungen

## 1. Zusammenfassung der Analyse

**Ausgangslage [Repo].** Die Kalkulation ist kein Prototyp mehr: rund 139.000 Zeilen Python in 323 Modulen (PySide6-Oberfläche, SQLite-Datendatei, eigene STEP-Messung mit OpenCascade als `STEP-Import.exe`), 390 Testdateien, über 300 Versionen mit dokumentierten Neuerungen. STEP-Import mit Merkmalserkennung, 3D-Editoren für Rohr, Blech, Satz und Schweißbaugruppe, eine nachweisbar gute Stangenoptimierung (Schnittmuster mit Schranke), Zusatzarbeiten mit Regeln, Zukauf mit Lieferanten und Staffeln, Fracht nach PLZ, Staffelpreise, Nachkalkulation, Lernen aus Ist-Werten und eine Schnittstelle zur Rohrlaser Auslastung sind vorhanden.

**Handbücher [Handbuch].** PROfirst und LogiTRACE sind Programme für den **Plattenlaser** und für **Blechabwicklungen** (Stand etwa Windows 7). Übertragbar sind vor allem Rechenwege und Arbeitsweisen: transparente Schneidzeitformel (M1 S. 104), Rüstkosten ernst nehmen (M1 S. 46), freie Arbeitsgänge mit Formeln (M1 S. 45–48), automatische Arbeitsgänge aus Zeichnungsmerkmalen (M1 S. 79–81), Warnung vor gemeinsam verschachtelten Angeboten (M1 S. 82), Stückzahl- und Lagerverwaltung (M2 S. 57–66) sowie Kontaktstellen, Schweißspalt und Kurvenglättung (LT S. 9–17, 77). Tafel-, Resttafel-, Mehrbrenner- und Behälterbau-Themen sind für die Rohr-Kalkulation nicht sinnvoll.

**Ergebnis.** Vieles aus den Handbüchern ist bei uns bereits vorhanden und oft besser gelöst (Staffeln, Fracht, Baugruppen, Datensicherung, STEP statt Zeichnung). Die drei offenen PRs #450, #451 und #452 schließen weitere Lücken. Übrig bleiben **85 Entwicklungsaufgaben** (31 Verbesserungen, 45 neue Funktionen, 9 technische Prüfungen) und 28 intelligente Verknüpfungen. Der größte Hebel liegt nicht in weiteren Einzelfunktionen, sondern im **Verbinden**: eine zentrale Merkmal-Regeltabelle (GEO-009), Preis live im Editor (CAD-004), Schutz vor zu niedrigen Preisen bei Teilbestellung (OFFER-003), genauere Rüstkosten (CALC-005) und belegbar genauere Zeiten aus Ist-Daten (MACH-005).

## 2. Vergleich der drei Handbücher mit unserem System

| Funktion im Handbuch [Handbuch] | Quelle | Stand bei uns [Repo] | Bewertung |
|---|---|---|---|
| Werkstoff, Werkstofftyp (Legierung) mit eigenem Preis | M1 S. 8–10 | Werkstoffe mit Tonnenpreis, Preise je Profil + Werkstoff | gleichwertig (MAT-001) |
| Preisänderung mit Datum, Speichern in die Datenbank aus der Rechnung | M1 S. 21, 34 | 'Gültig ab' + Änderungsverlauf; keine Zeitreihe | ausbauen (MAT-008, MAT-009) |
| Schneidzeit = Einstiche × (Einstechzeit + PIERCINGCYCLETIME) + Längen je Konturklasse ÷ Vorschub × Poti | M1 S. 30, 104 | Konturklassen klein/mittel/groß, Einstechzeit, Nebenzeiten, Dynamik (PR #451) | gleichwertig bis besser (MACH-001/002) |
| Poti-Wert 80/85/90 % nach Dicke | M1 S. 27, 104 | Vorschub-Faktor je Werkstoff, Dynamik | prüfen (MACH-004) |
| Tafelrüstkosten nach Fläche, Maschinenrüstkosten je Güte/Stärke | M1 S. 27–28, 32 | Rüsten Maschine, Rüsten je Abmessung, Stangenwechsel | gleichwertig (MACH-011) |
| Freie Arbeitsgänge mit Formeln (Fragen A/B, Konstanten TA/TB) | M1 S. 45–48 | Zusatzarbeiten + Arbeitsschritte; Formeln im PR #452 | gleichwertig nach #452 (CALC-004) |
| Rüstzeit je Arbeitsgang | M1 S. 46 | Rüstzeit nur bei Arbeitsschritten (Angebot/Abmessung) | ausbauen (CALC-005) |
| Arbeitsgänge Sägen, Entgraten, Bolzenschweißen, Nieten, Prägen, Pulvern, Punktschweißen, Schweißen, Bohren, Gewinde, Senken, Richten, Heften, Planrichten, Einpressen, Zukauf, Verzinken, Reiben, Fremd | M1 S. 49–69 | Großteil als Zusatzarbeiten/Beispielwerte; Reiben/Sägen-Alternative fehlen | ausbauen (CALC-010, CALC-021) |
| Marge Bearbeitung und Marge Material getrennt | M1 S. 105 | Gewinn + 'Gewinn auf Material', Aufschlag Blech/Zukauf | gleichwertig, Anzeige ausbauen (MAT-011) |
| Marge brutto/netto | M1 S. 71 | im PR #452 (G2) | im Bau (OFFER-002) |
| Minimum Angebotspreis je Teil, Aufrunden | M1 S. 33 | Mindestpreis, Mindestauftragswert, Rundung | gleichwertig; Ausweis verbessern (OFFER-017) |
| Versandkosten nach Zonen/Gewicht, Formel je Tonne | M1 S. 35–36 | Frachtrechner mit PLZ, km, Tarifen, Diesel, Packvorschlag | deutlich besser |
| Dynamische Margen, Kundendaten, Kundenkommentar beim Öffnen | M1 S. 37, 42 | Gewinn gestaffelt, Kundenvorgaben; Kundenhinweis im PR #452 | gleichwertig nach #452 |
| Anwenderrechte AV/Vertrieb | M1 S. 39 | Admin/Benutzer, Admin-Schutz | ausbauen (ERP-003) |
| Automatische Arbeitsgänge aus DXF-Farben (Bohren 240, Gewinde 242, Senken 246) | M1 S. 79–81 | STEP-Erkennung + Bestätigung; DXF-Farben als K1 freigegeben | besser (STEP), DXF im Bau (GEO-006) |
| Kantungen in DXF definieren | M1 S. 79–80 | Kantteile aus STEP/DXF, Biegelinien ziehen | gleichwertig (GEO-003) |
| Kamera/PDF nachzeichnen, skalieren, Vektor-PDF → DXF | M1 S. 12–16, 90–92 | Vektor-PDF, Zeichnungstext; Raster-PDF als K2 freigegeben | im Bau (GEO-007) |
| KEEP: offene Konturen schließen, doppelte Linien, Blöcke auflösen | M1 S. 17, 93 | DXF-Import robust (Lücken, doppelte Linien, Layout) | gleichwertig (GEO-020) |
| Mehrteilverschachtelung nur, wenn alle Teile bestellt werden | M1 S. 82–84 | immer gemeinsame Optimierung je Angebot | Risiko, neu (OFFER-003) |
| Staffelpreise durch Kopieren/Multiplizieren | M1 S. 95–96 | eigene Staffeln je Satz/Position mit Schnittschema | deutlich besser |
| Baugruppen mit Hauptbauteil als erste Position | M1 S. 97–101 | Sätze/Schweißbaugruppen mit Struktur; kein Hauptteil | besser; Hauptteil neu (ASM-002) |
| 'Schneidfertig' nur bei vollständigen DXF-Konturen | M1 S. 102 | Prüfstatus; 'nur kalkuliert' im PR #452 | im Bau (CALC-023) |
| Nachkalkulation aus CAM-Verschachtelung | M1 S. 103 | Nachkalkulation, Ist-Zeiten CSV (PR #451), Rückmeldung Auslastung | gleichwertig; Automatik ausbauen (CAM-004) |
| Bilder bei 'bestellt', Programm beim Speichern (PPS) | M1 S. 34 | im PR #452 (G4, G5) | im Bau |
| Externe Datenbank laden (Server/Notebook) | M1 S. 106 | gemeinsamer Ordner, Abgleich, Positionen aus anderem Angebot | besser |
| 1ClickCAM/CAM Medium: Schachtelliste, Autonest, Tafelplan, Etiketten | M2 S. 19–36 | Stangenoptimierung, Schnittplan, Stangenbild, Etiketten mit QR | für Rohr besser |
| Fertigungsauftrag aus PPS-Liste (Excel/CSV) mit Spaltenzuordnung | M2 S. 45–47 | Formulare/Scans; keine Excel-Stückliste | neu (ERP-001) |
| Baugruppen im Fertigungsauftrag immer vollständig | M2 S. 39–41, 47 | Sätze/Fertigungslos (PR #451) | gleichwertig |
| Resttafelverwaltung mit Priorität | M2 S. 53–57 | bewusst keine Restverwaltung | nicht sinnvoll (MAT-017) |
| Stückzahlverwaltung (geschnitten abbuchen) | M2 S. 57–59 | offene Menge je Teil im PR #452 (I2) | im Bau |
| Teil in allen Tafelplänen suchen | M2 S. 59–61 | im PR #452 (I1) | im Bau |
| Blechverwaltung, Min. Lagerbestand, Lagerwert | M2 S. 61–66 | Lager für Stangen, Meldebestand im PR #452 | im Bau; Normteile neu (PART-008) |
| Sparschnitt (gemeinsame Kante), Brücken | M2 S. 26–28, 66, 87, 79 | gemeinsamer Schnitt gerader Enden; Gehrung mit Abstand | gleichwertig; Gehrung nicht sinnvoll (CAM-009) |
| Kleine Konturen: nicht schneiden, bohren, markieren | M2 S. 93–94 | bohren/Ø schneiden | ausbauen (GEO-017) |
| Nur eine Drehlage (strukturierte Oberfläche), Kippen vermeiden | M2 S. 91 | 'nicht wenden' im PR #452, Teil löst sich nicht im PR #451 | im Bau |
| Mehrbrenner, Tafelränder, Resttafel-Abtrennung | M2 S. 67–75 | – | nicht sinnvoll (CAM-008) |
| Automatische Datensicherung lokal + Server | M2 S. 69–70 | Sicherung täglich, geprüft, zweiter Ordner | besser |
| Blechstärke, Kontaktstellen innen/außen, neutrale Faser | LT S. 9–15 | Wand/Innen-/Außenkante bei Gehrung und Gegenrohr; Schweißspalt als K3 | gleichwertig für Rohr, K3 im Bau (CAD-003) |
| Teilung N, Sehnenlänge, Kurven → Bögen | LT S. 16–17, 77–78 | exakte Geometrie aus STEP; Bögen glätten als K5 | im Bau (GEO-008) |
| Rohrleitung aus XYZ-Koordinaten | LT S. 48 | als K4 freigegeben | im Bau (GEO-015) |
| Kantwerkzeuge, Presskraft, Mindestschenkel, K-Faktor-Formel | LT S. 65–68 | K-Faktor-Tabelle; Presskraft/K-Faktor nach Werkstoff im PR #452 | im Bau |
| Anreißen 1:1, Koordinatenliste | LT S. 79–83 | im PR #452 (I4) | im Bau (CAD-011) |
| 3D-DXF/STL-Export | LT S. 89 | STEP-Export; STL als K5 | im Bau |
| Datei für Support sichern (.SAV) | LT S. 74–75 | Support-Paket | gleichwertig (QA-004) |
| Klöpperboden, Konus, Behälter, Kombi-Körper | LT S. 27–43, 70–72 | – | nicht sinnvoll (CAD-012) |

**Was PROfirst/LogiTRACE besser machen [Handbuch]:** der Rechenweg ist im Handbuch offen erklärt (M1 S. 104–105); Rüstzeit gehört zu jedem Arbeitsgang (M1 S. 46); der Anwender wird ausdrücklich vor Preisen gewarnt, die nur bei Bestellung aller Teile stimmen (M1 S. 82); Stückzahl- und Lagerbestände werden beim Schneiden abgebucht (M2 S. 57–62); Rechte trennen AV und Vertrieb (M1 S. 39).

**Was wir besser machen [Repo]:** 3D-STEP statt Nachzeichnen, Merkmale mit Prüfstatus und Herkunft, Stangenoptimierung mit Nachweis gegen die Untergrenze, Staffeln mit eigenem Schnittschema, Fracht nach PLZ und Tarif, Schweißbaugruppen mit Nähten, Lernen aus Ist-Werten, Wiederholteile, Angebotsregeln, Lizenz, Update, Sicherung.

## 3. Bestandsaufnahme der vorhandenen Funktionen

### 3.1 Architektur und Technik [Repo]

- **Sprache/Framework:** Python, Oberfläche PySide6 (Qt), Start `python -m rohrlaser` (`programm/rohrlaser/`). Windows-Programm per PyInstaller, Installer mit Inno Setup, portabel als ZIP (README).
- **Geometrie:** eigene STEP-Messung mit OpenCascade in `programm/step_messung/` (eigene `STEP-Import.exe`, bis 4 Prozesse), 3D-Anzeige ohne OpenGL mit OpenGL-Option (`ansicht3d.py`, `ansicht3d_gl.py`), Netze je Position.
- **Datenbank:** SQLite `rohrlaser.db`, Schema 82 (`datenbank.py`), Tabellen u. a. angebote, positionen, stammdaten, staffeln, staffel_stufen, lager_*, auftrag_status, rueckmeldungen, reklamationen, verlauf, netze. Stammdaten als Tabellen-Definitionen in `stammdaten.py` (Kunden, Profile, Werkstoffe, Oberflächen, Preise, Lieferlängen, Maschinen, Schneiddaten, Gewinde, Zusatzarbeiten, Stundensätze, Arbeitsschritte, Blech, Dreh-/Fräs-Werkstoffe, Prüfregeln, Schweißen, Importprofile, Kundenvorgaben, Arbeitsgang-Regeln, Verpackung, Angebotsregeln). Mehrplatz über gemeinsamen Ordner (`teilen.py`), Sperre der Datendatei.
- **Imports:** STEP/IGES (`step.py`, `step_dialog.py`), DXF Blech und Rohr (`dxf_import.py`, `dxf_rohr.py`), Vektor-PDF und Zeichnung (`pdf_vektor.py`, `pdf_zeichnung.py`), Outlook-Mail und Formulare mit OCR (`mail.py`, `formular.py`, `ocr.py`), Kunden-, Zukauf- und Normteil-CSV.
- **3D-Editor:** Rohr-Editor (`teile_editor.py`, `editor_*.py`), Blech-Editor (`blech_dialog.py`, `blech3d.py`), Satz in 3D, Schweißbaugruppe; Konturen ziehen, Maße am Modell, Gegenrohr, Durchbruch, Lochfeld, Fase, Schrift, Messen, STEP-Export (`step_export.py`). Im PR #450: 3D-Auswahl (`auswahl3d.py`) und Ausschnitt mit Tiefe (`ausschnitt.py`).
- **Kalkulation:** `rechnen.py` (Positionswerte, Kostenarten, Zuschläge, Gewinn, Skonto), `preisschicht.py` (Verpackung, Runden, Preisuntergrenze, Neuteil-Zuschlag …), `schneidweg.py` (Schneidzeit), `optimierung.py` (Stangen), `staffeln.py`, `fracht*.py`, `zukauf.py`, `blech_preis.py`, `drehfraes_preis.py`.
- **Arbeitsgänge:** Zusatzarbeiten mit Abrechnungsarten und Regeln (`zusatz_*.py`), Arbeitsschritte und Stundensätze, Arbeitsgang-Regeln und Vorschläge (`arbeitsgaenge.py`), Vorkalkulation Schweißbaugruppe (`vorkalk.py`).
- **Angebot/Preis:** Angebotsfenster (`angebot_fenster.py`), Angebots-Check und -regeln, Plausibilität, Wiederholteile, Referenzangebote, Preis-Simulator, Angebotsvergleich, Nachkalkulation mit Kennwerten, Lernen aus ✓/✗, Absage-Auswertung.
- **Schnittstellen:** Rohrlaser Auslastung (`auslastung_austausch.py`, `docs/schnittstelle-auslastung.md`), CAM-Ordner (`cam_paket.py`), CSV-Exporte, Outlook, Online-Update mit Signatur, Lizenzdatei Ed25519.
- **Tests:** 390 Dateien in `tests/`, Lauf über `tests/alle.py`, Abnahme mit 8 Testangeboten (`tests/test_abnahme.py`), ruff; CI nur Linux-Teil bei Pull Requests, Windows-Build von Hand.

### 3.2 Bekannte Grenzen und offene Punkte [Repo, Projekt-Memory]

- STEP-Messung: gerade Rohre mit konstantem Querschnitt; Biegerohre nur von Hand (README 'Messregeln').
- Ausschnitt mit Tiefe (PR #450): I-/T-Profil nur innerhalb der Fläche, Eckradius des Rohrs nur angenähert (bis 0,1 mm).
- Optimierung in reinem Python mit festen Schrittgrenzen (300 Muster, 50.000 Suchschritte, exakte Suche bis 60 Teile) – reproduzierbar, aber bei sehr großen Gruppen nur heuristisch.
- Bleche: Richtpreis über Hüllrechtecke auf Tafelformaten, keine echte Verschachtelung (`blech.tafelbedarf`).
- Große STEP-Dateien brauchen viel Speicher (README: etwa 1,2 GB je 1.000 Bohrungen); 3D ohne OpenGL langsamer.
- Mehrplatz über gemeinsamen Ordner; Server-Synchronisation (Schritte 2–4) auf Eis.
- ERP-Preisimport (#358) wartet auf eine ERP-CSV; Buchhaltungs-Zielsystem ungeklärt.
- Für weitere Genauigkeitsprüfungen fehlen 10–20 typische STEPs und 5 bestätigte Angebote (Plan C2/D1).
- Entwurfs-PRs laufen in der CI erst bei 'Ready for review'.

### 3.3 Projektregeln, die jeder Vorschlag beachtet

- Konturen immer zu 100 % wie die STEP (Lage und Form); Bauteile im Export nie verschieben. Konstruktionsvorschläge sind deshalb nur Varianten neben dem Original (CAD-006, CAD-007).
- Gewinde, Senken, Flowdrill und Bohren nur € je Stück (auch Reiben, CALC-021).
- Kein Gewinn auf Zukauf/Bleche (nur Aufschlag); Staffeln nie automatisch anlegen (OFFER-004 nur Vorschlag).
- STEP mit mehreren Teilen nie automatisch Satz; Rohre mit Konturen/Gehrung/Nahtvorgabe nie drehen (Ausnahme 'Teil wenden' als Duplikat, PR #451).
- Zwei benachbarte gerade Enden teilen einen Schnitt; Gehrungen mit Teileabstand; kein Restelager (Verschnitt nur melden).
- Schritte aus einem Editor immer in alle Editoren (Rohr, Blech, Baugruppe, Satz in 3D).
- Jede Änderung aktualisiert die Bedienungsanleitung; sichtbare Änderungen mit Vorher-Nachher-Bildern.

### 3.4 Vorhandene Funktionen je Bereich (Kurzliste)

| ID | Funktion | Stand | Beleg [Repo] |
|---|---|---|---|
| MAT-001 | Materialpreise nach Werkstoff und Güte | ✅ vorhanden | stammdaten.py WERKSTOFFE, PREISE; Version 0.9.194 |
| MAT-002 | Preise nach Abmessung und Wandstärke, Rund-/Quadrat-/Rechteckrohr | ✅ vorhanden | stammdaten.py PROFILFORMEN, PROFILE, LIEFERLAENGEN; normprofile.py |
| MAT-003 | Materialgewicht automatisch | ✅ vorhanden | stammdaten.py Profile (Außenradius 0.9.62), rechnen.py |
| MAT-004 | Verschnitt exakt, Materialkosten je Position nach Längenanteil | ✅ vorhanden | optimierung.py, README Abschnitt Stangenoptimierung, tests/test_abnahme.py |
| MAT-005 | Lieferlängen-Vergleich und Materialvarianten | ✅ vorhanden | stammdaten.py LIEFERLAENGEN, varianten.py |
| MAT-006 | Materialanfrage, Lieferantenantwort, Preiswächter | ✅ vorhanden | materialanfrage.py, lieferantenantwort.py, lieferantenangebote.py, preiswaechter.py, sammel_preis.py |
| MAT-007 | Materialverbrauch je Auftrag, Lager mit Journal und Charge | ✅ vorhanden | fertigung.py, lager.py, lager_seite.py; PR #452 |
| MAT-009 | Preisalter-Warnung im Angebots-Check | 🚧 im Bau/PR | preisluecke.py, angebot_check.py, Feld gueltig_ab |
| MAT-015 | Werkstoff-Gleichwertigkeiten (1.4301 = X5CrNi18-10 = AISI 304) | 🚧 im Bau/PR | step_material.py (PR #450), formular.py, mail.py |
| GEO-001 | STEP-Import Rohre und Profile mit Wand, Länge, Enden, Konturen | ✅ vorhanden | step.py, programm/step_messung/, step_gegenprobe.py |
| GEO-002 | Bohrungen, Langlöcher, Ausschnitte, Durchbrüche, Gewinde, Senkungen, Flowdrill | ✅ vorhanden | bohrbild.py, zusatz_erkennung.py, Versionen 0.9.187, 0.9.237, 0.9.244 |
| GEO-003 | Kantteile erkennen und abwickeln | ✅ vorhanden | blech3d.py, blech.py, stammdaten.py BLECH_KFAKTOREN |
| GEO-004 | DXF-, Vektor-PDF- und Zeichnungs-Import | ✅ vorhanden | dxf_import.py, dxf_rohr.py, pdf_vektor.py, pdf_zeichnung.py, ocr.py |
| GEO-005 | Prüfstatus je Merkmal, Ampel, Importbericht | ✅ vorhanden | step_pruefung.py, step_pruefung_dialog.py, PR #450 Paket 2 |
| GEO-006 | DXF-Farbe/Layer → Bohren, Gewinde, Senken | 🚧 im Bau/PR | Plan PROfirst/LogiTRACE (K1) |
| GEO-007 | Raster-PDF/Scan nachzeichnen und skalieren | 🚧 im Bau/PR | Plan K2 |
| GEO-008 | Facetten-Konturen zu Bögen glätten, STL-Ausgabe | 🚧 im Bau/PR | Plan K5 |
| GEO-017 | Sehr kleine Konturen: Ankörnen/Markieren statt Schneiden | ✅ vorhanden | Version 0.9.162, bohrbild.py |
| GEO-018 | Unklare Merkmale als Rückfrage an den Kunden | 🚧 im Bau/PR | rueckfrage.py, step_pruefung.py |
| GEO-020 | Konturen nur aus Linien/Bögen, offene Konturen schließen (Toleranz) | ✅ vorhanden | dxf_import.py (0.9.188) |
| CALC-001 | Zusatzarbeiten mit Zeit, Stundensatz, Material, Zuschlägen, Mindestbetrag, Fremdleistung | ✅ vorhanden | stammdaten.py ZUSATZARBEITEN, rechnen.zusatz_preis |
| CALC-002 | Arbeitsschritte mit Rüstzeit, Zeit je Einheit, Maschine/Personal, parallel | ✅ vorhanden | stammdaten.py ARBEITSSCHRITTE, STUNDENSAETZE |
| CALC-003 | Arbeitsgang-Regeln und Vorschläge je Position | ✅ vorhanden | arbeitsgaenge.py, zusatz_regeln.py, stammdaten.py ARBEITSGANG_REGELN |
| CALC-004 | Zusatzarbeit mit Formel oder Wertetabelle | 🚧 im Bau/PR | zusatz_formel.py (PR #452) |
| CALC-005 | Rüstzeit je Zusatzarbeit und Los | 🚧 im Bau/PR | stammdaten.py ZUSATZARBEITEN, rechnen.py, staffeln.py |
| CALC-011 | Entgraten nach Schnittlänge, maschinell oder von Hand | 🚧 im Bau/PR | stammdaten.py REGEL_MENGEN |
| CALC-013 | Prüfkosten: Erstmusterprüfbericht, Messprotokoll | 🚧 im Bau/PR | pruefplan.py, kundenvorgabe.py, wiederholteile.py, preisschicht.py (Neuteil-Zuschlag) |
| CALC-014 | Rechenweg je Position in Klartext | 🚧 im Bau/PR | rechnen.py, pdf.py, klartext.py |
| CALC-021 | Reiben als Standard-Zusatzarbeit je Stück | 🚧 im Bau/PR | stammdaten.py Beispielwerte |
| CALC-022 | Pulvern, Verzinken, Strahlen nach Fläche/Gewicht inkl. innen | ✅ vorhanden | zusatz_regeln.py, Version 0.9.182 |
| CALC-023 | Teile nur kalkuliert (nicht schneidfertig) kennzeichnen | 🚧 im Bau/PR | PR #452 |
| PART-001 | Zukaufartikel mit Lieferant, EK-Staffel, Mindestmenge, VPE, Preisgültigkeit, Aufschlagsregeln | ✅ vorhanden | zukauf.py, zukauf_seite.py, zukauf_ek.py |
| PART-002 | Normteile aus STEP abtrennen und als Zukauf übernehmen | ✅ vorhanden | normteil_preise.py, zukaufteile.py (PR #450) |
| PART-003 | Rund-/Vierkantstahl, Dreh-/Frästeile, Bleche als Zukauf | ✅ vorhanden | vollmaterial.py, drehfraes_preis.py, blech_preis.py |
| PART-011 | Zukaufteile als eigene Angebotszeilen oder eingerechnet | ✅ vorhanden | Versionen 0.9.6, 0.9.272 |
| MACH-001 | Maschinenprofile mit Stundensatz, Schneiddaten, Konturklassen, Einstechzeit, Grenzen | ✅ vorhanden | stammdaten.py MASCHINEN, SCHNEIDDATEN, maschinen_vergleich.py |
| MACH-002 | Dynamik, Drehen je Seitenwechsel, Messzyklen, Lademinimum | 🚧 im Bau/PR | dynamik.py, zeit_zusatz.py (PR #451) |
| MACH-003 | Maschinen-, Material- und Personalkosten getrennt | ✅ vorhanden | rechnen.py, Version 0.9.34 |
| MACH-007 | Kapazitätsabhängiger Preishinweis | ✅ vorhanden | kalk_hinweise.auslastung_punkt |
| MACH-009 | Maschinendaten als Datei austauschen | 🚧 im Bau/PR | stammdaten.py, export.py |
| MACH-011 | Rüsten je Abmessung/Werkstoff, Profilwechsel, mannlose Laufzeit, Gas, CO₂ | ✅ vorhanden | rechnen.py, preisschicht.py (J3), co2.py |
| CAD-001 | Rohr-/Blech-Editor mit 3D, Konturen und Maßen am Modell | ✅ vorhanden | teile_editor.py, editor_griffe.py, blech_dialog.py |
| CAD-002 | 3D-Auswahl Körper/Fläche/Kante/Punkt, Ausschnitt mit Tiefe | 🚧 im Bau/PR | auswahl3d.py, ausschnitt.py (PR #450) |
| CAD-003 | Rohr auf Rohr ohne STEP mit Schweißspalt | 🚧 im Bau/PR | Plan K3 |
| CAD-004 | Live-Preis im Editor | 🚧 im Bau/PR | editor_ergebnis.py, rechnen.py |
| CAD-006 | Konstruktionsvorschläge mit €-Ersparnis an den Kunden | 🚧 im Bau/PR | Version 0.9.111, dfm.py, varianten.py |
| CAD-007 | Kundenvariante neben dem Original | 🚧 im Bau/PR | varianten.py, position_kopie.py |
| CAD-011 | Koordinatenliste und 1:1-Abwicklung | 🚧 im Bau/PR | abwicklung_druck.py (PR #452) |
| ASM-001 | Sätze und Schweißbaugruppen mit Unterbaugruppen, Nähten, Vor- und Nachkalkulation | ✅ vorhanden | baugruppe.py, baugruppe_dialog.py, vorkalk.py, umwandeln.py |
| ASM-003 | Stückliste exportieren (CSV/Excel) | 🚧 im Bau/PR | export.py, ausgabe.py |
| OFFER-001 | Staffeln, Mindestwerte, Gewinnstufen, Fracht, Verpackung, Rabatt, Skonto, Kundenvorgaben | ✅ vorhanden | staffeln.py, preisschicht.py, angebotsregeln.py, plausibel.py, nachkalkulation.py, fracht*.py |
| OFFER-002 | Marge brutto/netto, Kundenhinweis beim Öffnen, Teilebilder, PPS-Skript | 🚧 im Bau/PR | ertrag.py, kundenhinweis.py, teilebilder.py, auftrag_skript.py (PR #452) |
| OFFER-005 | Preisaufschlüsselung im Kunden-PDF (optional) | 🚧 im Bau/PR | pdf.py, angebot_ausgabe.py, kundenvorgabe.py |
| OFFER-006 | Kundenpreisliste exportieren | 🚧 im Bau/PR | teilekatalog.py |
| OFFER-010 | Risiko-Hinweis bei geschätzten Merkmalen | 🚧 im Bau/PR | angebot_check.py, angebotsregeln.py, step_pruefung.py |
| OFFER-014 | Hinweis 'Preis gilt bei Bestellung aller Positionen' | ✅ vorhanden | Projekt-Memory 12.11. (vorhanden) |
| CAM-001 | Stangenoptimierung mit Nachweis, gemeinsamer Schnitt, Greiferrest, Endbeschnitt | ✅ vorhanden | optimierung.py, stangenende.py, wenden.py, fertigungslos.py |
| CAM-002 | CAM-Paket, Etiketten mit QR, Werkstattpapiere, Laufzettel | ✅ vorhanden | cam_paket.py, etiketten.py, ausgabe.py |
| ERP-001 | Kunden-Stückliste (Excel/CSV) als Angebot einlesen | 🚧 im Bau/PR | formular.py, anfragen.py, kunden_csv.py (Spaltenzuordnung als Vorbild) |
| ERP-002 | ERP-Preisimport (#358) | 🚧 im Bau/PR | PR #358 |
| ERP-005 | Schnittstelle Auslastung, Kunden-CSV, Angebots-CSV, Support-Paket | ✅ vorhanden | auslastung_austausch.py, kunden_csv.py, export.py, support.py |
| QA-001 | Rechenweg-Test gegen die Handbuch-Formel | 🚧 im Bau/PR | tests/, rechnen.py |
| QA-003 | Referenzangebote nach jeder Stammdatenänderung prüfen | 🚧 im Bau/PR | referenzangebote.py, preiswaechter.py |
| MAT-020 | Kundenmaterial (Beistellung) mit Verschnittrisiko | ✅ vorhanden | angebot.py (handling_beistellung), optimierung.py |
| OFFER-017 | Mindermengenzuschlag sichtbar ausweisen | 🚧 im Bau/PR | rechnen.py (mindestwert), pdf.py |
| OFFER-018 | Angebotsgültigkeit nach Preisschwankung des Werkstoffs | 🚧 im Bau/PR | angebot.py, stammdaten.py WERKSTOFFE |
| CAM-010 | Mengenvorschlag: 'x Stück mehr passen ohne weitere Stange' | 🚧 im Bau/PR | optimierung.py, kalk_hinweise.py |
| GEO-021 | Bohrungen und Konturen zu nah an Kante/Rundung, Mindeststeg | ✅ vorhanden | dfm.py, Version 0.9.238 |
| GEO-022 | Gewindeeinsatz/Einschweißmutter im Rohr | 🚧 im Bau/PR | Plan Paket 5 |
| CAD-013 | Maß einer Kontur ändern, Kalkulation zieht nach | ✅ vorhanden | editor_griffe.py, Version 0.9.66 |
| ASM-007 | Baugruppen kopieren und wiederverwenden | ✅ vorhanden | Versionen 0.9.28, 0.9.215 |
| OFFER-019 | Nachkalkulation und Angebotsvergleich | ✅ vorhanden | nachkalkulation.py, kennwerte.py, angebotsvergleich.py |
| QA-004 | Support-Datei mit allen Daten eines Falls | ✅ vorhanden | support.py |
| OFFER-020 | Positionstext aus erkannten Merkmalen | 🚧 im Bau/PR | angebot_ausgabe.py, bohrbild.py, zusatz_erkennung.py |
| GEO-023 | Konturen auf der Längsnaht: Lage prüfen und melden | 🚧 im Bau/PR | PR #451 |
| QA-005 | Stammdaten-Prüfung mit FEHLER/WARNUNG | 🚧 im Bau/PR | stammdaten.py pruefen() |

## 4. Alle Verbesserungsvorschläge

Je Bereich alle Punkte mit Kennzeichnung. Bewertung und Phase stehen im [Backlog](FEATURE_BACKLOG_KALKULATION.md); hier stehen Inhalt, Quelle und Beleg.

### A. Material- und Rohstoffkalkulation

#### MAT-001 – Materialpreise nach Werkstoff und Güte

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Tonnenpreis je Werkstoff, dazu Preis je Profil + Werkstoff in €/kg, €/m oder €/Stange; Teuerungszuschlag je Werkstoff.
- **[Handbuch]** M1 S. 8, 10; M2 S. 14
- **[Repo]** stammdaten.py WERKSTOFFE, PREISE; Version 0.9.194

#### MAT-002 – Preise nach Abmessung und Wandstärke, Rund-/Quadrat-/Rechteckrohr

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Profil-ID trägt Form, Abmessung und Wand; Preise und Lieferlängen je Profil-ID; offene Profile, U/C/L, Träger, Flachstahl.
- **[Handbuch]** M1 S. 69–70 (Fremdbearbeitung Rundrohr/Vierkantrohr)
- **[Repo]** stammdaten.py PROFILFORMEN, PROFILE, LIEFERLAENGEN; normprofile.py

#### MAT-003 – Materialgewicht automatisch

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Metergewicht aus Querschnitt und Dichte inkl. Außenradius; PROfirst rechnet dafür Formeln von Hand (A/1000*B*TA+…).
- **[Handbuch]** M1 S. 69–70
- **[Repo]** stammdaten.py Profile (Außenradius 0.9.62), rechnen.py

#### MAT-004 – Verschnitt exakt, Materialkosten je Position nach Längenanteil

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Belegung je Stange mit Endbeschnitt, Trennschnitten, Greiferrest; Untergrenze, Nachweis optimal, Vergleich mit manueller Einteilung.
- **[Handbuch]** M1 S. 83–84 (Werkstoffpreis in der Mehrteilverschachtelung)
- **[Repo]** optimierung.py, README Abschnitt Stangenoptimierung, tests/test_abnahme.py

#### MAT-005 – Lieferlängen-Vergleich und Materialvarianten

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Weitere Lieferlängen (z. B. 12 m) werden verglichen und nur bei Ersparnis empfohlen; Varianten je Stangengruppe.
- **[Handbuch]** M1 S. 21 (Tafelformat probieren)
- **[Repo]** stammdaten.py LIEFERLAENGEN, varianten.py

#### MAT-006 – Materialanfrage, Lieferantenantwort, Preiswächter

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Stangenbedarf als Anfrage-Mail, Antwort (Mail/PDF) einlesen, Preisänderung prüft offene Angebote.
- **[Handbuch]** M1 S. 34 (Preise ändern sich oft täglich)
- **[Repo]** materialanfrage.py, lieferantenantwort.py, lieferantenangebote.py, preiswaechter.py, sammel_preis.py

#### MAT-007 – Materialverbrauch je Auftrag, Lager mit Journal und Charge

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Verbrauch je Charge in der Fertigung, Lagerbestand mit Reservierung; Meldebestand im offenen PR #452 (H2).
- **[Handbuch]** M2 S. 62–66
- **[Repo]** fertigung.py, lager.py, lager_seite.py; PR #452

#### MAT-008 – Materialpreis als Zeitreihe statt Überschreiben

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Heute hat 'Preise' je Profil + Werkstoff genau eine Zeile mit 'Gültig ab'; ältere Werte stehen nur im Änderungsverlauf. Vorschlag: mehrere datierte Preiszeilen behalten, das Angebot nimmt den am Angebotsdatum gültigen Preis, dazu ein Verlaufsdiagramm je Werkstoff/Abmessung und Durchschnitt der letzten 3/6/12 Monate. Festgeschriebene Preise (preisbasis) bleiben unverändert.
- **[Handbuch]** M1 S. 21 (Datum der Preisänderung), S. 34
- **[Repo]** stammdaten.py PREISE (Schlüssel profil_id + werkstoff_id), verlauf.py
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 7, Aufwand 5, Priorität Mittel, Mittel, Phase 2; Abhängigkeiten: Schema-Erweiterung; Preiswächter und Preisbasis müssen den Stichtag kennen

#### MAT-009 – Preisalter-Warnung im Angebots-Check

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Ist der wirksame Materialpreis älter als N Tage (Einstellung, Vorgabe 30, leer = aus), meldet der Angebots-Check HINWEIS mit Knopf 'Materialanfrage …'. Im Code gibt es eine Warnung für fehlende Preise (Preislücke), aber keine für alte. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Einstellung „Materialpreis alt ab [Tage]“ (30, 0 = aus), Hinweis mit Sprung zur Materialanfrage.
- **[Handbuch]** M1 S. 34 („Oft ändern sich die Preise täglich“)
- **[Repo]** preisluecke.py, angebot_check.py, Feld gueltig_ab

#### MAT-010 – Materialpreislisten importieren (Rohre/Profile)

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Lieferanten-Preisliste als CSV/Excel mit Spaltenzuordnung (Profil, Werkstoff, Basis, Preis, Länge, gültig ab), Vorschau Alt/Neu, Übernahme als datierte Zeilen. Bestand: Normteil-Preisliste CSV, Lieferantenantwort aus Mail; der ERP-Preisimport liegt als PR #358 offen und wartet auf Patricks Beispiel-CSV. Stand 12.11.: Läuft über PR #358 (ERP-Preisimport), wartet auf Patricks ERP-CSV.
- **[Handbuch]** M1 S. 10; M2 S. 46–47 (Listen aus PPS/ERP)
- **[Repo]** normteil_preise.py preisliste_lesen, lieferantenantwort.py, PR #358
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 8, Aufwand 4, Priorität Hoch, Mittel, Phase 1; Abhängigkeiten: Beispieldatei des Lieferanten/ERP (#358); MAT-008 empfohlen

#### MAT-011 – Getrennter Gewinn auf Material und auf Bearbeitung sichtbar

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Vorschlag]** Die Einstellung 'Gewinn auf Material [%] (leer = wie Gewinn)' gibt es schon. Vorschlag: im Angebotskopf und im Kalkulations-PDF beide Sätze nebeneinander zeigen und je Kunde vorbelegen (Kundenvorgaben), wie PROfirst Bauteilpreis = Bearbeitung × (1+Marge Bearb.) + Material × (1+Marge Mat.). Gebaut am 13.11.2026 (Phase 1 Rest): Feld „Gewinn auf Material [%]“ im Angebotskopf („wie Gewinn“ = leer) und in den Kundenvorgaben (Schema 85).
- **[Handbuch]** M1 S. 105
- **[Repo]** stammdaten.py Einstellung gewinn_material, rechnen.py, kundenvorgabe.py
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 6, Aufwand 2, Priorität Mittel, Einfach, Phase 1; Abhängigkeiten: keine

#### MAT-012 – Materialindex/Legierungszuschlag je Monat

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Monatswerte (von Hand oder CSV, nichts aus dem Netz erfunden) für Legierungszuschlag Edelstahl/Aluminium bzw. Stahlindex; Tonnenpreis = Basis + Index des Monats; Preiswächter meldet betroffene offene Angebote. Ergänzt die vorhandene Gleitklausel.
- **[Handbuch]** M1 S. 10 (Werkstofftypen mit eigenen Preisen)
- **[Repo]** gleitklausel.py, preiswaechter.py, Teuerungszuschlag (0.9.194)
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 7, Aufwand 4, Priorität Mittel, Mittel, Phase 2; Abhängigkeiten: MAT-008

#### MAT-013 – Mindestabnahme je Abmessung (Bund, Mindestmenge des Lieferanten)

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Feld 'Mindestabnahme [Stangen]' in Lieferlängen. Liegt der Bedarf darunter, rechnet das Angebot die Mehrmenge wahlweise als Kosten ein oder zeigt nur einen Hinweis. Kein Restelager: Mehrmenge wird nie als Bestand geführt.
- **[Handbuch]** M2 S. 62 (Tafelbestand), Projektregel 'Kein Restelager'
- **[Repo]** stammdaten.py LIEFERLAENGEN; zukauf.bestellmenge (gibt es schon für Zukauf)
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 7, Aufwand 3, Priorität Mittel, Einfach, Phase 2; Abhängigkeiten: Regel 'kein Restelager' beachten

#### MAT-014 – Vorverzinkt/vorbeschichtet kaufen oder nachträglich veredeln

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Variantenvergleich je Stangengruppe: Rohmaterial + Feuerverzinken nach dem Laser gegen sendzimirverzinktes Vormaterial (Oberfläche der Stammdaten), mit Preis und Lieferzeit. Nur Vorschlag, der Kunde entscheidet.
- **[Handbuch]** M1 S. 67 (Verzinken als Arbeitsgang)
- **[Repo]** varianten.py, stammdaten.py OBERFLAECHEN
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 4, Priorität Mittel, Mittel, Phase 2; Abhängigkeiten: Oberflächen mit Preisen gepflegt

#### MAT-015 – Werkstoff-Gleichwertigkeiten (1.4301 = X5CrNi18-10 = AISI 304)

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Eine Tabelle Gleichnamen je Werkstoff, genutzt von Mail-, Formular-, Zeichnungs- und STEP-Erkennung. PR #450 (step_material.py) erkennt eindeutige Namen schon für STEP; Vorschlag: eine gemeinsame, pflegbare Liste für alle Quellen. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Gemeinsame Gleichnamen-Liste + Einstellung „Werkstoff-Gleichnamen“.
- **[Handbuch]** M1 S. 9 (Werkstoffkodierung), S. 34 (Werkstofftyp bestimmt Werkstoff)
- **[Repo]** step_material.py (PR #450), formular.py, mail.py

#### MAT-016 – Zeugniskosten (3.1) je Abmessung

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Vorschlag]** Fordert der Kunde Abnahmeprüfzeugnisse (Kundenvorgabe), kommt je Abmessung/Charge ein Betrag hinzu (Lieferantenpreis je Zeugnis), im Angebot als eigene Zeile oder umgelegt. Gebaut am 13.11.2026 (Phase 1 Rest): Einstellung „Werkszeugnis 3.1 je Abmessung [€]“, Haken „Werkszeugnis 3.1 verlangt“ im Angebotskopf und Kundenvorgabe; umgelegt wie die Pauschale je Abmessung.
- **[Handbuch]** M2 S. 65 (Chargennummer)
- **[Repo]** kundenvorgabe.py, lager.py Charge
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 5, Aufwand 2, Priorität Niedrig, Einfach, Phase 1; Abhängigkeiten: keine

#### MAT-017 – Reststückverwaltung/Restelager ausbauen

- **Kennzeichnung:** Nicht sinnvoll
- **Begründung** Nicht sinnvoll: Projektregel 'Kein Restelager (Verschnitt nur melden)'. Die vorhandene optionale Einstellung für Reststücke im Lager bleibt, wird aber nicht erweitert. PROfirst verwaltet Resttafeln mit Priorität (Blech).
- **[Handbuch]** M2 S. 53–57; M1 S. 31
- **[Repo]** lager.py reste_aktiv, README 'Keine Restverwaltung'

#### MAT-018 – Wöchentlicher Sammelbedarf über beauftragte Aufträge

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Stangenbedarf aller beauftragten, noch nicht bestellten Aufträge je Abmessung bündeln (Fertigungslos aus PR #451 als Grundlage), Mindestabnahme (MAT-013) berücksichtigen, eine Materialanfrage je Lieferant.
- **[Handbuch]** M2 S. 62–66 (Blechverwaltung für Einkauf)
- **[Repo]** materialanfrage.py, fertigungslos.py (PR #451)
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 7, Aufwand 4, Priorität Mittel, Mittel, Phase 4; Abhängigkeiten: PR #451 gemergt; MAT-013

#### MAT-019 – Gewicht aus STEP-Volumen gegen gerechnetes Gewicht prüfen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Weicht das Gewicht aus STEP-Volumen × Dichte deutlich vom Gewicht aus Profil × Länge ab, stimmt oft Wand, Profil oder Werkstoff nicht: Hinweis im Prüfdialog. Versteckter, billiger Fehlerfänger vor dem Preis.
- **[Repo]** step.py, programm/step_messung/
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Mittel, Einfach, Phase 2; Abhängigkeiten: keine

#### MAT-020 – Kundenmaterial (Beistellung) mit Verschnittrisiko

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Handling Kundenmaterial [€/m] gibt es. Vorschlag: benötigte Stangen des Kunden aus der Optimierung als Beistell-Liste ins Angebot (wie viel Material er liefern muss) und Hinweis bei Fehlmenge. Beistell-Liste mit Stangenbedarf steht schon im Angebot (ausgabe.beistellung_text); offen bleibt nur ein Hinweis bei Fehlmenge.
- **[Repo]** angebot.py (handling_beistellung), optimierung.py

#### MAT-021 – Stangenwechsel-Zeit nach Stangengewicht

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Stangen über X kg (Kran, Hilfe) brauchen länger: Zeit je Stangenwechsel nach Gewichtsklasse statt fest.
- **[Handbuch]** M1 S. 27–28 (Tafelrüstkosten)
- **[Repo]** rechnen.py (Stangenwechsel), stammdaten.py MASCHINEN
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 5, Aufwand 2, Priorität Niedrig, Einfach, Phase 2; Abhängigkeiten: keine

### B. Automatische Geometrieerkennung

#### GEO-001 – STEP-Import Rohre und Profile mit Wand, Länge, Enden, Konturen

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Profilform aus dem Querschnitt, Konturen nach Art und Größe (klein/mittel/groß je Maschine), Gravur, Einstiche, 3D-Gegenprobe; IGES-Import.
- **[Handbuch]** M1 S. 29 (Groß/Mittel/Kleinkonturen)
- **[Repo]** step.py, programm/step_messung/, step_gegenprobe.py

#### GEO-002 – Bohrungen, Langlöcher, Ausschnitte, Durchbrüche, Gewinde, Senkungen, Flowdrill

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Gewinde über Kernloch (±0,05 mm) und ausmodelliert, Senkung durch die Wand, Einnietmuttern aus Sechskantlöchern, Bohrungsart umschaltbar.
- **[Handbuch]** M1 S. 79–81
- **[Repo]** bohrbild.py, zusatz_erkennung.py, Versionen 0.9.187, 0.9.237, 0.9.244

#### GEO-003 – Kantteile erkennen und abwickeln

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Bleche aus STEP/DXF mit Biegungen, K-Faktor-Tabelle, Abwicklung als DXF; K-Faktor nach Werkstoff im PR #452 (J2).
- **[Handbuch]** M1 S. 79–80; LT S. 65–68
- **[Repo]** blech3d.py, blech.py, stammdaten.py BLECH_KFAKTOREN

#### GEO-004 – DXF-, Vektor-PDF- und Zeichnungs-Import

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** DXF Blech und Rohr (Ansichten, Isometrie), doppelte Linien, Lücken, Rahmen; Vektor-PDF wie DXF; Formulare/Scans mit Texterkennung.
- **[Handbuch]** M1 S. 16, 90–94; M2 S. 42–43
- **[Repo]** dxf_import.py, dxf_rohr.py, pdf_vektor.py, pdf_zeichnung.py, ocr.py

#### GEO-005 – Prüfstatus je Merkmal, Ampel, Importbericht

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Merkmale grün/gelb/rot mit Herkunft; Importbericht je Datei und 'Wie in der STEP übernehmen' im PR #450.
- **[Handbuch]** M1 S. 102 (nur 'schneidfertig' wenn alle Konturen)
- **[Repo]** step_pruefung.py, step_pruefung_dialog.py, PR #450 Paket 2

#### GEO-006 – DXF-Farbe/Layer → Bohren, Gewinde, Senken

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Freigegeben als Paket K1 (Farbe einstellbar), Bau im Thread 'STEP-Import schneller und genauer machen'.
- **[Handbuch]** M1 S. 81 (Farben 240/242/246); M2 S. 21
- **[Repo]** Plan PROfirst/LogiTRACE (K1)

#### GEO-007 – Raster-PDF/Scan nachzeichnen und skalieren

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Freigegeben als Paket K2.
- **[Handbuch]** M1 S. 12–16
- **[Repo]** Plan K2

#### GEO-008 – Facetten-Konturen zu Bögen glätten, STL-Ausgabe

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Freigegeben als Paket K5.
- **[Handbuch]** LT S. 77–78, S. 89
- **[Repo]** Plan K5

#### GEO-009 – Zentrale Merkmal-Regeln: jedes Merkmal → Arbeitsgang/Zusatzarbeit/Prüfregel

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Repo]** Gebaut am 13.11.2026 (Phase 2, Paket 2a): Arbeitsgang-Regeln mit Bohrung Ø von/bis und Wand von/bis (Schema 86), Übersicht „Alle Merkmal-Regeln …“ (merkmal_regeln.py) aus 5 Quellen.
- **[Vorschlag]** Heute steckt die Zuordnung an mehreren Stellen (Bohrbild, Erkennungswörter, Arbeitsgang-Regeln, Prüfregeln). Vorschlag: eine Tabelle 'Merkmal-Regeln' (Merkmal, Bedingung wie Ø-Bereich/Werkstoff/Wand/Kunde, Folge: Zusatzarbeit, Arbeitsgang, Prüfregel oder Hinweis, Menge aus Merkmal, Vorschlag oder automatisch). Grundlage für fast alle Verknüpfungen in Kapitel 6. Gewinde/Senken/Bohren bleiben € je Stück.
- **[Handbuch]** M1 S. 79–81 (automatische Arbeitsgänge aus Zeichnung)
- **[Repo]** bohrbild.py, zusatz_erkennung.py, zusatz_regeln.py, arbeitsgaenge.py, stammdaten.py ARBEITSGANG_REGELN, PRUEFREGELN
- **Bewertung:** Kundennutzen 8, wirtschaftlicher Nutzen 8, Aufwand 5, Priorität Hoch, Mittel, Phase 2; Abhängigkeiten: keine; ersetzt nichts, liest die vorhandenen Regeln mit

#### GEO-010 – Passungen und Toleranzen aus der Zeichnung an die Bohrung binden

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Texte wie 'Ø10 H7', '4x M8', 'gesenkt 90°' aus PDF/Zeichnung mit gemessenem Ø der STEP-Bohrung abgleichen und Reiben/Gewinde/Senken je Bohrung vorschlagen (gelb, erst nach ✓ gerechnet). Bestand: Erkennungswörter je Zusatzarbeit und Gewinde aus der Zeichnung (0.9.239), aber ohne Bindung an die einzelne Bohrung.
- **[Handbuch]** M1 S. 68 (Reiben), S. 81
- **[Repo]** zusatz_erkennung.py, pdf_zeichnung.py, bohrbild.py
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 7, Aufwand 5, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: GEO-009

#### GEO-011 – STEP AP242: PMI und Bohrungsmerkmale lesen

- **Kennzeichnung:** Zunächst technisch zu prüfen
- **[Vorschlag]** Manche CAD-Systeme schreiben Gewinde, Passungen und Oberflächenangaben als PMI/Feature in AP242. Prüfen, ob OpenCascade (XDE) diese Angaben in den Kundendateien liefert; wenn ja, wären Gewinde/Passungen sicher statt geschätzt. Annahme, nicht geprüft: die meisten Kundendateien sind AP203/AP214 ohne PMI.
- **[Repo]** programm/step_messung/step_geometrie.py
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 6, Aufwand 8, Priorität Niedrig, Schwierig, Phase 3; Abhängigkeiten: 10–20 echte Kunden-STEPs (offen bei Patrick, C2/D1)

#### GEO-012 – Schweißvorbereitung (Fasen) als Arbeitsgang

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Fase-Zone wird im PR #450 erkannt, die Schweißbaugruppe nutzt Fasen (0.9.282). Vorschlag: Fase am Rohrende/Blech als Merkmal mit Folge 'Laser-Fase (3D-Schnitt)' oder 'Fase anarbeiten' (Zeit je m) über GEO-009.
- **[Handbuch]** M1 S. 58 (Schweißen V-Naht)
- **[Repo]** PR #450 (Fase-Zone), vorkalk.py, naht.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Mittel, Einfach, Phase 3; Abhängigkeiten: GEO-009, PR #450

#### GEO-013 – Spiegelteile (links/rechts) erkennen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Zwei Positionen, die spiegelbildlich gleich sind, werden markiert: gemeinsame Programmierung (Programmierkosten einmal, wie A3), Hinweis im Angebot, auf Wunsch eine Position mit 'je x links/rechts'. Geometrie bleibt je Teil 100 % wie STEP.
- **[Handbuch]** M1 S. 20 (Symmetrie erlaubt ja/nein)
- **[Repo]** wiederholteile.py, rechnen.py Programmierung (A3)
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 5, Aufwand 4, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: keine

#### GEO-014 – Ähnliche Teile trotz anderer Artikelnummer finden

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Wiederholteile und Revisionen werden erkannt; Vorschlag: Geometrie-Signatur (Profil, Länge ±1 %, Anzahl/Art der Konturen, Enden) für 'ähnliches Teil schon angeboten zu X €' auch ohne gleiche Nummer.
- **[Handbuch]** M1 S. 101 (vorhandene Teile automatisch finden)
- **[Repo]** wiederholteile.py, referenzangebote.py, teilekatalog.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 7, Aufwand 5, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: keine

#### GEO-015 – Biegerohre aus der STEP messen

- **Kennzeichnung:** Zunächst technisch zu prüfen
- **[Vorschlag]** Messregel heute: gerade Rohre mit konstantem Querschnitt; Biegerohre gibt es nur von Hand. Prüfen, ob gebogene Mittellinie (Gerade/Bogen) aus der STEP sicher genug ist. Rohrzug aus XYZ ist als K4 schon freigegeben.
- **[Handbuch]** LT S. 48 (Rohrleitung XYZ)
- **[Repo]** README 'Messregeln', biegerohr.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 8, Priorität Niedrig, Schwierig, Phase 3; Abhängigkeiten: Beispiel-STEPs mit Biegeteilen; K4

#### GEO-016 – Flachgedrückte/gequetschte Rohrenden erkennen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Rohr mit flach gedrücktem Ende (z. B. Streben) wird heute als Sonderform gemeldet. Vorschlag: Merkmal 'Ende gequetscht' mit Zusatzarbeit Quetschen je Ende; Laser schneidet nur das gerade Rohr (gestreckte Länge).
- **[Repo]** step.py (Sonderprofil-Hinweis)
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 5, Aufwand 6, Priorität Niedrig, Mittel, Phase 3; Abhängigkeiten: Beispiel-STEPs

#### GEO-017 – Sehr kleine Konturen: Ankörnen/Markieren statt Schneiden

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Für Bohrungen unter 0,7 × Wand gibt es 'bohren' oder 'Ø schneiden'. Vorschlag: dritte Wahl 'ankörnen (markieren) + Bohren' mit Markierzeit statt Schneidzeit. Gibt es schon als „Bohren (markieren, aufbohren)“ im Bohrbild (bohrbild.py).
- **[Handbuch]** M2 S. 93–94 (Bearbeitung kleiner Konturen: nicht schneiden, bohren, markieren)
- **[Repo]** Version 0.9.162, bohrbild.py

#### GEO-018 – Unklare Merkmale als Rückfrage an den Kunden

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Aus gelben Merkmalen (Gewinde ja/nein, Werkstoff fehlt, Revision unklar) per Klick eine Rückfrageliste/Mail. Rückfragen gibt es schon (rueckfrage.py); neu ist das Befüllen direkt aus dem Prüfstatus. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Gelbe/offene STEP-Merkmale als Fragen in der Rückfrage-Mail.
- **[Handbuch]** M1 S. 102 (unsichere Teile kennzeichnen)
- **[Repo]** rueckfrage.py, step_pruefung.py

#### GEO-019 – Revisionsvergleich der Geometrie

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Neue Revision wird erkannt (0.9.287). Vorschlag: farbiger 3D-Vergleich alt/neu (Konturen hinzu/weg/geändert) und nur die geänderten Merkmale neu prüfen lassen.
- **[Repo]** wiederholanfrage.py, neu_einlesen.py, ansicht3d.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 5, Aufwand 5, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: keine

#### GEO-020 – Konturen nur aus Linien/Bögen, offene Konturen schließen (Toleranz)

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** DXF-Import schließt Lücken und entfernt doppelte Linien; STEP-Konturen kommen exakt aus dem Modell.
- **[Handbuch]** M1 S. 17 (KEEP), S. 33 (Toleranz offene Konturen); LT S. 49–50
- **[Repo]** dxf_import.py (0.9.188)

#### GEO-021 – Bohrungen und Konturen zu nah an Kante/Rundung, Mindeststeg

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Prüfregeln mit Stegen und Abständen, Bohrung auf Rundung, Doppelbohrung.
- **[Handbuch]** M2 S. 42–43
- **[Repo]** dfm.py, Version 0.9.238

#### GEO-022 – Gewindeeinsatz/Einschweißmutter im Rohr

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Im freigegebenen Paket 5 (Thread STEP-Import).
- **[Repo]** Plan Paket 5

#### GEO-023 – Konturen auf der Längsnaht: Lage prüfen und melden

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Prüfregel 'Naht nicht suchbar' und Nahtvorgabe im offenen PR #451.
- **[Repo]** PR #451

### C. Arbeitsgänge und Fertigungszeiten

#### CALC-001 – Zusatzarbeiten mit Zeit, Stundensatz, Material, Zuschlägen, Mindestbetrag, Fremdleistung

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Abrechnung €/kg, €/m², €/m, €/Stück, s/Stück, €/Angebot, €/h; Menge aus Fläche/Bohrungen; Erkennungswörter.
- **[Handbuch]** M1 S. 45–68 (freie Arbeitsgänge)
- **[Repo]** stammdaten.py ZUSATZARBEITEN, rechnen.zusatz_preis

#### CALC-002 – Arbeitsschritte mit Rüstzeit, Zeit je Einheit, Maschine/Personal, parallel

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Rüstzeit je Angebot/Abmessung, Zeit je Teil/Stange/Position.
- **[Handbuch]** M1 S. 46
- **[Repo]** stammdaten.py ARBEITSSCHRITTE, STUNDENSAETZE

#### CALC-003 – Arbeitsgang-Regeln und Vorschläge je Position

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Regeln je Werkstoff/Profil/Kunde, Vorschlag oder automatisch, 'Arbeitsgänge vorschlagen …'.
- **[Handbuch]** M1 S. 79–81
- **[Repo]** arbeitsgaenge.py, zusatz_regeln.py, stammdaten.py ARBEITSGANG_REGELN

#### CALC-004 – Zusatzarbeit mit Formel oder Wertetabelle

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Im offenen PR #452 (G3).
- **[Handbuch]** M1 S. 46–48 (Abkanten mit Formel/Liste)
- **[Repo]** zusatz_formel.py (PR #452)

#### CALC-005 – Rüstzeit je Zusatzarbeit und Los

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Zusatzarbeiten haben Mindestbetrag, aber keine eigene Rüstzeit; Arbeitsschritte haben Rüstzeit nur je Angebot oder Abmessung. Vorschlag: Rüstzeit je Zusatzarbeit (je Angebot, je Position oder je Los) mit Stundensatz, damit Staffelpreise den Rüstanteil richtig verteilen. Leer = wie bisher. Im Bau im Thread zum ArTube-Plan (X1–X8).
- **[Handbuch]** M1 S. 46 („Unterschätzen Sie nicht die Rüstkosten“), S. 27–28, 32
- **[Repo]** stammdaten.py ZUSATZARBEITEN, rechnen.py, staffeln.py

#### CALC-006 – Werkzeugkosten je Arbeitsgang ausweisen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Feld 'Werkzeugkosten je Einheit' (Gewindebohrer, Senker, Reibahle, Düse/Schutzglas je Einstich) getrennt von Zeit und Material. Heute steckt Verschleiß nur im ermittelten Stundensatz (stundensatz.py).
- **[Handbuch]** M1 S. 104 (Stundensatz soll alle Kosten enthalten)
- **[Repo]** stundensatz.py, stammdaten.py ZUSATZARBEITEN
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Niedrig, Einfach, Phase 2; Abhängigkeiten: keine

#### CALC-007 – Lernkurve: Stückzeit sinkt mit der Menge

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Den Serieneffekt gibt es nur bei Schweißbaugruppen (0.9.175). Vorschlag: Faktortabelle je Arbeitsgang (z. B. 1–10 Stk 100 %, 11–50 90 %, >50 80 %), wirkt in Staffeln. Vorgabe leer = 100 %.
- **[Handbuch]** M1 S. 46 (Stückzeit), S. 95 (Staffelpreise)
- **[Repo]** vorkalk.py (Serieneffekt), rechnen.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 7, Aufwand 4, Priorität Mittel, Mittel, Phase 2; Abhängigkeiten: CALC-005

#### CALC-008 – Mengenstaffel je Zusatzarbeit (Fremdleister-Preisliste)

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Verzinken/Pulvern/Strahlen €/kg oder €/m² nach Chargengröße (Staffel ab Menge), wie bei Zukaufteilen schon üblich.
- **[Handbuch]** M1 S. 56, 67, 69
- **[Repo]** zukauf.staffel_wahl (Vorbild), stammdaten.py ZUSATZARBEITEN
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 7, Aufwand 4, Priorität Mittel, Mittel, Phase 2; Abhängigkeiten: keine

#### CALC-009 – Arbeitsplan je Position (Reihenfolge, Liegezeit, Durchlaufzeit)

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Arbeitsgänge je Position und Durchlaufzeiten gibt es; Vorschlag: feste Reihenfolge (Laser → Entgraten → Gewinde → Schweißen → Oberfläche) mit Liege-/Transportzeit, im Werkstattpapier und als Grundlage für den Termin.
- **[Handbuch]** M1 S. 45
- **[Repo]** arbeitsgaenge.py, fertigung.py, terminplan.py
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 5, Aufwand 4, Priorität Mittel, Mittel, Phase 2; Abhängigkeiten: Schnittstelle Auslastung

#### CALC-010 – Sägen als günstigere Alternative zum Laser

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Teile ohne Innenkonturen mit geraden Enden und großem Querschnitt: Säge-Zeit (Stammdaten 'Säge' als Maschine) gegen Laserzeit rechnen und Hinweis zeigen, nie automatisch umstellen.
- **[Handbuch]** M1 S. 49 (Sägen)
- **[Repo]** maschinen_vergleich.py, stammdaten.py MASCHINEN
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 7, Aufwand 4, Priorität Mittel, Mittel, Phase 2; Abhängigkeiten: Säge-Kennwerte von Patrick

#### CALC-011 – Entgraten nach Schnittlänge, maschinell oder von Hand

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** 'Menge aus' kennt Fläche, Gewinde, Bohrungen, Innenkonturen. Vorschlag: zusätzlich 'Schnittlänge' und 'Kantenlänge außen', damit Entgraten/Trovalisieren je m gerechnet werden kann. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Menge je Teil „Schnittlänge [m]“ und „Kantenlänge außen [m]“.
- **[Handbuch]** M1 S. 50–51, 108–109
- **[Repo]** stammdaten.py REGEL_MENGEN

#### CALC-012 – Bolzenschweißen und Einpressen je Element automatisch

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Erkannte Bolzen (abgetrennt beim Aufteilen) bzw. Einpresselemente (PART-006) erzeugen Zusatzarbeit je Stück + Zukaufteil. Heute werden Bolzen nur abgetrennt.
- **[Handbuch]** M1 S. 52–53, 65
- **[Repo]** anbau.py, step.py (Aufteilen trennt Bolzen, 0.9.274)
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 6, Aufwand 4, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: GEO-009, PART-006

#### CALC-013 – Prüfkosten: Erstmusterprüfbericht, Messprotokoll

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Kategorie 'Prüfung' und Prüfplan gibt es; Vorschlag: Kundenvorgabe 'EMPB bei Neuteil' setzt die Zusatzarbeit automatisch bei neuen Artikeln (Wiederholteil = nein). Im Bau im Thread zum ArTube-Plan (X1–X8).
- **[Repo]** pruefplan.py, kundenvorgabe.py, wiederholteile.py, preisschicht.py (Neuteil-Zuschlag)

#### CALC-014 – Rechenweg je Position in Klartext

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Kalkulations-PDF listet Kostenarten; Vorschlag: aufklappbarer Rechenweg je Position wie im PROfirst-Handbuch (Einstiche × Einstechzeit + Längen ÷ Vorschub je Konturklasse + Nebenzeiten; Material = kg × €/kg; Preis = Kosten × Zuschläge) mit den tatsächlich benutzten Werten, als Tooltip und PDF-Anhang. Im Bau im Thread zum ArTube-Plan (X1–X8).
- **[Handbuch]** M1 S. 104–105
- **[Repo]** rechnen.py, pdf.py, klartext.py

#### CALC-015 – Handlingzuschlag nach Teilgewicht/-länge

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Teile über X kg oder Y m (Kran, zwei Personen) bekommen Zeitzuschlag beim Entladen/Sortieren. Die Entladegrenze (PR #451) prüft nur die Machbarkeit.
- **[Handbuch]** M1 S. 27 (Teile entladen)
- **[Repo]** zeit_zusatz.py (PR #451), stammdaten.py ARBEITSSCHRITTE
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Mittel, Einfach, Phase 2; Abhängigkeiten: PR #451

#### CALC-016 – Fremdbearbeitung mit Transport und Lieferzeit

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Fremdleistung = ja kennt nur den Zuschlag. Vorschlag: je Fremdleister Hin-/Rückfracht (Mindestfracht), Zusatzlieferzeit in Tagen; fließt in Preis und Liefertermin.
- **[Handbuch]** M1 S. 69 (Fremdbearbeitungen)
- **[Repo]** stammdaten.py ZUSATZARBEITEN (fremd), fracht.py, terminplan.py
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 7, Aufwand 3, Priorität Mittel, Einfach, Phase 2; Abhängigkeiten: keine

#### CALC-017 – Montagezeit aus Verbindungselementen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Schrauben, Muttern, Nieten der Baugruppe (aus Zukaufteile-Liste PR #450) ergeben Montagezeit je Element (Kennwert je Kategorie/Größe).
- **[Handbuch]** M1 S. 54 (Nieten)
- **[Repo]** zukaufteile.py (PR #450), baugruppe.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 4, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: PR #450, PART-004

#### CALC-018 – Ausschuss nach Regel statt pauschal

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Ausschuss gibt es (0.9.200). Vorschlag: Regel nach Werkstoff/Wand/Toleranz (z. B. Edelstahl ≤ 1,5 mm +2 %), angezeigt im Rechenweg.
- **[Repo]** rechnen.py (ausschuss_hundert)
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 5, Aufwand 3, Priorität Niedrig, Einfach, Phase 2; Abhängigkeiten: keine

#### CALC-019 – Oberfläche: Sperrgut- und Mindestpreis je Teil nach Länge/Gewicht

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Mindestbetrag je Teil gibt es. Vorschlag: Schwellen 'ab Länge > 3 m' oder 'ab Gewicht > 50 kg' mit Zuschlag (Ofen-/Kabinenmaß des Beschichters).
- **[Handbuch]** M1 S. 56 (Pulverbeschichten), S. 67 (Verzinken)
- **[Repo]** zusatz_regeln.py, stammdaten.py ZUSATZARBEITEN
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Mittel, Einfach, Phase 2; Abhängigkeiten: keine

#### CALC-020 – Programmierzeit nach Komplexität

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Programmierkosten sind Pauschale und werden einmal gerechnet (A3). Vorschlag: Grundzeit + Zeit je Kontur/3D-Schnitt/Sonderkontur, Wiederholteil = 0.
- **[Handbuch]** M1 S. 95 (Artikel komplett mit allen Arbeitsgängen)
- **[Repo]** rechnen.py (programmierung_wiederholteil)
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 7, Aufwand 3, Priorität Mittel, Einfach, Phase 2; Abhängigkeiten: keine

#### CALC-021 – Reiben als Standard-Zusatzarbeit je Stück

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Beispiel-Zusatzarbeit 'Reiben' mit € je Stück (gleiche Regel wie Gewinde/Senken/Bohren), Ziel von GEO-010. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Zusatzarbeit Reiben (0,80 € je Bohrung, nur € je Stück).
- **[Handbuch]** M1 S. 68
- **[Repo]** stammdaten.py Beispielwerte

#### CALC-022 – Pulvern, Verzinken, Strahlen nach Fläche/Gewicht inkl. innen

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Menge aus Innen- + Außenfläche, Faktor Gehänge, Abrechnungsregeln.
- **[Handbuch]** M1 S. 56, 67
- **[Repo]** zusatz_regeln.py, Version 0.9.182

#### CALC-023 – Teile nur kalkuliert (nicht schneidfertig) kennzeichnen

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Im offenen PR #452 (I3).
- **[Handbuch]** M1 S. 102
- **[Repo]** PR #452

#### CALC-024 – Folge- und Ausschlussregeln zwischen Zusatzarbeiten

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Regeln wie 'Pulvern ⇒ Strahlen/Entfetten vorschlagen', 'Feuerverzinken ⇒ Gewinde nachschneiden', 'Verzinken + Pulvern = Duplex, Hinweis'. Vorschlag gelb, gerechnet erst nach ✓.
- **[Handbuch]** M1 S. 56, 67
- **[Repo]** zusatz_erkennung.py, zusatz_regeln.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Mittel, Einfach, Phase 2; Abhängigkeiten: GEO-009

#### CALC-025 – Artikelnummer gravieren als Kundenvorgabe

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Vorschlag]** Positionsgravur gibt es für Schweißbaugruppen (0.9.69). Vorschlag: Kundenvorgabe 'jedes Teil mit Artikelnummer gravieren' setzt die Gravur samt Zeit für alle Positionen. Gebaut am 13.11.2026 (Phase 1 Rest): Kundenvorgabe „Artikelnr. gravieren, Schrifthöhe [mm]“; nach dem STEP-Import automatisch, übrige Teile im Angebots-Check mit Erledigen.
- **[Repo]** Version 0.9.69, gravur_text.py, kundenvorgabe.py
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 5, Aufwand 2, Priorität Niedrig, Einfach, Phase 1; Abhängigkeiten: keine

#### CALC-026 – Bündeln und Umreifen je Bund aus dem Packvorschlag

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Verpackungstabelle und Packvorschlag gibt es. Vorschlag: Zeit/Material je Bund (Umreifen, Kantenschutz) aus der Anzahl Bunde des Packvorschlags.
- **[Repo]** stammdaten.py VERPACKUNG, paletten.py, preisschicht.py (G2)
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 5, Aufwand 3, Priorität Niedrig, Einfach, Phase 2; Abhängigkeiten: keine

#### CALC-027 – Kosten je Bohrungsart nebeneinander (Gewinde, Flowdrill, Einnietmutter, Einschweißmutter)

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Bohrungsart lässt sich mit ★-Vorschlägen umschalten (0.9.244). Vorschlag: im Dialog den Preis je Stück jeder Option zeigen; Gewinde/Senken/Flowdrill/Bohren bleiben € je Stück.
- **[Handbuch]** M1 S. 59–61
- **[Repo]** bohrbild_dialog.py, bohrbild.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Mittel, Einfach, Phase 2; Abhängigkeiten: keine

#### CALC-028 – Herkunft und Sicherheit für jeden Rechenwert

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Bericht Entwicklungspotenziale 12.11.2026: Jeder Wert trägt Quelle (STEP gemessen, Stammdaten, Richtwert, gelernt und freigegeben, von Hand, geschätzt) und Sicherheit (sicher, prüfen, unsicher); die Übersicht zeigt den unsicheren Anteil in € und % des Preises. Heute steht die Herkunft nur beim Materialpreis und bei STEP-Merkmalen. Erweitert OFFER-010.
- **[Repo]** step_pruefung.py, rechnen.py Kostenarten
- **Bewertung:** Kundennutzen 9, wirtschaftlicher Nutzen 9, Aufwand 6, Priorität Hoch, Schwierig, Phase 3; Abhängigkeiten: OFFER-010, X1 (ArTube-Plan)

#### CALC-029 – Empfindlichkeit je Annahme

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Bericht Entwicklungspotenziale 12.11.2026: Je Position mit ±10 % auf Vorschub, Materialpreis, Stundensatz, Rüstzeit und Zusatzarbeitszeit neu rechnen und die drei größten Hebel in € zeigen; im Hintergrund, Stangensprünge erkennen.
- **[Repo]** rechnen.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 7, Aufwand 4, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: CALC-028 hilfreich

#### CALC-030 – Kostentreiber über alle Aufträge

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Bericht Entwicklungspotenziale 12.11.2026: Auswertung der beauftragten Angebote je Bearbeitungsart und Abmessung: Zeit, Kosten, Soll-Ist-Abweichung, Top 10, immer mit Anzahl.
- **[Repo]** nachkalkulation.py, kennwerte.py
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 7, Aufwand 4, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: X1 (ArTube-Plan), Nachkalkulation

### D. Zukaufteile und Normteile

#### PART-001 – Zukaufartikel mit Lieferant, EK-Staffel, Mindestmenge, VPE, Preisgültigkeit, Aufschlagsregeln

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Fünf Aufschlagsmethoden (% auf Einstand, € je Einheit, € je Bestellung, Mengenstaffel %, Zielmarge %).
- **[Handbuch]** M1 S. 66
- **[Repo]** zukauf.py, zukauf_seite.py, zukauf_ek.py

#### PART-002 – Normteile aus STEP abtrennen und als Zukauf übernehmen

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Aufteilen trennt Mutter/Bolzen/Schraube ab, Normteil-Preisliste CSV; im PR #450 Kategorie, Norm (nur aus dem Namen), Größe und Vertrauensstufe je Teil.
- **[Handbuch]** M1 S. 66
- **[Repo]** normteil_preise.py, zukaufteile.py (PR #450)

#### PART-003 – Rund-/Vierkantstahl, Dreh-/Frästeile, Bleche als Zukauf

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** EK aus €/kg, Richtpreis Dreh-/Frästeil, Blech-EK je Satz.
- **[Repo]** vollmaterial.py, drehfraes_preis.py, blech_preis.py

#### PART-004 – Normteilbibliothek mit DIN/ISO-Merkmalen

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Statt Freitext-Bezeichnung: Norm, Größe, Länge, Festigkeitsklasse, Oberfläche, Lieferanten-Artikelnummern je Normteil. STEP-Normteile (PR #450) und CSV-Preise werden darüber eindeutig zugeordnet.
- **[Handbuch]** M1 S. 66
- **[Repo]** normteil_preise.normteil_schluessel (heute aus der Bezeichnung), zukaufteile.py (PR #450)
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 7, Aufwand 6, Priorität Hoch, Mittel, Phase 2; Abhängigkeiten: PR #450

#### PART-005 – Normgröße aus der Geometrie vorschlagen

- **Kennzeichnung:** Zunächst technisch zu prüfen
- **[Vorschlag]** PR #450 setzt eine Norm bewusst nur aus dem Namen ('nie erfinden'). Prüfen: Schlüsselweite, Kopfform, Länge, Gewinde-Ø als Kandidaten 'gemessen, ähnlich DIN 933 M8×20' (gelb, nie automatisch). Nutzen hoch bei Dateien ohne Normnamen.
- **[Repo]** zukaufteile.py, step_drehfraes (PR #450)
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 7, Priorität Mittel, Schwierig, Phase 3; Abhängigkeiten: PART-004; Beispieldateien

#### PART-006 – Einpresselemente aus dem Lochbild in Blechen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Loch-Ø passend zur Einpress-Tabelle (z. B. 6,0 für M3/M4-Mutter je Blechdicke) → Vorschlag Einpressmutter/-bolzen + Arbeitsgang Einpressen. Einnietmuttern werden schon aus Sechskantlöchern/Senkungen erkannt.
- **[Handbuch]** M1 S. 65 (Einpressen)
- **[Repo]** zusatz_erkennung.py, bohrbild.py
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 6, Aufwand 4, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: GEO-009, PART-004

#### PART-007 – Lieferzeit der Zukaufteile im Liefertermin

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Zukaufartikel haben ein Feld 'Lieferzeit [Tage]'; im Code wurde keine Verbindung zum Liefertermin des Angebots gefunden. Vorschlag: frühester Termin = max(Zukauf-Lieferzeit) + Fertigung (+ Fremdbearbeitung CALC-016).
- **[Repo]** zukauf.py Feld lieferzeit, angebot_oben.py, terminplan.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Mittel, Einfach, Phase 2; Abhängigkeiten: Schnittstelle Auslastung (Termin prüfen)

#### PART-008 – Lager für Normteile (Kanban, Meldebestand)

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Bestand, Meldebestand und Verbrauch je Auftrag für häufige Schrauben/Muttern; Lager heute nur für Stangen.
- **[Handbuch]** M2 S. 62 (min. Lagerbestand)
- **[Repo]** lager.py
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 5, Aufwand 4, Priorität Niedrig, Mittel, Phase 4; Abhängigkeiten: PR #452 (Meldebestand Stangen) als Vorbild

#### PART-009 – Sammel-Preisanfrage für Zukaufteile ohne Preis

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Normteile ohne Preis lassen sich gesammelt nachtragen; Vorschlag: daraus eine Anfrage-Mail je Lieferant wie die Materialanfrage, Antwort einlesen.
- **[Repo]** normteil_preise.ohne_preis, materialanfrage.py
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Mittel, Einfach, Phase 2; Abhängigkeiten: PART-004

#### PART-010 – Fehlende Verbindungselemente in Baugruppen erkennen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Koaxiale Durchgangsbohrungen zweier Teile ohne Schraube in der STEP → Hinweis 'Schrauben vom Kunden oder anbieten?' mit Vorschlag Größe aus Bohrungs-Ø und Länge aus Klemmlänge (+ Mutter, Scheibe).
- **[Repo]** baugruppe_step.py, zukaufteile.py (PR #450)
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 6, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: PART-004

#### PART-011 – Zukaufteile als eigene Angebotszeilen oder eingerechnet

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Normteile in Baugruppen als Zukauf mit Preis, Stückliste und Einmalkosten wahlweise getrennt.
- **[Handbuch]** M1 S. 66, 97
- **[Repo]** Versionen 0.9.6, 0.9.272

#### PART-012 – Endkappen aus offenen Rohrenden vorschlagen

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Zusatzarbeit 'Endkappen/Stopfen einsetzen' mit Erkennungswörtern gibt es. Vorschlag: Menge = offene Rohrenden (in der Schweißbaugruppe nicht verschweißte Enden) und Endkappe als Zukaufartikel passend zum Profil.
- **[Repo]** stammdaten.py Beispiel-Zusatzarbeiten, baugruppe.py
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 5, Aufwand 3, Priorität Niedrig, Einfach, Phase 3; Abhängigkeiten: PART-004

#### PART-013 – EK-Verlauf je Zukaufartikel

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Preisstände je Bezug mit Datum gibt es; Vorschlag: Verlauf als Liste/Diagramm und Hinweis bei Preissprung > x %.
- **[Repo]** zukauf.py (preis_gueltig, stand)
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 5, Aufwand 3, Priorität Niedrig, Einfach, Phase 2; Abhängigkeiten: MAT-008 (gleiche Darstellung)

### E. Maschinen- und Zeitkalkulation

#### MACH-001 – Maschinenprofile mit Stundensatz, Schneiddaten, Konturklassen, Einstechzeit, Grenzen

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** T03/T11/LT7, Schneiddaten interpoliert mit Herkunft, Gas aus Düse/Druck, Maschinenvergleich je Angebot.
- **[Handbuch]** M1 S. 7, 29–30, 104
- **[Repo]** stammdaten.py MASCHINEN, SCHNEIDDATEN, maschinen_vergleich.py

#### MACH-002 – Dynamik, Drehen je Seitenwechsel, Messzyklen, Lademinimum

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Im offenen PR #451 (ArTube).
- **[Handbuch]** M1 S. 30 (PIERCINGCYCLETIME inkl. Leerwege)
- **[Repo]** dynamik.py, zeit_zusatz.py (PR #451)

#### MACH-003 – Maschinen-, Material- und Personalkosten getrennt

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Kostenarten einzeln in Übersicht, Kalkulation, PDF, CSV; Zeiten nach Maschine und Personal.
- **[Handbuch]** M1 S. 104–105
- **[Repo]** rechnen.py, Version 0.9.34

#### MACH-004 – Vorschub-Abminderung nach Wandbereich

- **Kennzeichnung:** Zunächst technisch zu prüfen
- **[Vorschlag]** PROfirst empfiehlt 80/85/90 % je Dickenbereich. Es gibt den Vorschub-Faktor je Werkstoff, und PR #451 rechnet Dynamik. Prüfen, ob ein Faktor je Wandbereich mit der Dynamik doppelt zählt; nur dann bauen, wenn Ist-Zeiten eine Abweichung je Wand zeigen.
- **[Handbuch]** M1 S. 27, 104
- **[Repo]** stammdaten.py WERKSTOFFE (Vorschub-Faktor), dynamik.py (PR #451)
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 6, Aufwand 2, Priorität Niedrig, Einfach, Phase 4; Abhängigkeiten: MACH-005

#### MACH-005 – Schneiddaten aus Ist-Zeiten kalibrieren

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Kennwerte lernen heute Faktoren (Median Ist ÷ Soll). Vorschlag: mit Ist-Laufzeiten je Teil (Rückmeldung Auslastung, Ist-Zeiten-CSV PR #451) Einstechzeit, Vorschubfaktor je Konturklasse und Nebenzeit je Maschine schätzen (Regression), als Vorschlag mit Referenzangebote-Prüfung vor der Freigabe.
- **[Handbuch]** M1 S. 103 (Nachkalkulation aus CAM)
- **[Repo]** kennwerte.py, istzeiten.py (PR #451), auslastung_austausch.py, referenzangebote.py
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 9, Aufwand 6, Priorität Hoch, Mittel, Phase 4; Abhängigkeiten: genug Ist-Daten; PR #451

#### MACH-006 – Maschine je Position wählen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Maschinenvergleich rechnet das ganze Angebot je Maschine. Vorschlag: Positionen nach Fähigkeit und Kosten auf Maschinen aufteilen (z. B. dicke Rohre T11, kleine LT7), je Maschine eigene Stangenoptimierung.
- **[Handbuch]** M2 S. 47 (Maschine je Auftrag)
- **[Repo]** maschinen_vergleich.py, optimierung.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 8, Aufwand 6, Priorität Mittel, Mittel, Phase 4; Abhängigkeiten: Auslastung (freie Kapazität)

#### MACH-007 – Kapazitätsabhängiger Preishinweis

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Die Belegung der Lieferwoche gibt schon einen Hinweis (über 90 %: kein Nachlass nötig, unter 50 %: Spielraum bis zur Mindestmarge), nie automatisch.
- **[Handbuch]** M1 S. 37 (dynamische Margen)
- **[Repo]** kalk_hinweise.auslastung_punkt

#### MACH-008 – Rüstoptimierte Reihenfolge im Fertigungslos

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Abmessungen im Fertigungslos (PR #451) so sortieren, dass Spannmittel-/Düsenwechsel minimal sind, Ersparnis anzeigen.
- **[Handbuch]** M1 S. 28 (Maschinenrüstkosten je Güte/Stärke)
- **[Repo]** fertigungslos.py (PR #451)
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 6, Aufwand 5, Priorität Niedrig, Mittel, Phase 4; Abhängigkeiten: PR #451

#### MACH-009 – Maschinendaten als Datei austauschen

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Maschine samt Schneiddaten exportieren/importieren (z. B. für einen zweiten Standort oder Test-PC). Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Stammdaten Maschinen: „Maschine speichern/einlesen“ (*.rlmaschine).
- **[Handbuch]** M1 S. 7, 73 (Maschinen-Datenbank importieren)
- **[Repo]** stammdaten.py, export.py

#### MACH-010 – Maschinenstillstände in der Kalkulation

- **Kennzeichnung:** Nicht sinnvoll
- **Begründung** Nicht sinnvoll in der Kalkulation: Stillstände gehören in den Stundensatz bzw. in die Rohrlaser Auslastung (dort gebaut). Doppelt gerechnet würde jedes Angebot zu teuer.
- **[Handbuch]** M1 S. 104
- **[Repo]** stundensatz.py, programm/rl_auslastung

#### MACH-011 – Rüsten je Abmessung/Werkstoff, Profilwechsel, mannlose Laufzeit, Gas, CO₂

- **Kennzeichnung:** Bereits vorhanden
- **[Handbuch]** M1 S. 27–28, 32
- **[Repo]** rechnen.py, preisschicht.py (J3), co2.py

#### MACH-012 – Bandbreite der Laserzeit anzeigen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Aus der Streuung der Kalibrierung (MACH-005) eine Unsicherheit je Position (z. B. ±8 %) zeigen; hilft bei neuen Teilarten und bei der Entscheidung über Risikozuschläge.
- **[Repo]** kennwerte.py
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 5, Aufwand 4, Priorität Niedrig, Mittel, Phase 4; Abhängigkeiten: MACH-005

#### MACH-014 – Schneiddaten mit Quelle und Gültigkeitsbereich

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Bericht Entwicklungspotenziale 12.11.2026: Feld Quelle (Hersteller, eigene Messung, Richtwert) und Datum je Schneiddaten-Zeile; die Rechnung meldet „interpoliert“, „aus Kategorie“ oder „außerhalb der gemessenen Wand“. Alte Zeilen ohne Quelle = unbekannt.
- **[Repo]** rechnen.py _schneiddaten (Rückfall auf Kategorie still)
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 7, Aufwand 3, Priorität Hoch, Einfach, Phase 2; Abhängigkeiten: Schema +1

### F. 3D-Editor und CAD-Verknüpfung

#### CAD-001 – Rohr-/Blech-Editor mit 3D, Konturen und Maßen am Modell

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Gegenrohr, Durchbruch, Lochfeld, Fase, Schrift, Messen, Querschnitt, Kontur-Vorlagen je Kunde, Zurücksetzen auf STEP.
- **[Handbuch]** LT S. 23, 27–30
- **[Repo]** teile_editor.py, editor_griffe.py, blech_dialog.py

#### CAD-002 – 3D-Auswahl Körper/Fläche/Kante/Punkt, Ausschnitt mit Tiefe

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Im offenen PR #450 (Pakete 3 und 4).
- **[Repo]** auswahl3d.py, ausschnitt.py (PR #450)

#### CAD-003 – Rohr auf Rohr ohne STEP mit Schweißspalt

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Freigegeben als K3.
- **[Handbuch]** LT S. 13–15
- **[Repo]** Plan K3

#### CAD-004 – Live-Preis im Editor

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Der Rohr-Editor zeigt Schneidzeit und Konturklassen, der Blech-Editor einen Richtpreis. Vorschlag: Stückpreis und Differenz zum Ausgangsstand laufend anzeigen (Material, Laser, Zusatzarbeiten), auch bei Menge und Staffel. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Kachel „Stückpreis“ im Rohr-Editor mit Differenz zum Öffnen.
- **[Repo]** editor_ergebnis.py, rechnen.py

#### CAD-005 – Kostentreiber im 3D einfärben

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Konturen nach Kostenanteil färben (viele kleine Einstiche, 3D-Schnitte, Gewinde) mit Tooltip '€ je Stück'.
- **[Handbuch]** M1 S. 104 (Einstiche, Konturklassen)
- **[Repo]** ansicht3d.py, rechnen.py
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 6, Aufwand 5, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: CAD-004

#### CAD-006 – Konstruktionsvorschläge mit €-Ersparnis an den Kunden

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Für Knickrahmen, Steckverbindung und Längsnaht gibt es Vorschläge mit Ersparnis. Vorschlag: allgemeine Regeln (Gewinde als Flowdrill, kleine Bohrungen zusammenfassen, Gehrung als gerades Ende + Gegenrohr, Lieferlänge) mit Ersparnis je Stück; die Kontur wird nie automatisch geändert (Grundregel 100 % STEP). Im Bau im Thread zum ArTube-Plan (X1–X8).
- **[Repo]** Version 0.9.111, dfm.py, varianten.py

#### CAD-007 – Kundenvariante neben dem Original

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Im Editor geänderte Geometrie als Variante speichern; das Original bleibt exakt wie STEP; das Angebot zeigt beide Preise ('wie angefragt' / 'Vorschlag'). Im Bau im Thread zum ArTube-Plan (X1–X8).
- **[Repo]** varianten.py, position_kopie.py

#### CAD-008 – Flächen markieren: Sichtfläche, Abkleben, Schweißfläche

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Fläche per 3D-Auswahl (PR #450) als Sichtseite (Wirkung wie 'nicht wenden' PR #452), 'nicht beschichten/abkleben' (Zusatzarbeit Abkleben mit Fläche) oder Schweißfläche markieren.
- **[Handbuch]** M2 S. 91 (nur eine Drehlage für strukturierte Oberflächen)
- **[Repo]** auswahl3d.py (PR #450), wenden (PR #451/#452)
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 5, Aufwand 4, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: PR #450

#### CAD-009 – Arbeitsgänge per Rechtsklick im Editor

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Bohrungsart lässt sich ändern. Vorschlag: Rechtsklick auf Bohrung → Gewinde/Senken/Reiben, auf Kante → Fase/Entgraten, auf Fläche → Gravur/Abkleben; erzeugt die Zusatzarbeit mit Menge, Preis sofort (CAD-004).
- **[Repo]** editor_eigenschaften.py, bohrbild.py, auswahl3d.py (PR #450)
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 7, Aufwand 4, Priorität Hoch, Mittel, Phase 3; Abhängigkeiten: PR #450, GEO-009

#### CAD-010 – Teilefamilien mit Variablen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Teil mit Parametern (Länge L, Lochabstand a, Anzahl n) und Wertetabelle → mehrere Positionen in einem Schritt (z. B. Sprossen in 10 Längen). Bestand: Kontur- und Positionsvorlagen, Rahmen-Assistent.
- **[Handbuch]** M2 S. 21 ('Einfache Teile' mit Maßeingabe)
- **[Repo]** konturvorlagen.py, positionsvorlagen.py, rahmen.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 6, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: keine

#### CAD-011 – Koordinatenliste und 1:1-Abwicklung

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Im offenen PR #452 (I4).
- **[Handbuch]** LT S. 79–83
- **[Repo]** abwicklung_druck.py (PR #452)

#### CAD-012 – Behälterbau, Klöpperboden, Konus-Abwicklungen

- **Kennzeichnung:** Nicht sinnvoll
- **Begründung** Nicht sinnvoll: keine Rohrlaser-Teile, gehören zu Blech-Abwicklungsprogrammen.
- **[Handbuch]** LT S. 30–43, 70–72

#### CAD-013 – Maß einer Kontur ändern, Kalkulation zieht nach

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Konturen und Gehrung am 3D-Modell ziehen, Maße am Modell; die Position rechnet nach dem Übernehmen neu.
- **[Handbuch]** LT S. 28 (Maße ändern, neu berechnen)
- **[Repo]** editor_griffe.py, Version 0.9.66

### G. Baugruppen und Zusammenbau

#### ASM-001 – Sätze und Schweißbaugruppen mit Unterbaugruppen, Nähten, Vor- und Nachkalkulation

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Strukturbaum mit 3D, Stückliste, Vorlagen, Kopieren, Umwandeln Einzelteile ↔ Satz ↔ Schweißbaugruppe.
- **[Handbuch]** M1 S. 97–101; M2 S. 39–41
- **[Repo]** baugruppe.py, baugruppe_dialog.py, vorkalk.py, umwandeln.py

#### ASM-002 – Hauptbauteil der Baugruppe festlegen

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Vorschlag]** Im Code nicht gefunden. Vorschlag: ein Teil als Hauptteil (Bild der Baugruppe, Bezug für Positionieren/Wenden, erste Zeile der Stückliste). Gebaut am 13.11.2026 (Phase 1 Rest): Haken „Hauptteil“ im Baugruppen-Editor (positionen.bg_haupt, höchstens eins); Hauptbauteil zuerst in Stückliste und Angebot.
- **[Handbuch]** M1 S. 97
- **[Repo]** baugruppe.py
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 3, Aufwand 2, Priorität Niedrig, Einfach, Phase 1; Abhängigkeiten: keine

#### ASM-003 – Stückliste exportieren (CSV/Excel)

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Stückliste mit Ebene, Menge, Werkstoff, Gewicht, Zukauf, Artikelnummer als CSV für Kunde/ERP; heute in PDF und Angebots-CSV enthalten. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): CSV-Export „Stückliste je Satz/Baugruppe“.
- **[Handbuch]** M2 S. 47 (DXF vom Auftrag ausgeben)
- **[Repo]** export.py, ausgabe.py

#### ASM-004 – Preis 'nur Teile' und 'geschweißt' nebeneinander

- **Kennzeichnung:** Neu zu entwickeln
- **[Repo]** Gebaut am 13.11.2026 (Phase 2, Paket 2a): Haken „Schweißbaugruppen: Preis lose Einzelteile nennen“ im Angebotskopf; Angebot nennt den Preis ungeschweißt (ausgabe.lose_satzpreis).
- **[Vorschlag]** Option je Schweißbaugruppe: Angebot zeigt zusätzlich den Preis der losen Einzelteile; Kunde wählt.
- **[Handbuch]** M1 S. 97
- **[Repo]** baugruppe.py, angebot_ausgabe.py
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 7, Aufwand 3, Priorität Hoch, Einfach, Phase 2; Abhängigkeiten: keine

#### ASM-005 – Baugruppen-Varianten (mit/ohne Oberfläche, Zukauf)

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Mehrere Ausführungen einer Baugruppe mit Preis nebeneinander, ohne die Baugruppe zu kopieren.
- **[Repo]** varianten.py, baugruppe.py
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 5, Aufwand 4, Priorität Niedrig, Mittel, Phase 3; Abhängigkeiten: ASM-004

#### ASM-006 – Vorrichtungskosten vorschlagen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Einmalkosten für Vorrichtungen werden von Hand eingetragen. Vorschlag: Richtwert nach Anzahl Teile, Größe und Toleranz der Baugruppe, nur als Vorschlag; Wiederholauftrag ohne Vorrichtungskosten.
- **[Repo]** vorkalk.py, baugruppe.py (Einmalbeträge)
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Mittel, Einfach, Phase 3; Abhängigkeiten: Richtwerte von Patrick

#### ASM-007 – Baugruppen kopieren und wiederverwenden

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Baugruppen-Vorlagen, in anderes Angebot kopieren, Positionen aus anderem Angebot übernehmen.
- **[Handbuch]** M1 S. 101
- **[Repo]** Versionen 0.9.28, 0.9.215

#### ASM-008 – Gewicht und Schwerpunkt der Baugruppe für Handling und Verpackung

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Aus den Teilen (bzw. STEP-Volumen) Gesamtgewicht und Schwerpunkt; Hinweis Kran/zwei Personen, Packvorschlag nutzt das Gewicht.
- **[Repo]** baugruppe.py, paletten.py
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 4, Aufwand 3, Priorität Niedrig, Einfach, Phase 3; Abhängigkeiten: keine

### H. Angebot und Preisgestaltung

#### OFFER-001 – Staffeln, Mindestwerte, Gewinnstufen, Fracht, Verpackung, Rabatt, Skonto, Kundenvorgaben

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Dazu Angebotsregeln, Preis-Plausibilität, Referenzangebote, Preis-Simulator, Angebotsvergleich, Nachkalkulation, Wiederholteile, Teilekatalog, Gleitklausel, Abruf/Rahmen.
- **[Handbuch]** M1 S. 22, 33–37, 95–96
- **[Repo]** staffeln.py, preisschicht.py, angebotsregeln.py, plausibel.py, nachkalkulation.py, fracht*.py

#### OFFER-002 – Marge brutto/netto, Kundenhinweis beim Öffnen, Teilebilder, PPS-Skript

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Im offenen PR #452 (G1, G2, G4, G5).
- **[Handbuch]** M1 S. 34, 42, 71
- **[Repo]** ertrag.py, kundenhinweis.py, teilebilder.py, auftrag_skript.py (PR #452)

#### OFFER-003 – Teilbestell-Risiko bei gemeinsam optimierten Positionen

- **Kennzeichnung:** Neu zu entwickeln
- **[Repo]** Gebaut am 13.11.2026 (Phase 2, Paket 2a): teilbestellung.py rechnet jede Position bzw. jeden Satz allein; Hinweis im Angebots-Check ab Einstellung „Teilbestell-Risiko ab [%]“ (Vorgabe 0 = aus), Erledigen setzt den Vorbehalt im PDF.
- **[Vorschlag]** Liegen Positionen gemeinsam auf Stangen, ist der Preis zu niedrig, wenn der Kunde nur einen Teil bestellt. Vorschlag: je Position zusätzlich 'einzeln optimiert' rechnen, Differenz zeigen; ab Schwelle Hinweis im Angebot oder Einzelpreis als Untergrenze (Einstellung).
- **[Handbuch]** M1 S. 82 („Preise sind zu niedrig, wenn nicht alle Teile bestellt werden“)
- **[Repo]** optimierung.py, rechnen.py
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 8, Aufwand 4, Priorität Hoch, Mittel, Phase 2; Abhängigkeiten: keine

#### OFFER-004 – Staffelstufen an Stangensprüngen vorschlagen

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Repo]** Gebaut am 13.11.2026 (Phase 2, Paket 2a): Knopf „Sinnvolle Stufen …“ (stufen_vorschlag.py), Übernahme nur per Haken.
- **[Vorschlag]** Standard-Staffeln gibt es, Staffeln werden nie automatisch angelegt. Vorschlag: Knopf 'Sinnvolle Stufen' zeigt Mengen, an denen sich Stangenzahl/Rüstanteil spürbar ändert (z. B. Rüstanteil < 5 %), Übernahme nur per Klick.
- **[Handbuch]** M1 S. 95
- **[Repo]** staffeln.py, staffel_seite.py
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 7, Aufwand 4, Priorität Hoch, Mittel, Phase 2; Abhängigkeiten: keine

#### OFFER-005 – Preisaufschlüsselung im Kunden-PDF (optional)

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Je Position Material / Bearbeitung / Oberfläche / Zukauf als Spalten im Angebots-PDF, Einstellung je Kunde. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Einstellung „Preisaufteilung je Stück nennen“ (Vorgabe nein).
- **[Handbuch]** M1 S. 24–25 (Ausdruck frei konfigurierbar)
- **[Repo]** pdf.py, angebot_ausgabe.py, kundenvorgabe.py

#### OFFER-006 – Kundenpreisliste exportieren

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Aus dem Teilekatalog je Kunde alle Artikel mit aktuellen Staffelpreisen als PDF/CSV. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Knopf „Kundenpreisliste (CSV)“ im Teilekatalog, ohne interne Spalten.
- **[Handbuch]** M1 S. 37
- **[Repo]** teilekatalog.py

#### OFFER-007 – Rüst- und Programmierkosten als eigene Zeile

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Vorschlag]** Bei Abruf und Baugruppen gibt es Einmalkosten getrennt. Vorschlag: für jedes Angebot wählbar 'Rüsten/Programmierung einmalig ausweisen' statt im Stückpreis. Gebaut am 13.11.2026 (Phase 1 Rest): Haken „Rüsten und Programmierung als eigene Zeile“ im Angebotskopf; Zeile „einmalig je Auftrag“, Stückpreise kleiner, Summe gleich (ausgabe.einmal_abziehen).
- **[Handbuch]** M1 S. 27–28, 32
- **[Repo]** abruf.py, rechnen.py, pdf.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Mittel, Einfach, Phase 1; Abhängigkeiten: keine

#### OFFER-008 – Erklärung bei Preisabweichung zum Wiederholteil

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Repo]** Gebaut am 13.11.2026 (Phase 2, Paket 2a): „Preis erklären …“ bei Wiederholteilen (wiederhol_erklaerung.py), 4 Schritte mit Satz für den Kunden; MAT-008 (Zeitreihe) folgt in Paket 2b.
- **[Vorschlag]** Wiederholteile zeigen den alten Preis. Vorschlag: Abweichung nach Ursache zerlegen (Material ±, Menge, Stundensatz, Zusatzarbeiten), als Satz für den Kunden.
- **[Repo]** wiederholteile.py, fassung_vergleich.py
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 6, Aufwand 4, Priorität Hoch, Mittel, Phase 2; Abhängigkeiten: MAT-008

#### OFFER-009 – Preisband ähnlicher Teile

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Preis-Plausibilität nach Länge und Marktpreis aus Absagen gibt es. Vorschlag: Band (Median, beauftragt/abgelehnt) für Teile mit ähnlichen Merkmalen (GEO-014) neben dem Preis.
- **[Repo]** plausibel.py, absage.py, kalk_hinweise.py
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 7, Aufwand 4, Priorität Mittel, Mittel, Phase 2; Abhängigkeiten: GEO-014

#### OFFER-010 – Risiko-Hinweis bei geschätzten Merkmalen

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Positionen mit gelben/vereinfachten Merkmalen: Hinweis 'Preis unter Vorbehalt der Zeichnungsprüfung' im Angebot oder Risikozuschlag-Vorschlag (Angebotsregel). Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Einstellung „Text bei ungeprüften STEP-Teilen“ (leer = aus).
- **[Handbuch]** M1 S. 102
- **[Repo]** angebot_check.py, angebotsregeln.py, step_pruefung.py

#### OFFER-011 – Zielpreis rückwärts: welche Stellschrauben reichen

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Zielpreis gibt es (0.9.235). Vorschlag: Liste der Hebel mit Wirkung (Menge, Lieferlänge, Oberfläche, Gewinn, Variante) bis zum Zielpreis.
- **[Repo]** kalk_hinweise.py, preis_simulator.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 4, Priorität Mittel, Mittel, Phase 2; Abhängigkeiten: keine

#### OFFER-012 – Kundenwert: Deckungsbeitrag je Kunde und Jahr

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Trefferquote, Ertrag/Laserstunde und Auswertungen gibt es. Vorschlag: Kundenseite mit DB/Jahr, Anfragen, Trefferquote, Reklamationen, Laserstunden.
- **[Repo]** absage.py, monatsbericht.py, einsichten.py
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 7, Aufwand 4, Priorität Mittel, Mittel, Phase 4; Abhängigkeiten: keine

#### OFFER-013 – Rabattstaffel je Kunde nach Jahresumsatz

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Rabattfeld je Angebot und Kundenvorgaben gibt es. Vorschlag: Staffel 'ab Jahresumsatz X → Y %' als Vorschlag.
- **[Handbuch]** M1 S. 37
- **[Repo]** kundenvorgabe.py, angebot.py (rabatt)
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 4, Aufwand 2, Priorität Niedrig, Einfach, Phase 2; Abhängigkeiten: keine

#### OFFER-014 – Hinweis 'Preis gilt bei Bestellung aller Positionen'

- **Kennzeichnung:** Bereits vorhanden
- **[Handbuch]** M1 S. 82
- **[Repo]** Projekt-Memory 12.11. (vorhanden)

#### OFFER-015 – Englisches Angebots-PDF

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Angebot, Auftragsbestätigung und Lieferschein auf Englisch (Texte der Stammdaten mit Übersetzung).
- **[Handbuch]** M2 S. 13 (Übersetzung der Werkstoffnamen)
- **[Repo]** pdf.py, angebot_ausgabe.py
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 5, Aufwand 4, Priorität Mittel, Mittel, Phase 2; Abhängigkeiten: keine

#### OFFER-016 – Drei Liefertermine mit Preis (Express, Standard, flexibel)

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Eilzuschlag gibt es. Vorschlag: im Angebot drei Termine mit Preis nebeneinander, flexibel mit Abschlag, wenn die Auslastung Lücken hat.
- **[Repo]** preisschicht.py, terminplan.py, kalk_hinweise.auslastung_punkt
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 7, Aufwand 3, Priorität Mittel, Einfach, Phase 2; Abhängigkeiten: Schnittstelle Auslastung

#### OFFER-017 – Mindermengenzuschlag sichtbar ausweisen

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Mindestauftragswert und Mindestpreis heben heute den Preis an. Vorschlag: die Anhebung als eigene Zeile 'Mindermengenzuschlag' zeigen, damit der Kunde sieht, ab welcher Menge sie entfällt. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Einstellung „Mindermengenzuschlag als eigene Zeile“ (Vorgabe nein).
- **[Handbuch]** M1 S. 33 (Minimum Angebotspreis)
- **[Repo]** rechnen.py (mindestwert), pdf.py

#### OFFER-018 – Angebotsgültigkeit nach Preisschwankung des Werkstoffs

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Gültigkeitsdauer je Werkstoffkategorie (z. B. Edelstahl 14 Tage, Stahl 30 Tage) als Vorgabe im Angebot. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Einstellung „Gültigkeit je Werkstoff-Kategorie“; die kürzeste gilt.
- **[Handbuch]** M1 S. 34
- **[Repo]** angebot.py, stammdaten.py WERKSTOFFE

#### OFFER-019 – Nachkalkulation und Angebotsvergleich

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Soll/Ist je Kostenart, Auswertung aller Aufträge mit Kennwert-Vorschlägen, zwei Angebote Position für Position.
- **[Handbuch]** M1 S. 103
- **[Repo]** nachkalkulation.py, kennwerte.py, angebotsvergleich.py

#### OFFER-020 – Positionstext aus erkannten Merkmalen

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Angebotstext je Position automatisch aus Merkmalen und Zusatzarbeiten ('4× M8 Gewinde, feuerverzinkt, Gehrung 45°'), änderbar; spart Tipparbeit und macht den Umfang für den Kunden klar. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Einstellung „Bearbeitung aus den Merkmalen nennen“ (Vorgabe nein).
- **[Handbuch]** M1 S. 20 (Artikel-Nr./Artikeltext)
- **[Repo]** angebot_ausgabe.py, bohrbild.py, zusatz_erkennung.py

#### OFFER-021 – Rückfragen nur mit Preiswirkung

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Bericht Entwicklungspotenziale 12.11.2026: Je offenem Punkt den Preis mit beiden Antworten rechnen (z. B. 1.4301 oder 1.4404, mit oder ohne Pulvern); gefragt wird nur ab 3 % Unterschied (Vorgabe), sortiert nach €. Punkte, die sich nicht als Variante rechnen lassen, bleiben ungefiltert.
- **[Repo]** rueckfrage.py
- **Bewertung:** Kundennutzen 8, wirtschaftlicher Nutzen 8, Aufwand 4, Priorität Hoch, Mittel, Phase 2; Abhängigkeiten: CALC-029, GEO-018

#### OFFER-022 – Wettbewerbsabstand je Kategorie im Angebots-Check

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Bericht Entwicklungspotenziale 12.11.2026: Ab 3 Werten Median-Abstand zum Wettbewerb je Werkstoffkategorie und Preisklasse als Hinweis, mit Anzahl und Streuung; der Gewinn ändert sich nie von selbst. Heute stehen Wettbewerbspreise aus Absagen nur als Liste.
- **[Repo]** absage.py, kalk_hinweise.marktpreis
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 2, Priorität Mittel, Einfach, Phase 3; Abhängigkeiten: Absage-Auswertung

### I. CAM, Stangenoptimierung und Fertigungsvorbereitung

#### CAM-001 – Stangenoptimierung mit Nachweis, gemeinsamer Schnitt, Greiferrest, Endbeschnitt

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** FFD/BFD, Schnittmuster nach Gilmore-Gomory, Branch and Bound; Staffel-Schnittschema; im PR #451 Teil am Stangenende, ganze Stange, Teil wenden, Fertigungslos; im PR #452 weniger Muster, Teil in Stangenplänen finden.
- **[Handbuch]** M1 S. 82–88; M2 S. 48–52, 67
- **[Repo]** optimierung.py, stangenende.py, wenden.py, fertigungslos.py

#### CAM-002 – CAM-Paket, Etiketten mit QR, Werkstattpapiere, Laufzettel

- **Kennzeichnung:** Bereits vorhanden
- **[Handbuch]** M2 S. 34–35
- **[Repo]** cam_paket.py, etiketten.py, ausgabe.py

#### CAM-003 – Direkter Export im Format des Rohr-CAM

- **Kennzeichnung:** Zunächst technisch zu prüfen
- **[Vorschlag]** cam_paket.py legt heute STEP + Liste ab ('CAM-Format später'). Prüfen, welches Format das eingesetzte CAM (Adige/ArTube bzw. Trumpf) einliest (Teileliste mit Stückzahl, Werkstoff, Auftrag).
- **[Handbuch]** M1 S. 99–102; M2 S. 46–47
- **[Repo]** cam_paket.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 7, Aufwand 7, Priorität Mittel, Schwierig, Phase 4; Abhängigkeiten: Formatbeschreibung/Beispieldatei des CAM von Patrick

#### CAM-004 – Stangenrückmeldung in die Nachkalkulation

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Stangen melden (PR #452) und Ist-Zeiten (PR #451) übernehmen Ist-Stangen und Ist-Laserzeit automatisch in die Nachkalkulation; heute werden sie dort von Hand eingetragen.
- **[Handbuch]** M1 S. 103
- **[Repo]** nachkalkulation.py, nachkalk_vorbelegen.py, PR #451/#452
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Mittel, Einfach, Phase 4; Abhängigkeiten: PR #451, #452

#### CAM-005 – Materialbündelung über offene Aufträge für den Angebotspreis

- **Kennzeichnung:** Zunächst technisch zu prüfen
- **[Vorschlag]** Läuft dieselbe Abmessung bereits in einem beauftragten Los, kann ein Neuauftrag Verschnitt sparen. Prüfen, ob das für den Preis verlässlich ist (Termine, Stornos); höchstens als Hinweis, ohne Restelager.
- **[Handbuch]** M2 S. 54 (Füllteile)
- **[Repo]** fertigungslos.py (PR #451), fuellteile.py (PR #452)
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 6, Aufwand 6, Priorität Niedrig, Schwierig, Phase 4; Abhängigkeiten: PR #451, #452

#### CAM-006 – Stabile Stangenpläne bei kleinen Mengenänderungen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Ändert sich die Menge nach der Freigabe um wenige Stück, nur die betroffenen Stangen neu planen, damit gedruckte Papiere gültig bleiben.
- **[Handbuch]** M1 S. 88 (Positionsänderungen)
- **[Repo]** optimierung.py, freigabe.py
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 4, Aufwand 5, Priorität Niedrig, Mittel, Phase 4; Abhängigkeiten: keine

#### CAM-007 – Echte Blechverschachtelung statt Hüllrechteck

- **Kennzeichnung:** Zunächst technisch zu prüfen
- **[Vorschlag]** Der Blech-Richtpreis nutzt Hüllrechtecke mit Steg. PROfirst zeigt, dass Rechteck-Verschachtelung teurer rechnet. Nur sinnvoll, wenn Bleche oft selbst gelasert statt zugekauft werden; vorher klären.
- **[Handbuch]** M1 S. 21; M2 S. 48–52
- **[Repo]** blech.py tafelbedarf
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 5, Aufwand 7, Priorität Niedrig, Schwierig, Phase 4; Abhängigkeiten: Klärung: Bleche Zukauf oder Eigenfertigung

#### CAM-008 – Resttafeln, Restgitter, Mehrbrenner, Power-Nesting-Drehschritte

- **Kennzeichnung:** Nicht sinnvoll
- **Begründung** Nicht sinnvoll: Plattenlaser-Themen; Resttafeln widersprechen 'kein Restelager'.
- **[Handbuch]** M2 S. 53–57, 68–74, 89–91

#### CAM-009 – Gemeinsamer Schnitt bei Gehrungen

- **Kennzeichnung:** Nicht sinnvoll
- **Begründung** Nicht sinnvoll: Projektregel 'Gehrungen mit Teileabstand', gegenläufige Gehrungen ohne gemeinsamen Schnitt.
- **[Handbuch]** M2 S. 67, 88 (Sparschnitt)
- **[Repo]** README Optimierung, Projekt-Memory

#### CAM-010 – Mengenvorschlag: 'x Stück mehr passen ohne weitere Stange'

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Ist auf der letzten Stange einer Gruppe noch Platz, zeigt das Angebot 'bis zu x Stück mehr ohne zusätzliches Material' mit dem Stückpreis dieser Menge. Nur Hinweis, keine Staffel automatisch. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): Hinweis im Angebots-Check mit Stückpreis bei der größeren Menge, Probe-Optimierung.
- **[Handbuch]** M1 S. 84 (Nutzlänge)
- **[Repo]** optimierung.py, kalk_hinweise.py

### J. Schnittstellen, Rechte und Organisation

#### ERP-001 – Kunden-Stückliste (Excel/CSV) als Angebot einlesen

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Anfrageformulare (PDF/Scan) und Stückzahlen per Artikelnummer gibt es. Vorschlag: Excel/CSV-Stückliste mit Spaltenzuordnung, die je Kunde gespeichert wird (Artikel, Menge, Werkstoff, Dateiname), STEP-Zuordnung über Dateinamen. Gebaut in PR #453 (Phase 1, Entwurf, wartet auf Patricks Merge): CSV/Excel-Stückliste als Anfrageformular (Stückzahl und Werkstoff je Teil).
- **[Handbuch]** M2 S. 46–47 (Auftrag von PPS einlesen)
- **[Repo]** formular.py, anfragen.py, kunden_csv.py (Spaltenzuordnung als Vorbild)

#### ERP-002 – ERP-Preisimport (#358)

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Offener PR #358, wartet auf Patricks ERP-CSV.
- **[Repo]** PR #358

#### ERP-003 – Rechte nach Rolle (Vertrieb/AV)

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** Admins mit Passwort und Admin-Schutz gibt es. Vorschlag: Rollen 'AV' (Schneiddaten, Maschinen, Arbeitsgänge) und 'Vertrieb' (Angebote, Preise im Angebot), damit Fertigungsdaten nicht im Vertrieb geändert werden.
- **[Handbuch]** M1 S. 39 (Anwenderrechte)
- **[Repo]** admin_schutz.py, kollegen_dialog.py
- **Bewertung:** Kundennutzen 4, wirtschaftlicher Nutzen 5, Aufwand 4, Priorität Niedrig, Mittel, Phase 2; Abhängigkeiten: keine

#### ERP-004 – Übergabe an Buchhaltung (DATEV-CSV, XRechnung)

- **Kennzeichnung:** Zunächst technisch zu prüfen
- **[Vorschlag]** Zielsystem klären (offen seit 25.10.); erst dann Format festlegen.
- **[Handbuch]** M1 S. 33 (Rechnungsnummer)
- **[Repo]** auftrag.py, export.py
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 6, Aufwand 6, Priorität Niedrig, Mittel, Phase 4; Abhängigkeiten: Angabe des Zielsystems von Patrick

#### ERP-005 – Schnittstelle Auslastung, Kunden-CSV, Angebots-CSV, Support-Paket

- **Kennzeichnung:** Bereits vorhanden
- **[Handbuch]** M1 S. 41–42; M2 S. 81; LT S. 74–75
- **[Repo]** auslastung_austausch.py, kunden_csv.py, export.py, support.py

#### ERP-006 – Kundenportal/Webshop

- **Kennzeichnung:** Nicht sinnvoll
- **Begründung** Zurzeit nicht sinnvoll: Server-Synchronisation ist auf Eis; zuerst die Kalkulation selbst ausbauen.
- **[Repo]** Projekt-Memory (Server-Sync Schritte 2–4 auf Eis)

### K. Qualitätssicherung der Kalkulation

#### QA-001 – Rechenweg-Test gegen die Handbuch-Formel

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Test, der die Laserzeit eines Beispielteils einmal nach PROfirst-Formel (Einstiche × (Einstechzeit + Zyklus) + Längen ÷ Vorschub × Faktor) und einmal mit dem Programm rechnet und die Abweichung dokumentiert (nur Bericht, keine Änderung der Rechnung). Im Bau im Thread zum ArTube-Plan (X1–X8).
- **[Handbuch]** M1 S. 104–105
- **[Repo]** tests/, rechnen.py

#### QA-002 – Ende-zu-Ende-Abnahme mit echten STEP-Dateien

- **Kennzeichnung:** Vorhanden, aber verbesserungswürdig
- **[Vorschlag]** tests/test_abnahme.py rechnet 8 Testangebote. Vorschlag: 10–20 echte STEPs + 5 bestätigte Angebote als Abnahme jeder Verknüpfung (Import → Merkmale → Arbeitsgänge → Preis). Stand 12.11.: Wartet auf 10–20 echte STEP-Dateien und 5 bestätigte Angebote von Patrick.
- **[Repo]** tests/test_abnahme.py, referenzangebote.py
- **Bewertung:** Kundennutzen 5, wirtschaftlicher Nutzen 6, Aufwand 3, Priorität Hoch, Einfach, Phase 1; Abhängigkeiten: Dateien von Patrick (C2/D1)

#### QA-003 – Referenzangebote nach jeder Stammdatenänderung prüfen

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Referenzangebote prüft man heute über das Hilfe-Menü. Vorschlag: automatisch nach Änderungen an Schneiddaten, Maschinen, Stundensätzen; Abweichung > x % als Hinweis auf der Startseite. Im Bau im Thread zum ArTube-Plan (X1–X8).
- **[Repo]** referenzangebote.py, preiswaechter.py

#### QA-004 – Support-Datei mit allen Daten eines Falls

- **Kennzeichnung:** Bereits vorhanden
- **[Repo]** Support-Paket (ohne STEP-Dateien) und Fehler im gemeinsamen Ordner.
- **[Handbuch]** LT S. 74–75; M2 S. 82
- **[Repo]** support.py

#### QA-005 – Stammdaten-Prüfung mit FEHLER/WARNUNG

- **Kennzeichnung:** Bereits vorhanden (offener PR bzw. freigegeben, im Bau)
- **[Repo]** Bericht Entwicklungspotenziale 12.11.2026: Prüflauf nach jeder Stammdatenänderung und auf Knopf. FEHLER: Rechnung unmöglich oder sicher falsch (Stundensatz 0, Profil ohne Preis, Vorschub 0, Wandstufe doppelt). WARNUNG: auffällig (Vorschub steigt mit der Wand, Einstechzeit sinkt, €/kg mehr als doppelt so hoch wie bei der Nachbarabmessung, Lücke in den Wandstufen), je Zeile quittierbar. Ändert nichts. Im Bau im Thread zum ArTube-Plan (X1–X8).
- **[Repo]** stammdaten.py pruefen()

#### QA-006 – Regelkatalog aller Prüfungen

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Bericht Entwicklungspotenziale 12.11.2026: Eine Liste aller Prüfregeln (Angebots-Check, Plausibilität, Kalkulationshinweise, DFM, STEP-Prüfung) mit ID, Stufe, Grund und Ort; Warnung und Hinweis einstellbar, FEHLER nicht abschaltbar. Zuerst nur lesen und anzeigen.
- **[Repo]** angebot_check.py, plausibel.py, kalk_hinweise.py, dfm.py, step_pruefung.py
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 6, Aufwand 4, Priorität Hoch, Mittel, Phase 2; Abhängigkeiten: QA-005

### L. KI-Unterstützung

#### KI-001 – Anfrage-Mail auslesen mit Fundstelle

- **Kennzeichnung:** Neu zu entwickeln
- **[Vorschlag]** Bericht Entwicklungspotenziale 12.11.2026: Regelbasierter Leser schlägt Menge, Werkstoff, Oberfläche und Wunschtermin vor; jeder Wert mit zitierter Fundstelle und Sicherheit, Übernahme nur mit Häkchen.
- **[Repo]** mail.py, anfragen.py
- **Bewertung:** Kundennutzen 7, wirtschaftlicher Nutzen 6, Aufwand 5, Priorität Mittel, Mittel, Phase 3; Abhängigkeiten: CALC-028; 10–20 Beispiel-Mails von Patrick

#### KI-002 – Fragen zum Rechenweg beantworten

- **Kennzeichnung:** Zunächst technisch zu prüfen
- **[Vorschlag]** Bericht Entwicklungspotenziale 12.11.2026: „Warum ist Position 3 teurer als Position 2?“ – Architekturfrage; Empfehlung: zuerst regelbasiert aus dem Rechenweg, Antworten nennen nur vorhandene Zahlen. Ein Sprachmodell erst nach Klärung von Datenschutz und Kosten.
- **[Repo]** rechnen.py Kostenarten
- **Bewertung:** Kundennutzen 6, wirtschaftlicher Nutzen 7, Aufwand 7, Priorität Niedrig, Schwierig, Phase 4; Abhängigkeiten: CALC-014, CALC-028

## 5. Neue Funktionsideen

Ideen, die so in keinem der drei Handbücher stehen und aus der Kombination unserer vorhandenen Bausteine entstehen [Vorschlag]:

- **GEO-011 STEP AP242: PMI und Bohrungsmerkmale lesen:** Manche CAD-Systeme schreiben Gewinde, Passungen und Oberflächenangaben als PMI/Feature in AP242. Prüfen, ob OpenCascade (XDE) diese Angaben in den Kundendateien liefert; wenn ja, wären Gewinde/Passungen sicher statt geschätzt. Annahme, nicht geprüft: die meisten Kundendateien sind AP203/AP214 ohne PMI.
- **GEO-016 Flachgedrückte/gequetschte Rohrenden erkennen:** Rohr mit flach gedrücktem Ende (z. B. Streben) wird heute als Sonderform gemeldet. Vorschlag: Merkmal 'Ende gequetscht' mit Zusatzarbeit Quetschen je Ende; Laser schneidet nur das gerade Rohr (gestreckte Länge).
- **GEO-019 Revisionsvergleich der Geometrie:** Neue Revision wird erkannt (0.9.287). Vorschlag: farbiger 3D-Vergleich alt/neu (Konturen hinzu/weg/geändert) und nur die geänderten Merkmale neu prüfen lassen.
- **CALC-018 Ausschuss nach Regel statt pauschal:** Ausschuss gibt es (0.9.200). Vorschlag: Regel nach Werkstoff/Wand/Toleranz (z. B. Edelstahl ≤ 1,5 mm +2 %), angezeigt im Rechenweg.
- **PART-005 Normgröße aus der Geometrie vorschlagen:** PR #450 setzt eine Norm bewusst nur aus dem Namen ('nie erfinden'). Prüfen: Schlüsselweite, Kopfform, Länge, Gewinde-Ø als Kandidaten 'gemessen, ähnlich DIN 933 M8×20' (gelb, nie automatisch). Nutzen hoch bei Dateien ohne Normnamen.
- **PART-007 Lieferzeit der Zukaufteile im Liefertermin:** Zukaufartikel haben ein Feld 'Lieferzeit [Tage]'; im Code wurde keine Verbindung zum Liefertermin des Angebots gefunden. Vorschlag: frühester Termin = max(Zukauf-Lieferzeit) + Fertigung (+ Fremdbearbeitung CALC-016).
- **PART-009 Sammel-Preisanfrage für Zukaufteile ohne Preis:** Normteile ohne Preis lassen sich gesammelt nachtragen; Vorschlag: daraus eine Anfrage-Mail je Lieferant wie die Materialanfrage, Antwort einlesen.
- **PART-010 Fehlende Verbindungselemente in Baugruppen erkennen:** Koaxiale Durchgangsbohrungen zweier Teile ohne Schraube in der STEP → Hinweis 'Schrauben vom Kunden oder anbieten?' mit Vorschlag Größe aus Bohrungs-Ø und Länge aus Klemmlänge (+ Mutter, Scheibe).
- **CAD-009 Arbeitsgänge per Rechtsklick im Editor:** Bohrungsart lässt sich ändern. Vorschlag: Rechtsklick auf Bohrung → Gewinde/Senken/Reiben, auf Kante → Fase/Entgraten, auf Fläche → Gravur/Abkleben; erzeugt die Zusatzarbeit mit Menge, Preis sofort (CAD-004).
- **ASM-005 Baugruppen-Varianten (mit/ohne Oberfläche, Zukauf):** Mehrere Ausführungen einer Baugruppe mit Preis nebeneinander, ohne die Baugruppe zu kopieren.
- **OFFER-008 Erklärung bei Preisabweichung zum Wiederholteil:** Wiederholteile zeigen den alten Preis. Vorschlag: Abweichung nach Ursache zerlegen (Material ±, Menge, Stundensatz, Zusatzarbeiten), als Satz für den Kunden.
- **OFFER-009 Preisband ähnlicher Teile:** Preis-Plausibilität nach Länge und Marktpreis aus Absagen gibt es. Vorschlag: Band (Median, beauftragt/abgelehnt) für Teile mit ähnlichen Merkmalen (GEO-014) neben dem Preis.
- **OFFER-011 Zielpreis rückwärts: welche Stellschrauben reichen:** Zielpreis gibt es (0.9.235). Vorschlag: Liste der Hebel mit Wirkung (Menge, Lieferlänge, Oberfläche, Gewinn, Variante) bis zum Zielpreis.
- **OFFER-012 Kundenwert: Deckungsbeitrag je Kunde und Jahr:** Trefferquote, Ertrag/Laserstunde und Auswertungen gibt es. Vorschlag: Kundenseite mit DB/Jahr, Anfragen, Trefferquote, Reklamationen, Laserstunden.
- **QA-002 Ende-zu-Ende-Abnahme mit echten STEP-Dateien:** tests/test_abnahme.py rechnet 8 Testangebote. Vorschlag: 10–20 echte STEPs + 5 bestätigte Angebote als Abnahme jeder Verknüpfung (Import → Merkmale → Arbeitsgänge → Preis). Stand 12.11.: Wartet auf 10–20 echte STEP-Dateien und 5 bestätigte Angebote von Patrick.
- **MAT-019 Gewicht aus STEP-Volumen gegen gerechnetes Gewicht prüfen:** Weicht das Gewicht aus STEP-Volumen × Dichte deutlich vom Gewicht aus Profil × Länge ab, stimmt oft Wand, Profil oder Werkstoff nicht: Hinweis im Prüfdialog. Versteckter, billiger Fehlerfänger vor dem Preis.
- **CALC-025 Artikelnummer gravieren als Kundenvorgabe:** Positionsgravur gibt es für Schweißbaugruppen (0.9.69). Vorschlag: Kundenvorgabe 'jedes Teil mit Artikelnummer gravieren' setzt die Gravur samt Zeit für alle Positionen. Gebaut am 13.11.2026 (Phase 1 Rest).
- **CALC-026 Bündeln und Umreifen je Bund aus dem Packvorschlag:** Verpackungstabelle und Packvorschlag gibt es. Vorschlag: Zeit/Material je Bund (Umreifen, Kantenschutz) aus der Anzahl Bunde des Packvorschlags.
- **PART-012 Endkappen aus offenen Rohrenden vorschlagen:** Zusatzarbeit 'Endkappen/Stopfen einsetzen' mit Erkennungswörtern gibt es. Vorschlag: Menge = offene Rohrenden (in der Schweißbaugruppe nicht verschweißte Enden) und Endkappe als Zukaufartikel passend zum Profil.
- **ASM-006 Vorrichtungskosten vorschlagen:** Einmalkosten für Vorrichtungen werden von Hand eingetragen. Vorschlag: Richtwert nach Anzahl Teile, Größe und Toleranz der Baugruppe, nur als Vorschlag; Wiederholauftrag ohne Vorrichtungskosten.
- **OFFER-016 Drei Liefertermine mit Preis (Express, Standard, flexibel):** Eilzuschlag gibt es. Vorschlag: im Angebot drei Termine mit Preis nebeneinander, flexibel mit Abschlag, wenn die Auslastung Lücken hat.
- **MACH-012 Bandbreite der Laserzeit anzeigen:** Aus der Streuung der Kalibrierung (MACH-005) eine Unsicherheit je Position (z. B. ±8 %) zeigen; hilft bei neuen Teilarten und bei der Entscheidung über Risikozuschläge.
- **PART-013 EK-Verlauf je Zukaufartikel:** Preisstände je Bezug mit Datum gibt es; Vorschlag: Verlauf als Liste/Diagramm und Hinweis bei Preissprung > x %.
- **ASM-008 Gewicht und Schwerpunkt der Baugruppe für Handling und Verpackung:** Aus den Teilen (bzw. STEP-Volumen) Gesamtgewicht und Schwerpunkt; Hinweis Kran/zwei Personen, Packvorschlag nutzt das Gewicht.
- **CALC-028 Herkunft und Sicherheit für jeden Rechenwert:** Bericht Entwicklungspotenziale 12.11.2026: Jeder Wert trägt Quelle (STEP gemessen, Stammdaten, Richtwert, gelernt und freigegeben, von Hand, geschätzt) und Sicherheit (sicher, prüfen, unsicher); die Übersicht zeigt den unsicheren Anteil in € und % des Preises. Heute steht die Herkunft nur beim Materialpreis und bei STEP-Merkmalen. Erweitert OFFER-010.
- **MACH-014 Schneiddaten mit Quelle und Gültigkeitsbereich:** Bericht Entwicklungspotenziale 12.11.2026: Feld Quelle (Hersteller, eigene Messung, Richtwert) und Datum je Schneiddaten-Zeile; die Rechnung meldet „interpoliert“, „aus Kategorie“ oder „außerhalb der gemessenen Wand“. Alte Zeilen ohne Quelle = unbekannt.
- **QA-006 Regelkatalog aller Prüfungen:** Bericht Entwicklungspotenziale 12.11.2026: Eine Liste aller Prüfregeln (Angebots-Check, Plausibilität, Kalkulationshinweise, DFM, STEP-Prüfung) mit ID, Stufe, Grund und Ort; Warnung und Hinweis einstellbar, FEHLER nicht abschaltbar. Zuerst nur lesen und anzeigen.
- **OFFER-021 Rückfragen nur mit Preiswirkung:** Bericht Entwicklungspotenziale 12.11.2026: Je offenem Punkt den Preis mit beiden Antworten rechnen (z. B. 1.4301 oder 1.4404, mit oder ohne Pulvern); gefragt wird nur ab 3 % Unterschied (Vorgabe), sortiert nach €. Punkte, die sich nicht als Variante rechnen lassen, bleiben ungefiltert.
- **CALC-029 Empfindlichkeit je Annahme:** Bericht Entwicklungspotenziale 12.11.2026: Je Position mit ±10 % auf Vorschub, Materialpreis, Stundensatz, Rüstzeit und Zusatzarbeitszeit neu rechnen und die drei größten Hebel in € zeigen; im Hintergrund, Stangensprünge erkennen.
- **CALC-030 Kostentreiber über alle Aufträge:** Bericht Entwicklungspotenziale 12.11.2026: Auswertung der beauftragten Angebote je Bearbeitungsart und Abmessung: Zeit, Kosten, Soll-Ist-Abweichung, Top 10, immer mit Anzahl.
- **OFFER-022 Wettbewerbsabstand je Kategorie im Angebots-Check:** Bericht Entwicklungspotenziale 12.11.2026: Ab 3 Werten Median-Abstand zum Wettbewerb je Werkstoffkategorie und Preisklasse als Hinweis, mit Anzahl und Streuung; der Gewinn ändert sich nie von selbst. Heute stehen Wettbewerbspreise aus Absagen nur als Liste.
- **KI-001 Anfrage-Mail auslesen mit Fundstelle:** Bericht Entwicklungspotenziale 12.11.2026: Regelbasierter Leser schlägt Menge, Werkstoff, Oberfläche und Wunschtermin vor; jeder Wert mit zitierter Fundstelle und Sicherheit, Übernahme nur mit Häkchen.
- **KI-002 Fragen zum Rechenweg beantworten:** Bericht Entwicklungspotenziale 12.11.2026: „Warum ist Position 3 teurer als Position 2?“ – Architekturfrage; Empfehlung: zuerst regelbasiert aus dem Rechenweg, Antworten nennen nur vorhandene Zahlen. Ein Sprachmodell erst nach Klärung von Datenschutz und Kosten.

Dazu die Ideen, die ein Handbuch nur andeutet und die wir für Rohre deutlich weiter treiben: OFFER-003 (Teilbestell-Risiko, angedeutet in M1 S. 82), CAM-010 und OFFER-004 (Mengenvorschläge aus der Optimierung, angedeutet in M1 S. 84 und S. 95), GEO-009 (Merkmal-Regeln, angedeutet über DXF-Farben in M1 S. 79–81), MACH-005 (Kalibrierung, angedeutet über Nachkalkulation aus CAM in M1 S. 103).

## 6. Intelligente Verknüpfungen

V-01 bis V-05 sind Patricks Beispiele, V-06 bis V-28 sind zusätzliche Verknüpfungen [Vorschlag]. 'Stand' sagt, was davon im Repository schon läuft [Repo].

| Nr. | Kette | Stand | Aufgaben |
|---|---|---|---|
| V-01 | STEP importieren → Geometrie analysieren → Merkmale erkennen → Arbeitsgänge vorschlagen → Zeiten → Angebot | Weitgehend vorhanden (step.py, step_pruefung.py, bohrbild.py, zusatz_erkennung.py, arbeitsgaenge.py, angebot_automatik.py). Lücke: Zuordnung Merkmal → Arbeitsgang ist verteilt. | GEO-009, QA-002 |
| V-02 | Gewindebohrung erkennen → Gewindegröße → Bohren + Gewindeschneiden → Kosten | Vorhanden über Kernloch und ausmodellierte Gewinde, Bestätigung je Bohrung, € je Stück. Ausbau: Gewinde aus Zeichnungstext an die Bohrung binden, Preise der Bohrungsarten vergleichen. | GEO-010, CALC-027, GEO-011 |
| V-03 | Schraube als Zukaufteil erkennen → Normteil zuordnen → EK laden → Marge → Angebotsposition | Erkennen und Einordnen im PR #450, Preis über Normteil-CSV. Lücke: strukturierte DIN/ISO-Bibliothek. | PART-004, PART-005, PART-009 |
| V-04 | Ausschnitt im 3D-Editor ändern → Geometrie neu → Fertigungszeit → Angebotspreis | Ausschnitt mit Tiefe im PR #450; Neurechnung nach dem Übernehmen vorhanden. Ausbau: Preis schon während der Bearbeitung. | CAD-004, CAD-005 |
| V-05 | Baugruppe importieren → Einzelteile → Zukaufteile → Schweiß- und Montageaufwand → Baugruppenpreis | Schweißbaugruppe mit Nähten und Vorkalkulation vorhanden, Zukaufteile im PR #450. Lücke: Montagezeit aus Verbindungselementen, Preis lose/geschweißt. | CALC-017, ASM-004, PART-010 |
| V-06 | Werkstoff in Mail/Zeichnung/STEP → Gleichnamen-Tabelle → Preiszeile → Preisalter-Check → Materialanfrage | Neu verbunden; Einzelteile (Mail-, STEP-Werkstoff, Materialanfrage) gibt es. | MAT-015, MAT-009, MAT-006 |
| V-07 | Lieferantenantwort einlesen → datierter Preis → Preiswächter → offene Angebote mit Δ → Nachfassen | Antwort und Preiswächter vorhanden; neu ist die Zeitreihe und die Begründung im Nachfassen. | MAT-008, OFFER-008 |
| V-08 | Bohrung < 0,7 × Wand → Bohren/Ankörnen statt Laser → Arbeitsgang € je Stück → Werkzeugkosten | Wahl bohren/schneiden vorhanden; neu: Ankörnen und Werkzeugkosten. | GEO-017, CALC-006 |
| V-09 | Fase am Rohrende erkannt → Schweißvorbereitung → a-Maß/Lage der Naht → Schweißzeit | Fase-Zone (PR #450) und Schweißbaugruppe vorhanden; neu ist die Regel Fase → Arbeitsgang. | GEO-012, GEO-009 |
| V-10 | Zeichnungstext 'Ø10 H7' → passende Bohrung → Reiben (€ je Stück) → Prüfplan Messung | Neu. | GEO-010, CALC-021 |
| V-11 | Abgetrennter Bolzen im Blech → Normteil Bolzen + Bolzenschweißen je Stück | Abtrennen vorhanden; Folgeaktion neu. | CALC-012, PART-004 |
| V-12 | Lochbild im Blech passt zu Einpressmutter → Zukauf + Einpressen | Neu (Einnietmuttern gibt es schon). | PART-006, CALC-012 |
| V-13 | Koaxiale Bohrungen ohne Schraube in Baugruppe → Hinweis + Schraubenlänge → Zukauf + Montagezeit | Neu. | PART-010, CALC-017 |
| V-14 | Positionen teilen sich Stangen → Teilbestell-Risiko → Hinweis oder Einzelpreis als Untergrenze | Neu. | OFFER-003 |
| V-15 | Stangenzahl springt bei Menge X → Staffelvorschlag → Klick → Staffel rechnen → Kunden-PDF | Staffeln vorhanden; Vorschlag neu. | OFFER-004, CAM-010 |
| V-16 | Ist-Laufzeit aus Auslastung/CAM → Kalibriervorschlag → Referenzangebote prüfen → Freigabe | Ist-Daten fließen (Schnittstelle, PR #451); Kalibrierung neu. | MACH-005, QA-003 |
| V-17 | Neue Revision erkannt → 3D-Vergleich → nur Geändertes prüfen → Preisdifferenz erklärt | Revision erkannt; Vergleich und Erklärung neu. | GEO-019, OFFER-008 |
| V-18 | Wiederholteil → Preis anders als letztes Mal → Ursachen (Material, Menge, Sätze) → Satz für den Kunden | Wiederholteil vorhanden; Ursachenzerlegung neu. | OFFER-008, MAT-008 |
| V-19 | Spiegelteile erkannt → Programmierung einmal → Hinweis 'links/rechts' im Angebot | Neu (Programmierung einmal für gleiche Teile gibt es). | GEO-013, CALC-020 |
| V-20 | Oberfläche gewünscht → vorverzinktes Material gegen Feuerverzinken → Preis + Lieferzeit | Neu. | MAT-014, CALC-016 |
| V-21 | Schweres/langes Teil → Handlingzuschlag → Personalzeit in Auslastung | Entladegrenze im PR #451; Zuschlag neu. | CALC-015, MAT-021 |
| V-22 | Gelbe Merkmale → Risiko-Hinweis im Angebot → Rückfrage-Mail → Antwort → grün → endgültiger Preis | Rückfrage und Prüfstatus vorhanden; Verbindung neu. | OFFER-010, GEO-018 |
| V-23 | Kunden-Stückliste (Excel) → Positionen + STEP-Zuordnung → Messung → Angebot | Formular/OCR vorhanden; Excel-Stückliste neu. | ERP-001 |
| V-24 | Rechtsklick auf Bohrung im Editor → Gewinde → Zusatzarbeit → Preis sofort | Bohrungsart ändern vorhanden; Rechtsklick-Arbeitsgänge und Live-Preis neu. | CAD-009, CAD-004 |
| V-25 | Zukauf-Lieferzeit + Fremdbearbeitung → frühester Liefertermin → Termin prüfen in der Auslastung | Termin aus Auslastung vorhanden (0.9.293); Zukauf/Fremd fehlen. | PART-007, CALC-016 |
| V-26 | Beauftragt → Sammelbedarf der Woche → Mindestabnahme je Bund → eine Anfrage je Lieferant | Neu (Fertigungslos aus PR #451 als Grundlage). | MAT-018, MAT-013 |
| V-27 | Kostentreiber im 3D → Konstruktionsvorschlag → Kundenvariante → zwei Preise im Angebot | Neu (Vorschläge mit Ersparnis gibt es für Knickrahmen/Steckverbindung). | CAD-005, CAD-006, CAD-007 |
| V-28 | Zusatzarbeit Pulvern gewählt → Folgeregel Strahlen/Entfetten → Sperrgut-Regel nach Länge → Preis | Neu (Abrechnungsregeln gibt es). | CALC-024, CALC-019 |

## 7. Technische Voraussetzungen

- **Merkmal-Modell vereinheitlichen (für GEO-009):** heute liegen Merkmale in `bohrbild` (JSON je Position), Konturliste `konturen`, Prüfstatus `step_pruefung` und Erkennungswörtern. Eine Regeltabelle braucht eine gemeinsame Sicht 'Merkmal (Art, Maße, Lage, Herkunft, Status)' – lesend über die vorhandenen Daten, ohne Umbau der Speicherung.
- **Schema-Erweiterungen** (nur neue Spalten/Tabellen, leer = wie bisher): datierte Preise (MAT-008), Rüstzeit je Zusatzarbeit (CALC-005), Werkzeugkosten (CALC-006), Normteil-Merkmale (PART-004), Rollen (ERP-003). Jede Erweiterung mit Sicherung vor der Umstellung (vorhanden) und Test der Anpassung alter Dateien.
- **Rechenkern ohne Qt:** Live-Preis (CAD-004) braucht eine schnelle Einzelpositions-Rechnung ohne komplette Neuoptimierung; Teilbestell-Risiko (OFFER-003) braucht eine Optimierung je Position (Rechenzeit messen, ggf. Hilfsprozesse wie bei großen Angeboten).
- **Ist-Daten** für MACH-005: Rückmeldung der Auslastung (vorhanden), Ist-Zeiten-CSV (PR #451). Vor einer Kalibrierung mindestens etwa 30 Aufträge je Maschine sammeln (Annahme, im Plan zu prüfen).
- **Beispieldateien von Patrick:** ERP-/Lieferanten-CSV (MAT-010, #358), Kunden-Stückliste (ERP-001), CAM-Format (CAM-003), STEP mit Biegeteilen und gequetschten Enden (GEO-015, GEO-016), AP242-Dateien (GEO-011).
- **Tests:** jede Aufgabe mit eigenem Test in `tests/alle.py`; Rechenänderungen zusätzlich gegen die Abnahme (`tests/test_abnahme.py`) und Referenzangebote, damit alte Preise unverändert bleiben, solange die neue Einstellung leer ist.
- **Anleitung:** jede Funktion braucht einen Abschnitt in der Bedienungsanleitung (Build-Prüfung vorhanden).

## 8. Wirtschaftlicher Nutzen

Einschätzung [Vorschlag], ohne gemessene Zahlen; zu belegen mit Nachkalkulation und Referenzangeboten nach dem Bau.

- **Preise nicht zu niedrig:** OFFER-003 (Teilbestellung), CALC-005 (Rüsten je Zusatzarbeit), MAT-009 (alte Materialpreise), CALC-016 (Transport zum Fremdleister), OFFER-010 (Risiko bei Schätzwerten). Diese Punkte verhindern Verlustaufträge, die heute unbemerkt bleiben können.
- **Mehr Aufträge gewinnen:** OFFER-004/CAM-010 (Mengenvorschläge), ASM-004 (lose/geschweißt), OFFER-016 (drei Termine), CAD-006/CAD-007 (Konstruktionsvorschläge mit Ersparnis), OFFER-008 (Preis erklärt).
- **Zeit sparen bei der Angebotserstellung:** ERP-001 (Stückliste), MAT-010 (Preisliste), GEO-009/CAD-009 (Arbeitsgänge automatisch bzw. per Klick), OFFER-020 (Positionstext), GEO-018 (Rückfrage per Klick).
- **Genauere Kosten:** MACH-005 (Kalibrierung), CALC-007 (Lernkurve), CALC-020 (Programmierzeit), CALC-006 (Werkzeugkosten).
- **Einkauf:** MAT-013/MAT-018 (Bund, Sammelbedarf), PART-009 (Sammelanfrage Zukauf).

## 9. Priorisierung

### Phase 1 – Schnelle Verbesserungen (7 Aufgaben)

Stand 12.11.2026: 16 Aufgaben der Phase 1 sind in PR #453 gebaut (MAT-009, OFFER-017, OFFER-018, OFFER-010, CAM-010, CAD-004, GEO-018, OFFER-020, ERP-001, OFFER-006, ASM-003, OFFER-005, MACH-009, CALC-011, CALC-021, MAT-015), GEO-017 und MAT-020 gibt es schon, CALC-013, CALC-014, QA-001 und QA-003 baut der ArTube-Plan. Die übrigen warten auf den Merge des ArTube-Plans (Rechenkern, Schema) bzw. auf Unterlagen von Patrick:

Hohe Priorität: **MAT-010** Materialpreislisten importieren (Rohre/Profile), **QA-002** Ende-zu-Ende-Abnahme mit echten STEP-Dateien.

Stand 13.11.2026: PR #453 ist als 0.9.297 gemergt. Die fünf zurückgestellten Aufgaben OFFER-007, MAT-011, CALC-025, MAT-016 und ASM-002 sind nach dem Merge des ArTube-Plans gebaut (Phase 1 Rest, Schema 85). Offen bleiben MAT-010 und QA-002.

### Phase 2 – Erweiterung der Kalkulation (37 Aufgaben)

Hohe Priorität: **OFFER-021** Rückfragen nur mit Preiswirkung, **GEO-009** Zentrale Merkmal-Regeln: jedes Merkmal → Arbeitsgang/Zusatzarbeit/Prüfregel, **OFFER-003** Teilbestell-Risiko bei gemeinsam optimierten Positionen, **ASM-004** Preis 'nur Teile' und 'geschweißt' nebeneinander, **MACH-014** Schneiddaten mit Quelle und Gültigkeitsbereich, **OFFER-004** Staffelstufen an Stangensprüngen vorschlagen, **PART-004** Normteilbibliothek mit DIN/ISO-Merkmalen, **OFFER-008** Erklärung bei Preisabweichung zum Wiederholteil, **QA-006** Regelkatalog aller Prüfungen.

Weitere: OFFER-009 Preisband ähnlicher Teile, MAT-008 Materialpreis als Zeitreihe statt Überschreiben, OFFER-016 Drei Liefertermine mit Preis (Express, Standard, flexibel), CALC-007 Lernkurve: Stückzeit sinkt mit der Menge, CALC-010 Sägen als günstigere Alternative zum Laser, MAT-013 Mindestabnahme je Abmessung (Bund, Mindestmenge des Lieferanten), CALC-016 Fremdbearbeitung mit Transport und Lieferzeit, CALC-020 Programmierzeit nach Komplexität, PART-007 Lieferzeit der Zukaufteile im Liefertermin, CALC-024 Folge- und Ausschlussregeln zwischen Zusatzarbeiten, CALC-027 Kosten je Bohrungsart nebeneinander (Gewinde, Flowdrill, Einnietmutter, Einschweißmutter), MAT-012 Materialindex/Legierungszuschlag je Monat, MAT-014 Vorverzinkt/vorbeschichtet kaufen oder nachträglich veredeln, CALC-008 Mengenstaffel je Zusatzarbeit (Fremdleister-Preisliste), OFFER-011 Zielpreis rückwärts: welche Stellschrauben reichen, CALC-019 Oberfläche: Sperrgut- und Mindestpreis je Teil nach Länge/Gewicht, PART-009 Sammel-Preisanfrage für Zukaufteile ohne Preis, MAT-019 Gewicht aus STEP-Volumen gegen gerechnetes Gewicht prüfen, CALC-015 Handlingzuschlag nach Teilgewicht/-länge, CALC-009 Arbeitsplan je Position (Reihenfolge, Liegezeit, Durchlaufzeit), OFFER-015 Englisches Angebots-PDF, CALC-006 Werkzeugkosten je Arbeitsgang ausweisen, MAT-021 Stangenwechsel-Zeit nach Stangengewicht, CALC-018 Ausschuss nach Regel statt pauschal, CALC-026 Bündeln und Umreifen je Bund aus dem Packvorschlag, PART-013 EK-Verlauf je Zukaufartikel, OFFER-013 Rabattstaffel je Kunde nach Jahresumsatz, ERP-003 Rechte nach Rolle (Vertrieb/AV).

### Phase 3 – Intelligente CAD-Verknüpfung (26 Aufgaben)

Hohe Priorität: **CALC-028** Herkunft und Sicherheit für jeden Rechenwert, **CAD-009** Arbeitsgänge per Rechtsklick im Editor.

Weitere: CALC-030 Kostentreiber über alle Aufträge, GEO-010 Passungen und Toleranzen aus der Zeichnung an die Bohrung binden, CALC-029 Empfindlichkeit je Annahme, OFFER-022 Wettbewerbsabstand je Kategorie im Angebots-Check, GEO-012 Schweißvorbereitung (Fasen) als Arbeitsgang, GEO-014 Ähnliche Teile trotz anderer Artikelnummer finden, CAD-005 Kostentreiber im 3D einfärben, KI-001 Anfrage-Mail auslesen mit Fundstelle, CALC-017 Montagezeit aus Verbindungselementen, ASM-006 Vorrichtungskosten vorschlagen, CALC-012 Bolzenschweißen und Einpressen je Element automatisch, PART-006 Einpresselemente aus dem Lochbild in Blechen, PART-010 Fehlende Verbindungselemente in Baugruppen erkennen, CAD-010 Teilefamilien mit Variablen, GEO-019 Revisionsvergleich der Geometrie, PART-005 Normgröße aus der Geometrie vorschlagen, GEO-013 Spiegelteile (links/rechts) erkennen, CAD-008 Flächen markieren: Sichtfläche, Abkleben, Schweißfläche, GEO-011 STEP AP242: PMI und Bohrungsmerkmale lesen, PART-012 Endkappen aus offenen Rohrenden vorschlagen, GEO-015 Biegerohre aus der STEP messen, ASM-005 Baugruppen-Varianten (mit/ohne Oberfläche, Zukauf), GEO-016 Flachgedrückte/gequetschte Rohrenden erkennen, ASM-008 Gewicht und Schwerpunkt der Baugruppe für Handling und Verpackung.

### Phase 4 – Professionelle Fertigungsintegration (15 Aufgaben)

Hohe Priorität: **MACH-005** Schneiddaten aus Ist-Zeiten kalibrieren.

Weitere: MAT-018 Wöchentlicher Sammelbedarf über beauftragte Aufträge, MACH-006 Maschine je Position wählen, OFFER-012 Kundenwert: Deckungsbeitrag je Kunde und Jahr, CAM-003 Direkter Export im Format des Rohr-CAM, CAM-004 Stangenrückmeldung in die Nachkalkulation, KI-002 Fragen zum Rechenweg beantworten, MACH-004 Vorschub-Abminderung nach Wandbereich, CAM-005 Materialbündelung über offene Aufträge für den Angebotspreis, ERP-004 Übergabe an Buchhaltung (DATEV-CSV, XRechnung), MACH-008 Rüstoptimierte Reihenfolge im Fertigungslos, PART-008 Lager für Normteile (Kanban, Meldebestand), MACH-012 Bandbreite der Laserzeit anzeigen, CAM-006 Stabile Stangenpläne bei kleinen Mengenänderungen, CAM-007 Echte Blechverschachtelung statt Hüllrechteck.

## 10. Abhängigkeiten

- **Offene PRs zuerst mergen:** #450 (Zukaufteile, 3D-Auswahl, Ausschnitt), #451 (Dynamik, Ist-Zeiten, Fertigungslos), #452 (Ertrag, Formel-Zusatzarbeiten, Meldebestand, Stangen melden). Viele Aufgaben bauen darauf auf (PART-004/005/010, CAD-008/009, MACH-005, MAT-018, CAM-004). Kein Bau parallel auf denselben Dateien, solange diese PRs offen sind (Regel 22.10.: zurückstellen bis laufender Merge fertig).
- **GEO-009 Merkmal-Regeln** → GEO-010, GEO-012, CALC-012, CALC-024, PART-006, CAD-009.
- **PART-004 Normteilbibliothek** → PART-005, PART-006, PART-009, PART-010, PART-012, CALC-017.
- **MAT-008 Preis-Zeitreihe** → MAT-012, OFFER-008, PART-013; MAT-010 profitiert davon.
- **CAD-004 Live-Preis** → CAD-005, CAD-006, CAD-007.
- **CALC-005 Rüstzeit je Zusatzarbeit** → CALC-007 (Lernkurve in Staffeln).
- **MACH-005 Kalibrierung** → MACH-004, MACH-012; braucht Ist-Daten (Schnittstelle Auslastung, PR #451).
- **GEO-014 Ähnliche Teile** → OFFER-009.
- **Schnittstelle Auslastung** → CALC-009, PART-007, OFFER-016, MACH-006.
- **Daten von Patrick** → MAT-010 (#358), ERP-001, CAM-003, ERP-004, GEO-011, GEO-015, GEO-016, QA-002, ASM-006.

## 11. Risiken

| Risiko | Wirkung | Gegenmaßnahme |
|---|---|---|
| Neue Rechenbausteine ändern Preise offener Angebote | Kunden bekommen andere Preise als zugesagt | Jede Neuerung mit Vorgabe 'leer = wie bisher', Preisbasis festgeschrieben, Referenzangebote und Abnahme vor dem Merge (wie bei H1 im PR #452) |
| Automatische Erkennung irrt (Gewinde, Normteil, Passung) | falscher Preis oder falsches Teil | Immer gelb als Vorschlag, gerechnet erst nach ✓; Norm nie erfinden (wie PR #450); Lernen aus ✓/✗ |
| Geometrie wird verändert | Verstoß gegen Grundregel 100 % STEP | Konstruktionsvorschläge nur als Variante neben dem Original (CAD-007), Export unverändert |
| Konflikte mit offenen PRs | Mehrarbeit, Fehler beim Zusammenführen | Erst #450/#451/#452 mergen, dann bauen; kleine PRs je Aufgabe |
| Kalibrierung mit zu wenigen Ist-Daten | Zeiten werden schlechter statt besser | Mindestanzahl Fälle, Ausreißer ausschließen (wie kennwerte.py), nur Vorschlag mit Freigabe |
| Rechenzeit (Live-Preis, Optimierung je Position) | träge Oberfläche | Messung im Tempo-Protokoll, Rechnen im Hintergrund, Zwischenspeicher |
| Funktionsfülle überfordert Anwender | weniger Nutzung | Funktionen einzeln schaltbar (Einstellungen 'Funktionen ein/aus' gibt es), Vorgaben aus |
| Fehlende Beispieldaten | Aufgaben bleiben liegen | Datenbedarf früh anfragen (Kapitel 10) |
| Rechtliches/Markennamen | Nachbau fremder Software | Keine Kopie von PROfirst/LogiTRACE: nur Rechenwege und Arbeitsweisen als Anregung, eigene Umsetzung |

## 12. Konkrete Umsetzungsempfehlungen

### 12.1 Reihenfolge

- **Schritt 0:** offene PRs #450, #451, #452 fertigstellen und mergen (Sammel-Update), #358 mit ERP-CSV abschließen.
- **Schritt 1 (Phase 1, ein Sammel-PR, geringe Risiken):** MAT-009, CALC-014, OFFER-010, CAM-010, CAD-004, ERP-001, OFFER-007, OFFER-017, GEO-018, QA-002/QA-003, dazu die kleinen Punkte der Phase 1.
- **Schritt 2 (Phase 2):** GEO-009 als Fundament, danach CALC-005, OFFER-003, OFFER-004, PART-004, MAT-008/MAT-010, ASM-004, CALC-010, CALC-016.
- **Schritt 3 (Phase 3):** CAD-009, CAD-006/CAD-007, GEO-010, GEO-012, PART-006, PART-010, CALC-017, GEO-014.
- **Schritt 4 (Phase 4):** MACH-005 (sobald genug Ist-Daten), MAT-018, MACH-006, CAM-003 (nach Klärung Format), CAM-004.

### 12.2 Arbeitsweise je Aufgabe

- Vor dem Bau: Fragen klären und einen Plan mit 2–4 Schritten zur Freigabe vorlegen (Projektregel).
- Neue Einstellung immer mit Vorgabe 'aus' bzw. 'leer = wie bisher'; Preise offener Angebote ändern sich nicht.
- Test je Aufgabe in `tests/alle.py`, Abnahme und Referenzangebote unverändert, ruff sauber.
- Bedienungsanleitung anpassen, Vorher-Nachher-Bilder liefern, Version main+1 direkt vor dem Merge.
- Schritte aus einem Editor in alle Editoren übernehmen.

### 12.3 Empfehlung: die 10 Erweiterungen mit dem größten Nutzen

| Rang | ID | Erweiterung | Begründung |
|---|---|---|---|
| 1 | GEO-009 | Zentrale Merkmal-Regeln | Rückgrat fast aller Verknüpfungen: jedes erkannte Merkmal führt nachvollziehbar zu Arbeitsgang, Zusatzarbeit oder Prüfregel. Macht viele spätere Punkte (GEO-010, GEO-012, CALC-012, CALC-024, PART-006, CAD-009) zu kleinen Regel-Einträgen statt eigener Programmteile. |
| 2 | OFFER-003 | Teilbestell-Risiko bei gemeinsam optimierten Positionen | Schützt direkt vor zu niedrigen Preisen, wenn der Kunde nur einen Teil bestellt. PROfirst warnt davor ausdrücklich (M1 S. 82); unser Programm optimiert immer gemeinsam. |
| 3 | CAD-004 | Live-Preis im Editor | Jede Änderung im 3D-Editor zeigt sofort ihre Wirkung in €. Grundlage für Konstruktionsberatung (CAD-005, CAD-006, CAD-007) und für das Beispiel 'Ausschnitt ändern → Preis aktualisiert'. |
| 4 | CALC-005 | Rüstzeit je Zusatzarbeit und Los | Rüstkosten sind laut PROfirst der häufigste Grund für Verluste bei kleinen Mengen (M1 S. 46). Heute haben Zusatzarbeiten nur einen Mindestbetrag; Staffelpreise verteilen Rüsten daher nicht genau. |
| 5 | MAT-009 + MAT-010 | Preisalter-Warnung und Preislisten-Import | Materialpreise sind der größte Kostenblock. Eine Warnung bei alten Preisen kostet wenig Aufwand; der Import (mit PR #358) erspart das Abtippen ganzer Lieferantenlisten. |
| 6 | OFFER-004 + CAM-010 | Staffelstufen an Stangensprüngen und 'x Stück mehr passen' | Nutzt die vorhandene, sehr gute Optimierung für den Verkauf: der Kunde sieht, ab welcher Menge es günstiger wird, und bekommt Mehrmengen ohne zusätzliches Material angeboten. Staffeln bleiben ein Klick (nie automatisch). |
| 7 | ERP-001 | Kunden-Stückliste (Excel/CSV) einlesen | Viele Anfragen kommen als Liste. Mit gemerkter Spaltenzuordnung je Kunde wird aus der Liste plus STEP-Dateien in einem Schritt ein Angebot. |
| 8 | PART-004 | Normteilbibliothek mit DIN/ISO-Merkmalen | Macht die im PR #450 erkannten Zukaufteile eindeutig zuordenbar (Preis, Lieferant, Montagezeit) und ist Voraussetzung für PART-006, PART-010, CALC-017. |
| 9 | MACH-005 | Schneiddaten aus Ist-Zeiten kalibrieren | Die Schnittstelle zur Auslastung und die Ist-Zeiten aus PR #451 liefern Daten; daraus werden Laserzeiten belegbar genauer. Größter Hebel auf die Treffsicherheit aller Preise, sobald genug Ist-Daten da sind. |
| 10 | CAD-009 + CAD-006 | Arbeitsgänge per Rechtsklick und Konstruktionsvorschläge mit Ersparnis | Verbindet 3D-Editor und Kalkulation in beide Richtungen und hebt das Programm von reinen Angebotsprogrammen ab. Die Kontur wird nie automatisch geändert (Grundregel 100 % STEP). |

Die Auswahl berücksichtigt, was schon vorhanden ist: viele naheliegende Punkte aus den Handbüchern (Staffeln, Fracht, Baugruppen, Mindestpreise, Arbeitsgänge) sind bereits gebaut oder in den offenen PRs. Die Top 10 schließen deshalb vor allem Lücken bei Preissicherheit, Rüstkosten und der Verbindung zwischen CAD-Daten, Editor und Angebot.

