"""Sicherung des zentralen Servers mit Rücksicherungsprobe (Serverversion S6, Patrick 26.11.2026). Ohne Qt.

Am Server-Rechner (per Aufgabenplanung täglich): ``--server sichern --ordner …``.
1. In einer Transaktion mit festem Stand (Snapshot) wird von jeder Tabelle Anzahl und Prüfsumme aller Zeilen
   ermittelt; pg_dump schreibt genau diesen Stand (``--snapshot``) mit Eigentümern und Rechten nach
   ``<Server-Ordner>/Sicherung/server_<Zeit>_<Anlass>.pgdump``. Dazu die Zugänge (``….rollen.sql``, pg_dumpall
   --roles-only, mit den Prüfwerten der Passwörter: Ordner schützen) und ``….json`` mit den Prüfwerten.
2. Rücksicherungsprobe: die Sicherung wird in eine Probe-Datenbank eingespielt, dort werden Anzahl und Prüfsumme
   jeder Tabelle erneut ermittelt und verglichen; dann wird die Probe gelöscht. Nur eine Sicherung, die so
   zurückgeholt werden konnte, gilt als gut.
3. Ergebnis (Zeit, Datei, Probe, Größe) steht in der Serverinfo: jeder Arbeitsplatz zeigt es unter Datei →
   Datenbank …, Verwalter werden gewarnt, wenn die letzte gute Sicherung älter als 36 Stunden ist.
Ältere tägliche Sicherungen über ``behalten`` hinaus werden gelöscht (vor_… Sicherungen bleiben).

Zurückholen: ``--server zurueckholen --ordner … --datei …pgdump``: erst wird der jetzige Stand gesichert, dann die
Sicherung in eine neue Datenbank eingespielt und geprüft; erst danach werden die Verbindungen getrennt und die
Datenbanken getauscht (die bisherige bleibt als ``rohrlaser_vor_<Zeit>``). Fehlen auf einem neuen Server-Rechner
Zugänge, kommen sie aus der Rollen-Datei (bestehende Zugänge und Passwörter bleiben unverändert).
"""
import contextlib
import datetime
import json
import re
import secrets
import time
from pathlib import Path

from . import pg_lokal
from . import server_betrieb as sb

ORDNER = "Sicherung"
ENDUNG = ".pgdump"
TAEGLICH = "taeglich"
BEHALTEN = 14
WARNEN_H = 36


class SicherungFehler(sb.ServerFehler):
    pass


# ------------------------------------------------------------------------------------------------ Hilfen
def ordner(server):
    return Path(server.daten) / ORDNER


def _programm(server, name):
    exe = Path(server.bin) / pg_lokal._exe(name)
    if not exe.exists():
        raise SicherungFehler(f"{name} fehlt ({exe}). Ohne pg_dump/pg_restore keine Serversicherung.")
    return str(exe)


def _umgebung(pw):
    import os
    umg = dict(os.environ, PGPASSWORD=pw or "", PGAPPNAME="Rohrlaser-Kalkulation (Serversicherung)",
               PGCONNECT_TIMEOUT="10")
    umg.pop("PGSERVICE", None)
    return umg


def _ziel(server, benutzer, datenbank):
    return ["-h", "127.0.0.1", "-p", str(server.port), "-U", benutzer, "-d", datenbank]


def _lauf(server, befehl, pw, timeout=3600):
    r = pg_lokal._lauf(befehl, env=_umgebung(pw), timeout=timeout)
    if r.returncode != 0:
        raise SicherungFehler(f"{Path(befehl[0]).stem}: {(r.stderr or r.stdout).strip()[:400]}")
    return r


def pruefwerte(con):
    """{Tabelle: [Anzahl, Prüfsumme]} aller Tabellen im Schema public (psycopg-Verbindung, im laufenden Stand)."""
    out = {}
    for (t,) in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
                            "AND table_type = 'BASE TABLE' ORDER BY table_name").fetchall():
        n, h = con.execute(f'SELECT count(*), md5(coalesce(string_agg(md5(t::text), \'\' ORDER BY md5(t::text)), '
                           f'\'\')) FROM "{t}" t').fetchone()
        out[t] = [int(n), h]
    return out


def _probe_loeschen(con, name):
    with contextlib.suppress(Exception):
        con.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _neue_datenbank(con, name):
    con.execute(f'CREATE DATABASE "{name}" OWNER "{pg_lokal.BENUTZER}" ENCODING \'UTF8\' TEMPLATE template0')


