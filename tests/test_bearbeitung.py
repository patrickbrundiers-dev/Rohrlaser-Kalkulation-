"""Bearbeitungsliste je Position (Plan X1, Patrick 12.11.2026 „Alle Empfehlungen (X1–X8)“).

- Rohr-Editor: Merkmalsbaum mit Spalten Zeit [s] und Laser [€] je Ende und Innenkontur, Gruppe „Zeiten ohne
  Merkmal“ (Ecken, Nebenzeit …) mit der Summe = Laserzeit brutto je Teil des Editors (Kachel Schneidzeit)
- Bohrung: Zeit = 60 × Schnittlänge / Vorschub ihrer Klasse + Einstiche × (Einstechzeit + Zeit je Kontur)
- Position ohne Konturliste: Zeilen je Klasse aus dem Schneidweg; Schneidzeit von Hand ersetzt alle Zeilen
Die Summenprobe gegen die Kalkulation (Laserzeit netto, Laser schneiden) steht in test_referenz_kalkulation.py.

Aufruf: python tests/test_bearbeitung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import bearbeitung, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.schneidweg_dialog import SchneidwegDialog  # noqa: E402


def ok(t):
    print("OK    ", t)


def zahl(text):
    return float(str(text).replace(".", "").replace(",", "."))


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
a = db.angebot_neu(dict(kunde="Test", kundennr="4711", maschine="T11"))
db.position_neu(a, dict(pos=10, artikel="B1", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
                        stueck=10))
s = fenster.angebot_oeffnen(a)
p = s.positionen[0]
d = SchneidwegDialog(s, p, s.k.profile["QR 40x40x3"], s.kopf, s.k, s.tabellen)
d.zeile_neu(dict(art="Bohrung", anzahl=4, d=8, x=200, seite=0))
d.zeile_neu(dict(art="Langloch", anzahl=1, l=40, b=12, x=600, seite=0))
d.rechnen()
r = d.editor
r.aktualisieren()
b = r.baum
assert b.headerItem().text(2) == "Zeit [s]" and b.headerItem().text(3) == "Laser [€]"
werte, gruppen = {}, {}
for i in range(b.topLevelItemCount()):
    g = b.topLevelItem(i)
    gruppen[g.text(0)] = g
    for k in range(g.childCount()):
        it = g.child(k)
        if it.text(2) and g.text(0) != "Zeiten ohne Merkmal":
            werte[it.data(0, 0x0100) or it.text(0)] = (zahl(it.text(2)), zahl(it.text(3)))
assert "ende:a" in werte and "ende:b" in werte and "kontur:0" in werte and "kontur:1" in werte, werte
ok("Merkmalsbaum: Zeit und Kosten je Ende und Innenkontur")
ohne = gruppen["Zeiten ohne Merkmal"]
gesamt = zahl(ohne.text(2))
zeit = d.schneidzeit()
assert abs(gesamt - zeit) < 0.01, (gesamt, zeit)
assert abs(sum(v[0] for v in werte.values()) + sum(zahl(ohne.child(k).text(2)) for k in range(ohne.childCount()))
           - zeit) < 0.05
ok(f"Summe aller Zeilen = Schneidzeit des Editors ({rechnen.zahl(zeit, 2)} s)")

# Bohrung von Hand: Vorschub ihrer Klasse aus den Schneiddaten
t = rechnen._schneidzeit_teile(dict(p, **d.ergebnis["felder"]), s.kopf, 3.0, s.tabellen, s.k)
h, i_, j, _, l = t["vorschuebe"]
schritt = next(x for x in d.ergebnis["schritte"] if "Bohrung" in x["text"])
v = dict(klein=j, mittel=i_)[schritt["klasse"]] if schritt["klasse"] != "groß" else h
erwartet = 60 * schritt["laenge"] / v + schritt["einstiche"] * (l + t["ta"])
assert abs(werte["kontur:0"][0] - erwartet) < 0.01, (werte["kontur:0"], erwartet)
ok("Bohrung: 60 × Länge / Vorschub der Klasse + Einstiche × (Einstechzeit + Zeit je Kontur)")

# ohne Konturliste: Schneidweg je Klasse und Einstiche; von Hand ersetzt alles
q = dict(p, konturen=None, technik=None, schneidweg=500.0, klein_mm=60.0, mittel_mm=0.0, einstiche=6)
zeilen = bearbeitung.schritte_der_position(q, s.k.profile["QR 40x40x3"], (10, 50))
assert [x["klasse"] for x in zeilen] == ["groß", "klein", "groß"] and zeilen[0]["laenge"] == 440.0, zeilen
z = dict(zeit_manuell="ja", laser_netto=40.0, zeit_extra=5.0, zeit_pruefung=0.0, laser_brutto=12.0)
hand = bearbeitung.mit_kalkulation([dict(s=99.0, eur=1.0)], z, satz=150.0)
assert len(hand) == 2 and hand[0]["s"] == 35.0 and bearbeitung.summe(hand)[0] == 40.0, hand
ok("ohne Konturliste je Klasse; Schneidzeit von Hand ersetzt die berechneten Zeilen")
# Blech: Außenkontur + je Kontur, Summe = Laserzeit des Blechs; eigene Laserzeit als Abgleich
from rohrlaser import blech, schneidweg as sw  # noqa: E402
daten = db.blech_daten()
e = dict(werkstoff="S235JR", dicke=3, art=blech.ZUSCHNITT, form=blech.RECHTECK, laenge=400, breite=300, eckradius=0,
         stueck=25, konturen=[dict(art=sw.BOHRUNG, anzahl=4, d=10), dict(art=sw.LANGLOCH, anzahl=1, l=40, b=12)])
rb = blech.rechnen(e, daten["werkstoffe"], daten["laser"], daten["einst"])
bb = rb["bearbeitung"]
assert set(bb) == {"teil", "kontur:0", "kontur:1"} and abs(sum(bb.values()) - rb["zeit"]) < 1e-9, (bb, rb["zeit"])
rb = blech.rechnen(dict(e, eigene=dict(zeit=60)), daten["werkstoffe"], daten["laser"], daten["einst"])
assert abs(rb["bearbeitung"]["abgleich"] + sum(v for n, v in rb["bearbeitung"].items() if n != "abgleich") - 60) < 1e-9
ok("Blech: Zeit je Außenkontur und Kontur, eigene Laserzeit als Abgleich")
print("Bearbeitungsliste stimmt.")
