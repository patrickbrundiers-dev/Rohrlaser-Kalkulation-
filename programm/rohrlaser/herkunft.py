"""Herkunft und Sicherheit je Rechenwert (CALC-028, Patrick 12.11.2026 „Alle Empfehlungen“ zum Bericht
Entwicklungspotenziale; Regel: „Alle automatisch ermittelten Werte müssen mit ihrer Herkunft und Sicherheit
gekennzeichnet werden“).

Je Position wird der Preis je Teil in seine Bausteine geteilt (Material, Laser, Rüsten, Zusatzarbeiten, Zukauf,
Schweißen, Übriges). Jeder Baustein trägt eine Quelle und eine Sicherheit:
  Quelle:     STEP gemessen, Stammdaten, Richtwert, gelernt und freigegeben, von Hand, geschätzt
  Sicherheit: sicher, prüfen, unsicher
Zuschläge, Gewinn, Fracht und Skonto verteilen sich im Verhältnis der Kosten auf die Bausteine; so ist die Summe der
Anteile genau der Preis der Position. Nur Anzeige: keine Zahl der Kalkulation ändert sich. Ohne Qt."""
from . import rechnen

STEP, STAMMDATEN, RICHTWERT, GELERNT, HAND, GESCHAETZT = (
    "STEP gemessen", "Stammdaten", "Richtwert", "gelernt und freigegeben", "von Hand", "geschätzt")
QUELLEN = (STEP, STAMMDATEN, RICHTWERT, GELERNT, HAND, GESCHAETZT)
SICHER, PRUEFEN, UNSICHER = "sicher", "prüfen", "unsicher"
SICHERHEITEN = (SICHER, PRUEFEN, UNSICHER)
SD_STUFE = {"hoch": SICHER, "mittel": PRUEFEN, "niedrig": UNSICHER}
HINWEIS_AB = 0.05           # Angebots-Check: Hinweis ab 5 % unsicherem Anteil am Preis


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _b(baustein, kosten, quelle, sicherheit, grund=""):
    return dict(baustein=baustein, kosten=kosten, quelle=quelle, sicherheit=sicherheit, grund=grund)


def _material(z, p, kopf, k, tabellen):
    kosten = _n(z.get("material_teil")) - _n(z.get("schrott_teil")) + _n(z.get("ausschuss_mat_teil")) \
        + _n(z.get("lagerzins_teil"))
    if rechnen.beigestellt(p):
        return _b("Material", kosten, STAMMDATEN, SICHER, "Kundenmaterial")
    if not rechnen._leer(p.get("preis_m")):
        return _b("Material", kosten, HAND, SICHER, "Materialpreis von Hand")
    try:
        text = rechnen.preis_herkunft(p, kopf, k, tabellen) or ""
    except (KeyError, TypeError, ValueError, AttributeError):
        text = ""
    if not text or "kein Preis" in text:
        return _b("Material", kosten, GESCHAETZT, UNSICHER, text or "Herkunft des Preises unbekannt")
    if "Tonnenpreis" in text or "Achtung" in text or "ohne Datum" in text:
        return _b("Material", kosten, STAMMDATEN, PRUEFEN, text)
    return _b("Material", kosten, STAMMDATEN, SICHER, text)


def _laser(z, p):
    """Laser und Gas; Leerwege und Drehen aus der Maschinendynamik (Richtwerte der Beschleunigung) als eigener,
    unsicherer Anteil."""
    kosten = _n(z.get("laser_teil")) - _n(z.get("gewinde_teil"))       # laser_teil enthält Gas und Gewinde
    geo = "Geometrie aus STEP" if p.get("step_merkmale") else "Geometrie von Hand"
    if not rechnen._leer(p.get("zeit_manuell")):
        return [_b("Laser", kosten, HAND, SICHER, "Schneidzeit von Hand")]
    stufe = SD_STUFE.get(z.get("sd_sicherheit") or "", PRUEFEN)
    quelle = STEP if p.get("step_merkmale") and stufe == SICHER else STAMMDATEN
    grund = "; ".join(x for x in (z.get("sd_herkunft") or "Schneiddaten", geo) if x)
    if z.get("zeit_dynamik") != "ja":
        return [_b("Laser", kosten, quelle, stufe, grund)]
    brutto = _n(z.get("laser_brutto"))
    dyn = _n(z.get("zeit_anfahren")) + _n(z.get("zeit_drehen"))
    anteil = min(1.0, dyn / brutto) if brutto > 0 else 0.0
    return [_b("Laser", kosten * (1 - anteil), quelle, stufe, grund),
            _b("Laser: Leerwege/Drehen (Dynamik)", kosten * anteil, RICHTWERT, UNSICHER,
               "Bewegungszeit aus der Maschinendynamik gerechnet, nicht gemessen")]


