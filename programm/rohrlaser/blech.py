"""Blech-Editor: Richtpreis für Blech- und Kantteile vom Blechlaser (Patrick 22.10.2026).

Nur zur Kostenschätzung vorab (EK-Vorschlag eines Zukaufteils). Werkstoffe (Tabelle blech_werkstoffe), Schneiddaten
(Tabelle blechlaser) und Sätze (Einstellungen 'blech_…') sind eigene Daten; die Rohrlaser-Werkstoffe und
-Schneiddaten werden weder gelesen noch geschrieben.

Eingaben (JSON in positionen.technik, quelle QUELLE):
  werkstoff, dicke [mm], art ZUSCHNITT oder KANTTEIL, stueck
  Zuschnitt: form RECHTECK (laenge, breite, eckradius) oder POLYGON (punkte 'x,y; x,y; …')
  Kantteil: kantlaenge (Länge der Biegekanten) und schenkel [{laenge (Außenmaß), winkel (Biegewinkel zum
            nächsten Schenkel, + nach oben, − nach unten), radius (Innenradius, leer = Blechdicke)}]
  konturen: Innenkonturen wie im Schneidweg-Rechner (Bohrung, Senkung, Langloch, Rechteck, Polygon, sonstige)
            mit Anzahl, optional x/y = Mitte in der Abwicklung [mm]

Abwicklung je Biegung (Außenmaße, K-Faktor k, Innenradius r, Dicke s, Biegewinkel φ):
  Ausgleich v = 2·(r+s)·tan(φ/2) − π·φ/180·(r + k·s)   für φ ≤ 90°
  v = 2·(r+s) − π·φ/180·(r + k·s)                         für φ > 90°
  Abwicklungslänge = Σ Schenkel − Σ v
Richtpreis je Stück = (Material + Laser + Kanten + Rüsten je Stück) × (1 + Aufschlag); Material = Hüllrechteck ×
(1 + Verschnitt) × Dicke × Dichte × €/kg; Laserzeit = Außenkontur / Vorschub + Innenkonturen / Vorschub innen +
Einstiche × Einstechzeit."""
import json
import math

from . import schneidweg as sw

QUELLE = "Blech-Editor"
ZUSCHNITT, KANTTEIL = "Zuschnitt (flach)", "Kantteil"
ARTEN = (ZUSCHNITT, KANTTEIL)
RECHTECK, POLYGON = "Rechteck", "Polygon"
FORMEN = (RECHTECK, POLYGON)
KONTUR_ARTEN = (sw.BOHRUNG, sw.SENKUNG, sw.LANGLOCH, sw.RECHTECK, sw.POLYGON, sw.SONSTIGE)
K_FAKTOR = 0.33
GASE = ("N₂", "O₂")
EINSTELLUNGEN = {"blech_stundensatz": 120.0, "blech_ruesten": 30.0, "blech_verschnitt": 0.15, "blech_kantung": 1.20,
                 "blech_ruesten_kanten": 25.0, "blech_aufschlag": 0.15}

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


def biegungen(e, k=K_FAKTOR):
    """[(Lage der Biegelinie ab Anfang der Abwicklung, Winkel, Innenradius, Ausgleich)], Abwicklungslänge."""
    s = _z(e.get("dicke"))
    schenkel = [x for x in e.get("schenkel") or [] if _z(x.get("laenge")) > 0]
    out, pos = [], 0.0
    for i, x in enumerate(schenkel):
        pos += _z(x["laenge"])
        if i == len(schenkel) - 1 or not _z(x.get("winkel")):
            continue
        r = _z(x.get("radius")) if x.get("radius") not in (None, "") else s
        v = ausgleich(x["winkel"], r, s, k)
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
        return dict(laenge=lg, breite=breite, flaeche=lg * breite, aussen=2 * (lg + breite), biegungen=bg,
                    punkte=None)
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


def schneiddaten(zeilen, kategorie, dicke):
    """Passende Zeile der Blechlaser-Richtwerte (N₂ vor O₂, kleinste 'Dicke bis' ≥ Dicke) oder None."""
    for gas in GASE:
        passend = [z for z in zeilen if z.get("kategorie") == kategorie and z.get("gas") == gas
                   and _z(z.get("dicke_bis")) >= dicke - 1e-9 and _z(z.get("vorschub")) > 0]
        if passend:
            return min(passend, key=lambda z: _z(z["dicke_bis"]))
    return None


