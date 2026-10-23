"""DXF-Export der Abwicklung aus dem Blech-Editor (Plan S4, Patrick 23.10.2026 „3a“):
- D1 Zuschnitt Rechteck mit Eckradius und Innenkonturen (Bohrung, Langloch längs und quer, Rechteck, Polygon): die
  Datei liest sich wieder gleich, Schnittlänge Außenkontur und Innenkonturen wie im Richtpreis (blech.rechnen).
- D2 Kantteil: Biegelinien auf den Layern hoch/runter an der Lage der Abwicklung; mehrachsig gekantet mit den
  Biegelinien aus dem STEP-Import; Polygon-Außenkontur.
- D3 Layernamen aus der Einstellung (unzulässige Zeichen ersetzt, leere = Vorgabe), Biegelinien abschaltbar,
  Hinweise für Konturen ohne Lage, mehrfache und sonstige Konturen.
- D4 Blech-Editor: Knopf „DXF speichern …“ schreibt eine lesbare Datei (R12, Codepage 1252, Umlaute).

Aufruf: python tests/test_blech_dxf.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import blech, dxf, schneidweg as sw  # noqa: E402


def ok(t):
    print("OK    ", t)


def gleich(a, b, tol=1e-4):
    assert len(a) == len(b), (len(a), len(b))
    for x, y in zip(a, b):
        assert x[0] == y[0] and x[1] == y[1], (x, y)
        for u, v in zip(x[2:], y[2:]):
            if isinstance(u, tuple):
                assert all(abs(p - q) <= tol for p, q in zip(u, v)), (x, y)
            elif isinstance(u, float):
                assert abs(u - v) <= tol, (x, y)
            else:
                assert u == v, (x, y)


def zurueck(elem, namen=None):
    """Schreiben und wieder lesen; Layernamen zurück auf die Arten."""
    namen = namen or dxf.layer_namen()
    art = {v: k for k, v in namen.items()}
    return [(el[0], art[el[1]], *el[2:]) for el in dxf.lesen(dxf.schreiben(elem, namen))]


# ------------------------------------------------------------------ D1 Zuschnitt
konturen = [dict(art=sw.BOHRUNG, anzahl=1, d=10, x=30, y=50),
            dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=80, y=50),
            dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=110, y=50, quer=True),
            dict(art=sw.RECHTECK, anzahl=1, b=20, h=15, r=2, x=150, y=30),
            dict(art=sw.POLYGON, anzahl=1, punkte="0,0; 20,0; 10,15", x=170, y=75)]
e = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=200, breite=100, eckradius=10, konturen=konturen)
zs = blech.zuschnitt(e)
elem, hinweise = dxf.elemente(e, zs, beschriftung="Lasche 200 × 100 × 3 S235JR")
assert hinweise == []
assert sum(1 for el in elem if el[0] == "ARC" and el[1] == dxf.AUSSEN) == 4
gleich(zurueck(elem), elem)
lg = dxf.schnittlaenge(elem)
innen = sum(sw.kontur(z)[0] for z in konturen)
assert abs(lg[dxf.AUSSEN] - zs["aussen"]) < 1e-6, (lg[dxf.AUSSEN], zs["aussen"])
assert abs(lg[dxf.INNEN] - innen) < 1e-6, (lg[dxf.INNEN], innen)
# Lage: Bohrung als Kreis um (30, 50), Langloch quer steht hoch (Hüllmaß 10 × 30)
assert ("CIRCLE", dxf.INNEN, (30.0, 50.0), 5.0) in elem
quer = [p for el in dxf.kontur_elemente(konturen[2], 110, 50) for p in dxf._punkte(el)]
assert abs(max(y for _, y in quer) - min(y for _, y in quer) - 30) < 1e-9
assert abs(max(x for x, _ in quer) - min(x for x, _ in quer) - 10) < 1e-9
ok("D1 Zuschnitt mit Eckradius und Innenkonturen: Datei liest sich gleich, Schnittlängen wie im Richtpreis")

# ------------------------------------------------------------------ D2 Kantteil, mehrachsig, Polygon
kant = dict(art=blech.KANTTEIL, dicke=2, kantlaenge=300, form=blech.RECHTECK,
            schenkel=[dict(laenge=50, winkel=90), dict(laenge=80, winkel=-90), dict(laenge=40)], konturen=[])
zk = blech.zuschnitt(kant)
ek, _ = dxf.elemente(kant, zk)
hoch = [el for el in ek if el[1] == dxf.HOCH]
runter = [el for el in ek if el[1] == dxf.RUNTER]
(lage1, *_), (lage2, *_) = zk["biegungen"]
assert len(hoch) == 1 and len(runter) == 1
assert hoch[0][2] == (0.0, lage1) and hoch[0][3] == (300.0, lage1) and runter[0][2][1] == lage2
assert abs(dxf.schnittlaenge(ek)[dxf.AUSSEN] - zk["aussen"]) < 1e-6
gleich(zurueck(ek), ek)
schale = dict(art=blech.ZUSCHNITT, form=blech.POLYGON, dicke=2, punkte="10,10; 230,10; 230,190; 10,190",
              konturen=[], kantungen=2,
              biegelinien=[dict(punkte=[[30, 10], [30, 190]], winkel=-90), dict(punkte=[[210, 10], [210, 190]],
                                                                                 winkel=90)])
zp = blech.zuschnitt(schale)
ep, _ = dxf.elemente(schale, zp)
assert [el for el in ep if el[1] == dxf.RUNTER][0][2:] == ((20.0, 0.0), (20.0, 180.0))       # Polygon ab 0, 0
assert [el for el in ep if el[1] == dxf.HOCH][0][2:] == ((200.0, 0.0), (200.0, 180.0))
assert abs(dxf.schnittlaenge(ep)[dxf.AUSSEN] - zp["aussen"]) < 1e-6
ok("D2 Kantteil: Biegelinien hoch/runter an der Lage der Abwicklung; mehrachsig und Polygon-Außenkontur")

# ------------------------------------------------------------------ D3 Einstellungen und Hinweise
namen = dxf.layer_namen("Kontur außen; ; Biegen+; Biegen-")
assert namen[dxf.AUSSEN] == "KONTUR_AUSSEN" and namen[dxf.INNEN] == "INNENKONTUR"
assert namen[dxf.HOCH] == "BIEGEN_" and namen[dxf.TEXT] == "BESCHRIFTUNG"
text = dxf.schreiben(ek, namen)
assert "KONTUR_AUSSEN" in text and "AC1009" in text
assert not [el for el in dxf.elemente(kant, zk, biegelinien=False)[0] if el[1] in (dxf.HOCH, dxf.RUNTER)]
frei = dict(e, konturen=[dict(art=sw.BOHRUNG, anzahl=4, d=8), dict(art=sw.SONSTIGE, anzahl=1, laenge=50)])
_, h = dxf.elemente(frei, blech.zuschnitt(frei))
assert len(h) == 3 and "ohne Lage" in h[0] and "Anzahl > 1" in h[1] and "sonstige" in h[2], h
from rohrlaser.stammdaten import EINSTELLUNGEN  # noqa: E402
vorgaben = {x.name: x.vorgabe for x in EINSTELLUNGEN}
assert vorgaben["blech_dxf_layer"] == dxf.LAYER_VORGABE and vorgaben["blech_dxf_biegelinien"] == "ja"
ok("D3 Layernamen aus der Einstellung, Biegelinien abschaltbar, Hinweise für ungenaue Konturen")

# ------------------------------------------------------------------ D4 Blech-Editor
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
werkstoff = sorted(z["blech_werkstoff_id"] for z in db.zeilen("blech_werkstoffe"))[0]
d = BlechDialog(None, db, dict(e, werkstoff=werkstoff), kopf=dict(bezeichnung="Lasche Größe 1", artikelnr="L-01"))
d.stumm = True
assert d.dxf_knopf.text() == "DXF speichern …"
pfad = tmp / "L-01.dxf"
assert d.dxf_speichern(str(pfad)) == []
roh = pfad.read_bytes()
assert b"\r\n" in roh and "Größe".encode("cp1252") in roh
gelesen = dxf.lesen(roh.decode("cp1252"))
texte = [el for el in gelesen if el[0] == "TEXT"]
assert len(texte) == 1 and texte[0][4] == "L-01 Lasche Größe 1" and texte[0][1] == "BESCHRIFTUNG"
assert abs(dxf.schnittlaenge(gelesen)["AUSSENKONTUR"] - zs["aussen"]) < 1e-3
assert math.isclose(dxf.schnittlaenge(gelesen)["INNENKONTUR"], innen, rel_tol=1e-6)
db.schliessen()
ok("D4 Blech-Editor: DXF speichern schreibt eine lesbare R12-Datei mit Beschriftung und Umlauten")
