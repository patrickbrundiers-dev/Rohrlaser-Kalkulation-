"""Abwicklungskern: schnelle Profilerkennung über die Flächenparametrisierung (Master-Auftrag Patrick 24.11.2026
„STEP-Import durch abwicklungsbasierte Schnittwegberechnung beschleunigen“).

Untersuchung (docs/system-audit/ABWICKLUNGSKERN_2411.md): Der Schneidweg eines Rohrs wird heute schon NICHT im 3D-Raum
geschnitten. step_geometrie._profil_messen nimmt die Kanten, an denen Schnittflächen auf die Außenhaut treffen, direkt
aus der STEP (exakte Kantenlänge) und wickelt sie für Form und Lage auf den Umfang ab (_Abwicklung, _umriss_uv). Die
Zeit geht vorher verloren: Achse und Querschnitt werden über viele ebene Schnitte durch den ganzen Körper gesucht
(BRepAlgoAPI_Section, im Mittel rund 34 je Teil: 3 × 7 für die Achse, bis zu 49 für den Querschnitt), weil nicht
bekannt ist, wo Bohrungen und Ausschnitte liegen.

Dieser Kern liest die Lage stattdessen aus den Flächen selbst ab:
1. Längsflächen: Ebenen und Zylinder der STEP sind exakt parametrisiert. Die Rohrachse ist die Richtung, zu der die
   Normalen der Ebenen senkrecht und die Achsen der Zylinder parallel stehen (größte Fläche). Freiformflächen
   (B-Spline) und Profile ohne klare Längsrichtung gehen an die bisherige Rechnung (Rückfall).
2. Merkmalskarte der Abwicklung: Jede Fläche, die nicht längs läuft (Bohrung, Ende, Gehrung, Ausschnitt) und jede
   Längsfläche, die nicht bis zu einem Ende reicht (Langloch-Wand, Tasche), belegt einen Bereich in Z (Rohrachse). Die
   freien Bereiche dazwischen enthalten nur den reinen Profilquerschnitt.
3. Genau dort werden drei ebene Schnitte gelegt (exakt, mit OpenCascade, wie bisher), die gleich sein müssen
   (Gegenprobe). Daraus kommen Mitte und Drehung des Rohrsystems, Profilform, Wandstärke und Querschnittsfläche mit der
   bisherigen Auswertung.

Der Rest der Messung (Flächen außen/innen/Schnitt, Konturen, Schneidweg aus den Original-Kanten, Abwicklung der
Konturen, Bohrungsarten) läuft unverändert. Die Schnittkonturen bleiben die Kanten der STEP: eine Rückübertragung aus
der Abwicklung auf das Rohr ist nicht nötig, nichts wird verschoben oder nachgebaut (Grundregel Patrick 25.10.2026).

Modus (Einstellung „abwicklungskern“, CLI --abwicklungskern, Umgebung RL_ABWICKLUNGSKERN):
  aus       bisherige Rechnung (Vorgabe, bis Patrick die neue freigibt)
  vergleich beide rechnen, Ergebnis der bisherigen, Unterschiede und Zeiten ins Protokoll (PROTOKOLL)
  an        neue Lage verwenden, wo sie sicher möglich ist, sonst automatisch die bisherige (Hybrid)
"""
import math
import os
import time

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_SurfaceOfExtrusion
from OCP.BRep import BRep_Tool
from OCP.TopAbs import TopAbs_FACE, TopAbs_VERTEX
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Ax3, gp_Dir, gp_Pnt, gp_Vec

import step_geometrie as g

MODI = ("aus", "vergleich", "an")
MODUS_START = os.environ.get("RL_ABWICKLUNGSKERN") if os.environ.get("RL_ABWICKLUNGSKERN") in MODI else "aus"
MODUS = MODUS_START

PARALLEL = 1e-6         # 1 − |cos|: Zylinderachse parallel zur Rohrachse
SENKRECHT = 1e-6        # |cos|: Ebenennormale senkrecht zur Rohrachse
LAENGS_ANTEIL = 0.6     # so viel der Oberfläche muss längs laufen (sonst kein gerades Profil mit konstantem Querschnitt)
EINDEUTIG = 0.15        # so viel weniger Längsfläche muss jede andere Richtung haben (sonst Platte: bisherige Rechnung)
RAND = 0.5              # mm: Abstand eines Schnitts von jedem Merkmal (Hüllquader samt Toleranz)
ENDE = 0.05             # mm: eine Längsfläche reicht bis zum Ende, wenn sie so nah daran endet
FREI_MIN = 2.0          # mm: kürzester freier Bereich, in den geschnitten wird
LAGEN = 3               # Schnitte (Gegenprobe: alle gleich)
KURZ = 0.1              # Anteil der Länge: kürzere Längsflächen an einem Ende gehören zur Zone des Endes
TOL_VOLUMEN = 1e-6      # relativ: Volumen höchstens Querschnitt × Länge (Merkmale nehmen nur weg)

