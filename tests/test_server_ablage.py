"""Serverversion Paket S3: Dokumentenablage am Server (Patrick 26.11.2026).

Prüft mit echtem zentralem Server und zwei Arbeitsplätzen (PB Verwalter, AB bearbeiten):
- Einrichten legt <Server-Ordner>/Ablage an; ohne eingetragenen Pfad bleiben die Dateien am Arbeitsplatz (Anzeige
  sagt es);
- nur der Verwalter trägt den Pfad ein (Programm und Befehl „ablage“), mit Protokoll; die anderen Plätze sehen ihn
  nach spätestens einer Minute; ein Platz mit anderem Laufwerksbuchstaben trägt server_ablage_hier ein;
- alle Dateistellen nutzen die Ablage: Angebotsordner (PDF/CSV/STEP), Anfragen, Anfrage-Akten, Austausch, Updates,
  Admin- und Oberflächen-Vorgaben, Rechenmerker; Sicherungen nie (der Server sichert zentral); kein Abgleich;
- nicht erreichbare Ablage: Anzeige rot, Unterordner None (kein Schreiben ins Leere);
- Auftrags- und Rahmenauftragsnummern am Server in einer Transaktion: zwei Plätze gleichzeitig, nie doppelt;
- Oberfläche: Hauptfenster legt PDFs in die Ablage, Datei → Datenbank zeigt die Ablage, Fenster „Ablage am Server“.
Als root (initdb verweigert root) oder ohne PostgreSQL-Programme übersprungen.

Aufruf: python tests/test_server_ablage.py
"""
import os
import socket
import sys
import tempfile
import threading
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("ROHRLASER_PG_TEST", None)      # echter zentraler Server, nicht der Prüfserver
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import datenspeicher, pg_lokal, server_betrieb as sb, server_mehrplatz as sm, teilen  # noqa: E402
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
PW_PB, PW_AB = "Geheim-PB-123", "Geheim-AB-456"
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


def frisch(*dbs):
    """Merker der Ablage verwerfen (statt eine Minute zu warten)."""
    for db in dbs:
        db.server._ablage = None


