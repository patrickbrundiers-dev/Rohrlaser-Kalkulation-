"""Normteile mit Preis (Vorschlag N6, Patrick 07.11.2026): erkannte Normteile (Kugel, Mutter/Schraube mit Sechskant,
Begriff im Bauteilnamen) kommen angehakt als Zukaufteil in Schweißbaugruppe bzw. Satz. Preis aus der Normteil-Liste =
Zukaufartikel der Kategorie Normteile mit gleicher Bezeichnung; ohne passenden Artikel wird einer ohne EK angelegt
(gelb: EK fehlt), beim nächsten Import gilt sein EK. Nicht angehakt bleibt es wie bisher draußen.

Aufruf: python tests/test_normteile_preis.py
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
from OCP.IFSelect import IFSelect_RetDone  # noqa: E402
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer  # noqa: E402

import step_messen  # noqa: E402
from formen_baukasten import kugel, ohne, prisma, zyl  # noqa: E402
from rohrlaser import importprofil, step, zukauf  # noqa: E402
from rohrlaser.angebot import ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

TMP = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


def schreiben(name, form):
    w = STEPControl_Writer()
    w.Transfer(form, STEPControl_AsIs)
    assert w.Write(str(TMP / f"{name}.step")) == IFSelect_RetDone


def sechskant(sw, h):
    r = sw / math.sqrt(3)
    return prisma([(r * math.cos(math.radians(30 + 60 * i)), r * math.sin(math.radians(30 + 60 * i))) for i in range(6)], h)


schreiben("Kugel_8", kugel(4.365, 0))
schreiben("Mutter_M12", ohne(sechskant(19, 10), zyl(6, 10)))
schreiben("Schraube_M16", zyl(8, 40))
aus = TMP / "m.txt"
step_messen.main(["--ausgabe", str(aus)] + [str(TMP / f"{n}.step") for n in ("Kugel_8", "Mutter_M12", "Schraube_M16")])
MW = step.lies_messwerte(aus)
NAME = {"Mutter_M12": "ISO 4032 M12:1", "Schraube_M16": "DIN 933 M16x40:2"}   # Normteil über den CAD-Bauteilnamen
for m in MW:
    m["bauteil"] = NAME.get(Path(m["datei"]).stem, m.get("bauteil"))
importprofil.anwenden(MW, einstellungen=dict(step_normteile="ISO; DIN"))
JE = {Path(m["datei"]).stem: m for m in MW}
assert all(m.get("_normteil") for m in MW), [(m["datei"], m.get("profilform"), m.get("drehfraes")) for m in MW]
assert step.normteil_name(JE["Kugel_8"]) == "Kugel Ø8,73", step.normteil_name(JE["Kugel_8"])
assert step.normteil_name(JE["Mutter_M12"]) == "ISO 4032 M12", step.normteil_name(JE["Mutter_M12"])
assert step.normteil_name(JE["Schraube_M16"]) == "DIN 933 M16x40"
ok("Normteile erkannt (Form bzw. Bauteilname), Bezeichnung für die Preisliste: "
   + ", ".join(step.normteil_name(m) for m in MW))

db = Datenbank(TMP / "n.db")
k = db.kontext()
mw = [dict(m, _uebernehmen=True, _stueck=4) for m in MW]
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", 4, zukauf_liste=db.zukauf_artikel_liste())
pos = erg["positionen"]
assert len(pos) == 3 and all(p["art"] == ZUKAUFTEIL and p["stueck"] == 4 for p in pos), pos
neu = {w["bezeichnung"]: (w, b) for w, b in erg["zukauf_neu"].values()}
assert set(neu) == {p["bezeichnung"] for p in pos}
assert all(w["kategorie"] == step.NORMTEIL_KATEGORIE and w["artikeltyp"] == step.NORMTEIL_TYP and b[0]["preise"] == []
           for w, b in neu.values())
ok("Angehakt: je Normteil ein Zukaufteil, neuer Artikel der Kategorie Normteile ohne EK (EK fehlt)")

w, b = neu["Kugel Ø8,73"]
aid = db.zukauf_speichern(None, w, [dict(b[0], preise=[dict(ab=1, preis=0.12)])])
erg = step.uebernehmen([dict(JE["Kugel_8"], _uebernehmen=True)], [], k, db.zeilen("gewinde"), None, "S235-10219", 10,
                       zukauf_liste=db.zukauf_artikel_liste())
assert erg["positionen"][0]["_zukauf"] == {"artikel_id": aid} and not erg["zukauf_neu"], erg["positionen"]
assert not zukauf.ek_fehlt(db.zukauf_artikel(aid))
ok("Zweiter Import: gleiche Bezeichnung findet den Artikel der Preisliste mit EK 0,12 €")

zwei = [dict(JE["Kugel_8"], _uebernehmen=True, _stueck=2), dict(JE["Kugel_8"], _uebernehmen=True, _stueck=3)]
erg = step.uebernehmen(zwei, [], k, db.zeilen("gewinde"), None, "S235-10219", 1, zukauf_liste=db.zukauf_artikel_liste())
assert len(erg["positionen"]) == 1 and erg["positionen"][0]["stueck"] == 5, erg["positionen"]
ok("Dasselbe Normteil zweimal: eine Position, Stückzahl addiert")

erg = step.uebernehmen([dict(m) for m in MW], [], k, db.zeilen("gewinde"), None, "S235-10219", 1,
                       zukauf_liste=db.zukauf_artikel_liste())
assert not erg["positionen"], erg["positionen"]
ok("Nicht angehakt (Einzelteile): Normteile bleiben wie bisher draußen")
db.con.close()
print("Normteile mit Preis: alle Tests bestanden.")
