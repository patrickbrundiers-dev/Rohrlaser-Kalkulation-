"""Angebotsnummern: ein fortlaufender Nummernkreis für alle Mitarbeiter (Patrick 23.10.2026, Freigabe 1a 2c 3a 4a 5a).

Format Jahr-Zähler, z. B. 2026-00001; der Zähler läuft über den Jahreswechsel weiter (2026-00731 -> 2027-00732).
Mit gemeinsamem Ordner wird jede Nummer dort reserviert: Unterordner Nummern, je Zählerstand eine Datei 00042.nummer,
exklusiv angelegt. Gibt es sie schon, war ein Kollege schneller, und es kommt die nächste. Ist der Ordner nicht
erreichbar, bekommt das Angebot eine vorläufige Nummer (V-PB-1); die endgültige kommt beim nächsten Abgleich oder
vor dem Angebots-PDF. Ohne gemeinsamen Ordner zählt der Arbeitsplatz lokal im gleichen Format. Eine vergebene Nummer
wird nie wieder vergeben, auch wenn das Angebot gelöscht wird."""
import datetime
import json
import re
import socket

from . import angebotsordner, teilen

MUSTER = re.compile(r"^(\d{4})-(\d{5,})$")
VORLAEUFIG = re.compile(r"^V-[A-Z0-9ÄÖÜ]*-(\d+)(-\d+)?$")     # mit Zusatz -2 …: neue Fassung (W10)
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


def reservieren(db, jahr=None):
    """Nächste freie Nummer im gemeinsamen Ordner reservieren. OSError: Ordner nicht erreichbar."""
    w = teilen.weg(db)
    if w is None or not w.erreichbar():
        raise FileNotFoundError(f"Der gemeinsame Ordner ist nicht erreichbar: {w}")
    jahr = jahr or _jahr()
    n = max(w.nummer_hoechste(ORDNER), hoechster_lokal(db))
    while True:
        n += 1
        nr = nummer(jahr, n)
        if _vergeben(db, nr):
            continue
        if w.nummer_belegen(ORDNER, n, f"{nr}\n{teilen.kuerzel(db)}\n{socket.gethostname()}\n"
                                       f"{datetime.datetime.now().isoformat(timespec='seconds')}\n"):
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


def _grund(nr):
    """'V-PB-1-2' -> ('V-PB-1', '-2'); ohne Zusatz ('V-PB-1', '')."""
    m = VORLAEUFIG.match(str(nr or ""))
    zusatz = (m.group(2) or "") if m else ""
    return str(nr)[:len(str(nr)) - len(zusatz)], zusatz


def endgueltig(db, angebot_id=None):
    """Eigene Angebote mit vorläufiger Nummer bekommen eine reservierte Nummer (älteste zuerst); neue Fassungen
    (V-PB-1-2) bekommen dieselbe Nummer wie ihre Grundnummer mit ihrem Zusatz (2026-00042-2), Fassungsbezüge
    (fassung_basis, ersetzt_durch) werden mitgeändert. angebot_id: nur dieses Angebot samt seinen Fassungen.
    Ergebnis: [(alte, neue Nummer)]. OSError: Ordner nicht erreichbar."""
    zeilen = [(i, alt, datum) for i, alt, datum in db.con.execute(
        "SELECT id, nummer, datum FROM angebote WHERE fremd IS NULL AND nummer LIKE 'V-%' ORDER BY id").fetchall()
        if vorlaeufig(alt)]
    gruppen = {}                        # Grundnummer -> [(id, alte Nummer, Zusatz, Datum)], älteste Gruppe zuerst
    for i, alt, datum in zeilen:
        grund, zusatz = _grund(alt)
        gruppen.setdefault(grund, []).append((i, alt, zusatz, datum))
    if angebot_id is not None:
        gruppen = {g: z for g, z in gruppen.items() if any(i == angebot_id for i, *_ in z)}
    spalten = {r[1] for r in db.con.execute("PRAGMA table_info(angebote)")}
    out = []
    for grund, glieder in gruppen.items():
        nr = reservieren(db, _jahr(glieder[0][3]))
        neu_von = {grund: nr}
        neu_von.update({alt: nr + zusatz for _, alt, zusatz, _ in glieder})
        with db.con:
            for i, alt, zusatz, _ in glieder:
                db.con.execute("UPDATE angebote SET nummer=? WHERE id=?", (nr + zusatz, i))
            for spalte in ("fassung_basis", "ersetzt_durch"):
                if spalte in spalten:
                    for alt, neu in neu_von.items():
                        db.con.execute(f"UPDATE angebote SET {spalte}=? WHERE {spalte}=? AND fremd IS NULL", (neu, alt))
            db._einstellung_schreiben("letzte_angebotsnummer", nr)
            # Ordner des Angebots in der Ablage wird beim nächsten Zugriff umbenannt (angebotsordner)
            offen = db.einstellung(angebotsordner.UMNUMMERIERT) or []
            db._einstellung_schreiben(angebotsordner.UMNUMMERIERT,
                                      offen + [[grund, nr]] + [[alt, nr + zusatz] for _, alt, zusatz, _ in glieder
                                                               if zusatz])
        out += [(alt, nr + zusatz) for _, alt, zusatz, _ in glieder]
    return out


