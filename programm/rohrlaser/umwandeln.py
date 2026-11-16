"""Einzelteile, Sätze und Schweißbaugruppen ineinander umwandeln (Patrick 06.11.2026, Freigabe „Alle Empfehlungen“).

    Einzelteile  ──„Als Satz zusammenfassen …“──▶  Satz  ──„Satz → Schweißbaugruppe …“──▶  Schweißbaugruppe
    Einzelteile  ◀──────„Satz auflösen“───────  Satz  ◀────„Schweißbaugruppe → Satz“─────  Schweißbaugruppe

Regeln (F1a–F5a):
- Satz bilden (F1a): Name und Anzahl Sätze wählt man im Fenster; Vorschlag ist der größte gemeinsame Teiler der
  Stückzahlen. Die Stückzahlen bleiben, Stück je Satz = Stückzahl ÷ Anzahl Sätze (muss ganz aufgehen, nichts wird
  gerundet). Schweißbaugruppen und ihre Teile lassen sich nicht in einen Satz nehmen (sie sind schon einer).
- Satz auflösen (F4a): Satz und Stück je Satz werden geleert, jede Position behält ihre Gesamtstückzahl.
- Schweißbaugruppe → Satz (F2a, F3a): die Position der Baugruppe fällt weg, die Teile bleiben mit dem Namen der
  Baugruppe als Satz und Stück je Satz = Stück je Baugruppe (Unterbaugruppen flach, Mengen multipliziert); die
  Stückzahlen bleiben. Baugruppe (Nähte, Arbeitsgänge, Vorrichtungen, Unterbaugruppen, Steckverbindungen), die
  übrigen Felder ihrer Position und die Zuordnung der Teile werden je Satz in angebote.satz_daten gemerkt
  (Schlüssel MERK); die Steckverbindungen stehen danach auch im Satz in 3D.
- Satz → Schweißbaugruppe: der Editor der Schweißbaugruppe öffnet mit allen Teilen des Satzes, Anzahl Baugruppen =
  Anzahl Sätze, Name = Satzname (Staffeln mit dem Satznamen gelten weiter). Gibt es einen gemerkten Stand, setzt er
  Baugruppe, Felder und Zuordnung wieder ein (Teile, deren Stück je Satz sich inzwischen geändert hat, und neue
  Teile kommen direkt unter die Baugruppe). Ohne gemerkten Stand übernimmt die Baugruppe die Steckverbindungen des
  Satzes.
Preise, Zusatzarbeiten, Konturen, Lage (3D) und Positionsnummern der Teile ändern sich nie; Staffeln werden weder
angelegt noch geändert (ein Hinweis nennt Staffeln, die nicht mehr passen). Nur Rechnen, keine Oberfläche.
"""
import copy
import json
import math

from . import baugruppe, satz_menge
from .angebot import BAUGRUPPE, ist_baugruppe

MERK = "baugruppe_merk"         # gemerkte Schweißbaugruppe je Satz in angebote.satz_daten
# Felder der Position einer Baugruppe, die nicht gemerkt werden (Kennung, Ort, Mengen und die Baugruppe selbst)
_NICHT_MERKEN = ("id", "angebot_id", "nr", "pos", "stueck", "satz", "je_satz", "baugruppe")
_TEIL_FELDER = ("bg_knoten", "je_knoten", "bg_hilfe")


