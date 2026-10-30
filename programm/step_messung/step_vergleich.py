"""Prüfung STEP-Export gegen die Mutter-STEP (Patrick 30.10.2026: „Prüfen, ob die STEP, die aus dem Editor kommt, mit
der STEP übereinstimmt, die in das Programm geladen wurde, wenn Steckverbindungen eingefügt oder sonstige Änderungen
vorgenommen wurden – nicht dass Geometrien aus der Mutter-STEP nicht mehr da sind, wo sie hingehören“).

Nach dem Schreiben vergleicht der Export jeden eingesetzten Körper mit dem Körper der Kundendatei (Mutter-STEP), aus
dem er stammt: gemeinsames Volumen (Boolesche Schnittmenge, sonst genähert über Hülle und Volumen), Abweichung (Volumen, das
nur in einem der beiden liegt) und Verschiebung des Schwerpunkts. Ergebnis je Körper:

- gleich: Abweichung bis ANTEIL_GLEICH des Volumens
- geändert: Form örtlich anders, Lage stimmt (Schlitze und Nasen einer Steckverbindung, 2D-Gehrung wie gelasert,
  im Editor geänderte Konturen) – Hinweis mit den Änderungen, die der Bauplan erwartet
- Lage: Körper verschoben, verdreht oder stark anders (gemeinsam unter ANTEIL_LAGE oder Schwerpunkt mehr als
  SCHWERPUNKT_MM daneben) oder ohne Gegenstück in der Mutter-STEP – Warnung
Körper der Mutter-STEP ohne Gegenstück im Export werden genannt (fehlen).
"""
import math
import time

ANTEIL_GLEICH = 0.0005      # Abweichung bis 0,05 % des Volumens: gleich
ANTEIL_LAGE = 0.95          # gemeinsames Volumen unter 95 % des Originals: Lage oder Form falsch
SCHWERPUNKT_MM = 1.0        # Schwerpunkt weiter daneben: Lage falsch
TOLERANZEN = (0.0, 1e-3, 1e-2)  # Toleranz der Booleschen Schnittmenge [mm] (berührende, fast gleiche Flächen)
HUELLE_TEIL = 0.3           # Paare prüfen, deren Hüllen sich mindestens so weit decken (Nachbarn nur berührt)
HUELLE_GENAEHERT = 0.9      # ohne Schnittmenge: Hüllen decken sich so weit -> genähert über Volumen und Schwerpunkt
NACHFUEHREN_MM = 0.5        # ausgerichtete Bleche höchstens so weit auf die Mutter-STEP nachschieben
ZEIT = 120.0                # Sekunden für die ganze Prüfung, danach „nicht geprüft“


def _props(k):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(k, g)
    c = g.CentreOfMass()
    return abs(g.Mass()), (c.X(), c.Y(), c.Z())


def _box(k):
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_Box()
    BRepBndLib.Add_s(k, b)
    if b.IsVoid():
        return None
    a, z = b.CornerMin(), b.CornerMax()
    return (a.X(), a.Y(), a.Z(), z.X(), z.Y(), z.Z())


def koerper_info(k):
    v, c = _props(k)
    return dict(k=k, v=v, c=c, box=_box(k))


_GELESEN = {}               # Pfad -> Körper (eine Datei im Export nur einmal lesen)


def mutter_lesen(pfad):
    """Alle Volumenkörper der Mutter-STEP in Dateilage: [dict(k, v, c, box)]."""
    if str(pfad) in _GELESEN:
        return _GELESEN[str(pfad)]
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    r = STEPControl_Reader()
    if r.ReadFile(str(pfad)) != IFSelect_RetDone:
        raise ValueError("Mutter-STEP nicht lesbar")
    r.TransferRoots()
    out = []
    ex = TopExp_Explorer(r.OneShape(), TopAbs_SOLID)
    while ex.More():
        info = koerper_info(ex.Current())
        if info["box"] and info["v"] > 1e-6:
            out.append(info)
        ex.Next()
    _GELESEN[str(pfad)] = out
    return out


def nachfuehren(form, pfad, grenze=NACHFUEHREN_MM):
    """Am Netz ausgerichtetes Blech (step_schreiben.ausrichten, auf etwa 0,05 mm) exakt auf seinen Körper der
    Mutter-STEP schieben: gleiches Volumen (0,1 %), Hüllen fast gleich -> Verschiebung (dx, dy, dz) der Schwerpunkte,
    wenn kleiner als grenze; sonst None."""
    a = koerper_info(form)
    if not a["box"]:
        return None
    best = None
    for b in mutter_lesen(pfad):
        if abs(a["v"] - b["v"]) > 0.001 * b["v"] or not all(abs(a["box"][i] - b["box"][i]) < grenze
                                                               for i in range(6)):
            continue
        d = math.dist(a["c"], b["c"])
        if d < grenze and (best is None or d < best[0]):
            best = (d, tuple(b["c"][i] - a["c"][i] for i in range(3)))
    return best[1] if best and best[0] > 1e-6 else None


def _ueberlappen(a, b, rand=1.0):
    return all(a[i] - rand <= b[i + 3] and b[i] - rand <= a[i + 3] for i in range(3))


