"""Serverversion Paket S4: Rechenaufträge am Server (Patrick 26.11.2026).

Prüft mit echtem zentralem Server, zwei Arbeitsplätzen und echtem Messprogramm (step_messen.py):
- Tabellen da; gemeinsamer Zwischenspeicher der Messung in der Ablage (<Ablage>/STEP-Cache, mindestens 5000 MB);
- Entscheidung je Einstellung (automatisch: kurze Rechnung am Platz; am Server; an diesem Arbeitsplatz);
- ohne Rechner rechnet der Platz selbst; gleiche offene Aufträge werden nicht doppelt angelegt; Abbruch wartend;
- Rechner am Server misst eine Datei von außerhalb der Ablage (wird nach _Rechnen kopiert), Fortschritt und Ende in
  der Tabelle; danach misst der Platz aus dem gemeinsamen Zwischenspeicher – bitgleich zur Messung ohne Server;
- laufender Auftrag: Fortschritt, Abbruch beendet den Prozess; Server ausgelastet: Platz rechnet selbst;
- Vormessung einer Anfrage nutzt den Server; Fortschrittsfenster im Hauptfenster; Statuszeile in Datei → Datenbank.
Als root (initdb verweigert root), ohne PostgreSQL-Programme oder ohne OCP (Messprogramm) übersprungen.

Aufruf: python tests/test_server_rechnen.py
"""
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.pop("ROHRLASER_PG_TEST", None)      # echter zentraler Server, nicht der Prüfserver
HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))

from rohrlaser import datenspeicher, pg_lokal, server_betrieb as sb  # noqa: E402
from rohrlaser import server_rechnen as sr, step, step_einstellungen  # noqa: E402
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
if importlib.util.find_spec("OCP") is None:
    print("übersprungen: kein OCP (Messprogramm)")
    sys.exit(0)


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def warten(bedingung, s=30.0):
    ende = time.monotonic() + s
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.1)
    return bedingung()


tmp = Path(tempfile.mkdtemp())
PW_PB, PW_AB = "Geheim-PB-123", "Geheim-AB-456"
server = sb.ZentralerServer(tmp / "Server", port=freier_port(), namen=("rohrlaser-srv",))
offen, stopps, threads = [], [], []
PROGRAMM = HIER.parent / "programm"


def platz(name, kuerzel, pw):
    os.environ["ROHRLASER_ARBEITSPLATZ"] = name
    merk = tmp / name / "Daten" / "rohrlaser.db"
    merk.parent.mkdir(parents=True, exist_ok=True)
    sb.verbinden_einrichten(merk, sb.zugangsdatei_lesen(datei), adresse="127.0.0.1")
    sb.anmelden(kuerzel, pw)
    db = Datenbank(merk)
    offen.append(db)
    return db


