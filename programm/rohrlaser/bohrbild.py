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
- art "Bohren": Bohrung Ø d kleiner als 0,7 × Wandstärke (rechnen.KONTUR_MIN_WAND), die der Laser kaum sauber
  schneidet. Offen und abgelehnt schneidet der Laser sie wie gemessen; bestätigt markiert er nur (Gravur oder Loch
  Ø 0,5 wie beim Flowdrill), danach wird aufgebohrt.

Arbeitsschritt als Zusatzarbeit (ZUSATZ_ARBEIT): bestätigte Senkungen, Flowdrill und Bohren tragen beim Übernehmen
die Zusatzarbeiten Senken, Flowdrill bzw. Bohren mit der Anzahl je Teil in die Position ein (quelle = QUELLE);
offene und abgelehnte Zeilen nichts. Von Hand eingetragene Zusatzarbeiten gleichen Namens bekommen nur die Anzahl.

Was eine Zeile am Schneidweg, an Einstichen, Gravur und Konturliste ändert (zusatz), steht beim Speichern in der
Position; geändert wird um den Unterschied zwischen alter und neuer Wahl (anwenden).
"""
import json
import math

from . import rechnen
from .stammdaten import FLIESSLOCH_LASER, ZUSATZ_BOHREN, ZUSATZ_FLOWDRILL, ZUSATZ_SENKEN

OFFEN, BESTAETIGT, ABGELEHNT = "offen", "bestätigt", "abgelehnt"
LASER = FLIESSLOCH_LASER
GRAVUR, LOCH = LASER
MARKE_D = rechnen.MARKIERLOCH          # Ø der Markierung für Fließlochbohrungen [mm]
# Kernloch fürs Gewindeformen nach Fließlochbohrung (Richtwerte Flowdrill), nicht DIN 336
FLIESSLOCH_KERN = (("M5", 4.5), ("M6", 5.4), ("M8", 7.3), ("M10", 9.2), ("M12", 10.9), ("M16", 14.8))
BOHREN = "Bohren"
ZUSATZ_ARBEIT = {"Senkung": ZUSATZ_SENKEN, "Fließloch": ZUSATZ_FLOWDRILL, BOHREN: ZUSATZ_BOHREN}
QUELLE = "Bohrungen prüfen"         # Zusatzarbeit der Position stammt aus dem Bohrbild


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


def zu_klein(d, wand):
    """Bohrung Ø d kleiner als 0,7 × Wandstärke (nicht die Markierung Ø 0,5): Bohren vorschlagen."""
    return isinstance(wand, (int, float)) and wand > 0 and \
        MARKE_D < round(float(d or 0), 2) < round(rechnen.KONTUR_MIN_WAND * wand, 2)


def bohren_zeilen(bohrungen, wand, laser=GRAVUR, vorhanden=()):
    """Zeilen 'Bohren' für die Bohrungen [(Ø, Anzahl)] kleiner als 0,7 × Wandstärke, ohne die Ø in vorhanden."""
    summe = {}
    for d, n in bohrungen:
        if zu_klein(d, wand) and round(d, 2) not in vorhanden:
            summe[round(d, 2)] = summe.get(round(d, 2), 0) + int(n)
    return [dict(art=BOHREN, d=d, anzahl=n, laser=laser if laser in LASER else GRAVUR, status=OFFEN)
            for d, n in sorted(summe.items()) if n > 0]


def aus_messung(m, gewinde, laser=GRAVUR, wand=None):
    """Zeilen aus den Messwerten eines Teils (Spalten bohrungen, senkungen, fliessloecher); gewinde = [(Gewinde,
    Kernloch)] der Stammdaten. Alle Zeilen offen; laser = Vorgabe für Fließlochbohrungen und Bohren; mit wand
    (Wandstärke) zusätzlich Bohren für Bohrungen kleiner als 0,7 × Wand."""
    out = []
    bohrungen = [(d, n) for (d,), n in _paare(m.get("bohrungen"))]
    for d, n in bohrungen:
        g = _gewinde(d, gewinde)
        if g:
            out.append(dict(art="Bohrung", d=d, anzahl=n, gewinde=g, status=OFFEN))
    for (d, dd), n in _paare(m.get("senkungen")):
        out.append(dict(art="Senkung", d=d, D=dd, anzahl=n, gravur=False, status=OFFEN))
    for (d,), n in _paare(m.get("fliessloecher")):
        out.append(dict(art="Fließloch", d=d, anzahl=n, gewinde=_gewinde(d, FLIESSLOCH_KERN, 0.15),
                        laser=laser if laser in LASER else GRAVUR, status=OFFEN))
    return out + bohren_zeilen(bohrungen, wand, laser)


def aus_rechner(erg, alt, gewinde, wand=None, laser=GRAVUR):
    """Bohrbild nach dem Schneidweg-Rechner (Ergebnis schneidweg.rechnen): Gewinde-Vorschläge der Bohrungen,
    Senkungen und Bohren (< 0,7 × Wand) aus den Eingaben; Prüfstatus und Wahl der bisherigen Zeilen gleicher Art und
    gleichen Ø (alt) bleiben. Fließlochbohrungen kennt der Rechner nicht, sie fallen weg."""
    bohr, senk = {}, {}
    for s_ in erg.get("schritte", [])[2:]:
        e = s_.get("eingabe") or {}
        try:
            d = round(float(e.get("d")), 2)
        except (TypeError, ValueError):
            continue
        if s_.get("art") == "Bohrung":
            bohr[d] = bohr.get(d, 0) + int(s_["anzahl"])
        elif s_.get("art") == "Senkung" and isinstance(e.get("D"), (int, float)):
            schl = (d, round(float(e["D"]), 2))
            senk[schl] = senk.get(schl, 0) + int(s_["anzahl"])
    neu = [dict(art="Bohrung", d=d, anzahl=n, gewinde=_gewinde(d, gewinde), status=OFFEN)
           for d, n in sorted(bohr.items()) if _gewinde(d, gewinde)]
    neu += [dict(art="Senkung", d=d, D=dd, anzahl=n, gravur=False, status=OFFEN) for (d, dd), n in sorted(senk.items())]
    neu += bohren_zeilen(sorted(bohr.items()), wand, laser)
    vorher = {(z.get("art"), round(float(z.get("d") or 0), 2)): z for z in alt or ()}
    for z in neu:
        v = vorher.get((z["art"], z["d"]))
        if v:
            z.update({k: v[k] for k in ("status", "gewinde", "laser", "gravur") if k in v})
    return neu


def bohrungen_lesen(text):
    """Spalte Bohrungen der Position ('4xØ5; 1xØ10; 2x Senkung Ø6,6/12,4') -> [(5.0, 4), (10.0, 1)], nur einfache
    Bohrungen."""
    out = []
    for teil in str(text or "").split(";"):
        n, _, d = teil.strip().partition("xØ")
        try:
            out.append((float(d.replace(",", ".")), int(n)))
        except ValueError:
            continue
    return out


def ergaenzen(liste, p, wand, laser=GRAVUR):
    """Bohrbild um Zeilen 'Bohren' ergänzen, die es noch nicht gibt (Importe vor 0.8.12, Schneidweg-Rechner,
    andere Wandstärke): aus der Spalte Bohrungen der Position."""
    da = {round(float(z.get("d") or 0), 2) for z in liste if z.get("art") == BOHREN}
    return list(liste) + bohren_zeilen(bohrungen_lesen(p.get("bohrungen")), wand, laser, da)


def aus_position(p, gewinde, wand=None, laser=GRAVUR):
    """Zeilen einer Position: gespeichertes Bohrbild, sonst aus der Spalte Gewinde-Vorschlag (ältere Importe und
    Schneidweg-Rechner); bereits eingetragenes Gewinde gilt als bestätigt. Mit wand ergänzt um Bohren (ergaenzen)."""
    liste = lesen(p.get("bohrbild"))
    if liste:
        return ergaenzen(liste, p, wand, laser)
    out = []
    kern = dict(gewinde)
    fertig = rechnen.gewinde_anzahl(p.get("gewinde"), [dict(gewinde=g) for g, _ in gewinde]) if p.get("gewinde") \
        else {}
    for teil in str(p.get("gewinde_vorschlag") or "").split(";"):
        n, _, g = teil.strip().partition("x")
        if g and n.strip().isdigit():
            out.append(dict(art="Bohrung", d=kern.get(g.strip()), anzahl=int(n), gewinde=g.strip(),
                            status=BESTAETIGT if fertig.get(g.strip()) else OFFEN))
    return ergaenzen(out, p, wand, laser)


def lesen(text):
    try:
        liste = json.loads(text) if text else []
    except (TypeError, ValueError):
        return []
    return [z for z in liste if isinstance(z, dict) and z.get("art")] if isinstance(liste, list) else []


def schreiben(liste):
    return json.dumps(liste, ensure_ascii=False, separators=(",", ":")) if liste else None


def zusatz(liste):
    """Was die Wahl am Schneidweg ändert: dict(schneidweg, einstiche, gravur [mm], konturen [(Hüllmaß, Länge)]
    zusätzlich, weg [(Hüllmaß, Länge)] aus der gemessenen Konturliste entfernt)."""
    out = dict(schneidweg=0.0, einstiche=0, gravur=0.0, konturen=[], weg=[])
    for z in liste:
        n = int(z.get("anzahl") or 0)
        if z["art"] == "Senkung" and z.get("gravur") and z.get("status") != ABGELEHNT and z.get("D"):
            out["gravur"] += n * math.pi * float(z["D"])
        elif z["art"] == BOHREN and z.get("status") == BESTAETIGT:
            d = float(z.get("d") or 0)        # gemessene Bohrung fällt weg, der Laser markiert nur
            out["schneidweg"] -= n * math.pi * d
            out["weg"] += [(d, math.pi * d)] * n
            if z.get("laser") == LOCH:
                out["schneidweg"] += n * math.pi * MARKE_D
                out["konturen"] += [(MARKE_D, math.pi * MARKE_D)] * n
            else:
                out["einstiche"] -= n
                out["gravur"] += n * math.pi * MARKE_D
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


def arbeiten(liste):
    """Anzahl je Teil der Arbeitsschritte aus bestätigten Zeilen: {Zusatzarbeit: Anzahl} (Senken, Flowdrill, Bohren)."""
    out = {}
    for z in liste:
        name = ZUSATZ_ARBEIT.get(z.get("art"))
        if name and z.get("status") == BESTAETIGT and int(z.get("anzahl") or 0) > 0:
            out[name] = out.get(name, 0) + int(z["anzahl"])
    return out


def arbeiten_text(liste):
    return ", ".join(f"{n}× {name}" for name, n in arbeiten(liste).items())


def zusatz_eintragen(p, liste, katalog, saetze=None):
    """Spalte Zusatzarbeiten (JSON) der Position mit den Arbeitsschritten des Bohrbilds: vorhandener Eintrag gleichen
    Namens bekommt die Anzahl als Menge, neuer Eintrag mit Preisstand der Stammdaten (katalog = Zeilen der
    Zusatzarbeiten); Einträge aus dem Bohrbild ohne bestätigte Zeile fallen weg. Ergebnis: (JSON oder None, Namen,
    die in den Stammdaten fehlen)."""
    soll = arbeiten(liste)
    kat = {z.get("name"): z for z in katalog or ()}
    out, fehlt = [], []
    for e in rechnen.zusatz_liste(p):
        name = e["name"]
        if name in soll:
            out.append(dict(e, menge=soll.pop(name), quelle=e.get("quelle") or QUELLE))
        elif e.get("quelle") != QUELLE:
            out.append(e)
    for name, n in soll.items():
        if name not in kat:
            fehlt.append(name)
            continue
        out.append(dict(name=name, menge=n, preis=None, text=None, quelle=QUELLE,
                        stand=rechnen.zusatz_stand(kat[name], saetze)))
    return (json.dumps(out, ensure_ascii=False) if out else None), fehlt


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
        elif z["art"] == BOHREN:
            out.append(f"{z['anzahl']}x Bohren Ø{dez(z['d'])}")
    return "; ".join(out)


def _ohne(liste, weg, tol=0.06, gtol=0.006):
    """Konturliste ohne die Einträge in weg (je Eintrag ein Vorkommen, gerundet wie im Text; tol/gtol = Abweichung
    von Länge und Hüllmaß, gemessene Bohrungen weichen von π × d etwas ab)."""
    rest = list(liste)
    for g, lg in weg:
        for i, (a, g2, l2) in enumerate(rest):
            if not a and abs(round(g2, 2) - round(g, 2)) < gtol and abs(l2 - round(lg, 1)) < tol:
                del rest[i]
                break
    return rest


def hand_gewinde(p, liste):
    """Teile von 'Gewinde geprüft', die zu keiner Zeile des Bohrbilds gehören (von Hand eingetragen), als Text."""
    namen = {z.get("gewinde") for z in liste if z.get("gewinde")}
    return "; ".join(t.strip() for t in str(p.get("gewinde") or "").split(";")
                     if t.strip() and t.strip().upper().partition("X")[2].strip() not in {n.upper() for n in namen})


def anwenden(p, neu, hand=None, katalog=None, saetze=None):
    """Feldänderungen der Position für das neue Bohrbild: Schneidweg, Einstiche, Innenkonturen, Gravur, Konturliste
    und Konturklassen um den Unterschied alt → neu, dazu Gewinde geprüft (bestätigte Gewinde + hand, None = die von
    Hand eingetragenen bleiben), Gewinde-Vorschlag und bohrbild. Mit katalog (Zeilen der Zusatzarbeiten) auch die
    Zusatzarbeiten Senken, Flowdrill, Bohren (zusatz_eintragen); fehlende Namen unter '_fehlt' (nicht speichern)."""
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
    if alt_z["konturen"] != neu_z["konturen"] or alt_z["weg"] != neu_z["weg"]:
        liste = _ohne(rechnen.konturen_lesen(p.get("konturen"), True), alt_z["konturen"])
        liste += [("", g, lg) for g, lg in alt_z["weg"]]
        liste = _ohne(liste, neu_z["weg"], tol=1.0, gtol=0.06)
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
    if katalog is not None:
        zu, fehlt = zusatz_eintragen(p, neu, katalog, saetze)
        if zu != (p.get("zusatz") or None):
            out["zusatz"] = zu
        if fehlt:
            out["_fehlt"] = fehlt
    return out
