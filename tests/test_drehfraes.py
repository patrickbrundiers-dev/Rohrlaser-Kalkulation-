"""Dreh- und Frästeile im STEP als Zukaufartikel (Patrick 03.11.2026, Plan „Dreh- und Frästeile als Zukauf“, Freigabe
alle a, ohne Beispiel-STEPs: Testteile werden hier gebaut):
- D1 Messung: Stufenwelle, Bolzen mit Einstich, Bundbuchse, Buchse, Fräsblock mit Tasche, Platte mit Tasche,
  Winkelblock werden Dreh- bzw. Frästeil; glatter Rundstahl, Vierkant mit Bohrung, Normrohre und ein Normprofil
  bleiben wie bisher. Die alte Messung steht als Alternative, JSON-Block 'drehfraes' (Schema 1.27).
- D2 Übernahme: Zukaufteil-Position mit Artikel der Kategorie Drehteile bzw. Frästeile ohne EK, gleiche Teile einer
  Datei eine Position, ein gleiches Teil aus einer früheren Anfrage nimmt den vorhandenen Artikel (Frage 6 a).
- D3 Buchse nur nach Maßen erkannt: Prüfstatus prüfen (erst nach Anhaken); steht das Rohr in den Stammdaten, wird
  sie wieder Rohr (Frage 3 a).
- D4 Prüfdialog: Gruppe Dreh- und Frästeile, Art umstellbar auf die Messung als Rohr/Profil.
- D5 Datenbank: Kategorien Drehteile/Frästeile, Artikeltypen.

Aufruf: python tests/test_drehfraes.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder  # noqa: E402
from OCP.IFSelect import IFSelect_RetDone  # noqa: E402
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer  # noqa: E402
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: E402

from rohrlaser import drehfraes, step, zukauf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
import step_ergebnis  # noqa: E402
import step_messen  # noqa: E402

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


def zyl(r, h, z=0.0, x=0.0, y=0.0, d=(0, 0, 1)):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y, z), gp_Dir(*d)), r, h).Shape()


def quader(a, b, c, x=0.0, y=0.0, z=0.0):
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), a, b, c).Shape()


def vereint(*s):
    a = s[0]
    for b in s[1:]:
        a = BRepAlgoAPI_Fuse(a, b).Shape()
    return a


def ohne(a, *s):
    for b in s:
        a = BRepAlgoAPI_Cut(a, b).Shape()
    return a


TEILE = {     # Name: (Form, erwartete Art)
    "D01_Stufenwelle": (vereint(zyl(15, 40), zyl(10, 60, 40), zyl(8, 20, 100)), "Drehteil"),
    "D02_Bolzen_Einstich": (ohne(zyl(10, 80), ohne(zyl(11, 2, 60), zyl(8.5, 2, 60))), "Drehteil"),
    "D03_Bundbuchse": (ohne(vereint(zyl(25, 8), zyl(20, 42, 8)), zyl(12.5, 50)), "Drehteil"),
    "D04_Buchse_40_25": (ohne(zyl(20, 50), zyl(12.5, 50)), "Drehteil"),
    "D05_Fraesblock_Tasche": (ohne(quader(60, 40, 30), quader(40, 20, 10, 10, 10, 20), zyl(4, 30, 0, 8, 8)),
                              "Frästeil"),
    "D06_Platte_Tasche": (ohne(quader(100, 60, 20), quader(60, 30, 8, 20, 15, 12)), "Frästeil"),
    "D07_Winkelblock": (ohne(quader(50, 50, 50), quader(35, 50, 35, 15, 0, 15)), "Frästeil"),
    "N01_Rundstahl_glatt": (zyl(10, 80), "Rundstahl"),
    "N02_RR42_Bohrungen": (ohne(zyl(21.2, 400), zyl(18.6, 400), zyl(4, 50, 100, 0, -25, (0, 1, 0)),
                                zyl(4, 50, 300, 0, -25, (0, 1, 0))), "Rundrohr"),
    "N03_QR40_kurz": (ohne(quader(40, 40, 60), quader(34, 34, 60, 3, 3)), "Quadratrohr"),
    "N04_Vierkant_Bohrung": (ohne(quader(20, 20, 200), zyl(4, 20, 0, 10, 100, )), "Vierkantstahl"),
    "N05_RR42_kurz": (ohne(zyl(21.2, 40), zyl(18.6, 40)), "Rundrohr"),
}
TMP = Path(tempfile.mkdtemp())
_fd, _alt = sys.stdout.fileno(), os.dup(sys.stdout.fileno())     # Meldungen des STEP-Schreibers unterdrücken
sys.stdout.flush()
os.dup2(os.open(os.devnull, os.O_WRONLY), _fd)
try:
    for name, (form, _) in TEILE.items():
        w = STEPControl_Writer()
        w.Transfer(form, STEPControl_AsIs)
        assert w.Write(str(TMP / f"{name}.step")) == IFSelect_RetDone
finally:
    os.dup2(_alt, _fd)


def messen(*namen):
    aus, js = TMP / "m.txt", TMP / "m.json"
    step_messen.main(["--ausgabe", str(aus), "--json", str(js)] + [str(TMP / f"{n}.step") for n in namen])
    return step.lies_messwerte(aus), json.loads(js.read_text(encoding="utf-8"))


MW, JS = messen(*TEILE)
JE = {Path(m["datei"]).stem: m for m in MW}


@fall("D1 Messung: Dreh-/Frästeile erkannt, Laserteile unverändert, alte Messung als Alternative, JSON 1.27")
def _():
    ist = {n: JE[n]["profilform"] for n in TEILE}
    soll = {n: art for n, (_, art) in TEILE.items()}
    assert ist == soll, {n: (ist[n], soll[n]) for n in TEILE if ist[n] != soll[n]}
    d = drehfraes.daten(JE["D01_Stufenwelle"])
    assert d["durchmesser"] == 30 and d["laenge"] == 120 and d["durchmesser_liste"] == [16, 20, 30], d
    assert step.alternative(JE["D01_Stufenwelle"])["profilform"] == "Rundstahl"
    assert step.alternative(JE["D04_Buchse_40_25"])["profilform"] == "Rundrohr"
    assert step.alternative(JE["D05_Fraesblock_Tasche"])["profilform"] == "U-Profil"
    assert drehfraes.daten(JE["D04_Buchse_40_25"])["nur_abmessung"] and JE["D04_Buchse_40_25"]["pruefstatus"] == \
        "prüfen"
    assert JE["D01_Stufenwelle"]["pruefstatus"] == "plausibel" and JE["D06_Platte_Tasche"]["pruefstatus"] == "plausibel"
    assert drehfraes.text(JE["D03_Bundbuchse"]).startswith("Drehteil Ø50/Ø25 × 50 mm"), drehfraes.text(JE["D03_Bundbuchse"])
    f = drehfraes.daten(JE["D06_Platte_Tasche"])
    assert (f["laenge"], f["breite"], f["hoehe"]) == (100, 60, 20) and "Absatz/Tasche" in f["merkmale"], f
    assert all(not m.get("drehfraes") for n, m in JE.items() if n.startswith("N")), "Laserteile ohne Block"
    assert JS["schema_version"] == step_ergebnis.SCHEMA_VERSION == "1.28"
    k = next(x for dt in JS["dateien"] if dt["datei"].startswith("D01") for x in dt["koerper"])
    assert k["bauteiltyp"] == "Drehteil" and k["drehfraes"]["art"] == "Drehteil" and k["alternative"]["profiltyp"] \
        == "Rundstahl", k["drehfraes"]
    assert k["aussenmasse"] == {"durchmesser": 30.0} and k["wandstaerke"] is None, k["aussenmasse"]


@fall("D2 Übernahme: Zukaufteil mit Artikel der Kategorie, ohne EK, Wiederholteil nimmt vorhandenen Artikel")
def _():
    from rohrlaser.angebot import ZUKAUFTEIL
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        k = db.kontext()
        mw = [dict(JE[n]) for n in ("D01_Stufenwelle", "D06_Platte_Tasche", "N02_RR42_Bohrungen")]
        erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 4, zukauf_liste=[])
        p = {x["artikel"]: x for x in erg["positionen"]}
        assert p["D01_Stufenwelle"]["art"] == ZUKAUFTEIL and p["D06_Platte_Tasche"]["art"] == ZUKAUFTEIL, p
        assert p["N02_RR42_Bohrungen"].get("art") != ZUKAUFTEIL and p["N02_RR42_Bohrungen"]["profil_id"]
        assert p["D01_Stufenwelle"]["bezeichnung"] == "Drehteil Ø30 × 120 mm S235-10219", p["D01_Stufenwelle"]
        assert p["D01_Stufenwelle"]["stueck"] == 4 and p["D01_Stufenwelle"]["gewicht_teil"] > 0
        werte, bezuege = erg["zukauf_neu"][p["D01_Stufenwelle"]["_zukauf"]["neu"]]
        assert werte["artikeltyp"] == "Drehteil" and werte["kategorie"] == "Drehteile" and bezuege[0]["preise"] == []
        assert werte["fingerabdruck"] and werte["gewicht"] > 0 and "Rohgewicht" in werte["beschreibung"], werte
        assert erg["zukauf_neu"][p["D06_Platte_Tasche"]["_zukauf"]["neu"]][0]["kategorie"] == "Frästeile"
        assert any("EK fehlt: beim Lieferanten anfragen" in z for z in erg["bericht"]), erg["bericht"]
        # Artikel gespeichert: zweite Anfrage mit demselben Teil nimmt ihn (mit EK)
        aid = db.zukauf_speichern(None, werte, [dict(bezuege[0], preise=[dict(ab=1, preis=12.5)])])
        mw = [dict(JE["D01_Stufenwelle"])]
        erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 2,
                               zukauf_liste=db.zukauf_artikel_liste())
        assert erg["positionen"][0]["_zukauf"] == {"artikel_id": aid} and not erg["zukauf_neu"], erg["positionen"]
        assert not zukauf.ek_fehlt(db.zukauf_artikel(aid))
        # ohne Zukaufliste (alter Weg) wird es nie ein Rohrlaserteil
        erg = step.uebernehmen([dict(JE["D01_Stufenwelle"])], [], k, db.zeilen("gewinde"), None, "S235-10219", 1)
        assert not erg["positionen"], erg["positionen"]
        db.con.close()


@fall("D3 Buchse nur nach den Maßen: erst nach Anhaken; mit dem Rohr in den Stammdaten wieder Rohr")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        k = db.kontext()
        erg = step.uebernehmen([dict(JE["D04_Buchse_40_25"])], [], k, db.zeilen("gewinde"), None, "S235-10219", 1,
                               zukauf_liste=[])
        assert not erg["positionen"] and "ungeprüft" in erg["bericht"][0], erg["bericht"]
        erg = step.uebernehmen([dict(JE["D04_Buchse_40_25"], _uebernehmen=True)], [], k, db.zeilen("gewinde"),
                               None, "S235-10219", 1, zukauf_liste=[])
        assert erg["positionen"][0]["bezeichnung"].startswith("Drehteil Ø40/Ø25 × 50 mm"), erg["positionen"]
        m = dict(JE["D04_Buchse_40_25"])
        assert step.drehfraes_vorbelegen([m], {}) == 0 and m["profilform"] == "Drehteil"
        m = dict(JE["D04_Buchse_40_25"])
        profile = {"RR 40x7,5": dict(form="Rundrohr", a=40, b=None, wand=7.5)}
        assert step.drehfraes_vorbelegen([m], profile) == 1 and m["profilform"] == "Rundrohr", m["profilform"]
        assert drehfraes.daten(step.alternative(m))["art"] == "Drehteil" and m["_df_zurueck"]
        assert step.drehfraes_vorbelegen([m], profile) == 0, "nur einmal (Wahl im Prüfdialog bleibt)"
        db.con.close()


@fall("D4 Prüfdialog: Gruppe Dreh- und Frästeile, Zukaufartikel wählbar, Art auf Rohr/Profil umstellbar")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser.step_dialog import StepPruefDialog
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        mw = [dict(JE[n]) for n in ("D01_Stufenwelle", "D04_Buchse_40_25", "D05_Fraesblock_Tasche")]
        d = StepPruefDialog(None, mw, db.kontext(), "S235-10219", 1, db.zukauf_artikel_liste())
        z = next(z for z in d.zeilen if z.liste == [0])
        assert z.blech and z.it.parent().data(0, 0x0100) == d.DREHGRUPPE, z.it.parent().data(0, 0x0100)
        assert z.pr.itemText(0) == d.AUTOMATISCH and z.ws.currentText() == "S235-10219"
        assert "Drehteil Ø30 × 120 mm" in z.it.text(d.SP_HINWEIS) and z.it.checkState(0).name == "Unchecked"  # Zukauf: von Hand
        d.datei_waehlen(1)
        zb = next(z for z in d.zeilen if z.liste == [1])
        assert zb.it.checkState(0).name == "Unchecked" and "PRÜFEN" in zb.it.text(d.SP_HINWEIS)
        d.datei_waehlen(2)
        zf = next(z for z in d.zeilen if z.liste == [2])
        art = d.baum.itemWidget(zf.it, d.SP_ART)
        assert art.itemText(0) == "Frästeil" and art.itemData(1) == "alt" and art.itemText(1) == "U-Profil", \
            [art.itemText(i) for i in range(art.count())]
        art.setCurrentIndex(1)                       # zurück auf die Messung als Profil
        zf = next(z for z in d.zeilen if z.liste == [2])
        assert not zf.blech and mw[2]["profilform"] == "U-Profil"
        d.werte_schreiben()
        d.close()
        app.processEvents()
        db.con.close()


@fall("D5 Datenbank: Kategorien Drehteile/Frästeile (neu und nachgetragen), Artikeltypen wählbar")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        namen = {z["name"] for z in db.zeilen("zukauf_kategorien")}
        assert {"Drehteile", "Frästeile"} <= namen, namen
        db.con.execute("DELETE FROM zukauf_kategorien WHERE name IN ('Drehteile', 'Frästeile')")
        db.einstellung_setzen("drehfraes_stand", "alt")
        db.con.commit()
        db.con.close()
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        assert {"Drehteile", "Frästeile"} <= {z["name"] for z in db.zeilen("zukauf_kategorien")}
        assert "Drehteil" in zukauf.ZUKAUF_TYPEN and "Frästeil" in zukauf.ZUKAUF_TYPEN
        db.con.close()


sys.exit(1 if fehler else 0)
