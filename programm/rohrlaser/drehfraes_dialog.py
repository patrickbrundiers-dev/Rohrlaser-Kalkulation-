"""Dialog „Richtpreis Dreh-/Frästeil …“ (Patrick 03.11.2026, Plan Richtpreis Frage 6 a): Rohling, Arbeitsgänge mit
Zeiten (von Hand änderbar), Material, Rüsten, Zusätze und Richtpreis eines Dreh- oder Frästeils (drehfraes_preis).
Übernehmen trägt den Richtpreis als EK ab der Stückzahl ein (angebot_fenster.drehfraes_bearbeiten)."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QSpinBox, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import drehfraes, drehfraes_preis as dp

AMPEL_FARBE = {dp.GRUEN: "#2e7d32", dp.GELB: "#ef8f00", dp.ROT: "#c62828"}
SPALTEN = ("Arbeitsgang", "Verfahren", "Minuten je Stück", "Kosten €", "Rechnung")


def _eur(x):
    return f"{x:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _min(x):
    return f"{x:.2f}".replace(".", ",")


def werkstoff_liste(feld, einst):
    """Vorschläge aus der Tabelle Dreh-/Fräs-Werkstoffe im Werkstoff-Feld (freier Text bleibt möglich)."""
    from PySide6.QtWidgets import QCompleter
    ids = sorted((einst or {}).get("werkstoffe") or ())
    if ids:
        c = QCompleter(ids, feld)
        c.setCaseSensitivity(Qt.CaseInsensitive)
        c.setFilterMode(Qt.MatchContains)
        feld.setCompleter(c)
        feld.setToolTip("Werkstoff aus der Tabelle Dreh-/Fräs-Werkstoffe (Einstellungen → Dreh- und Frästeile) oder "
                        "frei; ohne Zeile gilt die Werkstoffgruppe nach Name")


class DrehfraesSkizze(QWidget):
    """Rohling (gestrichelt) und Fertigteil übereinander: Drehteil im Längsschnitt (Absätze außen, Bohrung innen),
    Frästeil in Draufsicht und Seitenansicht mit Taschentiefe; Ampel der Machbarkeit oben links, Befunde farbig."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 190)
        self.d, self.erg = {}, {}

    def setzen(self, d, erg):
        self.d, self.erg = d or {}, erg or {}
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        text = pal.windowText().color()
        p.fillRect(self.rect(), pal.base())
        roh = self.erg.get("rohling") or {}
        ampel = self.erg.get("ampel") or dp.GRUEN
        farbe = QColor(AMPEL_FARBE.get(ampel, "#2e7d32"))
        p.setPen(Qt.NoPen)
        p.setBrush(farbe)
        p.drawEllipse(QRectF(8, 8, 12, 12))
        p.setPen(text)
        p.drawText(26, 19, dp.AMPEL_TEXT.get(ampel, ""))
        if not roh:
            p.end()
            return
        befunde = self.erg.get("machbarkeit") or ()
        if self.d.get("art") == drehfraes.DREHTEIL:
            self._drehteil(p, roh, befunde, text)
        else:
            self._fraesteil(p, roh, befunde, text)
        p.end()

    def _rahmen(self, b, h, x0, y0, w, hh):
        s = min(w / max(b, 1), hh / max(h, 1))
        return s, x0 + (w - b * s) / 2, y0 + (hh - h * s) / 2

    def _drehteil(self, p, roh, befunde, text):
        k = self.d.get("kennwerte") or {}
        lr, dr = float(roh["laenge"]), float(roh["d"])
        s, x0, y0 = self._rahmen(lr, dr, 20, 30, self.width() - 40, self.height() - 70)
        mitte = y0 + dr * s / 2
        stift = QPen(text, 1, Qt.DashLine)
        p.setPen(stift)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(x0, y0, lr * s, dr * s))
        aussen = k.get("aussen") or [dict(d=self.d.get("durchmesser"), l=self.d.get("laenge"),
                                          z=float(self.d.get("laenge") or 0) / 2)]
        innen = k.get("innen") or ([dict(d=self.d.get("innen"), l=self.d.get("laenge"),
                                         z=float(self.d.get("laenge") or 0) / 2)] if self.d.get("innen") else [])
        z_min = min(float(a["z"]) - float(a["l"]) / 2 for a in aussen)
        versatz = (lr - float(self.d.get("laenge") or 0)) / 2
        warn = {x["gang"] for x in befunde}
        teil = QColor("#4a78b5")  # fest: Fertigteil blau, auf hell und dunkel sichtbar
        p.setPen(QPen(teil.darker(130), 1))
        p.setBrush(QBrush(teil))
        for a in aussen:
            z0 = float(a["z"]) - float(a["l"]) / 2 - z_min + versatz
            r = float(a["d"]) / 2
            p.drawRect(QRectF(x0 + z0 * s, mitte - r * s, float(a["l"]) * s, 2 * r * s))
        wand_warn = any("Wand" in x["text"] for x in befunde)
        p.setBrush(pal_base(self))
        p.setPen(QPen(QColor(AMPEL_FARBE[dp.ROT if any(x["stufe"] == dp.ROT and "Wand" in x["text"]
                                                     for x in befunde) else dp.GELB]), 2) if wand_warn else Qt.NoPen)
        for a in innen:
            z0 = float(a["z"]) - float(a["l"]) / 2 - z_min + versatz
            r = float(a["d"]) / 2
            p.drawRect(QRectF(x0 + z0 * s, mitte - r * s, float(a["l"]) * s, 2 * r * s))
        p.setPen(QPen(text, 1, Qt.DashDotLine))
        p.drawLine(int(x0 - 8), int(mitte), int(x0 + lr * s + 8), int(mitte))
        if "Drehen" in warn:
            p.setPen(QPen(QColor(AMPEL_FARBE[dp.GELB]), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(x0 - 3, y0 - 3, lr * s + 6, dr * s + 6))
        p.setPen(text)
        f = QFont(p.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() * 0.85))
        p.setFont(f)
        p.drawText(QRectF(4, self.height() - 34, self.width() - 8, 32), Qt.AlignCenter | Qt.TextWordWrap,
                   f"Rohling {roh['text']} (gestrichelt), Fertigteil blau, Längsschnitt")

    def _fraesteil(self, p, roh, befunde, text):
        k = self.d.get("kennwerte") or {}
        lr, br, hr = float(roh["laenge"]), float(roh["breite"]), float(roh["hoehe"])
        la, lb, lc = (float(self.d.get(n) or 0) for n in ("laenge", "breite", "hoehe"))
        w = (self.width() - 60) / 2
        teil = QColor("#4a78b5")  # fest: Fertigteil blau, auf hell und dunkel sichtbar
        for i, (hoch, h_teil, titel) in enumerate(((br, lb, "Draufsicht"), (hr, lc, "Seitenansicht"))):
            s, x0, y0 = self._rahmen(lr, hoch, 20 + i * (w + 20), 30, w, self.height() - 75)
            p.setPen(QPen(text, 1, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(x0, y0, lr * s, hoch * s))
            dx, dy = (lr - la) / 2 * s, (hoch - h_teil) / 2 * s
            p.setPen(QPen(teil.darker(130), 1))
            p.setBrush(QBrush(teil))
            p.drawRect(QRectF(x0 + dx, y0 + dy, la * s, h_teil * s))
            tt = float(k.get("taschentiefe") or 0)
            if i == 1 and tt > 0:
                stufe = next((x["stufe"] for x in befunde if "Tasche" in x["text"]), None)
                p.setPen(QPen(QColor(AMPEL_FARBE[stufe]) if stufe else text, 2, Qt.DashLine))
                y = y0 + dy + tt * s
                p.drawLine(int(x0 + dx + 4), int(y), int(x0 + dx + la * s - 4), int(y))
            p.setPen(text)
            p.drawText(QRectF(x0, y0 + hoch * s + 2, lr * s, 16), Qt.AlignCenter, titel)
        n = len(k.get("bohrungen") or ())
        f = QFont(p.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() * 0.85))
        p.setFont(f)
        p.drawText(QRectF(4, self.height() - 34, self.width() - 8, 32), Qt.AlignCenter | Qt.TextWordWrap,
                   f"Rohling {roh['text']} (gestrichelt), Hüllmaß blau" + (f", {n} Bohrung(en)" if n else "")
                   + (f", Tasche {_min(float(k.get('taschentiefe') or 0)).rstrip('0').rstrip(',')} mm tief (Linie)"
                      if k.get("taschentiefe") else ""))


