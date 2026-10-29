"""Mengen einer Schweißbaugruppe aus ihren Einzelteilen (Plan Schweißbaugruppen 28.10.2026, Schritt 1, Freigabe
„Ja alles“): Gewicht, Außenfläche, Länge der Teile, Nahtlänge und Anzahl Teile je Stück einer (Unter-)Baugruppe.

Bezug eines Arbeitsgangs (Feld 'bezug'): Gewicht [kg], Oberfläche [m²], Länge [m], Naht [m] oder Teile [Stück]; die
Menge des Arbeitsgangs folgt dann bei jeder Rechnung den Einzelteilen (Verzinken €/kg, Pulvern €/m², Prüfen je Teil).
Leer bzw. 'von Hand' = Menge wie eingetragen. Rechenweg je Teil wie bei den Zusatzarbeiten (rechnen.zusatz_menge_auto):
  Gewicht     Rohrlaserteil Metergewicht × Länge (virtuelles Bauteil aus dem Volumen), Zukaufteil 'Gewicht je Teil'
  Oberfläche  Rohrlaserteil Umfang × Länge (ohne Stirnflächen und Innenseite), Blech zweimal die Zuschnittfläche
  Länge       Rohrlaserteile
  Naht        Nahtgruppen: Länge × Anzahl × (2 bei beidseitig) / 1000
Menge eines Teils je Stück der (Unter-)Baugruppe = Stück je Knoten × Menge der Knoten dazwischen. Fehlt ein Wert
(Teil ohne Gewicht), zählt das Teil 0 und 'fehlt' nennt es; nichts wird erfunden.
Gewicht der Baugruppe für die Vorkalkulation (Wenden): Gewicht von Hand in den Stammdaten, sonst die Summe hier.
"""
import math

from . import baugruppe
from .angebot import ist_zukaufteil

GEWICHT, OBERFLAECHE, LAENGE, NAHT, TEILE, HAND = "Gewicht", "Oberfläche", "Länge", "Naht", "Teile", "von Hand"
AUTO = "automatisch"          # Herkunft der Menge im Editor
BEZUEGE = (HAND, GEWICHT, OBERFLAECHE, LAENGE, NAHT, TEILE)
EINHEIT = {GEWICHT: "kg", OBERFLAECHE: "m²", LAENGE: "m", NAHT: "m Naht", TEILE: "Teile"}
SCHLUESSEL = {GEWICHT: "gewicht", OBERFLAECHE: "oberflaeche", LAENGE: "laenge", NAHT: "naht", TEILE: "teile"}
# Bezug eines Arbeitsgangs aus einer Zusatzarbeit nach ihrer Abrechnung (Aus Zusatzarbeiten …)
BEZUG_ART = {"€/kg": GEWICHT, "€/m²": OBERFLAECHE, "€/m": LAENGE}

_zahl, _n = baugruppe._zahl, baugruppe._n


def bezug(ag):
    """Bezug eines Arbeitsgangs oder None (von Hand)."""
    b = (ag or {}).get("bezug")
    return b if b in SCHLUESSEL else None


def _blech_m2(p):
    """Beide Seiten eines Blechs [m²] aus dem Zuschnitt des Blech-Editors, sonst None."""
    from . import blech
    try:
        e = blech.lesen(p.get("technik"))
        z = blech.zuschnitt(e) if e else None
    except (TypeError, ValueError, KeyError, ZeroDivisionError):
        return None
    fl = (z or {}).get("flaeche")
    return 2 * fl / 1e6 if _zahl(fl) and fl > 0 else None


def teil_werte(p, k):
    """Gewicht [kg], Außenfläche [m²] und Länge [m] eines Einzelteils (None = unbekannt)."""
    from . import rechnen
    if ist_zukaufteil(p):
        g = p.get("gewicht_teil")
        m2 = _blech_m2(p) if p.get("technik") else 0.0      # Schrauben, Normteile: keine Fläche zum Beschichten
        return dict(gewicht=float(g) if _zahl(g) and g > 0 else None, oberflaeche=m2, laenge=0.0)
    if k is None:
        return dict(gewicht=None, oberflaeche=None,
                    laenge=p["laenge"] / 1000 if _zahl(p.get("laenge")) else None)
    try:
        g = rechnen.zusatz_menge_auto("€/kg", p, k)
        m2 = rechnen.oberflaeche(p, k)
    except (TypeError, ValueError, KeyError, ZeroDivisionError):
        g = m2 = None
    return dict(gewicht=g if _zahl(g) else None, oberflaeche=m2 if _zahl(m2) else None,
                laenge=p["laenge"] / 1000 if _zahl(p.get("laenge")) else None)


def _unter(bg, knoten_id):
    """Kennungen des Knotens und aller Knoten darunter ('' = ganze Baugruppe: None = alle)."""
    if not knoten_id:
        return None
    kinder = {}
    for x in bg["knoten"]:
        kinder.setdefault(x.get("parent") or "", []).append(x["id"])
    out, offen = set(), [knoten_id]
    while offen:
        x = offen.pop()
        if x not in out:
            out.add(x)
            offen += kinder.get(x, [])
    return out


