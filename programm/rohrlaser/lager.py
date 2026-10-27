"""Materialbestand und Reststücke (Wettbewerbsvergleich P0-1, Patrick 27.10.2026: Reststücke optional, Vorgabe aus).

Ganz optional: ohne die Einstellung 'lager_aktiv' gibt es keinen Reiter Lager und keine Lager-Einträge im Angebot;
Angebote rechnen wie bisher. Die Angebotskalkulation selbst ändert sich durch das Lager nie (Preise und
festgeschriebene Preisgrundlagen bleiben): das Lager kommt erst beim beauftragten Angebot ins Spiel, wenn das
Material bereitgestellt wird.

Bestand (Tabelle lager_bestand): je Zeile ein Posten mit eindeutiger Kennung (S-00001 ganze Stangen, R-00001
Reststücke), Profil, Werkstoff, Oberfläche, Länge, Anzahl (physischer Bestand), Charge, Lagerort und Herkunft. Ein
Reststück ist immer ein Stück (Anzahl 1). Reststücke gibt es nur mit der Einstellung 'reste_aktiv'.

Je Angebot ein Lagerauftrag (Tabelle lager_auftraege) mit dem Plan und einem Zustand:
  (kein) --reservieren--> reserviert --verbrauchen--> verbraucht
  reserviert --freigeben--> freigegeben (Storno vor dem Verbrauch, Reservierungen aufgehoben)
  verbraucht --verbrauch_stornieren--> reserviert (Wiederherstellung: Bestand zurück, entstandene Reste wieder weg)
Reservierungen (lager_reservierung) zählen gegen den Bestand: verfügbar = Anzahl − aktive Reservierungen. Ein Posten
kann daher nicht doppelt fest zugeordnet werden; reservieren prüft das in einer Transaktion und schreibt alles oder
nichts. Erst verbrauchen bucht den Bestand aus (nach bestätigtem Materialverbrauch), mit 'reste_aktiv' kommen dabei
die Reste der Stangen ab 'rest_min_laenge' als neue Reststücke ins Lager. Jede Buchung steht im Journal
(lager_buchungen).

Plan (planen): Die Optimierung des Angebots bleibt, wie sie ist. Für jede geplante Lieferstange (nicht vom
Lieferanten zugeschnitten, kein Kundenmaterial) ist der Bedarf = Endbeschnitt + Teile + Trennungen + letzter
Schnittverlust + Greiferrest bzw. 3D-Greifmaß (rechnen.stangen_werte 'belegt' + 'greif'). Ein Lagerposten passt, wenn
Profil, Werkstoff und Oberfläche gleich sind und er mindestens so lang ist wie der Bedarf: dann liegen die Teile
genau wie im Schnittplan, der Greiferrest bleibt frei, die Stange ist nie überbelegt. Größter Bedarf zuerst, je das
kürzeste passende Reststück, sonst die kürzeste passende Lagerstange; der Rest wird neu gekauft. Teile werden nicht
neu auf Reststücke verteilt (dafür: Variantenvergleich, varianten.py).

Mehrere Arbeitsplätze: das Lager steht in der eigenen Datendatei und wird nicht abgeglichen (teilen.py); es gehört
an einen Arbeitsplatz (Arbeitsvorbereitung).
"""
import datetime
import json

ARTEN = ("Stange", "Rest")
KENNUNG = {"Stange": "S", "Rest": "R"}
ZUSTAENDE = ("reserviert", "freigegeben", "verbraucht")
EPS = 1e-6

