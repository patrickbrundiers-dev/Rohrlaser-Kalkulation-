"""Fenster „Angebotsvarianten A–E“ (Angebotswesen P4, 20.11.2026): Original und bis zu fünf Varianten A–E
nebeneinander, Eingaben oben, Ergebnis darunter. Nichts ändert das Original; „Als Fassung übernehmen“ legt eine neue
Fassung mit den Kalkulationswerten der gewählten Variante an (angebot_varianten.py)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from . import angebot_varianten as av
from . import stil
from .stammdaten import zahl_als_text, zahl_aus_text

GRAU = stil.farbe_fest(stil.TEXT_GRAU)
ROT = stil.farbe_fest(stil.ROT)
GRUEN = stil.farbe_fest(stil.GRUEN)


def _geld(x):
    return "–" if x is None else f"{zahl_als_text(x, 2)} €"


def _prozent(x):
    return "–" if x is None else f"{zahl_als_text(100 * x, 1)} %"


class VariantenDialog(QDialog):
    """seite = Angebotsseite (kopf, positionen, ergebnis, k, tabellen, einst, _rechnung, db, id)."""

    def __init__(self, seite, parent=None):
        super().__init__(parent if parent is not None else seite)
        self.s = seite
        self.setWindowTitle(f"Angebotsvarianten A–E – Angebot {seite.kopf.get('nummer') or ''}")
        lay = QVBoxLayout(self)
        info = QLabel("Je Variante nur die Werte eintragen, die sich ändern sollen (leer = wie im Angebot). Gerechnet "
                      "wird mit der vollen Kalkulation und dem Schnittplan des Angebots; das Angebot selbst bleibt "
                      "unverändert. Preisänderungen (Material, Stundensätze, Zukauf) sind nur ein Vergleich.")
        info.setWordWrap(True)
        lay.addWidget(info)
        varianten = {v["buchstabe"]: v for v in av.lesen(seite.kopf)}
        self.varianten = [varianten.get(b) or dict(buchstabe=b, name="", werte={}) for b in av.BUCHSTABEN]
        spalten = ["Original"] + [f"Variante {b}" for b in av.BUCHSTABEN]
        zeilen = ["Bezeichnung"] + [t for _, t in av.FELDER]
        self.eingabe = QTableWidget(len(zeilen), len(spalten))
        self.eingabe.setHorizontalHeaderLabels(spalten)
        self.eingabe.setVerticalHeaderLabels(zeilen)
        for r, (n, _) in enumerate([("name", "")] + list(av.FELDER)):
            orig = QTableWidgetItem(self._original(n))
            orig.setFlags(Qt.ItemIsEnabled)
            orig.setForeground(QBrush(GRAU))
            orig.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.eingabe.setItem(r, 0, orig)
            for c, v in enumerate(self.varianten, start=1):
                w = v["name"] if n == "name" else v["werte"].get(n)
                it = QTableWidgetItem("" if w is None else (w if n == "name" else zahl_als_text(w, 2)))
                if n != "name":
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.eingabe.setItem(r, c, it)
        self.eingabe.resizeColumnsToContents()
        lay.addWidget(self.eingabe, 3)
        knoepfe = QHBoxLayout()
        rechnen_k = QPushButton("Vergleichen")
        rechnen_k.setToolTip("Alle Varianten mit der Kalkulation des Angebots rechnen")
        rechnen_k.clicked.connect(self.vergleichen)
        knoepfe.addWidget(rechnen_k)
        knoepfe.addStretch(1)
        knoepfe.addWidget(QLabel("Variante:"))
        self.wahl = QComboBox()
        self.wahl.addItems(list(av.BUCHSTABEN))
        knoepfe.addWidget(self.wahl)
        self.uebernehmen_k = QPushButton("Als Fassung übernehmen …")
        self.uebernehmen_k.setToolTip("Neue Fassung des Angebots (-2, -3 …) mit den Kalkulationswerten der Variante; "
                                      "das Original bleibt bestehen")
        self.uebernehmen_k.clicked.connect(lambda: self.uebernehmen())
        knoepfe.addWidget(self.uebernehmen_k)
        lay.addLayout(knoepfe)
        self.ergebnis = QTableWidget(len(av.ERGEBNIS), len(spalten))
        self.ergebnis.setHorizontalHeaderLabels(spalten)
        self.ergebnis.setVerticalHeaderLabels([t for _, t in av.ERGEBNIS])
        lay.addWidget(self.ergebnis, 2)
        unten = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Close)
        unten.button(QDialogButtonBox.Save).setText("Varianten speichern")
        unten.button(QDialogButtonBox.Close).setText("Schließen")
        unten.accepted.connect(self.speichern)
        unten.rejected.connect(self.reject)
        lay.addWidget(unten)
        self.zeilen = []
        self.resize(1100, 700)
        self.vergleichen()

    def _original(self, n):
        if n == "name":
            return "wie Angebot"
        w = self.s.kopf.get(n)
        if isinstance(w, (int, float)) and not isinstance(w, bool):
            return zahl_als_text(w, 2)
        return "" if n in dict(av.PREIS_FELDER) else "Einstellung"

    def werte(self):
        """Varianten aus der Tabelle; unlesbare Zahl: ValueError mit Zeile und Spalte."""
        out = []
        for c, v in enumerate(self.varianten, start=1):
            name = (self.eingabe.item(0, c).text() if self.eingabe.item(0, c) else "").strip()
            werte = {}
            for r, (n, titel) in enumerate(av.FELDER, start=1):
                t = (self.eingabe.item(r, c).text() if self.eingabe.item(r, c) else "").strip()
                if not t:
                    continue
                try:
                    z = zahl_aus_text(t)
                except (TypeError, ValueError):
                    z = None
                if z is None:
                    raise ValueError(f"Variante {v['buchstabe']}, {titel}: „{t}“ ist keine Zahl.")
                werte[n] = z
            out.append(dict(buchstabe=v["buchstabe"], name=name, werte=werte))
        return out

    def vergleichen(self):
        try:
            varianten = [v for v in self.werte() if v["name"] or v["werte"]]
        except ValueError as e:
            QMessageBox.warning(self, "Varianten", str(e))
            return None
        s = self.s
        summen = s._rechnung()[1]
        self.zeilen = av.vergleich(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst, summen, varianten)
        je = {z["buchstabe"]: z for z in self.zeilen}
        for c, b in enumerate([""] + list(av.BUCHSTABEN)):
            z = je.get(b)
            for r, (n, _) in enumerate(av.ERGEBNIS):
                if z is None:
                    text = ""
                elif z.get("fehler"):
                    text = "Fehler" if r == 0 else ""
                else:
                    w = z["ergebnis"].get(n)
                    text = _prozent(w) if n == "marge" else _geld(w)
                it = QTableWidgetItem(text)
                it.setFlags(Qt.ItemIsEnabled)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if z is not None and z.get("fehler"):
                    it.setToolTip(z["fehler"])
                    it.setForeground(QBrush(ROT))
                elif n == "unterschied" and z is not None and z["ergebnis"].get(n):
                    it.setForeground(QBrush(GRUEN if z["ergebnis"][n] > 0 else ROT))
                elif n == "marge" and z is not None and z["ergebnis"].get(n) is not None:
                    m = s.einst.get("mindestmarge") or 0
                    if m and z["ergebnis"][n] < m:
                        it.setForeground(QBrush(ROT))
                        it.setToolTip("Unter der Mindestmarge")
                self.ergebnis.setItem(r, c, it)
        self.ergebnis.resizeColumnsToContents()
        return self.zeilen

    def speichern(self):
        try:
            text = av.als_text(self.werte())
        except ValueError as e:
            QMessageBox.warning(self, "Varianten", str(e))
            return False
        s = self.s
        s.db.angebot_aendern(s.id, "varianten", text)
        s.kopf["varianten"] = text
        if hasattr(s, "f") and hasattr(s.f, "meldung"):
            s.f.meldung("Varianten gespeichert.")
        self.accept()
        return True

    def uebernehmen(self, frage=True):
        """Gewählte Variante als neue Fassung. frage=False: ohne Rückfrage (Tests). Ergebnis: neue ID oder None."""
        try:
            liste = self.werte()
        except ValueError as e:
            QMessageBox.warning(self, "Varianten", str(e))
            return None
        v = next(x for x in liste if x["buchstabe"] == self.wahl.currentText())
        if not v["werte"]:
            QMessageBox.information(self, "Varianten", f"Variante {v['buchstabe']} hat keine Werte.")
            return None
        s = self.s
        if frage and QMessageBox.question(
                self, "Als Fassung übernehmen",
                f"Neue Fassung von Angebot {s.kopf.get('nummer')} mit den Werten der Variante {v['buchstabe']} "
                "anlegen? Das bisherige Angebot steht danach auf „Ersetzt“.") != QMessageBox.Yes:
            return None
        s.db.angebot_aendern(s.id, "varianten", av.als_text(liste))
        neu, offen = av.uebernehmen(s.db, s.id, v)
        text = f"Variante {v['buchstabe']} als Fassung {s.db.angebot(neu)['nummer']} angelegt."
        if offen:
            text += " Nicht übernommen (nur Vergleich): " + ", ".join(offen) + "."
        if hasattr(s, "f") and hasattr(s.f, "meldung"):
            s.f.meldung(text)
        self.neue_fassung = neu
        return neu
