"""Zugangssystem Paket B: Datenbanktabellen zg_*, Benutzerkonten im neuen Format und die Migration (Schema 109).

Wo was liegt (vorhandene Architektur hat Vorrang, Abschnitt 13 des Auftrags):

- **Benutzerkonten** bleiben in der Einstellung ``benutzer_rollen``. Sie kommt als signierte Admin-Vorgabe
  (admin_signatur.py, Ed25519) über den gemeinsamen Ordner an jeden Platz; nur so sind sie bei PostgreSQL je PC an
  allen Plätzen gleich und fälschungssicher. Eine eigene Tabelle ``zg_benutzer`` je PC würde sich nicht abgleichen
  und wäre eine zweite, auseinanderlaufende Benutzerliste. Neu ist je Konto der Teil ``zg``
  (rollen, plus, minus, status, totp, passwort_aendern, minuten, id). Ältere Programmversionen lesen ihn nicht und
  arbeiten mit ``rollen`` (alte Rollennamen) weiter, solange noch nicht alle Plätze aktualisiert sind.
- **Konten ohne Teil zg** (alle aus der Zeit vor 0.9.553) werden beim Lesen umgerechnet: aus den alten Rollen und der
  alten Rechtetabelle (Bereich: sehen/bearbeiten) ergibt sich die Menge der Einzelrechte; Grundrolle plus
  Zusatzrechte minus entzogene Rechte ergeben genau diese Menge. Niemand bekommt mehr oder weniger als vorher.
  Die Umrechnung ändert die signierte Vorgabe nicht (das darf nur ein Admin); gespeichert wird das neue Format beim
  nächsten Speichern durch einen Admin.
- **In der Datenbank** (je PC; im Serverbetrieb gemeinsam am Server, nicht über den Ordner abgeglichen): ``zg_installation`` (diese Installation),
  ``zg_arbeitsplaetze``, ``zg_konto_stand`` (Fehlversuche, Sperre, letzter Einmalcode, letzte Anmeldung je Konto),
  ``zg_sitzungen`` (nur der SHA-256 des Tokens, nie das Token), ``zg_anmeldeversuche`` (ohne eingegebenes Passwort),
  ``zg_protokoll`` (Sicherheitsprotokoll, bereinigt) und ``zg_migration`` (Bericht der Umstellung).
- **Rechte und Rollen** stehen als Katalog im Programm (zugang_berechtigung.py), nicht in einer Tabelle: eine
  Tabellenkopie wäre eine zweite Quelle. Vom Admin angepasste Rollen folgen in Paket D als signierte Vorgabe.
- **Lizenzen** bleiben in den signierten Lizenzdateien (lizenz.py, aktivierung.py); Paket E ordnet sie zu.

Migration: Datenbank._anlegen sichert vor jedem Schema-Sprung (Sicherung ``vor_Schema_109``, geprüft mit
datei_pruefen; scheitert die Sicherung, bricht der Start ab und nichts wird umgestellt). Danach legt einrichten() die
Tabellen an und migrieren() schreibt den Bericht. Geschäftstabellen werden nicht verändert. Zurück geht es mit der
alten Programmversion und der Sicherung ``vor_Schema_109`` (Einstellungen → Datensicherung → Wiederherstellen).
Ohne Qt.
"""
import datetime
import hashlib
import json
import time

from . import protokoll as _protokoll
from . import zugang_berechtigung as B
from . import zugang_protokoll as P

SCHEMA = 109
BENUTZER = "benutzer_rollen"
TEIL = "zg"                                   # neues Format je Konto in benutzer_rollen
STATUS = ("aktiv", "gesperrt", "deaktiviert")

INSTALLATION, ARBEITSPLAETZE, KONTO_STAND, SITZUNGEN, VERSUCHE, PROTOKOLL, MIGRATION = (
    "zg_installation", "zg_arbeitsplaetze", "zg_konto_stand", "zg_sitzungen", "zg_anmeldeversuche", "zg_protokoll",
    "zg_migration")
