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
Ältere tägliche Sicherungen über ``behalten`` hinaus werden gelöscht; von ihnen bleiben je Woche (WOCHEN Wochen) und
je Monat (MONATE Monate) die neueste gute (vor_… Sicherungen bleiben immer).

Lückenlos (Patrick 27.11.2026, „durch alle Eventualitäten abgesichert“):
4. Die Ablage am Server (PDF, STEP, Anfragen, Austausch …) wird mit jeder Sicherung gespiegelt
   (dokumente_sicherung, ohne die Zwischenspeicher des Rechners); die Liste der Dateien liegt als
   ``….dokumente.json`` neben dem Abbild, ältere Dateistände bleiben 60 Tage.
5. Server-Einstellungen (Zertifikate der eigenen Zertifizierungsstelle, Zugangsdatei) kommen als
   ``….konfiguration.zip`` dazu: ein neuer Server-Rechner übernimmt sie mit ``zurueckholen --mit-zertifikat``, die
   Arbeitsplätze verbinden sich dann ohne neue Zugangsdatei.
6. Zweites Ziel (``sicherungsziel --pfad \\NAS\…``): jede gute Sicherung wird dorthin kopiert und per SHA-256
   nachgeprüft, die Ablage dort ein zweites Mal gespiegelt; Aufbewahrung wie oben. Misslingt das, warnt das Programm
   die Verwalter wie bei einer fehlenden Sicherung.
7. Aufgabenplanung: Sicherung mittags und abends (Vorgabe 12:30 und 22:30); eine verpasste Sicherung (Server aus)
   wird nachgeholt, sobald der Rechner wieder läuft; Ergebnis und Fehler stehen im Windows-Ereignisprotokoll
   (Anwendung, Quelle Rohrlaser-Server), damit die Überwachung der IT sie sieht.

