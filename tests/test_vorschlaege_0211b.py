"""Prüft die Vorschläge F, G, H und J vom 02.11.2026 (Freigaben Patrick „Alle weiter …“, „Alle Empfehlungen …“,
„Alle Empfehlungen j4 nicht Einbau“).

Aufruf: python tests/test_vorschlaege_0211b.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import (auslastung, fassung_vergleich, maschinen_vergleich, rechnen, teilekatalog,  # noqa: E402
                       terminplan)
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(t):
    print("OK    ", t)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
a = db.angebot_neu(dict(nummer="A-2026-0300", kundennr="K-1001", kunde="Beispiel Metallbau GmbH", datum="2026-10-20",
                        maschine="T11", stange=6000))
p10 = db.position_neu(a, dict(pos=10, artikel="AB-10", bezeichnung="Strebe", profil_id="RE 60x40x3",
                              werkstoff_id="S235-10219", laenge=485.0, stueck=400, schneidweg=380, einstiche=4))
p20 = db.position_neu(a, dict(pos=20, artikel="AB-20", bezeichnung="Riegel", profil_id="RE 60x40x3",
                              werkstoff_id="S235-10219", laenge=900.0, stueck=100, schneidweg=380, einstiche=2))
kopf, pos = db.angebot(a), db.positionen(a)
k, tab = db.kontext(), db.tabellen()
einst = rechnen.einstellungen_angebot(kopf, db.einstellungen())
erg = rechnen.optimieren(kopf, pos, k, tab, einst)
db.ergebnis_speichern(a, erg)

# ------------------------------------------------------------------ F1 Maschinenvergleich
liste = maschinen_vergleich.vergleich(kopf, pos, k, tab, db.einstellungen(), db.zeitbasis_vorgabe)
assert liste[0]["maschine"] == "T11" and len(liste) == len(k.maschinen), liste
assert all(r["verkauf"] for r in liste if r["moeglich"])
billig = dict(liste[0], verkauf=liste[0]["verkauf"] * 0.9, maschine="X")
assert maschinen_vergleich.check_punkt(liste + [billig], "T11")[0] == "HINWEIS"
assert maschinen_vergleich.check_punkt(liste[:1], "T11") is None
ok(f"F1 Maschinenvergleich: {', '.join(r['maschine'] for r in liste)}, Hinweis ab 5 %")

# ------------------------------------------------------------------ F7 Sperrtage
gesperrt = auslastung.betriebsruhe("10.11.2026; 12.11.2026-13.11.2026")
assert datetime.date(2026, 11, 12) in gesperrt and datetime.date(2026, 11, 13) in gesperrt
mo = datetime.date(2026, 11, 9)
voll = auslastung.kapazitaet(mo, 8, 0, 1.0, "NW", set())
weniger = auslastung.kapazitaet(mo, 8, 0, 1.0, "NW", gesperrt)
assert abs(voll - weniger - 24) < 1e-6, (voll, weniger)
assert "Sperrtag 10.11., 12.11., 13.11." in auslastung.gesperrt_text(set(), gesperrt, mo)
d = terminplan.arbeitstage_spaeter(datetime.date(2026, 11, 9), 2, "NW", gesperrt)
assert d == datetime.date(2026, 11, 16), d
assert terminplan.arbeitstage_zwischen(datetime.date(2026, 11, 9), datetime.date(2026, 11, 16), "NW", gesperrt) == 2
ok("F7 Sperrtage: Kapazität ohne gesperrte Tage, Terminplan rechnet sie heraus")

# ------------------------------------------------------------------ F2 Fassungsvergleich
db.staffelpreise_speichern(a, dict(zeilen=[dict(schluessel="10", einheit="Stk", menge=400, preis_einheit=4.2),
                                           dict(schluessel="20", einheit="Stk", menge=100, preis_einheit=7.9)],
                                   kennung="x", am="2026-10-20"))
db.vorgang_setzen(a, "Verschickt")
a2 = db.angebot_fassung(a)
assert fassung_vergleich.vorgaenger(db, a2) == a and fassung_vergleich.vorgaenger(db, a) is None
pos2 = db.positionen(a2)
db.position_aendern(next(p["id"] for p in pos2 if p["pos"] == 10), "stueck", 600)
db.positionen_loeschen([next(p["id"] for p in pos2 if p["pos"] == 20)])
db.position_neu(a2, dict(pos=30, artikel="AB-30", bezeichnung="Lasche", profil_id="RE 60x40x3",
                         werkstoff_id="S235-10219", laenge=120.0, stueck=50, schneidweg=200))
v = fassung_vergleich.vergleich(db, a, a2)
arten = {z["artikel"]: z["art"] for z in v["zeilen"]}
assert arten == {"AB-10": "geändert", "AB-20": "entfällt", "AB-30": "neu"}, arten
assert any("Menge 400 → 600" in t for z in v["zeilen"] for t in z["aenderungen"])
h = fassung_vergleich.html(v, nur_aenderungen=True)
assert "AB-30" in h and v["neu"].endswith("-2")
ok("F2 Fassungsvergleich: neu, entfällt, geändert mit Menge alt → neu")

# ------------------------------------------------------------------ F3 Teilekatalog
kat = teilekatalog.katalog(db, "K-1001")
art = {r["artikel"]: r for r in kat}
assert set(art) == {"AB-10", "AB-30"}, art            # AB-20 nur in der abgelösten Fassung
assert art["AB-10"]["nummer"].endswith("-2")
assert teilekatalog.katalog(db, "") == []
csv_t = teilekatalog.csv_text(kat)
assert csv_t.startswith("Artikel;Bezeichnung") and "AB-30" in csv_t
alt_kat = teilekatalog.nach_angebot(kat)
assert set(alt_kat) == {a2}
ok("F3 Teilekatalog: ein Eintrag je Artikel, ohne abgelöste Fassung, CSV")

# ------------------------------------------------------------------ Oberfläche
from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
from rohrlaser.fenster import Hauptfenster  # noqa: E402

hf = Hauptfenster(db, stumm=True)
s = hf.angebot_oeffnen(a2)
assert not s.kopf_bereich.maschinen_knopf.isHidden()
mv = s.maschinen_vergleichen(waehlen="LT7")
assert s.kopf["maschine"] == "LT7", s.kopf["maschine"]
s.maschinen_vergleichen(waehlen="T11")
assert s.kopf["maschine"] == "T11"
assert s._vorige_fassung() == a
fv = s.fassung_vergleichen(zeigen=False)
assert {z["art"] for z in fv["zeilen"]} == {"neu", "entfällt", "geändert"}
d = hf.kunden.teilekatalog("K-1001", zeigen=False)
assert d.tabelle.rowCount() == 2
neu = hf.kunden.katalog_angebot("K-1001", d.liste)
assert neu and {p["artikel"] for p in db.positionen(neu)} == {"AB-10", "AB-30"}
assert db.angebot(neu)["kundennr"] == "K-1001"
ok("Oberfläche F: Maschinen vergleichen und nehmen, Fassungsvergleich, Teilekatalog → neues Angebot")
print("Alle Prüfungen bestanden.")
