"""Gezogene Spaltenbreiten bleiben über einen Neustart erhalten (Layout-Plan L15), zurücksetzen passt neu ein."""
import sys
import tempfile
from pathlib import Path
from unittest import mock

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import spaltenbreite  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


pfad = Path(tempfile.mkdtemp()) / "rohrlaser.db"
db = Datenbank(pfad)
beispiel_angebot.anlegen(db)
f = Hauptfenster(db, stumm=True)
f.resize(1400, 850)
f.show()
f.reiter.setCurrentWidget(f.angebote)
app.processEvents()
v = f.angebote.ansicht
ag = v.auto_groesse
spalte = next(c for c in range(v.model().columnCount())
              if v.model().headerData(c, Qt.Horizontal, Qt.DisplayRole) == "Kunde")
alt = v.columnWidth(spalte)
with mock.patch.object(QGuiApplication, "mouseButtons", return_value=Qt.LeftButton):    # wie mit der Maus gezogen
    v.setColumnWidth(spalte, alt + 77)
ag.merken()
schl = spaltenbreite.tabellen_schluessel(v)
assert db.einstellung(spaltenbreite.SPEICHER_NAME)[schl]["Kunde"] == alt + 77
ok(f"gezogene Spalte gemerkt unter {schl!r}")

ag.neu_einpassen()                  # Tabelle neu aufgebaut: die gemerkte Breite gilt weiter
assert v.columnWidth(spalte) == alt + 77
f.close()
db.con.close()

db = Datenbank(pfad)                # Neustart
f = Hauptfenster(db, stumm=True)
f.resize(1400, 850)
f.show()
f.reiter.setCurrentWidget(f.angebote)
app.processEvents()
v = f.angebote.ansicht
assert v.columnWidth(spalte) == alt + 77, (v.columnWidth(spalte), alt)
ok("nach dem Neustart wieder dieselbe Breite")

kopf = v.horizontalHeader()
aktion = next(a for a in kopf.actions() if a.text() == "Spaltenbreiten zurücksetzen")
assert kopf.contextMenuPolicy() == Qt.ActionsContextMenu
aktion.trigger()
app.processEvents()
assert v.columnWidth(spalte) == alt and schl not in (db.einstellung(spaltenbreite.SPEICHER_NAME) or {})
ok("Rechtsklick auf den Kopf → Spaltenbreiten zurücksetzen: wieder eingepasst, nichts mehr gemerkt")

from rohrlaser import teilen  # noqa: E402
assert spaltenbreite.SPEICHER_NAME not in teilen.EINSTELLUNGEN_GETEILT
ok("Spaltenbreiten werden nicht mit den Kollegen geteilt")
print("OK: Spaltenbreiten merken")
