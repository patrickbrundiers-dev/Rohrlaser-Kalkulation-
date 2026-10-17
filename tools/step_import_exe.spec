# PyInstaller-Spezifikation für STEP-Import.exe (Ordner-Variante, startet schneller als eine Einzeldatei).
# Aufruf (Windows): pyinstaller --noconfirm --clean tools/step_import_exe.spec
# Ergebnis: dist/STEP-Import/STEP-Import.exe mit allen benötigten OpenCascade-Bibliotheken.
import glob
import os
import sysconfig

from PyInstaller.utils.hooks import collect_all

# OCP lädt Teilmodule aus dem C++-Code nach, das sieht die Importanalyse nicht: alles einsammeln.
datas, binaries, hiddenimports = collect_all("OCP")
hiddenimports = [m for m in hiddenimports if "Vtk" not in m and "vtk" not in m]
# Von delvewheel/auditwheel ausgelagerte DLLs (cadquery_ocp.libs) neben die .exe legen
site = sysconfig.get_paths()["purelib"]
for ordner in glob.glob(os.path.join(site, "*ocp*.libs")):
    binaries += [(f, ".") for f in glob.glob(os.path.join(ordner, "*")) if os.path.isfile(f)]

a = Analysis([os.path.join(SPECPATH, "step_messen.py")], pathex=[SPECPATH], binaries=binaries, datas=datas,
             hiddenimports=hiddenimports, excludes=["vtk", "vtkmodules", "tkinter", "matplotlib", "numpy.tests"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="STEP-Import", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="STEP-Import", upx=False)
