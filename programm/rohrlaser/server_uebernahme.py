"""Verlustfreie Übernahme der bisherigen Daten in den zentralen Server (Serverversion S5, Patrick 26.11.2026). Ohne Qt.

Bisher arbeitet jeder PC mit eigener Datenbank und gleicht über den gemeinsamen Ordner ab: Stammdaten, Einstellungen
und alle Angebote liegen danach an jedem PC, die Angebote der Kollegen als Kopie zum Ansehen (fremd = Kürzel).
Der Weg in den Server, am Server-Rechner in der Eingabeaufforderung:

1. Am Haupt-PC abgleichen und unter Datei → Daten exportieren … eine Export-Datei (.zip) oder eine Sicherung (.db)
   schreiben, dann am Server: ``--server uebernehmen --ordner … --datei Export.zip``. Alles kommt in den Server
   (alle Tabellen, die es in beiden gibt; gemeinsame Spalten), in einer Transaktion. Danach wird jede Tabelle Zeile
   für Zeile mit der Quelle verglichen (Anzahl und Inhalt, mit genau der Umwandlung, die das Einlesen macht); weicht
   etwas ab, wird alles zurückgerollt. Kopien von Angeboten der Kollegen werden zu deren Angeboten (bearbeiter =
   Kürzel, fremd leer), Einstellungen je Arbeitsplatz/Benutzer des Servers bleiben.
2. Jeder weitere PC (falls er seit dem letzten Abgleich etwas geändert hat): ``--server dazunehmen --ordner …
   --datei Export_AB.zip --kuerzel AB``: seine eigenen Angebote ersetzen den Stand am Server (der Bearbeiter hat die
   neueste Fassung), neue kommen dazu; jedes wird danach mit der Quelle verglichen.
Vor jedem Schreiben sichert der Server seinen Stand (SQLite-Datei und, wenn pg_dump da ist, ein Abbild) in
<Server-Ordner>/Sicherung. Die Quelle bleibt unverändert. Das Schema der Quelle muss gleich dem des Servers sein
(sonst erst den PC aktualisieren): so gibt es keine Umbauten unterwegs.
"""
import collections
import contextlib
import datetime
import hashlib
import json
import sqlite3
from pathlib import Path

from . import db_kopie, db_verbindung
from . import server_betrieb as sb

SICHERUNG_ORDNER = "Sicherung"


class UebernahmeFehler(sb.ServerFehler):
    pass


# ------------------------------------------------------------------------------------------------ Verbindung
@contextlib.contextmanager
def verbinden(server):
    """Hülle (wie db.con) als Verwalter des Servers: darf Trigger beim Kopieren ruhen lassen."""
    benutzer, pw = server._verwalter()
    v = db_verbindung.PostgresVerbindung(dict(host="127.0.0.1", port=server.port, datenbank=sb.DATENBANK,
                                              benutzer=benutzer, anwendung="Rohrlaser-Kalkulation (Übernahme)"),
                                         pw, zeitlimit_ms=0)
    con = db_verbindung.KompatVerbindung(v)
    try:
        yield con
    finally:
        with contextlib.suppress(Exception):
            v.schliessen()


@contextlib.contextmanager
def quelle_oeffnen(pfad):
    """sqlite3-Verbindung (nur lesen) zu einer Sicherung (.db) oder Export-Datei (.zip), geprüft."""
    from . import datenbank
    with datenbank._quelle_entpacken(pfad) as datei:
        info = datenbank.datei_pruefen(datei)
        con = sqlite3.connect(f"file:{Path(datei).as_posix()}?mode=ro", uri=True)
        try:
            yield con, info
        finally:
            con.close()


# ------------------------------------------------------------------------------------------------ Vergleich
def _norm(w, art):
    """Wert so, wie er nach dem Einlesen in PostgreSQL steht, in vergleichbarer Form."""
    if art is not None:
        w, _ = db_kopie.wert_fuer_pg(w, art)
    if w is None:
        return None
    if isinstance(w, bool):
        return float(int(w))
    if isinstance(w, (int, float)):
        return round(float(w), 9)
    if isinstance(w, (bytes, bytearray, memoryview)):
        return "b:" + hashlib.sha1(bytes(w)).hexdigest()
    if isinstance(w, (datetime.datetime, datetime.date)):
        return w.isoformat()
    return str(w)


def _zeilen_abdruck(zeilen, arten):
    z = collections.Counter()
    for r in zeilen:
        z[hashlib.sha1(json.dumps([_norm(w, a) for w, a in zip(r, arten)], ensure_ascii=False,
                                  default=str).encode()).hexdigest()] += 1
    return z


