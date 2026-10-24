"""Tabellen-Eingabe wie in Excel (Plan Arbeitsabläufe W5), zuerst in der Positionsliste.

- Eingabe springt eine Zelle weiter, nach unten oder nach rechts (Einstellung 'eingabe_richtung'), auch direkt
  nach dem Bearbeiten einer Zelle.
- In der letzten Zeile legen Pfeil ↓ und Eingabe (Richtung unten) eine neue Zeile an.
- Strg+D übernimmt den Wert der Zeile darüber; sind mehrere Zeilen markiert, füllt die oberste die übrigen.
- Profil-Felder vervollständigen beim Tippen: „40x3“ findet „QR 40x40x3“ (gleiche Maße doppelt geschrieben
  dürfen fehlen), „qr 40“ alle QR-Profile ab 40. Wird die Eingabe ohne Auswahl bestätigt, gilt der beste Treffer.
"""
import re

from PySide6.QtCore import QObject, QEvent, QStringListModel, Qt, QTimer
from PySide6.QtWidgets import QAbstractItemDelegate, QAbstractItemView, QCompleter

from . import tastatur
from .stammdaten import EINGABE_RICHTUNGEN

UNTEN, RECHTS = EINGABE_RICHTUNGEN
TREFFER_HOECHSTENS = 30


# ------------------------------------------------------------------ Profil vervollständigen
def _kurz(text):
    return str(text or "").lower().replace(" ", "").replace("*", "x").replace("×", "x").replace(",", ".")


def _zahlen(kurz):
    return [float(z) for z in re.findall(r"\d+(?:\.\d+)?", kurz)]


def _ohne_doppelte(nz):
    """Maße ohne direkt wiederholte (40x40x3 -> 40x3)"""
    return [x for i, x in enumerate(nz) if i == 0 or x != nz[i - 1]]


def profil_treffer(text, namen, hoechstens=TREFFER_HOECHSTENS):
    """Profilnamen zur Eingabe, beste zuerst: gleiche Maße (doppelte Maße dürfen fehlen: 40x3 = 40x40x3), dann Maße
    am Anfang (40 → 40x40x3, 40x60x4 …), dann Text irgendwo im Namen. Buchstaben am Anfang der Eingabe (QR, RE …)
    müssen am Anfang des Namens stehen."""
    t = _kurz(text)
    if not t:
        return []
    m = re.match(r"[a-zäöü]+", t)
    vorne = m.group(0) if m else ""
    z = _zahlen(t)
    gleich, anfang, sonst = [], [], []
    for n in namen:
        k = _kurz(n)
        if vorne and not k.startswith(vorne):
            continue
        nz = _zahlen(k)
        ohne_doppelte = _ohne_doppelte(nz)
        if z and z in (nz, ohne_doppelte):
            gleich.append(n)
        elif z and (nz[:len(z)] == z or ohne_doppelte[:len(z)] == z):
            anfang.append(n)
        elif t in k or (not z and vorne):
            sonst.append(n)
    return (gleich + anfang + sonst)[:hoechstens]


def profil_aufloesen(text, namen):
    """Bestätigte Eingabe im Profil-Feld: genauer Name (Groß-/Kleinschreibung egal), sonst der beste Treffer mit
    gleichen Maßen bzw. der einzige Treffer überhaupt, sonst die Eingabe unverändert (die Prüfung meldet sie)."""
    t = str(text or "").strip()
    genau = next((n for n in namen if n.lower() == t.lower()), None)
    if genau or not t:
        return genau or t
    treffer = profil_treffer(t, namen)
    z = _zahlen(_kurz(t))
    if treffer and z:
        nz = _zahlen(_kurz(treffer[0]))
        if z in (nz, _ohne_doppelte(nz)):
            return treffer[0]
    return treffer[0] if len(treffer) == 1 else t


def profil_vervollstaendigen(cb):
    """Auswahlfeld (QComboBox, bearbeitbar) eines Profils: Liste der Treffer beim Tippen; die Namen merkt sich das
    Feld für profil_aufloesen (Eigenschaft 'profil_namen')."""
    namen = [cb.itemText(i) for i in range(cb.count())
             if cb.itemText(i) and not cb.itemText(i).startswith("— ")]
    modell = QStringListModel(cb)
    c = QCompleter(modell, cb)
    c.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
    c.setCaseSensitivity(Qt.CaseInsensitive)
    cb.setCompleter(c)
    cb.setProperty("profil_namen", namen)

    def tippen(text):
        modell.setStringList(profil_treffer(text, namen))
        if text and modell.rowCount():
            c.complete()
    if cb.lineEdit() is not None:
        cb.lineEdit().textEdited.connect(tippen)
    return c


