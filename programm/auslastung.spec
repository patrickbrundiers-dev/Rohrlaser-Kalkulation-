# PyInstaller-Spezifikation für Rohrlaser-Auslastung.exe (eigenes Programm zur Maschinenauslastung, läuft ohne die
# Kalkulation; Ordner-Variante). Aufruf (Windows): pyinstaller --noconfirm --clean programm/auslastung.spec
# Ergebnis: dist/Rohrlaser-Auslastung/Rohrlaser-Auslastung.exe; die Datenbank legt das Programm beim ersten Start im
# Ordner 'Daten' daneben an (anderer Ort: Auslastung.ini, siehe rl_auslastung/ort.py).
# Aus dem Paket rohrlaser kommen nur einlastung, wochen, feiertage, stil und auslastung_grafik mit.
import os
import re
import sys

sys.path.insert(0, SPECPATH)
import versionsinfo as vi  # noqa: E402

VERSION = re.search(r'VERSION = "([^"]+)"', open(os.path.join(SPECPATH, "rl_auslastung", "__init__.py"),
                                                 encoding="utf-8").read()).group(1)
vi.version = lambda: VERSION            # eigene Versionsnummer, nicht die der Kalkulation
vi.PRODUKT = "Rohrlaser Auslastung"

a = Analysis([os.path.join(SPECPATH, "start_auslastung.py")], pathex=[SPECPATH], binaries=[], datas=[],
             # rohrlaser.auslastung / etiketten / qt_slots: nur in Funktionen der Kalkulation nachgeladen, hier nie
             hiddenimports=[], excludes=["rohrlaser.auslastung", "rohrlaser.etiketten", "rohrlaser.qt_slots", "tkinter", "matplotlib", "numpy", "reportlab", "cryptography", "pypdfium2",
                                         "PySide6.QtWebEngineCore", "PySide6.QtQml", "PySide6.QtQuick",
                                         "PySide6.Qt3DCore", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets"],
             noarchive=False)
fremd = [n for n, *_ in a.pure if n.startswith("rohrlaser.") and n not in (
    "rohrlaser.einlastung", "rohrlaser.wochen", "rohrlaser.feiertage", "rohrlaser.stil", "rohrlaser.auslastung_grafik")]
if fremd:
    raise SystemExit("auslastung.spec: das Programm zieht Module der Kalkulation mit: " + ", ".join(fremd))
# Im Sammel-Release (RL_KOMPILIERT gesetzt): die fünf Module der Kalkulation übersetzt wie dort (kompilieren.py)
if os.environ.get("RL_KOMPILIERT"):
    from kompilieren import kompiliert_tauschen  # noqa: E402
    print("kompiliert:", kompiliert_tauschen(a, os.environ["RL_KOMPILIERT"]), "Module")
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Rohrlaser-Auslastung", console=False, upx=False,
          version=vi.versionsinfo("Rohrlaser-Auslastung", "Rohrlaser Auslastung", workpath))
coll = COLLECT(exe, a.binaries, a.datas, name="Rohrlaser-Auslastung", upx=False)
