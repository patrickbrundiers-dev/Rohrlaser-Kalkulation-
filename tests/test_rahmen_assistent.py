"""Rahmen-Assistent (Plan „Baugruppen automatisch und innovativ“, P4; Patrick 25.10.2026 „Alle a“, 6a):
- rahmen.bauen: Rechteckrahmen mit Gehrung (außen B × H), stumpf (Senkrechte H − 2 × Profil, Rundrohr Mitte zu Mitte
  mit Sattel), Quader mit Querrohren; Außenmaße stimmen im 3D, gleiche Rohre sind ein Teil, Stöße wie aus der
  STEP-Messung; unmögliche Maße melden
- im Angebot: Neue Position → Rahmen-Assistent legt den Satz mit Positionen, Netzen und Stößen an; Satz in 3D zeigt
  alle Rohre, schlägt beim Gehrungsrahmen den Knickrahmen vor; „stumpf mit Steckverbindungen“ steckt alle Stöße und
  ist steckbar

Aufruf: python tests/test_rahmen_assistent.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import baugruppe_vorschlaege as bv, rahmen, schneidweg as sw  # noqa: E402
from rohrlaser.baugruppe_ansicht import in_lage  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.neue_position import RAHMEN  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(t):
    print("OK    ", t)


QR = dict(form="Quadratrohr", a=40.0, b=40.0, wand=2.0)
RE = dict(form="Rechteckrohr", a=60.0, b=40.0, wand=2.0)
RD = dict(form="Rundrohr", a=48.3, wand=2.0)


def huelle(erg, profil):
    lo, hi = [1e9] * 3, [-1e9] * 3
    for t in erg["teile"]:
        n = rahmen.netz(t, profil)
        p = n["p"]
        for lage in n["lagen"]:
            for i in range(0, len(p), 3):
                q = in_lage(p[i:i + 3], lage)
                for k in range(3):
                    lo[k], hi[k] = min(lo[k], q[k]), max(hi[k], q[k])
    return [round(v, 1) for v in lo], [round(v, 1) for v in hi]


# ------------------------------------------------------------------ Geometrie
g = rahmen.bauen(QR, rahmen.RAHMEN, 1000, 600, ecken=rahmen.GEHRUNG)
assert [(t["laenge"], len(t["lagen"])) for t in g["teile"]] == [(1000.0, 2), (600.0, 2)] and not g["stoesse"], g
assert g["teile"][0]["eingaben"]["a"] == {"winkel": 45.0, "richtung": 0.0}
assert huelle(g, QR) == ([0.0, -20.0, 0.0], [1000.0, 20.0, 600.0])
s = rahmen.bauen(QR, rahmen.RAHMEN, 1000, 600, ecken=rahmen.STECKEN)
assert [t["laenge"] for t in s["teile"]] == [1000.0, 520.0] and len(s["stoesse"]) == 4 and s["stecken"]
assert {x["seite"] for x in s["stoesse"]} == {"180°"} and sorted(x["z"] for x in s["stoesse"]) == [20, 20, 980, 980]
r = rahmen.bauen(RD, rahmen.QUADER, 1000, 600, 400, ecken=rahmen.STUMPF)
assert [t["laenge"] for t in r["teile"]] == [1000.0, 551.7, 351.7] and len(r["stoesse"]) == 16, r
assert r["teile"][1]["eingaben"]["a"] == {"sattel": 48.3}
assert huelle(r, RD) == ([0.0, 0.0, 0.0], [1000.0, 400.0, 600.0])
q = rahmen.bauen(RE, rahmen.QUADER, 1000, 600, 400, ecken=rahmen.STUMPF, hochkant=True)
assert [t["laenge"] for t in q["teile"]] == [1000.0, 480.0, 320.0] and huelle(q, RE) == ([0.0, 0.0, 0.0],
                                                                                          [1000.0, 400.0, 600.0])
for falsch in (lambda: rahmen.bauen(QR, rahmen.QUADER, 1000, 600, 400, ecken=rahmen.GEHRUNG),
               lambda: rahmen.bauen(QR, rahmen.RAHMEN, 60, 600), lambda: rahmen.bauen(dict(form="Flachstahl"),
                                                                                    rahmen.RAHMEN, 1000, 600)):
    try:
        falsch()
        raise AssertionError("ValueError erwartet")
    except ValueError:
        pass
# gleiche Stecker gleich gedreht: der Nasenwinkel (aus der ersten Lage) gilt für alle Körper des Teils
for erg in (s, q, rahmen.bauen(QR, rahmen.QUADER, 1000, 600, 400, ecken=rahmen.STECKEN)):
    for t in erg["teile"][1:]:
        assert len({tuple(lg[3:9]) for lg in t["lagen"]}) == 1, (t["name"], t["lagen"])
assert huelle(s, QR) == ([0.0, -20.0, 0.0], [1000.0, 20.0, 600.0])
ok("Geometrie: Gehrung außen B × H, stumpf mit Stößen, Rundrohr mit Sattel, Quader hochkant, Fehler gemeldet")

# ------------------------------------------------------------------ im Angebot
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rahmen.db")
f = Hauptfenster(db, stumm=True)
k = db.kontext()
qr = next(pid for pid, p in k.profile.items() if p.get("form") == "Quadratrohr")
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
seite = f.angebot_oeffnen(a)
gesehen = {}


def rahmen_fuellen(ecken, form=rahmen.RAHMEN, saetze=3):
    def bedienen(d):
        d.profil.setCurrentText(qr)
        d.form.setCurrentText(form)
        d.ecken.setCurrentText(ecken)
        d.b.setValue(1000)
        d.h.setValue(600)
        d.t.setValue(500)
        d.saetze.setValue(saetze)
        gesehen["vorschau"] = d.vorschau.text()
        gesehen["3d"] = bool(d.ansicht.ansicht.netz)
        d._ok()
        return d.result()
    return bedienen


def satz_ansehen(d):
    gesehen["koerper"] = d.zeigen()
    gesehen["vorschlaege"] = d.vorschlaege_sammeln(laser=False)
    gesehen["verbindungen"] = len(d.bg["steckverbindungen"])
    gesehen["pruef"] = d.steck_pruefen(melden=False)
    d._ok()
    return d.result()


assert seite.position_neu(RAHMEN, dialog=rahmen_fuellen(rahmen.GEHRUNG)) == RAHMEN
pos = [p for p in db.positionen(a) if p.get("satz")]
assert len(pos) == 2 and {p["je_satz"] for p in pos} == {2} and {p["stueck"] for p in pos} == {6}, pos
assert all(p.get("schneidweg") for p in pos), [p.get("schneidweg") for p in pos]
assert all(sw.lesen(p["technik"])["a"].get("winkel") == 45.0 for p in pos)
assert "2 × Rahmen waagrecht 1000 mm" in gesehen["vorschau"]
satz = pos[0]["satz"]
assert seite.satz_3d(satz=satz, dialog=satz_ansehen)
assert gesehen["koerper"] == 4 and any(v["art"] == bv.KNICK for v in gesehen["vorschlaege"]), gesehen["vorschlaege"]
ok(f"Angebot: Satz {satz} mit 2 Positionen (je Satz 2, 3 Sätze), Schneidweg gerechnet, Satz in 3D zeigt 4 Rohre und "
   "schlägt den Knickrahmen vor")

seite.rahmen_assistent(dialog=rahmen_fuellen(rahmen.STECKEN, saetze=1), satz_dialog=satz_ansehen)
# gleiche Teile: oben und unten sind eine Position, die Schlitze schneidet die erste Verbindung
assert gesehen["verbindungen"] == 3 and gesehen["pruef"]["ok"] and gesehen["pruef"]["kanten"] == 4, gesehen["pruef"]
neu = [p for p in db.positionen(a) if p.get("satz") and p["satz"] != satz]
senk = next(p for p in neu if p["je_satz"] == 2 and "senkrecht" in p["bezeichnung"])
assert senk["laenge"] > 520.0 and sw.lesen(senk["technik"])["a"].get("nasen"), senk      # Nasen, Rohr länger
assert len({p["satz"] for p in neu}) == 1 and next(iter({p["satz"] for p in neu})) != satz
ok("stumpf mit Steckverbindungen: 3 Verbindungen (gleiche Teile: Schlitze und Nasen je einmal) für 4 Stöße, steckbar, Nasen und Schlitze in den Teilen")
# Ecke Knickrahmen (Patrick 26.10.2026): Satz in 3D öffnet mit Knickrahmen erstellen, OK: eine Position
for falsch in (lambda: rahmen.bauen(QR, rahmen.QUADER, 1000, 600, 400, ecken=rahmen.KNICK),):
    try:
        falsch()
        raise AssertionError("Quader als Knickrahmen")
    except ValueError:
        pass
assert rahmen.bauen(QR, rahmen.RAHMEN, 1000, 600, ecken=rahmen.KNICK)["knick"]


def knick_ansehen(d):
    gesehen["knicke"] = len(d.knicke)
    d._ok()
    return d.result()


vorher_saetze = {p["satz"] for p in db.positionen(a) if p.get("satz")}
seite.rahmen_assistent(dialog=rahmen_fuellen(rahmen.KNICK, saetze=2), satz_dialog=knick_ansehen)
assert gesehen["knicke"] == 1 and gesehen["3d"] and "Knickrahmen" in gesehen["vorschau"], gesehen
neu = [p for p in db.positionen(a) if p.get("satz") and p["satz"] not in vorher_saetze]
kr = [p for p in neu if sw.lesen(p["technik"]).get("knickrahmen")]
assert len(kr) == 1 and kr[0]["laenge"] > 2 * (1000 + 600) - 100, [(p["bezeichnung"], p["laenge"]) for p in neu]
assert len(neu) == 1, [(p["bezeichnung"], p["je_satz"]) for p in neu]          # die Einzelrohre fallen weg
ok("Ecke Knickrahmen: 3D-Vorschau, Satz in 3D erstellt den Knickrahmen, OK: eine Position mit V-Ausschnitten")
db.schliessen()
print("Rahmen-Assistent: alle Tests bestanden.")
