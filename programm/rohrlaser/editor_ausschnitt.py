"""Ausklinkung mit einstellbarer Tiefe im Teile-Editor (CAD-Entwicklungsplan Paket 4, Patrick 12.11.2026).

Rohr-Editor: neue Kontur „Ausschnitt mit Tiefe“ auf der im 3D gewählten Außenfläche (sonst oben) oder aus einer
bestehenden Kontur (Bohrung, Langloch, Rechteck, Polygon) umgewandelt; Tiefe, Form und Richtung stehen rechts in den
Eigenschaften, das 3D zeigt den Ausschnitt sofort (Vorschau), Strg+Z nimmt ihn zurück.
Blech-Editor: Ausklinkung an einer Kante der Außenkontur mit Lage, Breite, Tiefe und Eckradius; der Dialog zeigt die
Kontur vorher und nachher und meldet, was nicht ausführbar ist."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QLabel,
                               QVBoxLayout, QWidget)

from . import ausschnitt, auswahl3d, blech, blech3d, einblendung, schneidweg as sw, stil

TITEL = "Ausschnitt mit Tiefe"
TIPP_ROHR = ("Ausklinkung mit einstellbarer Tiefe: Kontur auf einer Fläche, die um die Tiefe in das Profil geht. Reicht "
             "sie über die Kante der Fläche, werden die Seitenwände bis zur Tiefe mitgeschnitten; ein Durchbruch "
             "entsteht erst ab der ganzen Profilhöhe. Vorher im 3D mit „Auswahl“ eine Außenfläche wählen, dann "
             "liegt der Ausschnitt dort")
TIPP_BLECH = ("Ausklinkung mit einstellbarer Tiefe an einer Kante der Außenkontur: Lage, Breite, Tiefe und Eckradius "
              "eingeben, die Vorschau zeigt die Kontur vorher und nachher")


def _runden(x):
    return round(x * 2) / 2


def vorgabe(qs, seite=None):
    """Maße eines neuen Ausschnitts auf der Seite: so breit wie die Fläche (erreicht beide Kanten), Tiefe ein
    Viertel der Profilhöhe, mindestens Wand + 2 mm."""
    if qs.r:
        return dict(b=_runden(max(10.0, qs.r)), h=_runden(2 * qs.r), tiefe=_runden(max(qs.wand + 2, qs.r / 2)))
    f = qs.flaeche(seite) if seite else (qs.flaechen[0] if qs.flaechen else None)
    breit = f.breite if f is not None else qs.B
    hoch = max((-((p[0] - f.mitte[0]) * f.n[0] + (p[1] - f.mitte[1]) * f.n[1]) for g in qs.flaechen
                for p in (g.p0, g.p1)), default=qs.H) if f is not None else qs.H
    wand = qs.wand or qs.dicke
    tiefe = max(wand + 2, hoch / 4) if hoch > wand + 2 else hoch
    return dict(b=_runden(max(10.0, breit / 2)), h=_runden(breit), tiefe=_runden(tiefe))


def flaeche_aus_auswahl(rahmen):
    """(Seite, x, Versatz quer) der im 3D gewählten Fläche oder None; ValueError, wenn sie keine Außenfläche ist."""
    a = rahmen.ansicht()
    if a is None:
        return None
    gew = [g for g in a.wahl.gewaehlt if g.get("art") == auswahl3d.FLAECHE]
    if not gew:
        return None
    return ausschnitt.flaeche_zu_seite(rahmen.d.qs, a.wahl.punkte(gew[-1:]))


def einfuegen(rahmen):
    """Rohr-Editor: neuen Ausschnitt mit Tiefe anlegen, auf der im 3D gewählten Außenfläche (sonst erste Seite)."""
    d = rahmen.d
    z = dict(art=sw.AUSSCHNITT, anzahl=1)
    try:
        ort = flaeche_aus_auswahl(rahmen)
    except ValueError as f:
        einblendung.melden(d, str(f))
        return False
    if ort is not None:
        seite, x, q = ort
        z.update(seite=seite, x=x)
        if q:
            z["q"] = q
    z.update(vorgabe(d.qs, z.get("seite") if not d.qs.r else None))
    d.zeile_neu(z)
    r = d.tabelle.rowCount() - 1
    d.tabelle.selectRow(r)
    rahmen.aktualisieren()
    rahmen.waehlen(f"kontur:{r}")
    return True


def als_ausschnitt(z, wand):
    """Konturzeile (Bohrung, Langloch, Rechteck, Polygon) als Ausschnitt mit Tiefe: gleiche Kontur an gleicher
    Stelle, Tiefe = Wand (schneidet zunächst genau wie bisher). None, wenn die Art nicht passt."""
    art = z.get("art")
    fest = {k: v for k, v in z.items() if k in ("anzahl", "x", "abstand", "seite", "q", "text", "drehung", "bezug")}
    neu = dict(fest, art=sw.AUSSCHNITT, tiefe=wand or 1.0)
    if art == sw.BOHRUNG:
        neu.update(kontur_form="Rund", b=z.get("d"))
    elif art == sw.LANGLOCH:
        neu.update(kontur_form="Langloch", b=z.get("l"), h=z.get("b"))
        if z.get("quer"):
            neu["drehung"] = (sw._z(z.get("drehung")) + 90) % 360
    elif art == sw.RECHTECK:
        neu.update(b=z.get("b"), h=z.get("h"))
        if sw._z(z.get("r")):
            neu["eckradius"] = z["r"]
    elif art == sw.POLYGON:
        neu.update(kontur_form="Polygon", eckpunkte=z.get("punkte"))
    else:
        return None
    return neu


def umwandeln(rahmen, r=None):
    """Rohr-Editor: die gewählte Kontur in einen Ausschnitt mit Tiefe umwandeln (Kontur als Bearbeitungsgrundlage)."""
    d = rahmen.d
    r = rahmen._gewaehlte_zeile() if r is None else r
    e = d.eingaben()
    konturen = list(e.get("konturen") or [])
    neu = als_ausschnitt(konturen[r], d.qs.wand or d.qs.dicke) if r is not None and 0 <= r < len(konturen) else None
    if neu is None:
        einblendung.melden(d, "Erst eine Bohrung, ein Langloch, ein Rechteck oder ein Polygon wählen.")
        return False
    konturen[r] = neu
    d.eingaben_setzen(dict(e, konturen=konturen))
    d.rechnen()
    rahmen.aktualisieren()
    rahmen.waehlen(f"kontur:{r}")
    return True


# -------------------------------------------------------------------------------------------------- Blech
class KonturVorschau(QWidget):
    """Außenkontur vorher (grau) und nachher (blau), die Ausklinkung rot gefüllt."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(360, 220)
        self.alt, self.neu = [], None

    def setzen(self, alt, neu):
        self.alt, self.neu = alt, neu
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), stil.farbe("#FFFFFF"))
        if not self.alt:
            return
        xs, ys = [x for x, _ in self.alt], [y for _, y in self.alt]
        w, h = max(max(xs) - min(xs), 1e-6), max(max(ys) - min(ys), 1e-6)
        m = min((self.width() - 30) / w, (self.height() - 30) / h)
        ox, oy = (self.width() - w * m) / 2, (self.height() + h * m) / 2

        def poly(pk):
            return QPolygonF([QPointF(ox + (x - min(xs)) * m, oy - (y - min(ys)) * m) for x, y in pk])
        if self.neu:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(220, 60, 50, 110))
            p.drawPolygon(poly(self.alt))
            p.setBrush(stil.farbe("#EEF1F5"))
            p.setPen(QPen(stil.farbe("#1F5FBF"), 2))
            p.drawPolygon(poly(self.neu))
        else:
            p.setBrush(stil.farbe("#EEF1F5"))
            p.setPen(QPen(stil.farbe("#808080"), 1.5))
            p.drawPolygon(poly(self.alt))


