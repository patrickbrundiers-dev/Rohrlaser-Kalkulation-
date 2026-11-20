"""Sicherung mit PostgreSQL-Abbild und Angebotsdokumenten (Datenbank-Auftrag 19.11.2026, Schritt 4).

Prüft:
- jede Sicherung bekommt neben der SQLite-Datei ein geprüftes PostgreSQL-Abbild (.pgdump) mit allen Tabellen;
- aus dem Abbild lässt sich wiederherstellen (gleiche Daten, alter Stand vorher gesichert); ein beschädigtes Abbild
  wird abgewiesen, ohne etwas zu ändern;
- Angebotsdokumente: Spiegel der Ablage (nur Änderungen), ältere Stände bei Änderung/Löschung, Liste je Sicherung;
  zurückholen legt fehlende zurück, ersetzt abweichende (vorher beiseitegelegt), lässt neuere Dateien in Ruhe;
- Einstellung sicherung_dokumente = nein: keine Dokumente; Sicherung im Hintergrund nimmt die Dokumente mit;
- Aufräumen löscht Abbild und Dokumentenliste mit der Sicherung;
- Wiederherstellen-Dialog zeigt Abbild/Dokumente und bietet den Haken für die Dokumente an.

Aufruf: python tests/test_sicherung_abbild.py
"""
import datetime
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import db_verbindung, dokumente_sicherung, pg_abbild  # noqa: E402
from rohrlaser.datenbank import Datenbank, SicherungFehler  # noqa: E402


class _EigeneNamen:
    """Merkt sich die Zufallsnamen der eigenen Probe-Datenbanken (abbild_xxxx): andere Tests im selben Prüfserver
    legen gleichzeitig eigene an, gezählt werden nur die dieses Tests."""
    def __init__(self, echt):
        self.echt, self.namen = echt, []

    def token_hex(self, n):
        t = self.echt.token_hex(n)
        self.namen.append(f"abbild_{t}")
        return t


eigene_proben = _EigeneNamen(pg_abbild.secrets)
pg_abbild.secrets = eigene_proben


def ok(text):
    print("OK     " + text)


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "Daten" / "rohrlaser.db")
if db_verbindung.ist_sqlite(db.con):
    print("übersprungen: nur mit PostgreSQL (werkzeuge/mit_pg.py)")
    sys.exit(0)
aid = db.angebot_neu(dict(kunde="Abbild GmbH"))
db.position_neu(aid, dict(stueck=7, bezeichnung="Rohr 1"))
ablage = tmp / "Ablage"
(ablage / "2026-00001 Abbild GmbH" / "STEP").mkdir(parents=True)
a_pdf = ablage / "2026-00001 Abbild GmbH" / "2026-00001 Angebot.pdf"
a_pdf.write_bytes(b"%PDF Stand 1")
a_step = ablage / "2026-00001 Abbild GmbH" / "STEP" / "teil.stp"
a_step.write_bytes(b"ISO-10303-21; Stand 1")
(ablage / "2026-00001 Abbild GmbH" / "~$Angebot.docx").write_bytes(b"Sperrdatei")
db.dokumente_ablage = lambda: ablage

s1 = db.sicherung()
info1 = __import__("json").loads(s1.with_suffix(".json").read_text(encoding="utf-8"))
abbild1 = pg_abbild.pfad(s1)
assert abbild1.is_file() and info1.get("pg_abbild") == abbild1.name, info1
enthalten = pg_abbild.tabellen_mit_daten(abbild1)
assert {"angebote", "positionen", "kunden", "einstellungen"} <= enthalten, enthalten
assert "Angebotsdokumente gesichert: 2 Dateien (2 neu" in info1.get("dokumente", ""), info1
liste1 = dokumente_sicherung.liste(s1)
assert set(liste1["dateien"]) == {"2026-00001 Abbild GmbH/2026-00001 Angebot.pdf",
                                   "2026-00001 Abbild GmbH/STEP/teil.stp"}, "Sperrdateien bleiben draußen"
spiegel = s1.parent / dokumente_sicherung.ORDNER / dokumente_sicherung.AKTUELL
assert (spiegel / "2026-00001 Abbild GmbH" / "2026-00001 Angebot.pdf").read_bytes() == b"%PDF Stand 1"
ok("Sicherung: SQLite-Datei + geprüftes PostgreSQL-Abbild (alle Tabellen) + Spiegel der Angebotsdokumente mit Liste")

# ------------------------------------------------------------------ Änderungen an den Dokumenten
time.sleep(0.05)
a_pdf.write_bytes(b"%PDF Stand 2 (laenger)")
os.utime(a_pdf, (time.time() + 10, time.time() + 10))
a_step.unlink()
neu = ablage / "2026-00002 Neu" / "neu.pdf"
neu.parent.mkdir()
neu.write_bytes(b"%PDF neu")
s2 = db.sicherung()
info2 = __import__("json").loads(s2.with_suffix(".json").read_text(encoding="utf-8"))
assert "(1 neu, 1 geändert)" in info2["dokumente"], info2["dokumente"]
alt = s1.parent / dokumente_sicherung.ORDNER / dokumente_sicherung.ALT / datetime.date.today().isoformat()
assert (alt / "2026-00001 Abbild GmbH" / "2026-00001 Angebot.pdf").read_bytes() == b"%PDF Stand 1"
assert (alt / "2026-00001 Abbild GmbH" / "STEP" / "teil.stp").is_file(), "gelöschte Datei: Stand aufgehoben"
s3 = db.sicherung()
info3 = __import__("json").loads(s3.with_suffix(".json").read_text(encoding="utf-8"))
assert "(0 neu, 0 geändert)" in info3["dokumente"], "unverändert: nichts kopiert"
ok("Spiegel: nur Änderungen, geänderte und gelöschte Dateien behalten ihren alten Stand")

