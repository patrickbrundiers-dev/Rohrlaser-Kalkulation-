"""Prüft Preisänderungen und CSV der Zukaufartikel (Testplan 12 und 13): Protokoll, betroffene Angebote mit
Vergleich alt/neu, Aktualisieren je Angebot, CSV-Export und -Import mit Vorschau (ungültige Preise, doppelte Nummern,
fehlende Pflichtfelder, nichts ohne Bestätigung). Alle Preise sind Testwerte.

Aufruf: python tests/test_zukauf_preise.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import zukauf, zukauf_csv  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402
from rohrlaser.zukauf_preise import CsvImportDialog, csv_exportieren, csv_importieren  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyleSheet(STIL)
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


def nah(a, b, text, eps=1e-6):
    assert abs(float(a) - float(b)) < eps, f"{text}: {a} != {b}"


db = Datenbank(tmp / "z.db")
ind = dict(aufschlag_quelle=zukauf.INDIVIDUELL, aufschlag_methode=zukauf.PROZENT)
schraube = db.zukauf_speichern(None, dict(artikelnr="Z-1", bezeichnung="Schraube M6x20", kategorie="Normteile",
                                          einheit="Stück", aufschlag_wert=25, **ind),
                               [dict(lieferant="Lieferant A", preiseinheit=100, preise=[dict(ab=1, preis=12)], vpe=100,
                                     fracht=5)])
mutter = db.zukauf_speichern(None, dict(artikelnr="Z-2", bezeichnung="Mutter M6", einheit="Stück", aufschlag_wert=40,
                                        **ind), [dict(lieferant="Lieferant A", preiseinheit=1, preise=[dict(ab=1, preis=0.05)])])

a = db.angebot_neu(dict(kunde="Kunde 1"))
b = db.angebot_neu(dict(kunde="Kunde 2"))
for aid in (a, b):
    p = db.position_neu(aid, dict(pos=10, artikel="A", profil_id="RR 42,4x2,0", werkstoff_id="S235-10219",
                                  laenge=1000, stueck=10))
    db.position_aendern(p, "zukauf", json.dumps([dict(artikel_id=schraube, menge=4, stand=db.zukauf_stand(schraube))]))

f = Hauptfenster(db, stumm=True)
f.resize(1920, 1000)
f.show()
f.reiter.setCurrentWidget(f.zukauf)
app.processEvents()
unter = [f.zukauf.unter.tabText(i) for i in range(f.zukauf.unter.count())]
assert unter == ["Artikel", "Kategorien", "Lieferanten", "Preisänderungen"], unter

# ------------------------------------------------------------------ 12 Preisänderung, betroffene Angebote
art = db.zukauf_artikel(schraube)
bez = art.pop("bezuege")
bez[0]["preise"] = [dict(ab=1, preis=13)]
db.zukauf_speichern(schraube, art, bez)
h = db.zukauf_historie(schraube)
assert h[0]["feld"] == "Einkaufspreise" and h[0]["alt"] == "ab 1: 12,00" and h[0]["neu"] == "ab 1: 13,00", h[0]
betroffen = db.zukauf_betroffen(schraube)
assert [x["angebot_id"] for x in betroffen] == [a, b]
# 40 St -> Bestellung 100 St: alt (12 + 5) × 1,25 = 21,25 €, neu (13 + 5) × 1,25 = 22,50 €
nah(betroffen[0]["vk_alt"], 21.25, "VK alt")
nah(betroffen[0]["vk_neu"], 22.50, "VK neu")
nah(betroffen[0]["verbrauch"], 40, "Verbrauch")
assert db.zukauf_betroffen(mutter) == []

s = f.zukauf.preise
f.zukauf.unter.setCurrentWidget(s)
app.processEvents()
assert s.tabelle.rowCount() >= 1 and s.tabelle.item(0, 3).text() == "Einkaufspreise"
assert s.tab_betroffen.rowCount() == 2 and s.tab_betroffen.item(0, 7).text() == "1,25 €"
assert s.aktualisieren(bestaetigt=False) == 0, "ohne Bestätigung nichts"
assert len(db.zukauf_betroffen(schraube)) == 2
assert s.aktualisieren(bestaetigt=True) == 1
assert [x["angebot_id"] for x in db.zukauf_betroffen(schraube)] == [b], "nur das gewählte Angebot aktualisiert"
assert s.tab_betroffen.rowCount() == 1
s.artikel_filter.setCurrentIndex(s.artikel_filter.findData(mutter))
assert all(z["artikel_id"] == mutter for z in s.zeilen)
s.suche.setText("Einkaufspreise")
assert all("Einkaufspreise" in z["feld"] for z in s.zeilen)
ok("12 Preisänderungen: Protokoll alt/neu, betroffene Angebote mit VK alt/neu, Aktualisieren je Angebot erst nach "
   "Bestätigung")

# ------------------------------------------------------------------ CSV-Export
pfad = tmp / "export.csv"
csv_exportieren(s, db, pfad)
text = pfad.read_text(encoding="utf-8")
assert text.startswith("﻿Artikelnummer;Artikelbezeichnung;"), text[:60]
assert "Z-1;Schraube M6x20;Normteile;Stück" in text and "ab 1: 13,00" in text
v = zukauf_csv.vorschau(pfad.read_bytes(), db.zukauf_artikel_liste(), db.zukauf_kategorien())
assert [z["aktion"] for z in v["zeilen"]] == [zukauf_csv.GLEICH] * 2, "Export wieder eingelesen = unverändert"
ok("CSV-Export (Semikolon, Kopfzeile mit Feldtiteln) und unverändert wieder einlesbar")

# ------------------------------------------------------------------ 13 CSV-Import
kopf = text.splitlines()[0].lstrip("﻿")
spalten = kopf.split(";")


def zeile(**w):
    namen = {zukauf_csv.titel(n): n for n in zukauf_csv.ARTIKEL_SPALTEN + zukauf_csv.BEZUG_SPALTEN}
    return ";".join(w.get(namen[t], "") for t in spalten)


inhalt = "\n".join([
    kopf,
    zeile(artikelnr="Z-1", bezeichnung="Schraube M6x20", kategorie="Normteile", einheit="Stück", lieferant="Lieferant A",
          preiseinheit="100", preise="ab 1: 14,00 | ab 500: 11,00", vpe="100", fracht="5",
          aufschlag_quelle="individuell", aufschlag_methode=zukauf.PROZENT, aufschlag_wert="25"),     # ändern
    zeile(artikelnr="Z-1", bezeichnung="Schraube M6x20", kategorie="Normteile", lieferant="Lieferant B",
          preiseinheit="100", preise="ab 1: 15,00"),                    # zweiter Lieferant desselben Artikels
    zeile(artikelnr="Z-5", bezeichnung="Scheibe 6,4", kategorie="Neue Kategorie", einheit="Stück",
          lieferant="Lieferant A", preise="0,02"),                       # neu, Kategorie wird angelegt
    zeile(artikelnr="Z-6", bezeichnung="Ungültig", lieferant="Lieferant A", preise="ab 1: abc"),   # ungültiger Preis
    zeile(artikelnr="Z-7", bezeichnung="Negativ", lieferant="Lieferant A", preise="ab 1: -1,00"),  # negativer Preis
    zeile(artikelnr="Z-5", bezeichnung="Scheibe doppelt", lieferant="Lieferant A", preise="0,03"),  # doppelt
    zeile(artikelnr="", bezeichnung="ohne Nummer", lieferant="Lieferant A", preise="1"),          # Pflichtfeld
    zeile(artikelnr="Z-8", bezeichnung="", lieferant="Lieferant A", preise="1"),                  # Pflichtfeld
    zeile(artikelnr="Z-9", bezeichnung="Status falsch", status="weg"),                            # Auswahl
    zeile(artikelnr="Z-10", bezeichnung="Preis ohne Lieferant", preise="1,00"),
])
imp = tmp / "import.csv"
imp.write_text(inhalt, encoding="cp1252")              # auch Excel-Dateien ohne UTF-8
v = zukauf_csv.vorschau(imp.read_bytes(), db.zukauf_artikel_liste(), db.zukauf_kategorien())
aktion = [(z["artikelnr"], z["aktion"]) for z in v["zeilen"]]
assert aktion == [("Z-1", "ändern"), ("Z-1", "ändern"), ("Z-5", "neu"), ("Z-6", "Fehler"), ("Z-7", "Fehler"),
                  ("Z-5", "Fehler"), (None, "Fehler"), ("Z-8", "Fehler"), ("Z-9", "Fehler"), ("Z-10", "Fehler")], aktion
fehler = {z["nr"]: "; ".join(z["fehler"]) for z in v["zeilen"] if z["fehler"]}
assert "nicht lesbar" in fehler[5], fehler[5]
assert "negativ" in fehler[6].lower(), fehler[6]
assert "doppelt in der Datei (wie Zeile 4)" in fehler[7]
assert "Artikelnummer fehlt" in fehler[8] and "Artikelbezeichnung fehlt" in fehler[9]
assert "Status" in fehler[10] and "Lieferant fehlt" in fehler[11]
assert any("Einkaufspreise" in t and "14,00" in t for t in v["zeilen"][0]["aenderung"])
assert "Kategorie 'Neue Kategorie' wird angelegt" in v["zeilen"][2]["hinweis"]

d = CsvImportDialog(f, db, v, str(imp))
assert d.importieren_knopf.isEnabled() and "2 ändern" in d.zusammenfassung.text() and "7 mit Fehler" in d.zusammenfassung.text()
d.reject()
vorher = len(db.zukauf_artikel_liste())
_, erg = csv_importieren(f.zukauf.artikel, db, imp, bestaetigt=False)
assert erg is None and len(db.zukauf_artikel_liste()) == vorher, "nichts importiert ohne Bestätigung"
_, erg = csv_importieren(f.zukauf.artikel, db, imp, bestaetigt=True)
assert erg == (1, 1), erg
z1 = db.zukauf_artikel(schraube)
assert sorted(x["lieferant"] for x in z1["bezuege"]) == ["Lieferant A", "Lieferant B"]
assert zukauf.staffel_text(next(x for x in z1["bezuege"] if x["lieferant"] == "Lieferant A")["preise"]) \
    == "ab 1: 14,00 | ab 500: 11,00"
assert z1["aufschlag_wert"] == 25 and z1["kategorie"] == "Normteile"
assert "Neue Kategorie" in db.zukauf_kategorien()
assert not any(x["artikelnr"] in ("Z-6", "Z-7", "Z-8", "Z-9", "Z-10") for x in db.zukauf_artikel_liste())
assert db.zukauf_historie(schraube)[0]["bemerkung"] == "CSV-Import"
# bestehendes Angebot rechnet weiter mit seinem Preisstand
assert len(db.zukauf_betroffen(schraube)) == 2
leer = tmp / "leer.csv"
leer.write_text("Irgendwas;Anderes\n1;2\n", encoding="utf-8")
assert zukauf_csv.vorschau(leer.read_bytes(), [], {})["fehler"]
ok("13 CSV-Import: Vorschau, ungültige und negative Preise, doppelte Nummern, fehlende Pflichtfelder, unbekannte "
   "Auswahl, Preis ohne Lieferant erkannt; nichts ohne Bestätigung; zweiter Lieferant, neue Kategorie, Protokoll")

# Darstellung 1024 × 700
f.resize(1024, 700)
app.processEvents()
assert f.zukauf.preise.minimumSizeHint().width() < 1000
ok("Darstellung 1024 × 700")
print("OK: Preisänderungen und CSV der Zukaufartikel")
