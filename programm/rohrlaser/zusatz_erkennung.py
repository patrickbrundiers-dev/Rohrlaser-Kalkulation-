"""Zusatzarbeiten erkennen (Plan „Zusatzarbeiten besser erkennen“, Patrick 03.11.2026, Freigabe 1a 2a 3c 4a 5a 6a).

Jede Zusatzarbeit der Stammdaten kann Erkennungswörter haben (Feld erkennung, mit ; getrennt, z. B. Feuerverzinken:
„verzinkt; fvz; tZn“). Steht eines davon in einer Quelle der Position, schlägt das Programm die Zusatzarbeit vor:
  Bezeichnung, Artikelnummer, STEP-Name (Datei und Körper aus positionen.step_merkmale) – live bei jeder Anzeige,
  Anfrage-Mail und PDF-/DXF-Zeichnung – beim Import gemerkt in positionen.arbeitsgaenge {"erkannt": [...]}.
Das Feld Oberfläche der Position zählt bewusst nicht: es beschreibt die gekaufte Stange (Aufpreis im Materialpreis),
eine Zusatzarbeit daraus würde doppelt rechnen.

Ein Vorschlag kostet nichts (Freigabe 1a): er steht gelb in der Positionsliste („＋ Pulverbeschichten ?“), im Fenster
Zusatzarbeiten und in „Arbeitsgänge vorschlagen …“ und wird erst mit Übernehmen gerechnet (dann Eintrag mit Preisstand
und Herkunft „Erkannt: …“). Abgelehnte merkt sich die Position (wie Regel-Vorschläge, arbeitsgaenge.ablehnen). Schon
gewählte, automatische (Arbeitsgang-Regeln) und inaktive Zusatzarbeiten werden nie vorgeschlagen.

Wörter: Groß-/Kleinschreibung egal, das Wort muss am Wortanfang stehen („verzinkt“ trifft „verzinkte“, nicht
„unverzinkt“; „ohne …“, „nicht …“ und „kein …“ davor zählen als Verneinung), kurze Wörter bis 3 Zeichen
(„fvz“, „RAL“) auch am Wortende. Überdecken sich Treffer, gewinnt das längere Wort („galvanisch verzinkt“ ->
Galvanisch verzinken, nicht zusätzlich Feuerverzinken). Eine RAL-Farbe im selben Text wird als Text übernommen.
"""
import json
import math
import re

from .angebot import ist_baugruppe, ist_zukaufteil

ERKANNT = "Erkannt: "           # Herkunft im Eintrag der Position (quelle) und in der Übersicht
FOLGE = "Folge-Vorschlag"     # CALC-024: Herkunft eines Vorschlags aus „Schlägt zusätzlich vor“
QUELLEN = ("Bezeichnung", "Artikelnummer", "STEP-Name")
RAL = re.compile(r"\bRAL[\s-]*(\d{4})\b", re.I)
_BUCHSTABE = "a-zA-Z0-9äöüÄÖÜß"
VERNEINUNG = re.compile(r"\b(?:ohne|nicht|kein|keine)\s*$", re.I)


def woerter(z):
    """Erkennungswörter einer Zusatzarbeit (Stammdatenzeile), ohne leere."""
    return [w.strip() for w in str((z or {}).get("erkennung") or "").split(";") if w.strip()]


def _muster(wort):
    w = re.escape(wort.strip()).replace(r"\ ", r"\s*")
    ende = f"(?![{_BUCHSTABE}])" if len(wort.strip()) <= 3 else ""
    return re.compile(f"(?<![{_BUCHSTABE}]){w}{ende}", re.I)


_CACHE = {}
_TREFFER = {}       # je Muster-Liste: {Text: Treffer} (Prüfung „Programm langsam“ 04.11.2026: je Neuladen gleich)


