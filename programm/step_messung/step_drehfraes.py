"""Dreh- und Frästeile im STEP erkennen (Patrick 03.11.2026, Plan „Dreh- und Frästeile als Zukauf“, Freigabe alle a).

Die Profilmessung sucht immer einen gleichbleibenden Querschnitt; ein Dreh- oder Frästeil hat oft zufällig einen und
würde dann als Rohr oder Profil gelasert (Buchse Ø40/Ø25 -> Rundrohr 40 × 7,5, Fräsblock mit Tasche -> U-Profil,
Stufenwelle -> Rundstahl Ø20). Diese Prüfung kommt nach der Messung dazu: sie nimmt ein Teil nur aus „Rohr/Profil“
heraus (bauteiltyp und profilform „Drehteil“ bzw. „Frästeil“, Zukaufteil), die bisherige Messung bleibt als
alternative wählbar (Spalte Art im Prüfdialog). Die Messung eines Rohrs selbst ändert sie nie.

Drehteil: fast alle Flächen (DREH_ANTEIL der Oberfläche) liegen drehsymmetrisch um eine gemeinsame Achse (Zylinder,
Kegel, Radien, Stirnflächen senkrecht dazu); Querbohrungen, Schlüsselflächen und Gewinde sind als Zusatzbearbeitung
erlaubt. Drehteil wird es, sobald eins zutrifft: mehrere Außendurchmesser (Absatz, Einstich), mehrere Innendurchmesser
bzw. Sackbohrung, Fase/Kegel/Radius (Plan Frage 2 a). Glatter Rundstahl mit geraden Enden bleibt Vollmaterial, ein
glattes Rohr bleibt Rohr; nur kurze dickwandige Rohre (Buchse) werden Drehteil mit Prüfstatus „prüfen“ und Merkmal
„nur_abmessung“: das Programm stellt sie zurück auf Rohr, wenn das Profil in den Stammdaten steht (Frage 3 a).

Frästeil: gedrungener Körper (Länge höchstens GEDRUNGEN × zweitgrößtes Hüllmaß) überwiegend aus Ebenen (plus
Bohrungen, Radien, Fasen), der kein Blech, Rohr oder Rundstahl ist, und eins davon: Vollmaterial (Vierkant, Flachstahl,
offenes Sonderprofil, nicht messbar) mit Absatz, Tasche oder Fase (mehr als 6 Ebenen), oder ein offenes Profil
(U/L/C/T/I) ohne Normprofil mit dicker Wand (Wand ≥ WAND_DICK × kleineres Außenmaß) – dann mit „nur_abmessung“ und
„prüfen“ (das Programm prüft die Stammdaten).
"""
import math

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import (GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_SurfaceOfRevolution,
                         GeomAbs_Torus)
from OCP.BRep import BRep_Tool
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

import step_geometrie as g

DREH_ANTEIL = 0.85      # so viel der Oberfläche muss drehsymmetrisch um die Achse liegen (Rest: Querbohrung o. ä.)
FRAES_EBEN = 0.5        # so viel der Oberfläche eines Frästeils sind Ebenen
FREI_MAX = 0.05         # Freiformflächen (BSpline) höchstens so viel der Oberfläche
GEDRUNGEN = 3.0         # Frästeil/Buchse: Länge höchstens so viel × Breite bzw. Durchmesser
WAND_DICK = 0.2         # offenes Profil: Wand ab so viel × kleineres Außenmaß gilt als dick (Fräs- statt Walzprofil)
BUCHSE_WAND = 0.12      # Rohr: Wand ab so viel × Durchmesser (und kurz) gilt als Buchse (Drehteil-Verdacht)
WINKEL_TOL = 0.5        # Grad: Achsen gelten als gleich
ACHS_TOL = 0.05         # mm: Achse liegt auf der Hauptachse
DREHFRAES_ANTEIL = 0.6  # mit Lasche/Anbau außerhalb des Drehdurchmessers (Dreh-Fräs-Teil) genügt so viel
ANBAU_LAENGE = 1.5      # Dreh-Fräs-Teil mit Anbau: Rohr höchstens so viel × Ø lang (Ring, Flansch) oder dickwandig
ANBAU_MIN = 1.0         # mm: so weit muss ein Anbau über den größten Außendurchmesser hinausragen
BOHR_VOLL = 0.6         # Innenzylinder ab so viel des vollen Umfangs ist eine Bohrung (auch angeschnitten durch eine
                        # Querbohrung); weniger: Hohlkehle/Taschenecke
SACK = 0.8              # Bohrung auf der Achse kürzer als so viel × Länge: Sackbohrung
FORMEN_DREH = ("Rundstahl", "Rundrohr", "Sonderprofil", "offenes Sonderprofil", "")
FORMEN_FRAES_VOLL = ("Vierkantstahl", "Flachstahl", "offenes Sonderprofil", "Sonderprofil", "")
FORMEN_FRAES_OFFEN = ("U-Profil", "C-Profil", "L-Profil", "T-Profil", "I-/H-Träger")
DREHTEIL, FRAESTEIL = "Drehteil", "Frästeil"


