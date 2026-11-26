"""Zentrale Fensterverwaltung (Auftrag Patrick 26.11.2026 „Einheitliches Fenster- und Dialogmanagement“, Entscheidung
„Nur Fenster mit Inhalt maximiert“).

F1 Fenster mit Inhalt (Tabelle, Größe) öffnet ohne gemerkten Stand maximiert; kurze Rückfrage bleibt klein, auch mit
   Auswahlliste (Combobox zählt nicht als Inhalt);
F2 Titelleiste: Minimieren, Maximieren, Schließen; feste Größe nur Schließen; kein ?-Knopf;
F3 verkleinert geschlossen: öffnet in der gemerkten Größe, nicht maximiert; maximiert geschlossen: öffnet maximiert;
F4 je Benutzer: ein anderes Kürzel hat eigenen Stand; ältere Einträge ohne Kürzel gelten weiter;
F5 Eigenschaft fenster_groesse und Vorgabe aus (Ansicht) werden beachtet; Fenstergrößen zurücksetzen;
F6 Menü Ansicht hat beide Einträge, Teiler werden weiter gemerkt.
Aufruf: python tests/test_fensterverwaltung.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QLabel, QLineEdit, QSplitter,  # noqa: E402
                               QTableWidget, QTextEdit, QVBoxLayout)

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
from rohrlaser import fenster_merken as fm  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


class Liste(QDialog):
    """Fenster mit Inhalt: Tabelle, Teiler, 800 × 600."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Liste")
        lay = QVBoxLayout(self)
        self.teiler = QSplitter()
        self.teiler.addWidget(QTableWidget(20, 5))
        self.teiler.addWidget(QTextEdit())
        lay.addWidget(self.teiler)
        self.resize(800, 600)


class Frage(QDialog):
    """Kurze Rückfrage mit Eingabe und Auswahlliste."""

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Wie viele Stück?"))
        lay.addWidget(QLineEdit())
        c = QComboBox()
        c.addItems(["1", "2", "3"])
        lay.addWidget(c)


class Fest(QDialog):
    def __init__(self):
        super().__init__()
        QVBoxLayout(self).addWidget(QLabel("Feste Größe"))
        self.setFixedSize(300, 120)


db = Datenbank(Path(tempfile.mkdtemp()) / "x.db")
merker = fm.FensterMerker(db, benutzer="PB")
app.installEventFilter(merker)


def zeigen(w):
    w.show()
    app.processEvents()
    return w


def zu(w):
    w.close()
    app.processEvents()


# ---------------------------------------------------------------- F1
d = zeigen(Liste())
pruefe(d.isMaximized(), "F1 Fenster mit Tabelle öffnet ohne gemerkten Stand maximiert")
q = zeigen(Frage())
pruefe(not q.isMaximized() and not fm.mit_inhalt(q), "F1 kurze Rückfrage mit Auswahlliste bleibt klein")
zu(q)

# ---------------------------------------------------------------- F2
fl = d.windowFlags()
pruefe(bool(fl & Qt.WindowMinimizeButtonHint) and bool(fl & Qt.WindowMaximizeButtonHint)
       and bool(fl & Qt.WindowCloseButtonHint) and not fl & Qt.WindowContextHelpButtonHint,
       "F2 Titelleiste mit Minimieren, Maximieren und Schließen, ohne ?")
fe = zeigen(Fest())
ff = fe.windowFlags()
pruefe(not ff & Qt.WindowMaximizeButtonHint and bool(ff & Qt.WindowCloseButtonHint) and not fe.isMaximized(),
       "F2 feste Größe: nur Schließen, nicht maximiert")
zu(fe)

# ---------------------------------------------------------------- F3
d.setWindowState(Qt.WindowNoState)
app.processEvents()
d.resize(700, 500)
d.teiler.setSizes([100, 500])
app.processEvents()
zu(d)
e = db.einstellung(fm.GEOMETRIE).get("PB|Liste")
pruefe(e is not None and e.get("m") is False, f"F3 gemerkt je Benutzer und Fensterart, nicht maximiert ({e and e.get('m')})")
d2 = zeigen(Liste())
pruefe(not d2.isMaximized() and (d2.width(), d2.height()) == (700, 500), f"F3 öffnet verkleinert in 700 × 500 "
       f"({d2.width()} × {d2.height()})")