def _muster_liste(katalog):
    """[(Name, Wort, Muster)] aller aktiven Zusatzarbeiten mit Erkennungswörtern (zwischengespeichert)."""
    schl = tuple((z.get("name"), z.get("erkennung"), z.get("aktiv")) for z in katalog or ())
    if schl not in _CACHE:
        if len(_CACHE) > 20:
            _CACHE.clear()
            _TREFFER.clear()
        _CACHE[schl] = [(z["name"], w, _muster(w)) for z in katalog or ()
                        if z.get("name") and z.get("aktiv") != "nein" for w in woerter(z)]
    return _CACHE[schl]


def treffer(text, katalog):
    """[(Name, Wort im Text)] der Zusatzarbeiten, deren Erkennungswort im Text steht (je Name einmal, längster
    Treffer gewinnt bei Überdeckung, verneinte zählen nicht)."""
    text = str(text or "")
    if not text.strip():
        return []
    liste = _muster_liste(katalog)
    merker = _TREFFER.setdefault(id(liste), {})
    if text not in merker:
        if len(merker) > 5000:
            merker.clear()
        merker[text] = _treffer(text, liste)
    return list(merker[text])


def _treffer(text, liste):
    funde = []
    for name, _, m in liste:
        for t in m.finditer(text):
            if VERNEINUNG.search(text[max(0, t.start() - 12):t.start()]):
                continue
            funde.append((t.start(), t.end(), name, t.group(0)))
    funde.sort(key=lambda f: (-(f[1] - f[0]), f[0]))
    belegt, out, namen = [], [], set()
    for a, e, name, wort in funde:
        if any(a < e2 and a2 < e for a2, e2 in belegt):
            continue
        belegt.append((a, e))
        if name not in namen:
            namen.add(name)
            out.append((name, wort))
    return out


def ral(text):
    """RAL-Farbe im Text („RAL 7016“) oder None."""
    m = RAL.search(str(text or ""))
    return f"RAL {m.group(1)}" if m else None


def _step_name(p):
    from . import step_pruefung
    d = step_pruefung.lesen(p.get("step_merkmale")) or {}
    return " ".join(str(d.get(n) or "") for n in ("datei", "koerper")).replace("_", " ")


def gemerkt(p):
    """Beim Import gemerkte Erkennungen (Mail, Zeichnung): [{name, quelle, wort, text}]."""
    try:
        d = json.loads(p.get("arbeitsgaenge") or "{}")
    except (TypeError, ValueError):
        return []
    liste = d.get("erkannt") if isinstance(d, dict) else None
    return [e for e in liste or () if isinstance(e, dict) and e.get("name")]


def erkannt(p, katalog):
    """Alle Erkennungen der Position: [{name, quelle, wort, text}] (je Name die erste Quelle; Pulverbeschichten u. a.
    mit der RAL-Farbe als Text, wenn eine im selben Text steht). Zukaufteile (ohne Blech) nicht: „verzinkt“ beschreibt
    dort den gekauften Zustand."""
    if ist_zukaufteil(p) and not p.get("technik"):
        return []
    out = {}
    texte = (("Bezeichnung", p.get("bezeichnung")), ("Artikelnummer", p.get("artikel")), ("STEP-Name", _step_name(p)))
    for quelle, text in texte:
        for name, wort in treffer(text, katalog):
            out.setdefault(name, dict(name=name, quelle=quelle, wort=wort,
                                      text=ral(text) if _mit_farbe(name, katalog) else None))
    for e in gemerkt(p):
        x = out.setdefault(e["name"], dict(name=e["name"], quelle=e.get("quelle") or "Anfrage", wort=e.get("wort"),
                                           text=e.get("text")))
        if isinstance(e.get("menge"), (int, float)) and "menge" not in x:     # Anzahl aus der Zeichnung
            x["menge"] = e["menge"]
    niet = _niet_name(katalog)
    if niet:
        n6, ns = geometrie(p)
        if n6 + ns:
            e = out.setdefault(niet, dict(name=niet, quelle="Geometrie", wort=None, text=None))
            e.update(menge=n6 + ns)
            if e["quelle"] == "Geometrie":
                e["wort"] = _geometrie_text(n6, ns)
    return list(out.values())


