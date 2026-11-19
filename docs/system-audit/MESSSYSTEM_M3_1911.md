# Messplan M3: Rohr-, Kontur- und Fertigungsmessung (0.9.409)

Plan: docs/system-audit/CAD_MESSPLAN_SOLIDCRAFT_1911.md, Phase M3 (Variante A). Freigabe Patrick 19.11.2026 („Alle Empfehlungen“).

## Gebaut
- **Flächenkatalog der STEP-Messung** (step_geometrie.dreiecksnetz, STEP-JSON 1.30): `fk` = je STEP-Fläche Art (Ebene, Zylinder, Kegel, Kugel, Torus, Freiform), Fläche, Radius/Radien/Öffnungswinkel; `tf` = je Art und Dreieck die Nummer. Die Werte sind lageunabhängig, deshalb ändert Drehen (nach_bezug_drehen) nichts daran. Anhängen (Anbau, ergänzte Wand: Eintrag „Netz“), Verfeinern (offenes Rohr), Art-Tausch (step.py, netz_der_art) und Baugruppe führen ihn mit. Ein unpassender Katalog fällt in netz_pruefen still weg, dann wird wie bisher am Netz gemessen.
- **Programm**: Flächenauswahl folgt den STEP-Flächen; Fläche, Ø und R sind exakt. Zylinderachsen kommen aus mess_kern.zylinder_einpassen (ein Rechenweg, früher in auswahl3d), daraus Achsabstand, Steg Mantel–Mantel, Wandstärke radial sowie Abstand und Winkel zu Punkt, Kante und Fläche. Bogenangabe „350°“ bei ganzen Bohrungen behoben (ganz herum).
- **mess_teil.py** (ohne Qt): Rohrmessung aus dem Querschnitt mit der meisten Wand (Form, Länge, Breite/Höhe, Ø, Wand, Eckradius aus der Flächenlücke, Querschnitt, Umfang, Metergewicht, Masse aus Volumen oder Querschnitt × Länge). Konturen: STEP-Kanten verkettet, Geraden/Bögen/Ecken, Fläche, Größe längs × um den Umfang, Lage, doppelte und beidseitig gezeichnete Konturen. Fertigung: Lochabstände, Reststeg, Abstand zum Ende gegen dfm-Regeln (Steg, Rand, großer Ausschnitt, geschwächt, doppelt).
- **Fenster „Teil messen“** (mess_teil_dialog.py): Knopf in der Leiste aller 3D-Fenster und Rechtsklick, Kopieren, PDF (mess_protokoll.pdf_gruppen). Dichte/Werkstoff über `Ansicht3D.mess_kontext`, sonst Stahl angenommen (angeschrieben).
- **Gehrung**: ebene Schnittfläche → Gehrung zur Bezugsebene (senkrecht zur Rohrachse) mit Drehsinn um hoch/quer; Winkel-Paare quer zur Achse → gerichteter Winkel um die Rohrachse.

## Nicht geändert
Kalkulation, Schneidweg, Laserzeit, Preise. Messen ändert nie das Teil (Tests vergleichen das Netz).

## Hinweise
- Teile, die vor 0.9.409 gemessen wurden, haben keinen Katalog: Messung wie bisher mit ≈, bis sie neu eingelesen werden. Der Messprozess (STEP-Import.exe) braucht den Sammel-Build.
- Offen aus M2: Maße je Position speichern (Schema +1), eigener PR.

## Tests
tests/test_teilmessung_m3.py T1–T6 (in alle.py). Vorher-Nachher: https://claude.ai/artifact/9pCW45yAftGZzvrU8V1AL9
