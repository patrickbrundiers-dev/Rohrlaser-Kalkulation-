"""Nachfassen und Wiedervorlage (Plan A9), aufrufbar aus der Angebotsliste, der Startseite und dem Angebot.

„Nachfassen vermerken …“ trägt ein Nachfassen (Telefon, E-Mail, persönlich) in den Versandverlauf ein; das automatische
Nachfassen zählt dann neu. Eine E-Mail bereitet das Programm nicht vor (Patrick 24.10.: nur vermerken).

„Wiedervorlage …“ setzt ein freies Datum (oder keins); bis dahin ersetzt es das automatische Nachfassen."""
import datetime

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QLabel

from . import cockpit

WIE = ("Telefon", "E-Mail", "persönlich")


class NachfassDialog(QDialog):
    """Nachfassen vermerken: wie (Telefon, E-Mail, persönlich). Nach OK: self.ergebnis = 'vermerkt', self.wie,
    self.meldung (Statuszeile)."""

    def __init__(self, parent, kopf):
        super().__init__(parent)
        self.ergebnis, self.wie, self.meldung = None, None, ""
        self.setWindowTitle(f"Nachfassen vermerken – Angebot {kopf.get('nummer') or ''}".strip())
        form = QFormLayout(self)
        versandt, nachgefasst, _ = cockpit.verlauf(kopf)
        info = [f"Kunde: {kopf.get('kunde') or '–'}"]
        if versandt:
            info.append(f"verschickt am {versandt.strftime('%d.%m.%Y')}")
        if nachgefasst:
            info.append(f"zuletzt nachgefasst am {nachgefasst.strftime('%d.%m.%Y')}")
        k = QLabel(" · ".join(info) + "<br>Heute beim Kunden nachgefasst; die Tage bis zur nächsten Wiedervorlage "
                   "zählen ab heute neu.")
        k.setWordWrap(True)
        form.addRow(k)
        self.wie_auswahl = QComboBox()
        self.wie_auswahl.addItems(WIE)
        form.addRow("Wie", self.wie_auswahl)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Vermerken")
        knoepfe.accepted.connect(self.vermerken)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)

    def vermerken(self):
        self.ergebnis, self.wie = "vermerkt", self.wie_auswahl.currentText()
        self.meldung = f"Nachfassen ({self.wie}) vermerkt."
        self.accept()


class WiedervorlageDialog(QDialog):
    """Datum der Wiedervorlage; self.am = gewähltes Datum oder None (keine Wiedervorlage)."""

    def __init__(self, parent, nummer, am=None, vorschlag=None):
        super().__init__(parent)
        self.setWindowTitle(f"Wiedervorlage – Angebot {nummer or ''}".strip())
        self.am = am
        form = QFormLayout(self)
        t = QLabel("An diesem Tag steht das Angebot auf der Startseite unter <b>Wiedervorlage</b> und im Filter "
                   "<i>Wiedervorlage fällig</i>; bis dahin ruht das automatische Nachfassen.")
        t.setWordWrap(True)
        form.addRow(t)
        self.datum = QDateEdit()
        self.datum.setCalendarPopup(True)
        self.datum.setDisplayFormat("dd.MM.yyyy")
        d = am or vorschlag or datetime.date.today() + datetime.timedelta(days=7)
        self.datum.setDate(QDate(d.year, d.month, d.day))
        form.addRow("Wiedervorlage am", self.datum)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.keine = knoepfe.addButton("Keine Wiedervorlage", QDialogButtonBox.ResetRole)
        self.keine.setVisible(am is not None)
        self.keine.clicked.connect(self._keine)
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)

    def _ok(self):
        self.am = self.datum.date().toPython()
        self.accept()

    def _keine(self):
        self.am = None
        self.accept()


def _angebot(f, angebot_id, was):
    """Kopf des Angebots oder None (nicht da / Angebot eines Kollegen, dann mit Meldung)."""
    a = f.db.angebot(angebot_id)
    if not a:
        return None
    if a.get("fremd"):
        f.meldung(f"Angebot {a['nummer']} gehört {a['fremd']}: {was} kann nur {a['fremd']}.", fehler=True)
        return None
    return a


def nachfassen_dialog(f, angebot_id, parent=None, dialog=None):
    """Dialog Nachfassen vermerken; f = Hauptfenster. dialog(d) bedient den Dialog statt exec (Tests).
    Ergebnis: der Dialog oder None."""
    a = _angebot(f, angebot_id, "Nachfassen")
    if a is None:
        return None
    d = NachfassDialog(parent or f, a)
    (dialog(d) if dialog else d.exec())
    if d.ergebnis:
        f.db.nachgefasst_merken(angebot_id, d.wie)
        f.nachfassen_geaendert(angebot_id)
    if d.meldung:
        f.meldung(d.meldung)
    return d


def wiedervorlage_dialog(f, angebot_id, parent=None, dialog=None):
    """Dialog Wiedervorlage; dialog(d) bedient ihn statt exec (Tests). Ergebnis: der Dialog oder None."""
    a = _angebot(f, angebot_id, "die Wiedervorlage setzen")
    if a is None:
        return None
    _, _, am = cockpit.verlauf(a)
    d = WiedervorlageDialog(parent or f, a.get("nummer"), am)
    (dialog(d) if dialog else d.exec())
    if d.result() == QDialog.Accepted and d.am != am:
        f.db.wiedervorlage_setzen(angebot_id, d.am)
        f.nachfassen_geaendert(angebot_id)
        f.meldung(f"Angebot {a['nummer']}: Wiedervorlage " +
                  (f"am {d.am.strftime('%d.%m.%Y')}." if d.am else "entfernt."))
    return d