def _v(d):
    return (d.X(), d.Y(), d.Z())


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _abstand_achse(p, o, d):
    """Abstand des Punkts p von der Achse (Punkt o, Richtung d, Einheitsvektor)."""
    w = _sub(p, o)
    t = _dot(w, d)
    q = (w[0] - t * d[0], w[1] - t * d[1], w[2] - t * d[2])
    return math.sqrt(_dot(q, q))


def flaechen(solid):
    """Flächen des Körpers: je Fläche dict(typ, flaeche, achse=(Punkt, Richtung) bei Dreh-Flächen, normale/punkt bei
    Ebenen, radius, konvex (Zylinder: außen), face)."""
    out = []
    ex = TopExp_Explorer(solid, TopAbs_FACE)
    while ex.More():
        f = TopoDS.Face(ex.Current())
        ex.Next()
        a = g._flaeche(f)
        if a <= 1e-6:
            continue
        s = BRepAdaptor_Surface(f)
        typ = s.GetType()
        e = dict(flaeche=a, face=f)
        if typ == GeomAbs_Plane:
            pl = s.Plane()
            n = _v(pl.Axis().Direction())
            e.update(typ="eben", normale=n, punkt=_v(pl.Location()))
        elif typ in (GeomAbs_Cylinder, GeomAbs_Cone, GeomAbs_Torus, GeomAbs_Sphere):
            geo = {GeomAbs_Cylinder: s.Cylinder, GeomAbs_Cone: s.Cone, GeomAbs_Torus: s.Torus,
                   GeomAbs_Sphere: s.Sphere}[typ]()
            ax = geo.Position().Axis() if typ != GeomAbs_Sphere else None
            e.update(typ={GeomAbs_Cylinder: "zylinder", GeomAbs_Cone: "kegel", GeomAbs_Torus: "torus",
                          GeomAbs_Sphere: "kugel"}[typ],
                     achse=(_v(ax.Location()), _v(ax.Direction())) if ax is not None else None,
                     mitte=_v(geo.Location()) if typ == GeomAbs_Sphere else None)
            if typ == GeomAbs_Cylinder:
                e["radius"] = geo.Radius()
                # außen (Welle) oder innen (Bohrung): Normale am Mittelpunkt der Parameterfläche gegen die Achse
                u = (s.FirstUParameter() + s.LastUParameter()) / 2
                v = (s.FirstVParameter() + s.LastVParameter()) / 2
                p = s.Value(u, v)
                o, d = e["achse"]
                w = _sub(_v(p), o)
                t = _dot(w, d)
                radial = (w[0] - t * d[0], w[1] - t * d[1], w[2] - t * d[2])
                n = (radial[0], radial[1], radial[2])
                konvex = True
                if f.Orientation() == TopAbs_REVERSED:
                    konvex = False
                e["konvex"] = konvex if _dot(n, n) > 1e-12 else True
                vs = [s.FirstVParameter(), s.LastVParameter()]
                e["z"] = (_dot(_sub(_v(s.Value(u, vs[0])), (0, 0, 0)), d), _dot(_sub(_v(s.Value(u, vs[1])), (0, 0, 0)), d))
        elif typ == GeomAbs_SurfaceOfRevolution:
            ax = s.AxeOfRevolution()
            e.update(typ="rotation", achse=(_v(ax.Location()), _v(ax.Direction())))
        else:
            e["typ"] = "frei"
        out.append(e)
    return out


def _parallel(a, b, tol=WINKEL_TOL):
    return abs(_dot(a, b)) >= math.cos(math.radians(tol))


def _senkrecht(a, b, tol=WINKEL_TOL):
    return abs(_dot(a, b)) <= math.sin(math.radians(tol))


def _koaxial(e, o, d):
    """Dreh-Fläche e liegt auf der Achse (o, d)."""
    if e["typ"] == "kugel":
        return e.get("mitte") is not None and _abstand_achse(e["mitte"], o, d) <= ACHS_TOL
    ax = e.get("achse")
    return ax is not None and _parallel(ax[1], d) and _abstand_achse(ax[0], o, d) <= ACHS_TOL


def _radius_max(flaechen_, o, d):
    """Größter Abstand der Eckpunkte der Flächen von der Achse (Lasche/Anbau außerhalb des Drehdurchmessers)."""
    r = 0.0
    for e in flaechen_:
        ex = TopExp_Explorer(e["face"], TopAbs_VERTEX)
        while ex.More():
            p = BRep_Tool.Pnt_s(TopoDS.Vertex(ex.Current()))
            ex.Next()
            r = max(r, _abstand_achse((p.X(), p.Y(), p.Z()), o, d))
    return r


