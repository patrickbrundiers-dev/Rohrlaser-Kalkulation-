# PyInstaller-Spezifikation für STEP-Import.exe (Ordner-Variante, startet schneller als eine Einzeldatei).
# Aufruf (Windows): pyinstaller --noconfirm --clean programm/step_messung/step_messung.spec
# Ergebnis: dist/STEP-Import/STEP-Import.exe mit allen benötigten OpenCascade-Bibliotheken.
import glob
import os
import sys
import sysconfig

from PyInstaller.utils.hooks import collect_all

sys.path.insert(0, os.path.dirname(SPECPATH))
from versionsinfo import versionsinfo  # noqa: E402

# OCP lädt Teilmodule aus dem C++-Code nach, das sieht die Importanalyse nicht: alles einsammeln.
datas, binaries, hiddenimports = collect_all("OCP")
hiddenimports = [m for m in hiddenimports if "Vtk" not in m and "vtk" not in m]
hiddenimports += ["step_abwicklung"]      # Kantteil-Abwicklung, wird erst bei Bedarf importiert
# RP-Bibliothek (rohrlaser/rp_profile.json) für die Erkennung der RP-Profile per Fingerabdruck
datas += [(os.path.join(os.path.dirname(SPECPATH), "rohrlaser", "rp_profile.json"), "rohrlaser")]
# Von delvewheel/auditwheel ausgelagerte DLLs (cadquery_ocp.libs) neben die .exe legen
site = sysconfig.get_paths()["purelib"]
for ordner in glob.glob(os.path.join(site, "*ocp*.libs")):
    binaries += [(f, ".") for f in glob.glob(os.path.join(ordner, "*")) if os.path.isfile(f)]

# Startdatei nur mit dem Aufruf: die Messung selbst (step_messen) kann so übersetzt werden (kompilieren.py)
a = Analysis([os.path.join(SPECPATH, "step_start.py")], pathex=[SPECPATH, os.path.dirname(SPECPATH)],
             binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, excludes=["vtk", "vtkmodules", "tkinter", "matplotlib", "numpy.tests"],
             noarchive=False)
# Plan „Quellcode schützen“ Q3: eigene Module als übersetzte Erweiterungsmodule statt Bytecode (kompilieren.py)
if os.environ.get("RL_KOMPILIERT"):
    from kompilieren import kompiliert_tauschen  # noqa: E402
    print("kompiliert:", kompiliert_tauschen(a, os.environ["RL_KOMPILIERT"]), "Module")
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="STEP-Import", console=True, upx=False,
          version=versionsinfo("STEP-Import", "STEP-Messung der Rohrlaser Angebotskalkulation", workpath))
coll = COLLECT(exe, a.binaries, a.datas, name="STEP-Import", upx=False)
