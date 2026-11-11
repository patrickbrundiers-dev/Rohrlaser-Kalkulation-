"""Online-Update in der Oberfläche: nach dem Start im Hintergrund nachsehen, auf Klick nur Geändertes laden, die
Datenbank sichern, das Programm beenden und danach die Dateien austauschen (nach_beenden), dann neu starten.
Die Logik steht in aktualisierung.py (ohne Qt)."""
import html
import sys
import threading

from PySide6.QtCore import QObject, QProcess, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox,
                               QProgressDialog, QStyle, QVBoxLayout)

from . import NAME
from . import aktualisierung as A

SUCHEN_NACH_MS = 3000        # nach dem Start etwas warten, das Fenster soll zuerst da sein
SPAETER_FRAGEN_MS = 30000    # ist gerade ein Dialog offen (Auftrag, Fertigmeldung), später fragen
NACH_UPDATE_TEXT = dict(ok="Update eingespielt: {stand}.",
                        abgebrochen="Update abgebrochen, das Programm ist unverändert ({stand}).",
                        fehler="Update nicht gelungen, das Programm ist unverändert ({stand}).")


def mb(n):
    return f"{n / 1e6:.1f} MB".replace(".", ",")


class _Suche(QObject):
    """Dateiliste in einem eigenen Thread holen, damit das Fenster nicht hängt (kein Netz, langsame Leitung)."""
    fertig = Signal(object, object)       # Dateiliste oder None, Fehlertext oder None

    def starten(self, adresse):
        def arbeit():
            try:
                self.fertig.emit(A.online_liste(adresse), None)
            except Exception as e:      # noqa: BLE001 – kein Netz, Sperrseite, ungültige Signatur
                self.fertig.emit(None, str(e))
        threading.Thread(target=arbeit, daemon=True).start()


class Frage(QDialog):
    """Hinweis auf den neuen Stand mit „Jetzt aktualisieren“ und „Später“."""

    def __init__(self, eltern, online, lokal):
        super().__init__(eltern)
        self.setWindowTitle("Update verfügbar")
        symbol = QLabel()
        symbol.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxInformation).pixmap(40, 40))
        aenderung = html.escape(online.get("aenderung") or "")
        self.hinweis = QLabel(
            f"<b>Eine neue Version von {NAME} ist verfügbar.</b><br><br>"
            f"Installiert: {A.stand_text(lokal)}<br>Neu: {A.stand_text(online)}"
            + (f"<br>Neu darin: <i>{aenderung}</i>" if aenderung else "")
            + "<br><br>Es werden nur die geänderten Programmdateien geladen. Danach sichert das Programm die "
              "Datenbank, schließt sich, tauscht die Dateien aus und startet neu. Aufträge und Einstellungen "
              "bleiben, wie sie sind.<br><br>Arbeiten mehrere Plätze mit derselben Datenbank, bitte alle Plätze "
              "aktualisieren.")
        self.hinweis.setWordWrap(True)
        self.hinweis.setMinimumWidth(460)
        knoepfe = QDialogButtonBox()
        self.jetzt = knoepfe.addButton("Jetzt aktualisieren", QDialogButtonBox.AcceptRole)
        self.spaeter = knoepfe.addButton("Später", QDialogButtonBox.RejectRole)
        self.jetzt.setDefault(True)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        oben = QHBoxLayout()
        oben.addWidget(symbol, 0, Qt.AlignTop)
        oben.addWidget(self.hinweis, 1)
        lay = QVBoxLayout(self)
        lay.addLayout(oben)
        lay.addWidget(knoepfe)


