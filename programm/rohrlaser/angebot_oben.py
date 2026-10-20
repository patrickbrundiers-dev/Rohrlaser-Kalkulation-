"""Oberer Teil der Angebotsseite: Angebotskopf, Maschinenparameter, Kalkulationseinstellungen und Übersicht.

Welche Felder und Kennzahlen sichtbar sind, entscheidet sichtbarkeit.py: optionale Werte mit 0 oder leer stehen
nicht in der Hauptansicht, sondern unter 'Erweiterte Einstellungen' (dort immer änderbar). Pflichtfelder,
Stammdaten und Maschinenparameter bleiben immer sichtbar. Gespeichert und gerechnet wird wie bisher.
"""
from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateEdit, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from . import fracht_angebot, rechnen
from .ausgabe import datum_text
from .fracht_angebot import MODI, UMLAGEN
from .angebot import KALK_PROZENT, KALKULATION, KOPF, aktiv as position_aktiv
from .sichtbarkeit import KOPF_ROLLEN, MASCHINE, OPTIONAL, kopf_sichtbar, sichtbar
from .stammdaten import zahl_als_text

KOPF_FELD = {f.name: f for f in KOPF}
KALK_NAMEN = {f.name for f in KALKULATION}
KALK_OFFEN_EINSTELLUNG = "ansicht_kalkulation_offen"     # Karte Kalkulation auf- oder zugeklappt (alle Angebote)
# Kalkulationseinstellungen nach Zweck (Felder des Angebotskopfs)
GRUPPEN = (
    ("Material und Fertigung", ("zuschlag_material", "zuschlag_fertigung", "zuschlag_fremdleistung")),
    ("Zeit und Rüsten", ("ruesten_abmessung",)),
    ("Verkauf und Gewinn", ("gewinn", "angebotsaufschlag", "programmierung_teil", "pauschale_abmessung", "fracht")),
    ("Zahlungsbedingungen", ("skonto", "skonto_tage", "zahlungsziel")),
)
# Maschinenparameter (Stammdaten Maschinen): (Feld, Titel, Einheit, Stellen, Rolle)
MASCHINENPARAMETER = (
    ("endbeschnitt", "Endbeschnitt", "mm", 0, MASCHINE), ("greiferrest", "Greiferrest", "mm", 0, MASCHINE),
    ("schnittverlust", "Schnittverlust je Schnitt", "mm", 1, MASCHINE),
    ("max_stange", "Max. Stangenlänge", "mm", 0, MASCHINE),
    ("abstand", "Abstand getrennte Schnitte", "mm", 1, OPTIONAL),
    ("kontur_klein", "Kontur klein bis", "mm", 1, OPTIONAL), ("kontur_mittel", "Kontur mittel bis", "mm", 1, OPTIONAL),
    ("max_huellkreis", "Max. Hüllkreis-Ø", "mm", 1, OPTIONAL), ("max_kg_m", "Max. Metergewicht", "kg/m", 1, OPTIONAL),
)
# Werte der gewählten Maschine, die in die Kalkulation eingehen (Gruppe Zeit und Rüsten)
MASCHINE_KALK = (("ruestzeit", "Rüstzeit je Maschine (Angebot)", "min", 0),
                 ("stangenwechsel", "Stangenwechsel je Stange", "s", 0),
                 ("stundensatz", "Stundensatz Maschine", "€/h", 2))

GRAU = "#5F6B7A"


