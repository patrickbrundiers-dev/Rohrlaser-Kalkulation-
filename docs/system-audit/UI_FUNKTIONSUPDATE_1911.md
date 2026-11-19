# Abschlussbericht: Großes UI- und Funktionsupdate (0.9.404)

Auftrag Patrick 19.11.2026 („3D-Editor modernisieren | Einstellungen erweitern | Neue Funktionen entwickeln“).
Arbeitsweise: erst Bestand geprüft, nur Lücken geschlossen, nichts doppelt gebaut. Priorität 4 (Performance,
Stabilität, Datenbank, Tests) macht parallel der Thread „Großes System-Update für Tempo und Stabilität“, die
Dokumentenablage nach Angebotsnummer der Thread „Dokumente nach PPEASE-Angebotsnummer ablegen“.

Legende: **V** = vollständig umgesetzt, **T** = teilweise umgesetzt, **O** = noch offen.
„schon da“ = vor diesem Update vorhanden (Version in Klammern), hier nur geprüft.

## 1. 3D-Editor (Priorität 1)

| Anforderung | Stand | Wo |
|---|---|---|
| Zentrale 3D-Fläche, Werkzeugleiste, Eigenschaften rechts, Statuszeile unten, Panels ein/aus, Layout gemerkt | V (schon da, 0.9.400) | `editor_arbeitsbereich.py`, `teile_editor.py` |
| Dark/Light Mode | V (schon da) | `stil.py` (Hell, Dunkel, wie Windows) |
| Freie Rotation, Verschieben, Zoom, Standardansichten, Isometrie, auf Auswahl, einpassen | V (schon da) | `ansicht3d.py`, `ansicht3d_leiste.py`, Ansichtswürfel |
| Schnittansicht, Transparenz, Drahtgitter, verdeckt gestrichelt | V (schon da) | Darstellung, `editor_schnitt.py` |
| Bauteile ein-/ausblenden, isolieren, Mehrfachauswahl (Strg, Fenster) | V (schon da, 0.9.294) | `auswahl3d.py` |
| Flächen, Kanten, Punkte, Körper wählen, Konturen wählen | V (schon da) | `auswahl3d.py`, Teile-Editor |
| **Alle wählen (Strg+A), Auswahl umkehren (Strg+I)** | **V neu** | `auswahl3d.Auswahl.alle_waehlen/umkehren` |
| **Auswahlgruppen erstellen/wählen/entfernen** | **V neu** (gelten je offenem Fenster) | `auswahl3d.Auswahl.gruppe_*`, Menü Auswahl |
| **Rechtsklick-Menü in allen 3D-Fenstern** | **V neu** (Fenster mit eigenem Menü behalten es) | `Ansicht3D.standard_menue` |
| Messen: Abstand, Kante, Winkel, Ø, Radius, Wandstärke, Koordinaten, Kontur-Abstände | V (schon da, 0.9.390/0.9.400) | `messen3d.py`, Statuszeile |
| Konturen verschieben, kopieren (duplizieren), spiegeln, drehen (Seite), Eckpunkte, Vorlagen | V (schon da) | `editor_griffe.py`, `editor_mehrfach.py`, `eckpunkte_dialog.py`, `konturvorlagen.py` |
| **Konturen prüfen: doppelte, überlappende, außerhalb liegende** | **V neu** | `dfm._konflikte` (Regeln abschaltbar unter Prüfregeln) |
| Offene Konturen erkennen | T | Konturen des Programms sind geschlossene Formen; offen sind nur Schlitz/Ausklinkung (gewollt). Offene Linienzüge gibt es nur beim DXF-Import, dort meldet der Import sie schon. |
| Konturen vereinfachen, verbinden | O | Konturen sind Formelemente (Bohrung, Langloch, Rechteck …), keine freien Polylinien; Vereinfachen/Verbinden wäre erst mit freien Konturen sinnvoll. |

## 2. Einstellungen (Priorität 2)

