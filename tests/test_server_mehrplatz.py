"""Serverversion Paket S2: Mehrbenutzerbetrieb am zentralen Server (Patrick 26.11.2026).

Prüft mit echtem zentralem Server und zwei Arbeitsplätzen (PB Verwalter, AB bearbeiten):
- Anwesenheit: Puls je Platz, wer ist da, wer bearbeitet welches Angebot (teilen.lebenszeichen/kollegen_offen wie im
  Ordnerbetrieb), Programmende meldet ab und gibt Reservierungen frei;
- Reservierung je Angebot: der zweite Platz bekommt den Inhaber zurück, nach Ablauf ohne Puls ist sie frei,
  Übernehmen mit Protokoll, der bisherige Platz merkt den Verlust beim nächsten Puls;
- Live: Änderung an einem Angebot und Reservierungswechsel kommen beim anderen Platz über LISTEN/NOTIFY an, eigene
  Änderungen nicht; Wiederverbinden nach Abbruch;
- Stammdaten-Zähler bleibt beim Puls unverändert (server_… zählen nicht als Stammdaten);
- Benutzer über die Programmrollen: anlegen mit Passwort (Login am Server), Administrator → Verwalter, nur Sehen →
  Leserecht, sperren, entfernen; letzter Verwalter und eigener Zugang geschützt; nur Verwalter dürfen;
- Änderungsverlauf mit Kürzel im Serverbetrieb;
- Oberfläche: Angebot öffnen reserviert, zweiter Platz sieht es nur an (Leiste mit Inhaber, Übernehmen), Schließen
  gibt frei, Liste zeigt „in Bearbeitung“.
Als root (initdb verweigert root) oder ohne PostgreSQL-Programme übersprungen.

Aufruf: python tests/test_server_mehrplatz.py
"""
import os
import socket
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("ROHRLASER_PG_TEST", None)      # echter zentraler Server, nicht der Prüfserver
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import datenspeicher, pg_lokal, rollen, server_betrieb as sb, server_mehrplatz as sm, teilen  # noqa: E402,E501
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


def warten(bedingung, s=5.0):
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.05)
    return bedingung()


tmp = Path(tempfile.mkdtemp())
PW_PB, PW_AB = "Geheim-PB-123", "Geheim-AB-456"
server = sb.ZentralerServer(tmp / "Server", port=freier_port(), namen=("rohrlaser-srv",))
offen = []
zuhoerer = []


def platz(name, kuerzel, pw):
    os.environ["ROHRLASER_ARBEITSPLATZ"] = name
    merk = tmp / name / "Daten" / "rohrlaser.db"
    merk.parent.mkdir(parents=True, exist_ok=True)
    sb.verbinden_einrichten(merk, sb.zugangsdatei_lesen(datei), adresse="127.0.0.1")
    sb.anmelden(kuerzel, pw)
    db = Datenbank(merk)
    offen.append(db)
    return db


