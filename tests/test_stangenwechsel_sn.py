"""Prüft die zwei Stangenwechselzeiten je Maschine (Patrick 22.10.2026): Stangen, auf denen ein Teil eine feste
Schweißnaht-Lage hat, rechnen mit 'Stangenwechsel SN' (Vorgabe 29 s), alle anderen mit 'Stangenwechsel' (24 s).
- W1 Vorgaben neuer Dateien, Zählung beladungen_sn (auch zugeschnittene Lieferstangen je Werkstück)
- W2 Angebot ohne Naht: nur normaler Stangenwechsel; mit fester Naht: SN-Zeit nur für die betroffenen Stangen
- W3 Zeiten-Reiter (Formel), Anteil je Teil (Staffelpreise), Snapshot-Abweichung
- W4 Snapshot ohne SN-Wert (Angebote vor 0.8.9): SN = normaler Wert, Preis unverändert
- W5 Schema 38: T03/T11/LT7 mit altem Wert -> 24/29 s, eigene Werte bleiben und werden SN

Aufruf: python tests/test_stangenwechsel_sn.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import naht, optimierung as opt, rechnen  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

EPS = 1e-6


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)

# ------------------------------------------------------------------ W1 Vorgaben und Zählung
k = db.kontext()
for m in ("T03", "T11", "LT7"):
    assert (k.maschinen[m]["stangenwechsel"], k.maschinen[m]["stangenwechsel_sn"]) == (24, 29), k.maschinen[m]
assert rechnen.stangenwechsel_zeiten(dict(stangenwechsel=30)) == (30, 30)
assert rechnen.stangenwechsel_zeiten(dict(stangenwechsel=24, stangenwechsel_sn=0)) == (24, 0)
FEST, FREI = dict(drehfreigabe=opt.FEST), dict(drehfreigabe=opt.FREI)
stangen = [dict(teile=[FREI, FREI]), dict(teile=[FREI, FEST]), dict(teile=[]),
           dict(teile=[dict(FEST, werkstueck=1), dict(FREI, werkstueck=2), dict(FEST, werkstueck=3)],
                werkstuecke=[dict(nr=1), dict(nr=2), dict(nr=3)])]
assert rechnen.beladungen(stangen) == 6 and rechnen.beladungen_sn(stangen) == 3
ok("W1 Vorgaben 24/29 s je Maschine, Beladungen mit fester Naht gezählt (Werkstücke einzeln)")

# ------------------------------------------------------------------ W2 Kalkulation
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T03"))
# zwei Abmessungen = mindestens zwei Stangen; die feste Naht nur beim Rundrohr
for pos, profil, laenge, stueck in ((10, "QR 40x40x3", 2000, 4), (20, "RR 48,3x2,6", 1500, 3)):
    db.position_neu(a, dict(pos=pos, artikel=f"T{pos}", profil_id=profil, werkstoff_id="S235-10219",
                            laenge=laenge, stueck=stueck, schneidweg=320, einstiche=2))
s = fenster.angebot_oeffnen(a)
assert s.optimieren()


def rechnung():
    return rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)


z0, su0 = rechnung()
n = su0["beladungen"]
satz = next(z for z in su0["zeiten"] if z["schritt"] == "Stangenwechsel")["satz"]
assert su0["beladungen_sn"] == 0 and n >= 2
assert abs(su0["stangenwechsel_kosten"] - n * 24 / 3600 * satz) < EPS, su0["stangenwechsel_kosten"]

i_rr = next(i for i, p in enumerate(s.positionen) if p["profil_id"] == "RR 48,3x2,6")
db.position_aendern(s.positionen[i_rr]["id"], "naht_vorgabe", naht.FEST)
db.position_aendern(s.positionen[i_rr]["id"], "naht_winkel", 0)
s.neu_laden()
assert s.optimieren()
z1, su1 = rechnung()
rr = [st for st in s.ergebnis["stangen"] if st["profil"] == "RR 48,3x2,6"]
n_sn = rechnen.beladungen(rr)
assert su1["beladungen_sn"] == n_sn >= 1 and su1["beladungen"] == n, (su1["beladungen_sn"], n_sn)
erwartet = ((n - n_sn) * 24 + n_sn * 29) / 3600 * satz
assert abs(su1["stangenwechsel_kosten"] - erwartet) < EPS, (su1["stangenwechsel_kosten"], erwartet)
assert su1["stangenwechsel_s"] == (n - n_sn) * 24 + n_sn * 29
assert su1["verkauf"] > su0["verkauf"]
ok(f"W2 {n - n_sn} Stangen × 24 s + {n_sn} Stange(n) mit fester Naht × 29 s")

# ------------------------------------------------------------------ W3 Zeiten, Staffelanteil, Nachkalkulation
zs = next(z for z in su1["zeiten"] if z["schritt"] == "Stangenwechsel")
assert f"{n - n_sn} × 24 s + {n_sn} × 29 s (SN)" in zs["formel"], zs["formel"]
assert abs(zs["gesamt_min"] - su1["stangenwechsel_s"] / 60) < EPS and abs(zs["kosten"] - erwartet) < EPS
anteil = sum(z["stangenwechsel_teil"] * z["stueck"] for z in z1 if z)
assert abs(anteil - erwartet) < EPS
zb = s.kopf["zeitbasis"]
assert zb["maschine"]["stangenwechsel_sn"] == 29
vorgabe = rechnen.zeitbasis_aus("T03", s.k, s.tabellen)
assert rechnen.zeitbasis_abweichungen(dict(zb, maschine=dict(zb["maschine"], stangenwechsel_sn=35)), vorgabe) == \
    ["Stangenwechsel SN 35 statt 29 s"]
ok("W3 Zeiten-Reiter mit Aufteilung, Anteil je Teil = Summe, Snapshot-Abweichung SN")

# ------------------------------------------------------------------ W4 Snapshot vor 0.8.9
alt = dict(zb, maschine={n_: v for n_, v in zb["maschine"].items() if n_ != "stangenwechsel_sn"})
alt["maschine"]["stangenwechsel"] = 29
db.zeitbasis_speichern(a, alt)
s.neu_laden()
_, su2 = rechnung()
assert abs(su2["stangenwechsel_kosten"] - n * 29 / 3600 * satz) < EPS
assert rechnen.zeitbasis_abweichungen(alt, vorgabe) == ["Stangenwechsel 29 statt 24 s"]
ok("W4 altes Angebot (Snapshot ohne SN): alle Stangen mit dem gespeicherten Stangenwechsel, Preis unverändert")

# ------------------------------------------------------------------ W5 Schema 38
pfad = tmp / "alt" / "rohrlaser.db"
Datenbank(pfad).schliessen()
con = sqlite3.connect(pfad)
con.execute("UPDATE maschinen SET stangenwechsel=29, stangenwechsel_sn=NULL WHERE maschinen_id IN ('T03', 'T11')")
con.execute("UPDATE maschinen SET stangenwechsel=31, stangenwechsel_sn=NULL WHERE maschinen_id='T11'")
con.execute("UPDATE maschinen SET stangenwechsel=25, stangenwechsel_sn=NULL WHERE maschinen_id='LT7'")
con.execute("INSERT INTO maschinen (maschinen_id, stangenwechsel) VALUES ('EIGEN', 40)")
con.execute("PRAGMA user_version=37")
con.commit()
con.close()
d = Datenbank(pfad)
m = {z["maschinen_id"]: (z["stangenwechsel"], z["stangenwechsel_sn"]) for z in d.zeilen("maschinen")}
assert m == {"T03": (24, 29), "T11": (31, 31), "LT7": (24, 29), "EIGEN": (40, 40)}, m
assert d.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 38
assert len(list((pfad.parent / "Sicherung").glob("*vor_Schema_38*.db"))) == 1
d.schliessen()
ok("W5 Schema 38: unveränderte Beispielmaschinen 24/29 s, geänderte und eigene behalten ihren Wert (auch als SN)")
print("Alle Stangenwechsel-SN-Tests bestanden.")
