"""Menü „Hauptadmin“ im Hauptfenster (nur sichtbar, wenn als Hauptadmin angemeldet; hauptadmin.py).

Bündelt, was nur der Hauptadmin braucht: Passwort und Lizenzdatei, Rechte und Schutz (springt auf die vorhandenen
Seiten Arbeitsplätze und Rechte, Admin-Schutz, Funktionen), Einstellungen sichern/wiederherstellen/zurücksetzen (immer
mit Datensicherung vorher) und Diagnose (Protokoll, Lizenzordner, Systemprüfung,
Rechenzähler, Support-Paket). Die Rechte selbst
prüft weiter admin_schutz.py (Hauptadmin = als Admin freigeschaltet, auf allen Seiten).
"""
import datetime
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFontDatabase
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QLabel, QMessageBox, QPlainTextEdit,
                               QPushButton, QVBoxLayout)

from . import einstellungen_sicherung as ES
from . import hauptadmin as H
from .klartext import fehler_text


def einrichten(f):
    """Menü an die Menüleiste des Hauptfensters f hängen (zunächst unsichtbar). Ergebnis: das Menü."""
    m = f.menuBar().addMenu("Haupt&admin")
    f.hauptadmin_aktionen = {}
    for text, ziel in (("Passwort ändern …", lambda: passwort_aendern(f)),
                       ("Hauptadmin-Datei für weitere Rechner speichern …", lambda: datei_speichern(f)),
                       ("Lizenz …", lambda: f.lizenz_zeigen()),
                       (None, None),
                       ("Arbeitsplätze und Rechte", lambda: seite_zeigen(f, "plaetze_seite")),
                       ("Admin-Schutz der Einstellungen", lambda: seite_zeigen(f, "admin_seite")),
                       ("Funktionen ein/aus", lambda: funktionen_zeigen(f)),
                       (None, None),
                       ("Einstellungen sichern …", lambda: einstellungen_sichern(f)),
                       ("Einstellungen wiederherstellen …", lambda: einstellungen_wiederherstellen(f)),
                       ("Einstellungen auf Vorgabe zurücksetzen …", lambda: einstellungen_zuruecksetzen(f)),
                       (None, None),
                       ("Protokollordner öffnen", lambda: ordner_oeffnen(f.db.pfad.parent / "Protokoll")),
                       ("Lizenzordner öffnen", lambda: ordner_oeffnen(f.lizenz.ordner if f.lizenz else None)),
                       ("Systemprüfung …", lambda: f.systempruefung_zeigen()),
                       ("Diagnose: Rechenzähler …", lambda: diagnose_fenster(f)),
                       ("Support-Paket erstellen …", lambda: f.support_paket()),
                       (None, None),
                       ("Abmelden und beenden", lambda: abmelden(f))):
        if text is None:
            m.addSeparator()
            continue
        a = QAction(text, f)
        a.triggered.connect(ziel)
        m.addAction(a)
        f.hauptadmin_aktionen[text] = a
    m.menuAction().setVisible(False)
    f.hauptadmin_menue = m
    return m


def anwenden(f, z):
    """Menü zeigen, wenn als Hauptadmin angemeldet (z: lizenz.Zustand oder None)."""
    m = getattr(f, "hauptadmin_menue", None)
    if m is None:
        return
    an = bool(z is not None and getattr(z, "hauptadmin", False))
    m.menuAction().setVisible(an)
    a = f.hauptadmin_aktionen.get("Passwort ändern …")
    if a is not None:
        a.setEnabled(an and not getattr(f.lizenz, "hauptadmin_notfall", False))


def _ja(f, titel, text):
    if f.stumm:
        return True
    return QMessageBox.question(f, titel, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes


def passwort_aendern(f):
    from .anmelde_fenster import PasswortAendernDialog
    d = PasswortAendernDialog(f.lizenz, f)
    if not f.stumm and d.exec():
        f.lizenz_anwenden()
        f.meldung("Hauptadmin-Passwort geändert. Für weitere Rechner: Hauptadmin → Hauptadmin-Datei … speichern.")
    return d


def datei_speichern(f, ziel=None):
    if ziel is None:
        ziel, _ = QFileDialog.getSaveFileName(f, "Hauptadmin-Lizenz speichern", str(Path.home() / H.DATEI),
                                              "Lizenzdatei (*.lizenz)")
        if not ziel:
            return None
    try:
        p = f.lizenz.hauptadmin_exportieren(ziel)
    except (H.HauptadminFehler, OSError) as e:
        f.meldung(f"Hauptadmin-Datei nicht gespeichert: {fehler_text(e)}", fehler=True)
        return None
    f.meldung(f"Hauptadmin-Datei gespeichert: {p} – am anderen Rechner über Hilfe → Lizenz … laden.")
    return p


def seite_zeigen(f, attr):
    seite = getattr(f, attr, None)
    if seite is not None:
        f.zeigen(seite)
    return seite


class DiagnoseFenster(QDialog):
    """Hauptadmin → Diagnose: Rechenzähler … (Stabilität 18.11.2026): wie oft und wie lange gerechnet wurde, unnötige
    Mehrfachberechnungen, Merker-Treffer, Datenbank, Fehler, Speicher (diagnose.bericht)."""

    def __init__(self, eltern=None):
        super().__init__(eltern)
        self.setWindowTitle("Diagnose: Rechenzähler")
        self.resize(860, 560)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Zähler seit dem Programmstart. „doppelt“ zeigt Rechnungen, die mit genau denselben "
                             "Eingaben noch einmal liefen; der Bericht liegt auch im Support-Paket (diagnose.txt)."))
        self.text = QPlainTextEdit(readOnly=True)
        self.text.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        lay.addWidget(self.text)
        knoepfe = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        for name, tun in (("Aktualisieren", self.aktualisieren), ("Zähler zurücksetzen", self.zuruecksetzen)):
            b = QPushButton(name)
            b.clicked.connect(tun)
            knoepfe.addButton(b, QDialogButtonBox.ButtonRole.ActionRole)
        knoepfe.rejected.connect(self.close)
        lay.addWidget(knoepfe)
        self.aktualisieren()

    def aktualisieren(self):
        from . import diagnose
        self.text.setPlainText(diagnose.bericht())

    def zuruecksetzen(self):
        from . import diagnose
        diagnose.zuruecksetzen()
        self.aktualisieren()