try:
    datei = server.einrichten("Testfirma", "PB", PW_PB)
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        sb.benutzer_anlegen(con, "AB", PW_AB, sb.RECHT_BEARBEITEN, name="Anna Becker")
    db1 = platz("PC-EINS", "PB", PW_PB)         # Verwalter: richtet die Datenbank ein
    db2 = platz("PC-ZWEI", "AB", PW_AB)
    assert db1.server.verwalter and not db2.server.verwalter and not db2.nur_lesen
    tabellen = {r[0] for r in db1.con.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    assert {sm.ANWESEND, sm.SPERREN, sm.PROTOKOLL} <= tabellen, tabellen
    ok("Servertabellen für Anwesenheit, Reservierungen und Protokoll eingerichtet")

    # ------------------------------------------------------------------ Anwesenheit
    a1 = db1.angebot_neu(dict(kunde="Kunde Eins"))
    nr1 = db1.angebot(a1)["nummer"]
    stand = db1.stammdaten_stand()
    assert sm.puls(db1, {nr1: "2026-11-26T10:00"}) == set()
    assert sm.puls(db2) == set()
    assert db1.stammdaten_stand() == stand, "Puls zählt nicht als Stammdaten-Änderung"
    da = sm.anwesende(db2)
    assert da["PB"]["online"] and da["PB"]["rechner"] == "PC-EINS" and da["AB"]["online"], da
    assert teilen.lebenszeichen(db2)["PB"]["offen"] == {nr1: "2026-11-26T10:00"}
    assert teilen.mehrplatz(db2) and not teilen.aktiv(db2)
    sm.puls(db1, ende=True)
    assert not sm.anwesende(db2)["PB"]["online"]
    sm.puls(db1)
    assert sm.anwesende(db2)["PB"]["online"], "nach dem Ende wieder da"
    ok("Anwesenheit: Puls je Platz, Kollegen mit offenen Angeboten, Abmelden beim Beenden; Puls ohne Stammdaten-Zähler")

    # ------------------------------------------------------------------ Reservierung
    obj = sm.objekt_angebot(a1)
    assert sm.reservieren(db1, obj, nr1) is None
    assert sm.reservieren(db1, obj, nr1) is None, "zweimal reservieren am selben Platz"
    wer = sm.reservieren(db2, obj, nr1)
    assert wer and wer["kuerzel"] == "PB" and wer["platz"] == "PC-EINS" and not wer["ich"], wer
    assert sm.angebote_in_bearbeitung(db2)[a1]["kuerzel"] == "PB"
    assert teilen.kollegen_offen(db2)[nr1][0] == "PB"
    assert not sm.angebote_in_bearbeitung(db1), "eigene Reservierung zählt nicht als Kollege"
    # Absturz von PC-EINS: kein Puls mehr, nach FRISCH_S ist die Reservierung frei
    with db1.con:
        db1.con.execute(f"UPDATE {sm.SPERREN} SET zeit = now() - make_interval(secs => ?)", (sm.FRISCH_S + 5,))
    assert sm.inhaber(db2, obj) is None
    assert sm.reservieren(db2, obj, nr1) is None and sm.inhaber(db1, obj)["kuerzel"] == "AB"
    assert sm.puls(db1) == set(), "PC-EINS hat sie verloren"
    assert sm.puls(db2) == {obj}
    # Übernehmen (mit Rückfrage in der Oberfläche) und Freigeben
    vorher = sm.uebernehmen(db1, obj, nr1)
    assert vorher["kuerzel"] == "AB" and sm.puls(db2) == set() and sm.puls(db1) == {obj}
    assert any(p["art"] == sm.P_UEBERNOMMEN and "AB" in p["text"] for p in sm.protokoll(db1))
    sm.freigeben(db2, obj)                      # fremde Reservierung bleibt
    assert sm.inhaber(db2, obj)["kuerzel"] == "PB"
    sm.freigeben(db1, obj)
    assert sm.inhaber(db2, obj) is None
    sm.reservieren(db1, obj, nr1)
    sm.puls(db1, ende=True)
    assert sm.inhaber(db2, obj) is None, "Programmende gibt alle Reservierungen frei"
    ok("Reservierung je Angebot: Inhaber, Ablauf ohne Puls, Übernehmen mit Protokoll, Freigeben, Ende gibt frei")

    # ------------------------------------------------------------------ Live (LISTEN/NOTIFY)
    z2 = sm.Zuhoerer(db2)
    zuhoerer.append(z2)
    z2.eigene_pid_lesen()
    z2.start()
    assert z2.verbunden.wait(10), z2.fehler
    with db1.con:
        db1.con.execute("UPDATE angebote SET kunde = ? WHERE id = ?", ("Kunde Eins neu", a1))
    gesammelt = dict(angebote=set(), sperren=set(), neu=False)

    def sammeln():
        m = z2.abholen()
        gesammelt["angebote"] |= m["angebote"]
        gesammelt["sperren"] |= m["sperren"]
        return a1 in gesammelt["angebote"]
    assert warten(sammeln), gesammelt
    sm.reservieren(db1, obj, nr1)
    assert warten(lambda: (sammeln(), obj in gesammelt["sperren"])[1]), gesammelt
    gesammelt["angebote"].clear()
    with db2.con:
        db2.con.execute("UPDATE angebote SET bemerkung = ? WHERE id = ?", ("eigene Änderung", a1))
    time.sleep(1.0)
    sammeln()
    assert a1 not in gesammelt["angebote"], "eigene Änderungen melden sich nicht selbst"
    t0 = time.perf_counter()
    for _ in range(20):
        sm.puls(db1)
    assert not z2.abholen()["sperren"], "Verlängern der Reservierung meldet nichts"
    # Abbruch der Zuhörer-Verbindung: wieder verbinden, „neu“ melden
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        con.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query LIKE 'LISTEN%%'")
    assert warten(lambda: z2.abholen()["neu"], 15), "nach Abbruch wieder verbunden"
    ok(f"Live: Angebotsänderung und Reservierung kommen beim Kollegen an, eigene nicht, Puls still "
       f"({(time.perf_counter() - t0) / 20 * 1000:.0f} ms je Puls), Wiederverbinden nach Abbruch")

    # ------------------------------------------------------------------ Benutzer über die Programmrollen
    assert rollen.benutzer_setzen(db1, "XY", "Xaver Ypsilon", [rollen.KALKULATION]) != "", "ohne Passwort kein Login"
    assert rollen.benutzer_setzen(db1, "PB", "Patrick", [rollen.ADMIN]) == ""
    fehler = rollen.benutzer_setzen(db1, "XY", "Xaver Ypsilon", [rollen.KALKULATION], passwort="kurz12")
    assert "8 Zeichen" in fehler and "XY" not in rollen.benutzer(db1), fehler
    assert rollen.benutzer_setzen(db1, "XY", "Xaver Ypsilon", [rollen.KALKULATION], passwort="Geheim-XY-789") == ""
    b = {x["kuerzel"]: x for x in sm.benutzer_liste(db1)}
    assert b["XY"]["recht"] == sb.RECHT_BEARBEITEN and b["XY"]["name"] == "Xaver Ypsilon" and not b["XY"]["gesperrt"]
    assert b["PB"]["recht"] == sb.RECHT_VERWALTER
    assert sb.anmeldung_pruefen(tmp / "PC-EINS" / "Daten" / "rohrlaser.db", "XY", "Geheim-XY-789")["recht"] == \
        sb.RECHT_BEARBEITEN
    assert rollen.zugang_setzen(db1, "XY", "Geheim-XY-000") == ""
    assert sb.anmeldung_pruefen(tmp / "PC-EINS" / "Daten" / "rohrlaser.db", "XY", "Geheim-XY-000")
    # Rolle nur zum Sehen → Leserecht; gesperrt → keine Anmeldung; entfernen
    assert rollen.benutzer_setzen(db1, "XY", "Xaver Ypsilon", [rollen.WERKSTATT]) == ""
    rechte_ws = rollen.rechte(db1).get(rollen.WERKSTATT) or {}
    erwartet = sb.RECHT_BEARBEITEN if rollen.BEARBEITEN in rechte_ws.values() else sb.RECHT_LESEN
    assert {x["kuerzel"]: x for x in sm.benutzer_liste(db1)}["XY"]["recht"] == erwartet
    for bereich, _t in rollen.BEREICHE:         # eine Rolle, die nur sieht → Leserecht am Server
        assert rollen.recht_setzen(db1, rollen.QS, bereich, rollen.SEHEN) == ""
    assert rollen.benutzer_setzen(db1, "XY", "Xaver Ypsilon", [rollen.QS]) == ""
    assert {x["kuerzel"]: x for x in sm.benutzer_liste(db1)}["XY"]["recht"] == sb.RECHT_LESEN
    assert rollen.benutzer_setzen(db1, "XY", "Xaver Ypsilon", [rollen.WERKSTATT], aktiv_=False) == ""
    try:
        sb.anmeldung_pruefen(tmp / "PC-EINS" / "Daten" / "rohrlaser.db", "XY", "Geheim-XY-000")
        raise AssertionError("gesperrter Benutzer angemeldet")
    except sb.AnmeldeFehler:
        pass
    assert rollen.entfernen(db1, "XY") == "" and "XY" not in {x["kuerzel"] for x in sm.benutzer_liste(db1)}
    # Schutz: eigener Zugang, letzter Verwalter, nur Verwalter
    assert "eigenen" in rollen.benutzer_setzen(db1, "PB", "Patrick", [rollen.KALKULATION])
    assert "Verwalter" in sm.benutzer_server(db2, "QQ", "Q", [rollen.KALKULATION], passwort="Geheim-QQ-123")
    assert {x["kuerzel"]: x for x in sm.benutzer_liste(db1)}["PB"]["recht"] == sb.RECHT_VERWALTER
    assert any(p["art"] == sm.P_BENUTZER and "XY" in p["text"] for p in sm.protokoll(db1))
    ok("Benutzer über die Programmrollen: Login mit Passwort, Admin = Verwalter, Leserecht, sperren, entfernen; "
       "eigener Zugang und Verwalterrecht geschützt; Protokoll")

    # ------------------------------------------------------------------ Oberfläche: zwei Hauptfenster
    from PySide6.QtWidgets import QApplication
    from rohrlaser import aenderungsverlauf, kollegen_dialog, server_dialog
    from rohrlaser.angebot_fenster import _offen_text
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])
    a2 = db1.angebot_neu(dict(kunde="Kunde Zwei"))
    nr2 = db1.angebot(a2)["nummer"]
    f1 = Hauptfenster(db1, stumm=True)
    f2 = Hauptfenster(db2, stumm=True)
    z = sm.Zuhoerer(db2)
    zuhoerer.append(z)
    z.eigene_pid_lesen()
    z.start()
    f2._server_zuhoerer = z
    assert z.verbunden.wait(10)
    s1 = f1.angebot_oeffnen(a2)
    assert s1.fremd() is None and sm.inhaber(db2, sm.objekt_angebot(a2))["kuerzel"] == "PB"
    s2 = f2.angebot_oeffnen(a2)
    assert s2.fremd() == "PB" and not s2.server_knopf.isHidden() and "PB bearbeitet" in s2.fremd_text.text()
    assert not s2.kopf_bereich.isEnabled() and not s2.fremd_leiste.isHidden()
    assert _offen_text(dict(bearbeiter="AB", _offen=("PB", ""), _offen_server="PB")) == " ● PB bearbeitet"
    assert _offen_text(dict(bearbeiter="PB", _offen=("PB", ""), _offen_server="PB")) == " ● geöffnet"
    zk = {d["kuerzel"]: d for d in kollegen_dialog.zeilen(db2)}
    assert zk["PB"]["online"] and nr2 in zk["PB"]["werte"][7] and zk["AB"]["ich"], zk
    # PB ändert und schließt: Verlauf mit Kürzel, Reservierung frei, AB kann sofort bearbeiten (Live-Meldung)
    with db1.con:
        db1.con.execute("UPDATE angebote SET kunde = ? WHERE id = ?", ("Kunde Zwei GmbH", a2))
    f1.angebot_schliessen(a2)
    uid2 = db1.con.execute("SELECT uid FROM angebote WHERE id = ?", (a2,)).fetchone()[0]
    eintraege = aenderungsverlauf.eintraege(db1.con, "angebote", uid2)
    assert any(e["wer"] == "PB" and e["feld"] == "kunde" for e in eintraege), eintraege
    assert warten(lambda: (server_dialog.live(f2), s2.fremd() is None)[1]), "frei nach Live-Meldung"
    assert s2.server_knopf.isHidden() and s2.kopf_bereich.isEnabled()
    assert s2.kopf.get("kunde") == "Kunde Zwei GmbH", "Stand des Kollegen neu geladen"
    # PB übernimmt mit „Übernehmen“: AB sieht es beim nächsten Puls nur noch an
    s1 = f1.angebot_oeffnen(a2)
    assert s1.fremd() == "AB"
    assert s1._server_uebernehmen(fragen=False) and s1.fremd() is None
    f2._server_puls_merk["zeit"] = -1e9
    server_dialog.puls(f2)
    assert s2.fremd() == "PB", "Übernahme bemerkt"
    # Programmende: abgemeldet, frei
    server_dialog.mehrplatz_beenden(f1)
    assert not sm.anwesende(db2)["PB"]["online"] and sm.inhaber(db2, sm.objekt_angebot(a2)) is None
    assert any(p["art"] == sm.P_ABMELDEN and p["kuerzel"] == "PB" for p in sm.protokoll(db2))
    ok("Oberfläche: Öffnen reserviert, Kollege sieht nur an (Leiste, Übernehmen), Schließen gibt frei und trägt den "
       "Verlauf mit Kürzel ein, Live-Meldung macht das Angebot beim Kollegen bearbeitbar, Übernehmen, Abmelden")
    for f in (f1, f2):
        f.stumm = True
        f.close()
finally:
    for z in zuhoerer:
        z.stoppen()
    for db in offen:
        try:
            db.schliessen()
        except Exception:       # noqa: BLE001
            pass
    datenspeicher.alle_stoppen()
    server.stoppen()
print("alle Prüfungen bestanden")