# ------------------------------------------------------------------ Eingabe, ↓, Strg+D
def von_oben(ansicht):
    """Strg+D: markierte Zellen mit dem Wert der Zeile darüber füllen (je Spalte; mehrere markierte Zeilen: die
    oberste füllt die übrigen). Ergebnis: Anzahl geänderter Zellen."""
    je_spalte = {}
    for i in tastatur._bereich(ansicht):
        je_spalte.setdefault(i.column(), set()).add(i.row())
    modell, ziele = ansicht.model(), []
    for c, zeilen in je_spalte.items():
        zeilen = sorted(zeilen)
        if len(zeilen) > 1:
            quelle, rest = zeilen[0], zeilen[1:]
        else:
            quelle = next((r for r in range(zeilen[0] - 1, -1, -1) if not ansicht.isRowHidden(r)), None)
            rest = zeilen
        if quelle is None:
            continue
        wert = modell.index(quelle, c).data(Qt.DisplayRole)
        ziele += [(r, c, "" if wert is None else str(wert)) for r in rest]
    return tastatur._schreiben(ansicht, ziele)


class ExcelEingabe(QObject):
    """Eingabe/↓/Strg+D für eine Tabelle. richtung(): UNTEN oder RECHTS; neue_zeile(): legt eine Zeile an und liefert
    True (None/False = keine neue Zeile, z. B. im Lesemodus); fuellen(): Strg+D (Vorgabe von_oben, die Positionsliste
    fasst die Zellen zu einem Schritt für Rückgängig zusammen)."""

    def __init__(self, ansicht, richtung, neue_zeile=None, fuellen=None):
        super().__init__(ansicht)
        self.ansicht, self.richtung, self.neue_zeile = ansicht, richtung, neue_zeile
        self.fuellen = fuellen or (lambda: von_oben(ansicht))
        self.zuletzt = None              # (Zeile, Spalte) der letzten gültigen Zelle; Neuladen setzt sie zurück
        ansicht.installEventFilter(self)
        ansicht.selectionModel().currentChanged.connect(self._merken)
        ansicht.itemDelegate().closeEditor.connect(self._editor_zu)

    def _merken(self, jetzt, _vorher):
        if jetzt.isValid():
            self.zuletzt = (jetzt.row(), jetzt.column())

    def _editor_zu(self, _editor, hinweis):
        if hinweis == QAbstractItemDelegate.SubmitModelCache and self.zuletzt:   # mit Eingabe bestätigt
            r, c = self.zuletzt
            QTimer.singleShot(0, lambda: self.weiter(r, c))

    def eventFilter(self, objekt, ereignis):
        if objekt is not self.ansicht or ereignis.type() != QEvent.KeyPress \
                or self.ansicht.state() == QAbstractItemView.EditingState:
            return False
        if ereignis.key() == Qt.Key_D and ereignis.modifiers() == Qt.ControlModifier:
            self.fuellen()
            return True
        if ereignis.modifiers() in (Qt.NoModifier, Qt.KeypadModifier):
            i = self.ansicht.currentIndex()
            if i.isValid() and ereignis.key() in (Qt.Key_Return, Qt.Key_Enter):
                self.weiter(i.row(), i.column())
                return True
            if i.isValid() and ereignis.key() == Qt.Key_Down and self._letzte(i.row()):
                self._neue_zeile(i.column())
                return True
        return False

    def _sichtbare_zeilen(self):
        return [r for r in range(self.ansicht.model().rowCount()) if not self.ansicht.isRowHidden(r)]

    def _letzte(self, r):
        zeilen = self._sichtbare_zeilen()
        return bool(zeilen) and r >= zeilen[-1]

    def _spalten(self, r):
        """Sichtbare, bearbeitbare Spalten der Zeile in der angezeigten Reihenfolge."""
        kopf = self.ansicht.horizontalHeader()
        spalten = [kopf.logicalIndex(v) for v in range(kopf.count())]
        return [c for c in spalten if not self.ansicht.isColumnHidden(c) and tastatur._editierbar(self.ansicht, r, c)]

    def _setzen(self, r, c):
        i = self.ansicht.model().index(r, c)
        if i.isValid():
            self.ansicht.setCurrentIndex(i)
            self.ansicht.scrollTo(i)

    def weiter(self, r, c):
        """Nächste Zelle nach (r, c): unten bzw. rechts (am Zeilenende: erste Spalte der nächsten Zeile); nach der
        letzten Zeile eine neue Zeile."""
        zeilen = [z for z in self._sichtbare_zeilen() if z > r]
        if self.richtung() == RECHTS:
            kopf = self.ansicht.horizontalHeader()
            rechts = [x for x in self._spalten(r) if kopf.visualIndex(x) > kopf.visualIndex(c)]
            if rechts:
                return self._setzen(r, rechts[0])
            if zeilen:
                spalten = self._spalten(zeilen[0])
                return self._setzen(zeilen[0], spalten[0] if spalten else c)
            return self._neue_zeile(None)
        if zeilen:
            return self._setzen(zeilen[0], c)
        return self._neue_zeile(c)

    def _neue_zeile(self, c):
        if self.neue_zeile is None or not self.neue_zeile():
            return None
        zeilen = self._sichtbare_zeilen()
        if not zeilen:
            return None
        r = zeilen[-1]
        if c is None:
            spalten = self._spalten(r)
            c = spalten[0] if spalten else 0
        self._setzen(r, c)
        self.ansicht.setFocus()
        return r
