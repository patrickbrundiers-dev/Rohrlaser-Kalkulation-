"""Enter schließt kein Fenster (Patrick 28.10.2026: „Es sind noch öfter Fenster oder Funktionen die bei einer
Eingabe mit enter das Fenster schließen das darf nicht sein“). Regel tastatur.EnterRegel, für alle Dialoge über
tastatur.einrichten(app):
- E1 Enter in Textfeld, Zahlenfeld, Rechenfeld, Datum, Auswahlliste (auch beschreibbar) und Tabelle schließt den
  Dialog nicht; die Eingabe ist übernommen; in einer bearbeitbaren Tabelle geht es eine Zeile weiter.
- E2 Strg+Enter übernimmt gezielt (klickt OK); ein Knopf mit dem Fokus reagiert weiter auf Enter.
- E3 Ausnahmen nur für reine Bestätigungen: Ja/Nein-Fragen und Hinweise (QMessageBox), Dateiauswahl und
  „Suchen und ausführen“ (Enter führt aus). Kurze Eingabefragen (QInputDialog) halten die Regel ein.
- E4 Alle Dialogklassen des Programms durchlaufen: jede hält die Regel ein, auch mit eigener Tastenbehandlung
  (keyPressEvent, event, eventFilter); Ausnahmen nur aus der Liste unten.
- E5 Quelltext: kein Eingabefeld schließt per returnPressed/editingFinished den Dialog; das Programm richtet die
  Regel beim Start ein.
- E6 Echte Dialoge: Stückzahl ändern, Ecke abrunden (Zahl), Bestand korrigieren.

Aufruf: python tests/test_enter_dialoge.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import importlib
import os
import pkgutil
import re
import sys
from pathlib import Path

HIER = Path(__file__).parent
PROGRAMM = HIER.parent / "programm" / "rohrlaser"
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QDate, Qt, QTimer  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QApplication, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QInputDialog,  # noqa: E402
                               QLineEdit, QMessageBox, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

import rohrlaser  # noqa: E402
from rohrlaser import eingabe, tastatur  # noqa: E402
from rohrlaser.mengen_dialog import StueckDialog  # noqa: E402

# Bewusste Ausnahmen (ENTER_SCHLIESST = True): neue nur nach Rücksprache eintragen
AUSNAHMEN = {"rohrlaser.befehlspalette.Befehlspalette"}


def ok(t):
    print("OK    ", t)


def warten():
    for _ in range(3):
        app.processEvents()


app = QApplication.instance() or QApplication([])
tastatur.einrichten(app)
assert tastatur.einrichten(app) is app._enter_regel, "Regel doppelt eingerichtet"


def felder_dialog(d):
    """Typische Eingaben und OK/Abbrechen in den (beliebigen) Dialog d legen."""
    lay = QVBoxLayout(d)
    d.text = QLineEdit("alt")
    d.zahl = QSpinBox()
    d.zahl.setRange(0, 1000)
    d.rechen = eingabe.RechenSpin()
    d.rechen.setRange(0, 10000)
    d.datum = QDateEdit(QDate(2026, 10, 28))
    d.auswahl = QComboBox()
    d.auswahl.addItems(["a", "b"])
    d.frei = QComboBox()
    d.frei.setEditable(True)
    d.frei.addItems(["x", "y"])
    d.tabelle = QTableWidget(3, 2)
    for r in range(3):
        for c in range(2):
            d.tabelle.setItem(r, c, QTableWidgetItem(f"{r}{c}"))
    d.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    d.knoepfe.accepted.connect(d.accept)
    d.knoepfe.rejected.connect(d.reject)
    for w in (d.text, d.zahl, d.rechen, d.datum, d.auswahl, d.frei, d.tabelle, d.knoepfe):
        lay.addWidget(w)
    return d


def enter_in_feldern(d, name):
    """E1: Enter in jedem Feld lässt d offen (Ergebnis bleibt 0)."""
    d.show()
    warten()
    for feld, tippen in ((d.text, "neu"), (d.zahl, "42"), (d.rechen, "10+5"), (d.datum, None), (d.auswahl, None),
                         (d.frei, "z"), (d.tabelle, None)):
        feld.setFocus()
        if tippen is not None:
            (feld.lineEdit() if hasattr(feld, "lineEdit") and feld.lineEdit() else feld).selectAll()
            QTest.keyClicks(feld, tippen)
        for taste in (Qt.Key_Return, Qt.Key_Enter):
            QTest.keyClick(feld, taste)
            warten()
            assert d.isVisible() and d.result() == 0, f"{name}: Enter in {type(feld).__name__} schließt das Fenster"
    QTest.keyClick(d, Qt.Key_Return)            # Enter direkt am Dialog
    warten()
    assert d.isVisible() and d.result() == 0, f"{name}: Enter am Dialog schließt das Fenster"


# ------------------------------------------------------------------ E1 einfacher Dialog
d = felder_dialog(QDialog())
enter_in_feldern(d, "QDialog")
assert d.text.text() == "neu" and d.zahl.value() == 42 and d.rechen.value() == 15, \
    (d.text.text(), d.zahl.value(), d.rechen.value())
ok("E1 Enter in Text, Zahl, Rechenfeld (10+5 = 15), Datum, Auswahl, Tabelle: Fenster bleibt offen, Wert übernommen")

d.tabelle.setFocus()
d.tabelle.setCurrentCell(0, 1)
QTest.keyClick(d.tabelle, Qt.Key_Return)
warten()
assert d.isVisible() and d.tabelle.currentRow() == 1 and d.tabelle.currentColumn() == 1, d.tabelle.currentRow()
d.tabelle.setRowHidden(2, True)
QTest.keyClick(d.tabelle, Qt.Key_Return)
warten()
assert d.tabelle.currentRow() == 1, "ausgeblendete Zeile angesprungen"
ok("E1 Tabelle: Enter springt eine Zeile weiter (ausgeblendete übersprungen), letzte Zeile bleibt stehen")

# Zelle bearbeiten und mit Enter bestätigen: Wert in der Zelle, Fenster offen
d.tabelle.setCurrentCell(0, 0)
d.tabelle.editItem(d.tabelle.item(0, 0))
warten()
editor = QApplication.focusWidget()
assert isinstance(editor, QLineEdit), type(editor)
editor.selectAll()
QTest.keyClicks(editor, "77")
QTest.keyClick(editor, Qt.Key_Return)
warten()
assert d.isVisible() and d.result() == 0 and d.tabelle.item(0, 0).text() == "77", d.tabelle.item(0, 0).text()
ok("E1 Tabellenzelle bearbeitet und mit Enter bestätigt: Wert steht, Fenster offen")

# ------------------------------------------------------------------ E2 Strg+Enter und Knopf mit Fokus
d.text.setFocus()
QTest.keyClick(d.text, Qt.Key_Return, Qt.ControlModifier)
warten()
assert not d.isVisible() and d.result() == QDialog.Accepted, "Strg+Enter übernimmt nicht"
ok("E2 Strg+Enter klickt OK (übernimmt und schließt)")

d = felder_dialog(QDialog())
d.show()
warten()
abbrechen = d.knoepfe.button(QDialogButtonBox.Cancel)
abbrechen.setFocus()
QTest.keyClick(abbrechen, Qt.Key_Return)
warten()
assert not d.isVisible() and d.result() == QDialog.Rejected, "Enter auf Knopf mit Fokus wirkt nicht"
ok("E2 Enter auf einem angewählten Knopf (Abbrechen) drückt diesen Knopf")

d = QDialog()                   # ohne Knopfleiste: Standardknopf
lay = QVBoxLayout(d)
d.text = QLineEdit()
uebernehmen = QPushButton("Übernehmen")
uebernehmen.setDefault(True)
uebernehmen.clicked.connect(d.accept)
lay.addWidget(d.text)
lay.addWidget(uebernehmen)
d.show()
warten()
d.text.setFocus()
QTest.keyClick(d.text, Qt.Key_Return)
warten()
assert d.isVisible() and d.result() == 0
QTest.keyClick(d.text, Qt.Key_Enter, Qt.ControlModifier | Qt.KeypadModifier)
warten()
assert d.result() == QDialog.Accepted
ok("E2 ohne Knopfleiste: Enter hält, Strg+Enter (Ziffernblock) drückt den Standardknopf")


# ------------------------------------------------------------------ E3 Ausnahmen
def schliesst_mit_enter(d):
    d.show()
    warten()
    QTest.keyClick(QApplication.focusWidget() or d, Qt.Key_Return)
    warten()
    return not d.isVisible()


frage = QMessageBox(QMessageBox.Question, "Frage", "Wirklich?", QMessageBox.Yes | QMessageBox.No)
frage.setDefaultButton(QMessageBox.Yes)
assert schliesst_mit_enter(frage) and frage.result() == QMessageBox.Yes
ok("E3 Ja/Nein-Frage (QMessageBox): Enter = Standardantwort (Ausnahme)")

for art in ("text", "zahl"):
    q = QInputDialog()
    if art == "zahl":
        q.setInputMode(QInputDialog.DoubleInput)
    q.show()
    warten()
    feld = QApplication.focusWidget()
    QTest.keyClick(feld, Qt.Key_Return)
    warten()
    assert q.isVisible() and q.result() == 0, f"QInputDialog ({art}) schließt mit Enter"
    QTest.keyClick(feld, Qt.Key_Return, Qt.ControlModifier)
    warten()
    assert not q.isVisible() and q.result() == QDialog.Accepted, art
ok("E3 Eingabefrage (QInputDialog Text/Zahl): Enter hält, Strg+Enter übernimmt")

# ------------------------------------------------------------------ E4 alle Dialogklassen des Programms
for m in pkgutil.iter_modules(rohrlaser.__path__):
    importlib.import_module("rohrlaser." + m.name)


def unterklassen(k):
    for u in k.__subclasses__():
        yield u
        yield from unterklassen(u)


klassen = sorted({k for k in unterklassen(QDialog) if k.__module__.startswith("rohrlaser")},
                 key=lambda k: (k.__module__, k.__qualname__))
assert len(klassen) >= 50, len(klassen)
ausnahmen = {f"{k.__module__}.{k.__qualname__}" for k in klassen if getattr(k, "ENTER_SCHLIESST", False)}
assert ausnahmen == AUSNAHMEN, f"Ausnahmen geändert: {sorted(ausnahmen ^ AUSNAHMEN)}"

TASTEN_METHODEN = ("keyPressEvent", "event", "eventFilter", "keyReleaseEvent")


def tastenteil(k):
    """Prüfklasse mit der Tastenbehandlung von k (eigene keyPressEvent/event … aus allen Programm-Basisklassen),
    ohne die Daten, die k zum Aufbau braucht."""
    eigen = {}
    for basis in reversed(k.__mro__):
        if basis.__module__.startswith("rohrlaser"):
            eigen.update({n: v for n, v in vars(basis).items() if n in TASTEN_METHODEN})
    return type("Pruef" + k.__name__, (QDialog,), eigen), sorted(eigen)


geprueft, mit_tasten = [], []
for k in klassen:
    name = f"{k.__module__}.{k.__qualname__}"
    if name in AUSNAHMEN:
        continue
    pruef, eigen = tastenteil(k)
    d = felder_dialog(pruef())
    enter_in_feldern(d, name)
    d.reject()
    QTimer.singleShot(0, d.deleteLater)
    geprueft.append(name)
    if eigen:
        mit_tasten.append(f"{k.__name__} ({', '.join(eigen)})")
warten()
ok(f"E4 alle {len(geprueft)} Dialogklassen des Programms: Enter in jedem Feld schließt nicht, auch mit eigener "
   f"Tastenbehandlung: {'; '.join(mit_tasten) or '–'} (Ausnahmen: "
   f"{', '.join(sorted(n.rsplit('.', 1)[1] for n in AUSNAHMEN))})")

# ------------------------------------------------------------------ E5 Quelltext
SCHLIESST = re.compile(r"\.(returnPressed|editingFinished)\.connect\(\s*(self\.|d\.|dialog\.)?(accept|reject|close|done)\b")
treffer = [f"{p.name}:{i}" for p in sorted(PROGRAMM.glob("*.py"))
           for i, z in enumerate(p.read_text(encoding="utf-8").splitlines(), 1) if SCHLIESST.search(z)]
assert not treffer, f"Eingabefeld schließt per Enter den Dialog: {treffer}"
start = (PROGRAMM / "__main__.py").read_text(encoding="utf-8")
assert "tastatur.einrichten(app)" in start, "Enter-Regel wird beim Start nicht eingerichtet"
assert any(t == "Strg+Enter" for t, _, _ in tastatur.UEBERSICHT)
ok("E5 Quelltext: kein returnPressed/editingFinished → accept/close; Regel beim Start eingerichtet, Strg+Enter in "
   "der Tastenübersicht")

# ------------------------------------------------------------------ E6 echte Dialoge
s = StueckDialog(None, 3, False)
s.show()
warten()
s.faktor_feld.setFocus()
s.faktor_feld.selectAll()
QTest.keyClicks(s.faktor_feld, "3")
QTest.keyClick(s.faktor_feld, Qt.Key_Return)
warten()
assert s.isVisible() and s.result() == 0, "Stückzahl ändern schließt mit Enter"
QTest.keyClick(s.faktor_feld, Qt.Key_Return, Qt.ControlModifier)
warten()
assert s.result() == QDialog.Accepted and s.faktor == 3, s.faktor
ok("E6 Stückzahl ändern: Enter hält, Strg+Enter übernimmt × 3")


def eingabefrage(art):
    """QInputDialog.getDouble/getInt wie im Programm (Ecke abrunden, Bestand korrigieren)."""
    gesehen = {}

    def pruefen():
        q = next(w for w in QApplication.topLevelWidgets() if isinstance(w, QInputDialog) and w.isVisible())
        feld = QApplication.focusWidget()
        QTest.keyClick(feld, Qt.Key_Return)
        warten()
        gesehen["offen"] = q.isVisible()
        q.reject()
    QTimer.singleShot(50, pruefen)
    if art == "double":
        QInputDialog.getDouble(None, "Ecke abrunden", "Radius [mm]", 5, 0, 1000, 1)
    else:
        QInputDialog.getInt(None, "Bestand korrigieren", "neuer Bestand", 3, 0, 10000)
    return gesehen.get("offen")


assert eingabefrage("double") and eingabefrage("int")
ok("E6 Ecke abrunden / Bestand korrigieren (Eingabefragen): Enter schließt nicht")

print("\nAlle Enter-Prüfungen bestanden.")
