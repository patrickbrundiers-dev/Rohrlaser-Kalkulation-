"""Einstellungen → E-Mail-Vorlagen (Materialanfragen über Outlook, Patrick 13.11.2026).

Links die Vorlagen (Materialanfrage und Materialbestellung), rechts Name, Art, Materialgruppe, Betreff, Anrede, Text,
Grußformel, Signatur und „Materialliste als PDF anhängen“, darunter die Vorschau mit Beispieldaten. Anlegen,
Kopieren, Speichern, Löschen. „Standard“ ohne eigenen Datensatz kommt aus den Einstellungen der Materialanfrage;
gespeichert wird er als eigene Vorlage „Standard“, Löschen kehrt zur Einstellung zurück."""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QVBoxLayout,
                               QWidget)
from PySide6.QtCore import Qt

from . import materialanfragen as mv

PLATZHALTER = ("{anrede} {ansprechpartner} {lieferant} {projekt} {angebot} {kunde} {kennung} {materialdaten} "
               "{liefertermin} {gueltigkeit} {info} {datum} {gruss} {absender}")
BEISPIEL = dict(angebot="A-2026-0100", kunde="Muster GmbH", projekt="P-4711", kennung="MA A-2026-0100/1",
                positionen="- 4 Stangen Quadratrohr 40 x 40 x 3, S235JRH, à 6.000 mm (ca. 85 kg)\n"
                           "- 20 Stück Lasche (Art.-Nr. L-17), 120 x 60 x 5 mm, S235JR",
                liefertermin="KW 49", gueltigkeit="31.12.2026", info="", datum="13.11.2026", absender="")


