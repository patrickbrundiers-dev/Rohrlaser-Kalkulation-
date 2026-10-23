"""Lizenz: signierte Lizenzdatei prüfen, Rechner-ID, Zustand (Admin, gültig, läuft bald ab, Kulanz, Lesemodus).

Offline: Eine Lizenzdatei (.lizenz) ist JSON {"format": 1, "inhalt": {…}, "signatur": "Base64"}. Signiert ist der
Inhalt in fester Form (kanonisch(): sortierte Schlüssel, ohne Leerzeichen, UTF-8) mit Ed25519. Der private Schlüssel
liegt nur bei Patrick im Lizenz-Werkzeug (werkzeuge/lizenz_werkzeug.py), die öffentlichen Schlüssel stehen in
lizenz_schluessel.py. Wer am Inhalt etwas ändert (z. B. das Ablaufdatum), macht die Signatur ungültig.

Lizenzarten: admin (unbefristet, Rechner Pflicht), benutzer und test (Ablaufdatum Pflicht). Zustände siehe
ermitteln(). Eine abgelaufene oder fehlende Lizenz sperrt nie die Daten, sondern schaltet in den Lesemodus –
und das auch erst, wenn DURCHSETZUNG eingeschaltet ist (Einführung in zwei Stufen, Plan Abschnitt 13).

Gegen eine zurückgestellte Uhr merkt sich das Programm das späteste gesehene Datum (Lizenz/zeit.json und die
Einstellung lizenz_zuletzt in der Datendatei, es zählt der größere Wert). Die Sperrliste (Widerruf) kommt signiert
mit dem Update-Check und wird in Lizenz/sperrliste.json gespeichert.

Ohne Qt; alle Prüfungen sind reine Funktionen mit den Parametern jetzt/heute und schluessel, damit sie testbar sind.
"""
import base64
import datetime
import hashlib
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

FORMAT = 1
ARTEN = ("admin", "benutzer", "test")
WARNUNG_TAGE = 30          # so viele Tage vor Ablauf: gelber Hinweis in der Statusleiste
WARNUNG_START_TAGE = 7     # so viele Tage vor Ablauf: zusätzlich Hinweis beim Start
KULANZ_TAGE = 14           # so lange nach Ablauf: noch voller Zugriff, roter Hinweis
UHR_TOLERANZ_TAGE = 2      # Uhr darf so weit hinter dem spätesten gesehenen Datum liegen
STANDARD_MONATE = 6        # Vorgabe-Laufzeit einer Benutzerlizenz im Lizenz-Werkzeug (Entscheidung E2)
TEST_TAGE = 30             # Vorgabe-Laufzeit einer Testlizenz
ADMIN_RECHNER_MAX = 3      # Admin-Lizenz: bis zu 3 Rechner (Entscheidung E6)

# Einführung in zwei Stufen: False = Stufe 1 (nur Hinweis, keine Sperre). True = Stufe 2 (Lesemodus ohne gültige
# Lizenz). Geht etwas schief, schaltet ein Update sie wieder aus.
DURCHSETZUNG = False
STICHTAG = ""              # Stufe 1: ab wann eine Lizenz nötig ist (Text im Hinweis), leer = „demnächst“

ORDNER = "Lizenz"
AKTIV = "aktiv.lizenz"
SPERRLISTE = "sperrliste.json"
ZEIT = "zeit.json"
ALT = "alt"
EINSTELLUNG_ZULETZT = "lizenz_zuletzt"
EMAIL = "patrick.brundiers@gmail.com"    # Empfänger der E-Mail „Lizenz anfragen“ im Lizenzdialog


class LizenzFehler(ValueError):
    """Lizenzdatei ungültig (Text für den Benutzer)."""


