"""Test: zweistellige PLZ und 'Fracht automatisch berechnen' im Angebot (Entscheidungen 1B, 2A, 3A).

- PLZ-Bereich mit zwei Stellen: eine Zone, Bereich über mehrere Zonen (die teurere gilt, mit Hinweis), Rest des
  Bereichs in der Standardzone; '25' in der CSV-Datei = '25*'.
- Haken im Angebot: Vorgabe aus (1B), Ziel-PLZ aus dem Kunden, Tarifkopie beim Setzen (2A), Mengenänderung rechnet
  mit der Kopie neu, jede Staffelmenge eigene Fracht, Fehler -> Kalkulation ohne Fracht mit Warnung (nie still 0 €),
  von Hand übernommene Frachtberechnung schaltet die Automatik aus, ältere Angebote unverändert.
"""
import json
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
from rohrlaser import fracht, fracht_angebot, fracht_daten, rechnen, staffeln  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, stumm=True)
fd = db.fracht_daten()


def sendung(plz, **k):
    return dict(dict(datum="2026-10-20", land="DE", plz=plz, versandart="Stückgut", netto=180.0, lht=[]), **k)


# --- zweistellige PLZ im Rechenkern (Beispieldaten: 40000–42999 Z1, 25938–25999 Z5, Standardzone Z3)
z = fracht.zone_finden(fd, "DE", "40")
assert z["zone"]["zone_id"] == "Z1" and len(z.get("bereich_zonen") or []) < 2, z
e = fracht.rechnen(fd, sendung("40"))
assert e["gesamt"] is not None and not any("teurere" in h for h in e["hinweise"]), e
e1 = fracht.rechnen(fd, sendung("41000"))
assert abs(e["gesamt"] - e1["gesamt"]) < 0.005
ok(f"PLZ '40' liegt ganz in Zone Z1: {e['gesamt']:.2f} € wie mit fünfstelliger PLZ 41000")

z = fracht.zone_finden(fd, "DE", "25")
assert {b["zone_id"] for b in z["bereich_zonen"]} == {"Z3", "Z5"} and "teurere" in z["text"], z
e = fracht.rechnen(fd, sendung("25"))
e3, e5 = fracht.rechnen(fd, sendung("25000")), fracht.rechnen(fd, sendung("25980"))
assert e3["gesamt"] < e5["gesamt"] and abs(e["gesamt"] - e5["gesamt"]) < 0.005, (e["gesamt"], e3["gesamt"], e5["gesamt"])
assert any("teurere" in h for h in e["hinweise"]), e["hinweise"]
ok(f"PLZ '25' über Z3 (Standardzone für den Rest) und Z5 (Inseln): die teurere gilt, {e['gesamt']:.2f} €, mit Hinweis")

z = fracht.zone_finden(fd, "DE", "26")
assert z["zone"]["zone_id"] == "Z3" and len(z.get("bereich_zonen") or []) < 2, z
ok("PLZ '26' ohne eigene Zuordnung: Standardzone Z3")

# CSV: '25' = '25*'
zeilen, _ = fracht_daten.plz_csv_lesen("land;plz_von;plz_bis;zone_id\nDE;25;;Z2\n", {"Z2"}, {"DE"})
assert zeilen[0]["plz_von"] == "25*" and not zeilen[0].get("plz_bis"), zeilen
ok("CSV-Import: PLZ '25' ohne Bis-Wert wird zu '25*' (alle PLZ, die mit 25 beginnen)")

# --- Haken im Angebot
aid = beispiel_angebot.anlegen(db)
a = db.angebot(aid)
assert not fracht_angebot.auto(a) and a.get("fracht_plz") is None
seite = fenster.angebot_oeffnen(aid)
kb = seite.kopf_bereich
assert not kb.fracht_auto.isChecked()
ok("1B: neues Angebot ohne Haken 'Fracht automatisch berechnen'")

# Kunde mit Lieferanschrift 25980 -> Ziel '25980', DE (volle PLZ aus dem Kunden, zwei Ziffern reichen bei der Eingabe)
db.neu("kunden", dict(kundennr="K-77", name="Insel GmbH", plz_ort="40210 Düsseldorf", liefer_plz="25980",
                      liefer_land="DE"))
