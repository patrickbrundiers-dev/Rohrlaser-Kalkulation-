"""Hauptadmin-Lizenz ohne Rechner-ID, mit Passwort beim Start (Patrick 12.11.2026).

Eine eigene Lizenzart neben den Kundenlizenzen (lizenz.py bleibt, wie es ist). Die Datei hauptadmin.lizenz liegt im
Ordner Lizenz neben aktiv.lizenz und ist JSON:

    {"format": 1,
     "inhalt":  {"art": "hauptadmin", "lizenz_id": "HA-2026-0001", "inhaber": …, "ausgestellt": …, "rechner": [],
                 "funktionen": ["alle"], "admin_schluessel": "<öffentlicher Ed25519-Schlüssel, Base64>",
                 "schluessel_id": "K1", …},
     "signatur": "<Ed25519-Signatur des Inhalts mit Patricks Lizenzschlüssel (wie jede Lizenz)>",
     "tresor":  {"kdf": "scrypt", "n": …, "r": 8, "p": 1, "salz": hex, "nonce": hex, "daten": Base64, "stand": 1,
                 "geaendert": "JJJJ-MM-TT"}}

Zwei Schlüssel, zwei Aufgaben (Trennung von Lizenzprüfung und Anmeldung):
- Lizenzprüfung: Der Inhalt ist mit dem Lizenzschlüssel signiert (privat nur im Lizenz-Werkzeug). Wer etwas daran
  ändert (Art, Rechner, Admin-Schlüssel), macht die Signatur ungültig. Eine Rechner-ID gibt es nicht (rechner = []).
- Anmeldung: Im Tresor liegt der private Admin-Schlüssel, verschlüsselt mit AES-256-GCM. Der Schlüssel dafür kommt
  aus dem Passwort über scrypt mit eigenem Salz (langsam und speicherhungrig gegen Durchprobieren). Das Passwort ist
  richtig, wenn der Tresor sich öffnen lässt UND der Schlüssel darin zum signierten admin_schluessel passt. Das
  Passwort wird also nirgends gespeichert, auch nicht als Hash; ein selbst gebauter Tresor passt nie zum signierten
  öffentlichen Schlüssel.

Passwort ändern: Tresor mit dem neuen Passwort neu verschlüsseln (stand + 1). Die Signatur bleibt gültig, das
Lizenz-Werkzeug ist dafür nicht nötig. Jeder Rechner merkt sich den höchsten Stand (anmeldung.json); eine ältere Kopie
der Datei (altes Passwort) nimmt er danach nicht mehr an. Grenze (offline): Ein Rechner, der den neuen Stand nie
gesehen hat, nimmt eine alte Kopie mit dem alten Passwort weiter an. Ist ein Passwort bekannt geworden, hilft nur eine
neue Hauptadmin-Lizenz aus dem Lizenz-Werkzeug (Feld ersetzt) und die Sperrliste.

Schutz gegen Durchprobieren: nach FEHL_FREI Fehlversuchen Sperre SPERRE_ERSTE_S, jede weitere Fehleingabe verdoppelt
sie bis SPERRE_MAX_S. Der Zähler steht an zwei Orten (Lizenzordner und Benutzerprofil, es zählt der höhere Wert).

Ohne Qt; alle Funktionen sind mit festen Werten testbar.
"""
import base64
import datetime
import hmac
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from . import lizenz as L

ART = "hauptadmin"
FORMAT = 1
DATEI = "hauptadmin.lizenz"
ANMELDUNG = "anmeldung.json"
PRAEFIX = "HA"                  # Lizenz-IDs HA-JJJJ-NNNN (eigene Zählung im Register des Lizenz-Werkzeugs)
PASSWORT_MIN = 10
FEHL_FREI = 5                   # so viele Fehlversuche ohne Wartezeit
SPERRE_ERSTE_S = 60             # danach 1 Minute, jede weitere Fehleingabe verdoppelt …
SPERRE_MAX_S = 3600             # … bis höchstens 60 Minuten
KDF = dict(n=2 ** 16, r=8, p=1)  # scrypt: 64 MB Speicher, je Versuch etwa 0,2–0,5 s
KDF_MIN_N, KDF_MAX_N = 2 ** 14, 2 ** 20


