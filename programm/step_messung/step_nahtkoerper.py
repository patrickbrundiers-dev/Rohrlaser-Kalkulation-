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


class _Stuetz:
    """Punkte, die sicher AUF einem Körper liegen (Eckpunkte und je Kante drei Punkte jeder Fläche), in einem Raster
    mit Zellgröße NAHT_SCHENKEL. Liegt ein Prüfpunkt höchstens NAHT_SCHENKEL von einem davon, ist sein Abstand zum
    Körper sicher höchstens NAHT_SCHENKEL (der Körper ist mindestens so nah) – die exakte Abstandsrechnung entfällt.
    Sonst rechnet zuordnen exakt wie bisher: das Ergebnis ist dasselbe, nur schneller (Pizza-Ofen 21.11.2026).
    Zusätzliche Rasterpunkte auf den Flächen waren gemessen langsamer (Aufbau je großem Körper ~4 s) und bleiben weg."""

    def __init__(self, k):
        from OCP.TopoDS import TopoDS
        self.zellen = {}
        for f in g._liste(k, TopAbs_FACE):
            face = TopoDS.Face(f) if hasattr(TopoDS, "Face") else TopoDS.Face_s(f)
            for q in g._flaechen_punkte(face):
                x, y, z = q.X(), q.Y(), q.Z()
                self.zellen.setdefault(self._zelle(x, y, z), []).append((x, y, z))

    @staticmethod
    def _zelle(x, y, z):
        return int(x // NAHT_SCHENKEL), int(y // NAHT_SCHENKEL), int(z // NAHT_SCHENKEL)

    def sicher_nah(self, p):
        x, y, z = p.X(), p.Y(), p.Z()
        cx, cy, cz = self._zelle(x, y, z)
        grenze = NAHT_SCHENKEL * NAHT_SCHENKEL
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for (a, b, c) in self.zellen.get((cx + dx, cy + dy, cz + dz), ()):
                        if (a - x) ** 2 + (b - y) ** 2 + (c - z) ** 2 <= grenze:
                            return True
        return False


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


def _nachbarn(i, k, koerper, weg, nur=None, boxen=None):
    """Indizes der Körper, die k berühren (Abstand bis KONTAKT). nur(j): nur diese Körper prüfen (vor der exakten
    Abstandsrechnung statt danach aussortieren – gleiches Ergebnis); boxen: {j: Hülle} einmal je Körper."""
    kb = _box(k, KONTAKT)
    out = []
    for j, (_, kj) in enumerate(koerper):
        if j == i or j in weg or (nur is not None and not nur(j)):
            continue
        if boxen is not None:
            if j not in boxen:
                boxen[j] = _box(kj)
            bj = boxen[j]
        else:
            bj = _box(kj)
        if bj.IsOut(kb):
            continue
        d = _abstand(k, kj)
        if d is not None and d <= KONTAKT:
            out.append(j)
    return out


def zuordnen(teile, koerper, weg=()):
    """Schweißnähte als eigene Körper finden (siehe oben). weg: Indizes, die schon kein Teil sind (Gravurkörper).
    Ergebnis: Menge der Indizes (in teile), die Nahtkörper geworden sind."""
    fertig = set()
    stuetz = {}         # Nachbar -> _Stuetz (einmal je Körper, für alle Nahtkandidaten)
    boxen = {}          # Körper -> Hülle (einmal je Körper statt je Nahtkandidat, MASTER TOWER 21.11.2026)
    teil = {}           # Körper -> ist Rohr, Blech oder Profil (nur diese können die Naht tragen)

    def ist_teil(j):
        if j not in teil:
            teil[j] = teile[j].bauteiltyp in TEIL or g._ist_rohr(teile[j])
        return teil[j]
    for i, (t, (art, k)) in enumerate(zip(teile, koerper)):
        if i in weg or not kandidat(t, art):
            continue
        # erst nach der Art sortieren, dann exakt rechnen: Drehteile, Schrauben, Nahtkörper … tragen keine Naht
        nb = _nachbarn(i, k, koerper, set(weg) | fertig, ist_teil, boxen)
        if len(nb) < 2:
            continue
        roh = _punkte(k)
        pts = [BRepBuilderAPI_MakeVertex(p).Vertex() for p in roh]
        nah = {}        # Nachbar -> liegt jeder Punkt höchstens NAHT_SCHENKEL davon? (je Nachbar einmal, nicht je Paar)

        def alle_nah(j):
            if j not in nah:
                kj = koerper[j][1]
                box = _box(kj, NAHT_SCHENKEL)       # Punkt außerhalb der Hülle + Schenkel: sicher weiter weg
                if j not in stuetz:
                    stuetz[j] = _Stuetz(kj)
                st = stuetz[j]
                nah[j] = all(not box.IsOut(p) and (st.sicher_nah(p) or (
                    (d := _abstand(v, kj)) is not None and d <= NAHT_SCHENKEL)) for p, v in zip(roh, pts))
            return nah[j]
        paar = None
        for x in range(len(nb)):
            if not alle_nah(nb[x]):
                continue
            for y in range(x + 1, len(nb)):
                if alle_nah(nb[y]):
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
