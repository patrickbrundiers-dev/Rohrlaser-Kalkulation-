"""Vollmaterial (Rund- und Vierkantstahl) als Zukaufartikel (Patrick 25.10.2026, Plan Vollmaterial „alle a, 4 b“).

Ein Artikel ist ein Zuschnitt: Form, Ø bzw. Kantenlänge, Länge und Werkstoff (wie Bleche, F2 a). Das Gewicht je Stück
kommt aus Querschnitt × Länge × Dichte des Werkstoffs, der Einkaufspreis je Stück aus Gewicht × Preis je kg (F1 a;
leer = Tonnenpreis des Werkstoffs). Beim Speichern trägt datenbank.zukauf_speichern den EK als Staffelzeile 'ab 1'
beim bevorzugten Lieferanten ein, damit die übrige Zukauf-Rechnung (Aufschlag, Bezugskosten, Staffeln) unverändert
gilt. Das Sägen ist keine Sache des Artikels, sondern die Zusatzarbeit 'Sägen' an der Position (F4 b).
"""
import json
import math
from decimal import Decimal

RUNDSTAHL, VIERKANTSTAHL = "Rundstahl", "Vierkantstahl"
FORMEN = (RUNDSTAHL, VIERKANTSTAHL)
KATEGORIE = "Vollmaterial"
ZUSATZ_SAEGEN, SAEGEN_PREIS = "Sägen", 1.00      # € je Schnitt (Beispielpreis), Menge 1 je Teil
FELDER = ("abmessung", "gewicht", "preis_kg")     # zusätzliche Felder der Zukaufartikel (Schema 61)
TOL_ABM = 0.05       # mm, Ø bzw. Kante gleicher Artikel
TOL_LAENGE = 0.5     # mm, Länge gleicher Artikel


def ist_voll(artikel_oder_typ):
    t = artikel_oder_typ.get("artikeltyp") if isinstance(artikel_oder_typ, dict) else artikel_oder_typ
    return t in FORMEN


def _zahl(x):
    if isinstance(x, Decimal):
        return float(x)
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def querschnitt(form, abm):
    """Querschnitt [mm²]: Rundstahl π/4 × Ø², Vierkantstahl Kante²; None ohne gültige Abmessung."""
    a = _zahl(abm)
    if not a or a <= 0:
        return None
    return math.pi / 4 * a * a if form == RUNDSTAHL else a * a if form == VIERKANTSTAHL else None


def gewicht(form, abm, laenge, dichte):
    """Gewicht je Stück [kg] = Querschnitt [mm²] × Länge [mm] × Dichte [kg/dm³] / 10⁶; None, wenn ein Wert fehlt."""
    q, l, d = querschnitt(form, abm), _zahl(laenge), _zahl(dichte)
    if not q or not l or l <= 0 or not d or d <= 0:
        return None
    return round(q * l * d / 1e6, 4)


def kg_preis(werkstoff):
    """Vorgabe Preis je kg aus dem Tonnenpreis des Werkstoffs (Stammdaten) oder None."""
    t = _zahl((werkstoff or {}).get("tonnenpreis"))
    return round(t / 1000, 4) if t and t > 0 else None


def ek(gew, preis_kg):
    """Einkaufspreis je Stück [€] = Gewicht × Preis je kg (auf 4 Stellen) oder None."""
    g, p = _zahl(gew), _zahl(preis_kg)
    return round(g * p, 4) if g and p and g > 0 and p > 0 else None


def _mm(x):
    x = _zahl(x)
    if x is None:
        return "?"
    t = f"{x:.1f}".rstrip("0").rstrip(".")
    return t.replace(".", ",")


def masse_text(form, abm, laenge=None):
    """'Ø20 × 150 mm' bzw. '20 × 20 × 150 mm' (ohne Länge: 'Ø20 mm' bzw. '20 × 20 mm')."""
    quer = f"Ø{_mm(abm)}" if form == RUNDSTAHL else f"{_mm(abm)} × {_mm(abm)}"
    return f"{quer} × {_mm(laenge)} mm" if laenge is not None else f"{quer} mm"


def bezeichnung(form, abm, laenge, werkstoff=None):
    """Bezeichnung eines Vollmaterial-Artikels, z. B. 'Rundstahl Ø20 × 150 mm S235JR'."""
    return " ".join(x for x in (form, masse_text(form, abm, laenge), werkstoff) if x)


