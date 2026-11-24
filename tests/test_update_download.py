"""Online-Update im Firmennetz (Patrick 26.10.2026: Download bricht nach ein paar Prozent ab): Verbindungsabbruch
und vorzeitig beendete Verbindung werden neu versucht und an der Abbruchstelle fortgesetzt (HTTP Range), Server ohne
Range beginnt von vorn, Sperrseite eines Proxys (HTML statt ZIP) und HTTP 403 werden klar gemeldet, Geladenes bleibt
für den nächsten Versuch, fehlende Schreibrechte im Programmordner werden erkannt.

Aufruf: python tests/test_update_download.py
"""
import email.message
import hashlib
import io
import shutil
import sys
import tempfile
import urllib.error
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "programm"))
from rohrlaser import update  # noqa: E402

URL = "https://github.com/patrickbrundiers-dev/Rohrlaser-Updates/releases/download/update-dateien/"


def ok(text):
    print("OK    ", text)


class Antwort:
    """Gefälschte HTTP-Antwort: liefert daten ab Byte ab; nach abbruch_nach Bytes ConnectionResetError, mit
    kurz=True endet sie dort still (Content-Length größer als geliefert)."""

    def __init__(self, daten, ab=0, status=200, typ="application/octet-stream", abbruch_nach=None, kurz=False):
        self.status = status
        self.headers = email.message.Message()
        self.headers["Content-Type"] = typ
        self.headers["Content-Length"] = str(len(daten) - ab)
        if status == 206:
            self.headers["Content-Range"] = f"bytes {ab}-{len(daten) - 1}/{len(daten)}"
        rest = daten[ab:]
        self._daten = io.BytesIO(rest if abbruch_nach is None else rest[:abbruch_nach])
        self._abbruch = abbruch_nach is not None and not kurz

    def read(self, n=-1):
        teil = self._daten.read(n)
        if not teil and self._abbruch:
            raise ConnectionResetError(10054, "Eine vorhandene Verbindung wurde vom Remotehost geschlossen")
        return teil

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Server:
    """Ersetzt update._oeffnen. ablauf: je Aufruf eine Funktion (daten, ab) -> Antwort oder Ausnahme."""

    def __init__(self, daten, ablauf):
        self.daten, self.ablauf, self.aufrufe = daten, list(ablauf), []

    def __call__(self, quelle, timeout=30, ab=0):
        self.aufrufe.append(ab)
        schritt = self.ablauf.pop(0) if self.ablauf else (lambda d, a: Antwort(d, a, 206 if a else 200))
        erg = schritt(self.daten, ab)
        if isinstance(erg, BaseException):
            raise erg
        return erg