def _mit_farbe(name, katalog):
    """Zusatzarbeit, zu der eine RAL-Farbe als Text passt (Beschichten, Lackieren, Pulvern)."""
    z = next((x for x in katalog or () if x.get("name") == name), {})
    text = " ".join(str(z.get(n) or "") for n in ("name", "erkennung", "kategorie")).lower()
    return any(w in text for w in ("pulver", "beschicht", "lack", "ral"))


# ------------------------------------------------------------------ Geometrie: Einnietmuttern (Patrick 03.11.2026)
SECHSKANT_TOL = 0.15        # Seitenlängen höchstens ±15 % vom Mittel, Winkel 120° ± 12°


def _ecken(pts):
    """Eckpunkte eines geschlossenen Umrisses [(x, y)]: doppelte (< 0,3 mm) und gerade weiterlaufende Punkte weg."""
    p = []
    for x, y in pts:
        if not p or math.hypot(x - p[-1][0], y - p[-1][1]) > 0.3:
            p.append((float(x), float(y)))
    if len(p) > 1 and math.hypot(p[0][0] - p[-1][0], p[0][1] - p[-1][1]) <= 0.3:
        p.pop()
    geaendert = True
    while geaendert and len(p) >= 3:
        geaendert = False
        for i in range(len(p)):
            a, b, c = p[i - 1], p[i], p[(i + 1) % len(p)]
            w1, w2 = math.atan2(b[1] - a[1], b[0] - a[0]), math.atan2(c[1] - b[1], c[0] - b[0])
            knick = abs((math.degrees(w2 - w1) + 180) % 360 - 180)
            if knick < 20:
                p.pop(i)
                geaendert = True
                break
    return p


def ist_sechskant(pts):
    """Umriss ist ein (regelmäßiges) Sechseck: 6 Ecken, gleiche Seiten, Winkel 120° (Loch für Einnietmuttern)."""
    e = _ecken(pts)
    if len(e) != 6:
        return False
    seiten = [math.hypot(e[i][0] - e[i - 1][0], e[i][1] - e[i - 1][1]) for i in range(6)]
    m = sum(seiten) / 6
    if m <= 0 or any(abs(x - m) > SECHSKANT_TOL * m for x in seiten):
        return False
    for i in range(6):
        a, b, c = e[i - 1], e[i], e[(i + 1) % 6]
        w1, w2 = math.atan2(b[1] - a[1], b[0] - a[0]), math.atan2(c[1] - b[1], c[0] - b[0])
        if abs(abs((math.degrees(w2 - w1) + 180) % 360 - 180) - 60) > 12:
            return False
    return True


