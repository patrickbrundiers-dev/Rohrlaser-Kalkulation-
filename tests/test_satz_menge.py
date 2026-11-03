"""Prüft „Anzahl Sätze und Stück je Satz ändern“ (satz_menge.py, satz_dialog.py, Patrick 31.10.2026, Freigabe „Alle
Empfehlungen“): Anzahl Sätze setzen (Stückzahl = Sätze × Stück je Satz), Stück je Satz ändern (Stückzahl folgt),
Stückzahl einer Satzposition ändern (Stück je Satz folgt, geht es nicht auf: Hinweis, nichts gerundet), Fenster
„Satz bearbeiten“ (Doppelklick auf Spalte Satz, Rechtsklick), Feld „Anzahl Sätze“ im Satz in 3D, Rückgängig.

Aufruf: python tests/test_satz_menge.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rohrlaser import satz_menge  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ ohne Oberfläche
pos = [dict(id=1, satz="A", je_satz=2, stueck=6), dict(id=2, satz="A", je_satz=1, stueck=3),
       dict(id=3, stueck=5), dict(id=4, satz="A", je_satz=None, stueck=3)]
assert satz_menge.satz_positionen(pos, "A") == [0, 1, 3]
assert satz_menge.anzahl(pos, "A") == 3
assert satz_menge.saetze_setzen(pos, "A", 5) == [(1, "stueck", 10), (2, "stueck", 5), (4, "stueck", 5)]
assert satz_menge.saetze_setzen(pos, "A", 3, je={2: 4}) == [(2, "je_satz", 4), (2, "stueck", 12)]
ok("Anzahl Sätze setzen: Stückzahl = Sätze × Stück je Satz (leer = 1), Stück je Satz je Position dazu")

aend, h = satz_menge.je_satz_geaendert(pos[0], pos, 3)
assert aend == [(1, "stueck", 9)] and "3 Sätze" in h
assert satz_menge.je_satz_geaendert(pos[2], pos, 3) == ([], None)        # ohne Satz: nichts
ok("Stück je Satz geändert: Stückzahl zieht mit, Anzahl Sätze bleibt")

aend, h = satz_menge.stueck_geaendert(pos[1], pos, 6)
assert aend == [(2, "je_satz", 2)] and "= 2" in h
aend, h = satz_menge.stueck_geaendert(pos[1], pos, 7)
assert aend == [] and "nicht in ganzen Stück" in h                          # F3a: nichts gerundet
assert satz_menge.stueck_geaendert(pos[2], pos, 7) == ([], None)
assert satz_menge.stueck_geaendert(dict(id=9, satz="B", stueck=2), [dict(id=9, satz="B", stueck=2)], 4) == ([], None)
ok("Stückzahl einer Satzposition geändert: Stück je Satz folgt; geht es nicht auf, Hinweis und nichts gerundet")

uneben = [dict(id=1, satz="A", je_satz=1, stueck=2), dict(id=2, satz="A", je_satz=1, stueck=3)]
assert satz_menge.anzahl(uneben, "A") == 3                                  # Gleichstand: die größte (wie Angebot)
ok("Anzahl Sätze bei Abweichung: häufigste, bei Gleichstand die größte")

# ------------------------------------------------------------------ Angebotsseite
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
a = db.angebot_neu(dict(kunde="Test", kundennr="4711"))
for nr, satz, je in ((10, "Gestell", 2), (20, None, None), (30, "Gestell", 1)):
    w = dict(pos=nr, artikel=f"T{nr}", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500 + nr,
             stueck=4 * (je or 1), schneidweg=320, einstiche=2)
    if satz:
        w.update(satz=satz, je_satz=je)
    db.position_neu(a, w)
s = fenster.angebot_oeffnen(a)
QApplication.processEvents()


def stueck():
    return [(p.get("je_satz"), p.get("stueck")) for p in s.positionen]


assert stueck() == [(2, 8), (None, 4), (1, 4)]

# Fenster „Satz bearbeiten“: 4 -> 6 Sätze, Pos. 30 Stück je Satz 3
gesehen = {}


def bedienen(d):
    gesehen["titel"] = d.windowTitle()
    d.plus.click()
    d.plus.click()
    d.spins[1].setValue(3)
    gesehen["live"] = d.stueckzahlen()
    d._ok()
    return QDialog.Accepted


assert s.satz_bearbeiten(0, dialog=bedienen)
assert gesehen["titel"] == "Satz bearbeiten: Gestell" and gesehen["live"] == [12, 18]
assert stueck() == [(2, 12), (None, 4), (3, 18)], stueck()
s.rueckgaengig()
QApplication.processEvents()
assert stueck() == [(2, 8), (None, 4), (1, 4)], stueck()
ok("Fenster Satz bearbeiten: − / + Anzahl Sätze, Stück je Satz, Stückzahlen live; ein Schritt für Rückgängig")

assert "Satz bearbeiten (Anzahl Sätze) …" in s.pos_aktionen
s.pos_ansicht.selectRow(1)
assert "Satz bearbeiten (Anzahl Sätze) …" not in s._pos_menue_anpassen()
s.pos_ansicht.clearSelection()
s.pos_ansicht.selectRow(0)
assert "Satz bearbeiten (Anzahl Sätze) …" in s._pos_menue_anpassen()
spalte = next(c for c in range(len(s.pos_modell.spalten)) if s.pos_modell.name(c) == "satz")
aufgerufen = []
alt = s.satz_bearbeiten
s.satz_bearbeiten = lambda r=None, **k: aufgerufen.append(r)
s._doppelklick(s.pos_modell.index(0, spalte))
s._doppelklick(s.pos_modell.index(1, spalte))       # ohne Satz: Zelle bearbeiten wie bisher
s.satz_bearbeiten = alt
assert aufgerufen == [0], aufgerufen
ok("Rechtsklick „Satz bearbeiten …“ nur bei Satzpositionen; Doppelklick auf Spalte Satz öffnet das Fenster")

# Eingabe in der Liste: Stück je Satz -> Stückzahl folgt; Stückzahl -> Stück je Satz folgt
m = s.pos_modell
c_je = next(c for c in range(len(m.spalten)) if m.name(c) == "je_satz")
c_st = next(c for c in range(len(m.spalten)) if m.name(c) == "stueck")
assert m.setData(m.index(0, c_je), "3")
QApplication.processEvents()
assert stueck()[0] == (3, 12), stueck()
assert m.setData(m.index(2, c_st), "8")
QApplication.processEvents()
assert stueck()[2] == (2, 8), stueck()
assert m.setData(m.index(2, c_st), "9")        # 9 auf 4 Sätze geht nicht auf: bleibt, Stück je Satz unverändert
QApplication.processEvents()
assert stueck()[2] == (2, 9), stueck()
assert m.setData(m.index(1, c_st), "7")        # ohne Satz: wie bisher
QApplication.processEvents()
assert stueck()[1] == (None, 7)
ok("Liste: Stück je Satz ändern zieht Stückzahl mit, Stückzahl ändern zieht Stück je Satz mit (F1a, F3a)")

# Satz in 3D: Feld Anzahl Sätze
m.setData(m.index(2, c_st), "8")
QApplication.processEvents()


def satz3d(d):
    assert d.saetze_feld.value() == 4
    d.saetze_feld.setValue(5)
    d._ok()
    return QDialog.Accepted


assert s.satz_3d(satz="Gestell", dialog=satz3d)
QApplication.processEvents()
assert stueck()[0] == (3, 15) and stueck()[2] == (2, 10), stueck()
ok("Satz in 3D: Feld Anzahl Sätze, Stückzahlen folgen mit OK")
print("Alle Prüfungen bestanden.")
