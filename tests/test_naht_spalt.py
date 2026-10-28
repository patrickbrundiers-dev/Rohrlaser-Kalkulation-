"""Schweißstoß mit Spalt (Patrick 26.10.2026: „zwischen Blech und Rohr war ein Spalt, dort wurde kein Schweißen
gerechnet, auch wurde dort nicht graviert“; Plan Spalt_Naht_Gravur, Freigabe „Alle a“):
- N1 Blech flach mit Spalt 0,5 / 1,5 / 3 mm neben dem Rechteckrohr: Nahtkandidat (Kehlnaht, Umfang der Auflage) mit
  spalt_mm, Anbauteil mit Umriss-Gravur genau wie ohne Spalt (Lage und Länge), Vertrauen „prüfen“; ohne Spalt
  unverändert (kein Feld spalt)
- N2 Spalt 4 mm (über step_naht_spalt 3 mm): keine Naht, beide Körper in "ohne_naht"; mit Einstellung 5 mm erkannt
- N3 Rohrende mit Spalt vor der Kopfplatte: Kehlnaht mit der Schnittlänge des Endes wie ohne Spalt
- N4 Die Datei bleibt unverändert, das Blech wird nicht verschoben (Grundregel 25.10.: Lage wie STEP)
- N8 Rohr durch ein Blech gesteckt (mit und ohne Spalt): Naht rundum = Außenumfang, beidseitig (S8)
- N5 Programm: Nahtvorschlag mit Spalt, Prüfregel „Spalt zu groß“ (schweiss_spalt_max), Teile ohne Naht als Warnung,
  Einstellung geht als --naht-spalt an die Messung

Aufruf: python tests/test_naht_spalt.py
"""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
from importlib.util import find_spec
from pathlib import Path

HIER = Path(__file__).parent
PROGRAMM = HIER.parent / "programm"
sys.path[:0] = [str(HIER), str(PROGRAMM), str(PROGRAMM / "step_messung")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if find_spec("OCP") is None:
    print("OCP fehlt: übersprungen")
    sys.exit(0)
import step_ergebnis  # noqa: E402
import step_geometrie as sg  # noqa: E402
import step_messen  # noqa: E402
from erzeuge_testteile import baugruppe as zusammen, kastenrohr, rundrohr, schreibe, zylinder  # noqa: E402
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402
from rohrlaser import baugruppe, step, step_einstellungen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())
UMRISS = 2 * (150 + 40 - 2 * 4)         # Blech 150 lang auf der geraden Seite (40 - 2 Radien) des RE 60x40
ENDE = 2 * (60 + 40) - 8 * 4 + 2 * 3.141592653589793 * 4


def ok(t):
    print("OK    ", t)


def box(x, y, z, dx, dy, dz):
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape()


def datei(name, *koerper):
    with contextlib.redirect_stdout(io.StringIO()):
        schreibe(zusammen(*koerper), name, tmp)
    return tmp / f"{name}.step"


def blech_datei(spalt):
    return datei(f"blech_{spalt:g}", kastenrohr(60, 40, 3, 1000, 4), box(30 + spalt, -30, 600, 8, 60, 150))


def nah(ist, soll, tol, was):
    assert ist is not None and abs(ist - soll) <= tol, f"{was}: ist {ist}, soll {soll:.2f}"


# N1 Blech mit Spalt
ohne = sg.analysiere_datei(blech_datei(0))
a0 = ohne[0].anbauteile[0]
assert "spalt" not in a0 and a0["vertrauen"] == "sicher" and "spalt_mm" not in ohne[0].naehte[0]
for spalt in (0.5, 1.5, 3.0):
    t = sg.analysiere_datei(blech_datei(spalt))
    assert len(t[0].naehte) == 1, (spalt, t[0].naehte)
    n = t[0].naehte[0]
    assert n["stossart"] == "Kehlnaht" and sorted(n["teile"]) == [1, 2], n
    nah(n["laenge_mm"], UMRISS, 5, f"Naht bei Spalt {spalt}")
    nah(n["spalt_mm"], spalt, 0.01, "Spalt")
    assert len(t[0].anbauteile) == 1, t[0].anbauteile
    a = t[0].anbauteile[0]
    assert a["art"] == a0["art"] == "Blech" and a["bearbeitung"] == "Umriss", a
    nah(a["gravur_laenge"], a0["gravur_laenge"], 0.05, "Umriss-Gravur wie ohne Spalt")
    nah(a["z"], a0["z"], 0.01, "Lage z")
    assert a["winkel"] == a0["winkel"] and a["seite"] == a0["seite"], (a["winkel"], a["seite"])
    assert a["umriss_linien"] == a0["umriss_linien"], "Gravur genau unter dem Blech"
    assert a["vertrauen"] == "prüfen" and a["spalt"] == spalt and "Spalt" in a["hinweis"], a
    assert any("Spalt" in h for h in t[0].hinweise), t[0].hinweise
    nah(t[0].gravur, ohne[0].gravur, 0.05, "Gravur des Rohrs")
    assert t[0].ohne_naht == [], t[0].ohne_naht
