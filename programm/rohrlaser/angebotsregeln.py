"""Eigene Wenn-Dann-Regeln im Angebots-Check (Vorschläge 11.11.2026 V4, Freigabe „Alle Empfehlungen“, F2 a).

Vorbild: Regel-Bibliotheken anderer Angebotsprogramme, damit die Erfahrung des Betriebs nicht nur im Kopf steckt.
Stammdaten-Tabelle „Angebotsregeln“: je Regel Bedingungen, die ALLE zutreffen müssen (leer = egal): Kunde,
Werkstoff-Kategorie, Werkstoff, Profilform, Wand von/bis, Teilelänge von/bis, Stückzahl von/bis, Innenkonturen ab,
Merkmal (wie bei den Arbeitsgang-Regeln, z. B. „Schräges Ende“) und Zusatzarbeit. Die Wirkung:
  Hinweis / Warnung     Punkt im Angebots-Check mit dem eigenen Text
  Rückfrage             WARNUNG „Rückfrage: …“; sie kommt damit in die „Rückfrage an den Kunden“
  Zuschlag              Zuschlag [%] auf den Preis der betroffenen Positionen (preisschicht.py, Baustein „regel“),
                        immer sichtbar als HINWEIS im Check und als Kostenart in der Kalkulation; nur neue Angebote:
                        festgeschriebene Angebote rechnen mit den Regeln ihrer Preisbasis (ältere: ohne Zuschlag)
  Nicht anbieten        FEHLER im Angebots-Check (übergehen nur mit Begründung)
Es gibt keine stille Preisänderung. Ohne Qt."""

HINWEIS, WARNUNG, RUECKFRAGE, ZUSCHLAG, NICHT = "Hinweis", "Warnung", "Rückfrage", "Zuschlag", "Nicht anbieten"
WIRKUNGEN = (HINWEIS, WARNUNG, RUECKFRAGE, ZUSCHLAG, NICHT)
# Felder, die in den Snapshot der Preisbasis kommen (nur Zuschlag-Regeln wirken auf den Preis)
BEDINGUNGEN = ("kundennr", "kategorie", "werkstoff_id", "profilform", "wand_von", "wand_bis", "laenge_von",
               "laenge_bis", "stueck_von", "stueck_bis", "konturen_ab", "merkmal", "zusatzarbeit")


def _leer(w):
    return w is None or (isinstance(w, str) and not w.strip())


def _n(w):
    try:
        return float(w) if not _leer(w) else 0.0
    except (TypeError, ValueError):
        return 0.0


def aktiv(regel):
    return str((regel or {}).get("aktiv") or "ja") != "nein"


def wirkung(regel):
    w = (regel or {}).get("wirkung")
    return w if w in WIRKUNGEN else HINWEIS


def konturen(p):
    """Anzahl Innenkonturen der Position (STEP-Import: klein + mittel + groß)."""
    return int(_n(p.get("klein_n")) + _n(p.get("mittel_n")) + _n(p.get("gross_n")))


def zusatz_namen(p):
    import json
    z = p.get("zusatz")
    try:
        liste = json.loads(z) if isinstance(z, str) and z else (z or [])
    except ValueError:
        liste = []
    return {str(e.get("name")) for e in liste if isinstance(e, dict) and e.get("name")}


def trifft(regel, p, kopf, k, gewinde=()):
    """True, wenn die Position alle ausgefüllten Bedingungen der aktiven Regel erfüllt."""
    from . import rechnen
    from .zusatz_regeln import merkmal_trifft
    if not aktiv(regel):
        return False
    pr = (k.profile.get(p.get("profil_id")) if k else None) or {}
    gleich = (("kundennr", lambda: (kopf or {}).get("kundennr")),
              ("kategorie", lambda: rechnen.kategorie(p.get("werkstoff_id"), k) if k else None),
              ("werkstoff_id", lambda: p.get("werkstoff_id")), ("profilform", lambda: pr.get("form")))
    if any(not _leer(regel.get(n)) and str(regel[n]) != str(wert()) for n, wert in gleich):
        return False
    bereiche = (("wand", lambda: pr.get("wand")), ("laenge", lambda: p.get("laenge")),
                ("stueck", lambda: p.get("stueck")))
    for n, wert in bereiche:
        von, bis = regel.get(f"{n}_von"), regel.get(f"{n}_bis")
        if _leer(von) and _leer(bis):
            continue
        w = wert()
        if _leer(w):
            return False
        if not _leer(von) and _n(w) < _n(von) - 1e-9 or not _leer(bis) and _n(w) > _n(bis) + 1e-9:
            return False
    if not _leer(regel.get("konturen_ab")) and konturen(p) < _n(regel["konturen_ab"]):
        return False
    if not _leer(regel.get("zusatzarbeit")) and str(regel["zusatzarbeit"]) not in zusatz_namen(p):
        return False
    return merkmal_trifft(regel.get("merkmal"), p, gewinde)