def diagnose_fenster(f, zeigen=True):
    d = DiagnoseFenster(f)
    if zeigen:
        d.show()
    f._diagnose_fenster = d         # bleibt offen, solange es angezeigt wird
    return d


def funktionen_zeigen(f):
    from . import einstellungen_nav
    nav = f.bereich.unter
    for i in range(nav.count()):
        if einstellungen_nav.schluessel(nav.widget(i)) == "e_funktionen":
            f.zeigen(nav.widget(i))
            return nav.widget(i)
    return None


def einstellungen_sichern(f, ziel=None):
    if ziel is None:
        vorschlag = Path.home() / f"Rohrlaser-Einstellungen {datetime.date.today():%Y-%m-%d}.json"
        ziel, _ = QFileDialog.getSaveFileName(f, "Einstellungen sichern", str(vorschlag), "Einstellungen (*.json)")
        if not ziel:
            return None
    n = ES.einstellungen_sichern(f.db, ziel)
    f.meldung(f"{n} Einstellungen gesichert: {ziel}")
    return n


def einstellungen_wiederherstellen(f, quelle=None):
    if quelle is None:
        quelle, _ = QFileDialog.getOpenFileName(f, "Einstellungen wiederherstellen", str(Path.home()),
                                                "Einstellungen (*.json)")
        if not quelle:
            return None
    if not _ja(f, "Einstellungen wiederherstellen", "Die Einstellungen aus der Datei übernehmen? Vorher wird eine "
                                                    "Datensicherung angelegt."):
        return None
    try:
        n, sicherung = ES.einstellungen_wiederherstellen(f.db, quelle)
    except (H.HauptadminFehler, OSError) as e:
        f.meldung(f"Einstellungen nicht übernommen: {fehler_text(e)}", fehler=True)
        return None
    _neu_laden(f)
    f.meldung(f"{n} Einstellungen übernommen (Sicherung vorher: {Path(sicherung).name}).")
    return n


def einstellungen_zuruecksetzen(f):
    if not _ja(f, "Einstellungen zurücksetzen", "Alle Einstellungen auf die Vorgabe zurücksetzen? Preise, Maschinen, "
                                               "Material und Angebote bleiben. Passwort, Nummern, Kürzel und Ordner "
                                               "bleiben auch. Vorher wird eine Datensicherung angelegt."):
        return None
    try:
        n, sicherung = ES.einstellungen_zuruecksetzen(f.db)
    except OSError as e:
        f.meldung(f"Nicht zurückgesetzt: {fehler_text(e)}", fehler=True)
        return None
    _neu_laden(f)
    f.meldung(f"{n} Einstellungen auf die Vorgabe gesetzt (Sicherung vorher: {Path(sicherung).name}).")
    return n


def _neu_laden(f):
    for ziel in (getattr(f, "einstellungen", None), getattr(f, "bereich", None)):
        if hasattr(ziel, "neu_laden"):
            try:
                ziel.neu_laden()
            except Exception:       # noqa: BLE001 – Anzeige; die Werte stehen in der Datendatei
                pass
    if hasattr(f, "funktionen_anwenden"):
        f.funktionen_anwenden()


def ordner_oeffnen(pfad):
    if pfad is None:
        return False
    Path(pfad).mkdir(parents=True, exist_ok=True)
    return QDesktopServices.openUrl(QUrl.fromLocalFile(str(pfad)))


def abmelden(f):
    """Hauptadmin abmelden und das Programm schließen (beim nächsten Start wieder mit Passwort)."""
    if f.lizenz is not None:
        f.lizenz.hauptadmin_abmelden()
    f.close()
