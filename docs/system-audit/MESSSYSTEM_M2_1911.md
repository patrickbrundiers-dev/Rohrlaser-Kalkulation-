# Messsystem M2: Maße verwalten, Messprotokoll, Fangarten (19.11.2026)

Plan: docs/system-audit/CAD_MESSPLAN_SOLIDCRAFT_1911.md, Phase M2. Baut auf M1 (#576, mess_kern.py) auf.

## Umgesetzt

- **mess_protokoll.py** (neu, ohne Fenster): `Mass` ist das Datenobjekt eines stehenden Maßes. Es bleibt ein Tupel
  (Punkte, Text) wie bisher, mit art, wert, einheit, name, sichtbar und arten (Fangart je Punkt). Dazu gibt es
  dict hin und zurück, CSV (Semikolon, deutsche Zahlen) und das PDF-Messprotokoll (reportlab wie die anderen PDFs;
  „≈“ und „Δ“ werden lesbar ersetzt).
- **ansicht3d.py**: Jede fertige Messung legt ein Mass an, der Wert kommt aus der exakten Messung (messen3d). Dazu
  kommen masse_liste, mass_aendern (Name, sichtbar), mass_entfernen, Kopieren, CSV, PDF mit Bild der Ansicht und
  der Mess-Tafel-Knopf „Maße …“. Rechtsklick → Maße steht in allen 3D-Fenstern. Ausgeblendete Maße werden nicht
  gezeichnet, ein Name steht am Maß. `winkel_bei` liegt jetzt im Messkern (ein Rechenweg).
- **mess_liste.py** (neu): Fenster „Maße“ mit Liste, Umbenennen, Sichtbar-Haken, Löschen, Kopieren, CSV, PDF.
- **Fangarten**: Die Einstellungen fang_kreismitte/-konturmitte/-kantenmitte/-ecke/-punkt/-flaeche gelten je
  Arbeitsplatz, auf der Seite 3D-Navigation → Fangen beim Messen. `messen3d.Geometrie.fangen` beachtet sie und
  liefert mit alle=True alle Kandidaten. **Tab** schaltet beim Messen zum nächsten Kandidaten („Andere wählen“),
  der Klick nimmt genau den gezeigten.

## Bewusst später

- **Maße je Position speichern** (Schema +1) folgt nach dem Datenbank-Umbau #575 (PostgreSQL). Eine Schema-Änderung
  jetzt würde mit dem Umbau kollidieren. Die Datenform steht schon (Mass.als_dict).
- **Winkel mit Bezugsebene und Drehsinn**: Winkel zwischen Kanten, Flächen und zur Rohrachse liefert M1 schon. Der
  gerichtete Winkel (0–360° mit Bezugsebene) kommt mit M3 zur Gehrung.

## Tests

tests/test_masse_m2.py (S1–S5): Mass-Datenobjekt, CSV/PDF, Messung -> Mass mit exakt 50,000, Umbenennen,
Ausblenden, alte Tupel, Löschen, Fenster Maße, Rechtsklick-Menü, Fangarten aus, Tab. Das Netz bleibt unverändert.

Vorher-Nachher: https://claude.ai/artifact/RShyuVp1YcNVwCFrkPMznn