class HauptadminFehler(L.LizenzFehler):
    """Hauptadmin-Datei ungültig oder Passwort falsch (Text für den Benutzer)."""


# ------------------------------------------------------------------ Tresor (Passwort -> Admin-Schlüssel)
def _b64(b):
    return base64.b64encode(b).decode("ascii")


def _kdf(passwort, salz, n, r, p):
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=salz, length=32, n=n, r=r, p=p).derive(str(passwort).encode("utf-8"))


def _aad(inhalt):
    """Zusatzdaten der Verschlüsselung: der Tresor gehört genau zu dieser Lizenz und diesem Admin-Schlüssel."""
    return L.kanonisch(dict(lizenz_id=inhalt.get("lizenz_id"), admin_schluessel=inhalt.get("admin_schluessel")))


def tresor_bilden(seed, passwort, inhalt, stand=1, kdf=None, heute=None):
    """Tresor: privater Admin-Schlüssel (32 Byte) mit dem Passwort verschlüsselt."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    k = dict(KDF, **(kdf or {}))
    salz, nonce = os.urandom(16), os.urandom(12)
    daten = AESGCM(_kdf(passwort, salz, k["n"], k["r"], k["p"])).encrypt(nonce, bytes(seed), _aad(inhalt))
    return dict(kdf="scrypt", n=k["n"], r=k["r"], p=k["p"], salz=salz.hex(), nonce=nonce.hex(), daten=_b64(daten),
                stand=int(stand), geaendert=(heute or datetime.date.today()).isoformat())


def _oeffentlich_aus_seed(seed):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return L.oeffentlich_text(Ed25519PrivateKey.from_private_bytes(seed))


def tresor_oeffnen(daten, passwort):
    """Privater Admin-Schlüssel (32 Byte), wenn das Passwort stimmt und der Schlüssel zum signierten admin_schluessel
    passt; sonst None. Prüft nicht die Signatur (dafür pruefen())."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not passwort:
        return None
    t, inhalt = daten.get("tresor") or {}, daten.get("inhalt") or {}
    try:
        n, r, p = int(t["n"]), int(t["r"]), int(t["p"])
        if not (KDF_MIN_N <= n <= KDF_MAX_N and n & (n - 1) == 0 and 1 <= r <= 16 and 1 <= p <= 4):
            return None
        schluessel = _kdf(passwort, bytes.fromhex(t["salz"]), n, r, p)
        seed = AESGCM(schluessel).decrypt(bytes.fromhex(t["nonce"]), base64.b64decode(t["daten"]), _aad(inhalt))
    except (InvalidTag, KeyError, TypeError, ValueError):
        return None
    if len(seed) != 32:
        return None
    soll = str(inhalt.get("admin_schluessel") or "")
    if not hmac.compare_digest(_oeffentlich_aus_seed(seed).encode("ascii"), soll.encode("ascii")):
        return None
    return seed


def passwort_regeln(neu, alt=None):
    """Fehlertext für ein neues Hauptadmin-Passwort oder '' (in Ordnung)."""
    neu = neu or ""
    if len(neu) < PASSWORT_MIN:
        return f"Das Passwort braucht mindestens {PASSWORT_MIN} Zeichen."
    if len(set(neu)) < 4:
        return "Das Passwort ist zu einfach (zu wenige verschiedene Zeichen)."
    if alt is not None and neu == alt:
        return "Das neue Passwort muss sich vom bisherigen unterscheiden."
    return ""


