"""Fenster „Materialpreise aus ERP-CSV“ (erp_preise.py, Plan 30.10.2026): Spaltenzuordnung, Prüfliste der ERP-Artikel
mit Ampel, Preise je Profil + Werkstoff mit Verlauf und Übernahme per Haken (vorher Datensicherung)."""
import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QPainter, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from . import erp_preise as E
from . import hilfe, stil
from .kunden_csv_dialog import dateifehler
from .stammdaten import ROH
from .zukauf_preise import _fuellen, _tabelle

AMPEL = {E.GRUEN: "#E2F0D9", E.GELB: "#FFF2CC", E.ROT: "#F8D7DA"}
KEINE = "(keine)"
WEG = "– überspringen –"


def _t(x, stellen=2):
    return "" if x is None else E._t(x, stellen)


def _d(d):
    return d.strftime("%d.%m.%Y") if d else ""


class SpaltenDialog(QDialog):
    """Welche Spalte der CSV ist Kaufdatum, Menge, Meterpreis, Artikelnummer, EK-Artikel; mit Beispielwerten."""

    def __init__(self, parent, kopf, zuordnung, beispiel=()):
        super().__init__(parent)
        self.kopf = kopf
        self.setWindowTitle("Spalten der ERP-CSV zuordnen")
        lay = QVBoxLayout(self)
        t = QLabel("Bitte die Spalten zuordnen. Die Zuordnung wird für Dateien mit gleichem Spaltenkopf gespeichert.")
        t.setWordWrap(True)
        lay.addWidget(t)
        form = QFormLayout()
        self.wahl = {}
        for feld, titel in E.FELDER:
            c = QComboBox()
            c.addItem(KEINE, None)
            for i, k in enumerate(kopf):
                bsp = beispiel[i] if i < len(beispiel) else ""
                c.addItem(f"{k}" + (f"   (z. B. {bsp})" if bsp else ""), i)
            if zuordnung.get(feld) is not None:
                c.setCurrentIndex(zuordnung[feld] + 1)
            self.wahl[feld] = c
            form.addRow(titel + (" *" if feld in E.PFLICHT else ""), c)
        lay.addLayout(form)
        self.fehler = QLabel()
        self.fehler.setStyleSheet("color:#B42318")
        lay.addWidget(self.fehler)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.accepted.connect(self._ok)
        k.rejected.connect(self.reject)
        lay.addWidget(k)

    def zuordnung(self):
        return {f: c.currentData() for f, c in self.wahl.items() if c.currentData() is not None}

    def _ok(self):
        z = self.zuordnung()
        if E.fehlende(z):
            self.fehler.setText("Fehlt: " + ", ".join(E.FELD_TITEL[f] for f in E.fehlende(z)))
        elif len(set(z.values())) < len(z):
            self.fehler.setText("Eine Spalte ist mehrfach zugeordnet.")
        else:
            self.accept()


class VerlaufBild(QWidget):
    """Preis €/m über die Zeit: Punkte je Kauf (rot = zählt nicht), Linie = Durchschnitt."""

    def __init__(self, g):
        super().__init__()
        self.g = g
        self.setMinimumHeight(160)

    def paintEvent(self, _):
        ks = self.g["kaeufe"]
        if not ks:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(50, 10, -10, -24)
        preise = [k["preis"] for k in ks]
        lo, hi = min(preise), max(preise)
        if hi - lo < 0.01:
            lo, hi = lo * 0.95, hi * 1.05
        t0, t1 = ks[0]["datum"].toordinal(), ks[-1]["datum"].toordinal()
        t1 = t1 if t1 > t0 else t0 + 1

        def punkt(d, w):
            return QPointF(r.left() + (d.toordinal() - t0) / (t1 - t0) * r.width(),
                           r.bottom() - (w - lo) / (hi - lo) * r.height())
        grau = stil.farbe("#8A94A3")
        p.setPen(QPen(grau, 1))
        p.drawRect(r)
        for w in (lo, hi):
            p.drawText(QPointF(4, punkt(ks[0]["datum"], w).y() + 4), _t(w))
        p.drawText(QPointF(r.left(), r.bottom() + 16), _d(ks[0]["datum"]))
        p.drawText(QPointF(r.right() - 70, r.bottom() + 16), _d(ks[-1]["datum"]))
        if self.g.get("durchschnitt"):
            p.setPen(QPen(stil.farbe("#1F4E78"), 1, Qt.DashLine))
            y = punkt(ks[0]["datum"], self.g["durchschnitt"]).y()
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        p.setPen(QPen(grau, 1))
        p.drawPolyline([punkt(k["datum"], k["preis"]) for k in ks])
        for k in ks:
            p.setBrush(QBrush(stil.farbe("#1F4E78" if k["gerechnet"] else "#B42318")))
            p.drawEllipse(punkt(k["datum"], k["preis"]), 4, 4)
        p.end()


