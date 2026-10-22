"""Prüft die Trennung von Rohr und Anbauteilen im STEP-Import (Teile in tests/step_anbau, erzeugt mit
tests/erzeuge_testteile.py): aufgeschweißte Bolzen, Laschen, Bleche, Muttern, Kopfplatten, als ein Körper verschmolzen
oder als eigene Körper der Baugruppe.

Je Fall: Rohrprofil und Länge wie ohne Anbauteile, Anbauteile mit Art, Lage (z ab Ende A, Winkel: 0° = oben,
+X = 270°), Aufstandsfläche und Gravur (Vorgabe Patrick 22.10.2026: Bolzen Kreuzmarke 2 × 10 mm, Laschen/Bleche/
Muttern Umriss, Kopfplatte keine), reguläre Konturen unverändert, Schneidweg und Einstiche gleich dem Teil ohne
Anbauteile (Anbauteile nie im Schneidweg), unsichere Fälle mit Prüfstatus "prüfen", Originaldatei unverändert.
Aufruf: python tests/test_step_anbau.py
"""
import hashlib
import json
import math
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
import step_ergebnis  # noqa: E402
import step_messen  # noqa: E402
from step_geometrie import MARKE_KREUZ, analysiere_datei  # noqa: E402

ORDNER = HIER / "step_anbau"
fehler = 0
KREUZ = 2 * MARKE_KREUZ
RE_ENDE = 2 * (60 + 40) - 8 * 4 + 2 * math.pi * 4      # gerader Schnitt RE 60x40, Außenradius 4


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


def messen(name, netz=False):
    pfad = ORDNER / f"{name}.step"
    vorher = hashlib.sha256(pfad.read_bytes()).hexdigest()
    teile = analysiere_datei(pfad, netz=netz)
    assert hashlib.sha256(pfad.read_bytes()).hexdigest() == vorher, "Originaldatei verändert"
    return teile


def rohr(t, form, a, b, w, l):
    assert t.profilform == form, f"Profil {t.profilform}, soll {form}"
    nah(t.abm_a, a, 0.01, "Breite/Ø")
    nah(t.abm_b, b, 0.01, "Höhe")
    nah(t.wandstaerke, w, 0.01, "Wand")
    nah(t.laenge, l, 0.01, "Länge")


def anbau(t, art, z, winkel=None, gravur=None, vertrauen="sicher"):
    """Das Anbauteil der Art bei z (±0,5 mm) suchen und prüfen."""
    passend = [a for a in t.anbauteile if a["art"] == art and a["z"] is not None and abs(a["z"] - z) <= 0.5]
    assert len(passend) == 1, f"{art} bei z {z} nicht gefunden: {[(a['art'], a['z']) for a in t.anbauteile]}"
    a = passend[0]
    if winkel is not None:
        assert a["winkel"] is not None and abs((a["winkel"] - winkel + 180) % 360 - 180) <= 0.5, \
            f"{art} z {z}: Winkel {a['winkel']}, soll {winkel}"
    if gravur is not None:
        nah(a["gravur_laenge"], gravur, 0.05, f"{art} z {z} Gravur")
    assert a["vertrauen"] == vertrauen, f"{art} z {z}: Vertrauen {a['vertrauen']}, soll {vertrauen}"
    return a


def gerade_enden(t, ende):
    nah(t.ende_a, ende, 0.05, "Ende A")
    nah(t.ende_b, ende, 0.05, "Ende B")
    assert t.ende_a_gerade and t.ende_b_gerade, "Enden gerade"


A01 = messen("A01_RE60x40x3_ohne_Anbau")[0]


@fall("A01 RE 60x40x3 ohne Anbauteile: wie bisher, keine Anbauteile, keine Trennung")
def _():
    rohr(A01, "Rechteckrohr", 60, 40, 3, 1000)
    gerade_enden(A01, RE_ENDE)
    assert A01.anbauteile == [] and A01.trennung is None and A01.gravur == 0
    assert A01.pruefstatus == "plausibel"


@fall("A02 RE + Bolzen Ø8 im ersten Prüfschnitt: Profil nicht verfälscht (früher Sonderprofil 60 x 59,5)")
def _():
    t = messen("A02_RE60x40x3_Bolzen", netz=True)[0]
    rohr(t, "Rechteckrohr", 60, 40, 3, 1000)
    gerade_enden(t, RE_ENDE)
    nah(t.schneidweg, A01.schneidweg, 0.01, "Schneidweg wie ohne Bolzen")
    assert t.konturen == A01.konturen and t.konturen_liste[2:] == [], "keine zusätzlichen Konturen"
    assert len(t.anbauteile) == 1
    a = anbau(t, "Bolzen", 500, 0, KREUZ)
    assert a["seite"] == "0°" and a["aufstand"]["form"] == "Kreis", a
    nah(a["aufstand"]["durchmesser"], 8, 0.01, "Bolzen Ø")
    nah(a["hoehe"], 19.5, 0.05, "Bolzen Höhe über der Wand")
    assert a["bearbeitung"] == "Positionsmarke" and a["quelle"] == "verschmolzen"
    nah(t.gravur, KREUZ, 0.01, "Gravur")
    nah(t.gravur_anbau, KREUZ, 0.01, "davon Anbauteile")
    assert t.pruefstatus == "plausibel", t.hinweise
    assert t.trennung["ohne_trennung"]["profil_id"] == "Sonderprofil", t.trennung   # so war es früher
    assert "AN" in t.netz["t"] and len(t.netz["l"]["GA"]) == 2, "3D: Anbauteil und Kreuzmarke"


