"""Geometrieprüfung, Toleranzverwaltung und Reparatur-Protokoll des STEP-Imports (Master-Auftrag Patrick 24.11.2026
„CAD-Importkern auf höchstem technischem Niveau“, Abschnitte 4, 7 und 11).

Grundsatz: Die Messung rechnet weiter mit dem Körper GENAU wie aus der STEP-Datei gelesen (Patrick-Regel 25.10.2026:
Konturen immer zu 100 % wie die STEP). Dieses Modul prüft nur, protokolliert und bewertet:

1. Datei (datei_kopf): STEP-Schema (AP203/AP214/AP242), erzeugendes CAD-System, Längeneinheit mit Umrechnung in mm,
   Genauigkeit der Datei (UNCERTAINTY_MEASURE_WITH_UNIT) und die Prüfwerte des Original-CAD (CAx-IF „Geometric
   Validation Properties“: Volumen, Oberfläche, Schwerpunkt je Bauteil), soweit die Datei sie enthält.
2. Körper (koerper_pruefen): größte und mittlere Toleranz der Kanten/Punkte/Flächen nach dem Einlesen (OpenCascade heilt
   beim Einlesen und darf Toleranzen dabei bis read.maxprecision.val = 1 mm vergrößern), offene und falsch orientierte
   Kanten, Freiformflächen, bei ungültigem Körper die Fehlerarten (Selbstüberschneidung, Lücken, kleine/entartete
   Kanten, ungültige Flächen).
3. Reparatur-Probe (reparatur_probe), nur bei ungültigen oder offenen Körpern: ShapeFix_Shape an einer KOPIE mit der
   Genauigkeit der Datei und höchstens REPARATUR_MAX_TOL, vorher/nachher geprüft und verglichen. Klassen:
   1 = automatisch und sicher reparierbar (danach gültig, Abweichung im Rahmen der Messgenauigkeit),
   2 = reparierbar mit möglicher Genauigkeitsabweichung, 3 = nicht zuverlässig reparierbar.
   Nur wenn die Messung des Originals scheitert und die Reparatur Klasse 1 ist, misst step_geometrie den reparierten
   Körper (mit Hinweis und Protokoll); sonst bleibt alles wie gelesen.
4. Datei-Abgleich (datei_pruefen): Volumen/Oberfläche/Schwerpunkt gegen die Prüfwerte des Original-CAD und doppelte
   (deckungsgleiche) Körper.

Toleranzen werden nie pauschal erhöht, um Fehler zu verdecken: die Grenzen unten sind Bewertungsgrenzen, keine
Rechentoleranzen.
"""
import re
from pathlib import Path

TOL_FEIN = 1e-3         # mm: größte Toleranz bis hier = „fein“ (deutlich unter der Messgenauigkeit 0,01 mm)
TOL_NORMAL = 1e-2       # mm: bis hier „normal“ (= Messgenauigkeit der Referenztests, TOL_MASS)
TOL_GROB = 0.1          # mm: bis hier „grob“ (Konturen evtl. ungenau), darüber „kritisch“
REPARATUR_MAX_TOL = 0.01   # mm: größte Toleranz, die eine Reparatur setzen darf (nicht mehr als die Messgenauigkeit)
SICHER_HUELLE = 1e-3    # mm: Klasse 1 nur, wenn sich der Hüllquader um höchstens so viel ändert
SICHER_VOLUMEN = 1e-5   # relativ: und das Volumen um höchstens so viel
MIT_ABWEICHUNG_HUELLE = 0.1   # mm: Klasse 2 bis hier, darüber Klasse 3
REPARATUR_FLAECHEN_MAX = 5000  # Körper mit mehr Flächen: keine Reparatur-Probe (Dauer), nur Prüfung
FEHLER_FLAECHEN_MAX = 300      # höchstens so viele ungültige Flächen einzeln untersuchen
GVP_ABW_OK = 1e-3       # relativ: Volumen/Oberfläche bis 0,1 % Abweichung = bestätigt (CAx-IF: Produktion 0,5 %)
GVP_ABW_WARN = 5e-3     # relativ: über 0,5 % = Abweichung (rot), dazwischen „prüfen“
GVP_SP_OK = 0.02        # mm (+ 0,1 % der Größe): Schwerpunkt bestätigt
GVP_INDEX_MAX_MB = 100  # größere Dateien: Prüfwerte nicht auflösen (Index aller Einträge wäre zu groß)

