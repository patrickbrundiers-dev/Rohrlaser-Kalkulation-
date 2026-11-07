"""Verschmolzene Teile aufteilen (Vorschlag N3, Patrick 07.11.2026): ein Körper, den die Messung als „mehrere Teile in
einem Körper“ gelb markiert (z. B. Platte mit angeschweißter Mutter), wird an erkennbaren Anbauten getrennt:

- Sechskant (Mutter, Schraubenkopf) um eine Zylinderachse: das Sechskantprisma zwischen den Enden der Schlüsselflächen,
- Kugel: die Kugel aus den Kugelflächen,
- Bolzen, Stehbolzen, Gewindestangen (Vorschlag M5): Zylinder aus den außen liegenden Zylinderflächen gleicher Achse und
  gleichen Halbmessers zwischen ihren Enden; sitzt er unter einem Sechskant, wird beides eine Schraube.

Anbau = Körper ∩ Form, Grundteil = Körper − Form. Jedes Teil wird eine eigene STEP-Datei in den Koordinaten der
Baugruppe (Lage bleibt, nichts wird verschoben) und dann ganz normal gemessen; die Mutter erkennt die Messung dann
als Normteil. Ohne erkennbaren Anbau: keine Teile (der Körper bleibt gelb).
"""
import math
from pathlib import Path

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeFace
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism, BRepPrimAPI_MakeSphere
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Vec
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopAbs import TopAbs_SOLID, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.BRep import BRep_Tool

import step_drehfraes as df

MIN_VOLUMEN = 1.0       # mm³: kleinere Reste der Trennung (Rundungsfehler) fallen weg
BOLZEN_MIN = 1.0        # mm: kürzere bzw. dünnere Zylinder sind keine Bolzen (Fasen, Rundungen)
ZUGABE = 0.01           # mm: Bolzenform etwas dicker als der Bolzen, damit keine Haut am Grundteil bleibt


def _volumen(s):
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(s, p)
    return p.Mass()


def _solids(s):
    out, ex = [], TopExp_Explorer(s, TopAbs_SOLID)
    while ex.More():
        k = TopoDS.Solid(ex.Current())
        ex.Next()
        if _volumen(k) > MIN_VOLUMEN:
            out.append(k)
    return out


def _punkte(face):
    out, ex = [], TopExp_Explorer(face, TopAbs_VERTEX)
    while ex.More():
        p = BRep_Tool.Pnt_s(TopoDS.Vertex(ex.Current()))
        out.append((p.X(), p.Y(), p.Z()))
        ex.Next()
    return out


def _sechskant_form(o, d, flaechen):
    """Prisma des Sechskants: Querschnitt aus den sechs Ebenen, Höhe zwischen den Enden der Schlüsselflächen."""
    n = math.sqrt(sum(x * x for x in d))
    d = tuple(x / n for x in d)
    pts = [p for e in flaechen for p in _punkte(e["face"])]
    t = [df._dot(df._sub(p, o), d) for p in pts]
    t0, t1 = min(t), max(t)
    if t1 - t0 < 1e-3:
        return None
    # Ecken: Schnitt benachbarter Ebenen (nach Winkel der Normalen um die Achse geordnet) in der Ebene bei t0
    u = df._sub(flaechen[0]["normale"], tuple(df._dot(flaechen[0]["normale"], d) * x for x in d))
    nu = math.sqrt(sum(x * x for x in u))
    u = tuple(x / nu for x in u)
    w = (d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0])
    linien = []
    for e in flaechen:
        nn = e["normale"]
        a, b = df._dot(nn, u), df._dot(nn, w)
        c = df._dot(df._sub(e["punkt"], o), nn)
        if c < 0:
            a, b, c = -a, -b, -c
        linien.append((math.atan2(b, a), a, b, c))
    linien.sort()
    ecken = []
    for i in range(6):
        _, a1, b1, c1 = linien[i]
        _, a2, b2, c2 = linien[(i + 1) % 6]
        det = a1 * b2 - a2 * b1
        if abs(det) < 1e-9:
            return None
        x, y = (c1 * b2 - c2 * b1) / det, (a1 * c2 - a2 * c1) / det
        ecken.append(tuple(o[k] + t0 * d[k] + x * u[k] + y * w[k] for k in range(3)))
    poly = BRepBuilderAPI_MakePolygon()
    for p in ecken:
        poly.Add(gp_Pnt(*p))
    poly.Close()
    flaeche = BRepBuilderAPI_MakeFace(poly.Wire()).Face()
    return BRepPrimAPI_MakePrism(flaeche, gp_Vec(*(x * (t1 - t0) for x in d))).Shape()


