"""Prüft die Programmierung als Zeit × Stundensatz (Patrick 22.10.2026, bis 0.8.19: 8,50 € je Position):
- G1 Vorgaben neuer Dateien: 5 min je Position + 0,5 min je Innenkontur, Stundensatz/Arbeitsschritt 'Programmierung'
- G2 Angebot: Zeit je Position = Grundzeit + Konturen × Zeit, × Stundensatz, Zeile in Zeiten & Arbeitskosten
- G3 Zeit von Hand je Position, Werte und Stundensatz je Angebot; Stammdaten nur für neue Angebote
- G4 Staffel-Stufe mit eigener Programmierzeit; Stufe ohne Wert = Angebot
- G5 Schema 40: alle Angebote rechnen mit der Zeit, verschickte (festgeschriebene) behalten ihren Betrag je Position;
  fehlender Stundensatz/Arbeitsschritt ergänzt

Aufruf: python tests/test_programmierung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

EPS = 1e-6


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)

# ------------------------------------------------------------------ G1 Vorgaben
assert (db.einstellung("programmierung_zeit"), db.einstellung("programmierung_kontur")) == (5, 0.5)
assert "programmierung_teil" not in db.einstellungen()
satz = {z["satz_id"]: z["satz"] for z in db.zeilen("stundensaetze")}["Programmierung"]
schritt = next(z for z in db.zeilen("arbeitsschritte") if z["schritt"] == "Programmierung")
assert satz == 60 and (schritt["satz"], schritt["art"], schritt["parallel"]) == ("Programmierung", "Personal", "ja")
ok("G1 Vorgabe 5 min je Position + 0,5 min je Innenkontur × Stundensatz Programmierung 60 €/h, Arbeitsschritt Personal")

# ------------------------------------------------------------------ G2 Angebot
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
for pos, profil, laenge, stueck, konturen in ((10, "QR 40x40x3", 2000, 4, (2, 1, 1)), (20, "QR 40x40x3", 900, 6, None),
                                              (30, "RR 48,3x2,6", 1500, 3, (0, 0, 2)),
                                              (40, "RR 48,3x2,6", 700, None, (5, 0, 0))):
    p = dict(pos=pos, artikel=f"T{pos}", profil_id=profil, werkstoff_id="S235-10219", laenge=laenge, stueck=stueck,
             schneidweg=320, einstiche=2)
    if konturen:
        p.update(klein_n=konturen[0], mittel_n=konturen[1], gross_n=konturen[2])
    db.position_neu(a, p)
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
assert s.kopf["programmierung_zeit"] == 5 and s.kopf["programmierung_kontur"] == 0.5


def rechnung():
    return rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, s.einst)


z0, su0 = rechnung()
minuten = (5 + 4 * 0.5) + 5 + (5 + 2 * 0.5)            # Pos. 40 ohne Stückzahl zählt nicht
assert [z["prog_min"] for z in z0] == [7, 5, 6, 7.5] and z0[0]["prog_hand"] is False
assert su0["positionen"] == 3 and abs(su0["programmierung_min"] - minuten) < EPS
assert abs(su0["programmierung"] - minuten / 60 * 60) < EPS, su0["programmierung"]
assert abs(z0[0]["programmierung_anteil"] - 7 / 60 * 60 / 4) < EPS and z0[3]["programmierung_anteil"] == 0
pr = next(x for x in su0["zeiten"] if x["schritt"] == "Programmierung")
assert (pr["art"], pr["parallel"], pr["satz_id"], pr["satz"]) == ("Personal", True, "Programmierung", 60)
assert abs(pr["gesamt_min"] - minuten) < EPS and abs(pr["kosten"] - su0["programmierung"]) < EPS
assert pr["formel"].startswith("18 min / 60 × 60 €/h"), pr["formel"]
assert pr["quelle"] == "5 min je Position + 0,5 min je Innenkontur", pr["quelle"]
assert abs(sum(z["programmierung_anteil"] * z["stueck"] for z in z0 if z) - su0["programmierung"]) < EPS
k = rechnen.zeit_summen(su0["zeiten"])
assert k["personal_min"] >= minuten - EPS
m = s.pos_modell
spalte = next(c for c, (art, x) in enumerate(m.spalten) if art == "feld" and x.name == "prog_zeit")
assert m.data(m.index(0, spalte)) == "7,0" and "Innenkontur" in m.data(m.index(0, spalte), Qt.ToolTipRole)
ok(f"G2 3 Positionen: 7 + 5 + 6 = {minuten:g} min × 60 €/h = {su0['programmierung']:.2f} €, Spalte zeigt die "
   "berechnete Zeit grau, Personalzeit, Umlage = Summe")

# ------------------------------------------------------------------ G3 von Hand, Angebot, Stundensatz
assert m.setData(m.index(1, spalte), "12")
s.neu_laden()
z1, su1 = rechnung()
assert s.positionen[1]["prog_zeit"] == 12 and z1[1]["prog_hand"] and abs(su1["programmierung_min"] - (minuten + 7)) < EPS
assert "von Hand bei 1 Pos." in next(x for x in su1["zeiten"] if x["schritt"] == "Programmierung")["quelle"]
assert abs((su1["verkauf_kalkuliert"] - su0["verkauf_kalkuliert"]) - 7 / (1 - su0["skonto_satz"] / 100)) < EPS, \
    "ohne Zuschläge und Gewinn, nur Skonto"
assert not m.setData(m.index(0, spalte), "7"), "berechnete Zeit bestätigt: bleibt berechnet"
db.angebot_aendern(a, "programmierung_zeit", 10.0)
db.angebot_aendern(a, "programmierung_kontur", 1.0)
s.neu_laden()
_, su2 = rechnung()
assert abs(su2["programmierung_min"] - ((10 + 4) + 12 + (10 + 2))) < EPS
zb = s.kopf["zeitbasis"]
zb["saetze"]["Programmierung"] = 90.0
db.zeitbasis_speichern(a, zb)
s.neu_laden()
_, su3 = rechnung()
assert abs(su3["programmierung"] - su3["programmierung_min"] / 60 * 90) < EPS
sid = next(z["id"] for z in db.zeilen("stundensaetze") if z["satz_id"] == "Programmierung")
db.aendern("stundensaetze", sid, "satz", 75.0)
s.neu_laden()
assert abs(rechnung()[1]["programmierung"] - su3["programmierung"]) < EPS, "Snapshot im Angebot"
a_neu = db.angebot_neu(dict(maschine="T11"))
assert db.angebot(a_neu)["zeitbasis"]["saetze"]["Programmierung"] == 75
# Snapshot ohne Satz Programmierung (Angebot von früher): Satz aus den Stammdaten
zb["saetze"].pop("Programmierung")
db.zeitbasis_speichern(a, zb)
s.neu_laden()
assert abs(rechnung()[1]["programmierung"] - su3["programmierung_min"] / 60 * 75) < EPS
db.aendern("stundensaetze", sid, "satz", 60.0)
ok("G3 Zeit von Hand je Position (12 min, ohne Zuschläge), Grund-/Konturzeit je Angebot, Stundensatz im Angebot; "
   "Stammdaten gelten für neue Angebote und fehlende Sätze")

# ------------------------------------------------------------------ G4 Staffel-Stufe
einst = s.einst
e_st = staffeln.stufe_einst(s.kopf, dict(programmierung_zeit=20.0), einst)
assert e_st["programmierung_zeit"] == 20 and staffeln.stufe_einst(s.kopf, {}, einst)["programmierung_zeit"] == 10
assert {"programmierung_zeit", "programmierung_kontur"} <= set(staffeln.HAUPT) & set(staffeln.EINST_LAUF)
_, su_st = rechnen.kalkulation(s.kopf, s.positionen, s.ergebnis, s.k, s.tabellen, e_st)
assert abs(su_st["programmierung_min"] - ((20 + 4) + 12 + (20 + 2))) < EPS
ok("G4 Staffel-Stufe mit eigener Programmierzeit (20 min), leere Stufe = Wert des Angebots")

# ------------------------------------------------------------------ G5 Schema 40: bestehende Angebote
pfad = tmp / "alt" / "rohrlaser.db"
d = Datenbank(pfad)
ids = []
for _ in range(2):
    x = d.angebot_neu(dict(maschine="T11"))
    d.position_neu(x, dict(pos=10, artikel="A", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
                           stueck=5, schneidweg=200, einstiche=1))
    ids.append(x)
a1, a2 = ids
f2 = Hauptfenster(d, pfad.parent, stumm=True)
s2 = f2.angebot_oeffnen(a2)
assert s2.optimieren()
s2.preise_festschreiben()                       # a2 wurde verschickt (Angebots-PDF)
d.schliessen()
con = sqlite3.connect(pfad)
# wie eine Datei aus 0.8.19: Betrag je Position 12 € in den Einstellungen und im Angebot, festgeschrieben bei a2
pb = json.loads(con.execute("SELECT preisbasis FROM angebote WHERE id=?", (a2,)).fetchone()[0])
for n in ("programmierung_zeit", "programmierung_kontur"):
    pb["einstellungen"].pop(n, None)
pb["einstellungen"]["programmierung_teil"] = 12.0
con.execute("UPDATE angebote SET preisbasis=? WHERE id=?", (json.dumps(pb), a2))
con.execute("UPDATE angebote SET programmierung_zeit=NULL, programmierung_kontur=NULL, programmierung_teil=12")
con.execute("DELETE FROM einstellungen WHERE name IN ('programmierung_zeit', 'programmierung_kontur')")
con.execute("INSERT OR REPLACE INTO einstellungen (name, wert) VALUES ('programmierung_teil', ?)", (json.dumps(12.0),))
con.execute("DELETE FROM arbeitsschritte WHERE schritt='Programmierung'")
con.execute("PRAGMA user_version=39")
con.commit()
con.close()
d = Datenbank(pfad)
assert d.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
assert len(list((pfad.parent / "Sicherung").glob(f"*vor_Schema_{SCHEMA_VERSION}*.db"))) == 1
assert d.einstellung("programmierung_zeit") == 5 and d.einstellung("programmierung_kontur") == 0.5
assert d.con.execute("SELECT 1 FROM einstellungen WHERE name='programmierung_teil'").fetchone() is None
assert any(z["schritt"] == "Programmierung" for z in d.zeilen("arbeitsschritte"))
f2 = Hauptfenster(d, pfad.parent, stumm=True)
s1 = f2.angebot_oeffnen(a1)
assert s1.optimieren()
_, su = rechnen.kalkulation(s1.kopf, s1.positionen, s1.ergebnis, s1.k, s1.tabellen, s1.einst)
assert su["programmierung_min"] == 5 and abs(su["programmierung"] - 5) < EPS, "nicht verschickt: umgestellt auf Zeit"
s2 = f2.angebot_oeffnen(a2)
_, su = rechnen.kalkulation(s2.kopf, s2.positionen, s2.ergebnis, s2.k, s2.tabellen, s2.einst)
assert su["programmierung_min"] is None and abs(su["programmierung"] - 12) < EPS, "verschickt: Betrag bleibt"
pr = next(z for z in su["zeiten"] if z["schritt"] == "Programmierung")
assert pr["gesamt_min"] is None and "festgeschrieben" in pr["quelle"]
# Stufe eines verschickten Angebots: ohne Wert Betrag des Angebots, mit eigener Zeit die Zeit
assert staffeln.stufe_einst(s2.kopf, {}, s2.einst)["programmierung_zeit"] is None
assert staffeln.stufe_einst(s2.kopf, dict(programmierung_zeit=6.0), s2.einst)["programmierung_zeit"] == 6
# Zeit von Hand in einer Position gilt auch im verschickten Angebot
d.position_aendern(s2.positionen[0]["id"], "prog_zeit", 6.0)
s2.neu_laden()
_, su = rechnen.kalkulation(s2.kopf, s2.positionen, s2.ergebnis, s2.k, s2.tabellen, s2.einst)
assert abs(su["programmierung"] - 6) < EPS
d.schliessen()
ok("G5 Schema 40: nicht verschicktes Angebot rechnet 5 min × 60 €/h statt 12 €, verschicktes behält 12 € je "
   "Position (Stufen ebenso), Arbeitsschritt ergänzt")
print("Alle Programmierzeit-Tests bestanden.")