FAKTOR_MM = {"mm": 1.0, "cm": 10.0, "dm": 100.0, "m": 1000.0, "km": 1e6, "inch": 25.4, "ft": 304.8}
SCHEMAS = (("AP242", (b"AP242", b"MANAGED_MODEL_BASED")), ("AP214", (b"AUTOMOTIVE_DESIGN",)),
           ("AP203", (b"CONFIG_CONTROL_DESIGN", b"EXPLICIT_DRAUGHTING", b"AP203")))
STATUS = ("korrekt", "unsicher", "reparierbar", "fehlerhaft")   # Ampel je Körper (Importanalyse)
FEHLER_TEXT = {
    "ungueltige_flaechen": "ungültige Flächen",
    "selbstueberschneidung": "Selbstüberschneidung einer Kontur",
    "luecken": "Lücken zwischen Kanten",
    "kleine_kanten": "sehr kleine Kanten",
    "entartete_kanten": "entartete Kanten",
    "offene_kanten": "offene Kanten (Körper nicht geschlossen)",
    "falsch_orientiert": "falsch orientierte Kanten (Schale verdreht)",
    "kein_volumen": "Volumen null oder negativ",
    "nicht_geschlossen": "nicht geschlossen (Flächenmodell)",
}


# ---------------------------------------------------------------------------------------------- Datei
def datei_kopf(pfad, einheit=""):
    """Angaben der STEP-Datei: schema, system (erzeugendes CAD), einheit, faktor_mm, unsicherheit_mm (Genauigkeit
    der Datei, None = keine Angabe), gvp {Bauteilname: {volumen, flaeche, schwerpunkt}} (Prüfwerte des Original-CAD,
    in mm), gvp_hinweis. Nie eine Ausnahme: was nicht lesbar ist, bleibt leer."""
    out = dict(schema="", system="", einheit=einheit or "", faktor_mm=FAKTOR_MM.get(einheit), unsicherheit_mm=None,
               gvp={}, gvp_hinweis="")
    try:
        p = Path(pfad)
        if p.suffix.lower() not in (".step", ".stp"):
            return out
        daten = p.read_bytes()
    except OSError:
        return out
    kopf = daten[:20000].upper()
    i = kopf.find(b"FILE_SCHEMA")
    teil = kopf[i:i + 300] if i >= 0 else b""
    out["schema"] = next((n for n, merk in SCHEMAS if any(m in teil for m in merk)), "unbekannt" if teil else "")
    m = re.search(rb"FILE_NAME\s*\((.*?)\)\s*;", daten[:20000], re.S)
    if m:
        texte = re.findall(rb"'((?:[^']|'')*)'", m.group(1))
        # FILE_NAME(name, zeit, (autor), (organisation), preprocessor_version, originating_system, authorisation)
        sys_ = [t.decode("latin-1", "replace").strip() for t in texte[-3:-1]] if len(texte) >= 4 else []
        out["system"] = " / ".join(dict.fromkeys(s for s in reversed(sys_) if s))[:120]
    werte = [float(x) for x in re.findall(rb"UNCERTAINTY_MEASURE_WITH_UNIT\s*\(\s*(?:LENGTH_MEASURE\s*\()?\s*"
                                          rb"([0-9.Ee+-]+)", daten)[:50] if _zahl(x) is not None]
    f = out["faktor_mm"] or 1.0
    if werte:
        out["unsicherheit_mm"] = max(werte) * f      # die gröbste Angabe der Datei zählt
    if re.search(rb"(?i)'geometric validation property'", daten):
        if len(daten) > GVP_INDEX_MAX_MB * 1e6:
            out["gvp_hinweis"] = f"Prüfwerte des CAD vorhanden, Datei über {GVP_INDEX_MAX_MB} MB: nicht ausgewertet"
        else:
            try:
                out["gvp"] = _gvp(daten, f)
            except Exception as e:  # noqa: BLE001 – Prüfwerte sind Zusatz
                out["gvp_hinweis"] = f"Prüfwerte des CAD nicht lesbar: {type(e).__name__}"
    return out