def gemeinsame_tabellen(quelle, con):
    """{Tabelle: [gemeinsame Spalten]} der Tabellen, die es in Quelle und Server gibt (ohne Zähler der Verbindung)."""
    ziel = set(con.v.tabellen()) - db_kopie.EIGENE
    out = {}
    for (t,) in quelle.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                               "ORDER BY name"):
        if t in ziel:
            sp = set(con.v.spalten(t))
            out[t] = [r[1] for r in quelle.execute(f'PRAGMA table_info("{t}")') if r[1] in sp]
    return out


def vergleichen(quelle, con, tabellen=None, ohne_einstellungen=()):
    """Jede gemeinsame Tabelle Zeile für Zeile: {Tabelle: dict(quelle, server, gleich)}. ohne_einstellungen: Namen
    von Einstellungen, die nur am Server stehen (je Arbeitsplatz/Benutzer) und nicht zählen."""
    arten = db_kopie._pg_arten(con.v)
    tabellen = tabellen or gemeinsame_tabellen(quelle, con)
    ohne = set(ohne_einstellungen)
    out = {}
    for t, spalten in tabellen.items():
        if not spalten:
            continue
        liste = ", ".join(f'"{s}"' for s in spalten)
        a = [arten.get((t, s)) for s in spalten]
        q = _zeilen_abdruck(quelle.execute(f'SELECT {liste} FROM "{t}"'), a)
        zeilen = con.execute(f'SELECT {liste} FROM "{t}"').fetchall()
        if t == "einstellungen" and ohne and "name" in spalten:
            i = spalten.index("name")
            zeilen = [r for r in zeilen if r[i] not in ohne]
        z = _zeilen_abdruck(zeilen, [None] * len(spalten))
        out[t] = dict(quelle=sum(q.values()), server=sum(z.values()), gleich=q == z)
    return out


# ------------------------------------------------------------------------------------------------ Sicherung
def sichern(server, con, anlass):
    """Stand des Servers vor einer Übernahme: SQLite-Datei (auf jedem PC lesbar) und, wenn pg_dump da ist, ein
    geprüftes Abbild daneben. Ergebnis: Pfad der Datei."""
    from . import pg_abbild, protokoll
    ordner = Path(server.daten) / SICHERUNG_ORDNER
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / f"server_{datetime.datetime.now():%Y-%m-%d_%H%M%S}_vor_{anlass}.db"
    s = sqlite3.connect(ziel)
    try:
        db_kopie.pg_nach_sqlite(con, s)
    finally:
        s.close()
    try:
        pg_abbild.erstellen(con, ziel)
    except (pg_abbild.AbbildFehler, OSError) as e:
        protokoll.warnung(f"Übernahme: kein PostgreSQL-Abbild ({e}); die SQLite-Sicherung genügt zum Zurückholen")
    return ziel


def _schema_pruefen(con, info):
    am_server = db_verbindung.schema_version(con)
    if not am_server:
        raise UebernahmeFehler("Am Server gibt es noch keine Programmtabellen. Bitte zuerst einmal das Programm als "
                               "Verwalter mit dem Server verbinden (richtet die Tabellen ein).")
    if int(info["schema"]) != int(am_server):
        raise UebernahmeFehler(f"Die Quelle hat Schema {info['schema']}, der Server {am_server}. Bitte den PC erst auf "
                               "die Programmversion des Servers bringen, dort neu exportieren und dann übernehmen.")


def _anzahl(con, tabelle):
    return int(con.execute(f'SELECT count(*) FROM "{tabelle}"').fetchone()[0])


