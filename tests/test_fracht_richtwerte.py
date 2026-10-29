"""Test: Richtwerte Palettenversand (Recherche 10/2026, Marktpreise + 10 % Puffer, Zonen nach Entfernung).

- Knopf 'Richtwerte laden' ersetzt alle BEISPIEL-Zeilen, eigene Einträge bleiben, Absender-PLZ und Versandart werden
  gesetzt; unbekannte Absender-PLZ ändert nichts.
- Preise ab 33129 Delbrück: 1 Palette je Ring 65 (bis 50 km) / 80 (bis 100 km) / 100 / 115 / 125 €, mehrere Paletten günstiger je Stück, schwere
  Palette +40 € je Stellplatz, Langgut 6 m = 3 Stellplätze + Überlänge, Insel = teuerster Ring + Inselzuschlag;
  Diesel und Maut sind im Preis (keine eigenen Zuschläge).
- Eigene Anlieferung (Versandart, bis 200 km): 20 € je Sendung + 2,00 € je km Entfernung (Hin- und Rückfahrt);
  ohne Entfernung die typische Entfernung der Zone; weiter weg kein Tarif.
- Einmalige Umstellung beim Start (Patrick 29.10.2026, 3b): alte Richtwerte ohne Nahbereich werden mit Sicherung neu
  geladen, eigene Einträge bleiben.
- Frachtzonen auf Standard zurücksetzen: Zonen und PLZ-Zuordnungen wie nach dem Laden, eigene weg, Sicherung vorher.
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
from rohrlaser import fracht, fracht_angebot, fracht_richtwerte  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
fenster = Hauptfenster(db, stumm=True)

# eigene Zone und eigener Zuschlag bleiben
db.neu("fracht_zonen", dict(zone_id="EIGEN", bezeichnung="Eigene Zone", land="DE", aktiv="ja", bemerkung="von Hand"))
alt = {t: len(db.zeilen(t)) for t in ("fracht_tarife", "fracht_zonen", "fracht_zuschlaege")}
try:
    db.fracht_richtwerte_laden("00")
    raise AssertionError("unbekannte PLZ angenommen")
except ValueError as e:
    assert "unbekannt" in str(e)
assert {t: len(db.zeilen(t)) for t in alt} == alt
ok("Unbekannte Absender-PLZ: Fehlermeldung, Frachtdaten unverändert")

db.einstellung_setzen("absender_plz", "33129")
weg, neu = fenster.fracht.historie.richtwerte()        # Knopf 'Richtwerte laden' (stumm: ohne Rückfrage)
assert weg > 0 and neu > 100, (weg, neu)
for t in ("fracht_laender", "fracht_zonen", "fracht_plz", "fracht_tarife", "fracht_preise", "fracht_lht",
          "fracht_zuschlaege", "fracht_dienstleister"):
    assert not [z for z in db.zeilen(t) if (z.get("bemerkung") or "").startswith("BEISPIEL")], t
assert any(z["zone_id"] == "EIGEN" for z in db.zeilen("fracht_zonen"))
assert sorted(t["tarif_id"] for t in db.zeilen("fracht_tarife")) == [fracht_richtwerte.TARIF_EIGEN, fracht_richtwerte.TARIF_PAKET,
                                                                       fracht_richtwerte.TARIF]
assert db.einstellung("fracht_versandart") == "Palettenversand" and db.einstellung("absender_plz") == "33129"
ids = {z["zuschlag_id"] for z in db.zeilen("fracht_zuschlaege")}
assert not any(z["typ"] in ("Diesel", "Maut") for z in db.zeilen("fracht_zuschlaege")), ids
assert any(d["dienstleister_id"] == "SLH" for d in db.zeilen("fracht_dienstleister"))
ok(f"Richtwerte geladen: {neu} Zeilen, {weg} BEISPIEL-Zeilen ersetzt; eigene Zone bleibt; Versandart "
   "Palettenversand; kein Diesel- und Mautzuschlag (im Preis)")

# zweimal laden: gleiches Ergebnis
n_plz = len(db.zeilen("fracht_plz"))
db.fracht_richtwerte_laden()
assert len(db.zeilen("fracht_plz")) == n_plz
ok("Erneut laden ersetzt die Richtwerte, ohne doppelte Zeilen")

fd = db.fracht_daten()


def preis(plz, netto, lht, max_laenge=None):
    e = fracht.rechnen(fd, dict(datum="2026-10-21", land="DE", plz=plz, absender_plz="33129", absender_land="DE",
                                versandart="Palettenversand", netto=netto, max_laenge=max_laenge, lht=lht,
                                leistungen={}))
    assert e["gesamt"] is not None, (plz, e.get("fehler"))
    return e


def eur(n):
    return [dict(lht_id="EUR", anzahl=n)]


# Paketversand (Patrick 29.10.2026): je Karton nach Gewichtsklasse, überall in Deutschland gleich
lht_fd = {z["lht_id"]: z for z in fd["lht"]}
assert [(lht_fd[k]["laenge"], lht_fd[k]["breite"], lht_fd[k]["hoehe"]) for k in ("K-S", "K-M", "K-L")] == [
    (400, 300, 200), (600, 400, 400), (1200, 200, 200)]
assert lht_fd["EUR"]["max_laenge"] == lht_fd["EW"]["max_laenge"] == 3000 and lht_fd["IND"]["max_laenge"] == 1400
for plz in ("33100", "80331", "25980"):
    e = fracht.rechnen(fd, dict(datum="2026-10-21", land="DE", plz=plz, absender_plz="33129", absender_land="DE",
                                versandart=fracht_richtwerte.PAKET, netto=40, lht=[
                                    dict(lht_id="K-S", anzahl=2), dict(lht_id="K-M", anzahl=1),
                                    dict(lht_id="K-L", anzahl=1)], leistungen={}))
    assert e["tarif"]["tarif_id"] == fracht_richtwerte.TARIF_PAKET and abs(e["gesamt"] - 63.96) < 1e-6, (plz, e)
assert preis("33100", 190, eur(1))["tarif"]["tarif_id"] == fracht_richtwerte.TARIF
ok("Paket: 2 × Karton S + M + L = 2 × 10,49 + 18,99 + 23,99 = 63,96 € überall in Deutschland; Palette bleibt "
   "beim Palettentarif; Europalette und Einwegpalette bis 3.000 mm")

e1, e2, e3 = preis("33100", 190, eur(1)), preis("20095", 190, eur(1)), preis("80331", 190, eur(1))
assert (e1["gesamt"], e2["gesamt"], e3["gesamt"]) == (65.0, 115.0, 125.0), (e1["gesamt"], e2["gesamt"], e3["gesamt"])
assert not any("teurere" in h for h in e1["hinweise"])
ok("1 Europalette 190 kg ab Delbrück: Paderborn 65 €, Hamburg 115 €, München 125 € (Marktmedian 85/95/110 €)")

n1, n2, n3 = preis("32052", 190, eur(1)), preis("48143", 190, eur(1)), preis("44135", 190, eur(1))
assert (n1["gesamt"], n2["gesamt"], n3["gesamt"]) == (65.0, 80.0, 100.0), (n1["gesamt"], n2["gesamt"], n3["gesamt"])
assert preis("33100", 190, eur(2))["gesamt"] == 2 * 55.25
ok("Nahbereich: Herford (45 km) 65 €, Münster (80 km) 80 €, Dortmund (104 km) 100 €; 2 Paletten Paderborn 110,50 €")


def eigen(plz, km=None):
    return fracht.rechnen(fd, dict(datum="2026-10-29", land="DE", plz=plz, absender_plz="33129", absender_land="DE",
                                   versandart="Eigene Anlieferung", netto=190, km=km, lht=eur(1), leistungen={}))


a20, a0, weit = eigen("33100", 20), eigen("33100"), eigen("80331", 600)
assert a20["gesamt"] == 60.0 and a20["snapshot"]["tarif"]["tarif_id"] == fracht_richtwerte.TARIF_EIGEN, a20
assert a0["gesamt"] == 80.0, a0["gesamt"]
assert weit["gesamt"] is None and weit["fehler"], weit
ok("Eigene Anlieferung: 20 km 60 € (20 € + 40 km × 1,00 €), ohne Entfernung 30 km der Zone = 80 €, München kein Tarif")

z3, z5 = preis("20095", 450, eur(3)), preis("20095", 900, eur(5))
assert z3["gesamt"] == 3 * 97.75 and z5["gesamt"] == round(5 * 80.5, 2), (z3["gesamt"], z5["gesamt"])
ok(f"Hamburg 3 Paletten {z3['gesamt']:.2f} €, 5 Paletten {z5['gesamt']:.2f} € (Markt 2–3 Paletten 190 €, 4–6 285 €)")

s1 = preis("20095", 450, eur(1))
assert s1["gesamt"] == 155.0, s1["gesamt"]
ok("Schwere Palette 450 kg nach Hamburg: 115 € + 40 € = 155 € (Markt 300–600 kg ca. 140 €)")

lg = preis("20095", 500, [dict(lht_id="LG", anzahl=1)], max_laenge=6000)
assert lg["gesamt"] == round(3 * 97.75 + 60, 2), lg["gesamt"]
ok(f"Langgut 6 m, 500 kg nach Hamburg: {lg['gesamt']:.2f} € (3 Stellplätze + Überlänge; Markt ca. 270–340 €)")

ins = preis("25980", 190, eur(1))
assert ins["gesamt"] == 200.0, ins["gesamt"]
z25 = preis("25", 190, eur(1))
assert z25["gesamt"] == 200.0 and any("teurere" in h for h in z25["hinweise"])
ok("Sylt 25980: 140 € + 60 € Inselzuschlag = 200 €; nur '25' eingegeben: Inselpreis als teurere Zone mit Hinweis")

# automatische Fracht im Angebot mit den Richtwerten
aid = beispiel_angebot.anlegen(db)
seite = fenster.angebot_oeffnen(aid)
seite.fracht_ziel_setzen("80331", "DE")
seite.fracht_auto_setzen(True)
a = db.angebot(aid)
d = fracht_angebot.daten(a)
assert not d.get("fehler") and a["fracht"] and d["snapshot"]["tarif"]["tarif_id"] == fracht_richtwerte.TARIF, d
ok(f"Angebot mit 'Fracht automatisch berechnen' nach München: {a['fracht']:.2f} € aus dem Richtwert-Tarif")

# Frachtzonen auf Standard zurücksetzen: eigene Zone und verbogene Zuordnung weg, Sicherung vorher
with db.con:
    db.con.execute("UPDATE fracht_plz SET zone_id='EIGEN', bemerkung='von Hand' WHERE plz_von='80*'")
assert fracht.zone_finden(db.fracht_daten(), "DE", "80331")["zone"]["zone_id"] == "EIGEN"
sicherung = db.pfad.parent / "Sicherung"
vorher = set(sicherung.glob("*_vor_Frachtzonen_Standard*.db"))
assert db.fracht_zonen_fremd() == 0
weg, neu = fenster.fracht.zonen.zuruecksetzen()       # Knopf 'Auf Standard zurücksetzen …' (stumm: ohne Rückfrage)
assert weg > 0 and neu > 50, (weg, neu)
assert len(set(sicherung.glob("*_vor_Frachtzonen_Standard*.db")) - vorher) == 1
zonen = {z["zone_id"] for z in db.zeilen("fracht_zonen")}
assert zonen == {"RW0A", "RW0B", "RW1", "RW2", "RW3", "RW4", "RW-INSEL"}, zonen
assert len([p for p in db.zeilen("fracht_preise") if p["tarif_id"] == fracht_richtwerte.TARIF_EIGEN]) == 2
assert not [z for z in db.zeilen("fracht_plz") if z["zone_id"] == "EIGEN"]
assert len(db.zeilen("fracht_plz")) == n_plz
assert preis("80331", 190, eur(1))["gesamt"] == 125.0
ok("Frachtzonen auf Standard zurückgesetzt: eigene Zone und Zuordnung entfernt, Richtwert-Zonen wieder da, "
   "Sicherung vor_Frachtzonen_Standard angelegt, München wieder 125 €")

fenster.close()

# einmalige Umstellung beim Start: alter Stand (Ring bis 200 km ohne Nahbereich) wird neu geladen
with db.con:
    db.con.execute("DELETE FROM fracht_zonen WHERE zone_id IN ('RW0A', 'RW0B')")
    db.con.execute("UPDATE fracht_plz SET zone_id='RW1' WHERE zone_id IN ('RW0A', 'RW0B')")
    db.con.execute("DELETE FROM fracht_tarife WHERE tarif_id=?", (fracht_richtwerte.TARIF_EIGEN,))
    db.con.execute("DELETE FROM fracht_preise WHERE tarif_id=?", (fracht_richtwerte.TARIF_EIGEN,))
    db.con.execute("DELETE FROM fracht_preise WHERE zone_id IN ('RW0A', 'RW0B')")
    db.con.execute("DELETE FROM fracht_lht WHERE art='Karton'")
    db.con.execute("UPDATE fracht_lht SET max_laenge=1400 WHERE lht_id='EUR'")
db.neu("fracht_zonen", dict(zone_id="EIGEN2", bezeichnung="Eigene", land="DE", aktiv="ja", bemerkung="von Hand"))
db.einstellung_setzen("fracht_nah_stand", "")
fd = db.fracht_daten()
assert preis("33100", 190, eur(1))["gesamt"] == 100.0
pfad = db.pfad
db.schliessen()
vorher = set(sicherung.glob("*_vor_Fracht_Nahbereich*.db"))
db = Datenbank(pfad)
fd = db.fracht_daten()
assert preis("33100", 190, eur(1))["gesamt"] == 65.0
assert any(z["zone_id"] == "EIGEN2" for z in db.zeilen("fracht_zonen"))
assert any(t["tarif_id"] == fracht_richtwerte.TARIF_EIGEN for t in db.zeilen("fracht_tarife"))
assert {z["lht_id"]: z["max_laenge"] for z in db.zeilen("fracht_lht")}["EUR"] == 3000
assert {"K-S", "K-M", "K-L"} <= {z["lht_id"] for z in db.zeilen("fracht_lht")}
assert len(set(sicherung.glob("*_vor_Fracht_Nahbereich*.db")) - vorher) == 1
db.schliessen()
db = Datenbank(pfad)               # nur einmal
assert len(set(sicherung.glob("*_vor_Fracht_Nahbereich*.db")) - vorher) == 1
ok("Beim Start einmalig umgestellt: Paderborn 100 € -> 65 €, Europalette 3.000 mm, Kartons da, eigene Zone bleibt, "
   "Sicherung vor_Fracht_Nahbereich")
db.schliessen()
print("OK: Richtwerte Palettenversand")
