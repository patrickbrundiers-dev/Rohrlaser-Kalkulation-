"""Prüfteile für die Geometrieprüfung des STEP-Imports (Master-Auftrag CAD-Importkern 24.11.2026).

Erzeugt tests/step_pruefung/ mit Dateien, deren Sollwerte aus der Konstruktion bekannt sind:
- P01: Rechteckrohr mit Prüfwerten des „Original-CAD“ (CAx-IF Geometric Validation Properties: Volumen, Oberfläche,
  Schwerpunkt) – richtig, Abgleich muss „bestätigt“ ergeben.
- P02: wie P01, Volumen in den Prüfwerten 2 % zu groß – Abgleich muss „abweichung“ ergeben.
- P03: Rechteckrohr in Zoll mit Prüfwerten in Zoll – Umrechnung der Prüfwerte (Volumen ×25,4³) prüfen.
- P04: Rechteckrohr, Genauigkeit der Datei 0,05 mm (UNCERTAINTY) – Toleranzstufe „grob“.
- P05: zwei deckungsgleiche Körper (zweimal eingefügt) – „doppelt“.
- P06: Quader mit einer verdreht eingebauten Fläche (Schale falsch orientiert).
- P07: Prisma über eine sich selbst kreuzende Kontur („Fliege“).
- P08: Quader mit fehlender Fläche (offene Schale).
Die Messwerte der Rohre selbst kommen aus erzeuge_testteile (gleiche Bausteine).

Aufruf: python tests/erzeuge_pruefteile_2411.py
"""
import sys
from pathlib import Path

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import (BRepBuilderAPI_Copy, BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon,
                                BRepBuilderAPI_MakeSolid)
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism
from OCP.GProp import GProp_GProps
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shell
from OCP.gp import gp_Pnt, gp_Vec

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
from erzeuge_testteile import kastenrohr, schreibe, schreibe_einheit  # noqa: E402

ZIEL = HIER / "step_pruefung"


def kenn(shape):
    p, q = GProp_GProps(), GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, p)
    BRepGProp.SurfaceProperties_s(shape, q)
    c = p.CentreOfMass()
    return p.Mass(), q.Mass(), (c.X(), c.Y(), c.Z())


def gvp_einfuegen(pfad, volumen, flaeche, schwerpunkt):
    """Prüfwerte nach CAx-IF GVP 4.6 an PRODUCT_DEFINITION_SHAPE der Datei anhängen (Werte in Datei-Einheiten)."""
    import re
    text = pfad.read_text(encoding="latin-1")
    pds = re.search(r"#(\d+)\s*=\s*PRODUCT_DEFINITION_SHAPE\(", text).group(1)
    ctx = re.search(r"ADVANCED_BREP_SHAPE_REPRESENTATION\([^;]*#(\d+)\s*\)\s*;", text, re.S).group(1)
    x, y, z = schwerpunkt
    neu = (f"#990001 = PROPERTY_DEFINITION('geometric validation property','volume of part',#{pds});\n"
           f"#990002 = PROPERTY_DEFINITION_REPRESENTATION(#990001,#990003);\n"
           f"#990003 = REPRESENTATION('volume',(#990004),#{ctx});\n"
           f"#990004 = MEASURE_REPRESENTATION_ITEM('volume measure',VOLUME_MEASURE({volumen!r}),#990005);\n"
           f"#990005 = DERIVED_UNIT((#990006));\n"
           f"#990006 = DERIVED_UNIT_ELEMENT(#990007,3.);\n"
           f"#990007 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );\n"
           f"#990011 = PROPERTY_DEFINITION('geometric validation property','surface area of part',#{pds});\n"
           f"#990012 = PROPERTY_DEFINITION_REPRESENTATION(#990011,#990013);\n"
           f"#990013 = REPRESENTATION('surface area',(#990014),#{ctx});\n"
           f"#990014 = MEASURE_REPRESENTATION_ITEM('surface area measure',AREA_MEASURE({flaeche!r}),#990005);\n"
           f"#990021 = PROPERTY_DEFINITION('geometric validation property','centroid of part',#{pds});\n"
           f"#990022 = PROPERTY_DEFINITION_REPRESENTATION(#990021,#990023);\n"
           f"#990023 = REPRESENTATION('centroid',(#990024),#{ctx});\n"
           f"#990024 = CARTESIAN_POINT('centre point',({x!r},{y!r},{z!r}));\n")
    text = text.replace("ENDSEC;\nEND-ISO-10303-21;", neu + "ENDSEC;\nEND-ISO-10303-21;")
    assert "#990024" in text
    pfad.write_text(text, encoding="latin-1")