def drehteil(fl, t=None, streng=False):
    """Merkmale eines Drehteils (dict) oder None. fl = flaechen(solid), t = bisherige Messung (für das Glatt-Rohr).
    streng: gemessen als Blech, Flachstahl oder Profil (Drehteil nur mit Absatz oder Radius)."""
    gesamt = sum(e["flaeche"] for e in fl)
    if gesamt <= 0:
        return None
    zyl = [e for e in fl if e["typ"] == "zylinder"]
    if not zyl:
        return None
    haupt = max(zyl, key=lambda e: e["flaeche"])
    o, d = haupt["achse"]
    dreh = [e for e in fl if e["typ"] in ("zylinder", "kegel", "torus", "kugel", "rotation") and _koaxial(e, o, d)]
    stirn = [e for e in fl if e["typ"] == "eben" and _parallel(e["normale"], d)]
    anteil = (sum(e["flaeche"] for e in dreh) + sum(e["flaeche"] for e in stirn)) / gesamt
    frei = sum(e["flaeche"] for e in fl if e["typ"] == "frei") / gesamt
    aussen = sorted({round(e["radius"], 2) for e in dreh if e["typ"] == "zylinder" and e["konvex"]})
    innen = sorted({round(e["radius"], 2) for e in dreh if e["typ"] == "zylinder" and not e["konvex"]})
    if not aussen or frei > FREI_MAX:
        return None
    # Lasche/Anbau über den größten Außendurchmesser hinaus (Ring mit Lasche, Flansch mit Ohr): Dreh-Fräs-Teil
    # Eine flache Kontur (nur zwei Stirnebenen, alles andere parallel zur Achse) ist ein Blech (lasern), kein Anbau.
    hoehen = {round(_dot(e["punkt"], d), 1) for e in stirn}
    prisma = len(hoehen) <= 2 and all(
        (e["typ"] == "eben" and _senkrecht(e["normale"], d)) or (e["typ"] == "zylinder" and _parallel(e["achse"][1], d))
        for e in fl if e not in stirn)
    r_anbau = 0.0 if prisma else _radius_max([e for e in fl if e not in dreh], o, d)
    anbau = r_anbau > aussen[-1] + ANBAU_MIN
    if anteil < (DREHFRAES_ANTEIL if anbau else DREH_ANTEIL):
        return None
    absatz = len(aussen) >= 2 or len(innen) >= 2
    if streng and not absatz and not any(e["typ"] == "torus" and _abstand_achse(e["achse"][0], o, d) <= ACHS_TOL
                                         for e in dreh):
        return None     # Blech/Flachstahl/Profil: nur mit Absatz oder Radius (eine Fase allein kann eine Senkung sein)
    if sum(e["flaeche"] for e in dreh) < 0.4 * gesamt:       # z. B. Scheibe: Stirnflächen groß, aber kein Drehteil?
        # Flansch/Scheibe mit Absatz (zwei Außen- oder Innendurchmesser) oder Anbau ist gedreht, eine glatte Scheibe
        # mit Löchern bleibt Blech bzw. Laserteil
        if not any(e["typ"] in ("kegel", "torus") for e in dreh) and len(aussen) < 2 and len(innen) < 2 \
                and not anbau:
            return None
    zs = [z for e in dreh if e["typ"] == "zylinder" for z in e["z"]]
    z0, z1 = min(zs), max(zs)
    for e in stirn:
        z = _dot(e["punkt"], d)
        z0, z1 = min(z0, z), max(z1, z)
    laenge = z1 - z0
    merkmale = []
    if anbau and innen and laenge > ANBAU_LAENGE * 2 * aussen[-1] and aussen[-1] - innen[-1] < BUCHSE_WAND * 2 * aussen[-1]:
        # langes dünnwandiges Rohr mit angeschweißtem Blech/Lasche: Rohr mit Anbauteil (step_anbau), kein Drehteil
        if anteil < DREH_ANTEIL:
            return None
        anbau = False
    if anbau:
        merkmale.append("Lasche/Anbau außerhalb Ø (gefräst)")
    if len(aussen) >= 2:
        merkmale.append(f"{len(aussen)} Außendurchmesser (Absatz/Einstich)")
    if len(innen) >= 2:
        merkmale.append(f"{len(innen)} Innendurchmesser (Innenabsatz)")
    # schräge Ebenen (Gehrung, Schrägschnitt) gibt es an Drehteilen nicht: ein Laserteil (Rohr mit Schrägschnitt)
    rest = [e for e in fl if e not in dreh and e not in stirn]
    if any(e["typ"] == "eben" and not _senkrecht(e["normale"], d) for e in rest):
        return None
    sack = [e for e in dreh if e["typ"] == "zylinder" and not e["konvex"] and abs(e["z"][1] - e["z"][0]) < SACK * laenge]
    if innen and len(innen) == 1 and sack:
        merkmale.append("Sackbohrung")
    if any(e["typ"] == "kegel" for e in dreh):
        merkmale.append("Fase/Kegel")
    if any(e["typ"] in ("torus", "kugel") for e in dreh):
        merkmale.append("Radius")
    if any(e["typ"] == "rotation" for e in dreh):
        merkmale.append("Drehkontur")
    zusatz = []
    bohr_rest = [e for e in rest if e["typ"] == "zylinder" and not e["konvex"]]
    if any(not _parallel(e["achse"][1], d) for e in bohr_rest):
        zusatz.append("Querbohrung")
    if any(_parallel(e["achse"][1], d) for e in bohr_rest):
        zusatz.append("Bohrungen axial/Lochkreis")
    if any(e["typ"] == "eben" and _senkrecht(e["normale"], d) for e in rest):
        zusatz.append("Schlüsselfläche/Abflachung")
    if any(e["typ"] == "frei" for e in rest):
        zusatz.append("Gewinde/Freiform")
    nur_abmessung = False
    if innen and len(aussen) == 1 and len(innen) == 1 and set(merkmale) <= {"Fase/Kegel", "Radius"}:
        # Rohr mit Fase/Radius am Ende (z. B. entgratet, angefast) bleibt Rohrlaserteil, außer es ist eine Buchse
        da, di = 2 * aussen[-1], 2 * innen[0]
        if not ((da - di) / 2 >= BUCHSE_WAND * da and laenge <= GEDRUNGEN * da):
            return None
    if not merkmale:
        # glatt: Rundstahl bleibt Vollmaterial; glattes Rohr nur als Buchse (kurz und dickwandig) verdächtig
        if not innen:
            return None
        da, di = 2 * aussen[-1], 2 * innen[0]
        wand = (da - di) / 2
        if not (wand >= BUCHSE_WAND * da and laenge <= GEDRUNGEN * da):
            return None
        merkmale.append(f"kurzes dickwandiges Rohr Ø{_mm(da)} × {_mm(wand)} (Buchse?)")
        nur_abmessung = True
    return dict(art=DREHTEIL, durchmesser=round(2 * aussen[-1], 2), laenge=round(laenge, 2),
                innen=round(2 * innen[0], 2) if innen else 0.0,
                durchmesser_liste=[round(2 * r, 2) for r in aussen], merkmale=merkmale, zusatz=zusatz,
                nur_abmessung=nur_abmessung, achse=list(d), kennwerte=_kennwerte_dreh(fl, dreh, stirn, rest, d,
                                                                         2 * r_anbau if anbau else None))


