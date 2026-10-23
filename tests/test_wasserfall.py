"""Kostenwasserfall im Preisaufbau und Staffelkurve (Layout-Plan L22): Wasserfall = Verkaufspreis auf den Cent."""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.kostenbalken import wasserfall  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


# ohne Fenster: Gruppen addieren sich, Summenzeilen setzen den Stand neu, 0-Gruppen fehlen
werte = {n: 0.0 for _, n, _ in rechnen.KOSTENARTEN}
werte.update(material=100.0, laser_schneiden=20.0, ruesten_maschine=5.0, stangenwechsel_kosten=2.5, herstell=127.5, selbst=127.5,
             gewinn=12.75, skonto=-3.0, verkauf=137.25)
kosten = [(t, werte[n], fett) for t, n, fett in rechnen.KOSTENARTEN]
w = wasserfall(kosten)
assert [t for t, *_ in w] == ["Material", "Laser schneiden", "Rüsten", "Herstellkosten", "Selbstkosten",
                              "Gewinn", "Skonto",
                              "Verkaufspreis"], w
assert w[2][1:] == (120.0, 127.5, False) and w[3][1:] == (0.0, 127.5, True)
assert w[4][1:] == (0.0, 127.5, True) and w[6][1:] == (140.25, 137.25, False) and w[-1][2] == w[-2][2] == 137.25
ok("Wasserfall: Gruppen des Preisaufbaus, Rüsten zusammengefasst, Skonto negativ, ohne 0-Zeilen")

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
s = f.angebot_oeffnen(beispiel_angebot.anlegen(db))
assert s.optimieren()
ob = s.uebersicht_bereich
_, summen = s._rechnung()
stufen = ob.wasserfall.stufen
assert stufen[-1][0] == "Verkaufspreis" and round(stufen[-1][2], 2) == round(summen["verkauf"], 2)
assert abs(stufen[-2][2] - summen["verkauf"]) < 0.005, (stufen[-2], summen["verkauf"])
herstell = next(b for t, _, b, _ in stufen if t == "Herstellkosten")
vor = [b for t, _, b, _ in stufen][[t for t, *_ in stufen].index("Herstellkosten") - 1]
assert abs(vor - herstell) < 0.005
ok(f"Beispielangebot: {len(stufen)} Stufen, Herstellkosten und Verkaufspreis {summen['verkauf']:.2f} € auf den Cent")
ob.wasserfall_bereich.aufklappen(True)
ob.wasserfall.resize(420, ob.wasserfall.sizeHint().height())
assert not ob.wasserfall.grab().isNull() and ob.wasserfall.sizeHint().height() == 18 * len(stufen) + 4
ok("Wasserfall im Preisaufbau aufklappbar und gezeichnet")

sp = s.staffelpreise_rechnen()
kurve = s.st_seite.vergleich
assert kurve.reihen and kurve.mengen == sorted({z["menge"] for z in sp})
reihen = kurve.punkte(400, 300)
for _, (y0, y1, maxp), pk in reihen:
    xs = [x for x, *_ in pk]
    assert xs == sorted(xs) and all(y0 <= y <= y1 for _, y, _, _ in pk) and maxp == max(w for *_, w in pk)
kurve.resize(400, 300)
assert not kurve.grab().isNull() and "×" in kurve.toolTip()
ok(f"Staffelkurve: {len(reihen)} Reihe(n) über {len(kurve.mengen)} Mengen, Punkte im Bild")
print("OK: Wasserfall und Staffelkurve")
