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

from . import massbild, rechenfeld as rf, schneidweg as sw, stil

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
            else:
                self._zelle(titel.split(" (")[0], t, r, 2 + i)
        if self.art == "rohr":
            self._zelle("Anzahl", t, r, ROHR_SPALTEN["anzahl"], einheit="Stück")
            self._zelle("Lage ab Ende A", t, r, ROHR_SPALTEN["lage"], tipp="Mitte der (ersten) Kontur ab Ende A; "
                        "leer = gleichmäßig verteilt. Rechnung möglich, z. B. L/2")
            self._zelle("Abstand Muster", t, r, ROHR_SPALTEN["abstand"], muster_zu=ROHR_SPALTEN["anzahl"])
            self._combo("Seite", t.cellWidget(r, ROHR_SPALTEN["seite"]))
            if not d.qs.r:
                self._zelle("Versatz quer", t, r, ROHR_SPALTEN["quer"],
                            tipp="Versatz zur Flächenmitte (+ zur nächsten Fläche hin)")
            if art in sw.MIT_GEWINDE:
                self._combo("Gewinde", t.cellWidget(r, ROHR_SPALTEN["gewinde"]))
            self._zelle("Bemerkung", t, r, ROHR_SPALTEN["text"], text=True,
                        tipp="erscheint in Skizze und Zeichnung")
        else:
            self._zelle("Anzahl", t, r, BLECH_SPALTEN["anzahl"], einheit="Stück")
            self._zelle("Mitte x", t, r, BLECH_SPALTEN["x"], tipp="in der Abwicklung ab links")
            self._zelle("Mitte y", t, r, BLECH_SPALTEN["y"], tipp="in der Abwicklung ab unten")
        self._knoepfe(r)
        return f"{art} · Zeile {r + 1} von {t.rowCount()}"

    def _ende(self, s):
        d = self.d
        self._spin("Gehrungswinkel", d.winkel[s], "°", "Abweichung vom rechtwinkligen Schnitt (0 = gerade)")
        self._combo("gekippt über", d.achse[s])
        if d.achse[s].currentText() == sw.ACHSE_ZWEI:
            self._spin("Winkel über Breite", d.winkel_b[s], "°")
        if d.richtung[s].isEnabled():
            self._combo("längste Seite", d.richtung[s])
        if d.sattel[s].isEnabled():
            self._spin("Ausklinkung auf Rundrohr Ø", d.sattel[s], "mm")
        if d.d3.isChecked():
            self._haken("Gehrung in 3D", d.ende_3d[s])
        return "Anfangsschnitt (Ende A)" if s == "a" else "Endschnitt (Ende B)"

    def _teil(self):
        d = self.d
        if self.art == "rohr":
            if getattr(d, "neu", False) and hasattr(d, "k_laenge"):
                self._spin("Teilelänge", d.k_laenge, "mm")
            info = QLabel(d.info.text())
            info.setWordWrap(True)
            self._form.addRow(info)
            self._spin("Gravur je Teil", d.gravur, "mm")
            self._haken("3D-Schnittbearbeitung", d.d3)
            return "Teil"
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
