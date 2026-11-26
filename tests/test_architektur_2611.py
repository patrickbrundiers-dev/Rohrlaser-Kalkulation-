"""Architektur- und Parallel-Test (Software-Audit Patrick 26.11.2026, docs/system-audit/SOFTWARE_AUDIT_2611.md).

1. Rechenkern ohne Oberfläche: die Module des Rechenkerns (Kalkulation, Schneidweg, Optimierung, Staffeln, Fracht,
   Stammdaten, Datenbank, PDF, STEP-Übernahme …) lassen sich einzeln laden, ohne PySide6 (Qt) oder OCP (OpenCascade)
   nachzuziehen. Eine volle Rechnung (Angebot anlegen, optimieren, kalkulieren, Staffeln, Preisherkunft) lädt danach
   ebenfalls kein Qt. Grund: Kern-Module lassen sich so unabhängig testen und im Hintergrund rechnen; eine Änderung an
   einem Fenster kann den Rechenkern nicht mehr brechen (A-01: herkunft -> teile_editor, step -> ansicht3d).
2. Sperrklinke Abhängigkeiten: Anzahl der Importe von Qt-freien Modulen auf Oberflächen-Module (auch Importe in
   Funktionen) darf nicht steigen (Stand 26.11.2026 nach A-01). Neue Fälle gehören in ein Qt-freies Modul.
3. Parallel: dieselben Angebote in mehreren Threads gleichzeitig optimieren und kalkulieren (wie Optimieren und
   Staffelpreise im Hintergrund, während die Oberfläche rechnet), dabei die Merker laufend leeren; jedes Ergebnis muss
   typgenau dem Einzellauf gleichen, ohne Ausnahme.

Aufruf: python tests/test_architektur_2611.py
"""
import ast
import copy
import random
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

HIER = Path(__file__).parent
PROGRAMM = HIER.parent / "programm"
sys.path.insert(0, str(PROGRAMM))
sys.path.insert(0, str(HIER))

KERN = ["rohrlaser.rechnen", "rohrlaser.schneidweg", "rohrlaser.optimierung", "rohrlaser.staffeln",
        "rohrlaser.fracht", "rohrlaser.packkern", "rohrlaser.stammdaten", "rohrlaser.angebot", "rohrlaser.datenbank",
        "rohrlaser.blech", "rohrlaser.blech_preis", "rohrlaser.nesting", "rohrlaser.pdf", "rohrlaser.step",
        "rohrlaser.baugruppe", "rohrlaser.skizze", "rohrlaser.rohr3d", "rohrlaser.teilen", "rohrlaser.herkunft",
        "rohrlaser.netz_daten", "rohrlaser.teile_status", "rohrlaser.rahmen", "rohrlaser.cam_paket",
        "rohrlaser.nesting_abwicklung", "rohrlaser.step_gegenprobe", "rohrlaser.ausgabe", "rohrlaser.protokoll"]
# Sperrklinke (2.): Importe Qt-frei -> Oberfläche, Stand 26.11.2026 nach A-01 (vorher 56)
KANTEN_MAX = 46


# ------------------------------------------------------------------ 1. Kern-Module einzeln ohne Qt/OCP
code = ("import sys, importlib; importlib.import_module(sys.argv[1]); "
        "print(int('PySide6' in sys.modules), int('OCP' in sys.modules))")
fehler = []
for m in KERN:
    r = subprocess.run([sys.executable, "-c", code, m], capture_output=True, text=True, cwd=PROGRAMM)
    if r.returncode != 0:
        fehler.append(f"{m}: Import scheitert: {r.stderr.strip().splitlines()[-1:]}")
    elif r.stdout.split() != ["0", "0"]:
        fehler.append(f"{m}: zieht {'PySide6 ' if r.stdout.split()[0] == '1' else ''}"
                      f"{'OCP' if r.stdout.split()[1] == '1' else ''} nach")
assert not fehler, "Rechenkern lädt Oberfläche bzw. OpenCascade:\n" + "\n".join(fehler)
print(f"OK    {len(KERN)} Kern-Module einzeln geladen: ohne PySide6 und ohne OCP")


# ------------------------------------------------------------------ 2. Sperrklinke Abhängigkeiten Kern -> Oberfläche
def module():
    out = {}
    for p in sorted(PROGRAMM.rglob("*.py")):
        teile = p.relative_to(PROGRAMM).with_suffix("").parts
        name = ".".join(teile[:-1] if teile[-1] == "__init__" else teile)
        out[name] = (p, ast.parse(p.read_text(encoding="utf-8")))
    return out


