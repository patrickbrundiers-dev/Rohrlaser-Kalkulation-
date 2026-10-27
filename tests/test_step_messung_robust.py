"""STEP-Messung robuster: Zeitlimit je Körper, Zwischenspeicher, Teilergebnis, Prozesse und STEP-Einstellungen."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
MESSEN = HIER.parent / "programm" / "step_messung" / "step_messen.py"

DATEIEN = sorted(HIER.glob("step_satz/*.st*")) + sorted(HIER.glob("step_profile/*.st*"))[:6]
BAUGRUPPE = HIER / "step_satz" / "T08_Gestell_Baugruppe.step"
assert BAUGRUPPE in DATEIEN and len(DATEIEN) >= 5
tmp = Path(tempfile.mkdtemp())


def messen(name, *args, umgebung=None, dateien=DATEIEN):
    aus, js, netze = tmp / f"{name}.txt", tmp / f"{name}.json", tmp / f"{name}_netze"
    env = dict(os.environ, **(umgebung or {}))
    r = subprocess.run([sys.executable, str(MESSEN), "--ausgabe", str(aus), "--json", str(js), "--netze", str(netze),
                        *args, *map(str, dateien)], capture_output=True, text=True, env=env, timeout=600)
    assert r.returncode in (0, 1), r.stderr
    daten = json.loads(js.read_text(encoding="utf-8"))
    daten.pop("erzeugt", None)
    netz = {p.name: p.read_text(encoding="utf-8") for p in sorted(netze.iterdir())}
    return aus.read_text(encoding="utf-8"), daten, netz, r.stdout


# 1. Ohne neue Argumente: wie bisher. Mit Aufsicht (Zeitlimit) und anderer Prozesszahl: dasselbe Ergebnis
alt = messen("alt")
for name, args in (("auf1", ["--zeitlimit", "120", "--prozesse", "1"]),
                   ("auf3", ["--zeitlimit", "120", "--prozesse", "3"]),
                   ("pool", ["--prozesse", "2"])):
    neu = messen(name, *args)
    assert neu[:3] == alt[:3], f"{name}: Ergebnis weicht ab"
    assert ('"koerper_n"' in neu[3]) == ("--zeitlimit" in args), "Fortschritt je Körper nur mit Aufsicht"
print("OK: Messung mit Zeitlimit-Aufsicht und 1/2/3 Prozessen gleich wie bisher")

# 2. Zwischenspeicher: zweite Messung aus dem Speicher, gleiches Ergebnis (auch Netze unter neuer Nummer)
cache = tmp / "cache"
erst = messen("c1", "--zeitlimit", "120", "--cache", str(cache), "--kennung", "test")
zweit = messen("c2", "--zeitlimit", "120", "--cache", str(cache), "--kennung", "test")
assert erst[:3] == alt[:3] and zweit[:3] == alt[:3]
assert f"[{len(DATEIEN)}/{len(DATEIEN)}] aus dem Zwischenspeicher" in zweit[3], zweit[3]
umgedreht = list(reversed(DATEIEN))     # andere Reihenfolge: Netze bekommen die neue laufende Nummer
dreh = messen("c3", "--cache", str(cache), "--kennung", "test", dateien=umgedreht)
frisch = messen("c4", dateien=umgedreht)
assert dreh[:3] == frisch[:3], "Zwischenspeicher mit anderer Reihenfolge weicht ab"
anders = messen("c5", "--cache", str(cache), "--kennung", "test", "--flach-laenge", "4")
assert "aus dem Zwischenspeicher" not in anders[3], "andere Einstellungen: neu messen"
neue_version = messen("c6", "--cache", str(cache), "--kennung", "andere Version")
assert "aus dem Zwischenspeicher" not in neue_version[3]
eintraege = [e for e in cache.iterdir() if e.is_dir()]
assert len(eintraege) == 3 * len(DATEIEN), len(eintraege)
messen("c7", "--cache", str(cache), "--kennung", "klein", "--cache-mb", "0.05")
groesse = sum(f.stat().st_size for e in cache.iterdir() for f in e.iterdir())
assert groesse <= 0.05 * 1024 * 1024 + 200_000, groesse        # höchstens der zuletzt geschriebene Eintrag darüber
print("OK: Zwischenspeicher (Treffer, Reihenfolge, Einstellungen/Version im Schlüssel, Größe begrenzt)")

# 3. Zeitlimit: hängender Körper wird nicht gemessen, die anderen schon, Datei landet nicht im Zwischenspeicher
cache2 = tmp / "cache2"
haengt = messen("haengt", "--zeitlimit", "2", "--cache", str(cache2), "--kennung", "t", dateien=[BAUGRUPPE],
                umgebung={"STEP_MESSEN_TEST_HAENGT": f"{BAUGRUPPE.name}:2"})
normal = messen("normal", dateien=[BAUGRUPPE])
k = {kp["nr"]: kp for kp in haengt[1]["dateien"][0]["koerper"]}
assert any("nicht gemessen: Zeitlimit 2 s überschritten" in h for h in k[2]["warnungen"]), k[2]
n = {kp["nr"]: kp for kp in normal[1]["dateien"][0]["koerper"]}
for nr in (1, 3, 4):
    assert k[nr] == n[nr], f"Körper {nr} anders als ohne Zeitlimit"
assert not any(e.is_dir() for e in cache2.iterdir()), "Datei mit ausgelassenem Körper nicht merken"
assert '"koerper": 2' in haengt[3]
print("OK: Zeitlimit je Körper (Körper 'nicht gemessen', übrige gleich, nicht im Zwischenspeicher)")

# 4. Einstellungen: Vorgaben = bisher feste Werte, anwenden setzt die Toleranzen, Argumente für die Messung
from rohrlaser import bohrbild, step, step_einstellungen, teilen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.stammdaten import EINSTELLUNG  # noqa: E402

db = Datenbank(tmp / "db" / "rohrlaser.db")
assert (step.TOL_MASS, step.TOL_GLEICH, bohrbild.TOL_KERNLOCH) == (0.15, 0.2, 0.05)
for name, (modul, glob, vorgabe) in step_einstellungen.TOLERANZEN.items():
    assert EINSTELLUNG[name].vorgabe == vorgabe == getattr(modul, glob)
sys.path.insert(0, str(MESSEN.parent))
import step_geometrie  # noqa: E402
assert EINSTELLUNG["step_flach_laenge"].vorgabe == step_geometrie.FLACHSTAHL_LAENGE
assert EINSTELLUNG["step_gekantet_anteil"].vorgabe == step_geometrie.GEKANTET_ANTEIL
for name in ("flach_als", "flachstahl_bis", "step_ordner", "step_werkstoff", "fliessloch_laser", "bohren_laser",
             *step_einstellungen.EINSTELLUNGEN):
    assert EINSTELLUNG[name].gruppe == "STEP-Import", name
assert {"step_prozesse", "step_cache", "step_cache_mb"} <= teilen.LOKAL
args = step_einstellungen.mess_argumente(db)
assert args[args.index("--zeitlimit") + 1] == "120" and "--cache" in args
assert args[args.index("--cache") + 1] == str(tmp / "db" / "STEP-Cache")
db.einstellung_setzen("step_tol_kernloch", 0.3)
db.einstellung_setzen("step_tol_profil", 0.4)
step_einstellungen.anwenden(db)
assert bohrbild.TOL_KERNLOCH == 0.3 and step.TOL_MASS == 0.4
assert step.gewinde_vorschlag("4.9:4", step.KERNLOCH) == "4xM6"
db.einstellung_setzen("step_tol_kernloch", 0.05)
step_einstellungen.anwenden(db)
assert step.gewinde_vorschlag("4.9:4", step.KERNLOCH) == ""
db.einstellung_setzen("step_cache", "nein")
assert "--cache" not in step_einstellungen.mess_argumente(db)
(tmp / "db" / "STEP-Cache" / "x").mkdir(parents=True)
assert step_einstellungen.cache_leeren(db) == 1 and not (tmp / "db" / "STEP-Cache").exists()
print("OK: STEP-Einstellungen (Vorgaben wie bisher, Gruppe STEP-Import, Toleranzen wirken, Zwischenspeicher leeren)")

# 5. Einstellungsseite: Karte STEP-Import mit Knopf "Zwischenspeicher leeren"
from PySide6.QtWidgets import QApplication, QPushButton  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

app = QApplication.instance() or QApplication([])
fenster = Hauptfenster(db, stumm=True)
assert "Zwischenspeicher leeren" in [k.text() for k in fenster.einstellungen.findChildren(QPushButton)]
assert "step_zeitlimit" in fenster.einstellungen.felder
print("OK: Karte STEP-Import mit Knopf 'Zwischenspeicher leeren' in den Einstellungen")
