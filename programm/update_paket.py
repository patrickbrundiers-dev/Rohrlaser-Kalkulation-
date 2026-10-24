"""Dateiliste (Update.json) und Update-Pakete für das Online-Update erzeugen (Build, GitHub Actions).

Aufruf:
  python programm/update_paket.py --programm dist/Rohrlaser-Angebotskalkulation --ziel update_dateien
         --stand 57 [--commit SHA] [--adresse URL] [--in-programm]
--adresse      Adresse der Pakete (Release update-dateien im Repository Rohrlaser-Updates), steht in der Dateiliste
--in-programm  Dateiliste zusätzlich in den Programmordner legen (kommt so ins ZIP: installierter Stand)
--aenderung    Text "Was ist neu"; ohne Angabe die Kurzfassung der aktuellen Version aus neuerungen.py (öffentlich:
               keine PR-Titel, kein Commit, Audit H4)

Signatur (Audit H3): Mit dem privaten Update-Schlüssel aus der Umgebungsvariable UPDATE_SIGNATUR (Base64 der 32 Byte,
GitHub-Secret; Schlüssel-ID aus UPDATE_SIGNATUR_ID, Vorgabe U1) entsteht Update.json.sig neben Update.json.
Steht in rohrlaser/update_schluessel.py ein öffentlicher Schlüssel, verlangt das Programm die Signatur: dann bricht
der Build ohne Secret oder mit einem nicht passenden Secret ab, statt eine unsignierte Liste zu veröffentlichen.
"""
import argparse
import base64
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rohrlaser import VERSION, update  # noqa: E402
from rohrlaser.neuerungen import NEUERUNGEN  # noqa: E402


def letzte_aenderung(version=VERSION, neuerungen=None):
    """Kurzfassung der Neuerungen dieser Version (ohne Verweise und Auszeichnung), sonst leer."""
    for eintrag in neuerungen or NEUERUNGEN:
        if eintrag[0] == version:
            text = re.sub(r"\s*\([^()]*\[\[[a-z0-9_]+\]\][^()]*\)", "", eintrag[2] if len(eintrag) > 2 else eintrag[1])
            text = re.sub(r"\s*\[\[[a-z0-9_]+\]\]", "", text)
            return re.sub(r"<[^>]+>", "", text).replace(" ,", ",").strip()
    return ""


def signieren(ziel, umgebung=None):
    """Update.json.sig zu ziel/Update.json schreiben (Schlüssel aus UPDATE_SIGNATUR). Ergebnis: Schlüssel-ID oder None
    (ohne Secret, nur erlaubt, solange das Programm keine Signatur verlangt). Prüft die Signatur gleich mit den
    eingebauten öffentlichen Schlüsseln."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    umgebung = os.environ if umgebung is None else umgebung
    pflicht = bool(update.update_schluessel())
    geheim = (umgebung.get("UPDATE_SIGNATUR") or "").strip()
    if not geheim:
        if pflicht:
            raise SystemExit("Secret UPDATE_SIGNATUR fehlt, das Programm verlangt signierte Dateilisten: "
                             "Build abgebrochen, nichts veröffentlicht.")
        print("::warning::Secret UPDATE_SIGNATUR fehlt: Dateiliste bleibt unsigniert (noch erlaubt)")
        return None
    sid = (umgebung.get("UPDATE_SIGNATUR_ID") or "U1").strip()
    try:
        privat = Ed25519PrivateKey.from_private_bytes(base64.b64decode(geheim, validate=True))
    except ValueError as e:
        raise SystemExit(f"UPDATE_SIGNATUR ist kein gültiger Ed25519-Schlüssel: {e}") from None
    daten = (Path(ziel) / update.DATEILISTE).read_bytes()
    sig = update.signatur_erstellen(daten, privat, sid)
    (Path(ziel) / update.SIGNATUR).write_text(json.dumps(sig), encoding="ascii")
    if pflicht:
        try:
            update.signatur_pruefen(daten, sig, update.update_schluessel())
        except update.UpdateFehler as e:
            raise SystemExit(f"UPDATE_SIGNATUR passt nicht zu update_schluessel.py: {e}") from None
    return sid


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--programm", required=True)
    ap.add_argument("--ziel", required=True)
    ap.add_argument("--stand", required=True, type=int)
    ap.add_argument("--commit", default="")       # nicht mehr öffentlich (Audit H4); nur noch angenommen
    ap.add_argument("--adresse", default=update.ADRESSE.rpartition("/")[0] + "/")   # Ordner der Dateiliste
    ap.add_argument("--aenderung")
    ap.add_argument("--in-programm", action="store_true")
    a = ap.parse_args(argv)
    aenderung = letzte_aenderung() if a.aenderung is None else a.aenderung
    liste = update.erstellen(a.programm, a.ziel, a.stand, "", aenderung, a.adresse)
    sid = signieren(a.ziel)
    if a.in_programm:
        shutil.copyfile(Path(a.ziel) / update.DATEILISTE, Path(a.programm) / update.DATEILISTE)
    groesse = sum(p["groesse"] for p in liste["pakete"].values())
    print(f"Stand {liste['stand']}: {len(liste['dateien'])} Dateien in {len(liste['pakete'])} Paketen, "
          f"{groesse / 1e6:.1f} MB; Änderung: {aenderung}; "
          + (f"signiert mit {sid}" if sid else "unsigniert"))
    print(json.dumps({p: d["groesse"] for p, d in sorted(liste["pakete"].items(), key=lambda x: -x[1]["groesse"])[:5]}))


if __name__ == "__main__":
    main()
