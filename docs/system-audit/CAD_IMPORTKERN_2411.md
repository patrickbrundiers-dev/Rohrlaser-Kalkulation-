# CAD-Importkern: Genauigkeit, Toleranzen, Reparatur, Prüfwerte (24.11.2026)

Master-Auftrag Patrick 24.11.2026 19:45 UTC „STEP-Import und CAD-Importkern auf höchstem technischem Niveau
weiterentwickeln“. Abgrenzung zu den parallelen Threads (nichts doppelt gebaut):

| Thema | wo |
|---|---|
| eigener STEP-Viewer, Konturnummer je 3D-Linie | PR #642 (STEP Engine 2.0) |
| Tempo Rechenkern/Booleans, Lasttests, beschädigte STEPs | PR #643 (Rechenkern 2.0) |
| Schnellimport (nur Linien) | Thread Schnellimport |
| **Genauigkeit, Toleranzverwaltung, Shape Healing mit Protokoll, CAD-Prüfwerte, Importanalyse, Referenztests** | **dieser PR** |

Grundregel bleibt: Konturen 100 % wie die STEP (Lage und Form). Die Messung rechnet weiter mit dem Körper genau wie
gelesen. Neu ist eine Prüf- und Protokollschicht, die sagt, **wie verlässlich** jeder Körper ist.

## 1. Ergebnisse der Online-Recherche

