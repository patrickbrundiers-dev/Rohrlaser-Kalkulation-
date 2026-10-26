"""STEP-Baugruppenstruktur und Bauteilnamen (STEP-JSON 1.13): Knoten mit Menge, Teile je Knoten, Pfad je Körper.

Testdateien: tests/step_struktur/ (erzeugt mit tests/erzeuge_struktur_teile.py).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
MESSEN = HIER.parent / "programm" / "step_messung" / "step_messen.py"
ORDNER = HIER / "step_struktur"
tmp = Path(tempfile.mkdtemp())

from rohrlaser import step  # noqa: E402

dateien = [ORDNER / "S01_Gestell_verschachtelt.step", ORDNER / "S02_Einzelteil_benannt.step",
           HIER / "step_satz" / "T08_Gestell_Baugruppe.step", HIER / "step_referenz" / "REF01_RE60x40x2_L1000.step"]
aus, js = tmp / "m.txt", tmp / "m.json"
r = subprocess.run([sys.executable, str(MESSEN), "--ausgabe", str(aus), "--json", str(js), *map(str, dateien)],
                   capture_output=True, text=True, timeout=600)
assert r.returncode == 0, r.stderr
daten = json.loads(js.read_text(encoding="utf-8"))
assert daten["schema_version"] >= "1.13"
je = {d["datei"]: d for d in daten["dateien"]}

# S1: verschachtelte Baugruppe – Rahmenseite 2× im Gestell, Teile nur aus der ersten Instanz mit Anzahl je Knoten
s01 = je["S01_Gestell_verschachtelt.step"]
st = s01["struktur"]
assert st["knoten"] == [dict(id="K1", name="Gestell", eltern=None, menge=1),
                        dict(id="K2", name="Rahmenseite", eltern="K1", menge=2)], st["knoten"]
koerper = {k["nr"]: k for k in s01["koerper"]}
teile = {(koerper[t["teil_index"]]["bauteil"], t["knoten"]): t["anzahl"] for t in st["teile"]}
assert teile == {("Holm RE60x40x3 L800", "K2"): 1, ("Strebe QR40x3 L500", "K2"): 2,
                 ("Querrohr RR42.4x2 L600", "K1"): 2, ("Schraube ISO 4017 M8x20", "K1"): 4}, teile
assert len(s01["koerper"]) == 12 and all(k["bauteil"] and k["knoten"] for k in s01["koerper"])
pfade = [k["pfad"] for k in s01["koerper"]]
assert "Gestell/Rahmenseite[2]/Strebe QR40x3 L500[2]" in pfade and len(set(pfade)) == 12
# Gesamtzahl je Bauteil über die Struktur = Zahl der Körper in der Datei
menge = {k["id"]: k["menge"] for k in st["knoten"]}
eltern = {k["id"]: k["eltern"] for k in st["knoten"]}


def faktor(kid):
    return menge[kid] * (faktor(eltern[kid]) if eltern[kid] else 1)


gesamt = {}
for t in st["teile"]:
    b = koerper[t["teil_index"]]["bauteil"]
    gesamt[b] = gesamt.get(b, 0) + t["anzahl"] * faktor(t["knoten"])
zaehlen = {}
for k in s01["koerper"]:
    zaehlen[k["bauteil"]] = zaehlen.get(k["bauteil"], 0) + 1
assert gesamt == zaehlen, (gesamt, zaehlen)
print("OK: verschachtelte Baugruppe (Knoten mit Menge, Teile je Knoten, Pfade, Summe = Körper)")

# S2: Einzelteil mit Namen – keine Struktur, Bauteilname am Körper
s02 = je["S02_Einzelteil_benannt.step"]
assert s02["struktur"] is None and s02["koerper"][0]["bauteil"] == "Halter 4711 QR40x3"
assert s02["koerper"][0]["knoten"] is None
# ohne Namen (Testteile von OpenCascade): Struktur nur mit Wurzel aus dem Dateinamen, Bauteilname leer
t08 = je["T08_Gestell_Baugruppe.step"]
assert t08["struktur"]["knoten"] == [dict(id="K1", name="T08_Gestell_Baugruppe", eltern=None, menge=1)]
assert all(k["bauteil"] is None and k["knoten"] == "K1" for k in t08["koerper"])
assert je["REF01_RE60x40x2_L1000.step"]["struktur"] is None
print("OK: Einzelteil mit Namen, Dateien ohne Namen, Einzelteil ohne Baugruppe")

# S3: Messwerte (Textdatei) mit Spalten bauteil/pfad/knoten, Struktur für das Programm angehängt
messwerte = step.struktur_anhaengen(step.lies_messwerte(aus), js)
m = [x for x in messwerte if x["datei"] == "S01_Gestell_verschachtelt.step"]
assert m[0]["bauteil"] == "Holm RE60x40x3 L800" and m[0]["pfad"] == "Gestell/Rahmenseite/Holm RE60x40x3 L800"
assert m[0]["knoten"] == "K2" and m[0]["_struktur"] == st
assert all(x["_struktur"] is None for x in messwerte if x["datei"] == "REF01_RE60x40x2_L1000.step")
assert step.struktur_anhaengen([dict(datei="x")], tmp / "fehlt.json")[0]["_struktur"] is None
# Messwerte der Rohre unverändert gegenüber der Messung ohne Namen (Profil, Länge)
assert {x["profilform"] for x in m} >= {"Rechteckrohr", "Quadratrohr", "Rundrohr"}
print("OK: Messwerte mit Bauteil, Pfad und Knoten; Struktur je Datei an den Messwerten")

# S4: Schweißbaugruppe aus der Struktur (Häkchen „als Schweißbaugruppe“ im Prüfdialog)
from rohrlaser import baugruppe  # noqa: E402
from rohrlaser.angebot import BAUGRUPPE  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

db = Datenbank(tmp / "bg.db")
k = db.kontext()
for x in m:
    x.update(_saetze=2, _stueck=2, _baugruppe=True, _uebernehmen=True)
erg = step.uebernehmen(m, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True)
pos = erg["positionen"]
bgp = next(p for p in pos if p.get("art") == BAUGRUPPE)
g = baugruppe.lesen(bgp["baugruppe"])
assert (bgp["bezeichnung"], bgp["stueck"]) == ("S01_Gestell_verschachtelt", 2), bgp
assert [(kn["name"], kn["menge"], kn["parent"]) for kn in g["knoten"]] == [("Rahmenseite", 2, "")], g["knoten"]
assert not g["naehte"] and not g["arbeitsgaenge"]
laenge = {800: "Holm RE60x40x3 L800", 500: "Strebe QR40x3 L500", 600: "Querrohr RR42.4x2 L600"}
teile = {laenge[round(p["laenge"])]: (p["bg_knoten"], p["je_knoten"]) for p in pos if p.get("bg_knoten")}
kn = g["knoten"][0]["id"]
assert teile == {"Holm RE60x40x3 L800": (baugruppe.zuordnung_text(g["id"], kn), 1),
                 "Strebe QR40x3 L500": (baugruppe.zuordnung_text(g["id"], kn), 2),
                 "Querrohr RR42.4x2 L600": (g["id"], 2)}, teile
pos = [dict(p, id=i) for i, p in enumerate(pos)]
assert baugruppe.abgleich(pos) == [], baugruppe.abgleich(pos)      # Satz, Stück je Satz und Stückzahl passen schon
assert any(b.startswith("Schweißbaugruppe S01_Gestell_verschachtelt") for b in erg["bericht"])
print("OK: Schweißbaugruppe aus der STEP-Struktur (Unterbaugruppe Rahmenseite × 2, Teile zugeordnet, ohne Nähte)")

# S5: Prüfdialog – Häkchen „als Schweißbaugruppe“ nur mit Satz, schreibt _baugruppe
import os  # noqa: E402
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.step_dialog import StepPruefDialog  # noqa: E402

app = QApplication.instance() or QApplication([])
mw = [{n: v for n, v in x.items() if not n.startswith("_") or n in ("_struktur", "_netz")} for x in m]
d = StepPruefDialog(None, mw, k, "S235-10219", 1, db.zukauf_artikel_liste(), {})
assert not d.bg_haken.isEnabled() and not d.satz_knopf.isChecked()     # Vorgabe: Einzelpositionen, kein Satz
d.satz_knopf.setChecked(True)
assert d.bg_haken.isEnabled() and not d.bg_haken.isChecked()
d.bg_haken.setChecked(True)
d.werte_schreiben()
assert all(x["_baugruppe"] for x in mw if "_uebernehmen" in x) and sum("_uebernehmen" in x for x in mw) >= 8
d.saetze_setzen(0)
assert not d.bg_haken.isEnabled()
d.werte_schreiben()
assert not any(x.get("_baugruppe") for x in mw)
d.reject()
print("OK: Prüfdialog: Häkchen als Schweißbaugruppe (nur mit Satz)")

# S5b P8: zwei STEP-Dateien als eine Baugruppe – T08 als Unterbaugruppe (3 Stück) in S01
m2 = [dict(x) for x in messwerte if x["datei"] in ("S01_Gestell_verschachtelt.step", "T08_Gestell_Baugruppe.step")]
for x in m2:
    x.update(_saetze=2 if x["datei"].startswith("S01") else 3, _baugruppe=True, _uebernehmen=True)
    x["_stueck"] = x["_saetze"]
    if x["datei"].startswith("T08"):
        x["_in_baugruppe"] = "S01_Gestell_verschachtelt.step"
erg2 = step.uebernehmen(m2, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True)
pos2 = [dict(p, id=i) for i, p in enumerate(erg2["positionen"])]
bgs = [p for p in pos2 if p.get("art") == BAUGRUPPE]
assert len(bgs) == 1 and bgs[0]["bezeichnung"] == "S01_Gestell_verschachtelt" and bgs[0]["stueck"] == 2
g2 = baugruppe.lesen(bgs[0]["baugruppe"])
u = next(kn for kn in g2["knoten"] if kn["name"] == "T08_Gestell_Baugruppe")
assert u["menge"] == 3 and u["parent"] == "" and any(kn["name"] == "Rahmenseite" for kn in g2["knoten"])
t08 = [p for p in pos2 if p.get("bg_knoten") and m2 and baugruppe.zuordnung(p)[1] and
       baugruppe.zuordnung(p)[1].startswith(u["id"])]
assert t08, [p.get("bg_knoten") for p in pos2]
for i, feld, wert in baugruppe.abgleich(pos2):
    pos2[i][feld] = wert
assert baugruppe.abgleich(pos2) == [] and all(baugruppe.teil_pruefen(p, pos2) is None for p in pos2 if p.get("bg_knoten"))
assert all(p["stueck"] % (2 * 3) == 0 for p in t08)                     # 2 Gestelle × 3 Unterbaugruppen
assert any("als Unterbaugruppe eingehängt" in b for b in erg2["bericht"])
# ohne Ziel-Baugruppe (Ziel nicht als Schweißbaugruppe): eigene Baugruppe wie bisher
for x in m2:
    if x["datei"].startswith("S01"):
        x["_baugruppe"] = False
erg3 = step.uebernehmen(m2, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True)
assert [p["bezeichnung"] for p in erg3["positionen"] if p.get("art") == BAUGRUPPE] == ["T08_Gestell_Baugruppe"]
mw2 = [{n: v for n, v in x.items() if not n.startswith("_") or n in ("_struktur", "_netz")} for x in m2]
d = StepPruefDialog(None, mw2, k, "S235-10219", 1, db.zukauf_artikel_liste(), {})
t08_datei = "T08_Gestell_Baugruppe.step"
assert d._ziel_setzen("S01_Gestell_verschachtelt.step", t08_datei)
assert not d._ziel_setzen(t08_datei, "S01_Gestell_verschachtelt.step")     # Kette/Kreis: nur eine Ebene
assert not d._ziel_setzen(t08_datei, "andere.step")                          # Ziel hängt selbst schon unter S01
d.baugruppe[t08_datei] = True
d.saetze_setzen(3, t08_datei)
d.werte_schreiben()
assert all(x["_in_baugruppe"] == "S01_Gestell_verschachtelt.step" for x in mw2
           if x["datei"] == t08_datei and "_uebernehmen" in x)
assert all(x["_baugruppe"] for x in mw2 if x["datei"].startswith("S01") and "_uebernehmen" in x)
d.reject()
# Kette A → B → C aus alten Daten: A wird nicht still verworfen, sondern eigene Baugruppe mit Hinweis
for x in m2:
    x["_baugruppe"] = True
    x["_in_baugruppe"] = t08_datei if x["datei"].startswith("S01") else "S01_Gestell_verschachtelt.step"
erg4 = step.uebernehmen(m2, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True)
assert any("selbst Unterbaugruppe ist" in b for b in erg4["bericht"]), erg4["bericht"]
for x in m2:
    x.pop("_in_baugruppe", None)
print("OK: P8 zwei STEP-Dateien als eine Schweißbaugruppe (T08 × 3 als Unterbaugruppe von S01)")

# S6: Nahtkandidaten (STEP-JSON 1.14) – geschweißter Rahmen
aus2, js2 = tmp / "n.txt", tmp / "n.json"
r = subprocess.run([sys.executable, str(MESSEN), "--ausgabe", str(aus2), "--json", str(js2),
                    str(ORDNER / "S03_Rahmen_geschweisst.step"), str(ORDNER / "S02_Einzelteil_benannt.step")],
                   capture_output=True, text=True, timeout=600)
assert r.returncode == 0, r.stderr
d = {x["datei"]: x for x in json.loads(js2.read_text(encoding="utf-8"))["dateien"]}
rahmen = d["S03_Rahmen_geschweisst.step"]
name = {k["nr"]: k["bauteil"] for k in rahmen["koerper"]}
assert name[1].startswith("Längsrohr") and name[5].startswith("Fußplatte"), name     # Umlaute aus der Datei
naehte = {(name[n["teile"][0]].split()[0], name[n["teile"][1]].split()[0], n["stossart"]): n
          for n in rahmen["nahtkandidaten"]}
assert sorted((a, b, s) for a, b, s in naehte) == [
    ("Längsrohr", "Fußplatte", "Kehlnaht"), ("Längsrohr", "Querrohr", "Kehlnaht"),
    ("Längsrohr", "Verlängerung", "Stumpfnaht")], sorted(naehte)
assert len(rahmen["nahtkandidaten"]) == 6        # 4 Querrohr-Enden, Fußplatte, Verlängerung
for n in rahmen["nahtkandidaten"]:
    assert abs(n["laenge_mm"] - 152.3) < 0.2 and n["dicke_mm"] == 3.0 and n["status"] == "prüfen", n
    assert n["knoten"] == "K1"
assert d["S02_Einzelteil_benannt.step"]["nahtkandidaten"] == []
m = step.struktur_anhaengen(step.lies_messwerte(aus2), js2)
assert len(m[0]["_nahtkandidaten"]) == 6
print("OK: Nahtkandidaten (Kehlnaht, Stumpfnaht, Länge = Umfang am Rohrende, Dicke, Knoten)")

# S7: Schweißbaugruppe aus S03 – Nahtkandidaten nur als Vorschläge an der Baugruppe
m3 = [x for x in m if x["datei"] == "S03_Rahmen_geschweisst.step"]
for x in m3:
    x.update(_saetze=1, _stueck=1, _baugruppe=True, _uebernehmen=True)
erg = step.uebernehmen(m3, [], k, db.zeilen("gewinde"), None, "S235-10219", None, neue_profile=True,
                       zukauf_liste=[])
g = baugruppe.lesen(next(p for p in erg["positionen"] if p.get("art") == BAUGRUPPE)["baugruppe"])
assert not g["naehte"]
vs = sorted((v["nahtart"], v["anzahl"], v["laenge"], v["knoten"]) for v in g["vorschlaege"])
assert vs == [("Kehlnaht", 5, 152, ""), ("Stumpfnaht", 1, 152, "")], vs
assert any("6 Nahtkandidaten als Vorschlag" in b for b in erg["bericht"]), erg["bericht"]
print("OK: Schweißbaugruppe aus S03: 6 Nahtkandidaten als 2 Vorschläge, keine Nahtgruppe automatisch")
