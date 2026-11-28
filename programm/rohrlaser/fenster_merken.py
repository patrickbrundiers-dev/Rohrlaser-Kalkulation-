"""Zentrale Fensterverwaltung (Plan Bedienung B4, ausgebaut 26.11.2026 „Einheitliches Fenster- und Dialogmanagement“):
Größe, Lage, maximiert und Teiler jedes Fensters je Fensterart, Benutzer und Arbeitsplatz, und welche Angebote beim
Beenden offen waren (Freigabe F2a: sie öffnen beim nächsten Start wieder, samt Unterreiter).

Regeln (Entscheidung Patrick 26.11.2026: „Nur Fenster mit Inhalt maximiert“):
- Ein Fenster ohne gemerkten Stand öffnet maximiert, wenn es Inhalt hat (Tabellen, Listen, Reiter, Teiler, Texte,
  Zeichnungen und eine Größe ab etwa 560 × 420). Kurze Rückfragen, Eingaben und Meldungen bleiben klein.
  Ein Fenster kann das mit der Eigenschaft fenster_groesse = "klein" oder "maximiert" selbst festlegen.
- Jedes Fenster hat Minimieren, Maximieren/Wiederherstellen und Schließen in der Titelleiste und lässt sich in der
  Größe ändern und verschieben (außer Fenstern mit fester Größe).
- Beim Schließen merkt das Programm Größe, Lage, ob maximiert, und die Teiler, je Benutzer (angemeldetes Kürzel) und
  Arbeitsplatz. Beim nächsten Öffnen gilt das Gemerkte, auch wenn es kleiner war als die Vorgabe.
- Ansicht → „Fenster mit Inhalt maximiert öffnen“ schaltet die Vorgabe ab (dann öffnen Fenster in ihrer eigenen
  Größe); „Fenstergrößen zurücksetzen“ vergisst das Gemerkte des Benutzers.

Gemerkt wird in der eigenen Datendatei (Einstellungen fenster_geometrie, fenster_maximiert_vorgabe, sitzung_offen),
nicht im gemeinsamen Ordner und ohne Abgleich (fenster_* gilt je Arbeitsplatz). Meldungs-, Datei- und
Eingabefenster von Qt bleiben außen vor.
"""
import base64

from PySide6.QtCore import QByteArray, QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractScrollArea, QApplication, QDialog, QFileDialog, QInputDialog, QLayout,
                               QMainWindow, QMessageBox, QProgressDialog, QSplitter, QTabWidget, QWidget)

from .geister import losgeloest

GEOMETRIE = "fenster_geometrie"     # {"Kürzel|Fensterart": {"g": Geometrie, "t": [Teiler], "m": maximiert}} (base64)
VORGABE = "fenster_maximiert_vorgabe"   # Fenster mit Inhalt ohne gemerkten Stand maximiert öffnen (Vorgabe: ja)
INHALT_BREITE, INHALT_HOEHE = 560, 420  # ab dieser Größe (oder Wunschgröße) gilt ein Fenster mit Inhalt als groß
NIE_GROESSER = 16777215                 # QWIDGETSIZE_MAX
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


def feste_groesse(w):
    """Fenster mit fester Größe (gleiche Mindest- und Höchstgröße oder Layout SetFixedSize) lässt sich nicht ziehen."""
    lay = w.layout()
    return w.minimumSize() == w.maximumSize() or (lay is not None and lay.sizeConstraint() == QLayout.SetFixedSize)


def mit_inhalt(w):
    """Hat das Fenster Inhalt, für den mehr Platz hilft (Tabellen, Listen, Reiter, Teiler, Texte, Zeichnungen) und
    eine gewisse Größe? Kurze Rückfragen und Eingaben bleiben klein. Eigenschaft fenster_groesse entscheidet vorab."""
    wahl = w.property("fenster_groesse")
    if wahl in ("klein", "maximiert"):
        return wahl == "maximiert"
    if feste_groesse(w) or w.maximumWidth() < NIE_GROESSER or w.maximumHeight() < NIE_GROESSER:
        return False
    groesse = w.size().expandedTo(w.sizeHint())
    if groesse.width() < INHALT_BREITE and groesse.height() < INHALT_HOEHE:
        return False
    # nur eigene Teile zählen: die Auswahlliste einer Combobox ist ein eigenes (Popup-)Fenster
    return any(c.window() is w for t in (QAbstractScrollArea, QTabWidget, QSplitter) for c in w.findChildren(t))


