"""Bearbeitungshinweise aus dem Text einer Zeichnung (Patrick 03.11.2026, Freigabe 1a 2a 3a 4a): Gewinde („4x M8“,
„M10 (2x)“), Flowdrill („Flowdrill M8“, „FDS M6“, „Fließloch“), Einnietmuttern („Einnietmutter M6“, „Nietmutter“),
Senkungen („Senkung DIN 74“, „4x gesenkt“) und Blindniete, je mit Anzahl, wenn sie dasteht.

Abgleich mit dem STEP (bohrbild_abgleich): Gewinde und Flowdrill hängen sich als Vorschlag an die passende Bohrung
(Gewinde: Kernloch nach der Gewindetabelle, Flowdrill: Fließloch-Kern nach bohrbild.FLIESSLOCH_KERN); bestätigt wird
wie bisher im Fenster „Bohrungen prüfen“. Fehlt die Anzahl, gilt die Anzahl der passenden Bohrungen (2a). Passt
nichts oder weicht die Anzahl ab, gibt es einen Hinweis. Ohne STEP (Aus PDF-Zeichnung, 3a) werden Flowdrill,
Senken und Einnietmuttern als Zusatzarbeit vorgeschlagen (zusatz_mengen) und Gewinde als Gewinde-Vorschlag.
"""
import re

GEWINDE, FLOWDRILL, NIETMUTTER, SENKUNG, NIET = "Gewinde", "Flowdrill", "Einnietmutter", "Senkung", "Blindniet"
_FLOW = re.compile(r"flow\s*drill|flowdrill|\bfds\b|flie(ß|ss)\s*(loch|bohr|form)|thermisch\s*gebohrt|"
                   r"flie(ß|ss)geform", re.I)
_NIETM = re.compile(r"(einniet|blindniet|niet)\s*-?\s*mutter|rivkle|nietm\b", re.I)
_NIET = re.compile(r"blindniet(?!\s*-?\s*mutter)|\bpopniet|\bgenietet\b", re.I)
_SENK = re.compile(r"senkung|\bgesenkt|\bsenken\b|kegelsenk|din\s*74\b|iso\s*15065|⌵", re.I)
_M = re.compile(r"(?<![A-Za-z0-9])M\s?(\d{1,2})(?:\s*[x×]\s*(\d(?:[.,]\d{1,2})?)(?!\d))?(?![\d.,]*\s*:)", re.I)
_VOR = re.compile(r"(\d{1,3})\s*(?:[x×*]|stk\.?|stück|st\.)\s*$", re.I)
_NACH = re.compile(r"^\s*(?:\(\s*(\d{1,3})\s*[x×]?\s*\)|[x×]\s*(\d{1,3})\b|-\s*(\d{1,3})\s*[x×])", re.I)
_ANZ_ZEILE = re.compile(r"(?<![A-Za-z\d,.Ø])(\d{1,3})\s*(?:[x×](?!\s*\d)|stk\b\.?|stück)", re.I)


def _zeilen(text):
    return [z.strip() for z in str(text or "").replace("\r", "\n").split("\n") if z.strip()]


def _anzahl(zeile, a, e):
    """Anzahl vor („4x M8“, „4 Stk M8“) oder hinter („M8 (4x)“, „M8 x4“) dem Treffer [a:e], sonst die einzige
    Anzahl der Zeile, sonst None."""
    m = _VOR.search(zeile[:a])
    if m:
        return int(m.group(1))
    m = _NACH.match(zeile[e:])
    if m:
        return int(next(g for g in m.groups() if g))
    m = _ANZ_ZEILE.findall(zeile)      # „2 Stk Einnietmutter M5“, „Flowdrill M6 3x“: eine Anzahl in der Zeile
    return int(m[0]) if len(m) == 1 else None


def lesen(text):
    """Hinweise der Zeichnung: [dict(art, gewinde, anzahl, wort)] (anzahl None = nicht angegeben). Je Zeile wird ein
    M-Gewinde nach den Wörtern der Zeile eingeordnet (Flowdrill, Einnietmutter, sonst Gewinde); Senkungen und
    Blindniete ohne Gewinde zählen je Zeile einmal."""
    out = []
    for zeile in _zeilen(text):
        art = FLOWDRILL if _FLOW.search(zeile) else NIETMUTTER if _NIETM.search(zeile) else GEWINDE
        gefunden = False
        for m in _M.finditer(zeile):
            g = f"M{int(m.group(1))}"
            if not 2 <= int(m.group(1)) <= 30:
                continue
            gefunden = True
            out.append(dict(art=art, gewinde=g, anzahl=_anzahl(zeile, m.start(), m.end()), wort=zeile[:80]))
        if gefunden:
            continue
        for muster, art_ in ((_FLOW, FLOWDRILL), (_NIETM, NIETMUTTER), (_SENK, SENKUNG), (_NIET, NIET)):
            m = muster.search(zeile)
            if m:
                out.append(dict(art=art_, gewinde=None, anzahl=_anzahl(zeile, m.start(), m.end()), wort=zeile[:80]))
                break
    return _zusammen(out)


