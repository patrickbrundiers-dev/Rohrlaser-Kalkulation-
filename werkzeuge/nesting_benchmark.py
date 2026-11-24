"""Leistungs- und Qualitätsmessung der Nesting-Engine (Nesting-Arbeitsplatz 2.0, Patrick 24.11.2026).

Misst ohne Oberfläche und ohne Datenbank auf dem Weg der Engine (nesting.alle bzw. nesting.vergleichen):
- Fälle 10, 50, 100, 500 Teile (eine Abmessung, gemischte Längen) und eine große Baugruppe (mehrere Abmessungen,
  zusammen über 1.000 Teile), jeweils mit 6-m-Stange allein und mit 6/12-m-Lieferlängen samt Preisen,
- je Fall: Rechenzeit (Median aus --wdh Läufen, kalt: Merker der Optimierung geleert), Stangen, eingekaufte Länge,
  Ausnutzung, Untergrenze der Stangenzahl (Summe Mindestbedarf / Nutzlänge) und ob das Ergebnis bewiesen optimal ist,
- einen Fingerabdruck über das ungerundete Ergebnis (gleicher Fingerabdruck = bitgleiche Pläne).

Die Teile sind mit festem Startwert zufällig (auf jedem Rechner dieselben). Keine erfundenen Werte: alle Zahlen kommen
aus der Rechnung dieses Programmstands.

Aufruf:
  python werkzeuge/nesting_benchmark.py lauf ergebnis.json [--baum WURZEL] [--wdh 3]
  python werkzeuge/nesting_benchmark.py vergleich alt.json neu.json [--bericht bericht.md]
WURZEL = Wurzel eines Programmstands (z. B. git worktree des alten Stands); ohne Angabe dieser Stand.
"""
import argparse
import hashlib
import json
import random
import statistics
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent

FAELLE = (("10 Teile", 10, 1), ("50 Teile", 50, 1), ("100 Teile", 100, 1), ("500 Teile", 500, 1),
          ("Baugruppe 6 Abmessungen", 1200, 6))
PROFILE = ("QR 40x40x2", "QR 50x30x3", "RR 48,3x2,6", "QR 60x60x4", "RR 33,7x2", "QR 80x40x3")


def _abdruck(wert):
    return hashlib.blake2b(repr(wert).encode("utf-8", "surrogatepass"), digest_size=8).hexdigest()


def gruppen(opt, n_teile, n_abm, seed=24112026):
    """n_teile Teile auf n_abm Abmessungen, je Abmessung Positionen mit 1 … 40 Stück und 120 … 2.900 mm."""
    rnd = random.Random(seed + n_teile * 7 + n_abm)
    out = []
    je = n_teile // n_abm
    for a in range(n_abm):
        g = opt.Gruppe(profil=PROFILE[a % len(PROFILE)], werkstoff="S235", stange=6000, endbeschnitt=10,
                       greiferrest=142, kerf=0.2, abstand=0.0)
        teile, z = [], 0
        while len(teile) < je:
            laenge = round(rnd.uniform(120, 2900), 1)
            n = min(rnd.randint(1, 40), je - len(teile))
            gerade = rnd.random() < 0.8
            for i in range(n):
                teile.append(opt.Teil(zeile=13 + z, pos=10 * (z + 1), artikel=f"A{a}-{z}", nr=i + 1, laenge=laenge,
                                      a_gerade=gerade, b_gerade=gerade, a_schnitt=160, b_schnitt=160))
            z += 1
        g.teile = teile
        out.append(g)
    return out


def _leeren(opt):
    if hasattr(opt, "merker_leeren"):
        opt.merker_leeren()
    for name in ("_ANORDNUNG", "_TRENNSUMME", "_TIEFE"):
        m = getattr(opt, name, None)
        if m is not None:
            m.clear()


def _einmal(ne, opt, gs, laengen):
    _leeren(opt)
    t = time.perf_counter()
    erg = []
    for g in gs:
        g2 = opt.replace(g, teile=list(g.teile))
        # wie der Nesting-Arbeitsplatz (nesting_vergleich): jede Strategie einzeln über nesting.planen
        pl = {s: ne.planen(g2, s, laengen) for s in ("A", "B", "D", "E")}
        pl = {s: p for s, p in pl.items() if p is not None}
        erg.append((g2, pl))
    return time.perf_counter() - t, erg


