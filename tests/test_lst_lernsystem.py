"""Lernsystem L2, L4, L5 (Patrick 20.11.2026 „Alles einbauen nach allen Empfehlungen“; lst_vergleich.py,
lst_lernen.py):
- V1 Zuordnung: PPEASE-Nummer (Angebot mit Nummer in den Zusatzdaten), Artikelnummer, Merkmale (Profil, Werkstoff,
  Länge ± 0,5 mm, Schneidweg ± 2 %), von Hand gemerkt (auch „nie zuordnen“)
- V2 Vergleich: unsere Laserzeit ohne Nebenzeit gegen gemessen bzw. TRUMPF, absolut und in %; Geometrie-Abweichung →
  Liste „STEP-Messung prüfen“, zählt nicht fürs Lernen; vor dem Lauf gespeicherte LST zählt nicht
- L4 Vorschläge je Ebene (Maschine × Gruppe, Werkstoff × Profil, Wandbereich, Merkmal): gewichteter Median, ab 10
  Teilen aus 3 Programmen, Halbwertszeit 180 Tage, Ausreißer über 3 × MAD; Kalibrierung je Baustein bekommt die
  LST-Fälle (Einstechen eigener Baustein); Kennwerte-Quellen lst_…
- L5 Freigeben nur bei „ok“ und anwendbarer Ebene, über 15 % Preiswirkung nur mit Bestätigung; Ablehnen ruht;
  Zurücksetzen stellt die alten Vorschübe her; Protokoll
Synthetische Dateien, keine Kundendaten.

Aufruf: python tests/test_lst_lernsystem.py
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
import lst_beispiel as lb  # noqa: E402
from rohrlaser import kalibrierung, kennwerte  # noqa: E402
from rohrlaser import lst_lernen as ll  # noqa: E402
from rohrlaser import lst_vergleich as lv  # noqa: E402
from rohrlaser import produktion_lst as pl  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication(sys.argv)
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
heute = datetime.date.today()
aid = beispiel_angebot.anlegen(db, dict(datum=heute.isoformat()))
s = f.angebot_oeffnen(aid)
assert s.optimieren()
db.zusatz_setzen(aid, "ppease", dict(nummer="2026-44094"))
alt = beispiel_angebot.anlegen(db, dict(nummer="A-2025-0001", datum=(heute - datetime.timedelta(days=400)).isoformat()))

# Rohre der Positionen 10, 20, 50 (Rundrohre S235) mit Geometrie wie in der Kalkulation
POS = {10: dict(rund=42.4, wand=2.0, laenge=1250.0, weg=410.5, konturen=4, artikel="4711-001"),
       20: dict(rund=42.4, wand=2.0, laenge=860.0, weg=302.0, konturen=2, artikel="4711-002"),
       50: dict(rund=48.3, wand=2.6, laenge=345.0, weg=255.0, konturen=2, artikel="4711-005")}
ordner = tmp / "lst"
ordner.mkdir()
datum = heute.strftime("%d.%m.%Y")


def schreiben(name, pos, **mehr):
    (ordner / f"{name}.lst").write_text(lb.lst(name, datum=datum, **dict(POS[pos], **mehr)), encoding="cp1252")


# ------------------------------------------------------------------ V1 Zuordnung
schreiben("2026-44094_1", 20, artikel="x")                    # PPEASE-Nummer im Dateinamen
schreiben("P_ART", 50, job="J1", weg=999.0)                   # Artikelnummer (Fertigungsauftrag), Schneidweg falsch
schreiben("P_MERK", 10)                                       # nur Merkmale
schreiben("P_KEIN", 10, laenge=1300.0)                        # passt nirgends
schreiben("P_HAND", 10, laenge=1300.0, artikel="y")
assert pl.ordner_einlesen(db, ordner)["neu"] == 5
teil = {t["programm"]: t for t in pl.teile(db)}
zu = lv.zuordnen(db)
z = {p: zu[(p, 1)] for p in teil}
assert (z["2026-44094_1"]["art"], z["2026-44094_1"]["pos"], z["2026-44094_1"]["angebot_id"]) == (lv.PPEASE, 20, aid), z
assert (z["P_ART"]["art"], z["P_ART"]["pos"]) == (lv.ARTIKEL, 50), z["P_ART"]
assert (z["P_MERK"]["art"], z["P_MERK"]["pos"], z["P_MERK"]["sicher"]) == (lv.MERKMALE, 10, True), z["P_MERK"]
assert z["P_KEIN"]["art"] == lv.KEINE and z["P_KEIN"]["position_id"] is None
lv.merken(db, teil["P_HAND"], db.angebot(aid)["nummer"], 30)
lv.merken(db, teil["P_KEIN"], "", None)                         # nie zuordnen
zu = lv.zuordnen(db)
assert (zu[("P_HAND", 1)]["art"], zu[("P_HAND", 1)]["pos"]) == (lv.HAND, 30), zu[("P_HAND", 1)]
assert zu[("P_KEIN", 1)]["art"] == lv.HAND and zu[("P_KEIN", 1)]["position_id"] is None
lv.vergessen(db, teil["P_HAND"])
assert lv.zuordnen(db)[("P_HAND", 1)]["art"] == lv.KEINE
ok("V1 Zuordnung: PPEASE-Nummer, Artikelnummer, Merkmale, von Hand (auch „nie zuordnen“), vergessen")

# ------------------------------------------------------------------ V2 Vergleich
zeilen = {x["teil"]["programm"]: x for x in lv.vergleich(db)}
m = zeilen["P_MERK"]
assert m["soll_s"] and m["soll_s"] < m["soll_voll_s"], "unsere Zeit ohne Nebenzeit"
assert m["lst_s"] == 22.45 and m["ist_s"] is None and m["diff_pct"] is not None and not m["lernbar"]
assert "vor dem Lauf" in m["grund"], m["grund"]
assert zeilen["P_ART"]["geometrie"] and "Schneidweg" in zeilen["P_ART"]["geometrie"][0]
assert [x["teil"]["programm"] for x in lv.step_pruefen(list(zeilen.values()))] == ["P_ART"]
assert zeilen["P_KEIN"]["grund"] == "nicht zugeordnet"
soll = {p: zeilen[n]["soll_s"] for p, n in ((10, "P_MERK"), (20, "2026-44094_1"))}
kz = lv.kennzahlen(list(zeilen.values()))
assert (kz["teile"], kz["zugeordnet"], kz["step_pruefen"], kz["lernbar"]) == (5, 3, 1, 0), kz
ok(f"V2 Vergleich: unsere Zeit {m['soll_s']:.1f} s ohne Nebenzeit gegen TRUMPF {m['lst_s']:.1f} s "
   f"({m['diff_pct']:+.0f} %), Geometrie → „STEP-Messung prüfen“, vor dem Lauf gespeichert zählt nicht")

# ------------------------------------------------------------------ L4 Vorschläge
# 12 gelaufene Programme (gemessene Zeiten): Pos. 10 und 20 brauchen 20 % länger, ein Ausreißer (× 3)
for i in range(12):
    pos = 10 if i % 2 else 20
    ist = soll[pos] * (3.0 if i == 11 else 1.2 + 0.01 * (i % 3))
    schreiben(f"L{i:02d}", pos, n=2, mittel=(0.2 * ist, 0.6 * ist, 0.2 * ist))
pl.ordner_einlesen(db, ordner)
fl = ll.faelle(db)
assert len(fl) == 12 and all(0.99 < x["gewicht"] <= 1.0 for x in fl), len(fl)
assert abs(ll.gewicht(heute - datetime.timedelta(days=180), heute) - 0.5) < 1e-9
v = {(x["quelle"], x["schluessel"]): x for x in ll.vorschlaege(db)}
vm = v[(ll.Q_MASCHINE, ("T11", "Stahl"))]
assert vm["status"] == "ok" and vm["n"] == 11 and len(vm["ausreisser"]) == 1 and vm["programme"] == 11, vm["n"]
assert vm["anwendbar"] and vm["faktor"] > 1.2 and vm["preiswirkung"] > 0, (vm["faktor"], vm["preiswirkung"])
vp = v[(ll.Q_PROFIL, ("T11", "Kategorie Stahl", "RR 42,4x2,0"))]
assert vp["status"] == "ok" and not vp["anwendbar"] and 1.19 < vp["faktor"] < 1.23, vp["faktor"]
assert (ll.Q_BEREICH, ("T11", "Kategorie Stahl", "bis 3 mm")) in v
# zu wenig Programme: 11 Teile, aber nur 2 Programme
assert ll.auswerten([(dict(programm=f"P{i % 2}", gewicht=1.0), 1.0, 1.1) for i in range(11)])["status"] == \
    "zu wenig Daten"
assert ll.auswerten([(dict(programm=f"P{i}", gewicht=1.0), 1.0, 1.5) for i in range(11)])["warnung"]
# Kennwerte-Quellen und Kalibrierung je Baustein
kv = [x for x in kennwerte.vorschlaege(db) if x["quelle"] == ll.Q_MASCHINE]
assert kv and kv[0]["status"] == "ok", kv
kb = kalibrierung.faelle_bausteine(db).get("T11") or []
assert sum(1 for x in kb if x.get("lst")) == 12 and all(x["roh"]["neben"] == 0 for x in kb if x.get("lst"))
vb = [x for x in kalibrierung.vorschlaege_bausteine(db) if x["maschine"] == "T11" and x.get("kategorie") is None]
assert vb and vb[0]["n"] >= 12 and "einstechen" in vb[0]["neu"], vb
ok(f"L4 Vorschläge: Maschine × Gruppe Faktor {vm['faktor']:.3f} aus {vm['n']} Teilen (1 Ausreißer), Preiswirkung "
   f"{vm['preiswirkung']:+.1f} %, Profil nur Hinweis, ab 10 Teilen aus 3 Programmen, Kennwerte und Bausteine")

# ------------------------------------------------------------------ L5 Verwalten
try:
    ll.freigeben(db, vp, "0.9.425")
    raise AssertionError("nur Hinweis")
except ValueError as e:
    assert "nur ein Hinweis" in str(e)
vor = {z_["id"]: z_["vorschub_gross"] for z_ in kalibrierung.zeilen_zu(db, ("T11", "Kategorie Stahl", "bis 3 mm"),
                                                                        kalibrierung.QUELLE_BEREICH)}
gross = dict(vm, preiswirkung=20.0)
try:
    ll.freigeben(db, gross, "0.9.425")
    raise AssertionError("über 15 % ohne Bestätigung")
except ll.BestaetigungNoetig as e:
    assert "15 %" in str(e)
hid = ll.freigeben(db, vm, "0.9.425")
sd = {z_["id"]: z_ for z_ in db.zeilen("schneiddaten")}
assert any(sd[i]["vorschub_gross"] < vor[i] for i in vor if vor[i]), "Vorschübe kleiner (Ist länger)"
p = ll.protokoll(db)
assert p[0]["art"] == "freigegeben" and p[0]["historie_id"] == hid and "Lernsystem LST" in p[0]["text"]
assert ll.zuruecksetzen(db, hid) > 0
sd = {z_["id"]: z_ for z_ in db.zeilen("schneiddaten")}
assert all(sd[i]["vorschub_gross"] == vor[i] for i in vor)
assert ll.protokoll(db)[0]["art"] == "zurückgenommen"
ll.ablehnen(db, vp, "Profil wird ohnehin ersetzt", "PB")
assert (ll.Q_PROFIL, vp["schluessel"]) not in {(x["quelle"], x["schluessel"]) for x in ll.vorschlaege(db)}
assert any(x["art"] == "abgelehnt" for x in ll.protokoll(db))
ll.wieder_aufnehmen(db, vp)
assert (ll.Q_PROFIL, vp["schluessel"]) in {(x["quelle"], x["schluessel"]) for x in ll.vorschlaege(db)}
ok("L5 Freigeben (Hinweis-Ebene nein, über 15 % nur mit Bestätigung), Vorschübe geändert und zurückgesetzt, "
   "Ablehnen ruht, Protokoll")
# ------------------------------------------------------------------ L3 Fenster und L6 Mehrplatz
from rohrlaser import funktionen, teilen  # noqa: E402

assert lv.ZUORDNUNG.name in teilen.GETEILT_NAME and ll.ENTSCHEIDUNGEN.name in teilen.GETEILT_NAME
from rohrlaser import db_verbindung  # noqa: E402
assert "uid" in db_verbindung.spalten(db.con, lv.ZUORDNUNG.name), "Kennung für den Abgleich"
assert funktionen.DATEI_ODER["Produktionsdaten & Lernsystem …"]
db.einstellung_setzen("lst_ordner", str(ordner))
gesehen = {}


def bedienen(d):
    d.frage = lambda titel, text: gesehen.setdefault("fragen", []).append(titel) or True
    d.eingabe = lambda titel, text, vorgabe: f"{db.angebot(aid)['nummer']}/30"
    k = d.kacheln.kacheln
    gesehen["kacheln"] = {n: k[n].wert.text() for n in k}
    gesehen["reiter"] = [d.reiter.tabText(i) for i in range(d.reiter.count())]
    gesehen["zeilen"] = (d.ptab.rowCount(), d.vtab.rowCount(), d.stab.rowCount())
    d.nur_step.setChecked(True)
    gesehen["step"] = d.vtab.rowCount()
    d.nur_step.setChecked(False)
    r = next(i for i, z in enumerate(d.v_zeilen) if z["teil"]["programm"] == "P_HAND")
    d.vtab.selectRow(r)
    d.zuordnen()
    gesehen["hand"] = next(z for z in d.zeilen if z["teil"]["programm"] == "P_HAND")["zuordnung"]
    r = next(i for i, v in enumerate(d.vorschlaege) if v["quelle"] == ll.Q_MASCHINE)
    d.stab.selectRow(r)
    gesehen["freigabe"] = d.freigeben()
    gesehen["protokoll"] = d.rtab.rowCount()
    d.rtab.selectRow(0)
    gesehen["zurueck"] = d.zuruecksetzen()
    schreiben("NEU_1", 10)
    d.einlesen(warten=True)
    gesehen["status"] = d.status.text()


d = f.lernsystem(dialog=bedienen)
assert gesehen["reiter"] == ["Produktionsdaten", "Vergleich", "Vorschläge", "Protokoll"], gesehen["reiter"]
assert gesehen["kacheln"]["step"] == "1" and gesehen["kacheln"]["vorschlaege"] != "0", gesehen["kacheln"]
assert gesehen["zeilen"][0] == len(pl.teile(db)) - 1 and gesehen["step"] == 1, gesehen
assert (gesehen["hand"]["art"], gesehen["hand"]["pos"]) == (lv.HAND, 30), gesehen["hand"]
assert gesehen["freigabe"] and gesehen["fragen"][0] == "Vorschlag freigeben" and gesehen["zurueck"] > 0, gesehen
assert "1 LST-Datei neu gelesen" in gesehen["status"], gesehen["status"]
ok("L3 Fenster: Kacheln, Reiter Produktionsdaten/Vergleich/Vorschläge/Protokoll, Zuordnung von Hand, Freigeben "
   "und Zurücksetzen; L6 Einlesen im Hintergrund, Zuordnungen und Ablehnungen über den gemeinsamen Ordner")
f.close()
print("Alle Tests Lernsystem LST bestanden.")
