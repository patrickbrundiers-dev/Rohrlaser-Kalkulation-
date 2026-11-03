"""Auftragsnummer und Liefertermin beim Setzen auf „Beauftragt“ (Plan Arbeitsabläufe W8, Freigabe F6b).

Ein kleines Fenster fragt die Auftragsnummer des Kunden und den Liefertermin ab (beides freiwillig); gespeichert in
angebote.auftragsnr und angebote.liefertermin (ISO-Datum) und gezeigt in der Angebotsliste. Darunter Häkchen für die
Schritte danach (Auftragsbestätigung, Materialbestellung, Werkstattpapiere, CAM, Etiketten; auftrag_start.py,
Automationen 03.11.2026 2a), die das Programm nach OK nacheinander erledigt.
"""
import datetime

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QCheckBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, \
    QLineEdit, QPushButton, QVBoxLayout

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

    def __init__(self, parent, angebot, land=None, frueh=None, schritte=None):
        """frueh = terminplan.Termin (frühester Termin nach Auslastung, Vorschlag V2) oder None. schritte = gemerkte
        Schritte nach dem Auftrag (auftrag_start, Automationen 03.11.2026 2a) oder None (keine Häkchen)."""
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
        self.frueh = frueh
        if frueh is not None and frueh.datum is not None:
            from . import terminplan
            vorschlag = termin_vorschlag(angebot, land=land)
            t = QLabel(terminplan.text(frueh, vorschlag))
            t.setWordWrap(True)
            if vorschlag < frueh.datum:
                t.setStyleSheet("color: #A33A00;")
            uebernehmen = QPushButton(f"Frühesten Termin übernehmen ({frueh.datum.strftime('%d.%m.%Y')})")
            uebernehmen.clicked.connect(lambda: self.frueh_uebernehmen())
            lay.addWidget(t)
            lay.addWidget(uebernehmen)
        self.schritte = {}
        if schritte is not None:       # Auftrag starten in einem Schritt (2a)
            from .auftrag_start import SCHRITTE
            t = QLabel("<b>Danach gleich erledigen</b> (das Programm merkt die Auswahl; gesendet wird nur in Outlook):")
            t.setWordWrap(True)
            lay.addWidget(t)
            for name, text in SCHRITTE:
                c = QCheckBox(text)
                c.setChecked(name in schritte)
                self.schritte[name] = c
                lay.addWidget(c)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)

    def frueh_uebernehmen(self):
        self.mit_termin.setChecked(True)
        self.termin.setDate(QDate(self.frueh.datum))

    def werte(self):
        """(Auftragsnummer oder None, Liefertermin als ISO-Datum oder None)"""
        t = self.termin.date().toPython().isoformat() if self.mit_termin.isChecked() else None
        return self.nummer.text().strip() or None, t

    def gewaehlte_schritte(self):
        return [n for n, c in self.schritte.items() if c.isChecked()]


def abfragen(parent, angebot, land=None, frueh=None, schritte=None):
    """Fenster zeigen. Ergebnis: (Auftragsnummer, Liefertermin) oder None (abgebrochen). schritte (Liste): gemerkte
    Schritte zum Anhaken; die Liste enthält danach die gewählten."""
    d = AuftragDialog(parent, angebot, land, frueh, schritte)
    if d.exec() != QDialog.Accepted:
        return None
    if schritte is not None:
        schritte[:] = d.gewaehlte_schritte()
    return d.werte()