original = update._oeffnen
tmp = Path(tempfile.mkdtemp())
daten = bytes(range(256)) * 4000            # ~1 MB
ziel = tmp / "paket.zip"
geschlafen = []
schlafen = geschlafen.append
try:
    # 1) Abbruch nach 10 %, zweiter Versuch setzt mit Range fort
    update._oeffnen = s = Server(daten, [lambda d, a: Antwort(d, a, abbruch_nach=len(d) // 10)])
    gemeldet, meldungen = [], []
    update.holen(URL + "x.zip", ziel, gemeldet.append, grenze=len(daten), warten=(0, 0), melden=meldungen.append,
                 schlafen=schlafen)
    assert ziel.read_bytes() == daten and sum(gemeldet) == len(daten), sum(gemeldet)
    assert s.aufrufe == [0, len(daten) // 10], s.aufrufe
    assert meldungen and "neuer Versuch 2 von 3" in meldungen[0], meldungen
    ok("Verbindungsabbruch nach 10 %: neuer Versuch setzt an der Abbruchstelle fort, Fortschritt nicht doppelt")

    # 2) Verbindung endet still zu früh (urllib meldet das nicht) -> erkannt und fortgesetzt
    ziel.unlink()
    update._oeffnen = s = Server(daten, [lambda d, a: Antwort(d, a, abbruch_nach=5000, kurz=True)])
    update.holen(URL + "x.zip", ziel, grenze=len(daten), warten=(0,), schlafen=schlafen)
    assert ziel.read_bytes() == daten and s.aufrufe == [0, 5000], s.aufrufe
    ok("Vorzeitig beendete Verbindung erkannt (Content-Length) und fortgesetzt")

    # 3) Server kann kein Range (200 statt 206): von vorn, Datei richtig, Fortschritt nicht doppelt gezählt
    ziel.unlink()
    update._oeffnen = s = Server(daten, [lambda d, a: Antwort(d, a, abbruch_nach=7000),
                                         lambda d, a: Antwort(d, 0, 200)])
    gemeldet = []
    update.holen(URL + "x.zip", ziel, gemeldet.append, grenze=len(daten), warten=(0,), schlafen=schlafen)
    assert ziel.read_bytes() == daten and sum(gemeldet) == len(daten)
    ok("Server ohne Range: von vorn geladen, Datei und Fortschritt stimmen")

    # 4) Immer wieder Abbruch: nach allen Versuchen verständliche Meldung, Anfang bleibt für später
    ziel.unlink()
    update._oeffnen = Server(daten, [lambda d, a: Antwort(d, a, 206 if a else 200, abbruch_nach=1000)] * 3)
    try:
        update.holen(URL + "x.zip", ziel, grenze=len(daten), warten=(0, 0), schlafen=schlafen)
        raise AssertionError("Netzfehler erwartet")
    except update.Netzfehler as e:
        assert "3-mal unterbrochen" in str(e) and "Firmennetz" in str(e) and "Proxy:" in str(e), e
    assert ziel.stat().st_size == 3000, ziel.stat().st_size
    ok("Dauerhafte Abbrüche: Meldung nennt Firmennetz/Proxy, Geladenes bleibt erhalten")

    # 5) Sperrseite statt Datei, HTTP 403, Zertifikat: kein sinnloses Wiederholen, klare Ursache
    ziel.unlink()
    update._oeffnen = s = Server(daten, [lambda d, a: Antwort(b"<html>Blocked by policy</html>", typ="text/html")])
    try:
        update.holen(URL + "x.zip", ziel, warten=(0, 0), schlafen=schlafen)
        raise AssertionError("UpdateFehler erwartet")
    except update.UpdateFehler as e:
        assert "Webseite" in str(e) and "Sperrseite" in str(e), e
    assert len(s.aufrufe) == 1 and not ziel.exists()
    fehler403 = urllib.error.HTTPError(URL, 403, "Forbidden", None, None)
    update._oeffnen = s = Server(daten, [lambda d, a: fehler403])
    try:
        update.holen(URL + "x.zip", ziel, warten=(0, 0), schlafen=schlafen)
        raise AssertionError("UpdateFehler erwartet")
    except update.UpdateFehler as e:
        assert "403" in str(e) and "Proxy" in str(e) and not isinstance(e, update.Netzfehler), e
    assert len(s.aufrufe) == 1
    import ssl
    zert = urllib.error.URLError(ssl.SSLCertVerificationError(1, "certificate verify failed"))
    update._oeffnen = s = Server(daten, [lambda d, a: zert])
    try:
        update.holen(URL + "Update.json", warten=(0,), schlafen=schlafen)
        raise AssertionError("UpdateFehler erwartet")
    except update.UpdateFehler as e:
        assert "Zertifikat" in str(e), e
    assert len(s.aufrufe) == 1
    update._oeffnen = s = Server(daten, [lambda d, a: TimeoutError("timed out")])
    assert update.holen(URL + "Update.json", warten=(0,), schlafen=schlafen) == daten and len(s.aufrufe) == 2
    ok("Sperrseite (HTML), HTTP 403 und fremdes Zertifikat klar gemeldet, Zeitüberschreitung neu versucht")

    # 6) laden(): erster Klick scheitert, Download bleibt, zweiter Klick setzt fort; Prüfsummen bleiben Pflicht
    inhalt = b"programmdatei" * 50000
    sha = hashlib.sha256(inhalt).hexdigest()
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_STORED) as z:
        z.writestr(sha, inhalt)
    paket_daten = puffer.getvalue()
    paket = "d-" + "a" * 40 + ".zip"
    online = dict(format=1, stand=5, dateien={"a.dll": dict(sha256=sha, groesse=len(inhalt), paket=paket)},
                  pakete={paket: dict(groesse=len(paket_daten), sha256=hashlib.sha256(paket_daten).hexdigest())})
    prog = tmp / "prog"
    prog.mkdir()
    plan = update.planen(prog, online)
    update._oeffnen = Server(paket_daten, [lambda d, a: Antwort(d, a, 206 if a else 200, abbruch_nach=len(d) // 4)] * 2)
    try:
        update.laden(prog, URL + "Update.json", online, plan, warten=(0,), schlafen=schlafen)
        raise AssertionError("Netzfehler erwartet")
    except update.Netzfehler:
        pass
    update.verwerfen(prog, download_behalten=True)
    teil = (prog / update.ARBEITSORDNER / "pakete" / paket).stat().st_size
    assert teil == 2 * (len(paket_daten) // 4), teil
    update._oeffnen = s = Server(paket_daten, [])
    gemeldet = []
    neu = update.laden(prog, URL + "Update.json", online, plan, gemeldet.append, warten=(0,), schlafen=schlafen)
    assert (neu / sha).read_bytes() == inhalt and s.aufrufe == [teil] and sum(gemeldet) == len(paket_daten)
    update._oeffnen = s = Server(paket_daten, [])
    update.laden(prog, URL + "Update.json", online, plan, warten=(0,), schlafen=schlafen)
    assert s.aufrufe == []                      # schon entpackt und geprüft: nichts mehr zu laden
    update.verwerfen(prog)
    assert not (prog / update.ARBEITSORDNER / "neu").exists()
    # verändertes Paket (Proxy): einmal neu geladen, dann klare Meldung
    kaputt = paket_daten[:-10] + b"x" * 10
    update._oeffnen = s = Server(kaputt, [])
    try:
        update.laden(prog, URL + "Update.json", online, plan, warten=(0,), schlafen=schlafen)
        raise AssertionError("UpdateFehler erwartet")
    except update.UpdateFehler as e:
        assert "Prüfsumme des Pakets" in str(e) and "Proxy" in str(e), e
    assert s.aufrufe == [0, 0]
    ok("laden(): abgebrochener Download wird beim nächsten Versuch fortgesetzt, Entpacktes weiterverwendet, "
       "verändertes Paket erkannt")

    # 7) Kein Schreibrecht im Programmordner (z. B. portable Version in geschütztem Ordner)
    gesperrt = tmp / "gesperrt"
    gesperrt.mkdir()
    (gesperrt / update.ARBEITSORDNER).write_text("kein Ordner")     # mkdir scheitert wie ohne Schreibrecht
    try:
        update.laden(gesperrt, URL + "Update.json", online, update.planen(gesperrt, online))
        raise AssertionError("UpdateFehler erwartet")
    except update.UpdateFehler as e:
        assert "Schreibrechte" in str(e) and "portable" in str(e), e
    ok("Fehlendes Schreibrecht im Programmordner verständlich gemeldet")

    assert "//" not in update.systemproxy().replace("://", "") and update.systemproxy()
finally:
    update._oeffnen = original
    shutil.rmtree(tmp, ignore_errors=True)
print("OK: Online-Update im Firmennetz (Wiederholen, Fortsetzen, Sperrseite, Schreibrecht)")
