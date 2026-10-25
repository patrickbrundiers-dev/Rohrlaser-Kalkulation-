"""STEP-Export (Plan 3D-Editor 3E-8, Patrick 24.10.2026): baut aus einem Bauplan (JSON, programm/rohrlaser/
step_export.py) echte Volumenkörper mit OpenCascade und schreibt sie als STEP (AP214, mm).

Wie die Messung läuft das als eigener Prozess (STEP-Import.exe --export …): OpenCascade bleibt aus dem Programm
heraus. Der Bauplan beschreibt je Teil einen Grundkörper mit echten Radien und Bögen und die Werkzeuge, die
abgezogen werden:

- Grundkörper 'rohr': Querschnitt (Kreis oder Eckpunkte mit Bulge = Bogen zum nächsten Punkt) außen und innen,
  entlang Z von 0 bis laenge. 'platte': Außenkontur mit Löchern, entlang Z um die Dicke.
- Werkzeuge: 'ebene' (Halbraum auf der Seite der Normalen), 'zylinder' (Bohrung), 'quader' (Gravurrille),
  'prisma' (Vieleck in XY entlang Z), 'flach' (Kontur mit Bögen auf einer ebenen Wand, senkrecht hindurch), 'netz' (geschlossenes Dreiecksnetz, z. B. Schnitt eines Endes, Ausklinkung).
  Jedes Werkzeug kann 'ohne': [Werkzeuge] haben, die vorher von ihm abgezogen werden (Nasen einer Steckverbindung
  bleiben stehen).

Aufruf:
    STEP-Import.exe --export BAUPLAN.json --step ZIEL.step [--ergebnis ERGEBNIS.json]
    python step_schreiben.py BAUPLAN.json ZIEL.step [ERGEBNIS.json]

ERGEBNIS.json: {"ok": true/false, "teile": [{"name", "gueltig", "volumen", "flaechen", "meldungen"}], "fehler"}.
Rückgabewert 0 = geschrieben, 1 = Fehler.
"""
import json
import math
import sys
from pathlib import Path

GROSS = 1.0e5           # halbe Kantenlänge der Ebene für den Halbraum [mm]
NAEHEN_TOL = 1e-4       # Toleranz beim Nähen der Dreiecksnetze [mm]


def _pnt(p):
    from OCP.gp import gp_Pnt
    return gp_Pnt(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0)


def _dir(v):
    from OCP.gp import gp_Dir
    return gp_Dir(float(v[0]), float(v[1]), float(v[2]))


def _kante(a, b, bulge, z):
    """Kante von a nach b in der Ebene z: Gerade oder Kreisbogen (Bulge = tan(Öffnungswinkel / 4), + = gegen den
    Uhrzeigersinn)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.GC import GC_MakeArcOfCircle
    if abs(bulge) < 1e-9:
        return BRepBuilderAPI_MakeEdge(_pnt((a[0], a[1], z)), _pnt((b[0], b[1], z))).Edge()
    th = 4 * math.atan(bulge)
    c = math.dist(a, b)
    r = c / (2 * math.sin(abs(th) / 2))
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    nx, ny = -(b[1] - a[1]) / c, (b[0] - a[0]) / c          # links von a -> b
    s = 1 if th > 0 else -1
    d = r * math.cos(th / 2)
    cx, cy = mx + nx * d * s, my + ny * d * s
    w = math.atan2(a[1] - cy, a[0] - cx) + th / 2           # Mitte des Bogens
    m = (cx + r * math.cos(w), cy + r * math.sin(w), z)
    bogen = GC_MakeArcOfCircle(_pnt((a[0], a[1], z)), _pnt(m), _pnt((b[0], b[1], z))).Value()
    return BRepBuilderAPI_MakeEdge(bogen).Edge()


def draht(kontur, z=0.0):
    """Geschlossener Draht aus {"kreis": [cx, cy, r]} oder {"punkte": [[x, y, bulge], …]}."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.gp import gp_Ax2, gp_Circ
    if kontur.get("kreis"):
        cx, cy, r = kontur["kreis"]
        kreis = gp_Circ(gp_Ax2(_pnt((cx, cy, z)), _dir((0, 0, 1))), float(r))
        return BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(kreis).Edge()).Wire()
    pk = [(float(p[0]), float(p[1]), float(p[2]) if len(p) > 2 else 0.0) for p in kontur["punkte"]]
    pk = [p for i, p in enumerate(pk) if math.dist(p[:2], pk[i - 1][:2]) > 1e-7]     # doppelte Punkte weg
    w = BRepBuilderAPI_MakeWire()
    for i, a in enumerate(pk):
        b = pk[(i + 1) % len(pk)]
        w.Add(_kante(a[:2], b[:2], a[2], z))
    if not w.IsDone():
        raise ValueError("Kontur nicht geschlossen")
    return w.Wire()


