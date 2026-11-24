"""Rohrzug aus XYZ-Punkten (Plan Paket K4, Idee aus LogiTRACE): Die Punkte sind die Mittellinie eines Rohrzugs
(Geländer, Rahmen, Gestell). Zwischen zwei Punkten liegt ein gerades Rohr; an jedem inneren Punkt stoßen zwei Rohre
mit Gehrung aneinander (halber Knickwinkel je Rohr). Liegt der letzte Punkt auf dem ersten, ist der Zug geschlossen
und hat auch dort eine Gehrung. Das Ergebnis hat dieselbe Form wie rahmen.bauen: Rohre mit Länge, Enden und
Einbaulage, damit das Angebot daraus einen Satz mit 3D und danach eine Schweißbaugruppe macht.

Maße: Länge eines Rohrs = von Spitze zu Spitze (wie im Rohr-Editor: Mittellinie + an jeder Gehrung halbes
Profilmaß in der Knickebene × tan Gehrungswinkel). Die lange Seite jeder Gehrung liegt außen an der Ecke.
Quadrat- und Rechteckrohr nur in einer Ebene (sonst müsste sich das Profil verdrehen); Rundrohr auch räumlich.
Rechteckrohr liegt wie beim Rahmen-Assistent, hochkant mit dem anderen Maß in der Knickebene."""
import math
import re

from . import rahmen
from . import skizze as sk

TOL_PUNKT = 0.01        # mm: gleiche Punkte (doppelt eingegeben, geschlossener Zug)
TOL_GERADE = 0.05       # Grad: kein Knick, die Punkte liegen auf einer Geraden (Punkt fällt weg)
TOL_EBENE = 0.05        # mm: Abstand von der Ebene des Zugs (Quadrat- und Rechteckrohr)
MAX_KNICK = 150.0       # Grad: größerer Knick = Gehrung über 75°, nicht mehr schneidbar
NAME = "Rohrzug"


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _lg(a):
    return math.sqrt(sum(c * c for c in a))


def _norm(a):
    lg = _lg(a)
    return tuple(c / lg for c in a)


def _zahl(text):
    return float(text.replace(",", "."))


def punkte_lesen(text):
    """[(x, y, z)] aus Text: je Zeile ein Punkt, Werte getrennt durch Leerzeichen, Tabulator oder Semikolon (Komma =
    Dezimalkomma) oder nur durch Kommas (dann Punkt als Dezimalzeichen). Leere Zeilen, Kommentare (#) und
    Kopfzeilen ohne Zahlen fallen weg; eine führende Nummer (4 Werte) wird übersprungen. ValueError mit
    Zeilennummer bei falschen Zeilen."""
    out = []
    for nr, zeile in enumerate((text or "").splitlines(), 1):
        z = zeile.split("#", 1)[0].strip()
        if not z or not re.search(r"\d", z):
            continue
        if re.search(r"[;\t ]", z.strip()):
            teile = [t for t in re.split(r"[;\t ]+", z) if t]
        else:
            teile = z.split(",")
        try:
            werte = [_zahl(t) for t in teile]
        except ValueError:
            if not out and not re.match(r"^\s*[-+]?\d", z):
                continue                # Kopfzeile (X;Y;Z)
            raise ValueError(f"Zeile {nr}: „{zeile.strip()}“ ist kein Punkt (x y z).") from None
        if len(werte) == 4:
            werte = werte[1:]
        if len(werte) == 2:
            werte.append(0.0)
        if len(werte) != 3:
            raise ValueError(f"Zeile {nr}: drei Werte x y z erwartet, gefunden {len(werte)}.")
        out.append(tuple(werte))
    return out


def _aufbereiten(punkte):
    """Doppelte Punkte und Punkte auf einer Geraden weg; (Punkte, geschlossen)."""
    p = []
    for q in punkte:
        if not p or _lg(_sub(q, p[-1])) > TOL_PUNKT:
            p.append(tuple(float(c) for c in q))
    zu = len(p) > 3 and _lg(_sub(p[0], p[-1])) <= TOL_PUNKT
    if zu:
        p.pop()
    i = 0
    while len(p) > 2 and i < len(p):
        if not zu and i in (0, len(p) - 1):
            i += 1
            continue
        a, b, c = p[i - 1], p[i], p[(i + 1) % len(p)]
        w = _winkel(_norm(_sub(b, a)), _norm(_sub(c, b)))
        if w < TOL_GERADE:
            p.pop(i)
            continue
        i += 1
    return p, zu and len(p) >= 3


