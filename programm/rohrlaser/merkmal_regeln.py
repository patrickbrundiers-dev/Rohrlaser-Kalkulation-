"""Alle Merkmal-Regeln auf einen Blick (Roadmap Kalkulation Phase 2, GEO-009; Freigabe Patrick 13.11.2026 „Ganze
Phase 2 nach Empfehlung“).

Was ein Merkmal eines Teils auslöst, steht an mehreren Stellen: Arbeitsgang-Regeln (Merkmal und Bedingungen ->
Zusatzarbeit), Erkennungswörter der Zusatzarbeiten (Wort in Bezeichnung, Artikelnummer oder STEP-Name), die
Geometrie-Erkennung (Sechskantloch -> Einnietmutter, Senkung -> Senken), die Prüfregeln der Fertigung und die eigenen
Angebotsregeln (Hinweis, Rückfrage, Zuschlag). Diese Übersicht liest alle mit und ersetzt keine: geändert wird jede
Regel weiter an ihrer Stelle (Doppelklick springt hin). Dazu probe(): welche Regeln bei einer Position greifen.

Neu in den Arbeitsgang-Regeln (Schema 86): Bohrung Ø von/bis (nur Bohrungen in diesem Bereich, „Anzahl Bohrungen“
zählt nur diese) und Wand von/bis. Ohne Qt."""
from . import zusatz_regeln as zr

QUELLE_ARBEITSGANG, QUELLE_WORT, QUELLE_GEOMETRIE, QUELLE_PRUEF, QUELLE_ANGEBOT = (
    "Arbeitsgang-Regel", "Erkennungswort", "Geometrie-Erkennung", "Prüfregel", "Angebotsregel")
QUELLEN = (QUELLE_ARBEITSGANG, QUELLE_WORT, QUELLE_GEOMETRIE, QUELLE_PRUEF, QUELLE_ANGEBOT)
TABELLE = {QUELLE_ARBEITSGANG: "arbeitsgang_regeln", QUELLE_WORT: "zusatzarbeiten",
           QUELLE_GEOMETRIE: "zusatzarbeiten", QUELLE_PRUEF: "pruefregeln", QUELLE_ANGEBOT: "angebotsregeln"}
SPALTEN = ("Quelle", "Regel", "Wenn (Merkmal und Bedingungen)", "Dann", "Wie", "Aktiv")


def _leer(w):
    return w in (None, "")


def _z(w):
    from .stammdaten import zahl_als_text
    return zahl_als_text(w, 2).rstrip("0").rstrip(",") if isinstance(w, (int, float)) else str(w)


def _bereich(titel, von, bis, einheit=" mm"):
    if _leer(von) and _leer(bis):
        return None
    if _leer(bis):
        return f"{titel} ab {_z(von)}{einheit}"
    if _leer(von):
        return f"{titel} bis {_z(bis)}{einheit}"
    return f"{titel} {_z(von)}–{_z(bis)}{einheit}"


def bedingung_arbeitsgang(r):
    """Lesbare Bedingung einer Arbeitsgang-Regel: „Bohrungen, Ø 8,4–8,6 mm, Edelstahl“."""
    teile = [] if r.get("merkmal") in (None, "", "immer") else [str(r["merkmal"])]
    teile += [x for x in (_bereich("Bohrung Ø", r.get("bohr_von"), r.get("bohr_bis")),
                          _bereich("Wand", r.get("wand_von"), r.get("wand_bis")),
                          _bereich("Abmessung", r.get("a_von"), r.get("a_bis"))) if x]
    for n, titel in (("profilform", "Profilform"), ("kategorie", ""), ("werkstoff_id", "Werkstoff"),
                     ("oberflaeche", "Oberfläche"), ("kundennr", "Kunde")):
        if not _leer(r.get(n)):
            teile.append(f"{titel} {r[n]}".strip())
    if not _leer(r.get("stichwort")):
        teile.append(f"Wort „{r['stichwort']}“")
    if r.get("min_stueck"):
        teile.append(f"ab {_z(r['min_stueck'])} Stück")
    return ", ".join(teile) or "immer"


def bedingung_angebot(r):
    teile = [x for x in (_bereich("Wand", r.get("wand_von"), r.get("wand_bis")),
                         _bereich("Länge", r.get("laenge_von"), r.get("laenge_bis")),
                         _bereich("Stückzahl", r.get("stueck_von"), r.get("stueck_bis"), "")) if x]
    for n, titel in (("merkmal", ""), ("kategorie", ""), ("werkstoff_id", "Werkstoff"), ("profilform", "Profilform"),
                     ("zusatzarbeit", "mit Zusatzarbeit"), ("kundennr", "Kunde")):
        if not _leer(r.get(n)) and r.get(n) != "immer":
            teile.append(f"{titel} {r[n]}".strip())
    if r.get("konturen_ab"):
        teile.append(f"ab {_z(r['konturen_ab'])} Innenkonturen")
    return ", ".join(teile) or "immer"


