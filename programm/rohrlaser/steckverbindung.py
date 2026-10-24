"""Steckverbindung (Plan K2): zwei Rohre einer Baugruppe stecken mit Nasen und Schlitzen ineinander, damit sie sich
beim Schweißen selbst ausrichten. Der Stecker ist das Rohr, das mit einem Ende an die Aufnahme stößt: Sein Ende
bekommt Nasen (schmale Laschen der Wand, die durch die Wand der Aufnahme reichen), die Aufnahme an der Stelle je Nase
einen Schlitz.

Maße (Wand Aufnahme sA, Wand Stecker sB, Nasenbreite bN, Spiel c je Seite, Winkel α zwischen den Achsen, 90° =
senkrecht):
  Nasenlänge      lN = sA + Überstand (in der Tiefe, quer zur Wand der Aufnahme)
  Flanke          f  = lN / sin α (längs am Stecker; die Rohlänge des Steckers wächst um f)
  Stecker-Ende    + 2 · f je Nase (zwei Flanken)
  Schlitz         (Stärke der Nase längs der Aufnahme) × (bN + 2c), Konturart Rechteck, ein Einstich
                  Stärke = (sB + Bogenhöhe) / sin α + sA / tan α + 2c   (Bogenhöhe der Nase nur bei Rundrohr)
Die Nasen sitzen mittig auf zwei gegenüberliegenden Wänden des Steckers. Vorgabe 'quer': die Wände quer zur Achse
der Aufnahme (die Nasen liegen dann hintereinander längs der Aufnahme), 'längs' dreht sie um 90°. Bei 'längs' liegt
die Nasenbreite in der Ebene des Winkels: Länge des Schlitzes = bN / sin α + sA / tan α + 2c, Breite = Stärke.
Rundrohr als Stecker: die Nase ist ein Bogenstück (bN = Sehne), als Aufnahme: das Ende des Steckers ist ein Sattel
(Ausklinkung auf Rundrohr), der Schlitz liegt auf dem Bogen (Breite = Bogenlänge der Sehne). Schräge Stöße (α < 90°)
gehen bis zum kleinsten Winkel WINKEL_MIN.

Daten: die Baugruppe hält die Liste 'steckverbindungen' mit je
  {id, aufnahme: {pos, knoten}, stecker: {pos, knoten, ende: 'a'|'b'}, x, seite, anzahl, bN, ueberstand, lN, c,
   waende, winkel, wandbreite, abstand}
(x = Mitte des Steckers auf der Aufnahme ab Ende A, seite = Wand bzw. Winkel der Aufnahme zum Stecker; wandbreite und
abstand = Breite der Nasenwand und Außenabstand der beiden Nasenwände des Steckers, leer = aus dem Profil). Die
Schlitze sind Konturzeilen der Aufnahme mit der Quelle 'Steckverbindung id', das Ende des Steckers trägt den Block
'nasen' mit derselben id. Die Positionen findet die Verbindung über diese Kennung (bleibt beim Kopieren gleich)."""
import math

HERKUNFT = "Steckverbindung"
ANZAHL, SPIEL, UEBERSTAND, NASE_MIN = 2, 0.1, 0.0, 10.0     # Vorgaben (Einstellungen steck_…)
WAENDE = ("quer", "längs")
ANZAHLEN = (1, 2, 4)            # 1 Nase, 2 gegenüber, 4 = alle Wände
FORMEN = ("Quadratrohr", "Rechteckrohr", "Rundrohr")
WINKEL_MIN = 30.0


def _z(x):
    try:
        return float(x) if x not in (None, "") and not isinstance(x, bool) else 0.0
    except (TypeError, ValueError):
        return 0.0


def quelle(vid):
    """Quelle der Schlitz-Zeilen einer Verbindung."""
    return f"{HERKUNFT} {vid}"