# ------------------------------------------------------------------------------------------------ Übernehmen
def uebernehmen(server, datei, ersetzen=False, melden=print):
    """Alle Daten einer Export-Datei/Sicherung in den Server (siehe oben). Ergebnis: Bericht (dict)."""
    melden = melden or (lambda _t: None)
    with quelle_oeffnen(datei) as (quelle, info), verbinden(server) as con:
        _schema_pruefen(con, info)
        vorhanden = _anzahl(con, "angebote")
        if vorhanden and not ersetzen:
            raise UebernahmeFehler(f"Am Server stehen schon {vorhanden} Angebote. Übernehmen ersetzt alles: nur mit "
                                   "--ersetzen (der jetzige Stand wird vorher gesichert). Für die eigenen Angebote "
                                   "eines weiteren PCs: dazunehmen.")
        sicherung = sichern(server, con, "Uebernahme")
        melden(f"Stand des Servers gesichert: {sicherung}")
        tabellen = gemeinsame_tabellen(quelle, con)
        # was nur am Server steht, bleibt: Einstellungen je Arbeitsplatz/Benutzer (@platz:…, @benutzer:…)
        quell_namen = {r[0] for r in quelle.execute("SELECT name FROM einstellungen")}
        eigene_einst = [tuple(r) for r in con.execute("SELECT name, wert FROM einstellungen WHERE name LIKE '@%'")
                        if r[0] not in quell_namen]
        andere = _andere_verbindungen(con)
        if andere:
            melden(f"Hinweis: {andere} Arbeitsplätze sind gerade verbunden; sie laden nach der Übernahme neu.")
        anpassungen = []
        db_kopie.sqlite_nach_pg(quelle, con, anpassungen)       # eine Transaktion, Trigger ruhen
        with con:
            for name, wert in eigene_einst:
                con.execute("INSERT INTO einstellungen (name, wert) VALUES (?, ?) ON CONFLICT (name) DO NOTHING",
                            (name, wert))
        ergebnis = vergleichen(quelle, con, tabellen, ohne_einstellungen={n for n, _w in eigene_einst})
        fehler = {t: e for t, e in ergebnis.items() if not e["gleich"]}
        if fehler:
            # zurück auf den gesicherten Stand: nichts Halbes im Server lassen
            s = sqlite3.connect(f"file:{sicherung.as_posix()}?mode=ro", uri=True)
            try:
                db_kopie.sqlite_nach_pg(s, con)
            finally:
                s.close()
            raise UebernahmeFehler("Übernahme zurückgenommen, Inhalt weicht ab in: " + ", ".join(
                f"{t} ({e['quelle']} → {e['server']})" for t, e in sorted(fehler.items())[:8]))
        with con:
            fremd = con.execute("UPDATE angebote SET bearbeiter = COALESCE(NULLIF(bearbeiter, ''), fremd), "
                                "fremd = NULL, fremd_stand = NULL WHERE fremd IS NOT NULL AND fremd <> ''").rowcount
        zeilen = sum(e["quelle"] for e in ergebnis.values())
        _neu_laden_melden(con)
        _protokoll(con, "uebernahme", f"{Path(datei).name}: {len(ergebnis)} Tabellen, {zeilen} Zeilen, "
                   f"{fremd} Angebote der Kollegen umgestellt")
        melden(f"{len(ergebnis)} Tabellen, {zeilen} Zeilen übernommen und Zeile für Zeile geprüft: alles gleich.")
        if fremd:
            melden(f"{fremd} Angebote der Kollegen gehören jetzt deren Bearbeiter.")
        return dict(tabellen=ergebnis, zeilen=zeilen, fremd=fremd, sicherung=sicherung, anpassungen=len(anpassungen),
                    angebote=_anzahl(con, "angebote"))


# ------------------------------------------------------------------------------------------------ Dazunehmen
_INHALT_TABELLEN = (("kopf", "angebote"), ("positionen", "positionen"), ("stufen", "staffel_stufen"),
                    ("staffeln", "staffeln"))


def _vergleichbar(inhalt, arten):
    """Inhalt eines Angebots (teilen.angebot_inhalt) mit Werten, wie sie nach dem Einlesen in PostgreSQL stehen
    (Zahlen als Text werden Zahlen usw.), damit SQLite und Server gleich aussehen. Bearbeiter zählt nicht (wird
    beim Dazunehmen gesetzt)."""
    def n(d, tabelle):
        out = {}
        for k, v in d.items():
            if tabelle == "angebote" and k == "bearbeiter":
                continue
            w = _norm(v, arten.get((tabelle, k)))
            if w not in (None, ""):
                out[k] = w
        return out
    out = {}
    for teil, tabelle in _INHALT_TABELLEN:
        out[teil] = n(inhalt[teil], tabelle) if teil == "kopf" else [n(x, tabelle) for x in inhalt[teil]]
    out.update(protokoll=list(inhalt["protokoll"]), netze=dict(inhalt["netze"]))
    return out


def _andere_verbindungen(con):
    try:
        return int(con.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
                               "AND pid <> pg_backend_pid() AND usename LIKE 'rl\\_%'").fetchone()[0])
    except db_verbindung.DbFehler:
        return 0