def _koaxial(a, b):
    (o1, d1), (o2, d2) = a, b
    if abs(abs(df._dot(d1, d2)) - 1) > 1e-6:
        return False
    w = df._sub(o2, o1)
    t = df._dot(w, d1)
    return sum((w[k] - t * d1[k]) ** 2 for k in range(3)) < 1e-6


def _zylinder_gruppen(fl):
    """Außen liegende Zylinderflächen, zusammengefasst nach Achse und Halbmesser: Liste dict(achse, radius, t0, t1)
    (t = Lage entlang der Achse ab dem Achspunkt)."""
    gruppen = []
    for e in fl:
        if e["typ"] != "zylinder" or not e.get("konvex") or e["radius"] < BOLZEN_MIN / 2:
            continue
        g = next((g for g in gruppen if abs(g["radius"] - e["radius"]) < 1e-3 and _koaxial(g["achse"], e["achse"])),
                 None)
        if g is None:
            g = dict(achse=e["achse"], radius=e["radius"], t=[])
            gruppen.append(g)
        o, d = g["achse"]
        g["t"] += [df._dot(df._sub(p, o), d) for p in _punkte(e["face"])]
        g.setdefault("faces", []).append(e["face"])
    for g in gruppen:
        g["t0"], g["t1"] = (min(g["t"]), max(g["t"])) if g["t"] else (0.0, 0.0)
    return [g for g in gruppen if g["t1"] - g["t0"] >= BOLZEN_MIN and _rundum(g["faces"])]