def rechnen(e, werkstoffe, laserdaten, einst=None):
    """Richtpreis. werkstoffe: {ID: Zeile blech_werkstoffe}; laserdaten: Zeilen blechlaser; einst: Werte der
    Einstellungen 'blech_…' (fehlende: EINSTELLUNGEN). Ergebnis dict mit fehler [Texte], zuschnitt, gewicht,
    schneidweg, einstiche, zeit [s], kosten {Material, Laser, Kanten, Rüsten}, summe, richtpreis (je Stück)."""
    w = dict(EINSTELLUNGEN, **{n: v for n, v in (einst or {}).items() if v is not None})
    erg = dict(fehler=[], zuschnitt=None, gewicht=None, gewicht_tafel=None, schneidweg=None, aussen=None, innen=None,
               einstiche=None, zeit=None, kosten={}, summe=None, richtpreis=None, gas=None, kantungen=0,
               konturen=[])
    wst = werkstoffe.get(e.get("werkstoff"))
    s = _z(e.get("dicke"))
    if not wst:
        erg["fehler"].append("Blech-Werkstoff wählen.")
    if s <= 0:
        erg["fehler"].append("Blechdicke eingeben.")
    k = _z((wst or {}).get("k_faktor")) or K_FAKTOR
    try:
        zs = zuschnitt(e, k)
    except ValueError as x:
        erg["fehler"].append(str(x))
        return erg
    erg["zuschnitt"] = zs
    innen, einstiche, loch = 0.0, 1, 0.0
    for i, z in enumerate(e.get("konturen") or [], 1):
        try:
            lg, huelle, n = sw.kontur(z)
        except ValueError as x:
            erg["fehler"].append(f"Kontur {i}: {x}")
            continue
        innen += lg * n
        einstiche += n
        loch += kontur_flaeche(z) * n
        erg["konturen"].append(dict(art=z.get("art"), anzahl=n, laenge=lg, huelle=huelle))
    erg.update(aussen=zs["aussen"], innen=innen, schneidweg=zs["aussen"] + innen, einstiche=einstiche,
               kantungen=len(zs["biegungen"]))
    if erg["fehler"]:
        return erg
    dichte = _z(wst.get("dichte"))
    erg["gewicht"] = max(zs["flaeche"] - loch, 0) * s * dichte / 1e6
    erg["gewicht_tafel"] = zs["laenge"] * zs["breite"] * (1 + _z(w["blech_verschnitt"])) * s * dichte / 1e6
    sd = schneiddaten(laserdaten, wst.get("kategorie"), s)
    if sd is None:
        erg["fehler"].append(f"Keine Blechlaser-Richtwerte für {wst.get('kategorie')} {s:g} mm "
                             "(Einstellungen → Blechlaser (Richtwerte)).")
        return erg
    erg["gas"] = sd.get("gas")
    v_innen = _z(sd.get("vorschub_innen")) or _z(sd["vorschub"]) / 2
    erg["zeit"] = (zs["aussen"] / _z(sd["vorschub"]) * 60 + innen / v_innen * 60
                   + einstiche * _z(sd.get("einstechzeit")))
    stueck = max(int(_z(e.get("stueck")) or 1), 1)
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
    0.8.22): jede Innenkontur an ihrer Stelle (x/y im Zuschnitt), freie Außenkontur als Polygon. Ältere Messungen:
    Zuschnitt als Rechteck der Hüllmaße, Bohrungen je Durchmesser, die übrigen Innenkonturen als sonstige Kontur mit
    ihrer mittleren Schnittlänge. Gekantet: Zuschnitt mit der Abwicklungsfläche (Breite = Fläche / Länge), die
    Schenkel misst der Import nicht (im Editor als Kantteil nachtragen)."""
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
                dicke=_z(b.get("dicke")), laenge=lg, breite=br, eckradius=0, stueck=max(int(_z(stueck) or 1), 1),
                konturen=konturen, schenkel=[], kantlaenge=lg)


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
    if e.get("art") == KANTTEIL:
        n = len(zs.get("biegungen") or [])
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