def bausteine(z, p, kopf, k, tabellen):
    """Bausteine einer Kalkulationszeile z (rechnen.kalkulation) der Position p: [dict(baustein, kosten, eur,
    anteil, quelle, sicherheit, grund)], Summe eur = Preis je Teil."""
    if z is None:
        return []
    out = []
    zukauf = _n(z.get("zukauf_teil"))
    if not rechnen.kein_laserteil(p):
        out.append(_material(z, p, kopf, k, tabellen))
        out += _laser(z, p)
        out.append(_b("Rüsten", _n(z.get("ruesten_teil")), STAMMDATEN, SICHER, "Rüstzeiten der Maschine"))
        out.append(_b("Arbeitsschritte", _n(z.get("arbeit_teil")), STAMMDATEN, SICHER))
        out.append(_b("Qualität", _n(z.get("qualitaet_teil")), STAMMDATEN, SICHER))
        out.append(_b("Handling", _n(z.get("handling_teil")), STAMMDATEN, SICHER))
    out.append(_b("Gewinde/Senken (€/Stück)", _n(z.get("gewinde_teil")), STAMMDATEN, SICHER))
    out.append(_b("Zusatzarbeiten", _n(z.get("zusatz_teil")), STAMMDATEN, SICHER, "Stammdaten Zusatzarbeiten"))
    if zukauf:
        fehlt = int(_n(z.get("zukauf_fehlt")))
        out.append(_b("Zukauf", zukauf, STAMMDATEN, UNSICHER if fehlt else SICHER,
                      f"{fehlt} Zukaufteil(e) ohne Einkaufspreis" if fehlt else "Einkaufspreise"))
    bg = _n(z.get("bg_eigen_teil")) + _n(z.get("bg_fremd_teil"))
    if bg:
        out.append(_b("Schweißen/Baugruppe", bg, RICHTWERT, PRUEFEN, "Vorkalkulation Schweißen (Kennwerte)"))
    rest = _n(z.get("pauschalen_teil")) + _n(z.get("fracht_teil"))
    out.append(_b("Übriges (Programmierung, Pauschalen, Fracht)", rest, STAMMDATEN, SICHER))
    out = [b for b in out if abs(b["kosten"]) > 1e-12]
    preis = _n(z.get("preis_teil"))
    summe = sum(b["kosten"] for b in out)
    if not out or abs(summe) < 1e-12:
        return [dict(_b("Preis", preis, HAND if preis else GESCHAETZT, SICHER if preis else UNSICHER), eur=preis,
                     anteil=1.0)] if preis else []
    f = preis / summe
    for b in out:
        b["eur"] = b["kosten"] * f
        b["anteil"] = b["kosten"] / summe
    return out


def uebersicht(kopf, positionen, zeilen, k, tabellen):
    """Übersicht des Angebots: dict(gesamt, je_sicherheit {Sicherheit: €}, je_quelle {Quelle: €}, unsicher_eur,
    unsicher_pct, pruefen_eur, pruefen_pct, positionen [dict(pos, preis, bausteine)]). Beträge je Position
    (Preis je Teil × Stück)."""
    ges = 0.0
    je_s = {s: 0.0 for s in SICHERHEITEN}
    je_q = {q: 0.0 for q in QUELLEN}
    pos = []
    for i, z in enumerate(zeilen or ()):
        if z is None or i >= len(positionen):
            continue
        p = positionen[i]
        c = _n(z.get("stueck")) or _n(p.get("stueck"))
        bs = bausteine(z, p, kopf, k, tabellen)
        for b in bs:
            b["eur_position"] = b["eur"] * c
            je_s[b["sicherheit"]] += b["eur_position"]
            je_q[b["quelle"]] += b["eur_position"]
        preis = _n(z.get("preis_teil")) * c
        ges += preis
        pos.append(dict(pos=p.get("pos"), preis=preis, bausteine=bs))
    pct = (lambda e: 100 * e / ges if ges else 0.0)
    return dict(gesamt=ges, je_sicherheit=je_s, je_quelle=je_q, unsicher_eur=je_s[UNSICHER],
                unsicher_pct=pct(je_s[UNSICHER]), pruefen_eur=je_s[PRUEFEN], pruefen_pct=pct(je_s[PRUEFEN]),
                positionen=pos)


