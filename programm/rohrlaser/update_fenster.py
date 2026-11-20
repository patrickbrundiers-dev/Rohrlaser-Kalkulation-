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

from . import NAME, protokoll, update, update_quellen, update_verteilen
from .klartext import fehler_text

SUCHEN_NACH_MS = 3000        # nach dem Start etwas warten, das Fenster soll zuerst da sein
SPAETER_FRAGEN_MS = 30000    # ist gerade ein Dialog offen (z. B. STEP-Import), später nachfragen
HINTERGRUND = ("Optimieren",)   # Threads, die vor dem Austausch fertig sein sollen
HINTERGRUND_WARTEN_S = 15


class _Suche(QObject):
    """Alle Quellen in einem eigenen Thread fragen, damit das Fenster nicht hängt (kein Netz, langsame Leitung)."""
    fertig = Signal(object)               # Ergebnis von update_quellen.suchen
    lizenz = Signal(object)               # Sperrliste und Datum des Servers (update.lizenz_zusatz)

    def starten(self, quellen):
        def arbeit():
            internet = next((q for q in quellen if update._ist_url(q.ort)), None)
            lizenz_ort = internet or next(iter(quellen), None)
            if lizenz_ort is not None:
                try:
                    self.lizenz.emit(update.lizenz_zusatz(lizenz_ort.adresse()))
                except update.UpdateFehler:
                    pass
            self.fertig.emit(update_quellen.suchen(quellen))
        threading.Thread(target=arbeit, daemon=True).start()


def mb(n):
    return f"{n / 1e6:.1f} MB".replace(".", ",")


class Frage(QDialog):
    """Hinweis auf den neuen Stand mit „Jetzt aktualisieren“ und „Später“."""

    def __init__(self, eltern, online, lokal, quelle_text="", freigabe=None):
        super().__init__(eltern)
        freigabe = freigabe or {}
        pflicht = update_verteilen.pflicht_faellig(freigabe)
        self.setWindowTitle("Pflicht-Update" if pflicht else "Update verfügbar")
        symbol = QLabel()
        symbol.setPixmap(self.style().standardIcon(QStyle.SP_MessageBoxInformation).pixmap(40, 40))
        aenderung = html.escape(online.get("aenderung") or "")
        self.hinweis = QLabel(
            f"<b>Eine neue Version ist verfügbar.</b><br><br>"
            f"Installiert: {update.stand_text(lokal)}<br>Neu: {update.stand_text(online)}"
            + (f"<br>Zuletzt geändert: <i>{aenderung}</i>" if aenderung else "")
            + (f"<br>Quelle: {html.escape(quelle_text)}" if quelle_text else "")
            + ("<br><b>Vom Administrator als Pflicht-Update freigegeben</b>"
               + (f" (ab {html.escape(freigabe['pflicht_ab'])})" if freigabe.get("pflicht_ab") else "")
               if freigabe.get("pflicht") else "")
            + (f"<br>Hinweis: {html.escape(freigabe['hinweis'])}" if freigabe.get("hinweis") else "")
            + (f"<br>Wartungsfenster: {html.escape(freigabe['wartung'])}" if freigabe.get("wartung") else "")
            + "<br><br>Es werden nur die geänderten Programmdateien geladen. Danach sichert das Programm die "
              "Datendatei, schließt alles, tauscht die Dateien aus und startet neu. Daten und Angebote bleiben, "
              "wie sie sind.")
        self.hinweis.setWordWrap(True)
        self.hinweis.setMinimumWidth(460)
        knoepfe = QDialogButtonBox()
        self.jetzt = knoepfe.addButton("Jetzt aktualisieren", QDialogButtonBox.AcceptRole)
        # geplanter Zeitpunkt: jetzt laden und sichern, erst beim normalen Beenden austauschen
        self.beenden = knoepfe.addButton("Beim Beenden", QDialogButtonBox.AcceptRole)
        self.beenden.setToolTip("Jetzt laden und sichern, eingespielt wird beim Beenden des Programms – "
                                "kein Unterbrechen der laufenden Arbeit.")
        self.spaeter = knoepfe.addButton("Später", QDialogButtonBox.RejectRole)
        self.spaeter.setVisible(not pflicht)     # fälliges Pflicht-Update: nur jetzt oder beim Beenden
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
        self.accept() if knopf in (self.jetzt, self.beenden) else self.reject()

    def clickedButton(self):
        return self._geklickt

    def text(self):
        return self.hinweis.text()

    def buttons(self):
        return [k for k in (self.jetzt, self.beenden, self.spaeter) if not k.isHidden()]


