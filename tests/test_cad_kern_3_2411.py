"""CAD- und Kalkulationskern 3.0 (Master-Auftrag Patrick 24.11.2026): Lese-Zwischenspeicher der STEP-Messung und
threadsicheres STEP-Schreiben.

Geprüft wird:
1. Mit Lese-Zwischenspeicher (step_lesecache) messen erstes Lesen und Wiedereinlesen bitgleich (das erste Lesen misst
   schon die gemerkte Form) – Zeilen, JSON und 3D-Netze, für ein Einzelteil, Baugruppen mit Unterbaugruppen und
   Wiederholteilen und ein Flächenmodell. Kopien (verschoben/gedreht), Struktur und Bauteilnamen kommen gleich mit.
   Die Abweichung gegen das Lesen ohne Speicher (Normierung der Richtungen) wird nur ausgegeben.
2. Der Schlüssel hängt am Inhalt und am Dateinamen (Name der Baugruppenwurzel), nicht am Ordner; kleine Lesedauer
   unter AB_S wird nicht gemerkt; ohne Ordner (STEP_LESECACHE) bleibt alles wie bisher.
3. Wächter: Ändert sich der Lesecode (lies_step_info, _struktur, …), muss LESER_STAND hochgezählt werden – sonst
   lieferte der Speicher alte Lesungen. Der Test vergleicht eine Prüfsumme des Quelltexts.
4. Das Lesen benutzt keine globalen Importparameter (Interface_Static), nur Werte am eigenen Leser.
5. STEP-Schreiben aus zwei Threads gleichzeitig: jede Datei trägt ihren eigenen Produktnamen (Interface_Static nur
   unter Sperre).
6. Begrenzen des Zwischenspeichers räumt auch gemerkte Lesungen ab.
Aufruf: python tests/test_cad_kern_3_2411.py
"""
import hashlib
import inspect
import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

HIER = Path(__file__).resolve().parent
MESSUNG = HIER.parent / "programm" / "step_messung"
sys.path.insert(0, str(MESSUNG))

import step_geometrie as g  # noqa: E402
import step_lesecache as lc  # noqa: E402
import step_messen as sm  # noqa: E402

sys.path.insert(0, str(HIER.parent / "werkzeuge"))
from step_benchmark import unterschiede  # noqa: E402

GENAU = 1e-12       # BinTools schreibt Richtungen (gp_Dir) und liest sie normiert: Abweichung in der letzten Stelle

# Bei Änderung am Lesen: LESER_STAND in step_lesecache.py hochzählen und beide Werte hier neu eintragen
LESER_STAND = 2
LESE_PRUEFSUMME = "71aa69af49e06a35"
LESE_FUNKTIONEN = ("lies_step_info", "lies_iges_info", "_iges_einheit", "_solid_analytisch", "_analytisch",
                   "_draht_analytisch", "_caf_uebertragen", "_name", "_struktur", "_naehen", "_einheit",
                   "_grosse_datei_einstellen", "_konsole_mitschneiden", "_instanzen", "_teilform", "_gedrehte",
                   "datei_lesen")

fehler = []


def pruefe(bedingung, text):
    print(("ok    " if bedingung else "FEHLER ") + text)
    if not bedingung:
        fehler.append(text)


def pruefsumme():
    h = hashlib.sha256()
    for n in LESE_FUNKTIONEN:
        h.update(inspect.getsource(getattr(g, n)).encode("utf-8"))
    h.update(repr((g.GROSS_AB_MB, g.SCHNELL_OHNE)).encode("utf-8"))
    return h.hexdigest()[:16]


def zahlen(x):
    """Zeilen (TSV) bzw. Text darin als Zahlen, Listen und JSON, damit der Vergleich mit Toleranz rechnen kann."""
    if isinstance(x, list):
        return [zahlen(y) for y in x]
    if isinstance(x, str):
        for f in (float, json.loads):
            try:
                return zahlen(f(x)) if f is json.loads else f(x)
            except (ValueError, TypeError):
                pass
        if ":" in x or "|" in x:
            return [zahlen(t) for t in x.replace("|", ":").split(":")]
        return x
    if isinstance(x, dict):
        return {k: zahlen(v) for k, v in x.items()}
    return x


def ohne_zeit(js):
    js = dict(js)
    js.pop("erzeugt", None)
    return json.dumps(js, sort_keys=True, ensure_ascii=False)


