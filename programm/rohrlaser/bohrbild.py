"""Bohrbild einer Position: Gewinde-Vorschläge, Senkungen und Fließlochbohrungen (Flowdrill) aus dem STEP-Import,
je Zeile im Dialog 'Bohrungen prüfen' bestätigt oder abgelehnt (positionen.bohrbild, JSON-Liste).

Zeile: {art, d, anzahl, status, …}; status offen / bestätigt / abgelehnt.
- art "Bohrung": Kernloch Ø d passt zu einem Gewinde (gewinde = 'M6'). Bestätigt = Gewinde wird geschnitten
  (Spalte Gewinde geprüft), abgelehnt = nur Bohrung.
- art "Senkung": Bohrung Ø d (der Laser schneidet sie, steht schon im Schneidweg), Senk-Ø D ist Nacharbeit.
  gravur = True: der Senk-Ø wird zusätzlich graviert (π × D je Senkung).
- art "Fließloch": Fließlochbohrung mit Kragen, Kernloch Ø d; der Laser schneidet nur eine Markierung, je nach laser
  ein Loch Ø 0,5 mm (Schneidweg, Einstich, Kontur klein) oder eine Gravur Ø 0,5 mm. gewinde = Vorschlag fürs
  Gewindeformen (Kernloch nach FLIESSLOCH_KERN). Abgelehnt = normale Bohrung Ø d, die der Laser schneidet.

Was eine Zeile am Schneidweg, an Einstichen, Gravur und Konturliste ändert (zusatz), steht beim Speichern in der
Position; geändert wird um den Unterschied zwischen alter und neuer Wahl (anwenden).
"""
import json
import math

from . import rechnen
from .stammdaten import FLIESSLOCH_LASER

OFFEN, BESTAETIGT, ABGELEHNT = "offen", "bestätigt", "abgelehnt"
LASER = FLIESSLOCH_LASER
GRAVUR, LOCH = LASER
MARKE_D = rechnen.MARKIERLOCH          # Ø der Markierung für Fließlochbohrungen [mm]
# Kernloch fürs Gewindeformen nach Fließlochbohrung (Richtwerte Flowdrill), nicht DIN 336
FLIESSLOCH_KERN = (("M5", 4.5), ("M6", 5.4), ("M8", 7.3), ("M10", 9.2), ("M12", 10.9), ("M16", 14.8))


def _paare(text, getrennt="/"):
    """'6.6/12.4:2|8:1' -> [((6.6, 12.4), 2), ((8.0,), 1)]"""
    out = []
    for teil in str(text or "").split("|"):
        if ":" not in teil:
            continue
        a, n = teil.rsplit(":", 1)
        try:
            out.append((tuple(float(x) for x in a.split(getrennt)), int(float(n))))
        except ValueError:
            continue
    return out


def _gewinde(d, tabelle, tol=0.05):
    return next((g for g, kern in tabelle if abs(d - kern) <= tol), None)


def aus_messung(m, gewinde, laser=GRAVUR):
    """Zeilen aus den Messwerten eines Teils (Spalten bohrungen, senkungen, fliessloecher); gewinde = [(Gewinde,
    Kernloch)] der Stammdaten. Alle Zeilen offen; laser = Vorgabe für Fließlochbohrungen."""
    out = []
    for (d,), n in _paare(m.get("bohrungen")):
        g = _gewinde(d, gewinde)
        if g:
            out.append(dict(art="Bohrung", d=d, anzahl=n, gewinde=g, status=OFFEN))
    for (d, dd), n in _paare(m.get("senkungen")):
        out.append(dict(art="Senkung", d=d, D=dd, anzahl=n, gravur=False, status=OFFEN))
    for (d,), n in _paare(m.get("fliessloecher")):
        out.append(dict(art="Fließloch", d=d, anzahl=n, gewinde=_gewinde(d, FLIESSLOCH_KERN, 0.15),
                        laser=laser if laser in LASER else GRAVUR, status=OFFEN))
    return out


def aus_position(p, gewinde):
    """Zeilen einer Position: gespeichertes Bohrbild, sonst aus der Spalte Gewinde-Vorschlag (ältere Importe und
    Schneidweg-Rechner); bereits eingetragenes Gewinde gilt als bestätigt."""
    liste = lesen(p.get("bohrbild"))
    if liste:
        return liste
    out = []
    kern = dict(gewinde)
    fertig = rechnen.gewinde_anzahl(p.get("gewinde"), [dict(gewinde=g) for g, _ in gewinde]) if p.get("gewinde") \
        else {}
    for teil in str(p.get("gewinde_vorschlag") or "").split(";"):
        n, _, g = teil.strip().partition("x")
        if g and n.strip().isdigit():
            out.append(dict(art="Bohrung", d=kern.get(g.strip()), anzahl=int(n), gewinde=g.strip(),
                            status=BESTAETIGT if fertig.get(g.strip()) else OFFEN))
    return out


def lesen(text):
    try:
        liste = json.loads(text) if text else []
    except (TypeError, ValueError):
        return []
    return [z for z in liste if isinstance(z, dict) and z.get("art")] if isinstance(liste, list) else []


def schreiben(liste):
    return json.dumps(liste, ensure_ascii=False, separators=(",", ":")) if liste else None


