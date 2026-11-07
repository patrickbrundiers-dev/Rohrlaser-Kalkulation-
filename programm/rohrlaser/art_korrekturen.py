"""Prüfsammlung wächst von selbst (Vorschlag N5, Patrick 07.11.2026): jede im Prüfdialog von Hand geänderte Art eines
STEP-Teils (z. B. Rundstahl → Drehteil, Blech → Flachstahl) merkt sich das Programm im Ordner Daten/Prüfsammlung:
eine Zeile in korrekturen.jsonl mit den Kennwerten der Messung (Hüllmaße, Volumen, Flächen, Regel, Merkmale) und ein
kleines Vorschaubild. Die STEP-Datei selbst, Datei-, Artikel- und Bauteilnamen werden NICHT gespeichert. Das
Support-Paket nimmt den Ordner mit; daraus werden neue Erkennungsregeln und Testfälle.
"""
import datetime
import json
import uuid
from pathlib import Path

ORDNER = "Prüfsammlung"
DATEI = "korrekturen.jsonl"
HOECHSTENS = 500            # ältere Einträge (und ihre Bilder) fallen weg
KENNWERTE = ("bauteiltyp", "profilform", "abm_a", "abm_b", "wandstaerke", "laenge", "huelle", "volumen", "n_flaechen",
             "n_kanten", "art_regel", "art_grund", "sicherheit", "drehfraes")


def ordner(db_pfad):
    return Path(db_pfad).parent / ORDNER


def art_text(m):
    from . import step
    return f"{step.art_gruppe(m)}: {m.get('profilform') or m.get('bauteiltyp') or '?'}"


def start_merken(messwerte):
    """Art jedes Teils vor dem Prüfdialog: {(Datei, Körper): (Text, Kennwerte)}."""
    return {(m.get("datei"), str(m.get("koerper"))): (art_text(m), kennwerte(m)) for m in messwerte
            if not m.get("fehler")}


def kennwerte(m):
    out = {k: m.get(k) for k in KENNWERTE if m.get(k) not in (None, "")}
    if m.get("hinweise"):
        out["hinweise"] = str(m["hinweise"])[:300]
    return out


def korrekturen(start, messwerte):
    """Teile, deren Art im Prüfdialog geändert wurde: Liste dict(gemessen, gewaehlt, kennwerte, m)."""
    out, gesehen = [], set()
    for m in messwerte:
        s = start.get((m.get("datei"), str(m.get("koerper"))))
        if s is None or m.get("fehler"):
            continue
        neu = art_text(m)
        if neu == s[0]:
            continue
        from . import step
        schl = step.art_schluessel(m) or (s[0], neu, json.dumps(s[1], sort_keys=True, default=str))
        if schl in gesehen:         # gleiche Teile einer Baugruppe nur einmal
            continue
        gesehen.add(schl)
        out.append(dict(gemessen=s[0], gewaehlt=neu, kennwerte=s[1], m=m))
    return out


def _bild(m):
    """Vorschaubild (PNG-Bytes) der gewählten Art oder None (ohne 3D-Daten, ohne Qt)."""
    try:
        from PySide6.QtCore import QBuffer, QIODevice
        from . import step
        from .ansicht3d import entpacken, vorschaubild
        netz = step.netz_der_art(m)
        pix = vorschaubild(entpacken(netz) if isinstance(netz, (bytes, bytearray)) else netz, 240, 160)
        if pix is None:
            return None
        puffer = QBuffer()
        puffer.open(QIODevice.WriteOnly)
        pix.save(puffer, "PNG")
        return bytes(puffer.data())
    except Exception:  # das Bild darf das Merken nie verhindern
        return None


def merken(ziel, liste, version=None, jetzt=None):
    """Korrekturen (aus korrekturen()) anhängen. Ergebnis: Anzahl gespeicherter Einträge."""
    if not liste:
        return 0
    from . import VERSION
    ziel = Path(ziel)
    ziel.mkdir(parents=True, exist_ok=True)
    jetzt = jetzt or datetime.datetime.now()
    zeilen = []
    for k in liste:
        e = dict(id=uuid.uuid4().hex[:12], datum=jetzt.isoformat(timespec="seconds"), version=version or VERSION,
                 gemessen=k["gemessen"], gewaehlt=k["gewaehlt"], kennwerte=k["kennwerte"])
        bild = _bild(k["m"])
        if bild:
            (ziel / f"{e['id']}.png").write_bytes(bild)
            e["bild"] = f"{e['id']}.png"
        zeilen.append(json.dumps(e, ensure_ascii=False, default=str))
    datei = ziel / DATEI
    alt = datei.read_text(encoding="utf-8").splitlines() if datei.is_file() else []
    alle = alt + zeilen
    for z in alle[:-HOECHSTENS]:            # zu viele: die ältesten mit Bild löschen
        try:
            b = json.loads(z).get("bild")
            if b:
                (ziel / b).unlink(missing_ok=True)
        except (ValueError, OSError):
            pass
    datei.write_text("\n".join(alle[-HOECHSTENS:]) + "\n", encoding="utf-8")
    return len(zeilen)


def eintraege(ziel):
    datei = Path(ziel) / DATEI
    if not datei.is_file():
        return []
    out = []
    for z in datei.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(z))
        except ValueError:
            continue
    return out


def dateien(ziel):
    """Dateien für das Support-Paket: korrekturen.jsonl und die Bilder."""
    ziel = Path(ziel)
    if not (ziel / DATEI).is_file():
        return []
    return [ziel / DATEI] + sorted(p for p in ziel.glob("*.png"))
