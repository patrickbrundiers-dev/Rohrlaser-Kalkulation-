"""Serverversion Paket S5: Lastprobe mit 25 Arbeitsplätzen gleichzeitig (Patrick 26.11.2026).

Echter zentraler Server, 25 echte Programm-Verbindungen (je eigener Login), mehrere Runden gleichzeitig: Puls,
Angebotsliste, Angebot mit echter Nummer aus dem gemeinsamen Nummernkreis anlegen, reservieren, Positionen,
gemeinsames Angebot reservieren (immer nur einer), Notizen. Erwartet: keine Fehler, keine doppelte Nummer,
95 % der Aktionen unter 1 s, Verbindungen unter der Grenze; danach sind Probe-Logins und -Daten wieder weg; die
Befehlszeile lasttest läuft (kleine Probe, Firmennummern bleiben unberührt).
Als root (initdb verweigert root) oder ohne PostgreSQL-Programme übersprungen.

Aufruf: python tests/test_server_last.py
"""
import os
import socket
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("ROHRLASER_PG_TEST", None)
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import datenspeicher, pg_lokal, server_betrieb as sb, server_last  # noqa: E402
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
server = sb.ZentralerServer(tmp / "Server", port=freier_port(), namen=("rohrlaser-srv",))
db = None
try:
    datei = server.einrichten("Testfirma", "PB", "Geheim-PB-123")
    os.environ["ROHRLASER_ARBEITSPLATZ"] = "PC-EINS"
    merk = tmp / "PC-EINS" / "Daten" / "rohrlaser.db"
    merk.parent.mkdir(parents=True)
    sb.verbinden_einrichten(merk, sb.zugangsdatei_lesen(datei), adresse="127.0.0.1")
    sb.anmelden("PB", "Geheim-PB-123")
    db = Datenbank(merk)                     # Verwalter: Programmtabellen am Server
    vorher = db.angebot_neu(dict(kunde="echter Kunde"))
    nr_vorher = db.angebot(vorher)["nummer"]
    db.schliessen()
    db = None

    zeilen = []
    b = server_last.lauf(server, plaetze=25, runden=4, nummern=True, melden=zeilen.append, grenze_s=3.0)  # geteilte Prüfrechner
    print("\n".join("       " + z for z in zeilen))
    assert not b["fehler"], b["fehler"][:5]
    assert b["nummern"] == 100 and not b["doppelt"], (b["nummern"], b["doppelt"])
    assert b["p95_s"] < 3.0, b["p95_s"]
    assert 25 < b["verbindungen_max"] <= sb.MAX_VERBINDUNGEN, b["verbindungen_max"]
    assert b["gemeinsam_gehalten"] >= 4, "je Runde hielt mindestens einer das gemeinsame Angebot"
    assert b["bestanden"]
    ok(f"25 Plätze × 4 Runden gleichzeitig: {b['aktionen']} Aktionen, 95 % unter {b['p95_s'] * 1000:.0f} ms, "
       "keine Fehler, keine doppelte Nummer")

    with server.verwalter_verbinden(sb.DATENBANK) as con:
        assert not [r for r in sb.benutzer_liste(con) if r["kuerzel"].startswith(server_last.PRAEFIX)]
        assert con.execute("SELECT count(*) FROM angebote").fetchone()[0] == 1
        assert con.execute("SELECT count(*) FROM positionen").fetchone()[0] == 0
        assert con.execute("SELECT count(*) FROM einstellungen WHERE name LIKE '@%%LASTPROBE%%' OR name LIKE "
                           "'@benutzer:X%%'").fetchone()[0] == 0
    ok("danach: Probe-Logins, -Angebote und -Einstellungen entfernt, echtes Angebot bleibt")

    # ein echter Mitarbeiter mit einem Kürzel wie die Probe wird nie benutzt oder aufgeräumt
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        sb.benutzer_anlegen(con, "XAB01", "Geheim-XAB-123", sb.RECHT_BEARBEITEN, name="Echt")
        con.execute("INSERT INTO angebote (nummer, kunde, bearbeiter) VALUES ('2026-ECHT', 'echt', 'XAB01')")
    merk_buchstaben = server_last._BUCHSTABEN
    server_last._BUCHSTABEN = "AB"
    aus = []
    try:
        assert sb.main(["lasttest", "--ordner", str(tmp / "Server"), "--port", str(server.port), "--plaetze", "3",
                        "--runden", "2"], ausgabe=aus.append) == 0, aus
    finally:
        server_last._BUCHSTABEN = merk_buchstaben
    assert any("bestanden" in z for z in aus), aus
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        assert [b["kuerzel"] for b in sb.benutzer_liste(con) if b["kuerzel"].startswith("X")] == ["XAB01"]
        assert con.execute("SELECT count(*) FROM angebote WHERE bearbeiter='XAB01'").fetchone()[0] == 1
    sb.anmelden("PB", "Geheim-PB-123")
    os.environ["ROHRLASER_ARBEITSPLATZ"] = "PC-EINS"
    db = Datenbank(merk)
    neu = db.angebot(db.angebot_neu(dict(kunde="danach")))["nummer"]
    assert neu != nr_vorher and not neu.startswith(server_last.NUMMER_PRAEFIX)
    assert db.con.execute("SELECT count(*) FROM angebote").fetchone()[0] == 3
    ok("Befehlszeile lasttest: läuft, eigene Probe-Kürzel je Lauf (echter Zugang XAB01 unberührt), verbraucht "
       "keine Firmennummern, Programm arbeitet danach normal")
finally:
    if db is not None:
        db.schliessen()
    datenspeicher.alle_stoppen()
    server.stoppen()
print("alle Prüfungen bestanden")
