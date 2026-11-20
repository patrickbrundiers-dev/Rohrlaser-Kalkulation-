# Importengine nach Laserhub-Vergleich (20.11.2026)

Auftrag Patrick 20.11.2026: „Laserhub analysieren – CAD-Import, Bauteilerkennung und automatische Geometrieanalyse“.
Umgesetzt in 0.9.425 (PR „Importengine“). Dieses Dokument enthält Phase 1 (Funktionsanalyse Laserhub), Phase 2
(Vergleich mit dem Stand der Rohrlaser-Kalkulation), Phase 3 (technisches Konzept), den umgesetzten Stand und die
Testergebnisse.

Grundlage für Laserhub sind ausschließlich öffentlich zugängliche Seiten (ohne Anmeldung, ohne Formulare, Stand
20.11.2026). Es wurde kein Laserhub-Code und keine geschützte Implementierung übernommen; die Lösung ist eigen und baut
auf der vorhandenen STEP-Messung (OpenCascade) auf.

## 1. Laserhub: sichtbare Funktionsweise (Phase 1)

| Thema | Was Laserhub öffentlich beschreibt | Quelle |
|---|---|---|
| Dateiformate | Rohrlaserteile: STEP/STP, SLDPRT, CATPART. Blech: zusätzlich GEO, DXF, DWG. Zerspanung: zusätzlich IPT, PRT, JT, S3D. IGES nicht genannt | laserhub.com/plattform/faq/, …/richtlinien-rohrlaserteile/ |
| Mehrfach-Upload | mehrere Dateien per Drag & Drop ins Browserfenster; ZIP wird entpackt, jede Datei einzeln | FAQ |
| Anforderungen an die Datei | „Das Bauteil ist ein Volumenkörper“, Einheit mm, einheitliche Farbe; keine Gewindebohrungen, Senkungen, Fasen, Blindlöcher im Modell (kommen über Konfiguration/Zeichnung) | richtlinien-rohrlaserteile |
| Verarbeitung | Sofort-Angebot „in Sekunden“ bzw. „wenigen Minuten“; Machbarkeit bei Rohr sofort geprüft; sonst „Angebot anfragen“ (72 h) | rohrlaserschneiden/, FAQ |
| Bauteilart | wird automatisch erkannt (Blech, Rohr, CNC); falsch erkannt → manuell über das Kästchen an der Position umstellen, Vorschaubild nennt mögliche Gründe, CAD-Korrektur-Service | FAQ |
| Rohrprofile | über 700 Profilvarianten: rund (Ø 10–254 mm, Wand ≤ 12,5), quadratisch (6–200, ≤ 10), rechteckig (10–220, ≤ 10); Oval-, U-, L-, Sonderprofile erwähnt; Länge 12–5890 mm | rohrlaserschneiden/, 3d-schnitt/ |
| Schnitte | 2D (Kopf senkrecht) und 3D mit Gehrungen/Schrägschnitten bis ±45° | 3d-schnitt/, 2d-schnitt/ |
| Merkmale | Gravuren werden automatisch erkannt (≥ 0,2 mm tief); Gewinde und Senkungen: Anzahl in der Konfiguration, Maße in der PDF-Zeichnung; Werkstoff und Stückzahl wählt der Kunde | FAQ, gewinde/, senkungen/ |
| Konstruktionsregeln | Loch ≥ 0,7 × Wand (bis Ø 6), Stege/Schlitze ≥ 0,7 × Wand, Eckradien ≥ 0,3 mm, Kastenprofile mit Radien (Analyse), Genauigkeit ±0,1 mm, max. 225 kg je Teil | richtlinien-rohrlaserteile |
| Baugruppen | „Upload & Fertigung der Einzelteile, ohne Montage“; gemischte Warenkörbe; Aufteilung in Aufträge je Teileart. Ob eine Mehrkörper-STEP automatisch zerlegt und gleiche Teile gruppiert werden: **nicht öffentlich beschrieben** | rohrlaserschneiden/, FAQ |
| Ablauf | Upload → Spezifikation (Material, Weiterbearbeitung) → Preise berechnen → Liefertermin → Angebot (PDF) → Bestellung; 5-Schritt-Ablauf nur als Bild | FAQ, rohrlaserschneiden/ |
| Toleranzen | DIN ISO 2768-1, DIN EN ISO 9013-1 | toleranzen/ |

