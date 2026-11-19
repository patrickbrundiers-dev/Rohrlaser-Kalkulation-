# CAD- und Messplan nach SolidCraft-Vorbild

_Stand 19.11.2026, Basis main 0.9.401 (nach #568/#569), #571 in Arbeit. Nur Analyse und Plan, kein Code geändert._

Artifact-Seite: https://claude.ai/artifact/3d1PmSuLgm3LywaJpQ7ybT

## Kurzfassung

- SolidCraft (app.solidcraft.io, docs.solidcraft.io) ist ein quelloffenes parametrisches CAD in Rust (Lizenz MIT oder Apache-2.0). Der Geometriekern „solidcore“ ist laut Doku eine Rust-Portierung von NVIDIAs SMLib, die NVIDIA am 09.10.2026 als USD BRep unter Apache-2.0 freigegeben hat.
- Unser Programm hat schon einen großen Teil dessen, was SolidCraft für die Rohrlaserarbeit bietet: exakte Messwerte aus den Eingaben, Fangen, Auswahl mit Filter und Fenster, Rückgängig mit Verlauf, Wiederherstellung, STEP-Gegenprobe und Exportvergleich. Es fehlen vor allem dauerhafte Maße im Modell, Abstände zwischen Flächen und Kanten, Volumen/Masse/Schwerpunkt im Viewer, Interferenz, Bauteilvergleich mit Farbkarte, benannte Parameter mit Formeln, eine Merkmal-Zeitleiste mit Unterdrücken und ein 2D-Konturskizzierer mit Bedingungen.
- Empfehlung: Variante A (Ausbau im Bestand) mit dem Zusatz aus Variante B (OCCT-Dienst für schwere Analysen). SolidCraft-Code wird nicht übernommen. Die Lizenz würde es erlauben, aber Sprache (Rust), Reifegrad (laut Doku „early“) und ein zweiter Geometriekern neben OpenCascade passen nicht zur Regel „Konturen 100 % wie STEP“. Übernommen werden nur Konzepte.
- Reihenfolge: erst das Messsystem (M1 bis M4), dann die CAD-Phasen (C1 bis C7). Gebaut wird im Thread „3D-Editor, Einstellungen und neue Funktionen ausbauen“ nach dem Merge von #571.

## Bestandsaufnahme

| Bereich | Dateien | Was es schon gibt |
|---|---|---|
| STEP-Import | step.py, step_messung/* (OCP = OpenCascade, eigener Prozess) | Messung als eigener Prozess (Absturzschutz). Profilabgleich ±0,15 mm, Konturklassen, Gegenprobe, IGES, Volumen und Fläche über BRepGProp, Abstände über BRepExtrema. |
| 3D-Darstellung | ansicht3d.py (QPainter), ansicht3d_gl.py (OpenGL 2.0) | Dreiecksnetz {p, t, l} mit Arten, Rohrachse = Z. OpenGL mit Rückfall auf QPainter. Im GUI-Prozess gibt es keinen B-rep, nur Netz und 'geo' (exakte Kreise/Kanten aus den Eingaben). |
| Modell aus Eingaben | rohr3d.py, blech3d.py, skizze.py, schneidweg.py | Der Editor ist bereits eingabe-parametrisch: Profil, Enden und Konturzeilen erzeugen das Netz bei jeder Änderung neu. Damit ist er der Sache nach schon eine Merkmalsliste. |
| Messen | messen3d.py, ansicht3d.py (Abstand/Winkel), editor_schnitt.py, editor_mehrfach.py | Exakte Kernwerte (Kreis Ø/Mitte/Achse, Kante, Ebene, Rohrmantel), Wandstärke per Strahl, Vergleich zweier Elemente, Punkt–Punkt mit Δx/Δy/Δz, Winkel aus 3 Punkten, Querschnitt, Abstand zweier Konturen. Mess-Tafel mit Kopieren. |
| Auswahl und Fangen | auswahl3d.py (+ #571: alle/umkehren/Gruppe) | Körper/Fläche/Kante/Punkt, Strg+Klick, Fensterauswahl in beiden Richtungen, Filter, Ausblenden/Isolieren, Flächenmaße. Fang: Kreismitte, Konturmitte, Kantenmitte, Ecke, Punkt auf Linie, Fläche. |
| Bearbeiten | editor_griffe.py, editor_ausschnitt.py, editor_mehrfach.py, kontur_werkzeuge.py (#571) | Ziehgriffe, Ausschnitt mit Tiefe, Mehrfachbearbeitung, Drehen/Versatz/Verlängern/Reihe/Ellipse/Vieleck, Artikelnummer-Gravur. |
| Verlauf und Sicherheit | teile_editor.py (QUndoStack), editor_wiederherstellung.py, bg_verlauf.py | Rückgängig/Wiederholen mit Namen und Sprung im Verlauf, Wiederherstellung nach Absturz, Rückgängig auch in Baugruppe und Satz (#564). |
| Prüfen | step_gegenprobe.py, step_pruefung.py, step_messung/step_vergleich.py, dfm.py, geometrie.py | 3D-Gegenprobe vor dem Prüfdialog, Fertigungsregeln, Exportvergleich mit der Mutter-STEP (gemeinsames Volumen, Schwerpunktversatz), Kennzeichen „nur kalkuliert“. |
| Baugruppen | baugruppe_step.py, satz3d.py, baugruppe_dialog.py, bg_schwerpunkt.py | Teile in Einbaulage der STEP, Steckverbindungen, Knickrahmen, Längsnaht per Klick, Schwerpunkt der Baugruppe. |
| Navigation und Oberfläche | navigation3d.py (#571), editor_arbeitsbereich.py | Freie 360°-Drehung (#571), Werkzeugleiste am 3D, Reiter Merkmale/Verlauf/Ebenen, Statuszeile mit Koordinaten, Achsenkreuz/Raster, Dunkelmodus. |

## Gegenüberstellung

| Bereich | SolidCraft | Bestand | Entwicklungsbedarf | Machbarkeit | Aufwand | Nutzen | Performance | Kompatibilität |
|---|---|---|---|---|---|---|---|---|
| Messsystem | Measure, Mass Properties, Clearance, Section Analysis; Messwerte aus dem B-rep. | Exakte Einzelwerte, Punkt–Punkt, Winkel aus 3 Punkten, Wandstärke, Querschnitt. Keine dauerhaften Maße. | Gemeinsamer Messkern für alle Fenster, Direktmessung bei Auswahl, Kante/Fläche-Abstände, Mindestabstand, dauerhafte Maßlinien, Export/PDF, Speichern. | hoch | M | sehr hoch | unkritisch | sehr gut |
| Geometrieprüfung | Interference, Clearance, Compare Bodies, Curvature, Minimum Radius, Zebra. | Gegenprobe, Fertigungsregeln, Exportvergleich mit Volumen und Schwerpunkt. | Interferenz/Kollision in Baugruppe und Satz, Bauteilvergleich mit Farbkarte (max./mittlere Abweichung, Ort), offene Körper, doppelte Flächen und Konturen. | mittel | L | hoch | im Dienst-Prozess (B) | gut |
| Parametrische Maße | Jedes Maß ist ein Parameter (d1, d2 …), Benutzerparameter mit Einheit, Formeln, Umbenennen, Kreisbezüge erkannt, Parameter-Sweep. | Alle Konturen haben Maße und Lage als Eingabe; Rechenfeld ohne eval (#571). Keine Namen, keine Verknüpfung. | Parametertabelle je Teil, Namen in jedem Zahlenfeld („breite = 40“), Formeln, Abhängigkeiten anzeigen, STEP-Maße nur als Referenz. | hoch | M | hoch (Teilefamilien) | unkritisch | sehr gut |
| Feature-Timeline | Zeitleiste getrennt vom Rückgängig: Rollback-Marker, Unterdrücken, Umordnen, Ordner, Abhängige, Fehler am Schritt. | Konturtabelle und Merkmalsbaum sind schon Merkmale; Verlauf zeigt nur die Rückgängig-Schritte. | Schritt 0 „STEP-Import“ (gesperrt), Merkmale umbenennen, aktiv/unterdrückt, Rollback, fehlerhafte Schritte rot, Abhängigkeiten (Kontur liegt auf Fläche/Ende). | hoch | M | hoch | unkritisch (Netz wird schon neu gebaut) | gut |
| Skizzenerstellung | Voller 2D-Skizzierer: Linie, Bogen, Kreis, Rechteck, Langloch, Polygon, Ellipse, Spline, Text; Bedingungen und Bemaßungen mit Solver; DXF. | skizze.py zeichnet nur die Eingaben; Sonderkontur über Umriss; blech_zeichnen, DXF-Import. | 2D-Konturskizzierer auf einer Rohrfläche oder der Abwicklung mit kleinem Bedingungslöser. Ergebnis ist eine Sonderkontur mit Umriss, damit die Rechnung unverändert bleibt. | mittel | XL | mittel bis hoch | gut (2D) | gut |
| Konturbearbeitung | Trim, Extend, Break, Fillet, Chamfer, Offset, Muster, Spiegeln. | Griffe, Mehrfachbearbeitung, Reihe, Versatz, Drehen, Verlängern (#571). | Ecken abrunden/fasen an Polygon und Sonderkontur, Trimmen/Teilen im Skizzierer, Lochbild (Kreis/Raster), Kontur auf anderes Profil übertragen. | hoch | M | hoch | unkritisch | sehr gut |
| 3D-Bearbeitung | Extrude, Revolve, Sweep, Loft, Boolean, Fillet, Shell, Split, Offset Face. | Rohr und Blech aus Eingaben; Ausschnitt mit Tiefe, Sattel/Gegenrohr; Booleans nur beim STEP-Export im Messprozess. | Kein allgemeines Volumen-CAD. Nur rohrlaserbezogen: Rohr-auf-Rohr, schräge Enden, Projektion von Konturen, Durchbrüche. Booleans bleiben im OCCT-Prozess. | mittel | L | niedrig bis mittel | hoch, nur im Dienst | riskant für 100-%-Regel |
| Baugruppen | Komponenten, Gelenke, Stückliste, Massen, Explosion, Kontaktsätze. | Baugruppe aus STEP, Satz, Schweißbaugruppe, Stecksystem, Schwerpunkt. | Kollision/Überschneidung, Komponenten nur dann verschieben/ausrichten, wenn sie im Programm entstanden sind (STEP-Teile nie verschieben), Baugruppenvergleich. | mittel | L | mittel | im Dienst-Prozess | gut |
| STEP-Import | Eigener STEP-Leser; verknüpfte Designs, Flächennamen über Geometrie-Abgleich (F…:link:…). | Sehr ausgereift (OCP), Profilerkennung, Gegenprobe, Importbericht. | Beim Import zusätzlich einen Flächenkatalog speichern (Kennung, Art, exakte Parameter, Fläche, Hülle, geschlossen ja/nein). Damit misst der Viewer STEP-Teile exakt ohne OCCT im Programm. | hoch | M | hoch | einmalig beim Import | sehr gut |
| Undo/Redo | Undo/Redo, Checkpoints mit Namen, Befehl wiederholen. | QUndoStack mit Verlauf, Wiederherstellung, BG/Satz. | Benannte Stände („Stand merken“), Messungen und Parameter als eigene Rückgängig-Schritte. | hoch | S | mittel | unkritisch | sehr gut |
| Auswahl und Fangen | Select Other (Durchschalten unter dem Mauszeiger), Fenster/Kreuzen, Filter, Fang-Vorhersage im Skizzierer. | Filter, Fenster, Ausblenden/Isolieren, 6 Fangarten in fester Reihenfolge. | Fangarten einzeln ein/aus: Endpunkt, Mitte, Kante, Schnittpunkt, Kreismitte, Tangente, Fläche, Achse, Koordinate; „Andere wählen“; Auswahl nach Kontur und Bauteil. | hoch | M | hoch | unkritisch | sehr gut |
| Oberfläche | Reiter-Werkzeugleiste, Browser links, Zeitleiste unten, Befehlssuche (Taste S), Tastenkürzel editierbar, Navigationsvorlagen, Themen. | Menüband, linke Reiter, Statuszeile, Dunkelmodus, 360°-Drehung (#571). | Reiter „Messen“ und „Prüfen“, Befehlssuche, Tastenkürzel anpassen, Navigationsvorlagen, unten Zeitleiste/Meldungen. | hoch | M | mittel | unkritisch | gut |

Aufwand: S = Tage, M = ca. 1 PR, L = 1–2 PRs, XL = 2+ PRs.

## Architekturvarianten

### Variante A: Ausbau im Bestand (Python, Netz + exakte Daten) (empfohlen)

- + Neuer reiner Python-Messkern mess_kern.py ohne Oberfläche (testbar), den Viewer, alle Editoren, Baugruppe, Satz, STEP-Prüfdialog und die Kalkulation gemeinsam nutzen.
- + Exakte Werte kommen wie heute aus 'geo' (Editor-Teile) und neu aus einem Flächenkatalog, den die STEP-Messung einmal beim Import mitschreibt.
- + Keine neue Abhängigkeit, kein Eingriff in die Rechnung, gleiche Bedienung in allen Fenstern.
- − Mindestabstand zwischen beliebigen Körpern und Interferenz sind auf dem Netz nur genähert.

### Variante B: A plus OCCT-Dienstprozess für schwere Analysen (als Zusatz ab M4)

- + Der vorhandene Messprozess (STEP-Import.exe) bekommt einen Dienstmodus: bleibt geöffnet, hält die Körper und antwortet per JSON.
- + Er liefert exakten Mindestabstand (BRepExtrema), Interferenz (BRepAlgoAPI_Common), Volumen/Schwerpunkt/Masse nur bei geschlossenem Körper und den Bauteilvergleich.
- + Der Absturzschutz bleibt: stirbt der Dienst, meldet die Ansicht „Analyse nicht möglich“ und startet ihn neu.
- − Mehr Aufwand beim Prozessstart und Speicher je geöffneter Baugruppe.

### Variante C: SolidCraft/solidcore übernehmen oder einbetten (nicht empfohlen)

- + Lizenz würde es erlauben (MIT/Apache-2.0, solidcore Apache-2.0, NOTICE-Pflichten).
- + Bewährte Ideen wären direkt da.
- − Rust statt Python/Qt, keine Python-Anbindung, Build für Windows/Cython müsste neu gebaut werden.
- − Zweiter Geometriekern neben OpenCascade mit eigener Toleranz und Vernetzung. Das gefährdet „Konturen 100 % wie STEP“.
- − Laut Doku in einem frühen Stand; Kernfehler sind laut Doku auf SolidCraft-Seite nicht umgehbar.
- − Einbetten der Web-App ist ausdrücklich nicht gewünscht.

## Lizenzprüfung

| Teil | Lizenz | Bedeutung |
|---|---|---|
| SolidCraft | MIT OR Apache-2.0 (NOTICE im Repo tangency-labs/solidcraft) | Nutzung und Änderung erlaubt; bei Code-Übernahme Lizenztext und NOTICE beilegen. Name „SolidCraft“ nicht in unserer Oberfläche verwenden. |
| solidcore (Kern) | Laut Kernel-Seite Rust-Portierung von NVIDIA SMLib; NVIDIA hat SMLib als USD BRep unter Apache-2.0 freigegeben (09.10.2026) | Erlaubt mit Hinweispflichten. Die Architekturseite nennt noch „truck“ als Kern, die Doku ist hier nicht einheitlich. Vor einer Übernahme müsste der Lizenzstand im solidcore-Repo selbst geprüft werden. |
| truck-Crates | Apache-2.0 (RICOS Co. Ltd.) | Erlaubt mit Hinweis. |
| Schriften | SIL OFL 1.1 | Nicht relevant, wir übernehmen keine Schriften. |
| Unser Kern OCP/OpenCascade | LGPL-2.1 mit Ausnahme (wie bisher, eigener Prozess) | Unverändert. |

Ergebnis: Rechtlich wäre eine Übernahme mit Hinweispflichten möglich. Wir übernehmen trotzdem keinen Code, nur Konzepte. Ideen, Bedienabläufe und Funktionsnamen sind nicht geschützt. Geprüft wurden nur öffentliche Seiten (docs.solidcraft.io, NOTICE im Repo). In app.solidcraft.io wurde nichts angemeldet oder umgangen.

## Übernommene Konzepte

- **Zeitleiste ist nicht Rückgängig:** Die Zeitleiste zeigt, woraus das Teil besteht, und Rückgängig zeigt, was man getan hat. Beide bleiben getrennt.
- **Persistente Namen mit Rückfall:** Ein Maß hängt an einer Flächenkennung plus geometrischem Fingerabdruck. Findet es die Fläche nicht mehr genau, sagt es das, statt zu raten (bei uns: Maß wird gelb „Bezug verloren“).
- **Parameter beim Tippen benennen:** „breite = 40“ in einem Feld legt den Parameter an. Kreisbezüge werden mit Pfad gemeldet.
- **Kernaufruf mit Schutz:** Jeder Geometrieaufruf ist gekapselt. Ein Fehler markiert nur den Schritt, das Modell bleibt wie vorher. Bei uns gilt das schon für den Messprozess, künftig auch für den Dienst.
- **Referenztests gegen analytische Werte:** Messkern-Tests prüfen gegen bekannte Werte (Ø, Bogenlänge, Fläche, Volumen von Rohr und Quader) statt gegen frühere Ausgaben.
- **Befehle als Daten:** Jede Messung und jeder Schritt ist ein kleines JSON-Objekt. Das bringt Speichern, Rückgängig, Export und Tests auf einmal.

## Phasenplan

### M1 Messkern und Direktmessung (1 PR)

- mess_kern.py: Elemente Punkt, Kante, Kreis/Bogen, Ebene, Zylinder, Kontur, Körper; Werte und Abstände/Winkel zwischen allen Paaren, ohne Oberfläche.
- Direktmessung bei Auswahl: Kante (Länge, Anfang, Ende, Richtung, Winkel zur Achse), Kreis (Ø, R, Umfang, Mitte), Fläche (Inhalt, Umfang, Hülle, Normale), Punkt (X/Y/Z).
- Mehrfachauswahl: Gesamtlänge, Gesamtfläche, Abstand, Winkel, Mindestabstand.
- Mess-Tafel gleich in Rohr-, Blech-Editor, Baugruppe, Satz, STEP-Prüfdialog und Viewer (Regel „alle Editoren“).
- Tests gegen analytische Werte, Vorher-Nachher-Bilder.

### M2 Messwerkzeuge und Maße im Modell (1–2 PRs)

- Werkzeuggruppe „Messen“: Länge (auch Kontur und gekrümmte Kante), Ø/R (innen/außen, Bohrung, Rohrbogen), Winkel (Linien, Flächen, zur Achse, Gehrung) mit Bezugsebene und Drehsinn.
- Abstand Punkt–Punkt, Punkt–Kante, Punkt–Fläche, Kante–Kante, Fläche–Fläche, entlang einer Achse, immer mit ΔX/ΔY/ΔZ.
- Dauerhafte Maße mit Maßlinie, Pfeilen und Beschriftung; mehrere gleichzeitig; ein-/ausblenden, löschen; behindern Drehen und Auswahl nicht.
- Kopieren, CSV-Export, PDF-Messprotokoll, Speichern je Position (Schema +1).
- Fangarten einzeln einstellbar, „Andere wählen“ zum Durchschalten.

### M3 Rohr-, Kontur- und Fertigungsmessung (1 PR)

- Flächenkatalog aus der STEP-Messung (Variante A): exakte Werte auch für STEP-Teile.
- Rohrmessung automatisch: Länge, Außen/Innen, Wand, Breite/Höhe, Eckradien, Querschnitt, Umfang, Gewicht (Dichte aus Werkstoff) für Rund, Vierkant, Rechteck, Oval und Sonderprofil.
- Konturmessung: Länge offen/geschlossen, Segmente, Bögen mit R, Winkel zwischen Segmenten, Fläche, Anzahl, doppelte Konturen.
- Fertigung: Lochabstände, Kontur–Kontur, Kontur–Ende, Reststeg gegen dfm-Regeln, Ausschnittgröße, Lage von Durchbrüchen. Werte als Prüfung neben der Kalkulation, die Rechnung bleibt unverändert.
- Volumen und Masse nur bei geschlossenem Körper, sonst „nicht bestimmbar“.

### M4 Analyse und Bauteilvergleich (Variante B) (1–2 PRs)

- Dienstmodus des Messprozesses mit Neustart bei Absturz.
- Exakter Mindestabstand, Interferenz/Kollision in Baugruppe und Satz mit roter Schnittmenge.
- Bauteilvergleich zweier STEP-Stände: gleiche Bereiche, Überschuss, fehlende Geometrie, max./mittlere Abweichung mit Ort, Farbkarte im 3D.
- Prüfungen: offene Körper, doppelte Flächen, unplausible Wandstärke, Mindestbiegeradius, wo bestimmbar.

### C1 Parameter und Formeln (1 PR)

- Parametertabelle je Teil (Name, Ausdruck, Einheit, Kommentar); Namen in jedem Zahlenfeld; Rechenfeld ohne eval erweitert.
- Abhängigkeiten anzeigen, Kreisbezüge melden, Parameter in Verwendung nicht löschbar.
- STEP-Maße sind Referenzmaße (grau, nicht änderbar). Treibende Maße gibt es nur bei Editor-Geometrie.

### C2 Merkmal-Zeitleiste (1 PR)

- Schritt 0 „STEP-Import“ bzw. „Grundprofil“ gesperrt; danach Enden, Konturen, Ausschnitte, Gravuren als Schritte.
- Umbenennen, unterdrücken/aktivieren, Rollback-Marker, fehlerhafte Schritte rot, Abhängigkeiten.
- Die Kalkulation rechnet nur aktive Schritte; der Status zeigt unterdrückte Schritte deutlich.

### C3 Parametrisches Rohr (1 PR)

- Profil ändern (z. B. 60×40×3 auf 80×40×3): Konturen bleiben relativ zu Fläche und Ende, Maße und Rechnung folgen.
- Passt eine Kontur nicht mehr (über Kante, in Rundung), wird der Schritt rot markiert statt still verschoben.
- Nur für Editor-Teile; STEP-Geometrie bleibt unverändert.

### C4 2D-Konturskizzierer (2 PRs)

- Auf Rohrfläche oder Abwicklung: Linie, Polylinie, Kreis, Bogen, Rechteck (auch abgerundet), Langloch, Polygon, Ellipse, Spline, Konstruktionslinie, Punkt.
- Bearbeiten: Verschieben, Drehen, Spiegeln, Versatz, Trimmen, Verlängern, Teilen, Verbinden, Abrunden, Fasen, Schließen.
- Bedingungen: horizontal, vertikal, parallel, senkrecht, tangential, konzentrisch, symmetrisch, gleich, Mittelpunkt, koinzident; Bemaßungen; kleiner Löser (Newton).
- Ergebnis: Sonderkontur mit Umriss, damit Schneidweg, Einstiche und Export unverändert rechnen.

### C5 Rohrlaser-Werkzeuge ergänzen (1 PR)

- Lochbild (Kreis, Raster, entlang Achse), Konturen um die Achse drehen und verschieben (teils da), Kontur auf anderes Profil übertragen, Projektion auf gekrümmte Fläche.
- Vorhandenes (Sattel, Gegenrohr, Gehrung, Abwicklung) bekommt Zugang über die neue Zeitleiste.

### C6 Baugruppe (1 PR)

- Kollision aus M4, Komponenten aus dem Programm positionieren/ausrichten/kopieren (STEP-Teile nie verschieben), Baugruppen vergleichen.

### C7 Oberfläche (1 PR)

- Reiter „Messen“ und „Prüfen“ im Menüband, Befehlssuche, Tastenkürzel anpassen, Navigationsvorlagen, unten Zeitleiste und Meldungen, Profile je Benutzer.

## Bewusst nicht

- Kein allgemeines Volumen-CAD (Loft, Sweep, Flächenmodellierung, Shell, Fillet an STEP-Körpern). Der Nutzen für die Rohrlaserfertigung ist gering und das Risiko für die 100-%-Regel hoch.
- Kein Einbetten von app.solidcraft.io und keine Code-Übernahme.
- Keine Änderung importierter STEP-Geometrie durch Maße oder Parameter.

## Regeln für jede Phase

- Konturen 100 % wie STEP; STEP-Teile nie verschieben; Messen ändert nie etwas am Teil.
- Jede Funktion in allen Editoren (Rohr, Blech, Baugruppe, Satz in 3D) und im STEP-Prüfdialog.
- Je PR: Tests in tests/alle.py, ruff, Anleitung ergänzt, Vorher-Nachher-Bilder, Version main+1 direkt vor dem Merge, Schema eindeutig hochzählen.
- Messwerte für die Kalkulation sind Prüf- und Anzeigewerte. Die Rechnung (Schneidweg, Laserzeit) bleibt die bestehende.

## Quellen

- [docs.solidcraft.io (Einführung)](https://docs.solidcraft.io/)
- [Funktionsliste](https://docs.solidcraft.io/dev/features.html)
- [Kernel-Grenze](https://docs.solidcraft.io/dev/kernel.html)
- [Architektur](https://docs.solidcraft.io/dev/architecture.html)
- [Persistente Namen](https://docs.solidcraft.io/dev/naming.html)
- [Parameter](https://docs.solidcraft.io/guide/parameters.html)
- [Fenster-Rundgang](https://docs.solidcraft.io/guide/ui-tour.html)
- [NOTICE (Lizenzen)](https://raw.githubusercontent.com/tangency-labs/solidcraft/master/NOTICE)
- [NVIDIA USD BRep unter Apache-2.0](https://alphasignal.ai/news/nvidia-opens-usd-brep-s-cad-kernel-to-developers-under-apache-2-0)
