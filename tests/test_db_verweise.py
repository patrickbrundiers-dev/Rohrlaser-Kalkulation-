"""Verweise zwischen Tabellen (Systemprüfung 17.11.2026, DB-01, db_verweise.py):

V1 Neue Datendatei und Angebot mit Reklamation, Scan-Rückmeldung, 3D-Modell, Staffel: keine Verweise ins Leere.
V2 Angebot löschen und alte Angebote archivieren: weiterhin keine; Journal-Zeilen (Automatik) nur als Information.
V3 Eine Zeile, die ins Leere zeigt (wie DB-02 vor 0.9.375), wird gezählt und im Text genannt.
V4 Support-Paket legt verweise.json bei (nur Anzahlen, keine Inhalte).

Aufruf: python tests/test_db_verweise.py
"""
import datetime
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import beispiel_angebot  # noqa: E402
from rohrlaser import archiv, db_verweise, etiketten, reklamation, support  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
assert db_verweise.zaehlen(db) == dict(fehler={}, journal={})


def zubehoer(aid, nummer):
    p0 = db.positionen(aid)[0]["id"]
    db.netz_speichern(p0, b"3D-Modell")
    db.staffel_stufe_neu(aid)
    db.protokoll_anhaengen(aid, ["STEP gelesen"])
    db.con.execute("UPDATE angebote SET vorgang=? WHERE id=?", ("Beauftragt", aid))
    reklamation.speichern(db, aid, dict(position_id=p0, pos="1", datum="2022-05-02", menge=2,
                                        fehlerart="Grat oder Schlacke", kosten=10.0, status=reklamation.OFFEN))
    db.con.execute("INSERT INTO rueckmeldungen (angebot_id, position_id, pos, schritt, menge, am, wer, code) VALUES "
                   "(?, ?, '1', ?, 3, '2022-05-01T08:00:00', 'PB', ?)",
                   (aid, p0, etiketten.schritte(db)[0], etiketten.code(nummer, "1")))
    db.con.execute("INSERT INTO automatik (zeit, kuerzel, angebot_id) VALUES ('2022-05-01T08:00:00', 'PB', ?)", (aid,))
    db.con.commit()


# ---------------------------------------------------------------- V1
alt = beispiel_angebot.anlegen(db, dict(nummer="2022-00001", datum="2022-03-15"))
weg = beispiel_angebot.anlegen(db, dict(nummer="2026-00002", datum="2026-10-01"))
zubehoer(alt, "2022-00001")
zubehoer(weg, "2026-00002")
assert db_verweise.zaehlen(db) == dict(fehler={}, journal={}), db_verweise.zaehlen(db)
print("OK     V1 Angebote mit Zubehör: keine Verweise ins Leere")

# ---------------------------------------------------------------- V2
db.angebot_loeschen(weg)
erg = db_verweise.zaehlen(db)
assert erg["fehler"] == {}, erg
assert erg["journal"] == {"automatik.angebot_id → angebote": 1}, erg
ergebnis = archiv.archivieren(db, archiv.kandidaten(db, datetime.date(2026, 10, 28)))
assert ergebnis == {2022: 1}, ergebnis
erg = db_verweise.zaehlen(db)
assert erg["fehler"] == {}, erg
print("OK     V2 Löschen und Archivieren: keine Verweise ins Leere, Automatik-Journal nur als Information")

# ---------------------------------------------------------------- V3
db.con.execute("INSERT INTO rueckmeldungen (angebot_id, position_id, pos, schritt, menge, am, wer, code) VALUES "
               "(999999, NULL, '1', 'Laser', 1, '2022-05-01T08:00:00', 'PB', 'X')")
db.con.commit()
erg = db_verweise.zaehlen(db)
assert erg["fehler"] == {"rueckmeldungen.angebot_id → angebote": 1}, erg
t = db_verweise.text(erg)
assert t.startswith("Verweise ins Leere: 1 (Fehler)") and "rueckmeldungen.angebot_id" in t and "Journal" in t, t
print("OK     V3 Zeile ohne Angebot gezählt")

# ---------------------------------------------------------------- V4
e = support.erstellen(db, ziel_ordner=tmp / "Support", protokoll_ordner=tmp / "Protokoll", system=[])
assert "verweise.json" in e["dateien"], e["dateien"]
with zipfile.ZipFile(e["pfad"]) as z:
    inhalt = json.loads(z.read("verweise.json"))
assert inhalt["fehler"] == {"rueckmeldungen.angebot_id → angebote": 1}, inhalt
assert "PB" not in json.dumps(inhalt) and "Laser" not in json.dumps(inhalt)      # nur Anzahlen
db.con.close()
print("OK     V4 Support-Paket mit verweise.json")
