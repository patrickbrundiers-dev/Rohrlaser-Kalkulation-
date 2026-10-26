"""Dunkelmodus verbessern (24.10.2026): Flächen, Zeichnungen, feste Farben, „Wie Windows“, Spaltenköpfe.

D1 Eingabezellen im Dunkelmodus blaugrau (nicht olivbraun), berechnete Zellen dunkler, Unterschied sichtbar;
D2 jede helle Fläche und jede dunkle Schrift in Programmteilen der Oberfläche hat eine Dunkel-Farbe (kein Weiß bleibt
   stehen); Ausnahmen nur PDF-Module und Körperfarben der 3D-Ansicht;
D3 keine festen Farben QColor("#…") bzw. Qt.gray/red/darkYellow mehr (außer Zeilen mit „# fest:“);
D4 „Wie Windows“ folgt dem System, Hell wird fest gesetzt (helle Palette auch im Windows-Dunkelmodus);
D5 Themewechsel im laufenden Programm: Beschriftungen und Stylesheets hin und zurück richtig umgefärbt;
D6 Skizze und 3D-Hintergrund im Dunkelmodus dunkel, die Zeichnung fürs PDF bleibt weiß (stil.druckfarben);
D7 Spaltenkopf: Platz für den Sortierpfeil, gemerkte Breite nie schmaler als das längste Wort.
Aufruf: python tests/test_dunkelmodus.py
"""
import os
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import stil  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


def rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def helligkeit(h):
    r, g, b = rgb(h)
    return 0.299 * r + 0.587 * g + 0.114 * b


D = stil.UMSETZUNG["Dunkel"]

# D1
eingabe, berechnet, karte = D["#FFFCF0"], D["#EDEDED"], D["#FFFFFF"]
r, g, b = rgb(eingabe)
pruefe(b > r and b >= g, f"D1 Eingabezelle blaugrau, nicht gelblich ({eingabe})")
pruefe(helligkeit(eingabe) - helligkeit(berechnet) >= 10, "D1 Eingabe und berechnet gut zu unterscheiden")
pruefe(helligkeit(berechnet) <= helligkeit(karte), "D1 berechnete Zelle nicht heller als die Tabelle")
pruefe(D["#FFF9E5"] == eingabe and D["#F2F2F2"] == berechnet, "D1 Nachkalkulation: gleiche Eingabe-/Rechenfarben")
for v, h in ((stil.TEXT, "#FFFCF0"), (stil.TEXT, "#EDEDED")):
    pruefe(stil.kontrast(stil.umsetzen(v, "Dunkel"), stil.umsetzen(h, "Dunkel")) >= 7, f"D1 Schrift auf {h} kräftig lesbar")

# D2 + D3
NUR_DRUCK = {"pdf.py", "stil.py", "zeichnung.py", "palettenschein.py"}
ERLAUBT = {"#D0021B", "#E00000",                      # kräftige Rotlinien: auf hell und dunkel sichtbar
           "#1A1A1A", "#E8C77A", "#C9D6E3", "#D9DDE2", "#3C4650"}   # Körperfarben der 3D-Ansicht (auf Verlauf)
offen, fest = [], []
for datei in sorted((WURZEL / "programm" / "rohrlaser").glob("*.py")):
    if datei.name in NUR_DRUCK:
        continue
    for nr, zeile in enumerate(datei.read_text(encoding="utf-8").splitlines(), 1):
        for h in re.findall(r"#[0-9A-Fa-f]{6}\b", zeile):
            h = h.upper()
            if h not in D and h not in ERLAUBT and not 70 <= helligkeit(h) <= 200:
                offen.append(f"{datei.name}:{nr} {h}")
        if "# fest:" not in zeile and (re.search(r'QColor\("(#|white|black)', zeile)
                                        or re.search(r"setForeground\(Qt\.(gray|red|darkYellow|black)", zeile)
                                        # Themefarbe ohne stil.farbe (26.10.2026: Herkunft im Editor unsichtbar)
                                        or re.search(r"QColor\((stil\.)?(TEXT|ROT|GRUEN|ORANGE|GELB_TEXT|AKZENT|"
                                                     r"RAHMEN|LINIE|FLAECHE|FARBE_HERKUNFT|FARBE_STUFE)\b", zeile)):
            fest.append(f"{datei.name}:{nr}")
pruefe(not offen, f"D2 helle Flächen/dunkle Schrift haben eine Dunkel-Farbe {offen[:8] or ''}")
pruefe(not fest, f"D3 keine festen Farben in der Oberfläche {fest[:8] or ''}")

# D4
pruefe(stil.thema_aufloesen("Wie Windows", True) == "Dunkel" and stil.thema_aufloesen("Wie Windows", False) == "Hell",
       "D4 Wie Windows folgt dem System")

from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QTableView, QWidget  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
pruefe(isinstance(stil.windows_dunkel(), bool), "D4 Systemfarbschema lesbar (Registry bzw. Qt)")
hell = stil.palette("Hell")
pruefe(hell is not None and hell.color(QPalette.Window).lightness() > 200 and hell.color(QPalette.Text).lightness() < 80,
       "D4 Hell wird fest gesetzt: helle Palette, dunkle Schrift")
stil.anwenden(app, "Hell")
pruefe(app.palette().color(QPalette.Base).lightness() > 200, "D4 anwenden(Hell) setzt die helle Palette")

# D5
w = QWidget()
l1 = QLabel("<span style='color:#B42318'>Fehler</span>", w)        # Text im Konstruktor (Hell)
l2 = QLabel(w)
l2.setText("<b style='color:#1E6B34'>OK</b>")
fl = QLabel(w)
fl.setStyleSheet("background: #FFFCF0; color: #1F2937;")
stil.anwenden(app, "Dunkel")
stil.umfaerben(app)
pruefe(D["#B42318"] in l1.text() and D["#1E6B34"] in l2.text(), "D5 Hell → Dunkel: Beschriftungen umgefärbt")
pruefe(D["#FFFCF0"] in fl.styleSheet() and "#FFFCF0" not in fl.styleSheet().upper(), "D5 Hell → Dunkel: Stylesheet umgefärbt")
pruefe(app.palette().color(QPalette.Base).lightness() < 80, "D5 dunkle Palette")
l3 = QLabel(w)
l3.setText("<span style='color:#7A5A00'>Warnung</span>")
pruefe(D["#7A5A00"] in l3.text(), "D5 neue Beschriftung im Dunkelmodus gleich umgefärbt")
stil.anwenden(app, "Hell")
stil.umfaerben(app)
pruefe("#B42318" in l1.text() and "#1E6B34" in l2.text() and "#7A5A00" in l3.text(),
       "D5 Dunkel → Hell: wieder die Original-Farben")
pruefe("#FFFCF0" in fl.styleSheet(), "D5 Dunkel → Hell: Stylesheet wieder hell")

# D6
from rohrlaser import ansicht3d  # noqa: E402
from rohrlaser.skizze_widget import Skizze  # noqa: E402

stil.anwenden(app, "Dunkel")
pruefe(ansicht3d.HINTERGRUND.lightness() < 80 and ansicht3d.HINTERGRUND_OBEN.lightness() < 80,
       "D6 3D-Hintergrund dunkel")
s = Skizze(dict(form="Quadratrohr", a=40, b=40, wand=3), 500.0)
s.resize(400, 240)
bildschirm = s.grab().toImage()
pruefe(bildschirm.pixelColor(3, 3).lightness() < 80, "D6 Skizze auf dem Bildschirm dunkel")
druck, _ = s.bild(400, 240)
pruefe(druck.pixelColor(3, 3).lightness() > 240, "D6 Skizze für das PDF weiß")
with stil.druckfarben():
    pruefe(ansicht3d.HINTERGRUND.name().upper() == "#FFFFFF", "D6 druckfarben: Konstanten hell")
pruefe(ansicht3d.HINTERGRUND.lightness() < 80, "D6 nach druckfarben wieder dunkel")
stil.anwenden(app, "Hell")

# D7
from PySide6.QtGui import QStandardItemModel  # noqa: E402
from rohrlaser import spaltenbreite  # noqa: E402

m = QStandardItemModel(1, 1)
m.setHorizontalHeaderLabels(["Programmierzeit [min]"])
t = QTableView()
t.setModel(m)
ohne = spaltenbreite.kopfbreite(t, 0)
t.setSortingEnabled(True)
pruefe(spaltenbreite.kopfbreite(t, 0) >= ohne + 10, "D7 Platz für den Sortierpfeil")
pruefe(spaltenbreite.wortbreite(t, 0) > ohne - 20, "D7 längstes Wort samt Rand")

print()
print("Alles in Ordnung." if not fehler else f"{len(fehler)} Fehler.")
sys.exit(1 if fehler else 0)
