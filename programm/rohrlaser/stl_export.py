"""STL-Export des 3D-Modells aus dem Editor (Plan Paket K5).

Die STL enthält genau das Netz, das die 3D-Ansicht zeigt (Rohr aus den Eingaben oder aus der STEP, Blech gefaltet),
ohne Hilfskörper, Schnittkörper, Anbauteile und Linien. Maße in mm, Lage wie im Teil: beim Rohr X längs der
Rohrachse, beim Blech X/Y in der Abwicklung und Z nach oben. Für Kunden, 3D-Druck und Ansicht; für CAD bleibt
die STEP-Datei maßgeblich, weil STL nur Dreiecke kennt (Bögen sind darin Vielecke).
"""
import math
import struct

# Flächen der Ansicht (ansicht3d.ARTEN), die nicht zum gefertigten Teil gehören: Hilfskörper, Schnittkörper (W…),
# nicht gefertigte Ringe/Überstände, Nähte und Biegelinien
HILFE = ("HK", "EO", "UO", "SN", "SV", "SH", "SX", "NL", "B")


def _rohr(p):
    """Rohr: Ansicht (-u, v, x) -> Teil (x, u, v)."""
    return p[2], -p[0], p[1]


def _blech(p):
    """Blech: Ansicht (y, z, x) (blech3d._ansicht) -> Abwicklung (x, y, z)."""
    return p[2], p[0], p[1]


def _gleich(p):
    return p[0], p[1], p[2]


def teil_art(a, art):
    """Gehört die Fläche a der Ansicht zur STL? Einzelteile ohne Anbauteile, Baugruppen mit allen Teilen."""
    if a in HILFE or a.startswith("W"):
        return False
    return art == "datei" or a != "AN"


def dreiecke(netz, art="rohr"):
    """[(a, b, c)] der Dreiecke des Teils, außen gegen den Uhrzeigersinn wie in der Ansicht. art: "rohr" (X längs
    der Achse), "blech" (Abwicklung X/Y, Z oben) oder "datei" (Baugruppe/Satz: Einbaulage wie in der Ansicht)."""
    if not netz or not netz.get("p"):
        return []
    p = netz["p"]
    um = {"rohr": _rohr, "blech": _blech}.get(art, _gleich)
    spiegeln = art == "rohr"        # (x, u, v) aus (-u, v, x) ist gespiegelt: Reihenfolge der Ecken tauschen
    out = []
    for a, idx in (netz.get("t") or {}).items():
        if not teil_art(a, art):
            continue
        for i in range(0, len(idx) - 2, 3):
            ecken = [um(p[3 * k:3 * k + 3]) for k in idx[i:i + 3]]
            if spiegeln:
                ecken = [ecken[0], ecken[2], ecken[1]]
            out.append(tuple(tuple(float(x) for x in q) for q in ecken))
    return out


def _normale(a, b, c):
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    lg = math.sqrt(sum(x * x for x in n))
    return tuple(x / lg for x in n) if lg > 1e-15 else (0.0, 0.0, 0.0)


def daten(tri, name=""):
    """Binäre STL (bytes) aus Dreiecken; flache Dreiecke ohne Fläche fallen weg."""
    gut = [t for t in tri if _normale(*t) != (0.0, 0.0, 0.0)]
    kopf = ("Rohrlaser-Kalkulation " + str(name or "")).encode("ascii", "replace")[:80].ljust(80, b" ")
    teile = [kopf, struct.pack("<I", len(gut))]
    for t in gut:
        teile.append(struct.pack("<12fH", *_normale(*t), *t[0], *t[1], *t[2], 0))
    return b"".join(teile)


def lesen(roh):
    """Dreiecke aus einer binären STL (für Tests und Gegenprobe)."""
    n = struct.unpack_from("<I", roh, 80)[0]
    out = []
    for i in range(n):
        w = struct.unpack_from("<12f", roh, 84 + 50 * i)
        out.append((w[3:6], w[6:9], w[9:12]))
    return out


def volumen(tri):
    """Eingeschlossenes Volumen [mm³] (Divergenzsatz); bei geschlossenem, richtig orientiertem Netz positiv."""
    v = 0.0
    for a, b, c in tri:
        v += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
              + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    return v


def speichern(pfad, netz, art="rohr", name=""):
    """STL schreiben; Ergebnis: Zahl der Dreiecke (0 = nichts geschrieben)."""
    tri = dreiecke(netz, art)
    if not tri:
        return 0
    roh = daten(tri, name)
    with open(pfad, "wb") as f:
        f.write(roh)
    return struct.unpack_from("<I", roh, 80)[0]
