"""Oberfläche zu teilen.py: Dialog „Benutzer und gemeinsamer Ordner“ und der Abgleich aus dem Hauptfenster (Knopf,
Programmstart, Beenden) mit den Rückfragen beim ersten Abgleich und bei einem schon belegten Kürzel."""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QWidget)

from . import nummern, teilen
from .angebot import kuerzel_sauber


class BenutzerDialog(QDialog):
    """Name, Kürzel, E-Mail, Telefon und gemeinsamer Ordner dieses Arbeitsplatzes."""
    def __init__(self, fenster, erststart=False):
        super().__init__(fenster)
        self.f, self.db = fenster, fenster.db
        self.setWindowTitle("Benutzer und gemeinsamer Ordner")
        self.setMinimumWidth(560)
        form = QFormLayout(self)
        text = QLabel(("Willkommen! " if erststart else "") +
                      "Das Kürzel zeigt, wer ein Angebot bearbeitet (Spalte Bearbeiter, Angebotskopf). Name, E-Mail "
                      "und Telefon stehen im Angebots-PDF als Ansprechpartner. Die Angebotsnummern (z. B. 2026-00001) "
                      "zählen für alle Mitarbeiter gemeinsam fortlaufend.<br><br>Mit einem gemeinsamen Ordner (Netzlaufwerk oder OneDrive-/SharePoint-"
                      "Ordner, den alle erreichen) sieht jeder die Angebote der anderen, und alle arbeiten mit denselben "
                      "Stammdaten. Abgeglichen wird beim Start, beim Beenden und mit dem Knopf „Abgleichen“.")
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        form.addRow(text)
        self.name, self.kuerzel = QLineEdit(db_text(self.db, "benutzer_name")), QLineEdit(db_text(self.db, "benutzer_kuerzel"))
        self.email, self.telefon = QLineEdit(db_text(self.db, "benutzer_email")), QLineEdit(db_text(self.db, "benutzer_telefon"))
        self.kuerzel.setMaxLength(5)
        self.kuerzel.setMaximumWidth(90)
        self.kuerzel.setPlaceholderText("z. B. PB")
        self.kuerzel.textEdited.connect(lambda t: self.kuerzel.setText(kuerzel_sauber(t)))
        self.ordner = QLineEdit(db_text(self.db, "teilen_ordner"))
        self.ordner.setPlaceholderText("leer = nicht teilen (nur dieser Arbeitsplatz)")
        waehlen = QPushButton("Ordner wählen …")
        waehlen.clicked.connect(self._waehlen)
        zeile = QWidget()
        lay = QHBoxLayout(zeile)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.ordner, 1)
        lay.addWidget(waehlen)
        form.addRow("Name", self.name)
        form.addRow("Kürzel", self.kuerzel)
        form.addRow("E-Mail", self.email)
        form.addRow("Telefon", self.telefon)
        form.addRow("Gemeinsamer Ordner", zeile)
        self.hinweis = QLabel()
        self.hinweis.setWordWrap(True)
        self.hinweis.setStyleSheet("color: #B42318;")
        form.addRow(self.hinweis)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.accepted.connect(self._ok)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)

    def _waehlen(self):
        pfad = QFileDialog.getExistingDirectory(self, "Gemeinsamen Ordner wählen", self.ordner.text().strip())
        if pfad:
            self.ordner.setText(str(Path(pfad)))

    def pruefen(self):
        """Fehlertext oder None."""
        k = kuerzel_sauber(self.kuerzel.text())
        if not k:
            return "Bitte ein Kürzel eintragen (Buchstaben und Ziffern, z. B. PB)."
        o = self.ordner.text().strip()
        if o and not Path(o).is_dir():
            return f"Den Ordner {o} gibt es nicht oder er ist nicht erreichbar."
        return None

    def speichern(self):
        alt = (teilen.kuerzel(self.db), str(teilen.ordner(self.db) or ""))
        for n, w in (("benutzer_name", self.name.text().strip()), ("benutzer_kuerzel", kuerzel_sauber(self.kuerzel.text())),
                     ("benutzer_email", self.email.text().strip()), ("benutzer_telefon", self.telefon.text().strip()),
                     ("teilen_ordner", self.ordner.text().strip())):
            self.db.einstellung_setzen(n, w)
        teilen.bearbeiter_nachtragen(self.db)
        return alt != (teilen.kuerzel(self.db), str(teilen.ordner(self.db) or ""))

    def _ok(self):
        fehler = self.pruefen()
        if fehler:
            self.hinweis.setText(fehler)
            return
        self.geaendert = self.speichern()
        self.accept()


def db_text(db, name):
    return str(db.einstellung(name) or "")


