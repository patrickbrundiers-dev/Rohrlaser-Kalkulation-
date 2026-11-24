"""Prüft das Einlesen von TRUMPF-Rohrprogrammen (Patrick 20.11.2026, trumpf_programm.py):
- T1 LST eines Programms: Profil, Werkstoff St37, Teillänge, Schneidweg (Cutting length), Einstiche (TC_LASER_ON
  nach TC_LASER_OFF), TRUMPF-Zeit je Teil (Anschnitt + Konturen + Abschnitt)
- T2 Job-Liste mit zwei Programmen: Fertigungsauftrag als Artikel, Sollanzahl als Stückzahl, Programmname
- T3 TUBX (ZIP mit app.xml und Workpiece-BSON): Profil aus Profil-ID, Länge, Gewicht; ohne LST Hinweis, mit
  gleichnamiger LST daneben deren Schneidweg/Einstiche/Zeit
- T4 Fehler: keine LST, keine TUBX, beschädigt
- T5 Angebot: Neue Position „Aus TRUMPF-Programm“ legt je Teil eine Position an (Profil der Stammdaten, Werkstoff,
  Schneidzeit je Teil nach Einstellung trumpf_zeit), unbekanntes Profil mit Hinweis, Rückgängig
- T6 Laser-an-Zeit aus CONSUMPTION_TIMES: ja = reine Laserzeit (Rest berechnet), ganz = ganze TRUMPF-Zeit von Hand
Synthetische Dateien im Aufbau der echten (keine Kundendaten im Repo).

Aufruf: python tests/test_trumpf_programm.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import io
import os
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import trumpf_programm as tp  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def mm(namen):
    return "\n".join(f"MM,AT,1,{10 * (i + 1):4d},1,1,,'{n}',,'',T" for i, n in enumerate(namen))


def abschnitt(name, namen, zeilen):
    da = []
    for z in zeilen:
        werte = ",".join(f"'{w}'" if isinstance(w, str) else str(w) for w in z)
        # lange Zeilen wie TRUMPF mit „*“-Folgezeile
        da.append("DA," + werte[:40] + ("\n*  " + werte[40:] if len(werte) > 40 else ""))
    return f"BEGIN_{name}\nC\nZA,MM,{len(namen)}\n{mm(namen)}\nC\nZA,DA,{len(zeilen)}\n" + "\n".join(da) + \
        f"\nC\nENDE_{name}\nC\n"


def programm(name, h, b, wand, r, laenge, weg, konturen, zeiten):
    info = abschnitt("EINRICHTEPLAN_INFO", ["Maschine", "Programmnummer", "Bearbeiter", "Datum", "Material-ID",
                                            "Maschinenzeit", "Cutting length", "viewer name machine"],
                     [["T11", name, "Test", "10.03.2025", "St37", round(sum(zeiten) / 60, 2), weg, "Tube 5000 (T11) 1"]])
    tech = abschnitt("TUBE_TECH", ["Rohr-ID", "Querschnitt", "Rohrlaenge", "Wandstaerke", "Eckenradius (Rechteckrohr)",
                                   "Hoehe (Rechteckrohr)", "Breite (Rechteckrohr)",
                                   "(Huellkreis-)Durchmesser (Rechteck-/Rundrohr)", "Material", "Mass Per Meter"],
                     [[f"1_{int(b * 10)}X{int(h * 10)}X{int(r * 10)}_1_20", 1, 6000.0, wand, r, h, b, 0.0, "St37", 2.31]])
    teil = abschnitt("TUBE_PART_TECH", ["Tabellenidentifikator", "Querschnitt", "OriginalProgrammedTubeLength",
                                        "MachiningLength", "Work Part Length"],
                     [["TPT-1", 1, laenge + 0.1, laenge + 5.6, laenge]])
    zeit = abschnitt("TUBE_PART_TIMES", ["Calculated First Cut Machine Time", "Calculated Contour Machine Time",
                                         "Calculated Cut Off Machine Time", "Data Set Name"], [[*zeiten, "TPT-1"]])
    nc = ["BEGIN_PROGRAMM", f'N40 MSG("PART DIMENSIONS: {laenge} X {b} X {h} X {r} X {wand}")']
    for k in range(konturen):      # je Kontur mehrere TC_LASER_ON (Segmente), ein Einstich
        nc += [f"N{100 + k}0 TC_LASER_ON(1,\"ST020\",{k},100)", "G1 X10", "TC_LASER_ON(1,\"ST020\",2,100)",
               "TC_LASER_OFF(2)"]
    nc.append("ENDE_PROGRAMM")
    return "BD\nSET_METRIC\nC\n" + info + tech + teil + zeit + "\n".join(nc) + "\nC\nED\n"


def job(name, programme):
    kopf = abschnitt("FERTIGUNG_AUFTRAG_TMP", ["Jobname", "FertAuftrBez", "Programmname", "SollAnzahl"],
                     [[name, fa, p, n] for fa, p, n, _ in programme])
    return "BD\nSET_METRIC\n" + kopf + "ED\nC\n" + "".join(t for *_, t in programme)


def bson(d):
    teil = b""
    for k, v in d.items():
        kb = k.encode() + b"\x00"
        if isinstance(v, float):
            teil += b"\x01" + kb + struct.pack("<d", v)
        elif isinstance(v, str):
            s_ = v.encode() + b"\x00"
            teil += b"\x02" + kb + struct.pack("<i", len(s_)) + s_
        elif isinstance(v, dict):
            teil += b"\x03" + kb + bson(v)
        elif isinstance(v, list):
            teil += b"\x04" + kb + bson({str(i): x for i, x in enumerate(v)})
        elif isinstance(v, int):
            teil += b"\x10" + kb + struct.pack("<i", v)
    return struct.pack("<i", len(teil) + 5) + teil + b"\x00"


def tubx(pid, art, wand, laenge, gewicht, prog):
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("tubeProps/app.xml",
                   '﻿<?xml version="1.0" encoding="utf-8"?><appProperties xmlns="http://www.trumpf.com/xmlns/'
                   f'cadcam/tube-properties/"><profileId>{pid}</profileId><profileType>{art}</profileType><machineId>'
                   'Tube 5000 (T11) 1</machineId><laserTechnologyTable><material>1.0038</material><thickness>'
                   f'{wand} millimeter</thickness></laserTechnologyTable></appProperties>'.encode("utf-8"))
        z.writestr(f"Task3D/Workpiece{prog}.bson",
                   bson({"Version": {"Major": 1}, "Workpiece": {"VerticesOfTriangleMesh": [1.0, 2.0, 3.0] * 50,
                                                               "WorkpieceLength": laenge, "Weight": gewicht,
                                                               "ProfileId": pid}}))
        z.writestr("Preview/raw.png", b"\x89PNG")
    return puffer.getvalue()


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())

# ------------------------------------------------------------------ T1 ein Programm
p10 = programm("TEST_P10_1x", 40.0, 60.0, 2.0, 4.0, 3594.998, 5555.94, 77, (2.80, 67.52, 2.91))
(tmp / "TEST_P10_1x.lst").write_bytes(p10.replace("Test", "Bökmann").encode("cp1252"))
t = tp.lst_lesen(tmp / "TEST_P10_1x.lst")
assert len(t) == 1, t
t = t[0]
assert t["profilform"] == "Rechteckrohr" and (t["a"], t["b"], t["wand"], t["radius"]) == (60.0, 40.0, 2.0, 4.0), t
assert t["laenge"] == 3595.0 and t["schneidweg"] == 5555.9 and t["einstiche"] == 77 and t["zeit_s"] == 73.2, t
assert t["werkstoff"] == "St37" and tp.werkstoff_wort(t) == "S235" and t["artikel"] == "TEST_P10_1x" and \
    t["stueck"] is None and t["maschine"] == "Tube 5000 (T11) 1" and t["stangenlaenge"] == 6000.0, t
assert "Rechteckrohr 60,0×40,0×2,0" in tp.text(t) and "77 Einstiche" in tp.text(t)
ok("T1 LST: Rechteckrohr 60×40×2 R4, Länge 3595, Schneidweg 5555,9 mm, 77 Einstiche, 73,2 s je Teil, St37 → S235")

# ------------------------------------------------------------------ T2 Job-Liste
p20 = programm("TEST_P20_2x", 40.0, 40.0, 2.0, 4.0, 1435.0, 1978.46, 15, (6.32, 13.17, 2.96))
p30 = programm("TEST_P30_3x", 40.0, 60.0, 2.0, 4.0, 1275.0, 5531.56, 58, (2.80, 57.00, 3.20))
(tmp / "2026-44094_1.lst").write_text(job("2026-44094_1", [("10186133_247323", "TEST_P10_1x", 10, p10),
                                                          ("10186133_166060", "TEST_P30_3x", 30, p30)]),
                                      encoding="cp1252")
j = tp.lst_lesen(tmp / "2026-44094_1.lst")
assert [(x["artikel"], x["programm"], x["stueck"], x["laenge"], x["einstiche"]) for x in j] == [
    ("10186133_247323", "TEST_P10_1x", 10, 3595.0, 77), ("10186133_166060", "TEST_P30_3x", 30, 1275.0, 58)], j
assert j[1]["zeit_s"] == 63.0 and j[1]["schneidweg"] == 5531.6 and j[0]["auftrag"] == "2026-44094_1"
q = tp.lst_lesen(text=p20, name="P20.lst")[0]
assert q["profilform"] == "Quadratrohr" and (q["a"], q["b"]) == (40.0, 40.0) and q["einstiche"] == 15
ok("T2 Job-Liste: zwei Programme, Fertigungsauftrag als Artikel, Sollanzahl 10/30; Quadratrohr 40×40 erkannt")

# ------------------------------------------------------------------ T3 TUBX
nur = tmp / "nur"
nur.mkdir()
(nur / "TEST_P20_2x.tubx").write_bytes(tubx("1_400X400X40_1_20", "Rectangular", 2, 1435.0, 3.093, "TEST_P20_2x"))
teile, fehler = tp.lesen([nur / "TEST_P20_2x.tubx"])
assert not fehler and len(teile) == 1, (teile, fehler)
x = teile[0]
assert x["profilform"] == "Quadratrohr" and (x["a"], x["b"], x["wand"], x["radius"]) == (40.0, 40.0, 2.0, 4.0), x
assert x["laenge"] == 1435.0 and abs(x["gewicht"] - 3.093) < 1e-9 and x["werkstoff"] == "1.0038" and \
    tp.werkstoff_wort(x) == "S235" and x["schneidweg"] is None and "ohne LST" in x["hinweise"][0], x
(nur / "TEST_P20_2x.lst").write_text(p20, encoding="cp1252")        # LST daneben
teile, fehler = tp.lesen([nur / "TEST_P20_2x.tubx"])
x = teile[0]
assert x["schneidweg"] == 1978.5 and x["einstiche"] == 15 and x["zeit_s"] == 22.4 and not x["hinweise"] and \
    abs(x["gewicht"] - 3.093) < 1e-9 and "TEST_P20_2x.lst" in x["quelle"], x
teile, fehler = tp.lesen([nur / "TEST_P20_2x.lst", nur / "TEST_P20_2x.tubx"])     # beide gewählt: ein Teil
assert len(teile) == 1 and teile[0]["einstiche"] == 15, teile
rund = tp.tubx_lesen(roh=tubx("1_424X424_1_20", "Round", 2, 500.0, 1.0, "R"), name="R.tubx")[0]
assert rund["profilform"] == "Rundrohr" and rund["a"] == 42.4 and rund["b"] is None, rund
ok("T3 TUBX: Profil aus Profil-ID, Länge, Gewicht; ohne LST Hinweis, mit gleichnamiger LST Schneidweg/Einstiche/Zeit")

# ------------------------------------------------------------------ T4 Fehler
(tmp / "leer.lst").write_text("BD\nirgendwas\nED\n")
(tmp / "kaputt.tubx").write_bytes(b"kein zip")
teile, fehler = tp.lesen([tmp / "leer.lst", tmp / "kaputt.tubx", tmp / "fehlt.lst"])
assert not teile and len(fehler) == 3 and "keine TRUMPF-LST" in fehler[0] and "nicht öffnen" in fehler[1] and \
    "keine TUBX" in fehler[2], fehler
assert tp.dateien(["a.LST", "b.tubx", "c.stp", "d.dxf"]) == ["a.LST", "b.tubx"]
ok("T4 Fehler: keine LST, keine TUBX, fehlende Datei als Meldung, nichts angelegt")

# ------------------------------------------------------------------ T5 im Angebot
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
profile = {z["profil_id"]: z for z in db.zeilen("profile")}
for pid, form, a_, b_ in (("RE 60x40x2", "Rechteckrohr", 60.0, 40.0), ("QR 40x40x2", "Quadratrohr", 40.0, 40.0)):
    if not any(p.get("form") == form and p.get("a") == a_ and (p.get("b") or a_) == b_ and p.get("wand") == 2.0
               for p in profile.values()):
        vorlage = next(p for p in profile.values() if p.get("form") == form)
        db.neu("profile", {**{n: v for n, v in vorlage.items() if n not in ("id", "uid")}, "profil_id": pid,
                           "a": a_, "b": b_, "wand": 2.0})
a = db.angebot_neu(dict(nummer="2026-00099", kunde="Test", maschine="T11"))
s = fenster.angebot_oeffnen(a)
from rohrlaser.neue_position import TRUMPF, TYPEN  # noqa: E402
assert TRUMPF in TYPEN
(tmp / "unbekannt.lst").write_text(programm("TEST_X", 33.0, 77.0, 2.0, 4.0, 500.0, 300.0, 3, (1, 2, 1)),
                                   encoding="cp1252")
n = s.aus_trumpf([str(tmp / "2026-44094_1.lst"), str(nur / "TEST_P20_2x.lst"), str(tmp / "unbekannt.lst")])
assert n == 4, n
pos = db.positionen(a)
assert [p["artikel"] for p in pos] == ["10186133_247323", "10186133_166060", "TEST_P20_2x", "TEST_X"], pos
p1, p2, p3, px = pos
assert p1["laenge"] == 3595.0 and p1["stueck"] == 10 and p1["schneidweg"] == 5555.9 and p1["einstiche"] == 77 and \
    p1["zeit_manuell"] == 73.2 and p1["bezeichnung"] == "TEST_P10_1x", p1
profile = {z["profil_id"]: z for z in db.zeilen("profile")}
assert profile[p1["profil_id"]]["form"] == "Rechteckrohr" and profile[p3["profil_id"]]["form"] == "Quadratrohr"
assert str(p1["werkstoff_id"]).startswith("S235") and p3["stueck"] == 1 and p3["einstiche"] == 15, (p1, p3)
assert not px["profil_id"] and px["laenge"] == 500.0, px
ok("T5 Angebot: 4 Positionen (Job-Liste, LST, unbekanntes Profil ohne Profil-ID), Schneidzeit je Teil aus TRUMPF")
db.einstellung_setzen("trumpf_zeit", "nein")
s.aus_trumpf([str(tmp / "TEST_P10_1x.lst")])
assert db.positionen(a)[-1]["zeit_manuell"] in (None, ""), db.positionen(a)[-1]
ok("T5 Einstellung trumpf_zeit = nein: Schneidzeit bleibt berechnet")

# ------------------------------------------------------------------ T6 Laser-an-Zeit (Patrick 24.11.2026)
verbrauch = abschnitt("CONSUMPTION_TIMES", ["ConsumptionGroup", "LaserPower", "OnTime"],
                      [[1, 0, 50.0], [2, 3000, 40.5], [2, 0, 32.7]])
(tmp / "TEST_P11.lst").write_text(p10.replace("TEST_P10_1x", "TEST_P11").replace("BEGIN_PROGRAMM", verbrauch +
                                                                                 "BEGIN_PROGRAMM"), encoding="cp1252")
(t6,) = tp.lst_lesen(tmp / "TEST_P11.lst")
assert t6["laser_an_s"] == 40.5 and t6["verfahren_s"] == 32.7, t6
db.einstellung_setzen("trumpf_zeit", "ja")
s.aus_trumpf([str(tmp / "TEST_P11.lst")])
p6 = db.positionen(a)[-1]
assert p6["zeit_manuell"] in (None, "") and '"laser_an_s": 40.5' in p6["step_merkmale"], p6
from rohrlaser import rechnen  # noqa: E402
assert rechnen.programm_laserzeit(p6, {"trumpf_zeit": "ja"}) == (40.5, True, 32.7), p6["step_merkmale"]
db.einstellung_setzen("trumpf_zeit", "ganz")
s.aus_trumpf([str(tmp / "TEST_P11.lst")])
assert db.positionen(a)[-1]["zeit_manuell"] == 73.2, db.positionen(a)[-1]
ok("T6 Laser-an-Zeit: ja = reine Laserzeit (Programmdaten in der Position, Rest berechnet), ganz = ganze Zeit von Hand")

print("OK: TRUMPF-Programme einlesen")