def pal_base(w):
    return QBrush(w.palette().base().color())


class DrehfraesDialog(QDialog):
    """e = Eingaben (drehfraes_preis.aus_step bzw. gespeichert in positionen.technik), einst = Einstellungen."""

    def __init__(self, eltern, e, einst, titel="", nur_lesen=False, netz=None):
        """netz: 3D-Netz der Position aus dem STEP-Import (Datenbank) – wird unverändert in echter Form und Lage
        gezeigt wie im Prüfdialog (Patrick 04.11.2026: „Frästeile im Editor wie in der STEP anzeigen“)."""
        super().__init__(eltern)
        self.e = dict(e)
        self.e["zeiten"] = dict(e.get("zeiten") or {})
        self.einst = einst
        self.ergebnis = {}
        self._laedt = True
        d = self.e.get("daten") or {}
        self.setWindowTitle("Richtpreis Dreh-/Frästeil")
        self.resize(1240 if netz else 1000, 900 if netz else 760)
        lay = QVBoxLayout(self)
        kopf = QLabel(f"<b>{titel or drehfraes.bezeichnung(d, self.e.get('werkstoff'))}</b><br>"
                      f"{drehfraes.text(dict(drehfraes=d, profilform=d.get('art')))}")
        kopf.setWordWrap(True)
        lay.addWidget(kopf)
        form = QFormLayout()
        self.stueck = QSpinBox()
        self.stueck.setRange(1, 1000000)
        self.stueck.setValue(int(float(self.e.get("stueck") or 1)))
        self.werkstoff = QLineEdit(self.e.get("werkstoff") or "")
        self.werkstoff.setPlaceholderText("leer = Stahl")
        werkstoff_liste(self.werkstoff, einst)
        self.rohling = QComboBox()
        self.rohling.addItems(dp.ROHLINGE)
        self.rohling.setCurrentText(self.e.get("rohling") or dp.ROHLING_VOLL)
        self.rohling.setEnabled(d.get("art") == drehfraes.DREHTEIL and float(d.get("innen") or 0) >= 30)
        self.eur_kg = QDoubleSpinBox()
        self.eur_kg.setRange(0, 1000)
        self.eur_kg.setDecimals(2)
        self.eur_kg.setSpecialValueText("Vorgabe der Werkstoffgruppe")
        self.eur_kg.setValue(float(self.e.get("eur_kg") or 0))
        self.zusatz = QDoubleSpinBox()
        self.zusatz.setRange(0, 100000)
        self.zusatz.setDecimals(2)
        self.zusatz.setSuffix(" €/Stück")
        self.zusatz.setValue(float(self.e.get("zusatz_eur") or 0))
        self.zusatz_text = QLineEdit(self.e.get("zusatz_text") or "")
        self.zusatz_text.setPlaceholderText("z. B. 2× Gewinde M8, verzinkt, gehärtet")
        form.addRow("Stückzahl (Rüsten verteilt sich darauf)", self.stueck)
        form.addRow("Werkstoff", self.werkstoff)
        form.addRow("Rohling", self.rohling)
        if d.get("art") != drehfraes.DREHTEIL:          # Frästeil: Rohling immer Flachstahl (Skizze, Summe)
            form.setRowVisible(self.rohling, False)
        form.addRow("Material €/kg", self.eur_kg)
        zh = QHBoxLayout()
        zh.addWidget(self.zusatz)
        zh.addWidget(self.zusatz_text, 1)
        form.addRow("Zusätze (Gewinde, Oberfläche, Härten …)", zh)
        oben = QHBoxLayout()
        self.skizze = DrehfraesSkizze()
        if netz:        # mit 3D: Eingaben und Skizze links übereinander, 3D rechts groß (Leiste ganz lesbar)
            links = QVBoxLayout()
            links.addLayout(form)
            links.addWidget(self.skizze, 1)
            oben.addLayout(links, 1)
        else:
            oben.addLayout(form, 1)
            oben.addWidget(self.skizze, 1)
        self.ansicht3d = None
        if netz:
            from .ansicht3d import Ansicht3DMitKnoepfen
            self.ansicht3d = Ansicht3DMitKnoepfen()
            self.ansicht3d.setMinimumSize(560, 340)
            self.ansicht3d.setToolTip("Das Teil aus der STEP in echter Form und Lage wie im Prüfdialog "
                                      "(goldgelb = Dreh-/Frästeil, Zukauf)")
            self.ansicht3d.setzen(netz, "3D wie in der STEP")
            oben.addWidget(self.ansicht3d, 1)
        lay.addLayout(oben, 1 if netz else 0)
        self.befunde = QLabel()
        self.befunde.setWordWrap(True)
        self.befunde.setTextFormat(Qt.RichText)
        lay.addWidget(self.befunde)
        self.tabelle = QTableWidget(0, len(SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.tabelle.setSelectionMode(QAbstractItemView.SingleSelection)
        for i, b in enumerate((230, 80, 120, 90)):
            self.tabelle.setColumnWidth(i, b)
        lay.addWidget(self.tabelle, 1)
        # eigene Werte je Teil wie beim Blech (Patrick 04.11.2026): leer = berechnet, eingetragen = gilt (gelb)
        from .blech_dialog import RichtwerteTabelle
        self.richtwerte = RichtwerteTabelle(dp.RICHTWERTE, "Richtwerte des Dreh-/Frästeils: berechnet aus Messung, "
                                            "Werkstoff und Einstellungen; ein eigener Wert gilt nur für dieses Teil, "
                                            "„Richtpreis je Stück“ ersetzt den ganzen Preis (z. B. Angebot des "
                                            "Lieferanten). Der Richtpreis rechnet sofort neu.")
        self.richtwerte.eigene_setzen(self.e.get("eigene"))
        self.richtwerte.geaendert.connect(self.neu_rechnen)
        lay.addWidget(self.richtwerte)
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        self.summe.setTextFormat(Qt.RichText)
        lay.addWidget(self.summe)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Als EK übernehmen")
        knoepfe.button(QDialogButtonBox.Ok).setEnabled(not nur_lesen)
        self.zuruecksetzen = QPushButton("Zeiten zurücksetzen")
        knoepfe.addButton(self.zuruecksetzen, QDialogButtonBox.ResetRole)
        self.zuruecksetzen.clicked.connect(self._zuruecksetzen)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        for w in (self.stueck, self.eur_kg, self.zusatz):
            w.valueChanged.connect(self.neu_rechnen)
        self.werkstoff.editingFinished.connect(self.neu_rechnen)
        self.rohling.currentTextChanged.connect(self.neu_rechnen)
        self.tabelle.itemChanged.connect(self._zeit_geaendert)
        self._laedt = False
        self.neu_rechnen()

    def eingaben(self):
        """Eingaben wie gespeichert (positionen.technik)."""
        return dict(self.e, stueck=self.stueck.value(), werkstoff=self.werkstoff.text().strip() or None,
                    rohling=self.rohling.currentText(), eur_kg=self.eur_kg.value() or None,
                    zusatz_eur=self.zusatz.value(), zusatz_text=self.zusatz_text.text().strip(),
                    zeiten=dict(self.e["zeiten"]),
                    eigene=self.richtwerte.eigene() if hasattr(self, "richtwerte") else dict(self.e.get("eigene") or {}))

    def _zuruecksetzen(self):
        self.e["zeiten"] = {}
        self.neu_rechnen()

    def _zeit_geaendert(self, item):
        if self._laedt or item.column() != 2:
            return
        name = self.tabelle.item(item.row(), 0).text()
        try:
            wert = float(item.text().replace(",", "."))
        except ValueError:
            self.neu_rechnen()
            return
        self.e["zeiten"][name] = max(0.0, wert)
        self.neu_rechnen()

    def neu_rechnen(self):
        if self._laedt:
            return
        erg = dp.rechnen(self.eingaben(), self.einst)
        self.ergebnis = erg
        self._laedt = True
        try:
            self.tabelle.setRowCount(len(erg["arbeitsgaenge"]))
            for r, g in enumerate(erg["arbeitsgaenge"]):
                werte = (g["name"], g["verfahren"], _min(g["minuten"]), _eur(g["kosten"]),
                         g["info"] + (f" (gerechnet {_min(g['berechnet'])} min)" if g.get("hand") else ""))
                for c, w in enumerate(werte):
                    it = QTableWidgetItem(w)
                    if c != 2:
                        it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                    else:
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        if g.get("hand"):
                            f = it.font()
                            f.setBold(True)
                            it.setFont(f)
                    if c == 3:
                        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    self.tabelle.setItem(r, c, it)
        finally:
            self._laedt = False
        self.skizze.setzen(self.e.get("daten") or {}, erg)
        if hasattr(self, "richtwerte"):
            self.richtwerte.setzen(erg)
        mb = erg.get("machbarkeit") or ()
        self.befunde.setText(
            f"<b style='color:{AMPEL_FARBE.get(erg.get('ampel') or dp.GRUEN)}'>Machbarkeit: "
            f"{dp.AMPEL_TEXT.get(erg.get('ampel') or dp.GRUEN)}</b>"
            + "".join(f"<br><span style='color:{AMPEL_FARBE[x['stufe']]}'>●</span> {x['text']}" for x in mb))
        if erg["fehler"]:
            self.summe.setText("<b>Kein Richtpreis:</b> " + "; ".join(erg["fehler"]))
            return
        roh = erg["rohling"]
        zeilen = [f"Rohling {roh['text']}, {roh['gewicht']:.2f} kg".replace(".", ",")
                  + f" × {_eur(erg['eur_kg'])}/kg ({dp._gruppe_text(erg)}) + Zuschlag = {_eur(erg['material'])}",
                  f"Bearbeitung {_min(erg['zeit_stueck'])} min je Stück = {_eur(erg['maschine'])}; Rüsten und "
                  f"Programmieren {_min(erg['ruesten_min'])} min je Auftrag = {_eur(erg['ruesten_auftrag'])}, "
                  f"je Stück {_eur(erg['ruesten'])}",
                  f"Zusätze {_eur(erg['zusatz'])}, Aufschlag des Lieferanten {_eur(erg['aufschlag'])}",
                  f"<b>Richtpreis {_eur(erg['richtpreis'])} je Stück</b> – {dp.HINWEIS}"]
        if erg.get("eigene"):
            zeilen.append(f"<span style='color:#1F4E78'>{len(erg['eigene'])} eigene(r) Wert(e) statt Richtwert "
                          "(gelb)</span>")
        if erg["hinweise"]:
            zeilen.append("<i>" + "; ".join(erg["hinweise"]) + "</i>")
        self.summe.setText("<br>".join(zeilen))