ok("N1 Blech mit Spalt 0,5 / 1,5 / 3 mm: Kehlnaht + Umriss-Gravur wie ohne Spalt, prüfen")

# N2 Spalt über der Einstellung
t = sg.analysiere_datei(blech_datei(4))
assert t[0].naehte == [] and t[0].anbauteile == [] and t[0].ohne_naht == [1, 2], (t[0].naehte, t[0].ohne_naht)
assert step_ergebnis.datei("x", t)["ohne_naht"] == [1, 2]
sg.einstellen({"naht_spalt": 5})
try:
    t = sg.analysiere_datei(blech_datei(4))
    assert len(t[0].naehte) == 1 and t[0].naehte[0]["spalt_mm"] == 4 and t[0].anbauteile, t[0].naehte
finally:
    sg.einstellen({})
assert sg.NAHT_SPALT == 3.0
ok("N2 Spalt 4 mm: ohne Naht gemeldet, mit Einstellung 5 mm erkannt")

# N3 Rohrende mit Spalt vor der Kopfplatte
for spalt in (0.0, 1.0, 2.5):
    t = sg.analysiere_datei(datei(f"kopf_{spalt:g}", kastenrohr(60, 40, 3, 1000, 4),
                                  box(-50, -40, 1000 + spalt, 100, 80, 8)))
    assert len(t[0].naehte) == 1, t[0].naehte
    nah(t[0].naehte[0]["laenge_mm"], ENDE, 0.2, f"Naht am Ende, Spalt {spalt}")
    assert t[0].naehte[0].get("spalt_mm", 0) == spalt
    assert t[0].anbauteile and t[0].anbauteile[0]["art"] == "Kopfplatte"
ok("N3 Rohrende mit Spalt vor der Kopfplatte: Naht = Schnittlänge des Endes")

# N4 Datei und Lage des Blechs unverändert
pfad = blech_datei(1.5)
vorher = hashlib.sha256(pfad.read_bytes()).hexdigest()
t = sg.analysiere_datei(pfad)
assert hashlib.sha256(pfad.read_bytes()).hexdigest() == vorher
assert t[1].bauteiltyp == "Blech", t[1].bauteiltyp
assert t[1].ende_a_global == ohne[1].ende_a_global or t[1].huelle == ohne[1].huelle, "Blech gleich gemessen"
ok("N4 Datei unverändert, Blech bleibt an seiner Stelle")

# N5 Programm: Vorschlag mit Spalt, Prüfregel, Teile ohne Naht, Einstellung
def importieren(pfad):
    d = tmp / ("imp_" + pfad.stem)
    d.mkdir()
    step_messen.main(["--ausgabe", str(d / "m.txt"), "--json", str(d / "m.json"), "--netze", str(d / "n"),
                      "--naht-spalt", "3", str(pfad)])
    assert json.loads((d / "m.json").read_text(encoding="utf-8"))["schema_version"] == step_ergebnis.SCHEMA_VERSION
    mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(d / "m.txt"), d / "n"), d / "m.json")
    for x in mw:
        x.update(_saetze=1, _stueck=1, _baugruppe=True, _uebernehmen=True)
    db = Datenbank(d / "b.db")
    erg = step.uebernehmen(mw, [], db.kontext(), db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True,
                           zukauf_liste=[])
    bg_pos = next(p for p in erg["positionen"] if p.get("baugruppe"))
    return baugruppe.lesen(bg_pos["baugruppe"]), erg["bericht"], db


