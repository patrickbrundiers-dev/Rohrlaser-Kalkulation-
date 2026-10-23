"""Fertigungsprüfung (DFM) für Rohr und Blech (Plan S5, Abschnitt 5.6): eine Regeltabelle (Stammdaten
'pruefregeln'), jede Regel einzeln an- oder abschaltbar, mit Grenzwert und Stufe HINWEIS, WARNUNG oder FEHLER.
Die Befunde nennen die Lage am Teil (x ab Ende A und Seite bzw. x/y im Zuschnitt).

Regeln (Vorgaben sind Startwerte, bitte an die eigene Fertigung anpassen):
  Bohrung zu klein        Bohrung bzw. Senkung Ø kleiner als Faktor × Wandstärke bzw. Blechdicke (1,0, WARNUNG)
  Steg zu schmal          Abstand zwischen zwei Konturen kleiner als Faktor × Wand (1,5, WARNUNG)
  Kontur zu nah am Rand   Kontur näher am Ende bzw. an der Blechkante als Faktor × Wand (1,0, WARNUNG); Schlitze
                          und Ausklinkungen sind zum Ende offen und zählen nicht
  Teil zu kurz            Teil kürzer als 'Kürzestes Teil' der Maschine (FEHLER, leer = keine Grenze)
  Gravur über Kante       Gravur über mehrere Flächen des Profils (WARNUNG)
  Kantbarkeit             Hinweise der Kantbarkeit (blech.kantbarkeit, Faktoren in den Einstellungen) (HINWEIS)

Geometrie: jede Kontur mit Lage als Linienzug (skizze.umriss_kontur) auf der Abwicklung des Rohrs (x längs,
s am Umfang, skizze.s_lage) bzw. im Zuschnitt (x, y); Steg = kleinster Abstand zweier Linienzüge, Rand = Abstand
zu x = 0 und x = Länge bzw. zur Außenkontur des Zuschnitts. Konturen ohne Lage zählen nur bei 'Bohrung zu klein'.
Gehrungen und schräge Enden rechnen mit dem Ende bei x = 0 bzw. x = Länge."""
import functools
import math

HINWEIS, WARNUNG, FEHLER = "HINWEIS", "WARNUNG", "FEHLER"
STUFEN = (HINWEIS, WARNUNG, FEHLER)
BOHRUNG_KLEIN, STEG, RAND, KURZ, GRAVUR_KANTE, KANTBARKEIT = (
    "Bohrung zu klein", "Steg zu schmal", "Kontur zu nah am Rand", "Teil zu kurz für die Maschine",
    "Gravur über Kante", "Kantbarkeit")
# Regel: (Grenzwert, Stufe, Beschreibung) – Vorgaben und Beispielzeilen der Tabelle
REGELN = {
    BOHRUNG_KLEIN: (1.0, WARNUNG, "Bohrung bzw. Senkung Ø kleiner als Grenzwert × Wandstärke bzw. Blechdicke"),
    STEG: (1.5, WARNUNG, "Abstand zwischen zwei Konturen kleiner als Grenzwert × Wandstärke bzw. Blechdicke"),
    RAND: (1.0, WARNUNG, "Kontur näher am Ende bzw. an der Blechkante als Grenzwert × Wandstärke bzw. Blechdicke"),
    KURZ: (None, FEHLER, "Teil kürzer als 'Kürzestes Teil' der Maschine (Stammdaten Maschinen)"),
    GRAVUR_KANTE: (None, WARNUNG, "Gravur über mehrere Flächen des Profils"),
    KANTBARKEIT: (None, HINWEIS, "Kantteile: Hinweise der Kantbarkeit (Faktoren unter Einstellungen, "
                                 "Blech-Richtpreis)"),
}
RANG = {HINWEIS: 0, WARNUNG: 1, FEHLER: 2}


