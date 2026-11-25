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
- 3D-Greifmaß (Patrick 22.10.2026): hinter dem letzten Teil einer Stange bleibt der Greiferrest frei, bei einem Teil
  mit 3D-Bearbeitung nahe Ende B dessen Forderung Teil.rest (dreid.rest_letztes), wenn sie größer ist – das Maximum,
  nie die Summe (hinten, belegt). anordnen legt dafür nach Möglichkeit ein Teil ohne diese Forderung ans Ende.
- Teil am Stangenende (Adige „Abfallvorstellung“, Plan ArTube-Unterlagen A1, Patrick 12.11.2026): kann die Maschine es
  (Gruppe.ende_bonus > 0), darf das letzte Teil einer Stange in den Greiferrest, wenn sein Ende B gerade ist und im
  Spannbereich (= Greiferrest) keine Kontur liegt (Teil.ende_frei). Die Maschine trennt den Abfall vor dem letzten Teil
  ab; hinter dem Teil bleibt dann statt des Greiferrests nur der Mindestabfall frei (hinten). Gerechnet wird zur
  sicheren Seite: die Trennung vor dem letzten Teil bleibt, der Mindestabfall kommt dazu.
- Keine Restlagerverwaltung: Reste sind Verschnitt.

Verfahren: First-Fit- und Best-Fit-Decreasing mit Auflösen schwach belegter Stangen; ist das nicht nachweislich
optimal, rechnet die Schnittmuster-Optimierung (Spaltengenerierung nach Gilmore-Gomory: gleiche Teile als Typ,
Schnittmuster je Stange, lineares Programm über die Muster) eine Einteilung und eine Schranke; danach für kleine
Gruppen die exakte Suche. Alle Grenzen sind Schrittzahlen, keine Zeiten: das Ergebnis ist auf jedem Rechner gleich.
Mit Gehrungen, die sich ineinanderlegen lassen, gilt die Schranke der Schnittmuster nicht (die Muster rechnen ohne
Ineinanderlegen); die Untergrenze zieht dann je Teil die größtmögliche Überlappung ab.
"""
import bisect
import collections
import hashlib
import itertools
import math
import threading
from dataclasses import dataclass, field, replace

from . import normprofile, ovalprofile, rp_profile

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
    rest: float = 0.0       # Rest hinter dem Teil, wenn es das letzte der Stange ist (3D-Greifmaß; 0 = Greiferrest)
    angenommen: bool = False  # Richtung einer Gehrung angenommen (im Schneidweg-Rechner nicht angegeben)
    ende_frei: bool = False   # darf als letztes Teil in den Greiferrest (Teil am Stangenende, Gruppe.ende_bonus)
    ganz: bool = False        # ganze Lieferstange ohne Trennschnitt (Plan ArTube-Unterlagen A3, eigene Gruppe)
    # Universelle Endkonturen (endkontur.py, Patrick 25.11.2026): Schlüssel des sicheren Verlaufs d(s) je Ende im
    # Register von endkontur (V, U, S, Bogen, Stufen, Freiform, STEP-Umriss, Gegenrohr …) oder None
    a_kontur: str = None
    b_kontur: str = None


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
    muster: bool = False     # Musterteile: eigener Fertigungslauf, nie mit Serienteilen auf einer Stange
    # Querschnitt für das Ineinanderlegen von Gehrungen: ('Kasten', Breite, Höhe) mit der Breitseite oben,
    # ('Rund', Radius) oder () = keine Gehrungen ineinanderlegen
    querschnitt: tuple = ()
    # Teil am Stangenende: so viel weniger bleibt hinter einem letzten Teil mit ende_frei frei (Greiferrest minus
    # Mindestabfall); 0 = Maschine kann es nicht oder kein Teil der Gruppe darf ans Stangenende
    ende_bonus: float = 0.0
    # Maschine der Gruppe, wenn ihre Positionen eine andere Maschine als der Angebotskopf haben (MACH-006); leer = Kopf
    maschine: str = ""
    # Universelle Konturverschachtelung (endkontur.py): Schlüssel der Querschnitts-Geometrie, leer = aus; zugabe =
    # Sicherheitsabstand (Material- und Fertigungstoleranz) zusätzlich zu 2 × Schnittverlust + Abstand
    kontur_geo: str = ""
    kontur_zugabe: float = 0.0

    @property
    def nutzbar_bis(self):
        return self.stange - self.greiferrest

    @property
    def luft(self):
        """Obergrenze der Belegung für Vorprüfungen und Schranken: nutzbar_bis + ende_bonus (die eigentliche Prüfung
        ist belegt <= nutzbar_bis)."""
        return self.nutzbar_bis + self.ende_bonus


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
    k = (g.querschnitt, geh)
    if k not in _TIEFE:
        x, y = _richtung(geh[1])
        _TIEFE[k] = math.tan(math.radians(geh[0])) * _stuetz(g, x, y)
    return _TIEFE[k]


_TIEFE = {}


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
    return bool(g.querschnitt) and (t.a_gehrung is not None or t.b_gehrung is not None) or \
        bool(g.kontur_geo) and (t.a_kontur is not None or t.b_kontur is not None)


def _nestbar(g):
    """Ist in der Gruppe Ineinanderlegen überhaupt möglich (Gehrungen mit Querschnitt bzw. Endkonturen)?"""
    return bool(g.querschnitt or g.kontur_geo)


def kontur_abstand(g):
    """Geforderter Abstand der Schnittkanten im Raum beim Verschachteln von Endkonturen [mm]."""
    return 2 * g.kerf + g.abstand + g.kontur_zugabe


def kontur_trennung(g, t1, r1, t2, r2):
    """Verbrauch zwischen zwei Enden über ihre Verläufe (endkontur.trennung) oder None (nicht möglich)."""
    if not (g.kontur_geo and t1.b_kontur and t2.a_kontur):
        return None
    from . import endkontur
    return endkontur.trennung(g.kontur_geo, kontur_abstand(g), t1.b_kontur, r1, t2.a_kontur, r2)


# ------------------------------------------------------------------ Belegung einer Stange
def trennung(kerf, abstand, ende_gerade, anfang_gerade):
    """Materialverbrauch zwischen zwei Teilen."""
    return kerf if (ende_gerade and anfang_gerade) else 2 * kerf + abstand


def trennung_teile(g, t1, r1, t2, r2):
    """Materialverbrauch zwischen Teil t1 (Drehung r1) und dem folgenden t2 (Drehung r2): gemeinsamer Schnitt bei
    zwei geraden Enden, sonst 2 Schnitte oder – kürzer – Gehrungen ineinandergelegt."""
    normal = trennung(g.kerf, g.abstand, t1.b_gerade, t2.a_gerade)
    if t1.b_gerade and t2.a_gerade:
        return normal
    if t1.b_gehrung is None or t2.a_gehrung is None or not g.querschnitt:
        if not g.kontur_geo:
            return normal
        # beliebige Endkonturen (endkontur.py): Verlauf gegen Verlauf, nie kürzer als der Abstand im Raum erlaubt
        schluessel = ("K", t1.b_kontur, t2.a_kontur, r1 % 360, r2 % 360)
        speicher = _speicher(g)
        if schluessel not in speicher:
            x = kontur_trennung(g, t1, r1, t2, r2)
            speicher[schluessel] = normal if x is None else min(normal, x)
        return speicher[schluessel]
    # Kasten: gleich bei Drehung um den Rasterschritt (180° bzw. 90°), Rund: nur die Drehung zueinander zählt
    schluessel = (t1.b_gehrung, t2.a_gehrung, r1 % raster(g) if g.querschnitt[0] == "Kasten" else 0, (r2 - r1) % 360)
    speicher = _speicher(g)
    if schluessel not in speicher:
        speicher[schluessel] = min(normal, gehrung_trennung(g, t1.b_gehrung, r1, t2.a_gehrung, r2))
    return speicher[schluessel]


_SPEICHER = {}


def _speicher(g):
    """Zwischenspeicher der Gehrungs-Trennungen je Querschnitt, Schnittverlust und Abstand."""
    return _SPEICHER.setdefault((g.querschnitt, g.kerf, g.abstand) + ((g.kontur_geo, g.kontur_zugabe)
                                                                     if g.kontur_geo else ()), {})


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
    if g is None or not _nestbar(g) or sum(verschachtelbar(g, t) for t in teile) < 2 and not any(
            t.drehung == FEST for t in teile):
        folge = [(t, 0) for t in gerade]
        return _ende_3d(g, folge) if g is not None and _ende_suchen(g, teile) else folge
    # Das Ergebnis hängt nur von den Enden, der Drehfreigabe und der Naht der Teile (in dieser Reihenfolge) ab, nicht
    # von Länge oder Position: einmal gerechnet gilt es für alle gleichen Folgen (gleiches Ergebnis, viel schneller;
    # die Packverfahren prüfen dieselben Zusammenstellungen sehr oft)
    teile = list(teile)
    schluessel = (g.querschnitt, g.kerf, g.abstand, g.greiferrest, g.ende_bonus, tuple(_enden(t) for t in teile)) + \
        ((g.kontur_geo, g.kontur_zugabe) if g.kontur_geo else ()) + (("P",) if praezision_an() else ())
    speicher = _ANORDNUNG.get(schluessel)
    if speicher is None:
        if len(_ANORDNUNG) > ANORDNUNG_MAX:
            _ANORDNUNG.clear()
        # Index je Platz, nicht je Objekt: die Schnittmuster prüfen dasselbe Teil mehrfach ([Typ] * k); mit nur einem
        # Index je Objekt stünde ein Index doppelt im Speicher, und jede spätere gleiche Folge bekäme ein Teil doppelt
        # und eines gar nicht (Kontrolle „Teile fehlen oder doppelt“ bei fester Naht, 29.10.2026)
        nr = {}
        for i, t in enumerate(teile):
            nr.setdefault(id(t), []).append(i)
        folge = _anordnen_gehrung(g, teile, gerade)
        if _ende_suchen(g, teile):
            folge = _ende_3d(g, folge)
        speicher = _ANORDNUNG[schluessel] = tuple((nr[id(t)].pop(0), r) for t, r in folge)
    return [(teile[i], r) for i, r in speicher]


_ANORDNUNG = {}
ANORDNUNG_MAX = 200000      # Einträge im Zwischenspeicher von anordnen, danach wird er geleert


def _enden(t):
    if t.a_kontur or t.b_kontur:
        return t.a_gerade, t.b_gerade, t.a_gehrung, t.b_gehrung, t.drehung, t.naht, t.rest, t.ende_frei, \
            t.a_kontur, t.b_kontur
    return t.a_gerade, t.b_gerade, t.a_gehrung, t.b_gehrung, t.drehung, t.naht, t.rest, t.ende_frei


def _anordnen_gehrung(g, teile, gerade):
    beste = None
    for naht_stange in naht_lagen(g, teile) or [0]:
        for folge in (gerade, _kette_gehrung(g, list(teile), naht_stange)):
            summe, wahl = _drehungen_waehlen(g, folge, naht_stange)
            if beste is None or summe < beste[0] - EPS:
                beste = (summe, list(zip(folge, wahl)), naht_stange)
    if praezision_an() and 2 < len(teile) <= PRAEZ_MAX_TEILE:
        summe, folge = _lokal_suchen(g, [t for t, _ in beste[1]], beste[2])
        if summe < beste[0] - EPS:
            _, wahl = _drehungen_waehlen(g, folge, beste[2])
            beste = (summe, list(zip(folge, wahl)), beste[2])
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


def hinten(g, folge):
    """Freie Länge hinter dem letzten Teil: Greiferrest, bei einem letzten Teil mit 3D-Greifmaß dessen Forderung,
    wenn sie größer ist (Maximum, nie Summe); bei Teil am Stangenende (am_stangenende) nur der Mindestabfall."""
    if am_stangenende(g, folge):
        return g.greiferrest - g.ende_bonus
    return max(g.greiferrest, folge[-1][0].rest) if folge else g.greiferrest


def am_stangenende(g, folge):
    """True, wenn das letzte Teil der Folge in den Greiferrest darf (Teil am Stangenende)."""
    return bool(folge) and g.ende_bonus > EPS and folge[-1][0].ende_frei and folge[-1][0].rest <= g.greiferrest + EPS


def _ende_suchen(g, teile):
    """Lohnt es, ein anderes Teil ans Ende der Stange zu legen? (3D-Greifmaß oder Teil am Stangenende)"""
    return _mit_3d(g, teile) or (g.ende_bonus > EPS and any(t.ende_frei for t in teile))


def belegt(g, folge):
    """Verbrauch + Mehrbedarf hinter dem letzten Teil über den Greiferrest hinaus; zulässig bis g.nutzbar_bis."""
    return verbrauch(g, folge) + hinten(g, folge) - g.greiferrest


def _mit_3d(g, teile):
    return any(t.rest > g.greiferrest + EPS for t in teile)


def _drehen(g, teile):
    """Beste Drehungen für eine feste Reihenfolge (wie _anordnen_gehrung, ohne die Reihenfolge zu ändern)."""
    if not _nestbar(g) or sum(verschachtelbar(g, t) for t in teile) < 2 and not any(
            t.drehung == FEST for t in teile):
        return [(t, 0) for t in teile]
    beste = None
    for naht_stange in naht_lagen(g, teile) or [0]:
        summe, wahl = _drehungen_waehlen(g, teile, naht_stange)
        if beste is None or summe < beste[0] - EPS:
            beste = (summe, list(zip(teile, wahl)))
    return beste[1]


def _ende_3d(g, folge):
    """Liegt ein Teil mit 3D-Greifmaß am Ende, jedes andersartige Teil mit kleinerer Forderung ans Ende probieren
    (übrige Reihenfolge bleibt); es gilt die Folge mit der kleinsten Belegung. Ebenso, wenn ein Teil am Stangenende
    in den Greiferrest dürfte und das letzte Teil es nicht darf (Teil am Stangenende)."""
    if not folge:
        return folge
    ende = g.ende_bonus > EPS and not am_stangenende(g, folge)
    if folge[-1][0].rest <= g.greiferrest + EPS and not ende:
        return folge
    beste, wert, gesehen = folge, belegt(g, folge), set()
    for i, (t, _) in enumerate(folge[:-1]):
        if (_enden(t), t.laenge) in gesehen or (t.rest >= folge[-1][0].rest - EPS and not (ende and t.ende_frei)):
            continue
        gesehen.add((_enden(t), t.laenge))
        neu = _drehen(g, [x for j, (x, _) in enumerate(folge) if j != i] + [t])
        w = belegt(g, neu)
        if w < wert - EPS:
            beste, wert = neu, w
    return beste


def vertraeglich(g, teile):
    """Dürfen die Teile auf dieselbe Stange? Rechteckrohr: feste Naht nicht zugleich auf Breit- und Schmalseite."""
    return bool(naht_lagen(g, teile))


def passt(g, teile):
    # Verbrauch = Endbeschnitt + Teile + Trennungen der Anordnung + letzter Schnitt; die Trennungen hängen nur von den
    # Enden ab und werden je Folge von Enden einmal gerechnet (gleiches Ergebnis wie verbrauch(anordnen), schneller)
    laenge = g.endbeschnitt + sum(t.laenge for t in teile) + (g.kerf if teile else 0)
    # jede Trennung ist mindestens ein Schnittverlust abzüglich der größtmöglichen Überlappung der Gehrungen
    # (mindestbedarf): passt es selbst so nicht, muss nicht angeordnet werden
    ueber = sum(gehrung_tiefe(g, t.a_gehrung) + gehrung_tiefe(g, t.b_gehrung) for t in teile
                if t.a_gehrung or t.b_gehrung) if g.querschnitt else 0.0
    if g.kontur_geo:
        ueber = sum(_tiefe(g, t, "a") + _tiefe(g, t, "b") for t in teile)
    if laenge + (len(teile) - 1) * g.kerf - ueber > g.luft + EPS:
        return False
    if not vertraeglich(g, teile):
        return False
    if not _nestbar(g):
        return belegt(g, anordnen(teile, g)) <= g.nutzbar_bis + EPS
    schluessel = (g.querschnitt, g.kerf, g.abstand, g.greiferrest, g.ende_bonus, tuple(_enden(t) for t in teile)) + \
        ((g.kontur_geo, g.kontur_zugabe) if g.kontur_geo else ()) + (("P",) if praezision_an() else ())
    summe = _TRENNSUMME.get(schluessel)
    if summe is None:
        if len(_TRENNSUMME) > ANORDNUNG_MAX:
            _TRENNSUMME.clear()
        folge = anordnen(teile, g)
        summe = _TRENNSUMME[schluessel] = belegt(g, folge) - laenge
    return laenge + summe <= g.nutzbar_bis + EPS


_TRENNSUMME = {}


def mindestbedarf(g, t):
    """Kleinstmöglicher Längenbedarf eines Teils auf der Stange (Länge + Schnittverlust − größtmögliche Überlappung
    beider Gehrungen); Grundlage der Untergrenzen."""
    if g.kontur_geo:
        return t.laenge + g.kerf - _tiefe(g, t, "a") - _tiefe(g, t, "b")
    return t.laenge + g.kerf - gehrung_tiefe(g, t.a_gehrung) - gehrung_tiefe(g, t.b_gehrung)


def _tiefe(g, t, seite):
    """Größtmögliche Überlappung eines Endes: Gehrung (eben) bzw. Verlauf der Endkontur, das größere (sicher)."""
    geh = gehrung_tiefe(g, t.a_gehrung if seite == "a" else t.b_gehrung)
    k = t.a_kontur if seite == "a" else t.b_kontur
    if not k:
        return geh
    from . import endkontur
    return max(geh, endkontur.profil_tiefe(k))


# ------------------------------------------------------------------ Packverfahren
def sortiert(teile):
    return sorted(teile, key=lambda t: (-t.laenge, t.zeile, t.nr))


# Volle Stangen überspringen (Fehler-Durchgang 01.11.2026): First-Fit, Best-Fit und Auflösen prüften jedes Teil gegen
# jede Stange, auch gegen längst volle – bei 8.000 gleichen Teilen 100 s, bei 20.000 über 10 Minuten. Eine Stange gilt
# als voll, wenn nicht einmal das kleinste noch einzuplanende Teil ihre Untergrenze (Endbeschnitt + Mindestbedarf aller
# Teile, dieselbe Schranke wie in passt) unter nutzbar_bis lässt; solche Stangen nähmen ohnehin kein Teil mehr. Das
# Ergebnis bleibt Stange für Stange gleich (Test test_optimierung_gross), nur ohne die vergeblichen Prüfungen.
VOLL_MARGE = 1e-4       # Sicherheitsabstand [mm] zur Rundung, damit nie eine Stange zu früh als voll gilt


def _grenze(g):
    return g.luft + EPS + VOLL_MARGE


def _grund(g, teile, mb=None):
    """Untergrenze der Belegung: Endbeschnitt + Mindestbedarf der Teile (wie die Vorprüfung in passt)."""
    return g.endbeschnitt + sum((mb or (lambda t: mindestbedarf(g, t)))(t) for t in teile)


def _bedarf(g):
    """mindestbedarf mit Zwischenspeicher je Teil (gleiche Teile kommen tausendfach vor)."""
    speicher = {}

    def mb(t):
        k = id(t)
        if k not in speicher:
            speicher[k] = mindestbedarf(g, t)
        return speicher[k]
    return mb


def _kleinste_danach(teile, mb):
    """Je Platz in teile der kleinste Mindestbedarf dieses und aller folgenden Teile."""
    out, m = [0.0] * len(teile), math.inf
    for i in range(len(teile) - 1, -1, -1):
        m = min(m, mb(teile[i]))
        out[i] = m
    return out


def first_fit(g, teile):
    stangen, grund, offen = [], [], []      # offen: Nummern der Stangen, die noch ein Teil aufnehmen könnten
    folge, mb = sortiert(teile), _bedarf(g)
    kleinst, grenze = _kleinste_danach(folge, mb), _grenze(g)
    art, ab = None, 0       # gleiches Teil wie zuvor: die Stangen davor haben es schon abgelehnt (unverändert)
    for i, t in enumerate(folge):
        if offen and any(grund[j] + kleinst[i] > grenze for j in offen):
            offen = [j for j in offen if grund[j] + kleinst[i] <= grenze]
        bedarf = mb(t)
        if (_enden(t), t.laenge) != art:
            art, ab = (_enden(t), t.laenge), 0
        for j in offen:
            if j >= ab and grund[j] + bedarf <= grenze and passt(g, stangen[j] + [t]):
                stangen[j].append(t)
                grund[j] += bedarf
                ab = j
                break
        else:
            stangen.append([t])
            grund.append(g.endbeschnitt + bedarf)
            offen.append(len(stangen) - 1)
            ab = len(stangen) - 1
    return stangen


def best_fit(g, teile):
    stangen, grund, offen = [], [], []
    folge, mb = sortiert(teile), _bedarf(g)
    kleinst, grenze = _kleinste_danach(folge, mb), _grenze(g)
    art, merk = None, {}    # Belegung je Stange für die aktuelle Teileart (gilt, solange die Stange unverändert ist)
    for i, t in enumerate(folge):
        if offen and any(grund[j] + kleinst[i] > grenze for j in offen):
            offen = [j for j in offen if grund[j] + kleinst[i] <= grenze]
        bedarf = mb(t)
        if (_enden(t), t.laenge) != art:
            art, merk = (_enden(t), t.laenge), {}
        beste, rest_min = None, None
        for j in offen:
            if j not in merk:
                s = stangen[j]
                merk[j] = None if grund[j] + bedarf > grenze or not vertraeglich(g, s + [t]) else \
                    belegt(g, anordnen(s + [t], g))
            v = merk[j]
            if v is None:
                continue
            if v <= g.nutzbar_bis + EPS and (rest_min is None or g.nutzbar_bis - v < rest_min):
                beste, rest_min = j, g.nutzbar_bis - v
        if beste is None:
            stangen.append([t])
            grund.append(g.endbeschnitt + bedarf)
            offen.append(len(stangen) - 1)
        else:
            stangen[beste].append(t)
            grund[beste] += bedarf
            merk.pop(beste, None)
    return stangen


AUFLOESEN_MERKEN = True    # Ablehnungen/Belegungen in aufloesen merken (False nur für den Vergleich im Test)


def aufloesen(g, stangen):
    """Schwach belegte Stangen auflösen, wenn alle ihre Teile in andere Stangen passen."""
    stangen = [list(s) for s in stangen]
    belegt_ = {}        # Belegung je Zusammenstellung (wird sonst je Teil für jede Stange neu gerechnet)
    grenze, mb = _grenze(g), _bedarf(g)

    def vb(x):
        k = tuple(id(t) for t in x)
        if k not in belegt_:
            belegt_[k] = belegt(g, anordnen(x, g))
        return belegt_[k]
    geaendert = True
    while geaendert and len(stangen) > 1:
        geaendert = False
        # Vorprüfung: die Teile einer Stange brauchen mindestens ihren Mindestbedarf an freier Länge in den anderen
        # Stangen (Untergrenze wie in passt); reicht die freie Länge aller anderen zusammen nicht, kann sie nicht
        # aufgelöst werden – ohne jedes Teil einzeln zu probieren (gleiches Ergebnis). Gezählt werden nur Stangen, in
        # die wenigstens das kleinste ihrer Teile noch passen könnte.
        grund = {id(s): _grund(g, s, mb) for s in stangen}
        frei = {k: max(0.0, grenze - v) for k, v in grund.items()}
        werte = sorted(frei.values())
        summen = list(itertools.accumulate(reversed(werte)))[::-1] + [0.0]     # summen[i] = sum(werte[i:])
        for s in sorted(stangen, key=lambda s: sum(t.laenge for t in s)):
            kleinst = min(mb(t) for t in s)
            i = bisect.bisect_left(werte, kleinst - VOLL_MARGE)
            verfuegbar = summen[i] - (frei[id(s)] if frei[id(s)] >= kleinst - VOLL_MARGE else 0.0)
            if sum(mb(t) for t in s) > verfuegbar + VOLL_MARGE:
                continue
            andere = [list(x) for x in stangen if x is not s]
            g_andere = {id(neu): grund[id(x)] for neu, x in zip(andere, (x for x in stangen if x is not s))}
            # Gesamtprüfung 25.11.2026 (10.000 gleiche Teile mit schrägem Ende: 119 s): passt hängt nur von der
            # Stange und den Enden + der Länge des neuen Teils ab. Hat eine unveränderte Stange ein Teil dieser Art
            # schon abgelehnt, lehnt sie jedes weitere gleiche ab – nicht noch einmal prüfen. Ebenso die Belegung
            # einer unveränderten Stange für die Sortierung nur einmal rechnen. Die Stangen in andere wachsen nur
            # durch append und leben bis zum Ende dieses Durchgangs: (id, Länge) kennzeichnet ihren Inhalt eindeutig.
            # Gleiches Ergebnis, nur ohne die vergeblichen Prüfungen.
            abgelehnt, vb_stand = set(), {}

            def vb_jetzt(x):
                if not AUFLOESEN_MERKEN:
                    return vb(x)
                st = vb_stand.get(id(x))
                if st is None or st[0] != len(x):
                    st = vb_stand[id(x)] = (len(x), vb(x))
                return st[1]
            ok = True
            for t in sortiert(s):
                ziel = None
                # Stangen, deren Untergrenze das Teil nicht mehr zulässt, scheitern ohnehin an passt
                bedarf = mb(t)
                art = (_enden(t), t.laenge)
                moeglich = [x for x in andere if g_andere[id(x)] + bedarf <= grenze
                            and (id(x), len(x), art) not in abgelehnt]
                for x in sorted(moeglich, key=lambda x: -vb_jetzt(x)):
                    if passt(g, x + [t]):
                        ziel = x
                        break
                    if AUFLOESEN_MERKEN:
                        abgelehnt.add((id(x), len(x), art))
                if ziel is None:
                    ok = False
                    break
                ziel.append(t)
                g_andere[id(ziel)] += bedarf
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


def kontur_paar(g, t1, t2):
    """Liegen die Enden über ihre Verläufe (Endkonturen) statt über die ebene Gehrung aneinander?"""
    return bool(g.kontur_geo) and not (t1.b_gerade and t2.a_gerade) and bool(t1.b_kontur and t2.a_kontur) and \
        (t1.b_gehrung is None or t2.a_gehrung is None or not g.querschnitt)


def konturen_ineinander(g, folge):
    """Anzahl der Stellen, an denen beliebige Endkonturen (nicht nur ebene Gehrungen) ineinanderliegen."""
    return sum(1 for (t1, r1), (t2, r2) in zip(folge, folge[1:])
               if kontur_paar(g, t1, t2) and ineinander(g, t1, r1, t2, r2))


def gleichartig(a, b):
    return a.laenge == b.laenge and a.a_gerade == b.a_gerade and a.b_gerade == b.b_gerade and \
        (a.a_gehrung, a.b_gehrung, a.drehung, a.naht, a.rest, a.ende_frei, a.a_kontur, a.b_kontur) == (
            b.a_gehrung, b.b_gehrung, b.drehung, b.naht, b.rest, b.ende_frei, b.a_kontur, b.b_kontur)


def exakt(g, ziel):
    """Exakte Suche (Branch and Bound) nach einer Einteilung mit weniger als `ziel` Stangen.
    Teile in der Reihenfolge von sortiert(), jedes Teil der Reihe nach in jede vorhandene Stange,
    dann in eine neue. Abgeschnitten wird, wenn selbst bei voller Nutzung aller freien Längen
    nicht weniger Stangen als bisher bestes Ergebnis möglich sind. Ergebnis: (Stangen oder None,
    Suche vollständig)."""
    teile = sortiert(g.teile)
    n = len(teile)
    nutz = g.luft - g.endbeschnitt
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
        if zustand["knoten"] > EXAKT_MAX_KNOTEN * (PRAEZ_EXAKT if praezision_an() else 1):
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


# Auf Hilfsprozessen schon gerechnete Gruppen (parallel.vorrechnen): {schluessel(Gruppe): (Folgen als Teilnummern,
# bewiesen, schranke)}; je Thread, damit der Staffel-Hintergrund und die Oberfläche sich nicht in die Quere kommen
vorgerechnet = threading.local()


def schluessel(g):
    """Eingaben einer Gruppe für optimiere als Text (bewiesen und schranke sind nur Ergebnis)."""
    return repr(replace(g, bewiesen=False, schranke=0)) + ("|Präzision" if praezision_an() else "")


# ------------------------------------------------------------------ Präzisionsoptimierung (Strategie P)
# Master-Auftrag universelle Konturverschachtelung (Patrick 25.11.2026), Strategie C „Präzisionsoptimierung“: mehr
# Kombinationen und Konturvarianten untersuchen. Im Präzisionsmodus prüft anordnen nach den Ketten zusätzlich eine
# lokale Suche über die Reihenfolge (jedes Teil an jeden Platz, je zwei Teile tauschen; Drehungen jeweils optimal),
# und die exakte Suche darf mehr Schritte gehen. Grenzen in Schritten, nie in Zeit: auf jedem Rechner gleich.
PRAEZ_SCHRITTE = 600        # bewertete Reihenfolgen je Stange in der lokalen Suche
PRAEZ_MAX_TEILE = 40        # lokale Suche nur für Stangen bis zu so vielen Teilen
PRAEZ_EXAKT = 4             # Faktor für die Suchschritte der exakten Suche
_modus = threading.local()


class praezision:
    """with optimierung.praezision(): … rechnet im Präzisionsmodus (je Thread)."""

    def __enter__(self):
        self._vorher = getattr(_modus, "an", False)
        _modus.an = True
        return self

    def __exit__(self, *_):
        _modus.an = self._vorher
        return False


def praezision_an():
    return getattr(_modus, "an", False)


# Nesting-Kern (Patrick 25.11.2026, Variantenlogik): die Präzision ändert gegenüber der normalen Rechnung nur zwei
# Dinge, die lokale Suche beim Anordnen (nur mit Enden zum Ineinanderlegen) und die längere exakte Suche (nur, wo sie
# in der normalen Rechnung nicht vollständig war). Gezählt werden die Gruppen, deren Stangenzahl nicht bewiesen ist
# und für die die exakte Suche gilt: ist die Zahl 0 und gibt es keine Enden zum Ineinanderlegen, rechnet P genau
# wie A (gleiches Ergebnis ohne zweite Rechnung).
class offen_zaehlen:
    """with optimierung.offen_zaehlen() as z: z.n = Gruppen mit nicht vollständiger exakter Suche (je Thread,
    verschachtelt: die äußere Zählung bekommt die innere dazu)."""

    def __enter__(self):
        self._vorher = getattr(_modus, "offen", None)
        self._z = [0]
        _modus.offen = self._z
        return self

    @property
    def n(self):
        return self._z[0]

    def __exit__(self, *_):
        _modus.offen = self._vorher
        if self._vorher is not None:
            self._vorher[0] += self._z[0]
        return False


def offen_dazu(n):
    """n Gruppen mit offener exakter Suche der laufenden Zählung hinzufügen (Ergebnis aus einem Zwischenspeicher)."""
    z = getattr(_modus, "offen", None)
    if z is not None and n:
        z[0] += n


def _offen_melden(g):
    if not g.bewiesen and len(g.teile) <= EXAKT_MAX_TEILE:
        offen_dazu(1)


def praezision_wirkt(g):
    """Kann die lokale Suche der Präzision in dieser Gruppe überhaupt etwas ändern (Enden zum Ineinanderlegen oder
    feste Naht in einer Gruppe mit Querschnitt bzw. Endkonturen)?"""
    return _nestbar(g) and (sum(verschachtelbar(g, t) for t in g.teile) >= 2 or any(t.drehung == FEST
                                                                                   for t in g.teile))


def _lokal_suchen(g, folge, naht_stange):
    """Lokale Suche über die Reihenfolge (Präzisionsmodus): verschieben und tauschen, solange der Verbrauch der
    Trennungen sinkt; höchstens PRAEZ_SCHRITTE Bewertungen. Ergebnis (Summe, Reihenfolge)."""
    beste, _ = _drehungen_waehlen(g, folge, naht_stange)
    folge = list(folge)
    n, schritte = len(folge), 0
    besser = True
    while besser and schritte < PRAEZ_SCHRITTE:
        besser = False
        for i in range(n):
            for j in range(n):
                if i == j or schritte >= PRAEZ_SCHRITTE:
                    continue
                for art in ("schieben", "tauschen"):
                    if art == "tauschen" and j < i:
                        continue
                    neu = list(folge)
                    if art == "schieben":
                        neu.insert(j, neu.pop(i))
                    else:
                        neu[i], neu[j] = neu[j], neu[i]
                    if gleichartig(neu[i], folge[i]) and gleichartig(neu[j], folge[j]):
                        continue
                    schritte += 1
                    summe, _ = _drehungen_waehlen(g, neu, naht_stange)
                    if summe < beste - EPS:
                        beste, folge, besser = summe, neu, True
                        break
                if besser:
                    break
            if besser:
                break
    return beste, folge


# Schon gerechnete Gruppen über einen Lauf hinaus (Performance-Update 10.11.2026, Tempo Teil 2): nach einer Änderung
# an einer Position, beim Angebots-PDF und in den Staffeln rechnen sonst alle unveränderten Gruppen noch einmal.
# Schlüssel = schluessel(g) (alle Eingaben der Gruppe), Wert wie bei vorgerechnet; dieselbe Rechnung ergibt
# dasselbe (begrenzt nach Schritten, nie nach Zeit), das Ergebnis bleibt also gleich. Höchstens MERKER_MAX Gruppen.
MERKER_MAX = 400
_merker = collections.OrderedDict()
_merker_sperre = threading.Lock()


def _grenzen():
    """Suchgrenzen, mit denen gerechnet wurde (Tests ändern sie): gehören zum Schlüssel."""
    return (EXAKT_MAX_TEILE, EXAKT_MAX_KNOTEN, MUSTER_MAX_RUNDEN, MUSTER_MAX_KNOTEN)


def _merk_schluessel(schl):
    """Schlüssel im Merker: Prüfsumme (BLAKE2b, 256 Bit) des Gruppentexts statt des Texts selbst (Rechenkern 2.0,
    Paket 6, 24.11.2026: der Text enthält alle Teile der Gruppe; 400 solche Texte ließen den Speicher im
    Dauerlauf um ~0,4 MB je Rechenrunde wachsen, bei großen Gruppen um ein Vielfaches). Gleicher Text, gleiche
    Prüfsumme; zwei verschiedene Texte mit gleicher 256-Bit-Prüfsumme kommen praktisch nicht vor."""
    return hashlib.blake2b(schl.encode("utf-8", "surrogatepass"), digest_size=32).digest(), len(schl), _grenzen()


def gemerkt(schl):
    """Ergebnis einer schon gerechneten Gruppe (Folgen als Teilnummern, bewiesen, schranke) oder None."""
    s = _merk_schluessel(schl)
    with _merker_sperre:
        erg = _merker.get(s)
        if erg is not None:
            _merker.move_to_end(s)
        return erg


def _ablegen(schl, erg):
    s = _merk_schluessel(schl)
    with _merker_sperre:
        _merker[s] = erg
        _merker.move_to_end(s)
        while len(_merker) > MERKER_MAX:
            _merker.popitem(last=False)


def _merken(schl, g, folgen):
    stelle = {id(t): i for i, t in enumerate(g.teile)}
    try:
        erg = ([[(stelle[id(t)], d) for t, d in f] for f in folgen], g.bewiesen, g.schranke)
    except KeyError:            # Teil nicht aus g.teile (kommt nicht vor): nicht merken
        return
    _ablegen(schl, erg)


def merker_leeren():
    with _merker_sperre:
        _merker.clear()


def optimiere(g):
    """Ergebnis: Liste von Stangen, je Stange die angeordnete Folge [(Teil, gedreht)].
    Setzt g.bewiesen, wenn die Stangenzahl nachweislich minimal ist."""
    schl = schluessel(g)
    fertig = getattr(vorgerechnet, "gruppen", None)
    erg = fertig.pop(schl, None) if fertig else None
    if erg is None:
        erg = gemerkt(schl)
    else:
        _ablegen(schl, erg)
    if erg is not None:         # dieselbe Rechnung lief schon (Hilfsprozess oder früherer Lauf)
        folgen, g.bewiesen, g.schranke = erg
        _offen_melden(g)
        return [[(g.teile[i], d) for i, d in f] for f in folgen]
    folgen = _optimiere(g)
    _merken(schl, g, folgen)
    _offen_melden(g)
    return folgen


def _optimiere(g):
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


# ------------------------------------------------------------------ Stabile Stangenpläne (CAM-006)
# „leicht geändert“: höchstens so viele Teile neu einzuplanen (sonst rechnet der Plan ganz neu)
STABIL_NEU_MIN, STABIL_NEU_ANTEIL = 5, 0.25


def stabil(g, folgen, frueher, kennung):
    """CAM-006 (Plan Phase 3 und 4, Paket D, Patrick 13.11.2026): wird die Menge nur leicht geändert, bleibt der Plan
    so weit wie möglich gleich. frueher: Stangen des bisherigen Plans dieser Gruppe als Listen von Kennungen der Teile
    (kennung(Teil), z. B. Position und Länge). Jede frühere Stange wird mit den noch vorhandenen Teilen derselben
    Kennung neu belegt (überzählige fallen weg), zusätzliche (höchstens 5 bzw. ein Viertel der Teile) Teile kommen in den Platz der vorhandenen Stangen oder
    auf neue Stangen (First-Fit). Übernommen nur, wenn alle Teile eingeplant sind und es höchstens so viele Stangen
    sind wie im neu gerechneten Plan folgen – sonst bleibt folgen. Ergebnis (folgen, gleich): gleich = Zahl der
    Stangen mit genau derselben Belegung wie bisher (0 = neu gerechneter Plan)."""
    if not frueher or not folgen:
        return folgen, 0
    vorrat = {}
    for t in sortiert(g.teile):
        vorrat.setdefault(kennung(t), []).append(t)
    stangen, wie_alt = [], []
    for alt in frueher:
        st = []
        for kn in alt:
            liste = vorrat.get(kn)
            if liste:
                st.append(liste.pop(0))
        if not st:
            continue
        if not passt(g, st):            # Teil geändert (z. B. Länge): Stange auflösen, Teile neu einplanen
            for t in st:
                vorrat[kennung(t)].append(t)
            continue
        stangen.append(st)
        wie_alt.append(len(st) == len(alt))
    if not stangen:
        return folgen, 0
    rest = sortiert([t for liste in vorrat.values() for t in liste])
    if len(rest) > max(STABIL_NEU_MIN, STABIL_NEU_ANTEIL * len(g.teile)):     # keine leichte Änderung mehr
        return folgen, 0
    neue = []
    for t in rest:
        for i, st in enumerate(stangen):
            if passt(g, st + [t]):
                st.append(t)
                wie_alt[i] = False
                break
        else:
            neue.append(t)
    gesamt = stangen + (first_fit(g, neue) if neue else [])
    if len(gesamt) > len(folgen) or sum(len(s) for s in gesamt) != len(g.teile):
        return folgen, 0
    return [anordnen(s, g) for s in gesamt], sum(wie_alt)


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
    basis = (t.laenge, t.a_gerade, t.b_gerade, t.a_schnitt, t.b_schnitt, t.a_gehrung or (), t.b_gehrung or (),
             t.drehung, -1 if t.naht is None else t.naht, t.rest, t.ende_frei)
    return basis + (t.a_kontur or "", t.b_kontur or "") if (t.a_kontur or t.b_kontur) else basis


# Anzahl je Endenart als eine Zahl (16 Bit je Art) statt als Liste: spart je Suchknoten zwei Listenkopien
_ART_BITS = 16
_ART_MASKE = (1 << _ART_BITS) - 1


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
    vertreter = {a: replace(typen[art.index(a)], laenge=0.0, a_gehrung=None, b_gehrung=None, drehung=FREI, naht=None,
                            a_kontur=None, b_kontur=None)
                 for a in set(art)}
    zuschlag = {}

    def zuschlag_von(schl):
        anz = [(schl >> (_ART_BITS * a)) & _ART_MASKE for a in range(4)]
        null = [vertreter[a] for a in range(4) for _ in range(anz[a])]
        zs = zuschlag[schl] = verbrauch(g, anordnen(null))
        return zs

    grenze = g.nutzbar_bis + EPS
    frei = g.nutzbar_bis - g.endbeschnitt
    laengen = [t.laenge for t in typen]
    eins = [1 << (_ART_BITS * a) for a in art]      # +1 Teil dieser Endenart in der Anzahl-Zahl

    def suche(i, w, laenge, anz0):
        # anz0: Anzahl je Endenart der Typen vor i als eine Zahl (gleiche Suche, gleiche Knotenzahl wie bisher)
        knoten[0] += 1
        if w > beste[1] + 1e-9:
            beste[0], beste[1] = list(zahl), w
        if i == n or knoten[0] > MUSTER_MAX_KNOTEN:
            return
        if w + q_ab[i] * (frei - laenge) <= beste[1] + 1e-9:
            return
        li, d, bi = laengen[i], eins[i], bedarf[i]
        anz, k = anz0, 0
        while k < bi:
            anz += d
            zs = zuschlag.get(anz)
            if zs is None:
                zs = zuschlag_von(anz)
            if not zs + (laenge + li * (k + 1)) <= grenze:      # passt nicht mehr auf die Stange
                break
            k += 1
        wi, i1 = wert[i], i + 1
        while True:
            zahl[i] = k
            suche(i1, w + wi * k, laenge + li * k, anz0 + d * k)
            if k == 0:
                break
            k -= 1

    suche(0, 0.0, 0.0, 0)
    return beste[0], knoten[0] <= MUSTER_MAX_KNOTEN


# Simplex für die Spaltengenerierung (Master-Prompt Rechenkerne 21.11.2026). Jede Runde der Schnittmuster-Optimierung
# löst dasselbe lineare Programm mit einer Zeile (einem Muster) mehr. Die Schritte des Simplex hängen für die
# bisherigen Zeilen nicht von der neuen Zeile ab, solange die neue Zeile in keinem Schritt die Pivotzeile wird: bis
# dahin rechnet jede Zahl genau gleich. SimplexVerlauf merkt sich die Schritte der letzten Runde und alle
# SIMPLEX_STAND_ALLE Schritte den ganzen Stand; die nächste Runde führt nur die neue Zeile durch die bekannten
# Schritte, bis sie mitspielt, und rechnet ab dort wie bisher weiter. Ergebnis, Pivotfolge und jede Zahl sind
# dieselben wie bei einer Rechnung von vorn (Prüfung: tests/test_rechenkerne_2111.py).
# Aufbau einer Tableau-Zeile: [rechte Seite, Spalten der Typen, Schlupf 0 … m-1]; Zeilen dürfen kürzer sein als die
# Pivotzeile (fehlende Spalten sind 0,0 und werden erst bei Bedarf angehängt).
SIMPLEX_STAND_ALLE = 3      # alle so viele Schritte einen Zwischenstand merken …
SIMPLEX_STAENDE_MAX = 32    # … aber höchstens so viele (Arbeitsspeicher; danach gröber, die späten bleiben dichter)


class SimplexVerlauf:
    """Schritte und Zwischenstände des letzten Simplex-Laufs einer Spaltengenerierung (siehe oben)."""
    __slots__ = ("a", "c", "b", "staende", "schritte", "uebernommen", "gerechnet")

    def __init__(self):
        self.a = self.c = self.b = None
        self.staende, self.schritte = {}, []
        self.uebernommen = self.gerechnet = 0


def _simplex_schritt(tab, z, m, r, e, zeile, nz):
    """Pivotschritt: Zeile r wird zeile (schon durch das Pivotelement geteilt), alle anderen Zeilen und die
    Zielzeile verlieren f × zeile; nur die Spalten nz (zeile dort nicht 0) ändern sich (x − f·0 = x)."""
    tab[r] = list(zeile)
    lz = len(zeile)
    for i in range(m):
        if i != r:
            ti = tab[i]
            f = ti[e] if e < len(ti) else 0.0
            if abs(f) > 1e-12:
                if len(ti) < lz:
                    ti.extend([0.0] * (lz - len(ti)))
                for j in nz:
                    ti[j] = ti[j] - f * zeile[j]
    f = z[e]
    for j in nz:
        z[j] = z[j] - f * zeile[j]


def simplex_max(c, a, b, verlauf=None):
    """Lineares Programm max c·y unter a·y <= b, y >= 0 mit b >= 0 (Simplex mit Tableau, Regel von Bland gegen
    Kreisen). Ergebnis: (y, Zielwert, Schattenpreise der Zeilen, gelöst).
    verlauf (SimplexVerlauf): Ist a die Matrix des letzten Laufs mit einer Zeile mehr (c gleich, b gleich bis auf
    die neue Zeile), werden dessen Schritte übernommen, solange sie für die neue Zeile gleich bleiben."""
    m, n = len(a), len(c)
    grenze = 20 * (m + n) + 100
    start = None
    if verlauf is not None and verlauf.a is not None and m == len(verlauf.a) + 1 and verlauf.c == c \
            and verlauf.b == b[:-1] and a[:-1] == verlauf.a:
        start = _simplex_fortsetzen(verlauf, a[-1], b[-1], n, m)
    if start is None:
        tab = [[b[i]] + list(a[i]) + [0.0] * i + [1.0] for i in range(m)]
        z = [0.0] + [-x for x in c] + [0.0] * m
        basis = [n + i for i in range(m)]
        schritt, staende, schritte = 0, {}, []
    else:
        tab, z, basis, schritt, staende, schritte = start
        verlauf.uebernommen += schritt
    geloest = False
    merken = verlauf is not None
    while schritt < grenze:
        if merken and schritt % SIMPLEX_STAND_ALLE == 0 and schritt not in staende:
            staende[schritt] = ([list(t) for t in tab], list(z), list(basis))
        e = None
        for j in range(1, n + m + 1):
            if z[j] < -1e-9:
                e = j
                break
        if e is None:
            geloest = True
            break
        r, best = None, None
        for i in range(m):
            ti = tab[i]
            v = ti[e] if e < len(ti) else 0.0
            if v > 1e-9:
                q = ti[0] / v
                if best is None or q < best - 1e-12 or (abs(q - best) <= 1e-12 and basis[i] < basis[r]):
                    r, best = i, q
        if r is None:       # unbeschränkt: kommt bei Schnittmustern nicht vor (jeder Typ hat ein Muster)
            break
        p = tab[r][e]
        zeile = [x / p for x in tab[r]]
        nz = [j for j, y in enumerate(zeile) if y != 0.0]
        _simplex_schritt(tab, z, m, r, e, zeile, nz)
        if merken:
            schritte.append((e, r, best, zeile, nz))
            verlauf.gerechnet += 1
        basis[r] = e - 1
        schritt += 1
    if merken:
        verlauf.a, verlauf.c, verlauf.b = [list(x) for x in a], list(c), list(b)
        verlauf.staende, verlauf.schritte = _staende_ausduennen(staende), schritte
    y = [0.0] * n
    for i, bi in enumerate(basis):
        if bi < n:
            y[bi] = tab[i][0]
    return y, z[0], z[1 + n:1 + n + m], geloest


def _staende_ausduennen(staende):
    """Höchstens SIMPLEX_STAENDE_MAX Zwischenstände: die späteren Hälfte bleibt, von den früheren jeder zweite
    (die neue Zeile spielt meist erst spät mit). Schritt 0 bleibt immer. Nur Tempo, nie das Ergebnis: fehlt ein
    Stand, werden die bekannten Schritte ab dem vorigen nachgerechnet."""
    while len(staende) > SIMPLEX_STAENDE_MAX:
        schl = sorted(staende)
        frueh = schl[1:len(schl) // 2]
        if not frueh:
            break
        for s in frueh[::2]:
            del staende[s]
    return staende


def _simplex_basis(v, t, r):
    """Basisvariable der Zeile r vor Schritt t des gemerkten Laufs."""
    k = max(s for s in v.staende if s <= t)
    basis = list(v.staende[k][2])
    for s in range(k, t):
        e, rr = v.schritte[s][0], v.schritte[s][1]
        basis[rr] = e - 1
    return basis[r]


def _simplex_fortsetzen(v, a_neu, b_neu, n, m):
    """Neue Zeile durch die Schritte des gemerkten Laufs führen, bis sie in einem Schritt Pivotzeile würde (oder der
    Lauf endete). Ergebnis: (Tableau, Zielzeile, Basis, Schritt, Zwischenstände, Schritte) zum Weiterrechnen, oder
    None (von vorn rechnen)."""
    zeile_neu = [b_neu] + list(a_neu) + [0.0] * (m - 1) + [1.0]
    b_basis = n + m - 1
    breite = 1 + n + m
    staende = {}
    t = len(v.schritte)
    for s, (e, r, best, zeile, nz) in enumerate(v.schritte):
        if s in v.staende:
            tab_s, z_s, basis_s = v.staende[s]
            staende[s] = (tab_s + [list(zeile_neu)], z_s + [0.0] * (breite - len(z_s)), basis_s + [b_basis])
        w = zeile_neu[e] if e < len(zeile_neu) else 0.0
        if w > 1e-9:            # Quotiententest wie im Lauf: die neue Zeile ist die letzte, also zuletzt geprüft
            q = zeile_neu[0] / w
            if q < best - 1e-12 or (abs(q - best) <= 1e-12 and b_basis < _simplex_basis(v, s, r)):
                t = s
                break
        if abs(w) > 1e-12:
            if len(zeile_neu) < len(zeile):
                zeile_neu.extend([0.0] * (len(zeile) - len(zeile_neu)))
            for j in nz:
                zeile_neu[j] = zeile_neu[j] - w * zeile[j]
    if t == len(v.schritte) and t in v.staende:
        tab_s, z_s, basis_s = v.staende[t]
        staende[t] = (tab_s + [list(zeile_neu)], z_s + [0.0] * (breite - len(z_s)), basis_s + [b_basis])
    vorher = [s for s in staende if s <= t]
    if not vorher:
        return None
    k = max(vorher)             # letzter gemerkter Stand vor t, dann die bekannten Schritte bis t nachrechnen
    tab_s, z_s, basis_s = staende[k]
    tab, z, basis = [list(x) for x in tab_s], list(z_s), list(basis_s)
    for s in range(k, t):
        e, r, best, zeile, nz = v.schritte[s]
        _simplex_schritt(tab, z, m, r, e, zeile, nz)
        basis[r] = e - 1
    return tab, z, basis, t, {s: x for s, x in staende.items() if s <= t}, list(v.schritte[:t])


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
    verlauf = SimplexVerlauf()      # jede Runde setzt die Schritte der vorigen fort (gleiches Ergebnis, schneller)
    for _ in range(MUSTER_MAX_RUNDEN):
        y, wert, x, geloest = simplex_max([float(d) for d in bedarf], [[float(v) for v in m] for m in muster],
                                          [1.0] * len(muster), verlauf)
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
    # mit Teil am Stangenende auch nicht: die Muster rechnen ohne den Bonus am Stangenende
    schranke = math.ceil(wert - 1e-6) if vollstaendig and geloest and g.ende_bonus <= EPS and not any(
        verschachtelbar(g, t) for t in g.teile) else 0
    # ganze Stangen aus der LP-Lösung, Rest heuristisch
    rest, vorrat, stangen = list(bedarf), {k: list(v) for k, v in gruppen.items()}, []
    for m, xp in sorted(zip(muster, x), key=lambda a: (-a[1], a[0])):
        for _ in range(int(math.floor(xp + 1e-9))):
            if any(rest[i] < m[i] for i in range(n)):
                break
            neu = [vorrat[keys[i]][-1 - j] for i in range(n) for j in range(m[i])]
            if _mit_3d(g, neu) and not passt(g, neu):     # Muster ohne 3D-Greifmaß gerechnet: Rest heuristisch
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
    if _mit_3d(g, g.teile):     # Muster ohne 3D-Greifmaß gerechnet: Stangen, die damit nicht passen, neu packen
        zu_viel = [t for s in stangen if not passt(g, s) for t in s]
        stangen = [s for s in stangen if passt(g, s)] + (first_fit(g, zu_viel) if zu_viel else [])
    return aufloesen(g, stangen)


# ------------------------------------------------------------------ Weniger verschiedene Belegungen (Plan PROfirst H1)
# PROfirst „Anzahl verschiedener Schachtelungen minimieren“: jede andere Stangenbelegung ist an der Maschine ein
# eigenes Programm (Rüsten, Kontrolle, Sortieren). Darf etwas mehr Material verbraucht werden (Einstellung
# muster_mehrverschnitt, Vorgabe 2 % der Stangenlänge der Gruppe), werden gleiche Muster mehrfach geschnitten.
MUSTERARM_SCHWELLEN = (0.98, 0.95, 0.92, 0.88, 0.84, 0.8, 0.75, 0.7)


def belegungen(folgen):
    """Anzahl verschiedener Stangenbelegungen (Muster = welche Teiletypen wie oft, Reihenfolge egal)."""
    return len({tuple(sorted(collections.Counter(typ(t) for t, _ in f).items())) for f in folgen})


def _musterarm_lauf(g, keys, gruppen, schwelle):
    typen = [gruppen[k][0] for k in keys]
    vorrat = {k: list(gruppen[k]) for k in keys}
    bedarf = [len(gruppen[k]) for k in keys]
    wert = [t.laenge for t in typen]
    nutz = g.nutzbar_bis - g.endbeschnitt
    stangen = []
    while sum(bedarf):
        gewaehlt = None
        for k in range(max(bedarf), 0, -1):          # das Muster, das sich am öftesten wiederholen lässt
            teil = [b // k for b in bedarf]
            if not sum(teil):
                continue
            m, _ = bestes_muster(g, typen, teil, wert)
            if m and sum(m) and sum(c * t.laenge for c, t in zip(m, typen)) >= schwelle * nutz - EPS:
                gewaehlt = (k, m)
                break
        if gewaehlt is None:                          # Rest: bestes Muster je Stange
            m, _ = bestes_muster(g, typen, bedarf, wert)
            if not m or not sum(m):
                return None
            gewaehlt = (1, m)
        k, m = gewaehlt
        for _ in range(k):
            s = [vorrat[keys[i]].pop() for i in range(len(m)) for _ in range(m[i])]
            if not passt(g, s):
                return None
            stangen.append(s)
        bedarf = [b - k * c for b, c in zip(bedarf, m)]
    return stangen


def musterarm(g, folgen, grenze):
    """Stangenplan mit weniger verschiedenen Belegungen, wenn der Mehrverbrauch an Stangenlänge höchstens
    grenze × (Stangen × Stangenlänge) des besten Plans beträgt. Ergebnis: neue Folgen oder None (keine Verbesserung,
    ausgeschaltet, Teile mit fester Naht auf verschiedenen Seiten oder 3D-Greifmaß)."""
    if not grenze or grenze <= 0 or len(folgen) < 3 or not g.teile or not vertraeglich(g, g.teile) \
            or _mit_3d(g, g.teile) or sum(len(f) for f in folgen) != len(g.teile):
        return None
    vorher = belegungen(folgen)
    if vorher <= 1:
        return None
    gruppen = {}
    for t in sortiert(g.teile):
        gruppen.setdefault(typ(t), []).append(t)
    keys = sorted(gruppen, key=lambda k: (-k[0], k))
    erlaubt = len(folgen) + math.floor(grenze * len(folgen) + EPS)    # Mehrverschnitt in ganzen Stangen
    beste = None
    for schwelle in MUSTERARM_SCHWELLEN:
        st = _musterarm_lauf(g, keys, gruppen, schwelle)
        if st is None or len(st) > erlaubt or sum(len(s) for s in st) != len(g.teile):
            continue
        neu = [anordnen(s, g) for s in st]
        if any(belegt(g, f) > g.nutzbar_bis + EPS for f in neu):
            continue
        schl = (belegungen(neu), len(neu))
        if schl[0] < vorher and (beste is None or schl < beste[0]):
            beste = (schl, neu)
    if beste is None:
        return None
    neu = beste[1]
    neu.sort(key=lambda f: (-verbrauch(g, f), f[0][0].zeile))
    return neu


def manuell(g):
    """Einfache manuelle Einteilung: Eingabereihenfolge, keine Drehung, Stange voll, dann nächste."""
    stangen, aktuell = [], []
    for t in sorted(g.teile, key=lambda t: (t.zeile, t.nr)):
        if aktuell and belegt(g, [(x, False) for x in aktuell + [t]]) > g.nutzbar_bis + EPS:
            stangen.append(aktuell)
            aktuell = []
        aktuell.append(t)
    if aktuell:
        stangen.append(aktuell)
    return stangen


def ohne_drehung(g):
    """Stangen, wenn kein Teil gedreht werden dürfte (Vergleich für die Auswertung); None = in dieser Gruppe gibt es
    keine drehbaren Teile mit Gehrung."""
    h = ohne_drehung_gruppe(g)
    return None if h is None else len(optimiere(h))


def ohne_drehung_gruppe(g):
    """Die Gruppe, als dürfte kein Teil gedreht werden (ohne_drehung), oder None."""
    if not any(verschachtelbar(g, t) and len(drehungen(g, t)) > 1 for t in g.teile):
        return None
    return replace(g, teile=[replace(t, drehung=UNBEKANNT) if t.drehung == FREI else t for t in g.teile],
                   bewiesen=False, schranke=0)


def untergrenze(g):
    nutz = g.luft - g.endbeschnitt
    return math.ceil(sum(mindestbedarf(g, t) for t in g.teile) / nutz - EPS) if g.teile else 0



# ------------------------------------------------------------------ Stangen von Hand vorgegeben
# Patrick 26.10.2026: „Für die Verschachtelung eine Option: manuell Stangenlänge und die Stückzahl zu der Länge, mehrere
# Längen eintragbar“. Statt beliebig vieler Stangen der Angebotslänge gibt es genau die vorgegebenen Stangen, z. B.
# 3 × 6.000 + 2 × 4.500 mm. Ziel der Reihe nach: möglichst viele Teile einplanen, möglichst wenig Stangenlänge,
# möglichst wenige Stangen. Was nicht mehr auf eine vorgegebene Stange passt, bleibt nicht eingeplant. Keine
# Restverwaltung: nicht genutzte Länge ist Verschnitt, nicht gebrauchte Stangen bleiben einfach übrig.
def vorrat_lesen(vorgabe):
    """[(Länge, Anzahl)] aus [[Länge, Anzahl], …], gleiche Längen zusammengefasst, längste zuerst; Zeilen ohne
    gültige Länge oder Anzahl fallen weg."""
    out = {}
    for z in vorgabe or ():
        try:
            laenge, anzahl = float(z[0]), int(z[1])
        except (TypeError, ValueError, IndexError):
            continue
        if laenge > 0 and anzahl > 0:
            laenge = int(laenge) if laenge.is_integer() else laenge
            out[laenge] = out.get(laenge, 0) + anzahl
    return sorted(out.items(), reverse=True)


def _zuteilen(g, stangen, vorrat):
    """Längen für fertig zusammengestellte Stangen (Teilelisten): größter Bedarf zuerst, je die kürzeste freie Länge,
    auf die die Stange passt (so ist die Summe der Längen am kleinsten). Ergebnis: ([(Länge, Teile)], Teilelisten
    ohne Stange, übrige Anzahl je Länge)."""
    frei = dict(vorrat)
    gs = {laenge: replace(g, stange=laenge, teile=[]) for laenge in frei}
    out, ohne = [], []
    for s in sorted(stangen, key=lambda s: (-belegt(g, anordnen(s, g)), min((t.zeile, t.nr) for t in s))):
        laenge = min((x for x, n in frei.items() if n > 0 and passt(gs[x], s)), default=None)
        if laenge is None:
            ohne.append(s)
            continue
        frei[laenge] -= 1
        out.append((laenge, s))
    return out, ohne, frei


def _fuellen(g, teile, frei, stangen, art="quote"):
    """Teile auf die freien Stangen verteilen: das längste übrige Teil eröffnet eine Stange, aufgefüllt wird der Reihe
    nach mit allem, was noch passt; genommen wird die freie Länge, die so am besten gefüllt ist (art 'quote'), bzw.
    die längste ('lang') oder kürzeste ('kurz') freie Länge, auf die das Teil passt; 'anzahl': kürzeste Teile zuerst
    auf die längste freie Stange (möglichst viele Teile, wenn die Stangen knapp sind). Hängt an stangen [(Länge,
    Teile)] an und zählt frei herunter. Ergebnis: Teile ohne Stange."""
    gs = {laenge: replace(g, stange=laenge, teile=[]) for laenge in frei}
    teile, uebrig = sortiert(teile), []
    if art == "anzahl":
        teile = teile[::-1]
    while teile:
        t, beste = teile[0], None
        for laenge in sorted(frei, reverse=art != "kurz"):         # 'anzahl' wie 'lang'
            if frei[laenge] <= 0 or not passt(gs[laenge], [t]):
                continue
            if beste is not None and art != "quote":
                break
            s = [t]
            for x in teile[1:]:
                if passt(gs[laenge], s + [x]):
                    s.append(x)
            wert = sum(x.laenge for x in s) / laenge
            if beste is None or wert > beste[0] + EPS:
                beste = (wert, laenge, s)
        if beste is None:
            uebrig.append(t)
            teile = teile[1:]
            continue
        _, laenge, s = beste
        frei[laenge] -= 1
        stangen.append((laenge, s))
        weg = {id(x) for x in s}
        teile = [x for x in teile if id(x) not in weg]
    return uebrig


def _muster_fuellen(g, teile, frei, stangen, art="quote", hoch=1.0):
    """Wie _fuellen, aber je Stange das Schnittmuster mit der größten Teilelänge (bestes_muster): genommen wird die
    freie Länge mit der besten Füllung (art 'quote') bzw. die längste ('lang'); das Muster wird so oft geschnitten,
    wie Teile und Stangen reichen. hoch > 1 bevorzugt lange Teile im Muster (Wert Länge ** hoch). Passt ein Muster nicht (Gehrungen, 3D-Greifmaß), füllt First Fit. Ergebnis: Teile
    ohne Stange."""
    gs = {laenge: replace(g, stange=laenge, teile=[]) for laenge in frei}
    vorrat_t = {}
    for t in sortiert(teile):
        vorrat_t.setdefault(typ(t), []).append(t)
    while any(vorrat_t.values()) and any(n > 0 for n in frei.values()):
        keys = sorted((k for k, v in vorrat_t.items() if v), key=lambda k: (-k[0], k))
        typen = [vorrat_t[k][0] for k in keys]
        bedarf = [len(vorrat_t[k]) for k in keys]
        beste = None
        for laenge in sorted(frei, reverse=True):
            if frei[laenge] <= 0:
                continue
            m, _ = bestes_muster(gs[laenge], typen, bedarf, [t.laenge ** hoch for t in typen])
            if not m or not sum(m):
                continue
            wert = sum(m[i] * typen[i].laenge for i in range(len(m))) / laenge
            if beste is None or wert > beste[0] + EPS:
                beste = (wert, laenge, m)
            if art == "lang":
                break
        if beste is None:
            break
        _, laenge, m = beste
        mal = min([frei[laenge]] + [bedarf[i] // m[i] for i in range(len(m)) if m[i]])
        for _ in range(mal):
            s = [vorrat_t[keys[i]][-1 - j] for i in range(len(m)) for j in range(m[i])]
            if not passt(gs[laenge], s):            # Muster ohne Ineinanderlegen/3D-Greifmaß gerechnet
                s = []
                for t in sortiert([t for v in vorrat_t.values() for t in v]):
                    if passt(gs[laenge], s + [t]):
                        s.append(t)
                if not s:
                    break
            weg = {id(t) for t in s}
            for k in vorrat_t:
                vorrat_t[k] = [t for t in vorrat_t[k] if id(t) not in weg]
            frei[laenge] -= 1
            stangen.append((laenge, s))
            if any(len(vorrat_t[keys[i]]) < m[i] for i in range(len(m))):
                break
    return [t for v in vorrat_t.values() for t in v]


def _verbessern(g, stangen):
    """Schwach belegte Stangen auflösen, wenn alle ihre Teile auf die anderen Stangen (mit deren Länge) passen."""
    stangen = [(laenge, list(s)) for laenge, s in stangen]
    gs = {laenge: replace(g, stange=laenge, teile=[]) for laenge, _ in stangen}
    geaendert = True
    while geaendert and len(stangen) > 1:
        geaendert = False
        for i in sorted(range(len(stangen)), key=lambda i: (sum(t.laenge for t in stangen[i][1]), -stangen[i][0])):
            andere = [(laenge, list(s)) for j, (laenge, s) in enumerate(stangen) if j != i]
            ok = True
            for t in sortiert(stangen[i][1]):
                ziel = next((s for laenge, s in sorted(andere, key=lambda x: -belegt(g, anordnen(x[1], g)))
                             if passt(gs[laenge], s + [t])), None)
                if ziel is None:
                    ok = False
                    break
                ziel.append(t)
            if ok:
                stangen = andere
                geaendert = True
                break
    return stangen


def vorrat_planen(g, vorrat):
    """Schnittplan mit den vorgegebenen Stangen vorrat [(Länge, Anzahl)]. Kandidaten: die Optimierung je einzelner
    Länge (optimiere), deren Stangen die kürzesten passenden Längen bekommen, was keine Stange bekommt, wird auf die
    übrigen verteilt (_fuellen); dazu die Verteilung aller Teile mit _fuellen (beste Füllung, längste bzw. kürzeste
    Stange zuerst) und mit den besten Schnittmustern (_muster_fuellen). Jeder Kandidat wird verbessert (_verbessern: schwach belegte Stangen auflösen) und bekommt am
    Ende noch einmal die kürzesten passenden Längen (_zuteilen). Es gilt der Kandidat mit den wenigsten nicht eingeplanten
    Teilen, dann der kleinsten Summe der Stangenlängen, dann den wenigsten Stangen.
    Ergebnis: ([(Länge, Folge [(Teil, Drehung)])], nicht eingeplante Teile)."""
    vorrat = [(laenge, n) for laenge, n in vorrat if n > 0]
    kandidaten = []
    for laenge, _ in vorrat:
        h = replace(g, stange=laenge, teile=[t for t in g.teile if passt(replace(g, stange=laenge), [t])],
                    bewiesen=False, schranke=0)
        if not h.teile:
            continue
        drauf = {id(t) for t in h.teile}
        st, ohne, frei = _zuteilen(g, [[t for t, _ in f] for f in optimiere(h)], vorrat)
        rest = [t for t in g.teile if id(t) not in drauf] + [t for s in ohne for t in s]
        kandidaten.append((st, _fuellen(g, rest, frei, st)))
    for art in ("quote", "lang", "kurz", "anzahl"):
        st = []
        kandidaten.append((st, _fuellen(g, list(g.teile), dict(vorrat), st, art)))
    for art, hoch in (("quote", 1.0), ("lang", 1.0), ("quote", 1.2), ("lang", 1.2)):
        st, frei = [], dict(vorrat)
        rest = _muster_fuellen(g, list(g.teile), frei, st, art, hoch)
        kandidaten.append((st, _fuellen(g, rest, frei, st)))
    beste = None
    for st, uebrig in kandidaten:
        st = _verbessern(g, st)
        neu, ohne, _ = _zuteilen(g, [s for _, s in st], vorrat)
        if not ohne:
            st = neu
        wert = (len(uebrig), sum(laenge for laenge, _ in st), len(st))
        if beste is None or wert < beste[0]:
            beste = (wert, st, uebrig)
    _, st, uebrig = beste
    folgen = [(laenge, anordnen(s, replace(g, stange=laenge))) for laenge, s in st]
    # längste Stangen zuerst, je Länge die mit der höchsten Belegung (Reststange zuletzt)
    folgen.sort(key=lambda x: (-x[0], -verbrauch(g, x[1]), x[1][0][0].zeile))
    return folgen, sorted(uebrig, key=lambda t: (t.zeile, t.nr))


def pruefe_vorrat(g, vorrat, folgen, uebrig):
    """Unabhängige Kontrolle eines Plans mit vorgegebenen Stangen: jedes Teil genau einmal eingeplant oder übrig,
    je Länge nicht mehr Stangen als vorgegeben, keine Stange überbelegt."""
    ids = sorted([(t.zeile, t.nr) for _, f in folgen for t, _ in f] + [(t.zeile, t.nr) for t in uebrig])
    if ids != sorted((t.zeile, t.nr) for t in g.teile):
        raise AssertionError(f"{g.profil}: Teile fehlen oder doppelt (vorgegebene Stangen)")
    frei = dict(vorrat)
    for laenge, f in folgen:
        if frei.get(laenge, 0) <= 0:
            raise AssertionError(f"{g.profil}: mehr Stangen {laenge:g} mm als vorgegeben")
        frei[laenge] -= 1
        h = replace(g, stange=laenge, teile=[t for t, _ in f])
        pruefe([h], [[f]])


# ------------------------------------------------------------------ Zuschnitt langer Lieferstangen
# Eine Lieferstange, die länger ist als die Maschine laden kann (z. B. 12.000 mm bei 6.500 mm), wird vom Lieferanten
# in Werkstücke geschnitten, die einzeln geladen werden. Werkstück = Endbeschnitt + Teile + Trennungen + letzter
# Schnittverlust + Greiferrest, auf ganze mm aufgerundet, höchstens die max. Stangenlänge der Maschine. Zwischen zwei
# Werkstücken geht der Schnittverlust des Zuschnitts verloren, der Rest der Lieferstange ist Verschnitt.
ZUSCHNITT_TEILUNG = 6    # Ziel-Werkstücklängen: Lieferlänge geteilt durch 1 … 6 (Schritte, keine Zeit)
ZUSCHNITT_RASTER = 250   # dazu alle 250 mm zwischen nötiger und max. Werkstücklänge (Patrick 28.10.2026: optimale
                         # Zuschnittslänge; spart bei gemischten Teilelängen Lieferstangen)
ZUSCHNITT_RASTER_MAX = 300   # nur bis zu so vielen Teilen je Gruppe (große Gruppen: Rechenzeit, kaum Gewinn)


def werkstueck_laenge(g, folge):
    """Länge des Werkstücks für eine Folge (ganze mm)."""
    return math.ceil(verbrauch(g, folge) + hinten(g, folge) - EPS)


def zuschnitt_belegt(laengen, saege):
    """Belegte Länge einer Lieferstange: Werkstücke + Zuschnitte dazwischen."""
    return sum(laengen) + saege * max(len(laengen) - 1, 0)


def zuschnitt_ziele(g, lieferlaenge, max_werkstueck, saege, min_werkstueck=0, puffer=0):
    """Ziel-Werkstücklängen, die ausprobiert werden (Obergrenzen: jedes Werkstück wird danach auf seinen Bedarf
    gekürzt): die max. Werkstücklänge, die Lieferlänge geteilt durch 2 … n (abzüglich der Zuschnitte) und bis
    ZUSCHNITT_RASTER_MAX Teile ab der nötigen Länge alle ZUSCHNITT_RASTER mm, soweit das längste Teil hineinpasst und
    die Mindestlänge erreicht ist. Längste zuerst."""
    noetig = max(g.endbeschnitt + max(t.laenge + max(g.greiferrest - g.ende_bonus * t.ende_frei, t.rest) for t in g.teile) + g.kerf + puffer,
                 min_werkstueck or 0)
    ziele = {int(min(max_werkstueck, math.floor((lieferlaenge - (n - 1) * saege) / n + EPS)))
             for n in range(1, ZUSCHNITT_TEILUNG + 1)}
    if len(g.teile) <= ZUSCHNITT_RASTER_MAX:
        ziele |= set(range(int(math.ceil(noetig - EPS)), int(max_werkstueck), ZUSCHNITT_RASTER))
    return sorted((z for z in ziele if z + EPS >= noetig), reverse=True)


def zuschnitt_gruppen(g, lieferlaenge, max_werkstueck, saege, min_werkstueck=0, puffer=0):
    """Je Ziel-Werkstücklänge die Gruppe, die zuschnitt optimiert: [(Ziel, Gruppe)]."""
    mindest = math.ceil((min_werkstueck or 0) - EPS)
    puffer = math.ceil((puffer or 0) - EPS)
    return [(ziel, replace(g, stange=ziel - puffer, teile=list(g.teile)))
            for ziel in zuschnitt_ziele(g, lieferlaenge, max_werkstueck, saege, mindest, puffer)]


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
    for ziel, h in zuschnitt_gruppen(g, lieferlaenge, max_werkstueck, saege, min_werkstueck, puffer):
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
            if verbrauch(g, f) + hinten(g, f) > laenge + EPS:
                raise AssertionError(f"{g.profil}: Werkstück überbelegt")
        if zuschnitt_belegt([l for l, _ in s], saege) > lieferlaenge + EPS:
            raise AssertionError(f"{g.profil}: Lieferstange überbelegt")


# ------------------------------------------------------------------ Profile
OFFEN = ("U-Profil", "C-Profil", "L-Profil", "Flachstahl", "I-/H-Träger", "T-Profil")


RADIUS_FORMEN = ("Quadratrohr", "Rechteckrohr")


def aussenradius(form, a, b=None, wand=None, r=None):
    """Außenradius der Ecken [mm] von Quadrat- und Rechteckrohr: r aus Stammdaten bzw. Position (Zahl ≥ 0, 0 =
    scharfkantig) oder leer = Vorgabe nach EN 10219 (2 × Wand bis 6 mm, 2,5 × Wand bis 10 mm, darüber 3 × Wand);
    höchstens die halbe kleinere Seite. Andere Formen: 0."""
    if form not in RADIUS_FORMEN or not a:
        return 0.0
    if isinstance(r, (int, float)) and not isinstance(r, bool) and r >= 0:
        wert = float(r)
    else:
        t = wand if isinstance(wand, (int, float)) and wand > 0 else 0.0
        wert = 2 * t if t <= 6 else 2.5 * t if t <= 10 else 3 * t
    return max(0.0, min(wert, min(a, b or a) / 2))


def umfang(form, a, b, wand=None, flaeche=None, pid=None, r=None):
    """Umfang des Querschnitts (Außenfläche je m Länge). Offene Profile: beide Seiten, aus Querschnittsfläche und
    Blechdicke (dünnwandig: 2 × Fläche / Dicke + 2 × Dicke an den Kanten), damit gilt es auch für C-Profile mit
    Abkantung und Profile mit Radien. RP-Profil: Außenkontur aus der RP-Bibliothek (pid = Profil-ID). Quadrat- und
    Rechteckrohr mit Außenradius (aussenradius, r = Wert der Stammdaten/Position): je Ecke (2 − π/2) × r kürzer."""
    if form == rp_profile.FORM:
        r = rp_profile.daten(pid)
        return r["umfang"] if r else 0.0
    if form == "Rundrohr":
        return math.pi * a
    if form == "Quadratrohr":
        return 4 * a - (8 - 2 * math.pi) * aussenradius(form, a, a, wand, r)
    if form == "Rechteckrohr":
        return 2 * (a + (b or a)) - (8 - 2 * math.pi) * aussenradius(form, a, b, wand, r)
    if form == "I-/H-Träger" and b:       # scharfkantig: Flansche außen und innen, Flanschkanten, Steg
        return 2 * a + 4 * b - 2 * (wand or 0)
    if form == "T-Profil" and b:
        return 2 * a + 2 * b
    if form in OFFEN and wand and flaeche:
        return 2 * flaeche / wand + 2 * wand
    if form in ovalprofile.FORMEN:      # Flachoval, Halbflachoval, Elliptisch (Plan ArTube G1)
        return ovalprofile.umfang(form, a, b)
    return 0.0


def schnittlaenge(form, a, b, wand=None, flaeche=None, pid=None, r=None):
    """Länge eines geraden Trennschnitts: Rohre = Außenumfang, offene Profile = halber Umfang (der Laser schneidet
    jede Wand nur einmal). RP-Profil: aus der Kontur, der doppelt liegende Anschlag zählt einmal (rp_profile).
    r = Außenradius von Quadrat-/Rechteckrohr (leer = Vorgabe nach Norm, aussenradius)."""
    if form == rp_profile.FORM:
        rp = rp_profile.daten(pid)
        return rp["schnitt"] if rp else 0.0
    u = umfang(form, a, b, wand, flaeche, r=r)
    return u / 2 if form in OFFEN else u


PROFILFORM = {"RR": "Rundrohr", "QR": "Quadratrohr", "RE": "Rechteckrohr", "U": "U-Profil", "C": "C-Profil",
              "L": "L-Profil", "FL": "Flachstahl", "I": "I-/H-Träger", "T": "T-Profil",
              "FO": ovalprofile.FLACHOVAL, "HFO": ovalprofile.HALBFLACHOVAL, "EL": ovalprofile.ELLIPTISCH}


def profil_aus_name(pid):
    """Profilform und Maße aus der Profil-ID, z. B. 'RR 42,4x2,0', 'QR 40x40x3', 'RE 60x40x3', 'RP 0106-35'.
    Ergebnis dict(form, a, b, wand) oder None, wenn der Name nicht nach dem Schema aufgebaut ist.
    """
    n = normprofile.daten(pid)
    if n is not None and n["flaeche"]:       # Normprofil, z. B. 'IPE 200', 'HEB 160', 'UPN 100', 'T 50'
        return dict(form=n["form"], a=n["h"], b=n["b"], wand=n["tw"], flaeche_manuell=n["flaeche"])
    r = rp_profile.daten(pid)
    if r is not None:                        # RP-Profil aus der Bibliothek, z. B. 'RP 0106-35'
        z = rp_profile.stammdaten_zeile(r)
        return dict(form=z["form"], a=z["a"], b=z["b"], wand=z["wand"], flaeche_manuell=z["flaeche_manuell"])
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
    elif form in ovalprofile.FORMEN and len(z) == 3:      # 'FO 60x30x2': Breite x Höhe x Wand (G1)
        a, b, wand = z[0], z[1], z[2]
        if not ovalprofile.gueltig(form, a, b) or wand <= 0 or 2 * wand >= b:
            return None
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
            if verbrauch(g, f) + hinten(g, f) > g.stange + EPS:
                raise AssertionError(f"{g.profil}: Stange überbelegt (mit Greiferrest bzw. 3D-Greifmaß)")
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
        if kontur_paar(g, t1, t2) and ineinander(g, t1, r1, t2, r2):
            # Kollisionsprüfung der Endkonturen (unabhängig von der Rechnung, über alle Zellpaare): eine rein optische
            # Überlappung ist nie zulässig
            from . import endkontur
            d = endkontur.kleinster_abstand(g.kontur_geo, t1.b_kontur, r1, t2.a_kontur, r2,
                                            trennung_teile(g, t1, r1, t2, r2))
            if d < kontur_abstand(g) - 1e-6:
                raise AssertionError(f"{g.profil}: Endkonturen enger als der Abstand ({d:.2f} mm)")
