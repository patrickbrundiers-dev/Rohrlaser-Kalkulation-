"""Ordner je Angebot in der Ablage (Patrick 24.10.2026, Freigabe 1a 2a 3b 4a 5a 6a 7a 8a 9a).

Jedes Angebot bekommt einen Ordner '<Ablage>\\2026-00042 Kunde' für alle Ausgaben (PDFs, CSV, Materialanfrage,
STEP-Messung). Neue Fassungen liegen darin als Unterordner 'Fassung 2', 'Fassung 3' … Ein vorhandener Ordner mit
derselben Nummer wird weiterverwendet, auch wenn sich der Kunde geändert hat. Wird eine vorläufige Nummer (V-PB-1)
endgültig, merkt nummern.endgueltig das Paar; der Ordner wird beim nächsten Zugriff umbenannt. Die Dateinamen behalten
die Angebotsnummer vorne. STEP-Dateien kann der Import in den Unterordner 'STEP' kopieren. Lose Dateien aus der Zeit
vor den Ordnern werden einmalig in den Ordner ihres Angebots verschoben. Ohne Qt."""
import re
import shutil
from pathlib import Path

STEP_ORDNER = "STEP"
UMNUMMERIERT = "ordner_umnummeriert"        # vom Programm gemerkt: [[alte, neue Nummer]] (lokal, nicht sichtbar)
VERSCHOBEN = "ablage_lose_verschoben"       # vom Programm gemerkt: Ablage, deren lose Dateien verschoben wurden
KUNDE_MAX = 60                              # so viele Zeichen des Kundennamens im Ordnernamen


def sauber(text):
    """Text als Datei-/Ordnername: verbotene Zeichen als _, ohne Punkte und Leerzeichen am Ende (Windows)."""
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", str(text or ""))
    return re.sub(r"\s+", " ", s).strip().rstrip(". ")


def teile(kopf):
    """(Grundnummer, Fassung oder None): '2026-00042-2' mit fassung_basis '2026-00042' -> ('2026-00042', 2)."""
    nr = str(kopf.get("nummer") or "").strip() or "Angebot"
    basis = str(kopf.get("fassung_basis") or "").strip()
    if basis and nr.startswith(basis + "-") and nr[len(basis) + 1:].isdigit():
        return basis, int(nr[len(basis) + 1:])
    return nr, None


def ordnername(nummer, kunde=""):
    kunde = sauber(kunde)[:KUNDE_MAX].strip()
    return sauber(f"{nummer} {kunde}" if kunde else nummer) or "Angebot"


def finden(ablage, nummer):
    """Vorhandener Ordner der Nummer in der Ablage ('2026-00042' oder '2026-00042 …') oder None."""
    n = sauber(nummer)
    try:
        treffer = sorted(o for o in Path(ablage).iterdir() if o.is_dir() and (o.name == n or o.name.startswith(n + " ")))
    except OSError:
        return None
    return treffer[0] if treffer else None


def ordner(ablage, kopf, anlegen=True):
    """Ordner des Angebots (Fassungen: Unterordner 'Fassung n' im Ordner der Grundnummer); anlegen: wird angelegt."""
    grund, fassung = teile(kopf)
    o = finden(ablage, grund) or Path(ablage) / ordnername(grund, kopf.get("kunde"))
    if fassung:
        o = o / f"Fassung {fassung}"
    if anlegen:
        o.mkdir(parents=True, exist_ok=True)
    return o


def umnummerieren(ablage, paare):
    """Ordner und darin liegende Dateien von der alten auf die neue Nummer umbenennen ('V-PB-1 Kunde' ->
    '2026-00042 Kunde', 'V-PB-1 Kalkulation.pdf' -> '2026-00042 Kalkulation.pdf'). Ergebnis: Anzahl Ordner."""
    anzahl = 0
    for alt, neu in paare:
        o = finden(ablage, alt)
        a, n = sauber(alt), sauber(neu)
        if o is None or not n or finden(ablage, neu):
            continue
        ziel = o.with_name(n + o.name[len(a):])
        try:
            o.rename(ziel)
        except OSError:
            continue
        anzahl += 1
        for d in ziel.rglob("*"):
            if d.is_file() and (d.name.startswith(a + " ") or d.name == f"Angebot_{a}.zip"):
                neu_name = n + d.name[len(a):] if d.name.startswith(a + " ") else f"Angebot_{n}.zip"
                if not (d.parent / neu_name).exists():
                    try:
                        d.rename(d.parent / neu_name)
                    except OSError:
                        pass
    return anzahl