pruefe(d2.teiler.sizes()[0] < d2.teiler.sizes()[1], "F3 Teiler gemerkt")
d2.setWindowState(Qt.WindowMaximized)
app.processEvents()
zu(d2)
d3 = zeigen(Liste())
pruefe(d3.isMaximized(), "F3 maximiert geschlossen: öffnet maximiert")
d3.setWindowState(Qt.WindowNoState)
app.processEvents()
pruefe((d3.width(), d3.height()) == (700, 500), f"F3 Wiederherstellen kehrt zur gemerkten Größe zurück "
       f"({d3.width()} × {d3.height()})")
zu(d3)

# ---------------------------------------------------------------- F4
anderer = fm.FensterMerker(db, benutzer="MK")
app.removeEventFilter(merker)
app.installEventFilter(anderer)
d4 = zeigen(Liste())
pruefe(d4.isMaximized(), "F4 anderer Benutzer: eigener Stand (Vorgabe maximiert)")
zu(d4)
alle = db.einstellung(fm.GEOMETRIE)
alle["Frage"] = dict(g=alle["PB|Liste"]["g"], t=[])     # Eintrag wie vor 0.9.5xx, ohne Kürzel
db.einstellung_setzen(fm.GEOMETRIE, alle)
pruefe(anderer.eintrag(Frage()) is not None, "F4 alter Eintrag ohne Kürzel gilt weiter")

# ---------------------------------------------------------------- F5
app.removeEventFilter(anderer)
neu = fm.FensterMerker(db, benutzer="XY")
app.installEventFilter(neu)
k = Liste()
k.setProperty("fenster_groesse", "klein")
zeigen(k)
pruefe(not k.isMaximized(), "F5 fenster_groesse = klein bleibt klein")
k.setProperty("fenster_nicht_merken", True)
zu(k)
g = Frage()
g.setProperty("fenster_groesse", "maximiert")
g.setProperty("fenster_nicht_merken", True)
pruefe(fm.mit_inhalt(g), "F5 fenster_groesse = maximiert")
db.einstellung_setzen(fm.VORGABE, False)
d5 = zeigen(Liste())
pruefe(not d5.isMaximized(), "F5 Vorgabe aus: öffnet in eigener Größe")
zu(d5)
db.einstellung_setzen(fm.VORGABE, True)
n = neu.zuruecksetzen()
pruefe(n >= 1 and not any(s.startswith("XY|") for s in db.einstellung(fm.GEOMETRIE))
       and "PB|Liste" in db.einstellung(fm.GEOMETRIE), f"F5 Fenstergrößen zurücksetzen nur für den Benutzer ({n})")
app.removeEventFilter(neu)

# ---------------------------------------------------------------- F6 Menü
from PySide6.QtWidgets import QMainWindow, QMenu  # noqa: E402


class F(QMainWindow):
    pass


f = F()
f.db = db
f.meldungen = []
f.meldung = f.meldungen.append
f.fenster_merker = fm.FensterMerker(db, benutzer="PB")
m = QMenu("Ansicht", f)
a, b = fm.menue_eintraege(f, m)
pruefe(a.isCheckable() and a.isChecked() and b in m.actions(), "F6 Ansicht: Haken Vorgabe und Zurücksetzen")
a.setChecked(False)
pruefe(db.einstellung(fm.VORGABE) is False, "F6 Haken aus wird gemerkt")
b.trigger()
pruefe(f.meldungen and "zurückgesetzt" in f.meldungen[-1], f"F6 Zurücksetzen meldet {f.meldungen[-1:]}")

print(f"\n{len(fehler)} Fehler." if fehler else "\nAlles in Ordnung.")
sys.exit(1 if fehler else 0)