PROTOKOLL_MAX = 5000    # so viele Einträge bleiben höchstens im Protokoll
PROTOKOLL = []          # je Körper: dict(methode, grund, zeit_s, …) – step_messen schreibt es in die Diagnose


_NEU_LAEUFT = False     # Modus vergleich: gerade wird die neue Rechnung gemacht


def neu_aktiv():
    """Neue Rechnung wirksam (Endlinien bereinigen, exakte Rundrohr-Normale): Modus an, oder im Modus vergleich während
    der neuen der beiden Rechnungen."""
    return MODUS == "an" or _NEU_LAEUFT


def neu_rechnen(fn, *a, **k):
    """fn mit wirksamer neuer Rechnung aufrufen (Modus vergleich)."""
    global _NEU_LAEUFT
    vorher, _NEU_LAEUFT = _NEU_LAEUFT, True
    try:
        return fn(*a, **k)
    finally:
        _NEU_LAEUFT = vorher


def modus_setzen(m):
    global MODUS
    MODUS = m if m in MODI else "aus"


def _richtung_key(v):
    """Richtung ohne Vorzeichen, gerundet (Gruppierung gleicher Achsen)."""
    x, y, z = v.X(), v.Y(), v.Z()
    k = max((x, y, z), key=abs)
    if k < 0:
        x, y, z = -x, -y, -z
    return (round(x, 6), round(y, 6), round(z, 6))


FREIFORM_TOL = 1e-4     # mm: Freiform-Fläche (B-Spline) gilt als Ebene/Zylinder, wenn sie so genau passt (N6)


def analytisch(f):
    """('E', gp_Pln) | ('Z', gp_Cylinder) | ('X', gp_Dir Extrusionsrichtung) | ('F', None): Grundform der Fläche. Freiformflächen (B-Spline-Rohre aus
    manchen CAD-Systemen) werden auf Ebene/Zylinder geprüft (GeomConvert_SurfToAnaSurf, Abweichung höchstens
    FREIFORM_TOL); die Fläche selbst bleibt unverändert, Schnitte und Kanten laufen auf der Originalgeometrie."""
    s = BRepAdaptor_Surface(TopoDS.Face(f))
    typ = s.GetType()
    if typ == GeomAbs_Plane:
        return "E", s.Plane()
    if typ == GeomAbs_Cylinder:
        return "Z", s.Cylinder()
    if typ == GeomAbs_SurfaceOfExtrusion:
        return "X", s.Direction()       # Extrusionsfläche (Ovalrohr, Sonderkontur): läuft längs der Richtung
    try:
        from OCP.Geom import Geom_CylindricalSurface, Geom_Plane
        from OCP.GeomConvert import GeomConvert_SurfToAnaSurf
        ana = GeomConvert_SurfToAnaSurf(BRep_Tool.Surface_s(TopoDS.Face(f))).ConvertToAnalytical(FREIFORM_TOL)
    except Exception:  # keine Grundform bestimmbar: Freiform
        return "F", None
    if isinstance(ana, Geom_Plane):
        return "E", ana.Pln()
    if isinstance(ana, Geom_CylindricalSurface):
        return "Z", ana.Cylinder()
    return "F", None


def flaechen(solid):
    """Flächen mit Typ, Fläche und Parametern: [(face, 'E'|'Z'|'X'|'F', Fläche, gp_Dir Normale/Achse/Extrusionsrichtung
    oder None)]."""
    out = []
    for f in g._liste(solid, TopAbs_FACE):
        typ, geo = analytisch(f)
        d = geo if typ == "X" else geo.Axis().Direction() if geo is not None else None
        out.append((f, typ, g._flaeche(f), d))
    return out


def _laengs(typ, d, achse):
    if typ == "E":
        return abs(d.Dot(achse)) < SENKRECHT
    if typ in ("Z", "X"):
        return 1 - abs(d.Dot(achse)) < PARALLEL
    return False


LAENGER = 1.5           # Flachstahl: die Längsrichtung ist so viel länger als jede andere fast gleich gute Richtung