assert fracht_angebot.ziel_aus_kunde(db.kunde("K-77")) == ("25980", "DE")
assert fracht_angebot.ziel_aus_kunde(dict(plz_ort="40210 Düsseldorf")) == ("40210", "DE")
seite.kunde_waehlen("K-77")
seite = fenster.angebot_oeffnen(aid)
kb = seite.kopf_bereich
kb.fracht_auto.setChecked(True)
a = db.angebot(aid)
d = fracht_angebot.daten(a)
# ohne Versandart in den Einstellungen passen zwei Beispieltarife gleich gut: Fehler statt geratenem Tarif
assert fracht_angebot.auto(a) and "Mehrere Tarife" in d["fehler"] and d["gesamt"] is None, d
ok("Ohne Versandart in den Einstellungen: zwei Tarife passen gleich gut, Fehler statt geratenem Tarif")
db.einstellung_setzen("fracht_versandart", "Stückgut")
seite = fenster.angebot_oeffnen(aid)
assert db.angebot(aid)["fracht_plz"] == "25980"
seite.fracht_ziel_setzen("25980", "")     # unveränderte PLZ: nichts zu tun
assert "Mehrere Tarife" in fracht_angebot.daten(db.angebot(aid))["fehler"]
seite.neu_laden()                         # jede Änderung lädt neu: ohne Tarifkopie wird ganz neu gerechnet
assert not fracht_angebot.daten(db.angebot(aid)).get("fehler")
seite.fracht_ziel_setzen("25 ", "de")     # zwei Ziffern reichen: ganzer Bereich 25…
kb = seite.kopf_bereich
a = db.angebot(aid)
d = fracht_angebot.daten(a)
assert fracht_angebot.auto(a) and a["fracht_plz"] == "25" and a["fracht_land"] == "DE", a
assert a["fracht_modus"] == fracht_angebot.BERECHNET and not d.get("fehler"), d
assert d["snapshot"] and d["gesamt"] and a["fracht"] == d["gesamt"]
assert any("teurere" in h for h in d["hinweise"])
k, tab = db.kontext(), db.tabellen()
pos = db.positionen(aid)
erg = rechnen.optimieren(a, pos, k)
einst = rechnen.einstellungen_angebot(a, db.einstellungen())
_, summen = rechnen.kalkulation(a, pos, erg, k, tab, einst)
assert abs(summen["fracht"] - d["gesamt"]) < 0.005 and not summen["fracht_fehler"]
seite = fenster.angebot_oeffnen(aid)
kb = seite.kopf_bereich
assert kb.fracht_auto.isChecked() and kb.fracht_plz.text() == "25" and not kb.fracht_modus.isEnabled()
assert "Automatisch" in kb.fracht_text.text() and "teurere" in kb.fracht_text.text(), kb.fracht_text.text()
g1 = d["gesamt"]
ok(f"Haken gesetzt: Ziel '25' aus der Lieferanschrift des Kunden, Fracht {g1:.2f} € (teurere Zone) in der Kalkulation")

# 2A: Tarif ändern -> Angebot rechnet weiter mit der Kopie; Mengenänderung rechnet mit der Kopie neu
with db.con:
    db.con.execute("UPDATE fracht_preise SET preis = preis * 3")
p0 = pos[0]
db.position_aendern(p0["id"], "stueck", p0["stueck"] * 10)
a = db.angebot(aid)
pos = db.positionen(aid)
werte = [rechnen.position_werte(p, a, k, tab) if rechnen.position_aktiv(p) else None for p in pos]
g2, _, f2 = fracht_angebot.betrag_angebot(a, pos, werte)
d2 = fracht_angebot.daten(a)
neu_tarif = fracht.rechnen(db.fracht_daten(), dict(d2["sendung"], netto=fracht_angebot.ware(pos, werte)[0],
                                                     lht=[]))
assert not f2 and g2 > g1, (g2, g1)
assert a["fracht"] == g1                  # noch nicht nachgeführt (Änderung ohne Angebotsseite)
seite = fenster.angebot_oeffnen(aid)
seite.neu_laden()                         # wie nach einer Eingabe in der Positionsliste
assert abs(db.angebot(aid)["fracht"] - g2) < 0.005 and db.fracht_auto_nachfuehren(aid) is False
assert "Automatisch" in seite.kopf_bereich.fracht_text.text()
assert neu_tarif["gesamt"] is None or g2 < neu_tarif["gesamt"], (g2, neu_tarif["gesamt"])
ok(f"2A: Menge ×10 rechnet mit der Tarifkopie neu und schreibt {g2:.2f} € ins Feld Frachtkosten; der verdreifachte "
   "Tarif wirkt erst beim Neusetzen")

# PLZ ändern -> neue Tarifkopie (dann mit dem neuen Tarif)
seite = fenster.angebot_oeffnen(aid)
seite.fracht_ziel_setzen("40", "DE")
a = db.angebot(aid)
d3 = fracht_angebot.daten(a)
assert a["fracht_plz"] == "40" and d3["gesamt"] and not any("teurere" in h for h in d3["hinweise"])
assert d3["snapshot"] != d2["snapshot"]
ok(f"PLZ auf '40' geändert: neue Zone Z1 und neue Tarifkopie ({d3['gesamt']:.2f} €)")

