"""Position als neue Position kopieren (Patrick 30.10.2026): im selben Angebot duplizieren (Rechtsklick „Position
duplizieren“, Strg+Umschalt+D) oder Positionen aus einem anderen Angebot übernehmen (Auswahl mit Angebotsliste,
Mehrfachauswahl; auch Angebote der Kollegen und festgeschriebene, die nur gelesen werden).

Kopiert wird alles, was zur Position gehört: alle Eingaben (Technik/Konturen, Zusatzarbeiten, Gravur, Zukauf, Naht,
STEP-Merkmale …), das 3D-Netz, die Staffeln je Position bzw. Satz und die Daten „Satz in 3D“. Was als Einheit kopiert
wird, folgt den Blöcken der Positionsliste (reihenfolge.bloecke):
- Schweißbaugruppe markiert: mit allen Einzelteilen, neue Kennung (wie baugruppe.kopie);
- erste Zeile eines Satzes markiert (steht für den ganzen Satz): alle Positionen des Satzes, im selben Angebot unter
  neuem Satznamen „Name (2)“;
- sonst die einzelne Position; ein Einzelteil einer Baugruppe bzw. eine Position eines Satzes wird dabei eine
  eigenständige Position (ohne Zuordnung bzw. Satz).
Im selben Angebot wird die Artikelnummer eindeutig („A-100“ → „A-100-2“), die Kopie steht direkt hinter dem
Original, wenn dort Positionsnummern frei sind (10, 20 → 15), sonst am Ende; aus einem anderen Angebot kommen die
Positionen ans Ende (letzte Pos.-Nummer + 10 …). Der Preis entsteht immer neu aus der Kalkulation."""
from . import baugruppe, reihenfolge, satzgruppen
from .angebot import ist_baugruppe

BG, SATZ, EINZEL = "bg", "satz", "einzel"
SCHRITT = 10
_OHNE = ("id", "angebot_id", "nr")


def _txt(w):
    return "" if w is None else str(w).strip()


def _zahl(w):
    return isinstance(w, (int, float)) and not isinstance(w, bool)


def einheiten(positionen, markiert):
    """Was kopiert wird: [(Art, [Indizes])] in der Reihenfolge der Positionsliste; Art BG (Baugruppe mit Teilen),
    SATZ (ganzer Satz) oder EINZEL (eine Position)."""
    markiert = {i for i in markiert if 0 <= i < len(positionen)}
    out = []
    for gruppe, ix in reihenfolge.bloecke(positionen):
        if not markiert & set(ix):
            continue
        if gruppe and ix[0] in markiert:
            out.append((BG if gruppe[0] == "bg" else SATZ, list(ix)))
        else:
            out += [(EINZEL, [i]) for i in ix if i in markiert]
    return out


def frei(name, vorhanden, muster="{} ({})"):
    """name, sonst 'name (2)', 'name (3)' … (muster), das in vorhanden noch nicht vorkommt."""
    if name not in vorhanden:
        return name
    n = 2
    while muster.format(name, n) in vorhanden:
        n += 1
    return muster.format(name, n)


