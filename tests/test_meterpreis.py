"""Prüft den Materialpreis je m im Angebot: berechneter Meterpreis (Preise, Oberflächen-Aufpreis, Stangenlänge,
festgeschriebene Preisbasis), Anzeige in der Positionstabelle (grau berechnet, fett von Hand), Überschreiben
günstiger/teurer, Wirkung auf die Kalkulation und Zurücksetzen.

Aufruf: python tests/test_meterpreis.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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
from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(t):
    print("OK:", t)


def nah(a, b, tol=1e-9):
    return a is not None and abs(a - b) <= tol


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
a = db.angebot_neu(dict(kunde="Test", skonto=0, stange=6000))
for pos, art, ob, st in ((10, "roh", None, None), (20, "K240", "K240", None), (30, "roh2", None, None),
                         (40, "lang", None, 3000)):
    db.position_neu(a, dict(pos=pos, artikel=art, profil_id="RR 42,4x2,0", werkstoff_id="1.4301", oberflaeche=ob,
                            laenge=1000, stueck=3, schneidweg=300, einstiche=2, stange=st))
k, tab = db.kontext(), db.tabellen()
kopf = db.angebot(a)
pos = db.positionen(a)

# 1) Berechnet: Preise RR 42,4x2,0 + 1.4301 = 62 € je 6-m-Stange, K240 dazu 2,20 €/m
mp = [rechnen.meterpreis(p, kopf, pos, k, tab) for p in pos]
assert nah(mp[0][0], 62 / 6) and nah(mp[0][1], 62 / 6) and mp[0][2] is None, mp[0]
assert nah(mp[1][0], 62 / 6 + 2.20), mp[1]
assert nah(mp[3][0], 62 / 6), mp[3]      # €/Stange anteilig auf die Länge der Position umgerechnet
assert rechnen.meterpreis(dict(pos[0], profil_id=None), kopf, pos, k, tab) == (None, None, None)
ok("berechneter Meterpreis aus Preisen, mit Oberflächen-Aufpreis, je Stangenlänge")

# 2) Oberfläche: Spalte immer sichtbar, grau berechnet, fett von Hand, rücksetzbar
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, stumm=True)
s = fenster.angebot_oeffnen(a)
m = s.pos_modell
c = next(i for i, (art, f) in enumerate(m.spalten) if art == "feld" and f.name == "preis_m")
assert not s.pos_ansicht.isColumnHidden(c), "Meterpreis muss ohne Eintrag sichtbar sein"
assert m.headerData(c, Qt.Horizontal) == "Materialpreis [€/m]"
assert m.data(m.index(0, c)) == "10,33" and m.data(m.index(1, c)) == "12,53"
assert m.data(m.index(0, c), Qt.ForegroundRole).color().name() == "#5f6b7a"
assert "Doppelklick" in m.data(m.index(0, c), Qt.ToolTipRole)
m.setData(m.index(0, c), m.data(m.index(0, c), Qt.EditRole))
assert s.positionen[0]["preis_m"] is None, "unverändert bestätigt = bleibt berechnet"
s.optimieren()
material_vorher = s._rechnung()[1]["material"]
kosten_roh = sum(z["material_position"] for z in s._rechnung()[0][:1] + s._rechnung()[0][2:3])
assert m.setData(m.index(0, c), "8,50")              # günstiger
assert s.positionen[0]["preis_m"] == 8.5
s.neu_laden()
m = s.pos_modell
assert m.data(m.index(0, c)) == "8,50" and m.data(m.index(0, c), Qt.FontRole).bold()
assert m.status[0] == "HINWEIS: Meterpreis manuell"
# gleiche Stangengruppe (Pos. 30): es gilt der Preis von Hand, kursiv mit Hinweis
assert m.data(m.index(2, c)) == "8,50" and m.data(m.index(2, c), Qt.FontRole).italic()
assert "andere" in m.data(m.index(2, c), Qt.ToolTipRole) and s.positionen[2]["preis_m"] is None
assert m.data(m.index(1, c)) == "12,53"               # andere Oberfläche = andere Gruppe
s.optimieren()
zeilen, summen = s._rechnung()
kosten_neu = zeilen[0]["material_position"] + zeilen[2]["material_position"]
# 62 € je Stange (ohne Mehrlänge) gegen 8,50 €/m für 6,05 m (Händler +50 mm je 6-m-Stange)
assert nah(kosten_neu, kosten_roh * 8.5 * 6.05 / 62, 1e-6), (kosten_neu, kosten_roh)
assert summen["material"] < material_vorher
assert m.setData(m.index(0, c), "15")                 # teurer
s.optimieren()
assert s._rechnung()[1]["material"] > material_vorher
assert m.setData(m.index(0, c), "")                   # leeren = wieder berechnet
s.neu_laden()
s.optimieren()
assert s.positionen[0]["preis_m"] is None and nah(s._rechnung()[1]["material"], material_vorher, 1e-6)
assert s.pos_modell.status[0] == "OK"
ok("Anzeige grau/fett/kursiv, günstiger und teurer überschreiben, Kalkulation rechnet mit, leeren setzt zurück")

# 3) Festgeschriebene Preisbasis: berechneter Meterpreis bleibt beim Stand des Angebots
zid = next(z["id"] for z in db.zeilen("preise") if z["profil_id"] == "RR 42,4x2,0" and z["werkstoff_id"] == "1.4301")
kopf = db.angebot(a)
db.preisbasis_speichern(a, rechnen.preisbasis_aus(kopf, pos, k, tab))
db.aendern("preise", zid, "preis", 90.0)
kopf = db.angebot(a)
k2, tab2 = rechnen.preisbasis_anwenden(kopf, db.kontext(), db.tabellen())
assert nah(rechnen.meterpreis(pos[0], kopf, pos, k2, tab2)[0], 62 / 6)
assert nah(rechnen.meterpreis(pos[0], kopf, pos, db.kontext(), db.tabellen())[0], 15.0)
ok("festgeschriebene Preisbasis gilt auch für den angezeigten Meterpreis")

fenster.close()
db.schliessen()
print("OK: Meterpreis im Angebot")
