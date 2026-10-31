"""Fenster „Angebot per E-Mail“ (Vorschlag V1, 31.10.2026, angebot_mail.py).

Zeigt Empfänger, Betreff, Text und Anhang; „In Outlook öffnen“ zeigt die fertige E-Mail in Outlook (gesendet wird nur
dort), ohne Outlook entsteht eine E-Mail-Datei. Liegt die Anfrage-Mail als .msg im Angebotsordner, ist „Als Antwort
auf die Anfrage-Mail“ angehakt."""
from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from . import angebot_mail as am
from . import materialanfrage as ma


class AngebotMailDialog(QDialog):
    """kopf/kunde/einst des Angebots, pdf = Pfad des Angebots-PDF, anfrage = (Pfad, mail.Mail) der neuesten
    Anfrage-Mail oder None, eml_ziel = Pfad der Ersatz-Datei, oeffnen(pfad) öffnet Dateien, ausfuehren ersetzt den
    Outlook-Aufruf (Tests). Danach: self.ergebnis ('outlook', 'eml' oder None), self.meldung, self.eintrag
    (für den Versandverlauf)."""

    def __init__(self, parent, kopf, kunde, einst, pdf, anfrage, eml_ziel, oeffnen, ausfuehren=None, netto=None):
        super().__init__(parent)
        self.kopf, self.kunde, self.einst, self.pdf = kopf, kunde, einst, Path(pdf)
        self.anfrage_pfad, self.anfrage = anfrage if anfrage else (None, None)
        self.eml_ziel, self.oeffnen, self.ausfuehren = eml_ziel, oeffnen, ausfuehren
        self.ergebnis, self.meldung, self.eintrag = None, "", None
        self.setWindowTitle(f"Angebot per E-Mail – {kopf.get('nummer') or ''}".strip(" –"))
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        self.antwort = QCheckBox()
        if self.anfrage is not None:
            wann = self.anfrage.datum or getattr(self.anfrage, "datei_zeit", None)
            self.antwort.setText(f"Als Antwort auf die Anfrage-Mail von {self.anfrage.absender or 'unbekannt'}"
                                 + (f" vom {wann.strftime('%d.%m.%Y')}" if wann else "")
                                 + f": „{self.anfrage.betreff or 'ohne Betreff'}“")
            moeglich = am.antwort_moeglich(self.anfrage_pfad)
            self.antwort.setChecked(moeglich)
            self.antwort.setEnabled(moeglich)
            if not moeglich:
                self.antwort.setToolTip("Nur eine Outlook-Mail (.msg) lässt sich beantworten; aus einer .eml wird "
                                        "eine neue E-Mail an den Absender.")
            self.antwort.toggled.connect(self._betreff_neu)
            lay.addWidget(self.antwort)
        else:
            self.antwort.setVisible(False)
        form = QFormLayout()
        self.an = QLineEdit(am.empfaenger(kunde, self.anfrage))
        self.an.setPlaceholderText("E-Mail-Adresse (Stammdaten → Kunden, Spalte E-Mail)")
        self.betreff = QLineEdit()
        form.addRow("An", self.an)
        form.addRow("Betreff", self.betreff)
        form.addRow("Anhang", QLabel(self.pdf.name))
        lay.addLayout(form)
        self.text = QPlainTextEdit(am.text(kopf, einst, kunde, netto))
        lay.addWidget(self.text, 1)
        sig = QLabel("Signatur: setzt Outlook (Standardsignatur); in der E-Mail-Datei die eigene Signatur aus den "
                     "Einstellungen." if ma.outlook_signatur(einst) else
                     "Signatur: eigene Signatur aus den Einstellungen (Mein Arbeitsplatz → E-Mail-Signatur).")
        sig.setWordWrap(True)
        lay.addWidget(sig)
        knoepfe = QHBoxLayout()
        self.outlook_knopf = QPushButton("In Outlook öffnen")
        self.outlook_knopf.setObjectName("primaer")
        self.outlook_knopf.setToolTip("Outlook zeigt die fertige E-Mail mit dem Angebot; gesendet wird erst mit "
                                      "„Senden“ in Outlook")
        self.outlook_knopf.clicked.connect(lambda: self.in_outlook())
        self.eml_knopf = QPushButton("Als E-Mail-Datei speichern")
        self.eml_knopf.clicked.connect(lambda: self.als_datei())
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.reject)
        knoepfe.addWidget(QLabel("Gesendet wird nur in Outlook, nie vom Programm."))
        knoepfe.addStretch(1)
        for b in (self.outlook_knopf, self.eml_knopf, zu):
            knoepfe.addWidget(b)
        lay.addLayout(knoepfe)
        self._betreff_neu()

    def _betreff_neu(self, *_):
        self.betreff.setText(am.betreff(self.kopf, self.einst, self.anfrage if self.anfrage is not None and
                                        (self.antwort.isChecked() or not am.antwort_moeglich(self.anfrage_pfad))
                                        else None))

    def als_antwort(self):
        return self.anfrage is not None and self.antwort.isChecked() and am.antwort_moeglich(self.anfrage_pfad)

    def mail(self, signatur=False):
        text = self.text.toPlainText()
        return (self.an.text().strip(), self.betreff.text().strip(),
                ma.mit_signatur(text, ma.signatur(self.einst)) if signatur else text)

    def als_datei(self, oeffnen=True):
        """E-Mail-Datei (.eml) mit dem PDF im Angebotsordner speichern und im Standard-Mailprogramm öffnen."""
        if self.eml_ziel is None:
            return None
        pfad = ma.eml(self.eml_ziel, *self.mail(signatur=True), anhaenge=(self.pdf,))
        if oeffnen:
            self.oeffnen(pfad)
        self.ergebnis = "eml"
        self.eintrag = am.eintrag(self.an.text().strip(), datei=Path(pfad).name)
        self.meldung = f"E-Mail-Datei gespeichert: {pfad} – im Mailprogramm prüfen und senden."
        return pfad

    def in_outlook(self):
        """E-Mail in Outlook anzeigen (nicht senden); geht das nicht, E-Mail-Datei als Ersatz."""
        aus_outlook = ma.outlook_signatur(self.einst)
        antwort = self.anfrage_pfad if self.als_antwort() else None
        ok, fehler = ma.outlook_oeffnen(*self.mail(signatur=not aus_outlook), anhaenge=(self.pdf,),
                                        ausfuehren=self.ausfuehren, signatur_=aus_outlook, antwort=antwort)
        if ok:
            self.ergebnis = "outlook"
            self.eintrag = am.eintrag(self.an.text().strip(), antwort=bool(antwort))
            self.meldung = "Angebot in Outlook geöffnet – bitte dort prüfen und senden."
            self.accept()
            return True
        pfad = self.als_datei()
        self.meldung = (f"Outlook ließ sich nicht ansteuern ({fehler}). Ersatz: E-Mail-Datei {pfad} "
                        "im Standard-Mailprogramm geöffnet.")
        self.accept()
        return False
