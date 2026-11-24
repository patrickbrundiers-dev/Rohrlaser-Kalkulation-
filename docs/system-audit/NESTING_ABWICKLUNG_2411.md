# Nesting: Stangenabwicklung und 3D auf CAD/CAM-Niveau (24.11.2026)

Auftrag Patrick 24.11.2026 16:39 UTC („Master-Entwicklungsprompt: Nesting-Arbeitsplatz – Stangenabwicklung auf
CAD/CAM-Niveau und realistische 3D-Darstellung“). Plan A1–A6: https://claude.ai/artifact/6N3zhyFB4r43XTBufLoDVK

## Grundsatz: eine Quelle

Alle Ansichten lesen dieselben Stangen des Nesting-Ergebnisses (Format des Schnittplans, `nesting_vergleich.anzeige_stangen`
bzw. `ergebnis["stangen"]`): je Teil `von`, `bis`, `laenge`, `drehung`, dazu Endbeschnitt, Schnittfugen, Rest und
Greiferrest (`stangen_ansicht.bereiche`). `nesting_abwicklung.py` rechnet keine eigene Lage, es legt nur die
Geometrie jedes Teils an seinen Platz. Der Test vergleicht von/bis/Drehung jedes Teils mit dem Nesting-Ergebnis.

## Bausteine

| Datei | Inhalt |
|---|---|
| `nesting_abwicklung.py` (neu) | `stange()` Abwicklung je Stange: Umfang der echten Außenhaut (`abwicklung.Mantel`, Eckradien), Seiten, Radiusübergänge, Naht, Schnittkanten und Konturen je Teil aus `abwicklung.linien` (dieselben Linien wie Teile-Editor, DXF und 3D); Drehung = Verschiebung um Drehung/360 × Umfang, gewendet = gespiegelt; `kennzahlen`, `koordinaten`; `netz_stange()` 3D mit `ansicht3d.baugruppe` und Lage je Teil |
| `nesting_abwicklung_bild.py` (neu) | Zeichnung: maßstäblich, waagerecht/senkrecht, Umfang gestreckt oder 1:1, Ebenen (Bemaßung, Schnitte, Konturen, Reste, Seiten/Winkel), Zoom an der Maus, Verschieben, Messen, Auswahl, Rechtsklick; technische Variante mit Koordinaten |
| `nesting_dialog.py` | Ansichten Abwicklung · 3D · Technisch · Alle Stangen · Stangenbild, Ansicht gemerkt (`nesting_ansicht`), Stangenliste, Blättern, Infopanel Stange/Teil |
| `ansicht3d.py` | neue Art `RS` (Endbeschnitt, Rest, Greiferrest) |

## Moderne Ansichten (Plan M1–M7, Patrick 24.11.2026 18:06 „Alles einbauen nach Empfehlung“)

Plan: https://claude.ai/artifact/BEYDazZSK1UCxKE22ARest

| Paket | Umsetzung |
|---|---|
| M1 Werkzeugleiste | `nesting_ansicht_ui.knopf/segment`: Ansichten als Segmentschalter mit Symbol (Strg+1–5), Zoom als Symbolknöpfe, Ebenen-Menü, Stangenwahl „Stange 1 von 3“, Tasten M/S |
| M2 Abwicklung | `ruhig()` Palette (Teilfarbe zu 55 % Weiß), Rand in dunkler Teilfarbe, Zeigen mit Tooltip, Auswahl mit Schein, Konturen gefüllt, Gravur gestrichelt, Raster nach Zoom, Legende, ISO-Maßpfeile |
| M3 3D | Farben aus der Abwicklung (`netz_stange(farbe_ref=)`), `Ansicht3D.einpassen_auf` (gewähltes Teil, sonst erste 1,5 m), Schilder je Teil (`Ansicht3D.schilder`), Rest halb durchsichtig, Klick wählt das Teil über z |
| M4 Technisch | Zeile ↔ Teil/Stelle (Fadenkreuz), PDF (QPdfWriter A4 quer) und DXF (`nesting_abwicklung.dxf_elemente`) |
| M5 Infopanel | `InfoKarte` (Stange mit Ausnutzungsbalken, Teil mit 3D-Vorschau), rechte Spalte rollt als Ganzes |
| M6 Stangenliste | `StangenDelegate` mit Belegungsbalken |
| M7 Stil | `stange_zeichnen(ruhig=True)` unter „Alle Stangen“; das Stangenbild bleibt bewusst wie in der Optimierung; hell/dunkel geprüft |

## 3D: keine falsche Geometrie

* Je Teil das gespeicherte STEP-Netz der Position (Rohrachse z ab Ende A). Es wird nur gezeigt, wenn seine z-Ausdehnung
  zur Teillänge passt (±1 mm + 0,5 %). Sonst wird nichts gestreckt: das Teil kommt aus den Eingaben (`rohr3d.netz`,
  wie im Teile-Editor) und der Grund steht unter dem Bild.
* Lage = Verschiebung um `von`, Drehung um die Rohrachse wie in der Abwicklung; gewendet: um die senkrechte Achse.
* Die bisherige 3D-Ansicht (Kästen, Querschnitt 8-fach überhöht, ohne Gehrungen und Konturen) ist ersetzt.

## Tempo

* Abwicklung: gleiche Teile (Position + Länge) einmal gerechnet, je Stange zwischengespeichert; QR 40×40×3 mit 11
  Teilen ca. 50 ms beim ersten Mal, danach aus dem Speicher.
* 3D nur für die sichtbare Stange, Netze je Position zwischengespeichert.

## Tests

`tests/test_nesting_abwicklung.py` (neu, in `tests/alle.py`): Rund-, Quadrat- (Wand 3 und 5) und Rechteckrohr,
Lage/Drehung/Bereiche gegen das Nesting, Umfang mit Eckradien, Bohrung, Langloch, Gravur, Gehrung, gewendete Teile,
3D-Lage, STEP-Netz passend/unpassend, Tempo und Merker, Zeichnung (Ebenen, waagerecht/senkrecht, Bildpunkt ↔ mm).
`tests/test_nesting_arbeitsplatz2.py` erweitert: Dialog mit Abwicklung, Technisch, 3D, Stangenliste, Infopanel und
gemerkter Ansicht an einem echten Angebot.

## Grenzen

* Sonderprofile ohne Querschnitt aus dem Profilstamm: keine Abwicklung (Hinweis „Ohne Daten: Pos. …“).
* Zuschnitt beim Lieferanten (12 m): die Stücke legt der Zuschnitt fest, dafür keine Abwicklung.
