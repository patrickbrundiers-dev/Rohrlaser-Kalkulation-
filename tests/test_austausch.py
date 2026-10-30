"""Vorbereitung Server-Synchronisation (Plan 30.10.2026, Schritt 1): Austauschweg, Änderungsprotokoll, Kennungen.

Prüft: OrdnerWeg findet Haupt- und Einzeldateien wie bisher, belegt Nummern exklusiv (auch AB-Nummern), legt eigene
Daten im gleichen Aufbau ab (Rohrlaser_<K>/haupt.sqlite + Monatsdateien); das Änderungsprotokoll schreibt lokale
Änderungen (Herkunft leer) und beim Abgleich eingetragene (Herkunft „abgleich“) mit, nur gemeinsame Einstellungen,
alte Einträge fallen weg; Angebote und Positionen haben eine feste Kennung, die Kopie eine neue, die fremde Kopie beim
Kollegen dieselbe, die Umnummerierung einer vorläufigen Nummer behält sie; die Anzeige (angebot, positionen) sieht sie
nicht; die Info der geteilten Datei nennt Protokollstand und Uhrzeit.

Aufruf: python tests/test_austausch.py
"""
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import austausch, nummern, teilen  # noqa: E402
from rohrlaser.angebot import kuerzel_sauber  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
gemeinsam = tmp / "Gemeinsam"
gemeinsam.mkdir()

# ---------------------------------------------------------------- OrdnerWeg
w = austausch.OrdnerWeg(gemeinsam)
assert w.erreichbar() and not austausch.OrdnerWeg(tmp / "fehlt").erreichbar()
assert austausch.weg(None) is None and isinstance(austausch.weg(gemeinsam), austausch.OrdnerWeg)
(gemeinsam / "Rohrlaser_AB.sqlite").write_bytes(b"")                 # Format 1
(gemeinsam / "Rohrlaser_CD").mkdir()
(gemeinsam / "Rohrlaser_CD" / "haupt.sqlite").write_bytes(b"")        # Format 2
(gemeinsam / "Rohrlaser_EF").mkdir()                                  # Ordner ohne Hauptdatei
assert w.haupt("AB").name == "Rohrlaser_AB.sqlite" and w.haupt("CD").parent.name == "Rohrlaser_CD"
assert w.haupt("EF") is None
assert set(w.mitarbeiter("CD", kuerzel_sauber)) == {"AB"}
assert set(w.mitarbeiter("", kuerzel_sauber)) == {"AB", "CD"}
ok("OrdnerWeg: Format 1 und 2 gefunden, eigenes Kürzel und leere Ordner übergangen")

assert w.nummer_hoechste("Nummern") == 0
belegt = []


def belegen():
    for n in range(1, 21):
        if w.nummer_belegen("Nummern", n, "x"):
            belegt.append(n)


faeden = [threading.Thread(target=belegen) for _ in range(4)]
for f in faeden:
    f.start()
for f in faeden:
    f.join()
assert sorted(belegt) == list(range(1, 21)), belegt
assert w.nummer_hoechste("Nummern") == 20 and w.nummer_hoechste("AB-Nummern") == 0
assert (gemeinsam / "Nummern" / "00007.nummer").read_text() == "x"
ok("Nummern exklusiv belegt (4 gleichzeitig, keine doppelt), Bereiche getrennt")

assert w.unterordner("Anfragen") == gemeinsam / "Anfragen" and not (gemeinsam / "Anfragen").exists()
assert w.unterordner("Anfragen", anlegen=True).is_dir()
assert austausch.OrdnerWeg(tmp / "fehlt").unterordner("Anfragen", anlegen=True) is None
for p in ("Rohrlaser_AB.sqlite", "Rohrlaser_CD/haupt.sqlite"):
    (gemeinsam / p).unlink()
ok("Unterordner wie bisher (nur angelegt, wenn verlangt; nicht erreichbar = None)")


