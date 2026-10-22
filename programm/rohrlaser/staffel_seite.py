"""Reiter 'Staffeln' im Angebot: Mengenstufen mit eigenen Werten (Materialzuschlag, Gewinn, Nebenkosten …) und
Ergebnis je Stufe mit allen Kostenpositionen bis zum Bruttopreis.

Rechnung in staffeln.py: der Mengenlauf (Optimierung je Stufe) läuft nach Änderungen an Mengen, Positionen oder
Stammdaten automatisch im Hintergrund, die Preisschicht (Zuschläge, Gewinn, Nebenkosten) sofort bei jeder Eingabe.
"""
import copy
import datetime
import threading

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressDialog, QPushButton,
                               QSplitter, QTableView, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from . import fracht_angebot, hilfe, staffeln, stil
from .fenster import FARBE_BERECHNET, FARBE_EINGABE, FARBE_STATUS
from .spaltenbreite import AutoGroesse
from .sichtbarkeit import ohne_wert
from .staffeln import EURO, PROZENT, UMLEGEN
from .stammdaten import Feld, wert_aus_text, zahl_als_text

GRAU = QColor(stil.TEXT_GRAU)
FARBE_SUMME = QColor("#DDEBF7")
ZEILENHOEHE = 20


def _z(w, stellen=2):
    return zahl_als_text(w, stellen) if isinstance(w, (int, float)) and not isinstance(w, bool) else ""


def _zeit(iso):
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return ""


def angebotspreise(positionen, zeilen):
    """Preis je Einheit im Angebot (Hauptmenge): je Position ohne Satz der Stückpreis, je Satz die Summe der
    Stückpreise × Stück je Satz (wie im Angebots-PDF). zeilen = rechnen.kalkulation(...)[0]."""
    out = {}
    for p, z in zip(positionen, zeilen):
        if not z or not staffeln.position_aktiv(p) or not isinstance(z.get("preis_teil"), (int, float)):
            continue
        satz = staffeln.txt(p.get("satz"))
        if satz:
            out[satz] = out.get(satz, 0.0) + z["preis_teil"] * staffeln.je_satz(p)
        elif staffeln.txt(p.get("pos")):
            out[staffeln.txt(p.get("pos"))] = z["preis_teil"]
    return out


# ------------------------------------------------------------------ Stufentabelle (Übersicht)
STUFEN_SPALTEN = ("Stufe", "Bezeichnung", "Mengen", "Eigene Werte", "Netto gesamt [€]", "Prüfung")
PRUEFUNG = len(STUFEN_SPALTEN) - 1


