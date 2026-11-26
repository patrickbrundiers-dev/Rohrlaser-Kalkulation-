"""Technische Machbarkeit eines Nesting-Plans (Nesting-Arbeitsplatz 2.0, Patrick 24.11.2026: „Eine rechnerisch
optimale Verschachtelung darf nicht automatisch als fertigungstechnisch möglich eingestuft werden“). Ohne Qt.

Geprüft wird je Plan mit den Werten der Maschine der Gruppe (Stammdaten Maschinen):
  Fehler (Plan unzulässig, wird im Vergleich ausgeschlossen und nie empfohlen):
    - Stange länger als die max. Stangenlänge (Beladelänge) der Maschine,
    - Profil zu groß/zu klein für die Spannfutter (max./min. Hüllkreis), Metergewicht über der Grenze,
      Stange schwerer als der Lader zulässt (rechnen.grenze_ueberschritten, dieselbe Regel wie beim Optimieren),
    - Stange überbelegt oder Längenbilanz falsch (nesting.pruefe; Greiferrest bzw. 3D-Greifmaß frei).
  Hinweise (Plan bleibt zulässig, steht im Protokoll):
    - Reststück oder Stange kürzer als das Lademinimum (von Hand laden),
    - Teil kürzer als das kürzeste Teil der Maschine (Entnahme prüfen),
    - Teil mit 3D-Bearbeitung nicht am Stangenende (die Engine legt es dorthin, wenn es Platz braucht).
Spannmöglichkeiten, Zugänglichkeit und Schnittreihenfolge stecken schon in den Fertigungsregeln der Engine
(Greiferrest, 3D-Greifmaß, Gehrungsabstand, Nahtlage, gemeinsamer Schnitt nur bei zwei geraden Enden); sie werden
hier nicht ein zweites Mal geschätzt.
"""
from dataclasses import dataclass

from . import nesting as ne, optimierung as opt
from .zahlen import float_oder_0 as _n  # Audit 26.11.2026 R-01: gemeinsame Hilfsfunktion

FEHLER, HINWEIS = "Fehler", "Hinweis"
EPS = 1e-6


@dataclass(frozen=True)
class Befund:
    stufe: str
    text: str
    stange: int = None      # Nummer der Stange im Plan (1 …) oder None = ganzer Plan


def pruefen(g, stangen, m=None, profil=None, kgm=None, uebrig=(), reste=()):
    """Befunde [Befund] des Plans stangen [(Länge, Folge, Rest-Kennung)] der Gruppe g auf der Maschine m (dict der
    Maschinen-Stammdaten oder None), profil = Profilzeile (form, a, b) oder None, kgm = kg/m oder None."""
    from . import rechnen
    out = []
    m = m or {}
    try:
        ne.pruefe(g, stangen, list(uebrig), None, reste)
    except AssertionError as e:
        out.append(Befund(FEHLER, f"Kontrolle: {e}"))
    maxw, lade, min_teil = _n(m.get("max_stange")), _n(m.get("lademinimum")), _n(m.get("min_teil"))
    gesehen = set()
    for i, (laenge, folge, rest) in enumerate(stangen, 1):
        if maxw and laenge > maxw + EPS:
            out.append(Befund(FEHLER, f"Stange {i}: {laenge:g} mm länger als die max. Stangenlänge der Maschine "
                                      f"({maxw:g} mm)", i))
        if laenge not in gesehen:
            gesehen.add(laenge)
            grund = rechnen.grenze_ueberschritten(m, profil, kgm, laenge) if m else None
            if grund:
                out.append(Befund(FEHLER, f"{laenge:g} mm: {grund}", i))
        if lade and laenge + EPS < lade:
            out.append(Befund(HINWEIS, f"Stange {i}{' (Reststück ' + rest + ')' if rest else ''}: {laenge:g} mm "
                                       f"kürzer als das Lademinimum {lade:g} mm, von Hand laden", i))
        for t, _ in folge:
            if min_teil and t.laenge + EPS < min_teil:
                out.append(Befund(HINWEIS, f"Stange {i}: Teil Pos. {t.pos} {t.laenge:g} mm kürzer als das kürzeste "
                                           f"Teil der Maschine ({min_teil:g} mm)", i))
                break
        h = opt.replace(g, stange=laenge, teile=[])
        drei_d = [t for t, _ in folge if t.rest > g.greiferrest + EPS]
        if drei_d and folge and folge[-1][0] not in drei_d and opt.hinten(h, folge) + EPS < max(t.rest for t in drei_d):
            out.append(Befund(HINWEIS, f"Stange {i}: Teil mit 3D-Bearbeitung nicht am Stangenende", i))
    if profil is None and m and (_n(m.get("max_huellkreis")) or _n(m.get("min_huellkreis"))):
        out.append(Befund(HINWEIS, "Profilmaße unbekannt: Hüllkreis nicht geprüft"))
    return out


def zulaessig(befunde):
    return not any(b.stufe == FEHLER for b in befunde)


def text(befunde, max_n=4):
    """Kurztext der Befunde für Tabelle und Protokoll."""
    if not befunde:
        return "zulässig"
    f = [b.text for b in befunde if b.stufe == FEHLER]
    h = [b.text for b in befunde if b.stufe == HINWEIS]
    teile = (["unzulässig: " + "; ".join(f[:max_n])] if f else []) + (["; ".join(h[:max_n])] if h else [])
    return " · ".join(teile)
