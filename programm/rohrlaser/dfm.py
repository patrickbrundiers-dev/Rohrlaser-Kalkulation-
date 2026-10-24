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
  Kontur in der Biegezone Biegerohr: Kontur in einem Bogen oder näher als Grenzwert × Wand daran (0, WARNUNG)
  Gerade zwischen Biegungen zu kurz
                          Biegerohr: Gerade zwischen zwei Biegungen kürzer als Grenzwert × Außen-Ø (1,5, WARNUNG)
  Schenkel zu kurz        Knickrahmen: Schenkel kürzer als Grenzwert × Rohrmaß h in der Rahmenebene (2,0, WARNUNG)
  Kontur im Knickbereich  Knickrahmen: Kontur näher am V-Ausschnitt als Grenzwert × Wand (2,0, WARNUNG)
  Wand zu dick zum Knicken
                          Knickrahmen: Wandstärke über Grenzwert in mm (4, HINWEIS)

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
BIEGEZONE, GERADE_KURZ = "Kontur in der Biegezone", "Gerade zwischen Biegungen zu kurz"
SCHENKEL_KURZ, KNICKBEREICH, KNICK_WAND = "Schenkel zu kurz", "Kontur im Knickbereich", "Wand zu dick zum Knicken"
KNICK_REGELN = (SCHENKEL_KURZ, KNICKBEREICH, KNICK_WAND)
NASE_SCHMAL = "Nase zu schmal"
STECK_REGELN = (NASE_SCHMAL,)
# Regel: (Grenzwert, Stufe, Beschreibung) – Vorgaben und Beispielzeilen der Tabelle
REGELN = {
    BOHRUNG_KLEIN: (1.0, WARNUNG, "Bohrung bzw. Senkung Ø kleiner als Grenzwert × Wandstärke bzw. Blechdicke"),
    STEG: (1.5, WARNUNG, "Abstand zwischen zwei Konturen kleiner als Grenzwert × Wandstärke bzw. Blechdicke"),
    RAND: (1.0, WARNUNG, "Kontur näher am Ende bzw. an der Blechkante als Grenzwert × Wandstärke bzw. Blechdicke"),
    KURZ: (None, FEHLER, "Teil kürzer als 'Kürzestes Teil' der Maschine (Stammdaten Maschinen)"),
    GRAVUR_KANTE: (None, WARNUNG, "Gravur über mehrere Flächen des Profils"),
    KANTBARKEIT: (None, HINWEIS, "Kantteile: Hinweise der Kantbarkeit (Faktoren unter Einstellungen, "
                                 "Blech-Richtpreis)"),
    BIEGEZONE: (0.0, WARNUNG, "Biegerohr: Kontur in einem Bogen oder näher als Grenzwert × Wandstärke daran"),
    GERADE_KURZ: (1.5, WARNUNG, "Biegerohr: Gerade zwischen zwei Biegungen kürzer als Grenzwert × Außen-Ø "
                                "(Spannlänge der Biegemaschine)"),
    SCHENKEL_KURZ: (2.0, WARNUNG, "Knickrahmen: Schenkel kürzer als Grenzwert × Rohrmaß in der Rahmenebene"),
    KNICKBEREICH: (2.0, WARNUNG, "Knickrahmen: Kontur näher am V-Ausschnitt als Grenzwert × Wandstärke"),
    KNICK_WAND: (4.0, HINWEIS, "Knickrahmen: Wandstärke über Grenzwert in mm (Knicken von Hand schwer)"),
    NASE_SCHMAL: (3.0, WARNUNG, "Steckverbindung: Nasenbreite kleiner als Grenzwert × Wandstärke des Steckers"),
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
    """Ergebnis einer Regel; zeilen = betroffene Konturzeilen (ab 0) für den Teile-Editor, laenge = Teilelänge
    betroffen (Regel 'zu kurz'), biegung = Kantbarkeit."""
    __slots__ = ("regel", "stufe", "text", "zeilen")

    def __init__(self, regel, stufe, text, zeilen=()):
        self.regel, self.stufe, self.text, self.zeilen = regel, stufe, text, tuple(zeilen)

    def __repr__(self):
        return f"{self.stufe}: {self.regel}: {self.text}"

    def zeile(self):
        return f"{self.regel}: {self.text}"


def _befunde_sortiert(liste):
    return sorted(liste, key=lambda b: -RANG[b.stufe])


# ------------------------------------------------------------------ Rohr und Profil
def _schnittkonturen(konturen):
    from . import schneidweg as sw
    return [z for z in konturen or () if z.get("art") != sw.GRAVUR]


@functools.lru_cache(maxsize=4096)
def _rohr(technik, laenge, profil, wand, min_teil, r_key):
    from . import schneidweg as sw, skizze as sk
    r = dict((n, (g, s)) for n, g, s in r_key)
    out = []
    if KURZ in r and min_teil and laenge and laenge < min_teil - 1e-9:
        out.append(Befund(KURZ, r[KURZ][1], f"{_zahl(laenge, 0)} mm, die Maschine nimmt Teile ab "
                                             f"{_zahl(min_teil, 0)} mm"))
    e = sw.lesen(technik) if technik else None
    if e:
        e = sw.v_ergaenzen(e, dict(profil))
        out += _biegerohr(e, laenge, dict(profil), wand, r)
        out += _knickrahmen(e, laenge, dict(profil), wand, r)
        out += _nasen(e, wand, r)
    if not e or not e.get("konturen"):
        return tuple(out)
    konturen = e["konturen"]
    if BOHRUNG_KLEIN in r and wand:
        g, stufe = r[BOHRUNG_KLEIN]
        nr = [i for i, z in enumerate(konturen) if z.get("art") in (sw.BOHRUNG, sw.SENKUNG)
              and 0.5 < sw._z(z.get("d")) < g * wand - 1e-9]
        klein = [konturen[i] for i in nr]
        if klein:
            n = sum(max(int(sw._z(z.get("anzahl")) or 1), 1) for z in klein)
            d = min(sw._z(z["d"]) for z in klein)
            out.append(Befund(BOHRUNG_KLEIN, stufe, f"{n} Bohrung(en) ab Ø {_zahl(d)} mm unter {_zahl(g)} × Wand "
                                                    f"({_zahl(g * wand)} mm)" + _lage_rohr(klein[0]), nr))
    if GRAVUR_KANTE in r:
        nr = [i for i, z in enumerate(konturen) if z.get("art") == sw.GRAVUR and len(z.get("waende") or ()) > 1]
        if nr:
            out.append(Befund(GRAVUR_KANTE, r[GRAVUR_KANTE][1],
                              f"{len(nr)} Gravur(en) über mehrere Flächen" + _lage_rohr(konturen[nr[0]]), nr))
    if not wand or not laenge or (STEG not in r and RAND not in r):
        return tuple(out)
    qs = sk.Querschnitt(dict(profil))
    teile = []
    schnitt = _schnittkonturen(konturen)
    zeile = [i for i, z in enumerate(konturen) if z.get("art") != sw.GRAVUR]    # Tabellenzeile je Schnittkontur
    for d in sk.lagen(schnitt, laenge):
        if d.get("verteilt"):
            continue
        d = dict(d, zeile=zeile[d["zeile"]])
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
                                           + _lage_rohr(d["eingabe"], d["x"]), _zeilen(x[1] for x in nah)))
    if STEG in r:
        g, stufe = r[STEG]
        paare = stege(teile, g * wand)
        if paare:
            i, j, dmin = min(paare, key=lambda t: t[2])
            a, b = teile[i][1], teile[j][1]
            out.append(Befund(STEG, stufe, f"{len(paare)} Steg(e) unter {_zahl(g)} × Wand ({_zahl(g * wand)} mm), "
                                           f"schmalster {_zahl(dmin)} mm zwischen Kontur {_nr(a)} und {_nr(b)}"
                                           + _lage_rohr(a["eingabe"], a["x"]),
                              _zeilen(teile[k][1] for i_, j_, _ in paare for k in (i_, j_))))
    return tuple(out)


