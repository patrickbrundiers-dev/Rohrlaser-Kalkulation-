"""Mehrmenge ohne weitere Stange (Roadmap Kalkulation, Phase 1, CAM-010; Freigabe Patrick 12.11.2026).

Bleibt auf den Stangen einer Abmessung nach der Optimierung Platz, nennt der Angebots-Check je Position, wie viele
Teile zusätzlich darauf passen, ohne dass eine Stange mehr gebraucht wird, und den Stückpreis bei dieser Menge. Nur
Hinweis: keine Staffel und keine Menge ändert sich von selbst. Gezählt wird mit Teilelänge + Schnittverlust der
Maschine auf dem freien Rest jeder Stange (Stange − Endbeschnitt − Teile − Schnittverluste − Greiferrest); die
Probe-Optimierung mit der neuen Menge muss dieselbe Zahl Stangen ergeben, sonst wird die Menge verkleinert.
Nicht für Sätze, Musterteile, Halbschalen, Zukauf und Kundenmaterial. Ohne Qt."""
import math

ZIEL_PREFIX = "pos:"
HOECHSTENS_POSITIONEN = 3       # so viele Positionen bekommen eine Probe-Rechnung (Rechenzeit)


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def geeignet(p):
    from .angebot import aktiv, ist_muster
    from .rechnen import beigestellt, kein_laserteil
    return (aktiv(p) and not kein_laserteil(p) and not beigestellt(p) and not ist_muster(p)
            and not str(p.get("satz") or "").strip() and _n(p.get("laenge")) > 0 and _n(p.get("stueck")) > 0
            and _n(p.get("je_umfang")) <= 1)


def kandidaten(kopf, positionen, ergebnis, k):
    """{Positionsindex: zusätzliche Teile} nach dem freien Rest der Stangen ihrer Gruppe (ohne Probe-Optimierung)."""
    from .rechnen import gruppe_der_stange, gruppe_von, maschine
    kerf = _n((maschine(kopf, k) or {}).get("schnittverlust"))
    frei = {}
    for s in (ergebnis or {}).get("stangen") or ():
        if s.get("werkstuecke") or s.get("muster") or s.get("beistellung"):
            continue
        rest = _n(s.get("stange")) - _n(s.get("end")) - sum(_n(t.get("laenge")) for t in s.get("teile") or ()) \
            - _n(s.get("verlust")) - _n(s.get("greif"))
        if rest > 0:
            frei.setdefault(gruppe_der_stange(s)[:4], []).append(rest)
    out = {}
    for i, p in enumerate(positionen):
        if not geeignet(p):
            continue
        reste = frei.get(tuple(gruppe_von(p, kopf)[:4]))
        if not reste:
            continue
        n = sum(int(math.floor((r + 1e-6) / (_n(p["laenge"]) + kerf))) for r in reste)
        if n >= 1:
            out[i] = n
    return out


def pruefen(kopf, positionen, ergebnis, k, tabellen, einst, i, n):
    """Größte Zusatzmenge ≤ n, bei der die Optimierung nicht mehr Stangen braucht: (Zusatz, Stückpreis) oder None."""
    from .rechnen import kalkulation, optimieren
    basis = len((ergebnis or {}).get("stangen") or ())
    fehler = len((ergebnis or {}).get("fehler") or ())
    stueck = _n(positionen[i].get("stueck"))
    while n >= 1:
        pos = [dict(x, stueck=stueck + n) if j == i else x for j, x in enumerate(positionen)]
        erg = optimieren(kopf, pos, k, tabellen, einst)
        if len(erg.get("stangen") or ()) <= basis and len(erg.get("fehler") or ()) <= fehler:
            zeilen, _ = kalkulation(kopf, pos, erg, k, tabellen, einst)
            if zeilen[i]:
                return n, zeilen[i]["preis_teil"]
            return None
        n = n // 2 if n > 1 else 0
    return None


def punkte(kopf, positionen, ergebnis, k, tabellen, einst, kalk_zeilen):
    """HINWEIS-Punkte für den Angebots-Check (Ziel: die Position)."""
    from . import angebot_check
    from .stammdaten import zahl_als_text as zahl
    out = []
    kand = sorted(kandidaten(kopf, positionen, ergebnis, k).items(), key=lambda x: -x[1])
    for i, n in kand[:HOECHSTENS_POSITIONEN]:
        r = pruefen(kopf, positionen, ergebnis, k, tabellen, einst, i, n)
        if not r:
            continue
        mehr, preis = r
        p = positionen[i]
        jetzt = _n((kalk_zeilen[i] or {}).get("preis_teil")) if kalk_zeilen and i < len(kalk_zeilen) else 0.0
        neu = _n(p.get("stueck")) + mehr
        text = (f"Pos. {p.get('pos') or i + 1}: bis zu {mehr:.0f} Stück mehr passen ohne weitere Stange "
                f"({neu:.0f} statt {_n(p.get('stueck')):.0f} Stück: {zahl(preis, 2)} € statt {zahl(jetzt, 2)} € je Stück)")
        out.append(angebot_check.Punkt(
            angebot_check.HINWEIS, text, f"{ZIEL_PREFIX}{i}",
            "Platz auf den Stangen dieser Abmessung; teilen sich mehrere Positionen die Stangen, gilt der Platz nur "
            "einmal. Nur Hinweis: Menge oder Staffel bitte selbst anlegen."))
    return out
