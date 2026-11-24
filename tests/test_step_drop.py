"""STEP-Dateien aus dem Explorer ziehen: der Drop kehrt sofort zurück (sonst hält Windows den Explorer fest, bis die
Position im Angebot ist), der Import startet erst danach und genau einmal; ein zweiter Drop während eines laufenden
Imports wird mit Hinweis abgelehnt. Gilt für Angebot (Ablagefeld), Angebotsliste und Startseite.

Aufruf: python tests/test_step_drop.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))

from PySide6.QtCore import QMimeData, QUrl  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


class Ziehen:                                                # wie ein QDropEvent mit gezogenen Dateien
    def __init__(self, pfade):
        self.m = QMimeData()
        self.m.setUrls([QUrl.fromLocalFile(str(p)) for p in pfade])
        self.angenommen = self.abgelehnt = False

    def mimeData(self):
        return self.m

    def acceptProposedAction(self):
        self.angenommen = True

    def ignore(self):
        self.abgelehnt = True


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
ordner = tmp / "Anfrage"
(ordner / "unter").mkdir(parents=True)
for n in ("b.step", "unter/a.STP", "zeichnung.pdf"):
    (ordner / n).write_text("x")
leer = tmp / "leer"
leer.mkdir()

# 1. Vorprüfung beim Darüberziehen ohne Ordnersuche; step_dateien ohne Dubletten, sortiert
assert step.step_kandidaten([ordner / "b.step"]) and step.step_kandidaten([leer])
assert not step.step_kandidaten([ordner / "zeichnung.pdf"])
assert step.step_dateien([ordner, ordner / "b.step"]) == [ordner / "b.step", ordner / "unter" / "a.STP"]
print("OK: Vorprüfung ohne Ordnersuche, Ordner erst nach dem Ablegen durchsucht")

db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
seite = fenster.angebot_oeffnen(db.angebot_neu())
importe = []


def importieren(dateien=None, **_):
    importe.append(dateien)
    zweiter = Ziehen([ordner / "b.step"])               # während des Imports noch eine Datei gezogen
    seite.dropEvent(zweiter)
    assert zweiter.abgelehnt and not zweiter.angenommen
    assert "läuft schon ein STEP-Import" in fenster.statusBar().currentMessage()


seite.step_importieren = importieren

# 2. Angebot: Drop kehrt zurück, bevor der Import läuft; danach genau ein Import, zweiter Drop abgelehnt
z = Ziehen([ordner])
seite.dragEnterEvent(z)
assert z.angenommen
z = Ziehen([ordner])
seite.dropEvent(z)
assert z.angenommen and importe == [] and fenster.step_drop_laeuft, "Import erst nach dem Drop"
app.processEvents()
assert importe == [[str(ordner / "b.step"), str(ordner / "unter" / "a.STP")]], importe
assert not fenster.step_drop_laeuft
app.processEvents()
assert len(importe) == 1, "abgelehnter Drop importiert nicht nachträglich"
print("OK: Angebot: Drop sofort angenommen, Import danach genau einmal, zweiter Drop abgelehnt")

# 3. Ordner ohne STEP-Dateien: Hinweis, kein Import; nach einem Fehler im Import wieder frei
seite.dropEvent(Ziehen([leer]))
app.processEvents()
assert len(importe) == 1 and "Keine STEP-Dateien" in fenster.statusBar().currentMessage()


def fehler(dateien=None, **_):
    raise RuntimeError("Messung fehlgeschlagen")


seite.step_importieren = fehler
seite.dropEvent(Ziehen([ordner / "b.step"]))
app.processEvents()             # Qt meldet die Ausnahme aus dem Zeitgeber nur, der Test läuft weiter
assert not fenster.step_drop_laeuft, "nach einem Fehler sind weitere Drops möglich"
print("OK: leerer Ordner meldet 'Keine STEP-Dateien', Sperre nach Fehler wieder frei")

# 4. Angebotsliste und Startseite: neues Angebot aus STEP erst nach dem Drop
neu = []
fenster.angebote.neu_aus_step = lambda pfade=None, kundennr=None: neu.append(pfade)
for ziel in (fenster.angebote, fenster.start):
    vorher = len(neu)
    z = Ziehen([ordner])
    ziel.dropEvent(z)
    assert z.angenommen and len(neu) == vorher, "neues Angebot erst nach dem Drop"
    app.processEvents()
    assert len(neu) == vorher + 1 and neu[-1] == [str(ordner)], neu
print("OK: Angebotsliste und Startseite: neues Angebot aus STEP nach dem Drop")
fenster.close()
db.schliessen()