def _biegerohr(e, laenge, profil, wand, r):
    """Befunde eines Biegerohrs (technik mit Block 'biegerohr'): Konturen in der Biegezone, kurze Geraden."""
    from . import biegerohr as bg, schneidweg as sw, skizze as sk
    br = bg.lesen(e)
    if not br:
        return []
    out = []
    if GERADE_KURZ in r:
        g, stufe = r[GERADE_KURZ]
        d = sw._z(br.get("aussen_d")) or sw._z(profil.get("a"))
        kurz = [(n, lg) for n, lg in bg.geraden_zwischen(br) if g and d and lg < g * d - 1e-9]
        if kurz:
            n, lg = min(kurz, key=lambda t: t[1])
            out.append(Befund(GERADE_KURZ, stufe, f"{len(kurz)} Gerade(n) unter {_zahl(g)} × Außen-Ø "
                                                  f"({_zahl(g * d)} mm), kürzeste {_zahl(lg)} mm nach Biegung {n}"))
    if BIEGEZONE in r:
        g, stufe = r[BIEGEZONE]
        abstand = (g or 0.0) * (wand or 0.0)
        treffer, zonen = [], set()
        for d in sk.lagen(_schnittkonturen(e.get("konturen")), laenge):
            if d.get("verteilt"):
                continue
            pts = sk.umriss_kontur(d["eingabe"]) or [(0.0, 0.0)]
            x0, x1 = d["x"] + min(p[0] for p in pts), d["x"] + max(p[0] for p in pts)
            nr = bg.in_zone(x0, x1, br, None, abstand)
            if nr:
                treffer.append(d)
                zonen.update(nr)
        if treffer:
            zeilen_e = [i for i, z in enumerate(e.get("konturen") or ()) if z.get("art") != sw.GRAVUR]
            out.append(Befund(BIEGEZONE, stufe, f"{len(treffer)} Kontur(en) in der Biegezone (Biegung "
                                                f"{', '.join(map(str, sorted(zonen)))})"
                              + (f", Abstand unter {_zahl(abstand)} mm" if abstand else "")
                              + _lage_rohr(treffer[0]["eingabe"], treffer[0]["x"]),
                              sorted({zeilen_e[d["zeile"]] for d in treffer})))
    return out


