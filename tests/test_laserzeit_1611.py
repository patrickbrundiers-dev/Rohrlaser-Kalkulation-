"""Laserzeit genauer (Patrick 16.11.2026, Freigabe „1c 2a 3a“).

3a Faktor Laserzeit: Einstellung (Vorgabe 1,0 = wie berechnet) und Feld im Angebotskopf (leer = Einstellung); er
   wirkt auf die berechnete Laserzeit je Teil, nicht auf von Hand eingetragene Schneidzeiten. Festgeschriebene
   Angebote ohne den Wert rechnen mit 1,0.
E1 Einstechzeit berechnet (Plan „Laserzeit vollständig berechnen“ Phase 1): Grundzeit + 0,1 s × Wand^1,4 ×
   √(6 kW ÷ Leistung) × Werkstofffaktor, Überwachung × 0,75; ohne Grundzeit/Leistung die Schneiddaten. Beim Update
   vorhandener Dateien einmal Richtwerte in leere Felder von T03/T11/LT7, neue Dateien ohne.

Aufruf: python tests/test_laserzeit_1611.py
"""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import beispiel_angebot as bsp_a  # noqa: E402
from rohrlaser import angebot, einstechen, rechnen, sichtbarkeit  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNG  # noqa: E402


def ok(text):
    print("OK    ", text)


def nah(a, b, text="", eps=1e-6):
    assert abs(float(a) - float(b)) <= eps * max(1.0, abs(a), abs(b)), f"{text}: {a} != {b}"


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "lz.db")
k, tab, e = db.kontext(), db.tabellen(), db.einstellungen()
kopf = dict(bsp_a.KOPF)
pos = [dict(p, id=i) for i, p in enumerate(bsp_a.POSITIONEN, 1)]
erg = rechnen.optimieren(kopf, pos, k)

# ------------------------------------------------------------------ 3a Faktor Laserzeit
assert SCHEMA_VERSION >= 93
assert EINSTELLUNG["faktor_laserzeit"].vorgabe == 1.0 and e.get("faktor_laserzeit") == 1.0
assert "faktor_laserzeit" in {f.name for f in angebot.KALKULATION}
assert "faktor_laserzeit" not in angebot.KALK_PROZENT and "faktor_laserzeit" not in angebot.KALK_OHNE_VORGABE
assert "faktor_laserzeit" in rechnen.EINST_FEST and "faktor_laserzeit" in sichtbarkeit.KOPF_ROLLEN
assert db.kalkulation_vorgaben()["faktor_laserzeit"] == 1.0

z1, s1 = rechnen.kalkulation(kopf, pos, erg, k, tab, e)
z2, s2 = rechnen.kalkulation(kopf, pos, erg, k, tab, rechnen.einstellungen_angebot(dict(kopf, faktor_laserzeit=1.2), e))
z3, s3 = rechnen.kalkulation(kopf, pos, erg, k, tab, dict(e, faktor_laserzeit=1.2))
n = 0
for a, b in zip(z1, z2):
    if a.get("laser_netto") is None:
        continue
    teil = a["laser_netto"] - a.get("zeit_extra", 0.0)
    if a.get("zeit_manuell") == "ja":
        nah(b["laser_netto"], a["laser_netto"], "von Hand bleibt")
        continue
    nah(b["laser_netto"], a["laser_netto"] + 0.2 * teil, f"Pos. {a['pos']}")
    assert b["faktor_laserzeit"] == 1.2 and a["faktor_laserzeit"] == 1.0
    n += 1
assert n >= 3
nah(s2["laser_schneiden"], 1.2 * s1["laser_schneiden"], "Laserkosten × 1,2", eps=1e-3)
nah(s3["laser_schneiden"], s2["laser_schneiden"], "Einstellung = Angebotskopf")
assert s2["verkauf"] > s1["verkauf"]
texte = dict((t.split(" (")[0], t) for t, _, _ in rechnen.kostenarten(s2, e))
assert any("Faktor Laserzeit 1,2" in t for t, _, _ in rechnen.kostenarten(s2, e)), texte
assert not any("Faktor Laserzeit" in t for t, _, _ in rechnen.kostenarten(s1, e))
ok(f"3a Faktor 1,2: Laserkosten {s1['laser_schneiden']:.2f} → {s2['laser_schneiden']:.2f} €, "
   f"Verkauf {s1['verkauf']:.2f} → {s2['verkauf']:.2f} €")

# von Hand eingetragene Schneidzeit bleibt
pos_h = [dict(p, zeit_manuell=30.0) if i == 0 else p for i, p in enumerate(pos)]
zh1, _ = rechnen.kalkulation(kopf, pos_h, erg, k, tab, e)
zh2, _ = rechnen.kalkulation(kopf, pos_h, erg, k, tab, dict(e, faktor_laserzeit=1.5))
nah(zh1[0]["laser_netto"], zh2[0]["laser_netto"], "manuell")
assert zh2[0]["faktor_laserzeit"] == 1.0 and zh2[1]["laser_netto"] > zh1[1]["laser_netto"]
ok("3a Schneidzeit von Hand ohne Faktor")