def achse(fl, solid=None, mit_art=False):
    """Rohrachse aus den Flächen (gp_Dir) und Anteil der Längsflächen an der Oberfläche, oder (None, Anteil).
    Kandidaten: Achsen der Zylinder und Kreuzprodukte der Normalen der größten Ebenen; gewählt wird die mit der
    größten Längsfläche."""
    gesamt = sum(a for _, _, a, _ in fl) or 1.0
    kand = {}
    for _, typ, a, d in fl:
        if typ in ("Z", "X"):
            kand.setdefault(_richtung_key(d), d)
    ebenen = sorted(((a, d) for _, typ, a, d in fl if typ == "E"), key=lambda x: -x[0])[:12]
    gruppen = []
    for a, d in ebenen:
        if not any(abs(abs(d.Dot(x)) - 1) < 1e-9 for x in gruppen):
            gruppen.append(d)
    for i, a in enumerate(gruppen[:6]):
        for b in gruppen[i + 1:6]:
            v = gp_Vec(a.X(), a.Y(), a.Z()).Crossed(gp_Vec(b.X(), b.Y(), b.Z()))
            if v.Magnitude() > 1e-6:
                d = gp_Dir(v)
                kand.setdefault(_richtung_key(d), d)
    wertung = []
    for d in kand.values():
        wertung.append((sum(a for _, typ, a, n in fl if n is not None and _laengs(typ, n, d)) / gesamt, d))
    wertung.sort(key=lambda w: -w[0])
    if not wertung or wertung[0][0] < LAENGS_ANTEIL:
        a0 = wertung[0][0] if wertung else 0.0
        return (None, a0, "") if mit_art else (None, a0)
    anteil, beste = wertung[0]
    art = "flaechen"
    if len(wertung) > 1 and wertung[1][0] > anteil - EINDEUTIG:
        # zwei Richtungen fast gleich gut (Flachstahl, Platte): eindeutig nur über die Länge (Plan 2.0, N3)
        nah = [w for w in wertung if w[0] > anteil - EINDEUTIG]
        if solid is None:
            return None, -anteil
        pts = [BRep_Tool.Pnt_s(TopoDS.Vertex(v)) for v in g._liste(solid, TopAbs_VERTEX)]

        def ausdehnung(d):
            s = [p.X() * d.X() + p.Y() * d.Y() + p.Z() * d.Z() for p in pts]
            return max(s) - min(s) if s else 0.0
        lang = sorted(((ausdehnung(d), a, d) for a, d in nah), key=lambda x: -x[0])
        if len(lang) < 2 or lang[0][0] < LAENGER * lang[1][0]:
            return (None, -anteil, "") if mit_art else (None, -anteil)    # keine klar längste Richtung (Platte)
        _, anteil, beste = lang[0]
        art = "laenge"
    k = max((beste.X(), beste.Y(), beste.Z()), key=abs)       # wie _achse_grob: größter Anteil positiv
    if k < 0:
        beste = beste.Reversed()
    return (beste, anteil, art) if mit_art else (beste, anteil)


def freie_bereiche(lok_fl, zmin, zmax):
    """Freie Bereiche [(z0, z1)] der Merkmalskarte: Z-Bereiche ohne Merkmal, größter zuerst. Merkmal = Fläche, die
    nicht längs läuft (Bohrung, Ende, Gehrung, Ausschnitt), oder Längsfläche, die nicht von Ende zu Ende reicht
    (Langloch-Wand, Tasche, Lasche). Eine Wand reicht von Ende zu Ende, wenn sie an beiden Seiten an die Zone eines
    Endes stößt: an zmin/zmax oder an Flächen, die von dort ausgehen (Gehrung, Schrägschnitt, Ausklinkung am Ende)."""
    boxen = []
    for f, laengs in lok_fl:
        b = Bnd_Box()
        BRepBndLib.Add_s(f, b, False)
        if not b.IsVoid():
            boxen.append((b.CornerMin().Z(), b.CornerMax().Z(), laengs))
    # Zonen der Enden: zusammenhängende Kette von Nicht-Längsflächen und kurzen Längsflächen (Ringe, Ausklinkungen)
    # ab zmin bzw. zmax
    za, zb = zmin + ENDE, zmax - ENDE
    kurz = KURZ * (zmax - zmin)
    quer = sorted((z0, z1) for z0, z1, laengs in boxen if not laengs or z1 - z0 < kurz)
    for z0, z1 in quer:
        if z0 <= za:
            za = max(za, z1)
    for z0, z1 in sorted(quer, key=lambda q: -q[1]):
        if z1 >= zb:
            zb = min(zb, z0)
    belegt = []
    for z0, z1, laengs in boxen:
        if laengs and z0 <= za + ENDE and z1 >= zb - ENDE:
            continue        # Wand (von Ende zu Ende)
        belegt.append((z0 - RAND, z1 + RAND))
    belegt.sort()
    frei, lauf = [], zmin + RAND
    for z0, z1 in belegt:
        if z0 > lauf:
            frei.append((lauf, z0))
        lauf = max(lauf, z1)
    if zmax - RAND > lauf:
        frei.append((lauf, zmax - RAND))
    return sorted((f for f in frei if f[1] - f[0] >= FREI_MIN), key=lambda f: -(f[1] - f[0]))


