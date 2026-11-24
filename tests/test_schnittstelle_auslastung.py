"""Prüft die Schnittstelle Kalkulation ↔ Rohrlaser Auslastung, Format 2 (Plan 11.11.2026, auslastung_austausch.py):
- S1 Beauftragen schreibt die Auftragsdatei in den Unterordner „Auslastung“: Spalten wie in der Beschreibung,
  Laserzeit + Rüstzeit = kalkulierte Maschinenzeit, Rüsten auf der ersten Position je Abmessung, Zusatzarbeit mit Zeit,
  Stangen-Zeilen
- S2 neue Freigabe nur bei Änderung (Schließen des Angebots), Knopf Übergabe schreibt erneut mit gleicher Freigabe
- S3 Storno, wenn ein übergebener Auftrag nicht mehr beauftragt ist
- S4 Rückmeldung lesen: Ist-Laserzeit, frühester Fertig-Tag, Liefertermin-Vorschlag (abschaltbar, nur frisch)
- S5 Nachkalkulation vorbelegen mit der Ist-Laserzeit der Auslastung, wenn es keine Scans gibt
- S6 Austausch aus: keine Dateien, Knopf Übergabe fragt wieder nach einer Datei (Format 1)

Aufruf: python tests/test_schnittstelle_auslastung.py   (QT_QPA_PLATFORM=offscreen)
"""
import csv
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import auslastung, auslastung_austausch as aa, nachkalk_vorbelegen, terminplan  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


def lesen(pfad):
    with open(pfad, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


def kopfzeile(pfad):
    with open(pfad, newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f, delimiter=";"))


def zahl(t):
    return float(t.replace(",", ".")) if t else 0.0


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
ordner = tmp / "Auslastung"
katalog = [z for z in db.zeilen("zusatzarbeiten") if z.get("fremd") != "ja" and z.get("art") == "€/h"]
assert katalog, "Beispieldaten ohne Zusatzarbeit nach Zeit (€/h)"
arbeit = katalog[0]["name"]

# ------------------------------------------------------------------ S1 Beauftragen schreibt die Auftragsdatei
a = db.angebot_neu(dict(kunde="Becker GmbH", kundennr="10023", skonto=0, stange=6000, maschine="T03",
                        nummer="2026/00042"))
db.position_neu(a, dict(pos=1, artikel="BG-100", bezeichnung="Querrohr", profil_id="RR 42,4x2,0",
                        werkstoff_id="S235-10219", laenge=1250, stueck=50, schneidweg=300, einstiche=2,
                        zusatz=json.dumps([{"name": arbeit, "menge": 120}], ensure_ascii=False)))
db.position_neu(a, dict(pos=2, artikel="BG-101", bezeichnung="Stütze", profil_id="RR 42,4x2,0",
                        werkstoff_id="S235-10219", laenge=800, stueck=50, schneidweg=200, einstiche=1))
profile = [p["profil_id"] for p in db.zeilen("profile") if p.get("profil_id") != "RR 42,4x2,0"]
db.position_neu(a, dict(pos=3, artikel="BG-102", bezeichnung="Holm", profil_id=profile[0],
                        werkstoff_id="S235-10219", laenge=600, stueck=20, schneidweg=250, einstiche=1))
s = f.angebot_oeffnen(a)
s.optimieren()
s.neu_laden()
f.angebot_schliessen(a)
assert not ordner.exists()                                     # Angebot: noch nichts für die Auslastung
assert f.angebote.vorgang_setzen("Beauftragt", angebot_id=a, auftrag=("4711-22", "2026-11-27"))
dateien = sorted(ordner.glob("Auftrag-*.csv"))
assert len(dateien) == 1 and dateien[0].name.startswith("Auftrag-2026-00042-"), dateien   # „/“ ersetzt
assert not list(ordner.glob("*.tmp"))
assert tuple(kopfzeile(dateien[0])) == aa.SPALTEN
beispiel = HIER.parent / "docs" / "schnittstelle-beispiel"
for b in sorted(beispiel.glob("Auftrag-*.csv")) if beispiel.exists() else ():
    assert tuple(kopfzeile(b)) == aa.SPALTEN, b                # gleiche Spalten wie die Beispiele der Auslastung
z = lesen(dateien[0])
assert {r["Format"] for r in z} == {"2"} and {r["Freigabe"] for r in z} == {"1"}
assert {(r["Auftragsnummer"], r["Kundenauftrag"], r["Kunde"], r["Kundennr"], r["Maschine"], r["Liefertermin"])
        for r in z} == {("2026/00042", "4711-22", "Becker GmbH", "10023", "T03", "27.11.2026")}
