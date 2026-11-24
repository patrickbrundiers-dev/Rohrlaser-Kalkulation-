"""Reklamationen je Auftrag und Position (Plan 29.10.2026 Schritt 2c).

Erfasst im Angebot (Ausgaben → „Reklamation erfassen …“, nur beauftragte Angebote): Position, Datum, Menge, Fehlerart
(Einstellung 'reklamation_fehlerarten'), Ursache, Maßnahme, Kosten und Status. Die Kosten aller Reklamationen eines
Auftrags gehen als Kostenart „Reklamationen“ (Soll 0) in die Nachkalkulation und damit in Deckungsbeitrag und
Auswertung über alle Aufträge. Datei → „Reklamationen …“ zeigt alle offenen bzw. alle Reklamationen und die Quote
(reklamierte Stück ÷ gelieferte Stück der beauftragten Angebote) je Fehlerart, Kunde und Werkstoff.
Tabelle reklamationen: id, angebot_id, position_id, pos, datum, menge, fehlerart, ursache, massnahme, kosten, status,
bemerkung, wer, erledigt_am."""
import datetime

from .angebot import aktiv as position_aktiv

TABELLEN = ("reklamationen",)
TABELLEN_SQL = (
    "CREATE TABLE IF NOT EXISTS reklamationen (id INTEGER PRIMARY KEY, angebot_id INTEGER NOT NULL, position_id "
    "INTEGER, pos TEXT, datum TEXT, menge REAL, fehlerart TEXT, ursache TEXT, massnahme TEXT, kosten REAL, status "
    "TEXT, bemerkung TEXT, wer TEXT, erledigt_am TEXT)",
    "CREATE INDEX IF NOT EXISTS reklamationen_angebot ON reklamationen (angebot_id, id)",
)
FEHLERARTEN = ("Maß außerhalb der Toleranz", "Kontur fehlt oder falsch", "Grat oder Schlacke",
               "Oberfläche, Kratzer, Anlauffarben", "Falscher Werkstoff oder falsches Profil", "Falsche Menge",
               "Transportschaden", "Sonstiges")
URSACHEN = ("intern: Fertigung", "intern: Arbeitsvorbereitung / Programm", "Material / Lieferant", "Kunde (Zeichnung, "
            "Angabe)", "Transport", "unbekannt")
MASSNAHMEN = ("Nacharbeit", "Neuteile", "Gutschrift", "Rücksendung", "keine (unberechtigt)")
OFFEN, ERLEDIGT = "offen", "erledigt"
STATUS = (OFFEN, ERLEDIGT)
FELDER = ("position_id", "pos", "datum", "menge", "fehlerart", "ursache", "massnahme", "kosten", "status",
          "bemerkung")
ALLE_POSITIONEN = "ganzer Auftrag"


class ReklamationFehler(ValueError):
    """Reklamation nicht möglich (Text für den Benutzer)."""


def einrichten(con):
    for sql in TABELLEN_SQL:
        con.execute(sql)


def angebot_geloescht(db, angebot_id):
    db.con.execute("DELETE FROM reklamationen WHERE angebot_id=?", (angebot_id,))


def fehlerarten(db):
    out = []
    for z in str(db.einstellung("reklamation_fehlerarten") or "").splitlines():
        z = z.strip()
        if z and z not in out:
            out.append(z)
    return out or list(FEHLERARTEN)


def _schreibschutz(db):
    from .datenbank import Lesemodus
    if db.nur_lesen:
        raise Lesemodus(f"Lesemodus – {db.nur_lesen}.")


def speichern(db, angebot_id, werte, reklamation_id=None, wer=None):
    """Neue Reklamation anlegen (reklamation_id None) oder ändern. Ergebnis: id. ReklamationFehler sonst."""
    _schreibschutz(db)
    kopf = db.angebot(angebot_id)
    if not kopf:
        raise ReklamationFehler("Angebot nicht gefunden.")
    if kopf.get("vorgang") != "Beauftragt":
        raise ReklamationFehler("Reklamationen nur für beauftragte Angebote (Vorgang „Beauftragt“).")
    w = {f: werte.get(f) for f in FELDER}
    if w["position_id"] is not None:
        p = next((x for x in db.positionen(angebot_id) if x["id"] == w["position_id"]), None)
        if p is None:
            raise ReklamationFehler("Die Position gehört nicht zu diesem Angebot.")
        w["pos"] = _pos_text(p.get("pos"))
    if not (w["menge"] or 0) > 0 and w["position_id"] is not None:
        raise ReklamationFehler("Menge fehlt (reklamierte Stück).")
    w["datum"] = w["datum"] or datetime.date.today().isoformat()
    w["status"] = w["status"] if w["status"] in STATUS else OFFEN
    w["kosten"] = float(w["kosten"] or 0)
    with db.con:
        if reklamation_id is None:
            w.update(angebot_id=angebot_id, wer=wer if wer is not None else (db.einstellung("benutzer_kuerzel") or ""),
                     erledigt_am=datetime.date.today().isoformat() if w["status"] == ERLEDIGT else None)
            spalten = list(w)
            return db.con.execute(f"INSERT INTO reklamationen ({', '.join(spalten)}) VALUES "
                                  f"({', '.join('?' * len(spalten))})", [w[s] for s in spalten]).lastrowid
        alt = db.con.execute("SELECT status, erledigt_am FROM reklamationen WHERE id=?", (reklamation_id,)).fetchone()
        if alt is None:
            raise ReklamationFehler("Reklamation nicht gefunden.")
        w["erledigt_am"] = (alt[1] or datetime.date.today().isoformat()) if w["status"] == ERLEDIGT else None
        db.con.execute(f"UPDATE reklamationen SET {', '.join(f'{s}=?' for s in w)} WHERE id=?",
                       [*w.values(), reklamation_id])
        return reklamation_id