**Nicht öffentlich**: Erkennungsalgorithmen, Konfidenzwerte, wie Bohrungen/Konturen intern klassifiziert werden,
Fehlertexte bei defekten Dateien, Umgang mit Mehrkörper-Dateien. Diese Punkte werden hier nicht vermutet.

**Einordnung**: Laserhub ist ein Fertigungsmarktplatz. Die Erkennung dient dem Sofortpreis eines Einzelteils;
Gewinde, Senkungen und Fasen werden bewusst nicht aus dem Modell gelesen, sondern konfiguriert. Unsere Kalkulation
ist ein Werkzeug der Arbeitsvorbereitung und liest diese Merkmale aus der Geometrie (mit Bestätigung).

## 2. Vergleichsmatrix (Phase 2)

Aufwand: S ≤ 1 Tag, M 1–3 Tage, L > 3 Tage. „Neu“ = in 0.9.425 umgesetzt.

| Bereich | Laserhub (sichtbar) | Eigene Software vorher | Fehlte | Lösung / Stand 0.9.425 | Aufwand |
|---|---|---|---|---|---|
| CAD-Import | STEP, SLDPRT, CATPART | STEP und IGES (OpenCascade), Flächenmodelle genäht, Einheit, Geometrieprüfung, Zeitlimit je Körper, Cache, Vorab-Übersicht | Herstellerformate wurden still übergangen | **Neu**: SLDPRT/SLDASM, CATPart/CATProduct, IPT/IAM, PRT/ASM, X_T/X_B, SAT, JT, 3DM, F3D, STL/OBJ werden erkannt und als rote Zeile „nicht lesbar – bitte als STEP speichern“ gemeldet. Lesen dieser Formate braucht Herstellerkerne (Lizenz) – bewusst nicht | S |
| Mehrfachimport | Drag & Drop, mehrere Dateien | Mehrfachauswahl, Drag & Drop von Dateien/Ordnern, alle Dateien in einer Liste | Dubletten mehrfach gemessen | **Neu**: gleicher Inhalt (SHA-256) wird einmal gemessen, Hinweis im Bericht | S |
| ZIP-Import | ZIP entpackt | ZIP nur über den Mail-/Anfrageweg | ZIP im Angebot, Dateidialog | **Neu** `cad_import.py`: ZIP und ZIP in ZIP (3 Ebenen), Schutz vor Zip Slip, Größen-/Anzahlgrenze, verschlüsselt/defekt gemeldet; entpackt je Benutzer im Temp-Ordner (bleibt für Angebotsordner und „Neu einlesen“) | S |
| Fehlerhafte Dateien | Fehler + mögliche Gründe | defekte STEP → „nicht erkannt“, nie Absturz | leere Datei, kein STEP-Kopf, abgebrochene Übertragung | **Neu**: Vorprüfung (Kopf/Ende), rote Zeilen und Importbericht „Import …“ | S |
| Bauteilerkennung | Blech/Rohr/CNC automatisch, manuell umstellbar | zentrale Art-Entscheidung (Blech, Rohr/Profil, Dreh-/Frästeil) mit Regelliste und Grund, alle Arten wählbar, gelernte Wahl (ART_GELERNT), Prüfsammlung der Korrekturen | einheitliche Kategorie über alle Arten | **Neu** `bauteil_analyse.kategorie`: 11 Kategorien (Rund-, Vierkant-, Rechteck-, Ovalrohr, Sonderprofil, offenes Profil, Rohrlaser-Baugruppe, Blech, Fräs, Dreh, Sonstiges) aus der bestehenden Messung | S |
| Profilidentifikation | >700 Profile, rund/quadr./rechteckig | Rund, Quadrat, Rechteck, offene Profile (L, U, C, T, I/H, Flach), RP-Profile, Normprofile, Mehrkammer | Ovalrohre wurden „Sonderprofil, Fläche manuell prüfen“ | **Neu** `step_geometrie._ovalform`: Flachoval, Halbflachoval, Elliptisch über Fläche und Umfang der Außenkontur (±0,5 %) und gleichmäßige Innenkontur; Zuordnung zum Stammdatenprofil (`finde_profil`) | M |
| Geometrieanalyse | Sofortpreis aus Schnittzeit, Material, Größe | Profil, Wand (mehrere Messstellen), Länge, Querschnitt, Volumen, Achse, Schneidweg, Einstiche, Enden, Gegenprobe gegen das Editor-Modell | Kennzahlen gebündelt, Komplexität | **Neu** `kennzahlen`: Volumen, Richtgewicht, Bohrungen, Ausschnitte, Gravuren, Einstiche, Komplexität (einfach/mittel/komplex) | S |
| Bohrungserkennung | nicht beschrieben; Gewinde/Senkung manuell | Bohrungen inkl. schräg, im Eckradius, Doppelbohrung, Sackbohrung, Fließloch, Senkung, Gewinde-Vorschlag aus Kernloch | einheitliche Merkmalliste | **Neu** `merkmale`: jede Bohrung mit Lage x/Seite, Ø, Orientierung, Schnittlänge, Bearbeitung, Konfidenz; Gewinde als Annahme (70 %) | S |
| Konturerkennung | Gravuren automatisch | Langloch, Rechteck, Polygon, Sonderkontur, Freiform, Gehrung, Stirnausschnitt, Gravur, Gegenprobe 100 % wie STEP | Schlitz/Durchbruch/Schrägschnitt benannt | **Neu**: Merkmale Schlitz, Durchbruch, Konturausschnitt, Freiformkontur, Gehrungsschnitt, Schrägschnitt (um zwei Achsen), Stirnausschnitt, Fräsung, Fase | S |
| Baugruppenzerlegung | Einzelteile fertigen; Zerlegung nicht beschrieben | Mehrkörper-STEP, Struktur (Knoten), gleiche Teile in einer Zeile, Satz nur auf Knopfdruck, Schweißbaugruppe mit Nahtkandidaten | eine vollständige Bauteilliste mit Varianten und Materialbedarf | **Neu** `baugruppe_analyse`: Positionen mit Stückzahl je Knoten, Varianten (gleiches Profil, andere Länge/Bearbeitung), Verbindungen (Stoßart, Länge), Materialbedarf je Profil, CSV; Rohrlaser-Baugruppe nur bei sich berührenden Rohren | M |
| Automatische Kalkulation | Sofortpreis | Übernahme in Positionen, Laserzeit, Material, Zusatzarbeiten, Angebots-Check | Ergebnis der Erkennung je Position gespeichert | **Neu**: Analyse in `positionen.step_merkmale["analyse"]` (einmal beim Übernehmen), lesbar über `bauteil_analyse.aus_position` | S |
| Manuelle Korrektur | Bauteiltyp umstellen, CAD-Service | Art, Profil, Werkstoff, Artikel je Zeile; „Passt“; Korrekturprotokoll; Lernen | Gesamtsicht mit Konfidenz | **Neu**: Schrittleiste, Erkennungszeile, Fenster „Importanalyse“; Korrekturen weiter im Prüfdialog (kein zweiter Weg) | M |

