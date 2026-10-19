"""Erzeugt Test-STEP-Dateien mit bekannten Sollwerten (tests/step/)."""
import math
import sys
from pathlib import Path

from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepBuilderAPI import (BRepBuilderAPI_Transform, BRepBuilderAPI_NurbsConvert, BRepBuilderAPI_MakePolygon,
                                BRepBuilderAPI_MakeFace)
from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs, STEPControl_ShellBasedSurfaceModel
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Line
from OCP.BRep import BRep_Builder
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir, gp_Trsf, gp_Ax1, gp_Vec

ZIEL = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "step"


def cut(a, b):
    return BRepAlgoAPI_Cut(a, b).Shape()


def rundrohr(d, t, l):
    a = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), d / 2, l).Shape()
    i = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, -1), gp_Dir(0, 0, 1)), d / 2 - t, l + 2).Shape()
    return cut(a, i)


def kastenrohr(b, h, t, l, r_aussen):
    def box(bb, hh, z0, ll, r):
        s = BRepPrimAPI_MakeBox(gp_Pnt(-bb / 2, -hh / 2, z0), bb, hh, ll).Shape()
        if r <= 0:
            return s
        f = BRepFilletAPI_MakeFillet(s)
        ex = TopExp_Explorer(s, TopAbs_EDGE)
        while ex.More():
            e = TopoDS.Edge(ex.Current())
            c = BRepAdaptor_Curve(e)
            if c.GetType() == GeomAbs_Line and abs(abs(c.Line().Direction().Z()) - 1) < 1e-9:
                f.Add(r, e)
            ex.Next()
        return f.Shape()
    return cut(box(b, h, 0, l, r_aussen), box(b - 2 * t, h - 2 * t, -1, l + 2, max(r_aussen - t, 0)))


def profil(punkte, l, radien=None):
    """Gerades Profil aus einem Querschnitt-Polygon (x, y), Länge l in Z; radien {(x, y): r} rundet die Längskanten
    an diesen Ecken (Walz- bzw. Biegeradien)."""
    p = BRepBuilderAPI_MakePolygon()
    for x, y in punkte:
        p.Add(gp_Pnt(x, y, 0))
    p.Close()
    s = BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(p.Wire()).Face(), gp_Vec(0, 0, l)).Shape()
    if not radien:
        return s
    f = BRepFilletAPI_MakeFillet(s)
    ex = TopExp_Explorer(s, TopAbs_EDGE)
    while ex.More():
        e = TopoDS.Edge(ex.Current())
        c = BRepAdaptor_Curve(e)
        if c.GetType() == GeomAbs_Line and abs(abs(c.Line().Direction().Z()) - 1) < 1e-9:
            q = c.Value(c.FirstParameter())
            for (x, y), r in radien.items():
                if abs(q.X() - x) < 1e-6 and abs(q.Y() - y) < 1e-6:
                    f.Add(r, e)
        ex.Next()
    return f.Shape()


def bohrung_quer(shape, d, z, achse=(1, 0, 0)):
    zyl = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(-200 * achse[0], -200 * achse[1], z), gp_Dir(*achse)), d / 2, 400).Shape()
    return cut(shape, zyl)


def gehrung(shape, l, winkel_grad, breite=500):
    """Schneidet das obere Ende unter Winkel ab (um Y-Achse geneigte Ebene durch (0,0,l))."""
    k = BRepPrimAPI_MakeBox(gp_Pnt(-breite / 2, -breite / 2, 0), breite, breite, breite).Shape()
    tr = gp_Trsf(); tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), math.radians(winkel_grad))
    k = BRepBuilderAPI_Transform(k, tr, True).Shape()
    tr2 = gp_Trsf(); tr2.SetTranslation(gp_Vec(0, 0, l))
    k = BRepBuilderAPI_Transform(k, tr2, True).Shape()
    return cut(shape, k)


def drehe_beliebig(shape):
    """Lage im Raum schräg, damit die Achsenerkennung geprüft wird."""
    tr = gp_Trsf(); tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 1, 0)), math.radians(37))
    tr2 = gp_Trsf(); tr2.SetTranslation(gp_Vec(120, -45, 300))
    return BRepBuilderAPI_Transform(BRepBuilderAPI_Transform(shape, tr, True).Shape(), tr2, True).Shape()


