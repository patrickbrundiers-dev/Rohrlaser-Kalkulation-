"""Oberfläche zu teilen.py: Dialog „Benutzer und gemeinsamer Ordner“ und der Abgleich aus dem Hauptfenster (Knopf,
Programmstart, Beenden, alle paar Minuten von selbst) mit den Rückfragen beim ersten Abgleich und bei einem schon
belegten Kürzel; Anzeige in der Statusleiste, Angebot übergeben, Übernahme anfragen und beantworten, Konflikte."""
import datetime
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtCore import QDate
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QVBoxLayout, QWidget)

from . import nummern, stil, teilen
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
                      "Stammdaten. Abgeglichen wird beim Start, beim Beenden, mit dem Knopf „Abgleichen“ und alle "
                      "paar Minuten von selbst (Einstellung „Automatischer Abgleich alle [min]“).")
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


def offen_nummern(fenster, beenden=False):
    """{Nummer: seit} der hier geöffneten eigenen Angebote (für die Kollegen: wer arbeitet woran)."""
    merk = fenster.__dict__.setdefault("_teilen_offen_seit", {})
    if beenden:
        return {}
    jetzt = datetime.datetime.now().isoformat(timespec="minutes")
    out = {}
    for seite in fenster.offen.values():
        kopf = getattr(seite, "kopf", None) or {}
        nr = kopf.get("nummer")
        if nr and not kopf.get("fremd"):
            out[nr] = merk.get(nr) or jetzt
    merk.clear()
    merk.update(out)
    return out


def status_setzen(fenster, text, tipp="", fehler=False):
    """Stand des Abgleichs rechts in der Statusleiste („⇄ abgeglichen 14:32“)."""
    lab = getattr(fenster, "teilen_status", None)
    if lab is None:
        lab = fenster.teilen_status = QLabel()
        lab.setTextFormat(Qt.PlainText)
        fenster.statusBar().addPermanentWidget(lab)
    lab.setText(text)
    lab.setToolTip(tipp)
    lab.setStyleSheet("color: #B42318; padding: 0 6px;" if fehler else "padding: 0 6px;")
    lab.setVisible(bool(text))


def _status_nach(fenster, bericht):
    db = fenster.db
    wer = []
    for k, m in sorted((db.einstellung("teilen_mitarbeiter") or {}).items()):
        if k != teilen.kuerzel(db):
            wer.append(f"{k} {m.get('name') or ''}: Stand {(m.get('stand') or '?').replace('T', ' ')}")
    offen = len(teilen.konflikte(db, offen_nur=True))
    from . import ordner_pruefung       # Uhr, doppelte Nummern, Konfliktkopien (Paket A, 31.10.2026)
    try:
        warnung = ordner_pruefung.kurz(db)
    except OSError:
        warnung = []
    tipp = "Gemeinsamer Ordner: " + str(teilen.ordner(db)) + ("\n" + "\n".join(wer) if wer else "")
    if warnung:
        tipp += "\n\n⚠ " + "\n⚠ ".join(warnung) + "\nEinzelheiten: Datei → Gemeinsamen Ordner prüfen …"
    status_setzen(fenster, f"⇄ abgeglichen {datetime.datetime.now():%H:%M}" + (f" · {offen} Konflikte" if offen else "")
                  + (" · ⚠ " + ", ".join(warnung) if warnung else ""), tipp)


def _neu_laden(fenster, bericht, voll):
    """Nach dem Abgleich: voll = alles neu laden (Knopf, Start); sonst (automatischer Abgleich) nur, was sich geändert
    hat, damit die Arbeit im offenen Angebot nicht gestört wird."""
    for i in bericht.get("entfernte_ids", ()):
        fenster.angebot_schliessen(i)
    if voll:
        fenster.alles_neu_laden()
        return
    anwesend = teilen.kollegen_offen(fenster.db)               # wer gerade was geöffnet hat (● geöffnet)
    anders = anwesend != fenster.__dict__.get("_teilen_anwesend")
    fenster._teilen_anwesend = anwesend
    if (bericht.get("angebote_neu") or bericht.get("angebote_geaendert") or bericht.get("angebote_weg")
            or bericht.get("uebernommen") or bericht.get("nummern") or bericht.get("notizen")):
        fenster.start.neu_laden()
        fenster.angebote.neu_laden()
        fenster.versand.neu_laden()
        for i in bericht.get("geaenderte_ids", ()):
            if i in fenster.offen:
                fenster.offen[i].neu_laden()
    elif anders:
        fenster.angebote.neu_laden()
    if anders:
        for seite in fenster.offen.values():
            if (getattr(seite, "kopf", None) or {}).get("fremd"):
                seite._fremd_anzeigen()
    if bericht.get("stammdaten") or bericht.get("admin_vorgaben"):
        for s in fenster.seiten:
            s.neu_laden()
        for s in (fenster.zukauf, fenster.zusatz, fenster.einstellungen, fenster.fracht):
            s.neu_laden()
    if bericht.get("admin_vorgaben"):       # Schutzliste und Funktionen können sich geändert haben
        fenster.funktionen_anwenden()
        fenster.bereich.schutz_anwenden()


