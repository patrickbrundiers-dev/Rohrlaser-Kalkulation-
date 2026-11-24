"""Ausklinkung mit einstellbarer Tiefe (CAD-Entwicklungsplan Paket 4, Patrick 12.11.2026: „wie eine Ausklinkung, wo
die Tiefe eingestellt werden kann“). Die acht Testfälle aus Abschnitt 7.4 des Plans; geprüft werden die tatsächlich
erzeugte Tiefe (am 3D-Körper gemessen), die Richtung, ein gültiger Körper, keine Änderung anderer Konturen und Teile,
Vorschau und Fehlermeldungen.

T1 Rechteckiger Ausschnitt mit 5 mm Tiefe: Seitenwände 5 mm tief, kein Durchbruch
T2 Runder Ausschnitt mit 10 mm Tiefe (Rundrohr)
T3 Ausschnitt mit umgekehrter Richtung (von der Gegenseite)
T4 Vollständiger Durchbruch: erst ab der ganzen Profilhöhe, dann beide Wände
T5 Ausschnitt nahe einer Bauteilkante: Hinweis, kein Seitenwandschnitt; Blech: Ausklinkung an der Ecke
T6 Schräge Fläche: Rundrohr unter 135°, gedrehte Kontur; Schnittfläche am Ende wird abgelehnt
T7 Ungültige oder offene Kontur
T8 Geometrisch nicht ausführbar: Tasche in der Wand, Ende in der Gegenwand, Teil getrennt, Sackloch im Vollmaterial
T9 Blech-Editor: Ausklinkung an der Kante mit Tiefe (auch über die Biegelinie eines Kantteils), Vorschau, Rückgängig
T10 Rohr-Editor: Knopf, Eigenschaften, Vorschau im 3D, Fläche aus der 3D-Auswahl, Kontur umwandeln, Rückgängig

Aufruf: python tests/test_ausschnitt_tiefe.py
"""
import copy
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialogButtonBox  # noqa: E402

from rohrlaser import ausschnitt, auswahl3d as aw, blech, blech3d, editor_ausschnitt as ea, rohr3d  # noqa: E402
from rohrlaser import schneidweg as sw, skizze as sk  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(t):
    print("OK    ", t)


def nah(a, b, tol=0.02):
    return abs(a - b) <= tol


RR = dict(form="Rechteckrohr", a=60, b=40, wand=3)
RU = dict(form="Rundrohr", a=60, wand=3)
UP = dict(form="U-Profil", a=80, b=45, wand=6)
FL = dict(form="Flachstahl", a=50, wand=8)
L = 300


def zeile(**k):
    return dict(dict(art=sw.AUSSCHNITT, anzahl=1, x=150), **k)


def fertig(profil, **k):
    return sw.ausschnitt_ergaenzen(zeile(**k), profil)


def fehler(profil, **k):
    z = fertig(profil, **k)
    assert z.get("fehler_as") and not z.get("umriss") and not z.get("laenge_as"), z
    erg = sw.rechnen(dict(a={}, b={}, konturen=[zeile(**k)]), profil, (10, 50), laenge=L)
    assert any(z["fehler_as"] in f for f in erg["fehler"]), erg["fehler"]       # der Rechner meldet den Grund
    return z["fehler_as"]


def netz(profil, *zeilen):
    e = sw.v_ergaenzen(dict(a={}, b={}, laenge=L, konturen=list(zeilen)), profil)
    return rohr3d.netz(e, profil, L)


def flaeche(n, art):
    p, t, s = n["p"], n["t"].get(art, []), 0.0
    for i in range(0, len(t), 3):
        a, b, c = (p[3 * k:3 * k + 3] for k in t[i:i + 3])
        u, v = [b[j] - a[j] for j in range(3)], [c[j] - a[j] for j in range(3)]
        s += 0.5 * math.sqrt((u[1] * v[2] - u[2] * v[1]) ** 2 + (u[2] * v[0] - u[0] * v[2]) ** 2
                             + (u[0] * v[1] - u[1] * v[0]) ** 2)
    return s


