"""Layout-Rundgang (Patrick 11.11.2026: „Layout test – alles sichtbar, nichts überschnitten“).

Das Hauptfenster läuft ohne Bildschirm bei Laptop-Größen (1280 × 680 und 1366 × 728) in Hell und Dunkel, mit einem
optimierten Testangebot (erfundene Daten). Besucht werden alle Hauptreiter mit ihren Unterreitern, alle Reiter des
Angebots, alle Einstellungsseiten und jeder Menübefehl, der ein Fenster öffnet. Geprüft wird je Ansicht:
- keine abgeschnittenen Texte (texte_pruefen: Beschriftungen, Knöpfe, Platzhalter, Auswahlen, Spaltenköpfe),
- keine Bedienelemente, die sich überlappen (Geschwister im selben Eltern-Element),
- keine Bedienelemente, die aus ihrem Eltern-Element ragen (außer in Rollbereichen),
- die Reiter des Angebots passen ohne Blätterpfeile neben die Schrittanzeige (L1, die Anzeige kürzt sich).
Außerdem: Zahlen, die auf 0 gerundet werden, ohne Minus („-0,00“ in der Nachkalkulation, L4).

Aufruf: python tests/test_layout_rundgang.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER)]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QLocale, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (QAbstractScrollArea, QApplication, QDialog, QFileDialog, QInputDialog,  # noqa: E402
                               QMenu, QMessageBox, QRubberBand, QScrollBar, QSizeGrip, QSplitterHandle,
                               QStackedWidget, QTabWidget, QWidget)

QLocale.setDefault(QLocale(QLocale.German, QLocale.Germany))
app = QApplication.instance() or QApplication([])

from abnahme_angebote import ANGEBOTE  # noqa: E402
from rohrlaser import angebot_fenster, stil  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import zahl_als_text  # noqa: E402
from rohrlaser.texte_pruefen import abgeschnitten  # noqa: E402


def ok(text):
    print("OK    ", text)


# Dialoge und Rückfragen nicht blockieren: Meldungen mit „Nein“ beantworten, Dateiauswahl abbrechen
for _n in ("information", "warning", "critical", "question"):
    setattr(QMessageBox, _n, staticmethod(lambda *a, **k: QMessageBox.No))
QMessageBox.about = staticmethod(lambda *a, **k: None)
QMessageBox.aboutQt = staticmethod(lambda *a, **k: None)
QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: ([], ""))
QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: "")
QInputDialog.getText = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getItem = staticmethod(lambda *a, **k: ("", False))
QInputDialog.getInt = staticmethod(lambda *a, **k: (0, False))
QInputDialog.getDouble = staticmethod(lambda *a, **k: (0.0, False))
# Menübefehle, die nichts öffnen sollen (Programm beenden, Daten zurückholen/löschen, Online-Update, PDF-Anleitung)
AUSLASSEN = ("Beenden", "Schließen", "Wiederherstellen", "Update", "Anleitung", "löschen", "Löschen")


def _ort(w):
    t = []
    while w is not None:
        t.append(w.objectName() or type(w).__name__)
        if w.isWindow():
            break
        w = w.parentWidget()
    return " < ".join(t[:5])


def _ignorieren(w):
    return (w.isWindow() or w.objectName().startswith("qt_") or w.width() <= 2 or w.height() <= 2
            or isinstance(w, (QScrollBar, QSplitterHandle, QRubberBand, QSizeGrip, QMenu))
            or isinstance(w.parentWidget(), QStackedWidget) or getattr(w, "ueberlagert", False))


def ueberlappungen(wurzel):
    """Geschwister, die sich überdecken, und Kinder, die aus ihrem Eltern-Element ragen (ohne Rollbereiche)."""
    funde = []
    for p in [wurzel] + wurzel.findChildren(QWidget):
        if not p.isVisible() or isinstance(p, QAbstractScrollArea):
            continue
        kinder = [k for k in p.children() if isinstance(k, QWidget) and k.isVisible() and not _ignorieren(k)]
        for i, a in enumerate(kinder):
            for b in kinder[i + 1:]:
                s = a.geometry().intersected(b.geometry())
                if s.width() > 3 and s.height() > 3:
                    funde.append(f"überlappt {s.width()}×{s.height()} px: {_ort(a)} / {_ort(b)}")
        if isinstance(p.parentWidget(), QAbstractScrollArea):
            continue
        r = p.rect()
        for k in kinder:
            g = k.geometry()
            if k.width() > 8 and k.height() > 8 and (g.right() > r.right() + 3 or g.bottom() > r.bottom() + 3
                                                       or g.left() < -3 or g.top() < -3):
                funde.append(f"ragt heraus ({g.x()},{g.y()} {g.width()}×{g.height()} in {r.width()}×{r.height()}): "
                             f"{_ort(k)}")
    return funde


FUNDE = {}


def pruefen(w, name):
    QApplication.processEvents()
    if w.isVisible():
        f = [str(x) for x in abgeschnitten(w)] + ueberlappungen(w)
        if f:
            FUNDE[name] = f


def reiter_durchgehen(w, name, tiefe=0):
    tabs = [t for t in w.findChildren(QTabWidget) if t.isVisible() and t.window() is w.window()]
    tabs = [t for t in tabs if not any(o is not t and o.isAncestorOf(t) for o in tabs)]
    if not tabs or tiefe > 3:
        pruefen(w.window(), name)
        return
    for t in tabs:
        for i in range(t.count()):
            if t.isTabVisible(i) and t.isTabEnabled(i):
                t.setCurrentIndex(i)
                QApplication.processEvents()
                reiter_durchgehen(t.widget(i), f"{name}/{t.tabText(i)}", tiefe + 1)


def rundgang(thema, breite, hoehe):
    stil.anwenden(app, thema)
    FUNDE.clear()
    po = Path(tempfile.mkdtemp(prefix="rundgang_")) / "Rohrlaser-Angebotskalkulation"
    (po / "Daten").mkdir(parents=True)
    db = Datenbank(po / "Daten" / "rohrlaser.db")
    f = Hauptfenster(db, po, stumm=True)
    f.resize(breite, hoehe)
    f.show()
    v = ANGEBOTE[0]
    a = db.angebot_neu(dict(nummer="A-2026-0100", kunde="Metallbau Beispiel (erfunden)", kundennr="10417",
                            maschine=v["maschine"], stange=v["stange"]))
    for p in v["positionen"]:
        db.position_neu(a, dict(pos=p["pos"], artikel=p["artikel"], bezeichnung=p["bezeichnung"],
                                profil_id=p["profil"], werkstoff_id=p["werkstoff"], laenge=p["laenge"],
                                stueck=p["stueck"]))
    f.alles_neu_laden()
    f.angebot_oeffnen(a)
    QTest.qWait(1500)               # automatisch optimieren
    seite = f.reiter.currentWidget()
    # L1: alle Reiter des Angebots ohne Blätterpfeile, Schrittanzeige gekürzt statt verdrängt
    r = seite.reiter
    assert r.tabBar().width() >= r.tabBar().sizeHint().width(), (breite, r.tabBar().width(),
                                                                 r.tabBar().sizeHint().width())
    e = r.cornerWidget(Qt.TopRightCorner)
    assert e is seite.schritte and e.isVisible() and e.width() >= e.sizeHint().width() - 2, \
        (e.isVisible(), e.width(), e.sizeHint().width())
    stufe = e.stufe
    for i in range(f.reiter.count()):
        f.reiter.setCurrentIndex(i)
        QApplication.processEvents()
        reiter_durchgehen(f.reiter.widget(i), f"{f.reiter.tabText(i)}")
    f.reiter.setCurrentWidget(f.bereich)
    for s in f.einstellungen.seiten:
        f.bereich.zeigen(s)
        QApplication.processEvents()
        reiter_durchgehen(f.bereich, f"Einstellungen/{s.schluessel}")
    aktionen = []

    def sammeln(m, pfad):
        for act in m.actions():
            if act.menu():
                sammeln(act.menu(), pfad + "/" + act.menu().title().replace("&", ""))
            elif not act.isSeparator() and act.text():
                aktionen.append((pfad + "/" + act.text().replace("&", ""), act))
    for act in f.menuBar().actions():
        if act.menu():
            sammeln(act.menu(), act.menu().title().replace("&", ""))
    vorher = set(QApplication.topLevelWidgets())
    exec_alt, mb_alt = QDialog.exec, QMessageBox.exec
    geprueft = 0
    try:
        for pfad, act in aktionen:
            if any(x in pfad for x in AUSLASSEN):
                continue
            try:
                if not act.isEnabled():
                    continue
            except RuntimeError:
                continue
            offen = []

            def exec_(d, _o=offen, _p=pfad):
                d.show()
                _o.append(d)
                QApplication.processEvents()
                reiter_durchgehen(d, f"Menü {_p}")
                return 0
            QDialog.exec = exec_
            QMessageBox.exec = exec_
            act.trigger()
            QApplication.processEvents()
            for w in QApplication.topLevelWidgets():
                if w not in vorher and w is not f and w.isVisible() and not isinstance(w, QMenu):
                    if w not in offen:
                        reiter_durchgehen(w, f"Menü {pfad}")
                    geprueft += 1
                    w.close()
            QApplication.processEvents()
    finally:
        QDialog.exec, QMessageBox.exec = exec_alt, mb_alt
    assert geprueft >= 5, geprueft
    assert not FUNDE, "\n".join(f"{k}: {x}" for k, v in FUNDE.items() for x in v)
    f.close()
    return stufe, len(aktionen)


angebot_fenster.AngebotSeite.CHECK_SOFORT = False
for thema, breite, hoehe in (("Hell", 1280, 680), ("Hell", 1366, 728), ("Dunkel", 1366, 728), ("Hell", 1920, 1000)):
    stufe, n = rundgang(thema, breite, hoehe)
    ok(f"{thema} {breite} × {hoehe}: alle Reiter, Einstellungsseiten und {n} Menübefehle ohne abgeschnittene oder "
       f"überlappende Elemente; Angebotsreiter ohne Blätterpfeile (Schrittanzeige Stufe {stufe})")
    if breite == 1920:
        assert stufe == 0, stufe            # breit genug: Schrittanzeige voll

assert zahl_als_text(-0.001, 2) == "0,00" and zahl_als_text(-0.04, 1) == "0,0" and zahl_als_text(-0.4, 0) == "0"
assert zahl_als_text(-1.5, 2) == "-1,50" and zahl_als_text(-1000.0, 2) == "-1.000,00"
ok("L4 auf 0 gerundete Zahlen ohne Minus („0,00“ statt „-0,00“), echte negative Werte unverändert")
print("Alle Layout-Rundgang-Prüfungen bestanden.")
