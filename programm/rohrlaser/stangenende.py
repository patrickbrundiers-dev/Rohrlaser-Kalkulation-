"""Teil am Stangenende (Plan ArTube-Unterlagen A1, Patrick 12.11.2026; Adige LT8.20 „Abfallvorstellungszyklus“).

Die Maschine trennt den Abfall am Stangenende vor dem letzten Teil ab; das letzte Teil bleibt im Greifer und wird
mit dem Stangenende entladen. Es nutzt so den Greiferrest. Bedingungen (Handbuch 2.1.1, 2.1.4):
- Maschinenfeld 'Teil am Stangenende (Abfall vorziehen)' = ja;
- Ende B des Teils gerade (es ist das rohe Stangenende) und keine 3D-Bearbeitung mit Greifmaß;
- im Spannbereich keine Kontur und keine Gravur: Spannbereich = Greiferrest (Patrick 12.11.2026), gemessen ab Ende B;
- der Abfall vor dem letzten Teil liegt zwischen Mindestabfall (Vorgabe 5 mm, wie der Mindestabstand der Teile im
  Nesting) und höchstens Abfall (Vorgabe 300 mm, Abfallband). Die Optimierung rechnet mit dem Mindestabfall; ist der
  Greiferrest größer als der höchste Abfall, gibt es kein Teil am Stangenende (sonst ginge der Abfall nicht aufs Band).

Konturen ohne Lage (gleichmäßig verteilt) und Positionen mit Konturen ohne Konturliste zählen zur sicheren Seite als
„Kontur im Spannbereich“. Ohne Qt."""
import math

MIN_ABFALL = 5.0        # [mm] Vorgabe Mindestabfall
MAX_ABFALL = 300.0      # [mm] Vorgabe höchster Abfall (Abfallband)
EPS = 1e-6


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def kann(m):
    """Kann die Maschine das Teil am Stangenende? (Maschinenfeld 'stangenende' = ja)"""
    return (m or {}).get("stangenende") == "ja"


def mindestabfall(m):
    v = (m or {}).get("stangenende_min")
    return _n(v) if isinstance(v, (int, float)) and v >= 0 else MIN_ABFALL


def hoechstabfall(m):
    v = (m or {}).get("stangenende_max")
    return _n(v) if isinstance(v, (int, float)) and v > 0 else MAX_ABFALL


def bonus(m, greif):
    """So viel weniger bleibt hinter einem Teil am Stangenende frei [mm]: Greiferrest − Mindestabfall; 0 = geht nicht."""
    greif = _n(greif)
    if not kann(m) or greif > hoechstabfall(m) + EPS:
        return 0.0
    return max(0.0, greif - mindestabfall(m))


def abstand_b(p):
    """Kleinster Abstand einer Kontur oder Gravur von Ende B [mm]; math.inf ohne Konturen; None = unbekannt (Kontur
    ohne Lage, Konturen ohne Konturliste, Biegerohr bzw. Knickrahmen)."""
    from . import schneidweg as sw, skizze as sk
    laenge = _n(p.get("laenge"))
    e = sw.lesen(p.get("technik")) if p.get("technik") else None
    konturen = (e or {}).get("konturen") or []
    if e and (e.get("biegerohr") or e.get("knickrahmen")):
        return None
    if not konturen:
        if any(_n(p.get(f)) > 0 for f in ("innen", "gravur", "klein_n", "mittel_n", "gross_n")):
            return None
        return math.inf
    x_max = -math.inf
    for d in sk.lagen(konturen, laenge):
        if d.get("verteilt"):
            return None
        ein = d["eingabe"]
        x = _n(d["x"]) + _n(ein.get("_dx"))
        pts = sk.umriss_kontur(ein)
        x_max = max(x_max, x + (max(dx for dx, _ in pts) if pts else _n(d.get("huelle")) / 2))
    return math.inf if x_max == -math.inf else laenge - x_max


def frei(p, m, greif, b_gerade, rest=0.0):
    """Darf die Position als letztes Teil in den Greiferrest? (Grund als Text, '' = ja)"""
    if bonus(m, greif) <= EPS:
        return "Maschine ohne Teil am Stangenende"
    if not b_gerade:
        return "Ende B nicht gerade"
    if _n(rest) > _n(greif) + EPS:
        return "3D-Bearbeitung nahe Ende B"
    a = abstand_b(p)
    if a is None:
        return "Lage der Konturen unbekannt"
    if a < _n(greif) - EPS:
        return f"Kontur {max(a, 0):.0f} mm vor Ende B im Spannbereich ({_n(greif):.0f} mm)".replace(".", ",")
    return ""


GANZ_TOL = 1.0          # [mm] Teil darf so viel von der Lieferlänge abweichen und gilt als ganze Stange


def ganze_stange(p, m, lang, greif, a_gerade=True, b_gerade=True):
    """Ganze Stange ohne Trennschnitt (Plan ArTube-Unterlagen A3, Patrick 12.11.2026): das Teil ist so lang wie die
    Lieferstange (± 1 mm), beide Enden gerade (die rohen Stangenenden bleiben), Maschinenfeld 'Ganze Stange ohne
    Trennschnitt' = ja und im Spannbereich (Greiferrest ab Ende B) keine Kontur. Text des Hindernisses, '' = ja,
    None = kein Teil in Lieferlänge (nichts zu melden)."""
    laenge, lang = _n(p.get("laenge")), _n(lang)
    if lang <= 0 or abs(laenge - lang) > GANZ_TOL + EPS:
        return None
    if (m or {}).get("ganze_stange") != "ja":
        return "Maschine ohne ganze Stange"
    if not (a_gerade and b_gerade):
        return "Enden nicht gerade"
    a = abstand_b(p)
    if a is None:
        return "Lage der Konturen unbekannt"
    if a < _n(greif) - EPS:
        return f"Kontur {max(a, 0):.0f} mm vor Ende B im Spannbereich ({_n(greif):.0f} mm)".replace(".", ",")
    return ""