## 3. Technisches Konzept (Phase 3)

```
Dateien/Ordner/ZIP ──► cad_import.vorbereiten ──► STEP-Import.exe (step_messen, step_geometrie, step_arten)
   (entpacken, Formate,      (Messwerte je Körper: Profil, Wand, Länge, Konturen, Struktur, Nähte, Sicherheit)
    Dubletten, Vorprüfung)                │
                                          ▼
                    step.ampel (eine Entscheidung: grün/gelb/rot)  ◄── Prüfdialog (Korrektur, Lernen)
                                          │
                                          ▼
                 bauteil_analyse.analyse (Kategorie, Konfidenz, Merkmale, Kennzahlen) – nur abgeleitet
                 baugruppe_analyse.alle  (Bauteilliste, Varianten, Verbindungen, Materialbedarf)
                                          │
                                          ▼
              step.uebernehmen → Position (step_merkmale: ampel + analyse) → alle Module lesen dort
```

Grundsätze:

1. **Kein paralleles Erkennungssystem.** Geometrie wird nur in der STEP-Messung gerechnet. Die Analyse leitet
   ausschließlich ab (Messwerte, Sicherheit je Merkmal, Ampel). Neue Erkennung (Ovalrohre) gehört in die Messung.
2. **Eine Entscheidung, eine Zahl.** Die Stufe (sicher/prüfen/unsicher) ist immer die Erkennungs-Ampel. Die
   Konfidenz in % erklärt sie (Abzüge mit Grund) und liegt immer im Band der Ampel.
