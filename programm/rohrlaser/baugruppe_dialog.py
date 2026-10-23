"""Editor 'Schweißbaugruppe' (Plan Schweißbaugruppen, Teil 2): Kopf (Bezeichnung, Artikelnummer, Anzahl), Reiter
Stammdaten, Struktur und Teile (Unterbaugruppen mit Menge, Einzelteile aus der Positionsliste), Nahtgruppen,
Arbeitsgänge (mit Einmalkosten und Umlage) und Übersicht. Gerechnet wird mit baugruppe.rechnen, live bei jeder
Eingabe; gespeichert wird erst mit OK (ergebnis), das Angebot schreibt dann Position und Zuordnung der Teile.

Kennwerte einer Nahtgruppe: Beim Speichern merkt sich jede vollständig berechenbare Nahtgruppe ihren Stand
(baugruppe.naht_stand), damit spätere Änderungen der Stammdaten ein Angebot nicht verändern. Ändert man Verfahren,
Nahtart, Nahtgröße, Lage, Zugänglichkeit oder Qualität, gilt der neue Stand aus den Stammdaten; 'Kennwerte neu aus
Stammdaten' setzt alle Nahtgruppen auf die aktuellen Stammdaten."""
import copy
import html
import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QSpinBox,
                               QGroupBox, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from . import baugruppe, hilfe
from .kostenbalken import Kostenbalken
from .angebot import BAUGRUPPE, ist_baugruppe
from .stammdaten import NAHTARTEN, zahl_als_text, zahl_aus_text
from .stil import BLAU_FLAECHE, GELB_FLAECHE, GELB_TEXT

FEHLER_FARBE = "#B42318"
GRAU = "#5F6B7A"
WARNUNG = "warnung"         # Anzeige (Text, WARNUNG): Zeile gelb hinterlegt (D4)
RICHTWERT = (f"<span style='background: {BLAU_FLAECHE}; color: #1F4E78; border-radius: 3px;'>&nbsp;Richtwert&nbsp;"
             "</span>")
DIREKT = "(Baugruppe selbst)"
NAHT_SCHLUESSEL = ("verfahren", "nahtart", "mass", "lage", "zugang", "qualitaet")    # neuer Stand, wenn geändert
ARBEITSGAENGE = ("Vorrichten", "Heften", "Richten", "Schleifen", "Verputzen", "Entgraten", "Bohren", "Gewindeschneiden",
                 "Montage", "Prüfen", "Reinigen", "Verpacken", "Vorrichtung", "Programmierung Roboter",
                 "Strahlen (Fremd)", "Verzinken (Fremd)", "Pulverbeschichten (Fremd)")
LANGTEXT = ("beschreibung", "bemerkung", "intern")


def _text(w, stellen=None):
    return zahl_als_text(w, stellen, tausender=False) if isinstance(w, (int, float)) and not isinstance(w, bool) else ""


def _euro(w):
    return zahl_als_text(round(w or 0.0, 2), 2) + " €"


def _min(w):
    return zahl_als_text(round(w or 0.0, 1), 1) + " min"


class Spalte:
    """Spalte einer ZeilenTabelle. typ: text, zahl, ganz, auswahl (optionen() = [(Text, Wert)], frei = eigene Texte
    erlaubt), haken oder anzeige (anzeige(zeile, index) = Text, nur lesen; (Text, True) rot, (Text, WARNUNG) gelb
    hinterlegt mit markierter Zeilennummer)."""

    def __init__(self, schluessel, titel, typ="text", breite=90, optionen=None, frei=False, anzeige=None, tipp=""):
        self.schluessel, self.titel, self.typ, self.breite = schluessel, titel, typ, breite
        self.optionen, self.frei, self.anzeige, self.tipp = optionen, frei, anzeige, tipp


class ZeilenTabelle(QTableWidget):
    """Tabelle über einer Liste von dicts (self.zeilen): jede Eingabe ändert sofort das dict und ruft geaendert();
    Anzeigespalten werden mit auffrischen() neu beschriftet. Ungültige Zahlen: Feld rot, Wert None, in self.ungueltig."""

    def __init__(self, spalten, zeilen, geaendert):
        super().__init__(0, len(spalten))
        self.spalten, self.zeilen, self.geaendert = spalten, zeilen, geaendert
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
            kopf = self.verticalHeaderItem(r) or QTableWidgetItem(str(r + 1))
            kopf.setText(f"⚠ {r + 1}" if r in self.warnzeilen else str(r + 1))
            kopf.setToolTip("Zeile prüfen (Hinweis)" if r in self.warnzeilen else "")
            kopf.setBackground(QColor(GELB_FLAECHE) if r in self.warnzeilen else QBrush())
            self.setVerticalHeaderItem(r, kopf)

    def zeigen(self, r):
        """Zeile r markieren und hineinscrollen (Sprung vom Status, D4)."""
        if 0 <= r < self.rowCount():
            self.selectRow(r)
            self.scrollTo(self.model().index(r, 0))

    def markierte(self):
        return sorted({i.row() for i in self.selectionModel().selectedRows()})


