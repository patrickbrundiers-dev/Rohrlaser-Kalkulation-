"""Intelligente 12-m-Zuschnittoptimierung (Patrick 24.11.2026): 12 m nur bei echtem Gesamtkostenvorteil, eine zentrale
Entscheidung (rechnen.laenge_vorteil / laengen_bewerten) für Angebot, Staffeln und Nesting. Die 10 Pflichtszenarien
mit Kontrollrechnung, Übersteuerung von Hand und Automatik je Menge.

Aufruf: python tests/test_zuschnitt_12m_2411.py
"""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

import feste_zeiten  # noqa: E402
from rohrlaser import nesting, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import ALTE_MASCHINEN, MASCHINE_WERTE  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
feste_zeiten.setzen(db)
# T03 wie die frühere Beispielmaschine RL-1: Endbeschnitt 20, Greiferrest 80, Schnitt 0,3, max. 6.500, Wechsel 30 s
_t03 = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T03")
for _feld, _wert in zip(MASCHINE_WERTE, ALTE_MASCHINEN["RL-1"][1]):
    db.aendern("maschinen", _t03["id"], _feld, _wert)
QR, ST = "QR 40x40x3", "S235-10219"
z12 = db.neu("lieferlaengen", dict(profil_id=QR, werkstoff_id=ST, laenge=12000))
EINST = dict(db.einstellungen(), laenge_vergleich="ja")
assert rechnen.laenge_automatisch(EINST) and EINST["laenge_automatisch"] == "ja"      # Vorgabe: Automatik an
assert EINST["laenge_handling_eur"] == 0 and EINST["laenge_handling_ab"] == 6500
assert not rechnen.laenge_automatisch(None)                                           # ältere Aufrufe: wie bisher
kopf = dict(maschine="T03", stange=6000)


def pos(laenge, stueck, profil=QR, werkstoff=ST, nr=10):
    return dict(pos=nr, artikel=f"T{nr}", profil_id=profil, werkstoff_id=werkstoff, laenge=laenge, stueck=stueck)


def lauf(positionen, einst=None, kp=None, auto=False):
    """Optimieren (mit Automatik) und je Gruppe die Bewertung; Ergebnis (erg, [Bewertung])."""
    einst = EINST if einst is None else einst
    k, tab = db.kontext(), db.tabellen()
    erg = rechnen.optimieren(kp or kopf, positionen, k, tab, einst, auto=auto)
    return erg, [rechnen.laengen_bewerten(v, kp or kopf, positionen, k, tab, einst) for v in erg.get("laengen", [])]


def gewaehlt(erg, profil=QR):
    return next(v for v in erg["laengen"] if v["profil"] == profil)["gewaehlt"]


def kontrolle(b):
    """Gesamtkosten = Material + Beladungen + Zuschnitt + Handhabung − Reststückwert, Entscheidung = laenge_vorteil."""
    for v in b["varianten"]:
        assert abs(v["gesamt"] - (v["material"] + v["werkstueck_kosten"] + v["zuschnitt_kosten"]
                                  + v["handling_kosten"] - v["rest_wert"])) < 1e-6, v
        assert abs(v["material"] - v["preis_stange"] * v["lieferstangen"]) < 1e-6
    vk = b.get("vergleich")
    if vk:
        basis, alt = b["varianten"]
        assert abs(vk["gesamt_ersparnis"] - (basis["gesamt"] - alt["gesamt"])) < 1e-6
        assert abs(vk["material_ersparnis"] - (basis["material"] - alt["material"])) < 1e-6
        assert (vk["basis_rohre"], vk["rohre"]) == (basis["lieferstangen"], alt["lieferstangen"])
        assert vk["lohnt"] == (b["empfehlung"] == rechnen.LAENGE_ALTERNATIVE)


