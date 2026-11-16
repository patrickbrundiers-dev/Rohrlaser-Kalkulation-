"""Messlauf mit dem echten Programmcode (Datenbank-Klasse) auf SQLite und auf PostgreSQL (Plan Datenbank-Modernisierung,
Phase 4 und 8). Nur Entwicklung, nicht im Programm; erzeugte Testdaten, keine Kundendaten.

Gemessen: Datendatei öffnen (Programmstart ohne Fenster), Angebotsliste, Suche, Angebot öffnen (Kopf + Positionen,
5 und 50 Positionen), Zelle ändern (eine Transaktion), Angebot kopieren, Sicherung. Jede Messung als Median aus
mehreren Läufen in Millisekunden.

Aufruf: python werkzeuge/programm_messung.py [--angebote 1000] [--json DATEI] [--nur sqlite|postgres]
PostgreSQL braucht die PostgreSQL-Programme und einen Nicht-root-Benutzer (initdb verweigert root).
"""
import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "tests"))

import beispiel_angebot  # noqa: E402
from rohrlaser import datenspeicher, pg_lokal  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

KUNDEN = ["Müller Stahlbau", "Meier Metall", "Schmidt Anlagen", "Becker Fördertechnik", "Wagner Gestelle"]


def ms(f, n=5):
    werte = []
    for _ in range(n):
        t = time.perf_counter()
        f()
        werte.append((time.perf_counter() - t) * 1000)
    return round(statistics.median(werte), 1)


def fuellen(db, n):
    """n Angebote mit je 5 Positionen und Staffeln, dazu eines mit 50 Positionen. Ergebnis: (id5, id50)."""
    t = time.perf_counter()
    erstes = None
    with db.con:
        for i in range(n):
            a = beispiel_angebot.anlegen(db, dict(nummer=f"2026-{i:05d}", kunde=KUNDEN[i % len(KUNDEN)],
                                                  kundennr=f"K-{1000 + i % 50}")) if i == 0 else None
            if a is None:
                a = db.angebot_neu(dict(beispiel_angebot.KOPF, nummer=f"2026-{i:05d}", kunde=KUNDEN[i % len(KUNDEN)],
                                        kundennr=f"K-{1000 + i % 50}"))
                for p in beispiel_angebot.POSITIONEN:
                    db.position_neu(a, p)
            erstes = erstes or a
        gross = db.angebot_neu(dict(beispiel_angebot.KOPF, nummer="2026-99999", kunde="Großauftrag"))
        for k in range(10):
            for p in beispiel_angebot.POSITIONEN:
                db.position_neu(gross, dict(p, pos=p["pos"] + 100 * k))
    return erstes, gross, time.perf_counter() - t


def lauf(name, pfad, n):
    w = {}
    t = time.perf_counter()
    db = Datenbank(pfad)
    w["oeffnen_neu_ms"] = round((time.perf_counter() - t) * 1000, 1)
    a5, a50, s = fuellen(db, n)
    w["anlegen_je_angebot_ms"] = round(s * 1000 / n, 2)
    db.schliessen()
    w["oeffnen_ms"] = ms(lambda: Datenbank(pfad).schliessen(), 3)
    db = Datenbank(pfad)
    w["liste_ms"] = ms(lambda: db.angebote())
    w["suche_ms"] = ms(lambda: db.angebote(suche="Meier"))
    w["oeffnen_5_pos_ms"] = ms(lambda: (db.angebot(a5), db.positionen(a5)))
    w["oeffnen_50_pos_ms"] = ms(lambda: (db.angebot(a50), db.positionen(a50)))
    p = db.positionen(a5)[0]["id"]
    zaehler = iter(range(10 ** 6))
    w["zelle_aendern_ms"] = ms(lambda: db.position_aendern(p, "stueck", 10 + next(zaehler)), 20)
    w["kopieren_50_pos_ms"] = ms(lambda: db.angebot_kopieren(a50), 3)
    w["sicherung_ms"] = ms(lambda: db.sicherung(zusatz="messung"), 2)
    db.schliessen()
    print(name, json.dumps(w, ensure_ascii=False))
    return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angebote", type=int, default=1000)
    ap.add_argument("--json")
    ap.add_argument("--nur")
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp())
    ergebnis = dict(angebote=a.angebote)
    if a.nur in (None, "sqlite"):
        ergebnis["sqlite"] = lauf("SQLite", tmp / "s" / "rohrlaser.db", a.angebote)
    if a.nur in (None, "postgres"):
        try:
            pg_lokal.programme()
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                raise pg_lokal.PgFehlt("als root")
        except pg_lokal.PgFehlt as e:
            print("PostgreSQL übersprungen:", e)
        else:
            pfad = tmp / "p" / "rohrlaser.db"
            db = Datenbank(pfad)
            datenspeicher.umstellen(db)
            ergebnis["postgres"] = lauf_pg(pfad, a.angebote)
            datenspeicher.alle_stoppen()
    if a.json:
        Path(a.json).write_text(json.dumps(ergebnis, indent=1, ensure_ascii=False), encoding="utf-8")


def lauf_pg(pfad, n):
    """Wie lauf, aber auf einer schon umgestellten Datendatei (Merkdatei → PostgreSQL)."""
    return lauf("PostgreSQL", pfad, n)


if __name__ == "__main__":
    main()
