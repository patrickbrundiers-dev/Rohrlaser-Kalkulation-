"""STEP-Export gegen die Mutter-STEP (Patrick 30.10.2026: „Prüfen, ob die STEP, die aus dem Editor kommt, mit der STEP
übereinstimmt, die in das Programm geladen wurde, wenn Steckverbindungen eingefügt oder sonstige Änderungen
vorgenommen wurden – nicht dass Geometrien aus der Mutter-STEP nicht mehr da sind, wo sie hingehören“).

- M1 Rahmen mit Gehrungen (R08, wie Patricks Rahmen RE 80x40x3): die gegenüberliegenden gleichen Rohre sind gewendet
  eingebaut. Ihre Lage wird zum Netz des ersten Körpers passend gemacht (vorher lagen sie im Export und in 3D
  gespiegelt, Gehrung nach innen, 13–25 % daneben). Export der Baugruppe: alle 4 Körper an ihrer Stelle, nur die
  2D-Gehrung (wie gelasert, Innenkante maßhaltig) weicht ab; unabhängige exakte Prüfung (Boolesche Schnittmenge je
  Körper) bestätigt das.
- M2 Steckverbindungen (S03): nach „Alle Stöße stecken“ liegen alle 6 Körper wie in der Mutter-STEP; nur Holme
  (Schlitze) und Streben (Nasen) sind örtlich geändert, Blech und Platte gleich.
- M3 Satz in 3D: dieselbe Prüfung im Fenster „Satz in 3D“.
- M4 Rohr-Editor: Einzelteil (Holm mit Schlitzen) und Blech-Editor (Platte aus B14) prüfen gegen ihren Körper der
  Mutter-STEP; eine zusätzliche Bohrung im Editor ist „örtlich geändert“, keine Lagewarnung.
- M5 Warnung: eine falsche Einbaulage (Holm 5 mm verschoben) und ein gespiegelter Gehrungsrahmen (ohne Abgleich) werden
  als „liegen nicht dort, wo sie in der Mutter-STEP liegen“ gemeldet; Mutter-STEP nicht mehr da: keine Prüfung, kein
  Fehler.
- M6 Gestell mit schräg eingebautem Rohr (T08): Schnittmenge mit Toleranz, alle Körper gleich.
- M7 Platten 120 × 120 × 10 mit 4 Bohrungen (wie in Patricks Gestell RE 140x80): am Netz ausgerichtet lagen sie
  0,05 mm daneben (Facetten der Bohrungen); jetzt exakt auf ihren Körper der Mutter-STEP nachgeführt.

Aufruf: python tests/test_step_mutter.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

HIER = Path(__file__).parent
PROGRAMM = HIER.parent / "programm"
sys.path[:0] = [str(PROGRAMM), str(PROGRAMM / "step_messung")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if find_spec("OCP") is None:
    print("OCP fehlt: übersprungen")
    sys.exit(0)
import step_messen  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from rohrlaser import baugruppe_step, lage_abgleich, schneidweg as sw, step, step_export  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.ansicht3d import entpacken  # noqa: E402
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.satz3d import Satz3dDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())


def ok(t):
    print("OK    ", t)


def einlesen(datei):
    """STEP wie im Programm übernehmen (mit Pfad der Kundendatei) -> (Datenbank, Angebot)."""
    t = tmp / datei.stem
    t.mkdir()
    step_messen.main(["--ausgabe", str(t / "m.txt"), "--json", str(t / "m.json"), "--netze", str(t / "netze"),
                      str(datei)])
    mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(t / "m.txt"), t / "netze"), t / "m.json")
    for x in mw:
        x.update(_saetze=1, _stueck=1, _baugruppe=True, _uebernehmen=True, _pfad=str(datei))
    db = Datenbank(t / "b.db")
    k = db.kontext()
    erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True,
                           zukauf_liste=[])
    db.profile_anlegen(erg["profile"])
    a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
    for p in erg["positionen"]:
        netz = p.pop("_netz", None)
        p.pop("_zukauf", None)
        pid = db.position_neu(a, p)
        if netz:
            db.netz_speichern(pid, netz)
    return db, a


def baugruppe_export(db, a, ziel):
    positionen = db.positionen(a)
    bgp = next(p for p in positionen if p.get("art") == BAUGRUPPE)
    d = BaugruppeDialog(None, bgp, positionen, db.tabellen(), {"Schweißen": 75.0}, db=db, netze=db.netze(a),
                        profile=db.kontext().profile)
    d.stumm = True
    assert d.step_speichern(str(ziel)) == str(ziel), d.step_ergebnis
    e = d.step_ergebnis
    d.close()
    return e


def status(e):
    return sorted((x["koerper_mutter"], x["status"]) for x in e["vergleich"]["koerper"])


def exakt(orig, neu):
    """Unabhängige Prüfung in einem eigenen Prozess (wie der Export; im Testprozess hat die Messung OpenCascade schon
    benutzt, dort scheitern Schnittmengen manchmal): je Körper der Mutter-STEP die Boolesche Schnittmenge mit jedem
    Exportkörper, der größte -> [(Abweichung / Volumen, Schwerpunkt-Abstand)]."""
    skript = (
        "import json, math, sys\n"
        "import step_vergleich as v\n"
        "o, n = v.mutter_lesen(sys.argv[1]), v.mutter_lesen(sys.argv[2])\n"
        "out = []\n"
        "for b in o:\n"
        "    g, a = max((((v._schnitt(a['k'], b['k']) or 0.0), a) for a in n), key=lambda x: x[0])\n"
        "    out.append(((a['v'] + b['v'] - 2 * g) / b['v'], math.dist(a['c'], b['c'])))\n"
        "print(json.dumps(out))\n")
    r = subprocess.run([sys.executable, "-c", skript, str(orig), str(neu)], capture_output=True, text=True,
                       cwd=PROGRAMM / "step_messung", timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


# ------------------------------------------------------------------ M1 Rahmen mit Gehrungen
r08 = HIER / "step_regression" / "R08_Rahmen_4xRE80x40x3_Gehrung.step"
db, a = einlesen(r08)
netze = {q["id"]: entpacken(db.netz(q["id"])) for q in db.positionen(a) if q.get("profil_id")}
assert all(len(n["lagen"]) == 2 for n in netze.values()) and all(n["mutter"] == str(r08) for n in netze.values())
lang = next(n for n in netze.values() if max(n["p"][2::3]) > 800)
assert [round(c, 6) + 0.0 for c in lang["lagen"][1][6:9]] == [0.0, 0.0, -1.0], lang["lagen"]   # um 180° gedreht
e = baugruppe_export(db, a, tmp / "r08.step")
assert status(e) == [(1, "geändert"), (2, "geändert"), (3, "geändert"), (4, "geändert")], e["vergleich"]
assert all("Gehrung in 2D" in " ".join(x["erwartet"]) for x in e["vergleich"]["koerper"])
assert all(x["schwerpunkt"] < 0.05 and x["anteil"] < 0.003 for x in e["vergleich"]["koerper"]), e["vergleich"]
text, warnen = step_export.vergleich_text(e["vergleich"])
assert not warnen and "4 Körper örtlich geändert" in text and "ACHTUNG" not in text, text
assert "Prüfung gegen die Mutter-STEP" in baugruppe_step.ergebnis_text(e, tmp / "r08.step")
werte = exakt(r08, tmp / "r08.step")
assert all(r < 0.003 and ds < 0.05 for r, ds in werte), werte
ok("M1 Gehrungsrahmen: gewendete gleiche Rohre richtig eingebaut, nur die 2D-Gehrung weicht ab (auch exakt geprüft)")

# ------------------------------------------------------------------ M5 Warnung (gespiegelt ohne Abgleich)
alt = lage_abgleich.passende_lage
lage_abgleich.passende_lage = lambda muster, k: (k.get("lage"), 0.0, 0.0)        # Stand vor dem Abgleich
shutil.copy(r08, tmp / "R08_alt.step")
db_alt, a_alt = einlesen(tmp / "R08_alt.step")
lage_abgleich.passende_lage = alt
e = baugruppe_export(db_alt, a_alt, tmp / "r08_alt.step")
lage = [x for x in e["vergleich"]["koerper"] if x["status"] == "lage"]
assert sorted(x["koerper_mutter"] for x in lage) == [3, 4] and all(x["schwerpunkt"] > 3 for x in lage), lage
text, warnen = step_export.vergleich_text(e["vergleich"])
assert warnen and "ACHTUNG: 2 Körper liegen nicht dort" in text, text
ok("M5 Gespiegelt eingebaute Rohre (alter Stand) werden gemeldet: ACHTUNG, 2 Körper liegen nicht dort")

# ------------------------------------------------------------------ M2 Steckverbindungen
s03 = HIER / "step_struktur" / "S03_Rahmen_geschweisst.step"
db, a = einlesen(s03)
e0 = baugruppe_export(db, a, tmp / "s03_0.step")
assert {s for _, s in status(e0)} == {"gleich"} and len(status(e0)) == 6, status(e0)
f = Hauptfenster(db, stumm=True)
seite = f.angebot_oeffnen(a)
i = next(i for i, q in enumerate(seite.positionen) if q.get("art") == BAUGRUPPE)
gesehen = {}


def stecken(d):
    gesehen["erg"] = d.steck_alle(melden=False)
    d._ok()
    return d.result()


assert seite.baugruppe_bearbeiten([i], dialog=stecken) and gesehen["erg"] == (3, 0), gesehen
e = baugruppe_export(db, a, tmp / "s03_1.step")
st = dict(status(e))
assert [st[k] for k in (1, 2, 3, 4)] == ["geändert"] * 4 and st[5] == st[6] == "gleich", st
grund = {x["koerper_mutter"]: x["erwartet"] for x in e["vergleich"]["koerper"]}
assert "Schlitze der Steckverbindung" in grund[1] and "Nasen der Steckverbindung" in grund[3], grund
assert all(x["schwerpunkt"] < 0.1 for x in e["vergleich"]["koerper"]) and not step_export.vergleich_text(
    e["vergleich"])[1]
assert all(r < 0.005 and ds < 0.1 for r, ds in exakt(s03, tmp / "s03_1.step"))
ok("M2 Steckverbindungen: alle 6 Körper an ihrer Stelle, nur Schlitze (Holme) und Nasen (Streben) geändert")

# ------------------------------------------------------------------ M3 Satz in 3D
positionen = db.positionen(a)
satz = [dict(q, satz="S1") for q in positionen if q.get("art") != BAUGRUPPE]
s = Satz3dDialog(None, "S1", satz, profile=db.kontext().profile, netze=db.netze(a), daten={})
s.stumm = True
assert s.step_speichern(str(tmp / "satz.step"))
assert len(s.step_ergebnis["vergleich"]["koerper"]) == 6 and not step_export.vergleich_text(
    s.step_ergebnis["vergleich"])[1], s.step_ergebnis["vergleich"]
s.close()
ok("M3 Satz in 3D: Prüfung gegen die Mutter-STEP wie im Editor der Baugruppe")

# ------------------------------------------------------------------ M4 Rohr- und Blech-Editor
holm = next(r for r, q in enumerate(seite.positionen) if q.get("laenge") and q["laenge"] > 900
            and q.get("art") != BAUGRUPPE)
erg = {}


def rohr_editor(d):
    d.stumm = True
    erg["pfad"] = d.step_speichern(str(tmp / f"holm{len(erg)}.step"))
    erg["e"] = d.step_ergebnis
    return QDialog.Rejected


seite.schneidweg_berechnen(holm, dialog=rohr_editor)
v = erg["e"]["vergleich"]
assert erg["pfad"] and len(v["koerper"]) == 1 and v["koerper"][0]["status"] == "geändert", v
assert v["koerper"][0]["schwerpunkt"] < 0.1 and "Schlitze der Steckverbindung" in v["koerper"][0]["erwartet"], v
assert "Prüfung gegen die Mutter-STEP" in step_export.ergebnis_text(erg["e"], erg["pfad"])
# zusätzliche Bohrung (im Editor gezeichnet): örtlich geändert, keine Lagewarnung
p_h = seite.positionen[holm]
e_h = sw.lesen(p_h["technik"])
e_h["konturen"] = list(e_h.get("konturen") or []) + [dict(art=sw.BOHRUNG, d=12, x=500, anzahl=1, seite="oben")]
plan = step_export.rohr_teil(e_h, db.kontext().profile[p_h["profil_id"]], p_h["laenge"], "Holm")
plan["erwartet"] = step_export.erwartet_rohr(e_h)
netz_h = entpacken(db.netz(p_h["id"]))
eb = step_export.schreiben(step_export.mutter_einzelteil(plan, netz_h, 0.0), tmp / "holm_bohrung.step", PROGRAMM)
k = eb["vergleich"]["koerper"][0]
assert k["status"] == "geändert" and k["abweichung"] > v["koerper"][0]["abweichung"] + 300, (k, v)
ok("M4a Rohr-Editor: Holm mit Schlitzen an seiner Stelle; zusätzliche Bohrung = örtlich geändert, keine Warnung")

b14 = HIER / "step_bleche" / "B14_Baugruppe_Rohr_2Bleche.step"
db_b, a_b = einlesen(b14)
from rohrlaser import blech  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
p_b = next(q for q in db_b.positionen(a_b) if blech.lesen(q.get("technik")))
bd = BlechDialog(None, db_b, blech.lesen(p_b["technik"]), dict(bezeichnung="Platte"), neu=False)
bd.p, bd.stumm = p_b, True             # wie AngebotSeite.blech_bearbeiten
erg_b = dict(pfad=bd.step_speichern(str(tmp / "platte.step")), e=bd.step_ergebnis)
bd.close()
vb = erg_b["e"]["vergleich"]
assert erg_b["pfad"] and len(vb["koerper"]) == 1 and vb["koerper"][0]["status"] == "gleich", vb
ok("M4b Blech-Editor: Platte genau wie ihr Körper in der Mutter-STEP")

# ------------------------------------------------------------------ M5 Warnung (verschoben, Datei fehlt)
positionen = db.positionen(a)
bgp = next(p for p in positionen if p.get("art") == BAUGRUPPE)
d = BaugruppeDialog(None, bgp, positionen, db.tabellen(), {"Schweißen": 75.0}, db=db, netze=db.netze(a),
                    profile=db.kontext().profile)
eintraege = d.step_eintraege()
d.close()
x = next(x for x in eintraege if x["rohr"] and len((x["netz"] or {}).get("lagen") or ()) == 2)
x["netz"] = dict(x["netz"], lagen=[list(x["netz"]["lagen"][0]), list(x["netz"]["lagen"][1])])
x["netz"]["lagen"][1][0] += 5.0                     # zweiter Holm 5 mm daneben
plan, _ = baugruppe_step.bauplan("Test", eintraege)
e5 = step_export.schreiben(plan, tmp / "verschoben.step", PROGRAMM)
lage = [k for k in e5["vergleich"]["koerper"] if k["status"] == "lage"]
assert len(lage) == 1 and 4 < lage[0]["schwerpunkt"] < 6, e5["vergleich"]
assert step_export.vergleich_text(e5["vergleich"])[1]
weg = dict(x, netz=dict(x["netz"], mutter=str(tmp / "gibt_es_nicht.step")))
plan_w, _ = baugruppe_step.bauplan("Test", [weg])
assert "mutter" not in plan_w and baugruppe_step._mutter_nr([], None) is None
ok("M5 Holm 5 mm verschoben: Warnung; Mutter-STEP nicht mehr da: keine Prüfung, Export läuft")

# ------------------------------------------------------------------ M6 schräges Rohr
t08 = HIER / "step_satz" / "T08_Gestell_Baugruppe.step"
db, a = einlesen(t08)
e = baugruppe_export(db, a, tmp / "t08.step")
assert {s for _, s in status(e)} == {"gleich"} and len(status(e)) == 4, e["vergleich"]
ok("M6 Gestell mit schräg eingebautem Rohr: alle 4 Körper gleich (Schnittmenge mit Toleranz)")
# ------------------------------------------------------------------ M7 Platten exakt nachgeführt
from OCP.BRep import BRep_Builder  # noqa: E402
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer  # noqa: E402
from OCP.TopoDS import TopoDS_Compound  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402


def platte(x0, y0, z0):
    k = BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), 120, 120, 10).Shape()
    for x, y in ((20, 20), (100, 20), (20, 100), (100, 100)):
        k = BRepAlgoAPI_Cut(k, BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x0 + x, y0 + y, z0 - 1), gp_Dir(0, 0, 1)),
                                                        5.5, 12).Shape()).Shape()
    return k


bb, comp = BRep_Builder(), TopoDS_Compound()
bb.MakeCompound(comp)
for lage in ((0, -25, 2800), (700, -25, 2800), (0, 400, 0)):
    bb.Add(comp, platte(*lage))
w = STEPControl_Writer()
w.Transfer(comp, STEPControl_AsIs)
platten = tmp / "Platten_120x120x10.step"
w.Write(str(platten))
db, a = einlesen(platten)
e = baugruppe_export(db, a, tmp / "platten.step")
assert len(status(e)) == 3 and {s_ for _, s_ in status(e)} == {"gleich"}, e["vergleich"]
assert all(k["schwerpunkt"] < 0.001 for k in e["vergleich"]["koerper"]), e["vergleich"]
ok("M7 Platten 120×120×10 mit 4 Bohrungen: am Netz ausgerichtet und exakt auf die Mutter-STEP nachgeführt")
f.close()
print("Alle Tests STEP-Export gegen Mutter-STEP bestanden.")