def _zylinder_gruppen(flaechen_):
    """Zylinderflächen gleicher Achse, gleichen Radius und gleicher Lage zusammen (eine Bohrung besteht im STEP oft
    aus zwei Halbschalen): je Gruppe dict(radius, z0, z1, flaeche)."""
    gruppen = {}
    for e in flaechen_:
        o, d = e["achse"]
        vz = 1
        if max(d, key=abs) < 0:         # Richtung eindeutig machen (z entlang der Achse dreht dann das Vorzeichen)
            d, vz = (-d[0], -d[1], -d[2]), -1
        t = _dot(o, d)
        p = (o[0] - t * d[0], o[1] - t * d[1], o[2] - t * d[2])
        z0, z1 = sorted(vz * z for z in e["z"])
        schl = (round(e["radius"], 1), tuple(round(x, 2) for x in d), tuple(round(x, 1) for x in p),
                round(z0, 1), round(z1, 1))
        x = gruppen.setdefault(schl, dict(radius=e["radius"], z0=z0, z1=z1, flaeche=0.0))
        x["flaeche"] += e["flaeche"]
    return list(gruppen.values())


def _abschnitte(gruppen):
    """Zylindergruppen als Abschnitte [{d, l, z}] (Durchmesser, Länge, Mitte entlang der eigenen Achse), z aufsteigend."""
    out = [dict(d=round(2 * x["radius"], 2), l=round(x["z1"] - x["z0"], 2), z=round((x["z0"] + x["z1"]) / 2, 2))
           for x in gruppen]
    return sorted(out, key=lambda x: x["z"])


def _cm2(x):
    return round(x / 100, 2)


