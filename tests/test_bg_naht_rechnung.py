"""Prüft a-Maß, Heftpunkte und Schweißzeit (Plan Schweißbaugruppen 28.10.2026, Schritt 5, Freigabe „Alle a“):
- A1 a-Maß-Regel: 0,7 × dünnere Wand, mindestens 3 mm (Einstellung schweiss_a_min), mindestens √(dickere Wand) − 0,5,
  höchstens die dünnere Wand; 0 = alte Regel
- A2 Kennwert zwischen zwei Zeilen nach dem Nahtquerschnitt (a²), auf den Zeilen unverändert
- A3 mehrlagig ab 'a je Lage' mit Zeit je Zusatzlage; ohne Regel einlagig (alter Stand bitgleich)
- A4 Heftpunkte: + 1 für die Enden, rundum nach Umfang, Edelstahl/Aluminium enger; Heftzeit nach Wanddicke
- A5 Vorschlag aus STEP mit dickerer Wand (dicke_max)

Aufruf: python tests/test_bg_naht_rechnung.py
"""
import math
import os
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import baugruppe, step_einstellungen, vorkalk  # noqa: E402


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ A1 a-Maß
r = baugruppe.a_mass_regel
assert baugruppe.A_MIN == 3.0 and step_einstellungen.WEITERE["schweiss_a_min"] == (baugruppe, "A_MIN", 3.0)
assert r(5, 0.7) == 3.5                       # 0,7 × 5 = 3,5
assert r(4, 0.7) == 3.0                       # 2,8 → 2,5, mindestens 3
assert r(2, 0.7) == 2.0                       # mindestens 3, aber höchstens die Wand 2
assert r(2.5, 0.7) == 2.5
assert r(5, 0.7, 30) == 5.0                   # √30 − 0,5 = 4,98 → 5,0 (aufgerundet auf 0,5)
assert r(5, 0.7, 6) == 3.5                    # √6 − 0,5 = 1,95: 3,5 bleibt
assert r(3, 0.7, 30) == 3.0                   # höchstens die dünnere Wand
assert "mindestens √30" in baugruppe.a_mass_text(5, 0.7, 30) and "5 mm" in baugruppe.a_mass_text(5, 0.7, 30)
alt = baugruppe.A_MIN
baugruppe.A_MIN = 0.0
assert r(4, 0.7) == 2.5 and r(2, 0.7) == 1.0 and r(0.5, 0.7) is None          # wie vor 0.9.177
baugruppe.A_MIN = alt
ok("A1 a-Maß: 0,7 × t, mindestens 3 mm bzw. √t − 0,5, höchstens die dünnere Wand; Einstellung 0 = alte Regel")

# ------------------------------------------------------------------ A2 Kennwert interpolieren
TAB = dict(schweissverfahren=[dict(verfahren="MAG", satz_id="Schweißen", lichtbogen=50, heft_s=6, status="geprüft")],
           schweiss_kennwerte=[dict(verfahren="MAG", nahtart="Kehlnaht", mass_bis=m, min_m=z, status="geprüft")
                               for m, z in ((3, 2.0), (4, 3.2), (6, 6.0), (10, 15.0))])
for a, soll in ((3, 2.0), (4, 3.2), (6, 6.0), (2, 2.0)):
    nah(baugruppe.kennwert_min_m("MAG", "Kehlnaht", a, TAB)[0], soll, f"a = {a} auf der Zeile")
q = lambda a: baugruppe.nahtquerschnitt("Kehlnaht", a)          # noqa: E731
nah(baugruppe.kennwert_min_m("MAG", "Kehlnaht", 3.5, TAB)[0], 2.0 + 1.2 * (q(3.5) - q(3)) / (q(4) - q(3)), "a = 3,5")
assert 2.0 < baugruppe.kennwert_min_m("MAG", "Kehlnaht", 3.5, TAB)[0] < 3.2
assert baugruppe.kennwert_min_m("MAG", "Kehlnaht", 12, TAB) == (None, None)
naht = dict(verfahren="MAG", nahtart="Kehlnaht", mass=3.5, laenge=1000, anzahl=1)
nah(baugruppe.naht_rechnen(naht, TAB, {"Schweißen": 60})["lichtbogen_min"],
    round(baugruppe.kennwert_min_m("MAG", "Kehlnaht", 3.5, TAB)[0], 4), "Lichtbogenzeit 1 m mit dem Zwischenwert")
ok("A2 Kennwert nach Nahtquerschnitt: a = 3,5 zwischen 2,0 und 3,2 min/m, auf den Zeilen unverändert")

