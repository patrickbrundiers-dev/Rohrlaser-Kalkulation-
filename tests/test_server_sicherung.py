"""Serverversion Paket S6: Sicherung des zentralen Servers mit Rücksicherungsprobe (Patrick 26.11.2026).

Echter zentraler Server mit Arbeitsplatz und Daten:
- sichern: Abbild mit festem Stand, Zugänge, Prüfwerte; Rücksicherungsprobe spielt ein und vergleicht Zeile für
  Zeile; Ergebnis in der Serverinfo, Anzeige unter Datei → Datenbank, Verwalter-Warnung nur bei Bedarf;
  ältere tägliche Sicherungen über „behalten“ werden gelöscht; misslungene Probe wird gemeldet und gewarnt;
- zurueckholen: jetziger Stand vorher gesichert, Daten auf den Stand der Sicherung, Zugänge bleiben, Arbeitsplatz
  arbeitet danach normal weiter; auf einem NEUEN Server-Rechner kommen Zugänge und Daten aus der Sicherung;
- Befehlszeile sichern/sicherungen/zurueckholen/status/aufgaben.
Als root (initdb verweigert root) oder ohne PostgreSQL-Programme übersprungen.

Aufruf: python tests/test_server_sicherung.py
"""
import datetime
import os
import socket
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("ROHRLASER_PG_TEST", None)
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import datenspeicher, pg_lokal, server_betrieb as sb, server_sicherung as ss  # noqa: E402
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
PW, PW_AB = "Geheim-PB-123", "Geheim-AB-456"
server = sb.ZentralerServer(tmp / "Server", port=freier_port(), namen=("rohrlaser-srv",))
neu_server = sb.ZentralerServer(tmp / "NeuerServer", port=freier_port())
offen = []


def platz(srv, zugang, name, kuerzel, pw):
    os.environ["ROHRLASER_ARBEITSPLATZ"] = name
    merk = tmp / name / "Daten" / "rohrlaser.db"
    merk.parent.mkdir(parents=True, exist_ok=True)
    sb.verbinden_einrichten(merk, sb.zugangsdatei_lesen(zugang), adresse="127.0.0.1")
    sb.anmelden(kuerzel, pw)
    db = Datenbank(merk)
    offen.append(db)
    return db


def cli(*args, srv=None):
    srv = srv or server
    aus = []
    code = sb.main([args[0], "--ordner", str(srv.daten), "--port", str(srv.port), *args[1:]], ausgabe=aus.append)
    return code, aus


def ss_fehler(f, *args):
    try:
        f(*args, melden=None)
    except ss.SicherungFehler as e:
        return str(e)
    raise AssertionError(f"kein Fehler: {f.__name__}")


class Fenster:                       # genug vom Hauptfenster für die Warnung
    def __init__(self, db):
        self.db, self.meldungen = db, []

    def meldung(self, text, fehler=False):
        self.meldungen.append(text)


