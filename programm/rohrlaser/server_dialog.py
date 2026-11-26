"""Fenster der Betriebsart Server (Serverversion S1, Patrick 26.11.2026): Anmelden beim Start, Arbeitsplatz mit dem
Server verbinden (Zugangsdatei einlesen), zurück zur lokalen Datenbank, Hinweise beim Start. Regeln in
server_betrieb.py."""
import json

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from . import NAME, datenspeicher, db_verbindung
from . import server_betrieb as sb

ROT = "color: #B42318;"
GRUEN = "color: #067647;"


def fehler_text(e):
    return str(e) or type(e).__name__


class AnmeldeDialog(QDialog):
    """Anmeldung am zentralen Server mit Kürzel und Passwort (beim Start). Die Prüfung macht der Server selbst."""

    def __init__(self, eltern, merk_pfad, meldung=""):
        super().__init__(eltern)
        self.merk_pfad = merk_pfad
        self.merk = datenspeicher.merkdatei_lesen(merk_pfad) or {}
        self.setWindowTitle(f"{NAME} – Anmelden am Server")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        name = self.merk.get("name") or "Rohrlaser-Server"
        kopf = QLabel(f"<b>{name}</b><br>{self.merk.get('host', '')}:{self.merk.get('port', sb.PORT)}")
        form.addRow(kopf)
        self.kuerzel = QLineEdit(self.merk.get("kuerzel") or sb.angemeldet())
        self.passwort = QLineEdit()
        self.passwort.setEchoMode(QLineEdit.Password)
        form.addRow("Kürzel", self.kuerzel)
        form.addRow("Passwort", self.passwort)
        self.fehler = QLabel(meldung)
        self.fehler.setWordWrap(True)
        self.fehler.setStyleSheet(ROT)
        form.addRow(self.fehler)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.button(QDialogButtonBox.Ok).setText("Anmelden")
        k.button(QDialogButtonBox.Cancel).setText("Beenden")
        k.accepted.connect(self.pruefen)
        k.rejected.connect(self.reject)
        form.addRow(k)
        (self.passwort if self.kuerzel.text() else self.kuerzel).setFocus()
        self.ergebnis = None

    def pruefen(self):
        k, pw = self.kuerzel.text().strip().upper(), self.passwort.text()
        if not k or not pw:
            self.fehler.setText("Bitte Kürzel und Passwort eingeben.")
            return
        try:
            self.ergebnis = sb.anmeldung_pruefen(self.merk_pfad, k, pw, self.merk)
        except (sb.ServerFehler, db_verbindung.DbFehler) as e:
            self.fehler.setText(fehler_text(e))
            self.passwort.clear()
            return
        sb.anmelden(k, pw)
        self._kuerzel_merken(k)
        self.accept()

    def _kuerzel_merken(self, k):
        """Kürzel für das nächste Mal in der Merkdatei (kein Passwort)."""
        if self.merk.get("kuerzel") == k:
            return
        import os
        werte = dict(self.merk, kuerzel=k)
        try:
            tmp = datenspeicher._merkdatei_schreiben(self.merk_pfad, werte)
            os.replace(tmp, self.merk_pfad)
        except OSError:
            pass


def anmelden_beim_start(merk_pfad, meldung=""):
    """Anmeldefenster beim Start. Ergebnis: True (angemeldet) oder False (Beenden)."""
    return AnmeldeDialog(None, merk_pfad, meldung).exec() == QDialog.Accepted


def heben_fragen(meldung):
    """Ein Verwalter startet eine neuere Version: Server umstellen (alle müssen danach aktualisieren) oder nur
    ansehen?"""
    m = QMessageBox(QMessageBox.Question, NAME, meldung + "\n\nJetzt umstellen? Vorher wird gesichert.")
    ja = m.addButton("Server umstellen", QMessageBox.AcceptRole)
    m.addButton("Nur ansehen", QMessageBox.RejectRole)
    m.exec()
    return m.clickedButton() is ja


def fehler_beim_start(merk_pfad, fehler):
    """Server nicht erreichbar oder Anmeldung abgelehnt. Ergebnis: 'nochmal', 'lokal' oder 'beenden'."""
    m = datenspeicher.merkdatei_lesen(merk_pfad) or {}
    lokal_da = bool(json.loads(m.get("vorher") or "{}"))
    box = QMessageBox(QMessageBox.Warning, NAME, f"Der Server ist nicht bereit:\n\n{fehler_text(fehler)}")
    nochmal = box.addButton("Noch einmal", QMessageBox.AcceptRole)
    lokal = box.addButton("Lokal arbeiten (eigene Daten dieses PCs)", QMessageBox.DestructiveRole) if lokal_da else None
    box.addButton("Beenden", QMessageBox.RejectRole)
    box.exec()
    if box.clickedButton() is nochmal:
        return "nochmal"
    if lokal is not None and box.clickedButton() is lokal:
        return "lokal"
    return "beenden"


