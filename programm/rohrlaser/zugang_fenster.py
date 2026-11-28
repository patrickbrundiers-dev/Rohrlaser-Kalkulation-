"""Zugangssystem Paket C: Anmeldefenster, Sperrbildschirm nach Inaktivität, Benutzer wechseln (Qt).

Die Logik liegt in zugang_anmeldung.Anmeldung; hier nur Darstellung und Ablauf:

- AnmeldeDialog: Benutzer aus der Liste (der zuletzt an diesem Platz angemeldete ist vorgewählt), Passwort oder PIN,
  Einmalcode erst, wenn das Konto ihn verlangt. „Mit Entwickler-Ausweis …“ schaltet auf den Ausweis (USB-Stick oder
  hier hinterlegt). Beim Start heißt Abbrechen „Beenden“.
- SperrDialog: nach Inaktivität über dem Hauptfenster; weiter nur mit dem eigenen Passwort oder „Benutzer wechseln“.
- Waechter: zählt Tastatur und Maus als Eingabe und prüft jede halbe Minute den Ablauf.
- offene_fenster_schliessen: vor dem Wechsel alle anderen Fenster schließen; jedes fragt dabei selbst nach seinen
  ungespeicherten Änderungen. Bleibt eines offen (Abbrechen), wird nicht gewechselt.
"""
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton)


FEHLER_FARBE = "color: #B42318;"
PRUEF_TAKT_MS = 30_000


class AnmeldeDialog(QDialog):
    fenster_groesse = "klein"

    def __init__(self, eltern, anmeldung, beim_start=False, titel="Anmelden"):
        super().__init__(eltern)
        self.an = anmeldung
        self.entwickler = False
        self.ergebnis = None
        self.setWindowTitle(titel)
        form = self.form = QFormLayout(self)
        self.hinweis = QLabel("Benutzer wählen und Passwort oder PIN eingeben.")
        self.hinweis.setWordWrap(True)
        form.addRow(self.hinweis)
        self.auswahl = QComboBox()
        for k, text in anmeldung.auswahl():
            self.auswahl.addItem(text, k)
        i = self.auswahl.findData(anmeldung.letzter())
        if i >= 0:
            self.auswahl.setCurrentIndex(i)
        self.auswahl.currentIndexChanged.connect(self._benutzer_gewechselt)
        form.addRow("Benutzer", self.auswahl)
        self.geheim = QLineEdit()
        self.geheim.setEchoMode(QLineEdit.Password)
        form.addRow("Passwort / PIN", self.geheim)
        self.code = QLineEdit()
        self.code.setPlaceholderText("6 Ziffern aus der Authenticator-App")
        self.code.setMaxLength(8)
        self.code_text = QLabel("Einmalcode")
        form.addRow(self.code_text, self.code)
        self._code_zeigen(False)
        self.fehler = QLabel()
        self.fehler.setStyleSheet(FEHLER_FARBE)
        self.fehler.setWordWrap(True)
        form.addRow(self.fehler)
        self.knopf_entwickler = QPushButton("Mit Entwickler-Ausweis …")
        self.knopf_entwickler.setFlat(True)
        self.knopf_entwickler.clicked.connect(self.entwickler_umschalten)
        form.addRow(self.knopf_entwickler)
        k = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        k.button(QDialogButtonBox.Ok).setText("Anmelden")
        k.button(QDialogButtonBox.Cancel).setText("Beenden" if beim_start else "Abbrechen")
        k.accepted.connect(self.pruefen)
        k.rejected.connect(self.reject)
        form.addRow(k)
        self.geheim.setFocus()

    def _code_zeigen(self, an):
        self.code.setVisible(an)
        self.code_text.setVisible(an)
        if not an:
            self.code.clear()

    def _benutzer_gewechselt(self):
        self._code_zeigen(False)
        self.fehler.clear()

    def entwickler_umschalten(self):
        self.entwickler = not self.entwickler
        self._code_zeigen(False)
        self.fehler.clear()
        self.geheim.clear()
        self.auswahl.setEnabled(not self.entwickler)
        if self.entwickler:
            daten, von_stick, totp, wo = self.an.ausweis_finden()
            self.hinweis.setText(("Entwickler-Ausweis: " + wo + ". Passwort des Ausweises eingeben.")
                                 if daten is not None else wo)
            self.knopf_entwickler.setText("Zurück zur Benutzeranmeldung")
            if daten is not None and not von_stick and totp:
                self._code_zeigen(True)
        else:
            self.hinweis.setText("Benutzer wählen und Passwort oder PIN eingeben.")
            self.knopf_entwickler.setText("Mit Entwickler-Ausweis …")
        self.geheim.setFocus()

    def pruefen(self):
        code = self.code.text().strip() if self.code.isVisible() else None
        QApplication.setOverrideCursor(Qt.WaitCursor)       # scrypt/Tresor dauern einen Moment
        try:
            if self.entwickler:
                e = self.an.entwickler_anmelden(self.geheim.text(), code)
            else:
                e = self.an.anmelden(self.auswahl.currentData() or "", self.geheim.text(), code)
        finally:
            QApplication.restoreOverrideCursor()
        if e.zweiter_faktor_fehlt and not e.ok:
            self._code_zeigen(True)
            if self.code.text():
                self.code.clear()
            self.fehler.setText(e.text)
            self.code.setFocus()
            return
        if not e.ok:
            self.fehler.setText(e.text)
            self.geheim.clear()
            self.geheim.setFocus()
            return
        self.ergebnis = e
        self.accept()


