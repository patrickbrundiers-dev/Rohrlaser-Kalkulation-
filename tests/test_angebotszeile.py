"""Angebotsliste in der Zeile der geöffneten Angebote hervorgehoben (Patrick 18.11.2026).

Z1 Hell/Dunkel: der Reiter „Angebotsliste“ ist farbig gefüllt, die Angebotsreiter daneben nicht;
Z2 Schrift auf dem Knopf lesbar (Kontrast mindestens 4,5 : 1), gewählt und nicht gewählt;
Z3 die Liste bleibt farbig, egal ob sie oder ein Angebot gewählt ist.
Aufruf: python tests/test_angebotszeile.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from rohrlaser import stil  # noqa: E402
from rohrlaser.hauptreiter import HauptReiter  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")


def farbe_mitte(leiste, i):
    r = leiste.tabRect(i)
    bild = leiste.grab().toImage()
    # Rand des Reiters (links oben innen), dort steht keine Schrift
    return bild.pixelColor(r.left() + 4, r.top() + r.height() // 2 - 6).name().upper()


for thema in ("Hell", "Dunkel"):
    app.setStyleSheet(stil.stylesheet(thema))
    h = HauptReiter()
    h.addTab(QLabel("Start"), "Start")
    liste = QLabel("Liste")
    h.addTab(liste, "Angebote")
    h.gruppe_setzen(liste)
    a1, a2 = QLabel("A1"), QLabel("A2")
    h.addTab(a1, "Angebot A-2026-00001")
    h.addTab(a2, "Angebot A-2026-00002")
    h.setCurrentWidget(a1)
    h.resize(900, 400)
    h.show()
    app.processEvents()
    z = h.unten
    pruefe(z.objectName() == "angebotszeile" and z.tabText(0) == "Angebotsliste", f"{thema}: Zeile mit Angebotsliste")
    grund = farbe_mitte(z, 2)
    knopf = farbe_mitte(z, 0)
    pruefe(knopf != grund, f"Z1 {thema}: Angebotsliste farbig ({knopf}), Angebot daneben nicht ({grund})")
    h.setCurrentWidget(liste)
    app.processEvents()
    knopf_gewaehlt = farbe_mitte(z, 0)
    pruefe(knopf_gewaehlt != farbe_mitte(z, 1), f"Z3 {thema}: gewählt weiter farbig ({knopf_gewaehlt})")
    h.close()
    h.deleteLater()
    app.processEvents()
    del h, z

css = stil.STIL
for zustand, hinter in (("nicht gewählt", "#285F9E"), ("gewählt", "#1F4E78")):
    for thema in ("Hell", "Dunkel"):
        pruefe(stil.kontrast(stil.umsetzen("#FFFFFF", thema), stil.umsetzen(hinter, thema)) >= 4.5,
               f"Z2 {thema}: Schrift auf Angebotsliste {zustand} lesbar")
pruefe("QTabBar#angebotszeile::tab:first" in css and "QTabBar#angebotszeile::tab:only-one" in css,
       "Regel gilt auch, wenn nur die Liste in der Zeile steht")

print("\nalles OK" if not fehler else f"\n{len(fehler)} Fehler")
sys.exit(1 if fehler else 0)
