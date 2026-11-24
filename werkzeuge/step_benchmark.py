"""Benchmark und Regressionsvergleich der STEP-Messung (Master-Prompt Patrick 21.11.2026 „Extreme
Performance-Optimierung STEP-Import“, Punkt 5).

Misst jede STEP-Datei mit der STEP-Messung eines Programmstands (eigener Prozess wie STEP-Import.exe) und hält je Datei
fest: Gesamtdauer, Einlesen/Abschluss (ZEITEN-Zeile der Messung), CPU-Zeit, CPU-Auslastung (CPU-Zeit / Dauer) und den
größten Arbeitsspeicher (Spitze eines Messprozesses). Der Vergleich zweier Läufe prüft die UNGERUNDETEN Messwerte
(JSON der Messung, jede Zahl, jeder Text, jede Liste) – Standard ist Toleranz 0, also bitgleich.

Aufruf:
    python werkzeuge/step_benchmark.py lauf BAUM ERGEBNIS DATEI_ODER_ORDNER … [--prozesse 0] [--zeitlimit 600] [--wdh 1]
    python werkzeuge/step_benchmark.py vergleich ERGEBNIS_ALT ERGEBNIS_NEU [--toleranz 0] [--bericht DATEI.md]
    python werkzeuge/step_benchmark.py suite ERGEBNIS [--bericht DATEI.md]

lauf hält je Datei außerdem fest: STEP-Schema (AP203/AP214/AP242) und Größenklasse, Zeit je Schritt (lesen,
umwandeln/heilen, nähen, Struktur, Kopien suchen, Körper messen, Baugruppe auswerten), Körper, Normteile, Fehler und mit
--erwartung die Trefferquote der Erkennung. suite fasst einen Lauf je Schema/Größe und je Datei zusammen.

BAUM ist ein Programmstand (Ordner mit programm/step_messung, z. B. ein zweiter git worktree mit dem alten Stand).
--prozesse 0 = so viele Messprozesse wie im Programm (automatisch), 1 = ein Prozess (reproduzierbare Reihenfolge).
Die Messung hat Zeitbudgets (z. B. Erreichbarkeit 20 s): bei voll ausgelastetem Rechner können einzelne Zusatzfelder
anders ausfallen. Für den Vergleich daher beide Läufe unter gleichen Bedingungen und mit PYTHONHASHSEED=0 machen
(setzt der Lauf selbst).
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

FLUECHTIG = {"erzeugt", "schema_version"}      # Felder ohne Messbedeutung (Zeitpunkt, Programmversion)
ENDUNGEN = (".step", ".stp")
SCHEMAS = (("AP242", ("AP242", "MANAGED_MODEL_BASED")), ("AP214", ("AUTOMOTIVE_DESIGN",)),
           ("AP203", ("CONFIG_CONTROL_DESIGN", "EXPLICIT_DRAUGHTING")))
GROESSEN = ((1, "bis 1 MB"), (10, "1–10 MB"), (50, "10–50 MB"), (None, "über 50 MB"))


def kategorie(p):
    """Art der Datei für die Benchmark-Suite (Master-Auftrag 21.11.2026, Abschnitt Benchmark): STEP-Schema (AP203,
    AP214, AP242 aus FILE_SCHEMA im Kopf), Größenklasse, MB."""
    try:
        with open(p, "rb") as f:
            kopf = f.read(20000).decode("latin-1", "replace").upper()
        mb = Path(p).stat().st_size / 1e6
    except OSError:
        return dict(schema="unlesbar", groesse="", mb=0.0)
    i = kopf.find("FILE_SCHEMA")
    teil = kopf[i:i + 300] if i >= 0 else ""
    schema = next((n for n, merk in SCHEMAS if any(m in teil for m in merk)), "unbekannt" if teil else "kein Kopf")
    groesse = next(t for g, t in GROESSEN if g is None or mb <= g)
    return dict(schema=schema, groesse=groesse, mb=round(mb, 2))


def kennzahlen(js, erwartung=None):
    """Zahlen aus dem JSON der Messung: Körper, Fehler (Körper mit Fehler oder Datei nicht lesbar), Normteile (laut
    Name oder Form erkannt), Baugruppe; mit erwartung {Körpernummer: Art} die Trefferquote der Erkennung
    (bauteiltyp/profiltyp, Klassifikationsgenauigkeit)."""
    d = _lade(js)
    dateien = d.get("dateien") or []
    koerper = [k for f in dateien for k in (f.get("koerper") or [])]
    fehler = sum(1 for f in dateien if f.get("fehler")) + sum(1 for k in koerper if k.get("fehler"))
    normteile = sum(1 for k in koerper if str(k.get("art_grund") or "").startswith(("Normteil", "Norm ")))
    out = dict(koerper_n=len(koerper), fehler_n=fehler, normteile_n=normteile,
               baugruppe=any(f.get("baugruppe") for f in dateien))
    if erwartung:
        nach_nr = {str(k.get("nr")): k for k in koerper}
        treffer = sum(1 for nr, art in erwartung.items() if art in (
            (nach_nr.get(str(nr)) or {}).get("bauteiltyp"), (nach_nr.get(str(nr)) or {}).get("profiltyp")))
        out.update(erwartet_n=len(erwartung), treffer_n=treffer)
    return out


def dateien(pfade):
    out = []
    for p in map(Path, pfade):
        if p.is_dir():
            out.extend(sorted(q for q in p.rglob("*") if q.suffix.lower() in ENDUNGEN))
        elif p.suffix.lower() in ENDUNGEN:
            out.append(p)
    return out


def _name(p, basis):
    try:
        rel = p.resolve().relative_to(basis.resolve())
    except ValueError:
        rel = Path(p.name)
    return str(rel).replace(os.sep, "__").replace("/", "__")


def _starten(befehl, umgebung, zeitlimit):
    """Prozess starten und mit os.wait4 warten: (Rückgabe, Dauer s, CPU-Zeit s, RAM-Spitze MB, Ausgabe)."""
    t0 = time.perf_counter()
    p = subprocess.Popen(befehl, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=umgebung)
    ausgabe = []
    try:
        for zeile in p.stdout:
            ausgabe.append(zeile.decode("utf-8", "replace"))
            if time.perf_counter() - t0 > zeitlimit:
                p.kill()
                break
    finally:
        p.stdout.close()
    cpu = ram = 0.0
    try:
        _, status, ru = os.wait4(p.pid, 0)
        rc = os.waitstatus_to_exitcode(status)
        # wait4: CPU-Zeit und RAM-Spitze des Messprozesses samt seiner beendeten Messprozesse (Linux: KB)
        cpu = ru.ru_utime + ru.ru_stime
        ram = ru.ru_maxrss / 1024.0
    except (ChildProcessError, AttributeError):       # Windows: nur Dauer
        rc = p.wait()
    return rc, time.perf_counter() - t0, cpu, ram, "".join(ausgabe)


def lauf(baum, ergebnis, pfade, prozesse=0, zeitlimit=600, gesamt_max=3600, erwartung=None, wdh=1):
    baum, ergebnis = Path(baum), Path(ergebnis)
    messen = baum / "programm" / "step_messung" / "step_messen.py"
    if not messen.exists():
        raise SystemExit(f"{messen} fehlt – BAUM muss ein Programmstand sein")
    ergebnis.mkdir(parents=True, exist_ok=True)
    liste = dateien(pfade)
    basis = Path(os.path.commonpath([str(p.resolve().parent) for p in liste])) if liste else Path(".")
    umgebung = dict(os.environ, PYTHONHASHSEED="0", PYTHONDONTWRITEBYTECODE="1")
    werte = {}
    for p in liste:
        n = _name(p, basis)
        js, txt, netze = ergebnis / f"{n}.json", ergebnis / f"{n}.txt", ergebnis / f"{n}_netze"
        netze.mkdir(exist_ok=True)
        befehl = [sys.executable, str(messen), "--ausgabe", str(txt), "--json", str(js), "--netze", str(netze),
                  "--prozesse", str(prozesse), "--zeitlimit", str(zeitlimit), str(p)]
        # wdh > 1 (Master-Auftrag 24.11.2026): jede Datei mehrmals, Dauer = Median, dazu 90 %/95 % und längster Lauf;
        # jede Wiederholung muss dieselben Messwerte liefern (sonst ist die Messung nicht reproduzierbar)
        laeufe, abdruck = [], None
        for i in range(max(1, wdh)):
            laeufe.append(_starten(befehl, umgebung, gesamt_max))
            if wdh > 1 and js.exists():
                d = _lade(js)
                for f in FLUECHTIG:
                    d.pop(f, None)
                jetzt = json.dumps(d, sort_keys=True, ensure_ascii=False)
                if abdruck is not None and jetzt != abdruck:
                    print(f"NICHT REPRODUZIERBAR: {n} Lauf {i + 1}", flush=True)
                abdruck = jetzt
        dauern = sorted(x[1] for x in laeufe)
        rc, _, cpu, ram, aus = laeufe[-1]
        dauer = statistics.median(dauern)
        cpu = statistics.median(x[2] for x in laeufe)
        ram = max(x[3] for x in laeufe)
        zeiten = next((json.loads(z[7:]) for z in reversed(aus.splitlines()) if z.startswith("ZEITEN ")), {})
        teil = (zeiten.get("dateien") or {}).get(p.name) or {}
        werte[n] = dict(datei=str(p), rc=rc, dauer_s=round(dauer, 3), cpu_s=round(cpu, 3),
                        cpu_auslastung=round(cpu / dauer, 2) if dauer > 0 else 0, ram_mb=round(ram, 1),
                        lesen_s=teil.get("lesen"), abschluss_s=teil.get("abschluss"),
                        koerper_s=zeiten.get("koerper_s"), koerper=zeiten.get("koerper_n"),
                        schritte=teil.get("schritte") or {}, **kategorie(p), **_perzentile(dauern),
                        **kennzahlen(js, (erwartung or {}).get(p.name)))
        print(f"{dauer:8.1f} s  CPU {cpu:8.1f} s  RAM {ram:7.0f} MB  rc {rc}  {n}", flush=True)
    (ergebnis / "benchmark.json").write_text(json.dumps(werte, indent=1, ensure_ascii=False), encoding="utf-8")
    return werte


def _perzentile(dauern):
    """Läufe, 90 %/95 % (linear wie rohrlaser.leistung.perzentil) und längster Lauf einer Datei."""
    w = sorted(dauern)

    def p(q):
        r = (len(w) - 1) * q / 100.0
        i = int(r)
        return w[-1] if i >= len(w) - 1 else w[i] + (w[i + 1] - w[i]) * (r - i)
    return dict(laeufe=len(w), p90_s=round(p(90), 3), p95_s=round(p(95), 3), max_s=round(w[-1], 3))


def unterschiede(a, b, toleranz=0.0, pfad=""):
    """Alle Unterschiede zweier JSON-Werte als [(Pfad, alt, neu)]; Zahlen gelten bei |a−b| ≤ toleranz·max(1,|a|,|b|)
    als gleich (toleranz 0 = bitgleich). Flüchtige Felder (Zeitpunkt, Version) zählen nicht."""
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k in FLUECHTIG:
                continue
            if k not in a:
                out.append((f"{pfad}.{k}", "—", b[k]))
            elif k not in b:
                out.append((f"{pfad}.{k}", a[k], "—"))
            else:
                out.extend(unterschiede(a[k], b[k], toleranz, f"{pfad}.{k}"))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append((f"{pfad}[Anzahl]", len(a), len(b)))
        for i, (x, y) in enumerate(zip(a, b)):
            out.extend(unterschiede(x, y, toleranz, f"{pfad}[{i}]"))
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) \
            and not isinstance(b, bool):
        if a != b and abs(a - b) > toleranz * max(1.0, abs(a), abs(b)):
            out.append((pfad, a, b))
    elif a != b or isinstance(a, bool) != isinstance(b, bool):      # True und 1 sind nicht dasselbe Messergebnis
        out.append((pfad, a, b))
    return out


def _lade(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"_fehler": f"{type(e).__name__}: {e}"}


def vergleich(alt, neu, toleranz=0.0, bericht=None):
    """Messwerte und Zeiten zweier Läufe vergleichen; Ergebnis dict(gleich, anders, fehlt, zeilen, faktor)."""
    alt, neu = Path(alt), Path(neu)
    za, zn = _lade(alt / "benchmark.json"), _lade(neu / "benchmark.json")
    gleich, anders, fehlt, zeilen = [], {}, [], []
    for p in sorted(alt.glob("*.json")):
        if p.name == "benchmark.json":
            continue
        q = neu / p.name
        if not q.exists():
            fehlt.append(p.name)
            continue
        u = unterschiede(_lade(p), _lade(q), toleranz)
        (anders.__setitem__(p.name, u) if u else gleich.append(p.name))
        n = p.name[:-5]
        a, b = za.get(n) or {}, zn.get(n) or {}
        zeilen.append(dict(datei=n, alt_s=a.get("dauer_s"), neu_s=b.get("dauer_s"), alt_ram=a.get("ram_mb"),
                           neu_ram=b.get("ram_mb"), alt_cpu=a.get("cpu_auslastung"), neu_cpu=b.get("cpu_auslastung"),
                           gleich=not u))
    summe_a = sum(z["alt_s"] or 0 for z in zeilen)
    summe_n = sum(z["neu_s"] or 0 for z in zeilen)
    erg = dict(gleich=len(gleich), anders={k: v[:50] for k, v in anders.items()}, fehlt=fehlt, zeilen=zeilen,
               alt_s=round(summe_a, 1), neu_s=round(summe_n, 1),
               faktor=round(summe_a / summe_n, 2) if summe_n else None)
    if bericht:
        Path(bericht).write_text(_markdown(erg, toleranz), encoding="utf-8")
    return erg


def _markdown(e, toleranz):
    t = ["# STEP-Benchmark", "", f"Messwerte gleich: **{e['gleich']}**, anders: **{len(e['anders'])}**, fehlen: "
         f"{len(e['fehlt'])} (Toleranz {toleranz:g}).", "", f"Summe alt {e['alt_s']} s, neu {e['neu_s']} s, "
         f"Faktor **{e['faktor']}**.", "", "| Datei | alt s | neu s | Faktor | RAM alt/neu MB | gleich |",
         "|---|---:|---:|---:|---:|---|"]
    for z in sorted(e["zeilen"], key=lambda z: -(z["alt_s"] or 0)):
        f = round(z["alt_s"] / z["neu_s"], 2) if z["alt_s"] and z["neu_s"] else ""
        t.append(f"| {z['datei']} | {z['alt_s']} | {z['neu_s']} | {f} | {z['alt_ram']} / {z['neu_ram']} | "
                 f"{'ja' if z['gleich'] else '**nein**'} |")
    for n, u in e["anders"].items():
        t += ["", f"## {n}"] + [f"- `{p}`: {str(a)[:80]} → {str(b)[:80]}" for p, a, b in u[:20]]
    return "\n".join(t) + "\n"


SCHRITTE = (("lesen_s", "STEP lesen"), ("uebertragen_s", "umwandeln/heilen"), ("naehen_s", "nähen"),
            ("struktur_s", "Struktur"), ("kopien_s", "Kopien suchen"), ("messen_s", "Körper messen"),
            ("abschluss_s", "Baugruppe auswerten"))


def suite(ergebnis, bericht=None):
    """Bericht eines Laufs als Benchmark-Suite: je Datei Gesamtzeit, Zeit je Schritt, RAM-Spitze, CPU, Körper,
    Normteile, Fehler, Trefferquote; Summen je STEP-Schema und Größenklasse. Ergebnis: Markdown-Text."""
    w = _lade(Path(ergebnis) / "benchmark.json")
    w = {k: v for k, v in w.items() if isinstance(v, dict)}
    t = ["# STEP-Benchmark-Suite", "", f"{len(w)} Dateien, Summe {sum(v.get('dauer_s') or 0 for v in w.values()):.1f} s.",
         "", "## Je Schema und Größe", "", "| Schema | Größe | Dateien | Körper | Normteile | Fehler | Summe s | RAM max MB |",
         "|---|---|---:|---:|---:|---:|---:|---:|"]
    gruppen = {}
    for v in w.values():
        gruppen.setdefault((v.get("schema", "?"), v.get("groesse", "?")), []).append(v)
    for (sch, gr), vs in sorted(gruppen.items()):
        t.append(f"| {sch} | {gr} | {len(vs)} | {sum(v.get('koerper_n') or 0 for v in vs)} | "
                 f"{sum(v.get('normteile_n') or 0 for v in vs)} | {sum(v.get('fehler_n') or 0 for v in vs)} | "
                 f"{sum(v.get('dauer_s') or 0 for v in vs):.1f} | {max(v.get('ram_mb') or 0 for v in vs):.0f} |")
    t += ["", "## Je Datei", "", "| Datei | Schema | MB | s | CPU | RAM MB | Körper | Normteile | Fehler | Treffer | "
          + " | ".join(n for _, n in SCHRITTE) + " |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"
          + "---:|" * len(SCHRITTE)]
    for n, v in sorted(w.items(), key=lambda x: -(x[1].get("dauer_s") or 0)):
        sch = v.get("schritte") or {}
        treffer = f"{v['treffer_n']}/{v['erwartet_n']}" if v.get("erwartet_n") else ""
        t.append(f"| {n} | {v.get('schema', '')} | {v.get('mb', '')} | {v.get('dauer_s')} | {v.get('cpu_auslastung')} | "
                 f"{v.get('ram_mb')} | {v.get('koerper_n', '')} | {v.get('normteile_n', '')} | {v.get('fehler_n', '')} | "
                 f"{treffer} | " + " | ".join(f"{sch[k]:.2f}" if isinstance(sch.get(k), (int, float)) else ""
                                               for k, _ in SCHRITTE) + " |")
    erw = [v for v in w.values() if v.get("erwartet_n")]
    if erw:
        a, b = sum(v["treffer_n"] for v in erw), sum(v["erwartet_n"] for v in erw)
        t += ["", f"Erkennung: {a} von {b} Körpern wie erwartet ({100 * a / b:.1f} %)."]
    text = "\n".join(t) + "\n"
    if bericht:
        Path(bericht).write_text(text, encoding="utf-8")
    return text


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="befehl", required=True)
    a = sub.add_parser("lauf")
    a.add_argument("baum")
    a.add_argument("ergebnis")
    a.add_argument("pfade", nargs="+")
    a.add_argument("--prozesse", type=int, default=0)
    a.add_argument("--zeitlimit", type=int, default=600)
    a.add_argument("--erwartung", help="JSON {Dateiname: {Körpernummer: Art}} für die Trefferquote der Erkennung")
    a.add_argument("--wdh", type=int, default=1, help="Läufe je Datei (Median, 95 %%, längster Lauf)")
    s = sub.add_parser("suite")
    s.add_argument("ergebnis")
    s.add_argument("--bericht")
    v = sub.add_parser("vergleich")
    v.add_argument("alt")
    v.add_argument("neu")
    v.add_argument("--toleranz", type=float, default=0.0)
    v.add_argument("--bericht")
    x = ap.parse_args(argv)
    if x.befehl == "lauf":
        erw = json.loads(Path(x.erwartung).read_text(encoding="utf-8")) if x.erwartung else None
        lauf(x.baum, x.ergebnis, x.pfade, x.prozesse, x.zeitlimit, erwartung=erw, wdh=x.wdh)
        return 0
    if x.befehl == "suite":
        print(suite(x.ergebnis, x.bericht))
        return 0
    e = vergleich(x.alt, x.neu, x.toleranz, x.bericht)
    print(f"gleich {e['gleich']}, anders {len(e['anders'])}, fehlen {len(e['fehlt'])}; "
          f"Summe {e['alt_s']} s -> {e['neu_s']} s (Faktor {e['faktor']})")
    for n, u in e["anders"].items():
        print("==", n, len(u))
        for p, alt, neu in u[:8]:
            print("   ", p, "|", str(alt)[:70], "->", str(neu)[:70])
    return 1 if e["anders"] or e["fehlt"] else 0


if __name__ == "__main__":
    sys.exit(main())
