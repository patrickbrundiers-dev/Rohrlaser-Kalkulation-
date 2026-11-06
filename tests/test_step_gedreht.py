"""Gedrehte Kopien gleicher Bleche, Kantteile, Dreh- und Frästeile nur einmal messen (Patrick 06.11.2026
„langsamer Import“: Pizzaofen 76 Messungen für 33 verschiedene Teile, 0003-400-001 434 Messungen für 145 Teile).

Vorher wurden nur verschoben eingebaute Kopien übernommen, jede gedrehte Kopie wurde neu gemessen. Jetzt übernimmt
eine gedrehte Kopie eines Blechs, Kantteils, Dreh- oder Frästeils die Messung des ersten Teils, mit eigener
Einbaulage und eigenem Hüllquader. Rohre und Profile werden weiter selbst gemessen (Ende A und Konturen nach der
Lage im Raum). Geprüft: Messwerte wie bei der Einzelmessung jedes Körpers, 3D-Netz mit Einbaulage liegt auf dem
Körper in der Datei, verteilt auf mehrere Prozesse dasselbe wie in einem.

Aufruf: python tests/test_step_gedreht.py
"""
import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"), str(HIER)]
MESSEN = HIER.parent / "programm" / "step_messung" / "step_messen.py"

from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepBndLib import BRepBndLib  # noqa: E402
from OCP.Bnd import Bnd_Box  # noqa: E402

import erzeuge_testteile as et  # noqa: E402
import step_geometrie  # noqa: E402
import step_messen  # noqa: E402
from erzeuge_struktur_teile import Dokument, lage  # noqa: E402
from test_step_wie_modell import box  # noqa: E402
from rohrlaser.lage_abgleich import in_lage  # noqa: E402

PI2 = math.pi / 2
ORT = {"artikel", "koerper", "bauteil", "pfad", "knoten", "netz", "huelle", "hinweise", "meldungen", "anbauteile",
       "trennung", "verbund", "alternative", "arten", "geschlossen"}


def teile():
    blech = box(0, 0, 0, 200, 100, 3)
    for x in (20, 180):
        blech = et.cut(blech, et.zylinder((x, 50, -1), (0, 0, 1), 9, 5))
    blech = et.cut(blech, box(80, 30, -1, 40, 15, 5))
    dreh = BRepAlgoAPI_Fuse(et.zylinder((0, 0, 0), (0, 0, 1), 20, 12), et.zylinder((0, 0, 12), (0, 0, 1), 10, 25)).Shape()
    rohr = et.bohrung_quer(et.kastenrohr(40, 40, 3, 600, 4.5), 9, 150)
    return [("Lasche 200x100x3", blech), ("Bolzen", dreh), ("Holm QR40x3", rohr)]


def lagen(x0):
    """Original, um X gedreht, um Y gedreht, die um Y gedrehte verschoben (je Teil weit auseinander)."""
    return [lage(x0), lage(x0, 900, 0, um_x=PI2), lage(x0 + 1500, 0, 300, um_y=0.4), lage(x0 + 1500, 400, 300, um_y=0.4)]


def messen(pfad, ziel, umgebung=None, *args):
    ziel.mkdir()
    env = dict(os.environ, **(umgebung or {}))
    r = subprocess.run([sys.executable, str(MESSEN), "--ausgabe", str(ziel / "r.txt"), "--netze", str(ziel), *args,
                        str(pfad)], capture_output=True, text=True, env=env, timeout=1200)
    assert r.returncode in (0, 1), r.stderr[-2000:]
    zeilen = [dict(zip(step_messen.SPALTEN, z.split("\t"))) for z in
              (ziel / "r.txt").read_text(encoding="utf-8").splitlines()[1:]]
    return {int(z["koerper"]): z for z in zeilen}


