"""Teilebaum im Reiter Schnittplan (Lantek-Idee L3, Patrick 24.10.2026 „Alle a“): je Abmessung die Positionen mit
Benötigt, Eingeplant und Offen und einem Status-Punkt (grün = alle eingeplant, rot = Teile fehlen, grau = kein
Rohrlaserteil, hohl = noch nicht optimiert). Darunter eine kleine 3D-Vorschau der gewählten Position (Netz aus dem
STEP-Import, ohne STEP das Modell aus den Eingaben des Teile-Editors). Die Auswahl hebt das Teil im Stangenbild hervor
(Signal gewaehlt), Doppelklick springt zur Position. Die Zahlen rechnet abmessung.teilebaum.
"""
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QHeaderView, QLabel, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from . import abmessung, stil
from .stammdaten import zahl_als_text

FARBEN = {abmessung.OK: stil.GRUEN, abmessung.FEHLT: stil.ROT, abmessung.KEIN: "#9AA3AF", abmessung.OFFEN: "#9AA3AF"}
TEXTE = {abmessung.OK: "alle Teile eingeplant", abmessung.FEHLT: "Teile fehlen im Schnittplan",
         abmessung.KEIN: "kein Rohrlaserteil (nicht im Schnittplan)", abmessung.OFFEN: "noch nicht optimiert"}
SPALTEN = ("Abmessung / Position", "Benötigt", "Eingeplant", "Offen")
_PUNKTE = {}


def punkt(status):
    """Status-Punkt als Symbol (hohl = noch nicht optimiert)."""
    if status not in _PUNKTE:
        bild = QPixmap(24, 24)
        bild.fill(Qt.transparent)
        p = QPainter(bild)
        p.setRenderHint(QPainter.Antialiasing, True)
        farbe = stil.farbe(FARBEN.get(status, "#9AA3AF"))
        if status == abmessung.OFFEN:
            p.setPen(QPen(farbe, 3))
            p.setBrush(Qt.NoBrush)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(farbe)
        p.drawEllipse(QRectF(5, 5, 14, 14))
        p.end()
        _PUNKTE[status] = QIcon(bild)
    return _PUNKTE[status]


def _z(w, stellen=0):
    return "" if w is None else zahl_als_text(w, stellen)


