"""UI-Modernisierung U3 (Patrick 12.11.2026): dreispaltige Angebotsseite.

Prüft: ab 1700 px Seitenbreite stehen Angebotskopf, Kalkulation und Fracht als linke Spalte neben den Positionen
(Kopf aufgeklappt, Felder untereinander, kein waagrechter Bildlauf), darunter wie bisher über den Positionen; die
Wahl im Menü Ansicht → Angebotsseite (automatisch / drei / zwei) wird gespeichert und gilt sofort für offene
Angebote; Eingaben in der linken Spalte speichern wie vorher; der Verkaufspreis ändert sich durch das Umstellen nicht.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])

import beispiel_angebot  # noqa: E402
from rohrlaser import angebot_fenster  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def warten():
    QApplication.processEvents()
    QTest.qWait(30)
    QApplication.processEvents()


po = Path(tempfile.mkdtemp(prefix="drei_spalten_")) / "Rohrlaser-Angebotskalkulation"
(po / "Daten").mkdir(parents=True)
db = Datenbank(po / "Daten" / "rohrlaser.db")
db.einstellung_setzen("auto_optimieren_bis", 0)     # kein automatisches Optimieren mitten im Preisvergleich
f = Hauptfenster(db, po, stumm=True)
f.resize(1920, 1040)
f.show()
aid = beispiel_angebot.anlegen(db)
f.angebot_oeffnen(aid)
s = f.offen[aid]
warten()
kb = s.kopf_bereich
preis = s._verkauf()
assert preis and preis > 0, preis

# ---------------------------------------------------------------- 1920: drei Spalten
assert s.width() >= angebot_fenster.DREI_SPALTEN_AB, s.width()
assert kb.seitlich and s.oben_rahmen.parent() is s.mitte and s.mitte.indexOf(s.oben_rahmen) == 0
assert s.teiler.count() == 1, "über den Positionen steht nichts mehr"
links, mitte = s.mitte.sizes()
assert angebot_fenster.LINKS_BREIT <= links <= 520 and mitte > 800, s.mitte.sizes()
assert kb.kopf_offen(), "linke Spalte: Angebotskopf aufgeklappt"
for offen in (False, True):
    kb.kalkulation_aufklappen(offen)
    kb.fracht_aufklappen(offen)
    warten()
    assert s.oben_rahmen.horizontalScrollBar().maximum() == 0, "kein waagrechter Bildlauf in der linken Spalte"
# Felder untereinander: Kunde unter der Kundennummer, Gruppen der Kalkulation in einer Spalte, Fracht unter Kalkulation
b_nr, w_nr = kb._kopf_paare["kundennr"]
b_kd, w_kd = kb._kopf_paare["kunde"]
assert w_kd.y() > w_nr.y() and abs(w_kd.x() - w_nr.x()) < 3
assert kb._spalten_gruppen == 1 and len({g.x() for g in kb.gruppen_boxen}) == 1
assert kb.fracht_karte.y() > kb.kalk_karte.y() and kb.fracht_karte.x() == kb.kalk_karte.x()
# die Positionen beginnen oben auf der Seite (gleiche Höhe wie der Kopf links)
oben_pos = s.reiter.mapTo(s, s.reiter.rect().topLeft()).y()
assert oben_pos < 120, oben_pos
ok("1920 px: Kopf, Kalkulation und Fracht als linke Spalte, untereinander, ohne waagrechten Bildlauf")

# Eingabe in der linken Spalte speichert wie vorher
w = kb.felder["bemerkung"]
w.setText("Test drei Spalten (erfunden)")
w.editingFinished.emit()
warten()
assert db.angebot(aid)["bemerkung"] == "Test drei Spalten (erfunden)"
ok("Eingaben in der linken Spalte werden gespeichert")

# ---------------------------------------------------------------- 1366: zwei Spalten wie bisher
f.resize(1366, 728)
warten()
assert not kb.seitlich and s.oben_rahmen.parent() is s.teiler and s.mitte.count() == 1
assert kb._kopf_schmal is False and kb._erweitert_spalten == 3
assert s.oben_rahmen.horizontalScrollBar().maximum() == 0
ok("1366 px: Kopf wieder über den Positionen, Felder nebeneinander")

# ---------------------------------------------------------------- Wahl im Menü Ansicht
f.resize(1920, 1040)
warten()
assert kb.seitlich
f.angebot_spalten("zwei")
warten()
assert not kb.seitlich and db.einstellung(angebot_fenster.DREI_SPALTEN_EINSTELLUNG) == "zwei"
f.resize(1366, 728)
warten()
f.angebot_spalten("drei")
warten()
assert kb.seitlich and db.einstellung(angebot_fenster.DREI_SPALTEN_EINSTELLUNG) == "drei"
f.angebot_spalten("automatisch")
warten()
assert not kb.seitlich and not db.einstellung(angebot_fenster.DREI_SPALTEN_EINSTELLUNG)
texte = [a.text() for a in f.angebot_spalten_wahl.actions()]
assert len(texte) == 3 and texte[1].startswith("Drei Spalten"), texte
ok("Ansicht → Angebotsseite: automatisch / drei / zwei Spalten, gespeichert, gilt sofort")

# ---------------------------------------------------------------- Rechnung unverändert
s.neu_laden()
warten()
assert s._verkauf() == preis, (s._verkauf(), preis)
ok("Umstellen ändert nichts an der Rechnung")
print("Alle Tests OK")
