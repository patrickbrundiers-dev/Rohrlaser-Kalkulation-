"""Fenster des Server-Einrichtungs-Assistenten (server_assistent): fünf Seiten Angaben, eine Seite Ausführen mit
Fortschritt je Schritt, Ergebnis mit Zugangsdatei und Fingerabdruck. Die Arbeit macht server_assistent.ausfuehren
in einem eigenen Faden, das Fenster bleibt dabei bedienbar."""
import os
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QApplication, QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy, QSpinBox,
                               QTextBrowser,
                               QVBoxLayout, QWidget, QWizard, QWizardPage)

from . import server_assistent as sa

ZEICHEN = {"läuft": "◐", "gut": "✓", "Warnung": "!", "übersprungen": "–", "Fehler": "✗", "offen": "○"}


def _hinweis(text):
    lb = QLabel(text)
    lb.setWordWrap(True)
    lb.setTextFormat(Qt.RichText)
    lb.setStyleSheet("color: palette(mid);")
    lb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    lb.setMinimumWidth(420)
    return lb


def _ordner_zeile(feld, titel):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.addWidget(feld, 1)
    b = QPushButton("…")
    b.setFixedWidth(32)

    def waehlen():
        p = QFileDialog.getExistingDirectory(w, titel, feld.text())
        if p:
            feld.setText(os.path.normpath(p))
    b.clicked.connect(waehlen)
    h.addWidget(b)
    return w


class Seite(QWizardPage):
    def __init__(self, titel, unter):
        super().__init__()
        self.setTitle(titel)
        self.setSubTitle(unter)
        self.form = QFormLayout(self)
        self.form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)


class Bote(QObject):
    zeile = Signal(str)
    stand = Signal(int, int, str, str)
    fertig = Signal(dict)


