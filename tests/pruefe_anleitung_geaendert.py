"""Pflicht bei jeder Änderung: Ändert ein Pull Request das Programm, muss er auch die Bedienungsanleitung
(anleitung/) anpassen – oder in einer Commit-Nachricht begründen, warum nicht:

    Anleitung: unverändert, weil nur ein Rechenfehler behoben wurde

Aufruf: python tests/pruefe_anleitung_geaendert.py BASIS   (z. B. origin/main; braucht die volle Git-Historie)
"""
import re
import subprocess
import sys

BEGRUENDUNG = re.compile(r"^Anleitung:\s*unverändert\b.*\S", re.MULTILINE | re.IGNORECASE)


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def main():
    basis = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    geaendert = git("diff", "--name-only", f"{basis}...HEAD").split()
    programm = [d for d in geaendert if d.startswith("programm/")]
    anleitung = [d for d in geaendert if d.startswith("anleitung/")]
    if not programm:
        print("Programm unverändert, Anleitung muss nicht angepasst werden.")
        return 0
    if anleitung:
        print(f"OK: {len(programm)} Programmdatei(en) und die Anleitung ({', '.join(anleitung)}) geändert.")
        return 0
    grund = BEGRUENDUNG.search(git("log", "--format=%B", f"{basis}..HEAD"))
    if grund:
        print(f"OK: Programm geändert, Anleitung bewusst nicht – {grund.group(0).strip()}")
        return 0
    print("FEHLER: Das Programm wurde geändert, die Bedienungsanleitung (anleitung/) nicht:\n  "
          + "\n  ".join(programm)
          + "\n\nBitte anleitung/erzeuge_anleitung.py (und ggf. anleitung/bilder.py) anpassen. Braucht die Änderung "
            "wirklich keinen neuen Text, in einer Commit-Nachricht eine Zeile\n"
            "  Anleitung: unverändert, weil …\nschreiben.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
