"""Rechtsklick-Menü der Positionen aufgeräumt (Patrick 26.11.2026, positionsmenue.py).

- M1 Ordnung: jeder Eintrag genau einmal, oben die täglichen Aktionen, Seltenes in Untermenüs, Löschen ganz unten mit
     Linie davor; der doppelte Eintrag „Blech-EK je Satz/Baugruppe …“ ist in „Satz bearbeiten …“ aufgegangen
- M2 Dynamisch: nur passende Einträge; ein Untermenü ohne passenden Eintrag verschwindet; „Satz bearbeiten …“ bei
     Sätzen und Baugruppen
- M3 Löschen: eine oder zwei Positionen ohne Rückfrage (Rückgängig), ab drei Positionen bzw. bei einem ganzen Satz mit
     Rückfrage; Nein löscht nichts

Aufruf: python tests/test_positionsmenue.py   (ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QItemSelectionModel  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from rohrlaser import positionsmenue as pm  # noqa: E402
from rohrlaser.angebot import ZUKAUFTEIL  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
k = db.kontext()
profil = next(iter(k.profile))
werkstoff = next(iter(k.werkstoffe))
aid = db.angebot_neu(dict(kunde="Test"))
for i in range(5):
    db.position_neu(aid, dict(pos=(i + 1) * 10, artikel=f"A{i}", stueck=2, profil_id=profil, werkstoff_id=werkstoff,
                              laenge=500 + i, satz="Gestell" if i in (3, 4) else None))
db.position_neu(aid, dict(pos=60, artikel="Z", stueck=1, art=ZUKAUFTEIL, bezeichnung="Schraube"))
s = f.angebot_oeffnen(aid)


def markieren(zeilen):
    s.pos_ansicht.clearSelection()
    sel = s.pos_ansicht.selectionModel()
    for r in zeilen:
        sel.select(s.pos_modell.index(r, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)


# ------------------------------------------------------------------ M1 Ordnung
alle = pm.eintraege()
assert len(alle) == len(set(alle)) and set(alle) == set(s.pos_aktionen), set(alle) ^ set(s.pos_aktionen)
assert "Blech-EK je Satz/Baugruppe …" not in s.pos_aktionen
oben = [a.text().split("\t")[0] for a in s.pos_menue.actions() if not a.isSeparator()]
direkt = [t for t in alle if pm.untermenue_von(t) is None]
assert len(direkt) <= 14, direkt                                  # bisher 49 Einträge untereinander
assert oben[:3] == ["Schneidweg berechnen …", "Blech-Editor …", "Richtpreis Dreh-/Frästeil …"], oben
assert oben[-1] == "Positionen löschen" and s.pos_menue.actions()[-2].isSeparator()
assert set(s.pos_untermenues) == {"Prüfen und anzeigen", "Teil ändern", "Kennzeichnen", "Satz und Baugruppe",
                                  "Reihenfolge"}
for titel, menue in s.pos_untermenues.items():
    assert titel in oben and all(pm.untermenue_von(a.text().split("\t")[0]) == titel for a in menue.actions())
assert pm.untermenue_von("Nach oben") == "Reihenfolge" and s.pos_aktionen["Nach oben"].text().endswith("\tAlt+↑")
assert not s.pos_aktionen["Positionen löschen"].icon().isNull()
ok("M1 49 Einträge → Hauptaktionen oben, fünf Untermenüs, Löschen abgesetzt, kein doppelter Eintrag")

# ------------------------------------------------------------------ M2 Dynamisch
s.neu_laden()
zuk = next(r for r, p in enumerate(s.positionen) if s.position_art(p) == "zukauf")
einzel = next(r for r, p in enumerate(s.positionen) if s.position_art(p) == "rohr" and not p.get("satz"))
satz = [r for r, p in enumerate(s.positionen) if p.get("satz") == "Gestell"]
markieren([zuk])
sichtbar = s._pos_menue_anpassen()
assert "Schneidweg berechnen …" not in sichtbar and "Satz in 3D …" not in sichtbar
assert s.pos_untermenues["Reihenfolge"].menuAction().isVisible()
for menue in s.pos_untermenues.values():          # Untermenü sichtbar genau dann, wenn ein Eintrag darin passt
    assert menue.menuAction().isVisible() == any(a.isVisible() for a in menue.actions())
markieren([einzel])
sichtbar = s._pos_menue_anpassen()
assert "Schneidweg berechnen …" in sichtbar and "Satz bearbeiten (Anzahl Sätze) …" not in sichtbar
assert s.pos_untermenues["Teil ändern"].menuAction().isVisible()
markieren([satz[0]])
assert "Satz bearbeiten (Anzahl Sätze) …" in s._pos_menue_anpassen()
assert s.pos_untermenues["Satz und Baugruppe"].menuAction().isVisible()
ok("M2 nur passende Einträge, leere Untermenüs verschwinden, Satz bearbeiten bei Sätzen")

# ------------------------------------------------------------------ M3 Löschen
assert not pm.loeschen_fragen(1) and not pm.loeschen_fragen(2) and pm.loeschen_fragen(3) and pm.loeschen_fragen(1, True)
gefragt = []
echt = QMessageBox.question
QMessageBox.question = staticmethod(lambda *a, **kw: gefragt.append(a[2]) or QMessageBox.No)
f.stumm = False
try:
    n = len(db.positionen(aid))
    markieren([einzel])
    s.positionen_loeschen()
    assert not gefragt and len(db.positionen(aid)) == n - 1        # eine: ohne Rückfrage, Rückgängig
    s.rueckgaengig()
    s.neu_laden()
    markieren(satz)                                                # ganzer Satz
    s.positionen_loeschen()
    assert len(gefragt) == 1 and "Satz" in gefragt[0] and len(db.positionen(aid)) == n      # Nein: nichts weg
    markieren([0, 1, 2])
    s.positionen_loeschen()
    assert len(gefragt) == 2 and "3 Position(en)" in gefragt[1] and len(db.positionen(aid)) == n
    QMessageBox.question = staticmethod(lambda *a, **kw: QMessageBox.Yes)
    s.positionen_loeschen()
    assert len(db.positionen(aid)) == n - 3
finally:
    QMessageBox.question = echt
    f.stumm = True
ok("M3 Löschen: 1–2 Positionen mit Rückgängig, ab 3 bzw. ganzer Satz mit Rückfrage, Nein löscht nichts")
print("Alle Prüfungen bestanden.")