class VerbindenDialog(QDialog):
    """Arbeitsplatz mit dem Server verbinden: Zugangsdatei (vom Administrator) wählen, Fingerabdruck vergleichen,
    Adresse wählen, Anmeldung prüfen. Die lokalen Daten bleiben unverändert (zurück jederzeit möglich)."""

    def __init__(self, eltern, merk_pfad):
        super().__init__(eltern)
        self.merk_pfad = merk_pfad
        self.zugang = None
        self.setWindowTitle("Mit dem Server verbinden")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        einleitung = QLabel("Die Zugangsdatei (*.rlserver) bekommen Sie vom Administrator; sie liegt auf dem "
                            "Server-Rechner im Server-Ordner. Die Daten dieses PCs bleiben unverändert erhalten.")
        einleitung.setWordWrap(True)
        lay.addWidget(einleitung)
        zeile = QHBoxLayout()
        self.datei = QLineEdit()
        self.datei.setReadOnly(True)
        waehlen = QPushButton("Zugangsdatei wählen …")
        waehlen.clicked.connect(lambda: self.waehlen())
        zeile.addWidget(self.datei, 1)
        zeile.addWidget(waehlen)
        lay.addLayout(zeile)
        form = QFormLayout()
        self.name = QLabel("–")
        self.finger = QLabel("–")
        self.finger.setTextInteractionFlags(self.finger.textInteractionFlags())
        self.adresse = QComboBox()
        self.adresse.setEditable(True)
        self.kuerzel = QLineEdit()
        self.passwort = QLineEdit()
        self.passwort.setEchoMode(QLineEdit.Password)
        form.addRow("Server", self.name)
        form.addRow("Fingerabdruck", self.finger)
        form.addRow("Adresse", self.adresse)
        form.addRow("Kürzel", self.kuerzel)
        form.addRow("Passwort", self.passwort)
        lay.addLayout(form)
        self.hinweis = QLabel("Fingerabdruck mit der Anzeige auf dem Server vergleichen.")
        self.hinweis.setWordWrap(True)
        lay.addWidget(self.hinweis)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = k.button(QDialogButtonBox.Ok)
        self.ok.setText("Verbinden")
        self.ok.setEnabled(False)
        k.accepted.connect(self.verbinden)
        k.rejected.connect(self.reject)
        lay.addWidget(k)

    def waehlen(self, pfad=None):
        if not pfad:
            pfad, _ = QFileDialog.getOpenFileName(self, "Zugangsdatei wählen", "", "Zugangsdatei (*.rlserver)")
            if not pfad:
                return
        try:
            self.zugang = sb.zugangsdatei_lesen(pfad)
        except sb.ServerFehler as e:
            self.hinweis.setText(fehler_text(e))
            self.hinweis.setStyleSheet(ROT)
            return
        self.datei.setText(str(pfad))
        self.name.setText(self.zugang.get("name") or "Rohrlaser-Server")
        self.finger.setText(self.zugang["fingerabdruck"])
        self.adresse.clear()
        self.adresse.addItems([str(a) for a in self.zugang["adressen"]])
        self.ok.setEnabled(True)
        self.hinweis.setStyleSheet("")
        self.hinweis.setText("Fingerabdruck mit der Anzeige auf dem Server vergleichen, dann anmelden.")

    def verbinden(self):
        if self.zugang is None:
            return
        k, pw, adresse = self.kuerzel.text().strip().upper(), self.passwort.text(), self.adresse.currentText().strip()
        merk = sb.merk_werte(self.zugang, adresse, k)
        try:
            r = sb.anmeldung_pruefen(self.merk_pfad, k, pw, merk, self.zugang)
        except (sb.ServerFehler, db_verbindung.DbFehler) as e:
            self.hinweis.setText(fehler_text(e))
            self.hinweis.setStyleSheet(ROT)
            return
        sb.verbinden_einrichten(self.merk_pfad, self.zugang, adresse, k)
        self.ergebnis = r
        self.accept()


def verbinden(fenster, merk_pfad):
    """Datei → Datenbank → Mit dem Server verbinden. Ergebnis: True, wenn umgestellt (Neustart nötig)."""
    d = VerbindenDialog(fenster, merk_pfad)
    if d.exec() != QDialog.Accepted:
        return False
    QMessageBox.information(fenster, NAME, f"Dieser Arbeitsplatz ist jetzt mit „{d.zugang.get('name')}“ verbunden "
                                           f"(Recht: {d.ergebnis['recht']}).\n\nBitte das Programm neu starten.")
    return True


def zurueck(fenster, merk_pfad):
    """Datei → Datenbank → Zurück zur lokalen Datenbank. Ergebnis: True, wenn umgestellt (Neustart nötig)."""
    if QMessageBox.question(fenster, NAME, "Wieder mit der lokalen Datenbank dieses PCs arbeiten? Die Daten am "
                                           "Server bleiben unverändert, die lokalen Daten sind auf dem Stand vor dem "
                                           "Umstellen.") != QMessageBox.Yes:
        return False
    if not sb.zurueck_lokal(merk_pfad):
        QMessageBox.warning(fenster, NAME, "Auf diesem PC gibt es keine lokale Datenbank von vorher.")
        return False
    QMessageBox.information(fenster, NAME, "Umgestellt. Bitte das Programm neu starten.")
    return True
