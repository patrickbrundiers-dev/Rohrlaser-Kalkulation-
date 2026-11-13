"""Oberer Teil der Angebotsseite: Angebotskopf, Maschinenparameter, Kalkulationseinstellungen und Übersicht.

Welche Felder und Kennzahlen sichtbar sind, entscheidet sichtbarkeit.py: optionale Werte mit 0 oder leer stehen
nicht in der Hauptansicht, sondern unter 'Erweiterte Einstellungen' (dort immer änderbar). Pflichtfelder,
Stammdaten und Maschinenparameter bleiben immer sichtbar. Gespeichert und gerechnet wird wie bisher.
"""
import re

from PySide6.QtCore import QDate, QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QFont, QPainter, QTextCursor, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from . import abruf, fracht_angebot, funktionen, hilfe, rechnen, teilen, zukauf
from .ausgabe import datum_text
from .fracht_angebot import MODI, UMLAGEN
from .angebot import (KALK_OHNE_VORGABE, EIGENMATERIAL, KUNDENMATERIAL, KALK_PROZENT, KALKULATION, KOPF, MATERIAL_HERKUNFT,
                      aktiv as position_aktiv, kalk_abweichungen, lieferzeit_eingabe, lieferzeit_text)
from .sichtbarkeit import MASCHINE, OPTIONAL, ist_null, kopf_sichtbar, sichtbar
from .stammdaten import MUSTER_DARSTELLUNG, MUSTER_UMLEGEN, zahl_als_text
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
    ("Verkauf und Gewinn", ("gewinn", "angebotsaufschlag", "pauschale_abmessung", "fracht", "eilzuschlag")),
    ("Zahlungsbedingungen", ("skonto", "skonto_tage", "zahlungsziel")),
    ("Kundenkonditionen", ("rabatt", "frachtfrei_ab", "mindestwert")),        # Vorschlag G7, 02.11.2026
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

LIEFERZEIT_TOOLTIP = ("Lieferzeit in einem Feld: „3 Wochen“ oder „10 AT“ (ab Auftragseingang), „KW 48“, „15.11.“ "
                      "(feste Termine) oder Freitext wie „nach Absprache“. Was hinter der Angabe steht (z. B. "
                      "„3 Wochen, Teillieferung möglich“), kommt als Zusatz dazu.")
# Fracht rechts neben der Kalkulation ab dieser Breite der Angebotsseite (darunter steht sie unter der Kalkulation)
FRACHT_RECHTS_AB = 1620      # Breite der Angebotsseite (seit 0.9.300 ohne Seitenleiste links: 1800 - 180)
KOMPAKT_UNTER = 760       # px Höhe der Angebotsseite (Laptop 1366 × 768): Karten flacher, Kalkulation + Fracht nebeneinander
RUESTEN_EUR = ("ruesten_angebot_eur", "ruesten_abmessung_eur")     # leer = Rüsten in Minuten × Stundensatz
# Gestaffelter Gewinn im Angebot (Patrick 08.11.2026): das Gewinnfeld steht auf diesem Wert und zeigt statt einer Zahl
# „gestaffelt · 30,0 %“ (wirksamer Satz nach der Rechnung); eine eingetippte Zahl ist ein fester Gewinn
GESTAFFELT = -1.0

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