3. **Unsicheres nie unbemerkt.** Gelbe Teile bleiben gelb bis „Passt“/Bestätigung; der Angebots-Check meldet nicht
   bestätigte (bestehende Regel L4). Gewinde aus dem Kernloch ist eine Annahme (70 %).
4. **Einmal ermitteln.** Analyse je Teil einmal (`_analyse`), beim Übernehmen nach den Korrekturen neu und mit der
   Position gespeichert; danach lesen alle Module die gespeicherte Fassung.
5. **Regeln von Patrick bleiben**: Rohre mit Gravur immer Rohr; mehrere Teile nie automatisch Satz (lose Teile sind
   „mehrteilig“, nicht „Rohrlaser-Baugruppe“); Konturen 100 % wie STEP; Bauteile werden nie verschoben.

Module (neu): `cad_import.py`, `bauteil_analyse.py`, `baugruppe_analyse.py`, `importanalyse_dialog.py` (alle ohne
eigene Geometrie). Geändert: `step_geometrie.py` (Ovalform), `step_ergebnis.py` (HOHL), `step.py` (ZIP in
`step_dateien`, Filter, `finde_profil`/`MIT_B` für Ovale, Importbericht), `angebot_fenster.py` (Vorbereitung vor der
Messung, Ablegen), `step_dialog.py` (Schrittleiste, Knopf, Erkennungszeile), `step_pruefung.py` (Analyse speichern).

### Bewusst nicht umgesetzt (mit Grund)

- **SLDPRT/CATPART lesen**: proprietär; ohne lizenzierten Herstellerkern (z. B. Parasolid/CGM, kommerzielle
  Konverter) nicht zuverlässig möglich. Klare Meldung statt Teilergebnis.
- **Sofortpreis im Import**: die Kalkulation rechnet nach dem Übernehmen wie bisher (mit Maschine, Staffeln,
  Zusatzarbeiten); ein zweiter Preisweg wäre eine Doppelrechnung.
- **Lernen aus Korrekturen**: besteht schon (Art und Profil gelernt, Prüfsammlung); die Kategorie folgt daraus.

## 4. Umsetzung (Phasen 4–7)

| Phase | Inhalt | Stand |
|---|---|---|
| 4 CAD-Import | ZIP (verschachtelt, Schutz), Herstellerformate gemeldet, leere/kaputte/unvollständige STEP, Dubletten, andere Dateien | fertig |
| 5 Erkennung | Ovalrohre in der Messung; 11 Kategorien; Merkmalliste mit Lage/Abmessung/Orientierung/Länge/Bearbeitung; Konfidenz | fertig |
| 6 Baugruppen + Übergabe | Bauteilliste je Datei, gleiche Teile, Knoten, Varianten, Verbindungen, Materialbedarf, CSV; Analyse in der Position | fertig |
| 7 Oberfläche | Schrittleiste ①–⑥ im Prüfdialog (gleiche Zahlen wie die Ampel), Erkennungszeile, Fenster „Importanalyse“ | fertig |
| 8 Tests | siehe 5. | fertig |

## 5. Testkatalog und Ergebnisse (Phase 8)

`tests/test_importengine.py` (ohne Datenbank) und `tests/test_importengine_ablauf.py` (mit Datenbank und Fenster).
Neue Testteile in `tests/step_importengine/` (erzeugt mit `tests/importengine_teile.py`).

