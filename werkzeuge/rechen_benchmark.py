"""Leistungsmessung des Rechenkerns alt gegen neu (Master-Prompt Rechenkerne und Systemstabilität, 21.11.2026).

Misst ohne Oberfläche, auf dem Weg des Programms (Datenbank mit Beispiel-Stammdaten, Positionen anlegen,
optimieren, Ergebnis speichern, kalkulieren), je Rechenkern getrennt:
- Optimieren (Schnittplan, optimierung.py), kalt (alle Merker leer) und warm,
- Kalkulation (rechnen.kalkulation) kalt und warm,
- Staffeln (staffeln.rechnen_alle: je Mengenstufe Optimieren + Kalkulation),
- Maschinenvergleich (alle Maschinen),
für die Testangebote S/M/L/XL aus tests/testangebote_gross.py und die 20 Angebote des Regressionstests.

Je Messung: Median der Läufe, CPU-Zeit, RAM-Spitze des Prozesses und ein Fingerabdruck über das ungerundete Ergebnis
(repr). `vergleich` prüft, dass beide Stände je Messung denselben Fingerabdruck haben (bitgleich), und zeigt den
Faktor. Bei einem Unterschied ist der Rückgabewert 1.

Aufruf (PostgreSQL wie in CI über werkzeuge/mit_pg.py, nicht als root):
  python werkzeuge/mit_pg.py -- python werkzeuge/rechen_benchmark.py lauf  BAUM ergebnis.json [--groessen S,M,L,XL]
         [--wdh 3] [--profil ordner]
  python werkzeuge/rechen_benchmark.py vergleich alt.json neu.json [--bericht bericht.md]
BAUM = Wurzel eines Programmstands (z. B. ein git worktree des alten Stands); ohne Angabe dieser Stand.
"""
import argparse
import gc
import hashlib
import json
import os
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent


def _ram_mb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _abdruck(wert):
    return hashlib.blake2b(repr(wert).encode("utf-8", "surrogatepass"), digest_size=8).hexdigest()


def _merker_leeren():
    from rohrlaser import dauermerker, dynamik, optimierung, parallel, rechenmerker, rechnen
    parallel.beenden()          # Hilfsprozesse haben eigene Merker: neu starten, sonst ist „kalt“ halb warm
    rechenmerker.alle_leeren()
    dynamik._FOLGE_MERK.clear()
    for name in ("_ANORDNUNG", "_TRENNSUMME", "_TIEFE"):
        m = getattr(optimierung, name, None)
        if m is not None:
            m.clear()
    if hasattr(optimierung, "merker_leeren"):
        optimierung.merker_leeren()
    m = getattr(rechnen, "_KALK_MERK", None)
    if m is not None:
        m.leeren()
    try:
        dauermerker.einrichten(None)
    except Exception:           # noqa: BLE001 – alter Stand ohne Angebots-Cache
        pass


def _messen(name, fn, wdh, kalt, profil=None):
    zeiten, cpu = [], []
    erg = None
    for i in range(wdh):
        if kalt:
            _merker_leeren()
        gc.collect()
        t, c = time.perf_counter(), time.process_time()
        if profil and i == 0:
            import cProfile
            pr = cProfile.Profile()
            erg = pr.runcall(fn)
            pr.dump_stats(str(Path(profil) / (name.replace(" ", "_").replace("/", "-") + ".prof")))
        else:
            erg = fn()
        zeiten.append(time.perf_counter() - t)
        cpu.append(time.process_time() - c)
    return dict(name=name, n=wdh, median_s=statistics.median(zeiten), min_s=min(zeiten), cpu_s=statistics.median(cpu),
                ram_mb=round(_ram_mb(), 1), abdruck=_abdruck(erg))


