"""Fenster „Abruf-/Rahmenangebot“ (Patrick 30.10.2026, abruf.py): Jahresmenge und Abrufmenge von–bis, Laufzeit,
Material je Abruf (Materialklausel) oder bevorratet mit Lagerzins. Die Stückzahlen der Positionen bleiben, wie sie
sind; der Hinweis sagt, dass sie dem kleinsten Abruf entsprechen sollen."""
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
                               QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from . import abruf
from .eingabe import RechenSpin, RechenSpinGanz
from .stammdaten import ABRUF_JE, ABRUF_LAGER, ABRUF_MATERIAL

FELDER = ("abruf_jahr_von", "abruf_jahr_bis", "abruf_von", "abruf_bis", "abruf_laufzeit", "abruf_material",
          "abruf_lagerzins")


def _ganz(von, bis, wert, schritt=100):
    w = RechenSpinGanz()
    w.setRange(von, bis)
    w.setGroupSeparatorShown(True)
    w.setSingleStep(schritt)
    w.setValue(int(wert or 0))
    return w


class AbrufDialog(QDialog):
    """kopf = Angebotskopf, einst = Einstellungen (Vorgaben Laufzeit und Lagerzins), stueck = größte Stückzahl der
    Positionen (Vorschlag für den kleinsten Abruf). auswerten = Funktion(Kopffelder) → Auswertung wie beim
    Rahmenauftrag (rahmen_kalk.angebot_auswertung; Patrick 20.11.2026 „Ja umstellen“): Varianten A/B/C,
    Materialvergleich, Preisstaffel nach Jahresmenge, empfohlene Losgröße."""

    def __init__(self, parent, kopf, einst, stueck=None, losgroesse=None, auswerten=None):
        super().__init__(parent)
        self.setWindowTitle("Abruf-/Rahmenangebot")
        k, e = kopf or {}, einst or {}
        von = k.get("abruf_von") or (int(stueck) if stueck else None)
        self.jahr_von = _ganz(0, 100000000, k.get("abruf_jahr_von") or (von * 10 if von else 0))
        self.jahr_bis = _ganz(0, 100000000, k.get("abruf_jahr_bis") or self.jahr_von.value())
        self.von = _ganz(0, 10000000, von, 10)
        self.bis = _ganz(0, 10000000, k.get("abruf_bis") or von, 10)
        self.laufzeit = _ganz(1, 120, k.get("abruf_laufzeit") or e.get("abruf_laufzeit") or 12, 1)
        self.material = QComboBox()
        self.material.addItems(list(ABRUF_MATERIAL))
        self.material.setCurrentText(k.get("abruf_material") or ABRUF_JE)
        self.zins = RechenSpin()
        self.zins.setRange(0, 100)
        self.zins.setDecimals(1)
        z = k.get("abruf_lagerzins")
        self.zins.setValue(z if isinstance(z, (int, float)) else (e.get("abruf_lagerzins") or 0))
        form = QFormLayout()
        for titel, a, b in (("Jahresmenge [Stk.]", self.jahr_von, self.jahr_bis),
                            ("Abrufmenge [Stk.]", self.von, self.bis)):
            z_ = QHBoxLayout()
            z_.addWidget(QLabel("von"))
            z_.addWidget(a, 1)
            z_.addWidget(QLabel("bis"))
            z_.addWidget(b, 1)
            form.addRow(titel, z_)
        form.addRow("Laufzeit / Preisbindung [Monate]", self.laufzeit)
        form.addRow("Material", self.material)
        form.addRow("Lagerzins [% p. a.]", self.zins)
        self.info = QLabel()
        self.info.setWordWrap(True)
        hinweis = QLabel("Die Stückzahlen der Positionen sind der kleinste Abruf. Rüsten und Fracht zählen je Abruf, "
                         "Programmierung und Musterteile werden auf die kleinste Jahresmenge verteilt. Größere "
                         "Abrufe legt der Knopf „Abrufstufen anlegen“ (Reiter Staffeln) als Stufen an. Bevorratet: "
                         "Lagerzins auf das Material, im Mittel der halbe Jahresbedarf.")
        hinweis.setWordWrap(True)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(self.info)
        # Losgröße (Vorschlag J5b): wirtschaftliche Abrufmenge nach Andler, nur als Zahl
        self.los = QLabel(f"Wirtschaftliche Abrufmenge (Andler): {losgroesse} Stk." if losgroesse else "")
        self.los.setToolTip("√(2 × Jahresmenge × Rüsten und Fracht je Abruf ÷ (Stückkosten × Lagerzins)); nur ein "
                            "Richtwert, die Abrufmenge legen Sie fest.")
        self.los.setVisible(bool(losgroesse))
        lay.addWidget(self.los)
        lay.addWidget(hinweis)
        self.auswerten_fn, self.auswertung = auswerten, None
        if auswerten is not None:
            lay.addWidget(self._wirtschaftlichkeit())
        lay.addWidget(knoepfe)
        for w in (self.jahr_von, self.jahr_bis, self.von, self.bis, self.laufzeit, self.zins):
            w.valueChanged.connect(self._info)
        self.material.currentTextChanged.connect(self._info)
        self._info()

    def werte(self):
        """Kopffelder des Abruf-Angebots (abruf = ja); bis kleiner als von wird auf von gesetzt."""
        jv, av = self.jahr_von.value() or None, self.von.value() or None
        return dict(abruf="ja", abruf_jahr_von=jv, abruf_jahr_bis=max(self.jahr_bis.value(), jv or 0) or None,
                    abruf_von=av, abruf_bis=max(self.bis.value(), av or 0) or None,
                    abruf_laufzeit=self.laufzeit.value(),
                    abruf_material=None if self.material.currentText() == ABRUF_JE else ABRUF_LAGER,
                    abruf_lagerzins=self.zins.value())

    def _info(self, *_):
        self.zins.setEnabled(self.material.currentText() == ABRUF_LAGER)
        self.info.setText(abruf.kurz(self.werte()) or "")

    # ------------------------------------------------------------------ Wirtschaftlichkeit (wie Rahmenauftrag)
    def _wirtschaftlichkeit(self):
        box = QGroupBox("Wirtschaftlichkeit (wie Rahmenauftrag)")
        lay = QVBoxLayout(box)
        self.w_text = QLabel()
        self.w_text.setWordWrap(True)
        self.w_var = _tabelle(("Variante", "Lose", "Selbstkosten €", "Lager + Kapital €", "Preis €/Stk.", "Marge"))
        self.w_staffel = _tabelle(("Menge aller Positionen [Stk.]", "Szenario", "Selbstkosten €/Stk.", "Preis €/Stk.", "Marge"))
        k = QPushButton("Neu rechnen")
        k.setToolTip("Rechnet mit den Werten oben: gleiche Kalkulation wie das Angebot, Abrufe gleichmäßig über die "
                     "Laufzeit. Ändert am Angebot nichts.")
        k.clicked.connect(self.neu_rechnen)
        lay.addWidget(self.w_text)
        lay.addWidget(self.w_var)
        lay.addWidget(self.w_staffel)
        lay.addWidget(k)
        self.neu_rechnen()
        return box

    def neu_rechnen(self, *_):
        """Auswertung mit den Werten im Fenster; Ergebnis dict (auch mit fehler)."""
        from . import rahmen_kalk as rk
        try:
            a = self.auswerten_fn(self.werte())
        except (ValueError, KeyError, ZeroDivisionError, TypeError) as e:
            a = dict(fehler=f"Auswertung nicht möglich: {e}")
        self.auswertung = a
        self.w_text.setText(rk.angebot_text(a))
        if a.get("fehler"):
            self.w_var.setRowCount(0)
            self.w_staffel.setRowCount(0)
            return a
        v = a["varianten"]
        zeilen = []
        for x in (rk.A, rk.B, rk.C):
            r = v[x]
            zeilen.append([f"{x} {rk.VARIANTE_TEXT[x]}" + (" ★" if x == a["empfehlung"] else ""), str(r["lose"]),
                           _eur(r["selbst"]), _eur(r["lager"] + r["kapital"] + r.get("material_kapital", 0.0)),
                           _eur(r["preis_stueck"], 3), _pz(r["marge"])])
        _fuellen(self.w_var, zeilen)
        self.w_var.setFixedHeight(self.w_var.horizontalHeader().height() + 3 * self.w_var.rowHeight(0) + 4)
        self.los.setVisible(False)           # die Empfehlung oben ersetzt den Andler-Richtwert
        zeilen = [[f"{z['menge']:,}".replace(",", "."), s["name"], _eur(s["selbst_stueck"], 3), _eur(s["preis_stueck"], 3),
                   _pz(s["marge"])] for z in a["preisstaffel"] for s in z["szenarien"]]
        _fuellen(self.w_staffel, zeilen)
        return a


def _eur(x, nk=2):
    return f"{x:,.{nk}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pz(x):
    return f"{100 * x:.1f} %".replace(".", ",") if x is not None else ""


def _tabelle(spalten):
    t = QTableWidget(0, len(spalten))
    t.setHorizontalHeaderLabels(list(spalten))
    t.verticalHeader().setVisible(False)
    t.setEditTriggers(QAbstractItemView.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    t.horizontalHeader().setStretchLastSection(True)
    return t


def _fuellen(t, zeilen):
    t.setRowCount(len(zeilen))
    for r, z in enumerate(zeilen):
        for c, w in enumerate(z):
            t.setItem(r, c, QTableWidgetItem(w))
