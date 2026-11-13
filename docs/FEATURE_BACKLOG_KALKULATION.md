# Feature-Backlog Rohrlaser-Kalkulation

Stand: 12.11.2026, geprüft gegen `main` (Version 0.9.293, Schema 82) und die offenen Entwurfs-PRs #450, #451, #452 (und #358). Ausführliche Begründungen, Quellen und Verknüpfungen: [ROADMAP_KALKULATION_ERWEITERUNGEN.md](ROADMAP_KALKULATION_ERWEITERUNGEN.md).

**Nur Planung.** Nichts davon ist gebaut oder freigegeben; jede Aufgabe wird erst nach Patricks Freigabe umgesetzt.

Umfang: **85 Entwicklungsaufgaben** (verbessern, neu, prüfen), dazu 76 Funktionen, die schon vorhanden oder im Bau sind, und 6 bewusst verworfene Punkte.

## Legende

| Kürzel | Bedeutung |
|---|---|
| ✅ vorhanden | Bereits vorhanden |
| 🚧 im Bau/PR | Bereits vorhanden (offener PR bzw. freigegeben, im Bau) |
| 🔧 verbessern | Vorhanden, aber verbesserungswürdig |
| 🆕 neu | Neu zu entwickeln |
| 🔬 prüfen | Zunächst technisch zu prüfen |
| ⛔ nicht sinnvoll | Nicht sinnvoll |

Bewertung: **KN** Kundennutzen 1–10, **WN** wirtschaftlicher Nutzen 1–10, **TA** technischer Aufwand 1–10 (10 = sehr aufwendig), Priorität Hoch/Mittel/Niedrig, Umsetzbarkeit Einfach/Mittel/Schwierig. Die Werte sind Einschätzungen aus der Code-Analyse, keine Messungen.

ID-Kreise: MAT Material, GEO Geometrieerkennung, CALC Arbeitsgänge/Zeiten, PART Zukauf/Normteile, MACH Maschine, CAD 3D-Editor, ASM Baugruppen, OFFER Angebot/Preis, CAM Stangenoptimierung/Fertigung, ERP Schnittstellen/Rechte, QA Prüfung der Kalkulation.

## Top 10 – zuerst entwickeln

| Rang | ID | Erweiterung | Warum zuerst |
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

## Phase 1 – Schnelle Verbesserungen (7 Aufgaben)

