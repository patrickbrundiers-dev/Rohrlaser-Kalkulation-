"""Planungsserver: HTTP-Schnittstelle (JSON), Anmeldung, Rollen und Live-Meldungen (Server-Sent Events) für die
Browser-Oberfläche in web/. Nur Python-Standardbibliothek, damit der Server als eine portable .exe ohne Installation
und ohne Admin-Rechte läuft.

Rollen: lesen (ansehen), planen (Aufträge, Belegungen, Stillstände), verwalten (zusätzlich Maschinen, Schichten,
Ausnahmen, Einstellungen, Benutzer, Sicherung). Jede schreibende Anfrage braucht den Kopf 'X-Planung: 1' (Schutz
gegen Formulare fremder Seiten). Nach jeder gespeicherten Änderung bekommen alle offenen Seiten über
/api/ereignisse eine Meldung und laden neu.
"""
import json
import mimetypes
import secrets
import threading
import time
import traceback
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import plan, VERSION
from .datenbank import Fehler, KonfliktFehler, ROLLEN

WEB = Path(__file__).parent / "web"
COOKIE = "planung_sitzung"
SITZUNG_STUNDEN = 12
STUFE = {r: i for i, r in enumerate(ROLLEN)}


class Ereignisse:
    """Zähler 'stand' + Bedingung: jede gespeicherte Änderung weckt alle wartenden Ereignis-Verbindungen."""

    def __init__(self):
        self.bed = threading.Condition()
        self.stand, self.letzte = 0, {}

    def melden(self, benutzer, was):
        with self.bed:
            self.stand += 1
            self.letzte = dict(stand=self.stand, benutzer=benutzer, was=was)
            self.bed.notify_all()

    def warten(self, stand, sekunden):
        with self.bed:
            self.bed.wait_for(lambda: self.stand != stand, timeout=sekunden)
            return self.stand, dict(self.letzte)


class NichtErlaubt(Exception):
    pass


class Planungsserver(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, adresse, db):
        super().__init__(adresse, Handler)
        self.db = db
        self.ereignisse = Ereignisse()
        self.sitzungen = {}
        self.sitzung_sperre = threading.Lock()

    def sitzung_neu(self, benutzer):
        token = secrets.token_urlsafe(32)
        with self.sitzung_sperre:
            self.sitzungen[token] = dict(benutzer=benutzer, zuletzt=time.time())
        return token

    def sitzung(self, token):
        with self.sitzung_sperre:
            s = self.sitzungen.get(token or "")
            if not s:
                return None
            if time.time() - s["zuletzt"] > SITZUNG_STUNDEN * 3600:
                del self.sitzungen[token]
                return None
            s["zuletzt"] = time.time()
            return s["benutzer"]

    def sitzungen_von(self, name, rolle=None, aktiv=True):
        """Nach einer Benutzeränderung: Rolle in offenen Sitzungen nachziehen bzw. Sitzungen beenden."""
        with self.sitzung_sperre:
            for t, s in list(self.sitzungen.items()):
                if s["benutzer"]["name"] == name:
                    if not aktiv:
                        del self.sitzungen[t]
                    elif rolle:
                        s["benutzer"]["rolle"] = rolle


