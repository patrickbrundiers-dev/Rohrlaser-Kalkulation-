# Importengine 2.0: STEP, TubeX, LST, ArTube, BPF (26.11.2026)

Master-Auftrag Patrick 26.11.2026 15:32 UTC „High-Performance-Importengine 2.0 – Genauigkeit, Geschwindigkeit und
Zuverlässigkeit maximieren“. Version 0.9.537, kein Schema-Sprung, keine Änderung der Kalkulation
(tests/test_regression_ergebnisse.py: 20 Angebote bitgleich).

Gemessen wurde an Patricks echten Dateien aus den Supportpaketen (Kundendaten, **nicht im Repo**) und an den
144 Prüf-STEPs des Repos (`tests/step*`). Jede Zahl unten stammt aus `werkzeuge/step_benchmark.py lauf … --prozesse 1`
auf demselben Rechner (4 Kerne, Linux), alter Stand = main dfd043eb (0.9.522), neuer Stand = dieser PR.

## 1. Ergebnis in Kürze

- **Hänger behoben:** LST/TUBX 10186133 P10 und der Fertigungsauftrag 2026-44094_1 lieferten im alten Stand nach
  20 bzw. 55 min kein Ergebnis; jetzt 2,6 min bzw. 3,6 min, gültige Körper.
- **Genauer:** P20 jetzt gültig und 0,025 mm³ an der STEP (vorher ungültig, 718 mm³ zu wenig); P30 1,0 mm³ an der STEP
  (vorher 24.114 mm³ zu viel, Fenster fehlte); BPF/ARTUBE unverändert.
