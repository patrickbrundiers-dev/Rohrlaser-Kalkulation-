"""Online-Update in der Oberfläche: beim Start im Hintergrund nachsehen, auf Klick nur Geändertes laden,
vorher die Datendatei sichern. Dann beendet sich das Programm geordnet (Fenster, STEP-Messung, Abgleich, Sicherung,
Datendatei, Datensperre) und tauscht erst danach die Dateien aus (nach_beenden): gesperrte Dateien abwarten,
Wiederholen/Abbrechen, bei Fehler alles zurück, dann neu starten (Logik in update.py)."""
import html
import sys
import threading
import time

from PySide6.QtCore import QObject, QProcess, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox,
                               QProgressDialog, QStyle, QVBoxLayout)

from . import NAME, protokoll, update

SUCHEN_NACH_MS = 3000        # nach dem Start etwas warten, das Fenster soll zuerst da sein
SPAETER_FRAGEN_MS = 30000    # ist gerade ein Dialog offen (z. B. STEP-Import), später nachfragen
HINTERGRUND = ("Optimieren", "Staffelpreise")   # Threads, die vor dem Austausch fertig sein sollen
HINTERGRUND_WARTEN_S = 15


class _Suche(QObject):
    """Dateiliste in einem eigenen Thread holen, damit das Fenster nicht hängt (kein Netz, langsame Leitung)."""
    fertig = Signal(object, object)       # Dateiliste oder None, Fehlertext oder None
    lizenz = Signal(object)               # Sperrliste und Datum des Servers (update.lizenz_zusatz)

    def starten(self, quelle):
        def arbeit():
            self.lizenz.emit(update.lizenz_zusatz(quelle))
            try:
                self.fertig.emit(update.online_liste(quelle), None)
            except update.UpdateFehler as e:
                self.fertig.emit(None, str(e))
        threading.Thread(target=arbeit, daemon=True).start()


def mb(n):
    return f"{n / 1e6:.1f} MB".replace(".", ",")


