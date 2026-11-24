"""Produktionsdaten-Intelligenz (Master-Auftrag Patrick 24.11.2026 „Intelligente Maschinendaten-Analyse – .LST & .BPF“):
- I1 LST auswerten: jeder Wert mit Quelle, Einheit, Deutung; Laser an / Verfahren je Leistungsstufe aus
  CONSUMPTION_TIMES, Ereignisse im NC-Teil (Konturen, Einstiche, Positionierungen, Umspannen, Vollkreise),
  abgeleitete Werte (Materialverbrauch, Teile je Stange, Ausnutzung, Vorschub) mit „berechnet aus …“, nicht gedeutete
  Felder dokumentiert, fehlende Werte nicht ergänzt
- I2 BPF auswerten: Profil, Länge, Konturen je Art, Schnittlänge, Anfahrwege, Vollkreise, Einstiche, Eilgänge,
  Gehrungswinkel; keine Zeiten (steht in „fehlend“)
- I3 Robust: kaputte, leere, abgeschnittene und fremde Dateien geben eine Fehlermeldung statt eines Absturzes; der
  Ordner wird trotzdem gelesen
- I4 Produktionsdaten: LST und BPF im selben Ordner, Kopie erkannt, Format/Version/nicht gedeutete Felder im
  Importprotokoll, BPF-Teil ohne Zeit zählt nicht fürs Lernen
- I5 Abgleich Kalkulation ↔ Maschinendaten (12 Werte) und Ursachen der Zeitabweichung (Anteile ergeben die Abweichung)
- I6 Gegenprobe der Lernvorschläge: gleichmäßige Abweichung → besser; Rauschen → Freigabe nur mit Bestätigung
- I7 Zeitmodell je Konturklasse (groß/mittel/klein) findet die Vorschübe wieder, Gegenprobe klein
- I8 Genauigkeitsbewertung: ohne Daten „keine Produktionsdaten“, nur CAM-Zeiten höchstens „gering“, „sehr gut“ nur mit
  ≥ 10 gemessenen Teilen und kleiner Abweichung
- I9 Fenster „Produktionsdaten-Intelligenz“: Reiter, zweite Kachelzeile, Import mehrerer Dateien im Hintergrund,
  Maschinendaten und Abgleich des gewählten Teils
- I10 KI: Produktions-KI nennt die Datenbasis je Position und die Ursachen über alle Teile; Preis erklären nennt sie
- I11 echte Dateien (nur wenn RL_MASCHINENDATEN auf einen Ordner zeigt; Kundendaten nicht im Repo)
Synthetische Dateien, keine Kundendaten.

Aufruf: python tests/test_produktionsdaten_intelligenz.py
"""
import datetime
import os
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
import bpf_beispiel as bb  # noqa: E402
import lst_beispiel as lb  # noqa: E402
from rohrlaser import ki_agenten, ki_kalkulation  # noqa: E402
from rohrlaser import lst_dashboard  # noqa: E402
from rohrlaser import lst_lernen as ll  # noqa: E402
from rohrlaser import lst_vergleich as lv  # noqa: E402
from rohrlaser import maschinendaten as md  # noqa: E402
from rohrlaser import produktion_abgleich as pa  # noqa: E402
from rohrlaser import produktion_genauigkeit as pg  # noqa: E402
from rohrlaser import produktion_lst as pl  # noqa: E402
from rohrlaser import produktion_zeitmodell as zm  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication(sys.argv)
tmp = Path(tempfile.mkdtemp())
heute = datetime.date.today()
datum = heute.strftime("%d.%m.%Y")
# wie in Patricks echter LST: Gruppe 1 Schneidgas, Gruppe 2 je Laserleistung (0 W = Verfahren)
VERBRAUCH = [(1, 2, 21.31, 0), (2, 0, 9.78, 0), (2, 0, 0.60, 2250), (2, 0, 0.92, 1200), (2, 0, 5.54, 4000),
             (2, 0, 5.62, 700)]
EXTRA = {"Bearbeitungslaenge (Soll)": 425.3, "X Min Gap To Next Part": 2.5, "Chuck Position Program Start End": 58.0}

# ------------------------------------------------------------------ I1 LST auswerten
text = lb.lst("P20", verbrauch=VERBRAUCH, nc_voll=True, teil_extra=EXTRA, konturen=6)
(a,) = md.lst_auswerten(text, "P20.lst")
m = a["merkmale"]
assert md.w(m, "laser_an_s") == 12.68 and md.w(m, "verfahren_s") == 9.78, (md.w(m, "laser_an_s"), md.w(m, "verfahren_s"))
assert md.w(m, "laser_an_4000w_s") == 5.54 and m["laser_an_s"][1] == "s" and "LaserPower > 0" in m["laser_an_s"][2]
assert (md.w(m, "konturen"), md.w(m, "einstiche"), md.w(m, "positionierungen"), md.w(m, "umspannen"),
        md.w(m, "vollkreise")) == (6, 6, 6, 1, 3), m
