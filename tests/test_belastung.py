"""Belastungstest (Performance-Update 25.10.2026, Patrick: „Belastungstest Rundrohr 84x2 mit 7000 Bohrungen“):
Rundrohr 84 × 2 mit N radialen Bohrungen Ø 6 (20 je Umfang), Vorgabe N = 200; von Hand auch 1.000 oder 7.000.
- B1 STEP-Messung findet Rundrohr 84 × 2 und alle N Bohrungen.
- B2 Übernahme ins Angebot, Neuladen, Rohr-Editor öffnen und eine Änderung rechnen.
- B3 3D-Netz aus den Eingaben: zweiter Aufruf aus dem Merker (gleich, Kopie), Abwicklung der Werkstattpapiere.
- B4 STEP-Export: gültiger Körper mit N Bohrungen, Werkzeuge gruppiert (wenige Durchgänge statt N).
- B5 Angebots-PDF, Werkstattpapiere, Kalkulation-PDF.
Jeder Schritt mit Zeitgrenze (großzügig, Rechner im Workflow sind langsam); die Zeiten stehen in der Ausgabe.
Langsamer Test (tests/alle.py --langsam).

Aufruf: python tests/test_belastung.py [N]
"""
import json
import math
import os
import subprocess
import sys
import tempfile
import time
from importlib.util import find_spec
from pathlib import Path

HIER = Path(__file__).resolve().parent
PROGRAMM = HIER.parent / "programm"
sys.path[:0] = [str(PROGRAMM), str(HIER), str(PROGRAMM / "step_messung")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])
N = int(sys.argv[1]) if len(sys.argv) > 1 else 200
JE_UMFANG = 20
# Zeitgrenzen [s] für N = 200 (wachsen linear mit N)
GRENZEN = dict(messung=90, uebernahme=30, editor=40, aendern=40, netz=20, export=90, pdf=60)


def grenze(name):
    return GRENZEN[name] * max(1.0, N / 200)


def ok(t):
    print("OK    ", t, flush=True)


def fehler(t):
    print("FEHLER", t, flush=True)
    sys.exit(1)


def gemessen(name, fn):
    t = time.perf_counter()
    r = fn()
    for _ in range(3):
        APP.processEvents()
    dt = time.perf_counter() - t
    if dt > grenze(name.split()[0]):
        fehler(f"{name}: {dt:.1f} s (Grenze {grenze(name.split()[0]):.0f} s)")
    print(f"       {name}: {dt:.1f} s", flush=True)
    return r


def lochrohr(ziel):
    from erzeuge_testteile import rundrohr
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.collections import List_TopoDS_Shape
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    reihen = N // JE_UMFANG
    rohr = rundrohr(84, 2, 50 + 10 * reihen)
    werkzeuge, argumente = List_TopoDS_Shape(), List_TopoDS_Shape()
    for j in range(reihen):
        for i in range(JE_UMFANG):
            w = 2 * math.pi * (i + 0.5 * (j % 2)) / JE_UMFANG
            d = (math.cos(w), math.sin(w), 0)
            werkzeuge.Append(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(39 * d[0], 39 * d[1], 30 + 10 * j), gp_Dir(*d)),
                                                      3, 6).Shape())
    argumente.Append(rohr)
    c = BRepAlgoAPI_Cut()
    c.SetArguments(argumente)
    c.SetTools(werkzeuge)
    c.SetRunParallel(True)
    c.Build()
    w = STEPControl_Writer()
    w.Transfer(c.Shape(), STEPControl_AsIs)
    w.Write(str(ziel))
    return 50 + 10 * reihen


if find_spec("OCP") is None:
    print("OpenCascade (OCP) fehlt: Belastungstest übersprungen.")
    sys.exit(0)

from rohrlaser import rohr3d, schneidweg as sw, step, step_export as se, stangen_abwicklung  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

tmp = Path(tempfile.mkdtemp())
datei = tmp / f"RR84x2_{N}.step"
laenge = lochrohr(datei)
print(f"       Testteil: {datei.name}, {datei.stat().st_size / 1e6:.1f} MB, Länge {laenge} mm", flush=True)

# B1 Messung
ausgabe, netze, js = tmp / "m.txt", tmp / "netze", tmp / "m.json"
gemessen("messung (STEP-Import)", lambda: subprocess.run(
    [sys.executable, str(PROGRAMM / "step_messung" / "step_messen.py"), "--ausgabe", str(ausgabe), "--netze",
     str(netze), "--json", str(js), str(datei)], check=True, capture_output=True))
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(ausgabe), netze), js)
m = mw[0]
if m.get("profilform") != "Rundrohr" or abs(float(m["abm_a"]) - 84) > 0.01 or abs(float(m["wandstaerke"]) - 2) > 0.01 \
        or m.get("bohrungen") != f"6.0:{N}":
    fehler(f"B1 Messung {m.get('profilform')} {m.get('abm_a')} × {m.get('wandstaerke')}, Bohrungen {m.get('bohrungen')}")
