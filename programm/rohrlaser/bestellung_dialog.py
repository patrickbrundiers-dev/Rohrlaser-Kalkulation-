"""Fenster „Bestellung prüfen“ (Automationen 03.11.2026, Vorschlag 1a; Logik in bestellung.py).

Die Anfrage-Karte erkennt eine Bestellung des Kunden (Mail ohne STEP mit Angebots- bzw. Anfrage-Nr.). Das Fenster
zeigt Bestellnummer und Wunschtermin (vorbelegt aus der Mail) und je Position den Abgleich mit dem Angebot:
Menge und Preis je Stück, Abweichungen gelb, fehlende Artikel rot. „Beauftragen“ setzt das Angebot auf Beauftragt
(mit Bestellnummer und Termin), legt die Mail in den Angebotsordner (Unterordner „Bestellung“) und erledigt die
angehakten Schritte (auftrag_start). Bestellte Mengen übernimmt das Programm nur mit Häkchen."""
import datetime

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QAbstractItemView, QCheckBox, QDateEdit, QDialog, QFormLayout, QHBoxLayout, \
    QHeaderView, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout

from . import bestellung, stil

UNTERORDNER = "Bestellung"
SPALTEN = ("Pos.", "Artikel", "Angebot Stk", "Bestellt Stk", "Preis/Stk Angebot", "Preis/Stk Bestellung", "Prüfung")


def _euro(w):
    return f"{w:.2f}".replace(".", ",") if isinstance(w, (int, float)) else "–"


class BestellungDialog(QDialog):
    def __init__(self, parent, db, angebot, abgleich, bestellnr, termin, datei_name="", schritte=()):
        super().__init__(parent)
        from .auftrag_start import SCHRITTE
        self.abgleich = abgleich
        self.setWindowTitle(f"Bestellung prüfen – Angebot {angebot.get('nummer') or ''}")
        self.resize(860, 560)
        lay = QVBoxLayout(self)
        abw = [z for z in abgleich if z["status"] != bestellung.OK]
        t = QLabel(f"Bestellung von <b>{angebot.get('kunde') or ''}</b> zu Angebot <b>{angebot.get('nummer')}</b>"
                   + (f" ({datei_name})" if datei_name else "") + ". "
                   + (f"<span style='color:#A66A00'><b>{len(abw)} Abweichung(en)</b> – bitte prüfen.</span>" if abw
                      else "Mengen und Preise passen zum Angebot."))
        t.setWordWrap(True)
        lay.addWidget(t)
        form = QFormLayout()
        self.nummer = QLineEdit(bestellnr or angebot.get("auftragsnr") or "")
        form.addRow("Bestellnummer des Kunden", self.nummer)
        self.mit_termin = QCheckBox("Liefertermin")
        self.mit_termin.setChecked(bool(termin))
        self.termin = QDateEdit(QDate(datetime.date.fromisoformat(termin) if termin else
                                      datetime.date.today() + datetime.timedelta(days=14)))
        self.termin.setDisplayFormat("dd.MM.yyyy")
        self.termin.setCalendarPopup(True)
        self.termin.setEnabled(bool(termin))
        self.mit_termin.toggled.connect(self.termin.setEnabled)
        zeile = QHBoxLayout()
        zeile.addWidget(self.mit_termin)
        zeile.addWidget(self.termin, 1)
        form.addRow("Wunschtermin", zeile)
        lay.addLayout(form)
        tab = self.tabelle = QTableWidget(len(abgleich), len(SPALTEN))
        tab.setHorizontalHeaderLabels(SPALTEN)
        tab.verticalHeader().setVisible(False)
        tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        farbe = {bestellung.ABWEICHUNG: stil.farbe("#FFF4D6"), bestellung.FEHLT: stil.farbe("#FDECEA")}
        for r, z in enumerate(abgleich):
            werte = (z["pos"], z["artikel"], z["stueck"], z["bestellt"] if z["bestellt"] is not None else "–",
                     _euro(z["preis"]), _euro(z["preis_bestellt"]), z["hinweis"] or "passt")
            for c, w in enumerate(werte):
                it = QTableWidgetItem(str(w))
                if 2 <= c <= 5:
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if z["status"] in farbe:
                    it.setBackground(farbe[z["status"]])
                tab.setItem(r, c, it)
        tab.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        tab.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(tab, 1)
        mengen = [z for z in abgleich if z["bestellt"] is not None and z["bestellt"] != z["stueck"]]
        self.mengen = QCheckBox(f"Bestellte Mengen ins Angebot übernehmen ({len(mengen)} Position(en))")
        self.mengen.setVisible(bool(mengen))
        lay.addWidget(self.mengen)
        lay.addWidget(QLabel("<b>Danach gleich erledigen</b> (gesendet wird nur in Outlook):"))
        self.schritte = {}
        for name, text in SCHRITTE:
            c = QCheckBox(text)
            c.setChecked(name in schritte)
            self.schritte[name] = c
            lay.addWidget(c)
        knoepfe = QHBoxLayout()
        knoepfe.addStretch(1)
        self.knopf_ok = QPushButton("Beauftragen")
        self.knopf_ok.setObjectName("primaer")
        self.knopf_ok.clicked.connect(self.accept)
        abbrechen = QPushButton("Abbrechen")
        abbrechen.clicked.connect(self.reject)
        knoepfe.addWidget(self.knopf_ok)
        knoepfe.addWidget(abbrechen)
        lay.addLayout(knoepfe)

    def werte(self):
        """(Bestellnummer oder None, Termin ISO oder None, Mengen übernehmen, [Schritte])"""
        t = self.termin.date().toPython().isoformat() if self.mit_termin.isChecked() else None
        return (self.nummer.text().strip() or None, t, not self.mengen.isHidden() and self.mengen.isChecked(),
                [n for n, c in self.schritte.items() if c.isChecked()])


