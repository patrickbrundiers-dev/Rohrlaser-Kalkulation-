"""Geometrieauswertung von Rohrlaserteilen aus STEP-Dateien (OpenCascade).

Je Volumenkörper wird ermittelt:
- Rohrachse, Teilelänge (Ausdehnung entlang der Achse)
- Profilform, Abmessungen, Wandstärke, Querschnittsfläche
- Schneidweg getrennt nach Anfangsschnitt (Ende A), Endschnitt (Ende B) und
  Innenkonturen; Gravuren (nicht durchgehend) separat
- Anzahl Konturen (= Einstiche, ohne Gravur), Rundbohrungen je Durchmesser
- Innenkonturen je Kontur mit Größe (Hüllmaß der abgewickelten Kontur, Bohrung Ø) für die Einteilung
  klein/mittel/groß
- auf Wunsch (netz=True) ein Dreiecksnetz für die 3D-Ansicht im Programm: Flächen und Schnittkonturen nach Art
  (Außenwand, Innenwand, Anfangsschnitt, Endschnitt, Innenkontur, Gravur), Rohrachse = Z ab 0

Lokales Rohrkoordinatensystem (_lage): Z = Rohrachse, Ursprung auf der Schwerlinie des Querschnitts, X = Breite
(längere Seite des kleinsten umschreibenden Rechtecks), Y = Höhe. Die Achse kommt aus den Flächennormalen eines
groben Netzes, damit sie auch bei Freiformflächen (B-Spline) und beliebiger Lage im Raum stimmt.

Annahmen:
- Gerades Rohr mit konstantem Querschnitt (gebogene Rundrohre: step_biegerohr, vor dieser Messung).
- Schnitt- und Merkmalsflächen sind zusammen kleiner als der Außenmantel; sonst gilt die Erkennung als unsicher
  und es werden keine Maße ausgegeben.
- Jede Fläche, die nicht zur Außen- oder Innenwand gehört, gehört zu einem
  Merkmal. Reicht das Merkmal bis zur Innenwand, ist es ein Schnitt
  (Enden, Bohrungen, Ausschnitte), sonst eine Gravur.
- Der Schneidweg wird auf der Außenhaut gemessen. Beide Endschnitte zählen
  voll je Teil (kein gemeinsamer Trennschnitt).
- Offene Profile (U, C, L, Flachstahl): eine Kontur im Querschnitt; Schnittlänge = halbe Länge der Konturkanten
  (der Laser schneidet jede Wand einmal), siehe _offen_konturen.
"""
import math
from dataclasses import dataclass, field

from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX, TopAbs_WIRE
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopoDS import TopoDS
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.GCPnts import GCPnts_AbscissaPoint
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Torus, GeomAbs_Line, GeomAbs_BSplineSurface, GeomAbs_BezierSurface
from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
try:  # OCP >= 7.8
    from OCP.collections import (IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape,
                                 IndexedDataMap_TopoDS_Shape_List_TopoDS_Shape_TopTools_ShapeMapHasher
                                 as TopTools_IndexedDataMapOfShapeListOfShape,
                                 HSequence_TopoDS_Shape as TopTools_HSequenceOfShape)
except ImportError:  # ältere OCP-Versionen
    from OCP.TopTools import (TopTools_IndexedMapOfShape, TopTools_IndexedDataMapOfShapeListOfShape,
                              TopTools_HSequenceOfShape)
from OCP.BRep import BRep_Tool
from OCP.gp import gp_Pln, gp_Pnt, gp_Dir, gp_Vec, gp_Ax3, gp_Trsf
from OCP.TopLoc import TopLoc_Location

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))     # programm/: Normtabellen aus rohrlaser
from rohrlaser import dreid, normprofile, rp_profile  # noqa: E402

# ISO-Regelgewinde: Kernlochbohrung nach DIN 336 (Vorgabe; im Programm gelten die Stammdaten 'Gewinde')
KERNLOCH = [("M3", 2.5), ("M4", 3.3), ("M5", 4.2), ("M6", 5.0), ("M8", 6.8), ("M10", 8.5),
            ("M12", 10.2), ("M14", 12.0), ("M16", 14.0), ("M20", 17.5)]

TOL_WAND = 0.05     # mm, Abstand eines Punkts zur Profilkontur
TOL_PARALLEL = 1e-3
SCHRAEG_3D = 0.5     # Grad: ab dieser Neigung gegen die Wandnormale bekommt eine Bohrung neigung_l/neigung_q (3D)


@dataclass
class Teil:
    datei: str
    koerper: int
    profilform: str = ""
    abm_a: float = 0.0          # Ø bzw. Breite
    abm_b: float = 0.0          # Höhe (0 bei Rundrohr)
    wandstaerke: float = 0.0
    flaeche: float = 0.0        # Querschnitt mm²
    laenge: float = 0.0
    schneidweg: float = 0.0
    konturen: int = 0
    ende_a: float = 0.0         # Schnittlänge Ende A (Anfang, kleineres Achsmaß) [mm]
    ende_a_gerade: bool = False # Ende A ist ein gerader Schnitt (senkrecht zur Achse)
    ende_b: float = 0.0
    ende_a_huelle: float = 0.0  # Hüllmaß des Anfangs-/Endschnitts für die Konturklasse (_ende_huellmass) [mm]
    ende_b_huelle: float = 0.0
    ende_b_gerade: bool = False
    innen: float = 0.0          # Schneidweg aller Innenkonturen (Bohrungen, Ausschnitte)
    innen_konturen: int = 0
    gravur: float = 0.0         # Konturlänge nicht durchgehender Merkmale (Gravur/Markierung)
    gravur_konturen: int = 0
    bohrungen: dict = field(default_factory=dict)  # Ø -> Anzahl (durchgehende Rundbohrungen)
    senkungen: dict = field(default_factory=dict)  # (Bohrungs-Ø, Senk-Ø) -> Anzahl (Senkbohrungen)
    fliessloecher: dict = field(default_factory=dict)  # Kernloch-Ø -> Anzahl (Fließlochbohrungen mit Kragen)
    innen_liste: list = field(default_factory=list)  # je Innenkontur (Größe = größtes Hüllmaß, Länge) [mm]
    hinweise: list = field(default_factory=list)
    innen_a: float = 0.0        # Innenmaß Ø bzw. Breite (Hohlprofile)
    innen_b: float = 0.0        # Innenmaß Höhe
    wand_messungen: list = field(default_factory=list)  # je Messstelle (z ab Ende A, x, y, Wert, Seite) [mm]
    sicherheit: dict = field(default_factory=dict)       # je Merkmal: sicher / wahrscheinlich / unsicher / …
    achse_global: tuple = ()    # Richtung der Rohrachse (Ende A -> B) in der Datei, Einheitsvektor
    ende_a_global: tuple = ()   # Mitte von Ende A (Schwerlinie, z = 0) in der Datei [mm]
    x_global: tuple = ()        # lokale X-Richtung (Breite) in der Datei: mit Achse und Ende A die Einbaulage
    bezug: float = 0.0          # 0°-Richtung des Umfangswinkels im Messsystem (_bezug), für nach_bezug_drehen
    konturen_liste: list = field(default_factory=list)  # je Kontur ein dict: Art, Lage (z, Winkel, Seite), Maße
    # Import (je Datei bzw. je Körper)
    einheit: str = ""           # Längeneinheit laut Datei (mm, cm, m, inch, ft); gemessen wird immer in mm
    meldungen: list = field(default_factory=list)  # Meldungen des STEP-Lesers zur Datei
    bauteil: str = ""           # Name des Bauteils in der STEP-Datei (Produktname), leer = keiner
    pfad: str = ""              # Lage in der Baugruppe: "Gestell/Rahmenseite[2]/Strebe" (Instanznummer ab 2)
    knoten: str = ""            # Knoten der Baugruppenstruktur, in dem das Bauteil steckt (struktur["knoten"])
    struktur: dict = None       # Baugruppenstruktur der Datei (je Datei gleich), siehe _struktur
    naehte: list = None         # Nahtkandidaten der Datei (je Datei gleich), siehe _nahtkandidaten
    ohne_naht: list = None      # Körper der Datei ohne Nahtkandidat (nur am ersten Teil), siehe _ohne_naht
    koerperart: str = ""        # Volumenkörper / aus Flächenmodell genäht / Flächenmodell offen
    gueltig: bool = None        # Geometrieprüfung (OpenCascade) bestanden; None = nicht geprüft
    volumen: float = 0.0        # mm³
    oberflaeche: float = 0.0    # mm²
    n_flaechen: int = 0
    n_kanten: int = 0
    huelle: tuple = ()          # Hüllquader in Dateilage (dx, dy, dz) [mm]
    netz: dict = None           # 3D-Ansicht: {p: [x, y, z, …], t: {Art: [i, j, k, …]}, l: {Art: [[x, y, z, …], …]}}
    bauteiltyp: str = ""        # Profil, Blech oder Blech gekantet ("" = nicht erkannt)
    stegdicke: float = 0.0      # I-/H-Träger, T-Profil (Wandstärke = Stegdicke)
    flanschdicke: float = 0.0   # I-/H-Träger (Mittel beider Flansche), T-Profil
    symmetrisch: bool = None    # Träger: Steg mittig, Flansche gleich
    radius: float = 0.0         # Träger: Ausrundung Steg/Flansch (aus der Fläche, ca.)
    normprofil: str = ""        # zugeordnetes Normprofil (IPE 200, HEB 160, UPN 100, L 50x50x5, T 50) oder leer
    blech: dict = None          # nur Bleche: Länge, Breite, Dicke, Flächen, Kontur, Bohrungen, Fingerabdruck (_blech_daten)
    # Grenzfälle Flachstahl/Blech und Profil/Kantteil: dasselbe Teil in der anderen Art gemessen (ohne Netz), im
    # Prüfdialog wählbar; ersatz = nicht so messbar, Werte aus der ersten Messung abgeleitet
    alternative: object = None
    ersatz: bool = False
    # Anbauteile (aufgeschweißte Bolzen, Laschen, Bleche, Muttern, Kopfplatten): nicht Teil der Rohrlaser-Geometrie,
    # je Teil Art, Lage, Aufstandsfläche und Gravur (_anbau_beschreiben); trennung: Regelanteil, Vertrauen und die
    # Messung ohne Trennung (Kurzfassung) – leer, wenn nichts abgetrennt wurde
    anbauteile: list = field(default_factory=list)
    trennung: dict = None
    gravur_anbau: float = 0.0   # Gravur an den Anbauteilen [mm], in gravur enthalten
    # Hohlprofile: Zahl der Innenkonturen (Kammern) und Länge aller Konturen des Querschnitts (Fingerabdruck RP-Profile)
    kammern: int = 0
    kontur_umfang: float = 0.0
    verbund: str = ""           # Verbundprofil: Kern (Kunststoff o. ä.) in der Kammer eines anderen Körpers
    biegerohr: dict = None      # Biegerohr (step_biegerohr): Mittellinie, Elemente, LRA, XYZ; sonst None
    knick_schenkel: list = None  # Knickrahmen aus einem Körper (step_knickrahmen): gemessene Rohrstücke; sonst None
    offene_seite: dict = None   # offenes Rohr geschlossen (step_offenes_rohr): Seite, Lücken, Länge; sonst None
    geschlossen: object = None  # offen gezeichnetes Rohr: Messung mit ergänzter Wand (Teil); sonst None

    @property
    def pruefstatus(self):
        """'nicht messbar' (kein Profil erkannt), 'prüfen' (unsichere Merkmale, Hinweise, ungültige Geometrie) oder
        'plausibel'. Plausibel heißt nur: die Messung ist in sich stimmig – keine Fertigungsfreigabe."""
        if not self.profilform or self.laenge <= 0:
            return "nicht messbar"
        # Fase am Ende: nur Hinweis, Annahme längste Länge gilt (Patrick 22.10.2026), daher kein „prüfen“
        if any(FASE_HINWEIS not in h for h in self.hinweise) or self.gueltig is False or "unsicher" in self.sicherheit.values() or \
                "Sonderprofil" in self.profilform:
            return "prüfen"
        return "plausibel"

    @property
    def profil_id_vorschlag(self):
        f = lambda x: (f"{x:.1f}".rstrip("0").rstrip(".")).replace(".", ",")
        if self.profilform == "Rundrohr":
            return f"RR {f(self.abm_a)}x{f(self.wandstaerke)}"
        if self.profilform == "Quadratrohr":
            return f"QR {f(self.abm_a)}x{f(self.abm_a)}x{f(self.wandstaerke)}"
        if self.profilform == "Rechteckrohr":
            return f"RE {f(self.abm_a)}x{f(self.abm_b)}x{f(self.wandstaerke)}"
        if self.normprofil and self.profilform in ("U-Profil", rp_profile.FORM) + TRAEGER:
            return self.normprofil
        if self.profilform == "I-/H-Träger":
            return f"I {f(self.abm_a)}x{f(self.abm_b)}x{f(self.stegdicke)}x{f(self.flanschdicke)}"
        if self.profilform == "T-Profil":
            return f"T {f(self.abm_a)}x{f(self.abm_b)}x{f(self.stegdicke)}x{f(self.flanschdicke)}"
        kurz = {"U-Profil": "U", "C-Profil": "C", "L-Profil": "L"}.get(self.profilform)
        if kurz:
            return f"{kurz} {f(self.abm_a)}x{f(self.abm_b)}x{f(self.wandstaerke)}"
        if self.profilform == "Flachstahl":
            return f"FL {f(self.abm_a)}x{f(self.abm_b)}"
        if self.profilform == "Vierkantstahl":
            return f"VK {f(self.abm_a)}"
        if self.profilform == "Rundstahl":
            return f"RD {f(self.abm_a)}"
        return ""


EINHEITEN = {".MILLI.": "mm", ".CENTI.": "cm", ".DECI.": "dm", ".KILO.": "km", "$": "m"}


def _einheit(pfad):
    """Längeneinheit laut STEP-Datei (nur zur Information: OpenCascade rechnet beim Lesen in mm um)."""
    import re
    try:
        text = open(pfad, encoding="latin-1", errors="replace").read()
    except OSError:
        return ""
    text = re.sub(r"\s+", "", text.upper())
    m = re.search(r"CONVERSION_BASED_UNIT\('([^']*)'[^;]*LENGTH_UNIT", text) or \
        re.search(r"LENGTH_UNIT\(\)[^;]*CONVERSION_BASED_UNIT\('([^']*)'", text)
    if m:
        return {"INCH": "inch", "FOOT": "ft"}.get(m.group(1), m.group(1).lower())
    m = re.search(r"LENGTH_UNIT\(\)NAMED_UNIT\(\*\)SI_UNIT\(([^,]*),\.METRE\.\)", text) or \
        re.search(r"SI_UNIT\(([^,]*),\.METRE\.\)[^;]*LENGTH_UNIT", text)
    return EINHEITEN.get(m.group(1), m.group(1)) if m else "unbekannt"


def _konsole_mitschneiden(fn):
    """Führt fn aus und gibt (Ergebnis, Konsolenausgabe) zurück. OpenCascade schreibt Lesefehler direkt auf die
    Konsole (Dateideskriptor 1), nicht über Python."""
    import os
    import re
    import tempfile
    sys_out = None
    try:
        import sys
        sys.stdout.flush()
        sys_out = os.dup(1)
    except (OSError, ValueError):
        return fn(), ""
    with tempfile.TemporaryFile(mode="w+b") as tmp:
        os.dup2(tmp.fileno(), 1)
        try:
            erg = fn()
        finally:
            os.dup2(sys_out, 1)
            os.close(sys_out)
        tmp.seek(0)
        text = tmp.read().decode("utf-8", "replace")
    return erg, re.sub(r"\x1b\[[0-9;]*m", "", text)


GROSS_AB_MB = 20         # Performance-Update P5: ab dieser Dateigröße beim Einlesen ohne die Prüfung auf sich
                        # kreuzende Kanten (wächst quadratisch mit den Kanten einer Fläche: Rohr mit 7.000 Bohrungen über
                        # 80 min, ohne etwa 13 min mit Baugruppenleser). Kleinere Dateien werden wie bisher geheilt.
SCHNELL_OHNE = ("FixShape.FixNonAdjacentIntersectingEdgesMode", "FixShape.FixSelfIntersectionMode")


def _grosse_datei_einstellen(leser, pfad):
    """leser: Reader oder Liste (STEPCAFControl und STEPControl); True, wenn die zwei Prüfungen aus sind."""
    try:
        if _Path(pfad).stat().st_size < GROSS_AB_MB * 1e6:
            return False
        from OCP.TCollection import TCollection_AsciiString
        from OCP.collections import DataMap_TCollection_AsciiString_TCollection_AsciiString as Werte
        w = Werte()
        for name in SCHNELL_OHNE:
            w.Bind(TCollection_AsciiString(name), TCollection_AsciiString("0"))
        for r in leser if isinstance(leser, (list, tuple)) else [leser]:
            r.SetShapeFixParameters(w)
        return True
    except Exception:       # ältere OpenCascade-Version: wie bisher
        return False


def lies_step_info(pfad):
    """Liest eine STEP-Datei. Ergebnis: (Körper, Info). Körper = Liste (Art, Shape) mit Art 'Volumenkörper',
    'aus Flächenmodell genäht' (geschlossene Fläche zu Volumen gemacht) oder 'Flächenmodell offen' (nicht messbar).
    Info: einheit, meldungen (Fehler/Warnungen des Lesers), baugruppe (mehrere Körper). Nichts wird still verworfen:
    alles, was weder Volumenkörper noch nähbar ist, kommt als 'Flächenmodell offen' zurück.
    Wirft ValueError, wenn die Datei nicht lesbar ist."""
    from OCP.IFSelect import IFSelect_RetVoid
    try:            # mit Baugruppenstruktur und Namen (XCAF); Körper in derselben Reihenfolge wie ohne
        from OCP.STEPCAFControl import STEPCAFControl_Reader
        caf = STEPCAFControl_Reader()
        caf.SetNameMode(True)
        r = caf.ChangeReader()
    except ImportError:
        caf, r = None, STEPControl_Reader()
    _grosse_datei_einstellen([x for x in (caf, r) if x is not None], pfad)  # CAF-Leser hat eigene Werte
    status, ausgabe = _konsole_mitschneiden(lambda: r.ReadFile(str(pfad)))
    fehler = [z.strip(" *") for z in ausgabe.splitlines() if "ERR" in z or "Fail" in z]
    if status != IFSelect_RetDone:
        grund = "leer oder kein STEP" if status == IFSelect_RetVoid else "Syntaxfehler"
        raise ValueError(f"STEP-Datei nicht lesbar ({grund})" + (": " + "; ".join(fehler[:3]) if fehler else ""))
    meldungen = list(fehler)
    chk = r.WS().ModelCheckList(False)
    chk.Start()
    while chk.More():
        c = chk.Value()
        meldungen += [f"Fehler: {c.CFail(i)}" for i in range(1, c.NbFails() + 1)]
        meldungen += [f"Warnung: {c.CWarning(i)}" for i in range(1, c.NbWarnings() + 1)]
        chk.Next()
    doc = None
    if caf is not None:
        try:
            doc = _caf_uebertragen(caf)
        except Exception:  # Struktur und Namen sind Zusatz: ohne sie wie bisher messen
            doc = None
    if doc is None:
        if caf is not None:         # Übertragung abgebrochen: neu lesen ohne Struktur
            r = STEPControl_Reader()
            r.ReadFile(str(pfad))
        r.TransferRoots()
    shape = r.OneShape()
    koerper = [("Volumenkörper", TopoDS.Solid(x)) for x in _liste(shape, TopAbs_SOLID)]
    # Flächen außerhalb von Volumenkörpern (Flächenmodelle): zusammennähen, geschlossene Schalen werden Volumen
    lose = []
    ex = TopExp_Explorer(shape, TopAbs_FACE, TopAbs_SOLID)
    while ex.More():
        lose.append(ex.Current())
        ex.Next()
    if lose:
        koerper += _naehen(lose)
    meldungen = list(dict.fromkeys(m for m in meldungen if m))
    info = dict(einheit=_einheit(pfad), meldungen=meldungen[:20], baugruppe=len(koerper) > 1, struktur=None,
                bauteile={})
    if doc is not None:
        try:
            info["struktur"], info["bauteile"] = _struktur(doc, koerper, _Path(pfad).stem)
        except Exception:  # wie oben: Struktur darf die Messung nie verhindern
            pass
    return koerper, info


def _caf_uebertragen(caf):
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDocStd import TDocStd_Document
    doc = TDocStd_Document(TCollection_ExtendedString("XmlOcaf"))
    if not caf.Transfer(doc):
        return None
    return doc


def _name(lab):
    from OCP.TDataStd import TDataStd_Name
    n = TDataStd_Name()
    if lab.FindAttribute(TDataStd_Name.GetID_s(), n):
        text = n.Get().ToExtString().strip()
        if text and not text.startswith("=>") and not text.startswith("Open CASCADE STEP translator"):
            return text
    return ""


def _struktur(doc, koerper, dateiname):
    """Baugruppenstruktur aus dem XCAF-Dokument. Ergebnis (struktur, bauteile):
    struktur = None (kein Baugruppe) oder {"knoten": [{id, name, eltern, menge}], "teile": [{teil_index, knoten,
    anzahl}]}: Knoten = Baugruppen (menge = Instanzen je übergeordnetem Knoten, Wurzel 1); Teile = je Knoten und
    Bauteil der erste Körper (teil_index = Körpernummer) mit Anzahl im Knoten. Weitere Instanzen derselben
    Unterbaugruppe stehen nicht noch einmal in teile, ihre Körper aber mit ihrem Pfad in bauteile.
    bauteile = {Körpernummer: (Bauteilname, Pfad, Knoten-ID)} für alle Volumenkörper."""
    from OCP.TDF import TDF_Label
    from OCP.TopLoc import TopLoc_Location
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.collections import Sequence_TDF_Label
    st = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    index = TopTools_IndexedMapOfShape()
    nummer = {}
    for i, (art, k) in enumerate(koerper, start=1):
        if art == "Volumenkörper":
            nummer[index.Add(k)] = i

    def kinder(lab):
        seq = Sequence_TDF_Label()
        st.GetComponents_s(lab, seq)
        out = []
        for j in range(1, seq.Length() + 1):
            ref = TDF_Label()
            if st.GetReferredShape_s(seq.Value(j), ref):
                out.append((seq.Value(j), ref))
        return out

    def eintrag(lab):
        from OCP.TDF import TDF_Tool
        from OCP.TCollection import TCollection_AsciiString
        e = TCollection_AsciiString()
        TDF_Tool.Entry_s(lab, e)
        return e.ToCString()

    frei = Sequence_TDF_Label()
    st.GetFreeShapes(frei)
    wurzeln = [frei.Value(j) for j in range(1, frei.Length() + 1)]
    knoten, teile, bauteile = [], [], {}

    def koerper_von(lab, loc):
        """Körpernummern eines Bauteils in seiner Einbaulage."""
        out = []
        for so in _liste(st.GetShape_s(lab).Located(loc.Multiplied(st.GetShape_s(lab).Location())), TopAbs_SOLID):
            i = index.FindIndex(so)
            if i:
                out.append(nummer[i])
        if not out:     # Lage anders zusammengesetzt: über die Teilform (TShape) suchen
            for so in _liste(st.GetShape_s(lab), TopAbs_SOLID):
                for j in range(1, index.Extent() + 1):
                    if index.FindKey(j).TShape() == so.TShape() and nummer[j] not in bauteile:
                        out.append(nummer[j])
                        break
        return out

    def ablaufen(lab, loc, kid, pfad, erste):
        """Baugruppe lab (Knoten kid) durchlaufen; erste = erste Instanz dieses Knotens (Teile zählen)."""
        anzahl_bg, anzahl_teil, unter, eigene = {}, {}, {}, {}
        for komp, ref in kinder(lab):
            l2 = loc.Multiplied(st.GetLocation_s(komp))
            e = eintrag(ref)
            name = _name(ref) or (_name(komp) if not _name(komp).isdigit() else "")
            if st.IsAssembly_s(ref):
                anzahl_bg[e] = anzahl_bg.get(e, 0) + 1
                if e not in unter:
                    unter[e] = f"K{len(knoten) + 1}"
                    knoten.append(dict(id=unter[e], name=name or f"Baugruppe {len(knoten) + 1}", eltern=kid, menge=0))
                nr = anzahl_bg[e]
                ablaufen(ref, l2, unter[e], pfad + [name + (f"[{nr}]" if nr > 1 else "")], erste and nr == 1)
            else:
                anzahl_teil[e] = anzahl_teil.get(e, 0) + 1
                nr = anzahl_teil[e]
                for i in koerper_von(ref, l2):
                    bauteile[i] = (name, "/".join(pfad + [name + (f"[{nr}]" if nr > 1 else "")]), kid)
                if erste and nr == 1:
                    eigene[e] = [dict(teil_index=i, knoten=kid, anzahl=1) for i in koerper_von(ref, l2)]
                    teile.extend(eigene[e])
                elif erste:
                    for t in eigene.get(e, ()):
                        t["anzahl"] += 1
        if erste:
            for e, n in anzahl_bg.items():
                next(k for k in knoten if k["id"] == unter[e])["menge"] = n

    baugruppen = [w for w in wurzeln if st.IsAssembly_s(w)]
    if not baugruppen:
        for w in wurzeln:           # Einzelteile: nur Namen
            name = _name(w)
            for i in koerper_von(w, TopLoc_Location()):
                bauteile[i] = (name, name, "")
        return None, bauteile
    if len(wurzeln) == 1:
        knoten.append(dict(id="K1", name=_name(wurzeln[0]) or dateiname, eltern=None, menge=1))
        ablaufen(wurzeln[0], TopLoc_Location(), "K1", [knoten[0]["name"]], True)
    else:                           # mehrere freie Formen: gemeinsame Wurzel mit dem Dateinamen
        knoten.append(dict(id="K1", name=dateiname, eltern=None, menge=1))
        for w in wurzeln:
            name = _name(w)
            if st.IsAssembly_s(w):
                kid = f"K{len(knoten) + 1}"
                knoten.append(dict(id=kid, name=name or f"Baugruppe {len(knoten) + 1}", eltern="K1", menge=1))
                ablaufen(w, TopLoc_Location(), kid, [dateiname, knoten[-1]["name"]], True)
            else:
                for i in koerper_von(w, TopLoc_Location()):
                    bauteile[i] = (name, f"{dateiname}/{name}", "K1")
                    teile.append(dict(teil_index=i, knoten="K1", anzahl=1))
    return dict(knoten=knoten, teile=teile), bauteile


def _naehen(flaechen, tol=0.01):
    """Lose Flächen zu Schalen nähen; geschlossene Schalen werden Volumenkörper."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeSolid
    from OCP.ShapeFix import ShapeFix_Solid
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.BRepCheck import BRepCheck_Analyzer
    naht = BRepBuilderAPI_Sewing(tol)
    for f in flaechen:
        naht.Add(f)
    naht.Perform()
    erg = naht.SewedShape()
    out = []
    schalen = _liste(erg, TopAbs_SHELL)
    for sh in schalen:
        sh = TopoDS.Shell(sh)
        if BRep_Tool.IsClosed_s(sh):
            ms = BRepBuilderAPI_MakeSolid(sh)
            if ms.IsDone():
                fix = ShapeFix_Solid(ms.Solid())
                fix.Perform()
                sol = _liste(fix.Shape(), TopAbs_SOLID)
                if sol and BRepCheck_Analyzer(sol[0]).IsValid():
                    out.append(("aus Flächenmodell genäht", TopoDS.Solid(sol[0])))
                    continue
        out.append(("Flächenmodell offen", sh))
    # einzelne Flächen, die zu keiner Schale gehören, werden ebenfalls gemeldet (nichts still verwerfen)
    in_schalen = TopTools_IndexedMapOfShape()
    for sh in schalen:
        TopExp.MapShapes_s(sh, TopAbs_FACE, in_schalen)
    out += [("Flächenmodell offen", f) for f in _liste(erg, TopAbs_FACE) if not in_schalen.Contains(f)]
    return out


def lies_step(pfad):
    """Nur die messbaren Volumenkörper (auch aus Flächenmodellen genähte) einer STEP-Datei."""
    return [k for art, k in lies_step_info(pfad)[0] if art != "Flächenmodell offen"]


def _koerper_daten(t, shape, art):
    """Kenndaten eines Körpers (in Dateilage, mm) und Geometrieprüfung."""
    from OCP.BRepCheck import BRepCheck_Analyzer
    t.koerperart = art
    p = GProp_GProps()
    if art != "Flächenmodell offen":
        BRepGProp.VolumeProperties_s(shape, p)
        t.volumen = abs(p.Mass())
    t.oberflaeche = _flaeche(shape)
    for typ, attr in ((TopAbs_FACE, "n_flaechen"), (TopAbs_EDGE, "n_kanten")):
        m = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, typ, m)
        setattr(t, attr, m.Extent())
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if not box.IsVoid():
        a, b = box.CornerMin(), box.CornerMax()
        t.huelle = (b.X() - a.X(), b.Y() - a.Y(), b.Z() - a.Z())
    t.gueltig = BRepCheck_Analyzer(shape).IsValid()
    if not t.gueltig:
        t.hinweise.append("Geometrie laut Prüfung ungültig (Fehler im CAD-Modell), Messwerte prüfen")
    if art == "aus Flächenmodell genäht":
        t.hinweise.append("Flächenmodell: zu einem Volumen zusammengenäht, Messwerte prüfen")


def _liste(shape, typ):
    out = []
    ex = TopExp_Explorer(shape, typ)
    while ex.More():
        out.append(ex.Current())
        ex.Next()
    return out


def _flaeche(shape):
    p = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, p)
    return p.Mass()


def _kantenlaenge(kante):
    return GCPnts_AbscissaPoint.Length_s(BRepAdaptor_Curve(TopoDS.Edge(kante)))


def _vec(d):
    return gp_Vec(d.X(), d.Y(), d.Z())


def _netz_dreiecke(shape, abw):
    """Dreiecke eines groben Netzes als (Fläche, Normale). Unabhängig davon, wie das CAD die Flächen speichert
    (Ebene, Zylinder oder Freiformfläche). Das Netz wird danach wieder entfernt."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.TopLoc import TopLoc_Location
    BRepMesh_IncrementalMesh(shape, abw, False, 0.3, True)
    out = []
    for f in _liste(shape, TopAbs_FACE):
        ort = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(TopoDS.Face(f), ort)
        if tri is None:
            continue
        tr = ort.Transformation()
        p = [None] + [tri.Node(j).Transformed(tr) for j in range(1, tri.NbNodes() + 1)]
        for j in range(1, tri.NbTriangles() + 1):
            i1, i2, i3 = tri.Triangle(j).Get()
            n = gp_Vec(p[i1], p[i2]).Crossed(gp_Vec(p[i1], p[i3]))
            m = n.Magnitude()
            if m > 1e-12:
                out.append((m / 2, n.Divided(m)))
    BRepTools.Clean_s(shape)
    return out


