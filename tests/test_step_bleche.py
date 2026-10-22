"""Prüft Bleche beim STEP-Import im Programm: Messung über step_messen (Textdatei und JSON 1.2), Grenze Flachstahl aus
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
    assert JS["schema_version"] == step_ergebnis.SCHEMA_VERSION == "1.4", JS["schema_version"]
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


@fall("Als Zukaufteil: Bleche werden Positionen mit Zukaufartikel, gleiche Bleche einer Baugruppe ein Artikel")
def _():
    from rohrlaser import zukauf
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        k = db.kontext()
        mw = [dict(m) for m in MW]
        erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 2, zukauf_liste=[])
        arten = [(p["artikel"], p.get("art")) for p in erg["positionen"]]
        assert arten == [("B14_Baugruppe_Rohr_2Bleche-K1", None), ("B14_Baugruppe_Rohr_2Bleche-K2", "Zukaufteil"),
                         ("B14_Baugruppe_Rohr_2Bleche-K3", "Zukaufteil"), ("B02_Blech_400x200x4_Bohrungen", "Zukaufteil")], arten
        b1, b2, b3 = erg["positionen"][1:]
        assert b1["_zukauf"] == {"neu": "neu1"} and b2["_zukauf"] == {"neu": "neu1"}, "gleiches Blech: ein Artikel"
        assert b3["_zukauf"] == {"neu": "neu2"} and len(erg["zukauf_neu"]) == 2
        assert b1["werkstoff_id"] is None and b1["gewicht_teil"] is None, "Werkstoff der Rohre gilt nicht für Bleche"
        assert b1["stueck"] == 2 and b1["laenge"] == 150 and b1["bezeichnung"] == "Blech 150 × 150 × 8 mm (Werkstoff offen)"
        werte, bezuege = erg["zukauf_neu"]["neu2"]
        assert werte["artikeltyp"] == "Blech" and werte["step_datei"] == "B02_Blech_400x200x4_Bohrungen.step", werte
        assert bezuege[0]["lieferant"] == "Technik" and bezuege[0]["preise"] == []
        assert any("neuer Zukaufartikel Blech 400 × 200 × 4 mm (Werkstoff offen), EK fehlt" in z for z in erg["bericht"])
        # Werkstoff im Prüfdialog gewählt: Bezeichnung und Gewicht (Volumen × Dichte)
        mw = [dict(m) for m in MW]
        mw[3]["_werkstoff"] = "S235-10219"
        erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, None, 1, zukauf_liste=[])
        b = erg["positionen"][-1]
        dichte = k.werkstoffe["S235-10219"]["dichte"]
        bl = step.blech(MW[3])
        assert b["werkstoff_id"] == "S235-10219" and abs(b["gewicht_teil"] - bl["volumen"] * dichte / 1e6) < 1e-3, b
        assert erg["zukauf_neu"]["neu2"][0]["bezeichnung"] == "Blech S235-10219 400 × 200 × 4 mm"
        # Dublette: vorhandener Artikel wird verwendet, kein neuer
        i = db.zukauf_speichern(None, *zukauf.blech_artikel(bl, None, "alt.step"))
        mw = [dict(m) for m in MW]
        erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, None, 1, zukauf_liste=db.zukauf_artikel_liste())
        assert erg["positionen"][-1]["_zukauf"] == {"artikel_id": i} and len(erg["zukauf_neu"]) == 1, erg["zukauf_neu"]
        assert any("vorhandener Zukaufartikel" in z for z in erg["bericht"])
        # abgewählt bzw. erneuter Import: nicht übernommen
        mw = [dict(m) for m in MW]
        mw[3]["_uebernehmen"] = False
        erg = step.uebernehmen(mw, [dict(artikel="B14_Baugruppe_Rohr_2Bleche-K2")], k, db.zeilen("gewinde"), None,
                               None, 1, zukauf_liste=[])
        assert [p["artikel"] for p in erg["positionen"]] == ["B14_Baugruppe_Rohr_2Bleche-K1",
                                                             "B14_Baugruppe_Rohr_2Bleche-K3"], erg["positionen"]
        db.con.close()


@fall("Gekantetes Blech (Prüfstatus prüfen): erst nach Bestätigung, Beschreibung mit Außenmaßen")
def _():
    mw, _ = messen("B07_Blech_gekantet_Winkel")
    assert mw[0]["pruefstatus"] == "prüfen", mw[0]["pruefstatus"]
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        k = db.kontext()
        erg = step.uebernehmen([dict(mw[0])], [], k, db.zeilen("gewinde"), None, None, 1, zukauf_liste=[])
        assert not erg["positionen"] and "ungeprüft" in erg["bericht"][0], erg["bericht"]
        erg = step.uebernehmen([dict(mw[0], _uebernehmen=True)], [], k, db.zeilen("gewinde"), None, None, 1,
                               zukauf_liste=[])
        assert len(erg["positionen"]) == 1
        assert erg["zukauf_neu"]["neu1"][0]["beschreibung"].startswith("gekantet, Außenmaße"), erg["zukauf_neu"]
        db.con.close()


@fall("Satz: Baugruppe mit Rohr und 2 gleichen Blechen = Satz, Bleche eine Position mit 2 Stück je Satz")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        k = db.kontext()
        mw = [dict(m) for m in MW[:3]]
        assert step.mehrteilig(mw) == {} and step.mehrteilig(mw, True) == {"B14_Baugruppe_Rohr_2Bleche.step": (3, 2)}
        erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, None, 5,
                               saetze=["B14_Baugruppe_Rohr_2Bleche.step"], zukauf_liste=[])
        p = erg["positionen"]
        assert len(p) == 2 and p[1]["art"] == "Zukaufteil" and p[1]["je_satz"] == 2 and p[1]["stueck"] == 10, p
        assert p[0]["satz"] == p[1]["satz"] == "B14_Baugruppe_Rohr_2Bleche"
        db.con.close()


@fall("Angebot: STEP-Import legt Zukaufartikel an und trägt sie in die Blech-Positionen ein")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser import rechnen, zukauf
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
        s = f.angebot_oeffnen(db.angebot_neu(dict(kunde="Test")))
        erg = s.step_importieren([str(BL / "B02_Blech_400x200x4_Bohrungen.step")], stueck=3)
        assert erg and len(erg["positionen"]) == 1, erg and erg["bericht"]
        p = db.positionen(s.id)[0]
        assert p["art"] == "Zukaufteil" and p["stueck"] == 3, p
        e = zukauf.eintraege(p)
        a = db.zukauf_artikel(e[0]["artikel_id"])
        assert a["artikeltyp"] == "Blech" and zukauf.ek_fehlt(a) and e[0]["menge"] == 1, a
        w = rechnen.position_werte(p, s.kopf, s.k, s.tabellen)
        assert rechnen.status(p, w, s.kopf, s.k).startswith("WARNUNG: EK fehlt")
        # zweiter Import derselben Datei: Position übersprungen, kein zweiter Artikel
        erg = s.step_importieren([str(BL / "B02_Blech_400x200x4_Bohrungen.step")], stueck=1)
        assert len([x for x in db.zukauf_artikel_liste() if x.get("artikeltyp") == "Blech"]) == 1
        app.processEvents()
        f.close()
        db.con.close()


@fall("Prüfdialog: Gruppe Bleche, Werkstoff offen statt Vorgabe, Zukaufartikel wählbar, gekantet erst nach Anhaken")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser import zukauf
    from rohrlaser.step_dialog import StepPruefDialog
    app = QApplication.instance() or QApplication([])
    gek, _ = messen("B07_Blech_gekantet_Winkel")
    mw = [dict(m) for m in MW] + [dict(gek[0])]
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        i = db.zukauf_speichern(None, *zukauf.blech_artikel(step.blech(MW[3]), None, "alt.step"))
        d = StepPruefDialog(None, mw, db.kontext(), "S235-10219", 1, db.zukauf_artikel_liste())
        bg = d.baum.topLevelItem(0)        # B14 (Rohr + 2 gleiche Bleche) steht als Baugruppe, Vorgabe 1 Satz
        assert bg.text(0) == "Baugruppe „B14_Baugruppe_Rohr_2Bleche“ – 3 Teile, 2 verschieden – 1 Satz", bg.text(0)
        gruppen = [bg.child(n).text(0) for n in range(bg.childCount())]
        assert gruppen[0] == d.BLECHGRUPPE + " – 1 Teil" and not any("Nicht übernehmbar" in g for g in gruppen), gruppen
        bl = [z for z in d.zeilen if z.blech]
        assert len(bl) == 3 and [len(z.liste) for z in bl] == [2, 1, 1], [len(z.liste) for z in bl]
        assert all(z.ws.currentText() == "" for z in bl), "Werkstoff der Rohre nicht übernommen"
        rohr = next(z for z in d.zeilen if not z.blech)
        assert rohr.ws.currentText() == "S235-10219"
        z02 = next(z for z in bl if z.datei.startswith("B02"))
        assert z02.pr.count() == 2 and z02.pr.itemData(1) == i and "gleich, EK fehlt" in z02.pr.itemText(1)
        assert "vorhanden" in z02.it.text(9), z02.it.text(9)
        z07 = next(z for z in bl if z.datei.startswith("B07"))
        assert z07.it.checkState(0).name == "Unchecked" and "PRÜFEN" in z07.it.text(9), z07.it.text(9)
        z02.pr.setCurrentIndex(1)
        z02.ws.setCurrentText("S235-10219")
        d.werte_schreiben()
        assert mw[3]["_blech_artikel"] == i and mw[3]["_werkstoff"] == "S235-10219" and mw[3]["_uebernehmen"]
        assert mw[1]["_blech_artikel"] is None and mw[4]["_uebernehmen"] is False
        erg = step.uebernehmen(mw, [], db.kontext(), db.zeilen("gewinde"), None, None, 1,
                               zukauf_liste=db.zukauf_artikel_liste())
        assert erg["positionen"][-1]["_zukauf"] == {"artikel_id": i}, erg["positionen"][-1]
        # B14 ist als Baugruppe 1 Satz vorbelegt: die 2 gleichen Bleche sind eine Position (2 Stück je Satz)
        assert len(erg["positionen"]) == 3, [p["artikel"] for p in erg["positionen"]]
        assert erg["positionen"][1].get("je_satz") == 2, erg["positionen"][1]
        d.close()
        app.processEvents()
        db.con.close()


@fall("Art wählbar: Flachstahl/Blech und Kantteil/Profil gemessen, im Prüfdialog umstellbar (Ersatzwerte = prüfen)")
def _():
    from PySide6.QtWidgets import QApplication
    from rohrlaser.step_dialog import StepPruefDialog
    app = QApplication.instance() or QApplication([])
    mw, js = messen("B09_FL100x10_L800", "B10_Blech_1000x160x8", "B07_Blech_gekantet_Winkel", "B14_Baugruppe_Rohr_2Bleche")
    fl, bl, kant, rohr = mw[0], mw[1], mw[2], mw[3]
    # Messung: Grenzfälle mit Alternative, Rohr ohne
    assert step.art_text(fl) == "Flachstahl" and step.alternative(fl)["profilform"] == "Blech", fl.get("alternative")
    assert step.alternative(bl)["profil_id_vorschlag"] == "FL 160x8", bl.get("alternative")
    alt = step.alternative(kant)
    assert step.art_text(kant) == "Kantteil (Blech gekantet)" and alt["profilform"] == "L-Profil" and alt["ersatz"] == "1"
    assert alt["pruefstatus"] == "prüfen" and "konturen" in step.unsicher(alt), alt
    assert step.alternative(rohr) is None
    k_js = js["dateien"][2]["koerper"][0]
    assert k_js["alternative"]["profiltyp"] == "L-Profil" and k_js["alternative"]["ersatzwerte"] is True, k_js["alternative"]
    assert js["dateien"][3]["koerper"][0]["alternative"] is None
    # Umstellen in den Messwerten: hin und zurück gibt dieselben Werte
    m = dict(bl)
    assert step.art_wechseln(m) and m["profilform"] == "Flachstahl" and step.alternative(m)["profilform"] == "Blech"
    assert step.art_wechseln(m) and {k_: m[k_] for k_ in bl} == bl
    # Prüfdialog: Art vorbelegt, Wechsel verschiebt die Zeile in die andere Gruppe
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        d = StepPruefDialog(None, mw, db.kontext(), "S235-10219", 1, db.zukauf_artikel_liste())
        zfl = next(z for z in d.zeilen if z.liste == [0])
        art = d.baum.itemWidget(zfl.it, d.SP_ART)
        assert [art.itemText(n) for n in range(art.count())] == ["Flachstahl", "Blech"] and not zfl.blech
        assert d.baum.itemWidget(next(z for z in d.zeilen if z.liste == [3]).it, d.SP_ART) is None
        zfl.sp.setValue(4)
        art.setCurrentIndex(1)                                   # Flachstahl -> Blech
        z = next(z for z in d.zeilen if z.liste == [0])
        assert z.blech and z.ws.currentText() == "" and z.sp.value() == 4, (z.blech, z.ws.currentText())
        assert z.it.parent().data(0, 0x0100) == d.BLECHGRUPPE
        d.datei_waehlen(1)
        d.art_wechseln(1)                                        # Blech -> Flachstahl
        z = next(z for z in d.zeilen if z.liste == [1])
        assert not z.blech and z.pr.currentText() == "FL 160x8" and z.ws.currentText() == "S235-10219", z.pr.currentText()
        d.datei_waehlen(2)
        z = d.art_wechseln(2)                                    # Kantteil -> L-Profil (Ersatzwerte)
        assert not z.blech and z.it.checkState(0).name == "Unchecked" and "UNSICHER" in z.it.text(d.SP_HINWEIS)
        z.it.setCheckState(0, z.it.checkState(0).Checked)
        d.werte_schreiben()
        erg = step.uebernehmen(mw, [], db.kontext(), db.zeilen("gewinde"), None, None, 1, neue_profile=True,
                               zukauf_liste=db.zukauf_artikel_liste())
        arten = {p["artikel"]: (p.get("art"), p.get("profil_id")) for p in erg["positionen"]}
        assert arten["B09_FL100x10_L800"] == ("Zukaufteil", None), arten
        assert arten["B10_Blech_1000x160x8"] == (None, "FL 160x8"), arten
        assert arten["B07_Blech_gekantet_Winkel"][1].startswith("L "), arten
        d.close()
        app.processEvents()
        db.con.close()


@fall("Blech-Werkstoffe im Prüfdialog, Blech-Richtpreis als EK, Doppelklick aufs Bild öffnet den Blech-Editor")
def _():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from rohrlaser import blech, zukauf
    from rohrlaser.fenster import Hauptfenster
    from rohrlaser.step_dialog import StepPruefDialog
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        bw = {z["blech_werkstoff_id"]: z for z in db.zeilen("blech_werkstoffe")}
        wid = next(iter(sorted(bw)))
        mw = [dict(m) for m in MW]
        d = StepPruefDialog(None, mw, db.kontext(), "S235-10219", 1, db.zukauf_artikel_liste(), bw)
        z02 = next(z for z in d.zeilen if z.blech and z.datei.startswith("B02"))
        eintraege = [z02.ws.itemText(n) for n in range(z02.ws.count())]
        assert wid in eintraege and "S235-10219" not in eintraege, eintraege
        rohr = next(z for z in d.zeilen if not z.blech)
        assert rohr.ws.findText("S235-10219") >= 0          # Rohre weiter mit den Rohr-Werkstoffen
        d.close()
        f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
        s = f.angebot_oeffnen(db.angebot_neu(dict(kunde="Test")))
        gemessen = s.step_messen([str(BL / "B02_Blech_400x200x4_Bohrungen.step")])
        s.step_messen = lambda *a, **k: (gemessen, None)
        for m in gemessen:
            m["_werkstoff"] = wid
        erg = s.step_importieren(["B02"], stueck=3)
        p = db.positionen(s.id)[0]
        e = blech.lesen(p["technik"])
        assert e and e["werkstoff"] == wid and e["laenge"] == 400 and e["breite"] == 200 and e["dicke"] == 4, e
        assert [k_["art"] for k_ in e["konturen"]][:1] == ["Bohrung"], e["konturen"]
        a = db.zukauf_artikel(zukauf.eintraege(p)[0]["artikel_id"])
        rp = blech.rechnen(e, bw, db.zeilen("blechlaser"), {n: db.einstellung(n) for n in blech.EINSTELLUNGEN})
        assert not zukauf.ek_fehlt(a) and rp["richtpreis"] and e["richtpreise"] == [dict(ab=1, preis=rp["richtpreis"])]
        assert any("EK = Blech-Richtpreis" in t for t in erg["bericht"]), erg["bericht"]
        pm = s.pos_modell
        c = next(c for c in range(pm.columnCount()) if pm.name(c) == "artikel")
        aufrufe = []
        s.blech_bearbeiten = lambda zeile: aufrufe.append(("blech", zeile))
        s.ansicht_3d = lambda zeile: aufrufe.append(("3d", zeile))
        s._doppelklick(pm.index(0, c), auf_bild=True)
        s._doppelklick(pm.index(0, c), auf_bild=False)
        assert aufrufe == [("blech", 0), ("3d", 0)], aufrufe
        assert "Doppelklick aufs Bild: Blech-Editor" in pm.data(pm.index(0, c), Qt.ToolTipRole)
        f.close()
        app.processEvents()
        db.con.close()


sys.exit(1 if fehler else 0)