def _z(w, stellen=2):
    return zahl_als_text(w, stellen) if isinstance(w, (int, float)) and not isinstance(w, bool) else ""


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

        # Angebotskopf: Nummer, Kunde und Maschine vorn und hervorgehoben
        kopf, kl = karte("Angebotskopf")
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(5)
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
        w = self._eingabe(KOPF_FELD["bemerkung"], self.felder)
        g.addWidget(QLabel(KOPF_FELD["bemerkung"].titel), 2, 0)
        g.addWidget(w, 2, 1, 1, 5)
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
        hinweis = QLabel("Vorgabe aus den Einstellungen, hier änderbar. Werte mit 0 stehen unter "
                         "„Erweiterte Einstellungen“.")
        hinweis.setStyleSheet(f"color: {GRAU};")
        hinweis.setWordWrap(True)
        kal.addWidget(hinweis)
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
            if titel == "Zeit und Rüsten":     # Werte der Maschine (Stammdaten), nur Anzeige
                for name, text, einheit, _ in MASCHINE_KALK:
                    b, w = QLabel(text), QLabel()
                    w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    w.setToolTip("Aus den Stammdaten Maschinen (gewählte Maschine)")
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
        lay.addWidget(kalk)

        # Fracht: Frachtart, Verteilung und Berechnung (fracht_angebot.py)
        self.fracht_knopf = QPushButton("Fracht berechnen …")
        self.fracht_knopf.setToolTip("Frachtkosten aus PLZ, Gewicht, Ladehilfsmitteln und Tarif berechnen "
                                     "(Reiter Frachtkosten) und ins Angebot übernehmen")
        self.fracht_knopf.clicked.connect(lambda: seite.fracht_berechnen())
        fr, frl = karte("Fracht", self.fracht_knopf)
        zeile = QHBoxLayout()
        self.fracht_modus, self.fracht_umlage = QComboBox(), QComboBox()
        self.fracht_modus.addItems(MODI)
        self.fracht_umlage.addItems(UMLAGEN)
        self.fracht_modus.setToolTip("manuell: Betrag „Frachtkosten“ von Hand; berechnet: aus „Fracht berechnen …“, "
                                     "in den Staffelpreisen je Menge neu; keine Fracht (Abholung, ab Werk) und im "
                                     "Artikelpreis enthalten: 0 € in der Kalkulation, Hinweis im Angebot")
        self.fracht_umlage.setToolTip("je Stück: jedes Teil trägt gleich viel; nach Gewicht: Anteil des Teilegewichts "
                                      "am Gesamtgewicht")
        for titel, cb, name in (("Frachtart", self.fracht_modus, "fracht_modus"),
                                ("Fracht verteilen", self.fracht_umlage, "fracht_umlage")):
            zeile.addWidget(QLabel(titel))
            zeile.addWidget(cb)
            cb.currentTextChanged.connect(lambda t, name=name: seite._kopf_speichern(KOPF_FELD[name], t or None))
        zeile.addStretch(1)
        frl.addLayout(zeile)
        # automatisch: Ziel-PLZ (zwei Stellen reichen) und Land; Gewicht, Ladungsträger und Tarif rechnet das Programm
        zeile = QHBoxLayout()
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
        zeile.addWidget(self.fracht_auto)
        zeile.addWidget(QLabel("Ziel-PLZ"))
        zeile.addWidget(self.fracht_plz)
        zeile.addWidget(QLabel("Land"))
        zeile.addWidget(self.fracht_land)
        zeile.addStretch(1)
        frl.addLayout(zeile)
        self.fracht_text = QLabel()
        self.fracht_text.setWordWrap(True)
        self.fracht_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        frl.addWidget(self.fracht_text)
        lay.addWidget(fr)
        offen = self.s.db.einstellung(KALK_OFFEN_EINSTELLUNG)
        self.kalkulation_aufklappen(offen if isinstance(offen, bool) else True)
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

    def kalk_offen(self):
        return self.kalk_knopf.isChecked()

    def _kurzfassung(self):
        """Kalkulationswerte ungleich 0 in einer Zeile, z. B. 'Zuschlag Material 10 % · Gewinn 10 % · …'."""
        teile = []
        for _, namen in GRUPPEN:
            for name in namen:
                v = self.wert(name)
                if kopf_sichtbar(name, v):
                    fd = KOPF_FELD[name]
                    titel, einheit = fd.titel, ""
                    if "[" in titel:
                        titel, einheit = titel.split("[", 1)
                        einheit = einheit.rstrip("]")
                    teile.append(f"{titel.strip()} {_z(v, fd.stellen if fd.stellen is not None else (0 if fd.art == "ganz" else 2))} {einheit}".strip())
        self.kalk_kurz.setText("   " + " · ".join(teile))
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

    def breite_anpassen(self, breite):
        """Von der Angebotsseite bei Größenänderung aufgerufen (Breite der ganzen Seite)."""
        self._gruppen_anordnen(4 if breite >= 1600 else 2)

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
        elif fd.art == "datum":
            w = QDateEdit()
            w.setCalendarPopup(True)
            w.setDisplayFormat("dd.MM.yyyy")
            w.editingFinished.connect(lambda fd=fd, w=w: s._kopf_speichern(fd, w.date().toString("yyyy-MM-dd")))
        elif fd.art == "auswahl":
            w = QComboBox()
            w.currentTextChanged.connect(lambda t, fd=fd: s._kopf_speichern(fd, t or None))
        elif fd.art == "ganz":
            w = QSpinBox()
            w.setRange(int(fd.von), int(fd.bis))
            w.setGroupSeparatorShown(True)
            w.setSingleStep(100 if fd.bis > 1000 else 1)
            w.setAlignment(Qt.AlignRight)
            w.editingFinished.connect(lambda fd=fd, w=w: s._kopf_speichern(fd, w.value()))
        elif fd.art == "zahl":
            w = QDoubleSpinBox()
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
        if isinstance(w, (QSpinBox, QDoubleSpinBox)):
            w.setMinimumWidth(90)
        ablage[fd.name] = w
        return w

    def wert(self, name):
        """Wert eines Kopffelds wie angezeigt (ältere Angebote ohne Kalkulationswert: Wert der Einstellungen)."""
        v = self.s.kopf.get(name)
        if v is None and name in KALK_NAMEN:
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
        self.sichtbarkeit()
        self._kurzfassung()
        self._maschine_anzeigen()
        self._fracht_anzeigen()

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
                if "teurere" in h or "Beispieltarif" in h:
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

    def sichtbarkeit(self):
        """Optionale Felder mit 0 in die Erweiterten Einstellungen, alle anderen in die Hauptansicht."""
        versteckt = 0
        for name, (b, w) in self.zeilen.items():
            zeigen = kopf_sichtbar(name, self.wert(name))
            b.setVisible(zeigen)
            w.setVisible(zeigen)
            be, we = self.zeilen_erweitert[name]
            be.setVisible(not zeigen)
            we.setVisible(not zeigen)
            versteckt += not zeigen
        for titel, (leer, namen) in self.gruppen_leer.items():
            leer.setVisible(not any(kopf_sichtbar(n, self.wert(n)) for n in namen) and titel != "Zeit und Rüsten")
        self.erweitert_leer.setVisible(versteckt == 0)
        self.erweitert_bereich.setze_titel(
            f"Erweiterte Einstellungen ({versteckt} {'Wert' if versteckt == 1 else 'Werte'} auf 0)" if versteckt
            else "Erweiterte Einstellungen")

    def _maschine_anzeigen(self):
        m = rechnen.maschine(self.s.kopf, self.s.k)
        if not m:
            self.maschinenwerte.setText("<span style='color:#B42318'>Maschine fehlt oder ist unbekannt.</span>")
            self.maschinen_bereich.setze_titel("Maschinenparameter: Maschine fehlt oder ist unbekannt")
            for b, w, _ in self.maschine_kalk.values():
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
        for name, (b, w, einheit) in self.maschine_kalk.items():
            w.setText(f"{_z(m.get(name), dict((n, st) for n, _, _, st in MASCHINE_KALK)[name])} {einheit}")