def _profil(profil, rolle):
    form = (profil or {}).get("form")
    if form not in FORMEN:
        raise ValueError(f"Steckverbindung: {rolle} muss Quadrat-, Rechteck- oder Rundrohr sein "
                         f"(Profil: {form or '?'}).")
    a, s = _z(profil.get("a")), _z(profil.get("wand"))
    b = a if form != "Rechteckrohr" else (_z(profil.get("b")) or a)
    if a <= 0 or s <= 0 or 2 * s >= min(a, b):
        raise ValueError(f"Steckverbindung: Profilmaße und Wandstärke des {rolle}s fehlen oder passen nicht.")
    return form, a, b, s


def querschnitt(profil_s, waende="quer"):
    """(Breite der Nasenwand, Außenabstand der Nasenwände, Wand) des Steckers aus dem Profil. Rechteckrohr: Breite a
    liegt quer zur Achse der Aufnahme ('quer'), 'längs' tauscht; Rundrohr: beides = Außen-Ø."""
    form, a, b, s = _profil(profil_s, "Stecker")
    if form == "Rundrohr" or waende != "längs":
        return a, b, s
    return b, a, s


def vorgaben(profil_s, einst=None, waende="quer"):
    """Vorgabewerte einer neuen Verbindung aus den Einstellungen (einst = {Name ohne 'steck_': Wert}, leer =
    Programmvorgabe): Anzahl, Nasenbreite = halbe Wandbreite des Steckers (mindestens steck_nase_min), Spiel,
    Überstand, senkrechter Stoß."""
    einst = einst or {}
    bw, _, _ = querschnitt(profil_s, waende)
    n = int(_z(einst.get("anzahl")) or ANZAHL)
    mind = _z(einst.get("nase_min")) if einst.get("nase_min") not in (None, "") else NASE_MIN
    return dict(anzahl=n if n in ANZAHLEN else ANZAHL, bN=round(max(mind, bw / 2), 2),
                c=_z(einst.get("spiel")) if einst.get("spiel") not in (None, "") else SPIEL,
                ueberstand=_z(einst.get("ueberstand")) if einst.get("ueberstand") not in (None, "") else UEBERSTAND,
                waende=waende if waende in WAENDE else WAENDE[0], winkel=90.0)


def _bogenhoehe(r, sehne):
    """Pfeilhöhe eines Bogens mit Radius r über der Sehne."""
    if r <= 0 or sehne <= 0:
        return 0.0
    h = min(sehne / 2, r)
    return r - math.sqrt(r * r - h * h)