def _schnitt(a, b, fuzzy=0.0):
    """Gemeinsames Volumen zweier Körper (Boolesche Schnittmenge, auf Wunsch mit Toleranz) oder None."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    try:
        from OCP.collections import List_TopoDS_Shape as Liste
    except ImportError:             # ältere OCP-Versionen
        from OCP.TopTools import TopTools_ListOfShape as Liste
    la, lb = Liste(), Liste()
    la.Append(a)
    lb.Append(b)
    op = BRepAlgoAPI_Common()
    op.SetArguments(la)
    op.SetTools(lb)
    if fuzzy:
        op.SetFuzzyValue(fuzzy)
    op.Build()
    if not op.IsDone():
        return None
    return _props(op.Shape())[0]


def _huellen_anteil(a, b):
    """Anteil der kleineren Hülle, der in der anderen liegt (0 = getrennt, 1 = ganz darin)."""
    d = [max(0.0, min(a[i + 3], b[i + 3]) - max(a[i], b[i])) for i in range(3)]
    va, vb = (max(1e-9, (x[3] - x[0]) * (x[4] - x[1]) * (x[5] - x[2])) for x in (a, b))
    return d[0] * d[1] * d[2] / min(va, vb)


def _gemeinsam(a, b):
    """(gemeinsames Volumen, Abweichung, genähert) von Export a und Original b (dicts aus koerper_info). Gelingt die
    Schnittmenge nicht (facettiertes Netz, Flächen fast aufeinander; OpenCascade liefert dann 0), aber Hüllen und
    Volumen passen, wird genähert: gemeinsam = kleineres Volumen; Lage prüft dann der Schwerpunkt (bewerten)."""
    klein = min(a["v"], b["v"])
    g = None
    for fz in TOLERANZEN:       # Boolesche Operation mit steigender Toleranz, bis sie ein glaubhaftes Ergebnis gibt
        g = _schnitt(a["k"], b["k"], fz)
        if g is not None and g >= 0.5 * klein:
            return g, max(0.0, a["v"] + b["v"] - 2 * g), False
    if _huellen_anteil(a["box"], b["box"]) >= HUELLE_GENAEHERT and abs(a["v"] - b["v"]) < 0.02 * b["v"]:
        return klein, abs(a["v"] - b["v"]), True
    return (g or 0.0), a["v"] + b["v"] - 2 * (g or 0.0), False


def bewerten(a, b, gemeinsam, abweichung):
    """Status 'gleich' / 'geändert' / 'lage' und Kennwerte eines Paars Export a / Original b."""
    ds = math.dist(a["c"], b["c"])
    anteil = abweichung / b["v"] if b["v"] else 1.0
    if gemeinsam < ANTEIL_LAGE * b["v"] or ds > SCHWERPUNKT_MM:
        status = "lage"
    elif anteil <= ANTEIL_GLEICH:
        status = "gleich"
    else:
        status = "geändert"
    return dict(status=status, abweichung=round(abweichung, 1), anteil=round(anteil, 5), schwerpunkt=round(ds, 3),
                volumen=round(a["v"], 1), volumen_mutter=round(b["v"], 1))


def vergleichen(eingesetzt, mutter, zeit=ZEIT):
    """eingesetzt = [dict(name, form (in Dateilage), mutter (Index in mutter), erwartet [Texte])]; mutter = Pfade der
    Mutter-STEP. Ergebnis dict(koerper=[dict(name, status, …)], fehlen=[(Datei, Anzahl)], nicht_geprueft, fehler)."""
    from pathlib import Path
    start = time.monotonic()
    original, fehler = {}, []
    for i, pfad in enumerate(mutter):
        try:
            original[i] = mutter_lesen(pfad)
        except Exception as ex:
            fehler.append(f"{Path(pfad).name}: {ex}")
    benutzt = {i: set() for i in original}
    out, nicht = [], 0
    for e in eingesetzt:
        m = e.get("mutter")
        if m not in original:
            continue
        if time.monotonic() - start > zeit:
            nicht += 1
            continue
        a = koerper_info(e["form"])
        if not a["box"]:
            continue
        best = None
        for j, b in enumerate(original[m]):
            if j in benutzt[m] or not _ueberlappen(a["box"], b["box"]) or \
                    _huellen_anteil(a["box"], b["box"]) < HUELLE_TEIL:
                continue
            if abs(a["v"] - b["v"]) > 0.5 * max(a["v"], b["v"]):
                continue
            g, ab, genaehert = _gemeinsam(a, b)
            if best is None or g > best[0]:
                best = (g, ab, j, genaehert)
        zeile = dict(name=e.get("name") or "Teil", datei=Path(mutter[m]).name, erwartet=list(e.get("erwartet") or ()))
        if best is None or best[0] <= 0:
            zeile.update(status="lage", abweichung=round(a["v"], 1), anteil=1.0, schwerpunkt=None,
                         volumen=round(a["v"], 1), volumen_mutter=None)
        else:
            benutzt[m].add(best[2])
            b = original[m][best[2]]
            zeile.update(bewerten(a, b, best[0], best[1]), koerper_mutter=best[2] + 1, genaehert=best[3])
        out.append(zeile)
    fehlen = []
    for i, liste in original.items():
        if any(e.get("mutter") == i for e in eingesetzt):
            rest = len(liste) - len(benutzt[i])
            if rest > 0 and not nicht:
                fehlen.append((Path(mutter[i]).name, rest))
    return dict(koerper=out, fehlen=fehlen, nicht_geprueft=nicht, fehler=fehler,
                dauer=round(time.monotonic() - start, 1))
