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
from bisect import bisect_left, bisect_right
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
    rueckblick: dict = None     # Ist gegen Soll des alten Auftrags (nachkalkulation.rueckblick, Vorschlag K4)


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


# Felder der NEUEN Position, von denen auswerten() abhängt (Stückzahl, Pos.-Nr. und Bezeichnung nicht)
SUCH_FELDER = ("id", "artikel", "profil_id", "werkstoff_id", "laenge", "schneidweg", "klein_n", "mittel_n",
               "gross_n") + tuple(f for f, _ in UEBERNEHMBAR)


def kennung(db, angebot_id, kundennr, positionen):
    """Schlüssel für den Zwischenspeicher der Suche eines Angebots: ändert sich nur, wenn sich andere Angebote (oder
    die Datei von außen) oder die suchrelevanten Werte dieses Angebots ändern (Prüfung „Programm langsam“
    04.11.2026: vorher rechnete jede Änderung, auch eine Stückzahl, die Suche neu)."""
    st = db.angebote_stand(angebot_id) if hasattr(db, "angebote_stand") else stand(db)
    return (st, kundennr, tuple(tuple(p.get(f) for f in SUCH_FELDER) for p in positionen
                                if _txt(p.get("artikel")) or _txt(p.get("profil_id"))))


def stand(db):
    """Änderungsstand der Datendatei für den Zwischenspeicher: steigt bei jedem Schreiben über diese Verbindung (auch
    beim Abgleich der Kollegen-Angebote) und bei Schreiben anderer Verbindungen. Ein Zeitstempel reicht nicht, weil
    abgeglichene Angebote ihr eigenes, oft älteres Änderungsdatum mitbringen."""
    return db.con.total_changes, db.con.execute("PRAGMA data_version").fetchone()[0]


def suchen(db, angebot_id, kundennr, positionen):
    """{Positions-ID: [Treffer, bester zuerst]} für die Positionen eines Angebots; nur Positionen mit Treffern."""
    return auswerten(laden(db, angebot_id, positionen), kundennr, positionen)


def laden(db, angebot_id, positionen):
    """Mögliche Treffer aus der Datendatei (schnell, über Indizes): Positionen anderer Angebote mit gleicher
    Artikelnummer oder mit gleicher Abmessung und Länge ± LAENGE_TOL. Ergebnis: Zeilen für auswerten().
    Die Datenbank filtert nur grob vor, entschieden wird in einstufen() (Prüfung Datenbank bei vielen Angeboten)."""
    kandidaten = [p for p in positionen if _txt(p.get("artikel")) or _txt(p.get("profil_id"))]
    if not kandidaten:
        return []
    artikel = sorted({_txt(p.get("artikel")).casefold() for p in kandidaten if _txt(p.get("artikel"))})
    bedingung, werte = [], []
    if artikel:
        bedingung.append(f"LOWER(TRIM(p.artikel)) IN ({', '.join('?' * len(artikel))})")
        werte += artikel
    geometrie = sorted({(roh, _zahl(p.get("laenge"))) for p in kandidaten
                        for roh in {p.get("profil_id"), _txt(p.get("profil_id"))}
                        if _txt(p.get("profil_id")) and _zahl(p.get("laenge")) is not None}, key=repr)
    for profil, laenge in geometrie:
        bedingung.append("(p.profil_id = ? AND p.laenge BETWEEN ? AND ?)")
        werte += [profil, laenge - LAENGE_TOL - 1e-9, laenge + LAENGE_TOL + 1e-9]
    if not bedingung:
        return []
    spalten = ", ".join(f'p."{f}"' for f in FELDER)
    sql = (f"SELECT {spalten}, a.nummer AS _nummer, a.kunde AS _kunde, a.kundennr AS _kundennr, a.datum AS _datum, "
           "a.vorgang AS _vorgang, a.fremd AS _fremd, a.staffelpreise AS _sp, a.nachkalkulation IS NOT NULL AS _nk, "
           "a.nachkalkulation AS _nkj "
           f"FROM positionen p JOIN angebote a ON a.id = p.angebot_id WHERE p.angebot_id != ? AND ({' OR '.join(bedingung)})")
    return [dict(r) for r in db.con.execute(sql, [angebot_id] + werte)]


