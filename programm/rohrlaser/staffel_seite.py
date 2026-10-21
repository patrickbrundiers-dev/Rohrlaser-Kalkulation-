"""Reiter 'Staffeln' im Angebot: Mengenstufen mit eigenen Werten (Materialzuschlag, Gewinn, Nebenkosten …) und
Ergebnis je Stufe mit allen Kostenpositionen bis zum Bruttopreis.

Rechnung in staffeln.py: der Mengenlauf (Optimierung je Stufe) läuft nach Änderungen an Mengen, Positionen oder
Stammdaten automatisch im Hintergrund, die Preisschicht (Zuschläge, Gewinn, Nebenkosten) sofort bei jeder Eingabe.
"""
import copy
import datetime
import threading

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QHBoxLayout, QLabel,
                               QMessageBox, QProgressDialog, QPushButton, QSplitter, QStyledItemDelegate, QTableView,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import staffeln
from .fenster import FARBE_BERECHNET, FARBE_EINGABE, FARBE_STATUS
from .spaltenbreite import AutoGroesse
from .sichtbarkeit import ohne_wert
from .staffeln import ERWEITERT, EURO, PROZENT, STUFE_FELDER, UMLEGEN
from .stammdaten import wert_aus_text, zahl_als_text

PRUEFUNG = len(STUFE_FELDER)          # letzte Spalte der Stufentabelle
GRAU = QColor("#7F7F7F")
FARBE_SUMME = QColor("#DDEBF7")


def _z(w, stellen=2):
    return zahl_als_text(w, stellen) if isinstance(w, (int, float)) and not isinstance(w, bool) else ""


def _zeit(iso):
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
    except (TypeError, ValueError):
        return ""


# ------------------------------------------------------------------ Stufentabelle (Eingabe)
class StaffelAuswahl(QStyledItemDelegate):
    """Spalte 'Satz oder Pos.': Auswahl der Sätze und Positionen des Angebots (Eintippen geht weiter);
    Auswahlspalten (Zuschlag in, Rüstkosten, Rabatt erlaubt): feste Liste."""

    def __init__(self, seite, parent):
        super().__init__(parent)
        self.s = seite

    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        f = STUFE_FELDER[index.column()]
        if f.name == "schluessel":
            cb.setEditable(True)
            cb.setInsertPolicy(QComboBox.NoInsert)
            for schl, text, _ in staffeln.auswahl(self.s.positionen):
                cb.addItem(text, schl)
        else:
            cb.addItem("", None)
            for w in staffeln.AUSWAHL[f.auswahl]:
                cb.addItem(w, w)
        return cb

    def setEditorData(self, editor, index):
        w = index.data(Qt.EditRole) or ""
        i = editor.findData(w) if w else (0 if not editor.isEditable() else -1)
        editor.setCurrentIndex(i)
        if i < 0:
            editor.setEditText(w)

    def setModelData(self, editor, modell, index):
        i = editor.currentIndex()
        text = editor.currentText()
        wert = editor.itemData(i) if i >= 0 and editor.itemText(i) == text else text
        modell.setData(index, wert or "", Qt.EditRole)


