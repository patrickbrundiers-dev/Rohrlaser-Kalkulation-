"""Fenster „Satz in 3D“ (Patrick 24.10.2026, Schritt 2 „A“): Satz aus Rohrlaserteilen ohne Schweißbaugruppe.
- STEP-Import: Stöße Rohrende an Rohrwand je Satz (angebote.satz_daten, Schema 60)
- Alle Stöße stecken wie im Editor der Schweißbaugruppe (gemeinsamer Code), Rohre im 3D mit Nasen
- Teil im 3D anklicken markiert es (Strg: dazu), zwei markierte Rohre -> Steckverbindung hinzufügen
- Längsnaht per Klick auf die Fläche: Mitte der Wand, feste Position, Quelle manuell, rote Linie
- OK schreibt Schlitze, Nasen, Länge und Naht; Daten des Satzes gespeichert, beim Kopieren des Angebots mit

Aufruf: python tests/test_satz3d.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER.parent / "programm" / "step_messung"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
import step_messen  # noqa: E402
from rohrlaser import naht, schneidweg as sw, step  # noqa: E402
from rohrlaser.ansicht3d import entpacken  # noqa: E402
from rohrlaser.baugruppe_ansicht import in_lage, laengsnaht_linie, laengsnaht_winkel  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.satz3d import TEIL, saetze  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ Längsnaht aus dem Klick (ohne Fenster)
LAGE = [0, 0, 0, 0, 0, 1, 1, 0, 0]              # Rohrachse Z, X-Richtung X
KASTEN = dict(p=[-30, -20, 0, 30, 20, 0, 30, 20, 500])             # Rechteckrohr 60 × 40, Breitseite waagerecht
assert laengsnaht_winkel((5, 20, 100), LAGE, KASTEN, "Rechteckrohr") == 0.0           # oben, Mitte der Wand
assert laengsnaht_winkel((-30, 12, 100), LAGE, KASTEN, "Rechteckrohr") == 90.0        # rechts (−X, von A gesehen)
assert laengsnaht_winkel((30, -3, 100), LAGE, KASTEN, "Rechteckrohr") == 270.0
HOCH = dict(p=[-20, -30, 0, 20, 30, 0, 20, 30, 500])               # hochkant: Breitseite steht
assert laengsnaht_winkel((-20, 5, 100), LAGE, HOCH, "Rechteckrohr") == 0.0            # Breitseite = Bezug oben
RUND = dict(p=[-15, -15, 0, 15, 15, 500])
assert laengsnaht_winkel((-10.607, 10.607, 50), LAGE, RUND, "Rundrohr") == 45.0
li = laengsnaht_linie(LAGE, KASTEN, 90.0, "Rechteckrohr")
assert li[0] < -30 and abs(li[1]) < 1e-6 and li[2] == 0 and li[5] == 500, li
li = laengsnaht_linie(LAGE, HOCH, 0.0, "Rechteckrohr")
assert li[0] < -20 and abs(li[1]) < 1e-6, li                       # hochkant: Breitseite links/rechts im Netz
ok("Längsnaht aus dem Klick: Mitte der Wand, rechts = 90°, Bezug Breitseite oben, Rundrohr genau")

# ------------------------------------------------------------------ STEP-Import als Satz: Stöße je Satz
assert SCHEMA_VERSION >= 60
datei = HIER / "step_struktur" / "S03_Rahmen_geschweisst.step"
tmp = Path(tempfile.mkdtemp())
step_messen.main(["--ausgabe", str(tmp / "m.txt"), "--json", str(tmp / "m.json"), "--netze", str(tmp / "netze"),
                  str(datei)])
mw = step.struktur_anhaengen(step.lade_netze(step.lies_messwerte(tmp / "m.txt"), tmp / "netze"), tmp / "m.json")
for x in mw:
    x.update(_saetze=1, _stueck=1, _uebernehmen=True)             # Satz, keine Schweißbaugruppe
db = Datenbank(tmp / "satz.db")
k = db.kontext()
erg = step.uebernehmen(mw, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True, zukauf_liste=[])
satz = step.satzname(datei)
assert len(erg["satz_daten"][satz]["stoesse"]) == 4, erg["satz_daten"]
db.profile_anlegen(erg["profile"])
a = db.angebot_neu(dict(kunde="Test", maschine="T11"))
for q in erg["positionen"]:
    netz = q.pop("_netz", None)
    q.pop("_zukauf", None)
    pid = db.position_neu(a, q)
    if netz:
        db.netz_speichern(pid, netz)
db.satz_daten_speichern(a, satz, erg["satz_daten"][satz])
assert db.satz_daten(a)[satz]["stoesse"] == erg["satz_daten"][satz]["stoesse"]
netze = db.netze(a)
rolle = {kn: pid for pid in netze for kn in (entpacken(netze[pid]) or {}).get("koerper") or ()}
holm, strebe = rolle["1"], rolle["3"]
ok("STEP-Import als Satz: 4 Stöße je Satz gespeichert (Schema 60)")

# ------------------------------------------------------------------ Fenster
f = Hauptfenster(db, stumm=True)
seite = f.angebot_oeffnen(a)
assert saetze(seite.positionen) == [satz]
vorher = {q["id"]: q for q in db.positionen(a)}
gesehen = {}


def bedienen(d):
    gesehen["koerper"] = d.zeigen()
    gesehen["erg"] = d.steck_alle(melden=False)
    gesehen["fehler"] = d.pruefen()
    netz = d.ansicht3d.ansicht.netz
    p = netz["p"]
    zs = [p[i] for i in range(2, len(p), 3)]
    gesehen["nasen"] = min(zs), max(zs)
    # Klick auf eine Fläche der Strebe markiert sie, Strg-frei: nur sie
    nr = next(i for i, (pid, _, _) in enumerate(d._koerper) if pid == strebe)
    art, kn = next((art, kn) for art, kn in netz["ti"].items() if f"{TEIL}{nr}" in kn)
    j = kn.index(f"{TEIL}{nr}")
    punkt = tuple(p[3 * netz["t"][art][3 * j] + c] for c in range(3))
    gesehen["klick"] = d.geklickt(dict(id=f"{TEIL}{nr}", punkt=punkt))
    gesehen["markiert"] = [d.teile[r]["_id"] for r in d.teile_tab.markierte()]
    # Längsnaht: Modus an, Klick auf die Oberseite des Holms (Rohrsystem Y = +halbe Höhe)
    d.laengsnaht_knopf.setChecked(True)
    nr = next(i for i, (pid, _, _) in enumerate(d._koerper) if pid == holm)
    _, lage, modell = d._koerper[nr]
    gesehen["naht"] = d.geklickt(dict(id=f"{TEIL}{nr}", punkt=in_lage((3.0, 20.0, 100.0), lage)))
    gesehen["nl"] = len(d.ansicht3d.ansicht.netz["l"].get("NL") or [])
    d.laengsnaht_knopf.setChecked(False)
    d._ok()
    return d.result()


i = next(r for r, q in enumerate(seite.positionen) if q["id"] == holm)
assert seite.satz_3d(i, dialog=bedienen)
assert gesehen["erg"] == (3, 0) and gesehen["fehler"] is None, gesehen
assert gesehen["koerper"] >= 4, gesehen          # Rohre und Bleche
assert gesehen["klick"] == strebe and gesehen["markiert"] == [strebe], gesehen
assert gesehen["naht"] in (0.0, 180.0) and gesehen["nl"] == 2, gesehen          # beide Körper des Holms
pos = {q["id"]: q for q in db.positionen(a)}
eh, est = sw.lesen(pos[holm]["technik"]), sw.lesen(pos[strebe]["technik"])
assert len([z for z in eh["konturen"] if str(z.get("quelle", "")).startswith("Steckverbindung")]) == 4
assert est["a"].get("nasen") and est["b"].get("nasen")
assert pos[strebe]["laenge"] > vorher[strebe]["laenge"]
assert pos[holm]["naht_vorgabe"] == naht.FEST and pos[holm]["naht_winkel"] == gesehen["naht"]
assert pos[holm]["naht_quelle"] == "manuell"
gespeichert = db.satz_daten(a)[satz]
assert len(gespeichert["steckverbindungen"]) == 3 and len(gespeichert["stoesse"]) == 4
ok("Satz in 3D: Alle Stöße stecken, Klick markiert Teil, Längsnaht per Klick, OK schreibt Schlitze, Nasen, Naht")

# ------------------------------------------------------------------ wieder öffnen, entfernen, Kopie
zweit = {}


def nochmal(d):
    zweit["alt"] = len(d.steck_alt)
    zweit["erg"] = d.steck_alle(melden=False)
    d.steck_tab.selectRow(0)
    d.steck_entfernen()
    d._ok()
    return d.result()


assert seite.satz_3d(satz=satz, dialog=nochmal)
assert zweit == dict(alt=3, erg=(0, 0)), zweit
pos = {q["id"]: q for q in db.positionen(a)}
assert len([z for z in sw.lesen(pos[holm]["technik"])["konturen"] if str(z.get("quelle", "")).startswith(
    "Steckverbindung")]) == 2
assert len(db.satz_daten(a)[satz]["steckverbindungen"]) == 2
kopie = db.angebot_kopieren(a)
assert len(db.satz_daten(kopie)[satz]["steckverbindungen"]) == 2
ok("Wieder öffnen: Verbindungen über die Kennung gefunden, Entfernen nimmt Schlitze heraus, Kopie behält die Daten")
db.schliessen()
print("Satz in 3D: alle Tests bestanden.")