def _kennwerte_dreh(fl, dreh, stirn, rest, d, anbau_d=None):
    """Kennwerte für den Richtpreis (drehfraes_preis): Abschnitte außen/innen, Einstiche, Fasen, Radien,
    Stirnflächen, Querbohrungen (axial = parallel zur Drehachse, z. B. Lochkreis), Schlüsselflächen, Durchmesser über
    eine Lasche/einen Anbau (anbau_d) und Flächen [cm²]."""
    aussen = _abschnitte(_zylinder_gruppen([e for e in dreh if e["typ"] == "zylinder" and e["konvex"]]))
    innen = _abschnitte(_zylinder_gruppen([e for e in dreh if e["typ"] == "zylinder" and not e["konvex"]]))
    einstiche = sum(1 for i in range(1, len(aussen) - 1)
                    if aussen[i]["d"] < aussen[i - 1]["d"] - 0.1 and aussen[i]["d"] < aussen[i + 1]["d"] - 0.1)
    bohr = [e for e in rest if e["typ"] == "zylinder" and not e["konvex"]]
    quer = [dict(a, axial=True) for a in _abschnitte(_zylinder_gruppen([e for e in bohr if _parallel(e["achse"][1], d)]))]
    quer += _abschnitte(_zylinder_gruppen([e for e in bohr if not _parallel(e["achse"][1], d)]))
    schluessel = [e for e in rest if e["typ"] == "eben" and _senkrecht(e["normale"], d)]
    wand = None                     # dünnste Wand zwischen Außen- und Innendurchmesser (Machbarkeit)
    for a in aussen:
        for b in innen:
            if abs(a["z"] - b["z"]) < (a["l"] + b["l"]) / 2 - 0.01:
                w = (a["d"] - b["d"]) / 2
                wand = w if wand is None else min(wand, w)
    return dict(aussen=aussen, innen=innen, einstiche=einstiche, wand_min=round(wand, 2) if wand is not None else None,
                fasen=sum(1 for e in dreh if e["typ"] == "kegel"),
                radien=sum(1 for e in dreh if e["typ"] in ("torus", "kugel")),
                konturen=sum(1 for e in dreh if e["typ"] == "rotation"),
                stirn=len(stirn), stirn_flaeche=_cm2(sum(e["flaeche"] for e in stirn)),
                dreh_flaeche=_cm2(sum(e["flaeche"] for e in dreh)),
                querbohrungen=quer, schluessel=len(schluessel), anbau_d=round(anbau_d, 2) if anbau_d else None,
                schluessel_flaeche=_cm2(sum(e["flaeche"] for e in schluessel)),
                frei_flaeche=_cm2(sum(e["flaeche"] for e in rest if e["typ"] == "frei")),
                flaeche=_cm2(sum(e["flaeche"] for e in fl)))


def _kennwerte_fraes(fl, richtungen, stufen):
    """Kennwerte eines Frästeils für den Richtpreis: Ebenen, Bohrungen (ganze Zylinder) mit Ø und Tiefe,
    Innenradien (Teilzylinder, z. B. Taschenecken), Außenradien, Fasen/Senkungen, Bearbeitungsrichtungen, Stufen
    und Flächen [cm²]."""
    eben = [e for e in fl if e["typ"] == "eben"]
    bohr, ecken = [], []
    for x in _zylinder_gruppen([e for e in fl if e["typ"] == "zylinder" and not e["konvex"]]):
        voll = 2 * math.pi * x["radius"] * (x["z1"] - x["z0"])
        (bohr if voll > 0 and x["flaeche"] >= BOHR_VOLL * voll else ecken).append(x)
    tiefe = 0.0                     # tiefste Tasche/Absatz bis zur Außenfläche auf der offenen Seite (Machbarkeit)
    for r in richtungen:
        ebenen = []                 # (Höhe entlang r, Seite: +1 = Fläche zeigt nach +r)
        for e in eben:
            if _parallel(e["normale"], r):
                sg = 1 if _dot(e["normale"], r) > 0 else -1
                if e["face"].Orientation() == TopAbs_REVERSED:
                    sg = -sg
                ebenen.append((_dot(e["punkt"], r), sg))
        if len(ebenen) < 3:
            continue
        h0, h1 = min(h for h, _ in ebenen), max(h for h, _ in ebenen)
        for h, sg in ebenen:
            if h0 + 0.01 < h < h1 - 0.01:
                # Boden einer Tasche: zur offenen Seite hin liegt keine Gegenfläche (sonst ist es eine Wand/Breite)
                gegen = any(sg2 == -sg and (h2 - h) * sg > 0.01 for h2, sg2 in ebenen if h0 + 0.01 < h2 < h1 - 0.01)
                if not gegen:
                    tiefe = max(tiefe, (h1 - h) if sg > 0 else (h - h0))
    return dict(ebenen=len(eben), eben_flaeche=_cm2(sum(e["flaeche"] for e in eben)),
                bohrungen=_abschnitte(bohr), innenradien=len(ecken),
                innenradius_min=round(min(x["radius"] for x in ecken), 2) if ecken else None,
                taschentiefe=round(tiefe, 2),
                radien=sum(1 for e in fl if e["typ"] in ("torus", "kugel") or (e["typ"] == "zylinder" and e["konvex"])),
                fasen=sum(1 for e in fl if e["typ"] == "kegel"),
                richtungen=len(richtungen), stufen=stufen,
                kontur_flaeche=_cm2(sum(e["flaeche"] for e in fl) - sum(x["flaeche"] for x in bohr)),
                flaeche=_cm2(sum(e["flaeche"] for e in fl)))


