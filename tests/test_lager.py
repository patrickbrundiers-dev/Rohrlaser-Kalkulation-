"""Materialbestand und Reststücke (Wettbewerbsvergleich P0-1, lager.py): Zugang, Plan mit unabhängiger Kontrolle,
Reservierung ohne Doppelbelegung, Freigabe, Verbrauch mit Rest-Zugang, Storno und Wiederherstellung, Lesemodus,
Altbestand (Datei vor Schema 65).

Aufruf: python tests/test_lager.py
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from rohrlaser import lager, rechnen  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank, Lesemodus  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
k, tab, einst = db.kontext(), db.tabellen(), db.einstellungen()
assert db.einstellung("lager_aktiv") == "nein" and db.einstellung("reste_aktiv") == "nein"    # Vorgabe: aus
PROFIL, WST = "QR 40x40x3", "S235-10219"
kopf = dict(maschine="T03", stange=6000, nummer="2026-00001")


def pos(laenge, stueck, nr=10):
    return dict(pos=nr, artikel=f"T{nr}", profil_id=PROFIL, werkstoff_id=WST, laenge=laenge, stueck=stueck)


positionen = [pos(2000, 6), pos(1500, 2, 20)]
A1, A2 = db.angebot_neu(dict(kopf)), db.angebot_neu(dict(kopf, nummer="2026-00002"))
erg = rechnen.optimieren(kopf, positionen, k, tab, einst)
werte = rechnen.stangen_werte(erg, kopf, positionen, k, tab)
assert not erg["fehler"] and len(erg["stangen"]) == 3

# ------------------------------------------------------------------ Bedarf: unabhängig nachgerechnet
bed = lager.bedarf(erg, werte)
for s, b in zip(erg["stangen"], bed):
    kontrolle = s["end"] + sum(t["laenge"] for t in s["teile"]) + s["verlust"] + s["greif"]
    assert abs(b["bedarf"] - kontrolle) < 1e-6, (b, kontrolle)
    assert b["bedarf"] <= s["stange"]
    assert abs(b["rest"] - (s["stange"] - kontrolle + s["greif"])) < 1e-6

# ------------------------------------------------------------------ Zugang
try:
    lager.zugang(db, "Rest", PROFIL, WST, 4000)
    raise AssertionError("Reststück ohne Einstellung angenommen")
except lager.LagerFehler:
    pass
db.einstellung_setzen("lager_aktiv", "ja")
db.einstellung_setzen("reste_aktiv", "ja")
for falsch in (dict(art="X"), dict(laenge=0), dict(anzahl=0), dict(anzahl=1.5), dict(profil="")):
    a = dict(art="Stange", profil=PROFIL, werkstoff=WST, laenge=6000, anzahl=1, **{})
    a.update(falsch)
    try:
        lager.zugang(db, a["art"], a["profil"], a["werkstoff"], a["laenge"], a["anzahl"])
        raise AssertionError(f"Zugang angenommen: {falsch}")
    except lager.LagerFehler:
        pass
(s1,) = lager.zugang(db, "Stange", PROFIL, WST, 6000, 1, charge="CH-1", lagerort="Regal 3")
r_kurz, r_lang = lager.zugang(db, "Rest", PROFIL, WST, 2500, 1, charge="CH-2") + \
    lager.zugang(db, "Rest", PROFIL, WST, 4300, 1, charge="CH-3")
(fremd,) = lager.zugang(db, "Rest", "QR 50x50x3", WST, 6000)      # anderes Profil: nie eingeplant
assert [lager.posten(db, i)["kennung"] for i in (s1, r_kurz, r_lang)] == ["S-00001", "R-00001", "R-00002"]
assert lager.zugang(db, "Rest", PROFIL, WST, 1000, 2) and len(lager.bestand(db)) == 6      # 2 Reste = 2 Posten

# ------------------------------------------------------------------ Plan
plan = lager.planen(db, A1, erg, werte)
lager.pruefe_plan(plan)
quellen = {b["nr"]: (b["quelle"], b.get("kennung")) for b in plan["stangen"]}
# größter Bedarf zuerst je das kürzeste passende Reststück: 2 × 2.000 + 2 × 1.500 (Stange 1/2) braucht über 4.000 mm,
# passt nur auf R-00002 (4.300); dann die Lagerstange; der Rest 2.500 reicht nur für einen Bedarf bis 2.500 mm
assert all(b["bedarf"] <= b["laenge"] + 1e-6 for b in plan["stangen"] if b["quelle"] != "Neukauf")
assert fremd not in {b["bestand_id"] for b in plan["stangen"]}
aus = [b for b in plan["stangen"] if b["quelle"] != "Neukauf"]
assert plan["aus_lager"] == len(aus) >= 2 and plan["neukauf"] == 3 - len(aus), plan
assert "R-00002" in {b["kennung"] for b in aus}, quellen
# Kontrolle Materialkosten: Ersparnis = Kosten der ersetzten Stangen laut Kalkulation, Lagerwert = €/m × Länge
assert abs(plan["ersparnis"] - sum(werte[b["nr"] - 1]["kosten"] for b in aus)) < 1e-9
for b in aus:
    assert abs(b["lagerwert"] - werte[b["nr"] - 1]["kosten"] / 6000 * b["laenge"]) < 1e-9
ohne_reste = lager.planen(db, A1, erg, werte, mit_resten=False)
assert {b["quelle"] for b in ohne_reste["stangen"]} <= {"Lager", "Neukauf"}

# ------------------------------------------------------------------ Reservieren: keine Doppelbelegung
lager.reservieren(db, A1, "2026-00001", plan)
assert lager.auftrag(db, A1)["status"] == "reserviert"
assert lager.aus_lager(db, A1, erg) == {b["nr"] for b in aus}
r2 = lager.posten(db, r_lang)
assert next(z for z in lager.bestand(db) if z["id"] == r_lang)["verfuegbar"] == 0
# zweites Angebot mit demselben Bedarf: plant das reservierte Reststück nicht ein …
plan2 = lager.planen(db, A2, erg, werte)
assert r_lang not in {b["bestand_id"] for b in plan2["stangen"]}
# … und ein veralteter Plan mit dem schon reservierten Posten wird abgewiesen, ohne etwas zu ändern
vorher = lager.buchungen(db)
try:
    lager.reservieren(db, A2, "2026-00002", plan)
    raise AssertionError("Doppelte Reservierung angenommen")
except lager.LagerFehler as e:
    assert "nicht mehr verfügbar" in str(e)
assert lager.buchungen(db) == vorher and lager.auftrag(db, A2) is None
# Neu planen desselben Angebots ersetzt die eigenen Reservierungen (zählen als frei)
lager.reservieren(db, A1, "2026-00001", lager.planen(db, A1, erg, werte))
assert sum(z["reserviert"] for z in lager.bestand(db)) == len(aus)
# veraltet: anders optimiert
assert not lager.veraltet(db, A1, erg) and lager.veraltet(db, A1, dict(erg, kennung="anders"))
assert lager.aus_lager(db, A1, dict(erg, kennung="anders")) == set()
# Bestand kann nicht unter die Reservierung korrigiert werden
try:
    lager.korrigieren(db, r_lang, 0, "Inventur")
    raise AssertionError("Korrektur unter Reservierung angenommen")
except lager.LagerFehler:
    pass

# ------------------------------------------------------------------ Freigabe (Storno vor Verbrauch)
lager.freigeben(db, A1, "Auftrag verschoben")
assert lager.auftrag(db, A1)["status"] == "freigegeben"
assert all(z["reserviert"] == 0 for z in lager.bestand(db))
try:
    lager.freigeben(db, A1)
    raise AssertionError("doppelte Freigabe angenommen")
except lager.LagerFehler:
    pass
try:
    lager.verbrauchen(db, A1)
    raise AssertionError("Verbrauch ohne Reservierung angenommen")
except lager.LagerFehler:
    pass

# ------------------------------------------------------------------ Verbrauch mit Rest-Zugang
db.einstellung_setzen("rest_min_laenge", 400.0)      # die Reste dieses Plans liegen zwischen 400 und 4.300 mm
plan = lager.planen(db, A1, erg, werte)
lager.reservieren(db, A1, "2026-00001", plan)
bestand_vorher = {z["id"]: z["anzahl"] for z in lager.bestand(db, mit_leeren=True)}
neu = lager.verbrauchen(db, A1)
for b in aus:
    assert lager.posten(db, b["bestand_id"])["anzahl"] == bestand_vorher[b["bestand_id"]] - 1
# Reste ≥ 500 mm (Vorgabe) aus jeder Stange: Länge des Postens − belegt
min_rest = db.einstellung("rest_min_laenge")
erwartet = sorted(round(b["laenge"] - b["belegt"], 1) for b in plan["stangen"] if b["laenge"] - b["belegt"] >= min_rest)
neue_posten = [z for z in lager.bestand(db) if z["kennung"] in neu]
assert erwartet and sorted(z["laenge"] for z in neue_posten) == erwartet, (neue_posten, erwartet)
assert len(erwartet) < len(plan["stangen"]) or min_rest <= min(b["laenge"] - b["belegt"] for b in plan["stangen"])
assert all(z["art"] == "Rest" and z["anzahl"] == 1 and "2026-00001" in z["herkunft"] for z in neue_posten)
assert lager.auftrag(db, A1)["status"] == "verbraucht"
try:
    lager.verbrauchen(db, A1)
    raise AssertionError("doppelter Verbrauch angenommen")
except lager.LagerFehler as e:
    assert "schon gebucht" in str(e)
try:
    lager.reservieren(db, A1, "2026-00001", plan)
    raise AssertionError("Reservieren nach Verbrauch angenommen")
except lager.LagerFehler:
    pass
# Rückverfolgbarkeit: Charge je Verbrauch
chargen = {z["kennung"]: z["charge"] for z in lager.verbrauch_je_charge(db)}
assert chargen.get("R-00002") == "CH-3", chargen

# ------------------------------------------------------------------ Storno des Verbrauchs (Wiederherstellung)
try:
    lager.verbrauch_stornieren(db, A1, "")
    raise AssertionError("Storno ohne Grund angenommen")
except lager.LagerFehler:
    pass
lager.verbrauch_stornieren(db, A1, "falsch gebucht")
for b in aus:
    assert lager.posten(db, b["bestand_id"])["anzahl"] == bestand_vorher[b["bestand_id"]]
assert neu and not [z for z in lager.bestand(db) if z["kennung"] in neu]         # neue Reste wieder weg
assert lager.auftrag(db, A1)["status"] == "reserviert"
# Storno unmöglich, wenn ein neuer Rest schon weiter verwendet wurde
neu = lager.verbrauchen(db, A1)
weiter = next(z for z in lager.bestand(db) if z["kennung"] in neu)
lager.korrigieren(db, weiter["id"], 0, "verschrottet")
try:
    lager.verbrauch_stornieren(db, A1, "falsch gebucht")
    raise AssertionError("Storno trotz weiter verwendetem Rest")
except lager.LagerFehler:
    pass
assert lager.auftrag(db, A1)["status"] == "verbraucht"

# Journal: jede Buchung mit Art
arten = {b["art"] for b in lager.buchungen(db, angebot_id=A1)}
assert {"Reservierung", "Freigabe", "Verbrauch", "Rest-Zugang", "Storno Verbrauch", "Storno Rest-Zugang"} <= arten, arten

# ------------------------------------------------------------------ Angebot löschen gibt Reservierungen frei
lager.zugang(db, "Stange", PROFIL, WST, 6000, 2)
aid = db.angebot_neu(dict(kopf, nummer=None))
lager.reservieren(db, aid, "x", lager.planen(db, aid, erg, werte))
assert sum(z["reserviert"] for z in lager.bestand(db)) > 0
db.angebot_loeschen(aid)
assert sum(z["reserviert"] for z in lager.bestand(db)) == 0

# ------------------------------------------------------------------ Lesemodus
db.lesemodus("Test")
for f in (lambda: lager.zugang(db, "Stange", PROFIL, WST, 6000), lambda: lager.korrigieren(db, s1, 1, "x")):
    try:
        f()
        raise AssertionError("Lesemodus nicht beachtet")
    except Lesemodus:
        pass
assert lager.bestand(db)          # lesen geht
db.lesemodus("")
db.schliessen()

# ------------------------------------------------------------------ Altbestand: Datei vor Schema 65
alt = tmp / "alt.db"
d0 = Datenbank(alt)
d0.schliessen()
con = sqlite3.connect(alt)
for t in lager.TABELLEN:
    con.execute(f"DROP TABLE {t}")
con.execute("PRAGMA user_version=64")
con.commit()
con.close()
d1 = Datenbank(alt)
assert d1.con.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION >= 65
assert lager.bestand(d1) == [] and d1.einstellung("lager_aktiv") == "nein"
d1.schliessen()

# ------------------------------------------------------------------ Oberfläche: Reiter Lager und „Material aus Lager“
from PySide6.QtWidgets import QApplication  # noqa: E402

sys.path.insert(0, str(HIER))
import beispiel_angebot  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp2 = Path(tempfile.mkdtemp())
db2 = Datenbank(tmp2 / "rohrlaser.db")
fenster = Hauptfenster(db2, tmp2, stumm=True)
assert not fenster.reiter.isTabVisible(fenster.reiter.indexOf(fenster.lager))      # Vorgabe aus
s = fenster.angebot_oeffnen(beispiel_angebot.anlegen(db2))
assert s.material_aus_lager() is None                                              # ohne Lager: nichts
db2.einstellung_setzen("lager_aktiv", "ja")
fenster.lager_anwenden()
assert fenster.reiter.isTabVisible(fenster.reiter.indexOf(fenster.lager))
assert s.optimieren()
assert s.material_aus_lager(dialog=lambda d: None) is None                         # erst nach Beauftragt
db2.vorgang_setzen(s.id, "Beauftragt")
s.kopf["vorgang"] = "Beauftragt"
st = s.ergebnis["stangen"][0]
ws = rechnen.stangen_werte(s.ergebnis, s.kopf, s.positionen, s.k, s.tabellen)[0]
# eine passende Lagerstange für die erste Stange des Plans
ids = fenster.lager.zugang(dialog=lambda d: (d.profil.setCurrentText(st["profil"]),
                                            d.werkstoff.setCurrentText(st["werkstoff"]),
                                            d.oberflaeche.setText(st.get("oberflaeche") or ""),
                                            d.laenge.setText(str(int(st["stange"]))), d.charge.setText("CH-9"),
                                            d.speichern(), True)[-1])
assert ids and lager.bestand(db2)[0]["charge"] == "CH-9"
d = s.material_aus_lager(dialog=lambda d: None)
assert d.plan["aus_lager"] >= 1 and d.knoepfe["Reservieren"].isEnabled()
assert d.reservieren() and lager.auftrag(db2, s.id)["status"] == "reserviert"
assert lager.aus_lager(db2, s.id, s.ergebnis)
assert d.verbrauchen() and lager.auftrag(db2, s.id)["status"] == "verbraucht"
assert d.stornieren("Test") and lager.auftrag(db2, s.id)["status"] == "reserviert"
assert d.freigeben() and lager.auftrag(db2, s.id)["status"] == "freigegeben"
fenster.lager.neu_laden()
assert fenster.lager.tabelle.rowCount() == 1 and fenster.lager.buchungen.rowCount() >= 5
print("test_lager OK")
