# Abwicklungskern: STEP-Schnittwege über die Abwicklung beschleunigen

Master-Entwicklungsauftrag Patrick, 24.11.2026 („STEP-Import durch abwicklungsbasierte Schnittwegberechnung
beschleunigen“). Technischer Untersuchungsbericht und Umsetzung. Programmstand: main 0.9.473 (497fa66d) + dieser PR.

## 1. Kurzfassung

- **Befund:** Der Schneidweg eines Rohrs wird heute schon **nicht** im 3D-Raum geschnitten. Die Messung nimmt die
  Kanten, an denen Schnittflächen auf die Außenhaut treffen, direkt aus der STEP (exakte Kantenlänge) und wickelt
  sie für Form und Lage auf den Umfang ab. Diese Rechnung kostet nur rund **5–9 %** der Zeit.
- **Die Zeit geht woanders hin:** 32 % in ebenen Schnitten durch den ganzen Körper (Achse und Querschnitt suchen,
  im Mittel 34 Schnitte je Teil), 27 % in Booleschen Operationen, fast alle beim Bau der Variante „aus dem Rohr
  gelasert“ für offen gezeichnete U-Profile und Kantteile.
- **Umsetzung (Abwicklungskern):** Genau dort setzt die Abwicklungsidee an:
  1. Profil-Lage aus der Flächenparametrisierung und einer Merkmalskarte über die Länge statt Suchschnitten.
  2. Endlinien der Ringe/Wände offener Rohre in der Abwicklung (2D) bereinigen, bevor daraus 3D-Körper werden.
- **Ergebnis an den 126 Prüf-STEPs:** Summe **185,1 s → 95,7 s (Faktor 1,93)**, U-Profile und offene Rohre
  **5- bis 14-mal** schneller, Rohre mit vielen Konturen bis 2,8-mal. **123 von 124** lesbaren Dateien liefern
  dieselben Profile, Maße, Schneidwege und Konturen (Toleranz 0,01 mm). Die eine Abweichung (I10) ist eine
  Fehlerbehebung (radiale Bohrung im Rundrohr galt als 0,72° schräg).
- **Hybrid und Rückfall:** 170 von 211 Profilmessungen laufen über den neuen Weg, 41 automatisch über den bisherigen
  (Freiform, Platten/Flachstahl, Anbauteile, lange Fenster, keine freie Stelle).
- **Vorgabe „an“** (Patrick-Entscheidung 24.11.2026 21:47 UTC, Einstellung *Messung: Abwicklungskern*). Die Werte
  sind innerhalb der Toleranz gleich, aber nicht in jeder letzten Stelle bitgleich; Patrick hat das ausdrücklich
  freigegeben (Ausnahme zur Regel vom 21.11. „nur bitgleich“). „aus“ bleibt als Schalter für die bisherige Rechnung.

## 2. Ist-Zustand der Importarchitektur

```
STEP-Datei ─ datei_lesen (OCCT STEPControl, Heilen, Nähen, Struktur, Kopien)            ~2 %
   └ je Körper koerper_messen → analysiere → _analysiere_naht/_analysiere
        ├ Biegerohr, Kerbbiegen, Blech, Dreh-/Frästeil, Normteil … (eigene Module)
        └ _analysiere_profil → _profil_messen(solid)
             ├ _lage: grobe Achse aus Netznormalen, 3 × 7 Schnitte (Nachschärfen), Drehung     ~13 %
             ├ suche: bis 49 Schnitte, bis 3 gleiche größte Querschnitte                      ~12 %
             ├ Flächen außen/innen/Schnitt (Punkte auf der Querschnittskontur)                 ~5 %
             ├ Merkmale = zusammenhängende Schnittflächen, Kanten zur Außenhaut
             ├ Schneidweg = Σ Kantenlänge (exakt, GCPnts), Lage/Form über _Abwicklung (u, z)   ~5 %
             └ Enden, Gehrung, Bohrungsart, Schwenk, Netz
        └ step_offenes_rohr.schliessen (U/C/Kantteil → „aus dem Rohr“)                         ~48 %
             ├ Wand ergänzen, Ringe, Fenster: Lofts aus bis zu 240 Punkten je Endlinie
             ├ Boolesche Operationen damit (Fuse/Common/Cut, je 0,2–2,5 s)                    ~27 %
             └ _profil_messen(zu, quer=geschlossenes Rohr) noch einmal
   └ datei_abschliessen (Kopien, Anbauteile, Verbund, Nähte)
```

