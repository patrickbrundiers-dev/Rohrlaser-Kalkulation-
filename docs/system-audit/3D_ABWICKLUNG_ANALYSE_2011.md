# 3D-Visualisierung und Abwicklung: Analyse und Umsetzungsplan (20.11.2026)

Auftrag Patrick 20.11.2026, 16:03 UTC: „3D-Visualisierung und Abwicklung auf ein neues Niveau bringen“ (Laserhub als
Vorbild). Dieses Dokument ist Phase 1: Untersuchung des Bestands, Gegenüberstellung vorhanden/gewünscht und der
technische Umsetzungsplan der Phasen 2 bis 7.

Die **Laserhub-Funktionsanalyse** (nur öffentliche Seiten, kein fremder Code) steht schon in
`IMPORTENGINE_LASERHUB_2011.md` aus dem Thread „CAD-Import und Bauteilerkennung nach Laserhub-Vorbild“ (PR #596). Sie
wird hier nicht wiederholt. Für diesen Auftrag zählt daraus:

- Laserhub zeigt ein 3D-Vorschaubild je Teil und prüft die Machbarkeit sofort. Eine **Abwicklung des Rohrs, eine
  Verknüpfung 3D ↔ 2D oder ein Editor sind öffentlich nicht beschrieben**. Laserhub ist ein Marktplatz für
  Sofortpreise, kein Werkzeug der Arbeitsvorbereitung.
- Konstruktionsregeln sind öffentlich: Loch ≥ 0,7 × Wand, Stege und Schlitze ≥ 0,7 × Wand, Eckradien ≥ 0,3 mm,
  Genauigkeit ±0,1 mm, Gehrungen bis ±45°. Diese Regeln prüft unsere Fertigbarkeitsprüfung (Import-Thread).
- Damit liegt die Messlatte für 3D-Viewer, Abwicklung und Editor nicht bei Laserhub, sondern bei Rohr-CAM-Systemen
  (z. B. Lantek Flex3d Tubes, Trumpf TruTops Tube, BLM ArTube). Deren sichtbares Prinzip: Konturen liegen auf der
  echten Rohroberfläche, die Abwicklung ist eine exakte Abbildung dieser Oberfläche, 3D und Abwicklung zeigen
  dieselben Objekte.

## 1. Bestand: Antworten auf die Fragen aus Punkt 8

| Frage | Befund |
|---|---|
| 3D-Bibliothek | Eigene Darstellung in Python: `ansicht3d.py` (QPainter, ohne Grafikkarte) und `ansicht3d_gl.py` (OpenGL 2.1/3.3 über QOpenGLWidget, gleiche Farben über `visualisierung.py`). Keine fremde 3D-Engine, kein numpy im Windows-Paket. |
| STEP-Import | Eigenes Programm `STEP-Import.exe` (`programm/step_messung`, OpenCascade): Körper zerlegen, Profil, Wand, Länge, Enden, Konturen, Gravuren, Nähte, Flächenkatalog (STEP-JSON 1.30), Dreiecksnetz. Läuft als eigener Prozess mit Zeitlimit, Ergebnis im Cache. Erkennung und Prüfdialog: `step.py`, `step_pruefung.py`, `step_dialog.py`; neu `bauteil_analyse.py` (PR #596). |
| Speicherung | Position (`positionen`) mit Eingaben des Schneidweg-Rechners als JSON in `technik` (Enden a/b, Konturen mit art, Maßen, x, seite, q, umriss), Messwerte in `step_merkmale`, Netz gepackt in der Tabelle `netze`. Baugruppe als JSON (`baugruppe`), Satzdaten je Angebot. PostgreSQL je PC. |
| Aktuelle Abwicklung Rohr | `skizze.py` (Geometrie) + `skizze_widget.py` (Modus „Abwicklung“): Umfang aufgerollt, Enden exakt aus der Schnittgeometrie (`ende_abwicklung`, auch komplexe Enden mit gemessenem Umriss), Sonderkonturen und Gravuren mit echtem Umriss aus der STEP-Messung (`step_geometrie._umriss_uv`: Bogenlänge auf der Außenkontur, Eckradien eingeschlossen). Eigenes Fenster `editor_abwicklung.py`, 1:1-Druck `abwicklung_druck.py`, Zeichnung als PDF. |
| Aktuelle Abwicklung Blech | `step_abwicklung.py` (Kantteile aus STEP), Blech-Editor mit Zuschnitt und Biegelinien, **DXF-Export** `dxf.py` (Layer). |
| Performance | Software-Bild großer Baugruppen (127.000 Dreiecke) ≈ 27 s, mit OpenGL 0,07 s. Kanten großer Modelle im Hintergrund vorgerechnet (#584), adaptive Kantenstücke (#591). Messung großer STEP über Zeitlimit je Körper. |
| Erweiterbar | Viewer, Auswahl (`auswahl3d.py`), Messkern (`mess_kern.py`), Schnitt/Explosion, Editor-Werkzeuge (Griffe, Konturwerkzeuge, Mehrfach, Rückgängig, Wiederherstellung), Schneidweg-Rechner (einzige Rechnung der Schnittlängen). |
| Neu zu bauen | Ein **Abwicklungskern ohne Qt** (`abwicklung.py`), der jede Kontur exakt auf die Rohroberfläche abbildet, Bemaßung und **DXF-Export der Rohrabwicklung**. Kennungen je Kontur im 3D-Netz für die Verknüpfung. Alles andere wird erweitert. |

## 2. Gegenüberstellung vorhanden ↔ gewünscht

Stand main 0.9.423 plus #592 (Explosion). „Lücke“ = was fehlt; „Plan“ = Paket unten.

### 2.1 3D-Viewer (Punkt 2)

| Wunsch | Vorhanden | Lücke | Plan |
|---|---|---|---|
| Flüssig und performant | OpenGL-Weg, Umriss beim Drehen, Kanten im Hintergrund, Farb-Cache | Software-Weg bei großen Baugruppen langsam; gleiche Teile werden je Körper neu gezeichnet | P2.1 |
| Hochwertige Kanten | Kantenklassen außen/innen, Knickwinkel, verdeckt gestrichelt, keine Linien durch Wände (#591) | – | – |
| Innen-/Außenflächen | Innenwand eigene Farbe, Prüfmodus Rohrlaser (#591) | – | – |
| Keine durchscheinenden Kanten, auch bei sich kreuzenden Rohren | Verdeckung je Kantenstück gegen alle Körper (#591, Prüfmodelle mit Kreuzung/Durchdringung) | – | Test in P7 erweitern |
| Material/Oberfläche | 6 Materialien, Lichtprofile, Umgebung, Schatten (#584) | – | – |
| Drehen, Verschieben, Zoom, Zentrieren | ja, Mausbelegungen wie Inventor/SolidWorks/Creo, Einpassen | – | – |
| Standardansichten, Isometrie | 6 Ansichten + Iso, Tasten 1–6/0, ViewCube | – | – |
| Schnitt/Querschnitt | bis 3 Ebenen, Wandstärke, Querschnitt im Editor | – | – |
| Ein-/Ausblenden, Transparenz, Hervorhebung | Ausblenden H, Isolieren I, Durchsichtig T, Hervorheben | – | – |
| Große Dateien, viele Teile, Speicher, mehrere Projekte | Zeitlimit, Cache je PC | gleiche Teile mehrfach im Speicher und im GL-Puffer | P2.1 |

Der Viewer ist nach #584 und #591 weitgehend auf dem gewünschten Stand. Offen ist das Tempo bei sehr großen
Baugruppen.

### 2.2 Geometrieerkennung (Punkt 3)

Wird im Import-Thread gebaut (PR #596: 11 Kategorien, Ovalrohre, Merkmalliste mit Konfidenz, Baugruppenanalyse).
Hier wird **nichts doppelt gebaut**. Offen und mit dem Import-Thread abzustimmen:

| Wunsch | Stand | Plan |
|---|---|---|
| Unsichere Geometrie zur Prüfung markieren | Ampel und Konfidenz je Merkmal (#596) | P3.1: unsichere Merkmale im 3D und in der Abwicklung gelb zeigen (nur Anzeige der vorhandenen Konfidenz) |
| Verschneidungen mehrerer Rohre | Durchdringung/Gegenrohr im Editor, Stoßarten in der Baugruppenanalyse (#596) | P3.2: in der Abwicklung als Sattelschnitt mit Gegenrohr anzeigen (Daten aus #596) |

### 2.3 Abwicklung (Punkt 4)

| Wunsch | Vorhanden | Lücke | Plan |
|---|---|---|---|
| Rundrohr automatisch | ja | Bohrungen, Langlöcher, Rechtecke aus Maßen werden **eben** gezeichnet, nicht auf dem Zylinder abgewickelt | P4.1 |
| Vierkant/Rechteck | ja, Umfang inkl. Eckradien | Konturen über Kanten/Radien nur bei gemessenem Umriss exakt | P4.1 |
| Schräge Enden, Gehrungen | exakt (`ende_abwicklung`, gemessener Umriss) | – | Test P7 |
| Rohrverschneidungen (Sattel) | Ende auf Gegenrohr exakt | Durchdringung mitten im Rohr nur als Kontur aus Maßen | P4.1 |
| Durchbrüche/Ausschnitte | Ausschnitt mit Tiefe, Sonderkontur mit Umriss | wie oben | P4.1 |
| Schnittlinien, Konturen | ja, Farben wie im 3D | Kantenlinien der Profilkanten und Radiusbereiche fehlen | P4.2 |
| Bemaßung | Lage der Konturen ab Anfang, Maß je Kontur | Umfangslage, Kettenmaß, Gesamtabwicklung, Toleranzangabe | P4.2 |
| Export DXF und PDF | PDF (Zeichnung), 1:1-Druck | **kein DXF der Rohrabwicklung** | P4.3 |
| Manuelle Korrektur | Ziehen in der Abwicklung, Tabelle, Griffe im 3D | – | erhalten |

**Wie groß ist der Fehler heute?** Eine radial gelaserte Bohrung Ø d im Rundrohr mit Radius R ist auf der
abgewickelten Außenfläche quer zur Achse 2·R·asin(d/2R) breit, nicht d:

| Rohr | Bohrung | Breite in der Abwicklung | Abweichung heute |
|---|---|---|---|
| Ø 42,4 | Ø 8 | 8,05 mm | 0,6 % |
| Ø 42,4 | Ø 20 | 20,83 mm | 4,1 % |
| Ø 33,7 | Ø 20 | 21,41 mm | 7,1 % |
| Ø 60,3 | Ø 40 | 43,73 mm | 9,3 % |
| Ø 42,4 | Ø 30 | 33,33 mm | 11,1 % |

Die **Schnittlänge in der Kalkulation** (π·d bzw. gemessen) ist davon nicht betroffen, nur die Zeichnung der
Abwicklung. Genau das verlangt der Auftrag („keine vereinfachte grafische Darstellung“).

### 2.4 Verknüpfung 3D ↔ Abwicklung (Punkt 5)

| Wunsch | Vorhanden | Lücke | Plan |
|---|---|---|---|
| Kontur im 3D wählen → in der Abwicklung hervorgehoben | Klick im 3D sucht die **nächste Kontur längs der Achse** (`teile_editor._3d_geklickt`), wählt die Zeile, die Abwicklung folgt | Treffer nur über x, bei zwei Konturen auf gleicher Höhe (andere Seite) falsch | P5.1: Kennung je Konturlinie im Netz (`li`, wie beim Blech) |
| Kontur in der Abwicklung wählen → im 3D markiert | Klick wählt die Zeile, das 3D markiert die Kontur | – | Test |
| Änderungen übertragen | jede Eingabe baut 3D und Abwicklung neu | – | – |
| Maße/Positionen synchron | Ziehen in der Abwicklung ändert x/q, 3D folgt | Hover und Maß im jeweils anderen Bild | P5.2 |

### 2.5 3D-Editor (Punkt 6)

| Wunsch | Vorhanden |
|---|---|
| Direkt auswählen, Konturen bearbeiten, Maße ändern | Auswahl Körper/Fläche/Kante, Griffe mit Maß am Mauszeiger, Eigenschaften, Konturwerkzeuge (#571) |
| Rohrpositionen verschieben, drehen | Baugruppe: Steckverbindung/Montage; Editor: Ursprung, Drehen 360° (#571) |
| Schnittwinkel ändern | Enden a/b mit Winkel, Achse, Sattel; Gehrung beide Richtungen |
| Bohrungen/Ausschnitte hinzufügen, löschen, korrigieren | Konturtabelle, Konturwerkzeuge, Ausschnitt mit Tiefe |
| Teilen/Zusammenführen | Satz teilen (Steckverbindung), Baugruppe umwandeln; **Rohr an einer Stelle in zwei Teile teilen** fehlt |
| Rückgängig | ja, mit Verlauf und Wiederherstellung nach Absturz |
| Original ↔ bearbeitet vergleichen | „Alles wie aus STEP importiert“, STEP-Vergleich gegen Mutter-STEP (`step_vergleich.py`); **Überlagerung im 3D** fehlt |

Plan P6.2 (Teilen) und P6.3 (Vergleich als Überlagerung). Der Rest besteht.

### 2.6 Kalkulation (Punkt 7)

Schnittlängen, Einstiche, Anzahl Schnitte, Konturklassen und damit Laser- und Maschinenzeit rechnet **nur**
`schneidweg.py` aus den Eingaben (bzw. gemessenen Längen); Material und Verschnitt `optimierung.py`; Zeit
`rechnen.py`; Ergebnisse je Angebot im Cache (#574) mit gezielter Neuberechnung je Position. Das bleibt so: **keine
zweite Rechnung**. Neu ist nur eine Gegenprobe (P6.1): die exakte Abwicklung liefert die Länge jeder Kontur; weicht
sie von der Kalkulationslänge um mehr als 1 % ab, meldet der Angebots-Check die Kontur. Kalkulationsformeln ändern
sich nicht.

## 3. Architektur

```
STEP ──► STEP-Import.exe (Messung, Umriss auf der Außenkontur, Flächenkatalog)
            │
            ▼
   Position: Eingaben (Konturen, Enden) ── schneidweg.py ──► Schnittlängen, Einstiche ──► rechnen.py ──► Kalkulation
            │                                   ▲ Gegenprobe (P6.1, nur Meldung)
            ▼                                   │
   abwicklung.py (NEU, ohne Qt): jede Kontur als Linienzug (s am Umfang, x längs) auf der echten Außenfläche,
            │                  Kennung = Konturzeile; Profilkanten, Radiusbereiche, Naht, Bemaßung
            ├──► skizze_widget (Modus Abwicklung) ── Klick/Hover ──┐
            ├──► dxf_rohr_abwicklung.py (NEU): DXF R12 mit Layern │  Kennung „kontur:n“
            ├──► Zeichnung PDF, 1:1-Druck                         │
            └──► rohr3d.netz: Konturlinien mit Kennung (li) ◄─────┘──► ansicht3d / auswahl3d
```

Grundsätze: eine Abbildung Oberfläche → Abwicklung (`skizze.Querschnitt` mit Bogenlänge s, wie die Messung); die
3D-Konturlinien und die Abwicklung kommen aus derselben Linie; gemessene Umrisse aus der STEP haben Vorrang (100 %
STEP); Kalkulation bleibt bei `schneidweg.py`.

## 4. Umsetzungsplan

Reihenfolge nach Nutzen: zuerst die Abwicklung (größte Lücke), dann die Verknüpfung, dann Kalkulation und Editor,
zuletzt Tempo. Jedes Paket mit Tests, Anleitung, Neuerungen und Vorher-Nachher-Bildern.

| Paket | Inhalt | Prüfung (Sollwerte) |
|---|---|---|
| **P4.1 Abwicklungskern** | `abwicklung.py`: jede Kontur aus Maßen wird als 3D-Kurve auf der Rohroberfläche gebildet (radiale Projektion wie der Laser schneidet, Rundrohr: Zylinder; Rechteck: Flächen + Eckradien) und über die Bogenlänge s abgewickelt; Konturen mit gemessenem Umriss unverändert; Durchdringung als Sattelkurve; Skizze nutzt den Kern | Bohrung Ø 30 in Ø 42,4: Breite 33,33 mm; Umfang = Profilumfang; Bohrung auf Rechteckfläche unverändert d; Länge der abgewickelten Kurve = 3D-Kurvenlänge ±0,01 mm |
| **P4.2 Bemaßung und Linien** | Profilkanten und Radiusbereiche als Linien, Naht, Maße: Länge, Umfang, Lage x und s je Kontur, Kettenmaß wählbar | Maße gegen Eingaben |
| **P4.3 DXF/PDF** | DXF R12 der Rohrabwicklung (Layer KONTUR, ENDE, GRAVUR, KANTE, NAHT, BEMASSUNG), 1:1 in mm; PDF mit Bemaßung; Knopf im Editor und im Abwicklungsfenster | DXF zurücklesen: Kontur = Kern ±0,01 mm |
| **P5.1 Kennungen** | Konturlinien im Rohr-Netz mit Kennung „kontur:n“/„ende:a“; Klick im 3D wählt genau diese Kontur | zwei Bohrungen gleicher Höhe, gegenüber: richtige Zeile |
| **P5.2 Hover und Maß** | Überfahren hebt in 3D und Abwicklung dieselbe Kontur hervor, Maß x/s im anderen Bild | – |
| **P6.1 Gegenprobe** | Konturlänge aus der Abwicklung gegen Kalkulationslänge, Angebots-Check meldet > 1 % | keine Kalkulation ändert sich (Regressionstest der Ergebnisse) |
| **P6.2 Rohr teilen** | Rohr an Stelle x in zwei Positionen teilen (Konturen verteilt, Enden gerade) | Summe Längen, Konturen vollständig |
| **P6.3 Vergleich** | Original-STEP und Bearbeitung im 3D überlagert (Abweichung farbig) | – |
| **P3.1/P3.2** | unsichere Merkmale gelb in 3D und Abwicklung; Verschneidungen aus #596 anzeigen | mit Import-Thread |
| **P2.1 Tempo** | gleiche Teile einer Baugruppe als eine Netzkopie mit Lagen (Instanzen), weniger Speicher, GL-Puffer je Teil einmal | Speicher und Zeit vorher/nachher |
| **P7** | Referenzteile mit Sollwerten (Rundrohr Gehrung 45°, Sattel Ø 42,4 auf Ø 60,3, Rechteckrohr mit Bohrung über Radius), Test 3D ↔ Abwicklung, DXF zurücklesen, Regressionstest der Kalkulation | alle grün |

Verbindlich (Punkt 11): bestehende Funktionen bleiben; keine zweite Rechnung; Formeln unverändert; jede neue
Funktion mit Test und Anleitung; Arbeit auf eigenem Git-Zweig mit PR; alte Projekte bleiben lesbar (neue Felder nur
zusätzlich, Netze ohne Kennung funktionieren wie bisher).

## Stand 20.11.2026 (Paket 1, PR „Exakte Rohrabwicklung“)

- P4.1–P4.3, P5.1/P5.2, P6.1, P6.2, P6.3, P3.1 umgesetzt (`abwicklung.py`, `rohr_teilen.py`, Tests
  `test_abwicklung_exakt.py`, `test_rohr_teilen.py`).
- Korrektur zur Analyse: Die Lage der Bohrungen am Rundrohr folgt der bestehenden Regel vom 26.10.2026 (2D innen
  maßhaltig, außen breiter; 3D eben außen wie gezeichnet, `rohr3d.loch_poly`). Die Abwicklung nutzt genau diese
  Rechnung; eine eigene asin-Formel gibt es nicht.
- Gegenprobe (nur Hinweis, nichts geändert): Schneidweg Bohrung Ø 30 auf Rundrohr Ø 42,4 rechnet 105,3 mm, der Rand
  auf der Außenhaut ist 99,1 mm; Rechteck 20 × 20 bis in den Eckradius rechnet 80 mm (eben), auf der Außenhaut
  89,4 mm. Ob die Rechnung angepasst wird, entscheidet Patrick (Formeländerung).
- Offen: P3.2 Verschneidungen anzeigen, P2.1 Instanzen, P7 Referenzteile.
