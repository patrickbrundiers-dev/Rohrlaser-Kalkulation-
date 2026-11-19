"""Last- und Vergleichstest (Plan Datenbank-Modernisierung, Phase 8). Nur Entwicklung, erzeugte Testdaten.

Teil A – gleichzeitige Zugriffe auf eine Datenbank (1/5/10/25 Benutzer, je eigene Verbindung in einem eigenen Thread):
jeder Benutzer arbeitet eine Mischung ab (Angebotsliste, Suche, Angebot öffnen, Zelle ändern, neues Angebot mit
Position). Gemessen: Median und 95-%-Wert je Vorgang, Fehler, doppelte Angebotsnummern, Anzahl am Ende. Seit 0.9.407
nur PostgreSQL, alle Stufen nacheinander auf derselben Ausgangsdatenbank (Standard 10.000 Angebote).

Teil B – Abgleich über den gemeinsamen Ordner mit 1/5/10/25 Arbeitsplätzen: jeder ändert Stammdaten (zum Teil dieselbe
Zeile, verschiedene Felder) und legt Angebote an; gemessen wird ein Abgleich, danach müssen alle denselben Stand haben.

Aufruf: python werkzeuge/last_messung.py [--angebote 10000] [--benutzer 1,5,10,25] [--json DATEI] [--nur a|b]
PostgreSQL braucht die PostgreSQL-Programme und einen Nicht-root-Benutzer (initdb verweigert root).
"""
import argparse
import json
import random
import shutil
import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "tests"))
sys.path.insert(0, str(HIER))

import beispiel_angebot  # noqa: E402
import programm_messung  # noqa: E402
from rohrlaser import datenspeicher, teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

VORGAENGE_JE_BENUTZER = 30


def _werte(liste):
    if not liste:
        return {}
    s = sorted(liste)
    return dict(median_ms=round(statistics.median(s), 1), p95_ms=round(s[min(len(s) - 1, int(len(s) * 0.95))], 1),
                anzahl=len(s))


def benutzer_lauf(pfad, n_benutzer, ids, jahr_start):
    """n_benutzer Threads mit je eigener Datenbank-Verbindung. Ergebnis: Messwerte je Vorgang."""
    zeiten = {k: [] for k in ("liste", "suche", "oeffnen", "aendern", "neu")}
    fehler = []
    sperre = threading.Lock()
    start = threading.Barrier(n_benutzer)

    def arbeit(nr):
        rnd = random.Random(nr)
        try:
            db = Datenbank(pfad)
        except Exception as e:          # noqa: BLE001 – jeder Fehler zählt
            with sperre:
                fehler.append(f"öffnen: {e}")
            start.abort()
            return
        try:
            start.wait(120)
            for i in range(VORGAENGE_JE_BENUTZER):
                art = ("liste", "suche", "oeffnen", "aendern", "aendern", "oeffnen", "neu")[i % 7]
                t = time.perf_counter()
                try:
                    if art == "liste":
                        db.angebote()
                    elif art == "suche":
                        db.angebote(suche=rnd.choice(programm_messung.KUNDEN)[:5])
                    elif art == "oeffnen":
                        a = rnd.choice(ids)
                        db.angebot(a)
                        db.positionen(a)
                    elif art == "aendern":
                        a = rnd.choice(ids)
                        p = db.positionen(a)
                        if p:
                            db.position_aendern(p[0]["id"], "stueck", rnd.randint(1, 500))
                    else:
                        a = db.angebot_neu(dict({k_: v for k_, v in beispiel_angebot.KOPF.items() if k_ != "nummer"}, kunde=f"Last {nr}",
                                                datum=jahr_start))
                        db.position_neu(a, beispiel_angebot.POSITIONEN[0])
                    db.con.commit()
                except Exception as e:  # noqa: BLE001
                    try:
                        db.con.rollback()
                    except Exception:   # noqa: BLE001
                        pass
                    with sperre:
                        fehler.append(f"{art}: {type(e).__name__}: {str(e)[:120]}")
                    continue
                with sperre:
                    zeiten[art].append((time.perf_counter() - t) * 1000)
        except threading.BrokenBarrierError:
            pass
        finally:
            db.schliessen()

    t0 = time.perf_counter()
    th = [threading.Thread(target=arbeit, args=(i,)) for i in range(n_benutzer)]
    for x in th:
        x.start()
    for x in th:
        x.join()
    dauer = time.perf_counter() - t0
    db = Datenbank(pfad)
    nummern = [r[0] for r in db.con.execute("SELECT nummer FROM angebote")]
    db.schliessen()
    return dict(benutzer=n_benutzer, dauer_s=round(dauer, 2), fehler=len(fehler), fehler_beispiele=fehler[:5],
                doppelte_nummern=len(nummern) - len(set(nummern)), angebote=len(nummern),
                **{k: _werte(v) for k, v in zeiten.items()})


