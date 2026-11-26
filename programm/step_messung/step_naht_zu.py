"""Längsnaht ohne Spalt (Patrick 17.11.2026, tube-laser-cut-1: Rechteckrohr 50 × 30 × 2,6 aus einem Blechmodell).

Manche CAD-Modelle zeichnen ein Rohr als gebogenes Blech: die beiden Blechkanten stoßen an der Naht fast aneinander
(Spalt 0,01 mm, zwei Flächen liegen gegenüber). Jeder Querschnitt ist dann ein einziger Zug (außen, durch die Naht, innen)
statt Außen- und Innenkontur, und das Rohr wurde als „Blech gekantet“ (6 Kantungen) gemessen.

Für die Messung (nur eine Messkopie, die STEP bleibt unverändert) werden solche Flächenpaare geschlossen: ebene
Flächen mit entgegengesetzter Normale, die sich mit höchstens SPALT_MAX Abstand gegenüberliegen, bekommen den Spalt
über der gemeinsamen Fläche gefüllt (mit dem Körper verschmolzen). An den Konturen ändert das nichts: der Spalt ist
schmaler als jeder Laserschnitt.
"""
import step_geometrie as g
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Fuse
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
from OCP.GeomAbs import GeomAbs_Plane
from OCP.GProp import GProp_GProps
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Vec

DICKE = 0.02            # mm: die Füllung reicht so weit in das Material beider Seiten
SPALT_MAX = 0.1         # mm: höchstens so breit ist eine Naht „ohne Spalt“
NORMALE_COS = 0.9999    # entgegengesetzt
FLAECHE_MIN = 1.0       # mm²: so viel gemeinsame Fläche mindestens
EBENEN_MAX = 400        # mehr ebene Flächen: nicht prüfen (Rechenzeit)


def _flaeche(f):
    p = GProp_GProps()
    BRepGProp.SurfaceProperties_s(f, p)
    return abs(p.Mass())


def _ebenen(solid):
    out = []
    for f in g._liste(solid, TopAbs_FACE):
        f = TopoDS.Face(f)
        s = BRepAdaptor_Surface(f)
        if s.GetType() != GeomAbs_Plane:
            continue
        pl = s.Plane()
        n = pl.Axis().Direction()
        if f.Orientation() == 1:        # TopAbs_REVERSED: Normale nach außen umdrehen
            n = n.Reversed()
        out.append((f, n, pl))
    return out


def _prisma(f, n, laenge):
    return BRepPrimAPI_MakePrism(f, gp_Vec(n.X() * laenge, n.Y() * laenge, n.Z() * laenge)).Shape()


def _kaesten(eb):
    """Hüllquader je Fläche, um SPALT_MAX + DICKE vergrößert (Vorprüfung in paare)."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    out = []
    for f, _, _ in eb:
        b = Bnd_Box()
        BRepBndLib.Add_s(f, b)
        b.Enlarge(SPALT_MAX + DICKE)
        out.append(b)
    return out


def paare(solid):
    """Füllungen der Nähte: [Körper zwischen zwei gegenüberliegenden Flächen, je DICKE ins Material].
    Vorprüfung (Importengine 2.0): Flächen, deren Hüllquader (um SPALT_MAX + DICKE vergrößert) sich nicht berühren,
    können keine gemeinsame Fläche haben – die Prismen beider Flächen reichen nur d + DICKE weit, ihre Schnittmenge ist
    leer. Ohne diese Prüfung lief für jedes Paar eine boolesche Operation (aus der LST gebautes Rohr 10186133 P20:
    32.580 Paare in einer Ebene, 108 s, keine Naht); das Ergebnis ist dasselbe."""
    eb = _ebenen(solid)
    if len(eb) > EBENEN_MAX:
        return []
    kasten = _kaesten(eb)
    out = []
    for i, (fa, na, pa) in enumerate(eb):
        for j in range(i + 1, len(eb)):
            fb, nb, pb = eb[j]
            if na.Dot(nb) > -NORMALE_COS:
                continue
            if kasten[i].IsOut(kasten[j]):
                continue
            # Abstand der Ebene von B vor A (in Richtung der Außennormale von A)
            ob, oa = pb.Location(), pa.Location()
            d = (ob.X() - oa.X()) * na.X() + (ob.Y() - oa.Y()) * na.Y() + (ob.Z() - oa.Z()) * na.Z()
            if not -1e-6 <= d <= SPALT_MAX:
                continue
            # A nach vorn bis hinter B, B nach vorn bis hinter A: die Schnittmenge ist der Spalt über der gemeinsamen
            # Fläche, je DICKE in beide Wände
            ka = g.boolesch("und", _prisma(fa, na, d + DICKE), _prisma(fb, nb, d + DICKE), fuzzy=0)
            if not ka.IsDone():
                continue
            k = g._liste(ka.Shape(), TopAbs_SOLID)
            vol = sum(g._volumen(x) for x in k)
            if k and vol >= FLAECHE_MIN * (d + 2 * DICKE) * 0.5:
                out.extend(k)
    return out


def schliessen(solid):
    """(Körper mit geschlossener Naht, Anzahl Füllungen) oder (solid, 0), wenn es keine Naht gibt oder das
    Schließen nicht genau einen Körper ergibt."""
    try:
        pp = paare(solid)
        if not pp:
            return solid, 0
        form = solid
        for k in pp:
            fu = g.boolesch("plus", form, k)
            if not fu.IsDone():
                return solid, 0
            form = fu.Shape()
        k = g._liste(form, TopAbs_SOLID)
        if len(k) != 1:
            return solid, 0
        from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
        u = ShapeUpgrade_UnifySameDomain(k[0], True, True, True)
        u.Build()
        return u.Shape(), len(pp)
    except Exception:  # Schließen darf die Messung nie verhindern
        return solid, 0
