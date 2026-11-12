"""3D-Auswahl, in allen 3D-Fenstern gleich (CAD-Entwicklungsplan Paket 3, Patrick 12.11.2026: „Körper, Fläche, Kante
oder Punkt wählen, klar anzeigen, was gewählt ist; Mehrfachauswahl, Fensterauswahl, Filter, Ausblenden, Isolieren,
Eigenschaften“).

Die Auswahl hängt an der Ansicht (ansicht3d.Ansicht3D.wahl) und arbeitet nur mit dem gezeigten Netz – am Teil selbst
ändert sie nichts. Elemente:

- Körper: in Baugruppe, Satz und STEP-Prüfdialog das Teil (Kennung je Dreieck, netz 'ti'); im einzelnen Teil die
  zusammenhängenden Körper des Netzes (das Teil, jedes Anbauteil).
- Fläche: zusammenhängende Dreiecke ohne Körperkante dazwischen (eben oder gewölbt), mit Flächeninhalt.
- Kante: gerade Körperkante oder Kreis/Bogen (messen3d.Geometrie), mit Länge bzw. Durchmesser.
- Punkt: Ecke oder Kreismitte.

Bedienung (Ansicht3D): Auswahl einschalten, Filter wählen; Maus darüber zeigt die Art, Klick wählt, Strg+Klick dazu
bzw. weg, Umschalt+Ziehen = Fenster (nach rechts: ganz im Fenster, nach links: auch berührt), Esc hebt auf.
Ausblenden (H), Isolieren (I), Alle einblenden (Umschalt+H) gelten für Körper.
"""
import math

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QPolygonF

from . import stil

ALLES, KOERPER, FLAECHE, KANTE, PUNKT = "Alles", "Körper", "Fläche", "Kante", "Punkt"
FILTER = (ALLES, KOERPER, FLAECHE, KANTE, PUNKT)
PUNKT_PX, KANTE_PX = 8.0, 6.0
SCHWEBE_MAX = 80000         # Hervorheben unter der Maus nur bis zu so vielen Dreiecken (darüber erst beim Klick)
FARBE_WAHL = "#FF7A00"      # gewählt
FARBE_SCHWEBE = "#00A0C8"   # unter der Maus
TEIL, ANBAU = "Teil", "Anbauteil"


def _schl(q):
    return (round(q[0], 2), round(q[1], 2), round(q[2], 2))


def _flaeche(a, b, c):
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    return math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2
                     + (u[0] * v[1] - u[1] * v[0]) ** 2) / 2


class _Bund:
    """Vereinigungsmengen (Union-Find) über 0 … n − 1."""

    def __init__(self, n):
        self.v = list(range(n))

    def wurzel(self, i):
        v = self.v
        while v[i] != i:
            v[i] = v[v[i]]
            i = v[i]
        return i

    def eins(self, i, j):
        a, b = self.wurzel(i), self.wurzel(j)
        if a != b:
            self.v[b] = a


