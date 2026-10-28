"""Rahmen-Assistent (Plan „Baugruppen automatisch“ A8, Patrick 25.10.2026 „Alle a“, 6a): Rechteckrahmen oder Quader
aus Quadrat-, Rechteck- oder Rundrohr ohne STEP-Datei. Aus Außenmaß B × H (× T), Profil und Eckart entstehen die
Rohre mit Länge und Enden, ihre Einbaulage (wie aus dem STEP-Import: Netz mit 'lagen' und 'koerper') und die Stöße
(Rohrende an Rohrwand), damit Satz in 3D, Steckverbindungen, Vorschläge und Montagefolge wie bei einer STEP-Datei
arbeiten.

Lage: Rahmen in der Ebene X (Breite B) / Z (Höhe H), Tiefe T längs Y. Gehrung: alle vier Rohre mit 45°-Gehrung, außen
gemessen B bzw. H. Stumpf: die Waagrechten laufen durch (Länge B), die Senkrechten stehen dazwischen (Quadrat- und
Rechteckrohr H − 2 × Profilhöhe, Rundrohr Mitte zu Mitte H − Ø mit Sattel). Quader: zwei Rahmen (stumpf) vorne und
hinten, vier Querrohre längs Y an den Ecken stoßen stumpf an die Waagrechten. Rechteckrohr: Maß b in der Rahmenebene,
hochkant = Maß a."""
import json
import math

from . import skizze as sk

RAHMEN, QUADER = "Rechteckrahmen", "Quader"
FORMEN = (RAHMEN, QUADER)
GEHRUNG, STUMPF, STECKEN = "Gehrung", "stumpf", "stumpf mit Steckverbindungen"
KNICK = "Knickrahmen (ein Rohr, geknickt)"     # Patrick 26.10.2026: wie Gehrung, danach Knickrahmen erstellen
ECKEN = (GEHRUNG, KNICK, STUMPF, STECKEN)
PROFILE = ("Quadratrohr", "Rechteckrohr", "Rundrohr")


def _kreuz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _skalar(a, b):
    return sum(x * y for x, y in zip(a, b, strict=False))


def _lage(o, z, x):
    return [round(c, 6) for c in tuple(o) + tuple(z) + tuple(x)]


def masse(profil, hochkant=False):
    """(Profilmaß in der Rahmenebene, Profilmaß in der Tiefe, rund) aus dem Profil; ValueError bei falschem Profil."""
    if (profil or {}).get("form") not in PROFILE:
        raise ValueError("Rahmen-Assistent: Quadrat-, Rechteck- oder Rundrohr wählen.")
    qs = sk.Querschnitt(profil)
    if qs.r:
        return 2 * qs.r, 2 * qs.r, True
    if not qs.B or not qs.H:
        raise ValueError("Rahmen-Assistent: Profilmaße fehlen.")
    return (qs.B, qs.H, False) if hochkant else (qs.H, qs.B, False)


def _achsen(z, aussen, rund, hochkant):
    """X-Achse des Rohrsystems zur Rohrachse z: Seite oben (Y) bzw. bei hochkant vorne (−X) zeigt nach außen;
    Rundrohr: X so, dass ein Sattel auf einem Rohr längs Welt-X bzw. -Y waagrecht liegt."""
    if rund:
        return (1.0, 0.0, 0.0) if abs(z[0]) < 0.5 else (0.0, 1.0, 0.0)
    if hochkant:
        return tuple(-c for c in aussen)
    return _kreuz(aussen, z)


def _winkel(lage, richtung):
    """Winkel [°] der Richtung (Welt) im System eines Rohrs: 0 = oben (Y), 90 = vorne (−X)."""
    z, x = lage[3:6], lage[6:9]
    y = _kreuz(z, x)
    v, u = _skalar(richtung, y), -_skalar(richtung, x)
    return round(math.degrees(math.atan2(u, v)) % 360, 1)


