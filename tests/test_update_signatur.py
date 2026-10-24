"""Signierte Dateiliste (Audit 24.10.2026, H3/H4): Update.json.sig über die exakten Bytes, Prüfung im Client vor jeder
Verwendung, Signieren im Build (update_paket.signieren), Update-Schlüssel im Lizenz-Werkzeug, Änderungstext statt
Commit. Jeder Lauf erzeugt eigene Testschlüssel; der echte Schlüssel kommt in keinem Test vor.

Aufruf: python tests/test_update_signatur.py
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL / "programm"))
sys.path.insert(0, str(WURZEL / "werkzeuge"))
from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

import lizenz_werkzeug as wz  # noqa: E402
import update_paket  # noqa: E402
from rohrlaser import lizenz, update  # noqa: E402


def ok(text):
    print("OK    ", text)


def fehler_erwartet(f, *a, text=None, **k):
    try:
        f(*a, **k)
    except update.UpdateFehler as e:
        assert text is None or text in str(e), e
        return
    raise AssertionError(f"UpdateFehler erwartet: {f.__name__}")


def roh(privat):
    return base64.b64encode(privat.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                                 serialization.NoEncryption())).decode("ascii")


tmp = Path(tempfile.mkdtemp(prefix="upd_sig_"))
PRIVAT, FREMD = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
SCHL = {"U1": lizenz.oeffentlich_text(PRIVAT)}

# --- 1. Eingebaut: noch kein Schlüssel (PR-A), daher noch keine Pflicht -------------------------------------------
EINGEBAUT = update.update_schluessel()
assert EINGEBAUT and all(k.startswith("U") for k in EINGEBAUT), EINGEBAUT
assert all(len(base64.b64decode(t, validate=True)) == 32 for t in EINGEBAUT.values())
assert not set(EINGEBAUT.values()) & set(lizenz.standard_schluessel().values())
ok("Signaturpflicht an: öffentlicher Update-Schlüssel eingebaut, nur U-Schlüssel")

# --- 2. Signieren / Prüfen ------------------------------------------------------------------------------------------
daten = json.dumps({"format": 1, "stand": 5}).encode()
sig = update.signatur_erstellen(daten, PRIVAT, "U1")
assert sig["algorithmus"] == "ed25519" and sig["schluessel_id"] == "U1"
update.signatur_pruefen(daten, sig, SCHL)
update.signatur_pruefen(daten, json.dumps(sig).encode(), SCHL)
ok("gültige Signatur (dict und Bytes) akzeptiert")
fehler_erwartet(update.signatur_pruefen, daten + b" ", sig, SCHL, text="nicht gültig signiert")
ok("ein angehängtes Leerzeichen bricht die Signatur (exakte Bytes)")
fehler_erwartet(update.signatur_pruefen, daten, update.signatur_erstellen(daten, FREMD, "U1"), SCHL)
ok("fremder Schlüssel abgelehnt")
fehler_erwartet(update.signatur_pruefen, daten, dict(sig, schluessel_id="U9"), SCHL, text="unbekannter Schlüssel")
fehler_erwartet(update.signatur_pruefen, daten, dict(sig, algorithmus="rsa"), SCHL)
fehler_erwartet(update.signatur_pruefen, daten, dict(sig, format=2), SCHL)
fehler_erwartet(update.signatur_pruefen, daten, dict(sig, signatur="kein base64!"), SCHL)
fehler_erwartet(update.signatur_pruefen, daten, b"{kaputt", SCHL)
fehler_erwartet(update.signatur_pruefen, daten, sig, {})
ok("unbekannte ID, Verfahren, Format, kaputtes Base64/JSON, keine Schlüssel abgelehnt")
fehler_erwartet(update.signatur_pruefen, daten, update.signatur_erstellen(daten, PRIVAT, "K1"),
                {"K1": lizenz.oeffentlich_text(FREMD), **SCHL})
ok("Lizenzschlüssel-ID gilt nicht als Update-Schlüssel")

# --- 3. online_liste mit Ordnerquelle -------------------------------------------------------------------------------
quelle = tmp / "kanal"
quelle.mkdir()
(quelle / "a.txt").write_text("Hallo", encoding="utf-8")
update.erstellen(quelle, quelle, stand=7)
liste_bytes = (quelle / update.DATEILISTE).read_bytes()
assert b"commit" not in liste_bytes
ok("Dateiliste ohne Commit (H4)")
assert update.online_liste(str(quelle / update.DATEILISTE), schluessel={})["stand"] == 7
ok("ohne eingebaute Schlüssel: unsignierte Liste wie bisher")
fehler_erwartet(update.online_liste, str(quelle / update.DATEILISTE), schluessel=SCHL)
ok("mit Schlüsseln: fehlende Update.json.sig abgelehnt")
(quelle / update.SIGNATUR).write_text(json.dumps(update.signatur_erstellen(liste_bytes, PRIVAT, "U1")))
assert update.online_liste(str(quelle / update.DATEILISTE), schluessel=SCHL)["stand"] == 7
ok("mit Schlüsseln: signierte Liste akzeptiert")
gefaelscht = json.loads(liste_bytes)
gefaelscht["stand"] = 8
(quelle / update.DATEILISTE).write_text(json.dumps(gefaelscht), encoding="utf-8")
fehler_erwartet(update.online_liste, str(quelle / update.DATEILISTE), schluessel=SCHL, text="nicht gültig signiert")
ok("veränderte Liste (Stand hochgesetzt) abgelehnt")
(quelle / update.DATEILISTE).write_bytes(liste_bytes)

# --- 4. update_paket.signieren --------------------------------------------------------------------------------------
(quelle / update.SIGNATUR).unlink()
eingebaut = update.update_schluessel
try:
    update.update_schluessel = lambda: {}
    assert update_paket.signieren(quelle, {}) is None and not (quelle / update.SIGNATUR).exists()
    ok("Build ohne Secret und ohne Pflicht: Warnung, keine Signatur")
    assert update_paket.signieren(quelle, {"UPDATE_SIGNATUR": roh(PRIVAT)}) == "U1"
    update.signatur_pruefen(liste_bytes, (quelle / update.SIGNATUR).read_bytes(), SCHL)
    ok("Build mit Secret signiert schon vor der Pflicht")
    update.update_schluessel = lambda: SCHL
    for umgebung, text in (({}, "fehlt"), ({"UPDATE_SIGNATUR": roh(FREMD)}, "passt nicht"),
                           ({"UPDATE_SIGNATUR": "xx"}, "kein gültiger")):
        try:
            update_paket.signieren(quelle, umgebung)
        except SystemExit as e:
            assert text in str(e), e
        else:
            raise AssertionError(f"Abbruch erwartet: {text}")
    ok("Pflicht: fehlendes, fremdes oder kaputtes Secret bricht den Build ab")
    assert update_paket.signieren(quelle, {"UPDATE_SIGNATUR": roh(PRIVAT), "UPDATE_SIGNATUR_ID": "U1"}) == "U1"
    assert update.online_liste(str(quelle / update.DATEILISTE), schluessel=SCHL)["stand"] == 7
    ok("Pflicht: richtiges Secret signiert, Client nimmt die Liste an")
finally:
    update.update_schluessel = eingebaut

fehler_erwartet(update.online_liste, str(quelle / update.DATEILISTE), text="nicht gültig signiert")
ok("eingebauter Schlüssel: mit Testschlüssel signierte Liste abgelehnt")
# --- 5. Änderungstext statt Commit ----------------------------------------------------------------------------------
n = [("9.9.9", "Kurz [[updates]] mit <b>Fett</b>", "Lang (Kapitel [[updates]]), mit <i>mehr</i>"), ("9.9.8", "Alt")]
assert update_paket.letzte_aenderung("9.9.9", n) == "Lang, mit mehr", update_paket.letzte_aenderung("9.9.9", n)
assert update_paket.letzte_aenderung("9.9.8", n) == "Alt" and update_paket.letzte_aenderung("1.0", n) == ""
assert update_paket.letzte_aenderung() is not None
ok("Änderungstext aus den Neuerungen ohne Verweise und Auszeichnung")

# --- 6. Lizenz-Werkzeug: Update-Schlüssel ---------------------------------------------------------------------------
ordner = tmp / "lizenz"
ordner.mkdir()
oeff, geheim = wz.update_schluessel_erzeugen(ordner, "U1", b"testpasswort")
assert (ordner / "privat_U1.pem").exists() and b"ENCRYPTED" in (ordner / "privat_U1.pem").read_bytes()
assert geheim not in "".join(p.read_text(errors="ignore") for p in ordner.iterdir())
ok("U1 erzeugt, privat verschlüsselt, Secret-Wert nirgends gespeichert")
privat = Ed25519PrivateKey.from_private_bytes(base64.b64decode(geheim))
assert lizenz.oeffentlich_text(privat) == oeff
assert wz.update_secret(ordner, "U1", b"testpasswort") == (oeff, geheim)
update.update_schluessel = lambda: {"U1": oeff}
try:
    assert update_paket.signieren(quelle, {"UPDATE_SIGNATUR": geheim}) == "U1"
finally:
    update.update_schluessel = eingebaut
update.signatur_pruefen(liste_bytes, (quelle / update.SIGNATUR).read_bytes(), {"U1": oeff})
ok("Secret-Wert passt zum öffentlichen Schlüssel und signiert im Build")
try:
    wz.update_schluessel_erzeugen(ordner, "K7", b"testpasswort")
except SystemExit:
    pass
else:
    raise AssertionError("K-ID als Update-Schlüssel erwartet abgelehnt")
try:
    wz.aktueller_schluessel(ordner)
except SystemExit:
    ok("Update-Schlüssel zählt nicht als Lizenzschlüssel")
else:
    raise AssertionError("privat_U1.pem darf nicht als Lizenzschlüssel gelten")
umg = dict(os.environ, ROHRLASER_LIZENZ_ORDNER=str(ordner), ROHRLASER_LIZENZ_PASSWORT="testpasswort")
r = subprocess.run([sys.executable, str(WURZEL / "werkzeuge" / "lizenz_werkzeug.py"), "update-secret"],
                   capture_output=True, text=True, env=umg, encoding="utf-8")
assert r.returncode == 0 and geheim in r.stdout and oeff in r.stdout, r.stdout + r.stderr
ok("Befehl update-secret gibt beide Werte aus")

print("Alle Signatur-Prüfungen bestanden.")