def liste(tabellen):
    """Alle Regeln: [dict(quelle, regel, wenn, dann, wie, aktiv, tabelle, schluessel)]."""
    from . import dfm
    t = tabellen or {}
    out = []
    for r in t.get("arbeitsgang_regeln") or ():
        menge = r.get("menge_art") if r.get("menge_art") not in (None, "", "automatisch") else ""
        out.append(dict(quelle=QUELLE_ARBEITSGANG, regel=r.get("name") or "", wenn=bedingung_arbeitsgang(r),
                        dann=f"Zusatzarbeit {r.get('zusatzarbeit') or '?'}" + (f" ({menge})" if menge else ""),
                        wie=zr.zuordnung(r), aktiv=zr.aktiv(r), tabelle=TABELLE[QUELLE_ARBEITSGANG],
                        schluessel=r.get("name")))
    for z in t.get("zusatzarbeiten") or ():
        worte = [w.strip() for w in str(z.get("erkennung") or "").split(";") if w.strip()]
        if worte:
            out.append(dict(quelle=QUELLE_WORT, regel=z.get("name") or "",
                            wenn="Wort in Bezeichnung, Artikelnummer oder STEP-Name: " + ", ".join(worte),
                            dann=f"Zusatzarbeit {z.get('name')}", wie="Vorschlag (gelb, erst nach ✓ gerechnet)",
                            aktiv=z.get("aktiv") != "nein", tabelle=TABELLE[QUELLE_WORT], schluessel=z.get("name")))
    niet = _niet(t.get("zusatzarbeiten"))
    senken = next((z.get("name") for z in t.get("zusatzarbeiten") or ()
                   if str(z.get("name") or "").strip().lower() == "senken" and z.get("aktiv") != "nein"), None)
    for wenn, ziel in (("Sechskantloch im Teil (STEP bzw. Editor)", niet), ("Senkung im Bohrbild", senken)):
        out.append(dict(quelle=QUELLE_GEOMETRIE, regel=wenn.split(" ")[0], wenn=wenn,
                        dann=f"Zusatzarbeit {ziel}" if ziel else "– (keine passende Zusatzarbeit angelegt)",
                        wie="Vorschlag (gelb, erst nach ✓ gerechnet)", aktiv=bool(ziel),
                        tabelle=TABELLE[QUELLE_GEOMETRIE], schluessel=ziel))
    da = {r.get("regel"): r for r in t.get("pruefregeln") or ()}
    for name, (grenze, stufe, text) in dfm.REGELN.items():
        r = da.get(name) or {}
        g = r.get("grenzwert") if not _leer(r.get("grenzwert")) else grenze
        out.append(dict(quelle=QUELLE_PRUEF, regel=name, wenn=text + (f" (Grenzwert {_z(g)})" if g is not None else ""),
                        dann=f"{r.get('stufe') or stufe} im Status der Position", wie="automatisch",
                        aktiv=r.get("aktiv") != "nein", tabelle=TABELLE[QUELLE_PRUEF], schluessel=name))
    from . import angebotsregeln as ar
    for r in t.get("angebotsregeln") or ():
        w = ar.wirkung(r)
        out.append(dict(quelle=QUELLE_ANGEBOT, regel=r.get("name") or "", wenn=bedingung_angebot(r),
                        dann=w + (f" {_z(r.get('zuschlag'))} %" if w == ar.ZUSCHLAG and r.get("zuschlag") else "")
                        + (f": {r['text']}" if r.get("text") else ""), wie="Angebots-Check",
                        aktiv=r.get("aktiv") != "nein", tabelle=TABELLE[QUELLE_ANGEBOT], schluessel=r.get("name")))
    return out


def _niet(katalog):
    from .zusatz_erkennung import _niet_name
    return _niet_name(katalog)


def probe(p, kopf, k, tabellen):
    """Welche Arbeitsgang- und Angebotsregeln bei der Position greifen: [dict(quelle, regel, dann)]."""
    from . import angebotsregeln as ar
    t = tabellen or {}
    gewinde = t.get("gewinde") or ()
    out = [dict(quelle=QUELLE_ARBEITSGANG, regel=r.get("name"), dann=f"Zusatzarbeit {r.get('zusatzarbeit')}")
           for r in t.get("arbeitsgang_regeln") or () if zr.trifft(r, p, kopf, k, gewinde)]
    for r in t.get("angebotsregeln") or ():
        try:
            treffer = ar.trifft(r, p, kopf, k, gewinde)
        except (AttributeError, TypeError):
            treffer = False
        if treffer:
            out.append(dict(quelle=QUELLE_ANGEBOT, regel=r.get("name"), dann=ar.wirkung(r)))
    return out


def zaehlen(regeln):
    """{Quelle: (aktiv, gesamt)}."""
    out = {q: [0, 0] for q in QUELLEN}
    for r in regeln:
        out[r["quelle"]][1] += 1
        out[r["quelle"]][0] += bool(r["aktiv"])
    return {q: tuple(v) for q, v in out.items()}
