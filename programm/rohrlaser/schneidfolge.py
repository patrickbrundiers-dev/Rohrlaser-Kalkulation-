"""Schneidfolge, Anschnitt und Mikrostege (Patrick 16.11.2026, Recherche 3D-Editor V1 + V2, „Alle Empfehlungen“).

V1 Schneidvorschau: in welcher Reihenfolge der Laser ein Teil schneidet, wo er an jeder Kontur ansticht, welchen
Leerweg der Kopf dazwischen fährt und wie lange jeder Schritt dauert. Gezeigt im 3D des Teile-Editors (Rohr und
Blech, damit auch aus Baugruppe, Schweißbaugruppe und Satz in 3D) Schritt für Schritt oder als Ablauf.

V2 Anschnitt und Mikrostege je Kontur (Eigenschaften der Konturzeile, gespeichert mit den Eingaben):
- folge: Platz in der Schneidfolge (1 = zuerst); leer = automatisch
- anschnitt: Stelle des Einstichs am Umriss in % des Umfangs ab dem Anfang des Umrisses; leer = automatisch (Rohr:
  mittig auf der Kontur, an der Seite zum nächsten Rohrende, Patrick 16.11.2026; Blech: die Stelle, die dem vorigen
  Einstich am nächsten liegt)
- mikrostege: Anzahl Stege, die das Abfallstück bzw. das Blechteil halten (gleichmäßig verteilt, der erste eine
  halbe Teilung hinter dem Anschnitt: mit dem mittigen Einstich liegen sie symmetrisch zur Kontur, z. B. beim
  Langloch gegenüber); steg_breite: Breite je Steg [mm], leer = Staffel nach Dicke
Kritische Enden (Rohr, Patrick 16.11.2026): ist ein Ende tiefer als 'ende_abfall_ab' (Sonderanschnitt), bekommt sein
Abfall Abfallschnitte längs, damit er in Stücken abfällt; auf Wunsch (Einstellung ende_sichern) hält je Stück ein
Mikrosteg am Ende den Abfall gegen Kollision mit dem Kopf.
Blech: dieselben Werte für die Außenkontur in eingaben['aussen_schneiden'].

Automatische Reihenfolge wie an der Maschine üblich: Rohr erst der Anfangsschnitt (Ende A), dann Gravuren, dann die
Innenkonturen von Ende A nach Ende B (gleiche Lage: um den Umfang), zuletzt der Endschnitt (Ende B, trennt das Teil
ab). Blech: Gravuren, dann Innenkonturen (zeilenweise von unten nach oben), zuletzt die Außenkontur. Eine Kontur
mit Platz (folge) steht an diesem Platz unter den Konturen; die Enden bzw. die Außenkontur bleiben außen vor.

Zeit eines Schritts = Zeit des Merkmals aus der Bearbeitungsliste (bearbeitung.py, wie die Laserzeit), bei mehreren
Konturen einer Zeile (Anzahl, Muster, Kopien) zu gleichen Teilen. Mikrostege ändern Zeit und Preis nicht (der Weg
wird um die Stegbreiten kürzer, dafür kommt Nacharbeit; beides klein). Ohne Qt."""
import math

from . import schneidweg as sw

STEG_BREITE = 0.5           # mm je Mikrosteg ohne Angabe und ohne Dicke
# Stegbreite nach Wand-/Blechdicke (Patrick 16.11.2026): bis 1,5 mm 0,3; ab 2 mm 0,5; ab 4 mm 0,7; ab 6 mm 0,8;
# ab 10 mm 1,2 mm; Einstellung steg_staffel ("ab Dicke: Breite; …")
STEG_STAFFEL = ((0.0, 0.3), (2.0, 0.5), (4.0, 0.7), (6.0, 0.8), (10.0, 1.2))
STEG_STAFFEL_TEXT = "0: 0,3; 2: 0,5; 4: 0,7; 6: 0,8; 10: 1,2"
ENDE_ABFALL_AB = 20.0       # mm: Ende tiefer -> Abfallschnitte (Einstellung ende_abfall_ab, 0 = nie)
FELDER = ("folge", "anschnitt", "mikrostege", "steg_breite", "abfall")
# Patrick 16.11.2026 19:39/19:40: große Ausschnitte (z. B. Schlitz 200 × 30) zu gleichen Teilen mit Mikrostegen
# festsetzen oder klein schneiden, so wenig Schneidweg wie nötig; Anfahrweg immer Wandstärke + 1 mm, wenn er in die
# Kontur passt, sonst Punktanfahrt. Vorbelegt, in den Einstellungen änderbar.
MIKROSTEGE, ZERSCHNEIDEN, FREI = "Mikrostege", "Zerschneiden", "frei fallen"
ABFALL_ARTEN = (MIKROSTEGE, ZERSCHNEIDEN)
ABFALL_AB = 80.0            # mm: Abfall ab dieser Länge sichern (Einstellung abfall_ab; Maschinenfeld abfall_max geht vor)
ANFAHR_ZUSCHLAG = 1.0       # mm: Anfahrweg = Wandstärke + Zuschlag (Einstellung anfahr_zuschlag)
MIKROSTEG_EINSTICH = 100.0  # %: jeder Mikrosteg = neuer Einstich (Einstellung mikrosteg_einstich)
OHNE_ABFALL = ("Gravur", "Text-Gravur", "Schlitz", "Ausklinkung", "Senkung", "Flowdrill", "V-Ausschnitt")
ENDE_A, ENDE_B, AUSSEN = "ende:a", "ende:b", "teil"