# ---------------------------------------------------------------- zwei Arbeitsplätze
def arbeitsplatz(name, k):
    db = Datenbank(tmp / name / "rohrlaser.db")
    db.einstellung_setzen("benutzer_name", name)
    db.einstellung_setzen("benutzer_kuerzel", k)
    db.einstellung_setzen("teilen_ordner", str(gemeinsam))
    return db


def eintraege(db, seit=0, **gleich):
    return [e for e in teilen.protokoll(db.con, seit) if all(e[n] == v for n, v in gleich.items())]


pb = arbeitsplatz("Patrick", "PB")
assert isinstance(teilen.weg(pb), austausch.OrdnerWeg) and str(teilen.weg(pb)) == str(gemeinsam)
platz = pb.einstellung("teilen_installation")
assert platz and teilen.installation(pb) == platz
POS = dict(pos=10, artikel="T-1", bezeichnung="Holm", profil_id="QR 40x40x3", werkstoff_id="S235-10219", laenge=1000,
           stueck=5, schneidweg=320, einstiche=2)
a1 = pb.angebot_neu(dict(kunde="Kunde A", datum="2026-09-10"))
p1 = pb.position_neu(a1, POS)
u1 = pb.con.execute("SELECT uid FROM angebote WHERE id=?", (a1,)).fetchone()[0]
pu1 = pb.con.execute("SELECT uid FROM positionen WHERE id=?", (p1,)).fetchone()[0]
assert len(u1) == 32 and len(pu1) == 32
assert "uid" not in pb.angebot(a1) and "uid" not in pb.positionen(a1)[0]
ok("Angebot und Position mit fester Kennung; Anzeige sieht sie nicht")

kopie = pb.angebot_kopieren(a1)
uk = pb.con.execute("SELECT uid FROM angebote WHERE id=?", (kopie,)).fetchone()[0]
pk = [r[0] for r in pb.con.execute("SELECT uid FROM positionen WHERE angebot_id=?", (kopie,))]
assert uk and uk != u1 and pk and pu1 not in pk
n_pos = pb.con.execute("SELECT COUNT(*), COUNT(DISTINCT uid) FROM positionen").fetchone()
assert n_pos[0] == n_pos[1] >= 2, n_pos
ok("Kopie bekommt neue Kennungen (Angebot und Positionen)")

stand = teilen.protokoll_stand(pb.con)
assert stand > 0
lokal = eintraege(pb, tabelle="angebote", uid=u1)
assert lokal and all(e["herkunft"] is None and e["platz"] == platz for e in lokal), lokal
pb.einstellung_setzen("ansicht_thema", "dunkel")                     # nur dieser Arbeitsplatz (LOKAL)
pb.einstellung_setzen("teilen_lese_zeit", "x")                       # intern
assert not eintraege(pb, stand)
pb.einstellung_setzen("gewinn", 12)                         # gemeinsam
e = eintraege(pb, stand)
assert [(x["tabelle"], x["uid"], x["art"]) for x in e] == [("einstellungen", "gewinn", "neu")], e
stand = teilen.protokoll_stand(pb.con)
with pb.con:
    pb.con.execute("UPDATE werkstoffe SET kategorie=kategorie WHERE rowid=(SELECT MIN(rowid) FROM werkstoffe)")
e = eintraege(pb, stand, tabelle="werkstoffe")
assert len(e) == 1 and e[0]["uid"] and e[0]["herkunft"] is None, e
ok("Protokoll: lokale Änderungen mit Arbeitsplatz, nur gemeinsame Einstellungen, Stammdaten je Kennung")

stand = teilen.protokoll_stand(pb.con)
pb.position_aendern(p1, "stueck", 6)
erst = eintraege(pb, stand)
pb.position_aendern(p1, "stueck", 7)
pb.position_aendern(p1, "laenge", 1200)
e = eintraege(pb, stand)
assert [(x["tabelle"], x["uid"], x["art"]) for x in e] == [("angebote", u1, "geaendert")], e
assert e[0]["nr"] > max(x["nr"] for x in erst)
ok("Mehrere Änderungen an einem Angebot hintereinander: ein Eintrag mit neuer Nummer")

