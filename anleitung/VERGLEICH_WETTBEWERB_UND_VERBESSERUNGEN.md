# Wettbewerbsanalyse und Entwicklungsplan – Rohrlaser-Angebotskalkulation

## Ziel

Die bestehende Anwendung `Rohrlaser-Kalkulation-` gezielt anhand etablierter Software für Rohrlaser-Kalkulation, CAD/CAM, Nesting und Fertigungsplanung verbessern. Ziel ist kein kompletter Neubau, sondern die schrittweise Übernahme sinnvoller Funktionen in die vorhandene Architektur.

## Vergleichsprodukte und Recherchefelder

- **PROfirst TubeCALC:** Profil-/Geometrieerkennung, Stücklistenerstellung, Baugruppen und Kalkulation.
- **TRUMPF TruTops Calculate:** Fertigungszeiten, Maschinenkosten, Verbrauchswerte und Kostenmodell.
- **Lantek Flex3D Tubes:** Rohrnesting, Stangenoptimierung und Restmaterial.
- **BLM ArTube / ProTube:** Rohrbaugruppen, komplexe Profile und Fertigungsprozesse.
- **TRUMPF Programming Tube:** 3D-Rohrbearbeitung und Bearbeitungsabläufe.
- **Lantek MES:** Produktionsplanung, Auftragsstatus und Rückmeldungen aus der Fertigung.

Die Herstellerangaben dienen als Orientierung. Vor einer Umsetzung muss Claude die konkrete Funktion anhand aktueller, öffentlich zugänglicher Dokumentation verifizieren. Keine Funktion als vorhanden oder überlegen darstellen, wenn das nicht belegt ist.

## Phase 1 – Ist-Analyse vor jeder Änderung

1. README, Verzeichnisstruktur, Datenmodell, Module und aktuelle Tests untersuchen.
2. Den tatsächlichen Implementierungsstand jeder relevanten Funktion anhand des Codes feststellen.
3. Bereits vorhandene und teilweise implementierte Funktionen identifizieren, damit nichts doppelt entwickelt wird.
4. Zu jedem Vorschlag die Vergleichsfunktion, den konkreten Nutzen, die bestehende Code-Stelle und die verbleibende Lücke nennen.
5. Abhängigkeiten, Datenbankmigrationen, Lizenzierung, Sicherung, Preis-Snapshots und Rückwärtskompatibilität berücksichtigen.
6. Zunächst nur einen priorisierten Bericht erstellen. Noch keine Codeänderungen ausführen, bis die Analyse vorliegt.

## Phase 2 – Prioritäten

### P0 – Korrektheit und wirtschaftlicher Nutzen

#### 1. Materialbestand und Reststückverwaltung
- Reststücke mit eindeutiger ID, Profil, Werkstoff, Abmessungen/Länge, Charge, Lagerort und Status verwalten.
- Reststücke reservieren und gegen doppelte Verwendung schützen.
- Verfügbare Handelslängen, Bestandsmaterial und Reststücke in zulässigen Kombinationen vergleichen.
- Verschnitt, Greiferrest, Schnittverlust, Beschnitt und tatsächliche Materialkosten berücksichtigen.
- Reststücke erst nach bestätigtem Fertigungs-/Materialverbrauch endgültig ausbuchen.
- Bestand und Restmaterialverwaltung optional halten, damit einfache Angebote weiterhin funktionieren.

**Abnahmekriterien**
- Ein Reststück kann nicht gleichzeitig mehreren Aufträgen fest zugeordnet werden.
- Keine Stange wird überbelegt; Greiferrest und Schnittverluste werden korrekt berücksichtigt.
- Materialkosten stimmen mit einer unabhängigen Kontrollrechnung überein.
- Reservierung, Freigabe, Verbrauch, Storno und Wiederherstellung sind getestet.