# ------------------------------------------------------------------ A3 mehrlagig
REGELN = [dict(art=a, wert=w, bis=b, zahl=z, status="geprüft") for a, w, b, z, _ in vorkalk.RICHTWERTE]
TAB_R = dict(TAB, schweiss_regeln=REGELN)
n8 = dict(verfahren="MAG", nahtart="Kehlnaht", mass=8, laenge=1000, anzahl=2)
ohne = baugruppe.naht_rechnen(n8, TAB, {"Schweißen": 60})
mit = baugruppe.naht_rechnen(n8, TAB_R, {"Schweißen": 60})
assert ohne["lagen"] == 1 and mit["lagen"] == 2
nah(mit["zwischen_min"], 2 * 1 * 1.0, "2 m Naht × 1 Zusatzlage × 1 min/m")
nah(mit["zeit_min"] - ohne["zeit_min"], 2.0, "nur die Zwischenzeit kommt dazu")
assert baugruppe.lagen_zahl(dict(mass=6), dict(lage_a=6)) == 1 and baugruppe.lagen_zahl(dict(mass=13), dict(lage_a=6)) == 3
st_alt = {k: v for k, v in baugruppe.naht_stand(n8, TAB_R).items() if k not in ("lage_a", "zusatzlage_min_m", "f_heft")}
nah(baugruppe.naht_rechnen(dict(n8, stand=st_alt), TAB_R, {"Schweißen": 60})["zeit_min"], ohne["zeit_min"],
    "gemerkter Stand ohne die neuen Werte: wie vorher")
ok("A3 a = 8 bei 6 mm je Lage: 2 Lagen, + 2 min Zwischenzeit; ohne Regel und alter Stand einlagig")

# ------------------------------------------------------------------ A4 Heften
regeln = vorkalk.Regeln(TAB_R)
gerade = dict(laenge=120, dicke=3)                  # Heftabstand bis 4 mm = 50
assert vorkalk.heftpunkte(gerade, regeln)[0] == 4            # aufrunden(2,4) + 1
assert "+ 1" in vorkalk.heftpunkte(gerade, regeln)[1]
assert vorkalk.heftpunkte(dict(laenge=30, dicke=3), regeln)[0] == 2           # 1 + 1 = 2 (Mindestzahl 2)
assert vorkalk.heftpunkte(dict(laenge=150, dicke=3), regeln)[0] == 4          # 3 + 1
rund = dict(laenge=math.pi * 48.3, dicke=3, rundum=True)                     # Ø48,3: 151,7 mm Umfang
assert vorkalk.heftpunkte(rund, regeln)[0] == 4                              # aufrunden(3,03) = 4, kein + 1
gross = dict(laenge=math.pi * 219.1, dicke=6, rundum=True)                    # 688 mm, Abstand 60 → 12
assert vorkalk.heftpunkte(gross, regeln)[0] == 12
klein = dict(laenge=math.pi * 21.3, dicke=2, rundum=True)                     # 67 mm: Mindestzahl 3
assert vorkalk.heftpunkte(klein, regeln)[0] == 3
weit = vorkalk.Regeln(dict(schweiss_regeln=[z for z in REGELN if z["wert"] != "Mindestzahl rundum"]
                           + [dict(art="Heften", wert="Mindestzahl rundum", zahl=3, status="geprüft")]))
assert vorkalk.heftpunkte(dict(laenge=math.pi * 219.1, dicke=12, rundum=True), weit)[0] == 9   # 688 ÷ 80 = 8,6 → 9
edel = dict(gerade, werkstoff="Edelstahl")                                    # 50 × 0,7 = 35 → aufrunden(3,43) + 1
assert vorkalk.heftpunkte(edel, regeln)[0] == 5 and "Edelstahl" in vorkalk.heftpunkte(edel, regeln)[1]
assert vorkalk.heftpunkte(dict(gerade, werkstoff="Aluminium"), regeln)[0] == 5
assert vorkalk.heftpunkte(dict(gerade, werkstoff="Stahl"), regeln)[0] == 4
for d, f in ((2, 1.0), (5, 1.3), (8, 1.6)):
    n = dict(verfahren="MAG", nahtart="Kehlnaht", mass=3, laenge=1000, anzahl=1, heftpunkte=10, dicke=d)
    nah(baugruppe.naht_rechnen(n, TAB_R, {"Schweißen": 60})["heft_min"], 10 * 6 / 60 * f, f"Heftzeit Wand {d}")
    nah(baugruppe.naht_rechnen(n, TAB, {"Schweißen": 60})["heft_min"], 10 * 6 / 60, f"ohne Regel Wand {d}")
ok("A4 Heftpunkte + 1 Enden, rundum nach Umfang, Edelstahl/Alu × 0,7, Heftzeit × 1 / 1,3 / 1,6 nach Wanddicke")

# ------------------------------------------------------------------ A5 Vorschlag aus STEP
bg = baugruppe.leer()
kand = [dict(teile=[1, 2], laenge_mm=200, stossart="Kehlnaht", dicke_mm=5, dicke_max_mm=30),
        dict(teile=[1, 3], laenge_mm=200, stossart="Kehlnaht", dicke_mm=5, dicke_max_mm=20)]
v = baugruppe.vorschlaege_aus_step(bg, kand)
assert len(v) == 1 and v[0]["dicke_max"] == 30
n = baugruppe.vorschlag_naht(v[0], 0.7)
assert n["mass"] == 5.0 and n["mass_regel"] == 5.0 and n["dicke_max"] == 30
n = baugruppe.vorschlag_naht(dict(v[0], dicke_max=None), 0.7)
assert n["mass"] == 3.5 and "dicke_max" not in n
ok("A5 STEP mit dickerer Wand 30 mm: a = 5 statt 3,5 (√30 − 0,5)")
print("Alle Naht-Rechnungs-Tests bestanden.")
