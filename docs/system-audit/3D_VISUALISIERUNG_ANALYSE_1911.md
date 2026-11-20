# 3D-Visualisierung – Analyse (Phase 1) und Plan V2–V7 (19.11.2026)

Auftrag Patrick 19.11.2026 20:06 UTC „GROßES 3D-VISUALISIERUNGSUPDATE“ (16 Punkte, Phasen 1–7). Dauerfreigabe:
die Empfehlungen setze ich selbst um. Grundregeln, die für jede Phase gelten:

* Die Geometrie wird nie ungenauer: das Netz aus der STEP-Messung bleibt, wie es ist. Grobe Stufen gibt es nur
  beim Drehen; sobald die Maus ruht, wird wieder das volle Netz gezeichnet.
* Konturen stimmen zu 100 % mit der STEP überein. Bauteile werden nie verschoben.
* Explosion und Schnitt ändern nur die Anzeige, nie das Teil, den Export oder die Kalkulation.
* Eine Engine für alle 3D-Fenster (Ansicht3D): STEP-Viewer, Anhang-Vorschau, Teile-, Blech-, Baugruppen- und
  Satz-Editor bekommen jede Änderung gleichzeitig.

## 1. Bestand

| Baustein | Datei | Stand |
|---|---|---|
| Ansicht (eine für alle Fenster) | `ansicht3d.py` (Ansicht3D, Modell, zeichnen) | Software-Zeichnen mit QPainter, Bild wird gemerkt, solange sich nichts ändert |
| OpenGL | `ansicht3d_gl.py` (GLFlaeche) | GLSL 1.20, Gouraud, 4× MSAA, Tiefenpuffer; fällt bei jedem Fehler auf Software zurück |
| Kamera | `navigation3d.py` | freie 360°-Drehung (Matrix), Drehteller, Tempo, Umkehren, Drehzentrum, Nachlauf |
| Auswahl | `auswahl3d.py` | Körper/Fläche/Kante/Punkt, Fenster, Filter, Ausblenden, Isolieren, Umkehren, Gruppen |
| Leiste | `ansicht3d_leiste.py` | gemeinsame Knöpfe aller 3D-Fenster |
| Darstellungen | `DARSTELLUNGEN` | Schattiert, Mit Kanten, Durchsichtig, Drahtgitter, Verdeckt gestrichelt (5) |
| Licht | `LICHT`, `LICHT2`, `LICHT_WERTE` | ein festes Profil (Grund-, Haupt-, Füll-, Glanzlicht) |
| Einstellungen | `stammdaten.EINSTELLUNGEN`, Seite „3D-Navigation“ | je Arbeitsplatz (`teilen.LOKAL`), keine Profile, kein Export/Import |
| Flächenkatalog | Netz `fk`/`tf` (STEP-JSON 1.30, M3) | Ebene/Zylinder/Kegel/Kugel/Torus/Freiform je Dreieck |

## 2. Messungen (Software-Zeichnen, 1200 × 800, ohne Grafikkarte)

| Modell | Dreiecke | Modell bauen | Körperkanten | Flächen gruppieren | Bild fein | Bild beim Drehen |
|---|---:|---:|---:|---:|---:|---:|
| REF03 | 288 | – | – | – | 95 ms | – |
| RP04 | 3 032 | – | – | – | 277 ms | – |
| REF15 | 38 779 | 67 ms | 331 ms | 332 ms | 284 ms | 147 ms |
| S01 (12 Teile) | 2 432 | – | – | – | ≈ 260 ms | – |

Kantenglättung allein (ein Dreiecksbild, gleiches Modell):

| Kantenglättung | Fläche | ms je Bild |
|---|---|---:|
| an | 1200 × 800 | 30,8 |
| an | 600 × 400 | 10,3 |
| aus | 1200 × 800 | 4,2 |
| aus | 600 × 400 | 3,1 |

Befunde:

1. **Software-Bild:** Beim Drehen ist die Kantenglättung schon aus. Die 147 ms kommen also von der Rechnung je
   Dreieck in Python (Drehen, Licht, Sortieren). Weniger Pixel helfen hier kaum, weniger Python-Arbeit je Dreieck
   hilft viel.
2. **Körperkanten und Flächen** (je ≈ 330 ms bei 39 000 Dreiecken) werden beim ersten Gebrauch im Vordergrund
   gerechnet. Das spürt man als Hänger beim ersten Klick auf „Mit Kanten“ oder beim ersten Wählen einer Fläche.
3. **OpenGL** zeichnet dasselbe Modell aus Puffern auf der Grafikkarte. Das Hochladen geschieht einmal je Modell.
   Bremsen gibt es nur bei „Drahtgitter“ und „Verdeckt“: Dort wird der Umriss der Rundungen in jedem Bild in Python
   neu gerechnet und hochgeladen.
4. **Licht und Farbe** sind fest. Es gibt kein Material (Rohstahl, Edelstahl …), kein Lichtprofil, keinen Schatten
   und keinen wählbaren Hintergrund.
5. **Einstellungen:** Die Navigation steht in einer eigenen Seite. Die Darstellung (Renderer, Raster, Achsen) ist
   verstreut über Einstellungen und Merker. Es gibt keine Profile und kein Export/Import.
6. **STEP-Viewer:** Die Anhang-Vorschau misst schon im Hintergrund (ThreadPool). Modell, Kanten und Flächen
   entstehen danach aber im Vordergrund. Das führt bei großen Dateien zu einem kurzen Einfrieren ohne Fortschritt.

## 3. Plan V2–V7 (meine Empfehlung, wird so gebaut)