def rand(n):
    """Punkte (u, v, x) der Lochränder im 3D-Modell (Linien der Innenkonturen, Modell = (−u, v, x))."""
    return [(-z[i], z[i + 1], z[i + 2]) for z in n["l"].get("K", []) for i in range(0, len(z), 3)]


def rand_rund(n, r):
    """Lochränder am Rundrohr auf dem Außenradius r (die Linien liegen zur Sichtbarkeit knapp darüber)."""
    return [(u * r / math.hypot(u, v), v * r / math.hypot(u, v), x) for u, v, x in rand(n)]


def koerper_gueltig(n):
    """Jedes Dreieck hat drei verschiedene, vorhandene Punkte und alle Koordinaten sind Zahlen."""
    anz = len(n["p"]) // 3
    assert all(math.isfinite(c) for c in n["p"])
    for t in n["t"].values():
        assert len(t) % 3 == 0 and all(0 <= k < anz for k in t)
    return True


LEER = netz(RR)
LEER_RU = netz(RU)

# ------------------------------------------------------------------ T1 Rechteck 5 mm tief
z = fertig(RR, b=30, h=70, tiefe=5, seite="oben")
dq = [q for _, q in z["umriss"]]
assert nah(min(dq), -35) and nah(max(dq), 35), dq                # 60 mm Fläche + je 5 mm die Seitenwand hinunter
assert z["tiefe_ist"] == 5.0 and nah(z["laenge_as"], 200) and nah(z["huelle_as"], 70)
assert z.get("wand") != "beide" and not z.get("kopien")           # 5 mm werden nie von selbst zum Durchbruch
z60 = fertig(RR, b=30, h=60, tiefe=5, seite="oben")               # genau so breit wie die Fläche: gleiche Ausklinkung
assert z60["umriss"] == z["umriss"]
erg = sw.rechnen(dict(a={}, b={}, konturen=[zeile(b=30, h=70, tiefe=5, seite="oben")]), RR, (10, 50), laenge=L)
schritt = erg["schritte"][-1]
assert schritt["anzahl"] == 1 and nah(schritt["laenge"], 200) and "5 mm tief" in schritt["text"], schritt
assert not erg["fehler"]
n1 = netz(RR, zeile(b=30, h=70, tiefe=5, seite="oben"))
assert koerper_gueltig(n1)
pk = rand(n1)
# tatsächliche Tiefe 5 mm: die Unterkante liegt hier noch im Eckradius des Rohrs (dort auf dem Bogen, ≤ 0,1 mm)
assert pk and nah(min(v for _, v, _ in pk), 20 - 5, 0.1), min(v for _, v, _ in pk)
pk10 = rand(netz(RR, zeile(b=30, h=70, tiefe=10, seite="oben")))                 # unter dem Eckradius: genau
assert nah(min(v for _, v, _ in pk10), 20 - 10, 0.005), min(v for _, v, _ in pk10)
assert nah(min(x for *_, x in pk), 135, 0.05) and nah(max(x for *_, x in pk), 165, 0.05)
weg = flaeche(LEER, "A") - flaeche(n1, "A")
assert 0.85 * 30 * 70 < weg <= 30 * 70 + 1, weg                    # Außenwand um den Ausschnitt kleiner (Eckradius)
assert any(len(zug) >= 6 for zug in n1["l"].get("HK", []))         # Vorschau: Kontur auf der Fläche und in der Tiefe
vorschau = [(-zz[i], zz[i + 1], zz[i + 2]) for zz in n1["l"]["HK"] for i in range(0, len(zz), 3)]
assert nah(min(v for _, v, _ in vorschau), 15, 1e-6) and nah(max(v for _, v, _ in vorschau), 20, 1e-6)
ok("T1 Rechteck 5 mm tief: Seitenwände genau 5 mm, Schnittlänge 200 mm, kein Durchbruch, Vorschau zeigt die Tiefe")