# ------------------------------------------------------------------ Dokumente zurückholen (Stand Sicherung 1)
z = dokumente_sicherung.zurueckholen(s1, ablage)
assert (z["zurueck"], z["ersetzt"], z["fehlt"]) == (1, 1, []), z
assert a_pdf.read_bytes() == b"%PDF Stand 1" and a_step.read_bytes() == b"ISO-10303-21; Stand 1"
assert neu.read_bytes() == b"%PDF neu", "später entstandene Datei bleibt"
beiseite = list((ablage / dokumente_sicherung.VOR_WIEDERHERSTELLUNG).rglob("2026-00001 Angebot.pdf"))
assert len(beiseite) == 1 and beiseite[0].read_bytes() == b"%PDF Stand 2 (laenger)", "abweichender Stand beiseite"
assert "1 zurückgelegt, 1 ersetzt" in dokumente_sicherung.text(z)
z = dokumente_sicherung.zurueckholen(s1, ablage)
assert z["unveraendert"] == 2 and z["zurueck"] == z["ersetzt"] == 0
assert all(not r.startswith(dokumente_sicherung.VOR_WIEDERHERSTELLUNG) for r in dokumente_sicherung.bestand(ablage))
ok("Dokumente zurückholen: fehlende zurück, abweichende ersetzt (vorher beiseite), neuere unberührt, zweites Mal "
   "nichts zu tun")

# ------------------------------------------------------------------ Wiederherstellen aus dem Abbild
db.angebot_aendern(aid, "kunde", "Später GmbH")
db.position_neu(aid, dict(stueck=99))
info, vorher = db.wiederherstellen(abbild1)
assert db.angebot(aid)["kunde"] == "Abbild GmbH"
assert [p["stueck"] for p in db.positionen(aid)] == [7]
assert vorher.is_file() and pg_abbild.pfad(vorher).is_file(), "alter Stand vorher gesichert, auch als Abbild"
kaputt = tmp / "kaputt.pgdump"
kaputt.write_bytes(abbild1.read_bytes()[:200])
try:
    db.wiederherstellen(kaputt)
    raise AssertionError("beschädigtes Abbild angenommen")
except (SicherungFehler, OSError):
    pass
assert db.angebot(aid)["kunde"] == "Abbild GmbH", "beschädigtes Abbild ändert nichts"
assert eigene_proben.namen, "Wiederherstellen aus dem Abbild ging über eine Probe-Datenbank"
reste = [n for (n,) in db.con.execute("SELECT datname FROM pg_database WHERE datname LIKE 'abbild_%'").fetchall()
         if n in eigene_proben.namen]
assert not reste, f"Probe-Datenbanken wieder gelöscht: {reste}"
ok("Wiederherstellen aus dem PostgreSQL-Abbild: gleiche Daten, alter Stand gesichert; beschädigtes Abbild abgewiesen")

# ------------------------------------------------------------------ Einstellung, Hintergrund, Aufräumen
db.einstellung_setzen("sicherung_dokumente", "nein")
s4 = db.sicherung()
assert not dokumente_sicherung.listenpfad(s4).exists()
db.einstellung_setzen("sicherung_dokumente", "ja")
from rohrlaser.datenbank import SicherungLauf  # noqa: E402
ordner_h = tmp / "Hintergrund"
lauf = SicherungLauf(db, ordner_h, db.dokumente_fuer_sicherung())
assert lauf.warten(120) and lauf.fehler is None, lauf.fehler
assert lauf.info.get("pg_abbild") and "Angebotsdokumente gesichert" in lauf.info.get("dokumente", ""), lauf.info
assert pg_abbild.pfad(lauf.pfad).is_file() and dokumente_sicherung.listenpfad(lauf.pfad).is_file()
ordner_r = tmp / "Aufraeumen"
for _ in range(3):
    db.sicherung(ordner_r, behalten=1)
assert len(list(ordner_r.glob("*.db"))) == 1 and len(list(ordner_r.glob("*.pgdump"))) == 1
assert len(list(ordner_r.glob("*.dokumente.json"))) == 1
ok("Einstellung „nein“ ohne Dokumente; Sicherung im Hintergrund mit Abbild und Dokumenten; Aufräumen löscht mit")

# ------------------------------------------------------------------ Dialog
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser import sicherung_dialog  # noqa: E402

app = QApplication.instance() or QApplication([])
zeilen = sicherung_dialog.sicherungen_lesen([s1.parent])
z1 = next(z for z in zeilen if z["pfad"] == s1)
z4 = next(z for z in zeilen if z["pfad"] == s4)
assert z1["abbild"] and z1["dokumente"] and z4["abbild"] and not z4["dokumente"]
ok("Wiederherstellen-Dialog kennt Abbild und Dokumente je Sicherung")
db.schliessen()
print("OK: Sicherung mit PostgreSQL-Abbild und Angebotsdokumenten")