def flaeche(aussen, loecher=(), z=0.0):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    mf = BRepBuilderAPI_MakeFace(draht(aussen, z), True)
    for k in loecher:
        w = draht(k, z)
        w.Reverse()
        mf.Add(w)
    if not mf.IsDone():
        raise ValueError("Fläche nicht erzeugt")
    from OCP.ShapeFix import ShapeFix_Face
    fix = ShapeFix_Face(mf.Face())
    fix.Perform()                   # Löcher richtig herum
    return fix.Face()


def _prisma(f, h, richtung=(0, 0, 1)):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    from OCP.gp import gp_Vec
    return BRepPrimAPI_MakePrism(f, gp_Vec(*(float(c) * h for c in richtung))).Shape()


def grundkoerper(k):
    if k["art"] == "rohr":
        f = flaeche(k["aussen"], [k["innen"]] if k.get("innen") else [])
        return _prisma(f, float(k["laenge"]))
    if k["art"] == "platte":
        f = flaeche(k["aussen"], k.get("loecher") or [])
        return _prisma(f, float(k["dicke"]))
    raise ValueError(f"Grundkörper {k['art']!r} unbekannt")


def netz_koerper(p, t):
    """Geschlossenes Dreiecksnetz (Punkte flach x, y, z …, Dreiecke i, j, k …) als Volumenkörper."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeSolid
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    pts = [_pnt(p[i:i + 3]) for i in range(0, len(p), 3)]
    naehen = BRepBuilderAPI_Sewing(NAEHEN_TOL)
    n = 0
    for i in range(0, len(t), 3):
        a, b, c = pts[t[i]], pts[t[i + 1]], pts[t[i + 2]]
        if a.Distance(b) < 1e-7 or b.Distance(c) < 1e-7 or a.Distance(c) < 1e-7:
            continue
        poly = BRepBuilderAPI_MakePolygon(a, b, c, True)
        mf = BRepBuilderAPI_MakeFace(poly.Wire(), True)
        if mf.IsDone():
            naehen.Add(mf.Face())
            n += 1
    if not n:
        raise ValueError("leeres Netz")
    naehen.Perform()
    genaeht = naehen.SewedShape()
    ex = TopExp_Explorer(genaeht, TopAbs_SHELL)
    if not ex.More():
        raise ValueError("Netz nicht geschlossen")
    ms = BRepBuilderAPI_MakeSolid()
    while ex.More():
        ms.Add(TopoDS.Shell(ex.Current()))
        ex.Next()
    fix = ShapeFix_Solid(ms.Solid())
    fix.Perform()
    k = fix.Solid()
    if _volumen(k) < 0:             # Dreiecke andersherum: Körper umdrehen
        k = TopoDS.Solid(k.Reversed())
    return k


def _volumen(k):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(k, g)
    return g.Mass()


def werkzeug(w):
    """Werkzeug als Körper (siehe Kopf)."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeHalfSpace
    from OCP.gp import gp_Ax2, gp_Pln
    art = w["art"]
    if art == "ebene":
        from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
        pln = gp_Pln(_pnt(w["p"]), _dir(w["n"]))
        f = BRepBuilderAPI_MakeFace(pln, -GROSS, GROSS, -GROSS, GROSS).Face()
        ref = [w["p"][i] + w["n"][i] for i in range(3)]
        k = BRepPrimAPI_MakeHalfSpace(f, _pnt(ref)).Solid()
    elif art == "zylinder":
        k = BRepPrimAPI_MakeCylinder(gp_Ax2(_pnt(w["p"]), _dir(w["achse"])), float(w["r"]), float(w["h"])).Shape()
    elif art == "quader":
        k = BRepPrimAPI_MakeBox(gp_Ax2(_pnt(w["p"]), _dir(w["z"]), _dir(w["x"])), float(w["l"]), float(w["b"]),
                                float(w["h"])).Shape()
    elif art == "prisma":
        f = flaeche({"punkte": w["punkte"]}, z=float(w["z0"]))
        k = _prisma(f, float(w["z1"]) - float(w["z0"]))
    elif art == "netz":
        k = netz_koerper(w["p"], w["t"])
    elif art == "flach":            # Kontur in der Ebene (o, Normale n, Richtung x), entlang −n um h
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Ax3, gp_Trsf
        tr = gp_Trsf()
        tr.SetDisplacement(gp_Ax3(), gp_Ax3(_pnt(w["o"]), _dir(w["n"]), _dir(w["x"])))
        f = BRepBuilderAPI_Transform(flaeche(w["kontur"]), tr, True).Shape()
        k = _prisma(f, -float(w["h"]), w["n"])
    else:
        raise ValueError(f"Werkzeug {art!r} unbekannt")
    if w.get("ohne"):
        k = abziehen(k, [werkzeug(x) for x in w["ohne"]])
    return k