def text(u):
    """Eine Zeile für Übersicht und Check."""
    z = rechnen.zahl
    return (f"Sicher {z(100 - u['unsicher_pct'] - u['pruefen_pct'], 1)} %, prüfen {z(u['pruefen_eur'])} € "
            f"({z(u['pruefen_pct'], 1)} %), unsicher {z(u['unsicher_eur'])} € ({z(u['unsicher_pct'], 1)} %) des "
            f"Preises {z(u['gesamt'])} €")


def gruende(u, sicherheit=UNSICHER, n=3):
    """Die größten Bausteine einer Sicherheit: [(Position, Baustein, €, Grund)]."""
    liste = [(p["pos"], b["baustein"], b["eur_position"], b["grund"]) for p in u["positionen"] for b in p["bausteine"]
             if b["sicherheit"] == sicherheit]
    return sorted(liste, key=lambda x: -x[2])[:n]


GRENZE_ZEIGEN = 0.005       # unter 0,5 % des Preises zählt ein Anteil nicht für die Stufe der Position


def position_stufe(bs):
    """A3 (Plan Phase 3 und 4): Sicherheit einer Position aus ihren Bausteinen: dict(stufe, text, tipp, unsicher,
    pruefen) mit unsicher/pruefen = Anteil am Preis 0 … 1. text "" = alles sicher (Spalte bleibt dann leer), sonst
    z. B. „unsicher 30 %“ bzw. „prüfen 12 %“; tipp = Bausteine mit Quelle, Sicherheit und Grund."""
    ges = sum(abs(_n(b.get("eur"))) for b in bs or ())
    if not bs or ges <= 0:
        return dict(stufe=None, text="", tipp="", unsicher=0.0, pruefen=0.0)
    anteil = {s: sum(abs(_n(b.get("eur"))) for b in bs if b.get("sicherheit") == s) / ges for s in SICHERHEITEN}
    stufe = UNSICHER if anteil[UNSICHER] > GRENZE_ZEIGEN else PRUEFEN if anteil[PRUEFEN] > GRENZE_ZEIGEN else SICHER
    z = rechnen.zahl
    text = "" if stufe == SICHER else f"{stufe} {z(100 * anteil[stufe], 0)} %"
    eur = (lambda w: f"{_n(w):.2f}".replace(".", ","))
    tipp = "\n".join(f"{b['baustein']}: {eur(b.get('eur'))} € – {b['quelle']}, {b['sicherheit']}"
                     + (f" ({b['grund']})" if b.get("grund") else "") for b in bs)
    return dict(stufe=stufe, text=text, tipp=f"Herkunft und Sicherheit je Baustein des Preises je Teil:\n{tipp}",
                unsicher=anteil[UNSICHER], pruefen=anteil[PRUEFEN])


def merkmal_sicherheit(herkunft):
    """A3: Sicherheit eines Merkmals im Teile-Editor aus seiner Herkunft: STEP gemessen und von Hand = sicher,
    von Hand geänderter STEP-Wert und Grundwert (Vorgabe) = prüfen. Unbekannt = prüfen."""
    from .teile_editor import GEAENDERT, MANUELL, STEP as STEP_TE, VORGABE
    return {STEP_TE: SICHER, MANUELL: SICHER, GEAENDERT: PRUEFEN, VORGABE: PRUEFEN}.get(herkunft, PRUEFEN)
