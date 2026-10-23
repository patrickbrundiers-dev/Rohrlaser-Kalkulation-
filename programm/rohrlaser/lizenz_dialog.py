"""Dialog Hilfe → Lizenz …: Zustand der Lizenz, Rechner-ID zum Kopieren, Lizenzdatei laden (auch per Drag & Drop).

Dazu lesemodus_anwenden(): Knöpfe und Eingaben einer Seite im Lesemodus sperren. Das dient der Bedienung; die
eigentliche Sicherung ist der Schreibschutz der Datenbank (datenbank.Lesemodus, PRAGMA query_only).
"""
import datetime
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from . import NAME, lizenz

STUFEN = dict(admin="Admin-Lizenz – voller Zugriff", gueltig="Lizenz gültig", bald="Lizenz läuft bald ab",
              kulanz="Lizenz abgelaufen – Kulanzzeit", lesemodus="Keine gültige Lizenz")
FARBEN = {"": ("#E8F5E9", "#2E7D32"), "gelb": ("#FFF4D6", "#E8C66B"), "rot": ("#FDECEA", "#B42318")}
LESEMODUS_TIPP = "Lesemodus: Ändern ist erst mit gültiger Lizenz möglich (Hilfe → Lizenz …)."
# Knöpfe, die auch im Lesemodus gehen: ansehen, blättern, Daten exportieren
FREI = {"Öffnen", "Angebot öffnen", "Ablage öffnen", "3D-Ansicht …", "Kalkulation anzeigen", "Alle aufklappen",
        "Schließen", "Abbrechen", "Einpassen", "◀", "▶", "Weitere Spalten", "12-m-Lösung ansehen …",
        "Frachtdaten öffnen", "Einstellungen öffnen", "Einstellungen sperren", "CSV exportieren", "Material …"}


def stufe_text(z):
    if z.admin_aus:
        return "Admin-Lizenz – ohne Admin-Rechte"
    if z.stufe == "lesemodus":
        return "Lesemodus – nur ansehen" if z.nur_lesen else "Keine gültige Lizenz (noch ohne Sperre)"
    return STUFEN.get(z.stufe, z.stufe)


def _datum(text):
    try:
        return datetime.date.fromisoformat(text).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return text or "–"