# ------------------------------------------------------------------ 1) 12 m deutlich günstiger
# 30 × 3.100 mm: 6 m 1 Teil je Stange (30 Stangen), 12 m 3 Teile je Stange (10 Stangen, Zuschnitt auf 6.500 mm)
erg, (b,) = lauf([pos(3100, 30)])
basis, alt = b["varianten"]
kontrolle(b)
assert (basis["lieferstangen"], alt["lieferstangen"], alt["zuschnitt"]) == (30, 10, True)
assert abs(alt["material"] - basis["material"] * 2 / 3) < 0.01
assert b["empfehlung"] == rechnen.LAENGE_ALTERNATIVE and gewaehlt(erg) == 12000          # automatisch übernommen
assert {s["stange"] for s in erg["stangen"]} == {12000}
vk = b["vergleich"]
assert vk["lohnt"] and vk["gesamt_ersparnis"] >= 20 and abs(vk["je_teil"] - vk["gesamt_ersparnis"] / 30) < 1e-9, vk
assert vk["verschnitt_ersparnis"] > 0 and abs(vk["anteil"] - vk["gesamt_ersparnis"] / basis["gesamt"]) < 1e-9
P6 = basis["preis_stange"]
# technische Grenze: kein Werkstück länger als die Maschine laden kann
assert max(alt["werkstueck_laengen"]) <= 6500
GESPART = vk["gesamt_ersparnis"]
print("1 deutlich günstiger OK", round(GESPART, 2), "€")

# ------------------------------------------------------------------ 2) 12 m nur geringfügig günstiger (10 € < 20 €)
db.aendern("lieferlaengen", z12, "basis", "€/Stange")
db.aendern("lieferlaengen", z12, "preis", round(3 * P6 - 1.0, 4))
erg, (b,) = lauf([pos(3100, 30)])
kontrolle(b)
assert abs(b["vergleich"]["gesamt_ersparnis"] - 10.0) < 0.01, b["vergleich"]
assert b["empfehlung"] == rechnen.LAENGE_KEIN_VORTEIL and "unter den Grenzen" in b["begruendung"], b["begruendung"]
assert gewaehlt(erg) is None and {s["stange"] for s in erg["stangen"]} == {6000}
# mit geringerer Mindestersparnis lohnt es sich
erg, (b,) = lauf([pos(3100, 30)], dict(EINST, laenge_mindest_eur=5, laenge_mindest_anteil=0))
assert b["empfehlung"] == rechnen.LAENGE_ALTERNATIVE and gewaehlt(erg) == 12000
print("2 geringfügig OK")

# ------------------------------------------------------------------ 3) 12 m trotz weniger Verschnitt teurer (Handhabung)
db.aendern("lieferlaengen", z12, "basis", None)
db.aendern("lieferlaengen", z12, "preis", None)                       # Preis wie 'Preise' (€/kg)
einst_h = dict(EINST, laenge_handling_eur=round(GESPART / 10 + 1, 2))   # je 12-m-Stange mehr als die Ersparnis
erg, (b,) = lauf([pos(3100, 30)], einst_h)
basis, alt = b["varianten"]
kontrolle(b)
assert alt["verschnitt_mm"] < basis["verschnitt_mm"] and alt["material"] < basis["material"]
assert basis["handling_kosten"] == 0 and abs(alt["handling_kosten"] - 10 * einst_h["laenge_handling_eur"]) < 1e-6
assert alt["gesamt"] > basis["gesamt"] and b["empfehlung"] == rechnen.LAENGE_KEIN_VORTEIL
assert "fressen den Vorteil auf" in b["begruendung"] and "Handhabung" in b["begruendung"], b["begruendung"]
assert gewaehlt(erg) is None
print("3 teurer trotz Verschnitt OK")

# ------------------------------------------------------------------ 4) 6 m wirtschaftlicher (Längenzuschlag)
db.aendern("lieferlaengen", z12, "basis", "€/kg")
db.aendern("lieferlaengen", z12, "preis", 2.40)
erg, (b,) = lauf([pos(3100, 30)])
kontrolle(b)
assert b["varianten"][1]["gesamt"] > b["varianten"][0]["gesamt"] and "teurer" in b["begruendung"]
assert b["empfehlung"] == rechnen.LAENGE_KEIN_VORTEIL and gewaehlt(erg) is None
db.aendern("lieferlaengen", z12, "basis", None)
db.aendern("lieferlaengen", z12, "preis", None)
print("4 6 m wirtschaftlicher OK")