# ------------------------------------------------------------------ Signatur
def kanonisch(inhalt):
    """Feste Form des Inhalts, die signiert wird: Leerzeichen und Reihenfolge in der Datei ändern nichts."""
    return json.dumps(inhalt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _oeffentlich(text):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    return Ed25519PublicKey.from_public_bytes(base64.b64decode(text))


def oeffentlich_text(privat):
    """Öffentlicher Schlüssel (Base64 der 32 Byte) zu einem privaten Ed25519-Schlüssel."""
    from cryptography.hazmat.primitives import serialization
    return base64.b64encode(privat.public_key().public_bytes(serialization.Encoding.Raw,
                                                             serialization.PublicFormat.Raw)).decode("ascii")


def signieren(inhalt, privat):
    """Signatur (Base64) zum Inhalt; privat: Ed25519PrivateKey (nur im Lizenz-Werkzeug und in den Tests)."""
    return base64.b64encode(privat.sign(kanonisch(inhalt))).decode("ascii")


def signatur_gueltig(inhalt, signatur, schluessel_id, schluessel):
    """True, wenn die Signatur mit dem öffentlichen Schlüssel schluessel_id aus schluessel passt."""
    from cryptography.exceptions import InvalidSignature
    text = (schluessel or {}).get(schluessel_id)
    if not text or not isinstance(signatur, str):
        return False
    try:
        _oeffentlich(text).verify(base64.b64decode(signatur, validate=True), kanonisch(inhalt))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def standard_schluessel():
    from .lizenz_schluessel import SCHLUESSEL
    return SCHLUESSEL


# ------------------------------------------------------------------ Rechner-ID
def _machine_guid():
    if sys.platform == "win32":
        import winreg
        for zugriff in (winreg.KEY_READ | winreg.KEY_WOW64_64KEY, winreg.KEY_READ):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography", 0,
                                    zugriff) as k:
                    return str(winreg.QueryValueEx(k, "MachineGuid")[0])
            except OSError:
                continue
        return ""
    for pfad in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            return Path(pfad).read_text(encoding="ascii").strip()
        except OSError:
            continue
    return ""


def rechner_id(roh=None):
    """Rechner-ID RL-XXXX-XXXX-XXXX-XXXX: SHA-256 von 'rohrlaser|' + MachineGuid (Windows) bzw. /etc/machine-id,
    davon 16 Hexzeichen. Die echte Kennung wird nicht preisgegeben. Leer, wenn sie sich nicht lesen lässt."""
    roh = _machine_guid() if roh is None else roh
    if not roh:
        return ""
    h = hashlib.sha256(("rohrlaser|" + roh.strip().lower()).encode("utf-8")).hexdigest()[:16].upper()
    return "RL-" + "-".join(h[i:i + 4] for i in range(0, 16, 4))


def id_normal(text):
    """Rechner-ID in der Schreibweise RL-XXXX-… (Groß, ohne Leerzeichen), für den Vergleich."""
    return "".join(str(text or "").split()).upper()


# ------------------------------------------------------------------ Lizenzdatei
def _datum(wert, name):
    try:
        return datetime.date.fromisoformat(str(wert))
    except ValueError:
        raise LizenzFehler(f"Feld {name} ist kein Datum ({wert!r}).") from None


def lesen(quelle):
    """Lizenzdatei (Pfad, Text oder dict) als dict; LizenzFehler, wenn es kein JSON-Objekt ist."""
    if isinstance(quelle, dict):
        return quelle
    try:
        text = Path(quelle).read_text(encoding="utf-8-sig") if isinstance(quelle, Path) else str(quelle)
        daten = json.loads(text)
    except OSError as e:
        raise LizenzFehler(f"Lizenzdatei lässt sich nicht lesen: {e}") from None
    except ValueError:
        raise LizenzFehler("Das ist keine Lizenzdatei (kein gültiges JSON).") from None
    if not isinstance(daten, dict):
        raise LizenzFehler("Das ist keine Lizenzdatei.")
    return daten


