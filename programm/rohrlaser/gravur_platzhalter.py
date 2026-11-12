"""Gravurtext mit Platzhaltern (Plan ArTube-Unterlagen D2, Patrick 12.11.2026 „Alles einbauen“).

Statt nur der Artikelnummer graviert der Laser einen Text aus der Position-Spalte „Gravurtext (Platzhalter)“, z. B.
„{Angebot} {Artikel} {Nr}“. Platzhalter: {Artikel}, {Pos}, {Angebot}, {Kunde}, {Datum}, {KW}, {Nr} (laufende Nummer
„23/1000“ je Teil) und {Stück}. Mehrere Gravurbereiche werden mit „|“ getrennt. Grenzen wie in ArTube: höchstens 5
Bereiche, je Bereich 30 Zeichen, Schrifthöhe mindestens 3 mm (darunter liest man die Gravur nicht sicher). Die
Schrifthöhe kommt aus „Gravur Artikelnr. h [mm]“, leer = 3 mm. Die Lage sucht der STEP-Export wie bei der
Artikelnummer automatisch (größter Abstand zu Enden und Konturen). Ohne Qt."""
import datetime
import re

PLATZHALTER = ("Artikel", "Pos", "Angebot", "Kunde", "Datum", "KW", "Nr", "Stück")
TRENNER = "|"
MAX_BEREICHE = 5
MAX_ZEICHEN = 30
MIN_HOEHE = 3.0
_MUSTER = re.compile(r"\{([^{}]*)\}")


def vorlage(p):
    return str((p or {}).get("gravur_text") or "").strip()


def hoehe(p):
    """Schrifthöhe [mm]: 'Gravur Artikelnr. h [mm]', leer = 3 mm."""
    h = (p or {}).get("bg_gravur")
    return float(h) if isinstance(h, (int, float)) and not isinstance(h, bool) and h > 0 else MIN_HOEHE


def _datum(kopf, datum):
    if datum is None:
        t = str((kopf or {}).get("datum") or "")
        try:
            datum = datetime.date.fromisoformat(t[:10])
        except ValueError:
            datum = datetime.date.today()
    return datum


def ausfuellen(text, p, kopf=None, nr=1, datum=None):
    """Text mit eingesetzten Platzhaltern für das Teil Nr. nr; unbekannte Platzhalter bleiben stehen."""
    p, kopf = p or {}, kopf or {}
    d = _datum(kopf, datum)
    stk = int(p.get("stueck") or 0) if isinstance(p.get("stueck"), (int, float)) else 0
    pos = p.get("pos")
    werte = {"Artikel": str(p.get("artikel") or ""),
             "Pos": "" if pos is None else (str(int(pos)) if isinstance(pos, float) and pos == int(pos) else str(pos)),
             "Angebot": str(kopf.get("nummer") or ""), "Kunde": str(kopf.get("kunde") or ""),
             "Datum": d.strftime("%d.%m.%y"), "KW": f"KW{d.isocalendar()[1]:02d}",
             "Nr": f"{nr}/{stk}" if stk else str(nr), "Stück": str(stk or "")}
    return _MUSTER.sub(lambda m: werte.get(m.group(1).strip(), m.group(0)), str(text or "")).strip()


def bereiche(text):
    return [b.strip() for b in str(text or "").split(TRENNER) if b.strip()]


def text_fuer(p, kopf=None, nr=None):
    """Gravierter Text des Teils: Vorlage mit Platzhaltern, sonst die Artikelnummer. Ohne nr der längste (letzte
    laufende Nummer), für die Gravurlänge der Kalkulation."""
    v = vorlage(p)
    if not v:
        return str((p or {}).get("artikel") or "")
    if nr is None:
        stk = (p or {}).get("stueck")
        nr = int(stk) if isinstance(stk, (int, float)) and stk >= 1 else 1
    return ausfuellen(v, p, kopf, nr)


def texte(p, kopf=None):
    """Gravurtext je Teil (laufende Nummer 1 … Stückzahl), leer ohne Vorlage."""
    if not vorlage(p):
        return []
    stk = (p or {}).get("stueck")
    n = int(stk) if isinstance(stk, (int, float)) and stk >= 1 else 1
    if "{Nr}" not in vorlage(p).replace(" ", ""):
        return [ausfuellen(vorlage(p), p, kopf, 1)] * n
    return [ausfuellen(vorlage(p), p, kopf, i) for i in range(1, n + 1)]


def pruefen(p, kopf=None):
    """Meldungen zur Vorlage (WARNUNG …/HINWEIS …), leer ohne Vorlage oder wenn alles passt."""
    v = vorlage(p)
    if not v:
        return []
    out = []
    unbekannt = [m.strip() for m in _MUSTER.findall(v) if m.strip() not in PLATZHALTER]
    if unbekannt:
        out.append(f"WARNUNG: Gravurtext: Platzhalter {{{unbekannt[0]}}} unbekannt (möglich: "
                   + ", ".join("{" + n + "}" for n in PLATZHALTER) + ")")
    b = bereiche(text_fuer(p, kopf))
    if len(b) > MAX_BEREICHE:
        out.append(f"WARNUNG: Gravurtext: {len(b)} Bereiche, höchstens {MAX_BEREICHE}")
    lang = [x for x in b if len(x) > MAX_ZEICHEN]
    if lang:
        out.append(f"WARNUNG: Gravurtext: „{lang[0][:20]}…“ hat {len(lang[0])} Zeichen, höchstens {MAX_ZEICHEN} je "
                   "Bereich")
    h = (p or {}).get("bg_gravur")
    if isinstance(h, (int, float)) and 0 < h < MIN_HOEHE:
        out.append(f"HINWEIS: Gravurtext: Schrifthöhe {h:g} mm unter {MIN_HOEHE:g} mm, schlecht lesbar")
    return out


def step_gravur(p, kopf=None):
    """(Text, Schrifthöhe) für das 3D-Modell bzw. die STEP-Datei: mit Vorlage der Text von Teil 1 (Bereiche
    nebeneinander) und hoehe(p), sonst Artikelnummer und 'Gravur Artikelnr. h [mm]' wie bisher."""
    if vorlage(p):
        return "  ".join(bereiche(text_fuer(p, kopf, 1))), hoehe(p)
    return (p or {}).get("artikel"), (p or {}).get("bg_gravur")
