# Rohrlaser Angebotskalkulation

Eigenständiges Windows-Programm zur Angebotskalkulation und Materialoptimierung von Rohrlaserteilen:
Angebote erfassen (von Hand oder per STEP-Import), Teile auf möglichst wenige Stangen verteilen,
Kosten je Kostenart kalkulieren, Staffelpreise rechnen und Angebot, Werkstattpapiere und Kalkulation
als PDF ausgeben. Zum Installieren (ohne Administratorrechte) oder portabel ohne Installation.

## Installation oder portabel

Beide Formen kommen aus demselben Build und enthalten dieselben Programmdateien (der Build prüft die Prüfsummen und vergleicht die Rechenergebnisse); sie unterscheiden sich nur im Datenort (`programm/rohrlaser/orte.py`):

| | Installation | Portabel |
|---|---|---|
| Release „aktuell“ | `Rohrlaser-Angebotskalkulation-Setup.exe` (Inno Setup, `programm/installer/rohrlaser.iss`) | `Rohrlaser-Angebotskalkulation.zip` |
| Programm | `%LOCALAPPDATA%\Programs\Rohrlaser Angebotskalkulation` (nur für den Benutzer, keine Adminrechte) | beliebiger beschreibbarer Ordner |
| Daten | `%LOCALAPPDATA%\Rohrlaser Angebotskalkulation\Daten` | `Daten` neben der .exe (`Portabel.ini` im ZIP; ältere ZIP-Stände am vorhandenen Ordner `Daten` erkannt) |
| PDF/CSV | `Dokumente\Rohrlaser Angebote` | `Angebote` neben der .exe |
| Deinstallieren | entfernt nur Programmdateien, Daten bleiben | Ordner löschen |

Das Online-Update funktioniert in beiden gleich (der Programmordner ist beschreibbar). Umziehen: **Datei → Daten exportieren …** / **Daten importieren …** oder beim ersten Start „Daten übernehmen …“. Solange das Programm läuft, sperrt es die Datendatei (`rohrlaser.db.sperre`), damit nie zwei Programme gleichzeitig damit arbeiten.

## Benutzung

