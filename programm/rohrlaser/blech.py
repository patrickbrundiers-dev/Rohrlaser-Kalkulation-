"""Blech-Editor: Richtpreis für Blech- und Kantteile vom Blechlaser (Patrick 22.10.2026).

Nur zur Kostenschätzung vorab (EK-Vorschlag eines Zukaufteils). Werkstoffe (Tabelle blech_werkstoffe), Schneiddaten
(Tabelle blechlaser) und Sätze (Einstellungen 'blech_…') sind eigene Daten; die Rohrlaser-Werkstoffe und
-Schneiddaten werden weder gelesen noch geschrieben.

Eingaben (JSON in positionen.technik, quelle QUELLE):
  werkstoff, dicke [mm], art ZUSCHNITT oder KANTTEIL, stueck
  Zuschnitt: form RECHTECK (laenge, breite, eckradius) oder POLYGON (punkte 'x,y; x,y; …')
  Kantteil: kantlaenge (Länge der Biegekanten) und schenkel [{laenge (Außenmaß), winkel (Biegewinkel zum
            nächsten Schenkel, + nach oben, − nach unten), radius (Innenradius, leer = Blechdicke)}]; mit form
            POLYGON und punkte eine freie Außenkontur der Abwicklung (x längs der Kante, y ab Schenkel 1)
  Mehrachsig gekantet (STEP-Import, Schale, Kasten): Zuschnitt mit kantungen (Anzahl) und biegelinien [{punkte
            (Mittellinie [[x, y], [x, y]]), winkel, ba (Bogenlänge), radius (gemessener Innenradius, None = scharf)}] für Skizze, 3D-Ansicht
            und Kantbarkeit
  konturen: Innenkonturen wie im Schneidweg-Rechner (Bohrung, Senkung, Langloch, Rechteck, Polygon, sonstige)
            mit Anzahl, optional x/y = Mitte in der Abwicklung [mm]; Text-Gravur (text, hoehe, winkel, x/y, z. B. die
            Artikelnummer) wird nur graviert: Gravurlänge ÷ Vorschub Gravur der Richtwerte, kein Einstich
  step: True aus dem STEP-Import; der Blech-Editor ersetzt es beim ersten Öffnen durch die Eingaben wie gemessen
            (ohne stueck). Der Teile-Editor zeigt damit je Merkmal die Herkunft STEP oder manuell und setzt zurück.

Abwicklung je Biegung (Außenmaße, K-Faktor k, Innenradius r, Dicke s, Biegewinkel φ):
  Ausgleich v = 2·(r+s)·tan(φ/2) − π·φ/180·(r + k·s)   für φ ≤ 90°
  v = 2·(r+s) − π·φ/180·(r + k·s)                         für φ > 90°
  Abwicklungslänge = Σ Schenkel − Σ v
Richtpreis je Stück = (Material + Laser + Kanten + Rüsten je Stück) × (1 + Aufschlag); Material = Tafelbedarf der
Losgröße ÷ Stückzahl × Dicke × Dichte × €/kg (tafelbedarf: Hüllrechtecke mit Steg auf den Tafelformaten, volle Tafeln
ganz, die letzte nur mit ihrer belegten Fläche samt Rand; Einstellung 'pauschaler Verschnitt': Hüllrechteck ×
(1 + Verschnitt)); Laserzeit = Außenkontur / Vorschub + Innenkonturen / Vorschub innen +
Einstiche × Einstechzeit."""
import json
import math

from . import schneidweg as sw

QUELLE = "Blech-Editor"
ZUSCHNITT, KANTTEIL = "Zuschnitt (flach)", "Kantteil"
ARTEN = (ZUSCHNITT, KANTTEIL)
RECHTECK, POLYGON = "Rechteck", "Polygon"
FORMEN = (RECHTECK, POLYGON)
KONTUR_ARTEN = (sw.BOHRUNG, sw.SENKUNG, sw.LANGLOCH, sw.RECHTECK, sw.POLYGON, sw.SONSTIGE, sw.TEXT_GRAVUR)
K_FAKTOR = 0.33
GASE = ("N₂", "O₂")
ABWICKLUNG_K = ("K-Faktor-Tabelle", "je Werkstoff")       # Einstellung blech_abwicklung
MATERIAL_AUS = ("Tafelausnutzung", "pauschaler Verschnitt")  # Einstellung blech_material
EINSTELLUNGEN = {"blech_stundensatz": 120.0, "blech_ruesten": 30.0, "blech_verschnitt": 0.15, "blech_kantung": 1.20,
                 "blech_ruesten_kanten": 25.0, "blech_aufschlag": 0.15, "blech_abwicklung": ABWICKLUNG_K[0],
                 "blech_kant_v": 8.0, "blech_kant_schenkel": 0.7, "blech_kant_loch": 2.0, "blech_kant_radius": 0.5,
                 "blech_material": MATERIAL_AUS[0], "blech_tafeln": "3000 × 1500; 2500 × 1250",
                 "blech_tafel_rand": 10.0, "blech_tafel_steg": 5.0}
NICHT_GEPRUEFT = "Biegefolge und Werkzeugkollision prüft das Programm nicht"

_z = sw._z


def ausgleich(winkel, radius, dicke, k=K_FAKTOR):
    """Ausgleichswert v einer Biegung [mm] (Außenmaße der Schenkel)."""
    phi = abs(_z(winkel))
    if phi <= 0:
        return 0.0
    r, s = _z(radius), _z(dicke)
    bogen = math.pi * phi / 180 * (r + k * s)
    if phi <= 90:
        return 2 * (r + s) * math.tan(math.radians(phi) / 2) - bogen
    return 2 * (r + s) - bogen


