"""Fenster 'Material …' im Angebot (Patrick 22.10.2026: "€/m je Abmessung über einen Button ändern", "Fenster mit
dem Materialeinsatz je Abmessung", "alles zum Material, was man einstellen kann"): je Abmessung eine Zeile mit
Querschnitt, Materialeinsatz aus dem Schnittplan und den Materialwerten zum Ändern.

Alle Werte werden wie in den Spalten der Positionen gespeichert, und zwar an allen Positionen der Abmessung: Oberfläche,
Stangenlänge abweichend (Lieferlänge), Material (Eigen-/Kundenmaterial) und Materialpreis [€/m] (preis_m, leer =
wieder berechnet aus Lieferlängen, Preisen bzw. Tonnenpreis mit Aufpreis der Oberfläche).
"""
from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHeaderView,
                               QLabel, QLineEdit, QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import hilfe, querschnitt, rechnen
from .stammdaten import EIGENMATERIAL, KUNDENMATERIAL, MATERIAL_HERKUNFT, ROH, zahl_als_text, zahl_aus_text

GRAU = "#5F6B7A"
SPALTEN = ("", "Abmessung", "Werkstoff", "Oberfläche", "Lieferlänge [mm]", "Material", "Pos.", "Stangen", "Meter",
           "Gewicht [kg]", "Material [€]", "berechnet [€/m]", "Meterpreis [€/m]")
BILD = 44


def _z(w, stellen=2):
    return "" if w is None else zahl_als_text(w, stellen)


