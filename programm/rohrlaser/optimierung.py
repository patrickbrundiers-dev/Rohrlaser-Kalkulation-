"""Stangenoptimierung: teilt die Teile je Profil + Werkstoff + Stangenlänge auf möglichst wenige Stangen auf.

Regeln:
- Belegung = Endbeschnitt + Teile + Trennungen + Schnittverlust des letzten Schnitts;
  frei bleiben muss der Greiferrest.
- Trennung zwischen zwei Teilen: beide zugewandten Enden gerade = 1 gemeinsamer Schnitt
  (1 × Schnittverlust), sonst 2 Schnitte (2 × Schnittverlust + Abstand getrennte Schnitte).
- Teile werden nie gewendet (Ende A bleibt vorn), nur um die eigene Achse gedreht (Patrick 21.10.2026):
  Rechteckrohr 0°/180°, Quadrat- und Rundrohr 0°/90°/180°/270°. Gedreht wird nur ein Teil ohne Nahtvorgabe; bei
  fester Naht folgt die Drehung aus der Naht der Stange, bei unbekannter Naht bleibt das Teil wie gezeichnet.
- Gehrungen ineinanderlegen: zwei benachbarte ebene schräge Enden rücken zusammen, bis an der engsten Stelle der
  Abstand 2 × Schnittverlust + Abstand senkrecht zur steileren Schnittfläche erreicht ist (kein gemeinsamer Schnitt).
  Genutzt nur, wenn es kürzer ist als die normale Trennung. Siehe gehrung_trennung.
- Keine Restlagerverwaltung: Reste sind Verschnitt.

Verfahren: First-Fit- und Best-Fit-Decreasing mit Auflösen schwach belegter Stangen; ist das nicht nachweislich
optimal, rechnet die Schnittmuster-Optimierung (Spaltengenerierung nach Gilmore-Gomory: gleiche Teile als Typ,
Schnittmuster je Stange, lineares Programm über die Muster) eine Einteilung und eine Schranke; danach für kleine
Gruppen die exakte Suche. Alle Grenzen sind Schrittzahlen, keine Zeiten: das Ergebnis ist auf jedem Rechner gleich.
Mit Gehrungen, die sich ineinanderlegen lassen, gilt die Schranke der Schnittmuster nicht (die Muster rechnen ohne
Ineinanderlegen); die Untergrenze zieht dann je Teil die größtmögliche Überlappung ab.
"""
import math
from dataclasses import dataclass, field, replace

from . import normprofile

EPS = 1e-6
EXAKT_MAX_TEILE = 60     # exakte Suche nur für Gruppen bis zu so vielen Teilen
EXAKT_MAX_KNOTEN = 20000  # Suchschritte je Gruppe, danach gilt das beste bis dahin gefundene Ergebnis
MUSTER_MAX_RUNDEN = 300    # neue Schnittmuster je Gruppe
MUSTER_MAX_KNOTEN = 50000  # Suchschritte je Suche nach dem besten Schnittmuster
FREI, FEST, UNBEKANNT = "frei", "fest", "unbekannt"     # Drehfreigabe eines Teils (aus der Nahtvorgabe)


@dataclass(frozen=True)
class Teil:
    zeile: int          # Bezug auf die Position (Index im Angebot)
    pos: object
    artikel: str
    nr: int             # laufende Nummer innerhalb der Position (1..Stückzahl)
    laenge: float
    a_gerade: bool      # Anfang (Ende A) gerade
    b_gerade: bool
    a_schnitt: float    # Schnittlänge Ende A [mm] (für Einsparung)
    b_schnitt: float
    # ebene Gehrung je Ende: (Winkel gegen den geraden Schnitt [°], Richtung [°], in der das Teil an diesem Ende am
    # längsten ist; von Ende A gesehen 0° oben, 90° rechts, Rechteckrohr mit der Breitseite oben) oder None
    a_gehrung: tuple = None
    b_gehrung: tuple = None
    drehung: str = FREI     # frei | fest | unbekannt (naht.py: keine Vorgabe | feste Position | unbekannt)
    naht: float = None      # fest: Nahtwinkel [°]


@dataclass
class Gruppe:
    profil: str
    werkstoff: str
    stange: float
    endbeschnitt: float
    greiferrest: float
    kerf: float
    abstand: float
    oberflaeche: str = ""    # leer = roh; unterschiedliche Oberflächen nie auf derselben Stange
    teile: list = field(default_factory=list)
    bewiesen: bool = False   # Stangenzahl ist nachweislich minimal
    schranke: int = 0        # nachgewiesene Mindestzahl Stangen (Untergrenze oder Schranke der Schnittmuster)
    beistellung: str = ""    # 'Kunde' = vom Kunden beigestelltes Material; nie mit eigenem Material auf einer Stange
    # Querschnitt für das Ineinanderlegen von Gehrungen: ('Kasten', Breite, Höhe) mit der Breitseite oben,
    # ('Rund', Radius) oder () = keine Gehrungen ineinanderlegen
    querschnitt: tuple = ()

    @property
    def nutzbar_bis(self):
        return self.stange - self.greiferrest


# ------------------------------------------------------------------ Drehung um die eigene Achse
def raster(g):
    """Schritt der zulässigen Drehungen [°]: Rechteckrohr 180, Quadrat- und Rundrohr 90, sonst 360 (keine)."""
    q = g.querschnitt
    if not q:
        return 360
    if q[0] == "Kasten" and abs(q[1] - q[2]) > EPS:
        return 180
    return 90


def drehungen(g, t, naht_stange=0):
    """Zulässige Drehungen eines Teils auf der Stange [°]. naht_stange: Lage der Naht der Stange (0, 90, 180, 270)."""
    r = raster(g)
    if t.drehung == FREI:
        return tuple(range(0, 360, r))
    if t.drehung == FEST and t.naht is not None and r < 360:
        if g.querschnitt[0] == "Rund":
            return ((naht_stange - t.naht) % 360,)
        return (int((naht_stange - round(t.naht / 90) * 90) % 360),)
    return (0,)