def _mm(x):
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _bohr_richtungen(fl):
    """Richtungen der Bohrungen (ganze Zylinder innen, keine Hohlkehlen/Taschenecken), je Richtung einmal."""
    innen = [e for e in fl if e["typ"] == "zylinder" and not e["konvex"]]
    out = []
    for e in innen:
        o, d = e["achse"]
        z = sorted(e["z"])
        gruppe = [x for x in innen if abs(x["radius"] - e["radius"]) < 0.05 and _koaxial(x, o, d)
                  and abs(sorted(x["z"])[0] - z[0]) < 0.1]
        voll = 2 * math.pi * e["radius"] * (z[1] - z[0])
        if voll > 0 and sum(x["flaeche"] for x in gruppe) >= BOHR_VOLL * voll and not any(_parallel(d, r) for r in out):
            out.append(d)
    return out


def _block_mit_bohrung(fl):
    """Als Quadrat-/Rechteckrohr gemessen, aber innen nur Bohrungen und keine Innenwände (höchstens 6 größere Ebenen;
    kleine Reste wie flache Bohrungsgründe zählen nicht): ein gebohrter Block (Verteilerblock), kein Rohr."""
    gesamt = sum(e["flaeche"] for e in fl)
    gross = sum(1 for e in fl if e["typ"] == "eben" and e["flaeche"] >= 0.03 * gesamt)
    return gross <= 6 and bool(_bohr_richtungen(fl))


def fraesteil(fl, t, huelle, form=None, achse=None):
    """Merkmale eines Frästeils (dict) oder None. huelle = drei Hüllmaße (beliebige Lage, sortiert groß -> klein);
    form = Profilform, als die das Teil gilt (sonst die der Messung t), achse = Profilachse der Messung (offenes Profil:
    Absatz/Tasche nur entlang der Achse)."""
    if t is not None and form is None and (t.kammern or t.profilform in ("Rundrohr", "Rundstahl", "Quadratrohr", "Rechteckrohr",
                                                         "Blech", "Blech gekantet")):
        return None
    if form is None:
        form = t.profilform if t is not None else ""
    gesamt = sum(e["flaeche"] for e in fl)
    if gesamt <= 0 or len(huelle) != 3:
        return None
    eben = [e for e in fl if e["typ"] == "eben"]
    if sum(e["flaeche"] for e in eben) < FRAES_EBEN * gesamt:
        return None
    if sum(e["flaeche"] for e in fl if e["typ"] in ("frei", "rotation")) > FREI_MAX * gesamt:
        return None
    la, lb, lc = huelle
    if lb <= 0 or la > GEDRUNGEN * lb + 1e-6 or lc < 3.0:
        return None
    merkmale, nur_abmessung = [], False
    richtungen, stufen = [], 0
    for e in eben:
        if not any(_parallel(e["normale"], r) for r in richtungen):
            richtungen.append(e["normale"])
    if form in FORMEN_FRAES_VOLL:
        mehrseitig = len(_bohr_richtungen(fl)) >= 2
        if len(eben) <= 6 and not mehrseitig:
            return None             # Quader (auch mit Bohrungen von einer Seite): Vollmaterial gesägt bzw. Blech
        if mehrseitig:
            merkmale.append("Bohrungen aus mehreren Richtungen")
        for r in richtungen:
            hoehen = {round(_dot(e["punkt"], r) * (1 if _dot(e["normale"], r) > 0 else -1), 1)
                      for e in eben if _parallel(e["normale"], r)}
            stufen += max(0, len({abs(h) for h in hoehen}) - 2)
        if stufen:
            merkmale.append("Absatz/Tasche")
        if len(richtungen) > 3:
            merkmale.append("Fase/Schräge")
        if not merkmale:
            merkmale.append("Kontur gefräst")
    elif form in FORMEN_FRAES_OFFEN:
        if t.normprofil:
            return None
        klein = min(t.abm_a, t.abm_b) if t.abm_b else t.abm_a
        wand = max(t.wandstaerke, t.flanschdicke or 0.0, t.stegdicke or 0.0)
        if klein <= 0 or wand < WAND_DICK * klein:
            return None
        stufe = False
        if achse and len(achse) == 3:
            # Ebenen quer zur Profilachse auf mehr als zwei Höhen: Querschnitt ändert sich (Tasche, Absatz)
            hoehen = {round(abs(_dot(e["punkt"], achse)), 1) for e in eben if _parallel(e["normale"], achse)}
            stufe = len(hoehen) > 2
        if stufe:
            merkmale.append("Absatz/Tasche")
        else:
            merkmale.append(f"{form} ohne Normmaß mit dicker Wand {_mm(wand)} mm (aus dem Vollen?)")
            nur_abmessung = True
    else:
        return None
    kw = _kennwerte_fraes(fl, richtungen, stufen)
    # nur echte Bohrungen (ganze Innenzylinder), keine Biegeradien oder Taschenecken (Patrick 04.11.2026)
    return dict(art=FRAESTEIL, laenge=round(la, 2), breite=round(lb, 2), hoehe=round(lc, 2), merkmale=merkmale,
                zusatz=["Bohrungen"] if kw["bohrungen"] else [], nur_abmessung=nur_abmessung, kennwerte=kw)