# ------------------------------------------------------------------ T2 rund 10 mm tief
z = fertig(RU, kontur_form="Rund", b=60, tiefe=10, seite="oben (0°)")
grenze = 30 * math.acos(1 - 10 / 30)                              # Bogen bis 10 mm unter dem Scheitel
dq = [q for _, q in z["umriss"]]
assert nah(max(dq), grenze, 0.05) and nah(min(dq), -grenze, 0.05), (max(dq), grenze)
assert z["tiefe_ist"] == 10.0 and not z.get("kopien")
n2 = netz(RU, zeile(kontur_form="Rund", b=60, tiefe=10, seite="oben (0°)"))
assert koerper_gueltig(n2)
pk = rand_rund(n2, 30)
assert nah(min(v for _, v, _ in pk), 30 - 10, 0.01), min(v for _, v, _ in pk)
assert flaeche(LEER_RU, "A") - flaeche(n2, "A") > 1500
klein = fertig(RU, kontur_form="Rund", b=20, tiefe=10, seite="oben (0°)")        # schmale Kontur: nur ein Loch
assert klein["tiefe_ist"] == 3.0 and "nur so tief, wie die Kontur breit ist" in klein["hinweis_as"][0]
rund_rr = fertig(RR, kontur_form="Rund", b=70, tiefe=10, seite="oben")           # rund auf dem Rechteckrohr
assert nah(max(q for _, q in rund_rr["umriss"]), 40) and rund_rr["tiefe_ist"] == 10.0
ok("T2 rund 10 mm tief: Rundrohr bis 10 mm unter dem Scheitel, am 3D-Körper gemessen; schmale Kontur mit Hinweis")

# ------------------------------------------------------------------ T3 umgekehrte Richtung
n3 = netz(RR, zeile(b=30, h=70, tiefe=5, seite="oben", umgekehrt=True))
pk = rand(n3)
assert pk and nah(max(v for _, v, _ in pk), -20 + 5, 0.1), max(v for _, v, _ in pk)     # von unten 5 mm hinauf
assert koerper_gueltig(n3)
z = fertig(RR, b=30, h=70, tiefe=5, seite="oben", umgekehrt=True)
assert z["tiefe_ist"] == 5.0 and nah(z["laenge_as"], 200)
assert "von der Gegenseite" in sw.ausschnitt_text(z)
n3r = netz(RU, zeile(kontur_form="Rund", b=60, tiefe=10, seite="oben (0°)", umgekehrt=True))
assert nah(max(v for _, v, _ in rand_rund(n3r, 30)), -30 + 10, 0.01)
vorschau = [(-zz[i], zz[i + 1], zz[i + 2]) for zz in n3["l"]["HK"] for i in range(0, len(zz), 3)]
assert nah(min(v for _, v, _ in vorschau), -20, 1e-6) and nah(max(v for _, v, _ in vorschau), -15, 1e-6)
ok("T3 umgekehrte Richtung: gleiche Kontur, geschnitten von der Gegenseite, Tiefe 5 bzw. 10 mm von dort")

# ------------------------------------------------------------------ T4 vollständiger Durchbruch
z = fertig(RR, b=30, h=20, tiefe=40, seite="oben")
assert z["wand"] == "beide" and z["kopien"] == [dict(seite="unten", q=None, spiegeln=True)] and z["tiefe_ist"] == 40.0
erg = sw.rechnen(dict(a={}, b={}, konturen=[zeile(b=30, h=20, tiefe=40, seite="oben")]), RR, (10, 50), laenge=L)
schritt = erg["schritte"][-1]
assert schritt["anzahl"] == 2 and "vollständiger Durchbruch" in schritt["text"] and nah(schritt["laenge"], 200)
n4 = netz(RR, zeile(b=30, h=20, tiefe=40, seite="oben"))
vs = [v for _, v, _ in rand(n4)]
assert nah(max(vs), 20, 0.5) and nah(min(vs), -20, 0.5)            # Loch in beiden Wänden
for t in (5, 20, 37, 38, 39.9):                                    # darunter nie ein Durchbruch
    zz = fertig(RR, b=30, h=20, tiefe=t, seite="oben")
    assert zz.get("wand") != "beide" and not zz.get("kopien") and zz["tiefe_ist"] == 3.0, (t, zz)
