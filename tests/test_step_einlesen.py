"""Prüft das Einlesen von STEP-Dateien (Teile in tests/step_import, dazu T01 und die Baugruppe T08):
Einheiten (Zoll, Meter -> mm), Flächenmodelle (geschlossen: genäht und gemessen, offen: gemeldet statt verworfen),
defekte und leere Dateien, Körperdaten (Volumen, Oberfläche, Flächen, Kanten, Hüllquader, Geometrieprüfung).

Sollwerte aus den Konstruktionsmaßen in tests/erzeuge_testteile.py.
Aufruf: python tests/test_step_einlesen.py
"""
import math
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
from step_geometrie import analysiere_datei  # noqa: E402

IMP = HIER / "step_import"
pi = math.pi
fehler = 0


def nah(ist, soll, tol, was):
    assert abs(ist - soll) <= tol, f"{was} ist {ist:.4f}, soll {soll:.4f}"


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


@fall("I01 Zoll wird in mm gemessen")
def _():
    (t,) = analysiere_datei(IMP / "I01_RE60x40x2_L1000_Zoll.step")
    assert t.einheit == "inch" and t.koerperart == "Volumenkörper" and t.gueltig, (t.einheit, t.koerperart)
    assert t.profilform == "Rechteckrohr", t.profilform
    nah(t.abm_a, 60, 0.01, "Breite"); nah(t.abm_b, 40, 0.01, "Höhe"); nah(t.wandstaerke, 2, 0.01, "Wand")
    nah(t.laenge, 1000, 0.01, "Länge")
    fl = (2400 - (4 - pi) * 16) - (56 * 36 - (4 - pi) * 4)
    nah(t.volumen, fl * 1000, 5, "Volumen")


@fall("I02 Meter wird in mm gemessen")
def _():
    (t,) = analysiere_datei(IMP / "I02_RR42-4x2_L1000_Meter.step")
    assert t.einheit == "m" and t.profilform == "Rundrohr", (t.einheit, t.profilform)
    nah(t.abm_a, 42.4, 0.01, "Ø"); nah(t.wandstaerke, 2, 0.01, "Wand"); nah(t.laenge, 1000, 0.01, "Länge")


@fall("I03 geschlossenes Flächenmodell wird genäht und gemessen")
def _():
    (t,) = analysiere_datei(IMP / "I03_QR40x2_L800_Flaechenmodell.step")
    assert t.koerperart == "aus Flächenmodell genäht" and t.gueltig, t.koerperart
    assert any("Flächenmodell" in h for h in t.hinweise), t.hinweise
    assert t.profilform == "Quadratrohr", t.profilform
    nah(t.abm_a, 40, 0.01, "Seite"); nah(t.wandstaerke, 2, 0.01, "Wand"); nah(t.laenge, 800, 0.01, "Länge")


@fall("I04 offenes Flächenmodell wird gemeldet, nicht verworfen")
def _():
    (t,) = analysiere_datei(IMP / "I04_Flaechenmodell_offen.step")
    assert t.koerperart == "Flächenmodell offen" and t.profilform == "" and t.laenge == 0, (t.koerperart, t.profilform)
    assert any("nicht messbar" in h for h in t.hinweise), t.hinweise
    nah(t.oberflaeche, 2 * pi * 21.2 * 500, 0.5, "Fläche")
    assert t.n_flaechen == 1 and t.volumen == 0


for datei in ("I05_defekt", "I06_leer"):
    @fall(f"{datei} wird als nicht lesbar gemeldet")
    def _():
        try:
            analysiere_datei(IMP / f"{datei}.step")
        except ValueError as e:
            assert "nicht lesbar" in str(e), e
        else:
            raise AssertionError("keine Fehlermeldung")


@fall("T01 Körperdaten (Volumen, Oberfläche, Flächen, Hüllquader)")
def _():
    (t,) = analysiere_datei(HIER / "step" / "T01_RR42-4x2_L1250.step")
    a = pi / 4 * (42.4 ** 2 - 38.4 ** 2)
    nah(t.volumen, a * 1250, 1, "Volumen")
    nah(t.oberflaeche, pi * (42.4 + 38.4) * 1250 + 2 * a, 1, "Oberfläche")
    assert t.einheit == "mm" and t.gueltig and t.koerperart == "Volumenkörper"
    assert t.n_flaechen >= 4, t.n_flaechen
    for ist, soll in zip(sorted(t.huelle), sorted((42.4, 42.4, 1250))):
        nah(ist, soll, 0.001, "Hüllquader")


@fall("T08 Baugruppe: alle 4 Körper einzeln gemessen")
def _():
    teile = analysiere_datei(HIER / "step_satz" / "T08_Gestell_Baugruppe.step")
    assert [t.profilform for t in teile] == ["Quadratrohr"] * 3 + ["Rundrohr"], [t.profilform for t in teile]
    assert [t.koerper for t in teile] == [1, 2, 3, 4]


@fall("STEP-Import.exe-Ausgabe: nicht messbare Körper und defekte Dateien stehen als Zeile drin")
def _():
    with tempfile.TemporaryDirectory() as tmp:
        aus = Path(tmp) / "m.txt"
        r = subprocess.run([sys.executable, str(HIER.parent / "programm" / "step_messung" / "step_messen.py"),
                            "--ausgabe", str(aus), str(IMP)], capture_output=True)
        assert r.returncode == 1, r.returncode     # 1 = mindestens eine Datei mit Fehler
        zeilen = [z.split("\t") for z in aus.read_text(encoding="utf-8").splitlines()]
    kopf = zeilen[0]
    daten = [dict(zip(kopf, z)) for z in zeilen[1:]]
    assert [d["datei"] for d in daten] == sorted(p.name for p in IMP.glob("*.step")), [d["datei"] for d in daten]
    nach = {d["datei"]: d for d in daten}
    assert nach["I04_Flaechenmodell_offen.step"]["koerperart"] == "Flächenmodell offen"
    assert "nicht lesbar" in nach["I05_defekt.step"]["fehler"]
    assert nach["I01_RE60x40x2_L1000_Zoll.step"]["einheit"] == "inch"


sys.exit(1 if fehler else 0)
