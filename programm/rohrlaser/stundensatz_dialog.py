"""Dialog „Stundensatz ermitteln …“ je Maschine (Plan „Stundensatz-Ermittlung je Maschine“, Patrick 29.10.2026).

Links die Werte der Maschine (Anschaffung, Nutzungsdauer, Fläche, Instandhaltung, Wartung, Anschlussleistung,
Verschleiß, Bediener-Anteil), rechts der Rechenweg je Posten (stundensatz.posten) mit Vergleich zum eingetragenen
Satz. „Übernehmen“ speichert die Werte, stellt die Maschine auf „ermittelt“ und schreibt den Satz ins Feld
Stundensatz. Strompreis, Raumkosten, Zinssatz, Bedienerlohn, Gemeinkosten, Arbeitstage und Auslastung kommen aus den
Einstellungen (Kalkulation)."""
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)
from PySide6.QtCore import Qt

from . import stundensatz
from .eingabe import RechenSpin
from .stammdaten import MASCHINEN, zahl_als_text as z

TITEL = {f.name: f.titel.removeprefix("Ermittlung: ") for f in MASCHINEN.felder}
GRENZE = {f.name: (f.von or 0, f.bis or 1e9, f.stellen or 0) for f in MASCHINEN.felder}


class StundensatzDialog(QDialog):
    def __init__(self, eltern, maschine, einst):
        super().__init__(eltern)
        self.maschine, self.einst = dict(maschine), einst
        self.setWindowTitle(f"Stundensatz ermitteln – {maschine.get('maschinen_id') or ''}")
        self.felder = {}
        form = QFormLayout()
        for n in stundensatz.FELDER:
            von, bis, stellen = GRENZE[n]
            s = RechenSpin()
            s.setRange(von, bis)
            s.setDecimals(stellen)
            s.setGroupSeparatorShown(True)
            v = maschine.get(n)
            s.setValue(v if isinstance(v, (int, float)) else 0)
            s.valueChanged.connect(self.rechnen)
            form.addRow(TITEL[n], s)
            self.felder[n] = s
        self.tabelle = QTableWidget(0, 4)
        self.tabelle.setHorizontalHeaderLabels(["Posten", "Eingabe", "€/Jahr", "€/h"])
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabelle.horizontalHeader().setStretchLastSection(True)
        self.stunden = QLabel()
        self.vergleich = QLabel()
        self.vergleich.setWordWrap(True)
        hinweis = QLabel("Strompreis, Raumkosten, Zinssatz, Bedienerlohn, Gemeinkosten, Arbeitstage und Auslastung: "
                         "Einstellungen → Kalkulation. Schneidgas zählt nicht mit, es wird je Teil gerechnet.")
        hinweis.setWordWrap(True)
        rechts = QVBoxLayout()
        for w in (self.tabelle, self.stunden, self.vergleich):
            rechts.addWidget(w)
        oben = QHBoxLayout()
        oben.addLayout(form)
        oben.addLayout(rechts, 1)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Übernehmen (Stundensatz ermittelt)")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        self.knopf = knoepfe.button(QDialogButtonBox.Ok)
        aussen = QVBoxLayout(self)
        aussen.addLayout(oben)
        aussen.addWidget(hinweis)
        aussen.addWidget(knoepfe)
        self.resize(980, 520)
        self.rechnen()

    def werte(self):
        """Werte der Felder als dict (0 = leer)."""
        return {n: s.value() or None for n, s in self.felder.items()}

    def rechnen(self):
        m = dict(self.maschine, **self.werte())
        zeilen, h, satz = stundensatz.posten(m, self.einst)
        self.tabelle.setRowCount(len(zeilen))
        for r, (t, e, j, eh) in enumerate(zeilen):
            summe = e is None
            for c, text in enumerate((t, e or "", "" if j is None else z(j, 0), z(eh, 2))):
                it = QTableWidgetItem(text)
                if c >= 2:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if summe:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                self.tabelle.setItem(r, c, it)
        self.tabelle.resizeColumnsToContents()
        self.stunden.setText(f"Genutzte Stunden je Jahr: {z(h, 0)} h (Stunden je Arbeitstag × Arbeitstage × "
                             "Auslastung)")
        alt = self.maschine.get("stundensatz")
        if satz is None:
            self.vergleich.setText("Noch nicht rechenbar: Werte eintragen (und Stunden je Jahr > 0).")
        else:
            text = f"Ermittelt: <b>{z(satz, 2)} €/h</b>"
            if isinstance(alt, (int, float)):
                text += f" · eingetragen bisher {z(alt, 2)} €/h (von Hand, mit Gas und Strom)"
            self.vergleich.setText(text + ". Mit „ermittelt“ kommt das Schneidgas je Teil dazu.")
        self.satz = satz
        self.knopf.setEnabled(satz is not None)


def dialog_zeigen(eltern, maschine, einst):
    """Dialog öffnen; Ergebnis {Feld: Wert} zum Speichern (mit satz_art, stundensatz) oder None."""
    d = StundensatzDialog(eltern, maschine, einst)
    if d.exec() != QDialog.Accepted or d.satz is None:
        return None
    return dict(d.werte(), satz_art=stundensatz.SATZ_ERMITTELT, stundensatz=round(d.satz, 2))
