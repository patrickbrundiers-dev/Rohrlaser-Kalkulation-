"""Zukaufkosten je Satz und Häkchen der Zukaufteile im Import (Patrick 03.11.2026: „Bleche automatisch abhaken beim
Import wenn Schweißbaugruppe ausgewählt ist, sonst immer manuell entscheiden“, „Pro Satz die Option, die kompletten
Blechkosten pro Satz einzutragen, die dann auf die einzelnen Teile umgelegt werden“; Freigabe „Alle Empfehlungen, zu 1
alle Zukaufteile, dann separate Kosten“):
- K1 Umlegen nach Gewicht (ohne Gewicht nach Stück), je Art getrennt (Bleche, Vollmaterial, Dreh-/Frästeile), 0 nimmt
  den Betrag wieder weg.
- K2 zukauf.rechnen: der feste EK ersetzt den EK des Artikels (auch wenn der fehlt), Aufschlag wie bisher.
- K3 Fenster „Satz bearbeiten“: Felder nur für vorhandene Arten, Betrag gespeichert, wieder angezeigt, Rückgängig.
- K4 Prüfdialog: Zukaufteile nur mit „als Schweißbaugruppe“ angehakt; Umschalten zieht mit, von Hand gesetzte bleiben.

Aufruf: python tests/test_satz_kosten.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rohrlaser import satz_kosten, zukauf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

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


def eintrag(kat, menge=1, ek=None):
    bezug = dict(lieferant="L", preise=[dict(ab=1, preis=ek)]) if ek else None
    return dict(artikel_id=None, menge=menge, stand=dict(bezeichnung=f"Teil {kat}", kategorie=kat, einheit="Stück",
                                                          bezug=bezug, regeln=[zukauf.regel(zukauf.PROZENT, 10)]))


def satz_pos():
    return [dict(id=1, satz="G", je_satz=2, stueck=10, gewicht_teil=1.5, zukauf=[eintrag("Blechteile")]),
            dict(id=2, satz="G", je_satz=1, stueck=5, gewicht_teil=3.0, zukauf=[eintrag("Blechteile")]),
            dict(id=3, satz="G", je_satz=4, stueck=20, gewicht_teil=0.5, zukauf=[eintrag("Vollmaterial")]),
            dict(id=4, satz="G", je_satz=1, stueck=5, gewicht_teil=None, zukauf=[eintrag("Drehteile")]),
            dict(id=5, satz="G", je_satz=1, stueck=5, gewicht_teil=None, zukauf=[eintrag("Frästeile")]),
            dict(id=6, stueck=3, gewicht_teil=2.0, zukauf=[eintrag("Blechteile")])]


@fall("K1 Umlegen je Art: Bleche nach Gewicht, Dreh-/Frästeile ohne Gewicht nach Stück, 0 nimmt es weg")
def _():
    pos = satz_pos()
    assert satz_kosten.arten(pos, "G") == ["Bleche", "Vollmaterial", "Dreh-/Frästeile"]
    aend = satz_kosten.verteilen(pos, "G", {"Bleche": 120.0, "Dreh-/Frästeile": 50.0})
    neu = {pid: json.loads(w) for pid, f, w in aend}
    assert set(neu) == {1, 2, 4, 5}, set(neu)          # Vollmaterial ohne Betrag, Pos. 6 nicht im Satz
    # Bleche: Pos. 1 2 × 1,5 kg = 3 kg, Pos. 2 1 × 3 kg = 3 kg -> je 60 € je Satz; je Teil 30 € bzw. 60 €
    assert neu[1][0]["ek_fest"] == 30.0 and neu[2][0]["ek_fest"] == 60.0, (neu[1], neu[2])
    assert neu[1][0]["satzkosten"] == dict(art="Bleche", betrag=120.0, nach="Gewicht")
    assert neu[4][0]["ek_fest"] == 25.0 and neu[5][0]["satzkosten"]["nach"] == "Stück"
    for p in pos:
        if p["id"] in neu:
            p["zukauf"] = neu[p["id"]]
    assert satz_kosten.betraege(pos, "G") == {"Bleche": 120.0, "Dreh-/Frästeile": 50.0}
    aend = satz_kosten.verteilen(pos, "G", {"Bleche": 0})
    assert {pid for pid, *_ in aend} == {1, 2} and all("ek_fest" not in json.loads(w)[0] for *_, w in aend)
    # Stück je Satz aus dem Fenster (je) zählt statt der Position
    pos = satz_pos()
    neu = {pid: json.loads(w) for pid, f, w in satz_kosten.verteilen(pos, "G", {"Bleche": 120.0}, je={1: 1})}
    assert neu[1][0]["ek_fest"] == 40.0 and neu[2][0]["ek_fest"] == 80.0, (neu[1], neu[2])


@fall("K2 Rechnen: fester EK je Einheit statt Artikel-EK (auch ohne EK), Aufschlag wie bisher")
def _():
    e = dict(eintrag("Blechteile", ek=99), ek_fest=30.0)
    _, je = zukauf.rechnen([("a", e, 10)])
    assert je["a"]["einstand"] == Decimal("300") and not je["a"]["fehler"], je["a"]
    assert je["a"]["aufschlag"] == Decimal("30"), je["a"]["aufschlag"]
    _, je = zukauf.rechnen([("b", dict(eintrag("Blechteile"), ek_fest=12.5), 4)])
    assert je["b"]["einstand"] == Decimal("50") and not je["b"]["fehler"], je["b"]
    _, je = zukauf.rechnen([("c", eintrag("Blechteile"), 4)])
    assert je["c"]["fehler"] == "kein Einkaufspreis"


@fall("K3 Fenster Satz bearbeiten: Felder je vorhandener Art, Betrag gespeichert und wieder angezeigt, Rückgängig")
def _():
    from rohrlaser.angebot import ZUKAUFTEIL
    QApplication.instance() or QApplication([])
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "rohrlaser.db")
    fenster = Hauptfenster(db, tmp, stumm=True)
    a = db.angebot_neu(dict(kunde="Test", kundennr="4711"))
    for nr, kat, je, g in ((10, "Blechteile", 2, 1.5), (20, "Blechteile", 1, 3.0), (30, "Drehteile", 1, 0.2)):
        db.position_neu(a, dict(pos=nr, artikel=f"T{nr}", art=ZUKAUFTEIL, stueck=4 * je, satz="Gestell", je_satz=je,
                                gewicht_teil=g, zukauf=json.dumps([eintrag(kat)])))
    s = fenster.angebot_oeffnen(a)
    QApplication.processEvents()
    gesehen = {}

    def bedienen(d):
        gesehen["felder"] = list(d.kosten_felder)
        d.kosten_felder["Bleche"].setValue(240)
        d._ok()
        return QDialog.Accepted

    assert s.satz_bearbeiten(0, dialog=bedienen)
    assert gesehen["felder"] == ["Bleche", "Dreh-/Frästeile"], gesehen
    ek = [(zukauf.json_liste(p["zukauf"])[0].get("ek_fest")) for p in s.positionen]
    assert ek == [60.0, 120.0, None], ek
    wieder = {}
    s.satz_bearbeiten(0, dialog=lambda d: wieder.update(b=d.kosten_felder["Bleche"].value()) or QDialog.Rejected)
    assert wieder["b"] == 240, wieder
    s.rueckgaengig()
    QApplication.processEvents()
    assert all("ek_fest" not in zukauf.json_liste(p["zukauf"])[0] for p in s.positionen), "Rückgängig"
    fenster.close()
    db.con.close()


@fall("K4 Prüfdialog: Zukaufteile nur mit „als Schweißbaugruppe“ angehakt, Umschalten zieht mit, Hand bleibt")
def _():
    sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
    sys.path.insert(0, str(HIER))
    import step_messen
    from formen_baukasten import ohne, quader, schreibe
    from rohrlaser import step
    from rohrlaser.step_dialog import StepPruefDialog
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    QApplication.instance() or QApplication([])
    tmp = Path(tempfile.mkdtemp())
    c = TopoDS_Compound()
    bb = BRep_Builder()
    bb.MakeCompound(c)
    for s_ in (ohne(quader(40, 40, 600), quader(34, 34, 600, 3, 3)), quader(300, 200, 5, 200, 100, 800),
               quader(250, 120, 4, 200, 400, 900)):
        bb.Add(c, s_)
    schreibe({"BG": c}, tmp)
    aus, js = tmp / "m.txt", tmp / "m.json"
    step_messen.main(["--ausgabe", str(aus), "--json", str(js), "--flachstahl-bis", "0", str(tmp / "BG.step")])
    db = Datenbank(tmp / "r.db")
    mw = step.lies_messwerte(aus)
    d = StepPruefDialog(None, mw, db.kontext(), "S235-10219", 1, db.zukauf_artikel_liste())
    bl = [z for z in d.zeilen if z.blech]
    rohr = [z for z in d.zeilen if not z.blech]
    assert len(bl) == 2 and rohr, (len(bl), len(rohr))
    zust = lambda: [z.it.checkState(0) == Qt.Checked for z in bl]  # noqa: E731
    assert zust() == [False, False], "ohne Schweißbaugruppe nicht angehakt"
    assert all(z.it.checkState(0) == Qt.Checked for z in rohr)
    d.bg_haken.setChecked(True)
    assert zust() == [True, True], "mit Schweißbaugruppe angehakt"
    bl[0].it.setCheckState(0, Qt.Unchecked)          # von Hand
    d.bg_haken.setChecked(False)
    d.bg_haken.setChecked(True)
    assert zust() == [False, True], zust()
    d.werte_schreiben()
    assert [mw[i]["_uebernehmen"] for i in bl[1].liste] == [True]
    d.close()
    db.con.close()


if fehler:
    print(f"{fehler} Fall/Fälle rot")
    sys.exit(1)
print("Alle Prüfungen bestanden.")
