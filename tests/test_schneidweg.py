"""Prüft den Schneidweg-Rechner (Positionen ohne STEP-Datei):
- Formeln: gerade Enden wie die Optimierung, Gehrung an Rund-, Quadrat- und Rechteckrohr (geometrisch), an offenen
  Profilen als Schätzung; Bohrung, Langloch, Rechteck mit Eckradius, Schlitz, sonstige Kontur; Einstiche je Ende
  nach Profilform; Konturklassen nach den Grenzen der Maschine; Prüfung unmöglicher Maße.
- Übernahme in die Position: Schneidweg, Einstiche, Enden, Innenkonturen, Konturliste, Klassen; Schneidzeit danach
  aus den Schneiddaten wie beim STEP-Import; Eingaben bleiben gespeichert (erneut öffnen), STEP-Werte nur nach
  Rückfrage ersetzt; Dialog zeigt Ergebnis und Schneidzeit sofort.
- Ältere Datei (Schema 25) bekommt die Spalte technik leer.

Aufruf: python tests/test_schneidweg.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
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
from rohrlaser import optimierung as opt, rechnen, schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.05):
    return abs(a - b) <= tol


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.neu("profile", dict(profil_id="IPE 200", form="I-/H-Träger", a=200, b=100, wand=5.6))
k = db.kontext()
RR, QR, RE, IPE = (k.profile[n] for n in ("RR 42,4x2,0", "QR 40x40x3", "RE 60x40x3", "IPE 200"))

# ------------------------------------------------------------------ S1 Enden
assert nah(sw.ende(RR)[0], math.pi * 42.4) and sw.ende(RR)[0] == opt.schnittlaenge("Rundrohr", 42.4, None, 2.0, None)
lg, sch = sw.ende(RR, 45)
r = 21.2
assert not sch and nah(lg, sw.ellipse(r, r / math.cos(math.radians(45))))
assert nah(sw.ellipse(10, 10), 2 * math.pi * 10, 1e-9) and nah(sw.ellipse(10, 20), 96.88, 0.01)   # Kreis, Ellipse 1:2
assert sw.ende(QR) == (160.0, False) and nah(sw.ende(QR, 45)[0], 2 * 40 / math.cos(math.radians(45)) + 80)
assert nah(sw.ende(RE, 30, "über Höhe")[0], 2 * 60 / math.cos(math.radians(30)) + 2 * 40)
assert nah(sw.ende(RE, 30, "über Breite")[0], 2 * 40 / math.cos(math.radians(30)) + 2 * 60)
g = sw.ende(IPE)[0]                                     # 200 + 2 × 100 − 5,6 (halber Umfang, scharfkantig)
c20 = math.cos(math.radians(20))
assert nah(g, 394.4) and sw.zerlegung(IPE) == (200, g - 200)
lg, sch = sw.ende(IPE, 20)
assert not sch and nah(lg, 200 / c20 + 194.4)                                  # Steg gekippt
assert nah(sw.ende(IPE, 20, "über Breite")[0], 200 + 194.4 / c20)              # Flansche gekippt
assert sw.ende(dict(form="Sonderform", a=50), 20) == (0.0, False) or sw.ende(dict(form="Sonderform", a=50), 20)[1]
try:
    sw.ende(QR, 85)
    raise AssertionError("85° muss abgelehnt werden")
except ValueError:
    pass
ok("S1 Enden: gerade wie Optimierung, Gehrung Rundrohr Ellipse, Quadrat/Rechteck/Träger je Richtung (Höhe, Breite)")

# ------------------------------------------------------------------ S2 Konturen
assert nah(sw.kontur(dict(art="Bohrung", anzahl=4, d=10))[0], math.pi * 10)
assert sw.kontur(dict(art="Bohrung", anzahl=4, d=10))[1:] == (10, 4)
assert nah(sw.kontur(dict(art="Langloch", anzahl=1, l=30, b=10))[0], 40 + math.pi * 10)
assert nah(sw.kontur(dict(art="Rechteck", anzahl=1, b=20, h=60, r=0))[0], 160)
assert nah(sw.kontur(dict(art="Rechteck", anzahl=1, b=20, h=60, r=5))[0], 160 - 40 + 10 * math.pi)
assert sw.kontur(dict(art="Schlitz", anzahl=2, l=25, b=4))[:2] == (54, 25)
assert sw.kontur(dict(art="sonstige Kontur", anzahl=1, laenge=123))[1] is None
for falsch in (dict(art="Bohrung", anzahl=1), dict(art="Langloch", anzahl=1, l=5, b=10),
               dict(art="Rechteck", anzahl=1, b=10, h=10, r=6), dict(art="Bohrung", anzahl=0, d=5),
               dict(art="sonstige Kontur", anzahl=1)):
    try:
        sw.kontur(falsch)
        raise AssertionError(falsch)
    except ValueError:
        pass
ok("S2 Konturen: Bohrung π·d, Langloch 2(l−b)+π·b, Rechteck mit Eckradius, Schlitz 2l+b, unmögliche Maße abgelehnt")

# ------------------------------------------------------------------ S3 Gesamtrechnung
EIN = dict(a=dict(winkel=45), b={}, gravur=50,
           konturen=[dict(art="Bohrung", anzahl=4, d=8.5), dict(art="Langloch", anzahl=2, l=30, b=10),
                     dict(art="Rechteck", anzahl=1, b=20, h=60, r=2), dict(art="sonstige Kontur", anzahl=1, laenge=123)])
erg = sw.rechnen(EIN, QR, (10, 50))
f = erg["felder"]
innen = 4 * math.pi * 8.5 + 2 * (40 + math.pi * 10) + (160 - 16 + 4 * math.pi) + 123
a_s = 2 * 40 / math.cos(math.radians(45)) + 80
assert not erg["fehler"] and nah(f["innen"], innen) and nah(f["a_schnitt"], a_s) and f["b_schnitt"] == 160
assert nah(f["schneidweg"], a_s + 160 + innen, 0.1) and f["einstiche"] == 2 + 4 + 2 + 1 + 1
assert (f["a_gerade"], f["b_gerade"]) == ("nein", "ja") and f["gravur"] == 50 and f["kontur_grenzen"] == "10/50"
assert (f["klein_n"], f["mittel_n"], f["gross_n"]) == (4, 2, 2), f
assert f["konturen"].startswith("A:40x193,1; E:40x160; 8,5x26,7") and f["konturen"].endswith("9999x123"), f["konturen"]
assert rechnen.konturen_lesen(f["konturen"], True)[0] == ("A", 40.0, 193.1)
assert sw.rechnen(dict(a={}, b={}), IPE, (10, 50))["einstiche"] == 8          # Träger: 4 Einstiche je Ende
fe = sw.rechnen(dict(a=dict(winkel=85), b={}, konturen=[dict(art="Bohrung", anzahl=1)]), QR, (10, 50))
assert len(fe["fehler"]) == 2 and fe["felder"]["a_schnitt"] == 160            # Fehler gemeldet, gerade gerechnet
ok("S3 Gesamt: Schneidweg = Enden + Innenkonturen, Einstiche je Kontur + je Ende, Klassen klein/mittel/groß, Konturliste")

# ------------------------------------------------------------------ S4 Übernahme in die Position
a = db.angebot_neu(dict(kunde="Test", maschine="T03"))
db.position_neu(a, dict(pos=10, artikel="ohne STEP", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=800,
                        stueck=10))
db.position_neu(a, dict(pos=20, artikel="mit STEP", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=800,
                        stueck=10, schneidweg=500, einstiche=3, a_schnitt=160, b_schnitt=160, innen=180,
                        a_gerade="ja", b_gerade="ja"))
db.position_neu(a, dict(pos=30, artikel="Zukauf", art="Zukaufteil", stueck=1))
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, stumm=True)
fenster.resize(1920, 1080)
s = fenster.angebot_oeffnen(a)
assert s.schneidweg_berechnen(0, EIN)
p = db.positionen(a)[0]
for n, w in f.items():
    assert p[n] == w, (n, p[n], w)
assert sw.lesen(p["technik"])["quelle"] == sw.QUELLE and sw.lesen(p["technik"])["konturen"][0]["d"] == 8.5
w = rechnen.position_werte(p, s.kopf, s.k, s.tabellen)
sd, _, zeit = rechnen.schneidzeit(p, s.kopf, w["wand_schneiden"], s.tabellen, s.k)
assert zeit and zeit > 0 and s.pos_modell.zeiten[0] == zeit
anteile = rechnen.zeitanteile(p, rechnen.schneidzeit(p, s.kopf, w["wand_schneiden"], s.tabellen, s.k)[1])
assert anteile["klein"] > 0 and anteile["mittel"] > 0 and anteile["gravur"] > 0
# STEP-Werte: nur nach Rückfrage ersetzen
assert s.schneidweg_berechnen(1, EIN, ueberschreiben=False) is False and db.positionen(a)[1]["schneidweg"] == 500
assert s.schneidweg_berechnen(1, EIN, ueberschreiben=True) and db.positionen(a)[1]["schneidweg"] == f["schneidweg"]
assert s.schneidweg_berechnen(2, EIN) is False                                   # Zukaufteil
assert s.schneidweg_berechnen(0, dict(a={}, b={}, konturen=[dict(art="Bohrung", anzahl=1)])) is False
assert db.positionen(a)[0]["schneidweg"] == f["schneidweg"]                      # Fehler: nichts geändert
ok("S4 Übernahme: Felder der Position, Schneidzeit aus Schneiddaten, Eingaben gespeichert, STEP-Werte nur nach Rückfrage")

# ------------------------------------------------------------------ S5 Dialog
gesehen = {}


def bedienen(d):
    """Dialog wie ein Benutzer: gespeicherte Eingaben sichtbar, eine Bohrung dazu, Ergebnis prüfen, OK."""
    gesehen["zeilen"] = d.tabelle.rowCount()
    gesehen["winkel"] = d.winkel["a"].value()
    d.zeile_neu(dict(art="Bohrung", anzahl=2, d=6))
    gesehen["summe"] = d.summe.text()
    gesehen["schritte"] = d.ergebnis_tabelle.rowCount()
    d.winkel["b"].setValue(30)
    return QDialog.Accepted


assert "Schneidweg berechnen …" in [x.text() for x in s.pos_menue.actions()]           # Rechtsklick
assert "Schneidweg berechnen …" in [x.text() for x in s.weitere.menu().actions()]      # Weitere Aktionen
assert s.schneidweg_berechnen(0, dialog=bedienen)
assert gesehen["zeilen"] == 4 and gesehen["winkel"] == 45 and gesehen["schritte"] == 2 + 5
assert "Schneidweg" in gesehen["summe"] and "Schneidzeit je Teil" in gesehen["summe"]
p = db.positionen(a)[0]
assert p["einstiche"] == f["einstiche"] + 2 and p["b_gerade"] == "nein" and p["b_schnitt"] > 160
assert nah(p["innen"], f["innen"] + 2 * math.pi * 6, 0.1)
# Dialog mit falschem Maß: OK gesperrt
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402
dlg = SchneidwegDialog(s, p, QR, s.kopf, s.k, s.tabellen)
dlg.zeile_neu(dict(art="Langloch", anzahl=1, l=5, b=10))
assert not dlg.ok_knopf.isEnabled() and "Langloch" in dlg.summe.text()
dlg.tabelle.removeRow(dlg.tabelle.rowCount() - 1)
dlg.rechnen()
assert dlg.ok_knopf.isEnabled()
# ohne Schneiddaten (Werkstoff ohne Zeile): Hinweis statt Zeit
dlg2 = SchneidwegDialog(s, dict(p, werkstoff_id="gibt es nicht"), QR, s.kopf, s.k, s.tabellen)
assert "Keine Schneiddaten" in dlg2.summe.text()
dlg3 = SchneidwegDialog(s, dict(p, technik=None), IPE, s.kopf, s.k, s.tabellen)
dlg3.winkel["a"].setValue(15)
assert dlg3.achse["a"].isEnabled() and not dlg3.sattel["a"].isEnabled()
assert "Gehrung 15° über Höhe" in dlg3.ergebnis_tabelle.item(0, 0).text() and "geschätzt" not in dlg3.summe.text()
ok("S5 Dialog: gespeicherte Eingaben, Ergebnis je Schnitt und Schneidzeit sofort, falsche Maße sperren OK, Richtung")

# ------------------------------------------------------------------ S7 Ausklinkung, Polygon, Gewinde-Vorschlag, Skizze
assert nah(sw.sattel(42.4, 1e6), math.pi * 42.4, 0.01)          # riesiges Gegenrohr: fast gerader Schnitt
s_gl = sw.sattel(42.4, 42.4)             # gleich groß: zwei halbe Ellipsen wie zwei 45°-Gehrungen
assert nah(s_gl, sw.ellipse(21.2 * math.sqrt(2), 21.2), 0.05), s_gl
assert sw.sattel(42.4, 60.3) > math.pi * 42.4
for falsch in (lambda: sw.sattel(42.4, 30), lambda: sw.ende(QR, 0, gegenrohr=60),
               lambda: sw.ende(RR, 30, gegenrohr=60)):
    try:
        falsch()
        raise AssertionError("muss abgelehnt werden")
    except ValueError:
        pass
e7 = dict(a=dict(sattel=60.3), b={}, konturen=[
    dict(art="Polygon", anzahl=1, punkte="0,0; 40,0; 40,20; 0,20", x=300),
    dict(art="Bohrung", anzahl=4, d=8.5), dict(art="Bohrung", anzahl=2, d=6.8), dict(art="Bohrung", anzahl=1, d=13)])
e7r = sw.rechnen(e7, RR, (10, 50))
f7 = e7r["felder"]
assert not e7r["fehler"] and f7["a_gerade"] == "nein" and nah(f7["a_schnitt"], sw.sattel(42.4, 60.3), 0.1)
assert "Ausklinkung auf Rundrohr Ø 60,3" in e7r["schritte"][0]["text"]
pol = next(x for x in e7r["schritte"] if "Polygon" in x["text"])
assert pol["laenge"] == 120 and pol["huelle"] == 40 and pol["klasse"] == "mittel" and "4 Eckpunkte" in pol["text"]
assert f7["bohrungen"] == "2xØ6,8; 4xØ8,5; 1xØ13" and f7["gewinde_vorschlag"] == "2xM8; 4xM10", f7
assert "Polygon" in sw.rechnen(dict(a={}, b={}, konturen=[dict(art="Polygon", anzahl=1, punkte="0,0; 1")]), RR,
                               (10, 50))["fehler"][0]
s2 = s
db.position_neu(a, dict(pos=40, artikel="Geländerpfosten", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                        laenge=1000, stueck=6))
s2.neu_laden()
assert s2.schneidweg_berechnen(3, e7)
p4 = db.positionen(a)[3]
assert p4["gewinde_vorschlag"] == "2xM8; 4xM10" and p4["gewinde"] is None
assert s2.pos_modell.status[3].startswith("HINWEIS: Gewinde-Vorschlag prüfen"), s2.pos_modell.status[3]
dlg7 = SchneidwegDialog(s2, p4, RR, s2.kopf, s2.k, s2.tabellen)
assert dlg7.sattel["a"].value() == 60.3 and dlg7.tabelle.item(0, 2).text() == "0,0; 40,0; 40,20; 0,20"
assert dlg7.tabelle.item(0, 5).text() == "300" and "Vorschlag" in dlg7.summe.text() and "M10" in dlg7.summe.text()
formen = dlg7.skizze.formen()
assert len(formen) == 8 and formen[0][0] == 300 and formen[0][2] == "Polygon"
dlg7.resize(1000, 760)
bild = dlg7.skizze.grab()
assert bild.width() > 100 and bild.height() >= 130
assert dlg7.eingaben()["konturen"][0] == dict(art="Polygon", anzahl=1, punkte="0,0; 40,0; 40,20; 0,20", x=300)
ok("S7 Ausklinkung auf Rundrohr, Polygon aus Koordinaten, Lage, Gewinde-Vorschlag (HINWEIS), Skizze")

# ------------------------------------------------------------------ S6 ältere Datei
db.schliessen()
alt = tmp / "alt.db"
shutil.copy(tmp / "rohrlaser.db", alt)
con = sqlite3.connect(alt)
con.execute("ALTER TABLE positionen DROP COLUMN technik")
con.execute("PRAGMA user_version=25")
con.commit()
con.close()
db2 = Datenbank(alt)
assert db2.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
assert all(p["technik"] is None for p in db2.positionen(a)) and db2.positionen(a)[0]["schneidweg"] == p["schneidweg"]
assert db2.sicherungen(zusatz=f"vor_Schema_{SCHEMA_VERSION}")
db2.schliessen()
ok("S6 Datei mit Schema 25: Spalte technik leer ergänzt, Werte unverändert, Sicherung vorher")
print("OK: Schneidweg-Rechner")
