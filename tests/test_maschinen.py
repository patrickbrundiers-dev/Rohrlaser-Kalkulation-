"""Maschinen T03 (Trumpf CO₂), T11 (Trumpf Faser), LT7 (Adige Faser), Schneiddaten-Richtwerte, Plausibilität,
Umbenennen mit Angeboten und Anpassung von Dateien bis 0.5.8.

Aufruf: python tests/test_maschinen.py
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import (ALTE_VORSCHUB, TABELLE, beispiel_schneiddaten, pruefen)  # noqa: E402

tmp = Path(tempfile.mkdtemp())

# 1) Neue Datei: Maschinen laut Patrick, Standard T03, Schneiddaten ohne Prüfmeldung
db = Datenbank(tmp / "a" / "rohrlaser.db")
k, tab = db.kontext(), db.tabellen()
assert sorted(k.maschinen) == ["LT7", "T03", "T11"], k.maschinen
t03, t11, lt7 = k.maschinen["T03"], k.maschinen["T11"], k.maschinen["LT7"]
for m in (t03, t11, lt7):
    assert (m["endbeschnitt"], m["schnittverlust"], m["max_stange"], m["stundensatz"], m["kontur_klein"],
            m["kontur_mittel"], m["abstand"], m["ruestzeit"]) == (10, 0.2, 6500, 150, 10, 50, 5, 5), m
assert (t03["greiferrest"], t03["stangenwechsel"], t03["max_huellkreis"], t03["max_kg_m"]) == (142, 29, 255, 36)
assert (t11["greiferrest"], t11["stangenwechsel"], t11["max_huellkreis"], t11["max_kg_m"]) == (142, 29, 255, 36)
assert (lt7["greiferrest"], lt7["stangenwechsel"], lt7["max_huellkreis"], lt7["max_kg_m"]) == (120, 25, 214, 23)
assert t03["bezeichnung"] == "Trumpf" and lt7["bezeichnung"] == "Adige" and "CO₂" in t03["bemerkung"]
assert db.einstellung("standard_maschine") == "T03"
for t in ("maschinen", "schneiddaten"):
    for z in db.zeilen(t):
        assert pruefen(TABELLE[t], z, k) == "OK", (t, z, pruefen(TABELLE[t], z, k))

sd = lambda m, w, s: rechnen.schneiddaten(m, w, s, tab, rechnen.kategorie(w, k))
# Faser: Stahl N₂ bis 4 mm, darüber O₂; CO₂: Stahl N₂ bis 2 mm; Edelstahl/Alu nur N₂
assert (sd("T11", "S235-10219", 4)["gas"], sd("T11", "S235-10219", 4.5)["gas"]) == ("N₂", "O₂")
assert (sd("T03", "S235-10219", 2)["gas"], sd("T03", "S235-10219", 2.5)["gas"]) == ("N₂", "O₂")
assert sd("T11", "1.4301", 10)["gas"] == "N₂" and sd("T11", "1.4301", 11) is None
assert sd("T03", "AW6060-T66", 6)["gas"] == "N₂" and sd("T03", "AW6060-T66", 7) is None
assert sd("T11", "AW6060-T66", 8)["gas"] == "N₂"
# CO₂ dünn langsamer als Faser, dick ähnlich; LT7 = T11
assert sd("T03", "S235-10219", 2)["vorschub_gross"] < sd("T11", "S235-10219", 2)["vorschub_gross"] / 1.5
assert sd("T03", "S235-10219", 10)["vorschub_gross"] >= 0.9 * sd("LT7", "S235-10219", 10)["vorschub_gross"]
# T11 mit 4 kW: 20 % mehr Vorschub als LT7 mit 3 kW
assert sd("LT7", "1.4301", 3)["vorschub_gross"] == 4200 and sd("T11", "1.4301", 3)["vorschub_gross"] == 5040
z = sd("LT7", "S235-10219", 3)
assert (z["vorschub_mittel"], z["vorschub_klein"], z["vorschub_gravur"]) == (3000, 1500, 3000), z   # Gravur 3.000 mm/min (Patrick, 21.10.2026)
assert "4 kW" in sd("T11", "S235-10219", 3)["bemerkung"] and "3,2 kW" in sd("T03", "S235-10219", 3)["bemerkung"]
assert sd("T03", "S235-10219", 3)["einstechzeit"] > sd("T11", "S235-10219", 3)["einstechzeit"]
assert sd("T11", "S235-10219", 12)["vorschub_gross"] == 1080 and sd("T11", "S235-10219", 13) is None
assert all(z["bemerkung"].startswith("Beispiel: Richtwert") for z in db.zeilen("schneiddaten"))

# 2) Plausibilität in der Prüfspalte
pz = lambda z: pruefen(TABELLE["schneiddaten"], z, db.kontext())
i = db.neu("schneiddaten", dict(maschinen_id="T11", kategorie="Stahl", gas="N₂", wand_bis=2.5, vorschub_gross=12000))
z = next(z for z in db.zeilen("schneiddaten") if z["id"] == i)
assert pz(z) == "WARNUNG: Vorschub höher als bei 2 mm", pz(z)
db.aendern("schneiddaten", i, "vorschub_gross", 6000)
db.aendern("schneiddaten", i, "vorschub_klein", 7000)
z = next(z for z in db.zeilen("schneiddaten") if z["id"] == i)
assert pz(z) == "WARNUNG: Vorschub klein größer als groß", pz(z)
db.loeschen("schneiddaten", [i])
db.neu("maschinen", dict(maschinen_id="X1", bezeichnung="ohne Daten", stundensatz=100))
km = db.kontext()
pm = lambda mid: pruefen(TABELLE["maschinen"], km.maschinen[mid], km)
assert pm("X1") == "WARNUNG: keine Schneiddaten" and pm("T11") == "OK"
db.neu("schneiddaten", dict(maschinen_id="X1", kategorie="Stahl", gas="N₂", wand_bis=2, vorschub_gross=5000))
km = db.kontext()
assert pm("X1") == "WARNUNG: keine Schneiddaten für Edelstahl, Aluminium", pm("X1")

# 3) Umbenennen: Angebote (Kopf und Snapshots) und Standard-Maschine ziehen mit
a = db.angebot_neu(dict(maschine="T11"))
ang = db.angebot(a)
assert ang["maschine"] == "T11" and ang["zeitbasis"]["maschine"]["maschinen_id"] == "T11"
db.preisbasis_speichern(a, dict(datum="2026-10-20", maschine="T11", preise=[], tonnenpreise={}, aufpreise={},
                                schneiddaten=[dict(maschinen_id="T11", kategorie="Stahl", gas="N₂", wand_bis=2,
                                                   vorschub_gross=8000)]))
db.einstellung_setzen("standard_maschine", "T11")
mid = next(z["id"] for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
assert db.verweise("maschinen", mid) > 1
db.aendern("maschinen", mid, "maschinen_id", "T11-neu")
ang = db.angebot(a)
assert ang["maschine"] == "T11-neu" and ang["zeitbasis"]["maschine"]["maschinen_id"] == "T11-neu"
assert ang["preisbasis"]["maschine"] == "T11-neu" and ang["preisbasis"]["schneiddaten"][0]["maschinen_id"] == "T11-neu"
assert db.einstellung("standard_maschine") == "T11-neu"
assert {z["maschinen_id"] for z in db.zeilen("schneiddaten")} == {"T03", "T11-neu", "LT7", "X1"}
db.schliessen()


# 4) Datei bis 0.5.8: Beispielmaschinen RL-1/RL-2 und alte Beispiel-Schneiddaten
ALT = [("RL-1", "Rohrlaser 1 (Beispiel)", 20, 80, 0.3, 6500, 120.00, 10, 50, 2, 15, 30, "Beispielwerte"),
       ("RL-2", "Rohrlaser 2 (Beispiel)", 15, 120, 0.3, 8500, 140.00, 10, 50, 2, 20, 40, "Beispielwerte")]


def alte_datei(pfad, umbenannt=False, eigene=False):
    """Datei wie aus 0.5.8: Maschinen RL-1/RL-2, alte Beispiel-Schneiddaten, ein Angebot auf RL-1.
    umbenannt: RL-1/RL-2 von Hand zu T03/T11 umbenannt (wie in Patricks Screenshot), LT7 von Hand ohne Schneiddaten.
    eigene: RL-1 mit eigenem Stundensatz und einer geänderten Schneiddaten-Zeile."""
    d = Datenbank(pfad)
    a = d.angebot_neu(dict(maschine="T03", nummer="ALT-1"))
    d.schliessen()
    con = sqlite3.connect(pfad)
    con.execute("DELETE FROM maschinen")
    con.execute("DELETE FROM schneiddaten")
    sp = "maschinen_id, bezeichnung, endbeschnitt, greiferrest, schnittverlust, max_stange, stundensatz, " \
         "kontur_klein, kontur_mittel, abstand, ruestzeit, stangenwechsel, bemerkung"
    con.executemany(f"INSERT INTO maschinen ({sp}) VALUES ({', '.join('?' * 13)})", ALT)
    for m, f in (("RL-1", 1.0), ("RL-2", 1.2)):
        for (kat, gas), stufen in ALTE_VORSCHUB.items():
            for wand, v in stufen:
                v = round(v * f, -1)
                ein = round(0.1 + wand * (0.18 if gas == "O₂" else 0.12), 1)
                con.execute("INSERT INTO schneiddaten (maschinen_id, kategorie, gas, wand_bis, vorschub_gross, "
                            "vorschub_mittel, vorschub_klein, einstechzeit, vorschub_gravur, bemerkung) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Beispiel')",
                            (m, kat, gas, wand, v, round(v * 0.7, -1), round(v * 0.4, -1), ein,
                             12000 if gas == "N₂" else 10000))
    zb = dict(maschine=dict(maschinen_id="RL-1", stundensatz=120.0, ruestzeit=15, stangenwechsel=30), saetze={},
              schritte=[])
    pb = dict(datum="2026-10-10", maschine="RL-1", preise=[], tonnenpreise={}, aufpreise={},
              schneiddaten=[dict(maschinen_id="RL-1", kategorie="Stahl", gas="N₂", wand_bis=2, vorschub_gross=7000)])
    con.execute("UPDATE angebote SET maschine='RL-1', zeitbasis=?, preisbasis=? WHERE id=?",
                (json.dumps(zb), json.dumps(pb), a))
    con.execute("INSERT OR REPLACE INTO einstellungen (name, wert) VALUES ('standard_maschine', '\"RL-1\"')")
    con.execute("DELETE FROM einstellungen WHERE name='maschinen_stand'")
    if eigene:
        con.execute("UPDATE maschinen SET stundensatz=135 WHERE maschinen_id='RL-1'")
        con.execute("UPDATE schneiddaten SET vorschub_gross=4444 WHERE maschinen_id='RL-1' AND kategorie='Stahl' "
                    "AND gas='N₂' AND wand_bis=3")
    if umbenannt:     # von Hand: Maschinen und Schneiddaten umbenannt, Angebote und Standard-Maschine nicht
        con.execute("UPDATE maschinen SET maschinen_id='T03', bezeichnung='Trumpf', endbeschnitt=10, greiferrest=142, "
                    "schnittverlust=0.2, max_stange=6500, stundensatz=150, abstand=5, ruestzeit=5, stangenwechsel=29, "
                    "max_huellkreis=255, max_kg_m=36 WHERE maschinen_id='RL-1'")
        con.execute("UPDATE maschinen SET maschinen_id='T11', bezeichnung='Trumpf', endbeschnitt=10, greiferrest=142, "
                    "schnittverlust=0.2, max_stange=6500, stundensatz=150, abstand=5, ruestzeit=5, stangenwechsel=29, "
                    "max_huellkreis=255, max_kg_m=36 WHERE maschinen_id='RL-2'")
        con.execute(f"INSERT INTO maschinen ({sp}, max_huellkreis, max_kg_m) VALUES "
                    "('LT7', 'Adige', 10, 120, 0.2, 6500, 150, 10, 50, 5, 5, 25, NULL, 214, 23)")
        con.execute("UPDATE schneiddaten SET maschinen_id='T03' WHERE maschinen_id='RL-1'")
        con.execute("UPDATE schneiddaten SET maschinen_id='T11' WHERE maschinen_id='RL-2'")
    con.commit()
    con.close()
    return a


def pruefe_neu(d, a):
    """Nach der Anpassung: T03/T11/LT7 mit neuen Schneiddaten, Angebot und Snapshots auf T03."""
    ang = d.angebot(a)
    assert ang["maschine"] == "T03", ang["maschine"]
    assert ang["zeitbasis"]["maschine"] == dict(maschinen_id="T03", stundensatz=120.0, ruestzeit=15, stangenwechsel=30)
    assert ang["preisbasis"]["maschine"] == "T03" and ang["preisbasis"]["schneiddaten"][0]["vorschub_gross"] == 7000
    assert d.einstellung("standard_maschine") == "T03" and d.einstellung("maschinen_stand") == "2026-10-20"
    assert len(list((d.pfad.parent / "Sicherung").glob("*vor_Maschinen*.db"))) == 1


# a) unverändert: RL-1 -> T03, RL-2 -> T11 mit Patricks Werten, LT7 neu, Schneiddaten = neue Richtwerte
p = tmp / "b" / "rohrlaser.db"
a = alte_datei(p)
d = Datenbank(p)
k = d.kontext()
assert sorted(k.maschinen) == ["LT7", "T03", "T11"], sorted(k.maschinen)
assert (k.maschinen["T03"]["greiferrest"], k.maschinen["T03"]["stundensatz"], k.maschinen["T11"]["max_stange"]) \
    == (142, 150, 6500)
neu = sorted(json.dumps(z[:10]) for z in beispiel_schneiddaten())
ist = sorted(json.dumps([z[n] for n in ("maschinen_id", "werkstoff_id", "kategorie", "gas", "wand_bis",
                                         "vorschub_gross", "vorschub_mittel", "vorschub_klein", "einstechzeit",
                                         "vorschub_gravur")]) for z in d.zeilen("schneiddaten"))
assert [json.loads(x) for x in ist] == [json.loads(x) for x in neu]
pruefe_neu(d, a)
d.schliessen()
d = Datenbank(p)     # zweites Öffnen ändert nichts mehr
assert d.anzahl("schneiddaten") == len(beispiel_schneiddaten()) and d.anzahl("maschinen") == 3
d.schliessen()

# b) von Hand umbenannt (Screenshot): Angebote ziehen nach, LT7 bekommt Schneiddaten, eigene Werte bleiben
p = tmp / "c" / "rohrlaser.db"
a = alte_datei(p, umbenannt=True)
con = sqlite3.connect(p)
con.execute("UPDATE maschinen SET stundensatz=155 WHERE maschinen_id='LT7'")
con.commit()
con.close()
d = Datenbank(p)
k, tb = d.kontext(), d.tabellen()
assert sorted(k.maschinen) == ["LT7", "T03", "T11"] and k.maschinen["LT7"]["stundensatz"] == 155
assert d.anzahl("schneiddaten") == len(beispiel_schneiddaten())
assert rechnen.schneiddaten("LT7", "S235-10219", 3, tb, "Stahl")["vorschub_gross"] == 5000
assert rechnen.schneiddaten("T03", "S235-10219", 3, tb, "Stahl")["gas"] == "O₂"
pruefe_neu(d, a)
d.schliessen()

# c) eigene Werte: RL-1 mit eigenem Stundensatz bleibt RL-1; geänderte Schneiddaten-Zeile bleibt
p = tmp / "d" / "rohrlaser.db"
a = alte_datei(p, eigene=True)
d = Datenbank(p)
k, tb = d.kontext(), d.tabellen()
assert sorted(k.maschinen) == ["LT7", "RL-1", "T03", "T11"] and k.maschinen["RL-1"]["stundensatz"] == 135
assert k.maschinen["T03"]["greiferrest"] == 142 and d.angebot(a)["maschine"] == "RL-1"
assert d.einstellung("standard_maschine") == "RL-1"
rl1 = [z for z in d.zeilen("schneiddaten") if z["maschinen_id"] == "RL-1"]
assert len(rl1) == 1 and rl1[0]["vorschub_gross"] == 4444
d.schliessen()

# d) Schneiddaten auf Standard zurücksetzen: eine Maschine bzw. alle mit Richtwerten, eigene Maschine bleibt
d = Datenbank(p)
t11 = [z for z in d.zeilen("schneiddaten") if z["maschinen_id"] == "T11"]
d.aendern("schneiddaten", t11[0]["id"], "vorschub_gross", 1)
d.neu("schneiddaten", {"maschinen_id": "T11", "werkstoff_id": "S235-10219", "gas": "N₂", "wand_bis": 2,
                       "vorschub_gross": 999})
lt7 = [z for z in d.zeilen("schneiddaten") if z["maschinen_id"] == "LT7"]
d.aendern("schneiddaten", lt7[0]["id"], "vorschub_gross", 2)
weg, neu = d.schneiddaten_zuruecksetzen(["T11"])
std = [z for z in beispiel_schneiddaten() if z[0] == "T11"]
assert (weg, neu) == (len(t11) + 1, len(std)), (weg, neu)
werte = lambda m: sorted((z["kategorie"], z["gas"], z["wand_bis"], z["vorschub_gross"], z["vorschub_mittel"],
                          z["vorschub_klein"], z["einstechzeit"], z["vorschub_gravur"], z["bemerkung"])
                         for z in d.zeilen("schneiddaten") if z["maschinen_id"] == m)
assert werte("T11") == sorted(z[2:] for z in std)
assert 2 in [z[3] for z in werte("LT7")]                       # LT7 nicht angefasst
assert d.einstellung("stammdaten_herkunft") == "eigene Werte"
weg, neu = d.schneiddaten_zuruecksetzen()
assert neu == len(beispiel_schneiddaten()) and 2 not in [z[3] for z in werte("LT7")]
rl1 = [z for z in d.zeilen("schneiddaten") if z["maschinen_id"] == "RL-1"]
assert len(rl1) == 1 and rl1[0]["vorschub_gross"] == 4444     # eigene Maschine ohne Richtwerte bleibt
assert d.schneiddaten_zuruecksetzen(["RL-1"]) == (0, 0)
d.schliessen()

# e) Datei mit Richtwerten bis 0.6.3: Gravur 15.000/10.000 wird einmalig 3.000, von Hand geänderte bleibt
p = tmp / "e" / "rohrlaser.db"
d = Datenbank(p)
d.schliessen()
con = sqlite3.connect(p)
con.execute("UPDATE schneiddaten SET vorschub_gravur=CASE WHEN maschinen_id='T03' THEN 10000 ELSE 15000 END")
con.execute("UPDATE schneiddaten SET vorschub_gravur=4444 WHERE id=(SELECT MIN(id) FROM schneiddaten)")
con.execute("DELETE FROM einstellungen WHERE name='gravur_stand'")
con.commit()
con.close()
d = Datenbank(p)
gr = [z["vorschub_gravur"] for z in d.zeilen("schneiddaten")]
assert gr[0] == 4444 and set(gr[1:]) == {3000}, set(gr)
assert d.einstellung("gravur_stand") == "2026-10-21"
d.schliessen()

print("OK: Maschinen und Schneiddaten")
