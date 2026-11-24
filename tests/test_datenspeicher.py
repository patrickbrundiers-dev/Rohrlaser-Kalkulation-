"""PostgreSQL als einzige Datenbank (SQLite entfernen, Patrick 19.11.2026; je PC eigenes PostgreSQL, Abgleich bleibt).

Prüft den Weg, den jeder PC beim Update geht, mit echtem eingebettetem Server je Datenordner (ohne Prüflauf-Server):
- neue Installation: Datenbank(pfad) legt PostgreSQL an (Daten/pg, Merkdatei am Pfad), Beispieldaten sind da;
- alte SQLite-Datendatei: wird beim Öffnen automatisch umgestellt: geprüfte Sicherung vorher, alle Zeilen übernommen
  und verglichen, gerechnete Angebote in beiden Datenbanken neu kalkuliert und gleich, alte Datei unverändert als
  Archiv unter Sicherung/Migration, Bericht; danach Änderungen in PostgreSQL, Sicherung bleibt eine SQLite-Datei;
- Merkdatei verloren, Daten im Ordner pg: werden geöffnet, nicht überschrieben;
- Fehlerfälle ändern nichts: PostgreSQL-Ordner hat schon Daten, Kalkulation weicht ab (kein SQLite-Betrieb, Fehler);
- kaputte Werte (Text in Zahlenfeldern, verwaiste Zeilen) werden angepasst und im Bericht genannt;
- Menü Datei → Datenbank (PostgreSQL) zeigt, wo die Daten liegen; einen Rückweg auf SQLite gibt es nicht.
Als root (initdb verweigert root) oder ohne PostgreSQL-Programme wird nur die Merkdatei-Erkennung geprüft.

Aufruf: python tests/test_datenspeicher.py
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("ROHRLASER_PG_TEST", None)      # hier geht es um den echten Weg je Datenordner, nicht den Prüfserver
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))

import beispiel_angebot  # noqa: E402
from rohrlaser import datenspeicher, db_verbindung, pg_lokal, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank, datei_pruefen  # noqa: E402


def ok(text):
    print("OK     " + text)


def sqlite_datei(pfad):
    """Alte SQLite-Datendatei wie vor dem Update (aktuelles Schema)."""
    pfad.parent.mkdir(parents=True, exist_ok=True)
    return Datenbank(pfad, verbindung=db_verbindung.SqliteVerbindung(pfad, fremdschluessel=False))


def gerechnet(db, kopf):
    aid = beispiel_angebot.anlegen(db, kopf)
    erg = rechnen.optimieren(db.angebot(aid), db.positionen(aid), db.kontext(), db.tabellen(), db.einstellungen())
    db.ergebnis_speichern(aid, erg)
    return aid


tmp = Path(tempfile.mkdtemp())
assert datenspeicher.art(tmp / "gibt_es_nicht.db") == datenspeicher.SQLITE
try:
    bin_ordner = pg_lokal.programme()
    import psycopg  # noqa: F401
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise pg_lokal.PgFehlt("als root (initdb verweigert root)")
except (pg_lokal.PgFehlt, ImportError) as e:
    print(f"PostgreSQL-Teil übersprungen: {e}")
    sys.exit(0)
os.environ["ROHRLASER_PG_BIN"] = str(bin_ordner)

# ---- neue Installation
neu_pfad = tmp / "Neu" / "rohrlaser.db"
db = Datenbank(neu_pfad)
assert not db_verbindung.ist_sqlite(db.con) and datenspeicher.art(neu_pfad) == datenspeicher.POSTGRES
assert (neu_pfad.parent / "pg" / "PG_VERSION").is_file() and neu_pfad.stat().st_size < 64 * 1024
assert db.con.execute("SELECT COUNT(*) FROM profile").fetchone()[0] > 10, "Beispieldaten"
a_neu = beispiel_angebot.anlegen(db, dict(nummer="2026-00500", kunde="Neu"))
db.con.commit()
db.schliessen()
db = Datenbank(neu_pfad)
assert db.angebot(a_neu)["kunde"] == "Neu"
db.schliessen()
ok("Neue Installation: PostgreSQL direkt angelegt (Daten/pg, Merkdatei), Beispieldaten, Daten bleiben")

# Merkdatei verloren: Daten im Ordner pg werden geöffnet, nicht überschrieben
neu_pfad.unlink()
db = Datenbank(neu_pfad)
assert db.angebot(a_neu)["kunde"] == "Neu" and datenspeicher.art(neu_pfad) == datenspeicher.POSTGRES
db.schliessen()
ok("Merkdatei verloren: vorhandene Daten in PostgreSQL wieder geöffnet")

# ---- alte SQLite-Datendatei: automatisch umstellen
pfad = tmp / "Daten" / "rohrlaser.db"
alt = sqlite_datei(pfad)
a = gerechnet(alt, dict(nummer="2026-00001", kunde="Umzug GmbH"))
gerechnet(alt, dict(nummer="2026-00002", kunde="Ölmühle & Söhne"))
alt.con.commit()
vorher = {t: alt.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("angebote", "positionen", "preise")}
kalk_vorher = datenspeicher.kalkulationen(alt)
assert len(kalk_vorher) == 2 and all(isinstance(v, dict) for v in kalk_vorher.values()), kalk_vorher
alt.schliessen()
db = Datenbank(pfad)
assert not db_verbindung.ist_sqlite(db.con) and datenspeicher.art(pfad) == datenspeicher.POSTGRES
assert {t: db.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in vorher} == vorher
assert datenspeicher.kalkulationen(db, list(kalk_vorher)) == kalk_vorher, "Kalkulation unverändert"
archiv = list((pfad.parent / "Sicherung" / datenspeicher.ARCHIV).glob("rohrlaser_SQLite_*.db"))
assert len(archiv) == 1 and datei_pruefen(archiv[0])["anzahl"]["angebote"] == vorher["angebote"], "Archiv"
sicherung = list((pfad.parent / "Sicherung").glob("*vor_PostgreSQL*.db"))
assert sicherung and datei_pruefen(sicherung[0])["anzahl"]["angebote"] == vorher["angebote"]
bericht = list((pfad.parent / "Sicherung").glob("Umstellung_PostgreSQL_*.txt"))
assert bericht and "umgestellt" in bericht[0].read_text(encoding="utf-8")
assert db.angebot(a)["kunde"] == "Umzug GmbH"
assert "PostgreSQL auf diesem PC" in datenspeicher.status(db) and "Migration" in datenspeicher.status(db)
ok(f"Alte Datendatei automatisch umgestellt: Sicherung geprüft, Zeilen und {len(kalk_vorher)} Kalkulationen "
   "gleich, alte Datei als Archiv unter Sicherung/Migration, Bericht")

db.angebot_aendern(a, "kunde", "Neu in PostgreSQL")
b = beispiel_angebot.anlegen(db, dict(nummer="2026-00003", kunde="Zweiter"))
db.con.commit()
s = db.sicherung(zusatz="test")
assert datei_pruefen(s)["anzahl"]["angebote"] == vorher["angebote"] + 1, "Sicherung ist eine SQLite-Datei"
db.schliessen()
db = Datenbank(pfad)
assert db.angebot(a)["kunde"] == "Neu in PostgreSQL" and db.angebot(b)["kunde"] == "Zweiter"
try:
    datenspeicher.umstellen(db)
    raise AssertionError("doppelt umgestellt")
except datenspeicher.UmstellFehler:
    pass
assert not hasattr(datenspeicher, "zurueck"), "kein Rückweg auf SQLite"
ok("Danach: Änderungen in PostgreSQL, Sicherung als SQLite-Datei, kein zweites Umstellen, kein Rückweg")

# ---- Fehler: PostgreSQL-Ordner hat schon Daten (z. B. Datendatei aus einer Sicherung zurückkopiert)
db.schliessen()
datenspeicher.alle_stoppen()
kopie = tmp / "Kopie" / "rohrlaser.db"
alt = sqlite_datei(kopie)
beispiel_angebot.anlegen(alt, dict(nummer="2026-00010"))
alt.con.commit()
alt.schliessen()
os.replace(kopie, kopie.with_name("alt.db"))
Datenbank(kopie).schliessen()               # Ordner pg mit Daten
kopie.unlink()
os.replace(kopie.with_name("alt.db"), kopie)
try:
    Datenbank(kopie)
    raise AssertionError("über vorhandene Daten umgestellt")
except datenspeicher.UmstellFehler as e:
    assert "schon Daten" in str(e), e
assert datenspeicher.art(kopie) == datenspeicher.SQLITE and datei_pruefen(kopie)["anzahl"]["angebote"] == 1
ok("PostgreSQL-Ordner mit Daten: Fehler statt SQLite-Betrieb, Datendatei unverändert")

# ---- Fehler: Kalkulation weicht nach dem Übernehmen ab → nicht umgestellt
k_pfad = tmp / "Kalk" / "rohrlaser.db"
alt = sqlite_datei(k_pfad)
gerechnet(alt, dict(nummer="2026-00020"))
alt.con.commit()
alt.schliessen()
echt = datenspeicher.kalkulationen
datenspeicher.kalkulationen = lambda d, ids=None, anzahl=20: (echt(d, ids, anzahl) if ids is None
                                                              else {i: "anders" for i in ids})
try:
    Datenbank(k_pfad)
    raise AssertionError("trotz abweichender Kalkulation umgestellt")
except datenspeicher.UmstellFehler as e:
    assert "Kalkulation" in str(e), e
finally:
    datenspeicher.kalkulationen = echt
assert datenspeicher.art(k_pfad) == datenspeicher.SQLITE and datei_pruefen(k_pfad)["anzahl"]["angebote"] == 1
db = Datenbank(k_pfad)                      # zweiter Versuch (Kalkulation gleich): umgestellt
assert datenspeicher.art(k_pfad) == datenspeicher.POSTGRES
db.schliessen()
ok("Abweichende Kalkulation: nicht umgestellt, Datei unverändert; nächster Start stellt um")

# ---- kaputte Daten (Text in Zahlenfeldern, Komma, verwaiste Position): angepasst, im Bericht
pfad2 = tmp / "Kaputt" / "rohrlaser.db"
d2 = sqlite_datei(pfad2)
k = beispiel_angebot.anlegen(d2, dict(nummer="2026-00077"))
pos = [p["id"] for p in d2.positionen(k)]
d2.con.commit()
d2.schliessen()
c = sqlite3.connect(pfad2)
c.execute("PRAGMA foreign_keys=OFF")
c.execute("UPDATE positionen SET stueck='abc' WHERE id=?", (pos[0],))
c.execute("UPDATE positionen SET laenge='12,5' WHERE id=?", (pos[1],))
c.execute("UPDATE positionen SET angebot_id=999999 WHERE id=?", (pos[2],))
c.commit()
c.close()
d2 = Datenbank(pfad2)
text = sorted((pfad2.parent / "Sicherung").glob("Umstellung_PostgreSQL_*.txt"))[-1].read_text(encoding="utf-8")
assert "'abc' → None" in text and "'12,5' → 12.5" in text and "positionen.angebot_id → angebote" in text, text
assert [p["laenge"] for p in d2.positionen(k) if p["id"] == pos[1]] == [12.5]
d2.schliessen()
ok("Kaputte Daten: Werte angepasst, verwaiste Zeile, alles im Bericht")

# ---- Menü Datei
from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
db = Datenbank(pfad)
fenster = Hauptfenster(db, tmp, stumm=True)
assert "Datenbank (PostgreSQL) …" in fenster.datei_aktionen
assert not any("SQLite" in t for t in fenster.datei_aktionen)
assert "PostgreSQL auf diesem PC" in fenster.datenspeicher_anzeigen()
ok("Menü Datei → Datenbank (PostgreSQL) zeigt den Speicherort, kein Wechsel auf SQLite")
fenster.close()
db.schliessen()
datenspeicher.alle_stoppen()
print("Alles in Ordnung.")
