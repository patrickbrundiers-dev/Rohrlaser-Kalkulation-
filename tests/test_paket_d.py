"""Paket D Fertigung und Rückmeldung (Plan Phase 3 und 4, Patrick 13.11.2026 „Alles einbauen“):

- D4 CAM-004: verbrauchte Stangen aus der Rückmeldung der Auslastung (Art „Stangen“) als Ist-Stangen der
  Nachkalkulation, beim Versand vorbelegt bzw. per Knopf „Verbrauchte Stangen übernehmen“
- D5 OFFER-012: Kundenwert je Kunde und Jahr (Umsatz der Aufträge, DB nur aus der Nachkalkulation)
- D6 MAT-018: Sammelbedarf an Stangen je Woche über alle beauftragten Aufträge ohne bereites Material, Reste nur
  gemeldet (kein Restelager), CSV
- D7 MACH-008: rüstgünstige Reihenfolge der Abmessungen im Fertigungslos als Vorschlag für die Werkstatt
- D8 CAM-006: stabiler Stangenplan bei leicht geänderter Menge (nie mehr Stangen als neu gerechnet), abschaltbar

Aufruf: python tests/test_paket_d.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import csv
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import types  # noqa: E402

from rohrlaser import (auslastung_austausch as aa, fertigung, fertigungslos as fl, kundenwert,  # noqa: E402
                       materialbedarf as mb, nachkalkulation as nk, preis_simulator, rechnen)
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
ordner = tmp / "Auslastung"
db.einstellung_setzen("auslastung_ordner", str(ordner))
ordner.mkdir()

# ------------------------------------------------------------------ D4 verbrauchte Stangen
a = db.angebot_neu(dict(kunde="Muster GmbH", skonto=0, stange=6000, maschine="T03", nummer="2026-00777"))
db.position_neu(a, dict(pos=1, artikel="S-1", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=1250,
                        stueck=40, schneidweg=300, einstiche=2))
s = f.angebot_oeffnen(a)
assert s.optimieren()
kopf = db.angebot(a)
zeilen = [z for z in aa.inhalt(db, kopf) if z["Art"] == aa.STANGEN]
assert len(zeilen) == 1 and int(zeilen[0]["Stangen"]) >= 1
soll = int(zeilen[0]["Stangen"])
spalten = ["Format", "Art", "Stand", "Auftragsnummer", "Profilform", "Maß a [mm]", "Maß b [mm]", "Wand [mm]",
           "Werkstoff", "Stangenlänge [mm]", "Stangen"]
with open(ordner / aa.RUECKMELDUNG, "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, spalten, delimiter=";", extrasaction="ignore")
    w.writeheader()
    w.writerow(dict(zeilen[0], Format="2", Art="Stangen", Stand="13.11.2026 16:00", Auftragsnummer="2026-00777",
                    Stangen=str(soll + 1)))
    w.writerow(dict(zeilen[0], Format="2", Art="Stangen", Stand="13.11.2026 16:00", Auftragsnummer="anderer",
                    Stangen="9"))
r = aa.rueckmeldung(db)
assert len(r["stangen"]) == 2
k, tab, _ = preis_simulator.grundlage(db, kopf)
gr = nk.gruppen(kopf["ergebnis"], kopf, db.positionen(a), k, tab)
ist = aa.ist_stangen(db, kopf, k, r)
assert ist == {gr[0]["schluessel"]: soll + 1}, (ist, gr)
assert aa.ist_stangen(db, dict(kopf, nummer="gibt es nicht"), k, r) == {}
ok(f"D4 Rückmeldung Art Stangen: {soll + 1} verbrauchte statt {soll} geplante Stangen der Gruppe zugeordnet")

s.neu_laden()
nkseite = s.nachkalk
nkseite.neu_laden()
assert nkseite.stangen_knopf.isVisibleTo(nkseite) and f"({soll + 1})" in nkseite.stangen_knopf.text()
assert nkseite.stangen_uebernehmen()
assert db.angebot(a)["nachkalkulation"]["stangen"] == {gr[0]["schluessel"]: soll + 1}
ok("D4 Nachkalkulation: Knopf „Verbrauchte Stangen übernehmen“ trägt die Ist-Stangen ein")

# ------------------------------------------------------------------ D5 Kundenwert
def angebot(kunde, nr, datum, vorgang, vk, nk_db=None):
    i = db.angebot_neu(dict(kunde=kunde, kundennr=nr, datum=datum, maschine="T03"))
    db.vorgang_setzen(i, vorgang)
    db.kennzahlen_merken(i, vk, "aktuell")
    if nk_db:
        db.nachkalkulation_speichern(i, dict(soll=dict(db=list(nk_db), erloes=[vk, vk, True])))
    return i


angebot("Alpha Rohr", "K1", "2025-03-01", "Beauftragt", 1000.0, (300.0, 250.0))
angebot("Alpha Rohr", "K1", "2026-02-01", "Beauftragt", 2000.0, (600.0, 700.0))
angebot("Alpha Rohr", "K1", "2026-05-01", "Beauftragt", 500.0)
angebot("Alpha Rohr", "K1", "2026-06-01", "Abgelehnt", 900.0)
angebot("Beta Stahl", "K2", "2026-04-01", "Beauftragt", 5000.0)
z26 = {z["kunde"]: z for z in kundenwert.zeilen(db, "2026")}
al = z26["Alpha Rohr"]
assert (al["angebote"], al["auftraege"], al["umsatz"], al["db_ist"], al["db_soll"], al["nachkalkuliert"]) == \
    (3, 2, 2500.0, 700.0, 600.0, 1), al
assert abs(al["quote"] - 2 / 3) < 1e-9 and abs(al["db_quote"] - 0.35) < 1e-9
be = z26["Beta Stahl"]
assert be["umsatz"] == 5000.0 and be["db_ist"] is None and be["db_quote"] is None   # ohne Nachkalkulation: leer
assert list(z26) .index("Alpha Rohr") < list(z26).index("Beta Stahl")        # nach DB Ist, dann Umsatz
assert {z["jahr"] for z in kundenwert.zeilen(db) if z["kunde"] == "Alpha Rohr"} == {"2025", "2026"}
assert "2026" in kundenwert.jahre(db) and "2025" in kundenwert.jahre(db)
seite = next(x for x in f.seiten if x.t.name == "kunden")
d = seite.kundenwert(dialog=lambda d_: None)
assert d.tab.rowCount() == len(d.zeilen) > 0 and d.jahr.currentData() == "2026"
ok("D5 Kundenwert 2026: Alpha 3 Angebote, 2 Aufträge, Umsatz 2.500 €, DB Ist 700 € (1 von 2 nachkalkuliert); "
   "Beta ohne Nachkalkulation ohne DB")

# ------------------------------------------------------------------ D6 Materialbedarf je Woche
f.angebot_schliessen(a)
db.auftrag_setzen(a, "", "2026-11-25")
db.vorgang_setzen(a, "Beauftragt")
b = db.angebot_neu(dict(kunde="Zweite KG", skonto=0, stange=6000, maschine="T03", nummer="2026-00778"))
db.auftrag_setzen(b, "", "2026-11-26")
db.position_neu(b, dict(pos=1, artikel="S-2", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", laenge=900,
                        stueck=30, schneidweg=200, einstiche=1))
sb = f.angebot_oeffnen(b)
assert sb.optimieren()
f.angebot_schliessen(b)
db.vorgang_setzen(b, "Beauftragt")
zeilen = mb.bedarf(db)
kw = [z for z in zeilen if z["profil"] == "RR 42,4x2,0"]
assert len(kw) == 1 and kw[0]["woche"] == "KW 48/2026" and sorted(kw[0]["auftraege"]) == ["2026-00777", "2026-00778"], kw
n_b = len(db.angebot(b)["ergebnis"]["stangen"])
assert kw[0]["stangen"] == soll + n_b and kw[0]["gewicht"] > 0 and kw[0]["rest_m"] >= 0
fertigung.setzen(db, b, "Freigegeben")
fertigung.setzen(db, b, "Material bereit")
kw2 = [z for z in mb.bedarf(db) if z["profil"] == "RR 42,4x2,0"]
assert kw2[0]["stangen"] == soll and kw2[0]["auftraege"] == ["2026-00777"]
assert [z for z in mb.bedarf(db, alle=True) if z["profil"] == "RR 42,4x2,0"][0]["stangen"] == soll + n_b
assert mb.csv_text(kw2).splitlines()[1].startswith("KW 48/2026;RR 42,4x2,0;S235-10219;;6000;")
dlg = f.fertigung.materialbedarf(dialog=lambda d_: None)
assert len(dlg.zeilen) >= 1 and not dlg.alle.isChecked()
ziel = tmp / "bedarf.csv"
assert dlg.speichern(str(ziel)) and ziel.read_text(encoding="utf-8-sig").startswith("Woche;Profil")
ok(f"D6 Materialbedarf KW 48/2026: {soll + n_b} Stangen aus 2 Aufträgen, nach „Material bereit“ nur noch {soll}; "
   "Rest in m gemeldet, CSV")

# ------------------------------------------------------------------ D7 Reihenfolge im Fertigungslos
k7 = types.SimpleNamespace(
    profile={"RR 40x2": dict(form="RR", a=40), "QR 40x40x3": dict(form="QR", a=40), "RR 60x2": dict(form="RR", a=60)},
    werkstoffe={"S235": dict(kategorie="Stahl"), "1.4301": dict(kategorie="Edelstahl")})
plan = [("RR 40x2", "S235"), ("RR 40x2", "1.4301"), ("RR 60x2", "S235"), ("QR 40x40x3", "1.4301"),
        ("QR 40x40x3", "S235")]
los7 = dict(k=k7, ergebnis=dict(stangen=[dict(profil=p_, werkstoff=w_, stange=6000) for p_, w_ in plan]))
r7 = fl.reihenfolge(los7)
assert r7 and len(r7["folge"]) == 5 and r7["punkte"] <= r7["punkte_plan"] and r7["wechsel"] < r7["wechsel_plan"], r7
folge = [(x["profil"], x["werkstoff"]) for x in r7["folge"]]
assert sorted(folge) == sorted(plan)
kat = [k7.werkstoffe[w_]["kategorie"] for _, w_ in folge]
assert sum(1 for x, y in zip(kat, kat[1:]) if x != y) == 1, folge        # Werkstoffgruppe nur einmal wechseln
txt = fl.reihenfolge_text(r7)
assert txt[0].startswith("Rüstgünstige Reihenfolge (Vorschlag): ") and len(txt) == 6 and txt[1].startswith("1. ")
assert fl.reihenfolge(dict(k=k7, ergebnis=dict(stangen=[dict(profil="RR 40x2", werkstoff="S235", stange=6000)]))) is None
ok(f"D7 Reihenfolge: {r7['wechsel']} statt {r7['wechsel_plan']} Wechsel von Werkstoffgruppe oder Profilform, "
   "Werkstoffgruppe nur einmal gewechselt, Text für die Werkstatt")

# ------------------------------------------------------------------ D8 stabile Stangenpläne
c = db.angebot_neu(dict(kunde="Stabil AG", skonto=0, stange=6000, maschine="T03"))
for i, (lg, n) in enumerate(((1700, 9), (1100, 11), (800, 13), (450, 7)), 1):
    db.position_neu(c, dict(pos=10 * i, artikel=f"ST-{i}", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                            laenge=lg, stueck=n, schneidweg=200, einstiche=1))
sc = f.angebot_oeffnen(c)
assert sc.optimieren()


def belegungen(erg):
    return [sorted((t["ref"], t["laenge"]) for t in st["teile"]) for st in erg["stangen"]]


alt = belegungen(db.angebot(c)["ergebnis"])
p4 = next(p_ for p_ in db.positionen(c) if p_["artikel"] == "ST-2")
db.position_aendern(p4["id"], "stueck", 12)             # ein Stück mehr
sc.neu_laden()
assert sc.optimieren()
erg8 = db.angebot(c)["ergebnis"]
neu = belegungen(erg8)
frisch = rechnen.optimieren(sc.kopf, sc.positionen, sc.k, sc.tabellen, sc.einst)
assert len(neu) <= len(frisch["stangen"]), (len(neu), len(frisch["stangen"]))
gleich = sum(1 for b in neu if b in alt)
assert gleich >= len(alt) - 1, (gleich, len(alt))
assert sum(len(b) for b in neu) == 9 + 12 + 13 + 7
bew = " ".join(z["bewertung"] for z in erg8["auswertung"])
assert "Plan stabil: " in bew and "belegt wie bisher" in bew, bew
ok(f"D8 ein Teil mehr: {gleich} von {len(alt)} Stangen wie bisher, {len(neu)} Stangen (neu gerechnet "
   f"{len(frisch['stangen'])})")

db.position_aendern(p4["id"], "stueck", 40)              # große Änderung: neu rechnen
sc.neu_laden()
assert sc.optimieren()
assert "Plan stabil" not in " ".join(z["bewertung"] for z in db.angebot(c)["ergebnis"]["auswertung"])
db.position_aendern(p4["id"], "stueck", 39)
sc.neu_laden()
sc.einst = dict(sc.einst, stangenplan_stabil="nein")
assert sc.optimieren()
assert "Plan stabil" not in " ".join(z["bewertung"] for z in db.angebot(c)["ergebnis"]["auswertung"])
ok("D8 große Änderung bzw. Einstellung „nein“: Plan wird neu gerechnet")
print("Alle Prüfungen bestanden.")