class StaffelnModell(QAbstractTableModel):
    """Mengenstufen eines Angebots: Felder aus staffeln.STUFE_FELDER und die Prüfung. Leere Werte zeigen grau den
    Wert, der gilt (Angebot bzw. automatische Höchstmenge)."""
    geaendert = Signal(str)          # Name des geänderten Felds

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
        return 0 if parent.isValid() else PRUEFUNG + 1

    def headerData(self, abschnitt, richtung, rolle=Qt.DisplayRole):
        if rolle == Qt.DisplayRole:
            if richtung != Qt.Horizontal:
                return str(abschnitt + 1)
            return "Prüfung" if abschnitt == PRUEFUNG else STUFE_FELDER[abschnitt].titel
        if rolle == Qt.ToolTipRole and richtung == Qt.Horizontal and abschnitt < PRUEFUNG:
            return TIPPS.get(STUFE_FELDER[abschnitt].name)
        return None

    def vorgabe(self, z, name):
        """Grauer Text für ein leeres Feld: der Wert, der gilt."""
        e = self.s.s.einst
        if name == "mat_zuschlag":
            return f"{_z(100 * (e.get('zuschlag_material') or 0), 1)} % (Einstellungen)"
        if name == "mat_art":
            return PROZENT
        if name == "gewinn":
            return f"{_z(100 * (e.get('gewinn') or 0), 1)} % (Angebot)"
        if name == "zuschlag_fertigung":
            return f"{_z(100 * (e.get('zuschlag_fertigung') or 0), 1)} % (Einstellungen)"
        if name == "ruesten":
            return UMLEGEN
        if name == "bis":
            b = staffeln.bis_wirksam(z, self.daten)
            return f"bis {_z(b, 0)}" if b is not None else "offen"
        if name == "arbeitsgang_satz" and (z.get("arbeitsgang_min") or 0):
            return "Maschine"
        return ""

    def anzeige(self, z, name):
        w = z.get(name)
        if name == "mat_zuschlag" and isinstance(w, (int, float)):
            return f"{_z(w, 2)} %" if (z.get("mat_art") or PROZENT) == PROZENT else f"{_z(w, 2)} €/Einheit"
        f = staffeln.STUFE_FELD[name]
        if f.art in ("zahl", "ganz"):
            return _z(w, f.stellen if f.art == "zahl" else 0)
        return "" if w is None else str(w)

    def data(self, index, rolle=Qt.DisplayRole):
        if not index.isValid():
            return None
        z, c = self.daten[index.row()], index.column()
        if c == PRUEFUNG:
            w = staffeln.pruefen(z, self.s.s.positionen, self.daten)
            if rolle in (Qt.DisplayRole, Qt.ToolTipRole):
                return w
            if rolle == Qt.BackgroundRole:
                return QBrush(FARBE_STATUS["FEHLER"] if w.startswith("FEHLER") else FARBE_BERECHNET)
            return None
        name = STUFE_FELDER[c].name
        leer = z.get(name) in (None, "")
        fehl = [t for n, t in staffeln.fehler(z, self.s.s.positionen, self.daten) if n == name] \
            if staffeln.txt(z.get("schluessel")) else []
        if rolle == Qt.DisplayRole:
            return self.vorgabe(z, name) if leer else self.anzeige(z, name)
        if rolle == Qt.EditRole:
            w = z.get(name)
            f = STUFE_FELDER[c]
            return "" if w is None else (_z(w, None if f.art == "zahl" else 0) if f.art in ("zahl", "ganz") else str(w))
        if rolle == Qt.ToolTipRole:
            return "; ".join(fehl) or (f"leer = {self.vorgabe(z, name)}" if leer and self.vorgabe(z, name) else None)
        if rolle == Qt.ForegroundRole and leer:
            return QBrush(GRAU)
        if rolle == Qt.FontRole and leer:
            f = QFont()
            f.setItalic(True)
            return f
        if rolle == Qt.TextAlignmentRole and STUFE_FELDER[c].art in ("zahl", "ganz"):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if rolle == Qt.BackgroundRole:
            if fehl or (name in ("schluessel", "menge") and leer and staffeln.txt(z.get("schluessel"))):
                return QBrush(FARBE_STATUS["FEHLER"])
            return QBrush(FARBE_EINGABE)
        return None

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return f | Qt.ItemIsEditable if index.column() < PRUEFUNG else f

    def setData(self, index, text, rolle=Qt.EditRole):
        if rolle != Qt.EditRole or not index.isValid() or index.column() >= PRUEFUNG:
            return False
        f = STUFE_FELDER[index.column()]
        z = self.daten[index.row()]
        t = str(text).strip().replace("€/Einheit", "").replace("%", "").strip() if f.art in ("zahl", "ganz") \
            else str(text).strip()
        try:
            if f.name == "schluessel":
                wert = t or None
            elif f.art == "auswahl":
                if t and t not in staffeln.AUSWAHL[f.auswahl]:
                    raise ValueError(f"{f.titel}: bitte aus der Liste wählen.")
                wert = t or None
            else:
                wert = wert_aus_text(f, t)
        except ValueError as e:
            self.s.s.f.meldung(str(e), fehler=True)
            return False
        if f.name == "menge" and wert is not None and wert < 1:
            self.s.s.f.meldung("Menge: bitte eine ganze Zahl ab 1 eingeben (Sätze bzw. Stück).", fehler=True)
            return False
        if f.name in ("mat_zuschlag", "gewinn") and isinstance(wert, (int, float)) and wert < 0 \
                and z.get("rabatt") != "ja":
            self.s.s.f.meldung(f"{f.titel}: negative Werte nur als Rabatt – zuerst 'Rabatt erlaubt' auf ja setzen.",
                               fehler=True)
            return False
        if f.name == "mat_zuschlag" and isinstance(wert, (int, float)) and (z.get("mat_art") or PROZENT) == PROZENT \
                and not -100 <= wert <= 500:
            self.s.s.f.meldung("Materialzuschlag: zwischen −100 % und 500 % eingeben.", fehler=True)
            return False
        if wert == z.get(f.name):
            return False
        self.s.s.db.staffel_aendern(z["id"], f.name, wert)
        z[f.name] = wert
        self.dataChanged.emit(self.index(0, 0), self.index(len(self.daten) - 1, PRUEFUNG))
        self.geaendert.emit(f.name)
        return True


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

    def setzen(self, zeilen, vorher=None):
        """zeilen: bepreiste Zeilen aus staffeln.rechnen_alle; vorher: {stufe_id: Preis je Einheit vorher}."""
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
            kopf = f"{'Satz ' if z.get('einheit') == 'Satz' else 'Pos. '}{z['schluessel']} · {menge} {z.get('einheit') or ''}"
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
        self.modell = StaffelnModell(self)
        self.modell.geaendert.connect(self._geaendert)
        self.ansicht = QTableView()
        self.ansicht.setModel(self.modell)
        self.ansicht.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ansicht.horizontalHeader().setDefaultAlignment(Qt.AlignCenter | Qt.TextWordWrap)
        self.ansicht.horizontalHeader().setMinimumHeight(48)
        self.ansicht.verticalHeader().setDefaultSectionSize(22)
        self.ansicht.horizontalHeader().setStretchLastSection(True)
        auswahl = StaffelAuswahl(self.s, self.ansicht)
        for i, f in enumerate(STUFE_FELDER):
            self.ansicht.setColumnWidth(i, f.breite)
            if f.art == "auswahl" or f.name == "schluessel":
                self.ansicht.setItemDelegateForColumn(i, auswahl)
        self.ansicht.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                     | QAbstractItemView.AnyKeyPressed)
        AutoGroesse(self.ansicht)        # Breite und Höhe passend zum Inhalt (spaltenbreite.py)
        self.erweitert = QCheckBox("Erweiterte Einstellungen")
        self.erweitert.setToolTip("Höchstmenge, Materialverlust, Grundpreis, Gemeinkosten, Rüstkosten separat, "
                                  "zusätzlicher Arbeitsgang, Nebenkosten und Rabatt je Stufe. Spalten mit Werten "
                                  "bleiben immer sichtbar.")
        self.erweitert.toggled.connect(self._spalten_zeigen)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.baum = ErgebnisBaum()
        self.vergleich = Vergleich()
        self.knoepfe = {}
        leiste = QHBoxLayout()
        for text, ziel in (("Neue Stufe", self.neu), ("Stufen aus Angebot", self.aus_angebot),
                           ("Stufen löschen", self.loeschen), ("Staffelpreise rechnen", self.rechnen)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, ziel=ziel: ziel())
            leiste.addWidget(b)
            self.knoepfe[text] = b
        leiste.addSpacing(12)
        leiste.addWidget(self.erweitert)
        leiste.addSpacing(12)
        hinweis = QLabel("Je Zeile eine Mengenstufe: Satz oder Position wählen, Menge eintragen. Leere Felder "
                         "(grau) nehmen den Wert des Angebots. Zuschläge wirken sofort, neue Mengen werden "
                         "automatisch neu gerechnet.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color: #595959;")
        leiste.addWidget(hinweis, 1)
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
        self.modell.setzen(self.s.stufen)
        self._spalten_zeigen()
        self.stand()

    def _spalten_zeigen(self):
        for i, f in enumerate(STUFE_FELDER):
            zeigen = f.name not in ERWEITERT or self.erweitert.isChecked() \
                or any(not ohne_wert(st.get(f.name)) for st in self.s.stufen)
            self.ansicht.setColumnHidden(i, not zeigen)

    def _args(self):
        s = self.s
        return s.kopf, s.positionen, s.stufen, s.k, s.tabellen, s.einst

    def kennung(self):
        return staffeln.kennung(*self._args())

    def anzahl_veraltet(self):
        return staffeln.veraltet(self.s.kopf.get("staffelpreise"), *self._args())

    def stand(self, speichern=False):
        """Preisschicht auf die gespeicherten Mengenläufe anwenden, anzeigen; speichern: Ergebnis sichern."""
        sp = self.s.kopf.get("staffelpreise")
        alt = (sp or {}).get("zeilen") or []
        self.zeilen = staffeln.rechnen_alle(*self._args(), alt=alt, ohne_lauf=True) if staffeln.gueltige(self.s.stufen) else []
        offen = self.anzahl_veraltet()
        if speichern and sp and not offen:
            self.speichern(self.zeilen, am=sp.get("am"))
        self.baum.setzen(self.zeilen, self.vorher)
        self.vergleich.setzen(self.zeilen)
        if not staffeln.gueltige(self.s.stufen):
            text, farbe = "Keine Mengenstufen eingetragen.", "#595959"
        elif not sp:
            text, farbe = "Staffelpreise noch nicht gerechnet.", "#9C5700"
        elif offen:
            text = (f"VERALTET – {offen} Stufe(n) passen nicht mehr zu Angebot, Mengen oder Stammdaten"
                    + (" und werden im Hintergrund neu gerechnet …" if self._laeuft or self._timer.isActive()
                       else ". Das Angebot rechnet sie neu."))
            farbe = "#C00000"
        else:
            text, farbe = f"Staffelpreise aktuell (Mengenlauf {_zeit(sp.get('am'))}).", "#375623"
        fehler = sum(1 for z in self.zeilen if str(z.get("hinweis") or "").startswith("FEHLER"))
        if fehler:
            text += f" {fehler} Stufe(n) mit FEHLER – ohne Preis, nicht im Angebot."
            farbe = "#C00000" if not offen else farbe
        self.info.setText(f"<b style='color:{farbe}'>{text}</b>")
        if offen and not self.s.f.stumm:
            self._planen()

    def _geaendert(self, feld):
        """Eingabe in der Stufentabelle: Zuschläge sofort bepreisen, Mengen im Hintergrund neu rechnen."""
        self.vorher = {z.get("stufe_id"): z.get("preis_einheit") for z in self.zeilen}
        self._spalten_zeigen()
        self.stand(speichern=feld not in ("schluessel", "menge"))
        self.s.verlauf.merken()         # Schritt für Rückgängig

    # -------------------------------------------------------------- Stufen
    def neu(self):
        self.s.db.staffel_neu(self.s.id)
        self.s.neu_laden()
        i = self.modell.index(len(self.s.stufen) - 1, 0)
        self.s.reiter.setCurrentWidget(self)
        self.ansicht.setCurrentIndex(i)
        self.ansicht.edit(i)

    def aus_angebot(self):
        """Je Satz und je Position ohne Satz eine Stufe mit der aktuellen Menge anlegen (nur, was noch fehlt)."""
        da = {staffeln.txt(s.get("schluessel")) for s in self.s.stufen}
        neu = [(schl, menge) for schl, _, menge in staffeln.auswahl(self.s.positionen) if schl not in da]
        if not neu:
            self.s.f.meldung("Alle Sätze und Positionen stehen schon in den Staffeln.", fehler=not self.s.stufen)
            return 0
        for schl, menge in neu:
            self.s.db.staffel_neu(self.s.id, dict(schluessel=schl, menge=menge))
        self.s.neu_laden()
        self.s.reiter.setCurrentWidget(self)
        self.s.f.meldung(f"{len(neu)} Stufe(n) angelegt. Weitere Mengen mit Neue Stufe ergänzen.")
        return len(neu)

    def loeschen(self):
        zeilen = sorted({i.row() for i in self.ansicht.selectionModel().selectedIndexes()})
        if not zeilen:
            self.s.f.meldung("Bitte zuerst die Stufen markieren, die gelöscht werden sollen.", fehler=True)
            return
        self.s.db.staffeln_loeschen([self.s.stufen[r]["id"] for r in zeilen])
        self.s.neu_laden()

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
            zeilen = staffeln.rechnen_alle(*self._args(), fortschritt=weiter, alt=alt)
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
        alt = copy.deepcopy((self.s.kopf.get("staffelpreise") or {}).get("zeilen"))
        kenn = self.kennung()

        def lauf():
            try:
                zeilen = staffeln.rechnen_alle(*args, alt=alt)
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
