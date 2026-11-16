"""Benutzer, Rollen und Rechte (Plan Auftragsworkflow 13.11.2026, Paket 6; F4a: Anmeldung mit Kürzel und Passwort,
Werkstatt mit kurzer PIN). Ohne Qt.

Benutzer sind die Kürzel der Mitarbeiter (wie im gemeinsamen Ordner). Der Administrator vergibt je Benutzer eine oder
mehrere Rollen und ein Passwort oder eine PIN (Einstellungen → Benutzer und Rollen, nur Hauptadmin). Die Rechtetabelle
legt je Rolle und Bereich fest: kein Zugriff, sehen oder bearbeiten. Mehrere Rollen: es gilt das höchste Recht.

Benutzerliste (BENUTZER), Rechtetabelle (RECHTE) und die Anmeldepflicht gehen wie die Admin-Liste mit den
Admin-Vorgaben an alle Arbeitsplätze (admin_schutz.einstellungen_geschuetzt); ohne Admin-Passwort mit dem normalen
Abgleich der Einstellungen.

Solange niemand eine Rolle hat, ist die Benutzerverwaltung aus und alles bleibt wie bisher (jeder darf alles). Ist sie
an, gilt für den angemeldeten Benutzer (sonst das Kürzel dieses Arbeitsplatzes) seine Rollen; wer keine Rolle hat,
darf nur sehen. Ein freigeschalteter Admin (Admin-Schutz) darf immer alles, damit sich niemand aussperrt.

Passwörter und PINs liegen nur als gesalzener, langsamer Hash vor (passwort.py). Nach FEHL_FREI Fehlversuchen wartet
die Anmeldung SPERRE_S Sekunden.
"""
import datetime
import time

from . import passwort as pw

BENUTZER = "benutzer_rollen"            # {Kürzel: {name, rollen: [...], hash, pin, aktiv, stand}}
RECHTE = "rollen_rechte"                # {Rolle: {Bereich: Stufe}}; leer = VORGABE
PFLICHT = "anmeldung_pflicht"           # ja: beim Start anmelden (nur wenn die Benutzerverwaltung an ist)

ADMIN, KALKULATION, AV, LEITUNG, WERKSTATT, QS, VERSAND = (
    "admin", "kalkulation", "av", "leitung", "werkstatt", "qs", "versand")
ROLLEN = ((ADMIN, "Administrator"), (KALKULATION, "Kalkulation"), (AV, "Arbeitsvorbereitung"),
          (LEITUNG, "Produktionsleitung"), (WERKSTATT, "Mitarbeiter Produktion"), (QS, "Qualitätskontrolle"),
          (VERSAND, "Versand"))
ROLLE_TITEL = dict(ROLLEN)

B_ANGEBOTE, B_AUFTRAEGE, B_AV, B_PRODUKTION, B_QS, B_VERSAND, B_AUSWERTUNG = (
    "angebote", "auftraege", "av", "produktion", "qs", "versand", "auswertung")
BEREICHE = ((B_ANGEBOTE, "Angebote und Kalkulation"), (B_AUFTRAEGE, "Aufträge"), (B_AV, "Arbeitsvorbereitung"),
            (B_PRODUKTION, "Produktion und Rückmeldung"), (B_QS, "Qualitätskontrolle"),
            (B_VERSAND, "Auslieferung und Versand"), (B_AUSWERTUNG, "Auswertungen"))
BEREICH_TITEL = dict(BEREICHE)

KEIN, SEHEN, BEARBEITEN = "", "sehen", "bearbeiten"
STUFEN = ((KEIN, "–"), (SEHEN, "sehen"), (BEARBEITEN, "bearbeiten"))
_RANG = {KEIN: 0, SEHEN: 1, BEARBEITEN: 2}

_S, _B, _K = SEHEN, BEARBEITEN, KEIN
# Vorgabe je Rolle in der Reihenfolge von BEREICHE: Angebote, Aufträge, AV, Produktion, QS, Versand, Auswertungen
_VORGABE = {ADMIN: (_B, _B, _B, _B, _B, _B, _B),
            KALKULATION: (_B, _B, _S, _S, _S, _S, _S),
            AV: (_S, _B, _B, _B, _S, _S, _S),
            LEITUNG: (_S, _B, _B, _B, _B, _B, _B),
            WERKSTATT: (_K, _S, _K, _B, _K, _K, _K),
            QS: (_K, _S, _S, _S, _B, _S, _S),
            VERSAND: (_K, _S, _K, _S, _S, _B, _K)}
VORGABE = {r: dict(zip((b for b, _ in BEREICHE), w)) for r, w in _VORGABE.items()}

