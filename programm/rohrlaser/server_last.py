"""Lastprobe des zentralen Servers mit vielen Arbeitsplätzen gleichzeitig (Serverversion S5, Patrick 26.11.2026).

Jeder Probe-Platz ist ein echtes Programm ohne Fenster (Datenbank mit eigenem Login rl_LTnn, eigener Merkdatei) und
macht in Runden, was ein Mitarbeiter tut: Puls (Anwesenheit, Reservierungen verlängern), Angebotsliste lesen,
eigenes Angebot anlegen und reservieren, Positionen dazu, ein gemeinsames Angebot zu reservieren versuchen (immer
nur einer hält es), Einstellung lesen, Notiz an einen Kollegen. Gemessen wird die Dauer jeder Aktion (Median, 95 %,
größte), gezählt werden Fehler, Verbindungen am Server und ob jede Nummer nur einmal vergeben wurde.

Am Server-Rechner: ``--server lasttest --ordner … [--plaetze 25] [--runden 10]``. Die Probe-Logins, ihre Angebote,
Reservierungen, Notizen und Anwesenheiten werden danach wieder entfernt; Angebotsnummern der Firma werden nicht
verbraucht (Probe-Angebote haben eigene Nummern LAST-…). Mit nummern=True (nur Prüfserver) vergeben die Plätze
echte Nummern aus dem gemeinsamen Nummernkreis, um deren Eindeutigkeit unter Last zu prüfen.
"""
import contextlib
import os
import secrets
import statistics
import tempfile
import threading
import time
from pathlib import Path

from . import server_betrieb as sb

PRAEFIX = "LT"
NUMMER_PRAEFIX = "LAST-"
PLATZ_PRAEFIX = "LASTPROBE-"
GRENZE_P95_S = 1.0          # 95 % aller Aktionen schneller als 1 s (Arbeitsplätze im Firmennetz)


def _kuerzel(i):
    return f"{PRAEFIX}{i + 1:02d}"


def _probe_aufraeumen(con, kuerzel):
    from . import server_mehrplatz, server_zusammenarbeit
    with con.transaction():
        ids = [r[0] for r in con.execute("SELECT id FROM angebote WHERE nummer LIKE %s OR bearbeiter = ANY(%s)",
                                         (NUMMER_PRAEFIX + "%", list(kuerzel)))]
        if ids:
            for (t,) in con.execute("SELECT table_name FROM information_schema.columns WHERE table_schema = "
                                    "current_schema() AND column_name = 'angebot_id' AND table_name <> 'netze'"
                                    ).fetchall():
                if t == "positionen":
                    con.execute("DELETE FROM netze WHERE position_id IN (SELECT id FROM positionen WHERE "
                                "angebot_id = ANY(%s))", (ids,))
                con.execute(f'DELETE FROM "{t}" WHERE angebot_id = ANY(%s)', (ids,))
            con.execute("DELETE FROM angebote WHERE id = ANY(%s)", (ids,))
        for t in (server_mehrplatz.ANWESEND, server_mehrplatz.SPERREN, server_mehrplatz.PROTOKOLL):
            con.execute(f"DELETE FROM {t} WHERE kuerzel = ANY(%s)", (list(kuerzel),))
        con.execute(f"DELETE FROM {server_zusammenarbeit.VORGAENGE} WHERE von = ANY(%s) OR an = ANY(%s)",
                    (list(kuerzel), list(kuerzel)))
        muster = [f"{sb.BENUTZER_PRAEFIX}{k}:%" for k in kuerzel] + [f"{sb.PLATZ_PRAEFIX}{PLATZ_PRAEFIX}%"]
        con.execute("DELETE FROM einstellungen WHERE name LIKE ANY(%s)", (muster,))
    for k in kuerzel:
        with contextlib.suppress(Exception):
            con.execute(f'DROP ROLE IF EXISTS "{sb.login_name(k)}"')


