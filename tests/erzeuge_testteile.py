"""Erzeugt Test-STEP-Dateien mit bekannten Sollwerten (tests/step/)."""
import math
import sys
from pathlib import Path

from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeBox, BRepPrimAPI_MakePrism
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepBuilderAPI import (BRepBuilderAPI_Transform, BRepBuilderAPI_NurbsConvert, BRepBuilderAPI_MakePolygon,
                                BRepBuilderAPI_MakeFace)
from OCP.STEPControl import (STEPControl_Writer, STEPControl_AsIs, STEPControl_ShellBasedSurfaceModel,
                             STEPControl_Controller)
from OCP.Interface import Interface_Static
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


def schraeg_ende(shape, z, um_x, um_y, ende_b=True, breite=500):
    """Schneidet ein Ende mit einer Ebene durch (0, 0, z) ab, deren Normale erst um X (um_x), dann um Y (um_y) aus der
    Rohrachse geneigt ist. ende_b: alles oberhalb der Ebene weg, sonst alles unterhalb."""
    k = BRepPrimAPI_MakeBox(gp_Pnt(-breite / 2, -breite / 2, 0 if ende_b else -breite), breite, breite, breite).Shape()
    tr = gp_Trsf(); tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), math.radians(um_x))
    ty = gp_Trsf(); ty.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), math.radians(um_y))
    ty.Multiply(tr)
    k = BRepBuilderAPI_Transform(k, ty, True).Shape()
    return cut(shape, verschiebe(k, 0, 0, z))


def zylinder(p, d, durchm, laenge):
    """Bohrwerkzeug: Zylinder Ø durchm ab Punkt p in Richtung d."""
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*p), gp_Dir(*d)), durchm / 2, laenge).Shape()


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