class SperrDialog(QDialog):
    """Sperrbildschirm: Ergebnis Accepted = entsperrt, WECHSELN = Benutzer wechseln."""
    fenster_groesse = "klein"
    WECHSELN = 2

    def __init__(self, eltern, anmeldung):
        super().__init__(eltern)
        self.an = anmeldung
        s = anmeldung.sitzung
        self.setWindowTitle("Gesperrt")
        form = QFormLayout(self)
        t = QLabel(f"Gesperrt nach {s.minuten if s else '?'} Minuten ohne Eingabe.<br><b>{anmeldung.text()}</b><br>"
                   "Zum Weiterarbeiten das eigene Passwort eingeben.")
        t.setWordWrap(True)
        form.addRow(t)
        self.geheim = QLineEdit()
        self.geheim.setEchoMode(QLineEdit.Password)
        form.addRow("Passwort / PIN", self.geheim)
        self.code = QLineEdit()
        self.code.setPlaceholderText("Einmalcode, falls verlangt")
        form.addRow("Einmalcode", self.code)
        self.fehler = QLabel()
        self.fehler.setStyleSheet(FEHLER_FARBE)
        form.addRow(self.fehler)
        k = QDialogButtonBox()
        k.addButton("Entsperren", QDialogButtonBox.AcceptRole)
        wechseln = k.addButton("Benutzer wechseln", QDialogButtonBox.ResetRole)
        k.accepted.connect(self.pruefen)
        wechseln.clicked.connect(lambda: self.done(self.WECHSELN))
        form.addRow(k)
        self.geheim.setFocus()

    def reject(self):          # Esc und Schließen entsperren nicht
        self.fehler.setText("Gesperrt: bitte Passwort eingeben oder den Benutzer wechseln.")

    def pruefen(self):
        f = self.an.entsperren(self.geheim.text(), self.code.text().strip() or None)
        if f:
            self.fehler.setText(f)
            self.geheim.clear()
            return
        self.accept()


class Waechter(QObject):
    """Eingaben zählen und den Ablauf prüfen; bei Ablauf ruft er sperren() des Hauptfensters."""
    EINGABEN = (QEvent.KeyPress, QEvent.MouseButtonPress, QEvent.Wheel)

    def __init__(self, fenster, anmeldung, takt_ms=PRUEF_TAKT_MS):
        super().__init__(fenster)
        self.f = fenster
        self.an = anmeldung
        self.offen = False
        QApplication.instance().installEventFilter(self)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.pruefen)
        self.timer.start(takt_ms)

    def eventFilter(self, obj, ereignis):
        if not self.offen and ereignis.type() in self.EINGABEN:
            self.an.eingabe()
        return False

    def pruefen(self):
        if self.offen or not self.an.angemeldet():
            return False
        if self.an.ablauf_pruefen() or self.an.gesperrt():
            self.offen = True
            try:
                self.f.sitzung_gesperrt()
            finally:
                self.offen = False
            return True
        return False

    def beenden(self):
        self.timer.stop()
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)


def _andere(hauptfenster):
    return [w for w in QApplication.topLevelWidgets()
            if w is not hauptfenster and w.isVisible() and w.isWindow()
            and not isinstance(w, (AnmeldeDialog, SperrDialog))]


def offene_fenster_schliessen(hauptfenster):
    """Alle anderen sichtbaren Fenster schließen (jedes fragt selbst nach Ungespeichertem). Ergebnis: alle zu."""
    for w in _andere(hauptfenster):
        w.close()
    QApplication.processEvents()
    return not _andere(hauptfenster)


def wechsel_fragen(eltern):
    """Rückfrage vor dem Benutzerwechsel."""
    return QMessageBox.question(
        eltern, "Benutzer wechseln",
        "Benutzer wechseln?\n\nAngebote sind gespeichert. Offene Fenster und Editoren werden geschlossen; "
        "ungespeicherte Änderungen darin fragt jedes Fenster selbst ab.",
        QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes

