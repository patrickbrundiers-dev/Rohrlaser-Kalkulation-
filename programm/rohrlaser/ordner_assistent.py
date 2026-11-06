"""Gemeinsamer Ordner, Paket F (Patrick 01.11.2026): Ausfall sichtbar machen, Arbeitsplatz einrichten, Ordner umziehen.

F1 Leiste oben, solange der gemeinsame Ordner nicht erreichbar ist („seit 10:42, Änderungen bleiben hier“); kommt er
zurück, gleicht das Programm gleich ab und meldet, was nachgetragen wurde (vorläufige Nummern endgültig).
F2 Assistent „Arbeitsplatz einrichten“ in drei Schritten (Ordner, Benutzer und Kürzel, erster Abgleich) und für den
Admin „Gemeinsamen Ordner umziehen“; die Kollegen sehen den Umzug im alten Ordner und stellen mit einem Klick um."""
import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QProgressDialog, QPushButton, QRadioButton, QToolBar,
                               QVBoxLayout, QWidget, QWizard, QWizardPage)

from . import admin_schutz, austausch, teilen
from .klartext import fehler_text
from .angebot import kuerzel_sauber

ROT_HG, ROT_TEXT = "#FDECEA", "#B42318"
UMSTELLEN_ANTWORT = None        # Tests: True (umstellen) / False (später) statt der Rückfrage


# ------------------------------------------------------------------ F1 Leiste „Ordner nicht erreichbar“
def _leiste(fenster):
    tb = fenster.__dict__.get("ordner_leiste")
    if tb is None:
        tb = QToolBar("Gemeinsamer Ordner", fenster)
        tb.setObjectName("ordner_leiste")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setStyleSheet(f"QToolBar {{ background: {ROT_HG}; border: 0; border-bottom: 1px solid {ROT_TEXT}; }}")
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(8, 4, 8, 4)
        tb.text = QLabel()
        tb.text.setWordWrap(True)
        tb.text.setStyleSheet(f"color: {ROT_TEXT}; font-weight: 600;")
        lay.addWidget(tb.text, 1)
        tb.erneut = QPushButton("Erneut versuchen")
        tb.erneut.clicked.connect(lambda: zustand(fenster))
        tb.umstellen = QPushButton("Auf neuen Ordner umstellen …")
        tb.umstellen.clicked.connect(lambda: umstellen_fragen(fenster, teilen.umzug(fenster.db) or {}, gefragt=True))
        lay.addWidget(tb.erneut)
        lay.addWidget(tb.umstellen)
        tb.addWidget(w)
        fenster.addToolBar(Qt.TopToolBarArea, tb)
        fenster.ordner_leiste = tb
    return tb


def _zeigen(fenster, text, umzug=False):
    tb = _leiste(fenster)
    tb.text.setText(text)
    tb.erneut.setVisible(not umzug)
    tb.umstellen.setVisible(umzug)
    tb.setVisible(True)


def _verstecken(fenster):
    tb = fenster.__dict__.get("ordner_leiste")
    if tb is not None:
        tb.setVisible(False)