def k_faktor(tabelle, kategorie, dicke, radius, vorgabe=K_FAKTOR):
    """K-Faktor aus der Tabelle blech_kfaktoren: Zeilen der Kategorie mit der kleinsten 'Dicke bis' ≥ Dicke, darin
    die kleinste 'Ri/s bis' ≥ Innenradius ÷ Dicke (größer als alle: die größte). Keine Zeile: vorgabe."""
    s = _z(dicke)
    zeilen = [z for z in tabelle or () if z.get("kategorie") == kategorie and _z(z.get("k_faktor")) > 0
              and _z(z.get("dicke_bis")) >= s - 1e-9]
    if not zeilen or s <= 0:
        return vorgabe
    d = min(_z(z["dicke_bis"]) for z in zeilen)
    zeilen = [z for z in zeilen if _z(z["dicke_bis"]) == d]
    ri_s = _z(radius) / s
    passend = [z for z in zeilen if _z(z.get("ri_s_bis")) >= ri_s - 1e-9]
    z = (min(passend, key=lambda z: _z(z["ri_s_bis"])) if passend
         else max(zeilen, key=lambda z: _z(z.get("ri_s_bis"))))
    return _z(z["k_faktor"])


def biegungen(e, k=K_FAKTOR):
    """[(Lage der Biegelinie ab Anfang der Abwicklung, Winkel, Innenradius, Ausgleich)], Abwicklungslänge.
    k: K-Faktor oder Funktion Innenradius -> K-Faktor (K-Faktor-Tabelle)."""
    s = _z(e.get("dicke"))
    schenkel = [x for x in e.get("schenkel") or [] if _z(x.get("laenge")) > 0]
    out, pos = [], 0.0
    for i, x in enumerate(schenkel):
        pos += _z(x["laenge"])
        if i == len(schenkel) - 1 or not _z(x.get("winkel")):
            continue
        r = _z(x.get("radius")) if x.get("radius") not in (None, "") else s
        v = ausgleich(x["winkel"], r, s, k(r) if callable(k) else k)
        out.append((pos - v / 2, _z(x["winkel"]), r, v))
        pos -= v
    return out, pos


def flaeche_polygon(pk):
    return abs(sum(pk[i][0] * pk[(i + 1) % len(pk)][1] - pk[(i + 1) % len(pk)][0] * pk[i][1]
                   for i in range(len(pk)))) / 2


def kontur_flaeche(e):
    """Fläche einer Innenkontur [mm²] (für das Gewicht; sonstige Kontur 0)."""
    art = e.get("art")
    if art in (sw.BOHRUNG, sw.SENKUNG):
        return math.pi * _z(e.get("d")) ** 2 / 4
    if art == sw.LANGLOCH:
        b = _z(e.get("b"))
        return (_z(e.get("l")) - b) * b + math.pi * b * b / 4
    if art == sw.RECHTECK:
        r = _z(e.get("r"))
        return _z(e.get("b")) * _z(e.get("h")) - (4 - math.pi) * r * r
    if art == sw.POLYGON:
        pk = sw.punkte(e.get("punkte"))
        return flaeche_polygon(pk) if len(pk) >= 3 else 0.0
    return 0.0


def zuschnitt(e, k=K_FAKTOR):
    """Ebener Zuschnitt: dict(laenge, breite (Hüllrechteck), flaeche, aussen (Schnittlänge Außenkontur), biegungen,
    punkte (Polygon oder None)). ValueError bei fehlenden Maßen."""
    s = _z(e.get("dicke"))
    if e.get("art") == KANTTEIL:
        lg = _z(e.get("kantlaenge"))
        schenkel = [x for x in e.get("schenkel") or [] if _z(x.get("laenge")) > 0]
        if lg <= 0:
            raise ValueError("Kantteil: Kantlänge fehlt.")
        if len(schenkel) < 2:
            raise ValueError("Kantteil: mindestens zwei Schenkel eingeben.")
        for x in schenkel[:-1]:
            if not 0 < abs(_z(x.get("winkel"))) <= 150:
                raise ValueError("Kantteil: Biegewinkel zwischen 1° und 150° (− = nach unten) eingeben.")
            r = _z(x.get("radius")) if x.get("radius") not in (None, "") else s
            if 2 * (r + s) * (1 if abs(_z(x["winkel"])) > 90 else math.tan(math.radians(abs(x["winkel"])) / 2)) \
                    >= _z(x["laenge"]) + 1e-9:
                raise ValueError(f"Kantteil: Schenkel {_z(x['laenge']):g} mm ist zu kurz für Radius und Dicke.")
        bg, breite = biegungen(e, k)
        if breite <= 0:
            raise ValueError("Kantteil: Abwicklung ergibt keine Länge.")
        erg = dict(laenge=lg, breite=breite, flaeche=lg * breite, aussen=2 * (lg + breite), biegungen=bg,
                   punkte=None, hinweise=[])
        pk = sw.punkte(e.get("punkte")) if e.get("form") == POLYGON else []
        if len(pk) >= 3:        # freie Außenkontur der Abwicklung (STEP-Import: Ausklinkungen, Laschen)
            xs, ys = [x for x, _ in pk], [y for _, y in pk]
            erg.update(flaeche=flaeche_polygon(pk), punkte=pk,
                       aussen=sum(math.dist(pk[i], pk[(i + 1) % len(pk)]) for i in range(len(pk))))
            if abs(max(xs) - min(xs) - lg) > 1 or abs(max(ys) - min(ys) - breite) > 1:
                erg["hinweise"].append(
                    f"Außenkontur {zahl_mm(max(xs) - min(xs))} × {zahl_mm(max(ys) - min(ys))} mm passt nicht zu "
                    f"Kantlänge × Abwicklung {zahl_mm(lg)} × {zahl_mm(breite)} mm: Polygon prüfen")
        return erg
    if e.get("form") == POLYGON:
        pk = sw.punkte(e.get("punkte"))
        if len(pk) < 3:
            raise ValueError("Polygon: mindestens 3 Eckpunkte x,y eingeben.")
        xs, ys = [x for x, _ in pk], [y for _, y in pk]
        return dict(laenge=max(xs) - min(xs), breite=max(ys) - min(ys), flaeche=flaeche_polygon(pk),
                    aussen=sum(math.dist(pk[i], pk[(i + 1) % len(pk)]) for i in range(len(pk))), biegungen=[],
                    punkte=pk)
    lg, br, r = _z(e.get("laenge")), _z(e.get("breite")), _z(e.get("eckradius"))
    if lg <= 0 or br <= 0:
        raise ValueError("Zuschnitt: Länge und Breite eingeben.")
    if 2 * r > min(lg, br):
        raise ValueError("Zuschnitt: Eckradius höchstens halbe Seite.")
    return dict(laenge=lg, breite=br, flaeche=lg * br - (4 - math.pi) * r * r,
                aussen=2 * (lg + br) - 8 * r + 2 * math.pi * r, biegungen=[], punkte=None)