1. Unter **Releases → aktuell** `Rohrlaser-Angebotskalkulation-Setup.exe` herunterladen und starten, oder `Rohrlaser-Angebotskalkulation.zip` in einen Ordner entpacken, in dem man schreiben darf (z. B. `C:\Rohrlaser`, nicht `C:\Programme`).
2. Programm starten (Startmenü bzw. `Rohrlaser-Angebotskalkulation.exe`). Beim ersten Start fragt es, ob vorhandene Daten übernommen werden sollen; sonst legt es `rohrlaser.db` (Stammdaten, Einstellungen, Angebote) mit Beispiel-Stammdaten an.
3. Die Beispielwerte in den Stammdaten-Reitern (Kunden, Profile, Werkstoffe, Preise, Maschinen, Schneiddaten, Gewinde, Zusatzarbeiten) und in den Einstellungen (Zuschläge, Briefkopf, Nummernkreis) durch die eigenen ersetzen. Jede Änderung wird sofort gespeichert; die Spalte **Prüfung** zeigt OK, WARNUNG oder FEHLER.
4. Reiter **Angebote**: neues Angebot anlegen (Nummer zählt hoch), kopieren (auch für einen anderen Kunden), löschen, suchen (auch nach Artikel). Doppelklick öffnet das Angebot in einem eigenen Reiter.
5. Im Angebot: Kopf oben, Positionen darunter. **STEP importieren** (oder Dateien hineinziehen) misst die Teile mit `STEP-Import.exe` und legt die Positionen an; Baugruppen werden als Satz übernommen. **Zusatzarbeiten …** wählt Gewinde, Verzinken, Pulverbeschichten usw. je Bauteil. **Optimieren** plant die Stangen; danach zeigen die Reiter Kalkulation, Schnittplan, Stangenbild und Auswertung die Ergebnisse. Nach jeder Änderung zeigt die Übersicht „VERALTET“, bis neu optimiert wird.
6. Reiter **Staffeln**: je Zeile eine Mengenstufe (Satz oder Position aus der Liste des Angebots und Menge); **Stufen aus Angebot** legt je Satz und Position eine Stufe an. **Staffelpreise rechnen** rechnet jede Stufe als eigenes Angebot neu.
7. Reiter **Nachkalkulation**: nach dem Auftrag Ist-Stangen und EK-Meterpreis je Gruppe (leer = kalkuliert), Laserzeit, Rüstzeit, Zusatzkosten und Erlös eintragen; das Programm vergleicht die Einzelkosten mit der Kalkulation (Abweichung in € und %, Deckungsbeitrag) und gibt den Vergleich als PDF aus.
8. Reiter **Frachtkosten**: Frachtrechner (Empfänger-PLZ, Gewicht, Ladehilfsmittel mit Packvorschlag, Zusatzleistungen) mit aufgeschlüsselter Kostenübersicht und Historie. Frachtzonen und PLZ-Zuordnungen (CSV-Import/-Export), Tarife mit Preisstaffeln und Versionen, Ladehilfsmittel, Zuschläge mit Dieselpreisen und Dieselstaffel, Währungen sowie Dienstleister und Kundentarife werden selbst gepflegt (hinter dem Passwort der Einstellungen). Mitgelieferte Werte sind als BEISPIEL gekennzeichnet; das Programm erfindet keine Tarife oder Dieselzuschläge. **Richtwerte laden** ersetzt die Beispielwerte durch Richtwerte für den Palettenversand in Deutschland (Recherche 10/2026, Marktpreise + 10 % Puffer, Maut und Diesel enthalten, vier Zonen nach Entfernung vom Versandort, gekennzeichnet als RICHTWERT). Im Angebot legt die Karte **Fracht** Frachtart (manuell, berechnet, keine Fracht, im Artikelpreis enthalten) und Verteilung (je Stück oder nach Gewicht) fest; **Fracht berechnen …** übernimmt Betrag und Tarifkopie, und die Staffelpreise rechnen dann je Menge ihre eigene Fracht. Mit dem Haken **Fracht automatisch berechnen** rechnet das Programm die Fracht selbst aus Ziel-PLZ (zwei Stellen reichen, z. B. 25), Gewicht der Positionen, Packvorschlag und der Versandart aus den Einstellungen; liegt ein PLZ-Bereich in mehreren Zonen, gilt die teurere.
9. Leiste **Ausgabe**: **Angebot (PDF)**, **Werkstattpapiere (PDF)**, **Kalkulation (PDF)** und **CSV-Export** (Angebotskopf, Kostenarten und Kalkulation je Position; Semikolon, Dezimalkomma). Die Dateien landen im Ablageordner aus den Einstellungen, sonst in der Vorgabe (siehe Tabelle oben). Das Angebots-PDF schreibt die Materialpreise und Schneiddaten im Angebot fest (`rechnen.preisbasis_aus`, Spalte `angebote.preisbasis`, Schema 18): spätere Änderungen der Stammdaten ändern den Preis nicht; die Übersicht zeigt Abweichungen und bietet **Aktuelle Preise übernehmen …**.

Die bebilderte Bedienungsanleitung `Bedienungsanleitung.pdf` (erzeugt der Build aus `anleitung/erzeuge_anleitung.py`, auch im Release „aktuell“) liegt im ZIP neben der .exe und öffnet sich im Programm über **Hilfe → Bedienungsanleitung** (F1).