def benutzer_bearbeiten(fenster, erststart=False):
    """Dialog zeigen; nach einer Änderung von Kürzel oder Ordner gleich abgleichen. Ergebnis: True = gespeichert."""
    d = BenutzerDialog(fenster, erststart)
    if d.exec() != QDialog.Accepted:
        return False
    fenster.alles_neu_laden()
    if d.geaendert and teilen.aktiv(fenster.db):
        abgleichen(fenster)
    return True


def _erst_frage(fenster, e):
    """Erster Abgleich: Stammdaten der anderen übernehmen (empfohlen) oder mit den eigenen zusammenführen."""
    box = QMessageBox(fenster)
    box.setWindowTitle("Erster Abgleich")
    box.setIcon(QMessageBox.Question)
    box.setText(f"{e}\n\nSollen die gemeinsamen Stammdaten (Kunden, Profile, Preise, Schneiddaten, Maschinen, "
                "Fracht, Einstellungen …) die Stammdaten dieses Arbeitsplatzes ersetzen?\n\n"
                "Übernehmen (empfohlen bei einer neuen Installation): die eigenen Stammdaten werden vorher gesichert "
                "und durch die gemeinsamen ersetzt; Zukaufartikel und eigene Angebote bleiben.\n"
                "Zusammenführen: eigene Zeilen, die es dort nicht gibt, kommen dazu; bei gleichen Zeilen gilt der "
                "gemeinsame Stand.")
    ueber = box.addButton("Übernehmen", QMessageBox.AcceptRole)
    zusammen = box.addButton("Zusammenführen", QMessageBox.ActionRole)
    box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(ueber)
    box.exec()
    if box.clickedButton() is ueber:
        return teilen.UEBERNEHMEN
    if box.clickedButton() is zusammen:
        return teilen.ZUSAMMENFUEHREN
    return None


def _belegt_frage(fenster, e):
    return QMessageBox.question(
        fenster, "Kürzel schon belegt",
        f"{e}\n\nArbeiten Sie selbst jetzt an einem neuen Rechner (oder nach einer Neuinstallation)? Dann übernimmt "
        "dieser Arbeitsplatz die Datei; Ihre Angebote von dort kommen hierher.\n\nGehört das Kürzel einem Kollegen, "
        "bitte „Nein“ wählen und unter Datei → Benutzer und gemeinsamer Ordner ein anderes Kürzel eintragen.",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes


def abgleichen(fenster, lesen=True, schreiben=True, leise=False):
    """Abgleich mit dem gemeinsamen Ordner samt Rückfragen; danach Listen, Stammdaten und offene Angebote neu laden.
    leise: Fehler nur in der Statuszeile (Programmstart). Ergebnis: Bericht oder None (nicht abgeglichen)."""
    db = fenster.db
    if not teilen.aktiv(db):
        if not leise:
            fenster.meldung("Zum Abgleichen unter Datei → Benutzer und gemeinsamer Ordner Kürzel und Ordner eintragen.",
                            fehler=True)
        return None
    modus, uebernehmen, bericht, umnummeriert = None, False, {}, []
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        umnummeriert = nummern.endgueltig(db)
        for _ in range(3):
            try:
                if lesen:
                    if modus == teilen.UEBERNEHMEN and not bericht:
                        db.sicherung(zusatz="vor_Uebernahme")
                    bericht = teilen.lesen(db, modus)
                if schreiben:
                    bericht["eigene"] = teilen.schreiben(db, uebernehmen)
                break
            except teilen.ErstAbgleich as e:
                QApplication.restoreOverrideCursor()
                modus = None if fenster.stumm else _erst_frage(fenster, e)
                QApplication.setOverrideCursor(Qt.WaitCursor)
                if modus is None:
                    fenster.meldung("Abgleich abgebrochen: noch nichts geteilt.", fehler=True)
                    return None
                lesen = True
            except teilen.KuerzelBelegt as e:
                QApplication.restoreOverrideCursor()
                ja = not fenster.stumm and _belegt_frage(fenster, e)
                QApplication.setOverrideCursor(Qt.WaitCursor)
                if not ja:
                    fenster.meldung(str(e), fehler=True)
                    return None
                uebernehmen, lesen = True, False
    except (teilen.TeilenFehler, OSError) as e:
        QApplication.restoreOverrideCursor()
        if leise or fenster.stumm:
            fenster.meldung(f"Abgleich nicht möglich: {e}", fehler=True)
        else:
            QMessageBox.warning(fenster, "Abgleichen", f"Abgleich nicht möglich:\n\n{e}")
        return None
    finally:
        if QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
    bericht["nummern"] = umnummeriert
    if lesen or uebernehmen or umnummeriert:
        for i in bericht.get("entfernte_ids", ()):
            fenster.angebot_schliessen(i)
        fenster.alles_neu_laden()
    fenster.meldung(teilen.bericht_text(bericht))
    if bericht.get("hinweise") and not (leise or fenster.stumm):
        QMessageBox.information(fenster, "Abgleichen", "\n\n".join(bericht["hinweise"]))
    return bericht
