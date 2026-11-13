"""Dialog 'Bohrungen prüfen': Gewinde-Vorschläge, Senkungen, Fließlochbohrungen und Bohrungen kleiner als
0,7 × Wandstärke (Bohren) einer Position bestätigen oder ablehnen (Doppelklick auf Status, Gewinde oder Bohrungen der
Position). Bestätigte Senkungen, Flowdrill und Bohren werden als Zusatzarbeit vorgeschlagen. Rechnet nichts selbst:
bohrbild.py.

Ausführung nachträglich ändern (Patrick 03.11.2026): je Zeile eine Auswahl Ausführung (Gewinde schneiden, Flowdrill,
Einnietmutter, Senkung, Bohren, nur lasern) mit ★ für den Vorschlag (bohrbild.vorschlaege) und dem Grund in der Spalte
Vorschlag; unten „Alle M8 → …“ und „★ Vorschläge übernehmen“ (auch im Fenster für mehrere Positionen = ganzes
Angebot). Eine geänderte Ausführung gilt als bestätigt."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import hilfe
from . import bohrbild, rechnen, stil
from .stammdaten import zahl_als_text

KEIN_GEWINDE = "kein Gewinde"
OHNE_GRAVUR, MIT_GRAVUR = "Senk-Ø nicht gravieren", "Senk-Ø gravieren"
ART_TEXT = {"Bohrung": "Bohrung (Kernloch)", "Fließloch": "Flowdrill", bohrbild.BOHREN: "Bohren (< 0,7 × Wand)"}
ROT, GELB, GRUEN = "#B42318", "#7A5A00", "#1B6E2E"


class _Zeile:
    """Bedienelemente einer Bohrbild-Zeile (beide Fenster): Ausführung mit ★, Vorschlag, Gewinde, Laser,
    Bestätigen/Ablehnen. geaendert() ruft das Fenster nach jeder Änderung."""

    def __init__(self, z, gewinde, wand, werkstoff, grenzen, laser, geaendert, stamm_arbeit=None, mit_preisen=True,
                 stamm_gewinde=None):
        self.z, self.tab, self.wand, self.werkstoff, self.grenzen = z, gewinde, wand, werkstoff, grenzen
        self.stamm_gewinde = stamm_gewinde      # CALC-027: Preis je Option in der Auswahl (None = ohne)
        self.vorgabe_laser, self.geaendert, self.stamm_arbeit = laser, geaendert, stamm_arbeit or {}
        self.natur = bohrbild.ausfuehrung(z)
        self._still = True
        self.aus = QComboBox()
        self.aus.setMinimumWidth(230)
        self.vorschlag = QLabel()
        self.vorschlag.setWordWrap(True)
        self.vorschlag.setMinimumWidth(240)
        self.gewinde = QComboBox()
        self.gewinde.addItem(KEIN_GEWINDE)
        namen = {g for g, _ in gewinde} | ({z["gewinde"]} if z.get("gewinde") else set())
        groesse = bohrbild.groesse(z, gewinde)
        if groesse:
            namen.add(groesse)
        self.gewinde.addItems(sorted(namen, key=_gewinde_sortierung))
        self.gewinde.setCurrentText(z.get("gewinde") or KEIN_GEWINDE)
        self.laser = QComboBox()
        self.g_preis = self.a_preis = None
        if mit_preisen:
            self.g_preis = _preisfeld(z.get("gewinde_preis"), self._neu)
            self.a_preis = _preisfeld(z.get("preis"), self._neu)
        self.knoepfe = QWidget()
        kl = QHBoxLayout(self.knoepfe)
        kl.setContentsMargins(2, 0, 2, 0)
        self.gruppe = QButtonGroup(self.knoepfe)
        for text, status, farbe in (("✓ Bestätigen", bohrbild.BESTAETIGT, "#C6EFCE"),
                                    ("✗ Ablehnen", bohrbild.ABGELEHNT, "#FFC7CE")):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setProperty("status", status)
            b.setStyleSheet(f"QPushButton:checked {{ background: {farbe}; font-weight: bold; }}")
            b.setChecked(z.get("status") == status)
            self.gruppe.addButton(b)
            kl.addWidget(b)
        self.gruppe.buttonClicked.connect(self._neu)
        self._aus_fuellen(self.natur)
        self._laser_fuellen()
        self.aus.currentIndexChanged.connect(self._aus_gewechselt)
        self.gewinde.currentTextChanged.connect(self._gewinde_gewechselt)
        self.laser.currentIndexChanged.connect(self._neu)
        self._still = False
        self._auffrischen()

    # ---------------------------------------------------------- Werte
    def groesse(self):
        return None if self.gewinde.currentText() == KEIN_GEWINDE else self.gewinde.currentText()

    def ausfuehrung(self):
        return self.aus.currentData() or self.natur

    def status(self):
        b = self.gruppe.checkedButton()
        return b.property("status") if b else bohrbild.OFFEN

    def vorschlaege(self):
        z = dict(self.z, gewinde=self.groesse())
        return bohrbild.vorschlaege(z, self.wand, self.werkstoff, self.tab, self.grenzen)

    def wert(self):
        """Zeile nach der Wahl."""
        z = dict(self.z, status=self.status())
        if "gewinde" in z or self.groesse():
            z["gewinde"] = self.groesse()
        if self.g_preis is not None:
            z["gewinde_preis"] = _preis(self.g_preis)
        if self.a_preis is not None:
            z["preis"] = _preis(self.a_preis)
        aus = self.ausfuehrung()
        if aus != self.natur or self.z.get("aus") or (z.get("gewinde") or None) != (self.z.get("gewinde") or None) \
                and self.z.get("aus"):
            z = bohrbild.ausfuehrung_setzen(z, aus, self.tab, self.vorgabe_laser, self.groesse())
        t = self.laser.currentText()
        if aus in (bohrbild.FLOWDRILL, bohrbild.AUFBOHREN) and t in bohrbild.LASER:
            z["laser"] = t
        elif aus == bohrbild.SENKEN and self.laser.isEnabled():
            z["gravur"] = self.laser.currentIndex() == 1
        return z

    # ---------------------------------------------------------- setzen (Maus, Tests)
    def aus_setzen(self, aus):
        i = self.aus.findData(aus)
        if i >= 0:
            self.aus.setCurrentIndex(i)
        return i >= 0

    def status_setzen(self, status):
        for b in self.gruppe.buttons():
            b.setChecked(b.property("status") == status)
        self._neu()

    # ---------------------------------------------------------- intern
    def _aus_fuellen(self, wahl):
        self._still, alt = True, self._still
        self.aus.clear()
        for v in self.vorschlaege():
            text = ("★ " if v["rang"] == 0 else "") + v["aus"] + (" (nicht empfohlen)" if v["rang"] == 2 else "")
            if self.stamm_gewinde is not None:
                w = bohrbild.option_preis(v["aus"], self.groesse(), self.stamm_gewinde, self.stamm_arbeit)
                text += f" – {zahl_als_text(w, 2)} €" if w is not None else " – Preis fehlt"
            self.aus.addItem(text, v["aus"])
            self.aus.setItemData(self.aus.count() - 1, v["grund"], Qt.ToolTipRole)
        if self.aus.findData(wahl) < 0:         # gewählt, aber nicht in der Liste (z. B. Bohren bei großer Bohrung)
            self.aus.addItem(wahl, wahl)
        self.aus.setCurrentIndex(self.aus.findData(wahl))
        self._still = alt

    def _laser_fuellen(self):
        self._still, alt = True, self._still
        aus = self.ausfuehrung()
        self.laser.clear()
        if aus in (bohrbild.FLOWDRILL, bohrbild.AUFBOHREN):
            self.laser.addItems(bohrbild.LASER)
            self.laser.setCurrentText(self.z.get("laser") if self.z.get("laser") in bohrbild.LASER
                                      else self.vorgabe_laser if self.vorgabe_laser in bohrbild.LASER
                                      else bohrbild.GRAVUR)
            self.laser.setEnabled(True)
            self.laser.setToolTip("Was der Laser an der Bohrung macht: Markierung als Gravur oder Loch Ø0,5")
        elif aus == bohrbild.SENKEN:
            D = self.z.get("D") or bohrbild.SENK_D.get(self.groesse() or "")
            self.laser.addItems([OHNE_GRAVUR, f"{MIT_GRAVUR} Ø{bohrbild.dez(D)}" if D else MIT_GRAVUR])
            self.laser.setCurrentIndex(1 if self.z.get("gravur") else 0)
            self.laser.setEnabled(True)
            self.laser.setToolTip("Senkung: der Laser schneidet die Bohrung, auf Wunsch wird der Senk-Ø graviert")
        else:
            d = bohrbild.laser_d(dict(self.z, gewinde=self.groesse()), aus, self.tab)
            self.laser.addItem(f"schneidet Ø{bohrbild.dez(d)}" if d else "schneidet die Bohrung")
            self.laser.setEnabled(False)
            self.laser.setToolTip("Ø, den der Laser für die Ausführung schneidet")
        self._still = alt

    def _aus_gewechselt(self, *_):
        if self._still:
            return
        if self.a_preis is not None:
            self.a_preis.clear()         # Preis gehörte zur alten Arbeit
        if self.status() != bohrbild.BESTAETIGT:     # selbst gewählt = bestätigt
            for b in self.gruppe.buttons():
                b.setChecked(b.property("status") == bohrbild.BESTAETIGT)
        self._laser_fuellen()
        self._neu()

    def _gewinde_gewechselt(self, *_):
        if self._still:
            return
        self._aus_fuellen(self.ausfuehrung())
        self._laser_fuellen()
        self._neu()

    def _neu(self, *_):
        if self._still:
            return
        self._auffrischen()
        self.geaendert()

    def _auffrischen(self):
        aus = self.ausfuehrung()
        self.gewinde.setEnabled(aus in bohrbild.MIT_GROESSE or (aus == bohrbild.SENKEN and
                                                                self.z.get("art") != "Senkung"))
        if self.g_preis is not None:
            g = self.groesse()
            self.g_preis.setEnabled(bool(g) and aus in (bohrbild.GEWINDE_SCHNEIDEN, bohrbild.FLOWDRILL))
        if self.a_preis is not None:
            name = bohrbild.ZUSATZ_AUS.get(aus)
            stamm = self.stamm_arbeit.get(name)
            self.a_preis.setEnabled(bool(name))
            self.a_preis.setPlaceholderText((zahl_als_text(stamm, 2) if stamm is not None else "fehlt") if name
                                            else "")
            self.a_preis.setToolTip(f"€ je Stück für {name}; leer = Einstellungen › Zusatzarbeiten" if name else "")
        v = self.vorschlaege()
        stern = next((x for x in v if x["rang"] == 0), None)
        gew = next((x for x in v if x["aus"] == aus), None)
        teile = []
        if stern:
            teile.append(f"<span style='color:{GRUEN}'>★ {bohrbild.KURZ[stern['aus']]}</span>: {stern['grund']}")
        if gew and gew["rang"] == 2:
            teile.append(f"<span style='color:{ROT}'>gewählt nicht empfohlen: {gew['grund']}</span>")
        z = self.wert()
        if bohrbild.abweichend(z):
            teile.append(f"<span style='color:{GELB}'>weicht von STEP ab ({bohrbild.KURZ[self.natur]})</span>")
        self.vorschlag.setText("<br>".join(teile))
        self.vorschlag.setToolTip("<br>".join(f"{'★ ' if x['rang'] == 0 else ''}{x['aus']}: {x['grund']}" for x in v))


def _preisfeld(wert, geaendert):
    """Eingabe € je Stück: leer = Preis der Einstellungen (als graue Vorgabe), sonst nur für diese Position."""
    f = QLineEdit(zahl_als_text(wert, 2, tausender=False) if isinstance(wert, (int, float)) else "")
    f.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    f.setFixedWidth(90)
    f.textChanged.connect(geaendert)
    return f


def _preis(feld):
    if feld is None or not feld.isEnabled() or not feld.text().strip():
        return None
    try:
        w = float(feld.text().strip().replace(".", "").replace(",", ".") if "," in feld.text()
                  else feld.text().strip())
    except ValueError:
        return None
    return w if w >= 0 else None


def _schluessel(z, tab):
    """Gruppe für „Alle … umstellen“: Gewindegröße, sonst der Ø."""
    g = z.get("gewinde") or bohrbild.groesse(z, tab)
    return g or f"Ø{bohrbild.dez(z.get('d'))}"


class _Umstellen(QWidget):
    """Leiste „Alle [M8] → [Ausführung] umstellen“ und „★ Vorschläge übernehmen“ für die Zeilen eines Fensters."""

    def __init__(self, zeilen, tab, geaendert):
        super().__init__()
        self.zeilen, self.tab, self.geaendert = zeilen, tab, geaendert
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("Alle"))
        self.gruppe = QComboBox()
        gruppen = []
        for zl in zeilen:
            s = _schluessel(dict(zl.z, gewinde=zl.groesse()), tab)
            if s not in gruppen:
                gruppen.append(s)
        self.gruppe.addItems(sorted(gruppen, key=_gewinde_sortierung))
        self.gruppe.setToolTip("Alle Bohrungen dieser Gewindegröße (bzw. dieses Ø) im Fenster")
        lay.addWidget(self.gruppe)
        lay.addWidget(QLabel("→"))
        self.ziel = QComboBox()
        self.ziel.addItems(bohrbild.AUSFUEHRUNGEN)
        lay.addWidget(self.ziel)
        k = QPushButton("Umstellen")
        k.setToolTip("Ausführung aller passenden Zeilen ändern (gilt als bestätigt); Zeilen, für die sie nicht geht "
                     "(z. B. Bohren bei großer Bohrung), bleiben")
        k.clicked.connect(lambda: self.umstellen(self.gruppe.currentText(), self.ziel.currentText()))
        lay.addWidget(k)
        lay.addSpacing(16)
        st = QPushButton("★ Vorschläge übernehmen")
        st.setToolTip("Jede Zeile auf die mit ★ vorgeschlagene Ausführung stellen und bestätigen")
        st.clicked.connect(self.vorschlaege)
        lay.addWidget(st)
        lay.addStretch(1)
        self.setEnabled(bool(zeilen))

    def umstellen(self, gruppe, aus):
        """Ergebnis: Anzahl umgestellter Zeilen."""
        n = 0
        for zl in self.zeilen:
            if _schluessel(dict(zl.z, gewinde=zl.groesse()), self.tab) == gruppe and zl.aus_setzen(aus):
                zl.status_setzen(bohrbild.BESTAETIGT)
                n += 1
        self.geaendert()
        return n

    def vorschlaege(self):
        for zl in self.zeilen:
            stern = next((x for x in zl.vorschlaege() if x["rang"] == 0), None)
            if stern:
                zl.aus_setzen(stern["aus"])
            zl.status_setzen(bohrbild.BESTAETIGT)
        self.geaendert()


class BohrbildDialog(QDialog):
    """Je Zeile: Art (STEP), Ø, Anzahl je Teil, Ausführung (★ Vorschlag), Vorschlag mit Grund, Gewinde, Preise, was
    der Laser macht und Bestätigen/Ablehnen. Unten Umstellen, weitere Gewinde von Hand und die Auswirkung. Ergebnis:
    self.ergebnis = (Liste, Text der Gewinde von Hand)."""
    SPALTEN = ("Art (STEP)", "Ø [mm]", "Anzahl je Teil", "Ausführung", "Vorschlag", "Gewinde", "Gewinde [€/Stk]",
               "Arbeit [€/Stk]", "Laser", "Prüfung")
    AUS, VORSCHLAG, GEW, G_PREIS, A_PREIS, LASER_SP, PRUEF = 3, 4, 5, 6, 7, 8, 9

    def __init__(self, parent, p, gewinde, wand=None, laser=None, katalog=None, saetze=None, gewinde_preise=None,
                 werkstoff=None, grenzen=None):
        """gewinde = [(Gewinde, Kernloch)] der Stammdaten, wand = Wandstärke (Bohren < 0,7 × Wand, Vorschläge), laser
        = Vorgabe für Bohren (Einstellung bohren_laser), katalog = Zeilen der Zusatzarbeiten (None: Zusatzarbeiten
        nicht anzeigen), gewinde_preise = {Gewinde: € je Stück} der Einstellungen, werkstoff = Werkstoff der Position
        (Alu: mehr Gänge), grenzen = Grenzen der Vorschläge (bohrbild.grenzen_aus). Preise je Zeile: leer =
        Einstellungen (grau), sonst nur diese Position."""
        super().__init__(parent)
        self.p = p
        self.katalog, self.saetze = katalog, saetze
        self.stamm_gewinde = gewinde_preise or {}
        self.stamm_arbeit = {z.get("name"): rechnen.zusatz_preis(z, saetze)["preis"] for z in katalog or ()
                             if z.get("name")}
        self.liste = [dict(z) for z in bohrbild.aus_position(p, gewinde, wand, laser or bohrbild.GRAVUR)]
        self.ergebnis = None
        titel = " ".join(str(x) for x in (p.get("pos"), p.get("artikel")) if x)
        self.setWindowTitle(f"Bohrungen prüfen – Pos. {titel}")
        self.resize(1500, 420)
        lay = QVBoxLayout(self)
        info = hilfe.Hinweis("Je Zeile „Bestätigen“ oder „Ablehnen“, die Ausführung lässt sich ändern (★ = Vorschlag "
                      "nach Gewindegröße, Wandstärke und Werkstoff, Grund in der Spalte Vorschlag). Gewinde werden "
                      "erst nach dem Bestätigen gerechnet. Ausführungen: Gewinde schneiden (Laser schneidet das "
                      "Kernloch), Flowdrill + Gewinde formen (Laser markiert nur), Einnietmutter (Laser schneidet "
                      "das Loch für die Mutter), Senkung (Bohrung, auf Wunsch Senk-Ø graviert), Bohren (markieren, "
                      "danach aufbohren), nur lasern (Ø schneiden). Eine geänderte Ausführung gilt als bestätigt; "
                      "die STEP-Kontur im Export bleibt, nur die Kalkulation folgt (Hinweis „weicht von STEP ab“). "
                      "Senken, Flowdrill, Bohren und Einnietmuttern kommen als Zusatzarbeit (€/Stück) mit der Anzahl "
                      "je Teil in die Position.", schluessel="bohrbild")
        lay.addWidget(info)
        self.tabelle = QTableWidget(len(self.liste), len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.zeilen = []
        for r, z in enumerate(self.liste):
            masse = bohrbild.dez(z.get("d")) + (f" / {bohrbild.dez(z.get('D'))}" if z.get("D") else "")
            art = ART_TEXT.get(z["art"], z["art"])
            if z.get("zeichnung"):      # Vorschlag aus der Zeichnung (zeichnung_hinweise, 03.11.2026)
                art += " · Zeichnung"
            for c, text in ((0, art), (1, masse), (2, str(z.get("anzahl") or ""))):
                it = QTableWidgetItem(text)
                if c:
                    it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                if z.get("zeichnung"):
                    it.setBackground(QBrush(QColor(stil.GELB_FLAECHE)))
                    it.setToolTip(z["zeichnung"] + ("\nDie gelaserte Bohrung entfällt erst nach „Bestätigen“."
                                                    if z.get("aus_bohrung") else ""))
                self.tabelle.setItem(r, c, it)
            zl = _Zeile(z, gewinde, wand, werkstoff or p.get("werkstoff_id"), grenzen, laser, self._auswirkung,
                        self.stamm_arbeit, stamm_gewinde=self.stamm_gewinde if katalog is not None else None)
            zl.gewinde.currentTextChanged.connect(lambda _=None, r=r: self._gewinde_platzhalter(r))
            for c, w in ((self.AUS, zl.aus), (self.VORSCHLAG, zl.vorschlag), (self.GEW, zl.gewinde),
                         (self.G_PREIS, zl.g_preis), (self.A_PREIS, zl.a_preis), (self.LASER_SP, zl.laser),
                         (self.PRUEF, zl.knoepfe)):
                self.tabelle.setCellWidget(r, c, w)
            self.zeilen.append(zl)
        # Zugriff wie bisher (Tests, Bildschirmfotos)
        self.gruppen = [zl.gruppe for zl in self.zeilen]
        self.gewinde = [zl.gewinde for zl in self.zeilen]
        self.laser = [zl.laser for zl in self.zeilen]
        self.preise = [(zl.g_preis, zl.a_preis) for zl in self.zeilen]
        self.ausfuehrung = [zl.aus for zl in self.zeilen]
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setStretchLastSection(True)
        self.tabelle.verticalHeader().setDefaultSectionSize(46)
        lay.addWidget(self.tabelle, 1)
        if not self.liste:
            lay.addWidget(QLabel("Diese Position hat keine Gewinde-Vorschläge, Senkungen, Fließlochbohrungen oder "
                                 "Bohrungen kleiner als 0,7 × Wandstärke."))
        self.umstellen = _Umstellen(self.zeilen, gewinde, self._auswirkung)
        lay.addWidget(self.umstellen)
        zeile = QHBoxLayout()
        alle = QPushButton("Alle bestätigen")
        alle.clicked.connect(self.alle_bestaetigen)
        alle.setEnabled(bool(self.liste))
        zeile.addWidget(alle)
        zeile.addSpacing(16)
        zeile.addWidget(QLabel("Weitere Gewinde von Hand:"))
        self.hand = QLineEdit(bohrbild.hand_gewinde(p, self.liste))
        self.hand.setPlaceholderText("z. B. 2xM10; 1xM12")
        self.hand.textChanged.connect(self._auswirkung)
        zeile.addWidget(self.hand, 1)
        lay.addLayout(zeile)
        self.auswirkung = QLabel()
        self.auswirkung.setWordWrap(True)
        lay.addWidget(self.auswirkung)
        bb = QDialogButtonBox()
        bb.addButton("Übernehmen", QDialogButtonBox.AcceptRole)
        bb.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for r in range(len(self.liste)):
            self._gewinde_platzhalter(r)
        self._auswirkung()

    def _gewinde_platzhalter(self, r):
        gp, g = self.preise[r][0], self.zeilen[r].groesse()
        if gp is None:
            return
        stamm = self.stamm_gewinde.get(g) if g else None
        gp.setPlaceholderText(zahl_als_text(stamm, 2) if stamm is not None else ("fehlt" if g else ""))
        gp.setToolTip(f"€ je Gewinde {g}; leer = Einstellungen › Gewinde" if g else "")

    def werte(self):
        """Bohrbild nach der Wahl im Dialog."""
        return [zl.wert() for zl in self.zeilen]

    def setzen(self, nr, status=None, gewinde=None, laser=None, gravur=None, preis=None, gewinde_preis=None,
               ausfuehrung=None):
        """Zeile nr ohne Maus setzen (Tests, Bildschirmfotos); preis/gewinde_preis als Text, '' = Einstellungen;
        laser = bohrbild.SCHNEIDEN wählt bei 'Bohren' die Ausführung nur lasern (wie bisher die 3. Option)."""
        zl = self.zeilen[nr]
        if gewinde is not None:
            zl.gewinde.setCurrentText(gewinde)
        if ausfuehrung is not None:
            zl.aus_setzen(ausfuehrung)
        if laser == bohrbild.SCHNEIDEN:
            zl.aus_setzen(bohrbild.NUR_LASER)
        elif laser is not None:
            if zl.ausfuehrung() not in (bohrbild.FLOWDRILL, bohrbild.AUFBOHREN):
                zl.aus_setzen(bohrbild.AUFBOHREN if zl.z.get("art") == bohrbild.BOHREN else bohrbild.FLOWDRILL)
            zl.laser.setCurrentText(laser)
        if gravur is not None:
            zl.laser.setCurrentIndex(1 if gravur else 0)
        if preis is not None:
            zl.a_preis.setText(preis)
        if gewinde_preis is not None:
            zl.g_preis.setText(gewinde_preis)
        if status is not None:
            zl.status_setzen(status)
        self._auswirkung()

    def alle_bestaetigen(self):
        for nr in range(len(self.liste)):
            self.setzen(nr, bohrbild.BESTAETIGT)

    def _auswirkung(self, *_):
        if not hasattr(self, "auswirkung"):
            return
        neu = self.werte()
        felder = bohrbild.anwenden(self.p, neu, self.hand.text(), self.katalog, self.saetze)
        teile = []
        for name, titel, einheit, stellen in (("schneidweg", "Schneidweg", " mm", 1), ("gravur", "Gravur", " mm", 1),
                                              ("einstiche", "Einstiche", "", 0)):
            if name in felder:
                alt, wert = self.p.get(name) or 0, felder[name] or 0
                teile.append(f"{titel} {zahl_als_text(alt, stellen)} → {zahl_als_text(wert, stellen)}{einheit}")
        g_preise = dict(self.stamm_gewinde, **bohrbild.gewinde_preise(neu))
        g_tab = [dict(gewinde=g, preis=w) for g, w in g_preise.items()]
        g_eur = rechnen.gewinde_preis(felder.get("gewinde"), g_tab) if felder.get("gewinde") else 0
        teile.append("Gewinde: " + (f"{felder['gewinde']} = {zahl_als_text(g_eur, 2)} €" if felder.get("gewinde")
                                    else "keine"))
        if self.katalog is not None:
            a_preise = dict(self.stamm_arbeit, **bohrbild.arbeit_preise(neu))
            arbeiten = bohrbild.arbeiten(neu)
            teile.append("Zusatzarbeiten: " + (", ".join(
                f"{n}× {name} à {zahl_als_text(a_preise.get(name) or 0, 2)} €" for name, n in arbeiten.items())
                or "keine"))
            if felder.get("_fehlt"):
                teile.append(f"<span style='color:{ROT}'>{', '.join(felder['_fehlt'])} fehlt in den Stammdaten "
                             "Zusatzarbeiten</span>")
        offen = bohrbild.offen(neu)
        if offen:
            teile.append(f"<span style='color:{GELB}'>{offen} Zeile{'n' if offen != 1 else ''} noch offen</span>")
        hinweis = bohrbild.step_hinweis(neu)
        if hinweis:
            teile.append(f"<span style='color:{GELB}'>{hinweis}</span>")
        self.auswirkung.setText("Auswirkung je Teil: " + " · ".join(teile))

    def accept(self):
        self.ergebnis = (self.werte(), self.hand.text())
        super().accept()


class BohrbildSammelDialog(QDialog):
    """„Bohrungen prüfen“ für mehrere Positionen in einer Tabelle (Plan Angebotsablauf V3): je Zeile Pos., Art, Ø,
    Anzahl je Teil, Ausführung (★), Vorschlag, Gewinde, Laser und Bestätigen/Ablehnen; „Alle bestätigen“, „Alle M8 →
    …“ (ganzes Angebot) und ein Übernehmen statt eines Fensters je Position. Preise je Position und Gewinde von Hand
    bleiben, wie sie sind (dafür das Fenster der einen Position). positionen = [(Zeile, Position, Wandstärke)].
    Ergebnis: self.ergebnis = {Zeile: Bohrbild-Liste}."""
    SPALTEN = ("Pos.", "Artikelnummer", "Art (STEP)", "Ø [mm]", "Anzahl je Teil", "Ausführung", "Vorschlag",
               "Gewinde", "Laser", "Prüfung")
    PRUEF = 9

    def __init__(self, parent, positionen, gewinde, laser=None, grenzen=None):
        super().__init__(parent)
        self.ergebnis = None
        self.zeilen = []        # (Zeile der Position, Index im Bohrbild, Auswahl Gewinde, Laser, Knopfgruppe)
        self._zeilen = []       # _Zeile je Tabellenzeile
        self.listen = {}
        for r, p, wand in positionen:
            self.listen[r] = [dict(z) for z in bohrbild.aus_position(p, gewinde, wand, laser or bohrbild.GRAVUR)]
        n = sum(len(liste) for liste in self.listen.values())
        self.setWindowTitle(f"Bohrungen prüfen – {len(positionen)} Positionen")
        self.resize(1450, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(hilfe.Hinweis(
            "Je Zeile „Bestätigen“ oder „Ablehnen“, oder alles mit „Alle bestätigen“. Die Ausführung lässt sich je "
            "Zeile oder mit „Alle M8 → …“ für das ganze Angebot ändern (★ = Vorschlag). Gewinde werden erst nach dem "
            "Bestätigen gerechnet; Senken, Flowdrill, Bohren und Einnietmuttern kommen als Zusatzarbeit (€/Stück) in "
            "die Position. Preise je Position und Gewinde von Hand: Doppelklick auf die Position im Angebot.",
            schluessel="bohrbild_sammel"))
        self.tabelle = QTableWidget(n, len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        zeile = 0
        for r, p, wand in positionen:
            for i, z in enumerate(self.listen[r]):
                masse = bohrbild.dez(z.get("d")) + (f" / {bohrbild.dez(z.get('D'))}" if z.get("D") else "")
                for c, text in ((0, str(p.get("pos") or "") if i == 0 else ""),
                                (1, str(p.get("artikel") or "") if i == 0 else ""),
                                (2, ART_TEXT.get(z["art"], z["art"])), (3, masse), (4, str(z.get("anzahl") or ""))):
                    it = QTableWidgetItem(text)
                    if c in (0, 3, 4):
                        it.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
                    self.tabelle.setItem(zeile, c, it)
                zl = _Zeile(z, gewinde, wand, p.get("werkstoff_id"), grenzen, laser, self._stand, mit_preisen=False)
                for c, w in ((5, zl.aus), (6, zl.vorschlag), (7, zl.gewinde), (8, zl.laser), (self.PRUEF, zl.knoepfe)):
                    self.tabelle.setCellWidget(zeile, c, w)
                self.zeilen.append((r, i, zl.gewinde, zl.laser, zl.gruppe))
                self._zeilen.append(zl)
                zeile += 1
        kopf = self.tabelle.horizontalHeader()
        kopf.setSectionResizeMode(QHeaderView.ResizeToContents)
        kopf.setSectionResizeMode(1, QHeaderView.Interactive)
        self.tabelle.setColumnWidth(1, 200)
        kopf.setStretchLastSection(True)
        self.tabelle.verticalHeader().setDefaultSectionSize(46)
        lay.addWidget(self.tabelle, 1)
        self.umstellen = _Umstellen(self._zeilen, gewinde, self._stand)
        lay.addWidget(self.umstellen)
        unten = QHBoxLayout()
        alle = QPushButton("Alle bestätigen")
        alle.clicked.connect(self.alle_bestaetigen)
        unten.addWidget(alle)
        self.info = QLabel()
        unten.addWidget(self.info, 1)
        lay.addLayout(unten)
        bb = QDialogButtonBox()
        bb.addButton("Übernehmen", QDialogButtonBox.AcceptRole)
        bb.addButton("Abbrechen", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._stand()

    def setzen(self, nr, status=None, ausfuehrung=None):
        if ausfuehrung is not None:
            self._zeilen[nr].aus_setzen(ausfuehrung)
        if status is not None:
            self._zeilen[nr].status_setzen(status)
        self._stand()

    def alle_bestaetigen(self):
        for nr in range(len(self.zeilen)):
            self.setzen(nr, bohrbild.BESTAETIGT)

    def werte(self):
        """{Zeile der Position: Bohrbild nach der Wahl im Dialog}."""
        out = {r: [dict(z) for z in liste] for r, liste in self.listen.items()}
        for (r, i, *_), zl in zip(self.zeilen, self._zeilen):
            out[r][i] = zl.wert()
        return out

    def _stand(self, *_):
        if not hasattr(self, "info"):
            return
        werte = self.werte()
        n = sum(bohrbild.offen(liste) for liste in werte.values())
        ab = sum(1 for liste in werte.values() for z in liste if bohrbild.abweichend(z))
        self.info.setText((f"<span style='color:{GELB}'>{n} Zeile{'n' if n != 1 else ''} noch offen</span>" if n
                           else "Alle Zeilen geprüft.")
                          + (f" · <span style='color:{GELB}'>{ab} Zeile{'n' if ab != 1 else ''} weich"
                             f"{'en' if ab != 1 else 't'} von STEP ab (Kontur im Export bleibt)</span>" if ab else ""))

    def accept(self):
        self.ergebnis = self.werte()
        super().accept()


def _gewinde_sortierung(g):
    try:
        return (0, float(str(g).upper().lstrip("M").replace(",", ".")))
    except ValueError:
        return (1, str(g))