def knoepfe_setzen(w):
    """Minimieren, Maximieren und Schließen in der Titelleiste (vor dem ersten Zeigen, sonst blendet Qt das Fenster
    beim Ändern der Flags aus). Fenster mit fester Größe bekommen nur Schließen. Ergebnis: True bei Änderung."""
    alt = w.windowFlags()
    neu = alt | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint | Qt.CustomizeWindowHint
    if not feste_groesse(w):
        neu |= Qt.WindowMinMaxButtonsHint
    # Hilfe-Knopf entfernen OHNE „& ~Qt.WindowContextHelpButtonHint“: unter Python 3.12 (Windows-Paket) liefert das
    # Umkehren eines Qt-Flags nur die Bits bis 0x01FFFFFF – Schließen-Knopf (0x08000000) und Customize gingen
    # verloren, das X war in jedem Dialog grau und ohne Funktion (Windows-Probe 28.11.2026).
    if neu & Qt.WindowContextHelpButtonHint:
        neu ^= Qt.WindowContextHelpButtonHint
    if neu == alt:
        return False
    w.setWindowFlags(neu)
    return True


class FensterMerker(QObject):
    """Ereignisfilter an der QApplication (zentrale Fensterverwaltung): vor dem ersten Zeigen Knöpfe der Titelleiste,
    beim ersten Zeigen Größe, Lage, maximiert und Teiler setzen, beim Schließen merken."""

    def __init__(self, db, parent=None, benutzer=None):
        super().__init__(parent)
        self.db = db
        self.gesetzt = set()        # id() der Fenster, die schon eingerichtet sind
        self._benutzer = benutzer   # Kürzel fest (Tests); sonst das angemeldete Kürzel

    def benutzer(self):
        if self._benutzer is not None:
            return self._benutzer
        try:
            from . import rollen
            return rollen.angemeldet(self.db) or ""
        except Exception:           # noqa: BLE001 – ohne Benutzerverwaltung (Tests, Probeordner): ohne Kürzel
            return ""

    def schluessel(self, w):
        return f"{self.benutzer()}|{art(w)}"

    def vorgabe_maximiert(self):
        try:
            return self.db.einstellung(VORGABE) is not False
        except Exception:           # noqa: BLE001 – Datendatei geschlossen o. Ä.: Vorgabe
            return True

    def _alle(self):
        try:
            d = self.db.einstellung(GEOMETRIE)
        except Exception:           # noqa: BLE001 – Datendatei geschlossen o. Ä.: nichts merken
            return {}
        return d if isinstance(d, dict) else {}

    @staticmethod
    def _passt(w):
        """Dialoge und eigene Fenster (z. B. Viewer), nicht das Hauptfenster, Popups, Werkzeugfenster und die
        Standarddialoge von Qt (Meldung, Datei, Eingabe, Fortschritt)."""
        if not isinstance(w, QWidget) or not w.isWindow() or isinstance(w, OHNE) or w.property("fenster_nicht_merken"):
            return False
        if losgeloest(w):           # Knopf/Haken ohne Fenster (noch nicht im Layout): kein Fenster (27.11.2026)
            return False
        if isinstance(w, QDialog):
            return True
        return w.windowType() == Qt.Window and not (isinstance(w, QMainWindow) and type(w).__name__ == "Hauptfenster")

    def eventFilter(self, w, e):
        t = e.type()
        if t == QEvent.Polish and self._passt(w) and not w.isVisible() and not w.property("_fenster_knoepfe"):
            w.setProperty("_fenster_knoepfe", True)
            knoepfe_setzen(w)
        elif t == QEvent.Show and self._passt(w) and id(w) not in self.gesetzt:
            self.gesetzt.add(id(w))
            if w.property("dialog_rahmen"):     # freigegebener Dialog-Rahmen (Variante B, 28.11.2026)
                from . import dialog_rahmen
                dialog_rahmen.anwenden(w)
            w.destroyed.connect(lambda *_a, i=id(w): self.gesetzt.discard(i))
            self.setzen(w)
        elif t in (QEvent.Hide, QEvent.Close) and self._passt(w) and id(w) in self.gesetzt:
            self.merken(w)
        elif t == QEvent.WindowStateChange and isinstance(w, QWidget) and w.isWindow():
            modal_mitnehmen(w)
        return False

    def eintrag(self, w):
        """Gemerkter Stand des Fensters für diesen Benutzer (ältere Einträge ohne Kürzel gelten weiter)."""
        alle = self._alle()
        return alle.get(self.schluessel(w)) or alle.get(art(w))

    def setzen(self, w):
        eintrag = self.eintrag(w)
        if not eintrag:
            if self.vorgabe_maximiert() and not w.isMaximized() and mit_inhalt(w):
                self.maximieren(w)
                return True
            return False
        if not w.isMaximized() and eintrag.get("g"):
            g = _bytes(eintrag["g"])
            if g is not None:
                w.restoreGeometry(g)
                self._auf_bildschirm(w)
        if eintrag.get("m") is True and not w.isMaximized():
            self.maximieren(w)
        elif eintrag.get("m") is False and w.isMaximized():     # zuletzt bewusst verkleinert (auch Editoren)
            w.setWindowState(w.windowState() & ~Qt.WindowMaximized)
            g = _bytes(eintrag.get("g") or "")
            if g is not None and eintrag.get("g"):
                w.restoreGeometry(g)
                self._auf_bildschirm(w)
        teiler = w.findChildren(QSplitter)
        for s, zustand in zip(teiler, eintrag.get("t") or []):
            z = _bytes(zustand)
            if z is not None:
                s.restoreState(z)
        return True

    @staticmethod
    def maximieren(w):
        w.setWindowState((w.windowState() & ~Qt.WindowMinimized) | Qt.WindowMaximized)

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
        schluessel = self.schluessel(w)
        alt = alle.get(schluessel) or alle.get(art(w)) or {}
        maximiert = w.isMaximized()
        # maximiert: die Größe davor bleibt gemerkt (Wiederherstellen kehrt dorthin zurück)
        eintrag = dict(g=alt.get("g") if maximiert else _b64(w.saveGeometry()),
                       t=[_b64(s.saveState()) for s in w.findChildren(QSplitter)], m=maximiert)
        if eintrag == alle.get(schluessel):
            return False
        alle[schluessel] = eintrag
        try:
            self.db.einstellung_setzen(GEOMETRIE, alle)
        except Exception:           # noqa: BLE001 – Lesemodus o. Ä.: Fenster einfach nicht merken
            return False
        return True

    def zuruecksetzen(self):
        """Alles Gemerkte des angemeldeten Benutzers vergessen (und alte Einträge ohne Kürzel). Ergebnis: Anzahl."""
        alle = self._alle()
        vorne = f"{self.benutzer()}|"
        weg = [k for k in alle if k.startswith(vorne) or "|" not in k]
        for k in weg:
            del alle[k]
        if weg and not getattr(self.db, "nur_lesen", False):
            self.db.einstellung_setzen(GEOMETRIE, alle)
        return len(weg)


