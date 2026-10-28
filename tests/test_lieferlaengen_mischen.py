"""Vorschlag Mischen (Patrick 28.10.2026): 12-m- und 6-m-Stangen in einer Abmessung, nur zum Ansehen.

Aufruf: python tests/test_lieferlaengen_mischen.py
"""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import ALTE_MASCHINEN, MASCHINE_WERTE  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
_t03 = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T03")
for _feld, _wert in zip(MASCHINE_WERTE, ALTE_MASCHINEN["RL-1"][1]):
    db.aendern("maschinen", _t03["id"], _feld, _wert)
einst = dict(db.einstellungen(), laenge_vergleich="ja")
kopf = dict(maschine="T03", stange=6000)
QR, ST = "QR 40x40x3", "S235-10219"
db.neu("lieferlaengen", dict(profil_id=QR, werkstoff_id=ST, laenge=12000))


def pos(laenge, stueck, nr=10):
    return dict(pos=nr, artikel=f"T{nr}", profil_id=QR, werkstoff_id=ST, laenge=laenge, stueck=stueck)


def bewerten(positionen):
    k, tab = db.kontext(), db.tabellen()
    erg = rechnen.optimieren(kopf, positionen, k, tab, einst)
    (vg,) = erg["laengen"]
    return erg, rechnen.laengen_bewerten(vg, kopf, positionen, k, tab, einst)


# 31 × 3.100 mm: 3 Teile je 12-m-Stange -> 11 × 12 m, die letzte nur mit 1 Teil; gemischt 10 × 12 m + 1 × 6 m
erg, b = bewerten([pos(3100, 31)])
basis, lang = b["varianten"]
assert lang["lieferstangen"] == 11 and basis["lieferstangen"] == 31, (lang["lieferstangen"], basis["lieferstangen"])
mi = lang["mischung"]
assert (mi["lang"], mi["basis"]) == (10, 1) and mi["material_mm"] == 126000, mi
assert mi["werkstuecke"] == 31 and mi["zuschnitte"] == lang["zuschnitte"] - 1, (mi, lang["zuschnitte"])
assert mi["gesamt"] < lang["gesamt"] and not mi["fehlt"], mi
v = b["mischung"]
assert v["text"] == "10 × 12 m + 1 × 6 m" and v["laenge"] == 12000 and v["ersparnis"] > 0, v
# nur ein Vorschlag: der Schnittplan bleibt bei 6 m (nichts übernommen)
assert all(s["stange"] == 6000 for s in erg["stangen"]) and len(erg["stangen"]) == 31

# Stangenbelegung des Vorschlags (nur Ansicht): 10 Lieferstangen 12 m mit Werkstücken + 1 Stange 6 m
(vg,) = erg["laengen"]
st = rechnen.mischung_stangen(kopf, [pos(3100, 31)], db.kontext(), db.tabellen(), einst, vg, 12000)
assert sorted(s["stange"] for s in st) == [6000] + [12000] * 10, [s["stange"] for s in st]
assert sum(len(s["teile"]) for s in st) == 31 and [len(s["teile"]) for s in st if s["stange"] == 6000] == [1]
assert all(s.get("werkstuecke") for s in st if s["stange"] == 12000)
assert len(rechnen.anzeige_stangen(dict(stangen=st))) == 31          # je Beladung eine Stange im Bild

# Vergleich in den Einstellungen aus: kein Vorschlag (Patrick 28.10.2026: nur wenn eingeschaltet), auch nicht bei
# einem Teil, das nur auf 12 m passt
_aus = dict(einst, laenge_vergleich="nein")
_p = [pos(3100, 30), pos(6200, 1, nr=20)]
_erg = rechnen.optimieren(kopf, _p, db.kontext(), db.tabellen(), _aus)
assert not any(v.get("mischung") for vg in _erg["laengen"] for v in vg["varianten"])

# 30 × 3.100: alle 12-m-Stangen voll belegt, eine 6-m-Stange spart nichts -> kein Vorschlag
_, b = bewerten([pos(3100, 30)])
assert "mischung" not in b["varianten"][1] and b["mischung"] is None, b["mischung"]

print("Mischen OK")
print("Alle Tests OK")