def _eigen3(m):
    """Eigenwerte und -vektoren (Spalten) einer symmetrischen 3x3-Matrix (Jacobi-Verfahren)."""
    a = [list(r) for r in m]
    v = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    for _ in range(60):
        p, q = max(((0, 1), (0, 2), (1, 2)), key=lambda ij: abs(a[ij[0]][ij[1]]))
        if abs(a[p][q]) <= 1e-14 * (abs(a[0][0]) + abs(a[1][1]) + abs(a[2][2])) + 1e-300:
            break
        th = (a[q][q] - a[p][p]) / (2 * a[p][q])
        tt = (1 if th >= 0 else -1) / (abs(th) + math.sqrt(th * th + 1))
        c = 1 / math.sqrt(tt * tt + 1)
        s = tt * c
        j = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        j[p][p], j[q][q], j[p][q], j[q][p] = c, c, s, -s
        a = [[sum(j[k][i] * a[k][l] * j[l][jj] for k in range(3) for l in range(3)) for jj in range(3)]
             for i in range(3)]
        v = [[sum(v[i][k] * j[k][jj] for k in range(3)) for jj in range(3)] for i in range(3)]
    return [a[i][i] for i in range(3)], v


def _achse_grob(solid, alle=False):
    """Rohrachse aus den Flächennormalen: Mantelflächen (außen, innen) stehen parallel zur Achse, ihre Normalen
    also senkrecht dazu. Die Achse ist die Richtung, zu der die Normalen (flächengewichtet) am wenigsten zeigen
    = Eigenvektor zum kleinsten Eigenwert von Σ Fläche·n·nᵀ. Funktioniert auch bei Freiformflächen."""
    box = Bnd_Box()
    BRepBndLib.Add_s(solid, box, False)
    p0, p1 = box.CornerMin(), box.CornerMax()
    diag = p0.Distance(p1)
    tris = _netz_dreiecke(solid, max(0.01, diag / 2000))
    m = [[0.0] * 3 for _ in range(3)]
    for fl, n in tris:
        k = (n.X(), n.Y(), n.Z())
        for i in range(3):
            for j in range(3):
                m[i][j] += fl * k[i] * k[j]
    werte, vek = _eigen3(m)
    achsen = []
    for i in sorted(range(3), key=lambda k: werte[k]):
        achse = gp_Vec(vek[0][i], vek[1][i], vek[2][i]).Normalized()
        # Richtung festlegen (sonst zufällig): größter Anteil positiv. Ende A liegt damit in der Datei vorn
        # (kleinere Koordinate in der Hauptrichtung des Rohrs).
        k = max((achse.X(), achse.Y(), achse.Z()), key=abs)
        if k < 0:
            achse.Reverse()
        achsen.append(achse)
    mitte = gp_Pnt((p0.X() + p1.X()) / 2, (p0.Y() + p1.Y()) / 2, (p0.Z() + p1.Z()) / 2)
    # alle=True: alle drei Eigenvektoren als Achskandidaten (bester zuerst), z. B. wenn große Anbauteile die
    # Normalenverteilung verschieben
    return (achsen, mitte) if alle else (achsen[0], mitte)


def _transformiere(shape, ax3):
    """Shape in das System ax3 (Z = Rohrachse) umrechnen."""
    tr = gp_Trsf()
    tr.SetTransformation(ax3)
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def _global(ax3, x, y, z):
    """Lokale Koordinaten in ax3 als globaler Punkt."""
    o, dx, dy, dz = ax3.Location(), ax3.XDirection(), ax3.YDirection(), ax3.Direction()
    return gp_Pnt(o.X() + x * dx.X() + y * dy.X() + z * dz.X(), o.Y() + x * dx.Y() + y * dy.Y() + z * dz.Y(),
                  o.Z() + x * dx.Z() + y * dy.Z() + z * dz.Z())


def _z_bereich(shape):
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    return box.CornerMin().Z(), box.CornerMax().Z()


def _schnitt(shape, z):
    """Konturen der Schnittebene Z = z, größte zuerst: Liste (Fläche, Draht, Schwerpunkt x, y)."""
    sec = BRepAlgoAPI_Section(shape, gp_Pln(gp_Pnt(0, 0, z), gp_Dir(0, 0, 1)), False)
    sec.SetRunParallel(True)   # Freiformflächen schneiden ist langsam
    sec.Build()
    kanten = TopTools_HSequenceOfShape()
    for e in _liste(sec.Shape(), TopAbs_EDGE):
        kanten.Append(e)
    if kanten.Length() == 0:
        return []
    wires = ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(kanten, 1e-4, False)
    out = []
    for i in range(1, wires.Length() + 1):
        w = TopoDS.Wire(wires.Value(i))
        mf = BRepBuilderAPI_MakeFace(w, True)
        if not mf.IsDone():
            continue
        p = GProp_GProps()
        BRepGProp.SurfaceProperties_s(mf.Face(), p)
        c = p.CentreOfMass()
        out.append((abs(p.Mass()), w, c.X(), c.Y()))
    out.sort(key=lambda x: -x[0])
    return out


def _querschnitt_daten(ws):
    """Netto-Fläche und Schwerpunkt eines Schnitts (größte Kontur außen, alle anderen innen). Liegt eine Kontur
    neben statt in der größten (Schnitt durch einen langen Ausschnitt zerfällt in Stücke), ist es kein Regel-
    querschnitt: Fläche 0 (sonst Netto-Fläche ≈ 0 und ein Schwerpunkt weit außerhalb, die Achse kippt weg)."""
    netto = ws[0][0] - sum(w[0] for w in ws[1:])
    if netto <= 1e-6 * ws[0][0] or any(not _innen_liegend(w[1], ws[0][1]) for w in ws[1:]):
        return 0.0, 0.0, 0.0
    sx = ws[0][0] * ws[0][2] - sum(w[0] * w[2] for w in ws[1:])
    sy = ws[0][0] * ws[0][3] - sum(w[0] * w[3] for w in ws[1:])
    return netto, sx / netto, sy / netto


def _querschnitt_gruppen(lok, zmin, zmax, n):
    """Schnitte an n Stellen, gruppiert nach Konturanzahl und Fläche: Liste von Gruppen [(z, Konturen, Fläche,
    Schwerpunkt x, y)]."""
    schnitte = []
    for i in range(n):
        z = zmin + (i + 0.537) / (n + 0.1) * (zmax - zmin)
        ws = _schnitt(lok, z)
        if ws:
            netto, cx, cy = _querschnitt_daten(ws)
            if netto > 0:
                schnitte.append((z, ws, netto, cx, cy))
    gruppen = []
    for s in schnitte:
        for g in gruppen:
            if len(g[0][1]) == len(s[1]) and abs(g[0][2] - s[2]) <= 0.002 * g[0][2]:
                g.append(s)
                break
        else:
            gruppen.append([s])
    return gruppen


def _regelquerschnitt(lok, zmin, zmax, n=7):
    """Schnitte an n Stellen; die häufigste Kombination aus Konturanzahl und Fläche ist der Regelquerschnitt
    (Schnitte durch Bohrungen o. ä. weichen ab). Ergebnis: Liste (z, Konturen, Fläche, Schwerpunkt x, y)."""
    gruppen = _querschnitt_gruppen(lok, zmin, zmax, n)
    if not gruppen:
        return [] if n >= REGEL_DICHT else _regelquerschnitt(lok, zmin, zmax, REGEL_DICHT)
    beste = max(gruppen, key=lambda g: (len(g), g[0][2]))
    if len(beste) < 3 and n < REGEL_DICHT:
        # viele Ausschnitte (Rohr voller Langlöcher): die meisten Schnitte treffen ein Merkmal, dichter suchen, damit
        # die Achse aus drei gleichen Querschnitten sicher ist
        dicht = _regelquerschnitt(lok, zmin, zmax, REGEL_DICHT)
        if len(dicht) > len(beste):
            return dicht
    if len(beste[0][1]) == 1 and n < REGEL_DICHT and any(
            len(_schnitt(lok, zmin + f * (zmax - zmin)) or ()) >= 2 for f in (0.01, 0.03, 0.97, 0.99)):
        # offener Querschnitt: auch ein Rohr mit einem langen Fenster (Patrick 27.10.2026, größere Ausschnitte) – alle
        # Schnitte treffen das Fenster, der Schwerpunkt liegt neben der Rohrmitte. Gibt es an anderer Stelle (meist
        # nahe den Enden) mindestens zwei gleiche geschlossene Querschnitte mit größerer Fläche, sind sie der Regel-
        # querschnitt (ein Ausschnitt nimmt nur Werkstoff weg). Dicht gesucht wird nur, wenn ein Probeschnitt nahe
        # den Enden geschlossen ist (offene Profile und Vollmaterial sonst ohne Mehraufwand)
        zu = [g for g in _querschnitt_gruppen(lok, zmin, zmax, REGEL_DICHT)
              if len(g) >= 2 and len(g[0][1]) >= 2 and g[0][2] > beste[0][2] * 1.002]
        if zu:
            return max(zu, key=lambda g: (g[0][2], len(g)))
    return beste


REGEL_DICHT = 41      # Schnitte, wenn bei 7 Schnitten keine drei gleichen Regelquerschnitte gefunden werden


def _min_rechteck(pts):
    """Drehwinkel des flächenkleinsten umschreibenden Rechtecks (über die konvexe Hülle)."""
    pts = sorted(set((round(x, 6), round(y, 6)) for x, y in pts))
    if len(pts) < 3:
        return 0.0

    def kreuz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    unten, oben = [], []
    for p in pts:
        while len(unten) >= 2 and kreuz(unten[-2], unten[-1], p) <= 0:
            unten.pop()
        unten.append(p)
    for p in reversed(pts):
        while len(oben) >= 2 and kreuz(oben[-2], oben[-1], p) <= 0:
            oben.pop()
        oben.append(p)
    huelle = unten[:-1] + oben[:-1]
    best = None
    for i in range(len(huelle)):
        (x1, y1), (x2, y2) = huelle[i], huelle[(i + 1) % len(huelle)]
        w = math.atan2(y2 - y1, x2 - x1)
        c, s = math.cos(w), math.sin(w)
        us = [x * c + y * s for x, y in huelle]
        vs = [-x * s + y * c for x, y in huelle]
        du, dv = max(us) - min(us), max(vs) - min(vs)
        fl = du * dv
        if best is None or fl < best[0] - 1e-9:
            best = (fl, w if du >= dv else w + math.pi / 2)
    return best[1]


def _strecken(draht, schritt=0.5):
    """Kontur als Polygonzug-Strecken (x1, y1, x2, y2) in der XY-Ebene, Teilung höchstens 'schritt' mm
    (Gerade: 1 mm, damit Punkte auch in der Mitte langer Seiten liegen)."""
    out = []
    for e in _liste(draht, TopAbs_EDGE):
        c = BRepAdaptor_Curve(TopoDS.Edge(e))
        lg = _kantenlaenge(e)
        n = max(2, min(2000, int(lg / (1.0 if c.GetType() == GeomAbs_Line else schritt)) + 1))
        u0, u1 = c.FirstParameter(), c.LastParameter()
        q = [c.Value(u0 + (u1 - u0) * k / n) for k in range(n + 1)]
        out += [(a.X(), a.Y(), b.X(), b.Y()) for a, b in zip(q, q[1:])]
    return out


def _abst_strecke(x, y, s):
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    ll = dx * dx + dy * dy
    u = 0.0 if ll == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / ll))
    return math.hypot(x - x1 - u * dx, y - y1 - u * dy)


RASTER = 2.0          # mm, Zellgröße des Rasters für Abstände Punkt–Polygonzug
RASTER_AB = 64        # erst ab so vielen Strecken lohnt das Raster
RASTER_RINGE = 6      # weiter entfernt (über 12 mm): alle Strecken durchgehen
_RASTER = {}          # id(strecken) -> (strecken, Raster); die Listen werden nach dem Anlegen nicht mehr geändert


def _raster(strecken):
    """Strecken nach Rasterzellen (jede Strecke in allen Zellen ihres Hüllrechtecks). Für Abstände wird nur in den
    Zellen um den Punkt gerechnet – mit derselben Formel (_abst_strecke), nur weit entfernte Strecken entfallen, die
    nachweislich nicht die nächsten sind: gleiche Werte wie jeder gegen jeden (Performance-Audit 22.10.2026)."""
    eintrag = _RASTER.get(id(strecken))
    if eintrag is not None and eintrag[0] is strecken and eintrag[2] == len(strecken):
        return eintrag[1]
    zellen = {}
    if not all(math.isfinite(v) for st in strecken for v in st):
        return None
    for i, (x1, y1, x2, y2) in enumerate(strecken):
        for ix in range(math.floor(min(x1, x2) / RASTER), math.floor(max(x1, x2) / RASTER) + 1):
            for iy in range(math.floor(min(y1, y2) / RASTER), math.floor(max(y1, y2) / RASTER) + 1):
                zellen.setdefault((ix, iy), []).append(i)
    if len(_RASTER) > 200:
        _RASTER.clear()
    _RASTER[id(strecken)] = (strecken, zellen, len(strecken))
    return zellen


def _ring(cx, cy, r):
    if r == 0:
        yield cx, cy
        return
    for ix in range(cx - r, cx + r + 1):
        yield ix, cy - r
        yield ix, cy + r
    for iy in range(cy - r + 1, cy + r):
        yield cx - r, iy
        yield cx + r, iy


def _abstand_zug(x, y, strecken):
    if len(strecken) < RASTER_AB or not (math.isfinite(x) and math.isfinite(y)):
        return min(_abst_strecke(x, y, s) for s in strecken)
    zellen = _raster(strecken)
    if zellen is None:
        return min(_abst_strecke(x, y, s) for s in strecken)
    cx, cy = math.floor(x / RASTER), math.floor(y / RASTER)
    best = math.inf
    for r in range(RASTER_RINGE + 1):
        for z in _ring(cx, cy, r):
            for i in zellen.get(z, ()):
                d = _abst_strecke(x, y, strecken[i])
                if d < best:
                    best = d
        # nicht besuchte Zellen liegen mindestens r·RASTER vom Punkt entfernt
        if best <= r * RASTER - 1e-6:
            return best
    return min(_abst_strecke(x, y, s) for s in strecken)


def _nah_zug(x, y, strecken, tol):
    if len(strecken) < RASTER_AB or tol > RASTER * (RASTER_RINGE - 2) or not (math.isfinite(x) and math.isfinite(y)):
        return any(_abst_strecke(x, y, s) < tol for s in strecken)
    zellen = _raster(strecken)
    if zellen is None:
        return any(_abst_strecke(x, y, s) < tol for s in strecken)
    cx, cy = math.floor(x / RASTER), math.floor(y / RASTER)
    # eine Strecke näher als tol berührt eine Zelle höchstens ceil(tol/RASTER) Zellen weiter (+1 Sicherheit)
    return any(_abst_strecke(x, y, strecken[i]) < tol for r in range(math.ceil(tol / RASTER) + 2)
               for z in _ring(cx, cy, r) for i in zellen.get(z, ()))


def _zylinder(face, tol=1e-3):
    """Zylinder (gp_Cylinder) einer Fläche oder None. Freiformflächen werden versuchsweise in einen Zylinder
    umgerechnet (Abweichung höchstens tol mm), weil manche CAD-Systeme auch Bohrungen als B-Spline exportieren."""
    sf = BRepAdaptor_Surface(TopoDS.Face(face))
    if sf.GetType() == GeomAbs_Cylinder:
        return sf.Cylinder()
    if sf.GetType() not in (GeomAbs_BSplineSurface, GeomAbs_BezierSurface):
        return None
    from OCP.GeomConvert import GeomConvert_SurfToAnaSurf
    from OCP.GeomAdaptor import GeomAdaptor_Surface
    ana = GeomConvert_SurfToAnaSurf(BRep_Tool.Surface_s(TopoDS.Face(face))).ConvertToAnalytical(tol)
    if ana is None:
        return None
    ga = GeomAdaptor_Surface(ana)
    return ga.Cylinder() if ga.GetType() == GeomAbs_Cylinder else None


