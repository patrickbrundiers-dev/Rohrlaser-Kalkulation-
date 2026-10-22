"""Prüft den Export der Stammdaten für die Android-App: alle Stammdatentabellen mit Feldbeschreibung und Zeilen,
Einstellungen ohne Passwort, Menüpunkt im Hauptfenster, Datei gültiges JSON (wie die App sie liest).

Aufruf: python tests/test_handy_export.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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

from rohrlaser import handy_export  # noqa: E402
from rohrlaser.datenbank import ALLE_TABELLEN, Datenbank  # noqa: E402
from rohrlaser.fenster import STIL, Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyleSheet(STIL)
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


db = Datenbank(tmp / "h.db")
db.einstellung_setzen("passwort", "geheim")
db.einstellung_setzen("standard_stange", 6500)
db.neu("kunden", dict(kundennr="10001", name="Stahlbau Test GmbH", plz_ort="33129 Delbrück"))

ziel = tmp / "ablage" / "Stammdaten.json"
anzahl = handy_export.schreiben(db, ziel)
d = json.loads(ziel.read_text(encoding="utf-8"))
assert d["format"] == "rohrlaser-stammdaten" and d["version"] == 1, d["format"]
assert set(d["tabellen"]) == {t.name for t in ALLE_TABELLEN}, set(d["tabellen"])
for t in ALLE_TABELLEN:
    assert len(d["tabellen"][t.name]["zeilen"]) == db.anzahl(t.name) == anzahl[t.name], t.name
    assert [f["name"] for f in d["tabellen"][t.name]["felder"]] == [f.name for f in t.felder], t.name
    assert all("id" not in z for z in d["tabellen"][t.name]["zeilen"]), t.name
ok(f"alle {len(ALLE_TABELLEN)} Stammdatentabellen mit Feldern und Zeilen ({sum(anzahl.values())} Zeilen)")
assert any(z["kundennr"] == "10001" for z in d["tabellen"]["kunden"]["zeilen"])
assert d["einstellungen"]["standard_stange"] == 6500 and "passwort" not in d["einstellungen"]
assert all(e["name"] != "passwort" for e in d["einstellungen_beschreibung"])
assert "geheim" not in ziel.read_text(encoding="utf-8")
ok("Einstellungen dabei, Passwort nicht")
assert not ziel.with_name(ziel.name + ".neu").exists()
assert handy_export.vorschlag(tmp).name.startswith("Rohrlaser-Stammdaten ")

fenster = Hauptfenster(db, stumm=True)
menue = [a.text() for m in fenster.menuBar().actions() for a in m.menu().actions()]
assert "Stammdaten fürs Handy exportieren …" in menue, menue
ziel2 = tmp / "Handy.json"
assert fenster.handy_export_schreiben(ziel2)["profile"] == db.anzahl("profile")
assert json.loads(ziel2.read_text(encoding="utf-8"))["programm"]
ok("Menü Datei → Stammdaten fürs Handy exportieren …")
print("Alle Prüfungen bestanden.")
