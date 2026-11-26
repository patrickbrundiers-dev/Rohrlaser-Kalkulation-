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
from .klartext import fehler_text

STUFEN = dict(admin="Admin-Lizenz – voller Zugriff", gueltig="Lizenz gültig", bald="Lizenz läuft bald ab",
              kulanz="Lizenz abgelaufen – Kulanzzeit", lesemodus="Keine gültige Lizenz")
FARBEN = {"": ("#E8F5E9", "#2E7D32"), "gelb": ("#FFF4D6", "#E8C66B"), "rot": ("#FDECEA", "#B42318")}
LESEMODUS_TIPP = "Lesemodus: Ändern ist erst mit gültiger Lizenz möglich (Hilfe → Lizenz …)."
# Knöpfe, die auch im Lesemodus gehen: ansehen, blättern, Daten exportieren
FREI = {"Öffnen", "Angebot öffnen", "Ablage öffnen", "Ordner öffnen", "3D-Ansicht …", "Kalkulation anzeigen", "Alle aufklappen",
        "Schließen", "Abbrechen", "Einpassen", "◀", "▶", "Weitere Spalten", "12-m-Lösung ansehen …",
        "Frachtdaten öffnen", "Einstellungen öffnen", "Einstellungen sperren", "CSV exportieren", "Material …", "Ausgaben",
        "Dateien im Austausch", "STEP-Viewer"}

NUR_FREIE_EINTRAEGE = {"Ausgaben"}      # Menüknöpfe, die offen bleiben, deren Einträge aber nur frei nach FREI


