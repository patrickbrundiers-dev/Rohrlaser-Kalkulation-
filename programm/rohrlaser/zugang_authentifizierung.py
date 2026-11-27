"""Anmeldung: Passwort-Hash, Passwortregeln, Einmalcode (TOTP), Sperre gegen Durchprobieren (Paket A).

Passwort-Hash: 'scrypt$<n>$<r>$<p>$<salz hex>$<hash hex>' – langsam und speicherhungrig, eigenes Salz je Passwort.
Ein alter Hash aus passwort.py ('pbkdf2_sha256$…') bleibt gültig; braucht_umstellung() sagt, dass er bei der nächsten
erfolgreichen Anmeldung durch einen scrypt-Hash ersetzt werden soll. Klartext wird nie angenommen.

Einmalcode (zweiter Faktor, optional): TOTP nach RFC 6238 (SHA-1, 6 Ziffern, 30 s) – geht mit jeder
Authenticator-App ohne Internet. Ein Code gilt nur einmal (letzter benutzter Zeitschritt wird gemerkt).

Sperre: hauptadmin.Sperre (5 Versuche frei, dann 60 s, verdoppelt bis 60 Minuten), Zähler je Benutzer.
Ohne Qt.
"""
import base64
import hashlib
import hmac
import os
import secrets
import struct
import time

from . import hauptadmin as _ha
from . import passwort as _alt

ART = "scrypt"
KDF = dict(n=2 ** 15, r=8, p=1)      # 32 MB je Prüfung, etwa 0,1–0,3 s
KDF_MIN_N, KDF_MAX_N = 2 ** 12, 2 ** 20
PASSWORT_MIN = 10                   # Büro und Administratoren
PIN_MIN = 6                         # Werkstatt-PIN (E5a): mindestens 6 Ziffern
TOTP_SCHRITT_S, TOTP_STELLEN, TOTP_FENSTER = 30, 6, 1

Sperre = _ha.Sperre
warte_text = _ha.warte_text


def _scrypt(text, salz, n, r, p):
    return hashlib.scrypt(str(text).encode("utf-8"), salt=salz, n=n, r=r, p=p, maxmem=256 * 1024 * 1024, dklen=32)


def hash_bilden(text, kdf=None, salz=None):
    """Hash zum Speichern. Leerer Text ist kein Passwort (ValueError)."""
    if not text:
        raise ValueError("Leeres Passwort")
    k = dict(KDF, **(kdf or {}))
    salz = salz if salz is not None else os.urandom(16)
    h = _scrypt(text, salz, k["n"], k["r"], k["p"])
    return f"{ART}${k['n']}${k['r']}${k['p']}${salz.hex()}${h.hex()}"


def ist_hash(wert):
    t = str(wert or "").split("$")
    return (len(t) == 6 and t[0] == ART and all(x.isdigit() for x in t[1:4])) or _alt.ist_hash(wert)


def pruefen(text, gespeichert):
    """True nur, wenn text zum gespeicherten Hash passt. Leerer Hash oder Klartext: immer False (anders als
    passwort.pruefen, das ohne Passwort True liefert – im Zugangssystem gibt es kein Konto ohne Passwort)."""
    if not text or not gespeichert:
        return False
    g = str(gespeichert)
    if g.startswith(ART + "$"):
        try:
            _, n, r, p, salz, soll = g.split("$")
            n, r, p = int(n), int(r), int(p)
            if not (KDF_MIN_N <= n <= KDF_MAX_N and n & (n - 1) == 0 and 1 <= r <= 16 and 1 <= p <= 4):
                return False
            ist = _scrypt(text, bytes.fromhex(salz), n, r, p)
        except (ValueError, TypeError):
            return False
        return hmac.compare_digest(ist.hex(), soll)
    if _alt.ist_hash(g):
        return _alt.pruefen(text, g)
    return False


def braucht_umstellung(gespeichert):
    """True für einen alten PBKDF2-Hash oder einen scrypt-Hash mit schwächeren Parametern als KDF."""
    g = str(gespeichert or "")
    if _alt.ist_hash(g):
        return True
    try:
        _, n, r, p, _s, _h = g.split("$")
        return int(n) < KDF["n"] or int(r) < KDF["r"]
    except ValueError:
        return False


def passwort_regeln(neu, alt=None, pin=False, name=""):
    """Fehlertext für ein neues Passwort bzw. eine PIN oder '' (in Ordnung)."""
    neu = neu or ""
    if pin:
        if not neu.isdigit() or len(neu) < PIN_MIN:
            return f"Die PIN braucht mindestens {PIN_MIN} Ziffern."
        if len(set(neu)) < 3 or neu in "0123456789" or neu in "9876543210":
            return "Die PIN ist zu einfach."
    else:
        if len(neu) < PASSWORT_MIN:
            return f"Das Passwort braucht mindestens {PASSWORT_MIN} Zeichen."
        if len(set(neu)) < 5:
            return "Das Passwort ist zu einfach (zu wenige verschiedene Zeichen)."
        if name and len(name) >= 3 and name.lower() in neu.lower():
            return "Das Passwort darf den Benutzernamen nicht enthalten."
    if alt is not None and neu == alt:
        return "Das neue Passwort muss sich vom bisherigen unterscheiden."
    return ""


# ------------------------------------------------------------------ Einmalcode (TOTP, RFC 6238)
def totp_geheimnis_neu():
    """Neues Geheimnis (Base32, 160 Bit) zum Einrichten in der Authenticator-App."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _geheimnis_bytes(geheimnis):
    g = str(geheimnis or "").replace(" ", "").upper()
    return base64.b32decode(g + "=" * (-len(g) % 8))


def totp_code(geheimnis, jetzt=None, schritt=None):
    """Code für den Zeitpunkt jetzt (Sekunden) oder den Zeitschritt schritt."""
    s = int((time.time() if jetzt is None else jetzt) // TOTP_SCHRITT_S) if schritt is None else int(schritt)
    h = hmac.new(_geheimnis_bytes(geheimnis), struct.pack(">Q", s), hashlib.sha1).digest()
    o = h[-1] & 0x0F
    zahl = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** TOTP_STELLEN
    return f"{zahl:0{TOTP_STELLEN}d}"


def totp_pruefen(geheimnis, code, jetzt=None, zuletzt=-1):
    """Zeitschritt des passenden Codes (zum Merken gegen Wiederverwendung) oder None. Erlaubt ±TOTP_FENSTER
    Schritte Uhrabweichung; ein Schritt <= zuletzt (schon benutzt) gilt nicht."""
    code = str(code or "").replace(" ", "")
    if not code.isdigit() or len(code) != TOTP_STELLEN or not geheimnis:
        return None
    jetzt_s = int((time.time() if jetzt is None else jetzt) // TOTP_SCHRITT_S)
    for s in range(jetzt_s - TOTP_FENSTER, jetzt_s + TOTP_FENSTER + 1):
        if s > zuletzt and hmac.compare_digest(totp_code(geheimnis, schritt=s), code):
            return s
    return None


def totp_uri(geheimnis, konto, aussteller="NexTube"):
    """otpauth-URI für einen QR-Code (wird nur am Bildschirm gezeigt, nie gespeichert oder protokolliert)."""
    from urllib.parse import quote
    return (f"otpauth://totp/{quote(aussteller)}:{quote(konto)}?secret={geheimnis}&issuer={quote(aussteller)}"
            f"&digits={TOTP_STELLEN}&period={TOTP_SCHRITT_S}")
