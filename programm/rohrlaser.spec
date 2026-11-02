# PyInstaller-Spezifikation für Rohrlaser-Angebotskalkulation.exe (Ordner-Variante, startet schneller als eine Einzeldatei).
# Aufruf (Windows): pyinstaller --noconfirm --clean programm/rohrlaser.spec
# Ergebnis: dist/Rohrlaser-Angebotskalkulation/Rohrlaser-Angebotskalkulation.exe; die Daten legt das Programm beim ersten
# Start im Ordner 'Daten' daneben an.
# Der Ordner STEP-Import (eigenes Paket) wird im Workflow neben die .exe kopiert.
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

sys.path.insert(0, SPECPATH)
from versionsinfo import versionsinfo  # noqa: E402

# reportlab lädt die Barcode-Module (code128, code39, usps …) über Namen nach, PyInstaller sieht sie nicht: alle
# mitnehmen, sonst bricht das Etiketten-PDF mit „No module named reportlab.graphics.barcode.code128“ ab (0.9.231)
BARCODE = [m for m in collect_submodules("reportlab.graphics.barcode") if not m.endswith(".test")]

a = Analysis([os.path.join(SPECPATH, "start.py")], pathex=[SPECPATH],
             binaries=[], datas=[(os.path.join(SPECPATH, "rohrlaser", "rp_profile.json"), "rohrlaser"),
                                 (os.path.join(SPECPATH, "rohrlaser", "Lizenzbedingungen.txt"), "rohrlaser")], hiddenimports=BARCODE + ["rohrlaser.ansicht3d_gl", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvg", "pypdfium2", "pypdfium2_raw", "olefile"], excludes=["tkinter", "matplotlib", "numpy", "PySide6.QtWebEngineCore",
                                         "PySide6.QtQml", "PySide6.QtQuick", "PySide6.Qt3DCore"],
             noarchive=False)
# Plan „Quellcode schützen“ Q3: eigene Module als übersetzte Erweiterungsmodule statt Bytecode (kompilieren.py)
if os.environ.get("RL_KOMPILIERT"):
    from kompilieren import kompiliert_tauschen  # noqa: E402
    print("kompiliert:", kompiliert_tauschen(a, os.environ["RL_KOMPILIERT"]), "Module")
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Rohrlaser-Angebotskalkulation", console=False, upx=False,
          version=versionsinfo("Rohrlaser-Angebotskalkulation", "Rohrlaser Angebotskalkulation", workpath))
coll = COLLECT(exe, a.binaries, a.datas, name="Rohrlaser-Angebotskalkulation", upx=False)
