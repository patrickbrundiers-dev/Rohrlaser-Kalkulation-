"""Prüfung der eigenen Programmdateien beim Start (echtheit.py, Patrick 30.10.2026 „c“) und die Ablage der exakten
Dateiliste samt Signatur beim Online-Update (update.Dateiliste, einspielen). Jeder Lauf erzeugt eigene Testschlüssel.

Aufruf: python tests/test_echtheit.py
"""
import base64
import json
import shutil
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from rohrlaser import echtheit, update  # noqa: E402

PRIVAT = Ed25519PrivateKey.generate()
SCHL = {"T1": base64.b64encode(PRIVAT.public_key().public_bytes(serialization.Encoding.Raw,
                                                                serialization.PublicFormat.Raw)).decode("ascii")}
FREMD = Ed25519PrivateKey.generate()


def ok(text):
    print("OK    ", text)


def programm(ordner, version=b"1"):
    """Kleiner Programmordner wie im Paket: eigene .pyd, Programm, Fremdbibliothek, STEP-Import."""
    ordner = Path(ordner)
    dateien = {"Rohrlaser-Angebotskalkulation.exe": b"exe" + version,
               "_internal/rohrlaser/lizenz.cp312-win_amd64.pyd": b"lizenz" + version,
               "_internal/rohrlaser/datenbank.cp312-win_amd64.pyd": b"datenbank" + version,
               "_internal/PySide6/Qt6Core.dll": b"qt" + version,
               "STEP-Import/STEP-Import.exe": b"step" + version,
               "STEP-Import/_internal/step_geometrie.cp312-win_amd64.pyd": b"geo" + version,
               "Bedienungsanleitung.pdf": b"pdf" + version}
    for rel, inhalt in dateien.items():
        (ordner / rel).parent.mkdir(parents=True, exist_ok=True)
        (ordner / rel).write_bytes(inhalt)
    return ordner


def release(prog, ziel, stand, privat=PRIVAT):
    update.erstellen(prog, ziel, stand, adresse="")
    daten = (Path(ziel) / update.DATEILISTE).read_bytes()
    (Path(ziel) / update.SIGNATUR).write_text(json.dumps(update.signatur_erstellen(daten, privat, "T1")),
                                              encoding="ascii")


