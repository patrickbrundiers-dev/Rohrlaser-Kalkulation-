"""Knickrahmen (Plan K1-1): V-Ausschnitt im Schneidweg-Rechner, gestreckte Länge, Prüfregeln, Zusatzarbeit Knicken.
- K1 Rechenkern: Beispiel aus dem Plan (QR 40 × 40 × 2, Rahmen 500 × 300 außen, 3 Knicke + Stoß): Ausgleich 2,43 mm,
  gestreckte Länge 1592,7 mm, V-Breite 76 mm, Schnittlänge 295,0 mm je Knick, Lage der Knicke; U-Rahmen (offen) und
  Dreieck (β = 120°) gegen eine Kontrollrechnung; Rechteckrohr: b und h nach Stegwand; Fehler bei falschen Eingaben.
- K2 Schneidweg: V-Ausschnitt als Konturart (1 Einstich, Text, Umriss auf drei Wänden), Rundrohr abgelehnt,
  gestreckte Länge und Zahl der Knicke im Ergebnis.
- K3 Dialog: Knopf „Knickrahmen …“ setzt V-Ausschnitte, Gehrung der Enden und Teilelänge; Skizze zeichnet; Knick
  verschieben führt die Schenkel nach (Länge bleibt); Entfernen.
- K4 Angebot: Übernehmen setzt Länge und Zusatzarbeit Knicken (Menge = Knicke), ohne Knicke fällt sie wieder weg.
- K5 Prüfregeln: Schenkel zu kurz, Kontur im Knickbereich, Wand zu dick; ältere Datei bekommt Regeln und Zusatzarbeit.

Aufruf: python tests/test_knickrahmen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import dfm, knickrahmen as kn, schneidweg as sw, skizze as sk  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.05):
    return abs(a - b) <= tol


def fehler(f):
    try:
        f()
    except ValueError as x:
        return str(x)
    raise AssertionError("muss abgelehnt werden")


QR2 = dict(form="Quadratrohr", a=40, b=40, wand=2, profil_id="QR 40x40x2")
RE = dict(form="Rechteckrohr", a=60, b=40, wand=3, profil_id="RE 60x40x3")
RR = dict(form="Rundrohr", a=40, wand=2, profil_id="RR 40x2")

# ------------------------------------------------------------------ K1 Rechenkern
assert nah(kn.ausgleich(90, 2), 4 - math.pi / 2, 1e-9) and nah(kn.ausgleich(90, 2), 2.43, 0.005)
m = kn.v_masse(40, 40, 2, 90)
assert nah(m["w"], 76, 1e-9) and nah(m["laenge"], 80 + 4 * 38 * math.sqrt(2), 1e-9) and nah(m["laenge"], 295.0)
assert nah(kn.v_masse(40, 40, 2, 90, 4)["laenge"], m["laenge"] + 8 * math.pi, 1e-9)       # Freistich an beiden Spitzen
BEISPIEL = dict(schenkel=[500, 300, 500, 300], geschlossen=True, beta=90, steg="unten")
r = kn.rahmen(BEISPIEL, QR2)
v = 4 - math.pi / 2
assert nah(r["laenge"], 1600 - 3 * v, 1e-6) and round(r["laenge"], 1) == 1592.7
assert [round(x["x"], 2) for x in r["knicke"]] == [round(500 - v / 2, 2), round(800 - 1.5 * v, 2),
                                                    round(1300 - 2.5 * v, 2)]
assert r["enden"] == dict(winkel=45.0, richtung=180) and r["stoss"] == 90
assert kn.kurz(r) == "geschlossen, 3 Knicke, gestreckt 1592,7 mm (Ausgleich 2,43 mm je Knick)"
# Knickzugabe: + z je Knick
rz = kn.rahmen(dict(BEISPIEL, z=1.0), QR2)
assert nah(rz["laenge"], r["laenge"] + 3, 1e-6) and "Zugabe 1 mm" in kn.kurz(rz)
# U-Rahmen offen, 2 Knicke: Enden bleiben, Länge = Σ − 2 v
ru = kn.rahmen(dict(schenkel=[200, 400, 200], geschlossen=False, beta=90), QR2)
assert nah(ru["laenge"], 800 - 2 * v, 1e-6) and ru["enden"] is None and len(ru["knicke"]) == 2
# Dreieck β = 120°: Stoß 120°, Enden 60°, v nach DIN 6935 (φ > 90°: 2 (r + s) − π φ/180 (r + k s))
rd = kn.rahmen(dict(schenkel=[300, 300, 300], geschlossen=True, beta=120), QR2)
vd = 2 * 2 - math.pi * 120 / 180 * (0.5 * 2)
assert nah(rd["laenge"], 900 - 2 * vd, 1e-6) and rd["enden"]["winkel"] == 60 and rd["stoss"] == 120
assert nah(rd["knicke"][0]["w"], 2 * 38 * math.tan(math.radians(60)), 1e-9)
assert nah(rd["knicke"][0]["laenge"], 80 + 4 * 38 / math.cos(math.radians(60)), 1e-9)
# Rechteckrohr 60 × 40: Stegwand unten -> b = 60 (Breitseite), h = 40; Stegwand vorne -> b = 40, h = 60
assert kn.querschnitt(RE, "unten") == (60, 40, 3) and kn.querschnitt(RE, "vorne") == (40, 60, 3)
rv = kn.rahmen(dict(BEISPIEL, steg="vorne"), RE)
assert rv["enden"]["richtung"] == 90 and nah(rv["knicke"][0]["laenge"], 2 * 40 + 4 * 57 * math.sqrt(2), 1e-9)
# Fehler
assert "nur bei Quadrat- und Rechteckrohr" in fehler(lambda: kn.rahmen(BEISPIEL, RR))
assert "zwei Schenkel" in fehler(lambda: kn.rahmen(dict(schenkel=[500]), QR2))
assert "schließen keinen Rahmen" in fehler(lambda: kn.rahmen(dict(BEISPIEL, beta=45), QR2))
assert "Schenkel 2 ist kürzer" in fehler(lambda: kn.rahmen(dict(BEISPIEL, schenkel=[500, 60, 500, 300]), QR2))
assert "3 Knickwinkel erwartet" in fehler(lambda: kn.rahmen(dict(BEISPIEL, beta=[90, 90]), QR2))
# V darf nicht über das Ende hinaus (offen: x − w/2 ≥ 0; geschlossen: auch nicht in die Gehrung des Stoßes)
assert "Schenkel 1 ist kürzer" in fehler(lambda: kn.rahmen(dict(schenkel=[30, 300, 200], beta=90), QR2))
assert "Schenkel 3 ist kürzer" in fehler(lambda: kn.rahmen(dict(schenkel=[200, 300, 30], beta=90), QR2))
kn.rahmen(dict(schenkel=[40, 300, 200], beta=90), QR2)                  # offen: 40 − 1,2 − 38 ≥ 0
assert "Schenkel 1 ist kürzer" in fehler(lambda: kn.rahmen(dict(BEISPIEL, schenkel=[70, 300, 500, 300]), QR2))
ok("K1 Rechenkern: Beispiel 1592,7 mm, V 76 mm / 295,0 mm, Lage der Knicke, U-Rahmen, Dreieck, Rechteckrohr")

# ------------------------------------------------------------------ K2 Schneidweg-Rechner
eing, r = kn.anwenden(dict(a={}, b={}, konturen=[dict(art="Bohrung", anzahl=2, d=8, x=200)]), BEISPIEL, QR2)
assert [z["art"] for z in eing["konturen"]] == ["Bohrung"] + [sw.V_AUSSCHNITT] * 3
assert eing["a"] == eing["b"] == dict(winkel=45.0, achse=sw.ACHSEN[0], richtung=180)
erg = sw.rechnen(eing, QR2, (10, 50))
assert not erg["fehler"] and erg["laenge"] == 1592.7 and erg["knicke"] == 3
vs = [s for s in erg["schritte"] if s.get("art") == sw.V_AUSSCHNITT]
assert len(vs) == 3 and all(nah(s["laenge"], 295.0) and s["einstiche"] == 1 and s["klasse"] == "groß" for s in vs)
assert vs[0]["text"].startswith("1 × V-Ausschnitt β 90°, Steg unten bei x = 498,8"), vs[0]["text"]
assert erg["einstiche"] == 2 + 2 + 3                    # je Ende 1 Einstich, 2 Bohrungen, 3 V
assert "Knickrahmen: geschlossen, 3 Knicke" in erg["hinweise"][0] and "Stoß schweißen" in erg["hinweise"][1]
# Umriss auf drei Wänden: Innenwand oben (gegenüber der Stegwand unten), Spitzen auf vorne/hinten
z = sw.v_ergaenzen(eing, QR2)["konturen"][1]
qs = sk.Querschnitt(QR2)
seiten = {sk.s_zu_seite(qs, sk.s_lage(qs, z, ds) % qs.umfang)[0] for _, ds in z["umriss"]}
assert seiten == {"oben", "vorne", "hinten"}, seiten
umfang = sum(math.dist(z["umriss"][i], z["umriss"][(i + 1) % len(z["umriss"])]) for i in range(len(z["umriss"])))
assert nah(umfang, 295.0, 0.05)
# Rundrohr: V-Ausschnitt abgelehnt; V von Hand ohne Block: kein Längen-Ergebnis
assert "nur bei Quadrat- und Rechteckrohr" in sw.rechnen(eing, RR, (10, 50))["fehler"][0]
hand = sw.rechnen(dict(a={}, b={}, konturen=[dict(art=sw.V_AUSSCHNITT, anzahl=2, beta=90, x=300, abstand=200)]),
                  QR2, (10, 50))
assert not hand["fehler"] and hand["laenge"] is None and hand["knicke"] == 2 and nah(hand["felder"]["innen"], 589.9)
# V-Ausschnitte von Hand geändert: passt nicht mehr zu den Schenkeln -> Fehler statt falscher Länge
geaendert = dict(eing, konturen=[dict(z, beta=80) if z.get("knick") == 2 else z for z in eing["konturen"]])
assert "von Hand geändert" in " ".join(sw.rechnen(geaendert, QR2, (10, 50))["fehler"])
weniger = dict(eing, konturen=[z for z in eing["konturen"] if z.get("knick") != 3])
assert "von Hand geändert" in " ".join(sw.rechnen(weniger, QR2, (10, 50))["fehler"])
# geschlossen -> offen: Gehrung des Stoßes fällt weg; Entfernen nimmt Block, V-Ausschnitte und Gehrung heraus
offen, ro = kn.anwenden(eing, dict(BEISPIEL, geschlossen=False), QR2)
assert ro["enden"] is None and offen["a"] == offen["b"] == {} and len(offen["konturen"]) == 4
weg, _ = kn.anwenden(eing, None, QR2)
assert "knickrahmen" not in weg and [z["art"] for z in weg["konturen"]] == ["Bohrung"] and weg["a"] == {}
ok("K2 Schneidweg: V-Ausschnitt 1 Einstich, Umriss auf drei Wänden, gestreckte Länge, Rundrohr abgelehnt")

# ------------------------------------------------------------------ K3 Dialog
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from rohrlaser.knickrahmen_dialog import KnickrahmenDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

fenster = Hauptfenster(db, HIER.parent / "programm", stumm=True)
a = db.angebot_neu(dict(kunde="Test"))
db.position_neu(a, dict(pos=10, artikel="Rahmen", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1500,
                        stueck=2))
seite = fenster.angebot_oeffnen(a)
p = db.positionen(a)[0]
QR3 = seite.k.profile["QR 40x40x3"]
d = SchneidwegDialog(seite, p, QR3, seite.kopf, seite.k, seite.tabellen, db)
assert d.knick_knopf.isEnabled()


def bedienen(k):
    assert not k.ok_knopf.isEnabled()            # leer: keine Schenkel
    k.schenkel.setText("500; 300; 500; 300")
    assert k.ok_knopf.isEnabled() and "gestreckt" in k.vorschau.text() and "Gehrung 45°" in k.vorschau.text()
    k.schenkel.setText("500; 300; x")
    assert not k.ok_knopf.isEnabled() and "als Zahlen" in k.vorschau.text()
    k.schenkel.setText("500; 300; 500; 300")
    return QDialog.Accepted


assert d.knickrahmen(dialog=bedienen)
v3 = kn.ausgleich(90, 3)
L3 = round(1600 - 3 * v3, 1)
eing = d.eingaben()
assert eing["knickrahmen"]["schenkel"] == [500, 300, 500, 300] and d.p["laenge"] == L3
assert [z["art"] for z in eing["konturen"]] == [sw.V_AUSSCHNITT] * 3 and all(z.get("umriss") for z in eing["konturen"])
assert d.winkel["a"].value() == 45 and d.richtung["b"].currentText() == "länger unten (180°)"
assert d.ergebnis["laenge"] == L3 and not d.ergebnis["fehler"] and d.ok_knopf.isEnabled()
d.skizze.resize(900, 400)
d.skizze.bild(900, 400)                       # V-Ausschnitte über drei Wände zeichnen ohne Fehler
# Knick verschieben (Teile-Editor, Tabelle): die Schenkel folgen, die gestreckte Länge bleibt, kein Fehler
neu = d.eingaben()
x2 = sorted(z["x"] for z in neu["konturen"])[1]
for z in neu["konturen"]:
    if z["x"] == x2:
        z["x"] = x2 + 20
d.eingaben_setzen(neu, mit_messung=True)
d.rechnen()
eing = d.eingaben()
assert [round(a_, 1) for a_ in eing["knickrahmen"]["schenkel"]] == [500, 320, 480, 300], eing["knickrahmen"]
assert d.ergebnis["laenge"] == L3 and not d.ergebnis["fehler"], d.ergebnis["fehler"]
assert kn.nachfuehren(eing, QR3) is None                  # passt jetzt
zwei = dict(eing, konturen=eing["konturen"][:2])           # Knick gelöscht: nicht nachführbar, Fehler bleibt
assert kn.nachfuehren(zwei, QR3) is None and sw.rechnen(zwei, QR3, (10, 50))["fehler"]
neu = d.eingaben()
for z in neu["konturen"]:
    if z["x"] == x2 + 20:
        z["x"] = x2
d.eingaben_setzen(neu, mit_messung=True)
assert [round(a_, 1) for a_ in d.eingaben()["knickrahmen"]["schenkel"]] == [500, 300, 500, 300]
# erneut öffnen: Dialog zeigt den Block; Entfernen nimmt Block und V-Ausschnitte heraus
k = KnickrahmenDialog(d, QR3, d.knick)
assert k.schenkel.text() == "500; 300; 500; 300" and k.geschlossen.isChecked()
assert d.knickrahmen(werte={})
assert "knickrahmen" not in d.eingaben() and not d.eingaben()["konturen"]
ok("K3 Dialog: Knickrahmen setzt V-Ausschnitte, Enden und Länge, Skizze, Entfernen")

# ------------------------------------------------------------------ K4 Angebot: Übernehmen
katalog = db.zeilen("zusatzarbeiten")
assert any(z["name"] == kn.ZUSATZ_KNICKEN and z["art"] == "€/Stück" and z["preis"] == 2.0 for z in katalog)
eing, _ = kn.anwenden(dict(a={}, b={}, konturen=[]), BEISPIEL, QR3)
assert seite.schneidweg_berechnen(0, eingaben=eing, ueberschreiben=True)
p = db.positionen(a)[0]
assert p["laenge"] == L3 and p["einstiche"] == 2 + 3
(zu,) = json.loads(p["zusatz"])
assert zu["name"] == "Knicken" and zu["menge"] == 3 and zu["quelle"] == sw.QUELLE and zu["stand"]["preis"] == 2.0
assert sw.lesen(p["technik"])["knickrahmen"]["schenkel"] == [500, 300, 500, 300]
# ohne Knickrahmen: Zusatzarbeit aus dem Rechner fällt weg, Länge bleibt
assert seite.schneidweg_berechnen(0, eingaben=dict(a={}, b={}, konturen=[]), ueberschreiben=True)
p = db.positionen(a)[0]
assert not p.get("zusatz") and p["laenge"] == L3
ok("K4 Angebot: Länge gestreckt, Zusatzarbeit Knicken × 3, wieder entfernt")

# ------------------------------------------------------------------ K5 Prüfregeln
QR5 = dict(form="Quadratrohr", a=40, b=40, wand=5, profil_id="QR 40x40x5")
e5, r5 = kn.anwenden(dict(a={}, b={}, konturen=[dict(art="Bohrung", anzahl=1, d=8, x=520)]),
                     dict(BEISPIEL, schenkel=[500, 79, 500, 300]), QR5)
p5 = dict(technik=sw.speichern(e5), laenge=round(r5["laenge"], 1))
befunde = {b.regel: b for b in dfm.rohr(p5, QR5)}
assert "kürzester Schenkel 2 mit 79 mm" in befunde[dfm.SCHENKEL_KURZ].text
assert befunde[dfm.KNICKBEREICH].zeilen == (0,) and "bei x = 520 mm" in befunde[dfm.KNICKBEREICH].text
assert befunde[dfm.KNICK_WAND].stufe == dfm.HINWEIS
p_ok = dict(technik=sw.speichern(kn.anwenden(dict(a={}, b={}, konturen=[]), BEISPIEL, QR2)[0]), laenge=1592.7)
assert not {b.regel for b in dfm.rohr(p_ok, QR2)} & set(dfm.KNICK_REGELN)
aus = [dict(regel=r_, aktiv="nein") for r_ in dfm.KNICK_REGELN]
assert not {b.regel for b in dfm.rohr(p5, QR5, zeilen=aus)} & set(dfm.KNICK_REGELN)
assert set(dfm.KNICK_REGELN) <= {z["regel"] for z in db.zeilen("pruefregeln")}
# ältere Datei: Zusatzarbeit und Regeln fehlen, Stand fehlt -> ergänzt
fenster.close()
db.con.execute("DELETE FROM zusatzarbeiten WHERE name='Knicken'")
db.con.execute(f"DELETE FROM pruefregeln WHERE regel IN ({','.join('?' * len(dfm.KNICK_REGELN))})", dfm.KNICK_REGELN)
db.con.execute("DELETE FROM einstellungen WHERE name='knick_stand'")
db.con.commit()
db.schliessen()
db = Datenbank(tmp / "rohrlaser.db")
assert any(z["name"] == "Knicken" for z in db.zeilen("zusatzarbeiten"))
assert set(dfm.KNICK_REGELN) <= {z["regel"] for z in db.zeilen("pruefregeln")}
assert db.einstellung("knick_k") == 0.5 and db.einstellung("knick_z") == 0
db.schliessen()
ok("K5 Prüfregeln: Schenkel zu kurz, Kontur im Knickbereich, Wand zu dick, abschaltbar; ältere Datei ergänzt")

# ------------------------------------------------------------------ K6 Freistich nimmt Material weg (Patrick 24.10.)
def _kreuzen(pk):
    n = len(pk)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            p, q, r_, s_ = pk[i], pk[(i + 1) % n], pk[j], pk[(j + 1) % n]
            d = (q[0] - p[0]) * (s_[1] - r_[1]) - (q[1] - p[1]) * (s_[0] - r_[0])
            if abs(d) < 1e-12:
                continue
            u = ((r_[0] - p[0]) * (s_[1] - r_[1]) - (r_[1] - p[1]) * (s_[0] - r_[0])) / d
            w = ((r_[0] - p[0]) * (q[1] - p[1]) - (r_[1] - p[1]) * (q[0] - p[0])) / d
            if 1e-9 < u < 1 - 1e-9 and 1e-9 < w < 1 - 1e-9:
                return True
    return False


def _flaeche(pk):
    return abs(sum(pk[i][0] * pk[i - 1][1] - pk[i - 1][0] * pk[i][1] for i in range(len(pk)))) / 2


ohne, mit = kn.v_umriss(40, 40, 2, 90), kn.v_umriss(40, 40, 2, 90, 8)
assert not _kreuzen(mit), "Umriss mit Freistich darf sich nicht selbst kreuzen (sonst bleibt Material stehen)"
assert _flaeche(mit) > _flaeche(ohne) + 2 * 0.5 * math.pi * 16          # mindestens die äußeren Halbkreise mehr
assert max(y for _, y in mit) > max(y for _, y in ohne) + 3.9             # Kreis reicht über die Spitze hinaus
ok("K6 Freistich: Umriss läuft außen um den Kreis, nimmt Material weg statt es stehen zu lassen")

# ------------------------------------------------------------------ K7 keine Längslinien „Mit Kanten“ (Patrick 24.10.)
from rohrlaser import rohr3d  # noqa: E402
from rohrlaser.ansicht3d import Ansicht3D  # noqa: E402

qr50 = dict(QR3, a=50, b=50, wand=4)
netz = rohr3d.netz(dict(a={}, b={}, konturen=[kn.zeile_ergaenzen(dict(art=sw.V_AUSSCHNITT, anzahl=1, beta=90,
                                                                       freistich=8, x=300, seite="oben"), qr50)]),
                   qr50, 600)
P = netz["p"]
for wand in ("A", "I"):
    t = netz["t"][wand]
    seiten = {}
    for j in range(0, len(t), 3):
        ecken = [tuple(P[3 * t[j + q] + c] for c in range(3)) for q in range(3)]
        for q in range(3):
            a_, b_ = ecken[q], ecken[(q + 1) % 3]
            seiten[(a_, b_) if a_ < b_ else (b_, a_)] = seiten.get((a_, b_) if a_ < b_ else (b_, a_), 0) + 1
    laengs = [k_ for k_, n_ in seiten.items() if n_ == 1 and abs(k_[0][0] - k_[1][0]) < 1e-6
              and abs(k_[0][1] - k_[1][1]) < 1e-6 and abs(k_[0][2] - k_[1][2]) > 1]
    assert not laengs, f"{wand}: {len(laengs)} offene Längskanten (T-Stöße zwischen den Spalten)"
a3 = Ansicht3D()
a3.setzen(netz)
assert len(a3.modell.kanten()) < 1500
ok("K7 Wand mit V-Ausschnitt ohne T-Stöße: „Mit Kanten“ zeigt keine Längslinien über das ganze Rohr")
print("Alle Knickrahmen-Tests bestanden.")
