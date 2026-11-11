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
ok("R2 Datenbank: Aufträge, Start/Stopp, Fertigmeldung, Maschinen, Zusatzfelder, zweiter Platz, Sicherung")

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
assert f.waehlen(n1["id"]) and f.k_start.isEnabled() and not f.k_stopp.isEnabled() and not f.k_oeffnen.isEnabled()
f.starten()
assert f.waehlen(n1["id"]) and f.k_stopp.isEnabled() and not f.k_start.isEnabled()
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
assert f.k_oeffnen.isEnabled() and not f.k_fertig.isEnabled()
f.wieder_oeffnen()
assert db.auftrag(n1["id"])["status"] == daten.OFFEN
f.filter.setCurrentIndex(2)
assert f.liste.rowCount() == len(db.auftraege()) and f.waehlen(n1["id"])
f.loeschen(fragen=False)
assert db.auftrag(n1["id"]) is None
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
f.e_vorlauf.setValue(2)
f.einstellungen_speichern()
assert db.einstellung("laufzeit_form") == "uhr" and db.einstellung("ohne_einheit") == "h" and db.zahl("vorlauf_tage") == 2
assert f.ein["kapazitaet"][("LT7", D(2026, 11, 14))] == 6.0 and laufzeit.lesen("2", db.einstellung("ohne_einheit")) == 120
f.reiter.setCurrentIndex(0)
assert f.liste.item(0, 3).text().endswith(" h") and ":" in f.liste.item(0, 3).text()
f.reiter.setCurrentIndex(3)
assert f.maschine_bearbeiten(neu=True, werte=("T30", 7.5, True)) and f.e_maschinen.rowCount() == len(db.maschinen())
f.e_maschinen.selectRow(f.e_maschinen.rowCount() - 1)
assert f.maschine_entfernen() and "T30" not in [m["name"] for m in db.maschinen()]
assert f.feld_bearbeiten(neu=True, name="Bearbeiter") and f.e_felder.rowCount() == 2
f.e_felder.selectRow(1)
assert f.feld_bearbeiten(name="Programmierer") and [x["name"] for x in db.zusatzfelder()] == ["Material", "Programmierer"]
f.e_felder.selectRow(1)
assert f.feld_entfernen(fragen=False) and f.e_felder.rowCount() == 1
assert f.jetzt_sichern().exists()
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