def _vorgaenge_zeigen(fenster, bericht, leise):
    """Übernommene Angebote, Absagen und Anfragen der Kollegen. Anfragen werden gefragt (übergeben, ablehnen, später);
    nach einer Antwort geht sie gleich in den gemeinsamen Ordner."""
    db = fenster.db
    texte = []
    for u in bericht.get("uebernommen", ()):
        texte.append(f"{_name(db, u['von'])} hat Ihnen Angebot {u['nummer']} übergeben" +
                     (f": „{u['notiz']}“" if u.get("notiz") else "."))
    for n in bericht.get("notizen", ()):
        texte.append(f"Notiz von {_name(db, n['von'])}" + (f" zu Angebot {n['nummer']}" if n.get("nummer") else "")
                     + f": „{n['notiz']}“" + (f" (Wiedervorlage {_datum(n['faellig'])})" if n.get("faellig") else ""))
    for a in bericht.get("abgelehnt", ()):
        texte.append(f"{_name(db, a['von'])} gibt Angebot {a['nummer']} nicht ab" +
                     (f": „{a['notiz']}“" if a.get("notiz") else "."))
    if texte:
        fenster.meldung(" ".join(texte))
        if not (leise or fenster.stumm):
            QMessageBox.information(fenster, "Kollegen", "\n\n".join(texte))
    if fenster.stumm or not bericht.get("anfragen"):
        return
    beantwortet = False
    for a in bericht["anfragen"]:
        antwort = anfrage_fragen(fenster, a)
        if antwort is None:
            continue
        try:
            teilen.beantworten(db, a, *antwort)
            beantwortet = True
        except teilen.TeilenFehler as e:
            fenster.meldung(str(e), fehler=True)
    if beantwortet:
        try:
            teilen.schreiben(db, offen=offen_nummern(fenster))
        except (teilen.TeilenFehler, OSError) as e:
            fenster.meldung(f"Antwort kommt beim nächsten Abgleich an: {e}", fehler=True)
        fenster.alles_neu_laden()


def _datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso)).strftime("%d.%m.%Y")
    except ValueError:
        return str(iso or "")


def _name(db, k):
    n = teilen.mitarbeiter(db, k).get("name")
    return f"{n} ({k})" if n else k


def anfrage_fragen(fenster, a):
    """Rückfrage zu einer Anfrage: (True, Notiz) übergeben, (False, Notiz) ablehnen, None = später."""
    kopf = fenster.db.angebot(a["angebot_id"]) or {}
    box = QMessageBox(fenster)
    box.setWindowTitle("Angebot übergeben?")
    box.setIcon(QMessageBox.Question)
    box.setText(f"{_name(fenster.db, a['von'])} möchte Ihr Angebot {a['nummer']} ({kopf.get('kunde') or 'ohne Kunde'}) "
                "übernehmen." + (f"\n\nNotiz: „{a['notiz']}“" if a.get("notiz") else "") +
                "\n\nÜbergeben: das Angebot gehört danach dem Kollegen, Sie können es nur noch ansehen.")
    ja = box.addButton("Übergeben", QMessageBox.AcceptRole)
    nein = box.addButton("Ablehnen …", QMessageBox.RejectRole)
    box.addButton("Später", QMessageBox.DestructiveRole)
    box.setDefaultButton(ja)
    box.exec()
    if box.clickedButton() is ja:
        return True, ""
    if box.clickedButton() is nein:
        notiz, gut = QInputDialog.getText(fenster, "Ablehnen", "Kurze Begründung für den Kollegen (darf leer sein):")
        return (False, notiz.strip()) if gut else None
    return None


