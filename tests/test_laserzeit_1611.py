"""Laserzeit genauer (Patrick 16.11.2026, Freigabe „1c 2a 3a“).

3a Faktor Laserzeit: Einstellung (Vorgabe 1,0 = wie berechnet) und Feld im Angebotskopf (leer = Einstellung); er
   wirkt auf die berechnete Laserzeit je Teil, nicht auf von Hand eingetragene Schneidzeiten. Festgeschriebene
   Angebote ohne den Wert rechnen mit 1,0.

Aufruf: python tests/test_laserzeit_1611.py
"""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
import beispiel_angebot as bsp_a  # noqa: E402
from rohrlaser import angebot, rechnen, sichtbarkeit  # noqa: E402
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
print("Alle Prüfungen bestanden.")
