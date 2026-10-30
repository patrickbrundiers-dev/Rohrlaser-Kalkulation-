"""Plan „Eingabefelder intuitiver machen“ (25.10.2026):
- E1: Ja/Nein-Einstellungen als Schiebeschalter, Ja/Nein-Spalten der Tabellen als Häkchen in der Zelle (Klick,
  Leertaste, J/N), gespeichert weiter als „ja“/„nein“.
- E2: wenige kurze Möglichkeiten als Knopfreihe; feste Auswahllisten der Einstellungen nicht mehr frei beschreibbar.
- E3/E6: Fenster passen auf den Bildschirm (auch gemerkte Größen), Fenster ohne Elternfenster bleiben vor dem
  Hauptfenster.
- E4: in Zahlenfeldern und Tabellen rechnen („6000/4“), Wert beim Hineinklicken markiert, unfertige Rechnung rot.

Aufruf: python tests/test_eingabefelder.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QLocale, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent, QMouseEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QStyleOptionViewItem  # noqa: E402

from rohrlaser import fenster_platz  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.eingabe import RechenSpin, RechenSpinGanz, Schalter, Segment, segment_passt  # noqa: E402
from rohrlaser.fenster import Auswahl, Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import Feld, wert_aus_text  # noqa: E402


def ok(text):
    print("OK    ", text)


QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
f.show()

# ---------------------------------------------------------------- E4 Rechnen in Zahlenfeldern
s = RechenSpin()
s.setRange(0, 100000)
s.setSuffix(" mm")
s.setGroupSeparatorShown(True)
s.setValue(6000)
s.show()
s.lineEdit().selectAll()
QTest.keyClicks(s.lineEdit(), "6000/4")
assert s.text() == "6000/4 mm", s.text()
QTest.keyClick(s, Qt.Key_Return)
assert s.value() == 1500, s.value()
s.lineEdit().setCursorPosition(len(s.text()) - len(" mm"))
QTest.keyClicks(s.lineEdit(), "*2")           # an „1.500,00“ angehängt: Punkt = Tausender
s.interpretText()
assert s.value() == 3000, s.value()
s.lineEdit().selectAll()
QTest.keyClicks(s.lineEdit(), "(5+1")
assert s.styleSheet(), "unfertige Rechnung rot umrandet"
QTest.keyClicks(s.lineEdit(), ")*2")
assert not s.styleSheet()
s.interpretText()
assert s.value() == 12
s.lineEdit().selectAll()
QTest.keyClicks(s.lineEdit(), "99999+5")       # über dem Höchstwert: auf den Höchstwert begrenzt
s.interpretText()
assert s.value() == 100000, s.value()
from PySide6.QtWidgets import QLineEdit, QVBoxLayout, QWidget  # noqa: E402
rahmen = QWidget()
lay = QVBoxLayout(rahmen)
u, anderes = RechenSpin(), QLineEdit()
u.setRange(0, 9999)
u.setValue(12)
lay.addWidget(u)
lay.addWidget(anderes)
rahmen.show()
rahmen.activateWindow()
app.processEvents()
u.setFocus()
u.lineEdit().selectAll()
QTest.keyClicks(u.lineEdit(), "60/")
assert not u.styleSheet(), "direkt nach dem Rechenzeichen noch nicht rot"
anderes.setFocus()
app.processEvents()
assert u.styleSheet() and "unvollständig" in u.toolTip() and u.value() == 12, (u.value(), u.toolTip())
rahmen.close()
g = RechenSpinGanz()
g.setRange(0, 30000)
g.lineEdit().selectAll()
QTest.keyClicks(g.lineEdit(), "6000x2+1")
g.interpretText()
assert g.value() == 12001
d = RechenSpin()
d.setRange(-100, 100)
d.lineEdit().selectAll()
QTest.keyClicks(d.lineEdit(), "-5,5")          # normale Zahl, keine Rechnung
d.interpretText()
assert d.value() == -5.5
zahl = Feld("x", "Länge", "zahl", 0, 20000)
assert wert_aus_text(zahl, "6000/4") == 1500 and wert_aus_text(zahl, "1.250 - 2×3") == 1244
assert wert_aus_text(zahl, "1.250") == 1250 and wert_aus_text(zahl, "12,5") == 12.5
for falsch in ("6000/", "abc", "2**3"):
    try:
        wert_aus_text(zahl, falsch)
        raise AssertionError(falsch)
    except ValueError:
        pass
ok("Zahlenfelder und Tabellen: rechnen wie im Teile-Editor, Tausenderpunkt, Grenzen, unfertige Rechnung rot")

# ---------------------------------------------------------------- E1/E2 Einstellungen
f.bereich.oeffnen("av")             # Admin-Schutz: Lieferlängen-Regeln ändert nur der Admin
e = f.einstellungen
sw = e.felder["laenge_vergleich"]
assert isinstance(sw, Schalter) and sw.currentText() == "nein" and not sw.isChecked()
QTest.mouseClick(sw, Qt.LeftButton)
assert db.einstellung("laenge_vergleich") == "ja", db.einstellung("laenge_vergleich")
QTest.keyClick(sw, Qt.Key_Space)
assert db.einstellung("laenge_vergleich") == "nein"
thema = e.felder["ansicht_dichte"]
assert isinstance(thema, Segment) and thema.count() == 3 and not thema.isEditable()
assert thema.currentText() == (db.einstellung("ansicht_dichte") or "normal")
thema.knoepfe[0].click()
assert db.einstellung("ansicht_dichte") == thema.itemText(0)
liste = e.felder["lieferzeit_art"]                 # 5 Möglichkeiten: Auswahlliste, aber nur Listenwerte
assert isinstance(liste, QComboBox) and not liste.isEditable()
maschine = e.felder["standard_maschine"]           # Liste aus den Stammdaten: tippen mit Teilwortsuche
assert isinstance(maschine, QComboBox) and maschine.isEditable() and maschine.completer() is not None
assert segment_passt(["Hell", "Dunkel"]) and not segment_passt(["a", "b", "c", "d", "e"])
assert not segment_passt(["Blech", "Flachstahl bis Breite (Einstellung darunter)"])
ok("Einstellungen: ja/nein als Schalter, kurze Listen als Knopfreihe, feste Listen nicht frei beschreibbar")

# ---------------------------------------------------------------- E1 Tabellen: Häkchen in der Zelle
seite = next(x for x in f.seiten if x.t.name == "maschinen")
spalte = next(i for i, (art, fd) in enumerate(seite.modell.spalten) if art == "feld" and fd.name == "d3")
idx = seite.filter.index(0, spalte)
deleg = seite.ansicht.itemDelegate()
assert isinstance(deleg, Auswahl) and deleg._janein(idx) and deleg.createEditor(seite.ansicht, None, idx) is None
vorher = str(idx.data(Qt.EditRole) or "")
opt = QStyleOptionViewItem()
opt.rect = seite.ansicht.visualRect(idx)
opt.widget = seite.ansicht
mitte = QPointF(opt.rect.center())
klick = QMouseEvent(QEvent.MouseButtonRelease, mitte, mitte, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
assert deleg.editorEvent(klick, seite.filter, opt, idx)
nachher = str(seite.filter.index(0, spalte).data(Qt.EditRole))
assert nachher == ("nein" if vorher == "ja" else "ja"), (vorher, nachher)
assert seite.modell.daten[0]["d3"] == nachher
idx = seite.filter.index(0, spalte)
taste = QKeyEvent(QEvent.KeyPress, Qt.Key_N, Qt.NoModifier, "n")
deleg.editorEvent(taste, seite.filter, opt, idx)
assert seite.modell.daten[0]["d3"] == "nein"
daneben = QPointF(opt.rect.left() + 1, opt.rect.top() + 1)
klick = QMouseEvent(QEvent.MouseButtonRelease, daneben, daneben, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
if opt.rect.width() > 60:
    assert not deleg.editorEvent(klick, seite.filter, opt, seite.filter.index(0, spalte))
    assert seite.modell.daten[0]["d3"] == "nein"
ok("Tabellen: ja/nein als Häkchen in der Zelle (Klick aufs Häkchen, J/N-Taste), kein Auswahl-Editor mehr")

# ---------------------------------------------------------------- E3/E6 Fenster
platz = fenster_platz.FensterPlatz(f, f)
app.installEventFilter(platz)
frei = fenster_platz.frei(f)
riesig = QDialog()                 # ohne Elternfenster und größer als der Bildschirm
riesig.resize(frei.width() + 500, frei.height() + 400)
riesig.move(frei.right() - 50, frei.bottom() - 50)
riesig.show()
app.processEvents()
assert riesig.width() <= frei.width() and riesig.height() <= frei.height(), (riesig.size(), frei)
assert frei.contains(riesig.geometry().topLeft()) and frei.contains(riesig.geometry().bottomRight()), \
    (riesig.geometry(), frei)
assert riesig.windowHandle().transientParent() is f.windowHandle()
riesig.close()
kind = QDialog(f)
kind.resize(300, 200)
kind.show()
app.processEvents()
assert kind.size().width() == 300 and kind.windowHandle().transientParent() is f.windowHandle()
kind.close()
app.removeEventFilter(platz)
ok("Fenster: auf den freien Bildschirm gekürzt und hineingeschoben, ohne Elternfenster vor dem Hauptfenster")

print("Alle Tests der Eingabefelder bestanden.")
