"""Release-Lieferkette (Absicherungsplan Phase 6, R3): Programmordner vor dem Veröffentlichen prüfen und eine
Release-Zusammenfassung schreiben (Build, GitHub Actions).

Aufruf:
  python programm/release_pruefen.py pruefen dist/Rohrlaser-Angebotskalkulation
  python programm/release_pruefen.py zusammenfassung --liste update_dateien/Update.json --kanal produktiv
         --commit SHA --lauf 123 --ausgabe Release-Zusammenfassung [--datei Setup.exe …] [--markdown DATEI]

pruefen         bricht ab (Rückgabe 1), wenn etwas im Programmordner liegt, das nicht zur Kundenverteilung gehört:
                Schlüssel und Zertifikate mit privatem Teil, Lizenzen, Datenbanken, Logs, Daten/Angebote/Update-Ordner,
                Tests, das Lizenz-Werkzeug, eigener Quelltext (.py nur in der Positivliste PY_ERLAUBT) oder der Wert
                eines Secrets (Umgebungsvariablen in SECRETS, auch als rohe Bytes).
zusammenfassung schreibt <ausgabe>.md und <ausgabe>.json: Version, Stand, Kanal, Commit, Lauf, Datum, Dateien je
                Endung, Prüfsumme und Größe jeder Datei (aus Update.json) und der zusätzlichen Dateien (Setup, ZIP).
                Die Zusammenfassung liegt nur im privaten Release, nie im öffentlichen Update-Repository.
"""
import argparse
import base64
import binascii
import datetime
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rohrlaser import update  # noqa: E402

# Endungen und Namen, die nie ausgeliefert werden (Vergleich ohne Groß-/Kleinschreibung)
ENDUNG_VERBOTEN = {".pem", ".key", ".pfx", ".p12", ".lizenz", ".db", ".sqlite", ".sqlite3", ".db-journal",
                   ".db-wal", ".log", ".env", ".spec"}
NAME_VERBOTEN = {"portabel.ini", "update.json.sig", "sperrliste.json", "lizenz-werkzeug.exe", ".git", ".github",
                 "tests", "daten", "angebote", update.ARBEITSORDNER.casefold()}
# Python-Quelltext nur von Fremdbibliotheken, die ihn zur Laufzeit brauchen (OCP-Typangaben); eigener Code steckt
# als Bytecode in der .exe. Ein neuer Eintrag hier ist eine bewusste Entscheidung.
PY_ERLAUBT = ("STEP-Import/_internal/OCP/",)
# Umgebungsvariablen mit geheimen Werten: tauchen sie (oder ihre Base64-Bytes) in einer Datei auf, bricht der Build ab
SECRETS = ("UPDATE_SIGNATUR", "SIGNATUR_PFX_PASSWORT", "UPDATES_TOKEN", "GH_TOKEN")
# ein echter privater Schlüssel im PEM-Format (nur der Kopf allein steht auch in OpenSSL-Bibliotheken)
_PEM = re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----\s*[A-Za-z0-9+/=]{40}")
STUECK = 4 << 20


def _muster(umgebung):
    """Bytefolgen der gesetzten Secrets: Text und, falls Base64, die rohen Bytes (mindestens 16 Byte)."""
    muster = []
    for name in SECRETS:
        wert = (umgebung.get(name) or "").strip()
        if len(wert) < 8:
            continue
        muster.append((name, wert.encode()))
        try:
            roh = base64.b64decode(wert, validate=True)
            if len(roh) >= 16:
                muster.append((name + " (Bytes)", roh))
        except (binascii.Error, ValueError):
            pass
    return muster


def _enthaelt(pfad, muster):
    """Namen der Muster (und "privater Schlüssel"), die in der Datei vorkommen; liest in Stücken mit Überlappung."""
    treffer = set()
    rand = max([len(m) for _, m in muster] + [200])
    rest = b""
    with open(pfad, "rb") as f:
        for teil in iter(lambda: f.read(STUECK), b""):
            block = rest + teil
            if _PEM.search(block):
                treffer.add("privater Schlüssel (PEM)")
            for name, m in muster:
                if m in block:
                    treffer.add(name)
            rest = block[-rand:]
    return treffer