def _z(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def staffel(text):
    """Stegstaffel aus dem Text der Einstellung ("ab Dicke: Breite; …", Komma oder Punkt; eine Zahl allein = für
    alle Dicken); unlesbar oder leer -> STEG_STAFFEL."""
    if not isinstance(text, str) or not text.strip():
        return STEG_STAFFEL
    out = []
    try:
        for teil in text.replace("|", ";").split(";"):
            teil = teil.strip()
            if not teil:
                continue
            ab, _, b = teil.rpartition(":")
            ab = float(ab.lower().replace("ab", "").replace("mm", "").replace(",", ".").strip() or 0)
            b = float(b.lower().replace("mm", "").replace(",", ".").strip())
            if b > 0:
                out.append((ab, b))
    except ValueError:
        return STEG_STAFFEL
    return tuple(sorted(out)) or STEG_STAFFEL


def steg_breite(rg, wand, z=None):
    """Breite je Mikrosteg [mm]: Eingabe der Kontur, sonst nach Wand-/Blechdicke aus der Staffel."""
    b = _z((z or {}).get("steg_breite"))
    if b > 0:
        return b
    st = (rg or {}).get("steg_staffel") or STEG_STAFFEL
    b = st[0][1]
    for ab, wert in st:
        if _z(wand) >= ab - 1e-9:
            b = wert
    return b


def werte(z):
    """(folge oder None, anschnitt in % oder None, Anzahl Mikrostege, Stegbreite mm) einer Konturzeile bzw. der
    Außenkontur (dict mit den FELDERN)."""
    z = z or {}
    folge = int(_z(z.get("folge"))) if _z(z.get("folge")) >= 1 else None
    an = z.get("anschnitt")
    an = (_z(an) % 100.0) if isinstance(an, (int, float)) and not isinstance(an, bool) else None
    n = max(0, int(_z(z.get("mikrostege"))))
    b = _z(z.get("steg_breite")) or STEG_BREITE
    return folge, an, n, b


def regel(einst=None, m=None):
    """Vorgaben für Anfahrweg und Abfall: dict(anfahr_zuschlag, anfahr_fest (Maschinenfeld 'anfahrweg' oder None),
    abfall_art, abfall_ab, steg_staffel, mikrosteg_anteil (Anteil der Einstichzeit je Mikrosteg),
    steg_abstand (größter Abstand der Mikrostege [mm], 0 = 2 × abfall_ab), ende_abfall_ab, ende_sichern) aus den
    Einstellungen und der Maschine."""
    einst, m = einst or {}, m or {}
    zuschlag = einst.get("anfahr_zuschlag")
    art = einst.get("abfall_art")
    fest = _z(m.get("anfahrweg"))
    ms = einst.get("mikrosteg_einstich")
    ea = einst.get("ende_abfall_ab")
    return dict(anfahr_zuschlag=_z(zuschlag) if isinstance(zuschlag, (int, float)) else ANFAHR_ZUSCHLAG,
                anfahr_fest=fest if fest > 0 else None,
                abfall_art=art if art in ABFALL_ARTEN else MIKROSTEGE,
                abfall_ab=_z(m.get("abfall_max")) or _z(einst.get("abfall_ab")) or ABFALL_AB,
                steg_staffel=staffel(einst.get("steg_staffel")),
                mikrosteg_anteil=(_z(ms) if isinstance(ms, (int, float)) else MIKROSTEG_EINSTICH) / 100,
                steg_abstand=_z(einst.get("steg_abstand")),
                ende_abfall_ab=_z(ea) if isinstance(ea, (int, float)) else ENDE_ABFALL_AB,
                ende_sichern=einst.get("ende_sichern") == "ja")


TEIL = "teil_schneiden"      # Eingaben: Vorgaben je Teil (Patrick 16.11.2026: je Teil ein-/aus-/umstellen)
TEIL_FELDER = ("abfall", "ende_abfall", "ende_sichern")


def mit_teil(rg, e):
    """Regel mit den Vorgaben des Teils (e['teil_schneiden']): abfall = Mikrostege/Zerschneiden (Art für große
    Ausschnitte) oder frei fallen (kein Sichern); ende_abfall ja/nein (Abfallschnitte an kritischen Enden; ja bei
    Einstellung 0 = 20 mm); ende_sichern ja/nein. Leer = Einstellung. Eine Vorgabe der Kontur geht vor."""
    rg = dict(rg or regel())
    t = (e or {}).get(TEIL) if isinstance((e or {}).get(TEIL), dict) else {}
    if not t or rg.get("_teil"):
        return rg
    rg["_teil"] = True
    if t.get("abfall") in ABFALL_ARTEN:
        rg["abfall_art"], rg["teil_abfall"] = t["abfall"], t["abfall"]
    elif t.get("abfall") == FREI:
        rg["teil_abfall"] = FREI
    if t.get("ende_abfall") == "nein":
        rg["ende_abfall_ab"] = 0.0
    elif t.get("ende_abfall") == "ja" and not rg.get("ende_abfall_ab"):
        rg["ende_abfall_ab"] = ENDE_ABFALL_AB
    if t.get("ende_sichern") in ("ja", "nein"):
        rg["ende_sichern"] = t["ende_sichern"] == "ja"
    return rg


def masse(z):
    """(Länge, Breite) des Abfalls einer Konturzeile [mm]: Hüllrechteck des Umrisses (skizze.umriss_kontur), längere
    Seite zuerst; Lochfeld je Loch; None ohne Maße."""
    from . import skizze as sk
    z = z or {}
    if z.get("art") == "Lochfeld":
        d_, l_ = _z(z.get("d")), _z(z.get("lang"))
        return (max(d_, l_), d_) if d_ > 0 else None
    if z.get("art") in ("Bohrung",) and _z(z.get("d")) > 0:
        return _z(z.get("d")), _z(z.get("d"))
    try:
        pts = sk.umriss_kontur(z)
    except (ValueError, TypeError, KeyError, ZeroDivisionError):
        pts = None
    if not pts or len(pts) < 3:
        return None
    a = max(p[0] for p in pts) - min(p[0] for p in pts)
    b = max(p[1] for p in pts) - min(p[1] for p in pts)
    return (max(a, b), min(a, b)) if a > 0 and b > 0 else None


def anfahrweg(z, wand, rg=None):
    """Anfahrweg einer Innenkontur [mm]: Maschinenfeld 'anfahrweg' (fest) oder Wandstärke + Zuschlag; 0 =
    Punktanfahrt, wenn er nicht in die Kontur passt (halbe Breite des Abfalls kleiner) oder ohne Abfall (Gravur,
    Schlitz, Ausklinkung)."""
    rg = rg or regel()
    if (z or {}).get("art") in OHNE_ABFALL:
        return 0.0
    weg = rg["anfahr_fest"] if rg.get("anfahr_fest") else _z(wand) + rg["anfahr_zuschlag"]
    mm = masse(z)
    if weg <= 0 or mm is None or mm[1] / 2 < weg - 1e-9:
        return 0.0
    return weg


def abfall(z, rg=None, umfang=None):
    """Was mit dem Abfall einer Innenkontur geschieht: dict(art (Mikrostege, Zerschneiden oder None), stege (Anzahl),
    schnitte [(Anzahl, Länge je Schnitt [mm], längs)]). Eigenschaft 'abfall' der Kontur geht vor (frei fallen = nichts),
    sonst Einstellung ab Länge abfall_ab. Mikrostege gleichmäßig: einer je angefangene 2 × abfall_ab Umfang, mindestens
    2; eine eingetragene Anzahl Mikrostege gilt. Zerschneiden: so wenige Querschnitte wie nötig, damit kein Stück länger
    als abfall_ab ist (Schlitz 200 × 30 bei 80 mm: 2 Schnitte je 30 mm)."""
    rg = rg or regel()
    z = z or {}
    n_hand = max(0, int(_z(z.get("mikrostege"))))
    wahl = z.get("abfall") or ""
    leer = dict(art=None, stege=0, schnitte=[])
    if n_hand:
        return dict(leer, art=MIKROSTEGE, stege=n_hand)
    if wahl == FREI or z.get("art") in OHNE_ABFALL or (not wahl and rg.get("teil_abfall") == FREI):
        return leer
    mm = masse(z)
    g = rg["abfall_ab"]
    if mm is None or g <= 0 or (mm[0] <= g + 1e-9 and wahl not in ABFALL_ARTEN):
        return leer
    art = wahl if wahl in ABFALL_ARTEN else rg["abfall_art"]
    lang, quer = mm
    if art == MIKROSTEGE:
        u = umfang if umfang else 2 * (lang + quer)
        teilung = rg.get("steg_abstand") or 2 * g
        return dict(leer, art=MIKROSTEGE, stege=max(2, math.ceil(u / teilung - 1e-9)))
    schnitte = []
    n_l = max(0, math.ceil(lang / g - 1e-9) - 1)
    if n_l:
        schnitte.append((n_l, quer, False))
    n_q = max(0, math.ceil(quer / g - 1e-9) - 1)
    if n_q:
        schnitte.append((n_q, lang, True))
    return dict(leer, art=ZERSCHNEIDEN, schnitte=schnitte) if schnitte else leer


def zerschneiden_mm(z, rg=None):
    """(Anzahl Schnitte, Schnittlänge [mm]) zum Zerschneiden des Abfalls einer Konturzeile je Kontur."""
    a = abfall(z, rg)
    if a["art"] != ZERSCHNEIDEN:
        return 0, 0.0
    return sum(n for n, _, _ in a["schnitte"]), sum(n * lg for n, lg, _ in a["schnitte"])


def mikrostege_n(z, rg=None):
    """Mikrostege einer Konturzeile je Kontur (Patrick 16.11.2026: nach jedem Steg setzt der Laser im vollen Material
    neu an = neuer Einstich)."""
    a = abfall(z, rg)
    return a["stege"] if a["art"] == MIKROSTEGE else 0


def tour(n, kosten, start=None, ende=None):
    """Reihenfolge der Knoten 0 … n−1 mit kleinen Gesamtkosten (nächster Nachbar, dann 2-opt): kosten(i, j) zwischen
    Knoten, start(j) vom Anfang zum Knoten, ende(i) vom Knoten zum Ende (None = 0)."""
    if n <= 1:
        return list(range(n))
    s = start or (lambda j: 0.0)
    e = ende or (lambda i: 0.0)
    frei, weg = set(range(n)), []
    akt = min(frei, key=s)
    while True:
        weg.append(akt)
        frei.discard(akt)
        if not frei:
            break
        akt = min(frei, key=lambda j, a=akt: (kosten(a, j), j))
    if n > 300:
        return weg

    def c(i, j):        # Kante zwischen Position i und j; −1 = Anfang, n = Ende (Kosten symmetrisch)
        if i < 0:
            return s(weg[j])
        if j >= n:
            return e(weg[i])
        return kosten(weg[i], weg[j])
    besser, runden = True, 0
    while besser and runden < 50:
        besser, runden = False, runden + 1
        for i in range(0, n - 1):
            for k in range(i + 1, n):
                alt = c(i - 1, i) + c(k, k + 1)
                neu = (s(weg[k]) if i == 0 else kosten(weg[i - 1], weg[k])) + \
                    (e(weg[i]) if k == n - 1 else kosten(weg[i], weg[k + 1]))
                if neu + 1e-9 < alt:
                    weg[i:k + 1] = weg[i:k + 1][::-1]
                    besser = True
    return weg


def zuege(netz, blech=False):
    """Linienzüge je Merkmal aus dem Netz der 3D-Ansicht: {Merkmal-ID: [[(x, y, z), …], …]} (Konturen, Gravuren,
    Enden; Blech: je Kontur nur die obere Seite, Außenkontur aus geo['aussen'])."""
    out = {}
    kennung = (netz or {}).get("li") or {}
    for art, liste in ((netz or {}).get("l") or {}).items():
        if art not in ("K", "G", "EA", "EB"):
            continue
        ids = kennung.get(art) or []
        for nr, zug in enumerate(liste):
            kn = ids[nr] if nr < len(ids) else None
            if not kn:
                continue
            pk = [tuple(zug[i:i + 3]) for i in range(0, len(zug) - 2, 3)]
            if len(pk) >= 2:
                out.setdefault(kn, []).append(pk)
    geo = (netz or {}).get("geo") or {}
    if blech and geo.get("zuege"):      # blech3d: je Kontur die Züge der oberen Seite
        out = {kn: [list(pk) for pk in zz] for kn, zz in geo["zuege"].items()}
    elif blech:     # ohne: jede Kontur oben und unten (Text-Gravur nur oben) -> die obere
        for kn, zz in out.items():
            if len(zz) % 2 == 0 and len(zz) >= 2 and all(len(zz[i]) == len(zz[i + 1]) for i in range(0, len(zz), 2)):
                out[kn] = zz[0::2]
    if blech:
        a = geo.get("aussen")
        if a and len(a) >= 2:
            out[AUSSEN] = [[tuple(p) for p in a]]
    return out


def _laenge(pk):
    return sum(math.dist(a, b) for a, b in zip(pk, pk[1:]))


def punkt_bei(pk, s):
    """Punkt auf dem Linienzug pk nach der Bogenlänge s (über das Ende hinaus: weiter von vorn, geschlossen)."""
    lg = _laenge(pk)
    if lg <= 0:
        return pk[0]
    s %= lg
    for a, b in zip(pk, pk[1:]):
        d = math.dist(a, b)
        if s <= d and d > 0:
            t = s / d
            return tuple(a[i] + t * (b[i] - a[i]) for i in range(3))
        s -= d
    return pk[-1]


def _stueck(pk, s0, s1, n=6):
    return [punkt_bei(pk, s0 + (s1 - s0) * k / n) for k in range(n + 1)]


def _naechste(pk, q):
    """Bogenlänge des Punkts auf pk, der q am nächsten liegt."""
    beste, s, ab = (None, 0.0), 0.0, None
    for a, b in zip(pk, pk[1:]):
        d = math.dist(a, b)
        if d > 0:
            t = max(0.0, min(1.0, sum((q[i] - a[i]) * (b[i] - a[i]) for i in range(3)) / (d * d)))
            p = tuple(a[i] + t * (b[i] - a[i]) for i in range(3))
            w = math.dist(p, q)
            if ab is None or w < ab:
                ab, beste = w, (p, s + t * d)
        s += d
    return beste[1]


def einstich_mitte(pk, laenge):
    """Bogenlänge des Einstichs einer Rohrkontur (Patrick 16.11.2026): mittig auf der Kontur (wo der Umriss die Linie
    längs durch ihre Mitte kreuzt) und von diesen Stellen die mit dem kleinsten Abstand zum nächsten Rohrende."""
    lg = _laenge(pk)
    if lg <= 0 or len(pk) < 3:
        return 0.0
    c = _mitte([pk])
    wc = math.atan2(c[1], -c[0])

    def quer(p):        # Abstand von der Mittellinie am Umfang, mit Vorzeichen
        return math.hypot(p[0], p[1]) * ((math.atan2(p[1], -p[0]) - wc + math.pi) % (2 * math.pi) - math.pi)
    L = _z(laenge)

    def ende_ab(p):
        return min(p[2], L - p[2]) if L > 0 else p[2]
    kreuz, s = [], 0.0
    for a, b in zip(pk, pk[1:]):
        d = math.dist(a, b)
        qa, qb = quer(a), quer(b)
        if d > 0 and qa * qb <= 0 and qa != qb:
            t = qa / (qa - qb)
            p = tuple(a[i] + t * (b[i] - a[i]) for i in range(3))
            kreuz.append((ende_ab(p), s + t * d))
        s += d
    if kreuz:
        return min(kreuz)[1]
    proben = [(abs(quer(punkt_bei(pk, lg * k / 144))), lg * k / 144) for k in range(144)]
    return min(proben)[1]


def ende_sonder(es):
    """Ende mit gemessenem Umriss (Sonderanschnitt aus der STEP): kann kritischen Abfall haben. Gerade Enden und
    Gehrungen nicht (Gehrungen liegen im Schnittplan ineinander, dazwischen nur der Teileabstand)."""
    if not isinstance(es, dict):
        return False
    return bool(es.get("umriss") and not _z(es.get("winkel"))) or bool(_z(es.get("sattel"))) or bool(es.get("gegen"))


def ende_abfall(pk, mid, rg, wand=0.0, n_proben=360):
    """Abfallschnitte eines kritischen Endes (Rohr, Achse z; Patrick 16.11.2026: quer am Umfang durch den Abfall):
    ist das Ende tiefer als rg['ende_abfall_ab'], laufen Schnitte quer zur Achse rund um das Rohr durch den Abfall
    zwischen Ende und der Ebene an seiner tiefsten Stelle, gleich verteilt über die Tiefe, so dass kein Stück
    länger als abfall_ab ist (mindestens einer). Jeder Querschnitt läuft von Endschnitt zu Endschnitt, nur wo Abfall
    ist; das Stück zwischen Querschnitt und Ende ist damit ganz frei. Mit ende_sichern hält je Querschnitt ein
    Mikrosteg in seiner Mitte den Abfall am Reststück: der Endschnitt bleibt ganz, das Teil fällt zu 100 % ab, nur
    der Abfall hängt und kippt nicht gegen den Kopf. Ergebnis dict(schnitte [[Punkte]] (Linienzüge), mm,
    stege [[Punkte]], tiefe) oder None."""
    if not pk or len(pk) < 3 or mid not in (ENDE_A, ENDE_B):
        return None
    zs = [p[2] for p in pk]
    tiefe = max(zs) - min(zs)
    grenze = rg.get("ende_abfall_ab") or 0.0
    if grenze <= 0 or tiefe < grenze - 1e-9:
        return None
    ebene = min(zs) if mid == ENDE_A else max(zs)
    richtung = 1.0 if mid == ENDE_A else -1.0          # von der Ebene zum Teil hin
    lg = _laenge(pk)
    g = rg.get("abfall_ab") or ABFALL_AB
    b = steg_breite(rg, wand)
    proben = [punkt_bei(pk, lg * k / n_proben) for k in range(n_proben)]
    n = max(1, math.ceil(tiefe / g - 1e-9) - 1)
    schnitte, mm, stege = [], 0.0, []
    for i in range(n):
        h = tiefe * (i + 1) / (n + 1)       # Abstand des Querschnitts von der Ebene
        zc = ebene + richtung * h
        drin = [abs(p[2] - ebene) > h + 1e-6 for p in proben]      # dort liegt Abfall auf Höhe zc
        if not any(drin):
            continue
        k0 = drin.index(False) if not all(drin) else 0
        zug, zuege_ = [], []
        for j in range(n_proben + (0 if all(drin) else 1)):
            k = (k0 + j) % n_proben
            if drin[k]:
                zug.append((proben[k][0], proben[k][1], zc))
            elif zug:
                zuege_.append(zug)
                zug = []
        if zug:
            if all(drin):
                zug.append(zug[0])          # rund um das Rohr: geschlossen
            zuege_.append(zug)
        for zg in zuege_:
            if len(zg) < 2:
                continue
            lz = _laenge(zg)
            schnitte.append(zg)
            mm += lz
            if rg.get("ende_sichern") and lz > b:
                stege.append(_stueck(zg, lz / 2 - b / 2, lz / 2 + b / 2, 2))
    if not schnitte:
        return None
    return dict(schnitte=schnitte, mm=mm, stege=stege, tiefe=tiefe)


def reihenfolge(e, art="rohr"):
    """Merkmal-IDs in Schneidfolge (siehe Modulkopf): [(Merkmal-ID, Konturzeile oder None)]."""
    from . import skizze as sk
    konturen = list((e or {}).get("konturen") or ())
    grav, rest = [], []
    if art == "rohr":
        lagen = {}
        for d in sk.lagen(konturen, _z((e or {}).get("laenge")) or 1000.0):
            lagen.setdefault(d["zeile"], d["x"] if d["x"] is not None else 0.0)
        for j, z in enumerate(konturen):
            if not z.get("art"):
                continue
            key = (_z(lagen.get(j)), sk.winkel_aus_text(z.get("seite")) or 0.0, j)
            (grav if z.get("art") in sw.GRAVUREN else rest).append((key, j))
    else:
        for j, z in enumerate(konturen):
            if not z.get("art"):
                continue
            key = (round(_z(z.get("y")), 1), _z(z.get("x")), j)
            (grav if z.get("art") in sw.GRAVUREN else rest).append((key, j))
    auto = [j for _, j in sorted(grav)] + [j for _, j in sorted(rest)]
    fest = sorted(((werte(konturen[j])[0], j) for j in auto if werte(konturen[j])[0]), key=lambda x: x)
    ohne = [j for j in auto if not werte(konturen[j])[0]]
    for platz, j in fest:
        ohne.insert(min(platz - 1, len(ohne)), j)
    mitte = [(f"kontur:{j}", j) for j in ohne]
    if art == "rohr":
        return [(ENDE_A, None)] + mitte + [(ENDE_B, None)]
    return mitte + [(AUSSEN, None)]


def _mitte(pks):
    q = [p for pk in pks for p in pk]
    return tuple(sum(p[i] for p in q) / len(q) for i in range(3))


def abstand(p, q, art="rohr"):
    """Leerweg zwischen zwei Punkten [mm]: Rohr längs (Achse z) plus Bogen um die Achse (der Kopf fährt längs, das
    Rohr dreht), Blech gerade."""
    if art != "rohr":
        return math.dist(p, q)
    wp, wq = math.atan2(p[1], -p[0]), math.atan2(q[1], -q[0])
    dw = abs((wq - wp + math.pi) % (2 * math.pi) - math.pi)
    r = (math.hypot(p[0], p[1]) + math.hypot(q[0], q[1])) / 2
    return abs(q[2] - p[2]) + r * dw


def _schnitt_linien(pk, n, quer=False):
    """n Schnitte quer durch den Abfall innerhalb des Linienzugs pk, gleichmäßig längs seiner langen (quer=True:
    kurzen) Achse: [[a, b]]."""
    if n <= 0 or len(pk) < 3:
        return []
    c = _mitte([pk])
    p0 = max(pk, key=lambda p: math.dist(p, c))
    p1 = max(pk, key=lambda p: math.dist(p, p0))
    u = [p1[i] - p0[i] for i in range(3)]
    lu = math.hypot(*u) or 1.0
    u = [x / lu for x in u]
    if quer:
        def senk(p):
            d = [p[i] - c[i] for i in range(3)]
            t = sum(d[i] * u[i] for i in range(3))
            return [d[i] - t * u[i] for i in range(3)]
        w = senk(max(pk, key=lambda p: math.hypot(*senk(p))))
        lw = math.hypot(*w) or 1.0
        u = [x / lw for x in w]
    ts = [sum((p[i] - c[i]) * u[i] for i in range(3)) for p in pk]
    t0, t1 = min(ts), max(ts)
    out = []
    for k in range(1, n + 1):
        t = t0 + (t1 - t0) * k / (n + 1)
        treff = []
        for a, b, ta, tb in zip(pk, pk[1:], ts, ts[1:]):
            if (ta - t) * (tb - t) <= 0 and ta != tb:
                f = (t - ta) / (tb - ta)
                treff.append(tuple(a[i] + f * (b[i] - a[i]) for i in range(3)))
        if len(treff) >= 2:
            a = treff[0]
            b = max(treff, key=lambda q: math.dist(q, a))
            out.append([a, b])
    return out


def schritte(e, netz, art="rohr", zeiten=None, rg=None, wand=None, optimieren=True):
    """Schritte der Schneidvorschau: [dict(nr, mid, text, punkte (Linienzüge), start (Einstich), anfahrt (Linie vom
    Einstich auf dem Abfall zur Kontur oder None = Punktanfahrt), anfahr_mm, stege [[Punkte]], schnitte [[a, b]]
    (Abfall zerschneiden), abfall (Art), s (Zeit [s] oder None), leer (Leerweg vom vorigen Einstich [mm]), gravur)].
    zeiten = {Merkmal-ID: Sekunden}, rg = regel(), wand = Wand- bzw. Blechdicke [mm]. optimieren: Reihenfolge mit
    kürzesten Leerwegen (Gravuren zuerst, Konturen dazwischen, Endschnitt bzw. Außenkontur zuletzt; Konturen mit Platz
    stehen an ihrem Platz), sonst Ende A nach B wie reihenfolge()."""
    rg = mit_teil(rg, e)
    if wand is None:
        wand = _z((e or {}).get("dicke"))
    zz = zuege(netz, blech=art != "rohr")
    konturen = list((e or {}).get("konturen") or ())
    einheiten = []
    for mid, j in reihenfolge(e, art):
        linien = zz.get(mid)
        if not linien:
            continue
        z = konturen[j] if j is not None else ((e or {}).get("aussen_schneiden") or {}) if mid == AUSSEN else {}
        gravur = j is not None and z.get("art") in sw.GRAVUREN
        if mid in (ENDE_A, ENDE_B, AUSSEN):
            linien = linien[:1]
            text = {ENDE_A: "Anfangsschnitt (Ende A)", ENDE_B: "Endschnitt (Ende B, trennt ab)",
                    AUSSEN: "Außenkontur (trennt ab)"}[mid]
        else:
            text = _text(z)
        teile = [linien] if gravur else [[pk] for pk in linien]
        for k, pks in enumerate(teile):
            einheiten.append(dict(mid=mid, j=j, z=z, pks=pks, gravur=gravur, k=k, n=len(teile), text=text,
                                  mitte=_mitte(pks)))
    if optimieren and einheiten:
        einheiten = _optimiert(einheiten, art)
    out, vorher = [], None
    for x in einheiten:
        mid, z, pks, gravur = x["mid"], x["z"], x["pks"], x["gravur"]
        pk = pks[0]
        lg = _laenge(pk)
        _, an, _, b = werte(z)
        b = steg_breite(rg, wand, z)
        if an is not None:
            s0 = lg * an / 100.0
        elif art == "rohr" and x["j"] is not None and not gravur:
            s0 = einstich_mitte(pk, _z((e or {}).get("laenge")) or max(p[2] for p in pk))
        elif vorher is not None and not gravur and mid != ENDE_A:
            s0 = _naechste(pk, vorher)
        else:
            s0 = 0.0
        start = punkt_bei(pk, s0)
        innen = x["j"] is not None and not gravur
        af = abfall(z, rg) if innen or mid == AUSSEN else dict(art=None, stege=0, schnitte=[])
        if (mid == AUSSEN or art != "rohr") and not _z(z.get("mikrostege")) and not z.get("abfall") and \
                not (mid != AUSSEN and rg.get("teil_abfall") in ABFALL_ARTEN):
            af = dict(art=None, stege=0, schnitte=[])        # Blech: fällt durch den Rost, Stege nur von Hand
        n = af["stege"]
        stege = []
        if n and lg > 0:
            for i in range(n):
                sm = s0 + lg * (i + 0.5) / n
                stege.append(_stueck(pk, sm - b / 2, sm + b / 2, 2))
        schnitte = []
        for n_s, _, quer in af["schnitte"]:
            schnitte += _schnitt_linien(pk, n_s, quer)
        ea = ende_abfall(pk, mid, rg, wand) if art == "rohr" and mid in (ENDE_A, ENDE_B) and \
            ende_sonder((e or {}).get(mid[-1])) else None
        if ea:
            schnitte += ea["schnitte"]
            stege += ea["stege"]
        weg = anfahrweg(z, wand, rg) if innen else (
            (rg["anfahr_fest"] or _z(wand) + rg["anfahr_zuschlag"]) if mid == AUSSEN else 0.0)
        anfahrt = None
        if weg > 0:
            c = x["mitte"]
            d = [c[i] - start[i] for i in range(3)]
            ld = math.hypot(*d)
            if ld > 1e-9:
                f = (min(weg, ld) if innen else -weg) / ld
                anfahrt = [tuple(start[i] + f * d[i] for i in range(3)), start]
        t_mid = (zeiten or {}).get(mid)
        tx = x["text"] if x["n"] == 1 else f"{x['text']} ({x['k'] + 1} von {x['n']})"
        out.append(dict(nr=len(out) + 1, mid=mid, text=tx, punkte=pks, start=start, anfahrt=anfahrt,
                        anfahr_mm=weg if anfahrt else 0.0, stege=stege, schnitte=schnitte, abfall=af["art"],
                        s=(t_mid / x["n"]) if isinstance(t_mid, (int, float)) else None,
                        leer=abstand(vorher, start, art) if vorher is not None else 0.0, gravur=gravur,
                        stege_n=(n if stege else 0) + (len(ea["stege"]) if ea else 0), steg_breite=b,
                        ende_n=len(ea["schnitte"]) if ea else 0))
        vorher = start
    return out


def _optimiert(einheiten, art):
    """Einheiten in Schneidfolge mit kurzen Leerwegen (tour): Anfang (Ende A) und Schluss (Ende B, Außenkontur)
    bleiben, Gravuren vor den Konturen, Konturzeilen mit Platz (folge) als Block an ihrem Platz."""
    kopf = [x for x in einheiten if x["mid"] == ENDE_A]
    schluss = [x for x in einheiten if x["mid"] in (ENDE_B, AUSSEN)]
    mitte = [x for x in einheiten if x["mid"] not in (ENDE_A, ENDE_B, AUSSEN)]
    fest = [x for x in mitte if werte(x["z"])[0]]
    frei = [x for x in mitte if not werte(x["z"])[0]]

    def gruppe(liste, von, nach):
        if not liste:
            return []
        d = lambda i, j: abstand(liste[i]["mitte"], liste[j]["mitte"], art)  # noqa: E731
        s = (lambda j: abstand(von, liste[j]["mitte"], art)) if von is not None else None
        e = (lambda i: abstand(liste[i]["mitte"], nach, art)) if nach is not None else None
        return [liste[i] for i in tour(len(liste), d, s, e)]
    von = kopf[0]["mitte"] if kopf else None
    nach = schluss[0]["mitte"] if schluss else None
    grav = gruppe([x for x in frei if x["gravur"]], von, None)
    rest = [x for x in frei if not x["gravur"]]
    folge = grav + gruppe(rest, grav[-1]["mitte"] if grav else von, nach)
    platz_von = {x["j"]: werte(x["z"])[0] for x in fest}
    for j in sorted(platz_von, key=lambda j: (platz_von[j], j)):
        platz = platz_von[j]
        block = [y for y in fest if y["j"] == j]
        gesehen, pos = set(), len(folge)
        for i, y in enumerate(folge):
            if len(gesehen) >= platz - 1 and y["j"] not in gesehen:
                pos = i
                break
            gesehen.add(y["j"])
        folge[pos:pos] = block
    return kopf + folge + schluss


def _text(z):
    """Kurztext einer Konturzeile: Art und Maße (skizze.kurz), die Art nicht doppelt."""
    from . import skizze as sk
    k, art = sk.kurz(z) or "", z.get("art") or ""
    return k if not art or k.startswith(art) else f"{art} {k}".strip()


def summen(liste, bis=None):
    """(Zeit [s] bis einschließlich Schritt bis (Index; None = alle), Zeit gesamt, Leerweg gesamt [mm])."""
    ges = sum(_z(x.get("s")) for x in liste)
    bis_s = ges if bis is None else sum(_z(x.get("s")) for x in liste[:bis + 1])
    return bis_s, ges, sum(_z(x.get("leer")) for x in liste)


def text_schritt(liste, i):
    """Zeile über dem 3D für Schritt i (Index) bzw. die Übersicht (i None)."""
    from .rechnen import zahl
    bis, ges, leer = summen(liste, i)
    zeit = any(x.get("s") is not None for x in liste)
    if i is None or not 0 <= i < len(liste):
        return (f"Schneidvorschau: {len(liste)} Schritte" + (f" · {zahl(ges, 1)} s" if zeit else "") +
                f" · Leerweg {zahl(leer, 0)} mm – ◀ ▶ Schritt, ▶▶ Ablauf")
    x = liste[i]
    t = f" · {zahl(x['s'], 1)} s" if x.get("s") is not None else ""
    st = f" · {x['stege_n']} Mikrosteg{'e' if x['stege_n'] != 1 else ''}" if x.get("stege_n") else ""
    if x.get("ende_n"):
        st += f" · {x['ende_n']} Abfallschnitt{'e' if x['ende_n'] != 1 else ''} am Ende"
    elif x.get("schnitte"):
        st += f" · Abfall in {len(x['schnitte']) + 1} Stücke geschnitten"
    if x.get("anfahr_mm"):
        st += f" · Anfahrweg {zahl(x['anfahr_mm'], 1)} mm"
    elif x.get("mid", "").startswith("kontur:") and not x.get("gravur"):
        st += " · Punktanfahrt"
    return (f"Schritt {i + 1} von {len(liste)}: {x['text']}{t}{st} · Leerweg {zahl(x['leer'], 0)} mm" +
            (f" · bisher {zahl(bis, 1)} s von {zahl(ges, 1)} s" if zeit else ""))


def tabelle(e, art="rohr", netz=None, rg=None, wand=None):
    """Schneidfolge für das CAM-Paket: [dict(nr, merkmal, art, text, anzahl, anschnitt, anfahrweg, abfall, mikrostege,
    steg_breite)] je Merkmal (Konturzeile, Enden bzw. Außenkontur). Mit Netz in der Folge der Schneidvorschau
    (kürzeste Leerwege), sonst Ende A nach B."""
    rg = mit_teil(rg, e)
    if wand is None:
        wand = _z((e or {}).get("dicke"))
    konturen = list((e or {}).get("konturen") or ())
    folge, enden = [], {}
    if netz:
        for x in schritte(e, netz, art, rg=rg, wand=wand):
            if x["mid"] not in folge:
                folge.append(x["mid"])
            if x.get("ende_n"):
                enden[x["mid"]] = x
    for mid, _ in reihenfolge(e, art):
        if mid not in folge:
            folge.append(mid)
    out = []
    for mid in folge:
        j = int(mid.split(":")[1]) if mid.startswith("kontur:") else None
        z = konturen[j] if j is not None else ((e or {}).get("aussen_schneiden") or {}) if mid == AUSSEN else {}
        _, an, _, b = werte(z)
        b = steg_breite(rg, wand, z)
        if j is None:
            text = {ENDE_A: "Anfangsschnitt", ENDE_B: "Endschnitt", AUSSEN: "Außenkontur"}[mid]
            kart, anz = "", 1
            af = dict(art=MIKROSTEGE, stege=int(_z(z.get("mikrostege"))), schnitte=[]) \
                if mid == AUSSEN and _z(z.get("mikrostege")) else dict(art=None, stege=0, schnitte=[])
            weg = (rg["anfahr_fest"] or _z(wand) + rg["anfahr_zuschlag"]) if mid == AUSSEN else 0.0
        else:
            kart, text = z.get("art") or "", _text(z)
            anz = int(_z(z.get("anzahl")) or 1)
            af = abfall(z, rg) if art == "rohr" or z.get("abfall") or _z(z.get("mikrostege")) else \
                dict(art=None, stege=0, schnitte=[])
            weg = anfahrweg(z, wand, rg) if kart not in sw.GRAVUREN else 0.0
        if af["art"] == MIKROSTEGE:
            atext = f"{af['stege']} Mikrostege"
        elif af["art"] == ZERSCHNEIDEN:
            k = sum(n for n, _, _ in af["schnitte"])
            atext = f"zerschneiden: {k} Schnitt{'e' if k != 1 else ''}, {k + 1} Stücke"
        else:
            atext = ""
        if mid in enden:        # kritisches Ende: Abfallschnitte, ggf. mit Mikrostegen gesichert
            x = enden[mid]
            atext = f"{x['ende_n']} Abfallschnitt{'e' if x['ende_n'] != 1 else ''}"
            if x["stege_n"]:
                af = dict(af, stege=x["stege_n"])
                atext += f", gesichert mit {x['stege_n']} Mikrosteg{'en' if x['stege_n'] != 1 else ''} (Teil fällt ganz ab)"
        out.append(dict(nr=len(out) + 1, merkmal=mid, art=kart, text=text, anzahl=anz,
                        anschnitt="automatisch" if an is None else f"{an:g} %".replace(".", ","),
                        anfahrweg=("" if kart in sw.GRAVUREN or mid in (ENDE_A, ENDE_B) else
                                   f"{weg:g} mm".replace(".", ",") if weg > 0 else "Punkt"),
                        abfall=atext, mikrostege=af["stege"], steg_breite=b if af["stege"] else None))
    return out


def hat_vorgaben(e):
    """True, wenn eine Kontur oder die Außenkontur Platz, Anschnitt oder Mikrostege vorgibt."""
    zs = list((e or {}).get("konturen") or ()) + [(e or {}).get("aussen_schneiden") or {}]
    return any(z.get(k) not in (None, "", 0) for z in zs if isinstance(z, dict) for k in FELDER)