| ID | Aufgabe | Status | KN | WN | TA | Priorität | Umsetzbarkeit | Abhängigkeiten |
|---|---|---|---|---|---|---|---|---|
| MAT-010 | Materialpreislisten importieren (Rohre/Profile) | 🔧 verbessern | 6 | 8 | 4 | Hoch | Mittel | Beispieldatei des Lieferanten/ERP (#358); MAT-008 empfohlen |
| QA-002 | Ende-zu-Ende-Abnahme mit echten STEP-Dateien | 🔧 verbessern | 5 | 6 | 3 | Hoch | Einfach | Dateien von Patrick (C2/D1) |
| OFFER-007 | Rüst- und Programmierkosten als eigene Zeile | 🚧 im Bau/PR | 6 | 6 | 3 | Mittel | Einfach | keine |
| MAT-011 | Getrennter Gewinn auf Material und auf Bearbeitung sichtbar | 🚧 im Bau/PR | 5 | 6 | 2 | Mittel | Einfach | keine |
| CALC-025 | Artikelnummer gravieren als Kundenvorgabe | 🚧 im Bau/PR | 5 | 5 | 2 | Niedrig | Einfach | keine |
| MAT-016 | Zeugniskosten (3.1) je Abmessung | 🚧 im Bau/PR | 4 | 5 | 2 | Niedrig | Einfach | keine |
| ASM-002 | Hauptbauteil der Baugruppe festlegen | 🚧 im Bau/PR | 4 | 3 | 2 | Niedrig | Einfach | keine |

## Phase 2 – Erweiterung der Kalkulation (37 Aufgaben)

| ID | Aufgabe | Status | KN | WN | TA | Priorität | Umsetzbarkeit | Abhängigkeiten |
|---|---|---|---|---|---|---|---|---|
| OFFER-021 | Rückfragen nur mit Preiswirkung | 🚧 im Bau/PR | 8 | 8 | 4 | Hoch | Mittel | CALC-029, GEO-018 |
| GEO-009 | Zentrale Merkmal-Regeln: jedes Merkmal → Arbeitsgang/Zusatzarbeit/Prüfregel | 🚧 im Bau/PR | 8 | 8 | 5 | Hoch | Mittel | keine; ersetzt nichts, liest die vorhandenen Regeln mit |
| OFFER-003 | Teilbestell-Risiko bei gemeinsam optimierten Positionen | 🚧 im Bau/PR | 7 | 8 | 4 | Hoch | Mittel | keine |
| ASM-004 | Preis 'nur Teile' und 'geschweißt' nebeneinander | 🚧 im Bau/PR | 7 | 7 | 3 | Hoch | Einfach | keine |
| MACH-014 | Schneiddaten mit Quelle und Gültigkeitsbereich | 🚧 im Bau/PR | 7 | 7 | 3 | Hoch | Einfach | Schema +1 |
| OFFER-004 | Staffelstufen an Stangensprüngen vorschlagen | 🚧 im Bau/PR | 7 | 7 | 4 | Hoch | Mittel | keine |
| PART-004 | Normteilbibliothek mit DIN/ISO-Merkmalen | 🔧 verbessern | 7 | 7 | 6 | Hoch | Mittel | PR #450 |
| OFFER-008 | Erklärung bei Preisabweichung zum Wiederholteil | 🚧 im Bau/PR | 7 | 6 | 4 | Hoch | Mittel | MAT-008 |
| QA-006 | Regelkatalog aller Prüfungen | 🚧 im Bau/PR | 6 | 6 | 4 | Hoch | Mittel | QA-005 |
| OFFER-009 | Preisband ähnlicher Teile | 🔧 verbessern | 7 | 7 | 4 | Mittel | Mittel | GEO-014 |
| MAT-008 | Materialpreis als Zeitreihe statt Überschreiben | 🚧 im Bau/PR | 7 | 7 | 5 | Mittel | Mittel | Schema-Erweiterung; Preiswächter und Preisbasis müssen den Stichtag kennen |
| OFFER-016 | Drei Liefertermine mit Preis (Express, Standard, flexibel) | 🔧 verbessern | 6 | 7 | 3 | Mittel | Einfach | Schnittstelle Auslastung |
| CALC-007 | Lernkurve: Stückzeit sinkt mit der Menge | 🚧 im Bau/PR | 6 | 7 | 4 | Mittel | Mittel | CALC-005 |
| CALC-010 | Sägen als günstigere Alternative zum Laser | 🚧 im Bau/PR | 6 | 7 | 4 | Mittel | Mittel | Säge-Kennwerte von Patrick |
| MAT-013 | Mindestabnahme je Abmessung (Bund, Mindestmenge des Lieferanten) | 🚧 im Bau/PR | 5 | 7 | 3 | Mittel | Einfach | Regel 'kein Restelager' beachten |
| CALC-016 | Fremdbearbeitung mit Transport und Lieferzeit | 🚧 im Bau/PR | 5 | 7 | 3 | Mittel | Einfach | keine |
| CALC-020 | Programmierzeit nach Komplexität | 🚧 im Bau/PR | 5 | 7 | 3 | Mittel | Einfach | keine |
| PART-007 | Lieferzeit der Zukaufteile im Liefertermin | 🆕 neu | 6 | 6 | 3 | Mittel | Einfach | Schnittstelle Auslastung (Termin prüfen) |
| CALC-024 | Folge- und Ausschlussregeln zwischen Zusatzarbeiten | 🚧 im Bau/PR | 6 | 6 | 3 | Mittel | Einfach | GEO-009 |
| CALC-027 | Kosten je Bohrungsart nebeneinander (Gewinde, Flowdrill, Einnietmutter, Einschweißmutter) | 🚧 im Bau/PR | 6 | 6 | 3 | Mittel | Einfach | keine |
| MAT-012 | Materialindex/Legierungszuschlag je Monat | 🚧 im Bau/PR | 5 | 7 | 4 | Mittel | Mittel | MAT-008 |
| MAT-014 | Vorverzinkt/vorbeschichtet kaufen oder nachträglich veredeln | 🚧 im Bau/PR | 6 | 6 | 4 | Mittel | Mittel | Oberflächen mit Preisen gepflegt |
| CALC-008 | Mengenstaffel je Zusatzarbeit (Fremdleister-Preisliste) | 🚧 im Bau/PR | 5 | 7 | 4 | Mittel | Mittel | keine |
| OFFER-011 | Zielpreis rückwärts: welche Stellschrauben reichen | 🔧 verbessern | 6 | 6 | 4 | Mittel | Mittel | keine |
| CALC-019 | Oberfläche: Sperrgut- und Mindestpreis je Teil nach Länge/Gewicht | 🚧 im Bau/PR | 5 | 6 | 3 | Mittel | Einfach | keine |
| PART-009 | Sammel-Preisanfrage für Zukaufteile ohne Preis | 🆕 neu | 5 | 6 | 3 | Mittel | Einfach | PART-004 |
| MAT-019 | Gewicht aus STEP-Volumen gegen gerechnetes Gewicht prüfen | 🚧 im Bau/PR | 5 | 6 | 3 | Mittel | Einfach | keine |
| CALC-015 | Handlingzuschlag nach Teilgewicht/-länge | 🚧 im Bau/PR | 4 | 6 | 3 | Mittel | Einfach | PR #451 |
| CALC-009 | Arbeitsplan je Position (Reihenfolge, Liegezeit, Durchlaufzeit) | 🔧 verbessern | 5 | 5 | 4 | Mittel | Mittel | Schnittstelle Auslastung |
| OFFER-015 | Englisches Angebots-PDF | 🆕 neu | 5 | 5 | 4 | Mittel | Mittel | keine |
| CALC-006 | Werkzeugkosten je Arbeitsgang ausweisen | 🚧 im Bau/PR | 4 | 6 | 3 | Niedrig | Einfach | keine |
| MAT-021 | Stangenwechsel-Zeit nach Stangengewicht | 🚧 im Bau/PR | 4 | 5 | 2 | Niedrig | Einfach | keine |
| CALC-018 | Ausschuss nach Regel statt pauschal | 🚧 im Bau/PR | 4 | 5 | 3 | Niedrig | Einfach | keine |
| CALC-026 | Bündeln und Umreifen je Bund aus dem Packvorschlag | 🚧 im Bau/PR | 4 | 5 | 3 | Niedrig | Einfach | keine |
| PART-013 | EK-Verlauf je Zukaufartikel | 🚧 im Bau/PR | 4 | 5 | 3 | Niedrig | Einfach | MAT-008 (gleiche Darstellung) |
| OFFER-013 | Rabattstaffel je Kunde nach Jahresumsatz | 🆕 neu | 4 | 4 | 2 | Niedrig | Einfach | keine |
| ERP-003 | Rechte nach Rolle (Vertrieb/AV) | 🔧 verbessern | 4 | 5 | 4 | Niedrig | Mittel | keine |

## Phase 3 – Intelligente CAD-Verknüpfung (26 Aufgaben)

| ID | Aufgabe | Status | KN | WN | TA | Priorität | Umsetzbarkeit | Abhängigkeiten |
|---|---|---|---|---|---|---|---|---|
| CALC-028 | Herkunft und Sicherheit für jeden Rechenwert | 🆕 neu | 9 | 9 | 6 | Hoch | Schwierig | OFFER-010, X1 (ArTube-Plan) |
| CAD-009 | Arbeitsgänge per Rechtsklick im Editor | 🔧 verbessern | 7 | 7 | 4 | Hoch | Mittel | PR #450, GEO-009 |
| CALC-030 | Kostentreiber über alle Aufträge | 🆕 neu | 7 | 7 | 4 | Mittel | Mittel | X1 (ArTube-Plan), Nachkalkulation |
| GEO-010 | Passungen und Toleranzen aus der Zeichnung an die Bohrung binden | 🔧 verbessern | 7 | 7 | 5 | Mittel | Mittel | GEO-009 |
| CALC-029 | Empfindlichkeit je Annahme | 🆕 neu | 6 | 7 | 4 | Mittel | Mittel | CALC-028 hilfreich |
| OFFER-022 | Wettbewerbsabstand je Kategorie im Angebots-Check | 🆕 neu | 6 | 6 | 2 | Mittel | Einfach | Absage-Auswertung |
| GEO-012 | Schweißvorbereitung (Fasen) als Arbeitsgang | 🔧 verbessern | 6 | 6 | 3 | Mittel | Einfach | GEO-009, PR #450 |
| GEO-014 | Ähnliche Teile trotz anderer Artikelnummer finden | 🔧 verbessern | 6 | 7 | 5 | Mittel | Mittel | keine |
| CAD-005 | Kostentreiber im 3D einfärben | 🆕 neu | 7 | 6 | 5 | Mittel | Mittel | CAD-004 |
| KI-001 | Anfrage-Mail auslesen mit Fundstelle | 🆕 neu | 7 | 6 | 5 | Mittel | Mittel | CALC-028; 10–20 Beispiel-Mails von Patrick |
| CALC-017 | Montagezeit aus Verbindungselementen | 🆕 neu | 6 | 6 | 4 | Mittel | Mittel | PR #450, PART-004 |
| ASM-006 | Vorrichtungskosten vorschlagen | 🆕 neu | 5 | 6 | 3 | Mittel | Einfach | Richtwerte von Patrick |
| CALC-012 | Bolzenschweißen und Einpressen je Element automatisch | 🆕 neu | 5 | 6 | 4 | Mittel | Mittel | GEO-009, PART-006 |
| PART-006 | Einpresselemente aus dem Lochbild in Blechen | 🆕 neu | 5 | 6 | 4 | Mittel | Mittel | GEO-009, PART-004 |
| PART-010 | Fehlende Verbindungselemente in Baugruppen erkennen | 🆕 neu | 6 | 6 | 6 | Mittel | Mittel | PART-004 |
| CAD-010 | Teilefamilien mit Variablen | 🆕 neu | 6 | 6 | 6 | Mittel | Mittel | keine |
| GEO-019 | Revisionsvergleich der Geometrie | 🔧 verbessern | 6 | 5 | 5 | Mittel | Mittel | keine |
| PART-005 | Normgröße aus der Geometrie vorschlagen | 🔬 prüfen | 6 | 6 | 7 | Mittel | Schwierig | PART-004; Beispieldateien |
| GEO-013 | Spiegelteile (links/rechts) erkennen | 🆕 neu | 5 | 5 | 4 | Mittel | Mittel | keine |
| CAD-008 | Flächen markieren: Sichtfläche, Abkleben, Schweißfläche | 🆕 neu | 5 | 5 | 4 | Mittel | Mittel | PR #450 |
| GEO-011 | STEP AP242: PMI und Bohrungsmerkmale lesen | 🔬 prüfen | 7 | 6 | 8 | Niedrig | Schwierig | 10–20 echte Kunden-STEPs (offen bei Patrick, C2/D1) |
| PART-012 | Endkappen aus offenen Rohrenden vorschlagen | 🔧 verbessern | 5 | 5 | 3 | Niedrig | Einfach | PART-004 |
| GEO-015 | Biegerohre aus der STEP messen | 🔬 prüfen | 6 | 6 | 8 | Niedrig | Schwierig | Beispiel-STEPs mit Biegeteilen; K4 |
| ASM-005 | Baugruppen-Varianten (mit/ohne Oberfläche, Zukauf) | 🆕 neu | 5 | 5 | 4 | Niedrig | Mittel | ASM-004 |
| GEO-016 | Flachgedrückte/gequetschte Rohrenden erkennen | 🆕 neu | 5 | 5 | 6 | Niedrig | Mittel | Beispiel-STEPs |
| ASM-008 | Gewicht und Schwerpunkt der Baugruppe für Handling und Verpackung | 🆕 neu | 4 | 4 | 3 | Niedrig | Einfach | keine |

## Phase 4 – Professionelle Fertigungsintegration (15 Aufgaben)

| ID | Aufgabe | Status | KN | WN | TA | Priorität | Umsetzbarkeit | Abhängigkeiten |
|---|---|---|---|---|---|---|---|---|
| MACH-005 | Schneiddaten aus Ist-Zeiten kalibrieren | 🔧 verbessern | 7 | 9 | 6 | Hoch | Mittel | genug Ist-Daten; PR #451 |
| MAT-018 | Wöchentlicher Sammelbedarf über beauftragte Aufträge | 🆕 neu | 6 | 7 | 4 | Mittel | Mittel | PR #451 gemergt; MAT-013 |
| MACH-006 | Maschine je Position wählen | 🆕 neu | 6 | 8 | 6 | Mittel | Mittel | Auslastung (freie Kapazität) |
| OFFER-012 | Kundenwert: Deckungsbeitrag je Kunde und Jahr | 🔧 verbessern | 5 | 7 | 4 | Mittel | Mittel | keine |
| CAM-003 | Direkter Export im Format des Rohr-CAM | 🔬 prüfen | 6 | 7 | 7 | Mittel | Schwierig | Formatbeschreibung/Beispieldatei des CAM von Patrick |
| CAM-004 | Stangenrückmeldung in die Nachkalkulation | 🔧 verbessern | 5 | 6 | 3 | Mittel | Einfach | PR #451, #452 |
| KI-002 | Fragen zum Rechenweg beantworten | 🔬 prüfen | 6 | 7 | 7 | Niedrig | Schwierig | CALC-014, CALC-028 |
| MACH-004 | Vorschub-Abminderung nach Wandbereich | 🔬 prüfen | 4 | 6 | 2 | Niedrig | Einfach | MACH-005 |
| CAM-005 | Materialbündelung über offene Aufträge für den Angebotspreis | 🔬 prüfen | 5 | 6 | 6 | Niedrig | Schwierig | PR #451, #452 |
| ERP-004 | Übergabe an Buchhaltung (DATEV-CSV, XRechnung) | 🔬 prüfen | 5 | 6 | 6 | Niedrig | Mittel | Angabe des Zielsystems von Patrick |
| MACH-008 | Rüstoptimierte Reihenfolge im Fertigungslos | 🆕 neu | 4 | 6 | 5 | Niedrig | Mittel | PR #451 |
| PART-008 | Lager für Normteile (Kanban, Meldebestand) | 🆕 neu | 4 | 5 | 4 | Niedrig | Mittel | PR #452 (Meldebestand Stangen) als Vorbild |
| MACH-012 | Bandbreite der Laserzeit anzeigen | 🆕 neu | 4 | 5 | 4 | Niedrig | Mittel | MACH-005 |
| CAM-006 | Stabile Stangenpläne bei kleinen Mengenänderungen | 🆕 neu | 4 | 4 | 5 | Niedrig | Mittel | keine |
| CAM-007 | Echte Blechverschachtelung statt Hüllrechteck | 🔬 prüfen | 4 | 5 | 7 | Niedrig | Schwierig | Klärung: Bleche Zukauf oder Eigenfertigung |

## Bereits vorhanden oder im Bau (keine neue Aufgabe)

| ID | Funktion | Stand | Beleg im Repository |
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

## Nicht sinnvoll (bewusst verworfen)

| ID | Punkt | Begründung |
|---|---|---|
| MAT-017 | Reststückverwaltung/Restelager ausbauen | Nicht sinnvoll: Projektregel 'Kein Restelager (Verschnitt nur melden)'. Die vorhandene optionale Einstellung für Reststücke im Lager bleibt, wird aber nicht erweitert. PROfirst verwaltet Resttafeln mit Priorität (Blech). |
| MACH-010 | Maschinenstillstände in der Kalkulation | Nicht sinnvoll in der Kalkulation: Stillstände gehören in den Stundensatz bzw. in die Rohrlaser Auslastung (dort gebaut). Doppelt gerechnet würde jedes Angebot zu teuer. |
| CAD-012 | Behälterbau, Klöpperboden, Konus-Abwicklungen | Nicht sinnvoll: keine Rohrlaser-Teile, gehören zu Blech-Abwicklungsprogrammen. |
| CAM-008 | Resttafeln, Restgitter, Mehrbrenner, Power-Nesting-Drehschritte | Nicht sinnvoll: Plattenlaser-Themen; Resttafeln widersprechen 'kein Restelager'. |
| CAM-009 | Gemeinsamer Schnitt bei Gehrungen | Nicht sinnvoll: Projektregel 'Gehrungen mit Teileabstand', gegenläufige Gehrungen ohne gemeinsamen Schnitt. |
| ERP-006 | Kundenportal/Webshop | Zurzeit nicht sinnvoll: Server-Synchronisation ist auf Eis; zuerst die Kalkulation selbst ausbauen. |

## Übersicht je Bereich

| Bereich | vorhanden | im Bau | verbessern | neu | prüfen | nicht sinnvoll |
|---|---|---|---|---|---|---|
| A. Material- und Rohstoffkalkulation | 8 | 2 | 3 | 7 | 0 | 1 |
| B. Automatische Geometrieerkennung | 8 | 6 | 5 | 2 | 2 | 0 |
| C. Arbeitsgänge und Fertigungszeiten | 4 | 7 | 8 | 11 | 0 | 0 |
| D. Zukaufteile und Normteile | 4 | 0 | 3 | 5 | 1 | 0 |
| E. Maschinen- und Zeitkalkulation | 4 | 2 | 1 | 4 | 1 | 1 |
| F. 3D-Editor und CAD-Verknüpfung | 2 | 6 | 1 | 3 | 0 | 1 |
| G. Baugruppen und Zusammenbau | 2 | 1 | 0 | 5 | 0 | 0 |
| H. Angebot und Preisgestaltung | 3 | 7 | 7 | 5 | 0 | 0 |
| I. CAM, Stangenoptimierung und Fertigungsvorbereitung | 2 | 1 | 1 | 1 | 3 | 2 |
| J. Schnittstellen, Rechte und Organisation | 1 | 2 | 1 | 0 | 1 | 1 |
| K. Qualitätssicherung der Kalkulation | 1 | 3 | 1 | 1 | 0 | 0 |
| L. KI-Unterstützung | 0 | 0 | 0 | 1 | 1 | 0 |