try:
    datei = server.einrichten("Testfirma", "PB", PW_PB)
    ablage = server.ablage_ordner()
    assert ablage == tmp / "Server" / sb.ABLAGE_ORDNER and ablage.is_dir(), ablage
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        sb.benutzer_anlegen(con, "AB", PW_AB, sb.RECHT_BEARBEITEN, name="Anna Becker")
        sb.benutzer_anlegen(con, "LL", "Geheim-LL-789", sb.RECHT_LESEN, name="Werkstatt")
    db1 = platz("PC-EINS", "PB", PW_PB)
    db2 = platz("PC-ZWEI", "AB", PW_AB)
    from rohrlaser import admin_schutz, anfragen, anfragen_akten, austausch_dateien, update_quellen, werkzeugleiste

    # ------------------------------------------------------------------ ohne eingetragene Ablage
    assert teilen.dateiordner(db2) is None and not teilen.dateien_geteilt(db2)
    p, erreichbar, text = teilen.ablage_zustand(db2)
    assert p is None and not erreichbar and "keine eingetragen" in text, text
    assert anfragen_akten.wurzel(db2) == Path(db2.pfad).parent / anfragen_akten.ORDNER
    assert austausch_dateien.gemeinsam(db2) == Path(db2.pfad).parent / austausch_dateien.ORDNER
    assert teilen.unterordner(db2, teilen.ANGEBOTE, "teilen_ablage") is None
    ok("Einrichten legt den Ordner Ablage an; ohne eingetragenen Pfad bleiben die Dateien am Arbeitsplatz")

    # ------------------------------------------------------------------ eintragen: nur Verwalter
    try:
        sm.ablage_speichern(db2, str(ablage))
        raise AssertionError("Nicht-Verwalter trägt die Ablage ein")
    except sb.ServerFehler as e:
        assert "Verwalter" in str(e)
    assert sm.ablage_speichern(db1, str(ablage)) == (ablage, True)
    assert teilen.dateiordner(db1) == ablage, "eigener Merker sofort neu"
    assert any(e["art"] == "ablage" and str(ablage) in e["text"] for e in sm.protokoll(db1)), "Protokoll"
    frisch(db2)
    assert teilen.dateiordner(db2) == ablage and teilen.dateien_geteilt(db2) and not teilen.aktiv(db2)
    # Befehl auf dem Server-Rechner: anzeigen und eintragen
    zeilen = []
    assert sb.main(["ablage", "--ordner", str(tmp / "Server"), "--port", str(server.port)], ausgabe=zeilen.append) == 0
    assert str(ablage) in zeilen[-1], zeilen
    anders = tmp / "Freigabe"
    anders.mkdir()
    sb.main(["ablage", "--ordner", str(tmp / "Server"), "--port", str(server.port), "--pfad", str(anders)],
            ausgabe=zeilen.append)
    assert teilen.dateiordner(db2) == ablage, "eine Minute lang gilt der gelesene Pfad"
    frisch(db1, db2)
    assert teilen.dateiordner(db1) == anders == teilen.dateiordner(db2)
    sm.ablage_speichern(db1, str(ablage))
    frisch(db2)
    ok("Pfad trägt nur der Verwalter ein (Programm und Befehl „ablage“), mit Protokoll; andere Plätze sehen ihn nach "
       "spätestens einer Minute")

    # ------------------------------------------------------------------ alle Dateistellen in der Ablage
    db2.einstellung_setzen("teilen_ablage", "nein")         # im Serverbetrieb ohne Bedeutung: Ablage gilt immer
    assert teilen.unterordner(db2, teilen.ANGEBOTE, "teilen_ablage", anlegen=True) == ablage / teilen.ANGEBOTE
    assert (ablage / teilen.ANGEBOTE).is_dir()
    assert anfragen.ordner(db2) == ablage / teilen.ANFRAGEN and (ablage / teilen.ANFRAGEN).is_dir()
    assert teilen.unterordner(db2, teilen.SICHERUNGEN, "teilen_sicherung") is None, "Sicherungen macht der Server"
    assert db2.sicherung_gemeinsam() is None
    assert anfragen_akten.wurzel(db1) == ablage / anfragen_akten.ORDNER == anfragen_akten.wurzel(db2)
    assert austausch_dateien.gemeinsam(db1) == ablage / austausch_dateien.ORDNER == austausch_dateien.gemeinsam(db2)
    w = austausch_dateien.wurzeln(db2, anlegen=True)
    assert w[austausch_dateien.PERSOENLICH] == ablage / austausch_dateien.ORDNER / austausch_dateien.PERSOENLICH_ORDNER \
        / "AB" and w[austausch_dateien.PERSOENLICH].is_dir(), w
    assert w[austausch_dateien.ANGEBOTE] == ablage / teilen.ANGEBOTE, w
    if not update_quellen.einstellungen(db2)["ordner"]:
        assert update_quellen.update_ordner(db2) == ablage / update_quellen.UPDATES
    assert admin_schutz.ablage(db2) is not None
    assert werkzeugleiste.vorgaben_schreiben(db1) and werkzeugleiste.vorgaben_lesen(db2) in (True, False)
    assert (ablage.joinpath(*werkzeugleiste.DATEI)).is_file(), "Oberflächen-Vorgaben in der Ablage"
    # eine Datei von PB ist bei AB sofort da (derselbe Ordner, kein Abgleich)
    (austausch_dateien.gemeinsam(db1) / "Zeichnung.txt").write_text("PB", encoding="utf-8")
    assert (austausch_dateien.gemeinsam(db2) / "Zeichnung.txt").read_text(encoding="utf-8") == "PB"
    db3 = platz("PC-DREI", "LL", "Geheim-LL-789")
    assert db3.nur_lesen and teilen.dateiordner(db3) == ablage
    assert austausch_dateien.darf(db3, austausch_dateien.LESEN)
    assert not austausch_dateien.darf(db3, austausch_dateien.HOCHLADEN), "Leserecht lädt nichts in die Ablage"
    assert austausch_dateien.darf(db2, austausch_dateien.HOCHLADEN)
    ok("Angebotsordner, Anfrage-Akten, Austausch, Updates, Admin- und Oberflächen-Vorgaben liegen in der Ablage am "
       "Server; Sicherungen nicht; kein Abgleich nötig; Leserecht sieht nur an")

    # ------------------------------------------------------------------ anderer Pfad an einem Platz, nicht erreichbar
    db2.einstellung_setzen("server_ablage_hier", str(anders))
    assert teilen.dateiordner(db2) == anders and teilen.dateiordner(db1) == ablage, "nur dieser Platz"
    db2.einstellung_setzen("server_ablage_hier", "")
    weg = tmp / "gibt-es-nicht"
    sm.ablage_speichern(db1, str(weg))
    p, erreichbar, text = teilen.ablage_zustand(db1)
    assert p == weg and not erreichbar and "NICHT erreichbar" in text, text
    assert teilen.unterordner(db1, teilen.ANGEBOTE, "teilen_ablage", anlegen=True) is None and not weg.exists()
    sm.ablage_speichern(db1, str(ablage))
    frisch(db2)
    ok("Arbeitsplatz mit anderem Pfad (server_ablage_hier); nicht erreichbare Ablage wird angezeigt, nichts wird "
       "ins Leere geschrieben")

    # ------------------------------------------------------------------ Auftrags- und Rahmennummern am Server
    from rohrlaser import auftraege, rahmenauftrag
    nummern, fehler = [], []

    def ziehen(db, n):
        try:
            for _ in range(n):
                nummern.append(auftraege.neue_nummer(db, "2026-11-26"))
                nummern.append(rahmenauftrag.neue_nummer(db, "2026-11-26"))
        except Exception as e:      # noqa: BLE001
            fehler.append(e)
    t = [threading.Thread(target=ziehen, args=(d, 8)) for d in (db1, db2)]
    for x in t:
        x.start()
    for x in t:
        x.join(60)
    assert not fehler, fehler
    au = sorted(n for n in nummern if n.startswith("AU-"))
    ra = sorted(n for n in nummern if n.startswith("RA-"))
    assert len(au) == len(set(au)) == 16 and len(ra) == len(set(ra)) == 16, (au, ra)
    assert au[0] == "AU-2026-00001" and au[-1] == "AU-2026-00016", au
    assert ra[0] == "RA-2026-0001" and ra[-1] == "RA-2026-0016", ra
    ok("Auftrags- und Rahmenauftragsnummern am Server: zwei Plätze gleichzeitig, fortlaufend, nie doppelt")

    # ------------------------------------------------------------------ Oberfläche
    from PySide6.QtWidgets import QApplication
    from rohrlaser import server_dialog
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])
    f1 = Hauptfenster(db1, stumm=True)
    assert f1.ablage() == ablage / teilen.ANGEBOTE, "PDF und CSV in die Ablage am Server"
    assert "Ablage am Server: " + str(ablage) in f1.datenspeicher_anzeigen() and "erreichbar" in \
        f1.datenspeicher_anzeigen()
    assert server_dialog.ablage_einstellen(f1, str(anders)) == (anders, True)
    assert teilen.dateiordner(db1) == anders
    assert server_dialog.ablage_einstellen(f1, str(ablage)) == (ablage, True)
    f2 = Hauptfenster(db2, stumm=True)
    assert server_dialog.ablage_einstellen(f2, str(anders)) is None, "Bearbeiter darf nicht"
    frisch(db2)
    assert teilen.dateiordner(db2) == ablage
    ok("Oberfläche: Ablage im Hauptfenster, Datei → Datenbank zeigt sie, Fenster „Ablage am Server“ nur für Verwalter")
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