class LizenzDialog(QDialog):
    def __init__(self, fenster, stelle, stumm=False):
        super().__init__(fenster)
        self.f, self.stelle, self.stumm = fenster, stelle, stumm
        self.setWindowTitle("Lizenz")
        self.setAcceptDrops(True)
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.RichText)
        lay.addWidget(self.status)
        self.form = QFormLayout()
        lay.addLayout(self.form)
        self.rechner = QLineEdit(stelle.rechner or "nicht lesbar")
        self.rechner.setReadOnly(True)
        kopieren = QPushButton("Kopieren")
        kopieren.clicked.connect(self.kopieren)
        mail = QPushButton("E-Mail an Patrick …")
        mail.setToolTip("Fertige E-Mail mit der Rechner-ID im Mailprogramm öffnen")
        mail.clicked.connect(self.email)
        zeile = QHBoxLayout()
        zeile.addWidget(self.rechner, 1)
        zeile.addWidget(kopieren)
        zeile.addWidget(mail)
        lay.addWidget(QLabel("<b>Rechner-ID dieses Rechners</b> (für eine neue Lizenz an Patrick senden):"))
        lay.addLayout(zeile)
        hinweis = QLabel("Lizenzdatei (.lizenz) laden oder auf dieses Fenster ziehen. Eine ungültige Datei ersetzt nie "
                         "die geladene Lizenz. Die eigenen Daten bleiben immer erhalten.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color: #595959;")
        lay.addWidget(hinweis)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Close)
        laden = knoepfe.addButton("Lizenzdatei laden …", QDialogButtonBox.ActionRole)
        laden.setObjectName("primaer")
        laden.clicked.connect(lambda: self.laden())
        self.admin = knoepfe.addButton("Admin freischalten …", QDialogButtonBox.ActionRole)
        self.admin.setToolTip("Admin-Rechte mit dem Admin-Passwort (= Passwort der Einstellungen) einschalten")
        self.admin.clicked.connect(lambda: self.admin_freischalten())
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        self.anzeigen()

    def anzeigen(self):
        z = self.stelle.zustand or self.stelle.pruefen()
        self.admin.setVisible(z.admin_aus)
        hg, rand = FARBEN["rot" if z.nur_lesen else "gelb" if z.stufe == "lesemodus" else z.farbe]
        text = f"<b>{stufe_text(z)}</b>"
        if z.hinweis or z.grund:
            text += f"<br>{z.hinweis or z.grund}"
        self.status.setText(text)
        self.status.setStyleSheet(f"QLabel {{ background: {hg}; border: 1px solid {rand}; border-radius: 4px; "
                                  "padding: 8px; }")
        while self.form.rowCount():
            self.form.removeRow(0)
        i = z.inhalt or {}
        if not i:
            self.form.addRow("Lizenz:", QLabel("keine geladen"))
            return
        art = dict(admin="Admin (unbefristet)", benutzer="Benutzer", test="Testlizenz (Aufdruck TESTVERSION)")
        for titel, wert in (("Lizenz-ID:", i.get("lizenz_id")), ("Art:", art.get(i.get("art"), i.get("art"))),
                            ("Inhaber:", i.get("inhaber")), ("Firma:", i.get("firma")),
                            ("Ausgestellt:", _datum(i.get("ausgestellt"))),
                            ("Gültig:", f"{_datum(i.get('gueltig_ab'))} bis "
                                        f"{_datum(i.get('gueltig_bis')) if i.get('gueltig_bis') else 'unbefristet'}"),
                            ("Rechner:", ", ".join(i.get("rechner") or []) or "beliebig"),
                            ("Funktionen:", ", ".join(i.get("funktionen") or ["alle"])),
                            ("Hinweis:", i.get("hinweis"))):
            if wert:
                w = QLabel(str(wert))
                w.setTextInteractionFlags(Qt.TextSelectableByMouse)
                self.form.addRow(titel, w)
        if z.tage_rest is not None and z.tage_rest >= 0 and z.stufe != "admin":
            self.form.addRow("Restlaufzeit:", QLabel(f"{z.tage_rest} Tage"))

    def kopieren(self):
        QGuiApplication.clipboard().setText(self.stelle.rechner)
        if hasattr(self.f, "meldung"):
            self.f.meldung(f"Rechner-ID {self.stelle.rechner} kopiert.")

    def email_adresse(self):
        betreff = f"Lizenz {NAME} – Rechner-ID {self.stelle.rechner}"
        text = (f"Hallo Patrick,\n\nbitte eine Lizenz für {NAME} ausstellen.\n\nRechner-ID: {self.stelle.rechner}\n"
                "Name:\nFirma:\n")
        return f"mailto:{lizenz.EMAIL}?subject={quote(betreff)}&body={quote(text)}"

    def email(self):
        QDesktopServices.openUrl(QUrl(self.email_adresse()))

    def laden(self, pfad=None):
        """Lizenzdatei prüfen und übernehmen. Ergebnis: True = geladen."""
        if pfad is None:
            pfad, _ = QFileDialog.getOpenFileName(self, "Lizenzdatei laden", str(Path.home()),
                                                  "Lizenzdatei (*.lizenz);;Alle Dateien (*)")
            if not pfad:
                return False
        try:
            z = self.stelle.laden(Path(pfad))
        except lizenz.LizenzFehler as e:
            if not self.stumm:
                QMessageBox.warning(self, "Lizenz", f"Diese Lizenzdatei wurde nicht übernommen:\n\n{e}\n\n"
                                                    "Die bisherige Lizenz bleibt unverändert.")
            return False
        self.anzeigen()
        if hasattr(self.f, "lizenz_anwenden"):
            self.f.lizenz_anwenden()
        if not self.stumm:
            QMessageBox.information(self, "Lizenz", f"Lizenz übernommen: {stufe_text(z)}.\n\n{self.stelle.text()}")
        return True

    def admin_freischalten(self, passwort=None):
        """Admin-Rechte nachträglich mit dem Admin-Passwort einschalten. Ergebnis: True = freigeschaltet."""
        if passwort is None:
            passwort = admin_passwort_abfragen(self)
            if passwort is None:
                return False
        if not self.stelle.admin_freigeben(passwort):
            if not self.stumm:
                QMessageBox.warning(self, "Lizenz", "Das Admin-Passwort ist falsch.")
            return False
        self.anzeigen()
        if hasattr(self.f, "lizenz_anwenden"):
            self.f.lizenz_anwenden()
        return True

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            if url.isLocalFile():
                self.laden(url.toLocalFile())
                break


def admin_passwort_abfragen(eltern=None, versuch=0):
    """Eingabefeld für das Admin-Passwort. Ergebnis: Text oder None (abgebrochen)."""
    text = "Admin-Passwort eingeben:" if not versuch else "Passwort falsch. Bitte noch einmal:"
    wert, ok = QInputDialog.getText(eltern, f"{NAME} – Admin-Lizenz", text, QLineEdit.Password)
    return wert if ok else None


def admin_beim_start(stelle, abfragen=admin_passwort_abfragen, versuche=3):
    """Beim Start mit Admin-Lizenz: Admin-Passwort abfragen (bis zu 3 Versuche). Abbrechen oder falsch: das Programm
    startet ohne Admin-Rechte (wie mit einer Benutzerlizenz). Ergebnis: True = Admin-Rechte an."""
    if stelle is None or not stelle.admin_passwort_noetig():
        return bool(stelle and stelle.zustand and stelle.zustand.admin)
    for versuch in range(versuche):
        wert = abfragen(None, versuch)
        if wert is None:
            break
        if stelle.admin_freigeben(wert):
            return True
    stelle.admin_sperren()
    return False


def lesemodus_anwenden(widget, frei=FREI):
    """Seite im Lesemodus: Knöpfe (außer ansehen/exportieren) sperren, Tabellen nicht bearbeitbar, kein Drag & Drop."""
    widget.setAcceptDrops(False)
    for k in widget.findChildren(QPushButton):
        if k.text() not in frei and k.isEnabled():
            k.setEnabled(False)
            k.setToolTip(LESEMODUS_TIPP)
    for v in widget.findChildren(QAbstractItemView):
        v.setEditTriggers(QAbstractItemView.NoEditTriggers)
        v.setAcceptDrops(False)