# festgeschriebene Preisbasis ohne den Wert: 1,0
assert rechnen.faktor_laserzeit({}) == 1.0 and rechnen.faktor_laserzeit({"faktor_laserzeit": None}) == 1.0
assert rechnen.faktor_laserzeit({"faktor_laserzeit": 0}) == 1.0
ok("3a ohne Wert bzw. festgeschrieben vor dem 16.11.2026: Faktor 1,0")

# ------------------------------------------------------------------ E1 Einstechzeit berechnet
from rohrlaser.stammdaten import EINSTICH_RICHTWERTE  # noqa: E402
m11 = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
assert m11.get("einstich_grund") is None and not einstechen.aktiv(m11)     # neue Datei: wie bisher
assert db.einstellung("einstich_stand") == 1
assert einstechen.zeit(m11, 3, "Stahl", 0.3) == 0.3
m = dict(m11, laser_kw=4.0, einstich_grund=0.15, einstich_ueberwachung="nein")
nah(einstechen.zeit(m, 3, "Stahl", 0.3), 0.15 + 0.1 * 3 ** 1.4 * 1.5 ** 0.5, "Stahl 3 mm 4 kW", eps=1e-3)
nah(einstechen.zeit(m, 3, "Edelstahl", 0.3), 0.15 + 1.75 * 0.1 * 3 ** 1.4 * 1.5 ** 0.5, "Edelstahl", eps=1e-3)
nah(einstechen.zeit(dict(m, einstich_ueberwachung="ja"), 3, "Stahl", 0.3),
    0.15 + 0.75 * 0.1 * 3 ** 1.4 * 1.5 ** 0.5, "Überwachung", eps=1e-3)
nah(einstechen.zeit(dict(m, laser_kw=6.0, einstich_grund=0.0), 10, "Stahl", 9), 0.1 * 10 ** 1.4, "6 kW 10 mm", eps=1e-3)
assert einstechen.zeit(m, 6, "Stahl", 1) > einstechen.zeit(m, 3, "Stahl", 1) > einstechen.zeit(m, 1, "Stahl", 1)
assert einstechen.zeit(dict(m, laser_kw=None), 3, "Stahl", 0.3) == 0.3
ok(f"E1 Formel: Stahl 3 mm 4 kW {einstechen.zeit(m, 3, 'Stahl', 0):.2f} s (Tabelle 0,3 s), Edelstahl "
   f"{einstechen.zeit(m, 3, 'Edelstahl', 0):.2f} s")

for x in db.zeilen("maschinen"):
    for n, w in zip(("laser_kw", "einstich_grund", "einstich_ueberwachung"), EINSTICH_RICHTWERTE.get(x["maschinen_id"], ())):
        db.aendern("maschinen", x["id"], n, w)
k2, tab2 = db.kontext(), db.tabellen()
ze, se = rechnen.kalkulation(kopf, pos, erg, k2, tab2, e)
mehr = 0
for a, b in zip(z1, ze):
    if a.get("laser_netto") is None or not a.get("einstiche_teil"):
        continue
    assert b["einstechzeit"] > a["einstechzeit"], (a["pos"], a["einstechzeit"], b["einstechzeit"])
    assert b["zeit_einstiche"] > a["zeit_einstiche"] and b["laser_netto"] > a["laser_netto"]
    mehr += 1
assert mehr >= 3 and se["laser_schneiden"] > s1["laser_schneiden"]
ok(f"E1 im Angebot: Laserkosten {s1['laser_schneiden']:.2f} → {se['laser_schneiden']:.2f} €")

# Update einer vorhandenen Datei: Richtwerte einmal in leere Felder, eigene Werte bleiben
db2 = Datenbank(tmp / "alt.db")
for x in db2.zeilen("maschinen"):
    if x["maschinen_id"] == "LT7":
        db2.aendern("maschinen", x["id"], "einstich_grund", 0.3)
db2.con.execute("DELETE FROM einstellungen WHERE name = 'einstich_stand'")
db2.con.commit()
db2._einstich_ergaenzen()
mm = {x["maschinen_id"]: x for x in db2.zeilen("maschinen")}
assert mm["T11"]["laser_kw"] == 4.0 and mm["T11"]["einstich_grund"] == 0.15 and mm["T11"]["einstich_ueberwachung"] == "ja"
assert mm["LT7"]["einstich_grund"] == 0.3 and mm["LT7"]["laser_kw"] == 3.0 and mm["T03"]["laser_kw"] == 3.2
ok("E1 Update: Richtwerte in leere Felder, eigene Werte bleiben")

# festgeschriebene Preisbasis ohne die Felder: Einstechzeit der Schneiddaten
assert {"laser_kw", "einstich_grund", "einstich_ueberwachung"} <= set(rechnen.MASCHINE_NEU)
print("Alle Prüfungen bestanden.")