def gleich(a, b, tol=1e-5):
    if a == b:
        return True
    try:
        x, y = float(a), float(b)
        return abs(x - y) <= tol * max(1.0, abs(x), abs(y))
    except (TypeError, ValueError):
        pass
    try:
        a, b = json.loads(a), json.loads(b)
    except (TypeError, ValueError):
        ta, tb = str(a).replace(":", "|").split("|"), str(b).replace(":", "|").split("|")
        return len(ta) > 1 and len(ta) == len(tb) and all(gleich(x, y, tol) for x, y in zip(ta, tb))
    if isinstance(a, dict) and isinstance(b, dict):     # Umriss einer Bohrung: Punkte je nach Lage anders verteilt
        return a.keys() == b.keys() and all(k == "umriss" or gleich(json.dumps(a[k]), json.dumps(b[k]), tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(gleich(json.dumps(x), json.dumps(y), tol) for x, y in zip(a, b))
    return gleich(str(a), str(b), tol) if not isinstance(a, (str, dict, list)) else False


def main():
    fehler = 0
    tmp = Path(tempfile.mkdtemp())
    d = Dokument()
    pfad = tmp / "Gedreht.step"
    d.baugruppe("Test", [(d.teil(n, s), loc) for j, (n, s) in enumerate(teile()) for loc in lagen(4000 * j)])
    d.schreiben(pfad)
    gel = step_geometrie.datei_lesen(pfad)
    # Körper je Teil: 1 Original, 2 um X gedreht, 3 um Y gedreht, 4 = 3 verschoben
    namen = [gel.info["bauteile"].get(i, ("",))[0] for i in range(1, len(gel.koerper) + 1)]
    erwartet = {i for i in range(1, len(namen) + 1) if (i - 1) % 4 in (1, 2)}
    if set(gel.gedreht) != erwartet or set(gel.gleich) != {i for i in range(1, len(namen) + 1) if (i - 1) % 4 == 3}:
        fehler += 1
        print("FEHLER gedrehte/verschobene Kopien:", sorted(gel.gedreht), sorted(gel.gleich), namen)
    else:
        print("OK     gedrehte Kopien erkannt:", ", ".join(f"K{i} ({namen[i - 1]})" for i in sorted(gel.gedreht)))
    einzeln = messen(pfad, tmp / "einzeln", {"STEP_MESSEN_EINZELN": "1"})
    neu = messen(pfad, tmp / "neu")
    verteilt = messen(pfad, tmp / "verteilt", {"STEP_MESSEN_TEILEN_AB": "2"}, "--prozesse", "3")
    for k, z in neu.items():
        # gedrehte Kopie eines Blechs/Drehteils: wie das Original einzeln gemessen (schräg im Raum gemessen war ein
        # Ausschnitt der Lasche vorher 36,84 statt 40 mm), sonst wie der Körper selbst
        v = gel.gedreht[k][0] if k in gel.gedreht and z["profilform"] in step_geometrie.GEDREHT_UEBERNEHMEN else k
        v = gel.gleich[k][0] if k in gel.gleich and gel.gleich[k][0] in gel.gedreht and \
            z["profilform"] in step_geometrie.GEDREHT_UEBERNEHMEN else v
        v = gel.gedreht[v][0] if v in gel.gedreht and z["profilform"] in step_geometrie.GEDREHT_UEBERNEHMEN else v
        for spalte, wert in z.items():
            if spalte not in ORT and not gleich(wert, einzeln[v][spalte]):
                fehler += 1
                print(f"FEHLER K{k} {namen[k - 1]} {spalte}: {str(wert)[:80]} statt {str(einzeln[v][spalte])[:80]}")
            if spalte not in ("hinweise",) and wert != verteilt[k][spalte]:
                fehler += 1
                print(f"FEHLER K{k} verteilt anders: {spalte}")
    print(f"OK     Messwerte aller {len(neu)} Körper wie einzeln gemessen, verteilt wie in einem Prozess"
          if not fehler else "")
    weit = 0.0
    for k, z in neu.items():
        n = json.loads((tmp / "neu" / z["netz"]).read_text(encoding="utf-8"))
        pts = in_lage(n["p"], n["lage"])
        b = Bnd_Box()
        BRepBndLib.Add_s(gel.koerper[k - 1][1], b)
        lo, hi = b.CornerMin(), b.CornerMax()
        for i, (u, o) in enumerate(((lo.X(), hi.X()), (lo.Y(), hi.Y()), (lo.Z(), hi.Z()))):
            weit = max(weit, abs(min(p[i] for p in pts) - u), abs(max(p[i] for p in pts) - o))
    if weit > 0.5:
        fehler += 1
        print(f"FEHLER 3D-Netz mit Einbaulage {weit:.2f} mm neben dem Körper in der Datei")
    else:
        print(f"OK     3D-Netze mit Einbaulage auf den Körpern der Datei ({weit:.3f} mm)")
    arten = {namen[k - 1]: z["profilform"] for k, z in neu.items()}
    print("       erkannt:", arten)
    if arten.get("Lasche 200x100x3") != "Blech" or arten.get("Bolzen") not in ("Drehteil", "Frästeil"):
        fehler += 1
        print("FEHLER Testteile nicht wie gedacht erkannt")
    print("Alle Tests OK" if not fehler else f"{fehler} Test(s) fehlgeschlagen")
    return fehler


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