def drehe_achse(shape, grad):
    """Dreht das Teil um seine eigene Achse (Z), damit Breite/Höhe nicht mit X/Y zusammenfallen."""
    tr = gp_Trsf(); tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), math.radians(grad))
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def freiform(shape):
    """Alle Flächen und Kanten als Freiformflächen/-kurven (B-Spline), wie sie manche CAD-Systeme exportieren."""
    return BRepBuilderAPI_NurbsConvert(shape, True).Shape()


def verschiebe(shape, x, y, z):
    tr = gp_Trsf(); tr.SetTranslation(gp_Vec(x, y, z))
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def baugruppe(*shapes):
    """Mehrere Körper in einer Datei (wie eine Baugruppe aus dem CAD)."""
    c = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(c)
    for s in shapes:
        b.Add(c, s)
    return c


def schreibe(shape, name, ziel=None):
    ziel = ziel or ZIEL
    ziel.mkdir(parents=True, exist_ok=True)
    w = STEPControl_Writer()
    w.Transfer(shape, STEPControl_AsIs)
    w.Write(str(ziel / f"{name}.step"))


def schreibe_einheit(shape, name, ziel, einheit):
    """STEP in anderer Längeneinheit: Geometrie in diese Einheit umrechnen und die Einheit in der Datei ersetzen.
    Gelesen muss wieder dasselbe Teil in mm herauskommen."""
    faktor = {"inch": 25.4, "m": 1000.0}[einheit]
    tr = gp_Trsf(); tr.SetScale(gp_Pnt(0, 0, 0), 1 / faktor)
    schreibe(BRepBuilderAPI_Transform(shape, tr, True).Shape(), name, ziel)
    pfad = ziel / f"{name}.step"
    text = pfad.read_text(encoding="latin-1")
    alt = "( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )"
    assert alt in text
    if einheit == "m":
        text = text.replace(alt, "( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT($,.METRE.) )")
    else:
        nr = text.index(alt)
        text = text.replace(alt, "( CONVERSION_BASED_UNIT('INCH',#900001) LENGTH_UNIT() NAMED_UNIT(#900003) )")
        zusatz = ("#900001 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(25.4),#900002);\n"
                  "#900002 = ( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );\n"
                  "#900003 = DIMENSIONAL_EXPONENTS(1.,0.,0.,0.,0.,0.,0.);\n")
        ende = text.index("ENDSEC;", nr)
        text = text[:ende] + zusatz + text[ende:]
    pfad.write_text(text, encoding="latin-1")


def schreibe_flaechenmodell(shape, name, ziel):
    """Nur die Flächen (Schalenmodell), kein Volumenkörper – wie manche CAD-Exporte."""
    ziel.mkdir(parents=True, exist_ok=True)
    w = STEPControl_Writer()
    w.Transfer(shape, STEPControl_ShellBasedSurfaceModel)
    w.Write(str(ziel / f"{name}.step"))


