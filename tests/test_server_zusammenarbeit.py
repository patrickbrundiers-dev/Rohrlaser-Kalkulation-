"""Serverversion Paket S4b: Zusammenarbeit im Serverbetrieb (Patrick 26.11.2026).

Prüft mit echtem zentralem Server und drei Arbeitsplätzen (PB Verwalter, AB bearbeiten, LL nur ansehen):
- Kollegen = Logins am Server (gesperrte nicht), Namen aus der Benutzerverwaltung;
- Übergabe: Bearbeiter wechselt sofort, Empfänger bekommt die Meldung einmal; nur der Bearbeiter (oder Verwalter)
  übergibt; keine Rücknahme nötig;
- Übernahme anfragen → Bearbeiter wird gefragt; ja = übergeben, nein = Absage beim Fragenden; offene Anfrage
  einmal; übergibt der Bearbeiter von selbst, ist die Anfrage erledigt;
- Notiz mit Wiedervorlage, erledigt am Server (an jedem Platz des Mitarbeiters gleich); Nur-Lesen sendet nichts;
- Oberfläche: Meine/Alle mit Bearbeiter, Vorgang-Menü, Puls zeigt Übergaben/Notizen und fragt Anfragen, Zuweisen
  der Anfragen sichtbar.
Als root (initdb verweigert root) oder ohne PostgreSQL-Programme übersprungen.

Aufruf: python tests/test_server_zusammenarbeit.py
"""
import datetime
import os
import socket
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("ROHRLASER_PG_TEST", None)      # echter zentraler Server, nicht der Prüfserver
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import datenspeicher, pg_lokal, server_betrieb as sb, server_zusammenarbeit as sz, teilen  # noqa: E402
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
PW_PB, PW_AB, PW_LL = "Geheim-PB-123", "Geheim-AB-456", "Geheim-LL-789"
server = sb.ZentralerServer(tmp / "Server", port=freier_port(), namen=("rohrlaser-srv",))
offen = []


def platz(name, kuerzel, pw):
    os.environ["ROHRLASER_ARBEITSPLATZ"] = name
    merk = tmp / name / "Daten" / "rohrlaser.db"
    merk.parent.mkdir(parents=True, exist_ok=True)
    sb.verbinden_einrichten(merk, sb.zugangsdatei_lesen(datei), adresse="127.0.0.1")
    sb.anmelden(kuerzel, pw)
    db = Datenbank(merk)
    offen.append(db)
    return db


def fehler(f, *args):
    try:
        f(*args)
    except teilen.TeilenFehler as e:
        return str(e)
    raise AssertionError(f"kein Fehler: {f.__name__}{args}")


