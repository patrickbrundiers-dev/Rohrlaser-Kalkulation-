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
| `tests/test_cad_importkern_2411.py` | 13 Fälle (in `tests/alle.py`) |
| Bedienungsanleitung | Abschnitt „Geometrieprüfung und Prüfwerte des CAD“ |

## 6. Benchmark vorher/nachher

BENCHMARK_TABELLE

## 7. Genauigkeitsvergleich

GENAUIGKEIT_TABELLE

## 8. Performancevergleich

PERFORMANCE_TEXT

## 9. Testergebnisse

TEST_TEXT

## 10. Noch bestehende Einschränkungen

- OpenCascade heilt beim Einlesen selbst (Orientierung, kreuzende Konturen: P06/P07 kommen gültig an). Diese Heilung
  lässt sich nicht Schritt für Schritt protokollieren, nur ihr Ergebnis (Toleranzen) und – falls vorhanden – über die
  CAD-Prüfwerte gegenprüfen.
- CAD-Prüfwerte werden je Bauteil verglichen; Prüfwerte auf Baugruppenebene und „Anzahl Kinder“ noch nicht. Schwerpunkt
  nur bei Einzelkörpern (Bauteil-Koordinaten). Dateien über 100 MB: Prüfwerte werden nicht ausgewertet (Hinweis).
- Die Test-STEPs stammen alle aus OpenCascade (Genauigkeit 1e-7 mm, keine Prüfwerte). Echte Exporte aus Inventor,
  SolidWorks, Creo, NX mit eingeschalteten Validierungseigenschaften fehlen noch als Referenz.
- Farbige Darstellung im 3D: in der Importanalyse über die Tabelle; Einfärben im neuen STEP-Viewer folgt nach dem
  Merge von #642 (gleiche Statusfarben).
- Tempo: dieser PR macht den Import nicht schneller (Abschnitt 8); die Tempo-Arbeit läuft in #643 und im Schnellimport.

## 11. Empfehlungen für die nächste Entwicklungsstufe

1. **Echte Referenzdateien**: 10–20 STEPs aus den CAD-Systemen der Kunden mit eingeschalteten Validierungseigenschaften
   in `tests/step_pruefung` aufnehmen; der Abgleich prüft dann automatisch gegen das Quell-CAD.
2. **read.maxprecision begrenzen**: Test mit `read.maxprecision.mode = Forced`, 0,01 mm auf echten Dateien. Ändert
   Messwerte (nicht bitgleich), daher nur nach Patricks Freigabe.
3. **STEP-Viewer**: Statusfarben und Prüfprotokoll beim Anklicken (nach #642).
4. **Netzformate** (STL, OBJ, 3MF): nur Anzeige, nie Grundlage für Maße; OCCT liest STL/OBJ/glTF, 3MF nicht.
   SAT, Parasolid X_T, JT gibt es für OCCT nur als kostenpflichtige Zusatzmodule – Kunden um STEP AP214/AP242 bitten.
5. **Lokale KI** nur als Erkennungsschicht (Normteil/Art), ihre Vorschläge mit der Geometrieprüfung gegenprüfen; Maße
   bleiben B-Rep.
6. Prüfung großer Baugruppen parallel je Körper (OCCT 8 ist thread-sicher je Instanz).