if __name__ == "__main__":
    # 1 Rundrohr glatt
    schreibe(rundrohr(42.4, 2.0, 1250), "T01_RR42-4x2_L1250")
    # 2 Rundrohr mit Querbohrung Ø10 (durch beide Wände), räumlich gedreht
    s = bohrung_quer(rundrohr(42.4, 2.0, 860), 10, 430)
    schreibe(drehe_beliebig(s), "T02_RR42-4x2_L860_Bohrung")
    # 3 Quadratrohr 40x40x3 mit Eckradius 6, Querbohrung Ø8 durch eine Seite
    s = kastenrohr(40, 40, 3, 2150, 6)
    zyl = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 1000), gp_Dir(1, 0, 0)), 4, 100).Shape()
    schreibe(cut(s, zyl), "T03_QR40x3_L2150_Bohrung")
    # 4 Rechteckrohr 60x40x3 scharfkantig, ein Ende 45° Gehrung
    schreibe(gehrung(kastenrohr(60, 40, 3, 1795.5 + 60, 0), 1795.5, 45), "T04_RE60x40x3_Gehrung")
    # 5 Rundrohr 33,7x2,6 (nicht in den Beispiel-Stammdaten)
    schreibe(rundrohr(33.7, 2.6, 500), "T05_RR33-7x2-6_L500")
    # 6 Quadratrohr 40x40x3 mit Langloch 20 breit von 10 % bis 90 % der Länge in einer Wand
    s = kastenrohr(40, 40, 3, 1000, 6)
    schlitz = BRepPrimAPI_MakeBox(gp_Pnt(10, -10, 100), 20, 20, 800).Shape()
    schreibe(cut(s, schlitz), "T06_QR40x3_L1000_Langloch")
    # 7 Quadratrohr 40x40x3 L1000, r6: 4x Kernloch Ø5 (M6) in +X-Wand, Rechteckausschnitt 10x20 in -X-Wand,
    #   Gravur 24x5 (0,3 tief) in +Y-Wand, Ausklinkung 16 breit x 15 tief am Ende B in +X-Wand
    s = kastenrohr(40, 40, 3, 1000, 6)
    for z in (100, 150, 200, 250):
        s = cut(s, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(10, 0, z), gp_Dir(1, 0, 0)), 2.5, 20).Shape())
    s = cut(s, BRepPrimAPI_MakeBox(gp_Pnt(-21, -5, 600), 5, 10, 20).Shape())
    s = cut(s, BRepPrimAPI_MakeBox(gp_Pnt(-12, 19.7, 400), 24, 2, 5).Shape())
    s = cut(s, BRepPrimAPI_MakeBox(gp_Pnt(15, -8, 985), 10, 16, 20).Shape())
    schreibe(s, "T07_QR40x3_L1000_Gewinde_Gravur")
    # 8 Baugruppe (eigener Ordner step_satz, damit die Einzelteil-Tests unverändert bleiben): 3x Quadratrohr
    #   40x40x3 L600 (eines gedreht, eines gespiegelt) mit Bohrung Ø8 + 1x Rundrohr 42,4x2 L900 = 2 verschiedene Teile
    q = kastenrohr(40, 40, 3, 600, 6)
    q = cut(q, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 150), gp_Dir(1, 0, 0)), 4, 100).Shape())
    gespiegelt = gp_Trsf(); gespiegelt.SetRotation(gp_Ax1(gp_Pnt(0, 0, 300), gp_Dir(0, 1, 0)), math.pi)
    schreibe(baugruppe(q, verschiebe(q, 100, 0, 0), BRepBuilderAPI_Transform(verschiebe(q, 200, 0, 0), gespiegelt, True).Shape(),
                       drehe_beliebig(rundrohr(42.4, 2.0, 900))),
             "T08_Gestell_Baugruppe", ZIEL.parent / "step_satz")
    # Regressionsteile (eigener Ordner step_regression): Fehler, die die Messung früher hatte
    reg = ZIEL.parent / "step_regression"
    # R01 Rechteckrohr als Freiformflächen: früher Achse falsch, Außenmantel als Schnittkontur gerechnet
    schreibe(freiform(kastenrohr(60, 40, 2, 1000, 4)), "R01_RE60x40x2_L1000_Freiform", reg)
    # R02 Rundrohr als Freiformflächen: früher hing die Messung (Abstand gleichmittiger Kurven)
    schreibe(freiform(rundrohr(42.4, 2.0, 1000)), "R02_RR42-4x2_L1000_Freiform", reg)
    # R03 Rechteckrohr um die eigene Achse gedreht und schräg im Raum: früher 66,16 x 51,54 statt 60 x 40
    schreibe(drehe_beliebig(drehe_achse(kastenrohr(60, 40, 2, 1000, 4), 23)), "R03_RE60x40x2_L1000_gedreht", reg)
    # R04 Quadratrohr 45° um die Achse gedreht: früher 54,08 statt 40
    schreibe(drehe_achse(kastenrohr(40, 40, 2, 800, 3), 45), "R04_QR40x2_L800_45Grad", reg)
    # R05 Teil T07 (Bohrungen, Ausschnitt, Gravur, Ausklinkung) als Freiformflächen, gedreht und verschoben
    schreibe(drehe_beliebig(drehe_achse(freiform(s), 30)), "R05_QR40x3_L1000_Merkmale_Freiform", reg)
    # Import-Teile (eigener Ordner step_import): Einheiten, Flächenmodelle, defekte Dateien
    imp = ZIEL.parent / "step_import"
    schreibe_einheit(kastenrohr(60, 40, 2, 1000, 4), "I01_RE60x40x2_L1000_Zoll", imp, "inch")
    schreibe_einheit(rundrohr(42.4, 2.0, 1000), "I02_RR42-4x2_L1000_Meter", imp, "m")
    schreibe_flaechenmodell(kastenrohr(40, 40, 2, 800, 3), "I03_QR40x2_L800_Flaechenmodell", imp)
    # nur der Außenmantel eines Rundrohrs: offene Fläche, nicht messbar
    schreibe_flaechenmodell(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 21.2, 500).Cylinder()
                            .LateralFace(), "I04_Flaechenmodell_offen", imp)
    (imp / "I05_defekt.step").write_text("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n#1=CARTESIAN_POINT(;\nENDSEC;\n"
                                         "END-ISO-10303-21;\n", encoding="ascii")
    (imp / "I06_leer.step").write_text("", encoding="ascii")
    # Profil-Teile (eigener Ordner step_profile): offene Profile, Vollprofile, ungleiche Wände
    pro = ZIEL.parent / "step_profile"
    u = [(0, 0), (50, 0), (50, 30), (47, 30), (47, 3), (3, 3), (3, 30), (0, 30)]
    schreibe(drehe_beliebig(profil(u, 800)), "P01_U50x30x3_L800", pro)
    schreibe(profil(u, 600, {(0, 0): 6, (50, 0): 6, (3, 3): 3, (47, 3): 3}), "P02_U50x30x3_Radien_L600", pro)
    schreibe(profil([(0, 0), (60, 0), (60, 30), (52, 30), (52, 4), (8, 4), (8, 30), (0, 30)], 500),
             "P03_U60x30_Steg4_Flansch8_L500", pro)
    schreibe(profil([(0, 0), (40, 0), (40, 4), (4, 4), (4, 40), (0, 40)], 800), "P04_L40x40x4_L800", pro)
    schreibe(drehe_beliebig(drehe_achse(profil([(0, 0), (60, 0), (60, 5), (5, 5), (5, 40), (0, 40)], 600), 17)),
             "P05_L60x40x5_gedreht_L600", pro)
    schreibe(profil([(0, 0), (50, 0), (50, 5), (5, 5), (5, 50), (0, 50)], 600, {(5, 5): 7, (50, 5): 2.5, (5, 50): 2.5}),
             "P06_L50x50x5_Radien_L600", pro)
    c = [(0, 0), (50, 0), (50, 20), (47, 20), (47, 3), (3, 3), (3, 97), (47, 97), (47, 80), (50, 80), (50, 100), (0, 100)]
    schreibe(profil(c, 700, {(0, 0): 6, (50, 0): 6, (0, 100): 6, (50, 100): 6, (3, 3): 3, (47, 3): 3, (3, 97): 3,
                             (47, 97): 3}), "P07_C100x50x20x3_L700", pro)
    schreibe(profil([(0, 0), (40, 0), (40, 5), (0, 5)], 800), "P08_FL40x5_L800", pro)
    rr = cut(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 21.2, 800).Shape(),
             BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0.4, 0, -1), gp_Dir(0, 0, 1)), 19.2, 802).Shape())
    schreibe(rr, "P09_RR42-4_exzentrisch_L800", pro)
    schreibe(cut(profil([(-30, -20), (30, -20), (30, 20), (-30, 20)], 600),
                 profil([(-28, -17), (28, -17), (28, 18), (-28, 18)], 600)), "P10_RE60x40_Wand2und3_L600", pro)
    print("Testteile geschrieben nach", ZIEL, ",", reg, ",", imp, "und", pro)