def schreibe_schema(shape, name, ziel, schema):
    """STEP in einem bestimmten Anwendungsprotokoll (AP203, AP214IS, AP242DIS) schreiben."""
    STEPControl_Controller.Init_s()
    alt = Interface_Static.CVal_s("write.step.schema")
    Interface_Static.SetCVal_s("write.step.schema", schema)
    try:
        schreibe(shape, name, ziel)
    finally:
        Interface_Static.SetCVal_s("write.step.schema", alt)


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
    # Kontur-Teile (eigener Ordner step_konturen): Bohrungen, Langloch, Ausschnitt, Sackbohrung, schräge Bohrung,
    # Gehrung und zweiachsiger Schrägschnitt an bekannten Stellen
    kon = ZIEL.parent / "step_konturen"
    k = kastenrohr(60, 40, 3, 900, 0)                                   # RE 60x40x3, X = 60er-Seite
    k = cut(k, zylinder((0, 10, 100), (0, 1, 0), 10, 30))              # Ø10 oben (+Y, 0°), z 100
    k = cut(k, zylinder((20, 0, 200), (1, 0, 0), 6.6, 30))             # Ø6,6 rechts (+X, 270°), z 200
    ll = cut(cut(BRepPrimAPI_MakeBox(gp_Pnt(-5, -30, 390), 10, 20, 20).Shape(), BRepPrimAPI_MakeBox(
        gp_Pnt(-10, -30, 380), 20, 20, 10).Shape()), BRepPrimAPI_MakeBox(gp_Pnt(-10, -30, 410), 20, 20, 10).Shape())
    k = cut(k, ll)                                                       # Langloch 30x10 längs, unten (-Y, 180°)
    k = cut(k, zylinder((0, -30, 390), (0, 1, 0), 10, 20))
    k = cut(k, zylinder((0, -30, 410), (0, 1, 0), 10, 20))
    k = cut(k, BRepPrimAPI_MakeBox(gp_Pnt(-40, -5, 590), 20, 10, 20).Shape())   # Ausschnitt 20 längs x 10, links (90°)
    k = cut(k, zylinder((0, 19, 700), (0, 1, 0), 6, 10))               # Sackbohrung Ø6, 1 tief, oben, z 700
    k = schraeg_ende(k, 850, 30, 0)                                      # Ende B: Gehrung 30° um X
    schreibe(k, "K01_RE60x40x3_Konturen", kon)
    schreibe(drehe_beliebig(k), "K02_RE60x40x3_Konturen_gedreht", kon)
    r = rundrohr(42.4, 2.0, 700)
    r = cut(r, zylinder((0, 0, 150), (0, 1, 0), 8, 40))                 # Ø8 radial oben (0°), z 150
    r = cut(r, zylinder((0, 0, 300), (0, math.cos(math.radians(30)), math.sin(math.radians(30))), 8, 40))  # 30° schräg
    r = cut(r, zylinder((0, 0, 450), (-1, 0, 0), 12, 40))               # Ø12 radial links (90°), z 450
    r = schraeg_ende(r, 30, 20, 10, ende_b=False)                        # Ende A: zweiachsig 20°/10° durch z 30
    schreibe(r, "K03_RR42-4x2_Konturen", kon)
    # Referenzteile (eigener Ordner step_referenz): Grundformen, STEP-Varianten (AP203/AP214/AP242), CAD-Toleranzen,
    # gefaste Ecken
    ref = ZIEL.parent / "step_referenz"
    schreibe(kastenrohr(60, 40, 2, 1000, 4), "REF01_RE60x40x2_L1000", ref)
    schreibe(kastenrohr(40, 40, 2, 1000, 3), "REF02_QR40x40x2_L1000", ref)
    schreibe(rundrohr(42.4, 2.0, 1000), "REF03_RR42-4x2_L1000", ref)
    for nr, schema in (("REF04", "AP203"), ("REF05", "AP214IS"), ("REF06", "AP242DIS")):
        schreibe_schema(drehe_beliebig(kastenrohr(60, 40, 2, 1000, 4)), f"{nr}_RE60x40x2_{schema}", ref, schema)
    # CAD-Toleranzen: Außenmaß 60,02 x 39,99, Wand 2,01 (Innenkasten 56,00 x 35,97): Maße wie modelliert, Profil
    # passt im Programm trotzdem auf RE 60x40x2 (±0,15 mm)
    schreibe(cut(profil([(-30.01, -19.995), (30.01, -19.995), (30.01, 19.995), (-30.01, 19.995)], 1000),
                 profil([(-28, -17.985), (28, -17.985), (28, 17.985), (-28, 17.985)], 1000)),
             "REF07_RE60x40x2_Toleranz", ref)
    # Quadratrohr 40x2 mit 45°-Fasen statt Radien (außen 3 mm, innen parallel im Abstand der Wand)
    ca, ci = 3.0, 3.0 - 4 + 2 * math.sqrt(2)

    def achteck(h, c):
        return [(-h + c, -h), (h - c, -h), (h, -h + c), (h, h - c), (h - c, h), (-h + c, h), (-h, h - c), (-h, -h + c)]
    schreibe(cut(profil(achteck(20, ca), 800), profil(achteck(18, ci), 800)), "REF08_QR40x2_Fasen_L800", ref)
    # Rechteckrohr 60x40x2 scharfkantig, Ende B 45° Gehrung über die 60er-Seite (Länge außen 1030)
    schreibe(gehrung(kastenrohr(60, 40, 2, 1100, 0), 1000, 45), "REF09_RE60x40x2_Gehrung45", ref)
    # Baugruppe aus drei Rohren, alle verschoben/gedreht
    tr = gp_Trsf(); tr.SetTranslation(gp_Vec(300, 0, 0))
    tr2 = gp_Trsf(); tr2.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), math.radians(90))
    schreibe(baugruppe(kastenrohr(60, 40, 2, 1000, 4),
                       BRepBuilderAPI_Transform(rundrohr(42.4, 2, 600), tr, True).Shape(),
                       BRepBuilderAPI_Transform(kastenrohr(40, 40, 2, 500, 3), tr2, True).Shape()),
             "REF10_Baugruppe_3Rohre", ref)
    # Grenzfälle: gebogenes Rundrohr (90°-Bogen R200) und nicht konvexes Hohlprofil (Quadratrohr mit Sicke)
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeTorus
    bogen = [BRepPrimAPI_MakeTorus(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 200, r, math.radians(90)).Shape()
             for r in (21.2, 19.2)]
    schreibe(cut(*bogen), "REF11_RR42-4x2_Bogen90", ref)
    schreibe(cut(profil([(-20, -20), (20, -20), (20, 20), (5, 20), (0, 15), (-5, 20), (-20, 20)], 600),
                 profil([(-18, -18), (18, -18), (18, 18), (6, 18), (0, 12), (-6, 18), (-18, 18)], 600)),
             "REF12_QR40x2_Sicke", ref)
    # T-Profil 50x40x5 (offen, von der Profilerkennung nicht als U/L/C erkannt): gemeldet, nie kalkuliert
    schreibe(profil([(-25, 15), (-2.5, 15), (-2.5, -20), (2.5, -20), (2.5, 15), (25, 15), (25, 20), (-25, 20)], 600),
             "REF13_T50x40x5_L600", ref)
    # Flächenmodell: geschlossenes Quadratrohr und eine lose Fläche daneben (beides muss gemeldet werden)
    tr = gp_Trsf(); tr.SetTranslation(gp_Vec(200, 0, 0))
    lose = BRepBuilderAPI_Transform(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 21.2, 500)
                                    .Cylinder().LateralFace(), tr, True).Shape()
    schreibe_flaechenmodell(baugruppe(kastenrohr(40, 40, 2, 800, 3), lose), "REF14_Flaechenmodell_mit_loser_Flaeche",
                            ref)
    # Offene Profile mit Konturen (kalkuliert seit 20.10.2026): U 50x30x3 (Steg 50 in Y, Flansche nach +X, Steg
    # außen bei x=0), Ø8 durch den Steg bei z 200, Ø6 durch einen Flansch bei z 400, Ausschnitt 20x10 im Steg bei
    # z 600, Sackbohrung Ø5 (2 mm tief) im Steg bei z 700, Ende B 45° Gehrung (um Y, über die Flanschbreite)
    u = profil([(0, -25), (30, -25), (30, -22), (3, -22), (3, 22), (30, 22), (30, 25), (0, 25)], 900)
    u = cut(u, zylinder((-1, 0, 200), (1, 0, 0), 8, 5))
    u = cut(u, zylinder((15, 20, 400), (0, 1, 0), 6, 10))
    u = cut(u, BRepPrimAPI_MakeBox(gp_Pnt(-1, -5, 590), 5, 10, 20).Shape())
    u = cut(u, zylinder((-1, 0, 700), (1, 0, 0), 5, 3))
    schreibe(gehrung(u, 800, 45), "REF15_U50x30x3_Konturen", ref)
    # L 40x40x4 mit Ø10 durch einen Schenkel bei z 150, gerade Enden, L 500
    lp = profil([(0, 0), (40, 0), (40, 4), (4, 4), (4, 40), (0, 40)], 500)
    schreibe(cut(lp, zylinder((20, -1, 150), (0, 1, 0), 10, 6)), "REF16_L40x40x4_Bohrung", ref)
    # Flachstahl 40x5 L 300 mit zwei Bohrungen Ø9 bei z 50 und 250
    fl = profil([(-20, -2.5), (20, -2.5), (20, 2.5), (-20, 2.5)], 300)
    for z in (50, 250):
        fl = cut(fl, zylinder((0, -3, z), (0, 1, 0), 9, 6))
    schreibe(fl, "REF17_FL40x5_Bohrungen", ref)
    # Bleche (tests/step_bleche, test_step_bleche.py): Blech liegt in XY, Dicke in Z, sofern nicht gedreht
    bl = ZIEL.parent / "step_bleche"

    def blech(lx, ly, d):
        return BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), lx, ly, d).Shape()

    def loch(shape, x, y, durchm, d):
        return cut(shape, zylinder((x, y, -1), (0, 0, 1), durchm, d + 2))
    schreibe(blech(500, 300, 5), "B01_Blech_500x300x5", bl)
    b2 = blech(400, 200, 4)
    for x, y in ((30, 30), (370, 30), (30, 170), (370, 170)):
        b2 = loch(b2, x, y, 10, 4)
    schreibe(loch(b2, 200, 100, 20, 4), "B02_Blech_400x200x4_Bohrungen", bl)
    # Ausschnitt 100x50 und Langloch 40x12 (zwei Halbkreise) im Blech 600x400x3
    b3 = cut(blech(600, 400, 3), BRepPrimAPI_MakeBox(gp_Pnt(100, 100, -1), 100, 50, 5).Shape())
    lang = profil([(400, 194), (420, 194), (420, 206), (400, 206)], 5)
    lang = BRepAlgoAPI_Fuse(BRepAlgoAPI_Fuse(lang, zylinder((400, 200, 0), (0, 0, 1), 12, 5)).Shape(),
                            zylinder((420, 200, 0), (0, 0, 1), 12, 5)).Shape()
    schreibe(cut(b3, verschiebe(lang, 0, 0, -1)), "B03_Blech_600x400x3_Ausschnitte", bl)
    # unregelmäßige Kontur (Fünfeck mit schräger Ecke), Hüllrechteck 400 x 250
    schreibe(profil([(0, 0), (400, 0), (400, 120), (250, 250), (0, 250)], 6), "B04_Blech_400x250x6_Kontur", bl)
    schreibe(drehe_beliebig(blech(500, 300, 5)), "B05_Blech_500x300x5_gedreht", bl)
    # schräg liegend: um X um 30° gekippt, mit Bohrung Ø16
    tr = gp_Trsf(); tr.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), math.radians(30))
    schreibe(BRepBuilderAPI_Transform(loch(blech(250, 180, 8), 125, 90, 16, 8), tr, True).Shape(),
             "B06_Blech_250x180x8_schraeg", bl)
    # gekantet: Grundplatte 120 x 100 x 3, Schenkel 60 hoch, Biegeradius innen 3 / außen 6, Schenkel nur 50 breit
    # (z 25 bis 75), dadurch kein gleichbleibender Querschnitt
    w = profil([(0, 0), (120, 0), (120, 3), (3, 3), (3, 60), (0, 60)], 100, {(0, 0): 6, (3, 3): 3})
    w = cut(w, BRepPrimAPI_MakeBox(gp_Pnt(-1, 10, -1), 5, 60, 26).Shape())
    w = cut(w, BRepPrimAPI_MakeBox(gp_Pnt(-1, 10, 75), 5, 60, 26).Shape())
    schreibe(w, "B07_Blech_gekantet_Winkel", bl)
    # dünnes Vollmaterial, kein Blech: Platte 200 x 100 x 8 mit Tasche 50 x 30, 4 tief
    schreibe(cut(blech(200, 100, 8), BRepPrimAPI_MakeBox(gp_Pnt(75, 35, 4), 50, 30, 5).Shape()),
             "B08_Platte_mit_Tasche", bl)
    # Abgrenzung Flachstahl: 100 x 10 L 800 bleibt Flachstahl, 160 x 8 L 1000 ist breiter als 150 -> Blech,
    # 40 x 8 L 100 ist kürzer als 3 × Breite -> Blech
    schreibe(blech(800, 100, 10), "B09_FL100x10_L800", bl)
    schreibe(blech(1000, 160, 8), "B10_Blech_1000x160x8", bl)
    schreibe(blech(100, 40, 8), "B11_Blech_100x40x8", bl)
    # Fase 2 x 45° an einer Längskante, kleines Reststück
    fase = profil([(0, 0), (300, 0), (300, 3), (298, 5), (0, 5)], 200)
    schreibe(fase, "B12_Blech_300x200x5_Fase", bl)
    schreibe(blech(30, 20, 3), "B13_Blech_30x20x3_Rest", bl)
    # Baugruppe: Rechteckrohr mit zwei Fußplatten
    schreibe(baugruppe(kastenrohr(60, 40, 2, 800, 4), verschiebe(blech(150, 150, 8), -75, -75, -8),
                       verschiebe(blech(150, 150, 8), -75, -75, 800)), "B14_Baugruppe_Rohr_2Bleche", bl)
    print("Testteile geschrieben nach", ZIEL, ",", reg, ",", imp, ",", pro, ",", kon, ",", ref, "und", bl)
