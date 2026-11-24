"""Abwicklungskern 2.0 (Plan Patrick 24.11.2026, https://claude.ai/artifact/MeGQKSAn71xSDVx7aCUzP4).

A8  Selbstprüfung (N1): Gegenproben aus den Flächen bestehen bei richtigen Messungen (Vertrauen 100 bei Rohren mit
    Maß-Probe, 80 ohne), schlagen bei falschem Ø, Außen-/Innenmaß, Querschnitt, Länge oder ungültigem Wert an
    (Vertrauen 0 = Rückfall); Rechteckrohr mit Fasen (eigene Richtung) zählt richtig.
A9  Dauer-Vergleich (N1): Auswahl nur nach Datei und Körper; Stichprobe rechnet zusätzlich bisher und protokolliert;
    0 = aus; Einstellung über step_geometrie.einstellen.
A11 Flachstahl (N3): zwei fast gleich gute Längsrichtungen, klar längste gewinnt (1,5×); Tasche/Stufe und kurze
    Platte bleiben bei der bisherigen Rechnung.
A10 Prüfbasis (N7): Sollwerte JSON hin und zurück gleich; Auswahl von Prüf-STEPs gegen tests/daten/
    abwicklungskern_soll.json (Modus an) ohne Abweichung.

Aufruf: python tests/test_abwicklungskern_2.py
"""
import copy
import json
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path[:0] = [str(HIER.parent / "programm"), str(HIER.parent / "programm" / "step_messung"),
                str(HIER.parent / "werkzeuge")]

import step_abwicklungskern as ak  # noqa: E402
import step_geometrie as g  # noqa: E402


def ok(text):
    print("OK:", text)


def kern(name):
    """(Teil im Modus an, Vorgabe des Kerns) für den ersten Körper einer Prüf-STEP."""
    ak.modus_setzen("an")
    ak.stichprobe_setzen(0)
    del SOLIDE[:]
    t = g.analysiere_datei(str(HIER / name))[0]
    assert SOLIDE, name
    solid = SOLIDE[0]
    vorgabe, grund = ak.profil_vorgabe(solid)
    assert vorgabe is not None, (name, grund)
    return t, vorgabe


# Körper aus der Messung selbst holen (gleiche Lage wie dort)
SOLIDE = []
_alt = g._profil_messen


def _merken(solid, datei="", koerper=1, netz=False, quer=None):
    if quer is None:
        SOLIDE.append(solid)
    return _alt(solid, datei, koerper, netz, quer)


g._profil_messen = _merken

# A8 Selbstprüfung
FAELLE = {"step_referenz/REF01_RE60x40x2_L1000.step": 100, "step_referenz/REF03_RR42-4x2_L1000.step": 100,
          "step_referenz/REF02_QR40x40x2_L1000.step": 100, "step_referenz/REF08_QR40x2_Fasen_L800.step": 100,
          "step_konturen/K01_RE60x40x3_Konturen.step": 100}
for name, soll in FAELLE.items():
    t, (ax3, info) = kern(name)
    v, befunde = ak.gegenproben(t, info, ax3)
    assert v == soll, (name, v, befunde)
t, (ax3, info) = kern("step_referenz/REF01_RE60x40x2_L1000.step")
for feld, delta in (("abm_a", 0.5), ("abm_b", -0.2), ("innen_a", 0.1), ("flaeche", 5.0), ("laenge", 0.5)):
    x = copy.copy(t)
    setattr(x, feld, getattr(x, feld) + delta)
    v, befunde = ak.gegenproben(x, info, ax3)
    assert v == 0, (feld, befunde)
x = copy.copy(t)
x.schneidweg = float("nan")
assert ak.gegenproben(x, info, ax3)[0] == 0
x = copy.copy(t)
x.laenge += 0.5
assert ak.gegenproben(x, info, ax3, quer=True)[0] == 100      # Lage aus anderem Körper: Länge nicht vergleichbar
t, (ax3, info) = kern("step_referenz/REF03_RR42-4x2_L1000.step")
for feld, delta in (("abm_a", 0.1), ("innen_a", -0.1)):
    x = copy.copy(t)
    setattr(x, feld, getattr(x, feld) + delta)
    assert ak.gegenproben(x, info, ax3)[0] == 0, feld
