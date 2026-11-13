"""Spalte „Sicherheit“ (A3, Plan Phase 3 und 4, Patrick 13.11.2026 „Alles einbauen“; Folge von CALC-028):

- herkunft.position_stufe: unsicher vor prüfen vor sicher (ab 0,5 % des Preises), Text „unsicher 30 %“, leer = sicher
- Positionsliste: Spalte gleich hinter dem Status, Tooltip mit allen Bausteinen (Quelle, Sicherheit, Grund);
  optional: erscheint, sobald eine Position nicht ganz sicher ist
- Teile-Editor: Spalte Sicherheit je Merkmal (STEP und von Hand = sicher, Vorgabe/geändert = prüfen)

Aufruf: python tests/test_sicherheit_spalte.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import herkunft as hk, schneidweg as sw, teile_editor as te  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK    ", t)


def b(eur, s, name="X"):
    return dict(baustein=name, eur=eur, quelle=hk.STAMMDATEN, sicherheit=s, grund="Test")


st = hk.position_stufe([b(70, hk.SICHER), b(30, hk.UNSICHER, "Laser: Leerwege")])
assert st["stufe"] == hk.UNSICHER and st["text"] == "unsicher 30 %" and abs(st["unsicher"] - 0.3) < 1e-9, st
assert "Laser: Leerwege: 30,00 € – Stammdaten, unsicher (Test)" in st["tipp"], st["tipp"]
assert hk.position_stufe([b(88, hk.SICHER), b(12, hk.PRUEFEN)])["text"] == "prüfen 12 %"
assert hk.position_stufe([b(99.9, hk.SICHER), b(0.1, hk.UNSICHER)])["text"] == ""        # unter 0,5 %: sicher
assert hk.position_stufe([])["stufe"] is None and hk.position_stufe([])["text"] == ""
assert [hk.merkmal_sicherheit(h) for h in (te.STEP, te.MANUELL, te.GEAENDERT, te.VORGABE, "?")] == \
    [hk.SICHER, hk.SICHER, hk.PRUEFEN, hk.PRUEFEN, hk.PRUEFEN]
ok("Stufe je Position: unsicher vor prüfen (ab 0,5 %), leer = alles sicher; Merkmal: STEP/von Hand sicher")

# ------------------------------------------------------------------ Positionsliste
app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "r.db")
k = db.kontext()
m = next(iter(k.maschinen))
pid = next(p for p, w in k.profile.items() if w.get("form") == "Rundrohr")
ang = db.angebot_neu(dict(kunde="Test", maschine=m))
db.position_neu(ang, dict(pos=10, profil_id=pid, werkstoff_id="S235-10219", laenge=800, stueck=30, schneidweg=400,
                          einstiche=2))
db.position_neu(ang, dict(pos=20, profil_id=pid, werkstoff_id="S235-10219", laenge=500, stueck=10, schneidweg=300,
                          einstiche=1, zeit_manuell=12.0, preis_m=4.5))
f = Hauptfenster(db, stumm=True)
s = f.angebot_oeffnen(ang)
mo = s.pos_modell
c = next(i for i, (a, _) in enumerate(mo.spalten) if a == "sicherheit")
assert mo.spalten[c - 1][0] == "status" and mo.headerData(c, Qt.Horizontal) == "Sicherheit"
assert len(mo.sicherheit) == len(s.positionen) == 2
u = s.herkunft_uebersicht()
for r, p in enumerate(s.positionen):
    erwartet = hk.position_stufe(next(x["bausteine"] for x in u["positionen"] if x["pos"] == p["pos"]))
    assert mo.sicherheit[r]["text"] == erwartet["text"], (mo.sicherheit[r], erwartet)
    tipp = mo.data(mo.index(r, c), Qt.ItemDataRole.ToolTipRole)
    assert tipp.startswith("Herkunft und Sicherheit") and "Laser: " in tipp, tipp
texte = [mo.data(mo.index(r, c)) for r in range(2)]
sichtbar = not s.pos_ansicht.isColumnHidden(c)
assert sichtbar == any(texte), (texte, sichtbar)
ok(f"Positionsliste: Spalte Sicherheit hinter dem Status ({texte}), Tooltip mit Bausteinen, sichtbar nur mit Werten")

# ------------------------------------------------------------------ Teile-Editor
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402

technik = dict(quelle=sw.QUELLE, a=dict(winkel=30, achse="über Höhe", gemessen=70.5), b=dict(winkel=0),
               konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100, seite="oben", gemessen=31.4)])
p = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500, stueck=10, technik=json.dumps(technik))
d = SchneidwegDialog(None, p, k.profile["QR 40x40x3"], dict(maschine="T11", stange=6000), k, db.tabellen(), db)
ed = d.editor
assert ed.baum.headerItem().text(4) == "●" and "Sicherheit" in ed.baum.headerItem().toolTip(4)
spalte = {}
for i in range(ed.baum.topLevelItemCount()):
    g = ed.baum.topLevelItem(i)
    for j in range(g.childCount()):
        it = g.child(j)
        if it.data(0, Qt.UserRole):
            spalte[it.data(0, Qt.UserRole)] = (it.text(1), it.data(4, Qt.UserRole))
            assert it.toolTip(4) == f"Sicherheit: {it.data(4, Qt.UserRole)}"
assert spalte["ende:a"] == (te.STEP, hk.SICHER) and spalte["ende:b"] == (te.VORGABE, hk.PRUEFEN), spalte
assert spalte["kontur:0"] == (te.STEP, hk.SICHER), spalte
ok("Teile-Editor: Sicherheit je Merkmal (STEP sicher, Vorgabe prüfen)")
print("alle Prüfungen bestanden")