PASSWORT_MIN = 6
PIN_MIN, PIN_MAX = 4, 8
FEHL_FREI = 5
SPERRE_S = 30


class RechteFehler(ValueError):
    """Keine Berechtigung (Text für den Benutzer)."""


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ------------------------------------------------------------------ Daten
def benutzer(db):
    """{Kürzel: {name, rollen, hash, pin, aktiv, stand}}."""
    return {k: dict(v) for k, v in (db.einstellung(BENUTZER) or {}).items() if isinstance(v, dict)}


def rechte(db):
    """Rechtetabelle {Rolle: {Bereich: Stufe}} (fehlende Werte aus der Vorgabe)."""
    gespeichert = db.einstellung(RECHTE) or {}
    return {r: {b: (gespeichert.get(r) or {}).get(b, VORGABE[r][b]) for b, _ in BEREICHE} for r, _ in ROLLEN}


def aktiv(db):
    """Benutzerverwaltung an: mindestens ein aktiver Benutzer hat eine Rolle."""
    return db is not None and any(u.get("rollen") and u.get("aktiv", True) for u in benutzer(db).values())


def pflicht(db):
    """Beim Start anmelden? Nur wenn die Benutzerverwaltung an ist und jemand ein Passwort oder eine PIN hat."""
    return aktiv(db) and db.einstellung(PFLICHT) != "nein" and any(
        u.get("hash") or u.get("pin") for u in benutzer(db).values())


def benutzer_setzen(db, kuerzel, name="", rollen=(), aktiv_=True):
    """Benutzer anlegen oder ändern (Kürzel, Name, Rollen, aktiv). Ergebnis: Fehlertext oder ''."""
    from .teilen import kuerzel_sauber
    k = kuerzel_sauber(kuerzel)
    if not k:
        return "Bitte ein Kürzel angeben (bis 5 Buchstaben oder Ziffern)."
    falsch = [r for r in rollen if r not in ROLLE_TITEL]
    if falsch:
        return f"Rolle „{falsch[0]}“ gibt es nicht."
    liste = benutzer(db)
    e = dict(liste.get(k) or {})
    e.update(name=str(name or e.get("name") or "").strip(), rollen=[r for r, _ in ROLLEN if r in rollen],
             aktiv=bool(aktiv_), stand=_jetzt())
    liste[k] = e
    db.einstellung_setzen(BENUTZER, liste)
    return ""


def entfernen(db, kuerzel):
    liste = benutzer(db)
    if liste.pop(kuerzel, None) is None:
        return "Den Benutzer gibt es nicht."
    db.einstellung_setzen(BENUTZER, liste)
    return ""


def zugang_setzen(db, kuerzel, passwort=None, pin=None):
    """Passwort und/oder PIN setzen ('' entfernt). Ergebnis: Fehlertext oder ''."""
    liste = benutzer(db)
    if kuerzel not in liste:
        return "Den Benutzer gibt es nicht."
    e = liste[kuerzel]
    if passwort is not None:
        if passwort and len(passwort) < PASSWORT_MIN:
            return f"Das Passwort braucht mindestens {PASSWORT_MIN} Zeichen."
        e["hash"] = pw.hash_bilden(passwort) if passwort else ""
    if pin is not None:
        if pin and (not pin.isdigit() or not PIN_MIN <= len(pin) <= PIN_MAX):
            return f"Die PIN besteht aus {PIN_MIN} bis {PIN_MAX} Ziffern."
        e["pin"] = pw.hash_bilden(pin) if pin else ""
    e["stand"] = _jetzt()
    db.einstellung_setzen(BENUTZER, liste)
    return ""


def recht_setzen(db, rolle, bereich, stufe):
    if rolle not in ROLLE_TITEL or bereich not in BEREICH_TITEL or stufe not in _RANG:
        return "Unbekannte Rolle, Bereich oder Stufe."
    if rolle == ADMIN and stufe != BEARBEITEN:
        return "Der Administrator darf immer alles."
    gespeichert = dict(db.einstellung(RECHTE) or {})
    gespeichert[rolle] = dict(gespeichert.get(rolle) or {}, **{bereich: stufe})
    db.einstellung_setzen(RECHTE, gespeichert)
    return ""


def vorgabe_wiederherstellen(db):
    db.einstellung_setzen(RECHTE, {})


# ------------------------------------------------------------------ Anmeldung
class Sitzung:
    """Angemeldeter Benutzer dieses Programmfensters ('' = Kürzel des Arbeitsplatzes)."""

    def __init__(self, uhr=time.monotonic):
        self.uhr = uhr
        self.kuerzel = ""
        self.fehl = 0
        self.gesperrt_bis = 0.0


