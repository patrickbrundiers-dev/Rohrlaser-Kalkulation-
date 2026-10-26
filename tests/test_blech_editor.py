"""Prüft den Blech-Editor (Richtpreis für Blech- und Kantteile, Patrick 22.10.2026):
- B1 Abwicklung: Ausgleichswert je Biegung (90° wie Tabelle, stumpf/spitz), Lage der Biegelinien, Zuschnitt
  Rechteck mit Eckradius und Polygon, Prüfung unmöglicher Maße.
- B2 Richtpreis: Material (Hüllrechteck mit Verschnitt), Laser (Vorschub je Kategorie und Dicke, N₂ vor O₂,
  Innenkonturen, Einstiche), Kanten, Rüsten je Stück, Aufschlag; fehlende Richtwerte als Fehler.
- B3 Daten getrennt: eigene Tabellen und Einstellungen; Rohrlaser-Werkstoffe und -Schneiddaten bleiben unverändert;
  ältere Datei (Schema 36) bekommt die Blech-Tabellen.
- B4 Angebot: Neue Position → Blech / Kantteil legt Zukaufartikel (Blechteile, Artikeltyp Blech, Richtpreis als EK)
  und Position an; erneut öffnen trägt den neuen Richtpreis ab Stückzahl ein.
- B6 Kantteil aus dem STEP-Import (Patrick 23.10.2026): Kantteil mit Polygon-Außenkontur (Fläche, Schnittlänge,
  Hinweis bei unpassender Kontur), mehrachsig gekanteter Zuschnitt mit gezählten Kantungen (Kosten Kanten),
  Editor mit 3D-Ansicht (gefaltet, Blickrichtung bleibt beim Tippen), Biegelinien bleiben gespeichert;
  Profil/Kantteil im Prüfdialog: Profil nur, wenn es in den Stammdaten steht.
- B5 Staffelstufe: andere Stückzahl -> Richtpreis für die Stückzahl der Stufe neu, EK aus dem Einkauf (ab ≤ Stückzahl)
  geht vor; gleiche Stückzahl wie im Angebot = gleicher Preis.

Aufruf: python tests/test_blech_editor.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from rohrlaser import blech, schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.neue_position import BLECH  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.01):
    return abs(a - b) <= tol


# ------------------------------------------------------------------ B1 Abwicklung
assert nah(blech.ausgleich(90, 2, 2), 2 * 4 - math.pi / 2 * (2 + 0.33 * 2))          # 3,82 mm
assert nah(blech.ausgleich(45, 2, 2), 2 * 4 * math.tan(math.radians(22.5)) - math.pi / 4 * 2.66)
assert nah(blech.ausgleich(-90, 2, 2), blech.ausgleich(90, 2, 2)) and blech.ausgleich(0, 2, 2) == 0
assert nah(blech.ausgleich(120, 2, 2), 8 - math.pi * 120 / 180 * 2.66)
winkel = dict(art=blech.KANTTEIL, dicke=2, kantlaenge=300, schenkel=[dict(laenge=50, winkel=90), dict(laenge=80)])
bg, lg = blech.biegungen(winkel)
assert nah(lg, 130 - 3.8217) and len(bg) == 1 and nah(bg[0][0], 50 - 3.8217 / 2) and bg[0][2] == 2
u = dict(winkel, schenkel=[dict(laenge=30, winkel=90, radius=4), dict(laenge=60, winkel=-90), dict(laenge=30)])
zs = blech.zuschnitt(u)
assert len(zs["biegungen"]) == 2 and nah(zs["breite"], 120 - blech.ausgleich(90, 4, 2) - blech.ausgleich(90, 2, 2))
assert zs["laenge"] == 300 and nah(zs["aussen"], 2 * (300 + zs["breite"]))
q = blech.querschnitt(u)[-1]
assert nah(q[0], 60) and nah(q[1], 60)                                       # Z: rechts, hoch, rechts
r = blech.zuschnitt(dict(dicke=3, laenge=200, breite=100, eckradius=10))
assert nah(r["aussen"], 600 - 80 + 20 * math.pi) and nah(r["flaeche"], 20000 - (4 - math.pi) * 100)
p = blech.zuschnitt(dict(dicke=3, form=blech.POLYGON, punkte="0,0; 200,0; 200,100; 0,100"))
assert (p["laenge"], p["breite"], p["flaeche"], p["aussen"]) == (200, 100, 20000, 600)
for falsch in (dict(dicke=3, laenge=0, breite=100), dict(dicke=3, laenge=50, breite=50, eckradius=30),
               dict(winkel, kantlaenge=0), dict(winkel, schenkel=[dict(laenge=50)]),
               dict(winkel, schenkel=[dict(laenge=3, winkel=90), dict(laenge=80)]),
               dict(winkel, schenkel=[dict(laenge=50, winkel=170), dict(laenge=80)])):
    try:
        blech.zuschnitt(falsch)
        raise AssertionError(falsch)
    except ValueError:
        pass
ok("B1 Abwicklung: Ausgleich je Biegung (90° = 3,82 mm bei 2 mm/r2), Biegelinien, Rechteck/Polygon, falsche Maße")

# ------------------------------------------------------------------ B2 Richtpreis
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
werkstoffe = {z["blech_werkstoff_id"]: z for z in db.zeilen("blech_werkstoffe")}
laser = db.zeilen("blechlaser")
assert {"S235JR", "1.4301 2B", "AlMg3"} <= set(werkstoffe) and len(laser) == 33
assert blech.schneiddaten(laser, "Stahl", 3)["gas"] == "N₂" and blech.schneiddaten(laser, "Stahl", 8)["gas"] == "O₂"
assert blech.schneiddaten(laser, "Stahl", 2.5)["dicke_bis"] == 3 and blech.schneiddaten(laser, "Stahl", 25) is None
e = dict(werkstoff="S235JR", dicke=3, art=blech.ZUSCHNITT, laenge=200, breite=100, stueck=10,
         konturen=[dict(art=sw.BOHRUNG, anzahl=4, d=10)])
erg = blech.rechnen(e, werkstoffe, laser, dict(blech_material=blech.MATERIAL_AUS[1]))   # Tafel: test_blech_tafel
assert not erg["fehler"] and erg["einstiche"] == 5 and nah(erg["schneidweg"], 600 + 40 * math.pi)
assert nah(erg["gewicht"], (20000 - 4 * math.pi * 25) * 3 * 7.85 / 1e6, 1e-6)
assert nah(erg["gewicht_tafel"], 20000 * 1.15 * 3 * 7.85 / 1e6, 1e-6)
assert nah(erg["kosten"]["Material"], erg["gewicht_tafel"] * 1.10, 1e-6)
zeit = 600 / 10000 * 60 + 40 * math.pi / 5000 * 60 + 5 * 0.3
assert nah(erg["zeit"], zeit, 1e-6) and nah(erg["kosten"]["Laser"], zeit / 3600 * 120, 1e-6)
assert erg["kosten"]["Kanten"] == 0 and nah(erg["kosten"]["Rüsten"], 3.0)
assert erg["richtpreis"] == round(erg["summe"] * 1.15, 2)
ek = blech.rechnen(dict(e, art=blech.KANTTEIL, kantlaenge=200, schenkel=[dict(laenge=50, winkel=90),
                                                                           dict(laenge=60)]), werkstoffe, laser,
                   dict(blech_kantung=2.0, blech_aufschlag=0))
assert ek["kantungen"] == 1 and ek["kosten"]["Kanten"] == 2.0 and nah(ek["kosten"]["Rüsten"], (30 + 25) / 10)
assert ek["richtpreis"] == round(ek["summe"], 2)
assert blech.rechnen(dict(e, dicke=40), werkstoffe, laser)["fehler"]
assert blech.rechnen(dict(e, werkstoff=None), werkstoffe, laser)["fehler"]
assert blech.rechnen(dict(e, konturen=[dict(art=sw.BOHRUNG, anzahl=1)]), werkstoffe, laser)["fehler"]
assert blech.lesen(blech.speichern(e))["laenge"] == 200 and blech.lesen(sw.speichern(dict(a={}, b={}))) is None
ok("B2 Richtpreis: Material mit Verschnitt, Laser je Kategorie/Dicke (N₂ vor O₂), Kanten, Rüsten je Stück, Aufschlag")

# ------------------------------------------------------------------ B3 Daten getrennt, ältere Datei
rohr_vorher = (db.zeilen("werkstoffe"), db.zeilen("schneiddaten"))
db.schliessen()
alt = tmp / "alt.db"
shutil.copy(tmp / "rohrlaser.db", alt)
con = sqlite3.connect(alt)
con.execute("DROP TABLE blech_werkstoffe")
con.execute("DROP TABLE blechlaser")
con.execute("PRAGMA user_version=36")
con.commit()
con.close()
db2 = Datenbank(alt)
assert db2.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
assert len(db2.zeilen("blech_werkstoffe")) == len(werkstoffe) and len(db2.zeilen("blechlaser")) == 33
db2.schliessen()
db = Datenbank(tmp / "rohrlaser.db")
ok("B3 Ältere Datei (Schema 36) bekommt Blech-Werkstoffe und Blechlaser-Richtwerte")

# ------------------------------------------------------------------ B4 Angebot
app = QApplication.instance() or QApplication([])
a = db.angebot_neu(dict(kunde="Test", maschine="T03"))
fenster = Hauptfenster(db, stumm=True)
s = fenster.angebot_oeffnen(a)
gesehen = {}


def ausfuellen(d):
    d.werkstoff.setCurrentText("1.4301 2B")
    d.dicke.setValue(2)
    d._vorlage(d.vorlage.findText("U-Profil"))
    gesehen["art"] = d.art.currentText()
    d.kantlaenge.setValue(300)
    d.kontur_neu(dict(art=sw.LANGLOCH, anzahl=2, l=20, b=8.5))
    d.tabelle.setCurrentCell(0, 2)
    gesehen["kopf"] = d.tabelle.horizontalHeaderItem(2).text()
    d.stueck.setValue(20)
    gesehen["vorschlag"] = d.bezeichnung.placeholderText()
    gesehen["ok"] = d.ok_knopf.isEnabled()
    d.skizze.grab()
    return QDialog.Accepted


assert s.position_neu(BLECH, dialog=ausfuellen) == BLECH
p = db.positionen(a)[-1]
assert gesehen["art"] == blech.KANTTEIL and gesehen["ok"] and gesehen["kopf"].startswith("Länge")
assert gesehen["vorschlag"].startswith("Kantteil 300 × 112 × 2 1.4301 2B (2 Kantungen)")
assert p["art"] == "Zukaufteil" and p["stueck"] == 20 and p["bezeichnung"] == gesehen["vorschlag"]
eingabe = blech.lesen(p["technik"])
assert eingabe["werkstoff"] == "1.4301 2B" and len(eingabe["schenkel"]) == 3 and eingabe["konturen"][0]["l"] == 20
aid = json.loads(p["zukauf"])[0]["artikel_id"]
art = db.zukauf_artikel(aid)
richt = blech.rechnen(eingabe, werkstoffe, laser, {n: db.einstellung(n) for n in blech.EINSTELLUNGEN})["richtpreis"]
assert (art["kategorie"], art["artikeltyp"], art["herkunft"], art["dicke"]) == ("Blechteile", "Blech", blech.QUELLE, 2)
assert art["bezuege"][0]["lieferant"] == "Technik" and json.loads(art["bezuege"][0]["preise"])[0]["preis"] == richt
assert db.zeilen("werkstoffe") == rohr_vorher[0] and db.zeilen("schneiddaten") == rohr_vorher[1]
s.optimieren()
assert s.ergebnis is not None
# erneut öffnen (Rechtsklick „Blech-Editor …“ bzw. Doppelklick): dickeres Blech, neuer Preis ab Stückzahl
assert "Blech-Editor …" in [x.text() for x in s.pos_menue.actions()]
zeile = len(s.positionen) - 1
gesehen.clear()


def dicker(d):
    gesehen["dicke"] = d.dicke.value()
    gesehen["knopf"] = d.ok_knopf.text()
    d.dicke.setValue(3)
    return QDialog.Accepted


assert s.blech_bearbeiten(zeile, dialog=dicker)
assert gesehen == dict(dicke=2, knopf="Richtpreis übernehmen")
p = db.positionen(a)[-1]
preise = json.loads(db.zukauf_artikel(aid)["bezuege"][0]["preise"])
assert blech.lesen(p["technik"])["dicke"] == 3 and len(preise) == 2 and preise[1]["ab"] == 20
assert preise[1]["preis"] > richt and json.loads(p["zukauf"])[0]["stand"]["bezug"]["preise"][1]["ab"] == 20
ok("B4 Angebot: Blech / Kantteil legt Zukaufartikel mit Richtpreis und Position an, Rohrdaten unverändert, erneut "
   "öffnen trägt den neuen Preis ab Stückzahl ein")

# ------------------------------------------------------------------ B5 Staffelstufe
from rohrlaser import staffeln  # noqa: E402
daten = db.blech_daten()
p = db.positionen(a)[-1]
eingabe = blech.lesen(p["technik"])
assert [r["ab"] for r in eingabe["richtpreise"]] == [1, 20]            # gemerkte Richtpreise (nicht EK Einkauf)
assert staffeln.blech_stand(p, 20, daten) == (None, None)               # Stückzahl des Angebots: Preisstand bleibt
r100 = blech.rechnen(dict(eingabe, stueck=100), werkstoffe, laser, daten["einst"])["richtpreis"]
neu, text = staffeln.blech_stand(p, 100, daten)
assert neu[0]["stand"]["bezug"]["preise"] == [dict(ab=1, preis=r100)] and r100 < preise[1]["preis"]
assert text.startswith(f"Pos. {p['pos']} Blech: Richtpreis") and "100 St" in text
# Einkauf trägt einen echten EK ab 50 Stück ein (Preisstand der Position aktualisiert)
db.zukauf_ek_eintragen(aid, 5.0, "Technik", ab=50)
liste = json.loads(p["zukauf"])
liste[0]["stand"] = db.zukauf_stand(aid, "Technik")
db.position_aendern(p["id"], "zukauf", json.dumps(liste))
p = db.positionen(a)[-1]
neu, text = staffeln.blech_stand(p, 100, daten)
assert [(float(x["ab"]), x["preis"]) for x in neu[0]["stand"]["bezug"]["preise"]] == [(50.0, 5.0)]
assert text.endswith("EK Einkauf ab 50 St")
neu, text = staffeln.blech_stand(p, 30, daten)              # unter 50 Stück: kein EK, Richtpreis für 30 Stück
assert "Richtpreis" in text and neu[0]["stand"]["bezug"]["preise"][0]["preis"] == \
    blech.rechnen(dict(eingabe, stueck=30), werkstoffe, laser, daten["einst"])["richtpreis"]
# Richtpreis ersetzt Preiseinheit und Rabatt des Lieferanten; EK mit gleichem Preis wie ein Richtpreis bleibt EK
p2 = dict(p, zukauf=json.dumps([dict(liste[0], stand=dict(liste[0]["stand"], bezug=dict(
    liste[0]["stand"]["bezug"], preiseinheit=100, rabatt=10)))]))
bz = staffeln.blech_stand(p2, 30, daten)[0][0]["stand"]["bezug"]
assert bz["preiseinheit"] == 1 and not bz["rabatt"]
rp1 = eingabe["richtpreise"][0]["preis"]
db.zukauf_ek_eintragen(aid, rp1, "Technik", ab=80)
liste2 = json.loads(p["zukauf"])
liste2[0]["stand"] = db.zukauf_stand(aid, "Technik")
neu, text = staffeln.blech_stand(dict(p, zukauf=json.dumps(liste2)), 100, daten)
assert text.endswith("EK Einkauf ab 80 St") and (80.0, rp1) in [(float(x["ab"]), x["preis"])
                                                               for x in neu[0]["stand"]["bezug"]["preise"]]
# ganze Stufe: Angebot × 5 (100 St) nimmt den EK, × 1 ergibt den Angebotspreis
s.neu_laden()
s.optimieren()
st = s.st_seite
st.aus_angebot(1)
st.aus_angebot(5)
zeilen = st.rechnen()
assert len(zeilen) == 2 and not any(str(z.get("hinweis") or "").startswith("FEHLER") for z in zeilen), zeilen
gleich, gross = zeilen
assert gross["menge"] == 100 and "EK Einkauf ab 50 St" in gross["hinweis"]
assert nah(gross["bausteine"]["zukauf_einstand"], 100 * 5.0)
assert "Blech" not in (gleich.get("hinweis") or "")
from rohrlaser.staffel_seite import angebotspreise  # noqa: E402
ap = angebotspreise(s.positionen, s._rechnung()[0])
assert nah(gleich["preis_einheit"], ap[str(p["pos"])], 0.005), (gleich["preis_einheit"], ap)
ok("B5 Staffelstufe: Richtpreis für die Stückzahl der Stufe neu, EK aus dem Einkauf ab 50 St geht vor, "
   "Stückzahl des Angebots = Angebotspreis")
# ------------------------------------------------------------------ B6 Kantteil aus dem STEP-Import
from rohrlaser import blech3d, step  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
u = dict(werkstoff="S235JR", dicke=2, art=blech.KANTTEIL, kantlaenge=200, stueck=1,
         schenkel=[dict(laenge=30, winkel=90), dict(laenge=60, winkel=90), dict(laenge=30)])
zs = blech.zuschnitt(u)
br = zs["breite"]
poly = dict(u, form=blech.POLYGON, punkte=f"0,0; 200,0; 200,{br:.3f}; 20,{br:.3f}; 20,{br - 10:.3f}; 0,{br - 10:.3f}")
zp = blech.zuschnitt(poly)
assert nah(zp["flaeche"], 200 * br - 200, 0.5) and nah(zp["aussen"], 2 * (200 + br), 0.05) and not zp["hinweise"]
assert zp["biegungen"] == zs["biegungen"] and zp["laenge"] == 200
assert blech.zuschnitt(dict(poly, punkte="0,0; 150,0; 150,50; 0,50"))["hinweise"]
schale = dict(werkstoff="S235JR", dicke=2, art=blech.ZUSCHNITT, form=blech.RECHTECK, laenge=232.36, breite=182.36,
              stueck=10, kantungen=4, konturen=[],
              biegelinien=[dict(punkte=[[18.09, 16.18], [18.09, 166.18]], winkel=-90, ba=4.178),
                           dict(punkte=[[214.27, 16.18], [214.27, 166.18]], winkel=-90, ba=4.178),
                           dict(punkte=[[16.18, 18.09], [216.18, 18.09]], winkel=-90, ba=4.178),
                           dict(punkte=[[16.18, 164.27], [216.18, 164.27]], winkel=-90, ba=4.178)])
es = blech.rechnen(schale, werkstoffe, laser, dict(blech_kantung=2.0))
assert es["kantungen"] == 4 and es["kosten"]["Kanten"] == 8.0 and not es["fehler"]
assert blech.bezeichnung_vorschlag(schale, es["zuschnitt"]).endswith("(4 Kantungen)")
n = blech3d.netz(schale, es["zuschnitt"])
hoehe = max(n["p"][1::3]) - min(n["p"][1::3])         # Ränder 20 hoch (nach unten gekantet)
assert 19 <= hoehe <= 23 and len(n["l"]["B"]) == 4, hoehe
d = BlechDialog(None, db, schale)
d.resize(1300, 900)
d.show()
app.processEvents()
assert d.ansicht3d.ansicht.netz and d.kantungen.value() == 4 and d.ergebnis["kantungen"] == 4
d.ansicht3d.ansicht.gier = 1.0
d.dicke.setValue(3)
assert d.ansicht3d.ansicht.gier == 1.0 and d.eingaben()["biegelinien"] == schale["biegelinien"]
d.grab()
d.kantungen.setValue(0)
assert "biegelinien" not in d.eingaben() and d.ergebnis["kantungen"] == 0
d.close()
# Prüfdialog: scharfkantiges L-Profil -> Kantteil, außer das Profil steht in den Stammdaten
mw = [dict(profilform="L-Profil", abm_a="50", abm_b="30", wandstaerke="3",
           alternative=json.dumps(dict(profilform="Blech gekantet", blech="{}")))]
assert step.kantteile_vorbelegen(mw, {}) == 1 and mw[0]["profilform"] == "Blech gekantet"
assert step.kantteile_vorbelegen(mw, {}) == 0                  # nur einmal
mw = [dict(mw[0], profilform="L-Profil", _art_vorbelegt=False)]
assert step.kantteile_vorbelegen(mw, {"L 50x30x3": dict(form="L-Profil", a=50, b=30, wand=3)}) == 0
assert mw[0]["profilform"] == "L-Profil"
ok("B6 Kantteil aus STEP: Polygon-Außenkontur, mehrachsig mit Kantungen, 3D-Ansicht gefaltet, Profil/Kantteil nach "
   "Stammdaten")

# B7 Konturen im 3D aus dem Material geschnitten (Patrick 26.10.2026: „nicht in 3D im Material sichtbar, nur 2D-Linien“)
from collections import Counter  # noqa: E402

from rohrlaser import blech3d  # noqa: E402


def dicht_und_volumen(e):
    n = blech3d.netz(e, blech.zuschnitt(e))
    p, t = n["p"], n["t"]["BL"]

    def k(i):
        return tuple(round(p[3 * i + j], 2) for j in range(3))
    kanten, vol = Counter(), 0.0
    for q in range(0, len(t), 3):
        a, b, c = k(t[q]), k(t[q + 1]), k(t[q + 2])
        if len({a, b, c}) < 3:
            continue
        kanten.update(((a, b), (b, c), (c, a)))
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) +
                a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
    return sum(1 for (u, v), m in kanten.items() if kanten.get((v, u), 0) != m), abs(vol), n


loecher = [dict(art=sw.BOHRUNG, d=20, x=60, y=40), dict(art=sw.LANGLOCH, l=50, b=12, x=150, y=82),
           dict(art=sw.RECHTECK, b=40, h=30, x=150, y=140), dict(art=sw.BOHRUNG, d=30, x=2, y=2),
           dict(art=sw.TEXT_GRAVUR, text="AB", hoehe=10, x=250, y=40)]
for name, grund in (("flach", dict(laenge=300, breite=200, dicke=5)),
                    ("gekantet", dict(art=blech.KANTTEIL, dicke=4, kantlaenge=300,
                                      schenkel=[dict(laenge=80, winkel=90, radius=8), dict(laenge=100)]))):
    offen0, v0, n0 = dicht_und_volumen(grund)
    offen, v, n = dicht_und_volumen(dict(grund, konturen=loecher))
    s_ = grund["dicke"]
    soll = (math.pi * 100 + (38 * 12 + math.pi * 36) + 1200) * s_      # Ø20, Langloch, Rechteck (Ø30 am Rand bleibt)
    assert offen0 == 0 and offen == 0, (name, offen0, offen)
    assert abs((v0 - v) - soll) < 0.03 * soll, (name, v0 - v, soll)
    assert n["l"]["K"] and n.get("wk"), name             # Linien und Schnittkörper bleiben
pk = [(0, 0), (100, 0), (100, 50), (0, 50)]
assert len(blech3d.loecher(pk, [[(40, 20), (60, 20), (60, 30), (40, 30)], [(50, 25), (70, 25), (70, 35), (50, 35)],
                                [(90, 40), (110, 40), (110, 45), (90, 45)]])) == 1      # Überschneidung, Rand
ok("B7 Blech-3D: Bohrung, Langloch und Rechteck aus dem Material geschnitten, Netz dicht, Volumen passt; Kontur am "
   "Rand und Gravur bleiben Linien")
print("OK: Blech-Editor")
