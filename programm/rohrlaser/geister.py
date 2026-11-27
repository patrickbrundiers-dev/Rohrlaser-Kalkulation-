"""Losgelöste Bedienelemente verhindern (Supportpaket 27.11.2026, Foto Patrick).

Ein Knopf, Haken oder ein Auswahlfeld, das mit setVisible(True) eingeblendet wird, BEVOR es in einem Fenster steckt
(Layout noch nicht am Fenster), wird von Qt als eigenes kleines Fenster gezeigt. Unter Windows blieben solche Teile
(„＋ Neue Zusatzarbeit …“, „STEP-Dateien in den Ordner des Angebots kopieren“, „(Zusatzarbeit)“) losgelöst über dem
Hauptfenster stehen und überdeckten Texte.

Die Wache (Ereignisfilter der Anwendung, nur Show) erkennt so ein Teil beim Zeigen: es zählt nie als Fenster für
Fensterverwaltung und Fensterlage (fenster_merken, fenster_platz), die Stelle kommt einmal ins Protokoll, und steckt
es nach dem Aufbau (nächster Durchlauf der Ereignisschleife) immer noch in keinem Fenster, wird es ausgeblendet.
Bewusst eigene Fenster (mit Fenstertitel oder Eigenschaft eigenes_fenster) bleiben unberührt.

Reste nach dem Schließen: Unter Windows zeichnete das Hauptfenster (mit 3D-Ansicht über OpenGL zusammengesetzt) die
Fläche unter einem gerade geschlossenen kleinen Fenster (Tooltip, so ein Bedienelement, Auswahlliste) nicht immer neu;
Bruchstücke blieben stehen, z. B. nur die erste Zeile eines Tooltips über der Tabelle. Die Wache lässt deshalb nach dem
Verschwinden (und Verschieben) jedes solchen Fensters die Fläche darunter in allen anderen Fenstern neu zeichnen.
"""
import traceback

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (QAbstractButton, QAbstractSlider, QAbstractSpinBox, QComboBox, QLabel, QLineEdit,
                               QProgressBar)

EINZELTEILE = (QAbstractButton, QLabel, QComboBox, QLineEdit, QAbstractSpinBox, QProgressBar, QAbstractSlider)
funde = []          # [(Klasse, Text, Stelle)] dieses Laufs (Tests, Diagnose)


def losgeloest(w):
    """Bedienelement ohne Eltern, das Qt als eigenes Fenster zeigen würde (und kein gewolltes Fenster ist)?"""
    try:
        return (isinstance(w, EINZELTEILE) and w.parent() is None and w.windowType() == Qt.Window
                and not w.windowTitle() and not w.property("eigenes_fenster"))
    except RuntimeError:
        return False


def _stelle():
    for f in reversed(traceback.extract_stack()[:-3]):
        if "geister.py" not in f.filename and "ereignis_verteiler" not in f.filename:
            return f"{f.filename.replace(chr(92), '/').rsplit('/', 1)[-1]}:{f.lineno}"
    return ""


def aufraeumen(w):
    try:
        if losgeloest(w) and w.isVisible():
            w.hide()
            return True
    except RuntimeError:        # schon gelöscht
        pass
    return False


def neu_zeichnen_unter(rahmen, ausser=None):
    """Fläche rahmen (globale Koordinaten) in allen sichtbaren Fenstern außer 'ausser' neu zeichnen lassen."""
    from PySide6.QtWidgets import QApplication
    n = 0
    for f in QApplication.topLevelWidgets():
        try:
            if f is ausser or not f.isVisible() or f.isMinimized():
                continue
            r = rahmen.translated(-f.mapToGlobal(f.rect().topLeft())).adjusted(-3, -3, 3, 3) & f.rect()
            if not r.isEmpty():
                f.update(r)
                n += 1
        except RuntimeError:
            continue
    return n


def _klein(w):
    """Kleines Fenster, unter dem neu gezeichnet wird: Tooltip, Auswahlliste/Menü, losgelöstes Bedienelement."""
    return w.windowType() in (Qt.ToolTip, Qt.Popup) or isinstance(w, EINZELTEILE)


class Wache(QObject):
    def eventFilter(self, w, e):
        art = e.type()
        if art in (QEvent.Hide, QEvent.Move):
            if w.isWidgetType() and w.isWindow() and _klein(w):
                if art == QEvent.Move:
                    alt = w.frameGeometry().translated(e.oldPos() - e.pos())
                else:
                    alt = w.frameGeometry()
                QTimer.singleShot(0, lambda r=alt, w=w: neu_zeichnen_unter(r, w))
            return False
        if art == QEvent.Show and w.isWidgetType() and losgeloest(w):
            text = w.text() if hasattr(w, "text") and callable(w.text) else ""
            if isinstance(w, QComboBox):
                text = w.currentText()
            fund = (type(w).__name__, str(text)[:60], _stelle())
            if fund not in funde:
                funde.append(fund)
                from . import protokoll
                protokoll.warnung(f"Bedienelement ohne Fenster eingeblendet: {fund[0]} „{fund[1]}“ {fund[2]}")
            QTimer.singleShot(0, lambda w=w: aufraeumen(w))
        return False


_wache = None


def _ausgeben():
    """Entwicklung: ROHRLASER_GEISTER=Ordner schreibt die Funde dieses Laufs (Prüfung aller Dialoge per Testsuite)."""
    import json
    import os
    ordner = os.environ.get("ROHRLASER_GEISTER")
    if ordner and funde:
        with open(os.path.join(ordner, f"geister_{os.getpid()}.json"), "w", encoding="utf-8") as f:
            json.dump(funde, f, ensure_ascii=False)


def einrichten(app=None):
    """Wache einmal an der Anwendung anmelden."""
    global _wache
    if _wache is None:
        from . import ereignis_verteiler
        _wache = Wache()
        import atexit
        import os
        if os.environ.get("ROHRLASER_GEISTER"):
            atexit.register(_ausgeben)
        ereignis_verteiler.anmelden(_wache, (QEvent.Show, QEvent.Hide, QEvent.Move), app)
    return _wache