Sicherung: beim ersten Start jedes Tages, beim Beenden, auf Knopfdruck, vor Updates, vor Schema-Umstellungen, vor Wiederherstellen und Import eine Kopie nach `Daten/Sicherung`, optional zusätzlich in einen zweiten Sicherungsordner (Einstellungen, z. B. Netzlaufwerk, OneDrive oder USB-Stick). Jede Sicherung wird nach dem Schreiben geprüft (`PRAGMA integrity_check`, gleiche Anzahl Angebote/Positionen) und bekommt eine `.json` mit Version, Schema, Anzahlen und SHA256. Es bleiben die letzten 30 laufenden Sicherungen und je Art die letzten 10 „vor …“-Sicherungen. **Sicherung wiederherstellen …** (Startseite, Menü Datei) prüft die gewählte Datei, lehnt Dateien einer neueren Programmversion ab und sichert vorher den jetzigen Stand. Lässt sich die Datendatei beim Start nicht öffnen, bietet das Programm das Wiederherstellen an. Eine Datendatei einer älteren Version (mit „Aufträgen“) wird beim ersten Öffnen automatisch auf Angebote umgestellt.

## Lizenz

Signierte Lizenzdatei (`.lizenz`, Ed25519), offline, ohne Lizenzserver (`programm/rohrlaser/lizenz.py`). Arten: **Admin** (unbefristet, bis 3 Rechner, Einstellungen ohne Passwort), **Benutzer** (Vorgabe 6 Monate), **Test** (30 Tage, PDFs mit Aufdruck TESTVERSION). Gebunden an die Rechner-ID (`RL-XXXX-XXXX-XXXX-XXXX`, gehasht aus der Windows-MachineGuid) oder „beliebig“ für portabel. Zustände: gültig, läuft bald ab (30 Tage), Kulanz (14 Tage nach Ablauf), danach **Lesemodus**: ansehen, exportieren, sichern und wiederherstellen gehen weiter, ändern nicht; Daten werden nie gelöscht. Der Schreibschutz sitzt in der `Datenbank` (`@schreibt` → Ausnahme `Lesemodus`, dazu `PRAGMA query_only`); jede öffentliche Methode muss `@liest`, `@schreibt` oder `@erlaubt` tragen (`tests/test_lesemodus.py`). Die Lizenz liegt in `Daten/Lizenz` (nicht in `rohrlaser.db`, Sicherung/Export nehmen sie nicht mit), dazu `zeit.json` gegen eine zurückgestellte Uhr und `sperrliste.json`. Einführung in zwei Stufen: solange `lizenz.DURCHSETZUNG = False` gibt es ohne Lizenz nur einen Hinweis.

Lizenz-Werkzeug (nur bei Patrick, nicht im Programm und nicht im Update): `Lizenz-Werkzeug.exe` aus dem Release bzw. `python werkzeuge/lizenz_werkzeug.py` (ohne Befehl Fenster, sonst `schluessel-erzeugen`, `erstellen`, `admin`, `pruefen`, `sperren`, `liste`). Der private Schlüssel liegt passwortgeschützt in `%USERPROFILE%\Rohrlaser-Lizenz\privat_K1.pem`, nie im Repository (`*.pem`, `*.lizenz` in `.gitignore`, `tests/test_lizenz.py` prüft das); den öffentlichen Schlüssel trägt `programm/rohrlaser/lizenz_schluessel.py`. Gesperrte Lizenzen: Werkzeug erzeugt `Sperrliste.json`, die in den Release `update-dateien` von `Rohrlaser-Updates` gehört; das Programm holt sie beim Update-Check.

## Windows-Warnungen (Virenscanner)

Das Programm ist nicht signiert; mit PyInstaller gebaute Programme halten SmartScreen und Defender anfangs oft für verdächtig. Gegen Fehlalarme baut der Workflow den PyInstaller-Bootloader selbst (eigene Signatur statt des auch von Schadsoftware genutzten fertigen Bootloaders), gibt beiden .exe Hersteller-, Produkt- und Versionsangaben (`programm/versionsinfo.py`, im Workflow geprüft), verzichtet auf UPX und legt dem Release eine SHA256-Prüfsumme bei. Was Anwender bei einer Warnung tun (ZIP zulassen, Trotzdem ausführen, Fehlalarm an Microsoft melden), steht in der Bedienungsanleitung, Kapitel 2. Ganz verschwinden die Warnungen erst mit einer Code-Signatur.

## STEP-Import

