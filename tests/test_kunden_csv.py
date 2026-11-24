"""Prüft CSV-Export und -Import der Kundenliste: Export für Excel (Semikolon, BOM, Komma-Zahlen) unverändert wieder
einlesbar, Vorschau mit neu/ändern/Fehler, doppelte Kundennummern, fehlende Pflichtfelder, falsche Lieferbedingung,
führende Null der PLZ, 'nur neue anlegen', nichts ohne Bestätigung, Sicherung vor dem Import, Knöpfe im Reiter
Kunden. Alle Kunden sind Testwerte.

Aufruf: python tests/test_kunden_csv.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from rohrlaser import kunden_csv  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402
from rohrlaser.kunden_csv_dialog import KundenImportDialog, csv_importieren  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyleSheet(STIL)
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


db = Datenbank(tmp / "k.db")
db.con.execute("DELETE FROM kunden")
db.con.commit()
db.neu("kunden", dict(kundennr="10001", name="Stahlbau Test GmbH", strasse="Werkstr. 1", plz_ort="33129 Delbrück",
                      telefon="05250 123", skonto=2.5, skonto_tage=10, zahlungsziel=30, lieferbedingung="frei Haus"))
db.neu("kunden", dict(kundennr="10002", name="Metallbau Probe", plz_ort="01067 Dresden", plz="01067", land="DE"))
fenster = Hauptfenster(db, stumm=True)
seite = next(s for s in fenster.seiten if s.t.name == "kunden")
texte = [k.text() for k in seite.findChildren(QPushButton)]
assert "CSV exportieren" in texte and "CSV importieren …" in texte, texte
ok("Reiter Kunden hat CSV exportieren und CSV importieren …")

# ------------------------------------------------------------------ Export
pfad = tmp / "Kunden.csv"
assert seite.kunden_exportieren(str(pfad)) == str(pfad)
text = pfad.read_text(encoding="utf-8")
assert text.startswith("﻿Kundennummer;Kundenname;Straße;PLZ Ort;"), text[:60]
assert "10001;Stahlbau Test GmbH;Werkstr. 1;33129 Delbrück" in text and ";2,5;10;30;" in text, text
v = kunden_csv.vorschau(pfad.read_bytes(), db.zeilen("kunden"), db.kontext())
assert [z["aktion"] for z in v["zeilen"]] == [kunden_csv.GLEICH] * 2, v
ok("Export (Semikolon, BOM, Komma-Zahlen) und unverändert wieder einlesbar")

# ------------------------------------------------------------------ Vorschau
kopf = text.splitlines()[0].lstrip("﻿").split(";")
titel = {kunden_csv.titel(n): n for n in kunden_csv.SPALTEN}


def zeile(**w):
    return ";".join(w.get(titel[t], "") for t in kopf)


inhalt = "\n".join([";".join(kopf),
    zeile(kundennr="10001", name="Stahlbau Test GmbH", strasse="Werkstr. 1", plz_ort="33129 Delbrück",
          telefon="05250 456", skonto="3", skonto_tage="10", zahlungsziel="30", lieferbedingung="frei Haus"),  # ändern
    zeile(kundennr="10003", name="Neukunde Müller", plz_ort="1067 Dresden", plz="1067"),     # neu, PLZ ohne Null
    zeile(kundennr="10004", name="Falsche Bedingung", lieferbedingung="irgendwie"),         # Auswahl
    zeile(kundennr="10005", name="Skonto zu hoch", skonto="50"),                            # Bereich
    zeile(kundennr="10003", name="doppelt"),                                                # doppelt in Datei
    zeile(kundennr="", name="ohne Nummer"),                                                 # Pflichtfeld
    zeile(kundennr="10006", name="", land="Germanien"),                                     # Pflicht + Land
])
imp = tmp / "import.csv"
imp.write_text(inhalt, encoding="cp1252")              # auch Excel-Dateien ohne UTF-8
v = kunden_csv.vorschau(imp.read_bytes(), db.zeilen("kunden"), db.kontext())
aktion = [(z["kundennr"], z["aktion"]) for z in v["zeilen"]]
assert aktion == [("10001", "ändern"), ("10003", "neu"), ("10004", "Fehler"), ("10005", "Fehler"),
                  ("10003", "Fehler"), (None, "Fehler"), ("10006", "Fehler")], aktion
z = {z["nr"]: z for z in v["zeilen"]}
assert z[2]["aenderung"] == ["Telefon: 05250 123 → 05250 456", "Skonto [%]: 2,5 → 3,0"], z[2]["aenderung"]
assert z[3]["kunde"]["plz"] == "01067" and z[3]["kunde"]["plz_ort"] == "01067 Dresden", z[3]["kunde"]
assert any("führende Null" in h for h in z[3]["hinweis"])
assert z[4]["fehler"][0].startswith("Spalte O (Lieferbedingung): „irgendwie“ unbekannt"), z[4]["fehler"]
assert z[5]["fehler"][0].startswith("Spalte J (Skonto [%]): Wert zwischen"), z[5]["fehler"]
assert "doppelt in der Datei (wie Zeile 3)" in z[6]["fehler"][0]
assert z[7]["fehler"] == ["Spalte A (Kundennummer): fehlt"] and "Spalte B (Kundenname): fehlt" in z[8]["fehler"]
assert "Spalte F (Land): Land als zweistelliger Ländercode, z. B. DE" in z[8]["fehler"], z[8]["fehler"]
ok("Vorschau: ändern mit Unterschieden, neu, PLZ-Null ergänzt, Fehler bei Auswahl, Bereich, Dublette, Pflichtfeld")

nur = kunden_csv.vorschau(imp.read_bytes(), db.zeilen("kunden"), db.kontext(), nur_neue=True)
assert nur["zeilen"][0]["aktion"] == kunden_csv.UEBERSPRUNGEN and nur["zeilen"][1]["aktion"] == kunden_csv.NEU
ok("Vorhandene Kunden nicht ändern: vorhandene Kundennummer wird übersprungen")

teil = tmp / "teil.csv"
teil.write_text("Kundennr.;Telefon\n10002;0351 999\n", encoding="utf-8")
v = kunden_csv.vorschau(teil.read_bytes(), db.zeilen("kunden"), db.kontext())
assert v["fehler"][0].startswith("Zeile 1: Kopfzeile ohne Spalte(n) Kundenname (gelesen mit Trennzeichen Semikolon: "
                              "Kundennr., Telefon)"), v
teil.write_text("Kundennr.;Name;Telefon\n10002;Metallbau Probe;0351 999\n", encoding="utf-8")
v = kunden_csv.vorschau(teil.read_bytes(), db.zeilen("kunden"), db.kontext())
assert v["zeilen"][0]["aenderung"] == ["Telefon: leer → 0351 999"], v["zeilen"][0]
assert v["zeilen"][0]["kunde"]["plz"] == "01067", "Spalten, die fehlen, bleiben"
leer = tmp / "leer.csv"
leer.write_text("", encoding="utf-8")
assert kunden_csv.vorschau(leer.read_bytes(), [], db.kontext())["fehler"] == ["Die Datei ist leer"]
ok("Kopfzeile ohne Pflichtspalte, Teilspalten ändern nur sich selbst, leere Datei")

# ------------------------------------------------------------------ Dialog und Übernahme
vorher = db.zeilen("kunden")
d = KundenImportDialog(seite, lambda nur: kunden_csv.vorschau(imp.read_bytes(), vorher, db.kontext(), nur), str(imp))
assert d.tabelle.rowCount() == 7 and d.importieren_knopf.isEnabled()
assert "1 neu · 1 ändern" in d.zusammenfassung.text() and "5 mit Fehler" in d.zusammenfassung.text()
d.nur_neue.setChecked(True)
assert "1 übersprungen" in d.zusammenfassung.text() and d.ergebnis["zeilen"][0]["aktion"] == kunden_csv.UEBERSPRUNGEN
d.close()
ok("Vorschau-Dialog: Zusammenfassung, Umschalten auf nur neue")

ergebnis, erg = csv_importieren(seite, db, str(imp), bestaetigt=False)
assert erg is None and db.zeilen("kunden") == vorher, "ohne Bestätigung nichts geändert"
assert seite.kunden_importieren(str(imp), bestaetigt=True, nur_neue=True)[:2] == (1, 0)
k = {k["kundennr"]: k for k in db.zeilen("kunden")}
assert k["10001"]["telefon"] == "05250 123" and k["10003"]["name"] == "Neukunde Müller"
neu, geaendert, sicherung = seite.kunden_importieren(str(imp), bestaetigt=True)
assert (neu, geaendert) == (0, 1), (neu, geaendert)
assert Path(sicherung).exists() and "vor_Kundenimport" in Path(sicherung).name
k = {k["kundennr"]: k for k in db.zeilen("kunden")}
assert k["10001"]["telefon"] == "05250 456" and k["10001"]["skonto"] == 3 and len(k) == 3
assert seite.modell.rowCount() == 3, "Reiter Kunden neu geladen"
alt = Datenbank(sicherung)
assert {k["kundennr"]: k["telefon"] for k in alt.zeilen("kunden")}["10001"] == "05250 123", "Sicherung = alter Stand"
alt.con.close()
ok("Import: nichts ohne Bestätigung, nur neue, dann ändern; Sicherung vorher mit altem Stand")

v = kunden_csv.vorschau(imp.read_bytes(), db.zeilen("kunden"), db.kontext())
assert [z["aktion"] for z in v["zeilen"][:2]] == [kunden_csv.GLEICH] * 2
assert db.kunden_importieren(v["zeilen"]) == (0, 0, None), "nichts zu tun = keine Sicherung"
ok("zweiter Import derselben Datei: unverändert, keine Sicherung")
fenster.close()
print("Alle Kunden-CSV-Tests bestanden.")