class UebergebenDialog(QDialog):
    """Kollegen und Notiz für die Übergabe eines Angebots wählen."""
    def __init__(self, fenster, nummer):
        super().__init__(fenster)
        self.setWindowTitle(f"Angebot {nummer} übergeben")
        form = QFormLayout(self)
        text = QLabel("Das Angebot gehört danach dem Kollegen; er übernimmt es beim nächsten Abgleich (spätestens "
                      "nach ein paar Minuten). Sie können es weiter ansehen und, solange er es noch nicht übernommen "
                      "hat, zurücknehmen.")
        text.setWordWrap(True)
        form.addRow(text)
        self.wer = QComboBox()
        for k, name in teilen.kollegen(fenster.db).items():
            self.wer.addItem(f"{k} – {name}" if name else k, k)
        self.notiz = QLineEdit()
        self.notiz.setPlaceholderText("z. B. bitte fertig rechnen, Kunde ruft morgen an")
        form.addRow("An", self.wer)
        form.addRow("Notiz", self.notiz)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Übergeben")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)


class NotizDialog(QDialog):
    """Notiz an einen Kollegen, wahlweise mit Wiedervorlage-Datum."""
    def __init__(self, fenster, nummer=None):
        super().__init__(fenster)
        self.setWindowTitle("Notiz an Kollegen" + (f" zu Angebot {nummer}" if nummer else ""))
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        self.wer = QComboBox()
        for k, name in teilen.kollegen(fenster.db).items():
            self.wer.addItem(f"{k} – {name}" if name else k, k)
        self.text = QLineEdit()
        self.text.setPlaceholderText("z. B. bitte Preis prüfen, Kunde ruft Freitag an")
        self.mit_datum = QCheckBox("Wiedervorlage am")
        self.datum = QDateEdit(QDate.currentDate().addDays(1))
        self.datum.setCalendarPopup(True)
        self.datum.setEnabled(False)
        self.mit_datum.toggled.connect(self.datum.setEnabled)
        zeile = QWidget()
        zl = QHBoxLayout(zeile)
        zl.setContentsMargins(0, 0, 0, 0)
        zl.addWidget(self.mit_datum)
        zl.addWidget(self.datum)
        zl.addStretch(1)
        form.addRow("An", self.wer)
        form.addRow("Notiz", self.text)
        form.addRow("", zeile)
        knoepfe = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        knoepfe.button(QDialogButtonBox.Ok).setText("Senden")
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        form.addRow(knoepfe)

    def faellig(self):
        return self.datum.date().toString("yyyy-MM-dd") if self.mit_datum.isChecked() else None


def notiz_senden(fenster, angebot_id=None, an=None, text="", faellig=None, vorschlag=None):
    """Notiz an einen Kollegen (ohne an: Dialog), gleich in den gemeinsamen Ordner. Ergebnis: True = gesendet."""
    db = fenster.db
    nummer = (db.angebot(angebot_id) or {}).get("nummer") if angebot_id else None
    if not teilen.aktiv(db) or not teilen.kollegen(db):
        fenster.meldung("Notizen gehen nur mit gemeinsamem Ordner und Kollegen darin.", fehler=True)
        return False
    if an is None:
        d = NotizDialog(fenster, nummer)
        if vorschlag and d.wer.findData(vorschlag) >= 0:
            d.wer.setCurrentIndex(d.wer.findData(vorschlag))
        if fenster.stumm or d.exec() != QDialog.Accepted:
            return False
        an, text, faellig = d.wer.currentData(), d.text.text(), d.faellig()
    try:
        teilen.notiz_senden(db, an, text, nummer, faellig)
    except teilen.TeilenFehler as e:
        fenster.meldung(str(e), fehler=True)
        return False
    fenster.meldung(f"Notiz an {an} gesendet" + (f" (Angebot {nummer})." if nummer else "."))
    abgleichen(fenster, lesen=False, leise=True)
    return True


def uebergeben(fenster, angebot_id, an=None, notiz=""):
    """Angebot an einen Kollegen übergeben (ohne an: Dialog) und gleich abgleichen. Ergebnis: True = übergeben."""
    db = fenster.db
    a = db.angebot(angebot_id) or {}
    if not teilen.aktiv(db):
        fenster.meldung("Übergeben geht nur mit gemeinsamem Ordner (Datei → Benutzer und gemeinsamer Ordner …).",
                        fehler=True)
        return False
    if an is None:
        if not teilen.kollegen(db):
            fenster.meldung("Im gemeinsamen Ordner gibt es noch keine Kollegen.", fehler=True)
            return False
        d = UebergebenDialog(fenster, a.get("nummer"))
        if fenster.stumm or d.exec() != QDialog.Accepted:
            return False
        an, notiz = d.wer.currentData(), d.notiz.text().strip()
    try:
        teilen.uebergeben(db, angebot_id, an, notiz)
    except teilen.TeilenFehler as e:
        fenster.meldung(str(e), fehler=True)
        return False
    fenster.meldung(f"Angebot {a.get('nummer')} an {an} übergeben.")
    abgleichen(fenster, lesen=False, leise=True)
    fenster.alles_neu_laden()
    return True