def bauen(profil, form, b, h, t=None, ecken=GEHRUNG, hochkant=False):
    """Rohre und Stöße: dict(teile = [dict(name, laenge, eingaben, lagen, koerper)], stoesse = [dict wie die
    STEP-Messung: aufnahme, stecker, ende, z, seite, winkel, achswinkel], stecken = True bei Steckverbindungen).
    Gleiche Rohre sind ein Teil mit mehreren Lagen. ValueError bei unmöglichen Maßen."""
    d, tief, rund = masse(profil, hochkant)
    b, h, t = float(b or 0), float(h or 0), float(t or 0)
    if form not in FORMEN or ecken not in ECKEN:
        raise ValueError("Rahmen-Assistent: Form und Ecken wählen.")
    if b <= 2 * d + 1 or h <= 2 * d + 1:
        raise ValueError(f"Rahmen-Assistent: Breite und Höhe müssen größer als 2 × {d:g} mm sein.")
    if ecken == KNICK and rund:
        raise ValueError("Rahmen-Assistent: Knickrahmen nur aus Quadrat- oder Rechteckrohr.")
    if form == QUADER:
        if ecken == KNICK:
            raise ValueError("Rahmen-Assistent: Knickrahmen nur als Rechteckrahmen.")
        if ecken == GEHRUNG:
            raise ValueError("Rahmen-Assistent: Quader nur mit stumpfen Ecken (Gehrung an drei Rohren je Ecke geht "
                             "nicht).")
        if t <= 2 * tief + 1:
            raise ValueError(f"Rahmen-Assistent: Tiefe muss größer als 2 × {tief:g} mm sein.")
    richtung = 90.0 if hochkant and not rund else 0.0
    koerper = []                # (Name, Länge, Eingaben, Lage)

    def rohr(name, laenge, enden, o, z, aussen, stecker=False):
        if stecker:     # gleiche Stecker gleich gedreht (Nasenwinkel gilt je Teil); 180° ändert den Querschnitt nicht
            aussen = tuple(abs(c) for c in aussen)
        x = _achsen(z, aussen, rund, hochkant)
        e = dict(a=dict(enden[0]), b=dict(enden[1]), konturen=[])
        koerper.append((name, round(laenge, 1), e, _lage(o, z, x)))
        return len(koerper)
    stoesse = []

    def stoss(auf, st, ende, punkt):
        la, ls = koerper[auf - 1][3], koerper[st - 1][3]
        z_auf = _skalar([punkt[i] - la[i] for i in range(3)], la[3:6])
        hin = ls[3:6] if ende == "a" else [-c for c in ls[3:6]]       # von der Aufnahme zum Stecker
        w = _winkel(la, hin)
        stoesse.append(dict(aufnahme=auf, stecker=st, ende=ende, z=round(z_auf, 3), winkel=w,
                            seite=f"{int(round(w / 90.0) * 90) % 360}°", achswinkel=90.0))
    gerade = ({}, {})
    if rund:
        sattel = ({"sattel": round(d, 3)}, {"sattel": round(d, 3)})
        senk_l, senk_z0 = h - d, d / 2
    else:
        sattel = gerade
        senk_l, senk_z0 = h - 2 * d, d
    gehrung = ({"winkel": 45.0, "richtung": richtung}, {"winkel": 45.0, "richtung": richtung})

    def rahmen(yc):
        """Ein Rahmen in der Ebene y = yc; Ergebnis {unten, oben, links, rechts: Körpernummer}."""
        k = {}
        if ecken in (GEHRUNG, KNICK):
            k["unten"] = rohr("Rahmen waagrecht", b, gehrung, (0, yc, d / 2), (1, 0, 0), (0, 0, -1))
            k["oben"] = rohr("Rahmen waagrecht", b, gehrung, (0, yc, h - d / 2), (1, 0, 0), (0, 0, 1))
            k["links"] = rohr("Rahmen senkrecht", h, gehrung, (d / 2, yc, 0), (0, 0, 1), (-1, 0, 0))
            k["rechts"] = rohr("Rahmen senkrecht", h, gehrung, (b - d / 2, yc, 0), (0, 0, 1), (1, 0, 0))
            return k
        k["unten"] = rohr("Rahmen waagrecht", b, gerade, (0, yc, d / 2), (1, 0, 0), (0, 0, -1))
        k["oben"] = rohr("Rahmen waagrecht", b, gerade, (0, yc, h - d / 2), (1, 0, 0), (0, 0, 1))
        for seite, x in (("links", d / 2), ("rechts", b - d / 2)):
            k[seite] = rohr("Rahmen senkrecht", senk_l, sattel, (x, yc, senk_z0), (0, 0, 1),
                            (-1 if seite == "links" else 1, 0, 0), stecker=True)
            stoss(k["unten"], k[seite], "a", (x, yc, d / 2))
            stoss(k["oben"], k[seite], "b", (x, yc, h - d / 2))
        return k
    if form == RAHMEN:
        rahmen(0.0)
    else:
        v = rahmen(tief / 2)
        hi = rahmen(t - tief / 2)
        quer_l = t - tief if rund else t - 2 * tief
        y0 = tief / 2 if rund else tief
        for unten in (True, False):
            for x in (tief / 2, b - tief / 2):      # außen bündig mit dem Rahmen
                zc = d / 2 if unten else h - d / 2
                n = rohr("Querrohr", quer_l, sattel, (x, y0, zc), (0, 1, 0), (0, 0, -1 if unten else 1),
                         stecker=True)
                stoss(v["unten" if unten else "oben"], n, "a", (x, tief / 2, zc))
                stoss(hi["unten" if unten else "oben"], n, "b", (x, t - tief / 2, zc))
    teile, schluessel = [], {}
    for nr, (name, laenge, e, lage) in enumerate(koerper, 1):
        k = (name, laenge, json.dumps(e, sort_keys=True))
        if k not in schluessel:
            schluessel[k] = len(teile)
            teile.append(dict(name=name, laenge=laenge, eingaben=e, lagen=[], koerper=[]))
        teile[schluessel[k]]["lagen"].append(lage)
        teile[schluessel[k]]["koerper"].append(nr)
    return dict(teile=teile, stoesse=stoesse, stecken=ecken == STECKEN, knick=ecken == KNICK)


def netz(teil, profil):
    """Netz der 3D-Ansicht für ein Teil wie aus dem STEP-Import (Rohr aus den Eingaben, Lagen, Körpernummern)."""
    from . import rohr3d
    n = rohr3d.netz(teil["eingaben"], profil, teil["laenge"]) or {}
    if n:
        n["lagen"] = teil["lagen"]
        n["koerper"] = teil["koerper"]
    return n


def vorschau(erg, profil):
    """Alle Rohre in Einbaulage als ein Netz für die 3D-Vorschau des Assistenten (gleiche Rohre in gleicher Farbe)
    oder None."""
    from .ansicht3d import baugruppe
    netze, farben = [], []
    for nr, t in enumerate(erg["teile"]):
        n = netz(t, profil)
        for lage in n.get("lagen") or ():
            netze.append(dict(n, lage=lage))
            farben.append(nr)
    return baugruppe(netze, (), farben)[0] if netze else None


def text(erg, profil_text=""):
    """Kurzer Überblick: ['2 × Rahmen waagrecht 1000 mm', …]."""
    from .rechnen import zahl
    return [f"{len(t['lagen'])} × {t['name']} {zahl(t['laenge'], 1)} mm" + (f" {profil_text}" if profil_text else "")
            for t in erg["teile"]]