def lauf(args):
    baum = Path(args.baum).resolve()
    sys.path[:0] = [str(baum / "programm"), str(HIER.parent / "tests"), str(baum / "tests")]
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import testangebote_gross
    from rohrlaser import maschinen_vergleich, rechnen, staffeln
    from rohrlaser.datenbank import Datenbank
    tmp = Path(tempfile.mkdtemp(prefix="rechen_bm_"))
    db = Datenbank(tmp / "bm.db")
    k, tab, einst = db.kontext(), db.tabellen(), db.einstellungen()
    out = dict(stand=subprocess.run(["git", "-C", str(baum), "log", "-1", "--format=%h %s"], capture_output=True,
                                    text=True).stdout.strip(), kerne=os.cpu_count(), messungen=[])
    if args.profil:
        Path(args.profil).mkdir(parents=True, exist_ok=True)
    for g in args.groessen.split(","):
        aid = testangebote_gross.anlegen(db, g)
        kopf, pos = db.angebot(aid), db.positionen(aid)
        teile = sum(int(p.get("stueck") or 0) for p in pos)
        info = dict(groesse=g, positionen=len(pos), teile=teile)
        wdh = args.wdh if g != "XL" else max(1, args.wdh - 1)

        def opt():
            return rechnen.optimieren(kopf, pos, k, tab, einst)
        m = _messen(f"Optimieren kalt [{g}]", opt, wdh, True, args.profil)
        out["messungen"].append(dict(m, **info))
        from rohrlaser import parallel
        ab, parallel.PARALLEL_AB_TEILE = parallel.PARALLEL_AB_TEILE, 10 ** 12
        try:                    # reiner Rechenkern ohne Hilfsprozesse (CPU-Zeit = Rechenzeit)
            out["messungen"].append(dict(_messen(f"Optimieren kalt, ein Prozess [{g}]", opt, wdh, True), **info))
        finally:
            parallel.PARALLEL_AB_TEILE = ab
        out["messungen"].append(dict(_messen(f"Optimieren warm [{g}]", opt, wdh, False), **info))
        erg = opt()
        db.ergebnis_speichern(aid, erg)
        kopf = db.angebot(aid)
        e = rechnen.einstellungen_angebot(kopf, einst)

        def kalk():
            return rechnen.kalkulation(kopf, pos, kopf["ergebnis"], k, tab, e)
        out["messungen"].append(dict(_messen(f"Kalkulation kalt [{g}]", kalk, wdh, True, args.profil), **info))
        out["messungen"].append(dict(_messen(f"Kalkulation warm [{g}]", kalk, wdh, False), **info))

        def sw():
            return rechnen.stangen_werte(kopf["ergebnis"], kopf, pos, k, tab)
        out["messungen"].append(dict(_messen(f"Stangenwerte kalt [{g}]", sw, wdh, True), **info))
        stufen = db.staffeln(aid)

        def staf():
            return staffeln.rechnen_alle(kopf, pos, stufen, k, tab, e)
        if g != "XL" or args.xl_staffeln:
            out["messungen"].append(dict(_messen(f"Staffeln kalt [{g}]", staf, 1, True, args.profil), **info))

        def mv():
            return maschinen_vergleich.vergleich(kopf, pos, k, tab, einst)
        if g in ("S", "M", "L"):
            out["messungen"].append(dict(_messen(f"Maschinenvergleich kalt [{g}]", mv, 1, True, args.profil), **info))
        for z in out["messungen"][-9:]:
            if z.get("groesse") == g:
                print(f"{z['name']:<34} {z['median_s']:8.3f} s  CPU {z['cpu_s']:7.3f} s  RAM {z['ram_mb']:7.1f} MB  "
                      f"{z['abdruck']}", flush=True)
    db.schliessen()
    Path(args.ergebnis).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def _z(w, st=2):
    return f"{w:.{st}f}".replace(".", ",")


def vergleich(args):
    alt = json.loads(Path(args.alt).read_text(encoding="utf-8"))
    neu = json.loads(Path(args.neu).read_text(encoding="utf-8"))
    a = {m["name"]: m for m in alt["messungen"]}
    zeilen = [f"Alt: {alt['stand']}  ·  Neu: {neu['stand']}", "",
              "| Messung | Positionen | Teile | alt s | neu s | Faktor | RAM alt/neu MB | gleich |",
              "|---|---:|---:|---:|---:|---:|---|---|"]
    fehler = 0
    for m in neu["messungen"]:
        x = a.get(m["name"])
        if x is None:
            continue
        gleich = x["abdruck"] == m["abdruck"]
        fehler += not gleich
        faktor = x["median_s"] / m["median_s"] if m["median_s"] > 0 else 0
        zeilen.append(f"| {m['name']} | {m['positionen']} | {m['teile']} | {_z(x['median_s'])} | {_z(m['median_s'])} | "
                      f"{_z(faktor)} | {x['ram_mb']:.0f} / {m['ram_mb']:.0f} | {'ja' if gleich else '**NEIN**'} |")
    text = "\n".join(zeilen) + "\n"
    print(text)
    if args.bericht:
        Path(args.bericht).write_text(text, encoding="utf-8")
    return 1 if fehler else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="befehl", required=True)
    lp = sub.add_parser("lauf")
    lp.add_argument("baum", nargs="?", default=str(HIER.parent))
    lp.add_argument("ergebnis")
    lp.add_argument("--groessen", default="S,M,L,XL")
    lp.add_argument("--wdh", type=int, default=3)
    lp.add_argument("--profil")
    lp.add_argument("--xl-staffeln", action="store_true")
    vp = sub.add_parser("vergleich")
    vp.add_argument("alt")
    vp.add_argument("neu")
    vp.add_argument("--bericht")
    args = ap.parse_args(argv)
    return lauf(args) if args.befehl == "lauf" else vergleich(args)


if __name__ == "__main__":
    sys.exit(main())
