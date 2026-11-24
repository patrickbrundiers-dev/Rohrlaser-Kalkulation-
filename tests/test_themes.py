"""Themes, Schriftgröße, Dichte und Einblendungen (Layout-Plan D2, Plan B1/B2/B7).

T1 Hell + normal = bisheriges Stylesheet Zeichen für Zeichen (Hell sieht aus wie vorher);
T2 jede wichtige Textfarbe erreicht auf ihrer Fläche in jedem Theme WCAG AA (4,5 : 1);
T3 Dunkel setzt jede Farbe des Stylesheets um (keine helle Fläche bleibt stehen), Farbkonstanten werden umgefärbt;
T4 „Wie Windows“ folgt dem Farbschema des Systems; Schriftgröße auf 90–150 % begrenzt;
T5 Einstellungen Theme/Schrift/Dichte gelten nur für diesen Arbeitsplatz (nicht geteilt);
T6 Meldungen landen im Verlauf (höchstens 20), Einblendung nur außerhalb des Selbsttests.
Aufruf: python tests/test_themes.py
"""
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from rohrlaser import stil, teilen  # noqa: E402

fehler = []


def pruefe(bedingung, text):
    print(("OK    " if bedingung else "FEHLER") + "  " + text)
    if not bedingung:
        fehler.append(text)


# T1
pruefe(stil.stylesheet("Hell", "normal") == stil.STIL, "T1 Hell + normal = bisheriges Stylesheet")
pruefe(stil.umsetzen("color: #B42318;", "Hell") == "color: #B42318;", "T1 Hell setzt keine Farbe um")

# T2
for thema in ("Hell", "Dunkel", "Hoher Kontrast"):
    schlecht = [f"{n} {stil.kontrast(stil.umsetzen(v, thema), stil.umsetzen(h, thema)):.2f}"
                for v, h, n in stil.KONTRAST_PAARE
                if stil.kontrast(stil.umsetzen(v, thema), stil.umsetzen(h, thema)) < 4.5]
    pruefe(not schlecht, f"T2 {thema}: alle Textfarben mindestens 4,5 : 1 {schlecht or ''}")

# T3
dunkel = stil.stylesheet("Dunkel")
uebrig = sorted({h.upper() for h in re.findall(r"#[0-9A-Fa-f]{6}", stil.STIL)} - set(stil.UMSETZUNG["Dunkel"])
                - {"#5B8DB8", "#B07AA1", "#7F8A99"})       # Balkenfarben (stil.BALKEN_FARBEN) passen auf beide
pruefe(not uebrig, f"T3 Dunkel kennt jede Farbe des Stylesheets {uebrig or ''}")
pruefe("#FFFFFF" not in dunkel.upper().split("QPUSHBUTTON#PRIMAER")[0], "T3 Dunkel: keine weiße Fläche")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
konst = stil.farbe_fest("#FFFCF0")
schrift = app.font().pointSizeF()
pruefe(stil.anwenden(app, "Dunkel", 120, "kompakt") == "Dunkel", "T3 anwenden(Dunkel)")
pruefe(konst.name().upper() == stil.UMSETZUNG["Dunkel"]["#FFFCF0"], "T3 Farbkonstante umgefärbt")
pruefe(abs(app.font().pointSizeF() - schrift * 1.2) < 0.01, "T4 Schriftgröße 120 %")
l = QLabel()
l.setText("<span style='color:#B42318'>x</span>")
pruefe("#F28B82" in l.text(), "T3 Farben in Beschriftungen umgesetzt")
pruefe("QPushButton { padding: 2px 8px; }" in stil.aktuell(), "T3 Dichte kompakt im Stylesheet")
stil.anwenden(app, "Hell", 100, "normal")
pruefe(konst.name().upper() == "#FFFCF0" and stil.aktuell() == stil.STIL, "T3 zurück auf Hell")
app.setFont(app.font())

# T4
pruefe(stil.thema_aufloesen("Wie Windows", True) == "Dunkel" and stil.thema_aufloesen("Wie Windows", False) == "Hell",
       "T4 Wie Windows folgt dem System")
pruefe(stil.thema_aufloesen("Quatsch") == "Hell", "T4 unbekanntes Theme = Hell")

# T5
pruefe({"ansicht_thema", "ansicht_schrift", "ansicht_dichte"} <= teilen.LOKAL, "T5 Ansicht nur für diesen Arbeitsplatz")

# T6
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="themes_"))
(tmp / "Daten").mkdir()
db = Datenbank(tmp / "Daten" / "rohrlaser.db")
f = Hauptfenster(db, tmp, stumm=True)
for i in range(25):
    f.meldung(f"Meldung {i}")
pruefe(len(f.verlauf.eintraege) == 20 and f.verlauf.eintraege[0][1] == "Meldung 24", "T6 Verlauf: letzte 20, neueste oben")
pruefe(not f.einblendung.isVisible(), "T6 Selbsttest: keine Einblendung")
f.stumm = False
f.show()
f.meldung("Gespeichert.")
app.processEvents()
pruefe(f.einblendung.isVisible() and "Gespeichert." in f.einblendung.text.text(), "T6 Einblendung sichtbar")
f.einblendung.uhr.timeout.emit()
pruefe(not f.einblendung.isVisible(), "T6 Einblendung verschwindet von selbst")
f.stumm = True
f.close()
db.schliessen()

print()
print("Alles in Ordnung." if not fehler else f"{len(fehler)} Fehler.")
sys.exit(1 if fehler else 0)
