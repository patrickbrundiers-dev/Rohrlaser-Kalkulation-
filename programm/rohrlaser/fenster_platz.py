"""Fenster passen auf den Bildschirm und das offene Fenster bleibt vorne (Plan Eingabefelder E3/E6, 25.10.2026).

Ereignisfilter an der QApplication, beim ersten Zeigen jedes Fensters (Dialoge, Editoren, eigene Fenster):
- Größe höchstens der freie Bereich des Bildschirms (ohne Taskleiste), Lage ganz auf dem Bildschirm. Das gilt auch
  für die gemerkte Größe (fenster_merken, B4), die auf einem großen Monitor gemerkt und am Laptop geöffnet wird.
- Fenster ohne Elternfenster bekommen das Hauptfenster als „Besitzer“ (transient parent): unter Windows liegen sie
  dann immer vor dem Hauptfenster und verschwinden nicht mehr dahinter, wenn man ins Hauptfenster klickt.
- Das neue Fenster kommt nach vorn und bekommt den Fokus.

Wird vor fenster_merken.FensterMerker installiert: Qt ruft den zuletzt installierten Filter zuerst auf, so setzt der
Merker erst die gemerkte Größe und dieser Filter passt sie danach an.
"""
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget

RAND = 8            # Abstand zum Bildschirmrand [px]
TITEL = 32          # Titelleiste und Rahmen, die Qt vor dem ersten Zeigen noch nicht kennt [px]


def frei(w):
    """Freier Bereich des Bildschirms, auf dem das Fenster liegt (sonst des Hauptbildschirms); None ohne Bildschirm."""
    bild = None
    try:
        bild = QApplication.screenAt(w.geometry().center()) or w.screen() or QApplication.primaryScreen()
    except RuntimeError:
        return None
    return bild.availableGeometry() if bild is not None else None


def einpassen(w):
    """Fenster auf den freien Bildschirm kürzen und hineinschieben. Ergebnis: True, wenn etwas geändert wurde."""
    if w.isMaximized() or w.isFullScreen():
        return False
    r = frei(w)
    if r is None or r.width() < 200 or r.height() < 200:
        return False
    innen = r.adjusted(RAND, TITEL, -RAND, -RAND)
    breite = max(min(w.width(), innen.width()), min(w.minimumWidth(), r.width()))
    hoehe = max(min(w.height(), innen.height()), min(w.minimumHeight(), r.height()))
    geaendert = (breite, hoehe) != (w.width(), w.height())
    if geaendert:
        w.resize(breite, hoehe)
    g = w.geometry()
    x = max(innen.left(), min(g.x(), innen.right() + 1 - g.width()))
    y = max(innen.top(), min(g.y(), innen.bottom() + 1 - g.height()))
    if (x, y) != (g.x(), g.y()):
        w.move(w.x() + x - g.x(), w.y() + y - g.y())
        geaendert = True
    return geaendert


class FensterPlatz(QObject):
    def __init__(self, hauptfenster, parent=None):
        super().__init__(parent)
        self.haupt = hauptfenster
        self.gesehen = set()

    @staticmethod
    def _fenster(w):
        return isinstance(w, QWidget) and w.isWindow() and w.windowType() in (Qt.Window, Qt.Dialog) \
            and not isinstance(w, QMainWindow)

    def eventFilter(self, w, e):
        if e.type() == QEvent.Show and self._fenster(w) and id(w) not in self.gesehen:
            self.gesehen.add(id(w))
            w.destroyed.connect(lambda *_a, i=id(w): self.gesehen.discard(i))
            self.besitzer_setzen(w)
            einpassen(w)
            QTimer.singleShot(0, lambda w=w: self.nach_vorn(w))
        return False

    def besitzer_setzen(self, w):
        """Fenster ohne Elternfenster: Hauptfenster (bzw. aktives Fenster) als Besitzer, damit es davor bleibt."""
        if w.parentWidget() is not None or w is self.haupt:
            return False
        besitzer = QApplication.activeWindow()
        if besitzer is None or besitzer is w or not besitzer.isVisible():
            besitzer = self.haupt
        try:
            fw, bw = w.windowHandle(), besitzer.windowHandle() if besitzer is not None else None
        except RuntimeError:
            return False
        if fw is None or bw is None or fw.transientParent() is not None:
            return False
        fw.setTransientParent(bw)
        return True

    @staticmethod
    def nach_vorn(w):
        try:
            if w.isVisible() and not (w.windowFlags() & Qt.WindowDoesNotAcceptFocus):
                w.raise_()
                w.activateWindow()
        except RuntimeError:        # Fenster schon wieder zu
            pass


def einrichten(hauptfenster):
    """Filter an der QApplication installieren (einmal je Hauptfenster)."""
    f = FensterPlatz(hauptfenster, hauptfenster)
    QApplication.instance().installEventFilter(f)
    return f
