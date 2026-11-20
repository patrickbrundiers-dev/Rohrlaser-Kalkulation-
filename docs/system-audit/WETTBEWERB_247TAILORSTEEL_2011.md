# Wettbewerbsanalyse 247TailorSteel / Sophia® und Weiterentwicklung (20.11.2026)

Auftrag Patrick 20.11.2026 („MASTER-AUFTRAG – Wettbewerbsanalyse … 247TailorSteel / Sophia®“). Untersucht wurden nur
öffentlich zugängliche Seiten (ohne Anmeldung). Kein Fremdcode, keine Designs und keine Grenzwerte übernommen: Werte
von 247 stehen hier nur als Information; unsere Grenzwerte bleiben je Maschine einstellbar (Thread Importengine/
Fertigbarkeit, PR #598).

Abgrenzung zu laufenden Arbeiten (nicht doppelt gebaut):

| Thema | Zuständig |
|---|---|
| CAD-Import, Bauteilerkennung, Fertigbarkeit mit Grenzwerten je Maschine | Thread Importengine (PR #596 gemergt, #598), `docs/system-audit/IMPORTENGINE_LASERHUB_2011.md` |
| 3D-Viewer, Abwicklung, 3D/2D-Verknüpfung, Explosion | UI-Thread (PR #600, #592) |
| Lernende Kalkulation aus LST | LST-Thread (PR #597) |
| Kundenangebot, interne Kalkulation/Aufschlüsselung, Staffeln mit Mindestmarge, Varianten, Nachkalkulation | Thread Angebotswesen (Auftrag Patrick 20.11. 17:35) |
| Outlook-Anfragen | Outlook-Thread |
| **Bauteil aus Text („Parts Builder“ lokal), Analyse, Matrix** | **dieser Thread** |

## 1. Quellen

| Kürzel | Seite | Stand |
|---|---|---|
| R | https://247tailorsteel.com/en/submission-guidelines/guidelines-for-tube-laser-cutting | Änderungshistorie bis 17.08.2026 |
| S | https://247tailorsteel.com/en/submission-guidelines | ohne Datum |
| B1 | https://247tailorsteel.com/en/about-us/knowledge-centre/blog/design-errors-tubes | 05.12.2025, akt. 27.03.2026 |
| C | https://247tailorsteel.com/en/metalworking/cnc-tube-laser-cutting | ohne Datum |
| M | https://www.247tailorsteel.com/en/machine-park/tube-lasers | ohne Datum |
| A | https://www.247tailorsteel.com/en/sophia/ | ohne Datum |
| U | https://www.247tailorsteel.com/en/sophia/updates | Changelog 2024 – 2026 |
| H | https://247tailorsteel.com/en/about-us/news/parts-builder-order-metal-without-cad | 16.11.2026 |
| P | https://247tailorsteel.com/en/parts-builder, https://247tailorsteel.com/de/parts-builder | ohne Datum |
| I | https://247tailorsteel.com/en/about-us/news/csv-import-renewed | 17.07.2026 |
| L | https://247tailorsteel.com/en/delivery-options | ohne Datum |
| B2 | https://247tailorsteel.com/en/about-us/knowledge-centre/blog/manufacturability-check | 06.10.2025 |
| B3 | https://247tailorsteel.com/en/about-us/knowledge-centre/blog/seam-welds-tubes-sophia | 13.11.2025, akt. 05.01.2026 |
| F | https://247tailorsteel.com/en/support/online-software-sophia (nur Fragentitel) | ohne Datum |
| D | https://247tailorsteel.com/de/ | ohne Datum |

Nicht lesbar: das Sophia-Handbuch (PDF-Link liefert die Startseite), die Antworten der FAQ und alles hinter der
Anmeldung (bewusst nicht versucht). Screenshots von 247 wurden nicht übernommen; die Funktionsanalyse stützt sich auf
die Texte und die dort beschriebenen Abbildungen.

## 2. Funktionsverzeichnis 247TailorSteel / Sophia (öffentlich)

**Neu** = laut Seite 2026, **älter** = bis 2025.

### Rohr- und Profillaser (R, C, M, B1)
- Profile: Rund Ø 12 – 254 mm, Vierkant/Rechteck 12×12 – 200×200 mm; L (EN 10056-1), H/I/U (EN 10365), T (EN 10055)
  werden automatisch erkannt (älter, T-Profil 22.07.2025).
- Wand: Stahl bis 12 mm, Edelstahl bis 6 mm, Alu bis 6 mm. Eckradien Stahl außen 2 × s, innen 1 × s; Alu außen bis
  0,6 mm, innen 0. Max. 40 kg/m. Länge bis 5.800 mm (7.800 auf Anfrage); Mindestlänge 10 mm (R) bzw. 31 mm (C),
  widersprüchlich.
- Löcher/Bearbeitungen mindestens 0,7 × Wandstärke; Toleranzen nach ISO 9013, Rohre nach EN 10219/10210/10305.
- Schneidtechnik 2,5D (Standard), **XY wählbar seit 17.06./17.08.2026 (neu)**, 3D auf Anfrage. XY macht Löcher in
  Rundrohr zylindrisch; Grenze ca. 0,5 × Rohr-Ø.
- U-Profile/Schalen: nur, wenn an einem von 5 Prüfpunkten (Enden, ¼, ½, ¾) der Umfang geschlossen ist
  (**30.06.2026, neu**); Lösung Ring/Brücke.
- Gravur auf Rohren (**31.03.2026, neu**): 0,2 mm tief, Abstand 1,5 mm, nur Umriss, berührt keine Schnittlinie,
  Schrift TC Laser Sans; automatische Gravur des Teilnamens (27.02.2025).
- Blindnietmuttern M4 – M8 (ER, FTTE seit 14.10.2024) nur in Vierkant/Rechteck bis 150×150, Wand 0,5 – 3 mm,
  Mindesthöhe je Typ und Lage, Abstand 2 × s, ein Typ je Auftrag.
- Rohrverbindungen: in 2,5D zeichnen, sonst passen die Teile nicht (07.11.2024).
- Schweißnahtseite im 3D wählen: Vierkant eine Seite, Rechteck zwei (07.06.2025; B3); nicht bei Alu.
- Splash innen wird nicht entfernt; Schneiden im Radius nicht möglich, ≥ 0,1 mm Abstand.

### Sophia (A, U, I, S, D)
- Upload STEP (AP203/214), DXF/DWG, NC1, IGS, TUB; CSV/XML-Import mit Spaltenvorlagen, mehrere Dateien = mehrere
  Projekte (**17.07.2026, neu**). Ohne CAD: Erstellung gegen Gebühr (10.04.2026).
- Automatische Erkennung Blech/Kantteil/Rohr, Baugruppen mit Stückzahlen; Teiletyp von Hand ändern (18.03.2026).
- Prüfung beim Upload, Ampel grün/rot/orange (B2, Abkantteile: 6 Regeln), Lösungsvorschläge mit Wert
  (Biegefehler-Feedback); Ingenieurprüfung anfragen (**09.10.2026, neu**); überlappende Konturen (07.12.2025).
- 3D: Bearbeitungen als „Pins“ wählen, Mehrfachauswahl, Bulk-Editor auch im 3D, Zoom zum Mauszeiger.
- Angebot in < 1 min (Mittel 30 s, ab 90 s Mail), gültig 48 h; Preis hängt vom Liefertermin ab (bis 8 Wochen
  voraus, früher bestellt = günstiger, L); Material erst Dicke, dann Werkstoff mit Preis-/Liefer-Schätzung
  (19.05.2026).
- Neuer Checkout (**18.09.2026**): Teile prüfen, Adresse, Liefertermin und Preis; Angebot Seite 1 nur Teil/Menge/
  Preis, Spezifikationen in der Anlage (**25.09.2026**); Leistungen je Teil (28.08.2026), Sonderbearbeitung je Teil
  sichtbar (10.09.2026).
- Teilebibliothek mit Gruppen (Wiederholaufträge), gesperrte Teile mit Sonderprogramm (08.01.2026), Netto-Preise mit
  Gültigkeit (04.08.2026), Suche im Projekt (30.07.2026), Rechte je Benutzer (17.09.2025).
- Support-Knopf mit Angebots-ID und Fehlercode bei fehlgeschlagener Berechnung (23.06.2026).

### Parts Builder (H, P, F) – **neu, für alle seit 16.11.2026**
- Teil in eigenen Worten beschreiben **oder** Skizze/Foto/PDF hochladen **oder** Vorlage (Blech, Flanschring,
  Verbindungslasche, L-Winkel) mit Maßen, Löchern, Ausschnitten.
- Ergebnis 3D mit Maßen, Biegevorschau; Änderungen per Chat-Satz („Schenkel 200 mm hoch“, „zwei Löcher dazu“) oder
  über Maße; sofortige Herstellbarkeitsprüfung mit Vorschlag; Rückfragen, wenn unklar.
- **Nur Bleche und Kantteile. Rohre, Profile, Baugruppen und Freiformen ausdrücklich nicht** (dafür CAD-Service).
- Cloud-KI (Datenschutzhinweis „#ai“ auf der Seite), Konto nötig.

## 3. Vergleichsmatrix

Bewertung 1 (niedrig) – 5 (hoch). Priorität A = jetzt, B = nächste Runde, C = später/beobachten.

| Funktion | 247TailorSteel | Unsere Software (Stand main 0.9.427) | Verbesserung | Nutzen | Aufwand | Mehrwert € | Risiko | Prio |
|---|---|---|---|---|---|---|---|---|
| CAD-Import | STEP/DXF/DWG/NC1/IGS/TUB, CSV/XML-Vorlagen | STEP, ZIP/Ordner, DXF Blech+Rohr, PDF-Zeichnung, TRUMPF LST/TUBX, Kunden-CSV (#596) | DWG/NC1/IGS nicht nötig (Kunden liefern STEP); CSV-Vorlagen gibt es | 2 | 3 | 2 | 2 | C |
| Bauteilerkennung | Blech/Kant/Rohr, Normprofile, Typ von Hand | 11 Kategorien mit Konfidenz, Ovalrohre, Normprofile, Schweißbaugruppen zerlegen, Normteile, Dubletten (#596) | gleichwertig bis besser; U-Profil-5-Punkte-Regel als Prüfidee an Import-Thread | 3 | 2 | 2 | 1 | B |
| Herstellbarkeitsprüfung | Ampel, Regeln Biegen, Lösungsvorschläge | Prüfdialog + Fertigbarkeit L1 je Maschine (#598), Kantbarkeit Blech, DFM-Regeln | Blindniet-Regeln, Gravur 1,5 mm/Schnittlinie, Ø ≤ 0,5 D im Rundrohr als Prüfideen gemeldet | 4 | 2 | 3 | 1 | B (Import-Thread) |
| 2,5D/XY-Schneidtechnik | wählbar je Teil (neu 2026) | Bohrung im Rundrohr als Kontur auf der Außenhaut (S14), keine Wahl | Wahl 2,5D/XY je Position mit Wirkung auf Schneidweg/Zeit | 3 | 3 | 2 | 2 | B (Import-/UI-Thread) |
| 3D-Viewer/Editor | Pins, Bulk-Edit im 3D, Nahtseite | Viewer+Editor mit Messen, Schnitt, Explosion, Kanten, Naht per Klick, Konturwerkzeuge | weitgehend weiter als 247 | 3 | 4 | 2 | 3 | – (UI-Thread) |
| **Parts Builder** | Text/Skizze/Vorlage → Blechteil, Cloud | Rahmen-Assistent, Rohrzug aus Punkten, Blech-Editor (alles Formulare) | **Bauteil aus Text: Rohrrahmen, Gestelle, Streben, Platten + Blechteile, lokal, Änderungen per Satz** | 4 | 3 | 4 | 2 | **A (gebaut)** |
| Kalkulation | Sofortpreis, Formel nicht öffentlich, Preis je Liefertermin | volle Kalkulation, Preisaufbau, Kostenwasserfall, Bausteine, Eilzuschlag, Staffeln, Preis-Simulator | Aufschlüsselung/Staffeln/Mindestmarge im Thread Angebotswesen | 4 | 4 | 4 | 3 | – (Angebots-Thread) |
| Liefertermin ↔ Preis | Preis hängt vom gewählten Termin ab | Eilzuschlag bei zu frühem Wunschtermin, Lieferzeit-Vorschlag aus Auslastung | Preis je Liefertermin (Termin-Staffel) als Idee an Angebots-Thread | 3 | 3 | 3 | 2 | C |
| Angebotsworkflow | Checkout, Anlage mit Spezifikation, Teilebibliothek | Anfrage → Angebot → Auftrag → Fertigung → Versand (P1-P7), Angebotsakte, Wiederholteile, PPEASE-Ablage | gleichwertig; Spezifikation in Anlage im Angebots-Thread | 3 | 2 | 2 | 1 | – |
| KI-Funktionen | Parts Builder (Cloud-KI), „KI-Steuerung“ der Anlagen | regelbasiert ohne Cloud: Erklärung Rechenweg, Lernen, Vorschläge, LST-Lernsystem (#597) | Bauteil aus Text regelbasiert, nachvollziehbar, offline | 4 | 3 | 3 | 2 | A (gebaut) |
| Mehrbenutzer/Rechte | Firmenkonto, Rechte je Benutzer | PostgreSQL je PC + Abgleich, Rollen, Hauptadmin | 10–25 Benutzer laut Auftrag: braucht Server-Betrieb (Server-Sync auf Eis, Patrick 14.11.) | 4 | 5 | 3 | 4 | C (Entscheidung Patrick) |

## 4. Umgesetzt in diesem Thread: Bauteil aus Text (0.9.429)

Warum zuerst: der Parts Builder ist die neueste 247-Funktion (16.11.2026) und genau dort, wo 247 aufhört (Rohre,
Profile, Baugruppen), liegt unser Geschäft. Bei uns gab es Rahmen-Assistent und Rohrzug nur als Formulare.

- `programm/rohrlaser/bauteil_generator.py` (ohne Qt): `lesen` (regelbasiert, Zahlwörter, Einheiten m/cm, Ø,
  Werkstoffwörter, Klassen über das nächste Schlüsselwort), `aendern` (nur Genanntes überschreibt), `bauen`
  (rahmen.bauen + Querstreben senkrecht/waagrecht/Bodenstreben mit Stößen + Befestigungsplatten mit Lochbild und
  Einbaulage; Blechteile Lasche/L-Winkel/Flanschring), Prüfungen, `vorschau` (3D in Einbaulage).
- `programm/rohrlaser/bauteil_generator_dialog.py`: Fenster mit Vorlagen, Beschreibung, Änderungsfeld, Verlauf mit
  Zurücknehmen, Werkstoffe Rohr/Blech, Stück, Bericht (Teile, Fehler rot, Annahmen und Hinweise orange, Erkannt,
  Nicht verstanden), 3D rechts, „Fehlendes Profil anlegen …“.
- `AngebotSeite.bauteil_aus_text`: Rohre über `_rohre_als_satz` (wie Rahmen-Assistent; neu: Profil je Teil für
  Streben aus anderem Rohr), Platten über `_blech_anlegen` im selben Satz, Beschreibung/Verlauf/Annahmen in
  `angebote.satz_daten[Satz].generator` bzw. in den Blech-Eingaben (`generator`). Danach Satz in 3D.
- Neue Position → „Bauteil aus Text“ (`neue_position.TEXT_BAUTEIL`).
- Keine Datenbankänderung (Schema bleibt), keine Kalkulationsformel geändert, nichts ohne „Übernehmen“.

Annahmen (immer im Fenster angezeigt): Ecken Gehrung (Rahmen) bzw. stumpf (Gestell), Streben senkrecht, Platten
unten, Platte ≥ 100 mm bzw. Profil + 60 mm, Dicke 8 mm, je Platte 4 × Ø 13 (M12), Blechteile 5 mm, Bohrung Ø 9.
Grenzen: keine Freiformen, keine Bögen, kein Knickrahmen (Rahmen-Assistent), keine Skizzen-/Fotoerkennung, keine
Gehrung am Gestell, Vierkant-Streben nicht an Rundrohr, Platten im Satz in 3D nicht mit dargestellt (nur im
Generator-3D und im Blech-Editor).

Tests: `tests/test_bauteil_generator.py` (in `tests/alle.py`), angepasst `tests/test_schneidweg.py` (Typenliste).
Lokal grün: test_bauteil_generator, test_rahmen_assistent, test_satz3d, test_paket_k, test_blech_editor,
test_baugruppe_vorschlaege, test_schneidweg, test_anleitung. Gesamtsuite läuft im CI-Check `tests`.

### 4b. Stufe 2 (Patrick 20.11.2026 18:05 UTC „Alles einbauen nach Empfehlungen“)

- **Rückfragen** (`plan["rueckfragen"]`): Ecken, Strebenrichtung, Plattengröße, Plattenbohrungen, Seite der
  Rohrbohrungen, Pfosten gesamt/zusätzlich, Geländerhöhe, fehlendes Profil (`naechste_profile`: 3 nächste
  vorhandene gleicher Form). Jede Antwort ist ein Änderungssatz und läuft durch `aendern` (Verlauf).
- **Bohrungen in Rohren**: „je 2 Bohrungen Ø 9 in den Querstreben / im Handlauf / im oberen Rohr / in allen Rohren“,
  „von oben“, „durchgehend“ → Konturen `{art: Bohrung, anzahl, d, x, abstand, seite, q}`; Teilung L / (n + 1);
  Prüfung Ø gegen Rohrseite − 2 × Wand − 2 mm, Steg < Ø, Abstand zum Ende. Oberes/unteres Rahmenrohr werden dann
  getrennte Positionen.
- **Geländer** (Handlauf, Untergurt, Endpfosten, Zwischenpfosten/Füllstäbe, Ecken stumpf) und **Tischgestell**
  (Beine, Mittelstrebe). „Länge“ bzw. „2000 lang“ = Breite bei Rohrteilen.
- **Satz per Text ändern** (Rechtsklick, nur Sätze mit `satz_daten[Satz].generator`): Verlauf wird abgespielt,
  Übernehmen ersetzt die Positionen des Satzes (gleicher Name, Rückgängig). Satz in 3D behält jetzt die
  Generator-Daten beim Speichern.
- Grenzen: Rahmen/Geländer liegen in der Vorschau wie im Rahmen-Assistenten; Bohrungen nur gleichmäßig verteilt;
  Handänderungen an alten Positionen gehen beim Ersetzen verloren (Titel des Fensters sagt es, Rückgängig möglich).

## 5. Entwicklungsplan (nächste 1 – 3 Schritte)

1. **Bauteil aus Text Stufe 2** (GEBAUT, siehe 4b; offen nur Leiter, Platten seitlich/Wandmontage): Rückfragen statt Annahmen bei wichtigen Lücken,
   weitere Formen (Rohrzug/Geländer per Text über rohrzug.py, Leiter, Tischgestell mit Mittelstrebe), Platten
   seitlich/Wandmontage, Bohrungen in Rohren per Text („2 Bohrungen Ø 9 im Querrohr“), Generator-Satz später erneut
   öffnen und per Satz ändern.
2. **Prüfideen an den Import-/Fertigbarkeits-Thread** (gebaut dort in PR #604): Blindnietmuttern-Regeln, U-Profil-
   Prüfpunkte, Gravurabstand/Schnittlinie, Lochgrenze Rundrohr; Schneidtechnik 2,5D/XY je Position.
3. **Ideen an den Angebots-Thread**: Preis je Liefertermin (Termin-Staffel), Spezifikationen als Anlage zum Angebot.

Offen bei Patrick: Mehrbenutzerbetrieb mit 10 – 25 Benutzern und Serverbetrieb widerspricht der Entscheidung
„PostgreSQL je PC, kein zentraler Server“ (19.11.); das bleibt so, bis Patrick es neu entscheidet.
