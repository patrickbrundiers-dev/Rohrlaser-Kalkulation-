# Messsystem M1: Messkern und Direktmessung (19.11.2026)

Plan: docs/system-audit/CAD_MESSPLAN_SOLIDCRAFT_1911.md, Phase M1 (freigegeben „Alle Empfehlungen“, Variante A).

## Umgesetzt

- **programm/rohrlaser/mess_kern.py** (neu, ohne Qt): einziger Rechenweg für Abstände, Winkel, Längen, Flächen,
  Umfang, Bogenlänge, Volumen und Schwerpunkt. Elemente: Punkt, Strecke, Kreis/Bogen, Ebene, gewölbte Fläche, Körper.
  Grundlagen nach Ericson: Strecke–Strecke, Punkt–Dreieck, Dreieck–Dreieck (Schnitt = 0).
- **messen3d.py** rechnet mit denselben Funktionen (Vektoren, Abstand Linie/Strecke/windschief, Schnittpunkt,
  Strahl–Dreieck, Zahlformat); die alten Kopien sind entfernt. Keine zweite Messmaschine.
- **auswahl3d.py**: Direktmessung bei Auswahl (`direktmessung`, `messelement`), in jedem 3D-Fenster, weil alle die
  Ansicht3D mit ihrer Auswahl benutzen (Viewer, Rohr-/Blech-Editor, Schweißbaugruppe, Satz, STEP-Prüfdialog).
  - ein Element: Kante mit Winkel zur Rohrachse (global: zu x/y/z), Kreis Ø/R/Umfang, Bogen Winkel/Bogenlänge,
    Fläche Inhalt/Umfang, Körper Volumen/Schwerpunkt;
  - zwei Elemente: Abstand oder Winkel je nach Art, Δ je Achse, Steg zwischen Bohrungen, Mindestabstand;
  - mehrere: Gesamtlänge, Gesamtfläche.

## Genauigkeit und ungültige Geometrie

- Exakt: Ebenen, gerade Kanten, Kreise aus den Eingaben bzw. eingepasst. Alles, was nur auf dem Netz gewölbter
  Flächen gemessen ist, steht mit „≈“.
- Umfang und Geschlossenheit: gerichtete Ränder heben sich auf derselben Geraden auf, dadurch zählen T-Stöße im Netz
  nicht als Rand.
- Offener Körper: kein Volumen, Hinweis „Körper ist offen“. Netze mit kleinem Versatz an Bohrungen (Rand bis 0,5 %
  der Kantenlänge): Volumen nur genähert mit Hinweis.
- Grenzen gegen Hänger: Volumen bis 40.000 Dreiecke, Mindestabstand bis 300.000 Teilpaare; darüber ein Hinweis.
  Exakte Körper-Analysen kommen mit M4 (Dienstprozess).

## Tests

tests/test_messkern_m1.py (M1–M6) gegen gerechnete Sollwerte: Quader 10×20×30 (Volumen 6000, Schwerpunkt,
Oberfläche, auch falsch orientiert), offener Körper, Umfang mit T-Stoß, Bogen 90° = 5π, Paare, Mindestabstand Körper,
Quadrat- und Rundrohr mit Bohrungen im 3D-Fenster (Volumen im Sollbereich des Querschnitts, Steg 41, Umfang 1056,
Winkel 90°, Gesamtlänge), Netz unverändert, messen3d benutzt den Messkern.

Vorher-Nachher: https://claude.ai/artifact/Mxr8RJyMRz72MtXYzQ7cQE
