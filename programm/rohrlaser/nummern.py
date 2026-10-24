"""Angebotsnummern: ein fortlaufender Nummernkreis für alle Mitarbeiter (Patrick 23.10.2026, Freigabe 1a 2c 3a 4a 5a).

Format Jahr-Zähler, z. B. 2026-00001; der Zähler läuft über den Jahreswechsel weiter (2026-00731 -> 2027-00732).
Mit gemeinsamem Ordner wird jede Nummer dort reserviert: Unterordner Nummern, je Zählerstand eine Datei 00042.nummer,
exklusiv angelegt. Gibt es sie schon, war ein Kollege schneller, und es kommt die nächste. Ist der Ordner nicht
erreichbar, bekommt das Angebot eine vorläufige Nummer (V-PB-1); die endgültige kommt beim nächsten Abgleich oder
vor dem Angebots-PDF. Ohne gemeinsamen Ordner zählt der Arbeitsplatz lokal im gleichen Format. Eine vergebene Nummer
wird nie wieder vergeben, auch wenn das Angebot gelöscht wird."""
import datetime
import os
import re
import socket

from . import angebotsordner, teilen

MUSTER = re.compile(r"^(\d{4})-(\d{5,})$")
VORLAEUFIG = re.compile(r"^V-[A-Z0-9ÄÖÜ]*-(\d+)$")
ORDNER = "Nummern"
ENDUNG = ".nummer"


def zaehler(nr):
    """'2026-00042' -> 42; andere Nummern (alte mit Kürzel, A-2026-0001, vorläufige) 0."""
    m = MUSTER.match(str(nr or "").strip())
    return int(m.group(2)) if m else 0


def nummer(jahr, n):
    return f"{jahr}-{n:05d}"


def vorlaeufig(nr):
    return bool(VORLAEUFIG.match(str(nr or "")))


def _jahr(datum=None):
    return str(datum or datetime.date.today().isoformat())[:4]


def _vergeben(db, nr):
    return db.con.execute("SELECT 1 FROM angebote WHERE nummer=?", (nr,)).fetchone() is not None


def hoechster_lokal(db):
    """Höchster Zählerstand dieses Arbeitsplatzes: eigene Angebote, die der Kollegen und die zuletzt vergebene Nummer
    (auch wenn das Angebot gelöscht ist)."""
    werte = [r[0] for r in db.con.execute("SELECT nummer FROM angebote")] + [db.einstellung("letzte_angebotsnummer")]
    return max((zaehler(n) for n in werte), default=0)


def reservierungen(o):
    """Höchster reservierter Zählerstand im Ordner Nummern."""
    return max((int(p.stem) for p in o.iterdir() if p.suffix == ENDUNG and p.stem.isdigit()), default=0)


def reservieren(db, jahr=None):
    """Nächste freie Nummer im gemeinsamen Ordner reservieren. OSError: Ordner nicht erreichbar."""
    basis = teilen.ordner(db)
    if basis is None or not basis.is_dir():
        raise FileNotFoundError(f"Der gemeinsame Ordner ist nicht erreichbar: {basis}")
    o = basis / ORDNER
    o.mkdir(exist_ok=True)
    jahr = jahr or _jahr()
    n = max(reservierungen(o), hoechster_lokal(db))
    while True:
        n += 1
        nr = nummer(jahr, n)
        if _vergeben(db, nr):
            continue
        try:                       # exklusiv: zwei Arbeitsplätze können dieselbe Datei nicht beide anlegen
            fd = os.open(o / f"{n:05d}{ENDUNG}", os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(f"{nr}\n{teilen.kuerzel(db)}\n{socket.gethostname()}\n"
                    f"{datetime.datetime.now().isoformat(timespec='seconds')}\n")
        return nr


def _vorlaeufige(db):
    k = teilen.kuerzel(db)
    hoch = max((int(m.group(1)) for m in (VORLAEUFIG.match(str(r[0] or ""))
                                         for r in db.con.execute("SELECT nummer FROM angebote")) if m), default=0)
    n = hoch + 1
    while _vergeben(db, f"V-{k}-{n}"):
        n += 1
    return f"V-{k}-{n}"


def neue_nummer(db, datum=None):
    """Nummer für ein neues Angebot: mit gemeinsamem Ordner reserviert (sonst vorläufig), ohne lokal hochgezählt."""
    jahr = _jahr(datum)
    if teilen.aktiv(db):
        try:
            return reservieren(db, jahr)
        except OSError:
            return _vorlaeufige(db)
    n = hoechster_lokal(db) + 1
    while _vergeben(db, nummer(jahr, n)):
        n += 1
    return nummer(jahr, n)


def endgueltig(db, angebot_id=None):
    """Eigene Angebote mit vorläufiger Nummer bekommen eine reservierte Nummer (älteste zuerst); angebot_id: nur
    dieses. Ergebnis: [(alte, neue Nummer)]. OSError: Ordner nicht erreichbar."""
    sql = "SELECT id, nummer FROM angebote WHERE fremd IS NULL AND nummer LIKE 'V-%'"
    werte = ()
    if angebot_id is not None:
        sql, werte = sql + " AND id=?", (angebot_id,)
    out = []
    for i, alt in db.con.execute(sql + " ORDER BY id", werte).fetchall():
        if not vorlaeufig(alt):
            continue
        datum = (db.con.execute("SELECT datum FROM angebote WHERE id=?", (i,)).fetchone() or [None])[0]
        nr = reservieren(db, _jahr(datum))
        with db.con:
            db.con.execute("UPDATE angebote SET nummer=? WHERE id=?", (nr, i))
            db._einstellung_schreiben("letzte_angebotsnummer", nr)
            # Ordner des Angebots in der Ablage wird beim nächsten Zugriff umbenannt (angebotsordner)
            offen = db.einstellung(angebotsordner.UMNUMMERIERT) or []
            db._einstellung_schreiben(angebotsordner.UMNUMMERIERT, offen + [[alt, nr]])
        out.append((alt, nr))
    return out
