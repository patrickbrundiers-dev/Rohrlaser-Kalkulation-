"""Kostentreiber im 3D farbig (CAD-005, Plan Phase 3 und 4, Patrick 13.11.2026 „Alles einbauen“, E4 = a):

- Stufen nach dem €-Anteil: ab 50 % rot, 25–50 % orange, 10–25 % gelb, unter 10 % grün; Summe 0 = nichts
- Baugruppe/Satz: Teile in den Arten KO0 … KO3 (mit Legende), gewählte Teile bleiben blau
- Ansicht3D: Linien je Merkmal bzw. Bereich längs der Achse, Legende ergänzt, aus = weg
- Teile-Editor Rohr und Blech: Knopf „Einfärben“, Werte aus der Bearbeitungsliste
- Baugruppen-Ansicht: Knopf „Kosten“; bg_kosten.teil_kosten = Selbstkosten je Stück

Aufruf: python tests/test_kostenfarben.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import kostenfarben as kf  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ Stufen
st = kf.stufen({"a": 60, "b": 30, "c": 6, "d": 4})
assert {k: s for k, (s, _) in st.items()} == {"a": 0, "b": 1, "c": 3, "d": 3}, st
assert abs(st["a"][1] - 0.6) < 1e-9
assert kf.stufen({"a": 50, "b": 25, "c": 15, "d": 10}) and \
    [kf.stufen({"a": 50, "b": 25, "c": 15, "d": 10})[k][0] for k in "abcd"] == [0, 1, 2, 2]
assert kf.stufen({"a": 0, "b": 0}) == {} and kf.stufen({}) == {} and kf.stufen(None) == {}
assert kf.stufen({"a": -5, "b": 10})["a"][0] == 3          # negativ zählt als 0
assert [t for t, _ in kf.legende({0, 3})] == ["Kosten ab 50 %", "Kosten unter 10 %"]
ok("Stufen nach Anteil (rot ab 50 %, orange, gelb, grün unter 10 %); Summe 0 färbt nichts")

# ------------------------------------------------------------------ Baugruppe: Arten KO
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import ansicht3d as a3  # noqa: E402

app = QApplication.instance() or QApplication([])
wuerfel = dict(p=[0, 0, 0, 1, 0, 0, 0, 1, 0], t={"A": [0, 1, 2]}, l={}, lage=[0, 0, 0, 0, 0, 1, 1, 0, 0])
netz, _ = a3.baugruppe([dict(wuerfel), dict(wuerfel), dict(wuerfel)], hervor={2}, kosten={0: 0, 1: 3, 2: 0})
assert set(netz["t"]) == {"KO0", "KO3", "S"}, netz["t"].keys()
assert all(a in a3.FARBE and a in a3.REIHE for a in kf.ARTEN)
assert [(a, f) for a, _, f, _ in a3.ARTEN if a in kf.ARTEN] == [(s[0], s[2]) for s in kf.STUFEN]
netz2, _ = a3.baugruppe([dict(wuerfel), dict(wuerfel)])
assert set(netz2["t"]) == {"F0", "F1"}
ok("Baugruppe/Satz: Teile in den Kostenfarben KO0 … KO3, gewählte bleiben blau; ohne kosten wie bisher")

# ------------------------------------------------------------------ Ansicht3D: Linien, Bereiche, Legende
from PySide6.QtGui import QImage, QPainter  # noqa: E402

v = a3.Ansicht3D()
v.resize(400, 300)
v.setzen(dict(p=[0, 0, 0, 10, 0, 0, 0, 10, 0, 0, 0, 100], t={"A": [0, 1, 2]}, l={"K": [[0, 0, 0, 0, 0, 100]]},
              li={"K": ["kontur:0"]}), "Test")
v.kosten_setzen(linien={"kontur:0": kf.farbe(0)}, legende=kf.legende({0}))
assert v.kosten_linien and v.kosten_legende == [("Kosten ab 50 %", "#C62828")]
bild = QImage(400, 300, QImage.Format_ARGB32)
p = QPainter(bild)
v._beschriften(p)               # zeichnet Legende und Kostenlinien ohne Fehler
p.end()
v.kosten_setzen(z_bereiche=[(0, 50, "#2E7D32")], legende=kf.legende({3}))
assert v.kosten_z and not v.kosten_linien
v.kosten_setzen()
assert not v.kosten_linien and not v.kosten_z and v.kosten_legende == []
ok("3D-Ansicht: Kostenfarben je Linie oder Achsbereich mit Legende; aus = weg")

# ------------------------------------------------------------------ Teile-Editor Rohr
from rohrlaser import schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
k = db.kontext()
technik = dict(quelle=sw.QUELLE, a=dict(winkel=30, achse="über Höhe"), b=dict(winkel=0),
               konturen=[dict(art=sw.BOHRUNG, anzahl=8, d=10, x=100, seite="oben"),
                         dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=300, seite="oben")])
p_ = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10, technik=json.dumps(technik))
d = SchneidwegDialog(None, p_, k.profile["QR 40x40x3"], dict(maschine="T11", stange=6000), k, db.tabellen(), db)
ed = d.editor
assert ed.kosten_knopf.isCheckable() and not ed.kosten_knopf.isChecked()
a = ed.ansicht()
assert a is not None and not a.kosten_linien and not a.kosten_z
ed.kosten_knopf.setChecked(True)
bearb = ed._bearbeitungen()
assert bearb, "Bearbeitungsliste fehlt"
erwartet = {mid: s for mid, (s, _) in kf.stufen({m: e for m, (_, e) in bearb[0].items()}).items()}
assert ed._kosten_zeigen() == erwartet and erwartet
assert (a.kosten_linien or a.kosten_z) and a.kosten_legende
assert set(a.kosten_legende) == set(kf.legende(set(erwartet.values())))
teuer = min(erwartet, key=erwartet.get)
assert teuer == max(bearb[0], key=lambda m: bearb[0][m][1])        # teuerstes Merkmal = höchste Stufe
ed.aktualisieren()
assert a.kosten_linien or a.kosten_z                                # bleibt beim Neurechnen an
ed.kosten_knopf.setChecked(False)
assert not a.kosten_linien and not a.kosten_z and not a.kosten_legende
ok(f"Teile-Editor Rohr: „Einfärben“ färbt die Merkmale nach der Bearbeitungsliste (teuerstes: {teuer})")

# ------------------------------------------------------------------ Teile-Editor Blech
from rohrlaser import blech  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402

roh = dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, laenge=300, breite=200, dicke=3, werkstoff="S235JR", stueck=5,
           konturen=[dict(art=sw.BOHRUNG, anzahl=12, d=10, x=30, y=30), dict(art=sw.BOHRUNG, anzahl=1, d=20, x=150,
                                                                            y=100)])
bd = BlechDialog(None, db, roh, neu=False)
be = bd.editor
be.aktualisieren()
be.kosten_knopf.setChecked(True)
bb = be._bearbeitungen()
if bb and kf.stufen({m: e for m, (_, e) in bb[0].items()}):
    ab = be.ansicht()
    assert ab.kosten_linien and ab.kosten_legende, (ab.kosten_linien, bb)
    ok("Teile-Editor Blech: Linien der Merkmale in den Kostenfarben")
else:
    assert be._kosten_zeigen() == {}
    ok("Teile-Editor Blech: ohne Zeiten bleibt das 3D ungefärbt")

# ------------------------------------------------------------------ Baugruppen-Ansicht, Selbstkosten je Teil
from rohrlaser import bg_kosten  # noqa: E402
from rohrlaser.baugruppe_ansicht import BaugruppenAnsicht  # noqa: E402

gerufen = []
ba = BaugruppenAnsicht(geaendert=lambda: gerufen.append(ba.kosten))
assert ba.kosten is False and ba.kosten_knopf.isCheckable()
ba.kosten_knopf.setChecked(True)
assert ba.kosten is True and gerufen == [True]
assert bg_kosten.teil_kosten([dict(id=1), dict(id=2), dict()], [dict(selbst_teil=12.5), None, dict(selbst_teil=3)]) \
    == {1: 12.5}
ok("Baugruppe und Satz in 3D: Knopf „Kosten“ zeichnet neu; Selbstkosten je Teil aus der Kalkulation")
print("alle Prüfungen bestanden")