tmp = Path(tempfile.mkdtemp(prefix="echtheit_"))
try:
    # ---------------------------------------------------------------- welche Dateien zählen
    for rel, soll in (("Rohrlaser-Angebotskalkulation.exe", True), ("STEP-Import/STEP-Import.exe", True),
                      ("_internal/rohrlaser/lizenz.cp312-win_amd64.pyd", True),
                      ("STEP-Import/_internal/rohrlaser/anbau.cp312-win_amd64.pyd", True),
                      ("STEP-Import/_internal/step_geometrie.cp312-win_amd64.pyd", True),
                      ("_internal/PySide6/Qt6Core.dll", False), ("_internal/numpy/core/_multiarray.pyd", False),
                      ("Bedienungsanleitung.pdf", False), ("_internal/rohrlaser/Lizenzbedingungen.txt", False)):
        assert echtheit.eigen(rel) is soll, rel
    ok("eigene Dateien: übersetzte Module rohrlaser/step_* und die beiden Programme, sonst nichts")

    # ---------------------------------------------------------------- unverändert / verändert
    prog = programm(tmp / "prog")
    assert echtheit.pruefen(prog, SCHL) is None
    ok("ohne Dateiliste (Entwicklung): nicht prüfbar (None)")
    release(prog, tmp / "rel", 5)
    for name in (update.DATEILISTE, update.SIGNATUR):
        shutil.copyfile(tmp / "rel" / name, prog / name)
    assert echtheit.pruefen(prog, SCHL) == ""
    ok("frisch installiert mit signierter Dateiliste: unverändert")

    lz = prog / "_internal/rohrlaser/lizenz.cp312-win_amd64.pyd"
    lz.write_bytes(b"ausgetauscht")
    assert echtheit.pruefen(prog, SCHL) == "lizenz geändert"
    ok("ausgetauschte Lizenzprüfung erkannt")
    lz.unlink()
    assert echtheit.pruefen(prog, SCHL) == "lizenz fehlt"
    ok("fehlendes eigenes Modul erkannt")
    lz.write_bytes(b"lizenz1")
    (prog / "_internal/PySide6/Qt6Core.dll").write_bytes(b"andere Qt")
    (prog / "Bedienungsanleitung.pdf").write_bytes(b"andere Anleitung")
    assert echtheit.pruefen(prog, SCHL) == ""
    ok("Fremdbibliotheken und Anleitung zählen nicht (schneller Start)")
    (prog / "_internal/rohrlaser/lizenz.py").write_text("x = 1", encoding="utf-8")
    assert echtheit.pruefen(prog, SCHL) == "lizenz.py fremd"
    (prog / "_internal/rohrlaser/lizenz.py").unlink()
    ok("zusätzlicher Quelltext neben den übersetzten Modulen erkannt")
    (prog / "STEP-Import/STEP-Import.exe").write_bytes(b"x")
    (prog / "Rohrlaser-Angebotskalkulation.exe").write_bytes(b"x")
    assert echtheit.pruefen(prog, SCHL) == "Rohrlaser-Angebotskalkulation geändert, STEP-Import geändert"
    (prog / "STEP-Import/STEP-Import.exe").write_bytes(b"step1")
    (prog / "Rohrlaser-Angebotskalkulation.exe").write_bytes(b"exe1")
    ok("geänderte Programme erkannt")

    # ---------------------------------------------------------------- Dateiliste selbst
    liste = json.loads((prog / update.DATEILISTE).read_text(encoding="utf-8"))
    lz.write_bytes(b"ausgetauscht")
    liste["dateien"]["_internal/rohrlaser/lizenz.cp312-win_amd64.pyd"]["sha256"] = update.pruefsumme(lz)
    (prog / update.DATEILISTE).write_text(json.dumps(liste, indent=1), encoding="utf-8")
    assert echtheit.pruefen(prog, SCHL) == "Dateiliste Update.json verändert"
    ok("Prüfsumme in der Dateiliste angepasst: Signatur passt nicht mehr")
    (prog / update.SIGNATUR).write_text(json.dumps(update.signatur_erstellen(
        (prog / update.DATEILISTE).read_bytes(), FREMD, "T1")), encoding="ascii")
    assert echtheit.pruefen(prog, SCHL) == "Dateiliste Update.json verändert"
    ok("mit fremdem Schlüssel neu signiert: abgelehnt")
    (prog / update.SIGNATUR).unlink()
    assert echtheit.pruefen(prog, SCHL) == ""
    ok("ältere Installation ohne Signatur: Prüfung gegen die unsignierte Liste (bekannte Grenze, Anleitung)")
    (prog / update.DATEILISTE).write_text("kaputt", encoding="utf-8")
    assert echtheit.pruefen(prog, SCHL) == "Dateiliste Update.json unlesbar"
    ok("unlesbare Dateiliste erkannt")

    # ---------------------------------------------------------------- Online-Update legt Liste + Signatur ab
    alt = programm(tmp / "alt", b"0")
    update.erstellen(alt, tmp / "rel_alt", 4, adresse="")
    shutil.copyfile(tmp / "rel_alt" / update.DATEILISTE, alt / update.DATEILISTE)     # alter Stand ohne Signatur
    neu = programm(tmp / "neu", b"2")
    release(neu, tmp / "rel2", 6)
    quelle = str(tmp / "rel2" / update.DATEILISTE)
    online = update.online_liste(quelle, schluessel=SCHL)
    assert isinstance(online, update.Dateiliste) and online.roh == (tmp / "rel2" / update.DATEILISTE).read_bytes() \
        and online.signatur == (tmp / "rel2" / update.SIGNATUR).read_bytes()
    ok("online_liste behält die exakten Bytes und die Signatur")
    update.aktualisieren(alt, quelle, alle=True, online=online)
    assert (alt / update.DATEILISTE).read_bytes() == online.roh
    assert (alt / update.SIGNATUR).read_bytes() == online.signatur
    assert echtheit.pruefen(alt, SCHL) == ""
    ok("nach dem Update: Dateiliste bytegleich, Signatur daneben, Prüfung ohne Befund")
    unsigniert = update.Dateiliste(online)          # z. B. Update ohne Schlüssel: alte Signatur muss weg
    (tmp / "leer").mkdir()
    update.einspielen(alt, unsigniert, dict(neu=[], weg=[]), tmp / "leer")
    assert not (alt / update.SIGNATUR).exists(), list(alt.iterdir())
    assert echtheit.pruefen(alt, SCHL) == "", echtheit.pruefen(alt, SCHL)
    ok("Update ohne Signatur: keine veraltete Update.json.sig bleibt liegen")
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("Alle Prüfungen bestanden.")
