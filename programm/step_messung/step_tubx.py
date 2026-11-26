"""TUBX (TRUMPF TubeCAM) wie eine STEP-Datei messen (Patrick 20.11.2026: „daraus errechnen wie eine step sollst du
tubex nutzen“).

Die TUBX ist ein ZIP. Task3D/Workpiece<Name>.bson enthält das Teil als Dreiecksnetz (VerticesOfTriangleMesh: je
Dreieck drei eigene Punkte, MeshIndices), Task3D/contour/Contour<Name>.opcContour (wieder ein ZIP mit
ContourData.json) die exakten Modellkanten (Linien, Bögen, Kreise, elliptische Bögen).

Aus dem Netz wird ein Volumenkörper genäht; ebene Dreiecke derselben Fläche werden zu einer Fläche zusammengefasst
(ShapeUpgrade_UnifySameDomain). Bohrungen wären danach Vielecke: jede Bohrung (zwei Kreise gleichen Radius auf einer
Achse, Außen- und Innenwand) wird darum erst mit einem etwas größeren Zylinder gefüllt und dann mit dem exakten
Zylinder neu gebohrt. So erkennt die Messung Bohrungen, Gewinde-Vorschläge und Konturklassen wie bei einer STEP.
Rundungen (Eckenradien, Rundrohre) bleiben Vielecke aus ebenen Streifen. Ergebnis wie step_geometrie.lies_step_info."""
import io
import json
import math
import re
import struct
import zipfile
from pathlib import Path

ENDUNG = ".tubx"
NAEH_TOL = 1e-3          # Nähen der Dreiecke [mm]
FUELL = 0.3              # Füllzylinder um so viel größer als die Bohrung [mm]
PAAR_ABSTAND = 30.0      # größter Abstand der beiden Kreise einer Bohrung (Wandstärke) [mm]
_NETZ = ("VerticesOfTriangleMesh", "MeshIndices")


def ist_tubx(pfad):
    return Path(str(pfad)).suffix.lower() == ENDUNG


def _bson(b, i=0, nur=None):
    """Kleiner BSON-Leser; Arrays von Zahlen (das Netz) direkt als Liste."""
    n = struct.unpack_from("<i", b, i)[0]
    ende, i, out = i + n - 1, i + 4, {}
    while i < ende:
        art = b[i]
        j = b.index(b"\x00", i + 1)
        key = b[i + 1:j].decode("utf-8", "replace")
        i = j + 1
        if art == 0x01:
            out[key] = struct.unpack_from("<d", b, i)[0]
            i += 8
        elif art in (0x02, 0x0D, 0x0E):
            ln = struct.unpack_from("<i", b, i)[0]
            out[key] = b[i + 4:i + 3 + ln].decode("utf-8", "replace")
            i += 4 + ln
        elif art == 0x03:
            ln = struct.unpack_from("<i", b, i)[0]
            out[key] = _bson(b, i)
            i += ln
        elif art == 0x04:
            ln = struct.unpack_from("<i", b, i)[0]
            out[key] = list(_bson(b, i).values())
            i += ln
        elif art == 0x05:
            ln = struct.unpack_from("<i", b, i)[0]
            i += 5 + ln
        elif art == 0x07:
            i += 12
        elif art == 0x08:
            out[key] = bool(b[i])
            i += 1
        elif art in (0x09, 0x11, 0x12):
            out[key] = struct.unpack_from("<q", b, i)[0]
            i += 8
        elif art == 0x10:
            out[key] = struct.unpack_from("<i", b, i)[0]
            i += 4
        elif art == 0x13:
            i += 16
        elif art in (0x0A, 0x06, 0xFF, 0x7F):
            out[key] = None
        else:
            break
    return out


def _netz_suchen(d):
    if isinstance(d, dict):
        if all(k in d for k in _NETZ):
            return d
        d = list(d.values())
    if isinstance(d, list):
        for v in d:
            if isinstance(v, (dict, list)):
                w = _netz_suchen(v)
                if w is not None:
                    return w
    return None


