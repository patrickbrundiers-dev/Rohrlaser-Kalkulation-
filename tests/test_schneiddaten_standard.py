"""Schneiddaten auf Standard zurücksetzen (Patrick 29.10.2026): Vorschau (schneiddaten_standard.vergleich), Umfang
alle / eine Maschine / markierte Zeilen, eigene Zeilen behalten, Sicherung vorher, Markierung abweichender Zellen.

Aufruf: python tests/test_schneiddaten_standard.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import schneiddaten_standard as ss  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import FARBE_ABWEICHUNG, StammdatenSeite  # noqa: E402
from rohrlaser.stammdaten import SCHNEIDDATEN, beispiel_schneiddaten  # noqa: E402


def ok(text):
    print("OK  ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
n_std = len(beispiel_schneiddaten())
n_t11 = sum(1 for z in beispiel_schneiddaten() if z[0] == "T11")

# 1) Neue Datei: alles Standard, nichts zu tun
v = ss.vergleich(db.zeilen("schneiddaten"))
assert (len(v["aendern"]), len(v["entfernen"]), len(v["ergaenzen"]), v["gleich"]) == (0, 0, 0, n_std), v
assert db.schneiddaten_standard_setzen() == dict(geaendert=0, weg=0, neu=0, pfad=None)
assert not list((tmp / "Sicherung").glob("*vor_Schneiddaten_Standard*"))
ok("Neue Datei: alle Zeilen Standard, Zurücksetzen ändert nichts und legt keine Sicherung an")

# 2) Eigene Werte: T11 geändert, werkstoffgenaue Zeile, LT7 geändert, eine T11-Standardzeile gelöscht
zeilen = db.zeilen("schneiddaten")
t11 = [z for z in zeilen if z["maschinen_id"] == "T11"]
lt7 = [z for z in zeilen if z["maschinen_id"] == "LT7"]
db.aendern("schneiddaten", t11[0]["id"], "vorschub_gross", 1234)
db.aendern("schneiddaten", t11[1]["id"], "zeit_ecke", 0.4)
db.loeschen("schneiddaten", [t11[2]["id"]])
db.neu("schneiddaten", {"maschinen_id": "T11", "werkstoff_id": "S235-10219", "gas": "N₂", "wand_bis": 2,
                        "vorschub_gross": 999})
db.aendern("schneiddaten", lt7[0]["id"], "vorschub_gross", 2)
v = ss.vergleich(db.zeilen("schneiddaten"), ["T11"])
assert v["maschinen"] == ["T11"]
assert [(z["id"], ab) for z, ab, _ in v["aendern"]] == [
    (t11[0]["id"], {"vorschub_gross": (1234, t11[0]["vorschub_gross"])}), (t11[1]["id"], {"zeit_ecke": (0.4, t11[1]["zeit_ecke"])})]
assert [z["werkstoff_id"] for z in v["entfernen"]] == ["S235-10219"]
assert [ss.schluessel(s) for s in v["ergaenzen"]] == [ss.schluessel(t11[2])]
assert v["gleich"] == n_t11 - 3
assert "2 Zeile(n) bekommen Standardwerte, 1 eigene Zeile(n) werden entfernt, 1 fehlende" in ss.zusammenfassung(v)
vz = ss.vorschau_zeilen(v)
assert vz[0] == (ss.zeile_text(t11[0]), "Vorschub groß / Trennschnitt [mm/min]", "1.234",
                 ss.wert_text(t11[0]["vorschub_gross"])), vz[0]
assert ("eigene Zeile", "vorhanden", "wird entfernt") in [r[1:] for r in vz]
assert ("Standardzeile", "fehlt", "wird ergänzt") in [r[1:] for r in vz]
ok("Vorschau: geänderte Werte (jetzt → Standard), eigene Zeile entfernt, fehlende Standardzeile ergänzt")

v2 = ss.vergleich(db.zeilen("schneiddaten"), ["T11"], eigene_behalten=True)
assert not v2["entfernen"] and [z["werkstoff_id"] for z in v2["ohne_standard"]] == ["S235-10219"]
v3 = ss.vergleich(db.zeilen("schneiddaten"), ids=[t11[0]["id"], lt7[0]["id"]])
assert v3["maschinen"] == ["LT7", "T11"] and len(v3["aendern"]) == 2 and not v3["ergaenzen"] and not v3["entfernen"]
assert ss.vergleich(db.zeilen("schneiddaten"), ["RL-9"])["maschinen"] == []
ok("Umfang: eigene Zeilen behalten, nur markierte Zeilen (nichts entfernt/ergänzt), Maschine ohne Richtwerte")

# 3) Modell markiert abweichende Zellen (orange, Tooltip mit Standard)
meldungen = []
seite = StammdatenSeite(db, SCHNEIDDATEN, lambda text, fehler=False: meldungen.append(text))
m = seite.modell
r = next(i for i, z in enumerate(m.daten) if z["id"] == t11[0]["id"])
sp = next(i for i, (art, f) in enumerate(m.spalten) if art == "feld" and f.name == "vorschub_gross")
sp_wand = next(i for i, (art, f) in enumerate(m.spalten) if art == "feld" and f.name == "wand_bis")
assert m.data(m.index(r, sp), Qt.ItemDataRole.BackgroundRole).color() == FARBE_ABWEICHUNG
assert "Standard:" in m.data(m.index(r, sp), Qt.ItemDataRole.ToolTipRole)
assert m.data(m.index(r, sp_wand), Qt.ItemDataRole.BackgroundRole).color() != FARBE_ABWEICHUNG
r_ok = next(i for i, z in enumerate(m.daten) if z["id"] == t11[3]["id"])
assert m.data(m.index(r_ok, sp), Qt.ItemDataRole.BackgroundRole).color() != FARBE_ABWEICHUNG
ok("Tabelle: Zelle mit eigenem Wert orange, Tooltip nennt den Standard; Standardwerte und Schlüssel unmarkiert")

# 4) Dialog: Vorwahl markierte Zeilen, Wechsel auf eine Maschine, Bestätigen (stumm)
d = ss.StandardDialog(None, m.daten, [t11[0]["id"]], stumm=True)
assert d.nur_markiert.isChecked() and d.umfang() == dict(maschinen=None, ids=[t11[0]["id"]], eigene_behalten=True)
assert not d.behalten.isEnabled() and d.tabelle.rowCount() == 1
d.maschine.setCurrentIndex(list(ss.LASER).index("T11"))
assert d.eine.isChecked() and d.umfang()["maschinen"] == ["T11"] and d.behalten.isEnabled()
assert d.tabelle.rowCount() == 4 and d.ok.isEnabled()
assert "T11" in d.bestaetigung_text() and "Datensicherung" in d.bestaetigung_text()
d._ok()
assert d.wahl == dict(maschinen=["T11"], ids=None, eigene_behalten=False)
leer = ss.StandardDialog(None, [z for z in m.daten if z["maschinen_id"] != "T11"] + [], [], stumm=True)
leer.eine.setChecked(True)
leer.maschine.setCurrentIndex(list(ss.LASER).index("T03"))
assert not leer.nur_markiert.isEnabled() and not leer.ok.isEnabled()
ok("Dialog: Umfang wählbar, Vorschau je Umfang, Knopf nur bei Änderungen, Rückfrage nennt Sicherung")

# 5) Zurücksetzen über die Seite: nur markierte Zeile, dann T11 ganz, Sicherung vorher, LT7 bleibt
r1 = seite.schneiddaten_zuruecksetzen(dict(maschinen=None, ids=[t11[0]["id"]], eigene_behalten=True))
assert (r1["geaendert"], r1["weg"], r1["neu"]) == (1, 0, 0) and Path(r1["pfad"]).is_file()
assert "vor_Schneiddaten_Standard" in Path(r1["pfad"]).name and "Sicherung" in meldungen[-1]
neu = {z["id"]: z for z in db.zeilen("schneiddaten")}
assert neu[t11[0]["id"]]["vorschub_gross"] == t11[0]["vorschub_gross"] and neu[t11[1]["id"]]["zeit_ecke"] == 0.4
r2 = seite.schneiddaten_zuruecksetzen(d.wahl)
assert (r2["geaendert"], r2["weg"], r2["neu"]) == (1, 1, 1), r2
assert ss.vergleich(db.zeilen("schneiddaten"), ["T11"])["gleich"] == n_t11
assert t11[1]["id"] in {z["id"] for z in db.zeilen("schneiddaten")}          # Zeile bleibt, nur Werte neu
assert 2 in [z["vorschub_gross"] for z in db.zeilen("schneiddaten") if z["maschinen_id"] == "LT7"]
assert db.einstellung("stammdaten_herkunft") == "eigene Werte"
from rohrlaser.sicherung_dialog import art_text  # noqa: E402
assert art_text(r2["pfad"]) == "vor Schneiddaten-Standard"
r3 = db.schneiddaten_standard_setzen(sichern=False)
assert (r3["geaendert"], r3["weg"], r3["neu"], r3["pfad"]) == (1, 0, 0, None)
assert ss.vergleich(db.zeilen("schneiddaten"))["gleich"] == n_std
ok("Zurücksetzen: markierte Zeile, dann Maschine T11 (geändert/entfernt/ergänzt), Sicherung 'vor Schneiddaten-"
   "Standard', danach alle Maschinen")
db.schliessen()

# 6) Zeit je Ecke nach Wandstärke (S2): Standard und einmalige Anpassung älterer Dateien
from rohrlaser import rechnen, schneidweg  # noqa: E402
from rohrlaser.stammdaten import zeit_ecke  # noqa: E402
assert (zeit_ecke(1), zeit_ecke(3), zeit_ecke(8), zeit_ecke(12)) == (0.25, 0.35, 0.6, 0.8)
assert all(z[11] == zeit_ecke(z[4]) for z in beispiel_schneiddaten())
p2 = tmp / "alt" / "rohrlaser.db"
db = Datenbank(p2)
eigen = db.neu("schneiddaten", {"maschinen_id": "T11", "werkstoff_id": "S235-10219", "gas": "N₂", "wand_bis": 3,
                                "vorschub_gross": 5000})
db.con.execute("UPDATE schneiddaten SET zeit_ecke=NULL")
db.con.execute("UPDATE schneiddaten SET zeit_ecke=0.9 WHERE maschinen_id='LT7' AND wand_bis=3 AND kategorie='Stahl'")
db.con.execute("DELETE FROM einstellungen WHERE name='ecke_stand'")
db.con.commit()
db.schliessen()
db = Datenbank(p2)
z = db.zeilen("schneiddaten")
assert all(x["zeit_ecke"] == zeit_ecke(x["wand_bis"]) for x in z if not x["werkstoff_id"] and
           not (x["maschinen_id"] == "LT7" and x["wand_bis"] == 3 and x["kategorie"] == "Stahl"))
assert [x["zeit_ecke"] for x in z if x["maschinen_id"] == "LT7" and x["wand_bis"] == 3 and x["kategorie"] == "Stahl"] \
    == [0.9]
assert [x["zeit_ecke"] for x in z if x["werkstoff_id"] == "S235-10219"] == [None]
ok("Zeit je Ecke: 0,2 s + 0,05 s je mm; ältere Datei einmalig gefüllt, eigene Werte und Zeilen bleiben")

# 7) Enden nach Hüllmaß auch im Schneidweg-Rechner (S1), Innenkonturen ohne Enden, Anfahrzeit (S3)
db.loeschen("schneiddaten", [x["id"] for x in db.zeilen("schneiddaten") if x["werkstoff_id"]])
k, tab = db.kontext(), db.tabellen()
kopf = dict(maschine="T11", stange=6000)
m = rechnen.maschine(kopf, k)
pr = dict(k.profile["QR 40x40x3"], profil_id="QR 40x40x3")
r = schneidweg.rechnen(dict(a={}, b={}, konturen=[dict(art="Bohrung", d=10, anzahl=8)]), pr, rechnen.kontur_regel(m, 3))
f = r["felder"]
assert (f["klein_n"], f["mittel_n"], f["gross_n"]) == (8, 2, 0) and f["mittel_mm"] == f["a_schnitt"] + f["b_schnitt"]
pos = dict(f, pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10)
assert rechnen.konturen_anzahl(pos) == 8 and rechnen.konturen_anzahl(dict(klein_n=3, gross_n=1)) == 4
assert rechnen.konturklassen_neu(pos, m, 3) is None          # gleiche Einteilung wie beim Neu-Einteilen
assert rechnen.ende_vorschub(pos, (5800, 3480, 1740), rechnen.kontur_regel(m, 3)) == 3480


def kalk(pos, kopf=kopf, k=k, tab=tab):
    erg = rechnen.optimieren(kopf, [pos], k)
    return rechnen.kalkulation(kopf, [pos], erg, k, tab, db.einstellungen())[0][0]


z0 = kalk(pos)
ende = 60 * f["a_schnitt"] / 3480                              # ein gerades Ende mit Vorschub mittel
assert abs(z0["zeit_mittel"] - 2 * ende) < 1e-6 and z0["zeit_anfahren"] == 0
assert abs(z0["zeit_ecken"] - 2 * 4 * zeit_ecke(3)) < 1e-9
gem = sum(t["eingespart_e"] for st in rechnen.optimieren(kopf, [pos], k)["stangen"] for t in st["teile"])
assert gem == 9 and abs(z0["einsparung"] - gem * (ende + 0.3 + 4 * zeit_ecke(3)) / 10) < 1e-6, z0["einsparung"]
assert z0["laser_netto"] > 0
for x in db.zeilen("maschinen"):
    db.aendern("maschinen", x["id"], "zeit_kontur", 0.5)
k1 = db.kontext()
z1 = kalk(pos, k=k1)
assert abs(z1["zeit_anfahren"] - 10 * 0.5) < 1e-9 and abs(z1["laser_brutto"] - z0["laser_brutto"] - 5) < 1e-9
assert abs(z1["einsparung"] - z0["einsparung"] - gem * 0.5 / 10) < 1e-9
ok("Rechner: Enden QR 40 mittel wie STEP, Einsparung = angesetzte Zeit des Endes; Anfahren je Einstich, gemeinsamer "
   "Schnitt spart es mit")

# 8) Festgeschriebene Angebote vor 0.9.195: ohne Eckzeit und ohne Anfahrzeit, keine Meldung 'geändert'
pb = rechnen.preisbasis_aus(kopf, [pos], k, tab)
assert all("zeit_ecke" in x for x in pb["schneiddaten"])
alt = dict(pb, schneiddaten=[{n: v for n, v in x.items() if n != "zeit_ecke"} for x in pb["schneiddaten"]],
           maschinen={mid: {n: v for n, v in x.items() if n != "zeit_kontur"} for mid, x in pb["maschinen"].items()})
kf = dict(kopf, preisbasis=alt)
assert rechnen.preisbasis_abweichung(dict(kopf, preisbasis=dict(alt, maschinen={
    mid: {n: v for n, v in x.items() if n != "zeit_kontur"} for mid, x in rechnen.preisbasis_aus(
        kopf, [pos], k, tab)["maschinen"].items()})), k, tab) == []
kfest, tfest = rechnen.preisbasis_anwenden(kf, k1, db.tabellen())
zf = kalk(pos, kopf=kf, k=kfest, tab=tfest)
assert zf["zeit_ecken"] == 0 and zf["zeit_anfahren"] == 0, (zf["zeit_ecken"], zf["zeit_anfahren"])
kneu, tneu = rechnen.preisbasis_anwenden(dict(kopf, preisbasis=pb), k1, db.tabellen())
zn = kalk(pos, kopf=kopf, k=kneu, tab=tneu)
assert zn["zeit_ecken"] > 0 and zn["zeit_anfahren"] == 0      # festgeschrieben mit Ecke, Anfahren damals leer
ok("Festgeschriebene Angebote: alte ohne Eckzeit/Anfahren, neue mit ihrem Stand; keine Meldung für neue Felder")
db.schliessen()
print("Alle Tests bestanden.")