def _zahl(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _gvp(daten, faktor):
    """Geometric Validation Properties (CAx-IF Recommended Practices GVP 4.6): PROPERTY_DEFINITION('geometric
    validation property', …, #ref) → PROPERTY_DEFINITION_REPRESENTATION(#pd, #rep) → REPRESENTATION('volume' |
    'surface area' | 'centroid', (#item), #ctx) mit MEASURE_REPRESENTATION_ITEM(…, VOLUME_MEASURE(v) | AREA_MEASURE(a),
    #einheit) bzw. CARTESIAN_POINT('centre point', (x, y, z)). #ref = PRODUCT_DEFINITION_SHAPE, SHAPE_ASPECT oder
    SHAPE_REPRESENTATION; daraus der Bauteilname (PRODUCT). Werte in mm (Einheit der Datei umgerechnet)."""
    text = daten.decode("latin-1", "replace")
    ent = {}
    for m in re.finditer(r"#(\d+)\s*=\s*([^;]*?)\s*;", text, re.S):
        ent[int(m.group(1))] = m.group(2)

    def typ(e):
        return (ent.get(e) or "").split("(", 1)[0].strip().upper()

    def args(e):
        return [int(x) for x in re.findall(r"#(\d+)", ent.get(e) or "")]

    def strings(e):
        return re.findall(r"'((?:[^']|'')*)'", ent.get(e) or "")

    pdr, sdr = {}, {}       # Rückverweise: Eigenschaft → Darstellung, Darstellung → Produktform
    for nr, inhalt in ent.items():
        k = inhalt.split("(", 1)[0].strip().upper()
        if k == "PROPERTY_DEFINITION_REPRESENTATION":
            a = args(nr)
            if len(a) >= 2:
                pdr.setdefault(a[0], []).append(a[1])
        elif k == "SHAPE_DEFINITION_REPRESENTATION":
            a = args(nr)
            if len(a) >= 2:
                sdr[a[1]] = a[0]

    def produkt(ref, tiefe=0):
        if tiefe > 6 or ref not in ent:
            return ""
        k = typ(ref)
        if k == "PRODUCT":
            s = strings(ref)
            return (s[1] if len(s) > 1 and s[1] else s[0] if s else "").replace("''", "'")
        if k in ("SHAPE_REPRESENTATION", "ADVANCED_BREP_SHAPE_REPRESENTATION",
                 "MANIFOLD_SURFACE_SHAPE_REPRESENTATION") or "SHAPE_REPRESENTATION" in k:
            return produkt(sdr.get(ref, -1), tiefe + 1)
        a = args(ref)
        if k == "SHAPE_ASPECT":
            return produkt(a[0] if a else -1, tiefe + 1)
        if k in ("PRODUCT_DEFINITION_SHAPE", "PRODUCT_DEFINITION", "PRODUCT_DEFINITION_FORMATION",
                 "PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE"):
            return produkt(a[0] if a else -1, tiefe + 1)
        return ""

    out = {}
    for nr, inhalt in ent.items():
        if not inhalt.upper().startswith("PROPERTY_DEFINITION(") or "geometric validation property" not in \
                inhalt.lower():
            continue
        a = args(nr)
        name = produkt(a[-1]) if a else ""
        for rep in pdr.get(nr, ()):
            s = strings(rep)
            art = (s[0] if s else "").lower()
            for item in args(rep):
                inh = ent.get(item) or ""
                ku = inh.upper()
                if art == "volume" and "VOLUME_MEASURE" in ku:
                    v = _zahl((re.search(r"VOLUME_MEASURE\s*\(\s*([0-9.Ee+-]+)", inh, re.I) or [None, None])[1])
                    if v is not None:
                        out.setdefault(name, {})["volumen"] = v * faktor ** 3
                elif art in ("surface area", "wetted area") and "AREA_MEASURE" in ku:
                    v = _zahl((re.search(r"AREA_MEASURE\s*\(\s*([0-9.Ee+-]+)", inh, re.I) or [None, None])[1])
                    if v is not None:
                        out.setdefault(name, {})["flaeche"] = v * faktor ** 2
                elif art == "centroid" and ku.startswith("CARTESIAN_POINT"):
                    xyz = re.search(r"\(\s*([0-9.Ee+-]+)\s*,\s*([0-9.Ee+-]+)\s*,\s*([0-9.Ee+-]+)\s*\)", inh)
                    if xyz:
                        out.setdefault(name, {})["schwerpunkt"] = [float(x) * faktor for x in xyz.groups()]
        if len(out) >= 2000:
            break
    return out


# ---------------------------------------------------------------------------------------------- Körper
def toleranz_stufe(t):
    if t is None:
        return ""
    return "fein" if t <= TOL_FEIN else "normal" if t <= TOL_NORMAL else "grob" if t <= TOL_GROB else "kritisch"


def _toleranzen(shape):
    from OCP.ShapeAnalysis import ShapeAnalysis_ShapeTolerance
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_SHAPE, TopAbs_VERTEX
    st = ShapeAnalysis_ShapeTolerance()
    return dict(max=st.Tolerance(shape, 1, TopAbs_SHAPE), mittel=st.Tolerance(shape, 0, TopAbs_SHAPE),
                punkte=st.Tolerance(shape, 1, TopAbs_VERTEX), kanten=st.Tolerance(shape, 1, TopAbs_EDGE),
                flaechen=st.Tolerance(shape, 1, TopAbs_FACE))


def _schale_pruefen(shape):
    """(offene Kanten, falsch orientierte Kanten) der Schalen."""
    from OCP.ShapeAnalysis import ShapeAnalysis_Shell
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    sa = ShapeAnalysis_Shell()
    sa.LoadShells(shape)
    sa.CheckOrientedShells(shape, True)

    def zahl(c):
        n, ex = 0, TopExp_Explorer(c, TopAbs_EDGE)
        while ex.More():
            n += 1
            ex.Next()
        return n
    offen = zahl(sa.FreeEdges()) if sa.HasFreeEdges() else 0
    falsch = zahl(sa.BadEdges()) if sa.HasBadEdges() else 0
    return offen, falsch


def _fehlerarten(shape, unsicherheit):
    """Fehlerarten eines ungültigen Körpers je Fläche: {Code: Anzahl}."""
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.ShapeAnalysis import ShapeAnalysis_Wire
    from OCP.TopAbs import TopAbs_FACE, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    prec = max(unsicherheit or 1e-7, 1e-7)
    out = {}
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    n = 0
    while ex.More() and n < FEHLER_FLAECHEN_MAX:
        f = TopoDS.Face_s(ex.Current()) if hasattr(TopoDS, "Face_s") else TopoDS.Face(ex.Current())
        ex.Next()
        if BRepCheck_Analyzer(f).IsValid():
            continue
        n += 1
        out["ungueltige_flaechen"] = out.get("ungueltige_flaechen", 0) + 1
        wx = TopExp_Explorer(f, TopAbs_WIRE)
        while wx.More():
            w = TopoDS.Wire_s(wx.Current()) if hasattr(TopoDS, "Wire_s") else TopoDS.Wire(wx.Current())
            wx.Next()
            try:
                sw = ShapeAnalysis_Wire(w, f, prec)
                for code, pruef in (("selbstueberschneidung", sw.CheckSelfIntersection),
                                    ("luecken", lambda: sw.CheckGaps3d()),
                                    ("kleine_kanten", lambda: sw.CheckSmall(prec)),
                                    ("entartete_kanten", sw.CheckDegenerated)):
                    if pruef():
                        out[code] = out.get(code, 0) + 1
            except Exception:  # noqa: BLE001 – einzelne Prüfung nicht möglich: weiter
                pass
    return out


def _kenndaten(shape):
    """Volumen, Oberfläche, Hüllquader (min/max), Schwerpunkt eines Körpers."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, p)
    vol, sp = p.Mass(), p.CentreOfMass()
    q = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, q)
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    h = None
    if not box.IsVoid():
        a, b = box.CornerMin(), box.CornerMax()
        h = (a.X(), a.Y(), a.Z(), b.X(), b.Y(), b.Z())
    return dict(volumen=abs(vol), flaeche=q.Mass(), huelle=h, schwerpunkt=(sp.X(), sp.Y(), sp.Z()))


def _gueltig(shape):
    from OCP.BRepCheck import BRepCheck_Analyzer
    return bool(BRepCheck_Analyzer(shape).IsValid())


def _anzahl(shape, typ):
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher as TopTools_IndexedMapOfShape
    from OCP.TopExp import TopExp
    m = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, typ, m)
    return m.Extent()


def reparatur_probe(shape, unsicherheit=None):
    """ShapeFix_Shape an einer Kopie (das Original bleibt unverändert). Ergebnis (protokoll, reparierter Körper oder
    None). protokoll: klasse 1/2/3, text, vorher/nachher {gueltig, toleranz_max, offene_kanten}, abweichung
    {volumen_rel, flaeche_rel, huelle_mm, schwerpunkt_mm}. Ohne Zeitangaben: das Ergebnis ist reproduzierbar."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.ShapeFix import ShapeFix_Shape
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    prec = min(max(unsicherheit or 1e-7, 1e-7), REPARATUR_MAX_TOL)
    vorher = _kenndaten(shape)
    v_tol = _toleranzen(shape)["max"]
    v_offen, v_falsch = _schale_pruefen(shape)
    prot = dict(klasse=3, text="", vorher=dict(gueltig=_gueltig(shape), toleranz_max=v_tol, offene_kanten=v_offen),
                nachher=None, abweichung=None, genauigkeit_mm=prec, max_toleranz_mm=REPARATUR_MAX_TOL)
    try:
        kopie = BRepBuilderAPI_Copy(shape, True, False).Shape()
        fix = ShapeFix_Shape(kopie)
        fix.SetPrecision(prec)
        fix.SetMinTolerance(prec)
        fix.SetMaxTolerance(max(REPARATUR_MAX_TOL, prec))
        fix.Perform()
        neu = fix.Shape()
    except Exception as e:  # noqa: BLE001
        prot.update(text=f"Reparatur gescheitert: {type(e).__name__}")
        return prot, None
    feste = []
    ex = TopExp_Explorer(neu, TopAbs_SOLID)
    while ex.More():
        feste.append(ex.Current())
        ex.Next()
    koerper = (TopoDS.Solid_s(feste[0]) if hasattr(TopoDS, "Solid_s") else TopoDS.Solid(feste[0])) \
        if len(feste) == 1 else None
    ziel = koerper if koerper is not None else neu
    nachher = _kenndaten(ziel)
    n_gueltig = _gueltig(ziel)
    n_tol = _toleranzen(ziel)["max"]
    n_offen = _schale_pruefen(ziel)[0]
    prot["nachher"] = dict(gueltig=n_gueltig, toleranz_max=n_tol, offene_kanten=n_offen, koerper=len(feste))
    dv = abs(nachher["volumen"] - vorher["volumen"]) / max(vorher["volumen"], 1e-9)
    df = abs(nachher["flaeche"] - vorher["flaeche"]) / max(abs(vorher["flaeche"]), 1e-9)
    dh = max(abs(a - b) for a, b in zip(nachher["huelle"], vorher["huelle"])) \
        if nachher["huelle"] and vorher["huelle"] else None
    ds = sum((a - b) ** 2 for a, b in zip(nachher["schwerpunkt"], vorher["schwerpunkt"])) ** 0.5
    prot["abweichung"] = dict(volumen_rel=dv, flaeche_rel=df, huelle_mm=dh, schwerpunkt_mm=ds)
    sicher = n_gueltig and koerper is not None and n_offen == 0 and dh is not None and dh <= SICHER_HUELLE \
        and (dv <= SICHER_VOLUMEN or v_falsch) and df <= SICHER_VOLUMEN and n_tol <= REPARATUR_MAX_TOL
    # falsch orientierte Flächen: das Volumen VOR der Reparatur ist ohne Bedeutung (Vorzeichen je Fläche), es zählen
    # Lage (Hülle) und Oberfläche
    if sicher:
        prot.update(klasse=1, text="automatisch und sicher reparierbar (Abweichung unter der Messgenauigkeit)")
    elif n_gueltig and koerper is not None and dh is not None and dh <= MIT_ABWEICHUNG_HUELLE:
        prot.update(klasse=2, text=f"reparierbar mit Abweichung (Hülle {dh:.4f} mm, Volumen {dv * 100:.3f} %): "
                                   "nicht automatisch übernommen")
    else:
        grund = "danach weiterhin ungültig" if not n_gueltig else "kein einzelner Volumenkörper" if koerper is None \
            else f"Abweichung zu groß (Hülle {dh if dh is not None else 0:.3f} mm)"
        prot.update(klasse=3, text=f"nicht zuverlässig reparierbar: {grund}")
    return prot, (koerper if prot["klasse"] == 1 else None)


def koerper_pruefen(shape, art, gueltig=None, unsicherheit=None, volumen=None, reparatur=True):
    """Geometrieprüfung eines Körpers wie gelesen. Ergebnis (prüfung, reparierter Körper oder None); prüfung:
    status (korrekt/unsicher/reparierbar/fehlerhaft), toleranz {max, mittel, punkte, kanten, flaechen, stufe},
    offene_kanten, falsch_orientiert, freiform_flaechen, flaechen, fehler {Code: Anzahl}, hinweise, reparatur
    (Protokoll der Probe oder None)."""
    from OCP.ShapeAnalysis import ShapeAnalysis_ShapeContents
    from OCP.TopAbs import TopAbs_FACE
    out = dict(status="korrekt", toleranz=None, offene_kanten=0, falsch_orientiert=0, freiform_flaechen=0,
               flaechen=0, fehler={}, hinweise=[], reparatur=None, eingelesen=art)
    repariert = None
    try:
        tol = _toleranzen(shape)
        tol["stufe"] = toleranz_stufe(tol["max"])
        out["toleranz"] = tol
        inhalt = ShapeAnalysis_ShapeContents()
        inhalt.Perform(shape)
        out["freiform_flaechen"] = inhalt.NbBSplibeSurf() + inhalt.NbBezierSurf()
        out["flaechen"] = _anzahl(shape, TopAbs_FACE)
        offen, falsch = _schale_pruefen(shape)
        out["offene_kanten"], out["falsch_orientiert"] = offen, falsch
        if gueltig is None:
            gueltig = _gueltig(shape)
        fehler = {}
        if art == "Flächenmodell offen":
            fehler["nicht_geschlossen"] = 1
        if offen and art != "Flächenmodell offen":
            fehler["offene_kanten"] = offen
        if falsch:
            fehler["falsch_orientiert"] = falsch
        if volumen is not None and art != "Flächenmodell offen" and volumen <= 1e-9:
            fehler["kein_volumen"] = 1
        if not gueltig and out["flaechen"]:
            fehler.update(_fehlerarten(shape, unsicherheit))
        out["fehler"] = fehler
        h = out["hinweise"]
        if tol["stufe"] in ("grob", "kritisch"):
            h.append(f"Toleranz nach dem Einlesen bis {tol['max']:.3g} mm ({tol['stufe']}): Konturen können um "
                     "diesen Betrag ungenau sein")
        if unsicherheit and unsicherheit > TOL_NORMAL:
            h.append(f"Genauigkeit der STEP-Datei nur {unsicherheit:.3g} mm (gröber als die Messgenauigkeit "
                     f"{TOL_NORMAL:g} mm)")
        if unsicherheit and tol["max"] > max(10 * unsicherheit, 1e-4):
            h.append(f"Toleranz durch Heilung beim Einlesen vergrößert ({unsicherheit:.3g} → {tol['max']:.3g} mm)")
        if art == "aus Flächenmodell genäht":
            h.append("aus Flächen genäht (Nähtoleranz 0,01 mm)")
        if out["freiform_flaechen"]:
            h.append(f"{out['freiform_flaechen']} Freiformfläche(n) (B-Spline/Bézier)")
        if fehler and reparatur and art != "Flächenmodell offen" and out["flaechen"] <= REPARATUR_FLAECHEN_MAX:
            out["reparatur"], repariert = reparatur_probe(shape, unsicherheit)
        elif fehler and out["flaechen"] > REPARATUR_FLAECHEN_MAX:
            h.append(f"keine Reparatur-Probe (über {REPARATUR_FLAECHEN_MAX} Flächen)")
        if fehler:
            k = (out["reparatur"] or {}).get("klasse")
            out["status"] = "reparierbar" if k in (1, 2) else "fehlerhaft"
        elif tol["stufe"] in ("grob", "kritisch") or art == "aus Flächenmodell genäht" or \
                (unsicherheit or 0) > TOL_NORMAL:
            out["status"] = "unsicher"
    except Exception as e:  # noqa: BLE001 – Prüfung ist Zusatz, die Messung läuft trotzdem
        out["status"] = "unsicher"
        out["hinweise"].append(f"Geometrieprüfung nicht möglich: {type(e).__name__}")
    return out, repariert


def kurztext(q):
    """Eine Zeile für Hinweise und Tabellen."""
    if not q:
        return ""
    teile = []
    if q.get("fehler"):
        teile.append(", ".join(f"{n}× {FEHLER_TEXT.get(c, c)}" for c, n in q["fehler"].items()))
    r = q.get("reparatur")
    if r:
        teile.append(f"Reparatur Klasse {r['klasse']}: {r['text']}")
    tol = q.get("toleranz") or {}
    if tol.get("max") is not None:
        teile.append(f"Toleranz {tol['max']:.2g} mm ({tol.get('stufe')})")
    ref = q.get("cad_referenz")
    if ref:
        teile.append(f"CAD-Prüfwerte: {ref['status']}")
    if q.get("doppelt_zu"):
        teile.append(f"deckungsgleich mit Körper {q['doppelt_zu']}")
    return "; ".join(teile)


# ---------------------------------------------------------------------------------------------- Datei-Abgleich
def _rel(a, b):
    return abs(a - b) / max(abs(b), 1e-9)


def cad_abgleich(gruppen, gvp):
    """gruppen [(Bauteilname, [(Körpernummer, volumen, flaeche, schwerpunkt_bauteil)])] (je Einbau eine Gruppe) gegen die Prüfwerte gvp
    {Name: {volumen, flaeche, schwerpunkt}}. Ergebnis {Körpernummer: abgleich} mit abgleich = {status bestätigt/
    prüfen/abweichung, volumen_rel, flaeche_rel, schwerpunkt_mm, quelle}. Ein Bauteil aus mehreren Körpern wird
    als Summe verglichen (Volumen, Fläche)."""
    out = {}
    namen = {(n or "").strip().lower(): n for n in gvp}
    for name, koerper in gruppen:
        ref = gvp.get(name) or gvp.get(namen.get((name or "").strip().lower(), "\0"))
        if ref is None and len(gvp) == 1 and len(gruppen) == 1:
            ref = next(iter(gvp.values()))          # Einzelteil-Datei: die einzigen Prüfwerte
        if not ref:
            continue
        v = sum(k[1] or 0 for k in koerper)
        f = sum(k[2] or 0 for k in koerper)
        abg = dict(quelle="Prüfwerte aus der STEP-Datei (Original-CAD)", volumen_rel=None, flaeche_rel=None,
                   schwerpunkt_mm=None)
        if ref.get("volumen"):
            abg["volumen_rel"] = _rel(v, ref["volumen"])
        if ref.get("flaeche"):
            abg["flaeche_rel"] = _rel(f, ref["flaeche"])
        if ref.get("schwerpunkt") and len(koerper) == 1 and koerper[0][3]:
            abg["schwerpunkt_mm"] = sum((a - b) ** 2 for a, b in zip(koerper[0][3], ref["schwerpunkt"])) ** 0.5
        rel = [x for x in (abg["volumen_rel"], abg["flaeche_rel"]) if x is not None]
        groesse = max(abs(x) for x in ref.get("schwerpunkt") or [1.0])
        sp_ok = abg["schwerpunkt_mm"] is None or abg["schwerpunkt_mm"] <= GVP_SP_OK + 1e-3 * groesse
        if not rel and abg["schwerpunkt_mm"] is None:
            continue
        if all(x <= GVP_ABW_OK for x in rel) and sp_ok:
            abg["status"] = "bestätigt"
        elif all(x <= GVP_ABW_WARN for x in rel):
            abg["status"] = "prüfen"
        else:
            abg["status"] = "abweichung"
        for k in koerper:
            out[k[0]] = abg
    return out


def datei_pruefen(koerper, gleich, bauteile, kopf, volumen):
    """Datei-Abgleich nach dem Messen. koerper = [(Art, Shape)], gleich = verschobene Kopien {nr: (vorbild, v)},
    bauteile {nr: (Name, Pfad, Knoten)}, kopf = datei_kopf, volumen {nr: (volumen, flaeche)}. Ergebnis
    {"doppelt": {nr: vorbild}, "cad": {nr: abgleich}}."""
    doppelt = {}
    for nr, (vnr, v) in gleich.items():         # verschobene Kopie ohne Verschiebung = doppelter Körper
        if max(abs(x) for x in v) <= 1e-6:
            doppelt[nr] = vnr
    # nicht als Kopie gespeichert, aber deckungsgleich (z. B. zweimal eingefügt): gleiches Volumen, gleiche Hülle,
    # gleicher Schwerpunkt
    kand = {}
    for nr, (art, k) in enumerate(koerper, start=1):
        if art == "Flächenmodell offen" or nr in gleich or nr not in volumen:
            continue
        kand.setdefault(round(volumen[nr][0], 3), []).append(nr)
    for nrn in kand.values():
        if len(nrn) < 2:
            continue
        daten = {n: _kenndaten(koerper[n - 1][1]) for n in nrn[:50]}
        for j, a in enumerate(nrn[:50]):
            for b in nrn[:j]:
                da, db = daten[a], daten[b]
                if da["huelle"] and db["huelle"] and max(abs(x - y) for x, y in zip(da["huelle"], db["huelle"])) \
                        <= 1e-4 and sum((x - y) ** 2 for x, y in zip(da["schwerpunkt"], db["schwerpunkt"])) <= 1e-8 \
                        and abs(da["flaeche"] - db["flaeche"]) <= 1e-6 * max(da["flaeche"], 1):
                    doppelt.setdefault(a, b)
                    break
    cad = {}
    gvp = (kopf or {}).get("gvp") or {}
    if gvp:
        from OCP.TopLoc import TopLoc_Location
        gruppen = {}
        for nr, (art, k) in enumerate(koerper, start=1):
            if art == "Flächenmodell offen" or nr not in volumen:
                continue
            name, pfad, _ = bauteile.get(nr, ("", "", ""))
            gruppen.setdefault((pfad or name or ""), []).append(nr)
        je_name = {}
        for pfad, nrn in gruppen.items():
            name = bauteile.get(nrn[0], ("",))[0] if bauteile else ""
            sp = None
            if len(nrn) == 1 and any("schwerpunkt" in g for g in gvp.values()):
                try:    # Schwerpunkt in Bauteil-Koordinaten (ohne Einbaulage), wie ihn das CAD angibt
                    sp = _kenndaten(koerper[nrn[0] - 1][1].Located(TopLoc_Location()))["schwerpunkt"]
                except Exception:  # noqa: BLE001
                    sp = None
            je_name.setdefault(pfad, (name, [(n, volumen[n][0], volumen[n][1], sp) for n in nrn]))
        cad = cad_abgleich(list(je_name.values()), gvp)     # je Einbau eigener Abgleich, Prüfwerte nach Name
    return dict(doppelt=doppelt, cad=cad)


def datei_zusammenfassung(kopf, pruefungen):
    """Kennzahlen einer Datei für JSON und Importanalyse: Kopfangaben (ohne Prüfwerte-Liste), Zahl der Körper je
    Status, größte Toleranz, Reparaturen je Klasse, CAD-Abgleich je Status, doppelte Körper."""
    st = {s: 0 for s in STATUS}
    klassen, cad = {}, {}
    tol_max, doppelt = None, 0
    for q in pruefungen:
        if not q:
            continue
        st[q.get("status", "unsicher")] = st.get(q.get("status", "unsicher"), 0) + 1
        t = (q.get("toleranz") or {}).get("max")
        if t is not None:
            tol_max = t if tol_max is None else max(tol_max, t)
        r = q.get("reparatur")
        if r:
            klassen[str(r["klasse"])] = klassen.get(str(r["klasse"]), 0) + 1
        c = q.get("cad_referenz")
        if c:
            cad[c["status"]] = cad.get(c["status"], 0) + 1
        doppelt += bool(q.get("doppelt_zu"))
    k = dict(kopf or {})
    gvp = k.pop("gvp", {}) or {}
    return dict(schema=k.get("schema") or None, system=k.get("system") or None, einheit=k.get("einheit") or None,
                faktor_mm=k.get("faktor_mm"), unsicherheit_mm=k.get("unsicherheit_mm"),
                cad_pruefwerte=len(gvp), cad_pruefwerte_hinweis=k.get("gvp_hinweis") or None, status=st,
                toleranz_max=tol_max, toleranz_stufe=toleranz_stufe(tol_max) or None, reparaturen=klassen,
                cad_abgleich=cad, doppelte_koerper=doppelt)