# ------------------------------------------------------------------ Datei ausstellen und prüfen
def erstellen(inhaber, passwort, privat, schluessel_id, lizenz_id, heute=None, hinweis="", ersetzt="", kdf=None):
    """Neue Hauptadmin-Lizenz (Lizenz-Werkzeug und Tests). privat: Patricks Ed25519-Lizenzschlüssel. Ergebnis: dict."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    fehler = passwort_regeln(passwort)
    if fehler:
        raise HauptadminFehler(fehler)
    heute = heute or datetime.date.today()
    admin = Ed25519PrivateKey.generate()
    seed = admin.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                               serialization.NoEncryption())
    inhalt = dict(art=ART, lizenz_id=lizenz_id, inhaber=inhaber or "", ausgestellt=heute.isoformat(), rechner=[],
                  funktionen=["alle"], admin_schluessel=L.oeffentlich_text(admin), schluessel_id=schluessel_id,
                  hinweis=hinweis or "")
    if ersetzt:
        inhalt["ersetzt"] = ersetzt
    return dict(format=FORMAT, inhalt=inhalt, signatur=L.signieren(inhalt, privat),
                tresor=tresor_bilden(seed, passwort, inhalt, 1, kdf, heute))


def ist_datei(quelle):
    """True, wenn quelle (Pfad, Text, dict) eine Hauptadmin-Datei sein will (Art), ohne sie zu prüfen."""
    try:
        d = L.lesen(quelle)
    except L.LizenzFehler:
        return False
    return isinstance(d.get("inhalt"), dict) and d["inhalt"].get("art") == ART


def pruefen(quelle, schluessel=None):
    """Aufbau und Signatur einer Hauptadmin-Datei (ohne Passwort). Ergebnis: (daten, inhalt); HauptadminFehler mit
    Begründung, wenn sie ungültig ist. Unabhängig von lizenz.pruefen (die kennt die Art nicht und lehnt sie ab)."""
    daten = L.lesen(quelle)
    inhalt = daten.get("inhalt")
    if daten.get("format") != FORMAT or not isinstance(inhalt, dict):
        raise HauptadminFehler("Das ist keine Hauptadmin-Lizenz (Format oder Inhalt fehlt).")
    if inhalt.get("art") != ART:
        raise HauptadminFehler("Das ist keine Hauptadmin-Lizenz.")
    schluessel = L.standard_schluessel() if schluessel is None else schluessel
    sid = inhalt.get("schluessel_id")
    if sid not in schluessel:
        raise HauptadminFehler(f"Hauptadmin-Lizenz mit unbekanntem Schlüssel {sid!r} – bitte das Programm "
                               "aktualisieren.")
    if not L.signatur_gueltig(inhalt, daten.get("signatur"), sid, schluessel):
        raise HauptadminFehler("Signatur ungültig: Die Hauptadmin-Lizenz wurde verändert oder stammt nicht von "
                               "Patrick.")
    if not inhalt.get("lizenz_id"):
        raise HauptadminFehler("Lizenz-ID fehlt.")
    if inhalt.get("rechner") != []:
        raise HauptadminFehler("Eine Hauptadmin-Lizenz ist an keinen Rechner gebunden (Feld rechner muss leer sein).")
    if inhalt.get("admin_passwort") or inhalt.get("gueltig_bis"):
        raise HauptadminFehler("Hauptadmin-Lizenz mit unzulässigen Feldern.")
    try:
        if len(base64.b64decode(str(inhalt.get("admin_schluessel")), validate=True)) != 32:
            raise ValueError
    except ValueError:
        raise HauptadminFehler("Admin-Schlüssel der Hauptadmin-Lizenz fehlt oder ist beschädigt.") from None
    t = daten.get("tresor")
    if not isinstance(t, dict) or t.get("kdf") != "scrypt" or not isinstance(t.get("stand"), int):
        raise HauptadminFehler("Passwort-Tresor der Hauptadmin-Lizenz fehlt oder ist beschädigt.")
    return daten, inhalt


def passwort_aendern(daten, alt, neu, heute=None, kdf=None):
    """Neue Daten mit dem Tresor für das neue Passwort (stand + 1). HauptadminFehler, wenn das alte Passwort falsch ist
    oder das neue den Regeln nicht genügt. Die Signatur des Inhalts bleibt unverändert gültig."""
    seed = tresor_oeffnen(daten, alt)
    if seed is None:
        raise HauptadminFehler("Das bisherige Passwort ist falsch.")
    fehler = passwort_regeln(neu, alt)
    if fehler:
        raise HauptadminFehler(fehler)
    alt_t = daten["tresor"]
    k = kdf or dict(n=max(int(alt_t["n"]), KDF["n"]), r=int(alt_t["r"]), p=int(alt_t["p"]))
    return dict(daten, tresor=tresor_bilden(seed, neu, daten["inhalt"], int(alt_t["stand"]) + 1, k, heute))


def stand(daten):
    return int((daten.get("tresor") or {}).get("stand") or 0)


# ------------------------------------------------------------------ Anmeldesperre
def zweiter_ort():
    """Zweiter Ort für den Fehlversuch-Zähler: im Benutzerprofil (APPDATA), nicht im Daten- oder Programmordner."""
    basis = os.environ.get("APPDATA")
    return (Path(basis) / "Rohrlaser" if basis else Path.home() / ".rohrlaser") / ANMELDUNG


class Sperre:
    """Fehlversuche und Wartezeit der Hauptadmin-Anmeldung, dazu der höchste gesehene Tresor-Stand je Lizenz. Gelesen
    wird von allen Orten (höchster Wert zählt), geschrieben an alle; ein fehlender Ort ist kein Fehler."""

    def __init__(self, orte, uhr=time.time):
        self.orte = [Path(o) for o in orte]
        self.uhr = uhr

    def _lesen(self):
        fehl, bis, staende = 0, 0.0, {}
        for o in self.orte:
            try:
                d = json.loads(o.read_text(encoding="utf-8"))
                fehl = max(fehl, int(d.get("fehl") or 0))
                bis = max(bis, float(d.get("bis") or 0))
                for k, v in (d.get("staende") or {}).items():
                    staende[str(k)] = max(staende.get(str(k), 0), int(v))
            except (OSError, ValueError, TypeError, AttributeError):
                continue
        return dict(fehl=fehl, bis=bis, staende=staende)

    def _schreiben(self, d):
        for o in self.orte:
            try:
                L._schreiben(o, json.dumps(d))
            except OSError:
                continue

    def wartezeit(self):
        """Sekunden bis zum nächsten erlaubten Versuch (0 = jetzt)."""
        return max(0, int(self._lesen()["bis"] - self.uhr() + 0.999))

    def fehlversuche(self):
        return self._lesen()["fehl"]

    def fehlschlag(self):
        """Fehlversuch zählen. Ergebnis: Wartezeit in Sekunden ab jetzt (0 = noch ohne Sperre)."""
        d = self._lesen()
        d["fehl"] += 1
        warten = 0
        if d["fehl"] >= FEHL_FREI:
            warten = min(SPERRE_ERSTE_S * 2 ** (d["fehl"] - FEHL_FREI), SPERRE_MAX_S)
            d["bis"] = max(d["bis"], self.uhr() + warten)
        self._schreiben(d)
        return warten

    def erfolg(self):
        d = self._lesen()
        d.update(fehl=0, bis=0)
        self._schreiben(d)

    def stand(self, lizenz_id):
        return self._lesen()["staende"].get(str(lizenz_id), 0)

    def stand_merken(self, lizenz_id, neu):
        d = self._lesen()
        if int(neu) > d["staende"].get(str(lizenz_id), 0):
            d["staende"][str(lizenz_id)] = int(neu)
            self._schreiben(d)


@dataclass
class Ergebnis:
    """Ergebnis einer Anmeldung: ok, notfall (mit Notfallcode), text (Grund), warten (Sekunden Sperre), rest (Versuche
    bis zur Sperre)."""
    ok: bool
    text: str = ""
    warten: int = 0
    notfall: bool = False
    rest: int = 0


def warte_text(sekunden):
    if sekunden >= 120:
        return f"{(sekunden + 59) // 60} Minuten"
    return f"{sekunden} Sekunden"