def ziele(name, baum, alle, ist_paket):
    for node in ast.walk(baum):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names if a.name in alle)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                basis = name.split(".")[:len(name.split(".")) - node.level + (1 if ist_paket else 0)]
                b = ".".join(basis + ([node.module] if node.module else []))
            else:
                b = node.module or ""
            for a in node.names:
                z = f"{b}.{a.name}"
                if z in alle:
                    yield z
                elif b in alle:
                    yield b


alle = module()
qt_oben = {n for n, (_, b) in alle.items()
           if any(isinstance(x, (ast.Import, ast.ImportFrom)) and "PySide6" in ast.unparse(x) for x in b.body)}
kanten = sorted({(n, z) for n, (p, b) in alle.items() if n.startswith("rohrlaser.") and n not in qt_oben
                 for z in ziele(n, b, alle, p.name == "__init__.py") if z in qt_oben and z != n})
assert len(kanten) <= KANTEN_MAX, (f"{len(kanten)} Importe von Qt-freien Modulen auf Oberflächen-Module (höchstens "
                                   f"{KANTEN_MAX}). Neue Funktionen ohne Qt gehören in ein Qt-freies Modul:\n"
                                   + "\n".join(f"  {a} -> {b}" for a, b in kanten))
print(f"OK    Importe Qt-frei -> Oberfläche: {len(kanten)} (Grenze {KANTEN_MAX}, vor dem Audit 56)")
for k in KERN:
    assert not any(a == k for a, _ in kanten), f"Kern-Modul {k} importiert ein Oberflächen-Modul: " + \
        ", ".join(b for a, b in kanten if a == k)
print("OK    Kein Kern-Modul importiert ein Oberflächen-Modul (auch nicht in Funktionen)")

# ------------------------------------------------------------------ 2b. keine neuen Kopien der gemeinsamen Hilfsfunktionen
def form(fn):
    y = copy.deepcopy(fn)
    if ast.get_docstring(y):
        y.body = y.body[1:] or [ast.Pass()]
    y.name = "_"
    if y.args.args:
        alt = y.args.args[0].arg
        for n in ast.walk(y):
            if isinstance(n, ast.Name) and n.id == alt:
                n.id = "P"
            if isinstance(n, ast.arg) and n.arg == alt:
                n.arg = "P"
    return ast.dump(y, annotate_fields=False)


gemeinsam = {form(x): x.name for x in alle["rohrlaser.zahlen"][1].body if isinstance(x, ast.FunctionDef)}
kopien = [f"{n}.{x.name} (= zahlen.{gemeinsam[form(x)]})" for n, (_, b) in alle.items()
          if n.startswith("rohrlaser.") and n != "rohrlaser.zahlen"
          for x in b.body if isinstance(x, ast.FunctionDef) and form(x) in gemeinsam]
assert not kopien, "Kopie einer gemeinsamen Hilfsfunktion, bitte aus rohrlaser/zahlen.py einbinden:\n" + "\n".join(kopien)
print(f"OK    Keine Kopien der {len(gemeinsam)} gemeinsamen Hilfsfunktionen (rohrlaser/zahlen.py)")

# ------------------------------------------------------------------ 3. volle Rechnung ohne Qt, parallel bitgleich
import test_regression_ergebnisse as T  # noqa: E402
from rohrlaser import dauermerker, dynamik, herkunft, rechenmerker, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())
dauermerker.einrichten(None)
db = Datenbank(tmp / "architektur.db")
for a in T.ANGEBOTE:
    T.abnahme_rechnen(a, db)
for a in T.KONTUR_ANGEBOTE:
    T.kontur_rechnen(a, db)
faelle = []
for (aid,) in db.con.execute("SELECT id FROM angebote ORDER BY id").fetchall():
    faelle.append((db.angebot(aid), db.positionen(aid), db.kontext(), db.tabellen(), db.einstellungen()))
db.schliessen()


def eins(f):
    kopf, pos, k, tab, einst = copy.deepcopy(f)
    erg = rechnen.optimieren(kopf, pos, k, tab, einst)
    kopf = dict(kopf, ergebnis=erg)
    e = rechnen.einstellungen_angebot(kopf, einst)
    zeilen, summen = rechnen.kalkulation(kopf, pos, erg, k, tab, e)
    return repr((erg.get("stangen"), zeilen, summen))