class VerlaufDialog(QDialog):
    """Käufe einer Gruppe mit Verlauf; Haken „zählt“ je Kauf (3a: Ausreißer von Hand mitrechnen oder weglassen)."""
    SPALTEN = ("Zählt", "Kaufdatum", "Menge [m]", "€/m", "Artikelnummer", "EK-Artikel", "Hinweis")

    def __init__(self, parent, db, g):
        super().__init__(parent)
        self.db, self.g = db, g
        self.setWindowTitle(f"Einkaufsverlauf {g['profil_id']} {g['werkstoff_id']} {g['oberflaeche']}".strip())
        self.resize(900, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Ø {_t(g['durchschnitt'])} €/m aus {g['anzahl']} Käufen ({_t(g['meter'], 0)} m) · "
                             f"letzter {_t(g['letzter'])} €/m am {_d(g['letzter_datum'])} · heute in den Stammdaten "
                             f"{_t(g['heute']) or '–'} €/m ({g['herkunft']})"))
        lay.addWidget(VerlaufBild(g))
        self.tabelle = _tabelle(self.SPALTEN, (50, 85, 75, 70, 110, 260))
        lay.addWidget(self.tabelle, 1)
        self.geaendert = False
        rechts = (2, 3)
        _fuellen(self.tabelle, [("", _d(k["datum"]), _t(k["menge"], 1), _t(k["preis"]), k["artikelnr"],
                                 k["bezeichnung"], "außerhalb des Zeitraums" if not k["im_zeitraum"] else
                                 ("Ausreißer" if k["ausreisser"] else "") +
                                 (" (von Hand)" if k.get("rechnen") is not None else ""))
                                for k in g["kaeufe"]], rechts=rechts)
        for r, k in enumerate(g["kaeufe"]):
            it = self.tabelle.item(r, 0)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if k["gerechnet"] else Qt.Unchecked)
            if not k["im_zeitraum"]:
                it.setFlags(it.flags() & ~Qt.ItemIsEnabled)
        self.tabelle.itemChanged.connect(self._haken)
        k = QDialogButtonBox(QDialogButtonBox.Close)
        k.button(QDialogButtonBox.Close).setText("Schließen")
        auto = k.addButton("Ausreißer automatisch", QDialogButtonBox.ResetRole)
        auto.setToolTip("Eigene Haken zurücknehmen: Ausreißer zählen wieder automatisch nicht")
        auto.clicked.connect(self.automatisch)
        k.rejected.connect(self.accept)
        lay.addWidget(k)

    def _haken(self, it):
        if it.column() != 0:
            return
        kauf = self.g["kaeufe"][it.row()]
        E.kauf_rechnen(self.db, kauf["id"], it.checkState() == Qt.Checked)
        self.geaendert = True

    def automatisch(self):
        for kauf in self.g["kaeufe"]:
            E.kauf_rechnen(self.db, kauf["id"], None)
        self.geaendert = True
        self.accept()


