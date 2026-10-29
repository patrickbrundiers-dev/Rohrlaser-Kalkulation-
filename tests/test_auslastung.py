"""Prüft die Wochenauslastung je Maschine mit Schichtkalender (Plan 29.10.2026 Schritt 2b):

- W1 Kapazität: Stunden je Arbeitstag × Arbeitstage (ohne Feiertage, Betriebsruhe) + Samstag, × nutzbarer Anteil;
  Stunden der Maschine gehen vor der Einstellung; Betriebsruhe lesen
- W2 Bedarf = Laserzeit der Kalkulation (Laser schneiden, Rüsten, Stangenwechsel) in der Woche Liefertermin minus
  Vorlauf; überfällig, später, ohne Termin; nicht optimiert -> Hinweis; nur beauftragte, nicht fertig gemeldete
- W3 gemeldete Teile (Scan, erster Schritt) ziehen ihren Anteil ab
- W4 verschickte Angebote gewichtet mit der Trefferquote
- W5 Fenster: Tabelle Maschinen × Spalten, Farben, Details je Zelle; Menü Datei

Aufruf: python tests/test_auslastung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import auslastung, etiketten, fertigung  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


def nah(a, b, tol=1e-6):
    return abs(a - b) <= tol


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
heute = datetime.date(2026, 11, 4)          # Mittwoch KW 45
m0 = datetime.date(2026, 11, 2)

# W1 Kapazität
assert auslastung.kapazitaet(m0, 8, 0, 1.0, "Nordrhein-Westfalen", set()) == 40
assert auslastung.kapazitaet(datetime.date(2026, 10, 26), 8, 0, 1.0, "Nordrhein-Westfalen", set()) == 40
assert auslastung.kapazitaet(datetime.date(2026, 12, 21), 16, 4, 0.5, "Nordrhein-Westfalen", set()) == \
    4 * 16 * 0.5, "25.12. (Fr) und 26.12. (Sa) Feiertage"
ruhe = auslastung.betriebsruhe("24.12.2026-31.12.2026; 02.10.2026, unsinn")
assert len(ruhe) == 9 and datetime.date(2026, 10, 2) in ruhe
assert auslastung.kapazitaet(datetime.date(2026, 12, 28), 8, 0, 1, "Nordrhein-Westfalen", ruhe) == 0
db.einstellung_setzen("schicht_stunden", 16.0)
db.einstellung_setzen("schicht_verfuegbar", 0.5)
with db.con:
    db.con.execute("UPDATE maschinen SET schicht_stunden=8 WHERE maschinen_id='LT7'")
d = auslastung.berechnen(db, heute, 4)
assert d["kapazitaet"][("T03", m0)] == 40 and d["kapazitaet"][("LT7", m0)] == 20, d["kapazitaet"]
assert [s for s, _, _ in d["spalten"]][0] == auslastung.UEBERFAELLIG and len(d["spalten"]) == 7
ok("W1 Kapazität aus Schichtkalender, Feiertage, Betriebsruhe, Maschine vor Einstellung")


def auftrag(termin, stueck=100, maschine="T03", vorgang="Beauftragt", optimieren=True):
    a = db.angebot_neu(dict(kunde="Kunde", skonto=0, stange=6000, maschine=maschine))
    db.position_neu(a, dict(pos=10, artikel="T", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                            stueck=stueck, schneidweg=300, einstiche=2))
    if optimieren:
        s = f.angebot_oeffnen(a)
        s.optimieren()
        s.neu_laden()
        f.angebot_schliessen(a)
    db.vorgang_setzen(a, vorgang)
    if vorgang == "Beauftragt":
        db.auftrag_setzen(a, "B", termin.isoformat() if termin else None)
    return a


# W2 Bedarf
a1 = auftrag(datetime.date(2026, 11, 13))                 # Fr KW 46 - 2 AT = Mi KW 46
a2 = auftrag(datetime.date(2026, 11, 3))                  # vor dieser Woche -> überfällig (So 1.11. -> KW 44)
a3 = auftrag(datetime.date(2027, 3, 1))                   # später
a4 = auftrag(None)                                        # ohne Termin
a5 = auftrag(datetime.date(2026, 11, 20), optimieren=False)
a6 = auftrag(datetime.date(2026, 11, 13), vorgang="Verschickt")
h1, fertig = auslastung.maschinenzeit(db, db.angebot(a1))
zeiten = {z["schritt"]: z["gesamt_min"] for z in f.angebot_oeffnen(a1)._rechnung()[1]["zeiten"]}
f.angebot_schliessen(a1)
assert nah(h1, sum(zeiten[s] for s in auslastung.LASER_SCHRITTE) / 60) and fertig == 0, (h1, zeiten)
d = auslastung.berechnen(db, heute, 4)
kw46 = datetime.date(2026, 11, 9)
assert nah(d["bedarf"][("T03", kw46)], h1)
assert ("T03", auslastung.UEBERFAELLIG) in d["bedarf"] and ("T03", auslastung.SPAETER) in d["bedarf"]
assert ("T03", auslastung.OHNE) in d["bedarf"]
alle = {x["id"] for v in d["auftraege"].values() for x in v}
assert alle == {a1, a2, a3, a4}, alle
assert any(g == "nicht optimiert" for _, g in d["fehlt"]), d["fehlt"]
fertigung.setzen(db, a3, "Freigegeben")
fertigung.setzen(db, a3, "Fertig gemeldet")
assert a3 not in {x["id"] for v in auslastung.berechnen(db, heute, 4)["auftraege"].values() for x in v}
ok("W2 Laserzeit in der Woche Termin minus Vorlauf, überfällig/später/ohne Termin, fertig gemeldet zählt nicht")

# W3 gemeldete Teile
etiketten.rueckmelden(db, etiketten.code(db.angebot(a1)["nummer"], 10), "Geschnitten", menge=25)
h, fertig = auslastung.maschinenzeit(db, db.angebot(a1))
assert nah(fertig, 0.25), fertig
d = auslastung.berechnen(db, heute, 4)
assert nah(d["bedarf"][("T03", kw46)], h1 * 0.75)
ok("W3 gemeldete Teile ziehen ihren Anteil ab")

# W4 verschickte Angebote gewichtet
d = auslastung.berechnen(db, heute, 4, offene=True)
z6 = [x for v in d["auftraege"].values() for x in v if x["id"] == a6]
assert len(z6) == 1 and d["gewicht"] == 1.0 and z6[0]["gewicht"] == 1.0, d["gewicht"]   # bisher nur Aufträge
a7 = auftrag(None, vorgang="Abgelehnt", optimieren=False)
d = auslastung.berechnen(db, heute, 4, offene=True)
assert d["gewicht"] is not None and 0 < d["gewicht"] < 1, d["gewicht"]
ok(f"W4 verschickte Angebote mit Trefferquote {d['gewicht']:.0%}")

# W5 Fenster
from rohrlaser.auslastung_dialog import AuslastungDialog  # noqa: E402
dlg = AuslastungDialog(f, heute)
t = dlg.tabelle
assert t.rowCount() == 3 and t.columnCount() == 4 + 8 - 1, (t.rowCount(), t.columnCount())
r = [t.verticalHeaderItem(i).text() for i in range(t.rowCount())].index("T03")
c = 2                                                     # überfällig, KW 45, KW 46
assert "/" in t.item(r, c).text() and "%" in t.item(r, c).text(), t.item(r, c).text()
dlg.wochen.setValue(4)
t.setCurrentCell(r, c)
assert dlg.details.rowCount() == 1 and dlg.details.item(0, 0).text() == db.angebot(a1)["nummer"]
dlg.offene.setChecked(True)
assert "Verschickte Angebote zählen mit" in dlg.info.text()
assert "Maschinenauslastung …" in f.datei_aktionen and isinstance(f.maschinenauslastung(), AuslastungDialog)
ok("W5 Fenster mit Maschinen × Wochen, Details, Menü Datei")
print("Alle Auslastungs-Tests bestanden.")