try:
    datei = server.einrichten("Testfirma", "PB", PW)
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        sb.benutzer_anlegen(con, "AB", PW_AB, sb.RECHT_BEARBEITEN, name="Anna Becker")
    db = platz(server, datei, "PC-EINS", "PB", PW)
    a1 = db.angebot_neu(dict(kunde="Müller GmbH"))
    db.position_neu(a1, dict(bezeichnung="Rohr Ø 42,4", menge=12))
    nr1 = db.angebot(a1)["nummer"]
    from rohrlaser import server_dialog
    f = Fenster(db)
    assert "noch keine" in server_dialog.sicherung_warnen(f), "ohne Sicherung warnen"
    f2 = Fenster(db)
    f2._sicherung_gewarnt = True
    assert server_dialog.sicherung_warnen(f2) is None, "nur einmal je Sitzung"
    ok("ohne Serversicherung wird der Verwalter gewarnt (einmal)")

    # ------------------------------------------------------------------ Sichern
    code, aus = cli("sichern")
    assert code == 0 and any("Zeile für Zeile gleich" in z for z in aus), aus
    s1 = ss.sicherungen(server)
    assert len(s1) == 1 and s1[0]["gut"] and s1[0]["anlass"] == ss.TAEGLICH, s1
    d1 = s1[0]["datei"]
    assert d1.parent == server.daten / "Sicherung" and d1.with_suffix(".rollen.sql").exists()
    assert "rl_ab" in d1.with_suffix(".rollen.sql").read_text(encoding="utf-8")
    if os.name != "nt":                 # nur der Eigentümer liest Daten und Prüfwerte der Passwörter
        assert (d1.parent.stat().st_mode & 0o077) == 0
        for endung in (".pgdump", ".rollen.sql", ".json"):
            assert (d1.with_suffix(endung).stat().st_mode & 0o077) == 0, endung
    with server.verwalter_verbinden() as con:
        assert not con.execute("SELECT datname FROM pg_database WHERE datname LIKE 'rl_probe%'").fetchall()
    i = sb.info_lesen(db.con)
    assert i["sicherung_probe"] == "ok" and i["sicherung_gut"] == i["sicherung_zeit"], i
    assert "Rücksicherungsprobe ok" in datenspeicher.status(db), datenspeicher.status(db)
    assert server_dialog.sicherung_warnen(Fenster(db)) is None, "frisch gesichert: keine Warnung"
    code, aus = cli("status")
    assert any("Serversicherung: zuletzt" in z for z in aus), aus
    ok("Sichern: Abbild + Zugänge + Prüfwerte, Rücksicherungsprobe gleich, Probe-Datenbank weg, Anzeige am Platz")

    alt = (datetime.datetime.now() - datetime.timedelta(hours=40)).isoformat(timespec="seconds")
    text, warnen = ss.zustand(dict(i, sicherung_gut=alt))
    assert warnen and "vor 1.7 Tagen" in text, text
    ok("Warnung, wenn die letzte gute Sicherung älter als 36 Stunden ist")

    # ------------------------------------------------------------------ Probe misslingt
    echt = ss._pruefwerte_in
    ss._pruefwerte_in = lambda srv, name: {**echt(srv, name), "angebote": [99, "x"]}
    try:
        code, aus = None, []
        try:
            ss.sichern(server, melden=aus.append)
            raise AssertionError("Probe-Fehler nicht gemeldet")
        except ss.SicherungFehler as e:
            assert "angebote" in str(e), e
    finally:
        ss._pruefwerte_in = echt
    i = sb.info_lesen(db.con)
    assert i["sicherung_probe"].startswith("FEHLER") and ss.zustand(i)[1]
    assert len(ss.sicherungen(server)) == 2 and not ss.sicherungen(server)[0]["gut"]
    ok("Misslingt die Rücksicherungsprobe: Fehler, Serverinfo FEHLER, Verwalter wird gewarnt")

    # ------------------------------------------------------------------ Behalten
    for _ in range(2):
        assert cli("sichern", "--behalten", "2")[0] == 0
    taeglich = [x for x in ss.sicherungen(server) if x["anlass"] == ss.TAEGLICH]
    assert len(taeglich) == 2 and d1 not in [x["datei"] for x in taeglich], taeglich
    assert not d1.exists() and not d1.with_suffix(".json").exists()
    ok("Ältere tägliche Sicherungen über --behalten hinaus gelöscht")

    # ------------------------------------------------------------------ Zurückholen
    stand = taeglich[0]["datei"]        # neueste: mit Angebot nr1
    ohne = tmp / "ohne_pruefwerte.pgdump"
    ohne.write_bytes(stand.read_bytes())
    assert "Prüfwerte" in ss_fehler(ss.zurueckholen, server, ohne), "ohne Prüfwerte nie einspielen"
    with db.con:
        db.con.execute("UPDATE angebote SET kunde='nach der Sicherung geändert' WHERE id=?", (a1,))
    a2 = db.angebot_neu(dict(kunde="nach der Sicherung neu"))
    nr2 = db.angebot(a2)["nummer"]
    code, aus = cli("zurueckholen", "--datei", str(stand))
    assert code == 0 and any("auf den Stand von" in z for z in aus), aus
    vorher = [x for x in ss.sicherungen(server) if x["anlass"] == "vor_Zurueckholen"]
    assert len(vorher) == 1 and vorher[0]["gut"], "jetziger Stand vorher gesichert"
    for d in offen:
        d.schliessen()
    offen.clear()
    db = platz(server, datei, "PC-EINS", "PB", PW)
    assert db.con.execute("SELECT kunde FROM angebote WHERE nummer=?", (nr1,)).fetchone()[0] == "Müller GmbH"
    assert db.con.execute("SELECT count(*) FROM angebote WHERE nummer=?", (nr2,)).fetchone()[0] == 0
    assert db.con.execute("SELECT count(*) FROM positionen").fetchone()[0] == 1
    a3 = db.angebot_neu(dict(kunde="nach dem Zurückholen"))
    assert db.angebot(a3)["nummer"] not in (nr1,)
    dab = platz(server, datei, "PC-ZWEI", "AB", PW_AB)
    assert dab.con.execute("SELECT count(*) FROM angebote").fetchone()[0] == 2
    with server.verwalter_verbinden() as con:
        assert len(con.execute("SELECT datname FROM pg_database WHERE datname LIKE 'rohrlaser\\_vor\\_%'").fetchall()) == 1
    ok("Zurückholen: vorher gesichert, Daten auf dem Stand der Sicherung, Zugänge und Arbeitsplätze arbeiten weiter")

    # ------------------------------------------------------------------ Neuer Server-Rechner
    neu_server.einrichten("Testfirma", "", "")      # ohne Administrator: alles kommt aus der Sicherung
    code, aus = cli("zurueckholen", "--datei", str(stand), srv=neu_server)
    assert code == 0 and any("Zugänge aus der Sicherung" in z and "rl_ab" in z for z in aus), aus
    zugang_neu = neu_server.zugang_schreiben()
    dneu = platz(neu_server, zugang_neu, "PC-DREI", "AB", PW_AB)
    assert dneu.con.execute("SELECT kunde FROM angebote WHERE nummer=?", (nr1,)).fetchone()[0] == "Müller GmbH"
    ok("Neuer Server-Rechner: Zugänge (mit Passwort) und Daten kommen aus der Sicherung")

    # ------------------------------------------------------------------ Liste, Aufgaben
    code, aus = cli("sicherungen")
    assert code == 0 and any("Probe ok" in z for z in aus) and "Sicherungen in" in aus[-1], aus
    liste = ss.aufgaben(server, r"C:\Rohrlaser\Rohrlaser-Angebotskalkulation.exe", r"D:\RohrlaserServer",
                        anlegen=False, konto=r"FIRMA\pb")
    assert [n for n, _z in liste] == ["Rohrlaser-Server starten", "Rohrlaser-Server Rechner",
                                      "Rohrlaser-Server Sicherung"]
    assert "DAILY" in liste[2][1] and "22:30" in liste[2][1] and "sichern" in liste[2][1], liste[2]
    assert all("/RU FIRMA\\pb" in z and "SYSTEM" not in z for _n, z in liste), liste
    assert ss.konto_vorgabe(), "Vorgabe: dieses Konto (Eigentümer des Datenordners)"
    ok("Befehlszeile sicherungen; Aufgaben für die Aufgabenplanung (Start, Rechner, tägliche Sicherung)")
finally:
    for d in offen:
        try:
            d.schliessen()
        except Exception:       # noqa: BLE001
            pass
    datenspeicher.alle_stoppen()
    server.stoppen()
    neu_server.stoppen()
print("alle Prüfungen bestanden")
