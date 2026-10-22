# PyInstaller-Spezifikation für Rohrlaser-Angebotskalkulation.exe (Ordner-Variante, startet schneller als eine Einzeldatei).
# Aufruf (Windows): pyinstaller --noconfirm --clean programm/rohrlaser.spec
# Ergebnis: dist/Rohrlaser-Angebotskalkulation/Rohrlaser-Angebotskalkulation.exe; die Daten legt das Programm beim ersten
# Start im Ordner 'Daten' daneben an.
# Der Ordner STEP-Import (eigenes Paket) wird im Workflow neben die .exe kopiert.
import os
import sys

sys.path.insert(0, SPECPATH)
from versionsinfo import versionsinfo  # noqa: E402

a = Analysis([os.path.join(SPECPATH, "start.py")], pathex=[SPECPATH],
             binaries=[], datas=[(os.path.join(SPECPATH, "rohrlaser", "rp_profile.json"), "rohrlaser")], hiddenimports=["reportlab.graphics.barcode.common"], excludes=["tkinter", "matplotlib", "numpy", "PySide6.QtWebEngineCore",
                                         "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Rohrlaser-Angebotskalkulation", console=False, upx=False,
          version=versionsinfo("Rohrlaser-Angebotskalkulation", "Rohrlaser Angebotskalkulation", workpath))
coll = COLLECT(exe, a.binaries, a.datas, name="Rohrlaser-Angebotskalkulation", upx=False)