def masse(v, profil_a, profil_s):
    """Maße einer Verbindung v: dict(lN, flanke, schlitz_l (längs der Aufnahme), schlitz_b (am Umfang), schlitz
    (Schnittlänge je Schlitz), nasen = [(dx, dq)] Lage der Schlitze um die Mitte, ende_plus (Stecker-Ende länger um),
    laenge_plus (Rohlänge Stecker), aufnahme_plus (Schneidweg Aufnahme), einstiche_plus). ValueError bei unmöglichen
    Maßen."""
    form_a, a_a, _, s_a = _profil(profil_a, "Aufnahme")
    form_s = _profil(profil_s, "Stecker")[0]
    waende = v.get("waende") if v.get("waende") in WAENDE else WAENDE[0]
    bw0, ab0, s_b = querschnitt(profil_s, waende)
    bw, ab = _z(v.get("wandbreite")) or bw0, _z(v.get("abstand")) or ab0
    n = int(_z(v.get("anzahl")) or 0)
    if n not in ANZAHLEN:
        raise ValueError("Steckverbindung: 1, 2 oder 4 Nasen eingeben.")
    b_n, c = _z(v.get("bN")), _z(v.get("c"))
    if b_n <= 0 or c < 0:
        raise ValueError("Steckverbindung: Nasenbreite > 0 und Spiel ≥ 0 eingeben.")
    if b_n > bw - (0 if form_s == "Rundrohr" else 2 * s_b) + 1e-9:
        raise ValueError(f"Steckverbindung: Nase {b_n:g} mm breiter als die Wand des Steckers innen.")
    alpha = _z(v.get("winkel")) or 90.0
    if not WINKEL_MIN - 1e-9 <= alpha <= 90 + 1e-9:
        raise ValueError(f"Steckverbindung: Winkel zwischen den Achsen {WINKEL_MIN:g}° bis 90° eingeben.")
    sin, cot = math.sin(math.radians(alpha)), 1 / math.tan(math.radians(alpha))
    l_n = s_a + _z(v.get("ueberstand"))
    if l_n <= 0:
        raise ValueError("Steckverbindung: Nasenlänge (Wand der Aufnahme + Überstand) muss > 0 sein.")
    flanke = l_n / sin
    staerke = s_b + (_bogenhoehe(ab / 2, b_n) if form_s == "Rundrohr" else 0.0)
    lage = []                   # (Art der Wand, Vorzeichen) je Nase
    for i in range(n):
        art = waende if i < 2 else WAENDE[1 - WAENDE.index(waende)]
        lage.append((art, 1 if i % 2 == 0 else -1))
    nasen, schlitze, laengen = [], [], []
    for art, vz in lage:
        abst = (ab if art == waende else bw) - s_b         # Mitte zu Mitte der beiden Nasenwände
        if art == "quer":       # Nasen hintereinander längs der Aufnahme
            sl, sb = staerke / sin + s_a * cot + 2 * c, b_n + 2 * c
            dx, dq = vz * abst / 2 / sin, 0.0
        else:                   # Nasen nebeneinander am Umfang der Aufnahme
            sl, sb = b_n / sin + s_a * cot + 2 * c, staerke + 2 * c
            dx, dq = 0.0, vz * abst / 2
        if form_a == "Rundrohr":                # Breite am Umfang = Bogen über der Sehne
            r = a_a / 2
            sb = 2 * r * math.asin(min(1.0, sb / (2 * r)))
        nasen.append((dx, dq))
        schlitze.append((sl, sb))
        laengen.append(2 * (sl + sb))
    return dict(lN=l_n, flanke=flanke, schlitze=schlitze, nasen=nasen, schlitz_l=schlitze[0][0],
                schlitz_b=schlitze[0][1], schlitz=laengen[0], ende_plus=2 * n * flanke, laenge_plus=flanke,
                aufnahme_plus=sum(laengen), einstiche_plus=n, bN=b_n, anzahl=n, staerke=staerke)


def schlitz_zeilen(v, profil_a, profil_s):
    """Konturzeilen der Schlitze auf der Aufnahme (Rechteck, Lage x/seite/q, Quelle der Verbindung)."""
    from . import skizze as sk
    m = masse(v, profil_a, profil_s)
    rund = profil_a.get("form") == "Rundrohr"
    out = []
    for (dx, dq), (sl, sb) in zip(m["nasen"], m["schlitze"]):
        z = dict(art="Rechteck", anzahl=1, b=round(sl, 3), h=round(sb, 3), r=0, quelle=quelle(v["id"]),
                 text=f"Schlitz {HERKUNFT}")
        if v.get("x") is not None:
            z["x"] = round(_z(v["x"]) + dx, 3)
        seite = v.get("seite")
        if rund and dq:
            w = sk.winkel_aus_text(seite) or 0.0
            seite = sk.winkel_text(round(w + math.degrees(dq / (_z(profil_a.get("a")) / 2)), 1))
            dq = 0.0
        if seite:
            z["seite"] = seite
        if dq:
            z["q"] = round(dq, 3)
        out.append(z)
    return out


def nasen_block(v, profil_a, profil_s):
    """Block 'nasen' für das Ende des Steckers."""
    m = masse(v, profil_a, profil_s)
    return dict(id=v["id"], anzahl=m["anzahl"], bN=m["bN"], lN=round(m["lN"], 3), flanke=round(m["flanke"], 3),
                plus=round(m["ende_plus"], 3), laenge_plus=round(m["laenge_plus"], 3), waende=v.get("waende") or "quer")


def nasen(e):
    """Block 'nasen' eines Endes (dict der Eingaben a/b) oder None."""
    x = (e or {}).get("nasen") if isinstance(e, dict) else None
    return x if isinstance(x, dict) and x.get("id") else None


