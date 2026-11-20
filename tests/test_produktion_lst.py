"""Lernsystem L1: Produktionsdaten aus TRUMPF-LST sammeln (Patrick 20.11.2026, produktion_lst.py):
- P1 Leser: Zeitanteile berechnet (Anschnitt, Konturen, Abschnitt), gemessen (Mittel, sonst letzter Lauf) mit Anzahl,
  Strahl-Ein aus CONSUMPTION_TIMES, Maschinenzeit; Datenqualität vollständig / Teilwerte fehlen / unplausibel
- P2 Ordner einlesen (mit Unterordnern): PPEASE-Nummer aus Dateiname/Auftrag, jede Datei einmal (Prüfsumme, auch
  umbenannt), neu gespeicherte LST mit gemessenen Zeiten ersetzt die Teile der alten Fassung, Fehler gemeldet
- P3 Einstellung lst_ordner (Seite STEP-Import), Lernzentrale: Knopf „LST-Ordner einlesen“ und Zahlen im Text
Synthetische Dateien im Aufbau der echten (keine Kundendaten im Repo).

Aufruf: python tests/test_produktion_lst.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

from rohrlaser import einstellungen_ordnung, lernen_dialog  # noqa: E402
from rohrlaser import produktion_lst as pl  # noqa: E402
from rohrlaser import trumpf_programm as tp  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def abschnitt(name, namen, zeilen):
    mm = "\n".join(f"MM,AT,1,{10 * (i + 1):4d},1,1,,'{n}',,'',T" for i, n in enumerate(namen))
    da = ["DA," + ",".join(f"'{w}'" if isinstance(w, str) else str(w) for w in z) for z in zeilen]
    return f"BEGIN_{name}\nC\nZA,MM,{len(namen)}\n{mm}\nC\nZA,DA,{len(zeilen)}\n" + "\n".join(da) + \
        f"\nC\nENDE_{name}\nC\n"


ZEITEN = ["Calculated First Cut Machine Time", "Calculated Contour Machine Time", "Calculated Cut Off Machine Time",
          "Last Program Run Measured First Cut Machine Time", "Last Program Run Measured Contour Machine Time",
          "Last Program Run Measured Cut Off Machine Time", "Number Of Recorded Part Times",
          "Average Measured First Cut Machine Time", "Average Measured Contour Machine Time",
          "Average Measured Cut Off Machine Time", "Data Set Name"]


def lst(name, weg=1978.5, konturen=15, ber=(6.32, 13.17, 2.96), letzt=(0, 0, 0), n=0, mittel=(0, 0, 0), job=""):
    info = abschnitt("EINRICHTEPLAN_INFO", ["Maschine", "Programmnummer", "Datum", "Material-ID", "Maschinenzeit",
                                            "Cutting length", "viewer name machine"],
                     [["T11", name, "10.03.2025", "St37", round(sum(ber) / 60, 2), weg, "Tube 5000 (T11) 1"]])
    tech = abschnitt("TUBE_TECH", ["Rohr-ID", "Querschnitt", "Rohrlaenge", "Wandstaerke", "Eckenradius (Rechteckrohr)",
                                   "Hoehe (Rechteckrohr)", "Breite (Rechteckrohr)", "Material", "Mass Per Meter"],
                     [["1_400X600X20_1_20", 1, 6000.0, 2.0, 2.0, 60.0, 40.0, "St37", 2.31]])
    teil = abschnitt("TUBE_PART_TECH", ["Tabellenidentifikator", "Work Part Length"], [["TPT-1", 425.0]])
    zeit = abschnitt("TUBE_PART_TIMES", ZEITEN, [[*ber, *letzt, n, *mittel, "TPT-1"]])
    verbr = abschnitt("CONSUMPTION_TIMES", ["ConsumptionGroup", "GasType", "OnTime"], [[1, 2, 21.31], [2, 0, 9.0]])
    nc = ["BEGIN_PROGRAMM"] + [f'TC_LASER_ON(1,"ST020",{k},100)\nG1 X10\nTC_LASER_OFF(2)' for k in range(konturen)]
    kopf = abschnitt("FERTIGUNG_AUFTRAG_TMP", ["Jobname", "FertAuftrBez", "Programmname", "SollAnzahl"],
                     [[job, "10186133", name, 2]]) if job else ""
    return ("BD\n" + kopf + "ED\nC\n" if job else "") + "BD\nSET_METRIC\nC\n" + info + tech + teil + zeit + verbr + \
        "\n".join(nc) + "\nENDE_PROGRAMM\nC\nED\n"


app = QApplication.instance() or QApplication(sys.argv)
tmp = Path(tempfile.mkdtemp())

# ------------------------------------------------------------------ P1 Leser
(t,) = tp.lst_lesen(text=lst("P20"), name="P20.lst")
assert t["zeiten_berechnet"] == dict(anschnitt=6.32, konturen=13.17, abschnitt=2.96), t["zeiten_berechnet"]
assert t["zeiten_gemessen"] is None and t["messungen"] == 0 and t["strahl_s"] == 21.31, t
assert abs(t["maschinenzeit_s"] - 22.2) < 0.01 and t["einstiche"] == 15 and t["schneidweg"] == 1978.5
assert tp.qualitaet(t) == (tp.VOLL, [])
(g,) = tp.lst_lesen(text=lst("P20", letzt=(6.0, 14.0, 3.0), n=4, mittel=(6.1, 14.2, 3.1)), name="P20.lst")
assert g["zeiten_gemessen"] == dict(anschnitt=6.1, konturen=14.2, abschnitt=3.1) and g["messungen"] == 4, g
(g1,) = tp.lst_lesen(text=lst("P20", letzt=(6.0, 14.0, 3.0)), name="P20.lst")
assert g1["zeiten_gemessen"] == dict(anschnitt=6.0, konturen=14.0, abschnitt=3.0), "ohne Mittel: letzter Lauf"
assert pl.zeit_s(g) == 23.4 and pl.zeit_s(g, gemessen=False) == 22.45
(u,) = tp.lst_lesen(text=lst("P21", weg=50.0), name="P21.lst")
stufe, gruende = tp.qualitaet(u)
assert stufe == tp.UNPLAUSIBEL and "Trennschnitt" in gruende[0], gruende
(o,) = tp.lst_lesen(text=lst("P22", konturen=0), name="P22.lst")
assert tp.qualitaet(o)[0] == tp.TEIL and "Einstiche fehlt" in tp.qualitaet(o)[1]
ok("P1 Zeitanteile berechnet/gemessen (Mittel vor letztem Lauf), Strahl-Ein, Maschinenzeit, Datenqualität")

# ------------------------------------------------------------------ P2 Ordner einlesen
db = Datenbank(tmp / "rohrlaser.db")
ordner = tmp / "lst"
(ordner / "2025").mkdir(parents=True)
(ordner / "2026-44094_2.lst").write_text(lst("10186133_P20"), encoding="cp1252")
(ordner / "2025" / "P21.lst").write_text(lst("P21", weg=50.0, job="2026-43001"), encoding="cp1252")
(ordner / "kaputt.lst").write_text("kein Programm", encoding="cp1252")
(ordner / "notiz.txt").write_text("x")
assert pl.ordner_einlesen(db)["fehler"][0].startswith("Kein LST-Ordner")
db.einstellung_setzen("lst_ordner", str(ordner))
erg = pl.ordner_einlesen(db)
assert (erg["neu"], erg["teile"], erg["bekannt"], len(erg["fehler"])) == (3, 2, 0, 1), erg
tl = {x["programm"]: x for x in pl.teile(db)}
assert tl["10186133_P20"]["ppease"] == "2026-44094" and tl["P21"]["ppease"] == "2026-43001", tl
assert tl["10186133_P20"]["qualitaet"] == tp.VOLL and tl["P21"]["qualitaet"] == tp.UNPLAUSIBEL
assert tl["10186133_P20"]["zeiten_berechnet"]["konturen"] == 13.17 and tl["P21"]["gruende"]
shutil.copy(ordner / "2026-44094_2.lst", ordner / "kopie.lst")
erg = pl.ordner_einlesen(db)
assert (erg["neu"], erg["bekannt"]) == (0, 4), erg
(ordner / "2026-44094_2_gelaufen.lst").write_text(lst("10186133_P20", n=3, mittel=(6.0, 15.0, 3.0)),
                                                  encoding="cp1252")
erg = pl.ordner_einlesen(db)
tl = [x for x in pl.teile(db) if x["programm"] == "10186133_P20"]
assert erg["neu"] == 1 and len(tl) == 1 and tl[0]["messungen"] == 3 and pl.zeit_s(tl[0]) == 24.0, (erg, tl)
u = pl.uebersicht(db)
assert u == dict(dateien=4, teile=2, voll=1, gemessen=1), u
assert "1 LST-Datei neu gelesen (1 Teile)" in pl.ergebnis_text(erg)
ok("P2 Ordner mit Unterordnern, PPEASE-Nummer, jede Datei einmal (auch Kopie), gelaufene Fassung ersetzt die alte")

# ------------------------------------------------------------------ P3 Einstellung und Lernzentrale
assert any("lst_ordner" in g.namen for s in einstellungen_ordnung.SEITEN for g in s.abschnitte
           if s.schluessel == "e_step"), "lst_ordner auf der Seite STEP-Import"
f = Hauptfenster(db)
gesehen = {}


def schauen(d):
    gesehen["texte"] = " ".join(x.text() for x in d.findChildren(QLabel))
    gesehen["knoepfe"] = [b.text() for b in d.findChildren(QPushButton)]


lernen_dialog.zeigen(f, dialog=schauen)
assert "LST-Ordner einlesen" in gesehen["knoepfe"], gesehen["knoepfe"]
assert "Produktionsdaten: 4 LST-Dateien, 2 Teile (1 vollständig, 1 mit gemessener Zeit)" in gesehen["texte"], \
    gesehen["texte"]
ok("P3 Einstellung lst_ordner (STEP-Import), Lernzentrale mit Knopf „LST-Ordner einlesen“ und Zahlen")
f.close()

# ------------------------------------------------------------------ P4 Tempo (L6): viele Dateien, zweiter Lauf öffnet keine
import time  # noqa: E402

viele = tmp / "viele"
viele.mkdir()
for i in range(1500):
    (viele / f"2026-{40000 + i}_1.lst").write_text(lst(f"V{i}", weg=1978.5 + i), encoding="cp1252")
t0 = time.perf_counter()
erg = pl.ordner_einlesen(db, viele)
t1 = time.perf_counter()
assert (erg["neu"], erg["teile"]) == (1500, 1500), erg
geoeffnet = []
alt_lesen = pl.Path.read_bytes
pl.Path.read_bytes = lambda self: geoeffnet.append(self) or alt_lesen(self)
try:
    erg = pl.ordner_einlesen(db, viele)
finally:
    pl.Path.read_bytes = alt_lesen
t2 = time.perf_counter()
assert erg["bekannt"] == 1500 and erg["neu"] == 0 and not geoeffnet, (erg, len(geoeffnet))
assert t2 - t1 < max(2.0, (t1 - t0) / 3), (t1 - t0, t2 - t1)
ok(f"P4 Tempo: 1.500 LST-Dateien in {t1 - t0:.1f} s gelesen, zweiter Lauf {t2 - t1:.2f} s ohne eine Datei zu öffnen")
print("Alle Tests Produktionsdaten LST bestanden.")
