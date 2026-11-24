"""Prüft die Optimierung im Hintergrund (Prüfbericht 22.10.2026, B-6): ab HINTERGRUND_AB_TEILEN rechnet sie in einem
eigenen Thread mit Fortschritt, das Ergebnis ist dasselbe wie im Vordergrund, und Abbrechen speichert nichts.

Aufruf: python tests/test_hintergrund.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
a = db.angebot_neu(dict(kunde="Test", kundennr="1"))
for i, (profil, laenge) in enumerate([("QR 40x40x3", 700), ("QR 40x40x3", 1150), ("RR 42,4x2,0", 900),
                                      ("RR 42,4x2,0", 430)]):
    db.position_neu(a, dict(pos=10 * (i + 1), artikel=f"T{i}", profil_id=profil, werkstoff_id="S235-10219",
                            laenge=laenge, stueck=60, schneidweg=320, einstiche=2))
s = fenster.angebot_oeffnen(a)
vorne = rechnen.optimieren(s.kopf, s.positionen, s.k, s.tabellen, s.einst)

# Fortschritt und Abbruch im Rechenkern
schritte = []
erg = rechnen.optimieren(s.kopf, s.positionen, s.k, s.tabellen, s.einst,
                         fortschritt=lambda i, n, t: schritte.append((i, n, t)))
assert erg == vorne and [i for i, _, _ in schritte] == list(range(4)) and schritte[0][1] == 4, schritte


def ab_zwei(i, n, t):
    if i == 1:
        raise rechnen.Abbruch()


try:
    rechnen.optimieren(s.kopf, s.positionen, s.k, s.tabellen, s.einst, fortschritt=ab_zwei)
    raise AssertionError("nicht abgebrochen")
except rechnen.Abbruch:
    pass
ok("Rechenkern: Fortschritt je Abmessung (Schnittplan, Lieferlängen), gleiches Ergebnis, Abbruch möglich")

# Fenster: 240 Teile >= 150 -> Hintergrund-Thread
threads = []
alt_start = threading.Thread.start
threading.Thread.start = lambda self: (threads.append(self.name), alt_start(self))[1]
assert s.optimieren()
threading.Thread.start = alt_start
assert "Optimieren" in threads, threads
gespeichert = db.angebot(a)["ergebnis"]
assert gespeichert["stangen"] == vorne["stangen"] and s.stand_optimierung() == "aktuell"
ok(f"Fenster: 240 Teile im Hintergrund optimiert, Ergebnis wie im Vordergrund ({len(vorne['stangen'])} Stangen)")

# Abbrechen: nichts gespeichert, Meldung
db.position_aendern(s.positionen[0]["id"], "stueck", 61)
s.neu_laden()
vorher = db.angebot(a)["ergebnis"]
echt = rechnen.optimieren


def abbrechen_lassen(*args, fortschritt=None, **kw):
    fortschritt(0, 4, "Test")
    raise rechnen.Abbruch()        # wie Klick auf Abbrechen während der Rechnung


rechnen.optimieren = abbrechen_lassen
assert not s.optimieren()
rechnen.optimieren = echt
assert db.angebot(a)["ergebnis"] == vorher and "abgebrochen" in fenster.statusBar().currentMessage()
assert s.stand_optimierung().startswith("VERALTET")
ok("Abbrechen: kein Ergebnis gespeichert, Stand bleibt Veraltet, Meldung in der Statuszeile")
print("OK: Optimierung im Hintergrund")
