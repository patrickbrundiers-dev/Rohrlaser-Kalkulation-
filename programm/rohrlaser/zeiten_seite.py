"""Reiter 'Zeiten & Arbeitskosten' im Angebot: Zeit, Stundensatz und Kosten je Arbeitsschritt.

Die Werte kommen aus rechnen.kalkulation (summen['zeiten']), also aus derselben Rechnung wie Herstellkosten und
Verkaufspreis. Änderungen hier (Rüstzeit und Zeit je Einheit der weiteren Arbeitsschritte, Stundensätze) gelten nur
für dieses Angebot und stehen in seinem Snapshot der Stundensätze und Zeitvorgaben.
"""
import copy

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QScrollArea, QSplitter, QTableView, QVBoxLayout, QWidget)

from . import rechnen
from .fenster import FARBE_BERECHNET, FARBE_EINGABE
from .spaltenbreite import AutoGroesse
from .sichtbarkeit import ohne_wert
from .stammdaten import SATZ_MASCHINE, Feld, wert_aus_text, zahl_als_text

SPALTEN = (("Arbeitsschritt", 180), ("Art", 130), ("Menge", 110), ("Rüstzeit", 75), ("Zeit je Einheit", 90),
           ("Gesamtzeit", 85), ("Stundensatz [€/h]", 140), ("Kosten [€]", 85), ("Quelle", 210), ("Berechnung", 380))
F_RUEST = Feld("ruestzeit", "Rüstzeit [min]", "zahl", 0, 100000, stellen=1)
F_ZEIT = Feld("zeit", "Zeit je Einheit [s]", "zahl", 0, 100000, stellen=1)
F_SATZ = Feld("satz", "Stundensatz [€/h]", "zahl", 0, 10000, stellen=2)


def _z(w, stellen=2):
    return zahl_als_text(w, stellen) if isinstance(w, (int, float)) and not isinstance(w, bool) else ""


zeile_sichtbar = rechnen.schritt_sichtbar