class BaugruppeDialog(QDialog):
    """p: Position der Art Schweißbaugruppe (neu: leeres dict mit pos); positionen: alle Positionen des Angebots;
    tabellen: Stammdaten (Schweißverfahren, -kennwerte, -faktoren); saetze: Stundensätze des Angebots {ID: €/h}.
    vorwahl: IDs von Positionen, die neu in die Baugruppe kommen (markierte Zeilen beim Anlegen)."""

    def __init__(self, parent, p, positionen, tabellen, saetze, vorwahl=()):
        super().__init__(parent)
        self.p, self.positionen, self.tabellen, self.saetze = p, positionen, tabellen, saetze
        self.bg = baugruppe.lesen(p.get("baugruppe")) or baugruppe.leer()
        self.bg = copy.deepcopy(self.bg)
        self.stand_alt = {n.get("id"): {k: n.get(k) for k in NAHT_SCHLUESSEL} for n in self.bg["naehte"]}
        self.stand_verwerfen = False
        self.ergebnis, self.erg, self.status = None, None, None
        self._teile_aufbauen(vorwahl)
        self.setWindowTitle(f"Schweißbaugruppe Pos. {p.get('pos') or ''} {baugruppe.name(p, self.bg)}".strip())
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
        self.reiter.addTab(self._seite_stamm(), "Stammdaten")
        self.reiter.addTab(self._seite_uebersicht(), "Übersicht")
        lay.addWidget(self.reiter, 1)
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        lay.addWidget(self.summe)
        self.fehler = QLabel()
        self.fehler.setWordWrap(True)
        self.fehler.setStyleSheet(f"color: {FEHLER_FARBE};")
        lay.addWidget(self.fehler)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.aktualisieren()

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
                                   (q.get("je_satz") or 1) if drin else 1))

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
            Spalte("_je", "Stück je\nBaugruppe", "anzeige", 110, anzeige=self._teil_je)],
            self.teile, self.aktualisieren)
        rechts.addWidget(self.teile_tab, 1)
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
            Spalte("laenge", "Länge je\nNaht [mm]", "zahl", 85),
            Spalte("anzahl", "Anzahl", "ganz", 55, tipp="Gleiche Nähte je Stück der Unterbaugruppe"),
            Spalte("beidseitig", "beidseitig", "haken", 65),
            Spalte("heftpunkte", "Heftpunkte\nje Naht", "ganz", 75),
            Spalte("lage", "Lage", "auswahl", 60, optionen=lambda: self._faktor_optionen("Schweißlage", baugruppe.LAGEN),
                   tipp=", ".join(f"{k} {v}" for k, v in baugruppe.LAGEN.items())),
            Spalte("zugang", "Zugänglichkeit", "auswahl", 95, optionen=lambda: self._faktor_optionen("Zugänglichkeit")),
            Spalte("qualitaet", "Qualität", "auswahl", 85, optionen=lambda: self._faktor_optionen("Qualität")),
            Spalte("zeit_hand", "Zeit von\nHand [min]", "zahl", 80, tipp="Zeit je Stück der Unterbaugruppe; geht vor"),
            Spalte("_zeit", "Zeit je\nBaugruppe", "anzeige", 95, anzeige=lambda z, r: self._zeile_wert("Naht", z, "zeit")),
            Spalte("_kosten", "Kosten je\nBaugruppe", "anzeige", 95,
                   anzeige=lambda z, r: self._zeile_wert("Naht", z, "kosten")),
            Spalte("_hinweis", "Hinweis", "anzeige", 200, anzeige=lambda z, r: self._zeile_wert("Naht", z, "hinweis"))],
            self.bg["naehte"], self.aktualisieren)
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
        for b in (neu, kopie, weg, stamm):
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
        leiste.addWidget(uebernehmen)
        leiste.addWidget(verwerfen)
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
        neu = [self.naht_neu(baugruppe.vorschlag_naht(self.bg["vorschlaege"][r])) for r in zeilen]
        self.vorschlaege_verwerfen(zeilen)
        return neu

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
            Spalte("name", "Arbeitsgang", "auswahl", 150, optionen=[(a, a) for a in ARBEITSGAENGE], frei=True),
            Spalte("knoten", "Unterbaugruppe", "auswahl", 130, optionen=lambda: self._knoten_optionen()),
            Spalte("satz_id", "Stundensatz", "auswahl", 150, optionen=self._satz_optionen),
            Spalte("menge", "Menge", "zahl", 55, tipp="Einheiten je Stück der Unterbaugruppe (leer = 1)"),
            Spalte("zeit_min", "Zeit je\nEinheit [min]", "zahl", 80),
            Spalte("kosten_einheit", "Kosten je\nEinheit [€]", "zahl", 80, tipp="z. B. Fremdleistung, Material"),
            Spalte("ruest_min", "Rüstzeit\n[min]", "zahl", 70, tipp="einmal je Auftrag bzw. Staffelstufe"),
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
            self.bg["arbeitsgaenge"], self.aktualisieren)
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
        lay.addLayout(leiste)
        lay.addWidget(hilfe.Hinweis(
            "Laufende Kosten je Stück: Zeit je Einheit × Menge × Stundensatz + Kosten je Einheit × Menge. Rüstzeit "
            "und Einmalbetrag fallen einmal je Auftrag bzw. Staffelstufe an und werden auf die Baugruppen verteilt: "
            "'je Auftrag' ganz, 'anteilig' mit dem Anteil in %, 'wiederverwendbar' gar nicht (Vorrichtung schon "
            "vorhanden). Fremd = Fremdleistung mit Zuschlag Fremdleistung.", schluessel="baugruppe_arbeitsgaenge"))
        return w

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
            neu = {k: v for k, v in copy.deepcopy(liste[r]).items() if k != "stand"}
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
            return dict(bg_knoten=None, je_knoten=None)
        return dict(bg_knoten=baugruppe.zuordnung_text(self.bg["id"], t.get("knoten") or ""), je_knoten=t.get("je") or 1)

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
            if self._naht_aktuell(z).get("stand"):
                teile.append(f"Kennwerte vom {z['stand'].get('datum') or '?'}")
            return ", ".join(teile)
        if w.get("umlage") == baugruppe.UMLAGE_WIEDER and w.get("einmal"):
            return "wiederverwendbar: einmalig nicht berechnet"
        return ""

    def aktualisieren(self, *_):
        bg = self.daten()
        p = self._position(bg)
        self.erg = baugruppe.rechnen(p, self.tabellen, self.saetze)
        for tab in (getattr(self, "knoten_tab", None), getattr(self, "teile_tab", None),
                    getattr(self, "naht_tab", None), getattr(self, "ag_tab", None)):
            if tab is not None:
                tab.auffrischen()
        if not hasattr(self, "summe"):
            return
        w = dict(bg_tabellen=self.tabellen, saetze=self.saetze)
        positionen = self._positionen_neu(p)
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

    def _springen(self, reiter, tab, r):
        self.reiter.setCurrentIndex(reiter)
        if r is not None:
            tab.zeigen(r)
        return reiter, r

    def _naht_ergebnis(self, n):
        x = next((x for x in (self.erg or {}).get("zeilen", ()) if x["art"] == "Naht" and x["id"] == n.get("id")), None)
        return x["werte"] if x else {}

    def pruefen(self):
        """Fehlertext (ungültige Zahlen, Struktur), sonst None."""
        for tab in (self.knoten_tab, self.teile_tab, self.naht_tab, self.ag_tab):
            if tab.ungueltig:
                return "Bitte nur Zahlen eintragen (rot markierte Felder)."
        fehler = baugruppe.struktur_fehler(self.bg)
        if fehler:
            return fehler
        for liste in (self.bg["naehte"], self.bg["arbeitsgaenge"]):
            for x in liste:
                for k, v in x.items():
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and v < 0:
                        return "Negative Werte sind nicht erlaubt."
        return None

    def _ok(self):
        f = self.pruefen()
        if f:
            self.fehler.setText(f)
            return
        self.ergebnis = self.werte()
        self.accept()

    def werte(self):
        """Ergebnis: dict(position = Felder der Baugruppen-Position, teile = {Positions-ID: dict(bg_knoten,
        je_knoten)} nur für geänderte Zuordnungen)."""
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
            if neu["bg_knoten"] != (q.get("bg_knoten") or None) or neu["je_knoten"] != q.get("je_knoten"):
                teile[t["_id"]] = neu
        return dict(position={k: p.get(k) for k in ("art", "stueck", "baugruppe", "bezeichnung", "artikel")},
                    teile=teile)