def pruefen(quelle, schluessel=None):
    """Prüft Aufbau und Signatur einer Lizenzdatei, unabhängig von Datum und Rechner. Ergebnis: Inhalt (dict);
    LizenzFehler mit Begründung, wenn sie ungültig ist."""
    daten = lesen(quelle)
    if "format" not in daten or "inhalt" not in daten:
        raise LizenzFehler("Das ist keine Lizenzdatei (Format oder Inhalt fehlt).")
    if daten.get("format") != FORMAT:
        raise LizenzFehler("Lizenz für eine neuere Programmversion – bitte das Programm aktualisieren.")
    inhalt = daten["inhalt"]
    if not isinstance(inhalt, dict):
        raise LizenzFehler("Lizenzinhalt fehlt.")
    schluessel = standard_schluessel() if schluessel is None else schluessel
    sid = inhalt.get("schluessel_id")
    if sid not in schluessel:
        raise LizenzFehler(f"Lizenz mit unbekanntem Schlüssel {sid!r} – bitte das Programm aktualisieren.")
    if not signatur_gueltig(inhalt, daten.get("signatur"), sid, schluessel):
        raise LizenzFehler("Signatur ungültig: Die Lizenzdatei wurde verändert oder stammt nicht von Patrick.")
    art = inhalt.get("art")
    if art not in ARTEN:
        raise LizenzFehler(f"Unbekannte Lizenzart {art!r}.")
    if not inhalt.get("lizenz_id"):
        raise LizenzFehler("Lizenz-ID fehlt.")
    rechner = inhalt.get("rechner")
    if not isinstance(rechner, list):
        raise LizenzFehler("Feld rechner muss eine Liste sein.")
    if inhalt.get("gueltig_ab"):
        _datum(inhalt["gueltig_ab"], "gueltig_ab")
    bis = inhalt.get("gueltig_bis")
    if art == "admin":
        if not rechner:
            raise LizenzFehler("Eine Admin-Lizenz muss an Rechner gebunden sein.")
        if len(rechner) > ADMIN_RECHNER_MAX:
            raise LizenzFehler(f"Eine Admin-Lizenz gilt für höchstens {ADMIN_RECHNER_MAX} Rechner.")
        if bis:
            _datum(bis, "gueltig_bis")
    else:
        if not bis:
            raise LizenzFehler("Eine Benutzer- oder Testlizenz braucht ein Ablaufdatum.")
        _datum(bis, "gueltig_bis")
    return inhalt


def ist_test(inhalt):
    return bool(inhalt) and (inhalt.get("art") == "test" or bool(inhalt.get("test")))


# ------------------------------------------------------------------ Sperrliste
def sperrliste_pruefen(quelle, schluessel=None):
    """Signierte Sperrliste {"stand": n, "gesperrt": [...], "schluessel_id": "K1", "signatur": "…"}. Ergebnis: dict
    ohne Signatur oder None, wenn sie fehlt oder ungültig ist (eine ungültige Liste zählt nicht)."""
    try:
        daten = lesen(quelle)
    except LizenzFehler:
        return None
    inhalt = {k: v for k, v in daten.items() if k != "signatur"}
    if not isinstance(inhalt.get("stand"), int) or not isinstance(inhalt.get("gesperrt"), list):
        return None
    schluessel = standard_schluessel() if schluessel is None else schluessel
    if not signatur_gueltig(inhalt, daten.get("signatur"), inhalt.get("schluessel_id"), schluessel):
        return None
    return inhalt


def sperrliste_signieren(stand, gesperrt, privat, schluessel_id):
    inhalt = dict(stand=int(stand), gesperrt=sorted(set(gesperrt)), schluessel_id=schluessel_id)
    return dict(inhalt, signatur=signieren(inhalt, privat))


def sperrliste_uebernehmen(ordner, quelle, schluessel=None):
    """Neue Sperrliste speichern, wenn sie gültig ist und einen größeren Stand hat als die vorhandene. Ergebnis:
    True, wenn übernommen. Eine ältere Liste ersetzt nie eine neuere."""
    neu = sperrliste_pruefen(quelle, schluessel)
    if neu is None:
        return False
    alt = sperrliste_pruefen(Path(ordner) / SPERRLISTE, schluessel)
    if alt is not None and alt["stand"] >= neu["stand"]:
        return False
    daten = lesen(quelle)
    _schreiben(Path(ordner) / SPERRLISTE, json.dumps(daten, indent=1, ensure_ascii=False))
    return True


# ------------------------------------------------------------------ Zeit
def spaetestes_datum(ordner, db_wert=None):
    """Spätestes bisher gesehenes Datum aus Lizenz/zeit.json und der Einstellung lizenz_zuletzt (größerer Wert)."""
    werte = []
    try:
        werte.append(datetime.date.fromisoformat(json.loads(
            (Path(ordner) / ZEIT).read_text(encoding="utf-8"))["zuletzt"]))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        if db_wert:
            werte.append(datetime.date.fromisoformat(str(db_wert)))
    except ValueError:
        pass
    return max(werte) if werte else None


