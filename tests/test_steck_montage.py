"""Montagemarken und Steckbarkeit (Plan „Baugruppen automatisch und innovativ“, P2; Patrick 25.10.2026 „Alle a“):
- Montagemarke: dieselbe Zahl als Text-Gravur neben den Schlitzen der Aufnahme (außerhalb des Steckers) und auf der
  Nasenwand des Steckers hinter dem Schnitt, 0,5 mm Abstand; ohne Platz ein Hinweis; Entfernen nimmt sie mit, sie
  zählt nicht als Schlitz der Verbindung
- Reihenfolge: Rahmen aus zwei Aufnahmen und zwei Querrohren (Nasen an beiden Enden) ist steckbar, ein Ring, in dem
  jedes Rohr in das nächste steckt, nicht
- Satz S03 mit Einstellung steck_marke = ja: „Alle Stöße stecken“ nummeriert je Steckerende (1, 1, 2), die Marken stehen in den Eingaben
  beider Teile; Steckbarkeit prüfen findet die Stöße; eine feste Längsnaht auf einem Schlitz wird gemeldet

Aufruf: python tests/test_steck_montage.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))

from PySide6.QtWidgets import QApplication  # noqa: E402

import step_messen  # noqa: E402
from rohrlaser import schneidweg as sw, skizze as sk, step, steck_montage as sm, steckverbindung as sv  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(t):
    print("OK    ", t)


QR = dict(form="Quadratrohr", a=40.0, b=40.0, wand=2.0)
RR = dict(form="Rundrohr", a=48.3, wand=2.0)
LEER = dict(a={}, b={}, konturen=[])


def marken(e):
    return [z for z in e.get("konturen") or () if z.get("art") == sw.TEXT_GRAVUR]


# ------------------------------------------------------------------ Montagemarke
v = dict(sv.neu(dict(id=1), dict(id=2), QR, {}, ende="a", x=200, seite="oben"), marke="7", marke_h=10.0)
h = []
auf, st, plus = sv.anwenden(v, LEER, LEER, QR, QR, (500.0, 300.0), h)
assert not h and plus == 2.0, (h, plus)
(ma,), (ms,) = marken(auf), marken(st)
assert ma["text"] == ms["text"] == "7" and ma["seite"] == "oben" and ma["quelle"] == sv.marke_quelle(v["id"])
m = sv.masse(v, QR, QR)
rand = max(abs(dx) + sl / 2 for (dx, _), (sl, _) in zip(m["nasen"], m["schlitze"]))
b = __import__("rohrlaser.gravur_text", fromlist=["masse"]).masse("7", 10.0)[0]
assert ma["x"] - b / 2 - 200 >= max(rand, 20.0) + 0.5, ma          # außerhalb der Schlitze und des Steckers
assert ms["x"] - b / 2 >= plus + 0.5 and ms["seite"] == "oben", ms   # hinter Schnitt und Nasen, Nasenwand oben
assert sv.rollen(sw.speichern(auf)) == {v["id"]: {"aufnahme"}}       # Marke zählt nicht als Schlitz
assert not marken(sv.entfernen(auf, v["id"])[0]) and not marken(sv.entfernen(st, v["id"])[0])
# Ende E mit Gehrung: Marke vor dem Schnitt, längs Wände: Nasenwand vorne
gehr = dict(a={}, b=dict(winkel=45.0), konturen=[])
v2 = dict(v, stecker=dict(v["stecker"], ende="b"), waende="längs")
_, st2, plus2 = sv.anwenden(v2, LEER, gehr, QR, QR, (500.0, 300.0), h)
(ms2,) = marken(st2)
qs = sk.Querschnitt(QR)
tiefe = max(sk.schnitt_x(qs, gehr["b"], *qs.s_zu_uv(sk.naht_s(qs, 90.0) + d)[0]) for d in (-5, 0, 5))
assert ms2["seite"] == "vorne" and ms2["x"] + b / 2 <= 300.0 + plus2 - tiefe - plus2 - 0.5 + 1e-6, (ms2, tiefe)
# erst Ende E, dann Ende A: die Marke am Ende E wandert mit der längeren Rohlänge mit (und zurück beim Entfernen)
vb = dict(sv.neu(dict(id=1), dict(id=2), QR, {}, ende="b", x=300, seite="oben"), marke="8", marke_h=10.0)
va = dict(sv.neu(dict(id=3), dict(id=2), QR, {}, ende="a", x=300, seite="oben"), marke="9", marke_h=10.0)
_, sb, pb = sv.anwenden(vb, LEER, LEER, QR, QR, (500.0, 300.0), h)
xb = marken(sb)[0]["x"]
_, sab, pa = sv.anwenden(va, LEER, sb, QR, QR, (500.0, 300.0 + pb), h)
m8 = next(z for z in marken(sab) if z["text"] == "8")
assert abs(m8["x"] - (xb + pa)) < 1e-6 and 300.0 + pb + pa - m8["x"] == 300.0 + pb - xb, (m8, xb, pa)
zur, _ = sv.entfernen(sab, va["id"])
assert abs(marken(zur)[0]["x"] - xb) < 1e-6
# Rundrohr als Aufnahme: Seite als Winkel
auf3, _, _ = sv.anwenden(dict(v, seite="90°"), LEER, LEER, RR, QR, (500.0, 300.0), h)
assert marken(auf3)[0]["seite"] == "90°"
# kein Platz: kurze Aufnahme
h = []
auf4, _, _ = sv.anwenden(dict(v, x=25.0), LEER, LEER, QR, QR, (50.0, 300.0), h)
assert not marken(auf4) and any("kein Platz" in t for t in h), h
assert sv.marke_naechste([dict(marke="2"), dict(marke="x"), {}]) == "3"
ok("Montagemarke an Schlitz und Nase, 0,5 mm Abstand, Gehrung beachtet, ohne Platz Hinweis, Entfernen nimmt sie mit")

# ------------------------------------------------------------------ Reihenfolge
def lage(o, z, x):
    return list(o) + list(z) + list(x)


# zwei Aufnahmen längs X (y = 0 und y = 500), zwei Querrohre längs Y mit Nasen an beiden Enden
koerper = {"1": ("A", lage((0, 0, 0), (1, 0, 0), (0, 1, 0))), "2": ("A", lage((0, 500, 0), (1, 0, 0), (0, 1, 0))),
           "3": ("Q", lage((50, 0, 0), (0, 1, 0), (1, 0, 0))), "4": ("Q", lage((950, 0, 0), (0, 1, 0), (1, 0, 0)))}
stoesse = [dict(aufnahme=1, stecker=3, ende="a"), dict(aufnahme=2, stecker=3, ende="b"),
           dict(aufnahme=1, stecker=4, ende="a"), dict(aufnahme=2, stecker=4, ende="b")]
k = sm.kanten(koerper, stoesse, [("A", "Q", "a"), ("A", "Q", "b")])
r = sm.reihenfolge(k)
assert len(k) == 4 and r["ok"] and len(r["schritte"]) == 4 and r["schritte"][0][1] is None, r
assert sm.kanten(koerper, stoesse, [("A", "Q", "a")]) and len(sm.kanten(koerper, stoesse, [("A", "Q", "a")])) == 2
# Ring: jedes Rohr steckt mit Ende E im nächsten
ring = {"1": ("R1", lage((0, 0, 0), (1, 0, 0), (0, 1, 0))), "2": ("R2", lage((100, 0, 0), (0, 1, 0), (1, 0, 0))),
        "3": ("R3", lage((100, 100, 0), (-1, 0, 0), (0, 1, 0))), "4": ("R4", lage((0, 100, 0), (0, -1, 0), (1, 0, 0)))}
st_ring = [dict(aufnahme=2, stecker=1, ende="b"), dict(aufnahme=3, stecker=2, ende="b"),
           dict(aufnahme=4, stecker=3, ende="b"), dict(aufnahme=1, stecker=4, ende="b")]
k2 = sm.kanten(ring, st_ring, [("R2", "R1", "b"), ("R3", "R2", "b"), ("R4", "R3", "b"), ("R1", "R4", "b")])
r2 = sm.reihenfolge(k2)
assert not r2["ok"] and len(r2["offen"]) == 1 and "verschiedene Richtungen" in sm.konflikt(r2["offen"][0],
                                                                                             r2["schritte"], k2), r2
ok("Reihenfolge: Rahmen mit zwei Querrohren steckbar, Ring (jedes Rohr ins nächste) nicht, Grund genannt")

# ------------------------------------------------------------------ Satz S03 mit Marken
tmp = Path(tempfile.mkdtemp())
datei = HIER / "step_struktur" / "S03_Rahmen_geschweisst.step"
ziel = tmp / datei.stem
step_messen.main(["--ausgabe", str(ziel) + ".txt", "--json", str(ziel) + ".json", "--netze", str(ziel), str(datei)])
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(str(ziel) + ".txt"), ziel), str(ziel) + ".json")
for x in mw:
    x.update(_stueck=1, _uebernehmen=True, _saetze=1)
db = Datenbank(tmp / "montage.db")
db.einstellung_setzen("steck_marke", "ja")
f = Hauptfenster(db, stumm=True)
kx = db.kontext()
erg = step.uebernehmen(mw, [], kx, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True, zukauf_liste=[])
db.profile_anlegen(erg["profile"])
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
for q in erg["positionen"]:
    netz = q.pop("_netz", None)
    q.pop("_zukauf", None)
    pid = db.position_neu(a, q)
    if netz:
        db.netz_speichern(pid, netz)
for satz, daten in (erg.get("satz_daten") or {}).items():
    db.satz_daten_speichern(a, satz, daten)
seite = f.angebot_oeffnen(a)
gesehen = {}


def bedienen(d):
    d.steck_alle(melden=False)
    gesehen["marken"] = [z.get("marke") for z in d.bg["steckverbindungen"]]
    eing, _ = d._rohr_eingaben()
    gesehen["gravuren"] = sum(len([z for z in marken(e) if str(z.get("quelle")).startswith(sv.MARKE)])
                              for e, _ in eing.values())
    gesehen["pruef"] = d.steck_pruefen(melden=False)
    z = d.bg["steckverbindungen"][0]                   # feste Längsnaht genau auf die Schlitzseite der Aufnahme
    qs_ = sk.Querschnitt(d._steck_profil(z["_auf"]))
    w = next(w for w in (0.0, 90.0, 180.0, 270.0) if sk.s_zu_seite(qs_, sk.naht_s(qs_, w))[0] == z.get("seite"))
    d.laengsnaehte[z["_auf"]] = w
    gesehen["naht"] = d.steck_pruefen(melden=False)
    del d.laengsnaehte[z["_auf"]]
    d.marken_nummerieren()
    gesehen["neu"] = [z.get("marke") for z in d.bg["steckverbindungen"]]
    d._ok()
    return d.result()


assert seite.satz_3d(0, dialog=bedienen)
n = len(gesehen["marken"])
assert n == 3 and gesehen["marken"] == ["1", "1", "2"], gesehen["marken"]    # gleiches Steckerende, gleiche Zahl
assert gesehen["gravuren"] >= n, gesehen["gravuren"]          # je Verbindung mindestens die Marke an einem Teil
p = gesehen["pruef"]
assert p["kanten"] >= 3 and not p["offen"], p
assert any("Längsnaht liegt auf einem Schlitz" in t for t in gesehen["naht"]["texte"]), gesehen["naht"]["texte"]
assert gesehen["neu"] == ["1", "1", "2"]
pos = db.positionen(a)
assert sum(len([z for z in marken(sw.lesen(q.get("technik"))) if str(z.get("quelle")).startswith(sv.MARKE)])
           for q in pos) == gesehen["gravuren"]
ok(f"Satz S03: Marken je Steckerende aus der Einstellung, {gesehen['gravuren']} Gravuren in den Teilen, steckbar "
   f"({p['kanten']} Stöße), feste Naht auf Schlitz gemeldet")
db.schliessen()
print("Montagemarken und Steckbarkeit: alle Tests bestanden.")