try:
    datei = server.einrichten("Testfirma", "PB", PW_PB)
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        sb.benutzer_anlegen(con, "AB", PW_AB, sb.RECHT_BEARBEITEN, name="Anna Becker")
        sb.benutzer_anlegen(con, "LL", PW_LL, sb.RECHT_LESEN, name="Werkstatt")
        sb.benutzer_anlegen(con, "XX", "Geheim-XX-000", sb.RECHT_BEARBEITEN, name="Ausgeschieden")
        sb.benutzer_sperren(con, "XX")
    db1 = platz("PC-EINS", "PB", PW_PB)
    db2 = platz("PC-ZWEI", "AB", PW_AB)
    db3 = platz("PC-DREI", "LL", PW_LL)
    tabellen = {r[0] for r in db1.con.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    assert sz.VORGAENGE in tabellen

    # ------------------------------------------------------------------ Kollegen
    assert teilen.zusammenarbeit(db1) and not teilen.aktiv(db1)
    assert teilen.kollegen(db1) == {"AB": "Anna Becker", "LL": "Werkstatt"}, teilen.kollegen(db1)
    assert set(teilen.kollegen(db2)) == {"PB", "LL"}, teilen.kollegen(db2)
    assert teilen.mitarbeiter(db1, "AB")["name"] == "Anna Becker"
    ok("Kollegen = Logins am Server ohne gesperrte, Namen aus der Benutzerverwaltung")

    # ------------------------------------------------------------------ Übergabe
    a1 = db1.angebot_neu(dict(kunde="Kunde Eins"))
    nr1 = db1.angebot(a1)["nummer"]
    assert db1.angebot(a1)["bearbeiter"] == "PB"
    assert "keinen Zugang" in fehler(teilen.uebergeben, db1, a1, "XX")
    assert "Kollegen wählen" in fehler(teilen.uebergeben, db1, a1, "PB")
    teilen.uebergeben(db1, a1, "AB", "bitte fertig machen")
    assert db2.angebot(a1)["bearbeiter"] == "AB" and not db2.angebot(a1).get("fremd"), "sofort beim Kollegen"
    assert teilen.vorgang_offen(db1, nr1, teilen.UEBERGABE) is None and not teilen.zuruecknehmen(db1, a1)
    b = sz.abholen(db2)
    assert b["uebernommen"] == [dict(nummer=nr1, von="PB", notiz="bitte fertig machen", id=a1)], b
    assert sz.abholen(db2)["uebernommen"] == [], "Meldung nur einmal"
    a0 = db1.angebot_neu(dict(kunde="Kunde Null"))
    assert "übergeben kann nur der Bearbeiter" in fehler(teilen.uebergeben, db2, a0, "LL")
    a2 = db2.angebot_neu(dict(kunde="Kunde Zwei"))
    assert db2.angebot(a2)["bearbeiter"] == "AB"
    teilen.uebergeben(db1, a2, "LL")                    # Verwalter darf fremde Angebote übergeben
    assert db1.angebot(a2)["bearbeiter"] == "LL"
    teilen.uebergeben(db1, a2, "AB")
    ok("Übergabe: Bearbeiter wechselt sofort, Meldung einmal beim Empfänger, Verwalter darf auch fremde")

    # ------------------------------------------------------------------ Übernahme anfragen
    assert "gehört schon Ihnen" in fehler(teilen.anfragen, db2, a1)
    q = teilen.anfragen(db1, a1, "Kunde hat angerufen")
    assert teilen.anfragen(db1, a1) == q, "offene Anfrage nur einmal"
    assert teilen.vorgang_offen(db1, nr1, teilen.ANFRAGE)["id"] == q
    b = sz.abholen(db2)
    assert [a["id"] for a in b["anfragen"]] == [q] and b["anfragen"][0]["von"] == "PB", b
    assert [a["id"] for a in sz.abholen(db2)["anfragen"]] == [q], "bleibt offen bis zur Antwort"
    teilen.beantworten(db2, b["anfragen"][0], False, "noch in Arbeit")
    assert sz.abholen(db1)["abgelehnt"] == [dict(nummer=nr1, von="AB", notiz="noch in Arbeit")]
    assert teilen.vorgang_offen(db1, nr1, teilen.ANFRAGE) is None and db1.angebot(a1)["bearbeiter"] == "AB"
    q2 = teilen.anfragen(db1, a1)
    teilen.beantworten(db2, [a for a in sz.abholen(db2)["anfragen"] if a["id"] == q2][0], True)
    assert db1.angebot(a1)["bearbeiter"] == "PB" and sz.abholen(db1)["uebernommen"][0]["notiz"] == "auf Ihre Anfrage"
    # übergibt der Bearbeiter von selbst, ist die Anfrage erledigt
    teilen.anfragen(db2, a1)
    teilen.uebergeben(db1, a1, "AB")
    assert sz.abholen(db1)["anfragen"] == [] and teilen.vorgang_offen(db2, nr1, teilen.ANFRAGE) is None
    sz.abholen(db2)
    ok("Übernahme anfragen: Bearbeiter wird gefragt, Absage kommt zurück, ja übergibt, offene Anfrage einmal")

    # ------------------------------------------------------------------ Notizen
    morgen = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    teilen.notiz_senden(db1, "AB", "Bitte  Kunde   anrufen", nr1, morgen)
    teilen.notiz_senden(db1, "AB", "Kaffee")
    assert "Text" in fehler(teilen.notiz_senden, db1, "AB", "  ")
    assert "nur ansehen" in fehler(teilen.notiz_senden, db3, "AB", "von der Werkstatt")
    n = teilen.notizen(db2, offen_nur=True)
    assert [x["notiz"] for x in n] == ["Kaffee", "Bitte Kunde anrufen"], n
    assert n[1]["faellig"] == morgen and not n[1]["faellig_jetzt"] and n[0]["faellig_jetzt"]
    assert [x["notiz"] for x in sz.abholen(db2)["notizen"]] == ["Bitte Kunde anrufen", "Kaffee"]
    db2b = platz("PC-VIER", "AB", PW_AB)
    teilen.notiz_erledigt(db2b, n[0]["id"])
    assert [x["notiz"] for x in teilen.notizen(db2, offen_nur=True)] == ["Bitte Kunde anrufen"]
    assert teilen.notizen(db1) == [], "fremde Notizen sieht niemand"
    ok("Notizen mit Wiedervorlage; erledigt am Server gilt an jedem Platz; Nur-Lesen sendet nichts")

    # ------------------------------------------------------------------ Oberfläche
    from PySide6.QtWidgets import QApplication
    from rohrlaser import server_dialog, teilen_fenster
    from rohrlaser.angebot_fenster import ALLE, MEINE
    from rohrlaser.fenster import Hauptfenster
    _app = QApplication.instance() or QApplication([])
    f1 = Hauptfenster(db1, stumm=True)
    f2 = Hauptfenster(db2, stumm=True)
    au = f1.angebote
    au.neu_laden()
    eintraege = [au.wer_filter.itemText(i) for i in range(au.wer_filter.count())]
    assert eintraege == [MEINE, ALLE, "AB"], eintraege
    au.wer_filter.setCurrentText(MEINE)
    au.neu_laden()
    meine = {z["id"] for z in au.modell.zeilen}
    assert a0 in meine and not meine & {a1, a2}, "a1, a2 gehören AB"
    au.wer_filter.setCurrentText("AB")
    au.neu_laden()
    assert {a1, a2} <= {z["id"] for z in au.modell.zeilen}
    au.wer_filter.setCurrentText(ALLE)
    au.neu_laden()
    menue = au.vorgang_knopf.menu()
    menue.aboutToShow.emit()
    assert au.uebergeben_aktion.isVisible() and au.notiz_aktion.isVisible() and au.anfragen_aktion.isVisible()
    # Übergabe über die Oberfläche, Empfänger sieht sie beim Puls
    a3 = db1.angebot_neu(dict(kunde="Kunde Drei"))
    assert au.uebergeben(a3, "AB", "über die Oberfläche")
    assert au.uebernahme_anfragen(a3, "zurück bitte")
    assert teilen_fenster.notiz_senden(f1, a3, "AB", "Notiz über die Oberfläche")
    gefragt = []
    teilen_fenster.anfrage_fragen = lambda fenster, a: gefragt.append(a["id"]) or (True, "")
    f2.stumm = False                                    # fragen (gefälscht) statt still übergehen
    try:
        b = teilen_fenster.server_vorgaenge(f2)
    finally:
        f2.stumm = True
    assert [u["id"] for u in b["uebernommen"]] == [a3] and len(gefragt) == 1, (b, gefragt)
    assert db1.angebot(a3)["bearbeiter"] == "PB", "Anfrage beantwortet: zurück an PB"
    f2.stumm = False
    try:
        assert teilen_fenster.server_vorgaenge(f2)["anfragen"] == [], "je Sitzung einmal gefragt"
    finally:
        f2.stumm = True
    f1._server_puls_merk = {}
    assert server_dialog.puls(f1) is not None
    ok("Oberfläche: Meine/Alle nach Bearbeiter, Vorgang-Menü, Puls zeigt Übergaben und fragt Anfragen einmal")
    for f in (f1, f2):
        f.stumm = True
        f.close()
finally:
    for db in offen:
        try:
            db.schliessen()
        except Exception:       # noqa: BLE001
            pass
    datenspeicher.alle_stoppen()
    server.stoppen()
print("alle Prüfungen bestanden")