class Assistent(QWizard):
    def __init__(self, angaben=None):
        super().__init__()
        self.a = angaben or sa.vorschlag()
        self.ergebnis = None
        self.setWindowTitle("NexTube Server einrichten")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.NoBackButtonOnLastPage, True)
        self.setOption(QWizard.NoCancelButtonOnLastPage, True)
        self.setButtonText(QWizard.NextButton, "Weiter >")
        self.setButtonText(QWizard.BackButton, "< Zurück")
        self.setButtonText(QWizard.CancelButton, "Abbrechen")
        self.setButtonText(QWizard.FinishButton, "Fertig")
        self.resize(720, 560)
        a = self.a

        p = Seite("Willkommen", "Der Assistent richtet den zentralen Server auf diesem Rechner ein.")
        p.form.addRow(_hinweis(
            "Er erledigt in einem Durchgang, was im IT-Handbuch (Kapitel 3 bis 5) als Befehle steht: Datenbank mit "
            "Zertifikaten, erster Administrator, Firewall-Regel, Freigabe der Ablage, Aufgabenplanung (Start, "
            "Rechner-Dienst, Sicherung), zweites Sicherungsziel und die erste Sicherung mit Probe.<br><br>"
            "<b>Vorher</b>: als Dienstkonto angemeldet, Programm als Administrator gestartet, Laufwerk für den "
            "Server-Ordner vorhanden, feste IP und DNS-Name. Ein schon eingerichteter Server bleibt erhalten; der "
            "Assistent darf erneut laufen."))
        if not sa.ist_admin():
            p.form.addRow(_hinweis("<span style='color:#b00020'><b>Nicht als Administrator gestartet.</b> Bitte "
                                   "schließen und mit Rechtsklick → „Als Administrator ausführen“ neu starten."
                                   "</span>"))
        self.addPage(p)

        p = Seite("Server", "Wo die Daten liegen und wie der Server heißt.")
        self.f_ordner = QLineEdit(a.ordner)
        p.form.addRow("Server-Ordner", _ordner_zeile(self.f_ordner, "Server-Ordner wählen"))
        self.f_firma = QLineEdit(a.firma)
        self.f_firma.setPlaceholderText("z. B. Muster Rohrbearbeitung GmbH")
        p.form.addRow("Firmenname", self.f_firma)
        self.f_adressen = QLineEdit(" ".join(a.adressen))
        p.form.addRow("Name und IP", self.f_adressen)
        p.form.addRow("", _hinweis("DNS-Name und feste IP des Servers, mit Leerzeichen getrennt. Sie stehen im "
                                   "Zertifikat; die Arbeitsplätze verbinden sich darüber."))
        self.f_port = QSpinBox()
        self.f_port.setRange(1, 65535)
        self.f_port.setValue(int(a.port))
        p.form.addRow("Port", self.f_port)
        self.addPage(p)

        p = Seite("Erster Administrator", "Mit diesem Zugang legt der Verwalter später die Mitarbeiter an.")
        self.f_admin = QLineEdit(a.admin)
        self.f_admin.setPlaceholderText("Kürzel, z. B. PB")
        self.f_admin.setMaxLength(8)
        p.form.addRow("Kürzel", self.f_admin)
        self.f_pw1 = QLineEdit()
        self.f_pw1.setEchoMode(QLineEdit.Password)
        self.f_pw2 = QLineEdit()
        self.f_pw2.setEchoMode(QLineEdit.Password)
        p.form.addRow("Passwort", self.f_pw1)
        p.form.addRow("Noch einmal", self.f_pw2)
        p.form.addRow("", _hinweis("Mindestens 8 Zeichen. Weitere Mitarbeiter danach im Programm unter "
                                   "Einstellungen → Benutzer und Rollen."))
        self.addPage(p)

        p = Seite("Netzwerk", "Firewall und Freigabe der gemeinsamen Dateien (Ablage).")
        self.f_fw = QCheckBox("Firewall-Regel für die Datenbank anlegen")
        self.f_fw.setChecked(a.firewall)
        p.form.addRow(self.f_fw)
        self.f_fwq = QLineEdit(a.firewall_quelle)
        p.form.addRow("Erlaubt aus", self.f_fwq)
        p.form.addRow("", _hinweis("LocalSubnet = eigenes Subnetz, oder z. B. 192.168.1.0/24."))
        self.f_fg = QCheckBox("Ablage im Netz freigeben (SMB) und Rechte setzen")
        self.f_fg.setChecked(a.freigabe)
        p.form.addRow(self.f_fg)
        self.f_fgn = QLineEdit(a.freigabe_name)
        p.form.addRow("Name der Freigabe", self.f_fgn)
        self.f_gruppe = QLineEdit(a.gruppe)
        p.form.addRow("Gruppe (Ändern)", self.f_gruppe)
        p.form.addRow("", _hinweis("Windows-Gruppe der Mitarbeiter, z. B. FIRMA\\GG-Rohrlaser-Benutzer. Das "
                                   "Dienstkonto bekommt Vollzugriff."))
        self.addPage(p)

        p = Seite("Sicherung und Dienstkonto", "Zeiten, zweites Ziel und das Konto der geplanten Aufgaben.")
        self.f_zeiten = QLineEdit(a.uhrzeiten)
        p.form.addRow("Sicherung um", self.f_zeiten)
        self.f_nas = QLineEdit(a.nas)
        self.f_nas.setPlaceholderText("\\\\NAS\\Backup\\Rohrlaser (empfohlen)")
        p.form.addRow("Zweites Ziel", _ordner_zeile(self.f_nas, "Zweites Sicherungsziel wählen"))
        p.form.addRow("", _hinweis("Jede gute Sicherung samt Ablage wird dorthin kopiert und per SHA-256 geprüft. "
                                   "Leer lassen, wenn die IT selbst kopiert."))
        self.f_konto = QLineEdit(a.konto)
        p.form.addRow("Dienstkonto", self.f_konto)
        self.f_kpw = QLineEdit()
        self.f_kpw.setEchoMode(QLineEdit.Password)
        p.form.addRow("Windows-Passwort", self.f_kpw)
        p.form.addRow("", _hinweis("Die Aufgaben laufen damit auch ohne Anmeldung. Das Passwort wird nur an die "
                                   "Windows-Aufgabenplanung übergeben, nirgends gespeichert."))
        self.f_erste = QCheckBox("Gleich die erste Sicherung mit Probe machen")
        self.f_erste.setChecked(a.erste_sicherung)
        p.form.addRow(self.f_erste)
        self.addPage(p)

        self.s_zus = Seite("Zusammenfassung", "Mit „Einrichten“ geht es los. Das dauert einige Minuten.")
        self.zus = QTextBrowser()
        self.zus.setFrameShape(QTextBrowser.NoFrame)
        self.zus.setStyleSheet("background: transparent;")
        self.s_zus.form.addRow(self.zus)
        self.s_zus.setButtonText(QWizard.NextButton, "Einrichten")
        self.addPage(self.s_zus)

        self.s_lauf = LaufSeite(self)
        self.addPage(self.s_lauf)
        self.currentIdChanged.connect(self._seite)

    def angaben(self):
        a = self.a
        a.ordner = self.f_ordner.text().strip()
        a.firma = self.f_firma.text().strip()
        a.adressen = self.f_adressen.text().replace(",", " ").split()
        a.port = self.f_port.value()
        a.admin = self.f_admin.text().strip().upper()
        a.admin_passwort = self.f_pw1.text()
        a.firewall = self.f_fw.isChecked()
        a.firewall_quelle = self.f_fwq.text().strip() or "LocalSubnet"
        a.freigabe = self.f_fg.isChecked()
        a.freigabe_name = self.f_fgn.text().strip()
        a.gruppe = self.f_gruppe.text().strip()
        a.uhrzeiten = self.f_zeiten.text().strip()
        a.nas = self.f_nas.text().strip()
        a.konto = self.f_konto.text().strip()
        a.konto_passwort = self.f_kpw.text()
        a.erste_sicherung = self.f_erste.isChecked()
        return a

    def validateCurrentPage(self):
        if self.currentPage() is self.s_zus:
            return True
        a = self.angaben()
        idx = self.currentId()
        fehler = []
        if idx == 2 and self.f_pw1.text() != self.f_pw2.text():
            fehler.append("Die beiden Passwörter sind verschieden.")
        alle = sa.pruefen(a)
        felder = {1: ("Server-Ordner", "Firmenname", "Adresse", "Mindestens eine", "Port"),
                  2: ("Administrator",), 3: ("Name der Freigabe",),
                  4: ("Zweites Sicherungsziel", "Sicherungszeiten", "Windows-Passwort")}.get(idx, ())
        fehler += [f for f in alle if f.startswith(felder)] if felder else []
        if fehler:
            QMessageBox.warning(self, "Bitte prüfen", "\n".join(fehler))
            return False
        return True

    def _seite(self, idx):
        if self.page(idx) is self.s_zus:
            a = self.angaben()
            zeilen = "".join(f"<li>{s.titel}</li>" for s in sa.schritte(a))
            self.zus.setText(
                f"<b>{a.firma}</b>, Server-Ordner <b>{a.ordner}</b>, Port {a.port}, Adressen "
                f"{', '.join(a.adressen)}<br>Administrator <b>{a.admin}</b>, Dienstkonto {a.konto}<br>"
                f"Ablage für die Arbeitsplätze: {sa.ablage_unc(a) if a.freigabe or a.ablage_pfad else '–'}<br>"
                f"Sicherung um {a.uhrzeiten}, zweites Ziel: {a.nas or '–'}<br><br>Schritte:<ol>{zeilen}</ol>")
        elif self.page(idx) is self.s_lauf:
            self.s_lauf.los(self.angaben())


