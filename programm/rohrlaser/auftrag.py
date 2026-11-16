"""Auftragsnummer und Liefertermin beim Setzen auf „Beauftragt“ (Plan Arbeitsabläufe W8, Freigabe F6b).

Ein kleines Fenster fragt die Auftragsnummer des Kunden und den Liefertermin ab (beides freiwillig); gespeichert in
angebote.auftragsnr und angebote.liefertermin (ISO-Datum, ab Werk) und gezeigt in der Angebotsliste. Dazu das
Lieferdatum frei Haus (angebote.liefertermin_frei_haus, frachtzeit.py): ab Werk + Frachtlaufzeit; beide Felder sind
gekoppelt (eins ändern rechnet das andere). Darunter Häkchen für die
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


def termin_vorschlag(kopf, heute=None, land=None, lz=None):
    """Vorschlag für den Liefertermin ab Werk aus der Lieferzeit des Angebots, gerechnet ab heute (Auftragseingang):
    Arbeitstage/Wochen ab heute (Arbeitstage ohne die Feiertage des Bundeslands land), Kalenderwoche = Freitag der
    Woche, Lieferdatum = das Datum; sonst heute + 14 Tage. Ein schon eingetragener Termin geht vor.
    lz = frachtzeit.Laufzeit: die Lieferzeit meint bei frei Haus die Ankunft beim Kunden, ab Werk wird rückwärts
    gerechnet (Patrick 10.11.2026, F3a); None = wie bisher ohne Fracht."""
    heute = heute or datetime.date.today()
    kopf = kopf or {}
    if kopf.get("liefertermin"):
        try:
            return datetime.date.fromisoformat(kopf["liefertermin"])
        except ValueError:
            pass
    d = kunden_vorschlag(kopf, heute, land)
    if lz is not None and d is not None:
        from . import frachtzeit
        return frachtzeit.aus_kundentermin(d, lz, land)
    return d if d is not None else heute + datetime.timedelta(days=OHNE_LIEFERZEIT_TAGE)


def kunden_vorschlag(kopf, heute=None, land=None):
    """Termin, den die Lieferzeit des Angebots dem Kunden nennt (bei frei Haus: Ankunft), oder None ohne
    auswertbare Lieferzeit."""
    heute = heute or datetime.date.today()
    kopf = kopf or {}
    try:
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
    return None


class AuftragDialog(QDialog):
    """Auftragsnummer des Kunden und Liefertermin ab Werk und frei Haus (Häkchen aus = noch kein Termin)."""

    def __init__(self, parent, angebot, land=None, frueh=None, schritte=None, lz=None):
        """frueh = terminplan.Termin (frühester Termin nach Auslastung, Vorschlag V2) oder None. schritte = gemerkte
        Schritte nach dem Auftrag (auftrag_start, Automationen 03.11.2026 2a) oder None (keine Häkchen).
        lz = frachtzeit.Laufzeit (None = ohne Fracht: frei Haus = ab Werk)."""
        from . import frachtzeit
        super().__init__(parent)
        self.land = land
        self.lz = lz or frachtzeit.Laufzeit(0, "ohne Frachtangabe", False)
        self.setWindowTitle(f"Angebot {angebot.get('nummer') or ''} beauftragt")
        lay = QVBoxLayout(self)
        hinweis = QLabel("Auftragsnummer des Kunden und Liefertermin eintragen. Beides steht danach in der "
                         "Angebotsliste und lässt sich hier jederzeit ändern (Vorgang ▾ → Beauftragt). "
                         "Ab Werk = versandbereit (so wird geplant), frei Haus = Ankunft beim Kunden.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        form = QFormLayout()
        self.nummer = QLineEdit(angebot.get("auftragsnr") or "")
        self.nummer.setPlaceholderText("z. B. Bestellnummer des Kunden")
        form.addRow("Auftragsnummer des Kunden", self.nummer)
        self.mit_termin = QCheckBox()
        self.mit_termin.setChecked(bool(angebot.get("liefertermin")) or not angebot.get("auftragsnr"))
        vorschlag = termin_vorschlag(angebot, land=land, lz=self.lz)
        self.termin = QDateEdit(QDate(vorschlag))
        self.frei_haus = QDateEdit()
        for f in (self.termin, self.frei_haus):
            f.setDisplayFormat("dd.MM.yyyy")
            f.setCalendarPopup(True)
        gespeichert = frachtzeit._iso(angebot.get("liefertermin_frei_haus")) if angebot.get("liefertermin") else None
        self.frei_haus.setDate(QDate(gespeichert or frachtzeit.frei_haus(vorschlag, self.lz.tage, land)))
        self._koppeln = True
        self.termin.dateChanged.connect(lambda _d: self._ab_werk_geaendert())
        self.frei_haus.dateChanged.connect(lambda _d: self._frei_haus_geaendert())
        self.mit_termin.toggled.connect(self._freigeben)
        zeile = QHBoxLayout()
        zeile.addWidget(self.mit_termin)
        zeile.addWidget(self.termin, 1)
        form.addRow("Liefertermin ab Werk", zeile)
        form.addRow("Lieferdatum frei Haus", self.frei_haus)
        self.laufzeit_text = QLabel(frachtzeit.hinweis(self.lz))
        self.laufzeit_text.setWordWrap(True)
        self.laufzeit_text.setStyleSheet("color: gray;")
        form.addRow("", self.laufzeit_text)
        self._freigeben(self.mit_termin.isChecked())
        lay.addLayout(form)
        self.frueh = frueh
        if frueh is not None and frueh.datum is not None:
            from . import terminplan
            t = QLabel(terminplan.text(frueh, vorschlag) + " Frei Haus frühestens "
                       f"{frachtzeit.text_datum(frachtzeit.frei_haus(frueh.datum, self.lz.tage, land))}.")
            t.setWordWrap(True)
            if vorschlag < frueh.datum:
                t.setStyleSheet("color: #A33A00;")
            uebernehmen = QPushButton(f"Frühesten Termin übernehmen (ab Werk {frueh.datum.strftime('%d.%m.%Y')})")
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

    def _freigeben(self, an):
        self.termin.setEnabled(an)
        # ab Werk/Abholung: frei Haus ist dasselbe Datum, nur zur Anzeige
        self.frei_haus.setEnabled(an and self.lz.frei_haus and self.lz.tage > 0)

    def _ab_werk_geaendert(self):
        from . import frachtzeit
        if self._koppeln:
            self._koppeln = False
            self.frei_haus.setDate(QDate(frachtzeit.frei_haus(self.termin.date().toPython(), self.lz.tage, self.land)))
            self._koppeln = True

    def _frei_haus_geaendert(self):
        """Wunschtermin beim Kunden eingetragen: ab Werk rückwärts (F3a)."""
        from . import frachtzeit
        if self._koppeln:
            self._koppeln = False
            self.termin.setDate(QDate(frachtzeit.ab_werk(self.frei_haus.date().toPython(), self.lz.tage, self.land)))
            self._koppeln = True

    def frueh_uebernehmen(self):
        self.mit_termin.setChecked(True)
        self.termin.setDate(QDate(self.frueh.datum))

    def werte(self):
        """(Auftragsnummer oder None, Liefertermin ab Werk als ISO-Datum oder None, frei Haus als ISO-Datum oder
        None)"""
        if not self.mit_termin.isChecked():
            return self.nummer.text().strip() or None, None, None
        return (self.nummer.text().strip() or None, self.termin.date().toPython().isoformat(),
                self.frei_haus.date().toPython().isoformat())

    def gewaehlte_schritte(self):
        return [n for n, c in self.schritte.items() if c.isChecked()]


def abfragen(parent, angebot, land=None, frueh=None, schritte=None, lz=None):
    """Fenster zeigen. Ergebnis: (Auftragsnummer, Liefertermin ab Werk, frei Haus) oder None (abgebrochen).
    schritte (Liste): gemerkte Schritte zum Anhaken; die Liste enthält danach die gewählten."""
    d = AuftragDialog(parent, angebot, land, frueh, schritte, lz)
    if d.exec() != QDialog.Accepted:
        return None
    if schritte is not None:
        schritte[:] = d.gewaehlte_schritte()
    return d.werte()