Zurückholen: ``--server zurueckholen --ordner … --datei …pgdump``: erst wird der jetzige Stand gesichert, dann die
Sicherung in eine neue Datenbank eingespielt und geprüft; erst danach werden die Verbindungen getrennt und die
Datenbanken getauscht (die bisherige bleibt als ``rohrlaser_vor_<Zeit>``). Fehlen auf einem neuen Server-Rechner
Zugänge, kommen sie aus der Rollen-Datei (bestehende Zugänge und Passwörter bleiben unverändert).
"""
import contextlib
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import time
import zipfile
from pathlib import Path

from . import dokumente_sicherung as ds
from . import pg_lokal
from . import server_betrieb as sb

ORDNER = "Sicherung"
ENDUNG = ".pgdump"
TAEGLICH = "taeglich"
BEHALTEN = 14
WOCHEN = 8                  # dazu je Woche die neueste gute Sicherung, so viele Wochen
MONATE = 12                 # und je Monat die neueste gute, so viele Monate
WARNEN_H = 36
UHRZEITEN = "12:30,22:30"   # Vorgabe der Aufgabenplanung
KONFIG = ".konfiguration.zip"
KONFIG_DATEIEN = ("ca.crt", "ca.key", "server.crt", "server.key", sb.ZUGANG_DATEI)
NEBEN = (".json", ".rollen.sql", KONFIG, ds.LISTE)     # Begleitdateien eines Abbilds
ZIEL2 = "sicherung_ziel2"   # Serverinfo: Pfad des zweiten Ziels
EREIGNIS_QUELLE = "Rohrlaser-Server"


class SicherungFehler(sb.ServerFehler):
    pass


# ------------------------------------------------------------------------------------------------ Hilfen
def ordner(server):
    return Path(server.daten) / ORDNER


def _schuetzen(pfad, ordner_=False):
    """Nur der Eigentümer darf lesen (Sicherungen enthalten Geschäftsdaten und Prüfwerte der Passwörter). Unter
    Windows erbt der Ordner die Rechte des Server-Ordners."""
    import os
    if os.name != "nt":
        os.chmod(pfad, 0o700 if ordner_ else 0o600)


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


def neben(datei, endung):
    """Begleitdatei eines Abbilds (server_….pgdump → server_….json usw.)."""
    p = Path(datei)
    return p.with_name(p.stem + endung) if endung == ds.LISTE else p.with_suffix(endung)


def ablage_lokal(server, info=None):
    """Ablage am Server auf diesem Rechner: der eingetragene Pfad, wenn er hier erreichbar ist, sonst
    <Server-Ordner>/Ablage (wie der Rechner am Server)."""
    eingetragen = str((info or {}).get("ablage") or "").strip()
    return Path(eingetragen) if eingetragen and Path(eingetragen).is_dir() else server.ablage_ordner()


def _ablage_auslassen():
    from . import server_rechnen
    return (server_rechnen.CACHE, server_rechnen.EINGANG)


def konfiguration_sichern(server, ziel):
    """Zertifikate und Zugangsdatei des Server-Ordners als zip (ohne Passwörter: die Zugänge stehen in der
    Rollen-Datei). Ergebnis: Pfad oder None (nichts da)."""
    da = [n for n in KONFIG_DATEIEN if (Path(server.daten) / n).is_file()]
    if not da:
        return None
    tmp = Path(str(ziel) + ".neu")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for n in da:
            z.write(Path(server.daten) / n, n)
    os.replace(tmp, ziel)
    _schuetzen(ziel)
    return Path(ziel)


def konfiguration_zurueckholen(server, datei):
    """Zertifikate und Zugangsdatei aus der Sicherung in den Server-Ordner (neuer Server-Rechner): danach gilt der
    Fingerabdruck der alten Zugangsdatei wieder. Der Server muss danach neu starten. Ergebnis: Liste der Dateien."""
    p = neben(datei, KONFIG)
    if not p.exists():
        raise SicherungFehler(f"Zu {Path(datei).name} gibt es keine Server-Einstellungen ({p.name}).")
    daten = Path(server.daten)
    with zipfile.ZipFile(p) as z:
        namen = [n for n in z.namelist() if n in KONFIG_DATEIEN]
        for n in namen:
            ziel = daten / n
            tmp = ziel.with_name(ziel.name + ".neu")
            tmp.write_bytes(z.read(n))
            os.replace(tmp, ziel)
            if n.endswith(".key"):
                _schuetzen(ziel)
    for n in ("server.crt", "server.key"):              # PostgreSQL liest sie aus dem Datenordner
        if n in namen and Path(server.pg).is_dir():
            (Path(server.pg) / n).write_bytes((daten / n).read_bytes())
            with contextlib.suppress(OSError):
                os.chmod(Path(server.pg) / n, 0o600)
    return namen


def _sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def ziel2_lesen(server):
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        return str(sb.info_lesen(con).get(ZIEL2) or "").strip()


def ziel2_setzen(server, pfad):
    """Zweites Ziel eintragen (leer = keins). Der Ordner muss erreichbar und beschreibbar sein."""
    pfad = str(pfad or "").strip()
    if pfad:
        o = Path(pfad)
        try:
            o.mkdir(parents=True, exist_ok=True)
            probe_ = o / f".rl_probe_{secrets.token_hex(3)}"
            probe_.write_bytes(b"ok")
            probe_.unlink()
        except OSError as e:
            raise SicherungFehler(f"Zweites Ziel {pfad} ist nicht beschreibbar: {e}") from e
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        sb.info_setzen(con, **{ZIEL2: pfad})
    return pfad


def zweitkopie(datei, ziel2, ablage, behalten=BEHALTEN):
    """Abbild mit Begleitdateien nach ziel2 kopieren, jede Datei per SHA-256 nachprüfen, die Ablage dort spiegeln,
    ältere Stände dort aufräumen. Ergebnis: dict(dateien, ablage, geloescht); SicherungFehler bei Abweichung."""
    ziel2 = Path(ziel2)
    ziel2.mkdir(parents=True, exist_ok=True)
    kopiert = []
    for endung in (ENDUNG, *NEBEN):
        q = neben(datei, endung)
        if not q.exists():
            continue
        z = ziel2 / q.name
        tmp = z.with_name(z.name + ".neu")
        shutil.copyfile(q, tmp)
        if _sha256(tmp) != _sha256(q):
            with contextlib.suppress(OSError):
                tmp.unlink()
            raise SicherungFehler(f"Zweites Ziel: {q.name} kam nicht unverändert an (SHA-256).")
        os.replace(tmp, z)
        kopiert.append(z)
    dok = ds.spiegeln(ablage, ziel2, liste_fuer=ziel2 / Path(datei).name, auslassen=_ablage_auslassen()) \
        if Path(ablage).is_dir() else None
    return dict(dateien=kopiert, ablage=dok, geloescht=aufraeumen_ordner(ziel2, behalten))


def ereignis(text, fehler=False):
    """Eintrag im Windows-Ereignisprotokoll (Anwendung, Quelle Rohrlaser-Server) für die Überwachung der IT.
    Andere Systeme oder ohne Recht: nichts."""
    if os.name != "nt":
        return False
    import subprocess
    with contextlib.suppress(Exception):
        r = subprocess.run(["eventcreate", "/L", "APPLICATION", "/SO", EREIGNIS_QUELLE, "/T",
                            "ERROR" if fehler else "INFORMATION", "/ID", "201" if fehler else "200",
                            "/D", text[:30000]], capture_output=True, timeout=30)
        return r.returncode == 0
    return False


# Textform der Werte unabhängig von den Einstellungen des Servers (Zeitzone, Datumsform …): sonst unterschieden sich
# die Prüfsummen derselben Daten auf einem anders eingestellten neuen Server-Rechner
_GLEICHE_TEXTFORM = ("SET TIME ZONE 'UTC'", "SET DateStyle = 'ISO, YMD'", "SET IntervalStyle = 'postgres'",
                     "SET extra_float_digits = 1", "SET bytea_output = 'hex'")


def pruefwerte(con):
    """{Tabelle: [Anzahl, Prüfsumme]} aller Tabellen im Schema public (psycopg-Verbindung, im laufenden Stand)."""
    for befehl in _GLEICHE_TEXTFORM:
        con.execute(befehl)
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
    _schuetzen(ziel, ordner_=True)
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
    _schuetzen(datei)
    rollen = stamm.with_suffix(".rollen.sql")
    _lauf(server, [_programm(server, "pg_dumpall"), "-h", "127.0.0.1", "-p", str(server.port), "-U", benutzer,
                   "--roles-only", "-f", str(rollen)], pw)
    _schuetzen(rollen)
    konfiguration_sichern(server, neben(datei, KONFIG))
    abweichung = probe(server, datei, soll)
    gut = not abweichung
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        info = sb.info_lesen(con)
    ablage = ablage_lokal(server, info)
    dok = None
    if gut:                                 # 4. Ablage mitsichern
        dok = ds.spiegeln(ablage, ziel, liste_fuer=datei, auslassen=_ablage_auslassen()) if ablage.is_dir() \
            else dict(dateien=0, neu=0, geaendert=0, weg=0, bytes=0, fehler=[f"Ablage {ablage} nicht erreichbar"])
        for p_ in (neben(datei, ds.LISTE),):
            if p_.exists():
                _schuetzen(p_)
    dauer = time.monotonic() - t0
    mb = datei.stat().st_size / 1e6
    zeilen = sum(n for n, _h in soll.values())
    neben(datei, ".json").write_text(json.dumps(dict(
        zeit=datetime.datetime.now().isoformat(timespec="seconds"), anlass=anlass, datei=datei.name, gut=gut,
        abweichung=abweichung, tabellen=soll, ablage=None if dok is None else dict(
            ordner=str(ablage), dateien=dok["dateien"], mb=round(dok["bytes"] / 1e6, 1), fehler=dok["fehler"][:20])),
        indent=1, ensure_ascii=False), encoding="utf-8")
    _schuetzen(neben(datei, ".json"))
    weg = aufraeumen(server, behalten) if gut and anlass == TAEGLICH else []
    # 6. zweites Ziel
    z2, z2_text = (info.get(ZIEL2) or "").strip(), ""
    if gut and z2:
        try:
            k = zweitkopie(datei, z2, ablage, behalten)
            z2_text = "ok"
            melden(f"Zweites Ziel {z2}: {len(k['dateien'])} Dateien kopiert und per SHA-256 geprüft"
                   + (f", Ablage gespiegelt ({k['ablage']['dateien']} Dateien)" if k["ablage"] else "") + ".")
        except (OSError, SicherungFehler) as e:
            z2_text = f"FEHLER: {e}"[:300]
            melden(f"Zweites Ziel {z2}: {e}")
    with server.verwalter_verbinden(sb.DATENBANK) as con:
        werte = dict(sicherung_zeit=datetime.datetime.now().isoformat(timespec="seconds"), sicherung_datei=str(datei),
                     sicherung_probe="ok" if gut else "FEHLER: " + "; ".join(abweichung[:5]),
                     sicherung_mb=f"{mb:.1f}", sicherung_zeilen=str(zeilen))
        if gut:
            werte["sicherung_gut"] = werte["sicherung_zeit"]
        if dok is not None:
            werte["sicherung_ablage"] = (f"{dok['dateien']} Dateien" + (f", {len(dok['fehler'])} nicht lesbar"
                                                                          if dok["fehler"] else ""))
        if z2_text:
            werte["sicherung_ziel2_probe"] = z2_text
            if z2_text == "ok":
                werte["sicherung_ziel2_gut"] = werte["sicherung_zeit"]
        sb.info_setzen(con, **werte)
    melden(f"Sicherung {datei.name}: {len(soll)} Tabellen, {zeilen} Zeilen, {mb:.1f} MB, {dauer:.0f} s. "
           + ("Rücksicherungsprobe: eingespielt und Zeile für Zeile gleich." if gut else
              "Rücksicherungsprobe: ABWEICHUNG – " + "; ".join(abweichung[:5])))
    if dok is not None:
        melden(f"Ablage gesichert: {dok['dateien']} Dateien ({dok['neu']} neu, {dok['geaendert']} geändert, "
               f"{dok['weg']} gelöscht)" + (f"; nicht lesbar: {'; '.join(dok['fehler'][:3])}" if dok["fehler"] else "")
               + ".")
    if weg:
        melden(f"{len(weg)} ältere tägliche Sicherungen gelöscht (behalten: {behalten} Tage, dazu je Woche und "
               "Monat eine).")
    if not gut:
        raise SicherungFehler("Rücksicherungsprobe nicht bestanden: " + "; ".join(abweichung[:5]))
    if z2_text.startswith("FEHLER"):
        raise SicherungFehler(f"Sicherung gut, aber zweites Ziel fehlgeschlagen: {z2_text[8:]}")
    return dict(datei=datei, rollen=rollen, gut=gut, tabellen=len(soll), zeilen=zeilen, mb=mb, dauer_s=dauer,
                geloescht=weg, ablage=dok, ziel2=z2_text or None)


def sicherungen(server):
    """[{datei, zeit, anlass, gut, mb}] neueste zuerst."""
    return sicherungen_in(ordner(server))


def sicherungen_in(o):
    """Wie sicherungen, für einen Sicherungsordner (auch das zweite Ziel)."""
    out = []
    for j in sorted(Path(o).glob("server_*.json"), reverse=True):
        if j.name.endswith(ds.LISTE):
            continue
        with contextlib.suppress(OSError, ValueError):
            d = json.loads(j.read_text(encoding="utf-8"))
            p = j.with_suffix(ENDUNG)
            if p.exists():
                out.append(dict(datei=p, zeit=d.get("zeit"), anlass=d.get("anlass"), gut=bool(d.get("gut")),
                                mb=p.stat().st_size / 1e6))
    return out


def aufraeumen(server, behalten=BEHALTEN):
    """Tägliche Sicherungen über die neuesten behalten hinaus löschen; je Woche (WOCHEN) und je Monat (MONATE) bleibt
    die neueste gute. Ergebnis: gelöschte Dateien."""
    return aufraeumen_ordner(ordner(server), behalten)


def bleiben(taeglich, behalten=BEHALTEN, wochen=WOCHEN, monate=MONATE):
    """Welche täglichen Sicherungen bleiben (Liste neueste zuerst, Einträge wie sicherungen): die neuesten behalten
    und je Woche/Monat die neueste gute (Generationen). Ergebnis: Menge der Dateien."""
    bleibt = {x["datei"] for x in taeglich[:max(int(behalten), 1)]}
    w_gesehen, m_gesehen = set(), set()
    for x in taeglich:
        if not x["gut"]:
            continue
        try:
            tag = datetime.datetime.fromisoformat(str(x["zeit"])).date()
        except ValueError:
            continue
        w, m = tuple(tag.isocalendar())[:2], (tag.year, tag.month)
        if w not in w_gesehen and len(w_gesehen) < wochen:
            w_gesehen.add(w)
            bleibt.add(x["datei"])
        if m not in m_gesehen and len(m_gesehen) < monate:
            m_gesehen.add(m)
            bleibt.add(x["datei"])
    return bleibt


def aufraeumen_ordner(o, behalten=BEHALTEN):
    taeglich = [s for s in sicherungen_in(o) if s["anlass"] == TAEGLICH]
    bleibt = bleiben(taeglich, behalten)
    weg = []
    for x in taeglich:
        p = x["datei"]
        if p in bleibt:
            continue
        for endung in (ENDUNG, *NEBEN):
            with contextlib.suppress(OSError):
                neben(p, endung).unlink()
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


def zurueckholen(server, datei, melden=print, mit_ablage=True, mit_zertifikat=False):
    """Server auf den Stand einer Sicherung setzen (siehe oben). mit_ablage: auch die Dateien der Ablage auf den Stand
    der Sicherung bringen (fehlende zurück, abweichende ersetzt, der abweichende Stand nach _vor_Wiederherstellung,
    später entstandene bleiben). mit_zertifikat: Zertifikate und Zugangsdatei aus der Sicherung (neuer
    Server-Rechner; danach Server neu starten). Ergebnis: Bericht (dict)."""
    melden = melden or (lambda _t: None)
    datei = Path(datei)
    if not datei.exists() or datei.suffix != ENDUNG:
        raise SicherungFehler(f"{datei} ist keine Serversicherung ({ENDUNG}).")
    try:
        merk = json.loads(datei.with_suffix(".json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SicherungFehler(f"Zu {datei.name} fehlen die Prüfwerte ({datei.with_suffix('.json').name}): ohne sie "
                              f"lässt sich der eingespielte Stand nicht prüfen ({e}).") from e
    soll = merk.get("tabellen") if isinstance(merk, dict) else None
    if not soll:
        raise SicherungFehler(f"{datei.with_suffix('.json').name} enthält keine Prüfwerte.")
    if not merk.get("gut"):
        raise SicherungFehler(f"{datei.name} hat die Rücksicherungsprobe nicht bestanden; bitte eine andere "
                              "Sicherung wählen (Liste: sicherungen).")
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
        info = sb.info_lesen(con)
    melden(f"Server auf den Stand von {datei.name} gesetzt (geprüft: {len(soll)} Tabellen gleich). Die "
           "Arbeitsplätze verbinden sich neu."
           + (f" Bisheriger Stand: Datenbank {alt}, Sicherung {vorher.name}." if vorher else ""))
    dok = None
    if mit_ablage and ds.liste(datei) is not None:
        ablage = ablage_lokal(server, info)
        ablage.mkdir(parents=True, exist_ok=True)
        dok = ds.zurueckholen(datei, ablage)
        melden(f"Ablage {ablage} auf den Stand der Sicherung: {dok['zurueck']} zurückgelegt, {dok['ersetzt']} "
               f"ersetzt (alter Stand in {ds.VOR_WIEDERHERSTELLUNG}), {dok['unveraendert']} unverändert"
               + (f"; nicht mehr in der Sicherung: {len(dok['fehlt'])}" if dok["fehlt"] else "") + ".")
    zert = []
    if mit_zertifikat:
        zert = konfiguration_zurueckholen(server, datei)
        melden(f"Server-Einstellungen aus der Sicherung: {', '.join(zert)}. Die bisherige Zugangsdatei gilt wieder; "
               "der Server startet neu.")
    return dict(vorher=vorher, alt=alt if da else None, rollen=neu_rollen, geprueft=True, ablage=dok,
                zertifikat=zert)


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
    if info.get("sicherung_ablage"):
        text += f"; Ablage {info['sicherung_ablage']}"
    z2 = str(info.get(ZIEL2) or "").strip()
    if z2:
        z2_gut = info.get("sicherung_ziel2_gut")
        try:
            z2_h = (jetzt - datetime.datetime.fromisoformat(z2_gut)).total_seconds() / 3600 if z2_gut else None
        except ValueError:
            z2_h = None
        if z2_h is None or z2_h > WARNEN_H:
            warnen = True
            text += f"; zweites Ziel {z2}: " + (str(info.get("sicherung_ziel2_probe") or "noch keine Kopie") + "!")
        else:
            text += f"; zweites Ziel {z2}: Kopie ok"
    else:
        text += "; kein zweites Ziel eingetragen (sicherungsziel)"
    return text, warnen


def status_text(db):
    return zustand(sb.info_lesen(db.con))[0]


# ------------------------------------------------------------------------------------------------ Aufgaben
def konto_vorgabe():
    """Windows-Konto, unter dem die Aufgaben laufen: das Konto, das den Server eingerichtet hat (ihm gehört der
    Datenordner; SYSTEM dürfte ihn nicht lesen)."""
    import getpass
    import os
    dom = os.environ.get("USERDOMAIN", "")
    return f"{dom}\\{getpass.getuser()}" if dom else getpass.getuser()


def _uhrzeiten(uhrzeit):
    """'12:30,22:30' → ['12:30', '22:30'] (geprüft, sortiert, ohne doppelte)."""
    out = []
    for t in re.split(r"[,;\s]+", str(uhrzeit or "").strip()):
        if not t:
            continue
        m = re.fullmatch(r"(\d{1,2}):(\d{2})", t)
        if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise SicherungFehler(f"Uhrzeit {t!r}: bitte als HH:MM, mehrere mit Komma (z. B. 12:30,22:30).")
        out.append(f"{int(m.group(1)):02d}:{m.group(2)}")
    return sorted(set(out)) or ["22:30"]


def _xml(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def aufgabe_xml(programm, argumente, beim_start=False, uhrzeiten=(), verzoegerung=None, zeitlimit="PT0S"):
    """Aufgabe für die Windows-Aufgabenplanung als XML (schtasks /XML): mit „Verpasste Ausführung so bald wie möglich
    nachholen“ (StartWhenAvailable), Neustart bei Fehlschlag (3× alle 15 min), auch im Akkubetrieb, keine zweite
    Instanz; läuft mit höchsten Rechten auch ohne Anmeldung (Konto und Passwort gibt schtasks dazu)."""
    ausloeser = []
    if beim_start:
        ausloeser.append("<BootTrigger><Enabled>true</Enabled>"
                         + (f"<Delay>{verzoegerung}</Delay>" if verzoegerung else "") + "</BootTrigger>")
    for t in uhrzeiten:
        ausloeser.append(f"<CalendarTrigger><StartBoundary>2026-01-01T{t}:00</StartBoundary><Enabled>true</Enabled>"
                         "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>")
    return ('<?xml version="1.0" encoding="UTF-16"?>\n'
            '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">'
            f"<RegistrationInfo><Author>{_xml(sb.ANWENDUNG)}</Author></RegistrationInfo>"
            f"<Triggers>{''.join(ausloeser)}</Triggers>"
            '<Principals><Principal id="Author"><LogonType>Password</LogonType>'
            "<RunLevel>HighestAvailable</RunLevel></Principal></Principals>"
            "<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>"
            "<DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>"
            "<StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>"
            "<StartWhenAvailable>true</StartWhenAvailable>"
            "<RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>"
            "<IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>"
            "<AllowStartOnDemand>true</AllowStartOnDemand><Enabled>true</Enabled><Hidden>false</Hidden>"
            "<RunOnlyIfIdle>false</RunOnlyIfIdle><WakeToRun>false</WakeToRun>"
            f"<ExecutionTimeLimit>{zeitlimit}</ExecutionTimeLimit><Priority>7</Priority>"
            "<RestartOnFailure><Interval>PT15M</Interval><Count>3</Count></RestartOnFailure></Settings>"
            f'<Actions Context="Author"><Exec><Command>{_xml(programm)}</Command>'
            f"<Arguments>{_xml(argumente)}</Arguments></Exec></Actions></Task>")


def aufgaben(server, programm, ordner_, uhrzeit=UHRZEITEN, anlegen=None, konto=None, passwort=None):
    """Aufgaben für die Windows-Aufgabenplanung: Server beim Hochfahren starten, Rechner starten, sichern zu den
    Uhrzeiten (Vorgabe mittags und abends; eine verpasste Sicherung wird nachgeholt); sie laufen unter konto
    (Vorgabe: dieses Konto, dem der Datenordner gehört), auch ohne Anmeldung (dafür das Windows-Passwort des
    Kontos). Ergebnis: Liste (Name, Beschreibung mit Befehlszeile ohne Passwort). anlegen (Vorgabe: unter Windows)
    trägt sie mit schtasks /XML ein."""
    import subprocess
    import tempfile
    konto = konto or konto_vorgabe()
    zeiten = _uhrzeiten(uhrzeit)
    basis = f'--server {{}} --ordner "{ordner_}" --port {server.port}'
    liste = [("Rohrlaser-Server starten", "beim Hochfahren", basis.format("starten"),
              aufgabe_xml(programm, basis.format("starten"), beim_start=True)),
             ("Rohrlaser-Server Rechner", "beim Hochfahren (1 min später)", basis.format("rechnen"),
              aufgabe_xml(programm, basis.format("rechnen"), beim_start=True, verzoegerung="PT1M")),
             ("Rohrlaser-Server Sicherung", "täglich " + ", ".join(zeiten) + ", verpasste nachholen",
              basis.format("sichern"), aufgabe_xml(programm, basis.format("sichern"), uhrzeiten=zeiten,
                                                   zeitlimit="PT6H"))]
    if anlegen is None:
        anlegen = os.name == "nt"
    out = []
    for name, wann, argumente, xml in liste:
        args = ["schtasks", "/Create", "/F", "/TN", name, "/XML", "<XML>", "/RU", konto]
        if anlegen:
            with tempfile.TemporaryDirectory() as tmp:
                datei = Path(tmp) / "aufgabe.xml"
                datei.write_text(xml, encoding="utf-16")
                befehl = [str(datei) if a == "<XML>" else a for a in args] + (["/RP", passwort] if passwort else [])
                r = subprocess.run(befehl, capture_output=True, text=True)
            if r.returncode != 0:
                raise SicherungFehler(f"Aufgabe {name}: {(r.stderr or r.stdout).strip()[:300]}")
        out.append((name, f"{wann}: \"{programm}\" {argumente} (Konto {konto})"))
    return out