„STEP importieren“ startet `STEP-Import.exe` (Ordner `STEP-Import` neben dem Programm), das die gewählten Dateien misst und die Werte in eine Textdatei schreibt; das Programm übernimmt sie ins Angebot und protokolliert alles im Reiter STEP-Protokoll. Vor dem Übernehmen zeigt der Dialog „STEP-Import prüfen“ die Rohre der Dateien je Profil (gleiche Teile einer Datei in einer Zeile) mit Häkchen, Profil-ID, Werkstoff und Stückzahl je Teil sowie einer drehbaren 3D-Ansicht (Anfangsschnitt orange, Endschnitt violett, Innenkonturen rot, Gravur grün); das 3D-Modell wird je Position gespeichert (Vorschaubild in der Positionsliste, Knopf „3D-Ansicht …“). Gezeichnet wird ohne OpenGL (`programm/rohrlaser/ansicht3d.py`). Ab 6 Dateien misst `STEP-Import.exe` auf bis zu 4 Prozessorkernen gleichzeitig. Die Messung lässt sich auch direkt aufrufen (`--netze ORDNER` schreibt zusätzlich die 3D-Netze als JSON):

```
STEP-Import.exe --ausgabe messwerte.txt ORDNER_ODER_DATEIEN
python programm/step_messung/step_messen.py --ausgabe messwerte.txt ORDNER_ODER_DATEIEN
```

Messregeln und Annahmen:
- Gerade Rohre mit konstantem Querschnitt (keine Biegeteile).
- Teilelänge = größte Ausdehnung entlang der Rohrachse (bei Gehrung die lange Seite).
- Konturen werden nach Art getrennt: Anfangsschnitt, Endschnitt, Innenkonturen (Bohrungen, Ausschnitte) und Gravuren. Eine Kontur, die bis ans Rohrende reicht (z. B. Ausklinkung), gehört zum Anfangs- bzw. Endschnitt; das Ende gilt dann als nicht gerade.
- Konturgröße: Jede Innenkontur und auch Anfangs- und Endschnitt werden nach ihrem Hüllmaß als klein, mittel oder groß eingestuft (Bohrung = Ø, sonst größere Seite des kleinsten Rechtecks um die abgewickelte Kontur bzw. die Schnittfläche des Endes). Die Grenzen stehen je Maschine in den Stammdaten Maschinen (Vorgabe klein ≤ 10 mm, mittel ≤ 50 mm). Es gilt die im Angebotskopf gewählte Maschine; die Konturliste je Position (`konturen`, `kontur_grenzen`) wird bei anderer Maschine oder geänderten Grenzen neu eingeteilt.
- Gravur = Kontur, die nicht durch die Wand geht. Sie wird separat ausgewiesen und ist nicht im Schneidweg enthalten.
- Schneidweg = Anfangsschnitt + Endschnitt + Innenkonturen, gemessen auf der Außenhaut. Beide Endschnitte zählen voll je Teil.
- Einstiche = Anzahl getrennter Schnittkonturen ohne Gravuren.
- Gewinde: Durchgehende Rundbohrungen werden je Durchmesser gezählt. Passt der Durchmesser zu einem Kernloch in den Stammdaten Gewinde (±0,05 mm), wird ein Gewinde vorgeschlagen (z. B. 4× Ø5 → 4xM6). Gerechnet wird nur, was nach manueller Prüfung in „Gewinde geprüft“ eingetragen ist.
- Je Ende wird erkannt, ob der Schnitt gerade (senkrecht zur Achse) ist, und die Schnittlänge des Endes gemessen. Regel für die Optimierung: zwei benachbarte Teile mit geraden zugewandten Enden teilen sich einen Schnitt, sonst werden zwei Schnitte gerechnet.
- Profilform aus dem Querschnitt: Rund-, Quadrat-, Rechteckrohr; alles andere wird als Sonderprofil mit Hinweis gemeldet.


## Stangenoptimierung und Kalkulation

