# PyInstaller-Spezifikation für Rohrlaser-Kalkulation.exe (Ordner-Variante, startet schneller als eine Einzeldatei).
# Aufruf (Windows): pyinstaller --noconfirm --clean programm/rohrlaser.spec
# Ergebnis: dist/Rohrlaser-Kalkulation/Rohrlaser-Kalkulation.exe; die Daten legt das Programm beim ersten
# Start im Ordner 'Daten' daneben an.
import os

a = Analysis([os.path.join(SPECPATH, "start.py")], pathex=[SPECPATH], binaries=[], datas=[],
             hiddenimports=[], excludes=["tkinter", "matplotlib", "numpy", "PySide6.QtWebEngineCore",
                                         "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Rohrlaser-Kalkulation", console=False, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="Rohrlaser-Kalkulation", upx=False)
