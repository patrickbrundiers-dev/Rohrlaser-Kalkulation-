"""Für Tests mit Referenzwerten aus der Zeit vor „Laserzeit vollständig berechnet“ (bis 0.9.349): Seit 16.11.2026
sind in jeder Datendatei Richtwerte für Dynamik, Einstechen, Kopfhub, Stangenwechsel, Nebenzeit, Entladen, Messen
und Handarbeit vorbelegt. setzen(db) leert diese Maschinenfelder wieder, damit die Maschinen mit den festen Zeiten
rechnen (so wie ein Anwender, der die Felder leert)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "programm"))
from rohrlaser.stammdaten import DYNAMIK_FELDER, EINSTICH_FELDER, KOPFWEG_FELDER, ZEITEN_FELDER  # noqa: E402

FELDER = DYNAMIK_FELDER + EINSTICH_FELDER + ZEITEN_FELDER + KOPFWEG_FELDER


def setzen(db):
    for z in db.zeilen("maschinen"):
        for feld in FELDER:
            if z.get(feld) is not None:
                db.aendern("maschinen", z["id"], feld, None)
    return db
