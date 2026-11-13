"""Schachtelvergleich in einer Tabelle (Plan X3, Patrick 12.11.2026 „Alle Empfehlungen (X1–X8)“).

Je Stangengruppe: 1 einfache Einteilung, 2 optimiert, 3 ohne gemeinsamen Schnitt (nur Vergleich), 4 andere
Lieferlängen, 5 Lager nur mit eingeschaltetem Lager. Stangen, Material kg und €, Verschnitt, Schnitte und Laserzeit
gespart, Einsparung gegenüber 1. Reiter „Schachtelvergleich“ im Fenster Varianten vergleichen.

Aufruf: python tests/test_schachtelvergleich.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import optimierung as opt, rechnen, schachtelvergleich as sv  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("laenge_vergleich", "ja")
db.neu("lieferlaengen", dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=12000))
fenster = Hauptfenster(db, tmp, stumm=True)
aid = db.angebot_neu(dict(kunde="Test", maschine="T11", stange=6000))
# 1.950 mm mit geraden Enden: 3 je Stange nur mit gemeinsamem Schnitt (3 × 1.950 + Schnitte knapp an 6 m)
db.position_neu(aid, dict(pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1300.0,
                          stueck=17, schneidweg=200, einstiche=1))
db.position_neu(aid, dict(pos=20, artikel="B", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=2900.0,
                          stueck=5, schneidweg=200, einstiche=1))
s = fenster.angebot_oeffnen(aid)
assert s.schachtel_vergleich() == []
assert s.optimieren()
gr = s.schachtel_vergleich()
g = next(x for x in gr if x["profil"] == "QR 40x40x3")
arten = [z["art"] for z in g["zeilen"]]
assert arten[:3] == [sv.EINFACH, sv.OPTIMIERT, sv.OHNE_GEM] and sv.LIEFER in arten and sv.LAGER not in arten, arten
e, o, ohne = g["zeilen"][:3]
a = next(x for x in s.ergebnis["auswertung"] if x["profil"] == "QR 40x40x3")
st = [x for x in s.ergebnis["stangen"] if x["profil"] == "QR 40x40x3" and x["stange"] == a["stange"]]
assert e["stangen"] == a["manuell"] and o["stangen"] == len(st) and o["stangen"] <= e["stangen"]
assert o["eingeplant"] == 22 and o["nicht"] == 0
assert o["schnitte"] == sum(x["gemeinsam"] for x in st) > 0
assert ohne["stangen"] >= o["stangen"] and ohne["schnitte"] == 0
assert abs(o["nutz_m"] - o["stangen"] * a["stange"] / 1000) < 1e-9
kgm = rechnen.kg_je_m("QR 40x40x3", "S235-10219", s.k)
assert abs(o["kg"] - o["nutz_m"] * kgm) < 1e-9
assert e["eur"] is not None and abs(o["ersparnis"] - (e["eur"] - o["eur"])) < 1e-9
z = s._rechnung()[0]
erwartet = sum(z[i]["einsparung"] * z[i]["stueck"] for i in (0, 1))
assert abs(o["laser_s"] - erwartet) < 1e-6 and o["laser_s"] > 0
ok(f"einfach {e['stangen']}, optimiert {o['stangen']}, ohne gemeinsamen Schnitt {ohne['stangen']} Stangen; "
   f"{o['schnitte']} Schnitte und {rechnen.zahl(o['laser_s'], 0)} s gespart, {rechnen.zahl(o['ersparnis'])} € ggü. einfach")

# ohne gemeinsamen Schnitt: Regel nur zwei gerade Enden, Gruppe ohne gerade Enden
grp = rechnen.gruppen_bilden(s.kopf, s.positionen, s.k, s.tabellen, s.einst)[0][0]
h = sv.ohne_gemeinsamen_schnitt(grp)
assert all(not t.a_gerade and not t.b_gerade for t in h.teile)
assert all(opt.gemeinsame_schnitte(f) == 0 for f in opt.optimiere(h))
ok("Vergleich ohne gemeinsamen Schnitt: keine geraden Enden, kein gemeinsamer Schnitt")

# Lager nur mit eingeschaltetem Lager
db.einstellung_setzen("lager_aktiv", "ja")
fenster.einstellungen_neu() if hasattr(fenster, "einstellungen_neu") else None
d = s.varianten_vergleichen(dialog=lambda d: None)
assert d.reiter.count() == 2 and d.reiter.tabText(1) == "Schachtelvergleich"
texte = [d.sv_tabelle.item(r, 0).text() for r in range(d.sv_tabelle.rowCount())]
assert any("einfache Einteilung" in t for t in texte) and any("ohne gemeinsamen Schnitt" in t for t in texte), texte
ok("Reiter Schachtelvergleich im Fenster Varianten vergleichen")
print("Schachtelvergleich stimmt.")
