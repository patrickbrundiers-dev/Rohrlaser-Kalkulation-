"""STEP-Import: Ablagefeld für Drag & Drop im Angebot und Startordner des Dateidialogs.

Der Dateidialog „STEP importieren …“ startet im Standardordner aus den Einstellungen (step_ordner), sonst im
zuletzt benutzten STEP-Ordner (step_letzter_ordner, vom Programm gemerkt), sonst im Benutzerordner."""
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel

LETZTER = "step_letzter_ordner"     # vom Programm gemerkt, nicht in den Einstellungen sichtbar


def start_ordner(db):
    """Ordner, in dem der STEP-Dateidialog startet."""
    for name in ("step_ordner", LETZTER):
        wert = db.einstellung(name)
        if wert and Path(wert).is_dir():
            return Path(wert)
    return Path.home()


def ordner_merken(db, dateien):
    """Ordner der zuletzt gewählten STEP-Dateien merken (für den nächsten Dateidialog ohne Standardordner)."""
    if dateien:
        ordner = str(Path(dateien[0]).parent)
        if db.einstellung(LETZTER) != ordner:
            db.einstellung_setzen(LETZTER, ordner)


class AblageFeld(QLabel):
    """Gestrichelt umrandetes Feld „STEP / DXF ziehen oder klicken“. Klick = Dateidialog für STEP und DXF (Signal
    geklickt, ersetzt den Knopf „STEP importieren …“, der nur noch im Menü steht). Das
    Ziehen selbst nimmt die Angebotsseite an (das Feld leitet es an sie weiter); hervorheben() färbt das Feld,
    solange Dateien darüber gezogen werden. gross: großes Feld statt der leeren Positionsliste."""
    geklickt = Signal()
    KLEIN = "⇩ STEP / DXF hierher\nziehen oder klicken"     # zweizeilig: schmal genug für 1366 px
    GROSS = ("STEP- und DXF-Dateien oder Ordner hierher ziehen\n\n"
             "oder klicken, um Dateien zu wählen (STEP und DXF auch gemischt)")

    def __init__(self, gross=False):
        super().__init__(self.GROSS if gross else self.KLEIN)
        self.gross = gross
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("STEP- und DXF-Dateien oder ganze Ordner aus dem Explorer hierher (oder irgendwo ins Angebot) "
                        "ziehen; Klick öffnet den Dateidialog für STEP und DXF (beides zugleich wählbar)")
        if gross:
            self.setMinimumHeight(160)
        self.hervorheben(False)

    def hervorheben(self, an):
        rand, grund, schrift = ("#1F5FAD", "#DCE9F8", "#1F5FAD") if an else ("#8FA6C1", "#F4F7FB", "#3D5573")
        groesse = "15px" if self.gross else "11px"
        polster = "24px" if self.gross else "0px 8px"
        self.setStyleSheet(f"QLabel {{ border: 2px dashed {rand}; border-radius: 6px; background: {grund}; "
                           f"color: {schrift}; font-size: {groesse}; padding: {polster}; }}")

    def mouseReleaseEvent(self, ereignis):
        if ereignis.button() == Qt.LeftButton and self.rect().contains(ereignis.position().toPoint()):
            self.geklickt.emit()
        super().mouseReleaseEvent(ereignis)
