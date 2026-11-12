"""Qualitätskosten aus dem Prüfplan (Plan X1–X8, Paket X4, Patrick 12.11.2026, Freigabe „Alle Empfehlungen“).

Je Position mit Qualitätsstufe (Stammdaten „Qualitätsstufen“, leer ausgeliefert):

    Q = (M × t_Merkmal × n_Prüf + 60 × (t_Erstmuster + t_Protokoll)) / 3600 × S_QS     [€ je Position und Los]

M = Prüfmerkmale der Position aus dem Prüfplan (pruefplan.merkmale: Länge, Gehrungen, je Kontur Maß, Lage, Teilung),
t_Merkmal = Messzeit je Merkmal [s], n_Prüf = geprüfte Teile (alle, jedes n-te = ⌈Stück / n⌉, erste n = min(n, Stück)),
Erstmuster und Protokoll [min] einmal je Los (Position; jede Staffel ist ein eigenes Los), S_QS = Stundensatz der
Stufe. Kein Prozentaufschlag. Der Messzyklus an der Maschine bleibt Maschinenzeit; Q ist die Messung von Hand.
Steht an der Position schon die Zusatzarbeit „Erstmusterprüfung“ (pruefplan.ZUSATZ), zählt die Erstmusterzeit der
Stufe nicht (keine Doppelzählung). Fehlt der Stundensatz, wird nichts erfunden: Q = 0 mit Hinweis. Ohne Qt."""
import math

from .pruefplan import ZUSATZ as ERSTMUSTER_ZUSATZ, merkmale

ALLE, JEDES_N, ERSTE_N = "alle Teile", "jedes n-te Teil", "erste n Teile"


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def stufe(name, tabellen):
    """Zeile der Qualitätsstufe (aktiv) oder None."""
    if not name:
        return None
    return next((z for z in (tabellen or {}).get("qualitaetsstufen") or ()
                 if z.get("name") == name and z.get("aktiv") != "nein"), None)


def satz(z, tabellen):
    """Stundensatz QS der Stufe [€/h] (Stammdaten Stundensätze oder eigener) oder None."""
    if z.get("satz_id"):
        return next((s.get("satz") for s in (tabellen or {}).get("stundensaetze") or ()
                     if s.get("satz_id") == z["satz_id"]), None)
    return z.get("satz") if isinstance(z.get("satz"), (int, float)) else None


def gepruefte_teile(z, stueck):
    """Anzahl geprüfter Teile eines Loses."""
    c = int(_n(stueck))
    n = max(1, int(_n(z.get("pruef_n")) or 1))
    art = z.get("pruefanteil") or ALLE
    if art == JEDES_N:
        return math.ceil(c / n) if c else 0
    if art == ERSTE_N:
        return min(n, c)
    return c


def kosten(p, stueck, tabellen):
    """Qualitätskosten einer Position für ein Los mit stueck Teilen: dict(stufe, merkmale, gepruefte, min, satz, eur,
    hinweis, erstmuster_zusatz) oder None ohne Stufe. min = Prüfzeit von Hand je Los [min]."""
    name = p.get("qualitaet")
    if not name:
        return None
    z = stufe(name, tabellen)
    if z is None:
        return dict(stufe=name, merkmale=0, gepruefte=0, min=0.0, satz=None, eur=0.0, erstmuster_zusatz=False,
                    hinweis=f"Qualitätsstufe '{name}' unbekannt oder aus")
    from .rechnen import zusatz_liste
    m = len(merkmale(p))
    n = gepruefte_teile(z, stueck)
    zusatz = any(e.get("name") == ERSTMUSTER_ZUSATZ for e in zusatz_liste(p))
    erst = 0.0 if zusatz else _n(z.get("erstmuster"))
    sek = m * _n(z.get("zeit_merkmal")) * n + 60 * (erst + _n(z.get("protokoll")))
    s = satz(z, tabellen)
    hinweis = "" if s is not None or not sek else "Qualität: Stundensatz QS fehlt, nicht gerechnet"
    return dict(stufe=name, merkmale=m, gepruefte=n, min=sek / 60, satz=s, eur=sek / 3600 * _n(s),
                erstmuster_zusatz=zusatz, hinweis=hinweis)


def pruefung(z, k=None):
    """Prüfspalte der Qualitätsstufen."""
    if z.get("pruefanteil") in (JEDES_N, ERSTE_N) and not _n(z.get("pruef_n")):
        return "FEHLER: n fehlt (jedes n-te bzw. erste n Teile)"
    if not z.get("pruefanteil") and _n(z.get("zeit_merkmal")):
        return "FEHLER: Prüfanteil wählen (alle Teile, jedes n-te, erste n)"
    zeit = _n(z.get("zeit_merkmal")) or _n(z.get("erstmuster")) or _n(z.get("protokoll"))
    if zeit and not z.get("satz_id") and not isinstance(z.get("satz"), (int, float)):
        return "WARNUNG: ohne Stundensatz QS rechnet die Stufe 0 € (Stundensatz wählen)"
    if not zeit:
        return "WARNUNG: keine Zeit eingetragen, die Stufe kostet nichts"
    return None