seitlich = fertig(RR, b=30, h=40, q=15, tiefe=40, seite="oben")    # über eine Kante: um die Seitenwand herum
dq = [q for _, q in seitlich["umriss"]]
assert nah(min(dq), -20) and nah(max(dq), 90) and nah(seitlich["laenge_as"], 280) and not seitlich.get("kopien")
rund = fertig(RU, kontur_form="Rund", b=20, tiefe=60, seite="oben (0°)")
assert rund["wand"] == "beide" and len(rund["kopien"]) == 1
ok("T4 vollständiger Durchbruch erst ab der ganzen Höhe (beide Wände, zählt doppelt); darunter bleibt die Gegenwand")

# ------------------------------------------------------------------ T5 nahe einer Bauteilkante
z = fertig(RR, b=30, h=20, q=17, tiefe=5, seite="oben")            # Rest zur Kante 3 mm
assert z["tiefe_ist"] == 3.0 and nah(max(q for _, q in z["umriss"]), 10) and "Rest 3 mm" in z["hinweis_as"][0]
assert "ausreißen" not in z["hinweis_as"][0]
z = fertig(RR, b=30, h=20, q=18.5, tiefe=5, seite="oben")          # Rest 1,5 mm: schmaler als die Wand
assert "Rest 1,5 mm" in z["hinweis_as"][0] and "ausreißen" in z["hinweis_as"][0]
erg = sw.rechnen(dict(a={}, b={}, konturen=[zeile(b=30, h=20, q=18.5, tiefe=5, seite="oben")]), RR, (10, 50), laenge=L)
assert any("ausreißen" in h for h in erg["hinweise"]), erg["hinweise"]
z = fertig(RR, b=30, h=20, q=20, tiefe=5, seite="oben")            # erreicht die Kante: Seitenwand 5 mm
assert z["tiefe_ist"] == 5.0 and nah(max(q for _, q in z["umriss"]) + 20, 35) and not z.get("hinweis_as")
blech_r = [(0, 0), (200, 0), (200, 100), (0, 100)]
ecke = ausschnitt.blech_ausklinkung(blech_r, "unten", 5, 30, 12)   # ragt über die Ecke: Eckausklinkung
assert ecke == [(0.0, 12.0), (20.0, 12.0), (20.0, 0.0), (200.0, 0.0), (200.0, 100.0), (0.0, 100.0)], ecke
ok("T5 nahe der Kante: ohne Kante nur diese Wand (Hinweis mit Reststeg), an der Kante mit Seitenwand; Blech-Ecke")

