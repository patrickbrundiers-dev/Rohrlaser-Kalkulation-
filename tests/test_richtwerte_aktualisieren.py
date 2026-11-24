"""Richtwerte für alle Rechenwerte und „Richtwerte aktualisieren“ (Patrick 16.11.2026: „Alle Werte zur Berechnung mit
recherchierten Werten füllen, dass kein fester Wert genommen wird, Option zum Updaten der Einstellungen einbauen“):
- Grenzen und Zuschläge (Datenblätter Trumpf/BLM, sonst Schätzung) stehen in neuen Datendateien und kommen beim
  Update einmal in leere Felder; eigene Werte bleiben.
- Der Vergleich schlägt nur leere und vom Programm eingetragene Werte vor; eigene Werte und Felder, bei denen ein
  fester Wert gilt, sind nicht angehakt.
- Übernehmen schreibt nur die Auswahl und merkt sich die Werte.

Aufruf: python tests/test_richtwerte_aktualisieren.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import db_roh  # noqa: E402
from rohrlaser import richtwerte, stammdaten  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import StammdatenSeite  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())

# neue Datendatei: alle Richtwerte eingetragen und als Programmwerte gemerkt, nichts weicht ab
db = Datenbank(tmp / "neu.db")
ms = {z["maschinen_id"]: z for z in db.zeilen("maschinen")}
for mid in ("T03", "T11", "LT7"):
    for feld, w in zip(stammdaten.WEITERE_FELDER, stammdaten.WEITERE_RICHTWERTE[mid]):
        assert ms[mid][feld] == w, (mid, feld, ms[mid][feld], w)
assert ms["T11"]["entlade_laenge"] == 3000 and ms["LT7"]["entlade_laenge"] == 4500 and ms["LT7"]["lademinimum"] == 1900
merker = db.einstellung(richtwerte.MERKER)
assert set(merker) == {"T03", "T11", "LT7"} and merker["T11"]["max_stange_kg"] == 162
assert richtwerte.vergleich(db.zeilen("maschinen"), merker) == []
ok("Neue Datendatei: Grenzen und Zuschläge vorbelegt (T11 Entladen 3 m, LT7 4,5 m, Laden ab 1,9 m), nichts weicht ab")

# neue Richtwerte: Programmwert vorgeschlagen, eigener Wert nicht, leeres Feld vorgeschlagen, fester Wert nicht
i = stammdaten.WEITERE_FELDER.index("abfall_max")
alt_t11 = stammdaten.WEITERE_RICHTWERTE["T11"]
stammdaten.WEITERE_RICHTWERTE["T11"] = alt_t11[:i] + (120,) + alt_t11[i + 1:]
stammdaten.WEITERE_RICHTWERTE["T03"] = stammdaten.WEITERE_RICHTWERTE["T11"]
db.aendern("maschinen", ms["LT7"]["id"], "zeit_ausrichten", 12)
db.aendern("maschinen", ms["T03"]["id"], "handling_kg", None)
db.aendern("maschinen", ms["T11"]["id"], "zeit_teil", 3)
db.aendern("maschinen", ms["T11"]["id"], "entladen_grund", None)
v = {(x["maschinen_id"], x["feld"]): x for x in richtwerte.vergleich(db.zeilen("maschinen"),
                                                                      db.einstellung(richtwerte.MERKER))}
assert v[("T11", "abfall_max")]["art"] == richtwerte.ALT and v[("T11", "abfall_max")]["vorschlag"]
assert v[("LT7", "zeit_ausrichten")]["art"] == richtwerte.EIGEN and not v[("LT7", "zeit_ausrichten")]["vorschlag"]
assert v[("T03", "handling_kg")]["art"] == richtwerte.LEER and v[("T03", "handling_kg")]["vorschlag"]
assert v[("T11", "entladen_grund")]["art"] == richtwerte.FEST and not v[("T11", "entladen_grund")]["vorschlag"]
assert "Datenblatt" in v[("T11", "abfall_max")]["quelle"] or v[("T11", "abfall_max")]["quelle"] == "Schätzung"
ok("Vergleich: Programmwert und leeres Feld vorgeschlagen, eigener Wert und Feld mit festem Wert nicht")

# Fenster Maschinen: Knopf zeigt die Anzahl, Übernehmen nur die Vorschläge, eigener Wert bleibt
seite = StammdatenSeite(db, stammdaten.MASCHINEN, lambda *a, **k: None)
seite.zaehlen()
n_vor = sum(1 for x in v.values() if x["vorschlag"])
assert f"({n_vor})" in seite.richtwerte_knopf.text(), seite.richtwerte_knopf.text()
n = seite.richtwerte_aktualisieren("vorschlag")
assert n == n_vor, (n, n_vor)
ms = {z["maschinen_id"]: z for z in db.zeilen("maschinen")}
assert ms["T11"]["abfall_max"] == 120 and ms["T03"]["handling_kg"] == 15 and ms["LT7"]["zeit_ausrichten"] == 12
assert ms["T11"]["entladen_grund"] is None and ms["T11"]["zeit_teil"] == 3
rest = richtwerte.vergleich(db.zeilen("maschinen"), db.einstellung(richtwerte.MERKER))
assert not any(x["vorschlag"] for x in rest) and seite.richtwerte_knopf.text() == "Richtwerte aktualisieren …"
# eigenen Wert gezielt übernehmen
assert seite.richtwerte_aktualisieren([("LT7", "zeit_ausrichten")]) == 1
assert {z["maschinen_id"]: z for z in db.zeilen("maschinen")}["LT7"]["zeit_ausrichten"] == 10
ok(f"Fenster: Knopf „Richtwerte aktualisieren ({n_vor})“, übernimmt nur Vorschläge; eigener Wert nur, wenn angehakt")
stammdaten.WEITERE_RICHTWERTE["T11"] = stammdaten.WEITERE_RICHTWERTE["T03"] = alt_t11

# Fenster öffnet ohne Fehler (Vergleich mit Haken)
from PySide6.QtCore import QTimer  # noqa: E402
QTimer.singleShot(0, lambda: seite._richtwerte_fenster.reject())
assert seite.richtwerte_aktualisieren() == 0
ok("Fenster mit Vergleichstabelle öffnet, Abbrechen ändert nichts")

# vorhandene Datendatei (Update): einmal in leere Felder, eigene Werte bleiben
pfad = tmp / "update.db"
d2 = Datenbank(pfad)
d2.con.close()
con = db_roh.verbinden(pfad)
con.execute("DELETE FROM einstellungen WHERE name IN ('richtwerte_weitere', 'richtwerte_eingetragen')")
con.execute("UPDATE maschinen SET entlade_laenge = NULL, lademinimum = NULL, kleines_rohr_bis = NULL")
con.execute("UPDATE maschinen SET entlade_laenge = 2500 WHERE maschinen_id = 'T11'")
con.commit()
con.close()
d2 = Datenbank(pfad)
ms = {z["maschinen_id"]: z for z in d2.zeilen("maschinen")}
assert ms["T11"]["entlade_laenge"] == 2500 and ms["LT7"]["entlade_laenge"] == 4500 and ms["T03"]["lademinimum"] == 2000
merker = d2.einstellung(richtwerte.MERKER)
assert "entlade_laenge" not in merker.get("T11", {}) and merker["LT7"]["entlade_laenge"] == 4500
ok("Update: Richtwerte einmal in leere Felder, eigener Wert (T11 Entladen 2.500 mm) bleibt und gilt als eigener Wert")
print("Richtwerte aktualisieren: alle Tests bestanden.")