| Anforderung | Stand | Wo |
|---|---|---|
| Zentrale Einstellungsseite mit Kategorien, Suche | V (schon da, 0.9.202, 25 Seiten) | `einstellungen_nav.py`, `einstellungen_ordnung.py` |
| **Favoriten** (☆ je Wert, Seite „★ Favoriten“) | **V neu** | `einstellungen_extras.py`, `einstellungen_extras_dialog.FavoritenSeite` |
| **Beschreibung und Standardwert** je Einstellung (Tooltip: Titel, Standard, erlaubter Bereich) | **V neu** | `einstellungen_extras.beschreibung` |
| **Zurücksetzen je Wert (↺) und je Seite** | **V neu** (Datensicherung vorher, Passwort/Nummern/Kürzel/Ordner/Gesperrtes bleiben) | `EinstellungenSeite.wert_zuruecksetzen/seite_zuruecksetzen` |
| Gesamteinstellungen zurücksetzen | V (schon da, Hauptadmin-Menü) | `einstellungen_sicherung.py` |
| **Export / Import** mit Vorschau, Sperre, Bereichsprüfung | **V neu** (für jeden Arbeitsplatz; Hauptadmin-Sichern bleibt) | `einstellungen_extras.exportieren/importieren` |
| **Änderungsverlauf** der Einstellungen | **V neu** (je Arbeitsplatz, letzte 500) | `einstellungen_extras.verlauf*`, `VerlaufDialog` |
| **Plausibilitätsprüfung**, Warnungen | **V neu** (Bereich, Gewinn > 100 %, hohe Zuschläge/Rüstzeit, Staffelgrenzen) | `einstellungen_extras.pruefen` |
| Wichtige Werte nicht versehentlich überschreiben | V | Admin-Schutz (schon da) + Import/Reset überspringen Gesperrtes |
| **Persönliches Profil** exportieren/importieren | **V neu** | `einstellungen_extras.profil_*` |
| Benutzerprofile bei Benutzerwechsel | T | Jeder Arbeitsplatz hat schon eigene Daten (Kürzel, Layout, Darstellung); Profile lassen sich jetzt als Datei mitnehmen. Mehrere Benutzer an *einem* Windows-Konto mit Umschalten gibt es nicht. |
| Individuelle Tastenkürzel | O | Tastenkürzel sind fest (`tastatur.py`, Befehlspalette Strg+K). |
| Maschinen-/Materialprofile, Schnittwerte, Rüst-/Schweiß-/Nachbearbeitungszeiten, Zuschläge | V (schon da) | Maschinen-Editor, Schneiddaten, Zeitvorgaben, Schweißkennwerte, Zusatzarbeiten |

## 3. Neue Funktionen (Priorität 3)

| Anforderung | Stand | Wo |
|---|---|---|
| **Bauteilprüfung**: doppelte/überlappende/außerhalb liegende Konturen, fehlende Wandstärke, unplausible Abmessung | **V neu** | `dfm.py` (5 Regeln, Vorgabe WARNUNG); im Teile-Editor in den Prüfmeldungen, Klick markiert die Konturen im 3D |
| Weitere Fertigungsprobleme (Steg, Rand, Bohrung, Abfall, Spannbereich …) | V (schon da, 20 Regeln) | `dfm.py` |
| Kalkulationsassistenz (fehlendes Material, ungewöhnliche Werte, fehlende Schritte, Preisabweichung, Vollständigkeit) | V (schon da) | Angebots-Check `angebot_check.py`, `plausibel.py`, `kalk_hinweise.py`, Preiswächter – nur Hinweise, ändert nichts |
| Kalkulationsvergleich | **T → erweitert** | `fassung_vergleich.unterschiede`: jetzt auch Oberfläche, Gewinde, Maschine, Geometrie (Konturen), Arbeitsschritte, Material, Laserzeit, Laserkosten, Zusatzarbeiten, Einstiche. Alte und neue Geometrie nebeneinander im 3D: O |
| **Bauteilbibliothek** (speichern, Kategorien, Favoriten, Suche, wiederverwenden, kopieren, 3D-Vorschau) | **V neu** (auf den Positionsvorlagen aufgebaut, keine zweite Ablage) | `positionsvorlagen.py`, `bibliothek_dialog.py`, Schema 95 |
| Dokumentenausgabe (Angebot, Kalkulation, Zeichnung, 3D, Schnittschema, Material, Stückliste, Version) | V (schon da, 0.9.398 Angebotsakte) | `akte_pdf.py` |
| Zuordnung zur Angebotsnummer | – | Thread „Dokumente nach PPEASE-Angebotsnummer ablegen“ |

## 4. Bedienung

Schon da und geprüft: globale Suche/Befehlspalette (Strg+K), Kontextmenüs, Tastenkürzel, zuletzt benutzte
Profile/Werkstoffe, offene Angebote beim Start, Rückgängig/Wiederholen, automatisches Zwischenspeichern und
Wiederherstellung im Editor, Ladeanzeigen. Neu: Rechtsklick im 3D, Favoriten der Einstellungen.