tmp = Path(tempfile.mkdtemp(prefix="cadkern3_"))
try:
    # 3. Wächter
    pruefe(lc.LESER_STAND == LESER_STAND and pruefsumme() == LESE_PRUEFSUMME,
           f"Lesecode unverändert oder LESER_STAND hochgezählt (Prüfsumme {pruefsumme()}, Stand {lc.LESER_STAND})")

    # 4. keine globalen Importparameter beim Lesen
    quelle = (MESSUNG / "step_geometrie.py").read_text(encoding="utf-8")
    pruefe("Interface_Static" not in quelle, "Lesen ohne Interface_Static (nur Werte am eigenen Leser)")

    # 1. aus dem Speicher gleich wie frisch
    dateien = [HIER / "step_konturen" / "K08_U80x40x4_Lage_gedreht.step",
               HIER / "step_struktur" / "S04_Gestell_Unterbaugruppe_geschweisst.step",
               HIER / "step_struktur" / "S01_Gestell_verschachtelt.step"]
    flaechen = sorted((HIER / "step_import").glob("*Flaeche*")) + sorted((HIER / "step_import").glob("*flaeche*"))
    dateien += flaechen[:1]
    os.environ[lc.UMGEBUNG] = str(tmp / "cache")
    os.environ["STEP_LESECACHE_AB"] = "0"
    for d in dateien:
        for n in ("n0", "n1", "n2"):
            (tmp / n).mkdir(exist_ok=True)
        os.environ.pop(lc.UMGEBUNG)
        ohne = sm.messen(d, str(tmp / "n0"), 1)          # wie bisher, ohne Zwischenspeicher
        os.environ[lc.UMGEBUNG] = str(tmp / "cache")
        frisch = sm.messen(d, str(tmp / "n1"), 1)        # erstes Lesen: merken, Messung im Speicher wie bisher
        gel = g.datei_lesen(d)
        aus = sm.messen(d, str(tmp / "n2"), 1)           # aus dem Zwischenspeicher
        pruefe(gel.info.get("phasen", {}).get("lesecache") == 1, f"{d.name}: zweites Lesen aus dem Zwischenspeicher")
        pruefe(ohne_zeit(frisch[1]) == ohne_zeit(aus[1]) and frisch[0] == aus[0],
               f"{d.name}: erstes Lesen und Wiedereinlesen aus dem Zwischenspeicher bitgleich")
        n1 = sorted(q.read_bytes() for q in (tmp / "n1").glob("*.json"))
        n2 = sorted(q.read_bytes() for q in (tmp / "n2").glob("*.json"))
        pruefe(n1 == n2, f"{d.name}: 3D-Netze bitgleich ({len(n1)})")
        u = unterschiede(ohne[1], aus[1], GENAU)
        print(f"      {d.name}: gegen Lesen ohne Zwischenspeicher {len(unterschiede(ohne[1], aus[1]))} Zahlen in den "
              f"letzten Stellen anders, {len(u)} über {GENAU:g} (Normierung der Richtungen)")
        for n in ("n0", "n1", "n2"):
            shutil.rmtree(tmp / n, ignore_errors=True)
    s04 = dateien[1]
    os.environ.pop(lc.UMGEBUNG)
    roh = g.datei_lesen(s04)
    os.environ[lc.UMGEBUNG] = str(tmp / "cache")
    gem = g.datei_lesen(s04)
    pruefe(gem.gleich == roh.gleich and gem.gedreht == roh.gedreht and gem.info["struktur"] == roh.info["struktur"]
           and gem.info["bauteile"] == roh.info["bauteile"],
           f"Baugruppe: Kopien ({len(roh.gleich)} verschoben, {len(roh.gedreht)} gedreht), Struktur und Namen gleich")
    pruefe(all(a.IsPartner(gem.koerper[v - 1][1]) for k, (v, _) in gem.gleich.items() for a in [gem.koerper[k - 1][1]]),
           "Baugruppe: Wiederholteile teilen auch aus dem Speicher dieselbe Geometrie")

    # 2. Schlüssel
    kopie = tmp / "anders" / s04.name
    kopie.parent.mkdir()
    shutil.copyfile(s04, kopie)
    umbenannt = tmp / "Anderer_Name.step"
    shutil.copyfile(s04, umbenannt)
    pruefe(lc.schluessel(kopie) == lc.schluessel(s04), "Schlüssel: gleicher Inhalt in anderem Ordner trifft")
    pruefe(lc.schluessel(umbenannt) != lc.schluessel(s04), "Schlüssel: anderer Dateiname eigener Eintrag (Wurzelname)")
    pruefe(lc.schluessel(tmp / "x.tubx") is None, "Schlüssel: nur STEP/IGES")
    os.environ["STEP_LESECACHE_AB"] = "1e9"
    pruefe(not lc.merken(umbenannt, *g.lies_step_info(umbenannt), {}, {}), "kurzes Lesen wird nicht gemerkt")
    os.environ.pop(lc.UMGEBUNG)
    pruefe(lc.laden(s04) is None, "ohne Ordner kein Zwischenspeicher")
    os.environ.pop("STEP_LESECACHE_AB")

    # 6. Begrenzen
    sm.cache_begrenzen(tmp / "cache", 0)
    pruefe(not list((tmp / "cache").glob("lesen_*")), "Begrenzen räumt gemerkte Lesungen ab")

    # 7. Große Baugruppen: Kopiensuche je Fach und räumliche Paarsuche liefern dasselbe wie der Vergleich jeder mit
    # jedem (synthetisch: 1.200 verschiedene Körper, je eine verschobene und eine gedrehte Kopie, leere Hüllen)
    import random
    import time
    from OCP.Bnd import Bnd_Box
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    koerper = []
    for i in range(400):
        b = BRepPrimAPI_MakeBox(10 + i * 0.01, 20, 30).Shape()
        t1, t2 = gp_Trsf(), gp_Trsf()
        t1.SetTranslation(gp_Vec(100, i, 0))
        t2.SetRotation(gp_Ax1(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 0.5)
        koerper += [("Volumenkörper", TopoDS.Solid(b)), ("Volumenkörper", TopoDS.Solid(b.Moved(TopLoc_Location(t1)))),
                    ("Volumenkörper", TopoDS.Solid(b.Moved(TopLoc_Location(t2))))]
    gl = g._instanzen(koerper)
    pruefe(len(gl) == 400 and len(g._gedrehte(koerper, gl)) == 400 and all(v == n - 1 for n, (v, _) in gl.items()),
           "Kopiensuche je Fach: 400 verschobene und 400 gedrehte Kopien ihrem Vorbild zugeordnet")
    random.seed(1)
    boxen = []
    for i in range(1500):
        b = Bnd_Box()
        x, y, z = random.uniform(0, 3000), random.uniform(0, 2000), random.uniform(0, 1500)
        b.Update(x, y, z, x + random.uniform(5, 400), y + random.uniform(5, 60), z + random.uniform(5, 60))
        b.Enlarge(3.0)
        boxen.append(b if i % 50 else Bnd_Box())
    uhr = time.perf_counter()
    jeder = [(i, j) for i in range(len(boxen)) for j in range(i + 1, len(boxen)) if not boxen[i].IsOut(boxen[j])]
    t_alt = time.perf_counter() - uhr
    uhr = time.perf_counter()
    neu = g._ueberlappende_paare(boxen)
    pruefe(neu == jeder, f"räumliche Paarsuche: {len(neu)} Paare wie jeder mit jedem, gleiche Reihenfolge "
                         f"({t_alt:.2f} s → {time.perf_counter() - uhr:.3f} s)")

    # 5. Schreiben aus zwei Threads
    import step_schreiben as sw
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    ergebnisse = {}

    def schreiben(n):
        for i in range(4):
            ziel = tmp / f"w_{n}_{i}.step"
            sw.form_schreiben(BRepPrimAPI_MakeBox(10 + n, 10, 10).Shape(), ziel, f"Produkt_{n}")
            ergebnisse.setdefault(n, []).append(ziel.read_text(encoding="latin-1"))
    th = [threading.Thread(target=schreiben, args=(n,)) for n in (1, 2)]
    for t in th:
        t.start()
    for t in th:
        t.join()
    pruefe(all(f"Produkt_{n}" in x and f"Produkt_{3 - n}" not in x for n in (1, 2) for x in ergebnisse.get(n, [])),
           "STEP-Schreiben aus zwei Threads: jede Datei mit eigenem Produktnamen")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{'FEHLER: ' + str(len(fehler)) if fehler else 'Alles in Ordnung'}")
sys.exit(1 if fehler else 0)
