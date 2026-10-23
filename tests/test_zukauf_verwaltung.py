"""Prüft den Reiter 'Zukaufartikel' (zukauf_seite.py): Anlegen, Bearbeiten, Abbrechen, Duplizieren, Archivieren,
mehrere Lieferanten, Live-Vorschau (= Rechenkern), Suche/Filter/Sortierung, Kategorien und Darstellung bei 1920 und
1024 Pixel Breite (Testplan 1, 2 und 14). Alle Preise sind Testwerte.

Aufruf: python tests/test_zukauf_verwaltung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QTableWidgetItem  # noqa: E402

from rohrlaser import zukauf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyleSheet(STIL)
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


def warten():
    for _ in range(3):
        app.processEvents()


def staffel(tab, zeilen):
    tab.blockSignals(True)
    tab.setRowCount(0)
    for ab, w in zeilen + [("", "")]:
        r = tab.rowCount()
        tab.insertRow(r)
        tab.setItem(r, 0, QTableWidgetItem(str(ab)))
        tab.setItem(r, 1, QTableWidgetItem(str(w)))
    tab.blockSignals(False)
    tab.geaendert.emit()


db = Datenbank(tmp / "z.db")
f = Hauptfenster(db, stumm=True)
f.resize(1920, 1000)
f.show()
f.reiter.setCurrentWidget(f.zukauf)
warten()
s = f.zukauf.artikel
assert [f.zukauf.unter.tabText(i) for i in range(f.zukauf.unter.count())] == ["Artikel", "Kategorien", "Lieferanten",
                                                                                  "Preisänderungen"]
assert f.reiter.tabText(f.reiter.indexOf(f.zukauf)) == "Zukaufartikel"

# ------------------------------------------------------------------ 1 Anlegen
fo = s.neu()
warten()
assert fo is s.formular and s.rechts.isVisible(), "Formular neben der Tabelle"
fo.artikelnr.setText("Z-1001")
fo.bezeichnung.setText("Sechskantschraube M6x20")
fo.kategorie.setCurrentText("Schrauben und Muttern")
fo.lieferant.setCurrentText("Lieferant A")
fo.preiseinheit.setText("100")
fo.preiseinheit.textEdited.emit("100")
staffel(fo.preise, [(1, "12,00"), (1000, "9,50")])
fo.fracht.setText("5")
fo.fracht.textEdited.emit("5")
fo.verbrauch.setText("100")
fo.verbrauch.textEdited.emit("100")
fo.quelle.setCurrentIndex(fo.quelle.findData(zukauf.INDIVIDUELL))
fo.methode.setCurrentIndex(fo.methode.findData(zukauf.PROZENT))
fo.wert.setText("25")
fo.wert.textEdited.emit("25")
warten()
v = fo.vorschau_daten
assert v["je_einheit"]["ek"] == Decimal("0.12") and v["je_einheit"]["bezug"] == Decimal("0.05"), v["je_einheit"]
assert v["je_einheit"]["vk"] == Decimal("0.2125"), v["je_einheit"]
zeilen = {z[0]: z for z in fo.ergebnis_zeilen}
assert zeilen["Einstandspreis"][1:3] == ("0,17 €", "17,00 €"), zeilen["Einstandspreis"]
assert zeilen["Verkaufspreis netto"][1:3] == ("0,2125 €", "21,25 €"), zeilen["Verkaufspreis netto"]
assert any("25 % auf Einstand (individuell)" == z[0] for z in fo.ergebnis_zeilen)
assert zeilen["Aufschlag auf Einstand / Marge vom Verkaufspreis"][1] == "25 % / 20 %"
assert not db.zukauf_artikel_liste(), "vor dem Speichern nichts in der Datenbank"
# Vorschau = Rechenkern
kern = zukauf.vorschau(dict(fo._felder()[0]), fo.bezuege[0], db.zukauf_kategorien(), None, 100)
assert kern["vk"] == v["vk"]
assert fo.speichern(), fo.fehler.text()
warten()
a1 = db.zukauf_artikel_liste()[0]
assert (a1["artikelnr"], a1["kategorie"], a1["aufschlag_wert"], a1["bezuege"][0]["preiseinheit"]) == \
    ("Z-1001", "Schrauben und Muttern", 25, 100)
assert zukauf.staffel_text(a1["bezuege"][0]["preise"]) == "ab 1: 12,00 | ab 1000: 9,50"
assert [z.get("name") for z in db.zeilen("zukauf_lieferanten")] == ["Lieferant A"]
assert not s.rechts.isVisible() and s.gewaehlt() == a1["id"]
assert (s.zellen_text[0]["ek"], s.zellen_text[0]["bezug"], s.zellen_text[0]["vk"]) == ("0,12 €", "5,00 € je Best.", "0,15 €"), s.zellen_text[0]
ok("1 Anlegen: Formular mit Live-Vorschau (0,12 € + 0,05 € Fracht = 0,17 €, +25 % = 0,2125 €), erst Speichern schreibt")

# ------------------------------------------------------------------ Eingabeprüfung
fo = s.neu()
fo.bezeichnung.setText("Mutter M6")
fo.artikelnr.setText("Z-1001")
fo.preise.setItem(0, 0, QTableWidgetItem("1"))
fo.preise.setItem(0, 1, QTableWidgetItem("-1"))
fo._bezug_geaendert()
assert not fo.speichern() and "nicht negativ" in fo.fehler.text(), fo.fehler.text()
fo.preise.setItem(0, 1, QTableWidgetItem("0,05"))
fo._bezug_geaendert()
fo.preiseinheit.setText("0")
fo._bezug_geaendert()
assert not fo.speichern() and "größer als 0" in fo.fehler.text(), fo.fehler.text()
assert fo.preiseinheit.styleSheet(), "Feld rot markiert"
fo.preiseinheit.setText("")
fo._bezug_geaendert()
assert not fo.speichern() and "gibt es schon" in fo.fehler.text(), fo.fehler.text()
fo.artikelnr.setText("Z-1002")
fo.verbrauch.setText("abc")
fo._geaendert()
assert "keine Zahl" in fo.fehler.text()
fo.verbrauch.setText("10")
fo._geaendert()
assert fo.speichern(), fo.fehler.text()
warten()
ok("Eingaben: negativer Preis, Preiseinheit 0, doppelte Artikelnummer, Text statt Zahl -> Meldung, nicht gespeichert")

# ------------------------------------------------------------------ Bearbeiten, Abbrechen, zweiter Lieferant
s.auswaehlen(a1["id"])
fo = s.bearbeiten()
assert fo.artikelnr.text() == "Z-1001" and fo.preiseinheit.text() == "100" and fo.wert.text() == "25"
fo.bezeichnung.setText("GEÄNDERT")
fo._geaendert()
fo.abbrechen()
warten()
assert db.zukauf_artikel(a1["id"])["bezeichnung"] == "Sechskantschraube M6x20", "Abbrechen verwirft"
fo = s.bearbeiten(a1["id"])
fo.lieferant_neu()
fo.lieferant.setCurrentText("Lieferant B")
staffel(fo.preise, [(1, "10,00")])
fo.preiseinheit.setText("100")
fo._bezug_geaendert()
fo.lieferant_bevorzugt()
fo.lieferanten.setCurrentRow(0)        # zurück zu A: Werte von B bleiben erhalten
warten()
assert fo.lieferant.currentText() == "Lieferant A" and fo.preiseinheit.text() == "100"
assert fo.vorschau_daten["je_einheit"]["ek"] == Decimal("0.12"), "Vorschau zeigt den angezeigten Lieferanten"
assert fo.speichern(), fo.fehler.text()
a = db.zukauf_artikel(a1["id"])
assert [(b["lieferant"], b["bevorzugt"]) for b in a["bezuege"]] == [("Lieferant B", "ja"), ("Lieferant A", "nein")]
assert zukauf.staffel_text(a["bezuege"][0]["preise"]) == "ab 1: 10,00"
warten()
assert s.zellen_text[[x["id"] for x in s.sichtbar].index(a1["id"])]["lieferant"] == "Lieferant B"
ok("2 Bearbeiten: Werte vollständig geladen, Abbrechen verwirft, zweiter Lieferant, bevorzugter Lieferant")

# ------------------------------------------------------------------ Duplizieren, Archivieren
fo = s.duplizieren(a1["id"])
assert fo.zeilen_id is None and fo.artikelnr.text() == "Z-1001-K" and fo.bezeichnung.text().endswith("(Kopie)")
assert len(fo.bezuege) == 2 and len(db.zukauf_artikel_liste()) == 2, "erst nach Speichern angelegt"
assert fo.speichern(), fo.fehler.text()
fo = s.duplizieren(a1["id"])
assert fo.artikelnr.text() == "Z-1001-K2"
fo.abbrechen()
kopie = next(x for x in db.zukauf_artikel_liste() if x["artikelnr"] == "Z-1001-K")
assert [b["lieferant"] for b in kopie["bezuege"]] == ["Lieferant B", "Lieferant A"]
s.archiv_umschalten(kopie["id"])
warten()
assert db.zukauf_artikel(kopie["id"])["status"] == "archiviert"
s.status_filter.setCurrentText("Aktive")
assert kopie["id"] not in [x["id"] for x in s.sichtbar]
s.status_filter.setCurrentText("Archivierte")
assert [x["id"] for x in s.sichtbar] == [kopie["id"]]
s.archiv_umschalten(kopie["id"])
assert db.zukauf_artikel(kopie["id"])["status"] == "aktiv"
s.status_filter.setCurrentText("Aktive")
ok("2 Duplizieren (Nummer -K, -K2, alle Lieferanten, erst mit Speichern) und Archivieren/Wieder aktivieren")

# ------------------------------------------------------------------ Suche, Filter, Sortierung
s.suche.setText("z-1002")
assert [x["artikelnr"] for x in s.sichtbar] == ["Z-1002"]
s.suche.clear()
s.lief_filter.setCurrentText("Lieferant B")
assert {x["artikelnr"] for x in s.sichtbar} == {"Z-1001", "Z-1001-K"}
s.lief_filter.setCurrentText("Alle")
s.sortierung.setCurrentText("EK je Einheit")
eks = [x["_vorschau"]["je_einheit"]["ek"] for x in s.sichtbar if x["_vorschau"] and not x["_vorschau"]["fehler"]]
assert eks == sorted(eks, reverse=True)
s.sortierung.setCurrentText("Artikelnummer")
assert [x["artikelnr"] for x in s.sichtbar] == ["Z-1001", "Z-1001-K", "Z-1002"]
assert not s.spalte_sichtbar("Bezugskosten") or any(w["bezug"] for w in s.zellen_text)
ok("Suche nach Artikelnummer, Filter Lieferant, Sortierung nach EK und Artikelnummer, leere Spalten ausgeblendet")

# ------------------------------------------------------------------ Kategorien: Standardaufschlag
kat = f.zukauf.kategorien
f.zukauf.unter.setCurrentWidget(kat)
warten()
r = next(i for i, z in enumerate(kat.modell.daten) if z["name"] == "Schrauben und Muttern")
spalte = lambda name: next(i for i, (art, x) in enumerate(kat.modell.spalten) if art == "feld" and x.name == name)
kat.modell.setData(kat.modell.index(r, spalte("aufschlag_methode")), zukauf.PROZENT)
kat.modell.setData(kat.modell.index(r, spalte("aufschlag_wert")), "30")
f.zukauf.unter.setCurrentWidget(s)
warten()
z1002 = next(x for x in s.daten if x["artikelnr"] == "Z-1002")
assert z1002["_vorschau"]["regeln"] == [] or z1002.get("kategorie") != "Schrauben und Muttern"
a = next(x for x in s.daten if x["id"] == a1["id"])
assert a["_vorschau"]["regeln"][0]["quelle"] == zukauf.INDIVIDUELL, "individueller Artikel bleibt"
fo = s.neu()
fo.bezeichnung.setText("Unterlegscheibe")
fo.kategorie.setCurrentText("Schrauben und Muttern")
staffel(fo.preise, [(1, "0,02")])
warten()
assert "30 % auf Einstand" in fo.quelle_info.text(), fo.quelle_info.text()
assert fo.vorschau_daten["aufschlag_pct"] == Decimal(30), "Kategorieaufschlag vorgeschlagen"
fo.quelle.setCurrentIndex(fo.quelle.findData(zukauf.INDIVIDUELL))
fo.methode.setCurrentIndex(fo.methode.findData(zukauf.MARGE))
fo.wert.setText("20")
fo._geaendert()
assert any(z[0].startswith("Zielmarge 20 %") for z in fo.ergebnis_zeilen), fo.ergebnis_zeilen
assert fo.vorschau_daten["je_einheit"]["vk"] == Decimal("0.025"), "0,02 / (1 − 20 %)"
fo.abbrechen()
assert kat.modell.roh(r, len(kat.modell.spalten) - 1) == "OK"
ok("Kategorien: Standardaufschlag pflegen, neuer Artikel übernimmt ihn, individueller bleibt; Zielmarge sichtbar")

# ------------------------------------------------------------------ 14 Darstellung
for breite in (1920, 1024):
    f.resize(breite, 760 if breite == 1024 else 1000)
    warten()
    s.anzeigen()
    warten()
    assert s.tabelle.horizontalScrollBar().maximum() == 0, f"waagrechtes Scrollen bei {breite} px"
    fo = s.bearbeiten(a1["id"])
    warten()
    if breite == 1024:
        assert s.dialog is not None and s.dialog.isVisible() and not s.rechts.isVisible(), "eigenes Fenster"
    else:
        assert s.rechts.isVisible() and s.dialog is None, "Formular neben der Tabelle"
    assert fo.speichern_knopf.isVisible() and fo.abbrechen_knopf.isVisible()
    from PySide6.QtWidgets import QScrollArea
    sa = fo.findChild(QScrollArea)
    assert sa.horizontalScrollBar().maximum() == 0 and sa.widget().width() <= sa.viewport().width()
    fo.abbrechen()
    warten()
ok("14 Darstellung: 1920 px Formular neben der Tabelle, 1024 px eigenes Fenster, kein waagrechtes Scrollen")

f.close()
db.schliessen()
print("OK: Verwaltung der Zukaufartikel")