class ErpPreiseDialog(QDialog):
    """Prüfliste und Preise aus allen gespeicherten Käufen; Änderungen an der Zuordnung werden sofort gemerkt."""
    ARTIKEL = ("Ampel", "Artikelnummer", "EK-Artikel", "Käufe", "Meter", "Profil", "Werkstoff", "Oberfläche", "Hinweis")
    PREISE = ("Übernehmen", "Profil", "Werkstoff", "Oberfläche", "Käufe", "Meter", "Ø €/m (Vorschlag)", "≙ €/kg",
              "letzter €/m", "Min – Max", "Ausreißer", "heute €/m", "Abweichung")

    def __init__(self, parent, db, meldung="", heute=None):
        super().__init__(parent)
        self.db, self.heute = db, heute
        self.haken_hand = {}            # (Profil, Werkstoff, Oberfläche) -> True/False von Hand
        self.ergebnis = None
        self.setWindowTitle("Materialpreise aus ERP-CSV")
        self.resize(1400, 720)
        lay = QVBoxLayout(self)
        lay.addWidget(hilfe.Hinweis(
            "Je ERP-Artikel erkennt das Programm Profil, Werkstoff und Oberfläche aus der Bezeichnung. Grün = "
            "eindeutig, gelb = bitte Werkstoff bzw. Oberfläche wählen, rot = Profil fehlt (anlegen oder "
            "überspringen). Jede Wahl wird je ERP-Artikel gemerkt. Unter „Preise“ steht je Profil + Werkstoff der "
            "gewichtete Durchschnitt nach Menge; Doppelklick zeigt den Verlauf. „Übernehmen“ schreibt die "
            "angehakten Preise als €/m in die Stammdaten (vorher Datensicherung); verschickte Angebote behalten "
            "ihre festgeschriebenen Preise. Die Käufe bleiben nur an diesem Arbeitsplatz.", schluessel="erp_preise"))
        self.kopf = QLabel(meldung)
        self.kopf.setWordWrap(True)
        lay.addWidget(self.kopf)
        self.reiter = QTabWidget()
        seite_a = QWidget()
        la = QVBoxLayout(seite_a)
        self.artikel_tab = _tabelle(self.ARTIKEL, (60, 110, 300, 50, 70, 150, 140, 120))
        la.addWidget(self.artikel_tab, 1)
        leiste = QHBoxLayout()
        self.anlegen_knopf = QPushButton("Profil anlegen …")
        self.anlegen_knopf.setToolTip("Fehlendes Profil des markierten ERP-Artikels mit den erkannten Maßen anlegen")
        self.anlegen_knopf.clicked.connect(lambda: self.profil_anlegen())
        vergessen = QPushButton("Zuordnung vergessen")
        vergessen.setToolTip("Gemerkte Zuordnung des markierten ERP-Artikels löschen: er wird wieder aus der "
                             "Bezeichnung erkannt")
        vergessen.clicked.connect(lambda: self.vergessen())
        self.nur_offen = QCheckBox("Nur gelbe und rote")
        self.nur_offen.toggled.connect(lambda _: self._artikel_filtern())
        for w in (self.anlegen_knopf, vergessen, self.nur_offen):
            leiste.addWidget(w)
        leiste.addStretch(1)
        la.addLayout(leiste)
        seite_p = QWidget()
        lp = QVBoxLayout(seite_p)
        self.preis_tab = _tabelle(self.PREISE, (85, 120, 110, 95, 50, 60, 130, 60, 140, 110, 75, 75))
        self.preis_tab.cellDoubleClicked.connect(lambda r, _c: self.verlauf(r))
        self.preis_tab.itemChanged.connect(self._preis_haken)
        lp.addWidget(self.preis_tab, 1)
        self.aufpreis = QLabel()
        self.aufpreis.setWordWrap(True)
        lp.addWidget(self.aufpreis)
        self.reiter.addTab(seite_a, "Prüfliste ERP-Artikel")
        self.reiter.addTab(seite_p, "Preise")
        lay.addWidget(self.reiter, 1)
        k = QDialogButtonBox(QDialogButtonBox.Close)
        k.button(QDialogButtonBox.Close).setText("Schließen")
        self.uebernehmen_knopf = k.addButton("Übernehmen", QDialogButtonBox.AcceptRole)
        self.uebernehmen_knopf.setToolTip("Angehakte Preise als €/m in Stammdaten → Preise schreiben, vorher "
                                          "Datensicherung")
        self.uebernehmen_knopf.clicked.connect(lambda: self.uebernehmen())
        k.rejected.connect(self.reject)
        lay.addWidget(k)
        self.neu_rechnen()
        self.reiter.setCurrentIndex(0 if any(a["ampel"] != E.GRUEN for a in self.artikel) else 1)

    # ---------------------------------------------------------------- Rechnen
    def neu_rechnen(self):
        self.k, self.tabellen = self.db.kontext(), self.db.tabellen()
        e = self.db.einstellungen()
        self.kaeufe = E.gespeicherte(self.db)
        self.artikel = E.artikel(self.kaeufe, E.zuordnungen(self.db), self.k)
        self.gruppen = E.auswerten(self.kaeufe, self.artikel, self.k, self.tabellen, self.heute,
                                   monate=e.get("erp_monate") or 12, grenze=e.get("erp_ausreisser") or 0.25,
                                   schwelle=e.get("erp_schwelle") or 0.02)
        for g in self.gruppen:
            schl = (g["profil_id"], g["werkstoff_id"], g["oberflaeche"])
            if schl in self.haken_hand and not g["oberflaeche"] and g["durchschnitt"]:
                g["haken"] = self.haken_hand[schl]
        self._artikel_zeigen()
        self._preise_zeigen()

    def _artikel_zeigen(self):
        t = self.artikel_tab
        t.setRowCount(0)
        _fuellen(t, [(a["ampel"], a["artikelnr"], a["bezeichnung"], a["kaeufe"], _t(a["meter"], 1), "", "", "",
                      a["hinweis"]) for a in self.artikel], rechts=(3, 4))
        profile = [""] + sorted(self.k.profile, key=str.lower)
        werkstoffe = [""] + sorted(self.k.werkstoffe, key=str.lower)
        oberflaechen = [ROH] + sorted(o for o in self.k.oberflaechen if o.lower() != ROH)
        for r, a in enumerate(self.artikel):
            for c in range(len(self.ARTIKEL)):
                t.item(r, c).setBackground(QBrush(stil.farbe(AMPEL[a["ampel"]])))
            pc = QComboBox()
            pc.addItems(profile + [WEG])
            pc.setCurrentText(WEG if a.get("ignorieren") else (a["profil_id"] or ""))
            pc.setToolTip("Profil aus den Stammdaten; „– überspringen –“ = Artikel nie auswerten (z. B. kein Rohr)")
            wc = QComboBox()
            wc.addItems(werkstoffe)
            wc.setCurrentText(a["werkstoff_id"] or "")
            if a.get("kandidaten") and not a["werkstoff_id"]:
                wc.setToolTip("Passend: " + ", ".join(a["kandidaten"]))
            oc = QComboBox()
            oc.addItems(oberflaechen + ([a["oberflaeche"]] if a["oberflaeche"] and a["oberflaeche"] not in
                                        oberflaechen else []))
            oc.setCurrentText(a["oberflaeche"] or ROH)
            for c, box in ((5, pc), (6, wc), (7, oc)):
                box.currentTextChanged.connect(lambda _t, r=r: self.zuordnung_geaendert(r))
                t.setCellWidget(r, c, box)
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self._artikel_filtern()

    def _artikel_filtern(self):
        for r, a in enumerate(self.artikel):
            self.artikel_tab.setRowHidden(r, self.nur_offen.isChecked() and a["ampel"] == E.GRUEN)

    def _preise_zeigen(self):
        t = self.preis_tab
        t.blockSignals(True)
        t.setRowCount(0)
        _fuellen(t, [("", g["profil_id"], g["werkstoff_id"], g["oberflaeche"] or ROH, g["anzahl"], _t(g["meter"], 0),
                      _t(g["durchschnitt"]), _t(g["durchschnitt"] / g["kg_m"], 2) if g["durchschnitt"] and g["kg_m"]
                      else "", f"{_t(g['letzter'])} ({_d(g['letzter_datum'])})",
                      f"{_t(g['min'])} – {_t(g['max'])}" if g["min"] is not None else "", g["ausreisser"] or "",
                      _t(g["heute"]), f"{g['abweichung'] * 100:+.1f} %".replace(".", ",")
                      if g["abweichung"] is not None else ("" if g["oberflaeche"] else "neu"))
                     for g in self.gruppen],
                 rechts=(4, 5, 6, 7, 8, 10, 11, 12))
        for r, g in enumerate(self.gruppen):
            it = t.item(r, 0)
            if g["oberflaeche"] or not g["durchschnitt"]:
                it.setText("nur Info" if g["oberflaeche"] else "keine Käufe im Zeitraum")
                it.setToolTip("Preise mit Oberfläche gehen nicht in „Preise“ (nur Rohware); sie ergeben den "
                              "Aufpreis-Vorschlag unten" if g["oberflaeche"] else "")
            else:
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(Qt.Checked if g["haken"] else Qt.Unchecked)
            t.item(r, 11).setToolTip(g["herkunft"])
            if g["abweichung"] is not None and abs(g["abweichung"]) > 0.10:
                t.item(r, 12).setForeground(QBrush(stil.farbe("#B42318")))
        t.blockSignals(False)
        auf = E.aufpreise(self.gruppen, self.k)
        self.aufpreis.setText(
            "Aufpreis-Vorschlag aus Käufen mit Oberfläche (nur Hinweis, Stammdaten → Oberflächen bleiben): " +
            "; ".join(f"<b>{a['oberflaeche']}</b> {_t(a['aufpreis_kg'])} €/kg aus {a['profile']} Profil(en), "
                      f"{_t(a['meter'], 0)} m" + (f" (heute {a['heute']})" if a["heute"] else "") for a in auf)
            if auf else "")
        self.uebernehmen_knopf.setEnabled(any(g["haken"] for g in self.gruppen if not g["oberflaeche"]))
        self.reiter.setTabText(1, f"Preise ({sum(1 for g in self.gruppen if g['haken'] and not g['oberflaeche'])} "
                                  f"angehakt)")
        offen = sum(1 for a in self.artikel if a["ampel"] != E.GRUEN)
        self.reiter.setTabText(0, "Prüfliste ERP-Artikel" + (f" ({offen} offen)" if offen else ""))

    # ---------------------------------------------------------------- Aktionen
    def _preis_haken(self, it):
        if it.column() != 0 or not (it.flags() & Qt.ItemIsUserCheckable):
            return
        g = self.gruppen[it.row()]
        g["haken"] = it.checkState() == Qt.Checked
        self.haken_hand[(g["profil_id"], g["werkstoff_id"], g["oberflaeche"])] = g["haken"]
        self.uebernehmen_knopf.setEnabled(any(x["haken"] for x in self.gruppen if not x["oberflaeche"]))

    def zuordnung_geaendert(self, r):
        a = self.artikel[r]
        t = self.artikel_tab
        profil, werkstoff, ober = (t.cellWidget(r, c).currentText() for c in (5, 6, 7))
        if profil == WEG:
            E.zuordnung_merken(self.db, a["schluessel"], a["artikelnr"], a["bezeichnung"], ignorieren=True)
        elif profil and werkstoff:
            E.zuordnung_merken(self.db, a["schluessel"], a["artikelnr"], a["bezeichnung"], profil, werkstoff,
                               "" if ober == ROH else ober)
        else:
            return                      # noch unvollständig: erst merken, wenn Profil und Werkstoff gewählt sind
        self.neu_rechnen()

    def setzen(self, r, profil=None, werkstoff=None, oberflaeche=None):
        """Für Tests: Zelle der Prüfliste wählen wie von Hand."""
        for c, w in ((5, profil), (6, werkstoff), (7, oberflaeche)):
            if w is not None:
                self.artikel_tab.cellWidget(r, c).setCurrentText(w)

    def _markiert(self):
        rows = self.artikel_tab.selectionModel().selectedRows()
        return rows[0].row() if rows else None

    def profil_anlegen(self, r=None, werte=None):
        """Profil des ERP-Artikels anlegen (8a): Fenster Neues Profil mit den erkannten Maßen (werte = ohne Fenster)."""
        r = self._markiert() if r is None else r
        a = self.artikel[r] if r is not None else None
        if a is None or a.get("profil_id") or not a.get("vorschlag"):
            QMessageBox.information(self, "Profil anlegen", "Bitte einen roten ERP-Artikel mit erkannter Abmessung "
                                    "markieren.")
            return None
        if werte is None:
            from .profil_neu import ProfilNeuDialog
            d = ProfilNeuDialog(self, self.k.profile, eingabe=a["vorschlag"]["profil_id"],
                                bemerkung="aus ERP-Preisimport angelegt")
            if d.exec() != QDialog.Accepted:
                return None
            werte = d.werte()
        if werte["profil_id"] in self.k.profile:
            QMessageBox.information(self, "Profil anlegen", f"{werte['profil_id']} gibt es schon.")
            return None
        self.db.neu("profile", werte)
        self.neu_rechnen()
        return werte["profil_id"]

    def vergessen(self, r=None):
        r = self._markiert() if r is None else r
        if r is not None:
            E.zuordnung_vergessen(self.db, [self.artikel[r]["schluessel"]])
            self.neu_rechnen()

    def verlauf(self, r, zeigen=True):
        d = VerlaufDialog(self, self.db, self.gruppen[r])
        if zeigen:
            d.exec()
        if d.geaendert or not zeigen:
            self.neu_rechnen()
        return d

    def uebernehmen(self, frage=True):
        wahl = [g for g in self.gruppen if g["haken"] and not g["oberflaeche"] and g["durchschnitt"]]
        if not wahl:
            return None
        if frage and QMessageBox.question(
                self, "Preise übernehmen", f"{len(wahl)} Preis(e) als €/m in Stammdaten → Preise schreiben? Vorher "
                "wird eine Datensicherung angelegt.") != QMessageBox.Yes:
            return None
        for a in self.artikel:          # erkannte (grüne) Zuordnungen merken: nächster Import ohne Rückfrage
            if a["ampel"] == E.GRUEN and not a["gemerkt"] and a["profil_id"] and a["werkstoff_id"]:
                E.zuordnung_merken(self.db, a["schluessel"], a["artikelnr"], a["bezeichnung"], a["profil_id"],
                                   a["werkstoff_id"], a["oberflaeche"])
        self.ergebnis = E.uebernehmen(self.db, wahl, self.heute)
        self.haken_hand.clear()
        self.neu_rechnen()
        self.kopf.setText(f"Übernommen: {self.ergebnis[0]} Preis(e) neu, {self.ergebnis[1]} geändert. Sicherung "
                          f"vorher: {self.ergebnis[2]}")
        return self.ergebnis