def beispiel_regeln():
    """Zeilen der Tabelle pruefregeln: (regel, aktiv, grenzwert, stufe, bemerkung)."""
    return [(n, "ja", g, s, b + " (Startwert, bitte anpassen)") for n, (g, s, b) in REGELN.items()]


def regeln(zeilen=None):
    """{Regel: (Grenzwert, Stufe)} der aktiven Regeln; fehlende Zeilen mit ihrer Vorgabe, 'aktiv' = nein schaltet
    eine Regel ab, leerer Grenzwert = Vorgabe."""
    out = {n: (g, s) for n, (g, s, _) in REGELN.items()}
    for z in zeilen or ():
        n = z.get("regel")
        if n not in REGELN:
            continue
        if z.get("aktiv") == "nein":
            out.pop(n, None)
            continue
        g = z.get("grenzwert")
        out[n] = (REGELN[n][0] if g is None or g == "" else float(g),
                  z.get("stufe") if z.get("stufe") in STUFEN else REGELN[n][1])
    return out


def _schluessel(r):
    return tuple(sorted(((n, g, s) for n, (g, s) in r.items()), key=lambda t: t[0]))


def _zahl(x, stellen=1):
    t = f"{round(float(x), stellen):.{stellen}f}".replace(".", ",")
    return t[:-2] if t.endswith(",0") else t


# ------------------------------------------------------------------ Geometrie
def _abstand_punkt_strecke(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    lg = dx * dx + dy * dy
    t = 0.0 if lg <= 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / lg))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _innen(p, poly):
    drin = False
    for i, a in enumerate(poly):
        b = poly[i - 1]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
            drin = not drin
    return drin


