"""Archiv alter Angebote, eine Datei je Jahr (Vorschlag 5b, Prüfung „Datenbank bei vielen Angeboten“ 28.10.2026).

Prüft: Auswahl (Alter nach Einstellung, Kollegen-Angebote, Lagerauftrag und geöffnete Angebote bleiben), Verschieben
mit Positionen, 3D-Modellen, Staffeln, Mengenstufen, Protokoll und Fertigungsstatus, Datendatei danach sauber
(Integrität, Fremdschlüssel), Suche im Archiv, Zurückholen (gleiche Nummer, neue IDs, alles wieder da), Sicherung des
Archivs, Menü und Dialog im Hauptfenster.

Aufruf: python tests/test_archiv.py
"""
import datetime
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import archiv, archiv_dialog, fertigung  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

HEUTE = datetime.date(2026, 10, 28)


def ok(text):
    print("OK     " + text)


def inhalt(db, aid):
    """Vergleichbarer Inhalt eines Angebots ohne IDs."""
    a = db.angebot(aid)
    pos = db.positionen(aid)
    return dict(nummer=a["nummer"], kunde=a["kunde"], datum=a["datum"], ergebnis=a.get("ergebnis"),
                positionen=[(p["pos"], p["artikel"], p["laenge"], p["stueck"]) for p in pos],
                netze=sorted(str(tuple(db.con.execute("SELECT daten FROM netze WHERE position_id=?",
                                                      (p["id"],)).fetchone() or ())) for p in pos),
                staffeln=[(s["schluessel"], s["menge"]) for s in db.staffeln(aid)],
                stufen=db.con.execute("SELECT COUNT(*) FROM staffel_stufen WHERE angebot_id=?", (aid,)).fetchone()[0],
                protokoll=len(db.protokoll(aid)),
                status=[r[0] for r in db.con.execute("SELECT status FROM auftrag_status WHERE angebot_id=? ORDER BY id",
                                                     (aid,))])


tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
ids = {}
for jahr in (2022, 2023, 2024, 2025, 2026):
    ids[jahr] = beispiel_angebot.anlegen(db, dict(nummer=f"{jahr}-00001", datum=f"{jahr}-03-15"))
alt = ids[2022]
p0 = db.positionen(alt)[0]["id"]
db.netz_speichern(p0, b"3D-Modell")
db.staffel_stufe_neu(alt)
db.protokoll_anhaengen(alt, ["STEP gelesen"])
db.ergebnis_speichern(alt, dict(stangen=[dict(laenge=6000)], auswertung=dict(stangen=1)))
db.con.execute("UPDATE angebote SET vorgang=? WHERE id=?", ("Beauftragt", alt))
fertigung.setzen(db, alt, fertigung.status_liste(db)[0], wer="PB")
vorher = inhalt(db, alt)
db.con.execute("UPDATE angebote SET vorgang=? WHERE id=?", ("Beauftragt", ids[2023]))
fertigung.setzen(db, ids[2023], fertigung.status_liste(db)[0], wer="PB")
pos_2023 = [p["id"] for p in db.positionen(ids[2023])]
kollege = beispiel_angebot.anlegen(db, dict(nummer="2021-K-00001", datum="2021-01-10"))
db.con.execute("UPDATE angebote SET fremd='K' WHERE id=?", (kollege,))
db.con.commit()

k = archiv.kandidaten(db, HEUTE)
assert k == {2022: [ids[2022]], 2023: [ids[2023]], 2024: [ids[2024]]}, k
db.einstellung_setzen("archiv_jahre", "3")
assert archiv.kandidaten(db, HEUTE) == {2022: [ids[2022]], 2023: [ids[2023]]}
db.einstellung_setzen("archiv_jahre", "2")
assert archiv.kandidaten(db, HEUTE, offen={ids[2023]}) == {2022: [ids[2022]], 2024: [ids[2024]]}
ok("Auswahl: älter als eingestellte Jahre, Kollegen-Angebote und geöffnete Angebote bleiben")

ergebnis = archiv.archivieren(db, archiv.kandidaten(db, HEUTE))
assert ergebnis == {2022: 1, 2023: 1, 2024: 1}, ergebnis
assert archiv.bericht(ergebnis).startswith("3 Angebote archiviert")
assert sorted(archiv.dateien(db)) == [2022, 2023, 2024] and archiv.anzahl(db) == {2022: 1, 2023: 1, 2024: 1}
nummern = {a["nummer"] for a in db.angebote()}
assert nummern == {"2025-00001", "2026-00001", "2021-K-00001"}, nummern
for t in ("positionen", "staffeln", "staffel_stufen", "step_protokoll", "auftrag_status"):
    assert db.con.execute(f"SELECT COUNT(*) FROM {t} WHERE angebot_id=?", (alt,)).fetchone()[0] == 0, t