TABELLEN_SQL = (
    "CREATE TABLE IF NOT EXISTS lager_bestand (id INTEGER PRIMARY KEY, kennung TEXT UNIQUE, art TEXT, profil TEXT, "
    "werkstoff TEXT, oberflaeche TEXT, laenge REAL, anzahl INTEGER, charge TEXT, lagerort TEXT, herkunft TEXT, "
    "bemerkung TEXT, angelegt TEXT, geaendert TEXT)",
    "CREATE TABLE IF NOT EXISTS lager_reservierung (id INTEGER PRIMARY KEY, bestand_id INTEGER REFERENCES "
    "lager_bestand(id), angebot_id INTEGER, anzahl INTEGER, status TEXT, angelegt TEXT, geaendert TEXT)",
    "CREATE INDEX IF NOT EXISTS lager_reservierung_bestand ON lager_reservierung (bestand_id, status)",
    "CREATE TABLE IF NOT EXISTS lager_auftraege (angebot_id INTEGER PRIMARY KEY, nummer TEXT, status TEXT, "
    "plan TEXT, kennung TEXT, geaendert TEXT)",
    "CREATE TABLE IF NOT EXISTS lager_buchungen (id INTEGER PRIMARY KEY, zeit TEXT, art TEXT, bestand_id INTEGER, "
    "kennung TEXT, angebot_id INTEGER, nummer TEXT, anzahl INTEGER, laenge REAL, text TEXT, kuerzel TEXT)",
)
TABELLEN = ("lager_bestand", "lager_reservierung", "lager_auftraege", "lager_buchungen")


class LagerFehler(ValueError):
    """Buchung nicht möglich (Text für den Benutzer)."""


def einrichten(con):
    for sql in TABELLEN_SQL:
        con.execute(sql)


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _ob(oberflaeche):
    """Oberfläche für den Vergleich: leer und 'roh' sind gleich."""
    o = str(oberflaeche or "").strip()
    return "" if o.lower() == "roh" else o


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def aktiv(db):
    return db.einstellung("lager_aktiv") == "ja"


def reste_aktiv(db):
    return db.einstellung("reste_aktiv") == "ja"


def _schreiben(db):
    from .datenbank import Lesemodus
    if db.nur_lesen:
        raise Lesemodus(f"Lesemodus – {db.nur_lesen}. Ändern ist erst mit gültiger Lizenz möglich "
                        "(Hilfe → Lizenz …).")


def _buchen(db, art, bestand=None, angebot_id=None, nummer=None, anzahl=None, laenge=None, text=""):
    db.con.execute("INSERT INTO lager_buchungen (zeit, art, bestand_id, kennung, angebot_id, nummer, anzahl, laenge, "
                   "text, kuerzel) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (_jetzt(), art, (bestand or {}).get("id"), (bestand or {}).get("kennung"), angebot_id, nummer,
                    anzahl, laenge if laenge is not None else (bestand or {}).get("laenge"), text,
                    db.einstellung("benutzer_kuerzel") or ""))


def _zeile(r):
    return dict(r) if r is not None else None


# ------------------------------------------------------------------ Bestand
def bestand(db, mit_leeren=False):
    """Alle Posten mit reserviert (aktive Reservierungen) und verfuegbar; ohne mit_leeren nur Posten mit Bestand."""
    rows = db.con.execute(
        "SELECT b.*, COALESCE((SELECT SUM(r.anzahl) FROM lager_reservierung r WHERE r.bestand_id=b.id "
        "AND r.status='reserviert'), 0) AS reserviert FROM lager_bestand b ORDER BY b.profil, b.werkstoff, "
        "b.art DESC, b.laenge, b.kennung").fetchall()
    out = []
    for r in rows:
        z = dict(r)
        z["verfuegbar"] = (z["anzahl"] or 0) - z["reserviert"]
        if mit_leeren or (z["anzahl"] or 0) > 0:
            out.append(z)
    return out


def posten(db, bestand_id):
    return _zeile(db.con.execute("SELECT * FROM lager_bestand WHERE id=?", (bestand_id,)).fetchone())


def _reserviert(db, bestand_id, ohne_angebot=None):
    sql = "SELECT COALESCE(SUM(anzahl), 0) FROM lager_reservierung WHERE bestand_id=? AND status='reserviert'"
    args = [bestand_id]
    if ohne_angebot is not None:
        sql += " AND angebot_id<>?"
        args.append(ohne_angebot)
    return db.con.execute(sql, args).fetchone()[0]


