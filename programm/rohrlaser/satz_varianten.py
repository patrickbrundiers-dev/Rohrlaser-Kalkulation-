"""Varianten eines Satzes nebeneinander (ASM-005, Plan Phase 3 und 4, Paket C, 13.11.2026).

Preis je Satz wie angeboten, ohne Oberfläche (Zusatzarbeiten der Kategorie Oberfläche an den Teilen des Satzes), ohne
Zukauf (Zukaufteile an den Teilen und Zukaufteil-Positionen des Satzes) und ohne beides – jeweils mit der vollen
Angebotskalkulation auf einer Kopie gerechnet. Nur Anzeige: nichts wird geändert, keine Staffel angelegt (Staffeln
nie automatisch). Ohne Qt.
"""
import copy
import json

from .angebot import ist_zukaufteil

VARIANTEN = (("wie angeboten", False, False), ("ohne Oberfläche", True, False), ("ohne Zukauf", False, True),
             ("ohne Oberfläche und Zukauf", True, True))
OBERFLAECHE = "Oberfläche"


def _ist_oberflaeche(z, katalog):
    kat = (katalog.get(z.get("name")) or {}).get("kategorie") or (z.get("stand") or {}).get("kategorie")
    return kat == OBERFLAECHE


def abwandeln(positionen, indizes, katalog, ohne_oberflaeche, ohne_zukauf, loesen):
    """Kopie der Positionen: die mit Index in indizes ohne Oberflächen-Zusatzarbeiten bzw. ohne Zukauf.
    Zukaufteil-Positionen verlassen dafür Satz bzw. Baugruppe (Felder loesen, z. B. {"satz": None}); die Reihenfolge
    bleibt, damit die Kalkulationszeilen passen."""
    out = copy.deepcopy(positionen)
    for i in indizes:
        p = out[i]
        if ohne_oberflaeche and p.get("zusatz"):
            try:
                liste = json.loads(p["zusatz"]) if isinstance(p["zusatz"], str) else p["zusatz"]
            except ValueError:
                liste = None
            if isinstance(liste, list):
                p["zusatz"] = json.dumps([z for z in liste if not (isinstance(z, dict) and _ist_oberflaeche(z, katalog))],
                                         ensure_ascii=False)
        if ohne_zukauf:
            if ist_zukaufteil(p):
                p.update(loesen)
            else:
                p["zukauf"] = "[]"
    return out


def rechnen(kopf, positionen, ergebnis, k, tabellen, einst, indizes, loesen, preis):
    """[(Variante, Preis je Einheit, Differenz zu wie angeboten)]; [] ohne Kalkulation. indizes: Positionen des
    Satzes bzw. der Baugruppe (mit ihr selbst); preis(positionen, kalk_zeilen) -> Verkaufspreis je Satz/BG oder None.
    Varianten, die nichts ändern (kein Zukauf bzw. keine Oberfläche), fallen weg."""
    from . import rechnen as r
    katalog = {z.get("name"): z for z in (tabellen or {}).get("zusatzarbeiten") or ()}
    teile = [positionen[i] for i in indizes]
    hat_ob = any(_ist_oberflaeche(z, katalog) for p in teile for z in r.zusatz_liste(p))
    hat_zk = any(ist_zukaufteil(p) or (p.get("zukauf") not in (None, "", "[]")) for p in teile)
    out, basis = [], None
    for name, ob, zk in VARIANTEN:
        if (ob and not hat_ob) or (zk and not hat_zk):
            continue
        pos = abwandeln(positionen, indizes, katalog, ob, zk, loesen) if (ob or zk) else positionen
        zeilen, _ = r.kalkulation(kopf, pos, ergebnis, k, tabellen, einst)
        v = preis(pos, zeilen)
        if v is None:
            return []
        if basis is None:
            basis = v
        out.append((name, v, v - basis))
    return out if len(out) > 1 else []


def fuer_satz(kopf, positionen, ergebnis, k, tabellen, einst, satz, n):
    """Varianten je Satz (Satz in 3D)."""
    from . import bg_kosten

    def preis(pos, zeilen):
        u = bg_kosten.satz_uebersicht(pos, zeilen, satz, n)
        return u["verkauf"] if u else None
    indizes = [i for i, p in enumerate(positionen) if p.get("satz") == satz]
    return rechnen(kopf, positionen, ergebnis, k, tabellen, einst, indizes, {"satz": None}, preis)


def fuer_baugruppe(kopf, positionen, ergebnis, k, tabellen, einst, bg_index):
    """Varianten je Baugruppe (Schweißbaugruppe positionen[bg_index], Einzelteile über baugruppe.teile)."""
    from . import baugruppe, bg_kosten
    bg = baugruppe.lesen(positionen[bg_index].get("baugruppe")) or {}
    if not bg.get("id"):
        return []

    def preis(pos, zeilen):
        u = bg_kosten.uebersicht(pos, zeilen, bg_index)
        return u.get("verkauf") if u else None
    indizes = list(baugruppe.teile(positionen, bg["id"])) + [bg_index]
    return rechnen(kopf, positionen, ergebnis, k, tabellen, einst, indizes, {"bg_knoten": None}, preis)


def html(varianten, einheit="Satz"):
    """Kleine Tabelle für das Ergebnis rechts im Satz-Editor."""
    from .stammdaten import zahl_als_text
    if not varianten:
        return ""
    z = "".join(f"<tr><td>{n}</td><td align='right'>{zahl_als_text(p, 2)} €</td><td align='right'>"
                f"{'' if not d else zahl_als_text(d, 2) + ' €'}</td></tr>" for n, p, d in varianten)
    return (f"<b>Varianten je {einheit}</b> (nur zum Vergleich, keine Staffel angelegt)<table cellspacing='4'>"
            f"{z}</table>")
