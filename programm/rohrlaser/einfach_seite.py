"""Einfacher Modus: geführte Kalkulation in fünf Schritten (Patrick 25.11.2026, Master-Auftrag „Vereinfachten
Bedienmodus implementieren“; Einfacher Modus 2.0 vom 27.11.2026: „so einfach wie möglich, aber keinesfalls billig“).

Eine eigenständige Oberfläche neben dem Experten-Pro-Modus, aber KEIN zweites Kalkulationssystem: Jede Kalkulation
ist ein ganz normales Angebot. Die Seite arbeitet immer auf der Angebotsseite (angebot_fenster.AngebotSeite), die
auch der Pro-Modus zeigt (Hauptfenster.offen), und ruft deren vorhandene Funktionen auf: Kunde wählen, STEP-Import
mit Prüfdialog, CAD-Import, Bauteilbibliothek, Werkstoff setzen, Material und Materialkosten, Zusatzarbeiten,
Vorschläge, Optimieren, Fracht, Marge, Angebots-PDF. Zahlen kommen aus derselben Rechnung (AngebotSeite._rechnung =
rechnen.kalkulation), Marge und Ampel wie die Kachel „Gewinn und Marge“ (bedienmodus.ergebnis). Der Moduswechsel
tauscht nur die sichtbare Oberfläche: die Angebotsseiten, Eingaben und Rechnungen bleiben dieselben Objekte.

Aufbau (Designsystem „Klar“, design.py und bausteine.py): Kopf (Angebot und Kunde, Übersicht, Schrittleiste 1–5 mit
Stand je Schritt, Status-Chip, Hilfe, Pro-Modus) · Hilfe auf Abruf · Schrittseite und Zusammenfassung rechts (auf
schmalen Bildschirmen als Zeile unter dem Kopf) · Fuß (Zurück, nächster Schritt als Satz, Weiter). Umschalten:
Einstellungen → Darstellung und Bedienoberfläche, Menü Ansicht, Statusleiste oder Strg+Alt+M (einrichten,
umschalten).
"""
import tempfile
from pathlib import Path

from PySide6.QtCore import QStringListModel, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QBoxLayout, QCheckBox, QComboBox, QCompleter, QDoubleSpinBox,
                               QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QSizePolicy, QSpinBox, QSplitter, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from . import bausteine as bs
from . import bedienmodus as bm
from . import design, stil

PRUEF_TAKT_MS = 1200        # so oft schaut die sichtbare Seite nach, ob sich das Angebot geändert hat (billig)
TASTE = "Ctrl+Alt+M"        # Moduswechsel (Strg+Umschalt+M ist die Materialanfrage)
BREIT_AB = 1180             # ab dieser Breite steht die Zusammenfassung als Spalte rechts, darunter als Zeile oben
SCHMAL_AB = 1360            # darunter zeigt die Schrittleiste nur beim aktuellen Schritt den Namen
STUFE_CHIP = {"FEHLER": "fehler", "WARNUNG": "warnung", "HINWEIS": "info", "OK": "ok"}
AMPEL_CHIP = {"gut": "ok", "knapp": "warnung", "kritisch": "fehler"}
ZEICHEN = {"FEHLER": "✕", "WARNUNG": "!", "HINWEIS": "i", "OK": "✓"}
GRAU = design.TEXT_GRAU

# Nur Werte aus design.py (Designsystem „Klar“); Farben aus der Hell-Palette, stil.umsetzen setzt sie für Dunkel und
# Hohen Kontrast um. Karten, Kennzahlleiste, Chips, Hinweisbänder und Knöpfe kommen aus dem gemeinsamen Stylesheet.
STIL = f"""
QWidget#einfach {{ background: {design.ARBEITSFLAECHE}; }}
QFrame#e_kopf {{ background: {design.KARTE}; border: none; border-bottom: 1px solid {design.KARTE_RAHMEN}; }}
QFrame#e_fuss {{ background: {design.KARTE}; border: none; border-top: 1px solid {design.KARTE_RAHMEN}; }}
QFrame#e_streifen {{ background: {design.KARTE}; border: none; border-bottom: 1px solid {design.KARTE_RAHMEN}; }}
QLabel#e_titel {{ font-size: {design.UI_ABSCHNITT}px; font-weight: 600; color: {design.TEXT}; }}
QLabel#e_unter {{ color: {design.TEXT_GRAU}; }}
QLabel#e_klein {{ color: {design.TEXT_GRAU}; font-size: {design.UI_KLEIN}px; }}
QLabel#e_feld {{ color: {design.TEXT_GRAU}; font-size: {design.UI_KLEIN}px; font-weight: 500; }}
QLabel#e_summe {{ font-size: {design.UI_KENNZAHL}px; font-weight: 600; color: {design.AKZENT}; }}
QLabel#e_wert {{ color: {design.TEXT}; }}
QPushButton#e_schritt {{ border: 1px solid transparent; border-radius: {design.ECKE}px; padding: 4px 10px;
    color: {design.TEXT_GRAU}; background: transparent; font-weight: 500; }}
QPushButton#e_schritt:hover {{ background: {design.NEUTRAL_FLAECHE}; }}
QPushButton#e_schritt[zustand="ok"] {{ color: {design.GRUEN}; }}
QPushButton#e_schritt[zustand="fehlt"] {{ color: {design.GELB_TEXT}; }}
QPushButton#e_schritt:checked {{ background: {design.AKZENT_FLAECHE}; color: {design.AKZENT}; font-weight: 600; }}
QPushButton#e_schritt:disabled {{ color: #9AA3AF; }}
QPushButton#e_link {{ border: none; background: transparent; color: {design.AKZENT}; text-align: left;
    padding: 1px 0px; }}
QPushButton#e_link:hover {{ text-decoration: underline; }}
QToolButton#e_auf {{ border: none; background: transparent; color: {design.AKZENT}; font-weight: 600;
    padding: 2px 0px; }}
QFrame#e_zusammen {{ background: {design.KARTE}; border: 1px solid {design.KARTE_RAHMEN};
    border-radius: {design.ECKE_KARTE}px; }}
QFrame#e_zusammen QLabel {{ border: none; }}
QFrame#e_trenn {{ background: {design.KARTE_RAHMEN}; border: none; max-height: 1px; min-height: 1px; }}
QFrame#e_hilfe {{ background: {design.AKZENT_FLAECHE}; border: none; border-bottom: 1px solid #C9DAEE; }}
QFrame#e_hilfe QLabel {{ background: transparent; }}
QLabel#e_vorschau {{ background: {design.KARTE}; border: 1px solid {design.EINGABE_RAHMEN}; }}
QTableWidget#e_tabelle {{ background: {design.KARTE}; border: none; gridline-color: {design.LINIE}; }}
QTableWidget#e_tabelle::item {{ padding: 2px 6px; }}
"""


# ------------------------------------------------------------------ Bausteine (nur Zusammenbau aus bausteine.py)
def _label(text="", name=None, umbruch=True):
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(umbruch)
    lb.setTextFormat(Qt.RichText)
    return lb


def _farbe(hell):
    return stil.umsetzen(hell)


def _knopf(text, aufruf, tipp="", haupt=False):
    b = bs.knopf(text, haupt=haupt, klick=aufruf)
    b.setToolTip(tipp)
    return b


def _link(text, aufruf, tipp=""):
    b = QPushButton(text)
    b.setObjectName("e_link")
    b.setCursor(Qt.PointingHandCursor)
    b.setToolTip(tipp)
    b.clicked.connect(aufruf)
    return b


def _trenner():
    t = QFrame()
    t.setObjectName("e_trenn")
    return t