def messen(dateien, args, ausgabe_ordner):
    """Messung am Platz wie beim Import (eigener Prozess). Ergebnis: (Messwerte-Text, stdout)."""
    befehl = step.messprogramm(PROGRAMM)
    ausgabe_ordner.mkdir(parents=True, exist_ok=True)
    liste = ausgabe_ordner / "liste.txt"
    liste.write_text("\n".join(map(str, dateien)), encoding="utf-8")
    r = subprocess.run(befehl + ["--liste", str(liste), "--ausgabe", str(ausgabe_ordner / "m.txt"),
                                 "--netze", str(ausgabe_ordner / "netze")] + args,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600,
                       env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert r.returncode == 0, r.stderr[-2000:]
    return (ausgabe_ordner / "m.txt").read_text(encoding="utf-8"), r.stdout


try:
    datei = server.einrichten("Testfirma", "PB", PW_PB, str(tmp / "Server" / sb.ABLAGE_ORDNER))
    ablage = server.ablage_ordner()
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        sb.benutzer_anlegen(con, "AB", PW_AB, sb.RECHT_BEARBEITEN, name="Anna Becker")
    db1 = platz("PC-EINS", "PB", PW_PB)
    db2 = platz("PC-ZWEI", "AB", PW_AB)
    from rohrlaser import VERSION
    tabellen = {r[0] for r in db1.con.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")}
    assert {sr.AUFTRAEGE, sr.RECHNER} <= tabellen, tabellen
    assert step_einstellungen.cache_ordner(db2) == ablage / sr.CACHE, step_einstellungen.cache_ordner(db2)
    args2 = ["--flachstahl-bis", "0"] + step_einstellungen.mess_argumente(db2)
    assert args2[args2.index("--cache") + 1] == str(ablage / sr.CACHE)
    assert float(args2[args2.index("--cache-mb") + 1]) >= sr.CACHE_MB_MIN
    ok("Tabellen für Aufträge und Rechner; gemeinsamer Zwischenspeicher der Messung in der Ablage am Server")

    # ------------------------------------------------------------------ Entscheidung, ohne Rechner, doppelt, Abbruch
    teil = tmp / "Kunde" / "Teil QR40.step"            # außerhalb der Ablage (z. B. aus einer Mail)
    teil.parent.mkdir()
    shutil.copyfile(HIER / "step_referenz" / "REF02_QR40x40x2_L1000.step", teil)
    z = sr.zugang(db2)
    assert z["ort"] == "automatisch" and sr.entscheiden(z, [teil]) == (False, "kurze Rechnung")
    db2.einstellung_setzen(sr.ORT, "an diesem Arbeitsplatz")
    assert not sr.entscheiden(sr.zugang(db2), [teil])[0]
    db2.einstellung_setzen(sr.ORT, "am Server")
    z = sr.zugang(db2)
    assert sr.entscheiden(z, [teil]) == (True, "")
    assert not sr.entscheiden(z, [tmp / "x.tubx"])[0], "Dateien mit Begleitdatei rechnet der Platz"
    erg = sr.am_server_rechnen(z, [teil], args2, True)
    assert erg[0] is False and "kein Rechner" in erg[1], erg
    pg = sr.verbindung(db2)
    rel = sr.ablegen(z["ablage"], [teil])
    assert rel and rel[0].startswith(sr.EINGANG + "/") and (ablage / rel[0]).read_bytes() == teil.read_bytes()
    assert sr.ablegen(z["ablage"], [ablage / rel[0]]) == rel, "Datei in der Ablage wird nicht noch einmal kopiert"
    a1 = sr.einreichen(pg, rel, args2, True, "0.0.0-ohne", "AB", "PC-ZWEI", ablage=z["ablage"])
    assert sr.einreichen(pg, rel, args2 + ["--liste", "egal.txt"], True, "0.0.0-ohne", ablage=z["ablage"]) == a1, \
        "gleicher offener Auftrag (Ein-/Ausgabe zählt nicht)"
    sr.abbrechen(pg, a1)
    assert sr.zustand(pg, a1)["zustand"] == sr.ABGEBROCHEN
    ok("Entscheidung je Einstellung und Größe; ohne Rechner rechnet der Platz; gleiche Aufträge nur einmal; Abbruch "
       "eines wartenden Auftrags; Dateien von außerhalb kommen einmal in die Ablage")

    # ------------------------------------------------------------------ Rechner am Server: echte Messung
    protokoll = []
    r = sb.rechner(server, ausgabe=protokoll.append, programmordner=PROGRAMM)
    assert r.ablage == ablage and r.version == VERSION
    stop = threading.Event()
    stopps.append(stop)
    t = threading.Thread(target=r.laufen, args=(stop,), daemon=True)
    threads.append(t)
    t.start()
    assert warten(lambda: sr.rechner_da(pg.con, VERSION) == 1, 20), "Rechner meldet sich"
    gemeldet = []
    start = time.monotonic()
    erg = sr.am_server_rechnen(z, [teil], args2, True, melden=lambda f, g, tx: gemeldet.append((f, g, tx)))
    dauer_server = time.monotonic() - start
    assert erg[0] is True and "am Server gerechnet" in erg[1], (erg, protokoll)
    letzte = db1.con.execute(f"SELECT zustand, rechner, kuerzel, fortschritt, gesamt FROM {sr.AUFTRAEGE} "
                             "ORDER BY id DESC LIMIT 1").fetchone()
    assert tuple(letzte) == (sr.FERTIG, r.name, "AB", 1, 1), letzte
    eintraege = [e for e in (ablage / sr.CACHE).iterdir() if (e / "ergebnis.json").is_file()]
    assert len(eintraege) == 1, eintraege
    # der Platz misst danach aus dem gemeinsamen Zwischenspeicher – bitgleich zur Messung ohne Server
    werte_server, aus = messen([teil], args2, tmp / "platz")
    assert "aus dem Zwischenspeicher" in aus, aus
    ohne = list(args2)
    ohne[ohne.index("--cache") + 1] = str(tmp / "eigener-cache")
    werte_lokal, aus = messen([teil], ohne, tmp / "lokal")
    assert "aus dem Zwischenspeicher" not in aus
    assert werte_server == werte_lokal, "Messung am Server = Messung am Platz"
    ok(f"Rechner am Server misst ({dauer_server:.1f} s), Fortschritt und Ende in der Tabelle; der Platz liest danach "
       "aus dem gemeinsamen Zwischenspeicher, bitgleich zur Messung ohne Server")

    # ------------------------------------------------------------------ laufender Auftrag abbrechen (langsames Programm)
    langsam = tmp / "langsam.py"
    langsam.write_text("import sys, time\nfor i in range(1, 61):\n    print(f'[{i}/60] Teil', flush=True)\n"
                       "    time.sleep(0.5)\n", encoding="utf-8")
    r2 = sr.Rechner(r.verbinden, ablage, [sys.executable, str(langsam)], "0.0.0-langsam", name="LANGSAM")
    a2 = sr.einreichen(pg, rel, ["--cache", "x"], False, "0.0.0-langsam", ablage=z["ablage"])
    t2 = threading.Thread(target=r2.einmal, daemon=True)
    t2.start()
    assert warten(lambda: (sr.zustand(pg, a2) or {}).get("fortschritt", 0) >= 2, 20), sr.zustand(pg, a2)
    assert sr.zustand(pg, a2)["zustand"] == sr.LAEUFT and sr.zustand(pg, a2)["gesamt"] == 60
    sr.abbrechen(pg, a2)
    t2.join(20)
    assert not t2.is_alive() and sr.zustand(pg, a2)["zustand"] == sr.ABGEBROCHEN, sr.zustand(pg, a2)
    # Server ausgelastet: ein Rechner ist da, nimmt den Auftrag aber nicht an → der Platz rechnet selbst
    r2.lebenszeichen(sofort=True)
    z_belegt = dict(z, version="0.0.0-langsam")
    erg = sr.am_server_rechnen(z_belegt, [teil], ["--cache", "y"], False, warten_start_s=1.0)
    assert erg == (False, "Server ausgelastet"), erg
    r2.abmelden()
    ok("Laufender Auftrag: Fortschritt in der Tabelle, Abbruch beendet das Programm; Server ausgelastet: der Platz "
       "rechnet selbst")

    # ------------------------------------------------------------------ Vormessung, Oberfläche, Status
    from rohrlaser import anfrage_vorab
    teil2 = tmp / "Kunde" / "Teil RE60.step"
    shutil.copyfile(HIER / "step_referenz" / "REF01_RE60x40x2_L1000.step", teil2)

    class Anfrage:
        kunde = None
        step = [teil2]
        mails, archive = [], []
    job = anfrage_vorab.auftrag(db2, PROGRAMM, Anfrage())
    assert job and job.get("server") and job["server"]["ablage"] == str(ablage), job
    n_vorher = db1.con.execute(f"SELECT count(*) FROM {sr.AUFTRAEGE} WHERE zustand = 'fertig'").fetchone()[0]
    werte = anfrage_vorab.messen(job, Anfrage())
    assert werte and not werte[0].get("fehler"), werte
    n_nachher = db1.con.execute(f"SELECT count(*) FROM {sr.AUFTRAEGE} WHERE zustand = 'fertig'").fetchone()[0]
    assert n_nachher == n_vorher + 1, "Vormessung lief am Server"
    from PySide6.QtWidgets import QApplication
    from rohrlaser import server_dialog
    from rohrlaser.fenster import Hauptfenster
    app = QApplication.instance() or QApplication([])
    f2 = Hauptfenster(db2, stumm=True)
    teil3 = tmp / "Kunde" / "Teil RR42.step"
    shutil.copyfile(HIER / "step_referenz" / "REF03_RR42-4x2_L1000.step", teil3)
    assert server_dialog.vorrechnen(f2, f2, [teil3], args2) is True
    db2.einstellung_setzen(sr.ORT, "an diesem Arbeitsplatz")
    assert server_dialog.vorrechnen(f2, f2, [teil3], args2) is None
    text = f2.datenspeicher_anzeigen()
    assert "Rechnen am Server: 1 Rechner bereit" in text and "dieser Platz: an diesem Arbeitsplatz" in text, text
    f2.stumm = True
    f2.close()
    ok("Vormessung einer Anfrage über den Server; Fortschrittsfenster beim Import; Datei → Datenbank zeigt Rechner "
       "und Aufträge")
finally:
    for s in stopps:
        s.set()
    for t in threads:
        t.join(15)
    for db in offen:
        try:
            db.schliessen()
        except Exception:       # noqa: BLE001
            pass
    datenspeicher.alle_stoppen()
    server.stoppen()
print("alle Prüfungen bestanden")