def entfernen(eingaben, vid):
    """Eingaben ohne die Schlitze und Nasen der Verbindung vid (Kopie). Ergebnis (Eingaben, Rohlänge weniger um)."""
    neu = dict(eingaben)
    neu["konturen"] = [z for z in eingaben.get("konturen") or () if z.get("quelle") != quelle(vid)]
    weniger = 0.0
    for s in ("a", "b"):
        x = nasen(eingaben.get(s))
        if x and x["id"] == vid:
            neu[s] = {k: w for k, w in eingaben[s].items() if k != "nasen"}
            weniger += _z(x.get("laenge_plus"))
    return neu, weniger


def anwenden(v, eingaben_a, eingaben_s, profil_a, profil_s):
    """Verbindung v auf die Eingaben der Aufnahme und des Steckers (beide Kopien, frühere Konturen derselben Verbindung
    fallen weg). Ergebnis (Eingaben Aufnahme, Eingaben Stecker, Änderung der Rohlänge des Steckers [mm])."""
    ende = (v.get("stecker") or {}).get("ende")
    if ende not in ("a", "b"):
        raise ValueError("Steckverbindung: Ende des Steckers (A oder E) fehlt.")
    a, _ = entfernen(eingaben_a, v["id"])
    s, weniger = entfernen(eingaben_s, v["id"])
    a["konturen"] = list(a["konturen"]) + schlitz_zeilen(v, profil_a, profil_s)
    blk = nasen_block(v, profil_a, profil_s)
    s[ende] = dict(s.get(ende) or {}, nasen=blk)
    return a, s, round(blk["laenge_plus"] - weniger, 3)


# ------------------------------------------------------------------ Baugruppe
def liste(bg):
    """Verbindungen der Baugruppe (nur Datensätze mit Kennung)."""
    return [v for v in (bg or {}).get("steckverbindungen") or () if isinstance(v, dict) and v.get("id")]


def rollen(technik_text):
    """{Kennung: {'aufnahme', 'stecker'}} der Verbindungen, auf die eine Position verweist."""
    from . import schneidweg as sw
    e = sw.lesen(technik_text)
    out = {}
    for z in e.get("konturen") or ():
        q = str(z.get("quelle") or "")
        if q.startswith(HERKUNFT + " "):
            out.setdefault(q[len(HERKUNFT) + 1:], set()).add("aufnahme")
    for s in ("a", "b"):
        x = nasen(e.get(s))
        if x:
            out.setdefault(str(x["id"]), set()).add("stecker")
    return out


def teile_finden(positionen, indizes, vid, v=None):
    """(Index der Aufnahme, Index des Steckers) der Verbindung vid unter den Positionen indizes, je None ohne. Gesucht
    über die Kennung in den Eingaben (Schlitze, Nasen); mit v (Verbindung) auch über die Positions-ID, solange die
    Konturen noch nicht geschrieben sind (Editor der Baugruppe vor OK)."""
    auf = st = None
    for i in indizes:
        r = rollen(positionen[i].get("technik")).get(vid) or ()
        if "aufnahme" in r and auf is None:
            auf = i
        if "stecker" in r and st is None:
            st = i
    if v:
        for i in indizes:
            pid = positionen[i].get("id")
            if auf is None and pid is not None and pid == (v.get("aufnahme") or {}).get("id"):
                auf = i
            if st is None and pid is not None and pid == (v.get("stecker") or {}).get("id"):
                st = i
    return auf, st


def fehler(bg, positionen, indizes):
    """Erster Fehler der Steckverbindungen einer Baugruppe als Text (Teil fehlt = ohne Gegenstück), sonst None."""
    for n, v in enumerate(liste(bg), 1):
        auf, st = teile_finden(positionen, indizes, v["id"], v)
        if auf is None or st is None:
            fehlt = " und ".join(t for t, i in (("Aufnahme", auf), ("Stecker", st)) if i is None)
            return f"Steckverbindung {n} ohne Gegenstück ({fehlt} nicht in der Baugruppe)"
    return None


