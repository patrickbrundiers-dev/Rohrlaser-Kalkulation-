"""Maschinen-Editor je Maschine (Patrick 16.11.2026: „Einen Maschinen-Editor erstellen je Maschine, übersichtlich
gestalten, so wie jetzt alles in einer Reihe ist zu unübersichtlich“; Aufbau „Liste links, Editor rechts“):
- Jedes Maschinenfeld steht in genau einer Gruppe.
- Links die Maschinen, Auswahl folgt der Tabelle (Knöpfe Stundensatz/Datei/Löschen nutzen deren Auswahl).
- Speichern über das Tabellenmodell (Prüfung, Meldung), falsche Werte werden abgelehnt.
- Richtwert anzeigen und zurücksetzen; nicht wirksame Werte mit Grund; Rechenweg der Gruppe.
- „Als Tabelle“ schaltet auf die bisherige Tabelle um.

Aufruf: python tests/test_maschinen_editor.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import maschinen_editor as me, stammdaten  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import StammdatenSeite  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])

# Gruppen decken alle Felder genau einmal ab
alle = [f.name for f in stammdaten.MASCHINEN.felder]
in_gruppen = [n for g in me.GRUPPEN for n in g[3]]
assert sorted(in_gruppen) == sorted(alle), (set(alle) ^ set(in_gruppen), len(in_gruppen), len(alle))
assert all(me.gruppe_von(n) for n in alle)
ok(f"{len(alle)} Felder in {len(me.GRUPPEN)} Gruppen, jedes genau einmal")

# Beschriftung ohne Vorsilbe, Zusatz aus der Klammer
f = stammdaten.MASCHINEN.feld
assert me.beschriftung(f("eilgang_x")) == ("Eilgang X [m/min]", ""), me.beschriftung(f("eilgang_x"))
assert me.beschriftung(f("zeit_laden")) == ("Laden [s]", "leer = fester Stangenwechsel"), me.beschriftung(f("zeit_laden"))
assert me.richtwert("beschl_dreh", "T11") == 3000 and me.richtwert("zeit_laden", "XY") == 8
assert me.richtwert("stundensatz", "T11") is None
ok("Bezeichnung ohne Gruppen-Vorsilbe, Richtwerte je Maschine (fremde Maschine: Werte der T11)")

# nicht wirksame Werte
m = {"zeit_laden": 8, "eilgang_x": 100, "beschl_x": 10, "max_stange": 6500, "entladen_grund": 1}
assert "berechnet" in me.nicht_wirksam("stangenwechsel", m)
assert me.nicht_wirksam("zeit_spannen", m) is None and me.nicht_wirksam("zeit_spannen", {}) is not None
assert "berechnet" in me.nicht_wirksam("zeit_entladen", m) and me.nicht_wirksam("entladen_je_m", m) is None
assert me.nicht_wirksam("schwenk_min", {"d3": "nein"}) and me.nicht_wirksam("schwenk_min", {"d3": "ja"}) is None
assert me.nicht_wirksam("d3", {}) is None
assert me.nicht_wirksam("anschaffung", {"satz_art": "von Hand"}) and not me.nicht_wirksam("anschaffung", {"satz_art": "ermittelt"})
ok("Werte, die gerade nicht in die Rechnung eingehen, nennen den Grund")

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
meldungen = []
seite = StammdatenSeite(db, stammdaten.MASCHINEN, lambda t, fehler=False: meldungen.append((t, fehler)))
seite.resize(1366, 800)
seite.show()
app.processEvents()
ed = seite.editor
assert seite.ansicht_stapel.currentWidget() is ed
assert ed.liste.count() == 3 and ed.liste.item(0).text().startswith("T03")
assert ed.gruppen.count() == len(me.GRUPPEN)
ok("Maschinen-Seite öffnet den Editor: 3 Maschinen links, 11 Gruppen")

ed.liste.setCurrentRow(1)
app.processEvents()
assert ed.aktuelle_id() == "T11" and seite.ansicht.currentIndex().row() == 1
assert ed.kopf.text().startswith("T11")
seite.ansicht.selectRow(2)
app.processEvents()
assert ed.aktuelle_id() == "LT7"
ed.liste.setCurrentRow(1)
ok("Auswahl in Liste und Tabelle laufen mit (Stundensatz, Datei, Löschen nehmen die gewählte Maschine)")

ed.gruppe_zeigen("laden")
assert "Stangenwechsel berechnet" in ed.ergebnisse["laden"].text()
alt = ed.ergebnisse["laden"].text()
assert ed.speichern("zeit_laden", "10")
t11 = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
assert t11["zeit_laden"] == 10 and ed.aktuelle_id() == "T11"
assert ed.ergebnisse["laden"].text() != alt
z = ed.zeilen["zeit_laden"]
assert z.zurueck.isVisible() or not z.zurueck.isHidden()
assert "Richtwert 8" in z.hinweis.text()
z.auf_richtwert()
t11 = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
assert t11["zeit_laden"] == 8 and ed.zeilen["zeit_laden"].zurueck.isHidden()
ok("Wert speichern rechnet den Stangenwechsel neu; ↺ setzt auf den Richtwert zurück")

meldungen.clear()
assert not ed.speichern("zeit_laden", "abc")
assert meldungen and meldungen[-1][1]
assert ed.zeilen["zeit_laden"].eingabe.text() == "8"
assert not ed.speichern("beschl_dreh", "999999")
ok("Falsche Eingaben werden mit Meldung abgelehnt, das Feld zeigt wieder den gespeicherten Wert")

ed.zeilen["einstich_ueberwachung"].eingabe.setCurrentText("nein")
ed.zeilen["einstich_ueberwachung"].speichern("nein")
t11 = next(z for z in db.zeilen("maschinen") if z["maschinen_id"] == "T11")
assert t11["einstich_ueberwachung"] == "nein"
ok("Auswahlfelder (ja/nein) speichern")

seite.suche.setText("LT7")
app.processEvents()
assert ed.liste.count() == 1 and ed.aktuelle_id() == "LT7"
seite.suche.clear()
app.processEvents()
assert ed.liste.count() == 3 and ed.aktuelle_id() == "LT7"
ok("Suche filtert die Maschinenliste")

seite.maschinen_ansicht(True)
assert seite.ansicht_stapel.currentWidget() is seite.ansicht and seite.als_tabelle.isChecked()
seite.als_tabelle.setChecked(False)
assert seite.ansicht_stapel.currentWidget() is ed
ok("„Als Tabelle“ schaltet auf die Tabelle und zurück")

seite.modell.admin_gesperrt = True
ed.zeigen(ed.aktuelle_zeile())
assert not ed.zeilen["zeit_laden"].eingabe.isEnabled()
seite.modell.admin_gesperrt = False
ok("Admin-Schutz: ansehen ja, ändern nein")

print("Maschinen-Editor: alle Tests bestanden.")
