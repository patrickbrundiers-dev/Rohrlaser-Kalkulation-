"""Stehende Maße, Messprotokoll und Fangarten (Messplan M2, Patrick 19.11.2026 „professionelles 3D-Messsystem“).

S1 Mass als Datenobjekt: altes (Punkte, Text) bleibt gültig, Wert/Art/Einheit, Kopie, als dict und zurück
S2 CSV (deutsche Zahlen, ;) und PDF-Messprotokoll
S3 Ansicht: Messung legt ein Mass mit exaktem Wert an; umbenennen, ausblenden, löschen, CSV, PDF; Netz unverändert
S4 Fenster „Maße“: Liste, Haken blendet aus, Name ändern, Löschen, CSV/PDF speichern; Rechtsklick → Maße
S5 Fangarten einzeln aus (Einstellungen fang_*), Tab wählt den nächsten Kandidaten („Andere wählen“)

Aufruf: python tests/test_masse_m2.py
"""
import copy
import csv
import io
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ansicht3d, mess_liste, mess_protokoll as mp, messen3d, rohr3d, schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

ansicht3d.renderer_setzen("Software")
TMP = Path(tempfile.mkdtemp())


def ok(t):
    print("OK    ", t)


# ------------------------------------------------------------------ S1 Mass
m = mp.Mass([(0, 0, 0), (3, 4, 0)], "Abstand 5,000 mm")
punkte, text = m
assert text == "Abstand 5,000 mm" and punkte == [(0.0, 0.0, 0.0), (3.0, 4.0, 0.0)]
assert m.art == mp.ABSTAND and abs(m.wert - 5) < 1e-12 and m.einheit == "mm" and m.sichtbar
w = mp.Mass([(1, 0, 0), (0, 0, 0), (0, 1, 0)], "Winkel 90,0°")
assert w.art == mp.WINKEL and abs(w.wert - 90) < 1e-9 and w.einheit == "°"
k = m.kopie(name="Steg", sichtbar=False)
assert k.name == "Steg" and not k.sichtbar and k[0] == m[0] and m.sichtbar
assert mp.aus_dict(k.als_dict()).als_dict() == k.als_dict()
assert mp.als_mass(([(0, 0, 0), (0, 0, 7)], "x")).wert == 7
assert mp.wert_aus_text("Abstand Fläche–Fläche 12,500 mm") == (12.5, "mm")
assert mp.wert_aus_text("Winkel Kante–Kante 45,00°") == (45.0, "°")
assert mp.wert_aus_text("≈ Abstand 1.234,500 mm") == (1234.5, "mm") and mp.wert_aus_text("nichts") is None
ok("S1 Mass: (Punkte, Text) wie bisher, Wert/Art/Einheit, Kopie, dict hin und zurück, Wert aus Text")

# ------------------------------------------------------------------ S2 CSV und PDF
text = mp.csv_text([m, w.kopie(name="Gehrung")], kopf=[("Teil", "QR 40")])
zeilen = list(csv.reader(io.StringIO(text), delimiter=";"))
assert zeilen[0] == ["Teil", "QR 40"] and zeilen[2] == mp.KOPF
assert zeilen[3][:4] == ["1", "Maß 1", "Abstand", "5,000 mm"] and zeilen[4][1:4] == ["Gehrung", "Winkel", "90,00°"]
pfad = mp.pdf_schreiben(TMP / "p.pdf", [m, mp.Mass([(0, 0, 0), (0, 0, 1)], "≈ Abstand 1,000 mm (Δx 0)")],
                        angaben=[("Teil", "Test")])
roh = Path(pfad).read_bytes()
assert roh.startswith(b"%PDF") and len(roh) > 1000
ok("S2 CSV mit Kopf und deutschen Zahlen; PDF-Messprotokoll (≈/Δ lesbar ersetzt)")

# ------------------------------------------------------------------ S3 Ansicht
QR = dict(form="Quadratrohr", a=40, b=40, wand=3, profil_id="QR 40x40x3")
netz = rohr3d.netz(dict(a={}, b={}, konturen=[dict(art=sw.BOHRUNG, anzahl=1, d=10, x=100),
                                               dict(art=sw.BOHRUNG, anzahl=1, d=8, x=150)]), QR, 300)
roh_netz = copy.deepcopy(netz)
a = ansicht3d.Ansicht3D()
a.resize(900, 500)
a.setzen(netz)
a.show()
app.processEvents()
geo = a.geometrie()
mitten = sorted((k["m"] for k in geo.kreise if k["d"] < 12 and k["m"][1] > 0), key=lambda q: q[2])
assert len(mitten) == 2
a.messen_setzen(True)
bild = a.bildpunkt()
for q in mitten:
    px, py, _ = bild(q)
    a._messen_klick(bild, px, py)
