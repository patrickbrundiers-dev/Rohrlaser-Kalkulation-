"""Entwickler-Identität: der Entwickler-Ausweis (Paket A, ersetzt den Zugang mit festem Prüfwert aus PR #703).

Datei entwickler.ausweis (JSON):

    {"format": 1,
     "inhalt": {"art": "entwickler_ausweis", "ausweis_id": "EW-2026-0001", "name": "Patrick",
                "ausgestellt": "JJJJ-MM-TT", "gueltig_bis": "JJJJ-MM-TT",
                "umgebungen": ["produktiv", "test", "entwicklung"], "installationen": ["*"],
                "anmelde_schluessel": "<öffentlicher Ed25519-Schlüssel, Base64>", "schluessel_id": "K1", …},
     "signatur": "<Signatur des Inhalts mit Patricks Lizenzschlüssel>",
     "tresor": {"kdf": "scrypt", "n": …, "r": 8, "p": 1, "salz": hex, "nonce": hex, "daten": Base64, "stand": 1, …}}

Warum das sicher ist, ohne Passwort im Programm:
- Echtheit: Der Inhalt ist mit dem privaten Lizenzschlüssel signiert, der nur im Lizenz-Werkzeug bei Patrick liegt.
  Das Programm kennt nur den öffentlichen Schlüssel (lizenz_schluessel.py). Ein Kundenadministrator kann deshalb
  keinen Ausweis erzeugen oder verändern (Art, Laufzeit, Umgebungen, Installationen).
- Besitz und Wissen: Der private Anmeldeschlüssel liegt im Tresor, verschlüsselt mit AES-256-GCM; der Schlüssel dafür
  kommt über scrypt (eigenes Salz) aus Patricks Passwort. Richtig ist das Passwort nur, wenn der Tresor aufgeht UND
  der Schlüssel darin zum signierten anmelde_schluessel passt. Das Passwort steht nirgends, auch nicht als Hash.
- Keine Rechnerbindung: Der Ausweis enthält keine Rechner-ID. Er gilt an jeder Installation, die in installationen
  steht ("*" = alle) und deren Umgebung in umgebungen steht.
- Anmeldung als Nachweis: Mit dem geöffneten Schlüssel wird eine frische Anfrage (Zufallszahl, Installation, Zeit)
  signiert. Ein Server prüft diese Signatur selbst (anfrage_pruefen) und muss dafür nie ein Passwort sehen.
- Widerruf: Ausweis-IDs kommen auf die signierte Sperrliste (wie Lizenzen). Passwort ändern = neuer Tresor (stand+1);
  jede Installation merkt sich den höchsten gesehenen Stand und nimmt ältere Kopien danach nicht mehr an.

Zwei Wege (Empfehlung E2a): Ausweis auf dem USB-Stick (Besitz = zweiter Faktor, nötig an fremden Installationen) oder
je Installation hinterlegt (hinterlegen(), nur mit dem Ausweis vom Stick); eine hinterlegte Kopie kann zusätzlich einen
Einmalcode (TOTP) verlangen. Ohne Qt.
"""
import base64
import datetime
import hmac
import json
import os
import secrets
from pathlib import Path

from .. import lizenz as L

ART = "entwickler_ausweis"
ART_ANFRAGE = "entwickler_anmeldung"
ART_HINTERLEGT = "entwickler_hinterlegt"
FORMAT = 1
DATEI = "entwickler.ausweis"
DATEI_HINTERLEGT = "entwickler_hinterlegt.json"
PRAEFIX = "EW"
UMGEBUNGEN = ("produktiv", "test", "entwicklung")
ALLE = "*"
LAUFZEIT_MAX_TAGE = 3 * 366          # länger nimmt das Programm einen Ausweis nicht an
ANFRAGE_MAX_ALTER_S = 120
KDF = dict(n=2 ** 17, r=8, p=1)       # 128 MB je Versuch: Durchprobieren einer gestohlenen Datei teuer machen
KDF_MIN_N, KDF_MAX_N = 2 ** 14, 2 ** 20
PASSWORT_MIN = 12


class AusweisFehler(L.LizenzFehler):
    """Ausweis ungültig, Passwort falsch oder Anfrage abgelehnt (Text für den Benutzer)."""


def _b64(b):
    return base64.b64encode(b).decode("ascii")


def _kdf(passwort, salz, n, r, p):
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    return Scrypt(salt=salz, length=32, n=n, r=r, p=p).derive(str(passwort).encode("utf-8"))


def _aad(inhalt):
    return L.kanonisch(dict(ausweis_id=inhalt.get("ausweis_id"), anmelde_schluessel=inhalt.get("anmelde_schluessel")))