# ------------------------------------------------------------------ T6 schräge Fläche
z = fertig(RU, kontur_form="Rechteck", b=30, h=70, tiefe=12, seite=135)
assert z["tiefe_ist"] == 12.0
n6 = netz(RU, zeile(kontur_form="Rechteck", b=30, h=70, tiefe=12, seite=135))
nu, nv = math.sin(math.radians(135)), math.cos(math.radians(135))
tiefen = [30 - (u * nu + v * nv) for u, v, _ in rand_rund(n6, 30)]
assert nah(max(tiefen), 12, 0.01) and min(tiefen) > -0.01, (min(tiefen), max(tiefen))   # 12 mm senkrecht zur Fläche
gedreht = fertig(RR, b=40, h=20, drehung=30, tiefe=5, seite="oben")
dq = [q for _, q in gedreht["umriss"]]
assert nah(max(dq), 20 * math.sin(math.radians(30)) + 10 * math.cos(math.radians(30)), 0.01) and len(dq) == 4
quer = fertig(RR, b=40, h=20, drehung=90, tiefe=5, seite="oben")   # quer: jetzt 40 breit, bleibt in der Fläche
assert nah(max(q for _, q in quer["umriss"]), 20) and quer["tiefe_ist"] == 3.0
schraeg = fertig(RR, b=80, h=20, drehung=60, tiefe=5, seite="oben")      # schräg über beide Kanten
dq = [q for _, q in schraeg["umriss"]]
assert nah(max(dq), 35) and nah(min(dq), -35) and schraeg["tiefe_ist"] == 5.0
qs_rr = sk.Querschnitt(RR)
stirn = [(-30.0, 20.0, 0.0), (30.0, 20.0, 0.0), (30.0, -20.0, 0.0)]         # Schnittfläche am Ende A
try:
    ausschnitt.flaeche_zu_seite(qs_rr, stirn)
    raise AssertionError("Schnittfläche darf keine Fläche für den Ausschnitt sein")
except ValueError as f:
    assert "keine Außenfläche" in str(f)
assert ausschnitt.flaeche_zu_seite(qs_rr, [(-30.0, 5.0, 100.0), (-30.0, 15.0, 100.0), (-30.0, 10.0, 140.0)]) \
    == ("vorne", 113.3, -10.0)
ok("T6 schräge Fläche: Rundrohr unter 135° (Tiefe senkrecht zur Fläche), gedrehte Kontur; Schnittfläche abgelehnt")

# ------------------------------------------------------------------ T7 ungültige oder offene Kontur
assert "offen" in fehler(RR, kontur_form="Polygon", eckpunkte="0,0; 40,0", tiefe=5, seite="oben")
assert "schneidet sich selbst" in fehler(RR, kontur_form="Polygon", eckpunkte="0,0; 40,0; 0,30; 40,30", tiefe=5,
                                         seite="oben")
assert "keine Fläche" in fehler(RR, kontur_form="Polygon", eckpunkte="0,0; 20,0; 40,0", tiefe=5, seite="oben")
assert "nicht lesbar" in fehler(RR, kontur_form="Polygon", eckpunkte="0,0; abc", tiefe=5, seite="oben")
assert "Tiefe (Maß 3)" in fehler(RR, b=30, h=70, seite="oben")
assert "Länge längs" in fehler(RR, b=30, tiefe=5, seite="oben")
assert "Eckradius höchstens" in fehler(RR, b=30, h=20, eckradius=12, tiefe=5, seite="oben")
gut = fertig(RR, kontur_form="Polygon", eckpunkte="0,0; 40,0; 40,70; 0,70; 0,0", tiefe=5, seite="oben")
assert nah(gut["laenge_as"], 2 * 40 + 2 * 70 + 0) and gut["tiefe_ist"] == 5.0     # geschlossen angegeben ist gültig
try:
    ausschnitt.blech_ausklinkung([(0, 0), (100, 0)], "unten", 50, 20, 5)
    raise AssertionError("offene Außenkontur")
except ValueError as f:
    assert "offen" in str(f)
ok("T7 ungültige oder offene Kontur: zu wenige Punkte, Selbstschnitt, keine Fläche, fehlende Maße, jeweils mit Grund")

