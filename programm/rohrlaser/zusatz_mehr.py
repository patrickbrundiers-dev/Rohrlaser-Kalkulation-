"""Zusatzarbeiten genauer rechnen (Roadmap Kalkulation Phase 2, Paket 2c; Freigabe Patrick 13.11.2026 „Ganze Phase 2
nach Empfehlung“). Alle Felder sind in den Stammdaten der Zusatzarbeiten optional; leer = wie bisher. Ohne Qt.

CALC-006 Werkzeugkosten je Einheit (Gewindebohrer, Senker, Reibahle …): eigener Bestandteil des Preises je Einheit
         (rechnen.zusatz_preis), getrennt von Zeit und Material.
CALC-007 Lernkurve „ab Stück = Faktor; …“, z. B. „11 = 0,9; 51 = 0,8“: der Betrag je Teil sinkt mit der Stückzahl der
         Position (wirkt damit auch in den Staffeln). Nicht für Gewinde, Senken, Flowdrill und Bohren (nur € je Stück).
CALC-008 Preisstaffel „ab Menge = Preis; …“ nach der Menge der Zusatzarbeit im ganzen Angebot (Charge beim
         Fremdleister: kg, m², m oder Stück aller Positionen zusammen); ein Preis von Hand oder aus einer Regel geht vor.
CALC-016 Fremdleistung: Fracht hin und zurück je Angebot (einmal, auf die Teile umgelegt) und zusätzliche Lieferzeit
         in Arbeitstagen (Hinweis im Angebots-Check).
CALC-019 Sperrgut: ab Teillänge bzw. Teilgewicht ein Zuschlag in % auf die Zusatzarbeit (Ofen-/Kabinenmaß).
CALC-024 Folge- und Hinweisregeln: „Schlägt zusätzlich vor“ (Namen, ; getrennt) erscheint gelb wie ein Vorschlag
         der Erkennung; „Hinweis zusammen mit“ („Name = Text; …“) nennt der Angebots-Check, wenn beide an einer
         Position stehen (z. B. Verzinken + Pulvern = Duplex)."""
import re

EPS = 1e-9


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _leer(v):
    return v is None or v == ""


def ab_tabelle(text):
    """„ab = Wert; …“ -> [(ab, Wert)] aufsteigend; unlesbare Teile entfallen."""
    out = []
    for teil in re.split(r"[;\n]+", str(text or "")):
        m = re.match(r"\s*(?:ab\s*)?([0-9]+(?:[.,][0-9]+)?)\s*(?:=|:|->)\s*([0-9]+(?:[.,][0-9]+)?)\s*$", teil,
                     re.IGNORECASE)
        if m:
            out.append((float(m.group(1).replace(",", ".")), float(m.group(2).replace(",", "."))))
    return sorted(out)


def ab_wert(text, x):
    """Wert der Zeile mit dem größten ab <= x oder None (unter der ersten Zeile bzw. ohne Tabelle)."""
    w = None
    for ab, wert in ab_tabelle(text):
        if x + EPS >= ab:
            w = wert
    return w


# ---------------------------------------------------------------- CALC-007 Lernkurve
def lernfaktor(kz, stueck):
    """Faktor der Lernkurve für die Stückzahl (1.0 ohne Tabelle oder unter der ersten Zeile)."""
    f = ab_wert((kz or {}).get("lernkurve"), _n(stueck))
    return f if f is not None and f > 0 else 1.0


# ---------------------------------------------------------------- CALC-019 Sperrgut
def sperr_faktor(kz, laenge_mm, gewicht_kg):
    """1 + Zuschlag/100, wenn das Teil die Länge [m] bzw. das Gewicht [kg] der Zusatzarbeit erreicht, sonst 1."""
    z = _n((kz or {}).get("sperr_zuschlag"))
    if z <= 0:
        return 1.0
    ab_m, ab_kg = _n((kz or {}).get("sperr_ab_m")), _n((kz or {}).get("sperr_ab_kg"))
    lang = ab_m > 0 and _n(laenge_mm) >= ab_m * 1000 - EPS
    schwer = ab_kg > 0 and gewicht_kg is not None and _n(gewicht_kg) >= ab_kg - EPS
    return 1.0 + z / 100 if lang or schwer else 1.0


