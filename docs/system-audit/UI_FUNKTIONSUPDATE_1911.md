# Abschlussbericht: Großes UI- und Funktionsupdate (0.9.402)

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
