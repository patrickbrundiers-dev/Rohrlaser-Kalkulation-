"""Nachgebaute STEP-Messung für tests/test_vormessung_alle_plaetze.py: versteht --liste, --ausgabe, --netze, --cache wie
step_messen (ein Eintrag je Dateiinhalt mit ergebnis.json und Netz) und schreibt jeden Aufruf in <cache>/../aufrufe.txt
bzw. neben die Ausgabe. Keine echte Geometrie."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

a = sys.argv[1:]


def wert(n):
    return a[a.index(n) + 1] if n in a else None


dateien = [z.strip() for z in Path(wert("--liste")).read_text(encoding="utf-8").splitlines() if z.strip()]
netze, cache = wert("--netze"), wert("--cache")
log = Path(wert("--log") or (Path(cache).parent / "aufrufe.txt" if cache else Path(wert("--ausgabe")).parent / "a.txt"))
if netze:
    Path(netze).mkdir(parents=True, exist_ok=True)
treffer = 0
for i, d in enumerate(dateien, start=1):
    k = hashlib.sha256(Path(d).read_bytes() + json.dumps([wert("--flachstahl-bis"), bool(netze)]).encode()).hexdigest()
    name = f"{i:05d}_k1.json"
    e = Path(cache) / k if cache else None
    if e is not None and (e / "ergebnis.json").is_file():
        treffer += 1
        if netze:
            shutil.copyfile(e / "00001_k1.json", Path(netze) / name)
        continue
    netz = dict(p=[0, 0, 0, 10, 0, 0, 0, 10, 0], t={"AW": [0, 1, 2]})
    if netze:
        (Path(netze) / name).write_text(json.dumps(netz), encoding="utf-8")
    if e is not None:
        e.mkdir(parents=True)
        (e / "00001_k1.json").write_text(json.dumps(netz), encoding="utf-8")
        (e / "ergebnis.json").write_text(json.dumps(dict(nr=1, zeilen=[], json={})), encoding="utf-8")
Path(wert("--ausgabe")).write_text("datei\tkoerper\n", encoding="utf-8")
with open(log, "a", encoding="utf-8") as f:
    f.write(json.dumps(dict(args=a, treffer=treffer, dateien=len(dateien))) + "\n")
