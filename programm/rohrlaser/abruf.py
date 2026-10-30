"""Abruf-/Rahmenangebot (Patrick 30.10.2026, Plan „Abruf-Angebot“, Freigabe 1a 2a 3a 4 a und b 5a 6a 7b).

Der Kunde nimmt eine Jahresmenge (von–bis) in Abrufen (von–bis Stück) ab. Die Stückzahlen der Positionen sind der
kleinste Abruf (1a); größere Abrufe stehen als Abrufstufen (Staffeln, nur per Knopf angelegt). Rüsten,
Stangenwechsel und Fracht fallen je Abruf voll an (3a). Einmalkosten (Programmierung, Musterteile) gehen auf die
kleinste Jahresmenge (2a, 5a): Jahresmenge einer Position = Stückzahl des Angebots × Jahresmenge von ÷ Abrufmenge
von, so auch in jeder Abrufstufe (gerechnet wird mit der Stückzahl des Angebots, nicht der Stufe = ungünstigster
Fall). Material wahlweise je Abruf mit Materialklausel (4a) oder für die Jahresmenge bevorratet (4b): dann kommt ein
Lagerzins auf das Material (Zins % p. a. × Laufzeit ÷ 12 × ½, im Mittel ist der halbe Jahresbedarf gebunden).
Im Angebots-PDF steht ein Block „Rahmenbedingungen“ aus dem Textbaustein der Einstellungen (6a).

Ohne Qt, damit Rechnung, Tests und PDF es nutzen können."""
import math

from .stammdaten import ABRUF_LAGER, zahl_als_text

GEBUNDEN = 0.5          # Anteil des Jahresbedarfs, der im Mittel auf Lager liegt (gleichmäßige Abrufe)


def _n(w):
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else 0.0


def aktiv(kopf):
    """True, wenn das Angebot ein Abruf-/Rahmenangebot ist (Haken im Kopf)."""
    return (kopf or {}).get("abruf") == "ja"


def daten(kopf):
    """Werte des Abruf-Angebots oder None (kein Abruf-Angebot oder Jahres-/Abrufmenge fehlt). n = Abrufe bei der
    kleinsten Jahresmenge und dem kleinsten Abruf (≥ 1), lagerzins = Anteil auf das Material (nur bevorratet)."""
    k = kopf or {}
    jv, av = _n(k.get("abruf_jahr_von")), _n(k.get("abruf_von"))
    if not aktiv(k) or jv <= 0 or av <= 0:
        return None
    jb, ab = max(_n(k.get("abruf_jahr_bis")), jv), max(_n(k.get("abruf_bis")), av)
    laufzeit = _n(k.get("abruf_laufzeit")) or 12
    bevorraten = k.get("abruf_material") == ABRUF_LAGER
    zins = _n(k.get("abruf_lagerzins")) / 100 if bevorraten else 0.0
    return dict(jahr_von=jv, jahr_bis=jb, von=av, bis=ab, n=max(jv / av, 1.0), laufzeit=laufzeit,
                bevorraten=bevorraten, zins=zins, lagerzins=zins * laufzeit / 12 * GEBUNDEN)


def jahr_stueck(p, ab):
    """Jahresmenge einer Position [Stück]: Stückzahl im Angebot (in einer Stufe die des Angebots, 'abruf_basis')
    × Abrufe bei der kleinsten Jahresmenge. 0 ohne Stückzahl."""
    basis = p.get("abruf_basis", p.get("stueck"))
    return _n(basis) * ab["n"]


def anteil(p, ab):
    """Anteil der Einmalkosten einer Position, der auf diesen Abruf entfällt: Stückzahl ÷ Jahresmenge (höchstens 1)."""
    if not ab:
        return 1.0
    j = jahr_stueck(p, ab)
    return min(1.0, _n(p.get("stueck")) / j) if j > 0 else 1.0


def abrufe(ab):
    """(wenigste, meiste) Abrufe je Jahr: Jahresmenge von ÷ größtem Abruf, Jahresmenge bis ÷ kleinstem Abruf."""
    return math.ceil(ab["jahr_von"] / ab["bis"] - 1e-9), math.ceil(ab["jahr_bis"] / ab["von"] - 1e-9)


def _menge(a, b):
    a, b = zahl_als_text(a, 0), zahl_als_text(b, 0)
    return a if a == b else f"{a} bis {b}"


def kurz(kopf):
    """Kurzfassung für den Kopf, z. B. '4.000 bis 6.000 Stk./Jahr, Abruf 400 bis 600 Stk., ca. 7 bis 15 Abrufe,
    12 Monate'; leer ohne Abruf-Angebot."""
    ab = daten(kopf)
    if not ab:
        return "Jahresmenge und Abrufmenge fehlen" if aktiv(kopf) else ""
    w, m = abrufe(ab)
    return (f"{_menge(ab['jahr_von'], ab['jahr_bis'])} Stk./Jahr, Abruf {_menge(ab['von'], ab['bis'])} Stk., "
            f"ca. {_menge(w, m)} Abrufe, {zahl_als_text(ab['laufzeit'], 0)} Monate"
            + (f", Material bevorratet (Lagerzins {zahl_als_text(100 * ab['zins'], 1)} % p. a.)" if ab["bevorraten"] else ""))


def stufen_mengen(kopf):
    """Abrufmengen der Abrufstufen über dem kleinsten Abruf (1a): Mitte und größter Abruf, z. B. [500, 600];
    [] ohne Spanne."""
    ab = daten(kopf)
    if not ab or ab["bis"] <= ab["von"]:
        return []
    mitte, bis = int((ab["von"] + ab["bis"]) / 2 + 0.5), int(ab["bis"])
    return [mitte, bis] if ab["von"] < mitte < bis else [bis]


def rahmentext(kopf, einst, muster=False, datum=""):
    """Text „Rahmenbedingungen“ fürs Angebots-PDF aus den Textbausteinen der Einstellungen (6a); leer ohne
    Abruf-Angebot. Platzhalter: {jahr} {abruf} {abrufe} {laufzeit} {material} {muster}; im Materialtext {klausel}
    und {datum}."""
    ab = daten(kopf)
    if not ab:
        return ""
    e = einst or {}
    w, m = abrufe(ab)
    klausel = zahl_als_text(_n(e.get("abruf_klausel")), 1)
    material = (e.get("abruf_text_lager") if ab["bevorraten"] else e.get("abruf_text_klausel")) or ""
    material = material.replace("{klausel}", klausel).replace("{datum}", datum or "Angebotsdatum")
    text = (e.get("abruf_text") or "").replace("{jahr}", _menge(ab["jahr_von"], ab["jahr_bis"])) \
        .replace("{abruf}", _menge(ab["von"], ab["bis"])).replace("{abrufe}", _menge(w, m)) \
        .replace("{laufzeit}", zahl_als_text(ab["laufzeit"], 0)).replace("{material}", material) \
        .replace("{muster}", (e.get("abruf_text_muster") or "") if muster else "")
    return " ".join(text.split())
