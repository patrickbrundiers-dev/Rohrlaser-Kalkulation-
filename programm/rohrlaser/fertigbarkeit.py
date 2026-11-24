"""Fertigbarkeit beim STEP-Import prüfen (Laserhub-Vergleich L1/L3, Patrick 20.11.2026 „Alles einbauen nach
Empfehlungen“; Grenzwerte je Maschine).

Laserhub nennt öffentlich Konstruktionsregeln für Rohrlaserteile (Loch und Steg mindestens 0,7 × Wand, Innenecken mit
Radius, Länge und Gewicht begrenzt). Diese Prüfung macht das mit den Werten der eigenen Maschine, bevor ein Teil ins
Angebot geht. Sie liest nur die vorhandene Messung (Konturen mit Umriss in der Abwicklung), misst nichts neu und
ändert nichts am Teil (Grundregel: Konturen 100 % wie STEP). Jeder Befund macht das Teil gelb mit Grund (nie rot, nie
automatisch geändert); „Passt“ im Prüfdialog bestätigt es wie jeden anderen Grund.

Grenzwerte der Maschine (Stammdaten → Maschinen, Gruppe „Fertigbarkeit“); leer = Vorgabe, 0 = Prüfung aus:
  fb_loch_faktor   kleinstes Loch bzw. schmalster Schlitz = Faktor × Wand (Vorgabe 0,7)
  fb_steg_faktor   schmalster Steg zwischen zwei Konturen bzw. zum geraden Rohrende = Faktor × Wand (Vorgabe 0,7)
  fb_eckradius     kleinster Innen-Eckradius [mm] (Vorgabe aus: scharfe Ecken im CAD schneidet der Laser mit dem
                   Strahlradius, Patricks Teile haben sie oft gewollt)
  fb_gravur_tiefe  tiefste Gravur, die der Laser macht [mm] (Vorgabe 0,5 wie die Messung); tiefer = Fräsen prüfen
Dazu die vorhandenen Maschinenfelder: Länge (max. Stange − Endbeschnitt − Greiferrest, kürzestes Teil min_teil) und
Hüllkreis (max./min. Hüllkreis-Ø).

Prüfregeln aus dem 247TailorSteel-Vergleich (Patrick 20.11.2026 „Alles einbauen nach Empfehlungen“; nur die Ideen
aus öffentlichen Infos, Grenzwerte eigene je Maschine):
  fb_gravur_abstand  Gravur mindestens so weit von jeder Schnittlinie (Kontur, gerades Rohrende), berührt sie nie
                     (Vorgabe 1,5 mm)
  fb_umfang_offen    Umfang offen ab diesem Anteil [%] (Vorgabe 15): ist der Umfang an keinem der 5 Prüfpunkte (beide
                     Enden, ¼, ½, ¾) geschlossen, ist das Teil ein offenes Profil und spannt nicht sicher
  fb_nm_profil/_wand Einnietmuttern (aus Zeichnung/Formular oder Zusatzarbeit) M4–M8 nur in Quadrat-/Rechteckrohr bis
                     Profilgröße 150 mm, Wand 0,5 bis 3 mm; Seite mindestens Loch + 2 × 2 × Wand, Loch mindestens
                     2 × Wand von anderen Konturen und dem Rohrende
  schneidtechnik     Standard der Maschine (2,5D oder XY), je Position abweichend; bei XY Loch im Rundrohr höchstens
  fb_xy_faktor       Faktor × Rohr-Ø (Vorgabe 0,5)

Ergebnis je Teil in m["_fertigbarkeit"]: [{regel, text, x, seite, wert, grenze}]; step.ampel nimmt die Texte als
Gründe, bauteil_analyse als Merkmale „Fertigbarkeit“.
"""
import math

