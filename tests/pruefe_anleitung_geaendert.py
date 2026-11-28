"""Pflicht bei jeder Änderung: Ändert ein Pull Request das Programm, muss er auch die Bedienungsanleitung
(anleitung/) anpassen – oder in einer Commit-Nachricht begründen, warum nicht:

    Anleitung: unverändert, weil nur ein Rechenfehler behoben wurde

Ebenso das IT-Handbuch des Servers (Patrick 27.11.2026, „bei jeder Änderung mit aktualisieren“): Ändert ein Pull
Request die Server-Teile (SERVER_DATEIEN), muss anleitung/erzeuge_it_handbuch.py mitgeändert werden – oder eine
Commit-Zeile „IT-Handbuch: unverändert, weil …“ begründet es. Werte wie Ports und Befehle liest das Handbuch selbst
aus dem Programm; die Pflicht gilt für Abläufe, Voraussetzungen und Hinweise, die nur im Text stehen.

Aufruf: python tests/pruefe_anleitung_geaendert.py BASIS   (z. B. origin/main; braucht die volle Git-Historie)
"""
import re
import subprocess
import sys

BEGRUENDUNG = re.compile(r"^Anleitung:\s*unverändert\b.*\S", re.MULTILINE | re.IGNORECASE)
BEGRUENDUNG_IT = re.compile(r"^IT-Handbuch:\s*unverändert\b.*\S", re.MULTILINE | re.IGNORECASE)
IT_HANDBUCH = "anleitung/erzeuge_it_handbuch.py"
SERVER_DATEIEN = re.compile(r"^programm/rohrlaser/(server_\w+|pg_lokal|db_verbindung|update|update_quellen)\.py$")


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def it_handbuch(geaendert, nachrichten):
    """0 = in Ordnung, 1 = Server geändert, IT-Handbuch nicht und ohne Begründung."""
    server = [d for d in geaendert if SERVER_DATEIEN.match(d)]
    if not server or IT_HANDBUCH in geaendert:
        return 0
    grund = BEGRUENDUNG_IT.search(nachrichten)
    if grund:
        print(f"OK: Server geändert, IT-Handbuch bewusst nicht – {grund.group(0).strip()}")
        return 0
    print("FEHLER: Server-Teile wurden geändert, das IT-Handbuch (" + IT_HANDBUCH + ") nicht:\n  "
          + "\n  ".join(server)
          + "\n\nBitte das IT-Handbuch anpassen oder in einer Commit-Nachricht eine Zeile\n"
            "  IT-Handbuch: unverändert, weil …\nschreiben.")
    return 1


def main():
    basis = sys.argv[1] if len(sys.argv) > 1 else "origin/main"
    geaendert = git("diff", "--name-only", f"{basis}...HEAD").split()
    if it_handbuch(geaendert, git("log", "--format=%B", f"{basis}..HEAD")):
        return 1
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
