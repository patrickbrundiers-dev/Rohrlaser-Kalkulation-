"""Prüft Spaltenbreite und Zeilenhöhe automatisch (spaltenbreite.py): Spalten passend zum Inhalt mit Höchstbreite,
nur wachsen nach dem ersten Einpassen, von Hand gezogene Spalten bleiben, lange Texte machen die Zeile höher
(höchstens drei Textzeilen), kurze Zeilen bleiben einzeilig; angewendet in Angebot, Stammdaten, Staffeln, Zeiten.

Aufruf: python tests/test_spaltenbreite.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import spaltenbreite  # noqa: E402
from rohrlaser.angebot_fenster import Liste, _tabelle  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
LANG = "Sehr langer Text mit vielen Wörtern, der nicht in eine Spalte passt " * 6

# ------------------------------------------------------------------ Grundregeln an einer einfachen Liste
liste = Liste([("Nr.", "nr", 0, 300), ("Text", "text", None, 30), ("Wert", "wert", 2, 90)])
v = _tabelle(liste, sortieren=False)
v.resize(1200, 600)
v.show()
ag = v.auto_groesse
liste.setzen([dict(nr=1, text="kurz", wert=1.5), dict(nr=2, text=LANG, wert=2.0)])
app.processEvents()
assert ag.eingepasst
assert v.columnWidth(0) < 100, v.columnWidth(0)                 # Vorgabe 300 auf Inhalt verkleinert
assert v.columnWidth(1) == spaltenbreite.MAX_BREITE             # langer Text: Höchstbreite
standard = v.verticalHeader().defaultSectionSize()
hoechst = spaltenbreite.MAX_ZEILEN * v.fontMetrics().lineSpacing() + 8
assert v.rowHeight(0) == standard, (v.rowHeight(0), standard)   # kurze Zeile bleibt einzeilig
assert standard < v.rowHeight(1) <= hoechst, (v.rowHeight(1), hoechst)
ok(f"Spalten passend zum Inhalt (Vorgabe 300 -> {v.columnWidth(0)} px), langer Text höchstens "
   f"{spaltenbreite.MAX_BREITE} px breit; Zeile mit langem Text {v.rowHeight(1)} px (höchstens {hoechst}), "
   f"kurze Zeile {standard} px")

# nach dem ersten Einpassen nur wachsen
breit = v.columnWidth(1)
liste.setzen([dict(nr=1, text="kurz", wert=1.5)])
app.processEvents()
assert v.columnWidth(1) == breit and v.rowHeight(0) == standard
liste.setzen([dict(nr=1, text="kurz", wert=123456789.25)])
app.processEvents()
assert v.columnWidth(2) > 60
ok("Nach dem ersten Füllen werden Spalten nur breiter, nie schmaler (Tabelle springt beim Tippen nicht)")

# von Hand gezogen: bleibt
spaltenbreite.AutoGroesse._maus = staticmethod(lambda: True)
v.setColumnWidth(1, 120)
spaltenbreite.AutoGroesse._maus = staticmethod(lambda: False)
assert 1 in ag.von_hand
liste.setzen([dict(nr=1, text=LANG, wert=1.5)])
app.processEvents()
assert v.columnWidth(1) == 120
v.setColumnHidden(0, True)
v.setColumnHidden(0, False)
assert 0 not in ag.von_hand                                    # Ein-/Ausblenden ist keine Benutzeränderung
ag.neu_einpassen()
assert v.columnWidth(1) == spaltenbreite.MAX_BREITE and not ag.von_hand
ok("Von Hand gezogene Spalte (120 px) bleibt, Ein-/Ausblenden zählt nicht; Neu einpassen setzt zurück")

# sehr viele Zeilen: einzeilig
viele = [dict(nr=i, text=LANG, wert=1.0) for i in range(spaltenbreite.MAX_ANZAHL + 1)]
liste.setzen(viele)
app.processEvents()
assert v.rowHeight(5) == standard
ok(f"Über {spaltenbreite.MAX_ANZAHL} Zeilen bleiben die Zeilen einzeilig (Geschwindigkeit)")

# ------------------------------------------------------------------ im Programm
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
fenster.resize(1366, 768)
fenster.show()
a = db.angebot_neu(dict(kunde="Test", kundennr="4711"))
db.position_neu(a, dict(pos=10, artikel="T1", bezeichnung="Halter", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                        laenge=800, stueck=4, schneidweg=320, einstiche=2))
db.position_neu(a, dict(pos=20, artikel="T2", bezeichnung=LANG, profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                        laenge=900, stueck=4, schneidweg=320, einstiche=2))
s = fenster.angebot_oeffnen(a)
app.processEvents()
pv = s.pos_ansicht
spalte = next(i for i in range(pv.model().columnCount()) if s.pos_modell.name(i) == "bezeichnung")
assert pv.auto_groesse.eingepasst
assert pv.columnWidth(spalte) == spaltenbreite.MAX_BREITE, pv.columnWidth(spalte)
unter = pv.unterzeilen.hoehe          # Zusatzarbeiten unter der Position (Programmieren) kommen dazu
assert pv.rowHeight(0) - unter(0) == pv.verticalHeader().defaultSectionSize() < pv.rowHeight(1) - unter(1)
assert pv.rowHeight(1) - unter(1) <= spaltenbreite.MAX_ZEILEN * pv.fontMetrics().lineSpacing() + 8
sichtbar = [c for c in range(pv.model().columnCount()) if not pv.isColumnHidden(c)]
assert all(pv.columnWidth(c) <= spaltenbreite.MAX_BREITE for c in sichtbar[:-1])   # letzte füllt den Rest
ok("Angebot: Positionen passend eingepasst, lange Bezeichnung umgebrochen (höchstens 3 Zeilen), "
   "kurze Position einzeilig, keine Spalte breiter als die Höchstbreite")
assert s.optimieren()
app.processEvents()
for name in ("kalk_ansicht", "stangen_ansicht", "zukauf_ansicht"):
    assert getattr(s, name).auto_groesse, name
assert s.zeiten_seite.ansicht.auto_groesse.max_breite == 420
assert s.st_seite.ansicht.auto_groesse
ok("Kalkulation, Schnittplan, Zukauf, Zeiten und Staffeln passen sich ebenfalls an")
stamm = [w for w in fenster.findChildren(type(pv)) if hasattr(w, "auto_groesse")]
assert len(stamm) >= 10, len(stamm)
ok(f"{len(stamm)} Tabellen im Programm mit automatischer Breite und Höhe")
print("Alle Prüfungen bestanden.")