class Elemente:
    """Körper und Flächen eines ansicht3d.Modell (einmal je Modell gerechnet).

    koerper_von[Dreieck] = Kennung, koerper = {Kennung: [Dreiecke]}, namen = {Kennung: Name};
    flaechen() = (flaeche_von[Dreieck], [dict(dreiecke, koerper, typ, flaeche, n)])."""

    def __init__(self, modell, aus_kennung=False, name=None):
        self.modell = modell
        mo = modell
        n = len(mo.dreiecke)
        self.koerper_von = [None] * n
        self.koerper, self.namen = {}, {}
        ids = mo.dreiecke_id if aus_kennung and len(mo.dreiecke_id) == n else None
        if ids is not None and any(k is not None for k in ids):
            for nr, k in enumerate(ids):
                k = "ohne" if k is None else k
                self.koerper_von[nr] = k
                self.koerper.setdefault(k, []).append(nr)
            for k in self.koerper:
                self.namen[k] = (name(k) if name is not None else None) or str(k)
        else:
            self._zusammenhang()
        self._flaechen = None

    def _zusammenhang(self):
        """Körper = zusammenhängende Dreiecke (gleiche Ecken auf 0,01 mm), Anbauteile ('AN') für sich."""
        mo = self.modell
        p = mo.punkte
        bund = _Bund(len(mo.dreiecke))
        orte = {}
        for nr, (i, j, k, art, _) in enumerate(mo.dreiecke):
            an = art == "AN"
            for x in (i, j, k):
                schl = (an, _schl(p[x]))
                alt = orte.get(schl)
                if alt is None:
                    orte[schl] = nr
                else:
                    bund.eins(alt, nr)
        gruppen = {}
        for nr in range(len(mo.dreiecke)):
            gruppen.setdefault(bund.wurzel(nr), []).append(nr)

        def inhalt(tris):
            return sum(_flaeche(p[mo.dreiecke[t][0]], p[mo.dreiecke[t][1]], p[mo.dreiecke[t][2]]) for t in tris)
        teile = sorted((g for g in gruppen.values() if mo.dreiecke[g[0]][3] != "AN"), key=inhalt, reverse=True)
        anbau = sorted((g for g in gruppen.values() if mo.dreiecke[g[0]][3] == "AN"), key=lambda g: g[0])
        for liste, vor, wort in ((teile, "k", TEIL), (anbau, "a", ANBAU)):
            for nr, tris in enumerate(liste):
                kid = f"{vor}{nr}"
                self.koerper[kid] = tris
                self.namen[kid] = wort if len(liste) == 1 else f"{wort} {nr + 1}"
                for t in tris:
                    self.koerper_von[t] = kid

    def flaechen(self):
        """Flächen: Dreiecke eines Körpers, die über eine Seite ohne Körperkante zusammenhängen. Große Netze (ohne
        Körperkanten, ansicht3d.KANTEN_MAX): keine Flächen."""
        if self._flaechen is not None:
            return self._flaechen
        mo = self.modell
        p = mo.punkte
        n = len(mo.dreiecke)
        kanten = {(a, b) for a, b, _ in mo.kanten()}
        von, liste = [None] * n, []
        if kanten:
            bund = _Bund(n)
            seiten = {}
            for nr, (i, j, k, _, _) in enumerate(mo.dreiecke):
                a, b, c = _schl(p[i]), _schl(p[j]), _schl(p[k])
                for x, y in ((a, b), (b, c), (c, a)):
                    if x == y:
                        continue
                    s = (x, y) if x < y else (y, x)
                    if s in kanten:
                        continue
                    alt = seiten.get(s)
                    if alt is None:
                        seiten[s] = nr
                    elif self.koerper_von[alt] == self.koerper_von[nr]:
                        bund.eins(alt, nr)
            gruppen = {}
            for nr in range(n):
                gruppen.setdefault(bund.wurzel(nr), []).append(nr)
            nummer, _ = mo.ebenen()
            for tris in gruppen.values():
                inhalt, s = 0.0, [0.0, 0.0, 0.0]
                for t in tris:
                    i, j, k, _, nn = mo.dreiecke[t]
                    f = _flaeche(p[i], p[j], p[k])
                    inhalt += f
                    for q in range(3):
                        s[q] += nn[q] * f
                eben = len({nummer[t] for t in tris}) == 1 if len(nummer) == n else False
                betrag = math.sqrt(sum(c * c for c in s)) or 1.0
                for t in tris:
                    von[t] = len(liste)
                liste.append(dict(dreiecke=tris, koerper=self.koerper_von[tris[0]], typ="eben" if eben else "gewölbt",
                                  flaeche=inhalt, n=tuple(c / betrag for c in s)))
        self._flaechen = (von, liste)
        return self._flaechen

    def masse(self, kid):
        """(Ausdehnung je Achse x, y, z; Oberfläche [mm²]; Mitte) eines Körpers."""
        mo = self.modell
        p = mo.punkte
        tris = self.koerper.get(kid) or []
        if not tris:
            return None
        pk = [p[x] for t in tris for x in mo.dreiecke[t][:3]]
        lo = [min(q[i] for q in pk) for i in range(3)]
        hi = [max(q[i] for q in pk) for i in range(3)]
        inhalt = sum(_flaeche(p[mo.dreiecke[t][0]], p[mo.dreiecke[t][1]], p[mo.dreiecke[t][2]]) for t in tris)
        return tuple(hi[i] - lo[i] for i in range(3)), inhalt, tuple((lo[i] + hi[i]) / 2 for i in range(3))


def sichtbar(modell, koerper_von, versteckt):
    """Modell ohne die Dreiecke der versteckten Körper (Punkte, Mitte und Größe bleiben: das Bild springt nicht).
    herkunft[Dreieck] = Nummer im vollen Modell. Ist nichts versteckt: das Modell selbst."""
    if not versteckt:
        return modell
    from .ansicht3d import Modell
    g = Modell.__new__(Modell)
    g.__dict__.update(modell.__dict__)
    bleibt = [nr for nr in range(len(modell.dreiecke)) if koerper_von[nr] not in versteckt]
    g.dreiecke = [modell.dreiecke[nr] for nr in bleibt]
    g.dreiecke_id = [modell.dreiecke_id[nr] for nr in bleibt] if modell.dreiecke_id else []
    g.herkunft = bleibt
    haupt_weg = "k0" in versteckt            # das Teil selbst ist ausgeblendet: seine Konturlinien auch
    if haupt_weg:
        g.linien, g.linien_id, g.mitten, g.koerper = [], [], [], []
    for merker in ("_grob", "_glatt", "_ebenen", "_kanten", "_glatt_kanten"):
        g.__dict__.pop(merker, None)
    g._grob = None
    return g


def schluessel(el):
    """Eindeutiger Schlüssel eines Elements (für dazu/weg mit Strg)."""
    art = el["art"]
    if art == KOERPER:
        return (art, el["id"])
    if art == FLAECHE:
        return (art, el["koerper"], tuple(round(c, 1) for c in el["mitte"]), round(el["flaeche"], 1))
    if art == KANTE:
        if el.get("kreis"):
            k = el["kreis"]
            return (art, "kreis", _schl(k["m"]), round(k["d"], 2))
        return (art, tuple(sorted((_schl(el["a"]), _schl(el["b"])))))
    return (art, _schl(el["p"]))


def titel(el):
    """Kurztext „Art: was“ für die Anzeige unter der Maus und in der Statuszeile."""
    from .messen3d import zahl
    art = el["art"]
    if art == KOERPER:
        return f"Körper: {el['name']}"
    if art == FLAECHE:
        return f"Fläche ({el['typ']}): {zahl(el['flaeche'], 1)} mm²"
    if art == KANTE:
        if el.get("kreis"):
            k = el["kreis"]
            return (f"Kante (Bogen): R {zahl(k['d'] / 2, 2)} mm" if k.get("bogen")
                    else f"Kante (Kreis): Ø {zahl(k['d'], 2)} mm")
        return f"Kante (gerade): {zahl(math.dist(el['a'], el['b']), 2)} mm"
    return f"Punkt ({el['was']})"