def dazunehmen(server, datei, kuerzel, melden=print):
    """Eigene Angebote eines weiteren PCs (fremd leer; Bearbeiter kuerzel oder leer) in den Server: vorhandene
    (gleiche Nummer) ersetzt, neue angelegt, jedes danach mit der Quelle verglichen. Ergebnis: Bericht."""
    from . import teilen
    melden = melden or (lambda _t: None)
    kuerzel = teilen.kuerzel_sauber(kuerzel)
    if not kuerzel:
        raise UebernahmeFehler("Bitte --kuerzel des PCs angeben (wessen Angebote es sind).")
    with quelle_oeffnen(datei) as (quelle, info), verbinden(server) as con:
        _schema_pruefen(con, info)
        eigene = [r for r in quelle.execute(
            "SELECT id, nummer FROM angebote WHERE (fremd IS NULL OR fremd = '') AND (bearbeiter IS NULL OR "
            "bearbeiter = '' OR upper(bearbeiter) = ?) ORDER BY id", (kuerzel,))]
        sicherung = sichern(server, con, f"Dazunehmen_{kuerzel}")
        melden(f"Stand des Servers gesichert: {sicherung}")
        arten = db_kopie._pg_arten(con.v)
        quell_karte = teilen._uid_karte(quelle, "zukauf_artikel")
        ziel_karte = {u: i for i, u in teilen._uid_karte(con, "zukauf_artikel").items()}
        neu, ersetzt, gleich, fehler = [], [], [], []
        for qid, nummer in eigene:
            inhalt, netze = teilen.angebot_inhalt(quelle, qid, quell_karte)
            geaendert = quelle.execute("SELECT geaendert FROM angebote WHERE id=?", (qid,)).fetchone()[0]
            r = con.execute("SELECT id FROM angebote WHERE nummer=?", (nummer,)).fetchone()
            sid = r[0] if r else None
            if sid is not None:
                am_server, _n = teilen.angebot_inhalt(con, sid)
                if _vergleichbar(am_server, arten) == _vergleichbar(inhalt, arten):
                    gleich.append(nummer)
                    with con:
                        con.execute("UPDATE angebote SET bearbeiter=?, fremd=NULL, fremd_stand=NULL WHERE id=?",
                                    (kuerzel, sid))
                    continue
            with con:
                aid = teilen.angebot_einsetzen(con, inhalt, netze, None, None, angebot_id=sid, artikel_id=ziel_karte)
                con.execute("UPDATE angebote SET bearbeiter=?, geaendert=? WHERE id=?", (kuerzel, geaendert, aid))
            pruef, _n = teilen.angebot_inhalt(con, aid)
            if _vergleichbar(pruef, arten) != _vergleichbar(inhalt, arten):
                fehler.append(nummer)
            (ersetzt if sid is not None else neu).append(nummer)
        if neu or ersetzt:
            _neu_laden_melden(con)
        _protokoll(con, "dazunehmen", f"{Path(datei).name} ({kuerzel}): {len(neu)} neu, {len(ersetzt)} ersetzt, "
                   f"{len(gleich)} gleich" + (f", {len(fehler)} abweichend" if fehler else ""))
        melden(f"Eigene Angebote von {kuerzel}: {len(neu)} neu, {len(ersetzt)} ersetzt, {len(gleich)} schon gleich.")
        if fehler:
            melden("ABWEICHUNG nach dem Einlesen bei: " + ", ".join(fehler[:10]) + f" (Sicherung: {sicherung})")
        return dict(neu=neu, ersetzt=ersetzt, gleich=gleich, fehler=fehler, sicherung=sicherung)


def _neu_laden_melden(con):
    """Verbundene Arbeitsplätze laden Stammdaten, Einstellungen und Angebote neu (Zähler der Verbindung, die beim
    Kopieren nicht mitlaufen)."""
    with con:
        if "stammdaten_stand" in con.v.tabellen():
            con.execute("UPDATE stammdaten_stand SET n = n + 1")
        if "angebot_aenderungen" in con.v.tabellen():
            con.execute("INSERT INTO angebot_aenderungen (angebot_id, n) SELECT id, 1 FROM angebote "
                        "ON CONFLICT (angebot_id) DO UPDATE SET n = angebot_aenderungen.n + 1")


def _protokoll(con, art, text):
    from . import server_mehrplatz
    with contextlib.suppress(db_verbindung.DbFehler), con:
        con.execute(f"INSERT INTO {server_mehrplatz.PROTOKOLL} (kuerzel, platz, art, objekt, text) VALUES "
                    "(?, ?, ?, ?, ?)", ("Server", sb.platz(), art, "", text))


def vergleich_ausgeben(server, datei, ausgabe=print):
    """Server und Quelle Zeile für Zeile vergleichen und ausgeben (Einstellungen je Arbeitsplatz/Benutzer, die nur
    am Server stehen, zählen nicht). Ergebnis: True, wenn alles gleich ist."""
    with quelle_oeffnen(datei) as (quelle, _info), verbinden(server) as con:
        quell_namen = {r[0] for r in quelle.execute("SELECT name FROM einstellungen")}
        nur_server = {r[0] for r in con.execute("SELECT name FROM einstellungen WHERE name LIKE '@%'")} - quell_namen
        ergebnis = vergleichen(quelle, con, ohne_einstellungen=nur_server)
    anders = {t: e for t, e in ergebnis.items() if not e["gleich"]}
    for t, e in sorted(anders.items()):
        ausgabe(f"  anders: {t:<28} Quelle {e['quelle']:>7}  Server {e['server']:>7}")
    ausgabe(f"{len(ergebnis)} Tabellen verglichen: " + ("alles gleich." if not anders else
                                                         f"{len(anders)} weichen ab (z. B. seit der Übernahme "
                                                         "am Server gearbeitet)."))
    return not anders