class BlechAusklinkungDialog(QDialog):
    """Ausklinkung mit einstellbarer Tiefe an einer Kante des Blechs: Eingaben, Vorschau und Meldung."""

    def __init__(self, parent, e):
        super().__init__(parent)
        self.setWindowTitle("Ausklinkung mit Tiefe")
        self.e, self.ergebnis, self.hinweise = e, None, []
        zs = blech.zuschnitt(e)
        self.alt = blech3d.aussenkontur(e, zs)
        W, H = max(x for x, _ in self.alt), max(y for _, y in self.alt)
        self.masse = (W, H)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.kante = QComboBox()
        self.kante.addItems(list(ausschnitt.KANTEN))
        self.kante.setToolTip("Kante des Zuschnitts (Abwicklung), von der die Ausklinkung in das Blech geht")
        self.lage = self._zahl(W / 2, 100000, "Mitte der Ausklinkung entlang der Kante, ab der linken bzw. unteren Ecke")
        self.breite = self._zahl(min(40.0, W / 4), 100000, "Breite entlang der Kante")
        self.tiefe = self._zahl(5.0, 100000, "Tiefe von der Kante in das Blech")
        self.radius = self._zahl(0.0, 10000, "Rundung der beiden inneren Ecken (0 = scharfkantig)")
        self.umgekehrt = QCheckBox("Richtung umkehren (von der gegenüberliegenden Kante)")
        form.addRow("Kante", self.kante)
        form.addRow("Lage entlang der Kante", self.lage)
        form.addRow("Breite", self.breite)
        form.addRow("Tiefe", self.tiefe)
        form.addRow("Eckradius innen", self.radius)
        form.addRow("", self.umgekehrt)
        lay.addLayout(form)
        self.bild = KonturVorschau()
        lay.addWidget(self.bild, 1)
        self.meldung = QLabel()
        self.meldung.setWordWrap(True)
        lay.addWidget(self.meldung)
        self.knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.knoepfe.button(QDialogButtonBox.Ok).setText("Ausklinken")
        self.knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        self.knoepfe.accepted.connect(self.accept)
        self.knoepfe.rejected.connect(self.reject)
        lay.addWidget(self.knoepfe)
        for w in (self.lage, self.breite, self.tiefe, self.radius):
            w.valueChanged.connect(self.rechnen)
        self.kante.currentTextChanged.connect(self._kante_neu)
        self.umgekehrt.toggled.connect(self.rechnen)
        self.rechnen()

    def _zahl(self, wert, bis, tipp):
        f = QDoubleSpinBox()
        f.setRange(0, bis)
        f.setDecimals(1)
        f.setSuffix(" mm")
        f.setValue(wert)
        f.setToolTip(tipp)
        return f

    def _kante_neu(self, kante):
        lang = self.masse[0] if kante in ("unten", "oben") else self.masse[1]
        self.lage.blockSignals(True)
        self.lage.setValue(lang / 2)
        self.lage.blockSignals(False)
        self.rechnen()

    def rechnen(self):
        try:
            self.ergebnis, self.hinweise = ausschnitt.blech_ausklinken(
                self.e, self.kante.currentText(), self.lage.value(), self.breite.value(), self.tiefe.value(),
                self.radius.value(), self.umgekehrt.isChecked())
            neu = sw.punkte(self.ergebnis["punkte"])
            zs = blech.zuschnitt(self.ergebnis)
            text = (f"Ausklinkung {self.breite.value():g} × {self.tiefe.value():g} mm, Schnittlänge außen jetzt "
                    f"{zs['aussen']:.1f} mm.".replace(".", ",", 1) + " " + " ".join(self.hinweise)).strip()
            self.meldung.setStyleSheet("color: #7A5A00;" if self.hinweise else "color: #1E6B34;")
        except ValueError as f:
            self.ergebnis, neu, text = None, None, str(f).replace("Ausklinkung mit Tiefe: ", "")
            self.meldung.setStyleSheet("color: #B42318;")
        self.meldung.setText(text)
        self.bild.setzen(self.alt, neu)
        self.knoepfe.button(QDialogButtonBox.Ok).setEnabled(self.ergebnis is not None)


def blech_dialog(rahmen):
    """Blech-Editor: Dialog zeigen und die Ausklinkung in die Außenkontur übernehmen (Strg+Z nimmt sie zurück)."""
    d = rahmen.d
    try:
        dlg = BlechAusklinkungDialog(d, d.eingaben())
    except ValueError as f:
        einblendung.melden(d, f"Erst die Maße des Blechs eingeben ({f})")
        return False
    if dlg.exec() != QDialog.Accepted or dlg.ergebnis is None:
        return False
    return blech_uebernehmen(rahmen, dlg.ergebnis)


def blech_uebernehmen(rahmen, e):
    d = rahmen.d
    d.eingaben_setzen(e)
    d.rechnen()
    rahmen.aktualisieren()
    return True

