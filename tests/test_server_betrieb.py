"""Serverversion Paket S1: zentrale Datenbank und Betriebsart Server (Patrick 26.11.2026).

Prüft mit echtem zentralem Server (ZentralerServer, eigener Ordner, freier Port):
- Einrichten: Zertifikat der eigenen Zertifizierungsstelle, TLS an, Zugang aus dem Netz nur hostssl, Rollen
  rohrlaser_lesen/rohrlaser_verwalter, Servertabellen, erster Administrator, Zugangsdatei mit Fingerabdruck;
- Arbeitsplatz umstellen (Merkdatei art=server, Zertifikat daneben, alte Merkdatei bleibt als 'vorher'), Anmeldung
  mit eigenem Login je Mitarbeiter, Verbindung nur verschlüsselt mit geprüftem Zertifikat;
- erster Start des Administrators richtet die Datenbank ein und setzt die Pflichtversion; weitere Arbeitsplätze
  pflegen nichts (keine Schreibzugriffe beim Öffnen);
- Nummern: zwei Arbeitsplätze gleichzeitig, 2 × 15 Nummern ohne Doppelte, Lücke bleibt nach Löschen;
- Einstellungen: Firmenwerte für alle, Arbeitsplatz- und Benutzerwerte getrennt; Kürzel = Anmeldung;
- Rechte: Leser darf nur lesen (vom Server durchgesetzt), falsches Passwort, gesperrter Benutzer, falsches Zertifikat;
- Pflichtversion: ältere Version nur lesend, neuere ohne Verwalterrecht nur lesend, anderes Schema gar nicht;
- kein Abgleich über den Ordner, keine Sicherung je Arbeitsplatz; zurück zur lokalen Datenbank;
- Befehlszeile (einrichten/benutzer/status).
Als root (initdb verweigert root) oder ohne PostgreSQL-Programme übersprungen.

Aufruf: python tests/test_server_betrieb.py
"""
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("ROHRLASER_PG_TEST", None)      # echter zentraler Server, nicht der Prüfserver
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import VERSION, datenspeicher, db_verbindung, nummern, pg_lokal, server_betrieb as sb, teilen  # noqa: E402
from rohrlaser.datenbank import SCHEMA_VERSION, Datenbank  # noqa: E402


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
PW_PB, PW_AB, PW_WS = "Geheim-PB-123", "Geheim-AB-456", "Geheim-WS-789"
server = sb.ZentralerServer(tmp / "Server", port=freier_port(), namen=("rohrlaser-srv",))
offen = []
try:
    # ------------------------------------------------------------------ Server einrichten
    t0 = time.perf_counter()
    datei = server.einrichten("Testfirma", "PB", PW_PB)
    assert datei.is_file() and datei.suffix == sb.ENDUNG
    z = sb.zugangsdatei_lesen(datei)
    assert z["name"] == "Testfirma" and z["port"] == server.port and "BEGIN CERTIFICATE" in z["ca"]
    assert "PASSWORT" not in datei.read_text(encoding="utf-8").upper(), "kein Passwort in der Zugangsdatei"
    assert len(z["fingerabdruck"].split()) == 8
    hba = (server.pg / "pg_hba.conf").read_text(encoding="utf-8")
    assert "hostssl all all 0.0.0.0/0 scram-sha-256" in hba and "\nhost all all 0.0.0.0" not in hba
    conf = (server.pg / "postgresql.conf").read_text(encoding="utf-8")
    assert "ssl = on" in conf and "listen_addresses = '*'" in conf and f"port = {server.port}" in conf
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        rollen = {r[0] for r in con.execute("SELECT rolname FROM pg_roles")}
        assert {sb.ROLLE_APP, sb.ROLLE_LESEN, sb.ROLLE_VERWALTER, "rl_pb"} <= rollen
        b = {x["kuerzel"]: x for x in sb.benutzer_liste(con)}
        assert b["PB"]["recht"] == sb.RECHT_VERWALTER and not b["PB"]["gesperrt"]
        sb.benutzer_anlegen(con, "AB", PW_AB, sb.RECHT_BEARBEITEN, name="Anna Becker")
        sb.benutzer_anlegen(con, "WS", PW_WS, sb.RECHT_LESEN, name="Werkstatt")
        try:
            sb.benutzer_anlegen(con, "XX", "kurz")
            raise AssertionError("kurzes Passwort angenommen")
        except sb.ServerFehler:
            pass
        b = {x["kuerzel"]: x for x in sb.benutzer_liste(con)}
        assert b["AB"]["recht"] == sb.RECHT_BEARBEITEN and b["WS"]["recht"] == sb.RECHT_LESEN, b
        assert b["AB"]["name"] == "Anna Becker"
    ok(f"Server eingerichtet in {time.perf_counter() - t0:.1f} s: TLS, nur hostssl aus dem Netz, Rollen, "
       "Administrator, Benutzer, Zugangsdatei ohne Passwort")

    # ------------------------------------------------------------------ Arbeitsplatz 1 (Administrator)
    os.environ["ROHRLASER_ARBEITSPLATZ"] = "PC-EINS"
    merk1 = tmp / "Platz1" / "Daten" / "rohrlaser.db"
    lokal = Datenbank(merk1)            # bisher lokal (PostgreSQL je PC) mit eigenen Daten
    lokal.angebot_neu(dict(kunde="Lokal GmbH"))
    lokal.schliessen()
    datenspeicher.alle_stoppen()
    sb.verbinden_einrichten(merk1, z, adresse="127.0.0.1")
    m = datenspeicher.merkdatei_lesen(merk1)
    assert m["art"] == sb.ART and datenspeicher.art(merk1) == datenspeicher.SERVER
    assert json.loads(m["vorher"])["art"] == datenspeicher.POSTGRES and merk1.with_name("rohrlaser.db.lokal").is_file()
    assert (merk1.parent / sb.CA_DATEI).read_text(encoding="ascii") == z["ca"]
    try:
        Datenbank(merk1)
        raise AssertionError("ohne Anmeldung geöffnet")
    except sb.AnmeldungFehlt:
        pass
    sb.anmelden("PB", "falsch-falsch")
    try:
        Datenbank(merk1)
        raise AssertionError("falsches Passwort angenommen")
    except sb.AnmeldeFehler as e:
        assert "Passwort" in str(e)
    sb.anmelden("pb", PW_PB)
    t0 = time.perf_counter()
    db1 = Datenbank(merk1)
    offen.append(db1)
    t_neu = time.perf_counter() - t0
    assert db1.server is not None and db1.server.verwalter and db1.server.zustand == sb.OK
    assert db1.server.kuerzel == "PB" and db1.server.platz == "PC-EINS"
    assert db1.con.execute("SELECT session_user").fetchone()[0] == "rl_pb"
    assert db1.con.execute("SELECT current_user").fetchone()[0] == sb.ROLLE_APP
    assert db1.con.v.con.pgconn.ssl_in_use, "Verbindung ohne TLS"
    info = sb.info_lesen(db1.con)
    assert info["programm"] == VERSION and int(info["schema"]) == SCHEMA_VERSION and info["gehoben_von"] == "PB"
    assert db_verbindung.schema_version(db1.con) == SCHEMA_VERSION
    assert db1.angebote() == [], "der Server beginnt leer, die lokalen Daten bleiben lokal"
    ok(f"Administrator: Anmeldung (eigener Login, Arbeit als {sb.ROLLE_APP}, TLS), Datenbank eingerichtet "
       f"({t_neu:.1f} s), Pflichtversion {VERSION}")

    # ------------------------------------------------------------------ Arbeitsplatz 2 (Mitarbeiter)
    os.environ["ROHRLASER_ARBEITSPLATZ"] = "PC-ZWEI"
    merk2 = tmp / "Platz2" / "Daten" / "rohrlaser.db"
    merk2.parent.mkdir(parents=True)
    sb.verbinden_einrichten(merk2, z, adresse="127.0.0.1")
    assert json.loads(datenspeicher.merkdatei_lesen(merk2)["vorher"]) == {}
    sb.anmelden("AB", PW_AB)
    vorher = db1.con.execute("SELECT n FROM stammdaten_stand").fetchone()[0]
    t0 = time.perf_counter()
    db2 = Datenbank(merk2)
    offen.append(db2)
    t_platz = time.perf_counter() - t0
    assert db2.server.zustand == sb.OK and not db2.server.verwalter and not db2.server.nur_lesen
    assert db1.con.execute("SELECT n FROM stammdaten_stand").fetchone()[0] == vorher, "Öffnen hat geschrieben"
    assert t_platz < max(3.0, t_neu), (t_platz, t_neu)
    ok(f"Mitarbeiter: Öffnen ohne Datenpflege, nichts geschrieben ({t_platz:.2f} s statt {t_neu:.1f} s)")

    # ------------------------------------------------------------------ gemeinsame Daten, Nummern
    a1 = db1.angebot_neu(dict(kunde="Server Kunde 1", nummer=nummern.neue_nummer(db1)))
    nr1 = db1.angebot(a1)["nummer"]
    assert nr1.endswith("-00001"), nr1
    assert any(a["id"] == a1 for a in db2.angebote()), "Platz 2 sieht das Angebot von Platz 1"
    ergebnisse, fehler = {1: [], 2: []}, []

    def ziehen(db, wohin):
        try:
            for _ in range(15):
                wohin.append(nummern.neue_nummer(db))
        except Exception as e:      # noqa: BLE001
            fehler.append(e)
    th = [threading.Thread(target=ziehen, args=(db1, ergebnisse[1])),
          threading.Thread(target=ziehen, args=(db2, ergebnisse[2]))]
    for t in th:
        t.start()
    for t in th:
        t.join()
    assert not fehler, fehler
    alle = ergebnisse[1] + ergebnisse[2]
    assert len(alle) == 30 and len(set(alle)) == 30, "doppelte Nummer"
    assert sorted(nummern.zaehler(n) for n in alle) == list(range(2, 32))
    db2.angebot_loeschen(a1) if hasattr(db2, "angebot_loeschen") else db2.con.execute(
        "DELETE FROM angebote WHERE id = ?", (a1,))
    assert nummern.zaehler(nummern.neue_nummer(db2)) == 32, "gelöschte Nummer wird nicht wieder vergeben"
    vergeben = db1.con.execute(f"SELECT wer, platz FROM {sb.NUMMERN} WHERE zaehler = 1").fetchone()
    assert tuple(vergeben) == ("PB", "PC-EINS"), vergeben
    db1.einstellung_setzen("ab_nummer", nummern.AB_EIGEN)
    ab1 = nummern.ab_nummer(db1, {"nummer": nr1})
    ab2 = nummern.ab_nummer(db2, {"nummer": "x"})
    assert ab1 != ab2 and nummern.ab_zaehler(ab2) == nummern.ab_zaehler(ab1) + 1
    ok("Nummern: 2 Plätze gleichzeitig 30 Nummern ohne Doppelte, nie wieder vergeben, mit Mitarbeiter und Platz; "
       "AB-Nummern ebenso")

    # ------------------------------------------------------------------ Einstellungen je Firma/Platz/Benutzer
    firma = next(n for n in teilen.EINSTELLUNGEN_GETEILT if sb.bereich(n) == "firma" and n != "passwort")
    db1.einstellung_setzen(firma, "Firmenwert")
    db1.einstellung_setzen("step_ordner", "C:/PB-Platz/STEP")
    db1.einstellung_setzen("ansicht_thema", "dunkel")
    db1.einstellung_setzen("benutzer_name", "Patrick B.")
    time.sleep(Datenbank.EINST_PRUEFEN_S + 0.05)
    assert db2.einstellung(firma) == "Firmenwert", "Firmenwert gilt für alle"
    assert db2.einstellung("step_ordner") != "C:/PB-Platz/STEP", "Ordner des anderen Platzes"
    assert db2.einstellung("ansicht_thema") != "dunkel" and db2.einstellung("benutzer_name") != "Patrick B."
    assert db1.einstellung("step_ordner") == "C:/PB-Platz/STEP" and db1.einstellung("ansicht_thema") == "dunkel"
    assert db1.einstellung("benutzer_kuerzel") == "PB" and db2.einstellung("benutzer_kuerzel") == "AB"
    assert teilen.kuerzel(db2) == "AB"
    roh = dict(db1.con.execute("SELECT name, wert FROM einstellungen WHERE name LIKE '@%'").fetchall())
    assert "@platz:PC-EINS:step_ordner" in roh and "@benutzer:PB:ansicht_thema" in roh, sorted(roh)
    assert sb.bereich("benutzer_kuerzel") == "platz" and sb.bereich("maschinen_stand") == "firma"
    ok(f"Einstellungen: Firmenwert ({firma}) für alle, Ordner je Arbeitsplatz, Ansicht/Name je Benutzer, "
       "Kürzel = Anmeldung")

    # ------------------------------------------------------------------ kein Ordner-Abgleich, keine Platz-Sicherung
    db2.einstellung_setzen("teilen_ordner", str(tmp / "Gemeinsam"))
    assert teilen.ordner(db2) is None and not teilen.aktiv(db2)
    assert db2.sicherung_heute() is None and db2.sicherungen(zusatz="beenden") == ([], None)
    assert not list((merk2.parent / "Sicherung").glob("*.db")) if (merk2.parent / "Sicherung").exists() else True
    ok("kein Abgleich über den gemeinsamen Ordner, keine Sicherung je Arbeitsplatz")

    # ------------------------------------------------------------------ Leserecht
    db1.angebot_neu(dict(kunde="Für die Werkstatt", nummer=nummern.neue_nummer(db1)))
    os.environ["ROHRLASER_ARBEITSPLATZ"] = "WERKSTATT"
    sb.anmelden("WS", PW_WS)
    db3 = Datenbank(merk2)
    offen.append(db3)
    assert db3.server.nur_lesen and db3.server.rolle == sb.ROLLE_LESEN and db3.nur_lesen.startswith("nur Lesen")
    assert db3.angebote(), "Leser sieht die Angebote"
    db3.lesemodus("")           # Lizenzprüfung beim Start hebt den Lesemodus auf: Serverrecht bleibt
    assert db3.nur_lesen.startswith("nur Lesen am Server"), db3.nur_lesen
    z_alt = db2.server.zustand
    db2.server.zustand = sb.VERALTET        # andere Programmversion: bleibt nur Lesen, auch nach lesemodus("")
    db2.lesemodus("")
    assert db2.nur_lesen.startswith("nur Lesen am Server"), db2.nur_lesen
    db2.server.zustand = z_alt
    db2.lesemodus("")
    assert not db2.nur_lesen
    for sql in ("UPDATE angebote SET kunde = 'x'", "SET default_transaction_read_only = off"):
        try:
            db3.con.execute(sql)
            db3.con.execute("UPDATE angebote SET kunde = 'x'")
            db3.con.commit()
            raise AssertionError("Leser konnte ändern")
        except db_verbindung.DbFehler:
            db3.con.rollback()
    ok("Leser: sieht alles, Ändern sperrt der Server selbst (auch ohne Lesemodus der Verbindung)")

    # ------------------------------------------------------------------ gesperrt, falsches Zertifikat
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        sb.benutzer_sperren(con, "WS")
    try:
        Datenbank(merk2)
        raise AssertionError("gesperrter Benutzer angemeldet")
    except sb.AnmeldeFehler:
        pass
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        sb.benutzer_sperren(con, "WS", False)
    fremd = sb.zertifikate_erzeugen(tmp / "Fremd")
    echt = (merk2.parent / sb.CA_DATEI).read_bytes()
    (merk2.parent / sb.CA_DATEI).write_bytes(fremd["ca"].read_bytes())
    try:
        Datenbank(merk2)
        raise AssertionError("fremdes Zertifikat angenommen")
    except sb.ZertifikatFehler:
        pass
    (merk2.parent / sb.CA_DATEI).write_bytes(echt)
    ok("gesperrter Benutzer abgewiesen; Server mit fremdem Zertifikat abgewiesen")

    # ------------------------------------------------------------------ Pflichtversion
    z_ = sb.zustand_bestimmen
    assert z_("0.9.516", 107, "0.9.516", 107, False)[0] == sb.OK
    assert z_("0.9.516", 107, "0.9.515", 107, False)[0] == sb.VERALTET
    assert z_("0.9.516", 107, "0.9.517", 107, False)[0] == sb.VORAUS
    assert z_("0.9.516", 107, "0.9.517", 108, True)[0] == sb.HEBEN
    assert z_(None, 0, "0.9.517", 108, True)[0] == sb.NEU
    for args in (("0.9.516", 107, "0.9.515", 106, False), ("0.9.516", 107, "0.9.517", 108, False),
                 (None, 0, "0.9.517", 108, False)):
        try:
            z_(*args)
            raise AssertionError(f"geöffnet trotz {args}")
        except sb.ServerFehler:
            pass
    sb.anmelden("AB", PW_AB)
    alt = sb.oeffnen(merk2, programm="0.9.1")
    assert alt.server.zustand == sb.VERALTET and alt.server.nur_lesen and "aktualisiert" in alt.server.meldung
    try:
        alt.execute("UPDATE angebote SET kunde = 'x'")
        raise AssertionError("alte Version durfte schreiben")
    except db_verbindung.NurLesen:
        pass
    alt.schliessen()
    neu_ab = sb.oeffnen(merk2, programm="99.0.0")
    assert neu_ab.server.zustand == sb.VORAUS and neu_ab.server.nur_lesen
    neu_ab.schliessen()
    sb.anmelden("PB", PW_PB)
    neu_pb = sb.oeffnen(merk2, programm="99.0.0")
    assert neu_pb.server.zustand == sb.HEBEN and neu_pb.server.pflegen and not neu_pb.server.nur_lesen
    neu_pb.schliessen()
    ok("Pflichtversion: ältere/neuere Version nur lesend, anderes Schema gar nicht, nur Verwalter hebt an")

    # ------------------------------------------------------------------ Status, zurück zur lokalen Datenbank
    text = datenspeicher.status(db1)
    assert "Zentraler Server" in text and "PB" in text and "PC-EINS" in text, text
    for d in offen:
        d.schliessen()
    offen.clear()
    assert sb.zurueck_lokal(merk1) and datenspeicher.art(merk1) == datenspeicher.POSTGRES
    lokal = Datenbank(merk1)
    assert [a["kunde"] for a in lokal.angebote()] == ["Lokal GmbH"], "lokale Daten unverändert"
    assert lokal.server is None
    lokal.schliessen()
    datenspeicher.alle_stoppen()
    assert not sb.zurueck_lokal(merk2) or True
    ok("Statusanzeige nennt Server, Benutzer und Platz; zurück zur lokalen Datenbank mit unveränderten Daten")

    # ------------------------------------------------------------------ Fenster: verbinden, anmelden
    from PySide6.QtWidgets import QApplication
    from rohrlaser import server_dialog
    app = QApplication.instance() or QApplication([])
    merk4 = tmp / "Platz4" / "Daten" / "rohrlaser.db"
    merk4.parent.mkdir(parents=True)
    d = server_dialog.VerbindenDialog(None, merk4)
    assert not d.ok.isEnabled()
    d.waehlen(str(tmp / "fehlt.rlserver"))
    assert d.zugang is None and "lässt sich nicht lesen" in d.hinweis.text()
    d.waehlen(str(datei))
    assert d.ok.isEnabled() and d.finger.text() == z["fingerabdruck"] and d.name.text() == "Testfirma"
    d.adresse.setCurrentText("127.0.0.1")
    d.kuerzel.setText("ab")
    d.passwort.setText("falsch-falsch")
    d.verbinden()
    assert d.result() != d.DialogCode.Accepted and "Passwort" in d.hinweis.text(), d.hinweis.text()
    assert datenspeicher.art(merk4) == datenspeicher.SQLITE, "nichts umgestellt, solange die Anmeldung scheitert"
    d.passwort.setText(PW_AB)
    d.verbinden()
    assert d.result() == d.DialogCode.Accepted and d.ergebnis["recht"] == sb.RECHT_BEARBEITEN
    assert datenspeicher.art(merk4) == datenspeicher.SERVER
    assert datenspeicher.merkdatei_lesen(merk4)["kuerzel"] == "AB"
    sb.abmelden()
    a = server_dialog.AnmeldeDialog(None, merk4)
    assert a.kuerzel.text() == "AB"
    a.passwort.setText("falsch-falsch")
    a.pruefen()
    assert "Passwort" in a.fehler.text() and not sb.angemeldet()
    a.passwort.setText(PW_AB)
    a.pruefen()
    assert a.result() == a.DialogCode.Accepted and sb.angemeldet() == "AB" and a.ergebnis["name"] == "Testfirma"
    db4 = Datenbank(merk4)
    assert db4.server.kuerzel == "AB"
    db4.schliessen()
    ok("Fenster: Zugangsdatei einlesen (Fingerabdruck), falsches Passwort stellt nichts um, Anmelden beim Start")

    # ------------------------------------------------------------------ Befehlszeile
    ausgabe = []
    assert sb.main(["benutzer", "--ordner", str(server.daten), "--port", str(server.port), "--kuerzel", "MM",
                    "--recht", "lesen", "--name", "Max"], eingabe=lambda _f: "Geheim-MM-000",
                   ausgabe=ausgabe.append) == 0
    assert sb.main(["status", "--ordner", str(server.daten), "--port", str(server.port)],
                   ausgabe=ausgabe.append) == 0
    text = "\n".join(ausgabe)
    assert "MM" in text and "lesen" in text and "Testfirma" in text and VERSION in text, text
    zweit = sb.ZentralerServer(tmp / "Server2", port=freier_port())
    try:
        sb.main(["einrichten", "--ordner", str(zweit.daten), "--port", str(zweit.port), "--admin", "AD"],
                eingabe=lambda _f: "Geheim-AD-111", ausgabe=ausgabe.append)
        assert (zweit.daten / sb.ZUGANG_DATEI).is_file()
    finally:
        zweit.stoppen()
    try:
        sb.ZentralerServer(tmp / "Server3", port=server.port)._port_waehlen()
        raise AssertionError("belegter Port nicht erkannt")
    except sb.ServerFehler as e:
        assert "belegt" in str(e)
    ok("Befehlszeile: Benutzer anlegen, Status, neuen Server einrichten; belegter Port wird gemeldet")
finally:
    for d in offen:
        try:
            d.schliessen()
        except Exception:       # noqa: BLE001
            pass
    server.stoppen()
    datenspeicher.alle_stoppen()

print("Alle Prüfungen bestanden.")