bg, bericht, db = importieren(blech_datei(3))
assert len(bg["vorschlaege"]) == 1 and bg["vorschlaege"][0]["spalt"] == 3, bg["vorschlaege"]
assert any("mit Spalt" in z for z in bericht), bericht
naht = baugruppe.vorschlag_naht(bg["vorschlaege"][0], 0.7)
assert naht["spalt"] == 3 and naht["nahtart"] == "Kehlnaht" and naht["mass"] == 2.0, naht
assert baugruppe.SPALT_MAX == 2.0
assert "Spalt 3 mm" in (baugruppe.spalt_zu_gross(bg) or ""), baugruppe.spalt_zu_gross(bg)
baugruppe.SPALT_MAX = 3.0
assert baugruppe.spalt_zu_gross(bg) is None
db.einstellung_setzen("schweiss_spalt_max", 2.5)
step_einstellungen.anwenden(db)
assert baugruppe.SPALT_MAX == 2.5 and "Spalt 3 mm" in baugruppe.spalt_zu_gross(bg)
p = dict(stueck=1, baugruppe=baugruppe.speichern(bg))
assert baugruppe.status(p, {}).startswith("WARNUNG: Nahtvorschlag: Spalt 3 mm"), baugruppe.status(p, {})
db.einstellung_setzen("step_naht_spalt", 4)
args = step_einstellungen.mess_argumente(db)
assert args[args.index("--naht-spalt") + 1] == "4", args
db.einstellung_setzen("schweiss_spalt_max", 2.0)
step_einstellungen.anwenden(db)

bg, bericht, _ = importieren(blech_datei(4))
assert bg["vorschlaege"] == [] and [x["koerper"] for x in bg["ohne_naht"]] == ["1", "2"], bg.get("ohne_naht")
assert any("ohne Naht" in z for z in bericht), bericht
assert len(baugruppe.ohne_naht(bg)) == 2
p = dict(stueck=1, baugruppe=baugruppe.speichern(bg))
assert "ohne Naht zu einem anderen Teil" in baugruppe.status(p, {}), baugruppe.status(p, {})
bg["naehte"].append(dict(id="n1", nr="1", nahtart="Kehlnaht", laenge=100, koerper=["1", "2"]))
assert baugruppe.ohne_naht(bg) == []
bg["naehte"][0].pop("koerper")
assert baugruppe.ohne_naht(bg) == [], "Naht von Hand: keine Meldung mehr"
ok("N5 Programm: Vorschlag mit Spalt, Prüfregel, Teile ohne Naht, Einstellungen")

# N6 Spalt in der Rechnung (S3): mehr Schweißgut, gelb bis bestätigt
nah(baugruppe.spalt_faktor(dict(nahtart="Kehlnaht", mass=3, spalt=1.5)), 4.5 ** 2 / 9, 1e-9, "Kehlnaht a + Spalt")
nah(baugruppe.spalt_faktor(dict(nahtart="Stumpfnaht", mass=3, spalt=1)),
    (baugruppe.nahtquerschnitt("Stumpfnaht", 3) + 3.3) / baugruppe.nahtquerschnitt("Stumpfnaht", 3), 1e-9, "Stumpf")
assert baugruppe.spalt_faktor(dict(nahtart="Kehlnaht", mass=3)) == 1.0
assert baugruppe.spalt_faktor(dict(nahtart="Kehlnaht", mass=3, spalt=0)) == 1.0
assert baugruppe.spalt_faktor(dict(nahtart="Kehlnaht", spalt=2)) == 1.0, "ohne a-Maß kein Faktor"
tab = baugruppe.richtwerte()
vf = next(z["verfahren"] for z in tab["schweissverfahren"])
satz = {z.get("satz_id"): 60.0 for z in tab["schweissverfahren"]}
ohne_s = baugruppe.naht_rechnen(dict(verfahren=vf, nahtart="Kehlnaht", mass=3, laenge=500), tab, satz)
mit_s = baugruppe.naht_rechnen(dict(verfahren=vf, nahtart="Kehlnaht", mass=3, laenge=500, spalt=1.5), tab, satz)
assert ohne_s["lichtbogen_min"] > 0 and ohne_s["spalt_faktor"] == 1.0, ohne_s
nah(mit_s["lichtbogen_min"], ohne_s["lichtbogen_min"] * 2.25, 1e-9, "Lichtbogenzeit × Faktor")
assert mit_s["kosten"] > ohne_s["kosten"]
n = dict(id="x", nr="2", verfahren=vf, nahtart="Kehlnaht", mass=3, laenge=500, spalt=1.5)
assert baugruppe.spalt_offen(n)
bg = baugruppe.leer()
bg["naehte"].append(n)
assert baugruppe.status(dict(stueck=1, baugruppe=baugruppe.speichern(bg)), dict(bg_tabellen=tab, saetze=satz)) == \
    "HINWEIS: Nahtgruppe 2: Spalt 1,5 mm eingerechnet (a + Spalt), bitte bestätigen", "Hinweis bis bestätigt"
