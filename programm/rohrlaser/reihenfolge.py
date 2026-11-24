"""Reihenfolge der Positionen im Angebot ändern (Patrick 29.10.2026): markierte Positionen nach oben/unten, an den
Anfang/ans Ende oder per Drag & Drop am Zeilenkopf. Gerechnet wird in der Reihenfolge der Positionsliste: eine
Schweißbaugruppe wandert mit ihren Einzelteilen, ein Satz mit allen seinen Positionen; Einzelteile einer Baugruppe
bzw. Positionen eines Satzes lassen sich innerhalb ihrer Gruppe umstellen. Danach gilt die neue Reihenfolge überall
(Positionsliste, Kalkulation, Angebots-PDF, Werkstattpapiere): Feld nr = 1, 2, 3 …. Positionsnummern: standen sie
in der Liste aufsteigend, bleiben sie es (die vorhandenen Nummern werden der Reihe nach neu verteilt, 10, 20, 30 …
bleibt 10, 20, 30 …); sonst (eigenes Schema, z. B. Baugruppe 100 über Teilen 10–30) behält jede Position ihre Nummer.
„Positionsnummern neu vergeben“ zählt 10, 20, 30 … in der Reihenfolge der Liste. Staffeln je Position und ein
aktueller Schnittplan ziehen mit (gleiche Stangen, neue Nummern)."""
import copy
import re

from . import baugruppe, satzgruppen

OBEN, UNTEN, ANFANG, ENDE = -1, 1, "anfang", "ende"


