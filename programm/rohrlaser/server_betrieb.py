"""Betriebsart Server: eine zentrale PostgreSQL-Datenbank für alle Arbeitsplätze (Serverversion, Patrick 26.11.2026,
Paket S1). Ohne Qt.

Die lokale Betriebsart (PostgreSQL je PC, Abgleich über den gemeinsamen Ordner) bleibt unverändert. Im Serverbetrieb
arbeiten alle Arbeitsplätze mit derselben Datenbank auf einem Server-Rechner im Firmennetz; Oberfläche, Kalkulation
und Importe sind derselbe Code. Unterschiede gibt es nur hier, in datenspeicher (Merkdatei), bei den Nummern und bei
den Einstellungen je Arbeitsplatz und je Benutzer.

Server-Rechner (ZentralerServer): PostgreSQL aus dem Programmpaket, erreichbar im Netz nur verschlüsselt (TLS mit
eigenem Zertifikat, das eine eigene Zertifizierungsstelle unterschreibt) und nur mit Passwort (scram-sha-256).
Rollen in der Datenbank:
- rohrlaser_app: Eigentümer aller Tabellen (wie am Einzelplatz), ohne Superuser-Rechte.
- rohrlaser_lesen: darf nur lesen (Werkstatt, abweichende Programmversion).
- rohrlaser_verwalter: Markierung für Administratoren (Programmversion des Servers heben, Benutzer anlegen).
- je Mitarbeiter ein eigener Login rl_<kürzel> (NOINHERIT): er darf sich anmelden und arbeitet danach als
  rohrlaser_app oder rohrlaser_lesen (role beim Verbindungsaufbau). So prüft der Server Anmeldung und Leserecht
  selbst, und sein Protokoll nennt den Mitarbeiter.

Arbeitsplatz: Zugangsdatei (*.rlserver, schreibt der Server) einlesen; danach steht in der Merkdatei des
Datenspeichers art=server mit Adresse, Port und dem Zertifikat der Zertifizierungsstelle (server_ca.pem daneben).
Beim Start meldet sich der Mitarbeiter mit Kürzel und Passwort an.

Einheitliche Ergebnisse: in server_info steht die Programmversion des Servers (Pflichtversion). Nur Arbeitsplätze mit
genau dieser Version dürfen schreiben; andere öffnen nur lesend (gleiches Schema) oder gar nicht (anderes Schema).
Eine neuere Version hebt nur ein Administrator an (danach müssen alle aktualisieren). Die Datenpflege beim Öffnen
(Tabellen, Richtwerte, Ergänzungen) läuft einmal je Version, nicht bei jedem Start jedes Arbeitsplatzes.
"""
import contextlib
import datetime
import hashlib
import json
import os
import re
import secrets
import socket
from pathlib import Path

from . import db_verbindung, pg_lokal
from .zahlen import jetzt_text as _jetzt

ART = "server"                      # Merkdatei art=server
ENDUNG = ".rlserver"                # Zugangsdatei für die Arbeitsplätze
ZUGANG_DATEI = "Arbeitsplatz-Zugang" + ENDUNG
CA_DATEI = "server_ca.pem"          # am Arbeitsplatz neben der Merkdatei
PORT = 5432
DATENBANK = pg_lokal.DATENBANK
ROLLE_APP = pg_lokal.BENUTZER       # rohrlaser_app
ROLLE_LESEN = "rohrlaser_lesen"
ROLLE_VERWALTER = "rohrlaser_verwalter"
LOGIN_PRAEFIX = "rl_"
INFO = "server_info"                # schluessel, wert: programm (Pflichtversion), schema, pflege, name, eingerichtet
NUMMERN = "server_nummern"          # vergebene Nummern je Bereich (Angebote, AB-Nummern), nie zweimal
NUMMER_SPERRE = 73101               # pg_advisory_xact_lock beim Vergeben einer Nummer
ANWENDUNG = "Rohrlaser-Kalkulation (Server)"
MAX_VERBINDUNGEN = 150              # 25 Plätze × (Programm, Hintergrund, Sicherung) mit Reserve
ZERT_JAHRE = 10

# Zustände beim Öffnen (Sitzung.zustand)
OK, NEU, HEBEN, VERALTET, VORAUS = "ok", "neu", "heben", "veraltet", "voraus"
RECHT_BEARBEITEN, RECHT_LESEN, RECHT_VERWALTER = "bearbeiten", "lesen", "verwalter"
RECHTE = (RECHT_BEARBEITEN, RECHT_LESEN, RECHT_VERWALTER)


class ServerFehler(RuntimeError):
    """Serverbetrieb nicht möglich; der Text steht für den Benutzer."""


class AnmeldungFehlt(ServerFehler):
    """Serverbetrieb eingerichtet, aber (noch) niemand angemeldet."""


class AnmeldeFehler(ServerFehler):
    """Kürzel oder Passwort stimmt nicht (oder Benutzer gesperrt)."""


class ZertifikatFehler(ServerFehler):
    """Der Server weist sich nicht mit dem erwarteten Zertifikat aus."""


# ------------------------------------------------------------------------------------------------ Hilfen
def version_tupel(text):
    """'0.9.516' -> (0, 9, 516); unlesbar -> ()."""
    teile = re.findall(r"\d+", str(text or ""))
    return tuple(int(t) for t in teile[:4])


