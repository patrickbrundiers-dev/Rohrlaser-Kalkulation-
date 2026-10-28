"""Teil länger als die Stangenlänge des Angebots (Patrick 28.10.2026): kein FEHLER, wenn es auf eine vorgegebene oder
längere Lieferlänge (z. B. 12 m, beim Lieferanten zugeschnitten) passt; die Optimierung plant die Gruppe dann damit.

Aufruf: python tests/test_teil_laenger_stange.py
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
# RL-1: Endbeschnitt 20, Greiferrest 80, Schnittverlust 0,3, max. Stangenlänge 6.500
_t03 = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T03")
for _feld, _wert in zip(MASCHINE_WERTE, ALTE_MASCHINEN["RL-1"][1]):
    db.aendern("maschinen", _t03["id"], _feld, _wert)
einst = db.einstellungen()
assert einst["laenge_vergleich"] == "nein"          # Vergleich aus: das Ausweichen gilt trotzdem
kopf = dict(maschine="T03", stange=6000)
QR, ST = "QR 40x40x3", "S235-10219"


def pos(laenge, stueck=2, nr=10, **x):
    return dict(pos=nr, artikel=f"T{nr}", profil_id=QR, werkstoff_id=ST, laenge=laenge, stueck=stueck, **x)


def status(p, kp=kopf):
    k, tab = db.kontext(), db.tabellen()
    return rechnen.status(p, rechnen.position_werte(p, kp, k, tab), kp, k)


def optimieren(positionen, kp=kopf):
    return rechnen.optimieren(kp, positionen, db.kontext(), db.tabellen(), einst)


# Nutzlänge 6.000 − 20 − 80 = 5.900: 6.200 mm passt nicht, ohne Lieferlängen bleibt der FEHLER
assert status(pos(6200)) == "FEHLER: Teil länger als Nutzlänge", status(pos(6200))
erg = optimieren([pos(6200)])
assert not erg["stangen"] and erg["fehler"][0]["grund"] == "Teil länger als Nutzlänge der Stange", erg["fehler"]

# 12-m-Lieferlänge: Werkstück bis 6.500 − 50 Puffer = 6.450 -> 6.200 mm passt, kein FEHLER
db.neu("lieferlaengen", dict(profil_id=QR, werkstoff_id=ST, laenge=12000))
assert not status(pos(6200)).startswith("FEHLER"), status(pos(6200))
erg = optimieren([pos(6200), pos(2000, 3, nr=20)])
assert not erg["fehler"], erg["fehler"]
assert erg["stangen"] and all(s["stange"] == 12000 and s["grundlaenge"] == 6000 for s in erg["stangen"])
geplant = sorted(t["laenge"] for s in erg["stangen"] for t in s["teile"])
assert geplant == [2000] * 3 + [6200] * 2, geplant
assert max(w["laenge"] for s in erg["stangen"] for w in s["werkstuecke"]) <= 6500
(vg,) = erg["laengen"]
assert vg["zu_kurz"] and vg["gewaehlt"] == 12000 and not vg["basis_lieferbar"], vg
b = rechnen.laengen_bewerten(vg, kopf, [pos(6200)], db.kontext(), db.tabellen(), einst)
assert b["titel"] == "Teil zu lang für 6 m – 12-m-Stangen verwenden", b["titel"]
# Prüfsumme: gleiche Eingaben -> aktuell
assert erg["kennung"] == rechnen.eingabe_kennung(kopf, [pos(6200), pos(2000, 3, nr=20)], db.kontext(), db.tabellen(),
                                                 einst)
# kurze Teile allein bleiben auf 6 m (keine Änderung ohne zu langes Teil)
assert all(s["stange"] == 6000 for s in optimieren([pos(2000, 3)])["stangen"])

# Teil passt auf kein Werkstück (6.400 + 20 + 80 + 0,3 > 6.450): FEHLER bleibt
assert status(pos(6400)) == "FEHLER: Teil länger als Nutzlänge", status(pos(6400))
assert optimieren([pos(6400)])["fehler"][0]["grund"] == "Teil länger als Nutzlänge der Stange"

# Kundenmaterial kommt in der Stangenlänge des Angebots: FEHLER bleibt
kunde = pos(6200, material_herkunft=rechnen.KUNDENMATERIAL)
assert status(kunde) == "FEHLER: Teil länger als Nutzlänge", status(kunde)

# Profil vom Vergleich ausgenommen: FEHLER bleibt
pid = next(z["id"] for z in db.zeilen("profile") if z["profil_id"] == QR)
db.aendern("profile", pid, "laengenvergleich", "nein")
assert status(pos(6200)) == "FEHLER: Teil länger als Nutzlänge"
db.aendern("profile", pid, "laengenvergleich", None)
print("Lieferlänge OK")

# Stangen von Hand vorgegeben (6.500 mm): 6.200 passt, kein FEHLER, auch ohne Lieferlängen
db.loeschen("lieferlaengen", [z["id"] for z in db.zeilen("lieferlaengen")])
assert status(pos(6200)).startswith("FEHLER")
schl = rechnen.laengen_schluessel((QR, ST, "", 6000))
kv = dict(kopf, stangen_vorgabe={schl: [[6500, 3]]})
assert not status(pos(6200), kv).startswith("FEHLER"), status(pos(6200), kv)
erg = optimieren([pos(6200)], kv)
assert not erg["fehler"] and [s["stange"] for s in erg["stangen"]] == [6500, 6500], erg["fehler"]
print("Stangenvorgabe OK")
print("Alle Tests OK")
