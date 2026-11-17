"""Schweißnähte als eigene Körper (STEP 553591, Patrick 17.11.2026: „Das Rundrohr war in einer Baugruppe mit
anliegendem Rohrbund, in der Baugruppe eingezeichnete Schweißnaht“).

Viele CAD-Baugruppen zeichnen die Schweißnaht als eigenen Körper (Kehlnaht als Dreieck um das Rohr). Bisher wurde
dieser Körper wie ein Teil gemessen und kam als „offenes Sonderprofil“ (Wandstärke nicht einheitlich) in die Liste.

Jetzt gilt: ein eigener Körper, der zwei andere Körper berührt und mit jedem Punkt höchstens NAHT_SCHENKEL von beiden
entfernt liegt, ist eine Schweißnaht zwischen diesen beiden. Er wird kein Teil (Profilform NAHTKOERPER, wie ein
Gravurkörper nur gemeldet) und zählt nicht für Anbauteile, Nahtkandidaten und Erreichbarkeit; die Naht selbst findet
die Nahtsuche am Stoß der beiden Teile wie bisher.
"""
import step_geometrie as g
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.TopAbs import TopAbs_FACE

NAHTKOERPER = "Schweißnaht (Körper)"
NAHT_SCHENKEL = 8.0         # mm: jeder Punkt der Naht höchstens so weit von beiden Teilen (Schenkel bis a ≈ 5,6)
KONTAKT = 0.1               # mm: die Naht berührt beide Teile
PUNKTE_MAX = 400            # Prüfpunkte je Körper (Eckpunkte, je Kante drei Punkte)
FLAECHEN_MAX = 60           # mehr Flächen: kein Nahtkörper (Naht hat wenige Flächen), Rechenzeit sparen
TEIL = ("Profil", "Blech", "Blech gekantet")


def _box(k, rand=0.0):
    b = Bnd_Box()
    BRepBndLib.Add_s(k, b, False)
    if rand:
        b.Enlarge(rand)
    return b


def _abstand(a, b):
    d = BRepExtrema_DistShapeShape(a, b)
    return d.Value() if d.IsDone() else None


def _punkte(k):
    pts = []
    for f in g._liste(k, TopAbs_FACE):
        pts.extend(g._flaechen_punkte(f))
        if len(pts) > PUNKTE_MAX:
            break
    return pts[:PUNKTE_MAX]


def kandidat(t, art):
    """True, wenn der Körper (Teil t) eine Schweißnaht sein kann: Volumenkörper mit wenigen Flächen, der nicht als Rohr,
    Blech, Regelprofil (z. B. Vierkantstahl als Wand zwischen Platte und Deckel) oder Normteil gemessen ist."""
    if art != "Volumenkörper" or g._ist_rohr(t) or t.bauteiltyp in ("Blech", "Blech gekantet"):
        return False
    if t.profilform in g.OFFENE_PROFILE:     # Stab mit Regelquerschnitt (Flach-, Vierkantstahl, Winkel …): ein Teil
        return False
    if getattr(t, "drehfraes", None) and (t.drehfraes or {}).get("art") == "Normteil":
        return False
    return 0 < (t.n_flaechen or 0) <= FLAECHEN_MAX


def _nachbarn(i, k, koerper, weg):
    """Indizes der Körper, die k berühren (Abstand bis KONTAKT)."""
    kb = _box(k, KONTAKT)
    out = []
    for j, (_, kj) in enumerate(koerper):
        if j == i or j in weg or _box(kj).IsOut(kb):
            continue
        d = _abstand(k, kj)
        if d is not None and d <= KONTAKT:
            out.append(j)
    return out


def zuordnen(teile, koerper, weg=()):
    """Schweißnähte als eigene Körper finden (siehe oben). weg: Indizes, die schon kein Teil sind (Gravurkörper).
    Ergebnis: Menge der Indizes (in teile), die Nahtkörper geworden sind."""
    fertig = set()
    for i, (t, (art, k)) in enumerate(zip(teile, koerper)):
        if i in weg or not kandidat(t, art):
            continue
        nb = [j for j in _nachbarn(i, k, koerper, set(weg) | fertig)
              if teile[j].bauteiltyp in TEIL or g._ist_rohr(teile[j])]
        if len(nb) < 2:
            continue
        pts = [BRepBuilderAPI_MakeVertex(p).Vertex() for p in _punkte(k)]
        paar = None
        for x in range(len(nb)):
            for y in range(x + 1, len(nb)):
                a, b = koerper[nb[x]][1], koerper[nb[y]][1]
                if all((da := _abstand(v, a)) is not None and da <= NAHT_SCHENKEL and
                       (db := _abstand(v, b)) is not None and db <= NAHT_SCHENKEL for v in pts):
                    paar = (nb[x], nb[y])
                    break
            if paar:
                break
        if paar is None:
            continue
        ta, tb = teile[paar[0]], teile[paar[1]]
        t.profilform, t.bauteiltyp, t.alternative = NAHTKOERPER, "", None
        t.hinweise = [f"Schweißnaht als Körper zwischen Körper {ta.koerper} und {tb.koerper}: kein Teil, die Naht "
                      "kommt aus dem Stoß der beiden Teile"]
        fertig.add(i)
    return fertig