def abziehen(k, werkzeuge):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    try:  # OCP >= 7.8
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
    except ImportError:
        from OCP.TopTools import TopTools_ListOfShape
    if not werkzeuge:
        return k
    arg, wz = TopTools_ListOfShape(), TopTools_ListOfShape()
    arg.Append(k)
    for w in werkzeuge:
        wz.Append(w)
    cut = BRepAlgoAPI_Cut()
    cut.SetArguments(arg)
    cut.SetTools(wz)
    cut.SetRunParallel(True)
    cut.Build()
    if not cut.IsDone():
        raise ValueError("Boolesche Operation fehlgeschlagen")
    return cut.Shape()


def vereinfachen(k):
    """Gleiche Flächen zusammenlegen (ebene Dreiecke eines Werkzeugs werden eine Fläche)."""
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    u = ShapeUpgrade_UnifySameDomain(k, True, True, True)
    u.Build()
    return u.Shape()


def _kennwerte(k):
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(k, g)

    def anzahl(typ):
        ex, n = TopExp_Explorer(k, typ), 0
        while ex.More():
            n += 1
            ex.Next()
        return n
    return dict(gueltig=bool(BRepCheck_Analyzer(k).IsValid()), volumen=round(g.Mass(), 3),
                flaechen=anzahl(TopAbs_FACE), koerper=anzahl(TopAbs_SOLID))


def teil_bauen(teil):
    """Körper eines Teils und Meldungen."""
    meldungen = []
    k = grundkoerper(teil["koerper"])
    wz = []
    for w in teil.get("werkzeuge") or ():
        try:
            wz.append(werkzeug(w))
        except Exception as ex:             # ein Werkzeug fehlt: Teil trotzdem schreiben, mit Meldung
            meldungen.append(f"{w.get('name') or w['art']}: nicht erzeugt ({ex})")
    for w in wz:                    # einzeln: überlappende Werkzeuge (Stücke einer Kontur, Enden) sicher
        k = abziehen(k, [w])
    rillen = []
    for w in teil.get("rillen") or ():
        try:
            rillen.append(werkzeug(w))
        except Exception:
            pass
    if rillen:
        k = abziehen(k, rillen)
    try:
        k = vereinfachen(k)
    except Exception as ex:
        meldungen.append(f"Flächen nicht zusammengelegt ({ex})")
    if teil.get("lage"):
        from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCP.gp import gp_Trsf
        m = teil["lage"]                    # 3 × 4 Matrix zeilenweise
        tr = gp_Trsf()
        tr.SetValues(*[float(x) for x in m])
        k = BRepBuilderAPI_Transform(k, tr, True).Shape()
    return k, meldungen


def schreiben(bauplan, ziel):
    """Alle Teile bauen und als STEP schreiben -> Ergebnis (dict)."""
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    werkzeug_formen = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    teile = []
    for teil in bauplan.get("teile") or ():
        k, meldungen = teil_bauen(teil)
        lab = werkzeug_formen.AddShape(k, False)
        TDataStd_Name.Set_s(lab, TCollection_ExtendedString(str(teil.get("name") or "Teil")))
        teile.append(dict(name=teil.get("name"), meldungen=meldungen, **_kennwerte(k)))
    if not teile:
        raise ValueError("keine Teile im Bauplan")
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    Interface_Static.SetCVal_s("write.step.unit", "MM")
    Interface_Static.SetCVal_s("write.step.product.name", str(bauplan.get("name") or teile[0]["name"] or "Teil"))
    w = STEPCAFControl_Writer()
    w.SetNameMode(True)
    if not w.Transfer(doc, STEPControl_AsIs):
        raise ValueError("Übertragung nach STEP fehlgeschlagen")
    if w.Write(str(ziel)) != IFSelect_RetDone:
        raise ValueError(f"STEP-Datei nicht geschrieben: {ziel}")
    return dict(ok=all(t["gueltig"] for t in teile), teile=teile)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--export":          # STEP-Import.exe --export BAUPLAN --step ZIEL [--ergebnis E]
        werte = dict(zip(argv[::2], argv[1::2]))
        plan, ziel, erg_pfad = werte.get("--export"), werte.get("--step"), werte.get("--ergebnis")
    else:
        plan, ziel, erg_pfad = (argv + [None, None, None])[:3]
    if not plan or not ziel:
        print(__doc__)
        return 2
    try:
        bauplan = json.loads(Path(plan).read_text(encoding="utf-8"))
        erg = schreiben(bauplan, ziel)
        code = 0
    except Exception as ex:
        erg, code = dict(ok=False, fehler=str(ex), teile=[]), 1
    text = json.dumps(erg, ensure_ascii=False)
    if erg_pfad:
        Path(erg_pfad).write_text(text, encoding="utf-8")
    print(text, flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