def _zahl(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def bloecke(positionen):
    """Blöcke in der Reihenfolge der Positionsliste: [(Gruppe, [Indizes])]. Gruppe = ('bg', Baugruppen-ID) für eine
    Schweißbaugruppe mit ihren Einzelteilen (Baugruppe zuerst), ('satz', Name) für die Positionen eines Satzes,
    None für eine einzelne Position. Gleiche Reihenfolge wie die Anzeige (AngebotSeite._gruppieren)."""
    folge, zu = baugruppe.gruppen_reihenfolge(positionen)
    koepfe = {i: bg_id for bg_id, (i, _) in baugruppe.baugruppen(positionen).items()}
    saetze = satzgruppen.saetze(positionen, set(zu) | set(koepfe))
    folge = satzgruppen.ordnen(folge, saetze)
    satz_von = {i: n for n, ix in saetze.items() if len(ix) > 1 for i in ix}
    out = []
    for i in folge:
        if i in zu or (i in satz_von and out and out[-1][0] == ("satz", satz_von[i])):
            out[-1][1].append(i)            # Einzelteil unter seiner Baugruppe bzw. weitere Position des Satzes
        elif i in koepfe:
            out.append((("bg", koepfe[i]), [i]))
        elif i in satz_von:
            out.append((("satz", satz_von[i]), [i]))
        else:
            out.append((None, [i]))
    return out


def anzeige(positionen):
    """Indizes in der Reihenfolge der Positionsliste."""
    return [i for _, ix in bloecke(positionen) for i in ix]


def _mitglieder(block):
    """Umstellbare Positionen innerhalb eines Blocks: Einzelteile einer Baugruppe (ohne die Baugruppe selbst) bzw.
    alle Positionen eines Satzes."""
    gruppe, ix = block
    return ix[1:] if gruppe and gruppe[0] == "bg" else ix if gruppe else []


def _bewegen(liste, gewaehlt, ziel):
    """Liste mit den gewählten Einträgen einen Schritt nach oben/unten bzw. an den Anfang/ans Ende (Reihenfolge der
    gewählten untereinander bleibt)."""
    liste = list(liste)
    if ziel == ANFANG:
        return [x for x in liste if x in gewaehlt] + [x for x in liste if x not in gewaehlt]
    if ziel == ENDE:
        return [x for x in liste if x not in gewaehlt] + [x for x in liste if x in gewaehlt]
    reihe = range(1, len(liste)) if ziel == OBEN else range(len(liste) - 2, -1, -1)
    for k in reihe:
        j = k - 1 if ziel == OBEN else k + 1
        if liste[k] in gewaehlt and liste[j] not in gewaehlt:
            liste[k], liste[j] = liste[j], liste[k]
    return liste


def _innerhalb(bl, markiert):
    """Block, in dessen Gruppe alle markierten Positionen umgestellt werden (alle Einzelteile derselben Baugruppe
    bzw. weitere Positionen desselben Satzes), sonst None. Die erste Position eines Satzes (Zeile mit ▾ und dem
    Satznamen) steht für den ganzen Satz: ist sie markiert, wandert der Satz."""
    for n, b in enumerate(bl):
        m = _mitglieder(b)
        if m and markiert <= set(m) and len(m) > 1 and not (b[0][0] == "satz" and b[1][0] in markiert):
            return n
    return None


def verschieben(positionen, markiert, ziel):
    """Neue Reihenfolge (Liste alter Indizes) nach dem Verschieben der markierten Positionen (Indizes) um einen
    Schritt (OBEN, UNTEN) bzw. an den Anfang/ans Ende (ANFANG, ENDE); None, wenn sich nichts ändert. Markierte
    Einzelteile derselben Baugruppe bzw. Positionen desselben Satzes wandern innerhalb ihrer Gruppe, sonst wandern
    ganze Blöcke (Baugruppe mit Teilen, Satz)."""
    markiert = {i for i in markiert if 0 <= i < len(positionen)}
    if not markiert:
        return None
    bl = bloecke(positionen)
    alt = [i for _, ix in bl for i in ix]
    n = _innerhalb(bl, markiert)
    if n is not None:
        gruppe, ix = bl[n]
        m = _mitglieder(bl[n])
        neu = _bewegen(m, markiert, ziel)
        bl[n] = (gruppe, ix[:len(ix) - len(m)] + neu)
    else:
        gewaehlt = {k for k, (_, ix) in enumerate(bl) if markiert & set(ix)}
        bl = [bl[k] for k in _bewegen(range(len(bl)), gewaehlt, ziel)]
    folge = [i for _, ix in bl for i in ix]
    return folge if folge != alt else None


def einsetzen(positionen, quelle, vor):
    """Drag & Drop: neue Reihenfolge, wenn Position quelle vor die Position vor gezogen wird (Index; None = ans
    Ende), oder None. Innerhalb der eigenen Gruppe (Einzelteile einer Baugruppe, Satz) wird nur dort umgestellt; sonst
    wandert der ganze Block und landet vor dem Block von vor (mitten in einen Block gezogen: dahinter)."""
    if not 0 <= quelle < len(positionen) or quelle == vor:
        return None
    bl = bloecke(positionen)
    alt = [i for _, ix in bl for i in ix]
    for n, b in enumerate(bl):
        m = _mitglieder(b)
        if quelle in m and len(m) > 1 and (vor in m or (vor is None and alt[-1] in b[1]) or
                                           (vor is not None and alt.index(vor) == alt.index(b[1][-1]) + 1)):
            rest = [i for i in m if i != quelle]
            k = rest.index(vor) if vor in rest else len(rest)
            bl[n] = (b[0], b[1][:len(b[1]) - len(m)] + rest[:k] + [quelle] + rest[k:])
            folge = [i for _, ix in bl for i in ix]
            return folge if folge != alt else None
    von = next(k for k, (_, ix) in enumerate(bl) if quelle in ix)
    block = bl.pop(von)
    if vor is None or vor in block[1]:
        ziel = len(bl) if vor is None else von
    else:
        ziel = next(k for k, (_, ix) in enumerate(bl) if vor in ix)
        if bl[ziel][1][0] != vor:
            ziel += 1                       # mitten in einen Block gezogen: dahinter
    bl.insert(ziel, block)
    folge = [i for _, ix in bl for i in ix]
    return folge if folge != alt else None


SCHRITT = 10        # Positionsnummern neu vergeben: 10, 20, 30 …


def aufsteigend(positionen):
    """True, wenn die Positionsnummern in der gespeicherten Reihenfolge (Feld nr) aufsteigen (gleiche erlaubt, ohne
    Nummer zählt nicht); die Anzeige zieht Sätze zusammen, danach stehen sie auch dort aufsteigend."""
    werte = [p.get("pos") for p in positionen if _zahl(p.get("pos"))]
    return werte == sorted(werte)


def nummern(positionen, folge, neu_vergeben=False):
    """Positionsnummern in der neuen Reihenfolge (folge = alte Indizes): aufsteigende Nummern werden der Reihe nach
    neu verteilt (Positionen ohne Nummer bleiben ohne), sonst behält jede Position ihre Nummer; neu_vergeben = 10,
    20, 30 … für alle. Ergebnis: [Pos.-Nummer] je Eintrag von folge."""
    if neu_vergeben:
        return [SCHRITT * (k + 1) for k in range(len(folge))]
    if not aufsteigend(positionen):
        return [positionen[i].get("pos") for i in folge]
    zahlen = iter(sorted(p.get("pos") for p in positionen if _zahl(p.get("pos"))))
    return [next(zahlen) if _zahl(positionen[i].get("pos")) else positionen[i].get("pos") for i in folge]


def _text(v):
    return "" if v is None else str(v)


def ergebnis_umstellen(ergebnis, positionen, folge, pos_neu):
    """Gespeicherten Schnittplan auf die neue Reihenfolge umschreiben (gleiche Stangen und Teile): Zeilenindex,
    Bezug ixN, Positionsnummer der Teile, Belegungstext und nicht eingeplante Teile. Ergebnis: Kopie."""
    if not ergebnis:
        return ergebnis
    neu_ix = {alt: k for k, alt in enumerate(folge)}
    neu_pos = {alt: pos_neu[k] for k, alt in enumerate(folge)}
    erg = copy.deepcopy(ergebnis)

    def ix(i):
        return neu_ix.get(i, i) if isinstance(i, int) else i

    for s in erg.get("stangen") or ():
        tausch = {}
        for t in s.get("teile") or ():
            i = t.get("index")
            if isinstance(i, int) and i in neu_ix:
                if t.get("pos") is not None and _text(t["pos"]) != _text(neu_pos[i]):
                    tausch.setdefault(_text(t["pos"]), set()).add(_text(neu_pos[i]))
                t["index"], t["pos"] = neu_ix[i], neu_pos[i]
                if str(t.get("ref") or "").startswith("ix"):
                    t["ref"] = f"ix{neu_ix[i]}"
        tausch = {a: b.pop() for a, b in tausch.items() if len(b) == 1}
        if tausch and isinstance(s.get("belegung"), str):       # „10×1250 | 20×860“: Nummern auf einmal tauschen
            s["belegung"] = re.sub(r"(^|[|:] )([^\s|×]+)×", lambda m: m.group(1) + tausch.get(m.group(2), m.group(2))
                                   + "×", s["belegung"])
    for f in erg.get("fehler") or ():
        i = f.get("index")
        if isinstance(i, int) and i in neu_ix:
            f["index"], f["pos"] = neu_ix[i], neu_pos[i]
    return erg


def staffel_schluessel(positionen, folge, pos_neu):
    """{alter Schlüssel: neuer} der Staffeln je Position (Schlüssel = Positionsnummer als Text, Positionen eines
    Satzes zählen über den Satznamen und bleiben)."""
    from .staffeln import txt
    out = {}
    for k, i in enumerate(folge):
        p = positionen[i]
        alt, neu = txt(p.get("pos")), txt(pos_neu[k])
        if alt and alt != neu and not txt(p.get("satz")):
            out[alt] = neu
    return out


def anordnung(positionen, folge, neu_vergeben=False):
    """Positionen in der neuen Reihenfolge mit neuen Positionsnummern (Kopien, nr = 1, 2, 3 …) und die Nummern."""
    pos_neu = nummern(positionen, folge, neu_vergeben)
    return [dict(positionen[i], nr=k + 1, pos=pos_neu[k]) for k, i in enumerate(folge)], pos_neu
