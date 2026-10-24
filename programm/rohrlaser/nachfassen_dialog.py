"""Nachfassen und Wiedervorlage (Plan A9), aufrufbar aus der Angebotsliste, der Startseite und dem Angebot.

„Nachfassen …“ zeigt den E-Mail-Entwurf an den Kunden (Vorlage aus den Einstellungen, das zuletzt verschickte
Angebots-PDF auf Wunsch als Anhang). Wie bei der Materialanfrage sendet das Programm nie selbst: Outlook zeigt die
E-Mail, sonst entsteht eine E-Mail-Datei. Danach steht „nachgefasst am“ im Versandverlauf, und das automatische
Nachfassen zählt neu. „Nur vermerken“ trägt ein Nachfassen per Telefon o. Ä. ein.

„Wiedervorlage …“ setzt ein freies Datum (oder keins); bis dahin ersetzt es das automatische Nachfassen."""
import datetime

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout)

from . import cockpit, nachfassen
from . import materialanfrage as ma

WIE = ("Telefon", "E-Mail", "persönlich")      # Auswahl bei „Nur vermerken“


class NachfassDialog(QDialog):
    """Nach einer Aktion: self.ergebnis ('outlook', 'eml', 'vermerkt' oder None), self.wie (für den Vermerk),
    self.meldung (Statuszeile). ausfuehren ersetzt den Outlook-Aufruf (Tests)."""

    def __init__(self, parent, kopf, kunde, einst, gueltig_bis, anhang, eml_ziel, oeffnen, ausfuehren=None):
        super().__init__(parent)
        self.einst, self.anhang, self.eml_ziel = einst, anhang, eml_ziel
        self.oeffnen, self.ausfuehren = oeffnen, ausfuehren
        self.ergebnis, self.wie, self.meldung = None, None, ""
        self.setWindowTitle(f"Nachfassen – Angebot {kopf.get('nummer') or ''}".strip())
        self.resize(640, 520)
        lay = QVBoxLayout(self)
        versandt, nachgefasst, _ = cockpit.verlauf(kopf)
        info = [f"Kunde: {kopf.get('kunde') or '–'}"]
        if versandt:
            info.append(f"verschickt am {versandt.strftime('%d.%m.%Y')}")
        if nachgefasst:
            info.append(f"zuletzt nachgefasst am {nachgefasst.strftime('%d.%m.%Y')}")
        k = QLabel(" · ".join(info))
        k.setWordWrap(True)
        lay.addWidget(k)
        form = QFormLayout()
        self.an = QLineEdit(((kunde or {}).get("email") or "").strip())
        self.an.setPlaceholderText("E-Mail-Adresse des Kunden (im Kundenstamm leer)")
        form.addRow("An", self.an)
        self.betreff = QLineEdit(nachfassen.betreff(kopf, kunde, einst, gueltig_bis))
        form.addRow("Betreff", self.betreff)
        lay.addLayout(form)
        self.text = QPlainTextEdit(nachfassen.text(kopf, kunde, einst, gueltig_bis))
        lay.addWidget(self.text, 1)
        self.mit_pdf = QCheckBox(f"Angebots-PDF anhängen ({anhang.name})" if anhang else
                                 "Angebots-PDF anhängen (keins in der Ablage)")
        self.mit_pdf.setChecked(bool(anhang))
        self.mit_pdf.setEnabled(bool(anhang))
        lay.addWidget(self.mit_pdf)
        hinweis = QLabel("Das Programm sendet nicht: Outlook zeigt die E-Mail, gesendet wird dort. Danach steht "
                         "„nachgefasst“ im Versandverlauf.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color: #5F6B7A;")
        lay.addWidget(hinweis)
        knoepfe = QHBoxLayout()
        self.outlook_knopf = QPushButton("In Outlook öffnen")
        self.outlook_knopf.setObjectName("primaer")
        self.outlook_knopf.clicked.connect(lambda: self.in_outlook())
        self.eml_knopf = QPushButton("Als E-Mail-Datei speichern")
        self.eml_knopf.clicked.connect(lambda: self.als_datei())
        self.wie_auswahl = QComboBox()
        self.wie_auswahl.addItems(WIE)
        self.vermerk_knopf = QPushButton("Nur vermerken")
        self.vermerk_knopf.setToolTip("Ohne E-Mail nachgefasst (z. B. angerufen): nur im Versandverlauf eintragen")
        self.vermerk_knopf.clicked.connect(lambda: self.vermerken())
        zu = QPushButton("Abbrechen")
        zu.clicked.connect(self.reject)
        for b in (self.outlook_knopf, self.eml_knopf):
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        knoepfe.addWidget(self.wie_auswahl)
        knoepfe.addWidget(self.vermerk_knopf)
        knoepfe.addWidget(zu)
        lay.addLayout(knoepfe)

    def mail(self, signatur=False):
        text = self.text.toPlainText()
        return (self.an.text().strip(), self.betreff.text().strip(),
                ma.mit_signatur(text, ma.signatur(self.einst)) if signatur else text,
                [self.anhang] if self.anhang and self.mit_pdf.isChecked() else [])

    def als_datei(self, oeffnen=True):
        if self.eml_ziel is None:
            return None
        pfad = ma.eml(self.eml_ziel, *self.mail(signatur=True))
        if oeffnen:
            self.oeffnen(pfad)
        self.ergebnis, self.wie = "eml", "E-Mail"
        self.meldung = f"E-Mail-Datei gespeichert: {pfad} – im Mailprogramm prüfen und senden."
        self.accept()
        return pfad

    def in_outlook(self):
        aus_outlook = ma.outlook_signatur(self.einst)
        an, betreff, text, anhaenge = self.mail(signatur=not aus_outlook)
        ok, fehler = ma.outlook_oeffnen(an, betreff, text, anhaenge, ausfuehren=self.ausfuehren,
                                        signatur_=aus_outlook)
        if ok:
            self.ergebnis, self.wie = "outlook", "E-Mail"
            self.meldung = "Nachfassen: E-Mail in Outlook geöffnet – bitte dort prüfen und senden."
            self.accept()
            return True
        pfad = self.als_datei()
        self.meldung = (f"Outlook ließ sich nicht ansteuern ({fehler}). Ersatz: E-Mail-Datei {pfad} "
                        "im Standard-Mailprogramm geöffnet.")
        return False

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


def nachfassen_dialog(f, angebot_id, parent=None, dialog=None, ausfuehren=None):
    """Dialog Nachfassen für das Angebot; f = Hauptfenster. dialog(d) bedient den Dialog statt exec (Tests).
    Ergebnis: der Dialog oder None."""
    from . import ausgabe
    a = _angebot(f, angebot_id, "Nachfassen")
    if a is None:
        return None
    kunde = f.db.kunde(a["kundennr"]) if a.get("kundennr") else None
    from .angebot_fenster import gueltig_bis
    try:
        ablage = f.ablage()
    except OSError:
        ablage = None
    datei = nachfassen.letztes_pdf(a)
    anhang = ablage / datei if ablage and datei and (ablage / datei).is_file() else None
    ziel = ablage / (ausgabe.dateiname(a, "Nachfassen") + ".eml") if ablage else None
    d = NachfassDialog(parent or f, a, kunde, f.db.einstellungen(), gueltig_bis(a, f.db.einstellung("gueltigkeit")),
                       anhang, ziel, f.datei_oeffnen, ausfuehren)
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