def vorbereiten(werte, bezuege, werkstoffe):
    """Vor dem Speichern eines Vollmaterial-Artikels (datenbank.zukauf_speichern): Bezeichnung (leer = automatisch),
    Gewicht aus Werkstoff-Dichte (werkstoffe = {ID: Stammdatenzeile}), Preis je kg (leer = Tonnenpreis) und EK je
    Stück als Staffelzeile 'ab 1' beim bevorzugten (sonst ersten bzw. neuen) Lieferanten. Ohne Gewicht oder Preis
    je kg bleiben die Einkaufspreise, wie sie sind. Ergebnis: (werte, bezuege), beide neu."""
    werte, bezuege = dict(werte), [dict(b) for b in bezuege or ()]
    form = werte.get("artikeltyp")
    w = (werkstoffe or {}).get(werte.get("werkstoff")) or {}
    # immer neu: ohne Werkstoff (bzw. Dichte) kein Gewicht, auch kein altes eines anderen Werkstoffs
    werte["gewicht"] = gewicht(form, werte.get("abmessung"), werte.get("laenge"), w.get("dichte"))
    if _zahl(werte.get("preis_kg")) is None:
        werte["preis_kg"] = kg_preis(w)
    if not werte.get("bezeichnung"):
        werte["bezeichnung"] = bezeichnung(form, werte.get("abmessung"), werte.get("laenge"), werte.get("werkstoff"))
    werte["breite"] = werte["dicke"] = None
    werte["einheit"] = werte.get("einheit") or "Stück"
    preis = ek(werte.get("gewicht"), werte.get("preis_kg"))
    if preis is not None:
        if not bezuege:
            bezuege = [dict(lieferant=None, bevorzugt="ja", preiseinheit=1)]
        b = next((x for x in bezuege if x.get("bevorzugt") == "ja"), bezuege[0])
        b["preise"] = [dict(ab=1, preis=preis)]
        b["preiseinheit"] = 1
    return werte, bezuege


def artikel(form, abm, laenge, werkstoff=None, step_datei=None, herkunft="STEP-Import", lieferant=None,
            preis_kg=None):
    """Neuer Zukaufartikel (Werte, Einkaufsbedingungen) für Vollmaterial, Kategorie Vollmaterial, Einheit Stück; das
    Gewicht und den EK setzt vorbereiten() beim Speichern."""
    werte = dict(bezeichnung=bezeichnung(form, abm, laenge, werkstoff), kategorie=KATEGORIE, einheit="Stück",
                 status="aktiv", aufschlag_quelle="Kategorie", angebotstext="nein", rest_lager="nein",
                 kombiniert="nein", artikeltyp=form, abmessung=_zahl(abm), laenge=_zahl(laenge),
                 werkstoff=werkstoff or None, preis_kg=preis_kg, herkunft=herkunft, step_datei=step_datei or None)
    return werte, [dict(lieferant=lieferant or None, bevorzugt="ja", preiseinheit=1, preise=[])]


def _nahe(a, b, tol):
    a, b = _zahl(a), _zahl(b)
    return a is not None and b is not None and abs(a - b) <= tol


def dubletten(form, abm, laenge, werkstoff, artikel_liste):
    """Vorhandene Vollmaterial-Artikel: (gleich, ähnlich). gleich = gleiche Form, Ø bzw. Kante (± 0,05 mm), Länge
    (± 0,5 mm) und Werkstoff; ähnlich = gleiche Form und Abmessung, aber andere Länge oder anderer Werkstoff.
    Archivierte Artikel zählen nicht."""
    gleich, aehnlich = [], []
    for a in artikel_liste or ():
        if a.get("artikeltyp") != form or a.get("status") == "archiviert" or not _nahe(a.get("abmessung"), abm, TOL_ABM):
            continue
        if _nahe(a.get("laenge"), laenge, TOL_LAENGE) and (a.get("werkstoff") or "") == (werkstoff or ""):
            gleich.append(a)
        else:
            aehnlich.append(a)
    return gleich, aehnlich


def saegen_zusatz(katalog, menge=1, quelle=None):
    """JSON der Zusatzarbeit 'Sägen' (Menge je Teil, Preisstand aus den Stammdaten) oder None, wenn es sie in den
    Stammdaten (katalog = Zeilen der Zusatzarbeiten) nicht gibt."""
    from . import rechnen
    kat = {z.get("name"): z for z in katalog or ()}
    if ZUSATZ_SAEGEN not in kat:
        return None
    e = dict(name=ZUSATZ_SAEGEN, menge=menge, preis=None, text=None, stand=rechnen.zusatz_stand(kat[ZUSATZ_SAEGEN]))
    if quelle:
        e["quelle"] = quelle
    return json.dumps([e], ensure_ascii=False)


def text(a):
    """Kurztext eines Artikels für Listen: 'Rundstahl Ø20 × 150 mm S235JR, 0,37 kg, 1,20 €/kg'."""
    z = [bezeichnung(a.get("artikeltyp"), a.get("abmessung"), a.get("laenge"), a.get("werkstoff"))]
    if _zahl(a.get("gewicht")):
        z.append(f"{_zahl(a['gewicht']):.3f} kg".replace(".", ","))
    if _zahl(a.get("preis_kg")):
        z.append(f"{_zahl(a['preis_kg']):.2f} €/kg".replace(".", ","))
    return ", ".join(z)
