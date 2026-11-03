"""Richtpreis für Dreh- und Frästeile (Patrick 03.11.2026, Plan „Richtpreise für Dreh- und Frästeile“, Freigabe alle
a, Frage 2 b: Arbeitsgänge je Teil; Machbarkeitsprüfung und Skizze 03.11. 17:02). Testteile werden hier gebaut (wie
test_drehfraes.py, ohne echte STEP-Dateien):
- R1 Messung: Kennwerte (Abschnitte außen/innen, Einstich, Wand, Bohrung Ø × Tiefe, Taschentiefe), Halbschalen einer
  Bohrung zusammen.
- R2 Rechenkern: Werkstoffgruppe, Lagermaß, Bohrvorschub, Rohling, Arbeitsgänge; 1 Stück teurer als 100 Stück,
  Edelstahl teurer als Stahl, Alu billiger als Edelstahl; Zeit von Hand; Tabelle aus den Einstellungen.
- R3 Machbarkeit: grün, Tieflochbohrung rot, schlank gelb/rot, dünne Wand rot, Innenradius, Maschine zu klein.
- R4 STEP-Übernahme: neuer Artikel mit Richtpreis als EK und Hinweis, Position mit Eingaben; ohne Einstellungen
  (Funktion aus) wie bisher ohne EK.
- R5 Staffeln: Richtpreis für die Stückzahl der Stufe neu, EK aus dem Einkauf geht vor.
- R6 Angebot: Rechtsklick „Richtpreis Dreh-/Frästeil …“, Dialog mit Ampel und Skizze, Zeit von Hand, EK ab Stückzahl.

Aufruf: python tests/test_drehfraes_preis.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

from rohrlaser import drehfraes, drehfraes_preis as dp, staffeln, step, zukauf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
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
            import traceback
            print(f"FEHLER {name}: {e} ", traceback.format_exc().splitlines()[-3])
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


TEILE = {
    "D01_Stufenwelle": vereint(zyl(15, 40), zyl(10, 60, 40), zyl(8, 20, 100)),
    "D02_Bolzen_Einstich": ohne(zyl(10, 80), ohne(zyl(11, 2, 60), zyl(8.5, 2, 60))),
    "D03_Bundbuchse": ohne(vereint(zyl(25, 8), zyl(20, 42, 8)), zyl(12.5, 50)),
    "D05_Fraesblock_Tasche": ohne(quader(60, 40, 30), quader(40, 20, 10, 10, 10, 20), zyl(4, 30, 0, 8, 8)),
    "D06_Platte_Tasche": ohne(quader(100, 60, 20), quader(60, 30, 8, 20, 15, 12)),
}
TMP = Path(tempfile.mkdtemp())
_fd, _alt = sys.stdout.fileno(), os.dup(sys.stdout.fileno())
sys.stdout.flush()
os.dup2(os.open(os.devnull, os.O_WRONLY), _fd)
try:
    for name, form in TEILE.items():
        w = STEPControl_Writer()
        w.Transfer(form, STEPControl_AsIs)
        assert w.Write(str(TMP / f"{name}.step")) == IFSelect_RetDone
    aus, js = TMP / "m.txt", TMP / "m.json"
    step_messen.main(["--ausgabe", str(aus), "--json", str(js)] + [str(TMP / f"{n}.step") for n in TEILE])
finally:
    os.dup2(_alt, _fd)
MW = step.lies_messwerte(aus)
JE = {Path(m["datei"]).stem: m for m in MW}
D = {n: drehfraes.daten(m) for n, m in JE.items()}


@fall("R1 Messung: Kennwerte für den Richtpreis (Absätze, Einstich, Wand, Bohrung, Taschentiefe)")
def _():
    k = D["D01_Stufenwelle"]["kennwerte"]
    assert [a["d"] for a in k["aussen"]] == [30, 20, 16] and [a["l"] for a in k["aussen"]] == [40, 60, 20], k
    assert k["einstiche"] == 0 and k["innen"] == [] and k["dreh_flaeche"] > 0 and k["stirn"] >= 3, k
    k = D["D02_Bolzen_Einstich"]["kennwerte"]
    assert k["einstiche"] == 1 and [a["d"] for a in k["aussen"]] == [20, 17, 20], k
    k = D["D03_Bundbuchse"]["kennwerte"]
    assert k["innen"][0]["d"] == 25 and k["wand_min"] == 7.5, k
    k = D["D05_Fraesblock_Tasche"]["kennwerte"]
    assert k["bohrungen"] == [dict(d=8.0, l=30.0, z=15.0)] or (len(k["bohrungen"]) == 1 and k["bohrungen"][0]["d"]
                                                              == 8), k
    assert k["taschentiefe"] == 10, k
    assert D["D06_Platte_Tasche"]["kennwerte"]["taschentiefe"] == 8, D["D06_Platte_Tasche"]["kennwerte"]


@fall("R2 Rechenkern: Gruppe, Lagermaß, Rohling, Arbeitsgänge, Stückzahl, Werkstoff, Zeit von Hand")
def _():
    tab = dp.schnittwerte()
    g = {w: dp.gruppe(w, tab)["gruppe"] for w in ("S235JR", "S235-10219", "1.4301 2B", "EN AW-6082", "AlMgSi1",
                                                   "C45", "CuZn39Pb3", "POM", None, "1.0038")}
    assert g == {"S235JR": "Stahl", "S235-10219": "Stahl", "1.4301 2B": "Edelstahl", "EN AW-6082": "Aluminium",
                 "AlMgSi1": "Aluminium", "C45": "Vergütungsstahl", "CuZn39Pb3": "Messing", "POM": "Kunststoff",
                 None: "Stahl", "1.0038": "Stahl"}, g
    assert dp.lagermass(32, dp.RUND_LAGER, 10) == 32 and dp.lagermass(33, dp.RUND_LAGER, 10) == 35
    assert dp.lagermass(305, dp.RUND_LAGER, 10) == 310
    assert abs(dp.bohr_f(9, "A") - 0.225) < 1e-9 and dp.bohr_f(30, "A") == 0.40
    d = D["D01_Stufenwelle"]
    e1 = dp.rechnen(dp.aus_step(d, "S235JR", 1))
    e100 = dp.rechnen(dp.aus_step(d, "S235JR", 100))
    assert not e1["fehler"] and e1["rohling"]["d"] == 32 and e1["rohling"]["laenge"] == 125, e1["rohling"]
    namen = [x["name"] for x in e1["arbeitsgaenge"]]
    assert "Drehen schruppen" in namen and "Drehen schlichten" in namen and "Abstechen" in namen, namen
    assert e1["richtpreis"] > e100["richtpreis"] * 5 and e100["richtpreis"] > 2, (e1["richtpreis"], e100["richtpreis"])
    assert abs(e1["ruesten"] - 100 * e100["ruesten"]) < 1e-6 and e1["maschine"] == e100["maschine"]
    ed = dp.rechnen(dp.aus_step(d, "1.4301", 10))
    ea = dp.rechnen(dp.aus_step(d, "EN AW-6082", 10))
    es = dp.rechnen(dp.aus_step(d, "S235JR", 10))
    assert ed["richtpreis"] > es["richtpreis"] and ea["richtpreis"] < ed["richtpreis"], \
        (ed["richtpreis"], es["richtpreis"], ea["richtpreis"])
    assert ed["zeit_stueck"] > es["zeit_stueck"] > ea["zeit_stueck"]
    # Zeit von Hand: gilt statt der Rechnung, berechnet bleibt sichtbar
    eh = dp.rechnen(dict(dp.aus_step(d, "S235JR", 10), zeiten={"Drehen schruppen": 5.0}))
    g = next(x for x in eh["arbeitsgaenge"] if x["name"] == "Drehen schruppen")
    assert g["minuten"] == 5.0 and g["hand"] and g["berechnet"] < 5 and eh["richtpreis"] > es["richtpreis"]
    # Bohrung innen (Bundbuchse), Frästeil mit Bohrung und Tasche
    eb = dp.rechnen(dp.aus_step(D["D03_Bundbuchse"], "S235JR", 10))
    assert any(x["name"].startswith("Bohren innen Ø25") for x in eb["arbeitsgaenge"]), eb["arbeitsgaenge"]
    ef = dp.rechnen(dp.aus_step(D["D05_Fraesblock_Tasche"], "S235JR", 10))
    assert ef["rohling"]["text"].startswith("Flachstahl 45 × 35 × 63"), ef["rohling"]
    assert any(x["name"] == "Bohren (1×)" for x in ef["arbeitsgaenge"]) and ef["zeit_fraesen"] > 0
    # Einstellungen: Stundensatz und eigene Tabelle (ohne Zeile Stahl kommt die Vorgabe dazu)
    teuer = dp.rechnen(dp.aus_step(d, "S235JR", 10), dict(df_stundensatz_drehen=170))
    assert teuer["maschine"] > 1.9 * es["maschine"]
    tab = dp.schnittwerte("Titan; 4,5; 30; 50; 0,15; 1; 60; 0,1; 40; 0,04; 0,03; 30; E; 10; Ti,3.7")
    assert [z["gruppe"] for z in tab] == ["Titan", "Stahl"] and dp.gruppe("Ti6Al4V", tab)["gruppe"] == "Titan"
    assert "€ je Stück" in " ".join(dp.bericht(es)) and "Rohling: Rundstahl" in dp.bericht(es)[0] and dp.rechnen(dict(daten={}))["fehler"]


@fall("R3 Machbarkeit: grün, Tieflochbohrung, schlank, dünne Wand, Innenradius, Maschine zu klein")
def _():
    w = dp.einstellungen()
    assert dp.machbarkeit(D["D01_Stufenwelle"], w) == [] and dp.ampel([]) == dp.GRUEN
    welle = dict(art="Drehteil", durchmesser=10, laenge=200, innen=0, kennwerte=dict(aussen=[dict(d=10, l=200, z=100)]))
    mb = dp.machbarkeit(welle, w)
    assert dp.ampel(mb) == dp.ROT and "Lünette" in mb[0]["text"], mb
    welle["laenge"] = 60
    mb = dp.machbarkeit(welle, w)
    assert dp.ampel(mb) == dp.GELB and "Reitstock" in mb[0]["text"], mb
    hulse = dict(art="Drehteil", durchmesser=20, laenge=20, innen=19.2,
                 kennwerte=dict(aussen=[dict(d=20, l=20, z=10)], innen=[dict(d=19.2, l=20, z=10)], wand_min=0.4))
    assert any(x["stufe"] == dp.ROT and "Wand" in x["text"] for x in dp.machbarkeit(hulse, w))
    block = dict(art="Frästeil", laenge=80, breite=40, hoehe=40,
                 kennwerte=dict(bohrungen=[dict(d=4, l=60, z=30)], innenradius_min=3, taschentiefe=70))
    mb = dp.machbarkeit(block, w)
    stufen = {x["text"].split()[0]: x["stufe"] for x in mb}
    assert stufen == {"Bohrung": dp.ROT, "Innenradius": dp.GELB, "Tasche/Absatz": dp.ROT}, mb
    # Zeitzuschlag: gelbe Bohrung (6 × Ø) +50 %
    block["kennwerte"] = dict(bohrungen=[dict(d=5, l=30, z=15)])
    e = dp.rechnen(dict(daten=dict(block, volumen=80 * 40 * 40 * 0.95), werkstoff="S235JR", stueck=1))
    g = next(x for x in e["arbeitsgaenge"] if x["name"].startswith("Bohren"))
    assert e["ampel"] == dp.GELB and "Machbarkeit × 1,5" in g["info"], (e["ampel"], g)
    gross = dict(art="Frästeil", laenge=1200, breite=300, hoehe=100, kennwerte={})
    assert dp.ampel(dp.machbarkeit(gross, w)) == dp.ROT


@fall("R4 STEP-Übernahme: neuer Artikel mit Richtpreis als EK, Position mit Eingaben; Funktion aus: ohne EK")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        k = db.kontext()
        einst = db.drehfraes_einstellungen()
        assert einst["df_stundensatz_drehen"] == 85 and "Edelstahl" in einst["df_schnittwerte"]
        mw = [dict(JE[n]) for n in ("D01_Stufenwelle", "D06_Platte_Tasche")]
        erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 10, zukauf_liste=[],
                               drehfraes_einst=einst)
        p = {x["artikel"]: x for x in erg["positionen"]}
        werte, bezuege = erg["zukauf_neu"][p["D01_Stufenwelle"]["_zukauf"]["neu"]]
        soll = dp.richtpreis(D["D01_Stufenwelle"], "S235-10219", einst, 10)
        assert bezuege[0]["preise"] == [dict(ab=1, preis=soll)] and dp.HINWEIS in werte["beschreibung"], bezuege
        e = dp.lesen(p["D01_Stufenwelle"]["technik"])
        assert e["daten"]["art"] == "Drehteil" and e["stueck"] == 10 and e["richtpreise"] == [dict(ab=1, preis=soll)]
        assert any("EK = Richtpreis" in z for z in erg["bericht"]), erg["bericht"]
        aid = db.zukauf_speichern(None, werte, bezuege)
        assert not zukauf.ek_fehlt(db.zukauf_artikel(aid))
        # Wiederholteil mit EK: bleibt (Frage 5 a)
        erg = step.uebernehmen([dict(JE["D01_Stufenwelle"])], [], k, db.zeilen("gewinde"), None, "S235-10219", 3,
                               zukauf_liste=db.zukauf_artikel_liste(), drehfraes_einst=einst)
        assert erg["positionen"][0]["_zukauf"] == {"artikel_id": aid} and not erg["zukauf_neu"]
        # Funktion aus: wie bisher ohne EK, ohne Eingaben
        erg = step.uebernehmen([dict(JE["D06_Platte_Tasche"])], [], k, db.zeilen("gewinde"), None, "S235-10219", 1,
                               zukauf_liste=[])
        _, bz = next(iter(erg["zukauf_neu"].values()))
        assert bz[0]["preise"] == [] and not erg["positionen"][0].get("technik")
        db.con.close()


@fall("R5 Staffeln: Richtpreis für die Stückzahl der Stufe, EK aus dem Einkauf geht vor")
def _():
    einst = dp.einstellungen()
    e = dp.aus_step(D["D01_Stufenwelle"], "S235JR", 10)
    rp10 = dp.richtpreis(D["D01_Stufenwelle"], "S235JR", einst, 10)
    e["richtpreise"] = [dict(ab=1, preis=rp10)]
    stand = dict(bezug=dict(lieferant=None, preise=[dict(ab=1, preis=rp10)], preiseinheit=1))
    p = dict(pos=10, art="Zukaufteil", stueck=10, technik=dp.speichern(e),
             zukauf=json.dumps([dict(artikel_id=1, menge=1, je="Teil", stand=stand)]))
    neu, text = staffeln.drehfraes_stand(p, 100, einst)
    rp100 = dp.richtpreis(D["D01_Stufenwelle"], "S235JR", einst, 100)
    assert neu[0]["stand"]["bezug"]["preise"] == [dict(ab=1, preis=rp100)] and rp100 < rp10, (neu, rp100, rp10)
    assert "Richtpreis" in text and "100 St" in text, text
    assert staffeln.drehfraes_stand(p, 10, einst) == (None, None)
    # Lieferant hat ab 50 Stück einen echten Preis: der gilt in der Stufe 100
    stand["bezug"]["preise"].append(dict(ab=50, preis=4.2))
    p["zukauf"] = json.dumps([dict(artikel_id=1, menge=1, je="Teil", stand=stand)])
    neu, text = staffeln.drehfraes_stand(p, 100, einst)
    assert neu[0]["stand"]["bezug"]["preise"] == [dict(ab=50.0, preis=4.2)] and "Einkauf" in text, (neu, text)


@fall("R6 Angebot: Rechtsklick „Richtpreis Dreh-/Frästeil …“, Dialog mit Ampel/Skizze, Zeit von Hand, EK ab Stückzahl")
def _():
    from PySide6.QtWidgets import QApplication, QDialog
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as tmp:
        db = Datenbank(Path(tmp) / "rohrlaser.db")
        a = db.angebot_neu(dict(kunde="Test", maschine="T03"))
        fenster = Hauptfenster(db, stumm=True)
        s = fenster.angebot_oeffnen(a)
        s.step_importieren([str(TMP / "D01_Stufenwelle.step"), str(TMP / "D06_Platte_Tasche.step")],
                           "S235-10219", 20, als_satz=False)
        zeilen = [i for i, p in enumerate(s.positionen) if dp.lesen(p.get("technik"))]
        assert len(zeilen) == 2, [p.get("bezeichnung") for p in s.positionen]
        assert s.position_art(s.positionen[zeilen[0]]) == "drehfraes"
        assert "Richtpreis Dreh-/Frästeil …" in [x.text() for x in s.pos_menue.actions()]
        p = s.positionen[zeilen[0]]
        aid = json.loads(p["zukauf"])[0]["artikel_id"]
        preise = json.loads(db.zukauf_artikel(aid)["bezuege"][0]["preise"])
        assert preise and preise[0]["preis"] > 0, preise
        gesehen = {}

        def aendern(d):
            gesehen["ampel"] = d.ergebnis["ampel"]
            gesehen["text"] = d.befunde.text()
            gesehen["vorher"] = d.ergebnis["richtpreis"]
            d.skizze.grab()
            r = next(i for i in range(d.tabelle.rowCount()) if d.tabelle.item(i, 0).text() == "Drehen schruppen")
            d.tabelle.item(r, 2).setText("3,5")
            d.stueck.setValue(50)
            gesehen["nachher"] = d.ergebnis["richtpreis"]
            gesehen["hand"] = d.eingaben()["zeiten"]
            return QDialog.Accepted

        from rohrlaser import angebot_check
        assert dp.ek_ist_richtpreis(p)
        punkte = angebot_check.punkte(s.kopf, s.positionen, ["OK"] * len(s.positionen), "aktuell", {})
        assert any(art == "HINWEIS" and "Richtpreis (Schätzung)" in text for art, text in punkte), punkte
        assert s.drehfraes_bearbeiten(zeilen[0], dialog=aendern)
        assert gesehen["ampel"] == dp.GRUEN and "machbar" in gesehen["text"], gesehen
        assert gesehen["hand"] == {"Drehen schruppen": 3.5}, gesehen
        p = db.positionen(a)[[i for i, x in enumerate(db.positionen(a)) if x["id"] == p["id"]][0]]
        e = dp.lesen(p["technik"])
        assert p["stueck"] == 50 and e["zeiten"] == {"Drehen schruppen": 3.5}
        preise = json.loads(db.zukauf_artikel(aid)["bezuege"][0]["preise"])
        assert any(x["ab"] == 50 and abs(x["preis"] - gesehen["nachher"]) < 0.005 for x in preise), preise
        assert any(r["ab"] == 50 for r in e["richtpreise"])
        # Frästeil: Dialog zeigt Draufsicht/Seitenansicht ohne Fehler
        d_ = {}

        def ansehen(d):
            d.skizze.grab()
            d_["roh"] = d.ergebnis["rohling"]["text"]
            return QDialog.Rejected
        assert not s.drehfraes_bearbeiten(zeilen[1], dialog=ansehen) and d_["roh"].startswith("Flachstahl")
        fenster.close()
        app.processEvents()
        db.con.close()


sys.exit(1 if fehler else 0)