assert md.w(m, "verbrauch_mm") == 427.8 and "berechnet aus" in m["verbrauch_mm"][2]
assert md.w(m, "teile_je_stange") == 13 and m["teile_je_stange"][4] is False, "Deutung Futterposition unsicher"
assert md.w(m, "vorschub_mittel") and md.w(m, "zeit_gesamt_s") == 22.45 and md.w(m, "wand") == 2.0
assert m["kg_m"][1] == "kg/m", "Einheit berichtigt (Datei sagt kg)"
assert a["fehlend"] == [] and a["version"] == ""
assert any(f == "Work Part Length" for _, f, _ in a["unbekannt"]) is False
(b0,) = md.lst_auswerten(lb.lst("P0"), "P0.lst")         # alter Aufbau ohne Laserleistung und ohne Kommentare
assert "laser_an_s" not in b0["merkmale"] and "konturen" not in b0["merkmale"], "nichts ergänzt"
assert "konturen" in b0["fehlend"]
ok(f"I1 LST: {len(m)} Werte mit Quelle/Einheit/Deutung, Laser an 12,68 s + Verfahren 9,78 s, NC-Ereignisse, "
   "Verbrauch/Ausnutzung/Vorschub berechnet, fehlende Werte nicht ergänzt")

# ------------------------------------------------------------------ I2 BPF auswerten
bpf = bb.bpf(tmp / "Teil-1.bpf", bohrungen=2, rechtecke=1)
(e,) = md.bpf_auswerten(bpf.read_bytes(), bpf.name)
mb = e["merkmale"]
assert (md.w(mb, "konturen"), md.w(mb, "vollkreise"), md.w(mb, "einstiche"), md.w(mb, "positionierungen")) == \
    (5, 2, 5, 6), mb
assert abs(md.w(mb, "schneidweg") - 562.8) < 0.2 and md.w(mb, "anfahrweg") > 0
assert md.w(mb, "konturen_trennschnitt") == 2 and md.w(mb, "gehrung_ende") == 90.0 and md.w(mb, "maschine") == "LT8"
assert e["kopf"] == dict(profilform="Rechteckrohr", a=60.0, b=40.0, wand=3.0, radius=0.0), e["kopf"]
assert "zeit_gesamt_s" in e["fehlend"] and any("keine Zeiten" in f for f in e["fehlend"])
assert ("XML", "unbekanntes_feld", "42") in e["unbekannt"] and e["version"] == "3.10"
from step_messung import step_blm  # noqa: E402
from rohrlaser import bpf_xml  # noqa: E402
import xml.etree.ElementTree as ET  # noqa: E402
assert [ET.tostring(x) for x in bpf_xml.bpf_dokumente(bpf.read_bytes())] == \
    [ET.tostring(x) for x in step_blm.bpf_dokumente(bpf.read_bytes())], "Kopie bpf_xml liest wie step_blm"
ok("I2 BPF: Profil, Konturen je Art, Schnittlänge 562,8 mm, 2 Vollkreise, 5 Einstiche, 6 Eilgänge, Gehrung; "
   "keine Zeiten (als fehlend gemeldet), unbekanntes Feld dokumentiert")

