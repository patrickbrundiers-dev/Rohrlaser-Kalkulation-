"""Speicher-Dauerlauf des Rechenkerns (Master-Auftrag Rechenkern 2.0, 24.11.2026, Paket 6). Nur Entwicklung.

Rechnet viele Runden mit jeweils ANDEREN Eingaben (je Runde eine geänderte Teilelänge und Stückzahl), damit jeder
Merker neue Einträge bekommt: optimieren, kalkulieren, Staffeln, Maschinenvergleich. Gemessen wird der
Arbeitsspeicher (RSS) nach jeder Runde. Ein Merker ohne Obergrenze wächst dabei stetig; ein begrenzter bleibt
nach dem Füllen flach. Urteil: Zuwachs in der zweiten Hälfte der Runden je Runde (MB) und gesamt.

Aufruf (PostgreSQL wie im Programm): python werkzeuge/mit_pg.py -- python werkzeuge/speicher_dauerlauf.py
    [--groesse M] [--runden 60] [--json DATEI] [--grenze_mb 0.5]
Rückgabe 1, wenn der Zuwachs je Runde in der zweiten Hälfte über --grenze_mb liegt.
"""
import argparse
import gc
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "tests")]


def rss_mb():
    try:
        with open("/proc/self/statm") as f:
            import os
            return int(f.read().split()[1]) * os.sysconf("SC_PAGE_SIZE") / 1e6
    except OSError:
        from rohrlaser import tempo
        return tempo.speicher_mb() or 0.0


def _behaelter():
    """Länge aller Merker, Wörterbücher und Listen auf Modulebene (auch in Merker-Objekten und Thread-Merkern)."""
    import threading
    out = {}
    for name, mod in list(sys.modules.items()):
        if not (name.startswith("rohrlaser") or name.startswith("step")):
            continue
        for a, v in list(vars(mod).items()):
            ziele = [(a, v)]
            if isinstance(v, threading.local) or hasattr(v, "__dict__") and not isinstance(v, type) \
                    and not callable(v) and type(v).__module__.startswith("rohrlaser"):
                ziele += [(f"{a}.{b}", w) for b, w in list(vars(v).items())]
            for n, w in ziele:
                if isinstance(w, (dict, list, set)):
                    out[f"{name}.{n}"] = len(w)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--groesse", default="M")
    ap.add_argument("--runden", type=int, default=60)
    ap.add_argument("--json")
    ap.add_argument("--grenze_mb", type=float, default=0.5)
    ap.add_argument("--behaelter", action="store_true", help="Merker/Listen der Module: Länge Mitte und Ende")
    ap.add_argument("--spur", action="store_true", help="tracemalloc: größte Zuwächse der zweiten Hälfte je Zeile")
    ap.add_argument("--spur_ab", type=int, default=0, help="tracemalloc erst ab dieser Runde (schneller)")
    x = ap.parse_args(argv)
    import testangebote_gross
    from rohrlaser import maschinen_vergleich, rechnen, staffeln
    from rohrlaser.datenbank import Datenbank
    db = Datenbank(Path(tempfile.mkdtemp()) / "x.db")
    k, tab, einst = db.kontext(), db.tabellen(), db.einstellungen()
    aid = testangebote_gross.anlegen(db, x.groesse)
    kopf, pos0 = db.angebot(aid), db.positionen(aid)
    st = db.staffeln(aid)
    werte, zeiten, schnapp, bloecke = [], [], None, []
    import tracemalloc
    if x.spur and not x.spur_ab:
        tracemalloc.start(8)
    for r in range(x.runden):
        t0 = time.perf_counter()
        pos = [dict(p) for p in pos0]
        p = pos[r % len(pos)]
        p["laenge"] = float(p.get("laenge") or 500) + 0.5 * (r + 1)      # neue Eingabe je Runde
        p["stueck"] = int(p.get("stueck") or 1) + r
        e = rechnen.einstellungen_angebot(kopf, einst)
        erg = rechnen.optimieren(kopf, pos, k, tab, e)
        kp = dict(kopf, ergebnis=erg)
        rechnen.kalkulation(kp, pos, erg, k, tab, e)
        staffeln.rechnen_alle(kp, pos, st, k, tab, e)
        maschinen_vergleich.vergleich(kp, pos, k, tab, einst)
        gc.collect()
        zeiten.append(time.perf_counter() - t0)
        werte.append(rss_mb())
        bloecke.append(sys.getallocatedblocks())
        if x.behaelter and r == x.runden // 2:
            mitte = _behaelter()
        if x.spur and x.spur_ab and r == x.spur_ab:
            tracemalloc.start(8)
        if x.spur and r == max(x.runden // 2, x.spur_ab + 5):
            schnapp = tracemalloc.take_snapshot()
        print(f"Runde {r + 1:3}: {zeiten[-1]:5.2f} s  RSS {werte[-1]:7.1f} MB  Python-Blöcke {bloecke[-1]:9}", flush=True)
    h = len(werte) // 2
    zuwachs = (werte[-1] - werte[h]) / max(1, len(werte) - 1 - h)
    erg = dict(groesse=x.groesse, runden=x.runden, rss_start_mb=round(werte[0], 1), rss_mitte_mb=round(werte[h], 1),
               rss_ende_mb=round(werte[-1], 1),
               bloecke_mitte=bloecke[h], bloecke_ende=bloecke[-1], zuwachs_je_runde_mb=round(zuwachs, 3),
               dauer_median_s=round(statistics.median(zeiten), 3),
               dauer_95_s=round(sorted(zeiten)[min(len(zeiten) - 1, int(0.95 * len(zeiten)))], 3))
    print(json.dumps(erg, ensure_ascii=False))
    if x.behaelter:
        ende = _behaelter()
        diff = sorted(((ende[n] - mitte.get(n, 0), n) for n in ende), reverse=True)[:15]
        for d, n in diff:
            print(f"{d:+8} Einträge  {n} (Mitte {mitte.get(n, 0)}, Ende {ende[n]})")
    if schnapp is not None:
        for st_ in tracemalloc.take_snapshot().compare_to(schnapp, "traceback")[:8]:
            print(f"{st_.size_diff / 1e6:+8.2f} MB  {st_.count_diff:+7} Blöcke")
            for z in st_.traceback.format()[-8:]:
                print("     " + z)
    if x.json:
        Path(x.json).write_text(json.dumps(dict(erg, rss_mb=werte, dauer_s=zeiten), indent=1), encoding="utf-8")
    return 1 if zuwachs > x.grenze_mb else 0


if __name__ == "__main__":
    sys.exit(main())
