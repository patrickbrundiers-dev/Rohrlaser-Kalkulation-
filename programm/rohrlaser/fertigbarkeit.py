"""Fertigbarkeit beim STEP-Import prüfen (Laserhub-Vergleich L1/L3, Patrick 20.11.2026 „Alles einbauen nach
Empfehlungen“; Grenzwerte je Maschine).

Laserhub nennt öffentlich Konstruktionsregeln für Rohrlaserteile (Loch und Steg mindestens 0,7 × Wand, Innenecken mit
Radius, Länge und Gewicht begrenzt). Diese Prüfung macht das mit den Werten der eigenen Maschine, bevor ein Teil ins
Angebot geht. Sie liest nur die vorhandene Messung (Konturen mit Umriss in der Abwicklung), misst nichts neu und
ändert nichts am Teil (Grundregel: Konturen 100 % wie STEP). Jeder Befund macht das Teil gelb mit Grund (nie rot, nie
automatisch geändert); „Passt“ im Prüfdialog bestätigt es wie jeden anderen Grund.

Grenzwerte der Maschine (Stammdaten → Maschinen, Gruppe „Fertigbarkeit“); leer = Vorgabe, 0 = Prüfung aus:
  fb_loch_faktor   kleinstes Loch bzw. schmalster Schlitz = Faktor × Wand (Vorgabe 0,7)
  fb_steg_faktor   schmalster Steg zwischen zwei Konturen bzw. zum geraden Rohrende = Faktor × Wand (Vorgabe 0,7)
  fb_eckradius     kleinster Innen-Eckradius [mm] (Vorgabe aus: scharfe Ecken im CAD schneidet der Laser mit dem
                   Strahlradius, Patricks Teile haben sie oft gewollt)
  fb_gravur_tiefe  tiefste Gravur, die der Laser macht [mm] (Vorgabe 0,5 wie die Messung); tiefer = Fräsen prüfen
Dazu die vorhandenen Maschinenfelder: Länge (max. Stange − Endbeschnitt − Greiferrest, kürzestes Teil min_teil) und
Hüllkreis (max./min. Hüllkreis-Ø).

Ergebnis je Teil in m["_fertigbarkeit"]: [{regel, text, x, seite, wert, grenze}]; step.ampel nimmt die Texte als
Gründe, bauteil_analyse als Merkmale „Fertigbarkeit“.
"""
import math

LOCH_FAKTOR = 0.7
STEG_FAKTOR = 0.7
GRAVUR_TIEFE = 0.5
MARKIERLOCH = 0.5       # Markierloch Ø0,5 (Fließlochbohrung) ist gewollt kleiner als die Wand
ECKE_KNICK = 30.0       # Grad: ab so viel Richtungsänderung ohne Bogen gilt eine Ecke als scharf
ECKE_SEGMENT = 1.0      # mm: beide Kanten an der Ecke mindestens so lang (sonst ist es ein angenäherter Bogen)
MAX_BEFUNDE = 50        # je Teil (Rest als Zahl)
MAX_KONTUREN_STEG = 400  # mehr Konturen: Stegprüfung nur zum Rohrende (sonst zu langsam)

LOCH, SCHLITZ, STEG, STEG_ENDE, ECKE, GRAVUR, LAENGE, KURZ, HUELLE = (
    "Loch", "Schlitz", "Steg", "Steg zum Ende", "Innenecke", "Gravur", "Länge", "Kürzestes Teil", "Hüllkreis")

FELDER = ("fb_loch_faktor", "fb_steg_faktor", "fb_eckradius", "fb_gravur_tiefe")


def _f(x, vorgabe=0.0):
    try:
        v = float(x)
        return v if math.isfinite(v) else vorgabe
    except (TypeError, ValueError):
        return vorgabe


def _leer(x):
    return x is None or (isinstance(x, str) and not x.strip())


def _z(x):
    return f"{round(_f(x), 2):g}".replace(".", ",")