class Updater:
    """Gehört zum Hauptfenster. ordner: Programmordner (None beim Start aus dem Quelltext: dann gibt es kein
    Update). ausstehend: geladenes Update, das nach dem Beenden eingespielt wird (nach_beenden)."""

    def __init__(self, fenster, ordner=None, adresse=None, fragen=None):
        self.f, self.ordner, self.adresse = fenster, ordner, adresse or A.quelle()
        self.lokal = A.lokale_liste(ordner)
        self.fragen = fragen            # Tests: Funktion(online, lokal) -> True = jetzt aktualisieren
        self.ausstehend = None
        self._suche, self._laeuft = None, False

    def moeglich(self):
        return self.ordner is not None and self.lokal is not None

    def stand(self):
        return A.stand_text(self.lokal)

    def beim_start(self):
        """Still: meldet sich nur bei einem neuen Stand."""
        if self.moeglich():
            QTimer.singleShot(SUCHEN_NACH_MS, lambda: self.suchen(still=True))

    def suchen(self, still=False):
        if self._laeuft:
            return
        if not self.moeglich():
            if not still:
                self.f.hinweis("Updates gibt es nur für das Programm aus dem ZIP (ab Version 1.7).")
            return
        self._laeuft = True
        if not still:
            self.f.hinweis("Suche nach Updates …")
        self._suche = _Suche()
        self._suche.fertig.connect(lambda online, fehler: self.gefunden(online, fehler, still))
        self._suche.starten(self.adresse)

    def gefunden(self, online, fehler, still=False):
        self._laeuft = False
        if fehler:
            if not still:
                QMessageBox.warning(self.f, "Nach Updates suchen", f"Keine Verbindung zum Update:\n\n{fehler}")
            return False
        if not A.neuer(online, self.lokal):
            if not still:
                self.f.hinweis(f"Das Programm ist aktuell: {self.stand()}.")
            return False
        if still and QApplication.activeModalWidget() is not None:
            QTimer.singleShot(SPAETER_FRAGEN_MS, lambda: self.gefunden(online, None, still))
            return False
        if self.fragen is not None:
            ja = self.fragen(online, self.lokal)
        else:
            ja = Frage(self.f, online, self.lokal).exec() == QDialog.Accepted
        return self.einspielen(online) if ja else False

    def einspielen(self, online):
        """Laden, Datenbank sichern, dann das Programm beenden; ausgetauscht wird danach (nach_beenden).
        Ergebnis: True, wenn das Programm zum Einspielen beendet wird."""
        fortschritt = QProgressDialog("Programmdateien prüfen …", "Abbrechen", 0, len(online["dateien"]), self.f)
        fortschritt.setWindowTitle("Update")
        fortschritt.setMinimumDuration(0)
        fortschritt.setAutoReset(False)
        fortschritt.setValue(0)
        stand, hinweis, gesamt = [0], [""], [0]

        def pruefen(i, n):
            fortschritt.setRange(0, n)
            fortschritt.setValue(i)
            QApplication.processEvents()
            if fortschritt.wasCanceled():
                raise A.Abbruch()

        def geladen(n):
            if n:
                hinweis[0] = ""
            stand[0] += n
            fortschritt.setRange(0, max(1, gesamt[0], stand[0]))
            fortschritt.setValue(stand[0])
            fortschritt.setLabelText(f"Herunterladen: {mb(stand[0])}" + (f"\n{hinweis[0]}" if hinweis[0] else ""))
            QApplication.processEvents()
            if fortschritt.wasCanceled():
                raise A.Abbruch()

        def melden(text):
            hinweis[0] = text
            geladen(0)

        try:
            aus = A.laden(self.ordner, online, self.lokal, self.adresse, pruefen, geladen, melden)
            fortschritt.setCancelButton(None)        # ab hier nicht mehr abbrechen
            fortschritt.setLabelText("Datenbank sichern …")
            QApplication.processEvents()
            try:
                self.f.db.sichern("vor_update")
            except OSError as e:
                self.f.hinweis(f"Sicherung vor dem Update nicht möglich: {e}")
        except A.Abbruch:
            fortschritt.close()
            A.verwerfen(self.ordner)
            self.f.hinweis("Update abgebrochen, nichts geändert.")
            return False
        except (A.UpdateFehler, OSError) as e:
            fortschritt.close()
            QMessageBox.warning(self.f, "Update", "Das Update ließ sich nicht laden, das Programm bleibt, wie es "
                                f"war.\n\n{e}")
            return False
        fortschritt.close()
        plan = aus["plan"]
        if self.fragen is None:
            QMessageBox.information(self.f, "Update", f"{A.stand_text(aus['online'])} ist geladen "
                                    f"({len(plan['neu'])} Dateien, {mb(plan['groesse'])}).\n\n{NAME} schließt sich "
                                    "jetzt, tauscht die Dateien aus und startet neu.")
        self.ausstehend = aus
        for w in QApplication.topLevelWidgets():
            if w is not self.f and w.isVisible():
                w.close()
        self.f.close()
        QApplication.quit()
        return True


def nach_beenden(ordner, ausstehend, starten=None, exe=None, fragen=None):
    """Nach dem Beenden (Datenbank zu): Dateien austauschen. Hält ein anderes Programm eine Datei fest, wird gewartet
    und dann Wiederholen/Abbrechen angeboten; bei einem Fehler ist alles zurückgestellt. Danach startet das Programm
    neu (die neue oder bei Abbruch die alte Version). Ergebnis: 'ok', 'abgebrochen' oder 'fehler'.
    starten(exe, argumente) ersetzt QProcess.startDetached, fragen(gesperrt) die Rückfrage (Tests)."""
    from rohrlaser import update
    fortschritt = QProgressDialog("Dateien werden ausgetauscht …", None, 0, 0)
    fortschritt.setWindowTitle(f"{NAME} – Update")
    fortschritt.setMinimumDuration(0)
    fortschritt.show()
    QApplication.processEvents()

    def warten(gesperrt, rest):
        fortschritt.setLabelText(f"Warte, bis {gesperrt[0]} frei ist … (noch {rest:.0f} s)")
        QApplication.processEvents()

    ergebnis = None
    while ergebnis is None:
        try:
            gesperrt = A.austauschen(ordner, ausstehend, melden=warten)
        except (A.UpdateFehler, OSError) as e:
            fortschritt.hide()
            if fragen is None:
                QMessageBox.warning(None, f"{NAME} – Update", "Das Update ist nicht gelungen, die bisherige Version "
                                    f"bleibt und startet wieder.\n\n{e}")
            ergebnis = "fehler"
            break
        if not gesperrt:
            ergebnis = "ok"
            break
        fortschritt.hide()
        if fragen is not None:
            nochmal = fragen(gesperrt)
        else:
            nochmal = QMessageBox.warning(
                None, f"{NAME} – Update", f"{update.sperr_text(gesperrt, ordner)}\n\nLäuft das Programm noch an einem "
                "anderen Platz aus demselben Ordner? Bitte dort schließen und „Wiederholen“ klicken. „Abbrechen“ "
                "startet die bisherige Version, es wurde nichts geändert.",
                QMessageBox.Retry | QMessageBox.Cancel, QMessageBox.Retry) == QMessageBox.Retry
        if not nochmal:
            ergebnis = "abgebrochen"
        else:
            fortschritt.show()
    fortschritt.close()
    if ergebnis != "ok":
        A.verwerfen(ordner)
    if starten is None and getattr(sys, "frozen", False):
        starten = QProcess.startDetached
    if starten is not None:
        starten(exe or sys.executable, ["--nach-update", ergebnis])
    return ergebnis