def zuruecknehmen(fenster, angebot_id):
    if not teilen.zuruecknehmen(fenster.db, angebot_id):
        fenster.meldung("Der Kollege hat das Angebot schon übernommen.", fehler=True)
        return False
    fenster.meldung("Übergabe zurückgenommen: das Angebot gehört wieder Ihnen.")
    abgleichen(fenster, lesen=False, leise=True)
    fenster.alles_neu_laden()
    return True


def anfragen(fenster, angebot_id, notiz=None):
    """Übernahme eines Angebots beim Bearbeiter anfragen (ohne notiz: Eingabe) und gleich abgleichen."""
    a = fenster.db.angebot(angebot_id) or {}
    if notiz is None:
        if fenster.stumm:
            notiz = ""
        else:
            notiz, gut = QInputDialog.getText(fenster, "Übernahme anfragen",
                                              f"{_name(fenster.db, a.get('fremd'))} wird beim nächsten Abgleich "
                                              f"gefragt, ob er Ihnen Angebot {a.get('nummer')} übergibt.\n\n"
                                              "Notiz (darf leer sein):")
            if not gut:
                return False
    try:
        teilen.anfragen(fenster.db, angebot_id, notiz.strip())
    except teilen.TeilenFehler as e:
        fenster.meldung(str(e), fehler=True)
        return False
    fenster.meldung(f"Übernahme von Angebot {a.get('nummer')} bei {a.get('fremd')} angefragt.")
    abgleichen(fenster, lesen=False, leise=True)
    for seite in fenster.offen.values():
        if getattr(seite, "id", None) == angebot_id:
            seite._fremd_anzeigen()
    return True


class KonflikteDialog(QDialog):
    """Abgleich-Konflikte: welche Zeile, wer gewann, verlorene Fassung wiederherstellen oder als gesehen markieren."""
    def __init__(self, fenster):
        super().__init__(fenster)
        self.f, self.db = fenster, fenster.db
        self.setWindowTitle("Abgleich-Konflikte")
        self.resize(720, 420)
        lay = QVBoxLayout(self)
        text = QLabel("Dieselben Stammdaten wurden hier und bei einem Kollegen seit dem letzten Abgleich verschieden "
                      "geändert. Es gilt die jüngere Änderung. Die andere Fassung lässt sich hier wiederherstellen; sie "
                      "geht dann beim nächsten Abgleich an alle.")
        text.setWordWrap(True)
        lay.addWidget(text)
        self.liste = QListWidget()
        lay.addWidget(self.liste, 1)
        self.einzeln = QLabel()                 # abweichende Werte des gewählten Konflikts
        self.einzeln.setWordWrap(True)
        self.einzeln.setTextFormat(Qt.PlainText)
        lay.addWidget(self.einzeln)
        zeile = QHBoxLayout()
        self.zurueck = QPushButton("Andere Fassung wiederherstellen")
        self.zurueck.clicked.connect(lambda: self._erledigt(True))
        self.gesehen = QPushButton("So lassen (gesehen)")
        self.gesehen.clicked.connect(lambda: self._erledigt(False))
        zu = QPushButton("Schließen")
        zu.clicked.connect(self.accept)
        for b in (self.zurueck, self.gesehen):
            zeile.addWidget(b)
        zeile.addStretch(1)
        zeile.addWidget(zu)
        lay.addLayout(zeile)
        self.liste.currentRowChanged.connect(lambda _: self._knoepfe())
        self.laden()

    def laden(self):
        self.liste.clear()
        for k in teilen.konflikte(self.db):
            it = QListWidgetItem(konflikt_text(k))
            it.setData(Qt.UserRole, k["id"])
            it.setToolTip(_unterschied(k))
            if k.get("erledigt"):
                it.setForeground(stil.farbe(stil.TEXT_GRAU))
            self.liste.addItem(it)
        self._knoepfe()

    def _knoepfe(self):
        k = self._gewaehlt()
        for b in (self.zurueck, self.gesehen):
            b.setEnabled(bool(k) and not k.get("erledigt"))
        self.einzeln.setText(_unterschied(k) if k else "")

    def _gewaehlt(self):
        it = self.liste.currentItem()
        kid = it.data(Qt.UserRole) if it else None
        return next((k for k in teilen.konflikte(self.db) if k["id"] == kid), None)

    def _erledigt(self, wiederherstellen):
        k = self._gewaehlt()
        if k and teilen.konflikt_erledigt(self.db, k["id"], wiederherstellen):
            if wiederherstellen:
                self.f.alles_neu_laden()
                self.f.meldung(f"Wiederhergestellt: {k['text']} (geht beim nächsten Abgleich an alle).")
            zeile = self.liste.currentRow()
            self.laden()
            self.liste.setCurrentRow(zeile)
            _status_nach(self.f, {})


