"""Dialog 'Material per Outlook anfragen …' (Vorschau der Anfrage).

Die Materialanfrage wird nie vom Programm gesendet: 'In Outlook öffnen' zeigt die fertige E-Mail in Outlook, gesendet
wird dort mit einem Klick des Benutzers. Geht das nicht (kein klassisches Outlook), entsteht eine E-Mail-Datei."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from . import materialanfrage as ma


class AnfrageDialog(QDialog):
    """Vorschau der Materialanfrage. zeilen = materialanfrage.bedarf, lieferanten = {Name: E-Mail},
    eml_ziel = Pfad der E-Mail-Datei, oeffnen(pfad) öffnet Dateien, ausfuehren ersetzt den
    Outlook-Aufruf (Tests). Nach einer Aktion: self.meldung (Text für die Statuszeile), self.ergebnis
    ('outlook', 'eml' oder None)."""
    SPALTEN = ("Anfragen", "Material", "Stangen", "Lieferant", "Pos.")

    def __init__(self, parent, kopf, zeilen, k, einst, lieferanten, eml_ziel, oeffnen, ausfuehren=None):
        super().__init__(parent)
        self.kopf, self.zeilen, self.k, self.einst = kopf, zeilen, k, einst
        self.lieferanten, self.eml_ziel = lieferanten, eml_ziel
        self.oeffnen, self.ausfuehren = oeffnen, ausfuehren
        self.meldung, self.ergebnis, self._setzen = "", None, False
        self.text_von_hand = False
        self.setWindowTitle(f"Materialanfrage – Angebot {kopf.get('nummer') or ''}".strip())
        self.resize(900, 680)
        lay = QVBoxLayout(self)
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Anfrage an Lieferant:"))
        self.lieferant = QComboBox()
        namen = list(dict.fromkeys((z["lieferant"] or ma.OHNE_LIEFERANT) for z in zeilen))
        self.lieferant.addItems(namen + [n for n in sorted(lieferanten) if n not in namen])
        self.lieferant.currentTextChanged.connect(self._lieferant_gewaehlt)
        oben.addWidget(self.lieferant, 1)
        lay.addLayout(oben)

        self.tabelle = QTableWidget(len(zeilen), len(self.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(self.SPALTEN)
        self.tabelle.verticalHeader().setVisible(False)
        self.tabelle.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.mengen = []
        for r, z in enumerate(zeilen):
            an = QTableWidgetItem()
            an.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            an.setCheckState(Qt.Checked)
            self.tabelle.setItem(r, 0, an)
            self.tabelle.setItem(r, 1, QTableWidgetItem(z["text"]))
            m = QSpinBox()
            m.setRange(1, 100000)
            m.setValue(z["stangen"])
            m.valueChanged.connect(self._neu)
            self.mengen.append(m)
            self.tabelle.setCellWidget(r, 2, m)
            self.tabelle.setItem(r, 3, QTableWidgetItem(z["lieferant"] or "–"))
            self.tabelle.setItem(r, 4, QTableWidgetItem(", ".join(z["pos"])))
        kopfzeile = self.tabelle.horizontalHeader()
        for i, b in enumerate((70, 0, 75, 150, 90)):
            if b:
                self.tabelle.setColumnWidth(i, b)
        kopfzeile.setSectionResizeMode(1, QHeaderView.Stretch)
        self.tabelle.itemChanged.connect(self._neu)
        self.tabelle.setMaximumHeight(170)
        lay.addWidget(self.tabelle)

        form = QFormLayout()
        self.an = QLineEdit()
        self.an.setPlaceholderText("E-Mail-Adresse (Lieferanten unter Zukaufartikel → Lieferanten pflegen)")
        self.betreff = QLineEdit(ma.betreff(kopf))
        form.addRow("An", self.an)
        form.addRow("Betreff", self.betreff)
        lay.addLayout(form)
        self.text = QPlainTextEdit()
        self.text.textChanged.connect(self._text_geaendert)
        lay.addWidget(self.text, 1)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet("color: #7A5A00;")
        lay.addWidget(self.hinweis)
        knoepfe = QHBoxLayout()
        self.outlook_knopf = QPushButton("In Outlook öffnen")
        self.outlook_knopf.setObjectName("primaer")
        self.outlook_knopf.setToolTip("Outlook zeigt die fertige E-Mail; gesendet wird erst mit 'Senden' in Outlook")
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
        self._lieferant_gewaehlt(self.lieferant.currentText())

    # ------------------------------------------------------------------ Inhalt
    def _lieferant_gewaehlt(self, name):
        """Zeilen dieses Lieferanten anhaken (ohne Lieferant: die Zeilen ohne), E-Mail-Adresse eintragen."""
        self._setzen = True
        for r, z in enumerate(self.zeilen):
            passt = (z["lieferant"] or ma.OHNE_LIEFERANT) == name
            self.tabelle.item(r, 0).setCheckState(Qt.Checked if passt else Qt.Unchecked)
        self.an.setText(self.lieferanten.get(name, ""))
        self._setzen = False
        self.text_von_hand = False
        self._neu()

    def gewaehlt(self):
        """Indizes der angehakten Zeilen."""
        return [r for r in range(len(self.zeilen)) if self.tabelle.item(r, 0).checkState() == Qt.Checked]

    def _neu(self, *_):
        if self._setzen:
            return
        auswahl = self.gewaehlt()
        if not self.text_von_hand:
            self._setzen = True
            self.text.setPlainText(ma.anschreiben(self.kopf, [self.zeilen[r] for r in auswahl], self.einst, self.k,
                                                  {i: self.mengen[r].value() for i, r in enumerate(auswahl)}))
            self._setzen = False
        hinweise = []
        if not auswahl:
            hinweise.append("Keine Zeile angehakt.")
        if not self.an.text().strip():
            hinweise.append("Ohne E-Mail-Adresse: Empfänger in Outlook eintragen.")
        self.hinweis.setText(" ".join(hinweise))
        self.outlook_knopf.setEnabled(bool(auswahl))
        self.eml_knopf.setEnabled(bool(auswahl))

    def _text_geaendert(self):
        if not self._setzen:
            self.text_von_hand = True

    def mail(self):
        """(An, Betreff, Text) wie sie in die E-Mail gehen."""
        return self.an.text().strip(), self.betreff.text().strip(), self.text.toPlainText()

    # ------------------------------------------------------------------ Aktionen
    def als_datei(self, oeffnen=True):
        """E-Mail-Datei (.eml) in der Ablage speichern und mit dem Standard-Mailprogramm öffnen."""
        if self.eml_ziel is None:
            return None
        pfad = ma.eml(self.eml_ziel, *self.mail())
        if oeffnen:
            self.oeffnen(pfad)
        self.ergebnis = "eml"
        self.meldung = f"E-Mail-Datei gespeichert: {pfad} – im Mailprogramm prüfen und senden."
        return pfad

    def in_outlook(self):
        """E-Mail in Outlook anzeigen (nicht senden); geht das nicht, E-Mail-Datei als Ersatz."""
        ok, fehler = ma.outlook_oeffnen(*self.mail(), ausfuehren=self.ausfuehren)
        if ok:
            self.ergebnis = "outlook"
            self.meldung = "E-Mail in Outlook geöffnet – bitte dort prüfen und senden."
            self.accept()
            return True
        pfad = self.als_datei()
        self.meldung = (f"Outlook ließ sich nicht ansteuern ({fehler}). Ersatz: E-Mail-Datei {pfad} "
                        "im Standard-Mailprogramm geöffnet.")
        self.accept()
        return False