def _knickrahmen(e, laenge, profil, wand, r):
    """Befunde eines Knickrahmens (V-Ausschnitte, Block 'knickrahmen'): kurze Schenkel, Konturen im Knickbereich,
    dicke Wand."""
    from . import knickrahmen as kn, schneidweg as sw, skizze as sk
    konturen = e.get("konturen") or ()
    v_zeilen = [i for i, z in enumerate(konturen) if z.get("art") == sw.V_AUSSCHNITT]
    k = kn.lesen(e)
    if not v_zeilen and not k:
        return []
    out = []
    if KNICK_WAND in r and r[KNICK_WAND][0] and wand and wand > r[KNICK_WAND][0] + 1e-9:
        out.append(Befund(KNICK_WAND, r[KNICK_WAND][1], f"Wand {_zahl(wand)} mm über {_zahl(r[KNICK_WAND][0])} mm: "
                                                        "Knicken an der Abkantbank prüfen", v_zeilen))
    if k and SCHENKEL_KURZ in r:
        g, stufe = r[SCHENKEL_KURZ]
        try:
            rm = kn.rahmen(k, profil)
        except ValueError:
            rm = None
        if rm and g:
            kurz = [(i, a) for i, a in enumerate(rm["schenkel"], start=1) if a < g * rm["h"] - 1e-9]
            if kurz:
                i, a = min(kurz, key=lambda t: t[1])
                out.append(Befund(SCHENKEL_KURZ, stufe, f"{len(kurz)} Schenkel unter {_zahl(g)} × {_zahl(rm['h'])} mm "
                                                        f"({_zahl(g * rm['h'])} mm), kürzester Schenkel {i} mit "
                                                        f"{_zahl(a)} mm", v_zeilen))
    if KNICKBEREICH in r and v_zeilen:
        g, stufe = r[KNICKBEREICH]
        abstand = (g or 0.0) * (wand or 0.0)
        lagen = [d for d in sk.lagen(_schnittkonturen(konturen), laenge) if not d.get("verteilt")]
        schnitt = _schnittkonturen(konturen)
        zeilen_e = [i for i, z in enumerate(konturen) if z.get("art") != sw.GRAVUR]
        zonen = []
        for d in lagen:
            if d["art"] == sw.V_AUSSCHNITT:
                pts = sk.umriss_kontur(d["eingabe"]) or [(0.0, 0.0)]
                zonen.append((d["x"] + min(p[0] for p in pts) - abstand, d["x"] + max(p[0] for p in pts) + abstand))
        treffer = []
        for d in lagen:
            if d["art"] == sw.V_AUSSCHNITT:
                continue
            pts = sk.umriss_kontur(d["eingabe"]) or [(0.0, 0.0)]
            x0, x1 = d["x"] + min(p[0] for p in pts), d["x"] + max(p[0] for p in pts)
            if any(x1 > a + 1e-6 and x0 < b - 1e-6 for a, b in zonen):
                treffer.append(d)
        if treffer and schnitt:
            out.append(Befund(KNICKBEREICH, stufe, f"{len(treffer)} Kontur(en) näher als {_zahl(abstand)} mm am "
                                                   "V-Ausschnitt" + _lage_rohr(treffer[0]["eingabe"], treffer[0]["x"]),
                              sorted({zeilen_e[d["zeile"]] for d in treffer})))
    return out


