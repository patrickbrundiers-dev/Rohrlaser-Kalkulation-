"""Hell- und Dunkelmodus optisch verbessert (26.10.2026).

H1 Dunkel: Hauptknopf weiße Schrift auf kräftigem Blau (mindestens 4,5 : 1), nicht mehr auf Hellblau;
H2 Dunkel: Eingabefelder, Häkchenkästchen und Optionsfelder mit sichtbarem Rahmen, Häkchen als Bild vorhanden;
H3 Hell: Fensterfläche im kühlen Grau der Karten (FLAECHE) statt Fusion-Grau;
H4 Schrift auf farbigen Flächen (Stangenbild): dunkel auf Orange/Gelb/Grün, weiß auf Dunkelblau, immer ≥ 3 : 1;
H5 Themefarben im Programmtext laufen über stil.farbe (Herkunft im Editor im Dunkelmodus lesbar).
Aufruf: python tests/test_hell_dunkel.py
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import stil  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
dunkel = stil.stylesheet("Dunkel")

# H1
primaer = re.findall(r"QPushButton#primaer \{ background: (#[0-9A-F]{6}); color: (#[0-9A-F]{6})", dunkel)
pruefe(primaer and stil.kontrast(primaer[-1][1], primaer[-1][0]) >= 4.5,
       f"H1 Hauptknopf im Dunkelmodus lesbar {primaer[-1] if primaer else ''}")

# H2
pruefe("QCheckBox::indicator" in dunkel and "QRadioButton::indicator" in dunkel and "QLineEdit, QComboBox" in dunkel,
       "H2 Rahmen für Eingabefelder und Kästchen")
bilder = re.findall(r"url\(([^)]*)\)", dunkel)
pruefe(bilder and all(b and Path(b).is_file() for b in bilder), f"H2 Häkchen und Pfeile als Bild vorhanden {bilder}")
pruefe("{HAKEN}" not in dunkel and "{PFEIL}" not in dunkel, "H2 keine Platzhalter im Stylesheet")
pruefe(stil.stylesheet("Hell") == stil.STIL, "H2 Hell bleibt beim bisherigen Stylesheet")

# H3
hell = stil.palette("Hell")
pruefe(hell.color(QPalette.Window).name().upper() == stil.FLAECHE, "H3 Hell: Fensterfläche = FLAECHE")
pruefe(stil.palette("Dunkel").color(QPalette.Window).name().upper() == stil.UMSETZUNG["Dunkel"][stil.FLAECHE],
       "H3 Dunkel: Fensterfläche unverändert")

# H4
for f in stil.TEIL_FARBEN + ("#1F4E78", "#E06666", "#EDEDED"):
    s = stil.schrift_auf(f).name().upper()
    pruefe(stil.kontrast(s, f) >= 3.0, f"H4 Schrift {s} auf {f}: {stil.kontrast(s, f):.1f} : 1")
pruefe(stil.schrift_auf("#F28E2B").name().upper() == "#111827", "H4 dunkle Schrift auf Orange")
pruefe(stil.schrift_auf("#1F4E78").name().upper() == "#FFFFFF", "H4 weiße Schrift auf Dunkelblau")

# H5
stil.anwenden(app, "Dunkel")
from rohrlaser import teile_editor  # noqa: E402

c = stil.farbe(teile_editor.FARBE_HERKUNFT[teile_editor.MANUELL])
pruefe(c.lightness() > 150, f"H5 Herkunft „manuell“ im Dunkelmodus hell ({c.name()})")
stil.anwenden(app, "Hell")

print()
print("Alles in Ordnung." if not fehler else f"{len(fehler)} Fehler.")
sys.exit(1 if fehler else 0)