assert len(a.masse_fest) == 1
mass = a.masse_fest[0]
assert isinstance(mass, mp.Mass) and abs(mass.wert - 50) < 1e-9 and mass.arten == [messen3d.KREISMITTE] * 2, mass
assert any(t == "Maße …" for t, *_ in a.mass_aktionen())
a.mass_aendern(0, name="Lochabstand")
a.mass_aendern(0, sichtbar=False)
assert a.masse_fest[0].name == "Lochabstand" and not a.masse_fest[0].sichtbar
a.grab()                                    # ausgeblendetes Maß wird übersprungen, kein Fehler
a.masse_fest.append(([(0, 0, 0), (0, 0, 10)], "alt"))       # altes Tupel wird in der Liste umgewandelt
assert all(isinstance(x, mp.Mass) for x in a.masse_liste()) and len(a.masse_fest) == 2
assert "Lochabstand" in a.masse_klartext()
a.masse_csv(TMP / "m.csv", [("Teil", "QR")])
assert "Lochabstand" in (TMP / "m.csv").read_text(encoding="utf-8-sig")
a.masse_pdf(TMP / "m.pdf")
assert (TMP / "m.pdf").read_bytes().startswith(b"%PDF")
a.mass_entfernen([1])
assert len(a.masse_fest) == 1 and a.masse_fest[0].name == "Lochabstand"
assert netz == roh_netz
ok("S3 Messen legt ein Mass an (exakt 50,000), umbenennen, ausblenden, alte Einträge, CSV, PDF, löschen; Netz gleich")

# ------------------------------------------------------------------ S4 Fenster Maße und Rechtsklick
a.mass_aendern(0, sichtbar=True)
d = mess_liste.MessListe(a)
assert d.tabelle.rowCount() == 1 and d.tabelle.item(0, 1).text() == "Lochabstand"
assert d.tabelle.item(0, 3).text() == "50,000 mm"
d.tabelle.item(0, 5).setCheckState(Qt.Unchecked)
assert not a.masse_fest[0].sichtbar
d.tabelle.item(0, 1).setText("Steg Bohrungen")
assert a.masse_fest[0].name == "Steg Bohrungen"
d.csv(str(TMP / "d.csv"))
d.pdf(str(TMP / "d.pdf"))
assert (TMP / "d.csv").exists() and (TMP / "d.pdf").exists()
d.tabelle.selectRow(0)
d.loeschen()
assert a.masse_fest == [] and d.tabelle.rowCount() == 0 and not d.knoepfe["csv"].isEnabled()
d.close()
menue = a.standard_menue(zeigen=False)
untermenue = next(x.menu() for x in menue.actions() if x.text() == "Maße")
texte = [x.text() for x in untermenue.actions()]
assert texte[0].startswith("Maße verwalten") and "Alle kopieren" in texte and "Alle löschen" in texte
ok("S4 Fenster Maße: Liste, Haken blendet aus, Name ändern, CSV/PDF, Löschen; Rechtsklick → Maße")

# ------------------------------------------------------------------ S5 Fangarten und Tab
db = Datenbank(TMP / "rohrlaser.db")
assert set(messen3d.fang_erlaubt(None)) == set(messen3d.FANGARTEN) == set(messen3d.fang_erlaubt(db))
from rohrlaser import teilen  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNG  # noqa: E402

assert set(messen3d.FANG_EINSTELLUNG.values()) <= teilen.LOKAL and set(messen3d.FANG_EINSTELLUNG.values()) <= set(EINSTELLUNG)
px, py, _ = bild(mitten[0])
kand = geo.fangen(bild, px, py, alle=True)
assert kand[0]["art"] == messen3d.KREISMITTE and len(kand) >= 1
alt_speicher = ansicht3d._speicher
ansicht3d._speicher = db
db.einstellung_setzen("fang_kreismitte", "nein")
assert messen3d.KREISMITTE not in messen3d.fang_erlaubt(db)
t = a._fang_wahl(bild, px, py, neu=True)
assert t is None or t["art"] != messen3d.KREISMITTE
db.einstellung_setzen("fang_kreismitte", "ja")
# Tab: an einer Ecke liegen Ecke und Kantenmitte/Linie nah beieinander -> mehrere Kandidaten
a.messen_setzen(True)
ecke = geo.ecken[0]
ex, ey, _ = bild(ecke)
a._fang_nr = 0
erst = a._fang_wahl(bild, ex, ey, mit_flaeche=False, neu=True)
n = len(a._fang_kand)
a.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier))
assert a._fang_nr == 1
if n > 1:
    assert a._schwebe is not None and (a._schwebe["art"], a._schwebe["punkt"]) != (erst["art"], erst["punkt"])
assert a.focusNextPrevChild(True) is False          # beim Messen gehört Tab dem Fangen
ansicht3d._speicher = alt_speicher
assert netz == roh_netz
ok(f"S5 Fangarten einzeln aus (Kreismitte aus -> andere Fangart), Tab schaltet weiter ({n} Kandidaten an der Ecke)")
print("Alle Prüfungen bestanden.")