def _wandstaerke(aussen, innen, s_aussen, s_innen, z0):
    """Kleinster Abstand zwischen Außen- und Innenkontur. Der exakte Abstand Kontur–Kontur hängt bei gleichmittigen
    Freiformkurven (unendlich viele kürzeste Verbindungen), darum: Kandidaten über die Polygonzüge suchen und für die
    nächstgelegenen Punkte den exakten Abstand Punkt–Kontur rechnen."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    werte = []
    for von, nach, draht in ((s_aussen, s_innen, innen), (s_innen, s_aussen, aussen)):
        kand = sorted((_abstand_zug(s[0], s[1], nach), s[0], s[1]) for s in von)[:5]
        for _, x, y in kand:
            d = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(x, y, z0)).Vertex(), draht)
            if d.IsDone():
                werte.append(d.Value())
    return min(werte) if werte else 0.0


def _lage(solid, start=None):
    """Lokales Rohrkoordinatensystem: Z = Rohrachse, Ursprung auf der Schwerlinie des Regelquerschnitts,
    X = Richtung der längeren Seite des kleinsten umschreibenden Rechtecks (Breite), Y = Höhe.
    1. grobe Achse aus den Flächennormalen, 2. zweimal nachschärfen über die Schwerpunkte von zwei weit
    auseinanderliegenden Regelquerschnitten (bei konstantem Querschnitt liegen sie auf einer achsparallelen Linie),
    3. Drehung um die Achse aus dem Querschnitt. Ergebnis: (gp_Ax3, Regelquerschnitt im neuen System).
    start: (Achse, Mitte) statt der groben Achse (Achskandidaten der Anbauteil-Trennung)."""
    achse, mitte = start or _achse_grob(solid)
    ax3 = gp_Ax3(mitte, gp_Dir(achse.X(), achse.Y(), achse.Z()))
    gruppe = []
    for _ in range(3):
        lok = _transformiere(solid, ax3)
        zmin, zmax = _z_bereich(lok)
        gruppe = _regelquerschnitt(lok, zmin, zmax)
        if len(gruppe) < 2 or gruppe[-1][0] - gruppe[0][0] < 0.2 * (zmax - zmin):
            break
        (z1, _, _, x1, y1), (z2, _, _, x2, y2) = gruppe[0], gruppe[-1]
        dx, dy = (x2 - x1) / (z2 - z1), (y2 - y1) / (z2 - z1)
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            break
        p1 = _global(ax3, x1, y1, z1)
        g = _vec(ax3.XDirection()).Multiplied(dx).Added(_vec(ax3.YDirection()).Multiplied(dy)).Added(
            _vec(ax3.Direction()))
        ax3 = gp_Ax3(p1, gp_Dir(g.X(), g.Y(), g.Z()))
    if not gruppe:
        return ax3, []
    mitte_g = min(gruppe, key=lambda s: abs(s[0] - (gruppe[0][0] + gruppe[-1][0]) / 2))
    z, ws, _, cx, cy = mitte_g
    pts = [(s[0], s[1]) for s in _strecken(ws[0][1])]
    w = _min_rechteck(pts)
    o = _global(ax3, cx, cy, z)
    xr = _vec(ax3.XDirection()).Multiplied(math.cos(w)).Added(_vec(ax3.YDirection()).Multiplied(math.sin(w)))
    ax3 = gp_Ax3(o, ax3.Direction(), gp_Dir(xr.X(), xr.Y(), xr.Z()))
    return ax3, gruppe


def _profilform(aussen, a, b, tol=0.05):
    """Form der Außenkontur (im ausgerichteten System, Mitte ≈ 0): Kreis = alle Punkte gleich weit von der Mitte,
    Rechteck = die vier Seiten der Hülle sind mit geraden Abschnitten belegt (Ecken dürfen gerundet sein)."""
    st = _strecken(aussen)
    xs = [s[0] for s in st]
    ys = [s[1] for s in st]
    mx, my = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    r = [math.hypot(x - mx, y - my) for x, y in zip(xs, ys)]
    if max(r) - min(r) < 2 * tol:
        return "Kreis"
    belegt = [0.0] * 4
    gesamt = 0.0
    for x1, y1, x2, y2 in st:
        lg = math.hypot(x2 - x1, y2 - y1)
        gesamt += lg
        for k, (u1, u2, grenze) in enumerate(((x1, x2, a / 2), (x1, x2, -a / 2), (y1, y2, b / 2), (y1, y2, -b / 2))):
            if abs(u1 - (mx if k < 2 else my) - grenze) < tol and abs(u2 - (mx if k < 2 else my) - grenze) < tol:
                belegt[k] += lg
    if gesamt > 0 and sum(belegt) >= 0.5 * gesamt and min(belegt[0:2]) >= 0.1 * b and min(belegt[2:4]) >= 0.1 * a:
        return "Rechteck"
    return ""


TOL_WAND_GLEICH = 0.05  # mm: Einzelmessungen der Wandstärke, die weiter auseinanderliegen, gelten als widersprüchlich
OFFENE_PROFILE = ("U-Profil", "C-Profil", "L-Profil", "Flachstahl", "Vierkantstahl", "Rundstahl", "I-/H-Träger",
                  "T-Profil")


def _kanten_punkte(draht):
    """Je Kante die Punktfolge (x, y) des Polygonzugs (Teilung wie _strecken)."""
    out = []
    for e in _liste(draht, TopAbs_EDGE):
        c = BRepAdaptor_Curve(TopoDS.Edge(e))
        lg = _kantenlaenge(e)
        n = max(2, min(2000, int(lg / (1.0 if c.GetType() == GeomAbs_Line else 0.5)) + 1))
        u0, u1 = c.FirstParameter(), c.LastParameter()
        out.append([(q.X(), q.Y()) for q in (c.Value(u0 + (u1 - u0) * k / n) for k in range(n + 1))])
    return out


def _gerade(pts, tol=0.01):
    """True, wenn alle Punkte auf der Verbindung erster–letzter Punkt liegen (auch bei Freiformkurven)."""
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    lg = math.hypot(x2 - x1, y2 - y1)
    return lg > 0 and all(abs((x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)) / lg < tol for x, y in pts)


def _im_material(x, y, strecken):
    """Punkt im Querschnitt (Gerade nach +X schneidet die Konturen ungerade oft)."""
    n = 0
    for x1, y1, x2, y2 in strecken:
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            n += 1
    return n % 2 == 1


def _strahl(x, y, dx, dy, strecken):
    """Abstand vom Punkt in Richtung (dx, dy) bis zur nächsten Kontur (ohne den Startpunkt selbst)."""
    best = None
    for x1, y1, x2, y2 in strecken:
        ex, ey = x2 - x1, y2 - y1
        nenner = dx * ey - dy * ex
        if abs(nenner) < 1e-12:
            continue
        s = ((x1 - x) * ey - (y1 - y) * ex) / nenner
        u = ((x1 - x) * dy - (y1 - y) * dx) / nenner
        if s > 1e-4 and -1e-9 <= u <= 1 + 1e-9 and (best is None or s < best):
            best = s
    return best


def _wand_messungen(ws, kreis, z):
    """Wandstärke an mehreren Stellen des Querschnitts: senkrecht von der Außenkontur ins Material bis zur nächsten
    Kontur. Messstellen auf geraden Kanten bei 25/50/75 % (in Rundungen nicht, dort sind Außen- und Innenradius oft
    nicht gleichmittig), beim Kreis an 8 Stellen rundum. Ergebnis: Liste (z, x, y, Wert, Seite)."""
    alle = [s for w in ws for s in _strecken(w[1])]
    stellen = []
    kanten = _kanten_punkte(ws[0][1])
    if kreis:
        pts = [p for k in kanten for p in k]
        mx = (max(p[0] for p in pts) + min(p[0] for p in pts)) / 2
        my = (max(p[1] for p in pts) + min(p[1] for p in pts)) / 2
        for i in range(8):
            w = math.radians(22.5 + 45 * i)
            # Punkt der Außenkontur in dieser Richtung: Strahl von der Mitte nach außen, letzter Schnittpunkt
            d = max((s for s in (_strahl_alle(mx, my, math.cos(w), math.sin(w), alle))), default=None)
            if d:
                stellen.append((mx + d * math.cos(w), my + d * math.sin(w), -math.cos(w), -math.sin(w), "rund", None))
    else:
        for k in kanten:
            if not _gerade(k):
                continue
            (x1, y1), (x2, y2) = k[0], k[-1]
            lg = math.hypot(x2 - x1, y2 - y1)
            if lg < 3:
                continue
            nx, ny = -(y2 - y1) / lg, (x2 - x1) / lg
            for u in (0.25, 0.5, 0.75):
                px, py = x1 + u * (x2 - x1), y1 + u * (y2 - y1)
                if not _im_material(px + 0.01 * nx, py + 0.01 * ny, alle):
                    nx, ny = -nx, -ny
                seite = "x" if abs(nx) > abs(ny) else "y"
                stellen.append((px, py, nx, ny, f"{seite}{'+' if (px if seite == 'x' else py) > 0 else '-'}", lg))
    out = []
    for px, py, nx, ny, seite, lg in stellen:
        d = _strahl(px, py, nx, ny, alle)
        # eine Wand ist länger als dick: kurze Kanten (Stirnseite eines Schenkels o. ä.) messen keine Wand
        if d is not None and (lg is None or lg >= 2 * d):
            out.append((z, px, py, d, seite))
    return out


def _strahl_alle(x, y, dx, dy, strecken):
    """Alle Abstände, in denen ein Strahl die Konturen schneidet."""
    out = []
    for x1, y1, x2, y2 in strecken:
        ex, ey = x2 - x1, y2 - y1
        nenner = dx * ey - dy * ex
        if abs(nenner) < 1e-12:
            continue
        s = ((x1 - x) * ey - (y1 - y) * ex) / nenner
        u = ((x1 - x) * dy - (y1 - y) * dx) / nenner
        if s > 0 and -1e-9 <= u <= 1 + 1e-9:
            out.append(s)
    return out


def _seiten_belegung(strecken, x0, y0, x1, y1, tol=0.05):
    """Je Seite des Hüllrechtecks (links, rechts, unten, oben) die belegten Abschnitte [(von, bis)] entlang der Seite."""
    seiten = {"links": [], "rechts": [], "unten": [], "oben": []}
    for ax, ay, bx, by in strecken:
        for name, wert, koord, lauf in (("links", x0, (ax, bx), (ay, by)), ("rechts", x1, (ax, bx), (ay, by)),
                                        ("unten", y0, (ay, by), (ax, bx)), ("oben", y1, (ay, by), (ax, bx))):
            if abs(koord[0] - wert) < tol and abs(koord[1] - wert) < tol:
                seiten[name].append((min(lauf), max(lauf)))
    for name, ab in seiten.items():
        ab.sort()
        verbunden = []
        for a, b in ab:
            if verbunden and a <= verbunden[-1][1] + 0.6:
                verbunden[-1] = (verbunden[-1][0], max(verbunden[-1][1], b))
            else:
                verbunden.append((a, b))
        seiten[name] = verbunden
    return seiten


def _offenes_profil(draht, flaeche, x0, y0, x1, y1, je_seite):
    """Form eines Querschnitts mit nur einer Kontur. Ergebnis (Form, A, B, Bemerkung) oder None.
    Flachstahl/Vierkantstahl: Rechteck voll; Rundstahl: Kreis voll; L: zwei benachbarte Seiten des Hüllrechtecks voll
    belegt, die beiden anderen nur am Ende (Schenkeldicke); U: drei Seiten voll, die vierte nur an beiden Enden in
    Wanddicke; C: wie U, aber die vierte Seite an den Enden länger belegt (Abkantung)."""
    w, h = x1 - x0, y1 - y0
    st = _strecken(draht)
    if flaeche >= 0.97 * w * h:
        return ("Vierkantstahl" if abs(w - h) < 0.1 else "Flachstahl"), max(w, h), min(w, h), ""
    if _profilform(draht, w, h) == "Kreis":
        if flaeche >= 0.97 * math.pi / 4 * w * h:
            return "Rundstahl", (w + h) / 2, 0.0, ""
        return None
    s = _seiten_belegung(st, x0, y0, x1, y1)
    lang = {"links": h, "rechts": h, "unten": w, "oben": w}
    voll = {n for n, ab in s.items() if len(ab) == 1 and ab[0][1] - ab[0][0] >= 0.6 * lang[n]}
    gegen = {"links": "rechts", "rechts": "links", "unten": "oben", "oben": "unten"}
    if len(voll) == 2 and not any(gegen[n] in voll for n in voll):
        rest = [n for n in s if n not in voll]
        if all(len(s[n]) == 1 and s[n][0][1] - s[n][0][0] < 0.5 * lang[n] for n in rest):
            return "L-Profil", max(w, h), min(w, h), ""
    if len(voll) == 3:
        offen = next(n for n in s if n not in voll)
        if gegen[offen] in voll and len(s[offen]) == 2:
            # Ausdehnung der Enden von der Ecke des Hüllrechtecks aus (Außenradien an den Ecken zählen mit)
            von, bis = (y0, y1) if offen in ("links", "rechts") else (x0, x1)
            enden = [min(b - von, bis - a) for a, b in s[offen]]
            steg = lang[offen]     # Höhe = Länge der Stegseite, Breite = Flanschlänge
            breite = lang["unten" if offen in ("links", "rechts") else "links"]
            # Flanschdicke: gemessen von den Flansch-Außenseiten (quer zur offenen Seite)
            wand = je_seite.get("y" if offen in ("links", "rechts") else "x")
            if wand and all(abs(e - wand) <= max(0.2, 0.1 * wand) for e in enden):
                return "U-Profil", steg, breite, ""
            if wand and all(e >= 1.5 * wand for e in enden):
                return "C-Profil", steg, breite, f"Abkantung {min(enden):.1f} mm"
    # I/H: zwei gegenüberliegende Seiten voll (Flansche außen), die beiden anderen an beiden Enden in Flanschdicke
    # belegt. T: eine Seite voll (Flansch), die Gegenseite einmal (Stegende), die beiden anderen einmal (Flanschkante).
    if len(voll) == 2 and all(gegen[n] in voll for n in voll):
        quer = [n for n in s if n not in voll]
        if all(len(s[n]) == 2 for n in quer):
            return _traeger(st, flaeche, x0, y0, x1, y1, "oben" in voll, "I-/H-Träger")
    if len(voll) == 1:
        f = next(iter(voll))
        quer = [n for n in s if n not in (f, gegen[f])]
        if len(s[gegen[f]]) == 1 and all(len(s[n]) == 1 for n in quer):
            return _traeger(st, flaeche, x0, y0, x1, y1, f in ("oben", "unten"), "T-Profil")
    return None


def _traeger(st, flaeche, x0, y0, x1, y1, waagerecht, form):
    """Maße eines I-/H-Trägers oder T-Profils. waagerecht: Flansche liegen waagerecht (sonst werden x und y
    getauscht). Stegdicke: waagerechter Strahl durch den Steg; Flanschdicke: senkrechter Strahl bei (b − tw) / 4
    von der Flanschkante (Messstelle der Norm, auch bei geneigten Flanschen). Ausrundung aus dem Flächenüberschuss
    gegenüber dem scharfkantigen Querschnitt. Ergebnis (Form, h, b, Bemerkung, Zusatz) oder None."""
    if not waagerecht:
        st = [(ay, ax, by, bx) for ax, ay, bx, by in st]
        x0, y0, x1, y1 = y0, x0, y1, x1
    h, b = y1 - y0, x1 - x0
    s = _seiten_belegung(st, x0, y0, x1, y1)
    if form == "T-Profil":
        oben = len(s["oben"]) == 1 and s["oben"][0][1] - s["oben"][0][0] >= 0.6 * b
        y_steg = y0 + 0.35 * h if oben else y1 - 0.35 * h
    else:
        y_steg = (y0 + y1) / 2
    def alle(x, y, dx, dy):     # Treffer an einer Teilungsstelle der Kontur nur einmal zählen
        out = []
        for d in sorted(_strahl_alle(x, y, dx, dy, st)):
            if not out or d - out[-1] > 1e-6:
                out.append(d)
        return out
    treffer = alle(x0 - 1, y_steg + 0.0137 * h, 1, 0)
    if len(treffer) != 2:
        return None
    tw = treffer[1] - treffer[0]
    xm = x0 - 1 + (treffer[0] + treffer[1]) / 2
    dicken = []
    for xs in (x0 + (b - tw) / 4, x1 - (b - tw) / 4):
        z = alle(xs + 0.0113 * b, y0 - 1, 0, 1)
        if len(z) % 2 or not z:
            return None
        dicken.append([z[k + 1] - z[k] for k in range(0, len(z), 2)])
    if form == "T-Profil":
        if any(len(d) != 1 for d in dicken):
            return None
        tf, tf2 = dicken[0][0], dicken[1][0]
        scharf = b * tf + (h - tf) * tw
        ecken = 2
    else:
        if any(len(d) != 2 for d in dicken):
            return None
        tf, tf2 = dicken[0][0], dicken[0][1]
        tf = (tf + dicken[1][0]) / 2
        tf2 = (tf2 + dicken[1][1]) / 2
        scharf = b * (tf + tf2) + (h - tf - tf2) * tw
        ecken = 4
    if tw <= 0 or tf <= 0 or tw >= b or tf + (tf2 if form != "T-Profil" else 0) >= h:
        return None
    breiten = [ab[0][1] - ab[0][0] for ab in (s["unten"], s["oben"]) if len(ab) == 1]
    symmetrisch = (abs(xm - (x0 + x1) / 2) <= 0.1 and abs(tf - tf2) <= 0.1 and
                   (form == "T-Profil" or len(breiten) == 2 and abs(breiten[0] - breiten[1]) <= 0.2))
    ueber = max(0.0, flaeche - scharf)
    r = math.sqrt(ueber / (ecken * (1 - math.pi / 4))) if ueber > 0.5 else 0.0
    zusatz = dict(stegdicke=tw, flanschdicke=max(tf, tf2) if form == "T-Profil" else (tf + tf2) / 2,
                  flansch_oben=tf2, flansch_unten=tf, symmetrisch=symmetrisch, radius=r)
    bemerkung = "" if symmetrisch else "unsymmetrisch: " + (
        f"Flansche {tf:.1f} / {tf2:.1f} mm" if abs(tf - tf2) > 0.1 else "Steg außermittig oder Flansche ungleich breit")
    return form, h, b, bemerkung, zusatz


class _Abwicklung:
    """Abwicklung der Außenkontur (konvexe Hohlprofile): Umfangswinkel und Umfangsposition eines Punkts.

    Winkel: um die Rohrachse rechtsdrehend (Daumen der rechten Hand zeigt von Ende A nach Ende B), 0° = Bezugsrichtung
    ref (Richtung im Querschnitt, siehe _bezug). Umfangsposition u: Bogenlänge auf der Außenkontur ab 0° [mm]."""

    def __init__(self, s_aussen, ref):
        xs = [s[0] for s in s_aussen] + [s[2] for s in s_aussen]
        ys = [s[1] for s in s_aussen] + [s[3] for s in s_aussen]
        self.cx, self.cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        self.ref = ref
        pts = sorted({(round(self.theta(x, y), 9), x, y) for x, y in zip(xs, ys)})
        self.th, self.s, self.xy = [], [], []
        lauf = 0.0
        for i, (th, x, y) in enumerate(pts):
            if i:
                lauf += math.hypot(x - pts[i - 1][1], y - pts[i - 1][2])
            self.th.append(th)
            self.s.append(lauf)
            self.xy.append((x, y))
        self.umfang = lauf + math.hypot(pts[0][1] - pts[-1][1], pts[0][2] - pts[-1][2])
        self.versatz = 0.0
        self.versatz = self._u_th(0.0)      # u = 0 genau bei 0°

    def theta(self, x, y):
        return (math.degrees(math.atan2(-(x - self.cx), y - self.cy)) - self.ref) % 360

    def u(self, x, y):
        return self._u_th(self.theta(x, y))

    def _u_th(self, th):
        import bisect
        i = bisect.bisect_left(self.th, th)
        if i <= 0:
            t0, t1, s0, s1 = self.th[-1] - 360, self.th[0], self.s[-1] - self.umfang, self.s[0]
        elif i >= len(self.th):
            t0, t1, s0, s1 = self.th[-1], self.th[0] + 360, self.s[-1], self.umfang
        else:
            t0, t1, s0, s1 = self.th[i - 1], self.th[i], self.s[i - 1], self.s[i]
        return ((s0 + (s1 - s0) * (th - t0) / (t1 - t0) if t1 > t0 else s0) - self.versatz) % self.umfang

    def punkt(self, u):
        """(Winkel, x, y) des Punkts der Außenkontur an der Umfangsposition u."""
        import bisect
        u = (u + self.versatz) % self.umfang
        i = min(max(bisect.bisect_right(self.s, u), 1), len(self.s) - 1)
        s0, s1 = self.s[i - 1], self.s[i]
        f = (u - s0) / (s1 - s0) if s1 > s0 else 0.0
        x = self.xy[i - 1][0] + f * (self.xy[i][0] - self.xy[i - 1][0])
        y = self.xy[i - 1][1] + f * (self.xy[i][1] - self.xy[i - 1][1])
        return self.theta(x, y), x, y


GRAVUR_TIEFE = 0.5       # mm: flachere nicht durchgehende Merkmale sind immer Gravur (Prägung), nie Sackbohrung
UMRISS_PUNKTE = 300      # höchstens so viele Punkte je Umriss (sonst gröber ausgedünnt)


def _umriss_uv(kanten, abw, zmin, u_mitte=None):
    """Abgewickelter Umriss einer Kontur (STEP-JSON 1.12): Punkte [u, z] der Reihe nach, u = Umfangsposition
    [mm] wie bei 'u' (über die 0°-Naht hinaus fortlaufend, also auch < 0 oder > Umfang), z ab Ende A. Mehrere Züge:
    der längste, um ganze Umfänge so verschoben, dass seine Mitte bei u_mitte liegt. Ausgedünnt auf 0,05 mm (bei
    sehr vielen Punkten gröber); None, wenn sich nichts ordnen lässt."""
    seq = TopTools_HSequenceOfShape()
    for e in kanten:
        seq.Append(e)
    try:
        wires = ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(seq, 1e-3, False)
        zuege = [TopoDS.Wire(wires.Value(i)) for i in range(1, wires.Length() + 1)]
    except Exception:  # Umriss ist nur Zusatz
        return None
    if not zuege:
        return None
    w = max(zuege, key=_draht_laenge)
    pts, vorher, versatz = [], None, 0.0
    for p in _draht_punkte(w, 0.25):
        u = abw.u(p.X(), p.Y())
        if vorher is not None:
            if u + versatz - vorher > abw.umfang / 2:
                versatz -= abw.umfang
            elif vorher - (u + versatz) > abw.umfang / 2:
                versatz += abw.umfang
        vorher = u + versatz
        pts.append((vorher, p.Z() - zmin))
    if len(pts) < 3:
        return None
    mitte = (max(u for u, _ in pts) + min(u for u, _ in pts)) / 2
    k = round((u_mitte - mitte) / abw.umfang) if u_mitte is not None else -math.floor(mitte / abw.umfang)
    pts = [(u + k * abw.umfang, z) for u, z in pts]
    tol = 0.05
    um = _vereinfachen(pts, tol)
    while len(um) > UMRISS_PUNKTE and tol < 5:
        tol *= 2
        um = _vereinfachen(pts, tol)
    return [[round(u, 2), round(z, 2)] for u, z in um]


def _bezug(ax3, profilform):
    """Bezugsrichtung 0° des Umfangswinkels im Messsystem (Grad, gleiche Zählung wie _Abwicklung.theta).
    Kastenprofile: Mitte der breiten Seite (±Y), und zwar die, die in der Datei eher nach oben (+Z) zeigt.
    Rundrohre: die in der Datei oberste Stelle (+Z der Datei quer zur Achse; liegt das Rohr senkrecht, +Y der Datei)."""
    def lokal(g):
        return (g.Dot(_vec(ax3.XDirection())), g.Dot(_vec(ax3.YDirection())))
    gx, gy = lokal(gp_Vec(0, 0, 1))
    if math.hypot(gx, gy) < 0.1:
        gx, gy = lokal(gp_Vec(0, 1, 0))
    if profilform == "Rundrohr":
        return math.degrees(math.atan2(-gx, gy))
    return 0.0 if gy >= 0 else 180.0


def _punkte_kanten(kanten, schritt=0.5):
    out = []
    for e in kanten:
        c = BRepAdaptor_Curve(TopoDS.Edge(e))
        n = max(4, min(400, int(_kantenlaenge(e) / schritt) + 1))
        u0, u1 = c.FirstParameter(), c.LastParameter()
        out += [c.Value(u0 + (u1 - u0) * k / n) for k in range(n + 1)]
    return out


def _ende_huellmass(punkte):
    """Hüllmaß eines Anfangs- oder Endschnitts für die Konturklasse [mm]: größere Seite des kleinsten Rechtecks um die
    Schnittkontur in ihrer Ebene. Querschnitt in XY (kleinstes umschreibendes Rechteck mit den Seiten s, t), Neigung
    der Schnittebene aus der Ausgleichsebene z = a·s + b·t + c; die Seiten werden um √(1 + a²) bzw. √(1 + b²)
    länger. Gerader Schnitt QR 40x40 = 40, RR 42,4 = 42,4, Gehrung 45° über die 60er Seite eines RE 60x40 = 84,9."""
    if len(punkte) < 3:
        return None
    w = _min_rechteck([(p.X(), p.Y()) for p in punkte])
    c, s_ = math.cos(w), math.sin(w)
    q = [(p.X() * c + p.Y() * s_, -p.X() * s_ + p.Y() * c, p.Z()) for p in punkte]
    n = len(q)
    ms, mt, mz = (sum(x[i] for x in q) / n for i in range(3))
    sss = sum((x[0] - ms) ** 2 for x in q)
    stt = sum((x[1] - mt) ** 2 for x in q)
    sst = sum((x[0] - ms) * (x[1] - mt) for x in q)
    szs = sum((x[2] - mz) * (x[0] - ms) for x in q)
    szt = sum((x[2] - mz) * (x[1] - mt) for x in q)
    det = sss * stt - sst * sst
    a, b = ((szs * stt - szt * sst) / det, (szt * sss - szs * sst) / det) if abs(det) > 1e-9 else (0.0, 0.0)
    ds = max(x[0] for x in q) - min(x[0] for x in q)
    dt = max(x[1] for x in q) - min(x[1] for x in q)
    return round(max(ds * math.sqrt(1 + a * a), dt * math.sqrt(1 + b * b)), 2)


def _form_2d(uv, tol=0.05):
    """Form einer abgewickelten Kontur: ('Kreis', Ø) / ('Langloch', L, B) / ('Rechteck', L, B) / ('Ausschnitt', L, B),
    dazu Mittelpunkt (u, v) und Drehwinkel der Längsrichtung gegen die Rohrachse [Grad]."""
    w = _min_rechteck(uv)
    c, s = math.cos(w), math.sin(w)
    p = [(x * c + y * s, -x * s + y * c) for x, y in uv]
    p0, p1 = min(q[0] for q in p), max(q[0] for q in p)
    q0, q1 = min(q[1] for q in p), max(q[1] for q in p)
    lg, br = p1 - p0, q1 - q0
    mp, mq = (p0 + p1) / 2, (q0 + q1) / 2
    mitte = (mp * c - mq * s, mp * s + mq * c)
    lage = math.degrees(w) % 180          # 0° = Längsrichtung der Kontur quer zur Rohrachse (entlang u)
    rel = [(a - mp, b - mq) for a, b in p]
    r = [math.hypot(a, b) for a, b in rel]
    if max(r) - min(r) < 2 * tol:
        return ("Kreis", (max(r) + min(r)), 0.0), mitte, lage
    if lg > br + tol:
        h = (lg - br) / 2
        if all(abs(math.hypot(max(abs(a) - h, 0), b) - br / 2) < tol for a, b in rel):
            return ("Langloch", lg, br), mitte, lage
    auf_seite = sum(1 for a, b in rel if abs(abs(a) - lg / 2) < tol or abs(abs(b) - br / 2) < tol)
    if auf_seite >= 0.6 * len(rel):
        return ("Rechteck", lg, br), mitte, lage
    return ("Ausschnitt", lg, br), mitte, lage


def _ebene(face, tol=1e-4):
    """Ebene (gp_Pln) einer Fläche oder None, auch bei ebenen Freiformflächen."""
    from OCP.GeomLib import GeomLib_IsPlanarSurface
    sf = BRepAdaptor_Surface(TopoDS.Face(face))
    if sf.GetType() == GeomAbs_Plane:
        return sf.Plane()
    pr = GeomLib_IsPlanarSurface(BRep_Tool.Surface_s(TopoDS.Face(face)), tol)
    return pr.Plan() if pr.IsPlanar() else None


FASE_HINWEIS = "Fase erkannt"
FASE_TIEFE = 25.0   # mm: so weit darf die Außenkante einer Fase höchstens vom Ende entfernt liegen


def _fase_ende(flaechen, zmin, zmax, gz0, gz1, tol=0.01):
    """'A' bzw. 'B', wenn ein Merkmal eine Fase am Ende ist: seine Flächen reichen bis an das Ende (z min bzw. max),
    die Außenkanten (gz0..gz1) liegen aber davor, höchstens FASE_TIEFE entfernt (Schlitze und Ausklinkungen
    reichen mit ihren Außenkanten bis ans Ende). Sonst None."""
    bb = Bnd_Box()
    for f in flaechen:
        BRepBndLib.AddOptimal_s(f, bb, False, False)
    if bb.IsVoid():
        return None
    fz0, fz1 = bb.CornerMin().Z(), bb.CornerMax().Z()
    if zmax - fz1 < tol and zmax - gz1 > tol and zmax - gz0 <= FASE_TIEFE:
        return "B"
    if fz0 - zmin < tol and gz0 - zmin > tol and gz1 - zmin <= FASE_TIEFE:
        return "A"
    return None


SCHWENK_3D = 0.5    # Grad: ab dieser Abweichung von 90° zur Rohroberfläche ist ein Schnitt eine 3D-Bearbeitung


def schwenk(flaechen, kanten, abw, schritt=2.0):
    """Größter Winkel [Grad] zwischen Schnittfläche und Senkrechter zur Rohroberfläche entlang der Schnittkanten
    (Kanten zur Außenwand), STEP-JSON 1.10. 0 = Strahl senkrecht zur Oberfläche (2D, auch bei einer Gehrung), sonst
    3D (Patrick 23.10.2026: nur 3D, wenn die Geometrie nicht 90° zur Oberfläche steht). None, wenn nichts messbar."""
    from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
    from OCP.GeomLProp import GeomLProp_SLProps
    flaechen = [BRep_Tool.Surface_s(TopoDS.Face(f)) for f in flaechen]
    groesster = None
    for p in _punkte_kanten(kanten, schritt):
        beste = None
        for sf in flaechen:
            pr = GeomAPI_ProjectPointOnSurf(p, sf)
            if pr.NbPoints() and (beste is None or pr.LowerDistance() < beste[0]):
                beste = (pr.LowerDistance(), sf, pr.LowerDistanceParameters())
        if beste is None or beste[0] > 0.05:
            continue
        lp = GeomLProp_SLProps(beste[1], beste[2][0], beste[2][1], 1, 1e-6)
        if not lp.IsNormalDefined():
            continue
        n = lp.Normal()
        uc = abw.u(p.X(), p.Y())
        (_, ax_, ay_), (_, bx_, by_) = abw.punkt(uc - 0.5), abw.punkt(uc + 0.5)
        tl = math.hypot(bx_ - ax_, by_ - ay_)
        if tl < 1e-9:
            continue
        c = abs(n.X() * (by_ - ay_) / tl - n.Y() * (bx_ - ax_) / tl)      # Flächennormale · Wandnormale
        w = math.degrees(math.asin(min(1.0, c)))
        groesster = w if groesster is None else max(groesster, w)
    return None if groesster is None else round(groesster, 2)


def _ende_flaechen(flaechen, kanten, cx, cy, ref, z_ref, tol=0.1):
    """3D-Ende (komplex: mehrere Ebenen, Zylinder quer zur Rohrachse) als Flächen für den Schneidweg-Rechner (STEP-JSON
    1.9): Querschnitt um (cx, cy), gedreht wie _endform (Y = 0°-Richtung), z ab z_ref. Ebene ['E', gx, gy, c] mit
    z = c + gx·x + gy·y, Zylinder ['Z', ux, uy, ax, ay, az, r, vz] (Achse quer zum Rohr in Richtung (ux, uy) durch
    (ax, ay, az), vz = +1 obere bzw. −1 untere Hälfte). Die Schnittfläche über einem Punkt ist das Minimum bzw. Maximum
    der Flächen ('huelle'); gewählt wird, was die gemessene Schnittkontur (Kanten zur Außenwand) innerhalb tol trifft.
    Ergebnis dict(flaechen, huelle) oder None (andere Flächen, längs liegende Ebenen, keine Hülle passt)."""
    r = math.radians(ref)
    cr, sr = math.cos(r), math.sin(r)

    def dreh(x, y):
        return x * cr + y * sr, -x * sr + y * cr
    out = []
    for f in flaechen:
        sf = BRepAdaptor_Surface(TopoDS.Face(f))
        pl = _ebene(f)
        if pl is not None:
            d, p0 = pl.Axis().Direction(), pl.Location()
            n = (d.X(), d.Y(), d.Z()) if d.Z() >= 0 else (-d.X(), -d.Y(), -d.Z())
            if n[2] < 0.1:          # Ebene längs zum Rohr: keine Höhe über dem Querschnitt
                return None
            nx, ny = dreh(n[0], n[1])
            px, py = dreh(p0.X() - cx, p0.Y() - cy)
            gx, gy = -nx / n[2], -ny / n[2]
            e = ["E", round(gx, 6), round(gy, 6), round(p0.Z() - z_ref - gx * px - gy * py, 4)]
            if not any(all(abs(a - b) < 1e-4 for a, b in zip(e[1:], x[1:])) for x in out if x[0] == "E"):
                out.append(e)
        elif sf.GetType() == GeomAbs_Cylinder:
            zyl = sf.Cylinder()
            ax = zyl.Axis()
            d, l0 = ax.Direction(), ax.Location()
            if abs(d.Z()) > 1e-3:   # Achse nicht quer zum Rohr
                return None
            ux, uy = dreh(d.X(), d.Y())
            lg = math.hypot(ux, uy)
            ux, uy = ux / lg, uy / lg
            axx, ayy = dreh(l0.X() - cx, l0.Y() - cy)
            az = l0.Z() - z_ref
            u0, u1, v0, v1 = sf.FirstUParameter(), sf.LastUParameter(), sf.FirstVParameter(), sf.LastVParameter()
            pm = sf.Value((u0 + u1) / 2, (v0 + v1) / 2)
            vz = 1 if pm.Z() - z_ref >= az else -1
            e = ["Z", round(ux, 6), round(uy, 6), round(axx, 4), round(ayy, 4), round(az, 4), round(zyl.Radius(), 4),
                 vz]
            if e not in out:
                out.append(e)
        else:
            return None
    if not out:
        return None

    def hoehe(f, x, y):
        if f[0] == "E":
            return f[3] + f[1] * x + f[2] * y
        _, ux, uy, ax_, ay_, az_, rr, vz_ = f
        q = -(x - ax_) * uy + (y - ay_) * ux
        return None if abs(q) > rr + 1e-6 else az_ + vz_ * math.sqrt(max(rr * rr - q * q, 0.0))
    pts = []
    for p in _punkte_kanten(kanten, 1.0):
        x, y = dreh(p.X() - cx, p.Y() - cy)
        pts.append((x, y, p.Z() - z_ref))
    beste = None
    for huelle, wahl in (("min", min), ("max", max)):
        fehler = 0.0
        for x, y, z in pts:
            h = [v for v in (hoehe(f, x, y) for f in out) if v is not None]
            fehler = max(fehler, abs(wahl(h) - z) if h else math.inf)
        if fehler <= tol and (beste is None or fehler < beste[0]):
            beste = (fehler, huelle)
    return dict(flaechen=out, huelle=beste[1]) if beste else None


def _endform(flaechen, laenge, ref=0.0, ende="B"):
    """Form eines Endes aus seinen Schnittflächen: gerade, Gehrung (Neigung um eine Querachse), Schrägschnitt zwei-
    achsig oder komplex (mehrere Ebenen, gekrümmt: Ausklinkung, Sattel …). Winkel in Grad gegen den geraden Schnitt:
    gehrung = Gesamtneigung, um_x = Neigung zur 0°-Richtung hin (Drehung um die Querachse 270°–90°), um_y = Neigung
    zur 270°-Richtung hin (Drehung um die Querachse 0°–180°). ref: Bezugsrichtung 0° (siehe _bezug).
    richtung (nur ebene schräge Enden): Umfangswinkel (Zählung wie _Abwicklung.theta: von Ende A gesehen 0° oben,
    90° rechts), in dem das Teil an diesem Ende am längsten ist; ende = 'A' oder 'B'."""
    normalen = []
    for f in flaechen:
        pl = _ebene(f)
        if pl is None:
            return dict(form="komplex", gehrung=None, um_x=None, um_y=None, richtung=None,
                        schnittlaenge=round(laenge, 2))
        d = pl.Axis().Direction()
        n = (d.X(), d.Y(), d.Z()) if d.Z() >= 0 else (-d.X(), -d.Y(), -d.Z())
        if not any(sum(a * b for a, b in zip(n, m)) > 1 - 1e-6 for m in normalen):
            normalen.append(n)
    if len(normalen) != 1:
        return dict(form="komplex", gehrung=None, um_x=None, um_y=None, richtung=None,
                    schnittlaenge=round(laenge, 2))
    nx0, ny0, nz = normalen[0]
    r = math.radians(ref)      # Querachsen so drehen, dass Y in die 0°-Richtung zeigt
    nx, ny = nx0 * math.cos(r) + ny0 * math.sin(r), -nx0 * math.sin(r) + ny0 * math.cos(r)
    ges = math.degrees(math.acos(min(1.0, nz)))
    um_x, um_y = math.degrees(math.atan2(abs(ny), nz)), math.degrees(math.atan2(abs(nx), nz))
    form = "gerade" if ges < 0.05 else "Gehrung" if min(um_x, um_y) < 0.05 else "Schrägschnitt zweiachsig"
    # Ebene z = c − (nx·x + ny·y) / nz: Ende B ist in Richtung −(nx, ny) am längsten, Ende A in Richtung +(nx, ny)
    richtung = None
    if form != "gerade":
        dx, dy = (-nx0, -ny0) if ende == "B" else (nx0, ny0)
        richtung = round((math.degrees(math.atan2(-dx, dy)) - ref) % 360, 1) % 360
    return dict(form=form, gehrung=round(ges, 2), um_x=round(um_x, 2), um_y=round(um_y, 2), richtung=richtung,
                schnittlaenge=round(laenge, 2))


def _offen_auswerten(t, lok, aussen, passend, x0, y0, x1, y1, zmin, netz):
    """Profil mit einer Kontur im Querschnitt (U, C, L, Flach-, Vierkant-, Rundstahl): Form, Maße, Wandstärken.
    Konturen werden bei diesen Profilen noch nicht ausgewertet (sie werden auch noch nicht kalkuliert)."""
    messungen = []
    for z, wsz in passend:
        messungen += _wand_messungen(wsz, False, z - zmin)
    werte = sorted(m[3] for m in messungen)
    wand = werte[len(werte) // 2] if werte else 0.0
    seiten = {}
    for m in messungen:
        seiten.setdefault(m[4][0], []).append(m[3])
    je_seite = {k: sorted(v)[len(v) // 2] for k, v in seiten.items()}
    erg = _offenes_profil(aussen, t.flaeche, x0, y0, x1, y1, je_seite)
    if erg is None:
        t.profilform, t.abm_a, t.abm_b = "offenes Sonderprofil", max(x1 - x0, y1 - y0), min(x1 - x0, y1 - y0)
        t.hinweise.append("Offenes Profil nicht erkannt, Fläche manuell prüfen")
        t.sicherheit["profil"] = "unsicher"
    else:
        t.profilform, t.abm_a, t.abm_b, bemerkung = erg[:4]
        zusatz = erg[4] if len(erg) > 4 else {}
        t.sicherheit["profil"] = "sicher"
        if bemerkung:
            t.hinweise.append(bemerkung)
        if zusatz:
            t.stegdicke, t.flanschdicke = zusatz["stegdicke"], zusatz["flanschdicke"]
            t.symmetrisch, t.radius = zusatz["symmetrisch"], zusatz["radius"]
    if t.profilform in ("Flachstahl", "Vierkantstahl", "Rundstahl"):
        t.wandstaerke = 0.0          # Vollprofil: keine Wand
        t.sicherheit["wandstaerke"] = "sicher"
    elif werte:
        t.wand_messungen = messungen
        if max(werte) - min(werte) <= TOL_WAND_GLEICH:
            t.wandstaerke = wand
            t.sicherheit["wandstaerke"] = "sicher" if len(werte) >= 4 else "wahrscheinlich"
        elif all(max(v) - min(v) <= TOL_WAND_GLEICH for v in seiten.values()):
            t.wandstaerke = min(je_seite.values())    # z. B. Steg und Flansch verschieden dick
            t.sicherheit["wandstaerke"] = "wahrscheinlich"
            t.hinweise.append("Wandstärken verschieden: " + ", ".join(
                f"{'senkrecht' if k == 'x' else 'waagerecht'} {v:.2f} mm" for k, v in sorted(je_seite.items())))
        else:
            t.wandstaerke = min(werte)
            t.sicherheit["wandstaerke"] = "unsicher"
            t.hinweise.append(f"Wandstärke nicht einheitlich: {min(werte):.2f} bis {max(werte):.2f} mm")
    if t.profilform in TRAEGER:
        # Steg und Flansch sind bei Trägern verschieden dick: Wandstärke = Stegdicke, Flanschdicke eigenes Feld
        t.hinweise = [h for h in t.hinweise if not h.startswith("Wandstärke")]
        t.wandstaerke = t.stegdicke
        t.sicherheit["wandstaerke"] = "sicher"
    if t.profilform in ("U-Profil", "L-Profil") + TRAEGER:
        tf = t.flanschdicke or t.wandstaerke
        if t.profilform == "U-Profil" and len(je_seite) == 2:      # Steg dünner als die Flansche (UPN)
            tf = max(je_seite.values())
        t.normprofil = normprofile.zuordnen(t.profilform, t.abm_a, t.abm_b, t.wandstaerke, tf, t.flaeche) or ""
        if t.normprofil and t.profilform == "U-Profil":
            t.stegdicke, t.flanschdicke = t.wandstaerke, tf
            t.hinweise = [h for h in t.hinweise if not h.startswith("Wandstärken verschieden")]
            t.sicherheit["wandstaerke"] = "sicher"
    if t.profilform in OFFEN_KALKULIERT:
        return _offen_konturen(t, lok, aussen, zmin, netz)
    t.sicherheit["konturen"] = "nicht ausgewertet"
    t.hinweise.append(f"{t.profilform}: wird noch nicht kalkuliert, Konturen nicht ausgewertet")
    if netz:
        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(lok, TopAbs_FACE, faces)
        t.netz = dreiecksnetz(lok, faces, {i: "A" for i in range(1, faces.Extent() + 1)}, [], zmin,
                              max(t.abm_a, t.abm_b))
    return t


# Offene Profile, die das Programm kalkuliert (Patrick 20.10.2026: Plan Frage 2 b). Vierkant- und Rundstahl
# (Vollmaterial) und nicht erkannte offene Profile bleiben nur gemeldet.
OFFEN_KALKULIERT = ("U-Profil", "C-Profil", "L-Profil", "Flachstahl", "I-/H-Träger", "T-Profil")
TRAEGER = ("I-/H-Träger", "T-Profil")      # seit 20.10.2026 erkannt und kalkuliert (Frage 2 a)


def _normale(face, p):
    """Nach außen zeigende Flächennormale (x, y, z) im Punkt p (auf der Fläche) oder None."""
    from OCP.ShapeAnalysis import ShapeAnalysis_Surface
    from OCP.BRepGProp import BRepGProp_Face
    f = TopoDS.Face(face)
    uv = ShapeAnalysis_Surface(BRep_Tool.Surface_s(f)).ValueOfUV(p, 1e-3)
    q, v = gp_Pnt(), gp_Vec()
    BRepGProp_Face(f).Normal(uv.X(), uv.Y(), q, v)
    m = v.Magnitude()
    return (v.X() / m, v.Y() / m, v.Z() / m) if m > 1e-12 else None


def _offen_konturen(t, lok, aussen, zmin, netz):
    """Schnitte an offenen Profilen (U, C, L, Flachstahl). Profil und Wand liegen auf einer einzigen Kontur; eine
    Fläche, die nicht auf ihr liegt, gehört zu einem Merkmal (Ende, Bohrung, Ausschnitt). Ein Merkmal geht durch,
    wenn es Wandflächen beider Seiten der Wand berührt (Normalen entgegengesetzt), sonst ist es eine Gravur oder
    Sackbohrung. Der Laser schneidet von einer Seite: Schnittlänge = halbe Länge der Kanten zur Wand (oben und
    unten je einmal), Einstiche = halbe Anzahl Konturzüge (aufgerundet). Lage: z ab Ende A und "querlage" = Mitte
    (x, y) im Querschnitt um die Mitte des Hüllrechtecks; dazu steht bei Ende A der Umriss ("querschnitt"). Die
    Fläche (Steg, Flansch, Schenkel) bestimmt das Programm daraus (rohrlaser.step.offen_lage)."""
    zmax = zmin + t.laenge
    s_aussen = _strecken(aussen)
    # Lage im Querschnitt (für die Fläche im Programm): Mitte des Hüllrechtecks, Umriss als Punkte darum
    qx = [v for st in s_aussen for v in (st[0], st[2])]
    qy = [v for st in s_aussen for v in (st[1], st[3])]
    qcx, qcy = (max(qx) + min(qx)) / 2, (max(qy) + min(qy)) / 2
    schritt_q = max(1, len(s_aussen) // 160)
    querschnitt = [[round(st[0] - qcx, 2), round(st[1] - qcy, 2)] for st in s_aussen[::schritt_q]]

    def quer_lage(bb):
        mn, mx = bb.CornerMin(), bb.CornerMax()
        return dict(x=round((mn.X() + mx.X()) / 2 - qcx, 2), y=round((mn.Y() + mx.Y()) / 2 - qcy, 2))
    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(lok, TopAbs_FACE, faces)

    def punkte(face):
        pts = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in _liste(face, TopAbs_VERTEX)]
        for e in _liste(face, TopAbs_EDGE):
            c = BRepAdaptor_Curve(TopoDS.Edge(e))
            for u in (0.25, 0.5, 0.75):
                pts.append(c.Value(c.FirstParameter() + u * (c.LastParameter() - c.FirstParameter())))
        return pts

    art, fl_art = {}, {"A": 0.0, "S": 0.0}
    for i in range(1, faces.Extent() + 1):
        f = faces.FindKey(i)
        # Wandflächen liegen auf der Kontur und laufen längs; eine Stirnfläche hat ihren Rand auch auf der Kontur
        pl = _ebene(f)
        laengs = pl is None or abs(pl.Axis().Direction().Z()) < 1e-3
        art[i] = "A" if laengs and all(_nah_zug(p.X(), p.Y(), s_aussen, TOL_WAND) for p in punkte(f)) else "S"
        fl_art[art[i]] += _flaeche(f)
    if fl_art["S"] > fl_art["A"]:
        t.hinweise.append("Erkennung unsicher: Schnittflächen größer als die Profilflächen, Konturen nicht "
                          "ausgewertet. Teil bitte prüfen.")
        t.sicherheit["konturen"] = "unsicher"
        return t
    kf = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(lok, TopAbs_EDGE, TopAbs_FACE, kf)
    vmap = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(lok, TopAbs_VERTEX, vmap)
    eltern = {}

    def finde(x):
        while eltern.setdefault(x, x) != x:
            eltern[x] = eltern[eltern[x]]
            x = eltern[x]
        return x
    kanten_info = []
    for i in range(1, kf.Extent() + 1):
        fi = {faces.FindIndex(f) for f in kf.FindFromIndex(i)}
        kanten_info.append((kf.FindKey(i), fi))
        sf = [f for f in fi if art[f] == "S"]
        for f in sf[1:]:
            eltern[finde(f)] = finde(sf[0])
    merkmale = {}
    for f, a_ in art.items():
        if a_ == "S":
            merkmale.setdefault(finde(f), dict(faces=[], kanten=[], normalen=[]))["faces"].append(f)
    for e, fi in kanten_info:
        s_f = [f for f in fi if art[f] == "S"]
        a_f = [f for f in fi if art[f] == "A"]
        if s_f and a_f:
            m = merkmale[finde(s_f[0])]
            m["kanten"].append(e)
            c = BRepAdaptor_Curve(TopoDS.Edge(e))
            n = _normale(faces.FindKey(a_f[0]), c.Value((c.FirstParameter() + c.LastParameter()) / 2))
            if n:
                m["normalen"].append(n)

    def zuege(kanten):
        ve = {}

        def fv(x):
            while ve.setdefault(x, x) != x:
                ve[x] = ve[ve[x]]
                x = ve[x]
            return x
        for e in kanten:
            vs = [vmap.FindIndex(v) for v in _liste(e, TopAbs_VERTEX)]
            for v in vs:
                ve[fv(v)] = fv(vs[0])
        out = {}
        for e in kanten:
            out.setdefault(fv(vmap.FindIndex(_liste(e, TopAbs_VERTEX)[0])), []).append(e)
        return list(out.values())

    TOL_Z = 0.01
    enden = {"EA": [[], 0.0, []], "EB": [[], 0.0, []]}     # Flächen, Schnittlänge, Kanten je Ende
    liste, bohrungen = [], {}
    for m in merkmale.values():
        kanten = m["kanten"]
        if not kanten:
            continue
        laenge = sum(_kantenlaenge(e) for e in kanten)
        zg = zuege(kanten)
        nm = m["normalen"]
        durch = any(sum(p * q for p, q in zip(a_, b_)) < -0.5 for i, a_ in enumerate(nm) for b_ in nm[i + 1:])
        bb = Bnd_Box()
        for e in kanten:
            BRepBndLib.AddOptimal_s(e, bb, False, False)
        gz0, gz1 = bb.CornerMin().Z(), bb.CornerMax().Z()
        # Rundbohrung: nur Zylinderflächen gleichen Radius quer zur Achse (Sackbohrung: dazu ein ebener/kegeliger
        # Grund)
        radien, andere = set(), False
        for f in m["faces"]:
            fk = faces.FindKey(f)
            z_ = _zylinder(fk)
            if z_ is not None and abs(z_.Axis().Direction().Z()) < 0.99:
                radien.add(round(z_.Radius(), 2))
            elif durch or not (_ebene(fk) is not None or
                               BRepAdaptor_Surface(TopoDS.Face(fk)).GetType() == GeomAbs_Cone):
                andere = True
        rund = (None, round(2 * radien.pop(), 2)) if len(radien) == 1 and not andere else None
        if not durch:
            m["art"] = "G"
            t.gravur += laenge
            t.gravur_konturen += len(zg)
            d = dict(durchgehend=False, z=round((gz0 + gz1) / 2 - zmin, 2), winkel=None, u=None, seite=None,
                     schnittlaenge=round(laenge, 2))
            if rund:
                d.update(art="Sackbohrung", durchmesser=rund[1], hinweis="nicht durchgehend, mit dem Laser nicht "
                         "herstellbar")
                t.hinweise.append(f"Sackbohrung Ø{rund[1]:g} gefunden (nicht laserbar), prüfen")
            else:
                d.update(art="Gravur", hinweis="nicht durchgehend (Markierung/Vertiefung), nicht im Schneidweg")
            liste.append(d)
            continue
        schnitt = laenge / 2
        einstiche = (len(zg) + 1) // 2
        if gz0 - zmin < TOL_Z:
            m["art"] = "EA"
            t.ende_a += schnitt
            t.ende_a_gerade = gz1 - zmin < TOL_Z
        elif zmax - gz1 < TOL_Z:
            m["art"] = "EB"
            t.ende_b += schnitt
            t.ende_b_gerade = zmax - gz0 < TOL_Z
        else:
            m["art"] = "K"
            ba = bohrung_art([faces.FindKey(f) for f in m["faces"]], kanten)
            if ba:      # Senkung bzw. Fließloch (wie bei geschlossenen Rohren, siehe bohrung_art)
                art_, dm, aussen = ba
                d = dict(durchgehend=True, z=round((gz0 + gz1) / 2 - zmin, 2), winkel=None, u=None, seite=None,
                         art=art_, durchmesser=dm, querlage=quer_lage(bb))
                if art_ == "Senkung":
                    schnitt = math.pi * dm
                    t.innen += schnitt
                    t.innen_konturen += 1
                    t.konturen += 1
                    t.innen_liste.append((dm, schnitt))
                    t.senkungen[(dm, aussen)] = t.senkungen.get((dm, aussen), 0) + 1
                    d.update(senk_durchmesser=aussen, schnittlaenge=round(schnitt, 2), huellmass=dm,
                             hinweis="Laser schneidet die Bohrung, Senkung ist Nacharbeit")
                else:
                    t.fliessloecher[dm] = t.fliessloecher.get(dm, 0) + 1
                    d.update(kragen_durchmesser=aussen, schnittlaenge=0.0,
                             hinweis="Fließlochbohrung (Flowdrill): nicht im Schneidweg")
                liste.append(d)
                continue
            t.innen += schnitt
            t.innen_konturen += einstiche
            mn, mx = bb.CornerMin(), bb.CornerMax()
            dz = mx.Z() - mn.Z()
            quer = max(mx.X() - mn.X(), mx.Y() - mn.Y())
            d = dict(durchgehend=True, z=round((gz0 + gz1) / 2 - zmin, 2), winkel=None, u=None, seite=None,
                     schnittlaenge=round(schnitt, 2), querlage=quer_lage(bb))
            if rund:
                bohrungen[rund[1]] = bohrungen.get(rund[1], 0) + 1
                d.update(art="Bohrung", durchmesser=rund[1], huellmass=rund[1])
                t.innen_liste.append((rund[1], schnitt))
            else:
                # Maße in der Wandebene: entlang der Achse (dz) und quer dazu; die Wanddicke steckt mit im Hüllmaß
                d.update(art="Ausschnitt", laenge=round(max(dz, quer), 2), breite=round(min(dz, quer), 2),
                         huellmass=round(max(dz, quer), 2))
                t.innen_liste.append((max(dz, quer), schnitt))
            liste.append(d)
        if m["art"] in enden:
            enden[m["art"]][0] += [faces.FindKey(f) for f in m["faces"]]
            enden[m["art"]][1] += schnitt
            enden[m["art"]][2] += kanten
        t.konturen += einstiche
    kopf = []
    for art_, name, z in (("EA", "Ende A", 0.0), ("EB", "Ende B", t.laenge)):
        fl, lg, kt = enden[art_]
        e = _endform(fl, lg, ende=art_[1]) if fl else dict(form="nicht erkannt", gehrung=None, um_x=None,
                                                         um_y=None, richtung=None, schnittlaenge=0.0)
        e["huellmass"] = _ende_huellmass(_punkte_kanten(kt)) if kt else None
        setattr(t, "ende_a_huelle" if art_ == "EA" else "ende_b_huelle", e["huellmass"] or 0.0)
        kopf.append(dict(art=name, durchgehend=True, z=round(z, 2), winkel=None, u=None, seite=None, **e))
    kopf[0]["querschnitt"] = querschnitt        # Umriss von Ende A aus (x, y um die Mitte), zu "querlage" der Konturen
    t.konturen_liste = kopf + sorted(liste, key=lambda d: d["z"])
    t.bohrungen = dict(sorted(bohrungen.items()))
    t.schneidweg = t.ende_a + t.ende_b + t.innen
    t.sicherheit["konturen"] = "wahrscheinlich" if any(
        d["art"] == "Ausschnitt" or d.get("form") in ("komplex", "nicht erkannt") for d in t.konturen_liste) \
        else "sicher"
    if netz:
        art_flaeche = dict(art)
        for m in merkmale.values():
            for f in m["faces"]:
                art_flaeche[f] = m.get("art", "K")
        t.netz = dreiecksnetz(lok, faces, art_flaeche, [(m.get("art", "K"), m["kanten"]) for m in merkmale.values()],
                              zmin, max(t.abm_a, t.abm_b))
    return t


def _innen_liegend(innen, aussen):
    """True, wenn der Hüllquader von innen in dem von aussen liegt (Hohlprofil). Zwei nebeneinanderliegende
    Konturen (z. B. U-Profil im Schnitt durch eine Stegbohrung) sind kein Hohlprofil."""
    bi, ba = Bnd_Box(), Bnd_Box()
    BRepBndLib.AddOptimal_s(innen, bi, False, False)
    BRepBndLib.AddOptimal_s(aussen, ba, False, False)
    return (ba.CornerMin().X() < bi.CornerMin().X() and bi.CornerMax().X() < ba.CornerMax().X() and
            ba.CornerMin().Y() < bi.CornerMin().Y() and bi.CornerMax().Y() < ba.CornerMax().Y())


def _rp_erkennen(t, bx, by):
    """RP-Profil (Rohr mit Anschlag aus doppeltem Blech) per Fingerabdruck aus der Bibliothek rp_profile.json: Maße,
    Fläche, Konturlänge und Kammern. Trifft eins, bekommt das Teil Form, Profil-ID und Maße der Bibliothek (A = Breite,
    B = Höhe); mehrere gleiche stehen im Hinweis. Ergebnis: Profil-ID oder None."""
    treffer = rp_profile.erkennen(bx, by, t.flaeche, t.kontur_umfang, t.kammern, t.wandstaerke,
                                  rp_profile.bibliothek())
    if not treffer:
        return None
    e = rp_profile.bibliothek()[treffer[0]]
    t.profilform, t.normprofil, t.abm_a, t.abm_b = rp_profile.FORM, treffer[0], e["breite"], e["hoehe"]
    if len(treffer) > 1:
        t.hinweise.append(f"RP-Profil {treffer[0]} erkannt, gleicher Querschnitt: {', '.join(treffer[1:4])} "
                          "(Profil-ID prüfen)")
    return treffer[0]


def _profil_messen(solid, datei="", koerper=1, netz=False, quer=None):
    """Messung als gerades Profil (Rohr, offenes Profil, Flachstahl) mit konstantem Querschnitt. quer: Körper, aus dem
    Lage und Querschnitt kommen (gleiche Lage wie solid, z. B. das geschlossene Rohr zu einem Rohr mit großem
    Fenster, step_offenes_rohr); Konturen und Enden immer aus solid."""
    t = Teil(datei=datei, koerper=koerper)
    ax3, regel = _lage(quer if quer is not None else solid)
    lok = _transformiere(solid, ax3)
    lok_q = _transformiere(quer, ax3) if quer is not None else lok

    zmin, zmax = _z_bereich(lok)
    t.laenge = zmax - zmin
    d, p = ax3.Direction(), _global(ax3, 0, 0, zmin)
    t.achse_global = (d.X(), d.Y(), d.Z())
    t.ende_a_global = (p.X(), p.Y(), p.Z())
    x = ax3.XDirection()
    t.x_global = (x.X(), x.Y(), x.Z())

    # Querschnitt: Lage mit größter Netto-Fläche, zuerst als Hohlprofil (genau 2 Konturen: außen/innen), sonst mit
    # einer Kontur (U, L, C, Flach …). Bis zu 49 Lagen über die ganze Länge, damit auch lange Ausschnitte umgangen
    # werden; krumme Anteile, damit die Ebene nicht genau auf einer Merkmalskante liegt. Von der Mitte nach außen;
    # sobald drei Lagen den größten Querschnitt zeigen, ist er gefunden (ein Schnitt durch ein Merkmal hat weniger
    # Fläche oder mehr Konturen). Die drei Lagen dienen auch als Messstellen der Wandstärke.
    def suche(n_konturen):
        best, passend = None, []
        for anteil in sorted([0.5037] + [(i + 0.37) / 50 for i in range(1, 49)], key=lambda a: abs(a - 0.5037)):
            z = zmin + anteil * t.laenge
            ws = _schnitt(lok_q, z)
            if len(ws) != n_konturen or n_konturen >= 2 and not all(_innen_liegend(w[1], ws[0][1]) for w in ws[1:]):
                continue
            netto = ws[0][0] - sum(w[0] for w in ws[1:])
            if best is None or netto > best[0] * 1.001:
                best, passend = (netto, z, ws), [(z, ws)]
            elif netto >= best[0] * 0.999:
                passend.append((z, ws))
            if len(passend) >= 3:
                break
        return best, passend

    t.sicherheit["achse"] = t.sicherheit["laenge"] = \
        "sicher" if len(regel) >= 3 else "wahrscheinlich" if len(regel) == 2 else "unsicher"
    best, passend = suche(2)
    for n in range(3, 7):           # Mehrkammerprofil: mehrere Innenkonturen in der Außenkontur
        if best is not None:
            break
        best, passend = suche(n)
    hohl = best is not None
    if not hohl:
        best, passend = suche(1)
    if best is None:
        t.hinweise.append("Kein Profilquerschnitt gefunden (Querschnitt nicht über die Länge gleich?)")
        t.sicherheit.update(achse="unsicher", laenge="unsicher", profil="unsicher")
        return t
    t.flaeche, z0, ws = best
    aussen = ws[0][1]
    wb = Bnd_Box()
    BRepBndLib.AddOptimal_s(aussen, wb, False, False)
    x0, y0, x1, y1 = wb.CornerMin().X(), wb.CornerMin().Y(), wb.CornerMax().X(), wb.CornerMax().Y()
    bx, by = x1 - x0, y1 - y0
    a, b = max(bx, by), min(bx, by)

    if not hohl:
        return _offen_auswerten(t, lok, aussen, passend, x0, y0, x1, y1, zmin, netz)

    innen = ws[1][1]
    s_aussen, s_innen = _strecken(aussen), [s for w in ws[1:] for s in _strecken(w[1])]
    t.wandstaerke = min(_wandstaerke(aussen, w[1], s_aussen, _strecken(w[1]), z0) for w in ws[1:])
    t.kammern = len(ws) - 1
    t.kontur_umfang = _draht_laenge(aussen)
    innen_umfang = sum(_draht_laenge(w[1]) for w in ws[1:])
    ib = Bnd_Box()
    BRepBndLib.AddOptimal_s(innen, ib, False, False)
    ia, ibb = ib.CornerMax().X() - ib.CornerMin().X(), ib.CornerMax().Y() - ib.CornerMin().Y()

    # Profilform aus der Außenkontur (Ecken/Kreise können je nach CAD als Kreis, Ellipse, Spline oder Freiform-
    # kurve kommen, darum geometrisch statt über Kurventypen)
    form = _profilform(aussen, bx, by) if t.kammern == 1 else "Mehrkammer"
    t.sicherheit["profil"] = "sicher"
    rp = _rp_erkennen(t, bx, by) if form not in ("Kreis", "Rechteck") else None
    if rp:
        pass
    elif form == "Kreis" and a - b < 0.1:
        t.profilform, t.abm_a, t.innen_a = "Rundrohr", (a + b) / 2, (ia + ibb) / 2
    elif form == "Rechteck" and a - b < 0.1:
        t.profilform, t.abm_a, t.innen_a, t.innen_b = "Quadratrohr", (a + b) / 2, max(ia, ibb), min(ia, ibb)
    elif form == "Rechteck":
        t.profilform, t.abm_a, t.abm_b, t.innen_a, t.innen_b = "Rechteckrohr", a, b, max(ia, ibb), min(ia, ibb)
    else:
        t.profilform, t.abm_a, t.abm_b, t.innen_a, t.innen_b = "Sonderprofil", a, b, max(ia, ibb), min(ia, ibb)
        t.hinweise.append(f"Mehrkammerprofil ({t.kammern} Kammern): Profil nicht erkannt, Fläche manuell prüfen"
                          if t.kammern > 1 else "Profil nicht erkannt, Fläche manuell prüfen")
        t.sicherheit["profil"] = "unsicher"

    # Wandstärke an mehreren Stellen (je Querschnittslage mehrere Messstellen) und Gegenprobe
    for z, wsz in passend:
        t.wand_messungen += _wand_messungen(wsz, form == "Kreis", z - zmin)
    werte = [m[3] for m in t.wand_messungen] + [t.wandstaerke]
    if rp:      # RP-Profil: am Anschlag liegt das Blech doppelt (2 × Wand), das ist keine ungleiche Wand
        werte = [w for w in werte if abs(w - 2 * t.wandstaerke) > TOL_WAND_GLEICH] or [t.wandstaerke]
    if max(werte) - min(werte) > TOL_WAND_GLEICH:
        t.sicherheit["wandstaerke"] = "unsicher"
        t.hinweise.append(f"Wandstärke nicht einheitlich: {min(werte):.2f} bis {max(werte):.2f} mm an "
                          f"{len(werte)} Messstellen, Profil prüfen")
    else:
        t.sicherheit["wandstaerke"] = "sicher" if len(t.wand_messungen) >= 4 else "wahrscheinlich"

    # Wandflächen bestimmen: alle Punkte der Fläche liegen (in Z projiziert) auf Außen- bzw. Innenkontur
    def punkte(face):
        pts = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in _liste(face, TopAbs_VERTEX)]
        for e in _liste(face, TopAbs_EDGE):
            c = BRepAdaptor_Curve(TopoDS.Edge(e))
            for u in (0.25, 0.5, 0.75):
                pts.append(c.Value(c.FirstParameter() + u * (c.LastParameter() - c.FirstParameter())))
        return pts

    def auf(pts, strecken):
        return all(_nah_zug(p.X(), p.Y(), strecken, TOL_WAND) for p in pts)

    faces = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(lok, TopAbs_FACE, faces)
    art = {}   # Index -> "A" außen, "I" innen, "S" Schnitt
    flaeche_art = {"A": 0.0, "I": 0.0, "S": 0.0}
    verdacht, wand_z = False, (math.inf, -math.inf)
    for i in range(1, faces.Extent() + 1):
        f = faces.FindKey(i)
        pts = punkte(f)
        if auf(pts, s_aussen):
            art[i] = "A"
        elif auf(pts, s_innen):
            art[i] = "I"
        else:
            art[i] = "S"
            # Anbauteil-Verdacht: Merkmalsfläche ragt über die Außenkontur hinaus (Bearbeitungen liegen immer innerhalb;
            # y minimal versetzt, damit der Strahl der Innenprüfung nicht genau durch Teilungspunkte der Kontur läuft)
            verdacht = verdacht or any(not _im_material(p.X(), p.Y() + 1.37e-6, s_aussen) and
                                       _abstand_zug(p.X(), p.Y(), s_aussen) > TOL_WAND for p in pts)
        if art[i] != "S":
            b_ = Bnd_Box()
            BRepBndLib.AddOptimal_s(f, b_, False, False)
            wand_z = (min(wand_z[0], b_.CornerMin().Z()), max(wand_z[1], b_.CornerMax().Z()))
        flaeche_art[art[i]] += _flaeche(f)
    # … oder Material jenseits der Wandflächen (Kopfplatte) oder eine eingebuchtete Außenkontur (Schnitt durch ein
    # Anbauteil); dann versucht analysiere die Trennung (_getrennt_messen)
    t._anbau_verdacht = verdacht or wand_z[0] - zmin > 0.01 or zmax - wand_z[1] > 0.01 or \
        ws[0][0] < 0.98 * _huellflaeche(s_aussen)
    # Gegenprobe: Schnitt- und Merkmalsflächen sind bei einem Rohrteil viel kleiner als der Außenmantel. Sonst ist
    # die Lage falsch erkannt (z. B. der Mantel als Schnittkontur) – dann lieber keine Maße als falsche.
    if flaeche_art["S"] > flaeche_art["A"]:
        u = Teil(datei=datei, koerper=koerper)
        u.hinweise.append("Erkennung unsicher: Schnittflächen größer als der Außenmantel, keine Maße übernommen. "
                          "Teil bitte prüfen.")
        return u

    kf = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(lok, TopAbs_EDGE, TopAbs_FACE, kf)
    vmap = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(lok, TopAbs_VERTEX, vmap)

    # Merkmale = zusammenhängende Schnittflächen (über gemeinsame Kanten)
    eltern = {}

    def finde(x):
        while eltern.setdefault(x, x) != x:
            eltern[x] = eltern[eltern[x]]
            x = eltern[x]
        return x

    kanten_info = []   # (Kante, Menge Flächenindizes)
    for i in range(1, kf.Extent() + 1):
        fi = {faces.FindIndex(f) for f in kf.FindFromIndex(i)}
        kanten_info.append((kf.FindKey(i), fi))
        s_faces = [f for f in fi if art[f] == "S"]
        for f in s_faces:
            finde(f)
            if f != s_faces[0]:
                eltern[finde(f)] = finde(s_faces[0])

    merkmale = {}  # Wurzel -> dict(faces, aussenkanten, durch)
    for f, a_ in art.items():
        if a_ == "S":
            merkmale.setdefault(finde(f), dict(faces=[], kanten=[], durch=False))["faces"].append(f)
    for e, fi in kanten_info:
        arten = {art[f] for f in fi}
        for f in fi:
            if art[f] == "S":
                m = merkmale[finde(f)]
                if "A" in arten:
                    m["kanten"].append(e)
                if "I" in arten:
                    m["durch"] = True

    def konturzuege(kanten):
        """Kanten zu geschlossenen Konturzügen gruppieren (über gemeinsame Eckpunkte)."""
        ve = {}

        def fv(x):
            while ve.setdefault(x, x) != x:
                ve[x] = ve[ve[x]]
                x = ve[x]
            return x
        for e in kanten:
            vs = [vmap.FindIndex(v) for v in _liste(e, TopAbs_VERTEX)]
            for v in vs:
                ve[fv(v)] = fv(vs[0])
        zuege = {}
        for e in kanten:
            zuege.setdefault(fv(vmap.FindIndex(_liste(e, TopAbs_VERTEX)[0])), []).append(e)
        return list(zuege.values())

    def konturen_zaehlen(kanten):
        return len(konturzuege(kanten))

    TOL_Z = 0.01
    bohrungen = {}
    ref = _bezug(ax3, t.profilform)
    abw = _Abwicklung(s_aussen, ref)
    kasten = t.profilform in ("Quadratrohr", "Rechteckrohr")
    hx, hy = bx / 2, by / 2
    enden = {"EA": [[], 0.0, []], "EB": [[], 0.0, []]}     # Flächen, Schnittlänge und Kanten je Ende
    fasen = {}              # Ende ('A'/'B') mit Fase -> Außenkontur gerade (senkrecht zur Achse)
    liste = []

    def lage_auf_rohr(zug):
        """Abgewickelte Kontur -> Form, Maße, Mitte (z ab Ende A, Winkel, Seite), Normale der Wand dort."""
        uv = [(abw.u(p.X(), p.Y()), p.Z() - zmin) for p in _punkte_kanten(zug)]
        if max(u for u, _ in uv) - min(u for u, _ in uv) > abw.umfang / 2:     # über die 0°-Naht
            uv = [(u + abw.umfang if u < abw.umfang / 2 else u, v) for u, v in uv]
        form, (uc, vc), lage = _form_2d(uv)
        winkel, px, py = abw.punkt(uc)
        seite = None
        if kasten:
            dx, dy = px - abw.cx, py - abw.cy
            if abs(abs(dx) - hx) < 0.05 or abs(abs(dy) - hy) < 0.05:
                seite = f"{round(winkel / 90) % 4 * 90}°"
            else:
                seite = "Ecke"
        (wa, ax_, ay_), (wb, bx_, by_) = abw.punkt(uc - 0.5), abw.punkt(uc + 0.5)
        tl = math.hypot(bx_ - ax_, by_ - ay_) or 1.0
        tx, ty = (bx_ - ax_) / tl, (by_ - ay_) / tl
        if (wb - wa + 180) % 360 - 180 < 0:         # Tangente in Richtung steigender Umfangswinkel (quer +)
            tx, ty = -tx, -ty
        nx, ny = ty, -tx
        if nx * (px - abw.cx) + ny * (py - abw.cy) < 0:     # Normale nach außen
            nx, ny = -nx, -ny
        normale = (nx, ny, tx, ty)
        u = uc % abw.umfang
        d = dict(z=round(vc, 2), winkel=round(winkel % 360, 1) % 360,
                 u=round(0.0 if abw.umfang - u < 0.005 else u, 2), seite=seite)
        um = _umriss_uv(zug, abw, zmin, d["u"])
        if um:
            d["umriss"] = um
            if kasten:
                d["waende"] = waende(um)
        return form, lage, d, normale

    def waende(um):
        """Wände (Seiten wie 'seite', z. B. '0°', '90°'), die eine abgewickelte Kontur berührt; Ecken zählen nicht."""
        out, us = [], []
        for (u0, _), (u1, _) in zip(um, um[1:] + um[:1]):     # auch zwischen den Eckpunkten des Umrisses
            n = max(1, int(abs(u1 - u0)))
            us += [u0 + (u1 - u0) * i / n for i in range(n)]
        for u in us:
            _, x, y = abw.punkt(u)
            dx, dy = x - abw.cx, y - abw.cy
            if abs(abs(dy) - hy) < 0.05:
                mx, my = abw.cx, abw.cy + math.copysign(hy, dy)
            elif abs(abs(dx) - hx) < 0.05:
                mx, my = abw.cx + math.copysign(hx, dx), abw.cy
            else:
                continue
            s = f"{round(abw.theta(mx, my) / 90) % 4 * 90}°"
            if s not in out:
                out.append(s)
        return out

    def tiefe(fl):
        """Größte Tiefe eines nicht durchgehenden Merkmals unter der Außenhaut [mm] (Abstand seiner Eckpunkte von
        der Außenkontur im Querschnitt)."""
        return max((_abstand_zug(p.X(), p.Y(), s_aussen) for f in fl
                    for p in _punkte_kanten(_liste(faces.FindKey(f), TopAbs_EDGE), 1.0)), default=0.0)

    def zylinder_einheitlich(fl, mit_boden=False):
        """(gp_Cylinder, Ø), wenn alle Flächen Zylinder gleichen Radius quer zum Rohr sind (bei mit_boden dürfen
        ebene oder kegelige Bohrungsgründe dazukommen), sonst None."""
        zyl, radien = None, set()
        for f in fl:
            z_ = _zylinder(faces.FindKey(f))
            if z_ is None:
                if mit_boden and _ebene(faces.FindKey(f)) is not None or mit_boden and \
                        BRepAdaptor_Surface(TopoDS.Face(faces.FindKey(f))).GetType() == GeomAbs_Cone:
                    continue
                return None
            if abs(z_.Axis().Direction().Z()) > 0.99:
                return None
            zyl = z_
            radien.add(round(z_.Radius(), 2))
        return (zyl, round(2 * radien.pop(), 2)) if zyl is not None and len(radien) == 1 else None

    def rund_2d(dm, sonst):
        """Bohrung im Rundrohr beim 2D-Schnitt (Strahl zur Rohrmitte): Schnittlänge auf der Außenhaut, innen Ø dm
        (dreid.bohrung_2d_rundrohr, STEP-JSON 1.11); andere Profile oder unpassende Maße: sonst."""
        if t.profilform != "Rundrohr":
            return sonst
        return dreid.bohrung_2d_rundrohr(dm, t.abm_a, t.wandstaerke) or sonst

    def schraeg(zyl, normale):
        dz = zyl.Axis().Direction()
        c = abs(dz.X() * normale[0] + dz.Y() * normale[1])
        return round(math.degrees(math.acos(min(1.0, c))), 2)

    def neigung(zyl, normale):
        """Neigung der Bohrungsachse gegen die Wandnormale (3D-Schnittbearbeitung, Schema 1.5): längs (+ Richtung
        Ende B) und quer (+ Richtung steigender Umfangswinkel, von Ende A gesehen im Uhrzeigersinn) in Grad, als
        Winkel der Projektion (tan² gesamt = tan² längs + tan² quer)."""
        dz = zyl.Axis().Direction()
        n = dz.X() * normale[0] + dz.Y() * normale[1]
        q = dz.X() * normale[2] + dz.Y() * normale[3]
        z = dz.Z()
        if n < 0:                                   # Achse nach außen
            n, q, z = -n, -q, -z
        if n < 1e-9:
            return None, None
        return round(math.degrees(math.atan2(z, n)), 2) + 0.0, round(math.degrees(math.atan2(q, n)), 2) + 0.0

    def bohrung_sonder(ba, kanten):
        """Senkung: der Laser schneidet die Bohrung (π × Ø), Senken ist Nacharbeit; Fließloch: der Laser schneidet
        nichts (Loch formt das Fließbohrwerkzeug), im Programm wählbar als kleines Loch oder Gravur."""
        art_, dm, aussen = ba
        form, lage, d, normale = lage_auf_rohr(kanten)
        d.update(durchgehend=True, art=art_, durchmesser=dm)
        if art_ == "Senkung":
            schnitt = rund_2d(dm, math.pi * dm)
            t.innen += schnitt
            t.innen_konturen += 1
            t.konturen += 1
            t.innen_liste.append((dm, schnitt))
            t.senkungen[(dm, aussen)] = t.senkungen.get((dm, aussen), 0) + 1
            d.update(senk_durchmesser=aussen, schnittlaenge=round(schnitt, 2), huellmass=dm,
                     hinweis="Laser schneidet die Bohrung, Senkung ist Nacharbeit")
        else:
            t.fliessloecher[dm] = t.fliessloecher.get(dm, 0) + 1
            d.update(kragen_durchmesser=aussen, schnittlaenge=0.0,
                     hinweis="Fließlochbohrung (Flowdrill): nicht im Schneidweg")
        liste.append(d)

    for m in merkmale.values():
        kanten = m["kanten"]
        if not kanten:
            liste.append(dict(art="Innenmerkmal", durchgehend=False, z=None, winkel=None, u=None, seite=None,
                              schnittlaenge=0.0, hinweis="nur auf der Innenseite, von außen nicht sichtbar"))
            t.hinweise.append("Merkmal nur auf der Innenseite gefunden, nicht gerechnet")
            continue
        laenge = sum(_kantenlaenge(e) for e in kanten)
        n = konturen_zaehlen(kanten)
        if not m["durch"]:
            m["art"] = "G"
            t.gravur += laenge
            t.gravur_konturen += n
            sack = zylinder_einheitlich(m["faces"], mit_boden=True)
            tief = round(tiefe(m["faces"]), 2)
            if sack and tief <= GRAVUR_TIEFE:      # flache runde Prägung: Gravur, keine Sackbohrung
                sack = None
            for zug in konturzuege(kanten):
                form, lage, d, normale = lage_auf_rohr(zug)
                if sack:
                    d.update(art="Sackbohrung", durchgehend=False, durchmesser=sack[1], schraeg=schraeg(sack[0], normale),
                             tiefe=tief, hinweis="nicht durchgehend, mit dem Laser nicht herstellbar")
                else:
                    d.update(art="Gravur", durchgehend=False, laenge=round(form[1], 2), breite=round(form[2], 2),
                             tiefe=tief, hinweis="nicht durchgehend (Markierung/Vertiefung), nicht im Schneidweg")
                    if form[0] == "Kreis":
                        d.update(breite=round(form[1], 2), durchmesser=round(form[1], 2))
                d["schnittlaenge"] = round(sum(_kantenlaenge(e) for e in zug), 2)
                liste.append(d)
            if sack:
                t.hinweise.append(f"Sackbohrung Ø{sack[1]:g} gefunden (nicht laserbar), prüfen")
            continue
        bb = Bnd_Box()
        for e in kanten:
            BRepBndLib.AddOptimal_s(e, bb, False, False)
        gz0, gz1 = bb.CornerMin().Z(), bb.CornerMax().Z()
        m["art"] = "EA" if gz0 - zmin < TOL_Z else "EB" if zmax - gz1 < TOL_Z else "K"
        fase = _fase_ende([faces.FindKey(f) for f in m["faces"]], zmin, zmax, gz0, gz1) if m["art"] == "K" else None
        if fase:
            # Fase am Ende (Patrick 22.10.2026): wird nicht gelasert; der Laser schneidet an der längsten Stelle,
            # Schnittlänge = Außenkontur, an der die Fase beginnt, Länge = längste Länge des Teils
            m["art"] = "E" + fase
            fasen[fase] = gz1 - gz0 < TOL_Z
            if fase == "A":
                t.ende_a += laenge
                t.ende_a_gerade = fasen[fase] and t.ende_a == laenge
            else:
                t.ende_b += laenge
                t.ende_b_gerade = fasen[fase] and t.ende_b == laenge
        elif gz0 - zmin < TOL_Z:
            t.ende_a += laenge
            t.ende_a_gerade = (gz1 - zmin < TOL_Z) if t.ende_a == laenge else False
        elif zmax - gz1 < TOL_Z:
            t.ende_b += laenge
            t.ende_b_gerade = (zmax - gz0 < TOL_Z) if t.ende_b == laenge else False
        else:
            ba = bohrung_art([faces.FindKey(f) for f in m["faces"]], kanten)
            if ba:
                bohrung_sonder(ba, kanten)
                continue
            t.innen += laenge
            t.innen_konturen += n
            # Rundbohrung: nur Zylinderflächen gleichen Radius, Achse quer zum Rohr
            rund = zylinder_einheitlich(m["faces"])
            if rund:
                d = rund[1]
                bohrungen[d] = bohrungen.get(d, 0) + n
            for zug in konturzuege(kanten):
                form, lage, d, normale = lage_auf_rohr(zug)
                # Hüllmaß für die Konturklasse: Bohrung = Ø, sonst größte Seite des kleinsten (gedrehten) Rechtecks
                # um die abgewickelte Kontur. So zählen schräge Langlöcher und Schlitze um ein Rundrohr mit ihrer
                # wahren Länge (der achsparallele Hüllquader wäre kleiner).
                groesse = rund[1] if rund else max(form[1:])
                schnitt = sum(_kantenlaenge(e) for e in zug)
                sr = schraeg(rund[0], normale) if rund else None
                if rund and sr < SCHRAEG_3D:          # 2D im Rundrohr: außen breiter als die Konstruktion
                    neu_ = rund_2d(rund[1], schnitt)
                    t.innen += neu_ - schnitt
                    schnitt = neu_
                t.innen_liste.append((groesse, schnitt))
                d.update(durchgehend=True, schnittlaenge=round(schnitt, 2), huellmass=round(groesse, 2))
                if len(d.get("waende") or ()) > 1 or form[0] == "Ausschnitt" and not rund:
                    # über mehrere Wände oder keine Grundform (Patrick 23.10.2026): Sonderkontur mit Umriss
                    d.update(art="Sonderkontur", laenge=round(form[1], 2), breite=round(form[2], 2))
                elif rund:
                    d.update(art="Bohrung", durchmesser=rund[1], schraeg=sr)
                    if d["schraeg"] >= SCHRAEG_3D:
                        d["neigung_l"], d["neigung_q"] = neigung(rund[0], normale)
                    ax = rund[0].Axis()
                    d["_achse"] = (ax.Location(), ax.Direction())
                elif form[0] == "Kreis":
                    d.update(art="Bohrung", durchmesser=round(form[1], 2))
                elif form[0] == "Langloch":
                    d.update(art="Langloch", laenge=round(form[1], 2), breite=round(form[2], 2),
                             richtung=round(lage, 1))
                elif form[0] == "Rechteck":
                    d.update(art="Rechteckausschnitt", laenge=round(form[1], 2), breite=round(form[2], 2),
                             richtung=round(lage, 1))
                if not rund or d["art"] == "Sonderkontur":  # Bohrungen: Neigung der Achse (oben); sonst Flächen
                    d["schwenk"] = schwenk([faces.FindKey(f) for f in m["faces"]], zug, abw)
                liste.append(d)
        if m["art"] in enden:
            enden[m["art"]][0] += [faces.FindKey(f) for f in m["faces"]]
            enden[m["art"]][1] += laenge
            enden[m["art"]][2] += kanten
        t.konturen += n
    # gegenüberliegende Bohrungen (gleiche Achse, gleicher Ø): eine Bohrung durch beide Wände
    bo = [d for d in liste if d.get("_achse")]
    for i, a_ in enumerate(bo):
        for b_ in bo[i + 1:]:
            (pa, da), (pb, db) = a_["_achse"], b_["_achse"]
            if a_["durchmesser"] == b_["durchmesser"] and abs(abs(da.Dot(db)) - 1) < 1e-6 and \
                    gp_Vec(pa, pb).Crossed(_vec(da)).Magnitude() < 0.01:
                a_["gegenueber"], b_["gegenueber"] = True, True
    for d in liste:
        d.pop("_achse", None)
    kopf = []
    for art_, name, z in (("EA", "Ende A", 0.0), ("EB", "Ende B", t.laenge)):
        fl, lg, kt = enden[art_]
        e = _endform(fl, lg, ref, art_[1]) if fl else dict(form="nicht erkannt", gehrung=None, um_x=None,
                                                          um_y=None, richtung=None, schnittlaenge=0.0)
        if art_[1] in fasen:
            gerade = fasen[art_[1]] and abs(lg - enden[art_][1]) < 1e-9
            e.update(form="gerade" if gerade else "komplex", gehrung=0.0 if gerade else None,
                     um_x=0.0 if gerade else None, um_y=0.0 if gerade else None, richtung=None, fase=True,
                     hinweis="Fase: nicht gelasert, Schnitt an der längsten Stelle")
            t.hinweise.append(f"{name}: {FASE_HINWEIS}, wird nicht gelasert; Länge und Schneidweg an der längsten "
                              "Stelle angenommen")


        if e["form"] == "komplex" and kt:
            e.update(_ende_flaechen(fl, kt, abw.cx, abw.cy, ref, zmin + z) or {})
            um = _umriss_uv(kt, abw, zmin)      # z. B. Ausklinkung am Ende: echter Umriss für die Darstellung
            if um:
                e["umriss"] = um
        if fl and kt and art_[1] not in fasen:
            e["schwenk"] = schwenk(fl, kt, abw)
        e["huellmass"] = _ende_huellmass(_punkte_kanten(kt)) if kt else None
        setattr(t, "ende_a_huelle" if art_ == "EA" else "ende_b_huelle", e["huellmass"] or 0.0)
        kopf.append(dict(art=name, durchgehend=True, z=round(z, 2), winkel=None, u=None, seite=None, **e))
    t.konturen_liste = kopf + sorted(liste, key=lambda d: (d["z"] is None, d["z"] or 0, d["winkel"] or 0))
    # für die Anbauteile (_anbau_beschreiben): Abwicklung und Außenkontur im System ab Ende A (XY wie lok, z − zmin)
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(0, 0, -z0))
    t._rahmen = dict(abw=abw, s_aussen=s_aussen, kasten=kasten, hx=hx, hy=hy, solid=solid,
                     aussen=TopoDS.Wire(BRepBuilderAPI_Transform(aussen, tr, True).Shape()))
    t.sicherheit["konturen"] = "wahrscheinlich" if any(
        d["art"] in ("Ausschnitt", "Innenmerkmal") or d.get("form") in ("komplex", "nicht erkannt") or
        d.get("seite") == "Ecke" for d in t.konturen_liste) else "sicher"
    t.bohrungen = dict(sorted(bohrungen.items()))
    if t.kammern > 1 and t.kontur_umfang:
        # Mehrkammerprofil: die Enden schneiden auch die Zwischenwände. Jede Zwischenwand verlängert die Innenkonturen
        # um zweimal ihre Länge; ohne sie wäre die Innenkontur etwa Außenkontur − 8 × Wand (Näherung).
        zwischen = max((innen_umfang - (t.kontur_umfang - 8 * t.wandstaerke)) / 2, 0.0)
        for ende in ("ende_a", "ende_b"):
            if getattr(t, ende):
                setattr(t, ende, getattr(t, ende) + zwischen * getattr(t, ende) / t.kontur_umfang)
        t.hinweise.append(f"Mehrkammerprofil: Zwischenwände {zwischen:.0f} mm je Ende im Schnitt (Näherung)")
    t.schneidweg = t.ende_a + t.ende_b + t.innen
    if netz:
        art_flaeche = dict(art)
        for m in merkmale.values():
            for f in m["faces"]:
                art_flaeche[f] = m.get("art", "K")
        t.netz = dreiecksnetz(lok, faces, art_flaeche, [(m.get("art", "K"), m["kanten"]) for m in merkmale.values()],
                              zmin, max(t.abm_a, t.abm_b))
    t.bezug = ref
    return t


def nach_bezug_drehen(t):
    """Netz und Einbaulage (x_global) um die Rohrachse so drehen, dass +Y des Netzes die 0°-Richtung des
    Umfangswinkels ist (wie das Modell des Programms aus den Eingaben: Winkel w bei (−r sin w, r cos w)). Ohne das
    lagen Netz und Modell bei Rundrohren um die Bezugsrichtung (oberste Stelle in der Datei) und bei Kastenprofilen
    mit der Breitseite nach unten um 180° gegeneinander verdreht; die Lage in der Datei bleibt gleich. Erst ganz am
    Ende (step_messen), wenn Anbauteile, Gravur und Nähte im Messsystem fertig sind; danach bezug = 0."""
    w = math.radians(t.bezug or 0.0)
    t.bezug = 0.0
    if abs(math.sin(w)) < 1e-9 and math.cos(w) > 0:
        return
    c, s = math.cos(w), math.sin(w)
    if t.x_global and t.achse_global:
        x, z = gp_Vec(*t.x_global), gp_Vec(*t.achse_global)
        y = z.Crossed(x)
        n = x.Multiplied(c).Added(y.Multiplied(s))
        t.x_global = (n.X(), n.Y(), n.Z())

    def drehen(liste, schritt=3, stellen=2):
        for i in range(0, len(liste) - 1, schritt):
            x, y = liste[i], liste[i + 1]
            liste[i], liste[i + 1] = round(x * c + y * s, stellen), round(-x * s + y * c, stellen)
    for a in t.anbauteile or ():            # Gravur der Anbauteile (anbau.gravur_zuege) im selben System wie das Netz
        m = a.get("marke")
        if m:
            drehen(m["m"], 3, 3)
            drehen(m["c"], 2, 3)
            drehen(m["t"], 2, 6)
            drehen(m["n"], 2, 6)
        for zug in a.get("umriss_linien") or ():
            drehen(zug)
    if not t.netz:
        return
    drehen(t.netz.get("p") or [])
    for zuege in (t.netz.get("l") or {}).values():
        for zug in zuege:
            drehen(zug)


# ------------------------------------------------------------------ Bleche
# Ein Körper ist ein (ebenes) Blech, wenn er zwei parallele Hauptflächen hat, das Volumen der Hauptfläche mal ihrem
# Abstand entspricht (also überall gleich dick, keine Absätze oder Taschen) und die Dicke klein gegenüber der Breite
# ist. Die Dicke ist der Abstand der Hauptebenen, nicht die kleinste Kante des Hüllquaders: so stimmt sie auch bei
# gedrehten oder schräg liegenden Teilen. Länge und Breite kommen aus dem kleinsten umschreibenden Rechteck der
# Außenkontur in der Hauptebene.
# Flachstahl ist ein flacher Körper, der wie ein Stab aussieht (Patrick 20.10.2026, Frage 1 a): Breite bis
# FLACHSTAHL_BIS (Einstellung im Programm), Länge mindestens FLACHSTAHL_LAENGE × Breite und beide Längsseiten
# gerade über den größten Teil der Länge (Enden dürfen schräg oder ausgeklinkt sein). Alles andere Flache ist Blech.
FLACHSTAHL_BIS = 150.0          # mm
FLACHSTAHL_LAENGE = 3.0         # Länge mindestens 3 × Breite
BLECH_DICKE_ANTEIL = 0.2        # Dicke höchstens 1/5 der Breite
TOL_BLECH_VOLUMEN = 0.03        # Volumen = Hauptfläche × Dicke auf 3 %
TOL_EBENE = 0.01                # mm: Flächen in derselben Ebene
# Gleich dicke, gekantete Körper mit gleichbleibendem Querschnitt bleiben Profile (L, U, C, Kantprofil). Als
# gekantetes Blech gelten sie, wenn das Volumen deutlich unter Querschnitt × Länge liegt (Schenkel unterschiedlich
# lang oder ausgeschnitten, also kein Stangenmaterial).
GEKANTET_ANTEIL = 0.85


def _ebenen_gruppen(solid):
    """Ebene Flächen nach Normalenrichtung (ohne Vorzeichen) und Lage gruppiert:
    [(Richtung gp_Dir, [(Abstand, Fläche, [faces])])] – je Richtung die Ebenen, flächengrößte zuerst."""
    gruppen = []
    for f in _liste(solid, TopAbs_FACE):
        pl = _ebene(f)
        if pl is None:
            continue
        n, o = pl.Axis().Direction(), pl.Location()
        for g in gruppen:
            if abs(abs(g[0].Dot(n)) - 1) < 1e-5:
                break
        else:
            g = (n, [])
            gruppen.append(g)
        d = g[0]
        ab = o.X() * d.X() + o.Y() * d.Y() + o.Z() * d.Z()
        a = _flaeche(f)
        for e in g[1]:
            if abs(e[0] - ab) < TOL_EBENE:
                e[1] += a
                e[2].append(f)
                break
        else:
            g[1].append([ab, a, [f]])
    for g in gruppen:
        g[1].sort(key=lambda e: -e[1])
    return gruppen


def bohrung_art(flaechen, aussenkanten):
    """Senkung oder Fließlochbohrung (Flowdrill) aus den Flächen eines durchgehenden Merkmals und seinen Kanten auf
    der Außenhaut. Senkung: Zylinder eines Ø quer zur Achse + Kegel, außen größer als die Bohrung. Fließloch: Kernloch
    (kleinster Zylinder) ist außen genau so groß, dazu ein koaxialer Kragen innen (größerer Zylinder, Ring- oder
    Rundungsflächen). Ergebnis: ("Senkung", Ø, Senk-Ø) bzw. ("Fließloch", Ø, Kragen-Ø) oder None."""
    zyl, kegel, sonst, ebenen = [], 0, 0, []
    for f in flaechen:
        z_ = _zylinder(f)
        if z_ is not None:
            if abs(z_.Axis().Direction().Z()) > 0.99:
                return None
            zyl.append(z_)
            continue
        s = BRepAdaptor_Surface(TopoDS.Face(f))
        typ = s.GetType()
        if typ == GeomAbs_Cone:
            kegel += 1
        elif typ == GeomAbs_Torus:
            sonst += 1
        elif typ == GeomAbs_Plane:
            ebenen.append(s.Plane().Axis().Direction())
        else:
            return None
    if not zyl or not aussenkanten:
        return None
    kern = min(zyl, key=lambda c: c.Radius())
    ax = kern.Axis()
    # Ringfläche des Kragens: eben, quer zur Bohrungsachse. Andere Ebenen (Schlitz oder Ausschnitt, der an einen
    # Sattel anschließt, Patrick 27.10.2026) machen aus dem Merkmal keine Bohrung
    if any(abs(abs(n.Dot(ax.Direction())) - 1) > 1e-3 for n in ebenen):
        return None
    sonst += len(ebenen)
    for c in zyl:     # alle Zylinder koaxial zum Kernloch
        if abs(abs(c.Axis().Direction().Dot(ax.Direction())) - 1) > 1e-6 or \
                gp_Vec(ax.Location(), c.Axis().Location()).Crossed(_vec(ax.Direction())).Magnitude() > 0.01:
            return None
    radien = {round(c.Radius(), 2) for c in zyl}
    r = kern.Radius()
    # Abstand der Wandkanten von der Achse (offene Profile: Kanten beider Wandseiten, daher größter und kleinster)
    abst = [gp_Vec(ax.Location(), p).Crossed(_vec(ax.Direction())).Magnitude() for p in _punkte_kanten(aussenkanten)]
    if kegel and len(radien) == 1 and max(abst) > r + 0.1:
        return ("Senkung", round(2 * r, 2), round(2 * max(abst), 1))
    if abs(min(abst) - r) < 0.05 and (len(radien) > 1 or sonst):
        return ("Fließloch", round(2 * r, 2), round(2 * max(c.Radius() for c in zyl), 2))
    return None


def _zylinder_paare(solid, dicke, tol=0.02):
    """Fläche der Zylinderflächen, die paarweise koaxial im Abstand 'dicke' liegen (Biegezonen gekanteter Bleche)."""
    zyl = []
    for f in _liste(solid, TopAbs_FACE):
        sf = BRepAdaptor_Surface(TopoDS.Face(f))
        if sf.GetType() == GeomAbs_Cylinder:
            c = sf.Cylinder()
            zyl.append((c.Axis(), c.Radius(), _flaeche(f)))
    summe, benutzt = 0.0, set()
    for i, (ax1, r1, a1) in enumerate(zyl):
        for j in range(i + 1, len(zyl)):
            ax2, r2, a2 = zyl[j]
            if i in benutzt or j in benutzt or abs(abs(r1 - r2) - dicke) > tol:
                continue
            if abs(abs(ax1.Direction().Dot(ax2.Direction())) - 1) < 1e-5 and \
                    gp_Vec(ax1.Location(), ax2.Location()).Crossed(_vec(ax1.Direction())).Magnitude() < tol:
                summe += a1 + a2
                benutzt |= {i, j}
    return summe


def _flach_pruefen(solid, volumen):
    """Blechmerkmale eines Körpers oder None. Ergebnis dict: art 'eben' (Hauptflächen tragen das ganze Volumen)
    oder 'gekantet' (gleich dicke Schenkel in mindestens zwei Richtungen, verbunden über Biegezonen), dicke,
    hauptflaeche (Face), richtung (Normale), mitte (Punkt der Hauptebene)."""
    gruppen = _ebenen_gruppen(solid)
    kandidaten = [(g, g[1][0], g[1][1]) for g in gruppen if len(g[1]) >= 2]
    if not kandidaten or volumen <= 0:
        return None
    g, e1, e2 = max(kandidaten, key=lambda k: k[1][1])
    # die zweite Hauptfläche: die größte parallele Ebene in einem anderen Abstand
    dicke = abs(e1[0] - e2[0])
    if dicke < 0.05:
        return None
    haupt = max(e1[2], key=_flaeche)
    pl = _ebene(haupt)
    erg = dict(dicke=dicke, hauptflaeche=haupt, richtung=g[0], mitte=pl.Location(), flaeche_oben=e1[1],
               flaeche_unten=e2[1])
    # eben: nur diese beiden Ebenen in der Richtung (keine Absätze, Taschen oder Gravuren), Volumen = Fläche × Dicke
    weitere = [e for e in g[1][2:] if e[1] > 1e-3 * e1[1]]
    # (Senkungen nehmen auf einer Seite Fläche weg: Volumen liegt zwischen kleinerer und größerer Fläche × Dicke)
    if not weitere and e2[1] >= 0.9 * e1[1] and \
            min(e1[1], e2[1]) * dicke * (1 - TOL_BLECH_VOLUMEN) <= volumen <= \
            max(e1[1], e2[1]) * dicke * (1 + TOL_BLECH_VOLUMEN):
        return dict(erg, art="eben")
    # gekantet: alle Ebenenpaare im Abstand 'dicke' (je Richtung) und koaxiale Biegezonen tragen das Volumen
    paare, richtungen = 0.0, 0
    for _, ebenen in gruppen:
        frei = sorted(ebenen, key=lambda e: e[0])
        gefunden = False
        while frei:
            a = frei.pop(0)
            b = next((x for x in frei if abs(abs(x[0] - a[0]) - dicke) < 0.02), None)
            if b is not None:
                frei.remove(b)
                paare += a[1] + b[1]
                gefunden = True
        richtungen += gefunden
    biegungen = _zylinder_paare(solid, dicke)
    paare += biegungen
    if richtungen < 2:
        return None
    if biegungen > 0 and abs(volumen - paare / 2 * dicke) <= TOL_BLECH_VOLUMEN * 1.5 * volumen:
        return dict(erg, art="gekantet")
    # scharfkantig gezeichnet (Patrick 23.10.2026, Frage 1 a): Kantteil, wenn sich zwei Blechhäute mit Schenkeln
    # finden (ein T-Stoß oder Walzprofil ungleicher Dicke nicht; step_abwicklung)
    if biegungen == 0 and abs(volumen - paare / 2 * dicke) <= 0.15 * volumen:
        from step_abwicklung import abwickeln
        try:
            abw = abwickeln(solid, dicke)
        except Exception:  # Abwicklung ist nur ein Versuch
            abw = None
        if abw and "fehler" not in abw and not abw.get("rohr"):
            return dict(erg, art="gekantet", abwicklung=abw)
    return None


def _wire_kreis(draht):
    """Durchmesser, wenn der Draht ein Kreis ist (Kreiskanten mit gleichem Mittelpunkt und Radius), sonst None."""
    from OCP.GeomAbs import GeomAbs_Circle
    kreise = []
    for e in _liste(draht, TopAbs_EDGE):
        c = BRepAdaptor_Curve(TopoDS.Edge(e))
        if c.GetType() != GeomAbs_Circle:
            return None
        kreise.append(c.Circle())
    if not kreise:
        return None
    r, m = kreise[0].Radius(), kreise[0].Location()
    if all(abs(k.Radius() - r) < 1e-3 and k.Location().Distance(m) < 1e-3 for k in kreise):
        return round(2 * r, 3)
    return None


def _draht_laenge(draht):
    return sum(_kantenlaenge(e) for e in _liste(draht, TopAbs_EDGE))


def _draht_punkte(draht, schritt=0.5):
    """Punkte eines Drahts der Reihe nach (Kanten verbunden, Richtung beachtet), ohne doppelte Endpunkte."""
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.TopAbs import TopAbs_REVERSED
    out = []
    ex = BRepTools_WireExplorer(TopoDS.Wire(draht))
    while ex.More():
        e = ex.Current()
        c = BRepAdaptor_Curve(e)
        n = max(2, min(400, int(_kantenlaenge(e) / schritt) + 1))
        u0, u1 = c.FirstParameter(), c.LastParameter()
        if e.Orientation() == TopAbs_REVERSED:
            u0, u1 = u1, u0
        out += [c.Value(u0 + (u1 - u0) * k / n) for k in range(n)]
        ex.Next()
    return out


def _vereinfachen(pk, tol=0.05):
    """Geschlossenen Linienzug ausdünnen (Douglas-Peucker), Abweichung höchstens tol [mm]."""
    if len(pk) < 4:
        return pk

    def dp(a):
        if len(a) < 3:
            return a
        (x0, y0), (x1, y1) = a[0], a[-1]
        lg = math.hypot(x1 - x0, y1 - y0)
        ab = [abs((x1 - x0) * (y0 - y) - (x0 - x) * (y1 - y0)) / lg if lg > 1e-9 else math.hypot(x - x0, y - y0)
              for x, y in a[1:-1]]
        i = max(range(len(ab)), key=ab.__getitem__)
        if ab[i] <= tol:
            return [a[0], a[-1]]
        return dp(a[:i + 2])[:-1] + dp(a[i + 1:])
    j = max(range(len(pk)), key=lambda i: math.hypot(pk[i][0] - pk[0][0], pk[i][1] - pk[0][1]))
    return dp(pk[:j + 1])[:-1] + dp(pk[j:] + [pk[0]])[:-1]


def _blech_kontur(pts):
    """Innenkontur eines Blechs aus ihren Punkten (x, y im Zuschnitt): Art, Maße, Mitte, Lage für den Blech-Editor.
    Bohrung / Langloch / Rechteck längs oder quer, sonst Polygon (Eckpunkte um die Mitte)."""
    form, (cx, cy), lage = _form_2d(pts)
    d = dict(x=round(cx, 2), y=round(cy, 2))
    gerade = min(lage % 90, 90 - lage % 90) < 0.5
    quer = gerade and 45 < lage % 180 < 135
    if form[0] == "Kreis":
        d.update(art="Bohrung", durchmesser=round(form[1], 2))
    elif form[0] == "Langloch" and gerade:
        d.update(art="Langloch", laenge=round(form[1], 2), breite=round(form[2], 2), quer=quer)
    elif form[0] == "Rechteck" and gerade:
        d.update(art="Rechteck", laenge=round(form[1], 2), breite=round(form[2], 2), quer=quer)
    else:
        pk = _vereinfachen(pts)
        mx, my = sum(x for x, _ in pk) / len(pk), sum(y for _, y in pk) / len(pk)
        d.update(art="Polygon", x=round(mx, 2), y=round(my, 2),
                 punkte=[[round(x - mx, 2), round(y - my, 2)] for x, y in pk])
    return d


def _blech_daten(solid, fl):
    """Maße eines ebenen Blechs in der Hauptebene: Länge/Breite (kleinstes umschreibendes Rechteck der Außenkontur),
    Kontur rechteckig/frei, Innenkonturen und Bohrungen, Längsseiten gerade (für die Abgrenzung zum Flachstahl).
    Dazu das System ax3 (Z = Länge, X = Breite, Y = Normale) für die 3D-Ansicht."""
    from OCP.BRepTools import BRepTools
    face = TopoDS.Face(fl["hauptflaeche"])
    n = fl["richtung"]
    ax0 = gp_Ax3(fl["mitte"], n)
    aussen = BRepTools.OuterWire_s(face)
    lok = _transformiere(aussen, ax0)
    st = _strecken(lok)
    pts = [(x, y) for x1, y1, x2, y2 in st for x, y in ((x1, y1), (x2, y2))]
    w = _min_rechteck(pts)
    c, s_ = math.cos(w), math.sin(w)
    us = [x * c + y * s_ for x, y in pts]
    vs = [-x * s_ + y * c for x, y in pts]
    laenge, breite = max(us) - min(us), max(vs) - min(vs)
    if breite > laenge:      # _min_rechteck liefert die Richtung der längeren Seite; zur Sicherheit
        laenge, breite = breite, laenge
        c, s_ = -s_, c
        us, vs = vs, [-u for u in us]
    # Längsseiten: gerade Abschnitte auf den beiden langen Seiten des Rechtecks
    seiten = [0.0, 0.0]
    for x1, y1, x2, y2 in st:
        v1, v2 = -x1 * s_ + y1 * c, -x2 * s_ + y2 * c
        lg = math.hypot(x2 - x1, y2 - y1)
        for k, grenze in enumerate((min(vs), max(vs))):
            if abs(v1 - grenze) < 0.05 and abs(v2 - grenze) < 0.05:
                seiten[k] += lg
    mf = BRepBuilderAPI_MakeFace(aussen, True)
    flaeche_aussen = _flaeche(mf.Face()) if mf.IsDone() else laenge * breite
    innen = [TopoDS.Wire(d) for d in _liste(face, TopAbs_WIRE) if not d.IsSame(aussen)]
    bohrungen, innen_liste, innen_laenge, lage = {}, [], 0.0, []
    for d in innen:
        lg = _draht_laenge(d)
        innen_laenge += lg
        dm = _wire_kreis(d)
        if dm is not None:
            bohrungen[dm] = bohrungen.get(dm, 0) + 1
        b = Bnd_Box()
        BRepBndLib.AddOptimal_s(d, b, False, False)
        q0, q1 = b.CornerMin(), b.CornerMax()
        innen_liste.append((round(max(q1.X() - q0.X(), q1.Y() - q0.Y(), q1.Z() - q0.Z()), 2), round(lg, 2)))
        lage.append((d, lg))
    # System für die 3D-Ansicht und Lage in der Datei: Z = Längsrichtung, Y = Normale der Hauptfläche
    xd, yd = ax0.XDirection(), ax0.YDirection()
    lr = _vec(xd).Multiplied(c).Added(_vec(yd).Multiplied(s_))
    ax3 = gp_Ax3(fl["mitte"], gp_Dir(lr.X(), lr.Y(), lr.Z()), gp_Dir(_vec(n).Crossed(lr).X(), _vec(n).Crossed(lr).Y(),
                                                                       _vec(n).Crossed(lr).Z()))
    rechteckig = abs(flaeche_aussen - laenge * breite) <= 0.002 * laenge * breite
    # Lage im Zuschnitt: x längs ab der linken, y quer ab der unteren Kante des Hüllrechtecks [mm]
    u0, v0 = min(us), min(vs)

    def zuschnitt(draht):
        pk = [(p.X(), p.Y()) for p in _draht_punkte(_transformiere(draht, ax0))]
        return [(x * c + y * s_ - u0, -x * s_ + y * c - v0) for x, y in pk]
    konturen_lage = []
    for d, lg in lage:
        try:
            k = _blech_kontur(zuschnitt(d))
        except (ValueError, ZeroDivisionError, IndexError):
            continue
        k["schnittlaenge"] = round(lg, 2)
        konturen_lage.append(k)
    aussen_punkte = None
    if not rechteckig:
        try:
            aussen_punkte = [[round(x, 2), round(y, 2)] for x, y in _vereinfachen(zuschnitt(aussen))]
        except (ValueError, ZeroDivisionError, IndexError):
            aussen_punkte = None
    return dict(laenge=laenge, breite=breite, dicke=fl["dicke"], flaeche_aussen=flaeche_aussen,
                flaeche_netto=_flaeche(face), umfang_aussen=_draht_laenge(aussen), umfang_innen=innen_laenge,
                innen=len(innen), bohrungen=dict(sorted(bohrungen.items())), innen_liste=innen_liste,
                kontur="rechteckig" if rechteckig else "frei", laengsseiten_gerade=min(seiten) >= 0.8 * laenge,
                konturen_lage=konturen_lage, aussen_punkte=aussen_punkte, ax3=ax3)


def ist_flachstahl(laenge, breite, laengsseiten_gerade, flach_bis=FLACHSTAHL_BIS):
    """Abgrenzung Flachstahl/Blech (Frage 1 a): stabförmig, schmal, gerade Längsseiten."""
    return laengsseiten_gerade and breite <= flach_bis + 1e-6 and laenge >= FLACHSTAHL_LAENGE * breite - 1e-6


def fingerabdruck(b):
    """Geometrie-Fingerabdruck eines Blechs für den Dublettenvergleich (gerundete Kennwerte als Text)."""
    bo = ",".join(f"{d:g}x{n}" for d, n in b.get("bohrungen", {}).items())
    return (f"{b['dicke']:.1f}|{b['laenge']:.0f}|{b['breite']:.0f}|{b.get('flaeche_netto', 0):.0f}|"
            f"{b.get('umfang_aussen', 0) + b.get('umfang_innen', 0):.0f}|{b.get('innen', 0)}|{bo}")


def _blech_teil(solid, datei, koerper, fl, volumen, netz, daten=None):
    """Teil für ein ebenes oder gekantetes Blech."""
    t = Teil(datei=datei, koerper=koerper)
    d = fl["dicke"]
    if fl["art"] == "eben":
        b = daten or _blech_daten(solid, fl)
        ax3 = b.pop("ax3")
        t.bauteiltyp = t.profilform = "Blech"
        t.abm_a, t.abm_b, t.wandstaerke, t.laenge = b["laenge"], b["breite"], d, b["laenge"]
        t.bohrungen, t.innen_liste, t.innen_konturen = b["bohrungen"], b["innen_liste"], b["innen"]
        t.innen, t.konturen = b["umfang_innen"], 1 + b["innen"]
        t.schneidweg = b["umfang_aussen"] + b["umfang_innen"]
        t.sicherheit.update(profil="sicher", laenge="sicher", wandstaerke="sicher", konturen="nicht ausgewertet")
        b.pop("laengsseiten_gerade", None)
    else:
        # Außenmaße im System der Hauptfläche: Grundriss = kleinstes umschreibendes Rechteck, Höhe = senkrecht dazu
        ax0 = gp_Ax3(fl["mitte"], fl["richtung"])
        lok0 = _transformiere(solid, ax0)
        pts = [(x, y) for x1, y1, x2, y2 in _strecken(lok0, 2.0) for x, y in ((x1, y1), (x2, y2))]
        w = _min_rechteck(pts)
        c, s_ = math.cos(w), math.sin(w)
        us, vs = [x * c + y * s_ for x, y in pts], [-x * s_ + y * c for x, y in pts]
        z0, z1 = _z_bereich(lok0)
        masse = sorted((max(us) - min(us), max(vs) - min(vs), z1 - z0), reverse=True)
        t.bauteiltyp = t.profilform = "Blech gekantet"
        t.abm_a, t.abm_b, t.wandstaerke, t.laenge = masse[0], masse[1], d, masse[0]
        b = dict(laenge=masse[0], breite=masse[1], hoehe=masse[2], dicke=d, kontur="gekantet",
                 abwicklung_flaeche=volumen / d, flaeche_netto=volumen / d, umfang_aussen=0.0, umfang_innen=0.0,
                 innen=0, bohrungen={}, innen_liste=[])
        abw = fl.get("abwicklung")
        if abw is None:
            from step_abwicklung import abwickeln
            try:
                abw = abwickeln(solid, d)
            except Exception as e:  # ohne Abwicklung bleibt es bei den Außenmaßen
                abw = dict(fehler=str(e))
        if "fehler" not in abw:
            # Abwicklung (STEP-JSON 1.12): Zuschnitt, Schenkel, Biegelinien, Innenkonturen mit Lage, Schneidweg
            b.update(abwicklung_flaeche=abw["flaeche_netto"], flaeche_netto=abw["flaeche_netto"],
                     umfang_aussen=abw["umfang_aussen"], umfang_innen=abw["umfang_innen"], innen=abw["innen"],
                     bohrungen=abw["bohrungen"], innen_liste=abw["innen_liste"], konturen_lage=abw["konturen_lage"],
                     aussen_punkte=abw["aussen_punkte"], abwicklung=dict(
                         laenge=round(abw["laenge"], 2), breite=round(abw["breite"], 2), kantlaenge=abw["kantlaenge"],
                         schenkel=abw["schenkel"], biegelinien=abw["biegelinien"], kantungen=abw["kantungen"],
                         mehrachsig=abw["mehrachsig"], scharf=abw["scharf"], k_faktor=abw["k_faktor"]))
            t.innen, t.innen_konturen, t.innen_liste = abw["umfang_innen"], abw["innen"], abw["innen_liste"]
            t.bohrungen, t.konturen = abw["bohrungen"], 1 + abw["innen"]
            t.schneidweg = abw["umfang_aussen"] + abw["umfang_innen"]
            t.sicherheit.update(profil="wahrscheinlich", laenge="wahrscheinlich", wandstaerke="sicher",
                                konturen="sicher" if not abw["hinweise"] else "wahrscheinlich")
            art = "mehrachsig gekantet" if abw["mehrachsig"] else "gekantet"
            t.hinweise.append(f"Kantteil ({art}, {abw['kantungen']} Kantung{'en' if abw['kantungen'] != 1 else ''}): "
                              f"Zuschnitt {abw['laenge']:.1f} × {abw['breite']:.1f} mm (k = {abw['k_faktor']:g}), "
                              "Abwicklung prüfen")
            t.hinweise += abw["hinweise"]
        else:
            t.sicherheit.update(profil="wahrscheinlich", laenge="wahrscheinlich", wandstaerke="sicher",
                                konturen="nicht ausgewertet")
            t.hinweise.append(f"Gekantetes Blech: Außenmaße {masse[0]:.1f} × {masse[1]:.1f} × {masse[2]:.1f} mm, "
                              f"Abwicklung ca. {volumen / d / 1e6:.4f} m² (ohne Biegefaktor), Zuschnitt prüfen "
                              f"({abw['fehler']})")
        lr = _vec(ax0.XDirection()).Multiplied(c).Added(_vec(ax0.YDirection()).Multiplied(s_))
        ax3 = gp_Ax3(fl["mitte"], gp_Dir(lr.X(), lr.Y(), lr.Z()), fl["richtung"])
    b["volumen"] = volumen
    b["fingerabdruck"] = fingerabdruck(b)
    t.blech = b
    t.flaeche = 0.0       # kein Profilquerschnitt
    lok = _transformiere(solid, ax3)
    zmin, _ = _z_bereich(lok)
    dz, p = ax3.Direction(), _global(ax3, 0, 0, zmin)
    t.achse_global, t.ende_a_global = (dz.X(), dz.Y(), dz.Z()), (p.X(), p.Y(), p.Z())
    x = ax3.XDirection()
    t.x_global = (x.X(), x.Y(), x.Z())
    if netz:
        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(lok, TopAbs_FACE, faces)
        t.netz = dreiecksnetz(lok, faces, {i: "A" for i in range(1, faces.Extent() + 1)}, [], zmin, t.abm_a)
    return t


def analysiere(solid, datei="", koerper=1, netz=False, flach_bis=FLACHSTAHL_BIS):
    """Messung eines Körpers (_analysiere); ein offen gezeichnetes Quadrat-/Rechteckrohr (U offen, C mit Schlitz,
    Kantteil mit einer Lasche) wird zusätzlich als Rohr mit Stegen an den Enden gemessen (t.geschlossen,
    step_offenes_rohr, Patrick 25.10.2026); das Programm wählt, welche Messung gilt."""
    t = _analysiere(solid, datei, koerper, netz, flach_bis)
    if STEGE:           # vom Programm gewähltes größeres Profil: Winkel/U als virtuelles Bauteil mit Stegen
        try:
            from step_schenkel import mit_stegen, ziel_lesen
            v = mit_stegen(solid, t, ziel_lesen(STEGE), datei, koerper, netz)
        except Exception:  # dann gilt die Messung wie gezeichnet (das Programm rechnet mit der Formel)
            v = None
        if v is not None:
            return v
    try:
        from step_offenes_rohr import schliessen
        schliessen(solid, t, datei, koerper, netz)
    except Exception:  # Schließen darf die Messung nie verhindern
        t.geschlossen = None
    return t


def _analysiere(solid, datei="", koerper=1, netz=False, flach_bis=FLACHSTAHL_BIS):
    """Ein Körper: zuerst die Blechprüfung (ebene Bleche, die kein Flachstahl sind, werden als Blech gemessen), sonst
    die Profilmessung. Gekantete Bleche gelten nur dann als Blech, wenn die Profilmessung keinen gleichbleibenden
    Querschnitt findet (ein Kantprofil mit konstantem Querschnitt bleibt L/U/C-Profil)."""
    try:        # Biegerohr (Zylinder + Tori, Plan S9): Mittellinie und gestreckte Länge
        from step_biegerohr import messen as biegerohr_messen
        b = biegerohr_messen(solid, datei, koerper, netz)
    except Exception:  # Biegerohr-Erkennung darf die übrige Messung nie verhindern
        b = None
    if b is not None:
        return b
    try:        # Knickrahmen aus einem Körper (Plan K1-3): in gerade Stücke mit Gehrung teilen, je Stück messen
        from step_knickrahmen import messen as knickrahmen_messen
        b = knickrahmen_messen(solid, datei, koerper, netz)
    except Exception:  # Knickrahmen-Erkennung darf die übrige Messung nie verhindern
        b = None
    if b is not None:
        return b
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, p)
    volumen = abs(p.Mass())
    try:
        fl = _flach_pruefen(solid, volumen)
    except Exception:  # Blechprüfung darf die Profilmessung nie verhindern
        fl = None
    daten = None
    if fl and fl["art"] == "eben":
        daten = _blech_daten(solid, fl)
        dicke_ok = fl["dicke"] <= BLECH_DICKE_ANTEIL * daten["breite"] + 1e-6
        if dicke_ok and not ist_flachstahl(daten["laenge"], daten["breite"], daten["laengsseiten_gerade"], flach_bis):
            b = _blech_teil(solid, datei, koerper, fl, volumen, netz, dict(daten))
            b.alternative = _als_profil(solid, b, "Flachstahl")
            return b
    t = fehler = None
    try:
        t = _profil_messen(solid, datei, koerper, netz)
    except Exception as e:
        fehler = e
    # aufgesetzte Teile (Bolzen, Laschen, Kopfplatten …): nur bei Verdacht trennen und neu messen (sonst bleibt alles
    # wie bisher); Rohrlaser-Geometrie ohne Anbauteile, die Messung ohne Trennung steht kurz in t.trennung und ganz
    # in t.alternative
    if t is None or not t.profilform or getattr(t, "_anbau_verdacht", False) or t.profilform == "Sonderprofil" or \
            t.sicherheit.get("wandstaerke") == "unsicher":
        try:
            g = _getrennt_messen(solid, datei, koerper, netz, t)
        except Exception:  # Trennung gescheitert: Messung ohne Trennung gilt
            g = None
        if g is not None:
            if t is not None and t.profilform:
                t.bauteiltyp = "Profil"
                g.alternative = t       # Messung ohne Trennung: im Prüfdialog wählbar ("ist kein Anbauteil")
            t, fehler = g, None
    if fehler is not None and not (fl and fl["art"] == "gekantet"):
        raise fehler
    if fl and fl["art"] == "gekantet" and "abwicklung" not in fl and t is not None and t.kammern:
        fl["abwicklung"] = dict(fehler="geschlossenes Hohlprofil")     # Rohr, keine Abwicklung rechnen
    if fl and fl["art"] == "gekantet" and "abwicklung" not in fl:
        from step_abwicklung import abwickeln
        try:
            fl["abwicklung"] = abwickeln(solid, fl["dicke"])
        except Exception as e:  # ohne Abwicklung bleibt es bei den Außenmaßen
            fl["abwicklung"] = dict(fehler=str(e))
    mehrachsig = bool(fl and (fl.get("abwicklung") or {}).get("mehrachsig"))
    # geschlossenes Hohlprofil (Rohr) mit sicherer Achse bleibt Rohr: Gehrungen an beiden Enden drücken das Volumen
    # unter Querschnitt × Länge (RE 80x40, 480 mm, 2 × 45°: 83 %), das ist kein ausgeschnittenes Kantteil
    # Patrick 26.10.2026: ein geschlossenes Rohr ist immer ein Rohr, keine Ausnahme (auch wenn die Achse wegen vieler
    # Langlöcher nur "wahrscheinlich" ist oder die Ausschnitte das Volumen drücken)
    rohr = t is not None and bool(t.kammern) and t.profilform not in ("", "offenes Sonderprofil")
    if fl and fl["art"] == "gekantet" and not rohr and (
            t is None or not t.profilform or t.sicherheit.get("achse") != "sicher"
            or t.profilform == "offenes Sonderprofil" or mehrachsig
            or volumen < GEKANTET_ANTEIL * t.flaeche * t.laenge):
        b = _blech_teil(solid, datei, koerper, fl, volumen, netz)
        b.alternative = _als_profil(solid, b, None, t)
        return b
    if t.profilform:
        t.bauteiltyp = "Profil"
        if fl and t.alternative is None and not rohr and (fl["art"] == "gekantet" or t.profilform == "Flachstahl"):
            try:      # Grenzfall: auch als (gekantetes) Blech messen, im Prüfdialog wählbar
                t.alternative = _blech_teil(solid, datei, koerper, fl, volumen, False, daten and dict(daten))
            except Exception:  # Zweitmessung darf die Messung nie verhindern
                t.alternative = None
    return t


def _als_profil(solid, b, form=None, t=None):
    """Ein als Blech gemessenes Teil als Profil (Flachstahl bzw. L-/U-/C-Profil): die Profilmessung, wenn sie diese
    Form liefert, sonst Ersatzwerte aus den Blechmaßen (Länge × Breite) mit Prüfstatus 'prüfen'."""
    if t is None:
        try:
            t = _profil_messen(solid, b.datei, b.koerper, False)
        except Exception:  # nicht als Profil messbar: Ersatzwerte
            t = None
    passt = t is not None and t.laenge > 0 and (t.profilform == form if form else
                                                t.profilform in ("L-Profil", "U-Profil", "C-Profil"))
    if passt:
        t.bauteiltyp = "Profil"
        if not form:
            t.hinweise.append("als Profil gemessen, Volumen kleiner als Querschnitt × Länge (Ausschnitte?) – prüfen")
        return t
    bl = b.blech
    d = bl["dicke"]
    e = Teil(datei=b.datei, koerper=b.koerper, bauteiltyp="Profil", ersatz=True, laenge=bl["laenge"], konturen=2)
    if form == "Flachstahl":
        e.profilform, e.abm_a, e.abm_b, e.wandstaerke = "Flachstahl", bl["breite"], d, d
        e.flaeche = bl["breite"] * d
        e.ende_a = e.ende_b = e.ende_a_huelle = e.ende_b_huelle = bl["breite"]
        e.innen, e.innen_konturen = bl.get("umfang_innen", 0.0), bl.get("innen", 0)
        e.bohrungen, e.innen_liste = dict(bl.get("bohrungen") or {}), list(bl.get("innen_liste") or [])
        e.konturen += e.innen_konturen
    else:
        e.profilform, e.abm_a, e.abm_b, e.wandstaerke = "L-Profil", bl["breite"], bl.get("hoehe", 0.0), d
        e.flaeche = bl["volumen"] / bl["laenge"] if bl["laenge"] else 0.0
        e.ende_a = e.ende_b = e.ende_a_huelle = e.ende_b_huelle = bl["breite"] + bl.get("hoehe", 0.0)
    e.ende_a_gerade = e.ende_b_gerade = True
    e.schneidweg = e.ende_a + e.ende_b + e.innen
    e.achse_global, e.ende_a_global, e.x_global = b.achse_global, b.ende_a_global, b.x_global
    e.sicherheit.update(profil="unsicher", laenge="wahrscheinlich", wandstaerke="sicher", konturen="unsicher")
    e.hinweise.append(f"Ersatzwerte aus der Blechmessung ({form or 'L-Profil'} aus Länge × Breite), Schnitte "
                      "und Profil prüfen")
    return e


# ------------------------------------------------------------------ Anbauteile
# Aufgeschweißte Bolzen, Laschen, Bleche, Muttern oder Kopfplatten, die der Kunde zusammen mit dem Rohr als EINEN Körper
# konstruiert hat, oder als eigenen Körper, der das Rohr berührt (Plan "STEP-Import Anbauteile", Patrick 22.10.2026).
# Grundidee: Bearbeitungen (Bohrungen, Schlitze, Gehrungen, Gravuren) nehmen Material weg und liegen in der Rohrhülle,
# Anbauteile ergänzen Material außerhalb. Rohrhülle = Prisma aus der Außenkontur des häufigsten Querschnitts über den
# Bereich der Wandflächen. Körper ∩ Hülle = Rohrlaser-Geometrie (bisherige Messung), Körper − Hülle = Anbauteile.
# Unter einem Anbauteil bleibt die Rohrwand in der Schnittmenge geschlossen: keine künstlichen Konturen.
FUZZY = 1e-3                 # mm, Toleranz der Booleschen Operationen (die Hülle liegt genau auf dem Außenmantel)
ANBAU_DICKE_MIN = 0.05       # mm, mittlere Dicke 2·V/A darunter: Rechenrest der Booleschen Operation, kein Teil
ANBAU_KONTAKT = 0.05         # mm, ein eigener Körper gilt als aufgesetzt, wenn er das Rohr so nah berührt
REGEL_MIN = 0.4              # Anteil der Schnitte im Regelquerschnitt, ab dem getrennt wird
REGEL_SICHER = 0.6           # darunter: Trennung unsicher (Prüfstatus prüfen)
MARKE_KREUZ = 10.0           # mm, Strichlänge der Positionsmarke (Kreuz aus zwei Strichen)
# Vorgabe-Bearbeitung je Art (Patrick 22.10.2026, Frage F1 a); im Programm je Anbauteil änderbar
ANBAU_BEARBEITUNG = {"Bolzen": "Positionsmarke", "Mutter": "Umriss", "Lasche": "Umriss", "Blech": "Umriss",
                     "Kopfplatte": "keine", "Sonstiges": "Umriss"}


def virtuell_ablegen(form, koerper):
    """Virtuelles Bauteil (so wird gelasert: Teil ∪ Stege bzw. Ringe, in Dateilage) als STEP in den Ordner VIRTUELL
    schreiben, Datei k<Körper>.step (Patrick 26.10.2026: STEP-Export für die Maschine). Ohne Ordner nichts; ein Fehler
    beim Schreiben ändert die Messung nicht."""
    if not VIRTUELL or form is None:
        return
    try:
        from pathlib import Path

        from step_schreiben import form_schreiben
        Path(VIRTUELL).mkdir(parents=True, exist_ok=True)
        form_schreiben(form, Path(VIRTUELL) / f"k{int(koerper or 1)}.step", f"Teil {int(koerper or 1)} virtuell")
    except Exception:  # noqa: BLE001 – die Messung bleibt gültig
        pass


def _volumen(shape):
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, p)
    return abs(p.Mass())


def _flaechen_punkte(face):
    """Eckpunkte und je Kante drei Punkte einer Fläche (wie die Wandflächenprüfung in _profil_messen)."""
    pts = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in _liste(face, TopAbs_VERTEX)]
    for e in _liste(face, TopAbs_EDGE):
        c = BRepAdaptor_Curve(TopoDS.Edge(e))
        for u in (0.25, 0.5, 0.75):
            pts.append(c.Value(c.FirstParameter() + u * (c.LastParameter() - c.FirstParameter())))
    return pts


def _boolesch(art, a, b):
    """Schnittmenge ('common') bzw. Differenz ('cut') mit Fuzzy-Toleranz; None, wenn OpenCascade scheitert."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut
    try:  # OCP >= 7.8
        from OCP.collections import List_TopoDS_Shape as Liste
    except ImportError:
        from OCP.TopTools import TopTools_ListOfShape as Liste
    op = (BRepAlgoAPI_Common if art == "common" else BRepAlgoAPI_Cut)()
    la, lb = Liste(), Liste()
    la.Append(a)
    lb.Append(b)
    op.SetArguments(la)
    op.SetTools(lb)
    op.SetFuzzyValue(FUZZY)
    op.Build()
    return op.Shape() if op.IsDone() else None