def stufe_text(z):
    if getattr(z, "hauptadmin", False):
        return "Hauptadmin – voller Zugriff, ohne Rechner-ID"
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
        self.admin.setToolTip("Admin-Rechte mit dem Admin-Passwort der Admin-Lizenz (ältere Admin-Lizenz: Passwort "
                              "der Einstellungen) oder einem Notfallcode einschalten")
        self.admin.clicked.connect(lambda: self.admin_freischalten())
        # Hauptadmin (hauptadmin.py): Passwort ändern und Datei für weitere eigene Rechner speichern
        self.ha_passwort = knoepfe.addButton("Passwort ändern …", QDialogButtonBox.ActionRole)
        self.ha_passwort.setToolTip("Passwort der Hauptadmin-Lizenz ändern (gilt sofort auf diesem Rechner)")
        self.ha_passwort.clicked.connect(lambda: self.hauptadmin_passwort())
        self.ha_export = knoepfe.addButton("Für weitere Rechner speichern …", QDialogButtonBox.ActionRole)
        self.ha_export.setToolTip("Aktuelle Hauptadmin-Datei (mit dem neuesten Passwort) speichern, z. B. auf einen "
                                  "USB-Stick, und am anderen Rechner hier laden")
        self.ha_export.clicked.connect(lambda: self.hauptadmin_exportieren())
        knoepfe.rejected.connect(self.reject)
        # Lizenz 2.0 (aktivierung.py): mit Lizenzschlüssel aktivieren, ohne Internet
        zeile2 = QHBoxLayout()
        self.aktivieren_knopf = QPushButton("Mit Lizenzschlüssel aktivieren …")
        self.aktivieren_knopf.setToolTip("Lizenzschlüssel LZ-… eingeben: das Programm erstellt eine Aktivierungsanfrage "
                                         "(Datei oder Code) für Patrick")
        self.aktivieren_knopf.clicked.connect(lambda: self.aktivieren())
        self.einfuegen_knopf = QPushButton("Aktivierung einfügen …")
        self.einfuegen_knopf.setToolTip("Den Aktivierungscode AKTIVIERUNG-… aus Patricks Antwort einfügen (eine "
                                        "Antwortdatei geht auch über „Lizenzdatei laden …“)")
        self.einfuegen_knopf.clicked.connect(lambda: self.aktivierung_einfuegen())
        self.freigeben_knopf = QPushButton("Platz freigeben …")
        self.freigeben_knopf.setToolTip("Diesen Rechner abmelden, z. B. vor einem PC-Wechsel: der Platz wird für einen "
                                        "anderen Rechner frei")
        self.freigeben_knopf.clicked.connect(lambda: self.platz_freigeben())
        for k in (self.aktivieren_knopf, self.einfuegen_knopf, self.freigeben_knopf):
            zeile2.addWidget(k)
        zeile2.addStretch(1)
        lay.addLayout(zeile2)
        lay.addWidget(knoepfe)
        self.anzeigen()

    def anzeigen(self):
        z = self.stelle.zustand or self.stelle.pruefen()
        self.admin.setVisible(z.admin_aus)
        aktiviert = bool(getattr(self.stelle, "aktiviert", lambda: False)())
        self.freigeben_knopf.setVisible(aktiviert)
        self.aktivieren_knopf.setVisible(hasattr(self.stelle, "aktivierung_anfragen"))
        self.einfuegen_knopf.setVisible(hasattr(self.stelle, "aktivierung_laden"))
        ha = bool(getattr(self.stelle, "hauptadmin_ok", False))
        self.ha_passwort.setVisible(ha and not getattr(self.stelle, "hauptadmin_notfall", False))
        self.ha_export.setVisible(ha)
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
        art = dict(admin="Admin (unbefristet)", benutzer="Benutzer", test="Testlizenz (Aufdruck TESTVERSION)",
                   hauptadmin="Hauptadmin (unbefristet, ohne Rechner-ID, Passwort beim Start)")
        if i.get("version") == 2:
            from .aktivierung import TYP_TEXT
            plaetze = i.get("plaetze") or 1
            for titel, wert in (("Lizenznummer:", i.get("lizenz_id")),
                                ("Lizenzart:", f"{TYP_TEXT.get(i.get('typ'), i.get('typ'))}, {plaetze} "
                                               f"Platz{'' if plaetze == 1 else 'plätze'}"
                                               + (f", {i['benutzer']} Benutzer" if i.get("benutzer") else "")),
                                ("Lizenznehmer:", ", ".join(x for x in (i.get("inhaber"), i.get("firma")) if x)),
                                ("Gültig:", f"{_datum(i.get('gueltig_ab'))} bis "
                                            f"{_datum(i.get('gueltig_bis')) if i.get('gueltig_bis') else 'unbefristet'}"),
                                ("Updates bis:", _datum(i.get("updates_bis")) if i.get("updates_bis") else ""),
                                ("Dieser Platz:", f"{i.get('aktivierung_id')} (aktiviert am {_datum(i.get('aktiviert_am'))})"),
                                ("Module:", ", ".join(i.get("funktionen") or ["alle"])),
                                ("Hinweis:", i.get("hinweis"))):
                if wert:
                    w = QLabel(str(wert))
                    w.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    self.form.addRow(titel, w)
            if z.tage_rest is not None and z.tage_rest >= 0:
                self.form.addRow("Restlaufzeit:", QLabel(f"{z.tage_rest} Tage"))
            return
        for titel, wert in (("Lizenz-ID:", i.get("lizenz_id")), ("Art:", art.get(i.get("art"), i.get("art"))),
                            ("Inhaber:", i.get("inhaber")), ("Firma:", i.get("firma")),
                            ("Ausgestellt:", _datum(i.get("ausgestellt"))),
                            ("Gültig:", "unbefristet, bis zum Sperren im Lizenz-Werkzeug" if z.hauptadmin else
                                        f"{_datum(i.get('gueltig_ab'))} bis "
                                        f"{_datum(i.get('gueltig_bis')) if i.get('gueltig_bis') else 'unbefristet'}"),
                            ("Rechner:", ", ".join(i.get("rechner") or []) or (
                                "keine Bindung – alle eigenen Rechner" if z.hauptadmin else "beliebig")),
                            ("Passwort geändert:", _datum(i.get("passwort_geaendert")) if z.hauptadmin else ""),
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

    def laden(self, pfad=None, passwort=None):
        """Lizenzdatei prüfen und übernehmen (eine Hauptadmin-Lizenz nur mit ihrem Passwort). Ergebnis: True = geladen."""
        if pfad is None:
            pfad, _ = QFileDialog.getOpenFileName(self, "Lizenzdatei laden", str(Path.home()),
                                                  "Lizenzdatei (*.lizenz *.json);;Alle Dateien (*)")
            if not pfad:
                return False
        from . import aktivierung, hauptadmin
        if hauptadmin.ist_datei(Path(pfad)) and hasattr(self.stelle, "hauptadmin_laden"):
            return self.hauptadmin_laden(pfad, passwort)
        if aktivierung.ist_format2(Path(pfad)) and hasattr(self.stelle, "aktivierung_laden"):
            return self.aktivierung_uebernehmen(Path(pfad))
        try:
            z = self.stelle.laden(Path(pfad))
        except lizenz.LizenzFehler as e:
            if not self.stumm:
                QMessageBox.warning(self, "Lizenz", f"Diese Lizenzdatei wurde nicht übernommen:\n\n{fehler_text(e)}\n\n"
                                                    "Die bisherige Lizenz bleibt unverändert.")
            return False
        self.anzeigen()
        if hasattr(self.f, "lizenz_anwenden"):
            self.f.lizenz_anwenden()
        if not self.stumm:
            QMessageBox.information(self, "Lizenz", f"Lizenz übernommen: {stufe_text(z)}.\n\n{self.stelle.text()}")
        return True

    # -------------------------------------------------------------- Lizenz 2.0
    def aktivieren(self, schluessel=None, ziel=None):
        """Lizenzschlüssel abfragen, Aktivierungsanfrage erstellen, als Datei speichern und als Code kopieren.
        Ergebnis: (Anfrage-dict, Code) oder None."""
        from . import aktivierung
        if schluessel is None:
            schluessel, ok = QInputDialog.getText(self, "Mit Lizenzschlüssel aktivieren",
                                                  "Lizenzschlüssel (LZ-XXXXX-XXXXX-XXXXX-XXXXX):")
            if not ok or not schluessel.strip():
                return None
        try:
            anfrage = self.stelle.aktivierung_anfragen(schluessel)
        except (lizenz.LizenzFehler, OSError) as e:
            if not self.stumm:
                QMessageBox.warning(self, "Aktivierung", f"Keine Anfrage erstellt:\n\n{fehler_text(e)}")
            return None
        code = aktivierung.als_code(anfrage)
        if ziel is None and not self.stumm:
            ziel, _ = QFileDialog.getSaveFileName(self, "Aktivierungsanfrage speichern",
                                                  str(Path.home() / f"Aktivierungsanfrage_{self.stelle.rechner}.json"),
                                                  "Aktivierungsanfrage (*.json)")
        if ziel:
            import json
            Path(ziel).write_text(json.dumps(anfrage, indent=1, ensure_ascii=False), encoding="utf-8")
        try:
            QGuiApplication.clipboard().setText(code)
        except Exception:        # noqa: BLE001 – ohne Zwischenablage bleibt die Datei
            pass
        if not self.stumm:
            QMessageBox.information(
                self, "Aktivierung",
                "Die Aktivierungsanfrage ist fertig" + (f" und gespeichert:\n{ziel}" if ziel else ".") +
                "\n\nDer Code ist in der Zwischenablage. Bitte Datei oder Code an Patrick senden "
                f"({lizenz.EMAIL}). Die Antwort dann hier mit „Aktivierung einfügen …“ oder "
                "„Lizenzdatei laden …“ übernehmen. Eine laufende Lizenz bleibt bis dahin gültig.")
        return anfrage, code

    def aktivierung_einfuegen(self, text=None):
        """Aktivierungscode (AKTIVIERUNG-…) einfügen. Ergebnis: True = übernommen."""
        if text is None:
            text, ok = QInputDialog.getMultiLineText(self, "Aktivierung einfügen",
                                                     "Aktivierungscode aus Patricks Antwort (AKTIVIERUNG-…):")
            if not ok or not text.strip():
                return False
        return self.aktivierung_uebernehmen(text.strip())

    def aktivierung_uebernehmen(self, quelle):
        try:
            z = self.stelle.aktivierung_laden(quelle)
        except (lizenz.LizenzFehler, OSError) as e:
            if not self.stumm:
                QMessageBox.warning(self, "Aktivierung", f"Die Aktivierung wurde nicht übernommen:\n\n{fehler_text(e)}"
                                    "\n\nDie bisherige Lizenz bleibt unverändert.")
            return False
        self.anzeigen()
        if hasattr(self.f, "lizenz_anwenden"):
            self.f.lizenz_anwenden()
        if not self.stumm:
            QMessageBox.information(self, "Aktivierung", f"Aktiviert: {stufe_text(z)}.\n\n{self.stelle.text()}")
        return True

    def platz_freigeben(self, ziel=None, bestaetigt=None):
        """Diesen Platz freigeben: Freigabebeleg speichern (für Patrick), Aktivierung entfernen. Ergebnis: Beleg."""
        from . import aktivierung
        if bestaetigt is None:
            bestaetigt = QMessageBox.question(
                self, "Platz freigeben", "Diesen Rechner von der Lizenz abmelden?\n\nDanach ist hier nur noch "
                "Ansehen möglich (oder die bisherige Lizenzdatei gilt), und der Platz wird für einen anderen Rechner "
                "frei, sobald Patrick den Freigabebeleg erhalten hat.") == QMessageBox.Yes
        if not bestaetigt:
            return None
        try:
            beleg = self.stelle.platz_freigeben()
        except (lizenz.LizenzFehler, OSError) as e:
            if not self.stumm:
                QMessageBox.warning(self, "Platz freigeben", f"Nicht freigegeben:\n\n{fehler_text(e)}")
            return None
        code = aktivierung.als_code(beleg)
        if ziel is None and not self.stumm:
            ziel, _ = QFileDialog.getSaveFileName(self, "Freigabebeleg speichern",
                                                  str(Path.home() / f"Freigabe_{beleg['inhalt']['aktivierung_id']}.json"),
                                                  "Freigabebeleg (*.json)")
        if ziel:
            import json
            Path(ziel).write_text(json.dumps(beleg, indent=1), encoding="utf-8")
        try:
            QGuiApplication.clipboard().setText(code)
        except Exception:        # noqa: BLE001
            pass
        self.anzeigen()
        if hasattr(self.f, "lizenz_anwenden"):
            self.f.lizenz_anwenden()
        if not self.stumm:
            QMessageBox.information(self, "Platz freigeben", "Platz freigegeben. Bitte den Freigabebeleg (Datei oder "
                                    "Code in der Zwischenablage) an Patrick senden.")
        return beleg

    def hauptadmin_laden(self, pfad, passwort=None):
        """Hauptadmin-Lizenz übernehmen: Signatur prüfen, Passwort abfragen, danach als Hauptadmin angemeldet."""
        if passwort is None:
            passwort, ok = QInputDialog.getText(self, "Hauptadmin-Lizenz laden", "Passwort der Hauptadmin-Lizenz:",
                                                QLineEdit.Password)
            if not ok:
                return False
        try:
            e = self.stelle.hauptadmin_laden(Path(pfad), passwort)
        except (lizenz.LizenzFehler, OSError) as f:
            if not self.stumm:
                QMessageBox.warning(self, "Lizenz", f"Die Hauptadmin-Lizenz wurde nicht übernommen:\n\n{fehler_text(f)}")
            return False
        if not e.ok:
            if not self.stumm:
                QMessageBox.warning(self, "Lizenz", f"Die Hauptadmin-Lizenz wurde nicht übernommen:\n\n{e.text}")
            return False
        self.anzeigen()
        if hasattr(self.f, "lizenz_anwenden"):
            self.f.lizenz_anwenden()
        if not self.stumm:
            QMessageBox.information(self, "Lizenz", "Hauptadmin-Lizenz übernommen. Ab jetzt fragt das Programm auf "
                                    f"diesem Rechner beim Start nach dem Passwort.\n\n{self.stelle.text()}")
        return True

    def hauptadmin_passwort(self):
        from .anmelde_fenster import PasswortAendernDialog
        d = PasswortAendernDialog(self.stelle, self)
        if self.stumm:
            return d
        if d.exec():
            self.anzeigen()
            QMessageBox.information(self, "Lizenz", "Passwort geändert. Für deine anderen Rechner bitte die Datei "
                                    "über „Für weitere Rechner speichern …“ mitnehmen und dort laden.")
        return d

    def hauptadmin_exportieren(self, ziel=None):
        from . import hauptadmin
        if ziel is None:
            ziel, _ = QFileDialog.getSaveFileName(self, "Hauptadmin-Lizenz speichern", str(Path.home() / hauptadmin.DATEI),
                                                  "Lizenzdatei (*.lizenz)")
            if not ziel:
                return None
        try:
            return self.stelle.hauptadmin_exportieren(ziel)
        except (lizenz.LizenzFehler, OSError) as f:
            if not self.stumm:
                QMessageBox.warning(self, "Lizenz", f"Nicht gespeichert: {fehler_text(f)}")
            return None

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
        if self.stelle.notfall and not self.stumm:
            QMessageBox.information(self, "Lizenz", "Mit Notfallcode freigeschaltet (nur für diese Sitzung). Bitte "
                                    "eine neue Admin-Lizenz mit neuem Admin-Passwort ausstellen und hier laden.")
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
    text = ("Admin-Passwort (oder Notfallcode) eingeben:" if not versuch
            else "Passwort falsch. Bitte noch einmal:")
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
        elif k.text() in NUR_FREIE_EINTRAEGE and k.menu() is not None:     # darin nur die freien Einträge
            for a in k.menu().actions():
                if a.text() and a.text() not in frei:
                    a.setEnabled(False)
    for v in widget.findChildren(QAbstractItemView):
        v.setEditTriggers(QAbstractItemView.NoEditTriggers)
        v.setAcceptDrops(False)
