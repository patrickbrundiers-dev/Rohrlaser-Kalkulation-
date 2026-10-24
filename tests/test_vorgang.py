"""Prüft Vorgang und Gültigkeit in der Angebotsliste (Prüfbericht 22.10.2026, Paket 6): Entwurf, Verschickt (setzt das
Angebots-PDF), Beauftragt, Abgelehnt, Filter, 'Gültig bis', abgelaufene Angebote, 'Stand vom' beim Verkaufspreis und
die Umstellung älterer Dateien (Schema 35).

Aufruf: python tests/test_vorgang.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from rohrlaser.angebot_fenster import abgelaufen, gueltig_bis  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
db.einstellung_setzen("gueltigkeit", 30)
fenster = Hauptfenster(db, tmp, stumm=True)
au = fenster.angebote
heute = datetime.date.today()
ids = []
for n, tage in enumerate((0, 40, 5)):
    a = db.angebot_neu(dict(kunde=f"Kunde {n}", kundennr=str(n), datum=(heute - datetime.timedelta(days=tage)).isoformat()))
    db.position_neu(a, dict(pos=10, artikel="T", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
                            stueck=5, schneidweg=320, einstiche=2))
    ids.append(a)
au.neu_laden()
spalte = {au.modell.headerData(c, Qt.Horizontal): c for c in range(au.modell.columnCount())}
assert {"Vorgang", "Gültig bis", "Status"} <= set(spalte)
assert all(z.get("vorgang") is None for z in au.modell.zeilen)
assert {au.modell.wert(r, spalte["Vorgang"]) for r in range(au.modell.rowCount())} == {"Entwurf"}
ok("Neue Angebote: Vorgang Entwurf, Gültig bis = Datum + 30 Tage")

# Angebots-PDF: Entwurf -> Verschickt
s = fenster.angebot_oeffnen(ids[1])
assert s.optimieren() and s.angebot_pdf()
assert db.angebot(ids[1])["vorgang"] == "Verschickt"
z = next(z for z in au.modell.zeilen if z["id"] == ids[1])
assert z["_abgelaufen"] and gueltig_bis(z, 30) == heute - datetime.timedelta(days=10)
r = au.modell.zeilen.index(z)
assert au.modell.wert(r, spalte["Vorgang"]) == "Verschickt (abgelaufen)"
assert "Stand vom" in au.modell.data(au.modell.index(r, spalte["Verkaufspreis netto [€]"]), Qt.ToolTipRole)
ok("Angebots-PDF setzt Verschickt; 40 Tage alt = abgelaufen; Verkaufspreis mit 'Stand vom' im Tooltip")

# Beauftragt / Abgelehnt von Hand; Angebots-PDF ändert Beauftragt nicht mehr
assert au.vorgang_setzen("Beauftragt", ids[1]) and au.vorgang_setzen("Abgelehnt", ids[2])
s.angebot_pdf()
assert db.angebot(ids[1])["vorgang"] == "Beauftragt" and not abgelaufen(db.angebot(ids[1]), 30)
for titel, soll in (("Alle Angebote", 3), ("Offen (Entwurf, Verschickt)", 1), ("Beauftragt", 1), ("Abgelehnt", 1),
                    ("Verschickt und abgelaufen", 0)):
    au.vorgang_filter.setCurrentText(titel)
    assert au.modell.rowCount() == soll, (titel, au.modell.rowCount())
au.vorgang_filter.setCurrentText("Alle Angebote")
try:
    db.vorgang_setzen(ids[0], "Storniert")
    raise AssertionError("unbekannter Vorgang angenommen")
except ValueError:
    pass
kopie = db.angebot_kopieren(ids[1])
assert db.angebot(kopie)["vorgang"] is None
v = db.angebot(ids[1])["versand"]
assert len(v) == 2 and v[0]["netto"] > 0 and v[0]["datei"].endswith(".pdf"), v
s.neu_laden()
assert "Versandverlauf:" in s.uebersicht_bereich.preisstand.toolTip()
assert db.angebot(kopie)["versand"] == []
ok("Verlauf der verschickten Angebots-PDFs (Datum, netto, Datei) im Tooltip des Preisstands; Kopie ohne Verlauf")
ok("Beauftragt und Abgelehnt von Hand, Filter je Vorgang, Kopie beginnt als Entwurf")

# ältere Datei (Schema 34): festgeschriebene Preise = Verschickt
alt = tmp / "alt.db"
con = sqlite3.connect(db.pfad if hasattr(db, "pfad") else tmp / "rohrlaser.db")
con.execute(f"VACUUM INTO '{alt}'")
con.close()
c = sqlite3.connect(alt)
c.execute("UPDATE angebote SET vorgang=NULL")
c.execute("ALTER TABLE angebote DROP COLUMN vk_am")
c.execute("ALTER TABLE angebote DROP COLUMN vorgang")
c.execute("ALTER TABLE angebote DROP COLUMN versand")
c.execute("PRAGMA user_version=34")
c.commit()
c.close()
db2 = Datenbank(alt)
v = {a["id"]: a.get("vorgang") for a in db2.angebote()}
assert v[ids[1]] == "Verschickt" and v[ids[0]] is None and v[ids[2]] is None, v
ok("Datei Schema 34: Spalten ergänzt, Angebote mit Angebots-PDF (festgeschrieben) = Verschickt, sonst Entwurf")
print("OK: Vorgang und Gültigkeit in der Angebotsliste")
