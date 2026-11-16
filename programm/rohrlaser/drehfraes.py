"""Dreh- und Frästeile aus dem STEP-Import als Zukaufartikel (Patrick 03.11.2026, Plan „Dreh- und Frästeile als
Zukauf“, Freigabe alle a).

Die STEP-Messung (step_messung/step_drehfraes.py) erkennt Drehteile (drehsymmetrisch mit Absatz, Einstich, Fase …)
und Frästeile (gedrungene Körper aus dem Vollen mit Tasche, Absatz …) und schreibt ihre Merkmale in die Spalte
'drehfraes'. Im Programm werden sie Zukaufteile wie Bleche und Vollmaterial (kein Gewinn, nur der Aufschlag der
Zukaufregel; Fracht ja, Rüsten/Pauschalen/Programmierung nein):
- Artikeltyp „Drehteil“ bzw. „Frästeil“ mit eigener Kategorie (Frage 5 a), Maße und Fingerabdruck der Geometrie;
- der EK kommt von Hand bzw. aus der Lieferantenanfrage (Frage 4 a: Filter „EK fehlt“, „EK eintragen …“), das
  Rohgewicht (Drehteil Ø max × Länge, Frästeil Hüllquader) steht nur zur Information im Artikel;
- ein gleiches Teil (gleicher Fingerabdruck, Werkstoff) aus einer früheren Anfrage nimmt den vorhandenen Artikel mit
  seinem EK (Frage 6 a).
Ein nur nach den Maßen verdächtiges Teil (kurzes dickwandiges Rohr, offenes Profil ohne Normmaß mit dicker Wand;
'nur_abmessung') wird wieder Rohr/Profil, wenn das Profil in den Stammdaten steht (Frage 3 a, step.drehfraes_vorbelegen).
"""
import json
import math

DREHTEIL, FRAESTEIL = "Drehteil", "Frästeil"
ARTEN = (DREHTEIL, FRAESTEIL)
KATEGORIE = {DREHTEIL: "Drehteile", FRAESTEIL: "Frästeile"}


def daten(m):
    """Merkmale aus der Messung (Spalte 'drehfraes', JSON) oder None."""
    roh = m.get("drehfraes") if isinstance(m, dict) else None
    if not roh:
        return None
    if isinstance(roh, dict):
        return roh
    try:
        d = json.loads(roh)
    except ValueError:
        return None
    return d if isinstance(d, dict) and d.get("art") in ARTEN else None


def ist(m):
    """Gemessenes Dreh- oder Frästeil (wird Zukaufteil)."""
    return not m.get("fehler") and m.get("profilform") in ARTEN and daten(m) is not None


def _mm(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "?"
    return f"{x:.1f}".rstrip("0").rstrip(".").replace(".", ",")


def masse_text(d):
    """'Ø30 × 120 mm' (Drehteil, hohl 'Ø40/Ø25 × 50 mm') bzw. '100 × 60 × 20 mm' (Frästeil)."""
    if d.get("art") == DREHTEIL:
        innen = f"/Ø{_mm(d['innen'])}" if d.get("innen") else ""
        return f"Ø{_mm(d.get('durchmesser'))}{innen} × {_mm(d.get('laenge'))} mm"
    return f"{_mm(d.get('laenge'))} × {_mm(d.get('breite'))} × {_mm(d.get('hoehe'))} mm"


def text(m):
    """Kurztext für Prüfdialog und Bericht, z. B. 'Drehteil Ø30 × 120 mm (3 Außendurchmesser …)'."""
    d = daten(m) or {}
    merk = ", ".join((d.get("merkmale") or []) + (d.get("zusatz") or []))
    return f"{d.get('art') or m.get('profilform')} {masse_text(d)}" + (f" ({merk})" if merk else "")


def bezeichnung(d, werkstoff=None):
    """Bezeichnung des Zukaufartikels, z. B. 'Drehteil Ø30 × 120 mm S235-10219'."""
    return " ".join(x for x in (d.get("art"), masse_text(d), werkstoff) if x)


def rohgewicht(d, dichte):
    """Rohgewicht [kg] (nur Information, Frage 4 a): Drehteil Rundstahl Ø max × Länge, Frästeil Hüllquader; None ohne
    Dichte."""
    try:
        dichte = float(dichte)
    except (TypeError, ValueError):
        return None
    if dichte <= 0:
        return None
    if d.get("art") == DREHTEIL:
        v = math.pi / 4 * float(d.get("durchmesser") or 0) ** 2 * float(d.get("laenge") or 0)
    else:
        v = float(d.get("laenge") or 0) * float(d.get("breite") or 0) * float(d.get("hoehe") or 0)
    return round(v * dichte / 1e6, 4) if v > 0 else None


def fertiggewicht(d, dichte):
    """Gewicht des fertigen Teils [kg] aus dem Volumen der Messung (für Fracht) oder None."""
    try:
        v, dichte = float(d.get("volumen") or 0), float(dichte)
    except (TypeError, ValueError):
        return None
    return round(v * dichte / 1e6, 4) if v > 0 and dichte > 0 else None


def artikel(d, werkstoff=None, step_datei=None, dichte=None):
    """Neuer Zukaufartikel (Werte, Einkaufsbedingungen) ohne EK (Lieferantenanfrage, Frage 4 a)."""
    art = d.get("art")
    if art == DREHTEIL:
        laenge, breite, dicke = d.get("laenge"), d.get("durchmesser"), d.get("innen") or None
    else:
        laenge, breite, dicke = d.get("laenge"), d.get("breite"), d.get("hoehe")
    roh = rohgewicht(d, dichte)
    merk = ", ".join((d.get("merkmale") or []) + (d.get("zusatz") or []))
    beschreibung = "; ".join(x for x in (merk, f"Rohgewicht ca. {_mm(roh)} kg" if roh else "") if x) or None
    werte = dict(bezeichnung=bezeichnung(d, werkstoff), kategorie=KATEGORIE[art], einheit="Stück", status="aktiv",
                 aufschlag_quelle="Kategorie", angebotstext="nein", rest_lager="nein", kombiniert="nein",
                 artikeltyp=art, laenge=laenge, breite=breite, dicke=dicke,
                 abmessung=d.get("durchmesser") if art == DREHTEIL else None, gewicht=roh,
                 werkstoff=werkstoff or None, herkunft="STEP-Import", step_datei=step_datei or None,
                 fingerabdruck=d.get("fingerabdruck"), beschreibung=beschreibung)
    return werte, [dict(lieferant=None, bevorzugt="ja", preiseinheit=1, preise=[])]


def dubletten(d, werkstoff, liste):
    """(gleich, ähnlich): gleiche Artikel = gleicher Typ, Fingerabdruck und Werkstoff (Frage 6 a); ähnlich = gleicher
    Typ und Fingerabdruck, anderer bzw. offener Werkstoff. Archivierte zählen nicht."""
    gleich, aehnlich = [], []
    for a in liste or ():
        if a.get("artikeltyp") != d.get("art") or a.get("status") == "archiviert":
            continue
        if not d.get("fingerabdruck") or a.get("fingerabdruck") != d.get("fingerabdruck"):
            continue
        (gleich if (a.get("werkstoff") or None) == (werkstoff or None) else aehnlich).append(a)
    return gleich, aehnlich