#### 2. Kalkulation und Nachkalkulation verbinden
- Kalkulierte Werte und tatsächliche Werte nach Maschine, Werkstoff, Profil, Stückzahl und Arbeitsgang vergleichen.
- Rüstzeit, Laufzeit, Materialverbrauch, Ausschuss, Fremdleistung, Fracht und Zusatzkosten getrennt auswerten.
- Abweichungen in Euro und Prozent sowie Einfluss auf Deckungsbeitrag darstellen.
- Ausreichend belastbare historische Daten als Vorschläge für neue Richtwerte nutzen.
- Neue Richtwerte nur nach ausdrücklicher Freigabe übernehmen; keine stille automatische Änderung.

**Abnahmekriterien**
- Alte Angebote und gespeicherte Preisgrundlagen bleiben unverändert.
- Fehlende Ist-Daten werden nicht als Nullkosten interpretiert.
- Vorschläge zeigen Datenbasis, Stichprobengröße und Unsicherheit.
- Ergebnisse sind reproduzierbar und unabhängig nachprüfbar.

#### 3. STEP-Import und Geometrieprüfung absichern
- Erkannte Merkmale und nicht eindeutig erkannte Geometrien sichtbar trennen.
- Profilform, Querschnitt, Wandstärke, Länge, Gehrungen, Innenkonturen und Gewindevorschläge prüfen.
- Status je Merkmal: sicher erkannt, manuell zu prüfen oder nicht erkannt.
- Rohdaten, Annahmen und manuelle Korrekturen protokollieren.
- Unbekannte Geometrien nicht stillschweigend als Standardprofil behandeln.

**Abnahmekriterien**
- Unsichere Merkmale sind vor der Übernahme klar erkennbar.
- Manuelle Korrekturen bleiben nach erneutem Öffnen erhalten.
- Defekte und ungewöhnliche STEP-Dateien führen nicht zum Absturz des Hauptprogramms.
- Vorhandene STEP-Regressionstests bestehen.

### P1 – Automatisierung und Bedienung

#### 4. Regelbasierte Arbeitsgangvorschläge
- Arbeitsgänge je Angebotsposition vorschlagen: Programmieren, Gewinde, Bohren, Senken, Entgraten, Verzinken, Pulverbeschichten, Schweißen, Montage und Zukauf.
- Regeln anhand Profil, Werkstoff, Geometrie, Kundenanforderungen und Auftragsart definieren.
- Zeit, Menge, Einheit, Kostenart, Fremdleistung und Freigabestatus anzeigen.
- Jeden Vorschlag einzeln bestätigen, bearbeiten oder entfernen lassen.
- Keine doppelte Berechnung derselben Leistung; Regeln und Herkunft jedes Vorschlags nachvollziehbar machen.

**Abnahmekriterien**
- Ein Testangebot mit Rohrlaserteil, Gewinden, Verzinkung und Zukaufteil erzeugt passende Arbeitsgänge ohne Duplikate.
- Positionssumme, Kostenarten und Angebotssumme sind konsistent.
- Nicht bestätigte oder nicht zutreffende Vorschläge werden nicht unbemerkt als verbindliche Fertigungsvorgaben behandelt.

#### 5. Variantenvergleich für Material und Fertigung
- Zulässige Stangenlängen, Bestandsmaterial und Reststücke vergleichen.
- Materialkosten, Verschnittquote, Stangenanzahl und geschätzte Fertigungszeit darstellen.
- Zielkriterien nachvollziehbar gewichten; günstigste Lösung nicht allein an der Stangenanzahl festmachen.
- Optimierungslauf, Grenzen und Ergebnisstatus dokumentieren.

**Abnahmekriterien**
- Jede Variante erfüllt dieselben Fertigungs- und Sicherheitsregeln.
- Die angezeigte beste Variante entspricht der gewählten Zielgröße.
- Laufzeitgrenzen und nicht bewiesene Optimalität werden klar gekennzeichnet.

#### 6. Angebots-, Werkstatt- und Auftragsstatus verbinden
- Freigabe, Arbeitsvorbereitung, Materialbereitstellung, Fertigung, Fremdvergabe, Qualitätsprüfung und Fertigmeldung als konfigurierbare Status abbilden.
- Angebotspositionen und Werkstattunterlagen über stabile IDs verknüpfen.
- Änderungen nachvollziehbar protokollieren.
- Werkstattunterlagen aus einem eindeutig festgelegten Angebots-/Auftragsstand erzeugen.

