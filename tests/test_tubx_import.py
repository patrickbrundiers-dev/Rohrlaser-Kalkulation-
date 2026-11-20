"""TUBX (TRUMPF TubeCAM) wie eine STEP-Datei messen (Patrick 20.11.2026, step_messung/step_tubx.py):
- X1 Rechteckrohr 60×40×3 mit Bohrung Ø10 als TUBX (Dreiecksnetz + Modellkreise): gleiches Profil, gleiche Länge,
  Schneidweg und Konturen wie die STEP-Datei; die Bohrung ist ein exakter Zylinder (Ø10, nicht Vieleck)
- X2 ohne Modellkreise: Messung trotzdem (Bohrung nur als Kontur), kaputte TUBX: klare Meldung
- X3 Programm: .tubx gilt als CAD-Datei (Ablegen, Dateiauswahl, Ordner) wie .step/.igs
Synthetische Datei im Aufbau der echten TUBX (keine Kundendaten im Repo).

Aufruf: python tests/test_tubx_import.py
"""
import io
import json
import os
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from formen_baukasten import ohne, quader, schreibe, zyl  # noqa: E402
from step_geometrie import analysiere_datei  # noqa: E402

import step_tubx  # noqa: E402

fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            fehler += 1
            print(f"FEHLER {name}: {e}")
        return fn
    return deko


def bson(d):
    teil = b""
    for k, v in d.items():
        kb = k.encode() + b"\x00"
        if isinstance(v, float):
            teil += b"\x01" + kb + struct.pack("<d", v)
        elif isinstance(v, str):
            s_ = v.encode() + b"\x00"
            teil += b"\x02" + kb + struct.pack("<i", len(s_)) + s_
        elif isinstance(v, dict):
            teil += b"\x03" + kb + bson(v)
        elif isinstance(v, list):
            teil += b"\x04" + kb + bson({str(i): x for i, x in enumerate(v)})
        elif isinstance(v, int):
            teil += b"\x10" + kb + struct.pack("<i", v)
    return struct.pack("<i", len(teil) + 5) + teil + b"\x00"


def netz(form, fein=0.05):
    """Dreiecksnetz wie TubeCAM: je Dreieck drei eigene Punkte, nach außen orientiert."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    BRepMesh_IncrementalMesh(form, fein, False, 0.3, True)
    punkte = []
    ex = TopExp_Explorer(form, TopAbs_FACE)
    while ex.More():
        f = TopoDS.Face(ex.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        tr = loc.Transformation()
        for i in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(i).Get()
            if f.Orientation() == TopAbs_REVERSED:
                b, c = c, b
            for k in (a, b, c):
                p = tri.Node(k).Transformed(tr)
                punkte += [p.X(), p.Y(), p.Z()]
        ex.Next()
    return punkte


def tubx(form, name, kreise, ziel):
    punkte = netz(form)
    werkstueck = {"SerializationObjects": [{"T": "WorkpieceTube", "WorkpieceLength": 400.0,
                                            "VerticesOfTriangleMesh": punkte,
                                            "MeshIndices": list(range(len(punkte) // 3))},
                                           {"T": "TubeProfile", "ProfileId": "1_600X400X0_1_20"}]}
    ent = {f"Entity{i}": {"EntityTypeAsInt": 2, "Segment": {
        "EntityType": "Circle", "Radius": r, "Center": {"X": c[0], "Y": c[1], "Z": c[2]},
        "NormalDirectionX": n[0], "NormalDirectionY": n[1], "NormalDirectionZ": n[2]}}
        for i, (c, n, r) in enumerate(kreise)}
    ent["EntityX"] = {"EntityTypeAsInt": 2, "Segment": {"EntityType": "Line", "Vertices": {}}}
    kont = io.BytesIO()
    with zipfile.ZipFile(kont, "w") as kz:
        kz.writestr("ContourData.json", json.dumps({"EntityContainer": {"Entities": ent}}))
    with zipfile.ZipFile(ziel, "w") as z:
        z.writestr("tubeProps/app.xml", "<appProperties/>")
        z.writestr(f"Task3D/Workpiece{name}.bson", bson(werkstueck))
        z.writestr(f"Task3D/contour/Contour{name}.opcContour", kont.getvalue())


TMP = Path(tempfile.mkdtemp())
ROHR = ohne(ohne(quader(60, 40, 400), quader(54, 34, 402, 3, 3, -1)), zyl(5, 10, 200, 20, -5, (0, 1, 0)))
schreibe({"Rohr": ROHR}, TMP)
KREISE = [((20.0, 0.0, 200.0), (0, -1, 0), 5.0), ((20.0, 3.0, 200.0), (0, -1, 0), 5.0)]
tubx(ROHR, "Rohr_T", KREISE, TMP / "Rohr_T.tubx")
tubx(ROHR, "Rohr_O", [], TMP / "Rohr_O.tubx")
(S,) = analysiere_datei(TMP / "Rohr.step")


@fall("X1 TUBX wie STEP: Rechteckrohr 60×40×3, Länge 400, Schneidweg und Konturen gleich, Bohrung Ø10 exakt")
def _x1():
    (t,) = analysiere_datei(TMP / "Rohr_T.tubx")
    assert t.profilform == S.profilform == "Rechteckrohr", (t.profilform, S.profilform)
    assert abs(t.abm_a - 60) < 0.05 and abs(t.abm_b - 40) < 0.05 and abs(t.wandstaerke - 3) < 0.05, t
    assert abs(t.laenge - S.laenge) < 0.05, (t.laenge, S.laenge)
    assert t.konturen == S.konturen and t.innen_konturen == S.innen_konturen, (t.konturen, S.konturen)
    assert abs(t.schneidweg - S.schneidweg) < 0.01 * S.schneidweg, (t.schneidweg, S.schneidweg)
    assert dict(t.bohrungen) == dict(S.bohrungen) == {10.0: 1}, (t.bohrungen, S.bohrungen)


@fall("X2 ohne Modellkreise: Rohr gemessen, Bohrung nur als Kontur; kaputte TUBX: klare Meldung")
def _x2():
    (t,) = analysiere_datei(TMP / "Rohr_O.tubx")
    assert t.profilform == "Rechteckrohr" and t.konturen == S.konturen and not t.bohrungen, (t.profilform, t.bohrungen)
    (TMP / "kaputt.tubx").write_bytes(b"kein zip")
    try:
        analysiere_datei(TMP / "kaputt.tubx")
        raise AssertionError("kaputte TUBX ohne Fehler")
    except ValueError as e:
        assert "TUBX" in str(e), e
    paare = step_tubx.bohrungen([dict(c=c, n=n, r=r) for c, n, r in KREISE])
    assert len(paare) == 1 and abs(paare[0][2] - 3.0) < 1e-9 and paare[0][3] == 5.0, paare


@fall("X3 Programm: .tubx wie .step im Ablegen, in der Dateiauswahl und im Ordner")
def _x3():
    from rohrlaser import step, trumpf_programm
    assert ".tubx" in step.CAD_ENDUNGEN and "*.tubx" in step.CAD_FILTER
    assert step.step_kandidaten([str(TMP / "Rohr_T.tubx")])
    assert [p.name for p in step.step_dateien([str(TMP)]) if p.suffix == ".tubx"] == ["Rohr_O.tubx", "Rohr_T.tubx", "kaputt.tubx"]
    assert trumpf_programm.lst_dateien(["a.lst", "b.tubx", "c.LST"]) == ["a.lst", "c.LST"]


print("Alle Tests bestanden." if not fehler else f"{fehler} Fehler")
sys.exit(1 if fehler else 0)
