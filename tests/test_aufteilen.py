"""Verschmolzene Teile aufteilen (Vorschlag N3, Patrick 07.11.2026): ein Körper, den die Messung gelb als „mehrere Teile
in einem Körper“ markiert (Platte mit angeschweißter Mutter), lässt sich im Prüfdialog mit „Aufteilen“ an Sechskant
bzw. Kugel trennen. Beide Teile werden einzeln gemessen, Lage wie in der STEP, die Mutter wird Normteil (N6: in der
Schweißbaugruppe Zukauf). Ohne erkennbaren Anbau bleibt der Körper, wie er ist.

Aufruf: python tests/test_aufteilen.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER))
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import step_aufteilen  # noqa: E402
import step_messen  # noqa: E402
from formen_baukasten import kugel, ohne, plus, prisma, quader, schreibe, verschiebe, zyl  # noqa: E402
from rohrlaser import step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TMP = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


def sechskant(sw, h, z, x, y):
    r = sw / math.sqrt(3)
    ecken = [(r * math.cos(math.radians(30 + 60 * i)), r * math.sin(math.radians(30 + 60 * i))) for i in range(6)]
    return verschiebe(prisma(ecken, h), x, y, z)


mutter = ohne(sechskant(36, 20, 9.5, 73, 20), zyl(12, 20, 9.5, 73, 20))
platte_mutter = plus(quader(146, 40, 9.5), mutter)
teile = step_aufteilen.teilen(platte_mutter)
assert [n for n, _ in teile] == ["Mutter SW 36", "Grundteil"], teile
v = [step_aufteilen._volumen(s) for _, s in teile]
assert abs(v[0] - (2 * math.sqrt(3) * 18 ** 2 - math.pi * 144) * 20) < 1 and abs(v[1] - 146 * 40 * 9.5) < 1, v
ok("Platte 146 × 40 × 9,5 mit Mutter SW 36: Mutter und Platte mit genau ihrem Volumen getrennt")

teile = step_aufteilen.teilen(plus(quader(100, 40, 10), kugel(10, 20)))
assert [n for n, _ in teile] == ["Kugel Ø20", "Grundteil"], teile
assert step_aufteilen.teilen(quader(100, 40, 10)) == [] and step_aufteilen.teilen(ohne(sechskant(19, 10, 0, 0, 0),
                                                                                     zyl(6, 10))) == []
ok("Platte mit Kugel: Kugel Ø20 abgetrennt; glatte Platte und Mutter allein: nichts zu trennen")

schreibe({"Halter": platte_mutter}, TMP)
pfad = TMP / "Halter.step"
aus = TMP / "m.txt"
step_messen.main(["--ausgabe", str(aus), str(pfad)])
mw = step.lies_messwerte(aus)
assert len(mw) == 1 and step.MEHRTEILIG_HINWEIS in mw[0]["hinweise"], mw
mw[0]["_pfad"] = str(pfad)
assert step.mehrteilig_koerper(mw[0])
ok("Messung: Körper gelb „Mehrere Teile in einem Körper?“, Aufteilen möglich")


def aufteilen_messen(m):
    """Wie AngebotFenster._aufteilen_messen, nur ohne STEP-Import.exe."""
    t = Path(tempfile.mkdtemp())
    step_messen.main(["--ausgabe", str(t / "a.txt"), "--netze", str(t / "netze"), "--aufteilen",
                      str(int(float(m["koerper"]))), m["_pfad"]])
    return step.aufteilen_ergebnis(m, t / "a.txt", t / "netze")


neu = aufteilen_messen(dict(mw[0]))
assert [n["bauteil"].split(" – ")[-1] for n in neu] == ["Mutter SW 36", "Grundteil"], [n["bauteil"] for n in neu]
mu, gr = neu
assert all(n["datei"] == "Halter.step" and n["_pfad"] == str(pfad) and n.get("_netz") for n in neu)
assert gr["artikel"] == mw[0]["artikel"] and mu["artikel"] == mw[0]["artikel"] + "-1", [n["artikel"] for n in neu]
assert mu["_normteil"] == "Mutter" and step.normteil_name(mu) == "Mutter SW 36"
assert gr["profilform"] == "Flachstahl" and round(float(gr["abm_a"]), 2) == 40 and round(float(gr["abm_b"]), 2) == 9.5, \
    (gr["profilform"], gr["abm_a"], gr["abm_b"])
assert step.MEHRTEILIG_HINWEIS not in (gr.get("hinweise") or "")
ok("--aufteilen: Mutter SW 36 (Normteil, Artikel -1) und Grundteil Flachstahl 40 × 9,5 (Artikel bleibt), mit 3D-Netz")

kopie = dict(mw[0])
kopie["_pfad"] = str(TMP / "fehlt.step")
leer = TMP / "leer"
leer.mkdir()
schreibe({"Platte": quader(100, 40, 10)}, leer)
p2 = dict(mw[0], _pfad=str(leer / "Platte.step"))
assert aufteilen_messen(p2) is None
ok("Körper ohne Sechskant/Kugel: nichts aufgeteilt")

# ------------------------------------------------------------------ Prüfdialog
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(TMP / "a.db")
k = db.kontext()
werte = [dict(mw[0])]
d = StepPruefDialog(None, werte, k, "S235-10219", 1, zukauf_liste=[], aufteilen=aufteilen_messen)
assert not d.aufteil_zeile.isHidden() and not d.aufteil_knopf.isHidden(), d.aufteil_info.text()
assert "1 Körper aus mehreren verschmolzenen Teilen" in d.aufteil_info.text()
assert d.aufteilen() == 1 and len(werte) == 2, werte
assert "aufgeteilt (Mutter SW 36 + Grundteil)" in d.aufteil_info.text(), d.aufteil_info.text()
assert d.aufteil_knopf.isHidden() and "Halter.step" in d.mehrteilig
d.werte_schreiben()
ok("Prüfdialog: Zeile „Aufteilen“ über der Liste, nach dem Klick zwei Teile, die Datei ist jetzt eine Baugruppe")
d2 = StepPruefDialog(None, [dict(mw[0])], k, "S235-10219", 1, zukauf_liste=[])
assert d2.aufteil_zeile.isHidden()
ok("Ohne Messprogramm (aufteilen=None): keine Zeile")

erg = step.uebernehmen([dict(n, _uebernehmen=True) for n in werte], [], k, db.zeilen("gewinde"), None, "S235-10219",
                       1, zukauf_liste=[])
arten = sorted(str(p.get("art") or p.get("profil") or "Laserteil") for p in erg["positionen"])
assert any(p.get("bezeichnung") == "Mutter SW 36" for p in erg["positionen"]), erg["positionen"]
ok("Übernahme: Mutter SW 36 als Zukaufteil aus der Normteil-Liste, Platte als Laserteil (" + ", ".join(arten) + ")")
db.con.close()
print("Aufteilen: alle Tests bestanden.")