def _kreuzen(p1, p2, q1, q2):
    def seite(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    d1, d2, d3, d4 = seite(q1, q2, p1), seite(q1, q2, p2), seite(p1, p2, q1), seite(p1, p2, q2)
    return d1 * d2 < 0 and d3 * d4 < 0


def abstand(a, b):
    """Kleinster Abstand zweier geschlossener Linienzüge [mm]; 0, wenn sie sich schneiden (auch ohne Ecke im
    anderen, z. B. zwei gekreuzte schmale Rechtecke) oder einer im anderen liegt."""
    if len(a) >= 3 and _innen(b[0], a) or len(b) >= 3 and _innen(a[0], b):
        return 0.0
    if any(_kreuzen(a[i - 1], a[i], b[j - 1], b[j]) for i in range(len(a)) for j in range(len(b))):
        return 0.0
    d = min(min(_abstand_punkt_strecke(p, q[i - 1], q[i]) for i in range(len(q)))
            for p, q in ((p, b) for p in a))
    d = min(d, min(min(_abstand_punkt_strecke(p, a[i - 1], a[i]) for i in range(len(a))) for p in b))
    return d


def _huelle(pts):
    return (min(x for x, _ in pts), min(y for _, y in pts), max(x for x, _ in pts), max(y for _, y in pts))


def stege(teile, grenze):
    """Paare von Konturen [(i, j, Abstand)] mit Abstand < grenze; teile = [(Linienzug, …)]. Vorauswahl über die
    Hüllrechtecke."""
    hl = [_huelle(t[0]) for t in teile]
    out = []
    for i in range(len(teile)):
        for j in range(i + 1, len(teile)):
            a, b = hl[i], hl[j]
            if max(a[0] - b[2], b[0] - a[2], a[1] - b[3], b[1] - a[3]) >= grenze:
                continue
            d = abstand(teile[i][0], teile[j][0])
            if d < grenze - 1e-9:
                out.append((i, j, d))
    return out


class Befund:
    __slots__ = ("regel", "stufe", "text")

    def __init__(self, regel, stufe, text):
        self.regel, self.stufe, self.text = regel, stufe, text

    def __repr__(self):
        return f"{self.stufe}: {self.regel}: {self.text}"

    def zeile(self):
        return f"{self.regel}: {self.text}"


def _befunde_sortiert(liste):
    return sorted(liste, key=lambda b: -RANG[b.stufe])


# ------------------------------------------------------------------ Rohr und Profil
def _schnittkonturen(konturen):
    from . import schneidweg as sw
    return [z for z in konturen or () if z.get("art") not in (sw.GRAVUR,)]


@functools.lru_cache(maxsize=4096)
def _rohr(technik, laenge, profil, wand, min_teil, r_key):
    from . import schneidweg as sw, skizze as sk
    r = dict((n, (g, s)) for n, g, s in r_key)
    out = []
    if KURZ in r and min_teil and laenge and laenge < min_teil - 1e-9:
        out.append(Befund(KURZ, r[KURZ][1], f"{_zahl(laenge, 0)} mm, die Maschine nimmt Teile ab "
                                             f"{_zahl(min_teil, 0)} mm"))
    e = sw.lesen(technik) if technik else None
    if not e or not e.get("konturen"):
        return tuple(out)
    konturen = e["konturen"]
    if BOHRUNG_KLEIN in r and wand:
        g, stufe = r[BOHRUNG_KLEIN]
        klein = [z for z in konturen if z.get("art") in (sw.BOHRUNG, sw.SENKUNG)
                 and 0.5 < sw._z(z.get("d")) < g * wand - 1e-9]
        if klein:
            n = sum(max(int(sw._z(z.get("anzahl")) or 1), 1) for z in klein)
            d = min(sw._z(z["d"]) for z in klein)
            out.append(Befund(BOHRUNG_KLEIN, stufe, f"{n} Bohrung(en) ab Ø {_zahl(d)} mm unter {_zahl(g)} × Wand "
                                                    f"({_zahl(g * wand)} mm)" + _lage_rohr(klein[0])))
    if GRAVUR_KANTE in r:
        ueber = [z for z in konturen if z.get("art") == sw.GRAVUR and len(z.get("waende") or ()) > 1]
        if ueber:
            out.append(Befund(GRAVUR_KANTE, r[GRAVUR_KANTE][1],
                              f"{len(ueber)} Gravur(en) über mehrere Flächen" + _lage_rohr(ueber[0])))
    if not wand or not laenge or (STEG not in r and RAND not in r):
        return tuple(out)
    qs = sk.Querschnitt(dict(profil))
    teile = []
    for d in sk.lagen(_schnittkonturen(konturen), laenge):
        if d.get("verteilt"):
            continue
        e_ = d["eingabe"]
        pts = sk.umriss_kontur(e_)
        if not pts:
            continue
        teile.append(([(d["x"] + dx, sk.s_lage(qs, e_, dq)) for dx, dq in pts], d))
    if RAND in r:
        g, stufe = r[RAND]
        nah = []
        for pts, d in teile:
            if d["art"] in (sw.SCHLITZ, sw.AUSKLINKUNG):
                continue
            x0, x1 = min(x for x, _ in pts), max(x for x, _ in pts)
            rest = min(x0, laenge - x1)
            if rest < g * wand - 1e-9:
                nah.append((rest, d))
        if nah:
            rest, d = min(nah, key=lambda t: t[0])
            out.append(Befund(RAND, stufe, f"{len(nah)} Kontur(en) näher als {_zahl(g)} × Wand ({_zahl(g * wand)} mm) "
                                           f"am Ende, kleinster Abstand {_zahl(max(rest, 0))} mm"
                                           + _lage_rohr(d["eingabe"], d["x"])))
    if STEG in r:
        g, stufe = r[STEG]
        paare = stege(teile, g * wand)
        if paare:
            i, j, dmin = min(paare, key=lambda t: t[2])
            a, b = teile[i][1], teile[j][1]
            out.append(Befund(STEG, stufe, f"{len(paare)} Steg(e) unter {_zahl(g)} × Wand ({_zahl(g * wand)} mm), "
                                           f"schmalster {_zahl(dmin)} mm zwischen Kontur {_nr(a)} und {_nr(b)}"
                                           + _lage_rohr(a["eingabe"], a["x"])))
    return tuple(out)


def _nr(d):
    """Konturzeile, bei Mustern mit laufender Nummer (2.3 = dritte Kontur der Zeile 2)."""
    from .schneidweg import _z
    n = int(_z(d["eingabe"].get("anzahl")) or 1)
    return f"{d['zeile'] + 1}.{d['nr'] + 1}" if n > 1 else f"{d['zeile'] + 1}"


def _lage_rohr(z, x=None):
    x = z.get("x") if x is None else x
    if x is None:
        return ""
    seite = z.get("seite")
    return f" (bei x = {_zahl(x, 0)} mm{', ' + str(seite) if seite else ''})"


def rohr(p, profil, maschine=None, zeilen=None, wand=None):
    """Befunde einer Rohr- bzw. Profilposition p (technik aus Schneidweg-Rechner oder STEP-Import, laenge),
    profil = Zeile der Stammdaten (form, a, b, wand), maschine = Zeile Maschinen (min_teil), zeilen = Tabelle
    pruefregeln, wand = Wandstärke für die Grenzen (Vorgabe Wand des Profils). Sortiert FEHLER zuerst."""
    from .schneidweg import _z
    w = _z(wand if wand is not None else (profil or {}).get("wand"))
    pk = tuple(sorted((k, v) for k, v in (profil or {}).items() if k in ("form", "a", "b", "wand", "profil_id")))
    befunde = _rohr(p.get("technik") or "", _z(p.get("laenge")), pk, w, _z((maschine or {}).get("min_teil")),
                    _schluessel(regeln(zeilen)))
    return _befunde_sortiert(befunde)


# ------------------------------------------------------------------ Blech
def blech(e, zs, zeilen=None, kantbarkeit=True, einst=None):
    """Befunde eines Blechteils aus dem Blech-Editor: e = Eingaben, zs = blech.zuschnitt(e). Konturen mit x/y
    im Zuschnitt; Rand = Abstand zur Außenkontur (Polygon bzw. Rechteck laenge × breite). kantbarkeit=False lässt
    die Kantbarkeit weg (der Blech-Editor zeigt sie schon); einst = Einstellungen 'blech_kant_…' (fehlende:
    Vorgaben)."""
    from . import blech as bl, schneidweg as sw, skizze as sk
    r = regeln(zeilen)
    s = sw._z(e.get("dicke"))
    out = []
    if not zs or s <= 0:
        return out
    konturen = e.get("konturen") or []
    if BOHRUNG_KLEIN in r:
        g, stufe = r[BOHRUNG_KLEIN]
        klein = [z for z in konturen if z.get("art") in (sw.BOHRUNG, sw.SENKUNG)
                 and 0.5 < sw._z(z.get("d")) < g * s - 1e-9]
        if klein:
            n = sum(max(int(sw._z(z.get("anzahl")) or 1), 1) for z in klein)
            d = min(sw._z(z["d"]) for z in klein)
            out.append(Befund(BOHRUNG_KLEIN, stufe, f"{n} Bohrung(en) ab Ø {_zahl(d)} mm unter {_zahl(g)} × Dicke "
                                                    f"({_zahl(g * s)} mm)" + _lage_blech(klein[0])))
    punkte = zs.get("punkte")
    minx = min((x for x, _ in punkte), default=0.0) if punkte else 0.0
    miny = min((y for _, y in punkte), default=0.0) if punkte else 0.0
    aussen = ([(x - minx, y - miny) for x, y in punkte] if punkte else
              [(0.0, 0.0), (zs["laenge"], 0.0), (zs["laenge"], zs["breite"]), (0.0, zs["breite"])])
    teile = []
    for i, z in enumerate(konturen):
        if z.get("x") is None or z.get("y") is None or z.get("art") == sw.GRAVUR:
            continue
        pts = sk.umriss_kontur(z)
        if not pts:
            continue
        cx, cy = sw._z(z["x"]) - minx, sw._z(z["y"]) - miny
        teile.append(([(cx + dx, cy + dq) for dx, dq in pts], dict(zeile=i, eingabe=z, x=z["x"], y=z["y"])))
    if RAND in r:
        g, stufe = r[RAND]
        nah = []
        for pts, d in teile:
            if not all(_innen(p, aussen) for p in pts):
                rest = 0.0
            else:
                rest = min(_abstand_punkt_strecke(p, aussen[k - 1], aussen[k]) for p in pts
                           for k in range(len(aussen)))
            if rest < g * s - 1e-9:
                nah.append((rest, d))
        if nah:
            rest, d = min(nah, key=lambda t: t[0])
            out.append(Befund(RAND, stufe, f"{len(nah)} Kontur(en) näher als {_zahl(g)} × Dicke ({_zahl(g * s)} mm) "
                                           f"an der Blechkante, kleinster Abstand {_zahl(rest)} mm"
                                           + _lage_blech(d["eingabe"])))
    if STEG in r:
        g, stufe = r[STEG]
        paare = stege(teile, g * s)
        if paare:
            i, j, dmin = min(paare, key=lambda t: t[2])
            a, b = teile[i][1], teile[j][1]
            out.append(Befund(STEG, stufe, f"{len(paare)} Steg(e) unter {_zahl(g)} × Dicke ({_zahl(g * s)} mm), "
                                           f"schmalster {_zahl(dmin)} mm zwischen Kontur {a['zeile'] + 1} und "
                                           f"{b['zeile'] + 1}" + _lage_blech(a["eingabe"])))
    if kantbarkeit and KANTBARKEIT in r:
        texte = [t for t in bl.kantbarkeit(e, zs, einst) if not t.endswith(bl.NICHT_GEPRUEFT)]
        if texte:
            out.append(Befund(KANTBARKEIT, r[KANTBARKEIT][1],
                              "; ".join(t.split(": ", 1)[-1] for t in texte)))
    return _befunde_sortiert(out)


def _lage_blech(z):
    if z.get("x") is None or z.get("y") is None:
        return ""
    return f" (bei x = {_zahl(z['x'], 0)}, y = {_zahl(z['y'], 0)} mm)"


def blech_position(p, zeilen=None, einst=None):
    """Befunde einer Blech-Position (Zukaufteil aus dem Blech-Editor, technik); einst = Einstellungen (die
    'blech_kant_…' gelten für die Kantbarkeit wie im Blech-Editor)."""
    if not p.get("technik"):
        return []
    kant = tuple(sorted((n, v) for n, v in (einst or {}).items() if n.startswith("blech_kant_") and v is not None))
    return list(_blech_position(p["technik"], _schluessel(regeln(zeilen)), kant))


@functools.lru_cache(maxsize=2048)
def _blech_position(technik, r_key, kant):
    from . import blech as bl
    e = bl.lesen(technik)
    if not e:
        return ()
    try:
        zs = bl.zuschnitt(e)
    except ValueError:
        return ()
    zeilen = [dict(regel=n, aktiv="ja", grenzwert=g, stufe=s) for n, g, s in r_key]
    zeilen += [dict(regel=n, aktiv="nein") for n in REGELN if n not in {k for k, _, _ in r_key}]
    return tuple(blech(e, zs, zeilen, einst=dict(kant)))


def status(befunde):
    """Statustext aus den Befunden ('WARNUNG: Steg zu schmal: …', weitere als Anzahl) oder None."""
    if not befunde:
        return None
    b = befunde[0]
    mehr = len(befunde) - 1
    return f"{b.stufe}: {b.zeile()}" + (f" (+{mehr} weitere Prüfung{'en' if mehr > 1 else ''})" if mehr else "")

