"""Leerwege wie der Laserkopf fährt (Phase 5, Patrick 16.11.2026: „Die Schneidwege so berechnen wie der Laserkopf
fahren würde: bei einer Drehung Kopf um das Material heben, bei längeren Wegen Kopf heben“; dynamik.leerweg_art):
- kurzer Weg (unter „Kopf heben ab Weg“): Kopf bleibt unten, max(Verfahren, Drehen) + Einschwingen
- langer Weg: Froschsprung max(Verfahren, Drehen, Heben + Senken), ohne Froschsprung nacheinander
- Drehen über die Kante (Kasten-/offene Profile): heben bis Ecke + Sicherheit, drehen, senken; Rundrohr ohne Hub
- im Angebot ersetzt der Kopfweg den pauschalen Kopfhub je Einstich; ohne Feld bleibt alles wie bisher
- vorbelegt in neuen und (einmal, Merker richtwerte_kopfweg) in vorhandenen Datendateien

Aufruf: python tests/test_kopfweg.py
"""
import json
import math
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
from rohrlaser import dynamik as dy, rechnen, zeit_zusatz as zz  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import KOPFWEG_FELDER  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) <= eps * max(1.0, abs(a), abs(b)), f"{text}: {a} != {b}"


M = dict(eilgang_x=60, beschl_x=10, drehzahl=60, beschl_dreh=720, hub_z=3, eilgang_z=60, beschl_z=10,
         zeit_regelung=0.05, hub_ab_weg=20, hub_sicherheit=5, froschsprung="ja")
QR = dict(form="Quadratrohr", a=60, b=60, wand=3, r_aussen=6)
v, a = 1.0, 10.0
hub = dy.bewegung(0.003, 1.0, 10.0)

# kurz: Kopf bleibt unten
k = dy.leerweg_art((0, 0), (10, 0), M, QR)
assert k["hub"] == "kein" and k["hoehe_mm"] == 0
nah(k["t_s"], dy.bewegung(0.01, v, a) + 0.05)
# lang: Froschsprung – Heben überlappt mit dem Verfahren
lg = dy.leerweg_art((0, 0), (500, 0), M, QR)
assert lg["hub"] == "sprung" and lg["hoehe_mm"] == 3
nah(lg["t_s"], max(dy.bewegung(0.5, v, a), 2 * hub) + 0.05)
lg2 = dy.leerweg_art((0, 0), (500, 0), dict(M, froschsprung="nein"), QR)
nah(lg2["t_s"], 2 * hub + dy.bewegung(0.5, v, a) + 0.05)
assert lg2["t_s"] > lg["t_s"]
ok("kurzer Weg ohne Hub, langer Weg mit Froschsprung (ohne: heben, fahren, senken nacheinander)")

# Drehen über die Kante: Höhe = Eckradius – halbe Seite + Sicherheit
eck = math.hypot(30 - 6, 30 - 6) + 6
nah(dy.eck_radius(QR), eck)
d = dy.leerweg_art((0, 0), (0, 90), M, QR)
assert d["hub"] == "drehen"
nah(d["hoehe_mm"], eck - 30 + 5)
th = dy.bewegung((eck - 30 + 5) / 1000, 1.0, 10.0)
nah(d["t_s"], th + dy.bewegung(90, 360, 720) + th + 0.05)
assert dy.leerweg_art((0, 0), (0, 90), dict(M, hub_sicherheit=0), QR)["hoehe_mm"] < d["hoehe_mm"]
# Rechteckrohr: Zielfläche weiter weg -> anders senken
rq = dict(form="Rechteckrohr", a=100, b=40, wand=3, r_aussen=4)
r = dy.leerweg_art((0, 0), (0, 90), M, rq)
nah(r["hoehe_mm"], dy.eck_radius(rq) - 50 + 5)
# Rundrohr dreht ohne Hub (kurzer Weg) bzw. Froschsprung (langer Bogen)
rund = dict(form="Rundrohr", a=20, wand=2)
assert dy.eck_radius(rund) is None
assert dy.leerweg_art((0, 0), (0, 90), M, rund)["hub"] == "kein"           # Bogen 15,7 mm < 20 mm
assert dy.leerweg_art((0, 0), (0, 180), M, dict(rund, a=100))["hub"] == "sprung"
# große Ecke: mindestens Kopfhub
klein = dict(form="Quadratrohr", a=10, b=10, wand=1, r_aussen=4)
assert dy.leerweg_art((0, 0), (0, 90), dict(M, hub_sicherheit=0), klein)["hoehe_mm"] == 3
nah(dy.leerweg_s((0, 0), (0, 90), M, QR), d["t_s"])
ok(f"Drehen über die Kante: Quadratrohr 60 heben {d['hoehe_mm']:.1f} mm, {d['t_s']:.2f} s; Rundrohr ohne Hub")

