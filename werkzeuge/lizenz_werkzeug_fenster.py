"""Fenster des Lizenz-Werkzeugs (nur bei Patrick): Schlüssel erzeugen, Lizenz ausstellen, Register, sperren.

Start: Doppelklick auf Lizenz-Werkzeug.exe bzw. python werkzeuge/lizenz_werkzeug.py ohne Befehl. Die Logik steht
in lizenz_werkzeug.py; hier nur die Bedienung. Fehler meldet die Logik als SystemExit mit Text.
"""
import datetime
import sys
from pathlib import Path

from PySide6.QtCore import QDate, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

import lizenz_werkzeug as wz
from rohrlaser import lizenz

ARTEN = (("Benutzer", "benutzer"), ("Testlizenz (Aufdruck TESTVERSION)", "test"), ("Admin (unbefristet)", "admin"))


class Fenster(QWidget):
    def __init__(self, ordner):
        super().__init__()
        self.ordner = Path(ordner)
        self.setWindowTitle("Lizenz-Werkzeug – Rohrlaser Angebotskalkulation")
        self.resize(980, 720)
        lay = QVBoxLayout(self)
        # Schlüssel
        kopf = QHBoxLayout()
        self.ordner_text = QLabel()
        self.ordner_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
        kopf.addWidget(self.ordner_text, 1)
        for text, ziel in (("Ordner öffnen", self.ordner_oeffnen), ("Schlüssel erzeugen …", self.schluessel),
                           ("Update-Schlüssel …", self.update_schluessel)):
            b = QPushButton(text)
            b.clicked.connect(ziel)
            kopf.addWidget(b)
            if text.startswith("Schlüssel"):
                self.schluessel_knopf = b
        lay.addLayout(kopf)
        # Ausstellen
        box = QGroupBox("Lizenz ausstellen")
        form = QFormLayout(box)
        self.art = QComboBox()
        for text, wert in ARTEN:
            self.art.addItem(text, wert)
        self.art.currentIndexChanged.connect(self.art_gewechselt)
        self.inhaber = QLineEdit()
        self.firma = QLineEdit()
        self.bis = QDateEdit()
        self.bis.setCalendarPopup(True)
        self.bis.setDisplayFormat("dd.MM.yyyy")
        self.rechner = QPlainTextEdit()
        self.rechner.setPlaceholderText("Rechner-IDs, eine je Zeile (RL-XXXX-XXXX-XXXX-XXXX, aus Hilfe → Lizenz …)")
        self.rechner.setMaximumHeight(80)
        self.beliebig = QCheckBox("beliebiger Rechner (portabel an mehreren PCs)")
        self.beliebig.toggled.connect(lambda an: self.rechner.setEnabled(not an))
        self.hinweis = QLineEdit()
        erstellen = QPushButton("Lizenz erstellen …")
        erstellen.clicked.connect(self.erstellen)
        form.addRow("Art:", self.art)
        form.addRow("Inhaber:", self.inhaber)
        form.addRow("Firma:", self.firma)
        form.addRow("Gültig bis:", self.bis)
        form.addRow("Rechner:", self.rechner)
        form.addRow("", self.beliebig)
        form.addRow("Hinweis:", self.hinweis)
        form.addRow("", erstellen)
        lay.addWidget(box)
        # Register
        box = QGroupBox("Ausgestellte Lizenzen (lizenzen.csv)")
        bl = QVBoxLayout(box)
        self.tabelle = QTableWidget(0, len(wz.SPALTEN))
        self.tabelle.setHorizontalHeaderLabels(["Lizenz-ID", "Art", "Inhaber", "Firma", "Rechner", "Ausgestellt",
                                                "Gültig bis", "Gesperrt", "Datei"])
        self.tabelle.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabelle.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabelle.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        bl.addWidget(self.tabelle, 1)
        zeile = QHBoxLayout()
        for text, ziel in (("Markierte sperren …", self.sperren), ("Lizenzdatei prüfen …", self.pruefen),
                           ("Aktualisieren", self.neu_laden)):
            b = QPushButton(text)
            b.clicked.connect(ziel)
            zeile.addWidget(b)
        zeile.addStretch(1)
        bl.addLayout(zeile)
        lay.addWidget(box, 1)
        self.art_gewechselt()
        self.neu_laden()

    # ---------------------------------------------------------------- Hilfen
    def passwort(self, titel="Passwort des privaten Schlüssels"):
        pw, ok = QInputDialog.getText(self, titel, "Passwort:", QLineEdit.Password)
        return pw.encode("utf-8") if ok and pw else None

    def fehler(self, e):
        QMessageBox.warning(self, "Lizenz-Werkzeug", str(e))

    def schluessel_da(self):
        try:
            return wz.aktueller_schluessel(self.ordner)
        except SystemExit:
            return None

    def neu_laden(self):
        sid = self.schluessel_da()
        self.ordner_text.setText(f"Lizenzordner: {self.ordner}<br>Schlüssel: "
                                 + (f"<b>{sid}</b> vorhanden" if sid else "<b style='color:#B42318'>noch keiner – "
                                                                          "zuerst „Schlüssel erzeugen …“</b>"))
        self.schluessel_knopf.setEnabled(not sid)
        zeilen = sorted(wz.register_lesen(self.ordner), key=lambda z: z["gueltig_bis"])
        self.tabelle.setRowCount(len(zeilen))
        for i, z in enumerate(zeilen):
            for j, s in enumerate(wz.SPALTEN):
                self.tabelle.setItem(i, j, QTableWidgetItem(z.get(s) or ""))

    def art_gewechselt(self):
        art = self.art.currentData()
        heute = datetime.date.today()
        bis = (wz.monate_spaeter(heute, lizenz.STANDARD_MONATE) if art == "benutzer"
               else heute + datetime.timedelta(days=lizenz.TEST_TAGE - 1))
        self.bis.setDate(QDate(bis.year, bis.month, bis.day))
        self.bis.setEnabled(art != "admin")
        self.beliebig.setEnabled(art != "admin")
        if art == "admin":
            self.beliebig.setChecked(False)
            self.inhaber.setText(self.inhaber.text() or "Patrick")

    def ordner_oeffnen(self):
        self.ordner.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ordner)))

    # ---------------------------------------------------------------- Aktionen
    def schluessel(self):
        pw = self.passwort("Neues Passwort (mindestens 8 Zeichen)")
        if not pw:
            return
        if len(pw) < 8:
            return self.fehler("Bitte ein Passwort mit mindestens 8 Zeichen.")
        if self.passwort("Passwort wiederholen") != pw:
            return self.fehler("Die Passwörter stimmen nicht überein.")
        try:
            text = wz.schluessel_erzeugen(self.ordner, "K1", pw)
        except SystemExit as e:
            return self.fehler(e)
        QGuiApplication.clipboard().setText(f'"K1": "{text}",')
        d = QDialog(self)
        d.setWindowTitle("Schlüssel erzeugt")
        lay = QVBoxLayout(d)
        info = QLabel(f"Privater Schlüssel: {wz.schluessel_pfad(self.ordner, 'K1')}<br><br><b>Jetzt zwei Kopien "
                      "sichern</b> (USB-Stick im Tresor, Passwortmanager) und das Passwort nicht vergessen.<br><br>"
                      "Diesen <b>öffentlichen</b> Schlüssel ins Programm übernehmen lassen (in die Zwischenablage "
                      "kopiert, z. B. im Chat schicken). Er ist kein Geheimnis:")
        info.setWordWrap(True)
        lay.addWidget(info)
        feld = QLineEdit(f'"K1": "{text}",')
        feld.setReadOnly(True)
        lay.addWidget(feld)
        k = QDialogButtonBox(QDialogButtonBox.Ok)
        k.accepted.connect(d.accept)
        lay.addWidget(k)
        d.exec()
        self.neu_laden()

    def update_schluessel(self):
        """Schlüssel für die Signatur der Update-Dateiliste (U1): erzeugen bzw. den Secret-Wert noch einmal zeigen."""
        sid = "U1"
        da = wz.schluessel_pfad(self.ordner, sid).exists()
        if da:
            pw = self.passwort(f"Passwort des Update-Schlüssels {sid}")
        else:
            pw = self.passwort("Neues Passwort für den Update-Schlüssel (mindestens 8 Zeichen)")
            if pw and len(pw) < 8:
                return self.fehler("Bitte ein Passwort mit mindestens 8 Zeichen.")
            if pw and self.passwort("Passwort wiederholen") != pw:
                return self.fehler("Die Passwörter stimmen nicht überein.")
        if not pw:
            return
        try:
            oeffentlich, geheim = (wz.update_secret if da else wz.update_schluessel_erzeugen)(self.ordner, sid, pw)
        except SystemExit as e:
            return self.fehler(e)
        d = QDialog(self)
        d.setWindowTitle(f"Update-Schlüssel {sid}")
        lay = QVBoxLayout(d)
        info = QLabel(f"Privater Schlüssel: {wz.schluessel_pfad(self.ordner, sid)} – <b>zwei Kopien sichern</b> "
                      "(USB-Stick im Tresor, Passwortmanager). Geht er verloren, brauchen alle Installationen einmal "
                      "das Setup.<br><br><b>1. Geheim:</b> diesen Wert in GitHub eintragen (Repository "
                      "Rohrlaser-Kalkulation- → Settings → Secrets and variables → Actions → New repository secret, "
                      "Name <b>UPDATE_SIGNATUR</b>). Nicht in den Chat, keine Datei:")
        info.setWordWrap(True)
        lay.addWidget(info)
        feld_geheim = QLineEdit(geheim)
        feld_geheim.setReadOnly(True)
        feld_geheim.setEchoMode(QLineEdit.Password)
        kopieren = QPushButton("Geheimen Wert kopieren")
        kopieren.clicked.connect(lambda: QGuiApplication.clipboard().setText(geheim))
        zeile = QHBoxLayout()
        zeile.addWidget(feld_geheim, 1)
        zeile.addWidget(kopieren)
        lay.addLayout(zeile)
        info2 = QLabel("<b>2. Öffentlich:</b> diese Zeile ins Programm übernehmen lassen (z. B. im Chat schicken), sie "
                       "ist kein Geheimnis:")
        info2.setWordWrap(True)
        lay.addWidget(info2)
        feld = QLineEdit(f'"{sid}": "{oeffentlich}",')
        feld.setReadOnly(True)
        lay.addWidget(feld)
        k = QDialogButtonBox(QDialogButtonBox.Ok)
        k.accepted.connect(d.accept)
        lay.addWidget(k)
        d.exec()
        QGuiApplication.clipboard().setText(f'"{sid}": "{oeffentlich}",')    # Geheimes nicht in der Ablage lassen

    def erstellen(self):
        art = self.art.currentData()
        rechner = [r.strip() for r in self.rechner.toPlainText().split() if r.strip()]
        if self.beliebig.isChecked() and art != "admin":
            rechner = []
        elif not rechner:
            return self.fehler("Bitte mindestens eine Rechner-ID eintragen (oder „beliebiger Rechner“).")
        if art == "admin" and len(rechner) > lizenz.ADMIN_RECHNER_MAX:
            return self.fehler(f"Eine Admin-Lizenz gilt für höchstens {lizenz.ADMIN_RECHNER_MAX} Rechner.")
        if not self.inhaber.text().strip():
            return self.fehler("Bitte den Inhaber eintragen.")
        pw = self.passwort()
        if not pw:
            return
        q = self.bis.date()
        bis = None if art == "admin" else datetime.date(q.year(), q.month(), q.day())
        try:
            datei = wz.ausstellen(self.ordner, art, self.inhaber.text().strip(), self.firma.text().strip(), bis,
                                  rechner, self.hinweis.text().strip(), pw=pw)
        except (SystemExit, lizenz.LizenzFehler, ValueError) as e:
            return self.fehler(e)
        self.neu_laden()
        if QMessageBox.question(self, "Lizenz erstellt", f"Lizenzdatei:\n{datei}\n\nOrdner öffnen? Die Datei an den "
                                "Benutzer schicken; er lädt sie unter Hilfe → Lizenz …") == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(datei.parent)))

    def sperren(self):
        ids = sorted({self.tabelle.item(i.row(), 0).text() for i in self.tabelle.selectedIndexes()})
        if not ids:
            return self.fehler("Bitte zuerst Lizenzen in der Liste markieren.")
        if QMessageBox.question(self, "Sperren", f"Diese Lizenzen sperren?\n\n{', '.join(ids)}") != QMessageBox.Yes:
            return
        pw = self.passwort()
        if not pw:
            return
        try:
            p = wz.sperren(self.ordner, ids, pw)
        except SystemExit as e:
            return self.fehler(e)
        self.neu_laden()
        QMessageBox.information(self, "Sperrliste", f"Neue Sperrliste:\n{p}\n\nJetzt als Sperrliste.json in den "
                                "Release update-dateien des Repositorys Rohrlaser-Updates hochladen (vorhandene Datei "
                                "ersetzen). Die Programme holen sie beim nächsten Update-Check.")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.parent)))

    def pruefen(self):
        datei, _ = QFileDialog.getOpenFileName(self, "Lizenzdatei prüfen", str(self.ordner),
                                               "Lizenzdatei (*.lizenz)")
        if not datei:
            return
        try:
            daten = lizenz.lesen(Path(datei))
            inhalt = lizenz.pruefen(daten, wz.schluessel_bekannt(self.ordner))
        except lizenz.LizenzFehler as e:
            return self.fehler(f"UNGÜLTIG: {e}")
        z = lizenz.ermitteln(daten, rechner=(inhalt["rechner"] or [""])[0], schluessel=wz.schluessel_bekannt(self.ordner),
                             durchsetzung=True)
        QMessageBox.information(self, "Lizenzdatei prüfen", f"Signatur gültig.\n\n{inhalt['lizenz_id']} "
                                f"({inhalt['art']}) für {inhalt['inhaber']}, bis {inhalt['gueltig_bis'] or 'unbefristet'}"
                                f"\nZustand heute: {z.stufe}" + (f" – {z.hinweis or z.grund}" if z.hinweis or z.grund
                                                                  else ""))


def starten(ordner):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    f = Fenster(ordner)
    f.show()
    return app.exec()