def _hohl_regel(lok, zmin, zmax, n=25):
    """Häufigster Hohlquerschnitt (zwei Konturen, innen liegend) an n Stellen. Bohrungen machen einzelne Schnitte
    kleiner, Anbauteile größer: die Mehrheit ist das Rohr (bei Gleichstand die kleinere Außenkontur).
    Ergebnis (Anteil der Schnitte, Konturen, z) oder (0, None, None)."""
    gruppen = []
    for i in range(n):
        z = zmin + (i + 0.537) / (n + 0.1) * (zmax - zmin)
        ws = _schnitt(lok, z)
        if len(ws) != 2 or not _innen_liegend(ws[1][1], ws[0][1]):
            continue
        s = (ws[0][0] - ws[1][0], ws[0][0], ws, z)
        for g in gruppen:
            if abs(g[0][0] - s[0]) <= 0.002 * g[0][0] and abs(g[0][1] - s[1]) <= 0.002 * g[0][1]:
                g.append(s)
                break
        else:
            gruppen.append([s])
    if not gruppen:
        return 0.0, None, None
    g = max(gruppen, key=lambda g: (len(g), -g[0][1]))
    mitte = min(g, key=lambda s: abs(s[3] - (zmin + zmax) / 2))
    return len(g) / n, mitte[2], mitte[3]