def luecke(ziel, nach_pos, anzahl):
    """Positionsnummern für anzahl Kopien direkt hinter Pos. nach_pos, wenn bis zur nächsten Nummer genug frei ist
    (10 und 20: 15; drei Kopien: 12, 14, 16), sonst None. Ohne Position dahinter: nach_pos + 10, + 20 …"""
    if not _zahl(nach_pos) or anzahl < 1:
        return None
    danach = [p.get("pos") for p in ziel if _zahl(p.get("pos")) and p["pos"] > nach_pos]
    if not danach:
        return [int(nach_pos) + SCHRITT * (k + 1) for k in range(anzahl)]
    abstand = int(min(danach) - nach_pos)
    if abstand <= anzahl:
        return None
    schritt = max(1, min(SCHRITT, abstand // (anzahl + 1)))
    return [int(nach_pos) + schritt * (k + 1) for k in range(anzahl)]


def kopien(quelle, einheiten_, ziel, gleiches=False, pos_start=None):
    """Neue Positionen für das Angebot mit den Positionen ziel: [(alte Position, neue Werte)] in der Reihenfolge der
    Einheiten. gleiches = Kopie im selben Angebot (Artikelnummer eindeutig; ein Satzname, den es im Ziel schon gibt,
    wird immer „Name (2)“). pos_start = erste
    Positionsnummer (sonst letzte Nummer im Ziel + 10), danach + 10. Zusätzlich je Einheit die Umbenennung der Sätze:
    Ergebnis (paare, saetze {alter Name: neuer Name})."""
    artikel = {_txt(p.get("artikel")) for p in ziel} - {""}
    satz_namen = {satzgruppen.name(p) for p in ziel} - {""}
    if pos_start is None:
        pos_start = int(max((p["pos"] for p in ziel if _zahl(p.get("pos"))), default=0)) + SCHRITT
    paare, saetze = [], {}
    for art, ix in einheiten_:
        if art == BG:
            bg_id = (baugruppe.lesen(quelle[ix[0]].get("baugruppe")) or {}).get("id")
            teil = baugruppe.kopie(quelle, bg_id) if bg_id else []
            if not teil:        # Baugruppe nicht lesbar: Positionen einzeln, wie sie sind
                teil = [(quelle[i], dict(quelle[i])) for i in ix]
        else:
            teil = [(quelle[i], dict(quelle[i])) for i in ix]
        for alt, w in teil:
            for f in _OHNE:
                w.pop(f, None)
            if art == EINZEL:
                if baugruppe.zuordnung(alt)[0]:
                    w.pop("bg_knoten", None)
                    w.pop("je_knoten", None)
                if satzgruppen.name(alt) and not ist_baugruppe(alt):
                    w.pop("satz", None)
                    w.pop("je_satz", None)
            elif art == SATZ:
                n = satzgruppen.name(alt)
                if n not in saetze:
                    saetze[n] = frei(n, satz_namen)      # Name schon im Ziel: „Name (2)“
                    satz_namen.add(saetze[n])
                w["satz"] = saetze[n]
            if gleiches and _txt(w.get("artikel")):
                w["artikel"] = frei(_txt(w["artikel"]), artikel, "{}-{}")
            if _txt(w.get("artikel")):
                artikel.add(_txt(w["artikel"]))
            w["pos"] = pos_start + SCHRITT * len(paare)
            paare.append((alt, w))
        if art == BG and ist_baugruppe(teil[0][0]):
            _bg_name(teil, satz_namen, saetze)
    return paare, saetze


def _bg_name(teil, satz_namen, saetze):
    """Satzname der kopierten Baugruppe (= Bezeichnung, sonst Artikelnummer, baugruppe.name) eindeutig im Ziel:
    gibt es ihn dort schon, wird die Bezeichnung „Name (2)“; Baugruppe und Teile bekommen den neuen Satznamen."""
    alt, kopf = teil[0]
    alt_name = baugruppe.name(alt)
    neu = baugruppe.name(kopf)
    if neu in satz_namen:
        neu = frei(neu, satz_namen)
        kopf["bezeichnung"] = neu
    satz_namen.add(neu)
    saetze[alt_name] = neu
    for q, w in teil:
        if satzgruppen.name(q) == alt_name or q is alt:
            w["satz"] = neu


def staffeln_kopieren(staffeln, stufen, paare, saetze):
    """Staffeln der kopierten Positionen bzw. Sätze: [(Werte der Stufe, [Mengenzeilen])] für das Ziel. Schlüssel =
    Pos.-Nummer (Position ohne Satz) bzw. Satzname; Mengenzeilen derselben Stufe bleiben zusammen."""
    schl = {}
    for alt, w in paare:
        if not satzgruppen.name(alt) and _txt(alt.get("pos")):
            schl[_txt(alt["pos"])] = _txt(w.get("pos"))
    schl.update({a: n for a, n in saetze.items() if a})
    stufe_von = {s["id"]: s for s in stufen}
    out = {}
    for z in staffeln:
        neu = schl.get(_txt(z.get("schluessel")))
        if not neu:
            continue
        k = z.get("stufe_id")
        out.setdefault(k, (stufe_von.get(k) or {}, []))[1].append(dict(z, schluessel=neu))
    return list(out.values())


def folge_dahinter(positionen, neue_ids, original):
    """Positions-IDs in der Reihenfolge der Liste mit den neuen Positionen (neue_ids) direkt hinter dem Block der
    Original-Position (Index original in positionen, die die neuen schon enthalten)."""
    neu = set(neue_ids)
    alle = [i for i in reihenfolge.anzeige(positionen)]
    block = next((ix for _, ix in reihenfolge.bloecke(positionen) if original in ix), [original])
    rest = [i for i in alle if positionen[i]["id"] not in neu]
    k = rest.index(block[-1]) + 1 if block[-1] in rest else len(rest)
    dazu = [i for i in alle if positionen[i]["id"] in neu]
    return [positionen[i]["id"] for i in rest[:k] + dazu + rest[k:]]


def text(paare):
    """Kurzbeschreibung: '3 Positionen (Pos. 40–60)'."""
    nr = [w.get("pos") for _, w in paare if _zahl(w.get("pos"))]
    bereich = f" (Pos. {nr[0]}" + (f"–{nr[-1]}" if len(nr) > 1 else "") + ")" if nr else ""
    return (f"{len(paare)} Position" + ("en" if len(paare) != 1 else "")) + bereich
