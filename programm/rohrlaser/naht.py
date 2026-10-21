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
Die Nahtlage der Lieferstange (profile.naht_stange) gilt nur für Rechteckrohr.
"""
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


def pruefen(p, profil):
    """Prüfung der Nahtangaben einer Position: 'FEHLER: …', 'WARNUNG: …' oder None."""
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
    if form == "Rechteckrohr":
        stange = profil.get("naht_stange")
        if stange not in NAHT_STANGE:
            return "WARNUNG: Nahtlage der Lieferstange im Profil eintragen"
        if stange != s["flaeche"]:
            return f"FEHLER: Naht auf {s['flaeche']} gefordert, Lieferstange hat sie auf der {stange}"
    return None


def _z(w):
    return f"{w:.1f}".rstrip("0").rstrip(".").replace(".", ",")