def umnummerieren_offen(db, ablage):
    """Von nummern.endgueltig gemerkte Paare abarbeiten. Ergebnis: Anzahl umbenannter Ordner."""
    paare = db.einstellung(UMNUMMERIERT) or []
    if not paare:
        return 0
    anzahl = umnummerieren(ablage, paare)
    try:
        db.einstellung_setzen(UMNUMMERIERT, [])
    except Exception:       # Lesemodus: beim nächsten Mal noch einmal (umbenannte Ordner werden nicht mehr gefunden)
        pass
    return anzahl


def _nummer_der_datei(name, nummern):
    """Längste Nummer, zu der die Datei gehört ('2026-00042-2 Angebot.pdf', 'Angebot_2026-00042.zip')."""
    passend = [n for n in nummern if name.startswith(n + " ") or name == f"Angebot_{n.replace(' ', '_')}.zip"]
    return max(passend, key=len) if passend else None


def lose_verschieben(ablage, angebote):
    """Dateien direkt in der Ablage, deren Name mit der Nummer eines Angebots beginnt, in den Ordner dieses Angebots
    verschieben. Gleichnamige Dateien im Ziel und geöffnete Dateien bleiben liegen. Ergebnis: Anzahl verschoben."""
    je_nummer = {}
    for a in angebote:
        n = sauber(a.get("nummer"))
        if n:
            je_nummer.setdefault(n, a)
    anzahl = 0
    try:
        dateien = [d for d in Path(ablage).iterdir() if d.is_file()]
    except OSError:
        return 0
    for d in dateien:
        n = _nummer_der_datei(d.name, je_nummer)
        if n is None:
            continue
        try:
            ziel = ordner(ablage, je_nummer[n]) / d.name
            if ziel.exists():
                continue
            d.rename(ziel)
            anzahl += 1
        except OSError:
            continue
    return anzahl


def lose_verschieben_einmal(db, ablage):
    """lose_verschieben einmal je Ablage (gemerkt in VERSCHOBEN). Ergebnis: Anzahl verschoben."""
    if db.einstellung(VERSCHOBEN) == str(ablage):
        return 0
    angebote = [dict(nummer=r[0], kunde=r[1], fassung_basis=r[2]) for r in db.con.execute(
        "SELECT nummer, kunde, fassung_basis FROM angebote")]
    anzahl = lose_verschieben(ablage, angebote)
    try:
        db.einstellung_setzen(VERSCHOBEN, str(ablage))
    except Exception:       # Lesemodus: beim nächsten Start noch einmal
        pass
    return anzahl


def _gleich(a, b):
    try:
        return a.stat().st_size == b.stat().st_size and a.read_bytes() == b.read_bytes()
    except OSError:
        return False


def step_kopieren(dateien, ziel):
    """STEP-Dateien nach ziel kopieren. Gleiche Datei schon da: nichts; gleicher Name, anderer Inhalt: 'Name (2).stp'.
    Ergebnis: (Anzahl kopiert, [Fehlermeldungen])."""
    ziel = Path(ziel)
    kopiert, fehler = 0, []
    try:
        ziel.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return 0, [str(e)]
    for d in dateien:
        d = Path(d)
        z, i = ziel / d.name, 1
        while z.exists() and not _gleich(d, z):
            i += 1
            z = ziel / f"{d.stem} ({i}){d.suffix}"
        if z.exists():
            continue
        try:
            shutil.copy2(d, z)
            kopiert += 1
        except OSError as e:
            fehler.append(f"{d.name}: {e}")
    return kopiert, fehler
