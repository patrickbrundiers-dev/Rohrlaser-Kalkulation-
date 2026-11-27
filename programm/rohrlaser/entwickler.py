"""Entwickler-Zugang: ein fester Login, mit dem der Entwickler (Patrick) auf jeder Installation vollen Zugriff hat
(Patrick 27.11.2026, Entscheidung „Festes Passwort im Programm“).

Das Passwort ist überall gleich, steht aber NICHT im Klartext im Programm. Hinterlegt ist nur ein Prüfwert
(öffentlicher Ed25519-Schlüssel), der aus dem Passwort mit scrypt und festem Salz abgeleitet wird. Aus dem Prüfwert
lässt sich das Passwort nicht zurückrechnen; wer das Programm auseinandernimmt, findet also kein Geheimnis. Beim Login
leitet das Programm aus dem eingegebenen Passwort denselben öffentlichen Schlüssel ab und vergleicht ihn mit dem
hinterlegten Prüfwert.

Setzen (einmal, nie in Chat oder Repo): im Lizenz-Werkzeug `entwickler-schluessel`. Es fragt das Passwort und gibt
die Zeile für VERIFIZIERER aus. Solange VERIFIZIERER leer ist, ist der Entwickler-Zugang AUS (kein Hintertürchen).

Erkannt wird das Passwort an zwei Stellen: in der Schlossleiste der Einstellungen („Als Admin freischalten“,
fenster.Einstellungen.oeffnen) und bei der Hauptadmin-Anmeldung beim Start (lizenz.Stelle.hauptadmin_anmelden).
Danach gilt die Sitzung als voll freigeschaltet: admin_schutz.ist_admin/ist_haupt sind wahr und ein Lesemodus wird
aufgehoben. Jede Nutzung steht im Protokoll.

Import-arm (nur stdlib und cryptography), damit es früh im Start und ohne Qt nutzbar ist.
"""
import base64
import hmac
import logging

# Festes Salz für die Ableitung (nur dieses Salz macht das Passwort überall gleich prüfbar). Kein Geheimnis.
SALZ = "ca572e821c1f0ca4dec5b97bb0506ed0"
KDF = dict(n=2 ** 15, r=8, p=1)         # scrypt, etwa 0,3 s je Login (selten, darf langsam sein)

# Öffentlicher Prüfwert des Entwickler-Passworts (Base64, Ed25519). Leer = Entwickler-Zugang ausgeschaltet.
# Setzen mit `entwickler-schluessel` im Lizenz-Werkzeug; nur der öffentliche Schlüssel, nie das Passwort.
VERIFIZIERER = ""

_frei = False       # in dieser Sitzung mit dem Entwickler-Passwort freigeschaltet


def _pub(passwort):
    """Öffentlicher Ed25519-Schlüssel (Text) aus dem Passwort, über scrypt mit festem Salz."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    seed = Scrypt(salt=bytes.fromhex(SALZ), length=32, n=KDF["n"], r=KDF["r"], p=KDF["p"]).derive(
        str(passwort).encode("utf-8"))
    priv = Ed25519PrivateKey.from_private_bytes(seed)
    from . import lizenz as L
    return L.oeffentlich_text(priv)


def verifizierer(passwort):
    """Prüfwert für VERIFIZIERER (Lizenz-Werkzeug): öffentlicher Schlüssel zum Passwort."""
    return _pub(passwort)


def aktiv():
    """True, wenn ein Entwickler-Zugang hinterlegt ist."""
    return bool(VERIFIZIERER)


def passt(passwort):
    """True, wenn passwort das hinterlegte Entwickler-Passwort ist. Ohne hinterlegten Prüfwert immer False."""
    if not VERIFIZIERER or not passwort:
        return False
    try:
        return hmac.compare_digest(_pub(passwort), VERIFIZIERER)
    except Exception:       # noqa: BLE001 - jeder Fehler gilt als „passt nicht“
        return False


def frei():
    """In dieser Sitzung mit dem Entwickler-Passwort freigeschaltet."""
    return _frei


def setzen(an=True):
    global _frei
    _frei = bool(an)


def anmelden(passwort, db=None, wo=""):
    """Passwort prüfen; bei Treffer die Sitzung freischalten, einen Lesemodus aufheben und ins Protokoll schreiben.
    Ergebnis: True = Entwickler-Passwort erkannt."""
    if not passt(passwort):
        return False
    setzen(True)
    if db is not None:
        try:
            if getattr(db, "nur_lesen", ""):
                db.lesemodus("")
        except Exception:       # noqa: BLE001 - Lesemodus-Aufheben darf den Login nicht verhindern
            logging.getLogger(__name__).exception("Entwickler-Zugang: Lesemodus ließ sich nicht aufheben")
    logging.getLogger(__name__).warning("Entwickler-Zugang genutzt%s", f" ({wo})" if wo else "")
    try:
        from . import protokoll
        protokoll.warnung("Entwickler-Zugang genutzt" + (f" – {wo}" if wo else ""))
    except Exception:       # noqa: BLE001 - ohne Protokoll weiterarbeiten
        pass
    return True


def _b64_ok(text):
    """Grobe Prüfung, dass ein VERIFIZIERER-Text wie ein Ed25519-Schlüssel aussieht (32 Byte Base64)."""
    try:
        return len(base64.b64decode(text, validate=True)) == 32
    except Exception:       # noqa: BLE001
        return False