def text(v, m=None):
    """Kurztext, z. B. '2 Nasen 20 × 2 mm, Spiel 0,1 mm, Schlitz 2,2 × 20,2 mm'."""
    from .rechnen import zahl
    n = int(_z(v.get("anzahl")))
    t = f"{n} Nase{'n' if n != 1 else ''} {zahl(_z(v.get('bN')), 1)}"
    if m:
        t += f" × {zahl(m['lN'], 1)} mm, Schlitz {zahl(m['schlitz_l'], 2)} × {zahl(m['schlitz_b'], 2)} mm"
    t += f", Spiel {zahl(_z(v.get('c')), 2)} mm"
    if _z(v.get("winkel")) and _z(v["winkel"]) < 90 - 1e-6:
        t += f", schräg {zahl(_z(v['winkel']), 1)}°"
    return t


# ------------------------------------------------------------------ Editor der Baugruppe
SEITEN_KASTEN = ("oben", "vorne", "unten", "hinten")
FELDER = ("x", "seite", "anzahl", "bN", "c", "ueberstand", "waende", "winkel", "wandbreite", "abstand")


def neu(aufnahme, stecker, profil_s, einst=None, ende="a", x=None, seite=None, kennung=None):
    """Neue Verbindung zwischen den Positionen aufnahme und stecker (dicts mit id, pos, bg_knoten) mit den Vorgaben
    der Einstellungen."""
    import uuid
    from . import baugruppe
    v = dict(vorgaben(profil_s, einst), id=kennung or uuid.uuid4().hex[:10],
             aufnahme=dict(id=aufnahme.get("id"), pos=aufnahme.get("pos"),
                           knoten=baugruppe.zuordnung(aufnahme)[1] or ""),
             stecker=dict(id=stecker.get("id"), pos=stecker.get("pos"), knoten=baugruppe.zuordnung(stecker)[1] or "",
                          ende=ende if ende in ("a", "b") else "a"))
    if x is not None:
        v["x"] = x
    if seite:
        v["seite"] = seite
    return v


def tauschen(v, profil_s_neu, einst=None):
    """Aufnahme und Stecker vertauschen (Ende des neuen Steckers: A, Lage auf der neuen Aufnahme unbekannt); die
    Nasenbreite folgt dem neuen Stecker."""
    a, s_ = dict(v.get("aufnahme") or {}), dict(v.get("stecker") or {})
    s_.pop("ende", None)
    out = {k: w for k, w in v.items() if k not in ("x", "seite", "wandbreite", "abstand")}
    out.update(aufnahme=s_, stecker=dict(a, ende="a"), bN=vorgaben(profil_s_neu, einst, v.get("waende") or "quer")["bN"])
    return out


def aenderungen(alt, neu_):
    """Vergleich zweier Listen von Verbindungen: (weg = [alte Verbindung], dazu = [neue oder geänderte Verbindung]);
    eine geänderte Verbindung steht in beiden (erst entfernen, dann neu anlegen)."""
    a = {v["id"]: v for v in liste(dict(steckverbindungen=alt))}
    n = {v["id"]: v for v in liste(dict(steckverbindungen=neu_))}
    weg = [v for k, v in a.items() if k not in n or n[k] != v]
    dazu = [v for k, v in n.items() if k not in a or a[k] != v]
    return weg, dazu


def pruefen(v, profil_a, profil_s):
    """Fehlertext einer Verbindung im Editor oder None."""
    if not (v.get("aufnahme") or {}).get("id") or not (v.get("stecker") or {}).get("id"):
        return "Aufnahme und Stecker wählen"
    if v["aufnahme"]["id"] == v["stecker"]["id"]:
        return "Aufnahme und Stecker sind dasselbe Teil"
    if v.get("x") is None:
        return "Lage x auf der Aufnahme fehlt"
    try:
        masse(v, profil_a, profil_s)
    except ValueError as f:
        return str(f).replace("Steckverbindung: ", "")
    return None