TABELLEN = (INSTALLATION, ARBEITSPLAETZE, KONTO_STAND, SITZUNGEN, VERSUCHE, PROTOKOLL, MIGRATION)

# Sperre nach Fehlversuchen: wie die Hauptadmin-Anmeldung (hauptadmin.py)
FEHL_FREI, SPERRE_ERSTE_S, SPERRE_MAX_S = 5, 60, 3600
PROTOKOLL_MAX = 200_000                       # ältere Einträge räumt aufraeumen() weg


def einrichten(con):
    con.execute(f"CREATE TABLE IF NOT EXISTS {INSTALLATION} (id INTEGER PRIMARY KEY, kennung TEXT UNIQUE, "
                "name TEXT, umgebung TEXT, art TEXT, angelegt TEXT, geaendert TEXT)")
    con.execute(f"CREATE TABLE IF NOT EXISTS {ARBEITSPLAETZE} (id INTEGER PRIMARY KEY, platz TEXT UNIQUE, "
                "name TEXT, installation TEXT, geraet_pub TEXT, status TEXT, zuerst TEXT, zuletzt TEXT, "
                "version TEXT)")
    con.execute(f"CREATE TABLE IF NOT EXISTS {KONTO_STAND} (kuerzel TEXT PRIMARY KEY, fehl INTEGER, "
                "sperre_bis REAL, totp_zuletzt INTEGER, letzte_anmeldung TEXT, letzter_platz TEXT)")
    con.execute(f"CREATE TABLE IF NOT EXISTS {SITZUNGEN} (id INTEGER PRIMARY KEY, token_sha TEXT UNIQUE, "
                "benutzer TEXT, kuerzel TEXT, entwickler INTEGER, installation TEXT, platz TEXT, beginn TEXT, "
                "letzte TEXT, ende TEXT, grund TEXT)")
    con.execute(f"CREATE TABLE IF NOT EXISTS {VERSUCHE} (id INTEGER PRIMARY KEY, zeit TEXT, kuerzel TEXT, "
                "platz TEXT, ergebnis TEXT)")
    con.execute(f"CREATE TABLE IF NOT EXISTS {PROTOKOLL} (id INTEGER PRIMARY KEY, zeit TEXT, aktion TEXT, "
                "benutzer TEXT, installation TEXT, platz TEXT, objekt TEXT, ergebnis TEXT, details TEXT)")
    con.execute(f"CREATE TABLE IF NOT EXISTS {MIGRATION} (id INTEGER PRIMARY KEY, zeit TEXT, von INTEGER, "
                "nach INTEGER, version TEXT, sicherung TEXT, bericht TEXT, status TEXT)")
    con.execute(f"CREATE INDEX IF NOT EXISTS {PROTOKOLL}_zeit ON {PROTOKOLL} (zeit)")
    con.execute(f"CREATE INDEX IF NOT EXISTS {VERSUCHE}_kuerzel ON {VERSUCHE} (kuerzel, zeit)")


def _jetzt():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _ausfuehren(db, sql, werte=()):
    """Schreiben, das den Ablauf nie abbricht (nur-Lesen-Modus, Server ohne Schreibrecht): Ergebnis True/False."""
    if getattr(db, "nur_lesen", ""):
        return False
    try:
        with db.con:
            db.con.execute(sql, werte)
        return True
    except Exception as e:          # noqa: BLE001 – Zugangsdaten dürfen die Anmeldung nie verhindern
        _protokoll.warnung(f"Zugangsdaten: {sql.split('(')[0][:60]} fehlgeschlagen ({e})")
        return False


