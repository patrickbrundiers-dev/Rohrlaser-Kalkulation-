"""Support-Paket (Vorschlag S2, Patrick 02.11.2026 „S2a“: ZIP erstellen und Ordner öffnen, den Versand macht der Nutzer).

Hilfe → „Support-Paket erstellen …“ (und der Knopf „Support-Paket“ in der Fehlermeldung) legt im Ordner
Daten/Support eine Datei „Support_JJJJ-MM-TT_HHMM.zip“ an mit:
- fehler.log (+ fehler.log.1/.2, das Fehlerprotokoll aus Daten/Protokoll),
- info.txt: Programmversion, Datenschema, Lizenzstand, Betriebssystem, Datenort,
- systempruefung.txt: dieser Rechner gegen die Systemvoraussetzungen,
- einstellungen.json: die Einstellungen OHNE Passwörter, Bilder (Logo) und Kundendaten (es stehen keine Kunden,
  Angebote oder Preise darin),
- optional (Haken, Vorgabe aus) das gerade offene Angebot als angebot.json (Kopf + Positionen, ohne 3D-Netze).
Ohne Qt, damit Tests es nutzen können."""
import datetime
import json
import platform
import zipfile
from pathlib import Path

from . import protokoll

ORDNER = "Support"
# Einstellungen, die nie ins Paket gehören (zusätzlich zu art passwort/bild)
GEHEIM = ("passwort", "kennwort", "schluessel", "token", "hash", "geheim")


def einstellungen_sauber(db):
    """Einstellungen ohne Passwörter, Schlüssel und Bilder: {name: wert}."""
    from .stammdaten import EINSTELLUNGEN
    arten = {e.name: e.art for e in EINSTELLUNGEN}
    out = {}
    for name, wert in db.einstellungen().items():
        if arten.get(name) in ("passwort", "bild") or any(g in name.lower() for g in GEHEIM):
            out[name] = "(entfernt)" if wert not in (None, "") else ""
            continue
        out[name] = wert
    return out


def protokolldateien(ordner):
    """fehler.log und die rotierten Vorgänger im Protokollordner."""
    ordner = Path(ordner)
    return [p for p in (ordner / protokoll.DATEI, ordner / f"{protokoll.DATEI}.1", ordner / f"{protokoll.DATEI}.2")
            if p.is_file()]


def info_text(db, lizenz_text=None, version=None):
    from . import VERSION
    from .datenbank import SCHEMA_VERSION
    zeilen = [f"Programmversion: {version or VERSION}", f"Datenschema: {SCHEMA_VERSION}",
              f"Lizenz: {lizenz_text or 'nicht geprüft'}",
              f"Betriebssystem: {platform.platform()}", f"Python: {platform.python_version()}",
              f"Datendatei: {getattr(db, 'pfad', '')}",
              f"Nur lesen: {'ja' if getattr(db, 'nur_lesen', False) else 'nein'}",
              f"Erstellt: {datetime.datetime.now().isoformat(timespec='seconds')}"]
    return "\n".join(zeilen) + "\n"


def system_text(zeilen):
    return "\n".join(f"{b}: {g} (mindestens {m}, empfohlen {e}) – {s}" for b, g, m, e, s in zeilen) + "\n"


def angebot_daten(db, angebot_id):
    """Kopf und Positionen des offenen Angebots (ohne Netze) für das Paket."""
    kopf = dict(db.angebot(angebot_id) or {})
    kopf.pop("ergebnis", None)
    return dict(kopf=kopf, positionen=[dict(p) for p in db.positionen(angebot_id)])


def erstellen(db, ziel_ordner=None, protokoll_ordner=None, lizenz_text=None, system=None, angebot_id=None,
              jetzt=None):
    """ZIP schreiben. ziel_ordner: Vorgabe Daten/Support neben der Datendatei; protokoll_ordner: Vorgabe
    Daten/Protokoll; system = Zeilen von systempruefung.pruefen (None = jetzt prüfen); angebot_id = offenes Angebot
    beilegen (None = nicht). Ergebnis: dict(pfad, dateien=[Namen im ZIP], groesse [Byte])."""
    daten = Path(db.pfad).parent
    ziel_ordner = Path(ziel_ordner or daten / ORDNER)
    protokoll_ordner = Path(protokoll_ordner or daten / "Protokoll")
    ziel_ordner.mkdir(parents=True, exist_ok=True)
    jetzt = jetzt or datetime.datetime.now()
    pfad = ziel_ordner / f"Support_{jetzt:%Y-%m-%d_%H%M}.zip"
    if system is None:
        from . import systempruefung
        try:
            system = systempruefung.pruefen(daten)
        except Exception as f:          # Systemprüfung darf das Paket nie verhindern
            system = [("Systemprüfung", f"nicht möglich ({type(f).__name__})", "", "", "?")]
    dateien = []
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        for p in protokolldateien(protokoll_ordner):
            z.write(p, p.name)
            dateien.append(p.name)
        for name, inhalt in (("info.txt", info_text(db, lizenz_text)), ("systempruefung.txt", system_text(system)),
                             ("einstellungen.json", json.dumps(einstellungen_sauber(db), ensure_ascii=False,
                                                               indent=1, default=str))):
            z.writestr(name, inhalt)
            dateien.append(name)
        if angebot_id is not None:
            z.writestr("angebot.json", json.dumps(angebot_daten(db, angebot_id), ensure_ascii=False, indent=1,
                                                  default=str))
            dateien.append("angebot.json")
    return dict(pfad=str(pfad), dateien=dateien, groesse=pfad.stat().st_size)


def text(e):
    from .stammdaten import zahl_als_text
    return (f"Support-Paket erstellt: {Path(e['pfad']).name} ({zahl_als_text(e['groesse'] / 1024, 0)} KB) mit "
            f"{', '.join(e['dateien'])}.\n\nBitte die Datei per Mail an den Support schicken. Es sind keine Kunden, "
            "Preise oder Passwörter enthalten" + (" (außer dem beigelegten Angebot)." if "angebot.json" in e["dateien"]
                                                   else "."))
