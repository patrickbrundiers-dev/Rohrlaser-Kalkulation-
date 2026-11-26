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


# ------------------------------------------------------------------------------------------------ Mehrbenutzer (S2)
# Anbindung an das Hauptfenster: Anwesenheit (Puls), Reservierung je geöffnetem Angebot, Live-Meldungen anderer
# Arbeitsplätze, Übernehmen mit Rückfrage, Abmelden beim Beenden. Regeln in server_mehrplatz.py.
LIVE_MS = 1000              # so oft holt das Fenster die Live-Meldungen ab
LISTE_RUHE_MS = 1500        # Angebotsliste höchstens so oft neu laden (viele Meldungen hintereinander)


def _sm():
    from . import server_mehrplatz
    return server_mehrplatz


def aktiv(fenster):
    return getattr(fenster.db, "server", None) is not None


def mehrplatz_starten(fenster):
    """Beim Öffnen des Hauptfensters im Serverbetrieb: Anmeldung protokollieren, ersten Puls senden, Zuhörer für
    Live-Meldungen starten."""
    if not aktiv(fenster):
        return None
    from PySide6.QtCore import QTimer
    sm = _sm()
    db = fenster.db
    fenster.__dict__.setdefault("_server_belegt", {})
    sm.protokollieren(db, sm.P_ANMELDEN, db.server.text())
    try:
        sm.puls(db, {})
    except db_verbindung.DbFehler:
        pass
    z = None
    if not fenster.stumm:           # Tests starten den Zuhörer selbst
        z = sm.Zuhoerer(db)
        z.eigene_pid_lesen()
        z.start()
    fenster._server_zuhoerer = z
    fenster._server_live = QTimer(fenster)
    fenster._server_live.timeout.connect(lambda: live(fenster))
    fenster._server_live.start(LIVE_MS)
    return z


def reservieren(fenster, angebot_id):
    """Vor dem Öffnen eines Angebots: für diesen Platz reservieren. Hält es ein Kollege, öffnet es nur zum Ansehen
    (fenster._server_belegt[id] = Inhaber)."""
    if not aktiv(fenster):
        return None
    belegt = fenster.__dict__.setdefault("_server_belegt", {})
    db = fenster.db
    if db.nur_lesen:
        belegt.pop(angebot_id, None)
        return None
    sm = _sm()
    nummer = (db.angebot(angebot_id) or {}).get("nummer") or ""
    try:
        wer = sm.reservieren(db, sm.objekt_angebot(angebot_id), nummer)
    except db_verbindung.DbFehler:
        wer = None
    if wer:
        belegt[angebot_id] = wer
    else:
        if belegt.pop(angebot_id, None) is not None or angebot_id not in fenster.offen:
            # ab hier bearbeitet dieser Platz: Stand für den Änderungsverlauf merken
            verlauf_erfassen(db, [angebot_id], fenster.__dict__.setdefault("_server_verlauf_merk", {}))
    return wer


def freigeben(fenster, angebot_id):
    """Angebot geschlossen: Änderungen mit Kürzel in den Verlauf, Reservierung frei."""
    if not aktiv(fenster):
        return
    belegt = fenster.__dict__.setdefault("_server_belegt", {})
    if belegt.pop(angebot_id, None) is None and not fenster.db.nur_lesen:
        verlauf_erfassen(fenster.db, [angebot_id])
        _sm().freigeben(fenster.db, _sm().objekt_angebot(angebot_id))


def verlauf_erfassen(db, angebot_ids, merk=None):
    """Änderungen an den hier bearbeiteten Angeboten mit dem eigenen Kürzel in den Änderungsverlauf. merk:
    {Angebots-ID: Änderungszähler} beim letzten Mal – dann nur Angebote, die sich seitdem geändert haben."""
    from . import aenderungsverlauf
    if not angebot_ids or db.nur_lesen or db.con.in_transaction:
        return 0
    try:
        if merk is not None:
            platz = ", ".join("?" * len(angebot_ids))
            zaehler = dict(db.con.execute(f"SELECT angebot_id, n FROM angebot_aenderungen WHERE angebot_id IN "
                                          f"({platz})", tuple(angebot_ids)).fetchall())
            angebot_ids = [i for i in angebot_ids if merk.get(i, -1) != zaehler.get(i)]
            merk.update({i: zaehler.get(i) for i in angebot_ids})
            if not angebot_ids:
                return 0
        with db.con:
            return aenderungsverlauf.erfassen_angebote(db.con, db.server.kuerzel, angebot_ids)
    except db_verbindung.DbFehler:
        return 0