LOCH_FAKTOR = 0.7
STEG_FAKTOR = 0.7
GRAVUR_TIEFE = 0.5
MARKIERLOCH = 0.5       # Markierloch Ø0,5 (Fließlochbohrung) ist gewollt kleiner als die Wand
ECKE_KNICK = 30.0       # Grad: ab so viel Richtungsänderung ohne Bogen gilt eine Ecke als scharf
ECKE_SEGMENT = 1.0      # mm: beide Kanten an der Ecke mindestens so lang (sonst ist es ein angenäherter Bogen)
GRAVUR_ABSTAND = 1.5
UMFANG_OFFEN = 15.0     # % des Umfangs
PRUEF_ENDE = 10.0       # mm: Prüfpunkt „Ende“ so weit vom Rohrende (höchstens ein Zehntel der Länge)
XY_FAKTOR = 0.5
NM_PROFIL = 150.0
NM_WAND = 3.0
NM_WAND_MIN = 0.5
NM_ABSTAND = 2.0        # × Wand
NM_LOCH = {"M4": 6.0, "M5": 7.0, "M6": 9.0, "M8": 11.0}     # Bohrung für Einnietmuttern (Flachrundkopf, Rundschaft)
NM_LOCH_TOL = 0.3
XY, ZWEIEINHALB_D = "XY", "2,5D"
GESCHLOSSEN = ("Rundrohr", "Quadratrohr", "Rechteckrohr", "Flachoval", "Halbflachoval", "Elliptisch")
MAX_BEFUNDE = 50        # je Teil (Rest als Zahl)
MAX_KONTUREN_STEG = 400  # mehr Konturen: Stegprüfung nur zum Rohrende (sonst zu langsam)

LOCH, SCHLITZ, STEG, STEG_ENDE, ECKE, GRAVUR, LAENGE, KURZ, HUELLE = (
    "Loch", "Schlitz", "Steg", "Steg zum Ende", "Innenecke", "Gravur", "Länge", "Kürzestes Teil", "Hüllkreis")
GRAVUR_RAND, UMFANG, XY_LOCH, NIETMUTTER = ("Gravur zur Schnittlinie", "Umfang offen", "Loch im Rundrohr (XY)",
                                            "Einnietmutter")

FELDER = ("fb_loch_faktor", "fb_steg_faktor", "fb_eckradius", "fb_gravur_tiefe", "fb_gravur_abstand",
          "fb_umfang_offen", "fb_nm_profil", "fb_nm_wand", "schneidtechnik", "fb_xy_faktor")


def _f(x, vorgabe=0.0):
    try:
        v = float(x)
        return v if math.isfinite(v) else vorgabe
    except (TypeError, ValueError):
        return vorgabe


def _leer(x):
    return x is None or (isinstance(x, str) and not x.strip())


def _z(x):
    return f"{round(_f(x), 2):g}".replace(".", ",")


def grenzen(maschine):
    """Grenzwerte aus der Maschinenzeile (leer = Vorgabe, 0 = aus)."""
    m = maschine or {}

    def wert(n, vorgabe):
        return vorgabe if _leer(m.get(n)) else _f(m.get(n))
    stange = _f(m.get("max_stange"))
    max_l = stange - _f(m.get("endbeschnitt")) - _f(m.get("greiferrest")) if stange > 0 else 0.0
    return dict(loch=wert("fb_loch_faktor", LOCH_FAKTOR), steg=wert("fb_steg_faktor", STEG_FAKTOR),
                eckradius=wert("fb_eckradius", 0.0), gravur=wert("fb_gravur_tiefe", GRAVUR_TIEFE),
                max_laenge=max_l, min_laenge=_f(m.get("min_teil")), max_hk=_f(m.get("max_huellkreis")),
                min_hk=_f(m.get("min_huellkreis")), maschine=str(m.get("maschinen_id") or ""),
                gravur_abstand=wert("fb_gravur_abstand", GRAVUR_ABSTAND), umfang=wert("fb_umfang_offen", UMFANG_OFFEN),
                nm_profil=wert("fb_nm_profil", NM_PROFIL), nm_wand=wert("fb_nm_wand", NM_WAND),
                xy=wert("fb_xy_faktor", XY_FAKTOR), technik=technik_von(m))


def technik_von(maschine, position=None):
    """Schneidtechnik: Position, sonst Standard der Maschine, sonst 2,5D."""
    for q in (position, maschine):
        t = str((q or {}).get("schneidtechnik") or "").strip().upper().replace(".", ",")
        if t in ("XY", "2,5D"):
            return XY if t == "XY" else ZWEIEINHALB_D
    return ZWEIEINHALB_D


