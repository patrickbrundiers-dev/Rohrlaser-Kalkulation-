"""Designsystem „Klar“ (UI/UX Next Level, Freigabe Patrick 26.11.2026, Variante A): Bausteine und Werte.

B1 bausteine.py setzt keine eigene Farbe (nur Objektnamen), jedes Aussehen steht im Stylesheet;
B2 Status-Chips tragen immer ihr Zeichen (✓ ! ✕ i), unbekannte Stufe = neutral, Stufe lässt sich wechseln;
B3 jede Farbe der Chips und Hinweisbänder hat eine Entsprechung im Dunkelmodus und ist lesbar (4,5 : 1);
B4 Seitenkopf, Karte, Kennzahl und Hinweisband bauen sich auf und lassen sich füllen;
B5 Hell: Eingabefelder mit eigenem Rahmen, Pfeilbilder eingesetzt (kein Platzhalter bleibt stehen).
Aufruf: python tests/test_bausteine.py
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

from rohrlaser import bausteine, design, stil  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


quelle = (Path(bausteine.__file__)).read_text(encoding="utf-8")
pruefe(not re.findall(r"#[0-9A-Fa-f]{6}\b", quelle) and "setStyleSheet" not in quelle, "B1 keine eigenen Farben")
namen = ["seitenkopf", "seitentitel", "nebentext", "abschnitt", "karte", "kennzahl", "kennzahl_hervor",
         "kennzahl_gross", "kennzahltitel"] + [f"chip_{s}" for s in design.CHIPS] + \
        [f"hinweis_{s}" for s in ("ok", "warnung", "fehler", "info")]
fehlt = [n for n in namen if "#" + n + " " not in stil.STIL and "#" + n + "\n" not in stil.STIL]
pruefe(not fehlt, f"B1 jeder Objektname hat eine Regel im Stylesheet {fehlt or ''}")

c = bausteine.chip("Optimiert", "ok")
pruefe(c.text() == "✓ Optimiert" and c.objectName() == "chip_ok", "B2 Chip ok mit Haken")
pruefe(bausteine.chip("PLZ fehlt", "warnung").text() == "! PLZ fehlt", "B2 Chip Warnung mit !")
pruefe(bausteine.chip("x", "quatsch").objectName() == "chip_neutral", "B2 unbekannte Stufe = neutral")
bausteine.chip_setzen(c, "Nicht optimiert", "warnung")
pruefe(c.text() == "! Nicht optimiert" and c.objectName() == "chip_warnung", "B2 Stufe wechseln")

dunkel = stil.UMSETZUNG["Dunkel"]
farben = {h.upper() for n in namen for h in re.findall(r"#" + n + r"\b[^}]*}", stil.STIL) for h in
          re.findall(r"#[0-9A-Fa-f]{6}", h)}
pruefe(farben and not (farben - set(dunkel)), f"B3 Dunkel kennt alle Bausteinfarben {sorted(farben - set(dunkel))}")
for thema in ("Hell", "Dunkel", "Hoher Kontrast"):
    schlecht = [s for s, (t, f, _z) in design.CHIPS.items()
                if stil.kontrast(stil.umsetzen(t, thema), stil.umsetzen(f, thema)) < 4.5]
    pruefe(not schlecht, f"B3 {thema}: Chips lesbar {schlecht or ''}")

kopf = bausteine.seitenkopf("Start", "Donnerstag", [bausteine.knopf("Neues Angebot", haupt=True)])
pruefe(kopf.titel.objectName() == "seitentitel" and kopf.aktionen.count() == 1
       and kopf.aktionen.itemAt(0).widget().objectName() == "primaer", "B4 Seitenkopf mit Hauptknopf")
k = bausteine.karte("Preisaufbau", [QPushButton("Kostenwasserfall")])
pruefe(k.objectName() == "karte" and k.titel.text() == "Preisaufbau" and k.inhalt is not None, "B4 Karte")
z = bausteine.kennzahl("Verkaufspreis", "781,57 €", hervor=True)
z.setzen("800,00 €", "Marge 9,1 %")
pruefe(z.objectName() == "kennzahl_hervor" and z.wert.text() == "800,00 €" and not z.unter.isHidden(),
       "B4 Kennzahl hervorgehoben, setzen")
h = bausteine.hinweisband("<b>Stammdaten sind Beispielwerte.</b>", "warnung", "Einstellungen öffnen", schliessen=True)
pruefe(h.objectName() == "hinweis_warnung" and h.knopf.text() == "Einstellungen öffnen", "B4 Hinweisband")

hell = stil.stylesheet("Hell")
pruefe(hell.startswith(stil.STIL) and "QComboBox::down-arrow" in hell and "{PFEIL" not in hell
       and "{" + "HAKEN}" not in hell, "B5 Hell: Eingabefelder, Pfeile eingesetzt")
pruefe("{PFEIL" not in stil.stylesheet("Dunkel"), "B5 Dunkel: Pfeile eingesetzt")
pruefe(design.ECKE < design.ECKE_KARTE and design.UI_KLEIN < design.UI_TEXT < design.UI_ABSCHNITT < design.UI_TITEL,
       "B5 Ecken und Schriftstufen aufsteigend")

if fehler:
    print(f"\n{len(fehler)} Fehler")
    sys.exit(1)
print("Alle Tests OK")
