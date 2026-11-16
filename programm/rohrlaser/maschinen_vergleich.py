"""Maschinenvergleich im Angebot (Vorschlag F1, Patrick 02.11.2026 „Alle weiter“ = F1b).

Das Angebot wird auf jeder Maschine der Stammdaten gerechnet, wie es das Angebotsfenster nach „Maschine ändern“ tun
würde: Stundensatz und Zeitvorgaben der Maschine (Zeitbasis), Konturklassen nach den Grenzen der Maschine, neu
optimiert (Hüllkreis, Metergewicht, Greiferrest und Stangenlängen der Maschine). Teile, die auf einer Maschine nicht
eingeplant werden können, machen sie „nicht möglich“. Gespeichert wird nichts; „Diese Maschine nehmen“ stellt das
Angebot im Fenster um (wie die Auswahl im Kopf).

Der Angebots-Check nennt einen HINWEIS, wenn eine andere Maschine mehr als HINWEIS_AB günstiger ist (Variante b).
Ohne Qt."""
from . import rechnen

HINWEIS_AB = 0.05          # andere Maschine mindestens 5 % günstiger: Hinweis im Angebots-Check


def _konturen(positionen, m, k):
    """Positionen mit den Konturklassen der Maschine m (Kopien, nichts gespeichert)."""
    out = []
    for p in positionen:
        z = rechnen.konturklassen_neu(p, m, rechnen.wand_position(p, k)) if m is not None else None
        out.append(dict(p, **z) if z else p)
    return out


def rechnen_auf(kopf, positionen, maschine, k_akt, tab_akt, einst_db, zeitbasis_von=None):
    """Angebot auf einer Maschine: dict(maschine, moeglich, grund, laser_h, verkauf, stueck_preis={pos: €},
    nicht=Anzahl nicht eingeplanter Teile). zeitbasis_von(m) = Datenbank.zeitbasis_vorgabe (Stundensatz der Maschine,
    wenn das Angebot eine Zeitbasis hat)."""
    kopf_m = dict(kopf, maschine=maschine)
    if kopf.get("zeitbasis") and zeitbasis_von is not None:
        kopf_m["zeitbasis"] = dict(kopf["zeitbasis"], maschine=zeitbasis_von(maschine)["maschine"])
    k, tab = rechnen.preisbasis_anwenden(kopf_m, k_akt, tab_akt)
    m = rechnen.maschine(kopf_m, k)
    pos = _konturen(positionen, m, k)
    einst = rechnen.einstellungen_angebot(kopf_m, rechnen.einstellungen_fest(tab, einst_db))
    try:
        erg = rechnen.optimieren(kopf_m, pos, k, tab, einst)
        zeilen, s = rechnen.kalkulation(kopf_m, pos, erg, k, tab, einst)
    except (ValueError, KeyError, ZeroDivisionError, TypeError) as f:
        return dict(maschine=maschine, moeglich=False, grund=f"nicht rechenbar ({f})", laser_h=None, verkauf=None,
                    stueck_preis={}, nicht=0)
    nicht = sum(int(z.get("nicht_eingeplant") or 0) for z in zeilen if z)
    laser_h = sum((z.get("laser_netto") or 0) * (z.get("stueck") or 0) for z in zeilen if z) / 3600
    return dict(maschine=maschine, moeglich=nicht == 0, grund=f"{nicht} Teil(e) nicht eingeplant" if nicht else "",
                laser_h=laser_h, verkauf=s.get("verkauf"), nicht=nicht,
                stueck_preis={p.get("pos"): z.get("preis_teil") for p, z in zip(pos, zeilen) if z})


def vergleich(kopf, positionen, k_akt, tab_akt, einst_db, zeitbasis_von=None, maschinen=None):
    """Liste je Maschine (wie rechnen_auf), die aktuelle Maschine zuerst, dann nach Preis (nicht mögliche zuletzt)."""
    alle = list(maschinen or sorted(k_akt.maschinen))
    out = [rechnen_auf(kopf, positionen, m, k_akt, tab_akt, einst_db, zeitbasis_von) for m in alle]
    jetzt = kopf.get("maschine")
    return sorted(out, key=lambda r: (r["maschine"] != jetzt, not r["moeglich"], r["verkauf"] or 0))


def guenstiger(liste, maschine, ab=HINWEIS_AB):
    """Beste mögliche andere Maschine, wenn sie mehr als ab (Anteil) günstiger ist als maschine: (Zeile, Anteil) oder
    None."""
    jetzt = next((r for r in liste if r["maschine"] == maschine), None)
    if not jetzt or not jetzt["verkauf"]:
        return None
    andere = [r for r in liste if r["maschine"] != maschine and r["moeglich"] and r["verkauf"]]
    if not andere:
        return None
    best = min(andere, key=lambda r: r["verkauf"])
    anteil = 1 - best["verkauf"] / jetzt["verkauf"]
    return (best, anteil) if anteil > ab else None


def check_punkt(liste, maschine):
    """Hinweis für den Angebots-Check oder None."""
    from .stammdaten import zahl_als_text as zahl
    g = guenstiger(liste, maschine)
    if not g:
        return None
    best, anteil = g
    return ("HINWEIS", f"Auf Maschine {best['maschine']} wäre das Angebot {zahl(100 * anteil, 1)} % günstiger "
                       f"({zahl(best['verkauf'], 2)} € netto) – Maschinen vergleichen …", None)
