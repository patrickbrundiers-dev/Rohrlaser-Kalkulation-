"""Prüft den Löschschutz (Patrick 28.10.2026): Mit der Einstellung „Löschschutz“ lassen sich Angebote, die einmal
optimiert wurden, nicht mehr löschen (Angebotsliste und Datenbank); Positionen bleiben löschbar, der Admin darf das
Angebot nach Rückfrage löschen. Vorgabe aus. „von Hand“ zählt nur F9/Optimieren, nicht das automatische Optimieren.
Bestand: der Merker kommt aus 'optimiert_am'; er bleibt, auch wenn das Ergebnis verworfen wird; Kopien sind frei.

Aufruf: python tests/test_loeschschutz.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import angebot_fenster  # noqa: E402
from rohrlaser.datenbank import Datenbank, Loeschschutz  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNG, LOESCHSCHUTZ_AUS, LOESCHSCHUTZ_HAND, LOESCHSCHUTZ_JEDES  # noqa: E402


def ok(text):
    print("OK    ", text)


fragen, hinweise = [], []
antwort = {"ja": True}


class Kasten(QMessageBox):
    @staticmethod
    def question(_eltern, titel, text, *_):
        fragen.append(text)
        return QMessageBox.Yes if antwort["ja"] else QMessageBox.No

    @staticmethod
    def information(_eltern, titel, text, *_):
        hinweise.append(text)


angebot_fenster.QMessageBox = Kasten

app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
fenster = Hauptfenster(db, tmp, stumm=True)
liste = fenster.angebote
db.einstellung_setzen("auto_optimieren_bis", 0)      # hier steuert der Test, wann optimiert wird


def markieren(angebot_id):
    liste.neu_laden()
    m = liste.ansicht.model()
    for r in range(m.rowCount()):
        if liste._id(m.index(r, 0)) == angebot_id:
            liste.ansicht.setCurrentIndex(m.index(r, 0))
            return
    raise AssertionError(f"Angebot {angebot_id} nicht in der Liste")


def da(angebot_id):
    return db.angebot(angebot_id) is not None


def optimiert(automatisch):
    a = beispiel_angebot.anlegen(db)
    s = fenster.angebot_oeffnen(a)
    assert s.optimieren(automatisch=automatisch)
    fenster.angebot_schliessen(a)
    return a


# Vorgabe aus: optimiertes Angebot lässt sich wie bisher löschen
e = EINSTELLUNG["loeschschutz"]
assert e.vorgabe == LOESCHSCHUTZ_AUS and e.gruppe == "Angebot" and db.einstellung("loeschschutz") == LOESCHSCHUTZ_AUS
a = optimiert(False)
assert db.loeschschutz(a) is None
markieren(a)
liste.loeschen()
assert not da(a) and len(fragen) == 1 and not hinweise
ok("Vorgabe aus: optimiertes Angebot nach der Rückfrage gelöscht wie bisher")

# Nach jedem Optimieren: auch automatisch optimierte Angebote sind geschützt, nicht optimierte nicht
db.einstellung_setzen("loeschschutz", LOESCHSCHUTZ_JEDES)
frei = beispiel_angebot.anlegen(db)
assert db.loeschschutz(frei) is None
a = optimiert(True)
grund = db.loeschschutz(a)
assert grund and db.angebot(a)["nummer"] in grund and "Admin" in grund and "Abgelehnt" in grund, grund
try:
    db.angebot_loeschen(a)
    raise AssertionError("Datenbank hat ein geschütztes Angebot gelöscht")
except Loeschschutz as f:
    assert str(f) == grund
fragen.clear()
markieren(a)
liste.loeschen()
assert da(a) and not fragen and hinweise == [grund]
ok("Nach jedem Optimieren: automatisch optimiertes Angebot weder in der Liste noch in der Datenbank löschbar, "
   "Hinweis mit Grund und Ausweg")

# Positionen bleiben löschbar, der Schutz bleibt auch ohne Positionen und nach verworfenem Ergebnis
pos = [p["id"] for p in db.positionen(a)]
db.positionen_loeschen(pos[:1])
assert len(db.positionen(a)) == len(pos) - 1
db.ergebnis_speichern(a, None)
assert db.angebot(a)["optimiert_am"] is None and db.loeschschutz(a)
ok("Positionen weiter löschbar; Schutz bleibt nach verworfenem Schnittplan")

# Kopie und neue Fassung: noch nie optimiert, also frei
k = db.angebot_kopieren(a)
assert db.loeschschutz(k) is None
db.angebot_loeschen(k)
assert not da(k)
ok("Kopie eines geschützten Angebots ist frei (selbst noch nicht optimiert)")

# Admin: Rückfrage mit Grund, Nein lässt es stehen, Ja löscht
fenster.bereich.admin = True
hinweise.clear()
fragen.clear()
antwort["ja"] = False
markieren(a)
liste.loeschen()
assert da(a) and len(fragen) == 1 and "Admin-Rechten trotzdem löschen" in fragen[0] and not hinweise
antwort["ja"] = True
liste.loeschen()
assert not da(a)
fenster.bereich.admin = False
ok("Admin: Rückfrage „trotzdem löschen“, Nein behält, Ja löscht")

# Nur von Hand: automatisch optimiert = frei, F9 = geschützt
db.einstellung_setzen("loeschschutz", LOESCHSCHUTZ_HAND)
auto = optimiert(True)
assert db.loeschschutz(auto) is None
db.angebot_loeschen(auto)
hand = optimiert(False)
assert db.loeschschutz(hand)
s = fenster.angebot_oeffnen(frei)                    # erst automatisch, dann von Hand
assert s.optimieren(automatisch=True) and db.loeschschutz(frei) is None
assert s.optimieren(automatisch=False) and db.loeschschutz(frei)
fenster.angebot_schliessen(frei)
ok("Nach Optimieren von Hand: automatisches Optimieren schützt nicht, F9 schon")

# Bestand: Datei ohne die neuen Spalten, optimiert_am gesetzt -> beim Öffnen geschützt
db.einstellung_setzen("loeschschutz", LOESCHSCHUTZ_JEDES)
alt = beispiel_angebot.anlegen(db)
leer = beispiel_angebot.anlegen(db)
db.con.execute("UPDATE angebote SET optimiert_am='2026-10-01T08:30:00' WHERE id=?", (alt,))
db.con.commit()
fenster.close()
db.con.close()
con = sqlite3.connect(tmp / "rohrlaser.db")
con.execute("ALTER TABLE angebote DROP COLUMN optimiert_erstmals")
con.execute("ALTER TABLE angebote DROP COLUMN optimiert_hand")
con.commit()
con.close()
db = Datenbank(tmp / "rohrlaser.db")
assert "01.10.2026 08:30" in (db.loeschschutz(alt) or "") and db.loeschschutz(leer) is None
db.einstellung_setzen("loeschschutz", LOESCHSCHUTZ_HAND)
assert db.loeschschutz(alt)
ok("Bestand: einmal optimierte Angebote älterer Dateien sind geschützt (aus „Optimiert am“)")
print("Alle Prüfungen bestanden.")