class LaufSeite(QWizardPage):
    def __init__(self, wiz):
        super().__init__()
        self.wiz = wiz
        self.fertig_ = False
        self.setTitle("Einrichtung läuft")
        self.setSubTitle("Bitte warten, bis alle Schritte einen Haken haben.")
        v = QVBoxLayout(self)
        self.liste = QListWidget()
        v.addWidget(self.liste, 2)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFont("Consolas", 9))
        v.addWidget(self.log, 3)
        self.ergebnis = QLabel()
        self.ergebnis.setWordWrap(True)
        self.ergebnis.setTextFormat(Qt.RichText)
        self.ergebnis.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(self.ergebnis)
        h = QHBoxLayout()
        self.b_ordner = QPushButton("Server-Ordner öffnen")
        self.b_handbuch = QPushButton("IT-Handbuch öffnen")
        for b in (self.b_ordner, self.b_handbuch):
            b.setEnabled(False)
            h.addWidget(b)
        h.addStretch(1)
        v.addLayout(h)
        self.b_ordner.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.wiz.a.ordner)))
        self.b_handbuch.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(handbuch()))))
        self.bote = Bote()
        self.bote.zeile.connect(self.log.appendPlainText)
        self.bote.stand.connect(self._stand)
        self.bote.fertig.connect(self._fertig)

    def isComplete(self):
        return self.fertig_

    def los(self, a):
        self.liste.clear()
        for s in sa.schritte(a):
            self.liste.addItem(QListWidgetItem(f"{ZEICHEN['offen']}  {s.titel}"))
        threading.Thread(target=self._arbeiten, args=(a,), daemon=True).start()

    def _arbeiten(self, a):
        try:
            erg = sa.ausfuehren(a, melden=self.bote.zeile.emit, fortschritt=self.bote.stand.emit)
        except Exception as e:      # noqa: BLE001
            erg = dict(gut=False, warnungen=[str(e)], protokoll=None)
        self.bote.fertig.emit(erg)

    def _stand(self, nr, anzahl, titel, zustand):
        it = self.liste.item(nr - 1)
        if it:
            it.setText(f"{ZEICHEN.get(zustand, '?')}  {titel}" + ("" if zustand in ("gut", "läuft") else
                                                                    f"  ({zustand})"))
            self.liste.scrollToItem(it)

    def _fertig(self, erg):
        self.wiz.ergebnis = erg
        self.fertig_ = True
        self.b_ordner.setEnabled(True)
        self.b_handbuch.setEnabled(handbuch().exists())
        if erg.get("gut"):
            self.setTitle("Server eingerichtet")
            self.setSubTitle("Der Server läuft und startet nach jedem Neustart von selbst.")
            warn = "".join(f"<li>{w}</li>" for w in erg.get("warnungen") or [])
            self.ergebnis.setText(
                f"<b>Zugangsdatei für die Arbeitsplätze:</b> {erg['zugang']}<br>"
                f"<b>Fingerabdruck</b> (in der IT-Dokumentation notieren): <tt>{erg['fingerabdruck']}</tt><br>"
                f"Ablage: {erg['ablage']}<br>Protokoll: {erg.get('protokoll') or '–'}"
                + (f"<br><span style='color:#b26a00'><b>Bitte von Hand nachholen:</b><ul>{warn}</ul></span>"
                   if warn else "")
                + "<br>Nächste Schritte: Server-Lizenz im Programm aktivieren, Mitarbeiter anlegen, Arbeitsplätze "
                  "verbinden (IT-Handbuch Kapitel 6).")
        else:
            self.setTitle("Einrichtung abgebrochen")
            self.setSubTitle("Fertige Schritte bleiben erhalten. Fehler beheben und den Assistenten erneut starten.")
            self.ergebnis.setText("<span style='color:#b00020'>Details stehen oben und im Protokoll "
                                  f"{erg.get('protokoll') or ''}.</span>")
        self.completeChanged.emit()


def handbuch():
    import sys
    basis = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parents[2] / "anleitung"
    return basis / "IT-Handbuch_Server.pdf"


def starten():
    import sys
    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        from . import marke
        app.setWindowIcon(marke.icon())
    except Exception:       # noqa: BLE001 - ohne Symbol geht es auch
        pass
    w = Assistent()
    w.show()
    app.exec()
    return 0 if (w.ergebnis or {}).get("gut") else 1
