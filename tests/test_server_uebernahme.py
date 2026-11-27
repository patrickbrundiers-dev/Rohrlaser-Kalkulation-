"""Serverversion Paket S5: verlustfreie Übernahme der bisherigen Daten in den zentralen Server (Patrick 26.11.2026).

Prüft mit echtem zentralem Server: ein bisheriger PC (hier ein zweiter Server als Stand-in, gleiche Programmtabellen)
mit Angeboten, Positionen, Netzen, Staffeln, Einstellungen und einer Kopie eines Kollegen-Angebots schreibt eine
Export-Datei; am Server:
- uebernehmen: alles kommt an, jede Tabelle Zeile für Zeile gleich der Quelle; Kopien der Kollegen werden deren
  Angebote; Einstellungen je Arbeitsplatz des Servers bleiben; vorher Sicherung; Arbeitsplätze sehen die Daten;
- zweites Übernehmen ohne --ersetzen abgelehnt, anderes Schema abgelehnt;
- vergleichen erkennt eine Abweichung; dazunehmen: eigene Angebote des weiteren PCs ersetzen/kommen dazu, fremde
  nicht, unveränderte bleiben; Befehlszeile.
Als root (initdb verweigert root) oder ohne PostgreSQL-Programme übersprungen.

Aufruf: python tests/test_server_uebernahme.py
"""
import os
import socket
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("ROHRLASER_PG_TEST", None)      # echter zentraler Server, nicht der Prüfserver
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import datenspeicher, db_verbindung, pg_lokal, server_betrieb as sb  # noqa: E402
from rohrlaser import server_uebernahme as su  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK     " + text)


if hasattr(os, "getuid") and os.getuid() == 0:
    print("übersprungen: initdb läuft nicht als root")
    sys.exit(0)
try:
    pg_lokal.programme()
except pg_lokal.PgFehlt:
    print("übersprungen: keine PostgreSQL-Programme")
    sys.exit(0)


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


tmp = Path(tempfile.mkdtemp())
PW = "Geheim-PB-123"
server = sb.ZentralerServer(tmp / "Server", port=freier_port(), namen=("rohrlaser-srv",))
alt = sb.ZentralerServer(tmp / "AltPC", port=freier_port())
offen = []


def platz(srv, name, kuerzel, pw):
    os.environ["ROHRLASER_ARBEITSPLATZ"] = name
    merk = tmp / name / "Daten" / "rohrlaser.db"
    merk.parent.mkdir(parents=True, exist_ok=True)
    zugang = srv.einrichten("Firma", "PB", PW) if not srv.angelegt else srv.zugang_schreiben()
    sb.verbinden_einrichten(merk, sb.zugangsdatei_lesen(zugang), adresse="127.0.0.1")
    sb.anmelden(kuerzel, pw)
    db = Datenbank(merk)
    offen.append(db)
    return db


def fehler(f, *args, **kw):
    try:
        f(*args, **kw)
    except sb.ServerFehler as e:
        return str(e)
    raise AssertionError(f"kein Fehler: {f.__name__}")


