"""Preisalter-Warnung (Roadmap Kalkulation, Phase 1, MAT-009; Freigabe Patrick 12.11.2026 „Mit Phase 1 beginnen“).

Rechnet eine Position mit einem Materialpreis aus 'Preise' oder 'Lieferlängen', dessen „Gültig ab“ älter ist als die
Einstellung preisalter_tage (Vorgabe 30 Tage, 0 = aus), meldet der Angebots-Check einen HINWEIS je Abmessung mit
„Hinspringen“ zur Materialanfrage. Zeilen ohne Datum und der Tonnenpreis des Werkstoffs (ohne Datum; für ihn gibt es
den Teuerungs-Stand) zählen nicht, ebenso Positionen mit eigenem €/m, Kundenmaterial und Teile ohne Laser. Nur
Hinweis: kein Preis ändert sich. Ohne Qt."""
import datetime

VORGABE_TAGE = 30
ZIEL = "materialanfrage"


def tage(einst):
    w = (einst or {}).get("preisalter_tage")
    try:
        return VORGABE_TAGE if w is None or w == "" else int(float(w))
    except (TypeError, ValueError):
        return VORGABE_TAGE


def _datum(w):
    try:
        return datetime.date.fromisoformat(str(w or "")[:10])
    except ValueError:
        return None


def quellen(profil_id, werkstoff_id, k, tabellen, einst=None):
    """Datierte Preiszeilen, mit denen Profil + Werkstoff rechnet: [(Tabelle, Zeile, Datum)]."""
    from .rechnen import lieferlaengen, preis_zeile
    out = []
    z = preis_zeile(profil_id, werkstoff_id, k, tabellen)
    if z is not None and _datum(z.get("gueltig_ab")):
        out.append(("Preise", z, _datum(z.get("gueltig_ab"))))
    for z in lieferlaengen(profil_id, werkstoff_id, k, tabellen, einst, auto=False):
        if z.get("preis") and _datum(z.get("gueltig_ab")):
            out.append(("Lieferlängen", z, _datum(z.get("gueltig_ab"))))
    return out


def alte(positionen, k, tabellen, einst=None, heute=None):
    """Je Profil + Werkstoff mit zu altem Preis: dict(profil_id, werkstoff_id, datum (ältestes), tage, tabelle,
    zeilen [Positionsindex])."""
    from .angebot import aktiv
    from .rechnen import beigestellt, kein_laserteil
    grenze = tage(einst)
    if grenze <= 0:
        return []
    heute = heute or datetime.date.today()
    out, gesehen = [], {}
    for i, p in enumerate(positionen or ()):
        pid, wid = p.get("profil_id"), p.get("werkstoff_id")
        if not pid or not wid or not aktiv(p) or kein_laserteil(p) or beigestellt(p):
            continue
        preis_m = p.get("preis_m")
        if isinstance(preis_m, (int, float)) and not isinstance(preis_m, bool) and preis_m > 0:
            continue
        if (pid, wid) in gesehen:
            if gesehen[(pid, wid)] is not None:
                gesehen[(pid, wid)]["zeilen"].append(i)
            continue
        gesehen[(pid, wid)] = None
        q = [x for x in quellen(pid, wid, k, tabellen, einst) if (heute - x[2]).days > grenze]
        if not q:
            continue
        tabelle, _, datum = min(q, key=lambda x: x[2])
        e = dict(profil_id=pid, werkstoff_id=wid, datum=datum, tage=(heute - datum).days, tabelle=tabelle, zeilen=[i])
        gesehen[(pid, wid)] = e
        out.append(e)
    return out


def text(e):
    return (f"{e['profil_id']} {e['werkstoff_id']}: Materialpreis ({e['tabelle']}) gilt seit "
            f"{e['datum'].strftime('%d.%m.%Y')}, {e['tage']} Tage alt")


def punkte(positionen, k, tabellen, einst=None, heute=None):
    """HINWEIS-Punkte für den Angebots-Check, Ziel: Materialanfrage."""
    from . import angebot_check
    liste = alte(positionen, k, tabellen, einst, heute)
    if not liste:
        return []
    erste = text(liste[0])
    n = len(liste)
    nr = [str(positionen[i].get("pos") or i + 1) for e in liste for i in e["zeilen"]]
    details = ("; ".join(text(e) for e in liste[1:4]) + (" …" if n > 4 else "") + " – " if n > 1 else "") + \
        "Pos. " + ", ".join(nr[:6]) + (" …" if len(nr) > 6 else "") + \
        f". „Hinspringen“ öffnet die Materialanfrage (Grenze {tage(einst)} Tage, Einstellungen → Angebot)."
    titel = erste if n == 1 else f"{n} Abmessungen mit altem Materialpreis, z. B. {erste}"
    return [angebot_check.Punkt(angebot_check.HINWEIS, titel, ZIEL, details)]