VON_HAND = "von Hand gewählt"


def fraesteil_von_hand(fl, huelle):
    """Frästeil ohne Erkennung (Art von Hand umgestellt, Patrick 04.11.2026): Maße aus dem Hüllquader, Kennwerte für
    den Richtpreis wie beim erkannten Frästeil, Merkmal „von Hand gewählt“."""
    if len(huelle) != 3 or not fl:
        return None
    richtungen = []
    for e in fl:
        if e["typ"] == "eben" and not any(_parallel(e["normale"], r) for r in richtungen):
            richtungen.append(e["normale"])
    kw = _kennwerte_fraes(fl, richtungen, 0)
    la, lb, lc = huelle
    return dict(art=FRAESTEIL, laenge=round(la, 2), breite=round(lb, 2), hoehe=round(lc, 2), merkmale=[VON_HAND],
                zusatz=["Bohrungen"] if kw["bohrungen"] else [], nur_abmessung=True, kennwerte=kw)


def _huelle_ebenen(solid, fl):
    """Hüllmaße (groß -> klein) in den Richtungen der größten Ebenen (prismatische Frästeile in beliebiger Lage),
    None ohne zwei senkrechte Ebenenrichtungen."""
    flaeche = {}
    for e in fl:
        if e["typ"] != "eben":
            continue
        r = next((k for k in flaeche if _parallel(k, e["normale"])), None)
        if r is None:
            r = e["normale"]
        flaeche[r] = flaeche.get(r, 0.0) + e["flaeche"]
    richt = sorted(flaeche, key=flaeche.get, reverse=True)
    if not richt:
        return None
    a = richt[0]
    b = next((r for r in richt[1:] if _senkrecht(r, a)), None)
    if b is None:
        return None
    c = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    try:
        from OCP.BRep import BRep_Tool
        from OCP.TopAbs import TopAbs_VERTEX
        pkt = []
        ex = TopExp_Explorer(solid, TopAbs_VERTEX)
        while ex.More():
            pkt.append(_v(BRep_Tool.Pnt_s(TopoDS.Vertex(ex.Current()))))
            ex.Next()
        # Zylinder/Radien ohne Eckpunkte am Rand: Mantel-Punkte der Rundflächen mitnehmen
        for e in fl:
            if e["typ"] != "eben":
                s = BRepAdaptor_Surface(e["face"])
                for u in (0.0, 0.25, 0.5, 0.75, 1.0):
                    for v in (0.0, 0.5, 1.0):
                        uu = s.FirstUParameter() + u * (s.LastUParameter() - s.FirstUParameter())
                        vv = s.FirstVParameter() + v * (s.LastVParameter() - s.FirstVParameter())
                        pkt.append(_v(s.Value(uu, vv)))
    except Exception:
        return None
    if not pkt:
        return None
    m = [max(_dot(p, r) for p in pkt) - min(_dot(p, r) for p in pkt) for r in (a, b, c)]
    return sorted(m, reverse=True)


def _huelle(solid):
    """Hüllmaße (groß -> klein) im kleinsten umschreibenden Quader (Bnd_OBB), sonst achsparallel."""
    try:
        from OCP.BRepBndLib import BRepBndLib
        from OCP.Bnd import Bnd_OBB
        obb = Bnd_OBB()
        BRepBndLib.AddOBB_s(solid, obb, True, True, False)
        return sorted((2 * obb.XHSize(), 2 * obb.YHSize(), 2 * obb.ZHSize()), reverse=True)
    except Exception:  # Rückfall: Hüllquader in Dateilage
        x0, y0, z0, x1, y1, z1 = g._bbox(solid) if hasattr(g, "_bbox") else (0, 0, 0, 0, 0, 0)
        return sorted((x1 - x0, y1 - y0, z1 - z0), reverse=True)


