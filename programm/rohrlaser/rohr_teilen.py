"""Rohr an einer Stelle in zwei Teile teilen (Plan 3D/Abwicklung P6.2, Patrick 20.11.2026 „Alles einbauen“).

teilen(eingaben, L, x) teilt die Eingaben des Schneidweg-Rechners (Enden a/b, Konturen) an der Stelle x ab Ende A:
Teil 1 behält Ende A und bekommt bei x ein gerades Ende B, Teil 2 bekommt ein gerades Ende A und behält Ende B; jede
Kontur geht zu dem Teil, in dem ihre Mitte liegt (Lage in Teil 2 ab dem neuen Ende A). Muster mit Abstand werden
an der Stelle in zwei Zeilen aufgeteilt, verteilte Konturen ohne Lage bleiben je Teil verteilt (Anzahl nach Länge).
Eine Kontur, die über die Trennstelle reicht, wird nicht zerschnitten: Ergebnis None mit Grund.

Nur Eingaben, ohne Oberfläche und ohne Datenbank; gerechnet wird danach wie für jede Position (schneidweg.rechnen),
keine zweite Rechnung. Gemessene Werte aus der STEP (Umriss der Enden, gemessene Längen) gelten für das ganze Teil
und werden in den Teilen entfernt, damit nichts Falsches als „STEP gemessen“ erscheint.
"""
import copy

from . import skizze as sk

MIN_REST = 1.0          # mm: kürzeres Teil ist kein Teil


def teilen(eingaben, L, x, qs=None):
    """(teil1, teil2) mit teil = dict(eingaben, laenge) oder (None, Grund)."""
    L, x = float(L or 0), float(x or 0)
    if L <= 0:
        return None, "Teilelänge fehlt."
    if not MIN_REST <= x <= L - MIN_REST:
        return None, f"Trennstelle muss zwischen {MIN_REST:g} mm und {L - MIN_REST:g} mm liegen."
    e = copy.deepcopy(eingaben or {})
    konturen = e.get("konturen") or []
    eins, zwei = [], []
    for z, k in enumerate(konturen):
        try:
            teile = _kontur_teilen(k, z, konturen, L, x, qs)
        except _Ueber as u:
            return None, str(u)
        if teile[0]:
            eins.append(teile[0])
        if teile[1]:
            zwei.append(teile[1])
    gerade = dict(winkel=0)
    e1 = _ohne_messung(dict(e, b=dict(gerade), konturen=eins))
    e2 = _ohne_messung(dict(e, a=dict(gerade), konturen=zwei))
    return dict(eingaben=e1, laenge=round(x, 3)), dict(eingaben=e2, laenge=round(L - x, 3))


class _Ueber(ValueError):
    pass


def _kontur_teilen(k, zeile, konturen, L, x, qs):
    """(Kontur für Teil 1 oder None, Kontur für Teil 2 oder None)."""
    lagen = [d for d in sk.lagen(konturen, L, qs) if d["zeile"] == zeile and not d.get("kopie")]
    if not lagen:
        return copy.deepcopy(k), None
    for d in lagen:                     # Lage je Stück (Loch eines Lochfelds: Mitte des Felds + _dx)
        d["_x"] = d["x"] + float(d["eingabe"].get("_dx") or 0.0)
        umr = sk.umriss_kontur(dict(d["eingabe"], _dx=None, _dq=None)) or [(0.0, 0.0)]
        halb = (max(p[0] for p in umr) - min(p[0] for p in umr)) / 2
        if d["_x"] - halb < x - 1e-6 and d["_x"] + halb > x + 1e-6:
            return _fehler(k, d, x)
    n1 = [d for d in lagen if d["_x"] < x]
    n2 = [d for d in lagen if d["_x"] >= x]
    if k.get("art") == "Lochfeld":      # ein Feld bleibt ganz: nur auf einer Seite teilbar
        if n1 and n2:
            raise _Ueber(f"Lochfeld bei {lagen[0]['x']:g} mm liegt auf beiden Seiten der Trennstelle {x:g} mm. Bitte "
                         "eine andere Stelle wählen.")
        if n1:
            return copy.deepcopy(k), None
        t2 = copy.deepcopy(k)
        if t2.get("x") is not None:
            t2["x"] = round(float(t2["x"]) - x, 3)
        return None, t2
    if k.get("x") is None and not (k.get("art") in ("Schlitz", "Ausklinkung")):
        # verteilt ohne Lage: Anzahl nach Lage auf die Teile, je Teil wieder verteilt
        return (dict(copy.deepcopy(k), anzahl=len(n1)) if n1 else None,
                dict(copy.deepcopy(k), anzahl=len(n2)) if n2 else None)
    t1 = t2 = None
    if n1:
        t1 = copy.deepcopy(k)
        t1["anzahl"] = len(n1)
    if n2:
        t2 = copy.deepcopy(k)
        t2["anzahl"] = len(n2)
        t2["x"] = round(n2[0]["_x"] - x, 3)
        if k.get("ende_teil") == "A":
            t2.pop("ende_teil", None)
    if t1 is not None and k.get("ende_teil") == "B":
        t1.pop("ende_teil", None)
    return t1, t2


def _fehler(k, d, x):
    raise _Ueber(f"{sk.kurz(k)} bei {d['_x']:g} mm reicht über die Trennstelle {x:g} mm. Bitte eine andere Stelle "
                 "wählen.")


def _ohne_messung(e):
    for s in ("a", "b"):
        ende = e.get(s)
        if isinstance(ende, dict):
            for schl in ("umriss", "gemessen"):
                ende.pop(schl, None)
    for schl in ("l_step",):
        e.pop(schl, None)
    return e


def summe_ok(eingaben, L, teil1, teil2, qs=None):
    """Gegenprobe: Längen ergeben L, jede Kontur (Stück) liegt in genau einem Teil."""
    if abs(teil1["laenge"] + teil2["laenge"] - float(L)) > 1e-6:
        return False
    n = len([d for d in sk.lagen((eingaben or {}).get("konturen"), L, qs) if not d.get("kopie")])
    n1 = len([d for d in sk.lagen(teil1["eingaben"].get("konturen"), teil1["laenge"], qs) if not d.get("kopie")])
    n2 = len([d for d in sk.lagen(teil2["eingaben"].get("konturen"), teil2["laenge"], qs) if not d.get("kopie")])
    return n == n1 + n2