@fall("A03 QR 40x3 mit 4 Bolzen auf zwei Seiten")
def _():
    t = messen("A03_QR40x3_4Bolzen")[0]
    rohr(t, "Quadratrohr", 40, 0, 3, 800)
    assert len(t.anbauteile) == 4
    for z, w in ((150, 0), (300, 0), (450, 270), (600, 270)):
        a = anbau(t, "Bolzen", z, w, KREUZ)
        nah(a["aufstand"]["durchmesser"], 6, 0.01, "Bolzen Ø")
    nah(t.gravur, 4 * KREUZ, 0.01, "Gravur")
    assert t.pruefstatus == "plausibel", t.hinweise


@fall("A04 RR 42,4x2 mit aufgesetztem Blech (früher nicht messbar)")
def _():
    t = messen("A04_RR42-4x2_Blech")[0]
    rohr(t, "Rundrohr", 42.4, 0, 2, 1000)
    gerade_enden(t, math.pi * 42.4)
    assert len(t.anbauteile) == 1
    a = anbau(t, "Lasche", 500, 0)
    nah(a["aufstand"]["laenge"], 200, 0.05, "Aufstand Länge")
    nah(a["aufstand"]["breite"], 8, 0.1, "Aufstand Breite (abgewickelt)")
    nah(a["gravur_laenge"], a["aufstand"]["umfang"], 0.01, "Gravur = Umriss")
    assert a["bearbeitung"] == "Umriss"
    assert t.trennung["ohne_trennung"]["pruefstatus"] == "nicht messbar"


@fall("A05 RE 80x40x3 mit drei unterschiedlich großen Laschen")
def _():
    t = messen("A05_RE80x40x3_3Laschen")[0]
    rohr(t, "Rechteckrohr", 80, 40, 3, 1200)
    assert len(t.anbauteile) == 3
    for z, w, lg, br in ((200, 0, 40, 6), (600, 270, 80, 8), (950, 180, 120, 10)):
        a = anbau(t, "Lasche", z, w, 2 * (lg + br))
        nah(a["aufstand"]["laenge"], lg, 0.05, "Lasche Länge")
        nah(a["aufstand"]["breite"], br, 0.05, "Lasche Breite")
    nah(t.gravur, 2 * (46 + 88 + 130), 0.1, "Gravur Umrisse")


@fall("A06 Bohrungen und Langloch ohne Anbauteile: Konturen unverändert, nichts abgetrennt")
def _():
    t = messen("A06_RE60x40x3_Bohrungen_ohne_Anbau")[0]
    rohr(t, "Rechteckrohr", 60, 40, 3, 1000)
    assert t.anbauteile == [] and t.trennung is None
    arten = [(k["art"], round(k["z"]), k["winkel"]) for k in t.konturen_liste[2:]]
    assert arten == [("Bohrung", 200, 0.0), ("Langloch", 500, 0.0), ("Bohrung", 800, 270.0)], arten
    assert t.gravur == 0 and t.pruefstatus == "plausibel"


@fall("A07 Gehrung 30°, Bohrung, Bolzen und Lasche: Gehrung und Bohrung bleiben, Anbauteile getrennt")
def _():
    t = messen("A07_RE60x40x3_Gehrung_Anbau")[0]
    rohr(t, "Rechteckrohr", 60, 40, 3, 1000 + 30 * math.tan(math.radians(30)))   # Gehrung über die Breite
    b = t.konturen_liste[1]
    assert b["art"] == "Ende B" and b["form"] == "Gehrung", b
    nah(b["gehrung"], 30, 0.05, "Gehrung")
    rest = [(k["art"], round(k["z"]), k["winkel"], k.get("durchmesser")) for k in t.konturen_liste[2:]]
    assert rest == [("Bohrung", 300, 0.0, 10.0)], rest
    anbau(t, "Bolzen", 600, 0, KREUZ)
    anbau(t, "Lasche", 150, 270, 2 * (50 + 6))
    nah(t.innen, math.pi * 10, 0.05, "Innenkonturen nur die Bohrung")


