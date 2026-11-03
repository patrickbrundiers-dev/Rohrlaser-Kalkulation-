"""Eigenschaften-Feld des Teile-Editors (Plan 3D-Editor B1/B2/B5): rechts nur die Felder des gewählten Merkmals –
Kontur mit Maßbild, Ende als Karte, Teil, Schweißnaht, Biegung – statt der breiten Tabelle.

Die Werte stehen weiter in den Eingaben der Fenster (Tabellenzeilen, Felder der Enden); das Feld liest sie von dort
und schreibt jede Änderung dorthin zurück. Damit rechnen Schneidweg-Rechner und Blech-Editor wie bisher, Rückgängig
und die Herkunft (STEP / manuell) bleiben gleich. Maßfelder nehmen Rechnungen an (rechenfeld.py), z. B. „L/2“;
das Musterfeld auch „3x25“ = 3 Stück im Abstand 25.

Felder, die bei der Wahl nichts bedeuten (Winkel über Breite ohne Schrägschnitt zweiachsig, Ausklinkung ohne
Rundrohr …), erscheinen nicht.
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

from . import blech, massbild, optimierung as opt, rechenfeld as rf, schneidweg as sw, skizze as sk, stil

BEZUG = {"mitte_a": "Mitte ab Ende A", "kante_a": "Kante ab Ende A", "mitte_b": "Mitte ab Ende B",
         "kante_b": "Kante ab Ende B"}
SCHNITT = {"": "senkrecht zur Oberfläche", "parallel": "parallel zur Konturachse (3D)"}
ROHR_SPALTEN = dict(anzahl=1, lage=5, abstand=6, seite=7, quer=8, text=12, gewinde=13)
BLECH_SPALTEN = dict(anzahl=1, x=5, y=6)


def _zelle_text(tabelle, r, c):
    it = tabelle.item(r, c)
    return it.text() if it is not None else ""


def _zelle_zahl(tabelle, r, c):
    try:
        return rf.auswerten(_zelle_text(tabelle, r, c))
    except ValueError:
        return None


class Eigenschaften(QWidget):
    """art 'rohr' oder 'blech'; dialog = SchneidwegDialog bzw. BlechDialog. zeigen(merkmal_id) baut die Felder,
    auffrischen() übernimmt geänderte Werte (nicht, solange im Feld getippt wird)."""
    duplizieren = Signal(int)
    entfernen = Signal(int)

    def __init__(self, dialog, art, parent=None):
        super().__init__(parent)
        self.d, self.art = dialog, art
        self.mid = None
        self.felder = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.titel = QLabel("<b>Eigenschaften</b>")
        lay.addWidget(self.titel)
        self.rollen = QScrollArea()
        self.rollen.setWidgetResizable(True)
        self.rollen.setFrameShape(QScrollArea.NoFrame)
        lay.addWidget(self.rollen, 1)
        self._inhalt = None
        self.zeigen(None)

    # -------------------------------------------------------------- Größen für Rechenfelder
    def groessen(self):
        d = self.d
        if self.art == "rohr":
            qs = d.qs
            laenge = d.k_laenge.value() if getattr(d, "neu", False) and hasattr(d, "k_laenge") else d.p.get("laenge")
            return dict(L=sw._z(laenge), B=qs.B, H=qs.H, D=sw._z(d.profil.get("a")), S=sw._z(d.profil.get("wand")))
        zs = (d.ergebnis or {}).get("zuschnitt") or {}
        return dict(L=sw._z(zs.get("laenge")), B=sw._z(zs.get("breite")), S=d.dicke.value())

    # -------------------------------------------------------------- Aufbau
    def zeigen(self, mid):
        self.mid = mid
        self.felder = {}
        inhalt = QWidget()
        self._form = QFormLayout(inhalt)
        self._form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        art, _, nr = (mid or "").partition(":")
        titel = "Eigenschaften"
        try:
            if art == "kontur":
                titel = self._kontur(int(nr))
            elif art == "ende" and self.art == "rohr":
                titel = self._ende(nr)
            elif art == "biegung" and self.art == "blech":
                titel = self._biegung(int(nr))
            elif art == "teil":
                titel = self._teil()
            elif art == "naht" and self.art == "rohr":
                titel = self._naht()
            elif art == "gravur" and self.art == "rohr":
                titel = "Gravur je Teil"
                self._spin("Länge je Teil", self.d.gravur, "mm")
            else:
                hinweis = QLabel("<span style='color:%s'>Merkmal im Baum, in der Skizze oder im 3D wählen; hier "
                                 "stehen dann nur seine Felder.</span>" % stil.umsetzen(stil.TEXT_GRAU))
                hinweis.setWordWrap(True)
                self._form.addRow(hinweis)
        except (IndexError, AttributeError, ValueError):
            self._form.addRow(QLabel("–"))
        self.titel.setText(f"<b>{titel}</b>")
        alt = self.rollen.takeWidget()
        if alt is not None:
            alt.deleteLater()
        self.rollen.setWidget(inhalt)
        self._inhalt = inhalt

    def auffrischen(self):
        """Nach einer Rechnung: Felder neu aufbauen, außer der Benutzer tippt gerade hier."""
        fokus = QApplication.focusWidget()
        if fokus is not None and self.isAncestorOf(fokus):
            return
        self.zeigen(self.mid)

    # -------------------------------------------------------------- Bausteine
    def _rechen(self, titel, wert, schreiben, einheit="mm", tipp="", schluessel=None):
        f = rf.RechenFeld(wert, self.groessen(), einheit)
        f.setToolTip(tipp or "Zahl oder Rechnung, z. B. L/2 (L = Teilelänge), 1960 − 150")
        f.wert_geaendert.connect(schreiben)
        zeile = QHBoxLayout()
        zeile.addWidget(f, 1)
        if einheit:
            zeile.addWidget(QLabel(einheit))
        self._form.addRow(titel, zeile)
        self.felder[schluessel or titel] = f
        return f

    def _zelle(self, titel, tabelle, r, c, einheit="mm", tipp="", text=False, muster_zu=None):
        if text:
            f = QLineEdit(_zelle_text(tabelle, r, c))
            f.editingFinished.connect(lambda: self._setzen(tabelle, r, c, f.text().strip()))
            f.setToolTip(tipp)
            self._form.addRow(titel, f)
            self.felder[titel] = f
            return f

        def schreiben(v):
            self._setzen(tabelle, r, c, rf.zahl_text(v, 3) if v is not None else "")
        f = self._rechen(titel, _zelle_zahl(tabelle, r, c), schreiben, einheit, tipp)
        if muster_zu is not None:           # Abstand Muster: „3x25“ setzt Anzahl und Abstand
            alt = f.uebernehmen

            def muster():
                m = rf.muster(f.text())
                if m:
                    self._setzen(tabelle, r, muster_zu, str(m[0]))
                    f.setText(rf.zahl_text(m[1]))
                alt()
            f.editingFinished.disconnect()
            f.editingFinished.connect(muster)
            f.setToolTip("Abstand Mitte zu Mitte; „3x25“ = 3 Stück im Abstand 25")
        return f

    @staticmethod
    def _setzen(tabelle, r, c, text):
        it = tabelle.item(r, c)
        if it is not None and it.text() != text:
            it.setText(text)            # itemChanged: das Fenster rechnet neu

    def _combo(self, titel, quelle, tipp=""):
        f = QComboBox()
        f.addItems([quelle.itemText(i) for i in range(quelle.count())])
        f.setEditable(quelle.isEditable())
        f.setCurrentText(quelle.currentText())
        f.setEnabled(quelle.isEnabled())
        f.setToolTip(tipp or quelle.toolTip())
        if f.isEditable():
            f.lineEdit().editingFinished.connect(lambda: quelle.setCurrentText(f.currentText()))
        f.activated.connect(lambda _=None: quelle.setCurrentText(f.currentText()))
        self._form.addRow(titel, f)
        self.felder[titel] = f
        return f

    def _spin(self, titel, quelle, einheit="", tipp=""):
        return self._rechen(titel, quelle.value(), lambda v: quelle.setValue(v or 0), einheit,
                            tipp or quelle.toolTip())

    def _haken(self, titel, quelle, tipp=""):
        f = QCheckBox(titel)
        f.setChecked(quelle.isChecked())
        f.setEnabled(quelle.isEnabled())
        f.setToolTip(tipp or quelle.toolTip())
        f.toggled.connect(quelle.setChecked)
        self._form.addRow("", f)
        self.felder[titel] = f
        return f

    def _bild(self, art):
        b = QLabel()
        b.setPixmap(massbild.bild(art))
        b.setAlignment(Qt.AlignCenter)
        b.setToolTip("Maßbild: welches Maß welches ist (Längsrichtung des Teils waagerecht)")
        self._form.addRow(b)

    def _knoepfe(self, r):
        zeile = QHBoxLayout()
        for text, signal, tipp in (("Duplizieren", self.duplizieren, "Zeile kopieren (Strg+D)"),
                                   ("Entfernen", self.entfernen, "Zeile entfernen (Entf)")):
            b = QPushButton(text)
            b.setToolTip(tipp)
            b.clicked.connect(lambda _=False, s=signal: s.emit(r))
            zeile.addWidget(b)
        zeile.addStretch(1)
        self._form.addRow(zeile)

    # -------------------------------------------------------------- Merkmale
    def _kontur(self, r):
        d = self.d
        t = d.tabelle
        if not 0 <= r < t.rowCount():
            raise IndexError(r)
        combo = t.cellWidget(r, 0)
        art = combo.currentText()
        self._combo("Art", combo)
        self._bild(art)
        for i, (k, titel) in enumerate(sw.MASSE.get(art, ())):
            if k == "punkte":
                self._zelle(titel, t, r, 2 + i, text=True, tipp="Eckpunkte x,y in mm, getrennt mit Semikolon")
            elif k == "beta":
                self._zelle("Knickwinkel β", t, r, 2 + i, einheit="°")
            elif k in ("winkel", "reihen"):
                self._zelle(titel.split(" (")[0].replace(" [°]", ""), t, r, 2 + i,
                            einheit="°" if k == "winkel" else "Stück", tipp=titel)
            else:
                self._zelle(titel.split(" (")[0], t, r, 2 + i)
        if self.art == "rohr":
            self._zelle("Anzahl", t, r, ROHR_SPALTEN["anzahl"], einheit="Stück")
            self._lage(r, combo)
            self._zelle("Abstand Muster", t, r, ROHR_SPALTEN["abstand"], muster_zu=ROHR_SPALTEN["anzahl"])
            self._combo("Seite", t.cellWidget(r, ROHR_SPALTEN["seite"]))
            if not d.qs.r:
                self._zelle("Versatz quer", t, r, ROHR_SPALTEN["quer"],
                            tipp="Versatz zur Flächenmitte (+ zur nächsten Fläche hin)")
            self._rohr_eigenschaften(combo, art)
            if art in sw.MIT_GEWINDE:
                self._combo("Gewinde", t.cellWidget(r, ROHR_SPALTEN["gewinde"]))
            self._zelle("Bemerkung", t, r, ROHR_SPALTEN["text"], text=True,
                        tipp="erscheint in Skizze und Zeichnung")
        else:
            self._zelle("Anzahl", t, r, BLECH_SPALTEN["anzahl"], einheit="Stück")
            self._zelle("Mitte x", t, r, BLECH_SPALTEN["x"], tipp="in der Abwicklung ab links")
            self._zelle("Mitte y", t, r, BLECH_SPALTEN["y"], tipp="in der Abwicklung ab unten")
            if art in blech.DREH_ARTEN:
                eig = getattr(combo, "eig", None) or {}
                self._rechen("Drehwinkel", sw._z(eig.get("drehung")) or 0.0,
                             lambda v: self._eig_setzen(combo, "drehung", round(v, 3) % 360 if v else None), "°",
                             "Drehung der Kontur um ihre Mitte, + = gegen den Uhrzeiger; 0 = Länge waagerecht in der "
                             "Abwicklung", schluessel="Drehwinkel")
        self._knoepfe(r)
        return f"{art} · Zeile {r + 1} von {t.rowCount()}"

    # -------------------------------------------------------------- Eigenschaften je Kontur (3E-4, wie AlmaCAM)
    def _eig_setzen(self, combo, schl, wert):
        eig = dict(getattr(combo, "eig", None) or {})
        if wert in (None, "", 0):
            eig.pop(schl, None)
        else:
            eig[schl] = wert
        if eig != (getattr(combo, "eig", None) or {}):
            combo.eig = eig
            self.d.rechnen()
            self.zeigen(self.mid)       # Lage im neuen Bezug, Felder je Wahl (Anzahl am Umfang)

    def _lage(self, r, combo):
        """Lage mit Bezugspunkt: Mitte oder Kante der Kontur, ab Ende A oder B. In der Tabelle steht immer die Mitte
        ab Ende A; mit Bezug ab Ende B bleibt der Abstand zu Ende B, wenn sich die Teilelänge ändert."""
        t = self.d.tabelle
        eig = getattr(combo, "eig", None) or {}
        bezug = eig.get("bezug") or "mitte_a"
        b = QComboBox()
        for k, text in BEZUG.items():
            b.addItem(text, k)
        b.setCurrentIndex(max(0, b.findData(bezug)))
        b.setToolTip("Bezugspunkt der Lage: Mitte oder Kante der Kontur (bei Ende A die Kante zu A hin, bei Ende B "
                     "die zu B hin), gemessen ab Ende A oder Ende B")
        b.activated.connect(lambda _=None: self._eig_setzen(combo, "bezug", "" if b.currentData() == "mitte_a"
                                                            else b.currentData()))
        self._form.addRow("Bezug der Lage", b)
        self.felder["Bezug der Lage"] = b
        L = self.groessen()["L"]
        try:
            halb = sk.laenge_x(self.d.eingaben()["konturen"][r]) / 2
        except (IndexError, KeyError, TypeError, ValueError):
            halb = 0.0
        mitte = _zelle_zahl(t, r, ROHR_SPALTEN["lage"])

        def anzeige(x):
            if x is None:
                return None
            return {"kante_a": x - halb, "mitte_b": L - x, "kante_b": L - x - halb}.get(bezug, x)

        def schreiben(v):
            x = None if v is None else {"kante_a": v + halb, "mitte_b": L - v, "kante_b": L - v - halb}.get(bezug, v)
            self._setzen(t, r, ROHR_SPALTEN["lage"], rf.zahl_text(round(x, 3), 3) if x is not None else "")
        titel = BEZUG[bezug].replace("Mitte", "Lage Mitte").replace("Kante", "Lage Kante")
        f = self._rechen(titel, anzeige(mitte), schreiben, "mm",
                         "Lage der (ersten) Kontur; leer = gleichmäßig verteilt. Rechnung möglich, z. B. L/2",
                         schluessel="Lage")
        return f

    def _rohr_eigenschaften(self, combo, art):
        d = self.d
        eig = getattr(combo, "eig", None) or {}
        self._extra_3e7(combo, art)
        if art not in sk.DREH_OHNE and art not in (sw.SCHLITZ, sw.AUSKLINKUNG, sw.V_AUSSCHNITT, sw.DURCHBRUCH):
            self._rechen("Drehwinkel", sw._z(eig.get("drehung")) or 0.0,
                         lambda v: self._eig_setzen(combo, "drehung", round(v, 3) % 360 if v else None), "°",
                         "Drehung der Kontur auf der Fläche um ihre Mitte, + = gegen den Uhrzeiger (von außen gesehen); "
                         "0 = Länge längs zum Teil", schluessel="Drehwinkel")
        if (d.qs.r or d.qs.radius) and art not in sw.GRAVUREN and art != sw.FLOWDRILL:
            f = QComboBox()
            for k, text in SCHNITT.items():
                f.addItem(text, k)
            f.setCurrentIndex(max(0, f.findData(eig.get("schnitt") or "")))
            f.setToolTip("Senkrecht (2D, Standard): Strahl je Punkt senkrecht zur Oberfläche, die Innenkante der "
                         "Kontur ist maßhaltig, außen wird sie auf Rundrohr und Eckradius breiter. Parallel (3D): "
                         "ebene Schnittfläche parallel zur Achse der Kontur wie gebohrt – braucht die "
                         "3D-Schnittbearbeitung (Häkchen am Teil)")
            f.activated.connect(lambda _=None: self._eig_setzen(combo, "schnitt", f.currentData()))
            self._form.addRow("Schnittrichtung", f)
            self.felder["Schnittrichtung"] = f
        arten = sk.waende_arten(d.qs)
        if len(arten) > 1:
            w = QComboBox()
            for k in arten:
                w.addItem(sk.WAENDE[k], k)
            w.setCurrentIndex(max(0, w.findData(eig.get("wand") or "")))
            w.setToolTip("Beide Wände: dieselbe Kontur durchgehend auf der gegenüberliegenden Wand (zählt doppelt im "
                         "Schneidweg). Alle vier Seiten bzw. am Umfang verteilt: Kopien rundherum")
            w.activated.connect(lambda _=None: self._eig_setzen(combo, "wand", w.currentData()))
            self._form.addRow("Wände", w)
            self.felder["Wände"] = w
            if eig.get("wand") == "umfang":
                self._rechen("Anzahl am Umfang", sw._z(eig.get("umfang_n")) or 2,
                             lambda v: self._eig_setzen(combo, "umfang_n", max(2, int(round(v or 2)))), "Stück",
                             "so viele Konturen gleichmäßig am Umfang (z. B. 4 = alle 90°)", schluessel="Anzahl am Umfang")

    def _extra_3e7(self, combo, art):
        """Eigenschaften aus Schritt 3E-7: Lochfeld (Langloch, versetzt), Durchbruch (Versatz am Rundrohr, Eckradius
        des Gegenrohrs), Fase der Ecken (Rechteck, Ausklinkung)."""
        eig = getattr(combo, "eig", None) or {}
        if art == sw.LOCHFELD:
            self._rechen("Langloch-Länge", sw._z(eig.get("lang")) or None,
                         lambda v: self._eig_setzen(combo, "lang", round(v, 3) if v else None), "mm",
                         "leer = Bohrungen; sonst Langlöcher dieser Länge (Breite = Ø)", schluessel="Langloch-Länge")
            f = QCheckBox("jede 2. Reihe versetzt")
            f.setChecked(bool(eig.get("versetzt")))
            f.setToolTip("Reihen quer abwechselnd um die halbe Teilung längs verschoben")
            f.toggled.connect(lambda an: self._eig_setzen(combo, "versetzt", True if an else None))
            self._form.addRow("", f)
            self.felder["versetzt"] = f
        elif art == sw.DURCHBRUCH:
            if self.d.qs.r:
                self._rechen("Versatz", sw._z(eig.get("versatz")) or 0.0,
                             lambda v: self._eig_setzen(combo, "versatz", round(v, 3) if v else None), "mm",
                             "Achse des Gegenrohrs quer zur Rohrachse verschoben", schluessel="Versatz")
            self._rechen("Eckradius Gegenrohr", sw._z(eig.get("r_gegen")) or 0.0,
                         lambda v: self._eig_setzen(combo, "r_gegen", round(v, 3) if v else None), "mm",
                         "nur rechteckiges Gegenrohr (Tiefe eingegeben)", schluessel="Eckradius Gegenrohr")
        elif art in sw.MIT_FASE:
            self._rechen("Fase je Ecke", sw._z(eig.get("fase")) or 0.0,
                         lambda v: self._eig_setzen(combo, "fase", round(v, 3) if v else None), "mm",
                         "Ecken gefast statt gerundet (0 = Eckradius gilt); Rechtsklick auf die Kontur: Ecken",
                         schluessel="Fase je Ecke")

    def _ende(self, s):
        d = self.d
        self._spin("Gehrungswinkel", d.winkel[s], "°", "Abweichung vom rechtwinkligen Schnitt (0 = gerade)")
        self._combo("gekippt über", d.achse[s])
        if d.achse[s].currentText() == sw.ACHSE_ZWEI:
            self._spin("Winkel über Breite", d.winkel_b[s], "°")
        if d.richtung[s].isEnabled():
            self._combo("längste Seite", d.richtung[s])
        if d.sattel[s].isEnabled() and not d.gegen.get(s):
            self._spin("Ausklinkung auf Rundrohr Ø", d.sattel[s], "mm")
        if d.gegen_knopf[s].isEnabled():
            b = QPushButton(d.gegen_knopf[s].text())
            b.setToolTip(d.gegen_knopf[s].toolTip())
            b.clicked.connect(lambda: d.gegenrohr(s))
            self._form.addRow("Gegenrohr", b)
            self.felder["Gegenrohr"] = b
            if d.gegen.get(s):
                self._gegen_felder(s)
        if d.d3.isChecked():
            self._haken("Gehrung in 3D", d.ende_3d[s])
        return "Anfangsschnitt (Ende A)" if s == "a" else "Endschnitt (Ende B)"

    def _gegen_felder(self, s):
        """Gegenrohr direkt im 3D-Editor ändern (Rohranschluss aus der STEP oder von Hand, Patrick 30.10.2026): Ø,
        Winkel, Versatz und beim Rundrohr die Drehung um die Rohrachse; jede Änderung rechnet die Schnittkurve neu."""
        d = self.d
        g = d.gegen.get(s) or {}

        def setzen(schl, v):
            neu = dict(d.gegen.get(s) or {})
            if schl == "d" and not v:
                return
            if v:
                neu[schl] = round(v, 3)
            else:
                neu.pop(schl, None)
            d.gegenrohr(s, neu)
        felder = [("d", "Ø Gegenrohr", "mm", "Ø (bzw. Breite quer) des Gegenrohrs"),
                  ("winkel", "Winkel zum Gegenrohr", "°", "Abweichung der Achsen von rechtwinklig (0 = rechtwinklig)"),
                  ("versatz", "Versatz", "mm", "Achse des Gegenrohrs quer zur Rohrachse verschoben (0 = mittig)")]
        if d.qs.r:
            felder.append(("drehung", "Drehung um die Rohrachse", "°",
                           "Lage des Gegenrohrs am Umfang (0 = Achse waagerecht bzw. senkrecht wie gewählt)"))
        for schl, titel, einheit, tipp in felder:
            self._rechen(titel, sw._z(g.get(schl)) or (None if schl == "d" else 0.0),
                         lambda v, k_=schl: setzen(k_, v), einheit, tipp, schluessel=f"gegen_{schl}")

    def _teil(self):
        d = self.d
        if self.art == "rohr":
            self._profil()
            self._spin("Gravur je Teil", d.gravur, "mm")
            if d.profil.get("form") in opt.RADIUS_FORMEN:
                self._radius()
            self._haken("3D-Schnittbearbeitung", d.d3)
            info = QLabel("<span style='color:%s'>%s</span>" % (stil.umsetzen(stil.TEXT_GRAU), d.info.text()))
            info.setWordWrap(True)
            self._form.addRow(info)
            return "Profil und Teil"
        self._combo("Werkstoff", d.werkstoff)
        self._spin("Dicke", d.dicke, "mm")
        self._combo("Art", d.art)
        if d.art.currentText() == "Kantteil":
            self._spin("Kantlänge", d.kantlaenge, "mm")
        elif d.form.currentText() != "Polygon":
            self._spin("Länge", d.laenge, "mm")
            self._spin("Breite", d.breite, "mm")
            self._spin("Eckradius", d.eckradius, "mm")
        return "Teil"

    def _profil(self):
        """Profil-Einstellungen (Klick aufs Profil im 3D, Patrick 24.10.2026): neue Position Profilform, Profil,
        Werkstoff, Teilelänge und Stückzahl änderbar; bestehende Position zeigt die Profilwerte (Profil und
        Werkstoff ändert man in der Positionstabelle des Angebots)."""
        d = self.d
        neu = getattr(d, "neu", False) and hasattr(d, "k_profil")
        if neu:
            self._combo("Profilform", d.k_form)
            self._combo("Profil", d.k_profil)
            self._combo("Werkstoff", d.k_werkstoff)
            self._spin("Teilelänge", d.k_laenge, "mm")
            self._spin("Stückzahl", d.k_stueck, "Stück")
        pr, p = d.profil or {}, d.p or {}
        werte = [] if neu else [("Profil", p.get("profil_id")), ("Profilform", pr.get("form"))]
        masse = " × ".join(rf.zahl_text(pr[k]) for k in ("a", "b") if sw._z(pr.get(k)))
        werte += [("Abmessung", masse and f"{masse} mm"),
                  ("Wandstärke", sw._z(pr.get("wand")) and f"{rf.zahl_text(pr['wand'])} mm")]
        if not neu:
            kat = (d.k.werkstoffe.get(p.get("werkstoff_id")) or {}).get("kategorie") if p.get("werkstoff_id") else None
            werte += [("Werkstoff", (p.get("werkstoff_id") or "–") + (f" ({kat})" if kat else "")),
                      ("Teilelänge", sw._z(p.get("laenge")) and f"{rf.zahl_text(p['laenge'])} mm")]
        for titel, wert in werte:
            lab = QLabel(str(wert) if wert else "–")
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._form.addRow(titel, lab)
            self.felder[titel] = lab
        if not neu:
            h = QLabel("<span style='color:%s'>Profil und Werkstoff ändern: in der Positionstabelle des Angebots."
                       "</span>" % stil.umsetzen(stil.TEXT_GRAU))
            h.setWordWrap(True)
            self._form.addRow(h)

    def _radius(self):
        """Außenradius (gilt im Angebot je Profil + Werkstoff): leer = Stammdaten bzw. Vorgabe nach Norm (als Platzhalter
        angezeigt)."""
        d = self.d
        step_r = getattr(d, "r_step", None)
        eigen = step_r if isinstance(step_r, (int, float)) else getattr(d, "r_aussen", None)
        f = self._rechen("Außenradius", eigen, d.radius_setzen, "mm",
                         "Radius der Außenecken für Schnittlänge, Skizze und 3D. Gilt beim Übernehmen für alle "
                         "Positionen des Angebots mit gleichem Profil und Werkstoff. Leer = Wert der Stammdaten, bei "
                         "Aluminium 0, sonst Vorgabe nach EN 10219; 0 = scharfkantig. Teile aus einer STEP-Datei "
                         "zeigen den dort gemessenen Radius, damit Skizze und 3D genau zur STEP passen.")
        alu = d.profil.get("r_aussen") == 0 and (d.k.profile.get(d.p.get("profil_id")) or {}).get("r_aussen") in (None, "")
        f.setPlaceholderText(f"{rf.zahl_text(sw.radius(d.profil))} ({'Aluminium' if alu else 'Stammdaten'})")
        return f

    def _naht(self):
        d = self.d
        self._combo("Vorgabe", d.naht_vorgabe)
        if isinstance(d.naht_winkel, QComboBox):
            self._combo("Lage", d.naht_winkel)
        else:
            self._spin("Lage", d.naht_winkel, "°")
        self._combo("Quelle", d.naht_quelle)
        return "Schweißnaht"

    def _biegung(self, i):
        t = self.d.schenkel
        if not 0 <= i < t.rowCount():
            raise IndexError(i)
        self._zelle(f"Schenkel {i + 1} außen", t, i, 0)
        self._zelle("Biegewinkel danach", t, i, 1, einheit="°", tipp="+ nach oben, − nach unten, 90 = rechter Winkel")
        self._zelle("Innenradius", t, i, 2, tipp="leer = Blechdicke")
        return f"Biegung B{i + 1}"
