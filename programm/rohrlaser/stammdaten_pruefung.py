"""Stammdaten-Prüfung über Zeilen hinweg (QA-005, Patrick 12.11.2026 „Alle Empfehlungen“ zum Bericht
Entwicklungspotenziale). Die Prüfspalte jeder Tabelle prüft eine Zeile; hier geht es um Werte, die erst im
Zusammenhang auffallen. Ändert nichts.

FEHLER (Rechnung unmöglich oder sicher falsch):
  - Stundensatz 0 oder leer (Stundensätze, Maschinen mit Satz „von Hand“)
  - Vorschub groß 0 oder leer in einer Schneiddaten-Zeile
  - Preis 0 oder leer in einer Preiszeile mit Bezug
  - Wandstufe doppelt (gleiche Maschine, Werkstoff/Kategorie, Gas und Wand bis)
WARNUNG (auffällig, kann gewollt sein, je Zeile quittierbar):
  - Vorschub steigt mit der Wand (dickere Wand schneller als dünnere, gleiche Maschine/Werkstoff/Gas)
  - Einstechzeit sinkt mit der Wand
  - €/kg mehr als doppelt so hoch wie bei der Nachbarabmessung (gleicher Werkstoff und Profilform)
Ohne Qt."""
FEHLER, WARNUNG = "FEHLER", "WARNUNG"
QUITTIERT = "stammdaten_quittiert"          # Einstellung: JSON-Liste der quittierten Schlüssel
FAKTOR_NACHBAR = 2.0


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _m(stufe, tabelle, zeile, regel, text):
    schl = f"{regel}|{tabelle}|{zeile}"
    return dict(stufe=stufe, tabelle=tabelle, zeile=zeile, regel=regel, text=text, schluessel=schl)


def _sd_name(z):
    return (f"{z.get('maschinen_id')} · {z.get('werkstoff_id') or 'Kategorie ' + str(z.get('kategorie') or '?')} · "
            f"{z.get('gas') or ''}").strip(" ·")


def pruefen(daten, quittiert=()):
    """Meldungen [dict(stufe, tabelle, zeile, regel, text, schluessel)] zu daten = {Tabelle: [Zeilen]} (profile,
    preise, schneiddaten, stundensaetze, maschinen). Quittierte Warnungen fehlen; FEHLER sind nie quittierbar."""
    out = []
    for z in daten.get("stundensaetze") or ():
        if not _n(z.get("satz")) or _n(z.get("satz")) <= 0:
            out.append(_m(FEHLER, "Stundensätze", z.get("satz_id"), "satz_null",
                          f"Stundensatz {z.get('satz_id')}: 0 oder leer"))
    for z in daten.get("maschinen") or ():
        if z.get("satz_art") in (None, "", "von Hand") and (not _n(z.get("stundensatz")) or z["stundensatz"] <= 0):
            out.append(_m(FEHLER, "Maschinen", z.get("maschinen_id"), "satz_null",
                          f"Maschine {z.get('maschinen_id')}: Stundensatz 0 oder leer"))
    gruppen, gesehen = {}, {}
    for z in daten.get("schneiddaten") or ():
        name = f"{_sd_name(z)} · Wand bis {z.get('wand_bis')}"
        if not _n(z.get("vorschub_gross")) or z["vorschub_gross"] <= 0:
            out.append(_m(FEHLER, "Schneiddaten", name, "vorschub_null", f"{name}: Vorschub groß 0 oder leer"))
        schl = (z.get("maschinen_id"), z.get("werkstoff_id") or "", z.get("kategorie") or "", z.get("gas") or "")
        w = _n(z.get("wand_bis"))
        if (schl, w) in gesehen:
            out.append(_m(FEHLER, "Schneiddaten", name, "wand_doppelt", f"{name}: Wandstufe doppelt"))
        gesehen[(schl, w)] = True
        if w is not None:
            gruppen.setdefault(schl, []).append(z)
    for schl, zeilen in gruppen.items():
        zeilen = sorted(zeilen, key=lambda z: z["wand_bis"])
        for a, b in zip(zeilen, zeilen[1:]):
            name = f"{_sd_name(b)} · Wand bis {b['wand_bis']}"
            va, vb = _n(a.get("vorschub_gross")), _n(b.get("vorschub_gross"))
            if va and vb and vb > va:
                out.append(_m(WARNUNG, "Schneiddaten", name, "vorschub_steigt",
                              f"{name}: Vorschub groß {vb:g} höher als bei Wand bis {a['wand_bis']} ({va:g})"))
            ea, eb = _n(a.get("einstechzeit")), _n(b.get("einstechzeit"))
            if ea is not None and eb is not None and eb < ea:
                out.append(_m(WARNUNG, "Schneiddaten", name, "einstich_sinkt",
                              f"{name}: Einstechzeit {eb:g} s kürzer als bei Wand bis {a['wand_bis']} ({ea:g} s)"))
    profile = {p.get("profil_id"): p for p in daten.get("profile") or ()}
    kg = {}
    for z in daten.get("preise") or ():
        name = f"{z.get('profil_id')} / {z.get('werkstoff_id')}"
        if z.get("basis") and (not _n(z.get("preis")) or z["preis"] <= 0):
            out.append(_m(FEHLER, "Preise", name, "preis_null", f"Preis {name}: 0 oder leer"))
        p = profile.get(z.get("profil_id")) or {}
        if z.get("basis") == "€/kg" and _n(z.get("preis")) and _n(p.get("a")):
            kg.setdefault((z.get("werkstoff_id"), p.get("form")), []).append(
                (_n(p.get("a")) + (_n(p.get("b")) or 0) / 1000 + (_n(p.get("wand")) or 0) / 1e6, z["preis"], name))
    for (_, _), liste in kg.items():
        liste.sort()
        for i, (_, preis, name) in enumerate(liste):
            nachbarn = [liste[j][1] for j in (i - 1, i + 1) if 0 <= j < len(liste)]
            if nachbarn and preis > FAKTOR_NACHBAR * max(nachbarn):
                out.append(_m(WARNUNG, "Preise", name, "kg_nachbar",
                              f"Preis {name}: {preis:g} €/kg mehr als doppelt so hoch wie die Nachbarabmessung "
                              f"({max(nachbarn):g} €/kg)"))
    q = set(quittiert or ())
    return [x for x in out if x["stufe"] == FEHLER or x["schluessel"] not in q]


def quittiert(db):
    try:
        return set(db.einstellung(QUITTIERT) or ())
    except (TypeError, ValueError):
        return set()


def quittieren(db, schluessel):
    """Warnung quittieren (bewusster Sonderwert); FEHLER lassen sich nicht quittieren."""
    q = quittiert(db) | {schluessel}
    db.einstellung_setzen(QUITTIERT, sorted(q))


def pruefen_db(db):
    """Meldungen zu den Stammdaten der Datenbank (ohne quittierte Warnungen)."""
    daten = {t: db.zeilen(t) for t in ("profile", "preise", "schneiddaten", "stundensaetze", "maschinen")}
    return pruefen(daten, quittiert(db))