# ------------------------------------------------------------------ Auftragsbestätigung (Plan 29.10.2026 1c)
AB_WIE_ANGEBOT, AB_EIGEN = "wie Angebot", "eigener Nummernkreis"
AB_NUMMER = (AB_WIE_ANGEBOT, AB_EIGEN)
AB_MUSTER = re.compile(r"^AB-(\d{4})-(\d{5,})$")
AB_ORDNER = "AB-Nummern"


def ab_zaehler(nr):
    """'AB-2026-00007' -> 7, sonst 0."""
    m = AB_MUSTER.match(str(nr or "").strip())
    return int(m.group(2)) if m else 0


def ab_vorhanden(kopf):
    """AB-Nummer der letzten Auftragsbestätigung dieses Angebots (Versandverlauf, art 'ab') oder None."""
    alle = [e.get("nummer") for e in (kopf or {}).get("versand") or () if isinstance(e, dict) and e.get("art") == "ab"]
    return next((n for n in reversed(alle) if n), None)


def _ab_hoechster_lokal(db):
    werte = [db.einstellung("letzte_ab_nummer")]
    for (v,) in db.con.execute("SELECT versand FROM angebote WHERE versand LIKE '%\"art\": \"ab\"%'"):
        try:
            werte.append(ab_vorhanden({"versand": json.loads(v)}))
        except (TypeError, ValueError):
            continue
    return max((ab_zaehler(n) for n in werte), default=0)


def ab_nummer(db, kopf, datum=None):
    """Nummer der Auftragsbestätigung: eine schon vergebene AB-Nummer des Angebots bleibt; Einstellung
    'ab_nummer' = wie Angebot: die Angebotsnummer; eigener Nummernkreis: AB-Jahr-Zähler, mit gemeinsamem Ordner dort
    reserviert (Unterordner AB-Nummern, wie die Angebotsnummern), sonst lokal gezählt. OSError: Ordner nicht
    erreichbar."""
    alt = ab_vorhanden(kopf)
    if alt:
        return alt
    if (db.einstellung("ab_nummer") or AB_WIE_ANGEBOT) != AB_EIGEN:
        return str(kopf.get("nummer") or "")
    jahr = _jahr(datum)
    n = _ab_hoechster_lokal(db)
    if teilen.aktiv(db):
        w = teilen.weg(db)
        if w is None or not w.erreichbar():
            raise FileNotFoundError(f"Der gemeinsame Ordner ist nicht erreichbar: {w}")
        n = max(n, w.nummer_hoechste(AB_ORDNER))
        while True:
            n += 1
            if w.nummer_belegen(AB_ORDNER, n, f"AB-{jahr}-{n:05d}\n{kopf.get('nummer') or ''}\n"
                                              f"{teilen.kuerzel(db)}\n"
                                              f"{datetime.datetime.now().isoformat(timespec='seconds')}\n"):
                break
    else:
        n += 1
    nr = f"AB-{jahr}-{n:05d}"
    db.einstellung_setzen("letzte_ab_nummer", nr)
    return nr