def pruefen(solid, t, datei="", koerper=1, erzwingen=False):
    """Dreh- oder Frästeil? Dann ein neues Teil (bauteiltyp/profilform Drehteil bzw. Frästeil, drehfraes = Merkmale),
    sonst t unverändert. Biegerohre, Knickrahmen und Bleche prüft sie nicht. Die Messung t bleibt unverändert (auch
    ihre alternative): welche Art gilt, entscheidet step_arten.entscheiden (Patrick 04.11.2026).
    erzwingen: das Teil als Dreh- bzw. Frästeil messen, auch wenn es nicht so erkannt wird (Art von Hand wählbar):
    erst Drehteil, dann Frästeil, sonst Frästeil nach dem Hüllquader (Merkmal „von Hand gewählt“)."""
    if t is not None and (t.biegerohr or t.knick_schenkel) and not erzwingen:
        return t
    form = t.profilform if t is not None else ""
    blech = t is not None and (t.bauteiltyp == "Blech" or form == "Blech")
    block = None
    if erzwingen:
        fl = flaechen(solid)
    else:
        if t is not None and (t.bauteiltyp == "Blech gekantet" or form == "Blech gekantet"):
            return t
        if form in ("Quadratrohr", "Rechteckrohr") and t is not None:
            fl = flaechen(solid)
            if not _block_mit_bohrung(fl):
                return t
            block = "Vierkantstahl"     # gebohrter Block (Verteilerblock): als Vollmaterial prüfen
        elif not blech and form not in FORMEN_DREH + FORMEN_FRAES_VOLL + FORMEN_FRAES_OFFEN:
            return t
        else:
            fl = flaechen(solid)
    # Drehteil für jede Form (eine Rolle kann als Flachstahl/Blech, ein Flansch als T-Profil gemessen sein)
    info = drehteil(fl, t, streng=form not in FORMEN_DREH and not erzwingen) if block is None else None
    if info is None and (not blech or erzwingen):
        try:
            info = fraesteil(fl, t, _huelle_ebenen(solid, fl) or _huelle(solid), block,
                             achse=getattr(t, "achse_global", None))
        except Exception:  # erzwungen: dann nach dem Hüllquader
            if not erzwingen:
                raise
            info = None
    if info is None and erzwingen and t is not None and form in ("Rundrohr", "Rundstahl") and t.abm_a > 0:
        innen = max(0.0, t.abm_a - 2 * t.wandstaerke) if form == "Rundrohr" else 0.0
        info = dict(art=DREHTEIL, durchmesser=round(t.abm_a, 2), innen=round(innen, 2), laenge=round(t.laenge, 2),
                    durchmesser_liste=[round(t.abm_a, 2)], merkmale=[VON_HAND], zusatz=[], nur_abmessung=True,
                    kennwerte=None)
    if info is None and erzwingen:
        info = fraesteil_von_hand(fl, _huelle_ebenen(solid, fl) or _huelle(solid))
    if info is None:
        return t
    if info["art"] == DREHTEIL and info["nur_abmessung"] and form != "Rundrohr" and not erzwingen:
        return t                    # Buchsen-Verdacht nur bei gemessenen Rundrohren
    if erzwingen and VON_HAND not in info["merkmale"]:
        info["merkmale"] = list(info["merkmale"]) + [VON_HAND]
    v = g._volumen(solid)
    n = g.Teil(datei=datei, koerper=koerper)
    n.bauteiltyp = n.profilform = info["art"]
    if info["art"] == DREHTEIL:
        n.abm_a, n.abm_b, n.laenge = info["durchmesser"], info.get("innen") or 0.0, info["laenge"]
    else:
        n.abm_a, n.abm_b, n.laenge = info["breite"], info["hoehe"], info["laenge"]
    n.volumen = v
    info["volumen"] = round(v, 1)
    info["fingerabdruck"] = fingerabdruck(info, fl)
    n.drehfraes = info
    if t is not None:
        for name in ("einheit", "meldungen", "bauteil", "pfad", "knoten", "koerperart", "gueltig", "oberflaeche",
                     "n_flaechen", "n_kanten", "huelle", "achse_global", "ende_a_global", "x_global", "netz",
                     "struktur", "naehte", "ohne_naht"):
            if hasattr(t, name):
                setattr(n, name, getattr(t, name))
    unsicher = info["nur_abmessung"]
    n.sicherheit.update(profil="unsicher" if unsicher else "sicher", laenge="sicher", wandstaerke="sicher",
                        konturen="nicht ausgewertet")
    info["text"] = f"{info['art']} ({', '.join(info['merkmale'] + info['zusatz'])})"
    if unsicher and not erzwingen:  # nur dann „prüfen“ (Hinweis): das Programm stellt es zurück, wenn das Profil bekannt ist
        n.hinweise.append(f"{info['text']}: als Zukaufteil erkannt – prüfen, ob es gelasert wird")
    return n


def fingerabdruck(info, fl):
    """Geometrie-Kennung für Wiederholteile (gerundete Kennwerte): Art, Maße, Volumen, Flächenzahl je Typ."""
    zaehler = {}
    for e in fl:
        zaehler[e["typ"]] = zaehler.get(e["typ"], 0) + 1
    masse = ([info["durchmesser"], info.get("innen") or 0, info["laenge"]] if info["art"] == DREHTEIL else
             [info["laenge"], info["breite"], info["hoehe"]])
    return "|".join([info["art"][0]] + [f"{x:.0f}" for x in masse] + [f"{info['volumen'] / 1000:.0f}"]
                    + [f"{k}{zaehler[k]}" for k in sorted(zaehler)])