## 5. Technische Änderungen

- Neue Module ohne Qt: `einstellungen_extras.py`; mit Qt: `einstellungen_extras_dialog.py`, `bibliothek_dialog.py`.
- Erweitert: `auswahl3d.py`, `ansicht3d.py`, `ansicht3d_leiste.py`, `dfm.py`, `fenster.py` (EinstellungenSeite),
  `einstellungen_nav.py`, `positionsvorlagen.py`, `fassung_vergleich.py`, `vorschlaege_mixin.py`, `angebot_fenster.py`.
- Datenbank: Schema 95 = zwei neue Spalten `positionsvorlagen.kategorie/favorit` (leer = wie bisher).
- Favoriten, Verlauf und Profil liegen je Arbeitsplatz in der eigenen Datendatei (nicht im gemeinsamen Ordner).
- Rechnung unverändert: keine Kalkulationsformel geändert; die neuen Prüfregeln sind nur Befunde (WARNUNG).

## 6. Performance

Keine neue Rechnung im Zeichenweg. Die Konfliktprüfung nutzt die schon gebauten Linienzüge der Stegprüfung (Vorauswahl
über Hüllrechtecke) und liegt im vorhandenen Zwischenspeicher von `dfm._rohr`. Messung und Optimierung der übrigen
Abläufe macht der Thread „Großes System-Update für Tempo und Stabilität“.

## 7. Tests

Neu `tests/test_ui_update_1911.py` (U1–U7): Auswahl umkehren/Gruppen, Rechtsklick-Menü, 5 Prüfregeln, Einstellungen
ohne und mit Fenster (Favoriten, Verlauf, Plausibilität, Reset mit Schutz, Import mit Sperre, Profil),
Bauteilbibliothek (Logik und Dialog), Vergleich. Gesamter Lauf `python tests/alle.py`: Ergebnis im Pull Request.

## 8. Bekannte Einschränkungen

- Auswahlgruppen werden nicht in der Datei gespeichert (gelten, solange das Fenster offen ist).
- Plausibilitätsprüfung kennt bisher die wichtigsten Kalkulationswerte, nicht jede der 377 Einstellungen einzeln.
- Persönliches Profil übernimmt keine gemeinsamen Einstellungen (gewollt).

## 9. Offene Entwicklungspotenziale

1. Vergleich zweier Fassungen im 3D nebeneinander (alte/neue Geometrie überlagert).
2. Individuelle Tastenkürzel (Belegung je Benutzer).
3. Auswahlgruppen in Baugruppe/Satz dauerhaft speichern.
4. Freie Konturen (Polylinien) mit Vereinfachen/Verbinden.
5. Plausibilitätsregeln als Tabelle in den Stammdaten (wie die Prüfregeln), vom Admin erweiterbar.

## 10. Nachträge vom 19.11.2026 (gleicher Pull Request)

### 10.1 Erweiterter Entwicklungsauftrag 3D-Editor (15:53)

Bestand geprüft: Formen (Bohrung, Langloch, Rechteck mit Radius/Fase, Schlitz, Ausklinkung, Polygon mit Bögen,
Lochfeld mit Lochkreis/Spirale, Durchbruch, Sattel, Gehrung), Muster (Anzahl × Abstand, Kopien am Umfang),
Skalieren, Spiegeln, Duplizieren, Verschieben, Eckpunkte, Konturen auf anderes Profil (`kontur_umstellen`),
Rückgängig/Verlauf, sichere Rechenfelder (`rechenfeld.py`, kein eval) waren schon da.

| Anforderung | Stand | Wo |
|---|---|---|
| Drehen, Versatz (Offset), Verlängern/Kürzen, Richtung umkehren | **V neu** | `kontur_werkzeuge.py`, Menü *Bearbeiten* |
| Ellipse, Vieleck | **V neu** (als Polygon, Fehler ≤ 0,01 mm) | `kontur_werkzeuge.ellipse/vieleck` |
| Reihe mit verschiedenen Abständen | **V neu** | `kontur_werkzeuge.reihe` |
| Intelligente Auswahl: gleiche Art / Maße / Seite | **V neu** | `kontur_werkzeuge.gleiche` |
| Eingaben als Formel (L, B, H, D, S) | V (Rechenfelder, jetzt auch in allen neuen Abfragen) | `rechenfeld.py` |
| Trimmen, Teilen, Verbinden, Splines, Bedingungen (parallel, tangential …) | O | brauchen freie Skizzenkonturen → CAD-Update (eigener Plan-Thread) |
| Eigene Bearbeitungsregeln / Erweiterungssystem | T | Arbeitsgang- und Merkmalsregeln sind Tabellen; Programmcode von Benutzern wird bewusst nicht ausgeführt |
| Geometrieoptimierung, Konturassistent, Teilevergleich | T | Prüfregeln (dfm), Teilefamilien, Fassungsvergleich vorhanden; 3D-Vergleich offen |