def _einspielen(server, datei, name):
    benutzer, pw = server._verwalter()
    _lauf(server, [_programm(server, "pg_restore"), *_ziel(server, benutzer, name), "--exit-on-error",
                   "--single-transaction", str(datei)], pw)


def _pruefwerte_in(server, name):
    with server.verwalter_verbinden(name) as con:
        return pruefwerte(con)


def _vergleich(soll, ist):
    """Liste der Abweichungen (leer = gleich)."""
    out = []
    for t in sorted(set(soll) | set(ist)):
        if t not in ist:
            out.append(f"{t} fehlt")
        elif t not in soll:
            out.append(f"{t} zu viel")
        elif list(soll[t]) != list(ist[t]):
            out.append(f"{t}: {soll[t][0]} → {ist[t][0]} Zeilen" + ("" if soll[t][0] != ist[t][0] else ", Inhalt"))
    return out


def probe(server, datei, soll):
    """Rücksicherungsprobe: Sicherung in eine Probe-Datenbank einspielen und mit den Prüfwerten soll vergleichen.
    Ergebnis: Liste der Abweichungen (leer = gut)."""
    name = f"rl_probe_{secrets.token_hex(4)}"
    with server.verwalter_verbinden() as con:
        _neue_datenbank(con, name)
    try:
        _einspielen(server, datei, name)
        return _vergleich(soll, _pruefwerte_in(server, name))
    finally:
        with server.verwalter_verbinden() as con:
            _probe_loeschen(con, name)


# ------------------------------------------------------------------------------------------------ Sichern
def sichern(server, anlass=TAEGLICH, behalten=BEHALTEN, melden=print):
    """Sicherung mit Rücksicherungsprobe (siehe oben). Ergebnis: Bericht (dict); SicherungFehler, wenn die Probe
    nicht gleich ist (die Datei bleibt dann liegen, gilt aber nicht als gut)."""
    melden = melden or (lambda _t: None)
    ziel = ordner(server)
    ziel.mkdir(parents=True, exist_ok=True)
    stamm = ziel / f"server_{datetime.datetime.now():%Y-%m-%d_%H%M%S}_{anlass}"
    datei, neu = stamm.with_suffix(ENDUNG), stamm.with_suffix(ENDUNG + ".neu")
    benutzer, pw = server._verwalter()
    t0 = time.monotonic()
    with server.verwalter_verbinden(sb.DATENBANK) as con, con.transaction():
        con.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        snapshot = con.execute("SELECT pg_export_snapshot()").fetchone()[0]
        soll = pruefwerte(con)
        _lauf(server, [_programm(server, "pg_dump"), *_ziel(server, benutzer, sb.DATENBANK), "-Fc", "-Z", "6",
                       f"--snapshot={snapshot}", "-f", str(neu)], pw)
    neu.replace(datei)
    rollen = stamm.with_suffix(".rollen.sql")
    _lauf(server, [_programm(server, "pg_dumpall"), "-h", "127.0.0.1", "-p", str(server.port), "-U", benutzer,
                   "--roles-only", "-f", str(rollen)], pw)
    abweichung = probe(server, datei, soll)
    dauer = time.monotonic() - t0
    gut = not abweichung
    mb = datei.stat().st_size / 1e6
    zeilen = sum(n for n, _h in soll.values())
    stamm.with_suffix(".json").write_text(json.dumps(dict(
        zeit=datetime.datetime.now().isoformat(timespec="seconds"), anlass=anlass, datei=datei.name, gut=gut,
        abweichung=abweichung, tabellen=soll), indent=1, ensure_ascii=False), encoding="utf-8")
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        werte = dict(sicherung_zeit=datetime.datetime.now().isoformat(timespec="seconds"), sicherung_datei=str(datei),
                     sicherung_probe="ok" if gut else "FEHLER: " + "; ".join(abweichung[:5]),
                     sicherung_mb=f"{mb:.1f}", sicherung_zeilen=str(zeilen))
        if gut:
            werte["sicherung_gut"] = werte["sicherung_zeit"]
        sb.info_setzen(con, **werte)
    weg = aufraeumen(server, behalten) if gut and anlass == TAEGLICH else []
    melden(f"Sicherung {datei.name}: {len(soll)} Tabellen, {zeilen} Zeilen, {mb:.1f} MB, {dauer:.0f} s. "
           + ("Rücksicherungsprobe: eingespielt und Zeile für Zeile gleich." if gut else
              "Rücksicherungsprobe: ABWEICHUNG – " + "; ".join(abweichung[:5])))
    if weg:
        melden(f"{len(weg)} ältere tägliche Sicherungen gelöscht (behalten: {behalten}).")
    if not gut:
        raise SicherungFehler("Rücksicherungsprobe nicht bestanden: " + "; ".join(abweichung[:5]))
    return dict(datei=datei, rollen=rollen, gut=gut, tabellen=len(soll), zeilen=zeilen, mb=mb, dauer_s=dauer,
                geloescht=weg)