def zustand(fenster, jetzt_=None):
    """Erreichbarkeit des gemeinsamen Ordners prüfen (beim Puls und mit „Erneut versuchen“). Ergebnis: "ok", "weg",
    "umzug", "zurueck" (war weg, jetzt abgeglichen) oder None (kein Ordner eingetragen)."""
    from . import teilen_fenster
    db = fenster.db
    w = teilen.weg(db)
    if w is None or not teilen.aktiv(db):
        _verstecken(fenster)
        return None
    merk = fenster.__dict__.setdefault("_ordner_zustand", {})
    jetzt_ = jetzt_ or datetime.datetime.now()
    u = teilen.umzug(db)
    if u:
        merk.setdefault("seit", jetzt_)
        if u.get("fertig"):
            _zeigen(fenster, f"⚠ Der gemeinsame Ordner ist umgezogen nach {u.get('neu')} (Admin {u.get('von') or ''}). "
                             "Bis zum Umstellen bleiben Ihre Änderungen hier.", umzug=True)
            if not merk.get("umzug_gefragt"):
                merk["umzug_gefragt"] = True
                umstellen_fragen(fenster, u)
        else:
            _zeigen(fenster, "⚠ Der Admin zieht den gemeinsamen Ordner gerade um. Ihre Änderungen bleiben hier, bis "
                             "er fertig ist.")
        return "umzug"
    if not w.erreichbar():
        seit = merk.setdefault("seit", jetzt_)
        _zeigen(fenster, f"⚠ Gemeinsamer Ordner nicht erreichbar seit {seit:%H:%M} ({w}). Ihre Änderungen bleiben "
                         "hier gespeichert und werden übertragen, sobald er wieder da ist; neue Angebote bekommen "
                         "so lange vorläufige Nummern.")
        return "weg"
    _verstecken(fenster)
    if "seit" not in merk:
        return "ok"
    seit = merk.pop("seit")
    merk.pop("umzug_gefragt", None)
    bericht = teilen_fenster.abgleichen(fenster, leise=True, auto=True)
    text = f"Gemeinsamer Ordner wieder erreichbar (weg seit {seit:%H:%M}): abgeglichen."
    if bericht and bericht.get("nummern"):
        text += " Endgültige Nummern: " + ", ".join(f"{a} → {n}" for a, n in bericht["nummern"]) + "."
    elif bericht is None:
        text = f"Gemeinsamer Ordner wieder erreichbar (weg seit {seit:%H:%M}); der Abgleich folgt gleich."
    fenster.meldung(text)
    return "zurueck"


def umstellen_fragen(fenster, u, gefragt=False):
    """Kollege nach dem Umzug: auf den neuen Ordner umstellen (gleich, anderer Pfad, später). Ergebnis: True = um-
    gestellt."""
    from . import teilen_fenster
    neu = str(u.get("neu") or "")
    if not neu:
        return False
    if UMSTELLEN_ANTWORT is not None or fenster.stumm:
        if not UMSTELLEN_ANTWORT:
            return False
    else:
        box = QMessageBox(fenster)
        box.setWindowTitle("Gemeinsamer Ordner umgezogen")
        box.setIcon(QMessageBox.Information)
        box.setText(f"Der Admin ({u.get('von') or '?'}) hat den gemeinsamen Ordner umgezogen nach:\n\n{neu}\n\n"
                    "Jetzt umstellen? Danach gleicht das Programm mit dem neuen Ordner ab; der alte wird nicht mehr "
                    "benutzt.")
        ja = box.addButton("Jetzt umstellen", QMessageBox.AcceptRole)
        anders = box.addButton("Anderen Pfad wählen …", QMessageBox.ActionRole)
        box.addButton("Später", QMessageBox.RejectRole)
        box.setDefaultButton(ja)
        box.exec()
        if box.clickedButton() is anders:
            neu = QFileDialog.getExistingDirectory(fenster, "Neuen gemeinsamen Ordner wählen", neu)
            if not neu:
                return False
        elif box.clickedButton() is not ja:
            return False
    try:
        teilen.umstellen(fenster.db, neu)
    except teilen.TeilenFehler as e:
        if fenster.stumm:
            fenster.meldung(str(e), fehler=True)
        else:
            QMessageBox.warning(fenster, "Umstellen", str(e))
        return False
    fenster.__dict__.get("_ordner_zustand", {}).pop("seit", None)
    _verstecken(fenster)
    teilen_fenster.abgleichen(fenster, leise=True)
    fenster.meldung(f"Gemeinsamer Ordner umgestellt auf {neu}.")
    return True


