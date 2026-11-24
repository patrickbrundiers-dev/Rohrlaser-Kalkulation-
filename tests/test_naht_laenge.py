"""Prüft „Schweißnahtlänge und Positionieren besser berechnen“ (Patrick 03.11.2026, Freigabe „Alle Empfehlungen“):
- N1 Länge aus einem Teil (rundum = Umfang, Längsnaht = Teillänge, 2 Seiten = 2 × Breite)
- N2 STEP genauer: parallele Rohre nur Längsnähte, Kastenrohr über schmalerem Rohr nur die aufliegenden Wände,
     Lasche ohne Stirnseiten; Aufteilung als Text (STEP-JSON 1.26), bis ins Nahtgruppen-Feld
- N3 Stichnaht: geschweißt % kürzt die Naht [m], je weiteren Stich ein Ansatz
- N4 Positionieren: Basisteil = schwerstes Teil, Faktor nach Stückgewicht

Aufruf: python tests/test_naht_laenge.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
MESSEN = HIER.parent / "programm" / "step_messung" / "step_messen.py"

from rohrlaser import baugruppe, bg_mengen, vorkalk  # noqa: E402
from rohrlaser.angebot import ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ N3 Stichnaht
naht = dict(verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=500, anzahl=2, heftpunkte=3,
            stand=dict(verfahren=True, min_m=1.0, lichtbogen=50, heft_s=6, satz_id="Schweißen"))
voll = baugruppe.naht_rechnen(naht, {}, {"Schweißen": 60})
assert abs(voll["naht_m"] - 1.0) < 1e-9 and "Stich" not in voll["rechenweg"]
halb = baugruppe.naht_rechnen(dict(naht, geschweisst=50), {}, {"Schweißen": 60})
assert abs(halb["naht_m"] - 0.5) < 1e-9
assert baugruppe.stiche(dict(naht, geschweisst=50)) == 5                  # 250 mm ÷ 50 mm je Stich
assert abs(halb["stich_min"] - 4 * 2 * 6 / 60) < 1e-9                      # 4 weitere Stiche × 2 Nähte × 6 s
assert abs(halb["zeit_min"] - (0.5 / 0.5 + 3 * 2 * 6 / 60 + 0.8)) < 1e-9, halb
assert "(Stichnaht 50 %)" in halb["rechenweg"] and "Stiche 8 Ansätze" in halb["rechenweg"], halb["rechenweg"]
assert baugruppe.stiche(dict(naht, geschweisst=50), dict(stich_mm=125)) == 2
assert baugruppe.naht_meter(dict(naht, geschweisst=0)) == baugruppe.naht_meter(naht)    # 0 / leer = 100 %
ok("N3 Stichnaht: geschweißt % kürzt die Naht, Ansätze je Stich, Rechenweg")

# ------------------------------------------------------------------ N1 Länge aus einem Teil, N4 Positionieren
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
k = db.kontext()
rohr = dict(pos=10, artikel="R", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=600)
w, text = bg_mengen.naht_laenge_aus(bg_mengen.RUNDUM, rohr, k)
assert 145 < w < 160 and "Umfang QR 40x40x3" in text, (w, text)
assert bg_mengen.naht_laenge_aus(bg_mengen.LAENGS, rohr, k)[0] == 600
assert bg_mengen.naht_laenge_aus(bg_mengen.ZWEI_SEITEN, rohr, k) == (80.0, "2 × 40 mm (QR 40x40x3)")
assert bg_mengen.naht_laenge_aus(bg_mengen.RUNDUM, dict(rohr, profil_id="gibt es nicht"), k)[0] is None
ok("N1 Länge aus Teil: rundum = Umfang, Längsnaht = Länge, 2 Seiten = 2 × Breite")

regeln = vorkalk.Regeln(dict(schweiss_regeln=vorkalk.richtwerte()))
bg = baugruppe.leer()
positionen = [
    dict(id=1, pos=10, artikel="Lasche", art=ZUKAUFTEIL, gewicht_teil=0.3, je_knoten=4),
    dict(id=2, pos=20, artikel="Holm", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=6000, je_knoten=1),
    dict(id=3, pos=30, artikel="Platte", art=ZUKAUFTEIL, gewicht_teil=3.0, je_knoten=1)]
for p in positionen:
    p.update(bg_knoten=bg["id"])
g_holm = bg_mengen.teil_werte(positionen[1], k)["gewicht"]
assert g_holm > 20, g_holm
hilfen = {0: "frei", 1: "frei", 2: "frei"}
t, text = vorkalk.positionieren(bg, positionen, bg["id"], regeln, hilfen, k)
# Basisteil Holm (schwerstes, > 20 kg: × 3), 4 Laschen × 2 × 0,5, Platte × 2 × 1,0
assert abs(t - (0.5 * 3 + 4 * 2 * 0.5 + 2 * 1.0)) < 1e-9, (t, text)
assert "1 × 0,5 (Basisteil) × 3 (über 20 kg (Kran))" in text and "4 × 2 (frei) × 0,5 (bis 1 kg)" in text, text
alt = vorkalk.Regeln(dict(schweiss_regeln=[z for z in vorkalk.richtwerte() if not z["wert"].startswith("Faktor")
                                           or z["art"] != "Positionieren"]))
t0, text0 = vorkalk.positionieren(bg, positionen, bg["id"], alt, hilfen, k)
assert abs(t0 - (0.5 + 5 * 2.0)) < 1e-9 and "Faktor" not in text0 and "kg" not in text0, (t0, text0)
ok("N4 Positionieren: Basisteil = schwerstes Teil, Faktor nach Gewicht; ohne Regeln wie bisher")

# ------------------------------------------------------------------ N2 STEP genauer
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402
from erzeuge_struktur_teile import Dokument, lage  # noqa: E402
from erzeuge_testteile import kastenrohr  # noqa: E402

PI2 = 1.5707963267948966
faelle = {
    "parallel": [("Rohr1", kastenrohr(40, 40, 3, 500, 4.5), lage()),
                 ("Rohr2", kastenrohr(40, 40, 3, 500, 4.5), lage(40, 0, 0))],
    "ueber": [("Holm", kastenrohr(40, 40, 3, 600, 4.5), lage()),
              ("Stiel", kastenrohr(60, 60, 3, 300, 4.5), lage(20, 0, 300, um_y=PI2))],
    "gleich": [("Holm", kastenrohr(60, 40, 3, 600, 4.5), lage()),
               ("Stiel", kastenrohr(40, 40, 3, 300, 4.5), lage(30, 0, 300, um_y=PI2))],
    "lasche": [("Rohr", kastenrohr(40, 40, 3, 500, 4.5), lage()),
               ("Lasche", BRepPrimAPI_MakeBox(gp_Pnt(20, -2.5, 200), 40, 5, 80).Shape(), lage())],
}
dateien = []
for n, teile in faelle.items():
    d = Dokument()
    d.baugruppe(n, [(d.teil(name, s), lg) for name, s, lg in teile])
    d.schreiben(tmp / f"{n}.step")
    dateien.append(str(tmp / f"{n}.step"))
r = subprocess.run([sys.executable, str(MESSEN), "--ausgabe", str(tmp / "m.txt"), "--json", str(tmp / "m.json")]
                   + dateien, capture_output=True, text=True, timeout=600)
assert r.returncode == 0, r.stderr
erg = json.loads((tmp / "m.json").read_text(encoding="utf-8"))
assert erg["schema_version"] >= "1.26"
kand = {Path(x["datei"]).stem: x["nahtkandidaten"] for x in erg["dateien"]}
assert all(len(v) == 1 for v in kand.values()), kand
p_, u_, g_, l_ = (kand[n][0] for n in ("parallel", "ueber", "gleich", "lasche"))
assert p_["laenge_mm"] == 1000.0 and p_["aufteilung"].startswith("2 × 500,0 mm Längsnaht") and \
    p_["stichnaht_moeglich"], p_
assert u_["laenge_mm"] == 80.0 and "steht über" in u_["aufteilung"], u_
assert abs(g_["laenge_mm"] - 152.3) < 0.2 and g_["aufteilung"].startswith("rundum"), g_
assert l_["laenge_mm"] == 160.0 and "Stirnseiten 2 × 5,0 mm ohne Naht" in l_["aufteilung"], l_
v = baugruppe.vorschlaege_aus_step(baugruppe.leer(), kand["parallel"])[0]
assert v["aufteilung"] == p_["aufteilung"] and v["stichnaht_moeglich"]
assert baugruppe.vorschlag_naht(v)["aufteilung"] == p_["aufteilung"]
ok("N2 STEP: parallel 2 × 500, Überstand 2 × 40, gleich breit rundum 152, Lasche 2 × 80, Aufteilung in Nahtgruppe")
print("Alle Prüfungen bestanden.")
