"""Test: Entfernung nach PLZ (Patrick 11.11.2026, Freigabe alle a): Frachtkosten genauer.

- PLZ-Datei (GeoNames): alle rund 8.300 deutschen PLZ, km = Luftlinie × Umwegfaktor (Einstellung, Vorgabe 1,25, gemessen 11.11.2026);
  unbekannte PLZ = Mittelpunkt der PLZ-Region ('ungefähr'), keine km für andere Länder und unvollständige PLZ.
- Richtwert-Zone nach km statt nach der zweistelligen PLZ-Region (Lippstadt, Detmold, Warburg), eigene Zonen und
  Kunden-Regeln bleiben, Inselzone bleibt.
- Eigene Anlieferung mit den km aus der PLZ.
- Angebot: km aus PLZ gespeichert und in der Karte gezeigt, Feld km von Hand überschreibbar (Zone und Preis folgen),
  Feld leeren = wieder aus PLZ; Umwegfaktor wirkt; Frachtrechner rechnet ohne Eintrag mit den PLZ-km.
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import entfernung, fracht, fracht_angebot, fracht_richtwerte  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Entfernung
assert len(entfernung.punkte()) > 8000
km = {plz: entfernung.km("33129", plz)[0] for plz in ("59555", "32756", "34414", "44135", "20095", "80331")}
assert km == {"59555": 19, "32756": 40, "34414": 70, "44135": 94, "20095": 277, "80331": 577}, km
w, t = entfernung.km("33129", "59555")
assert t == "ca. 19 km (PLZ 33129 → 59555, Luftlinie × 1,25)", t
assert entfernung.km("33129", "59555", umweg="1,35")[0] == 20
assert entfernung.km("33129", "59555", umweg="9")[0] == 19          # außerhalb 1,0–2,0: Vorgabe
assert entfernung.km("33129", "25")[0] is None and entfernung.km("33129", "1010", nach_land="AT")[0] is None
assert entfernung.km("", "59555")[0] is None
neu = "59998"                                                       # nicht in der Liste: Mittelpunkt der Region 59
assert neu not in entfernung.punkte()
w, t = entfernung.km("33129", neu)
assert w and "ungefähr" in t, (w, t)
s = entfernung.ergaenzen(dict(absender_plz="33129", plz="59555", km=12.5))
assert s["km"] == 12.5 and s["km_quelle"] == "von Hand"
ok("Entfernung nach PLZ: Lippstadt 19, Detmold 40, Warburg 70, Dortmund 94, Hamburg 277, München 577 km; "
   "Umwegfaktor wirkt, unbekannte PLZ ungefähr, Ausland und '25' ohne km, von Hand bleibt")

# ------------------------------------------------------------------ Zone nach km
app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
fenster = Hauptfenster(db, stumm=True)
db.einstellung_setzen("absender_plz", "33129")
db.fracht_richtwerte_laden()
fd = db.fracht_daten()
EUR = [dict(lht_id="EUR", anzahl=1)]


def preis(plz, **k):
    return fracht.rechnen(fd, dict(dict(datum="2026-11-11", land="DE", plz=plz, absender_plz="33129",
                                        absender_land="DE", versandart="Palettenversand", netto=190, lht=EUR,
                                        leistungen={}), **k))


vorher = {plz: fracht.zone_finden(fd, "DE", plz)["zone"]["zone_id"] for plz in ("59555", "32756", "34414")}
assert vorher == {"59555": "RW0B", "32756": "RW0A", "34414": "RW1"}, vorher
e = {plz: preis(plz) for plz in ("59555", "32756", "34414", "32052")}
assert {p: (x["gesamt"], x["zone_empfang"]["zone"]["zone_id"]) for p, x in e.items()} == {
    "59555": (65.0, "RW0A"), "32756": (65.0, "RW0A"), "34414": (80.0, "RW0B"), "32052": (65.0, "RW0A")}, e
assert e["59555"]["hinweise"][0].startswith("Entfernung ca. 19 km")
assert any("statt Zone RW0B nach PLZ-Region 59*" in h for h in e["59555"]["hinweise"]), e["59555"]["hinweise"]
assert e["59555"]["zone_empfang"]["text"] == "Zone RW0A Palette bis 50 km (nach Entfernung)"
assert preis("59555", km=60)["gesamt"] == 80.0                        # von Hand eingetragen: Zone nach diesem Wert
assert preis("25980")["gesamt"] == 200.0                              # Insel bleibt
assert preis("25")["gesamt"] == 200.0                                 # PLZ-Bereich: wie bisher (teurere Zone)
ok("Zone nach km: Lippstadt 80 € -> 65 €, Warburg 100 € -> 80 €, Herford (47 km) und Detmold bleiben 65 €; "
   "Hinweis nennt die alte Zone; "
   "eingetragene km gelten; Insel und PLZ-Bereich wie bisher")

db.neu("fracht_zonen", dict(zone_id="NAH", bezeichnung="Eigene Nahzone", land="DE", aktiv="ja", bemerkung="von Hand"))
db.neu("fracht_plz", dict(land="DE", plz_von="59555", zone_id="RW0B", bemerkung="von Hand"))
fd = db.fracht_daten()
assert preis("59555")["zone_empfang"]["zone"]["zone_id"] == "RW0B"   # eigene Regel (genaue PLZ) bleibt
ok("Eigene PLZ-Regel (von Hand) bleibt bei ihrer Zone")
with db.con:
    db.con.execute("DELETE FROM fracht_plz WHERE plz_von='59555'")
fd = db.fracht_daten()


def eigen(plz, **k):
    return fracht.rechnen(fd, dict(dict(datum="2026-11-11", land="DE", plz=plz, absender_plz="33129",
                                        absender_land="DE", versandart="Eigene Anlieferung", netto=190, lht=EUR,
                                        leistungen={}), **k))


lp = eigen("59555")
assert lp["gesamt"] == 58.0 and lp["snapshot"]["tarif"]["tarif_id"] == fracht_richtwerte.TARIF_EIGEN, lp
ok("Eigene Anlieferung Lippstadt: 20 € + 2 × 19 km × 1,00 € = 58 € (vorher 75 km der Zone = 170 €)")

# ------------------------------------------------------------------ Angebot
aid = beispiel_angebot.anlegen(db)
seite = fenster.angebot_oeffnen(aid)
kb = seite.kopf_bereich
seite.fracht_ziel_setzen("59555", "DE")
seite.fracht_auto_setzen(True)
d = fracht_angebot.daten(db.angebot(aid))
assert d["sendung"]["km"] == 19 and d["sendung"]["km_quelle"] == "PLZ", d["sendung"]
assert "RW0A" in d["zone"] and "Entfernung ca. 19 km" in kb.fracht_text.text(), (d["zone"], kb.fracht_text.text())
assert kb.fracht_km.text() == "" and kb.fracht_km.placeholderText() == "19"
auto20 = db.angebot(aid)["fracht"]
seite.fracht_km_setzen("60")
a = db.angebot(aid)
d = fracht_angebot.daten(a)
assert a["fracht_km"] == 60 and d["sendung"]["km_quelle"] == "von Hand" and "RW0B" in d["zone"], d
assert a["fracht"] > auto20 and kb.fracht_km.text() == "60"
seite.fracht_km_setzen("abc")                                         # keine Zahl: Meldung, nichts geändert
assert db.angebot(aid)["fracht_km"] == 60
seite.fracht_km_setzen("")
a = db.angebot(aid)
assert a["fracht_km"] is None and a["fracht"] == auto20 and fracht_angebot.daten(a)["sendung"]["km"] == 19
ok("Angebot: km aus PLZ gespeichert und angezeigt (grau 19), von Hand 60 km -> Zone RW0B und höhere Fracht, "
   "Feld leeren = wieder aus PLZ")

db.einstellung_setzen("fracht_umwegfaktor", 1.35)
seite.fracht_auto_setzen(False)
seite.fracht_auto_setzen(True)
assert fracht_angebot.daten(db.angebot(aid))["sendung"]["km"] == 20
db.einstellung_setzen("fracht_umwegfaktor", 1.25)
ok("Umwegfaktor aus den Einstellungen wirkt im Angebot (1,35: 20 km)")

# ------------------------------------------------------------------ Frachtrechner
r = fenster.fracht.rechner
r.daten = db.fracht_daten()
r.abs_plz.setText("33129")
r.plz.setText("59555")
r.km.setText("")
r.rechnen()
assert r.ergebnis["eingaben"]["km"] == 19 and r.km.placeholderText() == "leer = aus den PLZ (19 km)"
assert any(h.startswith("Entfernung ca. 19 km") for h in r.ergebnis["hinweise"])
ok("Frachtrechner: ohne Eintrag 19 km aus den PLZ, im Feld grau angezeigt, Hinweis im Ergebnis")

fenster.close()
print("OK: Entfernung nach PLZ")
