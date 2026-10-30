"""Einbaulage gleicher Körper am Netz prüfen (Prüfung STEP-Export gegen Mutter-STEP, Patrick 30.10.2026: „nicht dass
Geometrien aus der Mutter-STEP nicht mehr da sind, wo sie hingehören“).

Gleiche Körper einer Datei werden eine Position mit dem Netz des ersten Körpers und je Körper seiner Einbaulage
('lagen'). Die Messung legt das Rohrsystem jedes Körpers aber für sich fest (Bezug, Ende A). Ist ein gleicher Körper
gedreht oder gewendet eingebaut (Rahmen mit Gehrungen: gegenüberliegende Seite), passt seine Lage nicht zum Netz des
ersten Körpers: 3D-Ansicht und STEP-Export zeigten ihn gespiegelt (Gehrung nach innen statt nach außen).

passende_lage sucht die Drehung um die Rohrachse und das Wenden, mit denen das Netz des ersten Körpers genau auf dem
eigenen Netz des Körpers liegt (Punktabstand, ohne OpenCascade).
"""
import math

ZELLE = 2.0             # Rastergröße für die Nachbarsuche [mm]
KAPPE = 5.0             # größter gezählter Abstand [mm]
PROBEN = 400            # so viele Punkte je Netz höchstens vergleichen
GUT = 0.05              # mittlerer Abstand bis hierhin: Lage passt [mm]


def in_lage(p, lage):
    """Punkte p (flach x, y, z im Rohrsystem) in der Datei."""
    o, z, x = lage[0:3], lage[3:6], lage[6:9]
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    return [tuple(o[k] + p[i] * x[k] + p[i + 1] * y[k] + p[i + 2] * z[k] for k in range(3))
            for i in range(0, len(p) - 2, 3)]


def _proben(p, n=PROBEN):
    zahl = len(p) // 3
    schritt = max(1, zahl // n)
    return [p[3 * i:3 * i + 3] for i in range(0, zahl, schritt)]


class _Raster:
    def __init__(self, punkte):
        self.z = {}
        for q in punkte:
            self.z.setdefault(tuple(int(math.floor(c / ZELLE)) for c in q), []).append(q)

    def abstand(self, q):
        k = [int(math.floor(c / ZELLE)) for c in q]
        best = KAPPE * KAPPE
        r = int(math.ceil(KAPPE / ZELLE))
        for ring in range(r + 1):           # innen anfangen: ein naher Punkt beendet die Suche früh
            if ring and best <= ((ring - 1) * ZELLE) ** 2:
                break
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    for dz in range(-ring, ring + 1):
                        if max(abs(dx), abs(dy), abs(dz)) != ring:
                            continue
                        for t in self.z.get((k[0] + dx, k[1] + dy, k[2] + dz), ()):
                            d = (t[0] - q[0]) ** 2 + (t[1] - q[1]) ** 2 + (t[2] - q[2]) ** 2
                            if d < best:
                                best = d
        return math.sqrt(best)


def abweichung(p_muster, lage, raster):
    """Mittlerer Abstand [mm] der Punkte des Netzes p_muster in lage zum Zielnetz (raster)."""
    ab = [raster.abstand(q) for q in in_lage([c for q in _proben(p_muster) for c in q], lage)]
    return sum(ab) / max(1, len(ab))


def _kandidat(lage, d, wenden, laenge):
    from .steckverbindung import lage_drehen
    return lage_drehen(lage, d, wenden, laenge)


def passende_lage(netz_muster, netz_k):
    """Lage, mit der netz_muster (Netz des ersten gleichen Körpers) dort liegt, wo netz_k (eigenes Netz des Körpers
    mit seiner 'lage') liegt. Ergebnis (Lage, mittlerer Abstand vorher, nachher); Lage unverändert, wenn sie schon
    passt oder keine bessere gefunden wird."""
    lage = netz_k.get("lage")
    pm, pk = netz_muster.get("p") or [], netz_k.get("p") or []
    if not lage or len(lage) != 9 or len(pm) < 9 or len(pk) < 9:
        return lage, 0.0, 0.0
    ziel = in_lage(pk, lage)
    raster = _Raster(ziel)
    vorher = abweichung(pm, lage, raster)
    if vorher <= GUT:
        return lage, vorher, vorher
    laenge = max(pm[2::3])
    beste = (vorher, lage)
    for wenden in (False, True):
        for d in range(0, 360, 15):
            k = _kandidat(lage, float(d), wenden, laenge)
            a = abweichung(pm, k, raster)
            if a < beste[0] - 1e-9:
                beste = (a, k)
    for schritt in (5.0, 1.0, 0.2):         # fein nachsuchen (Rundrohr: Drehung beliebig)
        start = beste[1]
        for i in (-2, -1, 1, 2):
            k = _kandidat(start, i * schritt, False, laenge)
            a = abweichung(pm, k, raster)
            if a < beste[0] - 1e-9:
                beste = (a, k)
    nachher, neu = beste
    if nachher < vorher * 0.5:
        return [round(float(c), 9) for c in neu], vorher, nachher
    return lage, vorher, vorher


def lagen_abgleichen(netz_muster, netze):
    """Lagen gleicher Körper zum Netz des ersten: netze = eigene Netze (mit 'lage') der Körper in der Reihenfolge
    der Lagen; der erste ist das Muster selbst. Ergebnis: Liste der Lagen."""
    out = []
    for i, n in enumerate(netze):
        if not n:
            out.append(None)
        elif i == 0 or n is netz_muster:
            out.append(n.get("lage"))
        else:
            out.append(passende_lage(netz_muster, n)[0])
    return out