def _naechste_kennung(db, art):
    p = KENNUNG[art]
    n = 0
    for (k,) in db.con.execute("SELECT kennung FROM lager_bestand WHERE kennung LIKE ?", (p + "-%",)):
        try:
            n = max(n, int(k.split("-", 1)[1]))
        except (ValueError, IndexError):
            pass
    return f"{p}-{n + 1:05d}"


def _pruefen(art, profil, werkstoff, laenge, anzahl):
    if art not in ARTEN:
        raise LagerFehler(f"Art '{art}' gibt es nicht (Stange oder Rest).")
    if not str(profil or "").strip() or not str(werkstoff or "").strip():
        raise LagerFehler("Bitte Profil-ID und Werkstoff-ID angeben.")
    if _n(laenge) is None or laenge <= 0:
        raise LagerFehler("Bitte eine Länge größer 0 mm angeben.")
    if _n(anzahl) is None or anzahl < 1 or int(anzahl) != anzahl:
        raise LagerFehler("Bitte eine ganze Anzahl ab 1 angeben.")


def zugang(db, art, profil, werkstoff, laenge, anzahl=1, oberflaeche="", charge="", lagerort="", herkunft="Zugang",
           bemerkung="", angebot_id=None, nummer=None, _transaktion=True):
    """Neuer Posten. Reststücke: je Stück ein Posten (Anzahl 1), nur mit 'reste_aktiv'. Ergebnis: [IDs]."""
    _schreiben(db)
    _pruefen(art, profil, werkstoff, laenge, anzahl)
    if art == "Rest" and not reste_aktiv(db):
        raise LagerFehler("Reststücke sind ausgeschaltet (Einstellungen → Lager: Reststücke verwalten).")
    stuecke = [1] * int(anzahl) if art == "Rest" else [int(anzahl)]
    ids = []

    def schreiben():
        for n in stuecke:
            jetzt = _jetzt()
            kennung = _naechste_kennung(db, art)
            cur = db.con.execute(
                "INSERT INTO lager_bestand (kennung, art, profil, werkstoff, oberflaeche, laenge, anzahl, charge, "
                "lagerort, herkunft, bemerkung, angelegt, geaendert) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (kennung, art, str(profil).strip(), str(werkstoff).strip(), _ob(oberflaeche), float(laenge), n,
                 charge or "", lagerort or "", herkunft or "", bemerkung or "", jetzt, jetzt))
            ids.append(cur.lastrowid)
            _buchen(db, "Rest-Zugang" if art == "Rest" and angebot_id else "Zugang", posten(db, cur.lastrowid),
                    angebot_id, nummer, n, text=herkunft or "")
    if _transaktion:
        with db.con:
            schreiben()
    else:
        schreiben()
    return ids


def korrigieren(db, bestand_id, anzahl, grund):
    """Bestand nach Inventur setzen (nicht unter die reservierte Menge)."""
    _schreiben(db)
    p = posten(db, bestand_id)
    if p is None:
        raise LagerFehler("Posten nicht gefunden.")
    if not (grund or "").strip():
        raise LagerFehler("Bitte einen Grund angeben.")
    if _n(anzahl) is None or anzahl < 0 or int(anzahl) != anzahl or (p["art"] == "Rest" and anzahl > 1):
        raise LagerFehler("Bitte eine ganze Anzahl ab 0 angeben (Reststück: 0 oder 1).")
    with db.con:
        res = _reserviert(db, bestand_id)
        if anzahl < res:
            raise LagerFehler(f"{p['kennung']}: {res} Stück sind reserviert, der Bestand kann nicht darunter.")
        db.con.execute("UPDATE lager_bestand SET anzahl=?, geaendert=? WHERE id=?", (int(anzahl), _jetzt(), bestand_id))
        _buchen(db, "Korrektur", p, anzahl=int(anzahl) - (p["anzahl"] or 0), text=grund.strip())


