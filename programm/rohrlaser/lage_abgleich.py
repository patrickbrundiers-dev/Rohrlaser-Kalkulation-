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

ZELLE = 2.0             # Rastergröße für die Nachbarsuche [mm] (dichte Netze feiner, siehe _Raster)
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


DICHTE = 8              # mittlere Punkte je belegter Zelle höchstens (sonst Raster feiner, kleine dichte Netze)
ZELLE_MIN = 0.25
GROB_AB = 1.0          # feines Raster nur bis hierhin absuchen [mm], weiter im groben (Zelle KAPPE)


def _schalen(r, _merker={}):
    """Nachbarzellen je Ring (Würfelschale im Abstand ring) für Ringe 0 bis r, einmal berechnet."""
    if r not in _merker:
        _merker[r] = [[(dx, dy, dz) for dx in range(-ring, ring + 1) for dy in range(-ring, ring + 1)
                       for dz in range(-ring, ring + 1) if max(abs(dx), abs(dy), abs(dz)) == ring]
                      for ring in range(r + 1)]
    return _merker[r]


class _Raster:
    """Nachbarsuche: abstand(q) = Abstand zum nächsten Punkt, höchstens KAPPE. Bei dichten Netzen (kleine Teile
    wie Schrauben mit vielen Punkten) wird das Raster feiner; das Ergebnis ist dasselbe, die Suche schneller."""

    def __init__(self, punkte):
        self.zelle = ZELLE
        while True:
            self.z = {}
            for q in punkte:
                self.z.setdefault(tuple(int(math.floor(c / self.zelle)) for c in q), []).append(q)
            if self.zelle / 2 < ZELLE_MIN or len(punkte) <= DICHTE * len(self.z):
                break
            self.zelle /= 2
        self.schalen = _schalen(int(math.ceil(KAPPE / self.zelle)))
        # Punkte ohne nahen Nachbarn suchen im groben Raster weiter statt durch bis zu
        # 41³ feine Zellen (Schrauben, gedrehte Lagen; STEP-Tempo 12.11.2026); gleiche Punkte, gleicher Abstand
        self.grob = {}
        for q in punkte:
            self.grob.setdefault(tuple(int(math.floor(c / KAPPE)) for c in q), []).append(q)
        self.grob_schalen = _schalen(1)
        self.fein_ringe = min(len(self.schalen) - 1, int(math.ceil(GROB_AB / self.zelle)))

    def abstand(self, q):
        zelle = self.zelle
        k0, k1, k2 = (int(math.floor(c / zelle)) for c in q)
        q0, q1, q2 = q
        best = KAPPE * KAPPE
        z = self.z
        schalen = self.schalen[:self.fein_ringe + 1]
        for ring, schale in enumerate(schalen):    # innen anfangen: ein naher Punkt beendet die Suche früh
            if ring and best <= ((ring - 1) * zelle) ** 2:
                return math.sqrt(best)
            for dx, dy, dz in schale:
                for t in z.get((k0 + dx, k1 + dy, k2 + dz), ()):
                    d = (t[0] - q0) ** 2 + (t[1] - q1) ** 2 + (t[2] - q2) ** 2
                    if d < best:
                        best = d
        if best <= (self.fein_ringe * zelle) ** 2:
            return math.sqrt(best)      # alle nicht besuchten feinen Zellen liegen weiter weg
        # grobes Raster (Zelle = KAPPE, ein Ring): alle Punkte bis KAPPE; der bisher beste ist einer davon, das
        # Minimum bleibt dasselbe
        zelle = KAPPE
        k0, k1, k2 = (int(math.floor(c / zelle)) for c in q)
        z = self.grob
        for ring, schale in enumerate(self.grob_schalen):
            if ring and best <= ((ring - 1) * zelle) ** 2:
                break
            for dx, dy, dz in schale:
                for t in z.get((k0 + dx, k1 + dy, k2 + dz), ()):
                    d = (t[0] - q0) ** 2 + (t[1] - q1) ** 2 + (t[2] - q2) ** 2
                    if d < best:
                        best = d
        return math.sqrt(best)