### V2 – Material, Licht, Hintergrund (Punkte 1–3)

* `visualisierung.py` (ohne Qt) wird die eine Quelle für Material-, Licht- und Hintergrundprofile.
  * Material: Rohstahl, Edelstahl, Aluminium, Lackiert, Gebürstet, Matt. Jedes Material bringt Grundfarbe,
    Glanz, Glanzbreite und Körnung mit.
  * Licht: Werkstatt (heutiges Licht), Studio, Hell, Technisch (flach).
  * Hintergrund: Verlauf, Weiß, Dunkel.
* Das Material färbt nur die neutralen Flächen. Konturen, Gravuren, Nähte und Kostentreiber behalten ihre
  Signalfarben, sonst ginge Information verloren.
* Beide Renderer lesen dieselben Werte: QPainter über `licht_wert`, OpenGL über Uniforms. Gebürstet als
  richtungsabhängiger Glanz entlang der Rohrachse.
* Kontaktschatten unter dem Modell als weicher Schatten auf der Bodenebene. Echte Schattenkarten gibt es nicht:
  GLSL 1.20 und Software-Fallback müssen gleich aussehen.

### V3 – Tempo (Punkte 4, 10)

* Körperkanten und Flächen nach dem Laden im Hintergrund vorrechnen. Der STEP-Viewer zeigt dabei einen Fortschritt
  („Netz … Kanten … Flächen“). Er friert nicht ein, Fenster und Knöpfe bleiben bedienbar.
* Software-Zeichnen: Drehung und Licht je Ecke statt je Dreieck rechnen und Ergebnisse zwischenspeichern.
  Gleiche Teile im Satz/Baugruppe einmal rechnen und mehrfach zeichnen (Instanzen).
* OpenGL: Umriss für Drahtgitter/Verdeckt nur bei Ruhe neu rechnen. Beim Drehen wird der letzte Umriss gezeigt.
  Rückseiten werden im Shader verworfen (gibt es schon), Teile außerhalb des Bildes werden übersprungen (Culling).
* Messgröße im Test: Bildzeit beim Drehen REF15 Software ≤ 100 ms, OpenGL unverändert flüssig.

### V4 – Navigation (Punkt 5)

* Bestehende Einstellungen bleiben. Neu:
  * Mausbelegung als Vorlage: Programm-Standard, „wie Inventor“, „wie SolidWorks“, „wie Creo“. Es werden nur
    Tastenbelegungen übernommen, kein Fremdcode.
  * Zoomrichtung umkehren, weicher Zoom.
  * Nachlauf-Stärke statt nur ein/aus.
* Navigation wechselt auf die neue Einstellungsseite (V7).

### V5 – Darstellungsarten, Kanten, Auswahl, Live-Vorschau (Punkte 6–7, 11)

* Zehn Darstellungen. Die fünf bestehenden bleiben, dazu kommen:
  * Verdeckt ausgeblendet (Linienbild ohne verdeckte Kanten)
  * Flächentypen (aus dem Katalog fk: Ebene, Zylinder … farbig)
  * Konturen betont (Rest grau)
  * Realistisch (Material + Schatten)
  * Kanten + Durchsichtig
* Kanten: Stärke und Farbe einstellbar, Silhouette betont.
* Auswahl:
  * Hervorheben beim Überfahren (Hover) in allen Fenstern.
  * Gewähltes durchsichtig/isoliert. Isolieren und Umkehren gibt es schon und bekommen Knöpfe in der Leiste.
* 3D-Editor: Live-Vorschau beim Ziehen von Werten mit grober Stufe. Bei Ruhe wird exakt neu gerechnet; die
  Rechnung bleibt der eine Weg über die Kalkulation.

### V6 – Schnitt und Explosion (Punkte 8–9)

* Bis zu drei Schnittebenen, frei drehbar (Griff oder Werteingabe).
* Schnittfläche gefüllt, mit Wandstärke-Farbskala aus der Messung. Die Messung zeigt die Wandstärke an der
  Schnittstelle (mess_kern, ein Rechenweg).
* Explosion für Baugruppe und Satz: Stärke als Schieber, Richtung aus der Lage der Teile. Nur Anzeige: Netz,
  Export und Kalkulation bleiben unverändert (eigener Test).
* Explosionsansicht speichern (Name je Baugruppe) und als Bild/PDF ausgeben.

### V7 – Zentrale Einstellungen, Profile, Qualitätskontrolle (Punkte 12–16)

* Eine Einstellungsseite „3D-Darstellung“ mit allen Werten. Darin:
  * Renderer, Material, Licht, Hintergrund, Raster, Achsen, Darstellung und Kanten.
  * Navigation und Fangen.
* Profile je Benutzer und Arbeitsplatz (lokal, nie abgeglichen), Export/Import als JSON-Datei.
* Automatische Qualitätskontrolle:
  * Selbsttest beim Start der ersten 3D-Ansicht (Bildzeit, OpenGL-Fehler → Software mit Hinweis).
  * Bildvergleich-Tests offscreen für jede Darstellung.
  * Netzprüfung `netz_pruefen` bleibt.
  * Test „Explosion/Schnitt ändern das Netz nie“.
* Anleitung, Vorher-Nachher-Bilder je Phase, Tests in `tests/alle.py`.

## 4. Reihenfolge

V2 → V3 → V4 → V5 → V6 → V7. Je Phase ein PR über den Merge-Thread. Messplan M4 und CAD C1–C7 laufen danach im
selben Thread weiter, wie vereinbart. „Maße je Position speichern“ (Schema +1) kommt zwischen V3 und V4, wenn kein
anderer Thread am Schema ist.