# ------------------------------------------------------------------ T8 geometrisch nicht ausführbar
assert "weniger als die Wand" in fehler(RR, b=30, h=70, tiefe=2, seite="oben")
assert "endet mitten in der Gegenwand" in fehler(RR, b=30, h=70, tiefe=38.5, seite="oben")
assert "durchgetrennt" in fehler(RR, b=30, h=70, tiefe=40, seite="oben")
assert "durchgetrennt" in fehler(RU, b=30, h=70, tiefe=60, seite="oben (0°)")
assert "Sackloch" in fehler(FL, b=30, h=20, tiefe=5, seite="oben")
assert "mehrere getrennte Ausschnitte" in fehler(UP, b=30, h=90, tiefe=20, seite="Steg", umgekehrt=True)
assert "trifft das Profil nicht" in fehler(RR, b=30, h=10, q=60, tiefe=5, seite="oben", umgekehrt=True)
u = fertig(UP, b=30, h=90, tiefe=20, seite="Steg")                 # U-Profil: beide Flansche 20 mm tief
assert nah(min(q for _, q in u["umriss"]), -60) and nah(max(q for _, q in u["umriss"]), 60) and u["tiefe_ist"] == 20.0
fl = fertig(FL, b=30, h=8, tiefe=12, seite="vorne")                # Flachstahl von der Schmalseite: Kerbe 12 tief
assert nah(fl["laenge_as"], 30 + 2 * 12) and fl["tiefe_ist"] == 12.0
for kw, text in ((dict(tiefe=100), "trennt das Blech"), (dict(breite=300), "Kürzen des Blechs"),
                 (dict(radius=30), "Eckradius höchstens")):
    try:
        ausschnitt.blech_ausklinkung(blech_r, "unten", 100, **dict(dict(breite=40, tiefe=5), **kw))
        raise AssertionError(text)
    except ValueError as f:
        assert text in str(f), f
einmal = ausschnitt.blech_ausklinkung(blech_r, "unten", 100, 40, 5)
try:
    ausschnitt.blech_ausklinkung(einmal, "unten", 110, 40, 8)       # träfe die erste Ausklinkung
    raise AssertionError("zweite Ausklinkung über der ersten")
except ValueError as f:
    assert "keine gerade Außenkante" in str(f)
# keine unbeabsichtigte Änderung: andere Konturen derselben Zeile und des Teils bleiben, die Eingabe selbst auch
andere = [dict(art=sw.BOHRUNG, anzahl=2, d=8, x=40, abstand=30, seite="vorne"),
          dict(art=sw.RECHTECK, anzahl=1, b=20, h=10, x=250, seite="unten")]
roh = zeile(b=30, h=70, tiefe=5, seite="oben")
ein = dict(a={}, b={}, konturen=copy.deepcopy(andere) + [roh])
vorher = copy.deepcopy(ein)
aus = sw.v_ergaenzen(ein, RR)
assert ein == vorher and aus["konturen"][:2] == andere and aus["konturen"][2]["umriss"]
ohne = sw.rechnen(dict(a={}, b={}, konturen=copy.deepcopy(andere)), RR, (10, 50), laenge=L)
mit = sw.rechnen(ein, RR, (10, 50), laenge=L)
assert [s["laenge"] for s in mit["schritte"][:len(ohne["schritte"])]] == [s["laenge"] for s in ohne["schritte"]]
ok("T8 nicht ausführbar: Tasche, Ende in der Gegenwand, Trennen, Sackloch jeweils mit Grund; andere Konturen bleiben")

# ------------------------------------------------------------------ T9 Blech-Editor
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
werkstoff = sorted(z["blech_werkstoff_id"] for z in db.zeilen("blech_werkstoffe"))[0]
bohrung = dict(art=sw.BOHRUNG, anzahl=1, d=8, x=40, y=30)
kant = dict(art=blech.KANTTEIL, form=blech.RECHTECK, dicke=3, kantlaenge=300, werkstoff=werkstoff, konturen=[bohrung],
            schenkel=[dict(laenge=40, winkel=90), dict(laenge=80, winkel=90), dict(laenge=40)])