def ausbuchen(db, bestand_id, grund):
    """Posten ganz ausbuchen (Schrott, verkauft …): Bestand 0; nicht, solange etwas reserviert ist."""
    korrigieren(db, bestand_id, 0, grund)


def buchungen(db, angebot_id=None, bestand_id=None):
    sql, args = "SELECT * FROM lager_buchungen", []
    if angebot_id is not None:
        sql, args = sql + " WHERE angebot_id=?", [angebot_id]
    elif bestand_id is not None:
        sql, args = sql + " WHERE bestand_id=?", [bestand_id]
    return [dict(r) for r in db.con.execute(sql + " ORDER BY id DESC", args)]


# ------------------------------------------------------------------ Plan
def bedarf(ergebnis, werte):
    """Lieferstangen des Schnittplans, die aus dem Lager kommen können: [dict(nr, profil, werkstoff, oberflaeche,
    stange, belegt, bedarf, rest, kosten)]; werte = rechnen.stangen_werte (gleiche Reihenfolge)."""
    out = []
    for s, w in zip((ergebnis or {}).get("stangen") or (), werte or ()):
        if s.get("beistellung") or s.get("werkstuecke"):
            continue
        belegt = w["belegt"]
        out.append(dict(nr=s["nr"], profil=s["profil"], werkstoff=s["werkstoff"], oberflaeche=_ob(s.get("oberflaeche")),
                        stange=s["stange"], belegt=belegt, bedarf=belegt + (s.get("greif") or 0),
                        rest=s["stange"] - belegt, kosten=w.get("kosten")))
    return out


def planen(db, angebot_id, ergebnis, werte, mit_resten=None):
    """Plan ohne zu buchen: dict(stangen=[Bedarf + quelle 'Rest'|'Lager'|'Neukauf', bestand_id, kennung, laenge
    (Länge des Postens), lagerwert (€, Meterpreis der Stange × Länge × Restwert), ersparnis (€ Neukauf gespart)],
    neukauf=Anzahl, aus_lager=Anzahl, ersparnis=€, kennung=Kennung des Ergebnisses). Eigene aktive Reservierungen
    dieses Angebots zählen als verfügbar (neu planen). mit_resten None = Einstellung."""
    mit_resten = reste_aktiv(db) if mit_resten is None else mit_resten
    restwert = _n(db.einstellung("restwert_anteil"))
    restwert = 1.0 if restwert is None else restwert
    frei = {}
    for z in bestand(db):
        if z["art"] == "Rest" and not mit_resten:
            continue
        n = (z["anzahl"] or 0) - _reserviert(db, z["id"], ohne_angebot=angebot_id)
        if n > 0:
            frei[z["id"]] = dict(z, frei=n)
    stangen = sorted(bedarf(ergebnis, werte), key=lambda b: (-b["bedarf"], b["nr"]))
    for b in stangen:
        passend = [z for z in frei.values() if z["frei"] > 0 and z["profil"] == b["profil"]
                   and z["werkstoff"] == b["werkstoff"] and _ob(z["oberflaeche"]) == b["oberflaeche"]
                   and z["laenge"] + EPS >= b["bedarf"]]
        wahl = min(passend, key=lambda z: (z["art"] != "Rest", z["laenge"], z["kennung"]), default=None)
        if wahl is None:
            b.update(quelle="Neukauf", bestand_id=None, kennung="", laenge=b["stange"], lagerwert=0.0, ersparnis=0.0)
            continue
        wahl["frei"] -= 1
        meter = b["kosten"] / b["stange"] if _n(b["kosten"]) is not None and b["stange"] else None
        b.update(quelle=wahl["art"] if wahl["art"] == "Rest" else "Lager", bestand_id=wahl["id"],
                 kennung=wahl["kennung"], laenge=wahl["laenge"], charge=wahl.get("charge") or "",
                 lagerort=wahl.get("lagerort") or "",
                 lagerwert=meter * wahl["laenge"] * restwert if meter is not None else None,
                 ersparnis=b["kosten"] if _n(b["kosten"]) is not None else None)
    stangen.sort(key=lambda b: b["nr"])
    aus = [b for b in stangen if b["quelle"] != "Neukauf"]
    return dict(stangen=stangen, aus_lager=len(aus), neukauf=len(stangen) - len(aus),
                ersparnis=sum(b["ersparnis"] or 0 for b in aus),
                lagerwert=sum(b["lagerwert"] or 0 for b in aus), kennung=(ergebnis or {}).get("kennung"))


