"""Linke Spalte der Angebotsseite einklappbar (Patrick 15.11.2026: „Kann man die Ansicht im Angebot umstellen, dass
Angebotskopf, Kalkulation und Fracht nicht dauerhaft daneben stehen? Nimmt viel Platz weg“ – „Alle Empfehlungen“).

Prüft: dreispaltig ist die linke Spalte auch beim Reiter Positionen zunächst eingeklappt (schmaler Streifen), die
Positionen werden breiter; » bzw. Strg+Umschalt+L klappt auf, « wieder ein, die Wahl gilt für alle Angebote; ein
Angebot ohne Kunde öffnet die Spalte; der Streifen zeigt Nummer und Kunde und einen Warnpunkt bei abweichender
Kalkulation; zweispaltig ändert sich nichts; der Verkaufspreis bleibt gleich.
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
from rohrlaser.angebot_fenster import LINKS_OFFEN_EINSTELLUNG  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


def warten():
    for _ in range(6):
        QApplication.processEvents()
    QTest.qWait(30)
    QApplication.processEvents()


po = Path(tempfile.mkdtemp(prefix="links_einklappen_")) / "Rohrlaser-Angebotskalkulation"
(po / "Daten").mkdir(parents=True)
db = Datenbank(po / "Daten" / "rohrlaser.db")
db.einstellung_setzen("auto_optimieren_bis", 0)
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

# 1 Vorgabe: auch bei Positionen eingeklappt, Positionen breiter
assert kb.seitlich and r.currentWidget() is s.pos_seite
assert db.einstellung(LINKS_OFFEN_EINSTELLUNG) is None
assert not s.oben_rahmen.isVisible() and s.links_streifen.isVisible(), "Vorgabe: eingeklappt"
breit_zu = s.pos_seite.width()
assert s.links_streifen.width() <= 40
ok(f"Reiter Positionen: linke Spalte eingeklappt, Positionen {breit_zu} px breit")

# 2 Streifen zeigt Nummer und Kunde
info, warnungen = kb.streifen_info()
assert s.kopf["nummer"] in info and s.kopf["kunde"] in info, info
assert s.kopf["nummer"] in s.links_streifen.text() and "Angebotskopf" in s.links_streifen.text()
assert not s.links_streifen.warnpunkt.isVisible(), warnungen
ok(f"Streifen: {s.links_streifen.text()!r}")

# 3 » klappt auf und merkt es; « klappt ein und merkt es
s.links_streifen.knopf.click()
warten()
assert s.oben_rahmen.isVisible() and not s.links_streifen.isVisible()
assert db.einstellung(LINKS_OFFEN_EINSTELLUNG) is True
assert kb.einklappen_knopf.isVisible()
assert s.pos_seite.width() < breit_zu - 300, (s.pos_seite.width(), breit_zu)
r.setCurrentWidget(s._nachkalk)
warten()
assert not s.oben_rahmen.isVisible(), "breiter Reiter: weiter eingeklappt"
r.setCurrentWidget(s.pos_seite)
warten()
assert s.oben_rahmen.isVisible(), "gemerkt: offen"
kb.einklappen_knopf.click()
warten()
assert not s.oben_rahmen.isVisible() and s.links_streifen.isVisible()
assert db.einstellung(LINKS_OFFEN_EINSTELLUNG) is None
ok("» klappt auf, « klappt ein, Wahl gemerkt")

# 4 Strg+Umschalt+L
assert f.links_aktion.shortcut().toString() == "Ctrl+Shift+L"
f.links_aktion.trigger()
warten()
assert s.oben_rahmen.isVisible() and db.einstellung(LINKS_OFFEN_EINSTELLUNG) is True
f.links_aktion.trigger()
warten()
assert not s.oben_rahmen.isVisible() and db.einstellung(LINKS_OFFEN_EINSTELLUNG) is None
ok("Strg+Umschalt+L klappt auf und ein")

# 5 gilt für alle Angebote: zweites Angebot auch eingeklappt; neues Angebot ohne Kunde offen
aid2 = beispiel_angebot.anlegen(db)
f.angebot_oeffnen(aid2)
warten()
s2 = f.offen[aid2]
assert not s2.oben_rahmen.isVisible() and s2.links_streifen.isVisible()
aid3 = db.angebot_neu() if hasattr(db, "angebot_neu") else None
if aid3 is None:
    aid3 = beispiel_angebot.anlegen(db)
    db.angebot_aendern(aid3, "kunde", None)
    db.angebot_aendern(aid3, "kundennr", None)
f.angebot_oeffnen(aid3)
warten()
s3 = f.offen[aid3]
assert s3.oben_rahmen.isVisible() and not s3.links_streifen.isVisible(), "ohne Kunde: Spalte offen"
assert db.einstellung(LINKS_OFFEN_EINSTELLUNG) is None, "automatisches Öffnen wird nicht gemerkt"
ok("Wahl gilt für alle Angebote; Angebot ohne Kunde öffnet die Spalte")

# 6 Warnpunkt bei abweichender Kalkulation
f.reiter.setCurrentWidget(s)
warten()
kb._n_abweichend = 2
s.streifen_aktualisieren()
warten()
assert s.links_streifen.warnpunkt.isVisible() and "2 Kalkulationswerte" in s.links_streifen.warnpunkt.toolTip()
kb.kundenhinweis_setzen("Nur mit Abnahmeprüfzeugnis 3.1")
assert "Abnahmeprüfzeugnis" in s.links_streifen.warnpunkt.toolTip()
kb._n_abweichend = 0
kb.kundenhinweis_setzen("")
assert not s.links_streifen.warnpunkt.isVisible()
ok("Warnpunkt bei Kundenhinweis und abweichender Kalkulation")

# 7 zweispaltig unverändert, kein Streifen; Strg+Umschalt+L nur Hinweis
f.resize(1366, 728)
warten()
assert not kb.seitlich and not s.links_streifen.isVisible() and s.oben_rahmen.isVisible()
assert not kb.einklappen_knopf.isVisible()
assert f.angebot_links_umschalten() is False
assert db.einstellung(LINKS_OFFEN_EINSTELLUNG) is None
f.resize(1920, 1040)
warten()
assert kb.seitlich and not s.oben_rahmen.isVisible()
ok("zweispaltig unverändert (Kopf über den Positionen)")

# 8 Preis unverändert
assert abs(s._verkauf() - preis) < 0.005, (s._verkauf(), preis)
ok(f"Verkaufspreis unverändert {preis:.2f} €")
print("Alle Prüfungen bestanden.")