ARTEN = (QEvent.Polish, QEvent.Show, QEvent.Hide, QEvent.Close, QEvent.WindowStateChange)


def _modal(w):
    return isinstance(w, QDialog) and w.isVisible() and (w.isModal() or w.windowModality() != Qt.NonModal)


def modal_mitnehmen(w):
    """Minimierter modaler Dialog sperrt sonst das sichtbare Hauptfenster (X und alles ohne Wirkung, Windows-Probe
    28.11.2026): Wird ein modaler Dialog minimiert, geht sein Fenster dahinter mit in die Taskleiste; wird dieses
    wiederhergestellt, kommt auch der Dialog wieder nach vorn."""
    if _modal(w) and w.isMinimized():
        eltern = w.parentWidget().window() if w.parentWidget() else None
        if eltern is not None and eltern.isVisible() and not eltern.isMinimized():
            QTimer.singleShot(0, eltern.showMinimized)
    elif not w.isMinimized():
        eltern = w.parentWidget().window() if _modal(w) and w.parentWidget() else None
        if eltern is not None and eltern.isMinimized():
            QTimer.singleShot(0, eltern.showNormal)
            QTimer.singleShot(0, w.raise_)
        for d in QApplication.topLevelWidgets():
            if d is not w and _modal(d) and d.isMinimized() and d.parentWidget() and d.parentWidget().window() is w:
                QTimer.singleShot(0, d.showNormal)
                QTimer.singleShot(0, d.raise_)


def menue_eintraege(f, menue):
    """Ansicht → „Fenster mit Inhalt maximiert öffnen“ (Haken, je Arbeitsplatz) und „Fenstergrößen zurücksetzen“."""
    menue.addSeparator()
    a = QAction("Fenster mit Inhalt maximiert öffnen", f)
    a.setCheckable(True)
    a.setChecked(f.db.einstellung(VORGABE) is not False)
    a.setToolTip("Fenster mit Tabellen, Listen oder Zeichnungen öffnen maximiert, solange keine Größe gemerkt ist; "
                 "kurze Rückfragen bleiben klein")

    def umschalten(an):
        if not getattr(f.db, "nur_lesen", False):
            f.db.einstellung_setzen(VORGABE, bool(an))
    a.toggled.connect(umschalten)
    menue.addAction(a)
    b = QAction("Fenstergrößen zurücksetzen", f)
    b.setToolTip("Gemerkte Größe und Lage aller Fenster für den angemeldeten Benutzer vergessen")

    def zuruecksetzen():
        m = getattr(f, "fenster_merker", None) or FensterMerker(f.db)
        n = m.zuruecksetzen()
        if hasattr(f, "meldung"):
            f.meldung(f"Fenstergrößen zurückgesetzt ({n} Fenster)." if n else "Keine Fenstergrößen gemerkt.")
    b.triggered.connect(zuruecksetzen)
    menue.addAction(b)
    f.fenster_vorgabe_aktion, f.fenster_zuruecksetzen_aktion = a, b
    return a, b


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