def _zahl(x):
    try:
        return float(str(x).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def _kontur_sechskant(z):
    """Konturzeile (Schneidweg-Rechner, Rohr- oder Blech-Editor, STEP-Import) ist ein Sechskantloch."""
    from . import schneidweg as sw
    art = z.get("art")
    if art == sw.POLYGON:
        try:
            pk = z["punkte"] if isinstance(z.get("punkte"), list) else sw.punkte_roh(z.get("punkte"))
        except (ValueError, KeyError):
            return False
        if any(len(q) > 2 and abs(_zahl(q[2])) > 1e-6 for q in pk):
            return False                    # mit Bögen
        return ist_sechskant([(_zahl(q[0]), _zahl(q[1])) for q in pk])
    if art not in (sw.SONDERKONTUR, sw.SONSTIGE):
        return False
    um = z.get("umriss")
    if isinstance(um, list) and len(um) >= 6:
        try:
            return ist_sechskant([(_zahl(q[0]), _zahl(q[1])) for q in um])
        except (TypeError, IndexError):
            return False
    lg, h = _zahl(z.get("laenge") or z.get("gemessen")), _zahl(z.get("huelle") or z.get("huelle_gemessen"))
    return h > 0 and abs(lg / h - 3.0) <= 0.04      # Umfang 6 s, Hüllmaß über Eck 2 s (Kreis 3,14, Achteck 3,06)


def geometrie(p):
    """(Sechskantlöcher, Senkungen) je Teil aus den Konturen der Position (positionen.technik) und dem Bohrbild
    (Senkungen ohne abgelehnte); (0, 0) ohne Angaben."""
    try:
        t = json.loads(p.get("technik") or "{}")
    except (TypeError, ValueError):
        t = {}
    konturen = [z for z in (t.get("konturen") if isinstance(t, dict) else None) or () if isinstance(z, dict)]
    n6 = sum(max(int(_zahl(z.get("anzahl")) or 1), 1) for z in konturen if _kontur_sechskant(z))
    try:
        bb = json.loads(p.get("bohrbild") or "[]")
    except (TypeError, ValueError):
        bb = []
    senk = [b for b in bb if isinstance(b, dict) and b.get("art") == "Senkung"] if isinstance(bb, list) else []
    if senk:
        ns = sum(int(_zahl(b.get("anzahl"))) for b in senk if b.get("status") != "abgelehnt")
    else:
        ns = sum(max(int(_zahl(z.get("anzahl")) or 1), 1) for z in konturen if z.get("art") == "Senkung")
    return n6, ns


def _niet_name(katalog):
    """Aktive Zusatzarbeit für Einnietmuttern (Name oder Erkennungswort mit „nietmutter“) oder None."""
    for z in katalog or ():
        if z.get("aktiv") != "nein" and z.get("name") and "nietmutter" in (
                str(z.get("name")) + " " + str(z.get("erkennung") or "")).lower().replace("-", ""):
            return z["name"]
    return None


def _geometrie_text(n6, ns):
    teile = ([f"{n6} Sechskantloch" if n6 == 1 else f"{n6} Sechskantlöcher"] if n6 else []) + \
        ([f"{ns} Senkung" if ns == 1 else f"{ns} Senkungen"] if ns else [])
    return ", ".join(teile)


def herkunft(e):
    """Text der Herkunft, z. B. „Erkannt: Bezeichnung „verzinkt““ oder „Erkannt: Geometrie 4 Sechskantlöcher“."""
    if e.get("quelle") == "Geometrie":
        return ERKANNT + "Geometrie " + str(e.get("wort") or "")
    return ERKANNT + str(e.get("quelle") or "") + (f" „{e['wort']}“" if e.get("wort") else "")


def text_merken(arbeitsgaenge, text, katalog, quelle, mengen=None):
    """Neuer Inhalt für positionen.arbeitsgaenge mit den Erkennungen aus text (Anfrage-Mail, Zeichnung) unter
    'erkannt'; unverändert, wenn nichts erkannt wird. mengen = {Zusatzarbeit: Anzahl oder None} aus den
    Bearbeitungshinweisen einer Zeichnung (zeichnung_hinweise.zusatz_mengen): auch ohne Erkennungswort ein
    Vorschlag, mit Anzahl je Teil."""
    namen = {z.get("name") for z in katalog or () if z.get("name") and z.get("aktiv") != "nein"}
    mengen = {n: v for n, v in (mengen or {}).items() if n in namen}
    funde = treffer(text, katalog)
    funde += [(n, "Zeichnung") for n in mengen if n not in {f[0] for f in funde}]
    if not funde:
        return arbeitsgaenge
    try:
        d = json.loads(arbeitsgaenge or "{}")
    except (TypeError, ValueError):
        d = {}
    d = d if isinstance(d, dict) else {}
    liste = [e for e in d.get("erkannt") or () if isinstance(e, dict) and e.get("name")]
    da = {e["name"] for e in liste}
    farbe = ral(text)
    liste += [dict(name=n, quelle=quelle, wort=w, text=farbe if farbe and _mit_farbe(n, katalog) else None,
                   **({"menge": mengen[n]} if mengen.get(n) else {}))
              for n, w in funde if n not in da]
    d["erkannt"] = liste
    return json.dumps(d, ensure_ascii=False)


def offen(p, kopf, k, tabellen):
    """Offene Vorschläge der Position (noch nicht gerechnet, nicht abgelehnt): [{name, herkunft, text, regel}] aus
    den Erkennungswörtern und aus Arbeitsgang-Regeln mit Zuordnung Vorschlag. Ohne Schweißbaugruppen (dort
    Arbeitsgänge im Editor)."""
    from . import rechnen
    from . import zusatz_regeln as zr
    if ist_baugruppe(p):
        return []
    katalog = tabellen.get("zusatzarbeiten") or ()
    aktive = {z.get("name") for z in katalog if z.get("name") and z.get("aktiv") != "nein"}
    vorhanden = {e["name"] for e in rechnen.zusatz_liste(p)}
    regeln = [r for r in tabellen.get("arbeitsgang_regeln") or () if zr.aktiv(r)]
    if regeln and k is not None:
        vorhanden |= {a["name"] for a in zr.automatische(p, kopf, k, tabellen, vorhanden)}
    weg = vorhanden | zr.abgelehnt(p)
    out = {}
    gewinde = tabellen.get("gewinde") or ()
    for r in regeln:
        name = r.get("zusatzarbeit")
        if zr.zuordnung(r) != zr.VORSCHLAG or name in weg or name in out or name not in aktive or k is None:
            continue
        if zr.trifft(r, p, kopf, k, gewinde):
            out[name] = dict(name=name, herkunft=zr.QUELLE + str(r.get("name")), text=None, regel=r.get("name"))
    for e in erkannt(p, katalog):
        if e["name"] in out and e.get("text"):          # Regel-Vorschlag: RAL-Farbe aus dem Text dazu
            out[e["name"]]["text"] = out[e["name"]]["text"] or e["text"]
        if e["name"] in weg or e["name"] in out or e["name"] not in aktive:
            continue
        out[e["name"]] = dict(name=e["name"], herkunft=herkunft(e), text=e.get("text"), regel=None,
                              menge=e.get("menge"))
    # CALC-024 (Roadmap Phase 2): Folge-Vorschläge der Zusatzarbeiten an der Position (z. B. Pulvern ⇒ Strahlen)
    from .zusatz_mehr import folge_vorschlaege
    for name in folge_vorschlaege(p, tabellen):
        if name not in weg and name not in out and name in aktive:
            out[name] = dict(name=name, herkunft=FOLGE, text=None, regel=None)
    return list(out.values())


def kurz(vorschlaege):
    """Anzeige in der Spalte Zusatzarbeiten, z. B. „＋ Pulverbeschichten RAL 7016 ?“, „＋ 4× Einnietmuttern setzen ?“."""
    return "; ".join("＋ " + (f"{v['menge']:g}× " if isinstance(v.get("menge"), (int, float)) and v["menge"] != 1
                             else "") + v["name"] + (f" {v['text']}" if v.get("text") else "") + " ?"
                     for v in vorschlaege)


def eintrag(v, katalog, tabellen, p=None, gewinde=()):
    """Eintrag für positionen.zusatz zu einem übernommenen Vorschlag (mit Preisstand und Herkunft)."""
    from . import rechnen
    from . import zusatz_regeln as zr
    kz = next((z for z in katalog or () if z.get("name") == v["name"]), None)
    if kz is None:
        return None
    regel = next((r for r in tabellen.get("arbeitsgang_regeln") or () if r.get("name") == v.get("regel")), None)
    menge = zr.regel_menge(regel, p or {}, gewinde) if regel else v.get("menge")
    return dict(name=v["name"], menge=menge, preis=None, text=v.get("text"), quelle=v["herkunft"],
                stand=rechnen.zusatz_stand(kz, rechnen.stundensaetze(tabellen)))


def uebernehmen(p, vorschlaege, tabellen):
    """Neuer Inhalt für positionen.zusatz mit den übernommenen Vorschlägen (schon vorhandene bleiben einmal)."""
    from . import rechnen
    liste = rechnen.zusatz_liste(p)
    da = {e["name"] for e in liste}
    katalog = tabellen.get("zusatzarbeiten") or ()
    for v in vorschlaege:
        if v["name"] in da:
            continue
        e = eintrag(v, katalog, tabellen, p, tabellen.get("gewinde") or ())
        if e:
            liste.append(e)
            da.add(v["name"])
    return json.dumps(liste, ensure_ascii=False) if liste else None
