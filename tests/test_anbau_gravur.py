"""Gravur der Anbauteile im 3D aus den Eingaben und im STEP-Export (Patrick 25.10.2026: „Gravuren, die von
Anbauteilen erstellt werden, im 3D als Gravur 0,1 mm sichtbar?“):
- A1 Die STEP-Messung speichert je Anbauteil die Lage der Gravur (Mitte, Richtung, Normale) und den Umriss.
- A2 3D aus den Eingaben (Rohr-Editor, Positions-3D): die Gravur der Anbauteile liegt genau auf den Linien der
  STEP-Messung (0,4 mm über der Wand), bei Rechteck-, Quadrat- und Rundrohr.
- A3 Bearbeitung geändert (Umriss -> Positionsmarke / Punktmarke) bzw. ausgeschlossen: das 3D zeigt die neue Wahl.
- A4 STEP-Export: die Gravur der Anbauteile ist eine Rille (0,1 mm tief) im Rohr, der Körper bleibt gültig.

Aufruf: python tests/test_anbau_gravur.py
"""
import json
import math
import os
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
from rohrlaser import anbau, ansicht3d, rohr3d, schneidweg as sw, step, step_export as se  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def einlesen(name):
    """STEP aus tests/step_anbau messen und übernehmen -> (Position, Profil, Netz der Messung)."""
    t = Path(tempfile.mkdtemp())
    step_messen.main(["--ausgabe", str(t / "m.txt"), "--json", str(t / "m.json"), "--netze", str(t / "n"),
                      str(HIER / "step_anbau" / f"{name}.step")])
    mw = step.lade_netze(step.lies_messwerte(t / "m.txt"), t / "n")
    for x in mw:
        x.update(_saetze=1, _stueck=1, _uebernehmen=True)
    db = Datenbank(t / "b.db")
    erg = step.uebernehmen(mw, [], db.kontext(), db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True,
                           zukauf_liste=[])
    db.profile_anlegen(erg["profile"])
    p = erg["positionen"][0]
    netz = p.get("_netz")
    return p, db.kontext().profile[p["profil_id"]], ansicht3d.entpacken(netz) if isinstance(netz, bytes) else netz


def punkte(zuege):
    """Anfang und Ende je Linienzug (das Kreuz hat im Modell Zwischenpunkte auf dem Mantel)."""
    return [tuple(z[i:i + 3]) for z in zuege for i in (0, len(z) - 3)]


def modell(p, profil):
    e = sw.aus_position(sw.lesen(p.get("technik")), p, profil)[0]
    return rohr3d.netz(anbau.eingaben_mit_gravur(e, p), profil, p["laenge"]), e


faelle = {}
for name in ("A03_QR40x3_4Bolzen", "A05_RE80x40x3_3Laschen", "A04_RR42-4x2_Blech"):
    faelle[name] = einlesen(name)

# ------------------------------------------------------------------ A1 Messung
for name, (p, _profil, _netz) in faelle.items():
    liste = anbau.lesen(p["anbauteile"])
    assert liste and all(a.get("marke") for a in liste), name
    assert all(a.get("umriss_linien") for a in liste if a["bearbeitung"] == "Umriss"), name
ok("A1 STEP-Messung: je Anbauteil Lage der Gravur und Umriss")

# ------------------------------------------------------------------ A2 3D aus den Eingaben
for name, (p, profil, netz) in faelle.items():
    n, _e = modell(p, profil)
    ga, mga = punkte(n["l"]["GA"]), punkte(netz["l"]["GA"])
    assert len(n["l"]["GA"]) == len(netz["l"]["GA"]), name
    assert max(math.dist(a, b) for a, b in zip(ga, mga)) < 0.41, name           # 0,4 mm über der Wand
    if profil["form"] == "Rundrohr":
        alle = [n["l"]["GA"][k][i:i + 2] for k in range(len(n["l"]["GA"])) for i in range(0, len(n["l"]["GA"][k]), 3)]
        assert all(abs(math.hypot(x, y) - profil["a"] / 2 - rohr3d.ABSTAND) < 0.01 for x, y in alle), name
ok("A2 3D aus den Eingaben: Gravur der Anbauteile auf den Linien der STEP-Messung (Rechteck-, Quadrat-, Rundrohr)")

# ------------------------------------------------------------------ A3 Bearbeitung geändert
p, profil, _ = faelle["A05_RE80x40x3_3Laschen"]
liste = anbau.lesen(p["anbauteile"])
umriss = len(modell(p, profil)[0]["l"]["GA"])
liste[0]["bearbeitung"], liste[0]["gravur_laenge"] = "Positionsmarke", anbau.MARKE
liste[1]["bearbeitung"], liste[1]["gravur_laenge"] = "Punktmarke", anbau.PUNKT
liste[2]["status"] = anbau.AUSGESCHLOSSEN
p2 = dict(p, anbauteile=json.dumps(liste))
n2 = modell(p2, profil)[0]
assert umriss == 12 and len(n2["l"]["GA"]) == 4, n2["l"]["GA"]
laengen = sorted(round(math.dist(z[:3], z[-3:]), 1) for z in n2["l"]["GA"])
assert laengen == [2.0, 2.0, 10.0, 10.0], laengen
assert "GA" not in (modell(dict(p, anbauteile=json.dumps([dict(a, marke=None) for a in liste])), profil)[0]["l"])
ok("A3 Bearbeitung Positionsmarke / Punktmarke / ausgeschlossen: 3D zeigt die neue Wahl; alte Messung ohne Lage: "
   "keine Linien")

# ------------------------------------------------------------------ A4 STEP-Export
tmp = Path(tempfile.mkdtemp())
for name in ("A05_RE80x40x3_3Laschen", "A04_RR42-4x2_Blech"):
    p, profil, _ = faelle[name]
    e = sw.aus_position(sw.lesen(p.get("technik")), p, profil)[0]
    mit, ohne = se.rohr_teil(anbau.eingaben_mit_gravur(e, p), profil, p["laenge"]), se.rohr_teil(e, profil, p["laenge"])
    assert len(mit["rillen"]) > len(ohne["rillen"]) == 0, name
    erg = se.schreiben([mit, ohne], tmp / f"{name}.step", PROGRAMM)
    a, b = erg["teile"]
    soll = anbau.gravur(anbau.lesen(p["anbauteile"])) * se.GRAVUR_BREITE * se.GRAVUR_TIEFE
    assert erg["ok"] and a["gueltig"] and a["koerper"] == 1, erg
    assert 0.6 * soll < b["volumen"] - a["volumen"] < 1.4 * soll, (name, b["volumen"] - a["volumen"], soll)
ok("A4 STEP-Export: Gravur der Anbauteile als Rille 0,1 mm, Körper gültig (Rechteck- und Rundrohr)")
print("Alle Tests Gravur Anbauteile bestanden.")
