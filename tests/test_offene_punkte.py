"""UI-Modernisierung U4 (Patrick 12.11.2026): offene Punkte in der Positionsliste schnell finden.

Prüft: F7 springt zur nächsten Position mit Status ungleich OK (am Ende wieder vorn), Umschalt+F7 zur vorherigen,
die Statuszeile nennt Position und Status; ohne offene Punkte kommt eine Meldung und nichts springt; die Kürzel stehen
im Menü Bearbeiten und in der Übersicht der Tastenkürzel.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))

from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])

from rohrlaser import tastatur  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


po = Path(tempfile.mkdtemp(prefix="offene_punkte_")) / "Rohrlaser-Angebotskalkulation"
(po / "Daten").mkdir(parents=True)
db = Datenbank(po / "Daten" / "rohrlaser.db")
f = Hauptfenster(db, po, stumm=True)
f.resize(1366, 728)
f.show()
meldungen = []
alt = f.meldung
f.meldung = lambda text, *a, **k: (meldungen.append(text), alt(text, *a, **k))
a = db.angebot_neu(dict(kunde="Test (erfunden)", maschine="T11"))
gut = dict(profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=900, stueck=4, schneidweg=320, einstiche=2)
db.position_neu(a, dict(gut, pos=10, artikel="G1"))
db.position_neu(a, dict(gut, pos=20, artikel="F1", laenge=None))                  # Teilelänge fehlt
db.position_neu(a, dict(gut, pos=30, artikel="G2"))
db.position_neu(a, dict(gut, pos=40, artikel="F2", werkstoff_id="XYZ-gibt-es-nicht"))
s = f.angebot_oeffnen(a)
s.optimieren()
app.processEvents()
m = s.pos_modell
offen = s.offene_punkte()
assert [m.daten[r]["pos"] for r in offen] == [20, 40], [(m.daten[r]["pos"], m.status[r]) for r in range(m.rowCount())]
assert "2 offene Punkte (F7)" in s.pos_info.text(), s.pos_info.text()

s.pos_ansicht.setCurrentIndex(m.index(0, 0))
assert m.daten[s.naechstes_problem()]["pos"] == 20
assert "Pos. 20 (1 von 2" in meldungen[-1] and "Teilelänge" in meldungen[-1], meldungen[-1]
assert m.daten[s.naechstes_problem()]["pos"] == 40
assert m.daten[s.naechstes_problem()]["pos"] == 20, "am Ende wieder vorn"
assert m.daten[s.vorheriges_problem()]["pos"] == 40, "rückwärts vom ersten zum letzten"
assert m.daten[s.pos_ansicht.currentIndex().row()]["pos"] == 40
ok("Zeile über den Positionen nennt die offenen Punkte; F7 / Umschalt+F7: nächste und vorherige Position mit offenem Punkt, ringsum, Status in der Statuszeile")

s.reiter.setCurrentIndex(1)
assert f.kuerzel("problem") and s.reiter.currentWidget() is s.pos_seite
assert f.kuerzel_aktionen["problem"].shortcut() == QKeySequence("F7")
assert f.kuerzel_aktionen["problem_zurueck"].shortcut() == QKeySequence("Shift+F7")
assert any(t.startswith("F7") for t, _, _ in tastatur.UEBERSICHT)
ok("Kürzel im Menü Bearbeiten, wirkt auch aus einem anderen Reiter (springt zu den Positionen)")

for r in offen:
    db.position_aendern(m.daten[r]["id"], "laenge", 900) if m.daten[r]["pos"] == 20 else \
        db.position_aendern(m.daten[r]["id"], "werkstoff_id", "S235-10219")
s.neu_laden()
s.optimieren()
app.processEvents()
assert not s.offene_punkte() and s.naechstes_problem() is None and meldungen[-1].startswith("Keine offenen Punkte")
assert "offene" not in s.pos_info.text(), s.pos_info.text()
ok("Ohne offene Punkte: Meldung, nichts springt")
print("Alle Tests OK")
