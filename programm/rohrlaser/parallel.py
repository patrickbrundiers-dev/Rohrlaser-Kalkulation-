"""Schnittpläne großer Angebote auf mehreren Prozessen rechnen (Performance-Audit F2, 23.10.2026).

Die Gruppen eines Angebots (Profil, Werkstoff, Oberfläche, Stangenlänge …) sind voneinander unabhängig; jede rechnet
optimierung.optimiere. Ab PARALLEL_AB_TEILE Teilen verteilt vorrechnen() die Gruppen auf Hilfsprozesse (dasselbe
Programm mit --optimierer, beim Entwickeln python -m rohrlaser.parallel); optimierung.optimiere übernimmt danach das
fertige Ergebnis. Jeder Prozess rechnet dieselben Schritte (begrenzt nach Schritten, nicht nach Zeit), das Ergebnis
ist also genau dasselbe wie nacheinander gerechnet. Startet ein Hilfsprozess nicht oder bricht ab, rechnet das
Programm wie bisher selbst. Die Hilfsprozesse bleiben bis zum Programmende bereit (Start kostet ~1 s).

Verbindung: multiprocessing.connection (Windows: Named Pipe, sonst Unix-Socket) mit zufälligem Schlüssel; je Auftrag
(Nummer, Gruppe) zurück (Nummer, (Folgen als Teilnummern, bewiesen, schranke)) oder (Nummer, None) bei Fehler.
"""
import atexit
import os
import secrets
import subprocess
import sys
import threading
from multiprocessing.connection import Client, Listener, wait
from pathlib import Path

from . import optimierung as opt

PARALLEL_AB_TEILE = 1500    # erst ab so vielen Teilen (alle Aufträge zusammen) lohnt der Start der Hilfsprozesse
PROZESSE_MAX = 4
START_WARTEN = 30           # s: so lange darf der Start eines Hilfsprozesses dauern

_helfer = []                # [(Prozess, Verbindung)]
_sperre = threading.Lock()  # ein Lauf gleichzeitig; ein zweiter (z. B. Staffel-Hintergrund) rechnet selbst


def anzahl_prozesse(auftraege):
    """Wie viele Hilfsprozesse sich lohnen (0 = selbst rechnen)."""
    if len(auftraege) < 2 or sum(len(g.teile) for g in auftraege) < PARALLEL_AB_TEILE:
        return 0
    n = min(PROZESSE_MAX, (os.cpu_count() or 1) - 1, len(auftraege))
    return n if n >= 2 else 0


def _befehl(adresse, schluessel):
    if getattr(sys, "frozen", False):           # Rohrlaser-Angebotskalkulation.exe (start.py)
        return [sys.executable, "--optimierer", adresse, schluessel]
    return [sys.executable, "-m", "rohrlaser.parallel", adresse, schluessel]


def _starten(n):
    """Hilfsprozesse bis zur Anzahl n starten. Ergebnis: True, wenn n bereitstehen."""
    _helfer[:] = [(p, c) for p, c in _helfer if p.poll() is None]
    if len(_helfer) >= n:
        return True
    schluessel = secrets.token_bytes(16)
    with Listener(authkey=schluessel) as hoerer:
        umgebung = dict(os.environ)
        if not getattr(sys, "frozen", False):
            umgebung["PYTHONPATH"] = os.pathsep.join([str(Path(__file__).resolve().parents[1])] +
                                                     ([umgebung["PYTHONPATH"]] if umgebung.get("PYTHONPATH") else []))
        neu = []
        for _ in range(n - len(_helfer)):
            neu.append(subprocess.Popen(_befehl(hoerer.address, schluessel.hex()), env=umgebung,
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        verbunden = []

        def annehmen():
            try:
                for _ in neu:
                    verbunden.append(hoerer.accept())
            except OSError:
                pass
        t = threading.Thread(target=annehmen, daemon=True)
        t.start()
        t.join(START_WARTEN)
        if len(verbunden) < len(neu):       # nicht alle gestartet: ohne Hilfsprozesse weiter
            for p in neu:
                p.kill()
            for c in verbunden:
                c.close()
            return False
        # Zuordnung Prozess/Verbindung ist für die Arbeit egal (beendet werden alle zusammen)
        _helfer.extend(zip(neu, verbunden))
    return True


def beenden():
    for p, c in _helfer:
        try:
            c.close()
        except OSError:
            pass
        try:
            p.wait(2)
        except subprocess.TimeoutExpired:
            p.kill()
    _helfer.clear()


atexit.register(beenden)


def vorrechnen(auftraege, melden=None):
    """Gruppen auf Hilfsprozessen optimieren. Ergebnis: {optimierung.schluessel(Gruppe): (Folgen als
    [[(Teilnummer, Drehung)]], bewiesen, schranke)} für optimierung.vorgerechnet; leer = selbst rechnen.
    melden(fertig, gesamt) nach jedem Ergebnis; löst es eine Ausnahme aus (Abbruch), werden die Hilfsprozesse
    beendet und die Ausnahme weitergegeben."""
    n = anzahl_prozesse(auftraege)
    if not n or not _sperre.acquire(blocking=False):
        return {}
    try:
        if not _starten(n):
            return {}
        # die größten Gruppen zuerst (dauern am längsten), freie Prozesse holen sich die nächste
        reihe = sorted(range(len(auftraege)), key=lambda i: -len(auftraege[i].teile))
        schluessel = {i: opt.schluessel(auftraege[i]) for i in reihe}
        ergebnis, laufend, frei = {}, {}, [c for _, c in _helfer[:n]]
        try:
            while reihe or laufend:
                while reihe and frei:
                    c, i = frei.pop(), reihe.pop(0)
                    c.send((i, auftraege[i]))
                    laufend[c] = i
                bereit = wait(list(laufend), timeout=5)
                if not bereit and any(p.poll() is not None for p, _ in _helfer[:n]):
                    beenden()           # Hilfsprozess weg, ohne zu antworten: was fehlt, rechnet optimiere selbst
                    break
                for c in bereit:
                    nr, erg = c.recv()
                    laufend.pop(c)
                    frei.append(c)
                    if erg is not None:
                        ergebnis[schluessel[nr]] = erg
                    if melden:
                        melden(len(auftraege) - len(reihe) - len(laufend), len(auftraege))
        except (EOFError, OSError):     # Verbindung weg: was fehlt, rechnet optimiere selbst
            beenden()
        except BaseException:
            beenden()                   # Abbruch: laufende Aufträge nicht weiterrechnen lassen
            raise
        return ergebnis
    finally:
        _sperre.release()


def dienst(adresse, schluessel):
    """Hilfsprozess: Aufträge annehmen und rechnen, bis die Verbindung geschlossen wird."""
    with Client(adresse, authkey=bytes.fromhex(schluessel)) as c:
        while True:
            try:
                nr, g = c.recv()
            except (EOFError, OSError):
                return 0
            try:
                folgen = opt.optimiere(g)
                stelle = {id(t): i for i, t in enumerate(g.teile)}
                erg = ([[(stelle[id(t)], d) for t, d in f] for f in folgen], g.bewiesen, g.schranke)
            except Exception:       # noqa: BLE001 – der Hauptprozess rechnet diese Gruppe dann selbst
                erg = None
            c.send((nr, erg))


if __name__ == "__main__":
    sys.exit(dienst(sys.argv[1], sys.argv[2]))
