"""Erzeugt STEP-Baugruppen mit Namen und Unterbaugruppen (XCAF) für die Strukturerkennung (tests/step_struktur/).

S01_Gestell_verschachtelt.step:
    Gestell
      Rahmenseite (2×)
        Holm RE60x40x3 L800 (1×)
        Strebe QR40x3 L500 (2×)
      Querrohr RR42.4x2 L600 (2×)
      Schraube ISO 4017 M8x20 (4×)
S02_Einzelteil_benannt.step: ein Teil "Halter 4711 QR40x3" ohne Baugruppe.
"""
import sys
from pathlib import Path

from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.gp import gp_Ax1, gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool

sys.path.insert(0, str(Path(__file__).parent))
from erzeuge_testteile import kastenrohr, rundrohr  # noqa: E402

ZIEL = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "step_struktur"


def lage(x=0, y=0, z=0, um_y=0.0, um_x=0.0):
    t = gp_Trsf()
    if um_y:
        t.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 1, 0)), um_y)
    if um_x:
        r = gp_Trsf()
        r.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0)), um_x)
        t = r.Multiplied(t)
    v = gp_Trsf()
    v.SetTranslation(gp_Vec(x, y, z))
    return TopLoc_Location(v.Multiplied(t))


class Dokument:
    def __init__(self):
        self.doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
        self.st = XCAFDoc_DocumentTool.ShapeTool_s(self.doc.Main())

    def teil(self, name, shape):
        lab = self.st.AddShape(shape, False)
        TDataStd_Name.Set_s(lab, TCollection_ExtendedString(name))
        return lab

    def baugruppe(self, name, teile):
        """teile: Liste (Label, TopLoc_Location)."""
        lab = self.st.NewShape()
        TDataStd_Name.Set_s(lab, TCollection_ExtendedString(name))
        for t, loc in teile:
            self.st.AddComponent(lab, t, loc)
        self.st.UpdateAssemblies()
        return lab

    def schreiben(self, pfad):
        w = STEPCAFControl_Writer()
        w.SetNameMode(True)
        w.Transfer(self.doc, STEPControl_AsIs)
        assert w.Write(str(pfad)) == IFSelect_RetDone, pfad


def main():
    ZIEL.mkdir(parents=True, exist_ok=True)
    d = Dokument()
    holm = d.teil("Holm RE60x40x3 L800", kastenrohr(60, 40, 3, 800, 4.5))
    strebe = d.teil("Strebe QR40x3 L500", kastenrohr(40, 40, 3, 500, 4.5))
    quer = d.teil("Querrohr RR42.4x2 L600", rundrohr(42.4, 2, 600))
    schraube = d.teil("Schraube ISO 4017 M8x20",
                      BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 4, 20).Shape())
    seite = d.baugruppe("Rahmenseite", [(holm, lage()), (strebe, lage(0, 300, 0)), (strebe, lage(0, 600, 0))])
    gestell = d.baugruppe("Gestell", [(seite, lage()), (seite, lage(1000, 0, 0)),
                                     (quer, lage(0, 0, 900, um_y=1.5707963267948966)),
                                     (quer, lage(0, 900, 900, um_y=1.5707963267948966))]
                          + [(schraube, lage(200 * i, -200, 0)) for i in range(4)])
    assert gestell is not None
    d.schreiben(ZIEL / "S01_Gestell_verschachtelt.step")
    e = Dokument()
    e.teil("Halter 4711 QR40x3", kastenrohr(40, 40, 3, 350, 4.5))
    e.schreiben(ZIEL / "S02_Einzelteil_benannt.step")
    print("geschrieben:", ZIEL)


if __name__ == "__main__":
    main()
