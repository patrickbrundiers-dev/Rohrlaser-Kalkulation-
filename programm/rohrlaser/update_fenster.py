"""Online-Update in der Oberfläche: beim Start im Hintergrund nachsehen, auf Klick nur Geändertes laden,
vorher die Datendatei sichern, austauschen und neu starten (Logik in update.py)."""
import html
import sys
import threading

from PySide6.QtCore import QObject, QProcess, Qt, QTimer, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox,
                               QProgressDialog, QStyle, QVBoxLayout)

from . import NAME, update

SUCHEN_NACH_MS = 3000        # nach dem Start etwas warten, das Fenster soll zuerst da sein


class _Suche(QObject):
    """Dateiliste in einem eigenen Thread holen, damit das Fenster nicht hängt (kein Netz, langsame Leitung)."""
    fertig = Signal(object, object)       # Dateiliste oder None, Fehlertext oder None

    def starten(self, quelle):
        def arbeit():
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
            + "<br><br>Es werden nur die geänderten Programmdateien geladen. Vorher sichert das Programm die "
              "Datendatei, danach startet es neu. Daten und Angebote bleiben, wie sie sind.")
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
        self._suche.starten(self.quelle)

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
        m = frage(self.f, online, self.lokal)
        m.exec()
        if m.clickedButton() is m.jetzt:
            self.einspielen(online)

    def einspielen(self, online):
        """Prüfen, laden, Datendatei sichern, austauschen, neu starten. Ergebnis: True wenn eingespielt."""
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
            fortschritt.setLabelText("Dateien austauschen …")
            QApplication.processEvents()
            update.einspielen(self.ordner, online, plan, neu_ordner)
        except update.Abbruch:
            fortschritt.close()
            update.verwerfen(self.ordner)
            self.f.meldung("Update abgebrochen, nichts geändert.")
            return False
        except (update.UpdateFehler, OSError) as e:
            fortschritt.close()
            update.verwerfen(self.ordner)
            QMessageBox.warning(self.f, "Update", f"Das Update ist nicht gelungen, das Programm bleibt wie es "
                                f"war.\n\n{e}\n\nTipp: geöffnete Bedienungsanleitung oder STEP-Import schließen "
                                "und noch einmal versuchen.")
            return False
        fortschritt.close()
        self.lokal = online
        QMessageBox.information(self.f, "Update", f"{NAME} ist jetzt auf {update.stand_text(online)}"
                                f" ({len(plan['neu'])} Dateien, {mb(plan['groesse'])} geladen).\n\n"
                                "Das Programm startet jetzt neu.")
        self.neu_starten()
        return True

    def neu_starten(self):
        """Erst schließen (der Benutzer kann beim Beenden noch abbrechen), dann die neue Version starten."""
        if self.f.close() and getattr(sys, "frozen", False):
            QProcess.startDetached(sys.executable, [])