**Abnahmekriterien**
- Statuswechsel sind nachvollziehbar und können nicht versehentlich doppelt verbucht werden.
- Werkstattkarten zeigen die zum freigegebenen Stand passenden Daten.
- Änderungen nach Freigabe werden erkennbar und lösen bei Bedarf eine erneute Freigabe aus.

### P2 – Erweiterte Fertigungsfunktionen

- Bauteilmarkierung und Rückverfolgbarkeit.
- Erweiterte 3D-Simulation und Kollisionsprüfung.
- Schnittstellen zu externen CAD/CAM- oder Produktionssystemen.
- Auswertungen zu Materialverbrauch, Ausschuss, Durchlaufzeiten und Produktivität.
- Weitere parametrische CAD-Funktionen nur dort ergänzen, wo sie klaren Nutzen bringen und die bestehende Geometriearchitektur unterstützen.

## Phase 3 – Technische Leitplanken

- Vorhandene Python-/PySide6-Architektur und bestehende Rechenkerne weiterverwenden.
- Keine komplette Neuentwicklung und keinen parallelen zweiten Kalkulationskern starten.
- Bestehende Datenbankmigrationen verwenden; Schemaänderungen mit Altbeständen testen.
- Änderungen in kleine, unabhängig prüfbare Schritte teilen.
- Bestehende Berechnungsregeln nicht ohne dokumentierte Begründung ändern.
- Angebote, Preis-Snapshots, Lizenzen, Lesemodus, Updates, Sicherungen und Datenexport/-import schützen.
- Bestehende Funktionen rückwärtskompatibel halten, soweit technisch möglich.
- Unsichere Geometrieerkennung oder Kostenrichtwerte nie stillschweigend übernehmen.
- Keine CNC-Ausgabe als freigegeben behandeln, solange Maschinenkompatibilität und Fertigungsregeln nicht validiert wurden.
- Neue Abhängigkeiten nur nach Prüfung von Lizenz, Größe, Wartbarkeit, Offline-Fähigkeit und Build-Auswirkungen hinzufügen.

## Phase 4 – Umsetzung nach Freigabe

Nach Abschluss und Prüfung der Ist-Analyse jeweils nur den nächsten freigegebenen Arbeitsschritt umsetzen.

Für jeden Schritt:

1. Problem, Nutzen und Ausgangszustand dokumentieren.
2. Betroffene Dateien, Schnittstellen und Datenbankänderungen benennen.
3. Umsetzung möglichst klein und isoliert halten.
4. Unit-, Integrations-, Regression- und Fehlerfalltests ergänzen.
5. Ergebnisse durch unabhängige Kontrollrechnungen prüfen, wo Berechnungen betroffen sind.
6. Bestehende Testsuite und relevante Abnahmetests ausführen.
7. Bedienungsanleitung und Tests bei Bedarf aktualisieren.
8. Änderungen, Testergebnisse, Einschränkungen und offene Risiken berichten.
9. Keine nicht geprüften Änderungen direkt in den produktiven Hauptzweig übernehmen.

## Abschlussbericht je Vorschlag

- Vergleichsprogramm und belegte Referenzfunktion
- Bereits vorhandene Implementierung
- Verbleibende Lücke
- Erwarteter Nutzen
- Priorität und Aufwandsschätzung
- Betroffene Module und Daten
- Risiken und Abhängigkeiten
- Testfälle und tatsächliches Ergebnis
- Entscheidung: übernehmen, später umsetzen oder verwerfen

## Reihenfolge der ersten Arbeitspakete

1. Ist-Analyse und Funktionsmatrix erstellen.
2. P0-Reststückverwaltung und Materialoptimierung detailliert planen.
3. P0-Nachkalkulation und Richtwertvorschläge planen.
4. P0-STEP-Prüfstatus und Erkennungssicherheit planen.
5. Erst nach Review die Arbeitspakete einzeln implementieren und testen.

**Wichtig:** Zuerst Analyse und Maßnahmenplan liefern, keine Sammeländerung ausführen. Bestehende Funktionen müssen vor jeder Neuentwicklung im Code gesucht und bewertet werden.