# ------------------------------------------------------------------ Installation und Arbeitsplatz
def installation(db, umgebung=None):
    """Diese Installation: dict(kennung, name, umgebung, art). kennung = vorhandene Kennung dieses Datenstands
    (teilen.installation, einmal zufällig vergeben). art: 'server' (zentrale Datenbank) oder 'lokal'."""
    from . import teilen
    kennung = teilen.installation(db)
    art = "server" if getattr(db, "server", None) is not None else "lokal"
    z = db.con.execute(f"SELECT name, umgebung, art FROM {INSTALLATION} WHERE kennung=?", (kennung,)).fetchone()
    if z is None or (umgebung and z[1] != umgebung) or z[2] != art:
        u = umgebung or (z[1] if z else None) or "produktiv"
        name = (z[0] if z else "") or ""
        if z is None:
            _ausfuehren(db, f"INSERT INTO {INSTALLATION} (kennung, name, umgebung, art, angelegt, geaendert) "
                        "VALUES (?, ?, ?, ?, ?, ?)", (kennung, name, u, art, _jetzt(), _jetzt()))
        else:
            _ausfuehren(db, f"UPDATE {INSTALLATION} SET umgebung=?, art=?, geaendert=? WHERE kennung=?",
                        (u, art, _jetzt(), kennung))
        return dict(kennung=kennung, name=name, umgebung=u, art=art)
    return dict(kennung=kennung, name=z[0] or "", umgebung=z[1] or "produktiv", art=z[2])


def arbeitsplatz_melden(db, platz=None, name="", geraet_pub="", version=""):
    """Diesen Arbeitsplatz eintragen bzw. 'zuletzt gesehen' setzen. Ein gesperrter Platz bleibt gesperrt.
    Ergebnis: dict(platz, status, neu)."""
    from . import server_betrieb
    p = (platz or server_betrieb.platz()).strip().upper()[:60]
    kennung = installation(db)["kennung"]
    z = db.con.execute(f"SELECT status FROM {ARBEITSPLAETZE} WHERE platz=?", (p,)).fetchone()
    if z is None:
        _ausfuehren(db, f"INSERT INTO {ARBEITSPLAETZE} (platz, name, installation, geraet_pub, status, zuerst, "
                    "zuletzt, version) VALUES (?, ?, ?, ?, 'aktiv', ?, ?, ?)",
                    (p, name or p, kennung, geraet_pub, _jetzt(), _jetzt(), version))
        return dict(platz=p, status="aktiv", neu=True)
    _ausfuehren(db, f"UPDATE {ARBEITSPLAETZE} SET zuletzt=?, version=COALESCE(NULLIF(?, ''), version), "
                "geraet_pub=COALESCE(NULLIF(?, ''), geraet_pub) WHERE platz=?", (_jetzt(), version, geraet_pub, p))
    return dict(platz=p, status=z[0] or "aktiv", neu=False)


def arbeitsplaetze(db):
    sp = ("platz", "name", "installation", "status", "zuerst", "zuletzt", "version")
    return [dict(zip(sp, z)) for z in db.con.execute(f"SELECT {', '.join(sp)} FROM {ARBEITSPLAETZE} ORDER BY platz")]


# ------------------------------------------------------------------ Konten (Umrechnung alt -> neu)
def alte_rechte(stufen):
    """Einzelrechte aus der alten Rechtetabelle {Bereich: '', 'sehen', 'bearbeiten'} (rollen.py). Gleiches oder
    mehr wie vorher: 'bearbeiten' bei Angeboten umfasste alles rund ums Angebot (auch Preise, Technik, Daten)."""
    from . import rollen as R
    s = {b: stufen.get(b) or R.KEIN for b, _ in R.BEREICHE}
    r = set()
    if s[R.B_ANGEBOTE] in (R.SEHEN, R.BEARBEITEN):
        r |= {"angebot.sehen", "preise.ek_sehen"}
    if s[R.B_ANGEBOTE] == R.BEARBEITEN:
        r |= {"angebot.erstellen", "angebot.bearbeiten", "angebot.freigeben", "angebot.loeschen",
              "preise.vk_bearbeiten", "daten.import", "daten.export"} | set(B._TECHNIK)
    for bereich, recht in ((R.B_AUFTRAEGE, "auftrag.bearbeiten"), (R.B_AV, "av.bearbeiten"),
                           (R.B_PRODUKTION, "produktion.bearbeiten"), (R.B_QS, "qs.bearbeiten"),
                           (R.B_VERSAND, "versand.bearbeiten")):
        if s[bereich] in (R.SEHEN, R.BEARBEITEN):
            r.add("auftrag.sehen")
        if s[bereich] == R.BEARBEITEN:
            r.add(recht)
    if s[R.B_AUSWERTUNG] in (R.SEHEN, R.BEARBEITEN):
        r.add("auswertung.sehen")
    return r


