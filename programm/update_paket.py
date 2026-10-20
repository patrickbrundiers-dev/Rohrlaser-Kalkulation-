"""Dateiliste (Update.json) und Update-Pakete für das Online-Update erzeugen (Build, GitHub Actions).

Aufruf:
  python programm/update_paket.py --programm dist/Rohrlaser-Angebotskalkulation --ziel update_dateien
         --stand 57 [--commit SHA] [--adresse URL] [--in-programm]
--adresse      Adresse der Pakete (Release update-dateien im Repository Rohrlaser-Updates), steht in der Dateiliste
--in-programm  Dateiliste zusätzlich in den Programmordner legen (kommt so ins ZIP: installierter Stand)
--aenderung    Text "Was ist neu"; ohne Angabe der Titel des letzten Pull Requests bzw. Commits
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rohrlaser import update  # noqa: E402


def letzte_aenderung():
    """Titel des letzten Pull Requests (steht im Merge-Commit unter der ersten Zeile), sonst der Commit-Titel."""
    try:
        kopf, _, rest = subprocess.run(["git", "log", "-1", "--format=%s%n%b"], capture_output=True, encoding="utf-8",
                                       check=True).stdout.strip().partition("\n")
    except (OSError, subprocess.CalledProcessError):
        return ""
    if kopf.startswith("Merge pull request") and rest.strip():
        return rest.strip().splitlines()[0].strip()
    return kopf.strip()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--programm", required=True)
    ap.add_argument("--ziel", required=True)
    ap.add_argument("--stand", required=True, type=int)
    ap.add_argument("--commit", default="")
    ap.add_argument("--adresse", default=update.ADRESSE.rpartition("/")[0] + "/")   # Ordner der Dateiliste
    ap.add_argument("--aenderung")
    ap.add_argument("--in-programm", action="store_true")
    a = ap.parse_args(argv)
    aenderung = letzte_aenderung() if a.aenderung is None else a.aenderung
    liste = update.erstellen(a.programm, a.ziel, a.stand, a.commit, aenderung, a.adresse)
    if a.in_programm:
        shutil.copyfile(Path(a.ziel) / update.DATEILISTE, Path(a.programm) / update.DATEILISTE)
    groesse = sum(p["groesse"] for p in liste["pakete"].values())
    print(f"Stand {liste['stand']}: {len(liste['dateien'])} Dateien in {len(liste['pakete'])} Paketen, "
          f"{groesse / 1e6:.1f} MB; Änderung: {aenderung}")
    print(json.dumps({p: d["groesse"] for p, d in sorted(liste["pakete"].items(), key=lambda x: -x[1]["groesse"])[:5]}))


if __name__ == "__main__":
    main()
