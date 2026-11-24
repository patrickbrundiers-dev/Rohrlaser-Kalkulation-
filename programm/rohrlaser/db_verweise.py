"""Verweise zwischen Tabellen prüfen (Systemprüfung 17.11.2026, DB-01).

Die meisten Verweise (…_id) stehen nur im Programmcode, nicht als Fremdschlüssel in der Datendatei: so lassen sich
Zeilen beim Abgleich über uid zwischen den PCs zusammenführen. Ein vergessener Lösch- oder Archivweg hinterlässt dann
Zeilen, die ins Leere zeigen (so DB-02 bis 0.9.374). zaehlen() zählt sie, nur lesend, für SQLite und PostgreSQL; das
Support-Paket legt das Ergebnis als verweise.json bei.

PFLICHT: Zeilen, die ohne ihr Angebot bzw. ihre Position nicht leben dürfen (Befund = Fehler im Programm).
JOURNAL: Protokolle, die nach dem Löschen eines Angebots bewusst bleiben (Lagerjournal, Automatik, Fracht); sie
werden nur zur Information gezählt (eine von SQLite wiedervergebene Angebots-ID kann dort auf ein neueres Angebot
zeigen).
"""
from . import db_verbindung

# (Tabelle, Spalte, Zieltabelle); Ziel-Spalte ist immer id
PFLICHT = (
    ("positionen", "angebot_id", "angebote"),
    ("step_protokoll", "angebot_id", "angebote"),
    ("staffel_stufen", "angebot_id", "angebote"),
    ("staffeln", "angebot_id", "angebote"),
    ("staffeln", "stufe_id", "staffel_stufen"),
    ("netze", "position_id", "positionen"),
    ("auftrag_status", "angebot_id", "angebote"),
    ("reklamationen", "angebot_id", "angebote"),
    ("reklamationen", "position_id", "positionen"),
    ("rueckmeldungen", "angebot_id", "angebote"),
    ("rueckmeldungen", "position_id", "positionen"),
    ("lager_auftraege", "angebot_id", "angebote"),
    ("lager_reservierung", "angebot_id", "angebote"),
    ("lager_reservierung", "bestand_id", "lager_bestand"),
)
JOURNAL = (
    ("lager_buchungen", "angebot_id", "angebote"),
    ("lager_buchungen", "bestand_id", "lager_bestand"),
    ("automatik", "angebot_id", "angebote"),
    ("fracht_kalkulationen", "angebot_id", "angebote"),
)


def _zaehlen(con, liste, da):
    out = {}
    for t, s, ziel in liste:
        if t not in da or ziel not in da or s not in db_verbindung.spalten(con, t):
            continue            # ältere Datendatei ohne diese Tabelle/Spalte: nichts zu prüfen
        n = con.execute(f'SELECT COUNT(*) FROM "{t}" k WHERE k."{s}" IS NOT NULL AND NOT EXISTS '
                        f'(SELECT 1 FROM "{ziel}" z WHERE z.id = k."{s}")').fetchone()[0]
        if n:
            out[f"{t}.{s} → {ziel}"] = int(n)
    return out


def zaehlen(db):
    """{"fehler": {"tabelle.spalte → ziel": Anzahl}, "journal": {…}} – nur Einträge mit Anzahl > 0. Liest nur."""
    con = db.con if hasattr(db, "con") else db
    da = set(db_verbindung.tabellen(con))
    return dict(fehler=_zaehlen(con, PFLICHT, da), journal=_zaehlen(con, JOURNAL, da))


def text(ergebnis):
    """Kurzer Klartext für Support-Paket und Protokoll."""
    f, j = ergebnis.get("fehler") or {}, ergebnis.get("journal") or {}
    zeilen = ["Verweise ins Leere: " + ("keine" if not f else f"{sum(f.values())} (Fehler)")]
    zeilen += [f"  {k}: {n}" for k, n in sorted(f.items())]
    if j:
        zeilen.append(f"Journal ohne Angebot (gewollt, nur Information): {sum(j.values())}")
        zeilen += [f"  {k}: {n}" for k, n in sorted(j.items())]
    return "\n".join(zeilen)
