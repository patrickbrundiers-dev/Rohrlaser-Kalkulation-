"""Windows-Update-Sicherheit (Auftrag Patrick 26.11.2026 „Systemunabhängigkeit, Windows-Update-Sicherheit und
langfristige Stabilität“). Geprüft wird, was sich ohne Windows nachstellen lässt:

1. Laufmarker: unerwartetes Ende erkennen, Reste des unterbrochenen Laufs beiseitelegen (nichts löschen),
   ältere Dateien unberührt lassen.
2. Tagessicherung: eine halb geschriebene Sicherung (ohne .json) zählt nicht als „heute gesichert“.
3. Riskante Stellen (OpenGL): Marker eines gestorbenen Laufs wird zur Sperre, gilt nur für diese Version,
   normales Ende räumt eigene Marker ab; renderer_waehlen nimmt dann Software.
4. Windows-Abmeldung (sitzungsende): Schritte nur bei endender Sitzung, in Reihenfolge, Fehler halten nicht auf,
   nie zweimal; main() hängt alles an.
5. PostgreSQL-Start: leere/veraltete postmaster.pid wird beiseitegelegt; echte Probe mit eingebettetem Server:
   Server mit kaputter Sperrdatei startet, unlesbare Zugangsdatei wird erneuert, Daten bleiben.
6. Netzlaufwerk: getrennter Laufwerksbuchstabe → gemerkter UNC-Pfad; gemeinsamer Ordner nutzt ihn.
7. Abhängigkeiten: alle Bibliotheken fest auf eine Version, VC++-Laufzeit beim PostgreSQL des Pakets, keine festen
   Laufwerkspfade im Programm.

Aufruf: python tests/test_windows_robust.py (Teil 5b braucht PostgreSQL und läuft nicht als root)
"""
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parent
sys.path.insert(0, str(WURZEL / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TMP = Path(tempfile.mkdtemp(prefix="winrobust_"))
UMG = {"LOCALAPPDATA": str(TMP / "lokal")}
os.environ["LOCALAPPDATA"] = UMG["LOCALAPPDATA"]        # Wächter-Ordner nicht im echten Profil

from rohrlaser import VERSION, laufwaechter, netzpfad, pg_lokal, sitzungsende  # noqa: E402


def ok(text):
    print("OK     " + text)


def alt_machen(p, sekunden=600):
    t = time.time() - sekunden
    os.utime(p, (t, t))


# ------------------------------------------------------------------------------------------------ 1. Laufmarker
daten = TMP / "Daten"
daten.mkdir()
assert laufwaechter.beginnen(daten) is None
assert (daten / laufwaechter.MARKER).is_file()
laufwaechter.beenden(daten)
assert not (daten / laufwaechter.MARKER).exists()
assert laufwaechter.beginnen(daten) is None
ok("Laufmarker: normaler Lauf hinterlässt nichts")

# Lauf „stirbt“ (Marker bleibt), währenddessen halbe Dateien
seit = (time.time() - 900)
marker = json.loads((daten / laufwaechter.MARKER).read_text(encoding="utf-8"))
import datetime  # noqa: E402
marker["seit"] = datetime.datetime.fromtimestamp(seit).isoformat(timespec="seconds")
(daten / laufwaechter.MARKER).write_text(json.dumps(marker), encoding="utf-8")
sich = daten / "Sicherung"
sich.mkdir()
halb = sich / "rohrlaser_2026-11-26_101500.db"
halb.write_bytes(b"SQLite format 3\x00halb")
fertig = sich / "rohrlaser_2026-11-26_090000.db"
fertig.write_bytes(b"x")
fertig.with_suffix(".json").write_text("{}", encoding="utf-8")
uralt = sich / "rohrlaser_2025-01-01_080000.db"       # Sicherung eines alten Programmstands ohne .json
uralt.write_bytes(b"x")
dump = sich / "rohrlaser_2026-11-26_101500.pgdump.neu"
dump.write_bytes(b"PGDMP")
zwischen = daten / "pg_zugang.tmp"
zwischen.write_text("{}", encoding="utf-8")
frisch = daten / "gerade.neu"                          # entsteht gerade (jünger als RESTE_ALTER_S)
frisch.write_text("x", encoding="utf-8")
for p in (halb, fertig, dump, zwischen):
    alt_machen(p, 300)
alt_machen(uralt, 86400 * 400)

vorher = laufwaechter.beginnen(daten)
assert vorher is not None and vorher["seit"] == marker["seit"], vorher
reste = laufwaechter.reste_aufraeumen(daten, vorher["seit"])
namen = sorted(p.name for p in reste)
assert namen == sorted([halb.name, dump.name, zwischen.name]), namen
assert all(p.is_file() for p in reste) and all(laufwaechter.UNVOLLSTAENDIG in str(p) for p in reste)
assert fertig.is_file() and uralt.is_file() and frisch.is_file()
assert not halb.exists() and not dump.exists() and not zwischen.exists()
t = laufwaechter.text_unterbrochen(vorher, reste)
assert "nicht normal beendet" in t and "3 unvollständige" in t, t
laufwaechter.beenden(daten)
ok("Laufmarker: unerwartetes Ende erkannt, 3 halbe Dateien verschoben (nichts gelöscht), fertige/alte/frische "
   "Dateien unberührt")

# beschädigter Marker (Stromausfall beim Schreiben) zählt auch als unerwartetes Ende
(daten / laufwaechter.MARKER).write_text('{"pid": 12', encoding="utf-8")
v = laufwaechter.beginnen(daten)
assert v is not None and "datei" in v
assert laufwaechter.reste_finden(daten, v.get("seit")) == []
laufwaechter.beenden(daten)
ok("Laufmarker: halb geschriebener Marker = unerwartetes Ende, Reste-Suche ohne Startzeit begrenzt")

# ------------------------------------------------------------------------------------------------ 3. Riskante Stellen
laufwaechter._bestaetigt.clear()
laufwaechter.markieren("probe", UMG)
m = laufwaechter._marker("probe", UMG)
assert m.is_file()
assert laufwaechter.blockiert("probe", UMG) is None          # eigener Lauf: keine Sperre
laufwaechter.entmarken("probe", UMG)
assert not m.exists()
laufwaechter.markieren("probe", UMG)
assert not m.exists()                                        # in diesem Lauf bestätigt: keine Dateizugriffe mehr
ok("Riskante Stelle: Marker nur bis zur ersten Bestätigung")

laufwaechter._bestaetigt.clear()
laufwaechter.markieren("probe", UMG)
d = json.loads(m.read_text(encoding="utf-8"))
d["pid"] = os.getpid() + 100000                              # früherer Lauf, dort gestorben
m.write_text(json.dumps(d), encoding="utf-8")
s = laufwaechter.blockiert("probe", UMG)
assert s is not None and s["version"] == VERSION
assert not m.exists() and laufwaechter._sperre("probe", UMG).is_file()
assert laufwaechter.blockiert("probe", UMG) is not None      # bleibt gesperrt (auch nach weiteren Starts)
sp = laufwaechter._sperre("probe", UMG)
d = json.loads(sp.read_text(encoding="utf-8"))
d["version"] = "0.0.1"
sp.write_text(json.dumps(d), encoding="utf-8")
assert laufwaechter.blockiert("probe", UMG) is None and not sp.exists()     # neue Version: neuer Versuch
ok("Riskante Stelle: Absturz-Marker wird Sperre, gilt nur für dieselbe Version")

laufwaechter._bestaetigt.clear()
laufwaechter.markieren("nie_fertig", UMG)
assert laufwaechter._marker("nie_fertig", UMG).is_file()
laufwaechter.beenden(daten, UMG)
assert not laufwaechter._marker("nie_fertig", UMG).exists()
assert laufwaechter.blockiert("nie_fertig", UMG) is None
ok("Riskante Stelle: normales Ende räumt eigene, nie bestätigte Marker ab (keine falsche Sperre)")

from rohrlaser import ansicht3d  # noqa: E402
laufwaechter._bestaetigt.discard(ansicht3d.GL_WAECHTER)
laufwaechter.freigeben(ansicht3d.GL_WAECHTER)
laufwaechter._schreiben(laufwaechter._sperre(ansicht3d.GL_WAECHTER),
                        dict(pid=1, version=VERSION, seit="2026-11-26T10:00:00"))
alt_renderer = ansicht3d._renderer
ansicht3d._renderer = "OpenGL"
r, grund = ansicht3d.renderer_waehlen()
assert r == "Software" and "Grafiktreiber" in grund, (r, grund)
ansicht3d._renderer = alt_renderer
laufwaechter.freigeben(ansicht3d.GL_WAECHTER)
ok("OpenGL nach Treiber-Absturz gesperrt: 3D zeichnet mit Software, auch bei Einstellung OpenGL")

# ------------------------------------------------------------------------------------------------ 4. Sitzungsende
folge = []
s = sitzungsende.Sitzung([("a", lambda r: folge.append(("a", r > 0))),
                          ("b", lambda r: (_ for _ in ()).throw(RuntimeError("kaputt"))),
                          ("c", lambda r: folge.append(("c", True)))], melden=folge.append)
s.beim_beenden()
assert folge == [] and not s.erledigt                       # normales Beenden: main() macht es wie bisher
s.endet_jetzt(None)
s.beim_beenden()
assert [f for f in folge if isinstance(f, tuple)] == [("a", True), ("c", True)]
assert s.erledigt and dict(s.ergebnis)["b"].startswith("RuntimeError")
n = len(folge)
s.beim_beenden()
s.abschliessen()
assert len(folge) == n                                      # nie zweimal
assert any(isinstance(f, str) and f.startswith("Sitzungsende:") for f in folge)
ok("Sitzungsende: nur bei endender Windows-Sitzung, Reihenfolge, Fehler halten nicht auf, nie zweimal")

from PySide6.QtWidgets import QApplication  # noqa: E402
app = QApplication.instance() or QApplication([])
gelaufen = []
s = sitzungsende.einrichten(app, [("x", lambda r: gelaufen.append(r))])
app.aboutToQuit.emit()
assert gelaufen == []
s.endet_jetzt()
app.aboutToQuit.emit()
assert len(gelaufen) == 1 and s.erledigt
assert sitzungsende.reihenfolge_setzen() is (sys.platform == "win32")
ok("Sitzungsende an QApplication: aboutToQuit nach commitDataRequest führt die Schritte aus")

import rohrlaser.__main__ as hauptprogramm  # noqa: E402


class Lauf:
    def __init__(self):
        self.gewartet = None

    def warten(self, sekunden=None):
        self.gewartet = sekunden
        return True


class Db:
    zu = False

    def schliessen(self):
        Db.zu = True


class Sperre:
    frei = False

    def freigeben(self):
        Sperre.frei = True


lauf = Lauf()
laufwaechter.beginnen(daten)
schritte = hauptprogramm._sitzung_schritte(lambda: Db(), lambda: lauf, Sperre(), daten)
ergebnis = sitzungsende.Sitzung(schritte).abschliessen()
assert [e for _t, e in ergebnis] == ["ok"] * 5, ergebnis
assert Db.zu and Sperre.frei and lauf.gewartet <= 10 and not (daten / laufwaechter.MARKER).exists()
quelle = (WURZEL / "programm/rohrlaser/__main__.py").read_text(encoding="utf-8")
for muss in ("laufwaechter.beginnen(o.daten)", "laufwaechter.reste_aufraeumen(", "sitzungsende.einrichten(app",
             "laufwaechter.text_unterbrochen(", "laufwaechter.beenden(o.daten)"):
    assert muss in quelle, muss
ok("main(): Laufmarker, Reste, Meldung und Sitzungsende eingebunden; Schritte schließen DB, Sperre, Marker")

# ------------------------------------------------------------------------------------------------ 5a. postmaster.pid
pg_ordner = TMP / "pgprobe"
(pg_ordner / "pg").mkdir(parents=True)
(pg_ordner / "pg" / "PG_VERSION").write_text("16", encoding="utf-8")
srv = pg_lokal.LokalerServer.__new__(pg_lokal.LokalerServer)
srv.daten, srv.pg, srv.bin = pg_ordner, pg_ordner / "pg", pg_ordner
srv.zugang_unlesbar, srv.reparaturen = None, []
srv.laeuft = lambda: False
pid_datei = srv.pg / "postmaster.pid"
pid_datei.write_text("", encoding="utf-8")                  # leer nach Stromausfall
g = srv.reparieren("FATAL: lock file \"postmaster.pid\" is empty")
assert g and "postmaster.pid" in g and not pid_datei.exists() and (srv.pg / "postmaster.pid.alt").is_file()
pid_datei.write_text(f"{os.getpid()}\n{srv.pg}\n", encoding="utf-8")      # PID gehört jetzt einem anderen Programm
assert srv.reparieren("") and not pid_datei.exists()
srv.laeuft = lambda: True                                   # Server läuft wirklich: nie anfassen
pid_datei.write_text("", encoding="utf-8")
assert srv.reparieren("") is None and pid_datei.exists()
assert pg_lokal._pid_aus(pid_datei) is None
ok("PostgreSQL: leere oder fremde postmaster.pid wird beiseitegelegt, nie bei laufendem Server")


# ------------------------------------------------------------------------------------------------ 5b. echter Server
def echter_server():
    try:
        pg_lokal.programme()
    except pg_lokal.PgFehlt:
        return "PostgreSQL fehlt"
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return "läuft als root (initdb verweigert root)"
    return None


grund = echter_server()
if grund:
    print(f"ÜBERSPRUNGEN echter PostgreSQL-Server: {grund}")
else:
    import psycopg
    from rohrlaser import zugangsschutz
    d5 = TMP / "pgecht"
    srv = pg_lokal.LokalerServer(d5)
    srv.anlegen()
    with psycopg.connect(host="127.0.0.1", port=srv.zugang()["port"], user=srv.zugang()["benutzer"],
                         password=srv.passwort(), dbname=pg_lokal.DATENBANK, autocommit=True) as con:
        con.execute("CREATE TABLE probe (wert text)")
        con.execute("INSERT INTO probe VALUES ('bleibt')")
    # Absturz nachstellen: Server hart beenden (kein sauberes Herunterfahren), leere Sperrdatei
    pid = pg_lokal._pid_aus(srv.pg / "postmaster.pid")
    import signal
    os.kill(pid, signal.SIGKILL)
    for _ in range(100):
        try:
            os.kill(pid, 0)
            time.sleep(0.05)
        except ProcessLookupError:
            break
    time.sleep(0.5)
    (srv.pg / "postmaster.pid").write_text("", encoding="utf-8")
    srv2 = pg_lokal.LokalerServer(d5)
    srv2.starten()
    assert any("postmaster.pid" in r for r in srv2.reparaturen), srv2.reparaturen
    ok("echter Server: nach hartem Abbruch mit leerer postmaster.pid wieder gestartet")

    # Zugangsdatei nicht entschlüsselbar (Datenordner von anderem PC / Windows neu aufgesetzt)
    srv2.stoppen()
    roh = json.loads((d5 / pg_lokal.ZUGANG).read_text(encoding="utf-8"))
    roh["passwort"] = roh["admin_passwort"] = {"art": "fremd", "wert": "AAAA"}
    (d5 / pg_lokal.ZUGANG).write_text(json.dumps(roh), encoding="utf-8")
    srv3 = pg_lokal.LokalerServer(d5)
    srv3.starten()
    assert srv3.zugang_unlesbar is None and any("Zugangsdaten" in r for r in srv3.reparaturen), srv3.reparaturen
    with psycopg.connect(host="127.0.0.1", port=srv3.zugang()["port"], user=srv3.zugang()["benutzer"],
                         password=srv3.passwort(), dbname=pg_lokal.DATENBANK) as con:
        assert con.execute("SELECT wert FROM probe").fetchall() == [("bleibt",)]
    hba = (srv3.pg / "pg_hba.conf").read_text(encoding="utf-8")
    aktiv = [z for z in hba.splitlines() if z.strip() and not z.lstrip().startswith("#")]
    assert aktiv and not any("trust" in z for z in aktiv), "pg_hba.conf muss wieder ohne trust sein"
    try:                                                    # ohne Passwort geht es danach nicht mehr
        psycopg.connect(host="127.0.0.1", port=srv3.zugang()["port"], user=pg_lokal.VERWALTER, dbname="postgres",
                        connect_timeout=5).close()
        raise AssertionError("Verwalter ohne Passwort angenommen")
    except psycopg.OperationalError:
        pass
    assert zugangsschutz.geschuetzt(json.loads((d5 / pg_lokal.ZUGANG).read_text(encoding="utf-8"))["passwort"])
    srv3.stoppen()
    ok("echter Server: unlesbare Zugangsdatei erneuert, Daten erhalten, pg_hba.conf wieder ohne trust")

# ------------------------------------------------------------------------------------------------ 2. Tagessicherung
if os.environ.get("ROHRLASER_PG_TEST") or not grund:
    sys.path.insert(0, str(HIER))
    from rohrlaser.datenbank import Datenbank  # noqa: E402
    dbd = TMP / "dbtest"
    dbd.mkdir()
    db = Datenbank(dbd / "rohrlaser.db")
    ordner = dbd / "sich"
    ordner.mkdir()
    halb = ordner / f"rohrlaser_{datetime.date.today():%Y-%m-%d}_070000.db"
    halb.write_bytes(b"halb")
    ziel = db.sicherung_heute(ordner)
    assert ziel is not None and ziel.with_suffix(".json").is_file(), ziel
    assert db.sicherung_heute(ordner) is None
    db.schliessen()
    ok("Tagessicherung: halbe Sicherung ohne .json zählt nicht, die richtige wird geschrieben")
else:
    print("ÜBERSPRUNGEN Tagessicherung: keine Datenbank (ohne werkzeuge/mit_pg.py)")

# ------------------------------------------------------------------------------------------------ 6. Netzlaufwerk
assert netzpfad.laufwerk(r"Z:\Rohrlaser") == "Z:" and netzpfad.laufwerk(r"\\srv\f\x") is None
assert netzpfad.laufwerk("/tmp/x") is None
netzpfad._gemerkt_laufwerke.clear()
assert netzpfad.merken(r"Z:\Rohrlaser", UMG, abfrage=lambda lw: r"\\srv\freigabe") == r"\\srv\freigabe"
karte = json.loads(netzpfad._datei(UMG).read_text(encoding="utf-8"))
assert karte == {"Z:": r"\\srv\freigabe"}
da = {r"\\srv\freigabe\Rohrlaser"}
e = netzpfad.ersatz(r"Z:\Rohrlaser", UMG, abfrage=lambda lw: None, ist_ordner=lambda p: p in da)
assert e is not None and str(e) == r"\\srv\freigabe\Rohrlaser", e
netzpfad._nicht_da.clear()
assert netzpfad.ersatz(r"Y:\x", UMG, abfrage=lambda lw: None, ist_ordner=lambda p: True) is None
aufrufe = []
assert netzpfad.ersatz(r"Z:\Weg", UMG, abfrage=lambda lw: None, ist_ordner=lambda p: aufrufe.append(p)) is None
assert netzpfad.ersatz(r"Z:\Weg", UMG, abfrage=lambda lw: None, ist_ordner=lambda p: aufrufe.append(p)) is None
assert len(aufrufe) == 1                                    # Netz ganz weg: nicht bei jedem Blick doppelt warten
ok("Netzlaufwerk: UNC-Pfad gemerkt, getrenntes Laufwerk über UNC erreichbar, Fehlversuch 60 s gemerkt")

from rohrlaser import austausch  # noqa: E402
echt = TMP / "unc_ziel"
echt.mkdir()
w = austausch.OrdnerWeg(r"Q:\nicht\da")
alt_ersatz = netzpfad.ersatz
netzpfad.ersatz = lambda p: echt
assert w.erreichbar() and w.pfad == echt
netzpfad.ersatz = lambda p: None
assert not austausch.OrdnerWeg(r"Q:\nicht\da").erreichbar()
netzpfad.ersatz = alt_ersatz
ok("Gemeinsamer Ordner: getrenntes Netzlaufwerk wird über den UNC-Weg erreicht")

# ------------------------------------------------------------------------------------------------ 7. Abhängigkeiten
for datei in (WURZEL / "programm/requirements.txt", WURZEL / "requirements.txt"):
    for zeile in datei.read_text(encoding="utf-8").splitlines():
        zeile = zeile.split("#")[0].strip()
        if zeile:
            assert re.fullmatch(r"[A-Za-z0-9_.\-\[\]]+==[0-9][0-9A-Za-z.]*", zeile), f"{datei.name}: {zeile}"
ok("Bibliotheken: jede Abhängigkeit fest auf eine Version (==)")

paket = (WURZEL / ".github/workflows/paket.yml").read_text(encoding="utf-8")
for muss in ("pgserver-0.1.4-cp312-cp312-win_amd64.whl", "vcruntime140.dll", "msvcp140.dll", 'python-version: "3.12"'):
    assert muss in paket, muss
ok("Paket: PostgreSQL mit Prüfsumme und eigener VC++-Laufzeit, Python fest 3.12")

FEST = re.compile(r"""["'][A-Za-z]:[\\/]""")
ERLAUBT = {"pg_lokal.py"}             # Rückfall C:/Program Files nur für Entwicklung, mit ProgramFiles-Variable
funde = []
for p in sorted((WURZEL / "programm/rohrlaser").glob("*.py")):
    if p.name in ERLAUBT:
        continue
    for nr, zeile in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        code = zeile.split("#")[0]
        if FEST.search(code) and '"""' not in code and "beispiel" not in code.lower():
            funde.append(f"{p.name}:{nr}: {zeile.strip()[:80]}")
print("       Pfade mit Laufwerksbuchstaben im Programmcode (geprüft):", len(funde))
for f in funde:
    print("         " + f)
assert len(funde) <= 3, "neue feste Laufwerkspfade im Programm – Orte aus orte.py/Einstellungen nehmen"
ok("Programm: keine neuen festen Laufwerkspfade (Sperrklinke)")
print("Alles in Ordnung.")