def sicherungen(server):
    """[{datei, zeit, anlass, gut, mb}] neueste zuerst."""
    out = []
    for j in sorted(ordner(server).glob("server_*.json"), reverse=True):
        with contextlib.suppress(OSError, ValueError):
            d = json.loads(j.read_text(encoding="utf-8"))
            p = j.with_suffix(ENDUNG)
            if p.exists():
                out.append(dict(datei=p, zeit=d.get("zeit"), anlass=d.get("anlass"), gut=bool(d.get("gut")),
                                mb=p.stat().st_size / 1e6))
    return out


def aufraeumen(server, behalten=BEHALTEN):
    """Tägliche Sicherungen über die neuesten behalten hinaus löschen. Ergebnis: gelöschte Dateien."""
    taeglich = [s["datei"] for s in sicherungen(server) if s["anlass"] == TAEGLICH]
    weg = []
    for p in taeglich[max(int(behalten), 1):]:
        for endung in (ENDUNG, ".json", ".rollen.sql"):
            with contextlib.suppress(OSError):
                p.with_suffix(endung).unlink()
        weg.append(p)
    return weg


# ------------------------------------------------------------------------------------------------ Zurückholen
_CREATE = re.compile(r'^CREATE ROLE "?([^";\s]+)"?;', re.M)


def rollen_ergaenzen(server, datei):
    """Zugänge aus der Rollen-Datei anlegen, die es hier noch nicht gibt (neuer Server-Rechner); bestehende bleiben
    unverändert. Ergebnis: angelegte Rollen."""
    p = Path(datei).with_suffix(".rollen.sql")
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8")
    with server.verwalter_verbinden() as con:
        da = {r[0] for r in con.execute("SELECT rolname FROM pg_roles")}
        neu = [r for r in _CREATE.findall(text) if r not in da]
        for stmt in [s.strip() for s in text.split(";\n") if s.strip()]:
            if stmt.startswith("--") and "\n" not in stmt:
                continue
            zeilen = [z for z in stmt.splitlines() if not z.startswith("--")]
            s = "\n".join(zeilen).strip()
            if not s or s.upper().startswith(("SET ", "\\")):
                continue
            m = re.match(r'(CREATE|ALTER|COMMENT ON) ROLE "?([^"\s;]+)"?', s)
            if m and m.group(2) not in neu:
                continue
            if not m and not s.upper().startswith("GRANT "):
                continue
            with contextlib.suppress(Exception):
                con.execute(s)
    return neu


def zurueckholen(server, datei, melden=print):
    """Server auf den Stand einer Sicherung setzen (siehe oben). Ergebnis: Bericht (dict)."""
    melden = melden or (lambda _t: None)
    datei = Path(datei)
    if not datei.exists() or datei.suffix != ENDUNG:
        raise SicherungFehler(f"{datei} ist keine Serversicherung ({ENDUNG}).")
    try:
        soll = json.loads(datei.with_suffix(".json").read_text(encoding="utf-8")).get("tabellen")
    except (OSError, ValueError):
        soll = None
    neu_rollen = rollen_ergaenzen(server, datei)
    if neu_rollen:
        melden(f"Zugänge aus der Sicherung angelegt: {', '.join(neu_rollen)}")
    with server.verwalter_verbinden() as con:
        da = con.execute("SELECT 1 FROM pg_database WHERE datname = %s", (sb.DATENBANK,)).fetchone()
    vorher = None
    if da:
        vorher = sichern(server, anlass="vor_Zurueckholen", melden=melden)["datei"]
    name = f"rohrlaser_neu_{secrets.token_hex(3)}"
    with server.verwalter_verbinden() as con:
        _neue_datenbank(con, name)
    try:
        _einspielen(server, datei, name)
        if soll:
            abweichung = _vergleich(soll, _pruefwerte_in(server, name))
            if abweichung:
                raise SicherungFehler("Eingespielter Stand weicht von der Sicherung ab: " + "; ".join(abweichung[:5]))
    except BaseException:
        with server.verwalter_verbinden() as con:
            _probe_loeschen(con, name)
        raise
    alt = f"{sb.DATENBANK}_vor_{datetime.datetime.now():%Y%m%d_%H%M%S}"
    with server.verwalter_verbinden() as con:
        alte = [r[0] for r in con.execute("SELECT datname FROM pg_database WHERE datname LIKE %s",
                                          (f"{sb.DATENBANK}\\_vor\\_%",))]
        if da:
            con.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s "
                        "AND pid <> pg_backend_pid()", (sb.DATENBANK,))
            con.execute(f'ALTER DATABASE "{sb.DATENBANK}" RENAME TO "{alt}"')
        con.execute(f'ALTER DATABASE "{name}" RENAME TO "{sb.DATENBANK}"')
        for d in alte:                  # Stand vor einem früheren Zurückholen: steckt in den Sicherungen
            _probe_loeschen(con, d)
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        sb.rollen_einrichten(con)       # Verbindungsrecht auf die neue Datenbank, Serverfunktionen
    melden(f"Server auf den Stand von {datei.name} gesetzt" + (f" (geprüft: {len(soll)} Tabellen gleich)" if soll
                                                               else "") + ". Die Arbeitsplätze verbinden sich neu."
           + (f" Bisheriger Stand: Datenbank {alt}, Sicherung {vorher.name}." if vorher else ""))
    return dict(vorher=vorher, alt=alt if da else None, rollen=neu_rollen, geprueft=bool(soll))