ref = [eins(f) for f in faelle]
kopf, pos, k, tab, einst = copy.deepcopy(faelle[-1])
stufen = [dict(id=i, schluessel="30", menge=m) for i, m in enumerate((1, 10, 100), 1)]
assert len(staffeln.rechnen_alle(kopf, pos, stufen, k, tab, einst)) == 3
herkunft.merkmal_sicherheit("STEP")
assert "PySide6" not in sys.modules, "Volle Rechnung (Optimieren, Kalkulation, Staffeln, Herkunft) lädt PySide6"
print(f"OK    Volle Rechnung von {len(faelle)} Angeboten samt Staffeln und Preisherkunft: ohne PySide6")


def merker_leeren():
    rechenmerker.alle_leeren()
    dynamik._FOLGE_MERK.clear()
    m = getattr(rechnen, "_KALK_MERK", None)
    if m is not None:
        m.leeren()


merker_leeren()
THREADS, RUNDEN = 6, 3
abweichung, ausnahmen, laeufe = [], [], [0]
stop = threading.Event()
alt_intervall = sys.getswitchinterval()
sys.setswitchinterval(1e-5)          # häufige Threadwechsel: Wettläufe zeigen sich schneller


def arbeiter(nr):
    r = random.Random(nr)
    for _ in range(RUNDEN):
        reihe = list(range(len(faelle)))
        r.shuffle(reihe)
        for i in reihe:
            try:
                if eins(faelle[i]) != ref[i]:
                    abweichung.append((nr, i))
                laeufe[0] += 1
            except Exception:       # noqa: BLE001 – jede Ausnahme ist ein Befund
                ausnahmen.append(traceback.format_exc())


def leerer():
    r = random.Random(99)
    while not stop.is_set():
        time.sleep(r.random() * 0.05)
        merker_leeren()


t0 = time.perf_counter()
lt = threading.Thread(target=leerer)
lt.start()
ts = [threading.Thread(target=arbeiter, args=(n,)) for n in range(THREADS)]
for t in ts:
    t.start()
for t in ts:
    t.join()
stop.set()
lt.join()
sys.setswitchinterval(alt_intervall)
assert not ausnahmen, f"{len(ausnahmen)} Ausnahmen beim parallelen Rechnen:\n" + ausnahmen[0]
assert not abweichung, f"Paralleles Rechnen weicht vom Einzellauf ab (Thread, Angebot): {abweichung[:10]}"
assert laeufe[0] == THREADS * RUNDEN * len(faelle)
print(f"OK    Parallel: {THREADS} Threads × {RUNDEN} Runden = {laeufe[0]} Rechnungen mit laufend geleerten Merkern in "
      f"{time.perf_counter() - t0:.1f} s, alle typgenau gleich dem Einzellauf")

# ------------------------------------------------------------------ 4. Software-3D: beim Drehen gröber sortieren (G-05)
import os  # noqa: E402

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, rohr3d  # noqa: E402

netz = rohr3d.netz(dict(a=dict(winkel=45.0), b=dict(winkel=30.0), konturen=[]),
                   dict(form="QR", b=60.0, h=60.0, d=60.0, wand=3.0, radius=6.0, profil_id="QR 60x60x3"), 1900)
modell = ansicht3d.Modell(ansicht3d.baugruppe([dict(netz, lage=[0, 300 * i, 0, 0, 0, 1, 1, 0, 0])
                                               for i in range(7)])[0])
stuecke, orig = [0], ansicht3d._sortier_teile


def zaehlen(*a, **kw):
    r = orig(*a, **kw)
    if kw.get("tiefe", a[4] if len(a) > 4 else 0) == 0:
        stuecke[0] += len(r)
    return r


ansicht3d._sortier_teile = zaehlen
bilder = {}
for f in (None, 1.0, ansicht3d.SORTIER_GROB):
    stuecke[0] = 0
    img = QImage(1400, 900, QImage.Format_ARGB32_Premultiplied)
    img.fill(0)
    p = QPainter(img)
    ansicht3d.zeichnen(p, modell, 1400, 900, 0.5, 0.4, linien=False, glatt=False,
                       **({} if f is None else dict(sortier_grob=f)))
    p.end()
    bilder[f] = (stuecke[0], img)
ansicht3d._sortier_teile = orig
assert bilder[None][1] == bilder[1.0][1], "Bild im Stillstand hat sich geändert"
assert bilder[ansicht3d.SORTIER_GROB][0] * 2 <= bilder[None][0], {f: n for f, (n, _) in bilder.items()}
print(f"OK    Software-3D: Stillstand bildgleich, beim Drehen {bilder[ansicht3d.SORTIER_GROB][0]} statt "
      f"{bilder[None][0]} Stücke je Bild")
print("Alles in Ordnung.")