def _huellflaeche(strecken):
    """Fläche der konvexen Hülle eines Polygonzugs."""
    pts = sorted({(round(x, 6), round(y, 6)) for st in strecken for x, y in ((st[0], st[1]), (st[2], st[3]))})
    if len(pts) < 3:
        return 0.0

    def kreuz(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    unten, oben = [], []
    for p in pts:
        while len(unten) >= 2 and kreuz(unten[-2], unten[-1], p) <= 0:
            unten.pop()
        unten.append(p)
    for p in reversed(pts):
        while len(oben) >= 2 and kreuz(oben[-2], oben[-1], p) <= 0:
            oben.pop()
        oben.append(p)
    h = unten[:-1] + oben[:-1]
    return abs(sum(h[i][0] * h[(i + 1) % len(h)][1] - h[(i + 1) % len(h)][0] * h[i][1] for i in range(len(h)))) / 2


def _laengsanbau_kontur(aussen, innen, wand):
    """Anbau über (fast) die ganze Länge: Außenkontur des Rohrs als Innenkontur + Wandstärke, wenn das eine Grundform
    (Kreis/Rechteck) ergibt und in der gemessenen Außenkontur liegt. Sonst None (Sonderprofil bleibt Sonderprofil)."""
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffset
    from OCP.GeomAbs import GeomAbs_Intersection
    if wand <= 0:
        return None
    ab = Bnd_Box()
    BRepBndLib.AddOptimal_s(aussen, ab, False, False)
    best = None
    for vz in (1, -1):
        try:
            mo = BRepOffsetAPI_MakeOffset(innen, GeomAbs_Intersection)
            mo.Perform(vz * wand)
            if not mo.IsDone():
                continue
            for w in _liste(mo.Shape(), TopAbs_WIRE):
                mf = BRepBuilderAPI_MakeFace(TopoDS.Wire(w), True)
                if mf.IsDone() and (best is None or _flaeche(mf.Face()) > best[0]):
                    best = (_flaeche(mf.Face()), TopoDS.Wire(w))
        except Exception:  # Versatz nicht möglich: kein Längsanbau-Kandidat
            continue
    if best is None:
        return None
    w = best[1]
    wb = Bnd_Box()
    BRepBndLib.AddOptimal_s(w, wb, False, False)
    if any(wb.CornerMin().Coord(i) < ab.CornerMin().Coord(i) - 0.05 or
           wb.CornerMax().Coord(i) > ab.CornerMax().Coord(i) + 0.05 for i in (1, 2)):
        return None
    if not _profilform(w, wb.CornerMax().X() - wb.CornerMin().X(), wb.CornerMax().Y() - wb.CornerMin().Y()):
        return None
    return w


def _anbau_trennen(solid):
    """Trennt Anbauteile von einem Hohlprofil (ein Körper). Ergebnis None (kein Hohlprofil, nichts abzutrennen oder
    unplausibel) oder dict(rohr=Solid, anbau=[Solid], regelanteil, laengsanbau, rest) – alles in Dateilage, das
    Original bleibt unverändert. Achse: wie die Messung; trägt der häufigste Querschnitt weniger als die Hälfte der
    Schnitte, werden die beiden anderen Hauptrichtungen der Flächennormalen als Achse versucht."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    achsen, mitte = _achse_grob(solid, alle=True)
    best = None
    for nr, achse in enumerate(achsen):
        ax3, _ = _lage(solid, (achse, mitte))
        lok = _transformiere(solid, ax3)
        zmin, zmax = _z_bereich(lok)
        anteil, ws, z = _hohl_regel(lok, zmin, zmax)
        if ws and (best is None or anteil > best[0]):
            best = (anteil, ws, z, ax3, lok)
        if best is None and nr == 0 or best and best[0] >= 0.5:
            break          # kein Hohlprofil (Blech, offenes Profil) oder Achse eindeutig
    if best is None or best[0] < REGEL_MIN:
        return None
    anteil, ws, z, ax3, lok = best
    aussen, innen = ws[0][1], ws[1][1]
    s_a, s_i = _strecken(aussen), _strecken(innen)
    ab = Bnd_Box()
    BRepBndLib.AddOptimal_s(aussen, ab, False, False)
    laengs = False
    form = _profilform(aussen, ab.CornerMax().X() - ab.CornerMin().X(), ab.CornerMax().Y() - ab.CornerMin().Y())
    # Rohre sind außen konvex; eine eingebuchtete Außenkontur (z. B. Blech längs auf dem Rohr) oder keine Grundform:
    # Rohrkontur aus Innenkontur + Wandstärke versuchen
    if not form or ws[0][0] < 0.98 * _huellflaeche(s_a):
        kand = _laengsanbau_kontur(aussen, innen, _wandstaerke(aussen, innen, s_a, s_i, z))
        if kand is not None:
            aussen, s_a, laengs = kand, _strecken(kand), True
        elif not form:
            return None
    # Wandbereich entlang der Achse: Flächen auf der Außen- oder Innenkontur (nicht der Hüllquader des Körpers – eine
    # Kopfplatte jenseits des Endes gehört nicht zur Rohrlänge)
    z0 = z1 = None
    for f in _liste(lok, TopAbs_FACE):
        pts = _flaechen_punkte(f)
        if all(_nah_zug(p.X(), p.Y(), s_a, TOL_WAND) for p in pts) or \
                all(_nah_zug(p.X(), p.Y(), s_i, TOL_WAND) for p in pts):
            b = Bnd_Box()
            BRepBndLib.AddOptimal_s(f, b, False, False)
            z0 = b.CornerMin().Z() if z0 is None else min(z0, b.CornerMin().Z())
            z1 = b.CornerMax().Z() if z1 is None else max(z1, b.CornerMax().Z())
    if z0 is None or z1 - z0 < 1.0:
        return None
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(0, 0, z0 - z))
    mf = BRepBuilderAPI_MakeFace(TopoDS.Wire(BRepBuilderAPI_Transform(aussen, tr, True).Shape()), True)
    if not mf.IsDone():
        return None
    huelle = BRepPrimAPI_MakePrism(mf.Face(), gp_Vec(0, 0, z1 - z0)).Shape()
    weg = _boolesch("cut", lok, huelle)
    if weg is None:
        return None
    anbau = [TopoDS.Solid(x) for x in _liste(weg, TopAbs_SOLID)
             if 2 * _volumen(x) / max(_flaeche(x), 1e-9) >= ANBAU_DICKE_MIN]
    if not anbau:
        return None
    rohr = _boolesch("common", lok, huelle)
    teile = sorted(_liste(rohr, TopAbs_SOLID), key=_volumen, reverse=True) if rohr is not None else []
    anteil_anbau = sum(_volumen(a) for a in anbau) / _volumen(teile[0]) if teile else 0.0
    if not teile or anteil_anbau > 3:
        return None        # weit mehr Anbau als Rohr: so nicht plausibel, Teil wie bisher messen
    inv = gp_Trsf()
    inv.SetTransformation(ax3)
    inv.Invert()

    def zurueck(s):
        return TopoDS.Solid(BRepBuilderAPI_Transform(s, inv, True).Shape())
    return dict(rohr=zurueck(teile[0]), anbau=[zurueck(a) for a in anbau], regelanteil=anteil, laengsanbau=laengs,
                rest=len(teile) - 1, mehr_anbau=anteil_anbau > 1)


def _flach_dicke(lok):
    """Dicke, wenn der Körper eine Platte ist: die größte ebene Fläche mal dem Abstand zur parallelen Gegenfläche
    ergibt das Volumen (±10 %) und die Dicke ist klein gegen die Fläche; sonst None."""
    vol = _volumen(lok)
    best = None
    for _, ebenen in _ebenen_gruppen(lok):
        groesste = max(ebenen, key=lambda e: e[1])
        for e in ebenen:
            d = abs(e[0] - groesste[0])
            if d > 0.05 and (best is None or groesste[1] > best[0]):
                best = (groesste[1], d)
    if best is None:
        return None
    flaeche, d = best
    return d if abs(flaeche * d - vol) <= 0.1 * vol and d <= math.sqrt(flaeche) / 2 else None


def _aufstand_huelle(r, lok, s_a, lg):
    """Aufstandsflächen eines Körpers, dessen anliegende Flächen über das Rohr hinausragen: Flächen mit Punkten auf
    der Außenkontur, geschnitten mit der Rohrhülle (Prisma aus der Außenkontur über die Länge, im System ab Ende A)."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakePrism
    if "huelle" not in r:
        mf = BRepBuilderAPI_MakeFace(r["aussen"], True)
        r["huelle"] = BRepPrimAPI_MakePrism(mf.Face(), gp_Vec(0, 0, lg)).Shape() if mf.IsDone() else None
    if r["huelle"] is None:
        return []
    out = []
    for f in _liste(lok, TopAbs_FACE):
        if not any(_abstand_zug(p.X(), p.Y(), s_a) < TOL_WAND for p in _flaechen_punkte(f)):
            continue
        teil = _boolesch("common", f, r["huelle"])
        if teil is None:
            continue
        out += [g for g in _liste(teil, TopAbs_FACE) if _flaeche(g) > 0.01 and
                all(_nah_zug(p.X(), p.Y(), s_a, TOL_WAND) for p in _flaechen_punkte(g))]
    return out


def _rohr_ax3(t):
    """System des Rohrs: Ursprung Ende A auf der Schwerlinie, Z = Achse, X = Breite (wie das Netz der 3D-Ansicht)."""
    return gp_Ax3(gp_Pnt(*t.ende_a_global), gp_Dir(*t.achse_global), gp_Dir(*t.x_global))


def _linienzug(kante, schritt=1.0):
    c = BRepAdaptor_Curve(TopoDS.Edge(kante))
    u0, u1 = c.FirstParameter(), c.LastParameter()
    n = max(2, min(120, int(_kantenlaenge(kante) / schritt) + 1))
    zug = []
    for k in range(n + 1):
        q = c.Value(u0 + (u1 - u0) * k / n)
        zug += [round(q.X(), 2), round(q.Y(), 2), round(q.Z(), 2)]
    return zug


def _netz_anhaengen(netz, dazu):
    basis = len(netz["p"]) // 3
    netz["p"] += dazu["p"]
    for art_, idx in dazu["t"].items():
        netz["t"].setdefault(art_, []).extend(basis + i for i in idx)
    for art_, zuege in dazu["l"].items():
        netz["l"].setdefault(art_, []).extend(zuege)


def _anbau_beschreiben(t, teile, quelle, netz=False, mit_flaechen=True):
    """Je Anbauteil (Solid in Dateilage) einen Eintrag in t.anbauteile: Art, Lage am Rohr (z ab Ende A, Winkel und
    Seite wie Bohrungen, siehe _Abwicklung), Aufstandsfläche, Höhe, Volumen, Vorgabe-Bearbeitung und Gravurlänge,
    Vertrauen. Die Gravur geht in t.gravur (nie in den Schneidweg). mit_flaechen: das Anbauteil ins Netz (Art AN);
    eigene Körper der Baugruppe haben ein eigenes Netz, dort nur die Gravurlinien (GA)."""
    r = t._rahmen
    abw, s_a, lg = r["abw"], r["s_aussen"], t.laenge
    ax3 = _rohr_ax3(t)
    tol = 0.01
    for teil in teile:
        lok = _transformiere(teil, ax3)
        za, zb = _z_bereich(lok)
        alle_pkt = [p for f in _liste(lok, TopAbs_FACE) for p in _flaechen_punkte(f)]
        d = dict(nr=len(t.anbauteile) + 1, art="Sonstiges", quelle=quelle, z=None, winkel=None, u=None, seite=None,
                 aufstand=None, hoehe=None, volumen=round(_volumen(lok), 1), bearbeitung=None, gravur_laenge=0.0,
                 vertrauen="sicher", hinweis="")
        rand, gravur_linien = [], []
        if zb <= tol or za >= lg - tol:
            # jenseits eines Endes: Kopf- bzw. Fußplatte, kein Eingriff in die Rohrwand
            ende = "A" if zb <= tol else "B"
            d.update(art="Kopfplatte", z=0.0 if ende == "A" else round(lg, 2), seite=f"Ende {ende}",
                     hoehe=round(-za if ende == "A" else zb - lg, 2))
        else:
            auf = [f for f in _liste(lok, TopAbs_FACE)
                   if all(_nah_zug(p.X(), p.Y(), s_a, TOL_WAND) and -tol <= p.Z() <= lg + tol
                          for p in _flaechen_punkte(f))]
            from OCP.BRepTools import BRepTools
            karte, zahl, loch = TopTools_IndexedMapOfShape(), {}, False
            for f in auf:
                loch |= len(_liste(f, TopAbs_WIRE)) > 1
                for e in _liste(BRepTools.OuterWire_s(TopoDS.Face(f)), TopAbs_EDGE):
                    i = karte.Add(e)
                    zahl[i] = zahl.get(i, 0) + 1
            if not auf:     # Fläche größer als die Auflage (Blech steht über): Teil der Fläche auf der Rohrhülle
                auf = _aufstand_huelle(r, lok, s_a, lg)
                for f in auf:
                    loch |= len(_liste(f, TopAbs_WIRE)) > 1
                    for e in _liste(BRepTools.OuterWire_s(TopoDS.Face(f)), TopAbs_EDGE):
                        i = karte.Add(e)
                        zahl[i] = zahl.get(i, 0) + 1
            rand = [karte.FindKey(i) for i, n in zahl.items() if n == 1]
            if rand:
                pts = _punkte_kanten(rand)
            else:   # nur Linien- oder Punktberührung (eigener Körper): Punkte nahe am Mantel
                pts = [p for p in alle_pkt if _abstand_zug(p.X(), p.Y(), s_a) < 0.1 and -tol <= p.Z() <= lg + tol]
                d["vertrauen"] = "prüfen"
                d["hinweis"] = "keine Aufstandsfläche, nur Berührung"
            if not pts:
                continue
            uv = [(abw.u(p.X(), p.Y()), p.Z()) for p in pts]
            if max(u for u, _ in uv) - min(u for u, _ in uv) > abw.umfang / 2:      # über die 0°-Naht
                uv = [(u + abw.umfang if u < abw.umfang / 2 else u, v) for u, v in uv]
            form, (uc, vc), _ = _form_2d(uv) if len(uv) >= 3 else (("Punkt", 0.0, 0.0), uv[0], 0.0)
            winkel, px, py = abw.punkt(uc)
            if r["kasten"]:
                # Seite je Punkt über die Wand, auf der er liegt (Mitte dieser Wand gibt den Winkel)
                seiten, ecke = set(), False
                for p in pts:
                    dx, dy = p.X() - abw.cx, p.Y() - abw.cy
                    auf_x, auf_y = abs(abs(dx) - r["hx"]) < 0.05, abs(abs(dy) - r["hy"]) < 0.05
                    if auf_x and auf_y:
                        continue                       # genau auf einer Kante: zählt zu beiden Seiten
                    if not (auf_x or auf_y):
                        ecke = True                    # in der Eckrundung
                    elif auf_x:
                        seiten.add(round(abw.theta(abw.cx + math.copysign(r["hx"], dx), abw.cy) / 90) % 4)
                    else:
                        seiten.add(round(abw.theta(abw.cx, abw.cy + math.copysign(r["hy"], dy)) / 90) % 4)
                d["seite"] = f"{seiten.pop() * 90}°" if len(seiten) == 1 and not ecke else "Ecke"
            u = uc % abw.umfang
            umfang = sum(_kantenlaenge(e) for e in rand)
            aufstand = dict(form=form[0], umfang=round(umfang, 2), flaeche=round(sum(_flaeche(f) for f in auf), 2))
            if form[0] == "Kreis":
                aufstand["durchmesser"] = round(form[1], 2)
            else:
                aufstand.update(laenge=round(form[1], 2), breite=round(form[2], 2))
            aussen_pkt = [p for p in alle_pkt if not _im_material(p.X(), p.Y() + 1.37e-6, s_a)]
            d.update(z=round(vc, 2), winkel=round(winkel % 360, 1) % 360,
                     u=round(0.0 if abw.umfang - u < 0.005 else u, 2), aufstand=aufstand,
                     hoehe=round(max([_abstand_zug(p.X(), p.Y(), s_a) for p in aussen_pkt] + [0.0]), 2))
            dicke = _flach_dicke(lok)
            if rand and form[0] == "Kreis" and (loch or d["hoehe"] >= 0.5 * form[1]):
                d["art"] = "Mutter" if loch else "Bolzen"      # flache runde Scheibe: Blech (Ronde)
            elif rand and loch and dicke is None:
                d["art"] = "Mutter"
            elif dicke is not None and rand:
                breite = form[1] if form[0] == "Kreis" else min(form[1:])
                d["art"] = "Lasche" if abs(breite - dicke) <= max(0.2, 0.2 * dicke) else "Blech"
            # Positionsmarke: Kreuz in der Mitte, ein Strich längs, einer quer (Sehne auf der Wand)
            (_, ax_, ay_), (_, bx_, by_) = abw.punkt(uc - 0.5), abw.punkt(uc + 0.5)
            tl = math.hypot(bx_ - ax_, by_ - ay_) or 1.0
            tx, ty, h = (bx_ - ax_) / tl, (by_ - ay_) / tl, MARKE_KREUZ / 2
            gravur_linien = [[round(v, 2) for v in (px, py, vc - h, px, py, vc + h)],
                             [round(v, 2) for v in (px - h * tx, py - h * ty, vc, px + h * tx, py + h * ty, vc)]]
            # Lage der Gravur fürs 3D aus den Eingaben und den STEP-Export (Mitte, Richtung quer, Normale nach außen)
            nx_, ny_ = ty, -tx
            if nx_ * (px - abw.cx) + ny_ * (py - abw.cy) < 0:
                nx_, ny_ = -nx_, -ny_
            d["marke"] = dict(m=[round(px, 3), round(py, 3), round(vc, 3)], t=[round(tx, 6), round(ty, 6)],
                              n=[round(nx_, 6), round(ny_, 6)], c=[round(abw.cx, 3), round(abw.cy, 3)],
                              rund=t.profilform == "Rundrohr")
            if rand:
                d["umriss_linien"] = [_linienzug(e) for e in rand]
        art_ = d["art"]
        if art_ == "Sonstiges" or d["seite"] == "Ecke" or (t.trennung or {}).get("laengsanbau"):
            d["vertrauen"] = "prüfen"
        bearbeitung = ANBAU_BEARBEITUNG[art_]
        if bearbeitung == "Umriss" and not rand:
            bearbeitung = "Positionsmarke"
        d["bearbeitung"] = bearbeitung
        d["gravur_laenge"] = round(sum(_kantenlaenge(e) for e in rand), 2) if bearbeitung == "Umriss" else \
            2 * MARKE_KREUZ if bearbeitung == "Positionsmarke" else 0.0
        if d["vertrauen"] != "sicher":
            t.hinweise.append(f"Anbauteil {d['nr']} ({art_}) bei z = {d['z'] or 0:.0f} mm nicht sicher erkannt, prüfen")
            t.sicherheit["anbauteile"] = "unsicher"
        t.sicherheit.setdefault("anbauteile", "sicher")
        t.gravur += d["gravur_laenge"]
        t.gravur_anbau += d["gravur_laenge"]
        t.gravur_konturen += 1 if d["gravur_laenge"] > 0 else 0
        t.anbauteile.append(d)
        if netz and t.netz is not None:
            dazu = dict(p=[], t={}, l={})
            if mit_flaechen:
                faces = TopTools_IndexedMapOfShape()
                TopExp.MapShapes_s(lok, TopAbs_FACE, faces)
                dazu = dreiecksnetz(lok, faces, {i: "AN" for i in range(1, faces.Extent() + 1)}, [], 0.0,
                                    max(t.abm_a, t.abm_b))
            if bearbeitung == "Umriss":
                dazu["l"]["GA"] = [_linienzug(e) for e in rand]
            elif bearbeitung == "Positionsmarke":
                dazu["l"]["GA"] = gravur_linien
            _netz_anhaengen(t.netz, dazu)


def _getrennt_messen(solid, datei, koerper, netz, ohne=None):
    """Messung mit abgetrennten Anbauteilen oder None (nichts abzutrennen). Die Profilmessung läuft unverändert auf
    der Rohrlaser-Geometrie; 'trennung' enthält Regelanteil, Längsanbau und die Messung ohne Trennung (ohne, kurz)."""
    tr = _anbau_trennen(solid)
    if tr is None:
        return None
    t = _profil_messen(tr["rohr"], datei, koerper, netz)
    if not t.profilform or getattr(t, "_rahmen", None) is None:
        return None
    o = ohne
    ohne = dict(profil_id=o.profil_id_vorschlag or o.profilform or None, laenge=round(o.laenge, 2),
                schneidweg=round(o.schneidweg, 2), pruefstatus=o.pruefstatus) if o is not None else None
    t.trennung = dict(regelanteil=round(tr["regelanteil"], 2), laengsanbau=tr["laengsanbau"], ohne_trennung=ohne)
    if tr["laengsanbau"]:
        t.hinweise.append("Anbau über (fast) die ganze Länge angenommen: Rohrprofil aus Innenkontur + Wandstärke, "
                          "prüfen")
        t.sicherheit["profil"] = "unsicher"
    elif tr["regelanteil"] < REGEL_SICHER:
        t.hinweise.append(f"Rohrquerschnitt nur in {tr['regelanteil']:.0%} der Schnitte gleich, Trennung prüfen")
        t.sicherheit["profil"] = "unsicher"
    if tr["mehr_anbau"]:
        t.hinweise.append("Anbauteile schwerer als das Rohr, Trennung prüfen")
        t.sicherheit["profil"] = "unsicher"
    if tr["rest"]:
        t.hinweise.append(f"{tr['rest']} weitere Restkörper in der Rohrhülle nicht gemessen, prüfen")
    _anbau_beschreiben(t, tr["anbau"], "verschmolzen", netz)
    return t


def _ist_rohr(t):
    return getattr(t, "_rahmen", None) is not None or getattr(t, "_rohr", False)


def _beruehrende_anbauteile(teile, koerper, netz, rahmen=None):
    """Baugruppe: eigene Körper (Bleche, Rundstahl/Bolzen, nicht messbare), die ein gemessenes Hohlprofil berühren,
    sind dessen Anbauteile (Patrick 22.10.2026, F2 a: sie bleiben zusätzlich eigene Positionen). Rohre, die andere
    Rohre berühren (Gestell), bleiben unberührt. rahmen(t): Abwicklung eines Rohrs, dessen _rahmen fehlt (in einem
    anderen Prozess gemessen); wird nur für Rohre mit Anbauteil gebraucht."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    rohre = [(t, k) for t, (art, k) in zip(teile, koerper) if _ist_rohr(t)]
    andere = [(t, k) for t, (art, k) in zip(teile, koerper) if art != "Flächenmodell offen" and
              not _ist_rohr(t) and (t.bauteiltyp in ("Blech", "Blech gekantet") or
                                    t.profilform in ("Rundstahl", "Vierkantstahl", ""))]
    for t, k in rohre:
        if not andere:
            break
        solid = t._rahmen["solid"] if getattr(t, "_rahmen", None) is not None else k
        rb = Bnd_Box()
        BRepBndLib.Add_s(solid, rb, False)
        rb.Enlarge(max(ANBAU_KONTAKT, NAHT_SPALT))
        for ta, ka in andere:
            kb = Bnd_Box()
            BRepBndLib.Add_s(ka, kb, False)
            if rb.IsOut(kb):
                continue
            if getattr(t, "_rahmen", None) is None:
                if rahmen is None or rahmen(t) is None:
                    break
                solid = t._rahmen["solid"]
            dist = BRepExtrema_DistShapeShape(solid, ka)
            if not dist.IsDone() or dist.Value() > max(ANBAU_KONTAKT, NAHT_SPALT):
                continue
            spalt = dist.Value() if dist.Value() > ANBAU_KONTAKT else 0.0
            vorher = len(t.anbauteile)
            try:
                # Spalt (Patrick 26.10.2026): eine an das Rohr geschobene Kopie beschreiben, so liegt die Gravur genau
                # unter dem Blech auf der Rohrwand; das Teil selbst bleibt, wo es ist
                k_ = _an_schieben(ka, dist) if spalt else ka
                _anbau_beschreiben(t, [TopoDS.Solid(k_)], f"Körper {ta.koerper}", netz, mit_flaechen=False)
            except Exception:  # Beschreibung gescheitert: Teil bleibt wie gemessen
                t.hinweise.append(f"Körper {ta.koerper} berührt das Rohr, Lage nicht bestimmbar, prüfen")
                continue
            if spalt and len(t.anbauteile) > vorher:
                d = t.anbauteile[-1]
                d["spalt"] = round(spalt, 2)
                d["hinweis"] = (d["hinweis"] + "; " if d["hinweis"] else "") + f"Spalt {_mm(spalt)} mm zum Rohr"
                if d["vertrauen"] == "sicher":
                    d["vertrauen"] = "prüfen"
                    t.hinweise.append(f"Anbauteil {d['nr']} ({d['art']}) mit Spalt {_mm(spalt)} mm zum Rohr, prüfen")
                    t.sicherheit["anbauteile"] = "unsicher"


NAHT_KONTAKT = 0.1          # mm: zwei Körper berühren sich (Nahtkandidat), wenn sie so nah beieinander liegen
NAHT_SPALT = 3.0            # mm: Spalt bis hier ist noch ein Schweißstoß (Naht und Gravur, Einstellung step_naht_spalt)
NAHT_SPALT_RAND = 0.05      # mm: so weit greift der aufgedickte Körper über den Spalt in das andere Teil
NAHT_PAARE_MAX = 5000       # höchstens so viele Paare mit überlappenden Hüllquadern prüfen (große Baugruppen)
NAHT_ENDE = 2.0             # mm: Kontakt gilt als am Rohrende, wenn er so nah am Ende liegt (entlang der Achse)


def _naht_dicke(t):
    for w in (t.wandstaerke, (t.blech or {}).get("dicke") if isinstance(t.blech, dict) else None):
        if isinstance(w, (int, float)) and w > 0:
            return float(w)
    return None


def _am_ende(t, punkt, spalt=0.0):
    """'A'/'B', wenn punkt (Schwerpunkt des Kontakts) an einem Rohrende liegt, sonst None (oder ohne Achse). spalt:
    das Rohrende darf so viel weiter vor dem anderen Teil enden."""
    if not t.achse_global or not t.ende_a_global or not t.laenge:
        return None
    z = sum((punkt[i] - t.ende_a_global[i]) * t.achse_global[i] for i in range(3))
    if abs(z) <= NAHT_ENDE + spalt + 1e-6:
        return "A"
    if abs(z - t.laenge) <= NAHT_ENDE + spalt + 1e-6:
        return "B"
    return None


def _auf_achse(t, punkt):
    """True, wenn punkt nahe der Achse des Rohrs t liegt (innerhalb ¼ des kleineren Außenmaßes) und das Rohr einen
    Außenumfang hat: eine Berührung rundum hat ihre Mitte auf der Achse."""
    if not _ist_rohr(t) or not t.achse_global or not t.ende_a_global or not t.kontur_umfang:
        return False
    v = gp_Vec(gp_Pnt(*t.ende_a_global), gp_Pnt(*punkt))
    return v.Crossed(gp_Vec(*t.achse_global)).Magnitude() < min(t.abm_a, t.abm_b or t.abm_a) / 4


def _mm(v):
    return f"{v:.1f}".replace(".", ",")


def _an_schieben(k, dist):
    """Kopie von k, um den kürzesten Abstand an das andere Teil geschoben (berührt es dann); dist =
    BRepExtrema_DistShapeShape(anderes Teil, k)."""
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(dist.PointOnShape2(1), dist.PointOnShape1(1)))
    return BRepBuilderAPI_Transform(k, tr, True).Shape()


def _spalt_huelle(k, spalt):
    """Körper k um spalt + NAHT_SPALT_RAND aufgedickt (überbrückt den Spalt), None, wenn OpenCascade scheitert."""
    from OCP.BRepOffset import BRepOffset_Skin
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
    from OCP.GeomAbs import GeomAbs_Arc
    try:
        mk = BRepOffsetAPI_MakeOffsetShape()
        mk.PerformByJoin(k, spalt + NAHT_SPALT_RAND, 1e-3, BRepOffset_Skin, False, False, GeomAbs_Arc)
        return mk.Shape() if mk.IsDone() else None
    except Exception:  # Aufdicken ist nur ein Hilfsmittel
        return None


def _naht_knoten(a, b, struktur):
    """Kleinster gemeinsamer Knoten der beiden Körper in der Baugruppenstruktur (oder None ohne Struktur)."""
    if not struktur or not a.knoten or not b.knoten:
        return None
    eltern = {k["id"]: k["eltern"] for k in struktur.get("knoten", [])}

    def kette(k):
        out = []
        while k:
            out.append(k)
            k = eltern.get(k)
        return out
    ka = kette(a.knoten)
    return next((k for k in kette(b.knoten) if k in ka), None)


NAHT_LINIE_SCHRITT = 5.0      # mm je Stützpunkt des Nahtverlaufs (3D-Ansicht), höchstens 24 Abschnitte je Kante


def _naht_linie(c, laenge):
    """Kante als Linienzug [x, y, z, x, y, z, …] in Dateilage, auf 0,1 mm gerundet (Nahtverlauf, STEP-JSON 1.16)."""
    n = max(1, min(24, int(math.ceil(laenge / NAHT_LINIE_SCHRITT))))
    if c.GetType() == GeomAbs_Line:
        n = 1
    t0, t1 = c.FirstParameter(), c.LastParameter()
    out = []
    for i in range(n + 1):
        p = c.Value(t0 + (t1 - t0) * i / n)
        out += [round(p.X(), 1), round(p.Y(), 1), round(p.Z(), 1)]
    return out


def _nahtkandidaten(teile, koerper, struktur=None, rahmen=None, stand=None):
    """Mögliche Schweißnähte einer Baugruppe: je Paar sich berührender Volumenkörper ein Kandidat
    {teile [a, b] (Körpernummern), knoten, laenge_mm, stossart, dicke_mm, status 'prüfen', linien (Nahtverlauf:
    je Kante des längsten Berührungszugs ein Linienzug in Dateilage)}. Länge = Schnittlänge
    des Rohrendes, das auf dem anderen Teil sitzt, sonst längster Linienzug der Berührung (Umfang der
    Kontaktfläche); Stoßart: Rohrende an Rohrende in einer
    Flucht = Stumpfnaht, Enden über Eck (Gehrung) = Ecknaht, sonst Kehlnaht; Dicke = dünnere Wand bzw. Blechdicke.
    Nur Vorschlag: übernommen wird erst nach Bestätigung (Schweißbaugruppen). Sitzt genau ein Rohrende auf einem
    anderen Rohr, beschreibt "stoss" die Lage (_stoss; rahmen(t) wie bei _beruehrende_anbauteile).
    Spalt bis NAHT_SPALT (Patrick 26.10.2026: Blech mit Spalt zum Rohr bekam keine Naht): der kleinere Körper wird um
    den Spalt aufgedickt und mit dem anderen geschnitten (Nahtverlauf auf dem anderen Teil), der Kandidat trägt
    "spalt_mm". stand (dict): "vollstaendig" = False, wenn wegen NAHT_PAARE_MAX nicht alle Paare geprüft wurden."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape
    koerper_ = [(t, k) for t, (art, k) in zip(teile, koerper) if art != "Flächenmodell offen" and t.koerper]
    if len(koerper_) < 2:
        return []
    boxen = []
    for t, k in koerper_:
        bb = Bnd_Box()
        BRepBndLib.Add_s(k, bb, False)
        bb.Enlarge(max(NAHT_KONTAKT, NAHT_SPALT))
        boxen.append(bb)
    out, paare = [], 0
    for i in range(len(koerper_)):
        for j in range(i + 1, len(koerper_)):
            if boxen[i].IsOut(boxen[j]):
                continue
            paare += 1
            if paare > NAHT_PAARE_MAX:
                if stand is not None:
                    stand["vollstaendig"] = False
                return out
            (ta, ka), (tb, kb) = koerper_[i], koerper_[j]
            dist = BRepExtrema_DistShapeShape(ka, kb)
            if not dist.IsDone() or dist.Value() > max(NAHT_KONTAKT, NAHT_SPALT):
                continue
            spalt = dist.Value() if dist.Value() > NAHT_KONTAKT else 0.0
            if spalt:
                klein_b = _volumen(kb) <= _volumen(ka)
                huelle = _spalt_huelle(kb if klein_b else ka, spalt)
                if huelle is not None:
                    sec = BRepAlgoAPI_Section(ka if klein_b else kb, huelle)
                else:       # Aufdicken gescheitert: b an a schieben (gleiche Länge bei ebener Auflage)
                    sec = BRepAlgoAPI_Section(ka, _an_schieben(kb, dist))
            else:
                sec = BRepAlgoAPI_Section(ka, kb)
            sec.Build()
            if not sec.IsDone():
                continue
            kanten = TopTools_HSequenceOfShape()
            for e in _liste(sec.Shape(), TopAbs_EDGE):
                kanten.Append(e)
            if kanten.Length() == 0:
                continue
            draehte = ShapeAnalysis_FreeBounds.ConnectEdgesToWires_s(kanten, 0.01, False)
            laengen, mitte, gesamt, zuege, schwer = [], [0.0, 0.0, 0.0], 0.0, [], [0.0, 0.0, 0.0]
            for w in range(1, draehte.Length() + 1):
                lw, zug = 0.0, []
                for e in _liste(draehte.Value(w), TopAbs_EDGE):
                    c = BRepAdaptor_Curve(TopoDS.Edge(e))
                    lg = GCPnts_AbscissaPoint.Length_s(c)
                    p = c.Value((c.FirstParameter() + c.LastParameter()) / 2)
                    for n, v in enumerate((p.X(), p.Y(), p.Z())):
                        mitte[n] += v * lg
                    for k in range(8):      # Schwerpunkt der Kanten (ganze Kreise: Mitte auf der Achse)
                        q = c.Value(c.FirstParameter() + (c.LastParameter() - c.FirstParameter()) * (k + 0.5) / 8)
                        for n, v in enumerate((q.X(), q.Y(), q.Z())):
                            schwer[n] += v * lg / 8
                    gesamt += lg
                    lw += lg
                    zug.append(_naht_linie(c, lg))
                laengen.append(lw)
                zuege.append(zug)
            if not laengen or max(laengen) < 0.5:
                continue        # nur Punkt- oder Linienberührung ohne Länge
            mitte = [v / gesamt for v in mitte] if gesamt else mitte
            ea, eb = _am_ende(ta, mitte, spalt), _am_ende(tb, mitte, spalt)
            if ea and eb:
                cos = abs(sum(x * y for x, y in zip(ta.achse_global, tb.achse_global)))
                stossart = "Stumpfnaht" if cos > 0.999 else "Ecknaht"
            else:
                stossart = "Kehlnaht"
            # Rohrende auf dem anderen Teil: Naht rundum = Schnittlänge dieses Endes (die Berührung selbst ist bei
            # gleich breiten Rohren wegen der Eckradien kürzer)
            enden = [x for t, e in ((ta, ea), (tb, eb)) if e
                     for x in [t.ende_a if e == "A" else t.ende_b] if isinstance(x, (int, float)) and x > 0]
            laenge = min(enden) if enden else max(laengen)
            # Rohr durch ein Blech gesteckt (Mitte der Berührung auf der Rohrachse, nicht am Ende): rundum, beidseitig
            # (Plan S8); Länge = Außenumfang des Rohrs, je Seite eine Naht
            schwer = [v / gesamt for v in schwer] if gesamt else schwer
            durch = next((t for t, e, o in ((ta, ea, tb), (tb, eb, ta)) if not e and not _ist_rohr(o)
                          and _auf_achse(t, schwer)), None)
            if durch is not None and not ea and not eb:
                laenge = durch.kontur_umfang
            dicken = [d for d in (_naht_dicke(ta), _naht_dicke(tb)) if d]
            k_ = dict(teile=[ta.koerper, tb.koerper], knoten=_naht_knoten(ta, tb, struktur),
                      laenge_mm=round(laenge, 1), stossart=stossart,
                      dicke_mm=round(min(dicken), 2) if dicken else None, status="prüfen",
                      linien=zuege[laengen.index(max(laengen))])
            if spalt:
                k_["spalt_mm"] = round(spalt, 2)
            if durch is not None and not ea and not eb:
                k_["beidseitig"] = True
            if stossart == "Kehlnaht" and bool(ea) != bool(eb):
                try:
                    st = _stoss(tb if eb else ta, eb or ea, ta if eb else tb, mitte, rahmen)
                except Exception:  # Lage des Stoßes ist nur ein Vorschlag: nie die Nahtkandidaten verhindern
                    st = None
                if st:
                    k_["stoss"] = st
            out.append(k_)
    return out


def _ohne_naht(teile, koerper, naehte):
    """Körpernummern einer Baugruppe (ab zwei Körpern), die mit keinem anderen Körper einen Nahtkandidaten haben
    (Patrick 26.10.2026: lose Teile sofort sehen, z. B. Spalt größer als NAHT_SPALT); [] bei Einzelteilen."""
    nummern = [t.koerper for t, (art, k) in zip(teile, koerper) if art != "Flächenmodell offen" and t.koerper
               and t.profilform != VERBUNDKERN]
    if len(nummern) < 2:
        return []
    mit = {k for n in naehte for k in n.get("teile") or ()}
    return [k for k in nummern if k not in mit]


def _stoss(st, ende, auf, mitte, rahmen=None):
    """Rohrende an Rohrwand (Stecker an Aufnahme, für Steckverbindungen, STEP-JSON 1.18): {stecker, ende ('a'/'b'),
    aufnahme (Körpernummern), z (Mitte des Kontakts auf der Aufnahme ab Ende A), seite ('0°', '90°', … der Aufnahme,
    Kastenprofil) bzw. winkel (Umfangswinkel, Rundrohr), achswinkel (90 = senkrecht)} oder None (kein Rohr)."""
    if not (_ist_rohr(st) and _ist_rohr(auf)) or not auf.achse_global or not st.achse_global or not auf.laenge:
        return None
    r = auf._rahmen if getattr(auf, "_rahmen", None) is not None else (rahmen(auf) if rahmen else None)
    if r is None:
        return None
    tr = gp_Trsf()
    tr.SetTransformation(_rohr_ax3(auf))
    q = gp_Pnt(*mitte).Transformed(tr)
    if not -1 <= q.Z() <= auf.laenge + 1:
        return None
    theta = r["abw"].theta(q.X(), q.Y())
    cos = min(1.0, abs(sum(x * y for x, y in zip(st.achse_global, auf.achse_global))))
    out = dict(stecker=st.koerper, ende=ende.lower(), aufnahme=auf.koerper, z=round(q.Z(), 1),
               achswinkel=round(math.degrees(math.acos(cos)), 1))
    if r["kasten"]:
        out["seite"] = f"{round(theta / 90) % 4 * 90}°"
    else:
        out["winkel"] = round(theta % 360, 1)
    return out


NETZ_ARTEN = {"A": "Außenwand", "I": "Innenwand", "EA": "Anfangsschnitt", "EB": "Endschnitt", "K": "Innenkontur",
              "G": "Gravur", "AN": "Anbauteil", "GA": "Gravur Anbauteil"}


def dreiecksnetz(lok, faces, art_flaeche, konturen, zmin, groesse):
    """Dreiecksnetz des Teils (lokal, Rohrachse = Z, Z ab 0) mit der Art je Fläche und den Schnittkonturen auf der
    Außenhaut als Linienzüge. Koordinaten auf 0,01 mm gerundet."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopAbs import TopAbs_REVERSED
    abw = min(0.5, max(0.02, (groesse or 40) / 250))
    BRepMesh_IncrementalMesh(lok, abw, False, 0.35, True)
    punkte, dreiecke = [], {}
    for i in range(1, faces.Extent() + 1):
        f = TopoDS.Face(faces.FindKey(i))
        ort = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, ort)
        if tri is None:
            continue
        tr = ort.Transformation()
        basis = len(punkte) // 3
        for j in range(1, tri.NbNodes() + 1):
            q = tri.Node(j).Transformed(tr)
            punkte += [round(q.X(), 2), round(q.Y(), 2), round(q.Z() - zmin, 2)]
        umdrehen = f.Orientation() == TopAbs_REVERSED
        liste = dreiecke.setdefault(art_flaeche.get(i, "K"), [])
        for j in range(1, tri.NbTriangles() + 1):
            a, b, c = tri.Triangle(j).Get()
            liste += [basis + a - 1, basis + c - 1, basis + b - 1] if umdrehen else \
                [basis + a - 1, basis + b - 1, basis + c - 1]
    linien = {}
    for art_, kanten in konturen:
        for e in kanten:
            c = BRepAdaptor_Curve(TopoDS.Edge(e))
            u0, u1 = c.FirstParameter(), c.LastParameter()
            n = max(2, min(120, int(_kantenlaenge(e) / max(abw * 4, 0.5)) + 1))
            zug = []
            for k in range(n + 1):
                q = c.Value(u0 + (u1 - u0) * k / n)
                zug += [round(q.X(), 2), round(q.Y(), 2), round(q.Z() - zmin, 2)]
            linien.setdefault(art_, []).append(zug)
    return dict(p=punkte, t=dreiecke, l=linien)


def gewinde_vorschlag(bohrungen, tabelle=None, tol=0.05):
    """Ordnet Bohrungsdurchmesser einem Kernloch zu. Ergebnis z. B. '4xM6' (so in Angebot AG übernehmbar). Nur Vorschlag."""
    tabelle = tabelle or KERNLOCH
    out = []
    for d, n in bohrungen.items():
        for gew, kern in tabelle:
            if abs(d - kern) <= tol:
                out.append(f"{n}x{gew}")
                break
    return "; ".join(out)


# Vorgabe Konturklassen, wenn in den Maschinen-Stammdaten nichts eingetragen ist
KLEIN_BIS, MITTEL_BIS = 10.0, 50.0


def konturklassen(innen_liste, klein_bis=KLEIN_BIS, mittel_bis=MITTEL_BIS):
    """Teilt Innenkonturen nach Größe (größtes Hüllmaß) ein: klein ≤ klein_bis < mittel ≤ mittel_bis < groß.
    Ergebnis: {'klein': (Anzahl, Länge), 'mittel': ..., 'gross': ...}"""
    out = {"klein": [0, 0.0], "mittel": [0, 0.0], "gross": [0, 0.0]}
    for groesse, laenge in innen_liste:
        groesse = round(groesse, 2)  # Ø10 genau auf der Grenze zählt als klein
        k = "klein" if groesse <= klein_bis else "mittel" if groesse <= mittel_bis else "gross"
        out[k][0] += 1
        out[k][1] += laenge
    return {k: tuple(v) for k, v in out.items()}


def bohrungen_text(bohrungen):
    return "; ".join(f"{n}xØ{f'{d:g}'.replace('.', ',')}" for d, n in bohrungen.items())


def _rohnetz(t, shape):
    """Nicht messbares Teil: Dreiecksnetz des Körpers unverändert in Dateilage (Art 'N'), damit die 3D-Ansicht zeigt,
    welches Teil fehlt und wo es in der Baugruppe sitzt. Lage = Dateikoordinaten (Ursprung, Z, X)."""
    try:
        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(shape, TopAbs_FACE, faces)
        if not faces.Extent():
            return
        groesse = math.sqrt(sum(x * x for x in t.huelle)) if t.huelle else 0.0
        t.netz = dreiecksnetz(shape, faces, {i: "N" for i in range(1, faces.Extent() + 1)}, [], 0.0,
                              max(10.0, groesse / 20))
        t.netz["lage"] = [0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0]
    except Exception:  # 3D-Ansicht darf die Messung nie verhindern
        t.netz = None


VERBUNDKERN = "Verbundkern"


def _in_kammer(t, kern):
    """Liegt der Körper kern ganz im Hüllprisma des Hohlprofils t (alle Eckpunkte höchstens halbe Diagonale des
    Querschnitts von der Rohrachse und zwischen den Enden)? Zwei gekreuzte Streben gleicher Hülle (Rahmengestell
    23.10.2026: Schwerpunkt der einen im Hohlraum der anderen) sind so kein Verbundprofil."""
    if not t.achse_global or not t.ende_a_global:
        return True
    a, o = gp_Vec(*t.achse_global), gp_Pnt(*t.ende_a_global)
    r = math.hypot(t.abm_a, t.abm_b or t.abm_a) / 2 + 0.1
    for v in _liste(kern, TopAbs_VERTEX):
        w = gp_Vec(o, BRep_Tool.Pnt_s(TopoDS.Vertex(v)))
        z = w.Dot(a)
        if z < -0.1 or z > t.laenge + 0.1 or w.Crossed(a).Magnitude() > r:
            return False
    return True


def _verbund_pruefen(teile, koerper):
    """Verbundprofil (Patrick 22.10.2026, F6 a: nur melden): ein Körper, der ganz in der Kammer eines Hohlprofils
    liegt (Kern aus Kunststoff, Dämmung o. ä.), wird nicht als eigenes Teil übernommen (Profilform 'Verbundkern'),
    das Hohlprofil bekommt einen Hinweis und damit den Prüfstatus 'prüfen'."""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.TopAbs import TopAbs_OUT
    if len(teile) < 2:
        return
    boxen = []
    for _, k in koerper:
        b = Bnd_Box()
        BRepBndLib.Add_s(k, b)
        boxen.append(b)
    for i, (t, (_, k)) in enumerate(zip(teile, koerper)):
        if not t.kammern:
            continue
        bi = boxen[i]
        for j, (u, (_, kj)) in enumerate(zip(teile, koerper)):
            bj = boxen[j]
            if i == j or u.verbund or bj.IsOut(bi) or not all(
                    bi.CornerMin().Coord(n) - 0.01 <= bj.CornerMin().Coord(n) and
                    bj.CornerMax().Coord(n) <= bi.CornerMax().Coord(n) + 0.01 for n in (1, 2, 3)):
                continue
            p = GProp_GProps()
            BRepGProp.VolumeProperties_s(kj, p)
            c = BRepClass3d_SolidClassifier(k, p.CentreOfMass(), 1e-6)
            if c.State() != TopAbs_OUT or not _in_kammer(t, kj):
                continue
            u.verbund = f"Kern in der Kammer von Körper {t.koerper}"
            u.profilform, u.bauteiltyp = VERBUNDKERN, ""
            u.hinweise.append(f"Verbundkern (z. B. Kunststoff) in Körper {t.koerper}: nicht übernommen")
            t.verbund = (t.verbund + ", " if t.verbund else "") + f"Kern Körper {u.koerper}"
            t.hinweise.append(f"Verbundprofil: Kern (Körper {u.koerper}) in der Kammer, nur gemeldet – Schneiddaten "
                              "und Kalkulation prüfen")


# Einstellungen des Programms für die Messung (STEP-Import.exe --flach-laenge/--gekantet-anteil), Vorgaben wie oben
EINSTELLBAR = {"flach_laenge": "FLACHSTAHL_LAENGE", "gekantet_anteil": "GEKANTET_ANTEIL", "naht_spalt": "NAHT_SPALT"}


STEGE = None    # größeres Profil gleicher Form („Form|A|B|Wand“): Winkel/U als virtuelles Bauteil (step_schenkel)
VIRTUELL = None     # Ordner für die virtuellen Bauteile als STEP (virtuell_ablegen) oder None


def einstellen(werte):
    """Grenzwerte der Erkennung aus den Einstellungen setzen ({Name aus EINSTELLBAR: Wert}, None = Vorgabe), das
    größere Profil für Winkel/U mit Stegen (Schlüssel stege, step_schenkel) und den Ordner für die virtuellen Bauteile
    als STEP (Schlüssel virtuell, virtuell_ablegen)."""
    global STEGE, VIRTUELL
    STEGE = (werte or {}).get("stege") or None
    VIRTUELL = (werte or {}).get("virtuell") or None
    vorgabe = {"flach_laenge": 3.0, "gekantet_anteil": 0.85, "naht_spalt": 3.0}
    for name, glob in EINSTELLBAR.items():
        v = (werte or {}).get(name)
        globals()[glob] = float(v) if v is not None else vorgabe[name]


@dataclass
class Gelesen:
    """Eine gelesene STEP-Datei: Körper wie lies_step_info, Name (Dateiname ohne Endung) und gleiche Körper
    (_instanzen: {Körpernummer: (Nummer des Vorbilds, Verschiebung)}), die nur einmal gemessen werden."""
    name: str
    koerper: list
    info: dict
    gleich: dict


def datei_lesen(pfad, name=None):
    """STEP-Datei lesen (lies_step_info) und gleiche Körper suchen. Wirft ValueError, wenn sie nicht lesbar ist."""
    import os
    koerper, info = lies_step_info(pfad)
    einzeln = os.environ.get("STEP_MESSEN_EINZELN")         # nur für Tests: jeden Körper selbst messen
    return Gelesen(name or _Path(pfad).stem, koerper, info, {} if einzeln else _instanzen(koerper))


def _instanzen(koerper):
    """Körper, die nur verschobene Kopien eines früheren sind (dieselbe Geometrie im CAD, z. B. 8 gleiche Stützen
    einer Baugruppe): {Nummer: (Nummer des Vorbilds, Verschiebung (x, y, z))}. Gedrehte oder gespiegelte Kopien
    werden einzeln gemessen, weil die Messung Ende A und die Lage der Konturen nach der Lage im Raum wählt."""
    gleich, vorbilder = {}, []
    for nr, (art, k) in enumerate(koerper, start=1):
        if art != "Volumenkörper":
            continue
        for vnr, vk in vorbilder:
            if not k.IsPartner(vk):
                continue
            rel = k.Location().Transformation().Multiplied(vk.Location().Transformation().Inverted())
            m = rel.HVectorialPart()
            if abs(rel.ScaleFactor() - 1) < 1e-12 and all(abs(m.Value(a, b) - (a == b)) < 1e-12
                                                          for a in (1, 2, 3) for b in (1, 2, 3)):
                v = rel.TranslationPart()
                gleich[nr] = (vnr, (v.X(), v.Y(), v.Z()))
                break
        else:
            vorbilder.append((nr, k))
    return gleich


def koerper_messen(gel, i, netz=False, flach_bis=FLACHSTAHL_BIS, auslassen=None):
    """Körper i (ab 1) einer gelesenen Datei messen: Teil mit Importdaten, Bauteilname und Rohnetz, wenn nicht
    messbar. Das Teil lässt sich zwischen Prozessen übergeben (ohne _rahmen, siehe teil_uebergeben)."""
    art, k = gel.koerper[i - 1]
    info = gel.info
    auslassen = auslassen or {}
    if i in auslassen:
        t = Teil(datei=gel.name, koerper=i)
        t.hinweise.append(f"nicht gemessen: {auslassen[i]}")
    elif art == "Flächenmodell offen":
        t = Teil(datei=gel.name, koerper=i)
        t.hinweise.append("Flächenmodell nicht geschlossen, nicht messbar")
    else:
        try:
            t = analysiere(k, gel.name, i, netz, flach_bis)
        except Exception as e:  # Messung dieses Körpers gescheitert: melden, andere Körper weiter messen
            t = Teil(datei=gel.name, koerper=i)
            t.hinweise.append(f"Messung fehlgeschlagen: {e or type(e).__name__}")
    t.einheit, t.meldungen = info["einheit"], info["meldungen"]
    t.bauteil, t.pfad, t.knoten = info["bauteile"].get(i, ("", "", ""))
    t.struktur = info["struktur"]
    if t.meldungen:
        t.hinweise.append(f"STEP-Leser meldet: {t.meldungen[0]}"
                          + (f" (+{len(t.meldungen) - 1} weitere)" if len(t.meldungen) > 1 else ""))
    _koerper_daten(t, k, art)
    if netz and not t.netz:
        _rohnetz(t, k)
    if t.alternative is not None:       # Importdaten gelten für beide Arten
        for n in ("einheit", "meldungen", "koerperart", "gueltig", "volumen", "oberflaeche", "n_flaechen",
                  "n_kanten", "huelle", "bauteil", "pfad", "knoten", "struktur"):
            setattr(t.alternative, n, getattr(t, n))
    t._rohr = getattr(t, "_rahmen", None) is not None       # Hohlprofil mit Abwicklung (Anbauteile)
    return t


def teil_uebergeben(t):
    """Teil ohne die OpenCascade-Daten (_rahmen), damit es sich an einen anderen Prozess schicken lässt."""
    t.__dict__.pop("_rahmen", None)
    if t.alternative is not None:
        t.alternative.__dict__.pop("_rahmen", None)
    return t


def _instanz(vorbild, nr, info, v):
    """Teil für Körper nr als verschobene Kopie des gemessenen Vorbilds (Lage um v verschoben)."""
    import copy
    rahmen = vorbild.__dict__.pop("_rahmen", None)
    try:
        t = copy.deepcopy(vorbild)
    finally:
        if rahmen is not None:
            vorbild._rahmen = rahmen
    t.koerper = nr
    t.bauteil, t.pfad, t.knoten = info["bauteile"].get(nr, ("", "", ""))
    for x in (t, t.alternative):
        if x is None:
            continue
        if x is not t:
            x.koerper, x.bauteil, x.pfad, x.knoten = nr, t.bauteil, t.pfad, t.knoten
        if x.ende_a_global:
            x.ende_a_global = tuple(a + b for a, b in zip(x.ende_a_global, v))
    if rahmen is not None:
        tr = gp_Trsf()
        tr.SetTranslation(gp_Vec(*v))
        t._rahmen = dict(rahmen, solid=rahmen["solid"].Moved(TopLoc_Location(tr)))
    return t


def datei_abschliessen(gel, teile, netz=False, flach_bis=FLACHSTAHL_BIS, auslassen=None):
    """Gemessene Teile {Körpernummer: Teil} einer Datei vervollständigen: Kopien für gleiche Körper, dann die
    Auswertungen über die ganze Baugruppe (Anbauteile, Verbundprofile, Nahtkandidaten). Ergebnis: Liste der Teile
    in der Reihenfolge der Körper. auslassen[n + 1] (n = Zahl der Körper): diese Auswertungen auslassen."""
    koerper, info = gel.koerper, gel.info
    auslassen = dict(auslassen or {})
    for i, (vnr, _) in gel.gleich.items():         # Kopien eines ausgelassenen Körpers ebenso
        if vnr in auslassen and i not in auslassen:
            auslassen[i] = auslassen[vnr]
    out = []
    for i in range(1, len(koerper) + 1):
        if i in teile:
            out.append(teile[i])
        elif i in gel.gleich and gel.gleich[i][0] in teile and i not in auslassen:
            vnr, v = gel.gleich[i]
            t = _instanz(teile[vnr], i, info, v)
            if netz and t.netz and "lage" in t.netz:     # Rohnetz in Dateilage: für diese Lage neu
                t.netz = None
                _rohnetz(t, koerper[i - 1][1])
            out.append(t)
        else:
            out.append(koerper_messen(gel, i, netz, flach_bis, auslassen))

    def rahmen(t):          # Abwicklung eines Rohrs, das in einem anderen Prozess gemessen wurde: neu messen
        if getattr(t, "_rahmen", None) is None:
            t._rahmen = getattr(koerper_messen(gel, t.koerper, False, flach_bis), "_rahmen", None)
        return t._rahmen
    n = len(koerper)
    if n + 1 in auslassen:
        if out:
            out[0].hinweise.append(f"Anbauteile, Verbund und Nahtkandidaten nicht bestimmt: {auslassen[n + 1]}")
        naehte = []
    else:
        try:
            _beruehrende_anbauteile(out, koerper, netz, rahmen)
        except Exception:  # Zuordnung der Baugruppe darf die Messung nie verhindern
            pass
        try:
            _verbund_pruefen(out, koerper)
        except Exception:  # wie oben
            pass
        stand = dict(vollstaendig=True)
        try:
            naehte = _nahtkandidaten(out, koerper, info.get("struktur"), rahmen, stand)
        except Exception:  # Nahtkandidaten sind ein Vorschlag: nie die Messung verhindern
            naehte, stand["vollstaendig"] = [], False
        if stand["vollstaendig"] and out:
            out[0].ohne_naht = _ohne_naht(out, koerper, naehte)
    for t in out:
        t.naehte = naehte
        if t.alternative is not None:
            t.alternative.naehte = naehte
    for t in out:
        teil_uebergeben(t)
        t.__dict__.pop("_rohr", None)
    return out


def analysiere_datei(pfad, netz=False, flach_bis=FLACHSTAHL_BIS, auslassen=None, melden=None, gel=None):
    """Alle Körper einer STEP-Datei messen. Je Körper ein Teil, auch für nicht messbare (Flächenmodell offen,
    Messfehler) – mit Hinweis statt Maßen. Wirft ValueError, wenn die Datei nicht lesbar ist.
    auslassen = {Körpernummer: Grund}: diese Körper nicht messen (z. B. Zeitlimit überschritten), nur Importdaten
    und Rohnetz; n + 1 = die Auswertungen über die Baugruppe. melden(i, n): vor jedem gemessenen Körper aufgerufen
    (i = 0: Datei gelesen, i = n + 1: Auswertungen), für Fortschritt und Zeitlimit. Gleiche Körper (verschobene
    Kopien) werden nur einmal gemessen. gel: schon gelesene Datei (datei_lesen)."""
    gel = gel or datei_lesen(pfad)
    if not gel.koerper:
        t = Teil(datei=gel.name, koerper=0, einheit=gel.info["einheit"], meldungen=gel.info["meldungen"])
        t.hinweise.append("Kein Körper und keine Fläche in der Datei")
        return [t]
    n = len(gel.koerper)
    auslassen = auslassen or {}
    if melden:
        melden(0, n)
    teile = {}
    for i in range(1, n + 1):
        if i in gel.gleich and i not in auslassen:
            continue
        if melden:
            melden(i, n)
        teile[i] = koerper_messen(gel, i, netz, flach_bis, auslassen)
    if melden:
        melden(n + 1, n)
    return datei_abschliessen(gel, teile, netz, flach_bis, auslassen)
