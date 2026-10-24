"""Symbole an Hauptaktionen (Layout-Plan L19): jedes Symbol zeichnet, Knöpfe bekommen es über ihren Text."""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import symbole  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


assert set(symbole.KNOPF_SYMBOL.values()) <= set(symbole.PFADE)
for name in symbole.PFADE:
    bild = symbole.symbol(name).pixmap(16, 16).toImage()
    gesetzt = sum(1 for x in range(16) for y in range(16) if bild.pixelColor(x, y).alpha() > 0)
    assert 8 < gesetzt < 220, (name, gesetzt)            # etwas gezeichnet, aber keine volle Fläche
ok(f"{len(symbole.PFADE)} Symbole zeichnen, alle Knopftexte haben ein vorhandenes Symbol")

weiss = symbole.symbol("optimieren", symbole.WEISS).pixmap(16, 16).toImage()
farben = {weiss.pixelColor(x, y).name() for x in range(16) for y in range(16) if weiss.pixelColor(x, y).alpha() == 255}
assert farben == {"#ffffff"}, farben
ok("Hauptknöpfe: Symbol in Weiß")

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
s = f.angebot_oeffnen(beispiel_angebot.anlegen(db))
knoepfe = {b.text(): b for b in s.findChildren(QPushButton)}
for text in ("Neue Position", "STEP importieren …", "Optimieren", "Angebot (PDF)", "Ausgaben"):
    assert not knoepfe[text].icon().isNull(), text
start = {b.text(): b for b in f.start.findChildren(QPushButton)}
assert not start["Neues Angebot"].icon().isNull() and not start["Datensicherung erstellen"].icon().isNull()
assert any(not a.icon().isNull() for a in s.weitere.menu().actions() if a.text() == "Kalkulation (PDF)")
ok("Angebot, Startseite und Menü Ausgaben mit Symbolen")
print("OK: Symbole")
