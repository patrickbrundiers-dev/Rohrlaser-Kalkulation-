"""Vergleich bisherige Rechnung gegen Abwicklungskern (Master-Auftrag Patrick 24.11.2026, Abschnitte 3 und 8).

Misst jede STEP-Datei zweimal im selben Prozess (Modus aus = bisher, an = Abwicklungskern mit automatischem Rückfall)
und vergleicht jedes Teil (Profil, Maße, Schneidweg je Ende/innen, jede Kontur, Hinweise, geschlossenes Rohr,
Alternative) mit den Toleranzen aus step_abwicklungskern (0,01 mm bzw. 1e-5 relativ). Dazu Zeit je Datei und Modus,
Methode je Körper (Abwicklung / Rückfall mit Grund) und Zeitanteile (Lage, Schnitte).

Aufruf:
    python werkzeuge/abwicklungskern_vergleich.py DATEI_ODER_ORDNER … [--json ERGEBNIS.json] [--bericht BERICHT.md]
        [--wdh N]

--wdh N: jede Messung N-mal, gezählt wird der Median (Zeiten schwanken um etwa ±10 %).
--soll-schreiben SOLL.json [--soll-modus an|aus]: Prüfbasis (Plan Abwicklungskern 2.0, N7) schreiben = Sollwerte
    jedes Teils (Vorgabe Modus an = abgenommener Stand; aus = bisherige Rechnung). Nur nach einer abgenommenen,
    bewusst geänderten Messung neu schreiben; die Änderung der Datei zeigt dann im PR jede geänderte Messung.
--soll SOLL.json: Abnahme = nur Modus an messen und gegen die Prüfbasis vergleichen (halbe Laufzeit). Der Bericht
    nennt Kernquote, Rückfall-Gründe, Vertrauenswerte, Abweichungen und Zeit.
Rückgabewert 0 = alle Teile gleich, 1 = mindestens ein Unterschied.
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "programm" / "step_messung"))
import step_abwicklungskern as ak  # noqa: E402
import step_geometrie as g  # noqa: E402

ENDUNGEN = (".step", ".stp")


def dateien(pfade):
    out = []
    for p in map(Path, pfade):
        if p.is_dir():
            out += sorted(q for q in p.rglob("*") if q.suffix.lower() in ENDUNGEN)
        elif p.suffix.lower() in ENDUNGEN:
            out.append(p)
    return out


def messen(pfad, modus, wdh=1):
    """(Teile, Median-Dauer s, Protokoll des letzten Laufs)."""
    ak.modus_setzen(modus)
    zeiten, teile, prot = [], None, []
    for _ in range(wdh):
        n0 = len(ak.PROTOKOLL)
        uhr = time.perf_counter()
        teile = g.analysiere_datei(str(pfad))
        zeiten.append(time.perf_counter() - uhr)
        prot = ak.PROTOKOLL[n0:]
    del ak.PROTOKOLL[:]
    return teile, statistics.median(zeiten), prot


def datei_vergleich(pfad, wdh=1, basis=None, soll=None):
    """soll: Sollwerte der Datei aus der Prüfbasis (Liste je Teil) statt der bisherigen Rechnung."""
    name = Path(pfad).relative_to(basis).as_posix() if basis else Path(pfad).name
    try:
        if soll is None:
            alt, t_alt, _ = messen(pfad, "aus", wdh)
        else:
            alt, t_alt = [ak.soll_teil(d) for d in soll], 0.0
        neu, t_neu, prot = messen(pfad, "an", wdh)
    except Exception as e:  # nicht lesbare Prüfdateien (defekt, leer) sind gewollt
        return dict(datei=name, fehler=f"{type(e).__name__}: {e}")
    unterschiede = []
    if len(alt) != len(neu):
        unterschiede.append(["teile", len(alt), len(neu)])
    for a, b in zip(alt, neu):
        unterschiede += [[f"K{a.koerper}.{n}", repr(x)[:160], repr(y)[:160]] for n, x, y in ak.vergleichen(a, b)]
    methoden = [dict(koerper=e["koerper"], quer=e["quer"], methode=e["methode"], grund=e.get("grund", ""),
                     vertrauen=e.get("vertrauen")) for e in prot]
    return dict(datei=name, alt_s=round(t_alt, 3), neu_s=round(t_neu, 3), teile=len(alt), gleich=not unterschiede,
                unterschiede=unterschiede, methoden=methoden)


def soll_schreiben(pfade, ziel, basis=None, modus="an"):
    """Prüfbasis: {Datei: [Sollwerte je Teil]} im Modus modus."""
    soll = {}
    for p in dateien(pfade):
        name = p.relative_to(basis).as_posix() if basis else p.name
        try:
            teile, _, _ = messen(p, modus)
        except Exception:   # nicht lesbare Prüfdateien: keine Sollwerte
            continue
        soll[name] = [ak.sollwerte(t) for t in teile]
        print(name, len(teile), flush=True)
    Path(ziel).write_text(json.dumps(soll, ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
    return soll


def bericht(erg):
    ok = [e for e in erg if "fehler" not in e]
    alt, neu = sum(e["alt_s"] for e in ok), sum(e["neu_s"] for e in ok)
    m = [x for e in ok for x in e["methoden"]]
    abw = sum(1 for x in m if x["methode"] == "abwicklung")
    gruende = {}
    for x in m:
        if x["methode"] != "abwicklung":
            gruende[x["grund"]] = gruende.get(x["grund"], 0) + 1
    z = ["# Abwicklungskern: Vergleich bisher / neu", "",
         f"Dateien {len(erg)} (davon nicht lesbar {len(erg) - len(ok)}), Teile gleich in "
         f"{sum(1 for e in ok if e['gleich'])} von {len(ok)} Dateien.", "",
         (f"Summe bisher {alt:.1f} s, neu {neu:.1f} s, Faktor {alt / neu if neu else 0:.2f}." if alt else
          f"Abnahme gegen die Prüfbasis: Summe {neu:.1f} s."), "",
         f"Profilmessungen {len(m)}: Abwicklungskern {abw}, Rückfall {len(m) - abw} "
         f"(Kernquote {abw / len(m) if m else 0:.0%}).", "",
         "Vertrauen der Kern-Messungen: " + ", ".join(
             f"{v}: {sum(1 for x in m if x['methode'] == 'abwicklung' and x.get('vertrauen') == v)}"
             for v in sorted({x.get("vertrauen") for x in m if x["methode"] == "abwicklung"}, key=str)) + ".", "",
         "| Rückfall-Grund | Anzahl |", "|---|---:|"]
    z += [f"| {k} | {v} |" for k, v in sorted(gruende.items(), key=lambda x: -x[1])]
    z += ["", "| Datei | bisher s | neu s | Faktor | gleich | Methoden |", "|---|---:|---:|---:|---|---|"]
    for e in ok:
        f = e["alt_s"] / e["neu_s"] if e["neu_s"] else 0
        meth = ", ".join(sorted({("A" if x["methode"] == "abwicklung" else "B") + ("q" if x["quer"] else "")
                                 for x in e["methoden"]}))
        z.append(f"| {e['datei']} | {e['alt_s']:.2f} | {e['neu_s']:.2f} | {f:.2f} | "
                 f"{'ja' if e['gleich'] else 'NEIN'} | {meth} |")
    abw_ = [e for e in ok if not e["gleich"]]
    if abw_:
        z += ["", "## Unterschiede", ""]
        for e in abw_:
            z.append(f"- {e['datei']}: " + "; ".join(f"{n}: {a} → {b}" for n, a, b in e["unterschiede"][:6]))
    z += ["", "Methoden: A = Abwicklungskern, B = bisherige Rechnung (Rückfall), q = Messung als geschlossenes Rohr "
          "(offen gezeichnete Rohre)."]
    return "\n".join(z) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pfade", nargs="+")
    ap.add_argument("--json")
    ap.add_argument("--bericht")
    ap.add_argument("--wdh", type=int, default=1)
    ap.add_argument("--soll-schreiben")
    ap.add_argument("--soll-modus", choices=("an", "aus"), default="an")
    ap.add_argument("--soll")
    x = ap.parse_args(argv)
    ak.stichprobe_setzen(0)     # Abnahme misst den Kern selbst, ohne Dauer-Vergleich
    basis = Path(x.pfade[0]) if Path(x.pfade[0]).is_dir() else None
    if x.soll_schreiben:
        soll_schreiben(x.pfade, x.soll_schreiben, basis, x.soll_modus)
        return 0
    soll = json.loads(Path(x.soll).read_text(encoding="utf-8")) if x.soll else None
    erg = []
    for p in dateien(x.pfade):
        name = p.relative_to(basis).as_posix() if basis else p.name
        if soll is not None and name not in soll:
            continue        # ohne Sollwerte (nicht lesbar oder neu): nicht Teil der Abnahme
        e = datei_vergleich(p, x.wdh, basis=basis, soll=soll[name] if soll is not None else None)
        erg.append(e)
        print(e["datei"], e.get("alt_s", ""), e.get("neu_s", ""), "gleich" if e.get("gleich") else
              e.get("fehler") or e.get("unterschiede", [])[:2], flush=True)
    if x.json:
        Path(x.json).write_text(json.dumps(erg, ensure_ascii=False, indent=1), encoding="utf-8")
    if x.bericht:
        Path(x.bericht).write_text(bericht(erg), encoding="utf-8")
    return 0 if all(e.get("gleich", True) for e in erg) else 1


if __name__ == "__main__":
    sys.exit(main())