class Frage(QDialog):
    """Hinweis auf den neuen Stand mit „Jetzt aktualisieren“ und „Später“."""

    def __init__(self, eltern, online, lokal):
        super().__init__(eltern)
        self.setWindowTitle("Update verfügbar")
        symbol = QLabel()
        symbol.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxInformation).pixmap(40, 40))
        aenderung = html.escape(online.get("aenderung") or "")
        self.hinweis = QLabel(
            f"<b>Eine neue Version ist verfügbar.</b><br><br>"
            f"Installiert: {update.stand_text(lokal)}<br>Neu: {update.stand_text(online)}"
            + (f"<br>Zuletzt geändert: <i>{aenderung}</i>" if aenderung else "")
            + "<br><br>Es werden nur die geänderten Programmdateien geladen. Danach sichert das Programm die "
              "Datendatei, schließt alles, tauscht die Dateien aus und startet neu. Daten und Angebote bleiben, "
              "wie sie sind.")
        self.hinweis.setWordWrap(True)
        self.hinweis.setMinimumWidth(460)
        knoepfe = QDialogButtonBox()
        self.jetzt = knoepfe.addButton("Jetzt aktualisieren", QDialogButtonBox.AcceptRole)
        self.spaeter = knoepfe.addButton("Später", QDialogButtonBox.RejectRole)
        self.jetzt.setDefault(True)
        self._geklickt = None
        knoepfe.clicked.connect(self._klick)
        oben = QHBoxLayout()
        oben.addWidget(symbol, 0, Qt.AlignTop)
        oben.addWidget(self.hinweis, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(knoepfe)

    def _klick(self, knopf):
        self._geklickt = knopf
        self.accept() if knopf is self.jetzt else self.reject()

    def clickedButton(self):
        return self._geklickt

    def text(self):
        return self.hinweis.text()

    def buttons(self):
        return [self.jetzt, self.spaeter]


def frage(eltern, online, lokal):
    return Frage(eltern, online, lokal)


class Updater:
    def __init__(self, fenster, quelle=update.ADRESSE):
        self.f = fenster
        self.quelle = quelle
        self.ordner = fenster.programmordner
        self.lokal = update.lokale_liste(self.ordner)
        self._suche = None
        self._laeuft = False
        self.ausstehend = None       # geladenes Update, wird nach dem Beenden eingespielt (nach_beenden)

    def beim_start(self):
        """Nur im fertigen Programm (Dateiliste aus dem ZIP), still: meldet sich nur bei einem neuen Stand."""
        if self.lokal is not None:
            QTimer.singleShot(SUCHEN_NACH_MS, lambda: self.suchen(still=True))
        if (self.ordner / update.ARBEITSORDNER).exists():       # alte Dateien nach dem Neustart frei: aufräumen
            QTimer.singleShot(15000, lambda: update.aufraeumen(self.ordner))

    def suchen(self, still=False):
        if self._laeuft:
            return
        if self.lokal is None and not getattr(sys, "frozen", False):
            if not still:
                QMessageBox.information(self.f, "Nach Updates suchen",
                                        "Updates gibt es nur für das Programm aus dem ZIP (Release „aktuell“).")
            return
        self._laeuft = True
        if not still:
            self.f.meldung("Suche nach Updates …")
        self._suche = _Suche()
        self._suche.fertig.connect(lambda online, fehler: self._gefunden(online, fehler, still))
        self._suche.lizenz.connect(self._lizenz)
        self._suche.starten(self.quelle)

    def _lizenz(self, zusatz):
        """Sperrliste und Zeitabgleich an die Lizenz des Hauptfensters (nur mit Lizenzprüfung, sonst nichts)."""
        if hasattr(self.f, "lizenz_zusatz"):
            self.f.lizenz_zusatz(zusatz)

    def _gefunden(self, online, fehler, still):
        self._laeuft = False
        if fehler:
            if not still:
                QMessageBox.warning(self.f, "Nach Updates suchen", f"Keine Verbindung zum Update:\n\n{fehler}")
            return
        if not update.neuer(online, self.lokal):
            if not still:
                self.f.meldung("Das Programm ist aktuell.")
                QMessageBox.information(self.f, "Nach Updates suchen",
                                        f"Das Programm ist aktuell: {update.stand_text(self.lokal)}.")
            return
        if still and QApplication.activeModalWidget() is not None:
            # gerade ist ein Dialog offen (STEP-Import, Optimieren …): nicht dazwischenfunken, später fragen
            QTimer.singleShot(SPAETER_FRAGEN_MS, lambda: self._gefunden(online, None, still))
            return
        m = frage(self.f, online, self.lokal)
        m.exec()
        if m.clickedButton() is m.jetzt:
            self.einspielen(online)

    def einspielen(self, online):
        """Prüfen, laden, Datendatei sichern, dann das Programm geordnet beenden; ausgetauscht wird danach
        (nach_beenden). Ergebnis: True wenn das Programm zum Einspielen beendet wird."""
        fortschritt = QProgressDialog("Programmdateien prüfen …", "Abbrechen", 0, len(online["dateien"]), self.f)
        fortschritt.setWindowTitle("Update")
        fortschritt.setMinimumDuration(0)
        fortschritt.setAutoReset(False)
        fortschritt.setValue(0)
        stand = [0]

        def pruefen(i, n):
            fortschritt.setValue(i)
            QApplication.processEvents()
            if fortschritt.wasCanceled():
                raise update.Abbruch()

        def geladen(n):
            stand[0] += n
            fortschritt.setValue(min(stand[0], fortschritt.maximum()))
            fortschritt.setLabelText(f"Herunterladen: {mb(stand[0])} von {mb(plan['groesse'])}")
            QApplication.processEvents()
            if fortschritt.wasCanceled():
                raise update.Abbruch()

        try:
            for versuch in range(2):
                fortschritt.setRange(0, len(online["dateien"]))
                fortschritt.setLabelText("Programmdateien prüfen …")
                plan = update.planen(self.ordner, online, self.lokal, fortschritt=pruefen)
                # auch ohne geänderte Dateien einspielen: dann wird nur die Dateiliste (der Stand) erneuert
                fortschritt.setRange(0, max(1, plan["groesse"]))
                stand[0] = 0
                geladen(0)
                try:
                    neu_ordner = update.laden(self.ordner, self.quelle, online, plan, geladen)
                    break
                except update.UpdateFehler:
                    # Paket fehlt: seit der Suche hat ein neuerer Stand die Dateiliste ersetzt -> mit der neuen
                    update.verwerfen(self.ordner)
                    frisch = update.neuere_liste(self.quelle, online) if versuch == 0 else None
                    if frisch is None:
                        raise
                    online = frisch
            fortschritt.setCancelButton(None)        # ab hier nicht mehr abbrechen
            fortschritt.setLabelText("Datendatei sichern …")
            QApplication.processEvents()
            _, fehler = self.f.db.sicherungen(zusatz="vor_update")
            if fehler:
                self.f.meldung(fehler, fehler=True)
        except update.Abbruch:
            fortschritt.close()
            update.verwerfen(self.ordner)
            self.f.meldung("Update abgebrochen, nichts geändert.")
            return False
        except (update.UpdateFehler, OSError) as e:
            fortschritt.close()
            update.verwerfen(self.ordner)
            QMessageBox.warning(self.f, "Update", f"Das Update ließ sich nicht laden, das Programm bleibt wie es "
                                f"war.\n\n{e}")
            return False
        fortschritt.close()
        protokoll.info(f"Update: {update.stand_text(online)} geladen ({len(plan['neu'])} Dateien), Programm wird "
                       "zum Austauschen beendet")
        QMessageBox.information(self.f, "Update", f"{update.stand_text(online)} ist geladen "
                                f"({len(plan['neu'])} Dateien, {mb(plan['groesse'])}).\n\n"
                                f"{NAME} schließt jetzt alle Fenster, legt die Angebote ab, sichert die Daten, "
                                "tauscht die Dateien aus und startet neu.")
        self.ausstehend = dict(online=online, plan=plan, neu_ordner=neu_ordner)
        if not self.beenden():
            self.ausstehend = None
            update.verwerfen(self.ordner)
            self.f.meldung("Update abgebrochen (Programm nicht beendet), nichts geändert.")
            return False
        return True

    def beenden(self):
        """Alles schließen, was den Austausch behindern kann: andere Fenster und Dialoge, laufende Prozesse (STEP-
        Messung), dann das Hauptfenster wie beim normalen Beenden (Abgleich, Sicherung; der Benutzer kann dort
        abbrechen), Hintergrund-Rechnungen abwarten, Ereignisschleife beenden. True = Programm wird beendet."""
        for w in QApplication.topLevelWidgets():
            if w is not self.f and w.isVisible():
                w.close()
        for p in self.f.findChildren(QProcess):
            if p.state() != QProcess.NotRunning:
                p.kill()
                p.waitForFinished(5000)
        if not self.f.close():
            return False
        hintergrund_abwarten()
        QApplication.closeAllWindows()
        QApplication.quit()
        return True


def hintergrund_abwarten(namen=HINTERGRUND, sekunden=HINTERGRUND_WARTEN_S):
    """Laufende Hintergrund-Rechnungen (Threads mit diesen Namen) bis zu sekunden zu Ende rechnen lassen."""
    ende = time.monotonic() + sekunden
    for t in threading.enumerate():
        if t.name in namen and t.is_alive() and t is not threading.current_thread():
            t.join(max(0.0, ende - time.monotonic()))


def nach_beenden(ordner, ausstehend, starten=None, exe=None):
    """Nach dem Beenden (Datendatei zu, Sperre frei): Dateien austauschen. Gesperrte Dateien bis zu
    update.SPERR_WARTEN_S abwarten, dann Wiederholen/Abbrechen anbieten; bei Fehler ist alles zurückgestellt.
    Danach das Programm neu starten (neue oder bei Abbruch die alte Version). Ergebnis: 'ok', 'abgebrochen' oder
    'fehler'. starten(exe, argumente) ersetzt QProcess.startDetached (Tests)."""
    online, plan, neu_ordner = ausstehend["online"], ausstehend["plan"], ausstehend["neu_ordner"]
    fortschritt = QProgressDialog("Dateien werden ausgetauscht …", None, 0, 0)
    fortschritt.setWindowTitle(f"{NAME} – Update")
    fortschritt.setMinimumDuration(0)
    fortschritt.show()
    QApplication.processEvents()

    def warten(gesperrt, rest):
        fortschritt.setLabelText(f"Warte, bis {gesperrt[0]} frei ist … (noch {rest:.0f} s)\n"
                                 f"{update.sperr_grund(gesperrt[0])}")
        QApplication.processEvents()

    ergebnis = None
    while ergebnis is None:
        gesperrt = update.warten_bis_frei(ordner, plan, melden=warten)
        fehler = None
        if not gesperrt:
            fortschritt.setLabelText("Dateien werden ausgetauscht …")
            QApplication.processEvents()
            try:
                update.einspielen(ordner, online, plan, neu_ordner)
                ergebnis = "ok"
                break
            except update.DateiGesperrt as e:
                gesperrt = e.dateien
            except (update.UpdateFehler, OSError) as e:
                fehler = str(e)
        if gesperrt:
            protokoll.info("Update: gesperrt " + ", ".join(gesperrt))
            fortschritt.hide()
            antwort = QMessageBox.warning(
                None, f"{NAME} – Update", f"{update.sperr_text(gesperrt)}\n\nBitte schließen und „Wiederholen“ "
                "klicken. „Abbrechen“ startet die bisherige Version, es wurde nichts geändert.",
                QMessageBox.Retry | QMessageBox.Cancel, QMessageBox.Retry)
            if antwort == QMessageBox.Retry:
                fortschritt.show()
                continue
            ergebnis = "abgebrochen"
        else:
            protokoll.info("Update fehlgeschlagen: " + fehler)
            fortschritt.hide()
            QMessageBox.warning(None, f"{NAME} – Update", "Das Update ist nicht gelungen, die bisherige Version "
                                f"bleibt und startet wieder.\n\n{fehler}")
            ergebnis = "fehler"
    fortschritt.close()
    if ergebnis != "ok":
        update.verwerfen(ordner)
    protokoll.info(f"Update: {ergebnis}" + (f", jetzt {update.stand_text(online)}" if ergebnis == "ok" else ""))
    if starten is None and getattr(sys, "frozen", False):
        starten = QProcess.startDetached
    if starten is not None:
        starten(exe or sys.executable, ["--nach-update", ergebnis])
    return ergebnis
