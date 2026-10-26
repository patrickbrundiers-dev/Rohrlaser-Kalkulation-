"""Zusatzfenster zum Fenster 'Material je Abmessung' (Patrick 23.10.2026: "auf Stangenanzahl Doppelklick, dann die
Optimierung für diesen Stangentyp in extra Fenster öffnen mit Liste der Teile darunter"; Freigabe 1a–6a):

- AbmessungFenster: Kennzahlen, Stangenbild nur dieser Abmessung, Schnittmuster, Meter-/Gewichtsbilanz und die
  Teileliste; Knöpfe für Neu optimieren, 12-m-Vergleich, Materialanfrage, Schnittplan drucken, Positionen markieren.
- PreisFenster: Preis-Aufbau des Materials mit der Herkunft des Meterpreises.
- ProfilFenster: Querschnitt groß mit Kennwerten und welche Maschinen das Profil laden können.

Die Werte rechnet abmessung.py. Schritte, die das Material-Fenster schließen müssen (zur Position, neu optimieren …),
gibt das Fenster an MeterpreisDialog.schliessen_mit weiter; ausgeführt werden sie danach im Angebot.
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
                               QHeaderView, QLabel, QMenu, QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextBrowser, QVBoxLayout, QWidget)

from . import abmessung, hilfe, rechnen, stil
from .meterpreis_dialog import laengen_text, querschnitt_pixmap
from .stammdaten import zahl_als_text


def _z(w, stellen=2):
    return "" if w is None else zahl_als_text(w, stellen)


def titel(g):
    """'QR 40x40x3 · S235 roh · 6.000 mm · Eigenmaterial' für Fenstertitel und Kopf."""
    return (f"{g['profil']} · {rechnen.material_text(g['werkstoff'], g['oberflaeche'])} · "
            f"{laengen_text(g) or _z(g['stange'], 0) + ' mm'} · {'Kundenmaterial' if g['kunde'] else 'Eigenmaterial'}")


def _tabelle(spalten, zeilen=0):
    t = QTableWidget(zeilen, len(spalten))
    t.setHorizontalHeaderLabels([s[0] for s in spalten])
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectRows)
    t.setSelectionMode(QAbstractItemView.SingleSelection)
    t.setAlternatingRowColors(True)
    t.verticalHeader().setDefaultSectionSize(t.fontMetrics().height() + 8)
    kopf = t.horizontalHeader()
    for i, s in enumerate(spalten):         # mindestens so breit, dass der Spaltentitel ganz zu lesen ist
        t.setColumnWidth(i, max(s[1], kopf.fontMetrics().horizontalAdvance(s[0]) + 24))
    return t


def _zelle(text, rechts=False, farbe=None, fett=False, tipp=None):
    it = QTableWidgetItem("" if text is None else str(text))
    if rechts:
        it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if farbe:
        it.setForeground(QColor(farbe))
    if fett:
        f = QFont()
        f.setBold(True)
        it.setFont(f)
    if tipp:
        it.setToolTip(tipp)
    return it


MUSTER_SPALTEN = (("Anzahl", 55), ("Stangen", 80), ("Länge [mm]", 75), ("Teile je Stange", 330), ("Rest [mm]", 70),
                  ("Ausnutzung [%]", 85), ("Material je Stange [€]", 110))
BILANZ_SPALTEN = (("Posten", 130), ("Meter", 65), ("Anteil [%]", 70), ("Gewicht [kg]", 85))
# Teileliste (F3a: alle Spalten, über das Kontextmenü der Kopfzeile ausblendbar): (Titel, Breite, Schlüssel, Stellen)
TEILE_SPALTEN = (("Pos.", 45, "pos", 0), ("Artikelnummer", 120, "artikel", None), ("Bezeichnung", 140, "bezeichnung", None),
                 ("Länge [mm]", 75, "laenge", 1), ("Stück", 50, "stueck", 0), ("Enden A / B", 140, "enden", None),
                 ("Naht / Drehung", 150, "lage", None), ("eingeplant", 70, "eingeplant", 0),
                 ("auf Stangen", 90, "stangen", None), ("Meter", 60, "meter", 2), ("Gewicht [kg]", 75, "kg", 1),
                 ("Anteil [%]", 65, "anteil", 1), ("Material je Teil [€]", 95, "material_teil", 3),
                 ("Laserzeit berechnet [s]", 95, "laser_brutto", 1), ("Laserzeit genutzt [s]", 95, "laser_netto", 1),
                 ("Verkaufspreis je Teil [€]", 105, "preis_teil", 3))


class AbmessungFenster(QDialog):
    """Abmessungs-Fenster (F1a: über dem Material-Fenster; F2a: alles untereinander). material = MeterpreisDialog
    (schliessen_mit, seite), g = Gruppe aus rechnen.material_abmessungen, fokus = 'stangen', 'teile' oder 'bilanz'."""

    def __init__(self, material, g, fokus="stangen"):
        super().__init__(material)
        self.material, self.g, self.seite = material, g, material.seite
        s = self.seite
        self.setWindowTitle("Abmessung " + titel(g))
        self.resize(1250, 860)
        lay = QVBoxLayout(self)
        sw = rechnen.stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen) \
            if s.ergebnis and s.ergebnis.get("stangen") else []
        self.paare = abmessung.stangen(s.ergebnis, g["gruppe"], sw) if sw else []
        kgm = rechnen.kg_je_m(g["profil"], g["werkstoff"], s.k)
        self.bilanz = abmessung.bilanz(self.paare, kgm, g["meter"] if self.paare else None)
        zeilen = s._rechnung()[0]
        self.teile = abmessung.teile(g, s.kopf, s.positionen, self.paare, zeilen, s.k)
        self.laengen = abmessung.laengen_indizes(s.ergebnis, g)

        oben = QHBoxLayout()
        bild = QLabel()
        bild.setPixmap(querschnitt_pixmap(s.k.profile.get(g["profil"]), 64))
        oben.addWidget(bild)
        kopf = QLabel(self.kennzahlen())
        kopf.setTextFormat(Qt.RichText)
        kopf.setWordWrap(True)
        oben.addWidget(kopf, 1)
        lay.addLayout(oben)
        self.warnung = QLabel()
        self.warnung.setStyleSheet(f"color: {stil.ROT};")
        if material.ohne_plan:
            self.warnung.setText("Noch nicht optimiert: Stangenbild, Schnittmuster und Bilanz folgen nach dem Optimieren.")
        elif material.veraltet:
            self.warnung.setText("Der Schnittplan passt nicht mehr zu den Positionen – bitte neu optimieren.")
        self.warnung.setVisible(bool(self.warnung.text()))
        lay.addWidget(self.warnung)

        teiler = QSplitter(Qt.Vertical)
        # Umschalter Stangenmuster / Übersicht / Detail wie im Reiter Stangenbild (Lantek-Ideen, F2a)
        from .angebot_fenster import STANGENBILD_EINSTELLUNG
        from .stangen_ansicht import StangenSeite
        db = getattr(s, "db", None)
        self.stangen_seite = StangenSeite(db.einstellung(STANGENBILD_EINSTELLUNG) if db else None,
                                          (lambda a: db.einstellung_setzen(STANGENBILD_EINSTELLUNG, a)) if db else None,
                                          (lambda: db.einstellung("stangenbild_popup")) if db else None)
        self.stangen_seite.setzen(self.paare, s._abwicklung_funktion() if self.paare and
                                  hasattr(s, "_abwicklung_funktion") else None)
        self.bild, self.rolle = self.stangen_seite.bild, self.stangen_seite.rolle
        self.bild.setToolTip("Klick auf ein Teil: in der Teileliste zeigen · Doppelklick: zur Position")
        self.stangen_seite.klick.connect(self.teil_waehlen)
        self.stangen_seite.doppelklick.connect(lambda ref: self.zur_position(ref))
        teiler.addWidget(self.stangen_seite)

        mitte = QWidget()
        ml = QHBoxLayout(mitte)
        ml.setContentsMargins(0, 0, 0, 0)
        gm = QGroupBox("Schnittmuster")
        gml = QVBoxLayout(gm)
        self.muster = abmessung.muster(self.paare)
        self.muster_tab = _tabelle(MUSTER_SPALTEN, len(self.muster))
        for r, m in enumerate(self.muster):
            for c, (w, rechts) in enumerate(((m["anzahl"], True), (abmessung.nummern_text(m["nummern"]), False),
                                             (_z(m["stange"], 0), True), (m["teile"], False),
                                             (_z(m["rest"], 1), True), (_z(100 * m["ausnutzung"], 1), True),
                                             (_z(m["kosten"]), True))):
                self.muster_tab.setItem(r, c, _zelle(w, rechts, tipp=m["teile"] if c == 3 else None))
        self.muster_tab.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.muster_tab.setToolTip("Klick: Stange im Stangenbild zeigen")
        self.muster_tab.cellClicked.connect(self.muster_waehlen)
        gml.addWidget(self.muster_tab)
        ml.addWidget(gm, 3)
        self.bilanz_box = QGroupBox("Meter- und Gewichtsbilanz")
        bl = QVBoxLayout(self.bilanz_box)
        b = self.bilanz
        self.bilanz_tab = _tabelle(BILANZ_SPALTEN, len(b["posten"]) + 1)
        for r, x in enumerate(b["posten"] + [dict(name="Lieferlänge gesamt", m=b["gesamt_m"],
                                                    anteil=1 if b["gesamt_m"] else None, kg=b["gesamt_kg"])]):
            fett = r == len(b["posten"])
            for c, (w, rechts) in enumerate(((x["name"], False), (_z(x["m"], 2), True),
                                             (_z(100 * x["anteil"], 1) if x["anteil"] is not None else "", True),
                                             (_z(x["kg"], 1), True))):
                self.bilanz_tab.setItem(r, c, _zelle(w, rechts, fett=fett))
        self.bilanz_tab.setSelectionMode(QAbstractItemView.NoSelection)
        bl.addWidget(self.bilanz_tab)
        extra = []
        if b["gespart_m"]:
            extra.append(f"Gehrungen ineinander: {_z(b['gespart_m'], 2)} m gespart")
        if b["gemeinsam"]:
            extra.append(f"{b['gemeinsam']} gemeinsame Schnitte")
        hinweis = QLabel(" · ".join(extra) or "Rest = Verschnitt (keine Reststücke, wird nicht gelagert).")
        hinweis.setStyleSheet(f"color: {stil.TEXT_GRAU};")
        hinweis.setWordWrap(True)
        bl.addWidget(hinweis)
        ml.addWidget(self.bilanz_box, 2)
        teiler.addWidget(mitte)

        gt = QGroupBox("Teile dieser Abmessung")
        tl = QVBoxLayout(gt)
        self.teile_tab = _tabelle(TEILE_SPALTEN, len(self.teile))
        self._teile_fuellen()
        self.teile_tab.setToolTip("Klick: Teil im Stangenbild hervorheben · Doppelklick: zur Position · "
                                  "Rechtsklick auf die Kopfzeile: Spalten ein-/ausblenden")
        self.teile_tab.cellClicked.connect(lambda r, c: self.teil_waehlen(self.teile[r]["ref"], tabelle=False))
        self.teile_tab.cellDoubleClicked.connect(lambda r, c: self.zur_position(self.teile[r]["ref"]))
        kz = self.teile_tab.horizontalHeader()
        kz.setContextMenuPolicy(Qt.CustomContextMenu)
        kz.customContextMenuRequested.connect(self._spalten_menue)
        tl.addWidget(self.teile_tab)
        self.summe = QLabel(self.summen_text())
        self.summe.setStyleSheet(f"color: {stil.TEXT_GRAU};")
        tl.addWidget(self.summe)
        teiler.addWidget(gt)
        teiler.setSizes([330, 210, 280])
        lay.addWidget(teiler, 1)

        knoepfe = QHBoxLayout()
        self.k_optimieren = QPushButton("Neu optimieren")
        self.k_optimieren.setToolTip("Schnittplan neu rechnen; danach öffnet sich das Material-Fenster wieder")
        self.k_optimieren.clicked.connect(lambda: self.schliessen_mit("optimieren"))
        self.k_optimieren.setVisible(material.ohne_plan or material.veraltet)
        self.k_laengen = QPushButton("12-m-Lösung ansehen …")
        self.k_laengen.setToolTip("Vergleich der Lieferlängen nur für diese Abmessung")
        self.k_laengen.clicked.connect(lambda: self.schliessen_mit("laengen", self.laengen))
        self.k_laengen.setVisible(material.laengen_sinnvoll(g))
        self.k_anfrage = QPushButton("Materialanfrage …")
        self.k_anfrage.setToolTip("Materialanfrage an den Lieferanten nur für diese Abmessung")
        self.k_anfrage.clicked.connect(lambda: self.schliessen_mit("anfrage", g))
        self.k_anfrage.setEnabled(bool(self.paare) and not g["kunde"])
        self.k_drucken = QPushButton("Schnittplan drucken …")
        self.k_drucken.setToolTip("Werkstattpapiere (Schnittplan und Stangenbild) nur dieser Abmessung als PDF")
        self.k_drucken.clicked.connect(lambda: material.drucken(g))
        self.k_drucken.setEnabled(bool(self.paare))
        self.k_markieren = QPushButton("Positionen markieren")
        self.k_markieren.setToolTip("Fenster schließen und alle Positionen dieser Abmessung im Angebot markieren")
        self.k_markieren.clicked.connect(lambda: self.schliessen_mit("markieren", g))
        for k in (self.k_optimieren, self.k_laengen, self.k_anfrage, self.k_drucken, self.k_markieren):
            knoepfe.addWidget(k)
        knoepfe.addStretch(1)
        zu = QDialogButtonBox(QDialogButtonBox.Close)
        zu.button(QDialogButtonBox.Close).setText("Schließen")
        zu.rejected.connect(self.reject)
        knoepfe.addWidget(zu)
        lay.addLayout(knoepfe)
        self.fokus(fokus)

    def kennzahlen(self):
        g, b = self.g, self.bilanz
        teile = b["posten"][0]["m"] if b["posten"] else 0
        werte = [f"<b>{titel(g)}</b>",
                 f"Stangen <b>{_z(g['stangen'], 0)}</b> · Meter {_z(g['meter'], 1)} · Gewicht {_z(g['kg'], 1)} kg · "
                 f"Material {_z(g['kosten'])} € · Ausnutzung "
                 f"{_z(100 * g['ausnutzung'], 1) + ' %' if g['ausnutzung'] else '–'} · "
                 f"Verschnitt {_z(max(b['gesamt_m'] - teile, 0), 2)} m · Meterpreis "
                 + ("Kundenmaterial" if g["kunde"] else
                    f"{_z(g['wirksam'])} €/m" + (" (von Hand)" if g["manuell"] is not None else "")
                    if g["wirksam"] is not None else "fehlt")]
        return "<br>".join(werte)

    def _teile_fuellen(self):
        for r, t in enumerate(self.teile):
            fehlt = t["eingeplant"] < (t.get("rohrstuecke", t["stueck"]) or 0) and not self.material.ohne_plan
            for c, (_, _, schl, stellen) in enumerate(TEILE_SPALTEN):
                w = t[schl]
                if schl == "stangen":
                    w = abmessung.nummern_text(w)
                elif schl == "anteil":
                    w = None if w is None else 100 * w
                if stellen is not None and isinstance(w, (int, float)):
                    w = _z(w, stellen)
                farbe = stil.ROT if fehlt and schl == "eingeplant" else None
                self.teile_tab.setItem(r, c, _zelle(w, stellen is not None, farbe,
                                                    tipp=f"{t['eingeplant']} von {_z(t['stueck'], 0)} Teilen eingeplant"
                                                    if schl == "eingeplant" else None))

    def summen_text(self):
        n = sum(rechnen._n(t["stueck"]) for t in self.teile)
        ein = sum(t["eingeplant"] for t in self.teile)
        mat = sum(rechnen._n(t["material_teil"]) * rechnen._n(t["stueck"]) for t in self.teile)
        kg = sum(rechnen._n(t["kg"]) for t in self.teile)
        return (f"{len(self.teile)} Position(en) · {_z(n, 0)} Teile, davon {_z(ein, 0)} eingeplant · Teile "
                f"{_z(sum(t['meter'] for t in self.teile), 2)} m · {_z(kg, 1)} kg · Material {_z(mat)} €")

    def fokus(self, wo):
        """Bereich hervorheben, je nachdem, welche Spalte im Material-Fenster doppelt geklickt wurde."""
        if wo == "bilanz":
            self.bilanz_box.setStyleSheet(f"QGroupBox {{ border: 2px solid {stil.ORANGE}; }}")
            self.bilanz_tab.setFocus()
        elif wo == "teile":
            self.teile_tab.setFocus()
            if self.teile:
                self.teile_tab.selectRow(0)
        else:
            self.rolle.setFocus()

    def _spalten_menue(self, punkt):
        menue = QMenu(self)
        for c, s in enumerate(TEILE_SPALTEN):
            a = menue.addAction(s[0])
            a.setCheckable(True)
            a.setChecked(not self.teile_tab.isColumnHidden(c))
            a.toggled.connect(lambda an, c=c: self.teile_tab.setColumnHidden(c, not an))
        menue.exec(self.teile_tab.horizontalHeader().mapToGlobal(punkt))

    def teil_waehlen(self, ref, tabelle=True):
        """Teil hervorheben: im Stangenbild markieren und hinscrollen, in der Teileliste die Zeile wählen."""
        self.stangen_seite.markieren(ref)
        if tabelle:
            r = next((r for r, t in enumerate(self.teile) if t["ref"] == ref), None)
            if r is not None:
                self.teile_tab.selectRow(r)

    def muster_waehlen(self, r, _c=None):
        self.stangen_seite.muster_zeigen(r)

    def zur_position(self, ref):
        self.schliessen_mit("position", ref)

    def schliessen_mit(self, aktion, wert=None):
        """Fenster und Material-Fenster schließen, danach im Angebot aktion ausführen (MeterpreisDialog)."""
        if self.material.schliessen_mit(aktion, wert):
            self.accept()


class PreisFenster(QDialog):
    """Preis-Aufbau des Materials einer Abmessung (Doppelklick auf Material € oder berechnet €/m)."""

    def __init__(self, material, g):
        super().__init__(material)
        s = material.seite
        self.setWindowTitle("Preis-Aufbau " + titel(g))
        self.resize(820, 620)
        lay = QVBoxLayout(self)
        sw = rechnen.stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen) \
            if s.ergebnis and s.ergebnis.get("stangen") else []
        self.werte = abmessung.preis_aufbau(g, s.kopf, s.positionen, s.ergebnis, sw, s._rechnung()[0], s.k,
                                            s.tabellen, s.einst)
        self.ansicht = QTextBrowser()
        self.ansicht.setHtml(self.html(g, self.werte))
        lay.addWidget(self.ansicht, 1)
        zu = QDialogButtonBox(QDialogButtonBox.Close)
        zu.button(QDialogButtonBox.Close).setText("Schließen")
        zu.rejected.connect(self.reject)
        lay.addWidget(zu)

    @staticmethod
    def html(g, w):
        rot = stil.ROT
        teile = [f"<h3>{titel(g)}</h3>"]
        if w["kunde"]:
            teile.append("<p><b>Kundenmaterial:</b> kein Materialpreis; berechnet wird nur das Handling je m der "
                         f"beigestellten Stangen ({_z(w['handling_m'], 3)} €/m = {_z(w['handling'])} €).</p>")
        else:
            teile.append("<p><b>Meterpreis</b><br>"
                         + (f"berechnet {_z(w['berechnet'])} €/m" if w["berechnet"] is not None else
                            f"<span style='color:{rot}'>kein Preis berechnet</span>")
                         + (f" · <b>von Hand {_z(w['manuell'])} €/m</b> (gilt statt berechnet)"
                            if w["manuell"] is not None else "")
                         + (f"<br>{w['herkunft']}" if w["herkunft"] else "")
                         + (f"<br><span style='color:{rot}'>{w['fehlt']}</span>" if w["fehlt"] else "")
                         + "<br><i>Preise ändern: Einstellungen → Preise bzw. Lieferlängen (Passwort), oder hier "
                           "im Material-Fenster einen Meterpreis von Hand eintragen.</i></p>")
        if w["laengen"]:
            zeilen = "".join(
                f"<tr><td align='right'>{z['stangen']}</td><td align='right'>{_z(z['laenge'], 0)}</td>"
                f"<td align='right'>{_z(z['mehr'], 0)}</td><td align='right'>{_z(z['meter'], 2)}</td>"
                f"<td align='right'>{_z(z['preis_m'])}</td><td align='right'>{_z(z['kosten'])}</td></tr>"
                for z in w["laengen"])
            teile.append("<p><b>Einkauf laut Schnittplan</b></p><table border='1' cellspacing='0' cellpadding='3'>"
                         "<tr><th>Stangen</th><th>Länge [mm]</th><th>Händler-Mehrlänge [mm]</th>"
                         "<th>berechnete Meter</th><th>€ je m</th><th>Einkauf [€]</th></tr>" + zeilen +
                         f"<tr><td colspan='5'><b>Einkauf gesamt</b></td><td align='right'><b>{_z(w['einkauf'])}"
                         "</b></td></tr></table>")
            teile.append(f"<p>+ Zuschlag Material {_z(100 * w['zuschlag_pct'], 1)} % = {_z(w['zuschlag'])} € "
                         "(Einstellungen; im Preisaufbau als Zuschlag, nicht im Material €)</p>")
        else:
            teile.append("<p><i>Noch nicht optimiert: Einkauf und Verteilung folgen nach dem Optimieren.</i></p>")
        if w["positionen"]:
            zeilen = "".join(
                f"<tr><td>{_z(p['pos'], 0)}</td><td>{p['artikel'] or ''}</td><td align='right'>{_z(p['stueck'], 0)}</td>"
                f"<td align='right'>{_z(100 * p['anteil'], 1) if p['anteil'] is not None else ''}</td>"
                f"<td align='right'>{_z(p['material_position'])}</td><td align='right'>{_z(p['material_teil'], 3)}</td>"
                f"<td align='right'>{_z(p['zuschlag_teil'], 3)}</td></tr>" for p in w["positionen"])
            teile.append("<p><b>Verteilung auf die Positionen</b> (nach Teilelänge × Stück; der Abfall wird "
                         "gleichmäßig mitgetragen)</p><table border='1' cellspacing='0' cellpadding='3'>"
                         "<tr><th>Pos.</th><th>Artikel</th><th>Stück</th><th>Anteil [%]</th><th>Material Position [€]"
                         "</th><th>Material je Teil [€]</th><th>Zuschlag je Teil [€]</th></tr>" + zeilen + "</table>")
        return "".join(teile)


class ProfilFenster(QDialog):
    """Profil-Info (Doppelklick auf Querschnitt oder Abmessung): Querschnitt groß, Kennwerte, passende Maschinen."""

    def __init__(self, material, g):
        super().__init__(material)
        s = material.seite
        self.setWindowTitle("Profil " + g["profil"])
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        self.info = abmessung.profil_info(g["profil"], g["werkstoff"], s.k)
        oben = QHBoxLayout()
        bild = QLabel()
        bild.setPixmap(querschnitt_pixmap(s.k.profile.get(g["profil"]), 180))
        oben.addWidget(bild)
        form = QFormLayout()
        i = self.info or {}
        for titel_, w in (("Profil", g["profil"]), ("Form", i.get("form")), ("Maß a [mm]", _z(i.get("a"), 1)),
                          ("Maß b [mm]", _z(i.get("b"), 1)), ("Wand [mm]", _z(i.get("wand"), 2)),
                          ("Querschnitt [mm²]", _z(i.get("flaeche"), 1)),
                          (f"Metergewicht {g['werkstoff']} [kg/m]", _z(i.get("kgm"), 3)),
                          ("Hüllkreis-Ø [mm]", _z(i.get("huellkreis"), 1))):
            form.addRow(titel_ + ":", QLabel(str(w or "–")))
        oben.addLayout(form, 1)
        lay.addLayout(oben)
        if not self.info:
            lay.addWidget(QLabel("Das Profil steht nicht in den Stammdaten."))
        maschinen = (self.info or {}).get("maschinen") or []
        lay.addWidget(hilfe.Hinweis("Welche Maschinen das Profil laden können (max. Hüllkreis-Ø und max. "
                                    "Metergewicht der Maschine).", schluessel="profil_info"))
        self.tab = _tabelle((("Maschine", 120), ("passt", 60), ("Grund", 220), ("Stangenlänge [mm]", 120)),
                            len(maschinen))
        for r, m in enumerate(maschinen):
            laenge = (f"{_z(m['min_stange'], 0)} – " if m["min_stange"] else "bis ") + _z(m["max_stange"], 0) \
                if m["max_stange"] else ""
            for c, (w, rechts) in enumerate(((m["name"], False), ("ja" if m["passt"] else "nein", False),
                                             (m["grund"], False), (laenge, True))):
                self.tab.setItem(r, c, _zelle(w, rechts, None if m["passt"] else stil.ROT))
        lay.addWidget(self.tab, 1)
        zu = QDialogButtonBox(QDialogButtonBox.Close)
        zu.button(QDialogButtonBox.Close).setText("Schließen")
        zu.rejected.connect(self.reject)
        lay.addWidget(zu)