# ------------------------------------------------------------------ F2 Ordner umziehen (Admin)
def umziehen(fenster, ziel=None):
    """Datei → Gemeinsamen Ordner umziehen … (nur Admin, Frage 6a). Ergebnis: dict oder None."""
    from . import teilen_fenster
    db = fenster.db
    if not teilen.aktiv(db):
        fenster.meldung("Erst einen gemeinsamen Ordner eintragen (Datei → Arbeitsplatz einrichten …).", fehler=True)
        return None
    if not admin_schutz.ist_admin(db):
        text = "Den gemeinsamen Ordner zieht nur der Admin um (Datei → Als Admin freischalten …)."
        fenster.meldung(text, fehler=True) if fenster.stumm else QMessageBox.information(fenster, "Umziehen", text)
        return None
    alt = teilen.ordner(db)
    if ziel is None:
        ziel = QFileDialog.getExistingDirectory(fenster, "Neuer gemeinsamer Ordner (leer)", str(alt.parent))
        if not ziel:
            return None
        if QMessageBox.question(
                fenster, "Gemeinsamen Ordner umziehen",
                f"Alles aus\n{alt}\nnach\n{ziel}\nkopieren und diesen Arbeitsplatz umstellen?\n\nAb dem Start schreibt "
                "niemand mehr in den alten Ordner; die Kollegen bekommen das Umstellen angeboten. Der alte Ordner "
                "bleibt zur Sicherheit liegen (später von Hand löschen).") != QMessageBox.Yes:
            return None
    fortschritt = None
    dlg = None
    if not fenster.stumm:
        dlg = QProgressDialog("Gemeinsamen Ordner kopieren …", None, 0, 100, fenster)
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)

        def fortschritt(n, gesamt):
            dlg.setMaximum(max(gesamt, 1))
            dlg.setValue(n)
            QApplication.processEvents()
    try:
        erg = teilen.umziehen(db, ziel, fortschritt=fortschritt)
    except teilen.TeilenFehler as e:
        fenster.meldung(str(e), fehler=True) if fenster.stumm else QMessageBox.warning(fenster, "Umziehen", str(e))
        return None
    finally:
        if dlg is not None:
            dlg.close()
    teilen_fenster.abgleichen(fenster, leise=True)
    fenster.meldung(f"Gemeinsamer Ordner umgezogen nach {ziel}: {erg['dateien']} Dateien "
                    f"({erg['bytes'] / 1e6:.1f} MB). Die Kollegen stellen beim nächsten Abgleich um.")
    return erg


# ------------------------------------------------------------------ F2 Assistent „Arbeitsplatz einrichten“
class OrdnerSeite(QWizardPage):
    def __init__(self, a):
        super().__init__()
        self.a = a
        self.setTitle("1. Gemeinsamer Ordner")
        self.setSubTitle("Der Ordner, den alle Mitarbeiter erreichen (Netzlaufwerk, NAS oder OneDrive/SharePoint).")
        lay = QVBoxLayout(self)
        zeile = QHBoxLayout()
        self.ordner = QLineEdit(str(teilen.ordner(a.db) or ""))
        self.ordner.setPlaceholderText(r"z. B. \\server\rohrlaser oder S:\Rohrlaser")
        self.ordner.textChanged.connect(self._pruefen)
        waehlen = QPushButton("Ordner wählen …")
        waehlen.clicked.connect(self._waehlen)
        zeile.addWidget(self.ordner, 1)
        zeile.addWidget(waehlen)
        lay.addLayout(zeile)
        self.befund = QLabel()
        self.befund.setWordWrap(True)
        lay.addWidget(self.befund)
        lay.addStretch(1)
        self.kollegen = {}

    def _waehlen(self):
        p = QFileDialog.getExistingDirectory(self, "Gemeinsamen Ordner wählen", self.ordner.text().strip())
        if p:
            self.ordner.setText(str(Path(p)))

    def _pruefen(self):
        self.kollegen = {}
        o = self.ordner.text().strip()
        if not o:
            self.befund.setText("Bitte den Ordner wählen.")
        else:
            w = austausch.OrdnerWeg(o)
            u = w.umgezogen() if Path(o).is_dir() else None
            if u:
                self.befund.setText(f"Dieser Ordner ist umgezogen nach {u.get('neu')}. Bitte den neuen wählen.")
            elif not w.erreichbar():
                self.befund.setText("Den Ordner gibt es nicht oder er ist von hier nicht erreichbar.")
            else:
                for k, h in w.mitarbeiter("", kuerzel_sauber).items():
                    self.kollegen[k] = (teilen.info_lesen(h) or {}).get("name") or ""
                self.befund.setText(
                    "✓ Erreichbar. " + ("Dort arbeiten schon: " + ", ".join(
                        f"{k} {n}".strip() for k, n in sorted(self.kollegen.items())) + "."
                        if self.kollegen else "Noch leer: Sie sind der Erste, die anderen kommen dazu."))
        self.completeChanged.emit()

    def initializePage(self):
        self._pruefen()

    def isComplete(self):
        o = self.ordner.text().strip()
        return bool(o) and austausch.OrdnerWeg(o).erreichbar()