class Handler(BaseHTTPRequestHandler):
    server_version = f"Rohrlaser-Planung/{VERSION}"
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):    # noqa: A002 - Name aus BaseHTTPRequestHandler
        pass

    # ------------------------------------------------------------------ Hilfen
    def _senden(self, status, daten=None, typ="application/json; charset=utf-8", kopf=None):
        body = daten if isinstance(daten, bytes) else json.dumps(daten, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (kopf or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise Fehler("Ungültige Anfrage (kein JSON)") from None

    def _token(self):
        c = SimpleCookie(self.headers.get("Cookie") or "")
        return c[COOKIE].value if COOKIE in c else None

    def _benutzer(self, rolle="lesen"):
        b = self.server.sitzung(self._token())
        if not b:
            raise PermissionError("Bitte anmelden")
        if STUFE[b["rolle"]] < STUFE[rolle]:
            raise NichtErlaubt(f"Dafür braucht es die Rolle '{rolle}'")
        return b

    def _gemeldet(self, benutzer, was):
        self.server.ereignisse.melden(benutzer["anzeige"], was)

    # ------------------------------------------------------------------ Verteilung
    def do_GET(self):
        self._bearbeiten("GET")

    def do_POST(self):
        self._bearbeiten("POST")

    def do_PUT(self):
        self._bearbeiten("PUT")

    def do_DELETE(self):
        self._bearbeiten("DELETE")

    def _bearbeiten(self, methode):
        url = urlparse(self.path)
        teile = [unquote(t) for t in url.path.strip("/").split("/") if t]
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if not teile or teile[0] != "api":
                return self._datei(methode, teile)
            if methode != "GET" and self.headers.get("X-Planung") != "1":
                raise NichtErlaubt("Anfrage ohne Kennung abgelehnt")
            return self._api(methode, teile[1:], q)
        except PermissionError as e:
            self._senden(HTTPStatus.UNAUTHORIZED, dict(fehler=str(e)))
        except NichtErlaubt as e:
            self._senden(HTTPStatus.FORBIDDEN, dict(fehler=str(e)))
        except KonfliktFehler as e:
            self._senden(HTTPStatus.CONFLICT, dict(fehler=str(e), aktuell=e.aktuell, letzte=e.letzte))
        except Fehler as e:
            self._senden(HTTPStatus.BAD_REQUEST, dict(fehler=str(e)))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:                              # Fehler im Server: Text an den Browser, Details ins Protokoll
            traceback.print_exc()
            self._senden(HTTPStatus.INTERNAL_SERVER_ERROR, dict(fehler="Interner Fehler im Planungsserver"))

    def _datei(self, methode, teile):
        if methode != "GET":
            return self._senden(HTTPStatus.METHOD_NOT_ALLOWED, dict(fehler="Nicht erlaubt"))
        name = "/".join(teile) or "index.html"
        pfad = (WEB / name).resolve()
        if WEB.resolve() not in pfad.parents or not pfad.is_file():
            return self._senden(HTTPStatus.NOT_FOUND, dict(fehler="Nicht gefunden"))
        typ = mimetypes.guess_type(pfad.name)[0] or "application/octet-stream"
        if typ.startswith("text/") or typ in ("application/javascript",):
            typ += "; charset=utf-8"
        self._senden(HTTPStatus.OK, pfad.read_bytes(), typ)

    def _api(self, methode, t, q):
        db = self.server.db
        r = (methode, t[0] if t else "")
        if r == ("GET", "status"):
            b = self.server.sitzung(self._token())
            return self._senden(200, dict(version=VERSION, eingerichtet=db.benutzer_anzahl() > 0, benutzer=b))
        if r == ("POST", "einrichten"):
            if db.benutzer_anzahl():
                raise NichtErlaubt("Die Planung ist schon eingerichtet")
            d = self._json()
            db.benutzer_anlegen(d.get("name"), d.get("passwort"), "verwalten", d.get("anzeige"))
            return self._anmelden(d)
        if r == ("POST", "anmelden"):
            return self._anmelden(self._json())
        if r == ("POST", "abmelden"):
            with self.server.sitzung_sperre:
                self.server.sitzungen.pop(self._token() or "", None)
            return self._senden(200, dict(ok=True), kopf={"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0"})
        if r == ("GET", "ereignisse"):
            self._benutzer()
            return self._ereignisse()
        if r == ("GET", "dashboard"):
            self._benutzer()
            return self._senden(200, plan.dashboard(db))
        if r == ("GET", "plan"):
            self._benutzer()
            if not q.get("von") or not q.get("bis"):
                raise Fehler("Zeitraum von/bis angeben")
            return self._senden(200, plan.plan(db, q["von"], q["bis"]))
        if r == ("POST", "plan") and t[1:] == ["vorschau"]:
            self._benutzer("planen")
            return self._senden(200, plan.vorschau(db, self._json()))
        if r == ("POST", "plan") and t[1:] == ["speichern"]:
            b = self._benutzer("planen")
            d = self._json()
            v = plan.vorschau(db, d.get("aenderung") or {})
            if v["fehler"]:
                raise Fehler("; ".join(v["fehler"]))
            db.belegungen_schreiben(v["schritte"], d.get("maschinen_versionen") or {}, b["anzeige"], d.get("grund"))
            self._gemeldet(b, "Plan")
            return self._senden(200, dict(ok=True))
        if r[1] == "auftraege":
            return self._auftraege(methode, t[1:], q)
        if r == ("GET", "historie"):
            self._benutzer()
            return self._senden(200, db.historie(q.get("objekt"), q.get("id"), int(q.get("anzahl") or 200)))
        if r == ("GET", "kalender"):
            self._benutzer()
            return self._senden(200, dict(db.kalender(), maschinen=db.maschinen()))
        if r[1] in ("maschinen", "ausnahmen", "feiertage", "stillstaende"):
            return self._kalender(methode, t, q)
        if r[1] == "einstellungen":
            if methode == "GET":
                self._benutzer()
                return self._senden(200, db.einstellungen())
            b = self._benutzer("verwalten")
            for n, w in self._json().items():
                db.einstellung_setzen(n, w, b["anzeige"])
            self._gemeldet(b, "Einstellungen")
            return self._senden(200, db.einstellungen())
        if r[1] == "benutzer":
            return self._benutzer_api(methode, t[1:])
        if r == ("PUT", "passwort"):
            b = self._benutzer()
            d = self._json()
            if not db.anmelden(b["name"], d.get("alt")):
                raise Fehler("Das bisherige Passwort stimmt nicht")
            db.benutzer_aendern(b["name"], b["anzeige"], passwort=d.get("neu"))
            return self._senden(200, dict(ok=True))
        if r == ("POST", "sicherung"):
            self._benutzer("verwalten")
            return self._senden(200, dict(pfad=str(db.sicherung())))
        return self._senden(HTTPStatus.NOT_FOUND, dict(fehler="Unbekannte Anfrage"))

    def _anmelden(self, d):
        b = self.server.db.anmelden(d.get("name"), d.get("passwort"))
        if not b:
            time.sleep(0.5)
            raise PermissionError("Name oder Passwort falsch")
        token = self.server.sitzung_neu(b)
        return self._senden(200, dict(benutzer=b),
                            kopf={"Set-Cookie": f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict"})

    def _ereignisse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        stand = self.server.ereignisse.stand
        self.wfile.write(f"event: stand\ndata: {json.dumps(dict(stand=stand))}\n\n".encode())
        self.wfile.flush()
        while True:
            neu, letzte = self.server.ereignisse.warten(stand, 20)
            if neu == stand:
                self.wfile.write(b": lebt\n\n")            # hält die Verbindung offen, erkennt geschlossene Seiten
            else:
                stand = neu
                self.wfile.write(f"event: aenderung\ndata: {json.dumps(letzte, ensure_ascii=False)}\n\n".encode())
            self.wfile.flush()

    def _auftraege(self, methode, t, q):
        db = self.server.db
        if methode == "GET" and not t:
            self._benutzer()
            return self._senden(200, db.auftraege())
        b = self._benutzer("planen")
        if methode == "POST" and not t:
            aid = db.auftrag_speichern(self._json(), b["anzeige"])
            self._gemeldet(b, "Auftrag")
            return self._senden(200, db.auftrag(aid))
        aid = int(t[0])
        if methode == "PUT":
            d = self._json()
            db.auftrag_speichern(d.get("daten") or {}, b["anzeige"], d.get("version"), aid)
            self._gemeldet(b, "Auftrag")
            return self._senden(200, db.auftrag(aid))
        if methode == "DELETE":
            db.auftrag_loeschen(aid, q.get("version"), b["anzeige"])
            self._gemeldet(b, "Auftrag")
            return self._senden(200, dict(ok=True))
        raise Fehler("Unbekannte Anfrage")

    def _kalender(self, methode, t, q):
        db = self.server.db
        art = t[0]
        if art == "maschinen" and methode == "PUT":
            b = self._benutzer("verwalten")
            d = self._json()
            if t[2:] == ["schichten"]:
                db.schichten_setzen(t[1], d.get("schichten") or [], b["anzeige"])
            else:
                db.maschine_aendern(t[1], d.get("daten") or {}, d.get("version"), b["anzeige"])
        elif art == "ausnahmen" and methode == "POST":
            b = self._benutzer("verwalten")
            db.ausnahme_anlegen(self._json(), b["anzeige"])
        elif art == "ausnahmen" and methode == "DELETE":
            b = self._benutzer("verwalten")
            db.ausnahme_loeschen(int(t[1]), b["anzeige"])
        elif art == "feiertage" and methode == "POST":
            b = self._benutzer("verwalten")
            n = db.feiertage_eintragen(self._json().get("jahr"), b["anzeige"])
            self._gemeldet(b, "Kalender")
            return self._senden(200, dict(eingetragen=n))
        elif art == "stillstaende" and methode == "POST":
            b = self._benutzer("planen")
            db.stillstand_anlegen(self._json(), b["anzeige"])
        elif art == "stillstaende" and methode == "DELETE":
            b = self._benutzer("planen")
            db.stillstand_loeschen(int(t[1]), b["anzeige"])
        else:
            raise Fehler("Unbekannte Anfrage")
        self._gemeldet(b, "Kalender")
        return self._senden(200, dict(db.kalender(), maschinen=db.maschinen()))

    def _benutzer_api(self, methode, t):
        db = self.server.db
        b = self._benutzer("verwalten")
        if methode == "GET":
            return self._senden(200, db.benutzer_liste())
        d = self._json()
        if methode == "POST":
            db.benutzer_anlegen(d.get("name"), d.get("passwort"), d.get("rolle"), d.get("anzeige"), b["anzeige"])
        elif methode == "PUT" and t:
            db.benutzer_aendern(t[0], b["anzeige"], d.get("rolle"), d.get("aktiv"), d.get("passwort"))
            self.server.sitzungen_von(t[0], d.get("rolle"), d.get("aktiv") is not False)
        else:
            raise Fehler("Unbekannte Anfrage")
        return self._senden(200, db.benutzer_liste())


def starten(db, host="0.0.0.0", port=8765):
    """Server anlegen (noch nicht laufen lassen): Planungsserver.serve_forever() startet ihn."""
    return Planungsserver((host, port), db)