**Open CASCADE Technology (OCCT).** Aktuell ist 8.0.1 (im Programm: cadquery-ocp 8.0.1.1.0, also aktuell). 8.0 bringt
für STEP: DE_Wrapper mit Stream-Lesen/Schreiben, **thread-sicheres STEP-Lesen bei einer Leser-Instanz je Thread**,
kleinere Dateien beim Schreiben, Shape-Healing-Korrekturen in ShapeBuild_ReShape (keine Stapelüberläufe bei geteilten
Teilformen). IGES-Lesen bleibt nicht thread-sicher.
Quellen: [OCCT 8.0.0 Release](https://dev.opencascade.org/content/open-cascade-technology-800-release),
[OCCT 8.0.1](https://github.com/Open-Cascade-SAS/OCCT/discussions/1415).

**STEPControl_Reader / STEPCAFControl_Reader.** Das Programm nutzt bereits STEPCAFControl (Baugruppe, Namen) mit
Rückfall auf STEPControl. Wichtig für die Genauigkeit sind die Leseparameter
([STEP-Benutzerhandbuch](https://dev.opencascade.org/doc/overview/html/occt_user_guides__step.html)):
`read.precision.mode` = 0 (File: Genauigkeit aus der Datei, UNCERTAINTY_MEASURE_WITH_UNIT), `read.precision.val` =
0,0001 mm (nur bei Mode User), `read.maxprecision.mode` = 0 (**Preferred: darf überschritten werden, um die Form gültig
zu halten**), `read.maxprecision.val` = **1 mm**. Das heißt: OpenCascade heilt beim Einlesen (ShapeFix) und darf dabei
Toleranzen still bis 1 mm und mehr vergrößern. Das war bisher unsichtbar.

**Shape Healing / Validierung.** ShapeFix_Shape (Reparatur), ShapeAnalysis_ShapeTolerance (Toleranzen),
ShapeAnalysis_Shell (offene/falsch orientierte Kanten), ShapeAnalysis_Wire (Lücken, Selbstüberschneidung, kleine und
entartete Kanten), ShapeAnalysis_ShapeContents (Freiformflächen), BRepCheck_Analyzer (Gültigkeit)
([Shape Healing Guide](https://dev.opencascade.org/doc/overview/html/occt_user_guides__shape_healing.html),
[ShapeAnalysis_ShapeTolerance](https://dev.opencascade.org/doc/refman/html/class_shape_analysis___shape_tolerance.html),
[BRepCheck_Analyzer](https://dev.opencascade.org/doc/refman/html/class_b_rep_check___analyzer.html)).
Befund: in OCP 8.0.1 ist `BRepCheck_Result.Status()` nicht nach Python übersetzt (Typ nicht registriert); die
Fehlerarten werden deshalb je Fläche mit ShapeAnalysis bestimmt.

**STEP AP203/AP214/AP242 und CAx-IF.** Die CAx-IF „Geometric Validation Properties“ (GVP, Recommended Practices 4.6)
legen fest, wie das Original-CAD Volumen, Oberfläche und Schwerpunkt je Bauteil in die STEP schreibt
(`PROPERTY_DEFINITION('geometric validation property', …)` → `REPRESENTATION('volume' | 'surface area' | 'centroid')`
→ `VOLUME_MEASURE` / `AREA_MEASURE` / `CARTESIAN_POINT('centre point')`). Damit lässt sich jeder Import gegen die
**Referenzwerte des ursprünglichen CAD-Systems** prüfen – genau das, was Abschnitt 11 des Auftrags verlangt. Die
CAx-IF-Prüfungen verwenden in der Produktion etwa 0,5 % für Volumen/Fläche
([GVP 4.6](https://www.mbx-if.org/documents/rec_prac_gvp_v46.pdf),
[GVP 4.2](https://www.mbx-if.org/home/wp-content/uploads/2024/05/rec_prac_gvp_v42.pdf)). Creo, NX, CATIA, SolidWorks
und Inventor können diese Werte beim STEP-Export mitschreiben (Option „Validierungseigenschaften“, siehe z. B.
[PTC Creo](https://support.ptc.com/help/creo/creo_pma/usascii/data_exchange/interface/About_3D_STEP_Validation_Properties.html)).
Der NIST STEP File Analyzer nutzt dieselben Werte für seine Prüfberichte
([NIST](https://www.nist.gov/services-resources/software/step-file-analyzer-and-viewer)).

**Alternative Kernel** (Bewertung, kein Wechsel – Patrick hat am 24.11. 18:22 UTC entschieden, bei OpenCascade zu
bleiben):

| Kernel | Lizenz/Kosten | Import/Genauigkeit | Integration | Eignung |
|---|---|---|---|---|
| OpenCascade 8.0.1 | LGPL 2.1 mit Ausnahme, kostenlos, kommerziell nutzbar | STEP/IGES exakt (B-Rep), gut; Heilung konfigurierbar | vorhanden | **bleibt** |
| Parasolid (Siemens) | kommerziell, Lizenz + Laufzeitgebühren | sehr robust, X_T nativ | Neuentwicklung des Messkerns | nur bei X_T-Pflicht |
| ACIS (Spatial/Dassault) | kommerziell | SAT nativ, gut | Neuentwicklung | nein |
| C3D (C3D Labs) | kommerziell, günstiger | gut | Neuentwicklung | nein |
| HOOPS Exchange (Tech Soft 3D) | kommerziell | liest sehr viele Formate | als Vor-Übersetzer möglich | später prüfen, falls Kunden native Formate schicken |

Quellen: [Siemens: Kosten eines Kernel-Wechsels](https://blogs.sw.siemens.com/solidedge/the-hidden-cost-of-swapping-cad-kernels/),
[Tech Soft 3D zu Parasolid](https://www.techsoft3d.com/resources/blog/7-reasons-to-consider-switching-to-parasolid),
[Geometric modeling kernel](https://en.wikipedia.org/wiki/Geometric_modeling_kernel).

## 2. Analyse des bisherigen Importkerns

Ablauf (`step_messung/step_geometrie.py`, Programm startet `STEP-Import.exe` = `step_messen.py`):

| Phase | Stelle | Bewertung |
|---|---|---|
| 1 Datei einlesen | `lies_step_info` → `STEPCAFControl_Reader.ReadFile` | gut, Konsolenmeldungen mitgeschnitten |
| 2 Struktur | `ModelCheckList` (Fehler/Warnungen) | gut |
| 3 Einheiten | OCCT rechnet in mm um; `_einheit` nur Anzeige | **Genauigkeit der Datei nicht ausgewertet** |
| 4 Baugruppe | `_caf_uebertragen`, `_struktur` (Knoten, Instanzen, Namen) | gut |
| 5–6 Geometrie/Topologie | `TransferRoots` inkl. ShapeFix; ab 20 MB ohne 2 teure Prüfungen | **Heilung unsichtbar, Toleranzzuwachs nicht gemeldet** |
| 7 Flächen/Kanten | Flächenkatalog, `_analytisch` (IGES) | gut |
| 8 Shape Healing | nur implizit beim Lesen; `_naehen` 0,01 mm für Flächenmodelle | **kein Protokoll, keine Klassen** |
| 9 Körper | `_instanzen`, `_gedrehte` (Kopien nur einmal messen) | gut; **doppelt eingefügte Körper wurden „Verbundkern“** |
| 10 Maße | `analysiere` (Profil, Blech, Dreh-/Fräs), `_koerper_daten` | exakt aus B-Rep, gut |
| 11 Fertigungsgeometrie | Konturen, Bohrungen (Durchgang/Sack/Senkung/Fließloch/Gewinde-Vorschlag), Langlöcher, Gravuren | gut, Unsicherheit je Merkmal |
| 12 Übergabe | Messwerte-TSV + JSON (`step_ergebnis`) | gut, versioniert |

## 3. Identifizierte Schwachstellen

| Nr | Schwachstelle | Folge |
|---|---|---|
| S1 | Heilung beim Einlesen darf Toleranzen bis 1 mm vergrößern, ohne Meldung | ungenaue Konturen unbemerkt |
| S2 | Prüfwerte des Original-CAD (GVP) in der STEP wurden ignoriert | keine Gegenprobe gegen das Quell-CAD |
| S3 | Genauigkeit der Datei (UNCERTAINTY) nicht ausgewertet | grobe Exporte nicht erkennbar |
| S4 | Gültigkeit nur ja/nein, keine Fehlerarten | Fehlerursache unklar |
| S5 | ungültiger Körper, Messung scheitert: kein Reparaturversuch | „nicht messbar“, obwohl sicher reparierbar |
| S6 | deckungsgleich doppelt eingefügter Körper wurde als „Verbundkern“ ausgeschlossen, ohne Hinweis auf Doppelung | Teil fehlt bzw. Anzahl falsch |
| S7 | Importanalyse ohne Geometrie-Qualität | Nutzer sieht Verlässlichkeit nicht |

## 4. Technische Verbesserungen

- **Toleranzverwaltung** (S1, S3): je Körper größte/mittlere Toleranz von Punkten, Kanten, Flächen nach dem Einlesen,
  Stufe fein (≤ 0,001 mm), normal (≤ 0,01 mm = Messgenauigkeit), grob (≤ 0,1 mm), kritisch; Vergleich mit der
  Genauigkeit der Datei („durch Heilung vergrößert“). Toleranzen werden **nie** erhöht, um Fehler zu verdecken.
- **Shape Healing mit Protokoll** (S4, S5): Fehlerarten je Körper; Reparatur-Probe mit ShapeFix_Shape **an einer
  Kopie**, Genauigkeit = Datei, höchstens 0,01 mm; vorher/nachher geprüft (gültig, Toleranz, offene Kanten, Volumen,
  Oberfläche, Hülle, Schwerpunkt). Klassen: 1 sicher (Hülle ≤ 0,001 mm, Volumen/Oberfläche ≤ 0,001 %), 2 mit
  Abweichung (nur gemeldet), 3 nicht zuverlässig. Nur wenn die Messung des Originals scheitert und Klasse 1 vorliegt,
  wird die Kopie gemessen (Hinweis „mit sicher reparierter Kopie gemessen – prüfen“).
- **CAD-Prüfwerte (GVP)** (S2): Volumen, Oberfläche, Schwerpunkt je Bauteil aus der STEP (auch Zoll/Meter umgerechnet),
  Zuordnung über den Bauteilnamen bzw. bei Einzelteilen direkt; bestätigt ≤ 0,1 %, prüfen ≤ 0,5 %, darüber Abweichung
  (rot, Hinweis, Prüfstatus „prüfen“).
- **Doppelte Körper** (S6): deckungsgleich (gleiche Lage, Volumen, Hülle, Schwerpunkt) → Hinweis „Anzahl prüfen“; die
  Verbund-Erkennung hält einen gleich großen Körper nicht mehr für einen Kern.
- **Importanalyse** (S7): Reiter „Geometrieprüfung“ mit Farben und vollem Prüfprotokoll je Körper.

## 5. Neu implementierte Funktionen

| Datei | Inhalt |
|---|---|
| `programm/step_messung/step_qualitaet.py` (neu) | `datei_kopf` (Schema, CAD-System, Einheit, Genauigkeit, GVP), `koerper_pruefen`, `reparatur_probe`, `datei_pruefen` (GVP-Abgleich, Doppelte), `datei_zusammenfassung` |
| `step_geometrie.py` | Felder `qualitaet`/`pruefung_datei`, `_geometrie_pruefen` (in `koerper_messen`), `_datei_pruefung` (in `datei_abschliessen`), Verbund-Fix, Zeit `pruefen_s`/`kopf_s` im Tempo-Protokoll |
| `step_ergebnis.py` | JSON 1.31: `geometriepruefung` je Körper, `genauigkeit` je Datei |
| `step_messen.py` | Spalten `pruefung`, `pruefung_datei` (vor `fehler`) |
| `rohrlaser/importanalyse_dialog.py` | Reiter Geometrieprüfung (Ampel je Datei, Tabelle, Protokoll), Zukaufteile grau |
| `werkzeuge/step_benchmark.py` | `vergleich --ohne FELD …` (neue Felder beim Bitgleich-Vergleich auslassen) |
| `tests/erzeuge_pruefteile_2411.py`, `tests/step_pruefung/` (8 STEPs) | Prüfteile mit bekannten Sollwerten |
| `tests/test_cad_importkern_2411.py` | 14 Fälle (in `tests/alle.py`) |
| `rohrlaser/step_viewer.py`, `step_viewer_fenster.py`, `ansicht3d.py` | Knopf „Farben nach Prüfung“, Prüfwerte beim Anklicken, Übersicht je Datei |
| Bedienungsanleitung | Abschnitt „Geometrieprüfung und Prüfwerte des CAD“ |

## 6. Benchmark vorher/nachher

Gemessen mit `werkzeuge/step_benchmark.py` auf diesem Rechner (Cloud, 4 Kerne), Ausgangsstand = main vor diesem PR.
Vergleich mit `vergleich ALT NEU --ohne geometriepruefung genauigkeit schema_version` (nur die neuen Felder sind
ausgenommen, alle übrigen Messwerte werden Zeichen für Zeichen verglichen).

**126 Test-STEPs** (alle Testordner, inkl. 8 neue Prüfteile):

| | vorher | nachher |
|---|---:|---:|
| Messwerte gleich | – | **126 von 126** (bitgleich) |
| Summe Zeit | 365,8 s | 371,1 s (+1,4 %) |
| RAM je Datei | ~300 MB | ~299 MB |

**8 echte Kunden-STEPs** (aus Supportpaketen):

| Datei | Körper | vorher s | nachher s | RAM vorher/nachher MB | Messwerte |
|---|---:|---:|---:|---:|---|
| 013dda55 | klein | 2,9 | 3,2 | 300 / 300 | gleich |
| 15c5a561 | klein | 2,6 | 2,6 | 299 / 300 | gleich |
| c04fe4c0 | klein | 6,1 | 5,9 | 299 / 285 | gleich |
| 21cf4d1e | mittel | 16,1 | 16,4 | 309 / 309 | gleich, **+1 Hinweis „deckungsgleich doppelt“** |
| 84f9a0c9 | mittel | 29,7 | 32,7 | 308 / 296 | gleich |
| 462679ba | mittel | 58,4 | 68,6 | 305 / 296 | **1 Rohr vorher „nicht messbar“, jetzt gemessen** (siehe 7) |
| 3859869a Trailer | 218 | 1367,6 | 1380,6 | 597 / 596 | gleich (bitgleich gegen main 497fa66) |
| 93ce4136 | groß | 1868,2 | 1850,2 | 2914 / 2794 | gleiche Messwerte, **+1 Hinweis „deckungsgleich doppelt“** (siehe unten) |

Trailer und 93ce4136 wurden zur Gegenprobe ein zweites Mal mit dem Ausgangsstand (main 497fa66) gemessen; die
Tabelle zeigt diesen Lauf. Bei 93ce4136 unterscheiden sich außer dem neuen Hinweis nur (a) die Achsrichtung einiger
Drehteile in der 16. Nachkommastelle (1e-16; dieses Rauschen gibt es auch zwischen zwei Läufen des Ausgangsstands, 24
Stellen) und (b) die Reihenfolge der Messstellen der Wandstärke bei 3 Rohren (gleiche Werte, nur andere Reihenfolge der
z-Positionen). Kein Maß, keine Kontur, kein Profil, keine Art hat sich geändert.

Die Zeiten der großen Dateien schwanken auf der Cloud-Maschine um ±5 %; die reine Prüfzeit steht im Tempo-Protokoll
(`pruefen_s`) und liegt bei den Testdateien bei rund 1,3 s gesamt.

## 7. Genauigkeitsvergleich

Was sich an den Messwerten ändert, ist gewollt und begründet:

1. **462679ba, Körper 5 (Rundrohr Ø 42,4 × 1426,2 mm):** vorher „nicht messbar“ (OpenCascade meldet 2 ungültige
   Flächen, kein Profilquerschnitt gefunden). Die Reparatur-Probe an einer Kopie ergibt **Klasse 1** (Hülle, Volumen,
   Oberfläche und Schwerpunkt unverändert, Abweichung 0,0000 mm, Toleranz danach 0,0003 mm). Nur in diesem Fall wird
   die reparierte Kopie gemessen; das Teil steht trotzdem auf „prüfen“ mit dem Hinweis „mit sicher reparierter Kopie
   gemessen“. Vorher musste das Rohr von Hand angelegt werden.
2. **Doppelte Körper:** 21cf4d1e (1 Rohr) und 93ce4136 (1 Kantteil) enthalten Körper, die exakt deckungsgleich auf
   einem anderen liegen (zweimal eingefügt). Sie werden weiter gezählt (nie still gelöscht), bekommen aber den Hinweis
   „Anzahl prüfen“.
3. **Prüfteile mit bekannten Sollwerten** (`tests/step_pruefung`): CAD-Prüfwerte richtig → „bestätigt“ (Abweichung
   < 0,001 %), Volumen 2 % falsch → „abweichung“/fehlerhaft, Zoll-Datei → Prüfwerte richtig umgerechnet, Genauigkeit
   0,05 mm → „unsicher“, offene Schale → „fehlerhaft“, keine Reparatur (es würde Geometrie erfunden).

Ergebnis der Prüfung über alle 126 Test-STEPs (223 Körper): 215 korrekt, 4 unsicher (Flächenmodelle genäht, grobe
Genauigkeit, Doppelter), 4 fehlerhaft (3 offene Flächenmodelle, 1 falsche CAD-Prüfwerte); alle Toleranzen „fein“
(≤ 0,001 mm). Schemas: AP214 129, AP242 2, AP203 1.

## 8. Performancevergleich

- Mehrzeit durch die Prüfung: +1,4 % auf 126 Test-STEPs, +2 bis +6 % bei den großen Kunden-Baugruppen (innerhalb
  der Messschwankung der Cloud-Maschine bei den großen Dateien). Bei 462679ba kommen die 10 s fast ganz aus der
  zusätzlichen Messung des vorher nicht messbaren Rohrs.
- RAM: nicht höher; bei den großen Dateien sogar niedriger (93ce4136 3045 → 2794 MB), weil die Prüfung keine Netze
  erzeugt und die Reparatur nur an Kopien von ungültigen Körpern läuft.
- Schutz gegen Ausreißer: Reparatur-Probe nur bis 5000 Flächen, Fehlerart-Suche je Fläche nur bis 300 Flächen,
  CAD-Prüfwerte nur bis 100 MB Dateigröße.
- Schneller wird der Import durch diesen PR nicht; das ist Aufgabe von #643/#651 und dem Schnellimport.

## 9. Testergebnisse

- Neu: `tests/test_cad_importkern_2411.py` mit 14 Fällen (Datei-Kopf, Toleranzstufen, CAD-Prüfwerte inkl. Zoll,
  Doppelte, offene Schale, Reparatur Klasse 1 und 3, Messung mit reparierter Kopie, TSV-Spalten, JSON 1.31,
  Importanalyse-Reiter, Viewer-Farben) – grün, in `tests/alle.py`.
- Grün: test_step_referenz (58/58), test_step_ergebnis, test_step_importfehler, test_step_robust, test_step_leistung,
  test_step_viewer, test_importanalyse_3d, test_drehfraes, test_teilmessung_m3, test_step_benchmark,
  test_quellcode_schutz, test_anleitung, test_ansicht, test_dunkelmodus, test_hell_dunkel; ruff sauber.
- Benchmark: 126/126 Test-STEPs bitgleich, Kunden-STEPs siehe Abschnitt 6.

## 10. Noch bestehende Einschränkungen

- OpenCascade heilt beim Einlesen selbst (Orientierung, kreuzende Konturen: P06/P07 kommen gültig an). Diese Heilung
  lässt sich nicht Schritt für Schritt protokollieren, nur ihr Ergebnis (Toleranzen) und – falls vorhanden – über die
  CAD-Prüfwerte gegenprüfen.
- CAD-Prüfwerte werden je Bauteil verglichen; Prüfwerte auf Baugruppenebene und „Anzahl Kinder“ noch nicht. Schwerpunkt
  nur bei Einzelkörpern (Bauteil-Koordinaten). Dateien über 100 MB: Prüfwerte werden nicht ausgewertet (Hinweis).
- Die Test-STEPs stammen alle aus OpenCascade (Genauigkeit 1e-7 mm, keine Prüfwerte). Echte Exporte aus Inventor,
  SolidWorks, Creo, NX mit eingeschalteten Validierungseigenschaften fehlen noch als Referenz.
- Tempo: dieser PR macht den Import nicht schneller (Abschnitt 8); die Tempo-Arbeit läuft in #643 und im Schnellimport.

## 11. Empfehlungen für die nächste Entwicklungsstufe

1. **Echte Referenzdateien**: 10–20 STEPs aus den CAD-Systemen der Kunden mit eingeschalteten Validierungseigenschaften
   in `tests/step_pruefung` aufnehmen; der Abgleich prüft dann automatisch gegen das Quell-CAD.
2. **read.maxprecision begrenzen**: Test mit `read.maxprecision.mode = Forced`, 0,01 mm auf echten Dateien. Ändert
   Messwerte (nicht bitgleich), daher nur nach Patricks Freigabe.
3. **Reparierte Kopie auch für die Kontur-Ausgabe**: heute nur Messung; DXF/Abwicklung aus der Kopie erst nach
   Vergleich der Konturen mit dem Original (Grundregel 100 % STEP-Treue).
4. **Netzformate** (STL, OBJ, 3MF): nur Anzeige, nie Grundlage für Maße; OCCT liest STL/OBJ/glTF, 3MF nicht.
   SAT, Parasolid X_T, JT gibt es für OCCT nur als kostenpflichtige Zusatzmodule – Kunden um STEP AP214/AP242 bitten.
5. **Lokale KI** nur als Erkennungsschicht (Normteil/Art), ihre Vorschläge mit der Geometrieprüfung gegenprüfen; Maße
   bleiben B-Rep.
6. Prüfung großer Baugruppen parallel je Körper (OCCT 8 ist thread-sicher je Instanz).
