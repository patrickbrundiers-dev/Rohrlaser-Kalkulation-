"""Schweißnaht eines Rohrs: Winkel, Profilseite, Drehfreigabe und Prüfung (Patrick 21.10.2026).

Winkel (überall gleich): Querschnitt von Ende A in Richtung Ende B gesehen, im Uhrzeigersinn
0° oben, 90° rechts, 180° unten, 270° links. Das ist dieselbe Zählung wie der Umfangswinkel der STEP-Messung
(step_geometrie._Abwicklung: rechtsdrehend um die Achse A→B, 0° = Mitte der Breitseite oben).

Bezug bei Rechteck- und Quadratrohr: die Breitseite (längere Seite, max(A, B)) liegt waagerecht oben. Welche Seite
breit ist, folgt aus der Seitenlänge, nicht aus der Reihenfolge von A und B im Profil. Liegt das Rohr in der
Zeichnung hochkant ('Schmalseite oben'), wird der Winkel in dieser Ansicht eingegeben und intern umgerechnet:
die Ansicht ist der Bezug um 90° gegen den Uhrzeigersinn gedreht, oben in der Ansicht = 90° im Bezug.

Gespeichert wird je Position: naht_vorgabe (leer = keine Vorgabe), naht_winkel (im Bezug), naht_quelle und
querschnitt_lage (nur Anzeige und Eingabe). Die Drehfreigabe wird abgeleitet: keine Vorgabe = frei drehbar, feste
Position und unbekannt = gesperrt. Gedreht wird nur um die eigene Achse, nie gewendet (Ende A bleibt vorn).
Die Nahtlage der Lieferstange (nur Rechteckrohr: Breit- oder Schmalseite) ist angebotsbezogen (Patrick 22.10.2026):
sie steht je Stangengruppe Profil + Werkstoff im Angebot (angebote.naht_stangen, JSON), leer = aus den Teilen mit
fester Naht abgeleitet, und geht in die Materialanfrage ein. Das frühere Profilfeld naht_stange wird nicht mehr gelesen.
"""
import json
import math

KEINE, FEST, UNBEKANNT = "keine Vorgabe", "feste Position", "unbekannt"
VORGABEN = (KEINE, FEST, UNBEKANNT)
QUELLEN = ("Kunde", "Zeichnung", "manuell", "Import")
BREIT_OBEN, SCHMAL_OBEN = "Breitseite oben", "Schmalseite oben"
LAGEN = (BREIT_OBEN, SCHMAL_OBEN)
BREITSEITE, SCHMALSEITE = "Breitseite", "Schmalseite"
NAHT_STANGE = (BREITSEITE, SCHMALSEITE)
RICHTUNGEN = ("oben", "rechts", "unten", "links")
ECKE_TOL = 2.0          # Grad: so nah an einer Ecke ist die Seite nicht eindeutig
# zulässige Drehungen um die eigene Achse je Profilform (Patrick 21.10.2026, Rundrohr wie Quadratrohr)
DREHUNGEN = {"Rundrohr": (0, 90, 180, 270), "Quadratrohr": (0, 90, 180, 270), "Rechteckrohr": (0, 180)}


def normieren(winkel):
    """Winkel auf 0 ≤ w < 360 bringen (360 -> 0, -90 -> 270, 450 -> 90). ValueError bei Text oder leer."""
    if winkel is None or isinstance(winkel, bool):
        raise ValueError("Nahtwinkel fehlt.")
    try:
        w = float(str(winkel).replace(",", ".")) if isinstance(winkel, str) else float(winkel)
    except ValueError:
        raise ValueError(f"Nahtwinkel: '{winkel}' ist keine Zahl.")
    if not math.isfinite(w):
        raise ValueError(f"Nahtwinkel: '{winkel}' ist keine Zahl.")
    w = round(w % 360.0, 1)
    return 0.0 if w >= 360.0 else w


def aus_ansicht(winkel, lage=BREIT_OBEN):
    """Winkel aus der Ansicht der Zeichnung (Lage) in den Bezug 'Breitseite oben'."""
    w = normieren(winkel)
    return normieren(w + 90) if lage == SCHMAL_OBEN else w


def in_ansicht(winkel, lage=BREIT_OBEN):
    """Winkel im Bezug in die Ansicht der gewählten Lage."""
    w = normieren(winkel)
    return normieren(w - 90) if lage == SCHMAL_OBEN else w


def form_von(profil):
    """Profilform für die Naht: Rechteckrohr mit gleichen Seiten zählt als Quadratrohr; None = keine Zuordnung."""
    if not profil:
        return None
    form = profil.get("form")
    if form == "Rechteckrohr":
        a, b = profil.get("a"), profil.get("b")
        if not a or not b:
            return None
        return "Quadratrohr" if abs(a - b) < 1e-9 else form
    if form in ("Quadratrohr", "Rundrohr"):
        return form if profil.get("a") else None
    return None