class KurzZeile(QLabel):
    """Einzeilige Kurzfassung neben einem Aufklapp-Knopf (Kopf, Kalkulation, Fracht): passt der Text nicht in die
    Breite, endet er mit „…“ statt mitten im Wort abgeschnitten, und der Tooltip zeigt den ganzen Text (Prüfung
    29.10.2026, O5). Rich Text (fett, Farbe) bleibt erhalten."""
    gekuerzt_mit_tooltip = True         # für die Prüfung auf abgeschnittene Texte (texte_pruefen)

    def __init__(self):
        super().__init__()
        self._voll, self._tipp = "", ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text):
        self._voll = text or ""
        self._kuerzen()

    def text(self):             # immer der ganze Text (Tests, Dunkelmodus-Umfärben), angezeigt wird ggf. gekürzt
        return self._voll

    def setToolTip(self, text):
        self._tipp = text or ""
        self._kuerzen()

    def resizeEvent(self, ereignis):
        super().resizeEvent(ereignis)
        self._kuerzen()

    def _dokument(self, html):
        doc = QTextDocument()
        doc.setDefaultFont(self.font())
        doc.setDocumentMargin(0)
        doc.setHtml(html)
        return doc

    def _kuerzen(self):
        breite = self.contentsRect().width() - 2
        doc = self._dokument(self._voll)
        if breite <= 0 or doc.idealWidth() <= breite:
            QLabel.setText(self, self._voll)
            QLabel.setToolTip(self, self._tipp)
            return
        n = doc.characterCount() - 1
        lo, hi = 0, n               # größte Zeichenzahl, die mit „…“ noch passt (binäre Suche)
        while lo < hi:
            m = (lo + hi + 1) // 2
            if self._teil(m).idealWidth() <= breite:
                lo = m
            else:
                hi = m - 1
        QLabel.setText(self, self._teil(lo).toHtml())
        voll = doc.toPlainText().strip()
        QLabel.setToolTip(self, voll if not self._tipp or self._tipp == voll else f"{voll}\n\n{self._tipp}")

    def _teil(self, zeichen):
        doc = self._dokument(self._voll)
        c = QTextCursor(doc)
        c.setPosition(zeichen)
        c.movePosition(QTextCursor.End, QTextCursor.KeepAnchor)
        c.removeSelectedText()
        c.insertText("…")
        return doc


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
    if v.get("art") == "absage":        # Absagegrund (absage.py)
        t = f"{datum_text(v.get('datum'))}: abgelehnt – {v.get('grund') or 'ohne Angabe'}"
        if v.get("preis"):
            t += f" (Wettbewerb {_z(v['preis'])} €)"
        return t + (f": {v['bemerkung']}" if v.get("bemerkung") else "")
    if v.get("art") == "ab":            # Auftragsbestätigung (Plan 29.10.2026 1c)
        return (f"{datum_text(v.get('datum'))}: Auftragsbestätigung {v.get('nummer') or ''} – {_z(v.get('netto'))} € "
                f"netto ({v.get('datei') or 'PDF'})")
    if v.get("art") == "mail":          # Angebot per E-Mail (angebot_mail.py)
        from .angebot_mail import verlauf_text
        return verlauf_text(v)
    if v.get("art") == "gleitklausel":  # Materialpreis-Gleitklausel (gleitklausel.py)
        from .gleitklausel import verlauf_text
        return verlauf_text(v)
    if v.get("art") == "csv":
        return f"{datum_text(v.get('datum'))}: CSV-Export ({v.get('datei') or 'CSV'})"
    if v.get("art") == "nachtrag":      # Nachtrag des Kunden einsortiert (Automationen 03.11.2026, 5a)
        return (f"{datum_text(v.get('datum'))}: Nachtrag des Kunden ({v.get('datei') or 'Mail'})"
                + (f" – {v['text']}" if v.get("text") else ""))
    if v.get("art") == "bestellung":    # Bestellung des Kunden zugeordnet (1a)
        return (f"{datum_text(v.get('datum'))}: Bestellung des Kunden {v.get('bestellnr') or ''}".rstrip()
                + f" ({v.get('datei') or 'Mail'})" + (f" – {v['abweichungen']} Abweichung(en)"
                                                      if v.get("abweichungen") else ""))
    if v.get("art") == "bestellung_material":   # Material beim Lieferanten bestellt (8a)
        return f"{datum_text(v.get('datum'))}: Material bestellt bei {v.get('lieferant') or 'Lieferant'}"
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
        self._lay = lay
        self.kompakt = False

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
        self.kopf_kurz = KurzZeile()
        self.kopf_kurz.setCursor(Qt.PointingHandCursor)
        self.kopf_kurz.mousePressEvent = lambda _e: self.kopf_aufklappen(True)
        titelzeile.addWidget(self.kopf_knopf, 0, Qt.AlignLeft)     # aufgeklappt (ohne Kurzzeile) links, nicht mittig
        titelzeile.addWidget(self.kopf_kurz, 1)
        kl0.addLayout(titelzeile)
        # Kundenhinweis (Plan PROfirst G1): groß und farbig, auch bei zugeklapptem Kopf sichtbar
        self.kundenhinweis = QLabel()
        self.kundenhinweis.setObjectName("kundenhinweis")
        self.kundenhinweis.setWordWrap(True)
        self.kundenhinweis.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.kundenhinweis.setStyleSheet(f"QLabel#kundenhinweis {{ background:{GELB}; color:{GELB_TEXT}; "
                                         f"border:2px solid {ORANGE}; border-radius:6px; padding:6px 10px; "
                                         "font-size:11pt; font-weight:bold; }")
        self.kundenhinweis.setToolTip("Kundenhinweis aus dem Kundenstamm (Reiter Kunden, Spalte Kundenhinweis)")
        self.kundenhinweis.setVisible(False)
        kl0.addWidget(self.kundenhinweis)
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
        # Lieferzeit dieses Angebots in einem Feld (Verbesserungsplan 06.11.2026, E3): „3 Wochen“, „10 AT“, „KW 48“,
        # „15.11.“ oder Freitext; das Programm erkennt die Art, darunter steht der Satz im Angebot (ändert keine Preise)
        self.lz_feld = QLineEdit()
        self.lz_feld.setPlaceholderText("z. B. 3 Wochen, 10 AT, KW 48, 15.11. oder nach Absprache")
        self.lz_feld.setToolTip(LIEFERZEIT_TOOLTIP)
        self.lz_feld.editingFinished.connect(lambda: seite.lieferzeit_speichern(self.lz_feld.text()))
        lz = QHBoxLayout()
        lz.setContentsMargins(0, 0, 0, 0)
        lz.addWidget(self.lz_feld, 1)
        # Liefertermin nach freier Kapazität (Vorschlag V2, terminplan.py): nur mit Funktion Maschinenauslastung
        self.termin_knopf = QPushButton("Termin prüfen …")
        self.termin_knopf.setToolTip("Frühesten Liefertermin nach der Maschinenauslastung und der Material-Lieferzeit "
                                     "rechnen und mit der Lieferzeit des Angebots vergleichen")
        self.termin_knopf.clicked.connect(lambda: seite.termin_pruefen())
        lz.addWidget(self.termin_knopf)
        # Maschinenvergleich (Vorschlag F1): das Angebot auf allen Maschinen rechnen
        self.maschinen_knopf = QPushButton("Maschinen vergleichen …")
        self.maschinen_knopf.setToolTip("Das Angebot auf jeder Maschine rechnen (Laserzeit, Preis, Termin) und auf "
                                        "Wunsch umstellen")
        self.maschinen_knopf.clicked.connect(lambda: seite.maschinen_vergleichen())
        lz.addWidget(self.maschinen_knopf)
        # Zielpreis rückwärts (Vorschlag G1a): nötiger Gewinn, Marge, „Auf Zielpreis setzen“
        self.ziel_knopf = QPushButton("Zielpreis …")
        self.ziel_knopf.setToolTip("Zielpreis netto eingeben: das Programm zeigt den nötigen Gewinn, ob die "
                                   "Mindestmarge und die Preisuntergrenze halten, und stellt den Gewinn auf Wunsch um")
        self.ziel_knopf.clicked.connect(lambda: seite.zielpreis())
        lz.addWidget(self.ziel_knopf)
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
        self.kopf_karte = kopf
        self.einzeilig = False      # Laptop: Kopf, Kalkulation und Fracht zugeklappt in einer Zeile (Plan B1)

        # Kalkulationseinstellungen dieses Angebots
        vorgaben = QPushButton("Vorgaben aus Einstellungen")
        vorgaben.setToolTip("Zuschläge, Gewinn, Rüstzeit und Pauschalen wieder auf die Werte der Einstellungen setzen")
        vorgaben.clicked.connect(lambda: seite.kalkulation_zuruecksetzen())
        self.vorgaben_knopf = vorgaben
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
        self.kalk_kurz = KurzZeile()
        self.kalk_kurz.setStyleSheet(f"color: {GRAU};")
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
        # Verpackung (Vorschlag G2): Kosten aus den Stammdaten Verpackung, je Angebot abschaltbar
        self.verpackung_an = QCheckBox("Verpackung berechnen")
        self.verpackung_an.setToolTip("Packmittel aus Einstellungen → Verpackung als eigene Kostenart (ohne Gewinn). "
                                      "Ohne Haken (Kunde holt ab, eigene Gitterbox) keine Verpackungskosten.")
        self.verpackung_an.toggled.connect(
            lambda an: seite._kopf_speichern(KOPF_FELD["verpackung"], None if an else "nein"))
        # Musterteile (Patrick 28.10.2026): Kosten auf die Serie umlegen oder als eigene Zeile; nur mit Musterteilen
        self.muster_wahl = QWidget()
        ml = QHBoxLayout(self.muster_wahl)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.addWidget(QLabel("Musterkosten"))
        self.muster_darstellung = QComboBox()
        self.muster_darstellung.addItems(list(MUSTER_DARSTELLUNG))
        self.muster_darstellung.setToolTip("Musterteile (Spalte Muster) stehen mit 0 € im Angebot. Ihre Kosten mit "
                                           "Gewinn werden nach den Selbstkosten auf die Serienpositionen umgelegt "
                                           "oder stehen als eigene Zeile „Musterkosten einmalig“ im Angebot (ohne "
                                           "Serienposition immer so).")
        self.muster_darstellung.currentTextChanged.connect(
            lambda t: seite._kopf_speichern(KOPF_FELD["muster_darstellung"], None if t == MUSTER_UMLEGEN else t))
        ml.addWidget(self.muster_darstellung, 1)
        # Abruf-/Rahmenangebot (Patrick 30.10.2026): Haken, Fenster mit Jahres-/Abrufmenge, Kurzfassung
        self.abruf_wahl = QWidget()
        av = QVBoxLayout(self.abruf_wahl)
        av.setContentsMargins(0, 0, 0, 0)
        av.setSpacing(2)
        al = QHBoxLayout()
        self.abruf_an = QCheckBox("Abruf-/Rahmenangebot")
        self.abruf_an.setToolTip("Jahresmenge in Abrufen: Stückzahlen = kleinster Abruf, Rüsten und Fracht je Abruf, "
                                 "Programmierung und Musterteile auf die Jahresmenge verteilt, Rahmenbedingungen im "
                                 "Angebots-PDF")
        self.abruf_an.toggled.connect(lambda an: seite.abruf_umschalten(an))
        self.abruf_knopf = QPushButton("Abrufdaten …")
        self.abruf_knopf.clicked.connect(lambda: seite.abruf_bearbeiten())
        self.abruf_kurz = QLabel()
        self.abruf_kurz.setWordWrap(True)
        self.abruf_kurz.setStyleSheet(f"color: {GRAU};")
        al.addWidget(self.abruf_an)
        al.addWidget(self.abruf_knopf)
        self.gleit_knopf = QPushButton("Gleitklausel prüfen …")
        self.gleit_knopf.setToolTip("Materialklausel (Vorschlag K1): festgeschriebene Materialpreise gegen die aktuellen; "
                                    "über der Schwelle (Einstellung Materialklausel) neue Materialpreise übernehmen")
        self.gleit_knopf.clicked.connect(lambda: seite.gleitklausel_pruefen())
        al.addWidget(self.gleit_knopf)
        al.addStretch(1)
        av.addLayout(al)
        av.addWidget(self.abruf_kurz)
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
                if name == "gewinn":            # Knopf zurück auf den gestaffelten Gewinn (Patrick 08.11.2026)
                    w = self._gewinn_zeile(w)
                self.zeilen[name] = (b, w)
                form.addWidget(b, r, 0)
                form.addWidget(w, r, 1)
                r += 1
            if titel == "Verkauf und Gewinn":  # Mindestauftragswert ein/aus gehört zum Verkauf, spart eine Zeile
                form.addWidget(self.mindest_an, r + 1, 0, 1, 2)
                form.addWidget(self.muster_wahl, r + 2, 0, 1, 2)
                form.addWidget(self.abruf_wahl, r + 3, 0, 1, 2)
                form.addWidget(self.verpackung_an, r + 4, 0, 1, 2)
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
        self.fracht_kurz = KurzZeile()
        self.fracht_kurz.setStyleSheet(f"color: {GRAU};")
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
        # Entfernung (Patrick 11.11.2026): leer = aus den PLZ gerechnet (Platzhalter zeigt den Wert), sonst von Hand
        self.fracht_km = QLineEdit()
        self.fracht_km.setMaxLength(5)
        self.fracht_km.setMaximumWidth(60)
        self.fracht_km.setPlaceholderText("aus PLZ")
        self.fracht_km.setToolTip("Entfernung zum Ziel in Straßen-km. Leer: aus den PLZ gerechnet (Luftlinie × "
                                  "Umwegfaktor, Einstellungen › Frachtkosten); eingetragen: gilt dieser Wert für "
                                  "Zone und km-Preise (z. B. eigene Anlieferung)")
        self.fracht_km.editingFinished.connect(lambda: seite.fracht_km_setzen(self.fracht_km.text()))
        ziel = QWidget()
        zl = QHBoxLayout(ziel)
        zl.setContentsMargins(0, 0, 0, 0)
        zl.addWidget(self.fracht_plz)
        zl.addWidget(QLabel("Land"))
        zl.addWidget(self.fracht_land)
        zl.addWidget(QLabel("km"))
        zl.addWidget(self.fracht_km)
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
        if self.kompakt:
            self._karten_neu()
        if merken:
            self.s.db.einstellung_setzen(KALK_OFFEN_EINSTELLUNG, offen)
            self.s.oben_anpassen()

    def feld_zeigen(self, name):
        """Angebots-Check „Hinspringen“: Kopf (bzw. Erweiterte Einstellungen) aufklappen und das Feld fokussieren.
        name = Feld des Angebotskopfs oder 'lieferzeit'. Ergebnis: das Eingabefeld oder None."""
        w = self.lz_feld if name == "lieferzeit" else self.felder.get(name) or self.erweitert.get(name)
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
        if self.kompakt:
            self._karten_neu()
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
        if self.kompakt:
            self._karten_neu()
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
                if name == "gewinn" and self.gewinn_gestaffelt():
                    teile.append("Gewinn gestaffelt" + (f" {_z(v, 1)} %" if v is not None else ""))
                    continue
                # leere Felder (Rabatt, Eilzuschlag, Frachtfrei ab …) nicht als „Rabatt  %“ zeigen (Bugfix 08.11.2026)
                if v is None or v == "":
                    continue
                if kopf_sichtbar(name, v) and name not in getattr(self, "_nicht_vorhanden", ()):
                    fd = KOPF_FELD[name]
                    titel, einheit = fd.titel, ""
                    if "[" in titel:
                        titel, einheit = titel.split("[", 1)
                        einheit = einheit.rstrip("]")
                    teile.append(f"{titel.strip()} {_z(v, fd.stellen if fd.stellen is not None else (0 if fd.art == "ganz" else 2))} {einheit}".strip())
        if self.s.kopf.get("mindestpreis_anwenden") == "nein":
            teile.append("ohne Mindestauftragswert")
        if abruf.aktiv(self.s.kopf):
            teile.append("Abruf: " + abruf.kurz(self.s.kopf))
        n = getattr(self, "_n_abweichend", 0)
        # Hinweis auf Abweichungen vorn: hinten wurde er bei vielen Werten als Erstes abgeschnitten (Design-Prüfung)
        abweichend = f"<b style='color:{ORANGE}'>({n} abweichend von den Einstellungen)</b>   " if n else ""
        self.kalk_kurz.setText("   " + abweichend + " · ".join(teile))
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
        v = 1 if self.einzeilig else 0      # einzeilig: der Kopf steht in Spalte 0
        for c in range(3):
            self.karten.setColumnStretch(c, 0)
        if rechts:          # oben bündig, jede Karte so hoch wie ihr Inhalt
            self.karten.addWidget(self.kalk_karte, 0, v, Qt.AlignTop)
            self.karten.addWidget(self.fracht_karte, 0, v + 1, Qt.AlignTop)
        else:
            self.karten.addWidget(self.kalk_karte, 0, v)
            self.karten.addWidget(self.fracht_karte, 1, v)
        if self.einzeilig:
            self.karten.setColumnStretch(0, 5)
        self.karten.setColumnStretch(v, (2 if self.kompakt else 3) if rechts else 1)
        self.karten.setColumnStretch(v + 1, 1 if rechts else 0)
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

    def breite_anpassen(self, breite, hoehe=None):
        """Von der Angebotsseite bei Größenänderung aufgerufen (Breite und Höhe der ganzen Seite). Niedrige Seite
        (Laptop, Prüfung 29.10.2026 O1): Karten flacher und Kalkulation + Fracht zugeklappt nebeneinander, damit mehr
        Positionen sichtbar sind."""
        kompakt = hoehe is not None and hoehe < KOMPAKT_UNTER
        if kompakt != self.kompakt:
            self.kompakt = kompakt
            self._lay.setSpacing(4 if kompakt else 8)
            self.karten.setSpacing(4 if kompakt else 8)
            for k in self.findChildren(QFrame, "karte"):
                if k.layout() is not None:
                    k.layout().setContentsMargins(12, 3 if kompakt else 8, 12, 3 if kompakt else 10)
        self._breite = breite
        self._gruppen_anordnen(4 if breite >= 1600 else 2)
        self._karten_neu()

    def _karten_neu(self):
        breite = getattr(self, "_breite", 0)
        zu = not self.kalk_knopf.isChecked() and not self.fracht_klapp.isChecked()
        self.einzeilig_setzen(self.kompakt and zu and not self.kopf_knopf.isChecked())
        self.karten_anordnen(breite >= FRACHT_RECHTS_AB or (self.kompakt and zu))

    def einzeilig_setzen(self, an):
        """Optimierungsplan B1 (Patrick 04.11.2026): auf niedrigen Seiten (Laptop) stehen Angebotskopf, Kalkulation
        und Fracht zugeklappt in EINER Zeile; die Knöpfe „Vorgaben aus Einstellungen“ und „Fracht berechnen …“
        erscheinen dann erst aufgeklappt. Spart eine Kartenzeile über der Positionsliste."""
        if an == self.einzeilig:
            return
        self.einzeilig = an
        if an:
            self._lay.removeWidget(self.kopf_karte)
            self.karten.addWidget(self.kopf_karte, 0, 0, Qt.AlignTop)
        else:
            self.karten.removeWidget(self.kopf_karte)
            self._lay.insertWidget(0, self.kopf_karte)
        self.vorgaben_knopf.setVisible(not an)
        if hasattr(self, "fracht_knopf"):
            self.fracht_knopf.setVisible(not an and funktionen.an("funktion_fracht"))
        self.fracht_rechts = None           # Karten neu einsetzen (Spalten verschieben sich um den Kopf)
        self.s.oben_anpassen()

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
            if fd.name == "gewinn":             # gestaffelt (GESTAFFELT) bleibt ohne eigenen Gewinn
                w.editingFinished.connect(lambda fd=fd, w=w: w.value() >= 0 and s._kopf_speichern(fd, round(w.value(), 4)))
            elif fd.name in KALK_NAMEN:         # 0 ist hier ein gültiger Wert (leer hieße: wie Einstellungen)
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

    def _gewinn_zeile(self, feld):
        """Gewinnfeld mit dem Knopf „Gestaffelt“: nimmt den eigenen Gewinn des Angebots weg, dann gilt wieder der
        gestaffelte Gewinn der Einstellungen (sichtbar nur, wenn er dort eingeschaltet ist)."""
        zeile = QWidget()
        h = QHBoxLayout(zeile)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        h.addWidget(feld, 1)
        self.gewinn_knopf = QToolButton()
        self.gewinn_knopf.setText("Gestaffelt")
        self.gewinn_knopf.setToolTip("Festen Gewinn dieses Angebots entfernen: es gilt wieder der gestaffelte Gewinn "
                                     "aus den Einstellungen (Seite Gewinn gestaffelt)")
        self.gewinn_knopf.clicked.connect(lambda: self.s._kopf_speichern(KOPF_FELD["gewinn"], None))
        self.gewinn_knopf.hide()
        h.addWidget(self.gewinn_knopf)
        return zeile

    def gewinn_gestaffelt(self):
        """Gilt im Angebot der gestaffelte Gewinn (in den Einstellungen an, kein eigener Gewinn im Angebot)?"""
        return self.s.kopf.get("gewinn") is None and bool(rechnen.gewinn_stufen(self.s.einst))

    def kundenhinweis_setzen(self, text):
        """Kundenhinweis (kundenhinweis.fuer_angebot); leer = ausblenden."""
        self.kundenhinweis.setText(f"Kundenhinweis: {text}" if text else "")
        self.kundenhinweis.setVisible(bool(text))

    def gewinn_satz_setzen(self, summen):
        """Wirksamen Satz des gestaffelten Gewinns nach der Rechnung ins Gewinnfeld und in die Kurzfassung."""
        satz = summen.get("gewinn_satz") if summen and summen.get("gewinn_gestaffelt") else None
        self._gewinn_satz = 100 * satz if isinstance(satz, (int, float)) else None
        self._gewinn_stufe = summen.get("gewinn_stufen_basis") if summen else None
        self._gewinn_anzeigen()
        self._kurzfassung()

    def _gewinn_anzeigen(self):
        """Gewinnfeld(er): gestaffelt den Text „gestaffelt · 30,0 %“ mit den Stufen im Tooltip, sonst die Zahl."""
        gest = self.gewinn_gestaffelt()
        satz = getattr(self, "_gewinn_satz", None)
        text = "gestaffelt" + (f" · {_z(satz, 1)} %" if satz is not None else "")
        stufen = rechnen.gewinn_stufen(self.s.einst) if gest else []
        tipp = ""
        if stufen:
            teile, unten = [], None
            for bis, s_ in stufen:
                teile.append(f"{'bis ' + _z(bis, 0) + ' €' if bis is not None else 'über ' + _z(unten, 0) + ' €'}: "
                             f"{_z(100 * s_, 1)} %")
                unten = bis
            basis = getattr(self, "_gewinn_stufe", None)
            tipp = ("Gewinn gestaffelt nach Auftragswert (Einstellungen → Gewinn gestaffelt):\n" + "\n".join(teile)
                    + (f"\nGewinnbasis dieses Angebots {_z(basis)} € → {_z(satz, 1)} %"
                       if isinstance(basis, (int, float)) and satz is not None else "")
                    + "\nEine Zahl eintippen = fester Gewinn nur für dieses Angebot.")
        for ablage in (self.felder, self.erweitert):
            w = ablage.get("gewinn")
            if w is None:
                continue
            w.blockSignals(True)
            if gest:
                w.setMinimum(GESTAFFELT)
                w.setSpecialValueText(text)
                w.setValue(GESTAFFELT)
                w.setToolTip(tipp)
            else:
                w.setSpecialValueText("")
                w.setMinimum(KOPF_FELD["gewinn"].von)
            w.blockSignals(False)
        if hasattr(self, "gewinn_knopf"):
            fest = rechnen.einstellungen_fest(self.s.tabellen, self.s.db.einstellungen())
            self.gewinn_knopf.setVisible(not gest and bool(rechnen.gewinn_stufen(fest)))

    def wert(self, name):
        """Wert eines Kopffelds wie angezeigt (ältere Angebote ohne Kalkulationswert: Wert der Einstellungen;
        gestaffelter Gewinn: der wirksame Satz nach der Rechnung, vorher None)."""
        v = self.s.kopf.get(name)
        if name == "gewinn" and v is None and self.gewinn_gestaffelt():
            return getattr(self, "_gewinn_satz", None)
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
        self._gewinn_anzeigen()
        self._lieferzeit_anzeigen()
        k = s.kopf.get("bearbeiter")
        name = teilen.mitarbeiter(s.db, k).get("name") if k else None
        self.bearbeiter.setText(f"{k} – {name}" if k and name else k or "–")
        self.mat_vorgabe.blockSignals(True)
        self.mat_vorgabe.setCurrentText(s.kopf.get("material_vorgabe") or EIGENMATERIAL)
        self.mat_vorgabe.blockSignals(False)
        betrag = rechnen.einstellungen_fest(s.tabellen, s.db.einstellungen()).get("mindestpreis")
        self.verpackung_an.blockSignals(True)
        self.verpackung_an.setChecked(s.kopf.get("verpackung") != "nein")
        self.verpackung_an.blockSignals(False)
        self.mindest_an.blockSignals(True)
        self.mindest_an.setChecked(s.kopf.get("mindestpreis_anwenden") != "nein")
        self.mindest_an.setText(f"Mindestauftragswert anwenden ({_z(betrag)} € netto)"
                                if isinstance(betrag, (int, float)) and betrag > 0 else
                                "Mindestauftragswert anwenden (0 €)")
        self.mindest_an.blockSignals(False)
        self.muster_darstellung.blockSignals(True)
        self.muster_darstellung.setCurrentText(s.kopf.get("muster_darstellung") or MUSTER_UMLEGEN)
        self.muster_darstellung.blockSignals(False)
        self.muster_wahl.setVisible(any(p.get("muster") == "ja" for p in getattr(s, "positionen", None) or ()))
        self.abruf_an.blockSignals(True)
        self.abruf_an.setChecked(abruf.aktiv(s.kopf))
        self.abruf_an.blockSignals(False)
        self.abruf_knopf.setVisible(abruf.aktiv(s.kopf))
        ab = abruf.daten(s.kopf)
        self.gleit_knopf.setVisible(bool(ab) and not ab["bevorraten"])
        self.gleit_knopf.setEnabled(isinstance(s.kopf.get("preisbasis"), dict))
        self.abruf_kurz.setText(abruf.kurz(s.kopf))
        self.abruf_wahl.setVisible(abruf.aktiv(s.kopf) or funktionen.an("funktion_abruf"))
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
        self.lz_feld.blockSignals(True)
        self.lz_feld.setText(lieferzeit_eingabe(k))
        self.lz_feld.blockSignals(False)
        from . import funktionen
        self.termin_knopf.setVisible(funktionen.an("funktion_auslastung"))
        text = lieferzeit_text(k)
        # E3: immer darunter, wie es im Angebot steht (das Feld zeigt nur die Kurzform)
        self.lz_vorschau.setText(f"Im Angebot: {text}" if text else
                                 "Keine Lieferzeit im Angebot: es gilt der Text der Bedingungen (Einstellungen).")
        self.lz_vorschau.setVisible(True)
        self.lz_feld.setToolTip(self.lz_vorschau.text() + "\n\n" + LIEFERZEIT_TOOLTIP)

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
        km_hand = s.kopf.get("fracht_km")
        self.fracht_km.blockSignals(True)
        self.fracht_km.setText(f"{km_hand:g}".replace(".", ",") if isinstance(km_hand, (int, float)) else "")
        self.fracht_km.blockSignals(False)
        sd = (fracht_angebot.daten(s.kopf) or {}).get("sendung") or {}
        self.fracht_km.setPlaceholderText(f"{sd['km']:g}" if sd.get("km_quelle") == "PLZ"
                                          and isinstance(sd.get("km"), (int, float)) else "aus PLZ")
        self.fracht_modus.setEnabled(not an)
        for ablage in (self.felder, self.erweitert):     # berechnet: Betrag kommt aus der Frachtberechnung
            w = ablage.get("fracht")
            if w is not None:
                w.setReadOnly(m == fracht_angebot.BERECHNET)
                w.setToolTip("aus „Fracht berechnen …“ (Frachtart berechnet)" if m == fracht_angebot.BERECHNET
                             else "")
        betrag = fracht_angebot.wirksam(s.kopf)
        d = fracht_angebot.daten(s.kopf) or {}
        # Werte je Position nur, wenn sie gebraucht werden: automatische Fracht oder ein Betrag zum Verteilen (der
        # Hinweis „Gewicht fehlt“ kommt nur mit Betrag); ohne Fracht sparte das bei jeder Änderung (Plan A2, 04.11.2026)
        werte = [rechnen.position_werte(p, s.kopf, s.k, s.tabellen) if position_aktiv(p) else None
                 for p in s.positionen] if an or betrag else None
        if an:
            b, info, fehler = fracht_angebot.betrag_angebot(s.kopf, s.positionen, werte)
            betrag = b or 0
            if fehler:
                text = f"<span style='color:#B42318'><b>{fehler}.</b> Die Kalkulation rechnet bis dahin ohne Fracht.</span>"
            else:
                text = f"Automatisch: {info or _z(betrag) + ' €'}"
                if d.get("zone"):
                    text += f"; {d['zone']}"
                if d.get("km_text"):
                    text += f"; Entfernung {d['km_text']}"
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
        hinweis = fracht_angebot.anteile(s.positionen, werte, betrag, u)[1] if werte is not None and betrag else ""
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
            zeigen = kopf_sichtbar(name, self.wert(name)) or name == "gewinn" and self.gewinn_gestaffelt()
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
            QTimer.singleShot(0, self, self._breite_anpassen)     # mit self: entfällt, wenn das Angebot vorher geschlossen wird
        return False

    def _breite_anpassen(self):
        if self.widget() is not None and self.minimumWidth() != (b := self.noetige_breite()):
            self.setMinimumWidth(b)

    def jetzt_anpassen(self):
        """Breite sofort an den neuen Inhalt anpassen (nach neuen Beträgen): sonst sind lange Beträge bis zum
        nächsten Durchlauf rechts abgeschnitten (Patrick 03.11.2026 „Werte unsichtbar“)."""
        if self.widget() is not None:
            self.widget().layout().activate()
            self._breite_anpassen()