def abweichung(p_muster, lage, raster, grenze=None):
    """Mittlerer Abstand [mm] der Punkte des Netzes p_muster in lage zum Zielnetz (raster). Mit grenze: sobald
    feststeht, dass der Mittelwert über grenze liegt, Abbruch mit math.inf (Kandidat kann nicht gewinnen)."""
    punkte = in_lage([c for q in _proben(p_muster) for c in q], lage)
    n = max(1, len(punkte))
    ab, summe = [], 0.0
    for q in punkte:
        ab.append(raster.abstand(q))
        summe += ab[-1]
        if grenze is not None and summe / n > grenze + 1e-9:
            return math.inf
    return sum(ab) / n


def _kandidat(lage, d, wenden, laenge):
    from .steckverbindung import lage_drehen
    return lage_drehen(lage, d, wenden, laenge)


EIGEN = (0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0)     # Rohrsystem des Körpers selbst (Ende A, Achse z, x)
_GEFUNDEN = {}          # (Muster-Punkte, eigene Punkte) -> Schritte (gleiche Körper einer Baugruppe: einmal suchen)
GEFUNDEN_MAX = 500


def _suchen(pm, pk):
    """Drehung/Wenden, mit der das Muster (Punkte pm) auf den Punkten pk liegt, im Rohrsystem des Körpers gerechnet
    (die Abstände hängen von seiner Lage im Raum nicht ab). Ergebnis (Schritte [(d, wenden)] oder None = Lage
    bleibt, vorher, nachher)."""
    raster = _Raster([tuple(pk[i:i + 3]) for i in range(0, len(pk) - 2, 3)])
    vorher = abweichung(pm, EIGEN, raster)
    if vorher <= GUT:
        return None, vorher, vorher
    laenge = max(pm[2::3])
    beste = (vorher, EIGEN, [])
    for wenden in (False, True):
        for d in range(0, 360, 15):
            k = _kandidat(EIGEN, float(d), wenden, laenge)
            a = abweichung(pm, k, raster, beste[0])
            if a < beste[0] - 1e-9:
                beste = (a, k, [(float(d), wenden)])
    for schritt in (5.0, 1.0, 0.2):         # fein nachsuchen (Rundrohr: Drehung beliebig)
        start, weg = beste[1], beste[2]
        for i in (-2, -1, 1, 2):
            k = _kandidat(start, i * schritt, False, laenge)
            a = abweichung(pm, k, raster, beste[0])
            if a < beste[0] - 1e-9:
                beste = (a, k, weg + [(i * schritt, False)])
    nachher = beste[0]
    if nachher < vorher * 0.5:
        return beste[2], vorher, nachher
    return None, vorher, vorher


def passende_lage(netz_muster, netz_k):
    """Lage, mit der netz_muster (Netz des ersten gleichen Körpers) dort liegt, wo netz_k (eigenes Netz des Körpers
    mit seiner 'lage') liegt. Ergebnis (Lage, mittlerer Abstand vorher, nachher); Lage unverändert, wenn sie schon
    passt oder keine bessere gefunden wird. Gesucht wird im Rohrsystem des Körpers; gleiche Paare (z. B. 50 gleiche
    Schrauben einer Baugruppe) nur einmal, die Schritte werden dann auf die eigene Lage angewendet."""
    lage = netz_k.get("lage")
    pm, pk = netz_muster.get("p") or [], netz_k.get("p") or []
    if not lage or len(lage) != 9 or len(pm) < 9 or len(pk) < 9:
        return lage, 0.0, 0.0
    schluessel = (tuple(pm), tuple(pk))
    if schluessel not in _GEFUNDEN:
        if len(_GEFUNDEN) >= GEFUNDEN_MAX:
            _GEFUNDEN.clear()
        _GEFUNDEN[schluessel] = _suchen(pm, pk)
    weg, vorher, nachher = _GEFUNDEN[schluessel]
    if weg is None:
        return lage, vorher, vorher
    laenge = max(pm[2::3])
    neu = lage
    for d, wenden in weg:
        neu = _kandidat(neu, d, wenden, laenge)
    return [round(float(c), 9) for c in neu], vorher, nachher


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