def mengen(bg, positionen, k, knoten_id=""):
    """Mengen je Stück der (Unter-)Baugruppe knoten_id ('' = Baugruppe): dict(gewicht, oberflaeche, laenge, naht,
    teile, fehlt {Schlüssel: [Pos.]}). Werte gerundet auf 4 Stellen."""
    out = dict(gewicht=0.0, oberflaeche=0.0, laenge=0.0, naht=0.0, teile=0, fehlt={})
    f0 = baugruppe.faktor(bg, knoten_id)
    if not f0:
        return out
    bereich = _unter(bg, knoten_id)
    for i in baugruppe.teile(positionen, bg["id"]):
        p = positionen[i]
        kn = baugruppe.zuordnung(p)[1]
        if bereich is not None and kn not in bereich:
            continue
        f = baugruppe.faktor(bg, kn)
        if not f:
            continue
        je = p.get("je_knoten") if _zahl(p.get("je_knoten")) and p["je_knoten"] >= 1 else 1
        n = je * f / f0
        out["teile"] += n
        w = teil_werte(p, k)
        for s in ("gewicht", "oberflaeche", "laenge"):
            if w[s] is None:
                out["fehlt"].setdefault(s, []).append(str(p.get("pos") or i + 1))
            else:
                out[s] += w[s] * n
    for nt in bg["naehte"]:
        kn = nt.get("knoten") or ""
        if bereich is not None and kn not in bereich:
            continue
        f = baugruppe.faktor(bg, kn)
        if not f:
            continue
        anzahl = _n(nt.get("anzahl")) if _zahl(nt.get("anzahl")) else 1
        out["naht"] += _n(nt.get("laenge")) * anzahl * (2 if nt.get("beidseitig") else 1) / 1000 * f / f0
    for s in ("gewicht", "oberflaeche", "laenge", "naht", "teile"):
        out[s] = round(out[s], 4)
    return out


def je_knoten(bg, positionen, k):
    """{Knoten-ID: mengen()} für die Knoten, an denen ein Arbeitsgang mit Bezug hängt (für baugruppe.rechnen)."""
    if bg is None or baugruppe.struktur_fehler(bg):
        return {}
    out = {}
    for ag in bg["arbeitsgaenge"]:
        kn = ag.get("knoten") or ""
        if bezug(ag) and kn not in out:
            out[kn] = mengen(bg, positionen, k, kn)
    return out


def menge(ag, m):
    """(Menge, Rechenweg) eines Arbeitsgangs mit Bezug aus mengen() m, sonst (None, Grund)."""
    b = bezug(ag)
    if b is None or m is None:
        return None, None
    s = SCHLUESSEL[b]
    wert = m.get(s)
    fehlt = (m.get("fehlt") or {}).get(s)
    if fehlt and not wert:
        return None, f"{b} fehlt (Pos. {', '.join(fehlt[:5])})"
    text = f"{b} der Teile {baugruppe._text(round(wert, 3))} {EINHEIT[b]}"
    if fehlt:
        text += f", ohne Pos. {', '.join(fehlt[:5])} ({b.lower()} unbekannt)"
    return wert, text


def gewicht(bg, positionen=None, k=None):
    """(Gewicht der Baugruppe [kg], Herkunft) : Stammdaten der Baugruppe (von Hand) vor der Summe der Teile; (None,
    None) ohne beides."""
    t = str((bg.get("stamm") or {}).get("gewicht") or "").replace(",", ".").split()
    try:
        g = float(t[0]) if t else None
    except ValueError:
        g = None
    if g is not None and math.isfinite(g) and g > 0:
        return g, "Stammdaten der Baugruppe"
    if positionen is None:
        return None, None
    m = mengen(bg, positionen, k)
    if m["gewicht"] > 0:
        return m["gewicht"], "Summe der Einzelteile" + (" (ohne Pos. " + ", ".join(m["fehlt"]["gewicht"][:5]) + ")"
                                                         if m["fehlt"].get("gewicht") else "")
    return None, None


def anwenden(bg, positionen, k):
    """Menge der Arbeitsgänge mit Bezug in bg eintragen (Anzeige, Schweißplan; der Preis rechnet immer neu) und als
    'menge_auto' merken. Weicht die Menge davon ab, wurde sie von Hand geändert: der Bezug fällt weg (Wert von Hand
    geht vor). Ergebnis: Anzahl geänderter Arbeitsgänge."""
    werte, n = None, 0
    for ag in bg["arbeitsgaenge"]:
        if not bezug(ag):
            if ag.pop("menge_auto", None) is not None:
                n += 1
            continue
        if _zahl(ag.get("menge_auto")) and ag.get("menge") != ag["menge_auto"]:
            ag.pop("bezug", None)
            ag.pop("menge_auto", None)
            n += 1
            continue
        if werte is None:
            werte = je_knoten(bg, positionen, k)
        wert, _ = menge(ag, werte.get(ag.get("knoten") or ""))
        if wert is not None and ag.get("menge") != round(wert, 4):
            ag["menge"] = ag["menge_auto"] = round(wert, 4)
            n += 1
    return n


def text(m):
    """Kurztext der Mengen: '12,4 kg · 1,8 m² · 3,2 m Naht · 14 Teile'."""
    if not m:
        return ""
    t = baugruppe._text
    teile = [f"{t(round(m['gewicht'], 1))} kg" if m["gewicht"] else "Gewicht unbekannt",
             f"{t(round(m['oberflaeche'], 2))} m²" if m["oberflaeche"] else "Oberfläche unbekannt",
             f"{t(round(m['naht'], 2))} m Naht", f"{t(m['teile'])} Teile"]
    fehlt = sorted({x for v in m["fehlt"].values() for x in v}, key=lambda x: (len(x), x))
    return " · ".join(teile) + (f" (unvollständig: Pos. {', '.join(fehlt[:5])})" if fehlt else "")


__all__ = ["mengen", "je_knoten", "menge", "gewicht", "anwenden", "text", "BEZUEGE", "BEZUG_ART"]
