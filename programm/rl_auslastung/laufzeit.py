"""Laufzeit lesen und schreiben (Patrick 11.11.2026: Stunden und Minuten, verschiedene Schreibweisen bei der Eingabe).

Gespeichert wird immer in ganzen Minuten. Gelesen werden unter anderem:

- 1 Stunde 30 Minuten, 1 Std 30 Min, 1 h 30 min, 1h30, 1h 30m, 1 Std. und 30 Min.
- 1:30 (Stunden:Minuten), 1:30:00
- 90 Minuten, 90 min, 90 m, 90'
- 1,5 h, 1.5 Std, 1,5 Stunden
- 2 Tage 3 h (ein Tag = 24 Stunden Laufzeit), 45 s werden auf volle Minuten gerundet
- eine Zahl ohne Einheit: ganze Zahl = Minuten (einstellbar: Stunden), Kommazahl = Stunden (1,5 = 1 h 30 min)
"""
import re

FORMEN = {"hm": "1 h 30 min", "uhr": "1:30 h", "dez": "1,50 h", "min": "90 min"}
OHNE_EINHEIT = {"min": "Minuten", "h": "Stunden"}
_EINHEIT = (
    (("tage", "tagen", "tag", "d", "t"), 1440.0),
    (("stunden", "stunde", "std.", "std", "st.", "st", "h"), 60.0),
    (("minuten", "minute", "min.", "min", "m", "'", "′"), 1.0),
    (("sekunden", "sekunde", "sek.", "sek", "sec", "s", '"', "″"), 1 / 60),
)
_FAKTOR = {wort: f for woerter, f in _EINHEIT for wort in woerter}
_TEIL = re.compile(r"(\d+(?:[.,]\d+)?)\s*([a-zäöü.'′\"″]*)")
BEISPIELE = "z. B. 1 Stunde 30 Minuten, 1 h 30 min, 1:30, 90 Minuten, 90 min oder 1,5 h"


class Fehler(ValueError):
    """Eingabe nicht lesbar; der Text ist für den Benutzer."""


def lesen(text, ohne_einheit="min"):
    """Text -> ganze Minuten. Leerer Text -> None. Unlesbares -> Fehler."""
    t = str(text if text is not None else "").strip().lower()
    if not t:
        return None
    t = re.sub(r"\b(und|u\.|ca\.?|etwa)\b", " ", t).replace("+", " ").strip()
    m = re.fullmatch(r"(\d+):(\d{1,2})(?::(\d{1,2}))?\s*(h|std\.?|stunden)?", t)
    if m:
        if int(m.group(2)) > 59 or int(m.group(3) or 0) > 59:
            raise Fehler("Bei Stunden:Minuten dürfen Minuten und Sekunden höchstens 59 sein.")
        return _runden(int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3) or 0) / 60)
    gesamt, ende, letzte, teile = 0.0, 0, None, 0
    for m in _TEIL.finditer(t):
        if t[ende:m.start()].strip(" ,;"):
            raise Fehler(f"„{text}“ ist keine Laufzeit ({BEISPIELE}).")
        zahl, kommazahl = float(m.group(1).replace(",", ".")), bool(re.search(r"[.,]", m.group(1)))
        einheit = m.group(2).strip()
        if einheit and einheit not in _FAKTOR:
            raise Fehler(f"Die Einheit „{einheit}“ kenne ich nicht ({BEISPIELE}).")
        if einheit:
            faktor = _FAKTOR[einheit]
        elif letzte == 60.0:                   # 1h30, 1 Std 30: Zahl nach den Stunden sind Minuten
            faktor = 1.0
        elif letzte is None and not t[m.end():].strip():        # nur eine Zahl
            faktor = 60.0 if kommazahl or ohne_einheit == "h" else 1.0
        else:
            raise Fehler(f"Bei „{text}“ fehlt eine Einheit ({BEISPIELE}).")
        gesamt += zahl * faktor
        letzte, ende, teile = faktor, m.end(), teile + 1
    if not teile or t[ende:].strip(" ,;."):
        raise Fehler(f"„{text}“ ist keine Laufzeit ({BEISPIELE}).")
    return _runden(gesamt)


def _runden(minuten):
    n = int(minuten + 0.5)
    if n > 60 * 24 * 365:
        raise Fehler("Die Laufzeit ist länger als ein Jahr.")
    return n


def text(minuten, form="hm"):
    """Ganze Minuten -> Anzeige. None -> ''."""
    if minuten is None or minuten == "":
        return ""
    n = int(minuten)
    vz, n = ("-" if n < 0 else ""), abs(n)
    h, m = divmod(n, 60)
    if form == "uhr":
        return f"{vz}{h}:{m:02d} h"
    if form == "dez":
        return f"{vz}{n / 60:.2f} h".replace(".", ",")
    if form == "min":
        return f"{vz}{n} min"
    if h and m:
        return f"{vz}{h} h {m} min"
    return f"{vz}{h} h" if h else f"{vz}{m} min"


def lang(minuten):
    """Ausgeschrieben, als Rückmeldung unter dem Eingabefeld: '1 Stunde 30 Minuten (90 Minuten)'."""
    if minuten is None:
        return ""
    h, m = divmod(int(minuten), 60)
    teile = []
    if h:
        teile.append(f"{h} Stunde" + ("" if h == 1 else "n"))
    if m or not h:
        teile.append(f"{m} Minute" + ("" if m == 1 else "n"))
    return " ".join(teile) + (f" ({int(minuten)} Minuten)" if h else "")