Regeln:
- Optimiert wird je Profil + Werkstoff + Stangenlänge, ohne Vermischung.
- Belegung je Stange = Endbeschnitt + Teile + Trennungen + Schnittverlust des letzten Schnitts. Frei bleiben muss der Greiferrest. Jede Stange wird vor dem Speichern geprüft; der Schnittplan zeigt das Ergebnis in der Spalte „Prüfung“.
- Trennung: Sind beide zugewandten Enden gerade, gibt es einen gemeinsamen Schnitt (1 × Schnittverlust, 1 Einstich und eine Endschnittlänge gespart). Sonst zwei Schnitte (2 × Schnittverlust + „Abstand getrennte Schnitte“ aus den Maschinen).
- Teile werden bei Bedarf gedreht, damit gerade Enden aneinanderliegen; schräge Enden kommen an Stangenanfang oder -ende.
- Keine Restverwaltung: Reste zählen als Verschnitt.
- Teile, die nicht auf eine Stange passen oder unvollständige Daten haben, stehen in „Auswertung“ unter „Nicht eingeplante Teile“ und in den Positionen als Warnung.
- Verfahren: First-Fit- und Best-Fit-Decreasing, danach werden schwach belegte Stangen aufgelöst. Liegt das Ergebnis über der Untergrenze, rechnet die Schnittmuster-Optimierung (Spaltengenerierung nach Gilmore-Gomory in reinem Python: gleiche Teile als Typ, bestes Muster je Runde per Tiefensuche, lineares Programm mit Simplex; höchstens 300 Muster und 50.000 Suchschritte je Mustersuche). Die abgerundete LP-Lösung legt ganze Stangen fest, der Rest wird heuristisch verteilt; die aufgerundete LP-Lösung ist eine Schranke („optimal (Schranke der Schnittmuster erreicht)“). Hat die Gruppe höchstens 60 Teile und ist das Ergebnis noch nicht bewiesen, sucht danach eine exakte Suche (Branch and Bound, höchstens 20.000 Suchschritte je Gruppe). Alle Grenzen sind Schrittzahlen, das Ergebnis ist reproduzierbar. Vergleich mit 40 großen Testgruppen (`tests/test_optimierung.py`): 1.250 statt 1.271 Stangen, 38 statt 17 nachweislich optimal. Die Auswertung zeigt je Gruppe die Untergrenze, den Abstand dazu, ob das Ergebnis nachweislich optimal ist, und den Vergleich mit einer manuellen Einteilung (Eingabereihenfolge, Stange voll, dann nächste).


Kalkulation: Material (Stangen laut Schnittplan, nach Längenanteil verteilt), Laser schneiden, Gewinde, Rüsten Maschine, Rüsten je Abmessung, Stangenwechsel, Zusatzarbeiten und die Zuschläge ergeben die Herstellkosten; dazu Gewinn, Pauschale je Abmessung, Programmierkosten, Angebotsaufschlag, Fracht und Skonto ergeben den Verkaufspreis. Zuschläge, Gewinn, Rüstzeit und Pauschalen kommen als Vorgabe aus den Einstellungen in jedes neue Angebot und sind dort im Angebotskopf änderbar. Die berechnete Schneidzeit steht grau in der Positionsliste und lässt sich je Position überschreiben. Das Skonto aus dem Angebotskopf (Vorgabe vom Kunden bzw. aus den Einstellungen) wird eingerechnet: Verkaufspreis = Preis ohne Skonto ÷ (1 − Skonto); das Angebots-PDF nennt die Zahlungsbedingung. Übersicht, Kalkulation, Kalkulations-PDF und CSV-Export listen jede Kostenart einzeln.

## Entwicklung