def _grundrolle(alte_rollen, admin):
    from . import rollen as R
    if admin or R.ADMIN in alte_rollen:
        return B.ADMIN
    if R.KALKULATION in alte_rollen:
        return B.KALK_PRO
    if alte_rollen:
        return B.MITARBEITER
    return B.NUR_LESEN


def umrechnen(alte_rollen, tabelle, admin=False):
    """Neues Format aus alten Rollen: dict(rollen, plus, minus) mit wirksame_rechte == alte Rechte. tabelle: alte
    Rechtetabelle {Rolle: {Bereich: Stufe}} (rollen.rechte). admin: Admin laut Admin-Liste bzw. alte Rolle admin
    (durfte alles; neu Rolle Administrator ohne Lizenz-, Datenbank- und Arbeitsplatzverwaltung, die Paket E dem
    Hauptadmin zuordnet)."""
    from . import rollen as R
    alt = [r for r in alte_rollen or () if r in R.ROLLE_TITEL]
    rolle = _grundrolle(alt, admin)
    if rolle == B.ADMIN:
        return dict(rollen=[rolle], plus=[], minus=[])
    stufen = {}
    for r in alt:
        for b, st in (tabelle.get(r) or {}).items():
            if R._RANG.get(st, 0) > R._RANG.get(stufen.get(b, R.KEIN), 0):
                stufen[b] = st
    if not alt:                       # ohne Rolle durfte man bisher alles ansehen
        stufen = {b: R.SEHEN for b, _ in R.BEREICHE}
    soll = alte_rechte(stufen)
    basis = B.rollen_rechte(rolle)
    return dict(rollen=[rolle], plus=sorted(soll - basis), minus=sorted(basis - soll))


def konto(kuerzel, e, tabelle, admin=False):
    """Konto für die Prüfstelle (zugang_pruefstelle.benutzer_anmelden) aus einem Eintrag von benutzer_rollen."""
    z = e.get(TEIL) if isinstance(e.get(TEIL), dict) else None
    if z is None:
        neu = umrechnen(e.get("rollen") or (), tabelle, admin)
        status = "aktiv" if e.get("aktiv", True) else "gesperrt"
        z = dict(neu, status=status, umgerechnet=True)
    status = z.get("status") if z.get("status") in STATUS else "aktiv"
    return dict(id=str(z.get("id") or kuerzel), kuerzel=kuerzel, name=str(e.get("name") or kuerzel),
                hash=e.get("hash") or "", pin=e.get("pin") or "", status=status,
                rollen=[r for r in z.get("rollen") or () if r in B.ROLLEN],
                plus=[r for r in z.get("plus") or () if r in B.RECHT],
                minus=[r for r in z.get("minus") or () if r in B.RECHT],
                totp=str(z.get("totp") or ""), passwort_aendern=bool(z.get("passwort_aendern")),
                minuten=int(z.get("minuten") or 0) or None, umgerechnet=bool(z.get("umgerechnet")))


def konten(db):
    """{Kürzel: Konto} aus benutzer_rollen und der Admin-Liste (gleiches Kürzel = ein Konto). Ein Admin der
    Admin-Liste ohne Eintrag in benutzer_rollen bekommt ein Konto ohne Passwort (anmelden kann er erst, wenn ein Admin
    ihm eines gibt; das Admin-Passwort ist ein anderes Geheimnis und wird nicht übernommen)."""
    from . import admin_schutz
    from . import rollen as R
    tabelle = R.rechte(db)
    admin = {k for k, v in admin_schutz.admins(db).items() if v.get("recht") == admin_schutz.ADMIN}
    aus = {}
    for k, e in R.benutzer(db).items():
        aus[k] = konto(k, e, tabelle, k in admin)
    for k in admin - set(aus):
        aus[k] = konto(k, dict(name=(admin_schutz.admins(db).get(k) or {}).get("name") or k, rollen=[R.ADMIN]),
                       tabelle, True)
    for k, st in _staende(db).items():
        if k in aus:
            aus[k]["totp_zuletzt"] = st["totp_zuletzt"]
    return aus