def _winkel(d1, d2):
    return math.degrees(math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(d1, d2))))))


def _ebene(p):
    """Normale der Ebene durch die Punkte oder None (Gerade)."""
    for i in range(1, len(p) - 1):
        n = rahmen._kreuz(_sub(p[i], p[0]), _sub(p[i + 1], p[0]))
        if _lg(n) > 1e-6 * max(1.0, _lg(_sub(p[i], p[0])) * _lg(_sub(p[i + 1], p[0]))):
            return _norm(n)
    return None


def _aussen(d, nachbar):
    """Außenseite der Ecke: Anteil von nachbar senkrecht zur Rohrachse d (Einheitsvektor)."""
    s = rahmen._skalar(nachbar, d)
    return _norm(tuple(nachbar[i] - s * d[i] for i in range(3)))


def _gewendet(e, lage, laenge):
    """Dasselbe Rohr von Ende B aus gesehen: Enden getauscht, Ursprung am anderen Ende, Achse und X-Richtung
    umgekehrt (Y bleibt, Winkel der Seiten wechseln das Vorzeichen). Ergebnis: (Eingaben, Lage)."""
    def ende(x):
        x = dict(x)
        if "richtung" in x:
            x["richtung"] = round((-x["richtung"]) % 360, 1)
        return x
    o, z, x = lage[0:3], lage[3:6], lage[6:9]
    o2 = tuple(o[i] + laenge * z[i] for i in range(3))
    return dict(e, a=ende(e["b"]), b=ende(e["a"])), rahmen._lage(o2, tuple(-c for c in z), tuple(-c for c in x))