def uhr_zurueck(heute, spaetestes):
    """True, wenn heute mehr als UHR_TOLERANZ_TAGE vor dem spätesten gesehenen Datum liegt."""
    return spaetestes is not None and (spaetestes - heute).days > UHR_TOLERANZ_TAGE


def zeit_merken(ordner, heute, spaetestes=None):
    """Spätestes Datum fortschreiben (nie zurück). Ergebnis: das neue späteste Datum (ISO-Text)."""
    neu = max(d for d in (heute, spaetestes) if d is not None)
    try:
        _schreiben(Path(ordner) / ZEIT, json.dumps(dict(zuletzt=neu.isoformat())))
    except OSError:
        pass
    return neu.isoformat()


# ------------------------------------------------------------------ Zustand
@dataclass
class Zustand:
    """Ergebnis von ermitteln(). stufe: admin, gueltig, bald, kulanz, lesemodus. nur_lesen: Grund (Text) oder
    leer. hinweis: Text für Statusleiste/Lizenzdialog, farbe: '', 'gelb', 'rot'."""
    stufe: str
    rechner_id: str = ""
    inhalt: dict = field(default_factory=dict)
    grund: str = ""          # warum keine gültige Lizenz (auch in Stufe 1 ohne Sperre)
    hinweis: str = ""
    farbe: str = ""
    tage_rest: int = None    # bis Ablauf (negativ: abgelaufen seit)
    start_hinweis: bool = False
    durchsetzung: bool = DURCHSETZUNG

    @property
    def admin(self):
        return self.stufe == "admin"

    @property
    def test(self):
        return ist_test(self.inhalt) and self.stufe != "lesemodus"

    @property
    def nur_lesen(self):
        """Grund des Lesemodus oder '' (voller Zugriff)."""
        return self.grund if (self.stufe == "lesemodus" and self.durchsetzung) else ""

    def darf(self, funktion="alle"):
        """True, wenn die Funktion freigeschaltet ist (Lesemodus: nichts Schreibendes). Feld funktionen ist für
        spätere Zusatzmodule vorbereitet; heute gilt immer ['alle']."""
        if self.nur_lesen:
            return False
        if self.stufe == "lesemodus":     # Stufe 1: ohne Lizenz trotzdem alles
            return True
        f = self.inhalt.get("funktionen") or ["alle"]
        return "alle" in f or funktion in f


def _datum_text(d):
    return d.strftime("%d.%m.%Y")