def _offen_eigene(fenster):
    belegt = fenster.__dict__.setdefault("_server_belegt", {})
    merk = fenster.__dict__.setdefault("_server_offen_seit", {})
    jetzt = __import__("datetime").datetime.now().isoformat(timespec="minutes")
    out = {}
    for aid, seite in list(fenster.offen.items()):
        if aid in belegt:
            continue
        nr = (getattr(seite, "kopf", None) or {}).get("nummer")
        if nr:
            out[nr] = merk.get(nr) or jetzt
    merk.clear()
    merk.update(out)
    return out


def puls(fenster):
    """Alle 15 s: Anwesenheit melden, eigene Reservierungen verlängern; verlorene (übernommen) → nur Ansehen;
    Angebote, die ein Kollege freigegeben hat → hier bearbeiten; Liste neu, wenn sich Bearbeiter geändert haben."""
    if not aktiv(fenster):
        return None
    from . import teilen
    sm = _sm()
    db = fenster.db
    merk = fenster.__dict__.setdefault("_server_puls_merk", {})
    import time
    jetzt_ = time.monotonic()
    if jetzt_ - merk.get("zeit", -1e9) < sm.PULS_S - 1:
        return None
    merk["zeit"] = jetzt_
    offen = _offen_eigene(fenster)
    try:
        halte = sm.puls(db, offen, teilen._zeilen_frisch(db, teilen._utc(teilen.uhr_versatz(db))))
    except db_verbindung.DbFehler:
        return None
    if halte is None:
        return None
    setattr(db, teilen.OFFEN_ZULETZT, offen)
    eigene = [aid for aid in fenster.offen if aid not in fenster._server_belegt]
    verlauf_erfassen(db, eigene, fenster.__dict__.setdefault("_server_verlauf_merk", {}))
    _reservierungen_pruefen(fenster, halte)
    try:
        stand = repr(sorted(sm.angebote_in_bearbeitung(db).items()))
    except db_verbindung.DbFehler:
        stand = merk.get("stand")
    if stand != merk.get("stand"):
        merk["stand"] = stand
        _liste_neu(fenster)
    return halte


def _reservierungen_pruefen(fenster, halte=None):
    """Offene Angebote mit der Lage am Server abgleichen. halte: Objekte, die dieser Platz noch hält (None: nur die
    Angebote prüfen, die ein Kollege bearbeitet)."""
    sm = _sm()
    db = fenster.db
    if db.nur_lesen:
        return
    belegt = fenster._server_belegt
    for aid, seite in list(fenster.offen.items()):
        obj = sm.objekt_angebot(aid)
        vorher = belegt.get(aid)
        if vorher is None and halte is not None and obj in halte:
            continue
        if vorher is None and halte is None:
            continue
        wer = reservieren(fenster, aid)
        nr = (getattr(seite, "kopf", None) or {}).get("nummer") or ""
        if vorher is None and wer is None:          # kurz abgelaufen (Netz), wieder hier reserviert
            continue
        if vorher is None and wer:
            fenster.meldung(f"{wer['kuerzel']} hat Angebot {nr} übernommen – hier jetzt nur zum Ansehen.", fehler=True)
        elif vorher is not None and wer is None:
            fenster.meldung(f"Angebot {nr} ist frei – Sie können es jetzt bearbeiten.")
        elif vorher is not None and wer and wer["kuerzel"] == vorher["kuerzel"] and wer["platz"] == vorher["platz"]:
            continue
        if hasattr(seite, "neu_laden"):
            seite.neu_laden()


def _liste_neu(fenster):
    liste = getattr(fenster, "angebote", None)
    if liste is None or not hasattr(liste, "neu_laden"):
        return
    import time
    merk = fenster.__dict__.setdefault("_server_puls_merk", {})
    if time.monotonic() - merk.get("liste", -1e9) < LISTE_RUHE_MS / 1000:
        merk["liste_offen"] = True
        return
    merk["liste"] = time.monotonic()
    merk["liste_offen"] = False
    liste.neu_laden()


def ablage_einstellen(fenster, pfad=None):
    """Datei → Datenbank → Ablage am Server … (Verwalter, S3): Pfad der Freigabe für die gemeinsamen Dateien
    eintragen und prüfen. pfad: ohne Rückfrage (Tests). Ergebnis: (Pfad oder None, erreichbar) oder None."""
    from PySide6.QtWidgets import QInputDialog

    from . import teilen
    db = fenster.db
    if pfad is None:
        alt = sb.ablage(db)
        pfad, ok = QInputDialog.getText(
            fenster, "Ablage am Server",
            "Ordner für Angebotsordner, Anfrage-Akten, Austausch und Updates, so wie ihn alle Arbeitsplätze im Netz "
            "erreichen (Freigabe des Ordners „Ablage“ im Server-Ordner, z. B. \\\\SERVER\\Rohrlaser-Ablage).\n"
            "Leer = keine Ablage (Dateien bleiben auf jedem Arbeitsplatz).", QLineEdit.Normal, alt)
        if not ok:
            return None
    try:
        erg = _sm().ablage_speichern(db, pfad)
    except (sb.ServerFehler, db_verbindung.DbFehler) as e:
        fenster.meldung(str(e))
        if not fenster.stumm:
            QMessageBox.warning(fenster, "Ablage am Server", fehler_text(e))
        return None
    p, erreichbar = erg
    _, _, text = teilen.ablage_zustand(db)
    fenster.meldung(text)
    if not fenster.stumm:
        (QMessageBox.information if (p is None or erreichbar) else QMessageBox.warning)(
            fenster, "Ablage am Server", text + ("" if p is None or erreichbar else
                                                 "\n\nEingetragen ist der Pfad trotzdem; die anderen Arbeitsplätze "
                                                 "nutzen ihn, sobald er für sie erreichbar ist."))
    return erg


