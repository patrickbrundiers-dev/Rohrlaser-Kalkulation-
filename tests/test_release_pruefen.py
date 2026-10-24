"""Release-Lieferkette (Absicherungsplan Phase 6, R3): Prüfung des Programmordners vor dem Veröffentlichen und
Release-Zusammenfassung (programm/release_pruefen.py).

Aufruf: python tests/test_release_pruefen.py
"""
import base64
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
import release_pruefen as rp  # noqa: E402
from rohrlaser import update  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp(prefix="release_pruefen_"))


def ordner(name, dateien):
    o = tmp / name
    for rel, inhalt in dateien.items():
        (o / rel).parent.mkdir(parents=True, exist_ok=True)
        (o / rel).write_bytes(inhalt)
    return o


sauber = {"Rohrlaser-Angebotskalkulation.exe": b"MZ" * 500,
          "_internal/libcrypto-3.dll": b"\0-----BEGIN PRIVATE KEY-----\0-----END PRIVATE KEY-----\0",
          "_internal/rp_profile.json": b"{}",
          "STEP-Import/_internal/OCP/AIS/__init__.py": b"# Typangaben",
          "Bedienungsanleitung.pdf": b"%PDF"}
gut = ordner("gut", sauber)
assert rp.pruefen(gut, {}) == [], rp.pruefen(gut, {})
ok("sauberer Programmordner (auch PEM-Kopf ohne Schlüssel in einer DLL) in Ordnung")

for rel in ("Daten/rohrlaser.db", "_internal/x.db", "angebote/A.pdf", "Portabel.ini", "_update/x", "tests/t.py",
            "privat.pem", "U1.KEY", "kunde.lizenz", "fehler.log", "signatur.pfx", "Lizenz-Werkzeug.exe",
            "_internal/rohrlaser/rechnen.py", "Update.json.sig", "Sperrliste.json"):
    o = ordner("schlecht_" + rel.replace("/", "_"), {**sauber, rel: b"x"})
    befunde = rp.pruefen(o, {})
    assert befunde and rel.split("/")[0] in befunde[0] or rel in befunde[0], (rel, befunde)
ok("Daten, Angebote, Portabel.ini, Update-Ordner, Tests, Schlüssel, Lizenzen, Logs, Quelltext, Werkzeug abgelehnt")

o = ordner("pem", {**sauber, "_internal/x.bin": b"-----BEGIN OPENSSH PRIVATE KEY-----\n" + b"A" * 70})
assert any("privater Schlüssel" in b for b in rp.pruefen(o, {}))
ok("echter privater Schlüssel (PEM mit Inhalt) in einer Datei gefunden")

geheim = os.urandom(32)
wert = base64.b64encode(geheim).decode()
o = ordner("secret_text", {**sauber, "_internal/a.json": b'{"x": "' + wert.encode() + b'"}'})
assert any("UPDATE_SIGNATUR" in b for b in rp.pruefen(o, {"UPDATE_SIGNATUR": wert}))
o = ordner("secret_roh", {**sauber, "_internal/a.dll": b"\0" * (rp.STUECK - 5) + geheim + b"\0" * 10})
assert any("UPDATE_SIGNATUR (Bytes)" in b for b in rp.pruefen(o, {"UPDATE_SIGNATUR": wert}))
assert rp.pruefen(gut, {"UPDATE_SIGNATUR": wert, "SIGNATUR_PFX_PASSWORT": "kurz"}) == []
ok("Secret-Wert als Text und als rohe Bytes (auch über eine Stückgrenze) gefunden")

if hasattr(os, "symlink"):
    o = ordner("link", sauber)
    try:
        os.symlink(tmp, o / "raus")
        assert any("Symlink" in b for b in rp.pruefen(o, {}))
        ok("Verknüpfung (Symlink) im Programmordner abgelehnt")
    except OSError:
        pass

assert rp.main(["pruefen", str(gut)]) == 0
assert rp.main(["pruefen", str(tmp / "fehlt")]) == 1

# Zusammenfassung aus der Dateiliste des Builds
liste = update.erstellen(gut, tmp / "pakete", 42)
setup = tmp / "Setup.exe"
setup.write_bytes(b"setup")
md = tmp / "summary.md"
assert rp.main(["zusammenfassung", "--liste", str(tmp / "pakete" / update.DATEILISTE), "--kanal", "test",
                "--commit", "abc", "--lauf", "7", "--datei", str(setup), "--ausgabe", str(tmp / "RZ"),
                "--markdown", str(md)]) == 0
z = json.loads((tmp / "RZ.json").read_text(encoding="utf-8"))
assert z["stand"] == 42 and z["kanal"] == "test" and z["anzahl"] == len(liste["dateien"]) == 5
assert z["dateien"]["Bedienungsanleitung.pdf"]["sha256"] == update.pruefsumme(gut / "Bedienungsanleitung.pdf")
assert z["zusatz"]["Setup.exe"]["sha256"] == update.pruefsumme(setup)
assert z["endungen"][".py"]["anzahl"] == 1
text = md.read_text(encoding="utf-8")
assert "Release-Zusammenfassung" in text and "Setup.exe" in text and (tmp / "RZ.md").read_text(encoding="utf-8") == text
ok("Release-Zusammenfassung: Version, Stand, Kanal, Commit, Dateien je Endung, Prüfsummen")

# Workflow: Vorgabe nur lesen, Actions auf Commit-SHAs, kein PFX-Kennwort und kein Secret-Wert im Klartext
import re  # noqa: E402

wf = (Path(__file__).resolve().parent.parent / ".github" / "workflows" / "paket.yml").read_text(encoding="utf-8")
assert re.search(r"^permissions:\n  contents: read\b", wf, re.M), "Vorgabe-Rechte nicht nur lesen"
uses = re.findall(r"uses:\s*(\S+)(.*)", wf)
assert uses and all(re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u) and "# v" in rest for u, rest in uses), uses
assert "/p rohrlaser-signatur" not in wf and '"rohrlaser-signatur")' not in wf
assert "release_pruefen.py pruefen" in wf and "release_pruefen.py zusammenfassung" in wf
ok("Workflow: Rechte nur lesen als Vorgabe, alle Actions auf Commit-SHA gepinnt, Paketprüfung im Build")
print("Alle Release-Prüfungen bestanden.")
