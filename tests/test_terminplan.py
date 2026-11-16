"""Prüft „Liefertermin nach freier Kapazität“ (Vorschlag V2, 31.10.2026, terminplan.py):
- T1 verteilen: Laserstunden über die freien Stunden der Wochen ab der Material-Woche
- T2 frühester Termin: Material-Lieferzeit, Kapazität minus beauftragte Aufträge, Vorlauf; eigenes Angebot nicht
  doppelt; volle Wochen als Hinweis; Kundenmaterial ohne Material-Lieferzeit
- T3 Knopf „Termin prüfen …“: Lieferzeit auf die KW übernehmen; Warnung, wenn die Lieferzeit nicht zu halten ist
- T4 Fenster „Beauftragt“: Vorschlag und Knopf „Frühesten Termin übernehmen“

Aufruf: python tests/test_terminplan.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402
from rohrlaser import auftrag as auftrag_fenster, auslastung, feiertage, terminplan  # noqa: E402
from rohrlaser.angebot import KUNDENMATERIAL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


D = datetime.date
# ------------------------------------------------------------------ T1 verteilen
mo = [D(2026, 11, 2), D(2026, 11, 9), D(2026, 11, 16), D(2026, 11, 23)]
w, b = terminplan.verteilen(10, list(zip(mo, (20, 0, 5, 30))), mo[0])
assert w == mo[0] and b == [(mo[0], 20, 10)]
w, b = terminplan.verteilen(10, list(zip(mo, (4, 0, 5, 30))), mo[0])
assert w == mo[3] and [x[2] for x in b] == [4, 0, 5, 1]
w, _ = terminplan.verteilen(10, list(zip(mo, (40, 40, 0, 0))), mo[2])
assert w is None                                     # ab KW 47 nichts frei
assert terminplan.kw_wert(D(2026, 11, 13)) == "46/2026"
ok("T1 Laserstunden auf freie Wochen ab der Material-Woche, passt nicht -> None, KW-Wert")

# ------------------------------------------------------------------ T2 frühester Termin
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
heute = D(2026, 11, 4)                    # Mittwoch KW 45
land = feiertage.VORGABE


def angebot(stueck=100, kunde_material=False):
    a = db.angebot_neu(dict(kunde="Kunde", skonto=0, stange=6000, maschine="T03", nummer=f"2026-{stueck:05d}"))
    db.position_neu(a, dict(pos=10, artikel="T", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1000,
                            stueck=stueck, schneidweg=300, einstiche=2,
                            **(dict(material_herkunft=KUNDENMATERIAL) if kunde_material else {})))
    s = f.angebot_oeffnen(a)
    s.optimieren()
    s.neu_laden()
    f.angebot_schliessen(a)
    return a


neu = angebot(200)
h, _ = auslastung.maschinenzeit(db, db.angebot(neu))
assert h and h > 0
# Kapazität: je Woche 60 % der Laserzeit des neuen Angebots (5 Arbeitstage, nutzbar 100 %)
db.einstellung_setzen("schicht_verfuegbar", 1.0)
db.einstellung_setzen("schicht_samstag", 0.0)
db.einstellung_setzen("schicht_stunden", h * 0.6 / 5)
db.einstellung_setzen("auslastung_vorlauf", 2)
db.einstellung_setzen("termin_material_tage", 3)          # Material Montag 9.11. (KW 46)
t = terminplan.fruehester(db, neu, heute)
assert t.material_ab == D(2026, 11, 9) and abs(t.laser_h - h) < 1e-9
# KW 46 ganz + KW 47 Rest -> Freitag 20.11. + 2 Arbeitstage = Di 24.11.
assert t.datum == D(2026, 11, 24), t
assert "Material ab 09.11.2026" in terminplan.text(t)

# ein beauftragter Auftrag mit Termin in KW 46 belegt die Woche (Laserzeit vor dem Termin, Vorlauf 2)
voll = angebot(300)
db.vorgang_setzen(voll, "Beauftragt")
db.auftrag_setzen(voll, "B", D(2026, 11, 20).isoformat())      # Fr KW 47 - 2 AT = Mi KW 47
t2 = terminplan.fruehester(db, neu, heute)
assert t2.datum > t.datum and "ausgebucht: KW 47" in terminplan.text(t2), terminplan.text(t2)
# eigenes Angebot beauftragt: zählt nicht doppelt
db.vorgang_setzen(neu, "Beauftragt")
db.auftrag_setzen(neu, "N", D(2026, 11, 13).isoformat())
assert terminplan.fruehester(db, neu, heute).datum == t2.datum
db.vorgang_setzen(neu, "Verschickt")
db.auftrag_setzen(neu, None, None)
# Kundenmaterial: kein Einkauf -> ab heute
km = angebot(50, kunde_material=True)
assert terminplan.fruehester(db, km, heute).material_ab == heute
ok("T2 Material-Lieferzeit, freie Kapazität minus Aufträge, Vorlauf; eigenes Angebot nicht doppelt; Kundenmaterial")

# ------------------------------------------------------------------ T3 Knopf „Termin prüfen …“
s = f.angebot_oeffnen(neu)
db.angebot_aendern(neu, "lieferzeit_art", "Kalenderwoche")
db.angebot_aendern(neu, "lieferzeit_wert", "1/2020")           # längst vorbei: nicht zu halten
s.neu_laden()
t3 = s.termin_pruefen(antwort=False)
assert t3.datum is not None and "nicht zu halten" in f.statusBar().currentMessage()
t3 = s.termin_pruefen(antwort=True)
kopf = db.angebot(neu)
assert kopf["lieferzeit_art"] == "Kalenderwoche" and kopf["lieferzeit_wert"] == terminplan.kw_wert(t3.datum)
db.einstellung_setzen("funktion_auslastung", "nein")
s.neu_laden()
knopf = next(w for w in s.findChildren(QPushButton) if w.text() == "Termin prüfen …")
assert knopf.isHidden()
db.einstellung_setzen("funktion_auslastung", "ja")
s.neu_laden()
assert not knopf.isHidden()
ok("T3 Termin prüfen: Warnung bei nicht haltbarer Lieferzeit, KW übernehmen; Knopf nur mit Maschinenauslastung")

# ------------------------------------------------------------------ T4 Fenster „Beauftragt“
d = auftrag_fenster.AuftragDialog(None, db.angebot(neu), land, frueh=t3)
d.mit_termin.setChecked(False)
d.frueh_uebernehmen()
assert d.werte()[1] == t3.datum.isoformat()
d2 = auftrag_fenster.AuftragDialog(None, db.angebot(neu), land, frueh=None)
assert d2.frueh is None
assert f.angebote._termin_frueh(neu).datum is not None
ok("T4 Beauftragt: frühester Termin angezeigt und übernehmbar")
print("Alle Prüfungen bestanden.")