# ------------------------------------------------------------------ 5) nahezu identische Kosten
# 20 × 2.900 mm: 2 Teile je 6 m (10 Stangen), 4 je 12 m (5 Stangen), gleiche Beladungen und gleiches Material
erg, (b,) = lauf([pos(2900, 20)])
kontrolle(b)
assert abs(b["vergleich"]["gesamt_ersparnis"]) < 1e-6 and b["empfehlung"] == rechnen.LAENGE_KEIN_VORTEIL
assert "gleiche Gesamtkosten" in b["begruendung"] and gewaehlt(erg) is None
print("5 identisch OK")

# ------------------------------------------------------------------ 6) Reste verwertbar (nur mit Lager und Reststücken)
einst_r = dict(EINST, lager_aktiv="ja", reste_aktiv="ja", rest_min_laenge=500, rest_min_nutz=0, restwert_anteil=1.0)
erg, (b,) = lauf([pos(3100, 30)], einst_r)
basis, alt = b["varianten"]
kontrolle(b)
# 6 m: je Stange 6.000 − 20 − 3.100 − 0,3 bleiben (abzüglich Greiferrest im Rest), verwertbar ab 500 mm
assert basis["rest_wert"] > 0 and basis["rest_verwertbar_mm"] > 0, basis
g = type("G", (), dict(endbeschnitt=20, greiferrest=80, kerf=0.3))()
mm = sum(r for r in basis["reste_mm"] if nesting.verwertbar(g, r, 500, 0))
assert abs(basis["rest_verwertbar_mm"] - mm) < 1e-6
assert abs(basis["rest_wert"] - mm * basis["preis_stange"] / 6000) < 1e-6
# ohne Lager/Reststücke kein Restwert (Vorgabe, Patrick 23.11.2026: nur optional)
_, (b0,) = lauf([pos(3100, 30)])
assert all(v["rest_wert"] == 0 for v in b0["varianten"])
print("6 Reste verwertbar OK")

# ------------------------------------------------------------------ 7) Reste nicht verwertbar (zu kurz)
erg, (b,) = lauf([pos(3100, 30)], dict(einst_r, rest_min_laenge=10000))
kontrolle(b)
assert all(v["rest_wert"] == 0 and v["rest_verwertbar_mm"] == 0 for v in b["varianten"])
assert b["empfehlung"] == rechnen.LAENGE_ALTERNATIVE
print("7 Reste nicht verwertbar OK")

# ------------------------------------------------------------------ 8) Maschinenlänge
# max. 6.500 mm: 12 m nur als Zuschnitt (siehe 1); Teil zu lang für jedes Werkstück: 12 m nicht ausführbar, nie gewählt
v = rechnen.variante_planen(rechnen.opt.replace(rechnen.opt.Gruppe(QR, ST, 6000, 20, 80, 0.3, 2), teile=[
    rechnen.opt.Teil(13, 10, "A", 1, 6400, True, True, 100, 100)]), 12000, dict(max_stange=6500), 3)
assert v["fehler"] and not v["stangen"]
# Maschine lädt 12,5 m: 12 m wird direkt geladen (kein Zuschnitt), 10 Beladungen statt 30
db.aendern("maschinen", _t03["id"], "max_stange", 12500)
erg, (b,) = lauf([pos(3100, 30)])
_, alt = b["varianten"]
assert not alt["zuschnitt"] and alt["werkstuecke"] == 10 and b["empfehlung"] == rechnen.LAENGE_ALTERNATIVE, alt
db.aendern("maschinen", _t03["id"], "max_stange", 6500)
print("8 Maschinenlänge OK")