class Auswahl(QObject):
    """Zustand und Bedienung der Auswahl einer Ansicht3D (ansicht.wahl)."""
    geaendert = Signal()            # Auswahl, Filter, an/aus oder Sichtbarkeit geändert

    def __init__(self, ansicht):
        super().__init__(ansicht)
        self.ansicht = ansicht
        self.an, self.filter = False, ALLES
        self.gewaehlt, self.schwebe = [], None
        self.versteckt = set()
        self.fenster = None                         # (Start, Ende) als QPointF beim Aufziehen
        self.koerper_name = None                    # Funktion Kennung -> Name (Baugruppe, Satz, STEP-Prüfdialog)
        self.koerper_info = None                    # Funktion Kennung -> [Zeilen] für die Eigenschaften
        self._sicht, self._sicht_nr = [frozenset()], 0  # Verlauf der Sichtbarkeit (Rückgängig/Wiederholen)
        self._el = None                             # (volles Modell, Elemente)
        self._px = None                             # (Schlüssel der Ansicht, Pixel je Punkt)

    # ------------------------------------------------------------ Zustand
    def setzen(self, an=None, filter_=None):
        if an is not None:
            self.an = bool(an)
        if filter_ in FILTER:
            self.filter = filter_
        if not self.an:
            self.schwebe, self.fenster = None, None
        a = self.ansicht
        a._maus_verfolgen()
        if self.an and a.messen:
            a.messen_setzen(False)
        self.eigenschaften_zeigen()
        a.update()
        self.geaendert.emit()

    def aus_kennung(self):
        """Körper aus der Kennung je Dreieck (Baugruppe, Satz, STEP-Prüfdialog mit mehreren Teilen)?"""
        mo = self.ansicht.voll
        return bool(mo is not None and mo.dreiecke_id and (getattr(self.ansicht, "flaeche_vor_kante", False)
                                                           or (self.ansicht.netz or {}).get("teile")))

    def elemente(self):
        mo = self.ansicht.voll
        if mo is None:
            return None
        if self._el is None or self._el[0] is not mo:
            self._el = (mo, Elemente(mo, self.aus_kennung(), self.koerper_name))
        return self._el[1]

    def modell_neu(self):
        """Neues Netz in der Ansicht: Gewähltes bleibt (Körper über die Kennung, das andere über seine Lage),
        Verstecktes nur, solange es die Körper noch gibt."""
        self._el, self._px, self.schwebe = None, None, None
        if not (self.an or self.versteckt or self.gewaehlt):
            self.__dict__.pop("_ids", None)     # Auswahl ungenutzt: nichts rechnen (jede Eingabe im Editor zeichnet neu)
            return
        el = self.elemente()
        if el is None:
            self.gewaehlt, self.versteckt = [], set()
            return
        # Körper ohne Kennung (k0, a1 …) gelten nur für dieses Netz; mit Kennung, solange dieselben Körper da sind
        # (z. B. „Nur Gewähltes“ zählt die Körper neu)
        ids = frozenset(el.koerper)
        if not self.aus_kennung() or ids != getattr(self, "_ids", ids):
            self.versteckt = set()
            self._sicht, self._sicht_nr = [frozenset()], 0
            self.gewaehlt = [g for g in self.gewaehlt if g["art"] != KOERPER]
        self._ids = ids
        self.versteckt &= set(el.koerper)
        self.gewaehlt = [g for g in self.gewaehlt if g["art"] != KOERPER or g["id"] in el.koerper]

    def arten(self):
        """Welche Arten sind gewählt: z. B. „2 Körper“, „1 Fläche, 1 Kante“ oder ""."""
        zahl = {}
        for g in self.gewaehlt:
            zahl[g["art"]] = zahl.get(g["art"], 0) + 1
        mehr = {KOERPER: "Körper", FLAECHE: "Flächen", KANTE: "Kanten", PUNKT: "Punkte"}
        return ", ".join(f"{n} {a if n == 1 else mehr[a]}" for a, n in zahl.items())

    def koerper_ids(self):
        """Kennungen der gewählten Körper (bei Flächen: ihr Körper), ohne Doppelte, in Klickfolge."""
        out = []
        for g in self.gewaehlt:
            k = g["id"] if g["art"] == KOERPER else g.get("koerper")
            if k is not None and k not in out:
                out.append(k)
        return out

    # ------------------------------------------------------------ Elemente bauen
    def _koerper_el(self, kid):
        el = self.elemente()
        return dict(art=KOERPER, id=kid, name=el.namen.get(kid) or str(kid), koerper=kid)

    def _flaeche_el(self, nr):
        el = self.elemente()
        mo = el.modell
        f = el.flaechen()[1][nr]
        tris = [tuple(mo.punkte[x] for x in mo.dreiecke[t][:3]) for t in f["dreiecke"]]
        gewicht = sum(_flaeche(*t) for t in tris) or 1.0
        mitte = tuple(sum(_flaeche(*t) * (t[0][i] + t[1][i] + t[2][i]) / 3 for t in tris) / gewicht for i in range(3))
        return dict(art=FLAECHE, koerper=f["koerper"], typ=f["typ"], flaeche=f["flaeche"], n=f["n"], mitte=mitte,
                    dreiecke=tris)

    def koerper_setzen(self, ids, melden=False):
        """Körper mit den Kennungen ids wählen (Auswahl über die Bauteilliste)."""
        el = self.elemente()
        self.gewaehlt = [self._koerper_el(k) for k in ids if el is not None and k in el.koerper]
        self.eigenschaften_zeigen()
        self.ansicht.update()
        if melden:
            self.geaendert.emit()

    # ------------------------------------------------------------ Treffer
    def _pixel(self):
        """Pixel je Punkt des gezeigten Modells für die aktuelle Ansicht (gemerkt, bis sie sich ändert)."""
        a = self.ansicht
        mo = a.modell
        schl = (mo, a.width(), a.height(), a.gier, a.nick, a.zoom, a.versatz, a.perspektive)
        if self._px is None or self._px[0] != schl:
            bild = a.bildpunkt()
            self._px = (schl, [bild(q) for q in mo.punkte], bild)
        return self._px[1], self._px[2]

    def dreieck_unter(self, x, y):
        """Vorderstes gezeigtes Dreieck unter dem Pixel: (Nummer im vollen Modell, Punkt im Modell) oder None."""
        a = self.ansicht
        mo = a.modell
        if mo is None:
            return None
        px, _ = self._pixel()
        beste = None
        for nr, (i, j, k, _, _) in enumerate(mo.dreiecke):
            pa, pb, pc = px[i], px[j], px[k]
            if (pa[0] > x and pb[0] > x and pc[0] > x) or (pa[0] < x and pb[0] < x and pc[0] < x) or \
                    (pa[1] > y and pb[1] > y and pc[1] > y) or (pa[1] < y and pb[1] < y and pc[1] < y):
                continue
            det = (pb[1] - pc[1]) * (pa[0] - pc[0]) + (pc[0] - pb[0]) * (pa[1] - pc[1])
            if abs(det) < 1e-9:
                continue
            l1 = ((pb[1] - pc[1]) * (x - pc[0]) + (pc[0] - pb[0]) * (y - pc[1])) / det
            l2 = ((pc[1] - pa[1]) * (x - pc[0]) + (pa[0] - pc[0]) * (y - pc[1])) / det
            l3 = 1 - l1 - l2
            if min(l1, l2, l3) < -1e-6:
                continue
            tiefe = l1 * pa[2] + l2 * pb[2] + l3 * pc[2]
            if beste is None or tiefe > beste[0]:
                beste = (tiefe, nr, (l1, l2, l3))
        if beste is None:
            return None
        _, nr, (l1, l2, l3) = beste
        i, j, k = mo.dreiecke[nr][:3]
        punkt = tuple(l1 * mo.punkte[i][m] + l2 * mo.punkte[j][m] + l3 * mo.punkte[k][m] for m in range(3))
        herkunft = getattr(mo, "herkunft", None)
        return (herkunft[nr] if herkunft is not None else nr), punkt

    def vorgabe(self):
        """Wofür „Alles“ auf einer Fläche steht: in Fenstern mit mehreren Teilen der Körper, sonst die Fläche."""
        return KOERPER if self.aus_kennung() else FLAECHE

    def unter(self, x, y):
        """Element unter dem Pixel (x, y) nach dem Filter oder None. Bei „Alles“: Punkt vor Kante vor Fläche bzw.
        Körper."""
        a = self.ansicht
        if a.modell is None:
            return None
        f = self.filter
        el = self.elemente()
        if f in (ALLES, PUNKT, KANTE) and not (f == ALLES and self.vorgabe() == KOERPER):
            geo = a.geometrie()
            _, bild = self._pixel()
            if f in (ALLES, PUNKT):
                beste = None
                for q, was in [(e, "Ecke") for e in geo.ecken] + [(k["m"], "Kreismitte") for k in geo.kreise]:
                    px, py, t = bild(q)
                    d = math.hypot(px - x, py - y)
                    if d <= PUNKT_PX and (beste is None or d - t * 1e-3 < beste[0]):
                        beste = (d - t * 1e-3, q, was)
                if beste is not None:
                    return dict(art=PUNKT, p=tuple(beste[1]), was=beste[2])
            if f in (ALLES, KANTE):
                beste = None
                for g in geo.geraden:
                    pa, pb = bild(g["a"]), bild(g["b"])
                    dx, dy = pb[0] - pa[0], pb[1] - pa[1]
                    lg = dx * dx + dy * dy
                    t = 0.0 if lg < 1e-9 else max(0.0, min(1.0, ((x - pa[0]) * dx + (y - pa[1]) * dy) / lg))
                    d = math.hypot(pa[0] + t * dx - x, pa[1] + t * dy - y)
                    if d <= KANTE_PX and (beste is None or d < beste[0]):
                        beste = (d, dict(art=KANTE, a=tuple(g["a"]), b=tuple(g["b"])))
                for k in geo.kreise:
                    pk = kreis_punkte(k)
                    pp = [bild(q) for q in pk]
                    for (ax, ay, _), (bx, by, _) in zip(pp, pp[1:]):
                        dx, dy = bx - ax, by - ay
                        lg = dx * dx + dy * dy
                        t = 0.0 if lg < 1e-9 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / lg))
                        d = math.hypot(ax + t * dx - x, ay + t * dy - y)
                        if d <= KANTE_PX and (beste is None or d < beste[0]):
                            beste = (d, dict(art=KANTE, kreis=dict(m=tuple(k["m"]), n=tuple(k["n"]), d=k["d"],
                                                                   bogen=bool(k.get("bogen")), punkte=pk)))
                if beste is not None:
                    return beste[1]
            if f != ALLES:
                return None
        if f in (PUNKT, KANTE):
            return None
        tr = self.dreieck_unter(x, y)
        if tr is None:
            return None
        nr, punkt = tr
        art = self.vorgabe() if f == ALLES else f
        von, liste = el.flaechen()
        if art == FLAECHE and von[nr] is not None:
            e = self._flaeche_el(von[nr])
        elif el.koerper_von[nr] is not None:
            if art == FLAECHE and f == FLAECHE:
                return None                     # großes Netz ohne Flächen: der Filter „Fläche“ trifft nichts
            e = self._koerper_el(el.koerper_von[nr])
        else:
            return None
        e["punkt"] = punkt
        return e

    def im_fenster(self, x0, y0, x1, y1, beruehrt=False):
        """Elemente im Rechteck nach dem Filter. beruehrt: auch die, die nur hineinragen (Fenster nach links)."""
        a = self.ansicht
        if a.modell is None:
            return []
        x0, x1 = sorted((x0, x1))
        y0, y1 = sorted((y0, y1))
        px, bild = self._pixel()
        mo = a.modell

        def drin(q):
            return x0 <= q[0] <= x1 and y0 <= q[1] <= y1

        def passt(pixel):
            pixel = list(pixel)
            return bool(pixel) and (any(map(drin, pixel)) if beruehrt else all(map(drin, pixel)))

        def schneidet(u, v):
            """Schneidet die Strecke u–v das Rechteck (Liang-Barsky)?"""
            t0, t1 = 0.0, 1.0
            dx, dy = v[0] - u[0], v[1] - u[1]
            for d, q in ((-dx, u[0] - x0), (dx, x1 - u[0]), (-dy, u[1] - y0), (dy, y1 - u[1])):
                if abs(d) < 1e-12:
                    if q < 0:
                        return False
                    continue
                r = q / d
                if d < 0:
                    if r > t1:
                        return False
                    t0 = max(t0, r)
                else:
                    if r < t0:
                        return False
                    t1 = min(t1, r)
            return t0 <= t1

        def dreieck_trifft(pa, pb, pc):
            if schneidet(pa, pb) or schneidet(pb, pc) or schneidet(pc, pa):
                return True
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2          # Fenster ganz im Dreieck
            det = (pb[1] - pc[1]) * (pa[0] - pc[0]) + (pc[0] - pb[0]) * (pa[1] - pc[1])
            if abs(det) < 1e-9:
                return False
            l1 = ((pb[1] - pc[1]) * (mx - pc[0]) + (pc[0] - pb[0]) * (my - pc[1])) / det
            l2 = ((pc[1] - pa[1]) * (mx - pc[0]) + (pa[0] - pc[0]) * (my - pc[1])) / det
            return min(l1, l2, 1 - l1 - l2) >= 0

        def zug_trifft(pixel):
            pixel = list(pixel)
            return any(schneidet(u, v) for u, v in zip(pixel, pixel[1:]))
        f = self.vorgabe() if self.filter == ALLES else self.filter
        el = self.elemente()
        herkunft = getattr(mo, "herkunft", None)
        out = []
        if f in (KOERPER, FLAECHE):
            von = el.koerper_von if f == KOERPER else el.flaechen()[0]
            ecken, beruehrte = {}, set()
            for nr, d in enumerate(mo.dreiecke):
                k = von[herkunft[nr] if herkunft is not None else nr]
                if k is not None:
                    ecken.setdefault(k, set()).update(d[:3])
                    if beruehrt and k not in beruehrte and dreieck_trifft(px[d[0]], px[d[1]], px[d[2]]):
                        beruehrte.add(k)
            for k, idx in ecken.items():
                if k in beruehrte or (not beruehrt and passt(px[i] for i in idx)):
                    out.append(self._koerper_el(k) if f == KOERPER else self._flaeche_el(k))
        elif f == KANTE:
            geo = a.geometrie()
            for g in geo.geraden:
                pp = (bild(g["a"]), bild(g["b"]))
                if zug_trifft(pp) if beruehrt else passt(pp):
                    out.append(dict(art=KANTE, a=tuple(g["a"]), b=tuple(g["b"])))
            for k in geo.kreise:
                pk = kreis_punkte(k)
                pp = [bild(q) for q in pk]
                if zug_trifft(pp) if beruehrt else passt(pp):
                    out.append(dict(art=KANTE, kreis=dict(m=tuple(k["m"]), n=tuple(k["n"]), d=k["d"],
                                                          bogen=bool(k.get("bogen")), punkte=pk)))
        else:
            geo = a.geometrie()
            for q in geo.ecken:
                if drin(bild(q)):
                    out.append(dict(art=PUNKT, p=tuple(q), was="Ecke"))
        return out

    # ------------------------------------------------------------ Bedienung
    def waehlen(self, elemente, dazu=False):
        """Elemente wählen. dazu (Strg): jedes Element dazu bzw. wieder weg, sonst ersetzt es die Auswahl."""
        elemente = [e for e in elemente if e is not None]
        if not dazu:
            self.gewaehlt = list(elemente)
        else:
            for e in elemente:
                s = schluessel(e)
                rest = [g for g in self.gewaehlt if schluessel(g) != s]
                self.gewaehlt = rest if len(rest) < len(self.gewaehlt) else self.gewaehlt + [e]
        self.eigenschaften_zeigen()
        self.ansicht.update()
        self.geaendert.emit()

    def klick(self, x, y, dazu=False):
        e = self.unter(x, y)
        if e is None and dazu:
            return None
        self.waehlen([e] if e is not None else [], dazu)
        return e

    def fenster_fertig(self, dazu=False):
        if self.fenster is None:
            return []
        s, e = self.fenster
        self.fenster = None
        gefunden = self.im_fenster(s.x(), s.y(), e.x(), e.y(), beruehrt=e.x() < s.x())
        if dazu:            # Fenster mit Strg: dazu, nichts weg
            schon = {schluessel(g) for g in self.gewaehlt}
            gefunden = self.gewaehlt + [g for g in gefunden if schluessel(g) not in schon]
        self.waehlen(gefunden)
        return gefunden

    def schweben(self, x, y):
        a = self.ansicht
        if a.modell is None or len(a.modell.dreiecke) > SCHWEBE_MAX:
            return
        e = self.unter(x, y)
        if (e and schluessel(e)) != (self.schwebe and schluessel(self.schwebe)):
            self.schwebe = e
            a.update()

    def aufheben(self):
        self.waehlen([])

    def ausblenden(self):
        """Gewählte Körper ausblenden. Ergebnis: Anzahl."""
        ids = [k for k in self.koerper_ids() if k not in self.versteckt]
        el = self.elemente()
        if not ids or el is None or set(el.koerper) <= self.versteckt | set(ids):
            return 0                # nichts gewählt bzw. es bliebe nichts zu sehen
        self.versteckt |= set(ids)
        self.gewaehlt = []
        self._sichtbarkeit()
        return len(ids)

    def isolieren(self):
        """Nur die gewählten Körper zeigen. Ergebnis: Anzahl der ausgeblendeten."""
        ids = set(self.koerper_ids())
        el = self.elemente()
        if not ids or el is None:
            return 0
        weg = set(el.koerper) - ids
        self.versteckt = weg
        self._sichtbarkeit()
        return len(weg)

    def alle_einblenden(self):
        n = len(self.versteckt)
        self.versteckt = set()
        self._sichtbarkeit()
        return n

    def sicht_zurueck(self):
        """Letztes Ausblenden/Isolieren/Einblenden rückgängig. False, wenn es nichts gibt."""
        if self._sicht_nr <= 0:
            return False
        self._sicht_nr -= 1
        self.versteckt = set(self._sicht[self._sicht_nr])
        self._sichtbarkeit(merken=False)
        return True

    def sicht_vor(self):
        """Rückgängig gemachten Schritt der Sichtbarkeit wiederholen. False, wenn es nichts gibt."""
        if self._sicht_nr >= len(self._sicht) - 1:
            return False
        self._sicht_nr += 1
        self.versteckt = set(self._sicht[self._sicht_nr])
        self._sichtbarkeit(merken=False)
        return True

    def _sichtbarkeit(self, merken=True):
        a = self.ansicht
        if merken and frozenset(self.versteckt) != self._sicht[self._sicht_nr]:
            self._sicht = self._sicht[:self._sicht_nr + 1] + [frozenset(self.versteckt)]
            self._sicht_nr = len(self._sicht) - 1
        a.sichtbarkeit_anwenden()
        self._px, self.schwebe = None, None
        self.eigenschaften_zeigen()
        a.update()
        self.geaendert.emit()

    def auf_auswahl(self):
        """Ansicht auf das Gewählte zoomen (Blickrichtung bleibt). False, wenn nichts gewählt ist."""
        pk = self.punkte()
        if not pk:
            return False
        a = self.ansicht
        a.zoom, a.versatz = 1.0, (0.0, 0.0)
        bild = a.bildpunkt()
        px = [bild(v) for v in pk]
        x0, x1 = min(q[0] for q in px), max(q[0] for q in px)
        y0, y1 = min(q[1] for q in px), max(q[1] for q in px)
        w, h = max(1, a.width()), max(1, a.height())
        k = max(1.0, min(40.0, 0.7 * min(w / max(x1 - x0, 4.0), h / max(y1 - y0, 4.0))))
        a.zoom = k
        a.versatz = (-((x0 + x1) / 2 - w / 2) * k, -((y0 + y1) / 2 - h / 2) * k)
        a.update()
        a.gedreht.emit()
        return True

    def punkte(self, elemente=None):
        """Modellpunkte der Elemente (Vorgabe: des Gewählten)."""
        el = self.elemente()
        pk = []
        for g in (self.gewaehlt if elemente is None else elemente):
            if g["art"] == KOERPER and el is not None:
                mo = el.modell
                pk += [mo.punkte[x] for t in el.koerper.get(g["id"], ()) for x in mo.dreiecke[t][:3]]
            elif g["art"] == FLAECHE:
                pk += [q for t in g["dreiecke"] for q in t]
            elif g["art"] == KANTE:
                pk += g["kreis"]["punkte"] if g.get("kreis") else [g["a"], g["b"]]
            else:
                pk.append(g["p"])
        return pk

    # ------------------------------------------------------------ Eigenschaften
    def eigenschaften(self, g=None):
        """Zeilen für den Eigenschaftenbereich: zu einem Element bzw. zur ganzen Auswahl."""
        from .messen3d import zahl
        a = self.ansicht
        if g is None:
            if not self.gewaehlt:
                return []
            if len(self.gewaehlt) > 1:
                zeilen = [f"Gewählt: {self.arten()}"]
                fl = [x for x in self.gewaehlt if x["art"] == FLAECHE]
                ka = [x for x in self.gewaehlt if x["art"] == KANTE and not x.get("kreis")]
                if len(fl) == len(self.gewaehlt):
                    zeilen.append(f"Flächeninhalt zusammen: {zahl(sum(x['flaeche'] for x in fl), 1)} mm²")
                if len(ka) == len(self.gewaehlt):
                    zeilen.append(f"Länge zusammen: {zahl(sum(math.dist(x['a'], x['b']) for x in ka), 2)} mm")
                zeilen += [titel(x) for x in self.gewaehlt[:6]]
                if len(self.gewaehlt) > 6:
                    zeilen.append(f"… und {len(self.gewaehlt) - 6} weitere")
                return zeilen
            g = self.gewaehlt[0]
        geo = a.geometrie() if a.modell is not None else None
        zeilen = [titel(g)]
        if g["art"] == KOERPER:
            el = self.elemente()
            m = el.masse(g["id"]) if el is not None else None
            if self.koerper_info is not None:
                zeilen += [z for z in (self.koerper_info(g["id"]) or ()) if z]
            if m is not None:
                x, y, z = m[0]
                zeilen.append(f"Ausdehnung: {zahl(x, 1)} × {zahl(y, 1)} × {zahl(z, 1)} mm")
                zeilen.append(f"Oberfläche: {zahl(m[1] / 100, 1)} cm²")
                if geo is not None:
                    zeilen.append(f"Mitte: {geo.lage(m[2])}")
        elif g["art"] == FLAECHE:
            if geo is not None:
                zeilen.append(f"Normale: {geo.richtung(g['n'])}" if g["typ"] == "eben" else "mittlere Richtung: "
                              + geo.richtung(g["n"]))
                zeilen.append(f"Mitte: {geo.lage(g['mitte'])}")
            name = self.elemente().namen.get(g["koerper"]) if self.elemente() is not None else None
            if name:
                zeilen.append(f"Körper: {name}")
        elif g["art"] == KANTE:
            if g.get("kreis"):
                k = g["kreis"]
                if geo is not None:
                    zeilen.append(f"Mitte: {geo.lage(k['m'])}")
                    zeilen.append(f"Achse: {geo.richtung(k['n'])}")
                if not k.get("bogen"):
                    zeilen.append(f"Umfang: {zahl(math.pi * k['d'], 2)} mm")
            elif geo is not None:
                r = tuple(g["b"][i] - g["a"][i] for i in range(3))
                lg = math.sqrt(sum(c * c for c in r)) or 1.0
                zeilen.append(f"Richtung: {geo.richtung(tuple(c / lg for c in r))}")
                zeilen.append(f"von {geo.lage(g['a'])}")
                zeilen.append(f"bis {geo.lage(g['b'])}")
        elif geo is not None:
            zeilen.append(geo.lage(g["p"]))
        return zeilen

    def eigenschaften_zeigen(self):
        a = self.ansicht
        if a.messen:
            return
        a.tafel.zeigen(self.eigenschaften() if self.an else [])

    # ------------------------------------------------------------ Zeichnen
    def zeichnen(self, p):
        """Gewähltes (orange), Element unter der Maus (türkis mit Art), Fenster und Statuszeile über dem Bild."""
        a = self.ansicht
        if not self.an or a.modell is None:
            return
        bild = a.bildpunkt()
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        for g in self.gewaehlt:
            self._element_zeichnen(p, bild, g, QColor(FARBE_WAHL))
        if self.schwebe is not None and not any(schluessel(g) == schluessel(self.schwebe) for g in self.gewaehlt):
            self._element_zeichnen(p, bild, self.schwebe, QColor(FARBE_SCHWEBE))
        if self.fenster is not None:
            s, e = self.fenster
            nach_links = e.x() < s.x()
            p.setPen(QPen(stil.farbe("#2E8B2E" if nach_links else "#1F6FD0"), 1.2,
                          Qt.DashLine if nach_links else Qt.SolidLine))
            feld = stil.farbe("#2E8B2E" if nach_links else "#1F6FD0")
            feld.setAlpha(40)
            p.setBrush(QBrush(feld))
            p.drawRect(QRectF(s, e).normalized())
        text = self.status()
        fm = p.fontMetrics()
        b = fm.horizontalAdvance(text) + 14
        r = QRectF(a.width() - b - 8, 8, b, 20)
        feld = stil.farbe("#FFFFFF")
        feld.setAlpha(220)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(feld))
        p.drawRoundedRect(r, 4, 4)
        p.setPen(stil.farbe("#202020"))
        p.drawText(r, Qt.AlignCenter, text)
        p.restore()

    def status(self):
        """Statuszeile oben rechts: was unter der Maus liegt, was gewählt ist, wie viel ausgeblendet ist."""
        teile = [f"Auswahl ({self.filter})"]
        if self.schwebe is not None:
            teile.append(titel(self.schwebe))
        if self.gewaehlt:
            teile.append("gewählt: " + (titel(self.gewaehlt[0]) if len(self.gewaehlt) == 1 else self.arten()))
        if self.versteckt:
            teile.append(f"{len(self.versteckt)} Körper ausgeblendet")
        return " · ".join(teile)

    def _element_zeichnen(self, p, bild, g, farbe):
        art = g["art"]
        if art in (KOERPER, FLAECHE):
            if art == KOERPER:
                el = self.elemente()
                mo = el.modell if el is not None else None
                tris = [] if mo is None else [tuple(mo.punkte[x] for x in mo.dreiecke[t][:3])
                                              for t in el.koerper.get(g["id"], ())]
            else:
                tris = g["dreiecke"]
            pfad = QPainterPath()
            pfad.setFillRule(Qt.WindingFill)
            for t in tris:
                q = [bild(v) for v in t]
                # nur dem Betrachter zugewandte Dreiecke (Umlaufsinn im Bild)
                if (q[1][0] - q[0][0]) * (q[2][1] - q[0][1]) - (q[1][1] - q[0][1]) * (q[2][0] - q[0][0]) >= 0:
                    continue
                pfad.addPolygon(QPolygonF([QPointF(v[0], v[1]) for v in q] + [QPointF(q[0][0], q[0][1])]))
            feld = QColor(farbe)
            feld.setAlpha(95 if art == FLAECHE else 70)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(feld))
            p.drawPath(pfad)
            p.setBrush(Qt.NoBrush)
        elif art == KANTE:
            p.setPen(QPen(farbe, 4.0, Qt.SolidLine, Qt.RoundCap))
            pk = [bild(v) for v in (g["kreis"]["punkte"] if g.get("kreis") else (g["a"], g["b"]))]
            for u, v in zip(pk, pk[1:]):
                p.drawLine(QPointF(u[0], u[1]), QPointF(v[0], v[1]))
        else:
            q = bild(g["p"])
            p.setPen(QPen(QColor("#FFFFFF"), 1.5))       # fest: heller Ring um den Punkt auf dem 3D-Körper
            p.setBrush(QBrush(farbe))
            p.drawEllipse(QPointF(q[0], q[1]), 5.5, 5.5)
            p.setBrush(Qt.NoBrush)