SITZUNG = None          # Sitzung des Hauptfensters (ohne Fenster: Kürzel des Arbeitsplatzes)


def anmelden(db, kuerzel, geheim, sitzung=None):
    """Mit Kürzel und Passwort oder PIN anmelden. Ergebnis: Fehlertext oder '' (angemeldet)."""
    s = sitzung if sitzung is not None else SITZUNG
    if s is not None and s.uhr() < s.gesperrt_bis:
        return f"Zu viele Fehlversuche. Bitte {int(s.gesperrt_bis - s.uhr()) + 1} Sekunden warten."
    from .teilen import kuerzel_sauber
    k = kuerzel_sauber(kuerzel)
    e = benutzer(db).get(k)
    ok = bool(e) and e.get("aktiv", True) and bool(geheim) and any(
        e.get(f) and pw.pruefen(geheim, e[f]) for f in ("hash", "pin"))
    if not ok:
        if s is not None:
            s.fehl += 1
            if s.fehl >= FEHL_FREI:
                s.gesperrt_bis, s.fehl = s.uhr() + SPERRE_S, 0
        if e and not e.get("aktiv", True):
            return "Dieser Benutzer ist gesperrt."
        return "Kürzel oder Passwort/PIN stimmt nicht."
    if s is not None:
        s.kuerzel, s.fehl = k, 0
    return ""


def abmelden(sitzung=None):
    s = sitzung if sitzung is not None else SITZUNG
    if s is not None:
        s.kuerzel = ""


def angemeldet(db, sitzung=None):
    """Kürzel, für das die Rechte gelten: angemeldeter Benutzer, sonst das Kürzel dieses Arbeitsplatzes."""
    s = sitzung if sitzung is not None else SITZUNG
    if s is not None and s.kuerzel:
        return s.kuerzel
    from .teilen import kuerzel
    return kuerzel(db)


def name(db, sitzung=None):
    k = angemeldet(db, sitzung)
    return (benutzer(db).get(k) or {}).get("name") or k


# ------------------------------------------------------------------ Rechte
def _admin_frei(db):
    from . import admin_schutz
    return admin_schutz.aktiv(db) and admin_schutz.ist_admin(db)


def stufe(db, bereich, kuerzel=None, sitzung=None):
    """Recht des Benutzers im Bereich: KEIN, SEHEN oder BEARBEITEN."""
    if not aktiv(db) or _admin_frei(db):
        return BEARBEITEN
    k = kuerzel or angemeldet(db, sitzung)
    e = benutzer(db).get(k)
    if not e or not e.get("aktiv", True) or not e.get("rollen"):
        return SEHEN                     # unbekannt oder ohne Rolle: nur ansehen
    t = rechte(db)
    return max((t[r][bereich] for r in e["rollen"] if r in t), key=_RANG.get, default=SEHEN)


def darf(db, bereich, aktion=BEARBEITEN, kuerzel=None, sitzung=None):
    return _RANG[stufe(db, bereich, kuerzel, sitzung)] >= _RANG[aktion]


def pruefen(db, bereich, aktion=BEARBEITEN, fehler=RechteFehler):
    """Fehler (fehler-Klasse), wenn der Benutzer im Bereich nicht darf."""
    if darf(db, bereich, aktion):
        return
    raise fehler(f"Keine Berechtigung: {BEREICH_TITEL[bereich]} {'bearbeiten' if aktion == BEARBEITEN else 'sehen'} "
                 f"darf {name(db) or 'dieser Arbeitsplatz'} nicht. Rechte vergibt der Administrator (Einstellungen → "
                 "Benutzer und Rollen).")


def uebersicht(db):
    """Zeilen für die Seite Benutzer und Rollen: bekannte Kürzel (gemeinsamer Ordner) und angelegte Benutzer:
    [dict(kuerzel, name, rollen, passwort, pin, aktiv, angelegt)] nach Name."""
    from . import teilen
    liste = benutzer(db)
    alle = {}
    for k, m in teilen.mitarbeiter(db).items():
        alle[k] = dict(kuerzel=k, name=(m or {}).get("name") or "", rollen=[], passwort=False, pin=False, aktiv=True,
                       angelegt=False)
    for k, e in liste.items():
        alle[k] = dict(kuerzel=k, name=e.get("name") or (alle.get(k) or {}).get("name") or "",
                       rollen=list(e.get("rollen") or ()), passwort=bool(e.get("hash")), pin=bool(e.get("pin")),
                       aktiv=e.get("aktiv", True), angelegt=True)
    return sorted(alle.values(), key=lambda z: (z["name"] or z["kuerzel"]).lower())
