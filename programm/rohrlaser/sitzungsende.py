"""Windows-Abmeldung, Neustart und Herunterfahren bei laufendem Programm (Auftrag Patrick 26.11.2026,
Windows-Update-Sicherheit).

Startet Windows für Updates neu, kommt erst WM_QUERYENDSESSION (Qt: commitDataRequest) und dann WM_ENDSESSION. Bei
WM_ENDSESSION sendet Qt aboutToQuit und kehrt zurück; danach beendet Windows den Prozess sofort, app.exec() kehrt nie
zurück. Ohne diesen Baustein liefen deshalb weder das Schließen der Datenbank noch das Stoppen des eingebetteten
PostgreSQL noch das Freigeben der Datensperre. PostgreSQL stellt sich dank Write-Ahead-Log zwar selbst wieder her,
aber eine laufende Tagessicherung blieb halb liegen.

einrichten(app, schritte) hängt sich an beide Signale: commitDataRequest merkt nur „Sitzung endet“ (Windows kann
das Herunterfahren noch abbrechen, wenn ein anderes Programm es aufhält; dann arbeitet das Programm normal weiter).
Erst aboutToQuit nach diesem Merker führt die Schritte aus, in ihrer Reihenfolge, jeder für sich abgesichert und
mit Zeitgrenze. Ein normales Beenden (Menü, Fenster schließen) läuft wie bisher über das Ende von main().

Dazu ruft einrichten() unter Windows SetProcessShutdownParameters: das Programm wird vor seinen PostgreSQL-
Prozessen benachrichtigt und kann den Server selbst sauber herunterfahren.

Kern (abschliessen) ohne Qt, damit er ohne Oberfläche getestet werden kann.
"""
import sys
import time

# Reihenfolge beim Herunterfahren: 0x100..0x3FF für Programme, höher = früher. Vorgabe ist 0x280; die
# PostgreSQL-Prozesse behalten sie und werden so nach diesem Programm beendet.
SHUTDOWN_STUFE = 0x300
ZEIT_S = 15.0           # alle Schritte zusammen (Windows wartet bei einer Abmeldung nur kurz)


class Sitzung:
    """Zustand der Windows-Sitzung für dieses Programm."""

    def __init__(self, schritte=(), melden=None, uhr=time.monotonic):
        self.schritte = list(schritte)       # [(Text, Funktion(rest_s))]
        self.endet = False                   # commitDataRequest gesehen
        self.erledigt = False                # Schritte ausgeführt (nie zweimal)
        self.ergebnis = []                   # [(Text, "ok" | Fehlertext)]
        self._melden = melden
        self._uhr = uhr

    def endet_jetzt(self, *_args):
        self.endet = True
        self._protokoll("Windows beendet die Sitzung (Abmelden, Neustart oder Herunterfahren)")

    def beim_beenden(self):
        """aboutToQuit: nur bei endender Sitzung die Schritte ausführen."""
        if self.endet:
            self.abschliessen()

    def abschliessen(self):
        """Alle Schritte nacheinander; ein Fehler hält die folgenden nicht auf. Ergebnis: self.ergebnis."""
        if self.erledigt:
            return self.ergebnis
        self.erledigt = True
        ende = self._uhr() + ZEIT_S
        for text, tun in self.schritte:
            rest = max(0.5, ende - self._uhr())
            try:
                tun(rest)
                self.ergebnis.append((text, "ok"))
            except Exception as e:      # noqa: BLE001 - beim Herunterfahren nie hängen oder abbrechen
                self.ergebnis.append((text, f"{type(e).__name__}: {e}"))
        self._protokoll("Sitzungsende: " + "; ".join(f"{t} {e}" for t, e in self.ergebnis))
        return self.ergebnis

    def _protokoll(self, text):
        if self._melden is None:
            return
        try:
            self._melden(text)
        except (OSError, RuntimeError, ValueError):     # Protokoll nicht schreibbar: Herunterfahren geht vor
            return


def reihenfolge_setzen(stufe=SHUTDOWN_STUFE):
    """Windows: dieses Programm vor den übrigen (PostgreSQL) benachrichtigen. Ergebnis: True, wenn gesetzt."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.kernel32.SetProcessShutdownParameters(stufe, 0))
    except (OSError, AttributeError):
        return False


def einrichten(app, schritte, melden=None):
    """An die QApplication hängen. Ergebnis: Sitzung (erledigt sagt main(), ob schon aufgeräumt ist)."""
    s = Sitzung(schritte, melden)
    app.commitDataRequest.connect(s.endet_jetzt)
    app.aboutToQuit.connect(s.beim_beenden)
    reihenfolge_setzen()
    return s