def _stufe(lok_fl, zmin, zmax):
    """Gibt es eine Längsfläche, die weder von Ende zu Ende reicht noch kurz an einem Ende liegt (Tasche, Stufe)?"""
    kurz = KURZ * (zmax - zmin)
    for f, laengs in lok_fl:
        if not laengs:
            continue
        b = Bnd_Box()
        BRepBndLib.Add_s(f, b, False)
        if b.IsVoid():
            continue
        z0, z1 = b.CornerMin().Z(), b.CornerMax().Z()
        if z0 <= zmin + ENDE + RAND and z1 >= zmax - ENDE - RAND:
            continue
        if z1 - z0 < kurz and (z0 <= zmin + ENDE + RAND or z1 >= zmax - ENDE - RAND):
            continue
        return True
    return False


def _lagen(frei, n=LAGEN):
    """n Schnittlagen in den freien Bereichen: je Bereich (größte zuerst) die Mitte, reichen die Bereiche nicht, im
    größten auch bei 25 % und 75 % (krumme Anteile, damit kein Schnitt genau auf einer Kante liegt)."""
    zs = [(a + b) / 2 + 0.0137 * (b - a) for a, b in frei[:n]]
    a, b = frei[0]
    for anteil in (0.2537, 0.7463):
        if len(zs) >= n:
            break
        zs.append(a + anteil * (b - a))
    return sorted(zs)


def lage(solid):
    """Rohrsystem aus der Flächenparametrisierung: (ax3, best, passend, info) wie _lage + suche in
    step_geometrie._profil_messen, oder (None, grund). best = (Netto-Fläche, z, Schnitt), passend = [(z, Schnitt)]
    (die Lage von best zuerst), z im System ax3."""
    uhr = time.perf_counter()
    fl = flaechen(solid)
    d, anteil, art = achse(fl, solid, mit_art=True)
    if d is None:
        return None, ("zwei Längsrichtungen fast gleich (Platte, Flachstahl)" if anteil < 0 else
                      f"keine Längsrichtung (Längsflächen {anteil:.0%}, z. B. Freiform)")
    box = Bnd_Box()
    BRepBndLib.Add_s(solid, box, False)
    p0, p1 = box.CornerMin(), box.CornerMax()
    mitte = gp_Pnt((p0.X() + p1.X()) / 2, (p0.Y() + p1.Y()) / 2, (p0.Z() + p1.Z()) / 2)
    ax3 = gp_Ax3(mitte, d)
    lok = g._transformiere(solid, ax3)
    zmin, zmax = g._z_bereich(lok)
    z_ = gp_Dir(0, 0, 1)        # im lokalen System ist die Rohrachse Z
    lok_fl = [(f, n is not None and _laengs(typ, n, z_)) for f, typ, _, n in flaechen(lok)]
    frei = freie_bereiche(lok_fl, zmin, zmax)
    if art == "laenge" and _stufe(lok_fl, zmin, zmax):
        # Flachstahl über die Länge bestimmt: Taschen, Stufen oder Absätze (Längsflächen nicht von Ende zu Ende)
        # machen den Querschnitt mehrdeutig (B08 Platte mit Tasche): bisherige Rechnung
        return None, "Platte mit Tasche oder Stufe (Längsfläche nicht von Ende zu Ende)"
    if not frei:
        return None, "kein merkmalsfreier Bereich (Querschnitt überall von Merkmalen belegt)"
    zs = _lagen(frei)
    schnitte = []
    for z in zs:
        ws = g._schnitt(lok, z)
        if not ws:
            return None, "Schnitt leer"
        schnitte.append((z, ws))
    n0 = len(schnitte[0][1])
    netto = [ws[0][0] - sum(w[0] for w in ws[1:]) for _, ws in schnitte]
    if any(len(ws) != n0 for _, ws in schnitte) or max(netto) - min(netto) > g.QUER_GLEICH * max(netto):
        return None, "Gegenprobe: Querschnitte in den freien Bereichen ungleich"
    if n0 >= 2 and not all(g._innen_liegend(w[1], ws[0][1]) for _, ws in schnitte for w in ws[1:]):
        return None, "Innenkontur liegt nicht in der Außenkontur"
    if n0 > 6:
        return None, "zu viele Konturen im Querschnitt"
    # Gegenprobe Volumen: bei einem geraden Profil nehmen Bohrungen, Ausschnitte und Enden nur Werkstoff weg. Ist das
    # Volumen größer als Querschnitt × Länge, ist der Querschnitt nicht der volle (z. B. alle Schnitte in einem langen
    # Fenster) oder es gibt Anbauteile: dann die bisherige Rechnung
    vol = g._volumen(solid)
    if vol > max(netto) * (zmax - zmin) * (1 + TOL_VOLUMEN):
        return None, "Gegenprobe: Volumen größer als Querschnitt × Länge (Fenster oder Anbauteil)"
    # Mitte und Drehung wie step_geometrie._lage: Schwerpunkt des mittleren Querschnitts, X = längere Seite des
    # kleinsten umschreibenden Rechtecks
    zm, wsm = min(schnitte, key=lambda s: abs(s[0] - (zmin + zmax) / 2))
    netto_m, cx, cy = g._querschnitt_daten(wsm)
    if netto_m <= 0:
        return None, "Querschnitt ohne Fläche"
    w = g._min_rechteck([(s[0], s[1]) for s in g._strecken(wsm[0][1])], kanten_lage=True)
    o = g._global(ax3, cx, cy, zm)
    xr = g._vec(ax3.XDirection()).Multiplied(math.cos(w)).Added(g._vec(ax3.YDirection()).Multiplied(math.sin(w)))
    ax3n = gp_Ax3(o, ax3.Direction(), gp_Dir(xr.X(), xr.Y(), xr.Z()))
    info = dict(methode="abwicklung", achse_anteil=round(anteil, 4), frei=[[round(a - zm, 2), round(b - zm, 2)]
                for a, b in frei[:6]], schnitte=len(schnitte), lage_s=round(time.perf_counter() - uhr, 4),
                zs=[z - zm for z in zs], netto=max(netto), laenge=zmax - zmin,
                z_mitte=(zmin + zmax) / 2 - zm)
    info["_fl"] = fl            # für die Gegenproben (gegenproben), nicht ins Protokoll
    return (ax3n, info), None