class MailVorlagenSeite(QWidget):
    titel = "E-Mail-Vorlagen"
    schluessel = "e_mail_vorlagen"      # Navigation der Einstellungen (einstellungen_nav.GRUPPEN)

    def __init__(self, db, meldung=None):
        super().__init__()
        self.db, self.meldung = db, meldung or (lambda *a, **k: None)
        self.aktuell = None             # Name der gewählten Vorlage
        lay = QVBoxLayout(self)
        hinweis = QLabel("Vorlagen für Materialanfragen und Materialbestellungen an Lieferanten. Platzhalter: "
                         + PLATZHALTER + ". Fehlen {anrede} oder {gruss} im Text, stehen Anrede vorn und Gruß hinten; "
                         "die Kennung der Anfrage kommt immer in den Betreff. Signatur leer = Signatur aus Outlook "
                         "bzw. den Einstellungen. Gilt für alle Arbeitsplätze.")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)
        teiler = QSplitter(Qt.Horizontal)
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.setContentsMargins(0, 0, 0, 0)
        self.vorlagen_liste = QListWidget()
        self.vorlagen_liste.currentItemChanged.connect(lambda it, _: self._zeigen(it.data(Qt.UserRole) if it else None))
        ll.addWidget(self.vorlagen_liste, 1)
        knoepfe = QHBoxLayout()
        self.neu_knopf = QPushButton("Neue Vorlage")
        self.neu_knopf.clicked.connect(lambda: self.neu())
        self.kopie_knopf = QPushButton("Kopieren")
        self.kopie_knopf.clicked.connect(lambda: self.kopieren())
        self.loeschen_knopf = QPushButton("Löschen")
        self.loeschen_knopf.clicked.connect(lambda: self.loeschen())
        for b in (self.neu_knopf, self.kopie_knopf, self.loeschen_knopf):
            knoepfe.addWidget(b)
        ll.addLayout(knoepfe)
        teiler.addWidget(links)

        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        rl.setContentsMargins(0, 0, 0, 0)
        form = QFormLayout()
        self.name = QLineEdit()
        self.art = QComboBox()
        self.art.addItems([mv.ANFRAGE, mv.BESTELLUNG])
        self.gruppe = QComboBox()
        self.betreff = QLineEdit()
        self.anrede = QLineEdit()
        self.anrede.setPlaceholderText("z. B. Sehr geehrte Damen und Herren (leer = steht im Text)")
        self.text = QPlainTextEdit()
        self.gruss = QLineEdit()
        self.gruss.setPlaceholderText("z. B. Mit freundlichen Grüßen")
        self.signatur = QPlainTextEdit()
        self.signatur.setMaximumHeight(70)
        self.signatur.setPlaceholderText("leer = Signatur aus Outlook bzw. Einstellungen → Materialanfrage")
        self.pdf = QCheckBox("Materialliste als PDF anhängen")
        form.addRow("Vorlagenname", self.name)
        form.addRow("Art", self.art)
        form.addRow("Materialgruppe", self.gruppe)
        form.addRow("Betreff", self.betreff)
        form.addRow("Standard-Anrede", self.anrede)
        form.addRow("E-Mail-Text", self.text)
        form.addRow("Standard-Grußformel", self.gruss)
        form.addRow("Signatur", self.signatur)
        form.addRow("", self.pdf)
        rl.addLayout(form, 3)
        unten = QHBoxLayout()
        self.speichern_knopf = QPushButton("Speichern")
        self.speichern_knopf.setObjectName("primaer")
        self.speichern_knopf.clicked.connect(lambda: self.speichern())
        unten.addStretch(1)
        unten.addWidget(self.speichern_knopf)
        rl.addLayout(unten)
        rl.addWidget(QLabel("Vorschau mit Beispieldaten:"))
        self.vorschau = QPlainTextEdit()
        self.vorschau.setReadOnly(True)
        rl.addWidget(self.vorschau, 2)
        for w in (self.betreff, self.anrede, self.gruss):
            w.textChanged.connect(self._vorschau)
        self.text.textChanged.connect(self._vorschau)
        self.signatur.textChanged.connect(self._vorschau)
        teiler.addWidget(rechts)
        teiler.setSizes([260, 700])
        lay.addWidget(teiler, 1)
        self.neu_laden()

    # ------------------------------------------------------------------ Daten
    def _einst(self):
        return self.db.einstellungen()

    def vorlagen(self):
        z = self.db.zeilen("mail_vorlagen")
        return mv.vorlagen(z, self._einst()) + mv.vorlagen(z, self._einst(), bestellung=True)

    def neu_laden(self, waehlen=None):
        waehlen = waehlen or self.aktuell
        self.gruppe.clear()
        self.gruppe.addItems([""] + [z["name"] for z in self.db.zeilen("materialgruppen") if z.get("name")])
        self.vorlagen_liste.blockSignals(True)
        self.vorlagen_liste.clear()
        for v in self.vorlagen():
            it = QListWidgetItem(f"{v['name']}" + (" (aus den Einstellungen)" if v.get("standard") else "")
                                 + ("" if v.get("art", mv.ANFRAGE) == mv.ANFRAGE else "  · Bestellung"))
            it.setData(Qt.UserRole, v["name"])
            self.vorlagen_liste.addItem(it)
        self.vorlagen_liste.blockSignals(False)
        namen = [self.vorlagen_liste.item(i).data(Qt.UserRole) for i in range(self.vorlagen_liste.count())]
        self.vorlagen_liste.setCurrentRow(namen.index(waehlen) if waehlen in namen else 0)

    def _vorlage(self, name):
        return next((v for v in self.vorlagen() if v["name"] == name), None)

    def _zeigen(self, name):
        v = self._vorlage(name) or {}
        self.aktuell = name
        self.name.setText(v.get("name") or "")
        self.art.setCurrentText(v.get("art") or mv.ANFRAGE)
        self.gruppe.setCurrentText(v.get("materialgruppe") or "")
        self.betreff.setText(v.get("betreff") or "")
        self.anrede.setText(v.get("anrede") or "")
        self.text.setPlainText(v.get("text") or "")
        self.gruss.setText(v.get("gruss") or "")
        self.signatur.setPlainText(v.get("signatur") or "")
        self.pdf.setChecked((v.get("pdf") or "ja") != "nein" if not v.get("standard") else False)
        self.loeschen_knopf.setEnabled(bool(v) and not v.get("standard"))
        self._vorschau()

    def werte(self):
        return dict(name=self.name.text().strip(), art=self.art.currentText(),
                    materialgruppe=self.gruppe.currentText() or None, betreff=self.betreff.text().strip(),
                    anrede=self.anrede.text().strip(), text=self.text.toPlainText(), gruss=self.gruss.text().strip(),
                    signatur=self.signatur.toPlainText().strip(), pdf="ja" if self.pdf.isChecked() else "nein")

    def _vorschau(self, *_):
        v = self.werte()
        b = mv.betreff_aus(v, BEISPIEL, BEISPIEL["kennung"])
        werte = dict(BEISPIEL, positionen=BEISPIEL["positionen"] + "\n\n" + mv.zusatz_block("KW 49", "31.12.2026"))
        t = mv.text_aus(v, werte)
        if v["signatur"]:
            t = t.rstrip() + "\n" + v["signatur"]
        self.vorschau.setPlainText(f"Betreff: {b}\n\n{t}")

    # ------------------------------------------------------------------ Aktionen
    def _zeile(self, name):
        return next((z for z in self.db.zeilen("mail_vorlagen") if z.get("name") == name), None)

    def speichern(self):
        """Gewählte Vorlage speichern (neu oder geändert). Ergebnis: True."""
        v = self.werte()
        if not v["name"]:
            self.meldung("Bitte einen Vorlagennamen eingeben.", fehler=True)
            return False
        if not v["text"].strip():
            self.meldung("Bitte einen E-Mail-Text eingeben.", fehler=True)
            return False
        alt = self._zeile(self.aktuell) if self.aktuell else None
        try:
            if alt is None:
                if self._zeile(v["name"]) is not None:
                    raise ValueError(f"Vorlagenname '{v['name']}' gibt es schon.")
                self.db.neu("mail_vorlagen", v)
            else:
                for feld, wert in v.items():
                    if alt.get(feld) != wert:
                        self.db.aendern("mail_vorlagen", alt["id"], feld, wert)
        except ValueError as e:
            self.meldung(str(e), fehler=True)
            return False
        self.aktuell = v["name"]
        self.neu_laden(v["name"])
        self.meldung(f"Vorlage „{v['name']}“ gespeichert.")
        return True

    def _freier_name(self, basis):
        namen = {v["name"] for v in self.vorlagen()}
        n, name = 1, basis
        while name in namen:
            n += 1
            name = f"{basis} {n}"
        return name

    def neu(self):
        self.aktuell = None
        self.vorlagen_liste.clearSelection()
        self._zeigen(None)
        self.aktuell = None
        self.name.setText(self._freier_name("Neue Vorlage"))
        self.betreff.setText("Materialanfrage – {projekt}")
        self.anrede.setText("Sehr geehrte Damen und Herren")
        self.text.setPlainText("bitte erstellen Sie uns ein Angebot für folgendes Material:\n\n{materialdaten}\n\n"
                               "Bitte teilen Sie uns Ihren Preis sowie den frühestmöglichen Liefertermin mit.\n\n"
                               "Vielen Dank im Voraus.")
        self.gruss.setText("Mit freundlichen Grüßen")
        self.pdf.setChecked(True)
        self.loeschen_knopf.setEnabled(False)

    def kopieren(self):
        v = self.werte()
        self.aktuell = None
        self.name.setText(self._freier_name(f"{v['name'] or 'Vorlage'} Kopie"))
        self.loeschen_knopf.setEnabled(False)

    def loeschen(self, fragen=True):
        z = self._zeile(self.aktuell) if self.aktuell else None
        if z is None:
            return False
        if fragen and QMessageBox.question(self, "Vorlage löschen", f"Vorlage „{z['name']}“ löschen?") \
                != QMessageBox.Yes:
            return False
        self.db.loeschen("mail_vorlagen", [z["id"]])
        self.aktuell = None
        self.neu_laden()
        self.meldung(f"Vorlage „{z['name']}“ gelöscht.")
        return True