def konto_speichern(db, kuerzel, *, rollen=None, plus=None, minus=None, status=None, totp=None,
                    passwort_aendern=None, minuten=None, hash_=None):
    """Teil zg eines Kontos schreiben (zuerst die Umrechnung übernehmen, damit nichts verloren geht). Die
    Rechteprüfung (wer darf was vergeben) macht der Aufrufer über zugang_berechtigung.vergabe_fehler; hier wird nur
    gespeichert. 'rollen' (alt) bleibt für ältere Programmversionen stehen. Ergebnis: Fehlertext oder ''."""
    from . import rollen as R
    liste = R.benutzer(db)
    if kuerzel not in liste:
        return "Den Benutzer gibt es nicht."
    e = liste[kuerzel]
    k = konten(db).get(kuerzel)
    z = dict(e.get(TEIL) or {}) or dict(id=kuerzel, rollen=k["rollen"], plus=k["plus"], minus=k["minus"],
                                        status=k["status"])
    for name, wert in (("rollen", rollen), ("plus", plus), ("minus", minus), ("status", status),
                       ("totp", totp), ("passwort_aendern", passwort_aendern), ("minuten", minuten)):
        if wert is not None:
            z[name] = list(wert) if isinstance(wert, (list, tuple, set, frozenset)) else wert
    if z.get("status") not in STATUS:
        return "Unbekannter Status."
    z.pop("umgerechnet", None)
    e[TEIL] = z
    e["aktiv"] = z["status"] == "aktiv"
    if hash_ is not None:
        e["hash"] = hash_
    e["stand"] = _jetzt()
    db.einstellung_setzen(BENUTZER, liste)
    return ""


# ------------------------------------------------------------------ Stand je Konto (nur dieser Platz)
def _staende(db):
    aus = {}
    for k, fehl, bis, totp, letzte, platz in db.con.execute(
            f"SELECT kuerzel, fehl, sperre_bis, totp_zuletzt, letzte_anmeldung, letzter_platz FROM {KONTO_STAND}"):
        aus[k] = dict(fehl=int(fehl or 0), bis=float(bis or 0), totp_zuletzt=-1 if totp is None else int(totp),
                      letzte=letzte or "", platz=platz or "")
    return aus


def stand(db, kuerzel):
    return _staende(db).get(kuerzel) or dict(fehl=0, bis=0.0, totp_zuletzt=-1, letzte="", platz="")


def _stand_setzen(db, kuerzel, **werte):
    alt = stand(db, kuerzel)
    alt.update(werte)
    return _ausfuehren(
        db, f"INSERT INTO {KONTO_STAND} (kuerzel, fehl, sperre_bis, totp_zuletzt, letzte_anmeldung, letzter_platz) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (kuerzel) DO UPDATE SET fehl=excluded.fehl, "
        "sperre_bis=excluded.sperre_bis, totp_zuletzt=excluded.totp_zuletzt, "
        "letzte_anmeldung=excluded.letzte_anmeldung, letzter_platz=excluded.letzter_platz",
        (kuerzel, alt["fehl"], alt["bis"], alt["totp_zuletzt"], alt["letzte"], alt["platz"]))


def anmeldung_merken(db, kuerzel, platz="", totp_schritt=-1):
    """Nach erfolgreicher Anmeldung: letzte Anmeldung und benutzter Einmalcode (gegen Wiederverwendung)."""
    werte = dict(letzte=_jetzt(), platz=platz)
    if totp_schritt is not None and int(totp_schritt) >= 0:
        werte["totp_zuletzt"] = int(totp_schritt)
    _stand_setzen(db, kuerzel, **werte)


