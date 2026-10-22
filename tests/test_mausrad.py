"""Prüft, dass das Mausrad über Zahlenfeldern, Auswahllisten, Datumsfeldern und Schiebereglern keine Werte ändert,
sondern die Seite bzw. Tabelle darunter rollt – auch für Editoren in Tabellenzellen und im echten Hauptfenster.
Bildlaufleisten rollen weiter, aufgeklappte Listen bleiben unberührt.

Aufruf: python tests/test_mausrad.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QDate, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import (QApplication, QComboBox, QDateEdit, QDoubleSpinBox, QScrollArea, QSlider,  # noqa: E402
                               QSpinBox, QTableWidget, QTabWidget, QVBoxLayout, QWidget)

from rohrlaser import mausrad  # noqa: E402

app = QApplication.instance() or QApplication([])
mausrad.einrichten(app)
FEHLER = []


def ok(text):
    print("OK    ", text)


def fehler(text):
    print("FEHLER", text)
    FEHLER.append(text)


def pruefe(bed, text):
    ok(text) if bed else fehler(text)


def rad(w, nach_unten=True):
    d = -120 if nach_unten else 120
    pos = QPointF(w.width() / 2, w.height() / 2)
    e = QWheelEvent(pos, QPointF(w.mapToGlobal(pos.toPoint())), QPoint(0, 0), QPoint(0, d),
                    Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
    QApplication.sendEvent(w, e)
    app.processEvents()


def seite():
    bereich = QScrollArea()
    bereich.setWidgetResizable(True)
    innen = QWidget()
    lay = QVBoxLayout(innen)
    felder = {"QSpinBox": QSpinBox(), "QDoubleSpinBox": QDoubleSpinBox(), "QComboBox": QComboBox(),
              "QComboBox editierbar": QComboBox(), "QDateEdit": QDateEdit(QDate(2026, 10, 22)),
              "QSlider": QSlider(Qt.Horizontal)}
    for f in felder.values():
        lay.addWidget(f)
        lay.addSpacing(400)
    felder["QSpinBox"].setRange(0, 1000)
    felder["QSpinBox"].setValue(50)
    felder["QDoubleSpinBox"].setRange(0, 1000)
    felder["QDoubleSpinBox"].setValue(50)
    for c in (felder["QComboBox"], felder["QComboBox editierbar"]):
        c.addItems(["a", "b", "c", "d"])
        c.setCurrentIndex(1)
    felder["QComboBox editierbar"].setEditable(True)
    felder["QSlider"].setRange(0, 100)
    felder["QSlider"].setValue(50)
    bereich.setWidget(innen)
    bereich.resize(300, 400)
    bereich.show()
    app.processEvents()
    return bereich, felder


def wert(f):
    if isinstance(f, QComboBox):
        return f.currentIndex()
    if isinstance(f, QDateEdit):
        return f.date()
    return f.value()


def test_seite():
    bereich, felder = seite()
    leiste = bereich.verticalScrollBar()
    for name, f in felder.items():
        for mit_fokus in (False, True):
            if mit_fokus:
                f.setFocus()
                app.processEvents()
            vorher, lauf = wert(f), leiste.value()
            rad(f)
            pruefe(wert(f) == vorher, f"{name}{' mit Fokus' if mit_fokus else ''}: Wert bleibt beim Mausrad")
            pruefe(leiste.value() > lauf or lauf == leiste.maximum(),
                   f"{name}{' mit Fokus' if mit_fokus else ''}: Seite rollt stattdessen ({lauf} → {leiste.value()})")
        pruefe(f.focusPolicy() == Qt.StrongFocus, f"{name}: Rad holt keinen Fokus (StrongFocus)")
    leiste.setValue(0)
    rad(leiste)
    pruefe(leiste.value() > 0, "Bildlaufleiste selbst rollt weiter mit dem Rad")
    bereich.close()


def test_tabelle():
    t = QTableWidget(60, 2)
    t.resize(300, 300)
    t.show()
    zahl = QSpinBox()
    zahl.setRange(0, 100)
    zahl.setValue(5)
    t.setCellWidget(2, 0, zahl)
    liste = QComboBox()
    liste.addItems(["x", "y", "z"])
    t.setCellWidget(3, 0, liste)
    app.processEvents()
    for f in (zahl, liste):
        vorher, lauf = wert(f), t.verticalScrollBar().value()
        rad(f)
        pruefe(wert(f) == vorher, f"Tabelle, {type(f).__name__} in Zelle: Wert bleibt")
        pruefe(t.verticalScrollBar().value() > lauf, f"Tabelle, {type(f).__name__} in Zelle: Tabelle rollt")
    t.close()


def test_hauptfenster():
    """Echtes Programm mit Beispielangebot: in allen Reitern und Unterreitern ändert das Rad kein Eingabefeld."""
    sys.path.insert(0, str(HIER))
    import beispiel_angebot
    from rohrlaser.datenbank import Datenbank
    from rohrlaser.fenster import Hauptfenster
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "rohrlaser.db")
    fenster = Hauptfenster(db, tmp, stumm=True)
    fenster.angebot_oeffnen(beispiel_angebot.anlegen(db))
    fenster.resize(1366, 768)
    fenster.show()
    app.processEvents()
    geprueft, geaendert = set(), []
    for reiter in fenster.findChildren(QTabWidget):
        for i in range(reiter.count()):
            if not reiter.isVisible():
                continue
            reiter.setCurrentIndex(i)
            app.processEvents()
            for f in fenster.findChildren(QWidget):
                if not mausrad.gesperrt(f) or not f.isVisible() or not f.isEnabled() or id(f) in geprueft:
                    continue
                geprueft.add(id(f))
                vorher = wert(f)
                rad(f)
                rad(f, nach_unten=False)
                if wert(f) != vorher:
                    geaendert.append(f"{type(f).__name__} {f.objectName()}")
    pruefe(len(geprueft) >= 10 and not geaendert,
           f"Hauptfenster: {len(geprueft)} sichtbare Eingabefelder mit dem Rad geprüft, geändert: {geaendert or 'keines'}")
    fenster.close()


if __name__ == "__main__":
    test_seite()
    test_tabelle()
    test_hauptfenster()
    print()
    print("FEHLER:" if FEHLER else "Alle Prüfungen bestanden.", len(FEHLER) if FEHLER else "")
    sys.exit(1 if FEHLER else 0)
