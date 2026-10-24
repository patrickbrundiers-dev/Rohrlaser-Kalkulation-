"""Prüft die Tabellen-Eingabe wie in Excel (Plan „Arbeitsabläufe effizienter“ W5, Schritt AB4) in der
Positionsliste: Eingabe springt nach unten bzw. rechts (Einstellung), ↓ und Eingabe in der letzten Zeile legen eine
Position an, Strg+D übernimmt den Wert von oben, Profil-Feld findet „40x3“ → „QR 40x40x3“.

Aufruf: python tests/test_tabellen_eingabe.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QItemSelection, QItemSelectionModel, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit  # noqa: E402

from rohrlaser import tabellen_eingabe as te  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Profil vervollständigen
namen = ["RR 42,4x2,0", "RR 48,3x2,6", "QR 40x40x3", "QR 40x40x4", "RE 60x40x3", "RE 40x20x3", "RP 0103-50"]
assert te.profil_treffer("40x3", namen)[0] == "QR 40x40x3"
assert te.profil_treffer("40 x 4", namen)[0] == "QR 40x40x4"
assert te.profil_treffer("40", namen)[:3] == ["QR 40x40x3", "QR 40x40x4", "RE 40x20x3"]
assert te.profil_treffer("re 60", namen) == ["RE 60x40x3"]
assert te.profil_treffer("42,4", namen) == ["RR 42,4x2,0"]
assert te.profil_treffer("qr", namen) == ["QR 40x40x3", "QR 40x40x4"]
assert te.profil_treffer("0103", namen) == ["RP 0103-50"] and te.profil_treffer("", namen) == []
assert te.profil_aufloesen("40x3", namen) == "QR 40x40x3"
assert te.profil_aufloesen("qr 40x40x4", namen) == "QR 40x40x4"
assert te.profil_aufloesen("48,3", namen) == "RR 48,3x2,6"           # einziger Treffer
assert te.profil_aufloesen("40", namen) == "40"                       # mehrdeutig: Eingabe bleibt
assert te.profil_aufloesen("XY 1", namen) == "XY 1"
ok("Profil: 40x3 → QR 40x40x3, Maße am Anfang, Buchstaben vorn, eindeutige Treffer beim Bestätigen")

# ------------------------------------------------------------------ Positionsliste
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert db.einstellung("eingabe_richtung") == te.UNTEN
fenster = Hauptfenster(db, tmp, stumm=True)
a = db.angebot_neu()
profil = db.zeilen("profile")[0]["profil_id"]
for n, stueck in ((10, 5), (20, None)):
    db.position_neu(a, dict(pos=n, artikel=f"T{n}", profil_id=profil, laenge=500, stueck=stueck))
s = fenster.angebot_oeffnen(a)
v, m = s.pos_ansicht, s.pos_modell
v.setFocus()
spalte = {x.name: i for i, (art, x) in enumerate(m.spalten) if x is not None and hasattr(x, "name")}
c_st, c_art = spalte["stueck"], spalte["artikel"]

# Eingabe ohne Bearbeiten: eine Zeile tiefer
v.setCurrentIndex(m.index(0, c_st))
QTest.keyClick(v, Qt.Key_Return)
assert (v.currentIndex().row(), v.currentIndex().column()) == (1, c_st)
ok("Eingabe springt nach unten (Standard)")

# Strg+D: Stückzahl von oben
QTest.keyClick(v, Qt.Key_D, Qt.ControlModifier)
assert db.positionen(a)[1]["stueck"] == 5, db.positionen(a)[1]
ok("Strg+D übernimmt den Wert der Zeile darüber")

# ↓ in der letzten Zeile: neue Position, gleiche Spalte; Strg+D über drei markierte Zeilen
n = len(db.positionen(a))
v.setCurrentIndex(m.index(n - 1, c_art))
QTest.keyClick(v, Qt.Key_Down)
assert len(db.positionen(a)) == n + 1 and v.currentIndex().row() == n and v.currentIndex().column() == c_art
assert db.positionen(a)[-1]["pos"] == 30
QTest.keyClick(v, Qt.Key_Down)                       # letzte Zeile noch leer: keine zweite leere Zeile
assert len(db.positionen(a)) == n + 1
auswahl = QItemSelection(m.index(0, c_st), m.index(n, c_st))
v.selectionModel().select(auswahl, QItemSelectionModel.ClearAndSelect)
te.von_oben(v)
assert [p["stueck"] for p in db.positionen(a)] == [5, 5, 5]
ok("↓ in der letzten Zeile legt eine Position an (Pos. +10, nicht unter einer leeren); Strg+D füllt mehrere Zeilen mit der obersten")

# Eingabe nach rechts: nächste bearbeitbare Spalte; am Zeilenende in die nächste Zeile
db.einstellung_setzen("eingabe_richtung", te.RECHTS) if hasattr(db, "einstellung_setzen") else \
    db._einstellung_schreiben("eingabe_richtung", te.RECHTS)
v.setCurrentIndex(m.index(0, c_art))
QTest.keyClick(v, Qt.Key_Return)
r, c = v.currentIndex().row(), v.currentIndex().column()
kopf = v.horizontalHeader()
assert r == 0 and kopf.visualIndex(c) > kopf.visualIndex(c_art) and m.index(0, c).flags() & Qt.ItemIsEditable
spalten = s.excel._spalten(0)
s.excel.weiter(0, spalten[-1])
assert v.currentIndex().row() == 1 and v.currentIndex().column() == s.excel._spalten(1)[0]
ok("Einstellung nach rechts: nächste bearbeitbare Spalte, am Ende erste Spalte der nächsten Zeile")

# Bearbeiten und mit Eingabe bestätigen: Wert gespeichert, dann weiter
db._einstellung_schreiben("eingabe_richtung", te.UNTEN)
v.setCurrentIndex(m.index(0, c_art))
v.edit(m.index(0, c_art))
app.processEvents()
editor = v.viewport().findChildren(QLineEdit)[-1]
editor.setText("NEU-1")
QTest.keyClick(editor, Qt.Key_Return)
for _ in range(5):
    app.processEvents()
assert db.positionen(a)[0]["artikel"] == "NEU-1"
assert (v.currentIndex().row(), v.currentIndex().column()) == (1, c_art), (v.currentIndex().row(), v.currentIndex().column())
ok("Zelle bearbeitet und mit Eingabe bestätigt: gespeichert, Zelle darunter gewählt")

# Profil-Feld in der Positionsliste: 40x3 wird zum Profilnamen
c_pr = spalte["profil_id"]
ziel, eingabe = "QR 40x40x3", "40x3"
assert ziel in {p["profil_id"] for p in db.zeilen("profile")}
v.setCurrentIndex(m.index(1, c_pr))
v.edit(m.index(1, c_pr))
app.processEvents()
cb = v.viewport().findChildren(QComboBox)[-1]
assert cb.property("profil_namen") and cb.completer() is not None
cb.setEditText(eingabe)
v.itemDelegate().setModelData(cb, m, m.index(1, c_pr))
assert db.positionen(a)[1]["profil_id"] == ziel, db.positionen(a)[1]["profil_id"]
ok("Profil-Feld in der Positionsliste: „40x3“ wird zu „QR 40x40x3“")

# Lesemodus: ↓ legt nichts an
db.nur_lesen = "Test"
n = len(db.positionen(a))
v.setFocus()
v.setCurrentIndex(m.index(m.rowCount() - 1, c_art))
QTest.keyClick(v, Qt.Key_Down)
db.nur_lesen = None
assert len(db.positionen(a)) == n
ok("Lesemodus: keine neue Position")

print("Alle Prüfungen bestanden.")