# ------------------------------------------------------------------ 9) Staffeln: je Menge die passende Länge
# 1 Stück: 12 m kostet die ganze Stange (doppelt) -> 6 m; 30 Stück -> 12 m. Gleiche Entscheidung ohne Haken je Stufe.
for menge, soll in ((1, None), (2, None), (30, 12000)):
    erg, _ = lauf([pos(3100, menge)])
    assert gewaehlt(erg) == soll, (menge, gewaehlt(erg))
    erg_a, _ = lauf([pos(3100, menge)], auto=True)                     # Haken 'Lieferlänge automatisch' je Stufe
    assert gewaehlt(erg_a) == soll and erg_a["stangen"] == erg["stangen"], menge
print("9 Staffeln OK")

# ------------------------------------------------------------------ 10) mehrere Abmessungen / Werkstoffe
zr = db.neu("lieferlaengen", dict(profil_id="RR 42,4x2,0", werkstoff_id="1.4301", laenge=12000, basis="€/Stange",
                                  preis=100000.0))
P2 = [pos(3100, 30), pos(3100, 30, profil="RR 42,4x2,0", werkstoff="1.4301", nr=20)]
erg, bs = lauf(P2)
for b in bs:
    kontrolle(b)
assert gewaehlt(erg) == 12000 and gewaehlt(erg, "RR 42,4x2,0") is None
assert {s["stange"] for s in erg["stangen"] if s["profil"] == "RR 42,4x2,0"} == {6000}
db.aendern("lieferlaengen", zr, "preis", 130.0)
erg, _ = lauf(P2)
assert gewaehlt(erg) == gewaehlt(erg, "RR 42,4x2,0") == 12000
print("10 mehrere Abmessungen OK")

# ------------------------------------------------------------------ Übersteuerung von Hand
(vg,) = lauf([pos(3100, 30)])[0]["laengen"]
schl = vg["schluessel"]
erg, _ = lauf([pos(3100, 30)], kp=dict(kopf, laengenwahl={schl: 6000}))      # von Hand 6 m: bleibt bei 6 m
assert gewaehlt(erg) is None and {s["stange"] for s in erg["stangen"]} == {6000}
db.aendern("lieferlaengen", z12, "basis", "€/kg")
db.aendern("lieferlaengen", z12, "preis", 2.40)                       # 12 m teurer, aber von Hand gewählt: gilt
erg, _ = lauf([pos(3100, 30)], kp=dict(kopf, laengenwahl={schl: 12000}))
assert gewaehlt(erg) == 12000
# Automatik aus: wie bisher nur Empfehlung
db.aendern("lieferlaengen", z12, "basis", None)
db.aendern("lieferlaengen", z12, "preis", None)
erg, (b,) = lauf([pos(3100, 30)], dict(EINST, laenge_automatisch="nein"))
assert b["empfehlung"] == rechnen.LAENGE_ALTERNATIVE and gewaehlt(erg) is None
# Vergleich aus (Vorgabe): keine Lieferlängen, nichts geändert
erg, bs = lauf([pos(3100, 30)], dict(EINST, laenge_vergleich="nein"))
assert not bs and {s["stange"] for s in erg["stangen"]} == {6000}
print("Übersteuerung OK")

# ------------------------------------------------------------------ Nesting: dieselbe Entscheidung
par = dict(min_eur=20.0, min_anteil=0.03)
assert rechnen.laenge_vorteil(100.0, 70.0, par)["lohnt"]
assert not rechnen.laenge_vorteil(100.0, 90.0, dict(par, min_eur=20.0))["lohnt"]          # 10 € unter 20 €
assert not rechnen.laenge_vorteil(1000.0, 980.0, par)["lohnt"]                           # 2 % unter 3 %
assert not rechnen.laenge_vorteil(100.0, 110.0, par)["lohnt"]
assert rechnen.laenge_vorteil(None, 50.0, par)["warum"] == "Preis fehlt"
assert rechnen.lange_stangen([6000, 12000, 12000, 6500], dict(handling_ab=6500)) == 2
assert rechnen.lange_stangen([12000], dict(handling_ab=0)) == 0
db.schliessen()
print("Alle Tests 12-m-Zuschnitt OK")