def teil_a(n_angebote, stufen, tmp):
    basis = tmp / "basis" / "rohrlaser.db"
    db = Datenbank(basis)
    a5, _a50, s = programm_messung.fuellen(db, n_angebote)
    db.con.commit()
    ids = [r[0] for r in db.con.execute("SELECT id FROM angebote ORDER BY id LIMIT 2000")]
    db.schliessen()
    print(f"Ausgangsdatei: {n_angebote} Angebote in {s:.0f} s angelegt")
    # seit 0.9.407 (Datenbank Schritt 1) gibt es nur noch PostgreSQL: alle Stufen auf derselben Datenbank
    erg = dict(postgres=[])
    ziel = basis
    for n in stufen:
        r = benutzer_lauf(ziel, n, ids, "2026-11-14")
        print("PostgreSQL", json.dumps(r, ensure_ascii=False))
        erg["postgres"].append(r)
    datenspeicher.alle_stoppen()
    return erg


def teil_b(stufen, tmp):
    """Abgleich mit n Arbeitsplätzen über einen gemeinsamen Ordner."""
    out = []
    for n in stufen:
        o = tmp / f"abgleich{n}"
        gemeinsam = o / "Gemeinsam"
        gemeinsam.mkdir(parents=True)
        plaetze = []
        for i in range(n):
            db = Datenbank(o / f"pc{i}" / "rohrlaser.db")
            db.einstellung_setzen("benutzer_name", f"PC {i}")
            db.einstellung_setzen("benutzer_kuerzel", f"P{i:02d}")
            db.einstellung_setzen("teilen_ordner", str(gemeinsam))
            teilen.abgleichen(db, teilen.UEBERNEHMEN if i else None)
            plaetze.append(db)
        erster = plaetze[0]
        k = erster.neu("kunden", dict(kundennr="K-1", name="Gemeinsam GmbH"))
        u = next(z["uid"] for z in erster.zeilen("kunden", True) if z["id"] == k)
        teilen.abgleichen(erster)
        for db in plaetze[1:]:
            teilen.abgleichen(db)
        felder = ["bemerkung", "telefon", "email", "strasse", "plz_ort", "ansprechpartner", "hinweis"]
        for i, db in enumerate(plaetze):      # jeder ändert ein anderes Feld derselben Zeile, dazu 3 Angebote
            z = next(z for z in db.zeilen("kunden", True) if z["uid"] == u)
            db.aendern("kunden", z["id"], felder[i % len(felder)], f"von P{i:02d}")
            for _ in range(3):
                a = db.angebot_neu(dict({k_: v for k_, v in beispiel_angebot.KOPF.items() if k_ != "nummer"}, kunde=f"P{i:02d}"))
                db.position_neu(a, beispiel_angebot.POSITIONEN[0])
            teilen.schreiben(db)
        zeiten = []
        for runde in range(2):            # zweimal: danach hat jeder alle Änderungen
            for db in plaetze:
                t = time.perf_counter()
                teilen.abgleichen(db)
                if runde == 0:
                    zeiten.append((time.perf_counter() - t) * 1000)
        staende = set()
        for db in plaetze:
            z = next(z for z in db.zeilen("kunden", True) if z["uid"] == u)
            staende.add(tuple(z.get(f) for f in felder))
        nummern = [r[0] for r in plaetze[0].con.execute("SELECT nummer FROM angebote")]
        erwartet = {f: f"von P{max(i for i in range(n) if i % len(felder) == j):02d}"
                    for j, f in enumerate(felder) if j < n}
        gleich = len(staende) == 1
        alle_da = gleich and all(dict(zip(felder, next(iter(staende)))).get(f) == w for f, w in erwartet.items())
        r = dict(arbeitsplaetze=n, abgleich=_werte(zeiten), gleicher_stand=gleich, alle_feldaenderungen=alle_da,
                 angebote_bei_pc0=len(nummern), doppelte_nummern=len(nummern) - len(set(nummern)),
                 konflikte=sum(len(teilen.konflikte(db)) for db in plaetze))
        print("Abgleich", json.dumps(r, ensure_ascii=False))
        out.append(r)
        for db in plaetze:
            db.schliessen()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angebote", type=int, default=10000)
    ap.add_argument("--benutzer", default="1,5,10,25")
    ap.add_argument("--json")
    ap.add_argument("--nur")
    a = ap.parse_args()
    stufen = [int(x) for x in a.benutzer.split(",")]
    tmp = Path(tempfile.mkdtemp())
    erg = dict(angebote=a.angebote, vorgaenge_je_benutzer=VORGAENGE_JE_BENUTZER)
    try:
        if a.nur in (None, "a"):
            erg["gleichzeitig"] = teil_a(a.angebote, stufen, tmp)
        if a.nur in (None, "b"):
            erg["abgleich"] = teil_b(stufen, tmp)
    finally:
        datenspeicher.alle_stoppen()
        shutil.rmtree(tmp, ignore_errors=True)
    if a.json:
        Path(a.json).write_text(json.dumps(erg, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
