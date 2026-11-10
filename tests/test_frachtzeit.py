"""Prüft „Lieferdatum ab Werk und frei Haus“ (Patrick 10.11.2026, Freigabe F1a–F5a, frachtzeit.py):
- F1 Frachtlaufzeit: Tarif (Feld laufzeit_tage im Snapshot der Frachtberechnung) vor Vorgabe Inland/Ausland;
  0 bei ab Werk, Abholung, frei Frachtführer, „keine Fracht“ und Eigener Anlieferung
- F2 Rechnen in Arbeitstagen ohne Wochenende und Feiertage, vorwärts (frei Haus) und rückwärts (ab Werk)
- F3 Kundentermin aus der Lieferzeit: bei frei Haus wird ab Werk rückwärts gerechnet
- F4 Datenbank: Spalten liefertermin_frei_haus und fracht_tarife.laufzeit_tage, auftrag_setzen rechnet frei Haus
- F5 Texte: Lieferzeit mit (frei Haus)/(ab Werk), AB-Termin mit Lieferart
- F6 Fenster „Beauftragt“: ab Werk und frei Haus gekoppelt, Ergebnis mit beiden Daten
- F7 Ablauf: Beauftragen speichert frei Haus, Liste und Fertigung zeigen es, AB nennt frei Haus

Aufruf: python tests/test_frachtzeit.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QDate  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser import auftrag, feiertage, fertigung, frachtzeit, pdf  # noqa: E402
from rohrlaser.angebot import lieferzeit_text  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fracht_angebot import BERECHNET, KEINE  # noqa: E402
from rohrlaser.stammdaten import KALENDERWOCHE  # noqa: E402


def ok(t):
    print("OK:", t)


D = datetime.date
EINST = {"absender_land": "DE"}

# ------------------------------------------------------------------ F1 Laufzeit
lz = frachtzeit.laufzeit({}, {}, EINST)
assert lz == (1, "Vorgabe Inland", True), lz
assert frachtzeit.laufzeit({"fracht_land": "AT"}, {}, EINST).tage == 3
assert frachtzeit.laufzeit({}, {"land": "CH"}, EINST).tage == 3
assert frachtzeit.laufzeit({}, {}, dict(EINST, frachtzeit_inland=2)).tage == 2
assert frachtzeit.laufzeit({}, {}, dict(EINST, frachtzeit_inland=0)).tage == 0
for lb in ("ab Werk", "Abholung", "frei Frachtführer"):
    x = frachtzeit.laufzeit({}, {"lieferbedingung": lb}, EINST)
    assert x.tage == 0 and not x.frei_haus and lb in x.quelle, x
assert frachtzeit.laufzeit({}, {"lieferbedingung": "unfrei"}, EINST).frei_haus     # unfrei: wird zugestellt
assert not frachtzeit.laufzeit({"fracht_modus": KEINE}, {}, EINST).frei_haus
snap = dict(sendung=dict(versandart="Stückgut"), snapshot=dict(tarif=dict(tarif_id="T-X", laufzeit_tage=2)))
x = frachtzeit.laufzeit({"fracht_modus": BERECHNET, "fracht_sendung": json.dumps(snap)}, {}, EINST)
assert x == (2, "Tarif T-X", True), x
snap["snapshot"]["tarif"]["laufzeit_tage"] = None
assert frachtzeit.laufzeit({"fracht_sendung": json.dumps(snap)}, {}, EINST).quelle == "Vorgabe Inland"
snap["sendung"]["versandart"] = frachtzeit.EIGEN
assert frachtzeit.laufzeit({"fracht_sendung": snap}, {}, EINST) == (0, frachtzeit.EIGEN, True)
assert "1 Arbeitstag Fracht" in frachtzeit.hinweis(lz) and "ab Werk" in frachtzeit.hinweis(
    frachtzeit.laufzeit({}, {"lieferbedingung": "Abholung"}, EINST))
ok("F1 Laufzeit: Tarif vor Vorgabe Inland 1 / Ausland 3, 0 bei ab Werk/Abholung/keine Fracht/Eigene Anlieferung")

# ------------------------------------------------------------------ F2 Arbeitstage
fr = D(2026, 11, 13)                                   # Freitag
assert frachtzeit.frei_haus(fr, 1) == D(2026, 11, 16)  # Montag
assert frachtzeit.frei_haus(fr, 3) == D(2026, 11, 18)
assert frachtzeit.frei_haus(fr, 0) == fr
assert frachtzeit.ab_werk(D(2026, 11, 16), 1) == fr
assert frachtzeit.ab_werk(D(2026, 11, 18), 3) == fr
LAND = feiertage.VORGABE
assert frachtzeit.frei_haus(D(2026, 12, 24), 1, LAND) == D(2026, 12, 28)  # 25./26. Feiertag, 27. Sonntag
assert frachtzeit.ab_werk(D(2026, 12, 28), 1, LAND) == D(2026, 12, 24)
ok("F2 frei Haus = ab Werk + Arbeitstage (ohne Wochenende/Feiertage), rückwärts genauso")

# ------------------------------------------------------------------ F3 Kundentermin
heute = D(2026, 11, 10)
kopf = dict(lieferzeit_art=KALENDERWOCHE, lieferzeit_wert="48/2026")      # Freitag 27.11.
assert auftrag.termin_vorschlag(kopf, heute) == D(2026, 11, 27)            # ohne Fracht wie bisher
assert auftrag.termin_vorschlag(kopf, heute, lz=lz) == D(2026, 11, 26)     # frei Haus: einen Arbeitstag früher ab Werk
abholung = frachtzeit.laufzeit({}, {"lieferbedingung": "Abholung"}, EINST)
assert auftrag.termin_vorschlag(kopf, heute, lz=abholung) == D(2026, 11, 27)
assert auftrag.termin_vorschlag(dict(kopf, liefertermin="2026-12-01"), heute, lz=lz) == D(2026, 12, 1)
assert auftrag.termin_vorschlag({}, heute, lz=lz) == heute + datetime.timedelta(days=14)
assert frachtzeit.kundentermin(D(2026, 11, 26), lz) == D(2026, 11, 27)
assert frachtzeit.aus_kundentermin(D(2026, 11, 27), abholung) == D(2026, 11, 27)
ok("F3 Lieferzeit meint bei frei Haus die Ankunft: ab Werk rückwärts; gespeicherter Termin geht vor")

# ------------------------------------------------------------------ F4 Datenbank
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert SCHEMA_VERSION >= 79
spalten = {r[1] for r in db.con.execute("PRAGMA table_info(angebote)")}
assert "liefertermin_frei_haus" in spalten
assert "laufzeit_tage" in {r[1] for r in db.con.execute("PRAGMA table_info(fracht_tarife)")}
assert db.einstellung("frachtzeit_inland") == 1 and db.einstellung("frachtzeit_ausland") == 3
db.neu("kunden", dict(kundennr="K1", name="Haus GmbH", land="DE", lieferbedingung="frei Haus"))
db.neu("kunden", dict(kundennr="K2", name="Abhol GmbH", land="DE", lieferbedingung="Abholung"))
a1 = db.angebot_neu(dict(kunde="Haus GmbH", kundennr="K1"))
a2 = db.angebot_neu(dict(kunde="Abhol GmbH", kundennr="K2"))
db.auftrag_setzen(a1, "PO", "2026-11-13")
assert db.angebot(a1)["liefertermin_frei_haus"] == "2026-11-16"
db.auftrag_setzen(a1, "PO", "2026-11-13", "2026-11-20")                   # von Hand: bleibt
assert db.angebot(a1)["liefertermin_frei_haus"] == "2026-11-20"
db.auftrag_setzen(a1, "PO", None, "2026-11-20")
assert db.angebot(a1)["liefertermin_frei_haus"] is None
db.auftrag_setzen(a2, None, "2026-11-13")
assert db.angebot(a2)["liefertermin_frei_haus"] == "2026-11-13"            # Abholung: gleiches Datum
assert frachtzeit.termine(db, dict(id=a2, kundennr="K2", liefertermin="2026-11-13")) == (fr, fr)
assert frachtzeit.termine(db, dict(id=a1, liefertermin="2026-11-13"))[1] == D(2026, 11, 16)   # alt: gerechnet
ok("F4 Schema 79: Spalten, Einstellungen, auftrag_setzen rechnet frei Haus (von Hand bleibt, Abholung = ab Werk)")

# ------------------------------------------------------------------ F5 Texte
k = dict(lieferzeit_art=KALENDERWOCHE, lieferzeit_wert="48/2026")
assert lieferzeit_text(k) == "Lieferzeit: KW 48/2026."
assert lieferzeit_text(k, frachtzeit.FREI_HAUS) == "Lieferzeit: KW 48/2026 (frei Haus)."
assert lieferzeit_text(dict(lieferzeit_zusatz="nach Absprache"), frachtzeit.AB_WERK) == "Lieferzeit: nach Absprache."
assert pdf.ab_termin_text("2026-11-16", "frei Haus") == "16.11.2026 (KW 47) frei Haus"
assert pdf.ab_termin_text("2026-11-16") == "16.11.2026 (KW 47)"
ok("F5 Lieferzeit mit (frei Haus)/(ab Werk), AB-Termin mit Lieferart")

# ------------------------------------------------------------------ F6 Fenster „Beauftragt“
d = auftrag.AuftragDialog(None, dict(nummer="X", lieferzeit_art=KALENDERWOCHE, lieferzeit_wert="48/2026"),
                          lz=frachtzeit.Laufzeit(2, "Tarif T", True))
assert d.termin.date().toPython() == D(2026, 11, 25) and d.frei_haus.date().toPython() == D(2026, 11, 27)
d.termin.setDate(QDate(2026, 11, 13))
assert d.frei_haus.date().toPython() == D(2026, 11, 17)
d.frei_haus.setDate(QDate(2026, 11, 23))                                   # Wunsch beim Kunden: Montag
assert d.termin.date().toPython() == D(2026, 11, 19)
assert d.werte() == (None, "2026-11-19", "2026-11-23")
d.mit_termin.setChecked(False)
assert d.werte() == (None, None, None) and not d.frei_haus.isEnabled()
d = auftrag.AuftragDialog(None, dict(nummer="Y"), lz=abholung)
d.mit_termin.setChecked(True)
assert not d.frei_haus.isEnabled() and d.frei_haus.date() == d.termin.date()
ok("F6 Beauftragt: ab Werk und frei Haus gekoppelt, Wunsch beim Kunden rechnet ab Werk rückwärts")

# ------------------------------------------------------------------ F7 Ablauf im Programm
from rohrlaser.fenster import Hauptfenster  # noqa: E402

db.einstellung_setzen("ablageordner", str(tmp / "Ablage"))
f = Hauptfenster(db, stumm=True)
a = db.angebot_neu(dict(kunde="Haus GmbH", kundennr="K1", skonto=0, stange=6000))
db.position_neu(a, dict(pos=10, artikel="T-100", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                        stueck=10, schneidweg=300, einstiche=2))
s = f.angebot_oeffnen(a)
s.optimieren()
s.neu_laden()
s.angebot_pdf(oeffnen=False)
assert f.angebote.vorgang_setzen("Beauftragt", angebot_id=a, auftrag=("BE-1", "2026-11-13"))
assert db.angebot(a)["liefertermin_frei_haus"] == "2026-11-16"
liste = f.angebote
liste.neu_laden()
titel = [t for t, *_ in liste.SPALTEN]
r = next(i for i, z in enumerate(liste.modell.zeilen) if z["id"] == a)
assert liste.modell.data(liste.modell.index(r, titel.index("ab Werk"))) == "13.11.2026"
assert liste.modell.data(liste.modell.index(r, titel.index("frei Haus"))) == "16.11.2026"
assert not liste.ansicht.isColumnHidden(titel.index("frei Haus"))
z = next(z for z in fertigung.uebersicht(db) if z["id"] == a)
assert z["liefertermin"] == "2026-11-13" and z["liefertermin_frei_haus"] == "2026-11-16"
s.neu_laden()
p = s.auftragsbestaetigung_pdf()
assert p is not None
import pypdfium2 as pdfium  # noqa: E402

doc = pdfium.PdfDocument(str(p))
t = "\n".join(seite.get_textpage().get_text_range() for seite in doc)
doc.close()
assert "16.11.2026 (KW 47) frei Haus" in t, t
ok("F7 Beauftragt speichert frei Haus, Angebotsliste und Fertigung zeigen beide Daten, AB nennt frei Haus")
print("Alle Prüfungen bestanden.")
