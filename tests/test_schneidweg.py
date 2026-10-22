"""Prüft den Schneidweg-Rechner (Positionen ohne STEP-Datei):
- Formeln: gerade Enden wie die Optimierung, Gehrung an Rund-, Quadrat- und Rechteckrohr (geometrisch), an offenen
  Profilen als Schätzung; Bohrung, Langloch, Rechteck mit Eckradius, Schlitz, sonstige Kontur; Einstiche je Ende
  nach Profilform; Konturklassen nach den Grenzen der Maschine; Prüfung unmöglicher Maße.
- Übernahme in die Position: Schneidweg, Einstiche, Enden, Innenkonturen, Konturliste, Klassen; Schneidzeit danach
  aus den Schneiddaten wie beim STEP-Import; Eingaben bleiben gespeichert (erneut öffnen), STEP-Werte nur nach
  Rückfrage ersetzt; Dialog zeigt Ergebnis und Schneidzeit sofort.
- Skizze (S8): maßstäbliche Draufsicht, Seitenansicht und Abwicklung je Profilform, Lage der Konturen (Seite,
  Versatz, Muster), Klick markiert die Zeile, Ziehen verschiebt die Kontur, Zoom.
- Ältere Datei (Schema 25) bekommt die Spalte technik leer.

Aufruf: python tests/test_schneidweg.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QLabel  # noqa: E402
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
for n, w in f.items():       # im Angebot mit der Wandstärke des Profils (3 mm), gleiche Klassen
    assert p[n] == (w if n != "kontur_grenzen" else "10/50; 3×/8× Wand 3"), (n, p[n], w)
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
assert s2.pos_modell.status[3].startswith("HINWEIS: Bohrungen prüfen"), s2.pos_modell.status[3]
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

# ------------------------------------------------------------------ S8 Skizze maßstäblich (0.6.26)
from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from rohrlaser import skizze as sk  # noqa: E402
from rohrlaser.schneidweg_dialog import ABSTAND_SPALTE, LAGE_SPALTE, QUER_SPALTE, SEITE_SPALTE  # noqa: E402

# Querschnitt und Abwicklung je Profilform: Flächen, Umfang der Abwicklung
assert sk.Querschnitt(RE).seiten() == ["oben", "vorne", "unten", "hinten"] and nah(sk.Querschnitt(RE).umfang, 200)
assert sk.Querschnitt(RR).seiten()[1] == "vorne (90°)" and nah(sk.Querschnitt(RR).umfang, math.pi * 42.4, 0.01)
assert sk.Querschnitt(IPE).seiten() == ["Flansch oben", "Steg", "Flansch unten"]
for form, seiten in (("U-Profil", ["Flansch oben", "Steg", "Flansch unten"]), ("L-Profil", ["Schenkel a", "Schenkel b"]),
                     ("T-Profil", ["Flansch", "Steg"]), ("Flachstahl", ["oben", "vorne", "unten", "hinten"])):
    q_ = sk.Querschnitt(dict(form=form, a=60, b=40, wand=5))
    assert q_.seiten() == seiten and q_.umfang > 0 and len(q_.abwicklung_streifen()) == len(seiten), form
# RE 60x40 liegt mit der Breitseite (60) oben. Gehrung 45° über Breite (Maß b = 40, senkrecht): oben 0, unten 40
# zurück; über Höhe (Maß a = 60, waagrecht): vorne 0, hinten 60; Richtung 180°: oben 40 zurück
qs = sk.Querschnitt(RE)
assert (qs.B, qs.H) == (60, 40)
e45 = dict(winkel=45, achse="über Breite")
assert nah(sk.schnitt_x(qs, e45, 0, 20), 0) and nah(sk.schnitt_x(qs, e45, 0, -20), 40)
assert nah(sk.schnitt_x(qs, dict(e45, richtung=180), 0, 20), 40)
assert nah(sk.schnitt_x(qs, dict(winkel=45, achse="über Höhe"), -30, 0), 60)
# Abwicklung: Schnittlinie des Endes; Seitenansicht zeigt die Schräge, Draufsicht nur die verdeckte Kante
linie = dict(sk.ende_abwicklung(qs, e45, 200))
assert nah(linie[0], 0) and nah(max(linie.values()), 40)
sil_v = sk.silhouette(qs, e45, {}, 800, "vorne")
assert nah(sil_v[0][1], 40) and nah(sil_v[-1][1], 0) and nah(sil_v[0][4], 800)        # schräg in der Seitenansicht
sil_o = sk.silhouette(qs, e45, {}, 800, "oben")
assert all(nah(z[1], 0) and nah(z[2], 0) and nah(z[3], 40) for z in sil_o)        # oben gerade, unten verdeckt bei 40
# Ausklinkung Rundrohr: Sattel R − √(R² − v²)
qr_ = sk.Querschnitt(RR)
assert nah(sk.schnitt_x(qr_, dict(sattel=60.3), 0, 21.2), 30.15 - math.sqrt(30.15 ** 2 - 21.2 ** 2), 0.01)
# Lage auf dem Teil und zurück (Abwicklung)
for seite, q in (("oben", 0), ("vorne", 12.5), ("hinten", -20)):
    assert sk.s_zu_seite(qs, sk.s_lage(qs, dict(seite=seite, q=q))) == (seite, q)
assert sk.s_zu_seite(qr_, sk.s_lage(qr_, dict(seite=90)))[0] == "vorne (90°)"
assert sk.winkel_aus_text("vorne (90°)") == 90 and sk.winkel_aus_text("45°") == 45 and sk.winkel_aus_text("x") is None
# Muster längs: Anzahl im Abstand ab Lage; ohne Lage verteilt; Schlitz ohne Lage am Ende A
lg = sk.lagen([dict(art="Bohrung", anzahl=3, d=8, x=100, abstand=50), dict(art="Bohrung", anzahl=1, d=8),
               dict(art="Schlitz", anzahl=1, l=40, b=6)], 1000)
assert [d["x"] for d in lg] == [100, 150, 200, 500, 20] and lg[3]["verteilt"]
pk, n_ = sk.platzieren(qs, dict(lg[0], eingabe=dict(art="Bohrung", anzahl=1, d=8, seite="vorne", q=10)))
assert n_ == (1, 0) and all(nah(u, 30) for _, u, _ in pk) and nah(sum(v for *_, v in pk) / len(pk), -10, 0.01)

# Dialog: Spalten Abstand/Seite/Versatz, Muster in der Rechnung unverändert, Klick und Ziehen in der Skizze
p8 = dict(db.positionen(a)[0], technik=sw.speichern(dict(a=dict(winkel=45, achse="über Breite"), b={}, konturen=[
    dict(art="Bohrung", anzahl=4, d=6.6, x=200, abstand=100, seite="vorne"),
    dict(art="Langloch", anzahl=1, l=30, b=10, x=600, seite="unten", q=5)])), laenge=800, profil_id="RE 60x40x3")
dlg8 = SchneidwegDialog(s, p8, RE, s.kopf, s.k, s.tabellen)
dlg8.resize(1300, 950)
dlg8.show()
app.processEvents()
t8 = dlg8.tabelle
assert t8.item(0, ABSTAND_SPALTE).text() == "100" and t8.cellWidget(0, SEITE_SPALTE).currentText() == "90° vorne"
assert t8.cellWidget(1, SEITE_SPALTE).currentText() == "180° unten" and t8.item(1, QUER_SPALTE).text() == "5"
e8 = dlg8.eingaben()
assert e8["konturen"][0] == dict(art="Bohrung", anzahl=4, d=6.6, x=200, abstand=100, seite="vorne")
assert nah(dlg8.ergebnis["felder"]["innen"], 4 * math.pi * 6.6 + 2 * 20 + math.pi * 10, 0.1)    # Lage zählt nicht
sk8 = dlg8.skizze
sk8.grab()
assert [round(x) for x, _, _ in sk8.formen()] == [200, 300, 400, 500, 600]
treffer = [(poly, d, an) for poly, d, an in sk8.treffer if d["zeile"] == 0 and d["nr"] == 1 and an[0] == "vorne"]
assert len(treffer) == 1                        # vorne nur in der Seitenansicht, nicht in der Draufsicht
assert not [1 for _, d, an in sk8.treffer if d["zeile"] == 0 and an[0] == "oben"]
start = treffer[0][0].boundingRect().center().toPoint()
QTest.mouseClick(sk8, Qt.LeftButton, Qt.NoModifier, start)
assert sorted({i.row() for i in t8.selectedIndexes()}) == [0] and sk8.markiert == 0
t8.selectRow(1)
assert sk8.markiert == 1
m = sk8.massstab()
QTest.mousePress(sk8, Qt.LeftButton, Qt.NoModifier, start)
QTest.mouseMove(sk8, start + QPoint(round(50 * m), 0))
QTest.mouseRelease(sk8, Qt.LeftButton, Qt.NoModifier, start + QPoint(round(50 * m), 0))
x_neu = float(t8.item(0, LAGE_SPALTE).text().replace(",", "."))
assert abs(x_neu - 250) <= 1.5 / m + 0.2, x_neu       # ganzes Muster um 50 mm verschoben
assert t8.item(0, ABSTAND_SPALTE).text() == "100" and dlg8.eingaben()["konturen"][0]["x"] == x_neu
# Abwicklung: Ziehen quer wechselt die Seite (vorne -> unten)
dlg8.ansicht_wahl.setCurrentText("Abwicklung")
sk8.grab()
tr = next(poly for poly, d, an in sk8.treffer if d["zeile"] == 0 and d["nr"] == 0)
st = tr.boundingRect().center().toPoint()
m = sk8.massstab()
QTest.mousePress(sk8, Qt.LeftButton, Qt.NoModifier, st)
QTest.mouseMove(sk8, st + QPoint(0, round(50 * m)))
QTest.mouseRelease(sk8, Qt.LeftButton, Qt.NoModifier, st + QPoint(0, round(50 * m)))
assert t8.cellWidget(0, SEITE_SPALTE).currentText() == "180° unten", t8.cellWidget(0, SEITE_SPALTE).currentText()
# Zoom mit dem Mausrad, Doppelklick passt ein
alt = sk8.massstab()
sk8.zoom = 4.0
assert nah(sk8.massstab(), 4 * alt, 1e-6)
QTest.mouseDClick(sk8, Qt.LeftButton, Qt.NoModifier, QPoint(5, 5))
assert sk8.zoom == 1.0
for name in ("U 100x50x6", "L 50x30x5", "T 50x50x6", "FL 40x5"):    # jede Profilform zeichnet ohne Fehler
    pr = dict(profil_id=name, **(opt.profil_aus_name(name) or {}))
    d_ = SchneidwegDialog(s, dict(p8, technik=None, profil_id=name), pr, s.kopf, s.k, s.tabellen)
    d_.zeile_neu(dict(art="Bohrung", anzahl=2, d=8, x=100, abstand=200, seite=sk.Querschnitt(pr).seiten()[-1]))
    for modus in ("Abwicklung", "Draufsicht und Seitenansicht"):
        d_.ansicht_wahl.setCurrentText(modus)
        assert not d_.skizze.grab().isNull() and d_.skizze.treffer, (name, modus)
dlg8.close()
ok("S8 Skizze maßstäblich: Querschnitt und Abwicklung je Profil, Gehrung/Ausklinkung, Seite und Muster, Klick "
   "markiert die Zeile, Ziehen verschiebt Lage bzw. Seite, Zoom")

# ------------------------------------------------------------------ S9 Editor: Senkung, Ausklinkung, Vorlagen, Kopieren
s9 = sw.rechnen(dict(a={}, b={}, konturen=[dict(art="Senkung", anzahl=2, d=6.6, D=12),
                                           dict(art="Ausklinkung", anzahl=1, l=30, b=20, r=5)]), RE, (10, 50))
assert not s9["fehler"] and s9["einstiche"] == 2 + 3
sen, aus = s9["schritte"][2], s9["schritte"][3]
assert nah(sen["laenge"], 2 * math.pi * 6.6) and sen["huelle"] == 6.6 and sen["klasse"] == "klein"
assert nah(aus["laenge"], 2 * 25 + 10 + math.pi * 5) and aus["huelle"] == 30 and aus["klasse"] == "mittel"
assert s9["hinweise"] and "Senkung" in s9["hinweise"][0] and s9["felder"]["bohrungen"] is None   # kein Gewinde-Vorschlag
for falsch in (dict(art="Senkung", anzahl=1, d=8, D=6), dict(art="Ausklinkung", anzahl=1, l=10, b=8, r=5)):
    assert sw.rechnen(dict(a={}, b={}, konturen=[falsch]), RE, (10, 50))["fehler"], falsch
assert [d["x"] for d in sk.lagen([dict(art="Ausklinkung", anzahl=1, l=30, b=20)], 800)] == [15]   # am Ende A
p_leer = dict(p8, technik=None, konturen=None, a_schnitt=None, b_schnitt=None, gravur=None)    # ohne Werte
dlg9 = SchneidwegDialog(s, p_leer, RE, s.kopf, s.k, s.tabellen, db, db.positionen(a))
assert {"Senkung", "Ausklinkung"} <= set(sw.ARTEN) and dlg9.tabelle.rowCount() == 0
dlg9.zeile_neu(dict(art="Senkung", anzahl=2, d=6.6, D=12, x=100, abstand=50, seite="oben"))
assert "Senkung" in dlg9.summe.text() and dlg9.ok_knopf.isEnabled()
dlg9.winkel["a"].setValue(30)
assert dlg9.vorlage_speichern("Halter 2 Senkungen") and not dlg9.vorlage_speichern("  ")
v = db.einstellung("rechner_vorlagen")
assert v["Halter 2 Senkungen"]["profilform"] == "Rechteckrohr" and v["Halter 2 Senkungen"]["a"]["winkel"] == 30
dlg10 = SchneidwegDialog(s, p_leer, RE, s.kopf, s.k, s.tabellen, db, db.positionen(a))
assert dlg10.tabelle.rowCount() == 0 and dlg10.vorlage_laden("Halter 2 Senkungen")
assert dlg10.winkel["a"].value() == 30 and dlg10.eingaben()["konturen"] == dlg9.eingaben()["konturen"]
assert not dlg10.vorlage_laden("gibt es nicht")
dlg10._vorlagen_menue()
assert [x.text() for x in dlg10.vorlagen_knopf.menu().actions()][0] == "Als Vorlage speichern …"
# Konturen einer anderen Position anhängen (Position 1 hat Konturen aus S4/S5)
kop = dlg10.kopierbare()
assert kop and all("Zeile" in t_ for t_, _ in kop)
n_vor = dlg10.tabelle.rowCount()
n_k = dlg10.konturen_kopieren(kop[0][1])
assert n_k > 0 and dlg10.tabelle.rowCount() == n_vor + n_k and dlg10.winkel["a"].value() == 30   # Enden bleiben
assert dlg10.vorlage_loeschen("Halter 2 Senkungen") and dlg10.vorlagen() == {}
# Senkung und Ausklinkung zeichnen
dlg10.zeile_neu(dict(art="Ausklinkung", anzahl=1, l=30, b=20, r=5))
dlg10.ansicht_wahl.setCurrentText("Abwicklung")
assert not dlg10.skizze.grab().isNull() and any(d["art"] == "Ausklinkung" for _, d, _ in dlg10.skizze.treffer)
ok("S9 Editor: Senkung (Bohrung geschnitten, Hinweis Zusatzarbeit), Ausklinkung am Ende, Vorlagen speichern/laden/"
   "löschen, Konturen aus einer anderen Position anhängen")

# ------------------------------------------------------------------ S10 Konturen aus dem STEP-Import (4b)
from rohrlaser import step  # noqa: E402
m10 = dict(konturen_liste=json.dumps([
    dict(art="Ende A", durchgehend=True, z=0, form="Gehrung", gehrung=45.0, richtung=90.0, schnittlaenge=230.5,
         huellmass=84.9),
    dict(art="Ende B", durchgehend=True, z=800, form="gerade", gehrung=None, richtung=None, schnittlaenge=200.0,
         huellmass=60.0),
    dict(art="Bohrung", durchgehend=True, z=120.0, winkel=0.0, u=0.0, seite="0°", durchmesser=8.5,
         schnittlaenge=26.6, huellmass=8.5),
    dict(art="Langloch", durchgehend=True, z=400.0, winkel=90.0, u=55.0, seite="90°", laenge=30.0, breite=10.0,
         richtung=90.0, schnittlaenge=72.6, huellmass=30.0),
    dict(art="Rechteckausschnitt", durchgehend=True, z=600.0, winkel=180.0, u=100.0, seite="180°", laenge=40.0,
         breite=20.0, richtung=0.0, schnittlaenge=119.0, huellmass=40.0),
    dict(art="Ausschnitt", durchgehend=True, z=700.0, winkel=270.0, u=150.0, seite="270°", laenge=25.0, breite=12.0,
         schnittlaenge=80.0, huellmass=25.0),
    dict(art="Gravur", durchgehend=False, z=300.0, schnittlaenge=50.0)]))
e10 = step.rechner_eingaben(m10, "Rechteckrohr", 60, 40)
assert e10["quelle"] == "STEP-Import" and len(e10["konturen"]) == 4                 # Gravur nicht
assert e10["a"]["gemessen"] == 230.5 and e10["a"]["winkel"] == 45 and e10["a"]["richtung"] == 90
assert e10["a"]["achse"] == "über Höhe" and e10["b"]["form"] == "gerade"           # 90°: über die Breitseite (a=60)
k10 = e10["konturen"]
assert k10[0] == dict(anzahl=1, x=120.0, gemessen=26.6, huelle_gemessen=8.5, art="Bohrung", d=8.5)
assert k10[1]["seite"] == "vorne" and k10[1]["art"] == "Langloch" and "quer" not in k10[1] and k10[1]["q"] == 5
assert k10[2]["seite"] == "unten" and (k10[2]["b"], k10[2]["h"]) == (20, 40)       # quer liegendes Rechteck
assert k10[3]["art"] == "sonstige Kontur" and k10[3]["laenge"] == 80 and k10[3]["seite"] == "hinten"
assert "q" not in k10[0] and "q" not in k10[2] and "q" not in k10[3]               # Flächenmitte (u 0/100/150)
r10 = sw.rechnen(e10, RE, (10, 50))
assert not r10["fehler"] and nah(r10["schneidweg"], 230.5 + 200 + 26.6 + 72.6 + 119 + 80, 0.11)
assert "STEP gemessen" in r10["schritte"][0]["text"] and r10["felder"]["a_gerade"] == "nein"
assert r10["felder"]["b_gerade"] == "ja"
assert step.rechner_eingaben(dict(konturen_liste=""), "Rundrohr", 42.4) is None
e_rr = step.rechner_eingaben(dict(konturen_liste=json.dumps([dict(art="Bohrung", durchgehend=True, z=50, winkel=135.0,
                                                                  durchmesser=6, schnittlaenge=18.8)])), "Rundrohr", 42.4)
assert e_rr["konturen"][0]["seite"] == 135.0
# Dialog: STEP-Zeilen mit gemessener Länge; Maß ändern -> Formel; Ende ändern -> Formel
p10 = dict(p8, technik=json.dumps(e10), laenge=800)
d10 = SchneidwegDialog(s, p10, RE, s.kopf, s.k, s.tabellen, db, [])
assert nah(d10.ergebnis["schneidweg"], r10["schneidweg"], 0.01)
assert any("STEP-Import" in x.text() for x in d10.findChildren(QLabel))
assert d10.tabelle.cellWidget(2, SEITE_SPALTE).currentText() == "180° unten"
d10.tabelle.item(0, 2).setText("9")                 # Bohrung Ø 9 statt 8,5: gerechnet
assert nah(d10.ergebnis["schritte"][2]["laenge"], math.pi * 9) and "gemessen" not in d10.eingaben()["konturen"][0]
assert d10.eingaben()["konturen"][1]["gemessen"] == 72.6
d10.winkel["a"].setValue(30)
assert "gemessen" not in d10.eingaben()["a"] and "STEP" not in d10.ergebnis["schritte"][0]["text"]
assert d10.vorlage_speichern("aus STEP") and "gemessen" not in json.dumps(db.einstellung("rechner_vorlagen"))
d10.vorlage_loeschen("aus STEP")
ok("S10 STEP-Konturen im Rechner: Art, Maße, Lage, Seite aus der Messung, gemessene Längen bis zur Änderung, "
   "Vorlagen ohne Messwerte")

# echte STEP-Datei (braucht OpenCascade): Rechner zeigt die Konturen, Schneidweg wie gemessen
if step.messprogramm(HIER.parent / "programm") is None:
    print("HINWEIS: OpenCascade fehlt, K01 nicht gemessen")
else:
    k01 = db.angebot_neu(dict(kunde="STEP", maschine="T03"))
    sk01 = fenster.angebot_oeffnen(k01)
    sk01.step_importieren([str(HIER / "step_konturen" / "K01_RE60x40x3_Konturen.step")], "S235-10219", 1,
                          als_satz=False)
    pk = db.positionen(k01)[0]
    ek = sw.lesen(pk["technik"])
    assert ek["quelle"] == "STEP-Import" and ek["konturen"] and all(sw._z(z.get("gemessen")) for z in ek["konturen"])
    dk = SchneidwegDialog(sk01, pk, sk01.k.profile[pk["profil_id"]], sk01.kopf, sk01.k, sk01.tabellen, db, [])
    assert not dk.ergebnis["fehler"], dk.ergebnis["fehler"]
    assert nah(dk.ergebnis["schneidweg"], pk["schneidweg"], 0.6), (dk.ergebnis["schneidweg"], pk["schneidweg"])
    assert dk.tabelle.rowCount() == len(ek["konturen"]) and not dk.skizze.grab().isNull()
    assert all(d["x"] == z["x"] for d, z in zip(dk.skizze.lagen(), ek["konturen"]) if z.get("anzahl") == 1)
    ok(f"S10 K01 aus STEP: {len(ek['konturen'])} Konturen im Rechner, Schneidweg {pk['schneidweg']} mm wie gemessen")

# ------------------------------------------------------------------ S11 STEP-Werte älterer Positionen, Naht, Seite, Zeichnung
from rohrlaser import naht as naht_  # noqa: E402
from rohrlaser.schneidweg_dialog import NAHT_WAHL  # noqa: E402
alt_p = dict(id=999, pos=70, artikel="alt importiert", profil_id="RE 60x40x3", werkstoff_id="S235-10219", laenge=420,
             stueck=5, technik=None, schneidweg=500.0, einstiche=6, a_schnitt=193.1, b_schnitt=226.3, a_gerade="ja",
             b_gerade="nein", b_ende=naht_.ende_text(30, 90), innen=80.0, gravur=58.0,
             konturen="A:60x193,1; E:69,3x226,3; 8,5x26,7; 8,5x26,7; 20x60")
e11, aus = sw.aus_position(sw.lesen(None), alt_p, RE)
assert aus and e11["gravur"] == 58 and e11["a"]["gemessen"] == 193.1 and e11["a"]["form"] == "gerade"
assert e11["b"]["winkel"] == 30 and e11["b"]["richtung"] == 90 and e11["b"]["achse"] == "über Höhe"
bohr = [z for z in e11["konturen"] if z["art"] == "Bohrung"]
assert len(bohr) == 1 and bohr[0]["anzahl"] == 2 and bohr[0]["d"] == 8.5 and bohr[0]["gemessen"] == 26.7
assert any(z["art"] == "sonstige Kontur" and z["laenge"] == 60 and z["huelle"] == 20 for z in e11["konturen"])
r11 = sw.rechnen(e11, RE, (10, 50))
assert nah(r11["schneidweg"], 193.1 + 226.3 + 2 * 26.7 + 60, 0.2) and r11["einstiche"] == 2 + 3, r11["felder"]
assert sw.aus_position(dict(sw.lesen(None), quelle=sw.QUELLE), alt_p, RE) == (dict(sw.lesen(None), quelle=sw.QUELLE),
                                                                                False)       # Rechner bleibt
d11 = SchneidwegDialog(s, dict(alt_p, naht_vorgabe=naht_.FEST, naht_winkel=93.0, naht_quelle="Kunde"), RE, s.kopf,
                       s.k, s.tabellen, db, [])
assert d11.tabelle.rowCount() == 2 and d11.gravur.value() == 58 and d11.step_info.isVisibleTo(d11)
assert "vor Version" in d11.step_info.text() and "gemessen 193,1" in d11.gemessen_text["a"].text()
assert nah(d11.ergebnis["schneidweg"], r11["schneidweg"], 0.05)
# Rechteckrohr: Naht und Seite nur 0°/90°/180°/270°; 93° wird als 90° angezeigt, ohne Änderung nichts gespeichert
assert [d11.naht_winkel.itemText(i) for i in range(d11.naht_winkel.count())] == list(NAHT_WAHL)
assert d11.naht_winkel.currentText().startswith("90°") and d11.naht_geaendert() == {}
seiten = d11.tabelle.cellWidget(0, SEITE_SPALTE)
assert [seiten.itemText(i) for i in range(seiten.count())] == ["0° oben", "90° vorne", "180° unten", "270° hinten"]
assert not seiten.isEditable()
seiten.setCurrentText("270° hinten")
assert d11.eingaben()["konturen"][0]["seite"] == "hinten"
d11.naht_winkel.setCurrentText("180° unten")
assert d11.naht_geaendert() == dict(naht_vorgabe=naht_.FEST, naht_winkel=180.0, naht_quelle="Kunde")
assert d11.skizze.naht == 180.0 and "unten" in d11.naht_info.text()
d11.naht_vorgabe.setCurrentText(naht_.KEINE)
assert d11.naht_geaendert() == dict(naht_vorgabe=None, naht_winkel=None, naht_quelle=None, querschnitt_lage=None)
assert d11.skizze.naht is None and not d11.naht_winkel.isEnabled()
d11.naht_vorgabe.setCurrentText(naht_.FEST)
# Erklärung der Maße: Überschrift und Text je Art der markierten Zeile
d11.tabelle.selectRow(0)
assert d11.tabelle.horizontalHeaderItem(2).text() == "Ø d [mm]" and "Durchmesser" in d11.erklaerung.text()
d11.tabelle.selectRow(1)
assert d11.tabelle.horizontalHeaderItem(2).text() == "Schnittlänge [mm]" and "Hüllmaß" in d11.erklaerung.text()
assert all(d11.tabelle.horizontalHeaderItem(c).toolTip() for c in range(d11.tabelle.columnCount()))
# Rundrohr: Naht frei im Winkel, Seite weiter frei eingebbar
d_rr = SchneidwegDialog(s, dict(alt_p, profil_id="RR 42,4x2,0", konturen=None, b_ende=None), RR, s.kopf, s.k,
                        s.tabellen, db, [])
assert not isinstance(d_rr.naht_winkel, type(d11.naht_winkel))
d_rr.zeile_neu(dict(art="Bohrung", anzahl=1, d=5, seite=45))
assert d_rr.tabelle.cellWidget(0, SEITE_SPALTE).isEditable()
# Skizze: Maße an den Konturen, SN; Zeichnung als PDF
assert not d11.skizze.grab().isNull() and sk.kurz(dict(art="Langloch", l=30, b=10)) == "LL 30 × 10"
assert sk.naht_punkt(sk.Querschnitt(RE), 90) == (30.0, 0.0) and nah(sk.naht_s(sk.Querschnitt(RE), 180), 60 + 40 + 30)
pdf_pfad = tmp / "zeichnung.pdf"
assert d11.zeichnung_pdf(pdf_pfad) == pdf_pfad and pdf_pfad.stat().st_size > 20000
try:                                    # Text prüfen, wo pypdf installiert ist (nicht in der CI)
    from pypdf import PdfReader  # noqa: E402
except ImportError:
    PdfReader = None
if PdfReader is not None:
    text = "\n".join(seite_.extract_text() for seite_ in PdfReader(str(pdf_pfad)).pages)
    for wort in ("Zeichnung", "alt importiert", "RE 60x40x3", "Abwicklung", "Innenkonturen", "Ø 8,5", "Maßstab 1 :",
                 "Gehrung 30°", "Schweißnaht"):
        assert wort in text, wort
assert pdf_pfad.read_bytes().count(b"/Type /Page") - pdf_pfad.read_bytes().count(b"/Type /Pages") == 2
# Übernehmen mit Naht: Felder der Position
pid11 = db.position_neu(a, dict(alt_p, id=None, pos=80))
s.neu_laden()
z11 = next(r for r, x in enumerate(s.positionen) if x["id"] == pid11)


def naht_unten(d):
    d.naht_vorgabe.setCurrentText(naht_.FEST)
    d.naht_winkel.setCurrentText("180° unten")
    return QDialog.Accepted


assert s.schneidweg_berechnen(z11, dialog=naht_unten, ueberschreiben=True)
p11 = next(x for x in db.positionen(a) if x["id"] == pid11)
assert (p11["naht_vorgabe"], p11["naht_winkel"]) == (naht_.FEST, 180.0) and p11["gravur"] == 58
ok("S11 Ältere STEP-Positionen zeigen Enden, Bohrungen, Konturen und Gravur; Naht im Rechner (Rechteckrohr 0/90/180/"
   "270°), Seite nur 0/90/180/270°, Maße je Art erklärt, Zeichnung als PDF")

if step.messprogramm(HIER.parent / "programm") is not None:
    gem = sk01.step_messen([str(HIER / "step_konturen" / "K01_RE60x40x3_Konturen.step")])
    d12 = SchneidwegDialog(sk01, dict(pk, technik=None), sk01.k.profile[pk["profil_id"]], sk01.kopf, sk01.k,
                           sk01.tabellen, db, [], step_lesen=lambda: gem)
    assert d12.aus_position and "vor Version" in d12.step_info.text()
    assert d12.step_knopf.isEnabled() and d12.step_einlesen()
    assert not d12.aus_position and "vor Version" not in d12.step_info.text()
    assert d12.tabelle.rowCount() == len(ek["konturen"]) and nah(d12.ergebnis["schneidweg"], pk["schneidweg"], 0.6)
    assert all(z.get("x") is not None for z in d12.eingaben()["konturen"])
    ok("S11 STEP neu einlesen: Konturen mit Lage und Seite aus der Datei, Schneidweg wie gemessen")

# ------------------------------------------------------------------ S12 Neue Position mit Typ-Abfrage
from rohrlaser import neue_position as np_  # noqa: E402
td = np_.TypDialog(s)
assert list(np_.TYPEN) == ["Rohr / Profil", "Blech / Kantteil", "Zukaufteil", "Leere Zeile"]
td.waehlen(np_.BLECH)
assert td.typ == np_.BLECH and td.result() == QDialog.Accepted
vorher = len(db.positionen(a))
assert s.position_neu() == np_.LEER and len(db.positionen(a)) == vorher + 1      # stumm: leere Zeile wie bisher
aufrufe = []
s.zukauf_schnell, alt_zs = (lambda zeilen=None, blech=True: aufrufe.append(blech) or 1), s.zukauf_schnell
s.blech_neu, alt_bn = (lambda dialog=None: aufrufe.append("Blech-Editor") or True), s.blech_neu
assert s.position_neu(np_.BLECH) == np_.BLECH and s.position_neu(np_.ZUKAUF) == np_.ZUKAUF
assert aufrufe == ["Blech-Editor", False]
s.zukauf_schnell, s.blech_neu = alt_zs, alt_bn
gesehen12 = {}


def rohr_bedienen(d):
    gesehen12["titel"] = d.windowTitle()
    gesehen12["fehler_leer"] = d.kopf_fehler()
    gesehen12["ok_leer"] = d.ok_knopf.isEnabled()
    d.k_artikel.setText("NEU-1")
    d.k_profil.setCurrentText("RE 60x40x3")
    gesehen12["kasten"] = d.kasten and isinstance(d.naht_winkel, QComboBox)
    d.k_laenge.setValue(1200)
    d.k_stueck.setValue(5)
    d.zeile_neu(dict(art="Bohrung", anzahl=2, d=8.5))
    d.naht_vorgabe.setCurrentText(naht_.FEST)
    d.naht_winkel.setCurrentText("90° vorne (rechts)")
    gesehen12["fehler"] = d.kopf_fehler()
    return QDialog.Accepted


vorher = len(db.positionen(a))
assert s.position_neu(np_.ROHR, dialog=rohr_bedienen) == np_.ROHR
neu12 = db.positionen(a)[-1]
assert len(db.positionen(a)) == vorher + 1 and gesehen12["titel"].startswith("Neue Position")
assert gesehen12["fehler_leer"] == ["Teilelänge eingeben."] and not gesehen12["ok_leer"] and gesehen12["kasten"] and gesehen12["fehler"] == []
assert (neu12["artikel"], neu12["profil_id"], neu12["laenge"], neu12["stueck"]) == ("NEU-1", "RE 60x40x3", 1200, 5)
assert neu12["werkstoff_id"] and neu12["einstiche"] >= 2 and neu12["schneidweg"] > 0
assert (neu12["naht_vorgabe"], neu12["naht_winkel"]) == (naht_.FEST, 90.0)
assert sw.lesen(neu12["technik"])["konturen"][0]["d"] == 8.5
assert s.position_neu(np_.ROHR, dialog=lambda d: QDialog.Rejected) is None and len(db.positionen(a)) == vorher + 1
ok("S12 Neue Position: erst Typ (Rohr / Profil, Blech / Kantteil, Zukaufteil, leere Zeile), Rohr im Rechner mit "
   "Kopfzeile (Profilwechsel, Länge Pflicht, Naht, Konturen)")

# ------------------------------------------------------------------ S13 Profilform vorwählen, Profil neu anlegen
from rohrlaser import profil_neu as pn_  # noqa: E402
assert pn_.profil_id("Quadratrohr", 40, None, 3) == "QR 40x40x3" and pn_.profil_id("Rundrohr", 48.3, None, 2.6) == \
    "RR 48,3x2,6" and pn_.profil_id("Rechteckrohr", 60, 40, 3) == "RE 60x40x3"
gesehen13 = {}


def rohr_neues_profil(d):
    d.k_form.setCurrentText("Rechteckrohr")
    liste = [d.k_profil.itemText(i) for i in range(d.k_profil.count())]
    gesehen13["nur_re"] = bool(liste) and all(s.k.profile[x]["form"] == "Rechteckrohr" for x in liste)
    nd = pn_.ProfilNeuDialog(d, d.k.profile, "Rechteckrohr")
    nd.a.setValue(70)
    nd.b.setValue(35)
    nd.wand.setValue(2.5)
    gesehen13["pid"], gesehen13["fehler"] = nd.pid.text(), nd.fehler()
    nd.b.setValue(0)
    gesehen13["ohne_b"] = nd.fehler()
    gesehen13["neu"] = d.profil_neu(dict(nd.werte(), b=35.0, profil_id="RE 70x35x2,5"))
    gesehen13["gewaehlt"] = (d.k_profil.currentText(), d.profil.get("profil_id"), d.k_form.currentText())
    d.k_artikel.setText("NEU-2")
    d.k_laenge.setValue(500)
    return QDialog.Accepted


assert s.position_neu(np_.ROHR, dialog=rohr_neues_profil) == np_.ROHR
assert gesehen13["nur_re"] and gesehen13["pid"] == "RE 70x35x2,5" and gesehen13["fehler"] == "", gesehen13
assert gesehen13["ohne_b"] == "Abmessung B eingeben." and gesehen13["neu"] == "RE 70x35x2,5"
assert gesehen13["gewaehlt"] == ("RE 70x35x2,5", "RE 70x35x2,5", "Rechteckrohr"), gesehen13
pr13 = next(z for z in db.zeilen("profile") if z["profil_id"] == "RE 70x35x2,5")
assert (pr13["form"], pr13["a"], pr13["b"], pr13["wand"]) == ("Rechteckrohr", 70, 35, 2.5)
assert db.positionen(a)[-1]["profil_id"] == "RE 70x35x2,5" and db.positionen(a)[-1]["artikel"] == "NEU-2"
ok("S13 Rohr-Editor: Profilform vorwählen filtert die Profile, fehlendes Profil direkt anlegen (ID aus den Maßen)")

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