def ermitteln(quelle, heute=None, rechner=None, schluessel=None, sperrliste=None, spaetestes=None,
              durchsetzung=None):
    """Lizenzzustand. quelle: Lizenzdatei (Pfad/Text/dict) oder None (keine Lizenz). heute: datetime.date.
    rechner: Rechner-ID dieses Rechners. sperrliste: geprüfte Sperrliste (dict) oder None. spaetestes: spätestes
    gesehenes Datum (Uhr-Prüfung). durchsetzung: Vorgabe DURCHSETZUNG (Stufe 2)."""
    heute = heute or datetime.date.today()
    rechner = rechner_id() if rechner is None else rechner
    durch = DURCHSETZUNG if durchsetzung is None else durchsetzung

    def lesemodus(grund, inhalt=None):
        if durch:
            hinweis = f"Lesemodus: {grund}"
        else:
            ab = f"Ab {STICHTAG}" if STICHTAG else "Demnächst"
            hinweis = (f"{ab} braucht das Programm eine Lizenz ({grund}). Bitte die Rechner-ID {rechner or '?'} "
                       "an Patrick senden (Hilfe → Lizenz …).")
        return Zustand("lesemodus", rechner, inhalt or {}, grund, hinweis, "rot" if durch else "gelb",
                       start_hinweis=durch, durchsetzung=durch)

    if quelle is None:
        return lesemodus(f"keine Lizenz geladen, Rechner-ID {rechner or 'unbekannt'}")
    try:
        inhalt = pruefen(quelle, schluessel)
    except LizenzFehler as e:
        return lesemodus(str(e).rstrip("."))
    lid = inhalt["lizenz_id"]
    if sperrliste and lid in (sperrliste.get("gesperrt") or []):
        return lesemodus(f"Lizenz {lid} ist gesperrt", inhalt)
    ids = [id_normal(r) for r in inhalt["rechner"]]
    if ids and id_normal(rechner) not in ids:
        return lesemodus(f"Lizenz gilt für eine andere Rechner-ID (dieser Rechner: {rechner or 'unbekannt'})", inhalt)
    if inhalt["art"] == "admin":
        return Zustand("admin", rechner, inhalt, durchsetzung=durch)
    if uhr_zurueck(heute, spaetestes):
        return lesemodus(f"Systemzeit prüfen – das Datum {_datum_text(heute)} liegt vor dem zuletzt gesehenen "
                         f"{_datum_text(spaetestes)}", inhalt)
    ab = inhalt.get("gueltig_ab")
    if ab and heute < datetime.date.fromisoformat(ab):
        return lesemodus(f"Lizenz gilt erst ab {_datum_text(datetime.date.fromisoformat(ab))}", inhalt)
    bis = datetime.date.fromisoformat(inhalt["gueltig_bis"])
    rest = (bis - heute).days
    art = "Testlizenz" if ist_test(inhalt) else "Lizenz"
    if rest > WARNUNG_TAGE:
        return Zustand("gueltig", rechner, inhalt, tage_rest=rest, durchsetzung=durch)
    if rest >= 0:
        return Zustand("bald", rechner, inhalt, hinweis=f"{art} läuft am {_datum_text(bis)} ab (noch {rest} "
                                                          f"Tag{'' if rest == 1 else 'e'}) – bitte verlängern.",
                       farbe="gelb", tage_rest=rest, start_hinweis=rest <= WARNUNG_START_TAGE, durchsetzung=durch)
    lese_ab = bis + datetime.timedelta(days=KULANZ_TAGE + 1)
    if -rest <= KULANZ_TAGE:
        return Zustand("kulanz", rechner, inhalt, hinweis=f"{art} abgelaufen am {_datum_text(bis)}, Lesemodus ab "
                                                            f"{_datum_text(lese_ab)} – bitte verlängern.",
                       farbe="rot", tage_rest=rest, start_hinweis=True, durchsetzung=durch)
    z = lesemodus(f"{art} abgelaufen am {_datum_text(bis)}", inhalt)
    z.tage_rest = rest
    return z


# ------------------------------------------------------------------ Lizenzordner
def ordner(daten):
    """Ordner Lizenz im Datenordner (neben rohrlaser.db, nicht darin: Sicherung und Import nehmen sie nicht mit)."""
    return Path(daten) / ORDNER


def _schreiben(pfad, text):
    pfad = Path(pfad)
    pfad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pfad.with_name(pfad.name + ".neu")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, pfad)


def aktive_lizenz(ordner_):
    """Pfad der geladenen Lizenz oder None."""
    p = Path(ordner_) / AKTIV
    return p if p.is_file() else None


def lizenz_laden(ordner_, quelle, heute=None, rechner=None, schluessel=None):
    """Lizenzdatei übernehmen: erst prüfen (Aufbau, Signatur, Rechner), dann als aktiv.lizenz speichern; die bisherige
    kommt nach alt/. Eine ungültige Datei ersetzt nie eine gültige (LizenzFehler, nichts geändert). Ergebnis: Inhalt."""
    if isinstance(quelle, str) and not quelle.lstrip().startswith("{"):
        quelle = Path(quelle)
    daten = lesen(quelle)
    inhalt = pruefen(daten, schluessel)
    rechner = rechner_id() if rechner is None else rechner
    ids = [id_normal(r) for r in inhalt["rechner"]]
    if ids and id_normal(rechner) not in ids:
        raise LizenzFehler(f"Diese Lizenz gilt für eine andere Rechner-ID (dieser Rechner: {rechner or 'unbekannt'}).")
    if inhalt["art"] != "admin":
        bis = datetime.date.fromisoformat(inhalt["gueltig_bis"])
        if (heute or datetime.date.today()) > bis + datetime.timedelta(days=KULANZ_TAGE):
            raise LizenzFehler(f"Diese Lizenz ist schon am {_datum_text(bis)} abgelaufen.")
    o = Path(ordner_)
    vorher = aktive_lizenz(o)
    if vorher:
        (o / ALT).mkdir(parents=True, exist_ok=True)
        stempel = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        shutil.copy2(vorher, o / ALT / f"{stempel}.lizenz")
    _schreiben(o / AKTIV, json.dumps(daten, indent=1, ensure_ascii=False))
    return inhalt