class TeileBaum(QWidget):
    """Teilebaum mit 3D-Vorschau. netz_von(zeile) -> (Netz oder None, Titel) liefert das Modell der Position;
    Signale gewaehlt(ref) und doppelklick(ref)."""
    gewaehlt = Signal(str)
    doppelklick = Signal(str)

    def __init__(self, netz_von=None):
        super().__init__()
        self.netz_von = netz_von
        self.daten, self.zeile_gewaehlt, self.ansicht = [], None, None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        self.info = QLabel()
        self.info.setWordWrap(True)
        lay.addWidget(self.info)
        self.teiler = QSplitter(Qt.Vertical)
        self.baum = QTreeWidget()
        self.baum.setColumnCount(len(SPALTEN))
        self.baum.setHeaderLabels(list(SPALTEN))
        self.baum.setRootIsDecorated(True)
        self.baum.setAlternatingRowColors(True)
        self.baum.setUniformRowHeights(True)
        self.baum.setToolTip("Klick: Teil im Stangenbild hervorheben und in 3D zeigen · Doppelklick: zur Position")
        self.baum.header().setStretchLastSection(False)
        self.baum.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.baum.header().setMinimumSectionSize(40)
        for c in (1, 2, 3):
            self.baum.setColumnWidth(c, max(58, self.baum.fontMetrics().horizontalAdvance(SPALTEN[c]) + 18))
        self.baum.currentItemChanged.connect(self._gewaehlt)
        self.baum.itemDoubleClicked.connect(self._doppelklick)
        self.teiler.addWidget(self.baum)
        self.vorschau = QWidget()
        vl = QVBoxLayout(self.vorschau)
        vl.setContentsMargins(0, 0, 0, 0)
        kopf = QHBoxLayout()
        self.k_3d = QCheckBox("3D-Vorschau")
        self.k_3d.setChecked(True)
        self.k_3d.setToolTip("3D-Modell der gewählten Position zeigen (STEP-Import oder Eingaben des Teile-Editors)")
        self.k_3d.toggled.connect(self._vorschau_zeigen)
        self.titel = QLabel()
        self.titel.setStyleSheet(f"color: {stil.TEXT_GRAU};")
        kopf.addWidget(self.k_3d)
        kopf.addWidget(self.titel, 1)
        vl.addLayout(kopf)
        self.platz = QVBoxLayout()
        vl.addLayout(self.platz, 1)
        self.teiler.addWidget(self.vorschau)
        self.teiler.setSizes([420, 260])
        lay.addWidget(self.teiler, 1)

    # ------------------------------------------------------------------ Daten
    def setzen(self, daten):
        """daten = abmessung.teilebaum(...); Auswahl (Position) bleibt, wenn es sie noch gibt."""
        self.daten = daten
        alt = self.zeile_gewaehlt
        self.baum.blockSignals(True)
        self.baum.clear()
        wahl = None
        for g in daten:
            kopf = QTreeWidgetItem([g["titel"], _z(g["benoetigt"]), _z(g["eingeplant"]) if g["status"] != abmessung.KEIN
                                    else "", _z(g["offen"]) if g["status"] != abmessung.KEIN else ""])
            kopf.setIcon(0, punkt(g["status"]))
            kopf.setToolTip(0, f"{g['titel']}\n{TEXTE[g['status']]}")
            f = kopf.font(0)
            f.setBold(True)
            for c in range(len(SPALTEN)):
                kopf.setFont(c, f)
            self.baum.addTopLevelItem(kopf)
            for x in g["positionen"]:
                text = f"Pos. {x['pos'] if x['pos'] is not None else '–'} · {x['artikel'] or ''}"
                if isinstance(x["laenge"], (int, float)):
                    text += f" · {zahl_als_text(x['laenge'], 1)} mm"
                it = QTreeWidgetItem([text, _z(x["benoetigt"]), _z(x["eingeplant"]), _z(x["offen"])])
                it.setIcon(0, punkt(x["status"]))
                it.setData(0, Qt.UserRole, x)
                tipp = [text, x.get("bezeichnung") or "", TEXTE[x["status"]]]
                if x.get("grund"):
                    tipp.append(f"Nicht eingeplant: {x['grund']}")
                it.setToolTip(0, "\n".join(t for t in tipp if t))
                if x["status"] == abmessung.FEHLT:
                    it.setForeground(3, stil.farbe(stil.ROT))
                for c in (1, 2, 3):
                    it.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
                kopf.addChild(it)
                if x["zeile"] == alt:
                    wahl = it
            for c in (1, 2, 3):
                kopf.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
            kopf.setExpanded(True)
        self.baum.blockSignals(False)
        n = sum(g["benoetigt"] for g in daten if g["status"] != abmessung.KEIN)
        e = sum(g["eingeplant"] for g in daten if g["status"] != abmessung.KEIN)
        offen = any(g["status"] == abmessung.OFFEN for g in daten)
        self.info.setText("Noch nicht optimiert." if offen else
                          f"<b>{_z(e)} von {_z(n)} Teilen eingeplant</b>" + (
                              f" · <span style='color:{stil.ROT}'>{_z(n - e)} offen</span>" if n > e else " · ✓ alle"))
        if wahl is not None:
            self.baum.setCurrentItem(wahl)
        else:
            self.zeile_gewaehlt = None
            self._vorschau(None)

    def position(self, item=None):
        it = item or self.baum.currentItem()
        return it.data(0, Qt.UserRole) if it is not None else None

    def waehlen(self, ref):
        """Position mit dem Bezug ref im Baum wählen (ohne Signal)."""
        for i in range(self.baum.topLevelItemCount()):
            kopf = self.baum.topLevelItem(i)
            for j in range(kopf.childCount()):
                it = kopf.child(j)
                if (it.data(0, Qt.UserRole) or {}).get("ref") == ref:
                    self.baum.blockSignals(True)
                    self.baum.setCurrentItem(it)
                    self.baum.blockSignals(False)
                    self.zeile_gewaehlt = it.data(0, Qt.UserRole)["zeile"]
                    self._vorschau(it.data(0, Qt.UserRole))
                    return True
        return False

    # ------------------------------------------------------------------ Bedienung
    def _gewaehlt(self, item, _=None):
        x = self.position(item)
        self.zeile_gewaehlt = x["zeile"] if x else None
        self._vorschau(x)
        if x:
            self.gewaehlt.emit(x["ref"])

    def _doppelklick(self, item, _spalte=0):
        x = self.position(item)
        if x:
            self.doppelklick.emit(x["ref"])

    def _vorschau_zeigen(self, an):
        if self.ansicht is not None:
            self.ansicht.setVisible(an)
        self._vorschau(self.position() if an else None)

    def _vorschau(self, x):
        """3D-Vorschau der Position x (nur, wenn eingeschaltet); die Ansicht entsteht erst beim ersten Bedarf."""
        if not self.k_3d.isChecked() or self.netz_von is None:
            self.titel.setText("")
            return
        if x is None:
            self.titel.setText("Position wählen")
            if self.ansicht is not None:
                self.ansicht.setzen(None)
            return
        netz, titel = self.netz_von(x["zeile"])
        if self.ansicht is None:
            from .ansicht3d import Ansicht3DMitKnoepfen
            self.ansicht = Ansicht3DMitKnoepfen()
            self.ansicht.setMinimumHeight(160)
            self.platz.addWidget(self.ansicht, 1)
        self.ansicht.setzen(netz, titel)
        self.titel.setText(titel if netz else "keine 3D-Daten (kein STEP, keine Eingaben)")