def pruefen(f, pfad, erkannt, text, dialog=None):
    """Fenster zeigen und bei „Beauftragen“ ausführen. erkannt = bestellung.erkennen(...). dialog(d) bedient das
    Fenster statt exec und gibt True (Beauftragen) oder False zurück (Tests). Ergebnis: True, wenn beauftragt."""
    from pathlib import Path
    from . import auftrag_start, automatik
    db = f.db
    a = erkannt["angebot"]
    abgleich = bestellung.abgleich(db, a["id"], text)
    d = BestellungDialog(f, db, a, abgleich, erkannt.get("bestellnr"), erkannt.get("termin"), Path(pfad).name,
                         auftrag_start.gewaehlt(db))
    ok = dialog(d) if dialog else d.exec() == QDialog.Accepted
    if not ok:
        return False
    nr, termin, mengen, schritte = d.werte()
    auftrag_start.merken(db, schritte)
    if mengen:
        for z in abgleich:
            if z["bestellt"] is not None and z["bestellt"] != z["stueck"]:
                db.position_aendern(z["position_id"], "stueck", int(z["bestellt"]))
    abw = sum(1 for z in abgleich if z["status"] != bestellung.OK)
    try:
        ziel = Path(f.angebot_ordner(db.angebot(a["id"]))) / UNTERORDNER
        neu = automatik.verschieben(db, pfad, ziel, "bestellung",
                                    f"Bestellung {nr or ''} ({Path(pfad).name}) zu Angebot {a.get('nummer')} "
                                    "zugeordnet".replace("  ", " "), a["id"])
    except OSError as e:
        neu = pfad
        f.meldung(f"Bestellung: Mail nicht verschoben ({e}).", fehler=True)
    db.versand_merken(a["id"], bestellung.eintrag(Path(neu).name, nr, abw))
    # schritte=[] : das Beauftragt-Fenster nicht noch einmal zeigen; die Schritte kommen danach
    if not f.angebote.vorgang_setzen("Beauftragt", a["id"], auftrag=(nr, termin), schritte=schritte):
        return False
    return True
