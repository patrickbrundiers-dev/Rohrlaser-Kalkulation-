"""Prüft die Konturerkennung mit Lage im Rohrkoordinatensystem (Teile in tests/step_konturen, dazu T02/T07):
Bohrungen (Ø, Position z und Umfangswinkel, schräg, gegenüberliegend), Langloch, Rechteckausschnitt, Sackbohrung,
Gravur, gerade Enden, Gehrung und zweiachsiger Schrägschnitt.

Rohrkoordinaten: z ab Ende A entlang der Achse; Umfangswinkel rechtsdrehend um die Achse (Daumen von A nach B),
0° = Mitte der breiten Seite, die in der Datei nach oben zeigt (liegt das Rohr senkrecht: nach +Y), bei Rundrohren die
oberste Stelle. Sollwerte aus den Konstruktionsmaßen in tests/erzeuge_testteile.py.
Aufruf: python tests/test_step_konturen.py
"""
import math
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from step_geometrie import analysiere_datei  # noqa: E402

ORDNER = HIER / "step_konturen"
fehler = 0


def nah(ist, soll, tol, was):
    assert ist is not None and abs(ist - soll) <= tol, f"{was} ist {ist}, soll {soll:.3f}"


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


def winkel_nah(ist, soll, tol, was):
    d = (ist - soll + 180) % 360 - 180
    assert abs(d) <= tol, f"{was}: Winkel {ist}, soll {soll}"


def k01(t, mit_winkel=True):
    kl = t.konturen_liste
    a, b = kl[0], kl[1]
    assert a["art"] == "Ende A" and a["form"] == "gerade", a
    nah(a["schnittlaenge"], 200, 0.05, "Ende A Schnittlänge")
    assert b["art"] == "Ende B" and b["form"] == "Gehrung", b
    nah(b["gehrung"], 30, 0.05, "Gehrung")
    nah(b["um_x"], 30, 0.05, "Gehrung um X")
    nah(b["um_y"], 0, 0.05, "Gehrung um Y")
    if mit_winkel:
        winkel_nah(b["richtung"], 0, 0.2, "Ende B am längsten oben (0°)")
    nah(b["z"], 850 + 20 * math.tan(math.radians(30)), 0.02, "Länge")
    nah(b["schnittlaenge"], 120 + 80 / math.cos(math.radians(30)), 0.05, "Ende B Schnittlänge")
    rest = kl[2:]
    soll = [("Bohrung", 100, 0, dict(durchmesser=10)), ("Bohrung", 200, 270, dict(durchmesser=6.6)),
            ("Langloch", 400, 180, dict(laenge=30, breite=10, richtung=90)),
            ("Rechteckausschnitt", 600, 90, dict(laenge=20, breite=10, richtung=90)),
            ("Sackbohrung", 700, 0, dict(durchmesser=6))]
    assert [d["art"] for d in rest] == [s[0] for s in soll], [d["art"] for d in rest]
    for d, (art, z, w, masse) in zip(rest, soll):
        nah(d["z"], z, 0.02, f"{art} z")
        if mit_winkel:
            winkel_nah(d["winkel"], w, 0.2, art)
            assert d["seite"] == f"{w}°", d
        for k, v in masse.items():
            nah(d[k], v, 0.02, f"{art} {k}")
        assert d["durchgehend"] == (art != "Sackbohrung"), d
    assert any("Sackbohrung" in h for h in t.hinweise), t.hinweise
    nah(t.schneidweg, 200 + 120 + 80 / math.cos(math.radians(30)) + math.pi * (10 + 6.6) + 2 * 20 + math.pi * 10 + 60,
        0.1, "Schneidweg")


@fall("K01 Rechteckrohr: Bohrungen, Langloch, Ausschnitt, Sackbohrung, Gehrung 30°")
def _():
    (t,) = analysiere_datei(ORDNER / "K01_RE60x40x3_Konturen.step")
    k01(t)


@fall("K02 dasselbe Teil gedreht und verschoben: gleiche Lage entlang der Achse und gleiche Maße")
def _():
    (t,) = analysiere_datei(ORDNER / "K02_RE60x40x3_Konturen_gedreht.step")
    k01(t, mit_winkel=False)
    # Winkel: gleiche Abstände untereinander wie in K01 (0° kann bei schräger Lage auf der Gegenseite liegen)
    w = [d["winkel"] for d in t.konturen_liste[2:]]
    for ist, soll in zip(w, (0, 270, 180, 90, 0)):
        d = (ist - w[0] - soll) % 360
        assert min(d, 360 - d) <= 0.2, w


