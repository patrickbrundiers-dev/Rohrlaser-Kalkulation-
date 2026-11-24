"""Dateiliste (Update.json), Signatur und Update-Pakete für das Online-Update von Rohrlaser Auslastung erzeugen
(Workflow Auslastung).

Aufruf:
  python programm/auslastung_update_paket.py --programm dist/Rohrlaser-Auslastung --ziel update_dateien --stand 12
         [--adresse URL] [--in-programm]
--adresse      Adresse der Pakete (Release auslastung-dateien im Repository Rohrlaser-Updates), steht in der Liste
--in-programm  Dateiliste und Signatur zusätzlich in den Programmordner legen (kommt so ins ZIP: installierter Stand)

Signatur: mit dem privaten Update-Schlüssel aus der Umgebungsvariable UPDATE_SIGNATUR (Base64 der 32 Byte, GitHub-
Secret, derselbe wie bei der Kalkulation; Schlüssel-ID aus UPDATE_SIGNATUR_ID, Vorgabe U1). Das Programm nimmt nur
signierte Dateilisten an: ohne Secret oder mit einem nicht passenden Secret bricht der Bau ab.
"""
import argparse
import base64
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rl_auslastung import NEU  # noqa: E402
from rl_auslastung import aktualisierung as A  # noqa: E402
from rohrlaser import update  # noqa: E402


def signieren(ziel, umgebung=None):
    """Update.json.sig zu ziel/Update.json schreiben und gleich mit den eingebauten Schlüsseln prüfen. Ergebnis:
    Schlüssel-ID."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    umgebung = os.environ if umgebung is None else umgebung
    geheim = (umgebung.get("UPDATE_SIGNATUR") or "").strip()
    if not geheim:
        raise SystemExit("Secret UPDATE_SIGNATUR fehlt, das Programm verlangt signierte Dateilisten: "
                         "Bau abgebrochen, nichts veröffentlicht.")
    sid = (umgebung.get("UPDATE_SIGNATUR_ID") or "U1").strip()
    try:
        privat = Ed25519PrivateKey.from_private_bytes(base64.b64decode(geheim, validate=True))
    except ValueError as e:
        raise SystemExit(f"UPDATE_SIGNATUR ist kein gültiger Ed25519-Schlüssel: {e}") from None
    daten = (Path(ziel) / update.DATEILISTE).read_bytes()
    sig = A.signieren(daten, privat, sid)
    (Path(ziel) / update.SIGNATUR).write_text(json.dumps(sig), encoding="ascii")
    try:
        A.signatur_pruefen(daten, sig)
    except update.UpdateFehler as e:
        raise SystemExit(f"UPDATE_SIGNATUR passt nicht zu update_schluessel.py: {e}") from None
    return sid


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--programm", required=True)
    ap.add_argument("--ziel", required=True)
    ap.add_argument("--stand", required=True, type=int)
    ap.add_argument("--adresse", default=A.ADRESSE.rpartition("/")[0] + "/")
    ap.add_argument("--in-programm", action="store_true")
    a = ap.parse_args(argv)
    liste = A.erstellen(a.programm, a.ziel, a.stand, NEU, a.adresse)
    sid = signieren(a.ziel)
    if a.in_programm:
        for name in (update.DATEILISTE, update.SIGNATUR):
            if (Path(a.ziel) / name).is_file():
                shutil.copyfile(Path(a.ziel) / name, Path(a.programm) / name)
    groesse = sum(p["groesse"] for p in liste["pakete"].values())
    print(f"{liste['programm']} {liste['version']} Stand {liste['stand']}: {len(liste['dateien'])} Dateien in "
          f"{len(liste['pakete'])} Paketen, {groesse / 1e6:.1f} MB; "
          f"signiert mit {sid}")


if __name__ == "__main__":
    main()