| Fall aus dem Auftrag | Testteil | Referenz | Ergebnis |
|---|---|---|---|
| Einfaches Rundrohr | T01 RR 42,4 × 2 L 1250 | Profil, Maße, Länge | OK |
| Vierkantrohr mit Bohrungen | T03 QR 40 × 3 L 2150, R05 | 1 Bohrung Ø 8 | OK |
| Rechteckrohr mit Langlöchern | R06 RE 40 × 30 × 3 L 920 | 6 Bohrungen, 4 Langlöcher | OK |
| Komplexe Konturausschnitte | R01/R02/R05 Freiform, T07 Stirnausschnitt + Gravur | Stirnausschnitt, Gravur, Gewinde-Vorschlag M6 | OK |
| Gehrungsschnitt | T04 RE 60 × 40 × 3, R08 Rahmen | Gehrung 45° | OK |
| Mehrere identische Bauteile | I05 (48 Körper) | 24/16/8 in 3 Positionen | OK |
| Komplette Schweißbaugruppe | S03, S04 (mit Unterbaugruppe) | 11 Körper → 3 Positionen (4/5/2), Knoten, ≥ 10 Verbindungen, 8420 mm QR 40 × 3 | OK |
| Baugruppe mit verschiedenen Profiltypen | S01, I06 (QR, RR, Blech, Frästeil), T08 | Kategorien je Teil | OK |
| Große Baugruppe | I05 (48 Körper, 2,6 MB) | Messung im Gesamtlauf; Gruppierung | OK |
| Fehlerhafte/unvollständige Dateien | leer, kein STEP, halbe STEP, defektes ZIP, SLDPRT, CATPart, IPT | Befund, kein Absturz | OK |
| Ovalrohre (neu) | I01 Flachoval 60 × 30 × 2 mit 2 × Ø 8, I02 Elliptisch, I03 Halbflachoval 80 × 30 × 2 | Form, Maße, Wand 2,0, Profilzuordnung | OK (vorher Sonderprofil) |
| Offenes Profil | I04 L 50 × 30 × 4 | L-Profil | OK |

Abweichungen gegen die Referenzmaße: keine (Toleranz 0,15 mm). Messung aller 26 Dateien / 108 Körper: rund 17–19 s im
Cloud-Container (4 Kerne). Einschränkungen: Halbflachoval mit nicht gleichmäßiger Innenkontur (Innenkontur nur
verkleinert statt versetzt) bleibt mit „Wandstärke nicht einheitlich“ gelb – so ist es auch richtig.

## 6. Nachtrag: weitere Übernahmen (Patrick 20.11.2026 „Alles einbauen nach Empfehlungen“)

Plan: Claude-Doc „Plan: Weitere Übernahmen aus dem Laserhub-Vergleich“. Grenzwerte je Maschine.

| Paket | Laserhub (öffentlich) | Umsetzung | Version | Tests |
|---|---|---|---|---|
| L1 Fertigbarkeit | Loch und Steg ≥ 0,7 × Wand, Eckradius ≥ 0,3 mm, Länge, Gewicht | `fertigbarkeit.py`: Loch/Schlitz, Steg zwischen Konturen derselben Wand und zum geraden Ende (Abstand der Umrisse in der Abwicklung), scharfe Innenecken (nur mit Grenzwert, Vorgabe aus), Länge (Stange − Endbeschnitt − Greiferrest, kürzestes Teil), Hüllkreis. Maschinenfelder `fb_*` (Schema 97). Nur gelb mit Grund, Teil unverändert; Angebots-Check-Hinweis | 0.9.427 | `test_fertigbarkeit.py` F1–F7, Ablauf A4 |
| L3 Gravur | Gravuren ab 0,2 mm Tiefe erkannt | Gravur tiefer als `fb_gravur_tiefe` (Vorgabe 0,5 mm wie die Messung) = Hinweis „tiefer nur gefräst“; Rohr bleibt Rohr (Regel 17.11.) | 0.9.427 | F1 |
| L6 Dateianforderungen | Volumenkörper, mm, eine Farbe | Reiter Dateien: Körper, Volumenkörper/genäht/offen, Einheit, Geometrie, Bewertung | 0.9.427 | F5 |
| L2 Merkmal im 3D | Vorschaubild nennt mögliche Gründe | Importanalyse mit 3D-Ansicht, Merkmal markiert (x0/x1 aus dem Umriss), „Nächstes zu prüfen“. Hauptviewer und Abwicklung: Thread „3D-Viewer und Abwicklung“ liest dieselben Felder | 0.9.427 | `test_importanalyse_3d.py` Z1–Z2 |
| L4 Gewinde mit Zeichnung | Gewinde/Senkungen aus der Zeichnung | Abgleich Kernloch-Vorschlag ↔ Zeichnung/Formular: bestätigt 95 %, Anzahl abweichend 70 %, nur Zeichnung 60 % | 0.9.427 | Z3 |
| L5 Zukauf je Teileart | Aufteilung des Warenkorbs je Teileart | war schon da (Materialanfrage mit Gruppen Blechteile, Dreh-/Frästeile, mit Zeichnung/DXF/STEP); neu nur der Hinweis in der Importanalyse | 0.9.427 | Z4 |

Prüfung gegen den Bestand: kein einziger Fehlalarm an den 87 Teilen aus `tests/step*` (Grenzwerte Vorgabe).