def seitenmasse(profil):
    """(Breite waagerecht, Höhe senkrecht) im Bezug: Breite = längere Seite."""
    a, b = profil.get("a"), profil.get("b") or profil.get("a")
    return max(a, b), min(a, b)


def seite(profil, winkel, lage=BREIT_OBEN):
    """Zuordnung der Naht zum Querschnitt. winkel im Bezug (wie gespeichert). Ergebnis dict:
    winkel (Bezug), ansicht (Winkel in der Lage), richtung (oben/rechts/unten/links in der Ansicht, '' bei Ecke oder
    Rundrohr zwischen den Hauptrichtungen), flaeche ('Breitseite'/'Schmalseite' bei Rechteckrohr, 'Seite' bei
    Quadratrohr, '' bei Rundrohr), eindeutig (bool), text."""
    form = form_von(profil)
    erg = dict(winkel=None, ansicht=None, richtung="", flaeche="", eindeutig=False, lage=lage, form=form)
    try:
        w = normieren(winkel)
    except ValueError:
        erg["text"] = "Nahtwinkel fehlt"
        return erg
    erg["winkel"], erg["ansicht"] = w, in_ansicht(w, lage)
    if form is None:
        erg["text"] = "Profil unbekannt oder kein Rohr: Seite nicht bestimmbar"
        return erg
    if form == "Rundrohr":
        v = erg["ansicht"]
        erg["richtung"] = RICHTUNGEN[int(v // 90)] if v % 90 == 0 else ""
        erg["eindeutig"] = True
        erg["text"] = f"{_z(v)}°" + (f" ({erg['richtung']})" if erg["richtung"] else "")
        return erg
    breite, hoehe = seitenmasse(profil)
    ecke = math.degrees(math.atan2(breite / 2, hoehe / 2))      # Ecke oben rechts, ab 0° im Uhrzeigersinn
    grenzen = (ecke, 180 - ecke, 180 + ecke, 360 - ecke)
    if any(abs(w - g) <= ECKE_TOL for g in grenzen):
        erg["text"] = f"{_z(erg['ansicht'])}° Ecke – nicht eindeutig"
        return erg
    nr = 0 if (w < grenzen[0] or w > grenzen[3]) else 1 if w < grenzen[1] else 2 if w < grenzen[2] else 3
    erg["mitte"] = nr * 90.0
    if form == "Rechteckrohr":
        erg["flaeche"] = BREITSEITE if nr in (0, 2) else SCHMALSEITE
    else:
        erg["flaeche"] = "Seite"
    nr_ansicht = (nr - 1) % 4 if lage == SCHMAL_OBEN else nr        # Ansicht: Bezug 90° gegen den Uhrzeiger gedreht
    erg["richtung"] = RICHTUNGEN[nr_ansicht]
    erg["eindeutig"] = True
    erg["text"] = f"{_z(erg['ansicht'])}° {erg['richtung']}" + (
        f", {erg['flaeche']}" if form == "Rechteckrohr" else "")
    return erg


def wirksamer_winkel(profil, winkel):
    """Nahtwinkel, mit dem die Optimierung rechnet: Rundrohr der Winkel selbst, Quadrat- und Rechteckrohr die Mitte
    der Seite, auf der die Naht liegt (wie Spalte und Prüfung, naht.seite). None, wenn der Winkel fehlt oder die Naht
    auf einer Ecke liegt (Seite nicht eindeutig: das Teil wird dann nicht gedreht). Andere Profile: der Winkel."""
    try:
        w = normieren(winkel)
    except ValueError:
        return None
    if form_von(profil) not in ("Quadratrohr", "Rechteckrohr"):
        return w
    s = seite(profil, w)
    return s.get("mitte") if s["eindeutig"] else None


def vorgabe(p):
    """Nahtvorgabe der Position; leer = keine Vorgabe (Patrick 21.10.2026, F6 b)."""
    v = (p or {}).get("naht_vorgabe")
    return v if v in VORGABEN else KEINE


def drehungen(p, profil):
    """Zulässige Drehungen um die eigene Achse [Grad] für die Optimierung. Keine Vorgabe: alle, die der Querschnitt
    erlaubt; feste Position und unbekannt: nur 0° (die Naht bleibt, wo sie ist). Andere Profile: nur 0°."""
    if vorgabe(p) != KEINE:
        return (0,)
    return DREHUNGEN.get(form_von(profil), (0,))


def drehung_frei(p):
    return vorgabe(p) == KEINE


def text(p, profil):
    """Kurztext für die Spalte Schweißnaht."""
    v = (p or {}).get("naht_vorgabe")
    if v not in VORGABEN:
        return ""
    if v != FEST:
        return v + (" – Drehung gesperrt" if v == UNBEKANNT else "")
    s = seite(profil, p.get("naht_winkel"), p.get("querschnitt_lage") or BREIT_OBEN)
    return f"fest {s['text']}"


def pruefen(p, profil, stange=None):
    """Prüfung der Nahtangaben einer Position: 'FEHLER: …', 'WARNUNG: …' oder None. stange = Nahtlage der
    Lieferstange aus dem Angebot (Breitseite/Schmalseite), leer = nicht vorgegeben (keine Prüfung, kein Hinweis)."""
    v = (p or {}).get("naht_vorgabe")
    if v != FEST:
        return None
    form = form_von(profil)
    if form is None:
        return "WARNUNG: Schweißnaht nur bei Rund-, Quadrat- und Rechteckrohr auswertbar"
    try:
        normieren(p.get("naht_winkel"))
    except ValueError:
        return "FEHLER: Nahtwinkel fehlt (Schweißnaht …)"
    s = seite(profil, p.get("naht_winkel"), p.get("querschnitt_lage") or BREIT_OBEN)
    if not s["eindeutig"]:
        return "WARNUNG: Schweißnaht auf der Ecke – Seite nicht eindeutig"
    if form == "Rechteckrohr" and stange in NAHT_STANGE:
        if stange != s["flaeche"]:
            return f"FEHLER: Naht auf {s['flaeche']} gefordert, Lieferstange hat sie auf der {stange}"
    return None


def gruppe_schluessel(profil_id, werkstoff_id):
    """Schlüssel der Stangengruppe in angebote.naht_stangen."""
    return f"{profil_id or ''}|{werkstoff_id or ''}"


def stange_gefordert(positionen, profil_id, werkstoff_id, profile):
    """Seiten (Breitseite/Schmalseite), die die Positionen mit fester Naht dieser Gruppe auf Rechteckrohr verlangen:
    set, leer = keine Position mit fester Naht (oder kein Rechteckrohr)."""
    profil = (profile or {}).get(profil_id)
    if form_von(profil) != "Rechteckrohr":
        return set()
    seiten = set()
    for p in positionen or ():
        if p.get("profil_id") != profil_id or p.get("werkstoff_id") != werkstoff_id or vorgabe(p) != FEST:
            continue
        s = seite(profil, p.get("naht_winkel"), p.get("querschnitt_lage") or BREIT_OBEN)
        if s["flaeche"] in NAHT_STANGE:
            seiten.add(s["flaeche"])
    return seiten


def stange_eingetragen(kopf, profil_id, werkstoff_id):
    """Im Angebot eingetragene Nahtlage der Lieferstange dieser Gruppe oder None."""
    w = ((kopf or {}).get("naht_stangen") or {}).get(gruppe_schluessel(profil_id, werkstoff_id))
    return w if w in NAHT_STANGE else None


def stange_lage(kopf, positionen, profil_id, werkstoff_id, profile):
    """Nahtlage der Lieferstange für Prüfung und Materialanfrage: (Seite, Quelle). Quelle 'Angebot' (eingetragen)
    oder 'Teile' (eindeutig aus den Positionen mit fester Naht); (None, None), wenn die Gruppe keine Position mit
    fester Naht auf Rechteckrohr hat oder die Teile beide Seiten verlangen und nichts eingetragen ist."""
    gefordert = stange_gefordert(positionen, profil_id, werkstoff_id, profile)
    if not gefordert:
        return None, None
    eingetragen = stange_eingetragen(kopf, profil_id, werkstoff_id)
    if eingetragen:
        return eingetragen, "Angebot"
    return (next(iter(gefordert)), "Teile") if len(gefordert) == 1 else (None, None)


def _z(w):
    return f"{w:.1f}".rstrip("0").rstrip(".").replace(".", ",")


# ------------------------------------------------------------------ ebene schräge Enden (Gehrung)
def ende_text(winkel, richtung):
    """Gehrung eines Endes für positionen.a_ende/b_ende: Winkel gegen den geraden Schnitt und Richtung, in der das
    Teil an diesem Ende am längsten ist (Umfangswinkel wie die Naht, Bezug 'Breitseite oben')."""
    return json.dumps(dict(winkel=round(float(winkel), 2), richtung=normieren(richtung)))


def ende_lesen(text):
    """(Winkel, Richtung) aus positionen.a_ende/b_ende oder None (leer, gerade, ungültig)."""
    try:
        d = json.loads(text) if text else None
        w, r = float(d["winkel"]), normieren(d["richtung"])
    except (TypeError, ValueError, KeyError):
        return None
    return (w, r) if 0 < w < 80 else None