def pruefe_plan(plan):
    """Unabhängige Kontrolle: kein Posten länger belegt als er ist (Bedarf ≤ Länge des Postens) und kein Reststück
    zweimal im Plan. AssertionError sonst."""
    reste = [b["bestand_id"] for b in plan["stangen"] if b["quelle"] == "Rest"]
    if len(reste) != len(set(reste)):
        raise AssertionError("Reststück doppelt eingeplant")
    for b in plan["stangen"]:
        if b["quelle"] != "Neukauf" and b["bedarf"] > b["laenge"] + EPS:
            raise AssertionError(f"Stange {b['nr']}: Bedarf {b['bedarf']} mm > {b['kennung']} {b['laenge']} mm")
        if b["bedarf"] > b["stange"] + EPS:
            raise AssertionError(f"Stange {b['nr']}: überbelegt")


# ------------------------------------------------------------------ Lagerauftrag je Angebot
def auftrag(db, angebot_id):
    """Lagerauftrag eines Angebots (mit plan als dict) oder None."""
    z = _zeile(db.con.execute("SELECT * FROM lager_auftraege WHERE angebot_id=?", (angebot_id,)).fetchone())
    if z:
        z["plan"] = json.loads(z["plan"] or "{}")
    return z


def veraltet(db, angebot_id, ergebnis):
    """True, wenn reserviert wurde, das Angebot aber seitdem anders optimiert ist (Plan passt nicht mehr)."""
    a = auftrag(db, angebot_id)
    return bool(a) and a["status"] == "reserviert" and a.get("kennung") != (ergebnis or {}).get("kennung")


def aus_lager(db, angebot_id, ergebnis=None):
    """Nummern der Stangen, die laut aktivem Lagerauftrag aus dem Lager kommen (für die Materialanfrage); leer, wenn
    nichts reserviert ist oder der Plan nicht mehr zum Ergebnis passt."""
    a = auftrag(db, angebot_id)
    if not a or a["status"] not in ("reserviert", "verbraucht"):
        return set()
    if ergebnis is not None and a.get("kennung") != ergebnis.get("kennung"):
        return set()
    return {b["nr"] for b in a["plan"].get("stangen") or () if b.get("quelle") != "Neukauf"}


def reservieren(db, angebot_id, nummer, plan):
    """Plan fest zuordnen: frühere Reservierungen dieses Angebots werden ersetzt. Alles oder nichts: ist ein Posten
    inzwischen anderweitig reserviert oder zu knapp, LagerFehler und keine Änderung."""
    _schreiben(db)
    pruefe_plan(plan)
    a = auftrag(db, angebot_id)
    if a and a["status"] == "verbraucht":
        raise LagerFehler("Der Materialverbrauch ist schon gebucht. Erst den Verbrauch stornieren.")
    menge = {}
    for b in plan["stangen"]:
        if b["quelle"] != "Neukauf":
            menge[b["bestand_id"]] = menge.get(b["bestand_id"], 0) + 1
    jetzt = _jetzt()
    with db.con:
        db.con.execute("UPDATE lager_reservierung SET status='freigegeben', geaendert=? WHERE angebot_id=? AND "
                       "status='reserviert'", (jetzt, angebot_id))
        for bid, n in sorted(menge.items()):
            p = posten(db, bid)
            if p is None:
                raise LagerFehler("Ein Posten des Plans ist nicht mehr im Lager. Bitte neu planen.")
            frei = (p["anzahl"] or 0) - _reserviert(db, bid)
            if frei < n:
                raise LagerFehler(f"{p['kennung']} ist nicht mehr verfügbar ({frei} frei, {n} gebraucht). "
                                  "Bitte neu planen.")
            db.con.execute("INSERT INTO lager_reservierung (bestand_id, angebot_id, anzahl, status, angelegt, "
                           "geaendert) VALUES (?, ?, ?, 'reserviert', ?, ?)", (bid, angebot_id, n, jetzt, jetzt))
            _buchen(db, "Reservierung", p, angebot_id, nummer, n)
        db.con.execute("INSERT OR REPLACE INTO lager_auftraege (angebot_id, nummer, status, plan, kennung, geaendert) "
                       "VALUES (?, ?, 'reserviert', ?, ?, ?)",
                       (angebot_id, nummer, json.dumps(plan, ensure_ascii=False), plan.get("kennung"), jetzt))