def _nasen(e, wand, r):
    """Befund 'Nase zu schmal' für die Nasen einer Steckverbindung an den Enden."""
    from . import steckverbindung as sv
    if NASE_SCHMAL not in r or not r[NASE_SCHMAL][0] or not wand:
        return []
    g, stufe = r[NASE_SCHMAL]
    out = []
    for s, titel in (("a", "Anfang"), ("b", "Ende")):
        nb = sv.nasen(e.get(s))
        if nb and sv._z(nb.get("bN")) < g * wand - 1e-9:
            out.append(Befund(NASE_SCHMAL, stufe, f"{titel}: Nase {_zahl(sv._z(nb['bN']))} mm unter {_zahl(g)} × Wand "
                                                  f"({_zahl(g * wand)} mm), Nase kann beim Heften abbrechen"))
    return out


def _zeilen(lagen):
    """Konturzeilen (ab 0, sortiert, ohne Doppelte) aus Lagen dict(zeile=…)."""
    return sorted({d["zeile"] for d in lagen})


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
    if isinstance(seite, (int, float)) and not isinstance(seite, bool):       # Rundrohr: Winkel
        seite = f"{_zahl(seite, 0)}°"
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
        nr = [i for i, z in enumerate(konturen) if z.get("art") in (sw.BOHRUNG, sw.SENKUNG)
              and 0.5 < sw._z(z.get("d")) < g * s - 1e-9]
        klein = [konturen[i] for i in nr]
        if klein:
            n = sum(max(int(sw._z(z.get("anzahl")) or 1), 1) for z in klein)
            d = min(sw._z(z["d"]) for z in klein)
            out.append(Befund(BOHRUNG_KLEIN, stufe, f"{n} Bohrung(en) ab Ø {_zahl(d)} mm unter {_zahl(g)} × Dicke "
                                                    f"({_zahl(g * s)} mm)" + _lage_blech(klein[0]), nr))
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
                                           + _lage_blech(d["eingabe"]), _zeilen(x[1] for x in nah)))
    if STEG in r:
        g, stufe = r[STEG]
        paare = stege(teile, g * s)
        if paare:
            i, j, dmin = min(paare, key=lambda t: t[2])
            a, b = teile[i][1], teile[j][1]
            out.append(Befund(STEG, stufe, f"{len(paare)} Steg(e) unter {_zahl(g)} × Dicke ({_zahl(g * s)} mm), "
                                           f"schmalster {_zahl(dmin)} mm zwischen Kontur {a['zeile'] + 1} und "
                                           f"{b['zeile'] + 1}" + _lage_blech(a["eingabe"]),
                              _zeilen(teile[k][1] for i_, j_, _ in paare for k in (i_, j_))))
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