class Sperre:
    """Fehlversuche je Kürzel in zg_konto_stand (übersteht Neustart). Schnittstelle wie hauptadmin.Sperre
    (wartezeit, fehlschlag, erfolg), damit die Prüfstelle beide gleich benutzt. Auch ein unbekanntes Kürzel wird
    gezählt (sonst verrät die Wartezeit, welche Kürzel es gibt)."""

    def __init__(self, db, kuerzel, uhr=time.time):
        self.db, self.kuerzel, self.uhr = db, str(kuerzel or "").upper()[:40], uhr

    def wartezeit(self):
        return max(0, int(stand(self.db, self.kuerzel)["bis"] - self.uhr() + 0.999))

    def fehlversuche(self):
        return stand(self.db, self.kuerzel)["fehl"]

    def fehlschlag(self):
        st = stand(self.db, self.kuerzel)
        fehl, bis, warten = st["fehl"] + 1, st["bis"], 0
        if fehl >= FEHL_FREI:
            warten = min(SPERRE_ERSTE_S * 2 ** (fehl - FEHL_FREI), SPERRE_MAX_S)
            bis = max(bis, self.uhr() + warten)
        _stand_setzen(self.db, self.kuerzel, fehl=fehl, bis=bis)
        return warten

    def erfolg(self):
        _stand_setzen(self.db, self.kuerzel, fehl=0, bis=0.0)

    def freigeben(self):
        """Admin hebt die Sperre auf (Paket C/F)."""
        self.erfolg()


# ------------------------------------------------------------------ Protokoll, Versuche, Sitzungen
_VERSUCH = {P.ANMELDUNG_OK: "ok", P.ANMELDUNG_FEHLER: None}


def senke(db):
    """Funktion(eintrag) für zugang_protokoll.Protokoll: Eintrag nach zg_protokoll, Anmeldungen zusätzlich nach
    zg_anmeldeversuche. Der Eintrag ist schon bereinigt (keine Geheimnisse)."""
    def ablegen(e):
        details = json.dumps(e.get("details") or {}, ensure_ascii=False)
        _ausfuehren(db, f"INSERT INTO {PROTOKOLL} (zeit, aktion, benutzer, installation, platz, objekt, ergebnis, "
                    "details) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (e["zeit"], e["aktion"], e["benutzer"], e["installation"], e["arbeitsplatz"], e["objekt"],
                     e["ergebnis"], details))
        if e["aktion"] in _VERSUCH:
            _ausfuehren(db, f"INSERT INTO {VERSUCHE} (zeit, kuerzel, platz, ergebnis) VALUES (?, ?, ?, ?)",
                        (e["zeit"], e["benutzer"], e["arbeitsplatz"], _VERSUCH[e["aktion"]] or e["ergebnis"]))
    return ablegen


def protokoll_lesen(db, letzte=500, aktion=None, benutzer=None):
    """Die letzten Einträge aus zg_protokoll, neueste zuletzt."""
    sql, werte = f"SELECT zeit, aktion, benutzer, installation, platz, objekt, ergebnis, details FROM {PROTOKOLL}", []
    bed = []
    if aktion:
        bed.append("aktion=?")
        werte.append(aktion)
    if benutzer:
        bed.append("benutzer=?")
        werte.append(benutzer)
    if bed:
        sql += " WHERE " + " AND ".join(bed)
    sql += f" ORDER BY id DESC LIMIT {int(letzte)}"
    aus = []
    for z in db.con.execute(sql, werte):
        try:
            details = json.loads(z[7] or "{}")
        except ValueError:
            details = {}
        aus.append(dict(zeit=z[0], aktion=z[1], benutzer=z[2], installation=z[3], arbeitsplatz=z[4], objekt=z[5],
                        ergebnis=z[6], details=details))
    return aus[::-1]


def versuche(db, kuerzel=None, letzte=200):
    sql, werte = f"SELECT zeit, kuerzel, platz, ergebnis FROM {VERSUCHE}", []
    if kuerzel:
        sql, werte = sql + " WHERE kuerzel=?", [kuerzel]
    rows = db.con.execute(sql + f" ORDER BY id DESC LIMIT {int(letzte)}", werte).fetchall()
    return [dict(zeit=a, kuerzel=b, platz=c, ergebnis=d) for a, b, c, d in rows][::-1]