# ------------------------------------------------------------------ I3 robust
kaputt = tmp / "kaputt"
kaputt.mkdir()
(kaputt / "leer.lst").write_bytes(b"")
(kaputt / "fremd.lst").write_text("Hallo", encoding="utf-8")
(kaputt / "halb.bpf").write_bytes(bpf.read_bytes()[:900])
(kaputt / "muell.bpf").write_bytes(bytes(random.Random(3).randrange(256) for _ in range(5000)))
(kaputt / "abgeschnitten.lst").write_text(text[:len(text) // 3], encoding="cp1252")
for p in sorted(kaputt.iterdir()):
    r = md.analysieren(p)
    assert r["fehler"] or r["teile"], p.name          # nie eine Ausnahme
assert md.analysieren(kaputt / "fremd.lst")["fehler"] and md.analysieren(kaputt / "muell.bpf")["fehler"]
assert md.analysieren(tmp / "gibtsnicht.bpf")["fehler"]
ok("I3 Robust: leere, fremde, abgeschnittene und zufällige Dateien → Fehlermeldung, kein Absturz")

# ------------------------------------------------------------------ I4 Produktionsdaten
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
aid = beispiel_angebot.anlegen(db, dict(datum=heute.isoformat()))
s = f.angebot_oeffnen(aid)
assert s.optimieren()
ordner = tmp / "maschine"
ordner.mkdir()
POS10 = dict(rund=42.4, wand=2.0, laenge=1250.0, weg=410.5, konturen=4, artikel="4711-001")
(ordner / "P10.lst").write_text(lb.lst("P10", datum=datum, verbrauch=[(1, 2, 8.0, 0), (2, 0, 1.5, 0),
                                                                    (2, 0, 6.5, 4000)], nc_voll=True, **POS10),
                                encoding="cp1252")
shutil.copy(bpf, ordner / "Teil-1.bpf")
shutil.copy(bpf, ordner / "Teil-1_kopie.bpf")
shutil.copy(kaputt / "fremd.lst", ordner / "fremd.lst")
erg = pl.ordner_einlesen(db, ordner)
assert (erg["neu"], erg["bekannt"], erg["bpf"], len(erg["fehler"])) == (3, 1, 1, 1), erg
assert "Maschinendatei" in pl.ergebnis_text(erg)
teile = {t["programm"]: t for t in pl.teile(db)}
assert teile["Teil-1"]["format"] == "BPF" and teile["Teil-1"]["qualitaet"] == "Teilwerte fehlen"
assert teile["Teil-1"]["profilform"] == "Rechteckrohr" and teile["P10"]["format"] == "LST"
assert md.w(teile["P10"]["merkmale"], "laser_an_s") == 6.5
kl = pl._klassen(dict(wand=2.0, schnittlaenge_material=1304.1, innen=[(10.3, 32.4)] * 3 + [(5.0, 15.7)],
                      enden=[("A", 40.0, 153.1), ("E", 40.0, 273.1)]))      # Felder aus trumpf_programm.lst_lesen
assert (md.w(kl, "mm_klein"), md.w(kl, "mm_mittel"), md.w(kl, "n_gross")) == (15.7, 97.2, 2), kl
assert abs(md.w(kl, "mm_gross") - (1304.1 - 15.7 - 97.2)) < 0.05 and "Grenzen" in kl["mm_gross"][2]
prot = {d["name"]: d for d in pl.dateien(db)}
assert prot["Teil-1.bpf"]["format"] == "BPF" and prot["Teil-1.bpf"]["version"] == "3.10"
assert prot["Teil-1.bpf"]["unbekannt"] >= 1 and prot["fremd.lst"]["fehler"]
u = pl.uebersicht(db)
assert (u["lst"], u["bpf"], u["fehler"]) == (2, 1, 1), u
ok("I4 Produktionsdaten: LST + BPF im Ordner, Kopie erkannt, Importprotokoll mit Format/Version/Fehler/unbekannten "
   "Feldern, BPF ohne Zeit zählt nicht fürs Lernen")

# ------------------------------------------------------------------ I5 Abgleich und Ursachen
zeilen = lv.vergleich(db)
z10 = next(z for z in zeilen if z["teil"]["programm"] == "P10")
assert z10["zuordnung"]["position_id"], z10["zuordnung"]
ergeb = pa.auswerten(db, zeilen)
e10 = next(x for x in ergeb if x["zeile"]["teil"]["programm"] == "P10")
w = {x["schluessel"]: x for x in e10["werte"]}
assert [x["schluessel"] for x in e10["werte"]] == [p[0] for p in pa.PARAMETER]
assert w["einstiche"]["kalk"] == 4 and w["einstiche"]["maschine"] == 4 and w["einstiche"]["diff"] == 0
assert w["laserzeit"]["maschine"] == 6.5 and w["positionierzeit"]["maschine"] == 1.5
assert w["zeit"]["maschine_art"] == pa.BERECHNET and w["zeit"]["kalk_art"] == pa.GESCHAETZT
assert w["vorschub"]["kalk"] and w["vorschub"]["maschine"] and w["material"]["maschine"] is None
assert w["material"]["maschine_art"] == pa.FEHLT, "Bearbeitungslänge nicht in der Datei → fehlt"
us = e10["ursachen"]
summe = sum(x["anteil_s"] for x in us)
assert abs(summe - w["zeit"]["diff"]) < pa.UNWICHTIG_S * len(pa.PARAMETER), (summe, w["zeit"]["diff"], us)
assert any(x["ursache"] == "Positionieren und Verfahren" for x in us), us
werte_z, urs_z = pa.zusammenfassung(ergeb)
assert "zeit" in werte_z and urs_z
ok(f"I5 Abgleich: 12 Werte (Kalkulation berechnet/geschätzt ↔ Maschine ermittelt/fehlt), Zeitabweichung "
   f"{w['zeit']['diff']:+.1f} s zerlegt: {pa.ursache_text(us, 3)}")

# ------------------------------------------------------------------ I6 Gegenprobe
def faelle(faktoren):
    return [(dict(programm=f"G{i}", gewicht=1.0), 10.0, 10.0 * x) for i, x in enumerate(faktoren)]


gut = ll.validieren(faelle([1.2, 1.21, 1.19, 1.2, 1.22, 1.18]))
assert gut["besser"] and gut["fehler_nachher"] < gut["fehler_vorher"] and gut["programme"] == 6, gut
rausch = ll.validieren(faelle([0.6, 1.5, 0.7, 1.4, 1.0, 0.65, 1.45]))
assert rausch["besser"] is False, rausch
assert ll.validieren(faelle([1.2]))["besser"] is None
v = dict(status="ok", anwendbar=True, faktor=1.0, n=12, programme=7, streuung=0.4, preiswirkung=0.0,
         validierung=rausch, quelle=ll.Q_MASCHINE, schluessel=("T11", "Stahl"))
try:
    ll.freigeben(db, v, "test")
    raise AssertionError("Freigabe ohne Bestätigung trotz schlechter Gegenprobe")
except ll.BestaetigungNoetig as ex:
    assert "Gegenprobe" in str(ex)
ok(f"I6 Gegenprobe: gleichmäßig {gut['fehler_vorher']:.1f} → {gut['fehler_nachher']:.1f} %, Rauschen nicht besser → "
   "Freigabe nur mit Bestätigung")

# ------------------------------------------------------------------ I7 Zeitmodell je Konturklasse
rnd = random.Random(1)
zt = []
for i in range(12):
    g, mi, k, n = rnd.uniform(500, 3000), rnd.uniform(100, 800), rnd.uniform(20, 300), rnd.randint(2, 40)
    y = (g / 1000 / 8 * 60 + mi / 1000 / 4 * 60 + k / 1000 / 1.5 * 60 + n * 0.4) * rnd.uniform(0.98, 1.02)
    mk = {f"mm_{c}": md.wert(x, "mm") for c, x in (("gross", g), ("mittel", mi), ("klein", k))}
    mk["laser_an_s"] = md.wert(y, "s")
    zt.append(dict(programm=f"Z{i}", maschine="T11", werkstoff="St37", wand=2.0, einstiche=n, merkmale=mk))
(mo,) = zm.modelle(zt)
assert mo["status"] == "ok" and abs(mo["vorschub"]["gross"] - 8) < 0.5 and abs(mo["vorschub"]["klein"] - 1.5) < 0.2
assert abs(mo["einstich_s"] - 0.4) < 0.1 and mo["fehler_pct"] < 3, mo
assert zm.modelle(zt[:2])[0]["status"] == "zu wenig Daten"
ok("I7 Zeitmodell: " + zm.text(mo))

# ------------------------------------------------------------------ I8 Genauigkeitsbewertung
k = db.kontext()
pos = next(p for p in db.positionen(aid) if p.get("pos") == 10)
leer = pg.bewertung(dict(pos, profil_id="gibt es nicht"), k, list(teile.values()))
assert leer["bereiche"][-1]["stufe"] == pg.KEINE and leer["vergleichbar"] == 0
cam = pg.bewertung(pos, k, list(teile.values()))
assert cam["cam"] >= 1 and cam["gemessen"] == 0 and cam["bereiche"][-1]["stufe"] == pg.GERING, cam
gem_teile = [dict(teile["P10"], programm=f"M{i}", teil_nr=1, zeiten_gemessen={"konturen": 9.0}) for i in range(10)]
sehr = pg.bewertung(pos, k, gem_teile, {(t["programm"], 1): 4.0 for t in gem_teile})
assert sehr["bereiche"][-1]["stufe"] == pg.SEHR_GUT and sehr["gemessen"] == 10
nur_cam = [dict(t, zeiten_gemessen=None) for t in gem_teile]
assert pg.bewertung(pos, k, nur_cam, {})["bereiche"][-1]["stufe"] == pg.GERING, "nie sehr gut ohne Messung"
grob = pg.bewertung(pos, k, gem_teile, {(t["programm"], 1): 35.0 for t in gem_teile})
assert grob["bereiche"][-1]["stufe"] == pg.GERING
assert "gemessene" in pg.kurz(sehr) and cam["fehlt"]
ok("I8 Genauigkeit: ohne Daten „keine Produktionsdaten“, nur CAM „gering“, 10 gemessene ±4 % „sehr gut“, ±35 % "
   "„gering“")

# ------------------------------------------------------------------ I9 Fenster
neu = tmp / "neu"
neu.mkdir()
bb.bpf(neu / "Teil-2.bpf", name="Teil-2", bohrungen=4)
(neu / "P11.lst").write_text(lb.lst("P11", datum=datum, verbrauch=VERBRAUCH, nc_voll=True), encoding="cp1252")
gesehen = {}


def bedienen(d):
    gesehen["reiter"] = [d.reiter.tabText(i) for i in range(d.reiter.count())]
    gesehen["k2"] = set(d.kacheln2.kacheln)
    d.importieren([neu / "Teil-2.bpf", neu / "P11.lst", neu / "nicht_lesbar.txt"], warten=True)
    gesehen["status"] = d.status.text()
    gesehen["bpf"] = d.kacheln2.kacheln["bpf"].wert.text()
    r = next(i for i, t in enumerate(d.teile) if t["programm"] == "Teil-2")
    d.ptab.selectRow(r)
    gesehen["merkmale"] = d.mtab.rowCount()
    r = next(i for i, z in enumerate(d.v_zeilen) if z["teil"]["programm"] == "P10")
    d.vtab.selectRow(r)
    gesehen["abgleich"] = (d.atab.rowCount(), d.utab.rowCount())
    gesehen["protokoll"] = d.itab.rowCount()     # Kopie (gleiche Prüfsumme) nur einmal
    gesehen["lern"] = d.ltab.rowCount()
    d.zeige_reiter("Genauigkeit")
    gesehen["genau"] = d.gtab.rowCount()


f.lernsystem(dialog=bedienen)
assert gesehen["reiter"] == list(lst_dashboard.REITER), gesehen["reiter"]
assert {"bpf", "qualitaet", "schritte", "genauigkeit", "fortschritt", "modelle"} <= gesehen["k2"]
assert "2 Maschinendateien neu gelesen" in gesehen["status"] and gesehen["bpf"] == "2", gesehen
assert gesehen["merkmale"] > 20 and gesehen["abgleich"][0] == len(pa.PARAMETER) and gesehen["abgleich"][1] >= 1
assert gesehen["protokoll"] == 5 and gesehen["lern"] >= 1 and gesehen["genau"] >= 4, gesehen
ok("I9 Fenster: Reiter " + ", ".join(gesehen["reiter"]) + "; Import von LST+BPF im Hintergrund, Maschinendaten "
   "und Abgleich des gewählten Teils")

# ------------------------------------------------------------------ I10 KI
ctx = ki_agenten.Kontext(db, aid)
bf = ki_agenten.ProduktionsKI().pruefen(ctx)
assert any("Datenbasis der Bearbeitungszeit" in x["text"] for x in bf), bf
ue = ki_agenten.ProduktionsKI().uebersicht(db)
assert isinstance(ue, list)
pe = ki_kalkulation.preis_erklaeren(ctx)
assert pe is None or "Datenbasis Bearbeitungszeit" in pe["text"], pe
ok("I10 KI: Produktions-KI nennt die Datenbasis je Position, Preis erklären ebenso")

# ------------------------------------------------------------------ Tempo
viele = tmp / "viele"
viele.mkdir()
for i in range(300):
    (viele / f"V{i}.lst").write_text(lb.lst(f"V{i}", weg=1978.5 + i, verbrauch=VERBRAUCH, nc_voll=True),
                                     encoding="cp1252")
    if i % 3 == 0:
        bb.bpf(viele / f"B{i}.bpf", name=f"B{i}", laenge=300.0 + i)
t0 = time.perf_counter()
erg = pl.ordner_einlesen(db, viele)
t1 = time.perf_counter()
assert erg["neu"] == 400 and not erg["fehler"], erg
assert pl.ordner_einlesen(db, viele)["bekannt"] == 400
ok(f"Tempo: 300 LST + 100 BPF in {t1 - t0:.1f} s gelesen und ausgewertet, zweiter Lauf ohne neue Datei")

# ------------------------------------------------------------------ I11 echte Dateien (optional)
echt = os.environ.get("RL_MASCHINENDATEN")
if echt and Path(echt).is_dir():
    n = 0
    for p in sorted(Path(echt).iterdir()):
        if md.format_von(p):
            r = md.analysieren(p)
            assert not r["fehler"], r["fehler"]
            n += len(r["teile"])
    ok(f"I11 echte Dateien: {n} Teile aus {echt} ohne Fehler ausgewertet")
f.close()
print("Alle Tests Produktionsdaten-Intelligenz bestanden.")
