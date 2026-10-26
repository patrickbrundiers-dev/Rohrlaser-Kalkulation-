"""Oberer Teil der Angebotsseite: Angebotskopf, Maschinenparameter, Kalkulationseinstellungen und Übersicht.

Welche Felder und Kennzahlen sichtbar sind, entscheidet sichtbarkeit.py: optionale Werte mit 0 oder leer stehen
nicht in der Hauptansicht, sondern unter 'Erweiterte Einstellungen' (dort immer änderbar). Pflichtfelder,
Stammdaten und Maschinenparameter bleiben immer sichtbar. Gespeichert und gerechnet wird wie bisher.
"""
from PySide6.QtCore import QDate, QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from . import fracht_angebot, hilfe, rechnen, teilen, zukauf
from .ausgabe import datum_text
from .fracht_angebot import MODI, UMLAGEN
from .angebot import (KALK_OHNE_VORGABE, EIGENMATERIAL, KUNDENMATERIAL, KALK_PROZENT, KALKULATION, KOPF, LIEFERZEIT_ARTEN, MATERIAL_HERKUNFT, LIEFERZEIT_HILFE, NUR_TEXT,
                      aktiv as position_aktiv, kalk_abweichungen, lieferzeit_text)
from .sichtbarkeit import MASCHINE, OPTIONAL, ist_null, kopf_sichtbar, sichtbar
from .stammdaten import zahl_als_text
from .eingabe import RechenSpin, RechenSpinGanz

KOPF_FELD = {f.name: f for f in KOPF}
KALK_NAMEN = {f.name for f in KALKULATION}
KALK_OFFEN_EINSTELLUNG = "ansicht_kalkulation_offen"     # Karte Kalkulation auf- oder zugeklappt (alle Angebote)
FRACHT_OFFEN_EINSTELLUNG = "ansicht_fracht_offen"        # Karte Fracht auf- oder zugeklappt (alle Angebote)
# Kalkulationseinstellungen nach Zweck (Felder des Angebotskopfs); programmierung_teil (€ je Position älterer Angebote)
# steht nicht hier: er zählt nur, solange die Programmierzeit leer ist (Kostenübersicht, Zeiten & Arbeitskosten)
GRUPPEN = (
    ("Material und Fertigung", ("zuschlag_fremdleistung", "aufschlag_blech", "aufschlag_zukauf", "handling_beistellung")),
    ("Zeit und Rüsten", ("ruesten_abmessung", "ruesten_abmessung_eur", "ruesten_angebot_eur", "programmierung_zeit",
                         "programmierung_kontur")),
    ("Verkauf und Gewinn", ("gewinn", "angebotsaufschlag", "pauschale_abmessung", "fracht")),
    ("Zahlungsbedingungen", ("skonto", "skonto_tage", "zahlungsziel")),
)
# Maschinenparameter (Stammdaten Maschinen): (Feld, Titel, Einheit, Stellen, Rolle)
MASCHINENPARAMETER = (
    ("endbeschnitt", "Endbeschnitt", "mm", 0, MASCHINE), ("greiferrest", "Greiferrest", "mm", 0, MASCHINE),
    ("schnittverlust", "Schnittverlust je Schnitt", "mm", 1, MASCHINE),
    ("max_stange", "Max. Stangenlänge", "mm", 0, MASCHINE),
    ("abstand", "Abstand getrennte Schnitte", "mm", 1, OPTIONAL),
    ("kontur_klein", "Kontur klein bis", "mm", 1, OPTIONAL), ("kontur_mittel", "Kontur mittel bis", "mm", 1, OPTIONAL),
    ("kontur_klein_wand", "Kontur klein bis", "× Wand", 1, OPTIONAL),
    ("kontur_mittel_wand", "Kontur mittel bis", "× Wand", 1, OPTIONAL),
    ("max_huellkreis", "Max. Hüllkreis-Ø", "mm", 1, OPTIONAL), ("max_kg_m", "Max. Metergewicht", "kg/m", 1, OPTIONAL),
    ("min_stange", "Min. Stangenlänge Zuschnitt", "mm", 0, OPTIONAL),
)
# Werte der gewählten Maschine, die in die Kalkulation eingehen (Gruppe Zeit und Rüsten)
MASCHINE_KALK = (("ruestzeit", "Rüstzeit je Maschine (Angebot)", "min", 0),
                 ("stangenwechsel", "Stangenwechsel je Stange", "s", 0),
                 ("stangenwechsel_sn", "Stangenwechsel SN (Schweißnaht)", "s", 0),
                 ("stundensatz", "Stundensatz Maschine", "€/h", 2))

LIEFERZEIT_TOOLTIP = ("Arbeitstage und Wochen zählen ab Auftragseingang; Kalenderwoche und Lieferdatum sind feste "
                      "Termine; „nur Text“ zeigt nur den Freitext")
# Fracht rechts neben der Kalkulation ab dieser Breite der Angebotsseite (darunter steht sie unter der Kalkulation)
FRACHT_RECHTS_AB = 1800
RUESTEN_EUR = ("ruesten_angebot_eur", "ruesten_abmessung_eur")     # leer = Rüsten in Minuten × Stundensatz

from .stil import GELB_FLAECHE as GELB, GELB_TEXT, ORANGE, TEXT_GRAU as GRAU  # noqa: E402


def _z(w, stellen=2):
    return zahl_als_text(w, stellen) if isinstance(w, (int, float)) and not isinstance(w, bool) else ""


def _kurz(titel):
    """'Zuschlag Material [%]' -> 'Zuschlag Material'"""
    return titel.split("[")[0].strip()


def _wert_text(fd, w):
    """Wert eines Kalkulationsfelds mit Einheit, z. B. '12 %' oder '200,00 €'."""
    einheit = fd.titel.split("[", 1)[1].rstrip("]") if "[" in fd.titel else ""
    stellen = fd.stellen if fd.stellen is not None else 2
    if einheit in ("%", "min"):
        t = rechnen.zahl(w, stellen)
    else:
        t = _z(w, stellen)
    return f"{t} {einheit}".strip()


def _lz_anzeige(art, wert):
    """Gespeicherten Lieferzeit-Wert anzeigen: Datum als TT.MM.JJJJ, sonst wie gespeichert."""
    if wert and art == "Lieferdatum":
        return datum_text(wert)
    return wert or ""


def karte(titel=None, rechts=None):
    """Weiße Karte mit dünnem Rahmen; Ergebnis: (Karte, Layout für den Inhalt)."""
    k = QFrame()
    k.setObjectName("karte")
    lay = QVBoxLayout(k)
    lay.setContentsMargins(12, 8, 12, 10)
    lay.setSpacing(6)
    if titel:
        zeile = QHBoxLayout()
        t = QLabel(titel)
        t.setObjectName("kartentitel")
        zeile.addWidget(t)
        zeile.addStretch(1)
        if rechts is not None:
            zeile.addWidget(rechts)
        lay.addLayout(zeile)
    return k, lay


class Doppelklick(QObject):
    """Doppelklick auf ein Eingabefeld ruft aktion() auf, statt ein Wort zu markieren (z. B. Kunde öffnen)."""

    def __init__(self, feld, aktion, tooltip):
        super().__init__(feld)
        self.aktion = aktion
        feld.installEventFilter(self)
        feld.setToolTip(tooltip)

    def eventFilter(self, _obj, ereignis):
        if ereignis.type() == QEvent.MouseButtonDblClick:
            self.aktion()
            return True
        return False


class Aufklapper(QWidget):
    """Aufklappbarer Bereich: Knopf mit Pfeil und Titel, darunter der Inhalt (zu Beginn zugeklappt)."""

    def __init__(self, titel, inhalt, offen=False):
        super().__init__()
        self.knopf = QToolButton()
        self.knopf.setObjectName("aufklapper")
        self.knopf.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.knopf.setCheckable(True)
        self.knopf.setAutoRaise(True)
        self.knopf.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.knopf.toggled.connect(self.aufklappen)
        self.inhalt = inhalt
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(self.knopf)
        lay.addWidget(inhalt)
        self.setze_titel(titel)
        self.knopf.setChecked(offen)
        self.aufklappen(offen)

    def setze_titel(self, titel):
        self.knopf.setText(titel)

    def aufklappen(self, offen=True):
        self.knopf.setChecked(offen)
        self.knopf.setArrowType(Qt.DownArrow if offen else Qt.RightArrow)
        self.inhalt.setVisible(offen)

    def offen(self):
        return self.knopf.isChecked()


def _versand_text(v):
    """Eine Zeile des Versandverlaufs: PDF mit Netto oder Vorgang von Hand, dazu ein übergangener Angebots-Check;
    Nachfassen und Wiedervorlage (Plan A9)."""
    if v.get("art") == "nachgefasst":
        return f"{datum_text(v.get('datum'))}: nachgefasst ({v.get('wie') or 'E-Mail'})"
    if v.get("art") == "csv":
        return f"{datum_text(v.get('datum'))}: CSV-Export ({v.get('datei') or 'CSV'})"
    if v.get("art") == "wiedervorlage":
        return (f"{datum_text(v.get('datum'))}: Wiedervorlage am {datum_text(v['am'])}" if v.get("am") else
                f"{datum_text(v.get('datum'))}: Wiedervorlage entfernt")
    t = (f"{datum_text(v.get('datum'))}: {_z(v.get('netto'))} € netto ({v.get('datei') or 'PDF'})" if v.get("datei")
         or v.get("netto") is not None else f"{datum_text(v.get('datum'))}: als verschickt markiert (ohne PDF)")
    c = v.get("check")
    if isinstance(c, dict) and c.get("punkte"):
        t += f" – Angebots-Check übergangen ({len(c['punkte'])} Punkte)"
        if c.get("begruendung"):
            t += f": {c['begruendung']}"
    return t