def treffer(regeln, kopf, positionen, k, gewinde=()):
    """[(Regel, [Positionsindex])] der aktiven Regeln mit mindestens einer passenden Position."""
    out = []
    for r in regeln or ():
        idx = [i for i, p in enumerate(positionen) if trifft(r, p, kopf, k, gewinde)]
        if idx:
            out.append((r, idx))
    return out


def zuschlaege(regeln, kopf, positionen, k, gewinde=()):
    """Zuschlag je Position {Positionsindex: (Anteil, [Regelname])}; mehrere Zuschlag-Regeln addieren sich."""
    out = {}
    for r, idx in treffer([r for r in regeln or () if wirkung(r) == ZUSCHLAG and _n(r.get("zuschlag")) > 0],
                          kopf, positionen, k, gewinde):
        for i in idx:
            alt, namen = out.get(i, (0.0, []))
            out[i] = (alt + _n(r["zuschlag"]) / 100, namen + [str(r.get("name") or "Regel")])
    return out


def _z(w):
    return f"{w:g}".replace(".", ",")


def _text(r):
    t = str(r.get("text") or "").strip()
    return t or f"Angebotsregel „{r.get('name') or ''}“ trifft zu"


def punkte(regeln, kopf, positionen, k, gewinde=()):
    """Punkte für den Angebots-Check."""
    from . import angebot_check as ac
    art = {HINWEIS: ac.HINWEIS, WARNUNG: ac.WARNUNG, RUECKFRAGE: ac.WARNUNG, ZUSCHLAG: ac.HINWEIS, NICHT: ac.FEHLER}
    out = []
    for r, idx in treffer(regeln, kopf, positionen, k, gewinde):
        w = wirkung(r)
        nr = [str(positionen[i].get("pos") or i + 1) for i in idx]
        pos = "Pos. " + ", ".join(nr[:8]) + (" …" if len(nr) > 8 else "")
        if w == ZUSCHLAG:
            if _n(r.get("zuschlag")) <= 0:
                continue
            text = f"Zuschlag {_z(_n(r['zuschlag']))} % durch Angebotsregel „{r.get('name') or ''}“" + (
                f": {str(r.get('text')).strip()}" if not _leer(r.get("text")) else "")
        elif w == RUECKFRAGE:
            text = f"Rückfrage: {_text(r)}"
        elif w == NICHT:
            text = f"Nicht anbieten (Angebotsregel „{r.get('name') or ''}“): {_text(r)}"
        else:
            text = _text(r)
        out.append(ac.Punkt(art[w], text, f"pos:{idx[0]}", f"{pos} – Angebotsregel „{r.get('name') or ''}“"))
    return out


def fuer_snapshot(regeln):
    """Zuschlag-Regeln für die Preisbasis (nur aktive mit Zuschlag > 0)."""
    from .stammdaten import ANGEBOTSREGELN
    return [{f.name: r.get(f.name) for f in ANGEBOTSREGELN.felder} for r in regeln or ()
            if aktiv(r) and wirkung(r) == ZUSCHLAG and _n(r.get("zuschlag")) > 0]


def beispiele():
    """Vorbelegung (aus): Beispiele, bitte an die eigene Fertigung anpassen."""
    from .stammdaten import ANGEBOTSREGELN

    def r(name, **w):
        return dict({f.name: None for f in ANGEBOTSREGELN.felder}, **dict(dict(name=name, aktiv="nein"), **w))
    return [r("Edelstahl dick mit Gehrung", kategorie="Edelstahl", wand_von=4.0, merkmal="Schräges Ende",
              wirkung=ZUSCHLAG, zuschlag=8.0, text="dicke Edelstahl-Gehrungen brauchen langsameren Vorschub",
              bemerkung="Beispiel: bei Bedarf aktivieren"),
            r("Sehr lange Teile", laenge_von=6000.0, wirkung=WARNUNG,
              text="Teil über 6 m: Abstützung und Entladen prüfen", bemerkung="Beispiel"),
            r("Kleine Stückzahl viele Konturen", stueck_bis=5, konturen_ab=20, wirkung=RUECKFRAGE,
              text="Gibt es eine größere Jahresmenge? Bei vielen Konturen lohnt sich ein Staffelpreis",
              bemerkung="Beispiel")]