def _sha(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


def sitzung_beobachter(db):
    """Funktion(ereignis, sitzung) für zugang_sitzungen.Sitzungen: Beginn, letzte Eingabe und Ende in zg_sitzungen.
    Gespeichert wird nur der SHA-256 des Tokens."""
    def melden(ereignis, s):
        jetzt = _jetzt()
        if ereignis == "angelegt":
            _ausfuehren(db, f"INSERT INTO {SITZUNGEN} (token_sha, benutzer, kuerzel, entwickler, installation, platz, "
                        "beginn, letzte) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (_sha(s.token), s.benutzer, s.kuerzel, int(s.entwickler), s.installation, s.arbeitsplatz,
                         jetzt, jetzt))
        elif ereignis in ("beendet", "gesperrt", "entsperrt"):
            ende = jetzt if ereignis == "beendet" else None
            _ausfuehren(db, f"UPDATE {SITZUNGEN} SET letzte=?, ende=COALESCE(?, ende), grund=? WHERE token_sha=?",
                        (jetzt, ende, ereignis, _sha(s.token)))
    return melden


def sitzungen_lesen(db, offen=False, letzte=200):
    sql = (f"SELECT benutzer, kuerzel, entwickler, installation, platz, beginn, letzte, ende, grund FROM {SITZUNGEN}"
           + (" WHERE ende IS NULL" if offen else "") + f" ORDER BY id DESC LIMIT {int(letzte)}")
    sp = ("benutzer", "kuerzel", "entwickler", "installation", "platz", "beginn", "letzte", "ende", "grund")
    return [dict(zip(sp, z)) for z in db.con.execute(sql)][::-1]


def aufraeumen(db, behalten=PROTOKOLL_MAX):
    """Älteste Protokoll- und Versuchszeilen über behalten löschen (beim Start, Paket C)."""
    for t in (PROTOKOLL, VERSUCHE):
        z = db.con.execute(f"SELECT MAX(id) FROM {t}").fetchone()
        if z and z[0] and z[0] > behalten:
            _ausfuehren(db, f"DELETE FROM {t} WHERE id <= ?", (int(z[0]) - behalten,))


# ------------------------------------------------------------------ Prüfstelle für diese Datenbank
def pruefstelle(db, ordner=None, umgebung=None):
    """Prüfstelle mit Protokoll (Datei in ordner und Tabelle zg_protokoll), Sitzungen mit Eintrag in zg_sitzungen,
    Installation und Arbeitsplatz dieser Datenbank. Das Anmeldefenster (Paket C) nimmt sie."""
    from . import server_betrieb
    from .zugang_pruefstelle import Pruefstelle
    from .zugang_sitzungen import Sitzungen
    inst = installation(db, umgebung)
    platz = server_betrieb.platz()
    prot = P.Protokoll(ordner, inst["kennung"], platz, senke=senke(db))
    return Pruefstelle(prot, Sitzungen(beobachter=sitzung_beobachter(db)), inst["kennung"], inst["umgebung"], platz,
                       nur_lesen=lambda: bool(getattr(db, "nur_lesen", "")))


# ------------------------------------------------------------------ Migration
def bericht(db):
    """Übernahme der Benutzer ins neue Format: Liste je Konto (ohne Geheimnisse) und Hinweise."""
    from . import admin_schutz
    from . import rollen as R
    zeilen, hinweise = [], []
    alt = R.benutzer(db)
    for k, ko in sorted(konten(db).items()):
        e = alt.get(k) or {}
        h = ko["hash"]
        stand_pw = "keins" if not h else ("vorhanden, wird bei der ersten Anmeldung auf scrypt umgestellt"
                                    if not str(h).startswith("scrypt$") else "vorhanden (scrypt)")
        zeilen.append(dict(kuerzel=k, name=ko["name"], alte_rollen=list(e.get("rollen") or ()),
                           neue_rollen=ko["rollen"], plus=ko["plus"], minus=ko["minus"], status=ko["status"],
                           kennwort=stand_pw, ziffern=bool(ko["pin"]), nur_admin_liste=k not in alt,
                           umgerechnet=ko["umgerechnet"]))
        if not h and not ko["pin"]:
            hinweise.append(f"{k}: kein Passwort und keine PIN – anmelden erst, wenn ein Admin eines vergibt.")
    if admin_schutz.aktiv(db):
        hinweise.append("Admin-Schutz ist eingerichtet: das Admin-Passwort bleibt wie bisher zusätzlich gültig.")
    if getattr(db, "server", None) is not None:
        hinweise.append("Serverbetrieb: die Logins am Server bleiben unverändert (Rechtegruppen folgen in Paket E).")
    return dict(konten=zeilen, hinweise=hinweise, anzahl=len(zeilen))


