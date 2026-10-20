"""Prüft die Schneidzeit mit der größten Wandstärke (Stammdaten Profile: Wandstärke max., Normtabelle) und die
Einstiche je Anfangs-/Endschnitt (I-/H-Träger und U-Profil 4, T-Profil 2, sonst 1): Stammdaten, Umstellung älterer
Datendateien (Schema 22), Kalkulation, Einsparung gemeinsamer Schnitte und STEP-Import.

Aufruf: python tests/test_wand_einstiche.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import rechnen, step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import PROFILE, pruefen, wand_schneiden  # noqa: E402

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


IPE = dict(profil_id="IPE 200", form="I-/H-Träger", a=200, b=100, wand=5.6)


@fall("Wandstärke für die Schneidzeit: größere von Wandstärke und Wandstärke max., sonst Flanschdicke der Normtabelle")
def _():
    assert wand_schneiden(IPE) == 8.5, wand_schneiden(IPE)
    assert wand_schneiden(dict(IPE, wand_max=9.0)) == 9.0
    assert wand_schneiden(dict(IPE, profil_id="I 200x100", wand_max=None)) == 5.6     # kein Normprofil
    assert wand_schneiden(dict(profil_id="RE 60x40x3", form="Rechteckrohr", a=60, b=40, wand=3, wand_max=4)) == 4
    assert wand_schneiden(dict(profil_id="RR 42,4x2", form="Rundrohr", a=42.4, wand=2)) == 2
    assert wand_schneiden(dict(profil_id="SP 1", form="Sonderprofil", wand_max=6)) == 6
    assert wand_schneiden(dict(profil_id="SP 1", form="Sonderprofil")) is None


@fall("Stammdaten: Wandstärke max. kleiner als Wandstärke ist ein Fehler, Sonderprofil ohne Wandstärke eine Warnung")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        k = db.kontext()
        z = dict(profil_id="RE 60x40x3", form="Rechteckrohr", a=60, b=40, wand=3)
        assert pruefen(PROFILE, dict(z, wand_max=2), k) == "FEHLER: Wandstärke max. kleiner als die Wandstärke"
        assert pruefen(PROFILE, dict(z, wand_max=4), k) == "OK"
        sp = dict(profil_id="SP 1", form="Sonderprofil", flaeche_manuell=300)
        assert pruefen(PROFILE, sp, k).startswith("WARNUNG: Wandstärke fehlt")
        db.con.close()


@fall("Schema 22: ältere Datei bekommt Wandstärke max. der Normprofile aus der Tabelle, andere bleiben leer")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        pfad = Path(tmp) / "rohrlaser.db"
        db = Datenbank(pfad)
        db.neu("profile", dict(IPE))
        db.neu("profile", dict(profil_id="UPN 100", form="U-Profil", a=100, b=50, wand=6))
        db.neu("profile", dict(profil_id="HEB 160", form="I-/H-Träger", a=160, b=160, wand=8, wand_max=14))
        db.con.close()
        con = sqlite3.connect(pfad)
        con.execute("PRAGMA user_version=21")
        con.commit()
        con.close()
        db = Datenbank(pfad)
        wm = {z["profil_id"]: z.get("wand_max") for z in db.zeilen("profile")}
        assert wm["IPE 200"] == 8.5 and wm["UPN 100"] == 8.5 and wm["HEB 160"] == 14, wm
        assert all(v is None for p, v in wm.items() if p not in ("IPE 200", "UPN 100", "HEB 160")), wm
        db.con.close()


@fall("Kalkulation: Schneiddaten-Stufe nach der Flanschdicke, Einsparung gemeinsamer Schnitte mit 4 Einstichen")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        db.neu("profile", dict(IPE))
        k, tab = db.kontext(), db.tabellen()
        kopf = dict(maschine=db.einstellung("standard_maschine"), stange=6000)
        p = dict(pos=10, artikel="T1", profil_id="IPE 200", werkstoff_id="S235-10219", laenge=1000, stueck=2,
                 schneidweg=768, einstiche=8, a_gerade="ja", a_schnitt=384, b_gerade="ja", b_schnitt=384)
        w = rechnen.position_werte(p, kopf, k, tab)
        assert w["wand"] == 5.6 and w["wand_schneiden"] == 8.5, w
        sd8 = rechnen.schneiddaten(kopf["maschine"], "S235-10219", 8.5, tab, "Stahl")
        sd5 = rechnen.schneiddaten(kopf["maschine"], "S235-10219", 5.6, tab, "Stahl")
        assert sd8["wand_bis"] >= 8.5, sd8
        z56 = rechnen.schneidzeit(p, kopf, 5.6, tab, k)[2]
        z85 = rechnen.schneidzeit(p, kopf, w["wand_schneiden"], tab, k)[2]
        assert sd8 is sd5 or z85 > z56, (z56, z85)
        assert rechnen.einstiche_ende("I-/H-Träger") == 4 and rechnen.einstiche_ende("U-Profil") == 4
        assert rechnen.einstiche_ende("T-Profil") == 2 and rechnen.einstiche_ende("Rundrohr") == 1
        erg = rechnen.optimieren(kopf, [p], k)
        zeilen, _ = rechnen.kalkulation(kopf, [p], erg, k, tab, db.einstellungen())
        z = zeilen[0]
        assert z["wand_stufe"] == sd8["wand_bis"], z["wand_stufe"]
        # 2 gleiche Teile mit geraden Enden auf einer Stange: 1 gemeinsamer Schnitt spart 4 Einstiche (je Teil 2)
        ein = sum(t["eingespart_e"] for s_ in erg["stangen"] for t in s_["teile"])
        assert ein == 1, ein
        einstich = 4 * z["einstechzeit"] / 2
        mm = sum(t["eingespart_mm"] for s_ in erg["stangen"] for t in s_["teile"])
        schnitt = 60 * mm / rechnen.ende_vorschub(p, (z["vorschub_gross"], z["vorschub_mittel"], z["vorschub_klein"]),
                                                  rechnen.kontur_grenzen(rechnen.maschine(kopf, k))[0]) / 2
        assert abs(z["einsparung"] - (einstich + schnitt)) < 1e-6, (z["einsparung"], einstich, schnitt)
        db.con.close()


def messen(*pfade):
    import step_messen
    with tempfile.TemporaryDirectory() as tmp:
        aus = Path(tmp) / "m.txt"
        step_messen.main(["--ausgabe", str(aus)] + [str(p) for p in pfade])
        return step.lies_messwerte(aus)


@fall("STEP-Import: Einstiche je Ende nach Profilform, neues Profil mit Wandstärke max. aus der Flanschdicke")
def _():
    tr = HIER / "step_traeger"
    mw = messen(tr / "TR01_IPE200_L1000.step", tr / "TR09_IPE200_Stegbohrungen_L1000.step",
                tr / "TR06_T50_L600.step", tr / "TR08_UPN100_L900.step", tr / "TR04_I150x80x5x7_L700.step",
                HIER / "step" / "T01_RR42-4x2_L1250.step")
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        erg = step.uebernehmen(mw, [], db.kontext(), db.zeilen("gewinde"), None, "S235-10219", 1, neue_profile=True)
        e = {p["artikel"]: p["einstiche"] for p in erg["positionen"]}
        assert e == {"TR01_IPE200_L1000": 8, "TR09_IPE200_Stegbohrungen_L1000": 10, "TR06_T50_L600": 4,
                     "TR08_UPN100_L900": 8, "TR04_I150x80x5x7_L700": 8, "T01_RR42-4x2_L1250": 2}, e
        neu = {p["profil_id"]: p for p in erg["profile"]}
        i150 = next(p for pid, p in neu.items() if pid.startswith("I 150"))
        assert i150["wand"] == 5 and i150["wand_max"] == 7, i150
        db.con.close()


sys.exit(1 if fehler else 0)
