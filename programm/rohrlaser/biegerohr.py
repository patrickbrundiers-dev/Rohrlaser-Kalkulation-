"""Biegerohre (Plan S9): gestreckte Länge, Biegezonen und Biegedaten aus der STEP-Messung (STEP-JSON 1.15, Block
'biegerohr'; step_messung/step_biegerohr.py).

Die Messung liefert die Mittellinie aus Geraden und Bögen (Länge, Radius, Winkel) und die Konturen mit ihrer Lage
auf der Mittellinie. Das Programm rechnet die gestreckte Länge mit dem Faktor der neutralen Faser (Einstellung
'biegerohr_faktor', 1,0 = Rohrmitte):  gestreckte Länge = Σ Geraden + Faktor × Σ (Radius × Winkel).
Konturen und Enden werden auf das gestreckte Rohr umgerechnet (in einem Bogen anteilig). Der Block steht in
positionen.technik unter 'biegerohr' (mit dem Faktor), so bleiben Skizze, Teile-Editor und Prüfung beim Teil."""
import json

from .stammdaten import ZUSATZ_BIEGEN  # noqa: F401  (Zusatzarbeit je Biegung)

FAKTOR = 1.0            # Vorgabe Faktor neutrale Faser


def lesen(x):
    """Block 'biegerohr' aus Messwert (JSON-Text), technik (dict oder JSON) oder None."""
    if isinstance(x, str):
        try:
            x = json.loads(x) if x else None
        except ValueError:
            return None
    if isinstance(x, dict) and "biegerohr" in x and "elemente" not in x:
        x = x.get("biegerohr")
    return x if isinstance(x, dict) and isinstance(x.get("elemente"), list) and x["elemente"] else None


def _f(br, faktor=None):
    if faktor is None:
        faktor = br.get("faktor", FAKTOR)
    try:
        faktor = float(faktor)
    except (TypeError, ValueError):
        faktor = FAKTOR
    return faktor if faktor > 0 else FAKTOR


def gestreckt(s, br, faktor=None):
    """Lage s auf der Mittellinie -> Lage x am gestreckten Rohr [mm]."""
    f = _f(br, faktor)
    x = 0.0
    for e in br["elemente"]:
        s0, s1 = float(e["s0"]), float(e["s1"])
        k = f if e["art"] == "bogen" else 1.0
        if s <= s1 + 1e-9:
            return x + k * max(0.0, s - s0)
        x += k * (s1 - s0)
    return x + (s - float(br["elemente"][-1]["s1"]))


def laenge(br, faktor=None):
    """Gestreckte Länge [mm]."""
    return gestreckt(float(br["elemente"][-1]["s1"]), br, faktor)


def biegungen(br, faktor=None):
    """Bögen am gestreckten Rohr: [{nr, x0, x1, winkel, radius, drehung, gerade (davor)}] (x ab Ende A)."""
    lra = [z for z in br.get("lra") or () if z.get("winkel")]
    out = []
    for e in br["elemente"]:
        if e["art"] != "bogen":
            continue
        z = lra[len(out)] if len(out) < len(lra) else {}
        out.append(dict(nr=len(out) + 1, x0=gestreckt(float(e["s0"]), br, faktor),
                        x1=gestreckt(float(e["s1"]), br, faktor), winkel=float(e.get("winkel") or 0),
                        radius=float(e.get("radius") or 0), drehung=float(z.get("drehung") or 0),
                        gerade=float(z.get("gerade") or 0)))
    return out


def geraden_zwischen(br):
    """Geraden zwischen zwei Biegungen: [(nr der Biegung davor, Länge)] (am Anfang und Ende nicht)."""
    el = br["elemente"]
    boegen = [i for i, e in enumerate(el) if e["art"] == "bogen"]
    out = []
    for n, (i, j) in enumerate(zip(boegen, boegen[1:]), start=1):
        out.append((n, sum(float(e["laenge"]) for e in el[i + 1:j] if e["art"] == "gerade")))
    return out


def in_zone(x0, x1, br, faktor=None, abstand=0.0):
    """Nummern der Biegungen, deren Zone (± abstand) der Bereich x0..x1 am gestreckten Rohr berührt."""
    return [b["nr"] for b in biegungen(br, faktor) if x1 > b["x0"] - abstand + 1e-6 and x0 < b["x1"] + abstand - 1e-6]


def _zahl(x, n=1):
    t = f"{round(float(x), n):.{n}f}".replace(".", ",")
    return t[:-2] if t.endswith(",0") else t


def lra_zeilen(br):
    """Biegedaten als Textzeilen: 'B1: L 200 · R 0° · A 90° · Radius 80' und zuletzt 'Ende: L 100'."""
    out = []
    for i, z in enumerate(br.get("lra") or (), start=1):
        if z.get("winkel"):
            out.append(f"B{i}: L {_zahl(z['gerade'])} · R {_zahl(z['drehung'])}° · A {_zahl(z['winkel'])}° · "
                       f"Radius {_zahl(z.get('radius') or 0)}")
        else:
            out.append(f"Ende: L {_zahl(z['gerade'])}")
    return out


def xyz_zeilen(br):
    """Eckpunkte des Tangentenzugs: 'P1: 0 / 0 / 0' …"""
    return [f"P{i}: " + " / ".join(_zahl(v) for v in p) for i, p in enumerate(br.get("xyz") or (), start=1)]


def kurz(br, faktor=None):
    """z. B. '2 Biegungen, gestreckt 638,5 mm (Mittellinie 638,5 mm, Faktor 1)'."""
    n = len(biegungen(br, faktor))
    return (f"{n} Biegung{'en' if n != 1 else ''}, gestreckt {_zahl(laenge(br, faktor))} mm (Mittellinie "
            f"{_zahl(br.get('mittellinie') or laenge(br, 1.0))} mm, Faktor {_zahl(_f(br, faktor), 3)})")


def technik_umrechnen(eing, br, faktor):
    """Eingaben des Schneidweg-Rechners (aus der Messung, x = Lage auf der Mittellinie) auf das gestreckte Rohr
    umrechnen und den Block 'biegerohr' mit dem Faktor anhängen. Ändert eing."""
    for k in eing.get("konturen") or ():
        if k.get("x") is not None:
            k["x"] = round(gestreckt(float(k["x"]), br, faktor), 1)
    eing["biegerohr"] = dict(br, faktor=_f(br, faktor))
    return eing