def bauen(profil, punkte, hochkant=False):
    """Rohre des Zugs: dict(teile = [dict(name, laenge, eingaben, lagen, koerper)], stoesse = [], stecken = False,
    knick = False, geschlossen, rohre = Zahl der Rohre, knicke = [Knickwinkel]); gleiche Rohre sind ein Teil mit
    mehreren Lagen (wie rahmen.bauen). ValueError bei unmöglichen Eingaben."""
    if (profil or {}).get("form") not in rahmen.PROFILE:
        raise ValueError("Rohrzug: Quadrat-, Rechteck- oder Rundrohr wählen.")
    qs = sk.Querschnitt(profil)
    rund = bool(qs.r)
    if not rund and (not qs.B or not qs.H):
        raise ValueError("Rohrzug: Profilmaße fehlen.")
    p, zu = _aufbereiten(punkte or ())
    if len(p) < 2:
        raise ValueError("Rohrzug: mindestens zwei verschiedene Punkte eingeben.")
    n_seg = len(p) if zu else len(p) - 1
    d = [_norm(_sub(p[(i + 1) % len(p)], p[i])) for i in range(n_seg)]
    knicke = []
    for k in (range(len(p)) if zu else range(1, len(p) - 1)):
        w = _winkel(d[k - 1], d[k % n_seg])
        if w > MAX_KNICK:
            raise ValueError(f"Rohrzug: Knick an Punkt {k + 1} ist {w:.0f}° (höchstens {MAX_KNICK:.0f}°, sonst "
                             "wäre die Gehrung über 75°).")
        knicke.append((k, w))
    normale = _ebene(p)
    if not rund:
        if normale is not None:
            for i, q in enumerate(p):
                ab = abs(rahmen._skalar(_sub(q, p[0]), normale))
                if ab > TOL_EBENE:
                    raise ValueError(f"Rohrzug: Punkt {i + 1} liegt {ab:.2f} mm außerhalb der Ebene. Quadrat- und "
                                     "Rechteckrohr nur in einer Ebene (das Profil müsste sich sonst verdrehen); "
                                     "räumlich geht Rundrohr.")
    winkel_an = dict(knicke)

    def mass_quer(lage, richtung_welt):
        """Profilmaß des Rohrs quer zur Achse in Richtung richtung_welt (Knickebene)."""
        if rund:
            return 2 * qs.r
        x = lage[6:9]
        return qs.B if abs(rahmen._skalar(richtung_welt, x)) > 0.5 else qs.H

    koerper = []
    for i in range(n_seg):
        a, b = p[i], p[(i + 1) % len(p)]
        z = d[i]
        ka, kb = i, (i + 1) % len(p)
        aus_a = _aussen(z, d[i - 1]) if ka in winkel_an else None
        aus_b = _aussen(z, tuple(-c for c in d[(i + 1) % n_seg])) if kb in winkel_an else None
        ref = aus_a or aus_b
        if ref is None:         # einzelnes gerades Rohr
            ref = _norm(rahmen._kreuz(z, normale)) if normale else (
                (0.0, 0.0, 1.0) if abs(z[2]) < 0.9 else (1.0, 0.0, 0.0))
            ref = _aussen(z, ref)
        if hochkant and not rund:
            x = tuple(-c for c in ref)
        else:
            x = rahmen._kreuz(ref, z)
        lage0 = rahmen._lage((0, 0, 0), z, x)
        enden, zug = [], []
        for k, aus in ((ka, aus_a), (kb, aus_b)):
            if aus is None:
                enden.append({})
                zug.append(0.0)
                continue
            g = winkel_an[k] / 2
            enden.append({"winkel": round(g, 3), "richtung": rahmen._winkel(lage0, aus)})
            zug.append(mass_quer(lage0, aus) / 2 * math.tan(math.radians(g)))
        mitte = _lg(_sub(b, a))
        laenge = mitte + zug[0] + zug[1]
        if mitte - zug[0] - zug[1] < -1e-6 or laenge <= 0:
            raise ValueError(f"Rohrzug: Rohr {i + 1} (Punkt {i + 1} bis {(i + 1) % len(p) + 1}) ist für die "
                             "Gehrungen zu kurz.")
        o = tuple(a[j] - zug[0] * z[j] for j in range(3))
        e = dict(a=enden[0], b=enden[1], konturen=[])
        koerper.append((f"{NAME} Rohr {i + 1}", round(laenge, 2), e, rahmen._lage(o, z, x)))
    teile = []
    for nr, (name, laenge, e, lage) in enumerate(koerper, 1):
        gleich = next((t for t in teile if abs(t["laenge"] - laenge) < 0.01 and t["eingaben"] == e), None)
        if not gleich:          # dasselbe Rohr andersherum eingebaut (z. B. die Schenkel eines U)
            e2, lage2 = _gewendet(e, lage, laenge)
            gleich = next((t for t in teile if abs(t["laenge"] - laenge) < 0.01 and t["eingaben"] == e2), None)
            if gleich:
                lage = lage2
        if gleich:
            gleich["lagen"].append(lage)
            gleich["koerper"].append(nr)
            gleich["name"] = gleich["name"].split(" Rohr ")[0] + " Rohr " + ", ".join(
                str(k) for k in gleich["koerper"])
            continue
        teile.append(dict(name=name, laenge=laenge, eingaben=e, lagen=[lage], koerper=[nr]))
    return dict(teile=teile, stoesse=[], stecken=False, knick=False, geschlossen=zu, rohre=len(koerper),
                knicke=[round(w, 2) for _, w in knicke], punkte=p)


def mittellinie(erg):
    """Gesamtlänge der Mittellinie [mm] (Kontrolle gegen die Eingabe)."""
    p = erg["punkte"]
    n = len(p) if erg["geschlossen"] else len(p) - 1
    return sum(_lg(_sub(p[(i + 1) % len(p)], p[i])) for i in range(n))


def text(erg, profil_text=""):
    """Überblick für das Fenster: Zahl der Rohre, Knicke und die Rohre wie rahmen.text."""
    from .rechnen import zahl
    kopf = (f"{erg['rohre']} Rohre, {'geschlossen' if erg['geschlossen'] else 'offen'}, Mittellinie "
            f"{zahl(mittellinie(erg), 1)} mm")
    if erg["knicke"]:
        kopf += ", Knicke " + ", ".join(f"{zahl(w, 1)}°" for w in erg["knicke"])
    return [kopf] + rahmen.text(erg, profil_text)