def zusatz(liste):
    """Was die Wahl am Schneidweg ändert: dict(schneidweg, einstiche, gravur [mm], konturen [(Hüllmaß, Länge)])."""
    out = dict(schneidweg=0.0, einstiche=0, gravur=0.0, konturen=[])
    for z in liste:
        n = int(z.get("anzahl") or 0)
        if z["art"] == "Senkung" and z.get("gravur") and z.get("status") != ABGELEHNT and z.get("D"):
            out["gravur"] += n * math.pi * float(z["D"])
        elif z["art"] == "Fließloch":
            if z.get("status") == ABGELEHNT:       # doch eine gelaserte Bohrung
                d = float(z.get("d") or 0)
            elif z.get("laser") == LOCH:
                d = MARKE_D
            else:
                out["gravur"] += n * math.pi * MARKE_D
                continue
            out["schneidweg"] += n * math.pi * d
            out["einstiche"] += n
            out["konturen"] += [(d, math.pi * d)] * n
    return out


def gewinde_text(liste):
    """Bestätigte Gewinde als Text der Spalte Gewinde geprüft ('4xM6; 2xM8'), sonst None."""
    summe = {}
    for z in liste:
        if z.get("status") == BESTAETIGT and z.get("gewinde"):
            summe[z["gewinde"]] = summe.get(z["gewinde"], 0) + int(z.get("anzahl") or 0)
    return "; ".join(f"{n}x{g}" for g, n in summe.items()) or None


def vorschlag_text(liste):
    """Alle Gewinde-Vorschläge (auch abgelehnte) als Text der Spalte Gewinde-Vorschlag."""
    summe = {}
    for z in liste:
        if z.get("gewinde"):
            summe[z["gewinde"]] = summe.get(z["gewinde"], 0) + int(z.get("anzahl") or 0)
    return "; ".join(f"{n}x{g}" for g, n in summe.items()) or None


def offen(liste):
    return sum(1 for z in liste if z.get("status", OFFEN) == OFFEN)


def dez(x):
    return f"{float(x):g}".replace(".", ",") if x not in (None, "") else ""


def text(liste):
    """Kurztext für die Spalte Bohrungen, z. B. '2x Senkung Ø6,6/12,4; 2x Flowdrill Ø7,3 (M8)'."""
    out = []
    for z in liste:
        if z["art"] == "Senkung":
            out.append(f"{z['anzahl']}x Senkung Ø{dez(z['d'])}/{dez(z.get('D'))}")
        elif z["art"] == "Fließloch":
            out.append(f"{z['anzahl']}x Flowdrill Ø{dez(z['d'])}"
                       + (f" ({z['gewinde']})" if z.get("gewinde") else ""))
    return "; ".join(out)


def _ohne(liste, weg):
    """Konturliste ohne die Einträge in weg (je Eintrag ein Vorkommen, gerundet wie im Text)."""
    rest = list(liste)
    for g, lg in weg:
        for i, (a, g2, l2) in enumerate(rest):
            if not a and round(g2, 2) == round(g, 2) and abs(l2 - round(lg, 1)) < 0.06:
                del rest[i]
                break
    return rest


def hand_gewinde(p, liste):
    """Teile von 'Gewinde geprüft', die zu keiner Zeile des Bohrbilds gehören (von Hand eingetragen), als Text."""
    namen = {z.get("gewinde") for z in liste if z.get("gewinde")}
    return "; ".join(t.strip() for t in str(p.get("gewinde") or "").split(";")
                     if t.strip() and t.strip().upper().partition("X")[2].strip() not in {n.upper() for n in namen})


def anwenden(p, neu, hand=None):
    """Feldänderungen der Position für das neue Bohrbild: Schneidweg, Einstiche, Innenkonturen, Gravur, Konturliste
    und Konturklassen um den Unterschied alt → neu, dazu Gewinde geprüft (bestätigte Gewinde + hand, None = die von
    Hand eingetragenen bleiben), Gewinde-Vorschlag und bohrbild."""
    alt_z, neu_z = zusatz(lesen(p.get("bohrbild"))), zusatz(neu)
    out = {}
    d_weg = neu_z["schneidweg"] - alt_z["schneidweg"]
    if abs(d_weg) > 1e-9:
        out["schneidweg"] = round(max(0.0, rechnen._n(p.get("schneidweg")) + d_weg), 1)
        out["innen"] = round(max(0.0, rechnen._n(p.get("innen")) + d_weg), 1)
    if neu_z["einstiche"] != alt_z["einstiche"]:
        out["einstiche"] = max(0, int(rechnen._n(p.get("einstiche"))) + neu_z["einstiche"] - alt_z["einstiche"])
    d_grav = neu_z["gravur"] - alt_z["gravur"]
    if abs(d_grav) > 1e-9:
        out["gravur"] = round(max(0.0, rechnen._n(p.get("gravur")) + d_grav), 1) or None
    if alt_z["konturen"] != neu_z["konturen"]:
        liste = _ohne(rechnen.konturen_lesen(p.get("konturen"), True), alt_z["konturen"])
        liste += [("", g, lg) for g, lg in neu_z["konturen"]]
        out["konturen"] = rechnen.konturen_text([(g, lg) for a, g, lg in liste if not a],
                                                [(a, g, lg) for a, g, lg in liste if a]) or None
        grenzen = rechnen.grenzen_lesen(p.get("kontur_grenzen"))
        if grenzen:
            out.update(rechnen.konturklassen([(g, lg) for a, g, lg in liste if not a], grenzen))
    hand = hand_gewinde(p, neu) if hand is None else str(hand).strip()
    out["gewinde"] = "; ".join(filter(None, [gewinde_text(neu), hand])) or None
    out["gewinde_vorschlag"] = vorschlag_text(neu)
    out["bohrbild"] = schreiben(neu)
    return out
