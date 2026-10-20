"""Prüft Blechartikel bei den Zukaufartikeln (Schema 20): Felder und Umstellung alter Dateien, EK fehlt (0 € ist kein
Einkaufspreis), Bezeichnung ohne angenommenen Werkstoff, Anlage aus einem gemessenen Blech, Dublettenprüfung, Bearbeiten
im Formular ohne Verlust der Blechdaten, Filter 'EK fehlt' und 'EK eintragen …' im Reiter Zukaufartikel.

Aufruf: python tests/test_zukauf_blech.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sqlite3
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import zukauf  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyleSheet(STIL)
tmp = Path(tempfile.mkdtemp())
fehler = 0


def fall(name):
    def deko(fn):
        global fehler
        try:
            fn()
            print(f"OK     {name}")
        except AssertionError as e:
            fehler += 1
            print(f"FEHLER {name}: {e}")
        return fn
    return deko


def warten():
    for _ in range(3):
        app.processEvents()


# gemessenes Blech wie step.blech() es liefert (Spalte 'blech' der Messung)
B = dict(laenge=500.0, breite=300.0, dicke=5.0, kontur="rechteckig", bohrungen={"10.0": 4}, innen=4,
         fingerabdruck="5.0|500|300|149686|1726|4|10x4")
db = Datenbank(tmp / "z.db")


@fall("Schema 20: neue Spalten, Umstellung einer Datei aus Schema 19 behält Artikel")
def _():
    assert SCHEMA_VERSION == 20
    spalten = {r[1] for r in db.con.execute("PRAGMA table_info(zukauf_artikel)")}
    assert set(zukauf.BLECH_FELDER) <= spalten, set(zukauf.BLECH_FELDER) - spalten
    alt = tmp / "alt.db"
    d = Datenbank(alt)
    d.zukauf_speichern(None, dict(bezeichnung="Schraube M6"), [dict(lieferant="A", preise=[dict(ab=1, preis=0.1)])])
    d.con.close()
    con = sqlite3.connect(alt)
    for n in zukauf.BLECH_FELDER:
        con.execute(f'ALTER TABLE zukauf_artikel DROP COLUMN "{n}"')
    con.execute("PRAGMA user_version=19")
    con.commit()
    con.close()
    d = Datenbank(alt)
    assert {r[1] for r in d.con.execute("PRAGMA table_info(zukauf_artikel)")} >= set(zukauf.BLECH_FELDER)
    a = d.zukauf_artikel_liste()
    assert [x["bezeichnung"] for x in a] == ["Schraube M6"] and a[0]["artikeltyp"] is None, a
    assert d.con.execute("PRAGMA user_version").fetchone()[0] == 20
    d.con.close()


@fall("EK fehlt: ohne Preis und mit 0 € fehlt der EK, die Kalkulation meldet 'kein Einkaufspreis'")
def _():
    assert zukauf.ek_fehlt(dict(bezuege=[]))
    assert zukauf.ek_fehlt(dict(bezuege=[dict(preise='[{"ab": 1, "preis": 0}]')]))
    assert not zukauf.ek_fehlt(dict(bezuege=[dict(preise='[{"ab": 1, "preis": 0}]'),
                                             dict(preise='[{"ab": 1, "preis": 12.5}]')]))
    st = zukauf.stand(dict(bezeichnung="X"), dict(lieferant="A", preise=[dict(ab=1, preis=0)]))
    assert zukauf.bestellung(st, 2)["fehler"] == "kein Einkaufspreis"
    st = zukauf.stand(dict(bezeichnung="X"), dict(lieferant="A", preise=[dict(ab=1, preis=3)]))
    assert zukauf.bestellung(st, 2)["einstand"] == Decimal(6)


@fall("Bezeichnung: Werkstoff nur, wenn bekannt; sonst 'Werkstoff offen' (nie S235 angenommen)")
def _():
    assert zukauf.blech_bezeichnung(500, 300, 5, "S235") == "Blech S235 500 × 300 × 5 mm"
    assert zukauf.blech_bezeichnung(500.04, 299.96, 1.5) == "Blech 500 × 300 × 1,5 mm (Werkstoff offen)"


@fall("Anlage aus gemessenem Blech: Kategorie Blechteile, Stück, Lieferant Technik, ohne Preis, Herkunft STEP")
def _():
    werte, bezuege = zukauf.blech_artikel(B, None, "Rahmen.step")
    i = db.zukauf_speichern(None, werte, bezuege)
    a = db.zukauf_artikel(i)
    assert a["artikeltyp"] == "Blech" and a["kategorie"] == "Blechteile" and a["einheit"] == "Stück", a
    assert (a["laenge"], a["breite"], a["dicke"], a["werkstoff"]) == (500, 300, 5, None), a
    assert a["herkunft"] == "STEP-Import" and a["step_datei"] == "Rahmen.step" and a["fingerabdruck"] == B["fingerabdruck"]
    assert [b["lieferant"] for b in a["bezuege"]] == ["Technik"] and zukauf.ek_fehlt(a), a["bezuege"]
    assert "Technik" in {z["name"] for z in db.zeilen("zukauf_lieferanten")}
    _.id = i


@fall("Dubletten: gleiche Maße (auch gedreht, ± 0,5) und Werkstoff = gleich; anderer Werkstoff/Kontur = ähnlich")
def _():
    liste = db.zukauf_artikel_liste()
    g, ae = zukauf.blech_dubletten(B, None, liste)
    assert len(g) == 1 and not ae, (g, ae)
    gedreht = dict(B, laenge=300.3, breite=499.6)
    assert len(zukauf.blech_dubletten(gedreht, None, liste)[0]) == 1
    g, ae = zukauf.blech_dubletten(B, "S235", liste)
    assert not g and len(ae) == 1, "anderer Werkstoff: nur ähnlich"
    g, ae = zukauf.blech_dubletten(dict(B, fingerabdruck="5.0|500|300|150000|1600|0|"), None, liste)
    assert not g and len(ae) == 1, "andere Bohrungen: nur ähnlich"
    assert zukauf.blech_dubletten(dict(B, dicke=6), None, liste) == ([], [])
    assert zukauf.blech_dubletten(dict(B, laenge=501), None, liste) == ([], [])
    a = liste[0]
    db.zukauf_status(a["id"], "archiviert")
    assert zukauf.blech_dubletten(B, None, db.zukauf_artikel_liste()) == ([], []), "archivierte zählen nicht"
    db.zukauf_status(a["id"], "aktiv")


@fall("EK eintragen: 0 € abgelehnt, Preis beim Lieferanten Technik, danach kein 'EK fehlt' mehr")
def _():
    i = db.zukauf_artikel_liste()[0]["id"]
    for p in (0, -1, None):
        try:
            db.zukauf_ek_eintragen(i, p, "Technik")
            raise AssertionError(f"{p} angenommen")
        except ValueError:
            pass
    db.zukauf_ek_eintragen(i, 18.4, "Technik")
    a = db.zukauf_artikel(i)
    assert not zukauf.ek_fehlt(a) and len(a["bezuege"]) == 1, a["bezuege"]
    assert zukauf.staffel_sortiert(a["bezuege"][0]["preise"]) == [dict(ab=Decimal(1), preis=Decimal("18.4"))]
    assert a["fingerabdruck"] == B["fingerabdruck"], "Blechdaten bleiben"
    assert any(h["bemerkung"] == "EK eingetragen" for h in db.zukauf_historie(i))


# ------------------------------------------------------------------ Oberfläche
f = Hauptfenster(db, stumm=True)
f.resize(1920, 1000)
f.show()
f.reiter.setCurrentWidget(f.zukauf)
warten()
s = f.zukauf.artikel


@fall("Formular: Blechdaten sichtbar, Werkstoff nachtragen, Speichern behält STEP-Datei und Kennung")
def _():
    i = db.zukauf_artikel_liste()[0]["id"]
    fo = s.bearbeiten(i)
    warten()
    assert fo.artikeltyp.currentData() == "Blech" and fo.b_laenge.text() == "500" and fo.b_dicke.text() == "5"
    assert fo.werkstoff.currentText() == "" and fo.zeile_masse.isVisible(), "Werkstoff offen"
    assert "Rahmen.step" in fo.blech_info.text(), fo.blech_info.text()
    fo.werkstoff.setCurrentText("S235")
    assert fo.speichern(), fo.fehler.text()
    a = db.zukauf_artikel(i)
    assert a["werkstoff"] == "S235" and a["step_datei"] == "Rahmen.step" and a["fingerabdruck"] == B["fingerabdruck"]
    assert a["laenge"] == 500 and a["artikeltyp"] == "Blech"
    fo = s.neu()
    warten()
    assert fo.artikeltyp.currentData() == "" and not fo.zeile_masse.isVisible(), "normaler Artikel ohne Blechfelder"
    fo.artikeltyp.setCurrentIndex(fo.artikeltyp.findData("Blech"))
    fo.bezeichnung.setText("Blech von Hand")
    fo.kategorie.setCurrentText("Blechteile")
    fo.b_laenge.setText("0")
    fo.b_laenge.textEdited.emit("0")
    warten()
    assert not fo.speichern(), "Länge 0 nicht erlaubt"
    fo.b_laenge.setText("200")
    fo.b_breite.setText("100")
    fo.b_dicke.setText("2")
    assert fo.speichern(), fo.fehler.text()
    a = next(x for x in db.zukauf_artikel_liste() if x["bezeichnung"] == "Blech von Hand")
    assert (a["laenge"], a["breite"], a["dicke"], a["herkunft"]) == (200, 100, 2, None), a


@fall("Übersicht: Filter 'EK fehlt', Spalte EK 'EK fehlt' in Rot, EK eintragen aus der Übersicht")
def _():
    s.neu_laden()
    s.status_filter.setCurrentText("EK fehlt")
    warten()
    namen = [a["bezeichnung"] for a in s.sichtbar]
    assert namen == ["Blech von Hand"], namen
    assert s.zellen_text[0]["ek"] == "EK fehlt"
    s.auswaehlen(s.sichtbar[0]["id"])
    assert "EK fehlt" in s.detail.text() and "Blech 200 × 100 × 2 mm" in s.detail.text(), s.detail.text()
    assert s.k_ek.isEnabled()
    assert s.ek_eintragen(preis=7.5)
    s.status_filter.setCurrentText("EK fehlt")
    warten()
    assert s.sichtbar == [], [a["bezeichnung"] for a in s.sichtbar]
    s.status_filter.setCurrentText("Aktive")
    warten()
    a = next(x for x in s.sichtbar if x["bezeichnung"] == "Blech von Hand")
    assert s.zellen(a)["ek"] == "7,50 €", s.zellen(a)["ek"]
    assert [b["lieferant"] for b in a["bezuege"]] == ["Technik"], "Lieferant nach Vorgabe der Kategorie"


@fall("Duplizieren: Kopie ohne Herkunft, STEP-Datei und Kennung")
def _():
    i = next(x["id"] for x in db.zukauf_artikel_liste() if x.get("step_datei"))
    fo = s.duplizieren(i)
    warten()
    assert fo.speichern(), fo.fehler.text()
    k = next(x for x in db.zukauf_artikel_liste() if x["bezeichnung"].endswith("(Kopie)"))
    assert k["fingerabdruck"] is None and k["step_datei"] is None and k["laenge"] == 500, k


f.close()
db.con.close()
sys.exit(1 if fehler else 0)
