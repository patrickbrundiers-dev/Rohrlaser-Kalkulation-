"""Bauteil aus Text (bauteil_generator.py, Wettbewerbsanalyse 247TailorSteel 20.11.2026, „Parts Builder“ lokal):
- lesen: Beispielsatz aus dem Auftrag, Gestell mit eigenem Strebenprofil, Rundrohr in m, Blechteile (Lasche, L-Winkel,
  Flanschring); nicht zugeordnete Zahlen erscheinen als „nicht verstanden“
- bauen: Rahmen + Querstreben (senkrecht, waagrecht, Bodenstreben) mit Stößen und richtigen Längen, Platten mit
  Lochbild und Lage, Annahmen gekennzeichnet, Fehler (Profil fehlt, zu lang, Platte zu klein, Rundrohr/Vierkant)
- aendern: nur Genanntes ändert sich, „ohne …“, Verlauf im Fenster mit Zurücknehmen
- Stufe 2: Rückfragen mit Knöpfen statt stiller Annahmen, Bohrungen in Rohren („2 Bohrungen Ø 9 in den
  Querstreben“) als Konturen mit Prüfung, Geländer (Pfosten gesamt/zusätzlich) und Tischgestell mit Mittelstrebe,
  gespeicherten Satz per Text ändern (alte Positionen ersetzt, Rückgängig), Beschreibung bleibt nach Satz in 3D
- im Angebot: Neue Position → Bauteil aus Text legt Satz (Rohre mit Schneidweg, Netz, Stöße) und Platten (Blech im
  Satz) an, Satz in 3D zeigt alle Rohre; Blechteil allein wird eine Position; fehlendes Profil wird gemeldet

Aufruf: python tests/test_bauteil_generator.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))

from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from rohrlaser import bauteil_generator as bg, blech, rahmen  # noqa: E402
from rohrlaser.baugruppe_ansicht import in_lage  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.neue_position import TEXT_BAUTEIL  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(t):
    print("OK    ", t)


def huelle(plan):
    lo, hi = [1e9] * 3, [-1e9] * 3
    for t in plan["erg"]["teile"]:
        p = plan["werte"]["streben_profil"] if t.get("profil") else plan["werte"]["profil"]
        n = rahmen.netz(t, p)
        for lage in n["lagen"]:
            for i in range(0, len(n["p"]), 3):
                q = in_lage(n["p"][i:i + 3], lage)
                for k in range(3):
                    lo[k], hi[k] = min(lo[k], q[k]), max(hi[k], q[k])
    return [round(v, 1) for v in lo], [round(v, 1) for v in hi]


BEISPIEL = ("Erstelle einen rechteckigen Rohrrahmen aus 40 x 40 x 3 mm Stahlrohr mit vier Querstreben und zwei "
            "Befestigungsplatten. Außenmaß 1000 x 600 mm")

# ------------------------------------------------------------------ lesen
w, erkannt, unklar = bg.lesen(BEISPIEL)
assert w["art"] == bg.RAHMEN and w["form"] == rahmen.RAHMEN and (w["b"], w["h"]) == (1000, 600), w
assert w["profil"] == dict(form="Quadratrohr", a=40, b=40, wand=3) and w["streben"] == 4 and w["platten"] == 2, w
assert not unklar and "Profil QR 40x40x3" in erkannt, (erkannt, unklar)
w2, _, _ = bg.lesen("Erstelle einen rechteckigen Rohrrahmen 1000 x 600 mm aus 40 x 40 x 3 mm Stahlrohr mit vier "
                    "Querstreben und zwei Befestigungsplatten.")
assert {k: w2[k] for k in ("b", "h", "profil", "streben", "platten")} == {k: w[k] for k in ("b", "h", "profil",
                                                                                           "streben", "platten")}
g, _, u = bg.lesen("Gestell 1200 x 800 x 900 aus 40x40x3 S235, stumpf, 2 Querstreben aus 30 x 30 x 2, 4 Fußplatten "
                   "120 x 120 x 10 mit 4 Bohrungen Ø 13, 5 Stück")
assert g["form"] == rahmen.QUADER and (g["b"], g["t"], g["h"]) == (1200, 800, 900) and g["ecken"] == rahmen.STUMPF
assert g["streben_profil"]["a"] == 30 and g["platte"] == dict(laenge=120, breite=120, dicke=10), g
assert g["bohrungen"] == dict(anzahl=4, d=13) and g["saetze"] == 5 and g["werkstoff_wort"] == "S235" and not u, (g, u)
r, _, u = bg.lesen("Rahmen aus Rundrohr Ø 48,3 x 2,6, Breite 1,2 m, Höhe 800, 3 waagrechte Streben")
assert r["profil"]["form"] == "Rundrohr" and r["b"] == 1200 and r["h"] == 800 and r["streben_richtung"] == bg.WAAGRECHT
la, _, u = bg.lesen("Lasche 80 x 40 x 5 mit 2 Bohrungen Ø 9, Edelstahl 1.4301, 20 Stück")
assert la["art"] == bg.BLECH and la["blech"] == dict(typ=bg.PLATTE, laenge=80, breite=40, dicke=5) and not u, la
assert la["werkstoff_wort"] == "1.4301" and la["bohrungen"] == dict(anzahl=2, d=9)
_, _, u = bg.lesen("Rohrrahmen 1000 x 600 aus 40 x 40 x 3 mit Abstand 77")
assert u == ["Zahl 77 nicht zugeordnet"], u
ok("lesen: Beispielsatz aus dem Auftrag (beide Wortstellungen), Gestell mit Strebenprofil, Rundrohr in m, Lasche; "
   "unbekannte Zahl als „nicht verstanden“")

# ------------------------------------------------------------------ bauen
p = bg.bauen(w)
assert not p["fehler"], p["fehler"]
assert bg.zusammenfassung(p) == ["2 × Rahmen waagrecht 1000 mm QR 40x40x3", "2 × Rahmen senkrecht 600 mm QR 40x40x3",
                                 "4 × Querstrebe 520 mm QR 40x40x3",
                                 "2 × Befestigungsplatte 100 × 100 × 8 mm mit 4 Bohrungen Ø 13"], bg.zusammenfassung(p)
assert any("Gehrung" in a for a in p["annahmen"]) and any("Plattendicke 8" in a for a in p["annahmen"]), p["annahmen"]
assert len(p["erg"]["stoesse"]) == 8 and {s["aufnahme"] for s in p["erg"]["stoesse"]} == {1, 2}
assert huelle(p) == ([0.0, -20.0, 0.0], [1000.0, 20.0, 600.0]), huelle(p)
xs = sorted(lg[0] for t in p["erg"]["teile"] if t["name"] == "Querstrebe" for lg in t["lagen"])
assert xs == [224.0, 408.0, 592.0, 776.0], xs                  # gleichmäßig im lichten Maß 40 … 960
e = bg.blech_e(p, "S235JR")
assert len(e["konturen"]) == 4 and {(k["x"], k["y"]) for k in e["konturen"]} == {(19.5, 19.5), (80.5, 19.5),
                                                                                  (19.5, 80.5), (80.5, 80.5)}
assert [lg[:3] for lg in p["platten"]["lagen"]] == [[0.0, -50.0, -4.0], [900.0, -50.0, -4.0]]
n = bg.vorschau(p, e)
q = n["p"]
assert (min(q[0::3]), max(q[0::3]), min(q[1::3]), max(q[1::3]), min(q[2::3]), max(q[2::3])) == \
    (0.0, 1000.0, -50.0, 50.0, -8.0, 600.0)
pg = bg.bauen(g)
assert not pg["fehler"] and "2 × Bodenstrebe 720 mm QR 30x30x2" in bg.zusammenfassung(pg), bg.zusammenfassung(pg)
assert huelle(pg) == ([0.0, 0.0, 0.0], [1200.0, 800.0, 900.0]) and len(pg["erg"]["stoesse"]) == 16 + 4
assert len(pg["platten"]["lagen"]) == 4
pr = bg.bauen(r)
assert not pr["fehler"] and "3 × Querstrebe waagrecht 1151.7 mm RR 48,3x2,6" in bg.zusammenfassung(pr)
assert {t["eingaben"]["a"].get("sattel") for t in pr["erg"]["teile"] if "Querstrebe" in t["name"]} == {48.3}
for text, teil in (("Rohrrahmen 1000 x 600", "Profil fehlt"), ("Rahmen aus 40 x 40 x 3", "Außenmaße fehlen"),
                   ("Rahmen 7000 x 600 aus 40 x 40 x 3", "länger als die Stange"),
                   ("Rahmen 1000 x 600 aus 60 x 60 x 3, 2 Platten 50 x 50 x 8", "kleiner als das Rohr"),
                   ("Rahmen aus Rundrohr Ø 48,3 x 2,6, 1000 x 600, 2 Querstreben aus 30 x 30 x 2", "Rundrohr gehen nicht"),
                   ("Rahmen 1000 x 600 aus 40 x 40 x 3, 3 Platten 400 x 100 x 8", "passen nicht")):
    f = bg.bauen(bg.lesen(text)[0])["fehler"]
    assert any(teil in x for x in f), (text, f)
assert any("unter dem Rohr" in h for h in bg.bauen(bg.lesen("Rahmen 1000 x 600 aus 40 x 40 x 3, 2 Platten "
                                                           "100 x 60 x 8 mit 2 Bohrungen Ø 13")[0])["hinweise"])
fehlt = bg.bauen(bg.lesen("Rahmen 1000 x 600 aus 50 x 30 x 2")[0], {"QR 40x40x3": dict(form="Quadratrohr", a=40, b=40,
                                                                                         wand=3)})
assert fehlt["fehlende_profile"] == ["RE 50x30x2"], fehlt
for text, erwartet in (("L-Winkel 60 x 40 x 5, Länge 100 mit 2 Bohrungen Ø 9", 1),
                       ("Flanschring Ø 200 x Ø 100 x 8 mit 6 Bohrungen Ø 11 auf Lochkreis 160", 7),
                       ("Lasche 80 x 40 x 5 mit 2 Bohrungen Ø 9", 2)):
    pb = bg.bauen(bg.lesen(text)[0])
    eb = bg.blech_e(pb, "S235JR")
    assert not pb["fehler"] and len(eb["konturen"]) == erwartet and blech.zuschnitt(eb), (text, pb["fehler"], eb)
    assert bg.vorschau(pb, eb), text
assert bg.bauen(bg.lesen("Flanschring Ø 200 x Ø 100 x 8 mit 6 Bohrungen Ø 30 auf Lochkreis 120")[0])["fehler"]
bw = {"DC01": dict(kategorie="Stahl"), "S235JR": dict(kategorie="Stahl"), "1.4301": dict(kategorie="Edelstahl"),
      "AlMg3": dict(kategorie="Aluminium")}
assert (bg.blech_werkstoff(bw, "Stahl", None, "S235JRH"), bg.blech_werkstoff(bw, "Stahl", "Edelstahl"),
        bg.blech_werkstoff(bw, "Stahl", "alu"), bg.blech_werkstoff(bw, "Stahl")) == ("S235JR", "1.4301", "AlMg3", "DC01")
ok("bauen: Teile und Längen, Stöße, Hülle = Außenmaße, Streben gleichmäßig, Lochbild, Plattenlage, Bodenstreben mit "
   "eigenem Profil, Rundrohr mit Sattel, Fehler und Hinweise, fehlendes Profil, Blechteile mit Bohrungen")

# ------------------------------------------------------------------ ändern
w3, e3, u3 = bg.aendern(w, "Breite 1200, 6 Querstreben, Profil 50 x 50 x 4, stumpf")
assert (w3["b"], w3["h"], w3["streben"], w3["profil"]["a"], w3["ecken"], w3["platten"]) == (1200, 600, 6, 50,
                                                                                             rahmen.STUMPF, 2), w3
w4, _, _ = bg.aendern(w3, "ohne Querstreben, ohne Platten")
assert w4["streben"] == 0 and w4["platten"] == 0 and w4["b"] == 1200
w5, _, _ = bg.aendern(w3, "Platten 150 x 150 x 10")
assert w5["platte"] == dict(laenge=150, breite=150, dicke=10) and w5["streben"] == 6
ok("aendern: nur Genanntes ändert sich, „ohne …“ entfernt Streben und Platten, Plattenmaß")

# ------------------------------------------------------------------ Stufe 2
PROFILE = {"QR 40x40x3": dict(form="Quadratrohr", a=40, b=40, wand=3),
           "QR 40x40x4": dict(form="Quadratrohr", a=40, b=40, wand=4),
           "QR 30x30x2": dict(form="Quadratrohr", a=30, b=30, wand=2),
           "RR 48,3x2,6": dict(form="Rundrohr", a=48.3, b=None, wand=2.6)}


def plan_aus(text, *aenderungen):
    w_, _, u_ = bg.lesen(text)
    for x in aenderungen:
        w_, _, u2 = bg.aendern(w_, x)
        u_ += u2
    return bg.bauen(w_, PROFILE), u_


def fragen(plan):
    return {r["frage"]: r for r in plan["rueckfragen"]}


pr, _ = plan_aus(BEISPIEL)
fr = fragen(pr)
assert set(fr) == {"Wie sollen die Ecken verbunden werden?", "Wie sollen die Querstreben laufen?",
                   "Wie groß sollen die Befestigungsplatten sein?", "Welche Bohrungen bekommen die Platten?"}, fr
assert [o["text"] for o in fr["Wie sollen die Ecken verbunden werden?"]["optionen"] if o["vorschlag"]] == ["Gehrung"]
saetze_ = [o["satz"] for r in pr["rueckfragen"] for o in r["optionen"] if not o["vorschlag"]]
for z in saetze_:           # jede Antwort ist ein gültiger Änderungssatz und beantwortet ihre Frage
    pz, uz = plan_aus(BEISPIEL, z)
    assert not uz and not pz["fehler"] and len(pz["rueckfragen"]) == 3, (z, uz, pz["fehler"], fragen(pz))
pz, _ = plan_aus(BEISPIEL, "Ecken stumpf", "waagrechte Querstreben", "Platten 150 x 150 x 12", "4 Bohrungen Ø 11")
assert not pz["rueckfragen"] and pz["werte"]["ecken"] == rahmen.STUMPF and pz["platten"]["werte"]["dicke"] == 12
assert [t["name"] for t in pz["erg"]["teile"]][-1] == "Querstrebe waagrecht"
pf, _ = plan_aus("Rohrrahmen 1000 x 600 aus 50 x 50 x 3")
opt = fragen(pf)["QR 50x50x3 gibt es nicht. Welches vorhandene Profil?"]["optionen"]
assert [o["text"] for o in opt] == ["QR 40x40x3", "QR 40x40x4", "QR 30x30x2"], opt
assert not plan_aus("Rohrrahmen 1000 x 600 aus 50 x 50 x 3", opt[0]["satz"])[0]["fehler"]
assert bg.naechste_profile(dict(form="Rundrohr", a=48.3, b=None, wand=2), PROFILE)[0]["a"] == 48.3
ok("Rückfragen: Ecken, Strebenrichtung, Plattengröße, Plattenbohrungen und fehlendes Profil (nächste vorhandene) "
   "mit Vorschlag; jede Antwort ist ein gültiger Änderungssatz und beantwortet genau ihre Frage")

pb2, ub = plan_aus("Rohrrahmen 1000 x 600 aus 40 x 40 x 3 mit vier Querstreben, je 2 Bohrungen Ø 9 in den Querstreben")
assert not ub and pb2["werte"]["streben"] == 4 and pb2["werte"]["bohrungen"] is None, (ub, pb2["werte"])
qs = next(t for t in pb2["erg"]["teile"] if t["name"] == "Querstrebe")
assert qs["eingaben"]["konturen"] == [dict(art="Bohrung", anzahl=2, d=9.0, x=173.3, abstand=173.3, seite="vorne",
                                           q=0.0)], qs["eingaben"]
assert all(not t["eingaben"]["konturen"] for t in pb2["erg"]["teile"] if t["name"] != "Querstrebe")
assert "Von welcher Seite werden die Rohre gebohrt?" in fragen(pb2)
pb3, _ = plan_aus("Rohrrahmen 1000 x 600 aus 40 x 40 x 3 mit vier Querstreben, je 2 Bohrungen Ø 9 in den Querstreben",
                  "Bohrungen durchgehend", "3 Bohrungen Ø 11 im oberen Rohr")
namen = {t["name"]: t for t in pb3["erg"]["teile"]}
assert [k["seite"] for k in namen["Querstrebe"]["eingaben"]["konturen"]] == ["vorne", "hinten"]
assert namen["Rahmen oben"]["eingaben"]["konturen"][0]["anzahl"] == 3 and not namen["Rahmen unten"]["eingaben"][
    "konturen"] and len(namen["Rahmen oben"]["lagen"]) == 1, namen
assert "Rahmen waagrecht" not in namen and pb3["erg"]["stoesse"] == pb2["erg"]["stoesse"]
assert any("passt nicht in die Rohrseite" in x for x in plan_aus(
    "Rohrrahmen 1000 x 600 aus 40 x 40 x 3, 2 Bohrungen Ø 36 in den Rahmenrohren")[0]["fehler"])
assert any("gibt es in diesem Bauteil nicht" in x for x in plan_aus(
    "Rohrrahmen 1000 x 600 aus 40 x 40 x 3, 2 Bohrungen Ø 9 in den Querstreben")[0]["fehler"])
prr, _ = plan_aus("Rahmen aus Rundrohr Ø 48,3 x 2,6, Breite 1200, Höhe 800, 2 waagrechte Streben, 3 Bohrungen Ø 10 in "
                  "den Streben von oben")
assert next(t for t in prr["erg"]["teile"] if t["name"] == "Querstrebe waagrecht")["eingaben"]["konturen"][0][
    "seite"] == "oben (0°)"
assert bg.vorschau(pb3, None)
ok("Bohrungen in Rohren: Querstreben, oberes Rohr getrennt, durch beide Wände, Rundrohr als Winkel, Prüfung Ø und "
   "fehlende Rohre, Plattenbohrungen unberührt")

pg, _ = plan_aus("Geländer Länge 3000, Höhe 1100 aus 40 x 40 x 3 mit 5 Pfosten")
namen = {t["name"]: (len(t["lagen"]), t["laenge"]) for t in pg["erg"]["teile"]}
assert namen == {"Handlauf": (1, 3000.0), "Untergurt": (1, 3000.0), "Endpfosten": (2, 1020.0),
                 "Zwischenpfosten": (3, 1020.0)}, namen
assert pg["werte"]["ecken"] == rahmen.STUMPF and "Sind die 5 Pfosten mit den beiden Endpfosten gezählt?" in fragen(pg)
pg2, _ = plan_aus("Geländer Länge 3000, Höhe 1100 aus 40 x 40 x 3 mit 5 Pfosten", "5 Zwischenpfosten")
assert {t["name"]: len(t["lagen"]) for t in pg2["erg"]["teile"]}["Zwischenpfosten"] == 5
pg3, _ = plan_aus("Geländer Länge 3000, Höhe 1100 aus 40 x 40 x 3 mit 5 Pfosten",
                  "5 Pfosten einschließlich Endpfosten")
assert not any(r["frage"].startswith("Sind die") for r in pg3["rueckfragen"])
pg4, _ = plan_aus("Geländer 2000 lang aus 40 x 40 x 3 mit 10 Füllstäben aus 30 x 30 x 2")
assert "Geländer: Höhe fehlt („Höhe 1100“)." in pg4["fehler"] and "Wie hoch soll das Geländer werden?" in fragen(pg4)
pg4, _ = plan_aus("Geländer Länge 2000 aus 40 x 40 x 3 mit 10 Füllstäben aus 30 x 30 x 2", "Höhe 1000")
assert not pg4["fehler"] and {t["name"]: t.get("profil") for t in pg4["erg"]["teile"]}["Füllstab"] == "QR 30x30x2"
pt, _ = plan_aus("Tischgestell 1200 x 800 x 750 aus 40 x 40 x 3 mit Mittelstrebe")
namen = {t["name"]: (len(t["lagen"]), t["laenge"]) for t in pt["erg"]["teile"]}
assert namen["Bein"] == (4, 670.0) and namen["Mittelstrebe"] == (1, 720.0) and pt["werte"]["form"] == rahmen.QUADER
ok("Geländer: Endpfosten, Handlauf, Untergurt, Zwischenpfosten (5 Pfosten gesamt = 3 dazwischen, Rückfrage), "
   "Füllstäbe mit eigenem Profil, Höhe als Rückfrage; Tischgestell mit Beinen und Mittelstrebe")

# ------------------------------------------------------------------ im Angebot
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "generator.db")
f = Hauptfenster(db, stumm=True)
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
seite = f.angebot_oeffnen(a)
gesehen = {}


def fenster(text, *aenderungen, zurueck=False, saetze=None):
    def bedienen(d):
        d.erstellen(text)
        for x in aenderungen:
            d.aendern(x)
        if zurueck:
            d.zuruecknehmen()
        if saetze:
            d.saetze.setValue(saetze)
        gesehen["bericht"] = d.bericht.text()
        gesehen["3d"] = bool(d.ansicht.ansicht.netz)
        gesehen["ok"] = d.knoepfe.button(QDialogButtonBox.Ok).isEnabled()
        gesehen["verlauf"] = d.verlauf_liste.count()
        d._ok()
        return d.result()
    return bedienen


def satz_ansehen(d):
    gesehen["koerper"] = d.zeigen()
    d._ok()
    return d.result()


assert seite.position_neu(TEXT_BAUTEIL, dialog=fenster(BEISPIEL, "Breite 1200", "6 Querstreben", zurueck=True,
                                                       saetze=3)) == TEXT_BAUTEIL
assert gesehen["3d"] and gesehen["ok"] and gesehen["verlauf"] == 2 and "Annahmen" in gesehen["bericht"], gesehen
pos = [x for x in db.positionen(a) if x.get("satz")]
rohre = [x for x in pos if x.get("profil_id")]
platten = [x for x in pos if not x.get("profil_id")]
assert sorted((x["laenge"], x["je_satz"], x["stueck"]) for x in rohre) == [(520.0, 4, 12), (600.0, 2, 6),
                                                                           (1200.0, 2, 6)], rohre
assert all(x.get("schneidweg") for x in rohre) and all(db.netz(x["id"]) for x in rohre)
assert len(platten) == 1 and platten[0]["je_satz"] == 2 and platten[0]["stueck"] == 6, platten
assert blech.lesen(platten[0]["technik"])["laenge"] == 100
satz = pos[0]["satz"]
daten = db.satz_daten(a)[satz]
assert len(daten["stoesse"]) == 8 and daten["generator"]["verlauf"] == [BEISPIEL, "Breite 1200"], daten
assert seite.satz_3d(satz=satz, dialog=satz_ansehen) and gesehen["koerper"] == 8, gesehen
ok("Angebot: Satz mit 3 Rohrpositionen (Schneidweg, 3D) und Platte im Satz, 3 Sätze, Änderung „Breite 1200“ "
   "übernommen, „6 Querstreben“ zurückgenommen, Satz in 3D zeigt 8 Rohre, Beschreibung im Satz gespeichert")

vorher = len(db.positionen(a))
assert seite.bauteil_aus_text(dialog=fenster("Lasche 80 x 40 x 5 mit 2 Bohrungen Ø 9", saetze=20))
neu = db.positionen(a)[vorher:]
assert len(neu) == 1 and neu[0]["stueck"] == 20 and neu[0]["art"] == "Zukaufteil", neu
e = blech.lesen(neu[0]["technik"])
assert e["laenge"] == 80 and len(e["konturen"]) == 2 and e["generator"]["text"].startswith("Lasche"), e
ok("Blechteil allein: Lasche wird eine Position wie aus dem Blech-Editor (Richtpreis, Bohrungen, Beschreibung)")

vorher = len(db.positionen(a))
assert seite.bauteil_aus_text(dialog=fenster("Rahmen 1000 x 600 aus 50 x 30 x 2")) is None
assert not gesehen["ok"] and "fehlt in den Stammdaten" in gesehen["bericht"] and len(db.positionen(a)) == vorher
ok("fehlendes Profil: Übernehmen gesperrt, Meldung mit „Profil anlegen“, nichts angelegt")

GEL = "Geländer Länge 2000, Höhe 1000 aus 40 x 40 x 3 mit 4 Pfosten, je 2 Bohrungen Ø 9 im Handlauf"


def gelaender(d):
    d.erstellen(GEL)
    gesehen["fragen"] = len(d.fragen_knoepfe)
    assert d.frage_beantworten("Sind die 4 Pfosten", "ja, gesamt")
    assert d.frage_beantworten("Von welcher Seite", "von oben")
    gesehen["fragen_danach"] = [f for f, _, _ in d.fragen_knoepfe]
    d._ok()
    return d.result()


vorher = {x["id"] for x in db.positionen(a)}
name_g = seite.bauteil_aus_text(dialog=gelaender)
assert name_g and gesehen["fragen"] >= 7 and gesehen["fragen_danach"] == ["Wie sollen die Ecken verbunden werden?"] * 3
neu = [x for x in db.positionen(a) if x["id"] not in vorher]
assert name_g == "Geländer 2000×1000"
assert sorted((x["bezeichnung"][len(name_g) + 1:], x["je_satz"], x["laenge"]) for x in neu) == [
    ("Endpfosten", 2, 920.0), ("Handlauf", 1, 2000.0), ("Untergurt", 1, 2000.0), ("Zwischenpfosten", 2, 920.0)], neu
hl = next(x for x in neu if x["bezeichnung"].endswith("Handlauf"))
k = json.loads(hl["technik"])["konturen"]
assert k[0]["art"] == "Bohrung" and k[0]["seite"] == "oben" and k[0]["anzahl"] == 2 and hl["einstiche"] > \
    next(x for x in neu if x["bezeichnung"].endswith("Untergurt"))["einstiche"], (k, hl)
assert seite.satz_3d(satz=name_g, dialog=satz_ansehen) and gesehen["koerper"] == 6, gesehen
gen = db.satz_daten(a)[name_g]["generator"]
assert gen["verlauf"] == [GEL, "4 Pfosten einschließlich Endpfosten", "Bohrungen von oben"], gen
ok("Angebot: Geländer mit Rückfragen per Knopf (Antwort kommt in den Verlauf), Bohrungen im Handlauf als Kontur mit "
   "Einstichen, Beschreibung bleibt nach Satz in 3D erhalten")

zeile = next(r for r, x in enumerate(seite.positionen) if x.get("satz") == name_g)
seite.pos_ansicht.selectRow(zeile)
seite._pos_menue_anpassen()
assert seite.pos_aktionen["Satz per Text ändern …"].isVisible()
zeile = next(r for r, x in enumerate(seite.positionen) if x.get("satz") == satz)
seite.pos_ansicht.clearSelection()
seite.pos_ansicht.selectRow(zeile)
seite._pos_menue_anpassen()
assert seite.pos_aktionen["Satz per Text ändern …"].isVisible()      # Rahmen von oben stammt auch aus dem Generator


def laenger(d):
    gesehen["wieder"] = [d.verlauf_liste.item(i).text() for i in range(d.verlauf_liste.count())]
    gesehen["name"] = d.name.text()
    gesehen["saetze_feld"] = d.saetze.value()
    d.aendern("Länge 2500")
    d.saetze.setValue(2)
    d._ok()
    return d.result()


anzahl_vorher = len(db.positionen(a))
alt_ids = {x["id"] for x in db.positionen(a) if x.get("satz") == name_g}
assert seite.bauteil_aus_text(satz=name_g, dialog=laenger) == name_g
assert gesehen["wieder"][0] == "Beschreibung: " + GEL and len(gesehen["wieder"]) == 3 and gesehen["name"] == name_g \
    and gesehen["saetze_feld"] == 1, gesehen
jetzt = [x for x in db.positionen(a) if x.get("satz") == name_g]
assert not alt_ids & {x["id"] for x in jetzt} and len(db.positionen(a)) == anzahl_vorher
assert sorted(x["laenge"] for x in jetzt if x["bezeichnung"].endswith(("Handlauf", "Untergurt"))) == [2500.0, 2500.0]
assert all(x["stueck"] == 2 * x["je_satz"] for x in jetzt)
assert db.satz_daten(a)[name_g]["generator"]["verlauf"][-1] == "Länge 2500"
seite.rueckgaengig()
assert {x["id"] for x in db.positionen(a) if x.get("satz") == name_g} == alt_ids
assert seite.bauteil_aus_text(satz="gibt es nicht") is None
ok("Satz per Text ändern: Menüeintrag nur bei Generator-Sätzen, Verlauf/Name/Sätze wieder da, neue Länge ersetzt die "
   "alten Positionen, Rückgängig holt sie zurück, fremder Satz wird abgelehnt")
db.schliessen()
print("Bauteil aus Text: alle Tests bestanden.")