def freigeben(db, angebot_id, grund=""):
    """Reservierungen aufheben (Storno vor dem Verbrauch, Auftrag abgesagt oder neu planen)."""
    _schreiben(db)
    a = auftrag(db, angebot_id)
    if not a or a["status"] != "reserviert":
        raise LagerFehler("Für dieses Angebot ist nichts reserviert.")
    jetzt = _jetzt()
    with db.con:
        for r in db.con.execute("SELECT * FROM lager_reservierung WHERE angebot_id=? AND status='reserviert'",
                                (angebot_id,)).fetchall():
            _buchen(db, "Freigabe", posten(db, r["bestand_id"]), angebot_id, a["nummer"], r["anzahl"], text=grund)
        db.con.execute("UPDATE lager_reservierung SET status='freigegeben', geaendert=? WHERE angebot_id=? AND "
                       "status='reserviert'", (jetzt, angebot_id))
        db.con.execute("UPDATE lager_auftraege SET status='freigegeben', geaendert=? WHERE angebot_id=?",
                       (jetzt, angebot_id))


def verbrauchen(db, angebot_id):
    """Bestätigten Materialverbrauch buchen: reservierte Posten ausbuchen; mit 'reste_aktiv' die Reste ab
    'rest_min_laenge' als neue Reststücke (Charge des Postens, bei Neukauf leer). Nur einmal je Lagerauftrag.
    Ergebnis: Kennungen der neuen Reststücke."""
    _schreiben(db)
    a = auftrag(db, angebot_id)
    if not a or a["status"] != "reserviert":
        raise LagerFehler("Verbrauch nur für reservierte Lageraufträge (zuerst „Reservieren“)."
                          if not a or a["status"] != "verbraucht" else "Der Verbrauch ist schon gebucht.")
    min_rest = _n(db.einstellung("rest_min_laenge")) or 0
    neue = []
    jetzt = _jetzt()
    with db.con:
        for r in db.con.execute("SELECT * FROM lager_reservierung WHERE angebot_id=? AND status='reserviert'",
                                (angebot_id,)).fetchall():
            p = posten(db, r["bestand_id"])
            if (p["anzahl"] or 0) < r["anzahl"]:
                raise LagerFehler(f"{p['kennung']}: Bestand {p['anzahl']} kleiner als reserviert {r['anzahl']}.")
            db.con.execute("UPDATE lager_bestand SET anzahl=anzahl-?, geaendert=? WHERE id=?",
                           (r["anzahl"], jetzt, p["id"]))
            db.con.execute("UPDATE lager_reservierung SET status='verbraucht', geaendert=? WHERE id=?", (jetzt, r["id"]))
            _buchen(db, "Verbrauch", p, angebot_id, a["nummer"], r["anzahl"])
        if reste_aktiv(db):
            for b in a["plan"].get("stangen") or ():
                rest = b["laenge"] - b["belegt"]
                if rest + EPS < max(min_rest, EPS):
                    continue
                neue += zugang(db, "Rest", b["profil"], b["werkstoff"], round(rest, 1), 1, b["oberflaeche"],
                               charge=b.get("charge") or "", herkunft=f"Rest aus {a['nummer']} Stange {b['nr']}"
                               + (f" ({b['kennung']})" if b.get("kennung") else ""), angebot_id=angebot_id,
                               nummer=a["nummer"], _transaktion=False)
        plan = dict(a["plan"], neue_reste=neue)
        db.con.execute("UPDATE lager_auftraege SET status='verbraucht', plan=?, geaendert=? WHERE angebot_id=?",
                       (json.dumps(plan, ensure_ascii=False), jetzt, angebot_id))
    return [posten(db, i)["kennung"] for i in neue]