def _halbmass(z):
    """Halbe Ausdehnung einer Innenkontur quer zu den Biegelinien (y) und größte halbe Ausdehnung [mm]."""
    art = z.get("art")
    if art in (sw.BOHRUNG, sw.SENKUNG):
        r = _z(z.get("d")) / 2
        return r, r
    if art == sw.LANGLOCH:
        lg, b = _z(z.get("l")), _z(z.get("b"))
        return (lg if z.get("quer") else b) / 2, max(lg, b) / 2
    if art == sw.RECHTECK:
        b, h = _z(z.get("b")), _z(z.get("h"))
        return h / 2, math.hypot(b, h) / 2
    if art == sw.POLYGON:
        try:
            pk = sw.punkte(z.get("punkte"))
        except ValueError:
            return None
        if len(pk) < 3:
            return None
        mx, my = sum(x for x, _ in pk) / len(pk), sum(y for _, y in pk) / len(pk)
        return max(abs(y - my) for _, y in pk), max(math.hypot(x - mx, y - my) for x, y in pk)
    return None


def _punkt_strecke(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy or 1.0)))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _innen(p, pk):
    """Punkt p im Polygon pk (Strahlverfahren)."""
    x, y = p
    drin = False
    for (x1, y1), (x2, y2) in zip(pk, pk[1:] + pk[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            drin = not drin
    return drin


def _abstand_rechteck(r, a, b):
    """Abstand der Strecke a–b vom achsparallelen Rechteck r = (x1, y1, x2, y2); 0 wenn sie es schneidet."""
    x1, y1, x2, y2 = r
    ecken = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
    if any(x1 <= px <= x2 and y1 <= py <= y2 for px, py in (a, b)):
        return 0.0
    def kreuz(p, q, u, v):
        def d(o, s, t):
            return (s[0] - o[0]) * (t[1] - o[1]) - (s[1] - o[1]) * (t[0] - o[0])
        return d(p, q, u) * d(p, q, v) < 0 and d(u, v, p) * d(u, v, q) < 0
    if any(kreuz(a, b, ecken[i], ecken[(i + 1) % 4]) for i in range(4)):
        return 0.0
    return min([_punkt_strecke(c, a, b) for c in ecken] +
               [_punkt_strecke(p, ecken[i], ecken[(i + 1) % 4]) for p in (a, b) for i in range(4)])


GRAVUR_ABSTAND = 0.5    # mm: Gravur mindestens so weit von Außenkontur, Innenkonturen und Biegelinien (Patrick)


def _gravur_hindernisse(e, z, k=K_FAKTOR):
    """(Außenkontur, Strecken, Kreise) für die Lage einer Text-Gravur z; None ohne Zuschnitt."""
    from . import gravur_text
    try:
        zs = zuschnitt(e, k)
    except ValueError:
        return None
    if not zs:
        return None
    pk = zs.get("punkte")
    if pk:
        rand = list(pk)
    else:
        lg, br = zs["laenge"], zs["breite"]
        rand = [(0.0, 0.0), (lg, 0.0), (lg, br), (0.0, br)]
    xs = [x for x, _ in rand]
    strecken = list(zip(rand, rand[1:] + rand[:1]))
    if e.get("art") == KANTTEIL:
        strecken += [((min(xs), lage), (max(xs), lage)) for lage, _, _, _ in zs.get("biegungen") or ()]
    else:
        for x in e.get("biegelinien") or ():
            try:
                (x1, y1), (x2, y2) = x["punkte"]
            except (TypeError, ValueError, KeyError):
                continue
            strecken.append(((x1, y1), (x2, y2)))
    kreise = []
    for k_ in e.get("konturen") or ():
        if k_ is z or k_.get("x") is None or k_.get("y") is None:
            continue
        if k_.get("art") == sw.TEXT_GRAVUR:
            bb, hh = gravur_text.masse(k_.get("text"), _z(k_.get("hoehe")))
            m = (None, math.hypot(bb, hh) / 2)
        else:
            m = _halbmass(k_)
        if m:
            kreise.append((_z(k_["x"]), _z(k_["y"]), m[1]))
    return rand, strecken, kreise


def _gravur_frei(hindernisse, cx, cy, b, h):
    """Kleinster Abstand des Hüllrechtecks b × h um (cx, cy) zu den Hindernissen [mm]; None, wenn es aus dem Blech
    ragt."""
    rand, strecken, kreise = hindernisse
    r = (cx - b / 2, cy - h / 2, cx + b / 2, cy + h / 2)
    if not all(_innen(c, rand) for c in ((r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3]))):
        return None
    frei = min(_abstand_rechteck(r, a, bb) for a, bb in strecken)
    for kx, ky, kr in kreise:
        dx, dy = max(r[0] - kx, 0, kx - r[2]), max(r[1] - ky, 0, ky - r[3])
        frei = min(frei, math.hypot(dx, dy) - kr)
    return frei


def gravur_masse(z):
    """(Breite, Höhe) des Hüllrechtecks einer Text-Gravur in der Abwicklung (90° = quer)."""
    from . import gravur_text
    b, h = gravur_text.masse(z.get("text"), _z(z.get("hoehe")))
    return (h, b) if round(_z(z.get("winkel"))) % 180 == 90 else (b, h)


def gravur_lage(e, z, k=K_FAKTOR, schritte=40):
    """Lage einer Text-Gravur z (text, hoehe) im Zuschnitt (Patrick 24.10.2026 F3a: Mitte der größten freien Fläche):
    das Hüllrechteck des Texts dort, wo es den größten Abstand zu Außenkontur, Innenkonturen (mit Lage) und
    Biegelinien hat; quer (90°), wenn es dort mehr Abstand hat. dict(x, y, winkel, frei = Abstand [mm]) im System der
    Innenkonturen, None ohne Zuschnitt oder Text oder wenn der Text nicht ins Blech passt."""
    hind = _gravur_hindernisse(e, z, k)
    b, h = gravur_masse(dict(z, winkel=0))
    if not hind or b <= 0:
        return None
    xs, ys = [x for x, _ in hind[0]], [y for _, y in hind[0]]
    mx, my = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    best = None
    for winkel, (bw, hw) in ((0, (b, h)), (90, (h, b))):
        for i in range(1, schritte):
            for j in range(1, schritte):
                cx = min(xs) + (max(xs) - min(xs)) * i / schritte
                cy = min(ys) + (max(ys) - min(ys)) * j / schritte
                frei = _gravur_frei(hind, cx, cy, bw, hw)
                if frei is None:
                    continue
                # gleich viel Platz: lieber waagerecht und näher an der Mitte
                wert = (round(frei, 1), -winkel, -math.hypot(cx - mx, cy - my))
                if best is None or wert > best[0]:
                    best = (wert, dict(x=round(cx, 1), y=round(cy, 1), winkel=winkel, frei=round(frei, 2)))
    return best[1] if best else None


def gravur_hinweise(e, k=K_FAKTOR):
    """Hinweise zu Text-Gravuren mit Lage, die aus dem Blech ragen oder näher als GRAVUR_ABSTAND an Kontur oder
    Biegelinie liegen."""
    out = []
    for i, z in enumerate(e.get("konturen") or (), 1):
        if z.get("art") != sw.TEXT_GRAVUR or z.get("x") is None or z.get("y") is None:
            continue
        hind = _gravur_hindernisse(e, z, k)
        b, h = gravur_masse(z)
        if not hind or b <= 0:
            continue
        frei = _gravur_frei(hind, _z(z["x"]), _z(z["y"]), b, h)
        if frei is None or frei < GRAVUR_ABSTAND - 1e-9:
            out.append(f"Kontur {i} Text-Gravur „{z.get('text') or ''}“: " +
                       ("ragt aus dem Blech" if frei is None else
                        f"nur {zahl_mm(max(frei, 0))} mm Abstand (mindestens {zahl_mm(GRAVUR_ABSTAND)} mm)") +
                       ", Lage oder Schrifthöhe ändern")
    return out


def kantbarkeit(e, zs, w=None):
    """Hinweise zur Kantbarkeit (Plan S4, Patrick 23.10.2026 „1a: Kantbarkeit als Hinweis“) nach den Regeln der
    Einstellungen 'blech_kant_…' (Faktor 0 = Regel aus): kleinster Schenkel (Außenmaß) ≥ Faktor × V-Öffnung
    (V = Faktor × Dicke), Abstand Innenkontur–Biegelinie ≥ Innenradius + Faktor × Dicke, Innenradius ≥ Faktor ×
    Dicke, Freischnitt an Biegeecken mehrachsig gekanteter Rechtecke. Biegefolge und Werkzeugkollision nicht."""
    w = dict(EINSTELLUNGEN, **{n: v for n, v in (w or {}).items() if v is not None})
    s = _z(e.get("dicke"))
    out = []
    if s <= 0 or not zs:
        return out
    kant = e.get("art") == KANTTEIL
    mehr = not kant and len(e.get("biegelinien") or ()) > 0
    if not kant and not mehr:
        return out
    v = _z(w.get("blech_kant_v")) * s
    radien = []
    if kant:
        schenkel = [x for x in e.get("schenkel") or [] if _z(x.get("laenge")) > 0]
        b_min = _z(w.get("blech_kant_schenkel")) * v
        if b_min > 0:
            kurz = [f"{i}" for i, x in enumerate(schenkel, 1) if _z(x["laenge"]) < b_min - 1e-9]
            if kurz:
                out.append(f"Kantbarkeit: Schenkel {', '.join(kurz)} kürzer als {zahl_mm(b_min)} mm "
                           f"(V-Öffnung {zahl_mm(v)} mm)")
        radien = [r for _, _, r, _ in zs.get("biegungen") or ()]
        linien = [((0.0, lage), (1.0, lage), r) for lage, _, r, _ in zs.get("biegungen") or ()]
    else:
        linien = []
        for x in e.get("biegelinien") or ():
            try:
                (x1, y1), (x2, y2) = x["punkte"]
            except (TypeError, ValueError, KeyError):
                continue
            r = _z(x.get("radius")) if x.get("radius") is not None else None    # gemessen (STEP), sonst = Dicke
            if r is not None:
                radien.append(r)
            linien.append(((x1, y1), (x2, y2), s if r is None else r))
    r_min = _z(w.get("blech_kant_radius")) * s
    if r_min > 0 and any(r < r_min - 1e-9 for r in radien):
        out.append(f"Kantbarkeit: Innenradius unter {zahl_mm(r_min)} mm ({zahl_mm(_z(w.get('blech_kant_radius')))} × "
                   "Dicke), Werkstoff und Werkzeug prüfen")
    faktor = _z(w.get("blech_kant_loch"))
    if faktor > 0 and linien:
        minx = min((x for x, _ in zs.get("punkte") or ()), default=0.0)
        miny = min((y for _, y in zs.get("punkte") or ()), default=0.0)
        nah = 0
        for z in e.get("konturen") or ():
            if z.get("x") is None or z.get("y") is None:
                continue
            m = _halbmass(z)
            if not m:
                continue
            cx, cy = _z(z["x"]) - minx, _z(z["y"]) - miny
            for (ax, ay), (bx, by), r in linien:
                if kant:
                    abstand = abs(cy - ay) - m[0]
                else:
                    ax, ay, bx, by = ax - minx, ay - miny, bx - minx, by - miny
                    lg = math.hypot(bx - ax, by - ay) or 1.0
                    abstand = abs((bx - ax) * (ay - cy) - (ax - cx) * (by - ay)) / lg - m[1]
                if abstand < r + faktor * s - 1e-9:
                    nah += 1
                    break
        if nah:
            out.append(f"Kantbarkeit: {nah} Innenkontur(en) näher als Innenradius + {zahl_mm(faktor)} × Dicke an einer "
                       "Biegelinie (verzieht sich beim Kanten)")
    if mehr and not zs.get("punkte"):
        richtungen = set()
        for (ax, ay), (bx, by), _ in linien:
            richtungen.add(round(math.degrees(math.atan2(by - ay, bx - ax))) % 180)
        if len(richtungen) > 1:
            out.append("Kantbarkeit: Biegelinien kreuzen sich, Außenkontur ohne Freischnitt an den Biegeecken")
    if out:
        out.append(f"Kantbarkeit: {NICHT_GEPRUEFT}")
    return out


def zahl_mm(x):
    return f"{round(float(x), 1):g}".replace(".", ",")


def kantungen(e, zs=None):
    """Anzahl Kantungen: Biegungen des Kantteils, beim mehrachsig gekanteten Zuschnitt die gezählten."""
    if e.get("art") == KANTTEIL:
        return len((zs or {}).get("biegungen") or biegungen(e)[0])
    return max(int(_z(e.get("kantungen"))), 0)


def schneiddaten(zeilen, kategorie, dicke):
    """Passende Zeile der Blechlaser-Richtwerte (N₂ vor O₂, kleinste 'Dicke bis' ≥ Dicke) oder None."""
    for gas in GASE:
        passend = [z for z in zeilen if z.get("kategorie") == kategorie and z.get("gas") == gas
                   and _z(z.get("dicke_bis")) >= dicke - 1e-9 and _z(z.get("vorschub")) > 0]
        if passend:
            return min(passend, key=lambda z: _z(z["dicke_bis"]))
    return None


def tafelformate(text):
    """Tafelformate aus der Einstellung 'blech_tafeln' ('3000 × 1500; 2500 × 1250'): [(Länge, Breite)], Länge ≥
    Breite, unlesbare Einträge fehlen."""
    out = []
    for teil in str(text or "").replace(",", ".").split(";"):
        zahlen = [x for x in teil.replace("×", " ").replace("x", " ").replace("X", " ").replace("*", " ").split()]
        try:
            l, b = (float(x) for x in zahlen)
        except ValueError:
            continue
        if l > 0 and b > 0:
            out.append((max(l, b), min(l, b)))
    return out


def _je_tafel(u, v, a, b):
    """Größte Anzahl gleicher Rechtecke a × b (mit Steg) auf der Fläche u × v (mit Steg): Raster in einer Lage plus
    Reststreifen gedreht, längs oder quer geteilt."""
    best = 0
    for p, q in ((a, b), (b, a)):
        for k in range(int(u // p) + 1):
            best = max(best, k * int(v // q) + int((u - k * p) // q) * int(v // p))
        for k in range(int(v // q) + 1):
            best = max(best, k * int(u // p) + int((v - k * q) // p) * int(u // q))
    return best


def _rest(m, u, v, a, b, steg, rand):
    """Kleinste belegte Fläche (Länge, Breite) samt Rand für m gleiche Teile als Raster, None = passt so nicht."""
    best = None
    for p, q in ((a, b), (b, a)):
        for reihen in range(1, int(v // q) + 1):
            spalten = math.ceil(m / reihen)
            if spalten * p > u + 1e-9:
                continue
            reihen_n = min(reihen, m)
            l, br = spalten * p - steg + 2 * rand, reihen_n * q - steg + 2 * rand
            if best is None or l * br < best[0] * best[1]:
                best = (l, br)
    return best


def tafelbedarf(laenge, breite, stueck, tafeln, rand=10.0, steg=5.0):
    """Tafelbedarf für stueck gleiche Teile mit dem Hüllrechteck laenge × breite [mm] (Plan S4, Tafelausnutzung):
    je Tafelformat volle Tafeln ganz und die letzte nur mit der belegten Fläche samt Rand; gewählt wird das Format
    mit der kleinsten Fläche. Ergebnis dict format (l, b), je_tafel, voll, rest (l, b) oder None, flaeche [mm²],
    tafeln (Anzahl, Rest als Anteil), ausnutzung (Teile ÷ Fläche); None, wenn das Teil auf keine Tafel passt."""
    n = max(int(stueck or 1), 1)
    a, b = _z(laenge) + steg, _z(breite) + steg
    best = None
    for l, br in tafeln:
        u, v = l - 2 * rand + steg, br - 2 * rand + steg
        je = _je_tafel(u, v, a, b)
        if je < 1:
            continue
        voll = (n - 1) // je                         # die letzte Tafel immer mit ihrer belegten Fläche
        rest = _rest(n - voll * je, u, v, a, b, steg, rand)
        if rest is None:                             # nur mit gemischter Lage: ganze Tafel
            voll += 1
        flaeche = voll * l * br + (rest[0] * rest[1] if rest else 0)
        if best is None or flaeche < best["flaeche"] - 1e-6:
            best = dict(format=(l, br), je_tafel=je, voll=voll, rest=rest, flaeche=flaeche,
                        tafeln=flaeche / (l * br), ausnutzung=n * _z(laenge) * _z(breite) / flaeche)
    return best


def rechnen(e, werkstoffe, laserdaten, einst=None):
    """Richtpreis. werkstoffe: {ID: Zeile blech_werkstoffe}; laserdaten: Zeilen blechlaser; einst: Werte der
    Einstellungen 'blech_…' (fehlende: EINSTELLUNGEN). Ergebnis dict mit fehler [Texte], zuschnitt, gewicht,
    schneidweg, einstiche, zeit [s], kosten {Material, Laser, Kanten, Rüsten}, summe, richtpreis (je Stück)."""
    w = dict(EINSTELLUNGEN, **{n: v for n, v in (einst or {}).items() if v is not None})
    erg = dict(fehler=[], zuschnitt=None, gewicht=None, gewicht_tafel=None, schneidweg=None, aussen=None, innen=None,
               einstiche=None, zeit=None, kosten={}, summe=None, richtpreis=None, gas=None, kantungen=0, gravur=0.0,
               konturen=[], hinweise=[], k_faktoren=[], tafel=None)
    wst = werkstoffe.get(e.get("werkstoff"))
    s = _z(e.get("dicke"))
    if not wst:
        erg["fehler"].append("Blech-Werkstoff wählen.")
    if s <= 0:
        erg["fehler"].append("Blechdicke eingeben.")
    k = _z((wst or {}).get("k_faktor")) or K_FAKTOR
    if w.get("blech_abwicklung") != ABWICKLUNG_K[1] and w.get("kfaktoren"):
        k = (lambda r, k0=k: k_faktor(w["kfaktoren"], (wst or {}).get("kategorie"), s, r, k0))
    try:
        zs = zuschnitt(e, k)
    except ValueError as x:
        erg["fehler"].append(str(x))
        return erg
    erg["zuschnitt"] = zs
    erg["k_faktoren"] = sorted({round(k(r) if callable(k) else k, 3) for _, _, r, _ in zs.get("biegungen") or ()})
    erg["hinweise"] = list(zs.get("hinweise") or ()) + kantbarkeit(e, zs, w) + gravur_hinweise(e, k)
    innen, einstiche, loch = 0.0, 1, 0.0
    for i, z in enumerate(e.get("konturen") or [], 1):
        try:
            lg, huelle, n = sw.kontur(z)
        except ValueError as x:
            erg["fehler"].append(f"Kontur {i}: {x}")
            continue
        if z.get("art") in sw.GRAVUREN:     # nur graviert: kein Einstich, kein Loch
            erg["gravur"] += lg * n
            erg["konturen"].append(dict(art=z.get("art"), anzahl=n, laenge=lg, huelle=huelle))
            continue
        innen += lg * n
        einstiche += n
        loch += kontur_flaeche(z) * n
        erg["konturen"].append(dict(art=z.get("art"), anzahl=n, laenge=lg, huelle=huelle))
    erg.update(aussen=zs["aussen"], innen=innen, schneidweg=zs["aussen"] + innen, einstiche=einstiche,
               kantungen=kantungen(e, zs))
    if erg["fehler"]:
        return erg
    dichte = _z(wst.get("dichte"))
    erg["gewicht"] = max(zs["flaeche"] - loch, 0) * s * dichte / 1e6
    stueck = max(int(_z(e.get("stueck")) or 1), 1)
    flaeche = zs["laenge"] * zs["breite"] * (1 + _z(w["blech_verschnitt"]))
    if w.get("blech_material") != MATERIAL_AUS[1]:
        erg["tafel"] = tafelbedarf(zs["laenge"], zs["breite"], stueck, tafelformate(w.get("blech_tafeln")),
                                   _z(w.get("blech_tafel_rand")), _z(w.get("blech_tafel_steg")))
        if erg["tafel"]:
            flaeche = erg["tafel"]["flaeche"] / stueck
        else:
            erg["hinweise"].append("Tafel: Zuschnitt passt auf kein Tafelformat, Material mit pauschalem Verschnitt")
    erg["gewicht_tafel"] = flaeche * s * dichte / 1e6
    sd = schneiddaten(laserdaten, wst.get("kategorie"), s)
    if sd is None:
        erg["fehler"].append(f"Keine Blechlaser-Richtwerte für {wst.get('kategorie')} {s:g} mm "
                             "(Einstellungen → Blechlaser (Richtwerte)).")
        return erg
    erg["gas"] = sd.get("gas")
    v_innen = _z(sd.get("vorschub_innen")) or _z(sd["vorschub"]) / 2
    erg["zeit"] = (zs["aussen"] / _z(sd["vorschub"]) * 60 + innen / v_innen * 60
                   + einstiche * _z(sd.get("einstechzeit")))
    if erg["gravur"] > 0:
        if _z(sd.get("vorschub_gravur")) > 0:
            erg["zeit"] += erg["gravur"] / _z(sd["vorschub_gravur"]) * 60
        else:
            erg["hinweise"].append(f"Gravur {erg['gravur']:.0f} mm ohne Zeit: Vorschub Gravur fehlt in den "
                                   f"Blechlaser-Richtwerten ({wst.get('kategorie')} {s:g} mm)")
    ruesten = _z(w["blech_ruesten"]) + (_z(w["blech_ruesten_kanten"]) if erg["kantungen"] else 0)
    erg["kosten"] = {"Material": erg["gewicht_tafel"] * _z(wst.get("preis_kg")),
                     "Laser": erg["zeit"] / 3600 * _z(w["blech_stundensatz"]),
                     "Kanten": erg["kantungen"] * _z(w["blech_kantung"]),
                     "Rüsten": ruesten / stueck}
    erg["summe"] = sum(erg["kosten"].values())
    erg["richtpreis"] = round(erg["summe"] * (1 + _z(w["blech_aufschlag"])), 2)
    return erg


def _zahl(x):
    return f"{round(float(x), 2):g}"


def _konturen_mit_lage(liste):
    """Innenkonturen mit Lage aus der STEP-Messung (blech.konturen_lage) als Zeilen des Editors: x/y = Mitte im
    Zuschnitt, Langloch quer, Rechteck mit Breite längs, sonst Polygon mit Eckpunkten um die Mitte."""
    out = []
    for k in liste:
        if not isinstance(k, dict) or k.get("x") is None or k.get("y") is None:
            continue
        z = dict(anzahl=1, x=round(_z(k["x"]), 1), y=round(_z(k["y"]), 1))
        art = k.get("art")
        if art == "Bohrung" and _z(k.get("durchmesser")) > 0:
            z.update(art=sw.BOHRUNG, d=round(_z(k["durchmesser"]), 2))
        elif art == "Langloch" and _z(k.get("laenge")) > 0:
            z.update(art=sw.LANGLOCH, l=round(_z(k["laenge"]), 2), b=round(_z(k.get("breite")), 2))
            if k.get("quer"):
                z["quer"] = True
        elif art == "Rechteck" and _z(k.get("laenge")) > 0:
            lg, br = round(_z(k["laenge"]), 2), round(_z(k.get("breite")), 2)
            z.update(art=sw.RECHTECK, b=br if k.get("quer") else lg, h=lg if k.get("quer") else br, r=0)
        elif art == "Polygon" and len(k.get("punkte") or ()) >= 3:
            z.update(art=sw.POLYGON, punkte="; ".join(f"{_zahl(x)},{_zahl(y)}" for x, y in k["punkte"]))
        else:
            z.update(art=sw.SONSTIGE, laenge=round(_z(k.get("schnittlaenge")), 1))
        out.append(z)
    return out


def aus_step(b, werkstoff, stueck=1):
    """Eingaben des Blech-Editors aus einem im STEP-Import gemessenen Blech b (step.blech). Mit Lage (Messung ab
    0.8.23): jede Innenkontur an ihrer Stelle (x/y im Zuschnitt), freie Außenkontur als Polygon. Gekantet mit
    Abwicklung (Messung ab 0.8.37): Kantteil mit Kantlänge, Schenkeln, Biegungen und den Konturen der Abwicklung;
    mehrachsig gekantet (Schale, Kasten) als Zuschnitt mit Außenkontur, gezählten Kantungen und Biegelinien.
    Ältere Messungen: Zuschnitt als Rechteck der Hüllmaße, Bohrungen je Durchmesser, die übrigen Innenkonturen als
    sonstige Kontur mit ihrer mittleren Schnittlänge; gekantet mit der Abwicklungsfläche (Breite = Fläche / Länge),
    die Schenkel im Editor als Kantteil nachtragen."""
    stueck = max(int(_z(stueck) or 1), 1)
    abw = b.get("abwicklung") if b.get("kontur") == "gekantet" else None
    if isinstance(abw, dict) and not abw.get("fehler") and _z(abw.get("laenge")) > 0:
        e = dict(quelle=QUELLE, werkstoff=werkstoff, dicke=_z(b.get("dicke")), stueck=stueck, eckradius=0,
                 konturen=_konturen_mit_lage(b.get("konturen_lage") or ()), form=RECHTECK, punkte=None,
                 laenge=round(_z(abw["laenge"]), 1), breite=round(_z(abw["breite"]), 1))
        if len(b.get("aussen_punkte") or ()) >= 3:
            e.update(form=POLYGON, punkte="; ".join(f"{_zahl(x)},{_zahl(y)}" for x, y in b["aussen_punkte"]))
        schenkel = abw.get("schenkel") or []
        if not abw.get("mehrachsig") and len(schenkel) >= 2:
            e.update(art=KANTTEIL, kantlaenge=round(_z(abw.get("kantlaenge") or abw["laenge"]), 1),
                     schenkel=[dict(laenge=round(_z(x.get("laenge")), 2), winkel=round(_z(x.get("winkel")), 1),
                                    radius=None if x.get("radius") is None else round(_z(x["radius"]), 2))
                               for x in schenkel])
        else:
            e.update(art=ZUSCHNITT, schenkel=[], kantlaenge=e["laenge"],
                     kantungen=int(_z(abw.get("kantungen")) or len(abw.get("biegelinien") or ())),
                     biegelinien=[dict(punkte=x.get("punkte"), winkel=x.get("winkel"), ba=x.get("ba"),
                                       radius=x.get("radius"))
                                  for x in abw.get("biegelinien") or () if len(x.get("punkte") or ()) == 2])
        return dict(e, step=True)
    lg, br = round(_z(b.get("laenge")), 1), round(_z(b.get("breite")), 1)
    gekantet = b.get("kontur") == "gekantet"
    if gekantet and _z(b.get("abwicklung_flaeche")) > 0 and lg > 0:
        br = round(_z(b["abwicklung_flaeche"]) / lg, 1)
    form, punkte = RECHTECK, None
    if not gekantet and len(b.get("aussen_punkte") or ()) >= 3:
        form, punkte = POLYGON, "; ".join(f"{_zahl(x)},{_zahl(y)}" for x, y in b["aussen_punkte"])
    konturen = [] if gekantet else _konturen_mit_lage(b.get("konturen_lage") or ())
    rest_n, rest_l = int(_z(b.get("innen", b.get("innenkonturen")))), _z(b.get("umfang_innen"))
    if konturen:
        rest_n = 0
    bo = b.get("bohrungen") or {}       # Messwerte {Ø: Anzahl}, JSON-Ergebnis [{durchmesser, anzahl}]
    for d, n in (() if konturen else bo.items() if isinstance(bo, dict) else
                 ((x.get("durchmesser"), x.get("anzahl")) for x in bo)):
        try:
            d, n = float(str(d).replace(",", ".")), int(_z(n))
        except ValueError:
            continue
        if d > 0 and n > 0:
            konturen.append(dict(art=sw.BOHRUNG, anzahl=n, d=round(d, 2), x=None, y=None))
            rest_n, rest_l = rest_n - n, rest_l - math.pi * d * n
    if rest_n > 0 and rest_l > 1:
        konturen.append(dict(art=sw.SONSTIGE, anzahl=rest_n, laenge=round(rest_l / rest_n, 1), x=None, y=None))
    return dict(quelle=QUELLE, art=ZUSCHNITT, form=form, punkte=punkte, werkstoff=werkstoff,
                dicke=_z(b.get("dicke")), laenge=lg, breite=br, eckradius=0, stueck=stueck,
                konturen=konturen, schenkel=[], kantlaenge=lg, step=True)


def lesen(text):
    """Gespeicherte Eingaben (positionen.technik) oder None, wenn sie nicht vom Blech-Editor sind."""
    try:
        d = json.loads(text) if text else None
    except (TypeError, ValueError):
        return None
    return d if isinstance(d, dict) and d.get("quelle") == QUELLE else None


def speichern(e):
    return json.dumps(dict(e, quelle=QUELLE), ensure_ascii=False)


def bezeichnung_vorschlag(e, zs=None):
    """z. B. 'Blech 200 × 100 × 3 S235JR' bzw. 'Kantteil 300 × 132 × 2 1.4301 2B (2 Kantungen)'."""
    zs = zs or {}
    s = f"{_z(e.get('dicke')):g}".replace(".", ",")
    werk = e.get("werkstoff") or ""
    n = kantungen(e, zs) if zs else 0
    if e.get("art") == KANTTEIL or n:
        return (f"Kantteil {_z(zs.get('laenge')):.0f} × {_z(zs.get('breite')):.0f} × {s} {werk} "
                f"({n} Kantung{'en' if n != 1 else ''})").strip()
    return f"Blech {_z(zs.get('laenge')):.0f} × {_z(zs.get('breite')):.0f} × {s} {werk}".strip()


def querschnitt(e):
    """Linienzug der Kantteil-Seitenansicht (Außenmaße, ohne Radien): [(x, y)] ab Schenkel 1 nach rechts."""
    pk, x, y, richtung = [(0.0, 0.0)], 0.0, 0.0, 0.0
    for sch in [z for z in e.get("schenkel") or [] if _z(z.get("laenge")) > 0]:
        x += _z(sch["laenge"]) * math.cos(math.radians(richtung))
        y += _z(sch["laenge"]) * math.sin(math.radians(richtung))
        pk.append((x, y))
        richtung += _z(sch.get("winkel"))
    return pk