_ZULETZT = []           # [(solid, Ergebnis)]: dieselbe Lage nicht zweimal rechnen (erkennen, schenkel, Messung)
ZULETZT_MAX = 8


def profil_vorgabe(solid):
    """Für step_geometrie._profil_messen: (ax3, Lagen z relativ zur Mitte, info) oder (None, grund)."""
    for s, erg in _ZULETZT:
        if s.IsSame(solid):
            return erg
    try:
        erg = lage(solid)
    except Exception as e:  # Rückfall auf die bisherige Rechnung
        erg = (None, f"Fehler {type(e).__name__}: {e}")
    _ZULETZT.insert(0, (solid, erg))
    del _ZULETZT[ZULETZT_MAX:]
    return erg


def achssystem(solid):
    """Rohrsystem wie step_geometrie._lage(solid)[0] (Achse Z, Mitte, X-Richtung), mit wirksamem Kern aus der
    Flächenparametrisierung (Plan 2.0, N5: Erkennung offener Rohre und Schenkel), sonst bisher."""
    if neu_aktiv():
        erg, _ = profil_vorgabe(solid)
        if erg is not None:
            # Ursprung wie _lage in der Mitte der Länge (der Querschnitt ist längs gleich: nur entlang der Achse)
            ax3, info = erg
            d = ax3.Direction()
            o = ax3.Location().Translated(gp_Vec(d.X(), d.Y(), d.Z()).Multiplied(info.get("z_mitte", 0.0)))
            return gp_Ax3(o, d, ax3.XDirection())
    return g._lage(solid)[0]


# ---------------------------------------------------------------------------------------------------------------
# Selbstprüfung (Plan Abwicklungskern 2.0, N1): Gegenproben unabhängig von den Schnitten, Vertrauenswert

def _flaechen_lage(fl, ax3):
    """Längsflächen relativ zur Rohrachse aus der Flächenparametrisierung: Ebenen [(Richtung, Lage entlang der
    Normale, Z-Länge)] und achsparallele Zylinder [(Radius, Abstand der Zylinderachse von der Rohrachse, Z-Länge)]."""
    o, d = ax3.Location(), ax3.Direction()
    ov = gp_Vec(o.X(), o.Y(), o.Z())
    ebenen, zylinder = [], []
    for f, typ, _, n in fl:
        if n is None or typ == "X" or not _laengs(typ, n, d):
            continue
        b = Bnd_Box()
        BRepBndLib.Add_s(f, b, False)
        if b.IsVoid():
            continue
        ecken = [gp_Vec(p.X(), p.Y(), p.Z()).Subtracted(ov).Dot(gp_Vec(d.X(), d.Y(), d.Z()))
                 for p in (b.CornerMin(), b.CornerMax())]
        geo = analytisch(f)[1]
        if typ == "E":
            pl = geo
            q = pl.Location()
            nn = pl.Axis().Direction()
            k = _richtung_key(nn)       # Richtung ohne Vorzeichen: Lage aller Ebenen dieser Richtung vergleichbar
            kv = gp_Vec(*k)
            lage_n = gp_Vec(q.X(), q.Y(), q.Z()).Subtracted(ov).Dot(kv) / kv.Magnitude()
            ebenen.append((k, lage_n, abs(ecken[1] - ecken[0])))
        else:
            c = geo
            q = c.Location()
            v = gp_Vec(q.X(), q.Y(), q.Z()).Subtracted(ov)
            abstand = v.Crossed(gp_Vec(d.X(), d.Y(), d.Z())).Magnitude()
            zylinder.append((c.Radius(), abstand, abs(ecken[1] - ecken[0])))
    return ebenen, zylinder


