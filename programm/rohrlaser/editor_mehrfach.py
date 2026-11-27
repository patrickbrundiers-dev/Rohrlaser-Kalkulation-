"""Mehrere Konturen gemeinsam bearbeiten (Plan 3D-Editor modernisieren 19.11.2026, A10 und A11).

Sind im Teile-Editor zwei oder mehr Konturzeilen markiert (Strg/Umschalt+Klick in der Tabelle oder im Merkmalsbaum),
zeigt die rechte Seite statt der Eigenschaften einer Kontur diese Tafel:
- gemeinsame Felder: Maße (nur bei gleicher Konturart), Anzahl, beim Rohr Seite; leer = nicht ändern;
- Lage verschieben um Δ (Rohr längs, Blech x/y);
- Duplizieren, Spiegeln (Rohr, zur Teilmitte) und Entfernen für alle markierten; „Weitere“ = Menü Bearbeiten
  (editor_konturwerkzeuge: drehen, Offset, verlängern, umkehren, Reihe, gleiche wählen);
- A11: bei genau zwei Konturen der Abstand längs Mitte–Mitte und Kante–Kante (lichter Abstand, aus den Umrissen).

Alles wird in die Tabelle der Fenster geschrieben (wie von Hand), die Rechnung bleibt im Schneidweg-Rechner bzw.
Blech-Editor. Jede Aktion der Tafel ist genau ein Schritt für Rückgängig.
"""
import copy

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from . import rechnen, stil
from . import schneidweg as sw
from .editor_eigenschaften import BLECH_SPALTEN, ROHR_SPALTEN
from . import geister  # noqa: E402

NICHT_AENDERN = "(nicht ändern)"