def _zusammen(liste):
    """Gleiche Hinweise (Art, Gewinde) zusammenfassen: Anzahlen addieren, ohne Anzahl bleibt None."""
    out = {}
    for h in liste:
        schl = (h["art"], h["gewinde"])
        if schl not in out:
            out[schl] = dict(h)
        elif h["anzahl"] is not None:
            alt = out[schl]["anzahl"]
            out[schl]["anzahl"] = (alt or 0) + h["anzahl"]
    return list(out.values())


def text(h):
    """„4× M8“, „Flowdrill M8“, „2× Senkung“ …"""
    n = f"{h['anzahl']}× " if h.get("anzahl") else ""
    if h["art"] == GEWINDE:
        return f"{n}{h['gewinde']}"
    return f"{n}{h['art']}" + (f" {h['gewinde']}" if h.get("gewinde") else "")


def _bohrungen(m):
    from .bohrbild import _paare
    return [(d, n) for (d,), n in _paare((m or {}).get("bohrungen"))]


def bohrbild_abgleich(bild, hinweise, m, gewinde, quelle="Zeichnung"):
    """Hinweise der Zeichnung ins Bohrbild (Liste von bohrbild-Zeilen, wird geändert): passende Zeilen bekommen
    zeichnung = Text; Gewinde ohne Zeile, aber mit einer Bohrung in Kernloch-Nähe (±0,3 mm), und Flowdrill auf
    einer gemessenen Bohrung mit Fließloch-Kern (±0,15 mm) werden neue offene Zeilen (Flowdrill mit aus_bohrung:
    erst bestätigt fällt die gelaserte Bohrung weg). Ergebnis: Hinweistexte für Abweichungen."""
    from . import bohrbild
    meldungen = []
    bohr = _bohrungen(m)
    for h in hinweise:
        art, g, soll = h["art"], h.get("gewinde"), h.get("anzahl")
        notiz = f"{quelle}: {h.get('wort') or text(h)}"
        if art == GEWINDE and g:
            zeilen = [z for z in bild if z["art"] == "Bohrung" and z.get("gewinde") == g]
            if not zeilen:
                kerne = [k_ for k_ in (dict(gewinde or ()).get(g), bohrbild.KERN_D1.get(g)) if k_]
                passend = [(d, n) for d, n in bohr if any(abs(d - k_) <= 0.3 for k_ in kerne)]
                for d, n in passend:
                    zeilen.append(dict(art="Bohrung", d=d, anzahl=n, gewinde=g, status=bohrbild.OFFEN))
                bild.extend(zeilen)
        elif art == FLOWDRILL and g:
            zeilen = [z for z in bild if z["art"] == "Fließloch" and z.get("gewinde") == g]
            if not zeilen:
                kern = dict(bohrbild.FLIESSLOCH_KERN).get(g)
                for d, n in [(d, n) for d, n in bohr if kern and abs(d - kern) <= 0.15]:
                    zeilen.append(dict(art="Fließloch", d=d, anzahl=n, gewinde=g, laser=bohrbild.GRAVUR,
                                       status=bohrbild.OFFEN, aus_bohrung=True))
                bild.extend(zeilen)
        elif art == SENKUNG:
            zeilen = [z for z in bild if z["art"] == "Senkung"]
        else:
            continue
        for z in zeilen:
            z["zeichnung"] = notiz
        ist = sum(int(z.get("anzahl") or 0) for z in zeilen)
        if not zeilen:
            meldungen.append(f"{quelle} nennt {text(h)}, im STEP keine passende Bohrung")
        elif soll and soll != ist:
            meldungen.append(f"{quelle} nennt {text(h)}, im STEP {ist} passende Bohrung{'en' if ist != 1 else ''}")
    return meldungen


ZUSATZ_JE_ART = {FLOWDRILL: "Flowdrill", SENKUNG: "Senken", NIETMUTTER: "Einnietmuttern setzen"}


def zusatz_mengen(hinweise, mit_bohrbild=True):
    """{Zusatzarbeit: Anzahl oder None} für Vorschläge aus der Zeichnung. Mit Bohrbild (STEP) nur Einnietmuttern
    (Flowdrill und Senken entstehen dort beim Bestätigen in „Bohrungen prüfen“), ohne (Aus PDF-Zeichnung, 3a) auch
    Flowdrill und Senken."""
    out = {}
    for h in hinweise:
        name = ZUSATZ_JE_ART.get(h["art"])
        if not name or (mit_bohrbild and h["art"] != NIETMUTTER):
            continue
        n = h.get("anzahl")
        out[name] = (out.get(name) or 0) + n if n else out.get(name)
    return out


def gewinde_vorschlag(hinweise):
    """Gewinde der Zeichnung als Text der Spalte Gewinde-Vorschlag („4xM8; 2xM10“), ohne Anzahl 1x."""
    return "; ".join(f"{h.get('anzahl') or 1}x{h['gewinde']}" for h in hinweise
                     if h["art"] == GEWINDE and h.get("gewinde")) or None


def nicht_abgedeckt(hinweise):
    """Hinweise ohne passende Zusatzarbeit (Blindniete): Text für den Bericht, sonst None."""
    t = [text(h) for h in hinweise if h["art"] == NIET]
    return ("Zeichnung nennt " + ", ".join(t) + " – keine Zusatzarbeit dafür, bitte von Hand ergänzen") if t else None
