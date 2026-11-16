"""UI-Modernisierung U5 (Patrick 12.11.2026): Kennzahl-Kacheln auf der Startseite.

Prüft: fünf Kacheln über der Startseite für alle Benutzer (nicht nur Admin) mit denselben Zahlen wie die Pipeline
(Entwürfe, verschickt), Aufträge und Trefferquote der letzten 90 Tage, fällige Wiedervorlagen; Klick auf eine Kachel
öffnet die Angebotsliste mit dem passenden Filter; ohne Funktion Nachfassen keine Wiedervorlage-Kachel.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])

from rohrlaser import funktionen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


po = Path(tempfile.mkdtemp(prefix="kacheln_")) / "Rohrlaser-Angebotskalkulation"
(po / "Daten").mkdir(parents=True)
db = Datenbank(po / "Daten" / "rohrlaser.db")
werte = (("Entwurf", 640.0), ("Entwurf", 360.0), ("Verschickt", 1250.0), ("Beauftragt", 3480.5),
         ("Abgelehnt", 990.0), ("Abgelehnt", 100.0))
for i, (v, vk) in enumerate(werte):
    a = db.angebot_neu(dict(kunde=f"Kunde {i} (erfunden)", maschine="T11"))
    if v != "Entwurf":
        db.vorgang_setzen(a, v)
    db.kennzahlen_merken(a, vk, "")
f = Hauptfenster(db, po, stumm=True)
f.resize(1366, 728)
f.show()
f.reiter.setCurrentWidget(f.start)
f.start.neu_laden()
QApplication.processEvents()
k = f.start.kacheln.kacheln
assert f.start.kacheln.isVisible() and not (getattr(f, "bereich", None) and f.bereich.admin), "auch ohne Admin"
assert (k["Entwurf"].wert.text(), k["Entwurf"].unter.text()) == ("2", "1.000,00 € netto"), k["Entwurf"].unter.text()
assert (k["Verschickt"].wert.text(), k["Verschickt"].unter.text()) == ("1", "1.250,00 € netto")
assert (k["Beauftragt"].wert.text(), k["Beauftragt"].unter.text()) == ("1", "3.480,50 € netto")
assert k["quote"].wert.text() == "33 %", k["quote"].wert.text()          # 1 von 3 entschiedenen
assert k["wiedervorlage"].wert.text() == str(sum(1 for w in f.start.wiedervorlagen if w.rest <= 0))
ok("Fünf Kacheln für alle: Entwürfe, Verschickt, Aufträge und Trefferquote (90 Tage), Wiedervorlage")

QTest.mouseClick(k["Verschickt"], Qt.LeftButton, pos=QPoint(10, 10))
QApplication.processEvents()
assert f.reiter.currentWidget() is f.angebote and f.angebote.vorgang_filter.currentText() == "Verschickt"
ok("Klick auf eine Kachel öffnet die Angebotsliste mit diesem Filter")

db.einstellung_setzen("funktion_nachfassen", "nein")
assert not funktionen.an("funktion_nachfassen")
f.reiter.setCurrentWidget(f.start)
f.start.neu_laden()
QApplication.processEvents()
assert not k["wiedervorlage"].isVisible() and k["Entwurf"].isVisible()
ok("Funktion Nachfassen aus: keine Wiedervorlage-Kachel")
print("Alle Tests OK")
