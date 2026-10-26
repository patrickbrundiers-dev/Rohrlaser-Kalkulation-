"""Prüft „Zusatzarbeiten unter Position“ (unterzeilen.py, Patrick 26.10.2026): Unterzeilen je Arbeitsschritt in der
Reihenfolge der Werkstatt, ohne Laserzeit-Zusatzarbeiten, mit Programmieren, Gewinde und Zukaufteilen; Werte gleich der
Kalkulation; Häkchen (Vorgabe an) in Positionsliste und kompakter Kalkulation gemeinsam; Zeile bleibt die Position.

Aufruf: python tests/test_unterzeilen.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import json
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import unterzeilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ Reihenfolge und Inhalt (ohne Oberfläche)
KATALOG = [dict(name="Pulverbeschichten", kategorie="Oberfläche"), dict(name="Senken", kategorie="Nachbearbeitung"),
           dict(name="Schweißen", kategorie="Montage", art="€/h"), dict(name="Gravur extra", kategorie="Laser"),
           dict(name="Prüfprotokoll", kategorie="Prüfung"), dict(name="Etwas")]
p = dict(stueck=10, gewinde="2xM8", zusatz=json.dumps([dict(name=n, menge=36) if n == "Schweißen" else {"name": n} for n in (
    "Pulverbeschichten", "Gravur extra", "Prüfprotokoll", "Senken", "Schweißen", "Etwas")]),
    zukauf=json.dumps([dict(menge=4, stand=dict(bezeichnung="Mutter M6", einheit="Stück"))]))
zus = [dict(name="Pulverbeschichten", art="€/m²", einheit="m²", menge=0.5, preis=18.0, teil=9.0, betrag=9.0,
            fremd=True, text="RAL 7016"),
       dict(name="Gravur extra", art="s/Stück", einheit="Stk", menge=1, preis=20, teil=0.0, betrag=0.0, zeit=20.0),
       dict(name="Prüfprotokoll", art="€/Angebot", einheit="Angebot", menge=1, preis=50, teil=5.0, betrag=0.0,
            pauschal=50.0),
       dict(name="Senken", art="€/Stück", einheit="Stk", menge=4, preis=0.4, teil=1.6, betrag=1.6),
       dict(name="Schweißen", art="€/h", einheit="s", menge=36, preis=75.0, teil=0.75, betrag=0.75, arbeit_s=36),
       dict(name="Etwas", art="€/Stück", einheit="Stk", menge=1, preis=2.0, teil=3.0, betrag=2.0)]
z = dict(stueck=10, prog_min=6.0, programmierung_anteil=0.6, gewinde_teil=2.2, zusatzarbeiten=zus,
         zukauf_einzeln=[dict(vk=2.4, fehler="")])
zeilen = unterzeilen.schritte(p, z, KATALOG)
namen = [t.split(unterzeilen.TRENNER)[0] for t, _ in zeilen]
assert namen == ["Programmieren", "Gewinde", "Senken", "Schweißen", "Mutter M6", "Pulverbeschichten RAL 7016",
                 "Prüfprotokoll", "Etwas"], namen
assert not any(w for _, w in zeilen) and "Gravur extra" not in namen
t = dict(zip(namen, (x for x, _ in zeilen)))
assert "6,0 min" in t["Programmieren"] and "60,00 €/h" in t["Programmieren"] and "6,00 € Pos." in t["Programmieren"]
assert "2xM8" in t["Gewinde"] and "22,00 € Pos." in t["Gewinde"]
assert "0,5 m²" in t["Pulverbeschichten RAL 7016"] and "Fremdleistung" in t["Pulverbeschichten RAL 7016"]
assert "4 Stk" in t["Senken"] and "16,00 € Pos." in t["Senken"] and "eigen" in t["Senken"]
assert "36 s/Teil" in t["Schweißen"] and "75,00 €/h" in t["Schweißen"]
assert "pauschal 50,00 €" in t["Prüfprotokoll"] and "umgelegt 5,00 €/Teil" in t["Prüfprotokoll"]
assert "inkl. Mindestbetrag" in t["Etwas"]
assert "4 St/Teil" in t["Mutter M6"] and "0,24 €/Teil" in t["Mutter M6"] and "Zukauf" in t["Mutter M6"]
ok("Reihenfolge Programmieren, Gewinde, Nachbearbeitung, Montage (Schweißen, Zukauf), Oberfläche, Prüfung, Sonstiges; "
   "Gravur (Laserzeit) nicht")
# Zukaufteil-Position: der Artikel ist die Zeile selbst; unbekannte Zusatzarbeit als Warnung; ohne Rechnung nichts
assert not [x for x in unterzeilen.schritte(p, dict(z, zukaufteil=True), KATALOG) if "Mutter" in x[0]]
fremd = dict(p, zusatz=json.dumps([{"name": "Gibt es nicht"}]))
w = unterzeilen.schritte(fremd, dict(z, zusatzarbeiten=[]), KATALOG)
assert any(warn and "Gibt es nicht" in x and "unbekannt" in x for x, warn in w)
assert unterzeilen.schritte(p, None, KATALOG) == []
ok("Zukaufteil-Position ohne eigene Zukauf-Unterzeile, unbekannte Zusatzarbeit rot, ohne Rechnung keine Unterzeilen")

# ------------------------------------------------------------------ Angebotsseite
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
fenster.resize(1600, 1000)
fenster.show()
a = db.angebot_neu(dict(kunde="Test", kundennr="4711"))
for i in range(3):
    db.position_neu(a, dict(pos=10 * (i + 1), artikel=f"T{i}", profil_id="QR 40x40x3", werkstoff_id="S235-10219",
                            laenge=800 + 100 * i, stueck=4, schneidweg=320, einstiche=2))
s = fenster.angebot_oeffnen(a)
ids = [x["id"] for x in s.positionen]
db.position_aendern(ids[0], "zusatz", json.dumps([dict(name="Feuerverzinken"), dict(name="Entgraten"),
                                                  dict(name="Gravur extra", text="Logo")]))
db.position_aendern(ids[0], "gewinde", "2xM8")
s.neu_laden()
assert s.optimieren()
QApplication.processEvents()
assert s.unter_haken_pos.isChecked() and s.unter_haken_kalk.isChecked() and s.pos_unter.an
u0 = [x for x, _ in s.unter_texte[0]]
assert [x.split(unterzeilen.TRENNER)[0] for x in u0] == ["Programmieren", "Gewinde", "Entgraten", "Feuerverzinken"]
assert [x.split(unterzeilen.TRENNER)[0] for x, _ in s.unter_texte[1]] == ["Programmieren"]
kz, _ = s._rechnung()
summe = sum(e["teil"] for e in kz[0]["zusatzarbeiten"] if e["art"] != "s/Stück")
gezeigt = sum(float(x.split(unterzeilen.TRENNER)[[i for i, t in enumerate(x.split(unterzeilen.TRENNER))
                                                     if t.endswith("€/Teil")][0]].split()[0].replace(",", "."))
              for x in u0[2:])
assert abs(summe - gezeigt) < 0.011, (summe, gezeigt)
ok("Positionsliste: Häkchen an (Vorgabe), Unterzeilen der Position in Werkstatt-Reihenfolge, € je Teil wie Kalkulation")

v = s.pos_ansicht
v.auto_groesse.anpassen()
QApplication.processEvents()
std = v.verticalHeader().defaultSectionSize()
h0 = v.rowHeight(0)
assert h0 >= std + 4 * s.pos_unter.zeile_h, (h0, std)
assert v.rowHeight(1) >= std + s.pos_unter.zeile_h
v.grab()                    # zeichnen ohne Fehler
# Klick in die Unterzeilen trifft die Position (Zeile bleibt die Position), Doppelklick öffnet ihre Zusatzarbeiten
y = v.rowViewportPosition(0) + h0 - 3
assert v.rowAt(y) == 0 and s.pos_unter._zeile_bei(y) == 0 and s.pos_unter._zeile_bei(v.rowViewportPosition(0) + 3) == -1
geoeffnet = []
s.zusatzarbeiten, alt = (lambda zeilen=None, werte=None: geoeffnet.append(zeilen)), s.zusatzarbeiten
punkt = QPointF(v.columnViewportPosition(3) + 5, y)
ev = QMouseEvent(QEvent.MouseButtonDblClick, punkt, punkt, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
QApplication.sendEvent(v.viewport(), ev)
s.zusatzarbeiten = alt
assert geoeffnet == [[0]], geoeffnet
ok("Zeile höher um die Unterzeilen, Klick darin trifft die Position, Doppelklick öffnet ihre Zusatzarbeiten")

# Kompakte Kalkulation: dieselben Unterzeilen
assert s._kompakt_unter_texte(0) == s.unter_texte[s.kompakt.zeilen[0]["zeile"]]
s.kompakt_ansicht.grab()
# Häkchen aus: beide Häkchen, Einstellung gemerkt, Zeilen wieder einzeilig
s.unter_haken_kalk.setChecked(False)
assert not s.unter_haken_pos.isChecked() and not s.pos_unter.an and not s.kompakt_unter.an
assert db.einstellung(unterzeilen.EINSTELLUNG) is False
v.auto_groesse.anpassen()
assert v.rowHeight(0) < h0 and s.pos_unter.hoehe(0) == 0 and s.pos_unter._zeile_bei(y) == -1
s.unter_haken_pos.setChecked(True)
assert s.unter_haken_kalk.isChecked() and db.einstellung(unterzeilen.EINSTELLUNG) is True
ok("Kompakte Kalkulation mit denselben Unterzeilen; ein Häkchen schaltet beide, Wahl wird gemerkt")

# ausgeblendete Zeile (eingeklappte Baugruppe) zeichnet keine Unterzeilen
v.setRowHidden(0, True)
v.grab()
v.setRowHidden(0, False)
ok("ausgeblendete Zeilen ohne Unterzeilen")
print("Alle Prüfungen bestanden.")
