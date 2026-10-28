"""Gemeinsamer Ordner bei vielen Angeboten (Vorschlag 2b, Prüfung „Datenbank bei vielen Angeboten“ 28.10.2026).

Prüft: nur geänderte Angebote werden neu gepackt (Merker per Trigger), je Monat eine Datei, nur geänderte Monate gehen
in den gemeinsamen Ordner, Datum in anderen Monat, Löschen, halb geschriebene Daten (Kollege bleibt unverändert),
Daten eines Kollegen im alten Format 1 werden weiter gelesen, die eigene alte Einzeldatei verschwindet, nach einem
Programm-Update wird einmal alles neu gepackt.

Aufruf: python tests/test_teilen_monate.py
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()


def arbeitsplatz(name, k):
    db = Datenbank(tmp / name / "rohrlaser.db")
    db.einstellung_setzen("benutzer_name", name)
    db.einstellung_setzen("benutzer_kuerzel", k)
    db.einstellung_setzen("teilen_ordner", str(gemeinsam))
    return db


POS = dict(pos=10, artikel="T-1", bezeichnung="Holm", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
           stueck=5, schneidweg=320, einstiche=2)
gepackt = []
_inhalt = teilen.angebot_inhalt


def zaehlen(con, i, karte=None):
    gepackt.append(i)
    return _inhalt(con, i, karte)


teilen.angebot_inhalt = zaehlen

pb = arbeitsplatz("Patrick", "PB")
ids = {}
for datum in ("2026-08-03", "2026-09-10", "2026-09-20", "2026-10-01"):
    ids[datum] = pb.angebot_neu(dict(kunde="Kunde " + datum, datum=datum))
    pb.position_neu(ids[datum], dict(POS, artikel="T-" + datum))
pb.netz_speichern(pb.positionen(ids["2026-09-10"])[0]["id"], b"NETZ" * 50)
teilen.abgleichen(pb)
ordner = gemeinsam / "Rohrlaser_PB"
assert sorted(p.name for p in ordner.iterdir()) == ["Angebote_2026-08.sqlite", "Angebote_2026-09.sqlite",
                                                     "Angebote_2026-10.sqlite", "haupt.sqlite"]
assert teilen.info_lesen(ordner)["format"] == 2 and len(gepackt) == 4
ok("je Monat des Angebotsdatums eine Datei, Hauptdatei mit Info und Stammdaten")

mk = arbeitsplatz("Martin", "MK")
b = teilen.abgleichen(mk, teilen.UEBERNEHMEN)
assert b["angebote_neu"] == 4, b
fremd = {a["nummer"]: a for a in mk.angebote() if a["fremd"] == "PB"}
n0910 = pb.angebot(ids["2026-09-10"])["nummer"]
f = fremd[n0910]
assert mk.con.execute("SELECT COUNT(*) FROM netze n JOIN positionen p ON p.id=n.position_id WHERE p.angebot_id=?",
                      (f["id"],)).fetchone()[0] == 1
ok("Kollege liest alle Monate, 3D-Netze kommen mit")

# nichts geändert: nichts packen, keine Monatsdatei neu
staende = {p.name: p.stat().st_mtime_ns for p in ordner.glob("Angebote_*")}
gepackt.clear()
teilen.schreiben(pb)
assert gepackt == [], gepackt
assert {p.name: p.stat().st_mtime_ns for p in ordner.glob("Angebote_*")} == staende
ok("ohne Änderung: kein Angebot neu gepackt, keine Monatsdatei neu in den gemeinsamen Ordner")

# eine Position geändert: nur dieses Angebot und nur dieser Monat
pid = pb.positionen(ids["2026-09-20"])[0]["id"]
pb.position_aendern(pid, "stueck", 77)
gepackt.clear()
teilen.schreiben(pb)
assert gepackt == [ids["2026-09-20"]], gepackt
neu = {p.name: p.stat().st_mtime_ns for p in ordner.glob("Angebote_*")}
assert [n for n in neu if neu[n] != staende[n]] == ["Angebote_2026-09.sqlite"], (neu, staende)
b = teilen.lesen(mk)
assert b["angebote_geaendert"] == 1 and b["angebote_neu"] == 0, b
f = next(a for a in mk.angebote() if a["nummer"] == pb.angebot(ids["2026-09-20"])["nummer"])
assert mk.positionen(f["id"])[0]["stueck"] == 77
ok("Position geändert: nur dieses Angebot gepackt, nur der Monat 2026-09 neu, beim Kollegen angekommen")

# Datum in einen anderen Monat, Angebot gelöscht
pb.angebot_aendern(ids["2026-08-03"], "datum", "2026-10-15")
n0920 = pb.angebot(ids["2026-09-20"])["nummer"]
pb.angebot_loeschen(ids["2026-09-20"])
teilen.schreiben(pb)
assert not (ordner / "Angebote_2026-08.sqlite").exists()
b = teilen.lesen(mk)
assert b["angebote_weg"] == 1 and b["angebote_geaendert"] == 1, b
assert n0920 not in {a["nummer"] for a in mk.angebote()}
assert len([a for a in mk.angebote() if a["fremd"] == "PB"]) == 3
ok("Datum in anderen Monat: Angebot wandert, leerer Monat verschwindet; gelöschtes Angebot beim Kollegen weg")

# halb geschrieben: Monatsdatei passt nicht zur Hauptdatei -> beim Kollegen bleibt alles, wie es ist
pb.position_aendern(pb.positionen(ids["2026-10-01"])[0]["id"], "stueck", 11)
teilen.schreiben(pb)
c = sqlite3.connect(ordner / "Angebote_2026-10.sqlite")
c.execute("DELETE FROM angebote WHERE nummer=?", (pb.angebot(ids["2026-08-03"])["nummer"],))
c.commit()
c.close()
vorher = {a["nummer"] for a in mk.angebote() if a["fremd"] == "PB"}
b = teilen.lesen(mk)
assert b["angebote_weg"] == 0 and b["angebote_geaendert"] == 0, b
assert {a["nummer"] for a in mk.angebote() if a["fremd"] == "PB"} == vorher
(teilen._cache(pb) / "Rohrlaser_PB" / "hingelegt.json").unlink()      # nächstes Schreiben legt alles neu hin
teilen.schreiben(pb)
b = teilen.lesen(mk)
assert b["angebote_geaendert"] == 1 and b["angebote_weg"] == 0, b
ok("Monatsdatei passt nicht zur Hauptdatei (wird gerade geschrieben): Kollege ändert und löscht nichts, später alles da")

# Kollege mit älterem Programm (Format 1, eine Datei)
ko = arbeitsplatz("Klaus", "KO")
teilen.abgleichen(ko, teilen.ZUSAMMENFUEHREN)
a_ko = ko.angebot_neu(dict(kunde="Alt", datum="2026-10-20"))
ko.position_neu(a_ko, POS)
teilen.schreiben(ko)
kopf = sqlite3.connect(gemeinsam / "Rohrlaser_KO.sqlite")
teilen._datei_anlegen(kopf)
h = sqlite3.connect(gemeinsam / "Rohrlaser_KO" / "haupt.sqlite")
kopf.executemany("INSERT INTO stammdaten VALUES (?, ?, ?, ?)", h.execute("SELECT * FROM stammdaten").fetchall())
info = dict(h.execute("SELECT name, wert FROM info").fetchall())
info["format"] = "1"
kopf.executemany("INSERT OR REPLACE INTO info VALUES (?, ?)", info.items())
h.close()
for m in (gemeinsam / "Rohrlaser_KO").glob("Angebote_*"):
    c = sqlite3.connect(m)
    kopf.executemany("INSERT INTO angebote VALUES (?, ?, ?)", c.execute("SELECT * FROM angebote").fetchall())
    c.close()
kopf.commit()
kopf.close()
for p in (gemeinsam / "Rohrlaser_KO").iterdir():
    p.unlink()
(gemeinsam / "Rohrlaser_KO").rmdir()
assert teilen.andere_dateien(mk)["KO"].name == "Rohrlaser_KO.sqlite"
b = teilen.lesen(mk)
assert ko.angebot(a_ko)["nummer"] in {a["nummer"] for a in mk.angebote() if a["fremd"] == "KO"}, b
ok("Kollege mit älterem Programm (eine Datei, Format 1): Angebote werden weiter gelesen")

# eigene alte Einzeldatei: nach dem Schreiben im neuen Format weg
teilen.schreiben(ko)
assert not (gemeinsam / "Rohrlaser_KO.sqlite").exists() and (gemeinsam / "Rohrlaser_KO" / "haupt.sqlite").exists()
ok("eigene alte Einzeldatei wird nach dem ersten Schreiben im neuen Format entfernt")

# nach einem Programm-Update: einmal alles neu packen (Aufbau des Inhalts könnte sich geändert haben)
haupt = teilen._cache(pb) / "Rohrlaser_PB" / "haupt.sqlite"
c = sqlite3.connect(haupt)
c.execute("UPDATE info SET wert=? WHERE name='version'", (json.dumps("0.0.1"),))
c.commit()
c.close()
gepackt.clear()
teilen.schreiben(pb)
assert sorted(gepackt) == sorted(i for i in ids.values() if i != ids["2026-09-20"]), gepackt
gepackt.clear()
teilen.schreiben(pb)
assert gepackt == []
ok("nach einem Programm-Update einmal alle Angebote neu gepackt, danach wieder nur geänderte")
for db in (pb, mk, ko):
    db.schliessen()
print("Alle Prüfungen zum gemeinsamen Ordner mit Monatsdateien bestanden.")