def erledigen(db, reklamation_id):
    _schreibschutz(db)
    with db.con:
        db.con.execute("UPDATE reklamationen SET status=?, erledigt_am=COALESCE(erledigt_am, ?) WHERE id=?",
                       (ERLEDIGT, datetime.date.today().isoformat(), reklamation_id))


def loeschen(db, reklamation_id):
    _schreibschutz(db)
    with db.con:
        db.con.execute("DELETE FROM reklamationen WHERE id=?", (reklamation_id,))


def _pos_text(pos):
    try:
        f = float(pos)
        return str(int(f)) if f.is_integer() else str(pos)
    except (TypeError, ValueError):
        return str(pos or "")


def liste(db, angebot_id=None, nur_offen=False):
    """Reklamationen mit Angebotsnummer, Kunde und Artikel, neueste zuerst."""
    sql = ("SELECT r.*, a.nummer, a.kunde, p.artikel, p.werkstoff_id, p.stueck FROM reklamationen r "
           "LEFT JOIN angebote a ON a.id = r.angebot_id LEFT JOIN positionen p ON p.id = r.position_id")
    bed, args = [], []
    if angebot_id is not None:
        bed.append("r.angebot_id=?")
        args.append(angebot_id)
    if nur_offen:
        bed.append("r.status=?")
        args.append(OFFEN)
    if bed:
        sql += " WHERE " + " AND ".join(bed)
    return [dict(r) for r in db.con.execute(sql + " ORDER BY r.datum DESC, r.id DESC", args)]


def kosten(db, angebot_id):
    """Summe der Reklamationskosten eines Auftrags oder None (keine Reklamation)."""
    r = db.con.execute("SELECT COUNT(*), SUM(kosten) FROM reklamationen WHERE angebot_id=?", (angebot_id,)).fetchone()
    return float(r[1] or 0) if r[0] else None


def auswertung(db, heute=None, tage=365):
    """Quote je Fehlerart, Kunde und Werkstoff: dict(gesamt, fehlerart, kunde, werkstoff), je Gruppe [dict(name,
    anzahl, menge, kosten, geliefert, quote)]. geliefert = Stück der aktiven Positionen beauftragter Angebote im
    Zeitraum (nach Angebotsdatum); Quote = reklamierte ÷ gelieferte Stück (nur bei Kunde und Werkstoff sinnvoll)."""
    heute = heute or datetime.date.today()
    ab = (heute - datetime.timedelta(days=tage)).isoformat() if tage else ""
    auftraege = [a for a in db.angebote() if a.get("vorgang") == "Beauftragt" and not a.get("fremd")
                 and str(a.get("datum") or "") >= ab]
    ids = {a["id"] for a in auftraege}
    geliefert = {"kunde": {}, "werkstoff": {}}
    gesamt_stk = 0.0
    for a in auftraege:
        for p in db.positionen(a["id"]):
            if not position_aktiv(p) or not isinstance(p.get("stueck"), (int, float)):
                continue
            gesamt_stk += p["stueck"]
            k = a.get("kunde") or "?"
            w = p.get("werkstoff_id") or "?"
            geliefert["kunde"][k] = geliefert["kunde"].get(k, 0) + p["stueck"]
            geliefert["werkstoff"][w] = geliefert["werkstoff"].get(w, 0) + p["stueck"]
    rekl = [r for r in liste(db) if r["angebot_id"] in ids]
    out = {}
    for merkmal, schluessel in (("fehlerart", lambda r: r.get("fehlerart") or "?"),
                                ("kunde", lambda r: r.get("kunde") or "?"),
                                ("werkstoff", lambda r: r.get("werkstoff_id") or "ganzer Auftrag")):
        g = {}
        for r in rekl:
            x = g.setdefault(schluessel(r), dict(anzahl=0, menge=0.0, kosten=0.0))
            x["anzahl"] += 1
            x["menge"] += r.get("menge") or 0
            x["kosten"] += r.get("kosten") or 0
        zeilen = []
        for name, x in g.items():
            gel = geliefert.get(merkmal, {}).get(name)
            zeilen.append(dict(name=name, **x, geliefert=gel, quote=x["menge"] / gel if gel else None))
        out[merkmal] = sorted(zeilen, key=lambda z: (-z["kosten"], -z["anzahl"], str(z["name"])))
    menge = sum(r.get("menge") or 0 for r in rekl)
    out["gesamt"] = dict(anzahl=len(rekl), offen=sum(1 for r in rekl if r.get("status") == OFFEN), menge=menge,
                         kosten=sum(r.get("kosten") or 0 for r in rekl), geliefert=gesamt_stk,
                         auftraege=len(auftraege), quote=menge / gesamt_stk if gesamt_stk else None)
    return out
