"""Signatur der Admin-Vorgaben (Systemprüfung 17.11.2026, Befunde SEC-01 und SEC-02).

Die Admin-Vorgaben (admin_schutz.py, Datei Admin/admin_vorgaben.json im gemeinsamen Ordner) tragen alles, was nur
ein Admin ändern darf: Admin-Passwort, Admin-Liste, Rollen, Schutzliste und die Werte der geschützten Seiten
(Gewinn, Zuschläge, Preise, Maschinen …). Bis 0.9.373 schützte sie nur eine Prüfsumme; jeder mit Schreibrecht im
Ordner konnte sie fälschen. Jetzt ist jedes Paket mit Ed25519 signiert:

- **Hauptadmin**: mit dem privaten Admin-Schlüssel aus dem Tresor seiner Hauptadmin-Lizenz (hauptadmin.py). Das
  Paket trägt den signierten Inhalt dieser Lizenz (ohne Tresor) als Anker mit. Jeder Platz prüft den Anker mit dem
  eingebauten öffentlichen Lizenzschlüssel und damit den Admin-Schlüssel, mit dem das Paket signiert ist.
- **Weiterer Admin** (Kürzel): mit einem Schlüssel aus seinem Passwort (scrypt mit eigenem Salz). Sein öffentlicher
  Schlüssel steht in der Admin-Liste, die nur der Hauptadmin ändern darf. Ein Paket eines weiteren Admins darf
  Rechte (Admin-Liste außer dem eigenen Passwort, Schutzliste, Rollen, Admin-Passwort) nicht ändern.

Übergang: Ein Platz, der noch nie ein gültig signiertes Paket gesehen hat, nimmt unsignierte Pakete wie bisher an
(ältere Programmversionen, Betrieb ohne Hauptadmin-Lizenz). Ab dem ersten gültig signierten Paket merkt er sich das
(Einstellung GEMERKT, nur an diesem Platz) und lehnt unsignierte oder falsch signierte Pakete ab.

Ohne Qt; nur lizenz (Ed25519, kanonisches JSON) und cryptography.
"""
import base64
import os

from . import lizenz as L

GEMERKT = "admin_vorgaben_signiert"     # lokal: {lizenz_id, seit} – ab hier nur noch signierte Pakete
HAUPT, ADMIN = "hauptadmin", "admin"
KDF = dict(n=2 ** 14, r=8, p=1)         # Admin-Schlüssel aus dem Passwort: etwa 0,05 s je Ableitung
# Werte, die nur der Hauptadmin ändert (ein weiterer Admin nur sein eigenes Passwort in der Admin-Liste)
RECHTE = ("passwort", "admin_seiten", "admin_liste", "benutzer_rollen", "rollen_rechte", "anmeldung_pflicht")
EIGENE_FELDER = ("hash", "neu", "stand", "salz", "pub")


class Schluessel:
    """Signaturschlüssel einer Admin-Sitzung: art HAUPT (seed aus dem Tresor, anker = signierter Lizenzinhalt) oder
    ADMIN (seed aus dem Passwort, kuerzel)."""

    def __init__(self, art, seed, anker=None, kuerzel=""):
        self.art, self.seed, self.anker, self.kuerzel = art, bytes(seed), anker, kuerzel

    def oeffentlich(self):
        return L.oeffentlich_text(_privat(self.seed))

    def __repr__(self):           # nie den Schlüssel ausgeben (Protokoll, Fehlermeldungen)
        return f"Schluessel({self.art}, {self.kuerzel or '-'})"


def _privat(seed):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(seed)


def hauptadmin_schluessel(daten, seed):
    """Schlüssel des Hauptadmins aus der geprüften Hauptadmin-Datei (hauptadmin.pruefen) und dem Seed aus
    hauptadmin.tresor_oeffnen."""
    return Schluessel(HAUPT, seed, anker=dict(inhalt=daten["inhalt"], signatur=daten["signatur"]))


def admin_seed(passwort, salz_hex, kdf=None):
    """32 Byte aus Passwort und Salz (scrypt)."""
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    k = kdf or KDF
    return Scrypt(salt=bytes.fromhex(salz_hex), length=32, n=k["n"], r=k["r"], p=k["p"]).derive(
        str(passwort).encode("utf-8"))


def admin_eintrag(passwort, kdf=None):
    """Neues Salz und öffentlicher Schlüssel für einen weiteren Admin: dict(salz, pub)."""
    salz = os.urandom(16).hex()
    return dict(salz=salz, pub=L.oeffentlich_text(_privat(admin_seed(passwort, salz, kdf))))


def admin_schluessel(kuerzel, passwort, eintrag, kdf=None):
    """Schlüssel eines weiteren Admins oder None (Eintrag ohne Salz/öffentlichen Schlüssel = vor 0.9.374 angelegt,
    oder Passwort passt nicht zum Schlüssel)."""
    if not eintrag or not eintrag.get("salz") or not eintrag.get("pub"):
        return None
    try:
        s = Schluessel(ADMIN, admin_seed(passwort, eintrag["salz"], kdf), kuerzel=kuerzel)
    except (ValueError, TypeError):
        return None
    return s if s.oeffentlich() == eintrag["pub"] else None