def _kundennr(text):
    """'K-1001 – Beispiel GmbH' (Eintrag der Kundenauswahl) -> 'K-1001'; frei eingetippt bleibt der Text."""
    return str(text or "").split(" – ")[0].strip()


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
            preise.addWidget(box, 1)
        kl.addLayout(preise)
        # Meldungen: Anzahl als Etikett, einzelne Meldungen aufklappbar
        self.meldungen = QLabel()
        self.meldungen.setWordWrap(True)
        self.meldungen.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.meldungen_bereich = Aufklapper("Meldungen", self.meldungen)
        kl.addWidget(self.meldungen_bereich)
        # Kennzahlen
        self.kennzahlen = QGridLayout()
        self.kennzahlen.setHorizontalSpacing(6)
        self.kennzahl = {}
        for i, (name, titel) in enumerate((("positionen", "Positionen"), ("stueck", "Stückzahl"),
                                           ("laenge", "Gesamtlänge"), ("gewicht", "Gewicht"),
                                           ("stangen", "Stangen"))):
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
        self.uebersicht = QLabel()
        self.uebersicht.setTextInteractionFlags(Qt.TextSelectableByMouse)
        kl.addWidget(self.uebersicht)
        self.einzeln = QLabel()
        self.einzeln.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.einzeln_bereich = Aufklapper("Kostenarten einzeln", self.einzeln)
        kl.addWidget(self.einzeln_bereich)
        # Zeiten je Arbeitsschritt (Reiter 'Zeiten & Arbeitskosten'), Zeilen mit 0 ausgeblendet
        self.zeiten = QLabel()
        self.zeiten.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.zeiten.setToolTip("Einzelheiten je Arbeitsschritt im Reiter „Zeiten & Arbeitskosten“")
        kl.addWidget(self.zeiten)
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

    def preisstand_setzen(self, preisbasis, abweichungen):
        """Hinweis, ob Materialpreise und Schneiddaten festgeschrieben sind und ob die Stammdaten seitdem
        abweichen; der Knopf erscheint nur bei Abweichungen."""
        if not isinstance(preisbasis, dict):
            self.preisstand.setText("<span style='color:#5F6B7A'>Materialpreise: aktuelle Stammdaten (werden beim "
                                    "Angebots-PDF festgeschrieben)</span>")
            self.preisstand.setToolTip("")
        elif abweichungen:
            self.preisstand.setText(f"<span style='color:#8A5A00'><b>Preise festgeschrieben am "
                                    f"{datum_text(preisbasis.get('datum'))}</b>, Stammdaten seitdem geändert "
                                    f"({len(abweichungen)})</span>")
            self.preisstand.setToolTip("\n".join(abweichungen))
        else:
            self.preisstand.setText(f"<span style='color:#5F6B7A'>Preise festgeschrieben am "
                                    f"{datum_text(preisbasis.get('datum'))}</span>")
            self.preisstand.setToolTip("Materialpreise und Schneiddaten stimmen mit den Stammdaten überein.")
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
            farbe = {"FEHLER": "#B42318", "WARNUNG": "#8A5A00", "HINWEIS": "#5F6B7A"}
            self.meldungen.setText("<br>".join(
                f"<span style='color:{farbe.get(t.split(':')[0], '#1F2937')}'>Pos. {_z(pos, 0) or '?'}: {t}</span>"
                for pos, t in meldungen))
        k = self.meldungen_bereich.knopf
        k.style().unpolish(k)
        k.style().polish(k)

    def kennzahlen_setzen(self, werte):
        for name, text in werte.items():
            self.kennzahl[name].setText(text)

    def kosten_setzen(self, kosten):
        """kosten: rechnen.kostenarten(...). Oben die Gruppen (rechnen.KOSTEN_GRUPPEN), aufklappbar jede Kostenart
        einzeln. Zeilen mit 0,00 € sind ausgeblendet, Herstellkosten und Verkaufspreis immer sichtbar."""
        betrag = {n: (t, w) for (t, w, _), (_, n, _) in zip(kosten, rechnen.KOSTENARTEN)}
        for name, w in self.preis.items():
            w.setText(f"{_z(betrag[name][1])} €")
        linie = "border-top:1px solid #C9D0D8"
        html = "<table width='100%' cellpadding='1' cellspacing='0'>"
        for titel, namen, summe in rechnen.KOSTEN_GRUPPEN:
            gesamt = sum(betrag[n][1] or 0 for n in namen)
            if summe:
                html += (f"<tr><td style='{linie}'><b>{titel}</b></td>"
                         f"<td align='right' style='{linie}'><b>{_z(gesamt)} €</b></td></tr>")
            elif titel == "Material" or any(sichtbar(betrag[n][1]) for n in namen):     # Material immer
                text = betrag[namen[0]][0] if len(namen) == 1 else titel      # einzeln mit Mengenangabe
                html += f"<tr><td>{text}</td><td align='right'>{_z(gesamt)} €</td></tr>"
        self.uebersicht.setText(html + "</table>")
        html = "<table width='100%' cellpadding='1' cellspacing='0'>"
        for t, w, fett in kosten:
            if fett:
                html += f"<tr><td><b>{t}</b></td><td align='right'><b>{_z(w)} €</b></td></tr>"
            elif sichtbar(w):
                html += f"<tr><td style='color:{GRAU}'>{t}</td><td align='right' style='color:{GRAU}'>{_z(w)} €</td></tr>"
        self.einzeln.setText(html + "</table>")

    def zeiten_setzen(self, k):
        """k: rechnen.zeit_summen(...). Zeiten und Arbeitskosten; Zeilen mit 0 ausgeblendet."""
        zeilen = (("Maschinenzeit", k["maschine_min"], True), ("Personalzeit", k["personal_min"], True),
                  ("Rüstzeit", k["ruest_min"], True), ("Durchlaufzeit", k["durchlauf_min"], True),
                  ("Arbeitskosten", k["arbeitskosten"], False))
        linie = "border-top:1px solid #C9D0D8"
        html = f"<table width='100%' cellpadding='1' cellspacing='0'><tr><td colspan='2' style='{linie}'>" \
               f"<b>Zeiten</b></td></tr>"
        n = 0
        for t, w, zeit in zeilen:
            if sichtbar(w):
                n += 1
                html += f"<tr><td>{t}</td><td align='right'>{rechnen.zeit_text(w) if zeit else _z(w) + ' €'}</td></tr>"
        self.zeiten.setText(html + "</table>")
        self.zeiten.setVisible(bool(n))
