"""Prüfrundgang Oberfläche 13.11.2026 (Patrick: „Alle Empfehlungen“).

Prüft: 1 dreispaltig steht die linke Spalte nur beim Reiter Positionen voll, bei den breiten Reitern ein schmaler
Streifen, ein Klick klappt sie auf, zurück bei Positionen ist sie wieder da; 2 die Kurzfassung der Kalkulation steht
in der linken Spalte unter dem Titel; 3 nach dem Öffnen zeigt der Detailbereich die erste Position (nicht markiert);
4 im Schnittplan ist die 3D-Vorschau ohne gewählte Position nur eine Kopfzeile; 5 auf der Startseite bekommt die
Kundenspalte die freie Breite; 6 einfache Tabellen (Fertigung, Lager) haben Spalten von mindestens 72 px. Der
Verkaufspreis bleibt gleich.
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QHeaderView  # noqa: E402

app = QApplication(sys.argv[:1])

import beispiel_angebot  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.lager_seite import _tabelle  # noqa: E402


def ok(text):
    print("OK    ", text)


def warten():
    for _ in range(6):
        QApplication.processEvents()
    QTest.qWait(30)
    QApplication.processEvents()


po = Path(tempfile.mkdtemp(prefix="pruefrundgang_")) / "Rohrlaser-Angebotskalkulation"
(po / "Daten").mkdir(parents=True)
db = Datenbank(po / "Daten" / "rohrlaser.db")
db.einstellung_setzen("auto_optimieren_bis", 0)     # Preisvergleich ohne späten Optimierungslauf
f = Hauptfenster(db, po, stumm=True)
f.resize(1920, 1040)
f.show()
aid = beispiel_angebot.anlegen(db)
f.angebot_oeffnen(aid)
s = f.offen[aid]
warten()
preis = s._verkauf()
kb = s.kopf_bereich
r = s.reiter

# 1 linke Spalte nur bei Positionen
assert kb.seitlich and r.currentWidget() is s.pos_seite
assert s.oben_rahmen.isVisible() and not s.links_streifen.isVisible()
r.setCurrentWidget(s._nachkalk)
warten()
assert not s.oben_rahmen.isVisible() and s.links_streifen.isVisible(), "breiter Reiter: linke Spalte eingeklappt"
assert s.links_streifen.width() <= 40 and r.width() > 1200, r.width()
s.links_streifen.knopf.click()
warten()
assert s.oben_rahmen.isVisible() and not s.links_streifen.isVisible(), "Klick klappt auf"
r.setCurrentIndex(r.indexOf(s.teile_baum))
warten()
assert not s.oben_rahmen.isVisible(), "anderer breiter Reiter: wieder eingeklappt"
r.setCurrentWidget(s.pos_seite)
warten()
assert s.oben_rahmen.isVisible() and not s.links_streifen.isVisible()
f.resize(1366, 728)
warten()
assert not kb.seitlich and not s.links_streifen.isVisible()
r.setCurrentWidget(s._nachkalk)
warten()
assert s.oben_rahmen.isVisible() and not s.links_streifen.isVisible(), "zweispaltig nie eingeklappt"
r.setCurrentWidget(s.pos_seite)
f.resize(1920, 1040)
warten()
ok("dreispaltig: linke Spalte nur bei Positionen voll, sonst schmaler Streifen, Klick klappt auf")

# 2 Kurzfassung unter dem Titel
kb.kalkulation_aufklappen(False)
warten()
assert kb.kalk_kurz.isVisible() and kb.kalk_kurz.geometry().top() >= kb.kalk_knopf.geometry().bottom(), \
    (kb.kalk_kurz.geometry(), kb.kalk_knopf.geometry())
assert kb.kalk_kurz.width() > 300, kb.kalk_kurz.width()
ok("linke Spalte: Kurzfassung der Kalkulation in eigener Zeile unter dem Titel")

# 3 Detailbereich mit erster Position
# (ohne aktuelle Zeile und ohne Markierung, damit Entf o. Ä. nichts ungewollt trifft)
assert s.pos_detail.isVisible() and f"POS. {s.pos_modell.daten[0]['pos']}" in s.pos_detail.titel.text()
assert not s.pos_ansicht.currentIndex().isValid() and not s.pos_ansicht.selectionModel().selectedRows()
ok("Detailbereich zeigt nach dem Öffnen die erste Position, nichts markiert")

# 4 Schnittplan: leere 3D-Vorschau klein
r.setCurrentIndex(r.indexOf(s.teile_baum))
warten()
tb = s.teile_baum
tb.baum.setCurrentItem(None)
tb._vorschau(None)
warten()
oben, unten = tb.teiler.sizes()
assert unten <= 60 and oben > 5 * unten, tb.teiler.sizes()
r.setCurrentWidget(s.pos_seite)
ok("Schnittplan: ohne gewählte Position ist die 3D-Vorschau nur eine Kopfzeile")

# 5 Startseite
kopf = f.start.zuletzt_ansicht.horizontalHeader()
assert kopf.sectionResizeMode(1) == QHeaderView.Stretch and not kopf.stretchLastSection()
ok("Startseite: Kundenspalte bekommt die freie Breite")

# 6 einfache Tabellen
t = _tabelle([("A", "a"), ("B", "b")])
assert t.horizontalHeader().minimumSectionSize() == 72
ok("Fertigung/Lager: Spalten mindestens 72 px")

s.neu_laden()
warten()
assert s._verkauf() == preis, (s._verkauf(), preis)
ok("Rechnung unverändert")
print("Alle Tests OK")
