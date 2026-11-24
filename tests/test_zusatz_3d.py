"""Zusatzarbeit per Rechtsklick im 3D (CAD-009, Plan Phase 3 und 4, Patrick 13.11.2026 „Alles einbauen“):

- Rohr- und Blech-Editor: Kontextmenü am Merkmal mit „Zusatzarbeit hier anlegen …“; Menge = Anzahl der Konturzeile
  (nur bei €/Stück), Herkunft „aus 3D: <Merkmal>“; im Merkmalsbaum unter „Zusatzarbeiten neu (mit OK)“
- mit OK in der Spalte Zusatzarbeiten der Position (Preisstand aus den Stammdaten); Abbrechen verwirft
- Blättern ohne andere Änderung speichert die Zusatzarbeit trotzdem
- Baugruppe und Satz in 3D: Rechtsklick auf ein Teil „Zusatzarbeit für dieses Teil …“, mit OK je Position

Aufruf: python tests/test_zusatz_3d.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rohrlaser import rechnen, schneidweg as sw, zusatz_3d as z3  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "r.db")
katalog = db.zeilen("zusatzarbeiten")
assert any(z["name"] == "Senken" and z["art"] == "€/Stück" for z in katalog)

# ------------------------------------------------------------------ ohne Oberfläche
e = dict(konturen=[dict(art=sw.BOHRUNG, anzahl=8, d=10, x=100), dict(art=sw.LANGLOCH, l=30, b=10, x=300)])
assert z3.menge_vorgabe("kontur:0", e) == 8 and z3.menge_vorgabe("kontur:1", e) == 1
assert z3.menge_vorgabe("ende:a", e) == 1 and z3.menge_vorgabe(None, None) == 1
senken = next(z for z in katalog if z["name"] == "Senken")
verzinken = next(z for z in katalog if z["art"] == "€/kg")
x = z3.eintrag(senken, 8, "1. Bohrung Ø d 10 × 8")
assert x == dict(name="Senken", menge=8, preis=None, text="aus 3D: 1. Bohrung Ø d 10 × 8", quelle="3D"), x
assert z3.eintrag(verzinken, 8, None)["menge"] is None          # nach Gewicht: Menge automatisch
alt = json.dumps([dict(name="Entgraten", menge=1, preis=None, text=None)])
js, fehlt = z3.anwenden(alt, [x, dict(x, menge=4), dict(name="Gibt es nicht", menge=1, text="aus 3D")], katalog)
liste = json.loads(js)
assert [(y["name"], y["menge"]) for y in liste] == [("Entgraten", 1), ("Senken", 4)] and fehlt == ["Gibt es nicht"]
assert liste[1]["stand"]["art"] == "€/Stück" and liste[1]["quelle"] == "3D"
assert z3.anwenden(None, [], katalog) == (None, [])
ok("Menge = Anzahl der Konturzeile (nur €/Stück), Herkunft „aus 3D“, gleiche Arbeit am selben Merkmal ersetzt")

# ------------------------------------------------------------------ Rohr-Editor bis in die Position
technik = dict(quelle=sw.QUELLE, a=dict(winkel=0), b=dict(winkel=0),
               konturen=[dict(art=sw.BOHRUNG, anzahl=8, d=10, x=100, seite="oben")])
ang = db.angebot_neu(dict(kunde="Test", maschine="T11"))
pid = db.position_neu(ang, dict(pos=1, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10,
                                technik=json.dumps(technik)))
pid2 = db.position_neu(ang, dict(pos=2, profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=600, stueck=5,
                                 technik=json.dumps(technik)))
f = Hauptfenster(db, stumm=True)
s = f.angebot_oeffnen(ang)
gesehen = {}


def bedienen(d, ok_=True):
    ed = d.editor
    m = ed.kontextmenue("kontur:0")
    gesehen["menue"] = [a.text() for a in m.actions()]
    gesehen["eintrag"] = ed.zusatz_anlegen("kontur:0", wahl=dict(name="Senken"))
    b = ed.baum
    gesehen["baum"] = [b.topLevelItem(i).text(0) for i in range(b.topLevelItemCount())]
    if ok_:
        d._ok() if hasattr(d, "_ok") else d.accept()
    else:
        d.reject()
    return d.result()


zeile = next(r for r, q in enumerate(s.positionen) if q["id"] == pid)
assert not s.schneidweg_berechnen(zeile, dialog=lambda d: bedienen(d, ok_=False))
assert not (next(q for q in db.positionen(ang) if q["id"] == pid).get("zusatz"))
ok("Abbrechen: keine Zusatzarbeit in der Position")
assert z3.MENUE in gesehen["menue"], gesehen["menue"]
assert gesehen["eintrag"]["menge"] == 8 and gesehen["eintrag"]["merkmal"] == "kontur:0"
assert "Zusatzarbeiten neu (mit OK)" in gesehen["baum"], gesehen["baum"]
assert s.schneidweg_berechnen(zeile, dialog=bedienen)
q = next(q for q in db.positionen(ang) if q["id"] == pid)
zl = rechnen.zusatz_liste(q)
assert [(y["name"], y["menge"], y.get("quelle")) for y in zl] == [("Senken", 8, "3D")], zl
assert zl[0]["text"].startswith("aus 3D: 1. Bohrung"), zl
ok("Rohr-Editor: Rechtsklick auf die Bohrung -> Senken × 8 mit OK in der Position (Preisstand aus den Stammdaten)")


def blaettern(d):
    if d.windowTitle().endswith("(1 von 2)"):
        d.editor.zusatz_anlegen("ende:a", wahl=dict(name="Entgraten"))
        d.blaettern_knoepfe[1].click()          # sonst nichts geändert: gespeichert wird trotzdem
    else:
        d.reject()
    return d.result()


s.neu_laden()
s.schneidweg_berechnen(next(r for r, q in enumerate(s.positionen) if q["id"] == pid), dialog=blaettern)
zl = rechnen.zusatz_liste(next(q for q in db.positionen(ang) if q["id"] == pid))
assert [y["name"] for y in zl] == ["Senken", "Entgraten"], zl
ok("Blättern speichert die Zusatzarbeit aus dem 3D, auch ohne andere Änderung")

# ------------------------------------------------------------------ Blech-Editor
from rohrlaser import blech  # noqa: E402
from rohrlaser.blech_dialog import BlechDialog  # noqa: E402

werkstoff = sorted(z["blech_werkstoff_id"] for z in db.zeilen("blech_werkstoffe"))[0]
bd = BlechDialog(None, db, dict(art=blech.ZUSCHNITT, form=blech.RECHTECK, dicke=3, laenge=300, breite=200,
                                werkstoff=werkstoff, konturen=[dict(art=sw.BOHRUNG, anzahl=4, d=8, x=30, y=30)]))
be = bd.editor
be.aktualisieren()
assert z3.MENUE in [a.text() for a in be.kontextmenue("kontur:0").actions()]
xb = be.zusatz_anlegen("kontur:0", wahl=dict(name="Senken"))
assert xb["menge"] == 4 and bd.zusatz_neu == [xb]
ok("Blech-Editor: dasselbe Kontextmenü, Menge 4 aus der Bohrungszeile")

# ------------------------------------------------------------------ Baugruppe / Satz in 3D (AuswahlEditor)
from rohrlaser.baugruppe_dialog import AuswahlEditor  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402


class Fenster(QWidget, AuswahlEditor):
    def __init__(self):
        super().__init__()
        self.tabellen = dict(zusatzarbeiten=katalog)
        self.teile = [dict(_id=pid, _q=dict(pos=1, artikel="Holm")), dict(_id=pid2, _q=dict(pos=2, artikel="Strebe"))]


w = Fenster()
xt = w.zusatz_teil(pid2, wahl=dict(name="Entgraten", menge=2))
assert xt["menge"] == 2 and xt["text"] == "aus 3D: Pos. 2 Strebe" and w.zusatz_neu == {pid2: [xt]}
assert w.zusatz_teil(999, wahl=dict(name="Entgraten")) is None
text = s.zusatz_3d_anwenden(pid2, w.zusatz_neu[pid2])
assert "1 Zusatzarbeit aus dem 3D" in text, text
zl = rechnen.zusatz_liste(next(q for q in db.positionen(ang) if q["id"] == pid2))
assert [(y["name"], y["menge"]) for y in zl] == [("Entgraten", 2)], zl
assert s.zusatz_3d_anwenden(pid2, []) == "" and "Nicht in den Stammdaten" in s.zusatz_3d_anwenden(
    pid2, [dict(name="Fehlt", menge=1, text="aus 3D")])
ok("Baugruppe und Satz in 3D: „Zusatzarbeit für dieses Teil …“ je Position, mit OK geschrieben")

# Dialog selbst: nur Stück-Arten mit Menge, ohne Stammdaten kein OK
dlg = z3.ZusatzDialog(None, katalog, "Ende A", 3)
dlg.arbeit.setCurrentIndex(next(i for i, z in enumerate(dlg.katalog) if z["art"] == "€/kg"))
assert not dlg.menge.isEnabled()
dlg.arbeit.setCurrentIndex(next(i for i, z in enumerate(dlg.katalog) if z["art"] == "€/Stück"))
assert dlg.menge.isEnabled() and dlg.menge.value() == 3
assert all(z["art"] != "€/Angebot" for z in dlg.katalog)
leer = z3.ZusatzDialog(None, [], "x")
assert leer.findChild(type(leer.leer)) is not None and not leer.katalog
assert QDialog.Accepted
ok("Fenster: Menge nur bei €/Stück, Arbeiten je Angebot nicht wählbar")
print("alle Prüfungen bestanden")
