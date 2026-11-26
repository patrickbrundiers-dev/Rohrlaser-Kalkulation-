"""Marke NexTube (Branding B-1, Patrick 26.11.2026): Name an einer Stelle, Icon, nichts bricht. Fälle B1–B9.

Aufruf: python tests/test_marke.py
"""
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
PROGRAMM = WURZEL / "programm"
sys.path.insert(0, str(PROGRAMM))

from PIL import Image  # noqa: E402

import rohrlaser  # noqa: E402
import rl_auslastung  # noqa: E402
from rohrlaser import marke, orte  # noqa: E402
from rl_auslastung import aktualisierung  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


pruefe(rohrlaser.NAME == marke.NAME == "NexTube" and rl_auslastung.NAME == "NexTube Auslastung",
       "B1 Name NexTube aus marke.py (Kalkulation und Auslastung)")
pruefe(rohrlaser.PROGRAMM_ID == "Rohrlaser Angebotskalkulation" and rl_auslastung.PROGRAMM_ID == "Rohrlaser Auslastung",
       "B2 Kennung der Update-Listen unverändert (ältere Auslastung nimmt das Update an)")
quelle = (PROGRAMM / "rl_auslastung" / "aktualisierung.py").read_text("utf-8")
pruefe('liste.get("programm") != PROGRAMM_ID' in quelle and "programm=PROGRAMM_ID" in quelle
       and aktualisierung.PROGRAMM_ID == "Rohrlaser Auslastung", "B3 Auslastung prüft und schreibt die feste Kennung")
pruefe("programm=PROGRAMM_ID" in (PROGRAMM / "rohrlaser" / "update.py").read_text("utf-8"),
       "B4 Kalkulation schreibt die feste Kennung in Update.json")
pruefe(orte.ORDNER_INSTALLIERT == "Rohrlaser Angebotskalkulation", "B5 Datenordner bleibt (keine Daten verschoben)")
iss = (PROGRAMM / "installer" / "rohrlaser.iss").read_text("utf-8")
pruefe('#define Name "NexTube"' in iss and "DefaultDirName={autopf}\\{#Ordner}" in iss
       and '#define Ordner "Rohrlaser Angebotskalkulation"' in iss and "{#AlterName}.lnk" in iss,
       "B6 Setup: Startmenü NexTube, Installationsordner bleibt, alte Verknüpfungen werden entfernt")
ico = Image.open(marke.ICON_ICO)
groessen = set(ico.info.get("sizes") or [])
pruefe({(16, 16), (32, 32), (48, 48), (256, 256)} <= groessen, f"B7 Icon mit 16–256 px ({sorted(groessen)})")
png = Image.open(marke.ICON_PNG)
pruefe(png.size == (512, 512) and png.mode == "RGBA" and png.getpixel((0, 0))[3] == 0,
       "B8 Icon 512 px mit durchsichtigen Ecken")
specs = {n: (PROGRAMM / n).read_text("utf-8") for n in ("rohrlaser.spec", "auslastung.spec")}
pruefe(all("nextube.ico" in t and '"rohrlaser/bilder"' in t for t in specs.values())
       and '"rohrlaser.marke"' in specs["auslastung.spec"]
       and re.search(r"--icon programm/rohrlaser/bilder/nextube.ico --name Lizenz-Werkzeug",
                     (WURZEL / ".github" / "workflows" / "paket.yml").read_text("utf-8")),
       "B9 Programmdateien und Lizenz-Werkzeug bekommen das Icon, Bilder liegen bei")

print()
if fehler:
    print(f"{len(fehler)} FEHLER")
    sys.exit(1)
print("Alle Prüfungen bestanden.")
