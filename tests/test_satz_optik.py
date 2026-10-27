"""Prüft „Sätze abheben“ (satzgruppen.py, Patrick 27.10.2026): Positionen eines Satzes stehen zusammen, sind je Satz
getönt (Blau/Violett abwechselnd, Hell und Dunkel), Satz und Stück je Satz stehen gleich hinter Pos., die erste
Position zeigt Name und Anzahl Sätze, der Zeilenkopf eine Klammer ▾ │ └, Klick auf ▾ klappt den Satz zu; die
Kalkulation (kompakt und alle Spalten) hat die Spalte Satz und dieselbe Tönung. Schweißbaugruppen bleiben außen vor.

Aufruf: python tests/test_satz_optik.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import satzgruppen, stil  # noqa: E402
from rohrlaser.angebot_fenster import SICHTBAR  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ ohne Oberfläche
pos = [dict(satz="A", je_satz=2, stueck=8), dict(), dict(satz="B", je_satz=1, stueck=3), dict(satz=" A ", je_satz=1,
                                                                                               stueck=4), dict(satz="B")]
g = satzgruppen.saetze(pos)
assert g == {"A": [0, 3], "B": [2, 4]}, g
assert satzgruppen.saetze(pos, aus={3}) == {"A": [0], "B": [2, 4]}
assert satzgruppen.ordnen(list(range(5)), g) == [0, 3, 1, 2, 4]
i = satzgruppen.info(pos, g)
assert i[0]["ton"] == 0 and i[2]["ton"] == 1 and i[0]["erste"] and i[3]["letzte"] and i[0]["saetze"] == 4
assert 1 not in i
assert satzgruppen.kopf_texte(g) == {0: "▾ 1", 3: "└ 4", 2: "▾ 3", 4: "└ 5"}
assert satzgruppen.kopf_texte(g, {"A"})[0] == "▸ 1"
assert satzgruppen.kopf_texte({"C": [1, 2, 3]})[2] == "│ 3"
assert satzgruppen.zelltext(i[0]) == "▣ A · 4 Sätze" and satzgruppen.zelltext(i[3]) == "A"
assert satzgruppen.zelltext(i[0], zu=True) == "▣ A · 4 Sätze · 2 Positionen"
assert satzgruppen.zelltext(dict(i[2], saetze=1)) == "▣ B · 1 Satz"
assert satzgruppen.anzahl_saetze(dict(satz="C", stueck=3)) == 3        # Stück je Satz leer = 1 wie rechnen
m = satzgruppen.zeilen_markieren(pos, [dict(pos=1), None, dict(pos=3), dict(pos=4), dict(pos=5)])
assert m[1] is None and m[0]["satz"] == "A" and m[0]["satz_ton"] == 0 and m[2]["satz_ton"] == 1 and m[3]["satz_ton"] == 0
ok("Gruppen je Satzname (ohne Baugruppen), Reihenfolge zusammen, Tönung abwechselnd, Klammer ▾ │ └, Zelltext")

assert SICHTBAR[:3] == ["pos", "satz", "je_satz"]
for thema in ("Hell", "Dunkel", "Hoher Kontrast"):
    for text, flaeche in zip(satzgruppen.TEXTE, satzgruppen.FLAECHEN):
        vorne, hinten = stil.umsetzen(text, thema), stil.umsetzen(flaeche, thema)
        assert stil.kontrast(vorne, hinten) >= 4.5, (thema, vorne, hinten)
        assert stil.kontrast(stil.umsetzen(stil.TEXT, thema), hinten) >= 4.5, (thema, hinten)
assert stil.umsetzen(satzgruppen.FLAECHEN[0], "Dunkel") != satzgruppen.FLAECHEN[0]
ok("Satzname und Zeilentext lesbar (≥ 4,5 : 1) in Hell, Dunkel und Hoher Kontrast; Dunkel eigene Töne")

# ------------------------------------------------------------------ Angebotsseite
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
fenster.resize(1600, 1000)
fenster.show()
a = db.angebot_neu(dict(kunde="Test", kundennr="4711"))
for nr, satz, je in ((10, "Gestell", 2), (20, None, None), (30, "Gestell", 1), (40, "Tisch", 4), (50, "Tisch", 2)):
    w = dict(pos=nr, artikel=f"T{nr}", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=500 + nr,
             stueck=4 * (je or 1), schneidweg=320, einstiche=2)
    if satz:
        w.update(satz=satz, je_satz=je)
    db.position_neu(a, w)
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
QApplication.processEvents()
m = s.pos_modell
kopf = s.pos_ansicht.verticalHeader()
assert [kopf.logicalIndex(v) for v in range(5)] == [0, 2, 1, 3, 4]       # Satz Gestell zusammen
assert m.headerData(0, Qt.Vertical) == "▾ 1" and m.headerData(2, Qt.Vertical) == "└ 3"
assert m.headerData(1, Qt.Vertical) == "2" and m.headerData(3, Qt.Vertical) == "▾ 4"
c = next(c for c in range(m.columnCount()) if m.name(c) == "satz")
assert c <= 3, c
assert m.data(m.index(0, c)) == "▣ Gestell · 4 Sätze" and m.data(m.index(2, c)) == "Gestell"
assert m.data(m.index(0, c), Qt.ItemDataRole.FontRole).bold()
assert m.data(m.index(3, c)) == "▣ Tisch · 4 Sätze"
art = next(c for c in range(m.columnCount()) if m.name(c) == "artikel")
bg = [m.data(m.index(r, art), Qt.ItemDataRole.BackgroundRole).color().name() for r in range(5)]
assert bg[0] == bg[2] != bg[1] and bg[3] == bg[4] not in (bg[0], bg[1]), bg
assert m.data(m.index(0, c), Qt.ItemDataRole.EditRole) == "Gestell"       # bearbeiten: nur der Name
ok("Positionsliste: Satz zusammen, Spalten Satz/je Satz vorne, erste Zeile fett mit Anzahl Sätze, Tönung je Satz")

s._kopf_klick(0)
assert s.pos_ansicht.isRowHidden(2) and not s.pos_ansicht.isRowHidden(0) and not s.pos_ansicht.isRowHidden(3)
assert m.headerData(0, Qt.Vertical) == "▸ 1" and m.data(m.index(0, c)).endswith("2 Positionen")
s.neu_laden()                               # bleibt zugeklappt
assert s.pos_ansicht.isRowHidden(2)
s._kopf_klick(0)
assert not s.pos_ansicht.isRowHidden(2) and m.headerData(0, Qt.Vertical) == "▾ 1"
s.pos_ansicht.grab()
ok("Klick auf ▾ klappt den Satz zu (▸, Anzahl Positionen), bleibt nach Neuladen, Klick klappt wieder auf")

k = s.kompakt
ks = next(c for c, sp in enumerate(k.spalten) if sp[1] == "satz")
assert not s.kompakt_ansicht.isColumnHidden(ks)
r0 = next(r for r, z in enumerate(k.zeilen) if z["zeile"] == 0)
r1 = next(r for r, z in enumerate(k.zeilen) if z["zeile"] == 1)
assert k.data(k.index(r0, ks)) == "Gestell" and k.data(k.index(r0, ks), Qt.ItemDataRole.FontRole).bold()
assert k.data(k.index(r0, 0), Qt.ItemDataRole.BackgroundRole) is not None
assert k.data(k.index(r1, 0), Qt.ItemDataRole.BackgroundRole) is None
kk = s.kalk
assert kk.data(kk.index(0, next(c for c, sp in enumerate(kk.spalten) if sp[1] == "satz"))) == "Gestell"
assert kk.data(kk.index(0, 0), Qt.ItemDataRole.BackgroundRole) is not None
ok("Kalkulation kompakt und alle Spalten: Spalte Satz, Satzzeilen getönt, Einzelteile wie bisher")

# ohne Sätze: Spalte Satz der kompakten Kalkulation ausgeblendet, nichts getönt
b = db.angebot_neu(dict(kunde="Test", kundennr="4711"))
db.position_neu(b, dict(pos=10, artikel="E", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=600, stueck=2,
                        schneidweg=320, einstiche=2))
s2 = fenster.angebot_oeffnen(b)
assert s2.optimieren()
assert s2.kompakt_ansicht.isColumnHidden(ks) and not s2.pos_modell.satz
assert s2.pos_modell.headerData(0, Qt.Vertical) == "1"
ok("ohne Satz: keine Tönung, keine Klammer, Spalte Satz der kompakten Kalkulation ausgeblendet")
print("Alle Prüfungen bestanden.")
