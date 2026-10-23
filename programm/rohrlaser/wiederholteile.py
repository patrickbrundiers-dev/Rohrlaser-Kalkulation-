"""Angebotsgedächtnis (Plan „Intelligenteres Programm“ A1): Wiederholteile in allen Angeboten erkennen, auch in denen
der Kollegen (über teilen.py als fremde Angebote in der Datendatei).

Ein Treffer ist eine Position eines anderen Angebots:
1. „sicher“: gleiche Artikelnummer beim selben Kunden
2. „prüfen“: gleiche Artikelnummer bei einem anderen Kunden
3. „ähnlich“: gleiche Geometrie (ohne passende Artikelnummer): Profil, Werkstoff, Länge ± LAENGE_TOL mm, Schneidweg
   ± SCHNEIDWEG_TOL (anteilig, nur wenn beide einen haben) und gleiche Konturanzahl

Der Preis wird nie übernommen, er entsteht immer neu aus der Kalkulation. Angezeigt wird der Preis je Einheit aus den
gespeicherten Staffelpreisen des alten Angebots (bei der Menge, die der Stückzahl dort am nächsten kommt). Übernehmen
lassen sich nur Eingaben, die man sonst von Hand wiederholt (UEBERNEHMBAR), jede einzeln an- oder abwählbar.
"""
from dataclasses import dataclass, field

LAENGE_TOL = 0.5            # mm
SCHNEIDWEG_TOL = 0.01       # 1 %
SICHER, PRUEFEN, AEHNLICH = "sicher", "prüfen", "ähnlich"
RANG = {SICHER: 0, PRUEFEN: 1, AEHNLICH: 2}
# (Feld, Titel) der Werte, die „Werte übernehmen“ anbietet; Naht mit Winkel zusammen
UEBERNEHMBAR = (("zeit_manuell", "Schneidzeit je Teil von Hand [s]"), ("prog_zeit", "Programmierzeit [min]"),
                ("einstiche", "Einstiche je Teil"), ("zusatz", "Zusatzarbeiten"), ("gewinde", "Gewinde geprüft"),
                ("naht_vorgabe", "Schweißnaht"), ("naht_winkel", "Nahtwinkel [°]"))
FELDER = ("id", "angebot_id", "pos", "art", "artikel", "bezeichnung", "profil_id", "werkstoff_id", "laenge", "stueck",
          "schneidweg", "klein_n", "mittel_n", "gross_n") + tuple(f for f, _ in UEBERNEHMBAR)


@dataclass
class Treffer:
    art: str                    # SICHER, PRUEFEN, AEHNLICH
    position: dict              # die alte Position
    angebot: dict               # id, nummer, kunde, kundennr, datum, vorgang, fremd
    preis: tuple = None         # (Menge, Preis je Einheit) aus den Staffelpreisen, sonst None
    nachkalkuliert: bool = False
    werte: dict = field(default_factory=dict)       # übernehmbare Werte, die sich von der neuen Position unterscheiden


def _txt(w):
    return str(w).strip() if w is not None else ""


def _zahl(w):
    return w if isinstance(w, (int, float)) and not isinstance(w, bool) else None


def konturen(p):
    return sum(int(_zahl(p.get(n)) or 0) for n in ("klein_n", "mittel_n", "gross_n"))


def gleiche_geometrie(a, b):
    """Profil, Werkstoff, Länge ± LAENGE_TOL, Schneidweg ± SCHNEIDWEG_TOL (wenn beide einen haben), Konturanzahl."""
    if not _txt(a.get("profil_id")) or _txt(a.get("profil_id")) != _txt(b.get("profil_id")):
        return False
    if _txt(a.get("werkstoff_id")) != _txt(b.get("werkstoff_id")):
        return False
    la, lb = _zahl(a.get("laenge")), _zahl(b.get("laenge"))
    if la is None or lb is None or abs(la - lb) > LAENGE_TOL:
        return False
    sa, sb = _zahl(a.get("schneidweg")), _zahl(b.get("schneidweg"))
    if sa and sb and abs(sa - sb) > SCHNEIDWEG_TOL * max(sa, sb):
        return False
    return konturen(a) == konturen(b)


def einstufen(neu, alt, kundennr, alt_kundennr):
    """Art des Treffers oder None."""
    art_neu, art_alt = _txt(neu.get("artikel")).casefold(), _txt(alt.get("artikel")).casefold()
    if art_neu and art_neu == art_alt:
        return SICHER if _txt(kundennr) and _txt(kundennr) == _txt(alt_kundennr) else PRUEFEN
    if gleiche_geometrie(neu, alt):
        return AEHNLICH
    return None


def preis_aus_staffeln(staffelpreise, pos, stueck):
    """(Menge, Preis je Einheit) der Position pos aus gespeicherten Staffelpreisen, Menge am nächsten an stueck."""
    zeilen = [z for z in (staffelpreise or {}).get("zeilen") or ()
              if _txt(z.get("schluessel")) == _txt(pos) and z.get("einheit") != "Satz"
              and _zahl(z.get("preis_einheit")) is not None and _zahl(z.get("menge"))]
    if not zeilen:
        return None
    ziel = _zahl(stueck) or 0
    z = min(zeilen, key=lambda z: (abs(z["menge"] - ziel), z["menge"]))
    return z["menge"], z["preis_einheit"]


