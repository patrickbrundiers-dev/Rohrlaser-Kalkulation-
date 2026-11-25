"""Fehlerresistenz der STEP-Messung (Master-Auftrag Rechenkern 2.0, 24.11.2026, Paket 4). Nur Entwicklung.

Erzeugt aus guten STEP-Dateien beschädigte Fassungen und misst jede mit der STEP-Messung wie im Programm (eigener
Prozess, mit Zeitlimit je Körper). Geprüft wird, dass nichts hängt oder abstürzt, ohne dass es gemeldet wird:
- jede Messung endet innerhalb des Gesamtlimits,
- es entsteht ein JSON-Ergebnis (bei unlesbaren Dateien mit Fehlertext statt leerem Ergebnis),
- in einer Baugruppe mit einem beschädigten Körper werden die übrigen Körper weiter gemessen.

Beschädigungen (alle reproduzierbar, fester Zufallsstartwert):
  abgeschnitten_50 / abgeschnitten_90   Datei nach 50 % bzw. 90 % abgeschnitten (Übertragung abgebrochen)
  zeilen_weg                            jede 7. Zeile im DATA-Teil gelöscht (Verweise ins Leere)
  bytes_kippen                          200 zufällige Bytes im DATA-Teil verändert
  zahlen_unsinn                         jede 5. Koordinate durch 1.E308 bzw. 0.0 ersetzt
  ohne_kopf                             HEADER-Teil fehlt
  binaer                                Datei nur aus Zufallsbytes, Endung .step
  doppelte_nummern                      jede 10. Entität bekommt die Nummer der vorigen
  ein_koerper_kaputt (nur Baugruppen)   Punkte eines einzelnen Körpers unbrauchbar, Rest unverändert

Aufruf: python werkzeuge/step_robust.py ERGEBNISORDNER DATEI.step … [--zeitlimit 60] [--gesamt 300]
Ausgabe: Tabelle je Datei und Beschädigung (Dauer, Rückgabe, Körper gesamt/gemessen/mit Fehler, Urteil) und
ERGEBNISORDNER/robust.json; Rückgabe 1, wenn eine Messung hängt oder ohne Ergebnis endet.
"""
import argparse
import json
import random
import re
import subprocess
import sys
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
MESSEN = HIER.parent / "programm" / "step_messung" / "step_messen.py"


def _teile(text):
    i = text.find("DATA;")
    j = text.rfind("ENDSEC;")
    return (text[:i + 5], text[i + 5:j], text[j:]) if i >= 0 and j > i else (text, "", "")


