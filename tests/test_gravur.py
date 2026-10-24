"""Positionsgravur (Patrick 24.10.2026 „C a a a b“): Artikelnummer auf Bleche und Rohre einer Schweißbaugruppe
gravieren.
- Einstrich-Schrift gravur_text: Striche, Maße, Länge, Ersatzzeichen, Lage längs eines Rohrs
- Konturart Text-Gravur: nur Gravur (kein Schneidweg, kein Einstich), Blech-Editor rechnet die Zeit mit Vorschub
  Gravur der Blechlaser-Richtwerte (leer = Hinweis, keine erfundene Zeit), Lage automatisch in der größten freien
  Fläche mit mindestens 0,5 mm Abstand, DXF-Layer Gravur, 3D-Linien je Strich
- Rohrlaserteil: Spalte bg_gravur (Schrifthöhe) zählt in die Gravurzeit der Kalkulation
- Baugruppen-Editor: Häkchen je Teil nach der Einstellung gravur_artikel, „Alle gravieren“, beim Speichern bekommt
  das Blech die Zeile Text-Gravur und einen neuen Richtpreis

Alle Preise und Vorschübe sind Testwerte. Aufruf: python tests/test_gravur.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import blech, blech3d, dxf, gravur_text, rechnen, schneidweg as sw, zukauf  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE, ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

tmp = Path(tempfile.mkdtemp())
app = QApplication.instance() or QApplication([])
fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            fehler += 1
            print(f"FEHLER {name}: {e}")
        return fn
    return deko


def nah(a, b, text, eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


@fall("Schrift: Striche je Zeichen, Mitte (0, 0), Maße, Länge = Summe der Striche, Ersatzzeichen")
def _():
    assert gravur_text.zeichen("Pos-ä1ß*") == "POS-A1SS?"
    z = gravur_text.linien("H", 6)
    assert z == [[(-2.0, -3.0), (-2.0, 3.0)], [(2.0, -3.0), (2.0, 3.0)], [(-2.0, 0.0), (2.0, 0.0)]], z
    nah(gravur_text.laenge("H", 6), 16, "H: 2 × 6 + 4")
    nah(gravur_text.laenge("H", 12), 32, "doppelte Höhe, doppelte Länge")
    b, h = gravur_text.masse("S03-K1", 10)
    nah(b, (6 * 6 - 2) * 10 / 6, "Breite")
    nah(h, 10, "Höhe")
    alle = [p for zug in gravur_text.linien("S03-K1", 10) for p in zug]
    assert all(abs(x) <= b / 2 + 1e-9 and abs(y) <= h / 2 + 1e-9 for x, y in alle), "im Hüllrechteck um (0, 0)"
    assert gravur_text.linien("", 10) == [] and gravur_text.laenge("X", 0) == 0
    g = gravur_text.gedreht([[(1.0, 0.0)]], 90, 10, 20)
    nah(g[0][0][0], 10, "gedreht x")
    nah(g[0][0][1], 21, "gedreht y")


@fall("Rohr: Lage längs mit größtem Abstand zu Anfang, Ende und Konturen, kein Platz = None")
def _():
    assert gravur_text.lage_laengs(500, [(100, 120), (400, 410)], 56.7) == (260.0, 111.65)
    assert gravur_text.lage_laengs(50, [], 56.7) is None
    assert gravur_text.lage_laengs(57.6, [], 56.7) is None, "0,45 mm Abstand reicht nicht"


@fall("Konturart Text-Gravur: Länge aus der Schrift, Text und Höhe Pflicht")
def _():
    lg, huelle, n = sw.kontur(dict(art=sw.TEXT_GRAVUR, text="AB", hoehe=10, anzahl=2))
    nah(lg, gravur_text.laenge("AB", 10), "Länge")
    assert huelle is None and n == 2
    try:
        sw.kontur(dict(art=sw.TEXT_GRAVUR, hoehe=10, anzahl=1))
        raise AssertionError("ohne Text muss es einen Fehler geben")
    except ValueError as x:
        assert "Text-Gravur" in str(x)


db = Datenbank(tmp / "g.db")
werkstoffe = {z["blech_werkstoff_id"]: z for z in db.zeilen("blech_werkstoffe")}
WST = next(iter(werkstoffe))
laser = db.zeilen("blechlaser")
E = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, werkstoff=WST, dicke=3, laenge=200, breite=100, stueck=1,
         konturen=[dict(art=sw.BOHRUNG, d=20, x=50, y=50, anzahl=1)])


@fall("Blech: Lage automatisch weg von der Bohrung, schmales Blech quer, 0,5 mm Abstand geprüft")
def _():
    z = dict(art=sw.TEXT_GRAVUR, text="S03-K1", hoehe=10, anzahl=1)
    lage = blech.gravur_lage(E, z)
    assert lage["x"] > 100 and lage["winkel"] == 0 and lage["frei"] >= blech.GRAVUR_ABSTAND, lage
    lage = blech.gravur_lage(dict(E, laenge=60, breite=150, konturen=[]), z)
    assert lage["winkel"] == 90, lage
    e = dict(E, konturen=E["konturen"] + [dict(z, x=lage["x"], y=lage["y"], winkel=0)])
    e["konturen"][-1].update(x=150, y=50)
    assert blech.gravur_hinweise(e) == []
    e["konturen"][-1].update(x=70)
    h = blech.gravur_hinweise(e)
    assert len(h) == 1 and "mindestens 0,5 mm" in h[0], h
    e["konturen"][-1].update(x=195)
    assert "ragt aus dem Blech" in blech.gravur_hinweise(e)[0]


@fall("Blech: Gravur ohne Einstich und Schneidweg, Zeit mit Vorschub Gravur, ohne Vorschub Hinweis")
def _():
    ohne = blech.rechnen(E, werkstoffe, laser)
    z = dict(art=sw.TEXT_GRAVUR, text="S03-K1", hoehe=10, anzahl=1, x=150, y=50, winkel=0)
    e = dict(E, konturen=E["konturen"] + [z])
    leer = [dict(r, vorschub_gravur=None) for r in laser]
    mit = blech.rechnen(e, werkstoffe, leer)
    assert not mit["fehler"], mit["fehler"]
    assert mit["einstiche"] == ohne["einstiche"] and mit["schneidweg"] == ohne["schneidweg"]
    nah(mit["gravur"], gravur_text.laenge("S03-K1", 10), "Gravurlänge")
    nah(mit["zeit"], ohne["zeit"], "ohne Vorschub Gravur keine Zeit")
    assert any("Vorschub Gravur fehlt" in h for h in mit["hinweise"]), mit["hinweise"]
    v = [dict(r, vorschub_gravur=3000) for r in laser]
    mit = blech.rechnen(e, werkstoffe, v)
    nah(mit["zeit"] - blech.rechnen(E, werkstoffe, v)["zeit"], gravur_text.laenge("S03-K1", 10) / 3000 * 60, "Zeit")
    assert not any("Vorschub Gravur" in h for h in mit["hinweise"])


@fall("Blech: DXF-Linien auf dem Layer Gravur, 3D je Strich ein Linienzug")
def _():
    z = dict(art=sw.TEXT_GRAVUR, text="H", hoehe=6, anzahl=1, x=150, y=50, winkel=0)
    el = dxf.kontur_elemente(z, 150, 50)
    assert len(el) == 3 and all(x[0] == "LINE" and x[1] == dxf.GRAVUR for x in el), el
    e = dict(E, konturen=[z])
    zuege = blech3d.konturzuege(e, blech.zuschnitt(e))
    assert len(zuege) == 3 and zuege[0][1] == [(148.0, 47.0), (148.0, 53.0)], zuege


# ------------------------------------------------------------------ Angebot: Rohr und Blech in einer Baugruppe
db.einstellung_setzen("mindestpreis", 0)
a = db.angebot_neu(dict(kunde="Test"))
r1 = db.position_neu(a, dict(pos=10, artikel="R-100", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                             laenge=1000, stueck=4, schneidweg=300, einstiche=2))
werte, bezuege = zukauf.blech_artikel(dict(laenge=200.0, breite=100.0, dicke=3.0, kontur="rechteckig",
                                           fingerabdruck="g"), WST)
aid = db.zukauf_speichern(None, werte, bezuege)
db.zukauf_ek_eintragen(aid, 5, "Technik")
b1 = db.position_neu(a, dict(pos=20, art=ZUKAUFTEIL, artikel="B-7", bezeichnung="Lasche", stueck=4,
                             technik=blech.speichern(E),
                             zukauf=json.dumps([dict(artikel_id=aid, menge=1, stand=db.zukauf_stand(aid))])))
k, tab = db.kontext(), db.tabellen()


def kalk():
    kopf, pos = db.angebot(a), db.positionen(a)
    einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
    return rechnen.kalkulation(kopf, pos, rechnen.optimieren(kopf, pos, k), k, tab, einst)[0]


@fall("Rohr: Artikelnummer-Gravur (bg_gravur) zählt in Gravurlänge und -zeit, 0 = keine, Zukaufteil nie")
def _():
    vorher = next(z for z in kalk() if z.get("pos") == 10)
    db.position_aendern(r1, "bg_gravur", 10.0)
    nachher = next(z for z in kalk() if z.get("pos") == 10)
    nah(nachher["mm_gravur"] - (vorher["mm_gravur"] or 0), gravur_text.laenge("R-100", 10), "mm Gravur")
    assert (nachher["zeit_gravur"] or 0) > (vorher["zeit_gravur"] or 0)
    assert rechnen.gravur_artikel(dict(art=ZUKAUFTEIL, artikel="X", bg_gravur=10)) == 0
    assert rechnen.gravur_artikel(dict(artikel="X", bg_gravur=0)) == 0
    db.position_aendern(r1, "bg_gravur", None)


f = Hauptfenster(db, stumm=True)
seite = f.angebot_oeffnen(a)
db.einstellung_setzen("gravur_artikel", "ja")
db.einstellung_setzen("gravur_schrifthoehe", 8)


@fall("Baugruppen-Editor: Häkchen nach Einstellung, Spalte Gravur, Speichern: Rohr bg_gravur, Blech Zeile + Preis")
def _():
    gesehen = {}

    def dialog(d):
        d.teil_setzen(r1, True)
        d.teil_setzen(b1, True)
        t = {x["_id"]: x for x in d.teile}
        gesehen.update(rohr=t[r1]["gravur"], blech=t[b1]["gravur"], h=t[r1]["gravur_h"],
                       info=d._gravur_text(t[b1], 0))
        d.alle_gravieren(False)
        assert not any(x["gravur"] for x in d.teile)
        d.alle_gravieren(True)
        d._ok()
        return d.result()
    assert seite.baugruppe_neu(dialog=dialog)
    assert gesehen["h"] == 8 and gesehen["info"].endswith("mm"), gesehen
    pos = {q["id"]: q for q in db.positionen(a)}
    assert pos[r1]["bg_gravur"] == 8 and pos[b1]["bg_gravur"] == 8
    e = blech.lesen(pos[b1]["technik"])
    g = [z for z in e["konturen"] if z.get("art") == sw.TEXT_GRAVUR]
    assert len(g) == 1 and g[0]["text"] == "B-7" and g[0]["hoehe"] == 8 and g[0]["artikel"], g
    assert g[0]["x"] > 100, g
    assert e["richtpreise"], "Richtpreis neu gerechnet"
    assert any(p.get("art") == BAUGRUPPE for p in pos.values())


@fall("Baugruppen-Editor: Häkchen weg = Gravur-Zeile des Blechs entfernt, Rohr 0")
def _():
    i = next(i for i, q in enumerate(seite.positionen) if q.get("art") == BAUGRUPPE)

    def dialog(d):
        d.alle_gravieren(False)
        d._ok()
        return d.result()
    assert seite.baugruppe_bearbeiten([i], dialog=dialog)
    pos = {q["id"]: q for q in db.positionen(a)}
    assert pos[r1]["bg_gravur"] == 0 and pos[b1]["bg_gravur"] == 0
    assert not [z for z in blech.lesen(pos[b1]["technik"])["konturen"] if z.get("art") == sw.TEXT_GRAVUR]


print("Positionsgravur:", "alles OK" if not fehler else f"{fehler} Fehler")
sys.exit(1 if fehler else 0)
