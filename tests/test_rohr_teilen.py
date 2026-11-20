"""Rohr teilen (Plan 3D/Abwicklung P6.2, Patrick 20.11.2026 „Alles einbauen“):

- T1 rohr_teilen.teilen: Längen ergeben die Teilelänge, jede Kontur liegt in genau einem Teil (Lage in Teil 2 ab dem
  neuen Ende A), Muster werden aufgeteilt, Trennstelle je gerades Ende, gemessene Enden fallen weg
- T2 Kontur über der Trennstelle bzw. Lochfeld auf beiden Seiten: nicht geteilt, mit Grund; Stelle außerhalb: Grund
- T3 Im Angebot: Rechtsklick „Rohr teilen …“ nur bei einer Rohrposition ohne STEP-3D; Teil 1 bleibt die Position,
  Teil 2 kommt als neue Position dahinter, beide neu gerechnet (schneidweg), Rückgängig stellt alles wieder her

Aufruf: python tests/test_rohr_teilen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import rohr_teilen as rt, schneidweg as sw, skizze as sk  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ T1 teilen
qs = sk.Querschnitt(dict(form="Quadratrohr", a=40, b=40, wand=3))
E = dict(a=dict(winkel=45, umriss=[[0, 1], [5, 2]], gemessen=1), b=dict(winkel=30),
         konturen=[dict(art=sw.BOHRUNG, anzahl=4, abstand=100, d=10, x=100, seite="oben"),
                   dict(art=sw.LANGLOCH, anzahl=1, l=30, b=10, x=700, seite="vorne"),
                   dict(art=sw.BOHRUNG, anzahl=2, d=8)])            # ohne Lage: verteilt
t1, t2 = rt.teilen(E, 1000, 450, qs)
assert t1["laenge"] == 450 and t2["laenge"] == 550 and rt.summe_ok(E, 1000, t1, t2, qs)
k1, k2 = t1["eingaben"]["konturen"], t2["eingaben"]["konturen"]
assert k1[0]["anzahl"] == 4 and k1[0]["x"] == 100                     # 100, 200, 300, 400 in Teil 1
assert [k["art"] for k in k2] == [sw.LANGLOCH, sw.BOHRUNG] and k2[0]["x"] == 250
assert k1[1]["anzahl"] == 1 and k2[1]["anzahl"] == 1 and k1[1].get("x") is None   # verteilt: je eins
assert t1["eingaben"]["a"]["winkel"] == 45 and t1["eingaben"]["b"] == dict(winkel=0)
assert t2["eingaben"]["a"] == dict(winkel=0) and t2["eingaben"]["b"]["winkel"] == 30
assert "umriss" not in t1["eingaben"]["a"] and "gemessen" not in t1["eingaben"]["a"]
assert E["a"]["umriss"] and E["konturen"][0]["anzahl"] == 4                       # Eingabe unverändert
t1, t2 = rt.teilen(E, 1000, 250, qs)                                              # Muster aufgeteilt
assert t1["eingaben"]["konturen"][0]["anzahl"] == 2 and t2["eingaben"]["konturen"][0] == dict(
    E["konturen"][0], anzahl=2, x=50.0), t2["eingaben"]["konturen"]
ok("T1 teilen: Längen, Konturen je Teil (Muster aufgeteilt), Trennstelle gerade, gemessene Enden entfernt")

# ------------------------------------------------------------------ T2 nicht teilbar
r = rt.teilen(E, 1000, 705, qs)
assert r[0] is None and "Trennstelle" in r[1], r
r = rt.teilen(E, 1000, 0.5, qs)
assert r[0] is None and "zwischen" in r[1], r
LF = dict(konturen=[dict(art=sw.LOCHFELD, anzahl=4, abstand=50, d=8, lang=8, x=100)])
r = rt.teilen(LF, 500, 180, qs)
assert r[0] is None and "Lochfeld" in r[1], r
ok("T2 Kontur über der Trennstelle, Lochfeld auf beiden Seiten, Stelle außerhalb: nicht geteilt, mit Grund")

# ------------------------------------------------------------------ T3 im Angebot
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
a = beispiel_angebot.anlegen(db)
s = f.angebot_oeffnen(a)
p = s.positionen[2]                                           # Pos. 30 QR 40x40x3, 2150 mm
technik = dict(quelle=sw.QUELLE, a=dict(winkel=0), b=dict(winkel=0),
               konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=300, seite="oben"),
                         dict(art=sw.BOHRUNG, anzahl=1, d=10, x=1800, seite="oben")])
db.position_aendern(p["id"], "technik", json.dumps(technik))
s.neu_laden()
s.pos_ansicht.selectRow(2)
assert "Rohr teilen …" in s._pos_menue_anpassen()
anzahl = len(s.positionen)
assert s.rohr_teilen(zeile=2, x=1000)
assert len(s.positionen) == anzahl + 1
eins = next(q for q in s.positionen if q["id"] == p["id"])
zwei = next(q for q in s.positionen if q["artikel"] == "4711-003-2")
assert eins["laenge"] == 1000 and zwei["laenge"] == 1150, (eins["laenge"], zwei["laenge"])
assert json.loads(zwei["technik"])["konturen"][0]["x"] == 800
assert eins["schneidweg"] > 0 and zwei["schneidweg"] > 0
assert eins["einstiche"] == 3 and zwei["einstiche"] == 3, (eins["einstiche"], zwei["einstiche"])   # 2 Enden + 1 Bohrung
s.rueckgaengig()
assert len(s.positionen) == anzahl and next(q for q in s.positionen if q["id"] == p["id"])["laenge"] == 2150
db.netz_speichern(p["id"], b"netz")                           # aus STEP: nicht teilen
s.neu_laden()
assert "Rohr teilen …" not in s._pos_menue_anpassen() and not s.rohr_teilen(zeile=2, x=1000)
ok("T3 Angebot: Rohr teilen legt Teil 2 als neue Position an, beide gerechnet, Rückgängig; STEP-Teile gesperrt")
print("Alles in Ordnung.")
