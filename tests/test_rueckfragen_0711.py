"""Rückfragen durch Rückgängig ersetzt (Vorschlag N2, Patrick 07.11.2026 „R1 … R11“). Hier R1 (Stammdaten-Zeilen
löschen) und R8 (große STEP-Datei ohne Frage); R2 test_baugruppe, R3 test_fracht_richtwerte, R4 test_baugruppe,
R6 test_konturvorlagen, R7 test_schneidweg, R10 test_zukauf_preise, R11 test_vorschlaege_0211.

Aufruf: python tests/test_rueckfragen_0711.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QItemSelectionModel  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "r.db")
for nr in ("K-1", "K-2", "K-3"):
    db.neu("kunden", dict(kundennr=nr, name=f"Kunde {nr}"))
f = Hauptfenster(db, stumm=True)
seite = next(s for s in f.seiten if s.t.name == "kunden")
seite.modell.neu_laden()
vorher = db.zeilen("kunden", mit_uid=True)
sel = seite.ansicht.selectionModel()
for r in (0, 1):
    sel.select(seite.filter.index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)
seite.zeilen_loeschen()
assert len(db.zeilen("kunden")) == len(vorher) - 2 and "gelöscht" in f.letzte_meldung, f.letzte_meldung
assert f.letzte_aktion[0] == "Rückgängig"
f.letzte_aktion[1]()
assert db.zeilen("kunden", mit_uid=True) == vorher, "Zeilen samt id, uid und Werten zurück"
assert seite.modell.rowCount() == len(vorher)
print("OK     R1 Stammdaten: Zeilen löschen ohne Rückfrage, Rückgängig stellt sie samt Kennung wieder her")

gross = tmp / "gross.step"
with open(gross, "wb") as d:
    d.truncate(int(step.GROSS_AB_MB * 1e6) + 1000)
t = step.grosse_dateien([gross])
assert t and "?" not in t and "gross.step" in t
print("OK     R8 große STEP-Datei: Hinweis für die Fortschrittsanzeige, keine Frage")
db.con.close()
print("Rückfragen 07.11.: alle Tests bestanden.")