class BenutzerSeite(QWizardPage):
    def __init__(self, a):
        super().__init__()
        self.a = a
        self.setTitle("2. Benutzer und Kürzel")
        self.setSubTitle("Das Kürzel zeigt, wer ein Angebot bearbeitet; Name, E-Mail und Telefon stehen im "
                         "Angebots-PDF.")
        form = QFormLayout(self)
        db = a.db
        self.name = QLineEdit(str(db.einstellung("benutzer_name") or ""))
        self.kuerzel = QLineEdit(str(db.einstellung("benutzer_kuerzel") or ""))
        self.kuerzel.setMaxLength(5)
        self.kuerzel.setMaximumWidth(90)
        self.kuerzel.textEdited.connect(lambda t: self.kuerzel.setText(kuerzel_sauber(t)))
        self.kuerzel.textChanged.connect(self._pruefen)
        self.email = QLineEdit(str(db.einstellung("benutzer_email") or ""))
        self.telefon = QLineEdit(str(db.einstellung("benutzer_telefon") or ""))
        self.ich = QCheckBox("Das bin ich – neuer Rechner oder Neuinstallation (meine Angebote von dort übernehmen)")
        self.ich.toggled.connect(lambda _: self.completeChanged.emit())
        form.addRow("Name", self.name)
        form.addRow("Kürzel", self.kuerzel)
        form.addRow("E-Mail", self.email)
        form.addRow("Telefon", self.telefon)
        self.befund = QLabel()
        self.befund.setWordWrap(True)
        form.addRow(self.befund)
        form.addRow(self.ich)

    def initializePage(self):
        self._pruefen()

    def belegt(self):
        k = kuerzel_sauber(self.kuerzel.text())
        return k in self.a.ordner_seite.kollegen

    def _pruefen(self):
        k = kuerzel_sauber(self.kuerzel.text())
        belegt = self.belegt()
        self.ich.setVisible(belegt)
        if not k:
            self.befund.setText("Bitte ein Kürzel eintragen (Buchstaben und Ziffern, z. B. PB).")
        elif belegt:
            n = self.a.ordner_seite.kollegen.get(k)
            self.befund.setText(f"Das Kürzel {k} gibt es im Ordner schon ({n or 'ohne Name'}). Gehört es einem "
                                "Kollegen, bitte ein anderes wählen; sind Sie es selbst, den Haken setzen.")
        else:
            self.befund.setText("✓ Kürzel frei.")
        self.completeChanged.emit()

    def isComplete(self):
        return bool(kuerzel_sauber(self.kuerzel.text())) and (not self.belegt() or self.ich.isChecked())