def lauf(wdh):
    from rohrlaser import nesting as ne, optimierung as opt
    laengen_sets = {"6 m": [ne.Laenge(6000, 60.0)],
                    "6/12 m": [ne.Laenge(6000, 60.0), ne.Laenge(12000, 114.0)]}
    out = []
    for name, n, abm in FAELLE:
        gs = gruppen(opt, n, abm)
        for lname, laengen in laengen_sets.items():
            zeiten, erg = [], None
            for _ in range(wdh):
                z, erg = _einmal(ne, opt, gs, laengen)
                zeiten.append(z)
            je = {}
            for g, pl in erg:
                for s, p in pl.items():
                    w = p.werte
                    d = je.setdefault(s, dict(stangen=0, gekauft_mm=0.0, teile_mm=0.0, einkauf=0.0))
                    d["stangen"] += w["stangen"]
                    d["gekauft_mm"] += w["gekauft_mm"]
                    d["teile_mm"] += w["teile_mm"]
                    d["einkauf"] += w["einkauf"] or 0.0
            untergrenze = sum(opt.untergrenze(opt.replace(g, stange=6000)) for g, _ in erg)
            for d in je.values():
                d["ausnutzung"] = d["teile_mm"] / d["gekauft_mm"] if d["gekauft_mm"] else 0.0
            abdruck = _abdruck([(s, [(lg, [(t.zeile, t.nr, r) for t, r in f], rr) for lg, f, rr in p.stangen])
                                for _, pl in erg for s, p in sorted(pl.items())])
            out.append(dict(fall=name, teile=n, abmessungen=abm, laengen=lname, zeit_s=statistics.median(zeiten),
                            zeiten=zeiten, strategien=je, untergrenze_6m=untergrenze, abdruck=abdruck))
            print(f"{name:26s} {lname:7s} {statistics.median(zeiten):7.2f} s  "
                  + "  ".join(f"{s}:{d['stangen']}/{d['gekauft_mm'] / 1000:.1f}m" for s, d in sorted(je.items()))
                  + f"  UG6m {untergrenze}", flush=True)
    return out


def vergleich(alt, neu, bericht=None):
    a = {(x["fall"], x["laengen"]): x for x in json.loads(Path(alt).read_text(encoding="utf-8"))}
    b = {(x["fall"], x["laengen"]): x for x in json.loads(Path(neu).read_text(encoding="utf-8"))}
    zeilen = ["| Fall | Lieferlängen | vorher [s] | nachher [s] | Faktor | Stangen vorher → nachher (E) | "
              "eingekauft vorher → nachher (E) [m] |", "|---|---|---|---|---|---|---|"]
    for k, x in a.items():
        y = b.get(k)
        if not y:
            continue
        ea, eb = x["strategien"].get("E", {}), y["strategien"].get("E", {})
        zeilen.append(f"| {k[0]} | {k[1]} | {x['zeit_s']:.2f} | {y['zeit_s']:.2f} | "
                      f"{x['zeit_s'] / y['zeit_s'] if y['zeit_s'] else 0:.1f}× | {ea.get('stangen')} → "
                      f"{eb.get('stangen')} | {ea.get('gekauft_mm', 0) / 1000:.1f} → {eb.get('gekauft_mm', 0) / 1000:.1f} |")
    text = "\n".join(zeilen)
    print(text)
    if bericht:
        Path(bericht).write_text(text + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("lauf")
    p1.add_argument("ziel")
    p1.add_argument("--baum", default=str(HIER.parent))
    p1.add_argument("--wdh", type=int, default=3)
    p2 = sub.add_parser("vergleich")
    p2.add_argument("alt")
    p2.add_argument("neu")
    p2.add_argument("--bericht")
    a = ap.parse_args()
    if a.cmd == "lauf":
        sys.path.insert(0, str(Path(a.baum) / "programm"))
        erg = lauf(a.wdh)
        Path(a.ziel).write_text(json.dumps(erg, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        vergleich(a.alt, a.neu, a.bericht)


if __name__ == "__main__":
    main()
