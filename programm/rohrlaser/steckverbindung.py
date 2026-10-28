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
   waende, winkel, wandbreite, abstand, schlitze, nasen}
(schlitze/nasen = False: bei gleichen Teilen schneidet eine andere Verbindung die Schlitze bzw. Nasen schon; x = Mitte des Steckers auf der Aufnahme ab Ende A, seite = Wand bzw. Winkel der Aufnahme zum Stecker; wandbreite und
abstand = Breite der Nasenwand und Außenabstand der beiden Nasenwände des Steckers, leer = aus dem Profil). Die
Schlitze sind Konturzeilen der Aufnahme mit der Quelle 'Steckverbindung id', das Ende des Steckers trägt den Block
'nasen' mit derselben id. Die Positionen findet die Verbindung über diese Kennung (bleibt beim Kopieren gleich)."""
import math

HERKUNFT = "Steckverbindung"
ANZAHL, SPIEL, UEBERSTAND, NASE_MIN = 2, 0.1, 0.0, 10.0     # Vorgaben (Einstellungen steck_…)
NASE_RAND = 2.0     # mm Abstand der Nase zum Eckradius je Seite (Einstellung steck_nase_rand, Patrick 25.10.2026 „c“)
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


def nase_max(profil_s, waende="quer", rand=None, wandbreite=None):
    """Größte Nasenbreite [mm] (Patrick 25.10.2026 „c: Gerade Wandfläche − 2 × x“): Quadrat-/Rechteckrohr = Wandbreite
    − 2 × Außenradius der Ecken − 2 × Randabstand, höchstens die Wand innen; Rundrohr = Außen-Ø − 2 × Randabstand.
    rand leer = NASE_RAND."""
    from .optimierung import aussenradius
    form, a, b, s = _profil(profil_s, "Stecker")
    bw = _z(wandbreite) or querschnitt(profil_s, waende)[0]
    x = _z(rand) if rand not in (None, "") else NASE_RAND
    if form == "Rundrohr":
        return bw - 2 * x
    r = aussenradius(form, a, b, s, r=(profil_s or {}).get("r_aussen"))
    return min(bw - 2 * r - 2 * x, bw - 2 * s)


def vorgaben(profil_s, einst=None, waende="quer"):
    """Vorgabewerte einer neuen Verbindung aus den Einstellungen (einst = {Name ohne 'steck_': Wert}, leer =
    Programmvorgabe): Anzahl, Nasenbreite = halbe Wandbreite des Steckers (mindestens steck_nase_min), Spiel,
    Überstand, senkrechter Stoß."""
    einst = einst or {}
    bw, _, _ = querschnitt(profil_s, waende)
    n = int(_z(einst.get("anzahl")) or ANZAHL)
    mind = _z(einst.get("nase_min")) if einst.get("nase_min") not in (None, "") else NASE_MIN
    rand = _z(einst.get("nase_rand")) if einst.get("nase_rand") not in (None, "") else NASE_RAND
    grenze = nase_max(profil_s, waende, rand)
    return dict(anzahl=n if n in ANZAHLEN else ANZAHL, bN=round(min(max(mind, bw / 2), grenze), 2), rand=rand,
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
    grenze = nase_max(profil_s, waende, v.get("rand"), bw)
    if grenze <= 0:
        raise ValueError("Steckverbindung: Wand des Steckers zu schmal für eine Nase (gerade Wandfläche − Rand).")
    gekuerzt = b_n > grenze + 1e-9          # zu breit: auf die gerade Wandfläche gekürzt
    b_n = min(b_n, grenze)
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
    if n == 1 and _z(v.get("nase_seite")) < 0:      # eine Nase auf der Gegenseite (nasen_wahl)
        lage = [(waende, -1)]
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
    gesamt = n + len(versatz_liste(v))      # mit den Nasen der Ecke (andere Aufnahme, nasen_wahl_ecke)
    return dict(lN=l_n, flanke=flanke, schlitze=schlitze, nasen=nasen, schlitz_l=schlitze[0][0],
                schlitz_b=schlitze[0][1], schlitz=laengen[0], ende_plus=2 * gesamt * flanke, laenge_plus=flanke,
                aufnahme_plus=sum(laengen), einstiche_plus=n, bN=b_n, anzahl=n, staerke=staerke,
                gekuerzt=round(grenze, 2) if gekuerzt else None)


def schlitz_zeilen(v, profil_a, profil_s):
    """Konturzeilen der Schlitze auf der Aufnahme (Rechteck, Lage x/seite/q, Quelle der Verbindung)."""
    from . import skizze as sk
    m = masse(v, profil_a, profil_s)
    rund = profil_a.get("form") == "Rundrohr"
    out = []
    for (dx, dq), (sl, sb) in zip(m["nasen"], m["schlitze"], strict=False):
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
    out = dict(id=v["id"], anzahl=m["anzahl"], bN=m["bN"], lN=round(m["lN"], 3), flanke=round(m["flanke"], 3),
               plus=round(m["ende_plus"], 3), laenge_plus=round(m["laenge_plus"], 3), waende=v.get("waende") or "quer")
    if m["anzahl"] == 1 and _z(v.get("nase_seite")) < 0:
        out["seite"] = -1
    if versatz_liste(v):        # Ecke: weitere Nasen am selben Ende (in die anderen Aufnahmen), Winkel zur ersten
        out["versatz"] = versatz_liste(v)
        out["anzahl"] = m["anzahl"] + len(out["versatz"])
    return out


def versatz_liste(v):
    """Winkel [°] der weiteren Nasen einer Ecke zur ersten (Feld 'versatz' der Verbindung bzw. des Blocks)."""
    x = (v or {}).get("versatz")
    return [round(_z(w), 1) for w in x] if isinstance(x, (list, tuple)) else []


def nasen(e):
    """Block 'nasen' eines Endes (dict der Eingaben a/b) oder None."""
    x = (e or {}).get("nasen") if isinstance(e, dict) else None
    return x if isinstance(x, dict) and x.get("id") else None


def entfernen(eingaben, vid):
    """Eingaben ohne die Schlitze und Nasen der Verbindung vid (Kopie). Ergebnis (Eingaben, Rohlänge weniger um)."""
    neu = dict(eingaben)
    weg = (quelle(vid), marke_quelle(vid))
    neu["konturen"] = [z for z in eingaben.get("konturen") or () if z.get("quelle") not in weg]
    weniger = 0.0
    for s in ("a", "b"):
        x = nasen(eingaben.get(s))
        if x and x["id"] == vid:
            neu[s] = {k: w for k, w in eingaben[s].items() if k != "nasen"}
            weniger += _z(x.get("laenge_plus"))
            if s == "a":
                _marken_schieben(neu, -_z(x.get("laenge_plus")))
    return neu, weniger


def _marken_schieben(e, dx):
    """Montagemarken am Ende E um dx verschieben, wenn das Teil an Ende A länger bzw. kürzer wird (Nasen), damit sie
    hinter dem Schnitt des Endes E bleiben."""
    if dx:
        e["konturen"] = [dict(z, x=round(_z(z.get("x")) + dx, 3)) if z.get("marke_ende") == "b" and
                         str(z.get("quelle") or "").startswith(MARKE + " ") else z for z in e.get("konturen") or ()]


def anwenden(v, eingaben_a, eingaben_s, profil_a, profil_s, laengen=None, hinweise=None):
    """Verbindung v auf die Eingaben der Aufnahme und des Steckers (beide Kopien, frühere Konturen derselben Verbindung
    fallen weg). Ergebnis (Eingaben Aufnahme, Eingaben Stecker, Änderung der Rohlänge des Steckers [mm]).
    Mit Montagemarke (v['marke'], P2) und laengen = (Rohlänge Aufnahme, Rohlänge Stecker vorher) kommt die Marke als
    Text-Gravur an beide Teile; passt sie nicht, steht der Grund in der Liste hinweise."""
    ende = (v.get("stecker") or {}).get("ende")
    if ende not in ("a", "b"):
        raise ValueError("Steckverbindung: Ende des Steckers (A oder E) fehlt.")
    a, _ = entfernen(eingaben_a, v["id"])
    s, weniger = entfernen(eingaben_s, v["id"])
    if v.get("schlitze") is not False:      # False: gleiches Teil, die Schlitze schneidet eine andere Verbindung
        a["konturen"] = list(a["konturen"]) + schlitz_zeilen(v, profil_a, profil_s)
    plus = -weniger
    if v.get("nasen") is not False:         # False: dieses Ende hat die Nasen schon aus einer anderen Verbindung
        blk = nasen_block(v, profil_a, profil_s)
        s[ende] = dict(s.get(ende) or {}, nasen=blk)
        plus += blk["laenge_plus"]
        if ende == "a":
            _marken_schieben(s, blk["laenge_plus"])
    if str(v.get("marke") or "").strip() and laengen:
        la, ls = laengen
        za, zs, h = marken_zeilen(v, a, s, profil_a, profil_s, la, None if ls is None else ls + plus)
        a["konturen"] = list(a["konturen"]) + za
        s["konturen"] = list(s.get("konturen") or []) + zs
        if hinweise is not None:
            hinweise.extend(h)
    return a, s, round(plus, 3)


# ------------------------------------------------------------------ Montagemarken (P2, A4)
MARKE = "Montagemarke"
MARKE_ABSTAND = 0.5             # zu Enden und Konturen wie die Gravur im STEP-Export (step_export.GRAVUR_ABSTAND)
MARKE_HOEHE = 10.0              # Vorgabe wie die Einstellung gravur_schrifthoehe


def marke_quelle(vid):
    """Quelle der Gravurzeilen einer Montagemarke (zählt nicht als Schlitz der Verbindung, siehe rollen)."""
    return f"{MARKE} {vid}"


def _marke_frei(qs, e, laenge, x, s, b, h):
    """True, wenn ein Text b × h (Mitte x längs, s am Umfang) mit Abstand zu Enden, Nasen und Konturen passt."""
    from . import skizze as sk
    if laenge is None or laenge <= 0:
        return False
    d = MARKE_ABSTAND
    za = (_z(((e.get("a") or {}).get("nasen") or {}).get("laenge_plus")) if nasen(e.get("a")) else 0.0)
    zb = (_z(((e.get("b") or {}).get("nasen") or {}).get("laenge_plus")) if nasen(e.get("b")) else 0.0)
    for ds in (-h / 2, 0.0, h / 2):
        (u, w), _ = qs.s_zu_uv((s + ds) % qs.umfang)
        if x - b / 2 - d < sk.schnitt_x(qs, e.get("a"), u, w) + za:
            return False
        if x + b / 2 + d > laenge - sk.schnitt_x(qs, e.get("b"), u, w) - zb:
            return False
    for k in sk.lagen(e.get("konturen") or (), laenge, qs):
        ein = k["eingabe"]             # alle Konturen, auch Gravuren und Marken anderer Verbindungen
        pts = sk.umriss_kontur(ein) or [(0.0, 0.0)]
        x0, x1 = k["x"] + min(p[0] for p in pts), k["x"] + max(p[0] for p in pts)
        m = sk.s_lage(qs, ein)
        s0, s1 = m + min(p[1] for p in pts), m + max(p[1] for p in pts)
        ds = (s - (s0 + s1) / 2 + qs.umfang / 2) % qs.umfang - qs.umfang / 2
        if x0 - d < x + b / 2 and x - b / 2 < x1 + d and abs(ds) < (s1 - s0) / 2 + h / 2 + d:
            return False
    return True


def marken_zeilen(v, e_a, e_s, profil_a, profil_s, laenge_a, laenge_s):
    """Montagemarke einer Verbindung: gleiche Zahl als Text-Gravur neben die Schlitze der Aufnahme (außerhalb des
    Steckers) und auf die Nasenwand des Steckers hinter dem Schnitt. Ergebnis (Zeilen Aufnahme, Zeilen Stecker,
    Hinweise). Höhe v['marke_h'] (Einstellung gravur_schrifthoehe)."""
    from . import gravur_text, rohr3d, skizze as sk
    from .schneidweg import TEXT_GRAVUR, mit_radius
    text_ = str(v.get("marke") or "").strip()
    h = _z(v.get("marke_h")) or MARKE_HOEHE
    b = gravur_text.masse(text_, h)[0]
    if not text_ or b <= 0:
        return [], [], []

    def zeile(x, seite, q=0.0):
        z = {"art": TEXT_GRAVUR, "text": text_, "hoehe": h, "x": round(x, 3), "seite": seite, "winkel": 0, "anzahl": 1,
             "quelle": marke_quelle(v["id"])}
        if q:
            z["q"] = round(q, 3)
        return z
    za, zs, hinweise = [], [], []
    # Aufnahme: neben dem Stecker, zuerst Richtung Ende E
    if v.get("schlitze") is not False and v.get("x") is not None:
        qs = sk.Querschnitt(mit_radius(profil_a, e_a))
        waende = v.get("waende") if v.get("waende") in WAENDE else WAENDE[0]
        bw, ab, _ = querschnitt(profil_s, waende)
        bw, ab = _z(v.get("wandbreite")) or bw, _z(v.get("abstand")) or ab
        sin = math.sin(math.radians(_z(v.get("winkel")) or 90.0))
        m = masse(v, profil_a, profil_s)
        halb = max([(ab if waende == "quer" else bw) / 2 / sin]
                   + [abs(dx) + sl / 2 for (dx, _), (sl, _) in zip(m["nasen"], m["schlitze"], strict=False)])
        seite = v.get("seite") or qs.seiten()[0]
        s = sk.s_lage(qs, dict(seite=seite))
        x0 = _z(v["x"])
        for vz in (1, -1):
            x = x0 + vz * (halb + MARKE_ABSTAND + b / 2 + 0.05)
            if _marke_frei(qs, e_a, laenge_a, x, s, b, h):
                za.append(zeile(x, seite))
                break
        else:
            hinweise.append(f"Montagemarke {text_}: kein Platz neben dem Stecker auf der Aufnahme, nicht graviert")
    # Stecker: Nasenwand, direkt hinter dem Schnitt des Endes
    ende = (v.get("stecker") or {}).get("ende")
    qs = sk.Querschnitt(mit_radius(profil_s, e_s))
    lage = rohr3d.nasen_lage(e_s.get(ende), qs) if nasen(e_s.get(ende)) else None
    w = lage[1][0] if lage else 0.0
    s = sk.naht_s(qs, w) or 0.0
    seite, q = sk.s_zu_seite(qs, s)
    plat = None
    if laenge_s:
        tiefe = max(sk.schnitt_x(qs, e_s.get(ende), *qs.s_zu_uv((s + ds) % qs.umfang)[0]) for ds in (-h / 2, 0, h / 2))
        tiefe += lage[0] if lage else 0.0
        x = tiefe + MARKE_ABSTAND + b / 2 + 0.05
        x = x if ende == "a" else laenge_s - x
        if _marke_frei(qs, e_s, laenge_s, x, s, b, h):
            plat = x
    if plat is None:
        hinweise.append(f"Montagemarke {text_}: kein Platz am Ende des Steckers, nicht graviert")
    else:
        zs.append(dict(zeile(plat, seite, q), marke_ende=ende))
    return za, zs, hinweise


def marke_naechste(verbindungen):
    """Nächste freie Zahl für eine neue Montagemarke (größte Zahl + 1)."""
    zahlen = [int(t) for t in (str(v.get("marke") or "").strip() for v in verbindungen or ()) if t.isdigit()]
    return str(max(zahlen, default=0) + 1)


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
    t = f"{n} Nase{'n' if n != 1 else ''} {zahl(_z(m['bN'] if m else v.get('bN')), 1)}"
    if m:
        t += f" × {zahl(m['lN'], 1)} mm, Schlitz {zahl(m['schlitz_l'], 2)} × {zahl(m['schlitz_b'], 2)} mm"
        if m.get("gekuerzt"):
            t += f" (Nase auf {zahl(m['gekuerzt'], 1)} mm gekürzt: gerade Wandfläche − 2 × Rand)"
    t += f", Spiel {zahl(_z(v.get('c')), 2)} mm"
    if _z(v.get("winkel")) and _z(v["winkel"]) < 90 - 1e-6:
        t += f", schräg {zahl(_z(v['winkel']), 1)}°"
    ohne = [n for n, k in (("Schlitze", "schlitze"), ("Nasen", "nasen")) if v.get(k) is False]
    if ohne:
        t += f"; {' und '.join(ohne)} schon aus einer gleichen Verbindung"
    return t


# ------------------------------------------------------------------ Nasen nur in die Stoßwand
WINKEL_RUND = 45.0      # Rundrohr als Aufnahme: Nase höchstens so weit (Grad am Umfang) neben der Mitte des Stoßes


def _nasen_passen(x, profil_s, k):
    """Passen die Nasen der Verbindung x an der Stelle k (Kontakt, siehe nasen_wahl)? Ergebnis: größte Nasenbreite,
    die passt (≤ bN), oder None."""
    from .optimierung import aussenradius
    profil_a = k["profil_a"]
    form_a, a_a, b_a, s_a = _profil(profil_a, "Aufnahme")
    c = _z(x.get("c"))
    rand = _z(x.get("rand")) if x.get("rand") not in (None, "") else NASE_RAND
    w, q, laenge, halb = (_z(k.get(n)) for n in ("w", "q", "laenge", "halb"))
    if form_a == "Rundrohr":
        grenze_q = halb * math.sin(math.radians(WINKEL_RUND))
    else:
        grenze_q = halb - aussenradius(form_a, a_a, b_a, s_a, r=profil_a.get("r_aussen")) - rand
    try:
        m = masse(x, profil_a, profil_s)
    except ValueError:
        return None
    b_n = m["bN"]
    waende = x.get("waende") if x.get("waende") in WAENDE else WAENDE[0]
    for i, (dx, dq) in enumerate(m["nasen"]):
        art = waende if i < 2 else WAENDE[1 - WAENDE.index(waende)]
        if art == "quer":           # Nasenbreite quer zur Achse der Aufnahme
            frei = 2 * (grenze_q - abs(q + dq) - c)
            if frei < 1e-9:
                return None
            b_n = min(b_n, frei)
            halb_l = m["staerke"] / 2 + c
        else:
            if abs(q) + abs(dq) + m["staerke"] / 2 + c > grenze_q + 1e-9:
                return None
            halb_l = b_n / 2 + c
        if w + dx - halb_l < s_a - 1e-9 or w + dx + halb_l > laenge - s_a + 1e-9:
            return None                 # über das Ende der Aufnahme hinaus
    return b_n


def nasen_wahl(v, profil_s, kontakte, nase_min=None):
    """Patrick 25.10.2026: Stecknasen nie in die Außenwand der Aufnahme, dann um 90° versetzt oder nur eine Nase.
    kontakte: alle Stöße desselben Steckerendes (gleiche Teile tragen dieselben Nasen), je dict(profil_a, w = Mitte
    längs ab Ende A der Aufnahme, q = Versatz quer auf der Stoßwand, laenge der Aufnahme, halb = halbe Breite der
    Stoßwand außen (Rundrohr: Radius), quer = (Wandbreite, Abstand) des Steckers für 'quer' aus seiner Einbaulage,
    phi = Richtung der Achse der Aufnahme am Stecker [°], 0 oben, wie baugruppe_ansicht.nasen_winkel). Jede Nase muss
    mit Breite und Spiel auf dem geraden Teil der Stoßwand liegen (Kastenprofil ohne Eckradius und Rand, Rundrohr
    höchstens WINKEL_RUND neben der Mitte) und innerhalb der Länge der Aufnahme. Reihenfolge: Vorgabe; um 90°
    versetzt; nur eine Nase (Wand quer zur Aufnahme, an allen Stößen dieselbe Wand des Steckers); die Nasenbreite
    dafür notfalls schmaler, nicht unter nase_min. Ergebnis (Werte für die Verbindung {waende, anzahl, bN,
    wandbreite, abstand}, Seite je Kontakt (1/−1, für nase_seite), Hinweis oder None) bzw. (None, None, Hinweis)."""
    if not kontakte:
        return dict(), [1], None
    form_s = _profil(profil_s, "Stecker")[0]
    mind = _z(nase_min) or NASE_MIN
    vorgabe = v.get("waende") if v.get("waende") in WAENDE else WAENDE[0]
    andere = WAENDE[1 - WAENDE.index(vorgabe)]
    n0 = int(_z(v.get("anzahl")) or ANZAHL)
    quer = kontakte[0].get("quer") or querschnitt(profil_s, "quer")[:2]

    def werte(waende, n):
        bw, ab = quer if waende == "quer" or form_s == "Rundrohr" else (quer[1], quer[0])
        return dict(waende=waende, anzahl=n, wandbreite=round(bw, 3), abstand=round(ab, 3))

    def breite(w_, seiten):
        b_n = _z(v.get("bN"))
        for k, sz in zip(kontakte, seiten, strict=False):
            x = dict(v, **w_)
            x.pop("nase_seite", None)
            if w_["anzahl"] == 1 and sz < 0:
                x["nase_seite"] = -1
            b = _nasen_passen(x, profil_s, k)
            if b is None or b < min(_z(v.get("bN")), mind) - 1e-9:
                return None
            b_n = min(b_n, b)
        return b_n

    def ergebnis(w_, seiten, b_n, text):
        geaendert = [text] if text else []
        if b_n < _z(v.get("bN")) - 1e-9:
            w_["bN"] = round(math.floor(b_n * 10) / 10, 1)
            geaendert.append(f"Nase {w_['bN']:g} mm breit")
        return w_, seiten, ("Nasen nur in die Stoßwand: " + ", ".join(geaendert)) if geaendert else None

    eins = [1] * len(kontakte)
    for waende, n, text in ((vorgabe, n0, None), (andere, n0, f"Nasen um 90° versetzt ({andere})"),
                            (vorgabe, 2, "2 Nasen"), (andere, 2, f"2 Nasen um 90° versetzt ({andere})")):
        if n == 4 and waende == andere:
            continue
        w_ = werte(waende, n)
        b_n = breite(w_, eins)
        if b_n is not None:
            return ergebnis(w_, eins, b_n, text)
    # nur eine Nase auf der Wand quer zur Aufnahme: an jedem Stoß die passende Seite, am Stecker dieselbe Wand
    w_ = werte("quer", 1)
    raster = 90.0 if form_s != "Rundrohr" else 1.0
    moeglich = None
    for k in kontakte:
        hier = set()
        for sz in (1, -1):
            if _breite_einzeln(v, w_, profil_s, k, sz, mind) is None:
                continue
            hier.add(round(((_z(k.get("phi")) + (0 if sz > 0 else 180)) % 360) / raster) * raster % 360)
        moeglich = hier if moeglich is None else moeglich & hier
    if moeglich:
        winkel = min(moeglich)
        seiten = [1 if round((_z(k.get("phi")) % 360) / raster) * raster % 360 == winkel else -1 for k in kontakte]
        b_n = breite(w_, seiten)
        if b_n is not None:
            return ergebnis(w_, seiten, b_n, "nur eine Nase")
    if len(kontakte) > 1:
        return None, None, ("keine Nasen: an gleichen Teilen passt keine gemeinsame Nasenlage in die Stoßwand "
                            "(Position teilen, dann neu stecken)")
    return None, None, "keine Nasen: keine Nase passt in die Stoßwand der Aufnahme"


def nasen_winkel_menge(werte, phi, form_s):
    """Winkel der Nasen am Stecker [°] (0 oben, wie baugruppe_ansicht.nasen_winkel) aus den Werten einer Verbindung
    und der Richtung phi der Aufnahme: für den Vergleich gleicher Teile (gleiche Menge = gleiche Nasen)."""
    raster = 90.0 if form_s != "Rundrohr" else 1.0
    w0 = _z(phi) + (90.0 if werte.get("waende") == WAENDE[1] else 0.0)
    n = int(_z(werte.get("anzahl")) or ANZAHL)
    if n == 1 and _z(werte.get("nase_seite")) < 0:
        w0 += 180.0
    schritt = {1: (0,), 2: (0, 180), 4: (0, 180, 90, 270)}.get(n, (0, 180)) + tuple(versatz_liste(werte))
    return tuple(sorted({round(((w0 + d) % 360) / raster) * raster % 360 for d in schritt}))


def _seite_grad(seite):
    """Seite einer Schlitzzeile als Winkel [°] (oben 0, vorne 90, …; Rundrohr aus dem Text) oder None."""
    from . import skizze as sk
    if seite in SEITEN_KASTEN:
        return SEITEN_KASTEN.index(seite) * 90.0
    try:
        return float(sk.winkel_aus_text(seite)) % 360 if seite else None
    except (TypeError, ValueError):
        return None


def gleich_lagen(muster_a, muster_b, schlitze, laenge, form, quadrat=False):
    """Gleiche Teile, die nur gedreht oder gewendet eingebaut sind (Rohr ohne eigene Konturen, gerade Enden): je
    Drehung d [°] um die Rohrachse und Wenden (Ende A <-> B) die Kennung der Nasen (muster_a/_b = (Winkelmenge, bN)
    oder None) und Schlitze (Zeilen mit x, seite) im so gedrehten Rohrsystem. Ergebnis [(Kennung, d, gewendet)],
    zuerst ohne Änderung; ohne sichere Umrechnung (Querversatz, schräge Schlitze) nur dieser Eintrag."""
    import json
    def kennung(d, wenden):
        def w_(w):
            w = (-w if wenden else w) - d
            return round(w % 360, 1) % 360
        ma, mb = (muster_b, muster_a) if wenden else (muster_a, muster_b)
        m = [None if x is None else [sorted(w_(w) for w in x[0]), x[1]] for x in (ma, mb)]
        zeilen = []
        for z in schlitze:
            g = _seite_grad(z.get("seite"))
            x = _z(z.get("x"))
            zeilen.append(json.dumps(dict({n: w for n, w in z.items() if n not in ("x", "seite")},
                                          x=round((laenge - x) if wenden else x, 1),
                                          seite=None if g is None else w_(g)), sort_keys=True))
        return json.dumps([m, sorted(zeilen)])
    out = [(kennung(0.0, False), 0.0, False)]
    if any(_z(z.get("q")) or z.get("winkel") not in (None, 0) or (z.get("seite") and
           _seite_grad(z.get("seite")) is None) for z in schlitze) or not laenge:
        return out
    if form == "Rundrohr":
        drehungen = {0.0} | {round(w_ % 360, 1) for x in (muster_a, muster_b) if x for w_ in x[0]} | {
            round(_seite_grad(z.get("seite")) or 0.0, 1) for z in schlitze}
        drehungen |= {round(-w % 360, 1) for w in drehungen}
    else:
        drehungen = [0.0, 90.0, 180.0, 270.0] if quadrat else [0.0, 180.0]
    for wenden in (False, True):
        for d in sorted(drehungen):
            if d or wenden:
                out.append((kennung(d, wenden), d, wenden))
    return out


def seite_drehen(seite, d, wenden):
    """Seite (Name oder Winkeltext) im mit lage_drehen geänderten Rohrsystem."""
    from . import skizze as sk
    g = _seite_grad(seite)
    if g is None:
        return seite
    g = round(((-g if wenden else g) - d) % 360, 1) % 360
    if seite in SEITEN_KASTEN:
        return SEITEN_KASTEN[int(round(g / 90.0)) % 4]
    return sk.winkel_text(g)


def lage_drehen(lage, d, wenden, laenge):
    """Einbaulage [Ende A, Achse, X] so ändern, dass ein Merkmal bei Winkel w des alten Rohrsystems im neuen bei
    (±w) − d liegt (gleich_lagen): erst Wenden (Drehung 180° um Y, Ende A an das alte Ende B), dann Drehung um d
    um die Achse."""
    o, z, x = list(lage[0:3]), list(lage[3:6]), list(lage[6:9])
    if wenden:
        o = [o[i] + laenge * z[i] for i in range(3)]
        z, x = [-v for v in z], [-v for v in x]
    y = [z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0]]
    c, s = math.cos(math.radians(d)), math.sin(math.radians(d))
    x = [c * x[i] + s * y[i] for i in range(3)]
    return [round(v, 9) for v in o + z + x]


def nasen_wahl_ecke(v, profil_s, kontakte, nase_min=None):
    """Ecke (Patrick 25.10.2026 „je Träger eine Nase, um 90° versetzt“): ein Steckerende stößt an mehrere Aufnahmen
    (z. B. Stütze unter zwei Trägern). Je Aufnahme genau eine Nase auf der Wand quer zu ihr, auf der Seite, die in
    die Stoßwand passt; zwei Nasen nie auf derselben Wand des Steckers. Die erste passende Verbindung trägt alle
    Nasen des Endes ('versatz' = Winkel der übrigen zur ersten), die anderen nur ihren Schlitz. kontakte wie bei
    nasen_wahl. Ergebnis (je Kontakt Werte {waende, anzahl 1, nase_seite, bN, wandbreite, abstand[, versatz],
    traegt} oder None, Hinweis)."""
    form_s = _profil(profil_s, "Stecker")[0]
    mind = _z(nase_min) or NASE_MIN
    raster = 90.0 if form_s != "Rundrohr" else 1.0
    standard = querschnitt(profil_s, "quer")[:2]

    def werte_von(k):           # je Aufnahme ihre Wand des Steckers (Rechteckrohr: Breite und Abstand je Richtung)
        quer = k.get("quer") or standard
        return dict(waende="quer", anzahl=1, wandbreite=round(quer[0], 3), abstand=round(quer[1], 3))
    w0 = werte_von(kontakte[0]) if kontakte else werte_von({})
    # das Modell zeichnet die versetzten Nasen mit dem Querschnitt der ersten: um 90° nur bei gleichen Wänden
    quadrat = abs(w0["wandbreite"] - w0["abstand"]) < 1e-6 or form_s == "Rundrohr"
    wahl, belegt = [], set()
    for k in kontakte:
        gefunden = None
        w_ = werte_von(k)
        for sz in (1, -1):
            b = _breite_einzeln(v, w_, profil_s, k, sz, mind)
            winkel = round(((_z(k.get("phi")) + (0 if sz > 0 else 180)) % 360) / raster) * raster % 360
            if not quadrat and belegt and any(round((winkel - w) % 180, 1) != 0 for w in belegt):
                continue
            if b is not None and winkel not in belegt:
                gefunden = (sz, b, winkel)
                break
        wahl.append(gefunden)
        if gefunden:
            belegt.add(gefunden[2])
    da = [g for g in wahl if g]
    if not da:
        return [None] * len(kontakte), "keine Nasen: an der Ecke passt keine Nase in die Stoßwände"
    b_n = min(g[1] for g in da)
    b_n = min(_z(v.get("bN")), round(math.floor(b_n * 10) / 10, 1))
    erste = next(i for i, g in enumerate(wahl) if g)
    out = []
    for i, g in enumerate(wahl):
        if not g:
            out.append(None)
            continue
        x = dict(werte_von(kontakte[i]), bN=b_n, traegt=i == erste)
        if g[0] < 0:
            x["nase_seite"] = -1
        if i == erste:
            rest = [round((h[2] - g[2]) % 360, 1) for j, h in enumerate(wahl) if h and j != erste]
            if rest:
                x["versatz"] = rest
        out.append(x)
    gedreht = any(round((g[2] - da[0][2]) % 180, 1) for g in da)
    text = "je Aufnahme eine Nase" + (", um 90° versetzt" if gedreht else ", gegenüber" if len(da) > 1 else "")
    if len(da) < len(kontakte):
        text += f", {len(kontakte) - len(da)} Aufnahme(n) ohne Nase"
    return out, "Nasen nur in die Stoßwand: " + text


def _breite_einzeln(v, w_, profil_s, k, seite, mind):
    x = dict(v, **w_)
    x.pop("nase_seite", None)
    if seite < 0:
        x["nase_seite"] = -1
    b = _nasen_passen(x, profil_s, k)
    return None if b is None or b < min(_z(v.get("bN")), mind) - 1e-9 else b


# ------------------------------------------------------------------ Editor der Baugruppe
SEITEN_KASTEN = ("oben", "vorne", "unten", "hinten")
SEITE_STEP = dict(zip(("0°", "90°", "180°", "270°"), SEITEN_KASTEN, strict=False))     # Seite der STEP-Messung (wie step.SEITE_KASTEN)
FELDER = ("x", "seite", "anzahl", "bN", "rand", "c", "ueberstand", "waende", "winkel", "wandbreite", "abstand", "schlitze",
          "nasen")


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
    out = {k: w for k, w in v.items() if k not in ("x", "seite", "wandbreite", "abstand", "schlitze", "nasen")}
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
