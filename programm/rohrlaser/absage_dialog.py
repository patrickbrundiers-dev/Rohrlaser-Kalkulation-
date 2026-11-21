"""Absagegrund beim Vorgang „Abgelehnt“ und Datei → „Angebots-Auswertung …“ (absage.py, Plan 29.10.2026 1b)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout)

from . import absage
from .ausgabe import euro_text


class AbsageDialog(QDialog):
    """Grund, Preis des Wettbewerbs (optional) und Bemerkung. Nach OK: self.ergebnis = (grund, bemerkung, preis)."""

    def __init__(self, parent, kopf):
        super().__init__(parent)
        self.ergebnis = None
        self.setWindowTitle(f"Angebot abgelehnt – {kopf.get('nummer') or ''}".strip(" –"))
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        info = QLabel(f"Kunde: {kopf.get('kunde') or '–'}. Warum hat der Kunde abgelehnt? Der Grund steht im "
                      "Versandverlauf und in der Angebots-Auswertung (Datei → Angebots-Auswertung …).")
        info.setWordWrap(True)
        form.addRow(info)
        self.grund = QComboBox()
        self.grund.addItems([absage.OHNE_GRUND, *absage.GRUENDE])
        form.addRow("Grund", self.grund)
        self.preis = QDoubleSpinBox()
        self.preis.setRange(0, 10_000_000)
        self.preis.setDecimals(2)
        self.preis.setGroupSeparatorShown(True)
        self.preis.setSuffix(" €")
        self.preis.setSpecialValueText("unbekannt")
        self.preis.setToolTip("Preis des Wettbewerbs netto, wenn der Kunde ihn nennt (leer = unbekannt)")
        form.addRow("Preis Wettbewerb", self.preis)
        self.bemerkung = QLineEdit()
        self.bemerkung.setPlaceholderText("z. B. Wettbewerber, Hinweis des Kunden")
        form.addRow("Bemerkung", self.bemerkung)
        # KI 3 (Paket C): Grund aus der Absage-Mail vorschlagen (Regeln, lokales Sprachmodell nur mit Beleg)
        self.mail = QPlainTextEdit()
        self.mail.setPlaceholderText("Optional: Mail des Kunden hier einfügen – „Grund vorschlagen“ füllt Grund, "
                                     "Preis und Bemerkung aus (nur Vorschlag).")
        self.mail.setMaximumHeight(90)
        form.addRow("Mail des Kunden", self.mail)
        self.vorschlag_knopf = QPushButton("Grund vorschlagen")
        self.vorschlag_knopf.clicked.connect(lambda: self.vorschlagen())
        self.vorschlag_text = QLabel("")
        self.vorschlag_text.setWordWrap(True)
        z = QHBoxLayout()
        z.addWidget(self.vorschlag_knopf)
        z.addWidget(self.vorschlag_text, 1)
        form.addRow(z)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Als abgelehnt markieren")
        knoepfe.button(QDialogButtonBox.Cancel).setText("Abbrechen")
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)

    def vorschlagen(self, text=None, db=None, mit_modell=True):
        """Grund, Wettbewerbspreis und Bemerkung aus der eingefügten Mail vorschlagen; ändert nur die Felder."""
        from . import ki_auslesen
        db = db or getattr(self.parent(), "db", None) or getattr(getattr(self.parent(), "f", None), "db", None)
        v = ki_auslesen.absage_aus_text(db, self.mail.toPlainText() if text is None else text,
                                        mit_modell=mit_modell and db is not None)
        if not v:
            self.vorschlag_text.setText("In der Mail steht kein erkennbarer Grund.")
            return None
        i = self.grund.findText(v["grund"])
        if i >= 0:
            self.grund.setCurrentIndex(i)
        if v.get("preis"):
            self.preis.setValue(v["preis"])
        if v.get("bemerkung") and not self.bemerkung.text().strip():
            self.bemerkung.setText(v["bemerkung"])
        self.vorschlag_text.setText(f"Vorschlag ({'Sprachmodell' if v['quelle'] == 'KI' else 'Regel'}): "
                                    f"{v['grund']}" + (f", Preis {euro_text(v['preis'])} €" if v.get('preis') else "")
                                    + " – bitte prüfen.")
        return v

    def _ok(self):
        self.ergebnis = (self.grund.currentText(), self.bemerkung.text().strip(), self.preis.value() or None)
        self.accept()


def abfragen(parent, kopf):
    """Dialog zeigen; (grund, bemerkung, preis) oder None (abgebrochen)."""
    d = AbsageDialog(parent, kopf)
    return d.ergebnis if d.exec() else None


def _q(w):
    return "–" if w is None else f"{w * 100:.0f} %"


def verkauf_text(g):
    """Verkaufskennzahlen (Master-Prompt 21.11.2026, Punkt 9): Ø Auftragswert, Ø Gewinn mit Marge, verlorenes Volumen,
    Umsatzpotenzial der offenen Angebote."""
    from . import marge as mg
    teile = []
    if g.get("auftrag_mittel") is not None:
        teile.append(f"Ø Auftragswert {euro_text(g['auftrag_mittel'])} €")
    if g.get("gewinn_mittel") is not None:
        m = mg.aus_aufschlag(g["gewinn_mittel"] / 100)
        teile.append(f"Ø Gewinn {g['gewinn_mittel']:.1f} %".replace(".", ",")
                     + (f" (Marge etwa {100 * m:.1f} %)".replace(".", ",") if m is not None else ""))
    if g.get("abgelehnt"):
        teile.append(f"verloren {euro_text(g['abgelehnt_wert'])} €")
    if g.get("potenzial") is not None and g.get("offen"):
        teile.append(f"Umsatzpotenzial offen {euro_text(g['potenzial'])} € (offen {euro_text(g['offen_wert'])} € × "
                     f"Trefferquote)")
    return (" · ".join(teile) + ".") if teile else ""


SPALTEN = ("", "Angebote", "beauftragt", "abgelehnt", "offen", "Trefferquote", "angeboten [€]", "beauftragt [€]")
SPALTEN_GRUND = ("Absagegrund", "Absagen", "Anteil", "abgelehnt [€]")
# Vorschlag K5: Ertrag (Verkauf ohne Material, Zukaufteile, Fracht) je Laserstunde der beauftragten Angebote
SPALTEN_ERTRAG = ("Laser-h beauftragt", "Ertrag €/h Soll", "Ertrag €/h Ist")
# Vorschläge 11.11.2026: V5 Teilemerkmale und V1 Reaktionszeit (vertrieb.py)
TITEL = (("kunde", "Je Kunde"), ("kategorie", "Je Werkstoff-Kategorie"), ("preisklasse", "Je Preisklasse"),
         ("form", "Je Profilform"), ("wand", "Je Wandstärke"), ("laenge", "Je Teilelänge"),
         ("konturen", "Je Komplexität"), ("stueck", "Je Stückzahl"), ("reaktion", "Je Reaktionszeit"),
         ("gewinn", "Je Gewinnhöhe"), ("grund", "Absagegründe"))


class AuswertungDialog(QDialog):
    """Trefferquote je Kunde, Werkstoff-Kategorie, Preisklasse und Absagegrund (nur mit Admin-Rechten)."""

    def __init__(self, fenster, heute=None):
        super().__init__(fenster)
        self.f, self.heute = fenster, heute
        self.setWindowTitle("Angebots-Auswertung")
        self.resize(900, 560)
        self.zeitraum = QComboBox()
        for tage, text in absage.ZEITRAEUME:
            self.zeitraum.addItem(text, tage)
        self.zeitraum.currentIndexChanged.connect(self.laden)
        self.kopf = QLabel()
        self.kopf.setWordWrap(True)
        self.kopf.setTextFormat(Qt.RichText)
        self.reiter = QTabWidget()
        self.tabellen = {}
        for name, titel in TITEL:
            spalten = SPALTEN_GRUND if name == "grund" else (titel.removeprefix("Je "),) + SPALTEN[1:]
            if name == "kunde":
                spalten += SPALTEN_ERTRAG
            t = QTableWidget(0, len(spalten))
            t.setHorizontalHeaderLabels(spalten)
            t.setEditTriggers(QAbstractItemView.NoEditTriggers)
            t.setSelectionBehavior(QAbstractItemView.SelectRows)
            t.verticalHeader().hide()
            t.setSortingEnabled(False)
            self.tabellen[name] = t
            self.reiter.addTab(t, titel)
        self.wettbewerb = QTableWidget(0, 5)
        self.wettbewerb.setHorizontalHeaderLabels(("Nummer", "Kunde", "unser Preis [€]", "Wettbewerb [€]",
                                                   "Abstand"))
        self.wettbewerb.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.wettbewerb.verticalHeader().hide()
        self.reiter.addTab(self.wettbewerb, "Preis Wettbewerb")
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Zeitraum"))
        oben.addWidget(self.zeitraum)
        oben.addStretch(1)
        knoepfe = QDialogButtonBox()
        knoepfe.addButton("Schließen", QDialogButtonBox.RejectRole)
        knoepfe.rejected.connect(self.reject)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(self.kopf)
        lay.addWidget(self.reiter, 1)
        lay.addWidget(knoepfe)
        self.laden()

    def laden(self):
        db = self.f.db
        kategorien = {w: z.get("kategorie") for w, z in db.kontext().werkstoffe.items()}
        from . import feiertage, vertrieb
        zeilen = db.angebote()
        try:
            merkmale = vertrieb.merkmale(db.positionen_merkmale(), db.kontext())
            reaktionen = vertrieb.reaktionen(zeilen, db.anfrage_eingaenge(),
                                             db.einstellung("versand_bundesland") or feiertage.VORGABE)
        except Exception:         # Auswertung nie an einem einzelnen Angebot scheitern lassen
            merkmale, reaktionen = {}, {}
        self.daten = absage.auswertung(zeilen, db.angebot_werkstoffe(), kategorien, self.heute,
                                       self.zeitraum.currentData(), merkmale, reaktionen)
        g = self.daten["gesamt"]
        self.kopf.setText(
            f"<b>{g['angebote']} Angebote</b> ({euro_text(g['summe'])} € netto): {g['beauftragt']} beauftragt "
            f"({euro_text(g['auftragswert'])} €), {g['abgelehnt']} abgelehnt, {g['offen']} offen. "
            f"<b>Trefferquote {_q(g['trefferquote'])}</b> (beauftragt von den entschiedenen). "
            + verkauf_text(g) + " Eine sehr hohe Quote kann heißen, dass die Preise Luft nach oben haben; viele "
            "Absagen „Preis zu hoch“ zeigen, wo es zu teuer ist. Der Reiter „Je Gewinnhöhe“ zeigt, bei welchem "
            "Gewinn Sie gewinnen.")
        for name, _ in TITEL:
            if name not in ("kunde", "grund"):
                self._fuellen(self.tabellen[name], self.daten[name])
        # Ertrag je Laserstunde je Kunde (Vorschlag K5): Soll aus der Kalkulation, Ist aus der Nachkalkulation
        try:
            self.ertrag = absage.ertrag_je_kunde(db, db.angebote(), self.heute, self.zeitraum.currentData())
        except Exception:         # Auswertung nie an einem einzelnen Angebot scheitern lassen
            self.ertrag = {}
        self._fuellen(self.tabellen["kunde"], self.daten["kunde"], lambda g: self._werte(g) + self._ertrag(g["name"]))
        n = sum(g["abgelehnt"] for g in self.daten["grund"])
        self._fuellen(self.tabellen["grund"], self.daten["grund"], lambda g: (
            g["name"], str(g["abgelehnt"]), _q(g["abgelehnt"] / n if n else None), euro_text(g["abgelehnt_wert"])))
        t = self.wettbewerb
        t.setRowCount(0)
        for w in self.daten["wettbewerb"]:
            r = t.rowCount()
            t.insertRow(r)
            for c, text in enumerate((w["nummer"] or "", w["kunde"] or "", euro_text(w["netto"]),
                                      euro_text(w["preis"]), f"{w['abstand'] * 100:+.0f} %")):
                it = QTableWidgetItem(text)
                if c >= 2:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, it)
        t.resizeColumnsToContents()

    def _ertrag(self, name):
        g = (getattr(self, "ertrag", None) or {}).get(name)
        if not g:
            return ("", "", "")
        h = lambda w: euro_text(w) if w is not None else "–"
        return (f"{g['laser_h']:.1f}".replace(".", ","), h(g["eur_h"]), h(g["eur_h_ist"]))

    @staticmethod
    def _werte(g):
        return (g["name"], str(g["angebote"]), str(g["beauftragt"]), str(g["abgelehnt"]), str(g["offen"]),
                _q(g["trefferquote"]), euro_text(g["summe"]), euro_text(g["auftragswert"]))

    def _fuellen(self, t, gruppen, werte=None):
        t.setRowCount(0)
        for g in gruppen:
            r = t.rowCount()
            t.insertRow(r)
            for c, text in enumerate((werte or self._werte)(g)):
                it = QTableWidgetItem(text)
                if c:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, it)
        t.resizeColumnsToContents()
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
