"""Anzahl Sätze und Stück je Satz ändern (Patrick 31.10.2026, Freigabe „Alle Empfehlungen“).

Ein Satz sind die Positionen mit gleichem Eintrag in der Spalte Satz. Jede trägt „Stück je Satz“ und ihre Stückzahl;
die Anzahl Sätze ist Stückzahl ÷ Stück je Satz (rechnen.saetze_von). Damit beides zusammenpasst:

- Anzahl Sätze ändern (Fenster „Satz bearbeiten“, Feld „Sätze“ im Satz in 3D): Stückzahl = Sätze × Stück je Satz für
  alle Positionen des Satzes.
- Stück je Satz ändern: die Stückzahl zieht mit (Anzahl Sätze bleibt).
- Stückzahl einer Satzposition ändern (F1a): Stück je Satz rechnet sich mit (Stückzahl ÷ Anzahl Sätze). Geht das
  nicht in ganzen Stück auf (z. B. 7 Stück bei 3 Sätzen), bleibt Stück je Satz, die Stückzahl wird wie getippt
  übernommen und ein Hinweis erscheint (F3a, nichts gerundet).

Schweißbaugruppen und ihre Teile bleiben außen vor: dort folgen Satz, Stück je Satz und Stückzahl der Struktur
(baugruppe.abgleich), die Anzahl steht im Editor der Baugruppe („Anzahl Baugruppen“). Nur Rechnen, keine Oberfläche.
"""
from collections import Counter


def _n(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def name(p):
    return str((p or {}).get("satz") or "").strip()


def je_satz(p):
    """Stück je Satz (leer = 1, wie rechnen.saetze_von)."""
    j = _n((p or {}).get("je_satz"))
    return int(j) if j and j >= 1 else 1


def satz_positionen(positionen, satz):
    """Indizes der Positionen des Satzes ohne Schweißbaugruppen und deren Teile."""
    from .satzgruppen import ausgenommen
    satz = str(satz or "").strip()
    if not satz:
        return []
    aus = ausgenommen(positionen)
    return [i for i, p in enumerate(positionen) if name(p) == satz and i not in aus]


def gehoert_zum_satz(p, positionen):
    """True, wenn p in einem Satz steht, den diese Regeln führen (kein Teil einer Schweißbaugruppe)."""
    if not name(p):
        return False
    pid = (p or {}).get("id")
    return any(positionen[i].get("id") == pid for i in satz_positionen(positionen, name(p)))


def anzahl(positionen, satz, ohne_id=None):
    """Anzahl Sätze des Satzes: die häufigste ganze Anzahl der Positionen (bei Gleichstand die größte, wie das
    Angebot); ohne_id lässt eine Position weg (die gerade geändert wird). None ohne Stückzahlen."""
    werte = []
    for i in satz_positionen(positionen, satz):
        p = positionen[i]
        st = _n(p.get("stueck"))
        if p.get("id") == ohne_id or not st or st <= 0:
            continue
        werte.append(st / je_satz(p))
    if not werte:
        return None
    zaehler = Counter(round(w, 6) for w in werte)
    best = max(zaehler.items(), key=lambda kv: (kv[1], kv[0]))[0]
    return int(best) if abs(best - round(best)) < 1e-6 else best


def saetze_setzen(positionen, satz, n, je=None):
    """Änderungen [(Positions-ID, Feld, Wert)] für n Sätze; je = {Positions-ID: Stück je Satz} ändert dazu Stück je
    Satz einzelner Positionen. Stückzahl = n × Stück je Satz."""
    n = int(n)
    je = je or {}
    out = []
    for i in satz_positionen(positionen, satz):
        p = positionen[i]
        j = int(je.get(p["id"], je_satz(p)))
        if j < 1:
            continue
        if p["id"] in je and j != _n(p.get("je_satz")):
            out.append((p["id"], "je_satz", j))
        if n >= 1 and _n(p.get("stueck")) != n * j:
            out.append((p["id"], "stueck", n * j))
    return out


def je_satz_geaendert(p, positionen, neu):
    """Stück je Satz einer Satzposition auf neu: die Stückzahl zieht mit. Ergebnis: (Änderungen, Hinweis)."""
    if not gehoert_zum_satz(p, positionen) or not _n(neu) or neu < 1:
        return [], None
    n = anzahl(positionen, name(p), ohne_id=p.get("id"))
    if n is None:
        st = _n(p.get("stueck"))
        n = st / je_satz(p) if st else None
    if not n or abs(n - round(n)) > 1e-6:
        return [], None
    st = int(round(n)) * int(neu)
    if st == _n(p.get("stueck")):
        return [], None
    return [(p["id"], "stueck", st)], f"Stückzahl folgt: {int(round(n))} Sätze × {int(neu)} = {st}."


def stueck_geaendert(p, positionen, neu):
    """Stückzahl einer Satzposition auf neu (F1a): Stück je Satz = neu ÷ Anzahl Sätze; geht es nicht ganz auf,
    bleibt Stück je Satz und es kommt ein Hinweis (F3a). Ergebnis: (Änderungen, Hinweis)."""
    if not gehoert_zum_satz(p, positionen) or not _n(neu) or neu <= 0:
        return [], None
    n = anzahl(positionen, name(p), ohne_id=p.get("id"))
    if n is None:           # einzige Position mit Stückzahl: sie bestimmt die Anzahl Sätze
        return [], None
    j = neu / n
    if j < 1 or abs(j - round(j)) > 1e-6:
        return [], (f"Satz {name(p)}: {_text(neu)} Stück passen nicht in ganzen Stück auf {_text(n)} Sätze. "
                    "Stück je Satz bleibt; Anzahl Sätze ändern über „Satz bearbeiten …“.")
    j = int(round(j))
    if j == je_satz(p) and p.get("je_satz") is not None:
        return [], None
    return [(p["id"], "je_satz", j)], f"Stück je Satz folgt: {_text(neu)} ÷ {_text(n)} Sätze = {j}."


def _text(x):
    return str(int(x)) if _n(x) is not None and abs(x - round(x)) < 1e-9 else str(x).replace(".", ",")
