"""Zwischenspeicher der Stammdaten (Plan C2): kontext() und tabellen() werden nur neu gebaut, wenn sich Stammdaten
geändert haben, gleich über welchen Weg (Methoden, db.con direkt, andere Verbindung, Wiederherstellen); Änderungen an
Angeboten lassen ihn stehen. Die Optimierungsprüfung läuft je Neuladen nur einmal."""
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])


def ok(text):
    print("OK    ", text)


pfad = Path(tempfile.mkdtemp()) / "rohrlaser.db"
db = Datenbank(pfad)
k, tab = db.kontext(), db.tabellen()
assert db.kontext() is k and db.tabellen() is tab
aid = beispiel_angebot.anlegen(db)            # legt auch Kunde und Nummernzähler an (Stammdaten)
k, tab = db.kontext(), db.tabellen()
db.position_aendern(db.positionen(aid)[0]["id"], "stueck", 77)
assert db.kontext() is k and db.tabellen() is tab
ok("unverändert und nach Änderungen an Angeboten: derselbe Kontext, keine neue Abfrage")

pid = db.positionen(aid)[0]["profil_id"]                  # im Angebot verwendet
zid = db.con.execute("SELECT id FROM profile WHERE profil_id=?", (pid,)).fetchone()[0]
db.aendern("profile", zid, "endbeschnitt", 17.0)
k2 = db.kontext()
assert k2 is not k and k2.profile[pid]["endbeschnitt"] == 17.0
ok("Stammdaten über die Methoden geändert: Kontext neu")

with db.con:
    db.con.execute("UPDATE profile SET endbeschnitt=18 WHERE id=?", (zid,))
assert db.kontext().profile[pid]["endbeschnitt"] == 18
tab2 = db.tabellen()
db.einstellung_setzen("zuschnitt_puffer", 3.0)
assert db.tabellen() is not tab2 and db.tabellen()["einstellungen"]["zuschnitt_puffer"] == 3.0
ok("über db.con direkt und Einstellungen geändert: neu")

andere = sqlite3.connect(pfad)
with andere:
    andere.execute("UPDATE profile SET endbeschnitt=19 WHERE id=?", (zid,))
andere.close()
assert db.kontext().profile[pid]["endbeschnitt"] == 19
ok("andere Verbindung (anderes Programm) schreibt in die Datei: neu")

sicherung = db.sicherung()
db.aendern("profile", zid, "endbeschnitt", 25.0)
assert db.kontext().profile[pid]["endbeschnitt"] == 25.0
db.wiederherstellen(sicherung)
assert db.kontext().profile[pid]["endbeschnitt"] == 19
db.aendern("profile", zid, "endbeschnitt", 26.0)
assert db.kontext().profile[pid]["endbeschnitt"] == 26.0
ok("Wiederherstellen: Kontext aus der Sicherung, danach weiter aktuell")

f = Hauptfenster(db, stumm=True)
s = f.angebot_oeffnen(aid)
assert s.optimieren()
aufrufe = []
alt = rechnen.eingabe_kennung
rechnen.eingabe_kennung = lambda *a, **kw: aufrufe.append(1) or alt(*a, **kw)
try:
    s.neu_laden()
finally:
    rechnen.eingabe_kennung = alt
assert len(aufrufe) == 1, len(aufrufe)
assert s.stand_optimierung() == "aktuell"
db.aendern("profile", zid, "endbeschnitt", 30.0)
s.neu_laden()
assert s.stand_optimierung().startswith("VERALTET")
ok("Optimierungsstand je Neuladen einmal geprüft; Stammdaten geändert → veraltet")
print("OK: Zwischenspeicher")