class KopfBereich(QWidget):
    """Angebotskopf, Maschinenparameter und Kalkulationseinstellungen (links auf der Angebotsseite)."""

    def __init__(self, seite):
        super().__init__()
        self.s = seite
        self.felder, self.erweitert = {}, {}         # Name -> Eingabe (Hauptansicht bzw. Erweiterte Einstellungen)
        self.zeilen, self.zeilen_erweitert = {}, {}  # Name -> (Beschriftung, Eingabe) zum Ein- und Ausblenden
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        # Angebotskopf: Nummer, Kunde und Maschine vorn und hervorgehoben; ausgefüllt zugeklappt auf eine Zeile
        kopf, kl0 = karte()
        titelzeile = QHBoxLayout()
        self.kopf_knopf = QToolButton()
        self.kopf_knopf.setObjectName("kartenknopf")
        self.kopf_knopf.setText("Angebotskopf")
        self.kopf_knopf.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.kopf_knopf.setCheckable(True)
        self.kopf_knopf.setAutoRaise(True)
        self.kopf_knopf.setToolTip("Angebotskopf ein- oder ausklappen (zugeklappt: Nummer, Kunde, Maschine, Stange)")
        self.kopf_knopf.clicked.connect(lambda offen: self.kopf_aufklappen(offen))
        self.kopf_kurz = QLabel()
        self.kopf_kurz.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.kopf_kurz.setCursor(Qt.PointingHandCursor)
        self.kopf_kurz.mousePressEvent = lambda _e: self.kopf_aufklappen(True)
        titelzeile.addWidget(self.kopf_knopf, 0, Qt.AlignLeft)     # aufgeklappt (ohne Kurzzeile) links, nicht mittig
        titelzeile.addWidget(self.kopf_kurz, 1)
        kl0.addLayout(titelzeile)
        self.kopf_inhalt = QWidget()
        kl = QVBoxLayout(self.kopf_inhalt)
        kl.setContentsMargins(0, 0, 0, 0)
        kl.setSpacing(6)
        kl0.addWidget(self.kopf_inhalt)
        self._kopf_gewaehlt = None          # None = automatisch (zu, sobald Kunde und Positionen da sind)
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(4)
        anordnung = (("nummer", 0, 0), ("kundennr", 0, 1), ("maschine", 0, 2),
                     ("datum", 1, 0), ("kunde", 1, 1), ("stange", 1, 2))
        for name, zeile, spalte in anordnung:
            fd = KOPF_FELD[name]
            w = self._eingabe(fd, self.felder)
            if zeile == 0:
                f = QFont(w.font())
                f.setBold(True)
                f.setPointSizeF(f.pointSizeF() + 1)
                w.setFont(f)
            b = QLabel(fd.titel)
            g.addWidget(b, zeile, 2 * spalte)
            g.addWidget(w, zeile, 2 * spalte + 1)
        w = self._eingabe(KOPF_FELD["kundenreferenz"], self.felder)
        w.setPlaceholderText("z. B. Anfrage 4711 vom 20.10.2026")
        # kompakt (Layout-Plan L2, Patrick 25.10.2026): Anfrage | Bemerkung | Bearbeiter, Lieferzeit | Material; die
        # Vorschau der Lieferzeit nur als eigene Zeile, wenn sie etwas sagt, was die Felder nicht zeigen
        g.addWidget(QLabel(KOPF_FELD["kundenreferenz"].titel), 2, 0)
        g.addWidget(w, 2, 1)
        # Lieferzeit dieses Angebots: Art, Wert passend zur Art und Freitext (ändert keine Preise)
        self.lz_art, self.lz_wert, self.lz_zusatz = QComboBox(), QLineEdit(), QLineEdit()
        self.lz_art.addItems(LIEFERZEIT_ARTEN)
        self.lz_art.setToolTip(LIEFERZEIT_TOOLTIP)
        self.lz_wert.setMaximumWidth(130)
        self.lz_zusatz.setPlaceholderText("Freitext, z. B. nach Absprache, Teillieferung möglich")
        self.lz_art.currentTextChanged.connect(lambda t: seite._kopf_speichern(KOPF_FELD["lieferzeit_art"], t or None))
        self.lz_wert.editingFinished.connect(
            lambda: seite._kopf_speichern(KOPF_FELD["lieferzeit_wert"], self.lz_wert.text().strip() or None))
        self.lz_zusatz.editingFinished.connect(
            lambda: seite._kopf_speichern(KOPF_FELD["lieferzeit_zusatz"], self.lz_zusatz.text().strip() or None))
        lz = QHBoxLayout()
        lz.setContentsMargins(0, 0, 0, 0)
        lz.addWidget(self.lz_art)
        lz.addWidget(self.lz_wert)
        lz.addWidget(self.lz_zusatz, 1)
        g.addWidget(QLabel("Lieferzeit"), 3, 0)
        g.addLayout(lz, 3, 1, 1, 3)
        self.lz_vorschau = QLabel()
        self.lz_vorschau.setStyleSheet(f"color: {GRAU};")
        g.addWidget(self.lz_vorschau, 4, 1, 1, 3)
        # Material neuer Positionen: Eigenmaterial oder vom Kunden beigestellt; je Position änderbar
        self.mat_vorgabe = QComboBox()
        self.mat_vorgabe.addItems(MATERIAL_HERKUNFT)
        self.mat_vorgabe.setToolTip("Vorgabe der Spalte Material für neue Positionen (auch STEP-Import); jede Position "
                                    "bleibt einzeln änderbar")
        self.mat_vorgabe.currentTextChanged.connect(
            lambda t: seite._kopf_speichern(KOPF_FELD["material_vorgabe"], None if t == EIGENMATERIAL else t))
        self.mat_alle = QPushButton("Für alle Positionen")
        self.mat_alle.setToolTip("Die gewählte Materialherkunft in alle Positionen (Rohrlaserteile) eintragen")
        self.mat_alle.clicked.connect(lambda: seite.material_fuer_alle(self.mat_vorgabe.currentText()))
        mz = QHBoxLayout()
        mz.setContentsMargins(0, 0, 0, 0)
        mz.addWidget(self.mat_vorgabe)
        mz.addWidget(self.mat_alle)
        mz.addStretch(1)
        g.addWidget(QLabel(KOPF_FELD["material_vorgabe"].titel), 3, 4)
        g.addLayout(mz, 3, 5)
        w = self._eingabe(KOPF_FELD["bemerkung"], self.felder)
        g.addWidget(QLabel(KOPF_FELD["bemerkung"].titel), 2, 2)
        g.addWidget(w, 2, 3)
        # Bearbeiter (Kürzel und Name, teilen.py): nur Anzeige, gesetzt beim Anlegen
        self.bearbeiter = QLabel()
        self.bearbeiter.setToolTip("Mitarbeiter, der das Angebot angelegt hat (Kürzel vorn in der Nummer); im "
                                   "Angebots-PDF als Ansprechpartner")
        g.addWidget(QLabel(KOPF_FELD["bearbeiter"].titel), 2, 4)
        g.addWidget(self.bearbeiter, 2, 5)
        for c in (1, 3, 5):
            g.setColumnStretch(c, 1)
        kl.addLayout(g)
        # Maschinenparameter (aufklappbar; der Titel zeigt die wichtigsten Werte auch zugeklappt)
        self.maschinenwerte = QLabel()
        self.maschinenwerte.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.maschinenwerte.setWordWrap(True)
        self.maschinen_bereich = Aufklapper("Maschinenparameter", self.maschinenwerte)
        kl.addWidget(self.maschinen_bereich)
        lay.addWidget(kopf)

        # Kalkulationseinstellungen dieses Angebots
        vorgaben = QPushButton("Vorgaben aus Einstellungen")
        vorgaben.setToolTip("Zuschläge, Gewinn, Rüstzeit und Pauschalen wieder auf die Werte der Einstellungen setzen")
        vorgaben.clicked.connect(lambda: seite.kalkulation_zuruecksetzen())
        kalk, kal0 = karte()
        titelzeile = QHBoxLayout()
        self.kalk_knopf = QToolButton()
        self.kalk_knopf.setObjectName("kartenknopf")
        self.kalk_knopf.setText("Kalkulation dieses Angebots")
        self.kalk_knopf.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.kalk_knopf.setCheckable(True)
        self.kalk_knopf.setAutoRaise(True)
        self.kalk_knopf.setToolTip("Kalkulationswerte ein- oder ausklappen (zugeklappt: Kurzfassung der Werte)")
        self.kalk_knopf.clicked.connect(lambda offen: self.kalkulation_aufklappen(offen, merken=True))
        self.kalk_kurz = QLabel()
        self.kalk_kurz.setStyleSheet(f"color: {GRAU};")
        self.kalk_kurz.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        titelzeile.addWidget(self.kalk_knopf)
        titelzeile.addWidget(self.kalk_kurz, 1)
        titelzeile.addStretch(0)            # aufgeklappt (Kurzfassung weg): Knopf bleibt rechts und schmal
        titelzeile.addWidget(vorgaben)
        kal0.addLayout(titelzeile)
        self.kalk_inhalt = QWidget()
        kal = QVBoxLayout(self.kalk_inhalt)
        kal.setContentsMargins(0, 0, 0, 0)
        kal.setSpacing(6)
        kal0.addWidget(self.kalk_inhalt)
        hinweis = hilfe.Hinweis("Vorgabe aus den Einstellungen, hier änderbar; gilt nur für dieses Angebot. Gelb = "
                                "weicht von den Einstellungen ab. Werte mit 0 stehen unter „Erweiterte "
                                "Einstellungen“.",
                                schluessel="angebot_kalkulation")
        kal.addWidget(hinweis)
        self.abweichung_text = QLabel()            # welche Werte vom Standard abweichen (auch Stundensätze)
        self.abweichung_text.setWordWrap(True)
        self.abweichung_text.setStyleSheet(f"color: {GELB_TEXT};")
        self.abweichung_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        kal.addWidget(self.abweichung_text)
        # Mindestauftragswert je Angebot ein/aus; der Betrag kommt nur aus den Einstellungen (Patrick 23.10.2026)
        self.mindest_an = QCheckBox("Mindestauftragswert anwenden")
        self.mindest_an.setToolTip("Betrag aus den Einstellungen. "
                                   "Liegt der Verkaufspreis unter dem Mindestauftragswert der Einstellungen, werden "
                                   "alle Stückpreise anteilig angehoben. Ohne Haken gilt für dieses Angebot kein "
                                   "Mindestauftragswert.")
        self.mindest_an.toggled.connect(
            lambda an: seite._kopf_speichern(KOPF_FELD["mindestpreis_anwenden"], None if an else "nein"))
        gruppen = QGridLayout()
        gruppen.setHorizontalSpacing(18)
        self.gruppen_leer = {}
        self.maschine_kalk = {}
        self.gruppen_boxen = []
        for spalte, (titel, namen) in enumerate(GRUPPEN):
            gruppe = QWidget()
            box = QVBoxLayout(gruppe)
            box.setContentsMargins(0, 0, 0, 0)
            t = QLabel(titel)
            t.setObjectName("gruppentitel")
            box.addWidget(t)
            form = QGridLayout()
            form.setHorizontalSpacing(6)
            form.setVerticalSpacing(4)
            r = 0
            if titel == "Zeit und Rüsten":     # Werte der Maschine (Snapshot des Angebots); Stangenwechsel änderbar
                for name, text, einheit, _ in MASCHINE_KALK:
                    if name == "stangenwechsel":   # je Angebot änderbar wie Rüstzeit je Abmessung (Patrick 25.10.2026)
                        b, w = QLabel(f"{text} [{einheit}]"), RechenSpinGanz()
                        w.setRange(0, 3600)
                        w.setAlignment(Qt.AlignRight)
                        w.setMinimumWidth(90)
                        w.editingFinished.connect(lambda w=w: seite.stangenwechsel_setzen(w.value()))
                        self.stangenwechsel = w
                    else:
                        b, w = QLabel(text), QLabel()
                        w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        w.setToolTip("Aus den Stammdaten Maschinen (gewählte Maschine), im Angebot gespeichert; "
                                     "Stundensatz änderbar im Reiter Zeiten & Arbeitskosten")
                    self.maschine_kalk[name] = (b, w, einheit)
                    form.addWidget(b, r, 0)
                    form.addWidget(w, r, 1)
                    r += 1
            for name in namen:
                fd = KOPF_FELD[name]
                w = self._eingabe(fd, self.felder)
                b = QLabel(fd.titel)
                self.zeilen[name] = (b, w)
                form.addWidget(b, r, 0)
                form.addWidget(w, r, 1)
                r += 1
            if titel == "Verkauf und Gewinn":  # Mindestauftragswert ein/aus gehört zum Verkauf, spart eine Zeile
                form.addWidget(self.mindest_an, r + 1, 0, 1, 2)
            leer = QLabel("alle Werte 0")
            leer.setStyleSheet(f"color: {GRAU}; font-style: italic;")
            self.gruppen_leer[titel] = (leer, namen)
            form.addWidget(leer, r, 0, 1, 2)
            form.setColumnStretch(1, 1)
            box.addLayout(form)
            box.addStretch(1)
            self.gruppen_boxen.append(gruppe)
        self.gruppen_raster = gruppen
        self._spalten_gruppen = None
        self._gruppen_anordnen(4)
        kal.addLayout(gruppen)
        # Erweiterte Einstellungen: alle optionalen Werte, die gerade 0 sind (hier änderbar)
        er = QWidget()
        eg = QGridLayout(er)
        eg.setContentsMargins(16, 0, 0, 0)
        eg.setHorizontalSpacing(8)
        eg.setVerticalSpacing(4)
        namen = [n for _, ns in GRUPPEN for n in ns]
        for i, name in enumerate(namen):
            fd = KOPF_FELD[name]
            w = self._eingabe(fd, self.erweitert)
            b = QLabel(fd.titel)
            self.zeilen_erweitert[name] = (b, w)
            eg.addWidget(b, i // 3, 2 * (i % 3))
            eg.addWidget(w, i // 3, 2 * (i % 3) + 1)
        for c in (1, 3, 5):
            eg.setColumnStretch(c, 1)
        self.erweitert_leer = QLabel("Keine weiteren Einstellungen: alle Werte sind oben sichtbar.")
        self.erweitert_leer.setStyleSheet(f"color: {GRAU};")
        eg.addWidget(self.erweitert_leer, len(namen), 0, 1, 6)
        self.erweitert_bereich = Aufklapper("Erweiterte Einstellungen", er)
        kal.addWidget(self.erweitert_bereich)
        # Kalkulation und Fracht: breite Seite nebeneinander, sonst untereinander (karten_anordnen)
        self.kalk_karte = kalk
        self.karten = QGridLayout()
        self.karten.setContentsMargins(0, 0, 0, 0)
        self.karten.setSpacing(8)
        lay.addLayout(self.karten)

        # Fracht: Frachtart, Verteilung und Berechnung (fracht_angebot.py)
        self.fracht_knopf = QPushButton("Fracht berechnen …")
        self.fracht_knopf.setToolTip("Frachtkosten aus PLZ, Gewicht, Ladehilfsmitteln und Tarif berechnen "
                                     "(Reiter Frachtkosten) und ins Angebot übernehmen")
        self.fracht_knopf.clicked.connect(lambda: seite.fracht_berechnen())
        fr, fr0 = karte()
        titelzeile = QHBoxLayout()
        self.fracht_klapp = QToolButton()
        self.fracht_klapp.setObjectName("kartenknopf")
        self.fracht_klapp.setText("Fracht")
        self.fracht_klapp.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.fracht_klapp.setCheckable(True)
        self.fracht_klapp.setAutoRaise(True)
        self.fracht_klapp.setToolTip("Fracht ein- oder ausklappen (zugeklappt: Frachtart und Betrag)")
        self.fracht_klapp.clicked.connect(lambda offen: self.fracht_aufklappen(offen, merken=True))
        self.fracht_kurz = QLabel()
        self.fracht_kurz.setStyleSheet(f"color: {GRAU};")
        self.fracht_kurz.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        titelzeile.addWidget(self.fracht_klapp)
        titelzeile.addWidget(self.fracht_kurz, 1)
        titelzeile.addStretch(0)
        titelzeile.addWidget(self.fracht_knopf)
        fr0.addLayout(titelzeile)
        self.fracht_inhalt = QWidget()
        frl = QVBoxLayout(self.fracht_inhalt)
        frl.setContentsMargins(0, 0, 0, 0)
        frl.setSpacing(6)
        fr0.addWidget(self.fracht_inhalt)
        self.fracht_karte = fr
        self.fracht_modus, self.fracht_umlage = QComboBox(), QComboBox()
        self.fracht_modus.addItems(MODI)
        self.fracht_umlage.addItems(UMLAGEN)
        self.fracht_modus.setToolTip("manuell: Betrag „Frachtkosten“ von Hand; berechnet: aus „Fracht berechnen …“, "
                                     "in den Staffelpreisen je Menge neu; keine Fracht (Abholung, ab Werk) und im "
                                     "Artikelpreis enthalten: 0 € in der Kalkulation, Hinweis im Angebot")
        self.fracht_umlage.setToolTip("je Stück: jedes Teil trägt gleich viel; nach Gewicht: Anteil des Teilegewichts "
                                      "am Gesamtgewicht")
        for cb, name in ((self.fracht_modus, "fracht_modus"), (self.fracht_umlage, "fracht_umlage")):
            cb.currentTextChanged.connect(lambda t, name=name: seite._kopf_speichern(KOPF_FELD[name], t or None))
        # automatisch: Ziel-PLZ (zwei Stellen reichen) und Land; Gewicht, Ladungsträger und Tarif rechnet das Programm
        self.fracht_auto = QCheckBox("Fracht automatisch berechnen")
        self.fracht_auto.setToolTip("Fracht bei jeder Änderung aus Ziel-PLZ, Gewicht der Positionen, Packvorschlag und "
                                    "automatisch gewähltem Tarif rechnen (Tarifkopie beim Setzen des Hakens bzw. "
                                    "Ändern der PLZ)")
        self.fracht_plz, self.fracht_land = QLineEdit(), QLineEdit()
        self.fracht_plz.setPlaceholderText("z. B. 25")
        self.fracht_plz.setMaxLength(10)
        self.fracht_plz.setMaximumWidth(80)
        self.fracht_land.setMaxLength(2)
        self.fracht_land.setMaximumWidth(40)
        self.fracht_auto.toggled.connect(lambda an: seite.fracht_auto_setzen(an))
        self.fracht_plz.editingFinished.connect(lambda: seite.fracht_ziel_setzen(self.fracht_plz.text(),
                                                                                  self.fracht_land.text()))
        self.fracht_land.editingFinished.connect(lambda: seite.fracht_ziel_setzen(self.fracht_plz.text(),
                                                                                   self.fracht_land.text()))
        ziel = QWidget()
        zl = QHBoxLayout(ziel)
        zl.setContentsMargins(0, 0, 0, 0)
        zl.addWidget(self.fracht_plz)
        zl.addWidget(QLabel("Land"))
        zl.addWidget(self.fracht_land)
        zl.addStretch(1)
        # Raster: neben der Kalkulation untereinander (schmal), unter ihr in zwei Zeilen (fracht_raster_setzen)
        self.fracht_raster = QGridLayout()
        self.fracht_raster.setContentsMargins(0, 0, 0, 0)
        self.fracht_raster.setHorizontalSpacing(6)
        self.fracht_raster.setVerticalSpacing(4)
        self._fracht_zellen = (QLabel("Frachtart"), self.fracht_modus, QLabel("Fracht verteilen"), self.fracht_umlage,
                               self.fracht_auto, QLabel("Ziel-PLZ"), ziel)
        frl.addLayout(self.fracht_raster)
        self.fracht_text = QLabel()
        self.fracht_text.setWordWrap(True)
        self.fracht_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        frl.addWidget(self.fracht_text)
        self.fracht_rechts = None
        self.karten_anordnen(False)
        offen = self.s.db.einstellung(KALK_OFFEN_EINSTELLUNG)
        self.kalkulation_aufklappen(offen if isinstance(offen, bool) else False)   # Vorgabe: Kurzzeile, Positionen vorn
        offen = self.s.db.einstellung(FRACHT_OFFEN_EINSTELLUNG)
        self.fracht_aufklappen(offen if isinstance(offen, bool) else False)
        lay.addStretch(1)

    def kalkulation_aufklappen(self, offen=True, merken=False):
        """Karte Kalkulation auf- oder zuklappen; zugeklappt steht die Kurzfassung in der Titelzeile.
        merken = Wahl des Benutzers für alle Angebote speichern."""
        self.kalk_knopf.setChecked(offen)
        self.kalk_knopf.setArrowType(Qt.DownArrow if offen else Qt.RightArrow)
        self.kalk_inhalt.setVisible(offen)
        self.kalk_kurz.setVisible(not offen)
        if merken:
            self.s.db.einstellung_setzen(KALK_OFFEN_EINSTELLUNG, offen)
            self.s.oben_anpassen()

    def feld_zeigen(self, name):
        """Angebots-Check „Hinspringen“: Kopf (bzw. Erweiterte Einstellungen) aufklappen und das Feld fokussieren.
        name = Feld des Angebotskopfs oder 'lieferzeit'. Ergebnis: das Eingabefeld oder None."""
        w = self.lz_art if name == "lieferzeit" else self.felder.get(name) or self.erweitert.get(name)
        if w is None:
            return None
        self.kopf_aufklappen(True)
        if name in self.erweitert:
            self.erweitert_bereich.aufklappen(True)
        w.setFocus()
        return w

    def kopf_aufklappen(self, offen=True, automatisch=False):
        """Angebotskopf auf- oder zuklappen; zugeklappt steht die Kurzfassung in der Titelzeile. Eine Wahl von Hand
        gilt für dieses Angebot, solange es offen ist; automatisch klappt nur, solange nichts gewählt wurde."""
        if automatisch and (self._kopf_gewaehlt is not None or offen == self.kopf_inhalt.isVisibleTo(self)
                            and self.kopf_knopf.isChecked() == offen):
            return
        if not automatisch:
            self._kopf_gewaehlt = offen
        self.kopf_knopf.setChecked(offen)
        self.kopf_knopf.setArrowType(Qt.DownArrow if offen else Qt.RightArrow)
        self.kopf_inhalt.setVisible(offen)
        self.kopf_kurz.setVisible(not offen)
        self.s.oben_anpassen()

    def kopf_offen(self):
        return self.kopf_knopf.isChecked()

    def _kopf_kurzfassung(self):
        """'A-2026-0041 · 10233 Anlagenbau Hessler · T03 · 6.000 mm · Lieferzeit …' für den zugeklappten Kopf."""
        k = self.s.kopf
        kunde = " ".join(str(x) for x in (k.get("kundennr"), k.get("kunde")) if x)
        teile = [f"<b>{k.get('nummer') or 'ohne Nummer'}</b>", kunde or "<i>kein Kunde</i>",
                 k.get("maschine") or "", f"{_z(k.get('stange'), 0)} mm" if k.get("stange") else "",
                 datum_text(k.get("datum")) if k.get("datum") else ""]
        lz = lieferzeit_text(k)
        if lz:
            teile.append(lz.rstrip("."))
        if k.get("bemerkung"):
            teile.append(str(k["bemerkung"]))
        self.kopf_kurz.setText("   " + " · ".join(t for t in teile if t))
        self.kopf_kurz.setToolTip("Klicken zum Aufklappen")

    def kopf_ausgefuellt(self):
        return bool(self.s.kopf.get("kunde") and self.s.positionen)

    def fracht_aufklappen(self, offen=True, merken=False):
        """Karte Fracht auf- oder zuklappen; zugeklappt steht Frachtart und Betrag in der Titelzeile."""
        self.fracht_klapp.setChecked(offen)
        self.fracht_klapp.setArrowType(Qt.DownArrow if offen else Qt.RightArrow)
        self.fracht_inhalt.setVisible(offen)
        self.fracht_kurz.setVisible(not offen)
        if merken:
            self.s.db.einstellung_setzen(FRACHT_OFFEN_EINSTELLUNG, offen)
            self.s.oben_anpassen()

    def kalk_offen(self):
        return self.kalk_knopf.isChecked()

    def _kurzfassung(self):
        """Kalkulationswerte ungleich 0 in einer Zeile, z. B. 'Zuschlag Material 10 % · Gewinn 10 % · …'."""
        teile = []
        for _, namen in GRUPPEN:
            for name in namen:
                v = self.wert(name)
                if kopf_sichtbar(name, v) and name not in getattr(self, "_nicht_vorhanden", ()):
                    fd = KOPF_FELD[name]
                    titel, einheit = fd.titel, ""
                    if "[" in titel:
                        titel, einheit = titel.split("[", 1)
                        einheit = einheit.rstrip("]")
                    teile.append(f"{titel.strip()} {_z(v, fd.stellen if fd.stellen is not None else (0 if fd.art == "ganz" else 2))} {einheit}".strip())
        if self.s.kopf.get("mindestpreis_anwenden") == "nein":
            teile.append("ohne Mindestauftragswert")
        n = getattr(self, "_n_abweichend", 0)
        self.kalk_kurz.setText("   " + " · ".join(teile)
                               + (f"   <b style='color:{ORANGE}'>({n} abweichend von den Einstellungen)</b>" if n else ""))
        self.kalk_kurz.setToolTip("\n".join(teile))

    def _gruppen_anordnen(self, spalten):
        """Gruppen nebeneinander (breites Fenster) oder 2 × 2 (schmales Fenster)."""
        if spalten == self._spalten_gruppen:
            return
        self._spalten_gruppen = spalten
        for i, g in enumerate(self.gruppen_boxen):
            self.gruppen_raster.removeWidget(g)
        for c in range(4):
            self.gruppen_raster.setColumnStretch(c, 0)
        for i, g in enumerate(self.gruppen_boxen):
            self.gruppen_raster.addWidget(g, i // spalten, i % spalten)
        for c in range(spalten):
            self.gruppen_raster.setColumnStretch(c, 1)

    def karten_anordnen(self, rechts):
        """Fracht rechts neben der Kalkulation (breite Seite) oder darunter."""
        if rechts == self.fracht_rechts:
            return
        self.fracht_rechts = rechts
        for w in (self.kalk_karte, self.fracht_karte):
            self.karten.removeWidget(w)
        if rechts:          # oben bündig, jede Karte so hoch wie ihr Inhalt
            self.karten.addWidget(self.kalk_karte, 0, 0, Qt.AlignTop)
            self.karten.addWidget(self.fracht_karte, 0, 1, Qt.AlignTop)
        else:
            self.karten.addWidget(self.kalk_karte, 0, 0)
            self.karten.addWidget(self.fracht_karte, 1, 0)
        self.karten.setColumnStretch(0, 3 if rechts else 1)
        self.karten.setColumnStretch(1, 1 if rechts else 0)
        # Felder der Fracht: rechts schmal untereinander, unten in zwei Zeilen nebeneinander
        art_t, art, umlage_t, umlage, auto, ziel_t, ziel = self._fracht_zellen
        for w in self._fracht_zellen:
            self.fracht_raster.removeWidget(w)
        for c in range(5):
            self.fracht_raster.setColumnStretch(c, 0)
        if rechts:
            lage = ((art_t, 0, 0, 1), (art, 0, 1, 1), (umlage_t, 1, 0, 1), (umlage, 1, 1, 1), (auto, 2, 0, 2),
                    (ziel_t, 3, 0, 1), (ziel, 3, 1, 1))
            self.fracht_raster.setColumnStretch(1, 1)
        else:
            lage = ((art_t, 0, 0, 1), (art, 0, 1, 1), (umlage_t, 0, 2, 1), (umlage, 0, 3, 1), (auto, 1, 0, 2),
                    (ziel_t, 1, 2, 1), (ziel, 1, 3, 1))
            self.fracht_raster.setColumnStretch(4, 1)
        for w, r, c, n in lage:
            self.fracht_raster.addWidget(w, r, c, 1, n)

    def breite_anpassen(self, breite):
        """Von der Angebotsseite bei Größenänderung aufgerufen (Breite der ganzen Seite)."""
        self._gruppen_anordnen(4 if breite >= 1600 else 2)
        self.karten_anordnen(breite >= FRACHT_RECHTS_AB)

    # -------------------------------------------------------------- Eingaben
    def _eingabe(self, fd, ablage):
        s = self.s
        if fd.name == "kundennr":       # Kunde aus dem Kundenstamm wählen oder Nummer frei eintippen
            w = QComboBox()
            w.setEditable(True)
            w.setInsertPolicy(QComboBox.NoInsert)
            w.lineEdit().setPlaceholderText("Kunde wählen oder Nummer eintippen")
            w.activated.connect(lambda i, w=w: s.kunde_waehlen(w.itemData(i)))
            w.lineEdit().editingFinished.connect(lambda w=w: s.kunde_waehlen(_kundennr(w.currentText())))
            Doppelklick(w.lineEdit(), s.kunde_zeigen, "Doppelklick: Kunde im Reiter Kunden öffnen")
        elif fd.art == "datum":
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setDisplayFormat("dd.MM.yyyy")
            w.editingFinished.connect(lambda fd=fd, w=w: s._kopf_speichern(fd, w.date().toString("yyyy-MM-dd")))
        elif fd.art == "auswahl":
            w = QComboBox()
            w.currentTextChanged.connect(lambda t, fd=fd: s._kopf_speichern(fd, t or None))
        elif fd.art == "ganz":
            w = RechenSpinGanz()
            w.setRange(int(fd.von), int(fd.bis))
            w.setGroupSeparatorShown(True)
            w.setSingleStep(100 if fd.bis > 1000 else 1)
            w.setAlignment(Qt.AlignRight)
            w.editingFinished.connect(lambda fd=fd, w=w: s._kopf_speichern(fd, w.value()))
        elif fd.art == "zahl":
            w = RechenSpin()
            w.setRange(fd.von, fd.bis)
            w.setDecimals(fd.stellen or 2)
            w.setGroupSeparatorShown(True)
            w.setAlignment(Qt.AlignRight)
            if fd.name in KALK_NAMEN:         # 0 ist hier ein gültiger Wert (leer hieße: wie Einstellungen)
                w.editingFinished.connect(lambda fd=fd, w=w: s._kopf_speichern(fd, round(w.value(), 4)))
            else:
                w.editingFinished.connect(lambda fd=fd, w=w: s._kopf_speichern(fd, round(w.value(), 2) or None))
        else:
            w = QLineEdit()
            w.editingFinished.connect(lambda fd=fd, w=w: s._kopf_speichern(fd, w.text().strip() or None))
            if fd.name == "kunde":
                Doppelklick(w, s.kunde_zeigen, "Doppelklick: Kunde im Reiter Kunden öffnen")
        if isinstance(w, (QSpinBox, QDoubleSpinBox)):
            w.setMinimumWidth(90)
        ablage[fd.name] = w
        return w

    def wert(self, name):
        """Wert eines Kopffelds wie angezeigt (ältere Angebote ohne Kalkulationswert: Wert der Einstellungen)."""
        v = self.s.kopf.get(name)
        if v is None and name in KALK_NAMEN and name not in KALK_OHNE_VORGABE:
            v = (self.s.einst.get(name) or 0) * (100 if name in KALK_PROZENT else 1)
        return v

    def anzeigen(self):
        s = self.s
        for ablage in (self.felder, self.erweitert):
            for name, w in ablage.items():
                v = self.wert(name)
                if name == "kundennr":
                    w.clear()
                    for kd in s.db.zeilen("kunden"):
                        if kd.get("kundennr"):
                            w.addItem(f"{kd['kundennr']} – {kd.get('name') or ''}", kd["kundennr"])
                    w.setCurrentIndex(w.findData(v) if v else -1)
                    w.setEditText(w.currentText() if v and w.findData(v) >= 0 else (v or ""))
                elif isinstance(w, QDateEdit):
                    w.setDate(QDate.fromString(v, "yyyy-MM-dd") if v else QDate.currentDate())
                elif isinstance(w, QComboBox):
                    w.clear()
                    w.addItems(s.k.auswahl("maschine"))
                    if v and v not in s.k.maschinen:
                        w.addItem(v)
                    w.setCurrentText(v or "")
                elif isinstance(w, QSpinBox):
                    w.setValue(int(v or 0))
                elif isinstance(w, QDoubleSpinBox):
                    w.setValue(v or 0)
                else:
                    w.setText(v or "")
        self._lieferzeit_anzeigen()
        k = s.kopf.get("bearbeiter")
        name = teilen.mitarbeiter(s.db, k).get("name") if k else None
        self.bearbeiter.setText(f"{k} – {name}" if k and name else k or "–")
        self.mat_vorgabe.blockSignals(True)
        self.mat_vorgabe.setCurrentText(s.kopf.get("material_vorgabe") or EIGENMATERIAL)
        self.mat_vorgabe.blockSignals(False)
        betrag = rechnen.einstellungen_fest(s.tabellen, s.db.einstellungen()).get("mindestpreis")
        self.mindest_an.blockSignals(True)
        self.mindest_an.setChecked(s.kopf.get("mindestpreis_anwenden") != "nein")
        self.mindest_an.setText(f"Mindestauftragswert anwenden ({_z(betrag)} € netto)"
                                if isinstance(betrag, (int, float)) and betrag > 0 else
                                "Mindestauftragswert anwenden (0 €)")
        self.mindest_an.blockSignals(False)
        self._abweichungen_anzeigen()
        self.sichtbarkeit()
        self._kurzfassung()
        self._kopf_kurzfassung()
        self._maschine_anzeigen()
        self._fracht_anzeigen()

    def abweichungen(self):
        """[(Feld, Wert, Standard)] der Kalkulationswerte und Texte der Stundensätze/Zeitvorgaben, die von den
        Einstellungen bzw. Stammdaten abweichen."""
        s = self.s
        kalk = kalk_abweichungen(s.kopf, s.db.kalkulation_vorgaben())
        zeiten = rechnen.zeitbasis_abweichungen(s.kopf.get("zeitbasis"), s.db.zeitbasis_vorgabe(s.kopf.get("maschine")))
        return kalk, zeiten

    def _abweichungen_anzeigen(self):
        kalk, zeiten = self.abweichungen()
        abw = {f.name: std for f, _, std in kalk}
        for ablage in (self.felder, self.erweitert):
            for name, w in ablage.items():
                if name not in KALK_NAMEN:
                    continue
                fd = KOPF_FELD[name]
                if name in abw:
                    w.setStyleSheet(f"background: {GELB};")
                    w.setToolTip(f"Weicht ab: Standard (Einstellungen) {_wert_text(fd, abw[name])}")
                else:
                    w.setStyleSheet("")
                    w.setToolTip("wie in den Einstellungen")
        teile = [f"{_kurz(f.titel)} {_wert_text(f, w)} statt {_wert_text(f, std)}" for f, w, std in kalk] + zeiten
        n = len(teile)
        self.abweichung_text.setVisible(bool(n))
        self.abweichung_text.setText(
            f"{n} {'Wert weicht' if n == 1 else 'Werte weichen'} von den Einstellungen ab: " + "; ".join(teile) + "."
            if n else "")
        self._n_abweichend = n

    def _lieferzeit_anzeigen(self):
        k = self.s.kopf
        art = k.get("lieferzeit_art") or ""
        for w, v in ((self.lz_art, art), (self.lz_wert, _lz_anzeige(art, k.get("lieferzeit_wert"))),
                     (self.lz_zusatz, k.get("lieferzeit_zusatz") or "")):
            w.blockSignals(True)
            if isinstance(w, QComboBox):
                w.setCurrentIndex(w.findText(v))
            else:
                w.setText(v)
            w.blockSignals(False)
        self.lz_wert.setEnabled(art not in ("", NUR_TEXT))
        self.lz_wert.setPlaceholderText(LIEFERZEIT_HILFE.get(art, ""))
        self.lz_wert.setToolTip(LIEFERZEIT_HILFE.get(art, ""))
        text = lieferzeit_text(k)
        self.lz_vorschau.setText(f"Im Angebot: {text}" if text else
                                 "Keine Lieferzeit im Angebot: es gilt der Text der Bedingungen (Einstellungen).")
        # mit Lieferzeit zeigen die Felder schon alles: Satz im Angebot nur als Tooltip, spart eine Zeile
        self.lz_vorschau.setVisible(not text)
        self.lz_art.setToolTip((self.lz_vorschau.text() + "\n\n" if text else "") + LIEFERZEIT_TOOLTIP)
        self.lz_zusatz.setToolTip(self.lz_vorschau.text() if text else "")

    def _fracht_anzeigen(self):
        s = self.s
        m, u = fracht_angebot.modus(s.kopf), fracht_angebot.umlage(s.kopf)
        self.fracht_modus.setCurrentText(m)
        self.fracht_umlage.setCurrentText(u)
        an = fracht_angebot.auto(s.kopf)
        for w, v in ((self.fracht_auto, an), (self.fracht_plz, s.kopf.get("fracht_plz") or ""),
                     (self.fracht_land, s.kopf.get("fracht_land") or "")):
            w.blockSignals(True)
            w.setChecked(v) if isinstance(w, QCheckBox) else w.setText(v)
            w.blockSignals(False)
        self.fracht_modus.setEnabled(not an)
        for ablage in (self.felder, self.erweitert):     # berechnet: Betrag kommt aus der Frachtberechnung
            w = ablage.get("fracht")
            if w is not None:
                w.setReadOnly(m == fracht_angebot.BERECHNET)
                w.setToolTip("aus „Fracht berechnen …“ (Frachtart berechnet)" if m == fracht_angebot.BERECHNET
                             else "")
        betrag = fracht_angebot.wirksam(s.kopf)
        d = fracht_angebot.daten(s.kopf) or {}
        werte = [rechnen.position_werte(p, s.kopf, s.k, s.tabellen) if position_aktiv(p) else None
                 for p in s.positionen]
        if an:
            b, info, fehler = fracht_angebot.betrag_angebot(s.kopf, s.positionen, werte)
            betrag = b or 0
            if fehler:
                text = f"<span style='color:#B42318'><b>{fehler}.</b> Die Kalkulation rechnet bis dahin ohne Fracht.</span>"
            else:
                text = f"Automatisch: {info or _z(betrag) + ' €'}"
                if d.get("zone"):
                    text += f"; {d['zone']}"
                text += ". In den Staffelpreisen rechnet jede Menge ihre eigene Fracht."
            for h in d.get("hinweise") or ():
                if "teurere" in h or "Beispieltarif" in h or "Richtwert" in h:
                    text += f"<br><span style='color:#7A5A00'>{h}</span>"
        elif m == fracht_angebot.BERECHNET:
            text = f"Berechnet: {d.get('text') or _z(betrag) + ' €'}"
            sd = d.get("sendung") or {}
            if sd.get("plz"):
                text += f", nach {(sd.get('land') or 'DE')} {sd['plz']}"
            text += ". In den Staffelpreisen rechnet jede Menge ihre eigene Fracht."
        elif m == fracht_angebot.MANUELL:
            text = (f"Von Hand: {_z(betrag)} € (Feld Frachtkosten), in den Staffelpreisen für alle Mengen gleich."
                    if betrag else "Keine Frachtkosten eingetragen.")
        else:
            text = f"{m}: 0 € in der Kalkulation, Hinweis im Angebot."
        _, hinweis, _ = fracht_angebot.anteile(s.positionen, werte, betrag, u)
        if hinweis:
            text += f"<br><span style='color:#7A5A00'>{hinweis}.</span>"
        self.fracht_text.setText(text)
        kurz = text.split("<br>")[0]
        self.fracht_kurz.setText("   " + kurz + (" ⚠" if hinweis else ""))
        self.fracht_kurz.setToolTip(text)

    def sichtbarkeit(self):
        """Optionale Felder mit 0 in die Erweiterten Einstellungen, alle anderen in die Hauptansicht."""
        versteckt = 0
        # Handling Kundenmaterial nur, wenn es Kundenmaterial gibt (Position oder Vorgabe) oder ein Wert eingetragen ist
        kunde = any(rechnen.beigestellt(p) for p in self.s.positionen) or \
            self.s.kopf.get("material_vorgabe") == KUNDENMATERIAL
        # Aufschlag Bleche bzw. Zukaufteile nur, wenn das Angebot Bleche bzw. andere Zukaufteile hat (Patrick 25.10.2026)
        blech_ids = set(self.s.tabellen.get("blech_artikel") or ())
        arten = {zukauf.ist_blech(e, blech_ids) for p in self.s.positionen if position_aktiv(p)
                 for e in zukauf.eintraege(p)}
        vorhanden = {"aufschlag_blech": True in arten, "aufschlag_zukauf": False in arten}
        self._nicht_vorhanden = {n for n, da in vorhanden.items() if not da}     # auch nicht in der Kurzfassung
        gezeigt = set()
        for name, (b, w) in self.zeilen.items():
            zeigen = kopf_sichtbar(name, self.wert(name))
            weg = name == "handling_beistellung" and not zeigen and not kunde or not vorhanden.get(name, True)
            zeigen = zeigen and not weg
            b.setVisible(zeigen)
            w.setVisible(zeigen)
            be, we = self.zeilen_erweitert[name]
            be.setVisible(not zeigen and not weg)
            we.setVisible(not zeigen and not weg)
            # Rüsten in € leer = Minuten (kein Wert auf 0): nur unter Erweiterte Einstellungen, nicht mitgezählt
            versteckt += not zeigen and not weg and not (name in RUESTEN_EUR and self.wert(name) is None)
            if zeigen:
                gezeigt.add(name)
        for titel, (leer, namen) in self.gruppen_leer.items():
            leer.setVisible(not gezeigt & set(namen) and titel != "Zeit und Rüsten")
        self.erweitert_leer.setVisible(versteckt == 0)
        self.erweitert_bereich.setze_titel(
            f"Erweiterte Einstellungen ({versteckt} {'Wert' if versteckt == 1 else 'Werte'} auf 0)" if versteckt
            else "Erweiterte Einstellungen")

    def _maschine_anzeigen(self):
        m = rechnen.maschine(self.s.kopf, self.s.k)
        if not m:
            self.maschinenwerte.setText("<span style='color:#B42318'>Maschine fehlt oder ist unbekannt.</span>")
            self.maschinen_bereich.setze_titel("Maschinenparameter: Maschine fehlt oder ist unbekannt")
            for name, (b, w, _) in self.maschine_kalk.items():
                if name != "stangenwechsel":
                    w.setText("–")
            return
        teile, kurz = [], []
        for name, titel, einheit, stellen, rolle in MASCHINENPARAMETER:
            v = m.get(name)
            if sichtbar(v, rolle):
                text = f"{_z(v, stellen)} {einheit}" if v is not None else "nicht gesetzt"
                teile.append(f"<tr><td>{titel}</td><td align='right'>&nbsp;&nbsp;{text}</td></tr>")
                if rolle == MASCHINE:
                    kurz.append(f"{titel.split(' je ')[0]} {text}")
        self.maschinenwerte.setText("<table cellpadding='1'>" + "".join(teile) + "</table>")
        self.maschinen_bereich.setze_titel(f"Maschinenparameter {m.get('maschinen_id') or ''}: " + " · ".join(kurz))
        # Zeitwerte und Stundensatz aus dem Snapshot des Angebots (damit rechnet der Preis), nicht aus den Stammdaten
        zb = rechnen.zeitbasis(self.s.kopf, self.s.k, self.s.tabellen)["maschine"]
        vorgabe = self.s.db.zeitbasis_vorgabe(self.s.kopf.get("maschine"))["maschine"]
        stellen = {n: st for n, _, _, st in MASCHINE_KALK}
        for name, (b, w, einheit) in self.maschine_kalk.items():
            v = zb.get(name)
            if name == "stangenwechsel_sn" and v is None:       # Snapshot vor 0.8.10: SN wie Stangenwechsel
                v = zb.get("stangenwechsel")
            if name == "stangenwechsel":
                w.blockSignals(True)
                w.setValue(int(round(rechnen._n(v))))
                w.blockSignals(False)
                abw = rechnen._n(v) != rechnen._n(vorgabe.get(name))
                w.setStyleSheet(f"background: {GELB};" if abw else "")
                w.setToolTip(f"Weicht ab: Standard (Stammdaten Maschine) {_z(vorgabe.get(name), 0)} s" if abw else
                             "Stangenwechsel je Stange ohne feste Schweißnaht, nur für dieses Angebot; Vorgabe aus den "
                             "Stammdaten Maschinen")
                continue
            w.setText(f"{_z(v, stellen[name])} {einheit}")
            # Rüstzeit je Maschine 0 min: Zeile weg (Patrick 25.10.2026)
            zeigen = name != "ruestzeit" or not ist_null(v)
            b.setVisible(zeigen)
            w.setVisible(zeigen)


def _kundennr(text):
    """'K-1001 – Beispiel GmbH' (Eintrag der Kundenauswahl) -> 'K-1001'; frei eingetippt bleibt der Text."""
    return str(text or "").split(" – ")[0].strip()


class UebersichtRahmen(QScrollArea):
    """Rollbereich der Übersicht rechts: rollt nur senkrecht; die Mindestbreite folgt dem Inhalt (z. B. lange Zeilen
    im Preisaufbau oder breite Beträge), damit rechts nichts abgeschnitten wird (Design-Prüfung D3)."""
    HOECHSTENS = 560        # px: breiter wird die Spalte auch bei sehr langen Zeilen nicht

    def __init__(self, inhalt, minimum):
        super().__init__()
        self._minimum = minimum
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWidget(inhalt)
        self.setMinimumWidth(minimum)
        inhalt.installEventFilter(self)

    def noetige_breite(self):
        w = self.widget()
        return max(self._minimum, min(self.HOECHSTENS, w.minimumSizeHint().width()
                                      + self.verticalScrollBar().sizeHint().width() + 2))

    def eventFilter(self, obj, ereignis):
        if obj is self.widget() and ereignis.type() == QEvent.LayoutRequest:
            QTimer.singleShot(0, self._breite_anpassen)
        return False

    def _breite_anpassen(self):
        if self.widget() is not None and self.minimumWidth() != (b := self.noetige_breite()):
            self.setMinimumWidth(b)


class UebersichtBereich(QWidget):
    """Rechte Seite: Stand der Optimierung, Meldungen, Kennzahlen und Kostenübersicht."""

    STAND = {"aktuell": ("Optimierung abgeschlossen", "stand_ok"),
             "noch nicht optimiert": ("Noch nicht optimiert", "stand_offen")}

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        k, kl = karte("Übersicht")
        self.stand = QLabel()
        self.stand.setAlignment(Qt.AlignCenter)
        self.stand.setMinimumHeight(28)
        kl.addWidget(self.stand)
        # festgeschriebene Materialpreise und Schneiddaten (beim Angebots-PDF gespeichert)
        zeile = QHBoxLayout()
        self.preisstand = QLabel()
        self.preisstand.setWordWrap(True)
        self.preisstand.setTextInteractionFlags(Qt.TextSelectableByMouse)
        zeile.addWidget(self.preisstand, 1)
        self.preise_knopf = QPushButton("Aktuelle Preise übernehmen …")
        self.preise_knopf.setToolTip("Materialpreise und Schneiddaten dieses Angebots auf die aktuellen Stammdaten "
                                     "setzen")
        zeile.addWidget(self.preise_knopf)
        kl.addLayout(zeile)
        # Herstellkosten und Verkaufspreis groß, ohne Rollen sichtbar
        preise = QHBoxLayout()
        preise.setSpacing(6)
        self.preis, self.preis_titel = {}, {}
        for name, titel, stil in (("herstell", "Herstellkosten", "preiswert_klein"),
                                  ("verkauf", "Verkaufspreis", "preiswert")):
            box = QFrame()
            box.setObjectName("preis")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(8, 4, 8, 4)
            bl.setSpacing(0)
            t = QLabel(titel)
            t.setObjectName("kennzahltitel")
            w = QLabel()
            w.setObjectName(stil)
            w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            w.setTextInteractionFlags(Qt.TextSelectableByMouse)
            bl.addWidget(t)
            bl.addWidget(w)
            self.preis[name] = w
            self.preis_titel[name] = (t, titel)
            preise.addWidget(box, 2 if name == "verkauf" else 1)   # Verkaufspreis ist die Hauptzahl (L5)
        kl.addLayout(preise)
        # Meldungen: Anzahl als Etikett, einzelne Meldungen aufklappbar
        self.meldungen = QLabel()
        self.meldungen.setWordWrap(True)
        self.meldungen.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.meldungen_bereich = Aufklapper("Meldungen", self.meldungen)
        kl.addWidget(self.meldungen_bereich)
        # Angebots-Check (früher Prüfen vor Freigabe): alle offenen Punkte vor dem Angebots-PDF (Kunde, Schnittplan, Meldungen, Bohrungen …)
        # Angebots-Check (Plan A2): Links check:<Ziel> verbindet die Angebotsseite (check_link)
        self.freigabe = QLabel()
        self.freigabe.setWordWrap(True)
        self.freigabe.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.freigabe_bereich = Aufklapper("Angebots-Check", self.freigabe)
        kl.addWidget(self.freigabe_bereich)
        # Wiederholteile (Plan A1): Positionen, die schon angeboten wurden; Links übernehmen / öffnen / hinspringen,
        # die Angebotsseite verbindet linkActivated (wiederholteil_link)
        self.wiederholteile = QLabel()
        self.wiederholteile.setWordWrap(True)
        self.wiederholteile.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.wiederholteile_bereich = Aufklapper("Wiederholteile", self.wiederholteile)
        self.wiederholteile_bereich.setVisible(False)
        kl.addWidget(self.wiederholteile_bereich)
        # Kennzahlen
        self.kennzahlen = QGridLayout()
        self.kennzahlen.setHorizontalSpacing(6)
        self.kennzahl = {}
        # ohne Gesamtlänge und Stangen: über verschiedene Abmessungen summiert nicht aussagekräftig
        for i, (name, titel) in enumerate((("positionen", "Positionen"), ("stueck", "Stückzahl"),
                                           ("gewicht", "Gewicht"))):
            box = QFrame()
            box.setObjectName("kennzahl")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(6, 4, 6, 4)
            bl.setSpacing(0)
            t = QLabel(titel)
            t.setObjectName("kennzahltitel")
            w = QLabel()
            w.setObjectName("kennzahlwert")
            bl.addWidget(t)
            bl.addWidget(w)
            self.kennzahl[name] = w
            self.kennzahlen.addWidget(box, 0, i)
        kl.addLayout(self.kennzahlen)
        # Kostenübersicht nach Gruppen, einzelne Kostenarten aufklappbar
        self.uebersicht = QLabel()          # Preisaufbau: Material → … → Herstellkosten → … → Verkaufspreis
        self.uebersicht.setWordWrap(True)   # lange Zeilen umbrechen statt die Spalte zu verbreitern (D3)
        self.uebersicht.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.uebersicht.setToolTip("Preisaufbau: Gruppen mit ▸ per Klick aufklappen")
        self.uebersicht.linkActivated.connect(self._gruppe_umschalten)
        self.offene_gruppen, self._kosten = set(), None
        kl.addWidget(self.uebersicht)
        self.einzeln = QLabel()
        self.einzeln.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.einzeln_bereich = Aufklapper("Kostenarten einzeln", self.einzeln)
        kl.addWidget(self.einzeln_bereich)
        # Kostenwasserfall (Layout-Plan L22): wie der Preisaufbau Stufe für Stufe zum Verkaufspreis kommt
        from .kostenbalken import Kostenwasserfall
        self.wasserfall = Kostenwasserfall()
        self.wasserfall_bereich = Aufklapper("Kostenwasserfall", self.wasserfall)
        kl.addWidget(self.wasserfall_bereich)
        # Zeiten je Arbeitsschritt (Reiter 'Zeiten & Arbeitskosten'), Zeilen mit 0 ausgeblendet
        self.zeiten = QLabel()
        self.zeiten.setWordWrap(True)
        self.zeiten.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.zeiten.setToolTip("Maschine und Personal mit ▸ per Klick aufklappen; Einzelheiten je Arbeitsschritt im "
                               "Reiter „Zeiten & Arbeitskosten“. Durchlaufzeit = Maschinenzeit + Personalzeit, die "
                               "nicht parallel zur Maschine läuft.")
        self.zeiten.linkActivated.connect(self._zeiten_umschalten)
        self.offene_zeiten, self._zeit_summen = set(), None
        kl.addWidget(self.zeiten)
        # Kosten je Schweißbaugruppe als Balken (D2); nur sichtbar, wenn das Angebot Baugruppen hat
        self.bg_inhalt = QWidget()
        self.bg_lay = QVBoxLayout(self.bg_inhalt)
        self.bg_lay.setContentsMargins(0, 0, 0, 0)
        self.bg_balken = []
        self.bg_bereich = Aufklapper("Schweißbaugruppen", self.bg_inhalt, offen=True)
        self.bg_bereich.setVisible(False)
        kl.addWidget(self.bg_bereich)
        kl.addStretch(1)
        lay.addWidget(k)

    def stand_setzen(self, stand):
        """Stand der Optimierung; ohne aktuelle Optimierung fehlen Material und Stangen, die Preise sind dann
        als vorläufig gekennzeichnet."""
        aktuell = stand == "aktuell"
        for name, (t, titel) in self.preis_titel.items():
            t.setText(titel if aktuell else f"{titel} (vorläufig)")
            w = self.preis[name]
            w.setStyleSheet("" if aktuell else "color: #7F8A99;")
            w.setToolTip("" if aktuell else "Ohne aktuelle Optimierung fehlen Material, Stangenwechsel und "
                                            "Verschnitt. Bitte optimieren.")
        self._stand_text(stand)

    def wird_berechnet(self):
        """Gleich optimiert das Programm selbst (Plan Angebotsablauf V7): statt eines vorläufigen Preises ohne
        Material „wird berechnet …“ zeigen, bis die Optimierung fertig ist (kosten_setzen schreibt dann die Preise)."""
        for name, (t, titel) in self.preis_titel.items():
            t.setText(titel)
            self.preis[name].setText("wird berechnet …")
            self.preis[name].setToolTip("Das Programm optimiert gleich selbst (Material, Stangen, Verschnitt).")

    def preisstand_setzen(self, preisbasis, abweichungen, verschickt=None, versand=None):
        """Hinweis, ob die Preisgrundlagen festgeschrieben sind und ob die Stammdaten seitdem abweichen; der Knopf
        erscheint nur bei Abweichungen. verschickt = Text, wenn der Preis vom verschickten Angebots-PDF abweicht."""
        zusatz = f"<br><span style='color:#B35C00'><b>{verschickt}</b></span>" if verschickt else ""
        if not isinstance(preisbasis, dict):
            self.preisstand.setText("<span style='color:#5F6B7A'>Preise: aktuelle Stammdaten (werden beim "
                                    "Angebots-PDF festgeschrieben)</span>")
            self.preisstand.setToolTip("")
        elif abweichungen:
            self.preisstand.setText(f"<span style='color:#7A5A00'><b>Preise festgeschrieben am "
                                    f"{datum_text(preisbasis.get('datum'))}</b>, Stammdaten seitdem geändert "
                                    f"({len(abweichungen)})</span>" + zusatz)
            self.preisstand.setToolTip("\n".join(abweichungen))
        else:
            self.preisstand.setText(f"<span style='color:#5F6B7A'>Preise festgeschrieben am "
                                    f"{datum_text(preisbasis.get('datum'))}</span>" + zusatz)
            self.preisstand.setToolTip("Materialpreise, Schneiddaten, Gewinde, Einstellungen, Profile und Maschine "
                                       "stimmen mit den Stammdaten überein.")
        if versand:                 # Verlauf der verschickten Angebots-PDFs (Versionsstand)
            self.preisstand.setToolTip((self.preisstand.toolTip() + "\n\n").lstrip() + "Versandverlauf:\n" + "\n".join(
                _versand_text(v) for v in versand))
        self.preise_knopf.setVisible(bool(isinstance(preisbasis, dict) and abweichungen))

    def _stand_text(self, stand):
        text, name = self.STAND.get(stand, ("Veraltet – Angebot oder Stammdaten geändert, bitte neu optimieren",
                                            "stand_veraltet"))
        self.stand.setText(text)
        self.stand.setObjectName(name)
        self.stand.setToolTip(f"Stand Optimierung: {stand}")
        self.stand.style().unpolish(self.stand)
        self.stand.style().polish(self.stand)

    def meldungen_setzen(self, meldungen):
        """meldungen: [(Pos., Statustext)] aller Positionen mit FEHLER, WARNUNG oder HINWEIS."""
        n = {art: sum(1 for _, t in meldungen if t.startswith(art)) for art in ("FEHLER", "WARNUNG", "HINWEIS")}
        teile = [f"{n['FEHLER']} {'Fehler'}", f"{n['WARNUNG']} {'Warnung' if n['WARNUNG'] == 1 else 'Warnungen'}",
                 f"{n['HINWEIS']} {'Hinweis' if n['HINWEIS'] == 1 else 'Hinweise'}"]
        if not meldungen:
            self.meldungen_bereich.setze_titel("Meldungen: keine Fehler oder Warnungen")
            self.meldungen_bereich.knopf.setObjectName("meldung_ok")
            self.meldungen.setText("Alle Positionen sind OK.")
        else:
            self.meldungen_bereich.setze_titel("Meldungen: " + " · ".join(t for t, a in zip(teile, n.values()) if a))
            self.meldungen_bereich.knopf.setObjectName("meldung_fehler" if n["FEHLER"] else "meldung_warnung")
            farbe = {"FEHLER": "#B42318", "WARNUNG": "#7A5A00", "HINWEIS": "#5F6B7A"}
            self.meldungen.setText("<br>".join(
                f"<span style='color:{farbe.get(t.split(':')[0], '#1F2937')}'>Pos. {_z(pos, 0) or '?'}: {t}</span>"
                for pos, t in meldungen))
        k = self.meldungen_bereich.knopf
        k.style().unpolish(k)
        k.style().polish(k)

    def freigabe_setzen(self, punkte):
        """punkte: angebot_check.punkte(...) (Paare (Art, Text) mit ziel und details)."""
        from html import escape
        from . import stil
        self.freigabe_punkte = punkte
        k = self.freigabe_bereich.knopf
        offen = [p for p in punkte if p[0] != "HINWEIS"]
        hinweise = len(punkte) - len(offen)
        zusatz = f" · {hinweise} Hinweis{'e' if hinweise > 1 else ''}" if hinweise else ""
        if not offen:
            self.freigabe_bereich.setze_titel("Angebots-Check: alles erledigt" + zusatz)
            k.setObjectName("meldung_ok")
        else:
            self.freigabe_bereich.setze_titel(f"Angebots-Check: {len(offen)} offene{'r' if len(offen) == 1 else ''} "
                                              f"Punkt{'e' if len(offen) > 1 else ''}" + zusatz)
            k.setObjectName("meldung_fehler" if any(a == "FEHLER" for a, _ in punkte) else "meldung_warnung")
        if not punkte:
            self.freigabe.setText("Kunde, Schnittplan, Positionen, Bohrungen, Fracht und Staffeln sind in Ordnung.")
        else:
            farbe = {"FEHLER": stil.ROT, "WARNUNG": stil.GELB_TEXT, "HINWEIS": stil.TEXT_GRAU}
            link = f"color:{stil.umsetzen(stil.AKZENT)}"
            zeilen = []
            for p in punkte:
                z = f"<span style='color:{stil.umsetzen(farbe[p[0]])}'>• {escape(p[1])}</span>"
                if getattr(p, "details", ""):
                    z += f" <span style='color:{stil.umsetzen(stil.TEXT_GRAU)}'>({escape(p.details)})</span>"
                if getattr(p, "ziel", None):
                    z += f" <a style='{link}' href='check:{p.ziel}'>Hinspringen</a>"
                zeilen.append(z)
            self.freigabe.setText("<br>".join(zeilen))
        k.style().unpolish(k)
        k.style().polish(k)

    def wiederholteile_setzen(self, eintraege):
        """eintraege: [(Zeile, Positionstext, Treffer-Liste)] (wiederholteile.suchen), nur Positionen mit Treffern."""
        from html import escape
        from .wiederholteile import SICHER, text
        n = len(eintraege)
        self.wiederholteile_bereich.setVisible(bool(n))
        if not n:
            self.wiederholteile.clear()
            return
        sicher = sum(1 for _, _, t in eintraege if t[0].art == SICHER)
        self.wiederholteile_bereich.setze_titel(
            f"Wiederholteile: {n} Position{'en' if n > 1 else ''} schon angeboten"
            + (f" ({sicher} sicher)" if sicher and sicher < n else ""))
        link = "color:#1F4E78"
        zeilen = []
        for zeile, titel, treffer in eintraege:
            t = treffer[0]
            aktionen = [f"<a style='{link}' href='hin:{zeile}'>Hinspringen</a>",
                        f"<a style='{link}' href='oeffnen:{t.angebot['id']}'>Angebot öffnen</a>"]
            if t.werte:
                aktionen.insert(0, f"<a style='{link}' href='werte:{zeile}'>Werte übernehmen …</a>")
            zeilen.append(f"💡 <b>{escape(titel)}</b>: {escape(text(treffer))}<br>"
                          f"<span style='color:{GRAU}'>{' · '.join(aktionen)}</span>")
        self.wiederholteile.setText("<br>".join(zeilen) + f"<br><span style='color:{GRAU}'>Der Preis wird nie "
                                    "übernommen, er entsteht immer neu aus der Kalkulation.</span>")

    def baugruppen_setzen(self, gruppen):
        """gruppen: [(Titel, [(Kostenteil, €)], [(größter Posten, €)])] je Schweißbaugruppe, Beträge je Baugruppe."""
        from .kostenbalken import Kostenbalken
        while self.bg_lay.count():
            w = self.bg_lay.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self.bg_balken = []
        for titel, teile, posten in gruppen:
            b = Kostenbalken(titel)
            b.setzen(teile)
            self.bg_lay.addWidget(b)
            self.bg_balken.append(b)
            if posten:
                t = QLabel("Größte Posten: " + ", ".join(f"{n} {_z(w)} €" for n, w in posten))
                t.setWordWrap(True)
                t.setStyleSheet(f"color: {GRAU};")
                self.bg_lay.addWidget(t)
        self.bg_bereich.setze_titel(f"Schweißbaugruppen: Kosten je Baugruppe ({len(gruppen)})")
        self.bg_bereich.setVisible(bool(gruppen))

    def kennzahlen_setzen(self, werte):
        for name, text in werte.items():
            self.kennzahl[name].setText(text)

    def kosten_setzen(self, kosten):
        """kosten: rechnen.kostenarten(...). Oben die Gruppen (rechnen.KOSTEN_GRUPPEN), aufklappbar jede Kostenart
        einzeln. Zeilen mit 0,00 € sind ausgeblendet, Herstellkosten und Verkaufspreis immer sichtbar."""
        betrag = {n: (t, w) for (t, w, _), (_, n, _) in zip(kosten, rechnen.KOSTENARTEN)}
        for name, w in self.preis.items():
            w.setText(f"{_z(betrag[name][1])} €")
        self._kosten = kosten
        linie = "border-top:1px solid #C9D0D8"
        html = (f"<table width='100%' cellpadding='1' cellspacing='0'><tr><td colspan='2' style='{linie}'>"
                f"<b>Preisaufbau</b></td></tr>")
        for titel, namen, summe in rechnen.KOSTEN_GRUPPEN:
            gesamt = sum(betrag[n][1] or 0 for n in namen)
            if summe:
                html += (f"<tr><td style='{linie}'><b>= {titel}</b></td>"
                         f"<td align='right' style='{linie}'><b>{_z(gesamt)} €</b></td></tr>")
            elif titel == "Material" or any(sichtbar(betrag[n][1]) for n in namen):     # Material immer
                zeichen = "" if titel == "Material" else "+ "
                einzeln = [n for n in namen if sichtbar(betrag[n][1])]
                if len(namen) == 1:
                    text = betrag[namen[0]][0]                                  # einzeln mit Mengenangabe
                elif titel in self.offene_gruppen:
                    text = f"<a href='{titel}' style='color:#1F2937;text-decoration:none'>▾ {titel}</a>"
                else:
                    text = f"<a href='{titel}' style='color:#1F2937;text-decoration:none'>▸ {titel}</a>"
                html += f"<tr><td>{zeichen}{text}</td><td align='right'>{_z(gesamt)} €</td></tr>"
                if len(namen) > 1 and titel in self.offene_gruppen:
                    for n in einzeln:
                        html += (f"<tr><td style='color:{GRAU};padding-left:14px'>{betrag[n][0]}</td>"
                                 f"<td align='right' style='color:{GRAU}'>{_z(betrag[n][1])} €</td></tr>")
        self.uebersicht.setText(html + "</table>")
        html = "<table width='100%' cellpadding='1' cellspacing='0'>"
        for t, w, fett in kosten:
            if fett:
                html += f"<tr><td><b>{t}</b></td><td align='right'><b>{_z(w)} €</b></td></tr>"
            elif sichtbar(w):
                html += f"<tr><td style='color:{GRAU}'>{t}</td><td align='right' style='color:{GRAU}'>{_z(w)} €</td></tr>"
        self.einzeln.setText(html + "</table>")
        self.wasserfall.setzen(kosten)

    def _gruppe_umschalten(self, titel):
        """Klick auf eine Gruppe im Preisaufbau: ihre Kostenarten auf- oder zuklappen."""
        self.offene_gruppen ^= {titel}
        if self._kosten is not None:
            self.kosten_setzen(self._kosten)

    def zeiten_setzen(self, k):
        """k: rechnen.zeit_summen(...). Zeiten und Arbeitskosten aufgeschlüsselt: Maschine und Personal aufklappbar je
        Arbeitsschritt (Zeit, Kosten), Rüstzeit als Teil der Maschinen- bzw. Personalzeit, Arbeitszeit gesamt,
        Durchlaufzeit und Zeit je Teil; Zeilen mit 0 ausgeblendet."""
        self._zeit_summen = k
        linie = "border-top:1px solid #C9D0D8"
        grau = f"color:{GRAU}"
        html = (f"<table width='100%' cellpadding='1' cellspacing='0'><tr><td colspan='3' style='{linie}'>"
                f"<b>Zeiten</b></td></tr>")
        n = 0
        titel = {"Maschine": ("Maschine", k["maschine_min"], k["maschinenkosten"], k.get("ruest_maschine_min", 0)),
                 "Personal": ("Personal", k["personal_min"], k["personalkosten"], k.get("ruest_personal_min", 0))}
        for art, schritte in k.get("gruppen") or ():
            name, minuten, kosten, ruest = titel[art]
            if not schritte:
                continue
            n += 1
            offen = art in self.offene_zeiten
            text = f"<a href='{art}' style='color:#1F2937;text-decoration:none'>{'▾' if offen else '▸'} {name}</a>"
            html += (f"<tr><td>{text}</td><td align='right'>{rechnen.zeit_text(minuten)}</td>"
                     f"<td align='right'>{_z(kosten)} €</td></tr>")
            if offen:
                for z in schritte:
                    zusatz = " (parallel)" if art == "Personal" and z["parallel"] else ""
                    html += (f"<tr><td style='{grau};padding-left:14px'>{z['schritt']}{zusatz}</td>"
                             f"<td align='right' style='{grau}'>{rechnen.zeit_text(z['gesamt_min'])}</td>"
                             f"<td align='right' style='{grau}'>{_z(z['kosten'])} €</td></tr>")
            if sichtbar(ruest):
                html += (f"<tr><td style='{grau};padding-left:14px'>davon Rüsten</td>"
                         f"<td align='right' style='{grau}'>{rechnen.zeit_text(ruest)}</td><td></td></tr>")
        if n:
            html += (f"<tr><td style='{linie}'><b>= Arbeitszeit gesamt</b></td>"
                     f"<td align='right' style='{linie}'><b>{rechnen.zeit_text(k['bearbeitung_min'])}</b></td>"
                     f"<td align='right' style='{linie}'><b>{_z(k['arbeitskosten'])} €</b></td></tr>")
            parallel = (f" (ohne {rechnen.zeit_text(k['parallel_min'])} parallel)"
                        if sichtbar(k.get("parallel_min", 0)) else "")
            html += (f"<tr><td>Durchlaufzeit{parallel}</td><td align='right'>{rechnen.zeit_text(k['durchlauf_min'])}"
                     "</td><td></td></tr>")
            if k.get("je_teil_min"):
                html += (f"<tr><td>Ø Arbeitszeit je Teil</td><td align='right'>{rechnen.zeit_text(k['je_teil_min'])}"
                         "</td><td></td></tr>")
            if sichtbar(k["sonstige"]):
                html += (f"<tr><td style='{grau}'>Kosten ohne Zeit (Festpreise, Fremdleistung)</td><td></td>"
                         f"<td align='right' style='{grau}'>{_z(k['sonstige'])} €</td></tr>")
        self.zeiten.setText(html + "</table>")
        self.zeiten.setVisible(bool(n))

    def _zeiten_umschalten(self, art):
        """Klick auf Maschine oder Personal in den Zeiten: Arbeitsschritte auf- oder zuklappen."""
        self.offene_zeiten ^= {art}
        if self._zeit_summen is not None:
            self.zeiten_setzen(self._zeit_summen)
