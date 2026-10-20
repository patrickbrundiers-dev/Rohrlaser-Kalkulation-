"""Prüft, dass die Bedienungsanleitung (anleitung/erzeuge_anleitung.py) mit dem Programm Schritt hält:
jede Stammdatentabelle, jede Einstellung, jedes sichtbare Eingabefeld der Positionen und des Angebotskopfs,
jeder Reiter und jeder Knopf des Programms muss im Text der Anleitung vorkommen. Kommt etwas Neues ins
Programm, schlägt dieser Test fehl, bis die Anleitung ergänzt ist.

Aufruf: python tests/test_anleitung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import re
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton  # noqa: E402

from rohrlaser.angebot import KOPF, POSITIONEN  # noqa: E402
from rohrlaser.angebot_fenster import SICHTBAR  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.rechnen import KOSTENARTEN  # noqa: E402
from rohrlaser.staffel_seite import ERGEBNIS  # noqa: E402
from rohrlaser.staffeln import STUFE_FELDER  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNGEN, TABELLEN  # noqa: E402

QUELLE = (HIER.parent / "anleitung" / "erzeuge_anleitung.py").read_text(encoding="utf-8")


def kern(text):
    """'Schneidzeit manuell je Teil [s]' -> 'Schneidzeit manuell je Teil'; 'Zusatzarbeiten …' -> 'Zusatzarbeiten'."""
    t = re.sub(r"\s*[\[(].*?[\])]", "", text).replace("…", "").replace("&", "").strip()
    return re.sub(r"\s+", " ", t)


def kommt_vor(text):
    norm = re.sub(r"</?[a-zA-Z][^<>\n]*>", "", QUELLE).replace("&nbsp;", " ").replace("&", " ")
    norm = re.sub(r'"\s*\n\s*"', "", norm)          # im Quelltext umgebrochene Zeichenketten
    norm = re.sub(r"\s+", " ", re.sub(r"\s*\[[^\[\]\n]{1,12}\]", "", norm))     # Einheiten [mm], [€] …
    return kern(text).lower() in norm.lower()


pruefen = []
pruefen += [("Stammdatentabelle", t.titel) for t in TABELLEN]
pruefen += [("Feld in " + t.titel, f.titel) for t in TABELLEN for f in t.felder]
pruefen += [("Einstellung", e.titel) for e in EINSTELLUNGEN]
pruefen += [("Kostenart", t) for t, _, _ in KOSTENARTEN]
pruefen += [("Angebotskopf", f.titel) for f in KOPF]
pruefen += [("Feld der Staffeln", f.titel) for f in STUFE_FELDER]
pruefen += [("Ergebnis der Staffeln", t) for _, t, _, _ in ERGEBNIS if t[:1].isupper()]
pruefen += [("Position", f.titel) for f in POSITIONEN.felder if f.name in SICHTBAR]

app = QApplication.instance() or QApplication([])
db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
fenster = Hauptfenster(db, stumm=True)
seite = fenster.angebot_oeffnen(db.angebot_neu())
for i in range(fenster.reiter.count()):
    text = fenster.reiter.tabText(i)
    if not text.startswith("Angebot "):
        pruefen.append(("Reiter", text))
pruefen += [("Reiter im Angebot", seite.reiter.tabText(i)) for i in range(seite.reiter.count())]
pruefen += [("Unterreiter der Einstellungen", fenster.bereich.unter.tabText(i))
            for i in range(fenster.bereich.unter.count())]
for w in fenster.findChildren(QPushButton) + fenster.findChildren(QCheckBox):
    if w.text():
        pruefen.append(("Knopf", w.text()))
fenster.close()
db.schliessen()

fehlt = sorted({f"{art}: {text}" for art, text in pruefen if not kommt_vor(text)})
assert not fehlt, "In der Bedienungsanleitung fehlt:\n  " + "\n  ".join(fehlt)
print(f"OK: Bedienungsanleitung beschreibt alle {len(set(t for _, t in pruefen))} Tabellen, Felder, Reiter und Knöpfe")
