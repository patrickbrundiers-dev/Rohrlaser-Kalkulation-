"""STEP-Import: Standardordner des Dateidialogs und sichtbares Ablagefeld für Drag & Drop im Angebot."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))

from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDragEnterEvent, QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import step_ablage  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster, OrdnerEingabe  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNG  # noqa: E402

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")

# 1. Startordner: Standardordner > zuletzt benutzter Ordner > Benutzerordner; nicht vorhandene Ordner zählen nicht
assert EINSTELLUNG["step_ordner"].art == "ordner" and db.einstellung("step_ordner") == ""
assert step_ablage.start_ordner(db) == Path.home()
zuletzt, standard = tmp / "zuletzt", tmp / "Zeichnungen"
zuletzt.mkdir()
standard.mkdir()
step_ablage.ordner_merken(db, [str(zuletzt / "a.step"), str(zuletzt / "b.stp")])
assert step_ablage.start_ordner(db) == zuletzt
db.einstellung_setzen("step_ordner", str(standard))
assert step_ablage.start_ordner(db) == standard
db.einstellung_setzen("step_ordner", str(tmp / "gibt es nicht"))
assert step_ablage.start_ordner(db) == zuletzt, "nicht erreichbarer Standardordner: zuletzt benutzter Ordner"
db.einstellung_setzen("step_ordner", "")
print("OK: Startordner (Standardordner, sonst zuletzt benutzter Ordner, sonst Benutzerordner)")

# 2. Einstellungsseite: Feld mit Ordner wählen/Leeren speichert die Einstellung
fenster = Hauptfenster(db, stumm=True)
eingaben = [w for w in fenster.findChildren(OrdnerEingabe) if w.titel == "Standardordner wählen"]   # ohne den
assert len(eingaben) == 1, eingaben                                     # gemeinsamen Ordner der Mitarbeiter
w = eingaben[0]
w._setzen(str(standard))
assert db.einstellung("step_ordner") == str(standard)
w._setzen("")
assert db.einstellung("step_ordner") == "" and w.pfad.text() == ""
print("OK: Einstellung STEP-Import: Standardordner (Ordner wählen …, Leeren)")

# 3. Ablagefeld: klein neben 'STEP importieren …', groß bei leerer Positionsliste, färbt sich beim Ziehen
seite = fenster.angebot_oeffnen(db.angebot_neu())
fenster.show()
app.processEvents()
assert seite.ablage_klein.isVisible() and seite.ablage_gross.isVisible() and not seite.pos_ansicht.isVisible()
geoeffnet = []
seite.step_importieren = lambda dateien=None, **_: geoeffnet.append(dateien)
seite.ablage_gross.geklickt.emit()
seite.ablage_klein.geklickt.emit()
assert geoeffnet == [None, None], "Klick aufs Feld öffnet den Dateidialog"

datei = tmp / "teil.step"
datei.write_text("ISO-10303-21;", encoding="utf-8")
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(str(datei))])
farbe = seite.ablage_gross.styleSheet()
seite.dragEnterEvent(QDragEnterEvent(QPoint(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
assert seite.ablage_gross.styleSheet() != farbe and "#DCE9F8" in seite.ablage_klein.styleSheet()
seite.dropEvent(QDropEvent(QPointF(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier))
assert seite.ablage_gross.styleSheet() == farbe, "nach dem Ablegen wieder normal"
assert geoeffnet[-1] == [str(datei)]

db.position_neu(seite.id, dict(artikel="T1", laenge=500, stueck=1))
seite.neu_laden()
app.processEvents()
assert not seite.ablage_gross.isVisible() and seite.pos_ansicht.isVisible() and seite.ablage_klein.isVisible()
print("OK: Ablagefeld (klein neben dem Knopf, groß im leeren Angebot, Klick und Drag & Drop)")
fenster.close()
db.schliessen()