Tests: `tests/test_konturwerkzeuge_1911.py` K1–K6 mit Sollmaßen (z. B. Bohrung Ø 10 + 1 mm Versatz = Ø 12 = 37,70 mm
Schnitt; Polygon 40 × 20 + 1 = 42 × 22 = 128 mm; Ellipse 40 × 20 = Ramanujan 96,88 mm; Sechseck Umkreis 30 = 90 mm).

### 10.2 Artikelnummer gravieren (Patrick 16:00)

Menü *Bearbeiten → Artikelnummer gravieren …* im Rohr- und Blech-Editor: Text = Artikelnummer des Artikels, gefragt
wird nur die Schriftgröße, Lage automatisch mit Sicherheitsabstand (neue Einstellung `gravur_abstand`, Vorgabe 3 mm)
zu Konturen, Enden und Rand; eine vorhandene Artikelnummer-Gravur wird ersetzt; ohne Platz eine Meldung. Rohr:
`step_export.artikel_gravur(…, abstand)`, Blech: `blech.gravur_lage(…, mindest)`. Die Gravur in der Schweißbaugruppe
(`bg_gravur`) rechnet unverändert mit 0,5 mm.

### 10.3 Freie 360°-Drehung (Auftrag 16:05)

**Ursache der Anschläge:** Die gemeinsame Kamera aller 3D-Fenster (`ansicht3d.Ansicht3D`) bestand aus zwei Winkeln;
das Kippen wurde beim Ziehen auf ±1,55 rad (89°) und mit Strg+Pfeil auf ±1,5 rad begrenzt. Über Kopf ging es nicht,
eine Drehung um die Blickachse gab es nicht.

**Änderung:** `navigation3d.py` – die Lage ist eine Drehmatrix aus gier/nick/roll (Rz·Rx·Ry, deckt jede Lage ab).
Beim Ziehen wird die kleine Bildschirmdrehung vor die Matrix gesetzt und wieder in die Winkel zerlegt: kein
Anschlag, kein Rücksprung, keine Gimbal-Sperre. Eine Kamerasteuerung für alle Fenster (STEP-Viewer, Rohr-, Blech-,
Teile-Editor, Baugruppe, Satz), OpenGL und Software gleich; Ansichtswürfel, Achsenkreuz und Auswahl rechnen mit roll.
Tasten Strg+Pfeile 90°, Alt+Pfeile 15°, Strg/Alt+Bild↑↓ um die Blickachse; *Blick → Um Achse drehen …* exakte
Winkeleingabe. Einstellungen je Arbeitsplatz (Einstellungen → 3D-Navigation): Drehart (frei/Drehteller),
Dreh-, Zoom-, Verschiebetempo, Richtung umkehren, Drehzentrum (unter der Maus/Modellmitte/Gewähltes), Nachlauf
(Vorgabe aus). Bauteilkoordinaten werden nie verändert (Test R6).

**Performance:** keine zusätzliche Rechnung beim Drehen (eine 3×3-Matrix je Mausereignis statt bisher ebenfalls
einer); Zwischenspeicher der Projektion und des Bildes enthalten jetzt roll.

Tests: `tests/test_navigation_360.py` R1–R6 (drei volle Umdrehungen langsam und schnell zurück auf exakt dieselbe
Lage, 300 Zufallslagen + genau oben/unten, Maus 180° über Kopf ohne Sprung, Tasten 4 × 90° und 24 × 15° = 360°,
Einstellungen, Geometrie unverändert).

**Offen:** Mausbelegung frei wählbar (fest: links drehen, rechts/mitte verschieben, Rad zoomen); Drehen um einen
frei gesetzten Ursprung (Drehzentrum = Punkt unter der Maus, Mitte oder Gewähltes).

### 10.4 Messsystem und CAD-Update (16:19 / 16:20)

Analyse und Plan nach SolidCraft laufen im Thread „SolidCraft analysieren und CAD-Plan schreiben“; gebaut wird nach
diesem Pull Request (erst Messsystem, dann CAD-Phasen), damit in den 3D-Dateien keine Konflikte entstehen.
