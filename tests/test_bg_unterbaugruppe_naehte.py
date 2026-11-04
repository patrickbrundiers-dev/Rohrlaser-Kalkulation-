"""Schweißnähte bei Schweißbaugruppen mit Unterbaugruppe (Patrick 04.11.2026: „keine Schweißnaht berechnet“):
- S04 Gestell mit 2× Seitenrahmen als Unterbaugruppe: STEP-Import mit Häkchen „als Schweißbaugruppe“ und
  Vorkalkulation automatisch legt die Nähte in der Unterbaugruppe (4 je Seitenrahmen × 2) und zwischen
  Unterbaugruppe und Gestell (4) an, rechnet 12 × 152 mm Naht
- ein Teilepaar, dessen Nahtberechnung scheitert, verwirft nicht mehr alle Nahtkandidaten, sondern meldet sich
- Außennähte (Stumpfnaht) bekommen in der Vorkalkulation die Nacharbeit „Naht verschleifen“

Aufruf: python tests/test_bg_unterbaugruppe_naehte.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))

import step_geometrie  # noqa: E402
import step_messen  # noqa: E402
from rohrlaser import baugruppe, step, vorkalk  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())


def ok(t):
    print("OK    ", t)


def messen(datei, name):
    ziel = tmp / name
    step_messen.main(["--ausgabe", str(ziel) + ".txt", "--json", str(ziel) + ".json", str(datei)])
    return ziel


def importieren(ziel):
    mw = step.struktur_anhaengen(step.lies_messwerte(str(ziel) + ".txt"), str(ziel) + ".json")
    for x in mw:
        x.update(_stueck=1, _uebernehmen=True, _saetze=1, _baugruppe=True)
    db = Datenbank(tmp / "naehte.db")
    erg = step.uebernehmen(mw, [], db.kontext(), db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True,
                           zukauf_liste=[])
    return erg["positionen"], erg["bericht"]


# ------------------------------------------------------------------ Nähte in und zwischen Unterbaugruppen
S04 = HIER / "step_struktur" / "S04_Gestell_Unterbaugruppe_geschweisst.step"
ziel = messen(S04, "s04")
d = json.loads(Path(str(ziel) + ".json").read_text(encoding="utf-8"))["dateien"][0]
kand = d["nahtkandidaten"]
assert len(kand) == 12 and d["ohne_naht"] == [], (len(kand), d.get("ohne_naht"))
assert sorted(k["knoten"] for k in kand) == ["K1"] * 4 + ["K2"] * 8, [k["knoten"] for k in kand]
pos, bericht = importieren(ziel)
bgp = next(p for p in pos if p.get("art") == BAUGRUPPE)
bg = baugruppe.lesen(bgp["baugruppe"])
assert [k["name"] for k in bg["knoten"]] == ["Seitenrahmen"] and bg["knoten"][0]["menge"] == 2, bg["knoten"]
unter = bg["knoten"][0]["id"]
vor = {v["knoten"]: v["anzahl"] for v in bg["vorschlaege"]}
assert vor == {unter: 4, "": 4}, vor
tab = baugruppe.richtwerte()
r = vorkalk.komplett(bgp, pos, tab, dict(schweiss_a_regel=0.7))
assert r["naehte_neu"] == 2, r
p2 = dict(bgp, baugruppe=baugruppe.speichern(r["bg"]))
erg = baugruppe.rechnen(p2, tab, {})
naht_m = sum(erg["naht_m"].values())
assert abs(naht_m - 12 * 0.152) < 1e-6, erg["naht_m"]
faktoren = sorted(z["faktor"] for z in erg["zeilen"] if z["art"] == "Naht")
assert faktoren == [1, 2], faktoren
assert erg["schweiss_min"] > 0 and not any("Unterbaugruppe" in w for w in erg["warnungen"]), erg["warnungen"]
ok("S04: 12 Nähte (8 im Seitenrahmen 2×, 4 zwischen Seitenrahmen und Gestell) angelegt und gerechnet, 1,824 m")

# ------------------------------------------------------------------ ein Paar scheitert: die anderen bleiben
original = step_geometrie._naht_paar
zaehler = dict(n=0)


def kaputt(ta, ka, tb, kb, struktur, rahmen):
    zaehler["n"] += 1
    if zaehler["n"] == 1:
        raise RuntimeError("Test: Schnitt gescheitert")
    return original(ta, ka, tb, kb, struktur, rahmen)


step_geometrie._naht_paar = kaputt
try:
    teile = step_geometrie.analysiere_datei(S04)        # in diesem Prozess, damit der Ersatz greift
finally:
    step_geometrie._naht_paar = original
assert len(teile[0].naehte) == 11, len(teile[0].naehte)
warn = [w for t in teile for w in t.hinweise]
assert any("Nahtkandidaten unvollständig" in w and "Schnitt gescheitert" in w for w in warn), warn
ok("ein gescheitertes Teilepaar: übrige Nahtkandidaten bleiben, Hinweis „Nahtkandidaten unvollständig“")

# ------------------------------------------------------------------ Außennaht verschleifen
nt = dict(id="n1", nr="1", verfahren="MAG", nahtart="Stumpfnaht", mass=3, laenge=152, anzahl=1, dicke=3)
st, grund = vorkalk.stufe_vorschlag(nt, dict(stamm={}))
assert st == "Naht verschleifen" and "außen" in grund, (st, grund)
assert vorkalk.stufe_vorschlag(dict(nt, nahtart="Kehlnaht"), dict(stamm={}))[0] == "keine"
ok("Stumpfnaht außen: Nacharbeit „Naht verschleifen“, Kehlnaht innen: keine")
print("Unterbaugruppen-Nähte: alle Tests bestanden.")