ok("A8 Gegenproben aus den Flächen: richtige Rohre 100, falsche Maße/Querschnitt/Länge/NaN 0, Fasen-Quadratrohr 100")

# A9 Dauer-Vergleich
ak.stichprobe_setzen(7)
wahl = [ak.stichprobe("C:/x/teil.step", k) for k in range(1, 200)]
assert wahl == [ak.stichprobe("/anders/teil.step", k) for k in range(1, 200)]       # nur Dateiname und Körper
assert 10 <= sum(wahl) <= 50, sum(wahl)
ak.stichprobe_setzen(0)
assert not any(ak.stichprobe("teil.step", k) for k in range(1, 100))
ak.stichprobe_setzen(1)
ak.modus_setzen("an")
del ak.PROTOKOLL[:]
t1 = g.analysiere_datei(str(HIER / "step_konturen/K01_RE60x40x3_Konturen.step"))[0]
e = [x for x in ak.PROTOKOLL if x["methode"] == "abwicklung"][0]
assert e["stichprobe"] and e["gleich"] and e["bisher_s"] > 0 and e["vertrauen"] == 100, e
z = ak.zusammenfassen(ak.PROTOKOLL)
assert z["stichproben"] >= 1 and z["vertrauen_min"] == 100, z
g.einstellen({"abwicklungskern": "an", "abwicklungskern_stichprobe": 5})
assert ak.STICHPROBE == 5
g.einstellen({})
assert ak.STICHPROBE == ak.STICHPROBE_START
ok("A9 Dauer-Vergleich: Auswahl je Datei/Körper, Stichprobe protokolliert, 0 = aus, Einstellung")

# A10 Prüfbasis
ak.stichprobe_setzen(0)
d = ak.sollwerte(t1)
d2 = json.loads(json.dumps(d))
assert not ak.vergleichen(ak.soll_teil(d2), t1)
import abwicklungskern_vergleich as av  # noqa: E402
SOLL = json.loads((HIER / "daten" / "abwicklungskern_soll.json").read_text(encoding="utf-8"))
AUSWAHL = ["step_referenz/REF01_RE60x40x2_L1000.step", "step_referenz/REF03_RR42-4x2_L1000.step",
           "step_referenz/REF09_RE60x40x2_Gehrung45.step", "step_konturen/K07_U80x40x4_Lage.step",
           "step_importengine/I10_RR40x2_L300_Loch25.step", "step_bleche/B08_Platte_mit_Tasche.step",
           "step_regression/R01_RE60x40x2_L1000_Freiform.step", "step_anbau/A05_RE80x40x3_3Laschen.step"]
for name in AUSWAHL:
    e = av.datei_vergleich(HIER / name, basis=HIER, soll=SOLL[name])
    assert e.get("gleich"), (name, e)
ok(f"A10 Prüfbasis: Sollwerte hin und zurück gleich, {len(AUSWAHL)} Prüf-STEPs gegen die Prüfbasis gleich")

# A11 Flachstahl über die Länge (N3)
ak.stichprobe_setzen(0)
ak.modus_setzen("an")
for name, methode, grund in (("step_profile/P08_FL40x5_L800.step", "abwicklung", ""),
                             ("step_bleche/B09_FL100x10_L800.step", "abwicklung", ""),
                             ("step_bleche/B08_Platte_mit_Tasche.step", "bisher", "Platte mit Tasche"),
                             ("step_regression/R07_FL80x8_L100_Senkungen.step", "bisher", "zwei Längsrichtungen")):
    del ak.PROTOKOLL[:]
    g.analysiere_datei(str(HIER / name))
    e = ak.PROTOKOLL[0]
    assert e["methode"] == methode and e.get("grund", "").startswith(grund), (name, e)
    if methode == "abwicklung":
        assert e["vertrauen"] == 100, (name, e)       # Breite × Dicke gegen die Wandebenen geprüft
ok("A11 Flachstahl: Längsrichtung über die Länge (P08, B09), Tasche und kurze Platte wie bisher")
g._profil_messen = _alt
print("Alle Tests bestanden.")
