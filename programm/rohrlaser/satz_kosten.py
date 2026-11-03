"""Zukaufkosten je Satz (Patrick 03.11.2026: „Pro Satz die Option, die kompletten Blechkosten pro Satz einzutragen, die
dann auf die einzelnen Teile umgelegt werden“; Freigabe „Alle Empfehlungen, zu 1 alle Zukaufteile, dann separate
Kosten“).

Im Fenster „Satz bearbeiten“ je Art ein Betrag: Bleche, Vollmaterial, Dreh-/Frästeile. Der Betrag ist der
Einkaufspreis je Satz (Frage 4 a); er wird nach Gewicht (Frage 3 a; ohne Gewicht nach Stück) auf die Zukaufteile dieser
Art im Satz umgelegt und steht nur an den Positionen dieses Angebots (Frage 6 a): je Zukauf-Eintrag 'ek_fest' (EK je
Einheit, ersetzt den EK des Artikels in zukauf.rechnen) und 'satzkosten' (Art, Betrag) zum Wiederanzeigen. Danach
rechnet das Teil wie jedes Zukaufteil (nur der Aufschlag, kein Gewinn). Leer bzw. 0 nimmt den Betrag wieder weg.
"""
import json

from . import satz_menge, zukauf

ARTEN = {"Bleche": ("Blechteile",), "Vollmaterial": ("Vollmaterial",), "Dreh-/Frästeile": ("Drehteile", "Frästeile")}


def art(e):
    """Art eines Zukauf-Eintrags nach der Kategorie im Preisstand (Bleche, Vollmaterial, Dreh-/Frästeile) oder None."""
    kat = (e.get("stand") or {}).get("kategorie")
    return next((a for a, k in ARTEN.items() if kat in k), None)


def _eintraege(positionen, satz):
    """[(Position, Liste der Einträge, Index, Eintrag, Art)] der Zukaufteile im Satz."""
    out = []
    for i in satz_menge.satz_positionen(positionen, satz):
        p = positionen[i]
        liste = zukauf.json_liste(p.get("zukauf"))
        for n, e in enumerate(liste):
            a = art(e)
            if a:
                out.append((p, liste, n, e, a))
    return out


def arten(positionen, satz):
    """Arten, die im Satz vorkommen (Reihenfolge wie ARTEN)."""
    da = {a for *_, a in _eintraege(positionen, satz)}
    return [a for a in ARTEN if a in da]


def betraege(positionen, satz):
    """Eingetragene Beträge je Art {Art: € je Satz} (fehlt = keiner)."""
    out = {}
    for *_, e, a in _eintraege(positionen, satz):
        b = (e.get("satzkosten") or {}).get("betrag")
        if isinstance(b, (int, float)) and b > 0 and a not in out:
            out[a] = float(b)
    return out


def _zahl(x, vorgabe=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return vorgabe


def verteilen(positionen, satz, kosten, je=None):
    """Beträge kosten {Art: € je Satz oder None/0 = entfernen} auf die Einträge umlegen. je {Positions-ID: Stück je
    Satz} wie im Fenster (sonst aus der Position). Ergebnis: [(Positions-ID, 'zukauf', JSON)] für geänderte Positionen
    (ein Schritt für Rückgängig mit den übrigen Änderungen des Fensters)."""
    je = je or {}
    eintr = _eintraege(positionen, satz)
    geaendert = {}
    for a, betrag in (kosten or {}).items():
        teile = [x for x in eintr if x[4] == a]
        if not teile:
            continue
        betrag = _zahl(betrag)
        einheiten, gewichte = [], []
        for p, _liste, _n, e, _ in teile:
            n_pos = je.get(p.get("id"), satz_menge.je_satz(p))
            m = _zahl(e.get("menge"), 1.0) or 1.0
            u = m if e.get("je") == zukauf.JE_SATZ else n_pos * m       # Einheiten je Satz
            einheiten.append(u)
            gewichte.append(u * _zahl(p.get("gewicht_teil")))
        nach_gewicht = all(g > 0 for g in gewichte)
        basis = gewichte if nach_gewicht else einheiten
        summe = sum(basis)
        for (p, liste, n, e, _), u, b in zip(teile, einheiten, basis):
            alt = (e.get("ek_fest"), e.get("satzkosten"))
            if betrag > 0 and summe > 0 and u > 0:
                e["ek_fest"] = round(betrag * b / summe / u, 4)
                e["satzkosten"] = dict(art=a, betrag=round(betrag, 2), nach="Gewicht" if nach_gewicht else "Stück")
            else:
                e.pop("ek_fest", None)
                e.pop("satzkosten", None)
            if (e.get("ek_fest"), e.get("satzkosten")) != alt:
                liste[n] = e
                geaendert[p.get("id")] = liste
    return [(pid, "zukauf", json.dumps(liste, ensure_ascii=False)) for pid, liste in geaendert.items()]