dlg = BlechDialog(None, db, kant)
rahmen = dlg.editor
dlg.resize(1500, 900)
dlg.show()
app.processEvents()
assert rahmen.band.knopf(ea.TITEL) is not None
e0 = dlg.eingaben()
zs0 = blech.zuschnitt(e0)
vor = rahmen.zustand()
a = ea.BlechAusklinkungDialog(dlg, e0)
a.kante.setCurrentText("unten")
a.lage.setValue(150)
a.breite.setValue(60)
a.tiefe.setValue(45)                                               # tiefer als der erste Schenkel: über die Biegelinie
assert a.ergebnis is not None and a.bild.neu and "Schnittlänge" in a.meldung.text()
assert a.knoepfe.button(QDialogButtonBox.Ok).isEnabled()
a.tiefe.setValue(500)                                              # Vorschau meldet, was nicht geht
assert a.ergebnis is None and a.bild.neu is None and "trennt das Blech" in a.meldung.text()
assert not a.knoepfe.button(QDialogButtonBox.Ok).isEnabled()
a.tiefe.setValue(45)
a.umgekehrt.setChecked(True)                                       # von der gegenüberliegenden Kante
oben = sw.punkte(a.ergebnis["punkte"])
assert nah(min(y for x, y in oben if 119 < x < 181), zs0["breite"] - 45, 1e-3)
a.umgekehrt.setChecked(False)
assert ea.blech_uebernehmen(rahmen, a.ergebnis)
app.processEvents()
e1 = dlg.eingaben()
zs1 = blech.zuschnitt(e1)
assert e1["form"] == blech.POLYGON and nah(zs1["aussen"], zs0["aussen"] + 2 * 45, 1e-3)
assert nah(zs0["flaeche"] - zs1["flaeche"], 60 * 45, 0.05) and nah(zs1["breite"], zs0["breite"], 1e-3), \
    (zs0["flaeche"] - zs1["flaeche"], zs1["breite"], zs0["breite"])
assert e1["schenkel"] == e0["schenkel"] and len(e1["konturen"]) == 1 and e1["konturen"][0]["d"] == 8   # Rest bleibt
n9 = blech3d.netz(e1, zs1)
assert koerper_gueltig(dict(p=n9["p"], t=n9["t"]))
assert rahmen.verlauf.canUndo()
rahmen.verlauf.undo()
assert rahmen.zustand() == vor
rahmen.verlauf.redo()
assert dlg.eingaben()["punkte"] == e1["punkte"]
dlg.close()
neu, hinweise = ausschnitt.blech_ausklinken(dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200,
                                                 breite=100, eckradius=0,
                                                 konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=8, x=100, y=3)]),
                                            "unten", 100, 40, 5)
assert hinweise and "liegt in der Ausklinkung" in hinweise[0]
ok("T9 Blech-Editor: Ausklinkung 60 × 45 an der Kante über die Biegelinie, Vorschau mit Meldung, Rückgängig")

# ------------------------------------------------------------------ T10 Rohr-Editor
fenster = Hauptfenster(db, tmp, stumm=True)
nr = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
db.position_neu(nr, dict(pos=10, artikel="AS-1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=400,
                         stueck=10))
seite = fenster.angebot_oeffnen(nr)
pos = seite.positionen[0]
d = SchneidwegDialog(seite, pos, seite.k.profile["QR 40x40x3"], seite.kopf, seite.k, seite.tabellen)
d.resize(1600, 950)
d.show()
app.processEvents()
rahmen = d.editor
knopf = rahmen.band.knopf(ea.TITEL)
assert knopf is not None and [x.text() for x in knopf.menu().actions()] == ["Neu auf der gewählten Fläche",
                                                                           "Gewählte Kontur umwandeln"]