def inhalt(pfad):
    """[(Name, Punkte [(x,y,z)], Indizes, Kreise [dict(c, n, r)])] je Werkstück der TUBX."""
    try:
        z = zipfile.ZipFile(pfad)
    except (OSError, zipfile.BadZipFile) as e:
        raise ValueError(f"TUBX-Datei nicht lesbar (kein ZIP oder beschädigt): {e}") from e
    out = []
    with z:
        namen = z.namelist()
        for n in namen:
            m = re.search(r"Task3D/Workpiece([^/]*)\.bson$", n)
            if not m:
                continue
            netz = _netz_suchen(_bson(z.read(n)))
            if netz is None:
                continue
            v, ix = netz["VerticesOfTriangleMesh"], netz["MeshIndices"]
            punkte = [(v[3 * k], v[3 * k + 1], v[3 * k + 2]) for k in range(len(v) // 3)]
            kreise = []
            kont = next((k for k in namen if re.search(rf"Task3D/contour/Contour{re.escape(m.group(1))}\.opcContour$",
                                                         k)), None)
            if kont:
                try:
                    with zipfile.ZipFile(io.BytesIO(z.read(kont))) as kz:
                        daten = json.loads(kz.read("ContourData.json").decode("utf-8-sig"))
                    for e in daten["EntityContainer"]["Entities"].values():
                        s = e.get("Segment") or {}
                        if s.get("EntityType") == "Circle":
                            c = s["Center"]
                            kreise.append(dict(c=(c["X"], c["Y"], c["Z"]), r=s["Radius"],
                                               n=(s["NormalDirectionX"], s["NormalDirectionY"],
                                                  s["NormalDirectionZ"])))
                except (KeyError, ValueError, zipfile.BadZipFile):
                    kreise = []
            out.append((m.group(1) or Path(pfad).stem, punkte, list(ix), kreise))
    if not out:
        raise ValueError("TUBX-Datei ohne 3D-Modell (Task3D/Workpiece*.bson fehlt)")
    return out


def bohrungen(kreise):
    """Bohrungen aus den Modellkreisen: [(Mittelpunkt Kreis 1, Richtung zu Kreis 2 (Einheitsvektor), Abstand, r)].
    Zwei Kreise gleichen Radius, deren Verbindung parallel zur Kreisnormalen ist, sind Außen- und Innenrand."""
    frei, out = list(kreise), []
    while frei:
        a = frei.pop()
        best = None
        for b in frei:
            if abs(b["r"] - a["r"]) > 1e-3:
                continue
            d = [q - p for p, q in zip(a["c"], b["c"])]
            lg = math.sqrt(sum(x * x for x in d))
            if lg < 1e-6 or lg > PAAR_ABSTAND:
                continue
            n = a["n"]
            kreuz = (d[1] * n[2] - d[2] * n[1], d[2] * n[0] - d[0] * n[2], d[0] * n[1] - d[1] * n[0])
            if math.sqrt(sum(x * x for x in kreuz)) / lg < 1e-3 and (best is None or lg < best[1]):
                best = (b, lg, d)
        if best:
            frei.remove(best[0])
            out.append((a["c"], tuple(x / best[1] for x in best[2]), best[1], a["r"]))
    return out


def koerper_bauen(punkte, ix, kreise):
    """Volumenkörper aus dem Netz, Bohrungen exakt. Ergebnis: (Art, Shape)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeSolid,
                                    BRepBuilderAPI_Sewing)
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.TopAbs import TopAbs_SHELL, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    try:
        from OCP.TopTools import TopTools_ListOfShape
    except ImportError:         # neuere OCP-Versionen
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape

    def gleich(p):
        return tuple(round(c, 4) for c in p)
    naht = BRepBuilderAPI_Sewing(NAEH_TOL)
    n = 0
    for k in range(0, len(ix) - 2, 3):
        a, b, c = punkte[ix[k]], punkte[ix[k + 1]], punkte[ix[k + 2]]
        if len({gleich(a), gleich(b), gleich(c)}) < 3:
            continue
        poly = BRepBuilderAPI_MakePolygon(gp_Pnt(*a), gp_Pnt(*b), gp_Pnt(*c), True)
        f = BRepBuilderAPI_MakeFace(poly.Wire(), True)
        if f.IsDone():
            naht.Add(f.Face())
            n += 1
    if not n:
        raise ValueError("TUBX: 3D-Modell ohne Dreiecke")
    naht.Perform()
    genaeht = naht.SewedShape()
    ms = BRepBuilderAPI_MakeSolid()
    ex = TopExp_Explorer(genaeht, TopAbs_SHELL)
    schalen = 0
    while ex.More():
        ms.Add(TopoDS.Shell(ex.Current()))
        schalen += 1
        ex.Next()
    if not schalen:
        return "Flächenmodell offen", genaeht
    form = ms.Solid()
    u = ShapeUpgrade_UnifySameDomain(form, True, True, False)
    u.Build()
    form = u.Shape()
    paare = bohrungen(kreise)
    if paare:
        try:
            fuell, bohr = TopTools_ListOfShape(), TopTools_ListOfShape()
            for c, d, lg, r in paare:
                fuell.Append(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*c), gp_Dir(*d)), r + FUELL, lg).Shape())
                p0 = gp_Pnt(*(x - 0.5 * dx for x, dx in zip(c, d)))
                bohr.Append(BRepPrimAPI_MakeCylinder(gp_Ax2(p0, gp_Dir(*d)), r, lg + 1.0).Shape())
            arg = TopTools_ListOfShape()
            arg.Append(form)
            fu = BRepAlgoAPI_Fuse()
            fu.SetArguments(arg)
            fu.SetTools(fuell)
            fu.Build()
            u = ShapeUpgrade_UnifySameDomain(fu.Shape(), True, True, False)
            u.Build()
            arg = TopTools_ListOfShape()
            arg.Append(u.Shape())
            ct = BRepAlgoAPI_Cut()
            ct.SetArguments(arg)
            ct.SetTools(bohr)
            ct.Build()
            if ct.IsDone():
                u = ShapeUpgrade_UnifySameDomain(ct.Shape(), True, True, False)
                u.Build()
                neu = u.Shape()
                ex = TopExp_Explorer(neu, TopAbs_SOLID)
                if ex.More():
                    form = TopoDS.Solid(ex.Current())
        except Exception:       # noqa: BLE001 – Bohrungen sind Verbesserung: ohne sie wie das Netz messen
            pass
    if form.ShapeType() != TopAbs_SOLID:
        ex = TopExp_Explorer(form, TopAbs_SOLID)
        form = TopoDS.Solid(ex.Current()) if ex.More() else form
    return "aus TUBX-Netz", form


def lies_tubx_info(pfad):
    """TUBX lesen: (Körper, Info) wie step_geometrie.lies_step_info. Liegt eine gleichnamige LST mit genau einem Teil
    daneben, wird das Teil aus ihrem Schneidweg gebaut (exakt, step_lst); sonst aus dem Netz."""
    try:
        import step_lst
        lst = step_lst.lst_daneben(pfad)
        if lst is not None:
            koerper, info = step_lst.lies_lst_info(lst)
            if info.pop("abfall_offen", 0):
                # Öffnung der LST nicht vollständig gebaut (Kerbe über drei Seiten): das Netz der TUBX ist für dieses
                # Teil genauer (Importengine 2.0, 10186133 P10: LST +1,4 % Volumen, Netz wie STEP)
                raise ValueError("Öffnung über mehr als die halbe Rohrseite nicht aus dem Schneidweg baubar")
            if len(koerper) == 1:
                info["meldungen"].insert(0, f"aus der LST daneben ({Path(str(lst)).name}), genauer als das Netz der TUBX")
                return koerper, info
    except (ValueError, OSError) as e:
        meld_lst = f"LST daneben nicht nutzbar ({e}), Netz der TUBX gemessen"
    else:
        meld_lst = None
    teile = inhalt(pfad)
    koerper, meldungen = [], []
    for name, punkte, ix, kreise in teile:
        art, form = koerper_bauen(punkte, ix, kreise)
        if art == "Flächenmodell offen":
            meldungen.append(f"{name}: 3D-Modell nicht geschlossen")
        koerper.append(("Volumenkörper" if art != "Flächenmodell offen" else art, form))
    meldungen.append("aus TUBX (TubeCAM): Dreiecksnetz, Bohrungen aus den Modellkreisen exakt, Rundungen als Vieleck")
    if meld_lst:
        meldungen.append(meld_lst)
    return koerper, dict(einheit="mm", meldungen=meldungen, baugruppe=len(koerper) > 1, struktur=None, bauteile={})
