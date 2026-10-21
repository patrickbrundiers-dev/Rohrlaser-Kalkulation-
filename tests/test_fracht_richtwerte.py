"""Test: Richtwerte Palettenversand (Recherche 10/2026, Marktpreise + 10 % Puffer, Zonen nach Entfernung).

- Knopf 'Richtwerte laden' ersetzt alle BEISPIEL-Zeilen, eigene Einträge bleiben, Absender-PLZ und Versandart werden
  gesetzt; unbekannte Absender-PLZ ändert nichts.
- Preise ab 33129 Delbrück: 1 Palette je Ring 100 / 115 / 125 €, mehrere Paletten günstiger je Stück, schwere
  Palette +40 € je Stellplatz, Langgut 6 m = 3 Stellplätze + Überlänge, Insel = teuerster Ring + Inselzuschlag;
  Diesel und Maut sind im Preis (keine eigenen Zuschläge).
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
from rohrlaser import fracht, fracht_angebot, fracht_richtwerte, rechnen  # noqa: E402
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
assert [t["tarif_id"] for t in db.zeilen("fracht_tarife")] == [fracht_richtwerte.TARIF]
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


e1, e2, e3 = preis("33100", 190, eur(1)), preis("20095", 190, eur(1)), preis("80331", 190, eur(1))
assert (e1["gesamt"], e2["gesamt"], e3["gesamt"]) == (100.0, 115.0, 125.0), (e1["gesamt"], e2["gesamt"], e3["gesamt"])
assert not any("teurere" in h for h in e1["hinweise"])
ok("1 Europalette 190 kg ab Delbrück: Paderborn 100 €, Hamburg 115 €, München 125 € (Marktmedian 85/95/110 €)")

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
assert zonen == {"RW1", "RW2", "RW3", "RW4", "RW-INSEL"}, zonen
assert not [z for z in db.zeilen("fracht_plz") if z["zone_id"] == "EIGEN"]
assert len(db.zeilen("fracht_plz")) == n_plz
assert preis("80331", 190, eur(1))["gesamt"] == 125.0
ok("Frachtzonen auf Standard zurückgesetzt: eigene Zone und Zuordnung entfernt, Richtwert-Zonen wieder da, "
   "Sicherung vor_Frachtzonen_Standard angelegt, München wieder 125 €")

fenster.close()
db.schliessen()
print("OK: Richtwerte Palettenversand")
