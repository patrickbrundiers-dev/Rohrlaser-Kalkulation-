"""Prüft die 3D-Schnittbearbeitung (Patrick 22.10.2026, Plan kalkulation/3d-schnitt, Freigabe 19:12):
- D1 zentrale Winkelbegrenzung: +60 -> +45, −55 -> −45, ±30 bleibt, NaN/∞/Text abgefangen, Maschinengrenzen
- D2 Gesamtneigung aus Längs- und Querneigung, Begrenzung skaliert beide Anteile, Gehrung 3D (kleinere Grenze)
- D3 Geometrie: wirksame Dicke, schräge Bohrung (Ellipse, Austritt), Achsdefinition
- D4 Greifmaß des letzten Teils (Funktion): Gehrung 3D an Ende B volles Greifmaß, Bohrung nach Abstand, nie Summe
- D5 Kalkulation: 2D unverändert, 3D bei 0°, +30°, −30°, ±45° (Schneiddaten der wirksamen Dicke), Faktor und
  Zusatzzeit, Maschine ohne 3D = FEHLER, Begrenzung = WARNUNG, Schema 39

Aufruf: python tests/test_3d.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import dreid, rechnen  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

EPS = 1e-6
M3D = dict(maschinen_id="T11", d3="ja", schwenk_min=-45, schwenk_max=45, greif_3d=300, zeit_3d=0, faktor_3d=1.0)


def ok(text):
    print("OK    ", text)


def nah(a, b, tol=EPS):
    return abs(a - b) <= tol


def fehler(fn, *a):
    try:
        fn(*a)
    except ValueError:
        return True
    return False


# ------------------------------------------------------------------ D1 Begrenzung
for ein, aus in ((60, 45), (50, 45), (45, 45), (30, 30), (0, 0), (-30, -30), (-45, -45), (-55, -45), (-60, -45)):
    v, h = dreid.begrenzen(ein, M3D)
    assert v == aus and (h is None) == (ein == aus), (ein, v, h)
assert dreid.begrenzen(60)[1] == "Winkel wurde auf maximal 45° begrenzt."
assert dreid.begrenzen("+30°")[0] == 30 and dreid.begrenzen("−45")[0] == -45 and dreid.begrenzen("12,5")[0] == 12.5
assert dreid.begrenzen("")[0] == 0 and dreid.begrenzen(None)[0] == 0
for x in (float("nan"), float("inf"), float("-inf"), "abc", True):
    assert fehler(dreid.begrenzen, x), x
eng = dict(M3D, schwenk_min=-30, schwenk_max=40)
assert dreid.begrenzen(45, eng)[0] == 40 and dreid.begrenzen(-45, eng)[0] == -30
assert dreid.grenzen({}) == (-45, 45) and dreid.grenzen(dict(schwenk_min=5, schwenk_max=-5)) == (0, 0)
ok("D1 Begrenzung +60→+45, −55→−45, ±30 bleibt; NaN, ∞, Text abgefangen; Grenzen der Maschine haben Vorrang")

# ------------------------------------------------------------------ D2 Neigung und Gehrung
assert nah(dreid.gesamtwinkel(30, 0), 30) and nah(dreid.gesamtwinkel(0, -30), 30)
g = dreid.gesamtwinkel(30, 30)
assert nah(math.tan(math.radians(g)) ** 2, 2 * math.tan(math.radians(30)) ** 2)
l_, q_, ges, h = dreid.neigung_begrenzen(40, 40, M3D)       # gesamt ≈ 49,9° -> 45°, Richtung bleibt
assert nah(ges, 45) and nah(dreid.gesamtwinkel(l_, q_), 45, 1e-9) and nah(l_, q_) and h
l_, q_, ges, h = dreid.neigung_begrenzen(-60, 0, M3D)
assert nah(l_, -45) and q_ == 0 and h
assert dreid.neigung_begrenzen(-30, 20, M3D)[3] is None
assert nah(dreid.neigung_begrenzen(-40, 0, eng)[0], -30)         # längs negativ: Grenze min der Maschine
assert fehler(dreid.neigung_begrenzen, 95, 0) and fehler(dreid.neigung_begrenzen, "x", 0)
assert dreid.gehrung_begrenzen(-30, M3D) == (30, None)
assert dreid.gehrung_begrenzen(60, M3D)[0] == 45 and dreid.gehrung_begrenzen(35, eng)[0] == 30
ok(f"D2 Gesamtneigung (30/30 → {g:.2f}°), 40/40 auf 45° skaliert, Gehrung 3D mit der kleineren Grenze")

# ------------------------------------------------------------------ D3 Geometrie
assert nah(dreid.wirksame_dicke(3, 0), 3) and nah(dreid.wirksame_dicke(3, -30), 3 / math.cos(math.radians(30)))
assert nah(dreid.wirksame_dicke(3, 45), 3 * math.sqrt(2))
assert nah(dreid.bohrung_laenge(10, 0), math.pi * 10, 1e-9)
assert nah(dreid.bohrung_laenge(10, 30), dreid.ellipse(5, 5 / math.cos(math.radians(30))))
assert nah(dreid.bohrung_laenge(10, 30), 33.890, 1e-3), dreid.bohrung_laenge(10, 30)
assert nah(dreid.bohrung_laenge(10, -30), dreid.bohrung_laenge(10, 30))
assert nah(dreid.bohrung_huelle(10, 30), 11.547, 1e-3)
dx, dq = dreid.austritt(5, 30, 0)
assert nah(dx, 2.887, 1e-3) and dq == 0                        # + = Richtung Ende B
assert dreid.austritt(5, -30, 0)[0] < 0 and dreid.austritt(5, 0, 30)[1] > 0
ok("D3 Wand/cos: 30° → 1,155×, 45° → 1,414×; Bohrung Ø10 / 30° = 33,89 mm (Ellipse), Austritt 2,89 mm Richtung B")


# ------------------------------------------------------------------ D4 Greifmaß des letzten Teils
def teil(laenge=1000, a=None, b=None, konturen=(), an=True):
    t = dict(d3=an, a=a or {}, b=b or {}, konturen=list(konturen))
    return dict(laenge=laenge, a_schnitt=160, b_schnitt=180, technik=json.dumps(t))


ohne = teil(an=False, b=dict(winkel=30, d3=True))
assert dreid.rest_letztes(ohne, M3D) == 0 and dreid.bearbeitungen(ohne, M3D) == []
gb = teil(b=dict(winkel=30, d3=True))
assert dreid.rest_letztes(gb, M3D) == 300
assert dreid.rest_letztes(teil(b=dict(winkel=30, d3=True)), dict(M3D, greif_3d=None)) == 300   # Vorgabe
assert dreid.rest_letztes(teil(b=dict(winkel=30)), M3D) == 0         # Gehrung ohne 3D: kein Sonderfall
assert dreid.rest_letztes(teil(laenge=200, a=dict(winkel=30, d3=True)), M3D) == 100   # Ende A, Teil 200 lang
assert dreid.rest_letztes(teil(laenge=1000, a=dict(winkel=30, d3=True)), M3D) == 0
bo = dict(art="Bohrung", d=10, anzahl=2, x=700, abstand=100, d3=True, neigung_l=30)
assert nah(dreid.rest_letztes(teil(konturen=[bo]), M3D), 300 - (1000 - 800 - 5))        # letzte Bohrung bei 800
assert dreid.rest_letztes(teil(konturen=[dict(bo, x=100, anzahl=1)]), M3D) == 0
assert dreid.rest_letztes(teil(konturen=[dict(bo, x=None)]), M3D) == 300              # Lage unbekannt
assert dreid.rest_letztes(gb, dict(M3D, d3="nein")) == 0
# keine doppelte Berücksichtigung: der Rest ist eine Forderung, die Optimierung nimmt max(Greiferrest, Rest)
assert max(142, dreid.rest_letztes(gb, M3D)) == 300 and max(400, dreid.rest_letztes(gb, M3D)) == 400
ok("D4 Greifmaß: Gehrung 3D an Ende B 300 mm, Ende A 300 − Länge, Bohrung 300 − Abstand, ohne 3D 0, nie Summe")

# ------------------------------------------------------------------ D5 Kalkulation
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
k = db.kontext()
for m in ("T03", "T11", "LT7"):
    z = k.maschinen[m]
    assert (z["d3"], z["schwenk_min"], z["schwenk_max"], z["greif_3d"], z["zeit_3d"], z["faktor_3d"]) == \
        ("nein", -45, 45, 300, 0, 1.0), z
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
TECHNIK0 = dict(quelle="Schneidweg-Rechner", a={}, b=dict(winkel=30, richtung=0), konturen=[])
db.position_neu(a, dict(pos=10, artikel="G1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=900,
                        stueck=40, schneidweg=340, einstiche=2, a_schnitt=160, b_schnitt=180, a_gerade="ja",
                        b_gerade="nein", technik=json.dumps(TECHNIK0)))
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
pid = s.positionen[0]["id"]
mid = next(z["id"] for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")


def rechnung():
    s.neu_laden()
    z, su = rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)
    st = rechnen.status(s.positionen[0], rechnen.position_werte(s.positionen[0], s.kopf, s.k, s.tabellen),
                        s.kopf, s.k)
    return z[0], su, st


def technik(**kw):
    t = json.loads(json.dumps(TECHNIK0))
    t.update(kw)
    db.position_aendern(pid, "technik", json.dumps(t))


z0, su0, st0 = rechnung()
assert z0["zeit_d3"] == 0 and z0["zeit_3d_gesamt"] is None and st0 == "OK", (z0["zeit_d3"], st0)
technik(d3=False, b=dict(winkel=30, richtung=0, d3=True))      # Bauteil ohne Häkchen: Bearbeitung zählt nicht
z1, su1, st1 = rechnung()
assert z1["laser_brutto"] == z0["laser_brutto"] and su1["verkauf"] == su0["verkauf"] and st1 == "OK"
ok(f"D5 2D ohne Häkchen unverändert (Laser brutto {z0['laser_brutto']:.2f} s, VK {su0['verkauf']:.2f} €)")

technik(d3=True, b=dict(winkel=30, richtung=0, d3=True))
z2, su2, st2 = rechnung()
assert st2 == "FEHLER: Maschine T11 kann keine 3D-Bearbeitung", st2
assert z2["zeit_d3"] == 0 and z2["zeit_3d_gesamt"] is None
assert z2["hinweis"] == "Maschine T11 kann keine 3D-Bearbeitung", z2["hinweis"]
ok("D5 Maschine ohne 3D: FEHLER, keine 3D-Zeit (nicht stillschweigend 2D)")

db.aendern("maschinen", mid, "d3", "ja")
tab = s.tabellen


def vorschub(dicke):
    return rechnen.schneiddaten("T11", "S235-10219", dicke, tab, "Stahl")


v3, v_alt = vorschub(3), vorschub(3)
ergebnisse = {}
for winkel in (0, 30, -30, 45, -45):
    technik(d3=True, b=dict(winkel=winkel, richtung=0, d3=True))
    z, su, st = rechnung()
    w = abs(winkel)
    if w == 0:
        assert st.startswith("FEHLER: Gehrung 3D Ende B"), st
        continue
    sd = vorschub(3 / math.cos(math.radians(w)))
    soll = 60 * 180 / sd["vorschub_gross"] + sd["einstechzeit"]
    ref = 60 * 180 / v3["vorschub_gross"] + v3["einstechzeit"]
    assert nah(z["zeit_3d_gesamt"], soll) and nah(z["zeit_d3"], soll - ref), (winkel, z["zeit_3d_gesamt"], soll)
    assert nah(z["laser_brutto"], z0["laser_brutto"] + soll - ref) and st == "OK", (winkel, st)
    assert z["mm_3d"] == 180 and z["bearbeitungen_3d"] == 1
    assert nah(sum(z[f"zeit_{n}"] for n in rechnen.ZEITANTEILE), z["laser_brutto"])
    ergebnisse[winkel] = (z["zeit_3d_gesamt"], su["verkauf"])
assert ergebnisse[30] == ergebnisse[-30] and ergebnisse[45] == ergebnisse[-45]
assert ergebnisse[45][0] > ergebnisse[30][0] > 0 and ergebnisse[45][1] > ergebnisse[30][1] > su0["verkauf"]
ok("D5 Gehrung 3D +30/−30 gleich (Schneiddaten 3,46 mm), ±45 (4,24 mm) länger, Summe der Anteile = Laser brutto; "
   "Gehrung 3D ohne Winkel = FEHLER")

# 3D-Bohrung bei 0°: Weg gleich, Schneiddaten gleich -> keine Mehrzeit; Faktor und Zusatzzeit
technik(d3=True, konturen=[dict(art="Bohrung", d=10, anzahl=1, x=450, d3=True, neigung_l=0, neigung_q=0)])
z, su, st = rechnung()
assert st == "OK" and nah(z["zeit_d3"], 0) and z["zeit_3d_gesamt"] > 0, (st, z["zeit_d3"])
db.aendern("maschinen", mid, "zeit_3d", 5)
db.aendern("maschinen", mid, "faktor_3d", 1.5)
z, su, st = rechnung()
basis = z["zeit_3d_gesamt"] - 5
assert nah(z["zeit_d3"], basis + 5 - basis / 1.5), (z["zeit_d3"], basis)
ok("D5 Bohrung 3D bei 0°: keine Mehrzeit; Faktor 1,5 und Zusatzzeit 5 s je Bearbeitung")

# Begrenzung: Eingabe +60° -> WARNUNG, gerechnet mit 45° (gleich wie Eingabe 45°)
db.aendern("maschinen", mid, "zeit_3d", 0)
db.aendern("maschinen", mid, "faktor_3d", 1.0)
technik(d3=True, b=dict(winkel=60, richtung=0, d3=True))
z60, _, st60 = rechnung()
assert st60 == "WARNUNG: 3D-Winkel begrenzt, Kontur nicht maßhaltig", st60
assert nah(z60["zeit_3d_gesamt"], ergebnisse[45][0])
db.aendern("maschinen", mid, "schwenk_max", 30)                # Maschine: Gehrung 3D höchstens 30°
z30, _, _ = rechnung()
assert nah(z30["zeit_3d_gesamt"], ergebnisse[30][0])
db.aendern("maschinen", mid, "schwenk_max", 45)
technik(d3=True, b=dict(winkel="abc", richtung=0, d3=True))
assert rechnung()[2].startswith("FEHLER: Gehrung 3D Ende B: Winkel"), rechnung()[2]
ok("D5 Eingabe 60° → 45° mit WARNUNG, Maschine mit max. 30° rechnet 30°, ungültiger Winkel = FEHLER")

# keine Schneiddaten für die 3D-Dicke: WARNUNG statt stiller 2D-Zeit (Schneiddaten nur bis 4 mm)
technik(d3=True, b=dict(winkel=45, richtung=0, d3=True))
s.neu_laden()
p0 = s.positionen[0]
bis4 = dict(s.tabellen, schneiddaten=[z_ for z_ in s.tabellen["schneiddaten"] if z_["wand_bis"] <= 4])
d3 = rechnen.zeit_3d(p0, s.kopf, 3.0, bis4, s.k, (5800, 3480, 1740, 3000, 0.3))
assert d3["fehlt"] == "keine Schneiddaten für 3D (Dicke 4,2 mm)" and d3["mehr"] == 0, d3
w_ = rechnen.position_werte(p0, s.kopf, s.k, bis4)
assert w_["fehlt_3d"] == d3["fehlt"]
assert rechnen.status(p0, w_, s.kopf, s.k) == "WARNUNG: " + d3["fehlt"]
ok(f"D5 {d3['fehlt']}: WARNUNG, keine Mehrzeit geraten")

# Schema 39
pfad = tmp / "alt" / "rohrlaser.db"
Datenbank(pfad).schliessen()
con = sqlite3.connect(pfad)
con.execute("UPDATE maschinen SET d3=NULL, schwenk_min=NULL, schwenk_max=NULL, greif_3d=NULL, zeit_3d=NULL, "
            "faktor_3d=NULL")
con.execute("PRAGMA user_version=38")
con.commit()
con.close()
d = Datenbank(pfad)
werte = {(z["d3"], z["schwenk_min"], z["schwenk_max"], z["greif_3d"], z["zeit_3d"], z["faktor_3d"])
         for z in d.zeilen("maschinen")}
assert werte == {("nein", -45, 45, 300, 0, 1.0)}, werte
assert d.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION >= 39
d.schliessen()
ok("D5 Schema 39: vorhandene Maschinen ohne 3D, ±45°, Greifmaß 300 mm, 0 s, Faktor 1")
print("Alle 3D-Tests bestanden.")