def grenzen(maschine):
    """Grenzwerte aus der Maschinenzeile (leer = Vorgabe, 0 = aus)."""
    m = maschine or {}

    def wert(n, vorgabe):
        return vorgabe if _leer(m.get(n)) else _f(m.get(n))
    stange = _f(m.get("max_stange"))
    max_l = stange - _f(m.get("endbeschnitt")) - _f(m.get("greiferrest")) if stange > 0 else 0.0
    return dict(loch=wert("fb_loch_faktor", LOCH_FAKTOR), steg=wert("fb_steg_faktor", STEG_FAKTOR),
                eckradius=wert("fb_eckradius", 0.0), gravur=wert("fb_gravur_tiefe", GRAVUR_TIEFE),
                max_laenge=max_l, min_laenge=_f(m.get("min_teil")), max_hk=_f(m.get("max_huellkreis")),
                min_hk=_f(m.get("min_huellkreis")), maschine=str(m.get("maschinen_id") or ""))


# ---------------------------------------------------------------------------------------------- Geometrie (u, x)
def _punkte(d):
    out = []
    for p in d.get("umriss") or ():
        try:
            out.append((float(p[0]), float(p[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _box(pk):
    us, xs = [p[0] for p in pk], [p[1] for p in pk]
    return min(us), max(us), min(xs), max(xs)


def _punkt_strecke(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll <= 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / ll))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def _innen(p, pk):
    """Punkt im Polygon (gerade Anzahl Schnitte = außen)."""
    n, drin = len(pk), False
    for i in range(n):
        (u1, x1), (u2, x2) = pk[i], pk[(i + 1) % n]
        if (x1 > p[1]) != (x2 > p[1]) and p[0] < (u2 - u1) * (p[1] - x1) / ((x2 - x1) or 1e-12) + u1:
            drin = not drin
    return drin


def abstand(a, b):
    """Kleinster Abstand zweier geschlossener Umrisse [mm] (0 bei Überschneidung)."""
    if len(a) < 2 or len(b) < 2:
        return math.inf
    if _innen(a[0], b) or _innen(b[0], a):
        return 0.0
    best = math.inf
    for p, q in ((a, b), (b, a)):
        n = len(q)
        for pt in p:
            for i in range(n):
                best = min(best, _punkt_strecke(pt, q[i], q[(i + 1) % n]))
    return best


def scharfe_ecken(pk):
    """Anzahl scharfer Innenecken eines Konturumrisses (Ecke ohne Bogen: zwei gerade Kanten ≥ ECKE_SEGMENT mit
    Knick ≥ ECKE_KNICK). Angenäherte Bögen (viele kurze Kanten) zählen nicht."""
    n, k = len(pk), 0
    if n < 3:
        return 0
    for i in range(n):
        a, b, c = pk[i - 1], pk[i], pk[(i + 1) % n]
        v1, v2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        if l1 < ECKE_SEGMENT or l2 < ECKE_SEGMENT:
            continue
        cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))
        if math.degrees(math.acos(cos)) >= ECKE_KNICK:
            k += 1
    return k


# ---------------------------------------------------------------------------------------------- Prüfung
def _befund(regel, text, d=None, wert=None, grenze=None, bereich=None):
    """bereich = (x0, x1) längs für die Markierung im 3D (Vorgabe: Ausdehnung der Kontur d)."""
    d = d or {}
    out = dict(regel=regel, text=text, wert=None if wert is None else round(wert, 2),
               grenze=None if grenze is None else round(grenze, 2))
    if d.get("z") is not None:
        out["x"] = round(_f(d.get("z")), 1)
    if d.get("seite"):
        out["seite"] = str(d["seite"])
    if bereich is None:
        pk = _punkte(d)
        bereich = (_box(pk)[2], _box(pk)[3]) if pk else None
    if bereich:
        out["x0"], out["x1"] = round(min(bereich), 1), round(max(bereich), 1)
    return out


def _ist_rohr(m):
    return bool(m.get("profilform")) and (m.get("bauteiltyp") or "Profil") == "Profil" and \
        (m.get("profilform") or "") not in ("Blech", "Blech gekantet", "Drehteil", "Frästeil", "Normteil")


def pruefen(m, maschine=None):
    """Befunde eines gemessenen Teils (Liste, leer = fertigbar)."""
    if m.get("fehler") or not _ist_rohr(m):
        return []
    g = grenzen(maschine)
    wand = _f(m.get("wandstaerke"))
    laenge = _f(m.get("laenge"))
    try:
        import json
        konturen = m.get("konturen_liste")
        konturen = json.loads(konturen) if isinstance(konturen, str) else (konturen or [])
    except (ValueError, TypeError):
        konturen = []
    konturen = [d for d in konturen if isinstance(d, dict)]
    out = []
    innen = [d for d in konturen if d.get("art") not in ("Ende A", "Ende B")]
    durch = [d for d in innen if d.get("durchgehend", True) and d.get("art") not in ("Gravur", "Sackbohrung")]
    # Loch bzw. Schlitz kleiner als Faktor × Wand
    if g["loch"] > 0 and wand > 0:
        grenze = g["loch"] * wand
        for d in durch:
            if d.get("art") == "Bohrung":
                dm = _f(d.get("durchmesser")) or _f(d.get("huellmass"))
                if MARKIERLOCH + 1e-6 < dm < grenze - 1e-6:
                    out.append(_befund(LOCH, f"Loch Ø {_z(dm)} mm kleiner als {_z(g['loch'])} × Wand {_z(wand)} mm",
                                       d, dm, grenze))
            else:
                br = min(x for x in (_f(d.get("breite")), _f(d.get("laenge"))) if x > 0) \
                    if (_f(d.get("breite")) > 0 or _f(d.get("laenge")) > 0) else 0.0
                if 0 < br < grenze - 1e-6:
                    out.append(_befund(SCHLITZ, f"{d.get('art') or 'Kontur'} {_z(br)} mm breit, kleiner als "
                                       f"{_z(g['loch'])} × Wand {_z(wand)} mm", d, br, grenze))
    # Steg zwischen Konturen derselben Wand und zum geraden Rohrende
    if g["steg"] > 0 and wand > 0:
        grenze = g["steg"] * wand
        formen = [(d, _punkte(d)) for d in durch]
        formen = [(d, pk, _box(pk)) for d, pk in formen if len(pk) >= 3]
        ende = {d.get("art"): d for d in konturen if d.get("art") in ("Ende A", "Ende B")}
        for d, pk, (u0, u1, x0, x1) in formen:
            for name, rand in (("Ende A", x0), ("Ende B", laenge - x1)):
                e = ende.get(name)
                if e is not None and (e.get("form") or "gerade") == "gerade" and abs(_f(e.get("gehrung"))) < 0.05 \
                        and -1e-6 < rand < grenze - 1e-6:
                    out.append(_befund(STEG_ENDE, f"Steg zum {name} {_z(rand)} mm, kleiner als {_z(g['steg'])} × "
                                       f"Wand {_z(wand)} mm", d, rand, grenze,
                                       (0.0, x1) if name == "Ende A" else (x0, laenge)))
        if len(formen) <= MAX_KONTUREN_STEG:
            formen.sort(key=lambda t: t[2][2])
            for i, (d, pk, (u0, u1, x0, x1)) in enumerate(formen):
                wa = set(d.get("waende") or ([d["seite"]] if d.get("seite") else []))
                for e, qk, (v0, v1, y0, y1) in formen[i + 1:]:
                    if y0 - x1 >= grenze:
                        break
                    we = set(e.get("waende") or ([e["seite"]] if e.get("seite") else []))
                    if wa and we and not (wa & we):
                        continue
                    if v0 - u1 >= grenze or u0 - v1 >= grenze:
                        continue
                    s = abstand(pk, qk)
                    if 1e-6 < s < grenze - 1e-6:
                        out.append(_befund(STEG, f"Steg {_z(s)} mm zwischen {d.get('art') or 'Kontur'} (x "
                                           f"{_z(d.get('z'))}) und {e.get('art') or 'Kontur'} (x {_z(e.get('z'))}), "
                                           f"kleiner als {_z(g['steg'])} × Wand {_z(wand)} mm", d, s, grenze,
                                           (min(x0, y0), max(x1, y1))))
    # scharfe Innenecken (nur mit Grenzwert)
    if g["eckradius"] > 0:
        for d in durch:
            if d.get("art") == "Bohrung":
                continue
            k = scharfe_ecken(_punkte(d))
            if k:
                out.append(_befund(ECKE, f"{d.get('art') or 'Kontur'}: {k} Innenecke(n) ohne Radius (mind. "
                                   f"{_z(g['eckradius'])} mm)", d, 0.0, g["eckradius"]))
    # Gravur tiefer als der Laser graviert (bleibt Gravur und Rohr, Patrick 17.11.2026; nur Hinweis)
    if g["gravur"] > 0:
        for d in innen:
            if d.get("art") == "Gravur" and _f(d.get("tiefe")) > g["gravur"] + 1e-6:
                out.append(_befund(GRAVUR, f"Gravur {_z(d.get('tiefe'))} mm tief: der Laser markiert bis "
                                   f"{_z(g['gravur'])} mm, tiefer nur gefräst – prüfen", d, _f(d.get("tiefe")),
                                   g["gravur"]))
    # Länge und Hüllkreis gegen die Maschine
    if g["max_laenge"] > 0 and laenge > g["max_laenge"] + 1e-6:
        out.append(_befund(LAENGE, f"Teil {_z(laenge)} mm länger als die Maschine aus einer Stange schneidet "
                           f"({_z(g['max_laenge'])} mm)", None, laenge, g["max_laenge"]))
    if g["min_laenge"] > 0 and 0 < laenge < g["min_laenge"] - 1e-6:
        out.append(_befund(KURZ, f"Teil {_z(laenge)} mm kürzer als das kürzeste Teil der Maschine "
                           f"({_z(g['min_laenge'])} mm)", None, laenge, g["min_laenge"]))
    hk = huellkreis(m)
    if hk and g["max_hk"] > 0 and hk > g["max_hk"] + 1e-6:
        out.append(_befund(HUELLE, f"Hüllkreis Ø {_z(hk)} mm größer als die Maschine spannt "
                           f"(max. {_z(g['max_hk'])} mm)", None, hk, g["max_hk"]))
    if hk and g["min_hk"] > 0 and hk < g["min_hk"] - 1e-6:
        out.append(_befund(HUELLE, f"Hüllkreis Ø {_z(hk)} mm kleiner als die Maschine spannt "
                           f"(min. {_z(g['min_hk'])} mm)", None, hk, g["min_hk"]))
    if len(out) > MAX_BEFUNDE:
        rest = len(out) - MAX_BEFUNDE
        out = out[:MAX_BEFUNDE] + [dict(regel="mehr", text=f"… und {rest} weitere Befunde")]
    return out


def huellkreis(m):
    """Hüllkreis-Ø des Profils aus der Messung [mm] oder None (wie stammdaten.huellkreis)."""
    from .stammdaten import huellkreis as hk
    a, b = _f(m.get("abm_a")), _f(m.get("abm_b"))
    if a <= 0:
        return None
    try:
        return hk(dict(form=m.get("profilform"), a=a, b=b if b > 0 else None, wand=_f(m.get("wandstaerke")) or None))
    except Exception:       # noqa: BLE001
        return None


def markieren(messwerte, maschine=None):
    """Alle Teile prüfen und das Ergebnis in m["_fertigbarkeit"] merken (leere Liste = fertigbar)."""
    for m in messwerte or ():
        try:
            m["_fertigbarkeit"] = pruefen(m, maschine)
        except Exception as e:     # noqa: BLE001 – Prüfung ist Zusatz, darf den Import nie stören
            m["_fertigbarkeit"] = [dict(regel="fehler", text=f"Fertigbarkeit nicht geprüft: {e}")]
    return messwerte


def gruende(m, n=3):
    """Gründe für die Ampel (höchstens n Texte, Rest als Zahl)."""
    liste = [b.get("text") for b in (m.get("_fertigbarkeit") or ()) if b.get("text")]
    if not liste:
        return []
    kurz = liste[:n]
    if len(liste) > n:
        kurz.append(f"{len(liste) - n} weitere")
    return ["Fertigbarkeit: " + "; ".join(kurz)]