class ZeitenModell(QAbstractTableModel):
    def __init__(self, seite):
        super().__init__()
        self.seite = seite
        self.zeilen = []

    def setzen(self, zeilen):
        self.beginResetModel()
        self.zeilen = list(zeilen)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.zeilen)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(SPALTEN)

    def headerData(self, abschnitt, richtung, rolle=Qt.DisplayRole):
        if rolle == Qt.DisplayRole:
            return SPALTEN[abschnitt][0] if richtung == Qt.Horizontal else str(abschnitt + 1)
        return None

    def bearbeitbar(self, r, c):
        z = self.zeilen[r]
        if c in (3, 4):
            return not z["fest"]
        return c == 6 and z["satz_id"] is not None

    def text(self, r, c):
        z = self.zeilen[r]
        if c == 0:
            return z["schritt"]
        if c == 1:
            return z["art"] + (" (parallel)" if z["parallel"] and z["art"] != "Maschine" else "")
        if 2 <= c <= 6:
            return rechnen.schritt_texte(z)[c - 2]
        if c == 7:
            return _z(z["kosten"])
        return z["quelle"] if c == 8 else z["formel"]

    def data(self, index, rolle=Qt.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        z = self.zeilen[r]
        if rolle in (Qt.DisplayRole, Qt.ToolTipRole):
            t = self.text(r, c)
            if rolle == Qt.ToolTipRole and self.bearbeitbar(r, c):
                t += ("\nDoppelklick: Stundensatz für dieses Angebot ändern (gilt für alle Schritte mit diesem Satz)"
                      if c == 6 else "\nDoppelklick: Wert für dieses Angebot ändern")
            return t
        if rolle == Qt.EditRole:
            return {3: _z(z.get("ruest_einzeln") or 0, 1),
                    4: _z(z["zeit_einheit_s"] or 0, 1), 6: _z(z["satz"])}.get(c, "")
        if rolle == Qt.TextAlignmentRole and 2 <= c <= 7:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if rolle == Qt.BackgroundRole:
            return QBrush(FARBE_EINGABE if self.bearbeitbar(r, c) else FARBE_BERECHNET)
        if rolle == Qt.ForegroundRole and z["gesamt_min"] is None and c in (5, 6):
            return QBrush(QColor("#5F6B7A"))
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.isValid() and self.bearbeitbar(index.row(), index.column()):
            f |= Qt.ItemIsEditable
        return f

    def setData(self, index, text, rolle=Qt.EditRole):
        if rolle != Qt.EditRole or not index.isValid():
            return False
        r, c = index.row(), index.column()
        try:
            w = wert_aus_text({3: F_RUEST, 4: F_ZEIT, 6: F_SATZ}[c], text)
        except ValueError as e:
            self.seite.f.meldung(str(e), fehler=True)
            return False
        self.seite.zeiten_seite.aendern(self.zeilen[r], c, w or 0.0)
        return True


class ZeitenSeite(QWidget):
    def __init__(self, seite):
        super().__init__()
        self.s = seite
        self.modell = ZeitenModell(seite)
        self.ansicht = QTableView()
        self.ansicht.setModel(self.modell)
        self.ansicht.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                     | QAbstractItemView.AnyKeyPressed)
        self.ansicht.verticalHeader().setDefaultSectionSize(22)
        self.ansicht.verticalHeader().hide()        # Zeilennummern wären wegen ausgeblendeter Schritte lückenhaft
        kopf = self.ansicht.horizontalHeader()
        kopf.setStretchLastSection(True)
        for i, (_, b) in enumerate(SPALTEN):
            self.ansicht.setColumnWidth(i, b)
        AutoGroesse(self.ansicht, max_breite=420)
        self.alle = QCheckBox("Alle Arbeitsschritte zeigen")
        self.alle.setToolTip("Auch Arbeitsschritte ohne Zeit und Kosten zeigen, z. B. um eine Zeit einzutragen")
        self.alle.toggled.connect(self._zeilen_zeigen)
        self.uebernehmen = QPushButton("Stundensätze aus Einstellungen")
        self.uebernehmen.setToolTip("Stundensätze und Zeitvorgaben dieses Angebots auf die aktuellen Einstellungen "
                                    "setzen (Stammdaten Stundensätze, Arbeitsschritte, Maschine)")
        self.uebernehmen.clicked.connect(lambda: self.aus_einstellungen())
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.summen = QLabel()
        self.summen.setTextInteractionFlags(Qt.TextSelectableByMouse)
        leiste = QHBoxLayout()
        leiste.addWidget(self.alle)
        leiste.addSpacing(16)
        leiste.addWidget(self.uebernehmen)
        leiste.addSpacing(16)
        leiste.addWidget(self.hinweis, 1)
        self.summen.setWordWrap(True)
        self.summen.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        rechts = QScrollArea()
        rechts.setWidget(self.summen)
        rechts.setWidgetResizable(True)
        rechts.setFrameShape(QFrame.NoFrame)
        rechts.setMinimumWidth(300)
        teiler = QSplitter(Qt.Horizontal)          # links die Schritte, rechts die Summen
        teiler.addWidget(self.ansicht)
        teiler.addWidget(rechts)
        teiler.setStretchFactor(0, 1)
        teiler.setSizes([1400, 420])
        lay = QVBoxLayout(self)
        lay.addLayout(leiste)
        lay.addWidget(teiler, 1)

    def setzen(self, summen):
        zeiten = summen["zeiten"]
        self.modell.setzen(zeiten)
        self._zeilen_zeigen()
        gespeichert = summen.get("zeitbasis_gespeichert")
        self.hinweis.setText(
            "Stundensätze und Zeitvorgaben sind in diesem Angebot gespeichert; spätere Änderungen in den "
            "Einstellungen ändern es nicht. Gelbe Felder gelten nur für dieses Angebot." if gespeichert else
            "<span style='color:#7A5A00'><b>Stundensätze nicht im Angebot gespeichert</b> (älteres Angebot): es gelten "
            "die aktuellen Einstellungen. „Stundensätze aus Einstellungen“ speichert sie im Angebot.</span>")
        k = rechnen.zeit_summen(zeiten)
        wert = {n: w for (_, w, _), (_, n, _) in zip(rechnen.kostenarten(summen, self.s.einst), rechnen.KOSTENARTEN)}
        zuschlaege = wert["zuschlag_material"] + wert["zuschlag_fertigung"] + wert["zuschlag_fremdleistung"]
        zeilen = [("Maschinenzeit", rechnen.zeit_text(k["maschine_min"]), False),
                  ("Personalzeit", rechnen.zeit_text(k["personal_min"]), False),
                  ("Rüstzeit", rechnen.zeit_text(k["ruest_min"]), False),
                  ("Bearbeitungszeit gesamt", rechnen.zeit_text(k["bearbeitung_min"]), False),
                  ("Durchlaufzeit (parallele Personalzeit nicht addiert)", rechnen.zeit_text(k["durchlauf_min"]), False),
                  ("Arbeitskosten", f"{_z(k['arbeitskosten'])} €", True),
                  ("davon Maschinenkosten", f"{_z(k['maschinenkosten'])} €", False),
                  ("davon Personalkosten", f"{_z(k['personalkosten'])} €", False),
                  ("Materialkosten", f"{_z(wert['material'])} €", False),
                  ("Kosten ohne Zeit (Festpreise, Zusatzarbeiten)", f"{_z(k['sonstige'])} €", False),
                  ("Zuschläge", f"{_z(zuschlaege)} €", False),
                  ("Herstellkosten", f"{_z(summen['herstell'])} €", True), ("Gewinn", f"{_z(wert['gewinn'])} €", False),
                  ("Verkaufspreis", f"{_z(summen['verkauf'])} €", True)]
        roh = dict(Maschinenzeit=k["maschine_min"], Personalzeit=k["personal_min"], Rüstzeit=k["ruest_min"])
        html = "<table cellpadding='1'>"
        for t, w, fett in zeilen:
            if t in roh and ohne_wert(roh[t]) or t.startswith("davon") and ohne_wert(w) \
                    or t.startswith(("Kosten ohne", "Zuschläge", "Gewinn")) and ohne_wert(w):
                continue
            html += (f"<tr><td>{'<b>' + t + '</b>' if fett else t}</td><td width='12'></td>"
                     f"<td align='right'>{'<b>' + w + '</b>' if fett else w}</td></tr>")
        self.summen.setText(html + "</table><span style='color:#5F6B7A'>Zeiten aus Schneiddaten, Maschinen und "
                            "Arbeitsschritten; ohne bestätigte Betriebsdaten sind es Vorgabewerte, keine gemessenen "
                            "Zeiten.</span>")

    def _zeilen_zeigen(self):
        for r, z in enumerate(self.modell.zeilen):
            self.ansicht.setRowHidden(r, not (self.alle.isChecked() or zeile_sichtbar(z)))
        self.ansicht.auto_groesse.spaeter()

    # -------------------------------------------------------------- Ändern (Snapshot des Angebots)
    def _zeitbasis(self):
        s = self.s
        zb = s.kopf.get("zeitbasis")
        return copy.deepcopy(zb) if isinstance(zb, dict) else s.db.zeitbasis_vorgabe(s.kopf.get("maschine"))

    def aendern(self, z, spalte, wert):
        """Rüstzeit (Spalte 3, min) bzw. Zeit je Einheit (4, s) eines weiteren Arbeitsschritts oder den Stundensatz
        (6, €/h) für dieses Angebot ändern."""
        s = self.s
        zb = self._zeitbasis()
        if spalte == 6:
            if z["satz_id"] == SATZ_MASCHINE:
                zb["maschine"]["stundensatz"] = wert
            else:
                zb["saetze"][z["satz_id"]] = wert
            text = f"Stundensatz {z['satz_id']} für dieses Angebot gespeichert."
        else:
            for x in zb["schritte"]:
                if x.get("schritt") == z["schritt"]:
                    x["ruestzeit" if spalte == 3 else "zeit"] = wert
            text = f"{z['schritt']}: {'Rüstzeit' if spalte == 3 else 'Zeit je Einheit'} für dieses Angebot gespeichert."
        s.db.zeitbasis_speichern(s.id, zb)
        s.f.meldung(text)
        s.neu_laden()

    def aus_einstellungen(self):
        s = self.s
        if not s.f.stumm and QMessageBox.question(
                self, "Stundensätze", "Stundensätze und Zeitvorgaben dieses Angebots auf die aktuellen Einstellungen "
                "setzen? Eigene Werte dieses Angebots gehen dabei verloren.") != QMessageBox.Yes:
            return False
        s.db.zeitbasis_speichern(s.id, s.db.zeitbasis_vorgabe(s.kopf.get("maschine")))
        s.f.meldung("Stundensätze und Zeitvorgaben aus den Einstellungen übernommen.")
        s.neu_laden()
        return True
