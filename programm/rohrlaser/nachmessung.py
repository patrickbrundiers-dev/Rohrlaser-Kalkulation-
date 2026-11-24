"""Langsame Teile im Hintergrund (Vorschlag N4, Patrick 07.11.2026): messen beim STEP-Import nur noch Körper, die schon
lange laufen (step_messen --zwischenstand), öffnet der Prüfdialog mit dem Zwischenstand. Diese Körper stehen dort als
„Messung läuft noch“ und rücken nach, sobald die Messung fertig ist; OK wartet nötigenfalls auf sie.
"""
import shutil
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

    def warten(self, parent, offen):
        """Auf das Ende der Messung warten (Fortschrittsfenster, „Ohne sie übernehmen“ bricht ab). True = fertig."""
        if not self.laeuft():
            return True
        f = QProgressDialog(f"{offen} langsame(s) Teil(e) werden noch gemessen …", "Ohne sie übernehmen", 0, 0, parent)
        f.setWindowTitle("STEP-Import")
        f.setWindowModality(Qt.WindowModal)
        f.setMinimumDuration(0)
        schleife = QEventLoop()
        self.proz.finished.connect(schleife.quit)
        f.canceled.connect(schleife.quit)
        uhr = QTimer()
        uhr.timeout.connect(lambda: schleife.quit() if not self.laeuft() else None)
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
        for k, v in m.items():
            if k.startswith("_") and k not in ("_netz", "_struktur", "_nahtkandidaten"):
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
