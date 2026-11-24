"""Langsame Teile im Hintergrund (Vorschlag N4, Patrick 07.11.2026): messen beim STEP-Import nur noch Körper, die schon
lange laufen (step_messen --zwischenstand), öffnet der Prüfdialog mit dem Zwischenstand. Diese Körper stehen dort als
„Messung läuft noch“ und rücken nach, sobald die Messung fertig ist; OK wartet nötigenfalls auf sie.
"""
import shutil
import time
from pathlib import Path

from PySide6.QtCore import QEventLoop, QProcess, Qt, QTimer
from PySide6.QtWidgets import QProgressDialog

from . import step

ZWISCHENSTAND_S = 20        # so lange darf ein Körper laufen, bevor der Prüfdialog ohne ihn öffnet


class Nachmessung:
    """Laufende Messung nach dem Zwischenstand: Prozess, Arbeitsordner (wird mit beenden gelöscht), Ergebnisdateien."""

    def __init__(self, proz, ordner, ausgabe, netze, ergebnis):
        self.proz, self.ordner = proz, Path(ordner)
        self.ausgabe, self.netze, self.ergebnis_json = Path(ausgabe), Path(netze), Path(ergebnis)
        self._messwerte = None

    def laeuft(self):
        return self.proz is not None and self.proz.state() != QProcess.NotRunning

    def ok(self):
        return (not self.laeuft() and self.proz is not None and self.proz.exitStatus() == QProcess.NormalExit
                and self.proz.exitCode() in (0, 1) and self.ausgabe.exists())

    def messwerte(self):
        """Endgültige Messwerte (nach dem Ende der Messung) oder None (läuft noch / fehlgeschlagen)."""
        if self._messwerte is None and self.ok():
            self._messwerte = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(self.ausgabe), self.netze),
                                                      self.ergebnis_json)
        return self._messwerte

    def warten(self, parent, offen, namen=()):
        """Auf das Ende der Messung warten (Fortschrittsfenster mit Teilen und Wartezeit; „Nicht mehr warten“ bricht
        das Warten ab, was dann geschieht, entscheidet der Aufrufer). True = fertig."""
        if not self.laeuft():
            return True
        liste = ", ".join(str(n) for n in list(namen)[:4]) + (" …" if len(namen) > 4 else "")
        kopf = f"{offen} langsame(s) Teil(e) werden noch gemessen" + (f" ({liste})" if liste else "")
        f = QProgressDialog(kopf + " …", "Nicht mehr warten …", 0, 0, parent)
        f.setWindowTitle("STEP-Import")
        f.setWindowModality(Qt.WindowModal)
        f.setMinimumDuration(0)
        schleife = QEventLoop()
        self.proz.finished.connect(schleife.quit)
        f.canceled.connect(schleife.quit)
        start = time.monotonic()

        def tick():
            if not self.laeuft():
                schleife.quit()
                return
            s = int(time.monotonic() - start)
            f.setLabelText(f"{kopf} …\nWartezeit {s // 60}:{s % 60:02d} min – Bohrungen und Konturen dieser Teile "
                           "kommen erst mit der Messung.")
        uhr = QTimer()
        uhr.timeout.connect(tick)
        uhr.start(500)
        if self.laeuft():
            schleife.exec()
        uhr.stop()
        f.canceled.disconnect()
        f.close()
        return not self.laeuft()

    def beenden(self):
        """Messung abbrechen, falls sie noch läuft, und den Arbeitsordner löschen."""
        if self.laeuft():
            self.proz.kill()
            self.proz.waitForFinished(3000)
        shutil.rmtree(self.ordner, ignore_errors=True)


def einsetzen(messwerte, neue):
    """Platzhalter „Messung läuft noch“ in messwerte durch die endgültigen Messwerte (neue, gleiche Datei und Körper)
    ersetzen; was der Prüfdialog gesetzt hat (Schlüssel mit _), Artikel und Bauteilname bleiben. Struktur und
    Nahtkandidaten dieser Dateien kommen aus der endgültigen Messung. Ergebnis: Anzahl ersetzter Teile."""
    from . import drehfraes
    je = {(n.get("datei"), str(n.get("koerper"))): n for n in neue or ()}
    n_ersetzt, dateien = 0, set()
    for i, m in enumerate(messwerte):
        if not step.noch_in_messung(m):
            continue
        n = je.get((m.get("datei"), str(m.get("koerper"))))
        if n is None or step.noch_in_messung(n):
            continue
        neu = dict(n)
        # von Hand nachgetragener Platzhalter (Länge aus dem Hüllmaß, ohne Konturen): die Messung ersetzt den
        # Nachtrag ganz, sonst bliebe das geratene Profil bzw. „zurücknehmen“ führte zum Platzhalter (24.11.2026)
        nachtrag = ("_original", "_profil", "_uebernehmen") if m.get("_original") else ()
        for k, v in m.items():
            if k.startswith("_") and k not in ("_netz", "_struktur", "_nahtkandidaten") + nachtrag:
                neu[k] = v
        neu["artikel"], neu["bauteil"] = m.get("artikel"), m.get("bauteil") or n.get("bauteil")
        b = (drehfraes.daten(neu) or {}).get("normteil")
        if b:
            neu["_normteil"] = b
        messwerte[i] = neu
        dateien.add(m.get("datei"))
        n_ersetzt += 1
    erste = {}
    for n in neue or ():
        erste.setdefault(n.get("datei"), n)
    for m in messwerte:
        q = erste.get(m.get("datei"))
        if q is not None and m.get("datei") in dateien:
            m["_struktur"], m["_nahtkandidaten"] = q.get("_struktur"), q.get("_nahtkandidaten")
    return n_ersetzt
