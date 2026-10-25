"""Zuordnungsfenster für Rohrzeichnungen (Plan 3D-Editor 3E-15, Patrick 25.10.2026 „Alle a“, F6 a).

Erscheint nur, wenn der DXF-Import unsicher ist (dxf_rohr.erkennen: unsicher), sonst wird ohne Rückfrage übernommen:
Projektionsmethode nicht in der Zeichnung, mehrere Teile auf dem Blatt, Maßstab nur angenommen; im Rohr-Editor auch,
wenn keine Längsansicht zum Profil passt. Die Zeichnung ist mit den gefundenen Ansichten (Nummern) zu sehen; je Ansicht
wählt man die Rolle (Vorderansicht, Draufsicht, Schnitt, nicht verwenden), dazu Projektionsmethode, Drehung und Teil.
„Neu erkennen“ rechnet mit der Zuordnung neu. Die gewählte Projektionsmethode merkt sich das Programm je Zeichnungsstil
(Layernamen, dxf_rohr.fingerabdruck) in der Einstellung dxf_projektion.
"""
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QPainter, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QSpinBox,
                               QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import dxf_import as di, dxf_rohr, stil

ROLLEN = (("", "Automatisch"), ("vorne", "Vorderansicht"), ("oben", "Draufsicht"), ("schnitt", "Schnitt"),
          ("weg", "nicht verwenden"))
PROJEKTIONEN = ((None, "Automatisch"), (1, "Europa / DIN (Erstwinkel)"), (3, "USA (Drittwinkel)"))
DREHUNGEN = ((None, "Automatisch"), (0, "Rohr waagrecht (Ende A links)"), (90, "Rohr senkrecht (Ende A oben)"))
EINSTELLUNG = "dxf_projektion"


def gemerkt(db, text):
    """Gemerkte Projektionsmethode des Zeichnungsstils oder None."""
    try:
        return ((db.einstellung(EINSTELLUNG) if db else None) or {}).get(dxf_rohr.fingerabdruck(text))
    except (AttributeError, TypeError):
        return None


def merken(db, text, projektion):
    if not db or getattr(db, "nur_lesen", False) or projektion not in (1, 3):
        return
    alle = dict(db.einstellung(EINSTELLUNG) or {})
    alle[dxf_rohr.fingerabdruck(text)] = projektion
    db.einstellung_setzen(EINSTELLUNG, alle)


def rohr_erkennen(fenster, db, pfad, dialog=None, auch_fehler=False):
    """DXF lesen und als Rohrzeichnung erkennen; bei Unsicherheit das Zuordnungsfenster (auch_fehler: auch, wenn das
    Rohr nicht erkannt wurde, aber ein Schnitt oder Profiltext da ist). dialog(d) bedient das Fenster statt exec
    (Tests). Ergebnis von dxf_rohr.erkennen; abgebrochen=True, wenn das Fenster abgebrochen wurde. OSError und
    ValueError beim Lesen gehen an den Aufrufer."""
    text = di.datei_lesen(pfad)
    name = Path(pfad).name
    erg, vorgaben = dxf_rohr.erkennen(text, name), {}
    proj = gemerkt(db, text)
    if proj and erg.get("projektion_quelle") is None:      # Angabe in der Zeichnung geht vor
        vorgaben = dict(projektion=proj)
        erg = dxf_rohr.erkennen(text, name, vorgaben=vorgaben)
    if not ((erg["ok"] and erg["unsicher"]) or (auch_fehler and not erg["ok"] and erg["rohrartig"])):
        return erg
    d = DxfZuordnungDialog(fenster, text, name, erg, vorgaben)
    if (dialog(d) if dialog else d.exec()) != QDialog.Accepted or not d.erg["ok"]:
        return dict(d.erg, ok=False, abgebrochen=True)
    if d.vorgaben.get("projektion") in (1, 3):
        merken(db, text, d.vorgaben["projektion"])
    return d.erg