def sm_eigene(db):
    return _sm().eigene(db)


def live(fenster):
    """Live-Meldungen anderer Arbeitsplätze verarbeiten: geänderte Angebote in der Liste und in hier nur angesehenen
    Angeboten neu laden, Reservierungswechsel sofort prüfen (statt erst beim nächsten Puls)."""
    z = getattr(fenster, "_server_zuhoerer", None)
    merk = fenster.__dict__.setdefault("_server_puls_merk", {})
    if z is None:
        return None
    m = z.abholen()
    if not (m["angebote"] or m["sperren"] or m["neu"]):
        if merk.get("liste_offen"):
            _liste_neu(fenster)
        return m
    belegt = fenster.__dict__.setdefault("_server_belegt", {})
    if m["sperren"] or m["neu"]:
        try:
            halte = sm_eigene(fenster.db)
        except db_verbindung.DbFehler:
            halte = None
        _reservierungen_pruefen(fenster, halte)     # auch eigene: übernommen → sofort nur Ansehen
    for aid in m["angebote"] | (set(fenster.offen) if m["neu"] else set()):
        seite = fenster.offen.get(aid)
        if seite is not None and aid in belegt and hasattr(seite, "neu_laden"):
            seite.neu_laden()       # nur angesehen: Stand des Kollegen zeigen
    _liste_neu(fenster)
    return m


def uebernehmen(fenster, angebot_id, fragen=True):
    """Bearbeitung eines Angebots vom Kollegen übernehmen (Rückfrage). Ergebnis: True = übernommen."""
    if not aktiv(fenster) or fenster.db.nur_lesen:
        return False
    sm = _sm()
    belegt = fenster.__dict__.setdefault("_server_belegt", {})
    wer = belegt.get(angebot_id)
    nr = (fenster.db.angebot(angebot_id) or {}).get("nummer") or ""
    if fragen and wer and not fenster.stumm and QMessageBox.question(
            fenster, "Angebot übernehmen",
            f"{wer['kuerzel']} bearbeitet Angebot {nr} gerade am Arbeitsplatz {wer['platz']}.\n\nJetzt hier "
            f"übernehmen? {wer['kuerzel']} sieht es danach nur noch an; was dort schon eingegeben ist, bleibt "
            "gespeichert.") != QMessageBox.Yes:
        return False
    try:
        sm.uebernehmen(fenster.db, sm.objekt_angebot(angebot_id), nr, erwartet=wer)
    except sm.SchonUebernommen as e:
        belegt[angebot_id] = e.inhaber
        seite = fenster.offen.get(angebot_id)
        if seite is not None and hasattr(seite, "neu_laden"):
            seite.neu_laden()
        fenster.meldung(f"Angebot {nr}: {e} Hier weiter nur zum Ansehen.", fehler=True)
        return False
    belegt.pop(angebot_id, None)
    seite = fenster.offen.get(angebot_id)
    if seite is not None and hasattr(seite, "neu_laden"):
        seite.neu_laden()
    fenster.meldung(f"Angebot {nr} übernommen – Sie bearbeiten es jetzt.")
    return True


def mehrplatz_beenden(fenster):
    """Programmende: Verlauf der offenen Angebote, Abmelden (alle Reservierungen frei), Zuhörer anhalten."""
    if not aktiv(fenster):
        return
    sm = _sm()
    db = fenster.db
    t = getattr(fenster, "_server_live", None)
    if t is not None:
        t.stop()
    z = getattr(fenster, "_server_zuhoerer", None)
    if z is not None:
        z.stoppen()
    belegt = fenster.__dict__.setdefault("_server_belegt", {})
    verlauf_erfassen(db, [aid for aid in fenster.offen if aid not in belegt])
    try:
        sm.puls(db, ende=True)
    except db_verbindung.DbFehler:
        pass
    sm.protokollieren(db, sm.P_ABMELDEN, "")