def _privat(seed):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(bytes(seed))


def passwort_regeln(neu, alt=None):
    neu = neu or ""
    if len(neu) < PASSWORT_MIN:
        return f"Das Entwickler-Passwort braucht mindestens {PASSWORT_MIN} Zeichen."
    if len(set(neu)) < 6:
        return "Das Entwickler-Passwort ist zu einfach (zu wenige verschiedene Zeichen)."
    if alt is not None and neu == alt:
        return "Das neue Passwort muss sich vom bisherigen unterscheiden."
    return ""


def tresor_bilden(seed, passwort, inhalt, stand=1, kdf=None, heute=None):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    k = dict(KDF, **(kdf or {}))
    salz, nonce = os.urandom(16), os.urandom(12)
    daten = AESGCM(_kdf(passwort, salz, k["n"], k["r"], k["p"])).encrypt(nonce, bytes(seed), _aad(inhalt))
    return dict(kdf="scrypt", n=k["n"], r=k["r"], p=k["p"], salz=salz.hex(), nonce=nonce.hex(), daten=_b64(daten),
                stand=int(stand), geaendert=(heute or datetime.date.today()).isoformat())


def tresor_oeffnen(daten, passwort):
    """Privater Anmeldeschlüssel (32 Byte) oder None (Passwort falsch, Tresor fremd oder beschädigt)."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not passwort:
        return None
    t, inhalt = daten.get("tresor") or {}, daten.get("inhalt") or {}
    try:
        n, r, p = int(t["n"]), int(t["r"]), int(t["p"])
        if not (KDF_MIN_N <= n <= KDF_MAX_N and n & (n - 1) == 0 and 1 <= r <= 16 and 1 <= p <= 4):
            return None
        seed = AESGCM(_kdf(passwort, bytes.fromhex(t["salz"]), n, r, p)).decrypt(
            bytes.fromhex(t["nonce"]), base64.b64decode(t["daten"]), _aad(inhalt))
    except (InvalidTag, KeyError, TypeError, ValueError):
        return None
    if len(seed) != 32:
        return None
    ist = L.oeffentlich_text(_privat(seed)).encode("ascii")
    if not hmac.compare_digest(ist, str(inhalt.get("anmelde_schluessel") or "").encode("ascii")):
        return None
    return seed


# ------------------------------------------------------------------ ausstellen (Lizenz-Werkzeug, Tests)
def erstellen(name, passwort, privat, schluessel_id, ausweis_id, gueltig_bis, umgebungen=UMGEBUNGEN,
              installationen=(ALLE,), heute=None, ersetzt="", kdf=None):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    fehler = passwort_regeln(passwort)
    if fehler:
        raise AusweisFehler(fehler)
    heute = heute or datetime.date.today()
    if not (heute < gueltig_bis <= heute + datetime.timedelta(days=LAUFZEIT_MAX_TAGE)):
        raise AusweisFehler(f"Laufzeit des Ausweises: nach heute und höchstens {LAUFZEIT_MAX_TAGE} Tage.")
    falsch = [u for u in umgebungen if u not in UMGEBUNGEN]
    if falsch or not umgebungen:
        raise AusweisFehler(f"Unbekannte Umgebung: {', '.join(falsch) or '(keine)'}")
    schluessel = Ed25519PrivateKey.generate()
    seed = schluessel.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                    serialization.NoEncryption())
    inhalt = dict(art=ART, ausweis_id=ausweis_id, name=name or "", ausgestellt=heute.isoformat(),
                  gueltig_bis=gueltig_bis.isoformat(), umgebungen=sorted(set(umgebungen)),
                  installationen=sorted(set(installationen)) or [ALLE],
                  anmelde_schluessel=L.oeffentlich_text(schluessel), schluessel_id=schluessel_id, rechner=[])
    if ersetzt:
        inhalt["ersetzt"] = ersetzt
    return dict(format=FORMAT, inhalt=inhalt, signatur=L.signieren(inhalt, privat),
                tresor=tresor_bilden(seed, passwort, inhalt, 1, kdf, heute))


# ------------------------------------------------------------------ prüfen
def lesen(quelle):
    return L.lesen(quelle)


def ist_ausweis(quelle):
    try:
        d = lesen(quelle)
    except L.LizenzFehler:
        return False
    return isinstance(d.get("inhalt"), dict) and d["inhalt"].get("art") == ART


def pruefen(quelle, schluessel=None, heute=None, gesperrt=(), umgebung=None, installation=None, spaetestes=None):
    """Aufbau, Signatur, Laufzeit, Sperrliste, Umgebung und Installation. Ergebnis: (daten, inhalt);
    AusweisFehler mit verständlicher Begründung, wenn der Ausweis hier nicht gilt."""
    daten = lesen(quelle)
    inhalt = daten.get("inhalt")
    if daten.get("format") != FORMAT or not isinstance(inhalt, dict) or inhalt.get("art") != ART:
        raise AusweisFehler("Das ist kein Entwickler-Ausweis.")
    schluessel = L.standard_schluessel() if schluessel is None else schluessel
    sid = inhalt.get("schluessel_id")
    if sid not in schluessel:
        raise AusweisFehler(f"Entwickler-Ausweis mit unbekanntem Schlüssel {sid!r} – bitte das Programm aktualisieren.")
    if not L.signatur_gueltig(inhalt, daten.get("signatur"), sid, schluessel):
        raise AusweisFehler("Signatur ungültig: Der Entwickler-Ausweis wurde verändert oder ist nicht echt.")
    aid = str(inhalt.get("ausweis_id") or "")
    if not aid.startswith(PRAEFIX + "-"):
        raise AusweisFehler("Ausweis-Nummer fehlt.")
    if inhalt.get("rechner") not in ([], None):
        raise AusweisFehler("Ein Entwickler-Ausweis ist an keinen Rechner gebunden.")
    try:
        if len(base64.b64decode(str(inhalt.get("anmelde_schluessel")), validate=True)) != 32:
            raise ValueError
        ab = datetime.date.fromisoformat(inhalt["ausgestellt"])
        bis = datetime.date.fromisoformat(inhalt["gueltig_bis"])
    except (ValueError, KeyError, TypeError):
        raise AusweisFehler("Der Entwickler-Ausweis ist beschädigt.") from None
    heute = heute or datetime.date.today()
    if spaetestes and L.uhr_zurueck(heute, spaetestes):
        raise AusweisFehler("Die Uhr dieses Rechners geht nach. Bitte Datum und Uhrzeit prüfen.")
    if bis - ab > datetime.timedelta(days=LAUFZEIT_MAX_TAGE):
        raise AusweisFehler("Laufzeit des Ausweises unzulässig lang.")
    if heute > bis:
        raise AusweisFehler(f"Der Entwickler-Ausweis ist am {bis:%d.%m.%Y} abgelaufen.")
    if heute < ab - datetime.timedelta(days=L.UHR_TOLERANZ_TAGE):
        raise AusweisFehler("Der Entwickler-Ausweis gilt erst ab dem Ausstellungstag.")
    if aid in set(gesperrt or ()):
        raise AusweisFehler(f"Der Entwickler-Ausweis {aid} ist gesperrt.")
    if umgebung is not None and umgebung not in (inhalt.get("umgebungen") or []):
        raise AusweisFehler(f"Der Entwickler-Ausweis gilt nicht für die Umgebung „{umgebung}“.")
    inst = inhalt.get("installationen") or []
    if installation is not None and ALLE not in inst and installation not in inst:
        raise AusweisFehler("Der Entwickler-Ausweis gilt nicht für diese Installation.")
    t = daten.get("tresor")
    if not isinstance(t, dict) or t.get("kdf") != "scrypt" or not isinstance(t.get("stand"), int):
        raise AusweisFehler("Passwort-Tresor des Ausweises fehlt oder ist beschädigt.")
    return daten, inhalt


def stand(daten):
    return int((daten.get("tresor") or {}).get("stand") or 0)


def passwort_aendern(daten, alt, neu, heute=None, kdf=None):
    """Neue Daten mit neuem Tresor (stand + 1); die Signatur bleibt gültig."""
    seed = tresor_oeffnen(daten, alt)
    if seed is None:
        raise AusweisFehler("Das bisherige Entwickler-Passwort ist falsch.")
    fehler = passwort_regeln(neu, alt)
    if fehler:
        raise AusweisFehler(fehler)
    t = daten["tresor"]
    k = kdf or dict(n=max(int(t["n"]), KDF["n"]), r=int(t["r"]), p=int(t["p"]))
    return dict(daten, tresor=tresor_bilden(seed, neu, daten["inhalt"], int(t["stand"]) + 1, k, heute))


# ------------------------------------------------------------------ Anmeldenachweis (für Server und Pruefstelle)
def _jetzt():
    return datetime.datetime.now(datetime.timezone.utc)


def anfrage_signieren(seed, inhalt, installation, jetzt=None, nonce=None):
    """Signierte Anmeldeanfrage: beweist den Besitz des Anmeldeschlüssels, ohne das Passwort weiterzugeben."""
    a = dict(art=ART_ANFRAGE, ausweis_id=inhalt["ausweis_id"], installation=str(installation),
             nonce=nonce or secrets.token_hex(16), zeit=(jetzt or _jetzt()).isoformat(timespec="seconds"))
    return dict(a, signatur=_b64(_privat(seed).sign(L.kanonisch(a))))


def anfrage_pruefen(anfrage, inhalt, installation, jetzt=None, gesehen=None, max_alter_s=ANFRAGE_MAX_ALTER_S):
    """Prüft eine Anmeldeanfrage gegen den (bereits geprüften) Ausweis-Inhalt. gesehen: Menge benutzter Nonces
    (Wiederholung wird abgelehnt und die Nonce eingetragen). AusweisFehler bei Ablehnung."""
    from cryptography.exceptions import InvalidSignature
    if not isinstance(anfrage, dict) or anfrage.get("art") != ART_ANFRAGE:
        raise AusweisFehler("Keine Entwickler-Anmeldung.")
    a = {k: v for k, v in anfrage.items() if k != "signatur"}
    if a.get("ausweis_id") != inhalt.get("ausweis_id"):
        raise AusweisFehler("Anmeldung gehört zu einem anderen Ausweis.")
    if str(a.get("installation")) != str(installation):
        raise AusweisFehler("Anmeldung gehört zu einer anderen Installation.")
    try:
        zeit = datetime.datetime.fromisoformat(a["zeit"])
        L._oeffentlich(inhalt["anmelde_schluessel"]).verify(base64.b64decode(anfrage.get("signatur") or "",
                                                                             validate=True), L.kanonisch(a))
    except (InvalidSignature, KeyError, TypeError, ValueError):
        raise AusweisFehler("Anmeldung nicht echt (Signatur passt nicht zum Ausweis).") from None
    alter = abs(((jetzt or _jetzt()) - zeit).total_seconds())
    if alter > max_alter_s:
        raise AusweisFehler("Anmeldung zu alt oder Uhr falsch (mehr als 2 Minuten Abstand).")
    if gesehen is not None:
        n = str(a.get("nonce") or "")
        if not n or n in gesehen:
            raise AusweisFehler("Diese Anmeldung wurde schon benutzt.")
        gesehen.add(n)
    return True


# ------------------------------------------------------------------ hinterlegen und finden
def hinterlegen(ordner, daten, installation, totp_geheimnis="", heute=None, schluessel=None):
    """Ausweis für diese Installation hinterlegen (ordner = Zugangsordner der Installation). Danach zeigt das
    Loginfenster „Entwickler“ auch ohne Stick. Gespeichert wird der Ausweis mit Tresor (das Passwort nicht)."""
    pruefen(daten, schluessel, heute, installation=installation)
    h = dict(art=ART_HINTERLEGT, installation=str(installation), ausweis=daten,
             hinterlegt=(heute or datetime.date.today()).isoformat(), totp=str(totp_geheimnis or ""))
    p = Path(ordner) / DATEI_HINTERLEGT
    L._schreiben(p, json.dumps(h, indent=1, ensure_ascii=False))
    return p


def hinterlegt(ordner):
    """Hinterlegter Eintrag dict(ausweis=…, totp=…, installation=…) oder None."""
    p = Path(ordner) / DATEI_HINTERLEGT
    try:
        h = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return h if isinstance(h, dict) and h.get("art") == ART_HINTERLEGT and isinstance(h.get("ausweis"), dict) else None


def entfernen(ordner):
    p = Path(ordner) / DATEI_HINTERLEGT
    if p.exists():
        p.unlink()
        return True
    return False


def wechseldatentraeger():
    """Wurzeln der USB-Sticks/Wechseldatenträger (Windows); anderswo leer."""
    if os.name != "nt":
        return []
    import ctypes
    import string
    aus = []
    maske = ctypes.windll.kernel32.GetLogicalDrives()
    for i, b in enumerate(string.ascii_uppercase):
        if maske & (1 << i):
            wurzel = f"{b}:\\"
            if ctypes.windll.kernel32.GetDriveTypeW(wurzel) == 2:       # DRIVE_REMOVABLE
                aus.append(Path(wurzel))
    return aus


def auf_stick_suchen(wurzeln=None):
    """Erster Entwickler-Ausweis auf einem Wechseldatenträger (Wurzel oder Ordner NexTube/), sonst None."""
    for w in (wechseldatentraeger() if wurzeln is None else wurzeln):
        for p in (Path(w) / DATEI, Path(w) / "NexTube" / DATEI):
            try:
                if p.is_file() and ist_ausweis(p):
                    return p
            except OSError:
                continue
    return None
