"""Dialog 'Schneidweg berechnen …' einer Position ohne STEP-Datei: Enden (gerade, Gehrung oder Ausklinkung),
Innenkonturen (Bohrung, Langloch, Rechteck, Schlitz, Polygon aus Koordinaten, sonstige Kontur) und Gravur eingeben;
Skizze, Schnittlängen, Einstiche, Konturklassen, Gewinde-Vorschlag und die Schneidzeit mit den Schneiddaten der
Maschine stehen sofort daneben. Die Formeln stehen in schneidweg.py; OK schreibt die Werte in die Position
(Angebotsseite.schneidweg_berechnen)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QGridLayout,
                               QHBoxLayout, QHeaderView, QInputDialog, QLabel, QMenu, QMessageBox, QPushButton,
                               QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import hilfe, rechnen, schneidweg as sw, skizze as sk
from .skizze_widget import MODI, Skizze
from .stammdaten import zahl_aus_text

KONTUR_SPALTEN = ("Art", "Anzahl", "Maß 1 [mm]", "Maß 2 [mm]", "Maß 3 [mm]", "Lage ab Anfang [mm]", "Abstand [mm]",
                  "Seite", "Versatz quer [mm]", "Text")
LAGE_SPALTE, ABSTAND_SPALTE, SEITE_SPALTE, QUER_SPALTE, TEXT_SPALTE = 5, 6, 7, 8, 9
ERGEBNIS_SPALTEN = ("Schnitt", "Anzahl", "je Stück [mm]", "gesamt [mm]", "Einstiche", "Hüllmaß [mm]", "Klasse")
VORLAGEN = "rechner_vorlagen"          # Einstellung: {Name: {a, b, gravur, konturen, profilform}}
MASS_HILFE = ("Maße: Bohrung Ø · Senkung Bohrung Ø, Senk-Ø · Langloch Länge, Breite · Rechteck Breite, Höhe, "
              "Eckradius · Schlitz (offen, vom Rand) Tiefe, Breite · Ausklinkung am Ende Länge, Breite, Eckradius · "
              "Polygon Eckpunkte in Maß 1, z. B. 0,0; 40,0; 40,20; 0,20 · sonstige Kontur "
              "Schnittlänge, Hüllmaß (leer = groß). Lage ab Anfang = Mitte der (ersten) Kontur, leer = verteilt; Abstand = "
              "Muster längs (Anzahl Konturen im Abstand); Seite und Versatz quer zur Flächenmitte bzw. beim Rundrohr der "
              "Winkel (0° oben, 90° vorne). Lage, Seite und Versatz zählen nur für die Skizze, nicht für den Schneidweg.")


def _zahl(text):
    t = (text or "").strip()
    if not t:
        return None
    try:
        return zahl_aus_text(t)
    except ValueError:
        return None


class SchneidwegDialog(QDialog):
    """p: Position, profil: Stammdaten-Zeile des Profils, kopf/k/tabellen: Angebot und Stammdaten (Maschine,
    Konturgrenzen, Schneiddaten), db: Datenbank für Vorlagen, positionen: Positionen des Angebots zum Kopieren von
    Konturen. Nach OK: self.eingaben (dict) und self.ergebnis (schneidweg.rechnen)."""

    def __init__(self, parent, p, profil, kopf, k, tabellen, db=None, positionen=None):
        super().__init__(parent)
        self.p, self.profil, self.kopf, self.k, self.tabellen = p, profil, kopf, k, tabellen
        self.db, self.positionen = db, [x for x in (positionen or ()) if x.get("id") != p.get("id")]
        m = rechnen.maschine(kopf, k)
        vorgabe = rechnen.kontur_grenzen(m)[1]
        self.grenzen = rechnen.kontur_regel(m, rechnen.wand_schneiden(profil))
        self.gewinde = gewinde_liste(tabellen)
        self.ergebnis = None
        e = sw.lesen(p.get("technik"))
        self._ende_step = {}            # je Ende: Eingaben wie gemessen und gemessene Werte (STEP-Import)
        self.setWindowTitle(f"Schneidweg berechnen – Pos. {p.get('pos') or ''} {p.get('artikel') or ''}".strip())
        self.resize(1200, 900)
        self.qs = sk.Querschnitt(profil)
        haupt = QVBoxLayout(self)
        teiler = QSplitter(Qt.Vertical)
        haupt.addWidget(teiler, 1)
        oben = QWidget()
        lay = QVBoxLayout(oben)
        lay.setContentsMargins(0, 0, 0, 0)
        teiler.addWidget(oben)
        form = profil.get("form")
        info = QLabel(f"Profil {p.get('profil_id')} ({form}), Werkstoff {p.get('werkstoff_id') or '–'}, Maschine "
                      f"{kopf.get('maschine') or '–'}, Konturgrenzen klein bis {rechnen.zahl(self.grenzen[0])} mm, "
                      f"mittel bis {rechnen.zahl(self.grenzen[1])} mm" + (" (Vorgabe)" if vorgabe else "")
                      + (f", zusätzlich klein bis {rechnen.zahl(self.grenzen[2], 1)} × und mittel bis "
                         f"{rechnen.zahl(self.grenzen[3], 1)} × Wandstärke {rechnen.zahl(self.grenzen[4])} mm"
                         if len(self.grenzen) >= 5 else ""))
        info.setWordWrap(True)
        lay.addWidget(info)
        if any(sw._z(z.get("gemessen")) for z in e["konturen"] + [e["a"], e["b"]]):
            step_info = QLabel("Werte aus dem <b>STEP-Import</b> (grün): Es gelten die gemessenen Schnittlängen, "
                               "solange Art und Maße einer Zeile bzw. eines Endes unverändert bleiben.")
            step_info.setWordWrap(True)
            step_info.setStyleSheet("color: #1E6B35;")
            lay.addWidget(step_info)

        enden = QGridLayout()
        self.winkel, self.achse, self.sattel, self.richtung = {}, {}, {}, {}
        for r, (seite, titel) in enumerate((("a", "Anfangsschnitt"), ("b", "Endschnitt"))):
            w = QDoubleSpinBox()
            w.setRange(0, 79.9)
            w.setDecimals(1)
            w.setSuffix(" °")
            w.setSpecialValueText("gerade")
            w.setValue(sw._z(e[seite].get("winkel")))
            w.setToolTip("Gehrung: Abweichung vom rechtwinkligen Schnitt (0° = gerader Schnitt)")
            w.valueChanged.connect(self.rechnen)
            a = QComboBox()
            a.addItems(sw.ACHSEN)
            a.setCurrentText(e[seite].get("achse") or sw.ACHSEN[0])
            a.setEnabled(form != "Rundrohr")
            a.setToolTip("Richtung, in die die Gehrung läuft (Höhe = Maß a, Breite = Maß b des Profils)")
            a.currentTextChanged.connect(self.rechnen)
            sa = QDoubleSpinBox()
            sa.setRange(0, 2000)
            sa.setDecimals(1)
            sa.setSuffix(" mm")
            sa.setSpecialValueText("keine")
            sa.setValue(sw._z(e[seite].get("sattel")))
            sa.setEnabled(form == "Rundrohr")
            sa.setToolTip("Ausklinkung (Sattelschnitt): Ø des Rundrohrs, auf das dieses Ende rechtwinklig gesetzt wird")
            sa.valueChanged.connect(self.rechnen)
            ri = QComboBox()
            ri.addItems(list(sw.RICHTUNGEN))
            ri.setCurrentText(next((t for t, v in sw.RICHTUNGEN.items() if v == e[seite].get("richtung")),
                                   "nicht angegeben"))
            ri.setEnabled(form in sw.MIT_RICHTUNG)
            ri.setToolTip("Gehrung: Seite, an der das Teil an diesem Ende am längsten ist (Blick von Ende A, "
                          "Rechteckrohr mit der Breitseite oben). Damit legt die Optimierung Gehrungen ineinander.")
            ri.currentTextChanged.connect(self.rechnen)
            self.winkel[seite], self.achse[seite], self.sattel[seite], self.richtung[seite] = w, a, sa, ri
            if sw._z(e[seite].get("gemessen")):
                self._ende_step[seite] = (self._ende_werte(seite), {k_: e[seite][k_] for k_ in
                                                                    ("gemessen", "huelle_gemessen", "form")
                                                                    if e[seite].get(k_) is not None})
                w.setStyleSheet("background: #E8F5E9;")
            enden.addWidget(QLabel(titel + ": Gehrung"), r, 0)
            enden.addWidget(w, r, 1)
            enden.addWidget(a, r, 2)
            enden.addWidget(QLabel("Ausklinkung auf Rundrohr Ø"), r, 3)
            enden.addWidget(sa, r, 4)
            enden.addWidget(ri, r, 5)
        self.gravur = QDoubleSpinBox()
        self.gravur.setRange(0, 100000)
        self.gravur.setDecimals(1)
        self.gravur.setSuffix(" mm")
        self.gravur.setValue(sw._z(e.get("gravur")))
        self.gravur.valueChanged.connect(self.rechnen)
        enden.addWidget(QLabel("Gravur (Länge)"), 2, 0)
        enden.addWidget(self.gravur, 2, 1)
        enden.setColumnStretch(5, 1)
        lay.addLayout(enden)

        lay.addWidget(QLabel("<b>Innenkonturen</b>"))
        self.tabelle = QTableWidget(0, len(KONTUR_SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(KONTUR_SPALTEN)
        self.tabelle.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabelle.verticalHeader().setDefaultSectionSize(26)
        for i, b in enumerate((130, 60, 150, 80, 80, 130, 90, 120, 120)):
            self.tabelle.setColumnWidth(i, b)
        self.tabelle.horizontalHeader().setSectionResizeMode(TEXT_SPALTE, QHeaderView.Stretch)
        self.tabelle.itemChanged.connect(self.rechnen)
        self.tabelle.itemSelectionChanged.connect(self._auswahl_tabelle)
        lay.addWidget(self.tabelle, 1)
        lay.addWidget(hilfe.Hinweis(MASS_HILFE, schluessel="schneidweg"))
        leiste = QHBoxLayout()
        for art in sw.ARTEN:
            b = QPushButton(f"+ {art}")
            b.clicked.connect(lambda _=False, art=art: self.zeile_neu(dict(art=art, anzahl=1)))
            leiste.addWidget(b)
        weg = QPushButton("Markierte entfernen")
        weg.clicked.connect(self._entfernen)
        leiste.addStretch(1)
        kopieren = QPushButton("Aus Position kopieren …")
        kopieren.setToolTip("Konturen einer anderen Position dieses Angebots anhängen")
        kopieren.clicked.connect(self._kopieren_waehlen)
        kopieren.setEnabled(bool(self.positionen))
        leiste.addWidget(kopieren)
        self.vorlagen_knopf = QPushButton("Vorlagen")
        self.vorlagen_knopf.setToolTip("Enden, Konturen und Gravur als Vorlage speichern oder laden (für alle Angebote)")
        self.vorlagen_knopf.setMenu(QMenu(self.vorlagen_knopf))
        self.vorlagen_knopf.menu().aboutToShow.connect(self._vorlagen_menue)
        self.vorlagen_knopf.setEnabled(self.db is not None)
        leiste.addWidget(self.vorlagen_knopf)
        leiste.addWidget(weg)
        lay.addLayout(leiste)

        mitte = QWidget()
        ml = QVBoxLayout(mitte)
        ml.setContentsMargins(0, 0, 0, 0)
        kopfzeile = QHBoxLayout()
        kopfzeile.addWidget(QLabel("<b>Skizze</b> (maßstäblich)"))
        self.ansicht_wahl = QComboBox()
        self.ansicht_wahl.addItems(MODI)
        self.ansicht_wahl.currentTextChanged.connect(lambda m: self.skizze.modus_setzen(m))
        kopfzeile.addWidget(self.ansicht_wahl)
        einpassen = QPushButton("Einpassen")
        einpassen.clicked.connect(lambda: self.skizze.einpassen())
        kopfzeile.addWidget(einpassen)
        kopfzeile.addStretch(1)
        ml.addLayout(kopfzeile)
        self.skizze = Skizze(profil, p.get("laenge"))
        self.skizze.gewaehlt.connect(self._auswahl_skizze)
        self.skizze.verschoben.connect(self._verschoben)
        ml.addWidget(self.skizze, 1)
        teiler.addWidget(mitte)
        unten = QWidget()
        lay = QVBoxLayout(unten)
        lay.setContentsMargins(0, 0, 0, 0)
        teiler.addWidget(unten)
        lay.addWidget(QLabel("<b>Ergebnis je Teil</b>"))
        self.ergebnis_tabelle = QTableWidget(0, len(ERGEBNIS_SPALTEN))
        self.ergebnis_tabelle.setHorizontalHeaderLabels(ERGEBNIS_SPALTEN)
        self.ergebnis_tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.ergebnis_tabelle.verticalHeader().setVisible(False)
        self.ergebnis_tabelle.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        lay.addWidget(self.ergebnis_tabelle, 1)
        self.summe = QLabel()
        self.summe.setWordWrap(True)
        self.summe.setTextFormat(Qt.RichText)
        lay.addWidget(self.summe)
        teiler.setStretchFactor(0, 3)
        teiler.setStretchFactor(1, 4)
        teiler.setStretchFactor(2, 2)
        teiler.setSizes([330, 380, 190])
        lay = haupt
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("In Position übernehmen")
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.ok_knopf = knoepfe.button(QDialogButtonBox.Ok)
        for z in e["konturen"]:
            self.zeile_neu(z, rechnen_=False)
        self.rechnen()

    # ------------------------------------------------------------------ Eingaben
    def zeile_neu(self, z, rechnen_=True):
        self.tabelle.blockSignals(True)
        r = self.tabelle.rowCount()
        self.tabelle.insertRow(r)
        art = QComboBox()
        art.addItems(sw.ARTEN)
        art.setCurrentText(z.get("art") or sw.BOHRUNG)
        art.currentTextChanged.connect(lambda _=None, art=art: self._art_geaendert(art))
        self.tabelle.setCellWidget(r, 0, art)
        werte = [z.get("anzahl")] + [z.get(k_) for k_, _ in sw.MASSE.get(art.currentText(), ())]
        werte += [None] * (4 - len(werte)) + [z.get("x"), z.get("abstand")]
        for c, v in enumerate(werte, start=1):
            self.tabelle.setItem(r, c, QTableWidgetItem(rechnen.zahl(v, 3) if isinstance(v, (int, float)) else
                                                        v if isinstance(v, str) else ""))
        seite = QComboBox()
        seite.addItems(self.qs.seiten())
        if self.qs.r:
            seite.setEditable(True)         # Rundrohr: auch freier Winkel, z. B. 45°
            seite.setToolTip("Winkel am Umfang, Blick von Ende A: 0° oben, 90° vorne, 180° unten, 270° hinten")
            w = sk.winkel_aus_text(z.get("seite"))
            seite.setCurrentText(sk.winkel_text(w) if w is not None else self.qs.seiten()[0])
        else:
            seite.setToolTip("Fläche, auf der die Kontur liegt (siehe Ansicht von A in der Skizze)")
            seite.setCurrentText(z.get("seite") if z.get("seite") in self.qs.seiten() else self.qs.seiten()[0])
        seite.currentTextChanged.connect(self.rechnen)
        self.tabelle.setCellWidget(r, SEITE_SPALTE, seite)
        quer = QTableWidgetItem(rechnen.zahl(z["q"], 3) if isinstance(z.get("q"), (int, float)) else "")
        if self.qs.r:
            quer.setFlags(quer.flags() & ~Qt.ItemIsEditable)
            quer.setToolTip("Rundrohr: Lage am Umfang über den Winkel in der Spalte Seite")
        else:
            quer.setToolTip("Versatz quer zur Mitte der Fläche [mm] (+ in Richtung der nächsten Fläche)")
        self.tabelle.setItem(r, QUER_SPALTE, quer)
        self.tabelle.setItem(r, TEXT_SPALTE, QTableWidgetItem(z.get("text") or ""))
        self._kopf_hinweise(r)
        art.quer = bool(z.get("quer"))
        if sw._z(z.get("gemessen")):        # aus dem STEP-Import: gemessene Länge, solange die Maße bleiben
            art.step = (art.currentText(), self._mass_texte(r), {k_: z[k_] for k_ in ("gemessen", "huelle_gemessen")
                                                                 if z.get(k_) is not None})
            art.setToolTip(f"aus dem STEP-Import: gemessene Schnittlänge {rechnen.zahl(z['gemessen'], 1)} mm (gilt, "
                           "solange Art und Maße unverändert bleiben)")
            self.tabelle.item(r, 1).setBackground(QColor("#E8F5E9"))
        self.tabelle.blockSignals(False)
        if rechnen_:
            self.rechnen()

    def _mass_texte(self, r):
        return tuple(self.tabelle.item(r, 2 + i).text() for i in range(3))

    def _ende_werte(self, s):
        return (self.winkel[s].value(), self.achse[s].currentText(), self.sattel[s].value(),
                self.richtung[s].currentText())

    def _art_geaendert(self, combo):
        for r in range(self.tabelle.rowCount()):
            if self.tabelle.cellWidget(r, 0) is combo:
                self._kopf_hinweise(r)
        self.rechnen()

    def _kopf_hinweise(self, r):
        """Tooltip je Maßzelle: welches Maß die Art an dieser Stelle braucht."""
        masse = sw.MASSE.get(self.tabelle.cellWidget(r, 0).currentText(), ())
        for i in range(3):
            it = self.tabelle.item(r, 2 + i)
            if it is not None:
                it.setToolTip(masse[i][1] if i < len(masse) else "nicht benötigt")
                it.setFlags(it.flags() | Qt.ItemIsEditable if i < len(masse) else it.flags() & ~Qt.ItemIsEditable)
                if i >= len(masse):
                    it.setText("")

    def _entfernen(self):
        for r in sorted({i.row() for i in self.tabelle.selectedIndexes()}, reverse=True):
            self.tabelle.removeRow(r)
        self.rechnen()

    def eingaben(self):
        konturen = []
        for r in range(self.tabelle.rowCount()):
            art = self.tabelle.cellWidget(r, 0).currentText()
            z = dict(art=art, anzahl=_zahl(self.tabelle.item(r, 1).text()))
            for i, (k_, _) in enumerate(sw.MASSE.get(art, ())):
                text = self.tabelle.item(r, 2 + i).text()
                z[k_] = text.strip() if k_ == "punkte" else _zahl(text)
            x = _zahl(self.tabelle.item(r, LAGE_SPALTE).text())
            if x is not None:
                z["x"] = x
            ab = _zahl(self.tabelle.item(r, ABSTAND_SPALTE).text())
            if ab:
                z["abstand"] = ab
            seite = self.tabelle.cellWidget(r, SEITE_SPALTE).currentText()
            if self.qs.r:
                w = sk.winkel_aus_text(seite)
                if w:
                    z["seite"] = w
            elif seite != self.qs.seiten()[0]:
                z["seite"] = seite
            q = _zahl(self.tabelle.item(r, QUER_SPALTE).text())
            if q and not self.qs.r:
                z["q"] = q
            t = self.tabelle.item(r, TEXT_SPALTE).text().strip()
            if t:
                z["text"] = t
            combo = self.tabelle.cellWidget(r, 0)
            if getattr(combo, "quer", False):
                z["quer"] = True
            step = getattr(combo, "step", None)
            if step and step[0] == art and step[1] == self._mass_texte(r):
                z.update(step[2])
            konturen.append(z)
        enden = {s: dict(winkel=self.winkel[s].value(), achse=self.achse[s].currentText(),
                         sattel=self.sattel[s].value() or None,
                         richtung=sw.RICHTUNGEN.get(self.richtung[s].currentText())) for s in ("a", "b")}
        for s, (werte, gemessen) in self._ende_step.items():
            if self._ende_werte(s) == werte:
                enden[s].update(gemessen)
        return dict(enden, gravur=self.gravur.value() or None, konturen=konturen)

    # ------------------------------------------------------------------ Ergebnis
    def rechnen(self, *_):
        eingaben = self.eingaben()
        erg = sw.rechnen(eingaben, self.profil, self.grenzen, self.gewinde)
        self.ergebnis = erg
        t = self.ergebnis_tabelle
        t.setRowCount(len(erg["schritte"]))
        for r, s in enumerate(erg["schritte"]):
            werte = (s["text"] + (" (Schätzung)" if s["schaetzung"] else ""), str(s["anzahl"]),
                     rechnen.zahl(s["laenge_stueck"], 1), rechnen.zahl(s["laenge"], 1), str(s["einstiche"]),
                     "–" if s["huelle"] is None else rechnen.zahl(s["huelle"], 1), s["klasse"])
            for c, v in enumerate(werte):
                it = QTableWidgetItem(v)
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, it)
        f = erg["felder"]
        zeit = self.schneidzeit()
        teile = [f"<b>Schneidweg {rechnen.zahl(f['schneidweg'], 1)} mm</b>, {f['einstiche']} Einstiche "
                 f"(Enden {rechnen.zahl(f['a_schnitt'], 1)} + {rechnen.zahl(f['b_schnitt'], 1)} mm, Innenkonturen "
                 f"{rechnen.zahl(f['innen'], 1)} mm: klein {f['klein_n']}, mittel {f['mittel_n']}, groß {f['gross_n']})",
                 f"Schneidzeit je Teil {rechnen.zahl(zeit, 1)} s (Schneiddaten der Maschine)" if zeit is not None
                 else "<span style='color:#7A5A00'>Keine Schneiddaten für Maschine, Werkstoff und Wandstärke: "
                      "Schneidzeit von Hand eintragen.</span>"]
        if f.get("gewinde_vorschlag"):
            teile.append(f"<span style='color:#7A5A00'>Vorschlag: Bohrungen {f['bohrungen']} passen zu Kernlöchern "
                         f"für <b>{f['gewinde_vorschlag']}</b>. Erst nach Prüfung in <i>Gewinde geprüft</i> "
                         "eintragen (Zusatzarbeiten …).</span>")
        for h in erg.get("hinweise") or ():
            teile.append(f"<span style='color:#7A5A00'>{h}</span>")
        if erg["schaetzung"]:
            teile.append("<span style='color:#7A5A00'>Gehrung an diesem Profil: Schnittlänge geschätzt (gerade "
                         "Schnittlänge / cos Winkel).</span>")
        if not sw._z(self.p.get("zeit_manuell")) == 0:
            teile.append("<span style='color:#7A5A00'>Die Position hat eine Schneidzeit von Hand; sie gilt weiter, "
                         "bis sie in der Positionsliste gelöscht wird.</span>")
        if erg["fehler"]:
            teile.append("<span style='color:#B42318'>" + "<br>".join(erg["fehler"]) + "</span>")
        self.summe.setText("<br>".join(teile))
        if hasattr(self, "skizze"):
            self.skizze.zeigen(eingaben, erg)
            self._auswahl_tabelle()
        if hasattr(self, "ok_knopf"):
            self.ok_knopf.setEnabled(not erg["fehler"])

    # ------------------------------------------------------------------ Vorlagen und Kopieren
    def eingaben_setzen(self, e, anhaengen=False):
        """Enden, Gravur und Konturen setzen (anhaengen: nur Konturen dazu)."""
        e = sw.lesen(sw.speichern(ohne_messung(e))) if isinstance(e, dict) else sw.lesen(e)
        if not anhaengen:
            self._ende_step = {}
            for s in ("a", "b"):
                x = e.get(s) or {}
                self.winkel[s].setValue(sw._z(x.get("winkel")))
                if x.get("achse") in sw.ACHSEN:
                    self.achse[s].setCurrentText(x["achse"])
                self.sattel[s].setValue(sw._z(x.get("sattel")) if self.sattel[s].isEnabled() else 0)
                self.richtung[s].setCurrentText(next((t for t, v in sw.RICHTUNGEN.items()
                                                      if v == x.get("richtung")), "nicht angegeben"))
            self.gravur.setValue(sw._z(e.get("gravur")))
            self.tabelle.setRowCount(0)
        for z in e.get("konturen") or ():
            self.zeile_neu(z, rechnen_=False)
        self.rechnen()

    def vorlagen(self):
        v = self.db.einstellung(VORLAGEN) if self.db is not None else None
        return v if isinstance(v, dict) else {}

    def vorlage_speichern(self, name):
        name = (name or "").strip()
        if not name or self.db is None:
            return False
        v = self.vorlagen()
        v[name] = dict(ohne_messung(self.eingaben()), profilform=self.profil.get("form"))
        self.db.einstellung_setzen(VORLAGEN, v)
        return True

    def vorlage_laden(self, name):
        e = self.vorlagen().get(name)
        if not e:
            return False
        self.eingaben_setzen(e)
        return True

    def vorlage_loeschen(self, name):
        v = self.vorlagen()
        if v.pop(name, None) is None:
            return False
        self.db.einstellung_setzen(VORLAGEN, v)
        return True

    def _vorlagen_menue(self):
        m = self.vorlagen_knopf.menu()
        m.clear()
        m.addAction("Als Vorlage speichern …", self._vorlage_speichern_fragen)
        namen = sorted(self.vorlagen(), key=str.lower)
        laden, loeschen = m.addMenu("Vorlage laden"), m.addMenu("Vorlage löschen")
        for n in namen:
            form = self.vorlagen()[n].get("profilform")
            laden.addAction(n + (f"  ({form})" if form and form != self.profil.get("form") else ""),
                            lambda n=n: self.vorlage_laden(n))
            loeschen.addAction(n, lambda n=n: self._vorlage_loeschen_fragen(n))
        laden.setEnabled(bool(namen))
        loeschen.setEnabled(bool(namen))

    def _vorlage_speichern_fragen(self):
        name, ok = QInputDialog.getText(self, "Vorlage speichern", "Name der Vorlage (gleicher Name ersetzt sie):")
        if ok and name.strip():
            self.vorlage_speichern(name)

    def _vorlage_loeschen_fragen(self, name):
        if QMessageBox.question(self, "Vorlage löschen", f"Vorlage „{name}“ löschen?") == QMessageBox.Yes:
            self.vorlage_loeschen(name)

    def kopierbare(self):
        """[(Text, Position)] der anderen Positionen mit Konturen im Rechner."""
        out = []
        for x in self.positionen:
            k_ = sw.lesen(x.get("technik")).get("konturen")
            if k_:
                out.append((f"Pos. {x.get('pos') or ''} {x.get('artikel') or ''} – {x.get('profil_id') or ''}, "
                            f"{len(k_)} Zeile(n)".replace("  ", " "), x))
        return out

    def konturen_kopieren(self, position):
        """Konturen einer anderen Position anhängen (Seiten, die das Profil nicht hat, fallen auf die erste)."""
        k_ = sw.lesen(position.get("technik")).get("konturen")
        if not k_:
            return 0
        self.eingaben_setzen(dict(konturen=k_), anhaengen=True)
        return len(k_)

    def _kopieren_waehlen(self):
        liste = self.kopierbare()
        if not liste:
            QMessageBox.information(self, "Konturen kopieren", "Keine andere Position dieses Angebots hat Konturen im "
                                    "Schneidweg-Rechner.")
            return
        text, ok = QInputDialog.getItem(self, "Konturen kopieren", "Konturen anhängen von:", [t for t, _ in liste], 0,
                                        False)
        if ok:
            self.konturen_kopieren(dict(liste)[text])

    # ------------------------------------------------------------------ Skizze <-> Tabelle
    def _auswahl_tabelle(self):
        zeilen = sorted({i.row() for i in self.tabelle.selectedIndexes()})
        self.skizze.markieren(zeilen[0] if zeilen else None)

    def _auswahl_skizze(self, zeile):
        if 0 <= zeile < self.tabelle.rowCount():
            self.tabelle.selectRow(zeile)

    def _verschoben(self, zeile, neu):
        """Kontur in der Skizze gezogen: Lage, Abstand, Seite und Versatz in die Tabelle schreiben."""
        if not 0 <= zeile < self.tabelle.rowCount():
            return
        self.tabelle.blockSignals(True)
        for name, spalte in (("x", LAGE_SPALTE), ("abstand", ABSTAND_SPALTE), ("q", QUER_SPALTE)):
            if name in neu and not (name == "q" and self.qs.r):
                v = neu[name]
                self.tabelle.item(zeile, spalte).setText(rechnen.zahl(v, 3) if v is not None else "")
        if "seite" in neu:
            cb = self.tabelle.cellWidget(zeile, SEITE_SPALTE)
            cb.blockSignals(True)
            if self.qs.r:
                cb.setCurrentText(sk.winkel_text(neu["seite"] or 0.0))
            else:
                cb.setCurrentText(neu["seite"] or self.qs.seiten()[0])
            cb.blockSignals(False)
        self.tabelle.blockSignals(False)
        self.tabelle.selectRow(zeile)
        self.rechnen()

    def schneidzeit(self):
        """Schneidzeit je Teil [s] mit den neuen Werten oder None ohne Schneiddaten."""
        p = dict(self.p, **self.ergebnis["felder"])
        return rechnen.schneidzeit(p, self.kopf, rechnen.wand_schneiden(self.profil), self.tabellen, self.k)[2]

    def _ok(self):
        self.rechnen()
        if not self.ergebnis["fehler"]:
            self.accept()


def ohne_messung(e):
    """Eingaben ohne gemessene Werte des STEP-Imports (Vorlagen und kopierte Konturen rechnen mit den Formeln)."""
    weg = ("gemessen", "huelle_gemessen", "form")
    out = {k_: v for k_, v in e.items() if k_ not in ("a", "b", "konturen", "quelle")}
    for s in ("a", "b"):
        if isinstance(e.get(s), dict):
            out[s] = {k_: v for k_, v in e[s].items() if k_ not in weg}
    out["konturen"] = [{k_: v for k_, v in z.items() if k_ not in weg} for z in e.get("konturen") or ()]
    return out


def gewinde_liste(tabellen):
    """[(Gewinde, Kernloch-Ø)] aus den Stammdaten Gewinde (leer: übliche Kernlöcher, wie der STEP-Import)."""
    return [(g["gewinde"], g["kernloch"]) for g in (tabellen.get("gewinde") or ())
            if g.get("gewinde") and isinstance(g.get("kernloch"), (int, float))] or None
