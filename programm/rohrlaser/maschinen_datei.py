"""Maschinendaten als Datei austauschen (Roadmap Kalkulation, Phase 1, MACH-009; Freigabe Patrick 12.11.2026).

Eine Maschine aus den Stammdaten samt ihren Schneiddaten wird als JSON-Datei (*.rlmaschine) gespeichert und auf
einem anderen Rechner (zweiter Standort, Test-PC) wieder eingelesen. Gibt es die Maschinen-ID dort schon, entscheidet
der Bediener: unter einer neuen ID anlegen oder die vorhandene ersetzen (Maschinenwerte und alle ihre Schneiddaten).
Vor dem Einlesen legt das Programm eine geschützte Datensicherung an. Spalten, die die Zieldatei nicht kennt
(andere Programmversion), bleiben weg; festgeschriebene Angebote rechnen unverändert weiter. Ohne Qt."""
import datetime
import json
from pathlib import Path

ART = "Rohrlaser-Maschine"
ENDUNG = ".rlmaschine"
FORMAT = 1
OHNE = ("id", "uid")


def _sauber(z):
    return {k: v for k, v in z.items() if k not in OHNE}


def daten(db, maschinen_id):
    """dict der Datei für eine Maschine (ValueError, wenn es sie nicht gibt)."""
    from . import VERSION
    from .datenbank import SCHEMA_VERSION
    m = next((z for z in db.zeilen("maschinen") if z.get("maschinen_id") == maschinen_id), None)
    if m is None:
        raise ValueError(f"Die Maschine '{maschinen_id}' gibt es nicht.")
    sd = [_sauber(z) for z in db.zeilen("schneiddaten") if z.get("maschinen_id") == maschinen_id]
    return dict(art=ART, format=FORMAT, version=VERSION, schema=SCHEMA_VERSION,
                erstellt=datetime.datetime.now().isoformat(timespec="seconds"),
                maschine=_sauber(m), schneiddaten=sd)


def exportieren(db, maschinen_id, pfad):
    """Datei schreiben; Ergebnis: Anzahl Schneiddaten-Zeilen."""
    d = daten(db, maschinen_id)
    pfad = Path(pfad)
    neu = pfad.with_name(pfad.name + ".neu")
    neu.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    neu.replace(pfad)
    return len(d["schneiddaten"])


def lesen(pfad):
    """dict der Datei; ValueError, wenn sie keine Maschinendatei ist."""
    try:
        d = json.loads(Path(pfad).read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(f"{Path(pfad).name} ist keine Maschinendatei ({e}).") from None
    if not isinstance(d, dict) or d.get("art") != ART or not isinstance(d.get("maschine"), dict) \
            or not str(d["maschine"].get("maschinen_id") or "").strip():
        raise ValueError(f"{Path(pfad).name} ist keine Maschinendatei der Rohrlaser-Kalkulation.")
    if not isinstance(d.get("schneiddaten"), list):
        d["schneiddaten"] = []
    return d


def vorhanden(db, maschinen_id):
    return any(z.get("maschinen_id") == maschinen_id for z in db.zeilen("maschinen"))


def _spalten(db, tabelle):
    return {r[1] for r in db.con.execute(f'PRAGMA table_info("{tabelle}")')} - set(OHNE)


def importieren(db, d, neue_id=None, ersetzen=False, sichern=True):
    """Maschine aus der Datei d (lesen) eintragen. neue_id = unter dieser Maschinen-ID; ersetzen = vorhandene
    Maschine mit derselben ID überschreiben (Werte und alle ihre Schneiddaten). Gibt es die ID schon und ist weder
    neue_id noch ersetzen gesetzt: ValueError. Ergebnis dict(maschinen_id, schneiddaten, ersetzt, sicherung,
    weggelassen = Spalten, die diese Datei nicht kennt)."""
    mid = str(neue_id or d["maschine"]["maschinen_id"]).strip()
    da = vorhanden(db, mid)
    if da and not ersetzen:
        raise ValueError(f"Die Maschine '{mid}' gibt es schon: bitte eine neue Maschinen-ID wählen oder ersetzen.")
    sp_m, sp_s = _spalten(db, "maschinen"), _spalten(db, "schneiddaten")
    weg = sorted({k for k in d["maschine"] if k not in sp_m and k not in OHNE}
                 | {k for z in d["schneiddaten"] for k in z if k not in sp_s and k not in OHNE})
    werte = {k: v for k, v in d["maschine"].items() if k in sp_m}
    werte["maschinen_id"] = mid
    zeilen = [dict({k: v for k, v in z.items() if k in sp_s}, maschinen_id=mid) for z in d["schneiddaten"]]
    pfad = db.sicherung(zusatz="vor_Maschinenimport") if sichern else None
    if da:
        m = next(z for z in db.zeilen("maschinen") if z.get("maschinen_id") == mid)
        for k, v in werte.items():
            if k != "maschinen_id" and m.get(k) != v:
                db.aendern("maschinen", m["id"], k, v)
        alt = [z["id"] for z in db.zeilen("schneiddaten") if z.get("maschinen_id") == mid]
        if alt:
            db.loeschen("schneiddaten", alt)
    else:
        db.neu("maschinen", werte)
    for z in zeilen:
        db.neu("schneiddaten", z)
    return dict(maschinen_id=mid, schneiddaten=len(zeilen), ersetzt=da, sicherung=pfad, weggelassen=weg)