assert db.con.execute("SELECT COUNT(*) FROM netze WHERE position_id=?", (p0,)).fetchone()[0] == 0
assert db.con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
assert not db.con.execute("PRAGMA foreign_key_check").fetchall()
a = sqlite3.connect(archiv.datei(db, 2022))
assert a.execute("SELECT COUNT(*) FROM positionen").fetchone()[0] == len(beispiel_angebot.POSITIONEN)
assert a.execute("SELECT COUNT(*) FROM netze").fetchone()[0] == 1
assert a.execute("SELECT COUNT(*) FROM auftrag_status").fetchone()[0] == 1
a.close()
assert (tmp / "Sicherung" / "Archiv" / archiv.datei(db, 2022).name).is_file()
ok("Archivieren: Angebot mit Positionen, 3D-Modell, Staffeln, Protokoll, Status im Jahresarchiv; Datendatei sauber")

assert [z["nummer"] for z in archiv.suchen(db)] == ["2024-00001", "2023-00001", "2022-00001"]
assert [z["nummer"] for z in archiv.suchen(db, "2023-")] == ["2023-00001"]
assert len(archiv.suchen(db, beispiel_angebot.POSITIONEN[0]["artikel"])) == 3
assert archiv.suchen(db, "gibt es nicht") == []
ok("Archiv durchsuchen: Nummer, Artikel, neueste zuerst")

z = archiv.suchen(db, "2022-")[0]
neu = archiv.zurueckholen(db, z["jahr"], z["id"])
assert inhalt(db, neu) == vorher, (inhalt(db, neu), vorher)
assert archiv.anzahl(db)[2022] == 0
try:
    archiv.zurueckholen(db, z["jahr"], z["id"])
    raise AssertionError("doppelt zurückgeholt")
except ValueError:
    pass
assert not db.con.execute("PRAGMA foreign_key_check").fetchall()
assert not fertigung.geaendert(db, neu) and fertigung.aktuell(db, neu)["status"] == vorher["status"][0]
ok("Zurückholen: gleiche Nummer, Positionen, 3D-Modell, Staffeln, Protokoll, Status wieder da, Freigabe gilt")

# alte Positions-ID inzwischen vergeben: neue IDs, Freigabe wird mit umgestellt
platz = beispiel_angebot.anlegen(db, dict(nummer="2026-00099", datum="2026-10-01"))
db.con.execute("PRAGMA foreign_keys=OFF")
db.con.execute("UPDATE positionen SET id=? WHERE id=?", (pos_2023[0], db.positionen(platz)[0]["id"]))
db.con.commit()
db.con.execute("PRAGMA foreign_keys=ON")
z = archiv.suchen(db, "2023-")[0]
neu23 = archiv.zurueckholen(db, z["jahr"], z["id"])
assert pos_2023[0] not in [p["id"] for p in db.positionen(neu23)]
assert len(db.positionen(neu23)) == len(beispiel_angebot.POSITIONEN)
assert not fertigung.geaendert(db, neu23)
db.angebot_loeschen(platz)
ok("Zurückholen bei vergebener ID: neue IDs, Freigabe bleibt gültig")

# Oberfläche: Menü, Archivieren mit Sicherung, Dialog sucht und holt zurück
app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, tmp, stumm=True)
for text in ("Alte Angebote archivieren …", "Archiv durchsuchen …"):
    assert text in fenster.datei_aktionen, text
fenster.offen.update({neu: None, neu23: None})          # geöffnete Angebote bleiben
assert archiv_dialog.archivieren(fenster, HEUTE) is None
fenster.offen.clear()
assert archiv_dialog.archivieren(fenster, HEUTE) == {2022: 1, 2023: 1}
assert any("_vor_Archiv" in p.name for p in (tmp / "Sicherung").glob("*.db"))
d = archiv_dialog.ArchivDialog(fenster)
assert d.tabelle.rowCount() == 3
d.suche.setText("2024-")
d.laden()
assert d.tabelle.rowCount() == 1 and d.tabelle.item(0, 1).text() == "2024-00001"
neu2 = d.zurueckholen()
assert neu2 and d.zurueckgeholt == neu2 and db.angebot(neu2)["nummer"] == "2024-00001"
ok("Oberfläche: Datei-Menü, Archivieren nach Sicherung „vor Archivieren“, Dialog sucht und holt zurück")
db.schliessen()
print("Alle Archiv-Prüfungen bestanden.")