def login_name(kuerzel):
    """Datenbank-Login eines Mitarbeiters: rl_ + Kürzel in Kleinbuchstaben (nur a-z, 0-9, _)."""
    k = re.sub(r"[^a-z0-9_]", "", str(kuerzel or "").strip().lower()
               .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss"))
    if not k:
        raise ServerFehler("Bitte ein Kürzel eingeben (Buchstaben und Ziffern).")
    return LOGIN_PRAEFIX + k[:40]


def kuerzel_aus_login(login):
    return str(login or "")[len(LOGIN_PRAEFIX):].upper() if str(login or "").startswith(LOGIN_PRAEFIX) else ""


def platz():
    """Kennung dieses Arbeitsplatzes (Rechnername; ROHRLASER_ARBEITSPLATZ für Tests)."""
    return (os.environ.get("ROHRLASER_ARBEITSPLATZ") or socket.gethostname() or "PC").strip().upper()[:60]


def fingerabdruck(pem):
    """SHA-256 des Zertifikats (DER) in Vierergruppen, zum Vergleichen am Telefon."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    der = x509.load_pem_x509_certificate(pem.encode() if isinstance(pem, str) else pem).public_bytes(
        serialization.Encoding.DER)
    h = hashlib.sha256(der).hexdigest().upper()
    return " ".join(h[i:i + 4] for i in range(0, 32, 4))


# ------------------------------------------------------------------------------------------------ Zertifikate
def zertifikate_erzeugen(ordner, namen=()):
    """Eigene Zertifizierungsstelle (ca.crt/ca.key im Server-Ordner) und Serverzertifikat (server.crt/server.key)
    für die Rechnernamen und Adressen namen (dazu immer der eigene Rechnername, localhost, 127.0.0.1). Der Schlüssel
    der Zertifizierungsstelle verlässt den Server-Ordner nie; die Arbeitsplätze bekommen nur ca.crt."""
    import ipaddress
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    ordner = Path(ordner)
    ordner.mkdir(parents=True, exist_ok=True)
    jetzt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    bis = jetzt + datetime.timedelta(days=365 * ZERT_JAHRE)
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Rohrlaser-Kalkulation Server-CA"),
                         x509.NameAttribute(NameOID.SERIAL_NUMBER, secrets.token_hex(8))])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(jetzt).not_valid_after(bis)
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                       data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                       crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
          .sign(ca_key, hashes.SHA256()))
    alle = []
    for n in [socket.gethostname(), "localhost", "127.0.0.1", *namen]:
        n = str(n or "").strip()
        if n and n.lower() not in {a.lower() for a in alle}:
            alle.append(n)
    san = []
    for n in alle:
        try:
            san.append(x509.IPAddress(ipaddress.ip_address(n)))
        except ValueError:
            san.append(x509.DNSName(n))
    key = ec.generate_private_key(ec.SECP256R1())
    cert = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, alle[0])]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(jetzt).not_valid_after(bis)
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(ca_key, hashes.SHA256()))

    def schreiben(name, daten, geheim=False):
        p = ordner / name
        tmp = p.with_suffix(p.suffix + ".neu")
        tmp.write_bytes(daten)
        if geheim:
            with contextlib.suppress(OSError):
                os.chmod(tmp, 0o600)
        os.replace(tmp, p)
        return p
    pem = serialization.Encoding.PEM
    ohne = serialization.NoEncryption()
    schreiben("ca.crt", ca.public_bytes(pem))
    schreiben("ca.key", ca_key.private_bytes(pem, serialization.PrivateFormat.PKCS8, ohne), geheim=True)
    schreiben("server.crt", cert.public_bytes(pem))
    schreiben("server.key", key.private_bytes(pem, serialization.PrivateFormat.PKCS8, ohne), geheim=True)
    return dict(ca=ordner / "ca.crt", namen=alle, fingerabdruck=fingerabdruck(ca.public_bytes(pem)))


# ------------------------------------------------------------------------------------------------ Server-Rechner
class ZentralerServer(pg_lokal.LokalerServer):
    """PostgreSQL auf dem Server-Rechner: Datenordner <ordner>/pg, fester Port, im Netz nur mit TLS und Passwort.
    Der Verwalter (Superuser) bleibt wie am Einzelplatz nur für Einrichtung und Wartung; sein Passwort steht in
    pg_zugang.json im Server-Ordner (unter Windows verschlüsselt)."""

    def __init__(self, ordner, bin_ordner=None, port=PORT, namen=()):
        super().__init__(ordner, bin_ordner)
        self.port = int(port)
        self.namen = tuple(namen)

    def _konfiguration(self):
        return ("\n# Rohrlaser-Kalkulation zentraler Server (Serverversion S1)\nlisten_addresses = '*'\n"
                f"port = {self.port}\nunix_socket_directories = ''\nmax_connections = {MAX_VERBINDUNGEN}\n"
                "shared_buffers = 512MB\nwork_mem = 16MB\nmaintenance_work_mem = 128MB\n"
                "fsync = on\nsynchronous_commit = on\nfull_page_writes = on\n"
                "ssl = on\nssl_cert_file = 'server.crt'\nssl_key_file = 'server.key'\n"
                "ssl_min_protocol_version = 'TLSv1.2'\npassword_encryption = 'scram-sha-256'\n"
                "idle_in_transaction_session_timeout = '10min'\ntcp_keepalives_idle = 60\n"
                + "".join(f"{k} = {v}\n" for k, v in pg_lokal.PROTOKOLL.items()))

    def _nach_initdb(self):
        info = zertifikate_erzeugen(self.daten, self.namen)
        for n in ("server.crt", "server.key"):              # PostgreSQL liest sie aus dem Datenordner
            ziel = self.pg / n
            ziel.write_bytes((self.daten / n).read_bytes())
            with contextlib.suppress(OSError):
                os.chmod(ziel, 0o600)
        # Zugang aus dem Netz nur verschlüsselt und mit Passwort; ohne TLS passt keine Zeile (abgewiesen).
        # Auf dem Server-Rechner selbst (127.0.0.1) gelten die Zeilen von initdb (scram-sha-256).
        with open(self.pg / "pg_hba.conf", "a", encoding="utf-8") as f:
            f.write("\n# Rohrlaser-Kalkulation: Arbeitsplätze im Netz nur mit TLS und Passwort\n"
                    "hostssl all all 0.0.0.0/0 scram-sha-256\nhostssl all all ::/0 scram-sha-256\n")
        self.zertifikat = info

    def _port_waehlen(self):
        with socket.socket() as s:
            try:
                s.bind(("0.0.0.0", self.port))
            except OSError:
                raise ServerFehler(f"Port {self.port} ist auf diesem Rechner schon belegt (läuft dort ein anderes "
                                   "PostgreSQL?). Bitte einen anderen Port wählen.") from None
        return self.port

    def ca_pem(self):
        return (self.daten / "ca.crt").read_text(encoding="ascii")

    def verwalter_verbinden(self, datenbank="postgres"):
        return self._verbinden(*self._verwalter(), datenbank)

    def _verwalter(self):
        d = self._zugang_lesen() or {}
        return d.get("admin_benutzer", pg_lokal.VERWALTER), d.get("admin_passwort")

    def einrichten(self, name, admin_kuerzel, admin_passwort):
        """Neuen Server anlegen und starten, Rollen und Servertabellen einrichten, ersten Administrator anlegen.
        Ein schon eingerichteter Server bleibt unverändert (nur gestartet). Ergebnis: Pfad der Zugangsdatei."""
        neu = not self.angelegt
        self.starten()
        with self.verwalter_verbinden(DATENBANK) as con:
            rollen_einrichten(con)
            con.execute(f'SET ROLE "{ROLLE_APP}"')
            info_einrichten(con)
            con.execute("RESET ROLE")
            if neu or not info_lesen(con).get("name"):
                info_setzen(con, name=str(name or "Rohrlaser-Server"), eingerichtet=_jetzt(), port=str(self.port))
            if admin_kuerzel:
                benutzer_anlegen(con, admin_kuerzel, admin_passwort, RECHT_VERWALTER, name=admin_kuerzel)
        return self.zugang_schreiben()

    def zugang_schreiben(self, adressen=None, ziel=None):
        """Zugangsdatei für die Arbeitsplätze (Adressen, Port, Zertifikat der Zertifizierungsstelle; kein Passwort)."""
        with self.verwalter_verbinden(DATENBANK) as con:
            name = info_lesen(con).get("name") or "Rohrlaser-Server"
        adressen = list(adressen or self.namen or [socket.gethostname()])
        inhalt = dict(format=1, art="rohrlaser-server", name=name, adressen=adressen, port=self.port,
                      datenbank=DATENBANK, ca=self.ca_pem(), fingerabdruck=fingerabdruck(self.ca_pem()),
                      erstellt=_jetzt())
        ziel = Path(ziel) if ziel else self.daten / ZUGANG_DATEI
        tmp = ziel.with_suffix(".neu")
        tmp.write_text(json.dumps(inhalt, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, ziel)
        return ziel


def rollen_einrichten(con):
    """Gruppenrollen und Leserechte (als Verwalter, Datenbank rohrlaser). Mehrfach aufrufbar."""
    for rolle in (ROLLE_LESEN, ROLLE_VERWALTER):
        if not con.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (rolle,)).fetchone():
            con.execute(f'CREATE ROLE "{rolle}" NOLOGIN')
    con.execute(f'GRANT CONNECT ON DATABASE "{DATENBANK}" TO "{ROLLE_LESEN}"')
    con.execute(f'GRANT USAGE ON SCHEMA public TO "{ROLLE_LESEN}"')
    con.execute(f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{ROLLE_LESEN}"')
    con.execute(f'GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO "{ROLLE_LESEN}"')
    con.execute(f'ALTER DEFAULT PRIVILEGES FOR ROLE "{ROLLE_APP}" IN SCHEMA public GRANT SELECT ON TABLES '
                f'TO "{ROLLE_LESEN}"')
    con.execute(f'ALTER DEFAULT PRIVILEGES FOR ROLE "{ROLLE_APP}" IN SCHEMA public GRANT SELECT ON SEQUENCES '
                f'TO "{ROLLE_LESEN}"')


def info_einrichten(con):
    """Servertabellen (als rohrlaser_app). psycopg-Verbindung oder Verbindung dieser Schicht."""
    con.execute(f"CREATE TABLE IF NOT EXISTS {INFO} (schluessel TEXT PRIMARY KEY, wert TEXT)")
    con.execute(f"CREATE TABLE IF NOT EXISTS {NUMMERN} (bereich TEXT NOT NULL, zaehler INTEGER NOT NULL, "
                "nummer TEXT, wer TEXT, platz TEXT, zeit TEXT, PRIMARY KEY (bereich, zaehler))")


def info_lesen(con):
    try:
        return {k: w for k, w in con.execute(f"SELECT schluessel, wert FROM {INFO}").fetchall()}
    except Exception:       # noqa: BLE001 - Tabelle fehlt (Server noch nicht eingerichtet)
        return {}


def info_setzen(con, **werte):
    platzhalter = "%s" if _ist_psycopg(con) else "?"
    for k, w in werte.items():
        con.execute(f"INSERT INTO {INFO} (schluessel, wert) VALUES ({platzhalter}, {platzhalter}) "
                    "ON CONFLICT (schluessel) DO UPDATE SET wert = excluded.wert", (k, None if w is None else str(w)))


def _ist_psycopg(con):
    return type(con).__module__.startswith("psycopg")


# ------------------------------------------------------------------------------------------------ Benutzer
def _pw_literal(passwort):
    from psycopg import sql
    return sql.Literal(str(passwort))


def benutzer_anlegen(con, kuerzel, passwort, recht=RECHT_BEARBEITEN, name=""):
    """Login rl_<kürzel> anlegen oder ändern (Verwalter oder angemeldeter Administrator mit CREATEROLE).
    recht: bearbeiten (arbeitet als rohrlaser_app), lesen (nur lesen), verwalter (bearbeiten + Version heben +
    Benutzer verwalten). Passwort mindestens 8 Zeichen."""
    from psycopg import sql
    if recht not in RECHTE:
        raise ServerFehler(f"Unbekanntes Recht: {recht}")
    if not passwort or len(str(passwort)) < 8:
        raise ServerFehler("Das Passwort braucht mindestens 8 Zeichen.")
    login = login_name(kuerzel)
    da = con.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (login,)).fetchone()
    zusatz = " CREATEROLE" if recht == RECHT_VERWALTER else " NOCREATEROLE"
    befehl = sql.SQL(("ALTER" if da else "CREATE") + " ROLE {} LOGIN NOINHERIT" + zusatz + " PASSWORD {}").format(
        sql.Identifier(login), _pw_literal(passwort))
    con.execute(befehl)
    rechte_setzen(con, kuerzel, recht)
    if name:
        con.execute(sql.SQL("COMMENT ON ROLE {} IS {}").format(sql.Identifier(login), sql.Literal(str(name))))
    return login


def rechte_setzen(con, kuerzel, recht):
    from psycopg import sql
    login = login_name(kuerzel)
    soll = {RECHT_BEARBEITEN: {ROLLE_APP}, RECHT_LESEN: {ROLLE_LESEN},
            RECHT_VERWALTER: {ROLLE_APP, ROLLE_VERWALTER}}[recht]
    for rolle in (ROLLE_APP, ROLLE_LESEN, ROLLE_VERWALTER):
        mitglied = con.execute("SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.roleid JOIN pg_roles u "
                               "ON u.oid = m.member WHERE r.rolname = %s AND u.rolname = %s",
                               (rolle, login)).fetchone() is not None
        if rolle in soll and not mitglied:
            mit_admin = sql.SQL(" WITH ADMIN OPTION") if recht == RECHT_VERWALTER else sql.SQL("")
            con.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(rolle), sql.Identifier(login)) + mit_admin)
        elif rolle not in soll and mitglied:
            con.execute(sql.SQL("REVOKE {} FROM {}").format(sql.Identifier(rolle), sql.Identifier(login)))
    if recht == RECHT_VERWALTER:        # darf auch Leser anlegen
        con.execute(sql.SQL("GRANT {} TO {} WITH ADMIN OPTION").format(sql.Identifier(ROLLE_LESEN),
                                                                     sql.Identifier(login)))
    con.execute(sql.SQL("ALTER ROLE {} " + ("CREATEROLE" if recht == RECHT_VERWALTER else "NOCREATEROLE"))
                .format(sql.Identifier(login)))


def passwort_setzen(con, kuerzel, passwort):
    from psycopg import sql
    if not passwort or len(str(passwort)) < 8:
        raise ServerFehler("Das Passwort braucht mindestens 8 Zeichen.")
    con.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(login_name(kuerzel)),
                                                            _pw_literal(passwort)))


def benutzer_sperren(con, kuerzel, gesperrt=True):
    from psycopg import sql
    con.execute(sql.SQL("ALTER ROLE {} " + ("NOLOGIN" if gesperrt else "LOGIN")).format(
        sql.Identifier(login_name(kuerzel))))


def benutzer_liste(con):
    """[{kuerzel, login, recht, gesperrt, name}] aller Mitarbeiter-Logins."""
    zeilen = con.execute(
        "SELECT r.rolname, r.rolcanlogin, shobj_description(r.oid, 'pg_authid'), "
        f"pg_has_role(r.oid, '{ROLLE_VERWALTER}', 'MEMBER'), pg_has_role(r.oid, '{ROLLE_APP}', 'MEMBER'), "
        f"pg_has_role(r.oid, '{ROLLE_LESEN}', 'MEMBER') FROM pg_roles r WHERE r.rolname LIKE 'rl\\_%' "
        "ORDER BY r.rolname").fetchall()
    out = []
    for login, darf, name, verw, app, lesen in zeilen:
        recht = RECHT_VERWALTER if verw and app else RECHT_BEARBEITEN if app else RECHT_LESEN if lesen else ""
        out.append(dict(kuerzel=kuerzel_aus_login(login), login=login, recht=recht, gesperrt=not darf,
                        name=name or ""))
    return out


# ------------------------------------------------------------------------------------------------ Zugangsdatei
def zugangsdatei_lesen(pfad):
    """Inhalt der Zugangsdatei *.rlserver (geprüft) oder ServerFehler."""
    try:
        d = json.loads(Path(pfad).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise ServerFehler(f"Die Zugangsdatei {pfad} lässt sich nicht lesen: {e}") from e
    if d.get("art") != "rohrlaser-server" or not d.get("ca") or not d.get("adressen"):
        raise ServerFehler(f"{pfad} ist keine Zugangsdatei des Rohrlaser-Servers.")
    d["fingerabdruck"] = fingerabdruck(d["ca"])         # nachgerechnet, nicht aus der Datei übernommen
    return d


# ------------------------------------------------------------------------------------------------ Arbeitsplatz
def merk_werte(zugang, adresse=None, kuerzel="", vorher=None):
    """Werte der Merkdatei für art=server aus einer gelesenen Zugangsdatei."""
    return dict(art=ART, name=zugang.get("name", ""), host=adresse or zugang["adressen"][0],
                adressen=json.dumps(zugang["adressen"]), port=str(zugang.get("port", PORT)),
                datenbank=zugang.get("datenbank", DATENBANK), ca=CA_DATEI, fingerabdruck=zugang["fingerabdruck"],
                kuerzel=kuerzel or "", seit=_jetzt(), vorher=json.dumps(vorher or {}, ensure_ascii=False))


def ca_pfad(merk_pfad, merk):
    return Path(merk_pfad).resolve().parent / (merk.get("ca") or CA_DATEI)


def verbinden_einrichten(merk_pfad, zugang, adresse=None, kuerzel=""):
    """Arbeitsplatz auf den Server umstellen: Zertifikat ablegen, Merkdatei mit art=server schreiben. Die bisherige
    Merkdatei (lokales PostgreSQL) bleibt als 'vorher' darin, ihre Daten bleiben unverändert im Ordner Daten/pg
    (zurück_lokal stellt sie wieder her). Die alte Merkdatei kommt zusätzlich als Kopie *.lokal daneben."""
    from . import datenspeicher
    merk_pfad = Path(merk_pfad)
    vorher = datenspeicher.merkdatei_lesen(merk_pfad) or {}
    if vorher.get("art") == ART:
        vorher = json.loads(vorher.get("vorher") or "{}")
    (merk_pfad.resolve().parent / CA_DATEI).write_text(zugang["ca"], encoding="ascii")
    if merk_pfad.exists() and (datenspeicher.merkdatei_lesen(merk_pfad) or {}).get("art") != ART:
        kopie = merk_pfad.with_name(merk_pfad.name + ".lokal")
        kopie.write_bytes(merk_pfad.read_bytes())
    tmp = datenspeicher._merkdatei_schreiben(merk_pfad, merk_werte(zugang, adresse, kuerzel, vorher))
    os.replace(tmp, merk_pfad)


def zurueck_lokal(merk_pfad):
    """Arbeitsplatz wieder lokal betreiben (die lokalen Daten sind unverändert). False, wenn es keine gab."""
    from . import datenspeicher
    merk_pfad = Path(merk_pfad)
    m = datenspeicher.merkdatei_lesen(merk_pfad) or {}
    if m.get("art") != ART:
        return False
    vorher = json.loads(m.get("vorher") or "{}")
    if not vorher:
        return False
    tmp = datenspeicher._merkdatei_schreiben(merk_pfad, vorher)
    os.replace(tmp, merk_pfad)
    abmelden()
    return True


_anmeldung = {}


def anmelden(kuerzel, passwort):
    """Anmeldedaten für den nächsten Verbindungsaufbau merken (nur im Speicher)."""
    _anmeldung.clear()
    _anmeldung.update(kuerzel=str(kuerzel or "").strip().upper(), passwort=str(passwort or ""))


def abmelden():
    _anmeldung.clear()


def angemeldet():
    return _anmeldung.get("kuerzel") or ""


class Sitzung:
    """Ergebnis der Anmeldung am Server (hängt an der Verbindung als v.server und an Datenbank.server)."""

    def __init__(self, **w):
        self.kuerzel = w.get("kuerzel", "")
        self.login = w.get("login", "")
        self.rolle = w.get("rolle", ROLLE_LESEN)
        self.verwalter = bool(w.get("verwalter"))
        self.zustand = w.get("zustand", OK)
        self.meldung = w.get("meldung", "")
        self.name = w.get("name", "")
        self.host = w.get("host", "")
        self.port = w.get("port", PORT)
        self.pflicht = w.get("pflicht", "")
        self.platz = w.get("platz") or platz()

    @property
    def nur_lesen(self):
        return self.rolle == ROLLE_LESEN or self.zustand in (VERALTET, VORAUS)

    @property
    def pflegen(self):
        """Darf und soll diese Sitzung die Datenpflege (Tabellen, Ergänzungen) ausführen?"""
        return self.zustand in (NEU, HEBEN)

    def text(self):
        recht = "Verwalter" if self.verwalter else "nur lesen" if self.nur_lesen else "bearbeiten"
        return (f"Server {self.name or self.host} ({self.host}:{self.port}), angemeldet als {self.kuerzel} "
                f"({recht}), Arbeitsplatz {self.platz}, Serverversion {self.pflicht or '–'}")


def zustand_bestimmen(pflicht, schema_server, programm, schema_programm, verwalter):
    """(Zustand, Meldung) aus Pflichtversion/Schema des Servers und eigener Version/Schema. ServerFehler, wenn
    dieser Arbeitsplatz gar nicht öffnen darf."""
    if not pflicht:
        if verwalter:
            return NEU, "Der Server ist neu: die Datenbank wird jetzt eingerichtet."
        raise ServerFehler("Der Server ist noch nicht eingerichtet. Zuerst muss sich ein Administrator mit dem "
                           "Programm anmelden.")
    p, ich = version_tupel(pflicht), version_tupel(programm)
    if p == ich:
        return OK, ""
    s_server = int(schema_server or 0)
    if ich > p and verwalter:
        return HEBEN, (f"Der Server läuft mit Version {pflicht}, dieses Programm ist {programm}. Der Server wird "
                       f"auf {programm} gehoben; danach müssen alle Arbeitsplätze aktualisieren.")
    if s_server != int(schema_programm):
        if ich < p:
            raise ServerFehler(f"Der Server verlangt Version {pflicht}, dieses Programm ist {programm}. Bitte das "
                               "Programm aktualisieren (Hilfe → Update-Center oder Update-Datei vom Administrator).")
        raise ServerFehler(f"Dieses Programm ({programm}) ist neuer als der Server ({pflicht}). Erst muss ein "
                           "Administrator mit dieser Version den Server umstellen.")
    if ich < p:
        return VERALTET, (f"Der Server verlangt Version {pflicht}, dieses Programm ist {programm}: nur Ansehen, "
                          "Ändern ist gesperrt, bis das Programm aktualisiert ist.")
    return VORAUS, (f"Dieses Programm ({programm}) ist neuer als der Server ({pflicht}): nur Ansehen, bis ein "
                    "Administrator den Server umgestellt hat.")


def _probe(z, passwort):
    """Anmeldung prüfen: Rechte und Serverangaben lesen (eigene kurze Verbindung, ohne Rolle)."""
    import psycopg
    werte = dict(host=z["host"], port=int(z["port"]), dbname=z["datenbank"], user=z["benutzer"], password=passwort,
                 sslmode=z["sslmode"], sslrootcert=z["sslrootcert"], application_name=ANWENDUNG,
                 connect_timeout=int(z.get("verbinden_s", 8)))
    try:
        con = psycopg.connect(autocommit=True, **werte)
    except psycopg.OperationalError as e:
        text = str(e)
        if "password authentication failed" in text or "Passwort-Authentifizierung" in text:
            raise AnmeldeFehler("Kürzel oder Passwort stimmt nicht.") from e
        if "not permitted to log in" in text or "darf sich nicht anmelden" in text:
            raise AnmeldeFehler("Dieser Benutzer ist am Server gesperrt.") from e
        if "certificate" in text.lower() or "zertifikat" in text.lower() or "SSL" in text:
            raise ZertifikatFehler("Der Server weist sich nicht mit dem erwarteten Zertifikat aus. Bitte die "
                                   "Zugangsdatei vom Administrator neu einlesen. (" + text.splitlines()[0] + ")") from e
        raise db_verbindung.VerbindungWeg(f"Keine Verbindung zum Server {z['host']}:{z['port']} – läuft der "
                                          f"Server-Rechner, ist das Netzwerk da? ({text.splitlines()[0]})") from e
    try:
        app, lesen, verw = con.execute(
            "SELECT pg_has_role(session_user, %s, 'MEMBER'), pg_has_role(session_user, %s, 'MEMBER'), "
            "pg_has_role(session_user, %s, 'MEMBER')", (ROLLE_APP, ROLLE_LESEN, ROLLE_VERWALTER)).fetchone()
        info = {}
        if app or lesen:
            con.execute(f'SET ROLE "{ROLLE_APP if app else ROLLE_LESEN}"')
            with contextlib.suppress(Exception):
                info = dict(con.execute(f"SELECT schluessel, wert FROM {INFO}").fetchall())
            with contextlib.suppress(Exception):
                info["_schema"] = str(db_verbindung.schema_version(_PsycopgHuelle(con)))
        return bool(app), bool(lesen), bool(verw), info
    finally:
        con.close()


class _PsycopgHuelle:
    """Minimale Hülle, damit db_verbindung.schema_version eine rohe psycopg-Verbindung lesen kann."""
    art = "postgres"

    def __init__(self, con):
        self.con = con

    def execute(self, sql, werte=()):
        return self.con.execute(db_verbindung.nach_postgres(sql), werte or None)


def zugang(merk_pfad, merk, kuerzel):
    return dict(art="postgres", host=merk["host"], port=int(merk.get("port") or PORT),
                datenbank=merk.get("datenbank") or DATENBANK, benutzer=login_name(kuerzel), sslmode="verify-ca",
                sslrootcert=str(ca_pfad(merk_pfad, merk)), anwendung=ANWENDUNG)


def oeffnen(merk_pfad, merk=None, programm=None, schema=None):
    """Verbindung zum zentralen Server für den angemeldeten Mitarbeiter. Ergebnis: PostgresVerbindung mit
    v.server (Sitzung). AnmeldungFehlt/AnmeldeFehler/ZertifikatFehler/ServerFehler/VerbindungWeg."""
    from . import VERSION, datenspeicher
    merk = merk or datenspeicher.merkdatei_lesen(merk_pfad) or {}
    if merk.get("art") != ART:
        raise ServerFehler("Dieser Arbeitsplatz ist nicht auf den Server eingestellt.")
    k = _anmeldung.get("kuerzel")
    if not k:
        raise AnmeldungFehlt("Bitte am Server anmelden.")
    if not ca_pfad(merk_pfad, merk).is_file():
        raise ZertifikatFehler("Das Zertifikat des Servers fehlt auf diesem Arbeitsplatz. Bitte die Zugangsdatei "
                               "neu einlesen.")
    z = zugang(merk_pfad, merk, k)
    pw = _anmeldung.get("passwort")
    app, lesen, verw, info = _probe(z, pw)
    if not (app or lesen):
        raise AnmeldeFehler(f"Der Benutzer {k} hat am Server keine Rechte (weder bearbeiten noch lesen).")
    if programm is None:
        programm = VERSION
    if schema is None:
        from .datenbank import SCHEMA_VERSION as schema
    zustand, meldung = zustand_bestimmen(info.get("programm"), info.get("_schema") or info.get("schema"), programm,
                                         schema, verw and app)
    if zustand == HEBEN and heben_fragen is not None and not heben_fragen(meldung):
        if int(info.get("_schema") or info.get("schema") or 0) != int(schema):
            raise ServerFehler(f"Ohne Umstellung des Servers kann diese Version ({programm}) die Daten nicht öffnen "
                               "(anderer Aufbau der Datenbank).")
        zustand, meldung = VORAUS, (f"Der Server bleibt auf Version {info.get('programm')}; dieses Programm "
                                    f"({programm}) öffnet nur zum Ansehen.")
    s = Sitzung(kuerzel=k, login=z["benutzer"], rolle=ROLLE_APP if app else ROLLE_LESEN, verwalter=verw and app,
                zustand=zustand, meldung=meldung, name=info.get("name") or merk.get("name", ""), host=z["host"],
                port=z["port"], pflicht=info.get("programm", ""))
    z["rolle"] = s.rolle
    v = db_verbindung.PostgresVerbindung(z, passwort=pw, nur_lesen=s.nur_lesen)
    v.server = s
    return v


def anmeldung_pruefen(merk_pfad, kuerzel, passwort, merk=None, zugang_=None):
    """Kürzel und Passwort am Server prüfen (kurze eigene Verbindung). Ergebnis: dict(recht, name, programm) oder
    AnmeldeFehler/ZertifikatFehler/VerbindungWeg. zugang_: gelesene Zugangsdatei (beim Einrichten, vor der
    Merkdatei) mit Adresse merk['host']."""
    from . import datenspeicher
    merk = merk or datenspeicher.merkdatei_lesen(merk_pfad) or {}
    z = zugang(merk_pfad, merk, kuerzel)
    tmp = None
    if zugang_ is not None:             # Zertifikat aus der Zugangsdatei (noch nicht abgelegt)
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False, encoding="ascii") as f:
            f.write(zugang_["ca"])
            tmp = f.name
        z["sslrootcert"] = tmp
    try:
        app, lesen, verw, info = _probe(z, passwort)
    finally:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    if not (app or lesen):
        raise AnmeldeFehler(f"Der Benutzer {kuerzel} hat am Server keine Rechte.")
    recht = RECHT_VERWALTER if verw and app else RECHT_BEARBEITEN if app else RECHT_LESEN
    return dict(recht=recht, name=info.get("name", ""), programm=info.get("programm", ""))


heben_fragen = None     # Oberfläche: Funktion(meldung) -> True/False, bevor ein Verwalter den Server anhebt


def pflege_fertig(con, programm, schema):
    """Nach erfolgreicher Datenpflege (Administrator): Server auf diese Version setzen."""
    info_einrichten(con)
    info_setzen(con, programm=programm, schema=schema, pflege=programm, gehoben=_jetzt(),
                gehoben_von=angemeldet())


# ------------------------------------------------------------------------------------------------ Einstellungen
# Welche Einstellungen gelten im Serverbetrieb für die ganze Firma, welche je Arbeitsplatz, welche je Benutzer?
# Grundsatz wie beim Abgleich über den gemeinsamen Ordner: was dort geteilt wurde (teilen.EINSTELLUNGEN_GETEILT),
# Admin-Vorgaben und Merker der Datenpflege gelten für alle; Anzeige-, Ordner- und Gerätewerte je Arbeitsplatz;
# Name, Signatur und Ansicht je Benutzer (ein Mitarbeiter nimmt sie an jeden Platz mit).
PLATZ_PRAEFIX = "@platz:"
BENUTZER_PRAEFIX = "@benutzer:"
BENUTZER_SCHLUESSEL = {"benutzer_name", "benutzer_email", "benutzer_telefon", "anfrage_signatur",
                       "anfrage_outlook_signatur", "material_favoriten", "ansicht_thema", "ansicht_schrift",
                       "ansicht_dichte", "ansicht_hilfe", "eingabe_richtung", "auftrag_schritte", "angebote_zeitraum"}
FIRMA_EXTRA = {"rp_eigene", "rp_stand", "online_vorgabe", "online_dateien", "versand_absender", "rahmen_aktiv",
               "kunden_letzte_nummer", "rahmen_letzte_nummer", "letzte_ab_nummer", "auftraege_migriert",
               "zeichnungen_entfernt", "stammdaten_herkunft", "hub_ab_weg_zurueck", "programmierung_teil",
               "kategorien", "passwort", "admin_liste", "admin_seiten", "admin_verlauf", "admin_vorgaben_stand"}
FIRMA_ENDUNGEN = ("_stand", "_zurueck", "_merker")


def _firma_namen():
    from . import admin_signatur, teilen
    return set(teilen.EINSTELLUNGEN_GETEILT) | set(admin_signatur.RECHTE) | FIRMA_EXTRA


_FIRMA = None


def bereich(name):
    """'firma', 'platz' oder 'benutzer' für eine Einstellung im Serverbetrieb."""
    global _FIRMA
    if name in BENUTZER_SCHLUESSEL:
        return "benutzer"
    if _FIRMA is None:
        _FIRMA = _firma_namen()
    if name in _FIRMA or name.endswith(FIRMA_ENDUNGEN):
        return "firma"
    return "platz"


def gespeicherter_name(sitzung, name):
    """Name der Zeile in der Tabelle einstellungen für diese Einstellung dieser Sitzung."""
    b = bereich(name)
    if b == "platz":
        return f"{PLATZ_PRAEFIX}{sitzung.platz}:{name}"
    if b == "benutzer":
        return f"{BENUTZER_PRAEFIX}{sitzung.kuerzel}:{name}"
    return name


def sicht(sitzung, texte):
    """Gespeicherte Einstellungen {name: json} so, wie diese Sitzung sie sieht: Firmenwerte, darüber die eigenen
    Arbeitsplatz- und Benutzerwerte; fremde Plätze/Benutzer unsichtbar. Werte je Platz/Benutzer, die nur als
    Firmenwert gespeichert sind (aus der Übernahme der lokalen Daten), gelten nicht: sonst bekäme jeder Platz die
    Ordner und das Kürzel des Administrators."""
    eigen_p = f"{PLATZ_PRAEFIX}{sitzung.platz}:"
    eigen_b = f"{BENUTZER_PRAEFIX}{sitzung.kuerzel}:"
    out, ueber = {}, {}
    for n, w in texte.items():
        if n.startswith("@"):
            if n.startswith(eigen_p):
                ueber[n[len(eigen_p):]] = w
            elif n.startswith(eigen_b):
                ueber[n[len(eigen_b):]] = w
            continue
        if bereich(n) == "firma":
            out[n] = w
    out.update(ueber)
    out["benutzer_kuerzel"] = json.dumps(sitzung.kuerzel)       # wer angemeldet ist, ist der Bearbeiter
    return out


# ------------------------------------------------------------------------------------------------ Nummern
def nummer_vergeben(db, bereich_, hoechster, format_, jahr, vergeben=None, zusatz=""):
    """Nächste Nummer eines Bereichs (Angebote, AB-Nummern) in einer Transaktion, für alle Arbeitsplätze eindeutig
    und nie zweimal (auch nicht nach Löschen). hoechster: höchster schon benutzter Zählerstand in den Daten;
    format_(jahr, n) -> Nummer; vergeben(nr) -> schon in Benutzung?"""
    s = db.server
    with db.con:
        db.con.beginnen()       # die Sperre gilt bis zum Ende der Transaktion (SELECT allein liefe sofort durch)
        db.con.execute(f"SELECT pg_advisory_xact_lock({NUMMER_SPERRE})")
        r = db.con.execute(f"SELECT MAX(zaehler) FROM {NUMMERN} WHERE bereich = ?", (bereich_,)).fetchone()
        n = max(int(r[0] or 0), int(hoechster or 0))
        while True:
            n += 1
            nr = format_(jahr, n)
            if vergeben is None or not vergeben(nr):
                break
        db.con.execute(f"INSERT INTO {NUMMERN} (bereich, zaehler, nummer, wer, platz, zeit) VALUES (?, ?, ?, ?, ?, ?)",
                       (bereich_, n, nr, s.kuerzel if s else "", s.platz if s else platz(), _jetzt() + zusatz))
    return nr


# ------------------------------------------------------------------------------------------------ Befehle
HILFE = """Rohrlaser-Server (Serverversion) – Befehle auf dem Server-Rechner:

  einrichten --ordner ORDNER --admin KÜRZEL [--name NAME] [--port 5432] [--adresse NAME_ODER_IP ...]
      neuen Server anlegen (PostgreSQL, Zertifikat, Rollen, erster Administrator) und die Zugangsdatei
      Arbeitsplatz-Zugang.rlserver im Ordner schreiben; das Passwort wird abgefragt
  starten --ordner ORDNER      Server starten (z. B. per Aufgabenplanung beim Hochfahren)
  stoppen --ordner ORDNER      Server sauber beenden
  status --ordner ORDNER       läuft er, Version, Verbindungen, Benutzer
  benutzer --ordner ORDNER --kuerzel KÜRZEL [--recht bearbeiten|lesen|verwalter] [--name NAME] [--sperren]
      Mitarbeiter anlegen oder ändern (Passwort wird abgefragt, außer bei --sperren)
  zugang --ordner ORDNER [--adresse NAME_ODER_IP ...]   Zugangsdatei neu schreiben
"""


def main(argv=None, eingabe=None, ausgabe=print):
    """Befehlszeile (python -m rohrlaser.server_betrieb … oder Rohrlaser-Kalkulation.exe --server …)."""
    import argparse
    import getpass
    p = argparse.ArgumentParser(prog="rohrlaser-server", description=HILFE,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("befehl", choices=("einrichten", "starten", "stoppen", "status", "benutzer", "zugang"))
    p.add_argument("--ordner", required=True)
    p.add_argument("--admin")
    p.add_argument("--name", default="")
    p.add_argument("--port", type=int, default=PORT)
    p.add_argument("--adresse", nargs="*", default=[])
    p.add_argument("--kuerzel")
    p.add_argument("--recht", choices=RECHTE, default=RECHT_BEARBEITEN)
    p.add_argument("--sperren", action="store_true")
    p.add_argument("--bin")
    a = p.parse_args(argv)
    lies = eingabe or (lambda frage: getpass.getpass(frage))

    def passwort_fragen(wer):
        eins = lies(f"Passwort für {wer} (mindestens 8 Zeichen): ")
        if eingabe is None and eins != lies("Noch einmal: "):
            raise ServerFehler("Die beiden Passwörter sind verschieden.")
        return eins
    s = ZentralerServer(a.ordner, a.bin, a.port, a.adresse)
    if a.befehl == "einrichten":
        if not a.admin:
            raise ServerFehler("Bitte --admin KÜRZEL angeben (erster Administrator).")
        pw = passwort_fragen(a.admin)
        datei = s.einrichten(a.name, a.admin, pw)
        ausgabe(f"Server eingerichtet in {s.daten}, Port {s.port}.\nZugangsdatei für die Arbeitsplätze: {datei}\n"
                f"Fingerabdruck des Zertifikats: {fingerabdruck(s.ca_pem())}")
    elif a.befehl == "starten":
        s.starten()
        ausgabe(f"Server läuft (Port {s.port}).")
    elif a.befehl == "stoppen":
        s.stoppen()
        ausgabe("Server beendet.")
    elif a.befehl == "status":
        if not s.laeuft():
            ausgabe("Server läuft nicht.")
            return 1
        with s.verwalter_verbinden(DATENBANK) as con:
            i = info_lesen(con)
            n = con.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = %s", (DATENBANK,)).fetchone()[0]
            ausgabe(f"Server {i.get('name', '')} läuft (Port {s.port}), Programmversion {i.get('programm', '–')}, "
                    f"Schema {i.get('schema', '–')}, {n} Verbindungen")
            for b in benutzer_liste(con):
                ausgabe(f"  {b['kuerzel']:<8} {b['recht']:<11} {'gesperrt' if b['gesperrt'] else ''} {b['name']}")
    elif a.befehl == "benutzer":
        if not a.kuerzel:
            raise ServerFehler("Bitte --kuerzel angeben.")
        with s.verwalter_verbinden(DATENBANK) as con:
            if a.sperren:
                benutzer_sperren(con, a.kuerzel, True)
                ausgabe(f"{a.kuerzel} gesperrt.")
            else:
                benutzer_anlegen(con, a.kuerzel, passwort_fragen(a.kuerzel), a.recht, a.name)
                ausgabe(f"{a.kuerzel} angelegt bzw. geändert ({a.recht}).")
    elif a.befehl == "zugang":
        ausgabe(f"Zugangsdatei: {s.zugang_schreiben(a.adresse or None)}")
    return 0


def konsole_main(argv):
    """Einstieg aus dem Fensterprogramm (Rohrlaser-Kalkulation.exe --server …): unter Windows an die Konsole der
    Eingabeaufforderung anhängen (sonst gäbe es weder Ausgabe noch Passwortabfrage). Ergebnis: Rückgabewert."""
    import sys
    if os.name == "nt":
        import ctypes
        k = ctypes.windll.kernel32
        if not k.AttachConsole(-1):
            k.AllocConsole()
        sys.stdout = sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        sys.stdin = open("CONIN$", encoding="utf-8", errors="replace")
    try:
        return main(argv)
    except (ServerFehler, db_verbindung.DbFehler, OSError, RuntimeError) as e:
        print(f"Fehler: {e}")
        return 2


if __name__ == "__main__":
    import sys
    sys.exit(konsole_main(sys.argv[1:]))
