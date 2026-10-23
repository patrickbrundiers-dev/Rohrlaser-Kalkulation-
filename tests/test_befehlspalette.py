"""Befehlspalette Strg+K (Layout-Plan L20): findet Angebote, Kunden, Profile, Einstellungen und Befehle und führt sie aus."""
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser.befehlspalette import Eintrag, eintraege, treffer  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


# Suche ohne Fenster: alle Wörter müssen vorkommen, Treffer am Titelanfang zuerst
liste = [Eintrag("Befehl", "Optimieren", "Menü Bearbeiten", None), Eintrag("Profil", "QR 40x40x3", "", None),
         Eintrag("Profil", "RE 60x40x3", "", None), Eintrag("Einstellung", "Gewinn", "Vorgaben, Gruppe Kalkulation", None),
         Eintrag("Einstellung", "Aufschlag des Lieferanten (Gewinn)", "Vorgaben, Gruppe Blech-Richtpreis", None)]
assert [e.titel for e in treffer(liste, "gewinn")] == ["Gewinn", "Aufschlag des Lieferanten (Gewinn)"]
assert [e.titel for e in treffer(liste, "40x3 re")] == ["RE 60x40x3"]
assert [e.art for e in treffer(liste, "")] == ["Befehl"]
assert treffer(liste, "gibtsnicht") == []
ok("Suche: alle Wörter, Titelanfang zuerst, leere Suche zeigt Befehle")

db = Datenbank(Path(tempfile.mkdtemp()) / "rohrlaser.db")
f = Hauptfenster(db, stumm=True)
aid = beispiel_angebot.anlegen(db)
nummer = db.angebot(aid)["nummer"]
alle = eintraege(f)
arten = {e.art for e in alle}
assert {"Reiter", "Befehl", "Angebot", "Kunde", "Profil", "Werkstoff", "Einstellung"} <= arten, arten
assert any(e.titel == "Optimieren" and "F9" in e.zusatz for e in alle)
ok(f"{len(alle)} Ziele: Reiter, Menübefehle mit Tastenkürzel, Angebote, Kunden, Profile, Werkstoffe, Einstellungen")

d = f.befehlspalette()
d.suche.setText(nummer)
assert d.liste.count() >= 1 and d.liste.currentItem().data(Qt.UserRole).art == "Angebot"
QTest.keyClick(d.suche, Qt.Key_Return)
assert f.reiter.currentWidget() is f.offen[aid]
ok("Angebotsnummer tippen, Enter: Angebot öffnet")

d = f.befehlspalette()
d.suche.setText("gewinn")
e = d.ausfuehren(d.liste.currentItem())
assert e.art == "Einstellung" and f.reiter.currentWidget() is f.bereich
assert f.bereich.unter.suche.text() == "Gewinn"
ok("Einstellung: öffnet die Einstellungen mit gefilterter Suche")

d = f.befehlspalette()
d.suche.setText("QR 40x40x3")
QTest.keyClick(d.suche, Qt.Key_Down)
QTest.keyClick(d.suche, Qt.Key_Up)
e = d.ausfuehren(d.liste.currentItem())
seite = next(s for s in f.seiten if s.t.name == "profile")
assert e.art == "Profil" and seite.suche.text() == "QR 40x40x3"
ok("Profil: ↑/↓ wählt, Stammdaten Profile gefiltert")

kunde = db.zeilen("kunden")[0]
d = f.befehlspalette()
d.suche.setText(str(kunde["name"]))
e = next(d.liste.item(i).data(Qt.UserRole) for i in range(d.liste.count())
         if d.liste.item(i).data(Qt.UserRole).art == "Kunde")
e.aktion()
assert f.reiter.currentWidget() is f.kunden
ok("Kunde: Reiter Kunden mit dem Kunden")
print("OK: Befehlspalette")
