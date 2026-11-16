"""UI-Modernisierung U1/U2 (Patrick 12.11.2026): Seitenleiste, eine Menüzeile, Zukaufteile nur bei Bedarf.

Prüft: Seitenleiste mit Gruppen und allen festen Seiten, Klick wechselt die Seite, ausgeblendete Seiten (Versand)
verschwinden aus der Leiste, Breite automatisch/breit/schmal mit Speichern, Menü, offene Angebote und Suche in einer
Zeile (keine eigene Reiterzeile mehr über den Seiten), Dunkelmodus färbt die Leiste, Knopf und Reiter Zukaufteile nur
bei Angeboten mit Zukaufteilen.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])

import beispiel_angebot  # noqa: E402
from rohrlaser import navigation, stil  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


po = Path(tempfile.mkdtemp(prefix="navigation_")) / "Rohrlaser-Angebotskalkulation"
(po / "Daten").mkdir(parents=True)
db = Datenbank(po / "Daten" / "rohrlaser.db")
f = Hauptfenster(db, po, stumm=True)
f.resize(1920, 1040)
f.show()
QApplication.processEvents()

# ---------------------------------------------------------------- Seitenleiste
leiste = f.reiter.oben
assert isinstance(leiste, navigation.Seitenleiste)
texte = [leiste.tabText(i) for i in range(leiste.count())]
for t in ("Start", "Angebote", "Kunden", "Frachtkosten", "Einstellungen"):
    assert t in texte, (t, texte)
assert [g for g, t in leiste.titel.items() if t.isVisible()] == ["Arbeiten", "Auftrag", "Pflege"]
einst = leiste.knoepfe[texte.index("Einstellungen")]
assert einst.y() > max(k.y() for k, t in zip(leiste.knoepfe, texte) if t != "Einstellungen")     # ganz unten
QTest.mouseClick(leiste.knoepfe[texte.index("Kunden")], Qt.LeftButton)
assert f.reiter.currentWidget() is f.kunden and leiste.knoepfe[texte.index("Kunden")].isChecked()
f.reiter.setCurrentWidget(f.fracht)
assert leiste.currentIndex() == texte.index("Frachtkosten")
ok("Seitenleiste: alle festen Seiten in Gruppen, Einstellungen unten, Klick wechselt, Auswahl folgt")

db.einstellung_setzen("versand_aktiv", "nein")
f.versand_anwenden()
assert not leiste.knoepfe[texte.index("Versand")].isVisibleTo(leiste)
assert not leiste.isTabVisible(texte.index("Versand"))
db.einstellung_setzen("versand_aktiv", "ja")
f.versand_anwenden()
assert leiste.knoepfe[texte.index("Versand")].isVisibleTo(leiste)
ok("Ausgeschaltete Bereiche verschwinden aus der Leiste und kommen wieder")

# ---------------------------------------------------------------- Breite
assert leiste.modus == "automatisch" and leiste.breit and leiste.width() == navigation.BREIT
f.resize(1366, 728)
QApplication.processEvents()
assert not leiste.breit and leiste.width() == navigation.SCHMAL
assert all(k.toolButtonStyle() == Qt.ToolButtonIconOnly and k.toolTip() for k in leiste.knoepfe)
QTest.mouseClick(leiste.umschalter, Qt.LeftButton)
assert leiste.breit and leiste.modus == "breit" and db.einstellung(navigation.EINSTELLUNG) == "breit"
f.leiste_modus("schmal")
assert not leiste.breit and db.einstellung(navigation.EINSTELLUNG) == "schmal"
f.resize(1920, 1040)
QApplication.processEvents()
assert not leiste.breit                     # Wahl von Hand gilt auch im großen Fenster
f.leiste_modus("automatisch")
assert leiste.breit
ok("Breite: automatisch nach Fensterbreite, « / » und Menü Ansicht → Seitenleiste, Wahl wird gespeichert")

# ---------------------------------------------------------------- eine Menüzeile
aid = beispiel_angebot.anlegen(db)
f.angebot_oeffnen(aid)
s = f.offen[aid]
QApplication.processEvents()
zeile = f.reiter.unten
assert zeile.isVisible() and zeile.parent() is f.menue_ecke and f.menuBar().cornerWidget() is f.menue_ecke
oben = f.reiter.mapTo(f, f.reiter.rect().topLeft()).y()
assert zeile.mapTo(f, zeile.rect().bottomLeft()).y() <= oben, "Angebotszeile steht in der Menüzeile"
assert f.reiter.stapel.mapTo(f.reiter, f.reiter.stapel.rect().topLeft()).y() == 0, "keine Reiterzeile über der Seite"
assert f.suchknopf.isVisible() and f.suchknopf.mapTo(f, f.suchknopf.rect().topLeft()).x() > f.width() / 2
assert f.menuBar().height() < 45, f.menuBar().height()
f.reiter.setCurrentWidget(f.kunden)
QApplication.processEvents()
assert not zeile.isVisible()
f.reiter.setCurrentWidget(s)
ok("Menü, offene Angebote und Suche in einer Zeile; die Seiten beginnen direkt darunter")

# ---------------------------------------------------------------- Zukaufteile nur bei Bedarf
i = s.reiter.indexOf(s._zukauf_seite)
assert not s.zukauf_im_angebot() and not s.zukauf_knopf.isVisibleTo(s) and not s.reiter.isTabVisible(i)
db.position_neu(aid, dict(pos=90, art="Zukaufteil", bezeichnung="Sechskantschraube M8x20 (erfunden)", stueck=20,
                          ))
s.neu_laden()
QApplication.processEvents()
assert s.zukauf_im_angebot() and s.zukauf_knopf.isVisibleTo(s) and s.reiter.isTabVisible(i)
ok("Knopf und Reiter Zukaufteile nur, wenn das Angebot Zukaufteile enthält")

# ---------------------------------------------------------------- Dunkelmodus
stil.anwenden(app, "Dunkel")
f.setStyleSheet(stil.aktuell())
QApplication.processEvents()
assert "#0F141A" in stil.aktuell() and "#1B2735" not in stil.aktuell()
assert "#FEFEFE" in stil.aktuell()          # gewählter Eintrag bleibt weiß (nicht ins Dunkel umgesetzt)
stil.anwenden(app, "Hell")
ok("Dunkelmodus: Leiste dunkler als die Flächen, gewählter Eintrag weiß")
print("Alle Tests OK")