class StufenModell(QAbstractTableModel):
    """Stufen der Staffelpreise, eine Zeile je Stufe (nur Anzeige; Doppelklick öffnet das Fenster der Stufe)."""

    def __init__(self, seite):
        super().__init__()
        self.s, self.daten = seite, []

    def setzen(self, daten):
        self.beginResetModel()
        self.daten = daten
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.daten)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(STUFEN_SPALTEN)

    def headerData(self, abschnitt, richtung, rolle=Qt.DisplayRole):
        if rolle == Qt.DisplayRole:
            return STUFEN_SPALTEN[abschnitt] if richtung == Qt.Horizontal else str(abschnitt + 1)
        return None

    def mengen(self, st):
        return [z for z in self.s.s.stufen if z.get("stufe_id") == st["id"]]

    def zeilen(self, st):
        return [z for z in self.s.zeilen if z.get("stufe") == st["id"]]

    def text(self, r, c):
        st = self.daten[r]
        if c == 0:
            return f"Stufe {r + 1}"
        if c == 1:
            return st.get("bezeichnung") or ""
        if c == 2:
            return mengen_text(self.mengen(st), self.s.s.positionen) or "keine Mengen"
        if c == 3:
            return eigene_werte(st) or "wie Angebot"
        if c == 4:
            z = self.zeilen(st)
            return _z(sum(x["preis_gesamt"] for x in z)) if z and all(x.get("preis_gesamt") is not None for x in z) else ""
        return self.pruefung(st)

    def pruefung(self, st):
        mz = self.mengen(st)
        if not staffeln.gueltige(mz):
            return "FEHLER: keine Menge eingetragen"
        hinweise = [x.get("hinweis") or "" for x in self.zeilen(st)]
        fehler = next((h for h in hinweise if h.startswith("FEHLER")), None)
        if fehler:
            return fehler
        return next((h for h in hinweise if h.startswith("VERALTET")), "") or \
            ("gemeinsamer Auftrag" if len(mz) > 1 else "eine Position")

    def data(self, index, rolle=Qt.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if rolle in (Qt.DisplayRole, Qt.ToolTipRole):
            t = self.text(r, c)
            if rolle == Qt.ToolTipRole and c in (0, 1, 2, 3):
                return "Doppelklick: Stufe bearbeiten (Einstellungen, Materialpreise, Mengen)"
            return t
        if rolle == Qt.TextAlignmentRole and c == 4:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if rolle == Qt.BackgroundRole and c == PRUEFUNG:
            t = self.text(r, c)
            return QBrush(FARBE_STATUS["FEHLER"] if t.startswith("FEHLER") else FARBE_STATUS["WARNUNG"]
                          if t.startswith("VERALTET") else FARBE_BERECHNET)
        return None

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable


def mengen_text(mz, positionen):
    """Kurztext der Mengen einer Stufe: 'Satz Rahmen 4 · Pos. 10 24 Stk.'."""
    saetze = {staffeln.txt(p.get("satz")) for p in positionen if staffeln.txt(p.get("satz"))}
    teile = []
    for z in sorted(mz, key=lambda z: staffeln.txt(z.get("schluessel"))):
        schl = staffeln.txt(z.get("schluessel"))
        if schl and isinstance(z.get("menge"), (int, float)):
            teile.append(f"Satz {schl}: {_z(z['menge'], 0)}" if schl in saetze else f"Pos. {schl}: {_z(z['menge'], 0)} Stk.")
    return " · ".join(teile)


def eigene_werte(st):
    """Kurztext der Werte, die eine Stufe abweichend vom Angebot hat."""
    teile = []
    for f in staffeln.EINSTELLUNG_FELDER:
        w = st.get(f.name)
        if f.name in ("bezeichnung", "bemerkung", "mat_art") or w in (None, ""):
            continue
        if f.name == "meterpreise":
            n = len(staffeln.meterpreise(st))
            if n:
                teile.append(f"€/m für {n} Abmessung{'en' if n > 1 else ''}")
            continue
        titel = f.titel.split(" [")[0]
        if f.name == "mat_zuschlag":
            teile.append(f"{titel} {_z(w)} {'€/Einheit' if st.get('mat_art') == EURO else '%'}")
        elif f.art in ("zahl", "ganz"):
            einheit = f.titel.split("[")[1].rstrip("]") if "[" in f.titel else ""
            teile.append(f"{titel} {_z(w, f.stellen if f.art == 'zahl' else 0)} {einheit}".strip())
        else:
            teile.append(f"{titel}: {w}")
    return ", ".join(teile)


TIPPS = {
    "menge": "Kalkulationsmenge der Stufe (Mindestmenge), in Sätzen bzw. Stück",
    "bis": "Höchstmenge; leer = bis zur nächsten Stufe desselben Satzes bzw. derselben Position",
    "mat_zuschlag": "Zuschlag auf die Materialkosten nach Verlust; leer = 'Zuschlag Material' der Einstellungen. "
                    "Ersetzt den Zuschlag Material des Angebots für diese Stufe.",
    "mat_art": "% = Prozent auf die Materialkosten nach Verlust, €/Einheit = fester Betrag je Satz bzw. Stück",
    "gewinn": "Gewinn in % auf die Selbstkosten; leer = Gewinn des Angebots",
    "verlust": "Materialverlust / Ausschuss in % auf die Material-Grundkosten (zusätzlich zum echten Verschnitt "
               "der Stangen, der schon in den Grundkosten steckt)",
    "mat_grundpreis": "Fester Material-Grundpreis je Satz bzw. Stück statt der gerechneten Stangenkosten",
    "zuschlag_fertigung": "Gemeinkosten in % auf Fertigung und Rüsten (nicht auf Material); leer = Einstellungen",
    "ruesten": "umlegen = Rüstkosten im Stückpreis; separat = einmalige Position, nicht im Stückpreis",
    "arbeitsgang_min": "Zeit des zusätzlichen Arbeitsgangs je Satz bzw. Stück, mit dem Stundensatz bewertet",
    "arbeitsgang_satz": "Stundensatz des zusätzlichen Arbeitsgangs; leer = Maschinenstundensatz",
    "arbeitsgang_eur": "Fester Betrag des zusätzlichen Arbeitsgangs je Satz bzw. Stück",
    "neben_einheit": "Verpackung und Nebenkosten je Satz bzw. Stück (in den Selbstkosten, mit Gewinn)",
    "neben_pauschal": "Nebenkosten pauschal für die ganze Stufe (in den Selbstkosten, mit Gewinn)",
    "rabatt": "ja = negative Materialzuschläge und Gewinne sind erlaubt (Rabatt)",
}


TIPPS.update({
    "bezeichnung": "Freier Name der Stufe, z. B. „Rahmenauftrag 2027“",
    "zuschlag_fremdleistung": "Zuschlag auf Zusatzarbeiten als Fremdleistung; leer = Wert des Angebots",
    "ruesten_abmessung": "Rüstzeit je Abmessung in der Stufe; leer = Wert des Angebots",
    "pauschale_abmessung": "Pauschale je Abmessung in der Stufe; leer = Wert des Angebots",
    "programmierung_teil": "Programmierkosten je Teil (Position mit Stückzahl); leer = Wert des Angebots",
    "angebotsaufschlag": "Angebotsaufschlag einmal je Stufe; leer = Wert des Angebots",
    "handling_beistellung": "Handling Kundenmaterial je kg; leer = Wert des Angebots",
    "fracht": "Fester Frachtbetrag für die ganze Stufe; leer = Fracht wie im Angebot (berechnet für die Mengen der Stufe)",
    "skonto": "Skonto der Stufe in %; leer = Skonto des Angebots",
    "laenge_auto": "ja = für diese Stufe die empfohlene Lieferlänge je Profil wählen (z. B. 12 m erst bei großen "
                   "Mengen); leer = Lieferlängen wie im Angebot",
})


def _feld_text(f, w):
    if w is None or w == "":
        return ""
    if f.art in ("zahl", "ganz"):
        return _z(w, None if f.art == "zahl" else 0)
    return str(w)


class StufeDialog(QDialog):
    """Fenster einer Stufe: Einstellungen wie im Angebot (leer = Wert des Angebots, grau angezeigt), Erweitert die
    Sonderwerte der Preisschicht, Materialpreis €/m je Abmessung und die Mengen je Satz bzw. Position (leer = nicht
    in dieser Stufe). Die ganze Stufe wird als ein Auftrag gerechnet."""

    def __init__(self, seite, stufe):
        super().__init__(seite)
        self.s, self.stufe = seite, dict(stufe)
        a = seite.s
        self.setWindowTitle(f"Stufe {seite.nummer(stufe)} bearbeiten")
        lay = QVBoxLayout(self)
        lay.addWidget(hilfe.Hinweis("Die Stufe wird wie ein eigener Auftrag gerechnet: alle Positionen mit Menge "
                                    "zusammen optimiert und kalkuliert. Leere Felder (grau) nehmen den Wert des "
                                    "Angebots. Gleiche Mengen und Werte wie im Angebot ergeben dessen Preise."))
        self.felder = {}
        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)
        haupt = ("bezeichnung",) + staffeln.HAUPT
        for i, name in enumerate(haupt):
            self._feld(form, i // 2, 2 * (i % 2), name)
        lay.addLayout(form)
        er = QWidget()
        eg = QGridLayout(er)
        eg.setContentsMargins(16, 0, 0, 0)
        eg.setHorizontalSpacing(8)
        eg.setVerticalSpacing(4)
        erweitert = [f.name for f in staffeln.EINSTELLUNG_FELDER if f.name not in haupt + ("meterpreise",)]
        for i, name in enumerate(erweitert):
            self._feld(eg, i // 2, 2 * (i % 2), name)
        from .angebot_oben import Aufklapper
        self.erweitert = Aufklapper("Erweitert: Materialzuschlag, Verlust, Grundpreis, Gemeinkosten, Rüsten separat, "
                                    "Arbeitsgang, Nebenkosten, Rabatt, Lieferlänge", er,
                                    offen=any(not ohne_wert(stufe.get(n)) for n in erweitert))
        lay.addWidget(self.erweitert)
        # Materialpreis je Abmessung
        self.abm = staffeln.abmessungen(a.positionen)
        angebot_m = {}
        for p, mp in zip(a.positionen, getattr(a.pos_modell, "meterpreise", []) or []):
            if mp and mp[1] is not None:
                angebot_m.setdefault(staffeln.abmessung(p), mp[1])
        eigene = staffeln.meterpreise(stufe)
        self.preise = QTableWidget(len(self.abm), 3)
        self.preise.setHorizontalHeaderLabels(["Abmessung (Positionen)", "€/m im Angebot", "€/m in der Stufe"])
        for r, (abm, pos) in enumerate(self.abm):
            t = QTableWidgetItem(f"{abm} (Pos. {', '.join(pos)})")
            t.setFlags(Qt.ItemIsEnabled)
            w = QTableWidgetItem(_z(angebot_m.get(abm)))
            w.setFlags(Qt.ItemIsEnabled)
            w.setForeground(QBrush(GRAU))
            e = QTableWidgetItem(_z(eigene.get(abm)) if abm in eigene else "")
            for it in (w, e):
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.preise.setItem(r, 0, t)
            self.preise.setItem(r, 1, w)
            self.preise.setItem(r, 2, e)
        self._tabelle_einrichten(self.preise)
        lay.addWidget(QLabel("<b>Materialpreis je Abmessung</b> (leer = Preis des Angebots)"))
        lay.addWidget(self.preise)
        # Mengen je Satz bzw. Position
        self.auswahl = staffeln.auswahl(a.positionen)
        da = {staffeln.txt(z.get("schluessel")): z for z in a.stufen if z.get("stufe_id") == stufe.get("id")}
        self.mengen = QTableWidget(len(self.auswahl), 4)
        self.mengen.setHorizontalHeaderLabels(["Satz bzw. Position", "Menge im Angebot", "Menge ab", "Menge bis"])
        for r, (schl, text, menge) in enumerate(self.auswahl):
            z = da.get(schl) or {}
            t = QTableWidgetItem(text)
            t.setFlags(Qt.ItemIsEnabled)
            m = QTableWidgetItem(_z(menge, 0))
            m.setFlags(Qt.ItemIsEnabled)
            m.setForeground(QBrush(GRAU))
            ab = QTableWidgetItem(_z(z.get("menge"), 0))
            bis = QTableWidgetItem(_z(z.get("bis"), 0))
            for it in (m, ab, bis):
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for c, it in enumerate((t, m, ab, bis)):
                self.mengen.setItem(r, c, it)
        self._tabelle_einrichten(self.mengen)
        zeile = QHBoxLayout()
        zeile.addWidget(QLabel("<b>Mengen</b> in Sätzen bzw. Stück (leer = nicht in dieser Stufe)"), 1)
        for text, faktor in (("Mengen des Angebots", 1), ("× 2", 2), ("× 5", 5), ("× 10", 10)):
            b = QPushButton(text)
            b.setToolTip("Menge ab = Menge im Angebot × Faktor für alle Sätze und Positionen")
            b.clicked.connect(lambda _=False, f=faktor: self.mengen_aus_angebot(f))
            zeile.addWidget(b)
        lay.addLayout(zeile)
        lay.addWidget(self.mengen, 1)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.resize(860, 720)

    @staticmethod
    def _tabelle_einrichten(t):
        t.verticalHeader().setVisible(False)
        t.verticalHeader().setDefaultSectionSize(22)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, t.columnCount()):
            t.setColumnWidth(c, 110)

    def vorgabe(self, name):
        """Grauer Text eines leeren Felds: der Wert des Angebots."""
        a = self.s.s
        e, kopf = a.einst, a.kopf
        if name in ("gewinn", "zuschlag_fremdleistung", "zuschlag_fertigung", "mat_zuschlag"):
            quelle = {"mat_zuschlag": "zuschlag_material"}.get(name, name)
            return f"{_z(100 * (e.get(quelle) or 0), 1)} % (Angebot)"
        if name in ("ruesten_abmessung", "pauschale_abmessung", "programmierung_teil", "angebotsaufschlag",
                    "handling_beistellung"):
            f = staffeln.EINSTELLUNG_FELD[name]
            return f"{_z(e.get(name) or 0, f.stellen)} (Angebot)"
        if name == "fracht":
            return (f"{_z(fracht_angebot.wirksam(kopf))} (Angebot)" if fracht_angebot.modus(kopf) != fracht_angebot.BERECHNET
                    else "berechnet für die Mengen der Stufe")
        if name == "skonto":
            return f"{_z(kopf.get('skonto') or 0, 1)} % (Angebot)"
        if name == "mat_art":
            return PROZENT
        if name == "ruesten":
            return UMLEGEN
        if name == "arbeitsgang_satz":
            return "Maschine"
        return ""

    def _feld(self, raster, r, c, name):
        f = staffeln.EINSTELLUNG_FELD[name]
        if f.art == "auswahl":
            w = QComboBox()
            w.addItem("", None)
            for x in staffeln.AUSWAHL[f.auswahl]:
                w.addItem(x, x)
            i = w.findData(self.stufe.get(name)) if self.stufe.get(name) else 0
            w.setCurrentIndex(max(i, 0))
        else:
            w = QLineEdit(_feld_text(f, self.stufe.get(name)))
            w.setPlaceholderText(self.vorgabe(name))
            if f.art in ("zahl", "ganz"):
                w.setAlignment(Qt.AlignRight)
        w.setToolTip(TIPPS.get(name) or "")
        b = QLabel(f.titel)
        b.setToolTip(TIPPS.get(name) or "")
        raster.addWidget(b, r, c)
        raster.addWidget(w, r, c + 1)
        self.felder[name] = w

    def mengen_aus_angebot(self, faktor=1):
        for r, (_, _, menge) in enumerate(self.auswahl):
            self.mengen.item(r, 2).setText(_z(menge * faktor, 0) if menge else "")

    def werte(self):
        """Eingaben prüfen. Ergebnis: (Einstellungen, {Abmessung: €/m}, [(Schlüssel, Menge ab, Menge bis)]);
        ValueError mit Meldung bei ungültiger Eingabe."""
        werte = {}
        for name, w in self.felder.items():
            f = staffeln.EINSTELLUNG_FELD[name]
            werte[name] = (w.currentData() if isinstance(w, QComboBox) else wert_aus_text(f, w.text()))
        rabatt = werte.get("rabatt") == "ja"
        for name in ("mat_zuschlag", "gewinn"):
            if isinstance(werte.get(name), (int, float)) and werte[name] < 0 and not rabatt:
                raise ValueError(f"{staffeln.EINSTELLUNG_FELD[name].titel}: negative Werte nur als Rabatt – unter "
                                 "Erweitert 'Rabatt erlaubt' auf ja setzen.")
        if isinstance(werte.get("mat_zuschlag"), (int, float)) and (werte.get("mat_art") or PROZENT) == PROZENT \
                and not -100 <= werte["mat_zuschlag"] <= 500:
            raise ValueError("Materialzuschlag: zwischen −100 % und 500 % eingeben.")
        preis_f = Feld("meterpreis", "Materialpreis [€/m]", "zahl", 0, 100000, stellen=2)
        preise = {}
        for r, (abm, _) in enumerate(self.abm):
            w = wert_aus_text(preis_f, self.preise.item(r, 2).text())
            if w:
                preise[abm] = w
        mengen = []
        ab_f, bis_f = staffeln.STUFE_FELD["menge"], staffeln.STUFE_FELD["bis"]
        for r, (schl, text, _) in enumerate(self.auswahl):
            ab = wert_aus_text(ab_f, self.mengen.item(r, 2).text())
            bis = wert_aus_text(bis_f, self.mengen.item(r, 3).text())
            if ab is None and bis is not None:
                raise ValueError(f"{text}: Menge bis ohne Menge ab.")
            if ab is not None:
                if bis is not None and bis < ab:
                    raise ValueError(f"{text}: Menge bis kleiner als Menge ab.")
                mengen.append((schl, ab, bis))
        if not mengen:
            raise ValueError("Bitte mindestens eine Menge eintragen.")
        return werte, preise, mengen

    def accept(self):
        try:
            werte, preise, mengen = self.werte()
        except ValueError as e:
            QMessageBox.warning(self, self.windowTitle(), str(e))
            return
        self.s.stufe_speichern(self.stufe["id"], werte, preise, mengen)
        super().accept()


# ------------------------------------------------------------------ Ergebnis (Kostenpositionen je Stufe)
def _p(z):
    return z.get("preis") or {}


def _liste(z, art, name):
    return sum(x for n, x, _ in _p(z).get(art) or () if n == name)


def _pct(w):
    return f"{_z(100 * w, 1)} %"


# (Schlüssel, Titel, Betrag(z) für die ganze Stufe, Art) – Art: gruppe, kind, summe, info
ERGEBNIS = (
    ("material", "Materialkosten", lambda z: _p(z).get("m_gesamt"), "gruppe"),
    ("m_grund", "Material-Grundkosten (Stangen inkl. Verschnitt)", lambda z: _p(z).get("m_grund"), "kind"),
    ("m_verlust", "Materialverlust / Ausschuss", lambda z: _p(z).get("m_verlust"), "kind"),
    ("m_zuschlag", "Materialzuschlag", lambda z: _p(z).get("m_zuschlag"), "kind"),
    ("fertigung", "Fertigungskosten (Zeit × Stundensatz)", lambda z: _p(z).get("fert_gesamt"), "gruppe"),
    ("ruesten", "Rüstkosten", lambda z: _p(z).get("ruest_gesamt"), "gruppe"),
    ("gemeinkosten", "Gemeinkosten", lambda z: (_p(z).get("gk_fertigung") or 0) + (_p(z).get("gk_fremd") or 0)
     if _p(z) else None, "gruppe"),
    ("gk_fertigung", "Gemeinkosten Fertigung (auf Fertigung + Rüsten)", lambda z: _p(z).get("gk_fertigung"), "kind"),
    ("gk_fremd", "Zuschlag Fremdleistung", lambda z: _p(z).get("gk_fremd"), "kind"),
    ("fremd", "Fremdleistungen", lambda z: _p(z).get("fremd"), "gruppe"),
    ("neben", "Verpackung / Nebenkosten", lambda z: _p(z).get("neben"), "gruppe"),
    ("selbst", "Selbstkosten", lambda z: _p(z).get("selbst"), "summe"),
    ("gewinn", "Gewinn", lambda z: _p(z).get("gewinn"), "gruppe"),
    ("marge", "Gewinnmarge (vom Nettopreis)", lambda z: _p(z).get("marge"), "prozent"),
    ("zukauf", "Zukaufteile (eigener Aufschlag statt Zuschläge und Gewinn)", lambda z: (
        (_p(z).get("zukauf_einstand") or 0) + (_p(z).get("zukauf_aufschlag") or 0)) if _p(z) else None, "gruppe"),
    ("zukauf_einstand", "Einstand Zukaufteile (Einkauf + Bezugskosten)", lambda z: _p(z).get("zukauf_einstand"), "kind"),
    ("zukauf_aufschlag", "Aufschlag Zukaufteile", lambda z: _p(z).get("zukauf_aufschlag"), "kind"),
    ("weitere", "Weitere Kosten (ohne Zuschläge)", lambda z: sum(_p(z).get(n) or 0 for n in (
        "pauschalen", "programmierung", "angebotsaufschlag", "fracht", "skonto")) if _p(z) else None, "gruppe"),
    ("pauschalen", "Pauschale je Abmessung", lambda z: _p(z).get("pauschalen"), "kind"),
    ("programmierung", "Programmierkosten", lambda z: _p(z).get("programmierung"), "kind"),
    ("angebotsaufschlag", "Angebotsaufschlag", lambda z: _p(z).get("angebotsaufschlag"), "kind"),
    ("fracht", "Fracht", lambda z: _p(z).get("fracht"), "kind"),
    ("skonto", "Skonto (eingerechnet)", lambda z: _p(z).get("skonto"), "kind"),
    ("vk", "Verkaufspreis netto je Einheit", lambda z: z.get("preis_einheit"), "summe_einheit"),
    ("einmalig", "Einmalige Rüstkosten (separat)", lambda z: _p(z).get("einmalig"), "gruppe"),
    ("netto", "Gesamtpreis netto", lambda z: z.get("preis_gesamt"), "summe"),
    ("mwst", "Umsatzsteuer", lambda z: _p(z).get("mwst"), "gruppe"),
    ("brutto", "Gesamtpreis brutto", lambda z: _p(z).get("brutto"), "summe"),
)
IMMER = {"material", "fertigung", "ruesten", "selbst", "gewinn", "vk", "netto", "mwst", "brutto"}


class ErgebnisBaum(QTreeWidget):
    """Kostenpositionen (Zeilen, aufklappbar gruppiert) × Stufen (je Stufe € je Einheit und gesamt)."""

    def __init__(self):
        super().__init__()
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.header().setDefaultAlignment(Qt.AlignCenter | Qt.TextWordWrap)
        self.header().setMinimumHeight(52)
        self.offen = {"material", "fertigung"}

    def setzen(self, zeilen, vorher=None, angebot=None):
        """zeilen: bepreiste Zeilen aus staffeln.rechnen_alle; vorher: {stufe_id: Preis je Einheit vorher};
        angebot: {Schlüssel: Preis je Einheit im Angebot} (angebotspreise) für die Zeile 'Δ zum Angebotspreis'."""
        for i in range(self.topLevelItemCount()):
            it = self.topLevelItem(i)
            if it.data(0, Qt.UserRole):
                (self.offen.add if it.isExpanded() else self.offen.discard)(it.data(0, Qt.UserRole))
        self.clear()
        titel = ["Kostenposition"]
        for z in zeilen:
            bis = z.get("bis")
            menge = f"ab {_z(z['menge'], 0)}" if bis is None else _z(z["menge"], 0) if bis <= z["menge"] \
                else f"{_z(z['menge'], 0)}–{_z(bis, 0)}"
            kopf = f"Stufe {z.get('stufe_nr') or ''} · {'Satz ' if z.get('einheit') == 'Satz' else 'Pos. '}{z['schluessel']} · " \
                   f"{menge} {z.get('einheit') or ''}"
            titel += [f"{kopf}\n€ je {z.get('einheit') or 'Einheit'}", f"{kopf}\ngesamt €"]
        self.setColumnCount(len(titel))
        self.setHeaderLabels(titel)
        self.setColumnWidth(0, 330)
        for i in range(1, len(titel)):
            self.setColumnWidth(i, 105)
        if not zeilen:
            return

        def zelle(it, z, j, w, art):
            m = z["menge"]
            if art == "prozent":
                it.setText(1 + 2 * j, _pct(w) if isinstance(w, (int, float)) else "")
            elif art == "summe_einheit":
                it.setText(1 + 2 * j, _z(w))
                it.setText(2 + 2 * j, _z(w * m) if isinstance(w, (int, float)) else "")
            else:
                it.setText(1 + 2 * j, _z(w / m, 3 if abs(w / m) < 1 else 2) if isinstance(w, (int, float)) else "")
                it.setText(2 + 2 * j, _z(w))
            for c in (1 + 2 * j, 2 + 2 * j):
                it.setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)

        def neu(eltern, titel, art, schl=None):
            it = QTreeWidgetItem([titel])
            it.setSizeHint(0, QSize(-1, ZEILENHOEHE))       # sonst stoßen die Zeilen aneinander
            (eltern.addChild if eltern is not None else self.addTopLevelItem)(it)
            if schl:
                it.setData(0, Qt.UserRole, schl)
            if art.startswith("summe"):
                f = it.font(0)
                f.setBold(True)
                for c in range(self.columnCount()):
                    it.setFont(c, f)
                    it.setBackground(c, QBrush(FARBE_SUMME))
            return it

        oben = neu(None, "Mengen", "info", "mengen")
        for titel, f in (("Bestellmenge", lambda z: f"{_z(z['menge'], 0)} {z.get('einheit') or ''}"),
                         ("Teile gesamt", lambda z: _z(z.get("teile"), 0)), ("Stangen", lambda z: _z(z.get("stangen"), 0))):
            it = neu(oben, titel, "info")
            for j, z in enumerate(zeilen):
                it.setText(2 + 2 * j, f(z))
                it.setTextAlignment(2 + 2 * j, Qt.AlignRight | Qt.AlignVCenter)
        gruppe = None
        for schl, titel, f, art in ERGEBNIS:
            werte = [f(z) for z in zeilen]
            if schl not in IMMER and all(ohne_wert(w) for w in werte):
                continue
            if schl == "m_zuschlag":
                arten = {(_p(z).get("wirksam") or z.get("wirksam") or {}).get("mat_art") for z in zeilen if _p(z)}
                titel += " (auf Material nach Verlust" + (", €/Einheit" if EURO in arten else "") + ")"
            it = neu(gruppe if art == "kind" else None, titel, art, schl)
            if art != "kind":
                gruppe = it
            for j, (z, w) in enumerate(zip(zeilen, werte)):
                if isinstance(w, (int, float)):
                    zelle(it, z, j, w, art)
            if schl in ("fertigung", "ruesten"):            # Arbeitsschritte je Stufe
                namen = list(dict.fromkeys(n for z in zeilen for n, _, _ in _p(z).get(schl) or ()))
                for n in namen:
                    if n != "Laser schneiden" and all(ohne_wert(_liste(z, schl, n)) for z in zeilen):
                        continue
                    k = neu(it, n, "kind")
                    tipp = []
                    for j, z in enumerate(zeilen):
                        if _p(z):
                            zelle(k, z, j, _liste(z, schl, n), "kind")
                            tipp += [f"{z['schluessel']} {z['menge']}: {e}" for n2, _, e in _p(z)[schl] if n2 == n and e]
                    k.setToolTip(0, "\n".join(tipp))
        # Unterschied zum Preis je Einheit im Angebot (Hauptmenge): jede Stufe ist eine eigene Bestellung (B-3)
        if angebot and any(z.get("schluessel") in angebot for z in zeilen):
            it = neu(None, "Δ zum Angebotspreis je Einheit", "info", "delta")
            it.setToolTip(0, "Preis je Einheit der Stufe minus Preis je Einheit im Angebot (Hauptmenge). Jede Stufe "
                             "rechnet als eigener Auftrag mit allen Sätzen und Positionen der Stufe.")
            for j, z in enumerate(zeilen):
                ang, jetzt = angebot.get(z.get("schluessel")), z.get("preis_einheit")
                if isinstance(ang, (int, float)) and isinstance(jetzt, (int, float)):
                    d = jetzt - ang
                    it.setText(1 + 2 * j, f"{'+' if d > 0.005 else ''}{_z(d)} €")
                    it.setText(2 + 2 * j, f"{'+' if d > 0.005 else ''}{_z(100 * d / ang, 1)} %" if ang else "")
                    it.setToolTip(1 + 2 * j, f"Angebot {_z(ang)} €, Stufe {_z(jetzt)} € je Einheit")
        # Hinweise und Änderung zum vorherigen Stand
        if vorher:
            it = neu(None, "Änderung Preis je Einheit (zur letzten Eingabe)", "info", "aenderung")
            for j, z in enumerate(zeilen):
                alt, jetzt = vorher.get(z.get("stufe_id")), z.get("preis_einheit")
                if isinstance(alt, (int, float)) and isinstance(jetzt, (int, float)) and abs(jetzt - alt) >= 0.005:
                    it.setText(1 + 2 * j, f"{'+' if jetzt > alt else ''}{_z(jetzt - alt)} €")
                    it.setText(2 + 2 * j, f"{'+' if jetzt > alt else ''}{_z(100 * (jetzt - alt) / alt, 1)} %" if alt else "")
                    it.setToolTip(1 + 2 * j, f"vorher {_z(alt)} €, jetzt {_z(jetzt)} €")
        it = neu(None, "Hinweis", "info", "hinweis")
        for j, z in enumerate(zeilen):
            h = z.get("hinweis") or ""
            it.setText(1 + 2 * j, h)
            it.setToolTip(1 + 2 * j, h)
            if h.startswith(("FEHLER", "VERALTET")):
                it.setBackground(1 + 2 * j, QBrush(FARBE_STATUS["FEHLER"] if h.startswith("FEHLER")
                                                   else FARBE_STATUS["WARNUNG"]))
        for i in range(self.topLevelItemCount()):
            t = self.topLevelItem(i)
            t.setExpanded(t.data(0, Qt.UserRole) in self.offen)

    def zeile(self, schl):
        """Eintrag einer Kostenposition (für Tests und Bildschirmfotos)."""
        for i in range(self.topLevelItemCount()):
            t = self.topLevelItem(i)
            if t.data(0, Qt.UserRole) == schl:
                return t
            for c in range(t.childCount()):
                if t.child(c).data(0, Qt.UserRole) == schl:
                    return t.child(c)
        return None