class _Platz:
    def __init__(self, nr, db):
        self.nr, self.db = nr, db
        self.zeiten = {}
        self.fehler = []
        self.nummern = []
        self.gehalten = 0

    def mess(self, name, f, *a, **k):
        t = time.perf_counter()
        try:
            return f(*a, **k)
        except Exception as e:          # noqa: BLE001 - jeder Fehler zählt als Ergebnis der Probe
            self.fehler.append(f"{name}: {type(e).__name__}: {e}")
            return None
        finally:
            self.zeiten.setdefault(name, []).append(time.perf_counter() - t)


def _runde(p, i, gemeinsam, kollege, nummern, start):
    from . import server_mehrplatz as sm, server_zusammenarbeit as sz, teilen
    db = p.db
    p.mess("puls", sm.puls, db, {})
    p.mess("angebotsliste", lambda: db.con.execute(
        "SELECT id, nummer, kunde, bearbeiter, geaendert FROM angebote ORDER BY geaendert DESC LIMIT 200").fetchall())
    kopf = dict(kunde=f"Lastprobe {p.nr}/{i}")
    if not nummern:
        kopf["nummer"] = f"{NUMMER_PRAEFIX}{_kuerzel(p.nr)}-{i}"
    aid = p.mess("angebot_neu", db.angebot_neu, kopf, zaehler=nummern)
    if aid is not None:
        p.nummern.append(db.angebot(aid)["nummer"])
        p.mess("reservieren", sm.reservieren, db, sm.objekt_angebot(aid), "Lastprobe")
        for j in range(3):
            p.mess("position_neu", db.position_neu, aid, dict(bezeichnung=f"Teil {j}", menge=j + 1))
        p.mess("freigeben", sm.freigeben, db, sm.objekt_angebot(aid))
    start.wait()                        # alle gleichzeitig auf das gemeinsame Angebot
    r = p.mess("gemeinsam_reservieren", sm.reservieren, db, sm.objekt_angebot(gemeinsam), "gemeinsam")
    if r is None and sm.inhaber(db, sm.objekt_angebot(gemeinsam)) is None:
        p.fehler.append("gemeinsames Angebot ohne Inhaber nach eigener Reservierung")
    elif r is None:
        p.gehalten += 1
        p.mess("freigeben", sm.freigeben, db, sm.objekt_angebot(gemeinsam))
    p.mess("einstellung", db.einstellung, "stundensatz_laser")
    p.mess("notiz", teilen.notiz_senden, db, kollege, f"Lastprobe {i}")
    p.mess("vorgaenge", sz.abholen, db)


