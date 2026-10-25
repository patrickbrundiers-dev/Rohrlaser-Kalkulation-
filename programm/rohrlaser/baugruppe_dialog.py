"""Editor 'Schweißbaugruppe' (Plan Schweißbaugruppen, Teil 2): Kopf (Bezeichnung, Artikelnummer, Anzahl), Reiter
Stammdaten, Struktur und Teile (Unterbaugruppen mit Menge, Einzelteile aus der Positionsliste), Nahtgruppen,
Arbeitsgänge (mit Einmalkosten und Umlage) und Übersicht. Gerechnet wird mit baugruppe.rechnen, live bei jeder
Eingabe; gespeichert wird erst mit OK (ergebnis), das Angebot schreibt dann Position und Zuordnung der Teile.

Kennwerte einer Nahtgruppe: Beim Speichern merkt sich jede vollständig berechenbare Nahtgruppe ihren Stand
(baugruppe.naht_stand), damit spätere Änderungen der Stammdaten ein Angebot nicht verändern. Ändert man Verfahren,
Nahtart, Nahtgröße, Lage, Zugänglichkeit oder Qualität, gilt der neue Stand aus den Stammdaten; 'Kennwerte neu aus
Stammdaten' setzt alle Nahtgruppen auf die aktuellen Stammdaten."""
import copy
import datetime
import html
import json
import math
import re

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
                               QGroupBox, QInputDialog, QMessageBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import baugruppe, baugruppe_vorschlaege as bv, blech, hilfe, naht, schneidweg, skizze, steckverbindung, stil, vorkalk
from .baugruppe_step import StepBaugruppe
from .kostenbalken import Kostenbalken
from .angebot import BAUGRUPPE, ist_baugruppe, kein_laserteil
from .stammdaten import NACHARBEIT_STUFEN, NAHTARTEN, POSITIONIERHILFEN, zahl_als_text, zahl_aus_text
from .stil import BLAU_FLAECHE, GELB_FLAECHE, GELB_TEXT

FEHLER_FARBE = "#B42318"
GRAU = "#5F6B7A"
WARNUNG = "warnung"         # Anzeige (Text, WARNUNG): Zeile gelb hinterlegt (D4)
VORLAGEN = "baugruppen_vorlagen"
RICHTWERT = (f"<span style='background: {BLAU_FLAECHE}; color: #1F4E78; border-radius: 3px;'>&nbsp;Richtwert&nbsp;"
             "</span>")
DIREKT = "(Baugruppe selbst)"
NAHT_SCHLUESSEL = ("verfahren", "nahtart", "mass", "lage", "zugang", "qualitaet")    # neuer Stand, wenn geändert
ARBEITSGAENGE = ("Vorrichten", "Heften", "Richten", "Schleifen", "Verputzen", "Entgraten", "Bohren", "Gewindeschneiden",
                 "Montage", "Prüfen", "Reinigen", "Verpacken", "Vorrichtung", "Programmierung Roboter",
                 "Strahlen (Fremd)", "Verzinken (Fremd)", "Pulverbeschichten (Fremd)")
LANGTEXT = ("beschreibung", "bemerkung", "intern")
HERKUNFT = {vorkalk.VORSCHLAG: "Vorschlag der Vorkalkulation (gelb, mit „Vorschläge bestätigen“ übernehmen)",
            vorkalk.BESTAETIGT: "Vorschlag bestätigt", vorkalk.HAND: "von Hand (die Vorkalkulation lässt den Wert stehen)"}


def _text(w, stellen=None):
    return zahl_als_text(w, stellen, tausender=False) if isinstance(w, (int, float)) and not isinstance(w, bool) else ""


def _euro(w):
    return zahl_als_text(round(w or 0.0, 2), 2) + " €"


def _min(w):
    return zahl_als_text(round(w or 0.0, 1), 1) + " min"


class Spalte:
    """Spalte einer ZeilenTabelle. typ: text, zahl, ganz, auswahl (optionen() = [(Text, Wert)], frei = eigene Texte
    erlaubt), haken oder anzeige (anzeige(zeile, index) = Text, nur lesen; (Text, True) rot, (Text, WARNUNG) gelb
    hinterlegt mit markierter Zeilennummer). vk: Feld zeigt die Herkunft der Vorkalkulation (Vorschlag gelb, Tooltip
    mit Begründung), siehe ZeilenTabelle.herkunft."""

    def __init__(self, schluessel, titel, typ="text", breite=90, optionen=None, frei=False, anzeige=None, tipp="",
                 vk=False):
        self.schluessel, self.titel, self.typ, self.breite = schluessel, titel, typ, breite
        self.optionen, self.frei, self.anzeige, self.tipp, self.vk = optionen, frei, anzeige, tipp, vk


class ZeilenTabelle(QTableWidget):
    """Tabelle über einer Liste von dicts (self.zeilen): jede Eingabe ändert sofort das dict und ruft geaendert();
    Anzeigespalten werden mit auffrischen() neu beschriftet. Ungültige Zahlen: Feld rot, Wert None, in self.ungueltig.
    herkunft(zeile, schlüssel) = (Status, Begründung) oder None für Spalten mit vk (Vorkalkulation)."""

    def __init__(self, spalten, zeilen, geaendert, herkunft=None):
        super().__init__(0, len(spalten))
        self.spalten, self.zeilen, self.geaendert, self.herkunft = spalten, zeilen, geaendert, herkunft
        self.ungueltig = set()
        self.setHorizontalHeaderLabels([s.titel for s in spalten])
        for c, s in enumerate(spalten):
            self.setColumnWidth(c, s.breite)
            if s.tipp:
                self.horizontalHeaderItem(c).setToolTip(s.tipp)
        self.horizontalHeader().setSectionResizeMode(len(spalten) - 1, QHeaderView.Stretch)
        self.horizontalHeader().setMinimumHeight(40)         # zweizeilige Spaltentitel
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.verticalHeader().setDefaultSectionSize(28)
        self.aufbauen()

    def aufbauen(self):
        self.setRowCount(0)         # alte Felder weg, sonst bleiben sie bis zum nächsten Ereignis sichtbar
        self.setRowCount(len(self.zeilen))
        self.ungueltig = set()
        for r, z in enumerate(self.zeilen):
            for c, s in enumerate(self.spalten):
                self.setCellWidget(r, c, self._feld(z, s))
        self.auffrischen()

    def _feld(self, z, s):
        w = z.get(s.schluessel)
        if s.typ == "haken":
            f = QCheckBox()
            f.setChecked(bool(w))
            f.toggled.connect(lambda an, z=z, s=s: self._setzen(z, s, bool(an)))
            huelle = QWidget()
            lay = QHBoxLayout(huelle)
            lay.setContentsMargins(6, 0, 0, 0)
            lay.addWidget(f)
            huelle.feld = f
            return huelle
        if s.typ == "auswahl":
            f = QComboBox()
            f.setEditable(s.frei)
            self._optionen_setzen(f, s, w)
            if s.frei:
                f.currentTextChanged.connect(lambda t, z=z, s=s: self._setzen(z, s, t.strip() or None))
            else:
                f.currentIndexChanged.connect(lambda i, f=f, z=z, s=s: self._setzen(z, s, f.itemData(i)))
            return f
        if s.typ == "anzeige":
            f = QLabel()
            f.setTextFormat(Qt.RichText)
            f.setStyleSheet(f"color: {GRAU}; padding-left: 4px;")
            return f
        f = QLineEdit(_text(w) if s.typ in ("zahl", "ganz") else str(w or ""))
        if s.typ in ("zahl", "ganz"):
            f.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        f.textChanged.connect(lambda t, f=f, z=z, s=s: self._text(f, z, s, t))
        return f

    def _optionen_setzen(self, f, s, w):
        f.blockSignals(True)
        f.clear()
        optionen = list(s.optionen() if callable(s.optionen) else s.optionen or ())
        for text, wert in optionen:
            f.addItem(text, wert)
        i = next((i for i, (_, wert) in enumerate(optionen) if wert == w), -1)
        if i < 0 and w not in (None, ""):
            f.addItem(f"{w} (unbekannt)" if not s.frei else str(w), w)
            i = f.count() - 1
        f.setCurrentIndex(max(i, 0) if optionen or i >= 0 else -1)
        if s.frei:
            f.setEditText(str(w or ""))
        f.blockSignals(False)

    def optionen_neu(self):
        """Auswahllisten neu füllen (z. B. nach neuer Unterbaugruppe), gewählte Werte bleiben."""
        for r, z in enumerate(self.zeilen):
            for c, s in enumerate(self.spalten):
                if s.typ == "auswahl" and callable(s.optionen):
                    self._optionen_setzen(self.cellWidget(r, c), s, z.get(s.schluessel))

    def _text(self, f, z, s, t):
        t = t.strip()
        if s.typ in ("zahl", "ganz"):
            try:
                w = zahl_aus_text(t) if t else None
                if w is not None and s.typ == "ganz":
                    w = int(round(w))
                self.ungueltig.discard((id(z), s.schluessel))
                f.setStyleSheet("")
            except ValueError:
                w = None
                self.ungueltig.add((id(z), s.schluessel))
                f.setStyleSheet(f"color: {FEHLER_FARBE};")
            self._setzen(z, s, w)
        else:
            self._setzen(z, s, t or None)

    def _setzen(self, z, s, w):
        if w is None:
            z.pop(s.schluessel, None)
        else:
            z[s.schluessel] = w
        self.geaendert()

    def auffrischen(self):
        self.warnzeilen = set()
        for r, z in enumerate(self.zeilen):
            for c, s in enumerate(self.spalten):
                if s.typ == "anzeige" and s.anzeige:
                    w = self.cellWidget(r, c)
                    t = s.anzeige(z, r)
                    w.setText(html.escape(t[0] if isinstance(t, tuple) else t).replace(html.escape(RICHTWERT), RICHTWERT))
                    art = t[1] if isinstance(t, tuple) else None
                    if art == WARNUNG:
                        self.warnzeilen.add(r)
                        w.setStyleSheet(f"color: {GELB_TEXT}; background: {GELB_FLAECHE}; padding-left: 4px;")
                    else:
                        w.setStyleSheet(f"color: {FEHLER_FARBE if art else GRAU}; padding-left: 4px;")
                elif s.vk and self.herkunft:
                    self._herkunft_zeigen(self.cellWidget(r, c), z, s)
            kopf = self.verticalHeaderItem(r) or QTableWidgetItem(str(r + 1))
            kopf.setText(f"⚠ {r + 1}" if r in self.warnzeilen else str(r + 1))
            kopf.setToolTip("Zeile prüfen (Hinweis)" if r in self.warnzeilen else "")
            kopf.setBackground(stil.farbe(GELB_FLAECHE) if r in self.warnzeilen else QBrush())
            self.setVerticalHeaderItem(r, kopf)

    def _herkunft_zeigen(self, w, z, s):
        """Vorschlag gelb mit Begründung im Tooltip; bestätigt und von Hand normal, Tooltip nennt die Herkunft."""
        if (id(z), s.schluessel) in self.ungueltig:
            return
        h = self.herkunft(z, s.schluessel)
        st, grund = h if h else (None, None)
        stil_neu = f"background: {GELB_FLAECHE}; color: {GELB_TEXT};" if st == vorkalk.VORSCHLAG else ""
        ziel = getattr(w, "feld", w)
        if ziel.styleSheet() != stil_neu:
            ziel.setStyleSheet(stil_neu)
        w.setToolTip(f"{HERKUNFT[st]}: {grund}" if st and grund else HERKUNFT.get(st, ""))

    def zeigen(self, r):
        """Zeile r markieren und hineinscrollen (Sprung vom Status, D4)."""
        if 0 <= r < self.rowCount():
            self.selectRow(r)
            self.scrollTo(self.model().index(r, 0))

    def markierte(self):
        return sorted({i.row() for i in self.selectionModel().selectedRows()})


def gravierbar(q):
    """Artikelnummer gravierbar: Rohrlaserteil oder Blechteil aus dem Blech-Editor."""
    return not kein_laserteil(q) or blech.lesen(q.get("technik")) is not None


def blech_gravur_alt(q, hoehe):
    """Blechteil, dessen Gravur-Zeile nicht mehr zur Artikelnummer bzw. Schrifthöhe passt (neu schreiben)."""
    e = blech.lesen(q.get("technik"))
    if e is None:
        return False
    z = next((z for z in e.get("konturen") or () if z.get("art") == blech.sw.TEXT_GRAVUR and z.get("artikel")),
             None)
    if not hoehe:
        return z is not None
    return z is None or z.get("text") != str(q.get("artikel") or "").strip() or z.get("hoehe") != hoehe


NAHT_TOLERANZ = 1.0      # mm: gezeichneter Nahtpunkt gilt als am Teil, wenn er so nah an dessen Oberfläche liegt


def _abstand_dreieck(q, a, b, c):
    """Abstand Punkt q zum Dreieck a, b, c (nächster Punkt nach Ericson, Real-Time Collision Detection 5.1.5)."""
    ab, ac, aq = [b[k] - a[k] for k in range(3)], [c[k] - a[k] for k in range(3)], [q[k] - a[k] for k in range(3)]
    dot = lambda u, v: u[0] * v[0] + u[1] * v[1] + u[2] * v[2]  # noqa: E731
    d1, d2 = dot(ab, aq), dot(ac, aq)
    if d1 <= 0 and d2 <= 0:
        return math.dist(q, a)
    bq = [q[k] - b[k] for k in range(3)]
    d3, d4 = dot(ab, bq), dot(ac, bq)
    if d3 >= 0 and d4 <= d3:
        return math.dist(q, b)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        v = d1 / (d1 - d3)
        return math.dist(q, [a[k] + v * ab[k] for k in range(3)])
    cq = [q[k] - c[k] for k in range(3)]
    d5, d6 = dot(ab, cq), dot(ac, cq)
    if d6 >= 0 and d5 <= d6:
        return math.dist(q, c)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        w = d2 / (d2 - d6)
        return math.dist(q, [a[k] + w * ac[k] for k in range(3)])
    va = d3 * d6 - d5 * d4
    if va <= 0 and d4 - d3 >= 0 and d5 - d6 >= 0:
        w = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        return math.dist(q, [b[k] + w * (c[k] - b[k]) for k in range(3)])
    n = 1.0 / (va + vb + vc)
    v, w = vb * n, vc * n
    return math.dist(q, [a[k] + ab[k] * v + ac[k] * w for k in range(3)])


def _abstand_flaeche(q, p, dreiecke):
    """Kleinster Abstand von q zu den Dreiecken (Punktnummern je 3) im Punktfeld p."""
    beste = math.inf
    for i in range(0, len(dreiecke) - 2, 3):
        a, b, c = (p[3 * dreiecke[i + j]:3 * dreiecke[i + j] + 3] for j in range(3))
        if any(q[k] < min(a[k], b[k], c[k]) - beste or q[k] > max(a[k], b[k], c[k]) + beste for k in range(3)):
            continue                                        # Hüllquader des Dreiecks weiter weg als der beste
        beste = min(beste, _abstand_dreieck(q, a, b, c))
        if beste < 1e-6:
            break
    return beste


class StrukturBaum(QTreeWidget):
    """Baum Baugruppe → Unterbaugruppen → Einzelteile und Nahtgruppen (D1). Einzelteile lassen sich auf eine
    (Unter-)Baugruppe ziehen: verschieben(Positions-ID, Knoten-ID); den Baum baut danach der Dialog neu."""

    def __init__(self, verschieben):
        super().__init__()
        self.verschieben = verschieben
        self.setHeaderLabels(["Struktur", "Menge", "Stück je Baugruppe"])
        self.setColumnWidth(0, 300)
        self.setColumnWidth(1, 60)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)

    def dropEvent(self, e):
        quelle, ziel = self.currentItem(), self.itemAt(e.position().toPoint())
        e.ignore()                  # nichts im Baum selbst verschieben: der Dialog ordnet zu und baut neu auf
        if quelle is None or ziel is None:
            return
        art, pid = quelle.data(0, Qt.UserRole)
        while ziel is not None and ziel.data(0, Qt.UserRole)[0] not in ("bg", "knoten"):
            ziel = ziel.parent()
        if art == "teil" and ziel is not None:
            kn = ziel.data(0, Qt.UserRole)[1]
            QTimer.singleShot(0, lambda: self.verschieben(pid, kn))