# ------------------------------------------------------------------------------------------------ Anzeige
def zustand(info, jetzt=None):
    """(Text, warnen) aus der Serverinfo für Datei → Datenbank und die Warnung an Verwalter."""
    jetzt = jetzt or datetime.datetime.now()
    gut = info.get("sicherung_gut")
    probe_ = info.get("sicherung_probe") or ""
    if not info.get("sicherung_zeit"):
        return ("Serversicherung: noch keine – am Server-Rechner „--server sichern“ täglich per Aufgabenplanung "
                "einrichten (--server aufgaben).", True)
    try:
        alter_h = (jetzt - datetime.datetime.fromisoformat(gut)).total_seconds() / 3600 if gut else None
    except ValueError:
        alter_h = None
    text = (f"Serversicherung: zuletzt {info['sicherung_zeit'][:16].replace('T', ' ')}, "
            f"{info.get('sicherung_mb', '?')} MB, Rücksicherungsprobe {probe_ or '?'}")
    warnen = alter_h is None or alter_h > WARNEN_H or probe_ != "ok"
    if alter_h is None:
        text += " – noch keine gute Sicherung!"
    elif alter_h > WARNEN_H:
        text += f" – letzte gute Sicherung vor {alter_h / 24:.1f} Tagen!"
    return text, warnen


def status_text(db):
    return zustand(sb.info_lesen(db.con))[0]


# ------------------------------------------------------------------------------------------------ Aufgaben
def aufgaben(server, programm, ordner_, uhrzeit="22:30", anlegen=None):
    """Aufgaben für die Windows-Aufgabenplanung: Server beim Hochfahren starten, Rechner starten, täglich sichern.
    Ergebnis: Liste (Name, Befehlszeile). anlegen (Vorgabe: unter Windows) trägt sie mit schtasks ein."""
    import os
    import subprocess
    basis = f'"{programm}" --server {{}} --ordner "{ordner_}" --port {server.port}'
    liste = [("Rohrlaser-Server starten", "ONSTART", None, basis.format("starten")),
             ("Rohrlaser-Server Rechner", "ONSTART", None, basis.format("rechnen")),
             ("Rohrlaser-Server Sicherung", "DAILY", uhrzeit, basis.format("sichern"))]
    if anlegen is None:
        anlegen = os.name == "nt"
    out = []
    for name, art, zeit, befehl in liste:
        args = ["schtasks", "/Create", "/F", "/RU", "SYSTEM", "/RL", "HIGHEST", "/TN", name, "/SC", art,
                "/TR", befehl] + (["/ST", zeit] if zeit else []) + (["/DELAY", "0001:00"] if art == "ONSTART" and
                                                                     "rechnen" in befehl else [])
        if anlegen:
            r = subprocess.run(args, capture_output=True, text=True)
            if r.returncode != 0:
                raise SicherungFehler(f"Aufgabe {name}: {(r.stderr or r.stdout).strip()[:300]}")
        out.append((name, " ".join(a if " " not in a and '"' not in a else f'"{a}"' if '"' not in a else
                                   "'" + a + "'" for a in args)))
    return out