- `programm/rohrlaser/`: das Programm (PySide6). `optimierung.py` Stangenoptimierung, `rechnen.py` Positionswerte, Status und Kalkulation, `staffeln.py`, `fracht.py` (Frachtrechnung) + `fracht_angebot.py` (Fracht im Angebot und je Staffelmenge) + `fracht_daten.py` (Frachttabellen) + `fracht_seite.py` (Reiter Frachtkosten), `step.py` (Übernahme der Messwerte), `ausgabe.py` + `pdf.py` (PDF), `export.py` (CSV), `datenbank.py` (SQLite, Schema-Erweiterung alter Dateien).
- `programm/step_messung/`: STEP-Messung mit OpenCascade (`step_geometrie.py`, `step_messen.py`), wird als eigene `STEP-Import.exe` gebaut.
- Start: `pip install -r requirements.txt -r programm/requirements.txt`, dann im Ordner `programm` `python -m rohrlaser`.
- Tests (Oberfläche ohne Bildschirm mit `QT_QPA_PLATFORM=offscreen`): `tests/test_programm.py`, `tests/test_sicherung.py` (Datenort, Sperre, Sicherung, Wiederherstellen, Export/Import), `tests/test_preisbasis.py` (festgeschriebene Preise), `tests/test_rundung.py` (kaufmännische Rundung, Zeilen = Summe), `tests/test_zusatzarbeiten.py`, `tests/test_step_satz.py`, `tests/test_fracht.py`, `tests/test_fracht_angebot.py`, `tests/test_fracht_auto.py` (zweistellige PLZ, automatische Fracht), `tests/test_fracht_richtwerte.py` (Richtwerte Palettenversand), `tests/test_optimierung.py`, `tests/test_maschinen.py` (Maschinen T03/T11/LT7, Schneiddaten-Richtwerte, Umbenennen, Anpassung älterer Dateien), `tests/test_step_import.py`, `tests/test_lizenz.py` + `tests/test_lesemodus.py` (Lizenz, Lesemodus), `tests/test_anleitung.py` (jede Tabelle, jedes Feld, jede Einstellung und jeder Knopf steht in der Anleitung) und `tests/test_abnahme.py`.
- Abnahme: `tests/test_abnahme.py` rechnet 8 realistische Testangebote (`tests/abnahme_angebote.py`) auf dem Weg des Programms und prüft das Ergebnis unabhängig nach: jede Position mit voller Stückzahl eingeplant und nichts vermischt, Lage jedes Teils gegen Endbeschnitt, Trennschnitte und Greiferrest (keine Stange überlastet), Belegung, Rest, Gewicht und Materialkosten, nie mehr Stangen als die einfache manuelle Einteilung und nie weniger als die Untergrenze. GitHub Actions legt bei jedem Lauf das `Abnahmeprotokoll.md` ab.
- Bedienungsanleitung neu erzeugen: `python anleitung/erzeuge_anleitung.py` (braucht `pdftoppm` aus Poppler); die Bildschirmfotos stammen aus dem echten Programm. Die PDF liegt nicht im Repository, der Build erzeugt sie bei jedem Pull Request und jedem Windows-Lauf.
- Jede Programmänderung passt die Anleitung an (Build-Prüfung `tests/pruefe_anleitung_geaendert.py`); sonst in einer Commit-Nachricht `Anleitung: unverändert, weil …`. Kapitelverweise im Text nur als `[[marke]]` (Überschrift mit `marke="…"`), die Nummern setzt das Programm ein.
- `.github/workflows/paket.yml` baut auf Windows `STEP-Import.exe` und `Rohrlaser-Angebotskalkulation.exe` (PyInstaller), prüft beide (Messung gegen Python, `--selbsttest` der fertigen .exe, Online-Update), baut daraus das Setup (Inno Setup) und prüft Installation, Datenort, Deinstallation ohne Datenverlust, Neuinstallation und die portable Version mit gleichen Rechenergebnissen (`tests/installer_windows.py`). Dieser Windows-Teil läuft nur von Hand gestartet (Actions > Paket > Run workflow): auf `main` gehen Setup und ZIP dann als Release „aktuell“ und als Online-Update hinaus, von anderen Zweigen wird nur gebaut und geprüft. Pull Requests und Pushes auf `main` laufen nur die Linux-Prüfungen, so werden mehrere gemergte Pull Requests zusammen mit einem Windows-Lauf veröffentlicht.

Alle Stammdaten im Programm sind Beispielwerte.