- **Schneller:** P20 41 → 24 s (−41 %), P30 29 → 27 s, ARTUBE/BPF gleich schnell wie vorher (±3 %);
  **144 Prüf-STEPs 400,8 → 351,5 s (−12 %), alle 144 bitgleich.** Das Ziel 20–30 % ist bei den Maschinendateien
  erreicht und übertroffen, bei STEP nicht ganz (der STEP-Kern war schon in #643/#651/#652 optimiert).
- **Format am Inhalt** statt nur an der Endung, mit Hersteller, Software und Version.
- **Kalkulation unverändert** (20 Angebote bitgleich), kein Schema-Sprung.

## 2. Analyse je Format

| Format | Leser | Weg zum Körper | Befund vorher |
|---|---|---|---|
| STEP (AP203/214/242) | step_geometrie (OCCT STEPCAFControl) | B-Rep direkt aus der Datei | schnell und genau; Nahtsuche lief für jedes Flächenpaar eine boolesche Operation |
| IGES | step_geometrie (IGESCAFControl) | B-Rep | in Ordnung |
| TUBX (TRUMPF TubeCAM 5.x) | step_tubx | Netz aus Task3D (BSON) oder, wenn daneben, Schneidweg der LST | P10 367 s, die LST daneben bestimmte das Ergebnis |
| LST (TRUMPF Programming Tube 5.x) | step_lst + rohrlaser/lst_bahn | Rohr aus dem Profil, Werkzeugkörper je Kontur aus dem NC-Weg (Fugenbreite, Mitte der Fuge) | **P10 hing über 20 min**; P20 ungültiger Körper (718 mm³ zu wenig); P30 24.114 mm³ zu viel (Fenster nicht ausgeschnitten) |
| LST Fertigungsauftrag | – | enthält nur Programmnamen und Sollanzahl, keinen Schneidweg | wurde als Programm versucht |
| BPF (BLM/Adige) | step_blm | Rohr aus dem Profil, Werkzeug je Kontur als Dreiecksnetz | Nähen der Werkzeuge quadratisch (XW1006934 12,5 s Lesen) |
| ARTUBE (BLM ArTube) | step_blm (BPF daneben bzw. OBJ) | wie BPF | wie BPF |

**Gemeinsamer Engpass.** step_blm und step_lst bauten jedes Werkzeug als Dreiecksnetz und nähten es mit
`BRepBuilderAPI_Sewing`. Dessen Kandidatensuche wächst quadratisch mit der Zahl der Flächen; bei den großen
Kerbschnitten der TRUMPF-Programme (tausende Dreiecke je Kontur) dauerte allein das Nähen Minuten.

**Rohrecken.** Die Werkzeugtiefe 1,5 · Wand + 1 ist bei 60×40×2 R4 genau 4 mm = Eckradius: die inneren Punkte des
Werkzeugs fielen im Bogen der Ecke alle auf den Eckmittelpunkt, die Flächen hatten keinen Inhalt, der Körper war ungültig.

**Offene Konturen.** TubeCAM schneidet große Öffnungen und Kerben als zwei offene Konturen mit 1–1,5 mm Haltestegen
(Mikroverbindungen). Bisher wurde nur die Schnittfuge abgezogen, der Abfall blieb im Körper (P30: Fenster fehlte).

**Format nur an der Endung.** Eine umbenannte Datei (STEP als .txt, ZIP als .step, SolidWorks-Datei als .step,
Fertigungsauftrag als .lst) lief in den falschen Leser oder scheiterte ohne klare Meldung.

## 3. Ergebnisse der Online-Recherche

- **OCCT 8.0.1** (im Programm cadquery-ocp 8.0.1.1.0, also aktuell). STEP-Lesen ist mit einer Leser-Instanz je Thread
  thread-sicher, IGES nicht ([OCCT 8.0.0](https://dev.opencascade.org/content/open-cascade-technology-800-release),
  [8.0.1](https://github.com/Open-Cascade-SAS/OCCT/discussions/1415),
  [paralleles Lesen](https://dev.opencascade.org/content/reading-several-step-files-parallel)). Das Programm liest
  bereits je Datei in eigenen Prozessen; mehr Parallelität beim Lesen einer Datei bringt OCCT nicht.
- **Nähen.** `BRepBuilderAPI_Sewing` ist für beliebige Flächen gedacht und sucht Kandidaten paarweise.
  `BRepBuilderAPI_FastSewing` ([Doku](https://dev.opencascade.org/doc/refman/html/class_b_rep_builder_a_p_i___fast_sewing.html))
  und `BRepBuilderAPI_MakeShapeOnMesh`
  ([Doku](https://dev.opencascade.org/doc/occt-7.8.0/refman/html/classBRepBuilderAPI__MakeShapeOnMesh.html)) gibt es
  in OCP. Beide wären eine neue, an diesen Netzen ungeprüfte Abhängigkeit; ihr Verhalten bei fast doppelten Punkten
  und gemischter Dreiecksrichtung ist nicht dokumentiert. Bei den Werkzeugen ist die Topologie bekannt (geschlossenes
  Netz), deshalb baut das Programm Ecken, Kanten
  und Flächen jetzt **direkt** mit gemeinsamen Kanten (`step_blm._netz_direkt`), richtet die Dreiecke über die
  Nachbarschaft aus und prüft mit `BRepLib::OrientClosedSolid`. Ist das Netz nicht geschlossen, wird wie bisher genäht.
- **Toleranzen beim Einlesen** (`read.precision.mode`, `read.maxprecision.val` = 1 mm,
  [STEP-Handbuch](https://dev.opencascade.org/doc/overview/html/occt_user_guides__step.html)) sind seit PR #654 sichtbar;
  nichts geändert.
- **Zwischenspeicher.** Schlüssel = SHA-256 des Inhalts + Programmversion + Einstellungen (step_messen) und
  Leser-Stand (step_lesecache, jetzt LESER_STAND 4). Neu: bei TUBX gehört die LST daneben, bei ARTUBE die BPF daneben
  zum Schlüssel; ändert sich die Begleitdatei, wird neu gemessen. STEP-Schlüssel unverändert.
- **Proprietäre Formate.** Für TUBX, LST, BPF und ARTUBE gibt es keine öffentliche Spezifikation. Ausgewertet wird nur,
  was in Patricks Dateien eindeutig zu sehen ist (Abschnitt 4); alles andere wird als „unbekannt“ geführt und nicht
  gedeutet.

## 4. Formaterkennung am Inhalt (rohrlaser/dateiformat.py)

Neues Modul ohne Qt und ohne OpenCascade, also gleich für Hauptprogramm, STEP-Messung und Serverversion.
`erkennen(pfad)` liest höchstens 64 KB (LST bis 16 MB für den Auftragskopf) und liefert Art, Hersteller, Software,
Version, weitere Kopffelder und die unbekannten Bestandteile. Was die Datei nicht selbst sagt, bleibt leer.

| Art | Kennung im Inhalt | ausgelesen |
|---|---|---|
| STEP | `ISO-10303-21;` | Zeitpunkt, Präprozessor, CAD-System, Schema (AP203/214/242) |
| IGES | 80-Zeichen-Zeilen, Spalte 73 = S/G | Absender, System, Präprozessor (Hollerith-Texte) |
| TUBX | ZIP mit `Task3D/` und `tubeProps/app.xml` | TubeCAM-Version, Profil, Profil-ID, Maschine, Werkstoff, Wand |
| LST | `BD`, `SET_METRIC`, `BEGIN_EINRICHTEPLAN_INFO`, `BEGIN_PROGRAMM` | Programming Tube-Version, Maschine, Steuerung, Programme |
| LST-Fertigungsauftrag | `BEGIN_FERTIGUNG_AUFTRAG_TMP` ohne `BEGIN_PROGRAMM` | Programmnamen und Anzahl – **kein Schneidweg**, klare Meldung |
| BPF | `(c) Adige S.p.A. BLMGroup` + zlib | Hersteller |
| ARTUBE | tar mit `__ACF_FILE_SIGNATURE__` (ohne ustar-Kennung) | Teile (OBJ); Parasolid-Körper als „unbekannt“ |
| nicht messbar | OLE `D0CF11E0` (SolidWorks/Inventor/Solid Edge), CATIA, Parasolid, ACIS, STL, MegaCAD | Meldung „als STEP exportieren“ |

Der Import (`cad_import.nimm`) misst nach Inhalt: STEP mit falscher Endung wird gemessen (mit Hinweis), ein ZIP mit
falscher Endung wird entpackt, eine SolidWorks-Datei mit Endung .step wird abgewiesen statt falsch gelesen.

## 5. Genauigkeit

Bezug: STEP ZNG_10186133 (dieselben drei Teile wie die TRUMPF-Programme 10186133 P10/P20/P30).

| Teil | STEP (Bezug) | alt | neu | Abweichung neu |
|---|---:|---:|---:|---:|
| P20 aus LST/TUBX | 392.821,148 mm³ | 392.102,597 mm³, **ungültig** | 392.821,123 mm³, gültig | −0,025 mm³ |
| P30 aus LST/TUBX | 396.392,331 mm³ | 420.506,519 mm³ (Fenster fehlt) | 396.393,338 mm³ | +1,0 mm³ (Haltestege) |
| P10 aus LST | 1.277.319,648 mm³ | kein Ergebnis (> 20 min) | 1.295.016,285 mm³ | +1,4 % (zwei Kerben über 305°, gemeldet) |
| P10 aus TUBX | 1.277.319,648 mm³ | kein Ergebnis | 1.277.393,474 mm³ (TUBX-Netz) | +0,006 % |
| 35565 BPF/ARTUBE | – | 70.601,868 mm³ | 70.601,868 mm³ | gleich |
| XW1006934 BPF/ARTUBE | 307.800,123 mm³ | 307.773,892 mm³ | 307.773,892 mm³ | gleich |

Schnittlänge, Einstiche und Konturklassen für die Kalkulation kommen bei LST weiter aus dem NC-Weg und sind
unverändert (Test N4). Die aus dem Körper gemessene Konturzahl sinkt bei P20 von 193 auf 14: die 193 waren Splitter des
ungültigen Körpers.

## 6. Zeiten und Speicher vorher/nachher

Je Datei ein Messprozess (`--prozesse 1`), Lesen und Messen zusammen, Zeit = Wanduhr.

| Datei | alt | neu | RAM alt → neu |
|---|---:|---:|---:|
| 10186133 P10 .lst | kein Ergebnis nach > 20 min | 157,7 s | – → 873 MB |
| 10186133 P10 .tubx | (LST daneben, wie oben) | 347,9 s | – → 914 MB |
| 10186133 P20 .lst | 41,1 s | 24,2 s | 417 → 382 MB |
| 10186133 P20 .tubx | 39,9 s | 23,7 s | 418 → 381 MB |
| 10186133 P30 .lst | 29,2 s | 26,6 s | 443 → 498 MB |
| 10186133 P30 .tubx | 28,9 s | 26,8 s | 444 → 498 MB |
| 2026-44094_1 .lst (Auftrag, 2 Rohre) | kein Ergebnis nach 55 min | 213,3 s | – → 878 MB |
| 2026-44094_2 .lst | kein Ergebnis (erster Lauf hing, zweiter Lauf abgebrochen) | 23,8 s | – → 381 MB |
| 35565 .artube / .bpf | 6,3 / 6,5 s | 6,2 / 6,1 s | 299 → 300 MB |
| XW1006934 .artube / .bpf | 32,6 / 32,6 s | 32,7 / 31,8 s | 298 → 300 MB |
| XW1006934 .step | 4,9 s | 5,0 s | 300 MB |
| **144 Prüf-STEPs** (tests/step*) | **400,8 s** | **351,5 s** | gleich |

Nur Lesen (ohne Messen, `lies_*_info`): XW1006934.bpf 12,5 → 10,9 s, 35565.artube 2,1 → 1,5 s, LST P20 → 17 s,
P10 → 52 s. P30 braucht etwas mehr Speicher (+55 MB), weil die Öffnung als zusätzlicher Werkzeugkörper abgezogen wird.

Wo die Zeit bei P10 jetzt liegt: Messung des fertigen Körpers mit 72 Konturen und tausenden Dreiecksflächen der
Kerben (Konturen, Abstände, Flächeneigenschaften). Die Dreh-/Frästeilprüfung darin brauchte 30 Mio.
Richtungsvergleiche und ist jetzt über ein Raster gelöst (gleiches Ergebnis, Test N6).

## 7. Behobene Fehler

1. LST/TUBX P10 hing über 20 min (quadratisches Nähen) → Werkzeugnetz direkt (`_netz_direkt`).
2. LST P20 ungültiger Körper → Werkzeugtiefe an Rohrecken begrenzt (`step_lst.innen_tiefe`: Wand + (R − Wand)/2, wenn
   die Tiefe sonst den Eckmittelpunkt erreicht).
3. Kerbgrund schmaler als die Schnittfuge (0,08 mm) faltete den Fugenrand → Streifen an den Knicken teilen
   (`lst_bahn.streifen_stuecke`).
4. LST P30 Fenster blieb im Körper → zwei offene Schnitte mit Haltestegen bis 2 mm werden zur Öffnung verbunden
   (`step_lst.ketten`), der Abfall wird entfernt wie in der STEP.
5. Nahtsuche (step_naht_zu) prüfte jedes gegenüberliegende Flächenpaar mit einer booleschen Operation (P20: 32.580 Paare,
   108 s, keine Naht) → Vorprüfung mit Hüllquadern, gleiches Ergebnis; Körper aus Maschinenprogrammen ohne Nahtsuche
   (dort gibt es keine Blechnaht).
6. Dreh-/Frästeil-Prüfung verglich jede Flächenrichtung mit allen bisherigen (P10: 30 Mio. Vergleiche) → Raster mit
   exakt derselben Prüfung (`step_drehfraes._Richtungen`).
7. Umbenannte Dateien und Fertigungsaufträge → Erkennung am Inhalt mit klarer Meldung.
8. Fertigungsauftrag mit mehreren Programmen: alle Rohre liegen im Nullpunkt übereinander und wurden als Baugruppe
   ausgewertet (2026-44094_1: P30 als „Verbundkern“ in P10) → Körper aus Maschinenprogrammen ohne Baugruppen-Auswertung.
9. Zwischenspeicher übersah eine geänderte LST neben der TUBX → Begleitdateien im Schlüssel.

## 8. Plausibilitätsprüfungen

- Werkzeugnetz: jede Kante genau zweimal benutzt, sonst Rückfall auf Nähen; Körper mit `OrientClosedSolid` geprüft.
- Öffnung aus offenen Schnitten nur, wenn die Kette geschlossen ist (Stege ≤ 2 mm, höchstens 8 Glieder) und höchstens
  180° des Umfangs umfasst; sonst bleibt der Abfall im Körper und das Programm meldet es.
- TUBX: meldet die LST daneben Abfall in offenen Konturen, misst das Programm das TUBX-Netz und sagt es.
- Formaterkennung: Endung und Inhalt passen nicht → Hinweis; nicht messbarer Inhalt → Fehler statt Fehlmessung.

## 9. Lohnt sich die Profilabwicklung?

Für STEP ja, sie ist seit #650 eingebaut (Abwicklungskern, Vorgabe AN) und wurde hier nicht geändert. Für LST/BPF
nicht als zusätzlicher Schritt: der NC-Weg liegt dort schon abgewickelt vor (Drehachse A und Vorschub), das Programm
wickelt ihn mit lst_bahn auf das Profil. Eine zweite Abwicklung des daraus gebauten Körpers wäre doppelte Arbeit.

## 10. Grenzen

- Kerben, deren zwei offene Schnitte mehr als 180° des Umfangs umfassen (P10: zwei Eckkerben über 305°), behalten den
  Abfall im Körper (nur die Fugen sind abgezogen); P10 hat dadurch 1,4 % mehr Volumen als die STEP. Mit Meldung.
  Grund: eine solche Kette schließt im Rohr einen Deckel ein, der Körper würde falsch.
- Die Haltestege (0,1 mm Rest an jeder Mikroverbindung) bleiben, wie an der Maschine.
- Die Messung der großen STEP ZNG_10186133 dauert über 20 min (dreiteiliges Gestell mit Kerbbiegen); nicht Teil dieses
  Auftrags, steht als Empfehlung unten.
- Der STEP-Rechenkern selbst wurde nicht weiter beschleunigt (siehe #643, #651, #652); die 144 Prüf-STEPs messen
  bitgleich.

## 11. Empfehlungen

1. **Kerben über 180° des Umfangs** (P10): Abfall genau entfernen, wenn die Kette aus offenen Schnitten um die
   Rohrecke läuft; braucht ein eigenes Abwicklungs-Werkzeug statt eines Deckels. Bis dahin misst die TUBX aus ihrem Netz
   (0,006 % an der STEP).
2. **ZNG_10186133 als STEP** dauert über 20 min: eigener Auftrag „Kerbbiegen-Gestell schneller“ mit Profil des
   Kerbbiege-Pfads.
3. **Messung großer Dreiecksnetze** (P10, P10.tubx): Flächen gleicher Ebene vor der Messung zusammenfassen
   (UnifySameDomain nur am Werkzeug, nicht am Teil), dann erneut bitgleich gegen diesen Stand prüfen.
4. **Serverversion**: dateiformat.py und die Leser sind ohne Qt; der Server kann sie unverändert nutzen
   (gleicher Kern, gleicher Zwischenspeicher-Schlüssel).

## 12. Tests

`tests/test_importengine_2611.py` (in tests/alle.py): F1/F2 Formaterkennung und Import nach Inhalt, N1 Werkzeugnetz
direkt, N2 Kerbgrund schmaler als Fuge, N3 Werkzeugtiefe an der Rohrecke, N4 Öffnung aus zwei offenen Schnitten,
N5 Nahtsuche mit Vorprüfung gleich ohne, N6 Richtungsraster gleich dem Vergleich mit allen, C1 Zwischenspeicher.
Außerdem grün: test_regression_ergebnisse, test_cad_kern_3_2411 (Leser-Prüfsumme neu), test_step_importfehler,
test_architektur_2611, test_erkennung_schlitz_naht, test_blm_import, test_lst_schneidweg, test_tubx_import,
test_produktion_lst, test_lst_lernsystem, test_iges_import, test_cad_importkern_2411, test_importengine.
