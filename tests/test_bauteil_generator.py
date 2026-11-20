"""Bauteil aus Text (bauteil_generator.py, Wettbewerbsanalyse 247TailorSteel 20.11.2026, „Parts Builder“ lokal):
- lesen: Beispielsatz aus dem Auftrag, Gestell mit eigenem Strebenprofil, Rundrohr in m, Blechteile (Lasche, L-Winkel,
  Flanschring); nicht zugeordnete Zahlen erscheinen als „nicht verstanden“
- bauen: Rahmen + Querstreben (senkrecht, waagrecht, Bodenstreben) mit Stößen und richtigen Längen, Platten mit
  Lochbild und Lage, Annahmen gekennzeichnet, Fehler (Profil fehlt, zu lang, Platte zu klein, Rundrohr/Vierkant)
- aendern: nur Genanntes ändert sich, „ohne …“, Verlauf im Fenster mit Zurücknehmen
- im Angebot: Neue Position → Bauteil aus Text legt Satz (Rohre mit Schneidweg, Netz, Stöße) und Platten (Blech im
  Satz) an, Satz in 3D zeigt alle Rohre; Blechteil allein wird eine Position; fehlendes Profil wird gemeldet

Aufruf: python tests/test_bauteil_generator.py
"""
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
db.schliessen()
print("Bauteil aus Text: alle Tests bestanden.")
