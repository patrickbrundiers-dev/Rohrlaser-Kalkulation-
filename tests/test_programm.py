"""Prüft das Windows-Programm (Schritt 1): Datenbank, Übernahme aus der Mappe, Prüfregeln, Oberfläche.

Aufruf: python tests/test_programm.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from openpyxl import load_workbook  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.mappe_import import lies_mappe  # noqa: E402
from rohrlaser.stammdaten import (TABELLE, PROFILE, PREISE, Kontext, beispieldaten, flaeche_berechnet,  # noqa: E402
                                  preis_je_m_automatisch, pruefen, wert_aus_text, wert_als_text)

MAPPE = HIER.parent / "mappe" / "Rohrlaser_Kalkulation_v02.xlsm"
tmp = Path(tempfile.mkdtemp())

# 1) Beispieldaten einer neuen Datenbank = Stammdaten der Mappe v02 (Übernahme liest alles, ohne Hinweise)
daten, einst, hinweise = lies_mappe(MAPPE)
assert hinweise == [], hinweise
assert daten == beispieldaten(), "Beispieldaten im Programm weichen von der Mappe ab"
assert einst["zuschlag_fertigung"] == 0.15 and einst["standard_stange"] == 6000 and einst["mwst"] == 0.19
assert einst["profilformen"].splitlines() == ["Rundrohr", "Quadratrohr", "Rechteckrohr", "Sonderprofil"]
db = Datenbank(tmp / "a" / "rohrlaser.db")
assert db.einstellung("stammdaten_herkunft") == "Beispieldaten"
for name, zeilen in beispieldaten().items():
    gelesen = [{k: v for k, v in z.items() if k != "id"} for z in db.zeilen(name)]
    assert gelesen == zeilen, name

# 2) Eingabe: deutsche Zahlen, Bereiche, ganze Zahlen, Datum
f = PROFILE.feld("a")
assert wert_aus_text(f, "42,4") == 42.4 and wert_aus_text(f, "42.4") == 42.4 and wert_aus_text(f, " ") is None
for falsch in ("abc", "0,5", "1001"):
    try:
        wert_aus_text(f, falsch)
        raise AssertionError(falsch)
    except ValueError:
        pass
fl = PREISE.feld("lieferlaenge")
assert wert_aus_text(fl, "6.000") == 6000 and wert_als_text(fl, 6000) == "6.000"
try:
    wert_aus_text(fl, "6000,5")
    raise AssertionError("ganze Zahl")
except ValueError:
    pass
assert wert_aus_text(PREISE.feld("gueltig_ab"), "01.10.2026") == "2026-10-01"
assert wert_als_text(PREISE.feld("preis"), 1234.5) == "1.234,50"

# 3) Berechnete Spalten wie die Formeln der Mappe
assert abs(flaeche_berechnet(dict(profil_id="x", form="Rundrohr", a=42.4, wand=2)) - math.pi / 4 * (42.4 ** 2 - 38.4 ** 2)) < 1e-9
assert flaeche_berechnet(dict(profil_id="x", form="Quadratrohr", a=40, wand=3)) == 40 * 40 - 34 * 34
assert flaeche_berechnet(dict(profil_id="x", form="Rechteckrohr", a=60, b=40, wand=3)) == 60 * 40 - 54 * 34
assert flaeche_berechnet(dict(profil_id="x", form="Rechteckrohr", a=60, b=None, wand=3)) is None
k = db.kontext()
p = preis_je_m_automatisch(dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219"), k)
assert abs(p - 444 * 7.85 / 1000 * 1000 / 1000) < 1e-9, p

# 4) Prüfung wie Spalte 'Prüfung' / Eingabeprüfungen der Mappe
ok = lambda t, z: pruefen(TABELLE[t], z, k)
assert ok("profile", dict(profil_id="RR 1", form="Rundrohr", a=20, wand=10)).startswith("FEHLER: Wandstärke")
assert ok("profile", dict(profil_id="RE 1", form="Rechteckrohr", a=60, wand=3)) == "FEHLER: Abmessung B fehlt"
assert ok("profile", dict(profil_id="SP 1", form="Sonderprofil", flaeche_manuell=300)) == "OK"
assert ok("profile", dict(profil_id="SP 2", form="Sonderprofil")).startswith("FEHLER: Querschnitt")
assert ok("profile", dict(profil_id="X", form="Dreieck", a=20, wand=2)) == "FEHLER: Profilform unbekannt"
z = dict(profil_id="RR 42,4x2,0", werkstoff_id="S235-10219", basis="€/kg", preis=1.2)
assert ok("preise", z) == "OK"
assert ok("preise", dict(z, profil_id="RR 99")) == "FEHLER: Profil-ID unbekannt"
assert ok("preise", dict(z, werkstoff_id="X")) == "FEHLER: Werkstoff-ID unbekannt"
assert ok("preise", dict(z, preis=None)) == "FEHLER: Preis [€] fehlt"
assert ok("preise", dict(z, basis="€/Stange")) == "FEHLER: Stangenlänge fehlt"
assert ok("schneiddaten", dict(maschinen_id="RL-9", werkstoff_id="1.4301", wand_bis=2, vorschub_gross=100)) \
    == "FEHLER: Maschinen-ID unbekannt"
for t in TABELLE.values():
    for zeile in db.zeilen(t.name):
        assert pruefen(t, zeile, k) == "OK", (t.name, zeile, pruefen(t, zeile, k))

# 5) Umbenennen eines Schlüssels ändert die Verweise mit; doppelte Schlüssel werden abgewiesen
pid = next(z["id"] for z in db.zeilen("profile") if z["profil_id"] == "RR 42,4x2,0")
assert db.verweise("profile", pid) == 2
db.aendern("profile", pid, "profil_id", "RR 42,4x2")
assert sum(1 for z in db.zeilen("preise") if z["profil_id"] == "RR 42,4x2") == 2
assert not any(z["profil_id"] == "RR 42,4x2,0" for z in db.zeilen("preise"))
try:
    db.aendern("profile", pid, "profil_id", "QR 40x40x3")
    raise AssertionError("doppelte Profil-ID angenommen")
except ValueError as e:
    assert "gibt es schon" in str(e)
wid = next(z["id"] for z in db.zeilen("werkstoffe") if z["werkstoff_id"] == "1.4301")
db.aendern("werkstoffe", wid, "werkstoff_id", "1.4301-K240")
assert sum(1 for z in db.zeilen("schneiddaten") if z["werkstoff_id"] == "1.4301-K240") == 3
neu = db.neu("preise")
db.aendern("preise", neu, "profil_id", "QR 40x40x3")
try:
    db.aendern("preise", neu, "werkstoff_id", "S235-10219")
    raise AssertionError("doppelter Preis angenommen")
except ValueError:
    pass
db.loeschen("preise", [neu])

# 6) Übernahme aus einer geänderten Mappe: doppelte Zeilen und unlesbare Werte werden gemeldet
m = tmp / "geaendert.xlsm"
shutil.copy(MAPPE, m)
wb = load_workbook(m, keep_vba=True)
wb["Preise"]["A10"], wb["Preise"]["B10"], wb["Preise"]["C10"], wb["Preise"]["D10"] = "RR 42,4x2,0", "S235-10219", "€/kg", 9
wb["Profile"]["C6"] = "48,3"           # Zahl als Text mit Komma
wb["Profile"]["E7"] = "drei"           # nicht lesbar
wb["Kalkulation"]["C5"] = 0.2
wb["Angebot"]["A1"] = "Muster Laser GmbH"
wb.save(m)
daten, einst, hinweise = lies_mappe(m)
assert len(daten["preise"]) == 5 and any("doppelt" in h and "Preise Zeile 10" in h for h in hinweise), hinweise
assert daten["profile"][1]["a"] == 48.3
assert daten["profile"][2]["wand"] is None and any("Profile Zeile 7" in h for h in hinweise), hinweise
assert einst["zuschlag_fertigung"] == 0.2 and einst["briefkopf_1"] == "Muster Laser GmbH"
db.stammdaten_ersetzen(daten, einst, "Mappe geaendert.xlsm")
assert db.einstellung("zuschlag_fertigung") == 0.2 and db.einstellung("stammdaten_herkunft") == "Mappe geaendert.xlsm"
assert [z["profil_id"] for z in db.zeilen("preise")].count("RR 42,4x2,0") == 2   # Verweise wieder wie in der Mappe
try:
    lies_mappe(HIER / "step" / "T01_RR42-4x2_L1250.step")
    raise AssertionError("fremde Datei angenommen")
except Exception:
    pass

# 7) Sicherung: vollständige Kopie, höchstens `behalten` Stück
for _ in range(4):
    s = db.sicherung(tmp / "sich", behalten=3)
assert len(list((tmp / "sich").glob("*.db"))) == 3
kopie = sqlite3.connect(s)
assert kopie.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == db.anzahl("profile")
kopie.close()
assert db.sicherung_heute(tmp / "sich") is None   # heute schon gesichert
db.schliessen()
db = Datenbank(tmp / "a" / "rohrlaser.db")      # wieder öffnen: Daten bleiben, keine Beispieldaten
assert db.einstellung("stammdaten_herkunft") == "Mappe geaendert.xlsm"

# 8) Oberfläche: Bearbeiten über das Tabellenmodell speichert sofort, ungültige Eingaben werden abgewiesen
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db)
seite = next(s for s in fenster.seiten if s.t.name == "profile")
mod = seite.modell
r = next(i for i, z in enumerate(mod.daten) if z["profil_id"] == "QR 40x40x3")
c = next(i for i, (art, s) in enumerate(mod.spalten) if art == "feld" and s.name == "wand")
assert mod.setData(mod.index(r, c), "2,5")
assert next(z for z in db.zeilen("profile") if z["profil_id"] == "QR 40x40x3")["wand"] == 2.5
fl_spalte = [i for i, (art, _) in enumerate(mod.spalten) if art == "berechnet"][0]
assert mod.data(mod.index(r, fl_spalte)) == "375,0"   # 40² − 35² neu berechnet
assert not mod.setData(mod.index(r, c), "abc")
assert "keine Zahl" in fenster.statusBar().currentMessage()
assert mod.setData(mod.index(r, c), "25")         # Wandstärke 25 > halbe Abmessung: Feld erlaubt, Prüfung meldet
assert mod.roh(r, len(mod.spalten) - 1).startswith("FEHLER: Wandstärke")
assert mod.setData(mod.index(r, c), "3") and mod.roh(r, len(mod.spalten) - 1) == "OK"
n = len(mod.daten)
neu_r = mod.zeile_neu()
assert len(mod.daten) == n + 1 and mod.roh(neu_r, len(mod.spalten) - 1).startswith("FEHLER: Profil-ID fehlt")
mod.zeilen_loeschen([neu_r])
assert len(mod.daten) == n
# Sortieren nach Zahlen, leere zuletzt
seite.ansicht.sortByColumn(next(i for i, (a, s) in enumerate(mod.spalten) if a == "feld" and s.name == "b"),
                           Qt.AscendingOrder)
werte = [seite.filter.index(i, 3).data(Qt.UserRole) for i in range(seite.filter.rowCount())]
gefuellt = [w for w in werte if w is not None]
assert gefuellt == sorted(gefuellt) and werte[:len(gefuellt)] == gefuellt, werte
seite.suche.setText("RE ")
assert seite.filter.rowCount() == 2
fenster.einstellungen.felder["gewinn"].setValue(12.5)
fenster.einstellungen.felder["gewinn"].editingFinished.emit()
assert db.einstellung("gewinn") == 0.125
assert fenster.mappe_uebernehmen(str(MAPPE), nachfragen=False)
assert db.einstellung("gewinn") == 0.1 and db.einstellung("stammdaten_herkunft").endswith("v02.xlsm")
fenster.close()
db.schliessen()
shutil.rmtree(tmp, ignore_errors=True)
print("OK: Programm")