def importieren(seite, db, pfad=None, zuordnung=None, zeigen=True, heute=None):
    """Datei wählen, Spalten zuordnen (gespeicherte Vorlage, sonst Vorschlag, fehlt etwas: Fenster), Käufe speichern
    und das Fenster zeigen. zuordnung/zeigen=False für Tests. Ergebnis: ErpPreiseDialog oder None."""
    if pfad is None:
        f = seite.window()
        start = f.ablage() if hasattr(f, "ablage") else Path.home()
        pfad, _ = QFileDialog.getOpenFileName(seite, "ERP-Einkaufsdaten laden", str(start), "CSV (*.csv *.txt)")
        if not pfad:
            return None
    try:
        roh = Path(pfad).read_bytes()
    except OSError as e:
        raise OSError(dateifehler(e, pfad)) from e
    daten = E.lesen(roh)
    vorlagen = db.einstellung(E.VORLAGEN) or {}
    if zuordnung is None:
        zuordnung, gespeichert = E.zuordnung_fuer(daten["kopf"], vorlagen)
        if E.fehlende(zuordnung) or (zeigen and not gespeichert and len(zuordnung) < len(E.FELDER)):
            if not zeigen:
                raise E.ErpFehler("Spalten nicht erkannt: " + ", ".join(E.FELD_TITEL[f] for f in E.fehlende(zuordnung)))
            d = SpaltenDialog(seite, daten["kopf"], zuordnung, daten["zeilen"][0] if daten["zeilen"] else ())
            if d.exec() != QDialog.Accepted:
                return None
            zuordnung = d.zuordnung()
    vorlagen[E.vorlage_schluessel(daten["kopf"])] = zuordnung
    db.einstellung_setzen(E.VORLAGEN, vorlagen)
    liste, meldungen = E.kaeufe(daten, zuordnung)
    if not liste:
        raise E.ErpFehler("Keine lesbaren Käufe in der Datei. " + "; ".join(meldungen[:3]))
    neu = E.speichern(db, liste, Path(pfad).name)
    text = (f"<b>{Path(pfad).name}</b>: {len(liste)} Käufe gelesen, davon {neu} neu gespeichert"
            f"{f' ({len(liste) - neu} schon vorhanden)' if neu < len(liste) else ''}; Zeitraum "
            f"{_d(min(k['datum'] for k in liste))} – {_d(max(k['datum'] for k in liste))}.")
    if meldungen:
        text += f" <span style='color:#B42318'>{len(meldungen)} Zeile(n) übersprungen: " + \
            "; ".join(meldungen[:3]) + (" …" if len(meldungen) > 3 else "") + "</span>"
    d = ErpPreiseDialog(seite, db, text, heute=heute or datetime.date.today())
    d.meldungen = meldungen
    if zeigen:
        d.exec()
    return d