pos = [r for r in z if r["Art"] == "Position"]
assert [r["Pos"] for r in pos] == ["1", "2", "3"] and pos[0]["Stückzahl"] == "50" and pos[0]["Material"] == "eigen"
assert pos[0]["Profilform"] and pos[0]["Werkstoff"] and pos[0]["Teilelänge [mm]"] == "1250"
h, _ = auslastung.maschinenzeit(db, db.angebot(a))
summe = sum(zahl(r["Laserzeit [min]"]) + zahl(r["Rüstzeit [min]"]) for r in pos)
assert abs(summe - h * 60) < 0.5, (summe, h * 60)              # Summe = kalkulierte Maschinenzeit
assert zahl(pos[0]["Rüstzeit [min]"]) > 0 and zahl(pos[2]["Rüstzeit [min]"]) > 0     # erste je Abmessung
assert zahl(pos[1]["Rüstzeit [min]"]) == 0                     # gleiche Abmessung wie Pos. 1
assert all(zahl(r["Laserzeit [min]"]) > 0 for r in pos)
zus = [r for r in z if r["Art"] == "Zusatzarbeit"]
assert [(r["Pos"], r["Arbeit"], r["Fremdleistung"]) for r in zus] == [("1", arbeit, "nein")], zus
assert zahl(zus[0]["Zeit [min]"]) == 100              # 120 s × 50 Stück
st = [r for r in z if r["Art"] == "Stangen"]
assert len(st) == 2 and all(int(r["Stangen"]) >= 1 and r["Stangenlänge [mm]"] for r in st)
assert all(0 < zahl(r["Nutzlänge [mm]"]) <= int(r["Stangen"]) * zahl(r["Stangenlänge [mm]"]) for r in st)
ok("S1 Beauftragen: Auftragsdatei Format 2, Laser- + Rüstzeit = Maschinenzeit, Zusatzarbeit, Stangen")

# ------------------------------------------------------------------ S2 neue Freigabe nur bei Änderung
f.angebot_oeffnen(a)
f.angebot_schliessen(a)                                        # nichts geändert: keine neue Datei
assert len(list(ordner.glob("Auftrag-*.csv"))) == 1
p2 = db.positionen(a)[1]
db.position_aendern(p2["id"], "stueck", 80)
jetzt = datetime.datetime(2026, 11, 12, 8, 0, 0)
neu = aa.abgleich(db, a, jetzt)
assert neu and neu.name == "Auftrag-2026-00042-20261112-080000.csv"
z2 = lesen(neu)
assert {r["Freigabe"] for r in z2} == {"2"} and [r["Stückzahl"] for r in z2 if r["Art"] == "Position"][1] == "80"
assert aa.abgleich(db, a, jetzt) is None                       # gleich geblieben
from rohrlaser.auslastung_ansicht import AuslastungAnsicht  # noqa: E402
ansicht = AuslastungAnsicht(f, heute=datetime.date(2026, 11, 11))
assert ansicht.uebergabe() == ordner                           # Knopf: Nachzügler, gleiche Freigabe
letzte = max(ordner.glob("Auftrag-*.csv"), key=lambda p: p.stat().st_mtime_ns)
assert {r["Freigabe"] for r in lesen(letzte)} == {"2"}
ok("S2 neue Freigabe nur bei Änderung, Knopf Übergabe schreibt alle beauftragten erneut")

# ------------------------------------------------------------------ S3 Storno
vorher = set(ordner.glob("Auftrag-*.csv"))
assert f.angebote.vorgang_setzen("Abgelehnt", angebot_id=a, absage=("Preis", "", None))
storno = list(set(ordner.glob("Auftrag-*.csv")) - vorher)
assert len(storno) == 1
zs = lesen(storno[0])
assert [(r["Art"], r["Auftragsnummer"], r["Freigabe"], r["Pos"]) for r in zs] == [("Storno", "2026/00042", "3", "")]
assert aa.abgleich(db, a) is None                              # nur einmal
assert f.angebote.vorgang_setzen("Beauftragt", angebot_id=a, auftrag=("4711-22", "2026-11-27"))
wieder = max(ordner.glob("Auftrag-*.csv"), key=lambda p: p.stat().st_mtime_ns)
assert {r["Freigabe"] for r in lesen(wieder)} == {"4"} and lesen(wieder)[0]["Art"] == "Position"
ok("S3 Storno bei nicht mehr beauftragt, danach wieder beauftragt mit höherer Freigabe")

# ------------------------------------------------------------------ S4 Rückmeldung
SP = ("Format;Art;Stand;Auftragsnummer;Pos;Arbeitsgang;Maschine;Kalkuliert [min];Tatsächlich [min];Fertig am;"
      "Bediener;Status;Fertig (Plan);Terminrisiko;Montag;KW;Verfügbar [h];Verplant [h];Frei [h];Stunden;"
      "Frühester Fertig-Tag")


def rueckmeldung(stand, zeilen):
    (ordner / aa.RUECKMELDUNG).write_text("﻿" + SP + "\n" + "\n".join(
        z.replace("STAND", stand) for z in zeilen) + "\n", encoding="utf-8")


rueckmeldung("11.11.2026 18:00", [
    "2;Auftrag;STAND;2026/00042;;;T03;180;204;10.11.2026;Meier;fertig;;;;;;;;;",
    f"2;Auftrag;STAND;2026/00042;;{arbeit};Bearbeitung;95;;;;offen;16.11.2026;ok;;;;;;;",
    "2;Kapazität;STAND;;;;T03;;;;;;;;16.11.2026;47;40;12;28;;",
    "2;Kapazität;STAND;;;;T03;;;;;;;;23.11.2026;48;40;0;40;;",
    "2;Frühester;STAND;;;;T03;;;;;;;;;;;;;4;13.11.2026",
    "2;Frühester;STAND;;;;T03;;;;;;;;;;;;;16;18.11.2026"])
