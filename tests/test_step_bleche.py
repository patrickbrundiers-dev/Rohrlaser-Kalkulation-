"""Prüft Bleche beim STEP-Import im Programm: Messung über step_messen (Textdatei und JSON 1.1), Grenze Flachstahl aus
der Einstellung, Bleche werden nie als Rohrlaserteil (Profil) übernommen, Rohre derselben Baugruppe schon.

Die Geometrie der Bleche prüft tests/test_step_referenz.py (Fälle BL01 bis BL16) gegen die Konstruktionsmaße.
Aufruf: python tests/test_step_bleche.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from rohrlaser import step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
import step_ergebnis  # noqa: E402
import step_messen  # noqa: E402

BL = HIER / "step_bleche"
fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            fehler += 1
            print(f"FEHLER {name}: {e}")
        return fn
    return deko


def messen(*dateien, flach_bis=None):
    with tempfile.TemporaryDirectory() as tmp:
        aus, js = Path(tmp) / "m.txt", Path(tmp) / "m.json"
        arg = ["--ausgabe", str(aus), "--json", str(js)] + (["--flachstahl-bis", str(flach_bis)] if flach_bis else [])
        step_messen.main(arg + [str(BL / f"{d}.step") for d in dateien])
        return step.lies_messwerte(aus), json.loads(js.read_text(encoding="utf-8"))


MW, JS = messen("B14_Baugruppe_Rohr_2Bleche", "B02_Blech_400x200x4_Bohrungen")


@fall("Messwerte: Spalten bauteiltyp und blech, Blechdaten als JSON")
def _():
    assert [m["bauteiltyp"] for m in MW] == ["Profil", "Blech", "Blech", "Blech"], [m["bauteiltyp"] for m in MW]
    b = step.blech(MW[3])
    assert b["laenge"] == 400 and b["breite"] == 200 and b["dicke"] == 4, b
    assert b["bohrungen"] == {"10.0": 4, "20.0": 1} and b["innen"] == 5, b
    assert step.blech_text(MW[3]) == "Blech 400 × 200 × 4 mm", step.blech_text(MW[3])
    assert step.blech(MW[0]) is None


@fall("JSON 1.1: bauteiltyp, Block blech, keine Profilwerte bei Blechen")
def _():
    assert JS["schema_version"] == step_ergebnis.SCHEMA_VERSION == "1.1", JS["schema_version"]
    k = JS["dateien"][1]["koerper"][0]
    assert k["bauteiltyp"] == "Blech" and k["profiltyp"] == "Blech", k
    assert k["blech"]["dicke"] == 4 and k["blech"]["kontur"] == "rechteckig", k["blech"]
    assert {"durchmesser": 10.0, "anzahl": 4} in k["blech"]["bohrungen"], k["blech"]["bohrungen"]
    assert k["querschnittsflaeche_mm2"] is None and k["wandstaerke"] is None and k["innenmasse"] is None, k
    assert k["aussenmasse"] == {"laenge": 400.0, "breite": 200.0, "dicke": 4.0}, k["aussenmasse"]
    rohr = JS["dateien"][0]["koerper"][0]
    assert rohr["bauteiltyp"] == "Profil" and rohr["blech"] is None, rohr


@fall("Übernahme: Rohr der Baugruppe wird Position, Bleche nicht (kein Rohrlaserteil)")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        k = db.kontext()
        assert step.gleiche_teile(MW) == {0: [0]}, step.gleiche_teile(MW)
        erg = step.uebernehmen(MW, [], k, db.zeilen("gewinde"), None, "S235-10219", 1)
        assert [p["artikel"] for p in erg["positionen"]] == ["B14_Baugruppe_Rohr_2Bleche-K1"], erg["positionen"]
        assert sum("Blech 150 × 150 × 8 mm ist kein Rohrlaserteil" in z for z in erg["bericht"]) == 2, erg["bericht"]
        assert any("Blech 400 × 200 × 4 mm ist kein Rohrlaserteil" in z for z in erg["bericht"]), erg["bericht"]
        db.con.close()


@fall("Grenze Flachstahl: Einstellung 150 mm, mit 200 mm ist 160 breit Flachstahl")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        assert db.einstellung("flachstahl_bis") == 150.0
        db.con.close()
    mw, _ = messen("B10_Blech_1000x160x8")
    assert mw[0]["profilform"] == "Blech", mw[0]["profilform"]
    mw, _ = messen("B10_Blech_1000x160x8", flach_bis=200)
    assert mw[0]["profilform"] == "Flachstahl" and mw[0]["bauteiltyp"] == "Profil", mw[0]["profilform"]


sys.exit(1 if fehler else 0)
