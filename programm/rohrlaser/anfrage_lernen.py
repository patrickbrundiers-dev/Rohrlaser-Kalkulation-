"""Rückmeldungen zur Anfrage-Erkennung (Patrick 20.11.2026, Plan K9, „Alles einbauen“).

Jede Korrektur von Hand (Mail-Art, Sachgebiet, Kunde, Zuordnung zu einer Anfrage, Bearbeiter, erkannte Werte) wird
als eine Zeile in _outlook/rueckmeldung.jsonl im Akten-Ordner gespeichert: was automatisch erkannt war, was der
Mitarbeiter gewählt hat, wer, wann, die Anfrage und (für die Mail-Art) die ersten Zeichen des Mail-Texts als
Lernstoff. Alle Plätze schreiben in dieselbe Datei (nur anhängen, nie überschreiben).

rueckmelden(wurzel, feld, auto, neu, nr, kuerzel, text)   eine Rückmeldung anhängen
rueckmeldungen(wurzel, feld=None)                          alle (bzw. eines Felds), älteste zuerst
Ohne Qt."""
import datetime
import json
from pathlib import Path

DATEI = "rueckmeldung.jsonl"
STAMM = "_outlook"
TEXT_MAX = 2000
FELDER = {"art": "Mail-Art", "sachgebiet": "Sachgebiet", "kunde": "Kunde", "zuordnung": "Zuordnung zu Anfrage",
          "bearbeiter": "Bearbeiter", "wert": "Erkannter Wert", "ordner": "Outlook-Ordner"}


def pfad(wurzel):
    return Path(wurzel) / STAMM / DATEI


def rueckmelden(wurzel, feld, auto, neu, nr="", kuerzel="", text="", jetzt=None, **weitere):
    """Eine Rückmeldung anhängen. auto: was automatisch erkannt war; neu: was der Mitarbeiter gewählt hat.
    Gleiches auto und neu ist eine Bestätigung (richtig erkannt). Ergebnis: der Eintrag (dict)."""
    if not wurzel:
        return None
    e = dict(zeit=(jetzt or datetime.datetime.now()).isoformat(timespec="seconds"), feld=feld,
             auto=auto if auto is not None else "", neu=neu if neu is not None else "", richtig=auto == neu, nr=nr,
             kuerzel=kuerzel)
    if text:
        e["text"] = str(text)[:TEXT_MAX]
    e.update({k: v for k, v in weitere.items() if v not in (None, "")})
    p = pfad(wurzel)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return e


def rueckmeldungen(wurzel, feld=None):
    """Alle Rückmeldungen (bzw. eines Felds), älteste zuerst; kaputte Zeilen werden übersprungen."""
    p = pfad(wurzel) if wurzel else None
    if p is None or not p.is_file():
        return []
    out = []
    for z in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            e = json.loads(z)
        except ValueError:
            continue
        if isinstance(e, dict) and (feld is None or e.get("feld") == feld):
            out.append(e)
    out.sort(key=lambda e: e.get("zeit", ""))
    return out