class SteckEditor:
    """Steckverbindungen (Plan K2) und Rohre aus den Eingaben für die 3D-Ansicht (B2), gemeinsam für den Editor der
    Schweißbaugruppe und das Fenster „Satz in 3D“ (Patrick 24.10.2026: Schritte eines Editors auch in den anderen).
    Erwartet self.teile (je Teil _id, _q = Position, drin, knoten), self.teile_tab, self.bg['steckverbindungen']
    (Zeilen der Tabelle) und ['stoesse'], self.profile, self.einstellungen, self.netze, self._netz_cache,
    self.nur_lesen und self.aktualisieren()."""
    STECK_WAS = "Baugruppe"     # im Text: „Teile dieser Baugruppe“
    STECK_MARKIEREN = "im Reiter „Struktur und Teile“"
    STECK_OHNE_STOESSE = ("Nur Baugruppen aus dem STEP-Import (Häkchen „als Schweißbaugruppe“) kennen die Lage der "
                          "Rohrenden.")

    # -------------------------------------------------------------- Steckverbindungen (Plan K2)
    def _steck_flach(self, v):
        """Verbindung als Zeile der Tabelle: Aufnahme, Stecker und Ende als eigene Felder."""
        z = copy.deepcopy(v)
        z["_auf"] = (v.get("aufnahme") or {}).get("id")
        z["_st"] = (v.get("stecker") or {}).get("id")
        z["_ende"] = (v.get("stecker") or {}).get("ende") or "a"
        z["_schlitze"], z["_nasen"] = v.get("schlitze") is not False, v.get("nasen") is not False
        return z

    def _steck_daten(self, z):
        """Zeile der Tabelle -> gespeicherte Verbindung (Aufnahme und Stecker mit Position und Unterbaugruppe)."""
        v = {k: w for k, w in z.items() if not k.startswith("_")}
        teile = {t["_id"]: t for t in self.teile}
        for rolle, pid in (("aufnahme", z.get("_auf")), ("stecker", z.get("_st"))):
            t = teile.get(pid)
            v[rolle] = dict(id=pid, pos=t["_q"].get("pos") if t else None, knoten=(t or {}).get("knoten") or "")
        v["stecker"]["ende"] = z.get("_ende") or "a"
        for k in ("schlitze", "nasen"):
            v.pop(k, None)
            if z.get("_" + k) is False:
                v[k] = False
        return v

    def _steck_profil(self, pid):
        t = next((t for t in self.teile if t["_id"] == pid), None)
        return self.profile.get(t["_q"].get("profil_id")) if t else None

    def _steck_einst(self):
        return {n[6:]: w for n, w in self.einstellungen.items() if n.startswith("steck_")}

    def _steck_fehler(self, z):
        ids = {t["_id"] for t in self.teile if t.get("drin")}
        if z.get("_auf") not in ids or z.get("_st") not in ids:
            return f"Aufnahme und Stecker müssen Teile dieser {self.STECK_WAS} sein"
        if z.get("_nasen") is not False:        # je Ende des Steckers nur eine Verbindung mit Nasen
            for n, y in enumerate(self.bg["steckverbindungen"], 1):
                if y is z:
                    break
                if y.get("_st") == z.get("_st") and y.get("_ende") == z.get("_ende") and y.get("_nasen") is not False:
                    return (f"Ende {'A' if z.get('_ende') == 'a' else 'E'} des Steckers hat schon Nasen aus "
                            f"Steckverbindung {n}: Haken „Nasen schneiden“ weg")
        return steckverbindung.pruefen(self._steck_daten(z), self._steck_profil(z["_auf"]) or {},
                                       self._steck_profil(z["_st"]) or {})

    def _steck_teile(self):
        return [(f"Pos. {t['_q'].get('pos') or ''} {t['_q'].get('artikel') or t['_q'].get('profil_id') or ''}".strip(),
                 t["_id"]) for t in self.teile if t.get("drin") and t["_q"].get("profil_id")]

    def _steck_text(self, z, _r):
        f = self._steck_fehler(z)
        if f:
            return (f, True)
        v = self._steck_daten(z)
        return steckverbindung.text(v, steckverbindung.masse(v, self._steck_profil(z["_auf"]),
                                                              self._steck_profil(z["_st"])))

    def _seite_stecken(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.steck_tab = ZeilenTabelle([
            Spalte("_auf", "Aufnahme\n(Schlitze)", "auswahl", 170, optionen=self._steck_teile),
            Spalte("_st", "Stecker\n(Nasen)", "auswahl", 170, optionen=self._steck_teile),
            Spalte("_ende", "Ende\nStecker", "auswahl", 60, optionen=[("A", "a"), ("E", "b")]),
            Spalte("x", "Lage x auf der\nAufnahme [mm]", "zahl", 95, tipp="Mitte des Steckers ab Ende A der Aufnahme"),
            Spalte("seite", "Seite der\nAufnahme", "auswahl", 80, frei=True,
                   optionen=[(t, t) for t in steckverbindung.SEITEN_KASTEN],
                   tipp="Wand der Aufnahme, an der der Stecker sitzt (Rundrohr: Winkel, z. B. 90°)"),
            Spalte("anzahl", "Nasen", "auswahl", 55, optionen=[(str(n), n) for n in steckverbindung.ANZAHLEN]),
            Spalte("bN", "Nasen-\nbreite [mm]", "zahl", 70),
            Spalte("c", "Spiel je\nSeite [mm]", "zahl", 65),
            Spalte("ueberstand", "Über-\nstand [mm]", "zahl", 60),
            Spalte("waende", "Wände mit\nNasen", "auswahl", 75, optionen=[(t, t) for t in steckverbindung.WAENDE],
                   tipp="quer = Wände quer zur Achse der Aufnahme (Vorgabe), längs = um 90° gedreht"),
            Spalte("winkel", "Winkel der\nAchsen [°]", "zahl", 70, tipp="90 = senkrecht, schräg bis 30°"),
            Spalte("_schlitze", "Schlitze\nschneiden", "haken", 65,
                   tipp="Aus: gleiches Teil, die Schlitze schneidet schon eine andere Verbindung"),
            Spalte("_nasen", "Nasen\nschneiden", "haken", 65,
                   tipp="Aus: dieses Ende des Steckers hat die Nasen schon aus einer anderen Verbindung"),
            Spalte("_text", "Schlitz und Nasen", "anzeige", 260, anzeige=self._steck_text)],
            self.bg["steckverbindungen"], self.aktualisieren)
        lay.addWidget(self.steck_tab, 1)
        leiste = QHBoxLayout()
        neu = QPushButton("Steckverbindung hinzufügen")
        neu.setToolTip(f"Zwischen den zwei {self.STECK_MARKIEREN} markierten Teilen (sonst den ersten beiden Rohren "
                       f"der {self.STECK_WAS}); Vorgaben aus den Einstellungen")
        neu.clicked.connect(lambda: self.steck_neu())
        tausch = QPushButton("Aufnahme und Stecker tauschen")
        tausch.clicked.connect(lambda: self.steck_tauschen())
        alle = QPushButton("Alle Stöße stecken")
        alle.setToolTip("Je Rohrende, das in der STEP-Datei auf einem anderen Rohr sitzt, eine Steckverbindung mit "
                        "Lage und Seite aus der Datei (nur aus dem STEP-Import)")
        alle.clicked.connect(lambda: self.steck_alle())
        weg = QPushButton("Markierte entfernen")
        weg.setToolTip("Schlitze und Nasen fallen beim Speichern in beiden Teilen weg")
        weg.clicked.connect(lambda: self.steck_entfernen())
        for b in (neu, alle, tausch, weg):
            b.setEnabled(not self.nur_lesen if hasattr(self, "nur_lesen") else True)
            leiste.addWidget(b)
        leiste.addStretch(1)
        lay.addLayout(leiste)
        lay.addWidget(hilfe.Hinweis(
            "Der Stecker stößt mit einem Ende an die Aufnahme. Beim Speichern bekommt die Aufnahme je Nase einen "
            "Schlitz (Rechteck mit Spiel), das Ende des Steckers die Nasen; Schneidweg, Einstiche und die Länge des "
            "Steckers werden neu gerechnet. Lage x und Seite: Mitte des Steckers auf der Aufnahme.",
            schluessel="baugruppe_steckverbindungen"))
        return w

    def steck_neu(self, auf=None, st=None, **werte):
        """Neue Steckverbindung (auf/st = Positions-IDs; ohne: markierte Teile bzw. die ersten beiden Rohre). Der
        Stecker ist das zweite Teil. Ergebnis: Kennung oder None."""
        if auf is None or st is None:
            rohre = [t for t in self.teile if t.get("drin") and (self.profile.get(t["_q"].get("profil_id")) or {})
                     .get("form") in steckverbindung.FORMEN]
            mark = [self.teile[r] for r in self.teile_tab.markierte() if r < len(self.teile)]
            wahl = [t for t in mark if t in rohre] if len(mark) == 2 else rohre[:2]
            if len(wahl) < 2:
                QMessageBox.information(self, "Steckverbindung", f"Die {self.STECK_WAS} braucht zwei Rohre (Quadrat-, "
                                        f"Rechteck- oder Rundrohr); {self.STECK_MARKIEREN} zwei markieren.")
                return None
            auf, st = wahl[0]["_id"], wahl[1]["_id"]
        teile = {t["_id"]: t["_q"] for t in self.teile}
        v = steckverbindung.neu(teile[auf], teile[st], self._steck_profil(st) or {}, self._steck_einst(),
                                **werte) if (self._steck_profil(st) or {}).get("form") in steckverbindung.FORMEN \
            else dict(id=baugruppe.neue_id(), aufnahme=dict(id=auf), stecker=dict(id=st, ende=werte.get("ende") or "a"),
                      anzahl=2, c=0.1, **{k: w for k, w in werte.items() if k in ("x", "seite") and w is not None})
        self.bg["steckverbindungen"].append(self._steck_flach(v))
        self.steck_tab.aufbauen()
        self.aktualisieren()
        return v["id"]

    def steck_plan(self):
        """Steckverbindungen aus den Stößen der STEP-Messung (bg['stoesse']: Rohrende an Rohrwand, Körpernummern), wie
        „Alle Stöße stecken“ sie anlegt: [dict(auf, st, ende, x, seite, winkel, schlitze, nasen)] und die Zahl der
        Stöße, die keinem Rohr zugeordnet werden können. Gleiche Teile: Schlitze nur am ersten Körper der Aufnahme,
        Nasen je Ende des Steckers nur einmal; schon vorhandene Verbindungen bleiben (nicht im Plan). None ohne
        Stöße."""
        stoesse = [s_ for s_ in self.bg.get("stoesse") or () if isinstance(s_, dict)]
        if not stoesse:
            return None, 0
        besitzer = {}
        for t in self.teile:
            if t.get("drin") and (self._steck_profil(t["_id"]) or {}).get("form") in steckverbindung.FORMEN:
                for k in self._netz(t["_id"]).get("koerper") or ():
                    besitzer.setdefault(str(k), set()).add(t["_id"])
        erster = {}                 # Aufnahme -> erster Körper (dort die Schlitze)
        for s_ in sorted(stoesse, key=lambda x: (len(str(x.get("aufnahme"))), str(x.get("aufnahme")))):
            ids = besitzer.get(str(s_.get("aufnahme"))) or ()
            if len(ids) == 1:
                erster.setdefault(next(iter(ids)), str(s_.get("aufnahme")))
        vorhanden = self.bg["steckverbindungen"]
        schlitze = {(z.get("_auf"), round(float(z.get("x") or 0)), str(z.get("seite") or ""))
                    for z in vorhanden if z.get("_schlitze") is not False}
        nasen = {(z.get("_st"), z.get("_ende")) for z in vorhanden if z.get("_nasen") is not False}
        plan, weg = [], 0
        for s_ in stoesse:
            auf_, st_ = besitzer.get(str(s_.get("aufnahme"))) or (), besitzer.get(str(s_.get("stecker"))) or ()
            ende = s_.get("ende") if s_.get("ende") in ("a", "b") else None
            if len(auf_) != 1 or len(st_) != 1 or not ende or not isinstance(s_.get("z"), (int, float)):
                weg += 1
                continue
            auf, st = next(iter(auf_)), next(iter(st_))
            if self._steck_profil(auf).get("form") == "Rundrohr":
                seite = skizze.winkel_text(s_["winkel"]) if isinstance(s_.get("winkel"), (int, float)) else None
            else:
                seite = steckverbindung.SEITE_STEP.get(s_.get("seite"))
            x = round(float(s_["z"]), 1)
            ort = erster.get(auf) == str(s_.get("aufnahme"))
            mit_schlitz = ort and (auf, round(x), str(seite or "")) not in schlitze
            mit_nasen = (st, ende) not in nasen
            if not (mit_schlitz or mit_nasen):
                continue
            w = s_.get("achswinkel")
            plan.append(dict(auf=auf, st=st, ende=ende, x=x, seite=seite, schlitze=mit_schlitz, nasen=mit_nasen,
                             schlitz_ort=ort,
                             winkel=round(w, 1) if isinstance(w, (int, float))
                             and steckverbindung.WINKEL_MIN <= w < 89.5 else None))
            schlitze.add((auf, round(x), str(seite or "")))
            nasen.add((st, ende))
        return plan, weg

    def steck_schnitte(self, e):
        """Schlitze/Nasen eines Plan-Eintrags gegen die jetzt vorhandenen Verbindungen neu bestimmen (wer nur einen
        späteren Vorschlag übernimmt, braucht dessen Schlitze und Nasen selbst). None: beides gibt es schon."""
        vorhanden = self.bg["steckverbindungen"]
        mit_schlitz = e.get("schlitz_ort", e["schlitze"]) and not any(
            z.get("_schlitze") is not False and (z.get("_auf"), round(float(z.get("x") or 0)), str(z.get("seite") or ""))
            == (e["auf"], round(e["x"]), str(e["seite"] or "")) for z in vorhanden)
        mit_nasen = not any(z.get("_nasen") is not False and (z.get("_st"), z.get("_ende")) == (e["st"], e["ende"])
                            for z in vorhanden)
        if not (mit_schlitz or mit_nasen):
            return None
        return dict(e, schlitze=bool(mit_schlitz), nasen=mit_nasen)

    def steck_zeile(self, e):
        """Zeile der Tabelle Steckverbindungen für einen Eintrag von steck_plan (noch nicht angelegt)."""
        teile = {t["_id"]: t["_q"] for t in self.teile}
        profil = self._steck_profil(e["st"]) or {}
        if profil.get("form") in steckverbindung.FORMEN:
            v = steckverbindung.neu(teile[e["auf"]], teile[e["st"]], profil, self._steck_einst(), ende=e["ende"],
                                    x=e["x"], seite=e["seite"])
        else:
            v = dict(id=baugruppe.neue_id(), aufnahme=dict(id=e["auf"]), stecker=dict(id=e["st"], ende=e["ende"]),
                     anzahl=2, c=0.1, x=e["x"], seite=e["seite"])
        z = self._steck_flach(v)
        if e.get("winkel") is not None:
            z["winkel"] = e["winkel"]
        z["_schlitze"], z["_nasen"] = e["schlitze"], e["nasen"]
        return z

    def steck_alle(self, melden=True):
        """„Alle Stöße stecken“: je Stoß der STEP-Messung eine Verbindung mit Lage, Seite und Achswinkel aus der Datei
        (steck_plan). Ergebnis: (neu, übersprungen)."""
        plan, weg = self.steck_plan()
        if plan is None:
            if melden:
                QMessageBox.information(self, "Alle Stöße stecken", f"Keine Stöße aus der STEP-Datei: "
                                        f"{self.STECK_OHNE_STOESSE} Sonst mit „Steckverbindung hinzufügen“ anlegen.")
            return 0, 0
        for e in plan:
            self.bg["steckverbindungen"].append(self.steck_zeile(e))
        neu = len(plan)
        self.steck_tab.aufbauen()
        self.aktualisieren()
        if melden:
            QMessageBox.information(self, "Alle Stöße stecken", f"{neu} Steckverbindung(en) angelegt"
                                    + (f", {weg} Stoß/Stöße nicht zuordenbar (Teil fehlt in der {self.STECK_WAS} oder ist "
                                       "kein Rohr)" if weg else "") + ". Lage und Seite bitte prüfen.")
        return neu, weg

    def steck_entfernen(self):
        for r in reversed(self.steck_tab.markierte()):
            del self.bg["steckverbindungen"][r]
        self.steck_tab.aufbauen()
        self.aktualisieren()

    def steck_tauschen(self, zeilen=None):
        for r in zeilen if zeilen is not None else self.steck_tab.markierte():
            z = self.bg["steckverbindungen"][r]
            v = steckverbindung.tauschen(self._steck_daten(z), self._steck_profil(z.get("_auf")) or {},
                                         self._steck_einst()) if self._steck_profil(z.get("_auf")) else None
            if v:
                self.bg["steckverbindungen"][r] = self._steck_flach(v)
        self.steck_tab.aufbauen()
        self.aktualisieren()

    def _netz(self, pid):
        if pid not in self._netz_cache:
            from .ansicht3d import entpacken
            self._netz_cache[pid] = entpacken(self.netze.get(pid)) or {}
        return self._netz_cache[pid]

    def _rohr_eingaben(self):
        """Eingaben und Länge der Rohre mit den Steckverbindungen des Editors {Positions-ID: (Eingaben, Länge)} und
        die Winkel der Nasen {Positions-ID: {Ende: Winkel}} (für 3D und STEP-Export)."""
        from .baugruppe_ansicht import eingaben_stecken, nasen_winkel
        drin = {t["_id"]: t["_q"] for t in self.teile if t.get("drin") and self._steck_profil(t["_id"])}
        verbindungen = [self._steck_daten(z) for z in self.bg.get("steckverbindungen") or ()
                        if z.get("_auf") in drin and z.get("_st") in drin]
        eing = eingaben_stecken(drin, verbindungen, self._steck_profil)
        winkel = {}
        for v in verbindungen:
            if v.get("nasen") is False:
                continue
            auf, st = self._netz(v["aufnahme"]["id"]), self._netz(v["stecker"]["id"])
            la = (auf.get("lagen") or [auf.get("lage")])[0]
            ls = (st.get("lagen") or [st.get("lage")])[0]
            w = nasen_winkel(v, la, ls, (self._steck_profil(v["stecker"]["id"]) or {}).get("form"))
            if w is not None:
                winkel.setdefault(v["stecker"]["id"], {})[v["stecker"]["ende"]] = w
        return eing, winkel

    def _rohr_modelle(self):
        """Rohre aus den Eingaben (B2): {Positions-ID: Netz im Rohrsystem} mit den Steckverbindungen des Editors;
        Teile ohne Eingaben, Biegerohr, Knickrahmen oder mit Anbauteilen fehlen (dort bleibt das STEP-Netz)."""
        from .baugruppe_ansicht import eigenes_modell, rohr_netz
        eing, winkel = self._rohr_eingaben()
        cache = self.__dict__.setdefault("_rohr_cache", {})
        out = {}
        for pid, (e, laenge) in eing.items():
            if not eigenes_modell(e, self._netz(pid)) or not laenge:
                continue
            schluessel = json.dumps([e, laenge, winkel.get(pid)], sort_keys=True, default=str)
            if (cache.get(pid) or (None,))[0] != schluessel:
                cache[pid] = (schluessel, rohr_netz(e, self._steck_profil(pid), laenge, winkel.get(pid)))
            if cache[pid][1]:
                out[pid] = cache[pid][1]
        return out



def knick_messwerte(teile, netz, profil):
    """Je Körper der Teile (teile = [(Positions-ID, Position)], netz(pid) = entpacktes Netz mit lage bzw. lagen,
    profil(pid) = Profil der Stammdaten) Messwerte wie aus der STEP-Messung für knickverbindung.kette: Profil, Länge,
    Lage und die Gehrungen der Enden aus den Eingaben der Position. pid und lage_nr sagen, welcher Körper es ist."""
    out = []
    for pid, q in teile:
        n, p, e = netz(pid) or {}, profil(pid) or {}, schneidweg.lesen(q.get("technik"))
        liste = [dict(art=art, form="Gehrung", gehrung=x["winkel"], richtung=x["richtung"])
                 for art, x in (("Ende A", e.get("a") or {}), ("Ende B", e.get("b") or {}))
                 if x.get("winkel") and x.get("richtung") is not None and x.get("achse") != schneidweg.ACHSE_ZWEI]
        lagen = n.get("lagen") or ([n["lage"]] if n.get("lage") else [None])
        koerper = n.get("koerper") or []
        for j, lage in enumerate(lagen):
            mehr = f" ({j + 1}/{len(lagen)})" if len(lagen) > 1 else ""
            out.append(dict(artikel=f"Pos. {_text(q.get('pos'))} {q.get('artikel') or ''}".strip() + mehr,
                            koerper=koerper[j] if j < len(koerper) else None, profilform=p.get("form"),
                            abm_a=p.get("a"), abm_b=p.get("b"), wandstaerke=p.get("wand"), laenge=q.get("laenge"),
                            _netz=dict(n, lage=lage) if lage else None, konturen_liste=json.dumps(liste), pid=pid,
                            lage_nr=j))
    return out


def knick_grund(q):
    """Grund, warum die Position nicht in einen Knickrahmen kann, oder None."""
    e = schneidweg.lesen(q.get("technik"))
    if e.get("knickrahmen"):
        return "ist schon ein Knickrahmen"
    if steckverbindung.rollen(q.get("technik")):
        return "hat eine Steckverbindung (erst entfernen)"
    return None


class KnickEditor:
    """Knickrahmen aus markierten Rohren mit Gehrung (Patrick 24.10.2026, wie im STEP-Prüfdialog), gemeinsam für das
    Fenster „Satz in 3D“ und den Editor der Schweißbaugruppe. Erwartet wie SteckEditor self.teile, self.teile_tab,
    self.bg['steckverbindungen'], self._netz, self._steck_profil, self.einstellungen, self.nur_lesen und
    self.aktualisieren(); neue Rahmen stehen in self.knicke (mit OK: angebot_fenster.knicke_anwenden)."""

    def knick_knoepfe(self):
        """Leiste mit „Knickrahmen erstellen …“ und „Knickrahmen lösen“."""
        zeile = QHBoxLayout()
        self.knick_knopf = QPushButton("Knickrahmen erstellen …")
        self.knick_knopf.setToolTip("Markierte Quadrat- oder Rechteckrohre, die mit Gehrung aneinanderstoßen, werden ein "
                                    "Knickrahmen: eine Position mit dem gestreckten Rohr und einem V-Ausschnitt je Ecke")
        self.knick_knopf.clicked.connect(lambda: self.knick_erstellen())
        self.knick_weg_knopf = QPushButton("Knickrahmen lösen")
        self.knick_weg_knopf.setToolTip("Knickrahmen der markierten Teile wieder lösen (nur die in diesem Fenster "
                                        "erstellten)")
        self.knick_weg_knopf.clicked.connect(self.knick_loesen)
        for k in (self.knick_knopf, self.knick_weg_knopf):
            k.setEnabled(not self.nur_lesen)
            zeile.addWidget(k)
        if hasattr(self, "vorschlag_knopf"):        # Vorschläge (P1) in derselben Leiste
            zeile.addWidget(self.vorschlag_knopf())
            self.vorschlag_info = QLabel()
            self.vorschlag_info.setStyleSheet(f"color: {GRAU};")
            zeile.addWidget(self.vorschlag_info, 1)
        zeile.addStretch(1)
        return zeile

    def _knick_melden(self, text, melden):
        if melden:
            QMessageBox.information(self, "Knickrahmen", text)
        return text

    def knick_erstellen(self, dialog=None, melden=True):
        """Knickrahmen aus den markierten Rohren (alle ihre Körper, ohne die schon verbundenen) wie im STEP-Prüfdialog:
        Kette erkennen, Dialog (erster Schenkel, Laufrichtung, Freistich, Zugabe, K-Faktor, Innenwand), gestreckte
        Eingaben und gefaltetes Netz. Mehrere getrennte Rahmen bekommen dieselben Werte. dialog(d) bedient den Dialog
        statt exec (Tests). Ergebnis: Anzahl neuer Knickrahmen bzw. Text, warum keiner geht."""
        from . import knickverbindung as kv
        from .knickrahmen_dialog import KnickverbindungDialog
        if self.nur_lesen:
            return 0
        teile = [self.teile[r] for r in self.teile_tab.markierte() if r < len(self.teile) and self.teile[r].get("drin")]
        if len(teile) < 1:
            return self._knick_melden("Rohre markieren (Reiter Teile oder Strg+Klick im 3D), die mit Gehrung "
                                      "aneinanderstoßen.", melden)
        for t in teile:
            grund = knick_grund(t["_q"])
            if grund:
                return self._knick_melden(f"Pos. {_text(t['_q'].get('pos'))}: {grund}.", melden)
        belegt = {kp for k in self.knicke for kp in k["koerper"]}
        steck = {z.get(r) for z in self.bg["steckverbindungen"] for r in ("_auf", "_st")}
        if steck & {t["_id"] for t in teile}:
            return self._knick_melden("Ein markiertes Teil hat eine Steckverbindung (erst im Reiter Steckverbindungen "
                                      "entfernen).", melden)
        mw = [m for m in knick_messwerte([(t["_id"], t["_q"]) for t in teile], self._netz, self._steck_profil)
              if (m["pid"], m["lage_nr"]) not in belegt]
        gruppen = kv.vorschlaege(mw)
        if not gruppen:
            try:
                kv.kette(mw, list(range(len(mw))))
                grund = "Die markierten Rohre ergeben keinen Knickrahmen."
            except ValueError as f:
                grund = str(f)
            return self._knick_melden(grund, melden)
        vorgaben = {n: self.einstellungen.get(f"knick_{n}") for n in ("z", "freistich", "k")}
        try:
            d = KnickverbindungDialog(self, mw, gruppen[0], vorgaben)
        except ValueError as f:
            return self._knick_melden(str(f), melden)
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
            return 0
        werte = d.werte()
        start_pid = mw[d.kette["teile"][0]["i"]]["pid"]
        neu = []
        try:
            for nr, gruppe in enumerate(gruppen):
                if nr == 0:
                    k = d.kette
                else:
                    start = next((i for i in gruppe if mw[i]["pid"] == start_pid), None)
                    k = kv.kette(mw, gruppe, start, d.umkehren.isChecked())
                neu.append(self.knick_bauen(mw, k, werte))
        except ValueError as f:
            return self._knick_melden(str(f), melden)
        self.knicke += neu
        self._knick_vorschlaege()
        self.aktualisieren()
        return len(neu)

    def knick_vorgaben(self):
        """Werte des Knickrahmens aus den Einstellungen (wie die Vorbelegung des Dialogs)."""
        from . import knickrahmen as kn
        z, fs, kf = (self.einstellungen.get(f"knick_{n}") for n in ("z", "freistich", "k"))
        return dict(freistich=fs or None, z=z or None, kf=kf if isinstance(kf, (int, float)) and kf > 0 else kn.K_FAKTOR,
                    schraeg=False)

    def knick_bauen(self, mw, k, werte):
        """Knickrahmen aus der Kette k der Messwerte mw (knick_messwerte; erstellen ändert sie): dict(koerper, leit,
        eingaben, laenge, knicke, netz, text, nummern, ecken). ValueError, wenn der Rahmen nicht geht."""
        from . import knickverbindung as kv
        leit = kv.erstellen(mw, k, **werte)
        m = mw[leit]
        profil = dict(self._steck_profil(m["pid"]) or {})
        je_teil = {t["i"]: schneidweg.lesen(self._teil_q(mw[t["i"]]["pid"]).get("technik")) for t in k["teile"]}
        eing, _ = kv.eingaben(m, je_teil, profil)
        nrs = [mw[t["i"]].get("koerper") for t in k["teile"]]
        return dict(koerper=[(mw[t["i"]]["pid"], mw[t["i"]]["lage_nr"]) for t in k["teile"]],
                    leit=m["pid"], eingaben=eing, laenge=m.get("_knick_laenge"), knicke=len(k["teile"]) - 1,
                    netz=kv.netz_gefaltet(mw, m), text=kv.text(m), nummern=[str(x) for x in nrs if x not in (None, "")],
                    ecken=[sorted((str(a), str(b))) for a, b in zip(nrs, nrs[1:])
                           if a not in (None, "") and b not in (None, "")])

    def knick_kandidaten(self):
        """Mögliche Knickrahmen aus allen Rohren (ohne Knickrahmen, Steckverbindung und schon neu verbundene Körper):
        (Messwerte, [Kette]) für knick_bauen."""
        from . import knickverbindung as kv
        steck = {z.get(r) for z in self.bg["steckverbindungen"] for r in ("_auf", "_st")}
        teile = [t for t in self.teile if t.get("drin") and not knick_grund(t["_q"]) and t["_id"] not in steck
                 and (self._steck_profil(t["_id"]) or {}).get("form") in ("Quadratrohr", "Rechteckrohr")]
        belegt = {kp for k in self.knicke for kp in k["koerper"]}
        mw = [m for m in knick_messwerte([(t["_id"], t["_q"]) for t in teile], self._netz, self._steck_profil)
              if (m["pid"], m["lage_nr"]) not in belegt]
        ketten = []
        for gruppe in kv.vorschlaege(mw):
            try:
                ketten.append(kv.kette(mw, gruppe))
            except ValueError:
                continue
        return mw, ketten

    def _knick_vorschlaege(self):
        """Nahtvorschläge aus der STEP-Datei an den Ecken neuer Knickrahmen fallen weg (dort wird geknickt, nicht
        geschweißt); der Stoß eines geschlossenen Rahmens bleibt. Die Vorschläge vor dem ersten Knickrahmen merkt
        sich der Editor, damit Lösen sie zurückholt."""
        ecken = {tuple(e) for k in self.knicke for e in k.get("ecken") or ()}

        def ohne_ecken(v, feld):
            """Kopie ohne die Ecken (None: alle Paare sind Ecken, fällt weg)."""
            v = copy.deepcopy(v)
            paare = v.get(feld) or []
            rest = [p for p in paare if not (isinstance(p, (list, tuple)) and len(p) == 2
                                             and tuple(sorted(map(str, p))) in ecken)]
            if paare and not rest:
                return None
            if len(rest) != len(paare):
                je = max(1, len(paare) // max(1, v.get("anzahl") or 1))
                v.update({feld: rest, "anzahl": max(1, len(rest) // je)})
            return v
        if "vorschlaege" in self.bg:
            if not hasattr(self, "_vorschlaege_vor_knick"):
                self._vorschlaege_vor_knick = copy.deepcopy(self.bg["vorschlaege"])
            self.bg["vorschlaege"] = [v for v in (ohne_ecken(x, "teile") for x in self._vorschlaege_vor_knick) if v]
            if hasattr(self, "_vorschlaege_zeigen"):
                self._vorschlaege_zeigen()
        # Nahtgruppen aus den STEP-Vorschlägen (Vorkalkulation automatisch, mit Paaren): die Ecken fallen ebenso weg,
        # Lösen holt sie zurück; Gruppen ohne Ecke bleiben, wie sie sind
        if "naehte" not in self.bg:
            return
        vor = self.__dict__.setdefault("_naehte_vor_knick", {})
        weg = self.__dict__.setdefault("_naehte_weg", set())
        for n in self.bg["naehte"]:
            if n.get("paare") and n.get("id") not in vor:
                vor[n["id"]] = copy.deepcopy(n)
        aktuell = {n.get("id"): n for n in self.bg["naehte"]}
        out, geaendert = list(self.bg["naehte"]), False
        for nid, orig in vor.items():
            neu, da = ohne_ecken(orig, "paare"), aktuell.get(nid)
            if neu is None:
                if da is not None:
                    out.remove(da)
                    weg.add(nid)
                    geaendert = True
            elif da is not None:
                if da.get("paare") != neu.get("paare"):
                    da.update(paare=neu.get("paare"), anzahl=neu.get("anzahl"))
                    geaendert = True
            elif nid in weg:
                out.append(neu)
                weg.discard(nid)
                geaendert = True
        if geaendert:
            self.bg["naehte"][:] = out
            if hasattr(self, "naht_tab"):
                self.naht_tab.aufbauen()

    def _teil_q(self, pid):
        return next(t["_q"] for t in self.teile if t["_id"] == pid)

    def knick_loesen(self):
        """Neue Knickrahmen, zu denen die markierten Teile gehören, wieder lösen. Ergebnis: Anzahl gelöster."""
        ids = {self.teile[r]["_id"] for r in self.teile_tab.markierte() if r < len(self.teile)}
        vorher = len(self.knicke)
        self.knicke = [k for k in self.knicke if not ids & {pid for pid, _ in k["koerper"]}]
        if len(self.knicke) != vorher:
            self._knick_vorschlaege()
            self.aktualisieren()
        return vorher - len(self.knicke)

    def knick_pruefen(self):
        """Fehlertext, wenn eine Steckverbindung an einem Teil eines neuen Knickrahmens hängt, sonst None."""
        im_knick = {pid for k in self.knicke for pid, _ in k["koerper"]}
        for n, z in enumerate(self.bg["steckverbindungen"], 1):
            if {z.get("_auf"), z.get("_st")} & im_knick:
                return f"Steckverbindung {n}: Teil ist in einem neuen Knickrahmen (erst Knickrahmen lösen)."
        return None


class VorschlaegeDialog(QDialog):
    """Fenster „Vorschläge“ (Plan Baugruppen automatisch, P1): je Vorschlag Haken, Art, Text, Ersparnis und
    Rechenweg; Klick auf eine Zeile zeigt die Teile im 3D. „Übernehmen“ schließt mit Accepted, die Haken stehen in
    den Vorschlägen (an)."""

    def __init__(self, besitzer, liste):
        super().__init__(besitzer)
        self.besitzer, self.liste = besitzer, liste
        self.setWindowTitle("Vorschläge")
        self.resize(1100, 480)
        lay = QVBoxLayout(self)
        kopf = QLabel("Das Programm schlägt vor, was sich hier knicken, stecken oder günstiger legen lässt, und rechnet "
                      "mit den Werten aus den Einstellungen, was es spart (+) oder kostet (−). Nichts ändert sich von "
                      "selbst: anhaken und „Übernehmen“.")
        kopf.setWordWrap(True)
        lay.addWidget(kopf)
        self.tab = QTableWidget(len(liste), 5)
        self.tab.setHorizontalHeaderLabels(["", "Art", "Vorschlag", "Ersparnis", "Rechnung"])
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tab.verticalHeader().setVisible(False)
        self.tab.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        for c, b in enumerate((28, 110, 330, 80)):
            self.tab.setColumnWidth(c, b)
        for r, v in enumerate(liste):
            haken = QTableWidgetItem()
            haken.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            haken.setCheckState(Qt.Checked if v["an"] else Qt.Unchecked)
            self.tab.setItem(r, 0, haken)
            rechnung = bv.rechnung_text(v)
            for c, text in enumerate((v["art"], v["titel"], bv.euro(v["saldo"]), rechnung), 1):
                it = QTableWidgetItem(text)
                it.setToolTip(rechnung)
                if c == 3 and v["saldo"] is not None:
                    it.setForeground(QBrush(stil.farbe_fest("#1E7B34" if v["saldo"] >= 0 else FEHLER_FARBE)))
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.tab.setItem(r, c, it)
        self.tab.itemChanged.connect(self._haken)
        self.tab.currentCellChanged.connect(lambda r, *_: self._zeigen(r))
        lay.addWidget(self.tab, 1)
        self.summe = QLabel()
        lay.addWidget(self.summe)
        leiste = QHBoxLayout()
        for text, wahl in (("Alle mit Ersparnis anhaken", lambda v: (v["saldo"] or 0) > 0),
                           ("Alle anhaken", lambda v: True), ("Keine", lambda v: False)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, w=wahl: self.anhaken(w))
            leiste.addWidget(b)
        leiste.addStretch(1)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Close)
        self.ok_knopf = knoepfe.button(QDialogButtonBox.Ok)
        self.ok_knopf.setText("Übernehmen")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        leiste.addWidget(knoepfe)
        lay.addLayout(leiste)
        self._summe()

    def anhaken(self, wahl):
        self.tab.blockSignals(True)
        for r, v in enumerate(self.liste):
            v["an"] = bool(wahl(v))
            self.tab.item(r, 0).setCheckState(Qt.Checked if v["an"] else Qt.Unchecked)
        self.tab.blockSignals(False)
        self._summe()

    def _haken(self, it):
        if it.column() == 0:
            self.liste[it.row()]["an"] = it.checkState() == Qt.Checked
            self._summe()

    def _summe(self):
        an = [v for v in self.liste if v["an"]]
        self.summe.setText(f"{len(an)} von {len(self.liste)} angehakt" + (
            f", zusammen {'+' if bv.summe(an) >= 0 else '−'}{bv.euro(abs(bv.summe(an)))} je Baugruppe bzw. Satz"
            if any(v["saldo"] is not None for v in an) else ""))
        self.ok_knopf.setEnabled(bool(an))

    def _zeigen(self, r):
        if 0 <= r < len(self.liste):
            self.besitzer.vorschlag_zeigen(self.liste[r])


class VorschlagEditor:
    """Vorschläge Knickrahmen, Steckverbindung und Längsnaht (Plan Baugruppen automatisch, P1), gemeinsam für den
    Editor der Schweißbaugruppe und das Fenster „Satz in 3D“. Rechnen: baugruppe_vorschlaege; erwartet SteckEditor,
    KnickEditor und LaengsnahtEditor. Schweißposten nur mit self.saetze (Editor der Schweißbaugruppe)."""

    def vorschlag_knopf(self):
        self.vorschlag_k = QPushButton("Vorschläge …")
        self.vorschlag_k.setToolTip("Knickrahmen, Steckverbindungen und Lage der Längsnaht vorschlagen, mit Ersparnis in €; "
                                    "nichts ändert sich ohne „Übernehmen“")
        self.vorschlag_k.clicked.connect(lambda: self.vorschlaege_zeigen())
        self.vorschlag_k.setEnabled(not self.nur_lesen)
        return self.vorschlag_k

    def _vorschlag_preise(self, laser=True):
        eltern = self.parent()
        lz = getattr(eltern, "laser_teil_eur", None) if laser else None
        if hasattr(self, "saetze"):
            return bv.Preise(self.tabellen, self.saetze, self.einstellungen, lz)
        saetze = eltern._saetze() if hasattr(eltern, "_saetze") else {}
        return bv.Preise(getattr(eltern, "tabellen", None), saetze, self.einstellungen, lz, schweissen=False)

    def _vorschlag_hilfen(self):
        vk = getattr(self, "hilfe_vk", {}) or {}
        return {t["_id"]: t.get("hilfe") or (vk.get(t["_id"]) or (None,))[0] for t in self.teile if t.get("drin")}

    def _vorschlag_eingaben(self, extra=(), nur=None):
        """{pid: (Eingaben, Länge)} der Rohre mit den Steckverbindungen des Editors (und extra)."""
        from .baugruppe_ansicht import eingaben_stecken
        drin = {t["_id"]: t["_q"] for t in self.teile if t.get("drin") and self._steck_profil(t["_id"])
                and (nur is None or t["_id"] in nur)}
        verb = [self._steck_daten(z) for z in self.bg["steckverbindungen"]] + list(extra)
        return eingaben_stecken(drin, verb, self._steck_profil)

    def _baugruppe_mitte(self):
        """Schwerpunkt der Körpermitten in Dateilage oder None."""
        from .baugruppe_ansicht import _spannen, in_lage
        punkte = []
        for t in self.teile:
            if not t.get("drin"):
                continue
            netz = self._netz(t["_id"])
            for lage in netz.get("lagen") or ([netz["lage"]] if netz.get("lage") else []):
                if netz.get("p") and lage and len(lage) == 9:
                    _, _, z0, z1 = _spannen(netz)
                    punkte.append(in_lage((0.0, 0.0, (z0 + z1) / 2), lage))
        return bv.mitte(punkte) if len(punkte) > 1 else None

    def _naht_vorschlaege(self, eingaben, ausser=()):
        mitte, out = self._baugruppe_mitte(), []
        for t in self.teile:
            pid, q = t["_id"], t["_q"]
            if not t.get("drin") or pid in ausser or pid not in eingaben or self.laengsnaht(pid) is not None \
                    or naht.vorgabe(q) != naht.KEINE:
                continue
            profil = self._steck_profil(pid) or {}
            netz = self._netz(pid)
            lage = (netz.get("lagen") or [netz.get("lage")])[0]
            innen = bv.winkel_innen(mitte, lage, netz, profil.get("form"))
            e, lg = eingaben[pid]
            v = bv.naht_vorschlag(pid, q, profil, e, lg, innen)
            if v:
                out.append(v)
        return out

    def vorschlaege_sammeln(self, laser=True):
        """Alle Vorschläge, größte Ersparnis zuerst. laser=False: ohne Laserzeit (schnell, für den Hinweis)."""
        preise, hilfen = self._vorschlag_preise(laser), self._vorschlag_hilfen()
        teile_q = {t["_id"]: t["_q"] for t in self.teile if t.get("drin")}
        regel = self._regel_faktor() if hasattr(self, "_regel_faktor") else None
        out = []
        mw, ketten = self.knick_kandidaten()
        for k in ketten:
            try:
                r = self.knick_bauen([dict(m) for m in mw], k, self.knick_vorgaben())
            except ValueError:
                continue
            out.append(bv.knick_bewerten(preise, r, teile_q, hilfen, self.bg.get("vorschlaege"), self.bg.get("naehte"),
                                         regel))
        im_knick = {pid for k in self.knicke for pid, _ in k["koerper"]}
        plan, _ = self.steck_plan()
        vorher = self._vorschlag_eingaben()
        for e in plan or ():
            if {e["auf"], e["st"]} & im_knick:
                continue
            z = self.steck_zeile(e)
            v = self._steck_daten(z)
            nachher = self._vorschlag_eingaben([v], {e["auf"], e["st"]})
            m = steckverbindung.masse(v, self._steck_profil(e["auf"]), self._steck_profil(e["st"])) \
                if (self._steck_profil(e["st"]) or {}).get("form") in steckverbindung.FORMEN else None
            out.append(bv.steck_bewerten(preise, e, teile_q, hilfen, vorher, nachher, steckverbindung.text(v, m)))
        out += self._naht_vorschlaege(vorher, im_knick)
        return bv.sortieren(out)

    def vorschlaege_info_neu(self):
        """Hinweis neben dem Knopf: wie viele Vorschläge es gibt (ohne Laserzeit gezählt)."""
        lab = getattr(self, "vorschlag_info", None)
        if lab is None or self.nur_lesen:
            return None
        try:
            liste = self.vorschlaege_sammeln(laser=False)
        except (ValueError, TypeError, KeyError, ZeroDivisionError):
            liste = []
        je = {a: sum(1 for v in liste if v["art"] == a) for a in bv.ARTEN}
        mehr = {bv.KNICK: "Knickrahmen", bv.STECK: "Steckverbindungen", bv.NAHT: "Längsnähte"}
        teile = [f"{n} {a if n == 1 else mehr[a]}" for a, n in je.items() if n]
        lab.setText(("Vorschläge: " + ", ".join(teile) + " – „Vorschläge …“ zeigt sie mit Ersparnis") if teile else "")
        return liste

    def vorschlag_zeigen(self, v):
        """Teile eines Vorschlags markieren und im 3D zeigen."""
        ids = set(v["teile"])
        tab = self.teile_tab
        tab.blockSignals(True)
        tab.clearSelection()
        for r, t in enumerate(self.teile):
            if t["_id"] in ids:
                tab.selectionModel().select(tab.model().index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
        tab.blockSignals(False)
        if hasattr(self, "zeige_3d"):
            if self.ansicht3d is not None:
                self.zeige_3d(hervor=ids, text=v["titel"])
        else:
            self.zeigen()

    def vorschlaege_zeigen(self, dialog=None):
        """Fenster Vorschläge; dialog(d) bedient es statt exec (Tests). Ergebnis: (übernommen, nicht übernommen)."""
        liste = self.vorschlaege_sammeln()
        if not liste:
            QMessageBox.information(self, "Vorschläge", "Keine Vorschläge: kein Knickrahmen, keine Steckverbindung aus "
                                    "den Stößen der STEP-Datei und keine Längsnaht, die sich günstiger legen lässt.")
            return 0, []
        d = VorschlaegeDialog(self, liste)
        if (dialog(d) if dialog else d.exec()) != QDialog.Accepted:
            return 0, []
        n, nicht = self.vorschlaege_anwenden(liste)
        if nicht:
            QMessageBox.information(self, "Vorschläge", f"{n} übernommen. Nicht übernommen:\n" + "\n".join(nicht))
        return n, nicht

    def vorschlaege_anwenden(self, liste):
        """Angehakte Vorschläge umsetzen: erst Knickrahmen, dann Steckverbindungen, dann Längsnähte (neu gerechnet mit
        den neuen Schlitzen und Nasen). Ergebnis: (Anzahl, [Text, warum nicht])."""
        n, nicht = 0, []
        an = [v for v in liste if v["an"]]
        knick = [v for v in an if v["art"] == bv.KNICK]
        for v in knick:
            mw, ketten = self.knick_kandidaten()
            ziel = {tuple(x) for x in v["daten"]["koerper"]}
            k = next((k for k in ketten if {(mw[t["i"]]["pid"], mw[t["i"]]["lage_nr"]) for t in k["teile"]} == ziel),
                     None)
            try:
                if k is None:
                    raise ValueError("geht nicht mehr (Teile geändert)")
                self.knicke.append(self.knick_bauen(mw, k, self.knick_vorgaben()))
                n += 1
            except ValueError as f:
                nicht.append(f"{v['titel']}: {f}")
        if knick:
            self._knick_vorschlaege()
        im_knick = {pid for k in self.knicke for pid, _ in k["koerper"]}
        steck = [v for v in an if v["art"] == bv.STECK]
        for v in steck:
            if {v["daten"]["auf"], v["daten"]["st"]} & im_knick:
                nicht.append(f"{v['titel']}: Teil ist jetzt in einem Knickrahmen")
                continue
            e = self.steck_schnitte(v["daten"])
            if e is None:
                nicht.append(f"{v['titel']}: Schlitze und Nasen gibt es schon")
                continue
            self.bg["steckverbindungen"].append(self.steck_zeile(e))
            n += 1
        if steck:
            self.steck_tab.aufbauen()
        naehte = {v["daten"]["pid"]: v for v in an if v["art"] == bv.NAHT}
        if naehte:
            neu = {x["daten"]["pid"]: x for x in self._naht_vorschlaege(self._vorschlag_eingaben(), im_knick)}
            for pid, v in naehte.items():
                if pid not in neu:
                    nicht.append(f"{v['titel']}: keine freie Stelle mehr (neue Schlitze oder Nasen)")
                    continue
                self.__dict__.setdefault("laengsnaehte", {})[pid] = neu[pid]["daten"]["winkel"]
                n += 1
        self.aktualisieren()
        self.vorschlaege_info_neu()
        return n, nicht


class LaengsnahtEditor:
    """Längsnaht per Klick im 3D (Patrick 24.10.2026): „Längsnaht wählen“ an, dann die Fläche eines Rohrs anklicken;
    Quadrat-/Rechteckrohr: Mitte der Wand, Rundrohr: genau dort. Ergebnis je Teil: feste Position, Quelle manuell
    (wie der Dialog Schweißnaht). Gemeinsam für den Editor der Schweißbaugruppe und das Fenster „Satz in 3D“;
    erwartet self.teile, self.ansicht3d (BaugruppenAnsicht), self._steck_profil, self._netz und self.aktualisieren()."""

    def laengsnaht_knopf_anlegen(self, nur_lesen=False):
        self.__dict__.setdefault("laengsnaehte", {})
        self.laengsnaht_knopf = self.ansicht3d.knopf(
            "Längsnaht wählen", "Fläche eines Rohrs anklicken: die Längsnaht liegt dort (Quadrat-/Rechteckrohr in der "
            "Mitte der Wand, Rundrohr genau dort); feste Position, Quelle manuell", True, self._laengsnaht_modus)
        self.laengsnaht_knopf.setEnabled(not nur_lesen)
        return self.laengsnaht_knopf

    def _laengsnaht_modus(self, an):
        if an:
            self.ansicht3d.messen_aus()
            self.ansicht3d.ansicht.messen_setzen(False)
            if hasattr(self, "zeichnen_knopf") and self.zeichnen_knopf.isChecked():
                self.naht_zeichnen(False)
        self.ansicht3d.mass.setText("Fläche eines Rohrs anklicken" if an else "")

    def laengsnaht_aus(self):
        k = getattr(self, "laengsnaht_knopf", None)
        if k is not None and k.isChecked():
            k.setChecked(False)

    def laengsnaht(self, pid):
        """Nahtwinkel des Teils (per Klick gewählt oder feste Position aus der Position), sonst None."""
        neu = self.__dict__.get("laengsnaehte") or {}
        if pid in neu:
            return neu[pid]
        q = next((t["_q"] for t in self.teile if t["_id"] == pid), {})
        w = q.get("naht_winkel")
        return float(w) if q.get("naht_vorgabe") == naht.FEST and isinstance(w, (int, float)) else None

    def laengsnaht_linien(self, koerper):
        """Rote Linien der Längsnähte für die Körper [(Positions-ID, Lage, Netz)] in Dateilage."""
        from .baugruppe_ansicht import laengsnaht_linie
        out = []
        for pid, lage, modell in koerper:
            w = self.laengsnaht(pid)
            linie = laengsnaht_linie(lage, self._netz(pid) or modell, w,
                                     (self._steck_profil(pid) or {}).get("form")) if w is not None else None
            if linie:
                out.append(linie)
        return out

    def laengsnaht_setzen(self, pid, punkt, lage, modell=None):
        """Längsnaht des Teils pid an die angeklickte Stelle (Punkt in der Dateilage). Ergebnis: Winkel oder None."""
        from .baugruppe_ansicht import laengsnaht_winkel
        form = (self._steck_profil(pid) or {}).get("form")
        if form not in steckverbindung.FORMEN:
            self.ansicht3d.mass.setText("Längsnaht nur für Quadrat-, Rechteck- und Rundrohre")
            return None
        w = laengsnaht_winkel(punkt, lage, self._netz(pid) or modell or {}, form)
        if w is None:
            return None
        self.__dict__.setdefault("laengsnaehte", {})[pid] = w
        q = next(t["_q"] for t in self.teile if t["_id"] == pid)
        self.ansicht3d.mass.setText(f"Pos. {_text(q.get('pos'))}: Längsnaht {_text(w, 0)}° (von Ende A gesehen, "
                                    "0° oben, 90° rechts)")
        self.aktualisieren()
        if hasattr(self, "baum_gewaehlt"):          # Editor der Baugruppe: 3D mit der neuen Linie
            self.baum_gewaehlt()
        return w

    def laengsnaht_werte(self):
        """{Positions-ID: Nahtfelder} der per Klick geänderten Längsnähte."""
        out = {}
        for pid, w in (self.__dict__.get("laengsnaehte") or {}).items():
            q = next((t["_q"] for t in self.teile if t["_id"] == pid), None)
            neu = dict(naht_vorgabe=naht.FEST, naht_winkel=w, naht_quelle="manuell")
            if q is not None and any(q.get(k) != v for k, v in neu.items()):
                out[pid] = neu
        return out


class BaugruppeDialog(SteckEditor, LaengsnahtEditor, KnickEditor, VorschlagEditor, StepBaugruppe, QDialog):
    """p: Position der Art Schweißbaugruppe (neu: leeres dict mit pos); positionen: alle Positionen des Angebots;
    tabellen: Stammdaten (Schweißverfahren, -kennwerte, -faktoren); saetze: Stundensätze des Angebots {ID: €/h}.
    vorwahl: IDs von Positionen, die neu in die Baugruppe kommen (markierte Zeilen beim Anlegen)."""

    def __init__(self, parent, p, positionen, tabellen, saetze, vorwahl=(), db=None, nur_lesen=False,
                 einstellungen=None, netze=None, profile=None):
        super().__init__(parent)
        # Profile der Stammdaten {profil_id: Zeile} für die Steckverbindungen (ohne: die der Angebotsseite)
        self.profile = profile or getattr(getattr(parent, "k", None), "profile", None) or {}
        self.p, self.positionen, self.tabellen, self.saetze = p, positionen, tabellen, saetze
        self.einstellungen = einstellungen or {}     # Stundensätze der Vorkalkulation (schweiss_vk_satz …)
        self.hilfe_vk, self.vk_ergebnis = {}, None
        self.netze = netze or {}    # {Positions-ID: Netz-Bytes} aus dem STEP-Import (3D im Strukturbaum, D1)
        self._netz_cache, self.ansicht3d = {}, None
        self.db = db                # Datenbank für Vorlagen (P1); ohne db keine Vorlagen-Knöpfe
        self.bg = baugruppe.lesen(p.get("baugruppe")) or baugruppe.leer()
        self.bg = copy.deepcopy(self.bg)
        self.bg["steckverbindungen"] = [self._steck_flach(v) for v in steckverbindung.liste(self.bg)]
        self.knicke = []            # neue Knickrahmen (mit OK zu Positionen, angebot_fenster.knicke_anwenden)
        self.steck_alt = copy.deepcopy(steckverbindung.liste(baugruppe.lesen(p.get("baugruppe")) or {}))
        self.stand_alt = {n.get("id"): {k: n.get(k) for k in NAHT_SCHLUESSEL} for n in self.bg["naehte"]}
        self.stand_verwerfen = False
        self.ergebnis, self.erg, self.status = None, None, None
        self._teile_aufbauen(vorwahl)
        self.nur_lesen = nur_lesen  # T6: Angebot eines Kollegen bzw. Lesemodus – ansehen, nicht speichern
        self.setWindowTitle(f"Schweißbaugruppe Pos. {p.get('pos') or ''} {baugruppe.name(p, self.bg)}".strip()
                            + (" (nur ansehen)" if nur_lesen else ""))
        self.resize(1400, 720)
        lay = QVBoxLayout(self)
        kopf = QHBoxLayout()
        self.bezeichnung = QLineEdit(p.get("bezeichnung") or "")
        self.bezeichnung.setPlaceholderText("z. B. Rahmen Förderband")
        self.artikel = QLineEdit(p.get("artikel") or "")
        self.anzahl = QSpinBox()
        self.anzahl.setRange(1, 100000)
        self.anzahl.setValue(int(p.get("stueck") or 1))
        self.anzahl.setSuffix(" Stk.")
        for titel, w, streck in (("Bezeichnung", self.bezeichnung, 3), ("Artikelnummer", self.artikel, 2),
                                 ("Anzahl Baugruppen", self.anzahl, 0)):
            kopf.addWidget(QLabel(titel))
            kopf.addWidget(w, streck)
        self.bezeichnung.textChanged.connect(self.aktualisieren)
        self.anzahl.valueChanged.connect(self.aktualisieren)
        lay.addLayout(kopf)
        self.reiter = QTabWidget()
        self.reiter.addTab(self._seite_struktur(), "Struktur und Teile")
        self.reiter.addTab(self._seite_naehte(), "Nahtgruppen")
        self.reiter.addTab(self._seite_arbeitsgaenge(), "Arbeitsgänge und Vorrichtungen")
        self.reiter.addTab(self._seite_stecken(), "Steckverbindungen")
        self.reiter.addTab(self._seite_stamm(), "Stammdaten")
        self.reiter.addTab(self._seite_uebersicht(), "Übersicht")
        self.reiter.addTab(self._seite_baum(), "Strukturbaum und 3D")
        self.reiter.currentChanged.connect(self._reiter_gewechselt)
        lay.addWidget(self.reiter, 1)
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        lay.addWidget(self.summe)
        self.vk_info = QLabel()
        self.vk_info.setWordWrap(True)
        self.vk_info.setStyleSheet(f"color: {GRAU};")
        lay.addWidget(self.vk_info)
        self.fehler = QLabel()
        self.fehler.setWordWrap(True)
        self.fehler.setStyleSheet(f"color: {FEHLER_FARBE};")
        lay.addWidget(self.fehler)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        knoepfe.button(QDialogButtonBox.Ok).setEnabled(not nur_lesen)
        unten = QHBoxLayout()
        rechnen_k = QPushButton("Vorkalkulation rechnen")
        rechnen_k.setToolTip("Rüsten, Positionieren, Wenden, Heftpunkte und Verputzen aus Struktur, Teilen und den Regeln "
                             "(Einstellungen → Schweiß-Vorkalkulation) vorschlagen; Werte von Hand bleiben")
        rechnen_k.clicked.connect(lambda: self.vorkalkulation())
        bestaetigen = QPushButton("Vorschläge bestätigen")
        bestaetigen.setToolTip("Alle gelben Vorschläge als geprüft übernehmen (eine neue Vorkalkulation lässt sie stehen)")
        bestaetigen.clicked.connect(lambda: self.vorschlaege_bestaetigen())
        self.vk_auto = QCheckBox("Vorkalkulation automatisch")
        self.vk_auto.setToolTip("Nahtvorschläge aus dem STEP übernehmen (a-Maß nach Regel), Schweißen, Heften, Verputzen, "
                                "Rüsten, Positionieren und Wenden bei jeder Änderung neu vorschlagen; Werte von Hand und "
                                "bestätigte bleiben. Vorgabe: Einstellung Vorkalkulation automatisch")
        self.vk_auto.setChecked(baugruppe.vk_auto(self.bg, self.einstellungen.get("schweiss_vk_step") == "ja"))
        self.vk_auto.setEnabled(not nur_lesen)
        self._vk_laeuft = False
        self._vk_timer = QTimer(self)
        self._vk_timer.setSingleShot(True)
        self._vk_timer.setInterval(800)
        self._vk_timer.timeout.connect(self._vk_nach_eingabe)
        self.vk_auto.toggled.connect(lambda an: self.vorkalkulation() if an else self.aktualisieren())
        unten.addWidget(self.vk_auto)
        for b in (rechnen_k, bestaetigen):
            b.setEnabled(not nur_lesen)
            unten.addWidget(b)
        if db is not None:
            einsetzen = QPushButton("Vorlage einsetzen …")
            einsetzen.setToolTip("Struktur, Nahtgruppen und Arbeitsgänge aus einer gespeicherten Vorlage übernehmen")
            einsetzen.clicked.connect(lambda: self.vorlage_waehlen())
            merken = QPushButton("Als Vorlage speichern …")
            merken.setToolTip("Struktur, Nahtgruppen und Arbeitsgänge (ohne Einzelteile) für spätere Baugruppen merken")
            merken.clicked.connect(lambda: self.vorlage_merken())
            unten.addWidget(einsetzen)
            unten.addWidget(merken)
        unten.addWidget(self.step_knopf())
        unten.addStretch(1)
        unten.addWidget(knoepfe)
        lay.addLayout(unten)
        self.aktualisieren()
        if self.vk_auto.isChecked() and not nur_lesen:
            self.vorkalkulation()
        self.vorschlaege_info_neu()

    # -------------------------------------------------------------- Struktur und Teile
    def _teile_aufbauen(self, vorwahl):
        """Zeilen der Teiletabelle: alle Positionen außer Baugruppen und Teilen anderer Baugruppen."""
        self.teile = []
        self.fremd = 0
        for q in self.positionen:
            if ist_baugruppe(q) or not q.get("id"):
                continue
            bg_id, kn = baugruppe.zuordnung(q)
            if bg_id and bg_id != self.bg["id"]:
                self.fremd += 1
                continue
            drin = bg_id == self.bg["id"] or q["id"] in vorwahl
            self.teile.append(dict(_id=q["id"], _q=q, drin=drin, knoten=kn or "",
                                   je=q.get("je_knoten") if drin and bg_id else
                                   (q.get("je_satz") or 1) if drin else 1,
                                   hilfe=q.get("bg_hilfe") if drin and bg_id else None, **self._gravur_vorgabe(q)))

    def _gravur_vorgabe(self, q):
        """Häkchen und Schrifthöhe der Artikelnummer-Gravur: gespeichert (Spalte bg_gravur), sonst nach den
        Einstellungen gravur_artikel und gravur_schrifthoehe."""
        h_einst = self.einstellungen.get("gravur_schrifthoehe") or 10
        h = q.get("bg_gravur")
        if h is None:
            return dict(gravur=bool(gravierbar(q) and self.einstellungen.get("gravur_artikel") == "ja"),
                        gravur_h=h_einst)
        return dict(gravur=h > 0, gravur_h=h if h > 0 else h_einst)

    def alle_gravieren(self, an=True):
        """Häkchen Artikelnr. gravieren für alle Teile der Baugruppe setzen bzw. entfernen."""
        for t in self.teile:
            if t.get("drin") and gravierbar(t["_q"]):
                t["gravur"] = an
        self.teile_tab.aufbauen()
        self.aktualisieren()

    def _knoten_optionen(self, ohne=None):
        out = [(DIREKT, "")]
        for k in self.bg["knoten"]:
            if k.get("id") != ohne:
                out.append((k.get("name") or "Unterbaugruppe", k["id"]))
        return out

    def _seite_struktur(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        links = QVBoxLayout()
        links.addWidget(QLabel("<b>Unterbaugruppen</b>"))
        self.knoten_tab = ZeilenTabelle([
            Spalte("name", "Name", breite=150),
            Spalte("menge", "Menge", "ganz", 60, tipp="Stück dieser Unterbaugruppe je übergeordneter Baugruppe"),
            Spalte("parent", "gehört zu", "auswahl", 140, optionen=lambda: self._knoten_optionen()),
            Spalte("_je", "Stück je\nBaugruppe", "anzeige", 110, anzeige=self._knoten_je)],
            self.bg["knoten"], self._struktur_geaendert)
        links.addWidget(self.knoten_tab, 1)
        leiste = QHBoxLayout()
        neu = QPushButton("Unterbaugruppe hinzufügen")
        neu.clicked.connect(lambda: self.knoten_neu())
        weg = QPushButton("Unterbaugruppe entfernen")
        weg.setToolTip("Teile, Nahtgruppen und Arbeitsgänge der Unterbaugruppe wandern eine Ebene höher")
        weg.clicked.connect(lambda: self.knoten_entfernen(self.knoten_tab.markierte()))
        leiste.addWidget(neu)
        leiste.addWidget(weg)
        leiste.addStretch(1)
        links.addLayout(leiste)
        lay.addLayout(links, 2)
        rechts = QVBoxLayout()
        rechts.addWidget(QLabel("<b>Einzelteile</b> (Positionen des Angebots)"))
        self.teile_tab = ZeilenTabelle([
            Spalte("drin", "in Bau-\ngruppe", "haken", 60),
            Spalte("_pos", "Pos.", "anzeige", 50, anzeige=lambda z, r: str(z["_q"].get("pos") or "")),
            Spalte("_teil", "Teil", "anzeige", 260, anzeige=self._teil_text),
            Spalte("knoten", "Unterbaugruppe", "auswahl", 150, optionen=lambda: self._knoten_optionen()),
            Spalte("je", "Stück je Unter-\nbaugruppe", "ganz", 90),
            Spalte("_je", "Stück je\nBaugruppe", "anzeige", 110, anzeige=self._teil_je),
            Spalte("hilfe", "Positionier-\nhilfe", "auswahl", 125, vk=True,
                   optionen=[("(Vorschlag)", None)] + [(h, h) for h in POSITIONIERHILFEN],
                   tipp="Wie das Teil beim Schweißen seine Lage findet; leer = Vorschlag der Vorkalkulation"),
            Spalte("gravur", "Artikelnr.\ngravieren", "haken", 75,
                   tipp="Artikelnummer auf das Rohr bzw. Blech gravieren (Positionierhilfe beim Schweißen); Lage "
                        "automatisch, beim Blech im Blech-Editor verschiebbar"),
            Spalte("gravur_h", "Schrift-\nhöhe [mm]", "zahl", 70, tipp="Schrifthöhe der Gravur (Vorgabe in den "
                                                                       "Einstellungen)"),
            Spalte("_gravur_info", "Gravur", "anzeige", 140, anzeige=self._gravur_text),
            Spalte("_hilfe_vk", "Vorschlag", "anzeige", 200, anzeige=self._hilfe_text)],
            self.teile, self.aktualisieren, self._teil_herkunft)
        rechts.addWidget(self.teile_tab, 1)
        leiste = QHBoxLayout()
        for text, an in (("Alle gravieren", True), ("Keine gravieren", False)):
            b = QPushButton(text)
            b.setToolTip("Häkchen Artikelnr. gravieren für alle Bleche und Rohre der Baugruppe")
            b.clicked.connect(lambda _=False, an=an: self.alle_gravieren(an))
            leiste.addWidget(b)
        leiste.addStretch(1)
        rechts.addLayout(leiste)
        # Knickrahmen aus markierten Rohren mit Gehrung (wie im STEP-Prüfdialog und im Fenster Satz in 3D)
        rechts.addLayout(self.knick_knoepfe())
        self.knick_info = QLabel()
        self.knick_info.setWordWrap(True)
        self.knick_info.setStyleSheet("color: #595959;")
        rechts.addWidget(self.knick_info)
        if self.fremd:
            rechts.addWidget(QLabel(f"{self.fremd} weitere Position(en) gehören zu einer anderen Baugruppe."))
        lay.addLayout(rechts, 3)
        return w

    def _knoten_je(self, z, _r):
        f = baugruppe.faktor(self.bg, z.get("id"))
        return _text(f) if f is not None else ("?", True)

    def _teil_text(self, z, _r):
        q = z["_q"]
        teile = [q.get("artikel"), q.get("bezeichnung"), q.get("profil_id"),
                 _text(q.get("laenge")) + " mm" if q.get("laenge") else None]
        return " · ".join(str(t) for t in teile if t) or q.get("art") or ""

    def _teil_je(self, z, _r):
        if not z.get("drin"):
            return ""
        f = baugruppe.faktor(self.bg, z.get("knoten") or "")
        if f is None:
            return ("?", True)
        return _text((z.get("je") or 1) * f)

    def _gravur_text(self, z, _r):
        if not z.get("drin") or not z.get("gravur"):
            return ""
        q = z["_q"]
        if not gravierbar(q):
            return ("nur Rohrlaser- und Blechteile", True)
        if not str(q.get("artikel") or "").strip():
            return ("Artikelnummer fehlt", WARNUNG)
        from . import gravur_text
        b, h = gravur_text.masse(q["artikel"], z.get("gravur_h") or 0)
        if not kein_laserteil(q) and q.get("laenge") and not gravur_text.lage_laengs(q["laenge"], (), b):
            return (f"{_text(b, 0)} mm lang: Rohr zu kurz", WARNUNG)
        return f"{_text(b, 0)} × {_text(h, 0)} mm"

    def _hilfe_text(self, z, _r):
        v = self.hilfe_vk.get(z["_id"]) if z.get("drin") else None
        return f"{v[0]}: {v[1]}" if v else ""

    def _teil_herkunft(self, z, feld):
        if feld != "hilfe" or not z.get("drin"):
            return None
        v = self.hilfe_vk.get(z["_id"])
        if z.get("hilfe"):
            return (vorkalk.HAND, f"Vorschlag wäre {v[0]}" if v else None)
        return (vorkalk.VORSCHLAG, f"{v[0]}, {v[1]}") if v else None

    def knoten_neu(self, name=None, menge=1, parent=""):
        k = dict(id=baugruppe.neue_id(), name=name or f"Unterbaugruppe {len(self.bg['knoten']) + 1}", menge=menge,
                 parent=parent or None)
        self.bg["knoten"].append(k)
        self.knoten_tab.aufbauen()
        self._auswahl_neu()
        self.aktualisieren()
        return k["id"]

    def knoten_entfernen(self, zeilen):
        for r in sorted(zeilen, reverse=True):
            k = self.bg["knoten"][r]
            oben = k.get("parent") or ""
            for x in self.bg["knoten"]:
                if x.get("parent") == k["id"]:
                    x["parent"] = oben or None
            for x in self.bg["naehte"] + self.bg["arbeitsgaenge"]:
                if x.get("knoten") == k["id"]:
                    x["knoten"] = oben or None
            for t in self.teile:
                if t.get("knoten") == k["id"]:
                    t["knoten"] = oben
            del self.bg["knoten"][r]
        self.knoten_tab.aufbauen()
        self._auswahl_neu()
        self.aktualisieren()

    def _struktur_geaendert(self):
        """Zyklus sofort abweisen: 'gehört zu' zurück auf die Baugruppe selbst."""
        for k in self.bg["knoten"]:
            if k.get("parent") and (k["parent"] == k["id"] or not baugruppe.darf_unter(self.bg, k["id"], k["parent"])):
                self.fehler.setText(f"'{k.get('name')}' kann nicht unter sich selbst hängen.")
                k["parent"] = None
                self.knoten_tab.optionen_neu()
        self._auswahl_neu()
        self.aktualisieren()

    def _auswahl_neu(self):
        for tab in (self.knoten_tab, getattr(self, "teile_tab", None), getattr(self, "naht_tab", None),
                    getattr(self, "ag_tab", None)):
            if tab is not None:
                tab.optionen_neu()

    def teil_setzen(self, position_id, drin=True, knoten="", je=1):
        """Einzelteil zuordnen (Tests): knoten = Knoten-ID ('' = Baugruppe selbst)."""
        z = next(t for t in self.teile if t["_id"] == position_id)
        z.update(drin=drin, knoten=knoten, je=je)
        self.teile_tab.aufbauen()
        self.aktualisieren()

    # -------------------------------------------------------------- Nahtgruppen
    def _verfahren_optionen(self):
        return [("", None)] + [(z["verfahren"], z["verfahren"]) for z in self.tabellen.get("schweissverfahren") or ()
                               if z.get("verfahren") and z.get("aktiv", True) is not False]

    def _faktor_optionen(self, art, vorgabe=()):
        werte = [str(z["wert"]) for z in self.tabellen.get("schweiss_faktoren") or ()
                 if z.get("art") == art and z.get("wert")]
        return [("", None)] + [(w, w) for w in (werte or list(vorgabe))]

    def _seite_naehte(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.naht_tab = ZeilenTabelle([
            Spalte("nr", "Nr.", breite=45),
            Spalte("knoten", "Unterbaugruppe", "auswahl", 130, optionen=lambda: self._knoten_optionen()),
            Spalte("verfahren", "Verfahren", "auswahl", 90, optionen=self._verfahren_optionen),
            Spalte("nahtart", "Nahtart", "auswahl", 95, optionen=[(n, n) for n in NAHTARTEN]),
            Spalte("mass", "a-Maß /\nDicke [mm]", "zahl", 80, tipp="Kehlnaht: a-Maß; Stumpf- und Ecknaht: Blechdicke"),
            Spalte("dicke", "Wand-\ndicke [mm]", "zahl", 70,
                   tipp="Kleinere Wanddicke der verbundenen Teile (Heftabstand der Vorkalkulation); leer bei Stumpf- "
                        "und Ecknaht = Dicke"),
            Spalte("laenge", "Länge je\nNaht [mm]", "zahl", 85),
            Spalte("anzahl", "Anzahl", "ganz", 55, tipp="Gleiche Nähte je Stück der Unterbaugruppe"),
            Spalte("beidseitig", "beidseitig", "haken", 65),
            Spalte("heftpunkte", "Heftpunkte\nje Naht", "ganz", 75, vk=True),
            Spalte("gesteckt", "gesteckt", "haken", 60, tipp="Teile gesteckt (Stecknase): weniger Heftpunkte"),
            Spalte("rundum", "rundum", "haken", 55, tipp="Umfangsnaht um ein Rohr (Mindestzahl Heftpunkte rundum)"),
            Spalte("lage", "Lage", "auswahl", 60, optionen=lambda: self._faktor_optionen("Schweißlage", baugruppe.LAGEN),
                   tipp=", ".join(f"{k} {v}" for k, v in baugruppe.LAGEN.items())),
            Spalte("zugang", "Zugänglichkeit", "auswahl", 95, optionen=lambda: self._faktor_optionen("Zugänglichkeit")),
            Spalte("qualitaet", "Qualität", "auswahl", 85, optionen=lambda: self._faktor_optionen("Qualität")),
            Spalte("nacharbeit", "Nacharbeit", "auswahl", 120, vk=True,
                   optionen=[("", None)] + [(n, n) for n in NACHARBEIT_STUFEN],
                   tipp="Verputzen bzw. Schleifen der Naht (Arbeitsgang Verputzen der Vorkalkulation)"),
            Spalte("zeit_hand", "Zeit von\nHand [min]", "zahl", 80, tipp="Zeit je Stück der Unterbaugruppe; geht vor"),
            Spalte("_zeit", "Zeit je\nBaugruppe", "anzeige", 95, anzeige=lambda z, r: self._zeile_wert("Naht", z, "zeit")),
            Spalte("_kosten", "Kosten je\nBaugruppe", "anzeige", 95,
                   anzeige=lambda z, r: self._zeile_wert("Naht", z, "kosten")),
            Spalte("_hinweis", "Hinweis", "anzeige", 200, anzeige=lambda z, r: self._zeile_wert("Naht", z, "hinweis"))],
            self.bg["naehte"], self.aktualisieren, self._naht_herkunft)
        lay.addWidget(self.naht_tab, 1)
        leiste = QHBoxLayout()
        neu = QPushButton("Nahtgruppe hinzufügen")
        neu.clicked.connect(lambda: self.naht_neu())
        kopie = QPushButton("Markierte kopieren")
        kopie.clicked.connect(lambda: self._kopieren(self.bg["naehte"], self.naht_tab))
        weg = QPushButton("Markierte entfernen")
        weg.clicked.connect(lambda: self._entfernen(self.bg["naehte"], self.naht_tab))
        stamm = QPushButton("Kennwerte neu aus Stammdaten")
        stamm.setToolTip("Gemerkte Kennwerte aller Nahtgruppen verwerfen und mit den aktuellen Stammdaten rechnen")
        stamm.clicked.connect(self.kennwerte_neu)
        regel = QPushButton("a-Maß bestätigen")
        regel.setToolTip("a-Maß nach Regel der markierten Nahtgruppen als geprüft übernehmen")
        regel.clicked.connect(lambda: self.regel_bestaetigen(self.naht_tab.markierte()))
        for b in (neu, kopie, weg, stamm, regel):
            leiste.addWidget(b)
        leiste.addStretch(1)
        lay.addLayout(leiste)
        lay.addWidget(self._vorschlaege_box())
        lay.addWidget(hilfe.Hinweis(
            "Je Zeile eine Gruppe gleicher Nähte. Schweißzeit = Naht [m] × Kennwert [min/m] × Faktoren (Lage, "
            "Zugänglichkeit, Qualität) ÷ Lichtbogenzeitfaktor + Heftpunkte × Zeit je Heftpunkt; Kennwerte und "
            "Faktoren stehen unter Einstellungen (Schweißverfahren, Schweiß-Kennwerte, Schweiß-Faktoren). Fehlt ein "
            "Kennwert, rechnet die Zeile keine Zeit und zeigt den Grund. Eine Zeit von Hand geht immer vor.",
            schluessel="baugruppe_naehte"))
        return w

    def _vorschlaege_box(self):
        """Nahtkandidaten aus der STEP-Messung: nur Vorschläge, erst 'Markierte übernehmen' macht Nahtgruppen."""
        self.vorschlag_rahmen = QGroupBox("Nahtkandidaten aus STEP (prüfen, dann übernehmen)")
        vl = QVBoxLayout(self.vorschlag_rahmen)
        self.vorschlag_tab = QTableWidget(0, 6)
        self.vorschlag_tab.setHorizontalHeaderLabels(["Unterbaugruppe", "Stoßart", "Länge je Naht [mm]", "Anzahl",
                                                      "Dicke [mm]", "Körper"])
        self.vorschlag_tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.vorschlag_tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.vorschlag_tab.verticalHeader().setDefaultSectionSize(22)
        self.vorschlag_tab.setMaximumHeight(150)
        vl.addWidget(self.vorschlag_tab)
        leiste = QHBoxLayout()
        uebernehmen = QPushButton("Markierte übernehmen")
        uebernehmen.setToolTip("Markierte Vorschläge als Nahtgruppen anlegen; Verfahren und a-Maß danach eintragen")
        uebernehmen.clicked.connect(lambda: self.vorschlaege_uebernehmen())
        verwerfen = QPushButton("Markierte verwerfen")
        verwerfen.clicked.connect(lambda: self.vorschlaege_verwerfen())
        self.regel_haken = QCheckBox("a-Maß nach Regel vorschlagen")
        self.regel_haken.setToolTip(f"Kehlnaht: a = {_text(self._regel_faktor())} × kleinere Wanddicke, abgerundet auf "
                                    "0,5 mm (Faktor unter Einstellungen); bis zur Bestätigung als Hinweis markiert")
        leiste.addWidget(uebernehmen)
        leiste.addWidget(verwerfen)
        leiste.addWidget(self.regel_haken)
        leiste.addStretch(1)
        vl.addLayout(leiste)
        self._vorschlaege_zeigen()
        return self.vorschlag_rahmen

    def _vorschlaege_zeigen(self):
        vs = self.bg.setdefault("vorschlaege", [])
        namen = {k["id"]: k.get("name") or "Unterbaugruppe" for k in self.bg["knoten"]}
        self.vorschlag_tab.setRowCount(len(vs))
        for r, v in enumerate(vs):
            texte = [namen.get(v.get("knoten"), DIREKT), v.get("nahtart") or "", _text(v.get("laenge")),
                     _text(v.get("anzahl")), _text(v.get("dicke")),
                     ", ".join(f"{a}+{b}" for a, b in (x for x in v.get("teile") or () if x and len(x) == 2))]
            for c, s in enumerate(texte):
                self.vorschlag_tab.setItem(r, c, QTableWidgetItem(s))
        self.vorschlag_rahmen.setVisible(bool(vs))

    def _vorschlag_zeilen(self, zeilen=None):
        if zeilen is None:
            zeilen = {i.row() for i in self.vorschlag_tab.selectionModel().selectedIndexes()}
        return sorted(z for z in zeilen if 0 <= z < len(self.bg["vorschlaege"]))

    def vorschlaege_uebernehmen(self, zeilen=None):
        """Markierte Vorschläge (zeilen: Indizes, sonst die Auswahl) als Nahtgruppen anlegen und aus der Liste nehmen.
        Ergebnis: IDs der neuen Nahtgruppen."""
        zeilen = self._vorschlag_zeilen(zeilen)
        regel = self._regel_faktor() if self.regel_haken.isChecked() else None
        neu = [self.naht_neu(baugruppe.vorschlag_naht(self.bg["vorschlaege"][r], regel)) for r in zeilen]
        self.vorschlaege_verwerfen(zeilen)
        return neu

    def _regel_faktor(self):
        w = self.db.einstellung("schweiss_a_regel") if self.db is not None else None
        return w if isinstance(w, (int, float)) and w > 0 else baugruppe.A_REGEL_VORGABE

    def regel_bestaetigen(self, zeilen=None):
        """a-Maß nach Regel der markierten Nahtgruppen (zeilen: Indizes, sonst alle) als geprüft übernehmen."""
        zeilen = range(len(self.bg["naehte"])) if zeilen is None else zeilen
        for r in zeilen:
            self.bg["naehte"][r].pop("mass_regel", None)
        self.aktualisieren()

    def vorschlaege_verwerfen(self, zeilen=None):
        weg = set(self._vorschlag_zeilen(zeilen))
        self.bg["vorschlaege"] = [v for i, v in enumerate(self.bg["vorschlaege"]) if i not in weg]
        self._vorschlaege_zeigen()

    def naht_neu(self, werte=None):
        nr = max([int(n["nr"]) for n in self.bg["naehte"] if str(n.get("nr") or "").isdigit()], default=0) + 1
        vorlage = self.bg["naehte"][-1] if self.bg["naehte"] else {}
        n = dict(id=baugruppe.neue_id(), nr=str(nr), anzahl=1,
                 verfahren=vorlage.get("verfahren") or next((v for _, v in self._verfahren_optionen() if v), None),
                 nahtart=vorlage.get("nahtart") or NAHTARTEN[0])
        n.update(werte or {})
        self.bg["naehte"].append({k: v for k, v in n.items() if v is not None})
        self.naht_tab.aufbauen()
        self.aktualisieren()
        return n["id"]

    def kennwerte_neu(self):
        self.stand_verwerfen = True
        for n in self.bg["naehte"]:
            n.pop("stand", None)
        self.aktualisieren()

    def _naht_aktuell(self, n):
        """Nahtgruppe so, wie sie gerechnet wird: geänderte Schlüsselwerte = ohne gemerkten Stand."""
        alt = self.stand_alt.get(n.get("id"))
        if "stand" in n and (alt is None or any(alt.get(k) != n.get(k) for k in NAHT_SCHLUESSEL)):
            n = {k: v for k, v in n.items() if k != "stand"}
        return n

    # -------------------------------------------------------------- Arbeitsgänge
    def _satz_optionen(self):
        return [("", None)] + [(f"{s} ({_text(v)} €/h)" if isinstance(v, (int, float)) else s, s)
                               for s, v in sorted(self.saetze.items())]

    def _seite_arbeitsgaenge(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.ag_tab = ZeilenTabelle([
            Spalte("name", "Arbeitsgang", "auswahl", 150, optionen=[(a, a) for a in ARBEITSGAENGE], frei=True, vk=True),
            Spalte("knoten", "Unterbaugruppe", "auswahl", 130, optionen=lambda: self._knoten_optionen()),
            Spalte("satz_id", "Stundensatz", "auswahl", 150, optionen=self._satz_optionen),
            Spalte("menge", "Menge", "zahl", 55, tipp="Einheiten je Stück der Unterbaugruppe (leer = 1)", vk=True),
            Spalte("zeit_min", "Zeit je\nEinheit [min]", "zahl", 80, vk=True),
            Spalte("kosten_einheit", "Kosten je\nEinheit [€]", "zahl", 80, tipp="z. B. Fremdleistung, Material"),
            Spalte("ruest_min", "Rüstzeit\n[min]", "zahl", 70, tipp="einmal je Auftrag bzw. Staffelstufe", vk=True),
            Spalte("einmal_eur", "Einmal-\nbetrag [€]", "zahl", 80, tipp="Vorrichtung, Lehre, Prüfmittel, Programm …"),
            Spalte("umlage", "Umlage", "auswahl", 115, optionen=[(u, u) for u in baugruppe.UMLAGEN]),
            Spalte("anteil", "Anteil [%]", "zahl", 60, tipp="nur bei Umlage 'anteilig'"),
            Spalte("fremd", "Fremd", "haken", 50, tipp="Fremdleistung (Zuschlag Fremdleistung statt Fertigung)"),
            Spalte("_kosten", "je Baugruppe", "anzeige", 90,
                   anzeige=lambda z, r: self._zeile_wert("Arbeitsgang", z, "kosten")),
            Spalte("_einmal", "einmalig", "anzeige", 80,
                   anzeige=lambda z, r: self._zeile_wert("Arbeitsgang", z, "einmal")),
            Spalte("_hinweis", "Hinweis", "anzeige", 160,
                   anzeige=lambda z, r: self._zeile_wert("Arbeitsgang", z, "hinweis"))],
            self.bg["arbeitsgaenge"], self.aktualisieren, self._ag_herkunft)
        lay.addWidget(self.ag_tab, 1)
        leiste = QHBoxLayout()
        neu = QPushButton("Arbeitsgang hinzufügen")
        neu.clicked.connect(lambda: self.arbeitsgang_neu())
        vor = QPushButton("Vorrichtung hinzufügen")
        vor.setToolTip("Einmalkosten für eine Vorrichtung (Umlage je Auftrag)")
        vor.clicked.connect(lambda: self.arbeitsgang_neu(dict(name="Vorrichtung", umlage=baugruppe.UMLAGE_AUFTRAG)))
        katalog = QPushButton("Aus Zusatzarbeiten …")
        katalog.setToolTip("Arbeitsgang aus den Zusatzarbeiten der Stammdaten übernehmen (Stundensatz, Zeit, Preis)")
        katalog.setEnabled(bool(self._katalog()))
        katalog.clicked.connect(lambda: self.arbeitsgang_aus_katalog())
        kopie = QPushButton("Markierte kopieren")
        kopie.clicked.connect(lambda: self._kopieren(self.bg["arbeitsgaenge"], self.ag_tab))
        weg = QPushButton("Markierte entfernen")
        weg.clicked.connect(lambda: self._entfernen(self.bg["arbeitsgaenge"], self.ag_tab))
        for b in (neu, vor, katalog, kopie, weg):
            leiste.addWidget(b)
        leiste.addStretch(1)
        leiste.addWidget(QLabel("Wendevorgänge je Baugruppe"))
        self.wenden = QSpinBox()
        self.wenden.setRange(0, 99)
        self.wenden.setValue(int(self.bg.get("wenden") or 0))
        self.wenden.setToolTip("Wie oft die Baugruppe beim Schweißen gewendet oder umgespannt wird (Vorkalkulation: "
                               "Zeit je Wenden × Faktor nach Gewicht aus den Stammdaten der Baugruppe)")
        self.wenden.valueChanged.connect(self._wenden_geaendert)
        leiste.addWidget(self.wenden)
        lay.addLayout(leiste)
        lay.addWidget(hilfe.Hinweis(
            "Laufende Kosten je Stück: Zeit je Einheit × Menge × Stundensatz + Kosten je Einheit × Menge. Rüstzeit "
            "und Einmalbetrag fallen einmal je Auftrag bzw. Staffelstufe an und werden auf die Baugruppen verteilt: "
            "'je Auftrag' ganz, 'anteilig' mit dem Anteil in %, 'wiederverwendbar' gar nicht (Vorrichtung schon "
            "vorhanden). Fremd = Fremdleistung mit Zuschlag Fremdleistung.", schluessel="baugruppe_arbeitsgaenge"))
        return w

    def _wenden_geaendert(self, n):
        if n:
            self.bg["wenden"] = n
        else:
            self.bg.pop("wenden", None)
        self.aktualisieren()

    def arbeitsgang_neu(self, werte=None):
        a = dict(id=baugruppe.neue_id(), name="Vorrichten", umlage=baugruppe.UMLAGE_AUFTRAG,
                 satz_id="Schweißen" if "Schweißen" in self.saetze else None)
        if werte and ("satz" in werte or "satz_id" in werte):
            a.pop("satz_id")
        a.update(werte or {})
        self.bg["arbeitsgaenge"].append({k: v for k, v in a.items() if v is not None})
        self.ag_tab.aufbauen()
        self.aktualisieren()
        return a["id"]

    def _katalog(self):
        """Aktive Zusatzarbeiten der Stammdaten, die an einer Baugruppe Sinn ergeben (ohne s/Stück = Laserzeit)."""
        return {z["name"]: z for z in self.tabellen.get("zusatzarbeiten") or ()
                if z.get("name") and z.get("aktiv") != "nein" and z.get("art") != "s/Stück"}

    def arbeitsgang_aus_katalog(self, name=None):
        """Arbeitsgang aus einer Zusatzarbeit anlegen (name vorgegeben: ohne Auswahlfenster). Ergebnis: ID oder None."""
        katalog = self._katalog()
        if name is None:
            from PySide6.QtWidgets import QInputDialog
            name, ok = QInputDialog.getItem(self, "Arbeitsgang aus Zusatzarbeiten", "Zusatzarbeit:",
                                            sorted(katalog, key=str.lower), 0, False)
            if not ok:
                return None
        if name not in katalog:
            return None
        return self.arbeitsgang_neu(baugruppe.arbeitsgang_vorlage(katalog[name]))

    def _kopieren(self, liste, tab):
        for r in tab.markierte():
            neu = {k: v for k, v in copy.deepcopy(liste[r]).items() if k not in ("stand", "vk")}
            neu["id"] = baugruppe.neue_id()
            if "nr" in neu:
                neu["nr"] = str(max([int(n["nr"]) for n in liste if str(n.get("nr") or "").isdigit()], default=0) + 1)
            liste.append(neu)
        tab.aufbauen()
        self.aktualisieren()

    def _entfernen(self, liste, tab):
        for r in reversed(tab.markierte()):
            del liste[r]
        tab.aufbauen()
        self.aktualisieren()

    # -------------------------------------------------------------- Stammdaten und Übersicht
    def _seite_stamm(self):
        w = QWidget()
        form = QFormLayout(w)
        self.stamm_felder = {}
        for n, titel in baugruppe.STAMM_FELDER:
            if n in LANGTEXT:
                f = QPlainTextEdit(str(self.bg["stamm"].get(n) or ""))
                f.setFixedHeight(54)
            else:
                f = QLineEdit(str(self.bg["stamm"].get(n) or ""))
            self.stamm_felder[n] = f
            form.addRow(titel, f)
        self.stamm_wahl = {}
        for n, titel, tipp in baugruppe.STAMM_WAHL:
            f = QCheckBox(titel)
            f.setChecked(bool(self.bg["stamm"].get(n)))
            f.setToolTip(tipp)
            self.stamm_wahl[n] = f
            form.addRow("", f)
        return w

    def _seite_uebersicht(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.balken = Kostenbalken("Kosten je Baugruppe")
        lay.addWidget(self.balken)
        self.uebersicht = QLabel()
        self.uebersicht.setWordWrap(True)
        self.uebersicht.setTextFormat(Qt.RichText)
        self.uebersicht.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        lay.addWidget(self.uebersicht, 1)
        return w

    # -------------------------------------------------------------- Rechnen
    def daten(self):
        """Baugruppe mit den aktuellen Eingaben (Stand nur, wo er gilt)."""
        bg = copy.deepcopy(self.bg)
        bg["naehte"] = [self._naht_aktuell(n) for n in bg["naehte"]]
        bg["stamm"] = {}
        for n, f in getattr(self, "stamm_felder", {}).items():
            t = (f.toPlainText() if isinstance(f, QPlainTextEdit) else f.text()).strip()
            if t:
                bg["stamm"][n] = t
        for n, f in getattr(self, "stamm_wahl", {}).items():
            if f.isChecked():
                bg["stamm"][n] = True
        bg["steckverbindungen"] = [self._steck_daten(v) for v in self.bg["steckverbindungen"]]
        if not bg["steckverbindungen"]:
            bg.pop("steckverbindungen")
        if hasattr(self, "vk_auto"):
            bg["stamm"]["vk_auto"] = self.vk_auto.isChecked()
        return bg

    def _position(self, bg=None):
        return dict(self.p, art=BAUGRUPPE, stueck=self.anzahl.value(), baugruppe=baugruppe.speichern(bg or self.daten()),
                    bezeichnung=self.bezeichnung.text().strip() or None, artikel=self.artikel.text().strip() or None)

    def _positionen_neu(self, p):
        """Positionen des Angebots mit dieser Baugruppe und den Zuordnungen des Dialogs, abgeglichen (für den Status)."""
        teile = {t["_id"]: t for t in self.teile}
        out = []
        for q in self.positionen:
            if q is self.p or (self.p.get("id") and q.get("id") == self.p.get("id")):
                continue
            t = teile.get(q.get("id"))
            if t is not None:
                q = dict(q, **self._zuordnung(t))
            out.append(q)
        out.append(p)
        for i, feld, wert in baugruppe.abgleich(out):     # wie nach OK: Satz und Stückzahlen folgen der Struktur
            out[i] = dict(out[i], **{feld: wert})
        return out

    def _zuordnung(self, t):
        if not t.get("drin"):
            return dict(bg_knoten=None, je_knoten=None, bg_hilfe=None, bg_gravur=None)
        return dict(bg_knoten=baugruppe.zuordnung_text(self.bg["id"], t.get("knoten") or ""), je_knoten=t.get("je") or 1,
                    bg_hilfe=t.get("hilfe") or None,
                    bg_gravur=float(t.get("gravur_h") or 0) if t.get("gravur") and gravierbar(t["_q"]) else 0.0)

    def _zeile_wert(self, art, z, was):
        r = next((x for x in (self.erg or {}).get("zeilen", ()) if x["art"] == art and x["id"] == z.get("id")), None)
        if r is None:
            return ("Unterbaugruppe fehlt", WARNUNG) if was == "hinweis" else ""
        if was == "zeit":
            return _min(r["zeit_min"])
        if was == "kosten":
            return _euro(r["kosten"])
        if was == "einmal":
            return _euro(r["einmal"]) if r["einmal"] else ""
        w = r["werte"]
        if w.get("fehlt"):
            return (w["fehlt"], WARNUNG)
        if art == "Naht":
            teile = [f"{_text(round(w['naht_m'] * r['faktor'], 2))} m"]
            if w.get("hand"):
                teile.append("Zeit von Hand")
            elif w.get("richtwert"):
                teile.append(RICHTWERT)
            if w.get("material"):
                teile.append(f"Zusatz/Gas {_euro(w['material'] * r['faktor'])}")
            if w.get("verbrauch_hinweis"):
                teile.append(w["verbrauch_hinweis"])
            if baugruppe.regel_offen(z):
                return (", ".join(teile + ["a-Maß nach Regel, bitte bestätigen"]), WARNUNG)
            if self._naht_aktuell(z).get("stand"):
                teile.append(f"Kennwerte vom {z['stand'].get('datum') or '?'}")
            return ", ".join(teile)
        if w.get("umlage") == baugruppe.UMLAGE_WIEDER and w.get("einmal"):
            return "wiederverwendbar: einmalig nicht berechnet"
        return ""

    def aktualisieren(self, *_):
        if getattr(self, "vk_auto", None) is not None and self.vk_auto.isChecked() and not self._vk_laeuft \
                and not self.nur_lesen:
            self._vk_timer.start()      # Vorkalkulation automatisch: nach der Eingabe neu vorschlagen
        bg = self.daten()
        p = self._position(bg)
        self.erg = baugruppe.rechnen(p, self.tabellen, self.saetze)
        positionen = self._positionen_neu(p)
        self.hilfe_vk = {positionen[i]["id"]: v for i, v in vorkalk.hilfen_vorschlag(bg, positionen, bg["id"]).items()}
        for tab in (getattr(self, "knoten_tab", None), getattr(self, "teile_tab", None),
                    getattr(self, "naht_tab", None), getattr(self, "ag_tab", None)):
            if tab is not None:
                tab.auffrischen()
        if getattr(self, "knick_info", None) is not None:
            pos = {t_["_id"]: t_["_q"].get("pos") for t_ in self.teile}
            self.knick_info.setText("; ".join(
                f"Neuer Knickrahmen {n} aus Pos. " + ", ".join(sorted({_text(pos.get(pid)) for pid, _ in k["koerper"]}))
                + f": {k['text']} (mit OK eine Position)" for n, k in enumerate(self.knicke, 1)))
        if not hasattr(self, "summe"):
            return
        w = dict(bg_tabellen=self.tabellen, saetze=self.saetze)
        self.status = baugruppe.status(p, w, positionen)
        e = self.erg
        anzahl = self.anzahl.value()
        n_teile = sum(1 for t in self.teile if t.get("drin"))
        self.summe.setText(
            f"<b>Je Baugruppe:</b> Schweißen und Arbeitsgänge {_euro(e['eigen'])}, Fremdleistungen "
            f"{_euro(e['fremd'])}, davon Einmalkosten umgelegt {_euro(e['einmal'])} (gesamt "
            f"{_euro(e['einmal_gesamt'])} bei {anzahl} Stk.) · Zeit {_min(e['zeit_min'])}, davon Schweißen "
            f"{_min(e['schweiss_min'])} · {n_teile} Einzelteil(e). <b>Status:</b> {self.status}")
        self.summe.setTextFormat(Qt.RichText)
        self.balken.setzen(baugruppe.kostenaufteilung(e))
        naht = ", ".join(f"{v} {_text(round(m, 2))} m" for v, m in sorted(e["naht_m"].items())) or "keine"
        zeilen = "".join(
            f"<tr><td>{x['art']}</td><td>{x['name']}</td><td>{x['knoten'] or DIREKT}</td><td align=right>"
            f"{_text(x['faktor'])}</td><td align=right>{_min(x['zeit_min'])}</td><td align=right>{_euro(x['kosten'])}"
            f"</td><td align=right>{_euro(x['einmal']) if x['einmal'] else ''}</td><td>"
            f"{'Fremdleistung' if x['fremd'] else ''}</td></tr>" for x in e["zeilen"])
        warn = "".join(f"<li>{t}</li>" for t in e["warnungen"])
        self.uebersicht.setText(
            f"<p><b>Nahtlänge je Baugruppe:</b> {naht}</p>"
            f"<table cellspacing=0 cellpadding=3 border=1><tr><th>Art</th><th>Name</th><th>Unterbaugruppe</th>"
            f"<th>Stück je BG</th><th>Zeit je BG</th><th>Kosten je BG</th><th>einmalig</th><th></th></tr>{zeilen}"
            f"</table>" + (f"<p><b>Warnungen</b></p><ul>{warn}</ul>" if warn else ""))

    def fokus(self, status):
        """Zur Zeile springen, die ein Status nennt (D4, Doppelklick auf den Status im Angebot): Reiter wählen und Zeile
        markieren. Ergebnis: (Reiter, Zeile) oder None, wenn der Status keine Zeile nennt."""
        t = str(status or "")
        reiter = {"struktur": 0, "naht": 1, "ag": 2}
        m = re.search(r"Pos\. (\S+?)(?::| hat)", t)
        if m:
            r = next((i for i, z in enumerate(self.teile) if str(z["_q"].get("pos") or "") == m.group(1)), None)
            return self._springen(reiter["struktur"], self.teile_tab, r)
        m = re.search(r"Nahtgruppe (\S+?)(?::| hat|$)", t)
        if m:
            r = next((i for i, n in enumerate(self.bg["naehte"]) if str(n.get("nr") or "") == m.group(1)), None)
            return self._springen(reiter["naht"], self.naht_tab, r)
        m = re.search(r"Stundensatz fehlt \((.+)\)", t) or re.search(r"(?:WARNUNG|FEHLER): (.+?): Unterbaugruppe fehlt", t)
        if m:
            r = next((i for i, a in enumerate(self.bg["arbeitsgaenge"])
                      if (a.get("name") or "Arbeitsgang") == m.group(1)), None)
            return self._springen(reiter["ag"], self.ag_tab, r)
        m = re.search(r"Unterbaugruppe '(.+?)'", t)
        if m:
            r = next((i for i, k in enumerate(self.bg["knoten"]) if (k.get("name") or k.get("id")) == m.group(1)), None)
            return self._springen(reiter["struktur"], self.knoten_tab, r)
        if "der Vorkalkulation offen" in t:
            r = next((i for i, n in enumerate(self.bg["naehte"]) if any(vorkalk.naht_status(n, f) == vorkalk.VORSCHLAG
                                                                        for f in vorkalk.NAHT_FELDER)), None)
            if r is not None:
                return self._springen(reiter["naht"], self.naht_tab, r)
            r = next((i for i, a in enumerate(self.bg["arbeitsgaenge"]) if vorkalk.ag_status(a) == vorkalk.VORSCHLAG),
                     None)
            return self._springen(reiter["ag"], self.ag_tab, r)
        if "Richtwert" in t:
            r = next((i for i, n in enumerate(self.bg["naehte"]) if self._naht_ergebnis(n).get("richtwert")), None)
            return self._springen(reiter["naht"], self.naht_tab, r)
        if "Vorrichtung" in t:
            r = next((i for i, a in enumerate(self.bg["arbeitsgaenge"]) if a.get("umlage") == baugruppe.UMLAGE_WIEDER
                      and a.get("einmal_eur")), None)
            return self._springen(reiter["ag"], self.ag_tab, r)
        if "keine Nahtgruppen" in t:
            return self._springen(reiter["naht"], self.naht_tab, None)
        if "Einzelteile" in t or "doppelt" in t:
            return self._springen(reiter["struktur"], self.teile_tab, None)
        r = min(self.naht_tab.warnzeilen, default=None)
        if r is not None:
            return self._springen(reiter["naht"], self.naht_tab, r)
        return None

    # -------------------------------------------------------------- Vorkalkulation (vorkalk.py)
    def _naht_herkunft(self, z, feld):
        st = vorkalk.naht_status(z, feld)
        return (st, ((z.get("vk") or {}).get(feld) or {}).get("text")) if st else None

    def _ag_herkunft(self, z, _feld):
        st = vorkalk.ag_status(z)
        return (st, (z.get("vk") or {}).get("text")) if st else None

    def vorkalkulation(self):
        """Vorschläge rechnen (Knopf 'Vorkalkulation rechnen'): Heftpunkte und Nacharbeit der Nahtgruppen, Arbeitsgänge
        Rüsten, Positionieren, Wenden, Verputzen; Werte von Hand und bestätigte bleiben. Mit 'Vorkalkulation
        automatisch' vorher alle Nahtvorschläge aus dem STEP als Nahtgruppen (a-Maß nach Regel). Ergebnis:
        vorkalk-Ergebnis."""
        if self.nur_lesen:
            return None
        self._vk_timer.stop()
        self._vk_laeuft = True
        try:
            return self._vorkalkulation()
        finally:
            self._vk_laeuft = False

    def _vk_nach_eingabe(self):
        """Vorkalkulation automatisch nach einer Eingabe; solange in Nahtgruppen oder Arbeitsgängen getippt wird,
        warten (die Tabellen werden dabei neu aufgebaut)."""
        f = QApplication.focusWidget()
        if f is not None and any(t.isAncestorOf(f) for t in (self.naht_tab, self.ag_tab)):
            self._vk_timer.start()
            return
        self.vorkalkulation()

    def _vorkalkulation(self):
        n_neu = 0
        if self.vk_auto.isChecked() and self.bg.get("vorschlaege"):
            verfahren = next((v for _, v in self._verfahren_optionen() if v), None)
            n_neu = baugruppe.vorschlaege_anlegen(self.bg, self._regel_faktor(), verfahren)
            self._vorschlaege_zeigen()
        p = self._position()
        r = vorkalk.vorkalkulieren(p, self._positionen_neu(p), self.tabellen, self.einstellungen)
        neu = {n.get("id"): n for n in r["bg"]["naehte"]}
        for n in self.bg["naehte"]:
            x = neu.get(n.get("id"))
            if x is None:
                continue
            for feld in vorkalk.NAHT_FELDER + ("vk",):
                if x.get(feld) is None:
                    n.pop(feld, None)
                else:
                    n[feld] = x[feld]
        self.bg["arbeitsgaenge"][:] = r["bg"]["arbeitsgaenge"]       # gleiche Liste, die Tabelle zeigt sie
        self.vk_ergebnis = r
        self.naht_tab.aufbauen()
        self.ag_tab.aufbauen()
        self.aktualisieren()
        teile = [f"Vorkalkulation: {len(r['aenderungen'])} Änderung(en)"
                 + (f", {n_neu} Nahtgruppe(n) aus den STEP-Vorschlägen" if n_neu else "")
                 + (", Werte noch Richtwerte" if r["richtwert"] else "")]
        teile += r["hinweise"]
        self.vk_info.setText(" · ".join(teile))
        return r

    def vorschlaege_bestaetigen(self):
        """Alle offenen Vorschläge (gelb) bestätigen, auch die Positionierhilfe der Teile. Ergebnis: Anzahl."""
        if self.nur_lesen:
            return 0
        n = vorkalk.bestaetigen(self.bg)
        for t in self.teile:
            v = self.hilfe_vk.get(t["_id"])
            if t.get("drin") and not t.get("hilfe") and v:
                t["hilfe"] = v[0]
                n += 1
        self.teile_tab.aufbauen()
        self.aktualisieren()
        self.vk_info.setText(f"{n} Vorschläge bestätigt.")
        return n

    def _springen(self, reiter, tab, r):
        self.reiter.setCurrentIndex(reiter)
        if r is not None:
            tab.zeigen(r)
        return reiter, r

    def _naht_ergebnis(self, n):
        x = next((x for x in (self.erg or {}).get("zeilen", ()) if x["art"] == "Naht" and x["id"] == n.get("id")), None)
        return x["werte"] if x else {}

    # -------------------------------------------------------------- Strukturbaum und 3D (D1)
    BAUM = 6                    # Index des Reiters

    def _seite_baum(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        teil = QSplitter(Qt.Horizontal)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        self.baum = StrukturBaum(self.teil_verschieben)
        self.baum.itemSelectionChanged.connect(self.baum_gewaehlt)
        ll.addWidget(self.baum, 1)
        ll.addWidget(hilfe.Hinweis(
            "Klick auf eine Unterbaugruppe, ein Teil oder eine Nahtgruppe hebt die Teile in der 3D-Ansicht blau "
            "hervor. Ein Einzelteil auf eine andere (Unter-)Baugruppe ziehen ändert seine Zuordnung; die Stück je "
            "Baugruppe bleiben, wenn es aufgeht. Naht zeichnen: Punkte entlang der Naht am Modell anklicken, dann als "
            "Nahtgruppe übernehmen.", schluessel="baugruppe_baum"))
        self.baum_rechts = QWidget()
        self.baum_rechts_lay = QVBoxLayout(self.baum_rechts)
        self.baum_rechts_lay.setContentsMargins(0, 0, 0, 0)
        self.baum_info = QLabel()
        self.baum_info.setWordWrap(True)
        self.baum_rechts_lay.addWidget(self.baum_info)
        # Naht im 3D von Hand zeichnen (N2): Punkte am Modell anklicken, Länge und Teile ermittelt das Programm
        self.zeichnen_leiste = QWidget()
        zl = QHBoxLayout(self.zeichnen_leiste)
        zl.setContentsMargins(0, 0, 0, 0)
        self.zeichnen_knopf = QPushButton("Naht zeichnen")
        self.zeichnen_knopf.setCheckable(True)
        self.zeichnen_knopf.setToolTip("Punkte entlang der Naht am Modell anklicken (fängt die nächste Ecke); "
                                       "danach als Nahtgruppe übernehmen")
        self.zeichnen_knopf.toggled.connect(self.naht_zeichnen)
        self.zeichnen_art = QComboBox()
        self.zeichnen_art.addItems(NAHTARTEN)
        self.zeichnen_zurueck = QPushButton("Punkt zurück")
        self.zeichnen_zurueck.clicked.connect(lambda: self.ansicht3d and self.ansicht3d.ansicht.punkt_zurueck())
        self.zeichnen_ok = QPushButton("Als Nahtgruppe übernehmen")
        self.zeichnen_ok.clicked.connect(lambda: self.naht_aus_punkten())
        self.zeichnen_text = QLabel()
        for x in (self.zeichnen_knopf, self.zeichnen_art, self.zeichnen_zurueck, self.zeichnen_ok):
            zl.addWidget(x)
        zl.addWidget(self.zeichnen_text, 1)
        self.zeichnen_leiste.setVisible(False)
        self.baum_rechts_lay.addWidget(self.zeichnen_leiste)
        teil.addWidget(links)
        teil.addWidget(self.baum_rechts)
        teil.setSizes([540, 760])
        lay.addWidget(teil, 1)
        return w

    def _reiter_gewechselt(self, i):
        if i == self.BAUM:
            self.baum_aufbauen()

    def _teil_knoten(self, kid):
        """Knoten-IDs kid und aller Unterbaugruppen darunter ('' = ganze Baugruppe)."""
        ids, neu = {kid}, True
        while neu:
            neu = {k["id"] for k in self.bg["knoten"] if (k.get("parent") or "") in ids} - ids
            ids |= neu
        return ids

    def _teil_titel(self, q):
        return " ".join(str(x) for x in (f"Pos. {q.get('pos') or ''}", q.get("artikel") or q.get("bezeichnung") or "")
                        if x).strip()

    def baum_aufbauen(self):
        """Baum neu: Baugruppe, Unterbaugruppen mit Menge, darin die Einzelteile (Stück je Unterbaugruppe und je
        Baugruppe) und Nahtgruppen; die gewählte Zeile bleibt gewählt."""
        alt = self.baum.currentItem().data(0, Qt.UserRole) if self.baum.currentItem() else ("bg", "")
        self.baum.blockSignals(True)
        self.baum.clear()
        self.baum_items = {}

        def item(eltern, daten, texte, ziehen=False):
            it = QTreeWidgetItem(eltern, [str(t) for t in texte])
            it.setData(0, Qt.UserRole, daten)
            for c in (1, 2):
                it.setTextAlignment(c, int(Qt.AlignRight | Qt.AlignVCenter))
            flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable | (Qt.ItemIsDragEnabled if ziehen else Qt.ItemIsDropEnabled)
            it.setFlags(flags)
            self.baum_items[daten] = it
            return it

        def fuellen(eltern, kid):
            for t in self.teile:
                if t.get("drin") and (t.get("knoten") or "") == kid:
                    f = baugruppe.faktor(self.bg, kid)
                    je = t.get("je") or 1
                    it = item(eltern, ("teil", t["_id"]), (self._teil_titel(t["_q"]), _text(je),
                                                           _text(je * f) if f is not None else "?"), True)
                    it.setToolTip(0, self._teil_text(t, 0) + ("" if t["_id"] in self.netze else " (ohne 3D-Daten)"))
            for n in self.bg["naehte"]:
                if (n.get("knoten") or "") == kid:
                    text = f"Nahtgruppe {n.get('nr') or ''}: {n.get('nahtart') or ''} {_text(n.get('laenge'))} mm"
                    it = item(eltern, ("naht", n.get("id")), (text.strip(), _text(n.get("anzahl") or 1), ""))
                    it.setForeground(0, QBrush(stil.farbe(GRAU)))
            for k in self.bg["knoten"]:
                if (k.get("parent") or "") == kid:
                    f = baugruppe.faktor(self.bg, k["id"])
                    it = item(eltern, ("knoten", k["id"]), (k.get("name") or "Unterbaugruppe", _text(k.get("menge") or 1),
                                                            _text(f) if f is not None else "?"))
                    fuellen(it, k["id"])

        wurzel = item(self.baum, ("bg", ""), (self.bezeichnung.text().strip() or "Baugruppe", "",
                                              _text(1)))
        fuellen(wurzel, "")
        self.baum.expandAll()
        self.baum.setCurrentItem(self.baum_items.get(alt) or wurzel)
        self.baum.blockSignals(False)
        if self.ansicht3d is None and self.netze and any(t["_id"] in self.netze for t in self.teile):
            from .baugruppe_ansicht import BaugruppenAnsicht
            self.ansicht3d = BaugruppenAnsicht(geaendert=self.baum_gewaehlt, vor_messen=self._vor_messen)
            self.laengsnaht_knopf_anlegen(self.nur_lesen)
            self.ansicht3d.ansicht.angeklickt.connect(self._3d_geklickt)
            self.baum_rechts_lay.insertWidget(0, self.ansicht3d, 1)
            self.ansicht3d.ansicht.gemessen.connect(lambda _: self._zeichnen_stand())
            self.zeichnen_leiste.setVisible(not self.nur_lesen)
            self._zeichnen_stand()
        self.baum_gewaehlt()

    def _gewaehlte_teile(self, daten):
        """(Positions-IDs zum Hervorheben, Text) für eine Zeile des Baums."""
        art, wert = daten
        drin = [t for t in self.teile if t.get("drin")]
        if art == "teil":
            q = next((t["_q"] for t in drin if t["_id"] == wert), {})
            return {wert}, f"blau: {self._teil_titel(q)}"
        if art == "knoten":
            ids = self._teil_knoten(wert)
            name = next((k.get("name") for k in self.bg["knoten"] if k["id"] == wert), "")
            return {t["_id"] for t in drin if (t.get("knoten") or "") in ids}, f"blau: Teile von {name}"
        if art == "naht":
            n = next((x for x in self.bg["naehte"] if x.get("id") == wert), {})
            koerper = set(n.get("koerper") or ())
            mit = {t["_id"] for t in drin if koerper & set(self._netz(t["_id"]).get("koerper") or ())}
            if mit:
                return mit, f"blau: Teile der Nahtgruppe {n.get('nr') or ''} (aus den Nahtkandidaten)"
            ids = self._teil_knoten(n.get("knoten") or "")
            return ({t["_id"] for t in drin if (t.get("knoten") or "") in ids},
                    f"blau: Teile der Unterbaugruppe der Nahtgruppe {n.get('nr') or ''}")
        return set(), "gleiche Teile in gleicher Farbe"

    def baum_gewaehlt(self):
        it = self.baum.currentItem()
        art, kid = it.data(0, Qt.UserRole) if it else ("bg", "")
        hervor, text = self._gewaehlte_teile((art, kid))
        self.baum_hervor = hervor
        self.zeige_3d(hervor, text, naht=kid if art == "naht" else None)

    def naht_linien(self, naht=None):
        """Schweißnähte für die 3D-Ansicht: {Art: [Linienzüge]} mit SN = Nahtgruppen, SV = noch offene Nahtvorschläge
        aus dem STEP-Import, SH = Nahtgruppe naht (gewählt). Nur Nähte mit Nahtverlauf (STEP-JSON 1.16)."""
        linien = {}
        for art, zuege, _, _ in self._naehte_3d(naht):
            linien.setdefault(art, []).extend(zuege)
        return linien

    def _naehte_3d(self, naht=None, koerper_netz=None, nur_koerper=None):
        """Nähte für die Raupen (B3): [(Art, Linienzüge, Nahtart, Größe)]; Größe = a-Maß bzw. Dicke (ohne: nur
        für das Bild eine Vorgabe). Nahtgruppen ohne Verlauf bekommen ihn aus dem Stoß (koerper_netz, 3a).
        nur_koerper: nur Nähte zwischen diesen Körpern (Nur Gewähltes) und die gewählte."""
        from .baugruppe_ansicht import verlauf_aus_stoss
        out, self._abgeleitet = [], 0
        for n in self.bg.get("naehte") or []:
            zuege = n.get("linien")
            if not zuege and koerper_netz:
                zuege = verlauf_aus_stoss(n, self.bg.get("stoesse"), koerper_netz)
                self._abgeleitet += 1 if zuege else 0
            if nur_koerper is not None and n.get("id") != naht and \
                    not {str(k) for k in n.get("koerper") or ()} <= nur_koerper:
                continue
            if zuege:
                groesse = n.get("mass") if isinstance(n.get("mass"), (int, float)) and n["mass"] > 0 else \
                    (0.7 * n["dicke"] if n.get("nahtart") == "Kehlnaht" else n["dicke"]) \
                    if isinstance(n.get("dicke"), (int, float)) and n["dicke"] > 0 else None
                out.append(("SH" if n.get("id") == naht else "SN", zuege, n.get("nahtart"), groesse))
        for v in self.bg.get("vorschlaege") or []:
            koerper = {str(k) for paar in v.get("teile") or () if isinstance(paar, (list, tuple)) for k in paar}
            if nur_koerper is not None and not koerper <= nur_koerper:
                continue
            if v.get("linien"):
                d = v.get("dicke") if isinstance(v.get("dicke"), (int, float)) and v["dicke"] > 0 else None
                out.append(("SV", v["linien"], v.get("nahtart"),
                            (0.7 * d if v.get("nahtart") == "Kehlnaht" else d) if d else None))
        return out

    def zeige_3d(self, hervor=(), text="", naht=None):
        """Baugruppe in Einbaulage: je Einzelteil alle gleichen Körper der STEP-Datei, hervor (Positions-IDs) blau,
        dazu die Schweißnähte als Raupe (naht = ID der gewählten Nahtgruppe, rot). Rohre aus den Eingaben mit
        Schlitzen und Nasen (B2), sonst das STEP-Netz. Ergebnis: Anzahl gezeigter Körper."""
        nur = bool(hervor) and getattr(self.ansicht3d, "nur_gewaehlt", False)
        rohre = self._rohr_modelle() if self.ansicht3d is not None else {}
        netze, besitzer, farbe, koerper, koerper_netz, lagen = [], [], [], [], {}, []
        for n, t in enumerate(x for x in self.teile if x.get("drin")):
            netz = self._netz(t["_id"])
            nummern = netz.get("koerper") or []
            modell = rohre.get(t["_id"])
            for j, lage in enumerate(netz.get("lagen") or ([netz["lage"]] if netz.get("lage") else [])):
                kn = nummern[j] if j < len(nummern) else None
                if kn is not None:
                    koerper_netz[str(kn)] = (modell or netz, lage)
                if nur and t["_id"] not in hervor:
                    continue
                netze.append(dict(modell or netz, lage=lage))
                besitzer.append(t["_id"])
                farbe.append(n)
                koerper.append(kn)
                lagen.append((t["_id"], lage, modell or netz))
        n_teile = sum(1 for t in self.teile if t.get("drin"))
        ohne = n_teile - len(set(besitzer)) if not nur else 0
        if self.ansicht3d is None:
            self.baum_info.setText("Keine 3D-Daten: die Teile kommen nicht aus dem STEP-Import (oder aus einer älteren "
                                   "Messung ohne Einbaulage)." if n_teile else "Noch keine Einzelteile zugeordnet.")
            return 0
        from .ansicht3d import baugruppe as zusammen
        from .baugruppe_ansicht import Flaechen, naehte_einsetzen, teil_kennung
        bereiche = []
        netz, _ = zusammen(netze, {i for i, b in enumerate(besitzer) if b in hervor and not nur}, farbe,
                           bereiche=bereiche)
        self._koerper_lage = lagen
        if netz:                    # Klick auf eine Fläche findet ihr Teil (Längsnaht wählen)
            teil_kennung(netz, bereiche, [f"teil:{i}" for i in range(len(netze))])
            nl = self.laengsnaht_linien(lagen)
            if nl:
                netz["l"]["NL"] = nl
        self._koerper_3d = [(besitzer[nr], koerper[nr], netz["p"], von, bis, dreiecke)
                            for nr, von, bis, dreiecke in bereiche] if netz else []
        info = f"{len(netze)} Körper in Einbaulage, {text}."
        if rohre:
            info += " Rohre aus den Eingaben (mit Schlitzen und Nasen der Steckverbindungen)."
        if netz and getattr(self.ansicht3d, "naehte", True):
            naehte = self._naehte_3d(naht, koerper_netz, {str(k) for k in koerper} if nur else None)
            schluessel = json.dumps([[b, k] for b, k in zip(besitzer, koerper)] + [sorted(
                (pid, (self._rohr_cache.get(pid) or ("",))[0]) for pid in rohre)], default=str)
            if getattr(self, "_flaechen", (None,))[0] != schluessel:
                self._flaechen = (schluessel, Flaechen(netz))
            raupen = naehte_einsetzen(netz, naehte, self._flaechen[1])
            ohne_verlauf = sum(1 for n in self.bg.get("naehte") or [] if not n.get("linien")) - self._abgeleitet
            if naehte:
                info += (" Schweißnähte als Raupe schwarz, Vorschläge magenta, gewählte Naht rot" +
                         (f" ({self._abgeleitet} Verlauf aus dem Stoß abgeleitet)" if self._abgeleitet else "") + "."
                         if raupen else " Schweißnähte schwarz, Vorschläge magenta, gewählte Naht rot.")
            if ohne_verlauf > 0:
                info += (f" {ohne_verlauf} Nahtgruppe{'n' if ohne_verlauf != 1 else ''} ohne Nahtverlauf (im Reiter "
                         "Nahtgruppen angelegt oder älterer STEP-Import: neu importieren oder im 3D zeichnen).")
        if ohne:
            info += f" {ohne} Teil{'e' if ohne != 1 else ''} ohne 3D-Daten fehlen."
        weniger = self.weniger_im_3d(besitzer) if not nur else []
        if weniger:
            info += (" Nicht alle Stück im 3D (die STEP-Datei enthält weniger Körper, z. B. Menge von Hand erhöht oder "
                     "Unterbaugruppe aus eigener Datei): " + "; ".join(weniger) + ".")
        self.ansicht3d.setzen(netz, self.bezeichnung.text().strip() or "Baugruppe", info)
        self.baum_info.setText("")
        return len(netze)

    def weniger_im_3d(self, besitzer):
        """Teile, die öfter in der Baugruppe stecken, als die 3D-Ansicht Körper hat: ['Pos. 10 …: 1 von 4 Stück']."""
        out = []
        for t in self.teile:
            if not t.get("drin") or t["_id"] not in besitzer:
                continue
            soll = (t.get("je") or 1) * (baugruppe.faktor(self.bg, t.get("knoten") or "") or 1)
            ist = besitzer.count(t["_id"])
            if ist < soll:
                out.append(f"{self._teil_titel(t['_q'])}: {ist} von {soll} Stück")
        return out

    # -------------------------------------------------------------- Naht im 3D zeichnen (N2)
    def _vor_messen(self):
        self.naht_zeichnen(False)
        self.laengsnaht_aus()

    def _3d_geklickt(self, treffer):
        """Klick auf eine Fläche im 3D: mit „Längsnaht wählen“ die Längsnaht dieses Rohrs setzen."""
        kennung = str((treffer or {}).get("id") or "")
        lagen = getattr(self, "_koerper_lage", [])
        if not kennung.startswith("teil:") or not self.laengsnaht_knopf.isChecked() or self.nur_lesen:
            return None
        nr = int(kennung[5:])
        if nr >= len(lagen):
            return None
        pid, lage, modell = lagen[nr]
        return self.laengsnaht_setzen(pid, treffer["punkt"], lage, modell)

    def naht_zeichnen(self, an):
        """Zeichenmodus der 3D-Ansicht an/aus: Klicks setzen Punkte eines Linienzugs (fängt die nächste Ecke)."""
        if an:
            self.laengsnaht_aus()
        if self.ansicht3d is not None:
            if an and hasattr(self.ansicht3d, "messen_aus"):
                self.ansicht3d.messen_aus()             # Messen der Leiste aus, die Klicks gehören der Naht
            self.ansicht3d.ansicht.messen_setzen(bool(an), punkte=0)
        if self.zeichnen_knopf.isChecked() != bool(an):
            self.zeichnen_knopf.setChecked(bool(an))
        self._zeichnen_stand()

    def _zeichnen_stand(self):
        a = self.ansicht3d.ansicht if self.ansicht3d is not None else None
        n = len(a.messpunkte) if a is not None and a.messen else 0
        self.zeichnen_zurueck.setEnabled(n > 0)
        self.zeichnen_ok.setEnabled(n > 1)
        self.zeichnen_text.setText(f"{n} Punkt{'e' if n != 1 else ''}, {zahl_als_text(round(a.abstand(), 1))} mm"
                                   if n > 1 else f"{n} Punkt" if n else "")

    def teile_an(self, punkte, toleranz=NAHT_TOLERANZ):
        """Körper, die alle Punkte berühren (Abstand zur Oberfläche ≤ toleranz mm): [(Positions-ID, Körpernummer)],
        nächste zuerst."""
        treffer = []
        for pid, kn, p, von, bis, dreiecke in getattr(self, "_koerper_3d", []):
            box = [(min(p[3 * von + k:3 * bis:3]) - toleranz, max(p[3 * von + k:3 * bis:3]) + toleranz)
                   for k in range(3)]
            if any(not all(box[k][0] <= q[k] <= box[k][1] for k in range(3)) for q in punkte):
                continue
            abstand = max(_abstand_flaeche(q, p, dreiecke) for q in punkte)
            if abstand <= toleranz:
                treffer.append((abstand, pid, kn))
        return [(pid, kn) for _, pid, kn in sorted(treffer, key=lambda x: x[0])]

    def _gemeinsamer_knoten(self, knoten):
        """Unterste (Unter-)Baugruppe, die alle knoten enthält ('' = Baugruppe)."""
        def kette(k):
            out = [k]
            while k:
                k = next((x.get("parent") or "" for x in self.bg["knoten"] if x["id"] == k), "")
                out.append(k)
            return out
        ketten = [kette(k or "") for k in knoten]
        if not ketten:
            return ""
        return next((k for k in ketten[0] if all(k in c for c in ketten[1:])), "")

    def _wand(self, pids):
        """Kleinste Wanddicke der Teile pids aus den Profilen (Stammdaten) oder None."""
        if self.db is None:
            return None
        ids = {str(t["_q"].get("profil_id")) for t in self.teile if t["_id"] in pids and t["_q"].get("profil_id")}
        werte = [z["wand"] for z in self.db.zeilen("profile")
                 if str(z.get("profil_id")) in ids and isinstance(z.get("wand"), (int, float)) and z["wand"] > 0]
        return min(werte) if werte else None

    def naht_aus_punkten(self, punkte=None, nahtart=None):
        """Nahtgruppe aus einem im 3D gezeichneten Linienzug (punkte, sonst die geklickten): Länge = Länge des Zugs,
        Teile = Körper, die den ganzen Zug berühren, Unterbaugruppe = gemeinsame der Teile, Dicke = dünnste Wand.
        Ergebnis: ID der Nahtgruppe oder None (weniger als 2 Punkte)."""
        if punkte is None:
            punkte = self.ansicht3d.ansicht.messpunkte if self.ansicht3d is not None else []
        punkte = [tuple(q) for q in punkte]
        if len(punkte) < 2 or self.nur_lesen:
            return None
        laenge = sum(math.dist(a, b) for a, b in zip(punkte, punkte[1:]))
        teile = self.teile_an(punkte)
        pids = {pid for pid, _ in teile}
        knoten = self._gemeinsamer_knoten([next((t.get("knoten") or "" for t in self.teile if t["_id"] == pid), "")
                                           for pid in pids])
        werte = dict(knoten=knoten, nahtart=nahtart or self.zeichnen_art.currentText(), laenge=round(laenge, 1),
                     anzahl=1, quelle="3D", linien=[[round(v, 1) for q in punkte for v in q]])
        if teile and all(kn is not None for _, kn in teile):
            werte["koerper"] = sorted({str(kn) for _, kn in teile})
        wand = self._wand(pids)
        if wand:
            werte["dicke"] = wand
            if werte["nahtart"] != "Kehlnaht":
                werte["mass"] = wand
        nid = self.naht_neu(werte)
        if self.ansicht3d is not None:
            self.ansicht3d.ansicht.messen_setzen(self.zeichnen_knopf.isChecked(), punkte=0)
        self.baum_aufbauen()
        if ("naht", nid) in self.baum_items:
            self.baum.setCurrentItem(self.baum_items[("naht", nid)])
        self._zeichnen_stand()
        return nid

    def teil_verschieben(self, pid, knoten):
        """Einzelteil pid in die (Unter-)Baugruppe knoten ('' = Baugruppe selbst) legen (Ziehen im Baum). Stück je
        Unterbaugruppe so, dass das Stück je Baugruppe bleibt, wenn die Teilung aufgeht."""
        t = next((x for x in self.teile if x["_id"] == pid), None)
        if t is None or self.nur_lesen or (t.get("knoten") or "") == knoten:
            return False
        alt = baugruppe.faktor(self.bg, t.get("knoten") or "") or 1
        neu = baugruppe.faktor(self.bg, knoten) or 1
        gesamt = (t.get("je") or 1) * alt
        je = gesamt // neu if gesamt % neu == 0 else (t.get("je") or 1)
        self.teil_setzen(pid, True, knoten, int(je))
        self.baum_aufbauen()
        return True

    # -------------------------------------------------------------- Vorlagen (P1)
    def vorlagen(self):
        return self.db.zeilen(VORLAGEN) if self.db is not None else []

    def vorlage_speichern(self, name, bemerkung=None, ueberschreiben=False):
        """Aktuelle Baugruppe ohne Einzelteile als Vorlage name speichern. ValueError, wenn es den Namen schon gibt und
        ueberschreiben nicht gesetzt ist. Ergebnis: ID der Vorlage."""
        name = (name or "").strip()
        if not name:
            raise ValueError("Bitte einen Namen für die Vorlage eintragen.")
        v = baugruppe.vorlage_aus(self.daten())
        werte = dict(name=name, inhalt=baugruppe.vorlage_inhalt(v), daten=json.dumps(v, ensure_ascii=False),
                     angelegt=datetime.datetime.now().isoformat(timespec="seconds"), bemerkung=bemerkung)
        alt = next((z for z in self.vorlagen() if z["name"] == name), None)
        if alt and not ueberschreiben:
            raise ValueError(f"Die Vorlage '{name}' gibt es schon.")
        if alt:
            for feld in ("inhalt", "daten", "angelegt", "bemerkung"):
                self.db.aendern(VORLAGEN, alt["id"], feld, werte[feld])
            return alt["id"]
        return self.db.neu(VORLAGEN, werte)

    def vorlage_einsetzen(self, vorlage_id):
        """Vorlage übernehmen: Stammdaten, Unterbaugruppen, Nahtgruppen und Arbeitsgänge werden ersetzt, die Teile
        bleiben in der Baugruppe (in einer Unterbaugruppe, die es nicht mehr gibt: direkt an der Baugruppe).
        Kennwerte gelten aus den aktuellen Stammdaten. Ergebnis: True = eingesetzt."""
        z = next((x for x in self.vorlagen() if x["id"] == vorlage_id), None)
        try:
            v = json.loads(z["daten"]) if z else None
        except (TypeError, ValueError):
            v = None
        if not isinstance(v, dict):
            self.fehler.setText("Die Vorlage ist leer oder beschädigt.")
            return False
        knoten = baugruppe.vorlage_einsetzen(self.bg, v, z.get("name"))
        for t in self.teile:
            if t.get("knoten") and t["knoten"] not in knoten:
                t["knoten"] = ""
        self.stand_alt = {}
        for n, f in self.stamm_felder.items():
            w = str(self.bg["stamm"].get(n) or "")
            f.setPlainText(w) if isinstance(f, QPlainTextEdit) else f.setText(w)
        for n, f in self.stamm_wahl.items():
            f.setChecked(bool(self.bg["stamm"].get(n)))
        for tab in (self.knoten_tab, self.teile_tab, self.naht_tab, self.ag_tab):
            tab.aufbauen()
        self._vorschlaege_zeigen()
        self.aktualisieren()
        return True

    def vorlage_merken(self):
        name, ok = QInputDialog.getText(self, "Als Vorlage speichern", "Name der Vorlage:",
                                        text=self.bezeichnung.text().strip())
        if not ok:
            return None
        try:
            return self.vorlage_speichern(name)
        except ValueError as e:
            if "gibt es schon" not in str(e):
                QMessageBox.warning(self, "Vorlage", str(e))
                return None
            if QMessageBox.question(self, "Vorlage", f"{e} Überschreiben?") != QMessageBox.Yes:
                return None
            return self.vorlage_speichern(name, ueberschreiben=True)

    def vorlage_waehlen(self):
        liste = self.vorlagen()
        if not liste:
            QMessageBox.information(self, "Vorlagen", "Noch keine Vorlage gespeichert: eine fertige Baugruppe mit "
                                                      "„Als Vorlage speichern …“ merken.")
            return False
        texte = [f"{z['name']} ({z.get('inhalt') or ''})" for z in liste]
        wahl, ok = QInputDialog.getItem(self, "Vorlage einsetzen", "Vorlage (ersetzt Struktur, Nahtgruppen und "
                                        "Arbeitsgänge):", texte, 0, False)
        if not ok:
            return False
        return self.vorlage_einsetzen(liste[texte.index(wahl)]["id"])

    def pruefen(self):
        """Fehlertext (ungültige Zahlen, Struktur), sonst None."""
        for tab in (self.knoten_tab, self.teile_tab, self.naht_tab, self.ag_tab, self.steck_tab):
            if tab.ungueltig:
                return "Bitte nur Zahlen eintragen (rot markierte Felder)."
        fehler = baugruppe.struktur_fehler(self.bg)
        if fehler:
            return fehler
        if any(t.get("drin") and t.get("gravur") and not 1 <= (t.get("gravur_h") or 0) <= 200 for t in self.teile):
            return "Schrifthöhe der Gravur zwischen 1 und 200 mm eingeben."
        for n, v in enumerate(self.bg["steckverbindungen"], 1):
            f = self._steck_fehler(v)
            if f:
                return f"Steckverbindung {n}: {f}"
        f = self.knick_pruefen()
        if f:
            return f
        for liste in (self.bg["naehte"], self.bg["arbeitsgaenge"]):
            for x in liste:
                for k, v in x.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
                        return "Negative Werte sind nicht erlaubt."
        return None

    def step_name(self):
        return self.bezeichnung.text().strip() or self.artikel.text().strip() or "Baugruppe"

    def _ok(self):
        if self.nur_lesen:
            return
        f = self.pruefen()
        if f:
            self.fehler.setText(f)
            return
        if self.vk_auto.isChecked():
            self.vorkalkulation()
        self.ergebnis = self.werte()
        self.accept()

    def werte(self):
        """Ergebnis: dict(position = Felder der Baugruppen-Position, teile = {Positions-ID: dict(bg_knoten,
        je_knoten, bg_hilfe)} nur für geänderte Zuordnungen)."""
        bg = self.daten()
        for n in bg["naehte"]:          # Kennwerte merken, wenn die Nahtgruppe damit vollständig rechnet
            if "stand" not in n:
                st = baugruppe.naht_stand(n, self.tabellen)
                if not baugruppe.naht_rechnen(dict(n, stand=st), self.tabellen, self.saetze)["fehlt"]:
                    n["stand"] = st
        p = self._position(bg)
        teile = {}
        for t in self.teile:
            neu = self._zuordnung(t)
            q = t["_q"]
            if any(w != (q.get(k) or None) for k, w in neu.items()) or blech_gravur_alt(q, neu["bg_gravur"]):
                teile[t["_id"]] = neu
        weg, dazu = steckverbindung.aenderungen(self.steck_alt, bg.get("steckverbindungen") or [])
        return dict(position={k: p.get(k) for k in ("art", "stueck", "baugruppe", "bezeichnung", "artikel")},
                    teile=teile, stecken=dict(weg=weg, dazu=dazu), naehte=self.laengsnaht_werte(),
                    knicke=list(self.knicke))
