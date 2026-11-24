"""Abwicklung als Fenster und Enter im Editor (Patrick 25.10.2026):
- A1 Rohr: Knopf „Abwicklung“ oben rechts im Menüband öffnet ein eigenes Fenster mit der Abwicklung (folgt den
  Eingaben); Esc schließt nur dieses Fenster, der Editor bleibt offen, der Knopf springt zurück.
- A2 Blech: dasselbe mit dem Zuschnitt.
- A3 Enter nach einer Eingabe schließt Rohr- und Blech-Editor nicht mehr (Standardknopf OK nicht gedrückt).

Aufruf: python tests/test_editor_abwicklung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rohrlaser import schneidweg as sw, skizze_widget  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
technik = dict(quelle=sw.QUELLE, a=dict(winkel=0), b=dict(winkel=0),
               konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="oben")])
p = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10, technik=json.dumps(technik))


def warten():
    for _ in range(5):
        app.processEvents()


# ------------------------------------------------------------------ A1 Rohr
d = SchneidwegDialog(None, p, k.profile["QR 40x40x3"], dict(maschine="T11", stange=6000), k, db.tabellen(), db)
ed = d.editor
d.show()
warten()
knopf = ed.abwicklung_knopf
assert knopf.text() == "Abwicklung" and knopf.isVisible()
assert knopf.parent() is not None and not any(knopf in s.findChildren(type(knopf)) for s in ed.band.seiten.values())
knopf.click()
warten()
f = ed.abwicklung_fenster
assert f.isVisible() and f.bild.modus == skizze_widget.ABWICKLUNG
assert f.bild.eingaben == d.skizze.eingaben and len(f.bild.lagen()) == 1
d.tabelle.item(0, 2).setText("12")       # Eingabe ändern: die Abwicklung folgt
d.rechnen()
warten()
assert f.bild.eingaben["konturen"][0]["d"] == 12, f.bild.eingaben["konturen"]
f.bild.grab()
QTest.keyClick(f, Qt.Key_Escape)
warten()
assert not f.isVisible() and d.isVisible() and d.result() == 0 and not knopf.isChecked()
knopf.click()
warten()
assert f.isVisible()
knopf.click()
warten()
assert not f.isVisible() and d.isVisible()
ok("A1 Rohr: Knopf Abwicklung oben, eigenes Fenster folgt den Eingaben, Esc schließt nur das Fenster")

# ------------------------------------------------------------------ A3 Enter schließt den Rohr-Editor nicht
w = d.winkel["a"]
w.setFocus()
w.selectAll()
QTest.keyClicks(w, "30")
QTest.keyClick(w, Qt.Key_Return)
warten()
assert d.isVisible() and d.result() == 0, "Enter hat den Rohr-Editor geschlossen"
assert w.value() == 30, w.value()
QTest.keyClick(d, Qt.Key_Enter)
warten()
assert d.isVisible() and d.result() == 0
d.reject()

# ------------------------------------------------------------------ A2 Blech
bd = BlechDialog(None, db)
bd.show()
warten()
be = bd.editor
be.abwicklung_knopf.click()
warten()
bf = be.abwicklung_fenster
assert bf.isVisible() and bf.bild.zuschnitt == bd.skizze.zuschnitt and bf.bild.zuschnitt
bd.laenge.setValue(321)
warten()
assert bf.bild.zuschnitt["laenge"] == bd.skizze.zuschnitt["laenge"] and bf.bild.eingaben["laenge"] == 321
bf.bild.grab()
QTest.keyClick(bf, Qt.Key_Escape)
warten()
assert not bf.isVisible() and bd.isVisible() and not be.abwicklung_knopf.isChecked()
ok("A2 Blech: Abwicklung im eigenen Fenster, folgt den Eingaben, Esc schließt nur das Fenster")

bd.laenge.setFocus()
QTest.keyClick(bd.laenge, Qt.Key_Return)
warten()
assert bd.isVisible() and bd.result() == 0, "Enter hat den Blech-Editor geschlossen"
bd.reject()
assert bd.result() == QDialog.Rejected
ok("A3 Enter nach einer Eingabe schließt Rohr- und Blech-Editor nicht (OK nur per Knopf)")