Gemessen mit py-spy (100 Hz) über alle 126 Prüf-STEPs, 210 s Gesamtdauer, Anteile an der Gesamtzeit. Zählung:
7.278 ebene Schnitte (62,8 s, je 8,6 ms), 230 Boolesche Operationen (53,0 s, je 230 ms), 211 Profilmessungen.

| Teileart (126 Dateien) | Dateien | Zeit bisher |
|---|---:|---:|
| Offene Profile (U, C, L, T …) | 26 | 85,5 s |
| Geschlossene Rohre | 53 | 34,8 s |
| Kantteile | 5 | 28,6 s |
| Baugruppen | 12 | 27,7 s |
| RP-Profile | 4 | 17,6 s |
| Bleche, Flachstahl, Sonstige | 26 | 15,5 s |

## 3. Bewertung der vorgeschlagenen Abwicklungsmethode

| Schritt im Auftrag | Bewertung |
|---|---|
| 1 Profil erkennen | **Umgesetzt, neu.** Achse aus Ebenen und Zylindern (exakt statt aus dem Netz), Merkmalskarte der Abwicklung, 3 Schnitte an freien Stellen statt ~34 Suchschnitte. |
| 2 Profil abwickeln | **Vorhanden** (_Abwicklung: Umfangsposition u je Punkt, Rund/Kasten/Oval; seit #600 auch Eckradien exakt). Nicht neu gebaut. |
| 3 Schnittwege in 2D berechnen | **Bewusst nicht** für den Schneidweg: die Kanten der STEP sind die exakte Kontur. Eine 2D-Neuberechnung aus abgetasteten Punkten wäre ungenauer und nicht schneller (die Rechnung kostet nur 5 %). **Umgesetzt** dagegen: 2D-Bereinigung der Endlinien offener Rohre (Konturen bereinigen und zusammenführen), bevor 3D-Körper entstehen. |
| 4 Rückübertragung | **Nicht nötig:** die Konturen bleiben die Kanten der STEP, nichts wird projiziert, verschoben oder extrudiert. Damit gilt die Grundregel (Konturen 100 % wie STEP) ohne Risiko einer falschen Extrusion an gekrümmten Flächen. |
| Boolean nur wo nötig | **Umgesetzt:** die Lofts der Ringe/Wände haben statt bis zu 480 nur noch wenige Flächen; K07 Boolesche Operationen 11,5 s → 0,4 s. |

## 4. Machbarkeit, Grenzen, Probleme

- **Rohrachse:** nur aus analytischen Flächen. Freiform (B-Spline-Mantel), Körper ohne klare Längsrichtung und Platten
  (zwei fast gleich gute Richtungen, Abstand unter 15 % der Fläche) gehen an die bisherige Rechnung.
- **Merkmalskarte:** Jede nicht längs laufende Fläche belegt ihren Z-Bereich. Ebenso jede Längsfläche, die nicht von
  Ende zu Ende reicht. Zu den Enden gehören Gehrungs-/Schrägschnittflächen und kurze Längsflächen (Ringe,
  Ausklinkungen), die von dort ausgehen. Ohne freien Bereich von mindestens 2 mm: bisherige Rechnung.
- **Gegenproben:** drei Schnitte gleich (Fläche bis 1e-5, gleiche Konturzahl, Innen in Außen). Dazu das Volumen höchstens
  Querschnitt × Länge (Merkmale nehmen nur weg). Diese Probe fängt lange Fenster und Anbauteile ab.
- **Nicht bitgleich, aber innerhalb der Toleranz:** Achse exakt statt nachgeschärft (Unterschied ~1e-12), andere
  Schnittlagen für die Wandmessung (gleiche Werte), Endlinien ohne Zwischenpunkte (Lageunterschied ≤ 1e-6 mm).
- **Symmetrie:** Beim Quadratrohr und Rundrohr ist die X-Richtung schon bisher nur durch Rundungsrauschen bestimmt.
  Der Vergleich wertet ein um 90° gedrehtes Quadratrohr deshalb als gleiches Teil. Das Hüllmaß eines Endes hängt von
  der Abtastung ab (0,5 mm bzw. 1 % Toleranz; über 50 mm zählt die Konturklasse „groß“).
- **Gefundener Fehler (bisherige Rechnung):** Die Wandnormale am Rundrohr kam aus einer Sehne ±0,5 mm des Umrisses.
  Je nach Lage der Stützpunkte kippte sie um bis zu eine halbe Teilung (Ø40: 0,72°). Eine radiale Bohrung galt dann
  als schräg (über 0,5°) und bekam die 3D- statt der 2D-Rundrohr-Schnittlänge (I10: 25,20 statt 26,64 mm).
  Mit dem Abwicklungskern ist die Normale exakt radial. In der bisherigen Rechnung (Modus aus) bleibt es unverändert.

## 5. Vergleich der Berechnungsansätze

| Ansatz | Tempo | Genauigkeit | Aufwand/Risiko | Entscheidung |
|---|---|---|---|---|
| A bisher: Suchschnitte + Kanten der STEP | Basis | exakt | – | bleibt Rückfall |
| B1 Schneidweg komplett aus 2D-Abwicklung (Raster/Polygone, z. B. Shapely/Clipper) | kaum schneller (Schneidweg nur 5 %) | schlechter (Abtastung), Schrägschnitte/Durchdringungen in 2D nicht exakt | hoch | verworfen |
| B2 Lage aus Flächenparametrisierung + Merkmalskarte (gebaut) | Rohre bis 2,8× | gleich (Toleranz) | gering, Rückfall | **gebaut** |
| B3 2D-Bereinigung der Endlinien vor dem 3D-Körper (gebaut) | U/offene Rohre 5–14× | gleich (Toleranz) | gering | **gebaut** |
| C Variante „aus dem Rohr“ ganz in 2D (Fenster/Ringe als Bereiche der Abwicklung, keine Booleans) | weitere ~0,5–1 s je U | gleich zu prüfen | hoch (Enden, Gehrungen, Laschen) | Plan Stufe 3 |
| D anderer CAD-Kern / Fremdbibliothek | offen | offen | sehr hoch | entfällt (Patrick 24.11.: bei OpenCascade bleiben) |

Bibliotheken: OpenCascade 8.0.1 (OCP) bietet alles Nötige (BRepAdaptor_Surface für die Flächenparameter,
BRepAlgoAPI_Section, Bnd_Box, GCPnts). Zusätzliche 2D-Bibliotheken (Shapely, Clipper2) bringen hier keinen Vorteil, weil
keine Polygonoperationen mehr nötig sind. Parallelisierung: die Messung verteilt Körper und Dateien schon auf Prozesse
(step_messen), Boolesche Operationen laufen mit SetRunParallel (#643). Fachlich entspricht der Kern dem üblichen Vorgehen
der Rohrlaser-CAM-Systeme: Profil aus dem Regelquerschnitt, Konturen aus der B-Rep-Topologie, Abwicklung nur zur Lage und
Darstellung.

## 6. Architektur der Umsetzung

- `programm/step_messung/step_abwicklungskern.py` (eigenständig): `flaechen`, `achse`, `freie_bereiche`, `lage`,
  `profil_vorgabe`; Vergleich `vergleichen` (Toleranzen TOL_MM 0,01 mm, TOL_REL 1e-5, Symmetrie Quadratrohr, Hüllmaß);
  Modus `aus | vergleich | an` (`modus_setzen`, Umgebung `RL_ABWICKLUNGSKERN`), Protokoll `PROTOKOLL`,
  `zusammenfassen`.
- `step_geometrie._profil_messen`: Weiche. **aus** = unverändert (`_profil_messen_kern`). **an** = Vorgabe aus dem Kern,
  ohne Profil automatisch bisher. **vergleich** = beide rechnen, das bisherige Ergebnis gilt, Unterschiede ins
  Protokoll. `_profil_messen_kern(…, vorgabe)` nutzt die feste Lage und die drei Schnitte statt `_lage`/`suche`.
- `step_offenes_rohr._gerade_raus`: Endlinien der Ringe und Wände (Körper) ohne Punkte auf einer Geraden. Die Anzeige
  behält alle Stützpunkte.
- Protokoll: je Datei `phasen.abwicklungskern` (neu/Rückfall/Gründe/ungleich/Zeiten), im Programm als Zeile im
  Tempo-Protokoll (Support-Paket).
- Einstellung `step_abwicklungskern` (STEP-Import → Toleranzen, Experte) → `--abwicklungskern` an STEP-Import.exe. Der
  Zwischenspeicher-Schlüssel enthält die wirksamen Einstellungen, also auch den Modus. Der Biegerohr-Faktor steht
  jetzt auf der Seite *Knickrahmen und Steckverbindung* (Höchstzahl 25 je Seite).
- Werkzeug `werkzeuge/abwicklungskern_vergleich.py` (alt/neu je Datei im selben Prozess, `--wdh`, Bericht) und
  `werkzeuge/step_benchmark.py` mit `RL_ABWICKLUNGSKERN=aus|an` (eigene Prozesse: CPU, RAM).
- Test `tests/test_abwicklungskern.py` (A1–A7) in tests/alle.py.

## 7. Messung (126 Prüf-STEPs, ein Prozess, gleicher Rechner)

`python werkzeuge/abwicklungskern_vergleich.py tests` (Rohwerte in `docs/performance/abwicklungskern_2411.md`):

| Ordner | Dateien | bisher s | neu s | Faktor |
|---|---:|---:|---:|---:|
| step_konturen | 10 | 45,0 | 5,1 | 8,76 |
| step_rp | 6 | 27,5 | 20,6 | 1,34 |
| step_profile | 10 | 19,3 | 3,7 | 5,16 |
| step_offen | 4 | 16,9 | 4,4 | 3,84 |
| step_importengine | 10 | 16,7 | 14,8 | 1,13 |
| step_regression (Freiform = Rückfall) | 8 | 15,9 | 16,7 | 0,95 (Schwankung) |
| step_referenz | 18 | 13,8 | 5,4 | 2,56 |
| step_anbau | 11 | 8,4 | 8,0 | 1,05 |
| step_bleche | 18 | 7,3 | 7,3 | 1,01 |
| step_traeger | 9 | 3,7 | 1,2 | 3,02 |
| step (Grundteile) | 7 | 3,3 | 1,9 | 1,73 |
| übrige | 13 | 7,4 | 6,5 | 1,14 |
| **Summe** | **124** | **185,1** | **95,7** | **1,93** |

Größte Einzelgewinne: K08 U80x40x4 16,5 → 1,1 s, K07 15,9 → 1,2 s, K06 10,5 → 1,2 s, P01 9,5 → 1,0 s,
T06 QR40 mit Langlöchern 0,98 → 0,35 s. Genauigkeit: 123/124 Dateien gleich, I10 siehe Abschnitt 4. RAM und CPU je
Prozess: siehe `docs/performance/abwicklungskern_2411.md` (step_benchmark, eigene Prozesse).

**Eigene Prozesse wie STEP-Import.exe** (`RL_ABWICKLUNGSKERN=aus|an python werkzeuge/step_benchmark.py lauf …
--prozesse 1`, 55 Dateien aus step, step_konturen, step_offen, step_profile, step_regression, step_rp,
step_importengine, nacheinander): Dauer **249,8 s → 140,6 s (1,78)**, CPU-Zeit 246,7 s → 157,4 s, RAM-Spitze je
Prozess 287 MB → 287 MB (Mittel 285 MB, unverändert). Der JSON-Vergleich ungerundet (Toleranz 1e-4) zeigt Unterschiede
nur bei:
- Lage der Wandstärke-Messstellen (z, Seite): andere Schnittlagen, gleiche Werte (±0,001 mm),
- Stützpunkten der Umrisse für die Darstellung (meist ≤ 0,2 mm, bei anderer Punktzahl verschoben gezählt),
- I10 (Fehlerbehebung, oben),
- P02 Variante „aus dem Rohr“: Schwenkwinkel von Ende A 30,0° → 11,7°. Dieses „Ende“ umfasst dort das ganze Fenster
  (1.478 mm Schnitt), der Winkel ist schon bisher nicht aussagekräftig. Der Schneidweg ist gleich. Bleibt als Punkt für
  Stufe 3.

Abnahmekriterien: 1 Beschleunigung nachgewiesen. 2 und 3: Genauigkeit gleich, Schnittwege innerhalb 0,01 mm. 4 Rückfall
automatisch in 41 Fällen geprüft. 5 Modus aus = bisheriger Code, die bestehenden Tests unverändert. 6 Große Dateien:
I05 Baugruppe 48 Teile 11,7 → 10,5 s, gleich. Echte große Baugruppen (MASTER TOWER, Pizza-Ofen) liegen hier nicht vor.
Die Prüfung dort macht der Vergleichsmodus beim Kunden.

## 8. Priorisierter Entwicklungsplan

1. **Stufe 1 + 2 (dieser PR):** Kern, Weiche, Vergleich, Rückfall, Einstellung, Protokoll, Tests, Bericht.
2. **Freigabe:** Patrick schaltet *an* (oder erst *vergleich* auf einem Platz und sieht das Tempo-Protokoll an). Danach
   Vorgabe *an* für alle.
3. **Stufe 3:** Variante „aus dem Rohr“ ganz in der Abwicklung (Fenster/Ringe als 2D-Bereiche, Kanten direkt). Das
   spart die restlichen Booleschen Operationen der offenen Rohre (~0,5–1 s je U).
4. **Stufe 4:** Lage auch für `step_offenes_rohr.erkennen`, `step_schenkel` und die Anbauteil-Trennung aus dem Kern
   (dort noch `_lage` mit 21 Schnitten).
5. **Stufe 5:** Freiform-Mantel (B-Spline-Rohre aus manchen CAD) über die Isoparameter der Fläche statt Rückfall.

## 9. Abwicklungskern 2.0 (Plan vom 24.11.2026, freigegeben „Alles bauen“)

Plan: https://claude.ai/artifact/MeGQKSAn71xSDVx7aCUzP4. Pakete N1–N7 in fünf PRs (A: N7 + N1, B: N2, C: N3 + N4,
D: N5, E: N6). Abnahme je PR: alle Prüf-STEPs gegen die Prüfbasis gleich oder begründet genauer, nicht langsamer,
Schalter „aus“ unverändert.

### PR A: Prüfbasis (N7) und Selbstprüfung (N1)

- **Prüfbasis** `tests/daten/abwicklungskern_soll.json`: Sollwerte jedes Teils der 124 lesbaren Prüf-STEPs (alle
  Vergleichsfelder, Konturen, Hinweise, geschlossenes Rohr, Alternative), geschrieben im Modus an mit
  `werkzeuge/abwicklungskern_vergleich.py tests --soll-schreiben …`. Abnahme mit `--soll …` misst nur den Kern
  (89 s statt 185 + 96 s). Ein späterer PR, der eine Messung bewusst ändert, schreibt die Datei neu: der Diff zeigt jede
  geänderte Messung. Im Test A10 laufen 8 Prüf-STEPs (Rohre, Gehrung, U offen, I10, Platte, Freiform, Laschen) gegen
  die Prüfbasis.
- **Gegenproben** `step_abwicklungskern.gegenproben` aus der Flächenparametrisierung, unabhängig von den Schnitten:
  Werte endlich und ≥ 0; Querschnitt = Merkmalskarte (1e-5); Länge = Merkmalskarte (0,01 mm, nicht bei Lage aus dem
  geschlossenen Rohr); Rundrohr Ø und Innen-Ø als Radien achsgleicher Zylinder (0,01 mm); Rechteck-/Quadratrohr
  Außenmaße als äußerste Wandebenen zweier Richtungen und Innenmaße als Ebenenabstand (0,01 mm; Fasen bilden eigene
  Richtungen). Nicht bestanden → Rückfall mit Grund „Gegenprobe: …“. Vertrauen 100 (mit Maß-Probe), 80 (ohne).
- **Dauer-Vergleich**: jedes 20. Teil (CRC32 von Dateiname und Körper, also unabhängig von der Reihenfolge) wird im
  Modus an zusätzlich bisher gerechnet; bei Abweichung gilt die bisherige Rechnung. Protokoll: `stichprobe`, `gleich`,
  `unterschiede`; Tempo-Protokoll-Zeile zählt die Stichproben. CLI `--abwicklungskern-stichprobe N` (0 = aus). Keine
  eigene Einstellung: die Seiten STEP-Import und Arbeitsplatz haben schon die Höchstzahl 25 Einträge.

Messung 126 Prüf-STEPs (Modus an, ohne Stichprobe): 170 Kern-Messungen, davon 130 mit Vertrauen 100 und 40 mit 80,
41 Rückfälle wie bisher. Gegen die Prüfbasis 124 von 124 Dateien gleich. Die Gegenproben fanden an den Prüfteilen
keinen Fehler. Zuerst schlug REF08 (Quadratrohr mit Fasen) an, weil die Fasen als eigene Wandrichtung galten; das ist
behoben.