TOL_PROBE = 0.01        # mm: Gegenprobe Maße (wie TOL_MM)
LANG = 0.3              # Anteil der Länge: Längsfläche zählt für die Maß-Gegenprobe (Wände, keine Fensterflanken)
VERTRAUEN_VOLL = 100    # alle Gegenproben bestanden, Maße gegen die Flächen geprüft
VERTRAUEN_OHNE_MASS = 80  # bestanden, Maße nicht gegen Flächen prüfbar (offene Profile, Sonderprofile)


def _enthalten(wert, werte, tol=TOL_PROBE):
    return any(abs(wert - w) <= tol for w in werte)


def gegenproben(t, info, ax3, quer=False):
    """Gegenproben einer Messung über den Kern, unabhängig von den Schnitten: (Vertrauen 0–100, Befunde
    [(Probe, bestanden, Text)]). Nicht bestanden = Rückfall auf die bisherige Rechnung (step_geometrie._profil_messen).
    Proben: Werte endlich und nicht negativ; Querschnitt und Länge wie die Merkmalskarte; Rundrohr Ø und Innen-Ø als
    Radien achsgleicher Zylinder; Rechteck-/Quadratrohr und Flachstahl Außen- (und Innen-)maße als Abstände der
    Wandebenen.
    quer: die Lage kommt aus einem anderen Körper (geschlossenes Rohr zu einem offen gezeichneten): Länge nicht
    vergleichbar."""
    befunde = []
    werte = [getattr(t, n, 0.0) or 0.0 for n in ("abm_a", "abm_b", "wandstaerke", "flaeche", "laenge", "schneidweg",
                                                  "ende_a", "ende_b", "innen")]
    befunde.append(("werte", all(math.isfinite(w) and w >= 0 for w in werte), "Werte endlich und nicht negativ"))
    netto, laenge = info.get("netto"), info.get("laenge")
    if netto and t.flaeche:
        befunde.append(("querschnitt", abs(t.flaeche - netto) <= max(TOL_REL * netto, 1e-3),
                        f"Querschnitt {t.flaeche:.3f} / Merkmalskarte {netto:.3f} mm²"))
    if laenge and t.laenge and not quer:     # quer: Lage aus dem geschlossenen Rohr, Länge aus dem Teil selbst
        befunde.append(("laenge", abs(t.laenge - laenge) <= TOL_PROBE,
                        f"Länge {t.laenge:.3f} / Merkmalskarte {laenge:.3f} mm"))
    mass = False
    fl = info.get("_fl")
    if fl and t.profilform in ("Rundrohr", "Quadratrohr", "Rechteckrohr", "Flachstahl") and laenge:
        ebenen, zylinder = _flaechen_lage(fl, ax3)
        if t.profilform == "Rundrohr":
            radien = [r for r, ab, zl in zylinder if ab <= TOL_PROBE and zl >= LANG * laenge]
            if radien:
                mass = True
                ok = _enthalten(t.abm_a / 2, radien, TOL_PROBE / 2) and (
                    not t.innen_a or _enthalten(t.innen_a / 2, radien, TOL_PROBE / 2))
                befunde.append(("mass_zylinder", ok, f"Ø {t.abm_a:.3f}/{t.innen_a:.3f} gegen Zylinderradien "
                                f"{sorted(round(2 * r, 3) for r in set(radien))}"))
        else:
            gruppen = {}
            for k, lage_n, zl in ebenen:
                if zl >= LANG * laenge:
                    gruppen.setdefault(k, []).append(lage_n)
            # je Richtung die äußeren Wände; Fasen und Kantenbrüche bilden eigene Richtungen (zählen nicht)
            gr = [sorted(v) for v in gruppen.values() if len(v) >= 2]
            if len(gr) >= 2:
                mass = True
                aussen = sorted(v[-1] - v[0] for v in gr)
                abst = [b - a for v in gr for i, a in enumerate(v) for b in v[i + 1:]]
                soll = (t.abm_a, t.abm_b or t.abm_a)
                rest = list(aussen)
                ok = True
                for s in soll:      # jedes Außenmaß von einer eigenen Richtung
                    i = next((i for i, x in enumerate(rest) if abs(x - s) <= TOL_PROBE), None)
                    ok = ok and i is not None
                    if i is not None:
                        rest.pop(i)
                for innen in (t.innen_a, t.innen_b):
                    if innen:
                        ok = ok and _enthalten(innen, abst)
                befunde.append(("mass_ebenen", ok, f"{t.abm_a:.3f}×{t.abm_b:.3f} innen {t.innen_a:.3f}×"
                                f"{t.innen_b:.3f} gegen Wandebenen außen {[round(x, 3) for x in aussen]}"))
    if not all(ok for _, ok, _ in befunde):
        return 0, befunde
    return (VERTRAUEN_VOLL if mass else VERTRAUEN_OHNE_MASS), befunde


