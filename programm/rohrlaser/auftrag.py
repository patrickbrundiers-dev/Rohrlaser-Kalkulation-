"""Auftragsnummer und Liefertermin beim Setzen auf „Beauftragt“ (Plan Arbeitsabläufe W8, Freigabe F6b).

Ein kleines Fenster fragt die Auftragsnummer des Kunden und den Liefertermin ab (beides freiwillig); gespeichert in
angebote.auftragsnr und angebote.liefertermin (ISO-Datum) und gezeigt in der Angebotsliste. Werkstattpapiere und
Materialanfrage bleiben wie bisher eigene Schritte.
"""
import datetime

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QCheckBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, \
    QLineEdit, QVBoxLayout

from . import feiertage
from .stammdaten import ARBEITSTAGE, KALENDERWOCHE, LIEFERDATUM, WOCHEN

OHNE_LIEFERZEIT_TAGE = 14        # Vorschlag für den Termin, wenn das Angebot keine auswertbare Lieferzeit hat


def arbeitstage_spaeter(start, n, land=None):
    """Datum n Arbeitstage (Montag bis Freitag, ohne die Feiertage des Bundeslands land) nach start."""
    return feiertage.arbeitstage_spaeter(start, n, land)


def termin_vorschlag(kopf, heute=None, land=None):
    """Vorschlag für den Liefertermin aus der Lieferzeit des Angebots, gerechnet ab heute (Auftragseingang):
    Arbeitstage/Wochen ab heute (Arbeitstage ohne die Feiertage des Bundeslands land), Kalenderwoche = Freitag der
    Woche, Lieferdatum = das Datum; sonst heute + 14 Tage. Ein schon eingetragener Termin geht vor."""
    heute = heute or datetime.date.today()
    kopf = kopf or {}
    try:
        if kopf.get("liefertermin"):
            return datetime.date.fromisoformat(kopf["liefertermin"])
        art, w = kopf.get("lieferzeit_art"), str(kopf.get("lieferzeit_wert") or "")
        if w and art == ARBEITSTAGE:
            return arbeitstage_spaeter(heute, int(w), land)
        if w and art == WOCHEN:
            return heute + datetime.timedelta(weeks=int(w))
        if w and art == KALENDERWOCHE:
            kw, jahr = (int(t) for t in w.split("/"))
            return datetime.date.fromisocalendar(jahr, kw, 5)
        if w and art == LIEFERDATUM:
            return datetime.date.fromisoformat(w)
    except ValueError:
        pass
    return heute + datetime.timedelta(days=OHNE_LIEFERZEIT_TAGE)


class AuftragDialog(QDialog):
    """Auftragsnummer des Kunden und Liefertermin (Häkchen aus = noch kein Termin)."""

    def __init__(self, parent, angebot, land=None):
        super().__init__(parent)
        self.setWindowTitle(f"Angebot {angebot.get('nummer') or ''} beauftragt")
        lay = QVBoxLayout(self)
        hinweis = QLabel("Auftragsnummer des Kunden und Liefertermin eintragen. Beides steht danach in der "
                         "Angebotsliste und lässt sich hier jederzeit ändern (Vorgang ▾ → Beauftragt).")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        form = QFormLayout()
        self.nummer = QLineEdit(angebot.get("auftragsnr") or "")
        self.nummer.setPlaceholderText("z. B. Bestellnummer des Kunden")
        form.addRow("Auftragsnummer des Kunden", self.nummer)
        self.mit_termin = QCheckBox()
        self.mit_termin.setChecked(bool(angebot.get("liefertermin")) or not angebot.get("auftragsnr"))
        self.termin = QDateEdit(QDate(termin_vorschlag(angebot, land=land)))
        self.termin.setDisplayFormat("dd.MM.yyyy")
        self.termin.setCalendarPopup(True)
        self.mit_termin.toggled.connect(self.termin.setEnabled)
        self.termin.setEnabled(self.mit_termin.isChecked())
        zeile = QHBoxLayout()
        zeile.addWidget(self.mit_termin)
        zeile.addWidget(self.termin, 1)
        form.addRow("Liefertermin", zeile)
        lay.addLayout(form)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    def werte(self):
        """(Auftragsnummer oder None, Liefertermin als ISO-Datum oder None)"""
        t = self.termin.date().toPython().isoformat() if self.mit_termin.isChecked() else None
        return self.nummer.text().strip() or None, t


def abfragen(parent, angebot, land=None):
    """Fenster zeigen. Ergebnis: (Auftragsnummer, Liefertermin) oder None (abgebrochen)."""
    d = AuftragDialog(parent, angebot, land)
    return d.werte() if d.exec() == QDialog.Accepted else None