class Vergleich(QWidget):
    """Preisentwicklung: Verkaufspreis netto je Einheit über die Mengen, je Satz bzw. Position eine Reihe."""

    def __init__(self):
        super().__init__()
        self.reihen = []
        self.setMinimumWidth(260)

    def setzen(self, zeilen):
        reihen = {}
        for z in zeilen:
            if isinstance(z.get("preis_einheit"), (int, float)):
                reihen.setdefault((z.get("einheit"), z["schluessel"]), []).append((z["menge"], z["preis_einheit"]))
        self.reihen = [(k, sorted(v)) for k, v in reihen.items()]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        p.setPen(QColor("#404040"))
        p.drawText(QRectF(8, 4, self.width() - 16, 20), Qt.AlignLeft, "Preisentwicklung: VK netto je Einheit")
        if not self.reihen:
            p.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignCenter, "noch keine Staffelpreise")
            return
        farben = ["#4E79A7", "#F28E2B", "#59A14F", "#B07AA1", "#E15759", "#76B7B2"]
        y0, hoehe = 30, max(40, self.height() - 30)
        je = hoehe / len(self.reihen)
        for r, ((einheit, schl), punkte) in enumerate(self.reihen):
            top = y0 + r * je
            p.setPen(QColor("#404040"))
            p.drawText(QRectF(8, top, self.width() - 16, 16), Qt.AlignLeft,
                       f"{'Satz' if einheit == 'Satz' else 'Pos.'} {schl}")
            maxp = max(w for _, w in punkte) or 1
            balken = min(24, (je - 22) / max(1, len(punkte)))
            for i, (m, w) in enumerate(punkte):
                y = top + 18 + i * balken
                breite = (self.width() - 150) * w / maxp
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(farben[r % len(farben)]))
                p.drawRect(QRectF(60, y + 1, max(1, breite), max(3, balken - 3)))
                p.setPen(QColor("#404040"))
                p.drawText(QRectF(4, y, 54, balken), Qt.AlignRight | Qt.AlignVCenter, _z(m, 0))
                p.drawText(QRectF(64 + breite, y, 90, balken), Qt.AlignLeft | Qt.AlignVCenter, f"{_z(w)} €")