# ---------------------------------------------------------------------------------------------- Geometrie (u, x)
def _punkte(d):
    out = []
    for p in d.get("umriss") or ():
        try:
            out.append((float(p[0]), float(p[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return out


def _box(pk):
    us, xs = [p[0] for p in pk], [p[1] for p in pk]
    return min(us), max(us), min(xs), max(xs)


def _punkt_strecke(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll <= 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / ll))
    return math.hypot(p[0] - ax - t * dx, p[1] - ay - t * dy)


def _innen(p, pk):
    """Punkt im Polygon (gerade Anzahl Schnitte = außen)."""
    n, drin = len(pk), False
    for i in range(n):
        (u1, x1), (u2, x2) = pk[i], pk[(i + 1) % n]
        if (x1 > p[1]) != (x2 > p[1]) and p[0] < (u2 - u1) * (p[1] - x1) / ((x2 - x1) or 1e-12) + u1:
            drin = not drin
    return drin


def abstand(a, b):
    """Kleinster Abstand zweier geschlossener Umrisse [mm] (0 bei Überschneidung)."""
    if len(a) < 2 or len(b) < 2:
        return math.inf
    if _innen(a[0], b) or _innen(b[0], a):
        return 0.0
    best = math.inf
    for p, q in ((a, b), (b, a)):
        n = len(q)
        for pt in p:
            for i in range(n):
                best = min(best, _punkt_strecke(pt, q[i], q[(i + 1) % n]))
    return best


def scharfe_ecken(pk):
    """Anzahl scharfer Innenecken eines Konturumrisses (Ecke ohne Bogen: zwei gerade Kanten ≥ ECKE_SEGMENT mit
    Knick ≥ ECKE_KNICK). Angenäherte Bögen (viele kurze Kanten) zählen nicht."""
    n, k = len(pk), 0
    if n < 3:
        return 0
    for i in range(n):
        a, b, c = pk[i - 1], pk[i], pk[(i + 1) % n]
        v1, v2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        if l1 < ECKE_SEGMENT or l2 < ECKE_SEGMENT:
            continue
        cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (l1 * l2)))
        if math.degrees(math.acos(cos)) >= ECKE_KNICK:
            k += 1
    return k


# ---------------------------------------------------------------------------------------------- Prüfung
def _befund(regel, text, d=None, wert=None, grenze=None, bereich=None):
    """bereich = (x0, x1) längs für die Markierung im 3D (Vorgabe: Ausdehnung der Kontur d)."""
    d = d or {}
    out = dict(regel=regel, text=text, wert=None if wert is None else round(wert, 2),
               grenze=None if grenze is None else round(grenze, 2))
    if d.get("z") is not None:
        out["x"] = round(_f(d.get("z")), 1)
    if d.get("seite"):
        out["seite"] = str(d["seite"])
    if bereich is None:
        pk = _punkte(d)
        bereich = (_box(pk)[2], _box(pk)[3]) if pk else None
    if bereich:
        out["x0"], out["x1"] = round(min(bereich), 1), round(max(bereich), 1)
    return out


def _ist_rohr(m):
    return bool(m.get("profilform")) and (m.get("bauteiltyp") or "Profil") == "Profil" and \
        (m.get("profilform") or "") not in ("Blech", "Blech gekantet", "Drehteil", "Frästeil", "Normteil")


def pruefen(m, maschine=None, technik=None):
    """Befunde eines gemessenen Teils (Liste, leer = fertigbar). technik = Schneidtechnik der Position (leer =
    Standard der Maschine)."""
    if m.get("fehler") or not _ist_rohr(m):
        return []
    g = grenzen(maschine)
    if technik:
        g["technik"] = technik_von(None, dict(schneidtechnik=technik))
    wand = _f(m.get("wandstaerke"))
    laenge = _f(m.get("laenge"))
    try:
        import json
        konturen = m.get("konturen_liste")
        konturen = json.loads(konturen) if isinstance(konturen, str) else (konturen or [])
    except (ValueError, TypeError):
        konturen = []
    konturen = [d for d in konturen if isinstance(d, dict)]
    out = []
    innen = [d for d in konturen if d.get("art") not in ("Ende A", "Ende B")]
    durch = [d for d in innen if d.get("durchgehend", True) and d.get("art") not in ("Gravur", "Sackbohrung")]
    # Loch bzw. Schlitz kleiner als Faktor × Wand
    if g["loch"] > 0 and wand > 0:
        grenze = g["loch"] * wand
        for d in durch:
            if d.get("art") == "Bohrung":
                dm = _f(d.get("durchmesser")) or _f(d.get("huellmass"))
                if MARKIERLOCH + 1e-6 < dm < grenze - 1e-6:
                    out.append(_befund(LOCH, f"Loch Ø {_z(dm)} mm kleiner als {_z(g['loch'])} × Wand {_z(wand)} mm",
                                       d, dm, grenze))
            else:
                br = min(x for x in (_f(d.get("breite")), _f(d.get("laenge"))) if x > 0) \
                    if (_f(d.get("breite")) > 0 or _f(d.get("laenge")) > 0) else 0.0
                if 0 < br < grenze - 1e-6:
                    out.append(_befund(SCHLITZ, f"{d.get('art') or 'Kontur'} {_z(br)} mm breit, kleiner als "
                                       f"{_z(g['loch'])} × Wand {_z(wand)} mm", d, br, grenze))
    # Steg zwischen Konturen derselben Wand und zum geraden Rohrende
    if g["steg"] > 0 and wand > 0:
        grenze = g["steg"] * wand
        formen = [(d, _punkte(d)) for d in durch]
        formen = [(d, pk, _box(pk)) for d, pk in formen if len(pk) >= 3]
        ende = {d.get("art"): d for d in konturen if d.get("art") in ("Ende A", "Ende B")}
        for d, pk, (u0, u1, x0, x1) in formen:
            for name, rand in (("Ende A", x0), ("Ende B", laenge - x1)):
                e = ende.get(name)
                if e is not None and (e.get("form") or "gerade") == "gerade" and abs(_f(e.get("gehrung"))) < 0.05 \
                        and -1e-6 < rand < grenze - 1e-6:
                    out.append(_befund(STEG_ENDE, f"Steg zum {name} {_z(rand)} mm, kleiner als {_z(g['steg'])} × "
                                       f"Wand {_z(wand)} mm", d, rand, grenze,
                                       (0.0, x1) if name == "Ende A" else (x0, laenge)))
        if len(formen) <= MAX_KONTUREN_STEG:
            formen.sort(key=lambda t: t[2][2])
            for i, (d, pk, (u0, u1, x0, x1)) in enumerate(formen):
                wa = set(d.get("waende") or ([d["seite"]] if d.get("seite") else []))
                for e, qk, (v0, v1, y0, y1) in formen[i + 1:]:
                    if y0 - x1 >= grenze:
                        break
                    we = set(e.get("waende") or ([e["seite"]] if e.get("seite") else []))
                    if wa and we and not (wa & we):
                        continue
                    if v0 - u1 >= grenze or u0 - v1 >= grenze:
                        continue
                    s = abstand(pk, qk)
                    if 1e-6 < s < grenze - 1e-6:
                        out.append(_befund(STEG, f"Steg {_z(s)} mm zwischen {d.get('art') or 'Kontur'} (x "
                                           f"{_z(d.get('z'))}) und {e.get('art') or 'Kontur'} (x {_z(e.get('z'))}), "
                                           f"kleiner als {_z(g['steg'])} × Wand {_z(wand)} mm", d, s, grenze,
                                           (min(x0, y0), max(x1, y1))))
    # scharfe Innenecken (nur mit Grenzwert)
    if g["eckradius"] > 0:
        for d in durch:
            if d.get("art") == "Bohrung":
                continue
            k = scharfe_ecken(_punkte(d))
            if k:
                out.append(_befund(ECKE, f"{d.get('art') or 'Kontur'}: {k} Innenecke(n) ohne Radius (mind. "
                                   f"{_z(g['eckradius'])} mm)", d, 0.0, g["eckradius"]))
    # Gravur tiefer als der Laser graviert (bleibt Gravur und Rohr, Patrick 17.11.2026; nur Hinweis)
    if g["gravur"] > 0:
        for d in innen:
            if d.get("art") == "Gravur" and _f(d.get("tiefe")) > g["gravur"] + 1e-6:
                out.append(_befund(GRAVUR, f"Gravur {_z(d.get('tiefe'))} mm tief: der Laser markiert bis "
                                   f"{_z(g['gravur'])} mm, tiefer nur gefräst – prüfen", d, _f(d.get("tiefe")),
                                   g["gravur"]))
    out += _gravur_abstand(innen, durch, konturen, laenge, g)
    out += _umfang(m, durch, laenge, g)
    out += _xy_loecher(m, durch, g)
    out += _nietmuttern(m, durch, konturen, laenge, wand, g)
    # Länge und Hüllkreis gegen die Maschine
    if g["max_laenge"] > 0 and laenge > g["max_laenge"] + 1e-6:
        out.append(_befund(LAENGE, f"Teil {_z(laenge)} mm länger als die Maschine aus einer Stange schneidet "
                           f"({_z(g['max_laenge'])} mm)", None, laenge, g["max_laenge"]))
    if g["min_laenge"] > 0 and 0 < laenge < g["min_laenge"] - 1e-6:
        out.append(_befund(KURZ, f"Teil {_z(laenge)} mm kürzer als das kürzeste Teil der Maschine "
                           f"({_z(g['min_laenge'])} mm)", None, laenge, g["min_laenge"]))
    hk = huellkreis(m)
    if hk and g["max_hk"] > 0 and hk > g["max_hk"] + 1e-6:
        out.append(_befund(HUELLE, f"Hüllkreis Ø {_z(hk)} mm größer als die Maschine spannt "
                           f"(max. {_z(g['max_hk'])} mm)", None, hk, g["max_hk"]))
    if hk and g["min_hk"] > 0 and hk < g["min_hk"] - 1e-6:
        out.append(_befund(HUELLE, f"Hüllkreis Ø {_z(hk)} mm kleiner als die Maschine spannt "
                           f"(min. {_z(g['min_hk'])} mm)", None, hk, g["min_hk"]))
    if len(out) > MAX_BEFUNDE:
        rest = len(out) - MAX_BEFUNDE
        out = out[:MAX_BEFUNDE] + [dict(regel="mehr", text=f"… und {rest} weitere Befunde")]
    return out


def _gerade_enden(konturen):
    return {d.get("art") for d in konturen if d.get("art") in ("Ende A", "Ende B")
            and (d.get("form") or "gerade") == "gerade" and abs(_f(d.get("gehrung"))) < 0.05}


def _naechste(pk, box, durch, ausser=None):
    """(Abstand, Kontur) zur nächsten Schnittkontur, nur für Konturen in der Nähe (Hüllbox ± 50 mm)."""
    u0, u1, x0, x1 = box
    best, wer = math.inf, None
    for d in durch:
        if d is ausser:
            continue
        qk = _punkte(d)
        if len(qk) < 3:
            continue
        v0, v1, y0, y1 = _box(qk)
        if y0 - x1 > 50 or x0 - y1 > 50 or v0 - u1 > 50 or u0 - v1 > 50:
            continue
        s = abstand(pk, qk)
        if s < best:
            best, wer = s, d
    return best, wer


def _gravur_abstand(innen, durch, konturen, laenge, g):
    """Gravur mit Mindestabstand zu jeder Schnittlinie; berührt sie nie (247TailorSteel-Vergleich)."""
    out, ga = [], g["gravur_abstand"]
    if ga <= 0:
        return out
    gerade = _gerade_enden(konturen)
    for d in innen:
        pk = _punkte(d)
        if d.get("art") != "Gravur" or len(pk) < 3:
            continue
        box = _box(pk)
        s, wer = _naechste(pk, box, durch)
        name = f"{wer.get('art') or 'Kontur'} (x {_z(wer.get('z'))})" if wer is not None else ""
        for ende, rand in (("Ende A", box[2]), ("Ende B", laenge - box[3])):
            if ende in gerade and rand < s:
                s, name = max(rand, 0.0), f"dem {ende}"
        if s < ga - 1e-6:
            text = (f"Gravur berührt die Schnittlinie von {name}" if s <= 0.05 else
                    f"Gravur {_z(s)} mm neben {name}, mindestens {_z(ga)} mm")
            out.append(_befund(GRAVUR_RAND, text, d, s, ga))
    return out


def umfang_mm(m):
    """Umfang des Profils [mm] (Rundrohr π·D, sonst 2·(A + B), Ovale angenähert)."""
    a, b = _f(m.get("abm_a")), _f(m.get("abm_b"))
    if a <= 0:
        return 0.0
    form = m.get("profilform") or ""
    if form == "Rundrohr" or (b <= 0 and form != "Quadratrohr"):
        return math.pi * a
    b = b if b > 0 else a
    if form in ("Flachoval", "Elliptisch", "Halbflachoval"):
        return 2 * (a - b) + math.pi * b if a >= b else 2 * (b - a) + math.pi * a
    return 2 * (a + b)


def pruefpunkte(laenge):
    """Die 5 Prüfpunkte längs: beide Enden (PRUEF_ENDE, höchstens L/10), ¼, ½, ¾."""
    e = min(PRUEF_ENDE, laenge / 10)
    return [e, laenge / 4, laenge / 2, 3 * laenge / 4, laenge - e]


def _umfang(m, durch, laenge, g):
    """Offenes Profil: an keinem der 5 Prüfpunkte ist der Umfang geschlossen (247TailorSteel-Vergleich: U-Profile und
    Schalen spannen nur, wenn der Umfang irgendwo geschlossen ist)."""
    if g["umfang"] <= 0 or (m.get("profilform") or "") not in GESCHLOSSEN or laenge <= 0:
        return []
    u = umfang_mm(m)
    if u <= 0:
        return []
    boxen = [_box(pk) for pk in (_punkte(d) for d in durch) if len(pk) >= 3]
    offen = []
    for x in pruefpunkte(laenge):
        breite = sum(b[1] - b[0] for b in boxen if b[2] < x < b[3])
        offen.append(breite)
        if breite < g["umfang"] / 100 * u - 1e-6:
            return []
    return [_befund(UMFANG, f"Umfang an keinem der 5 Prüfpunkte geschlossen (Enden, ¼, ½, ¾; mind. "
                    f"{round(min(offen) / u * 100):d} % offen): offenes Profil, spannt nicht sicher – prüfen", None,
                    min(offen) / u * 100, g["umfang"], (0.0, laenge))]


def _xy_loecher(m, durch, g):
    """Schneidtechnik XY: Löcher im Rundrohr zylindrisch, höchstens Faktor × Rohr-Ø (247TailorSteel-Vergleich)."""
    if g["technik"] != XY or g["xy"] <= 0 or (m.get("profilform") or "") != "Rundrohr":
        return []
    big_d = _f(m.get("abm_a"))
    grenze = g["xy"] * big_d
    out = []
    for d in durch:
        if d.get("art") != "Bohrung":
            continue
        dm = _f(d.get("durchmesser")) or _f(d.get("huellmass"))
        if big_d > 0 and dm > grenze + 1e-6:
            out.append(_befund(XY_LOCH, f"Loch Ø {_z(dm)} mm größer als {_z(g['xy'])} × Rohr-Ø {_z(big_d)} mm: mit "
                               "XY nicht zylindrisch schneidbar – 2,5D wählen oder prüfen", d, dm, grenze))
    return out


def nietmuttern(m):
    """Einnietmuttern des Teils: [(Gewinde oder None, Anzahl oder None, Quelle)] aus Zeichnung/Formular
    (m["_zeichnung_text"]) und Zusatzarbeiten des Imports (m["_zusatz"])."""
    out = []
    if m.get("_zeichnung_text"):
        from . import zeichnung_hinweise as zh
        for h in zh.lesen(m["_zeichnung_text"]):
            if h.get("art") == zh.NIETMUTTER:
                out.append((h.get("gewinde"), h.get("anzahl"), m.get("_zeichnung_quelle") or "Zeichnung"))
    if not out:
        for z in m.get("_zusatz") or ():
            name = z.get("name") if isinstance(z, dict) else z
            if "nietmutter" in str(name or "").lower():
                out.append((None, None, f"Zusatzarbeit {name}"))
                break
    return out


def _nietmuttern(m, durch, konturen, laenge, wand, g):
    """Einnietmuttern: M4–M8, nur Quadrat-/Rechteckrohr bis Profilgröße, Wand 0,5 bis Grenze, Seite hoch genug, Loch
    2 × Wand von Konturen und Rohrende (247TailorSteel-Vergleich; eigene Grenzwerte je Maschine)."""
    nm = nietmuttern(m)
    if not nm:
        return []
    out, form = [], m.get("profilform") or ""
    a, b = _f(m.get("abm_a")), _f(m.get("abm_b")) or _f(m.get("abm_a"))
    quelle = nm[0][2]
    if form not in ("Quadratrohr", "Rechteckrohr"):
        out.append(_befund(NIETMUTTER, f"Einnietmuttern ({quelle}) nur in Quadrat- oder Rechteckrohr, hier {form} – "
                           "prüfen"))
    elif g["nm_profil"] > 0 and max(a, b) > g["nm_profil"] + 1e-6:
        out.append(_befund(NIETMUTTER, f"Einnietmuttern nur bis Profil {_z(g['nm_profil'])} mm, hier "
                           f"{_z(a)} × {_z(b)} mm – prüfen", None, max(a, b), g["nm_profil"]))
    if g["nm_wand"] > 0 and wand > 0 and not NM_WAND_MIN - 1e-6 <= wand <= g["nm_wand"] + 1e-6:
        out.append(_befund(NIETMUTTER, f"Einnietmuttern nur für Wand {_z(NM_WAND_MIN)} bis {_z(g['nm_wand'])} mm, hier "
                           f"{_z(wand)} mm – prüfen", None, wand, g["nm_wand"]))
    for gew, _n, _q in nm:
        if gew and gew not in NM_LOCH:
            out.append(_befund(NIETMUTTER, f"Einnietmutter {gew}: nur M4 bis M8 – prüfen"))
            continue
        loch = NM_LOCH.get(gew or "")
        if not loch or wand <= 0:
            continue
        rand = NM_ABSTAND * wand
        if form in ("Quadratrohr", "Rechteckrohr") and min(a, b) < loch + 2 * rand - 1e-6:
            out.append(_befund(NIETMUTTER, f"Einnietmutter {gew}: Seite {_z(min(a, b))} mm zu schmal (Loch Ø "
                               f"{_z(loch)} + 2 × {_z(rand)} mm Rand)", None, min(a, b), loch + 2 * rand))
        gerade = _gerade_enden(konturen)
        for d in durch:
            dm = _f(d.get("durchmesser")) or _f(d.get("huellmass"))
            pk = _punkte(d)
            if d.get("art") != "Bohrung" or abs(dm - loch) > NM_LOCH_TOL or len(pk) < 3:
                continue
            box = _box(pk)
            s, wer = _naechste(pk, box, durch, ausser=d)
            name = f"{wer.get('art') or 'Kontur'} (x {_z(wer.get('z'))})" if wer is not None else ""
            for ende, r in (("Ende A", box[2]), ("Ende B", laenge - box[3])):
                if ende in gerade and r < s:
                    s, name = max(r, 0.0), f"zum {ende}"
            if s < rand - 1e-6:
                out.append(_befund(NIETMUTTER, f"Einnietmutter {gew} (Loch Ø {_z(dm)}): {_z(s)} mm "
                                   f"{'' if name.startswith('zum') else 'bis '}{name}, mindestens 2 × Wand = "
                                   f"{_z(rand)} mm", d, s, rand))
    return out


def xy_zu_gross(analyse, faktor=XY_FAKTOR):
    """Bohrungen der gespeicherten Analyse eines Rundrohrs, die bei XY zu groß sind (Ø > faktor × Rohr-Ø)."""
    k = (analyse or {}).get("kennzahlen") or {}
    big_d = _f(k.get("abm_a"))
    if k.get("profilform") != "Rundrohr" or big_d <= 0 or faktor <= 0:
        return []
    return [_f(x.get("d")) for x in (analyse or {}).get("merkmale") or ()
            if x.get("art") == "Bohrung" and _f(x.get("d")) > faktor * big_d + 1e-6]


def huellkreis(m):
    """Hüllkreis-Ø des Profils aus der Messung [mm] oder None (wie stammdaten.huellkreis)."""
    from .stammdaten import huellkreis as hk
    a, b = _f(m.get("abm_a")), _f(m.get("abm_b"))
    if a <= 0:
        return None
    try:
        return hk(dict(form=m.get("profilform"), a=a, b=b if b > 0 else None, wand=_f(m.get("wandstaerke")) or None))
    except Exception:       # noqa: BLE001
        return None


def markieren(messwerte, maschine=None):
    """Alle Teile prüfen und das Ergebnis in m["_fertigbarkeit"] merken (leere Liste = fertigbar)."""
    for m in messwerte or ():
        try:
            m["_fertigbarkeit"] = pruefen(m, maschine)
        except Exception as e:     # noqa: BLE001 – Prüfung ist Zusatz, darf den Import nie stören
            m["_fertigbarkeit"] = [dict(regel="fehler", text=f"Fertigbarkeit nicht geprüft: {e}")]
    return messwerte


def gruende(m, n=3):
    """Gründe für die Ampel (höchstens n Texte, Rest als Zahl)."""
    liste = [b.get("text") for b in (m.get("_fertigbarkeit") or ()) if b.get("text")]
    if not liste:
        return []
    kurz = liste[:n]
    if len(liste) > n:
        kurz.append(f"{len(liste) - n} weitere")
    return ["Fertigbarkeit: " + "; ".join(kurz)]