def flaechen(s):
    ex, out = TopExp_Explorer(s, TopAbs_FACE), []
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def schale(fl):
    b, sh = BRep_Builder(), TopoDS_Shell()
    b.MakeShell(sh)
    for f in fl:
        b.Add(sh, f)
    return BRepBuilderAPI_MakeSolid(TopoDS.Shell(sh)).Solid()


def schreibe_roh(shape, name):
    """Ohne Prüfung schreiben (fehlerhafte Körper)."""
    ZIEL.mkdir(parents=True, exist_ok=True)
    w = STEPControl_Writer()
    w.Transfer(shape, STEPControl_AsIs)
    w.Write(str(ZIEL / f"{name}.step"))


def main():
    rohr = kastenrohr(60, 40, 2, 1000, 4)
    v, a, sp = kenn(rohr)
    schreibe(rohr, "P01_RE60x40x2_Pruefwerte_richtig", ZIEL)
    gvp_einfuegen(ZIEL / "P01_RE60x40x2_Pruefwerte_richtig.step", v, a, sp)
    schreibe(rohr, "P02_RE60x40x2_Pruefwerte_falsch", ZIEL)
    gvp_einfuegen(ZIEL / "P02_RE60x40x2_Pruefwerte_falsch.step", v * 1.02, a, sp)
    schreibe_einheit(rohr, "P03_RE60x40x2_Zoll_Pruefwerte", ZIEL, "inch")
    f = 25.4
    gvp_einfuegen(ZIEL / "P03_RE60x40x2_Zoll_Pruefwerte.step", v / f ** 3, a / f ** 2, tuple(x / f for x in sp))
    schreibe(rohr, "P04_RE60x40x2_Genauigkeit_005", ZIEL)
    p = ZIEL / "P04_RE60x40x2_Genauigkeit_005.step"
    text = p.read_text(encoding="latin-1")
    assert "UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07)" in text
    p.write_text(text.replace("UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07)",
                              "UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.05)"), encoding="latin-1")
    b, comp = BRep_Builder(), TopoDS_Compound()
    b.MakeCompound(comp)
    b.Add(comp, rohr)
    b.Add(comp, BRepBuilderAPI_Copy(rohr).Shape())      # eigene Geometrie, gleiche Lage: zweimal eingefügt
    schreibe(comp, "P05_RE60x40x2_doppelt", ZIEL)
    box = BRepPrimAPI_MakeBox(100, 40, 60).Shape()
    fl = flaechen(box)
    schreibe_roh(schale([fl[0].Reversed()] + fl[1:]), "P06_Quader_Flaeche_verdreht")
    w = BRepBuilderAPI_MakePolygon(gp_Pnt(0, 0, 0), gp_Pnt(50, 30, 0), gp_Pnt(50, 0, 0), gp_Pnt(0, 30, 0),
                                   True).Wire()
    schreibe_roh(BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(w, True).Face(), gp_Vec(0, 0, 20)).Shape(),
                 "P07_Prisma_Kontur_kreuzt")
    schreibe_roh(schale(fl[1:]), "P08_Quader_offen")
    print(f"{len(list(ZIEL.glob('*.step')))} Prüfteile in {ZIEL}")


if __name__ == "__main__":
    main()