def querschnitt_pixmap(profil, groesse=BILD, farbe="#1F4E78"):
    """Querschnitt des Profils (querschnitt.kontur) als Bild groesse × groesse; leer bei unbekannter Form."""
    bild = QPixmap(groesse, groesse)
    bild.fill(Qt.transparent)
    q = querschnitt.kontur(profil)
    if not q:
        return bild
    f, dx, dy = querschnitt.einpassen(q, groesse, groesse, rand=3)
    p = QPainter(bild)
    p.setRenderHint(QPainter.Antialiasing)

    def punkt(x, y):
        return QPointF(dx + x * f, groesse - dy - y * f)
    if q["flaechen"]:
        pfad = QPainterPath()
        pfad.setFillRule(Qt.OddEvenFill)
        for poly in q["flaechen"]:
            pfad.moveTo(punkt(*poly[0]))
            for x in poly[1:]:
                pfad.lineTo(punkt(*x))
            pfad.closeSubpath()
        p.setPen(QPen(QColor(farbe), 1))
        p.setBrush(QColor("#BDD7EE"))
        p.drawPath(pfad)
    if q["linien"]:
        pfad = QPainterPath()
        for zug in q["linien"]:
            pfad.moveTo(punkt(*zug[0]))
            for x in zug[1:]:
                pfad.lineTo(punkt(*x))
        p.setPen(QPen(QColor(farbe), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(pfad)
    p.end()
    return bild


def laengen_text(g):
    """Lieferlänge(n) der Abmessung: '6.000 mm' bzw. aus dem Schnittplan '3 × 6.000 + 1 × 12.000 mm'."""
    if len(g["laengen"]) > 1:
        return " + ".join(f"{n} × {_z(l, 0)}" for l, n in sorted(g["laengen"].items())) + " mm"
    laenge = next(iter(g["laengen"]), g["stange"])
    return f"{_z(laenge, 0)} mm" if laenge else ""


class MeterpreisDialog(QDialog):
    """Fenster 'Material …': je Abmessung Oberfläche, Lieferlänge, Material (Eigen-/Kundenmaterial) und Meterpreis
    änderbar, dazu der Materialeinsatz laut Schnittplan; unten Handling Kundenmaterial des Angebots und die
    Materialwerte aus den Einstellungen (nur Anzeige). gruppen = rechnen.material_abmessungen(...), k = Kontext
    (profile, oberflaechen), kopf = Angebotskopf, laengen(g) = Lieferlängen der Abmessung [mm], einst = Einstellungen,
    veraltet: Schnittplan passt nicht mehr zu den Positionen. Nach 'Übernehmen': self.aenderungen = [(Gruppe,
    {Feld: Wert})] (nur geänderte Abmessungen, Felder der Positionen) und self.kopf_aenderungen = {Feld: Wert}."""

    def __init__(self, parent, gruppen, k, kopf, laengen=None, einst=None, veraltet=False, ohne_plan=False):
        super().__init__(parent)
        self.gruppen, self.kopf = gruppen, kopf
        self.aenderungen, self.kopf_aenderungen = [], {}
        self.setWindowTitle("Material je Abmessung")
        self.resize(1320, 250 + 52 * min(len(gruppen), 8))
        lay = QVBoxLayout(self)
        lay.addWidget(hilfe.Hinweis(
            "Alles zum Material dieses Angebots je Abmessung: Oberfläche, Lieferlänge, Eigen- oder Kundenmaterial und "
            "Meterpreis gelten für alle Positionen der Abmessung und gehen nach 'Übernehmen' in die Kalkulation ein. "
            "Meterpreis grau = berechnet aus Lieferlängen, Preisen bzw. Tonnenpreis (mit Aufpreis der Oberfläche); ein "
            "eigener Wert steht fett, Feld leeren = wieder berechnet. Stangen, Meter, Gewicht und Material € kommen "
            "aus dem Schnittplan; nach einer anderen Lieferlänge oder Oberfläche bitte neu optimieren.",
            schluessel="meterpreise"))
        if ohne_plan or veraltet:
            t = QLabel("Noch nicht optimiert: Stangen, Meter und Gewicht folgen nach dem Optimieren." if ohne_plan else
                       "Der Schnittplan passt nicht mehr zu den Positionen: Materialeinsatz bitte nach dem Optimieren "
                       "prüfen.")
            t.setStyleSheet("color: #C00000;")
            lay.addWidget(t)
        self.tabelle = QTableWidget(len(gruppen), len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.verticalHeader().setDefaultSectionSize(BILD + 6)
        self.tabelle.setIconSize(QSize(BILD, BILD))
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        self.felder, self.oberflaechen, self.laengen, self.herkunft = [], [], [], []
        fett = QFont()
        fett.setBold(True)
        ob_liste = [ROH] + sorted(o for o in k.oberflaechen if o.lower() != ROH)
        for r, g in enumerate(gruppen):
            werte = {0: None, 1: g["profil"], 2: g["werkstoff"],
                     6: ", ".join(_z(p, 0) for p in g["positionen"] if p is not None),
                     7: _z(g["stangen"], 0) if g["stangen"] else "–", 8: _z(g["meter"], 1) if g["stangen"] else "–",
                     9: _z(g["kg"], 1) if g["stangen"] else "–", 10: _z(g["kosten"]) if g["stangen"] else "–",
                     11: _z(g["berechnet"]) if g["berechnet"] is not None else "–"}
            for c, w in werte.items():
                it = QTableWidgetItem("" if w is None else w)
                if c >= 7:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 11:
                    it.setForeground(QColor(GRAU))
                    if g["fehlt"]:
                        it.setToolTip(g["fehlt"])
                if c == 1:
                    it.setFont(fett)
                    it.setToolTip(f"Teile {_z(g['teile_m'], 1)} m"
                                  + (f", Ausnutzung {_z(100 * g['ausnutzung'], 1)} %" if g["ausnutzung"] else "")
                                  + (f", Lieferlängen laut Schnittplan: {laengen_text(g)}" if g["laengen"] else ""))
                self.tabelle.setItem(r, c, it)
            self.tabelle.item(r, 0).setIcon(QIcon(querschnitt_pixmap(k.profile.get(g["profil"]))))
            ob = QComboBox()
            ob.addItems(ob_liste)
            ob.setCurrentText(g["oberflaeche"] or ROH)
            self.oberflaechen.append(ob)
            self.tabelle.setCellWidget(r, 3, ob)
            lg = QComboBox()
            lg.setEditable(True)
            werte_l = sorted({x for x in ((laengen(g) if laengen else []) + [g["stange"]]) if x})
            lg.addItems([_z(x, 0) for x in werte_l])
            lg.setCurrentText(_z(g["stange"], 0) if g["stange"] else "")
            lg.setToolTip("Lieferlänge der Stangen dieser Abmessung [mm] (Liste aus den Stammdaten Lieferlängen, "
                          "andere Länge eintippen); gleich der Standard-Stangenlänge des Angebots = keine Abweichung")
            self.laengen.append(lg)
            self.tabelle.setCellWidget(r, 4, lg)
            hk = QComboBox()
            hk.addItems(MATERIAL_HERKUNFT)
            hk.setCurrentText(KUNDENMATERIAL if g["kunde"] else EIGENMATERIAL)
            self.herkunft.append(hk)
            self.tabelle.setCellWidget(r, 5, hk)
            feld = QLineEdit()
            feld.setAlignment(Qt.AlignRight)
            feld.setPlaceholderText(_z(g["berechnet"]) if g["berechnet"] is not None else "Preis eintragen")
            if g["manuell"] is not None:
                feld.setText(_z(g["manuell"]))
            feld.textChanged.connect(lambda t, feld=feld: self._fett(feld))       # eigener Wert fett, berechnet normal
            self._fett(feld)
            feld.setToolTip("Eigener Meterpreis für diese Abmessung; leer = berechnet")
            self.felder.append(feld)
            self.tabelle.setCellWidget(r, 12, feld)
            hk.currentTextChanged.connect(lambda t, feld=feld: self._kunde(feld, t))
            self._kunde(feld, hk.currentText())
        kopf_z = self.tabelle.horizontalHeader()
        for i, b in enumerate((BILD + 10, 130, 0, 95, 125, 140, 70, 60, 65, 85, 85, 110, 115)):
            if b:
                self.tabelle.setColumnWidth(i, b)
        kopf_z.setSectionResizeMode(2, QHeaderView.Stretch)
        lay.addWidget(self.tabelle, 1)
        summe = sum(g["kosten"] for g in gruppen)
        self.summe = QLabel(f"Material gesamt laut Schnittplan: {_z(summe)} €  ·  "
                            f"{_z(sum(g['meter'] for g in gruppen), 1)} m  ·  {_z(sum(g['kg'] for g in gruppen), 1)} kg")
        self.summe.setStyleSheet(f"color: {GRAU};")
        lay.addWidget(self.summe)
        unten = QFormLayout()
        self.handling = QLineEdit(_z(kopf.get("handling_beistellung"), 3) if kopf.get("handling_beistellung") else "")
        self.handling.setPlaceholderText("0")
        self.handling.setMaximumWidth(120)
        self.handling.setToolTip("Prüfen, Einlagern, Transport je kg der beigestellten Stangen (nur Kundenmaterial)")
        unten.addRow("Handling Kundenmaterial [€/kg]:", self.handling)
        e = einst or {}
        art = e.get("zuschlag_material_art")
        info = QLabel(f"Aus den Einstellungen: Zuschlag Material {_z(100 * rechnen._n(e.get('zuschlag_material')), 1)} %"
                      f"  ·  Händler-Mehrlänge {_z(rechnen.einstellung_wert(e, 'haendler_mehr_kurz'), 0)} mm bis "
                      f"{_z(rechnen.einstellung_wert(e, 'haendler_mehr_grenze'), 0)} mm Stangenlänge, darüber "
                      f"{_z(rechnen.einstellung_wert(e, 'haendler_mehr_lang'), 0)} mm" + (f" ({art})" if art else ""))
        info.setStyleSheet(f"color: {GRAU};")
        info.setToolTip("Gilt für alle Angebote; änderbar unter Einstellungen")
        unten.addRow("", info)
        lay.addLayout(unten)
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color: #C00000;")
        lay.addWidget(self.fehler)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Übernehmen")
        knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self.annehmen)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    @staticmethod
    def _fett(feld):
        f = feld.font()
        f.setBold(bool(feld.text().strip()))
        feld.setFont(f)

    @staticmethod
    def _kunde(feld, herkunft):
        """Kundenmaterial hat keinen Meterpreis: Feld gesperrt."""
        kunde = herkunft == KUNDENMATERIAL
        feld.setEnabled(not kunde)
        if kunde:
            feld.setPlaceholderText("Kundenmaterial")

    @staticmethod
    def _zahl(text, name):
        try:
            w = zahl_aus_text(text)
        except ValueError:
            raise ValueError(f"{name}: „{text}“ ist keine Zahl.") from None
        if w < 0:
            raise ValueError(f"{name} darf nicht negativ sein.")
        return w

    def _preis(self, g, feld):
        t = feld.text().strip()
        if not t or not feld.isEnabled():
            return None
        w = self._zahl(t, f"{g['profil']}: Meterpreis")
        # 0 = kein Preis von Hand; berechneten Wert unverändert bestätigt = bleibt berechnet
        if w == 0 or g["manuell"] is None and g["berechnet"] is not None and abs(w - round(g["berechnet"], 2)) < 0.005:
            return None
        return round(w, 4)

    def werte(self):
        """([(Gruppe, {Feld: Wert})] der geänderten Abmessungen, {Kopffeld: Wert}); ValueError bei ungültiger Eingabe."""
        out = []
        for i, g in enumerate(self.gruppen):
            neu = {}
            preis = self._preis(g, self.felder[i])
            if (preis is None) != (g["manuell"] is None) or preis is not None and abs(preis - g["manuell"]) > 1e-9:
                neu["preis_m"] = preis
            ob = self.oberflaechen[i].currentText()
            if (ob if ob.lower() != ROH else "") != (g["oberflaeche"] or ""):
                neu["oberflaeche"] = ob
            t = self.laengen[i].currentText().strip()
            laenge = self._zahl(t, f"{g['profil']}: Lieferlänge") if t else None
            if laenge is not None and not 500 <= laenge <= 20000:
                raise ValueError(f"{g['profil']}: Lieferlänge zwischen 500 und 20.000 mm eintragen.")
            if laenge is not None and abs(laenge - (g["stange"] or 0)) > 1e-6:
                neu["stange"] = None if abs(laenge - rechnen._n(self.kopf.get("stange"))) < 1e-6 else int(round(laenge))
            hk = self.herkunft[i].currentText()
            if (hk == KUNDENMATERIAL) != g["kunde"]:
                neu["material_herkunft"] = hk
            if neu:
                out.append((g, neu))
        kopf = {}
        t = self.handling.text().strip()
        h = self._zahl(t, "Handling Kundenmaterial") if t else None
        if (h or None) != (self.kopf.get("handling_beistellung") or None):
            kopf["handling_beistellung"] = h or None
        return out, kopf

    def annehmen(self):
        try:
            self.aenderungen, self.kopf_aenderungen = self.werte()
        except ValueError as e:
            self.fehler.setText(str(e))
            return
        self.accept()