# ohne Kopfweg-Feld: wie bisher
alt = dict(M, hub_ab_weg=None)
assert not dy.kopfweg_aktiv(alt) and dy.kopfweg_aktiv(M) and not dy.kopfweg_aktiv(dict(M, hub_z=None))
lagen = [dict(x=100, eingabe=dict(seite="oben")), dict(x=600, eingabe=dict(seite="unten"))]
nah(dy.verfahrzeit(alt, lagen, 1000, QR), dy.verfahrzeit(alt, lagen, 1000))
mit = dy.verfahrzeit(M, lagen, 1000, QR)
pkt = [(0.0, None), (100.0, 0.0), (600.0, 180.0), (1000.0, None)]
nah(mit, sum(dy.leerweg_s(p, q, M, QR) for p, q in zip(pkt, pkt[1:])))
assert dy.leerweg_s((0, 0), (0, 0), {}, QR) is None
ok("ohne „Kopf heben ab Weg“ rechnet alles wie bisher; mit: Summe der Leerwege einzeln")


# Angebot: Kopfweg ersetzt den pauschalen Hub je Einstich
def technik(*konturen):
    return json.dumps(dict(quelle="Schneidweg-Rechner", konturen=list(konturen)))


def zeile(db, extra=None):
    for x in db.zeilen("maschinen"):
        for n_, w in (extra or {}).items():
            db.aendern("maschinen", x["id"], n_, w)
    an = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
    db.position_neu(an, dict(pos=10, artikel="Q1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1200,
                             stueck=10, schneidweg=900, einstiche=6, technik=technik(
                                 dict(art="Bohrung", d=12, anzahl=4, abstand=30, x=300, seite="oben"),
                                 dict(art="Bohrung", d=12, anzahl=1, x=600, seite="unten"),
                                 dict(art="Rechteck", b=150, h=30, anzahl=1, x=900, seite="vorne"))))
    kopf, pos = db.angebot(an), db.positionen(an)
    k, tab = db.kontext(), db.tabellen()
    erg = rechnen.optimieren(kopf, pos, k, tab, db.einstellungen())
    zl, _ = rechnen.kalkulation(kopf, pos, erg, k, tab, rechnen.einstellungen_angebot(kopf, db.einstellungen()))
    return zl[0], k


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "neu.db")
t11 = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
assert (t11["hub_ab_weg"], t11["hub_sicherheit"], t11["froschsprung"]) == (20, 5, "ja")
z_neu, k = zeile(db)
z_alt, _ = zeile(Datenbank(tmp / "alt.db"), dict(hub_ab_weg=None))
m = k.maschinen["T11"]
pr = k.profile["QR 40x40x3"]
p = dict(laenge=1200, technik=technik(dict(art="Bohrung", d=12, anzahl=4, abstand=30, x=300, seite="oben"),
                                      dict(art="Bohrung", d=12, anzahl=1, x=600, seite="unten"),
                                      dict(art="Rechteck", b=150, h=30, anzahl=1, x=900, seite="vorne")))
erwartet = dy.verfahrzeit(m, zz._lagen(p), 1200, pr)
nah(z_neu["zeit_anfahren"], erwartet, "Anfahren mit Kopfweg")
alt_erw = dy.verfahrzeit(m, zz._lagen(p), 1200) + zz.hub_s(m) * 6
nah(z_alt["zeit_anfahren"], alt_erw, "Anfahren ohne Kopfweg")
ok(f"Angebot QR 40×40: Leerwege mit Kopfweg {z_neu['zeit_anfahren']:.2f} s statt {z_alt['zeit_anfahren']:.2f} s "
   "(pauschaler Hub je Einstich)")

# vorhandene Datendatei: einmal vorbelegt, danach geleert bleibt leer
pfad = tmp / "update.db"
d2 = Datenbank(pfad)
d2.con.close()
con = sqlite3.connect(pfad)
con.execute("DELETE FROM einstellungen WHERE name = 'richtwerte_kopfweg'")
con.execute("UPDATE maschinen SET hub_ab_weg = NULL, hub_sicherheit = NULL, froschsprung = NULL")
con.execute("UPDATE maschinen SET hub_ab_weg = 50 WHERE maschinen_id = 'LT7'")
con.commit()
con.close()
d2 = Datenbank(pfad)
werte = {z["maschinen_id"]: tuple(z[f] for f in KOPFWEG_FELDER) for z in d2.zeilen("maschinen")}
assert werte["T11"] == (20, 5, "ja") and werte["LT7"] == (50, 5, "ja"), werte
for z in d2.zeilen("maschinen"):
    d2.aendern("maschinen", z["id"], "hub_ab_weg", None)
d2.con.close()
d2 = Datenbank(pfad)
assert all(z["hub_ab_weg"] is None for z in d2.zeilen("maschinen"))
ok("Update: Richtwerte einmal in leere Felder, eigene Werte bleiben, danach geleert bleibt leer")
print("Kopfweg: alle Tests bestanden.")
