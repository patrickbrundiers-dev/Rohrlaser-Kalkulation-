"""Messprozess -> Aufsicht: eine Nachricht mit OpenCascade-Form darf nie still verloren gehen (Patrick 06.11.2026,
0003-400-001: „cannot pickle TopoDS_Solid“ im Hintergrund-Thread der Queue, der Import hing über 80 Minuten).

Geprüft: step_messen._senden entfernt Formen aus Teil, Wörterbuch, Liste und Tupel (übrige Werte bleiben) und
schickt bei nicht übertragbaren Resten eine Fehlermeldung statt nichts.

Aufruf: python tests/test_step_senden.py
"""
import pickle
import queue
import sys
import threading
from collections import namedtuple
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung")]

from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402

import step_geometrie  # noqa: E402
import step_messen  # noqa: E402


class Teil:
    pass


P = namedtuple("P", "form wert")


def main():
    fehler = []
    koerper = BRepPrimAPI_MakeBox(10, 20, 30).Solid()
    t = Teil()
    t.laenge, t.form = 123.4, koerper
    t.netz = {"punkte": [1, 2], "form": koerper, "liste": [5, (koerper, 6)], "p": P(koerper, 7)}
    t.alternative = Teil()
    t.alternative.solid, t.alternative.d = koerper, 3
    q = queue.Queue()
    step_messen._senden(q, ("teil", 0, ("koerper", 1, 5), t))
    ev = q.get_nowait()
    try:
        pickle.dumps(ev)
    except Exception as e:
        fehler.append(f"Nachricht nicht übertragbar: {e}")
    x = ev[3]
    if x is None or x.laenge != 123.4 or x.form is not None or x.netz["punkte"] != [1, 2] or \
            x.netz["liste"] != [5, (None, 6)] or x.netz["p"] != P(None, 7) or x.alternative.d != 3 or \
            x.alternative.solid is not None:
        fehler.append(f"falsch bereinigt: {vars(x) if x is not None else None}")

    class Sperrig:     # lässt sich gar nicht übertragen: Fehlermeldung statt verlorener Nachricht
        def __reduce__(self):
            raise TypeError("nein")
    step_messen._senden(q, ("fertig", 0, ("abschluss", 1), Sperrig()))
    ev = q.get_nowait()
    if ev[:4] != ("fertig", 0, ("abschluss", 1), None) or "nicht übertragbar" not in ev[4]:
        fehler.append(f"keine Fehlermeldung: {ev}")

    # Ursache bei 0003: _rahmen der Auswahl einer Auswahl (Kantteil -> Profil -> offenes Profil) blieb dran
    a, b, c = Teil(), Teil(), Teil()
    for x in (a, b, c):
        x.alternative, x.geschlossen, x.arten, x._rahmen = None, None, None, {"solid": koerper}
    a.alternative, b.alternative = b, c
    step_geometrie.teil_uebergeben(a)
    try:
        pickle.dumps(a)
    except Exception as e:
        fehler.append(f"teil_uebergeben: verschachtelte Auswahl nicht übertragbar ({e})")

    # echte multiprocessing-Queue: kommt an (vorher: Ausnahme im Feeder-Thread, nichts kam an)
    import multiprocessing as mp
    mq = mp.Queue()
    t2 = Teil()
    t2.form = koerper
    threading.Thread(target=step_messen._senden, args=(mq, ("teil", 0, ("koerper", 1, 2), t2))).start()
    try:
        ev = mq.get(timeout=10)
        if ev[3].form is not None:
            fehler.append("Form über die Queue übertragen?")
    except queue.Empty:
        fehler.append("Nachricht über multiprocessing-Queue verloren")
    for f in fehler:
        print("FEHLER", f)
    print("OK" if not fehler else f"{len(fehler)} Fehler")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