class AbgleichSeite(QWizardPage):
    def __init__(self, a):
        super().__init__()
        self.a = a
        self.setTitle("3. Erster Abgleich")
        self.setSubTitle("Mit „Fertig“ werden die Einstellungen gespeichert und die Daten abgeglichen.")
        lay = QVBoxLayout(self)
        self.uebernehmen = QRadioButton("Gemeinsame Stammdaten übernehmen (empfohlen für einen neuen Arbeitsplatz; "
                                        "die eigenen werden vorher gesichert)")
        self.zusammen = QRadioButton("Mit den eigenen Stammdaten zusammenführen")
        self.gruppe = QButtonGroup(self)
        for b in (self.uebernehmen, self.zusammen):
            self.gruppe.addButton(b)
            lay.addWidget(b)
        self.uebernehmen.setChecked(True)
        self.text = QLabel()
        self.text.setWordWrap(True)
        lay.addWidget(self.text)
        lay.addStretch(1)

    def initializePage(self):
        andere = bool(self.a.ordner_seite.kollegen) and not (
            self.a.benutzer_seite.belegt() and len(self.a.ordner_seite.kollegen) == 1)
        self.uebernehmen.setVisible(andere)
        self.zusammen.setVisible(andere)
        self.text.setText("Angebote, Stammdaten und Nummern der Kollegen kommen danach herein; dieser Arbeitsplatz "
                          "legt seine Daten in den Ordner." if andere else
                          "Dieser Arbeitsplatz legt seine Daten als Erster in den Ordner.")


class ArbeitsplatzAssistent(QWizard):
    """Datei → Arbeitsplatz einrichten (Assistent) …: Ordner, Kürzel, erster Abgleich (Paket F2)."""

    def __init__(self, fenster):
        super().__init__(fenster)
        self.f, self.db = fenster, fenster.db
        self.setWindowTitle("Arbeitsplatz einrichten")
        self.setWizardStyle(QWizard.ClassicStyle)
        self.setButtonText(QWizard.NextButton, "Weiter >")
        self.setButtonText(QWizard.BackButton, "< Zurück")
        self.setButtonText(QWizard.FinishButton, "Fertig")
        self.setButtonText(QWizard.CancelButton, "Abbrechen")
        self.ordner_seite, self.benutzer_seite, self.abgleich_seite = (OrdnerSeite(self), BenutzerSeite(self),
                                                                       AbgleichSeite(self))
        for s in (self.ordner_seite, self.benutzer_seite, self.abgleich_seite):
            self.addPage(s)
        self.resize(640, 420)
        self.ergebnis = None

    def accept(self):
        self.ergebnis = self.ausfuehren()
        if self.ergebnis is not None:
            super().accept()

    def ausfuehren(self):
        """Speichern und abgleichen. Ergebnis: Bericht (dict) oder None (Fehler, Meldung gezeigt)."""
        db, b = self.db, self.benutzer_seite
        for n, w in (("benutzer_name", b.name.text().strip()), ("benutzer_kuerzel", kuerzel_sauber(b.kuerzel.text())),
                     ("benutzer_email", b.email.text().strip()), ("benutzer_telefon", b.telefon.text().strip()),
                     ("teilen_ordner", self.ordner_seite.ordner.text().strip())):
            db.einstellung_setzen(n, w)
        teilen.bearbeiter_nachtragen(db)
        erstmals = not db.con.execute("SELECT 1 FROM teilen_basis LIMIT 1").fetchone()
        modus = (teilen.UEBERNEHMEN if self.abgleich_seite.uebernehmen.isChecked() else teilen.ZUSAMMENFUEHREN)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            if erstmals and modus == teilen.UEBERNEHMEN and teilen.andere_dateien(db):
                db.sicherung(zusatz="vor_Uebernahme")
            bericht = teilen.lesen(db, modus if erstmals else None)
            bericht["eigene"] = teilen.schreiben(db, uebernehmen=b.belegt() and b.ich.isChecked())
        except (teilen.TeilenFehler, OSError) as e:
            QApplication.restoreOverrideCursor()
            if self.f.stumm:
                self.f.meldung(str(e), fehler=True)
            else:
                QMessageBox.warning(self, "Arbeitsplatz einrichten", f"Abgleich nicht möglich:\n\n{fehler_text(e)}")
            return None
        finally:
            if QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
        self.f.alles_neu_laden()
        self.f.meldung("Arbeitsplatz eingerichtet: " + teilen.bericht_text(bericht))
        return bericht


def assistent(fenster):
    a = ArbeitsplatzAssistent(fenster)
    if not fenster.stumm:
        a.exec()
    return a
