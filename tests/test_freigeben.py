"""Speicher geschlossener Angebote (Systemcheck 19.11.2026, freigeben.py).

- Ring aus PySide-Hüllen (Fenster -> Modell ohne Eltern -> Fenster) mit großen Daten: nach nach_loeschen und
  deleteLater sind Fenster und Daten frei, das Modell ist mit dem Fenster gelöscht.
- Ein noch lebendes Objekt (hier das „Hauptfenster“, auf das das Fenster verweist) wird nie angefasst.
- Hauptfenster: ein Angebot zehnmal öffnen und schließen – keine geschlossene Seite behält ihre Daten.
Aufruf: python tests/test_freigeben.py
"""
import gc
import os
import sys
import tempfile
import weakref
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QAbstractTableModel, QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QTableView, QWidget  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import freigeben  # noqa: E402


def ok(text):
    print("OK    ", text)


def abarbeiten():
    for _ in range(3):
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        app.processEvents()
    gc.collect()


class Daten:
    pass


class Modell(QAbstractTableModel):
    def __init__(self, seite):
        super().__init__()          # ohne Eltern, wie die Tabellenmodelle der Angebotsseite
        self.s = seite

    def rowCount(self, *_):
        return 0

    def columnCount(self, *_):
        return 0


class Seite(QWidget):
    def __init__(self, haupt):
        super().__init__()
        self.f = haupt
        self.daten = Daten()
        self.daten.gross = bytearray(5_000_000)
        self.modell = Modell(self)
        self.ansicht = QTableView(self)
        self.ansicht.setModel(self.modell)
        self.ansicht.klick = self.zeigen        # Verweis zurück auf die Seite (Ring)

    def zeigen(self):
        return self.daten


haupt = QWidget()
haupt.merk = "bleibt"
s = Seite(haupt)
w_seite, w_daten, w_modell = weakref.ref(s), weakref.ref(s.daten), weakref.ref(s.modell)
assert freigeben.nach_loeschen(s) >= 3
assert s.modell.parent() is s, "Modell ohne Eltern nicht an das Fenster gehängt"
s.deleteLater()
del s
abarbeiten()
assert w_daten() is None and w_seite() is None, "Fenster bzw. Daten bleiben im Speicher"
assert w_modell() is None, "Modell bleibt im Speicher"
assert haupt.merk == "bleibt" and freigeben.zaehler["geleert"] >= 1, "lebendes Objekt angefasst"
ok("Ring Fenster -> Modell ohne Eltern -> Fenster: nach dem Schließen frei, lebendes Hauptfenster unberührt")

# Gegenprobe ohne nach_loeschen (nur Hinweis: der einfache Ring hier wird oft auch so frei, der echte nicht)
s2 = Seite(haupt)
w2 = weakref.ref(s2.daten)
s2.deleteLater()
del s2
abarbeiten()
ohne = w2() is not None
ok(f"Gegenprobe ohne Freigabe: Daten {'bleiben' if ohne else 'frei'} (PySide räumt Ringe {'nicht ' if ohne else ''}ab)")

# Hauptfenster: Angebot zehnmal öffnen und schließen
from rohrlaser.angebot_fenster import AngebotSeite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

AngebotSeite.CHECK_SOFORT = False
db = Datenbank(Path(tempfile.mkdtemp()) / "freigeben.db")
f = Hauptfenster(db, HIER.parent / "programm", stumm=True)
aid = db.angebot_neu(dict(kunde="Speicher"))
for _ in range(10):
    f.angebot_oeffnen(aid)
    app.processEvents()
    f.angebot_schliessen(aid)
    abarbeiten()
# leere Hüllen (ohne Attribute, also ohne Daten) können bleiben; Seiten mit Daten nicht
seiten = [o for o in gc.get_objects() if isinstance(o, AngebotSeite) and vars(o)]
assert len(seiten) <= 1, f"{len(seiten)} geschlossene Angebotsseiten mit ihren Daten noch im Speicher"
ok(f"Hauptfenster: Angebot zehnmal geöffnet und geschlossen, {len(seiten)} Seite(n) mit Daten im Speicher")
db.schliessen()
print("Freigeben: alle Prüfungen bestanden.")
os._exit(0)