@fall("K03 Rundrohr: radiale und schräge Bohrungen, zweiachsiger Schrägschnitt")
def _():
    (t,) = analysiere_datei(ORDNER / "K03_RR42-4x2_Konturen.step")
    a20, a10 = math.radians(20), math.radians(10)
    n = (math.cos(a20) * math.sin(a10), -math.sin(a20), math.cos(a20) * math.cos(a10))
    zmin = 30 - 21.2 * math.hypot(n[0], n[1]) / n[2]
    kl = t.konturen_liste
    a = kl[0]
    assert a["form"] == "Schrägschnitt zweiachsig", a
    nah(a["gehrung"], math.degrees(math.acos(n[2])), 0.02, "Gesamtneigung")
    nah(a["um_x"], math.degrees(math.atan(math.tan(a20) / math.cos(a10))), 0.02, "Neigung um X")
    nah(a["um_y"], 10, 0.02, "Neigung um Y")
    # am längsten in Richtung +(nx, ny) (Ende A): Umfangswinkel atan2(−nx, ny) = 205,5° (unten, nach links)
    winkel_nah(a["richtung"], math.degrees(math.atan2(-n[0], n[1])) % 360, 0.2, "Ende A Richtung")
    assert a["richtung"] is not None and kl[1]["richtung"] is None
    nah(t.laenge, 700 - zmin, 0.02, "Länge")
    b = kl[2:]
    assert [d["art"] for d in b] == ["Bohrung"] * 3, b
    nah(b[0]["z"], 150 - zmin, 0.02, "Bohrung 1 z"); winkel_nah(b[0]["winkel"], 0, 0.2, "Bohrung 1")
    nah(b[0]["durchmesser"], 8, 0.01, "Bohrung 1 Ø"); nah(b[0]["schraeg"], 0, 0.05, "Bohrung 1 schräg")
    nah(b[1]["durchmesser"], 8, 0.01, "Bohrung 2 Ø"); nah(b[1]["schraeg"], 30, 0.05, "Bohrung 2 schräg")
    winkel_nah(b[1]["winkel"], 0, 0.5, "Bohrung 2")
    assert 300 - zmin < b[1]["z"] < 300 - zmin + 21.2 * math.tan(math.radians(30)) + 1, b[1]["z"]
    nah(b[2]["z"], 450 - zmin, 0.02, "Bohrung 3 z"); winkel_nah(b[2]["winkel"], 90, 0.2, "Bohrung 3")
    nah(b[2]["durchmesser"], 12, 0.01, "Bohrung 3 Ø")


@fall("T02 Querbohrung durch beide Wände: zwei gegenüberliegende Bohrungen")
def _():
    (t,) = analysiere_datei(HIER / "step" / "T02_RR42-4x2_L860_Bohrung.step")
    b = [d for d in t.konturen_liste if d["art"] == "Bohrung"]
    assert len(b) == 2 and all(d.get("gegenueber") for d in b), b
    nah(abs((b[0]["winkel"] - b[1]["winkel"]) % 360), 180, 0.2, "Winkelabstand")
    assert all(abs(d["z"] - 430) < 0.02 for d in b), b


@fall("T07 Quadratrohr: 4 Kernlöcher in Reihe, Gravur, Ausklinkung als komplexes Ende")
def _():
    (t,) = analysiere_datei(HIER / "step" / "T07_QR40x3_L1000_Gewinde_Gravur.step")
    kl = t.konturen_liste
    assert kl[1]["form"] == "komplex", kl[1]
    b = [d for d in kl if d["art"] == "Bohrung"]
    assert [d["z"] for d in b] == [100, 150, 200, 250] and len({d["winkel"] for d in b}) == 1, b
    g = [d for d in kl if d["art"] == "Gravur"]
    assert len(g) == 1 and not g[0]["durchgehend"], g
    nah(g[0]["z"], 402.5, 0.02, "Gravur z"); nah(g[0]["laenge"], 24, 0.02, "Gravur Länge")
    winkel_nah(g[0]["winkel"], (b[0]["winkel"] + 90) % 360, 0.2, "Gravur 90° neben den Bohrungen")


@fall("Offene Profile: Fläche (Steg, Flansch, Schenkel) und Versatz quer je Kontur, auch gedreht (K07-K10)")
def _():
    import json
    sys.path.insert(0, str(HIER.parent / "programm"))
    from rohrlaser import step

    def lage(datei):
        t = analysiere_datei(str(ORDNER / datei))[0]
        m = dict(konturen_liste=json.dumps(t.konturen_liste), wandstaerke=t.wandstaerke, normprofil=t.normprofil,
                 profil_id_vorschlag=t.profil_id_vorschlag)
        e = step.rechner_eingaben(m, t.profilform, t.abm_a, t.abm_b)
        return [(k["x"], k.get("d"), k.get("seite"), k.get("q")) for k in e["konturen"]]
    # U80x40x4, Steg unten in der Datei: Ø8 20 neben der Steg-Mitte, Ø6 im Flansch x+ 5 zur Spitze, Ø10 im Flansch
    # x− 5 zum Steg (Skizze: Steg vorne, Flansch unten = der von Ende A gesehen rechts liegende)
    soll = [(100, 8, "Steg", 20), (250, 6, "Flansch unten", 5), (400, 10, "Flansch oben", 5)]
    for datei in ("K07_U80x40x4_Lage.step", "K08_U80x40x4_Lage_gedreht.step"):
        assert lage(datei) == soll, (datei, lage(datei))
    # L60x40x5: Ø8 im 60er Schenkel 40 von der Ecke (10 über die Mitte hinaus), Ø6 im 40er Schenkel 25 von der Ecke
    assert lage("K09_L60x40x5_Lage.step") == [(100, 8, "Schenkel a", -10), (300, 6, "Schenkel b", 5)], \
        lage("K09_L60x40x5_Lage.step")
    k10 = lage("K10_T60x60x5x7_Lage.step")
    assert [k[2] for k in k10] == ["Flansch", "Steg"] and abs(k10[0][3]) == 15, k10


sys.exit(1 if fehler else 0)