class UebersichtStreifen(QFrame):
    """Schmaler Streifen rechts, solange die Übersicht ausgeblendet ist (Plan B2 04.11.2026): oben « zum Einblenden,
    darunter senkrecht Verkaufspreis und Stand der Optimierung (Farbpunkt wie in der Übersicht). Ein Klick irgendwo
    auf den Streifen blendet die Übersicht wieder ein. Die Werte liest er aus dem UebersichtBereich."""
    BREITE = 30
    FARBE = {"stand_ok": "GRUEN", "stand_offen": "GELB_TEXT"}       # Namen in stil; sonst veraltet: ROT

    def __init__(self, bereich, knopf):
        super().__init__()
        self.bereich, self.knopf = bereich, knopf
        bereich.streifen = self
        self.setObjectName("karte")
        self.setFixedWidth(self.BREITE)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 4, 2, 4)
        lay.addWidget(knopf, 0, Qt.AlignHCenter)
        lay.addStretch(1)
        self.setToolTip("Übersicht einblenden")

    def text(self):
        preis = self.bereich.preis["verkauf"].text()
        return f"Übersicht  ·  VK {preis}" if preis else "Übersicht"

    def farbe(self):
        from . import stil
        return getattr(stil, self.FARBE.get(self.bereich.stand.objectName(), "ROT"))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.knopf.setChecked(True)
        super().mouseReleaseEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        oben = self.knopf.geometry().bottom() + 12
        p.setPen(Qt.NoPen)
        from . import stil
        p.setBrush(stil.farbe(self.farbe()))
        p.drawEllipse(self.width() // 2 - 5, oben, 10, 10)
        p.setPen(stil.farbe(stil.AKZENT))
        f = QFont(self.font())
        f.setBold(True)
        p.setFont(f)
        p.translate(self.width() / 2 + p.fontMetrics().ascent() / 2 - 2, oben + 20)
        p.rotate(90)
        p.drawText(0, 0, self.text())
        p.end()


class UebersichtBereich(QWidget):
    """Rechte Seite: Stand der Optimierung, Meldungen, Kennzahlen und Kostenübersicht."""

    STAND = {"aktuell": ("Optimierung abgeschlossen", "stand_ok"),
             "noch nicht optimiert": ("Noch nicht optimiert", "stand_offen")}

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        # » blendet die Übersicht aus; dann zeigt der schmale Streifen (UebersichtStreifen) Preis und Stand (Plan B2)
        self.ausblenden_knopf = QToolButton()
        self.ausblenden_knopf.setText("»")
        self.ausblenden_knopf.setAutoRaise(True)
        self.ausblenden_knopf.setToolTip("Übersicht ausblenden: die Positionsliste bekommt die ganze Breite, rechts "
                                         "bleibt ein schmaler Streifen mit Verkaufspreis und Stand")
        self.streifen = None
        k, kl = karte("Übersicht", rechts=self.ausblenden_knopf)
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
        # Trefferquote des Kunden (Plan „Programm soll lernen“ L4, 08.11.2026): nur Hinweis, ändert nichts
        self.treffer = QLabel()
        self.treffer.setWordWrap(True)
        self.treffer.setObjectName("trefferquote")
        self.treffer.setStyleSheet(f"color:{GRAU}")
        self.treffer.setToolTip("Aus den beauftragten und abgelehnten Angeboten dieses Kunden (auch denen der "
                                "Kollegen). Nur ein Hinweis: der Gewinn ändert sich nie von allein.")
        self.treffer.setVisible(False)
        kl.addWidget(self.treffer)
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
        self._streifen_neu()

    def wird_berechnet(self):
        """Gleich optimiert das Programm selbst (Plan Angebotsablauf V7): statt eines vorläufigen Preises ohne
        Material „…“ zeigen, bis die Optimierung fertig ist (kosten_setzen schreibt dann die Preise); der Stand oben
        behält Wort und Farbe („Noch nicht optimiert“ gelb, „Veraltet“ rot) und sagt dahinter „– wird berechnet …“.
        Den Text nicht in die großen Preisfelder (17 pt): er machte die Übersicht breiter als die Spalte, rechts
        wurden die Beträge im Preisaufbau abgeschnitten und die Spalte sprang nach dem Optimieren zurück
        (Design-Prüfung 28.10.2026)."""
        for name, (t, titel) in self.preis_titel.items():
            t.setText(titel)
            self.preis[name].setText("wird berechnet …")
            # klein und grau: in Schrift der Preise (17 pt) wäre der Text breiter als die Übersicht (E1)
            self.preis[name].setStyleSheet("color: #7F8A99; font-size: 10pt; font-weight: normal;")
            self.preis[name].setToolTip("Das Programm optimiert gleich selbst (Material, Stangen, Verschnitt).")
        self._streifen_neu()

    def _streifen_neu(self):
        if self.streifen is not None:
            self.streifen.update()

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
        self._stand = stand                 # für wird_berechnet
        text, name = self.STAND.get(stand, ("Veraltet – Angebot oder Stammdaten geändert, bitte neu optimieren",
                                            "stand_veraltet"))
        self.stand.setText(text)
        self.stand.setObjectName(name)
        # „Optimierung abgeschlossen“ zeigt schon die Schrittanzeige (② Optimiert): Kasten nur, wenn etwas fehlt (B4)
        self.stand.setVisible(name != "stand_ok")
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

    def treffer_setzen(self, text):
        """Trefferquote des Kunden (lernen.treffer_text); leer = ausblenden."""
        self.treffer.setText(text or "")
        self.treffer.setVisible(bool(text))

    def wiederholteile_setzen(self, eintraege):
        """eintraege: [(Zeile, Positionstext, Treffer-Liste)] (wiederholteile.suchen), nur Positionen mit Treffern."""
        from html import escape
        from .wiederholteile import SICHER, revision_text, text
        n = len(eintraege)
        self.wiederholteile_bereich.setVisible(bool(n))
        if not n:
            self.wiederholteile.clear()
            return
        sicher = sum(1 for _, _, t in eintraege if t[0].art == SICHER)
        geaendert = sum(1 for _, _, t in eintraege if t[0].geaendert)
        self.wiederholteile_bereich.setze_titel(
            f"Wiederholteile: {n} Position{'en' if n > 1 else ''} schon angeboten"
            + (f" ({sicher} sicher)" if sicher and sicher < n else "")
            + (f", {geaendert} geändert" if geaendert else ""))
        link = "color:#1F4E78"
        zeilen = []
        for zeile, titel, treffer in eintraege:
            t = treffer[0]
            aktionen = [f"<a style='{link}' href='hin:{zeile}'>Hinspringen</a>",
                        f"<a style='{link}' href='oeffnen:{t.angebot['id']}'>Angebot öffnen</a>"]
            if t.werte:
                aktionen.insert(0, f"<a style='{link}' href='werte:{zeile}'>Werte übernehmen …</a>")
            rev = revision_text(t)      # B1: neue Revision des Artikels (Geometrie anders als im alten Angebot)
            zeilen.append(f"💡 <b>{escape(titel)}</b>: {escape(text(treffer))}<br>"
                          + (f"<span style='color:{ORANGE}'>⚠ Neue Revision, {escape(rev)}</span><br>" if rev else "")
                          + f"<span style='color:{GRAU}'>{' · '.join(aktionen)}</span>")
        self.wiederholteile.setText("<br>".join(zeilen) + f"<br><span style='color:{GRAU}'>Der Preis wird nie "
                                    "übernommen, er entsteht immer neu aus der Kalkulation.</span>")

    def baugruppen_setzen(self, gruppen):
        """gruppen: [(Titel, [(Kostenteil, €)], [(größter Posten, €)])] je Schweißbaugruppe, Beträge je Baugruppe."""
        from .kostenbalken import Kostenbalken
        while self.bg_lay.count():
            w = self.bg_lay.takeAt(0).widget()
            if w is not None:       # sofort weg: sonst liegen die alten Balken bis zum Löschen über den neuen
                w.hide()
                w.setParent(None)
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

    def kosten_setzen(self, kosten, co2=None):
        """kosten: rechnen.kostenarten(...). Oben die Gruppen (rechnen.KOSTEN_GRUPPEN), aufklappbar jede Kostenart
        einzeln. Zeilen mit 0,00 € sind ausgeblendet, Herstellkosten und Verkaufspreis immer sichtbar."""
        betrag = {n: (t, w) for (t, w, _), (_, n, _) in zip(kosten, rechnen.KOSTENARTEN)}
        for name, w in self.preis.items():
            w.setText(f"{_z(betrag[name][1])} €")
            if "font-size" in w.styleSheet():           # „wird berechnet …“ war klein gesetzt
                w.setStyleSheet("")
        self._streifen_neu()
        self._kosten, self._co2 = kosten, co2
        linie = "border-top:1px solid #C9D0D8"
        html = (f"<table width='100%' cellpadding='1' cellspacing='0'><tr><td colspan='2' style='{linie}'>"
                f"<b>Preisaufbau</b></td></tr>")
        def _fest(t):       # Zahl und Einheit nicht trennen („360,25 €“ bricht nicht als „€)“ allein um, L2 11.11.2026)
            return re.sub(r"(\d) (€|%|min|h|kg|Stk)", r"\1&nbsp;\2", t or "")
        betrag = {n: (_fest(t), w) for n, (t, w) in betrag.items()}
        for titel, namen, summe in rechnen.KOSTEN_GRUPPEN:
            gesamt = sum(betrag[n][1] or 0 for n in namen)
            if summe:
                html += (f"<tr><td style='{linie}'><b>= {titel}</b></td>"
                         f"<td align='right' style='{linie}'><b>{_z(gesamt)} €</b></td></tr>")
            elif titel == "Material" or any(sichtbar(betrag[n][1]) for n in namen):     # Material immer
                zeichen = "" if titel == "Material" else "+ "
                einzeln = [n for n in namen if sichtbar(betrag[n][1])]
                if len(namen) == 1 or einzeln == [namen[0]]:
                    # einzeln mit Mengenangabe; auch eine Gruppe, deren Zusatzposten (z. B. Schneidgas, Schrotterlös)
                    # 0 sind, ohne Aufklappen
                    text = betrag[namen[0]][0]
                elif titel in self.offene_gruppen:
                    text = f"<a href='{titel}' style='color:#1F2937;text-decoration:none'>▾ {titel}</a>"
                else:
                    text = f"<a href='{titel}' style='color:#1F2937;text-decoration:none'>▸ {titel}</a>"
                html += f"<tr><td>{zeichen}{text}</td><td align='right'>{_z(gesamt)} €</td></tr>"
                if len(namen) > 1 and einzeln != [namen[0]] and titel in self.offene_gruppen:
                    for n in einzeln:
                        html += (f"<tr><td style='color:{GRAU};padding-left:14px'>{betrag[n][0]}</td>"
                                 f"<td align='right' style='color:{GRAU}'>{_z(betrag[n][1])} €</td></tr>")
        from . import ertrag         # Plan PROfirst G2: Ertrag nach Einkauf und nach Herstellkosten
        for i, (t, w) in enumerate(ertrag.text(ertrag.angebot({n: b for n, (_, b) in betrag.items()}), _z)):
            html += (f"<tr><td style='color:{GRAU};{linie if i == 0 else ''}'>{t}</td>"
                     f"<td align='right' style='color:{GRAU};{linie if i == 0 else ''}'>{_z(w)} €</td></tr>")
        if co2:          # CO₂-Bilanz (Vorschlag K3, nur mit Funktion „CO₂-Bilanz“)
            html += f"<tr><td colspan='2' style='color:{GRAU};{linie}'>{co2}</td></tr>"
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
            self.kosten_setzen(self._kosten, getattr(self, "_co2", None))

    def zeiten_setzen(self, k):
        """k: rechnen.zeit_summen(...). Zeiten und Arbeitskosten aufgeschlüsselt: Maschine und Personal aufklappbar je
        Arbeitsschritt (Zeit, Kosten), Rüstzeit als Teil der Maschinen- bzw. Personalzeit, Arbeitszeit gesamt,
        Durchlaufzeit und Zeit je Teil; Zeilen mit 0 ausgeblendet."""
        self._zeit_summen = k
        linie = "border-top:1px solid #C9D0D8"
        grau = f"color:{GRAU}"
        ABSTAND = "&nbsp;&nbsp;&nbsp;"      # Zeit und Betrag nie ohne Abstand („9 h 20 min1.024,94 €“, Prüfung 29.10.)
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
                     f"<td align='right'>{ABSTAND}{_z(kosten)} €</td></tr>")
            if offen:
                for z in schritte:
                    zusatz = " (parallel)" if art == "Personal" and z["parallel"] else ""
                    html += (f"<tr><td style='{grau};padding-left:14px'>{z['schritt']}{zusatz}</td>"
                             f"<td align='right' style='{grau}'>{rechnen.zeit_text(z['gesamt_min'])}</td>"
                             f"<td align='right' style='{grau}'>{ABSTAND}{_z(z['kosten'])} €</td></tr>")
            if sichtbar(ruest):
                html += (f"<tr><td style='{grau};padding-left:14px'>davon Rüsten</td>"
                         f"<td align='right' style='{grau}'>{rechnen.zeit_text(ruest)}</td><td></td></tr>")
        if n:
            html += (f"<tr><td style='{linie}'><b>= Arbeitszeit gesamt</b></td>"
                     f"<td align='right' style='{linie}'><b>{rechnen.zeit_text(k['bearbeitung_min'])}</b></td>"
                     f"<td align='right' style='{linie}'><b>{ABSTAND}{_z(k['arbeitskosten'])} €</b></td></tr>")
            parallel = (f" (ohne {rechnen.zeit_text(k['parallel_min'])} parallel)"
                        if sichtbar(k.get("parallel_min", 0)) else "")
            html += (f"<tr><td>Durchlaufzeit{parallel}</td><td align='right'>{rechnen.zeit_text(k['durchlauf_min'])}"
                     "</td><td></td></tr>")
            if k.get("je_teil_min"):
                html += (f"<tr><td>Ø Arbeitszeit je Teil</td><td align='right'>{rechnen.zeit_text(k['je_teil_min'])}"
                         "</td><td></td></tr>")
            if sichtbar(k["sonstige"]):
                html += (f"<tr><td style='{grau}'>Kosten ohne Zeit (Festpreise, Fremdleistung)</td><td></td>"
                         f"<td align='right' style='{grau}'>{ABSTAND}{_z(k['sonstige'])} €</td></tr>")
        self.zeiten.setText(html + "</table>")
        self.zeiten.setVisible(bool(n))

    def _zeiten_umschalten(self, art):
        """Klick auf Maschine oder Personal in den Zeiten: Arbeitsschritte auf- oder zuklappen."""
        self.offene_zeiten ^= {art}
        if self._zeit_summen is not None:
            self.zeiten_setzen(self._zeit_summen)
