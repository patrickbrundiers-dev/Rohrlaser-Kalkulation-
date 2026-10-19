"""Windows-Versionsinformationen (Eigenschaften → Details) für die mit PyInstaller gebauten .exe-Dateien.

Eine .exe ohne Hersteller, Produktname und Version wirkt auf Virenscanner wie Schadsoftware; mit vollständigen
Angaben gibt es deutlich weniger Fehlalarme. Benutzt von rohrlaser.spec und step_messung/step_messung.spec.
"""
import os
import re

HERSTELLER = "Patrick Brundiers"
PRODUKT = "Rohrlaser Angebotskalkulation"


def version():
    text = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "rohrlaser", "__init__.py"),
                encoding="utf-8").read()
    return re.search(r'VERSION = "([^"]+)"', text).group(1)


def versionsinfo(dateiname, beschreibung, ordner):
    """Versionsdatei im Textformat von PyInstaller (EXE(version=Pfad)) in ordner schreiben, Pfad zurückgeben."""
    v = version()
    zahlen = tuple((list(int(z) for z in re.findall(r"\d+", v)) + [0, 0, 0, 0])[:4])
    werte = [("CompanyName", HERSTELLER), ("FileDescription", beschreibung), ("FileVersion", v),
             ("InternalName", dateiname), ("LegalCopyright", f"© {HERSTELLER}"),
             ("OriginalFilename", dateiname + ".exe"), ("ProductName", PRODUKT), ("ProductVersion", v)]
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={zahlen}, prodvers={zahlen}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704B0', [
{chr(10).join(f"      StringStruct({n!r}, {w!r})," for n, w in werte)}
    ])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])
  ]
)
"""
    os.makedirs(ordner, exist_ok=True)
    pfad = os.path.join(ordner, dateiname + "_version.txt")
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(text)
    return pfad
