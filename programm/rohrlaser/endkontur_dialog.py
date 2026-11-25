"""Dialog 'Endkontur …' (Master-Auftrag universelle 3D-Konturbearbeitung, Patrick 25.11.2026): Anfangs- bzw. Endkontur
eines Rohrs frei festlegen – schräg, V-Spitze, V-Kerbe, U-Kerbe, U-Zunge, S-Kurve, Bogen konvex/konkav, abgestuft,
Freiform (in der Seitenansicht oder direkt auf der Abwicklung) und Kombinationen mehrerer Konturen an einem Ende.

Gleiches Muster wie der Dialog 'Gegenrohr …' (gegenrohr_dialog.py): aufgerufen aus dem Schneidweg-Rechner, dem
3D-Editor (Eigenschaften, Rechtsklick auf das Ende, Menüband) und damit aus allen Editoren, die den Rechner nutzen
(Rohr, Baugruppe, Satz in 3D). Das Programm rechnet Verlauf, Schnittlänge und Tiefe sofort (endkontur.py) und zeigt
die Kontur auf der Abwicklung des Endes: bisher grau gestrichelt, neu blau, nicht schneidbare Stellen rot.

Ergebnis (Eingabe des Endes 'kontur'): dict wie endkontur.lesen bzw. None (keine Endkontur, gerader Schnitt).
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

from . import endkontur as ek, rechnen, skizze as sk, stil
from .eingabe import RechenSpin

NEU = stil.farbe_fest("#1F6FB2")
ALT = stil.farbe_fest("#8A94A0")
ROT = stil.farbe_fest("#C62828")
RICHTUNGEN = {"oben (0°)": 0.0, "rechts/vorne (90°)": 90.0, "unten (180°)": 180.0, "links/hinten (270°)": 270.0}
VORLAGEN = (("V-Spitze 45°", dict(typ=ek.V_SPITZE)), ("V-Kerbe", dict(typ=ek.V_KERBE)),
            ("U-Kerbe", dict(typ=ek.U_KERBE)), ("Fischmaul (Bogen konkav)", dict(typ=ek.BOGEN_KAV)),
            ("Zapfen (U-Zunge)", dict(typ=ek.U_ZUNGE)), ("Stufe", dict(typ=ek.STUFEN)))


def _spin(minimum, maximum, wert, einheit, tipp, stellen=1):
    f = RechenSpin()
    f.setRange(minimum, maximum)
    f.setDecimals(stellen)
    f.setSuffix(f" {einheit}")
    f.setValue(wert)
    f.setToolTip(tipp)
    return f


class Vorschau(QWidget):
    """Abwicklung des Endes: s waagerecht (Umfang), Abstand von der Spitze senkrecht; bisher grau gestrichelt, neu
    blau, Befunde rot markiert."""

    def __init__(self, qs, alt=None, parent=None):
        super().__init__(parent)
        self.qs, self.alt, self.neu, self.befunde = qs, alt, None, []
        self.setMinimumSize(460, 170)

    def setzen(self, neu, befunde):
        self.neu, self.befunde = neu, befunde
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), stil.farbe_fest("#FFFFFF"))
        U = self.qs.umfang or 1.0
        linien = [x for x in (self.alt, self.neu) if x]
        tmax = max([d for li in linien for _, d in li] + [10.0])
        r = QRectF(36, 12, self.width() - 48, self.height() - 34)

        def pt(s, d):
            return QPointF(r.left() + s / U * r.width(), r.top() + d / tmax * r.height())
        p.setPen(QPen(ALT, 0.6))
        for name, s0, s1 in self.qs.abwicklung_streifen():
            x = r.left() + s0 / U * r.width()
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.drawText(QRectF(x + 2, r.bottom() + 2, (s1 - s0) / U * r.width(), 16), Qt.AlignLeft, name)
        p.drawText(QRectF(0, r.top() - 4, 34, 16), Qt.AlignRight, "0")
        p.drawText(QRectF(0, r.bottom() - 12, 34, 16), Qt.AlignRight, f"{rechnen.zahl(tmax, 0)}")
        for art, _t, s0, s1 in self.befunde:
            if art != ek.FEHLER and s1 - s0 < 1e-6:
                continue
            a, b = (s0, s1) if s1 >= s0 else (s0, U)
            p.fillRect(QRectF(pt(a, 0).x() - 2, r.top(), max(pt(b, 0).x() - pt(a, 0).x() + 4, 4), r.height()),
                       stil.farbe_fest("#F8D7DA") if art == ek.FEHLER else stil.farbe_fest("#FFF2CC"))
        for li, farbe, strich in ((self.alt, ALT, Qt.DashLine), (self.neu, NEU, Qt.SolidLine)):
            if not li:
                continue
            pfad = QPainterPath(pt(*li[0]))
            for s, d in li[1:]:
                pfad.lineTo(pt(s, d))
            pen = QPen(farbe, 2.0 if farbe == NEU else 1.2)
            pen.setStyle(strich)
            p.setPen(pen)
            p.drawPath(pfad)
        p.end()


class TeilKontur(QGroupBox):
    """Eine Teilkontur: Art, Richtung und Maße."""

    def __init__(self, qs, k=None, nummer=1, parent=None, geaendert=None):
        super().__init__(f"Kontur {nummer}", parent)
        k = dict(k or {})
        self.qs = qs
        form = QFormLayout(self)
        self.typ = QComboBox()
        self.typ.addItems([t for t in ek.TYPEN if t != ek.KOMBI])
        self.typ.setCurrentText(k.get("typ") or ek.V_SPITZE)
        self.richtung = QComboBox()
        for t, w in RICHTUNGEN.items():
            self.richtung.addItem(t, w)
        w = float(k.get("richtung") or 0) % 360
        i = next((j for j, v in enumerate(RICHTUNGEN.values()) if abs(v - w) < 1e-6), -1)
        if i < 0:
            self.richtung.addItem(f"{rechnen.zahl(w, 1)}°", w)
            i = self.richtung.count() - 1
        self.richtung.setCurrentIndex(i)
        self.richtung.setToolTip("Richtung, in der die Kontur in der Seitenansicht verläuft (wie die Gehrungsrichtung: "
                                 "Seite, an der das Teil am längsten ist bzw. die Kontur beginnt)")
        groesse = max(qs.B, qs.H)
        self.tiefe = _spin(0, 5000, ek._z(k.get("tiefe")) or round(groesse / 2, 1), "mm", "Tiefe der Kontur ab der Spitze")
        self.breite = _spin(0, 5000, ek._z(k.get("breite")), "mm", "Breite der Kerbe/Zunge (0 = ganze Breite)")
        self.breite.setSpecialValueText("ganze Breite")
        self.versatz = _spin(-2500, 2500, ek._z(k.get("versatz")), "mm",
                             "Lage der Spitze/Kerbe quer ab der Mitte (asymmetrische Kontur)")
        self.radius = _spin(0, 5000, ek._z(k.get("radius")), "mm", "Radius des Bogens (0 = aus der Tiefe)")
        self.radius.setSpecialValueText("aus Tiefe")
        self.stufen = QLineEdit("; ".join(f"{rechnen.zahl(a, 1)} {rechnen.zahl(b, 1)}"
                                          for a, b in ek.paare(k.get("stufen"))))
        self.stufen.setPlaceholderText("Breite Tiefe; Breite Tiefe … z. B. 20 0; 20 15")
        self.stufen.setToolTip("Stufen von der langen Seite aus: je Stufe Breite und Tiefe [mm]")
        self.punkte = QLineEdit("; ".join(f"{rechnen.zahl(a, 2)} {rechnen.zahl(b, 2)}"
                                          for a, b in ek.paare(k.get("punkte"))))
        self.punkte.setPlaceholderText("w d; w d … (Freiform: w ab Mitte; Abwicklung: s am Umfang)")
        self.punkte.setToolTip("Freiform: Stützpunkte [mm] – w quer ab Mitte bzw. bei „Freiform Abwicklung“ s am Umfang "
                               "ab dem Beginn der Abwicklung, d = Abstand von der Spitze; dazwischen gerade")
        self.zeilen = {}
        for titel, f, schl in (("Art", self.typ, "typ"), ("Richtung", self.richtung, "richtung"),
                               ("Tiefe", self.tiefe, "tiefe"), ("Breite", self.breite, "breite"),
                               ("Versatz", self.versatz, "versatz"), ("Radius", self.radius, "radius"),
                               ("Stufen", self.stufen, "stufen"), ("Punkte", self.punkte, "punkte")):
            form.addRow(titel, f)
            self.zeilen[schl] = (form.labelForField(f), f)
        self.typ.currentTextChanged.connect(self._sichtbar)
        for f in (self.tiefe, self.breite, self.versatz, self.radius):
            f.valueChanged.connect(lambda *_: geaendert and geaendert())
        for f in (self.stufen, self.punkte):
            f.textChanged.connect(lambda *_: geaendert and geaendert())
        self.typ.currentTextChanged.connect(lambda *_: geaendert and geaendert())
        self.richtung.currentIndexChanged.connect(lambda *_: geaendert and geaendert())
        self._sichtbar()

    def _sichtbar(self, *_):
        noetig = set(ek.MASSE.get(self.typ.currentText(), ())) | {"typ"}
        if self.typ.currentText() not in (ek.FREI_S,):
            noetig.add("richtung")
        for schl, (lab, f) in self.zeilen.items():
            an = schl in noetig
            f.setVisible(an)
            if lab is not None:
                lab.setVisible(an)

    def wert(self):
        typ = self.typ.currentText()
        k = dict(typ=typ)
        if typ != ek.FREI_S and self.richtung.currentData():
            k["richtung"] = round(float(self.richtung.currentData()), 3)
        for schl, f in (("tiefe", self.tiefe), ("breite", self.breite), ("versatz", self.versatz),
                        ("radius", self.radius)):
            if schl in ek.MASSE.get(typ, ()) and f.value():
                k[schl] = round(f.value(), 3)
        if typ == ek.STUFEN:
            k["stufen"] = [[round(a, 3), round(b, 3)] for a, b in ek.paare(self.stufen.text())]
        if typ in (ek.FREI, ek.FREI_S):
            k["punkte"] = [[round(a, 3), round(b, 3)] for a, b in ek.paare(self.punkte.text())]
        return k


class EndkonturDialog(QDialog):
    def __init__(self, profil, kontur=None, titel="Ende", parent=None, alt=None, kerf=0.2, laenge=None):
        super().__init__(parent)
        self.setWindowTitle(f"Endkontur – {titel}")
        self.qs = sk.Querschnitt(profil)
        self.kerf, self.laenge, self.entfernt = kerf, laenge, False
        self.wand = profil.get("wand")
        k = ek.lesen(kontur) or {}
        lay = QVBoxLayout(self)
        info = QLabel("Anfangs- bzw. Endkontur frei festlegen: schräg, V, U, S, Bogen, Stufen oder Freiform, auch "
                      "mehrere Konturen überlagert (an jeder Stelle gilt der tiefste Schnitt). Die Kontur wird senkrecht "
                      "zur Oberfläche geschnitten (2D). Die Stangenoptimierung legt passende Konturen benachbarter "
                      "Teile ineinander, wenn es technisch zulässig ist.")
        info.setWordWrap(True)
        lay.addWidget(info)
        vz = QHBoxLayout()
        vz.addWidget(QLabel("Vorlage:"))
        for text, vk in VORLAGEN:
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, v=vk: self._vorlage(v))
            vz.addWidget(b)
        vz.addStretch(1)
        lay.addLayout(vz)
        self.teile_lay = QVBoxLayout()
        lay.addLayout(self.teile_lay)
        self.teile = []
        for t in (k.get("teile") if k.get("typ") == ek.KOMBI else [k] if k else [dict(typ=ek.V_SPITZE)]):
            self._teil_dazu(t)
        zeile = QHBoxLayout()
        self.dazu = QPushButton("+ weitere Kontur überlagern")
        self.dazu.setToolTip("Kombination: z. B. Gehrung (Schräg) und V-Kerbe an demselben Ende")
        self.dazu.clicked.connect(lambda: self._teil_dazu(dict(typ=ek.V_KERBE)))
        self.weg_teil = QPushButton("− letzte Kontur entfernen")
        self.weg_teil.clicked.connect(self._teil_weg)
        zeile.addWidget(self.dazu)
        zeile.addWidget(self.weg_teil)
        zeile.addStretch(1)
        lay.addLayout(zeile)
        self.vorschau = Vorschau(self.qs, sk.ende_abwicklung(self.qs, alt) if alt else None)
        lay.addWidget(self.vorschau)
        self.ergebnis = QLabel()
        self.ergebnis.setWordWrap(True)
        lay.addWidget(self.ergebnis)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        weg = QPushButton("Keine Endkontur")
        weg.setToolTip("Endkontur an diesem Ende entfernen (gerader Schnitt)")
        weg.setEnabled(bool(k))
        weg.clicked.connect(self._entfernen)
        knoepfe.addButton(weg, QDialogButtonBox.ResetRole)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.ok = knoepfe.button(QDialogButtonBox.Ok)
        self._rechnen()

    def _teil_dazu(self, k):
        t = TeilKontur(self.qs, k, len(self.teile) + 1, self, geaendert=self._rechnen)
        self.teile.append(t)
        self.teile_lay.addWidget(t)
        self._rechnen()

    def _teil_weg(self):
        if len(self.teile) > 1:
            t = self.teile.pop()
            t.setParent(None)
            t.deleteLater()
            self._rechnen()

    def _vorlage(self, k):
        while len(self.teile) > 1:
            self._teil_weg()
        t = self.teile[0]
        t.typ.setCurrentText(k["typ"])
        self._rechnen()

    def wert(self):
        teile = [t.wert() for t in self.teile]
        if len(teile) == 1:
            return teile[0]
        return dict(typ=ek.KOMBI, teile=teile)

    def _rechnen(self, *_):
        if not hasattr(self, "vorschau"):
            return
        if hasattr(self, "weg_teil"):
            self.weg_teil.setEnabled(len(self.teile) > 1)
        k = self.wert()
        um = ek.umriss(self.qs, k)
        if not um:
            self.ergebnis.setText(f"<span style='color:{ROT.name()}'>Kontur unvollständig (Maße fehlen)</span>")
            self.ok.setEnabled(False)
            self.vorschau.setzen(None, [])
            return
        befunde = ek.pruefen(self.qs, k, self.kerf, self.laenge, self.wand)
        self.vorschau.setzen([(s, d) for s, d in um], befunde)
        teile = [f"Schnittlänge {rechnen.zahl(ek.schnittlaenge(self.qs, k), 1)} mm (Außenmantel)",
                 f"Tiefe {rechnen.zahl(ek.tiefe(self.qs, k), 1)} mm"]
        for art, t, _s0, _s1 in befunde:
            farbe = ROT.name() if art == ek.FEHLER else "#8A6D00"
            teile.append(f"<span style='color:{farbe}'>{art}: {t}</span>")
        self.ergebnis.setText("<br>".join(teile))
        self.ok.setEnabled(not any(a == ek.FEHLER for a, *_ in befunde))

    def _entfernen(self):
        self.entfernt = True
        self.accept()


def fragen(profil, kontur=None, titel="Ende", parent=None, alt=None, kerf=0.2, laenge=None):
    """Dialog zeigen: (geändert, Kontur oder None). alt = bisherige Eingabe des Endes (für den Vergleich)."""
    dlg = EndkonturDialog(profil, kontur, titel, parent, alt, kerf, laenge)
    if dlg.exec() != QDialog.Accepted:
        return False, kontur
    return True, None if dlg.entfernt else dlg.wert()
