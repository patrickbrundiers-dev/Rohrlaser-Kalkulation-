"""Leistungsvergleich der STEP-Messung (Plan S3): Laufzeit, Speicher und Netzgröße.

Misst T08_Gestell_Baugruppe und eine erzeugte Baugruppe mit 200 Körpern (Instanzen verschoben und gedreht, Rohre mit
Bohrungen und Gehrung, Bleche) mit verschiedenen Prozesszahlen. Entscheidet nicht über Grün/Rot, schreibt nur den
Bericht.

Aufruf: python tests/benchmark_step.py [BERICHT.md]
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
MESSEN = HIER.parent / "programm" / "step_messung" / "step_messen.py"
sys.path.insert(0, str(HIER))


def halle(ziel):
    """Baugruppe "Halle" mit 200 Körpern: 10 Rohrtypen je 8× verschoben, 5 Typen je 6× geneigt,
    4 Blechtypen je 10× verschoben, 50 einzelne Rohre verschiedener Länge; kein Teil berührt ein anderes."""
    from erzeuge_struktur_teile import Dokument, lage
    from erzeuge_testteile import bohrung_quer, gehrung, kastenrohr, rundrohr
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    d = Dokument()
    teile = []
    for i in range(10):
        s = kastenrohr(40 + 10 * (i % 3), 40, 3, 600 + 50 * i, 4.5)
        for k in range(3):
            s = bohrung_quer(s, 8 + k, 100 + 120 * k)
        s = gehrung(s, 600 + 50 * i, 45)
        lab = d.teil(f"Stütze {i + 1}", s)
        teile += [(lab, lage(1000 * i, 400 * j, 0)) for j in range(8)]
    for i in range(5):
        s = rundrohr(42.4 + 6 * i, 2.6, 800 + 40 * i)
        s = bohrung_quer(s, 10, 300)
        lab = d.teil(f"Riegel {i + 1}", s)
        teile += [(lab, lage(1000 * i, 5000 + 300 * j, 0, um_y=0.3 * j)) for j in range(6)]
    for i in range(4):
        b = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), 150 + 20 * i, 100, 8).Shape()
        for k in range(2):
            z = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(30 + 80 * k, 50, -1), gp_Dir(0, 0, 1)), 6.5, 10).Shape()
            b = BRepAlgoAPI_Cut(b, z).Shape()
        lab = d.teil(f"Lasche {i + 1}", b)
        teile += [(lab, lage(300 * j, -800 - 200 * i, 0)) for j in range(10)]
    for i in range(50):
        s = kastenrohr(60, 40, 3, 300 + 17 * i, 4.5)
        s = bohrung_quer(s, 9, 150, (0, 1, 0))
        teile.append((d.teil(f"Pfette {i + 1}", s), lage(200 * i, 8000, 0)))
    assert len(teile) == 200
    d.baugruppe("Halle", teile)
    d.schreiben(ziel)


def messen(dateien, args, tmp, name):
    aus, js, netze = tmp / f"{name}.txt", tmp / f"{name}.json", tmp / f"{name}_netze"
    netze.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    r = subprocess.run([sys.executable, str(MESSEN), "--ausgabe", str(aus), "--json", str(js), "--netze", str(netze),
                        *args, *map(str, dateien)], capture_output=True, text=True)
    dauer = time.perf_counter() - t0
    assert r.returncode in (0, 1), r.stderr
    import resource
    speicher = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024     # MB (größter Messprozess)
    groesse = sum(p.stat().st_size for p in netze.iterdir()) / 1024 / 1024
    daten = json.loads(js.read_text(encoding="utf-8"))
    daten.pop("erzeugt", None)
    return dict(dauer=dauer, speicher=speicher, netze_mb=groesse, koerper=sum(len(d["koerper"])
                                                                             for d in daten["dateien"])), daten


def main():
    bericht = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    tmp = Path(tempfile.mkdtemp())
    datei = tmp / "B01_Halle_200.step"
    halle(datei)
    faelle = [("T08 (4 Körper)", [HIER / "step_satz" / "T08_Gestell_Baugruppe.step"]), ("Halle (200 Körper)", [datei])]
    kerne = os.cpu_count() or 1
    zeilen = ["| Datei | Prozesse | Zeit [s] | Speicher größter Prozess [MB] | Netze [MB] | Körper |",
              "|---|---|---|---|---|---|"]
    for titel, dateien in faelle:
        ergebnis = None
        for p in sorted({1, max(1, kerne - 1)}):
            werte, daten = messen(dateien, ["--zeitlimit", "120", "--prozesse", str(p)], tmp, f"m{p}")
            if ergebnis is None:
                ergebnis = daten
            gleich = "" if daten == ergebnis else " (Ergebnis weicht ab!)"
            zeilen.append(f"| {titel} | {p} | {werte['dauer']:.1f} | {werte['speicher']:.0f} | "
                          f"{werte['netze_mb']:.1f} | {werte['koerper']}{gleich} |")
            print(zeilen[-1], flush=True)
    text = f"STEP-Messung, {kerne} Kerne, {time.strftime('%Y-%m-%d %H:%M')}\n\n" + "\n".join(zeilen) + "\n"
    if bericht:
        bericht.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