def konflikt_text(k):
    try:
        zeit = datetime.datetime.fromisoformat(k.get("zeit") or "").strftime("%d.%m.%Y %H:%M")
    except ValueError:
        zeit = ""
    stand = "wiederhergestellt" if k.get("wiederhergestellt") else "gesehen" if k.get("erledigt") else "offen"
    return f"{zeit}  {k.get('text')}: gilt die Änderung von {k.get('gewinner')}, die von {k.get('verlierer')} " \
           f"ging verloren ({stand})"


def _unterschied(k):
    a, b = k.get("gewonnen") or {}, k.get("verloren") or {}
    if a is None or b is None or not isinstance(a, dict) or not isinstance(b, dict):
        return "gelöscht" if not a else ""
    t = teilen.GETEILT_NAME.get(k.get("tabelle"))
    titel = {f.name: f.titel for f in getattr(t, "felder", ())}
    zeilen = [f"{titel.get(n, n)}: gilt „{a.get(n) if a.get(n) is not None else ''}“, verloren „"
              f"{b.get(n) if b.get(n) is not None else ''}“" for n in sorted(set(a) | set(b)) if a.get(n) != b.get(n)]
    return "\n".join(zeilen[:20])


def konflikte_zeigen(fenster):
    d = KonflikteDialog(fenster)
    if not fenster.stumm:
        d.exec()
    return d


def auto_abgleich(fenster):
    """Zeitgeber alle paar Minuten: nur lesen, wenn sich eine Datei der Kollegen geändert hat, nur schreiben, wenn sich
    hier etwas geändert hat (oder die geöffneten Angebote), sonst spätestens alle HERZSCHLAG_S, damit die Kollegen
    sehen, woran man gerade arbeitet. Nicht während eines Dialogs. Ergebnis: Bericht, None (nichts zu tun) oder False."""
    db = fenster.db
    if db.nur_lesen or not teilen.aktiv(db) or getattr(fenster, "step_drop_laeuft", False):
        return None
    if QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None:
        return None
    merk = fenster.__dict__.setdefault("_teilen_auto", {})
    try:
        stand = teilen.dateien_stand(db)
    except (teilen.TeilenFehler, OSError) as e:
        status_setzen(fenster, "⇄ Ordner nicht erreichbar", str(e), fehler=True)
        return False
    offen = offen_nummern(fenster)
    lesen = stand != merk.get("stand")
    schreiben = (db.con.total_changes != merk.get("aenderungen") or offen != merk.get("offen")
                 or time.monotonic() - merk.get("geschrieben", 0) >= HERZSCHLAG_S)
    if not (lesen or schreiben):
        return None
    bericht = abgleichen(fenster, lesen=lesen, schreiben=schreiben, leise=True, auto=True)
    if bericht is None:
        return False
    merk.update(stand=teilen.dateien_stand(db), offen=offen, aenderungen=db.con.total_changes)
    if schreiben:
        merk["geschrieben"] = time.monotonic()
    return bericht


HERZSCHLAG_S = 10 * 60      # spätestens so oft schreiben (geöffnete Angebote gelten FRISCH_MIN lang)
PULS_TICK_MS = 15_000       # Takt für Lebenszeichen und Sofort-Schreiben (Paket B, 31.10.2026)