def naht_lagen(g, teile):
    """Mögliche Lagen der Naht der Stange (0, 90, 180, 270) für die Teile mit fester Naht; [] = unvereinbar
    (Rechteckrohr: Naht auf Breit- und auf Schmalseite verlangt)."""
    fest = [t for t in teile if t.drehung == FEST and t.naht is not None]
    if not fest or raster(g) == 360:
        return [0]
    if raster(g) == 180:
        seiten = {round(t.naht / 90) % 2 for t in fest}
        if len(seiten) > 1:
            return []
        seite = seiten.pop()
        return [s for s in (0, 90, 180, 270) if s // 90 % 2 == seite]
    return [0, 90, 180, 270]


def _stuetz(g, vx, vy):
    """Stützfunktion des Querschnitts: größte Projektion eines Querschnittspunkts auf (vx, vy) (x rechts, y oben)."""
    q = g.querschnitt
    if q[0] == "Rund":
        return q[1] * math.hypot(vx, vy)
    return q[1] / 2 * abs(vx) + q[2] / 2 * abs(vy)


def _richtung(winkel):
    w = math.radians(winkel)
    return math.sin(w), math.cos(w)          # 0° oben, 90° rechts


def gehrung_tiefe(g, geh):
    """Größte Überlappung, die eine Gehrung erlauben kann [mm]: Tiefe des schrägen Schnitts über den Querschnitt."""
    if not geh or not g.querschnitt:
        return 0.0
    x, y = _richtung(geh[1])
    return math.tan(math.radians(geh[0])) * _stuetz(g, x, y)


def gehrung_trennung(g, b_geh, r1, a_geh, r2):
    """Materialverbrauch zwischen Ende B eines Teils (Gehrung b_geh, Drehung r1) und Ende A des nächsten (a_geh, r2),
    wenn beide ineinandergelegt werden. Ende B: Material bis z ≤ z1 + t1·(u1·p), Ende A ab z ≥ z2 − t2·(u2·p)
    (p = Punkt im Querschnitt, u = Richtung, in der das Teil am längsten ist, t = tan Winkel). Die Schnittflächen
    müssen überall mindestens G = (2 × Schnittverlust + Abstand) / cos(steilerer Winkel) entlang der Achse
    auseinander liegen (= Abstand senkrecht zur steileren Fläche). Verbrauch = Abstand der Ausdehnungen:
    G + h(t1·u1 + t2·u2) − t1·h(u1) − t2·h(u2), h = Stützfunktion des Querschnitts; negativ = Teile überlappen sich
    in der Länge."""
    t1, t2 = math.tan(math.radians(b_geh[0])), math.tan(math.radians(a_geh[0]))
    x1, y1 = _richtung(b_geh[1] + r1)
    x2, y2 = _richtung(a_geh[1] + r2)
    abstand = (2 * g.kerf + g.abstand) / math.cos(math.radians(max(b_geh[0], a_geh[0])))
    return (abstand + _stuetz(g, t1 * x1 + t2 * x2, t1 * y1 + t2 * y2) - t1 * _stuetz(g, x1, y1)
            - t2 * _stuetz(g, x2, y2))


def kante(g, geh, drehung, oben=0):
    """Rücksprung der Schnittkante eines schrägen Endes in der Ansicht der Stange gegenüber seiner Spitze [mm]:
    (oben, unten) im Bild. oben: Winkel der Stange, der im Bild oben liegt (0 = Blick von der Seite, 270 = Blick
    von oben). (0, 0) = gerades Ende oder die Schräge ist in dieser Ansicht nicht zu sehen."""
    if not geh or not g.querschnitt:
        return 0.0, 0.0
    t = math.tan(math.radians(geh[0]))
    c = math.cos(math.radians(geh[1] + drehung - oben))
    q = g.querschnitt
    if q[0] == "Rund":
        return t * q[1] * (1 - c), t * q[1] * (1 + c)
    hh = (q[2] if oben % 180 == 0 else q[1]) / 2
    return t * hh * (abs(c) - c), t * hh * (abs(c) + c)


def ansicht(g, folge):
    """Ansicht für das Stangenbild: 0 (von der Seite, 0° oben) oder 270 (von oben), je nachdem, in welcher die
    Schrägen der Gehrungen stärker zu sehen sind."""
    if not g.querschnitt or g.querschnitt[0] == "Rund":
        return 0
    w = {0: 0.0, 270: 0.0}
    for t, d in folge:
        for geh in (t.a_gehrung, t.b_gehrung):
            for oben in w:
                w[oben] += sum(kante(g, geh, d, oben))
    return 270 if w[270] > w[0] + EPS else 0


def verschachtelbar(g, t):
    """Kann das Teil an einem Ende mit einem Nachbarn ineinandergelegt werden?"""
    return bool(g.querschnitt) and (t.a_gehrung is not None or t.b_gehrung is not None)


# ------------------------------------------------------------------ Belegung einer Stange
def trennung(kerf, abstand, ende_gerade, anfang_gerade):
    """Materialverbrauch zwischen zwei Teilen."""
    return kerf if (ende_gerade and anfang_gerade) else 2 * kerf + abstand


def trennung_teile(g, t1, r1, t2, r2):
    """Materialverbrauch zwischen Teil t1 (Drehung r1) und dem folgenden t2 (Drehung r2): gemeinsamer Schnitt bei
    zwei geraden Enden, sonst 2 Schnitte oder – kürzer – Gehrungen ineinandergelegt."""
    normal = trennung(g.kerf, g.abstand, t1.b_gerade, t2.a_gerade)
    if t1.b_gerade and t2.a_gerade or t1.b_gehrung is None or t2.a_gehrung is None or not g.querschnitt:
        return normal
    # Kasten: gleich bei Drehung um den Rasterschritt (180° bzw. 90°), Rund: nur die Drehung zueinander zählt
    schluessel = (t1.b_gehrung, t2.a_gehrung, r1 % raster(g) if g.querschnitt[0] == "Kasten" else 0, (r2 - r1) % 360)
    speicher = _speicher(g)
    if schluessel not in speicher:
        speicher[schluessel] = min(normal, gehrung_trennung(g, t1.b_gehrung, r1, t2.a_gehrung, r2))
    return speicher[schluessel]


_SPEICHER = {}


def _speicher(g):
    """Zwischenspeicher der Gehrungs-Trennungen je Querschnitt, Schnittverlust und Abstand."""
    return _SPEICHER.setdefault((g.querschnitt, g.kerf, g.abstand), {})


def ineinander(g, t1, r1, t2, r2):
    """Liegen die Gehrungen der beiden Teile ineinander (kürzer als 2 Schnitte)?"""
    return not (t1.b_gerade and t2.a_gerade) and \
        trennung_teile(g, t1, r1, t2, r2) < trennung(g.kerf, g.abstand, False, False) - EPS


def lage(teil, drehung=0):
    """(Anfang gerade, Ende gerade, Schnitt Anfang, Schnitt Ende) in Lage auf der Stange. Teile werden nie gewendet:
    die Drehung um die eigene Achse ändert die Enden nicht."""
    return teil.a_gerade, teil.b_gerade, teil.a_schnitt, teil.b_schnitt


def _kette_gerade(teile):
    """Reihenfolge ohne Wenden mit möglichst vielen gemeinsamen Schnitten (gerades Ende B an geradem Ende A):
    schräg-gerade, alle gerade-gerade, gerade-schräg, dann die übrigen Paare schräg-gerade + gerade-schräg, Rest."""
    ss = [t for t in teile if t.a_gerade and t.b_gerade]
    ns = [t for t in teile if not t.a_gerade and t.b_gerade]
    sn = [t for t in teile if t.a_gerade and not t.b_gerade]
    nn = [t for t in teile if not t.a_gerade and not t.b_gerade]
    folge = []
    if ns:
        folge.append(ns.pop(0))
    folge += ss
    if sn:
        folge.append(sn.pop(0))
    while ns and sn:
        folge += [ns.pop(0), sn.pop(0)]
    return folge + nn + ns + sn


def _drehungen_waehlen(g, folge, naht_stange):
    """Drehungen für eine feste Reihenfolge (dynamische Programmierung über die zulässigen Drehungen je Teil):
    (Verbrauch der Trennungen, [Drehung je Teil])."""
    stufen = []
    for i, t in enumerate(folge):
        moegl = drehungen(g, t, naht_stange)
        if i == 0:
            stufen.append({r: (0.0, None) for r in moegl})
            continue
        vorher = stufen[-1]
        stufe = {}
        for r in moegl:
            stufe[r] = min(((v[0] + trennung_teile(g, folge[i - 1], rv, t, r), rv) for rv, v in vorher.items()),
                           key=lambda x: (round(x[0], 6), x[1]))
        stufen.append(stufe)
    if not stufen:
        return 0.0, []
    r = min(stufen[-1], key=lambda x: (stufen[-1][x][0], x))
    summe = stufen[-1][r][0]
    wahl = [r]
    for i in range(len(stufen) - 1, 0, -1):
        r = stufen[i][r][1]
        wahl.append(r)
    return summe, wahl[::-1]


def _kette_gehrung(g, teile, naht_stange):
    """Reihenfolge für Teile mit Gehrungen: Verbindungen mit dem kleinsten Verbrauch zuerst (jede Kante nur, wenn
    das Teil noch keinen Nachfolger bzw. Vorgänger hat und kein Kreis entsteht), Ketten danach aneinander."""
    n = len(teile)
    kosten = []
    for i, t1 in enumerate(teile):
        for j, t2 in enumerate(teile):
            if i != j:
                c = min(trennung_teile(g, t1, r1, t2, r2) for r1 in drehungen(g, t1, naht_stange)
                        for r2 in drehungen(g, t2, naht_stange))
                kosten.append((c, i, j))
    kosten.sort()
    nach, vor, kopf = [None] * n, [None] * n, list(range(n))

    def wurzel(i):
        while kopf[i] != i:
            kopf[i] = kopf[kopf[i]]
            i = kopf[i]
        return i
    normal = trennung(g.kerf, g.abstand, False, False)
    for c, i, j in kosten:
        if c >= normal - EPS and not (teile[i].b_gerade and teile[j].a_gerade):
            continue            # nur Verbindungen, die etwas bringen
        if nach[i] is None and vor[j] is None and wurzel(i) != wurzel(j):
            nach[i], vor[j] = j, i
            kopf[wurzel(j)] = wurzel(i)
    folge = []
    for i in range(n):
        if vor[i] is None:
            while i is not None:
                folge.append(teile[i])
                i = nach[i]
    return folge


def anordnen(teile, g=None):
    """Reihenfolge und Drehung um die eigene Achse so wählen, dass möglichst viele gerade Enden aneinanderliegen
    und Gehrungen ineinander. Ohne Gehrungen zum Ineinanderlegen: _kette_gerade, Drehung 0. Sonst die bessere von
    _kette_gerade und _kette_gehrung, je mit den besten Drehungen, für jede mögliche Lage der Naht der Stange.
    Ergebnis: Liste (Teil, Drehung [°])."""
    gerade = _kette_gerade(list(teile))
    if g is None or not g.querschnitt or sum(verschachtelbar(g, t) for t in teile) < 2 and not any(
            t.drehung == FEST for t in teile):
        return [(t, 0) for t in gerade]
    beste = None
    for naht_stange in naht_lagen(g, teile) or [0]:
        for folge in (gerade, _kette_gehrung(g, list(teile), naht_stange)):
            summe, wahl = _drehungen_waehlen(g, folge, naht_stange)
            if beste is None or summe < beste[0] - EPS:
                beste = (summe, list(zip(folge, wahl)))
    return beste[1]


def verbrauch(g, folge):
    """Position hinter dem letzten Schnitt (inkl. Schnittverlust) ab Stangenanfang."""
    pos = g.endbeschnitt
    vorher = None
    for t, r in folge:
        if vorher is not None:
            pos += trennung_teile(g, vorher[0], vorher[1], t, r)
        pos += t.laenge
        vorher = (t, r)
    return pos + (g.kerf if folge else 0)


def vertraeglich(g, teile):
    """Dürfen die Teile auf dieselbe Stange? Rechteckrohr: feste Naht nicht zugleich auf Breit- und Schmalseite."""
    return bool(naht_lagen(g, teile))


def passt(g, teile):
    return vertraeglich(g, teile) and verbrauch(g, anordnen(teile, g)) <= g.nutzbar_bis + EPS


def mindestbedarf(g, t):
    """Kleinstmöglicher Längenbedarf eines Teils auf der Stange (Länge + Schnittverlust − größtmögliche Überlappung
    beider Gehrungen); Grundlage der Untergrenzen."""
    return t.laenge + g.kerf - gehrung_tiefe(g, t.a_gehrung) - gehrung_tiefe(g, t.b_gehrung)


# ------------------------------------------------------------------ Packverfahren
def sortiert(teile):
    return sorted(teile, key=lambda t: (-t.laenge, t.zeile, t.nr))


def first_fit(g, teile):
    stangen = []
    for t in sortiert(teile):
        for s in stangen:
            if passt(g, s + [t]):
                s.append(t)
                break
        else:
            stangen.append([t])
    return stangen


def best_fit(g, teile):
    stangen = []
    for t in sortiert(teile):
        beste, rest_min = None, None
        for s in stangen:
            if not vertraeglich(g, s + [t]):
                continue
            v = verbrauch(g, anordnen(s + [t], g))
            if v <= g.nutzbar_bis + EPS and (rest_min is None or g.nutzbar_bis - v < rest_min):
                beste, rest_min = s, g.nutzbar_bis - v
        if beste is None:
            stangen.append([t])
        else:
            beste.append(t)
    return stangen


def aufloesen(g, stangen):
    """Schwach belegte Stangen auflösen, wenn alle ihre Teile in andere Stangen passen."""
    stangen = [list(s) for s in stangen]
    geaendert = True
    while geaendert and len(stangen) > 1:
        geaendert = False
        for s in sorted(stangen, key=lambda s: sum(t.laenge for t in s)):
            andere = [list(x) for x in stangen if x is not s]
            ok = True
            for t in sortiert(s):
                ziel = None
                for x in sorted(andere, key=lambda x: -verbrauch(g, anordnen(x, g))):
                    if passt(g, x + [t]):
                        ziel = x
                        break
                if ziel is None:
                    ok = False
                    break
                ziel.append(t)
            if ok:
                stangen = andere
                geaendert = True
                break
    return stangen


def gemeinsame_schnitte(folge):
    n = 0
    for (t1, d1), (t2, d2) in zip(folge, folge[1:]):
        if lage(t1, d1)[1] and lage(t2, d2)[0]:
            n += 1
    return n


def gehrungen_ineinander(g, folge):
    """Anzahl der Stellen, an denen Gehrungen ineinanderliegen."""
    return sum(1 for (t1, r1), (t2, r2) in zip(folge, folge[1:]) if ineinander(g, t1, r1, t2, r2))


def gleichartig(a, b):
    return a.laenge == b.laenge and a.a_gerade == b.a_gerade and a.b_gerade == b.b_gerade and \
        (a.a_gehrung, a.b_gehrung, a.drehung, a.naht) == (b.a_gehrung, b.b_gehrung, b.drehung, b.naht)


def exakt(g, ziel):
    """Exakte Suche (Branch and Bound) nach einer Einteilung mit weniger als `ziel` Stangen.
    Teile in der Reihenfolge von sortiert(), jedes Teil der Reihe nach in jede vorhandene Stange,
    dann in eine neue. Abgeschnitten wird, wenn selbst bei voller Nutzung aller freien Längen
    nicht weniger Stangen als bisher bestes Ergebnis möglich sind. Ergebnis: (Stangen oder None,
    Suche vollständig)."""
    teile = sortiert(g.teile)
    n = len(teile)
    nutz = g.nutzbar_bis - g.endbeschnitt
    bedarf = [mindestbedarf(g, t) for t in teile]
    rest = [0.0] * (n + 1)
    for i in range(n - 1, -1, -1):
        rest[i] = rest[i + 1] + bedarf[i]
    ug = untergrenze(g)
    stangen, belegt, zu = [], [], [0] * n
    zustand = dict(beste=None, beste_n=ziel, knoten=0, abbruch=False)

    def suche(i):
        if i == n:
            zustand["beste"] = [list(s) for s in stangen]
            zustand["beste_n"] = len(stangen)
            return
        zustand["knoten"] += 1
        if zustand["knoten"] > EXAKT_MAX_KNOTEN:
            zustand["abbruch"] = True
            return
        frei = 0.0
        for b in belegt:
            frei += nutz - b
        neu = 0
        if rest[i] > frei + EPS:
            neu = math.ceil((rest[i] - frei) / nutz - EPS)
        if len(stangen) + neu >= zustand["beste_n"]:
            return
        t = teile[i]
        start = zu[i - 1] if i > 0 and gleichartig(teile[i - 1], t) else 0
        for s in range(start, len(stangen)):
            if belegt[s] + bedarf[i] > nutz + EPS or not passt(g, stangen[s] + [t]):
                continue
            stangen[s].append(t)
            belegt[s] += bedarf[i]
            zu[i] = s
            suche(i + 1)
            stangen[s].pop()
            belegt[s] -= bedarf[i]
            if zustand["abbruch"] or zustand["beste_n"] <= ug:
                return
        if len(stangen) + 1 < zustand["beste_n"]:
            stangen.append([t])
            belegt.append(bedarf[i])
            zu[i] = len(stangen) - 1
            suche(i + 1)
            stangen.pop()
            belegt.pop()

    suche(0)
    return zustand["beste"], not zustand["abbruch"] or zustand["beste_n"] <= ug


def optimiere(g):
    """Ergebnis: Liste von Stangen, je Stange die angeordnete Folge [(Teil, gedreht)].
    Setzt g.bewiesen, wenn die Stangenzahl nachweislich minimal ist."""
    kandidaten = []
    for verfahren in (first_fit, best_fit):
        st = aufloesen(g, verfahren(g, g.teile))
        folgen = [anordnen(s, g) for s in st]
        kandidaten.append((len(folgen), sum(verbrauch(g, f) for f in folgen), folgen))
    kandidaten.sort(key=lambda k: (k[0], k[1]))
    folgen = kandidaten[0][2]
    g.schranke = untergrenze(g)
    g.bewiesen = len(folgen) <= g.schranke
    if not g.bewiesen:
        st, schranke = muster_optimierung(g)
        g.schranke = max(g.schranke, schranke)
        neu = [anordnen(s, g) for s in st]
        if sum(len(s) for s in st) == len(g.teile) and (len(neu), sum(verbrauch(g, f) for f in neu) + EPS) < \
                (len(folgen), sum(verbrauch(g, f) for f in folgen)):
            folgen = neu
        g.bewiesen = len(folgen) <= g.schranke
    if not g.bewiesen and len(g.teile) <= EXAKT_MAX_TEILE:
        st, g.bewiesen = exakt(g, len(folgen))
        if st is not None:
            folgen = [anordnen(s, g) for s in st]
    # Stangen mit der höchsten Belegung zuerst (Reststange zuletzt)
    folgen.sort(key=lambda f: (-verbrauch(g, f), f[0][0].zeile))
    return folgen


def bewertung(g, n_stangen):
    """Text für die Auswertung: wie nah das Ergebnis am Optimum liegt."""
    if n_stangen <= untergrenze(g):
        return "optimal (Untergrenze erreicht)"
    if n_stangen <= g.schranke:
        return "optimal (Schranke der Schnittmuster erreicht)"
    if g.bewiesen:
        return "optimal (alle Einteilungen geprüft)"
    return "nicht bewiesen (Suche begrenzt)"


# ------------------------------------------------------------------ Schnittmuster (Spaltengenerierung)
def typ(t):
    """Gleiche Teile (Länge, Enden, Schnittlängen, Gehrungen, Drehfreigabe) sind für die Schnittmuster ein Typ."""
    return (t.laenge, t.a_gerade, t.b_gerade, t.a_schnitt, t.b_schnitt, t.a_gehrung or (), t.b_gehrung or (),
            t.drehung, -1 if t.naht is None else t.naht)


def bestes_muster(g, typen, bedarf, wert):
    """Schnittmuster (Anzahl je Typ, höchstens der Bedarf) mit dem größten Gesamtwert, das auf eine Stange passt.
    Tiefensuche, je Typ zuerst die größte mögliche Anzahl; abgeschnitten wird, wenn selbst die freie Länge mit dem
    besten Wert je mm nicht mehr reicht. Ergebnis: (Muster, Suche vollständig)."""
    n = len(typen)
    beste, zahl, knoten = [None, -1.0], [0] * n, [0]
    q_ab = [max([wert[j] / typen[j].laenge for j in range(i, n) if bedarf[j]] or [0.0]) for i in range(n + 1)]
    # Die Trennungen hängen ohne Gehrungen nur davon ab, wie viele Teile welche Enden haben (gerade-gerade,
    # schräg-gerade, gerade-schräg, schräg-schräg; anordnen ordnet danach, gewendet wird nie); der Verbrauch ist also
    # Länge der Teile + Zuschlag je Anzahl. Gehrungen zählen hier wie 2 Schnitte (sicher, nie zu kurz).
    arten = ((True, True), (False, True), (True, False), (False, False))
    art = [arten.index((t.a_gerade, t.b_gerade)) for t in typen]
    vertreter = {a: replace(typen[art.index(a)], laenge=0.0, a_gehrung=None, b_gehrung=None, drehung=FREI, naht=None)
                 for a in set(art)}
    zuschlag = {}

    def passt_zahl(anz, laenge):
        if anz not in zuschlag:
            null = [vertreter[a] for a in range(4) for _ in range(anz[a])]
            zuschlag[anz] = verbrauch(g, anordnen(null))
        return zuschlag[anz] + laenge <= g.nutzbar_bis + EPS

    def suche(i, w, laenge):
        knoten[0] += 1
        if w > beste[1] + 1e-9:
            beste[0], beste[1] = list(zahl), w
        if i == n or knoten[0] > MUSTER_MAX_KNOTEN:
            return
        if w + q_ab[i] * (g.nutzbar_bis - g.endbeschnitt - laenge) <= beste[1] + 1e-9:
            return
        anz = [0, 0, 0, 0]
        for j in range(i):
            anz[art[j]] += zahl[j]
        while zahl[i] < bedarf[i]:
            anz[art[i]] += 1
            if not passt_zahl(tuple(anz), laenge + typen[i].laenge * (zahl[i] + 1)):
                break
            zahl[i] += 1
        while True:
            suche(i + 1, w + wert[i] * zahl[i], laenge + typen[i].laenge * zahl[i])
            if zahl[i] == 0:
                break
            zahl[i] -= 1

    suche(0, 0.0, 0.0)
    return beste[0], knoten[0] <= MUSTER_MAX_KNOTEN


def simplex_max(c, a, b):
    """Lineares Programm max c·y unter a·y <= b, y >= 0 mit b >= 0 (Simplex mit Tableau, Regel von Bland gegen
    Kreisen). Ergebnis: (y, Zielwert, Schattenpreise der Zeilen, gelöst)."""
    m, n = len(a), len(c)
    tab = [list(a[i]) + [1.0 if j == i else 0.0 for j in range(m)] + [b[i]] for i in range(m)]
    z = [-x for x in c] + [0.0] * (m + 1)
    basis = [n + i for i in range(m)]
    geloest = False
    for _ in range(20 * (m + n) + 100):
        e = next((j for j in range(n + m) if z[j] < -1e-9), None)
        if e is None:
            geloest = True
            break
        r, best = None, None
        for i in range(m):
            if tab[i][e] > 1e-9:
                q = tab[i][-1] / tab[i][e]
                if best is None or q < best - 1e-12 or (abs(q - best) <= 1e-12 and basis[i] < basis[r]):
                    r, best = i, q
        if r is None:       # unbeschränkt: kommt bei Schnittmustern nicht vor (jeder Typ hat ein Muster)
            break
        p = tab[r][e]
        tab[r] = [x / p for x in tab[r]]
        for i in range(m):
            if i != r and abs(tab[i][e]) > 1e-12:
                f = tab[i][e]
                tab[i] = [x - f * y for x, y in zip(tab[i], tab[r])]
        f = z[e]
        z = [x - f * y for x, y in zip(z, tab[r])]
        basis[r] = e
    y = [0.0] * n
    for i, bi in enumerate(basis):
        if bi < n:
            y[bi] = tab[i][-1]
    return y, z[-1], z[n:n + m], geloest


def muster_optimierung(g):
    """Schnittmuster-Optimierung (Gilmore-Gomory). Das lineare Programm „möglichst wenige Stangen, jeder Typ
    mindestens so oft wie gebraucht“ wird über seine duale Form gelöst; neue Muster liefert bestes_muster mit den
    Schattenpreisen als Wert. Die abgerundete Lösung legt ganze Stangen fest, den Rest teilen Best-Fit, First-Fit
    und das beste Muster je Schritt auf. Ergebnis: (Stangen als Teilelisten, Schranke): die Schranke ist die
    aufgerundete LP-Lösung, wenn alle Suchen vollständig waren, sonst 0."""
    if not vertraeglich(g, g.teile):     # feste Naht auf Breit- und Schmalseite: Muster würden sie mischen
        return [], 0
    gruppen = {}
    for t in sortiert(g.teile):
        gruppen.setdefault(typ(t), []).append(t)
    keys = sorted(gruppen, key=lambda k: (-k[0], k))
    typen = [gruppen[k][0] for k in keys]
    bedarf = [len(gruppen[k]) for k in keys]
    n = len(typen)
    muster = []
    for i in range(n):              # Startmuster: je Typ so viele wie auf eine Stange passen
        k = 0
        while k < bedarf[i] and passt(g, [typen[i]] * (k + 1)):
            k += 1
        if k == 0:
            return [], 0            # passt nicht auf eine Stange (wird vorher aussortiert)
        muster.append(tuple(k if j == i else 0 for j in range(n)))
    vollstaendig = False
    for _ in range(MUSTER_MAX_RUNDEN):
        y, wert, x, geloest = simplex_max([float(d) for d in bedarf], [[float(v) for v in m] for m in muster],
                                          [1.0] * len(muster))
        if not geloest:
            break
        m, ganz = bestes_muster(g, typen, bedarf, [max(v, 0.0) for v in y])
        if m is None or sum(y[i] * m[i] for i in range(n)) <= 1 + 1e-7:
            vollstaendig = ganz
            break
        if tuple(m) in muster:
            break
        muster.append(tuple(m))
    # mit Gehrungen zum Ineinanderlegen keine Schranke: die Muster rechnen ohne Ineinanderlegen
    schranke = math.ceil(wert - 1e-6) if vollstaendig and geloest and not any(
        verschachtelbar(g, t) for t in g.teile) else 0
    # ganze Stangen aus der LP-Lösung, Rest heuristisch
    rest, vorrat, stangen = list(bedarf), {k: list(v) for k, v in gruppen.items()}, []
    for m, xp in sorted(zip(muster, x), key=lambda a: (-a[1], a[0])):
        for _ in range(int(math.floor(xp + 1e-9))):
            if any(rest[i] < m[i] for i in range(n)):
                break
            stangen.append([vorrat[keys[i]].pop() for i in range(n) for _ in range(m[i])])
            rest = [r - c for r, c in zip(rest, m)]
    uebrig = [t for k in keys for t in vorrat[k]]
    if uebrig:
        h = replace(g, teile=uebrig, bewiesen=False, schranke=0)
        stangen += min((aufloesen(h, best_fit(h, uebrig)), aufloesen(h, first_fit(h, uebrig)), muster_folge(h)),
                       key=len)
    return aufloesen(g, stangen), schranke


def muster_folge(g):
    """Schritt für Schritt das Muster mit der größten belegten Länge (lange Teile etwas bevorzugt) so oft wie
    möglich schneiden."""
    gruppen = {}
    for t in sortiert(g.teile):
        gruppen.setdefault(typ(t), []).append(t)
    keys = sorted(gruppen, key=lambda k: (-k[0], k))
    typen = [gruppen[k][0] for k in keys]
    bedarf = [len(gruppen[k]) for k in keys]
    wert = [t.laenge ** 1.2 for t in typen]
    stangen = []
    while sum(bedarf):
        m, _ = bestes_muster(g, typen, bedarf, wert)
        if not m or not sum(m):         # kommt nicht vor (jedes Teil passt allein auf eine Stange)
            stangen += [[t] for k in keys for t in gruppen[k]]
            break
        for _ in range(min(bedarf[i] // m[i] for i in range(len(m)) if m[i])):
            stangen.append([gruppen[keys[i]].pop() for i in range(len(m)) for _ in range(m[i])])
            bedarf = [b - c for b, c in zip(bedarf, m)]
    return aufloesen(g, stangen)


def manuell(g):
    """Einfache manuelle Einteilung: Eingabereihenfolge, keine Drehung, Stange voll, dann nächste."""
    stangen, aktuell = [], []
    for t in sorted(g.teile, key=lambda t: (t.zeile, t.nr)):
        if aktuell and verbrauch(g, [(x, False) for x in aktuell + [t]]) > g.nutzbar_bis + EPS:
            stangen.append(aktuell)
            aktuell = []
        aktuell.append(t)
    if aktuell:
        stangen.append(aktuell)
    return stangen


def ohne_drehung(g):
    """Stangen, wenn kein Teil gedreht werden dürfte (Vergleich für die Auswertung); None = in dieser Gruppe gibt es
    keine drehbaren Teile mit Gehrung."""
    if not any(verschachtelbar(g, t) and len(drehungen(g, t)) > 1 for t in g.teile):
        return None
    h = replace(g, teile=[replace(t, drehung=UNBEKANNT) if t.drehung == FREI else t for t in g.teile],
                bewiesen=False, schranke=0)
    return len(optimiere(h))


def untergrenze(g):
    nutz = g.nutzbar_bis - g.endbeschnitt
    return math.ceil(sum(mindestbedarf(g, t) for t in g.teile) / nutz - EPS) if g.teile else 0


# ------------------------------------------------------------------ Zuschnitt langer Lieferstangen
# Eine Lieferstange, die länger ist als die Maschine laden kann (z. B. 12.000 mm bei 6.500 mm), wird vom Lieferanten
# in Werkstücke geschnitten, die einzeln geladen werden. Werkstück = Endbeschnitt + Teile + Trennungen + letzter
# Schnittverlust + Greiferrest, auf ganze mm aufgerundet, höchstens die max. Stangenlänge der Maschine. Zwischen zwei
# Werkstücken geht der Schnittverlust des Zuschnitts verloren, der Rest der Lieferstange ist Verschnitt.
ZUSCHNITT_TEILUNG = 6    # Ziel-Werkstücklängen: Lieferlänge geteilt durch 1 … 6 (Schritte, keine Zeit)


def werkstueck_laenge(g, folge):
    """Länge des Werkstücks für eine Folge (ganze mm)."""
    return math.ceil(verbrauch(g, folge) + g.greiferrest - EPS)


def zuschnitt_belegt(laengen, saege):
    """Belegte Länge einer Lieferstange: Werkstücke + Zuschnitte dazwischen."""
    return sum(laengen) + saege * max(len(laengen) - 1, 0)


def zuschnitt_ziele(g, lieferlaenge, max_werkstueck, saege, min_werkstueck=0, puffer=0):
    """Ziel-Werkstücklängen, die ausprobiert werden: die max. Werkstücklänge und die Lieferlänge geteilt durch 2 … n
    (abzüglich der Zuschnitte), soweit das längste Teil hineinpasst und die Mindestlänge erreicht ist. Längste
    zuerst."""
    noetig = max(g.endbeschnitt + max(t.laenge for t in g.teile) + g.kerf + g.greiferrest + puffer, min_werkstueck or 0)
    ziele = {int(min(max_werkstueck, math.floor((lieferlaenge - (n - 1) * saege) / n + EPS)))
             for n in range(1, ZUSCHNITT_TEILUNG + 1)}
    return sorted((z for z in ziele if z + EPS >= noetig), reverse=True)


def zuschnitt(g, lieferlaenge, max_werkstueck, saege, min_werkstueck=0, puffer=0):
    """Zweistufige Planung: Teile zu Werkstücken (Optimierung wie bei normalen Stangen, Stangenlänge = Ziel-
    Werkstücklänge), dann die Werkstücke auf Lieferstangen verteilen (dieselbe Optimierung: Werkstücke als Teile mit
    geraden Enden, Schnittverlust = Zuschnitt, ohne Endbeschnitt und Greiferrest). Je Ziel-Werkstücklänge eine
    Planung, es gilt die mit den wenigsten Lieferstangen, dann den wenigsten Werkstücken (Beladungen), dann den
    meisten gemeinsamen Schnitten. Die Restlänge der Lieferstange kommt an das kürzeste Werkstück, wenn es dadurch
    nicht zu lang wird (restlaenge_anhaengen). Jedes Werkstück bekommt den Puffer (Einstellung) dazu, damit nicht
    auf den Millimeter genau zugeschnitten wird. Ein Werkstück (zugeschnittene Stange) ist mindestens min_werkstueck lang
    (Min. Stangenlänge der automatischen Stangenladung), ein kürzeres wird bis dahin verlängert, der Mehrbedarf ist Verschnitt.
    Ergebnis: Liste der Lieferstangen, je Lieferstange [(Werkstücklänge, Folge)]; None, wenn ein Teil in kein
    Werkstück passt."""
    if not g.teile:
        return []
    beste = None
    mindest = math.ceil((min_werkstueck or 0) - EPS)
    puffer = math.ceil((puffer or 0) - EPS)
    for ziel in zuschnitt_ziele(g, lieferlaenge, max_werkstueck, saege, mindest, puffer):
        h = replace(g, stange=ziel - puffer, teile=list(g.teile))
        folgen = optimiere(h)
        laengen = [max(werkstueck_laenge(g, f) + puffer, mindest) for f in folgen]
        # Stange um einen Zuschnitt länger: verbrauch() zählt nach dem letzten Werkstück noch einen Schnitt
        p = Gruppe(g.profil, g.werkstoff, lieferlaenge + saege, 0, 0, saege, 0, g.oberflaeche)
        p.teile = [Teil(i, None, "", 1, float(l), True, True, 0, 0) for i, l in enumerate(laengen)]
        if any(l > lieferlaenge + EPS for l in laengen):
            continue
        verteilt = optimiere(p)
        stangen = [[(laengen[t.zeile], folgen[t.zeile]) for t, _ in sorted(f, key=lambda x: (-x[0].laenge,
                                                                                            x[0].zeile))]
                   for f in verteilt]
        wert = (len(stangen), len(folgen), -sum(gemeinsame_schnitte(f) for f in folgen), -ziel)
        if beste is None or wert < beste[0]:
            beste = (wert, stangen)
    return restlaenge_anhaengen(beste[1], lieferlaenge, max_werkstueck, saege) if beste else None


def restlaenge_anhaengen(stangen, lieferlaenge, max_werkstueck, saege):
    """Restlänge der Lieferstange an das kürzeste Werkstück hängen, solange es dadurch nicht länger als die max.
    Werkstücklänge wird: spart den letzten Sägeschnitt (Patrick 21.10.2026: 2 × 4.200 + Restlänge statt
    2 × 4.200 + 3.100 + Abfall). Passt der Rest nicht dran, bleibt er Abfall (keine Stange)."""
    out = []
    for s in stangen:
        rest = lieferlaenge - zuschnitt_belegt([l for l, _ in s], saege)
        if s and rest > EPS:
            l, f = s[-1]
            neu = math.floor(l + rest + EPS)
            if neu <= max_werkstueck + EPS:
                s = s[:-1] + [(neu, f)]
        out.append(s)
    return out


def pruefe_zuschnitt(g, stangen, lieferlaenge, max_werkstueck, saege, min_werkstueck=0):
    """Unabhängige Kontrolle des Zuschnitts: jedes Teil genau einmal, kein Werkstück über der max.
    Werkstücklänge, unter der Mindestlänge oder kürzer als seine Belegung + Greiferrest, keine Lieferstange
    überbelegt."""
    ids = sorted((t.zeile, t.nr) for s in stangen for _, f in s for t, _ in f)
    if ids != sorted((t.zeile, t.nr) for t in g.teile):
        raise AssertionError(f"{g.profil}: Teile fehlen oder doppelt (Zuschnitt)")
    for s in stangen:
        for laenge, f in s:
            if laenge > max_werkstueck + EPS:
                raise AssertionError(f"{g.profil}: Werkstück {laenge:g} mm länger als die Maschine laden kann")
            if min_werkstueck and laenge + EPS < min_werkstueck:
                raise AssertionError(f"{g.profil}: Werkstück {laenge:g} mm kürzer als die Min. Stangenlänge")
            if verbrauch(g, f) + g.greiferrest > laenge + EPS:
                raise AssertionError(f"{g.profil}: Werkstück überbelegt")
        if zuschnitt_belegt([l for l, _ in s], saege) > lieferlaenge + EPS:
            raise AssertionError(f"{g.profil}: Lieferstange überbelegt")


# ------------------------------------------------------------------ Profile
OFFEN = ("U-Profil", "C-Profil", "L-Profil", "Flachstahl", "I-/H-Träger", "T-Profil")


def umfang(form, a, b, wand=None, flaeche=None):
    """Umfang des Querschnitts (Außenfläche je m Länge). Offene Profile: beide Seiten, aus Querschnittsfläche und
    Blechdicke (dünnwandig: 2 × Fläche / Dicke + 2 × Dicke an den Kanten), damit gilt es auch für C-Profile mit
    Abkantung und Profile mit Radien."""
    if form == "Rundrohr":
        return math.pi * a
    if form == "Quadratrohr":
        return 4 * a
    if form == "Rechteckrohr":
        return 2 * (a + (b or a))
    if form == "I-/H-Träger" and b:       # scharfkantig: Flansche außen und innen, Flanschkanten, Steg
        return 2 * a + 4 * b - 2 * (wand or 0)
    if form == "T-Profil" and b:
        return 2 * a + 2 * b
    if form in OFFEN and wand and flaeche:
        return 2 * flaeche / wand + 2 * wand
    return 0.0


def schnittlaenge(form, a, b, wand=None, flaeche=None):
    """Länge eines geraden Trennschnitts: Rohre = Außenumfang, offene Profile = halber Umfang (der Laser schneidet
    jede Wand nur einmal)."""
    u = umfang(form, a, b, wand, flaeche)
    return u / 2 if form in OFFEN else u


PROFILFORM = {"RR": "Rundrohr", "QR": "Quadratrohr", "RE": "Rechteckrohr", "U": "U-Profil", "C": "C-Profil",
              "L": "L-Profil", "FL": "Flachstahl", "I": "I-/H-Träger", "T": "T-Profil"}


def profil_aus_name(pid):
    """Profilform und Maße aus der Profil-ID, z. B. 'RR 42,4x2,0', 'QR 40x40x3', 'RE 60x40x3'.
    Ergebnis dict(form, a, b, wand) oder None, wenn der Name nicht nach dem Schema aufgebaut ist.
    """
    n = normprofile.daten(pid)
    if n is not None and n["flaeche"]:       # Normprofil, z. B. 'IPE 200', 'HEB 160', 'UPN 100', 'T 50'
        return dict(form=n["form"], a=n["h"], b=n["b"], wand=n["tw"], flaeche_manuell=n["flaeche"])
    kurz, _, rest = str(pid).strip().partition(" ")
    form = PROFILFORM.get(kurz.upper())
    zahlen = rest.replace(",", ".").replace("X", "x").split("x")
    try:
        z = [float(v) for v in zahlen]
    except ValueError:
        return None
    if form == "Rundrohr" and len(z) == 2:
        a, b, wand = z[0], None, z[1]
    elif form == "Quadratrohr" and len(z) == 3 and z[0] == z[1]:
        a, b, wand = z[0], None, z[2]
    elif form in ("Rechteckrohr", "U-Profil", "C-Profil", "L-Profil") and len(z) == 3:
        a, b, wand = z[0], z[1], z[2]
    elif form in ("I-/H-Träger", "T-Profil") and len(z) == 4:     # 'I h x b x Steg x Flansch'
        h, b, tw, tf = z
        if min(z) <= 0 or tw >= b or (2 if form == "I-/H-Träger" else 1) * tf >= h:
            return None
        fl = 2 * b * tf + (h - 2 * tf) * tw if form == "I-/H-Träger" else b * tf + (h - tf) * tw
        return dict(form=form, a=h, b=b, wand=tw, flaeche_manuell=round(fl, 1))
    elif form == "Flachstahl" and len(z) == 2:
        a, b, wand = z[0], None, z[1]
        return dict(form=form, a=a, b=b, wand=wand) if 0 < wand < a else None
    else:
        return None
    if a <= 0 or wand <= 0 or 2 * wand >= a:
        return None
    return dict(form=form, a=a, b=b, wand=wand)


def pruefe(gruppen, ergebnisse):
    """Unabhängige Kontrolle: keine Stange überbelegt, jedes Teil genau einmal eingeplant."""
    for g, folgen in zip(gruppen, ergebnisse):
        ids = sorted((t.zeile, t.nr) for f in folgen for t, _ in f)
        soll = sorted((t.zeile, t.nr) for t in g.teile)
        if ids != soll:
            raise AssertionError(f"{g.profil}: Teile fehlen oder doppelt")
        for f in folgen:
            if verbrauch(g, f) > g.nutzbar_bis + EPS:
                raise AssertionError(f"{g.profil}: Stange überbelegt")
            pruefe_drehungen(g, f)


def pruefe_drehungen(g, folge):
    """Unabhängige Kontrolle der Lage: jede Drehung zulässig (nie gewendet, Teile ohne Freigabe nur wie die Naht
    der Stange es verlangt) und an jeder Stelle mindestens 2 Schnitte bzw. ein gemeinsamer Schnitt, ineinander-
    gelegte Gehrungen nie enger als der Abstand."""
    lagen = [s for s in naht_lagen(g, [t for t, _ in folge])]
    if not lagen:
        raise AssertionError(f"{g.profil}: feste Naht auf Breit- und Schmalseite auf einer Stange")
    if not any(all(r in drehungen(g, t, s) for t, r in folge) for s in lagen):
        raise AssertionError(f"{g.profil}: unzulässige Drehung um die Längsachse")
    for (t1, r1), (t2, r2) in zip(folge, folge[1:]):
        if t1.b_gehrung is not None and t2.a_gehrung is not None and g.querschnitt and \
                not (t1.b_gerade and t2.a_gerade) and ineinander(g, t1, r1, t2, r2):
            if gehrung_trennung(g, t1.b_gehrung, r1, t2.a_gehrung, r2) < trennung_teile(g, t1, r1, t2, r2) - EPS:
                raise AssertionError(f"{g.profil}: Gehrungen enger als der Abstand")