class _Bote(QObject):
    """Bringt das Ergebnis des Hintergrundlaufs in den Programmablauf zurück."""
    fertig = Signal(int, object, object)


# ------------------------------------------------------------------ Reiter
class StaffelSeite(QWidget):
    KUERZEL = {"neu": "neu", "loeschen": ("loeschen", "ansicht")}     # Tastenkürzel, siehe tastatur.py

    def __init__(self, seite):
        super().__init__()
        self.s = seite
        self.modell = StufenModell(self)
        self.ansicht = QTableView()
        self.ansicht.setModel(self.modell)
        self.ansicht.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ansicht.verticalHeader().setDefaultSectionSize(22)
        self.ansicht.horizontalHeader().setStretchLastSection(True)
        self.ansicht.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ansicht.doubleClicked.connect(lambda i: self.bearbeiten(i.row()))
        for i, breite in enumerate((60, 160, 320, 300, 110)):
            self.ansicht.setColumnWidth(i, breite)
        AutoGroesse(self.ansicht)        # Breite und Höhe passend zum Inhalt (spaltenbreite.py)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.baum = ErgebnisBaum()
        self.vergleich = Vergleich()
        self.knoepfe = {}
        leiste = QHBoxLayout()
        for text, ziel in (("Neue Stufe …", self.neu), ("Stufe bearbeiten …", self.bearbeiten),
                           ("Stufen löschen", self.loeschen), ("Staffelpreise rechnen", self.rechnen)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            leiste.addWidget(b)
            self.knoepfe[text] = b
        leiste.addStretch(1)
        self.hinweis = hilfe.Hinweis("Je Zeile eine Stufe, gerechnet wie ein eigener Auftrag: alle Sätze und "
                                     "Positionen mit Menge zusammen. Doppelklick öffnet die Stufe mit Einstellungen, "
                                     "Materialpreisen und Mengen. Leere Werte nehmen den Wert des Angebots.",
                                     getattr(self.s, "db", None), "staffeln")
        aufklappen = QPushButton("Alle aufklappen")
        aufklappen.clicked.connect(lambda: self.baum.expandAll())
        unten = QWidget()
        ul = QVBoxLayout(unten)
        ul.setContentsMargins(0, 0, 0, 0)
        zeile = QHBoxLayout()
        zeile.addWidget(self.info, 1)
        zeile.addWidget(aufklappen)
        ul.addLayout(zeile)
        quer = QSplitter(Qt.Horizontal)
        quer.addWidget(self.baum)
        quer.addWidget(self.vergleich)
        quer.setStretchFactor(0, 4)
        quer.setStretchFactor(1, 1)
        quer.setSizes([900, 280])
        ul.addWidget(quer, 1)
        self.teiler = QSplitter(Qt.Vertical)          # Stufen oben (wenige Zeilen), Ergebnis bekommt den Platz
        self.teiler.addWidget(self.ansicht)
        self.teiler.addWidget(unten)
        self.teiler.setStretchFactor(0, 0)
        self.teiler.setStretchFactor(1, 1)
        self.teiler.setSizes([150, 600])
        lay = QVBoxLayout(self)
        lay.addWidget(self.hinweis)
        lay.addLayout(leiste)
        lay.addWidget(self.teiler, 1)
        self.zeilen, self.vorher = [], {}
        self._lauf, self._laeuft = 0, False
        self._bote = _Bote()
        self._bote.fertig.connect(self._hintergrund_fertig)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._hintergrund_starten)

    # -------------------------------------------------------------- Anzeige
    def setzen(self):
        """Nach dem Laden des Angebots: Stufen, Preise (ohne neuen Mengenlauf) und Stand anzeigen."""
        self.stand()

    def _args(self):
        s = self.s
        return s.kopf, s.positionen, s.stufen, s.k, s.tabellen, s.einst

    def _daten(self):
        return getattr(self.s, "stufen_daten", None)

    def kennung(self):
        return staffeln.kennung(*self._args(), stufen_daten=self._daten())

    def anzahl_veraltet(self):
        return staffeln.veraltet(self.s.kopf.get("staffelpreise"), *self._args(), stufen_daten=self._daten())

    def nummer(self, stufe):
        return staffeln.stufe_nummern(self._daten()).get(stufe.get("id"), "")

    def stand(self, speichern=False):
        """Preisschicht auf die gespeicherten Mengenläufe anwenden, anzeigen; speichern: Ergebnis sichern."""
        sp = self.s.kopf.get("staffelpreise")
        alt = (sp or {}).get("zeilen") or []
        self.zeilen = staffeln.rechnen_alle(*self._args(), alt=alt, ohne_lauf=True, stufen_daten=self._daten()) \
            if staffeln.gueltige(self.s.stufen) else []
        self.modell.setzen(list(self._daten() or []))
        offen = self.anzahl_veraltet()
        if speichern and sp and not offen:
            self.speichern(self.zeilen, am=sp.get("am"))
        try:
            angebot = angebotspreise(self.s.positionen, self.s._rechnung()[0]) if self.zeilen else None
        except (ValueError, TypeError, KeyError):         # unvollständiges Angebot: ohne Vergleich
            angebot = None
        self.baum.setzen(self.zeilen, self.vorher, angebot)
        self.vergleich.setzen(self.zeilen)
        if not staffeln.gueltige(self.s.stufen):
            text, farbe = "Keine Mengenstufen eingetragen.", "#5F6B7A"
        elif not sp:
            text, farbe = "Staffelpreise noch nicht gerechnet.", "#7A5A00"
        elif offen:
            text = (f"VERALTET – {offen} Stufe(n) passen nicht mehr zu Angebot, Mengen oder Stammdaten"
                    + (" und werden im Hintergrund neu gerechnet …" if self._laeuft or self._timer.isActive()
                       else ". Das Angebot rechnet sie neu."))
            farbe = "#B42318"
        else:
            text, farbe = f"Staffelpreise aktuell (Mengenlauf {_zeit(sp.get('am'))}).", "#1E6B34"
        fehler = sum(1 for z in self.zeilen if str(z.get("hinweis") or "").startswith("FEHLER"))
        if fehler:
            text += f" {fehler} Stufe(n) mit FEHLER – ohne Preis, nicht im Angebot."
            farbe = "#B42318" if not offen else farbe
        self.info.setText(f"<b style='color:{farbe}'>{text}</b>")
        if offen and not self.s.f.stumm:
            self._planen()

    # -------------------------------------------------------------- Stufen
    def neu(self):
        """Neue Stufe mit den Mengen des Angebots anlegen und ihr Fenster öffnen (Mengen dort ändern)."""
        sid = self.aus_angebot(leer=True)
        if sid and not self.s.f.stumm:
            self.bearbeiten(next(r for r, st in enumerate(self.modell.daten) if st["id"] == sid), neu=True)
        return sid

    def aus_angebot(self, faktor=1, leer=False):
        """Eine Stufe mit den Mengen des Angebots (× faktor) für alle Sätze und Positionen anlegen. Ergebnis: ID der
        Stufe oder None (keine Mengen im Angebot; leer=True: dann eine Stufe ohne Mengen)."""
        mengen = [(schl, menge) for schl, _, menge in staffeln.auswahl(self.s.positionen) if menge]
        if not mengen and not leer:
            self.s.f.meldung("Im Angebot hat noch kein Satz und keine Position eine Stückzahl.", fehler=True)
            return None
        sid = self.s.db.staffel_stufe_neu(self.s.id)
        for schl, menge in mengen:
            self.s.db.staffel_neu(self.s.id, dict(schluessel=schl, menge=menge * faktor, stufe_id=sid))
        self.s.neu_laden()
        self.s.reiter.setCurrentWidget(self)
        r = next(r for r, st in enumerate(self.modell.daten) if st["id"] == sid)
        self.ansicht.setCurrentIndex(self.modell.index(r, 0))
        self.s.f.meldung(f"Stufe {r + 1} mit den Mengen des Angebots angelegt." if mengen else
                         f"Stufe {r + 1} angelegt: bitte im Fenster der Stufe Mengen eintragen.")
        self.s.verlauf.merken()
        return sid

    def bearbeiten(self, zeile=None, neu=False):
        """Fenster der Stufe (zeile = Zeile der Stufentabelle, sonst die markierte)."""
        if zeile is None or isinstance(zeile, bool):
            i = self.ansicht.currentIndex()
            zeile = i.row() if i.isValid() else None
        if zeile is None or not 0 <= zeile < len(self.modell.daten):
            self.s.f.meldung("Bitte zuerst eine Stufe markieren.", fehler=True)
            return False
        d = StufeDialog(self, self.modell.daten[zeile])
        return d.exec() == QDialog.Accepted

    def stufe_speichern(self, sid, werte, preise, mengen):
        """Werte, Materialpreise und Mengen einer Stufe speichern (Mengenzeilen werden angepasst, nicht neu
        angelegt, damit der Vergleich zur letzten Eingabe bleibt)."""
        self.vorher = {z.get("stufe_id"): z.get("preis_einheit") for z in self.zeilen}
        db = self.s.db
        for name, w in werte.items():
            db.staffel_stufe_aendern(sid, name, w)
        db.staffel_stufe_aendern(sid, "meterpreise", preise or None)
        da = {staffeln.txt(z.get("schluessel")): z for z in self.s.stufen if z.get("stufe_id") == sid}
        for schl, ab, bis in mengen:
            z = da.pop(schl, None)
            if z is None:
                db.staffel_neu(self.s.id, dict(schluessel=schl, menge=ab, bis=bis, stufe_id=sid))
            else:
                db.staffel_aendern(z["id"], "menge", ab)
                db.staffel_aendern(z["id"], "bis", bis)
        db.staffeln_loeschen([z["id"] for z in da.values()])
        self.s.neu_laden()
        self.stand(speichern=True)
        self.s.verlauf.merken()         # Schritt für Rückgängig

    def loeschen(self):
        zeilen = sorted({i.row() for i in self.ansicht.selectionModel().selectedIndexes()})
        if not zeilen:
            self.s.f.meldung("Bitte zuerst die Stufen markieren, die gelöscht werden sollen.", fehler=True)
            return
        self.s.db.staffel_stufen_loeschen([self.modell.daten[r]["id"] for r in zeilen])
        self.s.neu_laden()
        self.s.verlauf.merken()

    # -------------------------------------------------------------- Rechnen
    def speichern(self, zeilen, am=None):
        sp = dict(zeilen=zeilen, kennung=self.kennung(), version=staffeln.VERSION,
                  am=am or datetime.datetime.now().isoformat(timespec="seconds")) if zeilen else None
        self.s.db.staffelpreise_speichern(self.s.id, sp)
        self.s.kopf["staffelpreise"] = sp

    def rechnen(self, alle=True):
        """Mengenläufe rechnen (alle=True: alle Stufen neu, sonst nur veraltete) und speichern.
        Ergebnis: bepreiste Zeilen oder None (abgebrochen)."""
        stufen = staffeln.gueltige(self.s.stufen)
        if not stufen:
            self.s.f.meldung("Keine Mengenstufe eingetragen (Reiter Staffeln).", fehler=True)
            self.speichern([])
            self.stand()
            return []
        self._timer.stop()
        self._lauf += 1                 # ein laufender Hintergrundlauf gilt nicht mehr
        fortschritt = QProgressDialog("Staffelpreise werden gerechnet …", "Abbrechen", 0, len(stufen), self)
        fortschritt.setWindowModality(Qt.WindowModal)
        fortschritt.setMinimumDuration(500)

        def weiter(i, n):
            fortschritt.setMaximum(max(n, 1))
            fortschritt.setValue(i)
            QApplication.processEvents()
            return not fortschritt.wasCanceled()
        alt = None if alle else ((self.s.kopf.get("staffelpreise") or {}).get("zeilen"))
        try:
            zeilen = staffeln.rechnen_alle(*self._args(), fortschritt=weiter, alt=alt, stufen_daten=self._daten())
        except (ValueError, AssertionError) as e:
            fortschritt.close()
            QMessageBox.warning(self, "Staffelpreise", f"Staffelpreise abgebrochen:\n{e}")
            return None
        fortschritt.close()
        if zeilen is None:
            self.s.f.meldung("Staffelpreise abgebrochen.", fehler=True)
            return None
        self.speichern(zeilen)
        self.stand()
        self.s.f.meldung(f"{len(zeilen)} Mengenstufe(n) gerechnet.")
        return self.zeilen

    def aktuell(self):
        """Staffelpreise fürs Angebot; veraltete Stufen werden vorher neu gerechnet. None = abgebrochen."""
        if not staffeln.gueltige(self.s.stufen):
            return []
        if self.s.kopf.get("staffelpreise") and not self.anzahl_veraltet():
            self.stand()
            return self.zeilen
        return self.rechnen(alle=False)

    # -------------------------------------------------------------- Hintergrund
    def _planen(self):
        if not self._laeuft:
            self._timer.start(700)

    def _hintergrund_starten(self):
        """Veraltete Mengenläufe in einem eigenen Ablauf rechnen (mit Kopien der Eingaben)."""
        if self._laeuft or not self.anzahl_veraltet():
            return
        self._lauf += 1
        nr, self._laeuft = self._lauf, True
        args = copy.deepcopy(self._args())
        daten = copy.deepcopy(self._daten())
        alt = copy.deepcopy((self.s.kopf.get("staffelpreise") or {}).get("zeilen"))
        kenn = self.kennung()

        def lauf():
            try:
                zeilen = staffeln.rechnen_alle(*args, alt=alt, stufen_daten=daten)
                self._bote.fertig.emit(nr, zeilen, kenn)
            except Exception as e:          # noqa: BLE001 – Fehler im Programmablauf melden
                self._bote.fertig.emit(nr, None, str(e))
        threading.Thread(target=lauf, daemon=True).start()
        self.stand()

    def _hintergrund_fertig(self, nr, zeilen, kenn):
        self._laeuft = False
        if zeilen is None:
            self.s.f.meldung(f"Staffelpreise: Hintergrundlauf abgebrochen ({kenn}).", fehler=True)
            return
        if nr == self._lauf and kenn == self.kennung():
            self.speichern(zeilen)
            self.s.f.meldung(f"Staffelpreise neu gerechnet ({len(zeilen)} Stufe(n)).")
        self.stand()                    # passt es nicht mehr (Eingaben geändert), plant stand() neu

    def warten(self, sekunden=120):
        """Auf den Hintergrundlauf warten (Tests). True = fertig."""
        ende = datetime.datetime.now() + datetime.timedelta(seconds=sekunden)
        while (self._laeuft or self._timer.isActive()) and datetime.datetime.now() < ende:
            QApplication.processEvents()
            threading.Event().wait(0.02)
        return not self._laeuft and not self._timer.isActive()