def beschaedigen(text, art, zufall):
    kopf, data, ende = _teile(text)
    if art == "abgeschnitten_50":
        return text[:len(text) // 2]
    if art == "abgeschnitten_90":
        return text[:len(text) * 9 // 10]
    if art == "zeilen_weg":
        z = data.split("\n")
        return kopf + "\n".join(x for i, x in enumerate(z) if i % 7 != 3) + ende
    if art == "bytes_kippen":
        d = list(data)
        for _ in range(min(200, len(d))):
            d[zufall.randrange(len(d))] = chr(zufall.choice(b"()#,;'=0123456789.E-$*ABCXYZ\x00\xff"))
        return kopf + "".join(d) + ende
    if art == "zahlen_unsinn":
        n = [0]

        def ers(m):
            n[0] += 1
            return ("1.E308" if n[0] % 2 else "0.") if n[0] % 5 == 0 else m.group(0)
        return kopf + re.sub(r"-?\d+\.\d*(?:E[-+]?\d+)?", ers, data) + ende
    if art == "ohne_kopf":
        i = text.find("DATA;")
        return "ISO-10303-21;\n" + text[i:] if i >= 0 else text
    if art == "doppelte_nummern":
        z = data.split("\n")
        letzte = None
        for i, x in enumerate(z):
            m = re.match(r"#(\d+)\s*=", x)
            if m:
                if letzte is not None and i % 10 == 0:
                    z[i] = x.replace(f"#{m.group(1)}", f"#{letzte}", 1)
                letzte = m.group(1)
        return kopf + "\n".join(z) + ende
    raise ValueError(art)


def ein_koerper_kaputt(text):
    """Die Punkte (CARTESIAN_POINT) des ersten MANIFOLD_SOLID_BREP-Körpers unbrauchbar machen: alle Entitäten, die
    nur von diesem Körper erreicht werden, bekommen NaN-artige Koordinaten (1.E308). None, wenn die Datei nur einen
    Körper hat."""
    kopf, data, ende = _teile(text)
    ent = {}
    for m in re.finditer(r"#(\d+)\s*=\s*(.*?);\s*(?=#\d+\s*=|\Z)", data, re.S):
        ent[int(m.group(1))] = m.group(2)
    koerper = [n for n, t in ent.items() if t.lstrip().startswith("MANIFOLD_SOLID_BREP")]
    if len(koerper) < 2:
        return None

    def erreichbar(start):
        seen, st = set(), [start]
        while st:
            n = st.pop()
            if n in seen or n not in ent:
                continue
            seen.add(n)
            st.extend(int(x) for x in re.findall(r"#(\d+)", ent[n]))
        return seen
    andere = set()
    for k in koerper[1:]:
        andere |= erreichbar(k)
    nur = erreichbar(koerper[0]) - andere
    punkte = {n for n in nur if ent[n].lstrip().startswith("CARTESIAN_POINT")}
    if not punkte:
        return None

    def ers(m):
        n = int(m.group(1))
        if n in punkte:
            return f"#{n}=CARTESIAN_POINT('',(1.E308,-1.E308,1.E308));"
        return m.group(0)
    return kopf + re.sub(r"#(\d+)\s*=\s*CARTESIAN_POINT\s*\([^;]*\);", ers, data) + ende


ARTEN = ("abgeschnitten_50", "abgeschnitten_90", "zeilen_weg", "bytes_kippen", "zahlen_unsinn", "ohne_kopf",
         "doppelte_nummern")


def messen(datei, ordner, zeitlimit, gesamt):
    js, txt = ordner / (datei.name + ".json"), ordner / (datei.name + ".txt")
    befehl = [sys.executable, str(MESSEN), "--ausgabe", str(txt), "--json", str(js), "--prozesse", "0",
              "--zeitlimit", str(zeitlimit), str(datei)]
    t0 = time.perf_counter()
    try:
        p = subprocess.run(befehl, capture_output=True, timeout=gesamt, env=None)
        rc, haengt = p.returncode, False
    except subprocess.TimeoutExpired:
        rc, haengt = None, True
    dauer = time.perf_counter() - t0
    d = None
    if js.exists():
        try:
            d = json.loads(js.read_text(encoding="utf-8"))
        except ValueError:
            d = None
    return dauer, rc, haengt, d


def auswerten(d):
    """(Körper gesamt, gemessen ohne Fehler, mit Fehler, Fehlertext der Datei)"""
    if not isinstance(d, dict):
        return 0, 0, 0, ""
    teile = d.get("teile") or d.get("koerper") or []
    if isinstance(d.get("dateien"), list):
        teile = [t for f in d["dateien"] for t in (f.get("teile") or f.get("koerper") or [])]
    fehler = sum(1 for t in teile if isinstance(t, dict) and t.get("fehler"))
    datei_fehler = ""
    for f in d.get("dateien") or []:
        if isinstance(f, dict) and f.get("fehler"):
            datei_fehler = str(f["fehler"])[:80]
    return len(teile), len(teile) - fehler, fehler, datei_fehler


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("ergebnis")
    ap.add_argument("dateien", nargs="+")
    ap.add_argument("--zeitlimit", type=int, default=60)
    ap.add_argument("--gesamt", type=int, default=300)
    ap.add_argument("--arten", default=",".join(ARTEN + ("binaer", "ein_koerper_kaputt")))
    x = ap.parse_args(argv)
    aus = Path(x.ergebnis)
    aus.mkdir(parents=True, exist_ok=True)
    arten = x.arten.split(",")
    zeilen, schlecht = [], 0
    for q in map(Path, x.dateien):
        text = q.read_text(encoding="latin-1")
        for art in arten:
            zufall = random.Random(f"{q.name}:{art}")
            if art == "binaer":
                neu = bytes(zufall.randrange(256) for _ in range(50000))
            elif art == "ein_koerper_kaputt":
                t = ein_koerper_kaputt(text)
                if t is None:
                    continue
                neu = t.encode("latin-1")
            else:
                neu = beschaedigen(text, art, zufall).encode("latin-1", "replace")
            ordner = aus / f"{q.stem}__{art}"
            ordner.mkdir(exist_ok=True)
            datei = ordner / f"{q.stem}__{art}.step"
            datei.write_bytes(neu)
            dauer, rc, haengt, d = messen(datei, ordner, x.zeitlimit, x.gesamt)
            n, gut, fehl, dfehl = auswerten(d)
            ok = not haengt and d is not None
            schlecht += not ok
            zeilen.append(dict(datei=q.name, art=art, dauer_s=round(dauer, 1), rc=rc, haengt=haengt,
                               ergebnis=d is not None, koerper=n, gemessen=gut, fehler=fehl, datei_fehler=dfehl,
                               urteil="ok" if ok else "FEHLER"))
            print(f"{q.name[:34]:34} {art:20} {dauer:6.1f} s rc {rc!s:4} Körper {n:3} gemessen {gut:3} "
                  f"Fehler {fehl:3} {'OK' if ok else 'FEHLER (hängt)' if haengt else 'FEHLER (kein Ergebnis)'} "
                  f"{dfehl}", flush=True)
    (aus / "robust.json").write_text(json.dumps(zeilen, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(zeilen)} Messungen, {schlecht} mit Fehler")
    return 1 if schlecht else 0


if __name__ == "__main__":
    sys.exit(main())