@fall("A08 = A09: Bolzen und Blech als eigene Körper bzw. verschmolzen ergeben dieselben Anbauteile")
def _():
    teile = messen("A08_RE60x40x3_Anbau_eigene_Koerper")
    assert len(teile) == 3, "Rohr, Bolzen und Blech bleiben eigene Teile (F2 a)"
    t8 = teile[0]
    t9 = messen("A09_RE60x40x3_Anbau_verschmolzen")[0]
    for t, quelle in ((t8, "Körper"), (t9, "verschmolzen")):
        rohr(t, "Rechteckrohr", 60, 40, 3, 1000)
        nah(t.schneidweg, A01.schneidweg, 0.01, "Schneidweg")
        a = anbau(t, "Bolzen", 300, 0, KREUZ)
        b = anbau(t, "Blech", 675, 270)
        assert a["quelle"].startswith(quelle) and b["quelle"].startswith(quelle), (a["quelle"], b["quelle"])
        nah(b["aufstand"]["laenge"], 150, 0.05, "Blech Auflage Länge")
        nah(b["aufstand"]["breite"], 40 - 2 * 4, 0.05, "Blech Auflage Breite (gerade Seite)")
        nah(b["gravur_laenge"], 2 * (150 + 32), 0.05, "Blech Umriss")
        assert t.pruefstatus == "plausibel", t.hinweise
    assert teile[1].profilform == "Rundstahl" and teile[2].bauteiltyp == "Blech"
    assert teile[1].anbauteile == [] and teile[2].anbauteile == []
    nah(t8.gravur, t9.gravur, 0.01, "gleiche Gravur")


@fall("A10 Blech über die ganze Länge: Rohr aus Innenkontur + Wand, mehrdeutig -> prüfen")
def _():
    t = messen("A10_RE60x40x3_Laengsblech")[0]
    rohr(t, "Rechteckrohr", 60, 40, 3, 1000)
    assert t.trennung["laengsanbau"] is True
    assert t.pruefstatus == "prüfen" and any("ganze Länge" in h for h in t.hinweise), t.hinweise
    assert t.trennung["ohne_trennung"]["profil_id"].startswith("RE 120"), t.trennung
    assert all(a["vertrauen"] == "prüfen" for a in t.anbauteile)


@fall("A11 Kopfplatte, Mutter über Bohrung, Klotz an der Ecke: Länge ohne Platte, Bohrung bleibt, Ecke prüfen")
def _():
    t = messen("A11_RE60x40x3_Kopfplatte_Mutter_Ecke")[0]
    rohr(t, "Rechteckrohr", 60, 40, 3, 1000)
    gerade_enden(t, RE_ENDE)
    k = anbau(t, "Kopfplatte", 1000, gravur=0)
    assert k["seite"] == "Ende B" and k["bearbeitung"] == "keine"
    nah(k["hoehe"], 8, 0.01, "Plattendicke")
    m = anbau(t, "Mutter", 450, 0, 16 * math.pi)
    assert m["bearbeitung"] == "Umriss"
    bo = [k_ for k_ in t.konturen_liste[2:] if k_["art"] == "Bohrung"]
    assert len(bo) == 1 and bo[0]["durchmesser"] == 8.5 and round(bo[0]["z"]) == 450, bo
    e = anbau(t, "Sonstiges", 720, vertrauen="prüfen")
    assert e["seite"] == "Ecke", e
    assert t.pruefstatus == "prüfen" and t.sicherheit["anbauteile"] == "unsicher"
    assert t.trennung["ohne_trennung"]["laenge"] == 1008.0, "ohne Trennung war die Platte in der Länge"


@fall("Ausgabe: JSON-Schema 1.4 und TXT-Spalten anbauteile/trennung/gravur_anbau")
def _():
    t = messen("A02_RE60x40x3_Bolzen")[0]
    j = step_ergebnis.koerper(t)
    assert step_ergebnis.SCHEMA_VERSION >= "1.4"
    assert j["anbauteile"][0]["art"] == "Bolzen" and j["trennung"]["regelanteil"] > 0.9
    assert j["schneidweg"]["gravur_anbau"] == KREUZ and j["schneidweg"]["gravur"] == KREUZ
    assert step_ergebnis.koerper(A01)["anbauteile"] == [] and step_ergebnis.koerper(A01)["trennung"] is None
    json.dumps(j)
    with tempfile.TemporaryDirectory() as d:
        zeilen, _ = step_messen.messen(ORDNER / "A02_RE60x40x3_Bolzen.step", Path(d))
        m = dict(zip(step_messen.SPALTEN, zeilen[0]))
        assert json.loads(m["anbauteile"])[0]["art"] == "Bolzen"
        assert json.loads(m["trennung"])["ohne_trennung"]["profil_id"] == "Sonderprofil"
        assert float(m["gravur_anbau"]) == KREUZ and m["fehler"] == ""
        netz = json.loads((Path(d) / m["netz"]).read_text(encoding="utf-8"))
        assert "AN" in netz["t"] and "GA" in netz["l"]
        z1 = dict(zip(step_messen.SPALTEN, step_messen.messen(ORDNER / "A01_RE60x40x3_ohne_Anbau.step")[0][0]))
        assert z1["anbauteile"] == "" and z1["trennung"] == "" and z1["gravur_anbau"] == ""


print("Fehler:", fehler)
sys.exit(1 if fehler else 0)