def unterschiede(neu, alt):
    """Übernehmbare Werte der alten Position, die gesetzt sind und sich von der neuen unterscheiden."""
    return {f: alt[f] for f, _ in UEBERNEHMBAR if alt.get(f) not in (None, "") and alt.get(f) != neu.get(f)}


def stand(db):
    """Änderungsstand der Datendatei für den Zwischenspeicher: steigt bei jedem Schreiben über diese Verbindung (auch
    beim Abgleich der Kollegen-Angebote) und bei Schreiben anderer Verbindungen. Ein Zeitstempel reicht nicht, weil
    abgeglichene Angebote ihr eigenes, oft älteres Änderungsdatum mitbringen."""
    return db.con.total_changes, db.con.execute("PRAGMA data_version").fetchone()[0]


def suchen(db, angebot_id, kundennr, positionen):
    """{Positions-ID: [Treffer, bester zuerst]} für die Positionen eines Angebots; nur Positionen mit Treffern."""
    import json
    kandidaten = [p for p in positionen if _txt(p.get("artikel")) or _txt(p.get("profil_id"))]
    if not kandidaten:
        return {}
    artikel = sorted({_txt(p.get("artikel")).casefold() for p in kandidaten if _txt(p.get("artikel"))})
    profile = sorted({_txt(p.get("profil_id")) for p in kandidaten if _txt(p.get("profil_id"))})
    bedingung, werte = [], []
    if artikel:
        bedingung.append(f"LOWER(TRIM(p.artikel)) IN ({', '.join('?' * len(artikel))})")
        werte += artikel
    if profile:
        bedingung.append(f"p.profil_id IN ({', '.join('?' * len(profile))})")
        werte += profile
    spalten = ", ".join(f'p."{f}"' for f in FELDER)
    sql = (f"SELECT {spalten}, a.nummer AS _nummer, a.kunde AS _kunde, a.kundennr AS _kundennr, a.datum AS _datum, "
           "a.vorgang AS _vorgang, a.fremd AS _fremd, a.staffelpreise AS _sp, a.nachkalkulation IS NOT NULL AS _nk "
           f"FROM positionen p JOIN angebote a ON a.id = p.angebot_id WHERE p.angebot_id != ? AND ({' OR '.join(bedingung)})")
    zeilen = [dict(r) for r in db.con.execute(sql, [angebot_id] + werte)]
    staffeln = {}
    aus = {}
    for p in kandidaten:
        liste = []
        for z in zeilen:
            art = einstufen(p, z, kundennr, z["_kundennr"])
            if art is None:
                continue
            if z["angebot_id"] not in staffeln:
                try:
                    staffeln[z["angebot_id"]] = json.loads(z["_sp"]) if z["_sp"] else None
                except ValueError:
                    staffeln[z["angebot_id"]] = None
            angebot = dict(id=z["angebot_id"], nummer=z["_nummer"], kunde=z["_kunde"], kundennr=z["_kundennr"],
                           datum=z["_datum"], vorgang=z["_vorgang"] or "Entwurf", fremd=bool(z["_fremd"]))
            alt = {f: z[f] for f in FELDER}
            liste.append(Treffer(art, alt, angebot, preis_aus_staffeln(staffeln[z["angebot_id"]], z["pos"], z["stueck"]),
                                 bool(z["_nk"]), unterschiede(p, alt)))
        if liste:
            # bester zuerst: Art, beauftragt vor anderen, darin das neueste Datum
            liste.sort(key=lambda t: str(t.angebot["datum"] or ""), reverse=True)
            liste.sort(key=lambda t: (RANG[t.art], t.angebot["vorgang"] != "Beauftragt"))
            aus[p["id"]] = liste
    return aus


def text(treffer_liste):
    """Eine Zeile zum besten Treffer: „3× angeboten · zuletzt 12.09.2026 (A-2026-0142): 4,85 €/Stk bei 50 Stk –
    beauftragt“ (Art in Klammern, wenn nicht sicher)."""
    from .stammdaten import zahl_als_text
    t = treffer_liste[0]
    d = _txt(t.angebot["datum"])
    datum = f"{d[8:10]}.{d[5:7]}.{d[:4]}" if len(d) >= 10 else d
    s = f"{len(treffer_liste)}× angeboten · zuletzt {datum} ({t.angebot['nummer']})"
    if t.preis:
        s += f": {zahl_als_text(t.preis[1], 2)} €/Stk bei {zahl_als_text(t.preis[0], 0)} Stk"
    s += f" – {t.angebot['vorgang'].lower()}"
    if t.nachkalkuliert:
        s += " · nachkalkuliert"
    if t.art != SICHER:
        s += f" ({t.art}: " + ("anderer Kunde" if t.art == PRUEFEN else "gleiche Geometrie") + ")"
    return s