def _was(p):
    """Signierter Teil des Pakets: Kopf und Prüfsumme (die Prüfsumme deckt den Inhalt)."""
    return {k: p.get(k) for k in ("format", "stand", "von", "version", "schema", "hash")}


def signieren(p, schluessel):
    """Signatur ins Paket p eintragen (p wird verändert und zurückgegeben)."""
    sig = dict(art=schluessel.art, kuerzel=schluessel.kuerzel)
    if schluessel.art == HAUPT:
        sig["anker"] = schluessel.anker
    sig["wert"] = base64.b64encode(_privat(schluessel.seed).sign(L.kanonisch(dict(_was(p), signatur=dict(
        art=sig["art"], kuerzel=sig["kuerzel"]))))).decode("ascii")
    p["signatur"] = sig
    return p


def _gueltig(pub_text, wert, p, sig):
    from cryptography.exceptions import InvalidSignature
    try:
        L._oeffentlich(pub_text).verify(base64.b64decode(wert, validate=True), L.kanonisch(dict(_was(p), signatur=dict(
            art=sig.get("art"), kuerzel=sig.get("kuerzel")))))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def anker_pruefen(anker, schluessel=None):
    """Signierter Inhalt einer Hauptadmin-Lizenz: (inhalt, '') oder (None, Grund)."""
    if not isinstance(anker, dict) or not isinstance(anker.get("inhalt"), dict):
        return None, "ohne Hauptadmin-Lizenz"
    inhalt = anker["inhalt"]
    if inhalt.get("art") != HAUPT or inhalt.get("rechner") != []:
        return None, "Anker ist keine Hauptadmin-Lizenz"
    schluessel = L.standard_schluessel() if schluessel is None else schluessel
    if not L.signatur_gueltig(inhalt, anker.get("signatur"), inhalt.get("schluessel_id"), schluessel):
        return None, "Hauptadmin-Lizenz im Paket ist nicht von Patrick signiert"
    return inhalt, ""


def pruefen(p, admins_hier, rechte_hier, lizenz_schluessel=None, gesperrt=()):
    """Signatur eines Pakets prüfen. admins_hier: Admin-Liste dieses Platzes (zuletzt angenommener Stand);
    rechte_hier: {Name: Wert} der RECHTE an diesem Platz (Rohwerte wie in der Tabelle einstellungen); gesperrt:
    gesperrte oder ersetzte Lizenz-IDs dieses Rechners. Ergebnis: (art, wer, grund): art HAUPT/ADMIN bei gültiger
    Signatur, None ohne oder mit ungültiger Signatur (grund sagt warum; grund '' = ohne Signatur)."""
    sig = p.get("signatur")
    if not sig:
        return None, "", ""
    if not isinstance(sig, dict) or not isinstance(sig.get("wert"), str):
        return None, "", "Signatur unlesbar"
    if sig.get("art") == HAUPT:
        inhalt, grund = anker_pruefen(sig.get("anker"), lizenz_schluessel)
        if inhalt is None:
            return None, "", grund
        if inhalt.get("lizenz_id") in set(gesperrt or ()):
            return None, "", f"Hauptadmin-Lizenz {inhalt.get('lizenz_id')} ist gesperrt oder ersetzt"
        if not _gueltig(str(inhalt.get("admin_schluessel") or ""), sig["wert"], p, sig):
            return None, "", "Signatur des Hauptadmins passt nicht"
        return HAUPT, str(inhalt.get("lizenz_id") or ""), ""
    if sig.get("art") == ADMIN:
        k = str(sig.get("kuerzel") or "")
        e = (admins_hier or {}).get(k) or {}
        if e.get("recht") != ADMIN or not e.get("pub"):
            return None, k, f"{k or '?'} ist hier kein Admin mit Signaturschlüssel"
        if not _gueltig(e["pub"], sig["wert"], p, sig):
            return None, k, f"Signatur von Admin {k} passt nicht"
        grund = _nur_eigenes(p, k, admins_hier, rechte_hier)
        if grund:
            return None, k, grund
        return ADMIN, k, ""
    return None, "", "Signatur unbekannter Art"


def _nur_eigenes(p, k, admins_hier, rechte_hier):
    """Ein weiterer Admin darf an den Rechten nur sein eigenes Passwort ändern. Ergebnis: Grund oder ''."""
    import json
    einst = (p.get("inhalt") or {}).get("einstellungen") or {}
    for name in RECHTE:
        if name == "admin_liste" or name not in einst:
            continue
        if einst.get(name) != (rechte_hier or {}).get(name, einst.get(name)):
            return f"Admin {k} darf „{name}“ nicht ändern (nur der Hauptadmin)"
    if "admin_liste" in einst:
        try:
            neu = json.loads(einst["admin_liste"]) or {}
        except (TypeError, ValueError):
            return "Admin-Liste unlesbar"
        alt = {kk: dict(v) for kk, v in (admins_hier or {}).items()}
        for kk in set(neu) | set(alt):
            a, n = dict(alt.get(kk) or {}), dict(neu.get(kk) or {})
            if kk == k:
                for f in EIGENE_FELDER:
                    a.pop(f, None)
                    n.pop(f, None)
            if a != n:
                return f"Admin {k} darf die Admin-Liste nicht ändern (nur der Hauptadmin)"
    return ""