def pruefen(ordner, umgebung=None):
    """Liste der Befunde (leer = in Ordnung) für den Programmordner."""
    ordner = Path(ordner)
    umgebung = os.environ if umgebung is None else umgebung
    if not ordner.is_dir():
        return [f"{ordner} ist kein Ordner"]
    muster = _muster(umgebung)
    befunde = []
    for p in sorted(ordner.rglob("*")):
        rel = p.relative_to(ordner).as_posix()
        teile = [t.casefold() for t in rel.split("/")]
        if p.is_symlink():
            befunde.append(f"{rel}: Verknüpfung (Symlink) im Programmordner")
            continue
        if any(t in NAME_VERBOTEN for t in teile):
            befunde.append(f"{rel}: gehört nicht in die Kundenverteilung")
            continue
        if not p.is_file():
            continue
        name = teile[-1]
        if any(name.endswith(e) for e in ENDUNG_VERBOTEN):
            befunde.append(f"{rel}: Dateityp wird nie ausgeliefert")
        elif name.endswith(".py") and not rel.startswith(PY_ERLAUBT):
            befunde.append(f"{rel}: Python-Quelltext außerhalb der Positivliste")
        for t in sorted(_enthaelt(p, muster)):
            befunde.append(f"{rel}: enthält {t}")
    return befunde


def zusammenfassung(liste, kanal="", commit="", lauf="", dateien=(), datum=None):
    """Release-Zusammenfassung als dict aus der Dateiliste (Update.json) und zusätzlichen Dateien."""
    endungen = {}
    for rel, d in liste["dateien"].items():
        e = Path(rel).suffix.lower() or "(ohne)"
        n, g = endungen.get(e, (0, 0))
        endungen[e] = (n + 1, g + d["groesse"])
    extra = {Path(p).name: dict(sha256=update.pruefsumme(p), groesse=Path(p).stat().st_size) for p in dateien}
    return dict(programm=liste.get("programm"), version=liste.get("version"), stand=liste.get("stand"),
                kanal=kanal, commit=commit, lauf=str(lauf),
                erstellt=datum or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                anzahl=len(liste["dateien"]), groesse=sum(d["groesse"] for d in liste["dateien"].values()),
                pakete=len(liste.get("pakete") or {}),
                endungen={e: dict(anzahl=n, groesse=g) for e, (n, g) in sorted(endungen.items())},
                zusatz=extra,
                dateien={rel: dict(sha256=d["sha256"], groesse=d["groesse"]) for rel, d in liste["dateien"].items()})


def als_markdown(z):
    mb = 1 << 20
    zeilen = [f"## Release-Zusammenfassung {z['version']} (Stand {z['stand']})", "",
              "| Angabe | Wert |", "|---|---|",
              f"| Kanal | {z['kanal'] or '–'} |", f"| Commit | `{z['commit'] or '–'}` |",
              f"| Actions-Lauf | {z['lauf'] or '–'} |", f"| Erstellt | {z['erstellt']} |",
              f"| Dateien | {z['anzahl']} ({z['groesse'] / mb:.1f} MB) in {z['pakete']} Paketen |", ""]
    if z["zusatz"]:
        zeilen += ["| Datei | SHA-256 | Größe |", "|---|---|---|"]
        zeilen += [f"| {n} | `{d['sha256']}` | {d['groesse'] / mb:.1f} MB |" for n, d in z["zusatz"].items()]
        zeilen.append("")
    zeilen += ["| Endung | Anzahl | Größe |", "|---|---|---|"]
    zeilen += [f"| {e} | {d['anzahl']} | {d['groesse'] / mb:.1f} MB |" for e, d in z["endungen"].items()]
    zeilen += ["", "Prüfsummen aller Dateien: Release-Zusammenfassung.json"]
    return "\n".join(zeilen) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    unter = ap.add_subparsers(dest="befehl", required=True)
    p = unter.add_parser("pruefen")
    p.add_argument("ordner")
    z = unter.add_parser("zusammenfassung")
    z.add_argument("--liste", required=True)
    z.add_argument("--kanal", default="")
    z.add_argument("--commit", default="")
    z.add_argument("--lauf", default="")
    z.add_argument("--datei", action="append", default=[])
    z.add_argument("--ausgabe", required=True)
    z.add_argument("--markdown")
    a = ap.parse_args(argv)
    if a.befehl == "pruefen":
        befunde = pruefen(a.ordner)
        for b in befunde:
            print(f"::error::{b}")
        print(f"{a.ordner}: {'in Ordnung' if not befunde else f'{len(befunde)} Befunde, Build abgebrochen'}")
        return 1 if befunde else 0
    liste = json.loads(Path(a.liste).read_text(encoding="utf-8"))
    daten = zusammenfassung(liste, a.kanal, a.commit, a.lauf, a.datei)
    Path(a.ausgabe + ".json").write_text(json.dumps(daten, indent=1, ensure_ascii=False), encoding="utf-8")
    text = als_markdown(daten)
    Path(a.ausgabe + ".md").write_text(text, encoding="utf-8")
    if a.markdown:
        with open(a.markdown, "a", encoding="utf-8") as f:
            f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