teilen.abgleichen(pb)
ordner = gemeinsam / "Rohrlaser_PB"
assert (ordner / "haupt.sqlite").is_file() and (ordner / "Angebote_2026-09.sqlite").is_file()
assert not (gemeinsam / "Rohrlaser_PB.sqlite").exists()
info = teilen.info_lesen(ordner)
assert info["protokoll"] == teilen.protokoll_stand(pb.con) and info["uhr"].startswith("20"), info
assert info["installation"] == platz
ok("Ablage über den Austauschweg im gleichen Aufbau; Info mit Protokollstand und Uhrzeit")

mk = arbeitsplatz("Martin", "MK")
teilen.abgleichen(mk, teilen.UEBERNEHMEN)
fremd = mk.con.execute("SELECT id, uid FROM angebote WHERE fremd='PB' AND uid=?", (u1,)).fetchone()
assert fremd, "fremde Kopie mit derselben Kennung"
assert mk.con.execute("SELECT uid FROM positionen WHERE angebot_id=?", (fremd[0],)).fetchone()[0] == pu1
ab = eintraege(mk, tabelle="angebote", uid=u1)
assert ab and all(x["herkunft"] == "abgleich" for x in ab), ab
assert not mk.con.execute(f"SELECT 1 FROM {teilen.HERKUNFT}").fetchone()
stand_mk = teilen.protokoll_stand(mk.con)
mk.einstellung_setzen("gewinn", 14)
assert [x["herkunft"] for x in eintraege(mk, stand_mk)] == [None]
ok("Beim Kollegen: gleiche Kennungen, Herkunft „abgleich“, danach wieder lokal")

# ---------------------------------------------------------------- vorläufige Nummer wird endgültig: Kennung bleibt
weg_ordner = tmp / "nicht_da"
pb.einstellung_setzen("teilen_ordner", str(weg_ordner))
v = pb.angebot_neu(dict(kunde="Offline", datum="2026-10-30"))
nr_v = pb.angebot(v)["nummer"]
uv = pb.con.execute("SELECT uid FROM angebote WHERE id=?", (v,)).fetchone()[0]
assert nummern.vorlaeufig(nr_v), nr_v
pb.einstellung_setzen("teilen_ordner", str(gemeinsam))
nummern.endgueltig(pb)
assert not nummern.vorlaeufig(pb.angebot(v)["nummer"])
assert pb.con.execute("SELECT uid FROM angebote WHERE id=?", (v,)).fetchone()[0] == uv
ok("Vorläufige Nummer endgültig: Kennung bleibt")

# ---------------------------------------------------------------- ältere Datei, altes Protokoll
pfad = pb.pfad
pb.con.execute(f"INSERT INTO {teilen.PROTOKOLL} (tabelle, uid, art, zeit) VALUES ('kunden', 'x', 'neu', "
               "'2020-01-01T00:00:00.000')")
pb.con.commit()
pb.con.execute("UPDATE angebote SET uid=NULL")
pb.con.commit()
pb.con.close()
pb = Datenbank(pfad)
assert not pb.con.execute(f"SELECT 1 FROM {teilen.PROTOKOLL} WHERE uid='x'").fetchone()
assert all(r[0] for r in pb.con.execute("SELECT uid FROM angebote"))
c = sqlite3.connect(pfad)
trigger = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE '%protokoll'")}
c.close()
assert "einstellungen_insert_protokoll" in trigger and "netze_delete_protokoll" in trigger
ok("Beim Öffnen: alte Protokolleinträge weg, fehlende Kennungen vergeben, Trigger neu angelegt")

print("OK: Vorbereitung Server-Synchronisation (Austauschweg, Protokoll, Kennungen)")
