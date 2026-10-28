"""Das Programm merkt sich Fenster (Plan Bedienung B4): Größe, Lage und Teiler jedes Dialogs je Fensterart, und welche
Angebote beim Beenden offen waren (Freigabe F2a: sie öffnen beim nächsten Start wieder, samt Unterreiter).

Gemerkt wird in der eigenen Datendatei (Einstellungen fenster_geometrie, sitzung_offen), nicht im gemeinsamen Ordner.
Meldungs-, Datei- und Eingabefenster von Qt bleiben außen vor; die Teile-Editoren öffnen weiter maximiert.
"""
import base64

from PySide6.QtCore import QByteArray, QEvent, QObject, QTimer
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QInputDialog, QMessageBox, QProgressDialog,
                               QSplitter)

GEOMETRIE = "fenster_geometrie"     # {Fensterart: {"g": Geometrie, "t": [Teiler-Zustände]}} (base64)
SITZUNG = "sitzung_offen"           # {"angebote": [IDs], "aktiv": ID, "unterreiter": {ID: Index}}
OHNE = (QMessageBox, QFileDialog, QInputDialog, QProgressDialog)


def _b64(daten):
    return base64.b64encode(bytes(daten)).decode("ascii")


def _bytes(text):
    try:
        return QByteArray(base64.b64decode(text))
    except (ValueError, TypeError):
        return None


def art(dialog):
    """Schlüssel der Fensterart: Klasse, bei Dialogen ohne eigene Klasse dazu der Fenstertitel ohne Zahlen."""
    name = type(dialog).__name__
    if name == "QDialog":
        titel = "".join(c for c in (dialog.windowTitle() or "") if not c.isdigit()).strip()
        name += ":" + titel[:40]
    return name


class FensterMerker(QObject):
    """Ereignisfilter an der QApplication: beim ersten Zeigen eines Dialogs Größe, Lage und Teiler setzen, beim
    Schließen merken."""

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.gesetzt = set()        # id() der Dialoge, die schon eingerichtet sind

    def _alle(self):
        try:
            d = self.db.einstellung(GEOMETRIE)
        except Exception:           # noqa: BLE001 – Datendatei geschlossen o. Ä.: nichts merken
            return {}
        return d if isinstance(d, dict) else {}

    @staticmethod
    def _passt(w):
        return isinstance(w, QDialog) and not isinstance(w, OHNE) and w.isWindow() \
            and not w.property("fenster_nicht_merken")

    def eventFilter(self, w, e):
        t = e.type()
        if t == QEvent.Show and self._passt(w) and id(w) not in self.gesetzt:
            self.gesetzt.add(id(w))
            w.destroyed.connect(lambda *_a, i=id(w): self.gesetzt.discard(i))
            self.setzen(w)
        elif t in (QEvent.Hide, QEvent.Close) and self._passt(w) and id(w) in self.gesetzt:
            self.merken(w)
        return False

    def setzen(self, w):
        eintrag = self._alle().get(art(w))
        if not eintrag:
            return False
        if not w.isMaximized() and eintrag.get("g"):
            g = _bytes(eintrag["g"])
            if g is not None:
                w.restoreGeometry(g)
                self._auf_bildschirm(w)
        teiler = w.findChildren(QSplitter)
        for s, zustand in zip(teiler, eintrag.get("t") or [], strict=False):
            z = _bytes(zustand)
            if z is not None:
                s.restoreState(z)
        return True

    @staticmethod
    def _auf_bildschirm(w):
        """Lag das Fenster auf einem Bildschirm, den es nicht mehr gibt: in die Mitte des Hauptbildschirms."""
        bild = QApplication.screenAt(w.frameGeometry().center())
        if bild is None and QApplication.primaryScreen() is not None:
            r = QApplication.primaryScreen().availableGeometry()
            w.move(r.center() - w.rect().center())

    def merken(self, w):
        if getattr(self.db, "nur_lesen", False):
            return False
        alle = self._alle()
        alt = alle.get(art(w)) or {}
        eintrag = dict(g=alt.get("g") if w.isMaximized() else _b64(w.saveGeometry()),
                       t=[_b64(s.saveState()) for s in w.findChildren(QSplitter)])
        if eintrag == alt:
            return False
        alle[art(w)] = eintrag
        try:
            self.db.einstellung_setzen(GEOMETRIE, alle)
        except Exception:           # noqa: BLE001 – Lesemodus o. Ä.: Fenster einfach nicht merken
            return False
        return True


# ------------------------------------------------------------------ offene Angebote (F2a)
def sitzung_merken(fenster):
    """Beim Beenden: offene eigene Angebote, das aktive und den Unterreiter je Angebot merken."""
    db = fenster.db
    if getattr(db, "nur_lesen", False):
        return None
    ids = [i for i, s in fenster.offen.items() if not s.fremd()]
    aktiv = next((i for i, s in fenster.offen.items() if fenster.reiter.currentWidget() is s), None)
    stand = dict(angebote=ids, aktiv=aktiv,
                 unterreiter={str(i): s.reiter.currentIndex() for i, s in fenster.offen.items() if i in ids})
    try:
        db.einstellung_setzen(SITZUNG, stand)
    except Exception:               # noqa: BLE001
        return None
    return stand


def sitzung_wiederherstellen(fenster):
    """Beim Start: zuletzt offene Angebote wieder öffnen (nur noch vorhandene), Unterreiter und aktives Angebot wie
    beim Beenden. Ergebnis: Anzahl geöffneter Angebote."""
    stand = fenster.db.einstellung(SITZUNG)
    if not isinstance(stand, dict):
        return 0
    vorhanden = {a["id"] for a in fenster.db.angebote() if not a.get("fremd")}
    n = 0
    for i in stand.get("angebote") or []:
        if i not in vorhanden:
            continue
        s = fenster.angebot_oeffnen(i)
        if s is None:
            continue
        n += 1
        u = (stand.get("unterreiter") or {}).get(str(i))
        if isinstance(u, int) and 0 <= u < s.reiter.count():
            s.reiter.setCurrentIndex(u)
    if not n:
        return 0
    aktiv = fenster.offen.get(stand.get("aktiv"))
    if aktiv is not None:
        fenster.reiter.setCurrentWidget(aktiv)
    else:                           # Start bleibt im Reiter Angebote (PR #59)
        QTimer.singleShot(0, lambda: fenster.reiter.setCurrentWidget(fenster.angebote))
    fenster.meldung(f"{n} Angebot{'e' if n != 1 else ''} vom letzten Mal wieder geöffnet.")
    return n