# jede Staffelmenge eigene Fracht
stufen = [dict(id=i, schluessel="30", menge=m) for i, m in enumerate((10, 500), 1)]
einst = rechnen.einstellungen_angebot(a, db.einstellungen())
zs = staffeln.rechnen_alle(a, pos, stufen, k, tab, einst)
assert all(z["preis"] for z in zs) and zs[0]["preis"]["fracht"] < zs[1]["preis"]["fracht"], [z["hinweis"] for z in zs]
ok("Staffelpreise: jede Menge rechnet ihre eigene Fracht (" +
   " / ".join(f"{z['preis']['fracht']:.2f}" for z in zs) + " €)")

# Fehler: Ziel-PLZ leer -> Kalkulation ohne Fracht, Fehler sichtbar, Warnung vor der Ausgabe
seite.fracht_ziel_setzen("", "DE")
a = db.angebot(aid)
assert fracht_angebot.daten(a)["fehler"] == "Ziel-PLZ fehlt"
erg = rechnen.optimieren(a, pos, k)
_, summen = rechnen.kalkulation(a, pos, erg, k, tab, einst)
assert summen["fracht"] == 0 and "Ziel-PLZ fehlt" in summen["fracht_fehler"], summen.get("fracht_fehler")
assert a["fracht"] is None                # Feld Frachtkosten leer statt alter Betrag
seite = fenster.angebot_oeffnen(aid)
assert "Ziel-PLZ fehlt" in seite.kopf_bereich.fracht_text.text()
assert seite._vor_ausgabe()          # stumm: Meldung, dann weiter
ok("Ziel-PLZ fehlt: Kalkulation ohne Fracht, Fehler rot im Angebot, Warnung vor der PDF-Ausgabe (kein stilles 0 €)")

# Fehler behoben (Gewicht wieder da) -> nächste Änderung rechnet ganz neu
seite.fracht_ziel_setzen("40", "DE")
p1 = db.positionen(aid)[0]
db.position_aendern(p1["id"], "werkstoff_id", "UNBEKANNT")
seite.fracht_auto_setzen(False)
seite.fracht_auto_setzen(True)
assert "Gewicht fehlt" in (fracht_angebot.daten(db.angebot(aid)).get("fehler") or ""), fracht_angebot.daten(db.angebot(aid))
db.position_aendern(p1["id"], "werkstoff_id", p1["werkstoff_id"])
seite.neu_laden()
a = db.angebot(aid)
assert not fracht_angebot.daten(a).get("fehler") and a["fracht"], fracht_angebot.daten(a)
ok(f"Gewicht fehlte, Werkstoff wieder eingetragen: Fracht automatisch neu berechnet ({a['fracht']:.2f} €)")

# Haken aus: letzter Betrag bleibt, Frachtart wieder wählbar
seite.fracht_ziel_setzen("40", "DE")
betrag = db.angebot(aid)["fracht"]
seite = fenster.angebot_oeffnen(aid)
seite.kopf_bereich.fracht_auto.setChecked(False)
a = db.angebot(aid)
assert not fracht_angebot.auto(a) and a["fracht"] == betrag
seite = fenster.angebot_oeffnen(aid)
assert seite.kopf_bereich.fracht_modus.isEnabled()
ok(f"Haken aus: letzter Betrag {betrag:.2f} € bleibt, Frachtart wieder wählbar")

# Fracht berechnen … von Hand übernommen: Automatik aus
seite.kopf_bereich.fracht_auto.setChecked(True)
assert fracht_angebot.auto(db.angebot(aid))
seite = fenster.angebot_oeffnen(aid)
dlg = seite.fracht_berechnen()
dlg.rechner.plz.setText("41000")
dlg.rechner.versandart.setCurrentText("Stückgut")
assert dlg.rechner.rechnen()["gesamt"] is not None
assert dlg.uebernehmen()
assert not fracht_angebot.auto(db.angebot(aid))
ok("Fracht berechnen … von Hand übernommen: Automatik aus, sonst würde sie den Betrag überschreiben")

# ältere Angebote: ohne Haken und mit unveränderter Staffel-Prüfsumme
alt = db.angebot(beispiel_angebot.anlegen(db))
pa = db.positionen(alt["id"])
kenn = staffeln.kennung(alt, pa, [], k, tab, einst)
assert kenn == staffeln.kennung(dict(alt, fracht_auto=None, fracht_plz=None, fracht_land=None), pa, [], k, tab, einst)
assert fracht_angebot.betrag_angebot(dict(alt, fracht=99.0), pa, []) == (99.0, "", "")
ok("Ältere Angebote: ohne Haken wie bisher, Staffel-Prüfsumme unverändert")

fenster.close()
db.schliessen()
print("OK: zweistellige PLZ und automatische Fracht")