def lauf(server, plaetze=25, runden=10, nummern=False, melden=print, adresse="127.0.0.1", grenze_s=GRENZE_P95_S):
    """Lastprobe gegen den laufenden ZentralerServer server. Alle Probe-Plätze laufen in diesem einen Programm
    (strenger als echte Arbeitsplätze an eigenen PCs). Ergebnis: Bericht (dict)."""
    from . import server_mehrplatz as sm
    from .datenbank import Datenbank
    melden = melden or (lambda _t: None)
    if plaetze > sb.MAX_VERBINDUNGEN // 3:
        raise sb.ServerFehler(f"Höchstens {sb.MAX_VERBINDUNGEN // 3} Probe-Plätze.")
    kuerzel = [_kuerzel(i) for i in range(plaetze)]
    pw = {k: secrets.token_urlsafe(12) for k in kuerzel}
    zugang_datei = server.daten / sb.ZUGANG_DATEI
    if not zugang_datei.exists():
        server.zugang_schreiben()
    zugang = sb.zugangsdatei_lesen(zugang_datei)
    tmp = Path(tempfile.mkdtemp(prefix="rl_lastprobe_"))
    merk_platz = os.environ.get("ROHRLASER_ARBEITSPLATZ")
    dbs, bericht = [], {}
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        _probe_aufraeumen(con, kuerzel)
        for k in kuerzel:
            sb.benutzer_anlegen(con, k, pw[k], sb.RECHT_BEARBEITEN, name=f"Lastprobe {k}")
    try:
        t0 = time.perf_counter()
        for i, k in enumerate(kuerzel):
            os.environ["ROHRLASER_ARBEITSPLATZ"] = f"{PLATZ_PRAEFIX}{i + 1:02d}"
            merk = tmp / f"p{i}" / "Daten" / "rohrlaser.db"
            merk.parent.mkdir(parents=True, exist_ok=True)
            sb.verbinden_einrichten(merk, zugang, adresse=adresse)
            sb.anmelden(k, pw[k])
            dbs.append(Datenbank(merk))
        oeffnen_s = (time.perf_counter() - t0) / plaetze
        melden(f"{plaetze} Probe-Plätze angemeldet (je {oeffnen_s:.2f} s beim Öffnen).")
        gemeinsam = dbs[0].angebot_neu(dict(kunde="Lastprobe gemeinsam", nummer=f"{NUMMER_PRAEFIX}GEMEINSAM"),
                                       zaehler=False)
        ps = [_Platz(i, d) for i, d in enumerate(dbs)]
        verbindungen = []
        t0 = time.perf_counter()
        for i in range(runden):
            start = threading.Barrier(plaetze)
            fs = [threading.Thread(target=_runde, args=(p, i, gemeinsam, kuerzel[(p.nr + 1) % plaetze], nummern,
                                                         start), daemon=True) for p in ps]
            for f in fs:
                f.start()
            for f in fs:
                f.join(300)
            with server.verwalter_verbinden(sb.DATENBANK) as con:
                verbindungen.append(con.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s",
                                                (sb.DATENBANK,)).fetchone()[0])
        dauer = time.perf_counter() - t0
        alle = [z for p in ps for zs in p.zeiten.values() for z in zs]
        je = {}
        for p in ps:
            for n, zs in p.zeiten.items():
                je.setdefault(n, []).extend(zs)
        vergeben = [n for p in ps for n in p.nummern]
        fehler = [f for p in ps for f in p.fehler]
        q = statistics.quantiles(alle, n=20) if len(alle) >= 20 else [max(alle or [0])] * 19
        bericht = dict(
            plaetze=plaetze, runden=runden, aktionen=len(alle), dauer_s=dauer, oeffnen_s=oeffnen_s,
            median_s=statistics.median(alle) if alle else 0.0, p95_s=q[18], max_s=max(alle or [0]),
            je_aktion={n: dict(anzahl=len(zs), median_s=statistics.median(zs), max_s=max(zs)) for n, zs in je.items()},
            fehler=fehler, nummern=len(vergeben), doppelt=sorted({n for n in vergeben if vergeben.count(n) > 1}),
            verbindungen_max=max(verbindungen or [0]), gemeinsam_gehalten=sum(p.gehalten for p in ps),
            puls_verloren=len(sm.anwesende(dbs[0])) < plaetze)
        bericht["bestanden"] = (not fehler and not bericht["doppelt"] and bericht["p95_s"] < grenze_s
                                and bericht["verbindungen_max"] <= sb.MAX_VERBINDUNGEN)
        melden(f"{bericht['aktionen']} Aktionen in {dauer:.1f} s: Median {bericht['median_s'] * 1000:.0f} ms, "
               f"95 % unter {bericht['p95_s'] * 1000:.0f} ms, längste {bericht['max_s'] * 1000:.0f} ms; "
               f"{len(fehler)} Fehler, {len(bericht['doppelt'])} doppelte Nummern, höchstens "
               f"{bericht['verbindungen_max']} Verbindungen (erlaubt {sb.MAX_VERBINDUNGEN}).")
        for n, w in sorted(bericht["je_aktion"].items()):
            melden(f"  {n:<22} {w['anzahl']:>5}×  Median {w['median_s'] * 1000:>6.0f} ms  längste "
                   f"{w['max_s'] * 1000:>6.0f} ms")
        for f in fehler[:10]:
            melden(f"  FEHLER {f}")
        melden("Lastprobe bestanden." if bericht["bestanden"] else "Lastprobe NICHT bestanden.")
        return bericht
    finally:
        for d in dbs:
            with contextlib.suppress(Exception):
                d.schliessen()
        sb.abmelden()
        if merk_platz is None:
            os.environ.pop("ROHRLASER_ARBEITSPLATZ", None)
        else:
            os.environ["ROHRLASER_ARBEITSPLATZ"] = merk_platz
        with server.verwalter_verbinden(sb.DATENBANK) as con:
            _probe_aufraeumen(con, kuerzel)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