def frage(eltern, online, lokal, quelle_text="", freigabe=None):
    return Frage(eltern, online, lokal, quelle_text, freigabe)


class Updater:
    """Update im Programm. Quellen: fest (Umgebungsvariable RL_UPDATE_QUELLE, Tests und Vorabkanal) oder aus den
    Einstellungen (update_quellen: Update-Ordner und/oder Internet). Gesucht wird in allen, eingespielt aus der
    Quelle mit dem höchsten Stand."""

    def __init__(self, fenster, quelle=None):
        self.f = fenster
        self.feste_quelle = quelle if quelle and quelle != update.ADRESSE else None
        self.quelle = quelle or update.ADRESSE      # Adresse der Dateiliste der zuletzt gewählten Quelle
        self.quelle_obj = None
        self.letzte_suche = None                    # Ergebnis von update_quellen.suchen (Update-Center)
        self.freigabe = {}
        self.ordner = fenster.programmordner
        self.lokal = update.lokale_liste(self.ordner)
        self._suche = None
        self._laeuft = False
        self.ausstehend = None       # geladenes Update, wird nach dem Beenden eingespielt (nach_beenden)
        self.beim_beenden = False    # ausstehend nur beim normalen Beenden einspielen („Beim Beenden“)
        self.hinweis = update_quellen.netz_anwenden(self._db())   # Proxy/Zertifikat; Text bei ungültigem Wert

    def _db(self):
        return getattr(self.f, "db", None)

    def quellen(self):
        if self.feste_quelle:
            return [update_quellen.Quelle(self.feste_quelle, "fest eingestellt (RL_UPDATE_QUELLE)")]
        return update_quellen.quellen(self._db())

    def verlauf_pfad(self):
        return update_quellen.verlauf_pfad(self._db())

    def beim_start(self):
        """Nur im fertigen Programm (Dateiliste aus dem ZIP), still: meldet sich nur bei einem neuen Stand."""
        if self.lokal is not None and update_quellen.einstellungen(self._db())["beim_start"]:
            QTimer.singleShot(SUCHEN_NACH_MS, lambda: self.suchen(still=True))
        if self.hinweis:
            self.f.meldung(f"Update-Einstellung ungültig, es gilt der Windows-Proxy: {self.hinweis}", fehler=True)
        if (self.ordner / update.ARBEITSORDNER).exists():       # alte Dateien nach dem Neustart frei: aufräumen
            QTimer.singleShot(15000, lambda: (update.nachholen(self.ordner), update.aufraeumen(self.ordner)))

    def suchen(self, still=False, fertig=None, anbieten=True):
        """In allen Quellen suchen; fertig(ergebnis) zusätzlich nach der Suche (Update-Center, dort mit
        anbieten=False: nur anzeigen, keine Frage)."""
        if self._laeuft:
            return
        if self.lokal is None and not getattr(sys, "frozen", False):
            if not still:
                self.f.meldung("Updates gibt es nur für das Programm aus dem ZIP (Release „aktuell“).")
            if fertig:
                fertig(None)
            return
        self._laeuft = True
        if not still:
            self.f.meldung("Suche nach Updates …")
        self._suche = _Suche()
        self._suche.fertig.connect(lambda erg: self._ergebnis(erg, still, fertig, anbieten))
        self._suche.lizenz.connect(self._lizenz)
        self._suche.starten(self.quellen())

    def _lizenz(self, zusatz):
        """Sperrliste und Zeitabgleich an die Lizenz des Hauptfensters (nur mit Lizenzprüfung, sonst nichts)."""
        if hasattr(self.f, "lizenz_zusatz"):
            self.f.lizenz_zusatz(zusatz)

    def _ergebnis(self, erg, still, fertig=None, anbieten=True):
        self.letzte_suche = erg
        for q, liste, fehler in erg["ergebnisse"]:
            protokoll.info(f"Update-Suche {q.text()}: " + (update.stand_text(liste) if liste else f"Fehler: {fehler}"))
        if erg["beste"] is None:
            fehler = "\n\n".join(f"{q.text()}:\n{f}" for q, _, f in erg["ergebnisse"]) or "Keine Update-Quelle."
            self._gefunden(None, fehler, still)
        else:
            self.quelle_obj, online = erg["beste"]
            self.quelle = self.quelle_obj.adresse()
            self.freigabe = self.quelle_obj.freigabe() if hasattr(self.quelle_obj, "freigabe") else {}
            if self.freigabe.get("hinweis") and update.neuer(online, self.lokal):
                self.f.meldung(f"Hinweis vom Administrator: {self.freigabe['hinweis']}")
            if anbieten:
                self._gefunden(online, None, still)
        self._laeuft = False
        if fertig:
            fertig(erg)

    def _gefunden(self, online, fehler, still):
        self._laeuft = False
        if fehler:
            if not still:
                QMessageBox.warning(self.f, "Nach Updates suchen", f"Keine Verbindung zum Update:\n\n{fehler_text(fehler)}"
                                    "\n\nHilfe → Update-Center → Diagnose zeigt die Ursache und erstellt einen "
                                    "Bericht für die IT.")
            return
        if not update.neuer(online, self.lokal):
            if not still:
                self.f.meldung(f"Das Programm ist aktuell: {update.stand_text(self.lokal)}.")
            return
        if still and QApplication.activeModalWidget() is not None:
            # gerade ist ein Dialog offen (STEP-Import, Optimieren …): nicht dazwischenfunken, später fragen
            QTimer.singleShot(SPAETER_FRAGEN_MS, lambda: self._gefunden(online, None, still))
            return
        self.anbieten(online)

    def anbieten(self, online):
        """Frage „Update verfügbar“ zeigen und je nach Klick einspielen. Ergebnis: True, wenn geladen."""
        quelle_text = self.quelle_obj.text() if self.quelle_obj is not None else ""
        m = frage(self.f, online, self.lokal, quelle_text, self.freigabe)
        m.exec()
        knopf = m.clickedButton()
        if knopf is m.jetzt:
            return self.einspielen(online)
        if knopf is getattr(m, "beenden", None):
            return self.einspielen(online, beim_beenden=True)
        update_quellen.verlauf_schreiben(self.verlauf_pfad(), art="später", nach=online.get("stand"),
                                         quelle=quelle_text)
        return False

    def datei_einspielen(self, pfad):
        """Update-Datei (.rlupdate, USB-Stick, Download im Browser) prüfen und anbieten."""
        q = update_quellen.DateiQuelle(pfad, self.ordner / update.ARBEITSORDNER / "import")
        return self._aus_quelle(q)

    def ordner_einspielen(self, pfad):
        """Update aus einem gewählten Ordner (USB-Stick, anderer Netzwerkordner) prüfen und anbieten."""
        return self._aus_quelle(update_quellen.OrdnerQuelle(pfad))

    def _aus_quelle(self, q):
        try:
            online = q.liste()
        except update.UpdateFehler as e:
            protokoll.info(f"Update aus {q.text()} abgelehnt: {e}")
            QMessageBox.warning(self.f, "Update", f"Das Update lässt sich nicht verwenden:\n\n{e}")
            return False
        if not update.neuer(online, self.lokal):
            QMessageBox.information(self.f, "Update", f"{q.text()} enthält {update.stand_text(online)}. Installiert "
                                    f"ist schon {update.stand_text(self.lokal)} – nichts zu tun (ältere Stände werden "
                                    "nie eingespielt).")
            return False
        self.quelle_obj, self.quelle = q, q.adresse()
        self.freigabe = q.freigabe() if hasattr(q, "freigabe") else {}
        return self.anbieten(online)

    def _ausstehend(self, online, plan, neu_ordner, art="update"):
        quelle = self.quelle_obj.text() if self.quelle_obj is not None else str(self.quelle)
        return dict(online=online, plan=plan, neu_ordner=neu_ordner, art=art, quelle=quelle,
                    von=(self.lokal or {}).get("stand"), verlauf=self.verlauf_pfad(),
                    rueckmeldung=update_quellen.update_ordner(self._db()),
                    kuerzel=self._kuerzel())

    def _kuerzel(self):
        try:
            from . import teilen
            return teilen.kuerzel(self._db())
        except Exception:       # noqa: BLE001
            return ""

    def einspielen(self, online, beim_beenden=False):
        """Prüfen, laden, Datendatei sichern, dann das Programm geordnet beenden; ausgetauscht wird danach
        (nach_beenden). beim_beenden: laden und sichern, aber erst beim normalen Beenden austauschen.
        Ergebnis: True wenn geladen (und das Programm beendet wird bzw. beim Beenden einspielt)."""
        quelle = self.quelle_obj or update_quellen.Quelle(self.quelle)
        from .datenbank import SCHEMA_VERSION
        problem = update.schema_pruefen(online, SCHEMA_VERSION)
        if problem:
            protokoll.info("Update abgelehnt: " + problem)
            QMessageBox.warning(self.f, "Update", problem)
            return False
        fortschritt = QProgressDialog("Programmdateien prüfen …", "Abbrechen", 0, len(online["dateien"]), self.f)
        fortschritt.setWindowTitle("Update")
        fortschritt.setMinimumDuration(0)
        fortschritt.setAutoReset(False)
        fortschritt.setValue(0)
        stand = [0]
        hinweis = [""]          # „Verbindung unterbrochen, neuer Versuch …“ (update.holen)

        def pruefen(i, n):
            fortschritt.setValue(i)
            QApplication.processEvents()
            if fortschritt.wasCanceled():
                raise update.Abbruch()

        def geladen(n):
            if n:
                hinweis[0] = ""
            stand[0] += n
            fortschritt.setValue(min(stand[0], fortschritt.maximum()))
            fortschritt.setLabelText(f"Herunterladen: {mb(stand[0])} von {mb(plan['groesse'])}"
                                     + (f"\n{hinweis[0]}" if hinweis[0] else ""))
            QApplication.processEvents()
            if fortschritt.wasCanceled():
                raise update.Abbruch()

        def melden(text):
            hinweis[0] = text
            geladen(0)

        protokoll.info(f"Update: lade {update.stand_text(online)} von {quelle.text()} (Proxy: {update.systemproxy()})")
        verlauf = self.verlauf_pfad()
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
                    quelle.vorbereiten(online, plan)
                    neu_ordner = update.laden(self.ordner, self.quelle, online, plan, geladen, melden=melden)
                    break
                except update.UpdateFehler as e:
                    protokoll.info(f"Update: Download fehlgeschlagen: {e}")
                    # Paket fehlt: seit der Suche hat ein neuerer Stand die Dateiliste ersetzt -> mit der neuen.
                    # Geladenes bleibt (inhaltsadressiert, geprüft): ein neuer Versuch setzt dort fort.
                    update.verwerfen(self.ordner, download_behalten=True)
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
            update_quellen.verlauf_schreiben(verlauf, art="geladen", ergebnis="abgebrochen", nach=online.get("stand"),
                                             quelle=quelle.text())
            return False
        except (update.UpdateFehler, OSError) as e:
            fortschritt.close()
            update.verwerfen(self.ordner, download_behalten=isinstance(e, update.UpdateFehler))
            protokoll.info(f"Update ließ sich nicht laden: {e}")
            update_quellen.verlauf_schreiben(verlauf, art="geladen", ergebnis="fehler", nach=online.get("stand"),
                                             quelle=quelle.text(), fehler=str(e))
            QMessageBox.warning(self.f, "Update", f"Das Update ließ sich nicht laden, das Programm bleibt wie es "
                                f"war.\n\n{e}\n\nDetails stehen im Protokoll (Daten\\Protokoll\\fehler.log). "
                                "Hilfe → Update-Center → Diagnose hilft bei der Ursache.")
            return False
        fortschritt.close()
        update_quellen.verlauf_schreiben(verlauf, art="geladen", ergebnis="ok", von=(self.lokal or {}).get("stand"),
                                         nach=online.get("stand"), quelle=quelle.text(),
                                         dateien=len(plan["neu"]), groesse=plan["groesse"])
        self.ausstehend = self._ausstehend(online, plan, neu_ordner)
        if beim_beenden:
            self.beim_beenden = True
            protokoll.info(f"Update: {update.stand_text(online)} geladen, wird beim Beenden eingespielt")
            self.f.meldung(f"{update.stand_text(online)} ist geladen und gesichert; es wird beim Beenden des "
                           "Programms eingespielt.")
            return True
        protokoll.info(f"Update: {update.stand_text(online)} geladen ({len(plan['neu'])} Dateien), Programm wird "
                       "zum Austauschen beendet")
        QMessageBox.information(self.f, "Update", f"{update.stand_text(online)} ist geladen "
                                f"({len(plan['neu'])} Dateien, {mb(plan['groesse'])}).\n\n"
                                f"{NAME} schließt jetzt alle Fenster, legt die Angebote ab, sichert die Daten, "
                                "tauscht die Dateien aus und startet neu.")
        if not self.beenden():
            self.ausstehend = None
            update.verwerfen(self.ordner)
            self.f.meldung("Update abgebrochen (Programm nicht beendet), nichts geändert.")
            return False
        return True

    def zuruecksetzen(self):
        """Vorige Version wiederherstellen (Wiederherstellungspunkt aus dem letzten Update, ohne Internet)."""
        vorige = update.vorige_version(self.ordner)
        if vorige is None:
            QMessageBox.information(self.f, "Vorige Version", "Es ist keine vorige Version gespeichert. Sie entsteht "
                                    "beim nächsten Update.")
            return False
        from .datenbank import SCHEMA_VERSION
        schema = vorige.get("schema")
        warnung = ("\n\nAchtung: Die vorige Version kennt ein älteres Datenbank-Schema. Danach bitte die Sicherung "
                   "„vor_update“ wiederherstellen (Datei → Sicherung wiederherstellen …); Eingaben seit dem Update "
                   "gehen dabei verloren." if isinstance(schema, int) and schema < SCHEMA_VERSION else "")
        antwort = QMessageBox.question(
            self.f, "Vorige Version", f"Installiert: {update.stand_text(self.lokal)}\nZurück auf: "
            f"{update.stand_text(vorige)}\n\nDas Programm sichert die Daten, schließt sich, tauscht die Dateien "
            f"zurück und startet neu.{warnung}", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if antwort != QMessageBox.Yes:
            return False
        try:
            aus = update.zurueck_vorbereiten(self.ordner)
            _, fehler = self.f.db.sicherungen(zusatz="vor_update")
            if fehler:
                self.f.meldung(fehler, fehler=True)
        except (update.UpdateFehler, OSError) as e:
            update.verwerfen(self.ordner)
            QMessageBox.warning(self.f, "Vorige Version", str(e))
            return False
        self.quelle_obj = None
        self.quelle = "vorige Version"
        self.ausstehend = self._ausstehend(aus["online"], aus["plan"], aus["neu_ordner"], art="zurück")
        protokoll.info(f"Update: zurück auf {update.stand_text(aus['online'])}, Programm wird beendet")
        if not self.beenden():
            self.ausstehend = None
            update.verwerfen(self.ordner)
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
    from . import datenspeicher
    datenspeicher.alle_stoppen()        # PostgreSQL des PCs beenden: seine Programmdateien (pgsql) sind sonst belegt
    fortschritt = QProgressDialog("Dateien werden ausgetauscht …", None, 0, 0)
    fortschritt.setWindowTitle(f"{NAME} – Update")
    fortschritt.setMinimumDuration(0)
    fortschritt.show()
    QApplication.processEvents()

    def warten(gesperrt, rest):
        fortschritt.setLabelText(f"Warte, bis {gesperrt[0]} frei ist … (noch {rest:.0f} s)\n"
                                 f"{update.sperr_grund(gesperrt[0], ordner)}")
        QApplication.processEvents()

    ergebnis, fehler = None, None
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
        if gesperrt and update.nur_anleitungen(gesperrt):
            # nur die Anleitung hält jemand fest (PDF-Programm, Vorschau, Virenscanner): das Programm trotzdem
            # aktualisieren, die Anleitung tauscht der nächste Start (update.nachholen)
            protokoll.info("Update: Anleitung gesperrt, wird beim nächsten Start getauscht: " + ", ".join(
                f"{r} ({update.sperr_grund(r, ordner)})" for r in gesperrt))
            plan = update.zurueckstellen(ordner, plan, neu_ordner, online, gesperrt)
            continue
        if gesperrt:
            protokoll.info("Update: gesperrt " + "; ".join(f"{r} ({update.sperr_grund(r, ordner)})"
                                                            for r in gesperrt))
            fortschritt.hide()
            antwort = QMessageBox.warning(
                None, f"{NAME} – Update", f"{update.sperr_text(gesperrt, ordner)}\n\nBitte schließen und „Wiederholen“ "
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
    melden_ergebnis(ausstehend, ergebnis, fehler)
    if starten is None and getattr(sys, "frozen", False):
        starten = QProcess.startDetached
    if starten is not None:
        starten(exe or sys.executable, ["--nach-update", ergebnis])
    return ergebnis


def melden_ergebnis(ausstehend, ergebnis, fehler=None):
    """Ergebnis des Einspielens in den Verlauf dieses Platzes und als Rückmeldung in den Update-Ordner (der Admin
    sieht dort, welcher Platz welche Version hat). Fehler beim Schreiben zählen nicht."""
    online = ausstehend["online"]
    stand = online.get("stand") if ergebnis == "ok" else ausstehend.get("von")
    version = online.get("version") if ergebnis == "ok" else None
    update_quellen.verlauf_schreiben(ausstehend.get("verlauf"), art="eingespielt", ergebnis=ergebnis,
                                     von=ausstehend.get("von"), nach=online.get("stand"), quelle=ausstehend.get("quelle"),
                                     zurueck=ausstehend.get("art") == "zurück", fehler=fehler)
    if ausstehend.get("rueckmeldung"):
        update_verteilen.rueckmelden(ausstehend["rueckmeldung"], dict(
            kuerzel=ausstehend.get("kuerzel"), version=version, stand=stand, ergebnis=ergebnis,
            quelle=ausstehend.get("quelle"), fehler=fehler))