def _rundum(faces):
    """Die Zylinderflächen gehen zusammen einmal ganz herum (Bolzen), nicht nur ein Bogen (Rundung, Fase)."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    zwei_pi = 2 * math.pi
    bereiche = []
    for f in faces:
        s = BRepAdaptor_Surface(f)
        u0, u1 = s.FirstUParameter(), s.LastUParameter()
        if u1 - u0 >= zwei_pi * 0.98:
            return True
        u0 %= zwei_pi
        u1 = u0 + (s.LastUParameter() - s.FirstUParameter())
        bereiche += [(u0, min(u1, zwei_pi))] + ([(0.0, u1 - zwei_pi)] if u1 > zwei_pi else [])
    bereiche.sort()
    summe, ende = 0.0, 0.0
    for a, b in bereiche:
        if b > ende:
            summe += b - max(a, ende)
            ende = b
    return summe >= zwei_pi * 0.98


def bolzen(fl, volumen=None):
    """Bolzen am Körper (für die Erkennung „mehrere Teile in einem Körper“): Zylindergruppen rundum, ohne anderen
    Zylinder gleicher Achse und – mit volumen – kleiner als die Hälfte des Körpers."""
    gruppen = _zylinder_gruppen(fl)
    out = []
    for g in gruppen:
        if any(h is not g and _koaxial(h["achse"], g["achse"]) for h in gruppen):
            continue
        v = math.pi * g["radius"] ** 2 * (g["t1"] - g["t0"])
        if volumen is not None and v > 0.5 * volumen:
            continue
        out.append(g)
    return out


def _zylinder_form(g):
    o, d = g["achse"]
    p = tuple(o[k] + g["t0"] * d[k] for k in range(3))
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*p), gp_Dir(*d)), g["radius"] + ZUGABE, g["t1"] - g["t0"]).Shape()


def _mm(x):
    return f"{x:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def anbauten(solid):
    """Erkennbare Anbauten des Körpers: Liste (Name, Form) – Sechskante um Zylinderachsen, Kugeln."""
    fl = df.flaechen(solid)
    out, gesehen = [], []
    zylinder = _zylinder_gruppen(fl)
    benutzt = []                        # Zylinder, die schon zu einer Schraube gehören
    for z in (e for e in fl if e["typ"] == "zylinder"):
        o, d = z["achse"]
        kante, rest = df.sechskante(fl, o, d)
        if not kante or not rest:       # nur Sechskant = ganze Mutter/Schraube, nichts aufzuteilen
            continue
        for k in kante:
            schl = id(k["flaechen"][0]["face"].TShape())
            if schl in gesehen:
                continue
            gesehen.append(schl)
            form = _sechskant_form(o, d, k["flaechen"])
            if form is None:
                continue
            name = f"Mutter SW {k['schluessel']:g}".replace(".", ",")
            schaft = [g for g in zylinder if _koaxial(g["achse"], (o, d)) and g["radius"] < k["schluessel"] / 2
                      and id(g) not in benutzt]
            for g in schaft:            # Schraube: Kopf und Schaft bleiben ein Teil
                form = BRepAlgoAPI_Fuse(form, _zylinder_form(g)).Shape()
                benutzt.append(id(g))
                name = f"Schraube SW {k['schluessel']:g}".replace(".", ",")
            out.append((name, form))
    for g in zylinder:                  # M5: Bolzen, Stehbolzen, Gewindestangen
        if id(g) in benutzt:
            continue
        if any(h is not g and _koaxial(h["achse"], g["achse"]) for h in zylinder):
            continue                    # Absatz (Welle mit Bund): ein Drehteil, nicht trennen
        hohl = any(e["typ"] == "zylinder" and not e.get("konvex") and e["radius"] < g["radius"]
                   and _koaxial(e["achse"], g["achse"]) for e in fl)
        out.append((f"{'Rohr' if hohl else 'Bolzen'} Ø{_mm(2 * g['radius'])} × {_mm(g['t1'] - g['t0'])}",
                    _zylinder_form(g)))
    kugeln = [e for e in fl if e["typ"] == "kugel" and e.get("mitte")]
    if kugeln and len(kugeln) < len(fl):
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        mitten = []
        for e in kugeln:
            r = BRepAdaptor_Surface(e["face"]).Sphere().Radius()
            m = e["mitte"]
            if any(sum((a - b) ** 2 for a, b in zip(m, mm)) < 1e-4 and abs(r - rr) < 1e-3 for mm, rr in mitten):
                continue
            mitten.append((m, r))
            out.append((f"Kugel Ø{2 * r:.2f}".rstrip("0").rstrip(".").replace(".", ","),
                        BRepPrimAPI_MakeSphere(gp_Pnt(*m), r).Shape()))
    return out


def teilen(solid):
    """Körper an den Anbauten trennen: Liste (Name, Solid), Grundteil zuletzt; leer, wenn nichts zu trennen ist."""
    teile, rest = [], solid
    for name, form in anbauten(solid):
        anbau = _solids(BRepAlgoAPI_Common(rest, form).Shape())
        if not anbau:
            continue
        neu = BRepAlgoAPI_Cut(rest, form).Shape()
        if not _solids(neu):
            continue
        teile += [(name, a) for a in anbau]
        rest = neu
    if not teile:
        return []
    grund = _solids(rest)
    return teile + [("Grundteil" if len(grund) == 1 else f"Grundteil {i}", g) for i, g in enumerate(grund, start=1)]


def aufteilen(koerper, ordner, stamm, nr):
    """Körper (Shape mit Lage) trennen und jedes Teil als STEP-Datei in ordner schreiben ('<stamm>_K<nr>_T<i>.step').
    Ergebnis: Liste (Pfad, Name) in der Reihenfolge der Teile; leer, wenn nichts zu trennen ist."""
    out = []
    for i, (name, s) in enumerate(teilen(koerper), start=1):
        pfad = Path(ordner) / f"{stamm}_K{nr}_T{i}.step"
        w = STEPControl_Writer()
        w.Transfer(s, STEPControl_AsIs)
        if w.Write(str(pfad)) != IFSelect_RetDone:
            raise ValueError(f"Teil {i} nicht geschrieben")
        out.append((pfad, name))
    return out
