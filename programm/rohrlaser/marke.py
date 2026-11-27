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


def symbol_auffrischen(exe=None, version=None, merker=None):
    """Windows zeigt nach einem Update oft weiter das alte Programmsymbol (Eigenschaften, Explorer, Taskleiste,
    angeheftete Verknüpfungen): der Symbol-Zwischenspeicher von Windows merkt sich das Bild je Dateipfad, und die .exe
    behält beim Update ihren Namen. Einmal je Version: Windows die geänderte .exe melden und den Zwischenspeicher neu
    einlesen lassen (ie4uinit -show, ohne Adminrechte). Ergebnis: True, wenn aufgefrischt wurde (Patrick 27.11.2026)."""
    import os
    import subprocess
    import sys
    import tempfile
    if sys.platform != "win32" or not getattr(sys, "frozen", False) and exe is None:
        return False
    exe = str(exe or sys.executable)
    merker = Path(merker or Path(tempfile.gettempdir()) / f"NexTube_symbol_{Path(exe).stem}.txt")
    stand = f"{version or ''}|{exe}"
    try:
        if merker.is_file() and merker.read_text(encoding="utf-8").strip() == stand:
            return False
    except OSError:
        pass
    try:
        import ctypes
        shell = ctypes.windll.shell32
        shell.SHChangeNotify(0x00002000, 0x0005, ctypes.c_wchar_p(exe), None)    # SHCNE_UPDATEITEM, SHCNF_PATHW
        shell.SHChangeNotify(0x08000000, 0x0000, None, None)                     # SHCNE_ASSOCCHANGED
        ie4 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "ie4uinit.exe"
        if ie4.is_file():
            subprocess.Popen([str(ie4), "-show"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:      # noqa: BLE001 – nur Kosmetik, darf den Start nie stören
        from . import protokoll
        protokoll.warnung(f"Programmsymbol auffrischen: {type(e).__name__}: {e}")
        return False
    try:
        merker.write_text(stand, encoding="utf-8")
    except OSError as e:
        from . import protokoll
        protokoll.warnung(f"Programmsymbol: Merker nicht geschrieben ({e})")
    return True