d.zeile_neu(dict(art=sw.RECHTECK, anzahl=1, b=30, h=20, x=100, seite="vorne"))
rahmen.aktualisieren()
vor = rahmen.zustand()
knopf.click()
app.processEvents()
k = d.eingaben()["konturen"]
assert len(k) == 2 and k[1]["art"] == sw.AUSSCHNITT and k[1]["h"] == 40 and k[1]["tiefe"] == 10, k[1]
assert k[1]["tiefe_ist"] == 10.0 and nah(k[1]["laenge_as"], 2 * 20 + 2 * 60)
assert k[0] == dict(art=sw.RECHTECK, anzahl=1, b=30, h=20, x=100, seite="vorne") or k[0]["art"] == sw.RECHTECK
felder = rahmen.eigenschaften.felder
for name in ("Form der Kontur", "Tiefe t ins Profil", "Richtung umkehren", "Eckradius", "Ergebnis"):
    assert name in felder, sorted(felder)
assert "Wände" not in felder and "Erreichte Tiefe 10 mm" in felder["Ergebnis"].text()
a3 = rahmen.ansicht()
assert a3.netz["l"].get("HK")                                       # Vorschau der Tiefe im 3D
assert rahmen.verlauf.canUndo()
rahmen.verlauf.undo()
assert rahmen.zustand() == vor and len(d.eingaben()["konturen"]) == 1
rahmen.verlauf.redo()
assert d.eingaben()["konturen"][1]["art"] == sw.AUSSCHNITT
# Tiefe kleiner als die Wand: Meldung im Eigenschaftenbereich und im Rechner, nichts wird geschnitten
d.tabelle.item(1, 4).setText("2")
d.rechnen()
rahmen.aktualisieren()
rahmen.waehlen("kontur:1")
rahmen.eigenschaften.zeigen("kontur:1")
assert "weniger als die Wand" in rahmen.eigenschaften.felder["Ergebnis"].text(), \
    rahmen.eigenschaften.felder["Ergebnis"].text()
d.tabelle.item(1, 4).setText("10")
d.rechnen()
# bestehende Kontur als Grundlage: Rechteck -> Ausschnitt mit Tiefe, schneidet zunächst genau wie bisher
alt = sw.rechnen(dict(a={}, b={}, konturen=[d.eingaben()["konturen"][0]]), seite.k.profile["QR 40x40x3"], (10, 50),
                 laenge=400)["schritte"][-1]["laenge"]
assert ea.umwandeln(rahmen, 0)
k0 = d.eingaben()["konturen"][0]
assert k0["art"] == sw.AUSSCHNITT and k0["tiefe"] == 3 and k0["seite"] == "vorne" and k0["x"] == 100
assert nah(k0["laenge_as"], alt, 0.01) and k0["tiefe_ist"] == 3.0
assert not ea.umwandeln(rahmen, 0)                                  # ein Ausschnitt ist schon einer
# Fläche im 3D wählen, dann einfügen: der Ausschnitt liegt auf dieser Fläche
rahmen.band.knopf("Auswahl").setChecked(True)
app.processEvents()
assert a3.wahl.an
a3.wahl.filter = aw.FLAECHE
treffer = None
for x in range(10, a3.width() - 10, 5):
    for y in range(10, a3.height() - 10, 5):
        el = a3.wahl.unter(x, y)
        if el is not None and el["art"] == aw.FLAECHE and el["typ"] == "eben" and el["flaeche"] > 5000:
            treffer = (x, y)
            break
    if treffer:
        break
assert treffer, "keine Außenfläche im Bild"
a3.wahl.klick(*treffer)
ort = ea.flaeche_aus_auswahl(rahmen)
assert ort is not None and ort[0] in d.qs.seiten(), ort
assert ea.einfuegen(rahmen)
neu = d.eingaben()["konturen"][-1]
assert neu["art"] == sw.AUSSCHNITT and neu["seite"] == ort[0] and nah(neu["x"], ort[1], 0.11), (neu, ort)
d.close()
ok("T10 Rohr-Editor: Knopf und Eigenschaften, Vorschau im 3D, Rückgängig, Meldung, Kontur umwandeln, Fläche aus 3D")

print("Alle Prüfungen bestanden.")