# Dauer-Vergleich (N1): jede n-te Kern-Messung zusätzlich mit der bisherigen Rechnung (Modus an). Die Auswahl hängt
# nur von Datei und Körper ab (gleiches Teil = gleiche Entscheidung, Ergebnis unabhängig von der Reihenfolge).
STICHPROBE_START = 20
STICHPROBE = STICHPROBE_START


def stichprobe_setzen(n):
    global STICHPROBE
    try:
        STICHPROBE = max(0, int(n))
    except (TypeError, ValueError):
        STICHPROBE = STICHPROBE_START


def stichprobe(datei, koerper):
    """Dieses Teil (Datei, Körper) zusätzlich bisher rechnen?"""
    if not STICHPROBE:
        return False
    import zlib
    name = os.path.basename(str(datei or ""))
    return zlib.crc32(f"{name}|{koerper}".encode("utf-8")) % STICHPROBE == 0


def zusammenfassen(eintraege):
    """Protokoll einer Datei kurz: {modus, neu, rueckfall, gruende {Grund: Anzahl}, ungleich, neu_s, bisher_s}."""
    out = dict(modus=MODUS, neu=0, rueckfall=0, gruende={}, ungleich=0, neu_s=0.0, bisher_s=0.0, stichproben=0,
               vertrauen_min=None)
    for e in eintraege:
        if e.get("methode") in ("abwicklung", "vergleich"):
            out["neu"] += 1
        else:
            out["rueckfall"] += 1
            gr = e.get("grund") or "?"
            out["gruende"][gr] = out["gruende"].get(gr, 0) + 1
        out["ungleich"] += 1 if e.get("gleich") is False else 0
        out["stichproben"] += 1 if e.get("stichprobe") else 0
        if e.get("vertrauen") is not None:
            v = out["vertrauen_min"]
            out["vertrauen_min"] = e["vertrauen"] if v is None else min(v, e["vertrauen"])
        out["neu_s"] = round(out["neu_s"] + (e.get("neu_s") or e.get("gesamt_s") or 0.0), 3)
        out["bisher_s"] = round(out["bisher_s"] + (e.get("bisher_s") or 0.0), 3)
    return out


# ---------------------------------------------------------------------------------------------------------------
# Vergleich alt/neu (Vergleichsrechnung, Abnahme)

VERGLEICH_FELDER = ("profilform", "abm_a", "abm_b", "wandstaerke", "flaeche", "laenge", "schneidweg", "konturen",
                    "ende_a", "ende_b", "innen", "innen_konturen", "gravur", "gravur_konturen", "bohrungen",
                    "kammern", "kontur_umfang", "ende_a_gerade", "ende_b_gerade", "innen_a", "innen_b")
TOL_MM = 0.01           # mm: Maße und Schneidwege (Fertigungstoleranz weit darunter)
TOL_REL = 1e-5          # relativ: Flächen und lange Schneidwege
# Hüllmaß eines Endschnitts (nur Konturklasse klein/mittel/groß): kleinstes Rechteck um abgetastete Punkte; beim
# Rundrohr hängt die Abtastung von der (beliebigen) X-Richtung ab, schon die bisherige Rechnung schwankt so um einige
# Zehntel. Toleranz 0,5 mm bzw. 1 %. Liegt ein Ende bei beiden über der Grenze „groß“ (MITTEL_BIS), zählt es als
# gleich: bei offen gezeichneten Rohren umfasst Ende A das ganze Fenster, die Ausgleichsebene durch die Stützpunkte
# (_ende_huellmass) hängt dann von deren Verteilung ab (P02: 234,8 bzw. 297,0 mm, beide „groß“).
TOL_HUELLE_MM, TOL_HUELLE_REL = 0.5, 0.01