def kreis_punkte(k, n=48):
    """Punkte eines Kreises dict(m, n, d) als geschlossener Linienzug (Bogen: der ganze Kreis als Näherung)."""
    m, achse, r = k["m"], k["n"], k["d"] / 2
    hilf = (1.0, 0.0, 0.0) if abs(achse[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = (achse[1] * hilf[2] - achse[2] * hilf[1], achse[2] * hilf[0] - achse[0] * hilf[2],
         achse[0] * hilf[1] - achse[1] * hilf[0])
    lg = math.sqrt(sum(c * c for c in u)) or 1.0
    u = tuple(c / lg for c in u)
    v = (achse[1] * u[2] - achse[2] * u[1], achse[2] * u[0] - achse[0] * u[2], achse[0] * u[1] - achse[1] * u[0])
    return [tuple(m[i] + r * (math.cos(2 * math.pi * s / n) * u[i] + math.sin(2 * math.pi * s / n) * v[i])
                  for i in range(3)) for s in range(n + 1)]


def teil_zeilen(q, mehr=()):
    """Eigenschaften einer Position q (dict) für den Eigenschaftenbereich: Name, Art, Abmessungen, Werkstoff,
    Stückzahl, Herkunft. mehr: weitere Zeilen."""
    from .messen3d import zahl
    q = q or {}
    zeilen = []
    kopf = " ".join(str(x) for x in (f"Pos. {q['pos']}" if q.get("pos") else "", q.get("artikel") or "") if x)
    if kopf:
        zeilen.append(kopf)
    if q.get("bezeichnung") and q.get("bezeichnung") != q.get("artikel"):
        zeilen.append(str(q["bezeichnung"]))
    if q.get("profil_id"):
        zeilen.append(f"Profil: {q['profil_id']}")
    if q.get("laenge"):
        zeilen.append(f"Länge: {zahl(float(q['laenge']), 1)} mm")
    if q.get("werkstoff_id"):
        zeilen.append(f"Werkstoff: {q['werkstoff_id']}")
    if q.get("stueck"):
        zeilen.append(f"Stückzahl: {q['stueck']}")
    if q.get("step_datei"):
        zeilen.append(f"Importquelle: {q['step_datei']}")
    return zeilen + [z for z in mehr if z]


class TeileKopplung:
    """Koppelt die Auswahl einer 3D-Ansicht mit einem Fenster, das Teile in einer Liste führt (Schweißbaugruppe,
    Satz in 3D): Körper „<vorsatz><Nummer>“ im Netz, koerper() = [(Positions-ID, Lage, Modell)] in dieser
    Reihenfolge, teil(Positions-ID) = Position (dict), auswahl() / auswahl_setzen(ids) = gewählte Positions-IDs
    des Fensters. Wählt man im 3D Körper, folgt die Liste; wählt man in der Liste, folgt das 3D (nach_zeigen)."""

    def __init__(self, ansicht, koerper, teil, auswahl, auswahl_setzen, vorsatz="teil:"):
        self.ansicht, self.koerper, self.teil = ansicht, koerper, teil
        self.auswahl, self.auswahl_setzen, self.vorsatz = auswahl, auswahl_setzen, vorsatz
        self._laeuft = False
        w = ansicht.wahl
        w.koerper_name, w.koerper_info = self.name, self.info
        w.geaendert.connect(self.aus_3d)

    def pid(self, kennung):
        k = str(kennung or "")
        liste = self.koerper() or []
        if not k.startswith(self.vorsatz) or not k[len(self.vorsatz):].isdigit():
            return None
        nr = int(k[len(self.vorsatz):])
        return liste[nr][0] if nr < len(liste) else None

    def name(self, kennung):
        q = self.teil(self.pid(kennung)) or {}
        return " ".join(str(x) for x in (f"Pos. {q['pos']}" if q.get("pos") else "",
                                         q.get("artikel") or q.get("bezeichnung") or "") if x) or None

    def info(self, kennung):
        return teil_zeilen(self.teil(self.pid(kennung)))[1:]

    def aus_3d(self):
        """Im 3D gewählte Körper: ihre Teile in der Liste wählen."""
        w = self.ansicht.wahl
        if not w.an or self._laeuft:
            return
        ids = []
        for k in w.koerper_ids():
            p = self.pid(k)
            if p is not None and p not in ids:
                ids.append(p)
        if set(ids) == set(self.auswahl() or ()) or (not ids and any(g["art"] != KOERPER for g in w.gewaehlt)):
            return
        self._laeuft = True
        try:
            self.auswahl_setzen(ids)
        finally:
            self._laeuft = False

    def nach_zeigen(self):
        """Nach dem Neuzeichnen: in der Liste gewählte Teile auch im 3D als Körper wählen."""
        w = self.ansicht.wahl
        if not w.an or self._laeuft:
            return
        soll = set(self.auswahl() or ())
        hat = {self.pid(k) for k in w.koerper_ids()}
        if soll == hat or any(g["art"] != KOERPER for g in w.gewaehlt):
            return
        w.koerper_setzen([f"{self.vorsatz}{nr}" for nr, k in enumerate(self.koerper() or []) if k[0] in soll])