r = aa.rueckmeldung(db)
assert r["stand"] == datetime.datetime(2026, 11, 11, 18, 0) and len(r["auftraege"]) == 2
assert r["kapazitaet"][("T03", datetime.date(2026, 11, 16))] == 28.0
assert r["fruehester"]["T03"] == [(4.0, datetime.date(2026, 11, 13)), (16.0, datetime.date(2026, 11, 18))]
assert abs(aa.ist_laser_h(db, "2026/00042") - 204 / 60) < 1e-9 and aa.ist_laser_h(db, "gibt-es-nicht") is None
heute = datetime.date(2026, 11, 12)
ab = datetime.date(2026, 11, 12)
assert aa.termin_vorschlag(db, "T03", 3.0, ab, heute)[0] == datetime.date(2026, 11, 13)       # Stufe 4 h
assert aa.termin_vorschlag(db, "T03", 10.0, ab, heute)[0] == datetime.date(2026, 11, 18)      # Stufe 16 h
assert aa.termin_vorschlag(db, "T03", 3.0, datetime.date(2026, 11, 16), heute)[0] == datetime.date(2026, 11, 16)
assert aa.termin_vorschlag(db, "T03", 50.0, ab, heute)[0] == datetime.date(2026, 11, 27)      # 28 + 40 h frei
assert aa.termin_vorschlag(db, "T03", 100.0, ab, heute) is None                               # passt nicht
assert aa.termin_vorschlag(db, "LT9", 3.0, ab, heute) is None                                 # Maschine unbekannt
assert aa.termin_vorschlag(db, "T03", 3.0, ab, datetime.date(2026, 11, 20)) is None           # Stand zu alt
# Liefertermin-Vorschlag im Angebot (terminplan): Laser fertig nach Auslastung + Vorlauf
b = db.angebot_neu(dict(kunde="Kunde", skonto=0, stange=6000, maschine="T03", nummer="2026-00043"))
db.position_neu(b, dict(pos=1, artikel="T", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                        stueck=20, schneidweg=300, einstiche=2))
sb = f.angebot_oeffnen(b)
sb.optimieren()
f.angebot_schliessen(b)
db.einstellung_setzen("termin_material_tage", 0)
db.einstellung_setzen("auslastung_vorlauf", 2)
t = terminplan.fruehester(db, b, heute)
assert t.laser_h < 4 and t.datum == datetime.date(2026, 11, 17), t           # Fr 13.11. + 2 Arbeitstage
assert "Rohrlaser Auslastung (Stand 11.11.2026 18:00)" in terminplan.text(t)
db.einstellung_setzen("termin_aus_auslastung", "nein")
t2 = terminplan.fruehester(db, b, heute)
assert "Rohrlaser Auslastung" not in terminplan.text(t2)                     # abgeschaltet: eigene Rechnung
db.einstellung_setzen("termin_aus_auslastung", "ja")
ok("S4 Rückmeldung: Ist-Zeit, Kapazität, frühester Fertig-Tag, Liefertermin-Vorschlag (abschaltbar, nur frisch)")

# ------------------------------------------------------------------ S5 Nachkalkulation vorbelegen
info = nachkalk_vorbelegen.vorbelegen(db, a)
nk = db.angebot(a)["nachkalkulation"]
nk = json.loads(nk) if isinstance(nk, str) else nk
assert info is not None and abs(nk["laser_h"] - round(204 / 60, 3)) < 1e-9
assert "Rohrlaser Auslastung" in nk["bemerkung"]
ok("S5 Nachkalkulation: Ist-Laserzeit aus der Auslastung, wenn keine Scans da sind")

# ------------------------------------------------------------------ S6 Austausch aus
db.einstellung_setzen("auslastung_austausch", "nein")
anzahl = len(list(ordner.glob("Auftrag-*.csv")))
assert aa.ordner(db) is None and aa.rueckmeldung(db) is None
assert f.angebote.vorgang_setzen("Beauftragt", angebot_id=b, auftrag=("", "2026-11-30"))
assert len(list(ordner.glob("Auftrag-*.csv"))) == anzahl
ziel = tmp / "alt.csv"
assert ansicht.uebergabe(ziel) == ziel and kopfzeile(ziel)[0] == "Auftragsnummer"   # Format 1 wie bisher
db.einstellung_setzen("auslastung_austausch", "ja")
eigen = tmp / "geteilt"
db.einstellung_setzen("auslastung_ordner", str(eigen))
aa.abgleich(db, b)
assert len(list(eigen.glob("Auftrag-2026-00043-*.csv"))) == 1               # eigener Ordner
ok("S6 Austausch aus: keine Dateien, alter Knopf; eigener Ordner aus den Einstellungen")
f.close()
db.schliessen()
print("ALLE OK")