try:
    # ------------------------------------------------------------------ bisheriger PC mit Daten
    pc = platz(alt, "ALT-PC", "PB", PW)
    a1 = pc.angebot_neu(dict(kunde="Müller GmbH", projekt="Geländer Ø 42,4"))
    p1 = pc.position_neu(a1, dict(bezeichnung="Rohr 40x40x2", menge=12, laenge=1234.5))
    pc.position_neu(a1, dict(bezeichnung="Halter", menge=3))
    with pc.con:
        pc.con.execute(db_verbindung.NETZ_SETZEN, (p1, b"\x00\x01Netz\xff" * 50))
    a2 = pc.angebot_neu(dict(kunde="Kunde Zwei"))
    a3 = pc.angebot_neu(dict(kunde="Kopie von AB"))
    with pc.con:
        pc.con.execute("UPDATE angebote SET fremd='AB', bearbeiter=NULL, fremd_stand='2026-11-20' WHERE id=?", (a3,))
    with pc.con:            # wie an einem Einzelplatz: Firmenwert ohne Arbeitsplatz-Vorsatz
        pc.con.execute("INSERT INTO einstellungen (name, wert) VALUES ('ausschuss_regeln', ?) ON CONFLICT (name) DO "
                       "UPDATE SET wert=excluded.wert", ('"Rohrlaser Test – ÄÖÜ ß"',))
    nummern = {i: pc.angebot(i)["nummer"] for i in (a1, a2, a3)}
    export = tmp / "Export_PB.zip"
    pc.exportieren(export)
    ok("bisheriger PC: Export mit Angeboten, Positionen, Netz, Einstellungen, Kopie eines Kollegen-Angebots")

    # ------------------------------------------------------------------ Server
    db1 = platz(server, "PC-EINS", "PB", PW)          # Verwalter: legt die Programmtabellen an
    db1.einstellung_setzen("@platz:PC-EINS:rechnen_ort", "server")
    with db1.con:
        db1.con.execute("INSERT INTO einstellungen (name, wert) VALUES ('@platz:PC-EINS:nur_am_server', 'x') "
                        "ON CONFLICT (name) DO UPDATE SET wert='x'")
    zeilen = []
    b = su.uebernehmen(server, export, melden=zeilen.append)
    assert b["fremd"] == 1 and b["angebote"] == 3, b
    assert all(e["gleich"] for e in b["tabellen"].values()), {t: e for t, e in b["tabellen"].items() if not e["gleich"]}
    assert b["sicherung"].exists() and b["sicherung"].parent.name == su.SICHERUNG_ORDNER
    assert any("Zeile für Zeile" in z for z in zeilen), zeilen
    for t in ("angebote", "positionen", "netze", "einstellungen", "preise"):
        assert t in b["tabellen"], t
    with su.verbinden(server) as con:
        r = con.execute("SELECT bearbeiter, fremd, fremd_stand FROM angebote WHERE nummer=?",
                        (nummern[a3],)).fetchone()
        assert tuple(r) == ("AB", None, None), r
        assert con.execute("SELECT wert FROM einstellungen WHERE name='@platz:PC-EINS:nur_am_server'"
                           ).fetchone()[0] == "x", "Einstellung je Platz am Server bleibt"
        netz = con.execute("SELECT n.daten FROM netze n JOIN positionen p ON p.id=n.position_id "
                           "JOIN angebote a ON a.id=p.angebot_id WHERE a.nummer=?", (nummern[a1],)).fetchone()[0]
        assert bytes(netz) == b"\x00\x01Netz\xff" * 50
        n = con.execute("SELECT count(*) FROM server_protokoll WHERE art='uebernahme'").fetchone()[0]
        assert n == 1
    k = db1.con.execute("SELECT kunde, projekt FROM angebote WHERE nummer=?", (nummern[a1],)).fetchone()
    assert tuple(k) == ("Müller GmbH", "Geländer Ø 42,4"), k
    db1.__dict__.pop("_einst_merk", None)      # Merker prüft den Zähler nur alle paar Sekunden
    assert db1.einstellung("ausschuss_regeln") == "Rohrlaser Test – ÄÖÜ ß"
    ok("Übernehmen: alle Tabellen Zeile für Zeile gleich, Kopie wird Angebot von AB, Platz-Einstellung bleibt, "
       "Sicherung vorher, Arbeitsplatz sieht alles")

    # ------------------------------------------------------------------ Schutz
    assert "--ersetzen" in fehler(su.uebernehmen, server, export, melden=None)
    falsch = tmp / "falsch.db"
    with zipfile.ZipFile(export) as z:
        falsch.write_bytes(z.read("rohrlaser.db"))
    s = sqlite3.connect(falsch)
    s.execute("PRAGMA user_version=3")
    s.commit()
    s.close()
    assert "Schema 3" in fehler(su.uebernehmen, server, falsch, ersetzen=True, melden=None)
    ok("Schutz: zweites Übernehmen nur mit --ersetzen, anderes Schema abgelehnt")

    # ------------------------------------------------------------------ Vergleichen
    aus = []
    assert sb.main(["vergleichen", "--ordner", str(tmp / "Server"), "--port", str(server.port), "--datei",
                    str(export)], ausgabe=aus.append) == 1, aus     # Kopie umgestellt -> angebote anders
    assert any("angebote" in z for z in aus), aus
    with db1.con:
        db1.con.execute("UPDATE angebote SET kunde='Am Server geändert' WHERE nummer=?", (nummern[a2],))
    with su.quelle_oeffnen(export) as (q, _i), su.verbinden(server) as con:
        e = su.vergleichen(q, con)
    assert not e["angebote"]["gleich"] and e["positionen"]["gleich"], e["angebote"]
    ok("Vergleichen erkennt jede Abweichung (nur lesen)")

    # ------------------------------------------------------------------ Dazunehmen (weiterer PC: AB)
    with pc.con:
        pc.con.execute("UPDATE angebote SET fremd=NULL, fremd_stand=NULL, bearbeiter='AB', kunde='AB hat geändert' "
                       "WHERE id=?", (a3,))
        pc.con.execute("UPDATE angebote SET kunde='nur Kopie bei AB' WHERE id=?", (a1,))   # PB: nicht übernehmen
    pc.position_neu(a3, dict(bezeichnung="Neu bei AB", menge=7))
    a4 = pc.angebot_neu(dict(kunde="Neu bei AB"))
    with pc.con:
        pc.con.execute("UPDATE angebote SET bearbeiter='AB' WHERE id=?", (a4,))
    nr4 = pc.angebot(a4)["nummer"]
    export_ab = tmp / "Export_AB.zip"
    pc.exportieren(export_ab)
    aus = []
    assert sb.main(["dazunehmen", "--ordner", str(tmp / "Server"), "--port", str(server.port), "--datei",
                    str(export_ab), "--kuerzel", "ab"], ausgabe=aus.append) == 0
    assert any("1 neu, 1 ersetzt" in z for z in aus), aus
    with su.verbinden(server) as con:
        r = con.execute("SELECT kunde, bearbeiter, fremd FROM angebote WHERE nummer=?", (nummern[a3],)).fetchone()
        assert tuple(r) == ("AB hat geändert", "AB", None), r
        assert con.execute("SELECT count(*) FROM positionen p JOIN angebote a ON a.id=p.angebot_id WHERE a.nummer=?",
                           (nummern[a3],)).fetchone()[0] == 1
        assert con.execute("SELECT bearbeiter FROM angebote WHERE nummer=?", (nr4,)).fetchone()[0] == "AB"
        assert con.execute("SELECT kunde FROM angebote WHERE nummer=?", (nummern[a1],)).fetchone()[0] == \
            "Müller GmbH", "Angebot von PB bleibt"
    b2 = su.dazunehmen(server, export_ab, "AB", melden=None)
    assert b2["gleich"] == sorted([nummern[a3], nr4]) or set(b2["gleich"]) == {nummern[a3], nr4}, b2
    assert not b2["neu"] and not b2["ersetzt"] and not b2["fehler"], b2
    assert "--kuerzel" in fehler(su.dazunehmen, server, export_ab, "", melden=None)
    ok("Dazunehmen: eigene Angebote von AB ersetzt/neu und geprüft, fremde nicht, zweites Mal alles gleich")

    # ------------------------------------------------------------------ Befehlszeile übernehmen mit --ersetzen
    aus = []
    assert sb.main(["uebernehmen", "--ordner", str(tmp / "Server"), "--port", str(server.port), "--datei",
                    str(export), "--ersetzen"], ausgabe=aus.append) == 0, aus
    assert any("alles gleich" in z for z in aus), aus
    with su.verbinden(server) as con:
        assert con.execute("SELECT count(*) FROM angebote").fetchone()[0] == 3
        assert len(list((server.daten / su.SICHERUNG_ORDNER).glob("*.db"))) >= 3
    ok("Befehlszeile: uebernehmen --ersetzen setzt den Server auf den Export zurück (mit Sicherung)")

    # ------------------------------------------------------------------ Abweichung -> alles zurück
    echt = su.vergleichen
    su.vergleichen = lambda *a, **k: dict(echt(*a, **k), positionen=dict(quelle=5, server=4, gleich=False))
    try:
        assert "zurückgenommen" in fehler(su.uebernehmen, server, export_ab, ersetzen=True, melden=None)
    finally:
        su.vergleichen = echt
    with su.verbinden(server) as con:
        assert con.execute("SELECT count(*) FROM angebote").fetchone()[0] == 3, "Stand vor dem Versuch"
        assert con.execute("SELECT bearbeiter FROM angebote WHERE nummer=?", (nummern[a3],)).fetchone()[0] == "AB"
    ok("Weicht nach dem Einlesen etwas ab, kommt der gesicherte Stand zurück (nichts Halbes im Server)")
finally:
    for db in offen:
        try:
            db.schliessen()
        except Exception:       # noqa: BLE001
            pass
    datenspeicher.alle_stoppen()
    server.stoppen()
    alt.stoppen()
print("alle Prüfungen bestanden")