def zustand_im_ordner(ordner_, heute=None, rechner=None, schluessel=None, db_zuletzt=None, durchsetzung=None,
                      merken=True):
    """Zustand für einen Datenordner: aktive Lizenz, gespeicherte Sperrliste, Uhr-Prüfung. merken: spätestes Datum
    fortschreiben (nur befristete Lizenzen werten es aus). Ergebnis: (Zustand, neues spätestes Datum als Text)."""
    heute = heute or datetime.date.today()
    o = Path(ordner_)
    spaet = spaetestes_datum(o, db_zuletzt)
    aktiv = aktive_lizenz(o)
    z = ermitteln(aktiv, heute, rechner, schluessel, sperrliste_pruefen(o / SPERRLISTE, schluessel), spaet,
                  durchsetzung)
    neu = None
    if merken and not uhr_zurueck(heute, spaet):
        neu = zeit_merken(o, heute, spaet)
    return z, neu


class LizenzStelle:
    """Lizenz eines laufenden Programms: Ordner Lizenz im Datenordner und die Datendatei (Einstellung
    lizenz_zuletzt, Lesemodus). pruefen() ermittelt den Zustand und schaltet den Lesemodus der Datenbank."""

    def __init__(self, ordner_, db=None, schluessel=None, rechner=None, durchsetzung=None):
        self.ordner = Path(ordner_)
        self.db = db
        self.schluessel = schluessel
        self.rechner = rechner_id() if rechner is None else rechner
        self.durchsetzung = durchsetzung
        self.zustand = None

    def pruefen(self, heute=None):
        db_wert = self.db.einstellung(EINSTELLUNG_ZULETZT) if self.db is not None else None
        z, neu = zustand_im_ordner(self.ordner, heute, self.rechner, self.schluessel, db_wert, self.durchsetzung)
        if self.db is not None:
            if self.db.nur_lesen:
                self.db.lesemodus("")
            if neu and neu != db_wert:
                self.db.einstellung_setzen(EINSTELLUNG_ZULETZT, neu)
            self.db.lesemodus(z.nur_lesen)
        self.zustand = z
        return z

    def laden(self, quelle, heute=None):
        """Lizenzdatei übernehmen (LizenzFehler, wenn ungültig; dann bleibt alles, wie es war) und neu prüfen."""
        lizenz_laden(self.ordner, quelle, heute, self.rechner, self.schluessel)
        return self.pruefen(heute)

    def sperrliste(self, quelle):
        """Sperrliste vom Update-Check übernehmen (nur gültig signiert und neuer). Ergebnis: True = übernommen."""
        if sperrliste_uebernehmen(self.ordner, quelle, self.schluessel):
            self.pruefen()
            return True
        return False

    def zeit_abgleich(self, datum):
        """Datum des Update-Servers als zusätzlicher Zeitstempel (nie zurück). Liegt die Rechneruhr danach mehr als
        UHR_TOLERANZ_TAGE davor, meldet die nächste Prüfung „Systemzeit prüfen“. Ergebnis: neuer Zustand."""
        if not datum:
            return self.zustand
        db_wert = self.db.einstellung(EINSTELLUNG_ZULETZT) if self.db is not None else None
        neu = zeit_merken(self.ordner, datum, spaetestes_datum(self.ordner, db_wert))
        if self.db is not None and neu != db_wert and not self.db.nur_lesen:
            self.db.einstellung_setzen(EINSTELLUNG_ZULETZT, neu)
        return self.pruefen()

    def text(self):
        """Kurzbeschreibung für Hilfe → Über … und --info."""
        z = self.zustand or self.pruefen()
        i = z.inhalt
        if z.stufe == "admin":
            return f"Admin-Lizenz {i.get('lizenz_id')} ({i.get('inhaber')}), unbefristet"
        if i and z.stufe != "lesemodus":
            art = "Testlizenz" if z.test else "Lizenz"
            wer = ", ".join(x for x in (i.get("inhaber"), i.get("firma")) if x)
            return f"{art} {i.get('lizenz_id')} ({wer}), gültig bis {_datum_text(datetime.date.fromisoformat(i['gueltig_bis']))}"
        return ("Lesemodus: " if z.nur_lesen else "Keine gültige Lizenz: ") + z.grund