class Vorschau(QWidget):
    """Sichtbare Kanten der Zeichnung mit den Rahmen und Nummern der Ansichten (gewählte Ansicht blau)."""

    def __init__(self):
        super().__init__()
        self.linien, self.ansichten, self.markiert = [], [], None
        self.setMinimumSize(420, 300)

    def setzen(self, erg, markiert=None):
        self.linien, self.ansichten, self.markiert = erg.get("linien") or [], erg.get("ansichten") or [], markiert
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), stil.farbe("#FFFFFF"))
        # Ausschnitt: die gefundenen Ansichten (Linien außerhalb, z. B. vom Schriftfeld, sind nicht wichtig)
        xs = [a["bb"][i] for a in self.ansichten for i in (0, 2)] or [c for z in self.linien for c in (z[0], z[2])]
        ys = [a["bb"][i] for a in self.ansichten for i in (1, 3)] or [c for z in self.linien for c in (z[1], z[3])]
        if not xs:
            p.setPen(stil.farbe("#5F6B7A"))
            p.drawText(self.rect(), Qt.AlignCenter, "Keine sichtbaren Kanten in der Zeichnung.")
            return
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        rand = 34
        m = min((self.width() - 2 * rand) / max(x1 - x0, 1e-6), (self.height() - 2 * rand) / max(y1 - y0, 1e-6))

        ox = (self.width() - (x1 - x0) * m) / 2           # mittig
        oy = (self.height() - (y1 - y0) * m) / 2

        def pkt(x, y):
            return QPointF(ox + (x - x0) * m, self.height() - oy - (y - y0) * m)
        p.setPen(QPen(stil.farbe("#1F2933"), 1.0))
        for z in self.linien:
            p.drawLine(pkt(z[0], z[1]), pkt(z[2], z[3]))
        p.setFont(QFont(self.font().family(), 9, QFont.Bold))
        for a in self.ansichten:
            blau = a["nr"] == self.markiert
            farbe = stil.farbe("#1D4ED8" if blau else "#B26A00" if a["rolle"] == "nicht verwendet" else "#2E7D32")
            p.setPen(QPen(farbe, 2.0 if blau else 1.2, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            b = a["bb"]
            r = QRectF(pkt(b[0], b[3]), pkt(b[2], b[1])).adjusted(-4, -4, 4, 4)
            p.drawRect(r)
            p.drawText(r.topLeft() + QPointF(2, -3), f"{a['nr'] + 1}  {a['rolle']}")


class DxfZuordnungDialog(QDialog):
    """Zuordnung der Ansichten einer Rohrzeichnung. Nach OK: self.erg (neu erkannt) und self.vorgaben."""

    def __init__(self, parent, text, dateiname, erg, vorgaben=None):
        super().__init__(parent)
        self.text, self.dateiname, self.erg = text, dateiname, erg
        self.vorgaben = dict(vorgaben or {})
        self.setWindowTitle(f"DXF-Zeichnung zuordnen – {dateiname}")
        lay = QVBoxLayout(self)
        self.grund = QLabel()
        self.grund.setWordWrap(True)
        self.grund.setStyleSheet("color: #B26A00")
        lay.addWidget(self.grund)
        teiler = QSplitter(Qt.Horizontal)
        lay.addWidget(teiler, 1)
        self.vorschau = Vorschau()
        teiler.addWidget(self.vorschau)
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(6, 0, 0, 0)
        self.tabelle = QTableWidget(0, 4)
        self.tabelle.setHorizontalHeaderLabels(["Nr.", "Größe gezeichnet", "Maßstab", "Rolle"])
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.currentCellChanged.connect(lambda r, *_: self._markieren(r))
        rl.addWidget(self.tabelle, 1)
        zeile = QHBoxLayout()
        self.projektion = QComboBox()
        for _w, t in PROJEKTIONEN:
            self.projektion.addItem(t)
        self.projektion.setToolTip("Europa/DIN: Draufsicht unter der Vorderansicht; USA: Draufsicht darüber")
        self.drehung = QComboBox()
        for _w, t in DREHUNGEN:
            self.drehung.addItem(t)
        self.teil = QSpinBox()
        self.teil.setRange(1, 1)
        self.teil.setToolTip("Mehrere Teile auf dem Blatt: welches Teil übernommen wird (1 = das längste)")
        for titel, w in (("Projektion", self.projektion), ("Lage", self.drehung), ("Teil", self.teil)):
            zeile.addWidget(QLabel(titel))
            zeile.addWidget(w)
        rl.addLayout(zeile)
        self.neu_knopf = QPushButton("Neu erkennen")
        self.neu_knopf.setToolTip("Mit der Zuordnung oben neu rechnen")
        self.neu_knopf.clicked.connect(self.neu_erkennen)
        rl.addWidget(self.neu_knopf)
        self.bericht = QLabel()
        self.bericht.setWordWrap(True)
        rl.addWidget(self.bericht)
        teiler.addWidget(rechts)
        teiler.setSizes([620, 420])
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.button(QDialogButtonBox.Ok).setText("Übernehmen")
        self.knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        self.knoepfe.accepted.connect(self.accept)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)
        self.resize(1100, 650)
        self._felder_setzen()
        self._zeigen()

    # ------------------------------------------------------------------ Felder
    def _felder_setzen(self):
        v = self.vorgaben
        self.projektion.setCurrentIndex(next((i for i, (w, _t) in enumerate(PROJEKTIONEN) if w == v.get("projektion")),
                                             0))
        self.drehung.setCurrentIndex(next((i for i, (w, _t) in enumerate(DREHUNGEN) if w == v.get("drehung")), 0))

    def rolle_setzen(self, nr, rolle):
        """Rolle der Ansicht nr ('', 'vorne', 'oben', 'schnitt', 'weg'); für Tests und die Tabelle."""
        box = self.tabelle.cellWidget(nr, 3)
        box.setCurrentIndex(next(i for i, (w, _t) in enumerate(ROLLEN) if w == rolle))

    def _zeigen(self):
        e = self.erg
        gruende = list(e.get("unsicher") or ()) or ([] if e["ok"] else list(e.get("warnungen") or ()))
        self.grund.setText("Bitte prüfen: " + " ".join(gruende) if gruende else
                           "Zuordnung gefunden, bitte prüfen und übernehmen.")
        self.tabelle.setRowCount(0)
        rollen = {int(k): r for k, r in (self.vorgaben.get("rollen") or {}).items()}
        for a in e.get("ansichten") or ():
            i = self.tabelle.rowCount()
            self.tabelle.insertRow(i)
            b = a["bb"]
            for c, t in enumerate((str(a["nr"] + 1), f"{b[2] - b[0]:.1f} × {b[3] - b[1]:.1f}",
                                   dxf_rohr._massstab_text(a["massstab"]) if a.get("massstab") else "")):
                it = QTableWidgetItem(t)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                self.tabelle.setItem(i, c, it)
            box = QComboBox()
            for w, t in ROLLEN:
                box.addItem(t if w else f"Automatisch ({a['rolle']})")
            box.setCurrentIndex(next((k for k, (w, _t) in enumerate(ROLLEN) if w == rollen.get(a["nr"])), 0))
            self.tabelle.setCellWidget(i, 3, box)
        self.tabelle.resizeColumnsToContents()
        self.teil.setRange(1, max(1, int(e.get("teile") or 1)))
        self.teil.setValue(int(self.vorgaben.get("teil") or 0) + 1)
        self.teil.setEnabled((e.get("teile") or 1) > 1)
        if e["ok"]:
            self.bericht.setText("<br>".join(dxf_rohr.bericht(e)))
        else:
            self.bericht.setText("<span style='color:#B42318'>Kein Rohr erkannt: " + " ".join(e["warnungen"]) +
                                 "</span>")
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(bool(e["ok"]))
        self.vorschau.setzen(e)

    def _markieren(self, r):
        self.vorschau.setzen(self.erg, r if r >= 0 else None)

    # ------------------------------------------------------------------ Rechnen
    def vorgaben_lesen(self):
        rollen = {}
        for i in range(self.tabelle.rowCount()):
            w = ROLLEN[self.tabelle.cellWidget(i, 3).currentIndex()][0]
            if w:
                rollen[i] = w
        drehung = DREHUNGEN[self.drehung.currentIndex()][0]
        v = dict(projektion=PROJEKTIONEN[self.projektion.currentIndex()][0], teil=self.teil.value() - 1,
                 teil_gewaehlt=True)
        if drehung is None and rollen:
            drehung = self.erg.get("drehung") or 0      # Nummern gelten für die Lage, in der sie gezeigt sind
        elif drehung != (self.erg.get("drehung") or 0):
            rollen = {}             # andere Lage: Ansichten neu nummeriert
        v.update(drehung=drehung, rollen=rollen)
        return {k: x for k, x in v.items() if x is not None and x != {}}

    def neu_erkennen(self):
        self.vorgaben = self.vorgaben_lesen()
        try:
            self.erg = dxf_rohr.erkennen(self.text, self.dateiname, vorgaben=self.vorgaben)
        except (ValueError, KeyError, TypeError, ZeroDivisionError) as x:
            self.erg = dict(self.erg, ok=False, warnungen=[str(x)])
        self._zeigen()

    def accept(self):
        if self.vorgaben_lesen() != self.vorgaben:
            self.neu_erkennen()
        if self.erg["ok"]:
            super().accept()
