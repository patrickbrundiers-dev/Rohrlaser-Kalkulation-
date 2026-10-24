"""Eigenen Programmcode zu Maschinencode übersetzen (Plan „Quellcode schützen“, Q3), damit weder Python-Quelltext
noch zurückübersetzbarer Bytecode des eigenen Codes ausgeliefert wird.

Jedes eigene Modul (programm/rohrlaser/*.py außer __init__.py, programm/step_messung/step_*.py außer der Startdatei
step_start.py) wird mit Cython nach C übersetzt und als Erweiterungsmodul (.pyd unter Windows, .so unter Linux)
gebaut. Die Startdateien start.py und step_start.py bleiben bewusst winzig: Sie importieren nur das übersetzte Modul.
rohrlaser.spec und step_messung.spec tauschen beim Build (Umgebungsvariable RL_KOMPILIERT = Zielordner) die Module
im PYZ-Archiv gegen diese Erweiterungsmodule (kompiliert_tauschen); release_pruefen.py prüft danach, dass kein
eigenes Modul mehr als Bytecode im Paket steckt.

Aufruf:  python programm/kompilieren.py ZIELORDNER [-j N]
         legt ZIELORDNER/rohrlaser/… und ZIELORDNER/step_messung/… mit den Erweiterungsmodulen neben den Quellen an.

Cython-Einstellungen: language_level 3; annotation_typing aus (Typangaben im Code sind Hinweise und dürfen nicht
zu harten C-Typen werden, sonst lehnt ein Aufruf mit int statt float ab); binding an (Funktionen verhalten sich wie
Python-Funktionen, lassen sich für die Hilfsprozesse picklen und von Qt als Slot verbinden).
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

HIER = Path(__file__).resolve().parent
# Dateien, die als Python bleiben: Paket-Kopf (nur Version und Name) und die Startdateien
BLEIBT = {"rohrlaser/__init__.py", "step_messung/step_start.py"}
# Rechenintensive Module mit voller C-Optimierung; alle übrigen (Fenster, Dialoge, Datenbank) ohne, das spart beim
# Build den größten Teil der Übersetzungszeit und macht im Betrieb keinen spürbaren Unterschied
SCHNELL = {"rohrlaser.optimierung", "rohrlaser.parallel", "rohrlaser.rechnen", "rohrlaser.rohr3d", "rohrlaser.blech3d",
           "rohrlaser.schneidweg", "step_geometrie", "step_abwicklung"}
OHNE_OPTIMIERUNG = ["/Od"] if sys.platform == "win32" else ["-O0"]
DIREKTIVEN = dict(language_level=3, annotation_typing=False, binding=True, embedsignature=False, infer_types=False)


def module(programm=HIER):
    """(Modulname, Pfad relativ zu programm/) aller eigenen Module, die übersetzt werden."""
    programm = Path(programm)
    liste = [(f"rohrlaser.{p.stem}", f"rohrlaser/{p.name}") for p in sorted((programm / "rohrlaser").glob("*.py"))]
    liste += [(p.stem, f"step_messung/{p.name}") for p in sorted((programm / "step_messung").glob("step_*.py"))]
    return [(name, rel) for name, rel in liste if rel not in BLEIBT]


def eigen(name):
    """True, wenn der Modulname zum eigenen Code gehört (rohrlaser.* oder die STEP-Messung step_*)."""
    return name == "rohrlaser" or name.startswith("rohrlaser.") or name.startswith("step_")


def gebaut(ziel, rel):
    """Pfad des gebauten Erweiterungsmoduls zu einer Quelle (rohrlaser/x.py → rohrlaser/x.cp312-win_amd64.pyd) oder None."""
    q = Path(ziel) / rel
    treffer = sorted(p for p in q.parent.glob(q.stem + ".*") if p.suffix in (".pyd", ".so"))
    return treffer[0] if treffer else None


def kompiliert_tauschen(analyse, ziel):
    """Für rohrlaser.spec/step_messung.spec: eigene Module aus analyse.pure (Bytecode im PYZ) entfernen und die
    übersetzten Erweiterungsmodule aus ZIEL als Binärdateien an dieselbe Stelle legen. Gibt die Anzahl zurück.
    Fehlt zu einem eigenen Modul das übersetzte, bricht der Build ab (lieber kein Paket als ein lesbares)."""
    ziel = Path(ziel)
    namen = dict(module(ziel))
    neu_pure, getauscht = [], 0
    for eintrag in analyse.pure:
        name = eintrag[0]
        if name not in namen:
            neu_pure.append(eintrag)
            continue
        datei = gebaut(ziel, namen[name])
        if datei is None:
            raise SystemExit(f"kompilieren: {name} ist nicht übersetzt ({ziel / namen[name]})")
        teile = name.split(".")
        ablage = "/".join(teile[:-1] + [datei.name])
        analyse.binaries.append((ablage, str(datei), "EXTENSION"))
        getauscht += 1
    analyse.pure[:] = neu_pure
    return getauscht


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("ziel")
    ap.add_argument("-j", type=int, default=os.cpu_count() or 1)
    args = ap.parse_args(argv)
    from Cython.Build import cythonize
    from setuptools import Extension, setup

    ziel = Path(args.ziel).resolve()
    for ordner in ("rohrlaser", "step_messung"):
        shutil.copytree(HIER / ordner, ziel / ordner, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.spec", "*.pyc"))
    liste = module(ziel)
    alt = os.getcwd()
    # rohrlaser.* wird von ZIEL aus als Paket gebaut, step_* als Module ohne Paket im Ordner step_messung
    for basis, gruppe in ((ziel, [(n, r) for n, r in liste if r.startswith("rohrlaser/")]),
                          (ziel / "step_messung", [(n, Path(r).name) for n, r in liste if r.startswith("step_messung/")])):
        os.chdir(basis)
        try:
            erweiterungen = [Extension(name, [rel], extra_compile_args=[] if name in SCHNELL else OHNE_OPTIMIERUNG)
                             for name, rel in gruppe]
            setup(name="rohrlaser-kompiliert", ext_modules=cythonize(erweiterungen, compiler_directives=DIREKTIVEN,
                                                                      nthreads=args.j, quiet=True),
                  script_args=["build_ext", "--inplace", "-j", str(args.j)])
        finally:
            os.chdir(alt)
    fehlt = [rel for _, rel in liste if gebaut(ziel, rel) is None]
    if fehlt:
        print("Nicht übersetzt:", ", ".join(fehlt), file=sys.stderr)
        return 1
    print(f"{len(liste)} Module übersetzt nach {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
