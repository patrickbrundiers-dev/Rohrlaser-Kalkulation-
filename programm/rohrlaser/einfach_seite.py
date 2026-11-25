"""Einfacher Modus: geführte Kalkulation in sechs Schritten (Patrick 25.11.2026, Master-Auftrag „Vereinfachten
Bedienmodus implementieren“).

Eine eigenständige Oberfläche neben dem Experten-Pro-Modus, aber KEIN zweites Kalkulationssystem: Jede Kalkulation
ist ein ganz normales Angebot. Die Seite arbeitet immer auf der Angebotsseite (angebot_fenster.AngebotSeite), die
auch der Expertenmodus zeigt (Hauptfenster.offen), und ruft deren vorhandene Funktionen auf: STEP-Import mit
Prüfdialog, CAD-Import, Bauteilbibliothek, Werkstoff setzen, Material und Materialkosten, Zusatzarbeiten,
Vorschläge, Optimieren, Kunde wählen, Angebots-PDF. Zahlen kommen aus derselben Rechnung (AngebotSeite._rechnung =
rechnen.kalkulation), Marge und Ampel wie die Kachel „Gewinn und Marge“ (bedienmodus.ergebnis). Der Moduswechsel
tauscht nur die sichtbare Oberfläche: die Angebotsseiten, Eingaben und Rechnungen bleiben dieselben Objekte.

Aufbau: Kopf (Titel, Schrittleiste 1–6, Hilfe, Expertenmodus) · Schrittseite · Hilfebereich · Fuß (Zurück, nächster
Schritt, Weiter). Umschalten: Einstellungen → Darstellung und Bedienoberfläche, Menü Ansicht, Statusleiste oder
Strg+Alt+M (einrichten, umschalten).
"""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton, QScrollArea,
                               QSizePolicy, QSpinBox, QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem,
                               QToolButton, QVBoxLayout, QWidget)

from . import bedienmodus as bm
from . import stil

GRAU, AKZENT = "#5F6B7A", "#1F4E78"
FARBE_STUFE = {"FEHLER": "#B42318", "WARNUNG": "#B35C00", "HINWEIS": "#1F4E78", "OK": "#1E6B34"}
FLAECHE_STUFE = {"FEHLER": "#FDECEA", "WARNUNG": "#FFF4CE", "HINWEIS": "#EEF4FB", "OK": "#E3F4E8"}
AMPEL = {"gut": "#1E6B34", "knapp": "#B35C00", "kritisch": "#B42318"}
ZEICHEN = {"FEHLER": "●", "WARNUNG": "▲", "HINWEIS": "ℹ", "OK": "✓"}
PRUEF_TAKT_MS = 1200        # so oft schaut die sichtbare Seite nach, ob sich das Angebot geändert hat (billig)
TASTE = "Ctrl+Alt+M"        # Moduswechsel (Strg+Umschalt+M ist die Materialanfrage)

# Farben nur aus der Hell-Palette mit Dunkel-Entsprechung (stil.UMSETZUNG): setStyleSheet setzt sie um
STIL = """
QWidget#einfach { background: #F5F7FA; }
QFrame#e_kopf, QFrame#e_fuss { background: #FFFFFF; border: none; }
QFrame#e_kopf { border-bottom: 1px solid #D5DBE3; }
QFrame#e_fuss { border-top: 1px solid #D5DBE3; }
QLabel#e_titel { font-size: 15pt; font-weight: 600; color: #1F2937; }
QLabel#e_seitentitel { font-size: 17pt; font-weight: 600; color: #1F2937; }
QLabel#e_unter, QLabel#e_klein { color: #5F6B7A; }
QPushButton#e_schritt { border: 1px solid transparent; border-radius: 15px; padding: 5px 12px; color: #5F6B7A;
                        background: transparent; font-weight: 600; }
QPushButton#e_schritt:hover { background: #EEF4FB; }
QPushButton#e_schritt:checked { background: #1F4E78; color: #FFFFFF; }
QPushButton#e_schritt:disabled { color: #9AA3AF; }
QFrame#e_karte { background: #FFFFFF; border: 1px solid #E3E7EC; border-radius: 10px; }
QFrame#e_karte_akzent { background: #DDEBF7; border: 1px solid #C9DAEE; border-radius: 10px; }
QLabel#e_karten_titel { font-size: 11pt; font-weight: 600; color: #1F2937; }
QLabel#e_wert_titel { color: #5F6B7A; font-weight: 600; }
QLabel#e_zahl { font-size: 18pt; font-weight: 700; color: #1F2937; }
QLabel#e_zahl_gross { font-size: 24pt; font-weight: 700; color: #1F4E78; }
QToolButton#e_kachel { background: #FFFFFF; border: 1px solid #D5DBE3; border-radius: 12px; padding: 12px;
                       font-size: 11pt; font-weight: 600; color: #1F2937; text-align: left; }
QToolButton#e_kachel:hover { border-color: #1F4E78; background: #EEF4FB; }
QPushButton#primaer, QPushButton#e_gross { min-height: 34px; padding: 6px 16px; font-size: 10.5pt; }
QPushButton#e_riesig { min-height: 52px; padding: 8px 28px; font-size: 13pt; font-weight: 700;
                       background: #1F4E78; color: #FFFFFF; border: 1px solid #183E60; border-radius: 8px; }
QPushButton#e_riesig:hover { background: #183E60; }
QFrame#e_hilfe { background: #EEF4FB; border: 1px solid #C9DAEE; border-radius: 10px; }
QTableWidget#e_tabelle { background: #FFFFFF; border: none; gridline-color: #E3E7EC; }
QTableWidget#e_tabelle::item { padding: 4px 6px; }
QListWidget#e_liste { background: #FFFFFF; border: 1px solid #E3E7EC; border-radius: 8px; }
QListWidget#e_liste::item { padding: 8px 6px; border-bottom: 1px solid #E3E7EC; }
QListWidget#e_liste::item:selected { background: #DDEBF7; color: #1F2937; }
"""


# ------------------------------------------------------------------ Bausteine
def _label(text="", name=None, umbruch=True):
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(umbruch)
    lb.setTextFormat(Qt.RichText)
    return lb


def _farbe(hell):
    return stil.umsetzen(hell)


class Karte(QFrame):
    """Weiße Fläche mit runden Ecken und optionalem Titel; lay = Inhalt."""

    def __init__(self, titel="", akzent=False, parent=None):
        super().__init__(parent)
        self.setObjectName("e_karte_akzent" if akzent else "e_karte")
        aussen = QVBoxLayout(self)
        aussen.setContentsMargins(16, 12, 16, 14)
        aussen.setSpacing(8)
        self.titel = _label(titel, "e_karten_titel") if titel else None
        if self.titel is not None:
            aussen.addWidget(self.titel)
        self.lay = QVBoxLayout()
        self.lay.setSpacing(6)
        aussen.addLayout(self.lay, 1)