n["spalt_ok"] = True
assert not baugruppe.spalt_offen(n)
ok("N6 Spalt in der Rechnung: a + Spalt, Zeit und Kosten steigen, Hinweis bis bestätigt")

# N7 Editor: übernommene Naht mit Spalt, bestätigen, Naht mit Spalt im 3D zeichnen
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.baugruppe_dialog import BaugruppeDialog  # noqa: E402
app = QApplication.instance() or QApplication([])
d_ = tmp / "editor"
d_.mkdir()
step_messen.main(["--ausgabe", str(d_ / "m.txt"), "--json", str(d_ / "m.json"), "--netze", str(d_ / "n"),
                  str(blech_datei(1.5))])
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(d_ / "m.txt"), d_ / "n"), d_ / "m.json")
for x in mw:
    x.update(_saetze=1, _stueck=1, _baugruppe=True, _uebernehmen=True)
db = Datenbank(d_ / "b.db")
k = db.kontext()
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True, zukauf_liste=[])
db.profile_anlegen(erg["profile"])
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
for p in erg["positionen"]:
    netz = p.pop("_netz", None)
    p.pop("_zukauf", None)
    pid = db.position_neu(a, p)
    if netz:
        db.netz_speichern(pid, netz)
positionen = db.positionen(a)
bgp = next(p for p in positionen if p.get("art") == BAUGRUPPE)
d = BaugruppeDialog(None, bgp, positionen, db.tabellen(), {"Schweißen": 75.0}, db=db, netze=db.netze(a),
                    einstellungen={"step_naht_spalt": 3.0})
d.vorschlaege_uebernehmen([0])
neu = d.bg["naehte"][-1]
assert neu["spalt"] == 1.5 and neu["nahtart"] == "Kehlnaht" and sorted(neu["koerper"]) == ["1", "2"], neu
neu["mass"] = 3
assert baugruppe.spalt_offen(neu)
d.regel_bestaetigen([len(d.bg["naehte"]) - 1])
assert neu.get("spalt_ok") and not baugruppe.spalt_offen(neu)
# gezeichnet auf der Rohrwand unter dem Blech (x = 30), das Blech liegt 1,5 mm daneben
d.reiter.setCurrentIndex(d.BAUM)                          # 3D der ganzen Baugruppe
d.zeige_3d()
assert d._koerper_3d, "3D-Körper fehlen"
nid = d.naht_aus_punkten([(30.0, -16.0, 600.0), (30.0, -16.0, 750.0)], nahtart="Kehlnaht")
gez = next(x for x in d.bg["naehte"] if x["id"] == nid)
assert sorted(gez.get("koerper") or []) == ["1", "2"] and gez.get("spalt") == 1.5, gez
nid = d.naht_aus_punkten([(30.0, -16.0, 100.0), (30.0, -16.0, 250.0)], nahtart="Kehlnaht")
gez = next(x for x in d.bg["naehte"] if x["id"] == nid)
assert gez.get("koerper") == ["1"] and "spalt" not in gez, "weit weg vom Blech: nur das Rohr"
ok("N7 Editor: Naht mit Spalt übernehmen und bestätigen, Naht mit Spalt im 3D zeichnen")

# N8 Rohr durch ein Blech gesteckt
for spalt in (0.0, 1.0):
    platte = BRepAlgoAPI_Cut(box(-100, -100, 400, 200, 200, 10),
                             zylinder((0, 0, 390), (0, 0, 1), 42.4 + 2 * spalt, 30)).Shape()
    t = sg.analysiere_datei(datei(f"durch_{spalt:g}", rundrohr(42.4, 2, 1000), platte))
    assert len(t[0].naehte) == 1, t[0].naehte
    n = t[0].naehte[0]
    nah(n["laenge_mm"], 42.4 * 3.141592653589793, 0.2, f"Umfang, Spalt {spalt}")
    assert n["beidseitig"] is True and n["stossart"] == "Kehlnaht", n
    v = baugruppe.vorschlaege_aus_step(baugruppe.leer(), t[0].naehte)
    assert v[0]["beidseitig"] and baugruppe.vorschlag_naht(v[0])["beidseitig"], v
t = sg.analysiere_datei(blech_datei(1.5))
assert "beidseitig" not in t[0].naehte[0], "Blech außen auf dem Rohr: nicht beidseitig"
ok("N8 Rohr durch Blech gesteckt: rundum = Außenumfang, beidseitig")