def _ganz(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and abs(x - round(x)) < 1e-9


def _frei(p):
    """True für eine Position, die in einen Satz darf: keine Schweißbaugruppe und kein Teil einer Baugruppe."""
    return not ist_baugruppe(p) and not baugruppe.zuordnung(p)[0]


# ------------------------------------------------------------------ Einzelteile → Satz
def satz_name_vorschlag(positionen):
    """Erster freier Name „Satz 1“, „Satz 2“ … (auch Namen von Schweißbaugruppen zählen als belegt)."""
    belegt = {satz_menge.name(p) for p in positionen} | {baugruppe.name(positionen[i], bg) for i, bg in
                                                         baugruppe.baugruppen(positionen).values()}
    n = 1
    while f"Satz {n}" in belegt:
        n += 1
    return f"Satz {n}"


def saetze_vorschlag(positionen, zeilen):
    """Anzahl Sätze für die markierten Positionen: größter gemeinsamer Teiler der Stückzahlen (1 ohne Stückzahlen)."""
    st = [int(round(positionen[r].get("stueck"))) for r in zeilen
          if _ganz(positionen[r].get("stueck")) and positionen[r].get("stueck") >= 1]
    return math.gcd(*st) if st else 1


def satz_bilden_pruefen(positionen, zeilen, name, saetze):
    """Fehlertext, wenn sich die Positionen so nicht zu einem Satz zusammenfassen lassen, sonst None."""
    name = str(name or "").strip()
    if not zeilen:
        return "Bitte zuerst die Einzelteile markieren, die ein Satz werden sollen."
    if not name:
        return "Bitte einen Namen für den Satz eintragen."
    bg_namen = {baugruppe.name(positionen[i], bg) for i, bg in baugruppe.baugruppen(positionen).values()}
    if name in bg_namen:
        return f"„{name}“ ist schon der Name einer Schweißbaugruppe. Bitte einen anderen Namen wählen."
    if not _ganz(saetze) or saetze < 1:
        return "Die Anzahl Sätze muss eine ganze Zahl ab 1 sein."
    for r in zeilen:
        p = positionen[r]
        if not _frei(p):
            return (f"Pos. {p.get('pos') or ''}: Schweißbaugruppen und ihre Teile sind schon ein Satz. Erst "
                    "„Schweißbaugruppe → Satz“ wählen.")
        st = p.get("stueck")
        if not _ganz(st) or st < 1:
            return f"Pos. {p.get('pos') or ''}: Stückzahl fehlt."
        if int(round(st)) % int(saetze):
            return (f"Pos. {p.get('pos') or ''}: {int(round(st))} Stück lassen sich nicht in ganzen Stück auf "
                    f"{int(saetze)} Sätze verteilen. Vorschlag: {saetze_vorschlag(positionen, zeilen)} "
                    f"{'Satz' if saetze_vorschlag(positionen, zeilen) == 1 else 'Sätze'}.")
    return None


def satz_bilden(positionen, zeilen, name, saetze):
    """Änderungen [(Positions-ID, Feld, Wert)]: Satz = name, Stück je Satz = Stückzahl ÷ Sätze; Stückzahl bleibt.
    Vorher satz_bilden_pruefen aufrufen (sonst ValueError)."""
    f = satz_bilden_pruefen(positionen, zeilen, name, saetze)
    if f:
        raise ValueError(f)
    name, saetze = str(name).strip(), int(saetze)
    out = []
    for r in sorted(set(zeilen)):
        p = positionen[r]
        je = int(round(p["stueck"])) // saetze
        if satz_menge.name(p) != name:
            out.append((p["id"], "satz", name))
        if p.get("je_satz") != je:
            out.append((p["id"], "je_satz", je))
    return out


# ------------------------------------------------------------------ Satz → Einzelteile
def satz_aufloesen(positionen, satz):
    """Änderungen [(Positions-ID, Feld, Wert)]: Satz und Stück je Satz leer, die Stückzahl bleibt (F4a). Teile von
    Schweißbaugruppen bleiben unberührt (die Baugruppe zuerst in einen Satz umwandeln)."""
    out = []
    for i in satz_menge.satz_positionen(positionen, satz):
        p = positionen[i]
        out += [(p["id"], f, None) for f in ("satz", "je_satz") if p.get(f) is not None]
    return out


def staffeln_hinweis(staffeln, alt):
    """Hinweis, wenn Staffeln den Satz alt als Schlüssel tragen (sie gelten nach dem Auflösen nicht mehr)."""
    n = sum(1 for z in staffeln or () if str(z.get("schluessel") or "").strip() == str(alt or "").strip())
    return (f"{n} Staffelzeile(n) für „{alt}“ passen nicht mehr (Staffeln werden nie automatisch geändert)."
            if n else None)


# ------------------------------------------------------------------ Schweißbaugruppe → Satz
def bg_von_zeile(positionen, r):
    """Baugruppen-ID der Zeile r (die Baugruppe selbst oder eines ihrer Teile), sonst None."""
    if not 0 <= r < len(positionen):
        return None
    p = positionen[r]
    bg_id = (baugruppe.lesen(p.get("baugruppe")) or {}).get("id") if ist_baugruppe(p) else baugruppe.zuordnung(p)[0]
    return bg_id if bg_id in baugruppe.baugruppen(positionen) else None


def bg_zu_satz(positionen, bg_id, daten=None):
    """Schweißbaugruppe bg_id in einen Satz umwandeln (F2a, F3a). daten: bisherige satz_daten des Satzes (oder None).
    Ergebnis: dict(satz = Name, aenderungen = [(Positions-ID, Feld, Wert)], loeschen = [Positions-ID der Baugruppe],
    daten = neue satz_daten des Satzes) oder None ohne lesbare Baugruppe."""
    alle = baugruppe.baugruppen(positionen)
    if bg_id not in alle:
        return None
    i, bg = alle[bg_id]
    p = positionen[i]
    name = baugruppe.name(p, bg)
    soll = baugruppe.soll_werte(positionen)
    aend, teile = [], {}
    for j in baugruppe.teile(positionen, bg_id):
        q = positionen[j]
        s = soll.get(j) or {}
        je = s.get("je_satz") or satz_menge.je_satz(q)
        st = q.get("stueck")
        teile[str(q["id"])] = dict({f: q.get(f) for f in _TEIL_FELDER}, je_satz=je)
        for f in _TEIL_FELDER:
            if q.get(f) is not None:
                aend.append((q["id"], f, None))
        if satz_menge.name(q) != name:
            aend.append((q["id"], "satz", name))
        if q.get("je_satz") != je:
            aend.append((q["id"], "je_satz", je))
        if s.get("stueck") is not None and st != s["stueck"]:   # Stückzahl so, wie die Baugruppe sie rechnet
            aend.append((q["id"], "stueck", s["stueck"]))
    neu = dict(daten or {})
    neu[MERK] = dict(baugruppe=json.loads(baugruppe.speichern(bg)),
                     position={k: v for k, v in p.items() if k not in _NICHT_MERKEN and v is not None},
                     teile=teile)
    stecken = [copy.deepcopy(v) for v in bg.get("steckverbindungen") or () if isinstance(v, dict) and v.get("id")]
    if stecken:
        neu["steckverbindungen"] = stecken
    return dict(satz=name, aenderungen=aend, loeschen=[p["id"]], daten=neu)


# ------------------------------------------------------------------ Satz → Schweißbaugruppe
def satz_zu_bg_pruefen(positionen, satz):
    """Fehlertext, wenn der Satz keine Schweißbaugruppe werden kann, sonst None."""
    satz = str(satz or "").strip()
    idx = satz_menge.satz_positionen(positionen, satz)
    if not satz or not idx:
        if any(baugruppe.zuordnung(p)[0] or ist_baugruppe(p) for p in positionen if satz_menge.name(p) == satz
               and satz):
            return f"„{satz}“ ist schon eine Schweißbaugruppe."
        return "Bitte eine Position markieren, die in einem Satz steht (Spalte Satz)."
    n = satz_menge.anzahl(positionen, satz)
    if not n or not _ganz(n) or n < 1:
        return (f"Satz {satz}: Die Stückzahlen ergeben keine ganze Anzahl Sätze. Bitte erst „Satz bearbeiten "
                "(Anzahl Sätze) …“ prüfen.")
    return None


def satz_zu_bg(positionen, satz, daten=None):
    """Vorlage für den Editor der Schweißbaugruppe aus dem Satz. daten: satz_daten des Satzes (mit gemerkter
    Baugruppe unter MERK). Ergebnis: dict(position = vorbelegte Position der Baugruppe (ohne pos), vorwahl =
    {Positions-ID: (Knoten-ID, Stück je Knoten, Positionierhilfe)}, extra = gemerkte weitere Felder der Position, wieder = True wenn
    ein gemerkter Stand eingesetzt wurde) oder None (satz_zu_bg_pruefen)."""
    if satz_zu_bg_pruefen(positionen, satz):
        return None
    satz = str(satz).strip()
    idx = satz_menge.satz_positionen(positionen, satz)
    n = int(round(satz_menge.anzahl(positionen, satz)))
    daten = daten or {}
    merk = daten.get(MERK) if isinstance(daten.get(MERK), dict) else {}
    bg = baugruppe.lesen(merk.get("baugruppe")) if merk.get("baugruppe") else None
    wieder = bg is not None
    if bg is None:
        bg = baugruppe.leer()
        bg["steckverbindungen"] = [copy.deepcopy(v) for v in daten.get("steckverbindungen") or ()
                                   if isinstance(v, dict) and v.get("id")]
    elif bg["id"] in baugruppe.baugruppen(positionen):     # Kennung inzwischen vergeben (z. B. kopiert)
        bg["id"] = baugruppe.neue_id()
    knoten = {k["id"] for k in bg["knoten"] if k.get("id")}
    gemerkt = merk.get("teile") if isinstance(merk.get("teile"), dict) else {}
    vorwahl = {}
    for i in idx:
        q = positionen[i]
        je = satz_menge.je_satz(q)
        m = gemerkt.get(str(q["id"])) or {}
        kn = baugruppe.zuordnung(dict(bg_knoten=m.get("bg_knoten")))[1] or ""
        if m and m.get("je_satz") == je and (not kn or kn in knoten) and _ganz(m.get("je_knoten")):
            vorwahl[q["id"]] = (kn, int(m["je_knoten"]), m.get("bg_hilfe"))
        else:                                               # neu oder geändert: direkt unter die Baugruppe
            vorwahl[q["id"]] = ("", je, None)
    extra = {k: v for k, v in (merk.get("position") or {}).items() if k not in _NICHT_MERKEN and k != "art"}
    position = dict(extra, art=BAUGRUPPE, stueck=n, baugruppe=baugruppe.speichern(bg))
    if baugruppe.name(position) != satz:        # Name = Satzname (Staffeln mit dem Satznamen gelten weiter)
        position["bezeichnung"] = satz
    return dict(position=position, vorwahl=vorwahl, extra=extra, wieder=wieder)


def ohne_merk(daten):
    """satz_daten eines Satzes ohne den gemerkten Stand der Baugruppe (nach dem Zurückwandeln)."""
    return {k: v for k, v in (daten or {}).items() if k != MERK}