def _feld(titel, widget, pflicht=False, tipp=""):
    """Eingabefeld mit Bezeichnung darüber; Pflichtfelder mit rotem * (Status nie nur über die Farbe)."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(3)
    lb = _label(titel + (f" <span style='color:{_farbe(design.ROT)}'>*</span>" if pflicht else ""), "e_feld",
                umbruch=False)
    if tipp:
        lb.setToolTip(tipp)
        widget.setToolTip(tipp)
    v.addWidget(lb)
    v.addWidget(widget)
    w.feld, w.bezeichnung = widget, lb
    return w


def _scroll(inhalt):
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QFrame.NoFrame)
    s.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    s.setWidget(inhalt)
    inhalt.setObjectName("einfach")
    return s


def _seite(titel, untertitel="", aktionen=()):
    """Schrittseite: Seitenkopf (bausteine.seitenkopf) und darunter der Inhalt. Ergebnis: (Rollbereich, Layout,
    Seitenkopf)."""
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(design.ABSTAND_GROSS + 4, design.ABSTAND_GROSS, design.ABSTAND_GROSS + 4,
                         design.ABSTAND_GROSS)
    v.setSpacing(design.ABSTAND + 2)
    kopf = bs.seitenkopf(titel, untertitel, aktionen)
    v.addWidget(kopf)
    return _scroll(w), v, kopf


def _zelle(text, rechts=False, tipp=""):
    it = QTableWidgetItem(str(text))
    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    if rechts:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if tipp:
        it.setToolTip(tipp)
    return it


def _tabelle(spalten, dehnen=1, rechts=()):
    """Tabelle ohne waagerechten Rollbalken: die Spalte dehnen füllt die Breite, die übrigen nach Inhalt."""
    t = QTableWidget(0, len(spalten))
    t.setObjectName("e_tabelle")
    t.setHorizontalHeaderLabels(spalten)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(34)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setWordWrap(False)
    t.setShowGrid(False)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    kopf = t.horizontalHeader()
    kopf.setStretchLastSection(False)
    kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
    kopf.setSectionResizeMode(dehnen, QHeaderView.Stretch)
    kopf.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    for c in rechts:
        t.horizontalHeaderItem(c).setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return t


def _leeren(lay):
    """Alle Widgets aus einem Layout nehmen und entfernen (sofort unsichtbar, gelöscht beim nächsten Durchlauf)."""
    while lay.count():
        w = lay.takeAt(0).widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()


def _hoehe_anpassen(t, min_zeilen=3, max_zeilen=14):
    """Tabelle so hoch wie ihre Zeilen (die Seite rollt, nicht die Tabelle), höchstens max_zeilen."""
    n = max(min_zeilen, min(max_zeilen, t.rowCount()))
    t.setFixedHeight(t.horizontalHeader().height() + n * t.verticalHeader().defaultSectionSize() + 4)


class Aufklapper(QWidget):
    """Bereich, der erst bei Bedarf aufgeht (Details, Kostenarten, Weitere Kosten): Knopf „Titel ▸/▾“ und Inhalt."""
    umgeschaltet = Signal(bool)

    def __init__(self, titel, offen=False):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(design.ABSTAND_KLEIN)
        self.titel = titel
        self.knopf = QToolButton()
        self.knopf.setObjectName("e_auf")
        self.knopf.setCheckable(True)
        self.knopf.setCursor(Qt.PointingHandCursor)
        self.knopf.toggled.connect(self.zeigen)
        self.inhalt = QWidget()
        self.lay = QVBoxLayout(self.inhalt)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(design.ABSTAND_KLEIN)
        v.addWidget(self.knopf, 0, Qt.AlignLeft)
        v.addWidget(self.inhalt)
        self.zeigen(offen)

    def zeigen(self, an):
        an = bool(an)
        if self.knopf.isChecked() != an:
            self.knopf.blockSignals(True)
            self.knopf.setChecked(an)
            self.knopf.blockSignals(False)
        self.knopf.setText(f"{self.titel} {'▾' if an else '▸'}")
        self.inhalt.setVisible(an)
        self.umgeschaltet.emit(an)

    def offen(self):
        return self.knopf.isChecked()


class HinweisListe(QWidget):
    """Hinweise mit Lösung: je Hinweis ein Hinweisband (bausteine.hinweisband) mit verständlichem Text und einem
    Knopf, der die Lösung öffnet."""
    loesen = Signal(str, object)        # Aktion, Zeile

    TEXT = {"stueck": "Stück eintragen", "material": "Zum Material", "editor": "Im Editor prüfen",
            "zukauf": "Preis eintragen", "optimieren": "Neu berechnen", "experte": "Im Pro-Modus öffnen",
            "kunde": "Kunde wählen", "import": "Bauteil importieren"}

    def __init__(self, ok_text=""):
        super().__init__()
        self.ok_text = ok_text
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(design.ABSTAND_KLEIN)
        self.zeilen = []

    def setzen(self, hinweise, max_anzahl=6):
        _leeren(self.lay)
        self.zeilen = list(hinweise)
        if not hinweise:
            if self.ok_text:
                self.lay.addWidget(bs.hinweisband(self.ok_text, "ok"))
            self.setVisible(bool(self.ok_text))
            return
        self.setVisible(True)
        for st, text, aktion, zeile in hinweise[:max_anzahl]:
            self.lay.addWidget(bs.hinweisband(text, STUFE_CHIP.get(st, "info"), self.TEXT.get(aktion, ""),
                                              lambda _=False, a=aktion, r=zeile: self.loesen.emit(a, r)))
        if len(hinweise) > max_anzahl:
            self.lay.addWidget(_label(f"… und {len(hinweise) - max_anzahl} weitere.", "e_klein"))


class Zusammenfassung(QFrame):
    """Rechte Spalte ab Schritt 1: Angebotssumme, Kennwerte, Marge mit Ampel und offene Punkte als Links (ersetzt
    die frühere Hilfespalte; die Hilfe gibt es über „?“). zeile=True: dieselben Angaben als eine Zeile für schmale
    Bildschirme."""
    loesen = Signal(str, object)

    def __init__(self):
        super().__init__()
        self.setObjectName("e_zusammen")
        self.setFixedWidth(264)
        v = QVBoxLayout(self)
        v.setContentsMargins(design.ABSTAND + 4, design.ABSTAND + 2, design.ABSTAND + 4, design.ABSTAND + 2)
        v.setSpacing(design.ABSTAND_KLEIN + 2)
        v.addWidget(_label("Angebotssumme netto", "e_klein"))
        self.summe = _label("–", "e_summe", umbruch=False)
        v.addWidget(self.summe)
        self.summe_unter = _label("", "e_klein")
        v.addWidget(self.summe_unter)
        v.addWidget(_trenner())
        self.werte = bs.wertzeilen([("Angebotsnummer", "–"), ("Datum", "–"), ("Bauteile", "–"), ("Stück gesamt", "–"),
                                    ("Maschinenzeit", "–")])
        v.addWidget(self.werte)
        v.addWidget(_trenner())
        g = QGridLayout()
        g.setContentsMargins(0, 0, 0, 0)
        g.setVerticalSpacing(design.ABSTAND_KLEIN)
        g.addWidget(_label("Marge", "nebentext", umbruch=False), 0, 0)
        self.marge = bs.chip("–")
        g.addWidget(self.marge, 0, 1, Qt.AlignRight)
        g.addWidget(_label("Offene Punkte", "nebentext", umbruch=False), 1, 0)
        self.offen = bs.chip("–")
        g.addWidget(self.offen, 1, 1, Qt.AlignRight)
        v.addLayout(g)
        self.links = QVBoxLayout()
        self.links.setSpacing(2)
        v.addLayout(self.links)
        v.addStretch(1)

    def setzen(self, s, d, bereit):
        k = (s.kopf or {}) if s is not None else {}
        e = (d or {}).get("ergebnis") or {}
        bt = (d or {}).get("bauteile") or []
        gerechnet = bool(bereit and bereit["gerechnet"])
        self.summe.setText(bm.euro(e.get("verkauf")) if gerechnet and bt else "–")
        self.summe_unter.setText("" if gerechnet or not bt else "wird beim nächsten Schritt berechnet")
        self.summe_unter.setVisible(bool(self.summe_unter.text()))
        stueck = sum(int(b["stueck"] or 0) for b in bt)
        werte = {"Angebotsnummer": k.get("nummer") or (str(s.id) if s is not None else "–"),
                 "Datum": _datum(k.get("datum")), "Bauteile": str(len(bt)) if s is not None else "–",
                 "Stück gesamt": bm.zahl(stueck, 0) if bt else "–",
                 "Maschinenzeit": bm.minuten_text(e.get("maschine_min")) if gerechnet and bt else "–"}
        for t, w in werte.items():
            self.werte.werte[t].setText(w)
        if gerechnet and e.get("marge") is not None:
            bs.chip_setzen(self.marge, f"{bm.zahl(100 * e['marge'], 1)} %", AMPEL_CHIP.get(e.get("stufe"), "neutral"))
            self.marge.setToolTip(e.get("ampel_text") or "")
        else:
            bs.chip_setzen(self.marge, "–", "neutral")
        offen = (bereit or {}).get("offen") or []
        bs.chip_setzen(self.offen, "keine" if not offen else str(len(offen)), "ok" if not offen else "warnung")
        _leeren(self.links)
        for st, text, aktion, zeile in offen[:4]:
            kurz = text.split(":", 1)[0] if aktion in ("stueck", "editor", "zukauf") and ":" in text else \
                text.split(".", 1)[0]
            b = _link(f"{ZEICHEN[st]}  {kurz[:42]}{'…' if len(kurz) > 42 else ''}",
                      lambda _=False, a=aktion, r=zeile: self.loesen.emit(a, r), text)
            self.links.addWidget(b)
        if len(offen) > 4:
            self.links.addWidget(_label(f"… und {len(offen) - 4} weitere", "e_klein"))

    def zeilentext(self, s, d, bereit):
        """Dieselben Angaben als ein Satz (schmale Bildschirme)."""
        e = (d or {}).get("ergebnis") or {}
        bt = (d or {}).get("bauteile") or []
        teile = []
        if bereit and bereit["gerechnet"] and bt:
            teile.append(f"<b>{bm.euro(e.get('verkauf'))}</b> netto")
            if e.get("marge") is not None:
                teile.append(f"Marge {bm.zahl(100 * e['marge'], 1)} %")
        teile.append(f"{len(bt)} Bauteil(e)")
        offen = (bereit or {}).get("offen") or []
        teile.append("keine offenen Punkte" if not offen else f"{len(offen)} offene(r) Punkt(e)")
        return " · ".join(teile)


def _datum(iso):
    t = str(iso or "")[:10]
    if len(t) == 10 and t[4] == "-":
        return f"{t[8:10]}.{t[5:7]}.{t[:4]}"
    return t or "–"


# ------------------------------------------------------------------ Seite
class EinfachBereich(QWidget):
    """Die Oberfläche des einfachen Modus (eine Seite im Hauptfenster). seite = die bearbeitete AngebotSeite."""

    def __init__(self, fenster):
        super().__init__()
        self.f = fenster
        self.db = fenster.db
        self.seite = None
        self.schritt = bm.START
        self.daten = None
        self.bereit = None
        self._marke = None
        self._gefuellt = set()
        self._breit = None
        self.setObjectName("einfach")
        self.setStyleSheet(STIL)
        self.setAcceptDrops(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._kopf_bauen())
        lay.addWidget(self._hilfe_bauen())
        self.streifen = QFrame()
        self.streifen.setObjectName("e_streifen")
        sh = QHBoxLayout(self.streifen)
        sh.setContentsMargins(design.ABSTAND_GROSS + 4, design.ABSTAND_KLEIN, design.ABSTAND_GROSS + 4,
                              design.ABSTAND_KLEIN)
        self.streifen_text = _label("", "e_unter", umbruch=False)
        sh.addWidget(self.streifen_text, 1)
        lay.addWidget(self.streifen)
        mitte = QHBoxLayout()
        mitte.setContentsMargins(0, 0, 0, 0)
        mitte.setSpacing(0)
        self.stapel = QStackedWidget()
        self.seiten = [self._start_bauen(), self._kunde_bauen(), self._bauteile_bauen(), self._material_bauen(),
                       self._kalkulation_bauen(), self._angebot_bauen()]
        for s in self.seiten:
            self.stapel.addWidget(s)
        mitte.addWidget(self.stapel, 1)
        self.zus = Zusammenfassung()
        self.zus.loesen.connect(self.loesen)
        self._zus_aussen = QWidget()
        za = QVBoxLayout(self._zus_aussen)
        za.setContentsMargins(0, design.ABSTAND_GROSS, design.ABSTAND_GROSS, design.ABSTAND_GROSS)
        za.addWidget(self.zus)
        mitte.addWidget(self._zus_aussen)
        lay.addLayout(mitte, 1)
        lay.addWidget(self._fuss_bauen())
        self.uhr = QTimer(self)
        self.uhr.setInterval(PRUEF_TAKT_MS)
        self.uhr.timeout.connect(self._pruefen)
        self.hilfe_zeigen(bm.hilfe_an(self.db))
        self.zu_schritt(bm.START)

    # -------------------------------------------------------------- Kopf, Hilfe, Fuß
    def _kopf_bauen(self):
        kopf = QFrame()
        kopf.setObjectName("e_kopf")
        h = QHBoxLayout(kopf)
        h.setContentsMargins(design.ABSTAND_GROSS + 4, design.ABSTAND_KLEIN + 2, design.ABSTAND + 2,
                             design.ABSTAND_KLEIN + 2)
        h.setSpacing(design.ABSTAND_KLEIN)
        links = QVBoxLayout()
        links.setSpacing(0)
        self.titel = _label("Kalkulation", "e_titel", umbruch=False)
        self.untertitel = _label("Einfacher Modus", "e_klein", umbruch=False)
        links.addWidget(self.titel)
        links.addWidget(self.untertitel)
        kopf_links = QWidget()
        kopf_links.setLayout(links)
        kopf_links.setMinimumWidth(160)
        kopf_links.setMaximumWidth(420)
        h.addWidget(kopf_links)
        h.addStretch(1)
        self.uebersicht_knopf = QPushButton("Übersicht")
        self.uebersicht_knopf.setObjectName("e_schritt")
        self.uebersicht_knopf.setCheckable(True)
        self.uebersicht_knopf.setToolTip("Zuletzt bearbeitete Kalkulationen, neue Kalkulation anlegen")
        self.uebersicht_knopf.clicked.connect(lambda: self.zu_schritt(bm.START))
        h.addWidget(self.uebersicht_knopf)
        h.addSpacing(design.ABSTAND)
        self.schritt_knoepfe = []
        for n, (_, titel, kurz, _) in enumerate(bm.SCHRITTE[1:]):
            b = QPushButton(f"{n + 1}  {titel}")
            b.setObjectName("e_schritt")
            b.setCheckable(True)
            b.setToolTip(f"Schritt {n + 1}: {kurz}")
            b.clicked.connect(lambda _=False, i=n + 1: self.zu_schritt(i))
            self.schritt_knoepfe.append(b)
            h.addWidget(b)
            if n < len(bm.SCHRITTE) - 2:
                strich = QFrame()
                strich.setObjectName("e_trenn")
                strich.setFixedWidth(10)
                h.addWidget(strich, 0, Qt.AlignVCenter)
        h.addStretch(1)
        self.status_chip = bs.chip("", "neutral")
        self.status_chip.setToolTip("Stand der Kalkulation: bereit zur Ausgabe oder was noch fehlt")
        h.addWidget(self.status_chip)
        h.addSpacing(design.ABSTAND_KLEIN)
        self.hilfe_knopf = QPushButton("?")
        self.hilfe_knopf.setCheckable(True)
        self.hilfe_knopf.setFixedWidth(30)
        self.hilfe_knopf.setToolTip("Erklärung zum aktuellen Schritt ein- oder ausblenden")
        self.hilfe_knopf.toggled.connect(lambda an: self.hilfe_zeigen(an, merken=True))
        h.addWidget(self.hilfe_knopf)
        self.experte_knopf = QPushButton("Pro-Modus")
        self.experte_knopf.setToolTip("Zur vollständigen Arbeitsumgebung wechseln (dieselbe Kalkulation, "
                                      f"{TASTE.replace('Ctrl', 'Strg')})")
        self.experte_knopf.clicked.connect(lambda: umschalten(self.f, bm.EXPERTE))
        h.addWidget(self.experte_knopf)
        return kopf

    def _hilfe_bauen(self):
        self.hilfe = QFrame()
        self.hilfe.setObjectName("e_hilfe")
        h = QHBoxLayout(self.hilfe)
        h.setContentsMargins(design.ABSTAND_GROSS + 4, design.ABSTAND, design.ABSTAND_GROSS + 4, design.ABSTAND)
        h.setSpacing(design.ABSTAND_GROSS)
        v = QVBoxLayout()
        v.setSpacing(design.ABSTAND_KLEIN)
        self.hilfe_titel = _label("", "abschnitt")
        self.hilfe_text = _label("")
        v.addWidget(self.hilfe_titel)
        v.addWidget(self.hilfe_text)
        h.addLayout(v, 3)
        self.hilfe_felder = _label("", "e_klein")
        h.addWidget(self.hilfe_felder, 2)
        rechts = QVBoxLayout()
        anleitung = QPushButton("Bedienungsanleitung öffnen")
        anleitung.setToolTip("Kapitel „Einfacher Modus“ der Bedienungsanleitung (PDF)")
        anleitung.clicked.connect(lambda: self.f.anleitung_oeffnen() if hasattr(self.f, "anleitung_oeffnen") else None)
        rechts.addWidget(anleitung)
        rechts.addStretch(1)
        h.addLayout(rechts)
        return self.hilfe

    def hilfe_zeigen(self, an, merken=False):
        self.hilfe.setVisible(bool(an))
        if self.hilfe_knopf.isChecked() != bool(an):
            self.hilfe_knopf.blockSignals(True)
            self.hilfe_knopf.setChecked(bool(an))
            self.hilfe_knopf.blockSignals(False)
        if merken:
            bm.hilfe_setzen(self.db, an)

    FELDER_JE_SCHRITT = {bm.KUNDE: ("kunde", "projekt", "lieferzeit"), bm.BAUTEILE: ("stueck", "profil", "laenge"),
                         bm.MATERIAL: ("werkstoff", "preis_m", "verfuegbar", "maschine", "zusatz", "fracht"),
                         bm.KALKULATION: ("verkauf", "gesamt", "gewinn", "marge")}
    FELD_TITEL = {"stueck": "Stück", "profil": "Querschnitt", "laenge": "Länge", "werkstoff": "Werkstoff",
                  "preis_m": "Preis je Meter", "verfuegbar": "Verfügbarkeit", "maschinenzeit": "Maschinenzeit",
                  "schnitt": "Schnittkosten", "ruesten": "Rüstkosten", "zusatz": "Zusatzarbeiten",
                  "zukauf": "Zukaufteile", "gemein": "Gemeinkosten", "gesamt": "Selbstkosten",
                  "verkauf": "Verkaufspreis", "gewinn": "Gewinn und Marge", "fracht": "Frachtkosten",
                  "marge": "Marge einstellen", "kunde": "Kunde", "projekt": "Projekt", "lieferzeit": "Lieferzeit",
                  "maschine": "Maschine"}

    def _hilfe_setzen(self):
        _, titel, kurz, lang = bm.SCHRITTE[self.schritt]
        self.hilfe_titel.setText(titel if self.schritt == bm.START else f"Schritt {self.schritt}: {titel}")
        self.hilfe_text.setText(lang)
        felder = self.FELDER_JE_SCHRITT.get(self.schritt, ())
        self.hilfe_felder.setText("".join(f"<p style='margin:0 0 4px 0'><b>{self.FELD_TITEL[n]}</b>: "
                                          f"{bm.FELD_HILFE[n]}</p>" for n in felder))

    def _fuss_bauen(self):
        fuss = QFrame()
        fuss.setObjectName("e_fuss")
        h = QHBoxLayout(fuss)
        h.setContentsMargins(design.ABSTAND_GROSS + 4, design.ABSTAND_KLEIN + 2, design.ABSTAND_GROSS + 4,
                             design.ABSTAND_KLEIN + 2)
        h.setSpacing(design.ABSTAND)
        self.zurueck = _knopf("‹ Zurück", lambda: self.zu_schritt(self.schritt - 1), "Vorheriger Schritt")
        self.weiter = _knopf("Weiter ›", lambda: self.zu_schritt(self.schritt + 1), "Nächster Schritt", haupt=True)
        self.fuehrung = _label("", "e_unter")
        h.addWidget(self.zurueck)
        h.addWidget(self.fuehrung, 1)
        h.addWidget(self.weiter)
        return fuss

    # -------------------------------------------------------------- Ablauf
    def zu_schritt(self, i):
        i = max(bm.START, min(bm.ANGEBOT, i))
        if i > bm.START and self._seite_weg():
            i = bm.START
        self.schritt = i
        self.uebersicht_knopf.setChecked(i == bm.START)
        for n, b in enumerate(self.schritt_knoepfe):
            b.setChecked(n + 1 == i)
            b.setEnabled(self.seite is not None)
        self.stapel.setCurrentIndex(i)
        if i in (bm.MATERIAL, bm.KALKULATION, bm.ANGEBOT):
            self.automatisch_rechnen()
        self.aktualisieren(nur_seite=True)
        self._hilfe_setzen()
        self._breite_anwenden(force=True)
        if i == bm.ANGEBOT:
            QTimer.singleShot(0, self._vorschau_spaeter)
        return i

    @staticmethod
    def _schritt_kennzeichnen(b, n, erledigt, fehlt=False, kurz=False):
        """Stand eines Schrittknopfs (n = 0 … 4): ✓ erledigt (grün), ! es fehlt etwas (gelb), sonst die Nummer;
        kurz = nur Zeichen bzw. Nummer (schmale Bildschirme, außer beim aktuellen Schritt)."""
        titel = bm.SCHRITTE[n + 1][1]
        zeichen = "!" if fehlt else ("✓" if erledigt else str(n + 1))
        b.setText(zeichen if kurz else f"{zeichen}  {titel}")
        zustand = "fehlt" if fehlt else ("ok" if erledigt else "offen")
        if b.property("zustand") != zustand or b.property("erledigt") != bool(erledigt and not fehlt):
            b.setProperty("zustand", zustand)
            b.setProperty("erledigt", bool(erledigt and not fehlt))
            b.style().unpolish(b)
            b.style().polish(b)

    def _seite_weg(self):
        """Die bearbeitete Angebotsseite wurde (im Pro-Modus) geschlossen: zurück zur Übersicht."""
        if self.seite is not None and self.seite not in getattr(self.f, "offen", {}).values():
            self.seite = None
        return self.seite is None

    def seite_setzen(self, seite, schritt=bm.BAUTEILE):
        """Diese AngebotSeite im einfachen Modus bearbeiten (gleiche Seite wie im Pro-Modus)."""
        self.seite = seite
        self._marke = None
        self._vorschau_marke = None
        self.zu_schritt(schritt if seite is not None else bm.START)
        return seite

    def automatisch_rechnen(self):
        """Ist der Schnittplan nicht aktuell, rechnet das Programm ihn selbst (wie Optimieren, ohne Rückfragen)."""
        s = self.seite
        if s is None or not s.positionen or s.fremd() or self.db.nur_lesen:
            return False
        if s.stand_optimierung() == "aktuell":
            return False
        try:
            return bool(s.optimieren(automatisch=True))
        except Exception:           # noqa: BLE001 – die Hinweise nennen den Grund, der Ablauf geht weiter
            from . import protokoll
            protokoll.warnung("Einfacher Modus: automatisches Optimieren fehlgeschlagen")
            return False

    def _kennung(self):
        s = self.seite
        if s is None:
            return None
        return (id(s), id(getattr(s, "positionen", None)), id(getattr(s, "ergebnis", None)), id(getattr(s, "kopf", None)))

    def _pruefen(self):
        if self.isVisible() and self._kennung() != self._marke:
            self.aktualisieren()

    def showEvent(self, e):
        super().showEvent(e)
        self.uhr.start()
        self._pruefen()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.uhr.stop()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._breite_anwenden()

    def _breite_anwenden(self, force=False):
        """Zusammenfassung als Spalte (breit) oder als Zeile unter dem Kopf (schmal); Schrittleiste kurz unter
        SCHMAL_AB. Nie ein waagerechter Rollbalken."""
        b = self.width()
        breit = b >= BREIT_AB
        mit_zus = self.seite is not None and self.schritt not in (bm.START, bm.ANGEBOT)
        self._zus_aussen.setVisible(breit and mit_zus)
        self.streifen.setVisible(not breit and mit_zus)
        kurz = b < SCHMAL_AB
        je = (self.bereit or {}).get("je_schritt") or {}
        for n, k in enumerate(self.schritt_knoepfe):
            st = je.get(n + 1, "offen") if self.seite is not None else "offen"
            self._schritt_kennzeichnen(k, n, erledigt=st == "ok", fehlt=st == "fehlt",
                                       kurz=kurz and n + 1 != self.schritt)
        if hasattr(self, "ang_box"):
            self.ang_box.setDirection(QBoxLayout.LeftToRight if b >= BREIT_AB else QBoxLayout.TopToBottom)
        self._breit = breit

    # -------------------------------------------------------------- Daten
    def daten_lesen(self):
        """Alles, was die Schritte zeigen, aus der Angebotsseite (eine Kalkulation je Änderung)."""
        s = self.seite
        if s is None:
            return None
        bauteile = [bm.bauteil(p, s.position_art(p), s.k, w, st)
                    for p, w, st in zip(s.positionen, s.pos_modell.werte, s.pos_modell.status)]
        zeilen, summen = s._rechnung()
        from . import rechnen
        zs = rechnen.zeit_summen(summen["zeiten"], summen.get("teile")) if summen.get("zeiten") is not None else {}
        try:
            unsicher = s.unsicher_anteil()
        except Exception:           # noqa: BLE001
            unsicher = None
        erg = bm.ergebnis(summen, s.einst, zs, unsicher)
        fehler_einplanen = len((s.ergebnis or {}).get("fehler") or ())
        stand = s.stand_optimierung()
        hinw = bm.hinweise(bauteile, s.kopf, stand, erg, fehler_einplanen)
        # übrige offene Punkte des Angebots-Checks (wie vor dem PDF im Pro-Modus), z. B. veraltete Staffeln; solange
        # eigene Hinweise offen sind, nennen die Check-Punkte meist dasselbe noch einmal
        if not any(h[0] in ("FEHLER", "WARNUNG") for h in hinw):
            hinw += [(st, text, "experte", None) for st, text in self._punkte() if st in ("FEHLER", "WARNUNG")]
        kosten = list(zip(rechnen.kostenarten(summen, s.einst), rechnen.KOSTENARTEN))
        return dict(bauteile=bauteile, zeilen=zeilen, summen=summen, ergebnis=erg, hinweise=hinw, kosten=kosten,
                    zeiten=zs, stand=stand)

    def aktualisieren(self, nur_seite=False):
        neu = self._kennung()
        if neu != self._marke or self.daten is None and self.seite is not None:
            self._marke = neu
            self._gefuellt = set()
            try:
                self.daten = self.daten_lesen()
            except Exception:       # noqa: BLE001 – Anzeige; der Pro-Modus zeigt denselben Stand
                from . import protokoll
                protokoll.warnung("Einfacher Modus: Daten des Angebots nicht lesbar")
                self.daten = None
            d, s = self.daten, self.seite
            self.bereit = bm.bereitschaft(d["hinweise"], s.kopf, d["bauteile"], d["stand"], d["ergebnis"]) \
                if d and s is not None else None
        if self.schritt not in self._gefuellt:
            self._gefuellt.add(self.schritt)
            (self._start_fuellen, self._kunde_fuellen, self._bauteile_fuellen, self._material_fuellen,
             self._kalkulation_fuellen, self._angebot_fuellen)[self.schritt]()
        self._kopf_fuellen()

    def _kopf_fuellen(self):
        s = self.seite
        d = self.daten if s is not None else None
        if s is None:
            self.titel.setText("Kalkulation")
            self.untertitel.setText("Einfacher Modus · keine Kalkulation geöffnet")
            self.status_chip.setVisible(False)
        else:
            k = s.kopf or {}
            self.titel.setText(" · ".join(x for x in (f"Angebot {k.get('nummer') or s.id}",
                                                      k.get("kunde") or "ohne Kunde") if x))
            bt = d["bauteile"] if d else []
            stueck = sum(int(b["stueck"] or 0) for b in bt)
            self.untertitel.setText(" · ".join(x for x in (
                f"Projekt {k.get('projekt')}" if k.get("projekt") else "",
                f"{len(bt)} Bauteil(e)", f"{bm.zahl(stueck, 0)} Stück" if stueck else "") if x))
            b = self.bereit or {"text": "", "stufe": "neutral"}
            bs.chip_setzen(self.status_chip, b["text"], b["stufe"])
            self.status_chip.setVisible(bool(b["text"]))
        hinw = d["hinweise"] if d else []
        hat_kunde = bool(s is not None and ((s.kopf or {}).get("kundennr") or (s.kopf or {}).get("kunde")))
        self.fuehrung.setText(bm.naechster_schritt(self.schritt, hinw, s is not None, hat_kunde))
        self.zurueck.setEnabled(self.schritt > bm.START)
        self.zurueck.setVisible(self.schritt > bm.START)
        self.weiter.setVisible(bm.START < self.schritt < bm.ANGEBOT)
        self.weiter.setEnabled(s is not None)
        if bm.START < self.schritt < bm.ANGEBOT:
            self.weiter.setText(f"Weiter zu {bm.SCHRITTE[self.schritt + 1][1]} ›")
        self.zus.setzen(s, d, self.bereit)
        self.streifen_text.setText(self.zus.zeilentext(s, d, self.bereit) if s is not None else "")
        self._breite_anwenden(force=True)

    # -------------------------------------------------------------- Dateien ins Fenster ziehen
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        dateien = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if dateien:
            e.acceptProposedAction()
            QTimer.singleShot(0, lambda: self.dateien_oeffnen(dateien))

    def dateien_oeffnen(self, dateien):
        """Hineingezogene Dateien: in der Übersicht eine neue Kalkulation (STEP mit dem STEP-Import, sonst wie
        CAD-Import), in einer offenen Kalkulation als weitere Bauteile."""
        if self.seite is None or self.schritt == bm.START:
            if all(Path(d).suffix.lower() in (".step", ".stp") for d in dateien):
                return self.neu_aus_step(dateien)
            return self.neu_aus_cad(dateien)
        erg = self.importieren(dateien)
        self.zu_schritt(bm.BAUTEILE)
        return erg

    # -------------------------------------------------------------- Übersicht (Start)
    def _start_bauen(self):
        self.neu_knopf = _knopf("＋  Neue Kalkulation", self.neu_anlegen,
                                "Neues Angebot anlegen und mit dem Kunden beginnen", haupt=True)
        aktionen = [_knopf("STEP importieren …", lambda: self.neu_aus_step(),
                           "3D-Modell (STEP, IGES, ZIP) lesen und automatisch erkennen: neue Kalkulation"),
                    _knopf("Andere CAD-Datei …", lambda: self.neu_aus_cad(),
                           "DXF, TRUMPF LST, BLM ArTube/BPF: neue Kalkulation"),
                    _knopf("Aus Bauteilbibliothek …", lambda: self.neu_aus_vorlage(),
                           "Gespeichertes Bauteil (Positionsvorlage) in eine neue Kalkulation"),
                    self.neu_knopf]
        rolle, v, kopf = _seite("Kalkulationen", "Neue Kalkulation anlegen, eine Datei ins Fenster ziehen oder eine "
                                                 "bestehende Kalkulation öffnen.", aktionen)
        self.start_kopf = kopf
        self.willkommen = bs.hinweisband(
            "<b>Willkommen im Einfachen Modus.</b> In fünf Schritten zum Angebot: Anfrage und Kunde, Bauteile, "
            "Material und Fertigung, Kalkulation, Angebot. Oben sehen Sie jederzeit, wo Sie sind und was noch fehlt; "
            "„?“ erklärt jeden Schritt. Alles bleibt im Pro-Modus vollständig bearbeitbar.", "info", "Ausblenden",
            self._willkommen_aus)
        v.addWidget(self.willkommen)
        self.willkommen.setVisible(bm.willkommen_an(self.db))
        self.weiter_karte = bs.karte("Aktuelle Kalkulation")
        zeile = QHBoxLayout()
        self.weiter_text = _label("")
        zeile.addWidget(self.weiter_text, 1)
        zeile.addWidget(_knopf("Weiterbearbeiten ›", lambda: self.zu_schritt(self._erster_offener()),
                               "Beim ersten Schritt weitermachen, in dem noch etwas fehlt"))
        self.weiter_karte.inhalt.addLayout(zeile)
        v.addWidget(self.weiter_karte)
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Suchen: Angebotsnummer, Kunde, Zeichen, Artikel …")
        self.suche.setClearButtonEnabled(True)
        self.suche.setMaximumWidth(380)
        self.suche.textChanged.connect(lambda _: self._liste_fuellen())
        self.suche.returnPressed.connect(self._liste_oeffnen)
        liste = bs.karte("Zuletzt bearbeitet", rechts=[self.suche])
        self.liste = _tabelle(["Angebot", "Kunde", "Ihre Anfrage", "Stand", "Summe netto", "Geändert"], dehnen=1,
                              rechts=(4,))
        self.liste.setToolTip("Doppelklick oder Enter öffnet die Kalkulation")
        self.liste.doubleClicked.connect(lambda i: self._liste_oeffnen())
        self.liste.setMinimumHeight(260)
        liste.inhalt.addWidget(self.liste, 1)
        liste.inhalt.addWidget(bs.knopfzeile(_knopf("Öffnen", self._liste_oeffnen, "Gewählte Kalkulation öffnen")))
        v.addWidget(liste, 1)
        return rolle

    def _willkommen_aus(self):
        bm.willkommen_aus(self.db)
        self.willkommen.hide()

    def _erster_offener(self):
        je = (self.bereit or {}).get("je_schritt") or {}
        return next((n for n in range(bm.KUNDE, bm.ANGEBOT) if je.get(n) != "ok"), bm.ANGEBOT)

    def neu_zeigen(self):
        """Früherer Knopf „Neue Kalkulation erstellen“: zeigt jetzt die Wege im Seitenkopf (immer sichtbar)."""
        self.zu_schritt(bm.START)
        return True

    def neu_anlegen(self):
        """Neue, leere Kalkulation: Angebot mit automatischer Nummer, weiter mit Schritt 1 (Anfrage und Kunde)."""
        seite = self._neues_angebot()
        if seite is None:
            return None
        return self.seite_setzen(seite, bm.KUNDE)

    def _start_fuellen(self):
        aktiv = self.seite is not None and not self._seite_weg()
        self.weiter_karte.setVisible(aktiv)
        if aktiv:
            k = self.seite.kopf or {}
            b = self.bereit or {}
            self.weiter_text.setText(f"<b>Angebot {k.get('nummer') or self.seite.id}</b> · "
                                     f"{k.get('kunde') or 'ohne Kunde'} · {len(self.seite.positionen)} Bauteil(e)"
                                     + (f" · {b['text']}" if b.get("text") else ""))
        self._liste_fuellen()

    def _liste_fuellen(self):
        text = self.suche.text().strip()
        try:
            zeilen = self.db.angebote(text) if text else self.db.angebote()
        except Exception:           # noqa: BLE001
            zeilen = []
        zeilen = sorted(zeilen, key=lambda z: str(z.get("geaendert") or ""), reverse=True)[:40]
        self.liste.setRowCount(len(zeilen))
        for r, z in enumerate(zeilen):
            nr = _zelle(z.get("nummer") or f"Angebot {z['id']}")
            nr.setData(Qt.UserRole, z["id"])
            self.liste.setItem(r, 0, nr)
            self.liste.setItem(r, 1, _zelle(z.get("kunde") or "ohne Kunde"))
            self.liste.setItem(r, 2, _zelle(z.get("kundenreferenz") or ""))
            self.liste.setItem(r, 3, _zelle(z.get("vorgang") or "Entwurf"))
            vk = z.get("vk_netto")
            self.liste.setItem(r, 4, _zelle(bm.euro(vk) if isinstance(vk, (int, float)) else "–", True))
            self.liste.setItem(r, 5, _zelle(_datum(z.get("geaendert"))))
        self.liste.setToolTip("Doppelklick oder Enter öffnet die Kalkulation" if zeilen else
                              ("Keine Kalkulation gefunden." if text else "Noch keine Kalkulationen."))
        if len(zeilen) == 1:
            self.liste.selectRow(0)

    def _liste_oeffnen(self):
        r = self.liste.currentRow()
        if r < 0 and self.liste.rowCount() == 1:
            r = 0
        it = self.liste.item(r, 0) if r >= 0 else None
        if it is not None and it.data(Qt.UserRole) is not None:
            return self.oeffnen(it.data(Qt.UserRole))
        self.f.meldung("Bitte eine Kalkulation in der Liste wählen.", fehler=True)
        return None

    def oeffnen_suchen(self):
        self.zu_schritt(bm.START)
        self.suche.setFocus()
        self.suche.selectAll()
        return True

    def oeffnen(self, angebot_id, schritt=bm.BAUTEILE):
        """Bestehende Kalkulation öffnen: dieselbe Angebotsseite wie im Pro-Modus."""
        if angebot_id is None:
            return None
        seite = self.f.angebot_oeffnen(angebot_id)
        return self.seite_setzen(seite, schritt)

    def _neues_angebot(self):
        if self.db.nur_lesen:
            self.f.meldung("Lesemodus: es lassen sich keine Kalkulationen anlegen.", fehler=True)
            return None
        if self.f.angebote.rolle_gesperrt():
            return None
        i = self.db.angebot_neu()
        self.f.angebote.neu_laden()
        return self.f.angebot_oeffnen(i)

    def _leer_entfernen(self, seite):
        """Abgebrochen und noch keine Bauteile: das eben angelegte leere Angebot wieder entfernen (wie step_neu)."""
        if seite is None or seite.positionen:
            return False
        self.f.angebot_schliessen(seite.id)
        self.db.angebot_loeschen(seite.id, trotz_schutz=True)
        self.f.angebote.neu_laden()
        return True

    def neu_aus_step(self, dateien=None, kundennr=None):
        """STEP-Datei importieren: neues Angebot mit dem vorhandenen STEP-Import (Messung, Prüfdialog, Kunde)."""
        seite = self.f.angebote.neu_aus_step(dateien, kundennr)
        if seite is None:
            return None
        return self.seite_setzen(seite)

    def neu_aus_cad(self, dateien=None):
        """CAD-Datei importieren (DXF, TRUMPF LST, BLM, auch STEP): neues Angebot, Import wie Strg+I."""
        seite = self._neues_angebot()
        if seite is None:
            return None
        seite.dateien_waehlen(dateien)
        if self._leer_entfernen(seite):
            return None
        return self.seite_setzen(seite)

    def neu_aus_vorlage(self, vorlage_id=None):
        """Vorhandenes Bauteil aus der Bauteilbibliothek (Positionsvorlagen) in eine neue Kalkulation."""
        if not self.db.zeilen("positionsvorlagen"):
            self.f.meldung("Die Bauteilbibliothek ist noch leer. Ein Bauteil kommt hinein, wenn es im Pro-Modus "
                           "mit Rechtsklick → „Als Vorlage speichern“ gesichert wird.", fehler=True)
            return None
        seite = self._neues_angebot()
        if seite is None:
            return None
        seite.position_aus_vorlage(vorlage_id)
        if self._leer_entfernen(seite):
            return None
        return self.seite_setzen(seite)

    # -------------------------------------------------------------- Schritt 1: Anfrage und Kunde
    def _kunde_bauen(self):
        rolle, v, _ = _seite("Anfrage und Kunde", "Für wen ist das Angebot? Angebotsnummer, Datum und Bearbeiter "
                                                  "vergibt das Programm.")
        kunde = bs.karte("Kunde")
        zeile = QHBoxLayout()
        zeile.setSpacing(design.ABSTAND_KLEIN)
        self.kd_suche = QLineEdit()
        self.kd_suche.setPlaceholderText("Kunde suchen: Name, Kundennummer oder Ort")
        self.kd_suche.setClearButtonEnabled(True)
        self._kd_modell = QStringListModel()
        self.kd_vervollst = QCompleter(self._kd_modell, self.kd_suche)
        self.kd_vervollst.setCaseSensitivity(Qt.CaseInsensitive)
        self.kd_vervollst.setFilterMode(Qt.MatchContains)
        self.kd_vervollst.setMaxVisibleItems(10)
        self.kd_vervollst.activated.connect(self._kunde_aus_text)
        self.kd_suche.setCompleter(self.kd_vervollst)
        self.kd_suche.returnPressed.connect(lambda: self._kunde_aus_text(self.kd_suche.text()))
        zeile.addWidget(_feld("Kunde", self.kd_suche, pflicht=True, tipp=bm.FELD_HILFE["kunde"]), 1)
        knoepfe = QVBoxLayout()
        knoepfe.addStretch(1)
        reihe = QHBoxLayout()
        reihe.addWidget(_knopf("Kunde suchen …", lambda: self.kunde_waehlen(),
                               "Kundensuche mit allen Angaben (wie im Pro-Modus)"))
        self.kd_neu_knopf = _knopf("Neuer Kunde …", lambda: self.kunde_neu_zeigen(True),
                                   "Neuen Kunden direkt hier anlegen; die Kundennummer tragen Sie von Hand ein")
        reihe.addWidget(self.kd_neu_knopf)
        knoepfe.addLayout(reihe)
        zeile.addLayout(knoepfe)
        kunde.inhalt.addLayout(zeile)
        self.kd_text = _label("")
        self.kd_chip = bs.chip("", "neutral")
        info = QHBoxLayout()
        info.addWidget(self.kd_text, 1)
        info.addWidget(self.kd_chip, 0, Qt.AlignTop)
        kunde.inhalt.addLayout(info)
        v.addWidget(kunde)
        v.addWidget(self._kunde_neu_bauen())
        anfrage = bs.karte("Anfrage")
        g = QGridLayout()
        g.setHorizontalSpacing(design.ABSTAND_GROSS)
        g.setVerticalSpacing(design.ABSTAND)
        self.an_ansprech = QComboBox()
        self.an_ansprech.activated.connect(lambda _i: self.ansprech_setzen(self.an_ansprech.currentData()))
        self.an_projekt = QLineEdit()
        self.an_projekt.setPlaceholderText("z. B. Hallentor Nord")
        self.an_projekt.editingFinished.connect(lambda: self.feld_setzen("projekt", self.an_projekt.text()))
        self.an_zeichen = QLineEdit()
        self.an_zeichen.setPlaceholderText("Anfrage-Nr. oder Zeichen des Kunden")
        self.an_zeichen.editingFinished.connect(lambda: self.feld_setzen("kundenreferenz", self.an_zeichen.text()))
        self.an_lieferzeit = QLineEdit()
        self.an_lieferzeit.setPlaceholderText("z. B. 10 AT, 3 Wochen, KW 50, 15.12.2026")
        self.an_lieferzeit.editingFinished.connect(lambda: self.lieferzeit_setzen(self.an_lieferzeit.text()))
        g.addWidget(_feld("Ansprechpartner", self.an_ansprech, tipp="Ansprechpartner des Kunden; steht im Angebot "
                                                                    "als „z. Hd.“"), 0, 0)
        g.addWidget(_feld("Projekt", self.an_projekt, tipp=bm.FELD_HILFE["projekt"]), 0, 1)
        g.addWidget(_feld("Ihre Anfrage / Zeichen", self.an_zeichen, tipp="Anfragenummer oder Zeichen des Kunden; "
                                                                          "steht im Angebot"), 1, 0)
        g.addWidget(_feld("Lieferzeit", self.an_lieferzeit, tipp=bm.FELD_HILFE["lieferzeit"]), 1, 1)
        g.setColumnStretch(0, 1)
        g.setColumnStretch(1, 1)
        anfrage.inhalt.addLayout(g)
        self.an_nummer = _label("", "e_klein")
        anfrage.inhalt.addWidget(self.an_nummer)
        v.addWidget(anfrage)
        v.addStretch(1)
        return rolle

    def _kunde_neu_bauen(self):
        from . import kunden_daten
        self.kd_neu = bs.karte("Neuen Kunden anlegen")
        g = QGridLayout()
        g.setHorizontalSpacing(design.ABSTAND_GROSS)
        g.setVerticalSpacing(design.ABSTAND)
        self.kn = {}
        for i, (name, titel, pflicht, platz) in enumerate((
                ("kundennr", "Kundennummer", True, kunden_daten.nummer_hinweis(self.db)),
                ("name", "Firmenname", True, "z. B. Beispiel GmbH"), ("strasse", "Straße", False, ""),
                ("plz", "PLZ", False, ""), ("ort", "Ort", False, ""), ("email", "E-Mail", False, ""))):
            e = QLineEdit()
            e.setPlaceholderText(platz)
            self.kn[name] = e
            g.addWidget(_feld(titel, e, pflicht=pflicht), i // 3, i % 3)
        for c in range(3):
            g.setColumnStretch(c, 1)
        self.kd_neu.inhalt.addLayout(g)
        self.kn_fehler = _label("", "e_klein")
        self.kd_neu.inhalt.addWidget(self.kn_fehler)
        self.kn_trotzdem = _knopf("Trotzdem anlegen", lambda: self.kunde_anlegen(dubletten_ok=True),
                                  "Es gibt einen ähnlichen Kunden; trotzdem als neuen Kunden anlegen")
        self.kn_trotzdem.setVisible(False)
        self.kd_neu.inhalt.addWidget(bs.knopfzeile(
            self.kn_trotzdem, _knopf("Abbrechen", lambda: self.kunde_neu_zeigen(False), ""),
            _knopf("Kunde anlegen und übernehmen", lambda: self.kunde_anlegen(),
                   "Kunden im Kundenstamm anlegen und für dieses Angebot übernehmen")))
        self.kd_neu.setVisible(False)
        return self.kd_neu

    def kunde_neu_zeigen(self, an):
        self.kd_neu.setVisible(bool(an))
        self.kn_fehler.setText("")
        self.kn_trotzdem.setVisible(False)
        if an:
            from . import kunden_daten
            self.kn["kundennr"].setPlaceholderText(kunden_daten.nummer_hinweis(self.db))
            text = self.kd_suche.text().strip()
            if text and not self.kn["name"].text():
                self.kn["name"].setText(text)
            self.kn["kundennr"].setFocus()
        return bool(an)

    def kunde_anlegen(self, werte=None, dubletten_ok=False):
        """Neuen Kunden anlegen (kunden_daten.anlegen, Kundennummer immer von Hand) und ins Angebot übernehmen.
        werte (Tests): statt der Felder. Ergebnis: Kundennummer oder None (Fehlertext unter den Feldern)."""
        from . import kunden_daten
        if not self._darf_aendern():
            return None
        w = dict(werte) if werte is not None else {n: e.text().strip() for n, e in self.kn.items()}
        w = {n: x for n, x in w.items() if x not in ("", None)}
        try:
            nr = kunden_daten.anlegen(self.db, w, dubletten_ok=dubletten_ok)
        except kunden_daten.KundenFehler as e:
            self.kn_fehler.setText(f"<span style='color:{_farbe(design.ROT)}'>{e}</span>")
            self.kn_trotzdem.setVisible("Dublette" in str(e))
            return None
        for e in self.kn.values():
            e.clear()
        self.kd_neu.setVisible(False)
        kunden = getattr(self.f, "kunden", None)
        if kunden is not None and hasattr(kunden, "neu_laden"):
            kunden.neu_laden()
        self.kunde_waehlen(nr)
        self.f.meldung(f"Kunde {nr} angelegt und übernommen.")
        return nr

    def _kunden_liste(self):
        from . import kunden_daten
        try:
            zeilen = kunden_daten.uebersicht(self.db)
        except Exception:           # noqa: BLE001 – ohne Kundenstamm nur die Kundensuche
            zeilen = []
        self._kd_map = {}
        texte = []
        for z in zeilen:
            if z.get("status") == kunden_daten.GESPERRT:
                continue
            t = " · ".join(str(x) for x in (z.get("name"), z.get("kundennr"), z.get("ort_anzeige")) if x)
            self._kd_map[t] = z["kundennr"]
            texte.append(t)
        self._kd_modell.setStringList(texte)
        return texte

    def _kunde_aus_text(self, text):
        """Eintrag aus der Vervollständigung oder Enter im Suchfeld: genau ein Treffer = übernehmen, sonst die
        Kundensuche (vorbelegt)."""
        from . import kunden_daten
        text = str(text or "").strip()
        if not text:
            return None
        nr = getattr(self, "_kd_map", {}).get(text)
        if nr is None:
            treffer = kunden_daten.filtern(kunden_daten.uebersicht(self.db), text)
            if len(treffer) == 1:
                nr = treffer[0]["kundennr"]
        if nr is None:
            return self.kunde_waehlen()
        return self.kunde_waehlen(nr)

    def _kunde_fuellen(self):
        from . import kunden_daten
        from .angebot import lieferzeit_eingabe
        s = self.seite
        if s is None:
            return
        self._kunden_liste()
        k = s.kopf or {}
        darf = self._darf_aendern()
        for w in (self.kd_suche, self.kd_neu_knopf, self.an_ansprech, self.an_projekt, self.an_zeichen,
                  self.an_lieferzeit):
            w.setEnabled(darf)
        nr = k.get("kundennr")
        stamm = kunden_daten.kunde(self.db, nr) if nr else None
        if not self.kd_suche.hasFocus():
            self.kd_suche.setText("")
        if k.get("kunde") or nr:
            zeilen = kunden_daten.anschrift(stamm, k.get("kunde_ansprech")) if stamm else []
            self.kd_text.setText(f"<b>{k.get('kunde') or (stamm or {}).get('name') or ''}</b> · Kundennr. "
                                 f"{nr or '–'}" + "".join(f"<br><span style='color:{_farbe(GRAU)}'>{z}</span>"
                                                          for z in zeilen))
            bs.chip_setzen(self.kd_chip, "Aus dem Kundenstamm" if stamm else "Nicht im Kundenstamm",
                           "ok" if stamm else "warnung")
            self.kd_chip.setVisible(True)
        else:
            self.kd_text.setText(f"<span style='color:{_farbe(GRAU)}'>Noch kein Kunde gewählt. Im Feld oben tippen "
                                 "und aus der Liste wählen.</span>")
            self.kd_chip.setVisible(False)
        self.an_ansprech.blockSignals(True)
        self.an_ansprech.clear()
        self.an_ansprech.addItem("(ohne Ansprechpartner)", None)
        if nr and stamm:
            for uid, text in kunden_daten.fuer_angebot(self.db, nr)["personen"]:
                self.an_ansprech.addItem(text, uid)
        i = self.an_ansprech.findData(k.get("kunde_ansprech_uid")) if k.get("kunde_ansprech_uid") else 0
        self.an_ansprech.setCurrentIndex(max(0, i))
        self.an_ansprech.setEnabled(darf and self.an_ansprech.count() > 1)
        self.an_ansprech.blockSignals(False)
        for feld, name in ((self.an_projekt, "projekt"), (self.an_zeichen, "kundenreferenz")):
            if not feld.hasFocus():
                feld.setText(k.get(name) or "")
        if not self.an_lieferzeit.hasFocus():
            self.an_lieferzeit.setText(lieferzeit_eingabe(k))
        bearb = k.get("bearbeiter")
        self.an_nummer.setText(f"Angebotsnummer {k.get('nummer') or s.id} · Datum {_datum(k.get('datum'))}"
                               + (f" · Bearbeiter {bearb}" if bearb else ""))

    def feld_setzen(self, name, wert):
        """Projekt, Ihre Anfrage/Zeichen … in dieselben Angebotsfelder wie im Pro-Modus (Angebotskopf)."""
        s = self.seite
        if s is None:
            return False
        wert = str(wert or "").strip() or None
        if wert == ((s.kopf or {}).get(name) or None):
            return False
        return self._kopf_wert(name, wert)

    def ansprech_setzen(self, uid):
        if not self._darf_aendern():
            return None
        p = self.seite.ansprech_waehlen(uid)
        self.aktualisieren()
        return p

    def lieferzeit_setzen(self, text):
        from .angebot import lieferzeit_eingabe
        s = self.seite
        if not self._darf_aendern() or str(text or "").strip() == lieferzeit_eingabe(s.kopf or {}):
            return False
        s.lieferzeit_speichern(text)
        self.aktualisieren()
        return True

    def kunde_waehlen(self, kundennr=None):
        """Kunde übernehmen (kundennr) oder die Kundensuche öffnen (ohne): wie im Pro-Modus mit Name, Konditionen,
        Ansprechpartner und Lieferadresse."""
        if self.seite is None:
            return None
        nr = self.seite.kunde_suchen(kundennr)
        self.aktualisieren()
        return nr

    # -------------------------------------------------------------- Schritt 2: Bauteile
    def _bauteile_bauen(self):
        aktionen = [_knopf("Importieren …", lambda: self.importieren(),
                           "STEP-, DXF- oder TRUMPF-Dateien in diese Kalkulation holen (oder ins Fenster ziehen)"),
                    _knopf("Aus Bibliothek …", self.aus_bibliothek, "Gespeichertes Bauteil hinzufügen")]
        rolle, v, self.bt_kopf = _seite("Bauteile", "", aktionen)
        self.bt_hinweise = HinweisListe()
        self.bt_hinweise.loesen.connect(self.loesen)
        v.addWidget(self.bt_hinweise)
        teiler = QSplitter(Qt.Horizontal)
        teiler.setChildrenCollapsible(False)
        links = bs.karte("")
        links.layout().setContentsMargins(0, 0, 0, design.ABSTAND)
        self.bt = _tabelle(["", "Bauteil", "Profil", "Werkstoff", "Länge", "Stück", "Stückpreis", "Summe"], dehnen=1,
                           rechts=(4, 5, 6, 7))
        self.bt.itemSelectionChanged.connect(self._bauteil_gewaehlt)
        self.bt.doubleClicked.connect(lambda i: self.loesen("editor", i.row()))
        self.bt.setToolTip("Doppelklick: Bauteil im Editor prüfen. Stück direkt in der Spalte ändern.")
        links.inhalt.addWidget(self.bt)
        unten = QHBoxLayout()
        unten.setContentsMargins(design.ABSTAND, 0, design.ABSTAND, 0)
        unten.addWidget(_knopf("Im Editor prüfen …", lambda: self.loesen("editor", self._bt_zeile()),
                               "Gewähltes Bauteil im Editor öffnen (Konturen, Bohrungen, Länge)"))
        unten.addWidget(_knopf("Bauteil entfernen", self.bauteil_entfernen, "Gewähltes Bauteil löschen "
                               "(mit Rückgängig)"))
        unten.addStretch(1)
        self.bt_summe = _label("", "e_unter", umbruch=False)
        unten.addWidget(self.bt_summe)
        links.inhalt.addLayout(unten)
        links.inhalt.addStretch(1)
        self.vorschau_karte = bs.karte("Vorschau")
        self.vorschau_platz = QVBoxLayout()
        self.vorschau = None
        self.vorschau_titel = _label("Bauteil in der Liste wählen.", "e_klein")
        self.vorschau_karte.inhalt.addLayout(self.vorschau_platz, 1)
        self.vorschau_karte.inhalt.addWidget(self.vorschau_titel)
        self.erkannt = bs.wertzeilen([(t, "–") for t in ("Art", "Querschnitt", "Wandstärke", "Länge")])
        self.vorschau_karte.inhalt.addWidget(self.erkannt)
        self.details = Aufklapper("Details")
        self.erkannt_mehr = bs.wertzeilen([(t, "–") for t in ("Abmessung", "Werkstoff", "Schnittkonturen",
                                                              "Schneidweg")])
        self.details.lay.addWidget(self.erkannt_mehr)
        self.bt_status = _label("", "e_klein")
        self.details.lay.addWidget(self.bt_status)
        self.vorschau_karte.inhalt.addWidget(self.details)
        self.vorschau_karte.setMinimumWidth(300)
        teiler.addWidget(links)
        teiler.addWidget(self.vorschau_karte)
        teiler.setStretchFactor(0, 3)
        teiler.setStretchFactor(1, 2)
        v.addWidget(teiler, 1)
        return rolle

    def _bt_zeile(self):
        r = self.bt.currentRow()
        return r if r >= 0 else None

    def _bauteile_fuellen(self):
        d = self.daten
        bauteile = d["bauteile"] if d else []
        zeilen = d["zeilen"] if d else []
        gerechnet = bool(d and d["stand"] == "aktuell")
        stueck = sum(int(b["stueck"] or 0) for b in bauteile)
        self.bt_kopf.untertitel.setText(f"{len(bauteile)} Bauteil(e), {bm.zahl(stueck, 0)} Stück. Stückzahl prüfen, "
                                        "Bauteil anklicken für die Vorschau." if bauteile else
                                        "Noch keine Bauteile: „Importieren …“ oder Dateien ins Fenster ziehen.")
        self.bt_kopf.untertitel.show()
        self.bt.setRowCount(len(bauteile))
        self.stueck_felder = []
        for r, b in enumerate(bauteile):
            st = b["stufe"]
            z = _zelle(ZEICHEN[st], tipp=b["status"] or "Vollständig")
            z.setForeground(QColor(_farbe(design.CHIPS[STUFE_CHIP[st]][0])))
            z.setTextAlignment(Qt.AlignCenter)
            self.bt.setItem(r, 0, z)
            self.bt.setItem(r, 1, _zelle(b["name"], tipp=b["status"] or b["art_text"]))
            self.bt.setItem(r, 2, _zelle(" ".join(x for x in (b["form"], b["profil"]) if x) or b["art_text"],
                                         tipp=bm.FELD_HILFE["profil"]))
            self.bt.setItem(r, 3, _zelle(b["werkstoff"] or "–", tipp=bm.FELD_HILFE["werkstoff"]))
            self.bt.setItem(r, 4, _zelle(f"{bm.zahl(b['laenge'], 1)} mm" if b["laenge"] else "–", True,
                                         bm.FELD_HILFE["laenge"]))
            sp = QSpinBox()
            sp.setRange(0, 9_999_999)
            sp.setValue(int(b["stueck"] or 0))
            sp.setToolTip(bm.FELD_HILFE["stueck"])
            sp.setMinimumWidth(80)
            sp.setAlignment(Qt.AlignRight)
            sp.setGroupSeparatorShown(True)
            sp.setKeyboardTracking(False)
            sp.setEnabled(self._darf_aendern())
            sp.editingFinished.connect(lambda r=r, sp=sp: self.stueck_setzen(r, sp.value()))
            if b["stufe"] == "FEHLER" and not b["stueck"]:
                sp.setStyleSheet(stil.ROTER_RAHMEN)
            self.bt.setCellWidget(r, 5, sp)
            self.stueck_felder.append(sp)
            z = zeilen[r] if r < len(zeilen) else {}
            self.bt.setItem(r, 6, _zelle(bm.euro(z.get("preis_teil")) if gerechnet else "–", True))
            self.bt.setItem(r, 7, _zelle(bm.euro(z.get("preis_position")) if gerechnet else "–", True))
        _hoehe_anpassen(self.bt, 6, 16)
        self.bt_summe.setText(f"Summe {bm.euro(d['ergebnis']['verkauf'])} netto" if gerechnet and bauteile else
                              ("Preise nach der Berechnung (Schritt 3)" if bauteile else ""))
        self.bt_hinweise.setzen([h for h in (d["hinweise"] if d else []) if bm.schritt_von(h) == bm.BAUTEILE])
        if bauteile and self.bt.currentRow() < 0:
            self.bt.selectRow(0)
        else:
            self._bauteil_gewaehlt()

    def _bauteil_gewaehlt(self):
        r = self._bt_zeile()
        d = self.daten
        if r is None or d is None or r >= len(d["bauteile"]):
            for w in list(self.erkannt.werte.values()) + list(self.erkannt_mehr.werte.values()):
                w.setText("–")
            self.bt_status.setText("")
            return
        b = d["bauteile"][r]
        p = self.seite.positionen[r]
        werte = {"Art": b["art_text"], "Querschnitt": b["form"] or "–", "Abmessung": b["profil"] or "–",
                 "Wandstärke": f"{bm.zahl(b['wand'], 1)} mm" if b["wand"] else "–",
                 "Länge": f"{bm.zahl(b['laenge'], 1)} mm" if b["laenge"] else "–",
                 "Werkstoff": b["werkstoff"] or "nicht erkannt",
                 "Schnittkonturen": str(b["konturen"]) if b["konturen"] is not None else "–",
                 "Schneidweg": f"{bm.zahl(b['schneidweg'], 0)} mm" if b["schneidweg"] else "–"}
        for t, w in werte.items():
            (self.erkannt.werte.get(t) or self.erkannt_mehr.werte[t]).setText(w)
        self.vorschau_karte.titel.setText(b["name"][:60])
        self.bt_status.setText(f"<span style='color:{_farbe(design.CHIPS[STUFE_CHIP[b['stufe']]][0])}'>"
                               f"{ZEICHEN[b['stufe']]} {bm.loesung(b['status'])[0]}</span>" if b["stufe"] != "OK"
                               else "")
        self._vorschau(r, p)

    def _vorschau(self, r, p):
        try:
            netz, titel = self.seite._vorschau_netz(r)
        except Exception:           # noqa: BLE001 – Vorschau ist Zusatz
            netz, titel = None, ""
        if netz is None:
            self.vorschau_titel.setText("Keine 3D-Daten (kein STEP, keine Eingaben im Editor).")
            self.vorschau_titel.show()
            if self.vorschau is not None:
                self.vorschau.setzen(None)
            return
        if self.vorschau is None:
            from .ansicht3d import Ansicht3D      # ruhige Vorschau: Drehen mit der Maus, ohne Werkzeugleiste
            self.vorschau = Ansicht3D()
            self.vorschau.setMinimumHeight(260)
            self.vorschau.setToolTip("Mit der Maus drehen und zoomen. Messen, Schnitt und Explosion: im Editor "
                                     "bzw. im Pro-Modus.")
            self.vorschau_platz.addWidget(self.vorschau, 1)
        self.vorschau.setzen(netz, titel)
        self.vorschau_titel.setText("")
        self.vorschau_titel.hide()

    def stueck_setzen(self, zeile, anzahl):
        """Stückzahl wie in der Positionstabelle des Pro-Modus speichern (gleiche Prüfung und Sperre)."""
        s = self.seite
        if s is None or zeile >= len(s.positionen):
            return False
        if int(s.positionen[zeile].get("stueck") or 0) == int(anzahl):
            return False
        m = s.pos_modell
        spalte = next((c for c in range(m.columnCount()) if m.name(c) == "stueck"), None)
        if spalte is None:
            return False
        ok = m.setData(m.index(zeile, spalte), str(int(anzahl)) if anzahl else "")
        QTimer.singleShot(0, self.aktualisieren)
        return ok

    def _zeilen_markieren(self, zeilen):
        s = self.seite
        sel = s.pos_ansicht.selectionModel()
        sel.clearSelection()
        from PySide6.QtCore import QItemSelectionModel
        for r in zeilen:
            sel.select(s.pos_modell.index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)

    def bauteil_entfernen(self):
        r = self._bt_zeile()
        if self.seite is None or r is None:
            self.f.meldung("Bitte zuerst ein Bauteil in der Liste wählen.", fehler=True)
            return None
        self._zeilen_markieren([r])
        self.seite.positionen_loeschen()        # mit „Rückgängig“ in der Einblendung, wie im Pro-Modus
        self.aktualisieren()
        return True

    def importieren(self, dateien=None):
        if self.seite is None:
            return self.neu_aus_cad(dateien)
        self.seite.dateien_waehlen(dateien)
        self.aktualisieren()
        return True

    def aus_bibliothek(self, vorlage_id=None):
        if self.seite is None:
            return self.neu_aus_vorlage(vorlage_id)
        if not self.db.zeilen("positionsvorlagen"):
            self.f.meldung("Die Bauteilbibliothek ist noch leer.", fehler=True)
            return None
        erg = self.seite.position_aus_vorlage(vorlage_id)
        self.aktualisieren()
        return erg

    # -------------------------------------------------------------- Lösungen
    def loesen(self, aktion, zeile=None):
        """Lösungsknopf eines Hinweises: an die passende Stelle (im einfachen Modus, sonst Editor/Pro-Modus)."""
        s = self.seite
        if aktion == "import":
            self.zu_schritt(bm.BAUTEILE)
            return self.importieren()
        if s is None:
            return None
        if aktion == "stueck":
            self.zu_schritt(bm.BAUTEILE)
            if zeile is not None and zeile < len(getattr(self, "stueck_felder", ())):
                self.bt.selectRow(zeile)
                self.stueck_felder[zeile].setFocus()
                self.stueck_felder[zeile].selectAll()
            return True
        if aktion == "material":
            return self.zu_schritt(bm.MATERIAL)
        if aktion == "optimieren":
            ok = s.optimieren()
            self.aktualisieren()
            return ok
        if aktion == "kunde":
            self.zu_schritt(bm.KUNDE)
            self.kd_suche.setFocus()
            return True
        if aktion == "editor" and zeile is not None:
            erg = s.editor_oeffnen(zeile)
            self.aktualisieren()
            return erg
        if aktion == "zukauf" and zeile is not None:
            erg = s.editor_oeffnen(zeile) if s.editor_art(s.positionen[zeile]) else None
            if erg is None:
                self._zeilen_markieren([zeile])
                umschalten(self.f, bm.EXPERTE)
            self.aktualisieren()
            return erg
        if zeile is not None:
            self._zeilen_markieren([zeile])
        umschalten(self.f, bm.EXPERTE)
        return True

    # -------------------------------------------------------------- Schritt 3: Material und Fertigung
    def _material_bauen(self):
        rolle, v, self.mat_kopf = _seite("Material und Fertigung", "Das Programm schlägt Material und Maschine aus "
                                         "der erkannten Geometrie vor. Ändern Sie nur, was der Kunde anders möchte.")
        self.mat_hinweise = HinweisListe()
        self.mat_hinweise.loesen.connect(self.loesen)
        v.addWidget(self.mat_hinweise)
        mat = bs.karte("Material je Abmessung", rechts=[_knopf(
            "Materialpreise und Lieferlängen …", self.material_dialog,
            "Materialeinsatz und Kosten je Abmessung; Werkstoff, Lieferlänge, Meterpreis ändern")])
        self.mat_tab = _tabelle(["Abmessung", "Werkstoff", "Wand", "Teile", "Preis", "Preisstand", "Verfügbarkeit"],
                                dehnen=6, rechts=(2, 3, 4))
        self.mat_tab.verticalHeader().setDefaultSectionSize(38)
        mat.inhalt.addWidget(self.mat_tab)
        self.mat_leer = _label("Keine Rohr- oder Profilteile: Zukauf-, Norm- und Blechteile haben ihren eigenen "
                               "Preis.", "e_unter")
        mat.inhalt.addWidget(self.mat_leer)
        v.addWidget(mat)
        fert = bs.karte("Fertigung")
        oben = QHBoxLayout()
        oben.setSpacing(design.ABSTAND_GROSS)
        self.fe_maschine = QComboBox()
        self.fe_maschine.setMinimumWidth(220)
        self.fe_maschine.activated.connect(lambda _i: self.maschine_setzen(self.fe_maschine.currentText()))
        oben.addWidget(_feld("Maschine", self.fe_maschine, tipp=bm.FELD_HILFE["maschine"]), 0, Qt.AlignTop)
        self.fe_werte = bs.wertzeilen([("Schnittplan", "–"), ("Maschinenzeit", "–"), ("Rüsten und Programmieren", "–")])
        oben.addWidget(self.fe_werte, 1)
        fert.inhalt.addLayout(oben)
        fert.inhalt.addWidget(_trenner())
        zeile = QHBoxLayout()
        zeile.addWidget(_knopf("Zusatzarbeiten hinzufügen …", self.zusatzarbeiten,
                               "Gewinde, Senken, Entgraten, Biegen … für alle oder das gewählte Bauteil"))
        self.vorschlag_knopf = _knopf("Vorgeschlagene Arbeiten übernehmen", self.vorschlaege,
                                      "Vom Programm erkannte Zusatzarbeiten (z. B. Gewinde aus Bohrungen) übernehmen")
        zeile.addWidget(self.vorschlag_knopf)
        zeile.addStretch(1)
        zeile.addWidget(_knopf("Neu berechnen", lambda: self.loesen("optimieren"),
                               "Stangen optimieren und alle Preise neu rechnen"))
        fert.inhalt.addLayout(zeile)
        self.zusatz_text = _label("", "e_klein")
        fert.inhalt.addWidget(self.zusatz_text)
        v.addWidget(fert)
        weitere = bs.karte("")
        self.weitere = Aufklapper("Weitere Kosten: Fracht")
        self.weitere.lay.addWidget(self._fracht_karte_bauen())
        weitere.inhalt.addWidget(self.weitere)
        self.fr_kurz = _label("", "e_klein")
        weitere.inhalt.addWidget(self.fr_kurz)
        self.weitere.umgeschaltet.connect(lambda an: self.fr_kurz.setVisible(not an))
        v.addWidget(weitere)
        v.addStretch(1)
        return rolle

    def _material_fuellen(self):
        s, d = self.seite, self.daten
        self.mat_tab.setRowCount(0)
        if s is None or d is None:
            self.mat_gruppen = []
            return
        from . import materialplattform as mp, rechnen, step
        try:
            var = mp.varianten(s.k, s.tabellen, self.db.zeilen(mp.LIEFERANTEN_TABELLE), bestand=mp.lager_bestand(self.db))
        except Exception:           # noqa: BLE001 – ohne Zusatzangaben weiter
            var = []
        gruppen = bm.material_gruppen(s.positionen, d["bauteile"], s.kopf, s.k, s.tabellen, var,
                                      lambda p: rechnen.meterpreis(p, s.kopf, s.positionen, s.k, s.tabellen))
        lager = getattr(self.f, "lager_an", lambda: False)()
        darf = self._darf_aendern()
        self.mat_tab.setRowCount(len(gruppen))
        self.mat_ws = []
        for r, g in enumerate(gruppen):
            erkannt = any(step.herkunft(s.positionen[i]) for i in g["zeilen"])
            self.mat_tab.setItem(r, 0, _zelle(f"{g['form'] or 'Profil'} {g['profil']}",
                                              tipp="Abmessung aus der STEP-Datei erkannt" if erkannt else ""))
            ws = QComboBox()
            ws.setEditable(True)
            ws.setInsertPolicy(QComboBox.NoInsert)
            ws.setToolTip(bm.FELD_HILFE["werkstoff"] + " Tippen zum Suchen.")
            for wid, z in sorted(s.k.werkstoffe.items()):
                ws.addItem(" · ".join(str(x) for x in (wid, z.get("werkstoff"), z.get("kategorie")) if x), wid)
            i = ws.findData(g["werkstoff"])
            if i < 0:
                ws.insertItem(0, "(bitte wählen)", None)
                i = 0
            ws.setCurrentIndex(i)
            ws.completer().setFilterMode(Qt.MatchContains)
            ws.completer().setCompletionMode(QCompleter.PopupCompletion)
            ws.setEnabled(darf)
            ws.activated.connect(lambda _i, ws=ws, g=g: self.werkstoff_setzen(g["zeilen"], ws.currentData()))
            self.mat_tab.setCellWidget(r, 1, ws)
            self.mat_ws.append(ws)
            self.mat_tab.setItem(r, 2, _zelle(f"{bm.zahl(g['wand'], 1)} mm" if g["wand"] else "–", True))
            self.mat_tab.setItem(r, 3, _zelle(bm.zahl(g["stueck"], 0), True))
            if g["fehlt_preis"]:
                b = _knopf("Preis eintragen …", self.material_dialog, "Für dieses Material fehlt ein gültiger Preis")
                b.setStyleSheet(stil.ROTER_RAHMEN)
                self.mat_tab.setCellWidget(r, 4, b)
            else:
                self.mat_tab.setItem(r, 4, _zelle(f"{bm.zahl(g['preis_m'], 2)} €/m", True,
                                                  (f"{bm.zahl(g['preis_kg'], 2)} €/kg · " if g.get("preis_kg") else "")
                                                  + bm.FELD_HILFE["preis_m"]))
            alter = g.get("alter_tage")
            stand = (_datum(g["stand"]) if g["stand"] else "–") + (f" ({alter} Tage)" if alter is not None else "")
            self.mat_tab.setItem(r, 5, _zelle(stand, tipp=g["quelle"] or ""))
            vt = bm.verfuegbar_text(g, lager)
            self.mat_tab.setItem(r, 6, _zelle(vt, tipp=bm.FELD_HILFE["verfuegbar"]))
        _hoehe_anpassen(self.mat_tab, 1, 12)
        self.mat_tab.setVisible(bool(gruppen))
        self.mat_leer.setVisible(not gruppen)
        self.mat_gruppen = gruppen
        self.mat_hinweise.setzen([h for h in d["hinweise"] if bm.schritt_von(h) == bm.MATERIAL])
        self._fertigung_fuellen()
        self._fracht_fuellen()

    def _fertigung_fuellen(self):
        s, d = self.seite, self.daten
        e, g = d["ergebnis"], d["ergebnis"]["gruppen"]
        self.fe_maschine.blockSignals(True)
        self.fe_maschine.clear()
        self.fe_maschine.addItems(s.k.auswahl("maschine"))
        m = (s.kopf or {}).get("maschine") or ""
        if m and self.fe_maschine.findText(m) < 0:
            self.fe_maschine.addItem(m)
        self.fe_maschine.setCurrentText(m)
        self.fe_maschine.setEnabled(self._darf_aendern() and self.fe_maschine.count() > 1)
        self.fe_maschine.setToolTip(bm.FELD_HILFE["maschine"] if self.fe_maschine.count() > 1 else
                                    "Nur eine Maschine eingerichtet: sie wird automatisch genommen.")
        self.fe_maschine.blockSignals(False)
        aktuell = d["stand"] == "aktuell"
        w = self.fe_werte.werte
        w["Schnittplan"].setText("✓ aktuell" if aktuell else "wird neu berechnet")
        w["Schnittplan"].setStyleSheet(f"color: {_farbe(design.GRUEN if aktuell else design.GELB_TEXT)};")
        w["Maschinenzeit"].setText(bm.minuten_text(e["maschine_min"]) if aktuell and e["teile"] else "–")
        w["Rüsten und Programmieren"].setText(bm.euro(g["ruesten"]) if aktuell else "–")
        vorschl = sum(len(x or ()) for x in getattr(s.pos_modell, "vorschlaege", ()) or ())
        self.vorschlag_knopf.setText(f"Vorgeschlagene Arbeiten übernehmen ({vorschl})" if vorschl else
                                     "Keine offenen Vorschläge")
        self.vorschlag_knopf.setEnabled(bool(vorschl) and self._darf_aendern())
        zus = g["zusatz"] + g["bearbeitung"]
        self.zusatz_text.setText(f"Zusatzarbeiten und Bearbeitung in der Kalkulation: {bm.euro(zus)}" if aktuell and zus
                                 else "Noch keine Zusatzarbeiten." if aktuell else "")

    def maschine_setzen(self, name):
        """Maschine des Angebots (Kopffeld wie im Pro-Modus); danach wird automatisch neu gerechnet."""
        s = self.seite
        if s is None or not name or name == ((s.kopf or {}).get("maschine") or ""):
            return False
        ok = self._kopf_wert("maschine", name)
        if ok:
            self.automatisch_rechnen()
            self.aktualisieren()
        return ok

    def werkstoff_setzen(self, zeilen, werkstoff):
        if self.seite is None or not werkstoff:
            return None
        n = self.seite.fuer_markierte_setzen(list(zeilen), werkstoff=werkstoff)
        self.aktualisieren()
        return n

    def material_dialog(self):
        if self.seite is None:
            return None
        erg = self.seite.material_einstellen()
        self.aktualisieren()
        return erg

    def zusatzarbeiten(self):
        s = self.seite
        if s is None or not s.positionen:
            return None
        r = self._bt_zeile() if hasattr(self, "bt") else None
        erg = s.zusatzarbeiten([r] if r is not None else list(range(len(s.positionen))))
        self.aktualisieren()
        return erg

    def vorschlaege(self):
        if self.seite is None:
            return None
        erg = self.seite.vorschlaege_uebernehmen(list(range(len(self.seite.positionen))))
        self.aktualisieren()
        return erg
    # -------------------------------------------------------------- Fracht (Patrick 25.11.2026, gleiche Rechnung)
    def _darf_aendern(self):
        s = self.seite
        return s is not None and not s.db.nur_lesen and not s.fremd()

    def _fracht_karte_bauen(self):
        """Frachtkosten wie im Angebotskopf des Expertenmodus: Frachtart, Betrag von Hand, Verteilung, „Fracht
        berechnen …“ (Paket/Palette, Tarif, auch je Staffelmenge) und automatisch nachführen (fracht_angebot.py)."""
        from . import fracht_angebot as fa
        k = QWidget()
        k.lay = QVBoxLayout(k)
        k.lay.setContentsMargins(0, 0, 0, 0)
        k.lay.addWidget(_label("Fracht geht wie im Pro-Modus in den Verkaufspreis ein und wird auf die Bauteile "
                               "verteilt. Betrag von Hand eintragen oder vom Programm berechnen lassen.", "e_klein"))
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)
        self.fr_modus = QComboBox()
        self.fr_modus.addItems(fa.MODI)
        self.fr_modus.setToolTip("manuell: Betrag von Hand · berechnet: aus „Fracht berechnen …“ · keine Fracht "
                                 "(Abholung, ab Werk) und im Artikelpreis enthalten: 0 € in der Kalkulation")
        self.fr_modus.activated.connect(lambda _i: self.fracht_modus_setzen(self.fr_modus.currentText()))
        self.fr_betrag = QDoubleSpinBox()
        self.fr_betrag.setRange(0, 100000)
        self.fr_betrag.setDecimals(2)
        self.fr_betrag.setSuffix(" €")
        self.fr_betrag.setGroupSeparatorShown(True)
        self.fr_betrag.setKeyboardTracking(False)
        self.fr_betrag.setToolTip("Frachtkosten für das ganze Angebot (netto)")
        self.fr_betrag.editingFinished.connect(lambda: self.fracht_setzen(self.fr_betrag.value()))
        self.fr_umlage = QComboBox()
        self.fr_umlage.addItems(fa.UMLAGEN)
        self.fr_umlage.setToolTip("je Stück: jedes Teil trägt gleich viel · nach Gewicht: Anteil am Gesamtgewicht")
        self.fr_umlage.activated.connect(lambda _i: self.fracht_umlage_setzen(self.fr_umlage.currentText()))
        self.fr_auto = QCheckBox("Fracht automatisch berechnen")
        self.fr_auto.setToolTip("Fracht bei jeder Änderung aus Ziel-PLZ des Kunden, Gewicht, Packvorschlag (Paket "
                                "oder Palette) und Tarif rechnen")
        self.fr_auto.clicked.connect(self.fracht_auto)
        self.fr_knopf = _knopf("Fracht berechnen …", self.fracht_berechnen,
                               "Fracht aus PLZ, Gewicht, Paket/Palette und Tarif berechnen (wie im Pro-Modus)")
        g.addWidget(_label("Frachtart", "e_feld"), 0, 0)
        g.addWidget(self.fr_modus, 0, 1)
        g.addWidget(_label("Betrag", "e_feld"), 0, 2)
        g.addWidget(self.fr_betrag, 0, 3)
        g.addWidget(_label("Verteilen", "e_feld"), 1, 0)
        g.addWidget(self.fr_umlage, 1, 1)
        g.addWidget(self.fr_auto, 1, 2, 1, 2)
        g.setColumnStretch(4, 1)
        k.lay.addLayout(g)
        zeile = QHBoxLayout()
        self.fr_text = _label("", "e_klein")
        zeile.addWidget(self.fr_text, 1)
        zeile.addWidget(self.fr_knopf)
        k.lay.addLayout(zeile)
        return k

    def _fracht_fuellen(self):
        from . import fracht_angebot as fa
        from . import funktionen
        s, d = self.seite, self.daten
        if s is None or d is None:
            return
        kopf = s.kopf or {}
        m = fa.modus(kopf)
        for w, wert in ((self.fr_modus, m), (self.fr_umlage, fa.umlage(kopf))):
            w.blockSignals(True)
            w.setCurrentText(wert)
            w.blockSignals(False)
        self.fr_betrag.blockSignals(True)
        self.fr_betrag.setValue(float(kopf.get("fracht") or 0))
        self.fr_betrag.blockSignals(False)
        self.fr_auto.blockSignals(True)
        self.fr_auto.setChecked(fa.auto(kopf))
        self.fr_auto.blockSignals(False)
        darf = self._darf_aendern()
        berechnet = m == fa.BERECHNET
        self.fr_modus.setEnabled(darf)
        self.fr_umlage.setEnabled(darf and m in (fa.MANUELL, fa.BERECHNET))
        self.fr_betrag.setEnabled(darf and m == fa.MANUELL)
        rechnen_an = funktionen.an("funktion_fracht")
        self.fr_auto.setVisible(rechnen_an)
        self.fr_auto.setEnabled(darf and berechnet)
        self.fr_knopf.setVisible(rechnen_an)
        self.fr_knopf.setEnabled(darf and bool(s.positionen))
        betrag = float(d["summen"].get("fracht") or 0)
        frei = float(d["summen"].get("frachtfrei") or 0)
        teile = [f"In der Kalkulation: <b>{bm.euro(betrag)}</b>"]
        if abs(frei) > 0.004:
            teile.append(f"Frachtfrei-Umlage {bm.euro(frei)}")
        hinweis = fa.angebotstext(kopf)
        if hinweis:
            teile.append(f"Im Angebot: <i>{hinweis}</i>")
        if berechnet and not betrag:
            teile.append("Noch nicht berechnet: „Fracht berechnen …“")
        self.fr_text.setText(" · ".join(teile))
        self.fr_kurz.setText(f"{m}: {bm.euro(betrag)} in der Kalkulation" if m != fa.KEINE else "Keine Fracht.")
        if (betrag or m not in (fa.KEINE, fa.MANUELL)) and not self.weitere.offen() and not getattr(self, "_fr_auf", 0):
            self._fr_auf = 1            # einmal je Sitzung: vorhandene Fracht gleich sichtbar
            self.weitere.zeigen(True)

    def _kopf_wert(self, name, wert):
        s = self.seite
        if not self._darf_aendern():
            return False
        from .angebot import KOPF
        s._kopf_speichern(next(f for f in KOPF if f.name == name), wert)
        self.aktualisieren()
        return True

    def fracht_setzen(self, betrag):
        """Frachtbetrag von Hand (€, ganzes Angebot); stellt die Frachtart auf „manuell“, falls sie keine Fracht
        rechnet."""
        from . import fracht_angebot as fa
        s = self.seite
        if s is None:
            return False
        betrag = round(float(betrag or 0), 2) or None
        if betrag == (s.kopf.get("fracht") or None):
            return False
        if betrag and fa.modus(s.kopf) in (fa.KEINE, fa.ENTHALTEN):
            self._kopf_wert("fracht_modus", fa.MANUELL)
        return self._kopf_wert("fracht", betrag)

    def fracht_modus_setzen(self, modus):
        from . import fracht_angebot as fa
        s = self.seite
        if s is None or modus not in fa.MODI or modus == fa.modus(s.kopf):
            return False
        return self._kopf_wert("fracht_modus", modus)

    def fracht_umlage_setzen(self, umlage):
        from . import fracht_angebot as fa
        s = self.seite
        if s is None or umlage not in fa.UMLAGEN or umlage == fa.umlage(s.kopf):
            return False
        return self._kopf_wert("fracht_umlage", umlage)

    def fracht_auto(self, an):
        s = self.seite
        if not self._darf_aendern():
            return False
        s.fracht_auto_setzen(bool(an))
        self.aktualisieren()
        return True

    def fracht_berechnen(self):
        """Dialog „Fracht berechnen“ des Expertenmodus (Paket/Palette, Tarif, Übernehmen setzt „berechnet“)."""
        s = self.seite
        if not self._darf_aendern() or not s.positionen:
            return None
        d = s.fracht_berechnen()
        self.aktualisieren()
        return d

    # -------------------------------------------------------------- Marge (Patrick 25.11.2026, marge.py/Preisleiter)
    def _marge_karte_bauen(self):
        """Marge einstellen: stellt den Gewinn des Angebots über die volle Kalkulation so ein, dass die Marge vom
        Warenwert erreicht wird (AngebotSeite.auf_marge_setzen, wie „Auf Zielmarge setzen“ in der Preisleiter)."""
        k = bs.karte("Marge einstellen")
        zeile = QHBoxLayout()
        zeile.setSpacing(design.ABSTAND_KLEIN)
        self.mg_wert = QDoubleSpinBox()
        self.mg_wert.setRange(0, 90)
        self.mg_wert.setDecimals(1)
        self.mg_wert.setSingleStep(0.5)
        self.mg_wert.setSuffix(" %")
        self.mg_wert.setMinimumWidth(90)
        self.mg_wert.setToolTip(bm.FELD_HILFE["marge"])
        zeile.addWidget(self.mg_wert)
        self.mg_knopf = _knopf("Marge übernehmen", lambda: self.marge_setzen(self.mg_wert.value()),
                               "Gewinn so einstellen, dass die eingetragene Marge erreicht wird (rückgängig möglich)")
        zeile.addWidget(self.mg_knopf)
        self.mg_ziel = _knopf("", lambda: self.marge_setzen(self._satz("zielmarge") * 100),
                              "Marge auf die Zielmarge aus den Einstellungen setzen")
        self.mg_min = _knopf("", lambda: self.marge_setzen(self._satz("mindestmarge") * 100),
                             "Marge auf die Mindestmarge aus den Einstellungen setzen")
        zeile.addWidget(self.mg_ziel)
        zeile.addWidget(self.mg_min)
        zeile.addStretch(1)
        self.mg_text = _label("", "e_klein", umbruch=False)
        zeile.addWidget(self.mg_text)
        k.inhalt.addLayout(zeile)
        k.inhalt.addWidget(_label("Marge = Gewinn ÷ Warenwert. Rabatt, Rundung und Mindestpreis zählen mit; Fracht "
                                  "und Verpackung werden ohne Gewinn durchgereicht.", "e_klein"))
        return k

    def _satz(self, name):
        from . import preisleiter
        return preisleiter._anteil(self.seite.einst if self.seite else {}, name)

    def _marge_fuellen(self):
        from . import rechnen
        s, d = self.seite, self.daten
        if s is None or d is None:
            return
        e = d["ergebnis"]
        if not self.mg_wert.hasFocus():
            self.mg_wert.setValue(round(100 * e["marge"], 1) if e["marge"] is not None else 0)
        darf = self._darf_aendern() and bool(s.positionen)
        for w in (self.mg_wert, self.mg_knopf):
            w.setEnabled(darf)
        for knopf, name, titel in ((self.mg_ziel, "zielmarge", "Zielmarge"), (self.mg_min, "mindestmarge",
                                                                              "Mindestmarge")):
            satz = self._satz(name)
            knopf.setVisible(bool(satz))
            knopf.setEnabled(darf)
            if satz:
                knopf.setText(f"{titel} {bm.zahl(100 * satz, 1)} %")
        g = rechnen._n(s.einst.get("gewinn"))
        self.mg_text.setText(f"Jetzt: Marge {bm.zahl(100 * e['marge'], 1) if e['marge'] is not None else '–'} % · "
                             f"Gewinnzuschlag {bm.zahl(100 * g, 2)} % · Gewinn {bm.euro(e['gewinn'])}")

    def marge_setzen(self, prozent):
        """Marge in % vom Warenwert einstellen; Ergebnis: neuer Gewinnsatz (Anteil) oder None."""
        s = self.seite
        if not self._darf_aendern() or not s.positionen or not prozent or prozent <= 0:
            return None
        if s.stand_optimierung() != "aktuell":
            self.automatisch_rechnen()
            if s.stand_optimierung() != "aktuell":       # nie auf einem veralteten Schnittplan einstellen
                self.f.meldung("Marge nicht eingestellt: der Schnittplan ist nicht aktuell. Bitte zuerst „Neu "
                               "berechnen“ (Schritt 4) und die Hinweise prüfen.", fehler=True)
                return None
        g = s.auf_marge_setzen(float(prozent) / 100)
        self.aktualisieren()
        return g


    # -------------------------------------------------------------- Schritt 4: Kalkulation
    def _kalkulation_bauen(self):
        from .kostenbalken import Kostenbalken
        rolle, v, self.ka_kopf = _seite("Kalkulation", "")
        self.ampel = bs.chip("", "neutral")
        self.kz_leiste = bs.kennzahlleiste([("verkauf", "Verkaufspreis netto", "–"), ("stueck", "Ø Stückpreis", "–"),
                                            ("marge", "Marge", "–"), ("kosten", "Selbstkosten", "–")],
                                           rechts=[self.ampel])
        self.kz_leiste.werte["verkauf"].setObjectName("e_summe")
        for n, t in (("verkauf", "verkauf"), ("marge", "gewinn"), ("kosten", "gesamt")):
            self.kz_leiste.werte[n].setToolTip(bm.FELD_HILFE[t])
            self.kz_leiste.titel[n].setToolTip(bm.FELD_HILFE[t])
        v.addWidget(self.kz_leiste)
        self.ka_hinweise = HinweisListe()
        self.ka_hinweise.loesen.connect(self.loesen)
        v.addWidget(self.ka_hinweise)
        aufbau = bs.karte("Woraus sich der Preis zusammensetzt")
        self.balken = Kostenbalken()
        aufbau.inhalt.addWidget(self.balken)
        self.kostenarten = Aufklapper("Kostenarten anzeigen")
        self.ka_tab = _tabelle(["Kostenart", "Betrag", "Anteil"], dehnen=0, rechts=(1, 2))
        self.kostenarten.lay.addWidget(self.ka_tab)
        aufbau.inhalt.addWidget(self.kostenarten)
        v.addWidget(aufbau)
        je = bs.karte("Preis je Position")
        self.preis_tab = _tabelle(["Pos.", "Bauteil", "Profil", "Stück", "Stückpreis", "Summe"], dehnen=1,
                                  rechts=(3, 4, 5))
        je.inhalt.addWidget(self.preis_tab)
        v.addWidget(je)
        v.addWidget(self._marge_karte_bauen())
        v.addStretch(1)
        return rolle

    def _kalkulation_fuellen(self):
        d = self.daten
        if d is None:
            return
        e = d["ergebnis"]
        aktuell = d["stand"] == "aktuell"
        self.ka_kopf.untertitel.setText("Automatisch berechnet mit der Kalkulation des Pro-Modus." if aktuell else
                                        "Der Schnittplan ist nicht aktuell: Hinweise prüfen oder „Neu berechnen“ "
                                        "(Schritt 3).")
        self.ka_kopf.untertitel.show()
        w = self.kz_leiste.werte
        w["verkauf"].setText(bm.euro(e["verkauf"]))
        w["stueck"].setText(bm.euro(e["verkauf"] / e["teile"]) if e["teile"] else "–")
        w["marge"].setText(f"{bm.zahl(100 * e['marge'], 1)} %" if e["marge"] is not None else "–")
        w["kosten"].setText(bm.euro(e["gesamt"]))
        self.kz_leiste.titel["stueck"].setText(f"Ø Stückpreis ({bm.zahl(e['teile'], 0)} Stück)" if e["teile"]
                                               else "Ø Stückpreis")
        if e.get("stufe"):
            bs.chip_setzen(self.ampel, e["ampel_text"] or e["stufe"], AMPEL_CHIP.get(e["stufe"], "neutral"))
            self.ampel.setToolTip(bm.FELD_HILFE["gewinn"] + "".join("\n• " + x for x in e["gruende"]))
            self.ampel.show()
        else:
            self.ampel.hide()
        self.ka_hinweise.setzen([h for h in d["hinweise"] if h[0] in ("FEHLER", "WARNUNG")])
        self._marge_fuellen()
        g = e["gruppen"]
        farben = iter(design.PREIS_BALKEN)
        teile = []
        for n, titel, _ in bm.GRUPPEN:
            if abs(g[n]) <= 0.004:
                continue
            farbe = design.PREIS_BALKEN_GEWINN[0] if n == "gewinn" else (
                design.PREIS_BALKEN_GEWINN[1] if n == "preis" else next(farben, design.PREIS_BALKEN[-1]))
            teile.append((bm.GRUPPE_TITEL[n], g[n], farbe))
        self.balken.setzen(teile)
        summe = e["verkauf"] or 0
        self.ka_tab.setRowCount(len(teile))
        for r, (t, betrag, _) in enumerate(teile):
            self.ka_tab.setItem(r, 0, _zelle(t, tipp=self._gruppen_tipp(next(n for n, x, _ in bm.GRUPPEN if x == t))))
            self.ka_tab.setItem(r, 1, _zelle(bm.euro(betrag), True))
            self.ka_tab.setItem(r, 2, _zelle(f"{bm.zahl(100 * betrag / summe, 1)} %" if summe else "–", True))
        _hoehe_anpassen(self.ka_tab, 1, 12)
        zeilen, bt = d["zeilen"], d["bauteile"]
        self.preis_tab.setRowCount(len(zeilen))
        for r, z in enumerate(zeilen):
            b = bt[r] if r < len(bt) else {}
            self.preis_tab.setItem(r, 0, _zelle(z.get("pos") or r + 1))
            self.preis_tab.setItem(r, 1, _zelle(b.get("name") or str(z.get("artikel") or "")))
            self.preis_tab.setItem(r, 2, _zelle(" ".join(x for x in (b.get("form"), b.get("profil")) if x)
                                                or b.get("art_text") or ""))
            self.preis_tab.setItem(r, 3, _zelle(z.get("stueck") or "–", True))
            self.preis_tab.setItem(r, 4, _zelle(bm.euro(z.get("preis_teil")), True))
            self.preis_tab.setItem(r, 5, _zelle(bm.euro(z.get("preis_position")), True))
        _hoehe_anpassen(self.preis_tab, 2, 14)

    def _gruppen_tipp(self, gruppe):
        d = self.daten
        zuordnung = {n: g for g, _, namen in bm.GRUPPEN for n in namen}
        teile = [f"{text}: {bm.euro(w)}" for (text, w, _), (_, n, fett) in d["kosten"]
                 if not fett and zuordnung.get(n) == gruppe and abs(w or 0) > 0.004]
        return "\n".join(teile)

    def _punkte(self):
        aus = []
        for p in getattr(self.seite, "_punkte", None) or ():
            try:
                st, text = p[0], p[1]
            except (TypeError, IndexError):
                continue
            if st in ZEICHEN:
                aus.append((st, str(text)))
        return aus

    # -------------------------------------------------------------- Schritt 5: Angebot
    def _angebot_bauen(self):
        self.pdf_knopf = _knopf("Angebot erstellen (PDF)", self.pdf_erstellen, "Angebots-PDF für den Kunden "
                                "erstellen, ablegen und öffnen", haupt=True)
        rolle, v, self.ang_kopf = _seite("Angebot", "Zusammenfassung prüfen, Vorschau ansehen, PDF erstellen.",
                                         [self.pdf_knopf])
        self.ang_box = QBoxLayout(QBoxLayout.LeftToRight)
        self.ang_box.setSpacing(design.ABSTAND + 2)
        links = QVBoxLayout()
        links.setSpacing(design.ABSTAND + 2)
        zus = bs.karte("Zusammenfassung", rechts=[_link("Kunde und Anfrage ändern", lambda: self.zu_schritt(bm.KUNDE))])
        self.ang_werte = bs.wertzeilen([(t, "–") for t in ("Kunde", "Ansprechpartner", "Projekt", "Ihre Anfrage",
                                                            "Lieferzeit", "Positionen", "Stück gesamt")])
        zus.inhalt.addWidget(self.ang_werte)
        zus.inhalt.addWidget(_trenner())
        summe = QHBoxLayout()
        summe.addWidget(_label("Angebotssumme netto", "abschnitt", umbruch=False))
        summe.addStretch(1)
        self.ang_summe = _label("–", "e_summe", umbruch=False)
        summe.addWidget(self.ang_summe)
        zus.inhalt.addLayout(summe)
        links.addWidget(zus)
        pos = bs.karte("Positionen", rechts=[_link("Stückzahlen ändern", lambda: self.zu_schritt(bm.BAUTEILE))])
        self.ang_tab = _tabelle(["Pos.", "Bauteil", "Stück", "Stückpreis", "Summe"], dehnen=1, rechts=(2, 3, 4))
        pos.inhalt.addWidget(self.ang_tab)
        links.addWidget(pos)
        pruef = bs.karte("Prüfung vor dem Angebot")
        self.pruef_platz = QVBoxLayout()
        self.pruef_platz.setSpacing(4)
        pruef.inhalt.addLayout(self.pruef_platz)
        self.pruef = HinweisListe()
        self.pruef.loesen.connect(self.loesen)
        pruef.inhalt.addWidget(self.pruef)
        links.addWidget(pruef)
        zeile = QHBoxLayout()
        zeile.addWidget(_knopf("PDF öffnen", self.pdf_oeffnen, "Zuletzt erstelltes PDF dieses Angebots öffnen"))
        self.mail_knopf = _knopf("Per E-Mail senden …", self.mail, "Angebot als PDF per E-Mail schicken")
        zeile.addWidget(self.mail_knopf)
        zeile.addWidget(_knopf("Angebot speichern", self.speichern, "Jede Änderung ist schon gespeichert; mit "
                               "gemeinsamem Ordner gleich abgleichen"))
        zeile.addStretch(1)
        zeile.addWidget(_knopf("Im Pro-Modus weiterbearbeiten", lambda: umschalten(self.f, bm.EXPERTE),
                               "Staffeln, Rabatte, Sonderfälle: dasselbe Angebot mit allen Funktionen"))
        links.addLayout(zeile)
        links.addStretch(1)
        self.ang_box.addLayout(links, 3)
        vk = bs.karte("Vorschau", rechts=[_knopf("Vorschau aktualisieren", self.vorschau_aktualisieren,
                                                 "Erste Seite des Angebots-PDFs neu zeichnen (Entwurf, nichts wird "
                                                 "abgelegt)")])
        self.pdf_bild = QLabel()
        self.pdf_bild.setObjectName("e_vorschau")
        self.pdf_bild.setAlignment(Qt.AlignCenter)
        self.pdf_bild.setMinimumSize(300, 400)
        self.pdf_bild.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        vk.inhalt.addWidget(self.pdf_bild, 1)
        self.pdf_info = _label("", "e_klein")
        vk.inhalt.addWidget(self.pdf_info)
        vk.setMaximumWidth(520)
        self.ang_box.addWidget(vk, 2)
        v.addLayout(self.ang_box, 1)
        self._vorschau_marke = None
        return rolle

    def _angebot_fuellen(self):
        s, d = self.seite, self.daten
        if s is None or d is None:
            return
        from .angebot import lieferzeit_eingabe
        k = s.kopf or {}
        zeilen, bt = d["zeilen"], d["bauteile"]
        stueck = sum(int(z.get("stueck") or 0) for z in zeilen)
        werte = {"Kunde": (f"{k.get('kunde')} ({k.get('kundennr')})" if k.get("kundennr") else k.get("kunde"))
                 or "noch kein Kunde",
                 "Ansprechpartner": k.get("kunde_ansprech") or "–", "Projekt": k.get("projekt") or "–",
                 "Ihre Anfrage": k.get("kundenreferenz") or "–", "Lieferzeit": lieferzeit_eingabe(k) or "–",
                 "Positionen": str(len(zeilen)), "Stück gesamt": bm.zahl(stueck, 0)}
        for t, w in werte.items():
            self.ang_werte.werte[t].setText(str(w))
        self.ang_werte.werte["Kunde"].setStyleSheet("" if k.get("kunde") or k.get("kundennr") else
                                                    f"color: {_farbe(design.GELB_TEXT)};")
        self.ang_tab.setRowCount(len(zeilen))
        for r, z in enumerate(zeilen):
            self.ang_tab.setItem(r, 0, _zelle(z.get("pos") or r + 1))
            self.ang_tab.setItem(r, 1, _zelle(bt[r]["name"] if r < len(bt) else ""))
            self.ang_tab.setItem(r, 2, _zelle(bm.zahl(z.get("stueck"), 0) if z.get("stueck") else "–", True))
            self.ang_tab.setItem(r, 3, _zelle(bm.euro(z.get("preis_teil")), True))
            self.ang_tab.setItem(r, 4, _zelle(bm.euro(z.get("preis_position")), True))
        _hoehe_anpassen(self.ang_tab, 2, 10)
        e = d["ergebnis"]
        self.ang_summe.setText(bm.euro(e["verkauf"]))
        from . import funktionen
        self.mail_knopf.setVisible(funktionen.an("funktion_angebot_mail", self.db))
        self._pruefliste_fuellen()
        self.pruef.setzen([h for h in d["hinweise"] if h[0] in ("FEHLER", "WARNUNG")])

    def pruefliste(self):
        """Prüfliste vor dem Angebot: [(Text, erfüllt, Schritt)] aus dem Stand der Kalkulation (bereitschaft)."""
        b = self.bereit or {}
        je = b.get("je_schritt") or {}
        e = (self.daten or {}).get("ergebnis") or {}
        return [("Kunde gewählt", je.get(bm.KUNDE) == "ok", bm.KUNDE),
                ("Alle Bauteile vollständig", je.get(bm.BAUTEILE) == "ok", bm.BAUTEILE),
                ("Material, Preise und Fertigung vollständig", je.get(bm.MATERIAL) == "ok", bm.MATERIAL),
                ("Kalkulation aktuell", bool(b.get("gerechnet")), bm.MATERIAL),
                ("Preis wirtschaftlich", e.get("stufe") != "kritisch" and (e.get("verkauf") or 0) > 0, bm.KALKULATION),
                ("Angebots-Check ohne offene Punkte", je.get(bm.KALKULATION) == "ok", bm.KALKULATION)]

    def _pruefliste_fuellen(self):
        _leeren(self.pruef_platz)
        for text, erfuellt, schritt in self.pruefliste():
            z = QWidget()
            h = QHBoxLayout(z)
            h.setContentsMargins(0, 0, 0, 0)
            farbe = design.GRUEN if erfuellt else design.GELB_TEXT
            h.addWidget(_label(f"<span style='color:{_farbe(farbe)}'><b>{'✓' if erfuellt else '!'}</b></span>&nbsp; "
                               f"{text}", umbruch=False))
            h.addStretch(1)
            if not erfuellt:
                h.addWidget(_link(f"Zu Schritt {schritt}", lambda _=False, i=schritt: self.zu_schritt(i)))
            self.pruef_platz.addWidget(z)
        b = self.bereit or {}
        z = bs.hinweisband("Das Angebot ist bereit zur Ausgabe." if b.get("bereit") else
                           "Noch nicht bereit: bitte die markierten Punkte prüfen. Ein PDF lässt sich trotzdem "
                           "erstellen; vorher kommt die Sammelrückfrage wie im Pro-Modus.",
                           "ok" if b.get("bereit") else "warnung")
        self.pruef_platz.addWidget(z)

    def _vorschau_spaeter(self):
        if self.schritt == bm.ANGEBOT and self.isVisible() and self._vorschau_marke != self._kennung():
            self.vorschau_aktualisieren()

    def vorschau_aktualisieren(self):
        """Erste Seite des Angebots-PDFs als Bild (Entwurf in einer temporären Datei, dieselbe Ausgabe wie „Angebot
        erstellen“, aber ohne Ablage, Versandvermerk und Angebots-Check). Ergebnis: Anzahl Seiten oder 0."""
        from . import pdf, pdf_vorschau
        s = self.seite
        self._vorschau_marke = self._kennung()
        if s is None or not s.positionen:
            self.pdf_bild.setPixmap(QPixmap())
            self.pdf_bild.setText("Noch keine Bauteile.")
            self.pdf_info.setText("")
            return 0
        try:
            ang = s.angebot_daten(staffeln=False)
            ordner = Path(tempfile.mkdtemp(prefix="rl_vorschau_"))
            pfad = ordner / "Angebot_Vorschau.pdf"
            pdf.angebot_pdf(str(pfad), s.kopf, s._pdf_sprache(ang), s.einst)
            bilder = pdf_vorschau.seiten_bilder(pfad, breite_px=900)
        except Exception:           # noqa: BLE001 – Vorschau ist Zusatz; „Angebot erstellen“ meldet den Grund
            from . import protokoll
            protokoll.warnung("Einfacher Modus: Angebotsvorschau nicht erstellt")
            bilder = []
        if not bilder:
            self.pdf_bild.setPixmap(QPixmap())
            self.pdf_bild.setText("Vorschau nicht verfügbar.")
            self.pdf_info.setText("")
            return 0
        self._pdf_seite = QPixmap.fromImage(bilder[0])
        breite = max(280, min(480, self.pdf_bild.width() - 8))
        self.pdf_bild.setPixmap(self._pdf_seite.scaledToWidth(breite, Qt.SmoothTransformation))
        self.pdf_info.setText(f"Entwurf, Seite 1 von {len(bilder)}. Staffelpreise und die endgültige Nummer kommen "
                              "mit „Angebot erstellen (PDF)“.")
        return len(bilder)

    def pdf_erstellen(self):
        if self.seite is None:
            return None
        pfad = self.seite.angebot_pdf(oeffnen=not self.f.stumm)
        if pfad:
            self.f.meldung(f"Angebot erstellt: {pfad}")
        self.aktualisieren()
        return pfad

    def pdf_oeffnen(self):
        from . import aktionen
        if self.seite is None:
            return None
        self.f.reiter.setCurrentWidget(self.seite)      # aktionen.angebot() sucht das sichtbare Angebot
        return aktionen._pdf_oeffnen(self.f)

    def mail(self):
        if self.seite is None:
            return None
        return self.seite.angebot_mail()

    def speichern(self):
        from . import aktionen
        if self.seite is not None:
            self.f.reiter.setCurrentWidget(self.seite)
        return aktionen._speichern(self.f)


# ------------------------------------------------------------------ Hauptfenster
class ModusStapel(QStackedWidget):
    """Stapel aus Experten- und einfacher Oberfläche: nur die sichtbare bestimmt die Mindestgröße (verdeckt: Regel
    „Ignored“ waagrecht und senkrecht, wie einstellungen_nav.SeitenStapel), sonst würde das Fenster für die
    unsichtbare Oberfläche größer oder enger (maximiertes Fenster bleibt unverändert)."""

    def __init__(self):
        super().__init__()
        self._regel = {}
        self.currentChanged.connect(self._regeln)
        self.widgetAdded.connect(self._regeln)

    def _regeln(self, _=None):
        for i in range(self.count()):
            w = self.widget(i)
            alt = self._regel.setdefault(id(w), (w.sizePolicy().horizontalPolicy(), w.sizePolicy().verticalPolicy()))
            r = w.sizePolicy()
            h, v = alt if w is self.currentWidget() else (QSizePolicy.Ignored, QSizePolicy.Ignored)
            if (r.horizontalPolicy(), r.verticalPolicy()) != (h, v):
                r.setHorizontalPolicy(h)
                r.setVerticalPolicy(v)
                w.setSizePolicy(r)
        self.updateGeometry()


def einrichten(f):
    """Einfachen Modus ans Hauptfenster hängen: zentrales Widget = Stapel aus Expertenoberfläche (f.reiter, unverändert)
    und einfacher Oberfläche; Schnellwechsel in Statusleiste, Menü Ansicht und per Taste; Modus des Benutzers
    anwenden."""
    alt = f.takeCentralWidget()
    f.modus_stapel = ModusStapel()
    f.modus_stapel.addWidget(alt)
    f.einfach = EinfachBereich(f)
    f.modus_stapel.addWidget(f.einfach)
    f.setCentralWidget(f.modus_stapel)
    f.modus_knopf = QToolButton()
    f.modus_knopf.setAutoRaise(True)
    f.modus_knopf.setToolTip(f"Bedienoberfläche wechseln ({TASTE.replace('Ctrl', 'Strg')}); gilt nur für Sie an diesem "
                             "Arbeitsplatz")
    f.modus_knopf.clicked.connect(lambda: umschalten(f))
    f.statusBar().addPermanentWidget(f.modus_knopf)
    f.modus_taste = QShortcut(QKeySequence(TASTE), f)
    f.modus_taste.setContext(Qt.ApplicationShortcut)
    f.modus_taste.activated.connect(lambda: umschalten(f))
    f.modus = None
    anwenden(f, bm.modus(f.db))


def umschalten(f, neu=None):
    """Zwischen den Modi wechseln (neu=None: zum jeweils anderen) und für diesen Benutzer merken. Die geöffnete
    Kalkulation bleibt geöffnet und erscheint im anderen Modus."""
    neu = neu or (bm.EXPERTE if getattr(f, "modus", None) == bm.EINFACH else bm.EINFACH)
    if neu != bm.modus(f.db):
        bm.setzen(f.db, neu)
    anwenden(f, neu)
    seite = getattr(f, "bedienmodus_seite", None)
    if seite is not None:
        seite.neu_laden()
    return neu


def anwenden(f, neu):
    """Oberfläche des Modus zeigen, ohne Daten oder Eingaben zu verlieren: nur das sichtbare Widget, Menüleiste,
    Werkzeugleiste und Info-Panel wechseln."""
    if not hasattr(f, "modus_stapel"):
        return None
    alt = getattr(f, "modus", None)
    e = f.einfach
    if neu == bm.EINFACH:
        aktuell = f.reiter.currentWidget()
        if aktuell in getattr(f, "offen", {}).values() and aktuell is not e.seite:
            e.seite_setzen(aktuell, e.schritt if e.schritt > bm.START else bm.BAUTEILE)
        f.modus = neu
        f.modus_stapel.setCurrentWidget(e)
        e.aktualisieren()
    else:
        f.modus = neu
        f.modus_stapel.setCurrentIndex(0)
        if alt == bm.EINFACH and e.seite is not None and e.seite in getattr(f, "offen", {}).values():
            f.reiter.setCurrentWidget(e.seite)        # dieselbe Kalkulation gleich vorne
    oberflaeche_anpassen(f)
    f.modus_knopf.setText(f"⇄ {bm.TITEL[neu]}")
    aktion = getattr(f, "modus_aktion", None)
    if aktion is not None:
        try:                            # Menüpunkt kann fehlen (Menü neu aufgebaut): Umschalten geht trotzdem
            aktion.blockSignals(True)
            aktion.setChecked(neu == bm.EINFACH)
            aktion.blockSignals(False)
        except RuntimeError:
            f.modus_aktion = None
    if alt is not None and alt != neu:
        f.meldung(f"{bm.TITEL[neu]} – gilt für Sie an diesem Arbeitsplatz. Umschalten: {TASTE.replace('Ctrl', 'Strg')} "
                  "oder unten rechts.")
    return neu


def oberflaeche_anpassen(f):
    """Menüleiste, „Meine Werkzeugleiste“ und Info-Panel nur im Experten-Pro-Modus (nach jeder Änderung der Leiste
    aufgerufen: werkzeugleiste_qt.aendern/zustand_laden schalten sie sonst wieder ein)."""
    einfach = getattr(f, "modus", None) == bm.EINFACH
    if not hasattr(f, "modus_stapel"):
        return
    f.menuBar().setVisible(not einfach)
    leiste, dock = getattr(f, "meine_leiste", None), getattr(f, "info_dock", None)
    if einfach:
        for w in (leiste, dock):
            if w is not None:
                w.setVisible(False)
    else:
        from . import werkzeugleiste as wl
        if leiste is not None:
            leiste.setVisible(leiste.aufbau.get("sichtbar", True))
        if dock is not None:
            dock.setVisible(wl.info_an(f.db))


def benutzer_pruefen(f):
    """Nach An-/Abmelden eines Benutzers: dessen Bedienmodus anwenden (jeder Mitarbeiter seine Oberfläche)."""
    if hasattr(f, "modus_stapel") and bm.modus(f.db) != getattr(f, "modus", None):
        anwenden(f, bm.modus(f.db))


def menue_eintrag(f, menue):
    """Menü Ansicht: „Einfacher Modus“ zum Ankreuzen (Experten-Pro-Modus = ohne Haken)."""
    a = menue.addAction("Einfacher Modus")
    a.setCheckable(True)
    a.setToolTip("Geführte Kalkulation in fünf Schritten; ohne Haken: Experten-Pro-Modus")
    a.toggled.connect(lambda an: umschalten(f, bm.EINFACH if an else bm.EXPERTE))
    f.modus_aktion = a
    return a