class Kennzahl(Karte):
    """Kennzahl-Kachel: Titel, große Zahl, kurze Erklärung (Tooltip = ausführlich)."""

    def __init__(self, titel, hilfe="", gross=False, akzent=False):
        super().__init__("", akzent=akzent)
        self.kopf = _label(titel, "e_wert_titel")
        self.zahl = _label("–", "e_zahl_gross" if gross else "e_zahl", umbruch=False)
        self.unter = _label("", "e_klein")
        for w in (self.kopf, self.zahl, self.unter):
            self.lay.addWidget(w)
        self.lay.addStretch(1)
        self.setToolTip(hilfe)
        self.setMinimumWidth(170)

    def setzen(self, zahl, unter="", farbe=None, tipp=None):
        self.zahl.setText(zahl)
        self.zahl.setStyleSheet(f"color: {farbe};" if farbe else "")
        self.unter.setText(unter)
        self.unter.setVisible(bool(unter))
        if tipp is not None:
            self.setToolTip(tipp)


class Raster(QWidget):
    """Kacheln in so vielen Spalten, wie in die Breite passen (min_breite je Kachel): passt sich jeder
    Bildschirmgröße an, ohne waagerechten Rollbalken."""

    def __init__(self, min_breite=230, abstand=12, parent=None):
        super().__init__(parent)
        self.min_breite, self.kacheln, self._spalten = min_breite, [], 0
        self.gitter = QGridLayout(self)
        self.gitter.setContentsMargins(0, 0, 0, 0)
        self.gitter.setSpacing(abstand)

    def setzen(self, kacheln):
        for w in self.kacheln:
            self.gitter.removeWidget(w)
            if w not in kacheln:
                w.setParent(None)
                w.deleteLater()
        self.kacheln = list(kacheln)
        self._spalten = 0
        self._anordnen()

    def _anordnen(self):
        n = max(1, min(len(self.kacheln) or 1, max(self.width(), self.min_breite) // self.min_breite))
        if n == self._spalten:
            return
        self._spalten = n
        for w in self.kacheln:
            self.gitter.removeWidget(w)
        for i, w in enumerate(self.kacheln):
            self.gitter.addWidget(w, i // n, i % n)
        for c in range(self.gitter.columnCount()):
            self.gitter.setColumnStretch(c, 1 if c < n else 0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._anordnen()


class Balken(QWidget):
    """Kostenaufteilung als ein waagerechter Balken (Anteile der Kostengruppen am Verkaufspreis)."""
    FARBEN = ("#1F4E78", "#5B8DB8", "#B35C00", "#7F8A99", "#1E6B34", "#B07AA1", "#76B7B2")

    def __init__(self):
        super().__init__()
        self.teile = []
        self.setMinimumHeight(22)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def setzen(self, teile):
        self.teile = [(t, w) for t, w in teile if w > 0]
        self.setToolTip("\n".join(f"{t}: {bm.euro(w)}" for t, w in self.teile))
        self.update()

    def paintEvent(self, _):
        summe = sum(w for _, w in self.teile)
        if summe <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        x, b = 0.0, self.width()
        for i, (_, w) in enumerate(self.teile):
            breite = b * w / summe
            p.fillRect(int(x), 0, int(breite + 1), self.height(), stil.farbe(self.FARBEN[i % len(self.FARBEN)]))
            x += breite
        p.end()


def _kachel(titel, text, symbol, aufruf):
    k = QToolButton()
    k.setObjectName("e_kachel")
    k.setText(f"{titel}\n{text}")
    k.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    k.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    k.setMinimumHeight(84)
    k.setIconSize(QSize(34, 34))
    k.setToolTip(text)
    try:
        from . import symbole
        k.setIcon(symbole.symbol(symbol, AKZENT))
    except Exception:           # noqa: BLE001 – ohne Symbol
        pass
    k.clicked.connect(aufruf)
    return k


def _knopf(text, aufruf, tipp="", art="e_gross"):
    b = QPushButton(text)
    b.setObjectName(art)
    b.setToolTip(tipp)
    b.clicked.connect(aufruf)
    return b


def _scroll(inhalt):
    s = QScrollArea()
    s.setWidgetResizable(True)
    s.setFrameShape(QFrame.NoFrame)
    s.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    s.setWidget(inhalt)
    inhalt.setObjectName("einfach")
    return s


def _zelle(text, rechts=False, tipp=""):
    it = QTableWidgetItem(str(text))
    it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    if rechts:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if tipp:
        it.setToolTip(tipp)
    return it


def _tabelle(spalten):
    t = QTableWidget(0, len(spalten))
    t.setObjectName("e_tabelle")
    t.setHorizontalHeaderLabels(spalten)
    t.verticalHeader().setVisible(False)
    t.verticalHeader().setDefaultSectionSize(40)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setAlternatingRowColors(False)
    t.setWordWrap(False)
    t.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    t.horizontalHeader().setStretchLastSection(False)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    return t


class HinweisListe(QWidget):
    """Hinweise mit Lösung: je Zeile Symbol, verständlicher Text und ein Knopf, der die Lösung öffnet."""
    loesen = Signal(str, object)        # Aktion, Zeile

    TEXT = {"stueck": "Stück eintragen", "material": "Zum Material", "editor": "Im Editor prüfen",
            "zukauf": "Preis eintragen", "optimieren": "Neu berechnen", "experte": "Im Expertenmodus öffnen",
            "kunde": "Kunde wählen", "import": "Bauteil importieren"}

    def __init__(self):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(6)
        self.zeilen = []

    def setzen(self, hinweise, max_anzahl=8):
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.zeilen = list(hinweise)
        if not hinweise:
            ok = _label(f"<span style='color:{_farbe(FARBE_STUFE['OK'])}'><b>✓ Alles vollständig.</b></span> "
                        "Keine fehlenden Angaben.")
            self.lay.addWidget(ok)
            return
        for st, text, aktion, zeile in hinweise[:max_anzahl]:
            z = QFrame()
            z.setStyleSheet(f"QFrame {{ background: {FLAECHE_STUFE[st]}; border-radius: 6px; }}")
            h = QHBoxLayout(z)
            h.setContentsMargins(10, 6, 6, 6)
            lb = _label(f"<span style='color:{FARBE_STUFE[st]}'><b>{ZEICHEN[st]}</b></span>&nbsp; {text}")
            lb.setStyleSheet("background: transparent;")
            h.addWidget(lb, 1)
            if aktion in self.TEXT:
                b = QPushButton(self.TEXT[aktion])
                b.clicked.connect(lambda _=False, a=aktion, r=zeile: self.loesen.emit(a, r))
                h.addWidget(b)
            self.lay.addWidget(z)
        if len(hinweise) > max_anzahl:
            self.lay.addWidget(_label(f"… und {len(hinweise) - max_anzahl} weitere.", "e_klein"))


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
        self._marke = None
        self._gefuellt = set()
        self.setObjectName("einfach")
        self.setStyleSheet(STIL)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._kopf_bauen())
        mitte = QHBoxLayout()
        mitte.setContentsMargins(0, 0, 0, 0)
        mitte.setSpacing(0)
        self.stapel = QStackedWidget()
        self.seiten = [self._start_bauen(), self._bauteile_bauen(), self._material_bauen(), self._bearbeitung_bauen(),
                       self._ergebnis_bauen(), self._angebot_bauen()]
        for s in self.seiten:
            self.stapel.addWidget(s)
        mitte.addWidget(self.stapel, 1)
        mitte.addWidget(self._hilfe_bauen())
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
        h.setContentsMargins(16, 8, 12, 8)
        h.setSpacing(6)
        links = QVBoxLayout()
        links.setSpacing(0)
        self.titel = _label("Kalkulation", "e_titel", umbruch=False)
        self.untertitel = _label("Einfacher Modus", "e_unter", umbruch=False)
        links.addWidget(self.titel)
        links.addWidget(self.untertitel)
        h.addLayout(links)
        h.addStretch(1)
        self.schritt_knoepfe = []
        for i, (_, titel, kurz, _) in enumerate(bm.SCHRITTE):
            b = QPushButton(f"{i + 1}  {titel}")
            b.setObjectName("e_schritt")
            b.setCheckable(True)
            b.setToolTip(kurz)
            b.clicked.connect(lambda _=False, i=i: self.zu_schritt(i))
            self.schritt_knoepfe.append(b)
            h.addWidget(b)
        h.addStretch(1)
        self.hilfe_knopf = QPushButton("? Hilfe")
        self.hilfe_knopf.setCheckable(True)
        self.hilfe_knopf.setToolTip("Erklärungen zum aktuellen Schritt ein- oder ausblenden")
        self.hilfe_knopf.toggled.connect(lambda an: self.hilfe_zeigen(an, merken=True))
        h.addWidget(self.hilfe_knopf)
        self.experte_knopf = QPushButton("Expertenmodus")
        self.experte_knopf.setToolTip(f"Zur vollständigen Arbeitsumgebung wechseln (dieselbe Kalkulation, {TASTE.replace('Ctrl', 'Strg')})")
        self.experte_knopf.clicked.connect(lambda: umschalten(self.f, bm.EXPERTE))
        h.addWidget(self.experte_knopf)
        return kopf

    def _hilfe_bauen(self):
        self.hilfe = QFrame()
        self.hilfe.setObjectName("e_hilfe")
        self.hilfe.setFixedWidth(280)
        v = QVBoxLayout(self.hilfe)
        v.setContentsMargins(14, 12, 14, 12)
        self.hilfe_titel = _label("", "e_karten_titel")
        self.hilfe_text = _label("")
        self.hilfe_text.setStyleSheet("background: transparent;")
        v.addWidget(self.hilfe_titel)
        v.addWidget(self.hilfe_text)
        v.addSpacing(8)
        self.hilfe_felder = _label("", "e_klein")
        self.hilfe_felder.setStyleSheet("background: transparent;")
        v.addWidget(self.hilfe_felder)
        v.addStretch(1)
        anleitung = QPushButton("Bedienungsanleitung öffnen")
        anleitung.setToolTip("Kapitel „Einfacher Modus“ der Bedienungsanleitung (PDF)")
        anleitung.clicked.connect(lambda: self.f.anleitung_oeffnen() if hasattr(self.f, "anleitung_oeffnen") else None)
        v.addWidget(anleitung)
        aussen = QWidget()
        a = QVBoxLayout(aussen)
        a.setContentsMargins(0, 12, 12, 12)
        a.addWidget(self.hilfe)
        self._hilfe_aussen = aussen
        return aussen

    def hilfe_zeigen(self, an, merken=False):
        self._hilfe_aussen.setVisible(bool(an))
        if self.hilfe_knopf.isChecked() != bool(an):
            self.hilfe_knopf.blockSignals(True)
            self.hilfe_knopf.setChecked(bool(an))
            self.hilfe_knopf.blockSignals(False)
        if merken:
            bm.hilfe_setzen(self.db, an)

    FELDER_JE_SCHRITT = {bm.BAUTEILE: ("stueck", "profil", "laenge"), bm.MATERIAL: ("werkstoff", "preis_m", "verfuegbar"),
                         bm.BEARBEITUNG: ("maschinenzeit", "schnitt", "ruesten", "zusatz", "zukauf", "gemein",
                                          "fracht"),
                         bm.ERGEBNIS: ("gesamt", "verkauf", "gewinn", "marge")}
    FELD_TITEL = {"stueck": "Stück", "profil": "Querschnitt", "laenge": "Länge", "werkstoff": "Werkstoff",
                  "preis_m": "Preis je Meter", "verfuegbar": "Verfügbarkeit", "maschinenzeit": "Maschinenzeit",
                  "schnitt": "Schnittkosten", "ruesten": "Rüstkosten", "zusatz": "Zusatzarbeiten",
                  "zukauf": "Zukaufteile", "gemein": "Gemeinkosten", "gesamt": "Gesamtkosten",
                  "verkauf": "Verkaufspreis", "gewinn": "Gewinn und Marge",
                  "fracht": "Frachtkosten", "marge": "Marge einstellen"}

    def _hilfe_setzen(self):
        _, titel, kurz, lang = bm.SCHRITTE[self.schritt]
        self.hilfe_titel.setText(f"Schritt {self.schritt + 1}: {titel}")
        self.hilfe_text.setText(lang)
        felder = self.FELDER_JE_SCHRITT.get(self.schritt, ())
        self.hilfe_felder.setText("".join(f"<p><b>{self.FELD_TITEL[n]}</b>: {bm.FELD_HILFE[n]}</p>" for n in felder))

    def _fuss_bauen(self):
        fuss = QFrame()
        fuss.setObjectName("e_fuss")
        h = QHBoxLayout(fuss)
        h.setContentsMargins(16, 8, 16, 8)
        self.zurueck = _knopf("‹ Zurück", lambda: self.zu_schritt(self.schritt - 1), "Vorheriger Schritt")
        self.weiter = _knopf("Weiter ›", lambda: self.zu_schritt(self.schritt + 1), "Nächster Schritt", "primaer")
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
        for n, b in enumerate(self.schritt_knoepfe):
            b.setChecked(n == i)
            b.setEnabled(n == bm.START or self.seite is not None)
        self.stapel.setCurrentIndex(i)
        if i in (bm.BEARBEITUNG, bm.ERGEBNIS, bm.ANGEBOT):
            self.automatisch_rechnen()
        self.aktualisieren(nur_seite=True)
        self._hilfe_setzen()
        return i

    def _seite_weg(self):
        """Die bearbeitete Angebotsseite wurde (im Expertenmodus) geschlossen: zurück zum Start."""
        if self.seite is not None and self.seite not in getattr(self.f, "offen", {}).values():
            self.seite = None
        return self.seite is None

    def seite_setzen(self, seite, schritt=bm.BAUTEILE):
        """Diese AngebotSeite im einfachen Modus bearbeiten (gleiche Seite wie im Expertenmodus)."""
        self.seite = seite
        self._marke = None
        if seite is not None:
            self.zu_schritt(schritt)
        else:
            self.zu_schritt(bm.START)
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
        hinw = bm.hinweise(bauteile, s.kopf, s.stand_optimierung(), erg, fehler_einplanen)
        kosten = list(zip(rechnen.kostenarten(summen, s.einst), rechnen.KOSTENARTEN))
        return dict(bauteile=bauteile, zeilen=zeilen, summen=summen, ergebnis=erg, hinweise=hinw, kosten=kosten,
                    zeiten=zs, stand=s.stand_optimierung())

    def aktualisieren(self, nur_seite=False):
        neu = self._kennung()
        if neu != self._marke or self.daten is None and self.seite is not None:
            self._marke = neu
            self._gefuellt = set()
            try:
                self.daten = self.daten_lesen()
            except Exception:       # noqa: BLE001 – Anzeige; der Expertenmodus zeigt denselben Stand
                from . import protokoll
                protokoll.warnung("Einfacher Modus: Daten des Angebots nicht lesbar")
                self.daten = None
        if self.schritt not in self._gefuellt:
            self._gefuellt.add(self.schritt)
            (self._start_fuellen, self._bauteile_fuellen, self._material_fuellen, self._bearbeitung_fuellen,
             self._ergebnis_fuellen, self._angebot_fuellen)[self.schritt]()
        self._kopf_fuellen()

    def _kopf_fuellen(self):
        s = self.seite
        if s is None:
            self.titel.setText("Kalkulation")
            self.untertitel.setText("Einfacher Modus · noch keine Kalkulation geöffnet")
        else:
            k = s.kopf or {}
            self.titel.setText(f"Angebot {k.get('nummer') or s.id}")
            self.untertitel.setText(" · ".join(x for x in (k.get("kunde") or "ohne Kunde",
                                                            f"{len(s.positionen)} Bauteil(e)") if x))
        d = self.daten if s is not None else None
        hinw = d["hinweise"] if d else []
        self.fuehrung.setText(bm.naechster_schritt(self.schritt, hinw, s is not None))
        self.zurueck.setEnabled(self.schritt > bm.START)
        self.weiter.setVisible(self.schritt < bm.ANGEBOT)
        self.weiter.setEnabled(s is not None)

    # -------------------------------------------------------------- Schritt 1: Start
    def _start_bauen(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(14)
        self.willkommen = QFrame()
        self.willkommen.setObjectName("e_hilfe")
        wh = QHBoxLayout(self.willkommen)
        wh.setContentsMargins(14, 10, 10, 10)
        wl = _label("<b>Willkommen im einfachen Modus.</b> In sechs Schritten zum Angebot: Bauteil importieren → "
                    "prüfen → Material → Bearbeitung → Ergebnis → Angebot. Unten führt „Weiter“ durch den Ablauf, "
                    "rechts erklärt die Hilfe jeden Schritt. Alles bleibt auch im Expertenmodus vollständig "
                    "bearbeitbar.")
        wl.setStyleSheet("background: transparent;")
        wh.addWidget(wl, 1)
        aus = QPushButton("Ausblenden")
        aus.clicked.connect(self._willkommen_aus)
        wh.addWidget(aus, 0, Qt.AlignTop)
        v.addWidget(self.willkommen)
        self.willkommen.setVisible(bm.willkommen_an(self.db))
        titel = _label("Was möchten Sie tun?", "e_seitentitel")
        v.addWidget(titel)
        self.neu_knopf = _knopf("＋  Neue Kalkulation erstellen", self.neu_zeigen,
                                "Neue Kalkulation aus einer STEP- oder CAD-Datei oder aus einem gespeicherten "
                                "Bauteil", "e_riesig")
        self.neu_knopf.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        v.addWidget(self.neu_knopf)
        self.wege = Raster(min_breite=260)
        self.wege.setzen([
            _kachel("STEP-Datei importieren", "3D-Modell (STEP, IGES, ZIP) lesen und automatisch erkennen", "step",
                    lambda: self.neu_aus_step()),
            _kachel("CAD-Datei importieren", "DXF, TRUMPF LST, BLM ArTube/BPF", "kontur", lambda: self.neu_aus_cad()),
            _kachel("Vorhandenes Bauteil auswählen", "Aus der Bauteilbibliothek (gespeicherte Vorlagen)", "liste",
                    lambda: self.neu_aus_vorlage()),
            _kachel("Bestehende Kalkulation öffnen", "Angebot suchen und weiterbearbeiten", "oeffnen",
                    lambda: self.oeffnen_suchen()),
        ])
        self.wege.setVisible(False)
        v.addWidget(self.wege)
        self.weiter_karte = Karte("Aktuelle Kalkulation", akzent=True)
        self.weiter_text = _label("")
        self.weiter_text.setStyleSheet("background: transparent;")
        self.weiter_karte.lay.addWidget(self.weiter_text)
        self.weiter_karte.lay.addWidget(_knopf("Weiterbearbeiten ›", lambda: self.zu_schritt(bm.BAUTEILE), "",
                                               "primaer"), 0, Qt.AlignLeft)
        v.addWidget(self.weiter_karte)
        liste = Karte("Zuletzt bearbeitet")
        self.suche = QLineEdit()
        self.suche.setPlaceholderText("Angebot suchen: Nummer, Kunde, Artikel …")
        self.suche.setClearButtonEnabled(True)
        self.suche.setMinimumHeight(32)
        self.suche.textChanged.connect(lambda _: self._liste_fuellen())
        self.suche.returnPressed.connect(self._liste_oeffnen)
        liste.lay.addWidget(self.suche)
        self.liste = QListWidget()
        self.liste.setObjectName("e_liste")
        self.liste.setMinimumHeight(220)
        self.liste.itemActivated.connect(lambda it: self.oeffnen(it.data(Qt.UserRole)))
        liste.lay.addWidget(self.liste, 1)
        liste.lay.addWidget(_knopf("Öffnen", self._liste_oeffnen, "Gewählte Kalkulation öffnen"), 0, Qt.AlignRight)
        v.addWidget(liste, 1)
        return _scroll(w)

    def _willkommen_aus(self):
        bm.willkommen_aus(self.db)
        self.willkommen.hide()

    def neu_zeigen(self):
        self.wege.setVisible(True)
        return True

    def _start_fuellen(self):
        aktiv = self.seite is not None and not self._seite_weg()
        self.weiter_karte.setVisible(aktiv)
        if aktiv:
            k = self.seite.kopf or {}
            self.weiter_text.setText(f"<b>Angebot {k.get('nummer') or self.seite.id}</b> · "
                                     f"{k.get('kunde') or 'ohne Kunde'} · {len(self.seite.positionen)} Bauteil(e)")
        self._liste_fuellen()

    def _liste_fuellen(self):
        text = self.suche.text().strip()
        try:
            zeilen = self.db.angebote(text) if text else self.db.angebote()
        except Exception:           # noqa: BLE001
            zeilen = []
        zeilen = sorted(zeilen, key=lambda z: str(z.get("geaendert") or ""), reverse=True)[:40]
        self.liste.clear()
        for z in zeilen:
            vk = z.get("vk_netto")
            teile = [str(z.get("nummer") or f"Angebot {z['id']}"), z.get("kunde") or "ohne Kunde",
                     z.get("vorgang") or "Entwurf"]
            if isinstance(vk, (int, float)):
                teile.append(bm.euro(vk))
            it = QListWidgetItem("   ·   ".join(teile))
            it.setData(Qt.UserRole, z["id"])
            it.setToolTip(f"Zuletzt geändert: {str(z.get('geaendert') or '')[:16]}")
            self.liste.addItem(it)
        if not zeilen:
            self.liste.addItem(QListWidgetItem("Keine Kalkulation gefunden." if text else "Noch keine Kalkulationen."))

    def _liste_oeffnen(self):
        it = self.liste.currentItem() or (self.liste.item(0) if self.liste.count() == 1 else None)
        if it is not None and it.data(Qt.UserRole) is not None:
            return self.oeffnen(it.data(Qt.UserRole))
        self.f.meldung("Bitte eine Kalkulation in der Liste wählen.", fehler=True)
        return None

    def oeffnen_suchen(self):
        self.suche.setFocus()
        self.suche.selectAll()
        return True

    def oeffnen(self, angebot_id, schritt=bm.BAUTEILE):
        """Bestehende Kalkulation öffnen: dieselbe Angebotsseite wie im Expertenmodus."""
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
            self.f.meldung("Die Bauteilbibliothek ist noch leer. Ein Bauteil kommt hinein, wenn es im Expertenmodus "
                           "mit Rechtsklick → „Als Vorlage speichern“ gesichert wird.", fehler=True)
            return None
        seite = self._neues_angebot()
        if seite is None:
            return None
        seite.position_aus_vorlage(vorlage_id)
        if self._leer_entfernen(seite):
            return None
        return self.seite_setzen(seite)

    # -------------------------------------------------------------- Schritt 2: Bauteile
    def _bauteile_bauen(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(12)
        v.addWidget(_label("Bauteile prüfen", "e_seitentitel"))
        teiler = QSplitter(Qt.Horizontal)
        links = Karte("Erkannte Bauteile")
        self.bt = _tabelle(["", "Bauteil", "Art", "Querschnitt", "Länge", "Werkstoff", "Stück"])
        self.bt.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.bt.setMinimumHeight(240)
        self.bt.itemSelectionChanged.connect(self._bauteil_gewaehlt)
        self.bt.doubleClicked.connect(lambda i: self.loesen("editor", i.row()))
        self.bt.setToolTip("Doppelklick: Bauteil im Editor prüfen. Stück direkt in der Spalte ändern.")
        links.lay.addWidget(self.bt, 1)
        self.bt_hinweise = HinweisListe()
        self.bt_hinweise.loesen.connect(self.loesen)
        links.lay.addWidget(self.bt_hinweise)
        zeile = QHBoxLayout()
        zeile.addWidget(_knopf("Weitere Bauteile importieren …", lambda: self.importieren(),
                               "STEP-, DXF- oder TRUMPF-Dateien in diese Kalkulation holen"))
        zeile.addWidget(_knopf("Im Editor prüfen …", lambda: self.loesen("editor", self._bt_zeile()),
                               "Gewähltes Bauteil im Editor öffnen (Konturen, Bohrungen, Länge)"))
        zeile.addWidget(_knopf("Bauteil entfernen", self.bauteil_entfernen, "Gewähltes Bauteil löschen "
                               "(mit Rückgängig)"))
        zeile.addStretch(1)
        links.lay.addLayout(zeile)
        rechts = Karte("3D-Vorschau")
        self.vorschau_platz = QVBoxLayout()
        self.vorschau = None
        self.vorschau_titel = _label("Bauteil in der Liste wählen", "e_klein")
        rechts.lay.addLayout(self.vorschau_platz, 1)
        rechts.lay.addWidget(self.vorschau_titel)
        self.erkannt = _label("")
        rechts.lay.addWidget(self.erkannt)
        rechts.setMinimumWidth(280)
        teiler.addWidget(links)
        teiler.addWidget(rechts)
        teiler.setStretchFactor(0, 3)
        teiler.setStretchFactor(1, 2)
        teiler.setChildrenCollapsible(False)
        v.addWidget(teiler, 1)
        return _scroll(w)

    def _bt_zeile(self):
        r = self.bt.currentRow()
        return r if r >= 0 else None

    def _bauteile_fuellen(self):
        d = self.daten
        bauteile = d["bauteile"] if d else []
        self.bt.setRowCount(len(bauteile))
        self.stueck_felder = []
        for r, b in enumerate(bauteile):
            st = b["stufe"]
            z = _zelle(ZEICHEN[st], tipp=b["status"] or "Vollständig")
            z.setForeground(QColor(_farbe(FARBE_STUFE[st])))
            self.bt.setItem(r, 0, z)
            self.bt.setItem(r, 1, _zelle(b["name"], tipp=b["status"]))
            self.bt.setItem(r, 2, _zelle(b["art_text"]))
            self.bt.setItem(r, 3, _zelle(" ".join(x for x in (b["form"], b["profil"]) if x) or "–",
                                         tipp=bm.FELD_HILFE["profil"]))
            self.bt.setItem(r, 4, _zelle(f"{bm.zahl(b['laenge'], 1)} mm" if b["laenge"] else "–", True,
                                         bm.FELD_HILFE["laenge"]))
            self.bt.setItem(r, 5, _zelle(b["werkstoff"] or "–", tipp=bm.FELD_HILFE["werkstoff"]))
            sp = QSpinBox()
            sp.setRange(0, 9_999_999)
            sp.setValue(int(b["stueck"] or 0))
            sp.setToolTip(bm.FELD_HILFE["stueck"])
            sp.setMinimumWidth(90)
            sp.setKeyboardTracking(False)
            sp.editingFinished.connect(lambda r=r, sp=sp: self.stueck_setzen(r, sp.value()))
            if b["stufe"] == "FEHLER" and not b["stueck"]:
                sp.setStyleSheet(stil.ROTER_RAHMEN)
            self.bt.setCellWidget(r, 6, sp)
            self.stueck_felder.append(sp)
        self.bt_hinweise.setzen(d["hinweise"] if d else [])
        if bauteile and self.bt.currentRow() < 0:
            self.bt.selectRow(0)
        else:
            self._bauteil_gewaehlt()

    def _bauteil_gewaehlt(self):
        r = self._bt_zeile()
        d = self.daten
        if r is None or d is None or r >= len(d["bauteile"]):
            self.erkannt.setText("")
            return
        b = d["bauteile"][r]
        p = self.seite.positionen[r]
        werte = [("Art", b["art_text"]), ("Querschnitt", b["form"] or "–"), ("Abmessung", b["profil"] or "–"),
                 ("Wandstärke", f"{bm.zahl(b['wand'], 1)} mm" if b["wand"] else "–"),
                 ("Länge", f"{bm.zahl(b['laenge'], 1)} mm" if b["laenge"] else "–"),
                 ("Werkstoff", b["werkstoff"] or "nicht erkannt"),
                 ("Schnittkonturen", str(b["konturen"]) if b["konturen"] is not None else "–"),
                 ("Schneidweg", f"{bm.zahl(b['schneidweg'], 0)} mm" if b["schneidweg"] else "–")]
        if b["stufe"] != "OK":
            werte.append(("Hinweis", f"<span style='color:{_farbe(FARBE_STUFE[b['stufe']])}'>"
                                     f"{bm.loesung(b['status'])[0]}</span>"))
        self.erkannt.setText("<table cellspacing=0 cellpadding=2>" + "".join(
            f"<tr><td style='color:{_farbe(GRAU)};padding-right:10px'>{t}</td><td><b>{w}</b></td></tr>"
            for t, w in werte) + "</table>")
        self._vorschau(r, p)

    def _vorschau(self, r, p):
        try:
            netz, titel = self.seite._vorschau_netz(r)
        except Exception:           # noqa: BLE001 – Vorschau ist Zusatz
            netz, titel = None, ""
        if netz is None:
            self.vorschau_titel.setText("Keine 3D-Daten (kein STEP, keine Eingaben im Editor).")
            if self.vorschau is not None:
                self.vorschau.setzen(None)
            return
        if self.vorschau is None:
            from .ansicht3d import Ansicht3D      # ruhige Vorschau: Drehen mit der Maus, ohne Werkzeugleiste
            self.vorschau = Ansicht3D()
            self.vorschau.setMinimumHeight(240)
            self.vorschau.setToolTip("Mit der Maus drehen und zoomen. Messen, Schnitt und Explosion: im Editor "
                                     "bzw. im Expertenmodus.")
            self.vorschau_platz.addWidget(self.vorschau, 1)
        self.vorschau.setzen(netz, titel)
        self.vorschau_titel.setText("")

    def stueck_setzen(self, zeile, anzahl):
        """Stückzahl wie in der Positionstabelle des Expertenmodus speichern (gleiche Prüfung und Sperre)."""
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
        self.seite.positionen_loeschen()        # mit „Rückgängig“ in der Einblendung, wie im Expertenmodus
        self.aktualisieren()
        return True

    def importieren(self, dateien=None):
        if self.seite is None:
            return self.neu_aus_cad(dateien)
        self.seite.dateien_waehlen(dateien)
        self.aktualisieren()
        return True

    # -------------------------------------------------------------- Lösungen
    def loesen(self, aktion, zeile=None):
        """Lösungsknopf eines Hinweises: an die passende Stelle (im einfachen Modus, sonst Editor/Expertenmodus)."""
        s = self.seite
        if aktion == "import":
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
            self.zu_schritt(bm.ANGEBOT)
            return self.kunde_waehlen()
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
        umschalten(self.f, bm.EXPERTE)
        return True

    # -------------------------------------------------------------- Schritt 3: Material
    def _material_bauen(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(12)
        v.addWidget(_label("Material auswählen", "e_seitentitel"))
        v.addWidget(_label("Je Abmessung ein Material. Das Programm schlägt es aus der erkannten Geometrie vor und "
                           "übernimmt die hinterlegten Materialpreise.", "e_unter"))
        self.mat_raster = Raster(min_breite=300)
        v.addWidget(self.mat_raster)
        self.mat_leer = _label("Keine Rohr- oder Profilteile: Zukauf-, Norm- und Blechteile haben ihren eigenen "
                               "Preis.", "e_unter")
        v.addWidget(self.mat_leer)
        zeile = QHBoxLayout()
        zeile.addWidget(_knopf("Materialpreise und Lieferlängen …", self.material_dialog,
                               "Materialeinsatz und Kosten je Abmessung; Werkstoff, Lieferlänge, Meterpreis ändern"))
        zeile.addStretch(1)
        v.addLayout(zeile)
        v.addStretch(1)
        return _scroll(w)

    def _material_fuellen(self):
        s, d = self.seite, self.daten
        if s is None or d is None:
            self.mat_raster.setzen([])
            return
        from . import materialplattform as mp, rechnen
        try:
            var = mp.varianten(s.k, s.tabellen, self.db.zeilen(mp.LIEFERANTEN_TABELLE), bestand=mp.lager_bestand(self.db))
        except Exception:           # noqa: BLE001 – ohne Zusatzangaben weiter
            var = []
        gruppen = bm.material_gruppen(s.positionen, d["bauteile"], s.kopf, s.k, s.tabellen, var,
                                      lambda p: rechnen.meterpreis(p, s.kopf, s.positionen, s.k, s.tabellen))
        lager = getattr(self.f, "lager_an", lambda: False)()
        karten = []
        for g in gruppen:
            karten.append(self._material_karte(g, lager))
        self.mat_raster.setzen(karten)
        self.mat_leer.setVisible(not gruppen)
        self.mat_gruppen = gruppen

    def _material_karte(self, g, lager):
        from . import step
        s = self.seite
        k = Karte(f"{g['form'] or 'Profil'} {g['profil']}")
        erkannt = any(step.herkunft(s.positionen[i]) for i in g["zeilen"])
        k.lay.addWidget(_label(("✓ Abmessung aus der STEP-Datei erkannt · " if erkannt else "")
                               + f"{g['stueck']} Teile in {len(g['zeilen'])} Position(en)", "e_klein"))
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        ws = QComboBox()
        ws.setToolTip(bm.FELD_HILFE["werkstoff"])
        for wid, z in sorted(s.k.werkstoffe.items()):
            text = " · ".join(str(x) for x in (wid, z.get("werkstoff"), z.get("kategorie")) if x)
            ws.addItem(text, wid)
        i = ws.findData(g["werkstoff"])
        if i < 0:
            ws.insertItem(0, "(bitte wählen)", None)
            i = 0
        ws.setCurrentIndex(i)
        ws.currentIndexChanged.connect(lambda _, ws=ws, g=g: self.werkstoff_setzen(g["zeilen"], ws.currentData()))
        zeilen = [("Werkstoff", ws),
                  ("Wandstärke", _label(f"{bm.zahl(g['wand'], 1)} mm" if g["wand"] else "–")),
                  ("Preis", _label((f"<b>{bm.zahl(g['preis_m'], 2)} €/m</b>" if g["preis_m"] is not None else
                                    f"<span style='color:{_farbe(FARBE_STUFE['FEHLER'])}'><b>fehlt</b></span>")
                                   + (f" · {bm.zahl(g['preis_kg'], 2)} €/kg" if g.get("preis_kg") else ""))),
                  ("Preisstand", _label((f"{g['stand']}" if g["stand"] else "–")
                                        + (f" ({g['alter_tage']} Tage)" if g.get("alter_tage") is not None else "")
                                        + (f" · {g['quelle']}" if g["quelle"] else ""), "e_klein")),
                  ("Verfügbarkeit", _label(bm.verfuegbar_text(g, lager)))]
        tipps = {"Werkstoff": "werkstoff", "Preis": "preis_m", "Verfügbarkeit": "verfuegbar"}
        for r, (t, wdg) in enumerate(zeilen):
            lb = _label(t, "e_wert_titel", umbruch=False)
            if t in tipps:
                lb.setToolTip(bm.FELD_HILFE[tipps[t]])
                wdg.setToolTip(bm.FELD_HILFE[tipps[t]])
            form.addWidget(lb, r, 0)
            form.addWidget(wdg, r, 1)
        form.setColumnStretch(1, 1)
        k.lay.addLayout(form)
        if g["fehlt_preis"]:
            k.lay.addWidget(_knopf("Preis eintragen …", self.material_dialog,
                                   "Für dieses Material fehlt ein gültiger Preis", "primaer"), 0, Qt.AlignLeft)
        k.ws = ws
        return k

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

    # -------------------------------------------------------------- Schritt 4: Bearbeitung
    def _bearbeitung_bauen(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(12)
        v.addWidget(_label("Bearbeitung und Zusatzkosten", "e_seitentitel"))
        self.stand_text = _label("", "e_unter")
        v.addWidget(self.stand_text)
        self.kz = {n: Kennzahl(t, bm.FELD_HILFE[n]) for n, t in (
            ("maschinenzeit", "Maschinenzeit"), ("schnitt", "Schnittkosten"), ("ruesten", "Rüstkosten"),
            ("material", "Materialkosten"), ("zusatz", "Zusatzarbeiten"), ("zukauf", "Zukaufteile"),
            ("gemein", "Gemeinkosten"))}
        r = Raster(min_breite=200)
        r.setzen(list(self.kz.values()))
        v.addWidget(r)
        v.addWidget(self._fracht_karte_bauen())
        aktion = Karte("Wo Sie eingreifen können")
        aktion.lay.addWidget(_label("Alles Übrige rechnet das Programm automatisch mit denselben Werten wie im "
                                    "Expertenmodus.", "e_klein"))
        zeile = QHBoxLayout()
        zeile.addWidget(_knopf("Zusatzarbeiten hinzufügen …", self.zusatzarbeiten,
                               "Gewinde, Senken, Entgraten, Biegen … für alle oder die gewählten Bauteile"))
        self.vorschlag_knopf = _knopf("Vorgeschlagene Arbeiten übernehmen", self.vorschlaege,
                                      "Vom Programm erkannte Zusatzarbeiten (z. B. Gewinde aus Bohrungen) übernehmen")
        zeile.addWidget(self.vorschlag_knopf)
        zeile.addWidget(_knopf("Neu berechnen", lambda: self.loesen("optimieren"),
                               "Stangen optimieren und alle Preise neu rechnen"))
        zeile.addStretch(1)
        aktion.lay.addLayout(zeile)
        v.addWidget(aktion)
        v.addStretch(1)
        return _scroll(w)

    def _gruppen_tipp(self, gruppe):
        d = self.daten
        zuordnung = {n: g for g, _, namen in bm.GRUPPEN for n in namen}
        teile = [f"{text}: {bm.euro(w)}" for (text, w, _), (_, n, fett) in d["kosten"]
                 if not fett and zuordnung.get(n) == gruppe and abs(w or 0) > 0.004]
        return "\n".join(teile)

    def _bearbeitung_fuellen(self):
        d = self.daten
        if d is None:
            return
        e, g = d["ergebnis"], d["ergebnis"]["gruppen"]
        stand = d["stand"]
        self.stand_text.setText("✓ Schnittplan aktuell, alle Kosten gerechnet." if stand == "aktuell" else
                                "Der Schnittplan ist noch nicht aktuell: „Neu berechnen“ oder weiter zum Ergebnis "
                                "(rechnet automatisch).")
        self.kz["maschinenzeit"].setzen(bm.minuten_text(e["maschine_min"]),
                                        f"{e['teile']} Teile · {bm.zahl(e['maschine_min'] / e['teile'] * 60, 1)} s je Teil"
                                        if e["teile"] else "")
        for n in ("schnitt", "ruesten", "material", "zusatz", "zukauf", "gemein"):
            tipp = self._gruppen_tipp(n)
            self.kz[n].setzen(bm.euro(g[n]), bm.FELD_HILFE[n] if n != "material" else "Stangen inkl. Verschnitt",
                              tipp=(bm.FELD_HILFE[n] + ("\n\n" + tipp if tipp else "")))
        self._fracht_fuellen()
        n_vorschlaege = sum(len(v or ()) for v in getattr(self.seite.pos_modell, "vorschlaege", ()) or ())
        self.vorschlag_knopf.setText(f"Vorgeschlagene Arbeiten übernehmen ({n_vorschlaege})" if n_vorschlaege else
                                     "Keine offenen Vorschläge")
        self.vorschlag_knopf.setEnabled(bool(n_vorschlaege))

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
        k = Karte("Frachtkosten")
        k.lay.addWidget(_label("Fracht geht wie im Expertenmodus in den Verkaufspreis ein und wird auf die Bauteile "
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
                               "Fracht aus PLZ, Gewicht, Paket/Palette und Tarif berechnen (wie im Expertenmodus)")
        g.addWidget(_label("Frachtart", "e_wert_titel"), 0, 0)
        g.addWidget(self.fr_modus, 0, 1)
        g.addWidget(_label("Betrag", "e_wert_titel"), 0, 2)
        g.addWidget(self.fr_betrag, 0, 3)
        g.addWidget(_label("Verteilen", "e_wert_titel"), 1, 0)
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
        k = Karte("Marge einstellen")
        k.lay.addWidget(_label("Gewünschte Marge vom Warenwert eintragen: das Programm stellt den Gewinn so ein, "
                               "dass der Verkaufspreis genau diese Marge ergibt (Rabatt, Rundung und Mindestpreis "
                               "zählen mit). Fracht und Verpackung werden ohne Gewinn durchgereicht.", "e_klein"))
        zeile = QHBoxLayout()
        zeile.addWidget(_label("Marge", "e_wert_titel"))
        self.mg_wert = QDoubleSpinBox()
        self.mg_wert.setRange(0, 90)
        self.mg_wert.setDecimals(1)
        self.mg_wert.setSingleStep(0.5)
        self.mg_wert.setSuffix(" %")
        self.mg_wert.setToolTip("Marge = Gewinn ÷ Warenwert (Verkaufspreis ohne Fracht, Verpackung, Skonto)")
        zeile.addWidget(self.mg_wert)
        self.mg_knopf = _knopf("Marge übernehmen", lambda: self.marge_setzen(self.mg_wert.value()),
                               "Gewinn so einstellen, dass die eingetragene Marge erreicht wird (rückgängig möglich)")
        self.mg_knopf.setObjectName("primaer")
        zeile.addWidget(self.mg_knopf)
        self.mg_ziel = _knopf("", lambda: self.marge_setzen(self._satz("zielmarge") * 100),
                              "Marge auf die Zielmarge aus den Einstellungen setzen")
        self.mg_min = _knopf("", lambda: self.marge_setzen(self._satz("mindestmarge") * 100),
                             "Marge auf die Mindestmarge aus den Einstellungen setzen")
        zeile.addWidget(self.mg_ziel)
        zeile.addWidget(self.mg_min)
        zeile.addStretch(1)
        k.lay.addLayout(zeile)
        self.mg_text = _label("", "e_klein")
        k.lay.addWidget(self.mg_text)
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

    # -------------------------------------------------------------- Schritt 5: Ergebnis
    def _ergebnis_bauen(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(12)
        v.addWidget(_label("Kalkulationsergebnis", "e_seitentitel"))
        self.ek = {"verkauf": Kennzahl("Verkaufspreis (netto)", bm.FELD_HILFE["verkauf"], gross=True, akzent=True),
                   "gewinn": Kennzahl("Gewinn und Marge", bm.FELD_HILFE["gewinn"], gross=True),
                   "gesamt": Kennzahl("Gesamtkosten", bm.FELD_HILFE["gesamt"], gross=True)}
        oben = Raster(min_breite=260)
        oben.setzen(list(self.ek.values()))
        v.addWidget(oben)
        self.ek2 = {n: Kennzahl(t, bm.FELD_HILFE[h]) for n, t, h in (
            ("material", "Materialkosten", "material"), ("bearbeitung", "Bearbeitungskosten", "bearbeitung"),
            ("maschine", "Maschinenkosten", "schnitt"), ("zusatz", "Zusatzkosten", "zusatz"))}
        unten = Raster(min_breite=200)
        unten.setzen(list(self.ek2.values()))
        v.addWidget(unten)
        v.addWidget(self._marge_karte_bauen())
        auf = Karte("Kostenaufteilung")
        self.balken = Balken()
        self.balken_legende = _label("", "e_klein")
        auf.lay.addWidget(self.balken)
        auf.lay.addWidget(self.balken_legende)
        v.addWidget(auf)
        je = Karte("Preis je Bauteil")
        self.preis_tab = _tabelle(["Bauteil", "Stück", "Stückpreis", "Summe"])
        self.preis_tab.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.preis_tab.setMinimumHeight(220)
        je.lay.addWidget(self.preis_tab)
        v.addWidget(je, 1)
        pk = Karte("Prüfung vor dem Angebot")
        self.pruef = HinweisListe()
        self.pruef.loesen.connect(self.loesen)
        pk.lay.addWidget(self.pruef)
        v.addWidget(pk)
        return _scroll(w)

    def _ergebnis_fuellen(self):
        d = self.daten
        if d is None:
            return
        e = d["ergebnis"]
        self.ek["verkauf"].setzen(bm.euro(e["verkauf"]), f"{e['teile']} Teile" if e["teile"] else "")
        farbe = AMPEL.get(e["stufe"])
        marge = f"Marge {bm.zahl(100 * e['marge'], 1)} %" if e["marge"] is not None else "Marge –"
        self.ek["gewinn"].setzen(bm.euro(e["gewinn"]), f"● {e['ampel_text']}" if e["ampel_text"] else marge,
                                 _farbe(farbe) if farbe else None,
                                 tipp=bm.FELD_HILFE["gewinn"] + "".join("\n• " + x for x in e["gruende"]))
        self.ek["gesamt"].setzen(bm.euro(e["gesamt"]), "ohne Gewinn")
        self._marge_fuellen()
        for n in ("material", "bearbeitung", "maschine", "zusatz"):
            self.ek2[n].setzen(bm.euro(e[n]))
        g = e["gruppen"]
        teile = [(bm.GRUPPE_TITEL[n], g[n]) for n, _, _ in bm.GRUPPEN if n not in ("preis",)]
        self.balken.setzen(teile)
        summe = sum(w for _, w in teile if w > 0) or 1
        self.balken_legende.setText(" · ".join(
            f"<span style='color:{_farbe(Balken.FARBEN[i % len(Balken.FARBEN)])}'>■</span> {t} "
            f"{bm.zahl(100 * w / summe, 0)} %" for i, (t, w) in enumerate((t, w) for t, w in teile if w > 0)))
        zeilen = d["zeilen"]
        bt = d["bauteile"]
        self.preis_tab.setRowCount(len(zeilen))
        for r, z in enumerate(zeilen):
            name = bt[r]["name"] if r < len(bt) else str(z.get("artikel") or z.get("pos") or "")
            self.preis_tab.setItem(r, 0, _zelle(name))
            self.preis_tab.setItem(r, 1, _zelle(z.get("stueck") or "–", True))
            self.preis_tab.setItem(r, 2, _zelle(bm.euro(z.get("preis_teil")), True))
            self.preis_tab.setItem(r, 3, _zelle(bm.euro(z.get("preis_position")), True))
        punkte = [(st, text, "experte", None) for st, text in self._punkte() if st in ("FEHLER", "WARNUNG")]
        self.pruef.setzen([h for h in d["hinweise"] if h[0] != "HINWEIS"] + punkte)

    def _punkte(self):
        aus = []
        for p in getattr(self.seite, "_punkte", None) or ():
            try:
                st, text = p[0], p[1]
            except (TypeError, IndexError):
                continue
            if st in FARBE_STUFE:
                aus.append((st, str(text)))
        return aus

    # -------------------------------------------------------------- Schritt 6: Angebot
    def _angebot_bauen(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(12)
        v.addWidget(_label("Angebot erstellen", "e_seitentitel"))
        kunde = Karte("Kunde")
        h = QHBoxLayout()
        self.kunde_text = _label("")
        h.addWidget(self.kunde_text, 1)
        h.addWidget(_knopf("Kunde wählen …", self.kunde_waehlen, "Kunden suchen oder neu anlegen"))
        kunde.lay.addLayout(h)
        v.addWidget(kunde)
        pos = Karte("Positionen, Mengen und Preise")
        self.ang_tab = _tabelle(["Pos.", "Bauteil", "Menge", "Stückpreis", "Summe"])
        self.ang_tab.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.ang_tab.setMinimumHeight(200)
        pos.lay.addWidget(self.ang_tab, 1)
        self.ang_summe = _label("", "e_karten_titel")
        self.ang_summe.setAlignment(Qt.AlignRight)
        pos.lay.addWidget(self.ang_summe)
        v.addWidget(pos, 1)
        self.ang_hinweise = HinweisListe()
        self.ang_hinweise.loesen.connect(self.loesen)
        v.addWidget(self.ang_hinweise)
        zeile = QHBoxLayout()
        zeile.addWidget(_knopf("Angebot erstellen (PDF)", self.pdf_erstellen, "Angebots-PDF für den Kunden "
                               "erstellen und öffnen", "primaer"))
        zeile.addWidget(_knopf("PDF öffnen", self.pdf_oeffnen, "Zuletzt erstelltes PDF dieses Angebots öffnen"))
        self.mail_knopf = _knopf("Per E-Mail senden …", self.mail, "Angebot als PDF per E-Mail schicken")
        zeile.addWidget(self.mail_knopf)
        zeile.addWidget(_knopf("Angebot speichern", self.speichern, "Jede Änderung ist schon gespeichert; mit "
                               "gemeinsamem Ordner gleich abgleichen"))
        zeile.addStretch(1)
        zeile.addWidget(_knopf("Im Expertenmodus weiterbearbeiten", lambda: umschalten(self.f, bm.EXPERTE),
                               "Staffeln, Rabatte, Sonderfälle: dasselbe Angebot mit allen Funktionen"))
        v.addLayout(zeile)
        return _scroll(w)

    def _angebot_fuellen(self):
        s, d = self.seite, self.daten
        if s is None or d is None:
            return
        k = s.kopf or {}
        self.kunde_text.setText(f"<b>{k.get('kunde')}</b> · Kundennr. {k.get('kundennr') or '–'}" if k.get("kunde") else
                                f"<span style='color:{_farbe(FARBE_STUFE['WARNUNG'])}'><b>Noch kein Kunde gewählt.</b>"
                                "</span>")
        zeilen, bt = d["zeilen"], d["bauteile"]
        self.ang_tab.setRowCount(len(zeilen))
        self.menge_felder = []
        for r, z in enumerate(zeilen):
            self.ang_tab.setItem(r, 0, _zelle(z.get("pos") or r + 1))
            self.ang_tab.setItem(r, 1, _zelle(bt[r]["name"] if r < len(bt) else ""))
            sp = QSpinBox()
            sp.setRange(0, 9_999_999)
            sp.setValue(int(z.get("stueck") or 0))
            sp.setKeyboardTracking(False)
            sp.setToolTip(bm.FELD_HILFE["stueck"])
            sp.editingFinished.connect(lambda r=r, sp=sp: self.stueck_setzen(r, sp.value()))
            self.ang_tab.setCellWidget(r, 2, sp)
            self.menge_felder.append(sp)
            self.ang_tab.setItem(r, 3, _zelle(bm.euro(z.get("preis_teil")), True))
            self.ang_tab.setItem(r, 4, _zelle(bm.euro(z.get("preis_position")), True))
        e = d["ergebnis"]
        self.ang_summe.setText(f"Angebotssumme netto: {bm.euro(e['verkauf'])}")
        from . import funktionen
        self.mail_knopf.setVisible(funktionen.an("funktion_angebot_mail", self.db))
        self.ang_hinweise.setzen([h for h in d["hinweise"] if h[0] in ("FEHLER", "WARNUNG") or h[2] == "kunde"])

    def kunde_waehlen(self, kundennr=None):
        if self.seite is None:
            return None
        nr = self.seite.kunde_suchen(kundennr)
        self.aktualisieren()
        return nr

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
        aktion.blockSignals(True)
        aktion.setChecked(neu == bm.EINFACH)
        aktion.blockSignals(False)
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
    a.setToolTip("Geführte Kalkulation in sechs Schritten; ohne Haken: Experten-Pro-Modus")
    a.toggled.connect(lambda an: umschalten(f, bm.EINFACH if an else bm.EXPERTE))
    f.modus_aktion = a
    return a

