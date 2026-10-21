"""Prüft Positionen der Art Zukaufteil (Plan 4 b: Blech als eigene Position): Kalkulation (nur Einstand + Aufschlag
+ Fracht, mit Skonto; Rohrlaserteile unverändert), Status und Hinweis bei fehlendem EK (0 € zählt nicht), keine
Optimierung, Fracht je Stück und nach Gewicht, Angebot nur aus Zukaufteilen, Angebotstext, Satz, Staffelpreise,
Nachkalkulation, Werkstattpapiere, PDF und CSV-Export. Alle Preise sind Testwerte.

Aufruf: python tests/test_blech_position.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import ausgabe, export, nachkalkulation, pdf, rechnen, staffeln, zukauf  # noqa: E402
from rohrlaser.angebot import ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())
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


def nah(a, b, text, eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


db = Datenbank(tmp / "b.db")
# Blech S235 500 × 300 × 5: 20,00 € je Stück bei Technik, 25 % Aufschlag individuell
B = dict(laenge=500.0, breite=300.0, dicke=5.0, kontur="rechteckig", fingerabdruck="x")
werte, bezuege = zukauf.blech_artikel(B, "S235-10219", "Rahmen.step")
werte.update(aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT, aufschlag_wert=25)
blech = db.zukauf_speichern(None, werte, bezuege)
db.zukauf_ek_eintragen(blech, 20, "Technik")
ohne_ek = db.zukauf_speichern(None, *zukauf.blech_artikel(dict(B, laenge=400), None))


def eintrag(aid, menge=1):
    return json.dumps([dict(artikel_id=aid, menge=menge, stand=db.zukauf_stand(aid))])


a = db.angebot_neu(dict(kunde="Test", skonto=2, mindestpreis=0))   # Mindestpreis: eigener Test (test_angebot_vorgaben)
rohr = db.position_neu(a, dict(pos=10, artikel="R", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                               stueck=10, schneidweg=300, einstiche=2, satz="BG", je_satz=1))
k, tab = db.kontext(), db.tabellen()


def rechnung(aid=a):
    kopf, pos = db.angebot(aid), db.positionen(aid)
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    erg = rechnen.optimieren(kopf, pos, k)
    return kopf, pos, einst, erg, rechnen.kalkulation(kopf, pos, erg, k, tab, einst)


_, _, _, _, (z0, s0) = rechnung()
pb = db.position_neu(a, dict(pos=20, art=ZUKAUFTEIL, artikel="B1", bezeichnung="Blech", stueck=4, laenge=500,
                             satz="BG", je_satz=1, gewicht_teil=5.888))
db.position_aendern(pb, "zukauf", eintrag(blech))
KOPF, POS, EINST, ERG, (Z, S) = rechnung()


@fall("Kalkulation: Zukaufteil = (Einstand + Aufschlag) / (1 − Skonto), Rohrlaserteil unverändert")
def _():
    zb = Z[1]
    assert zb is not None and zb["zukaufteil"], zb
    nah(zb["zukauf_einstand_teil"], 20, "Einstand je Teil")
    nah(zb["zukauf_aufschlag_teil"], 5, "25 % Aufschlag")
    nah(zb["preis_teil"], 25 / 0.98, "mit Skonto 2 %")
    nah(zb["skonto_teil"], 25 / 0.98 - 25, "Skonto je Teil")
    for n in ("material_teil", "laser_teil", "ruesten_teil", "herstell_teil", "gewinn_teil", "pauschalen_teil"):
        assert zb[n] == 0, (n, zb[n])
    assert zb["hinweis"] == "", zb["hinweis"]
    nah(Z[0]["preis_teil"], z0[0]["preis_teil"], "Rohr: Rüsten, Pauschalen und Aufschlag nur auf Rohrlaserteile")
    assert S["teile"] == s0["teile"] == 10 and S["zukaufteile"] == 4
    nah(S["verkauf"], s0["verkauf"] + 4 * 25 / 0.98, "Summe Verkauf")
    nah(S["zukauf_einstand"], s0["zukauf_einstand"] + 80, "Summe Einstand Zukaufteile")


@fall("Optimierung: Zukaufteil kommt nicht in den Schnittplan und nicht in die Fehlerliste")
def _():
    assert all(t["artikel"] != "B1" for s in ERG["stangen"] for t in s["teile"])
    assert not ERG["fehler"], ERG["fehler"]


@fall("Status: OK; ohne Zukaufartikel FEHLER; ohne EK (auch 0 €) WARNUNG und Hinweis 'kein Einkaufspreis'")
def _():
    p = POS[1]
    w = rechnen.position_werte(p, KOPF, k, tab)
    assert rechnen.status(p, w, KOPF, k, None) == "OK"
    nah(w["gewicht"], 5.888, "Gewicht je Teil aus der Position")
    leer = dict(p, zukauf=None)
    assert rechnen.status(leer, w, KOPF, k).startswith("FEHLER: Zukaufartikel fehlt")
    assert rechnen.status(dict(p, stueck=None), w, KOPF, k) == "FEHLER: Stückzahl fehlt"
    ohne = dict(p, zukauf=eintrag(ohne_ek))
    assert rechnen.status(ohne, w, KOPF, k) == "WARNUNG: EK fehlt (Zukaufteil ohne Einkaufspreis)"
    st = db.zukauf_stand(blech)
    st["bezug"]["preise"] = [dict(ab=1, preis=0)]
    null = dict(p, zukauf=json.dumps([dict(artikel_id=blech, menge=1, stand=st)]))
    assert rechnen.status(null, w, KOPF, k).startswith("WARNUNG: EK fehlt"), "0 € ist kein EK"
    pos = [POS[0], null]
    zz, ss = rechnen.kalkulation(KOPF, pos, rechnen.optimieren(KOPF, pos, k), k, tab, EINST)
    assert zz[1]["hinweis"] == "Zukaufteil: kein Einkaufspreis" and ss["zukauf_fehlt"] >= 1, zz[1]["hinweis"]
    nah(zz[1]["preis_teil"], 0, "ohne EK kein Preis")


@fall("Fracht: je Stück auf alle Teile, nach Gewicht mit dem Gewicht je Teil")
def _():
    kopf = dict(KOPF, fracht=140, fracht_umlage="je Stück")
    zz, ss = rechnen.kalkulation(kopf, POS, ERG, k, tab, EINST)
    nah(zz[1]["fracht_teil"], 10, "140 € / 14 Teile")
    nah(zz[1]["preis_teil"], 35 / 0.98, "Fracht im Preis des Zukaufteils")
    kopf = dict(kopf, fracht_umlage="nach Gewicht")
    zz, ss = rechnen.kalkulation(kopf, POS, ERG, k, tab, EINST)
    w_rohr = rechnen.position_werte(POS[0], kopf, k, tab)["gewicht"]
    gesamt = 10 * w_rohr + 4 * 5.888
    nah(zz[1]["fracht_teil"], 140 * 5.888 / gesamt, "nach Gewicht", 1e-6)
    nur = [POS[1]]
    zz, ss = rechnen.kalkulation(dict(KOPF, fracht=40, fracht_umlage="je Stück"), nur, rechnen.optimieren(KOPF, nur, k), k, tab, EINST)
    nah(zz[0]["fracht_teil"], 10, "Angebot nur mit Zukaufteilen trägt die Fracht")
    nah(ss["angebotsaufschlag"], 0, "kein Angebotsaufschlag ohne Rohrlaserteile")
    nah(ss["programmierung"], 0, "keine Programmierkosten für Zukaufteile")


@fall("Angebot: Text aus dem Zukaufartikel, eigene Zeile bzw. Teil des Satzes")
def _():
    ang = ausgabe.angebot(KOPF, POS, Z, k, EINST)
    assert ang["zeilen"][0]["art"] == "satz", ang["zeilen"]
    texte = [z["text"] for z in ang["zeilen"]]
    assert "   1 x Blech S235-10219 500 × 300 × 5 mm" in texte, texte
    nah(ang["zeilen"][0]["preis"], ausgabe.kaufm_runden(Z[0]["preis_teil"], 2) + ausgabe.kaufm_runden(25 / 0.98, 2),
        "Satzpreis mit Blech")
    pos = [dict(POS[0], satz=None), dict(POS[1], satz=None)]
    ang = ausgabe.angebot(KOPF, pos, Z, k, EINST)
    b = ang["zeilen"][1]
    assert b["text"] == "Blech S235-10219 500 × 300 × 5 mm" and b["menge"] == 4, b
    nah(b["preis"], 25.51, "kaufmännisch gerundet")


@fall("Staffelpreise: Satz mit Blech und Position nur Blech ohne 'Materialpreis fehlt'")
def _():
    assert any(s[0] == "BG" for s in staffeln.auswahl(POS))
    z = staffeln.stufe_rechnen(KOPF, POS, "BG", 20, k, tab, EINST)
    assert z["bausteine"] and not z["bausteine"]["material_fehlt"], z
    nah(z["bausteine"]["zukauf_einstand"] - s0["zukauf_einstand"] * 2, 20 * 20, "Einstand 20 Bleche")
    pos = [dict(POS[0], satz=None), dict(POS[1], satz=None)]
    assert "20" in [s[0] for s in staffeln.auswahl(pos)]
    z = staffeln.stufe_rechnen(KOPF, pos, "20", 10, k, tab, EINST)
    assert z["bausteine"] and not z["bausteine"]["material_fehlt"] and z.get("preis_einheit"), z
    assert not (z.get("hinweis") or "").startswith("FEHLER"), z["hinweis"]


@fall("Nachkalkulation: Zeile Zukaufteile (Einstand) im Soll, Ist erfassbar")
def _():
    v = nachkalkulation.vergleich(KOPF, POS, ERG, k, tab, EINST, {"zukauf": 90})
    z = next(x for x in v["zeilen"] if x["text"] == "Zukaufteile (Einstand)")
    nah(z["soll"], S["zukauf_einstand"], "Soll")
    nah(z["ist"], 90, "Ist")
    assert [x["text"] for x in v["zeilen"]].index("Zukaufteile (Einstand)") == 4


@fall("Werkstattpapiere, PDF und CSV: Zukaufteil als eigene Liste bzw. Zeile")
def _():
    wp = ausgabe.werkstatt(KOPF, POS, ERG, k, tab)
    assert wp["zukaufteile"] == [dict(pos=20, artikel="B1", bezeichnung="Blech", stueck=4,
                                      text="Blech S235-10219 500 × 300 × 5 mm")], wp["zukaufteile"]
    pdf.werkstatt_pdf(tmp / "w.pdf", KOPF, wp)
    pdf.kalkulation_pdf(tmp / "k.pdf", KOPF, Z, S, EINST)
    ang = ausgabe.angebot(KOPF, POS, Z, k, EINST)
    ang["anschrift"] = ""
    pdf.angebot_pdf(tmp / "a.pdf", KOPF, ang, EINST)
    export.angebot_csv(tmp / "a.csv", KOPF, Z, S, EINST)
    text = (tmp / "a.csv").read_text(encoding="utf-8-sig")
    assert "B1" in text
    for n in ("w.pdf", "k.pdf", "a.pdf"):
        assert (tmp / n).stat().st_size > 1000, n
    nur = [POS[1]]
    wp = ausgabe.werkstatt(KOPF, nur, rechnen.optimieren(KOPF, nur, k), k, tab)
    assert wp["muster"] == [] and len(wp["zukaufteile"]) == 1


db.con.close()
sys.exit(1 if fehler else 0)