ok(f"B1 STEP-Messung: Rundrohr 84 × 2, Länge {float(m['laenge']):.1f} mm, {N} Bohrungen Ø 6")

# B2 Angebot und Editor
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, PROGRAMM, stumm=True)
f.show()
aid = db.angebot_neu(dict(kunde="Belastungstest"))
S = f.angebot_oeffnen(aid)
S.step_messen = lambda *a, **k: (mw, None) if k.get("mit_ablage") else mw
gemessen("uebernahme ins Angebot", lambda: S.step_importieren([str(datei)], stueck=10))
p = next(q for q in S.positionen if q.get("profil_id"))
e = json.loads(p["technik"])
bohrungen = sum(int(k.get("anzahl") or 1) for k in e.get("konturen") or [])
if bohrungen != N:
    fehler(f"B1 Bohrungen {bohrungen} statt {N}")
ok(f"B1 alle {N} Bohrungen erkannt")
gemessen("uebernahme Neuladen", S.neu_laden)
prof = S.k.profile[p["profil_id"]]


def editor():
    d = SchneidwegDialog(S, p, prof, S.kopf, S.k, S.tabellen, db, S.positionen)
    d.show()
    return d


D = gemessen("editor öffnen", editor)
gemessen("aendern (neu rechnen, Baum, 3D)", lambda: (D.rechnen(), D.editor.aktualisieren()))
D.reject()
ok("B2 Übernahme, Neuladen, Rohr-Editor öffnen und ändern")

# B3 Netz aus dem Merker
profil = sw.mit_radius(prof, e)
n1 = gemessen("netz (rohr3d, erster Aufruf oder Merker)", lambda: rohr3d.netz(e, profil, float(p["laenge"])))
t = time.perf_counter()
n2 = rohr3d.netz(e, profil, float(p["laenge"]))
if n1 != n2 or n1 is n2 or n1["p"] is n2["p"] or time.perf_counter() - t > 2:
    fehler("B3 Netz aus dem Merker nicht gleich, keine Kopie oder zu langsam")
n2["p"][0] += 1
if rohr3d.netz(e, profil, float(p["laenge"]))["p"][0] == n2["p"][0]:
    fehler("B3 Änderung an der Kopie ändert den Merker")
ok(f"B3 3D-Netz {len(n1['p']) // 3} Punkte, zweiter Aufruf aus dem Merker als Kopie")

# B4 STEP-Export
plan = se.rohr_teil(e, profil, float(p["laenge"]), "Belastung")
if se.werkzeug_zahl([plan]) < N:
    fehler(f"B4 nur {se.werkzeug_zahl([plan])} Werkzeuge")
if se.zeitlimit_fuer([plan]) < se.ZEITLIMIT + se.ZEIT_JE_WERKZEUG * N:
    fehler("B4 Zeitlimit wächst nicht mit den Werkzeugen")
erg = gemessen("export (STEP schreiben)", lambda: se.schreiben([plan], tmp / "export.step", PROGRAMM))
if not erg.get("ok") or erg["teile"][0]["flaechen"] < N:
    fehler(f"B4 Export {erg}")
ok(f"B4 STEP-Export gültig, {erg['teile'][0]['flaechen']} Flächen, Volumen {erg['teile'][0]['volumen'] / 1000:.1f} cm³")

# B5 PDFs
gemessen("pdf Optimieren + Angebot + Werkstatt + Kalkulation", lambda: (
    S.optimieren(), S.angebot_pdf(), S.werkstatt_pdf(), S.kalkulation_pdf()))
merker = {}
s0 = (S.ergebnis or {}).get("stangen") or []
if s0:
    profil_von = stangen_abwicklung.profil_funktion(S.kopf, S.k)
    a1 = stangen_abwicklung.stange(s0[0], S.positionen, profil_von, merker)
    a2 = stangen_abwicklung.stange(s0[0], S.positionen, profil_von)
    if a1 != a2:
        fehler("B5 Abwicklung mit Merker anders als ohne")
ok("B5 Optimieren, Angebots-PDF, Werkstattpapiere, Kalkulation-PDF")
print(f"Belastungstest mit {N} Bohrungen bestanden.")
os._exit(0)