def puls(fenster, jetzt_=None):
    """Alle PULS_TICK_MS (Paket B): eigenes Lebenszeichen höchstens alle teilen.PULS_S schreiben und die der Kollegen
    lesen (wer ist da, wer hat welches Angebot offen); hat sich dabei etwas geändert, die Angebotsliste neu zeichnen.
    Sofort schreiben: gibt es hier Änderungen, die noch nicht im Ordner liegen, und ruht die Eingabe seit dem letzten
    Takt, werden sie gleich abgelegt (nur geänderte Monatsdateien), nicht erst beim nächsten Abgleich.
    Ergebnis: dict(lebenszeichen, geschrieben) oder None (nichts zu tun)."""
    db = fenster.db
    if db.nur_lesen or not teilen.aktiv(db) or not teilen.kuerzel(db) or getattr(fenster, "step_drop_laeuft", False):
        return None
    merk = fenster.__dict__.setdefault("_teilen_puls", {})
    jetzt_ = time.monotonic() if jetzt_ is None else jetzt_
    erg = dict(lebenszeichen=False, geschrieben=False)
    auto = fenster.__dict__.setdefault("_teilen_auto", {})
    vorher_c = db.con.total_changes
    if jetzt_ - merk.get("zeichen", -1e9) >= teilen.PULS_S - 1:
        try:
            vorher = teilen.kollegen_offen(db)
            erg["lebenszeichen"] = teilen.lebenszeichen_schreiben(db, offen_nummern(fenster))
            online = teilen.lebenszeichen_lesen(db)
            merk["zeichen"] = jetzt_
            stand = {k: v["online"] for k, v in online.items()}
            if teilen.kollegen_offen(db) != vorher or stand != merk.get("online"):
                merk["online"] = stand
                liste = getattr(fenster, "angebote", None)
                if liste is not None and hasattr(liste, "neu_laden"):
                    liste.neu_laden()
        except (teilen.TeilenFehler, OSError):
            pass
    eigen = db.con.total_changes - vorher_c     # nur eigene Merker (gelesene Lebenszeichen): keine Änderung
    if eigen:
        for d, n in ((auto, "aenderungen"), (merk, "letzter")):
            if d.get(n) is not None:
                d[n] += eigen
    if auto.get("aenderungen") is None:         # Ausgangsstand: was bis hier geändert war, holt der Abgleich ab
        auto["aenderungen"] = db.con.total_changes
    # Sofort schreiben, sobald die Eingabe ruht (Dialoge nicht stören)
    if QApplication.activeModalWidget() is not None or QApplication.activePopupWidget() is not None:
        merk["letzter"] = db.con.total_changes
        return erg
    stand = db.con.total_changes
    if stand != auto["aenderungen"] and stand == merk.get("letzter"):
        bericht = abgleichen(fenster, lesen=False, schreiben=True, leise=True, auto=True)
        if bericht is not None:
            auto.update(aenderungen=db.con.total_changes, offen=offen_nummern(fenster), geschrieben=time.monotonic())
            erg["geschrieben"] = True
    merk["letzter"] = db.con.total_changes
    return erg


def takt_ms(db):
    """Abstand des automatischen Abgleichs (Einstellung teilen_takt in Minuten, 0 = aus) oder 0."""
    try:
        m = float(db.einstellung("teilen_takt") or 0)
    except (TypeError, ValueError):
        m = 0
    return int(m * 60_000) if m > 0 else 0


def abgleichen(fenster, lesen=True, schreiben=True, leise=False, beenden=False, auto=False):
    """Abgleich mit dem gemeinsamen Ordner samt Rückfragen; danach Listen, Stammdaten und offene Angebote neu laden.
    leise: Fehler nur in der Statuszeile (Programmstart). beenden: keine geöffneten Angebote mehr melden. auto:
    automatischer Abgleich (nur Geändertes neu laden, Meldung nur bei Neuem). Ergebnis: Bericht oder None."""
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
                    bericht["eigene"] = teilen.schreiben(db, uebernehmen, offen=offen_nummern(fenster, beenden))
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
        status_setzen(fenster, "⇄ nicht abgeglichen", str(e), fehler=True)
        if auto:
            return None
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
        _neu_laden(fenster, bericht, voll=not auto)
    neues = any(bericht.get(n) for n in ("angebote_neu", "angebote_geaendert", "angebote_weg", "stammdaten", "admin_vorgaben",
                                         "uebernommen", "konflikte", "nummern", "notizen"))
    if not auto or neues:
        fenster.meldung(teilen.bericht_text(bericht),
                        aktion=("Konflikte …", lambda: konflikte_zeigen(fenster)) if bericht.get("konflikte") else None)
    _status_nach(fenster, bericht)
    if bericht.get("hinweise") and not (leise or fenster.stumm):
        QMessageBox.information(fenster, "Abgleichen", "\n\n".join(bericht["hinweise"]))
    if not beenden:
        _vorgaenge_zeigen(fenster, bericht, leise)
    return bericht
