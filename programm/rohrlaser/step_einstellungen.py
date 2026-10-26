"""Einstellungen des STEP-Imports (Reiter Einstellungen, Karte STEP-Import) für Messung und Erkennung.

anwenden(db): Toleranzen des Programms setzen (step.TOL_MASS, step.TOL_GLEICH, bohrbild.TOL_KERNLOCH); beim Start und
nach jeder Änderung. mess_argumente(db): Aufrufargumente für STEP-Import.exe (Prozesse, Zeitlimit, Zwischenspeicher,
Grenzwerte der Erkennung). Die Vorgaben sind die bisher festen Werte, ohne Änderung bleibt das Ergebnis gleich.
"""
import shutil
from pathlib import Path

from . import VERSION, baugruppe, bohrbild, step

CACHE_ORDNER = "STEP-Cache"     # neben der Datenbank
TOLERANZEN = {"step_tol_profil": (step, "TOL_MASS", 0.15), "step_tol_gleich": (step, "TOL_GLEICH", 0.2),
              "step_tol_kernloch": (bohrbild, "TOL_KERNLOCH", 0.05)}
# außerhalb der Karte STEP-Import, aber ebenso beim Start und nach jeder Änderung gesetzt
WEITERE = {"schweiss_spalt_max": (baugruppe, "SPALT_MAX", 2.0)}
EINSTELLUNGEN = set(TOLERANZEN) | {"step_prozesse", "step_zeitlimit", "step_cache", "step_cache_mb",
                                   "step_flach_laenge", "step_gekantet_anteil", "step_naht_spalt"}


def _zahl(db, name, vorgabe):
    v = db.einstellung(name)
    return float(v) if isinstance(v, (int, float)) else vorgabe


def anwenden(db):
    for name, (modul, glob, vorgabe) in (TOLERANZEN | WEITERE).items():
        setattr(modul, glob, _zahl(db, name, vorgabe))


def cache_ordner(db):
    return Path(db.pfad).parent / CACHE_ORDNER


def mess_argumente(db):
    args = ["--prozesse", str(int(_zahl(db, "step_prozesse", 0))),
            "--zeitlimit", f"{_zahl(db, 'step_zeitlimit', 120):g}",
            "--flach-laenge", f"{_zahl(db, 'step_flach_laenge', 3.0):g}",
            "--gekantet-anteil", f"{_zahl(db, 'step_gekantet_anteil', 0.85):g}",
            "--naht-spalt", f"{_zahl(db, 'step_naht_spalt', 3.0):g}"]
    if (db.einstellung("step_cache") or "ja") == "ja":
        args += ["--cache", str(cache_ordner(db)), "--cache-mb", f"{_zahl(db, 'step_cache_mb', 500):g}",
                 "--kennung", VERSION]
    return args


def cache_leeren(db):
    """Zwischenspeicher löschen. Ergebnis: Anzahl gelöschter Einträge."""
    ordner = cache_ordner(db)
    if not ordner.is_dir():
        return 0
    n = sum(1 for e in ordner.iterdir() if e.is_dir())
    shutil.rmtree(ordner, ignore_errors=True)
    return n
