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
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
from OCP.TopAbs import TopAbs_FACE
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


def flaechen(solid):
    """Flächen mit Typ, Fläche und Parametern: [(face, 'E'|'Z'|'F', Fläche, gp_Dir Normale/Achse oder None)]."""
    out = []
    for f in g._liste(solid, TopAbs_FACE):
        s = BRepAdaptor_Surface(TopoDS.Face(f))
        typ = s.GetType()
        if typ == GeomAbs_Plane:
            out.append((f, "E", g._flaeche(f), s.Plane().Axis().Direction()))
        elif typ == GeomAbs_Cylinder:
            out.append((f, "Z", g._flaeche(f), s.Cylinder().Axis().Direction()))
        else:
            out.append((f, "F", g._flaeche(f), None))
    return out


def _laengs(typ, d, achse):
    if typ == "E":
        return abs(d.Dot(achse)) < SENKRECHT
    if typ == "Z":
        return 1 - abs(d.Dot(achse)) < PARALLEL
    return False


def achse(fl):
    """Rohrachse aus den Flächen (gp_Dir) und Anteil der Längsflächen an der Oberfläche, oder (None, Anteil).
    Kandidaten: Achsen der Zylinder und Kreuzprodukte der Normalen der größten Ebenen; gewählt wird die mit der
    größten Längsfläche."""
    gesamt = sum(a for _, _, a, _ in fl) or 1.0
    kand = {}
    for _, typ, a, d in fl:
        if typ == "Z":
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
        return None, wertung[0][0] if wertung else 0.0
    anteil, beste = wertung[0]
    if len(wertung) > 1 and wertung[1][0] > anteil - EINDEUTIG:
        return None, -anteil        # zwei Richtungen fast gleich gut (Platte, Flachstahl): nicht eindeutig
    k = max((beste.X(), beste.Y(), beste.Z()), key=abs)       # wie _achse_grob: größter Anteil positiv
    if k < 0:
        beste = beste.Reversed()
    return beste, anteil


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
    d, anteil = achse(fl)
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
                zs=[z - zm for z in zs])
    return (ax3n, info), None


def profil_vorgabe(solid):
    """Für step_geometrie._profil_messen: (ax3, Lagen z relativ zur Mitte, info) oder (None, grund)."""
    try:
        erg, grund = lage(solid)
    except Exception as e:  # Rückfall auf die bisherige Rechnung
        return None, f"Fehler {type(e).__name__}: {e}"
    if erg is None:
        return None, grund
    return erg, None


def zusammenfassen(eintraege):
    """Protokoll einer Datei kurz: {modus, neu, rueckfall, gruende {Grund: Anzahl}, ungleich, neu_s, bisher_s}."""
    out = dict(modus=MODUS, neu=0, rueckfall=0, gruende={}, ungleich=0, neu_s=0.0, bisher_s=0.0)
    for e in eintraege:
        if e.get("methode") in ("abwicklung", "vergleich"):
            out["neu"] += 1
        else:
            out["rueckfall"] += 1
            gr = e.get("grund") or "?"
            out["gruende"][gr] = out["gruende"].get(gr, 0) + 1
        out["ungleich"] += 1 if e.get("gleich") is False else 0
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
