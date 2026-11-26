"""Marke NexTube (Branding B-1; Patrick 26.11.2026: „NexTube neuer Name und dieses Icon verwenden“).

Die EINE Stelle für Name, Icon und Markenfarben. Ein neuer Name ändert nur diese Datei.

Bewusst NICHT umbenannt, damit nichts bricht:
- Programmdateien (Rohrlaser-Angebotskalkulation.exe, Rohrlaser-Auslastung.exe, STEP-Import.exe).
- Datenordner (%LOCALAPPDATA%\\Rohrlaser Angebotskalkulation\\Daten), Ablage, Lizenzordner.
- Update-Weg (Repo Rohrlaser-Updates).
- Kennung in den Update-Listen (PROGRAMM_ID_…): Eine installierte ältere Rohrlaser Auslastung prüft diese Kennung und
  würde ein Update mit neuem Namen ablehnen.

Ohne Qt (Tests, Anleitung, Auslastung); icon() lädt Qt erst beim Aufruf.
"""
from pathlib import Path

MARKE = "NexTube"
NAME = MARKE                                    # Kalkulation: Fenstertitel, Startseite, Über, Anleitung, PDF-Autor
NAME_AUSLASTUNG = f"{MARKE} Auslastung"
UNTERTITEL = "Angebotskalkulation und Materialoptimierung für Rohrlaserteile"

PROGRAMM_ID_KALKULATION = "Rohrlaser Angebotskalkulation"      # Update.json „programm“ (nie ändern)
PROGRAMM_ID_AUSLASTUNG = "Rohrlaser Auslastung"                 # Update.json „programm“ (nie ändern)

# Markenfarben aus dem Icon: Laser-Orange, Stahl, fast Schwarz
ORANGE = "#FF6A13"
STAHL = "#C4CAD2"
SCHWARZ = "#0E0E10"

BILDER = Path(__file__).resolve().parent / "bilder"
ICON_ICO = BILDER / "nextube.ico"       # Windows: Programmdatei, Fenster, Taskleiste (16–256 px, klein vereinfacht)
ICON_PNG = BILDER / "nextube.png"       # 512 px, Startseite und Über


def icon():
    """QIcon der Marke (leer, wenn die Datei fehlt)."""
    from PySide6.QtGui import QIcon
    for p in (ICON_ICO, ICON_PNG):
        if p.is_file():
            return QIcon(str(p))
    return QIcon()


def pixmap(px):
    """Icon als Bild in px × px (Startseite, Über); leer, wenn die Datei fehlt."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QPixmap
    bild = QPixmap(str(ICON_PNG)) if ICON_PNG.is_file() else QPixmap()
    return bild.scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation) if not bild.isNull() else bild