def _gleich(a, b):
    if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or isinstance(b, str) or a is None or b is None:
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= max(TOL_MM, TOL_REL * max(abs(a), abs(b)))
    if isinstance(a, dict) and isinstance(b, dict):
        a, b = _schluessel(a), _schluessel(b)     # Prüfbasis (JSON) hat Text-Schlüssel
        return a.keys() == b.keys() and all(_gleich(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_gleich(x, y) for x, y in zip(a, b))
    return a == b


def _kontur_kern(k):
    """Vergleichbare Werte einer Kontur (ohne Darstellung wie Umriss/Schwenk-Punkte)."""
    return {n: k.get(n) for n in ("art", "durchgehend", "z", "winkel", "u", "seite", "schnittlaenge", "durchmesser",
                                  "laenge", "breite", "huellmass", "form", "gehrung") if n in k}


def _drehung_quadrat(alt, neu, ka, kb):
    """Quadratrohr: gleiche Seiten, die 0°-Seite ist nur durch Rundungsrauschen bestimmt (schon bisher). Alle
    Konturen um dasselbe Vielfache von 90° gedreht = gleiches Teil. Ergebnis: Drehung in Grad oder None."""
    if alt.profilform != "Quadratrohr" or neu.profilform != "Quadratrohr" or len(ka) != len(kb):
        return None
    dw = {round(((y["winkel"] - x["winkel"]) % 360) / 90) % 4 for x, y in zip(ka, kb)
          if x.get("winkel") is not None and y.get("winkel") is not None}
    if len(dw) != 1:
        return None
    k = dw.pop()
    ok = all(abs((y["winkel"] - x["winkel"] - 90 * k + 180) % 360 - 180) <= 0.1 + 1e-9 for x, y in zip(ka, kb)
             if x.get("winkel") is not None and y.get("winkel") is not None)
    return 90 * k if ok and k else None


def _json(v):
    if isinstance(v, dict):
        return {str(k): _json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json(x) for x in v]
    if isinstance(v, float):
        return round(v, 6)
    return v


def sollwerte(t):
    """Vergleichbare Werte einer Messung (Teil) für die Prüfbasis (N7): JSON, wieder einlesbar mit soll_teil."""
    if t is None:
        return None
    d = {n: _json(getattr(t, n, None)) for n in VERGLEICH_FELDER + ("bauteiltyp",)}
    d["konturen_liste"] = [_json(_kontur_kern(k)) for k in t.konturen_liste or []]
    d["hinweise"] = sorted(t.hinweise or [])
    for n in ("geschlossen", "alternative"):
        d[n] = sollwerte(getattr(t, n, None))
    return d


def soll_teil(d):
    """Sollwerte (sollwerte) als Objekt für vergleichen."""
    if d is None:
        return None
    from types import SimpleNamespace
    x = SimpleNamespace(**d)
    x.geschlossen, x.alternative = soll_teil(d.get("geschlossen")), soll_teil(d.get("alternative"))
    return x


def _schluessel(d):
    """Dict-Schlüssel aus JSON (str) wie in der Messung (z. B. Bohrungs-Ø als Zahl) vergleichbar machen."""
    return {str(k): v for k, v in d.items()}


def vergleichen(alt, neu, pfad=""):
    """Unterschiede zweier Messungen (Teil) außerhalb der Toleranz: [(Feld, alt, neu)]. Auch die Messungen als
    geschlossenes Rohr (geschlossen) und in der anderen Art (alternative)."""
    out = []
    for n in VERGLEICH_FELDER + ("bauteiltyp",):
        a, b = getattr(alt, n, None), getattr(neu, n, None)
        if not _gleich(a, b):
            out.append((pfad + n, a, b))
    ka = [_kontur_kern(k) for k in alt.konturen_liste or []]
    kb = [_kontur_kern(k) for k in neu.konturen_liste or []]
    dreh = _drehung_quadrat(alt, neu, ka, kb)
    if len(ka) != len(kb):
        out.append((pfad + "konturen_liste", len(ka), len(kb)))
    else:
        for i, (x, y) in enumerate(zip(ka, kb)):
            for n in sorted(set(x) | set(y)):
                if dreh is not None and n in ("winkel", "u", "seite"):
                    continue        # Quadratrohr um 90°-Vielfache gedreht (siehe _drehung_quadrat)
                if n == "winkel" and x.get(n) is not None and y.get(n) is not None:
                    dw = abs((x[n] - y[n] + 180) % 360 - 180)
                    if dw > 0.1 + 1e-9:
                        out.append((f"{pfad}konturen_liste[{i}].{n}", x[n], y[n]))
                elif n == "u" and x.get(n) is not None and y.get(n) is not None and alt.kontur_umfang:
                    du = abs((x[n] - y[n] + alt.kontur_umfang / 2) % alt.kontur_umfang - alt.kontur_umfang / 2)
                    if du > 0.02 + 1e-9:
                        out.append((f"{pfad}konturen_liste[{i}].{n}", x[n], y[n]))
                elif n == "huellmass" and isinstance(x.get(n), (int, float)) and isinstance(y.get(n), (int, float)):
                    if str(x.get("art", "")).startswith("Ende") and min(x[n], y[n]) > g.MITTEL_BIS:
                        continue    # Ende über die Grenze groß: Konturklasse gleich (siehe TOL_HUELLE_MM)
                    if abs(x[n] - y[n]) > max(TOL_HUELLE_MM, TOL_HUELLE_REL * abs(x[n])):
                        out.append((f"{pfad}konturen_liste[{i}].{n}", x[n], y[n]))
                elif not _gleich(x.get(n), y.get(n)):
                    out.append((f"{pfad}konturen_liste[{i}].{n}", x.get(n), y.get(n)))
    if sorted(alt.hinweise or []) != sorted(neu.hinweise or []):
        out.append((pfad + "hinweise", alt.hinweise, neu.hinweise))
    for n in ("geschlossen", "alternative"):
        a, b = getattr(alt, n, None), getattr(neu, n, None)
        if (a is None) != (b is None):
            out.append((pfad + n, a is not None, b is not None))
        elif a is not None:
            out.extend(vergleichen(a, b, f"{pfad}{n}."))
    return out