def migrieren(db, von, nach=SCHEMA, sicherung=""):
    """Nach dem Anlegen der Tabellen (Datenbank._anlegen): Bericht über die Übernahme der Konten schreiben (zg_migration) und ins Sicherheitsprotokoll. Die Sicherung vor dem Schema-Sprung hat
    Datenbank._anlegen schon gemacht und geprüft. Ändert keine Geschäftstabelle und nicht die signierte Vorgabe."""
    from . import VERSION
    if db.con.execute(f"SELECT 1 FROM {MIGRATION} WHERE nach=? AND status='fertig'", (nach,)).fetchone():
        return None
    try:
        b = bericht(db)
        status = "fertig"
    except Exception as e:          # noqa: BLE001 – Bericht darf den Start nicht verhindern; Konten gelten trotzdem
        b, status = dict(konten=[], hinweise=[f"Bericht nicht erstellt: {e}"], anzahl=0), "fertig_ohne_bericht"
        _protokoll.warnung(f"Zugangsdaten: Migrationsbericht nicht erstellt ({e})")
    db.con.execute(f"INSERT INTO {MIGRATION} (zeit, von, nach, version, sicherung, bericht, status) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?)",
                   (_jetzt(), int(von or 0), int(nach), VERSION, str(sicherung or ""),
                    json.dumps(P.bereinigen(b), ensure_ascii=False), status))
    e = dict(zeit=_jetzt(), aktion=P.MIGRATION, benutzer="", installation="", arbeitsplatz="",
             objekt=f"Schema {von} -> {nach}", ergebnis=status, details=dict(konten=b["anzahl"]))
    db.con.execute(f"INSERT INTO {PROTOKOLL} (zeit, aktion, benutzer, installation, platz, objekt, ergebnis, details) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (e["zeit"], e["aktion"], "", "", "", e["objekt"], status,
                                                        json.dumps(e["details"])))
    return b


def migrationen(db):
    sp = ("zeit", "von", "nach", "version", "sicherung", "bericht", "status")
    aus = []
    for z in db.con.execute(f"SELECT {', '.join(sp)} FROM {MIGRATION} ORDER BY id"):
        d = dict(zip(sp, z))
        try:
            d["bericht"] = json.loads(d["bericht"] or "{}")
        except ValueError:
            d["bericht"] = {}
        aus.append(d)
    return aus


def bericht_text(b):
    """Bericht als Text (Dashboard, Paket F)."""
    z = [f"Übernommene Benutzerkonten: {b.get('anzahl', 0)}"]
    for k in b.get("konten") or ():
        extra = "".join([f", zusätzlich {', '.join(k['plus'])}" if k["plus"] else "",
                         f", ohne {', '.join(k['minus'])}" if k["minus"] else ""])
        z.append(f"- {k['kuerzel']} ({k['name']}): {', '.join(k['alte_rollen']) or 'keine Rolle'} -> "
                 f"{', '.join(B.ROLLE_TITEL.get(r, r) for r in k['neue_rollen'])}{extra}; Passwort {k['kennwort']}"
                 + ("; PIN vorhanden" if k.get("ziffern") else ""))
    z += [f"Hinweis: {h}" for h in b.get("hinweise") or ()]
    return "\n".join(z)
