"""Prüft den Blech-Editor (Richtpreis für Blech- und Kantteile, Patrick 22.10.2026):
- B1 Abwicklung: Ausgleichswert je Biegung (90° wie Tabelle, stumpf/spitz), Lage der Biegelinien, Zuschnitt
  Rechteck mit Eckradius und Polygon, Prüfung unmöglicher Maße.
- B2 Richtpreis: Material (Hüllrechteck mit Verschnitt), Laser (Vorschub je Kategorie und Dicke, N₂ vor O₂,
  Innenkonturen, Einstiche), Kanten, Rüsten je Stück, Aufschlag; fehlende Richtwerte als Fehler.
- B3 Daten getrennt: eigene Tabellen und Einstellungen; Rohrlaser-Werkstoffe und -Schneiddaten bleiben unverändert;
  ältere Datei (Schema 36) bekommt die Blech-Tabellen.
- B4 Angebot: Neue Position → Blech / Kantteil legt Zukaufartikel (Blechteile, Artikeltyp Blech, Richtpreis als EK)
  und Position an; erneut öffnen trägt den neuen Richtpreis ab Stückzahl ein.

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
erg = blech.rechnen(e, werkstoffe, laser)
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
print("OK: Blech-Editor")