def verbrauch_stornieren(db, angebot_id, grund):
    """Gebuchten Verbrauch zurücknehmen (Wiederherstellung): Bestand zurück, Reservierungen wieder aktiv, die dabei
    entstandenen Reststücke wieder entfernt. Nicht möglich, wenn eines davon inzwischen reserviert oder verbraucht
    ist."""
    _schreiben(db)
    a = auftrag(db, angebot_id)
    if not a or a["status"] != "verbraucht":
        raise LagerFehler("Für dieses Angebot ist kein Verbrauch gebucht.")
    if not (grund or "").strip():
        raise LagerFehler("Bitte einen Grund angeben.")
    jetzt = _jetzt()
    with db.con:
        for rid in a["plan"].get("neue_reste") or ():
            p = posten(db, rid)
            if p is None or (p["anzahl"] or 0) != 1 or _reserviert(db, rid) or db.con.execute(
                    "SELECT 1 FROM lager_reservierung WHERE bestand_id=? AND status='verbraucht'", (rid,)).fetchone():
                raise LagerFehler(f"Reststück {p['kennung'] if p else rid} ist schon weiter verwendet; Storno nicht "
                                  "möglich (Bestand von Hand korrigieren).")
            db.con.execute("UPDATE lager_bestand SET anzahl=0, geaendert=? WHERE id=?", (jetzt, rid))
            _buchen(db, "Storno Rest-Zugang", p, angebot_id, a["nummer"], -1, text=grund.strip())
        for r in db.con.execute("SELECT * FROM lager_reservierung WHERE angebot_id=? AND status='verbraucht'",
                                (angebot_id,)).fetchall():
            p = posten(db, r["bestand_id"])
            db.con.execute("UPDATE lager_bestand SET anzahl=anzahl+?, geaendert=? WHERE id=?", (r["anzahl"], jetzt, p["id"]))
            db.con.execute("UPDATE lager_reservierung SET status='reserviert', geaendert=? WHERE id=?", (jetzt, r["id"]))
            _buchen(db, "Storno Verbrauch", p, angebot_id, a["nummer"], r["anzahl"], text=grund.strip())
        plan = dict(a["plan"], neue_reste=[])
        db.con.execute("UPDATE lager_auftraege SET status='reserviert', plan=?, geaendert=? WHERE angebot_id=?",
                       (json.dumps(plan, ensure_ascii=False), jetzt, angebot_id))


def angebot_geloescht(db, angebot_id):
    """Angebot gelöscht: aktive Reservierungen freigeben (gebuchter Verbrauch bleibt im Journal)."""
    a = auftrag(db, angebot_id)
    if a and a["status"] == "reserviert":
        freigeben(db, angebot_id, "Angebot gelöscht")


def verbrauch_je_charge(db):
    """Rückverfolgbarkeit: [dict(charge, kennung, profil, werkstoff, nummer, anzahl, zeit)] aller Verbrauchsbuchungen
    mit Charge."""
    out = []
    for r in db.con.execute("SELECT b.zeit, b.kennung, b.nummer, b.anzahl, p.charge, p.profil, p.werkstoff FROM "
                            "lager_buchungen b LEFT JOIN lager_bestand p ON p.id=b.bestand_id WHERE b.art='Verbrauch' "
                            "ORDER BY b.id"):
        out.append(dict(r))
    return out