# ---------------------------------------------------------------- CALC-008 Preisstaffel im Angebot
def staffeln_anwenden(zus, positionen, aktiv):
    """Preise der Einträge mit Staffel nach der Menge im ganzen Angebot (rechnen._zusatz_umlegen vor dem
    Mindestbetrag): Menge je Teil × Stückzahl aller Positionen; betrag neu = Menge × Staffelpreis (× Lern- und
    Sperrgut-Faktor, mindestens Mindestbetrag je Teil)."""
    summe = {}
    for i in aktiv:
        c = _n(positionen[i].get("stueck"))
        for e in zus[i]:
            if e.get("staffel"):
                summe[e["name"]] = summe.get(e["name"], 0.0) + _n(e.get("menge")) * c
    for i in aktiv:
        for e in zus[i]:
            if not e.get("staffel"):
                continue
            p = ab_wert(e["staffel"], summe.get(e["name"], 0.0))
            if p is None:
                continue
            e["preis"], e["staffel_menge"] = p, summe.get(e["name"], 0.0)
            wert = _n(e.get("menge")) * p * _n(e.get("faktor_mehr") or 1.0)
            if e.get("mindest_teil"):
                wert = max(wert, e["mindest_teil"])
            e["betrag"] = wert
    return zus


# ---------------------------------------------------------------- CALC-016 Fracht der Fremdleistung
def fracht_umlegen(zus, positionen, aktiv):
    """Fracht hin und zurück einmal je Zusatzarbeit und Angebot (höchster Betrag), auf alle Teile mit dieser
    Zusatzarbeit umgelegt: e['fracht_teil'] kommt zu e['teil']."""
    fr, teile = {}, {}
    for i in aktiv:
        c = _n(positionen[i].get("stueck"))
        for e in zus[i]:
            if e.get("fracht") and c:
                fr[e["name"]] = max(fr.get(e["name"], 0.0), e["fracht"])
                teile[e["name"]] = teile.get(e["name"], 0.0) + c
    for i in aktiv:
        c = _n(positionen[i].get("stueck"))
        for e in zus[i]:
            e["fracht_teil"] = fr[e["name"]] / teile[e["name"]] if e.get("fracht") and c and teile.get(e["name"]) \
                else 0.0
            e["teil"] = _n(e.get("teil")) + e["fracht_teil"]
    return zus


def lieferzeit_tage(positionen, tabellen):
    """Größte zusätzliche Lieferzeit [Arbeitstage] der Fremdleistungen im Angebot und deren Name: (Tage, Name)."""
    from .rechnen import zusatz_liste
    katalog = {z.get("name"): z for z in (tabellen or {}).get("zusatzarbeiten") or ()}
    beste = (0, None)
    for p in positionen or ():
        if not _n(p.get("stueck")):
            continue
        for e in zusatz_liste(p):
            st = e.get("stand") if isinstance(e.get("stand"), dict) else None
            kz = katalog.get(e["name"]) or {}
            t = int(_n((st or {}).get("tage_fremd", kz.get("tage_fremd"))))
            if t > beste[0]:
                beste = (t, e["name"])
    return beste


# ---------------------------------------------------------------- CALC-024 Folge- und Hinweisregeln
def namen(text):
    return [x.strip() for x in str(text or "").split(";") if x.strip()]


def folge_vorschlaege(p, tabellen):
    """Namen der Zusatzarbeiten, die eine Zusatzarbeit der Position zusätzlich vorschlägt und die die Position noch
    nicht hat (und nicht abgelehnt sind)."""
    from .rechnen import zusatz_liste
    from .zusatz_regeln import abgelehnt
    katalog = {z.get("name"): z for z in (tabellen or {}).get("zusatzarbeiten") or ()}
    vorhanden = {e["name"] for e in zusatz_liste(p)}
    weg = set(abgelehnt(p) or ())
    out = []
    for n in sorted(vorhanden):
        for f in namen((katalog.get(n) or {}).get("folge")):
            if f in katalog and f not in vorhanden and f not in weg and f not in out \
                    and (katalog[f].get("aktiv") or "ja") != "nein":
                out.append(f)
    return out


def hinweise(p, tabellen):
    """[(Zusatzarbeit, andere, Text)] für Paare an der Position, die „Hinweis zusammen mit“ nennt."""
    from .rechnen import zusatz_liste
    katalog = {z.get("name"): z for z in (tabellen or {}).get("zusatzarbeiten") or ()}
    vorhanden = {e["name"] for e in zusatz_liste(p)}
    out = []
    for n in sorted(vorhanden):
        for teil in re.split(r"[;\n]+", str((katalog.get(n) or {}).get("hinweis_mit") or "")):
            name, _, text = teil.partition("=")
            name = name.strip()
            if name and name in vorhanden and name != n:
                out.append((n, name, text.strip() or f"{n} und {name} zusammen"))
    return out
