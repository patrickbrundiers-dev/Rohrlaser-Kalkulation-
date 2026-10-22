"""Prüft die Windows-Tastenkürzel: Rückgängig/Wiederholen im Angebot (alle Arten von Änderungen, 3D-Netze bleiben),
Kopieren/Einfügen/Ausschneiden in Tabellen, Entf, Strg+N, Strg+F, Strg+S, Strg+W und dass Textfelder ihre
eigenen Kürzel behalten.

Aufruf: python tests/test_tastatur.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QItemSelectionModel, Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit  # noqa: E402

from rohrlaser import tastatur  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.verlauf import GRENZE  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
f.show()
f.activateWindow()
app.processEvents()


def taste(w, kombi):
    """Tastendruck wie vom Benutzer (Kürzel laufen über die Shortcut-Verarbeitung von Qt)."""
    w.setFocus()
    app.processEvents()
    seq = kombi.split("+")
    mod = Qt.NoModifier
    for m in seq[:-1]:
        mod |= {"Ctrl": Qt.ControlModifier, "Shift": Qt.ShiftModifier}[m]
    key = {"Del": Qt.Key_Delete, "Esc": Qt.Key_Escape, "Return": Qt.Key_Return, "F5": Qt.Key_F5,
           "F9": Qt.Key_F9, "Tab": Qt.Key_Tab, "PgDown": Qt.Key_PageDown,
           "PgUp": Qt.Key_PageUp}.get(seq[-1]) or getattr(Qt, "Key_" + seq[-1])
    QTest.keyClick(w, key, mod)
    app.processEvents()


def pos_werte(s, feld):
    return [p.get(feld) for p in db.positionen(s.id)]


# 1) Angebot anlegen (Strg+N in der Angebotsliste), Positionen (Strg+N im Angebot)
f.reiter.setCurrentWidget(f.angebote)
taste(f.angebote.ansicht, "Ctrl+N")
assert len(f.offen) == 1, "Strg+N in der Angebotsliste legt ein Angebot an"
s = next(iter(f.offen.values()))
assert f.reiter.currentWidget() is s
for _ in range(3):
    taste(s.pos_ansicht, "Ctrl+N")
    if s.pos_ansicht.state() == s.pos_ansicht.State.EditingState:
        s.pos_ansicht.setFocus()
assert len(db.positionen(s.id)) == 3, len(db.positionen(s.id))
spalte = {f2.name: i for i, (art, f2) in enumerate(s.pos_modell.spalten) if art == "feld"}

# 2) Werte ändern und Rückgängig/Wiederholen
for r, laenge in enumerate((1000, 1500, 2000)):
    s.pos_modell.setData(s.pos_modell.index(r, spalte["laenge"]), str(laenge))
    s.pos_modell.setData(s.pos_modell.index(r, spalte["stueck"]), "5")
assert pos_werte(s, "laenge") == [1000, 1500, 2000]
s.pos_modell.setData(s.pos_modell.index(1, spalte["laenge"]), "1750")
assert pos_werte(s, "laenge")[1] == 1750
taste(s.pos_ansicht, "Ctrl+Z")
assert pos_werte(s, "laenge")[1] == 1500, "Strg+Z nimmt die letzte Eingabe zurück"
assert "länge" in f.statusBar().currentMessage(), f.statusBar().currentMessage()
taste(s.pos_ansicht, "Ctrl+Y")
assert pos_werte(s, "laenge")[1] == 1750, "Strg+Y wiederholt"
taste(s.pos_ansicht, "Ctrl+Z")
taste(s.pos_ansicht, "Ctrl+Shift+Z")
assert pos_werte(s, "laenge")[1] == 1750, "Strg+Umschalt+Z wiederholt ebenfalls"

# Kopf ändern, rückgängig
s._kopf_speichern(next(fd for fd in __import__("rohrlaser.angebot", fromlist=["KOPF"]).KOPF if fd.name == "bemerkung"),
                  "Eilauftrag")
assert db.angebot(s.id)["bemerkung"] == "Eilauftrag"
taste(s.pos_ansicht, "Ctrl+Z")
assert not db.angebot(s.id)["bemerkung"], "Kopfänderung rückgängig"

# 3) Entf löscht markierte Positionen (stumm: ohne Rückfrage), 3D-Netz kommt mit Rückgängig wieder
pid = db.positionen(s.id)[0]["id"]
db.netz_speichern(pid, b"x" * 500)
s.neu_laden()
s.pos_ansicht.setCurrentIndex(s.pos_modell.index(0, spalte["laenge"]))
taste(s.pos_ansicht, "Del")
assert len(db.positionen(s.id)) == 2 and db.netz(pid) is None
taste(s.pos_ansicht, "Ctrl+Z")
assert len(db.positionen(s.id)) == 3 and db.netz(pid) == b"x" * 500, "gelöschte Position samt 3D-Netz zurück"
assert db.positionen(s.id)[0]["id"] == pid and db.positionen(s.id)[0]["laenge"] == 1000
taste(s.pos_ansicht, "Ctrl+Y")
assert len(db.positionen(s.id)) == 2
taste(s.pos_ansicht, "Ctrl+Z")
# Entf in einer anderen Tabelle des Angebots löscht keine Positionen
taste(s.kalk_ansicht, "Del")
assert len(db.positionen(s.id)) == 3

# 4) Kopieren und Einfügen (ein Block aus Excel = ein Schritt für Rückgängig)
sel = s.pos_ansicht.selectionModel()
s.pos_ansicht.setCurrentIndex(s.pos_modell.index(0, spalte["laenge"]))
sel.select(s.pos_modell.index(1, spalte["laenge"]), QItemSelectionModel.Select)
taste(s.pos_ansicht, "Ctrl+C")
assert QGuiApplication.clipboard().text().split("\n") == ["1.000,0", "1.750,0"], repr(QGuiApplication.clipboard().text())
QGuiApplication.clipboard().setText("111\t7\n222\t8\n")
s.pos_ansicht.setCurrentIndex(s.pos_modell.index(1, spalte["laenge"]))
taste(s.pos_ansicht, "Ctrl+V")
assert pos_werte(s, "laenge") == [1000, 111, 222], pos_werte(s, "laenge")
assert pos_werte(s, "stueck")[1:] == [7, 8], "Block füllt auch die nächste Spalte (Stückzahl)"
taste(s.pos_ansicht, "Ctrl+Z")
assert pos_werte(s, "laenge") == [1000, 1750, 2000], "Einfügen in einem Schritt rückgängig"
# ein Wert füllt alle markierten Zellen
QGuiApplication.clipboard().setText("9")
s.pos_ansicht.setCurrentIndex(s.pos_modell.index(0, spalte["stueck"]))
for r in (1, 2):
    sel.select(s.pos_modell.index(r, spalte["stueck"]), QItemSelectionModel.Select)
taste(s.pos_ansicht, "Ctrl+V")
assert pos_werte(s, "stueck") == [9, 9, 9], pos_werte(s, "stueck")
# Ausschneiden leert
s.pos_modell.setData(s.pos_modell.index(2, spalte["bezeichnung"]), "Halter")
s.pos_ansicht.setCurrentIndex(s.pos_modell.index(2, spalte["bezeichnung"]))
taste(s.pos_ansicht, "Ctrl+X")
assert QGuiApplication.clipboard().text() == "Halter" and not pos_werte(s, "bezeichnung")[2]
taste(s.pos_ansicht, "Ctrl+Z")
assert pos_werte(s, "bezeichnung")[2] == "Halter"

# 5) Staffeln: Strg+N legt eine Stufe mit den Mengen des Angebots an, Rückgängig nimmt sie zurück
s.reiter.setCurrentWidget(s.st_seite)
taste(s.st_seite.ansicht, "Ctrl+N")
assert len(db.staffel_stufen(s.id)) == 1
taste(s.st_seite.ansicht, "Ctrl+Z")
assert len(db.staffel_stufen(s.id)) == 0 and len(db.staffeln(s.id)) == 0, "neue Stufe rückgängig"
s.reiter.setCurrentIndex(0)

# 6) Textfelder behalten ihre Kürzel: Strg+Z im Suchfeld ändert das Angebot nicht
f.reiter.setCurrentWidget(f.angebote)
vorher = db.angebot_stand(s.id)
f.angebote.suche.setText("abc")
taste(f.angebote.suche, "Ctrl+Z")
assert db.angebot_stand(s.id)["positionen"] == vorher["positionen"]
taste(f.angebote.suche, "Esc")
assert f.angebote.suche.text() == "", "Esc leert die Suche"
taste(f.angebote.ansicht, "Ctrl+F")
assert app.focusWidget() is f.angebote.suche, "Strg+F springt ins Suchfeld"

# 7) Eingabe öffnet, Strg+W schließt das Angebot
f.angebot_schliessen(s.id)
f.angebote.neu_laden()
f.angebote.ansicht.setCurrentIndex(f.angebote.filter.index(0, 0))
taste(f.angebote.ansicht, "Return")
assert len(f.offen) == 1
s = next(iter(f.offen.values()))
s.reiter.setCurrentIndex(0)
taste(s.pos_ansicht, "Ctrl+PgDown")
assert s.reiter.currentIndex() == 1 and f.reiter.currentWidget() is s, "Strg+Bild↓: nächster Unterreiter"
taste(s.pos_ansicht, "Ctrl+PgUp")
assert s.reiter.currentIndex() == 0
i = f.reiter.currentIndex()
taste(s.pos_ansicht, "Ctrl+Tab")
assert f.reiter.currentIndex() == (i + 1) % f.reiter.count(), "Strg+Tab: nächster Hauptreiter"
taste(f.reiter, "Ctrl+Shift+Tab")
assert f.reiter.currentWidget() is s
taste(s.pos_ansicht, "Ctrl+W")
assert not f.offen, "Strg+W schließt das Angebot"
# Rückgängig außerhalb eines Angebots: nur ein Hinweis
taste(f.angebote.ansicht, "Ctrl+Z")
assert "geöffneten Angebot" in f.statusBar().currentMessage()

# 8) Stammdaten: Strg+C über mehrere Zellen, Strg+N, Entf mit Rückfrage (hier nur Zielprüfung)
kunden = next(x for x in f.seiten if x.t.name == "kunden")
f.reiter.setCurrentWidget(kunden)
n = len(db.zeilen("kunden"))
taste(kunden.ansicht, "Ctrl+N")
kunden.ansicht.setFocus()
assert len(db.zeilen("kunden")) == n + 1, "Strg+N legt in den Stammdaten eine Zeile an"
kunden.ansicht.selectAll()
taste(kunden.ansicht, "Ctrl+C")
assert QGuiApplication.clipboard().text().count("\n") == n, "alle Zeilen kopiert"
taste(kunden.ansicht, "F5")
assert f.statusBar().currentMessage() == "Aktualisiert."

# 9) Strg+S schließt eine offene Zelleingabe ab
s = f.angebot_oeffnen(db.angebote()[0]["id"])
s.pos_ansicht.setCurrentIndex(s.pos_modell.index(0, spalte["bezeichnung"]))
s.pos_ansicht.edit(s.pos_ansicht.currentIndex())
app.processEvents()
editor = app.focusWidget()
assert isinstance(editor, QLineEdit)
editor.setText("Winkel")
taste(editor, "Ctrl+S")
assert pos_werte(s, "bezeichnung")[0] == "Winkel", pos_werte(s, "bezeichnung")

# 10) Grenze des Verlaufs, Übersicht für Hilfe und Anleitung
for k in range(GRENZE + 5):
    s.pos_modell.setData(s.pos_modell.index(0, spalte["stueck"]), str(k + 20))
assert len(s.verlauf.zurueck) == GRENZE
assert all(len(z) == 3 for z in tastatur.UEBERSICHT)
f.kuerzel_zeigen()
print("test_tastatur: OK")