def auswerten(zeilen, kundennr, positionen):
    """Treffer aus den Zeilen von laden() einstufen (ohne Datenbank, darf in einem eigenen Thread laufen)."""
    import json
    from .nachkalkulation import rueckblick
    kandidaten = [p for p in positionen if _txt(p.get("artikel")) or _txt(p.get("profil_id"))]
    staffeln, nachkalk = {}, {}
    aus = {}
    nach_artikel, nach_profil, ohne_zahl = {}, {}, {}   # nur Zeilen vergleichen, die überhaupt passen können
    for i, z in enumerate(zeilen):
        nach_artikel.setdefault(_txt(z.get("artikel")).casefold(), []).append(i)
        la = _zahl(z.get("laenge"))
        if la is None:              # ohne Länge nie gleiche Geometrie
            continue
        if la == la:
            nach_profil.setdefault(_txt(z.get("profil_id")), []).append((la, i))
        else:                       # nan (alte Daten): Vergleich wie früher immer in einstufen
            ohne_zahl.setdefault(_txt(z.get("profil_id")), []).append(i)
    for liste in nach_profil.values():
        liste.sort()
    laengen = {k: [la for la, _ in v] for k, v in nach_profil.items()}
    for p in kandidaten:
        liste = []
        art_p, profil_p = _txt(p.get("artikel")).casefold(), _txt(p.get("profil_id"))
        moegliche = set(nach_artikel.get(art_p, ()) if art_p else ())
        lp = _zahl(p.get("laenge"))
        if profil_p and lp is not None:
            moegliche.update(ohne_zahl.get(profil_p, ()))
        if profil_p and lp is not None and lp != lp:        # nan (alte Daten): wie früher alle mit dem Profil
            moegliche.update(i for _, i in nach_profil.get(profil_p, ()))
        elif profil_p and lp is not None and profil_p in nach_profil:
            # nur Zeilen mit Länge ± LAENGE_TOL (etwas weiter, entschieden wird genau in einstufen)
            ls = laengen[profil_p]
            von, bis = bisect_left(ls, lp - LAENGE_TOL - 1e-6), bisect_right(ls, lp + LAENGE_TOL + 1e-6)
            moegliche.update(i for _, i in nach_profil[profil_p][von:bis])
        for z in (zeilen[i] for i in sorted(moegliche)):
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
            if z["angebot_id"] not in nachkalk:
                try:
                    nachkalk[z["angebot_id"]] = json.loads(z["_nkj"]) if z.get("_nkj") else None
                except ValueError:
                    nachkalk[z["angebot_id"]] = None
            liste.append(Treffer(art, alt, angebot, preis_aus_staffeln(staffeln[z["angebot_id"]], z["pos"], z["stueck"]),
                                 bool(z["_nk"]), unterschiede(p, alt),
                                 rueckblick(nachkalk[z["angebot_id"]], z["id"])))
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
        from .nachkalkulation import rueckblick_text
        s += " · nachkalkuliert" + (f" ({rueckblick_text(t.rueckblick)})" if t.rueckblick else "")
    if t.art != SICHER:
        s += f" ({t.art}: " + ("anderer Kunde" if t.art == PRUEFEN else "gleiche Geometrie") + ")"
    return s


def check_punkte(treffer, positionen):
    """Hinweise für den Angebots-Check (Vorschlag K4): bester sicherer bzw. zu prüfender Treffer mit Nachkalkulation,
    deren Laserzeit um mehr als RUECKBLICK_GRENZE vom Soll abwich. [(Art, Text, Zeile)]."""
    from .nachkalkulation import RUECKBLICK_GRENZE, rueckblick_text
    out = []
    for i, p in enumerate(positionen):
        t = next((t for t in (treffer or {}).get(p.get("id")) or () if t.rueckblick and t.art != AEHNLICH), None)
        if t is None:
            continue
        r = t.rueckblick
        if r["laser_abw"] is not None and abs(r["laser_abw"]) > RUECKBLICK_GRENZE or \
                r["db_h_ist"] is not None and r["db_h_soll"] and r["db_h_ist"] < r["db_h_soll"] * (1 - RUECKBLICK_GRENZE):
            out.append(("HINWEIS", f"Pos. {p.get('pos')}: Wiederholteil aus {t.angebot['nummer']}, "
                                   f"{rueckblick_text(r)} – Zeit bzw. Preis prüfen", i))
    return out