def _zahl(text):
    try:
        return float(str(text).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def abstand_laengs(rahmen, r1, r2):
    """Rohr: (Mitte–Mitte, Kante–Kante) längs der Rohrachse zwischen den nächsten Konturen der Zeilen r1 und r2 [mm]
    oder None. Kante–Kante aus der Ausdehnung des Umrisses längs (skizze.laenge_x); < 0 = überlappen."""
    from . import skizze as sk
    d = rahmen.d
    try:
        e = d.eingaben()
        lagen = sk.lagen(e.get("konturen") or [], rahmen.teil_laenge(), getattr(d, "qs", None))
    except (ValueError, TypeError, ZeroDivisionError, AttributeError):
        return None
    a = [x for x in lagen if x["zeile"] == r1 and not x.get("kopie")]
    b = [x for x in lagen if x["zeile"] == r2 and not x.get("kopie")]
    if not a or not b:
        return None
    beste = None
    for p in a:
        for q in b:
            mm = abs(q["x"] - p["x"])
            try:
                lp, lq = sk.laenge_x(p["eingabe"]), sk.laenge_x(q["eingabe"])
            except (ValueError, TypeError, ZeroDivisionError):
                lp = lq = 0.0
            kk = mm - (lp + lq) / 2
            if beste is None or mm < beste[0]:
                beste = (mm, kk)
    return beste


class MehrfachTafel(QWidget):
    """Tafel für mehrere markierte Konturzeilen; zeigen(zeilen) füllt sie neu."""

    def __init__(self, rahmen, parent=None):
        super().__init__(parent)
        self.r = rahmen
        self.zeilen = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 4, 6, 4)
        self.titel = QLabel()
        self.titel.setStyleSheet("font-weight: bold;")
        lay.addWidget(self.titel)
        hinweis = QLabel("Leere Felder bleiben, wie sie sind. Jede Änderung gilt für alle markierten Konturen und ist "
                         "ein Schritt für Rückgängig.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {stil.umsetzen(stil.TEXT_GRAU)};")
        lay.addWidget(hinweis)
        self.form = QFormLayout()
        lay.addLayout(self.form)
        self.abstand = QLabel()
        self.abstand.setWordWrap(True)
        self.abstand.setToolTip("Abstand längs der Rohrachse zwischen den beiden Konturen (nächste Konturen eines "
                                "Musters): Mitte–Mitte und lichter Abstand Kante–Kante")
        lay.addWidget(self.abstand)
        knoepfe = QHBoxLayout()
        self.duplizieren_knopf = QPushButton("Duplizieren")
        self.duplizieren_knopf.setToolTip("Alle markierten Konturen kopieren (Strg+D)")
        self.duplizieren_knopf.clicked.connect(self.duplizieren)
        self.spiegeln_knopf = QPushButton("Spiegeln")
        self.spiegeln_knopf.setToolTip("Alle markierten Konturen zur Teilmitte spiegeln")
        self.spiegeln_knopf.clicked.connect(self.spiegeln)
        self.entfernen_knopf = QPushButton("Entfernen")
        self.entfernen_knopf.setToolTip("Alle markierten Konturen entfernen (Entf)")
        self.entfernen_knopf.clicked.connect(self.entfernen)
        from . import editor_konturwerkzeuge
        self.mehr_knopf = QPushButton("Weitere")
        self.mehr_knopf.setToolTip(editor_konturwerkzeuge.TIPP)
        self.mehr_knopf.setMenu(editor_konturwerkzeuge.menue(rahmen, self))
        for k in (self.duplizieren_knopf, self.spiegeln_knopf, self.entfernen_knopf, self.mehr_knopf):
            knoepfe.addWidget(k)
        geister.sichtbar(self.spiegeln_knopf, rahmen.art == "rohr")     # nie eigenes Fenster (27.11.2026)
        lay.addLayout(knoepfe)
        lay.addStretch(1)
        self.felder = {}

    # ---- Aufbau
    def _feld(self, titel, tipp, uebernehmen):
        f = QLineEdit()
        f.setPlaceholderText(NICHT_AENDERN)
        f.setToolTip(tipp)
        f.returnPressed.connect(lambda: self._feld_fertig(f, uebernehmen))
        f.editingFinished.connect(lambda: self._feld_fertig(f, uebernehmen))
        self.form.addRow(titel, f)
        self.felder[titel] = f
        return f

    def _feld_fertig(self, f, uebernehmen):
        text = f.text().strip()
        if not text:
            return
        f.blockSignals(True)
        f.clear()
        f.blockSignals(False)
        self._schritt(lambda: uebernehmen(text))

    def zeigen(self, zeilen):
        self.zeilen = sorted(zeilen)
        while self.form.rowCount():
            self.form.removeRow(0)
        self.felder = {}
        t = self.r.d.tabelle
        arten = {t.cellWidget(z, 0).currentText() for z in self.zeilen if t.cellWidget(z, 0) is not None}
        self.titel.setText(f"{len(self.zeilen)} Konturen markiert" + (f" ({next(iter(arten))})" if len(arten) == 1
                                                                      else ""))
        if len(arten) == 1:
            art = next(iter(arten))
            for i, (k, titel) in enumerate(sw.MASSE.get(art, ())):
                if k == "punkte":
                    continue
                spalte = 2 + i
                self._feld(titel.split(" (")[0], f"Neuer Wert für alle markierten {art}",
                           lambda text, s=spalte: self._zellen(s, text))
        spalten = ROHR_SPALTEN if self.r.art == "rohr" else BLECH_SPALTEN
        self._feld("Anzahl", "Neue Anzahl für alle markierten Konturen",
                   lambda text: self._zellen(spalten["anzahl"], text))
        if self.r.art == "rohr":
            self._feld("Lage verschieben um", "Alle markierten Konturen längs verschieben (+ zu Ende B), in mm",
                       lambda text: self._verschieben(spalten["lage"], text))
            seiten = QComboBox()
            seiten.setToolTip("Seite für alle markierten Konturen")
            vorlage = t.cellWidget(self.zeilen[0], spalten["seite"]) if self.zeilen else None
            seiten.addItem(NICHT_AENDERN)
            if isinstance(vorlage, QComboBox):
                seiten.addItems([vorlage.itemText(i) for i in range(vorlage.count())])
            seiten.activated.connect(lambda _i: seiten.currentIndex() > 0 and self._schritt(
                lambda: self._seite(spalten["seite"], seiten.currentText())))
            self.form.addRow("Seite", seiten)
            self.seiten = seiten
        else:
            self._feld("x verschieben um", "Alle markierten Konturen in x verschieben, in mm",
                       lambda text: self._verschieben(spalten["x"], text))
            self._feld("y verschieben um", "Alle markierten Konturen in y verschieben, in mm",
                       lambda text: self._verschieben(spalten["y"], text))
        self.abstand.setVisible(False)
        if self.r.art == "rohr" and len(self.zeilen) == 2:
            werte = abstand_laengs(self.r, *self.zeilen)
            if werte is not None:
                mm, kk = werte
                self.abstand.setText(f"<b>Abstand längs</b>: Mitte–Mitte {rechnen.zahl(mm, 1)} mm · Kante–Kante "
                                     f"{rechnen.zahl(kk, 1)} mm" + (" (überlappen)" if kk < 0 else ""))
                self.abstand.setVisible(True)

    # ---- Schreiben (ein Schritt für Rückgängig)
    def _schritt(self, tun):
        r = self.r
        r.aktualisieren()               # offene Eingaben vorher als eigener Schritt
        r._still = True
        try:
            tun()
        finally:
            r._still = False
        r.zeitgeber.stop()
        r.aktualisieren()
        self._markieren([z for z in self.zeilen if z < r.d.tabelle.rowCount()])
        # neu aufbauen erst nach dem Signal, das gerade läuft (das Feld darf in seinem eigenen Signal nicht weg)
        QTimer.singleShot(0, lambda: self.isVisible() and len(self.zeilen) > 1 and self.zeigen(self.zeilen))

    def _dazu(self, z):
        from PySide6.QtCore import QItemSelectionModel
        t = self.r.d.tabelle
        t.selectionModel().select(t.model().index(z, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def _zellen(self, spalte, text):
        wert = rechnen.zahl(_zahl(text), 3) if _zahl(text) is not None else None
        if wert is None:
            return
        t = self.r.d.tabelle
        for z in self.zeilen:
            it = t.item(z, spalte)
            if it is not None:
                it.setText(wert)
        self.r.d.rechnen()

    def _verschieben(self, spalte, text):
        delta = _zahl(text)
        if not delta:
            return
        t = self.r.d.tabelle
        for z in self.zeilen:
            it = t.item(z, spalte)
            alt = _zahl(it.text()) if it is not None else None
            if alt is not None:
                it.setText(rechnen.zahl(alt + delta, 3))
        self.r.d.rechnen()

    def _seite(self, spalte, text):
        t = self.r.d.tabelle
        for z in self.zeilen:
            cb = t.cellWidget(z, spalte)
            if isinstance(cb, QComboBox) and cb.findText(text) >= 0:
                cb.setCurrentText(text)
        self.r.d.rechnen()

    def duplizieren(self):
        r, d = self.r, self.r.d
        konturen = d.eingaben().get("konturen") or []
        neu = []

        def tun():
            for z in self.zeilen:
                if 0 <= z < len(konturen):
                    k = {s: v for s, v in copy.deepcopy(konturen[z]).items() if s not in ("gemessen", "huelle_gemessen")}
                    (d.zeile_neu if r.art == "rohr" else d.kontur_neu)(k)
                    neu.append(d.tabelle.rowCount() - 1)
            d.rechnen()
        self._schritt(tun)
        self.zeilen = neu
        self._markieren(neu)

    def spiegeln(self):
        if self.r.art != "rohr":
            return
        from . import editor_griffe
        r, d = self.r, self.r.d

        def tun():
            for z in self.zeilen:
                e = d.eingaben()["konturen"][z]
                neu = editor_griffe.gespiegelt(e, r.werkzeug.lagen(z), r.teil_laenge())
                if neu:
                    d._verschoben(z, neu)
        self._schritt(tun)

    def entfernen(self):
        r, d = self.r, self.r.d

        def tun():
            d.tabelle.blockSignals(True)        # Zwischenstände ohne Auswahl-Signale (Zeile halb entfernt)
            try:
                d.tabelle.clearSelection()
                for z in sorted(self.zeilen, reverse=True):
                    if 0 <= z < d.tabelle.rowCount():
                        d.tabelle.removeRow(z)
            finally:
                d.tabelle.blockSignals(False)
            r.gewaehlt = None
            d.rechnen()
        self._schritt(tun)
        self.zeilen = []
        self.r.eigenschaften.zeigen(None)
        self.hide()
        self.r.eigenschaften.show()

    def _markieren(self, zeilen):
        t = self.r.d.tabelle
        t.clearSelection()
        for z in zeilen:
            self._dazu(z)
