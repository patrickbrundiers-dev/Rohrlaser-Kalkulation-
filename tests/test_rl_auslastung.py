"""Prüft das eigene Programm „Rohrlaser Auslastung“ (programm/rl_auslastung, Patrick 11.11.2026):

- R1 Laufzeit in allen Schreibweisen lesen (1 Stunde 30 Minuten, 90 Minuten, 1:30, 1,5 h …), anzeigen, Fehlertexte
- R2 Datenbank: Aufträge anlegen/ändern/prüfen, Start/Stopp, Fertigmeldung, wieder öffnen, Maschinen, Zusatzfelder,
  zweiter Platz sieht Änderungen (stand), Sicherung, neuere Datei wird abgelehnt
- R3 Rechnung: Einlastung nur der offenen Aufträge mit Restlaufzeit, kein Tag über seiner Kapazität, Terminrisiko,
  tatsächliche Stunden vergangener Wochen, Soll und Ist je Auftrag und Maschine
- R4 CSV einlesen (neu, geändert, unverändert, fertig bleibt, Fehlerzeilen, neue Maschine, Zusatzfeld), speichern und
  wieder einlesen; Übergabedatei aus der Kalkulation
- R5 Fenster: Auftragsliste, Dialoge, Auslastung mit Wochenbalken und Plantafel, Soll und Ist, Einstellungen, PDF
- R6 unabhängig: das Programm lädt aus der Kalkulation nur einlastung, wochen, feiertage, stil, auslastung_grafik

Aufruf: python tests/test_rl_auslastung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rl_auslastung import austausch, daten, laufzeit, ort, rechnung  # noqa: E402
from rl_auslastung.fenster import Hauptfenster  # noqa: E402
from rohrlaser import einlastung  # noqa: E402


def ok(t):
    print("OK:", t)


def fehler(f, *a, **k):
    try:
        f(*a, **k)
    except (daten.Fehler, laufzeit.Fehler) as e:
        return str(e)
    raise AssertionError("kein Fehler gemeldet")


D = datetime.date
HEUTE = D(2026, 11, 11)             # Mittwoch
tmp = Path(tempfile.mkdtemp())

# ---------------------------------------------------------------- R1 Laufzeit
for text, minuten in (("1 Stunde 30 Minuten", 90), ("90 Minuten", 90), ("1:30", 90), ("1,5 h", 90), ("1.5 Std", 90),
                      ("1h30", 90), ("1 h 30 min", 90), ("1 Std. und 30 Min.", 90), ("90 min", 90), ("90'", 90),
                      ("90", 90), ("1,5", 90), ("2 Stunden", 120), ("45 Min", 45), ("0:45", 45), ("1:30:00", 90),
                      ("2 Tage 3 h", 3060), ("1 STUNDE 30 MINUTEN", 90), ("  90 m ", 90), ("30 sek", 1),
                      ("1 h 30 m 20 s", 90), ("12 h", 720)):
    assert laufzeit.lesen(text) == minuten, (text, laufzeit.lesen(text))
assert laufzeit.lesen("") is None and laufzeit.lesen(None) is None
assert laufzeit.lesen("2", "h") == 120 and laufzeit.lesen("2") == 2 and laufzeit.lesen("2 min", "h") == 2
for text in ("abc", "1 30", "1:75", "1 x", "h", "1 h zwei"):
    assert fehler(laufzeit.lesen, text), text
assert "1 Stunde 30 Minuten" in fehler(laufzeit.lesen, "abc")          # die Meldung nennt Beispiele
assert [laufzeit.text(90, f) for f in ("hm", "uhr", "dez", "min")] == ["1 h 30 min", "1:30 h", "1,50 h", "90 min"]
assert laufzeit.text(120) == "2 h" and laufzeit.text(45) == "45 min" and laufzeit.text(None) == ""
assert laufzeit.text(-20) == "-20 min" and laufzeit.text(0) == "0 min"
assert laufzeit.lang(90) == "1 Stunde 30 Minuten (90 Minuten)" and laufzeit.lang(1) == "1 Minute"
for f in laufzeit.FORMEN:                                               # jede Anzeige lässt sich wieder einlesen
    for n in (1, 45, 60, 90, 725, 3000):
        assert laufzeit.lesen(laufzeit.text(n, f)) == n, (f, n)
ok("R1 Laufzeit: alle Schreibweisen ergeben dieselben Minuten, Anzeige in vier Formen, verständliche Fehler")

# ---------------------------------------------------------------- R2 Datenbank
db = daten.Daten(tmp / "Daten" / "Auslastung.db")
assert [m["name"] for m in db.maschinen()] == ["LT7", "T03", "T11"]
a1 = db.auftrag_speichern(dict(nummer="A-1", kunde="Kramer", maschine="LT7", kalk_min=600, liefertermin=D(2026, 11, 13)))
a2 = db.auftrag_speichern(dict(nummer="A-2", maschine="LT7", kalk_min=960, liefertermin="17.11.2026"))
a3 = db.auftrag_speichern(dict(nummer="A-3", maschine="T03", kalk_min=90))
assert db.auftrag(a2)["liefertermin"] == "2026-11-17" and db.auftrag(a3)["liefertermin"] is None
assert db.auftrag(nummer="A-1")["id"] == a1 and db.auftrag(a1)["status"] == daten.OFFEN
assert "gibt es schon" in fehler(db.auftrag_speichern, dict(nummer="A-1", maschine="LT7", kalk_min=5))
assert fehler(db.auftrag_speichern, dict(nummer="", maschine="LT7", kalk_min=5))
assert fehler(db.auftrag_speichern, dict(nummer="A-9", maschine="LT7", kalk_min=0))
assert fehler(db.auftrag_speichern, dict(nummer="A-9", maschine="", kalk_min=5))
assert fehler(db.auftrag_speichern, dict(nummer="A-9", maschine="LT7", kalk_min=5, liefertermin="32.13.2026"))
assert len(db.auftraege()) == 3
db.auftrag_speichern(dict(db.auftrag(a1), kunde="Metallbau Kramer", kalk_min=630))
assert db.auftrag(a1)["kunde"] == "Metallbau Kramer" and db.auftrag(a1)["kalk_min"] == 630
# Start/Stopp sammelt die gelaufene Zeit, auch über mehrere Abschnitte
t0 = datetime.datetime(2026, 11, 11, 6, 0)
db.starten(a1, t0)
assert db.auftrag(a1)["status"] == daten.LAEUFT
assert db.gelaufen(db.auftrag(a1), t0 + datetime.timedelta(minutes=50)) == 50
assert db.stoppen(a1, t0 + datetime.timedelta(minutes=80)) == 80
db.starten(a1, t0 + datetime.timedelta(hours=3))
assert db.stoppen(a1, t0 + datetime.timedelta(hours=3, minutes=40)) == 120 and db.auftrag(a1)["start_am"] is None
assert fehler(db.fertig_melden, a1, 0) and fehler(db.fertig_melden, a1, None)
db.fertig_melden(a1, 655, D(2026, 11, 10))
f1 = db.auftrag(a1)
assert (f1["status"], f1["ist_min"], f1["fertig_am"]) == (daten.FERTIG, 655, "2026-11-10")
assert fehler(db.starten, a1)
assert [a["nummer"] for a in db.auftraege((daten.OFFEN, daten.LAEUFT))] == ["A-2", "A-3"]
db.wieder_oeffnen(a1)
assert db.auftrag(a1)["status"] == daten.OFFEN and db.auftrag(a1)["gelaufen_min"] == 655
db.fertig_melden(a1, 655, D(2026, 11, 10))
# Maschinen
db.maschine_speichern("T20", "7,5")
assert fehler(db.maschine_speichern, "T20") and fehler(db.maschine_speichern, "") and fehler(db.maschine_speichern, "X", 30)
db.maschine_speichern("LT8", 8, True, alt="LT7")                       # umbenennen zieht die Aufträge mit
assert db.auftrag(a2)["maschine"] == "LT8" and "LT7" not in [m["name"] for m in db.maschinen()]
db.maschine_speichern("LT7", 8, True, alt="LT8")
assert "Aufträge" in fehler(db.maschine_loeschen, "LT7")
db.maschine_loeschen("T20")
db.maschine_speichern("T11", 8, False, alt="T11")
assert [m["name"] for m in db.maschinen(nur_aktive=True)] == ["LT7", "T03"]
db.maschine_speichern("T11", 8, True, alt="T11")
# Zusatzfelder: Platz für Erweiterungen ohne Umbau
db.zusatzfeld_speichern("Material")
db.zusatzfeld_speichern("Stückzahl")
assert fehler(db.zusatzfeld_speichern, "material") and fehler(db.zusatzfeld_speichern, "Kunde")
db.auftrag_speichern(dict(db.auftrag(a2), zusatz={"Material": "S235", "Stückzahl": "40", "gibt es nicht": "x"}))
assert db.auftrag(a2)["zusatz"] == {"Material": "S235", "Stückzahl": "40"}
db.zusatzfeld_speichern("Werkstoff", alt="Material")
assert db.auftrag(a2)["zusatz"]["Werkstoff"] == "S235" and db.zusatz_gefuellt("Werkstoff") == 1
db.zusatzfeld_loeschen("Stückzahl")
assert db.auftrag(a2)["zusatz"] == {"Werkstoff": "S235"}
db.zusatzfeld_speichern("Material", alt="Werkstoff")
# zweiter Platz (zweite Verbindung auf dieselbe Datei)
platz2 = daten.Daten(tmp / "Daten" / "Auslastung.db")
s0 = platz2.stand()
db.auftrag_speichern(dict(nummer="A-4", maschine="T03", kalk_min=300, liefertermin=D(2026, 11, 20)))
assert platz2.stand() != s0 and platz2.auftrag(nummer="A-4")["kalk_min"] == 300
platz2.schliessen()
ziel = db.sichern()
assert ziel.exists() and ziel.parent.name == "Sicherung" and db.sichern() == ziel
db.con.execute(f"PRAGMA user_version = {daten.SCHEMA + 1}")
assert "neueren Programmversion" in fehler(daten.Daten, db.pfad)
db.con.execute(f"PRAGMA user_version = {daten.SCHEMA}")
assert db.einstellung("laufzeit_form") == "hm" and db.zahl("nutzungsgrad") == 100
db.einstellung_setzen("vorlauf_tage", 1)
assert db.zahl("vorlauf_tage") == 1
db.einstellung_setzen("vorlauf_tage", 0)
# Papierkorb (P3): gelöscht ist weg aus allen Listen, lässt sich 30 Tage zurückholen, danach endgültig entfernt
pk1 = db.auftrag_speichern(dict(nummer="PK-1", maschine=db.maschinen()[0]["name"], kalk_min=60))
pk2 = db.auftrag_speichern(dict(nummer="PK-2", maschine=db.maschinen()[0]["name"], kalk_min=60))
db.auftrag_loeschen(pk1, datetime.datetime(2026, 11, 1, 8, 0))
db.auftrag_loeschen(pk2, datetime.datetime(2026, 10, 1, 8, 0))
assert db.auftrag(pk1) is None and db.auftrag(nummer="PK-1") is None and db.im_papierkorb("PK-1")
assert "PK-1" not in [a["nummer"] for a in db.auftraege()] and [a["nummer"] for a in db.papierkorb()] == ["PK-1", "PK-2"]
assert "Papierkorb" in fehler(db.auftrag_speichern, dict(nummer="PK-1", maschine=db.maschinen()[0]["name"], kalk_min=5))
(tmp / "pk.csv").write_text("Auftragsnummer;Maschine;Kalkulierte Laufzeit\nPK-1;LT7;1 h\n", encoding="utf-8")
vorschau = austausch.lesen(db, tmp / "pk.csv")
assert not vorschau["neu"] and "Papierkorb" in vorschau["uebersprungen"][0]
assert db.papierkorb_leeren(D(2026, 11, 11)) == 1 and [a["nummer"] for a in db.papierkorb()] == ["PK-1"]
db.zurueckholen(pk1)
assert db.auftrag(pk1)["nummer"] == "PK-1" and not db.papierkorb()
db.auftrag_loeschen(pk1)
assert db.papierkorb_leeren(alle=True) == 1 and not db.papierkorb()
# Datei aus Version 1.0 (Schema 1): wird beim Öffnen nachgezogen, die Daten bleiben
alt = tmp / "alt.db"
con = sqlite3.connect(alt)
con.executescript(daten.SCHRITTE[0] + "PRAGMA user_version = 1;")
con.execute("INSERT INTO maschinen (name, stunden_tag, aktiv, reihenfolge) VALUES ('M1', 8, 1, 1)")
con.commit()
con.close()
db_alt = daten.Daten(alt)
assert db_alt.con.execute("PRAGMA user_version").fetchone()[0] == daten.SCHEMA >= 2
assert {m["name"]: m for m in db_alt.maschinen()}["M1"]["sperrtage"] == ""
neu_id = db_alt.auftrag_speichern(dict(nummer="X-1", maschine="M1", kalk_min=30))
assert db_alt.auftrag(neu_id)["vorrang"] == 0
db_alt.schliessen()
ok("R2 Datenbank: Aufträge, Start/Stopp, Fertigmeldung, Maschinen, Zusatzfelder, zweiter Platz, Sicherung, Papierkorb, "
   "Datei aus Version 1.0")

# ---------------------------------------------------------------- R3 Rechnung
aus, ein = rechnung.einlasten(db, HEUTE, 8)
plan = {a["nummer"]: a for a in ein["auftraege"]}
assert set(plan) == {"A-2", "A-3", "A-4"}                              # fertige Aufträge belegen nichts mehr
assert abs(plan["A-2"]["h"] - 16.0) < 1e-9
for (m, tag), belegt in ein["belegt"].items():
    assert sum(belegt.values()) <= ein["kapazitaet"][(m, tag)] + 1e-9
assert abs(sum(sum(b.values()) for b in ein["belegt"].values()) - (960 + 90 + 300) / 60) < 1e-6
assert plan["A-2"]["start"] == HEUTE and plan["A-2"]["fertig"] == D(2026, 11, 12)      # 16 h = Mi + Do
assert plan["A-2"]["risiko"] == einlastung.OK and plan["A-2"]["puffer"] == 3
assert plan["A-3"]["risiko"] == einlastung.OHNE
assert plan["A-4"]["fertig"] == HEUTE                                  # auf T03: mit Termin vor dem ohne Termin
# schon gelaufene Zeit verkürzt die Restlaufzeit
db.starten(a2, datetime.datetime(2026, 11, 11, 6, 0))
db.stoppen(a2, datetime.datetime(2026, 11, 11, 10, 0))
aus, ein = rechnung.einlasten(db, HEUTE, 8)
assert abs({a["nummer"]: a for a in ein["auftraege"]}["A-2"]["h"] - 12.0) < 1e-9
# enger Termin -> überschritten; Betriebsruhe und Nutzungsgrad wirken auf die Kapazität
a5 = db.auftrag_speichern(dict(nummer="A-5", maschine="T11", kalk_min=40 * 60, liefertermin=D(2026, 11, 13)))
db.einstellung_setzen("betriebsruhe", "12.11.2026")
db.einstellung_setzen("nutzungsgrad", 50)
aus, ein = rechnung.einlasten(db, HEUTE, 8)
assert ein["kapazitaet"][("T11", D(2026, 11, 12))] == 0 and ein["kapazitaet"][("T11", HEUTE)] == 4.0
p5 = {a["nummer"]: a for a in ein["auftraege"]}["A-5"]
assert p5["risiko"] == einlastung.UEBER and p5["fertig"] > D(2026, 11, 13)
assert ein["risiko"][einlastung.UEBER] == 1 and einlastung.kritische(ein)[0]["nummer"] == "A-5"
db.einstellung_setzen("betriebsruhe", "")
db.einstellung_setzen("nutzungsgrad", 100)
db.auftrag_loeschen(a5)
# tatsächliche Stunden vergangener Wochen und Soll/Ist
for nr, m, kalk, ist, tag in (("F-1", "LT7", 600, 660, D(2026, 11, 4)), ("F-2", "T03", 900, 810, D(2026, 11, 5)),
                               ("F-3", "LT7", 300, 300, D(2026, 10, 20)), ("F-4", "T03", 100, 100, D(2025, 12, 1))):
    db.fertig_melden(db.auftrag_speichern(dict(nummer=nr, maschine=m, kalk_min=kalk)), ist, tag)
aus, ein = rechnung.einlasten(db, HEUTE, 8)
gem = rechnung.gemessen(db, aus, HEUTE, 4)
assert gem["montage"] == [D(2026, 10, 12), D(2026, 10, 19), D(2026, 10, 26), D(2026, 11, 2)]
assert gem["stunden"][("LT7", D(2026, 11, 2))] == 11.0 and gem["stunden"][("T03", D(2026, 11, 2))] == 13.5
assert gem["stunden"][("LT7", D(2026, 10, 19))] == 5.0 and gem["kapazitaet"][("LT7", D(2026, 11, 2))] == 40.0
assert gem["laeufe"] == 3                       # A-1 (10.11.) liegt in der laufenden Woche, F-4 im Vorjahr
si = rechnung.soll_ist(db)
assert si["gesamt"]["anzahl"] == 5 and si["gesamt"]["kalk_min"] == 630 + 600 + 900 + 300 + 100
lt7 = next(s for s in si["maschinen"] if s["maschine"] == "LT7")
assert (lt7["anzahl"], lt7["kalk_min"], lt7["ist_min"], lt7["diff_min"]) == (3, 1530, 1615, 85)
assert abs(lt7["diff_prozent"] - 85 / 1530 * 100) < 1e-9
f2 = next(z for z in si["zeilen"] if z["nummer"] == "F-2")
assert f2["diff_min"] == -90 and abs(f2["diff_prozent"] + 10) < 1e-9
assert rechnung.soll_ist(db, D(2026, 11, 1), D(2026, 11, 30))["gesamt"]["anzahl"] == 3
assert rechnung.abweichung(600, None) == (None, None)
ok("R3 Rechnung: Einlastung der offenen Aufträge mit Restlaufzeit, Terminrisiko, gemessene Wochen, Soll und Ist")

# ---------------------------------------------------------------- R4 CSV
csv1 = tmp / "ein.csv"
csv1.write_text(
    "Auftrag;Kunde;Maschine;Laufzeit;Termin;Material;Farbe\n"
    "C-1;Voss;T11;1 Stunde 30 Minuten;27.11.2026;S355;rot\n"
    "C-2;Ohm;T50;90 Minuten;;1.4301;\n"
    "A-2;;LT7;16:00;17.11.2026;S235;\n"                      # unverändert (Kunde leer wie bisher)
    "A-3;Hesse;T03;2,5 h;01.12.2026;;\n"                      # geändert
    "A-1;Kramer;LT7;5 h;;;\n"                                # fertig: bleibt
    "C-3;X;T11;abc;;;\n"                                     # Fehler
    ";Y;T11;1 h;;;\n"                                        # Fehler
    "C-1;Doppelt;T11;1 h;;;\n", encoding="utf-8")
e = austausch.lesen(db, csv1)
assert [a["nummer"] for a in e["neu"]] == ["C-1", "C-2"] and [a["nummer"] for a in e["geaendert"]] == ["A-3"]
assert e["neu"][0]["kalk_min"] == 90 and e["neu"][1]["kalk_min"] == 90 and e["gleich"] == 1
assert e["neu"][0]["zusatz"] == {"Material": "S355"} and e["spalten_fremd"] == ["Farbe"]
assert e["maschinen_neu"] == ["T50"] and len(e["uebersprungen"]) == 1 and len(e["fehler"]) == 3
assert "Zeile 7" in e["fehler"][0] and "T50" in austausch.zusammenfassung(e)
assert db.auftrag(nummer="C-1") is None                              # lesen() speichert noch nichts
assert austausch.uebernehmen(db, e) == 3
c1, a3n = db.auftrag(nummer="C-1"), db.auftrag(a3)
assert (c1["kalk_min"], c1["liefertermin"], c1["zusatz"]["Material"]) == (90, "2026-11-27", "S355")
assert (a3n["kalk_min"], a3n["kunde"], a3n["liefertermin"]) == (150, "Hesse", "2026-12-01")
assert db.auftrag(a1)["status"] == daten.FERTIG and "T50" in [m["name"] for m in db.maschinen()]
e = austausch.lesen(db, csv1)
assert not e["neu"] and not e["geaendert"] and e["gleich"] == 4       # zweimal einlesen ändert nichts
(tmp / "komma.csv").write_bytes("Nr,Maschine,Zeit\nK-1,LT7,45 min\n".encode("cp1252"))
assert austausch.lesen(db, tmp / "komma.csv")["neu"][0]["kalk_min"] == 45
(tmp / "ohne.csv").write_text("Auftrag;Kunde\nX;Y\n", encoding="utf-8")
assert "Maschine" in austausch.lesen(db, tmp / "ohne.csv")["fehler"][0]
# speichern und in eine leere Datenbank wieder einlesen: gleiche Aufträge, auch die fertigen mit Ist-Zeit
for form in laufzeit.FORMEN:
    aus_csv = austausch.schreiben(db, tmp / f"aus-{form}.csv", form=form)
    db2 = daten.Daten(tmp / f"zwei-{form}.db")
    db2.zusatzfeld_speichern("Material")
    e2 = austausch.lesen(db2, aus_csv)
    assert not e2["fehler"] and len(e2["neu"]) == len(db.auftraege()), (form, e2["fehler"])
    austausch.uebernehmen(db2, e2)
    for a in db.auftraege():
        b = db2.auftrag(nummer=a["nummer"])
        assert all(a[k] == b[k] for k in ("maschine", "kalk_min", "liefertermin", "kunde", "ist_min", "fertig_am")), a
        assert b["status"] == (daten.FERTIG if a["status"] == daten.FERTIG else daten.OFFEN)
        assert b["zusatz"].get("Material", "") == a["zusatz"].get("Material", "")
    db2.schliessen()
ok("R4 CSV: neu, geändert, unverändert, fertig bleibt, Fehlerzeilen, neue Maschine, Zusatzfeld; speichern und einlesen")

# ---------------------------------------------------------------- R5 Fenster
app = QApplication.instance() or QApplication([])
f = Hauptfenster(db, heute=HEUTE)
f.resize(1300, 800)
f.show()
app.processEvents()
kopf = [f.liste.horizontalHeaderItem(c).text() for c in range(f.liste.columnCount())]
assert kopf[:6] == ["Auftragsnummer", "Kunde", "Maschine", "Kalkulierte Laufzeit", "Liefertermin", "Status"]
assert kopf[-1] == "Material" and "Tatsächliche Laufzeit" in kopf
offen = len(db.auftraege((daten.OFFEN, daten.LAEUFT)))
assert f.liste.rowCount() == offen and f.liste.isColumnHidden(8) and not f.liste.isColumnHidden(7)
assert not f.k_aendern.isEnabled() and not f.k_fertig.isEnabled() and f.k_neu.isEnabled()
f.suche.setText("voss")
assert f.liste.rowCount() == 1 and f.liste.item(0, 0).text() == "C-1"
f.suche.setText("")
# neuer Auftrag über den Dialog, Laufzeit in Worten; die Rückmeldung zeigt, wie sie verstanden wurde
d = f.neu(zeigen=False)
d.nummer.setText("N-1")
d.maschine.setCurrentText("T11")
d.kalk.eingabe.setText("1 Stunde 30 Minuten")
assert d.kalk.echo.text() == "= 1 Stunde 30 Minuten (90 Minuten)"
d.kalk.eingabe.setText("neunzig")
assert "keine Laufzeit" in d.kalk.echo.text() and not d.speichern() and d.fehler.text()
d.kalk.eingabe.setText("90 Minuten")
d.zusatz["Material"].setText("S235")
assert d.speichern()
n1 = db.auftrag(nummer="N-1")
assert n1["kalk_min"] == 90 and n1["zusatz"]["Material"] == "S235" and n1["liefertermin"]
d = f.neu(zeigen=False)                                            # doppelte Nummer: Meldung im Dialog, nichts gespeichert
d.nummer.setText("N-1")
d.kalk.eingabe.setText("10")
assert not d.speichern() and "gibt es schon" in d.fehler.text()
f.laden()
f.show()
app.processEvents()
assert f.waehlen(n1["id"]) and f.k_uhr.text() == "Start" and f.k_uhr.isEnabled() and not f.k_oeffnen.isVisible()
f.uhr_schalten()                                                   # P1: ein Knopf für Start und Stopp
assert f.waehlen(n1["id"]) and f.k_uhr.text() == "Stopp" and db.auftrag(n1["id"])["start_am"]
f.uhr_schalten()
assert f.waehlen(n1["id"]) and f.k_uhr.text() == "Start" and not db.auftrag(n1["id"])["start_am"]
f.uhr_schalten()
f.waehlen(n1["id"])
assert "läuft" in f.liste.item(f.liste.currentRow(), 5).text()
d = f.aendern(zeigen=False)                                        # Ändern zeigt die Laufzeit in der eingestellten Form
assert d.kalk.eingabe.text() == "1 h 30 min" and d.nummer.text() == "N-1"
d.kalk.eingabe.setText("2:15")
assert d.speichern() and db.auftrag(n1["id"])["kalk_min"] == 135
f.laden()
f.waehlen(n1["id"])
d = f.fertig_melden(zeigen=False)                                  # stoppt die Uhr und schlägt die gestoppte Zeit vor
assert db.auftrag(n1["id"])["start_am"] is None
d.ist.eingabe.setText("")
assert not d.speichern() and d.fehler.text()
d.ist.eingabe.setText("2 h 40 min")
assert d.speichern() and db.auftrag(n1["id"])["ist_min"] == 160 and db.auftrag(n1["id"])["status"] == daten.FERTIG
f.laden()
assert f.liste.rowCount() == offen                                 # fertig: nicht mehr bei den offenen
f.filter.setCurrentIndex(1)
assert f.liste.isColumnHidden(7) and not f.liste.isColumnHidden(8) and f.waehlen(n1["id"])
r = f.liste.currentRow()
assert f.liste.item(r, 8).text() == "2 h 40 min" and f.liste.item(r, 9).text().startswith("+25 min (+19 %")
assert f.k_oeffnen.isVisible() and not f.k_fertig.isVisible() and not f.k_uhr.isVisible()
f.wieder_oeffnen()
assert db.auftrag(n1["id"])["status"] == daten.OFFEN
f.filter.setCurrentIndex(2)
assert f.liste.rowCount() == len(db.auftraege()) and f.waehlen(n1["id"])
# P4 Reihenfolge von Hand: vorziehen, zurückstellen, wieder nach Liefertermin
db.auftrag_speichern(dict(db.auftrag(n1["id"]), kalk_min=600))     # Rest > 0, damit er eingeplant wird
f.laden()
f.waehlen(n1["id"])
assert not f.a_termin.isEnabled()
f.reihenfolge(1)
assert db.auftrag(n1["id"])["vorrang"] > 0 and f.waehlen(n1["id"]) and f.a_termin.isEnabled()
assert "vorgezogen" in f.liste.item(f.liste.currentRow(), 5).text()
assert rechnung.arbeitsliste(f.ein, n1["maschine"])[0]["nummer"] == "N-1"
f.reihenfolge(-1)
assert db.auftrag(n1["id"])["vorrang"] < 0 and f.waehlen(n1["id"])
assert "zurückgestellt" in f.liste.item(f.liste.currentRow(), 5).text()
assert rechnung.arbeitsliste(f.ein, n1["maschine"])[-1]["nummer"] == "N-1"
f.reihenfolge(0)
assert db.auftrag(n1["id"])["vorrang"] == 0 and f.waehlen(n1["id"])
# P3 Papierkorb: Löschen ohne Rückfrage, Zurückholen
alle = f.liste.rowCount()
f.loeschen()
assert db.auftrag(n1["id"]) is None and db.auftrag(nummer="N-1") is None and f.liste.rowCount() == alle - 1
assert "Papierkorb" in f.statusBar().currentMessage()
pk = f.papierkorb(zeigen=False)
assert pk.liste.rowCount() == len(db.papierkorb()) >= 1 and pk.k_zurueck.isEnabled()
zeile = [pk.liste.item(r, 0).text() for r in range(pk.liste.rowCount())].index("N-1")
pk.liste.selectRow(zeile)
assert pk.zurueckholen() == n1["id"] and db.auftrag(n1["id"])["nummer"] == "N-1" and f.liste.rowCount() == alle
f.waehlen(n1["id"])
f.loeschen()
f.filter.setCurrentIndex(0)
aus_csv = f.csv_speichern(tmp / "liste.csv")
assert Path(aus_csv).read_text(encoding="utf-8-sig").count("\n") == f.liste.rowCount() + 1
(tmp / "neu.csv").write_text("Auftragsnummer;Maschine;Kalkulierte Laufzeit;Liefertermin\nG-1;LT7;20 h;13.11.2026\n"
                             "G-2;LT7;1 Tag 6 h;16.11.2026\n", encoding="utf-8")
assert len(f.csv_einlesen(tmp / "neu.csv", fragen=False)["neu"]) == 2 and db.auftrag(nummer="G-2")["kalk_min"] == 1800
# Auslastung: Wochenbalken mit gemessenen Wochen, Plantafel, Terminrisiko, Woche wählen
f.reiter.setCurrentIndex(1)
app.processEvents()
assert [z["maschine"] for z in f.balken.zeilen] == f.ein["maschinen"]
spalten = f.balken.zeilen[0]["spalten"]
assert [s["art"] for s in spalten[:4]] == ["ist"] * 4 and len([s for s in spalten if s["art"] == "woche"]) == 8
assert spalten[3]["ist"] == 11.0 and spalten[4]["key"] == D(2026, 11, 9) and spalten[4]["kap"] == 24.0
assert "Terminrisiko" in f.info.text() and f.details.rowCount() == len(einlastung.kritische(f.ein)) >= 1
assert "G-1" in [f.details.item(r, 0).text() for r in range(f.details.rowCount())]
assert f.details.item(0, 7).text() in ("knapp", "überschritten")
f.balken.gewaehlt.emit("LT7", D(2026, 11, 16))
assert f.woche == ("LT7", D(2026, 11, 16)) and "KW 47" in f.details_titel.text() and f.details.rowCount() >= 1
f.wochen.setValue(4)
assert len(f.tafel.tage) == 28 and db.einstellung("wochen") == "4"
f.wochen.setValue(8)
f.k_risiko.click()
assert f.woche is None and "Terminrisiko" in f.details_titel.text()
f.tafel.repaint()
app.processEvents()
assert len(f.tafel.flaechen) >= len([a for a in f.ein["auftraege"] if a["stuecke"]])
pdf = f.pdf(tmp / "auslastung.pdf")
assert Path(pdf).read_bytes().startswith(b"%PDF") and Path(pdf).stat().st_size > 3000
# P6 Terminauskunft: rechnet je Maschine, speichert nichts; P7 Arbeitsliste je Maschine
stand = db.stand()
ta = f.terminauskunft(zeigen=False)
assert ta.tabelle.rowCount() == 0 and "Laufzeit eingeben" in ta.antwort.text()
ta.dauer.eingabe.setText("6 h")
assert ta.tabelle.rowCount() == len(f.ein["maschinen"]) and "Am frühesten auf" in ta.antwort.text()
erste = ta.rechnen()
assert erste[0]["fertig"] <= erste[-1]["fertig"] and erste[0]["start"] >= HEUTE and db.stand() == stand
assert {x["maschine"]: x for x in erste}["LT7"]["fertig"] > erste[0]["fertig"]      # LT7 ist am vollsten
al = f.arbeitsliste_pdf(tmp / "arbeitsliste.pdf")
assert Path(al).read_bytes().startswith(b"%PDF") and Path(al).stat().st_size > 3000
# Soll und Ist
f.reiter.setCurrentIndex(2)
assert f.si_liste.rowCount() == 5 and f.si_maschinen.rowCount() == 3 and "stimmen überein" in f.si_info.text()
assert f.si_maschinen.item(2, 0).text() == "Gesamt" and f.si_maschinen.item(0, 4).text().startswith("+1 h 25 min (+6 %")
f.zeitraum.setCurrentIndex(4)                                      # letztes Jahr: nur F-4
assert f.si_liste.rowCount() == 1 and f.si_liste.item(0, 0).text() == "F-4"
f.zeitraum.setCurrentIndex(0)
si_csv = Path(f.soll_ist_csv(tmp / "sollist.csv")).read_text(encoding="utf-8-sig")
assert "F-2;" in si_csv and "Gesamt;5;" in si_csv
assert Path(f.soll_ist_pdf(tmp / "sollist.pdf")).read_bytes().startswith(b"%PDF")
# Einstellungen
f.reiter.setCurrentIndex(3)
assert f.e_maschinen.rowCount() == len(db.maschinen()) and f.e_felder.rowCount() == 1 and str(db.pfad) in f.e_pfad.text()
f.e_form.setCurrentIndex(f.e_form.findData("uhr"))
f.e_ohne.setCurrentIndex(f.e_ohne.findData("h"))
f.e_samstag.setValue(6)
f.e_vorlauf.setValue(2)                                            # P2: gilt sofort, kein Speichern-Knopf
assert not hasattr(f, "k_speichern")
assert db.einstellung("laufzeit_form") == "uhr" and db.einstellung("ohne_einheit") == "h" and db.zahl("vorlauf_tage") == 2
assert f.ein["kapazitaet"][("LT7", D(2026, 11, 14))] == 6.0 and laufzeit.lesen("2", db.einstellung("ohne_einheit")) == 120
f.reiter.setCurrentIndex(0)
assert f.liste.item(0, 3).text().endswith(" h") and ":" in f.liste.item(0, 3).text()
f.reiter.setCurrentIndex(3)
assert f.maschine_bearbeiten(neu=True, werte=("T30", 7.5, True)) and f.e_maschinen.rowCount() == len(db.maschinen())
f.e_maschinen.selectRow(f.e_maschinen.rowCount() - 1)
# P5 Sperrtage je Maschine: der Tag hat keine Kapazität, nur an dieser Maschine
assert f.maschine_bearbeiten(werte=("T30", 7.5, True, "17.11.2026-18.11.2026; 20.11.2026"))
zeile = f.e_maschinen.rowCount() - 1
assert "17.11.2026" in f.e_maschinen.item(zeile, 3).text()
assert f.ein["kapazitaet"][("T30", D(2026, 11, 17))] == 0 and f.ein["kapazitaet"][("T30", D(2026, 11, 20))] == 0
assert f.ein["kapazitaet"][("T30", D(2026, 11, 19))] == 7.5 and f.ein["kapazitaet"][("LT7", D(2026, 11, 17))] > 0
f.e_maschinen.selectRow(zeile)
gemeldet = []
f.meldung = gemeldet.append
assert not f.maschine_bearbeiten(werte=("T30", 7.5, True, "irgendwann"))            # unlesbar: Meldung, nichts gespeichert
assert "kein Datum" in gemeldet[0] and "17.11.2026" in {m["name"]: m for m in db.maschinen()}["T30"]["sperrtage"]
del f.meldung
f.e_maschinen.selectRow(zeile)
assert f.maschine_entfernen() and "T30" not in [m["name"] for m in db.maschinen()]
assert f.feld_bearbeiten(neu=True, name="Bearbeiter") and f.e_felder.rowCount() == 2
f.e_felder.selectRow(1)
assert f.feld_bearbeiten(name="Programmierer") and [x["name"] for x in db.zusatzfelder()] == ["Material", "Programmierer"]
f.e_felder.selectRow(1)
assert f.feld_entfernen(fragen=False) and f.e_felder.rowCount() == 1
assert f.jetzt_sichern().exists()
f.reiter.setCurrentIndex(4)                                        # P8 Hilfe im Programm
hilfe_text = f.hilfe.toPlainText()
assert all(w in hilfe_text for w in ("Papierkorb", "Terminauskunft", "Arbeitsliste", "Sperrtage", "1 Stunde 30 Minuten"))
# anderer Platz speichert: der Takt lädt neu
f.reiter.setCurrentIndex(0)
vorher = f.liste.rowCount()
platz2 = daten.Daten(db.pfad)
platz2.auftrag_speichern(dict(nummer="P-2", maschine="T11", kalk_min=60))
platz2.schliessen()
f.takt()
assert f.liste.rowCount() == vorher + 1
# Datenbank an anderem Ort (gemeinsamer Ordner): wird dorthin kopiert und gemerkt
alt_basis, ort.basis = ort.basis, lambda: tmp / "programm"
gemeinsam = tmp / "gemeinsam" / "Auslastung.db"
assert f.datenbank_waehlen(gemeinsam) and f.db.pfad == gemeinsam and len(f.db.auftraege()) == vorher + 1 + 5
assert ort.datenbank() == gemeinsam and "gemeinsam" in (tmp / "programm" / ort.INI).read_text(encoding="utf-8")
os.environ["RLA_DATENBANK"] = str(tmp / "x.db")
assert ort.datenbank() == tmp / "x.db"
del os.environ["RLA_DATENBANK"]
ort.basis = alt_basis
f.close()
ok("R5 Fenster: Aufträge, Dialoge mit Laufzeit-Rückmeldung, Auslastung, Soll und Ist, Einstellungen, PDF, zweiter Platz")

# ---------------------------------------------------------------- R7 Benutzerrechte und Änderungsverlauf
chef = daten.Daten(tmp / "rechte" / "Auslastung.db", wer="Chef")
assert chef.wer == "chef" and not chef.rechte_an() and chef.rolle() == daten.VERWALTUNG      # ohne Benutzer: alles frei
assert chef.rolle("irgendwer") == daten.VERWALTUNG and chef.darf("einstellungen", "irgendwer")
assert "Verwaltung" in fehler(chef.benutzer_speichern, "meier", daten.WERKSTATT)             # erster: Verwaltung
chef.benutzer_speichern("Chef", daten.VERWALTUNG)
chef.benutzer_speichern("Meier", daten.WERKSTATT)
chef.benutzer_speichern("planer", daten.PLANUNG)
assert chef.rechte_an() and [b["name"] for b in chef.benutzer()] == ["chef", "meier", "planer"]
assert chef.rolle("MEIER") == daten.WERKSTATT and chef.rolle("fremd") == daten.LESEN         # Vorgabe: nur lesen
assert chef.darf("melden", "meier") and not chef.darf("auftraege", "meier") and not chef.darf("melden", "fremd")
assert chef.darf("auftraege", "planer") and not chef.darf("einstellungen", "planer") and chef.darf("einstellungen")
chef.einstellung_setzen("rolle_vorgabe", daten.WERKSTATT)
assert chef.rolle("fremd") == daten.WERKSTATT
chef.einstellung_setzen("rolle_vorgabe", daten.LESEN)
assert "gibt es schon" in fehler(chef.benutzer_speichern, "meier", daten.PLANUNG)
assert "Verwaltung" in fehler(chef.benutzer_speichern, "chef", daten.PLANUNG, "chef")        # letzter Verwalter bleibt
assert "Verwaltung" in fehler(chef.benutzer_loeschen, "chef")
chef.benutzer_speichern("mayer", daten.WERKSTATT, alt="meier")
assert chef.rolle("mayer") == daten.WERKSTATT and chef.rolle("meier") == daten.LESEN
chef.benutzer_speichern("meier", daten.WERKSTATT, alt="mayer")
# Änderungsverlauf: wer hat wann was getan
v1 = chef.auftrag_speichern(dict(nummer="V-1", maschine="LT7", kalk_min=90, liefertermin="20.11.2026"))
chef.auftrag_speichern(dict(chef.auftrag(v1), kalk_min=120, kunde="Kramer"))
chef.auftrag_speichern(dict(chef.auftrag(v1)))                                               # nichts geändert: kein Eintrag
platz_meier = daten.Daten(chef.pfad, wer="meier")
platz_meier.starten(v1)
platz_meier.stoppen(v1)
platz_meier.fertig_melden(v1, 100, HEUTE)
chef.wieder_oeffnen(v1)
chef.vorrang_setzen(v1, 1)
chef.auftrag_loeschen(v1)
chef.zurueckholen(v1)
verlauf = chef.verlauf(v1)[::-1]
assert [z["wer"] for z in verlauf] == ["chef", "chef", "meier", "meier", "meier", "chef", "chef", "chef", "chef"]
assert verlauf[0]["was"] == "angelegt (LT7, 1 h 30 min)"
assert verlauf[1]["was"] == "geändert (Kunde: leer → Kramer; Kalkulierte Laufzeit: 1 h 30 min → 2 h 0 min)"
assert [z["was"].split(" (")[0] for z in verlauf[2:]] == [
    "gestartet", "gestoppt", "fertig gemeldet", "wieder geöffnet", "Reihenfolge: vorgezogen",
    "in den Papierkorb gelegt", "aus dem Papierkorb zurückgeholt"]
platz_meier.schliessen()
# Fenster je Rolle: gesperrte Knöpfe und Reiter, Name und Rolle unten
fm = Hauptfenster(daten.Daten(chef.pfad, wer="meier"), heute=HEUTE)                          # Werkstatt
fm.show()
app.processEvents()
assert fm.waehlen(v1) and "meier (Werkstatt)" in fm.wer_zeile.text()
assert fm.k_uhr.isEnabled() and fm.k_fertig.isEnabled() and not fm.k_neu.isEnabled() and not fm.k_aendern.isEnabled()
assert not fm.k_loeschen.isEnabled() and not fm.k_reihe.isEnabled() and not fm.a_csv_ein.isEnabled()
assert not fm.a_papierkorb.isEnabled() and fm.a_verlauf.isEnabled() and not fm.reiter.isTabEnabled(3)
assert fm.neu(zeigen=False) is None and fm.aendern(zeigen=False) is None and "Werkstatt" in fm.statusBar().currentMessage()
fm.loeschen()
fm.reihenfolge(-1)
assert fm.csv_einlesen(tmp / "neu.csv", fragen=False) is None and fm.papierkorb(zeigen=False) is None
assert chef.auftrag(v1)["vorrang"] > 0 and len(chef.auftraege()) == 1                        # nichts davon ist passiert
fm.uhr_schalten()
assert chef.auftrag(v1)["start_am"] and fm.terminauskunft(zeigen=False) is not None
vd = fm.verlauf(zeigen=False)
assert vd.liste.rowCount() == 10 and vd.liste.item(0, 1).text() == "meier" and vd.liste.item(0, 2).text() == "gestartet"
fm.db.schliessen()
fm.close()
fl = Hauptfenster(daten.Daten(chef.pfad, wer="besucher"), heute=HEUTE)                       # nicht eingetragen: nur lesen
fl.show()
app.processEvents()
assert fl.waehlen(v1) and "besucher (Nur lesen)" in fl.wer_zeile.text() and not fl.k_uhr.isEnabled()
assert not fl.k_fertig.isEnabled() and not fl.k_neu.isEnabled() and not fl.reiter.isTabEnabled(3)
fl.uhr_schalten()
assert fl.fertig_melden(zeigen=False) is None and chef.auftrag(v1)["start_am"] and chef.auftrag(v1)["status"] != daten.FERTIG
assert Path(fl.pdf(tmp / "lesen.pdf")).read_bytes().startswith(b"%PDF")                      # ansehen und drucken geht
fl.db.schliessen()
fl.close()
fc = Hauptfenster(chef, heute=HEUTE)                                                         # Verwaltung
fc.reiter.setCurrentIndex(3)
app.processEvents()
assert fc.reiter.isTabEnabled(3) and fc.e_benutzer.rowCount() == 3 and "Rechte sind an" in fc.e_rechte_info.text()
assert fc.benutzer_bearbeiten(neu=True, werte=("Schulz", daten.PLANUNG)) and fc.e_benutzer.rowCount() == 4
fc.e_benutzer.selectRow(3)
assert fc.e_benutzer.item(3, 0).text() == "schulz" and fc.e_benutzer.item(3, 1).text() == "Planung"
assert fc.benutzer_bearbeiten(werte=("schulz", daten.LESEN)) and chef.rolle("schulz") == daten.LESEN
fc.e_benutzer.selectRow(3)
assert fc.benutzer_entfernen() and fc.e_benutzer.rowCount() == 3
fc.e_rolle_vorgabe.setCurrentIndex(fc.e_rolle_vorgabe.findData(daten.WERKSTATT))
assert chef.einstellung("rolle_vorgabe") == daten.WERKSTATT and fc.e_rolle_vorgabe.findData(daten.VERWALTUNG) < 0
gemeldet = []
fc.meldung = gemeldet.append
fc.e_benutzer.selectRow(0)
assert not fc.benutzer_entfernen() and "Verwaltung" in gemeldet[0]                           # letzter Verwalter bleibt
for name in ("meier", "planer", "chef"):                                                     # alle weg: Rechte wieder aus
    chef.benutzer_loeschen(name)
fc.laden()
assert not chef.rechte_an() and "Rechte sind aus" in fc.e_rechte_info.text() and fc.wer_zeile.text() == ""
fc.close()
ok("R7 Benutzerrechte: vier Rollen nach Anmeldename, gesperrte Knöpfe und Reiter, Änderungsverlauf je Auftrag")

# ---------------------------------------------------------------- R8 Arbeitsgänge, mehrere Maschinen
db8 = daten.Daten(tmp / "acht.db", wer="planer")
assert not db8.mit_gaengen() and daten.VORGABEN["arbeitsgaenge"] == "0"            # Vorgabe: aus
for n, (m, minuten, termin) in enumerate((("LT7", 600, D(2026, 11, 13)), ("LT7", 300, D(2026, 11, 20)),
                                          ("T03", 1500, None), ("T11", 90, D(2026, 11, 12))), start=1):
    db8.auftrag_speichern(dict(nummer=f"E-{n}", maschine=m, kalk_min=minuten, liefertermin=termin))
aus8 = rechnung.grundlage(db8, HEUTE)
kern, eigen = einlastung.rechnen(aus8, schwelle=2), rechnung.planen(aus8, 2)


def _kurz(ein):
    return sorted((a["id"], a["start"], a["fertig"], a["lieferbar"], a["puffer"], a["risiko"],
                   tuple((t, round(v, 6), round(b, 6)) for t, v, b in a["stuecke"])) for a in ein["auftraege"])


assert _kurz(kern) == _kurz(eigen) and kern["risiko"] == eigen["risiko"] and kern["spaeter"] == eigen["spaeter"]
assert all(abs(sum(kern["belegt"][k].values()) - sum(eigen["belegt"][k].values())) < 1e-6 for k in kern["belegt"])
assert "plan" in rechnung.einlasten(db8, HEUTE)[1]
for a in db8.auftraege():
    db8.auftrag_loeschen(a["id"])
db8.papierkorb_leeren(alle=True)

# Auftrag auf zwei Maschinen: die Teile laufen gleichzeitig, fertig ist der Auftrag mit dem letzten Teil
m1 = db8.auftrag_speichern(dict(nummer="M-1", kunde="Kramer", liefertermin=D(2026, 11, 20), gaenge=[
    dict(name="Teil 1", platz="T11", kalk_min=240), dict(name="Teil 2", platz="LT7", kalk_min=720, gleichzeitig=True)]))
a = db8.auftrag(m1)
assert (a["maschine"], a["kalk_min"], a["status"]) == ("T11 + LT7", 960, daten.OFFEN)
assert [g["stufe"] for g in a["gaenge"]] == [0, 0] and len(db8.bereit(a["gaenge"])) == 2
_aus, ein = rechnung.einlasten(db8, HEUTE)
teile = {x["maschine"]: x for x in ein["auftraege"]}
assert teile["T11"]["fertig"] == HEUTE and teile["LT7"]["fertig"] == D(2026, 11, 12)
assert teile["LT7"]["stuecke"] == [(HEUTE, 0.0, 8.0), (D(2026, 11, 12), 0.0, 4.0)]
plan = ein["plan"][m1]
assert (plan["start"], plan["fertig"], plan["lieferbar"], plan["risiko"]) == (
    HEUTE, D(2026, 11, 12), D(2026, 11, 16), einlastung.OK)
assert ein["risiko"][einlastung.OK] == 1                           # ein Auftrag, nicht zwei
db8.starten(m1, gang_id=a["gaenge"][1]["id"])
assert db8.auftrag(m1)["status"] == daten.LAEUFT and db8.uhr_laeuft()
db8.fertig_melden(m1, 700, HEUTE, gang_id=a["gaenge"][1]["id"])
assert db8.auftrag(m1)["status"] == daten.LAEUFT and not db8.uhr_laeuft()
db8.fertig_melden(m1, 250, D(2026, 11, 12))                        # ohne Angabe: der nächste, der an der Reihe ist
a = db8.auftrag(m1)
assert (a["status"], a["ist_min"], a["fertig_am"]) == (daten.FERTIG, 950, "2026-11-12")
si = rechnung.soll_ist(db8)
assert [(s["maschine"], s["kalk_min"], s["ist_min"]) for s in si["maschinen"]] == [("LT7", 720, 700), ("T11", 240, 250)]
assert si["gesamt"]["anzahl"] == 1 and si["gesamt"]["ist_min"] == 950
db8.wieder_oeffnen(m1)                                             # die letzte fertige Zeile ist wieder offen
a = db8.auftrag(m1)
assert a["status"] == daten.LAEUFT and [g["status"] for g in a["gaenge"]] == [daten.FERTIG, daten.OFFEN]
db8.auftrag_loeschen(m1)

# Arbeitsgänge nacheinander: Laser, Entgraten, Fremdarbeit
db8.einstellung_setzen("arbeitsgaenge", "1")
db8.maschine_speichern("Entgraten", 8, True)
for falsch in ("Fremdarbeit", "A + B", "A → B"):
    try:
        db8.maschine_speichern(falsch)
        raise AssertionError(falsch)
    except daten.Fehler:
        pass
gaenge = [dict(name="Laser", platz="LT7", kalk_min=360), dict(name="Entgraten", platz="Entgraten", kalk_min=180),
          dict(name="Verzinken", platz="Fremdarbeit", tage=5)]
g1 = db8.auftrag_speichern(dict(nummer="G-1", kunde="Voss", liefertermin=D(2026, 11, 20), gaenge=gaenge))
a = db8.auftrag(g1)
assert (a["maschine"], a["kalk_min"]) == ("LT7 → Entgraten → Fremdarbeit", 540)
assert [g["stufe"] for g in a["gaenge"]] == [0, 1, 2] and [g["name"] for g in db8.bereit(a["gaenge"])] == ["Laser"]
_aus, ein = rechnung.einlasten(db8, HEUTE)
je = {x["gang_name"]: x for x in ein["auftraege"]}
assert je["Laser"]["stuecke"] == [(HEUTE, 0.0, 6.0)]
# Übergangszeit 0: Entgraten beginnt am selben Tag, aber erst zur Tagesstunde, zu der der Laser fertig ist
assert je["Entgraten"]["stuecke"] == [(HEUTE, 6.0, 8.0), (D(2026, 11, 12), 0.0, 1.0)]
assert (je["Verzinken"]["start"], je["Verzinken"]["fertig"], je["Verzinken"]["stuecke"]) == (
    D(2026, 11, 12), D(2026, 11, 19), [])                          # 5 Arbeitstage, ohne Kapazität
plan = ein["plan"][g1]
assert (plan["start"], plan["fertig"], plan["durchlauf"], plan["lieferbar"]) == (
    HEUTE, D(2026, 11, 19), 7, D(2026, 11, 23))
assert plan["risiko"] == einlastung.UEBER and len(rechnung.kritische(ein)) == 1    # lieferbar nach dem 20.11.
db8.maschine_speichern("Entgraten", 8, True, alt="Entgraten", uebergang=1)         # ein Arbeitstag Übergang
_aus, ein = rechnung.einlasten(db8, HEUTE)
je = {x["gang_name"]: x for x in ein["auftraege"]}
assert je["Entgraten"]["stuecke"] == [(D(2026, 11, 12), 0.0, 3.0)] and je["Verzinken"]["fertig"] == D(2026, 11, 19)
# ein zweiter Auftrag nutzt die Lücke am Arbeitsplatz Entgraten, obwohl er später an der Reihe ist
g2 = db8.auftrag_speichern(dict(nummer="G-2", liefertermin=D(2026, 11, 27), gaenge=[
    dict(name="Entgraten", platz="Entgraten", kalk_min=120)]))
_aus, ein = rechnung.einlasten(db8, HEUTE)
assert ein["plan"][g2]["fertig"] == HEUTE
db8.auftrag_loeschen(g2)
# streng nacheinander
laser, entgraten, zink = (g["id"] for g in a["gaenge"])
for versuch in (lambda: db8.starten(g1, gang_id=entgraten), lambda: db8.fertig_melden(g1, 100, gang_id=zink)):
    try:
        versuch()
        raise AssertionError("nicht an der Reihe")
    except daten.Fehler as e:
        assert "noch nicht an der Reihe" in str(e) and "Laser" in str(e)
db8.starten(g1, jetzt=datetime.datetime(2026, 11, 11, 7, 0))
assert db8.stoppen(g1, jetzt=datetime.datetime(2026, 11, 11, 9, 30)) == 150
db8.fertig_melden(g1, 370, HEUTE)
db8.fertig_melden(g1, 200, D(2026, 11, 12))
a = db8.auftrag(g1)
assert a["status"] == daten.LAEUFT and [g["name"] for g in db8.bereit(a["gaenge"])] == ["Verzinken"]
db8.starten(g1, jetzt=datetime.datetime(2026, 11, 9, 8, 0))        # schon am Montag weggegeben
assert not db8.uhr_laeuft()                                        # Fremdarbeit: keine Uhr
_aus, ein = rechnung.einlasten(db8, HEUTE)
assert ein["plan"][g1]["fertig"] == D(2026, 11, 16)                # 5 Arbeitstage ab dem Start
db8.fertig_melden(g1, None, D(2026, 11, 17))                       # Fremdarbeit braucht keine Laufzeit
a = db8.auftrag(g1)
assert (a["status"], a["ist_min"], a["fertig_am"]) == (daten.FERTIG, 570, "2026-11-17")
assert [(s["maschine"], s["ist_min"]) for s in rechnung.soll_ist(db8)["maschinen"]] == [("Entgraten", 200), ("LT7", 370)]
gem8 = rechnung.gemessen(db8, rechnung.grundlage(db8, D(2026, 11, 18)), D(2026, 11, 18), 1)
assert abs(gem8["stunden"][("LT7", D(2026, 11, 9))] - 370 / 60) < 1e-9 and gem8["laeufe"] == 2
was = [v["was"] for v in db8.verlauf(g1)]
assert any(w.startswith("Arbeitsgänge: Laser (LT7, 6 h 0 min); Entgraten") for w in was)
assert "Laser: gestartet" in was and "Verzinken: fertig gemeldet" in was and "Laser: gestoppt (gelaufen 2 h 30 min)" in was
db8.maschine_speichern("Entgratung", 8, True, alt="Entgraten")                     # Umbenennen zieht die Gänge mit
assert db8.auftrag(g1)["maschine"] == "LT7 → Entgratung → Fremdarbeit"
try:
    db8.maschine_loeschen("Entgratung")
    raise AssertionError("Arbeitsplatz mit Arbeitsgängen")
except daten.Fehler:
    pass
# einteilig <-> mehrteilig: die gestoppte Zeit geht mit
e1 = db8.auftrag_speichern(dict(nummer="U-1", maschine="T03", kalk_min=300))
db8.starten(e1, jetzt=datetime.datetime(2026, 11, 11, 7, 0))
db8.stoppen(e1, jetzt=datetime.datetime(2026, 11, 11, 8, 0))
db8.auftrag_speichern(dict(db8.auftrag(e1), gaenge=[dict(platz="T03", kalk_min=200),
                                                   dict(platz="T11", kalk_min=100, gleichzeitig=True)]))
a = db8.auftrag(e1)
assert [g["gelaufen_min"] for g in a["gaenge"]] == [60, 0] and a["status"] == daten.LAEUFT
db8.auftrag_speichern(dict(a, bemerkung="eilt"))                   # ohne Schlüssel gaenge: Arbeitsgänge bleiben
assert len(db8.auftrag(e1)["gaenge"]) == 2 and db8.auftrag(e1)["bemerkung"] == "eilt"
db8.auftrag_speichern(dict(db8.auftrag(e1), gaenge=[], maschine="T03", kalk_min=300))
a = db8.auftrag(e1)
assert not a["gaenge"] and (a["maschine"], a["gelaufen_min"]) == ("T03", 60)
# CSV: mehrteilige Aufträge bleiben, wie sie im Programm stehen
db8.auftrag_speichern(dict(db8.auftrag(e1), gaenge=[dict(platz="T03", kalk_min=200),
                                                   dict(platz="T11", kalk_min=100, gleichzeitig=True)]))
csv8 = austausch.schreiben(db8, tmp / "acht.csv")
e8 = austausch.lesen(db8, csv8)
assert not e8["fehler"] and not e8["neu"] and not e8["geaendert"], e8
(tmp / "acht2.csv").write_text("Auftragsnummer;Maschine;Laufzeit;Liefertermin\nU-1;T03;5 h;30.11.2026\n"
                               "X-9;T03 + T11;5 h;\n", encoding="utf-8")
e8 = austausch.lesen(db8, tmp / "acht2.csv")
assert len(e8["geaendert"]) == 1 and "mehrere Arbeitsgänge" in e8["uebersprungen"][0] and "X-9" in e8["fehler"][0]
austausch.uebernehmen(db8, e8)
a = db8.auftrag(e1)
assert (a["maschine"], a["kalk_min"], a["liefertermin"]) == ("T03 + T11", 300, "2026-11-30")
# Vorlagen
db8.vorlage_speichern("Lasern und verzinken", [dict(name="Laser", platz="LT7"),
                                               dict(name="Verzinken", platz="Fremdarbeit", tage=5)])
try:
    db8.vorlage_speichern("Lasern und verzinken", [dict(name="Laser", platz="LT7")])
    raise AssertionError("Vorlage doppelt")
except daten.Fehler:
    pass
assert db8.vorlagen()[0]["gaenge"][1] == dict(name="Verzinken", platz="", kalk_min=0, tage=5, gleichzeitig=0)

# Fenster
f8 = Hauptfenster(db8, heute=HEUTE)
f8.show()
app.processEvents()
kopf8 = [f8.liste.horizontalHeaderItem(c).text() for c in range(f8.liste.columnCount())]
assert kopf8[6] == "Fertig (Plan)" and kopf8[12] == "Durchlaufzeit (Plan)" and not f8.liste.isColumnHidden(12)
d = f8.neu(zeigen=False)
assert d.mit_gaengen and not d.mehr.isChecked() and d.form.isRowVisible(d.maschine) and not d.form.isRowVisible(d.gaenge)
d.nummer.setText("G-3")
d.kalk.eingabe.setText("2 h")
d.mehr.setChecked(True)                                            # Maschine und Laufzeit werden die erste Zeile
assert not d.form.isRowVisible(d.maschine) and d.form.isRowVisible(d.gaenge) and len(d.gaenge.zeilen) == 1
assert d.gaenge.vorlage.count() == 2
d.gaenge._vorlage(1)                                               # Vorlage übernehmen, im Auftrag ändern
assert [z["name"] for z in d.gaenge.zeilen] == ["Laser", "Verzinken"] and d.gaenge.zeilen[1]["zeit"] == "5 Arbeitstage"
assert not d.speichern() and "Zeile 1" in d.fehler.text()          # Laufzeit fehlt noch
d.gaenge.tabelle.item(0, 2).setText("1:30")
d.gaenge.hinzu(name="Entgraten", platz="Entgratung", zeit="45 min")
d.gaenge.schieben(-1, 2)                                           # vor die Fremdarbeit
assert d.speichern()
a = db8.auftrag(nummer="G-3")
assert a["maschine"] == "LT7 → Entgratung → Fremdarbeit" and [g["kalk_min"] for g in a["gaenge"]] == [90, 45, 0]
f8.laden()
assert f8.waehlen(a["id"]) and f8.k_uhr.text() == "Start"
f8.uhr_schalten()
assert f8.k_uhr.text() == "Stopp" and "0 von 3 fertig, jetzt Laser" in f8.liste.item(f8.liste.currentRow(), 5).text()
assert f8.liste.item(f8.liste.currentRow(), 12).text().endswith("Arbeitstage")
fd = f8.fertig_melden(zeigen=False)
assert "„Laser“" in fd.windowTitle() and not fd.fremd
fd.ist.eingabe.setText("1 h 40 min")
assert fd.speichern()
f8.laden()
f8.waehlen(a["id"])
assert f8.k_oeffnen.isVisible() and f8.k_oeffnen.text() == "Letzten Arbeitsgang wieder öffnen"
assert "1 von 3 fertig, jetzt Entgraten" in f8.liste.item(f8.liste.currentRow(), 5).text()
f8.wieder_oeffnen()
assert db8.auftrag(a["id"])["gaenge"][0]["status"] == daten.OFFEN
# zwei Teile gleichzeitig: der Knopf fragt, welcher
f8.waehlen(e1)
assert f8.k_uhr.text() == "Start / Stopp …"
t03, t11 = (g["id"] for g in db8.auftrag(e1)["gaenge"])
f8.uhr_schalten(gang_id=t11)
assert [bool(g["start_am"]) for g in db8.auftrag(e1)["gaenge"]] == [False, True]
fd = f8.fertig_melden(zeigen=False, gang_id=t11)
fd.ist.eingabe.setText("95")
assert fd.speichern() and db8.auftrag(e1)["gaenge"][1]["ist_min"] == 95
# Einstellungen: Schalter, Übergangszeit, Vorlagen
f8.reiter.setCurrentIndex(3)
app.processEvents()
assert f8.e_gaenge.isChecked() and not f8.e_maschinen.isColumnHidden(4) and f8.e_vorlagen.rowCount() == 1
assert f8.g_maschinen.title() == "Maschinen und Arbeitsplätze"
assert f8.vorlage_bearbeiten(neu=True, werte=("Nur Laser", [dict(name="Laser", platz="T03")]))
f8.e_vorlagen.selectRow(1)
assert f8.vorlage_entfernen() and len(db8.vorlagen()) == 1
zeile = [m["name"] for m in db8.maschinen()].index("Entgratung")
f8.e_maschinen.selectRow(zeile)
assert f8.maschine_bearbeiten(werte=("Entgratung", 8, True, "", 2)) and "2 Arbeitstage" in f8.e_maschinen.item(zeile, 4).text()
f8.e_gaenge.setChecked(False)                                      # ausschalten: vorhandene Aufträge bleiben
assert not db8.mit_gaengen() and f8.e_maschinen.isColumnHidden(4) and not f8.e_vorlagen.isVisible()
assert len(db8.auftrag(a["id"])["gaenge"]) == 3
d = f8.aendern(a["id"], zeigen=False)                              # ein Auftrag mit Arbeitsgängen zeigt sie weiter
assert d.mit_gaengen and d.mehr.isChecked() and d.gaenge.art == "gaenge"
d = f8.neu(zeigen=False)                                           # sonst: nur „auf mehrere Maschinen aufteilen“
assert not d.mit_gaengen and d.gaenge.art == "teile" and "mehrere Maschinen" in d.mehr.text()
d.nummer.setText("M-2")
d.maschine.setCurrentText("T11")
d.kalk.eingabe.setText("3 h")
d.mehr.setChecked(True)
assert [z["platz"] for z in d.gaenge.zeilen] == ["T11", "LT7"] and d.gaenge.tabelle.isColumnHidden(3)
assert d.gaenge.tabelle.isColumnHidden(0) and d.gaenge.tabelle.isColumnHidden(4)
d.gaenge.tabelle.item(1, 2).setText("4,5 h")
assert d.speichern()
a = db8.auftrag(nummer="M-2")
assert (a["maschine"], a["kalk_min"], [g["gleichzeitig"] for g in a["gaenge"]]) == ("T11 + LT7", 450, [0, 1])
f8.reiter.setCurrentIndex(1)                                       # Auslastung und Arbeitsliste mit Arbeitsgängen
app.processEvents()
pdf8 = f8.arbeitsliste_pdf(tmp / "acht.pdf")
assert Path(pdf8).stat().st_size > 2000 and Path(f8.pdf(tmp / "acht-auslastung.pdf")).stat().st_size > 2000
f8.close()
# eine Datenbank vom Stand 3 (Version 1.2 ohne Arbeitsgänge) wird nachgezogen
alt8 = tmp / "stand3.db"
con = sqlite3.connect(alt8)
con.executescript("".join(daten.SCHRITTE[:3]) + "INSERT INTO auftraege (nummer, maschine, kalk_min) VALUES "
                  "('ALT-1', 'LT7', 120); PRAGMA user_version = 3;")
con.close()
db9 = daten.Daten(alt8)
assert db9.auftrag(nummer="ALT-1")["gaenge"] == [] and db9.maschinen()[0]["uebergang_tage"] == 0
db9.schliessen()
db8.schliessen()
ok("R8 Arbeitsgänge (zuschaltbar, nacheinander, Übergangszeit, Fremdarbeit, Durchlaufzeit, Vorlagen) und Auftrag "
   "auf mehreren Maschinen")

# ---------------------------------------------------------------- R4b Übergabe aus der Kalkulation
from rohrlaser import auslastung_ansicht  # noqa: E402


class _Fenster:
    pass


ansicht = auslastung_ansicht.AuslastungAnsicht.__new__(auslastung_ansicht.AuslastungAnsicht)
ansicht.daten = dict(maschinen=["LT7"], auftraege={("LT7", "x"): [
    dict(id=1, nummer="2026-00010", kunde="Kramer; Söhne", art=einlastung.AUFTRAG, maschine="LT7", h=12.5,
         termin="2026-11-20"),
    dict(id=2, nummer="2026-00011", kunde="Angebot", art=einlastung.ANGEBOT, maschine="LT7", h=3.0, termin=None)]})
ueb = auslastung_ansicht.AuslastungAnsicht.uebergabe(ansicht, tmp / "uebergabe.csv")
db3 = daten.Daten(tmp / "drei.db")
e3 = austausch.lesen(db3, ueb)
assert not e3["fehler"] and len(e3["neu"]) == 1                    # nur beauftragte Aufträge, keine Angebote
assert (e3["neu"][0]["nummer"], e3["neu"][0]["kalk_min"], e3["neu"][0]["liefertermin"], e3["neu"][0]["kunde"]) == (
    "2026-00010", 750, "2026-11-20", "Kramer; Söhne")
db3.schliessen()
ok("R4b Übergabedatei aus der Kalkulation lässt sich im Programm einlesen")

# ---------------------------------------------------------------- R6 unabhängig von der Kalkulation
code = ("import sys; sys.path.insert(0, r'%s'); import rl_auslastung.fenster, rl_auslastung.__main__; "
        "print(','.join(sorted(m for m in sys.modules if m.startswith('rohrlaser'))))" % (HIER.parent / "programm"))
geladen = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout.strip()
assert geladen == ("rohrlaser,rohrlaser.auslastung_grafik,rohrlaser.einlastung,rohrlaser.feiertage,rohrlaser.stil,"
                   "rohrlaser.wochen"), geladen
ok("R6 das Programm lädt aus der Kalkulation nur Rechenkern, Feiertage, Design und Grafik")
print("Alle Tests für Rohrlaser Auslastung bestanden.")
