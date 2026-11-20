"""Bauteil-Generator aus Text (Wettbewerbsanalyse 247TailorSteel, Patrick 20.11.2026, Punkt 5 „Parts Builder“).

Eigene Umsetzung ohne Cloud und ohne Sprachmodell: die Beschreibung wird regelbasiert gelesen, jedes erkannte Wort
wird angezeigt, jede Annahme ist gekennzeichnet, nicht zugeordnete Zahlen erscheinen als „nicht verstanden“. Nichts
gelangt ungeprüft in die Kalkulation: der Anwender sieht Teile, 3D und Prüfung und übernimmt erst dann.

Beispiel: „Erstelle einen rechteckigen Rohrrahmen 1000 x 600 mm aus 40 x 40 x 3 mm Stahlrohr mit vier Querstreben und
zwei Befestigungsplatten.“ → Rahmen (rahmen.bauen) + 4 senkrechte Querstreben mit Stößen + 2 Fußplatten (Blech).

Arten
  RAHMEN   Rechteckrahmen oder Gestell (Quader) aus Quadrat-, Rechteck- oder Rundrohr wie der Rahmen-Assistent, dazu
           Querstreben (senkrecht/waagrecht im Rahmen, beim Gestell als Bodenstreben längs der Tiefe, eigenes Profil
           möglich) und Befestigungsplatten (Fuß- oder Kopfplatten, Blech, Bohrungen optional)
  BLECH    einzelnes Blechteil: Platte/Lasche (Rechteck mit Bohrungen), L-Winkel (Kantteil), Flanschring (Ø außen,
           Ø innen, Lochkreis)

Änderungen per Text: aendern(werte, text) liest denselben Text-Wortschatz und überschreibt nur, was der Satz nennt
(„Breite 1200“, „6 Querstreben“, „ohne Platten“, „Profil 50 x 50 x 4“, „stumpf“, „Platten 150 x 150 x 10“ …).
Jede Änderung kommt in den Verlauf.

Grenzen (bewusst, siehe docs/system-audit/WETTBEWERB_247TAILORSTEEL_2011.md): keine Freiformen, keine Rohrbögen,
kein Knickrahmen (dafür Rahmen-Assistent), Streben aus Vierkant an Rundrohr nicht. Geometrie ohne Qt."""
import json
import math
import re

from . import rahmen

RAHMEN, BLECH = "Rohrrahmen", "Blechteil"
PLATTE, WINKEL, FLANSCH = "Platte/Lasche", "L-Winkel", "Flanschring"
SENKRECHT, WAAGRECHT = "senkrecht", "waagrecht"
UNTEN, OBEN = "unten", "oben"
GELAENDER, TISCH = "Geländer", "Tischgestell"
DURCH = "durch"
# Bohrungen in Rohren: Ziel → Teilenamen (None = alle Rohre); Wörter im Text → Ziel
STREBEN_NAMEN = {"Querstrebe", "Querstrebe waagrecht", "Bodenstrebe", "Mittelstrebe", "Zwischenpfosten", "Füllstab"}
ZIELE = {"streben": STREBEN_NAMEN,
         "pfosten": {"Endpfosten", "Zwischenpfosten"},
         "senkrecht": {"Rahmen senkrecht", "Endpfosten", "Bein"},
         "waagrecht": {"Rahmen waagrecht", "Rahmen oben", "Rahmen unten", "Handlauf", "Untergurt", "Querrohr"},
         "oben": {"Rahmen oben", "Handlauf"},
         "unten": {"Rahmen unten", "Untergurt"},
         "alle": None}
ZIEL_TEXT = {"streben": "in den Streben", "pfosten": "in den Pfosten", "senkrecht": "in den senkrechten Rohren",
             "waagrecht": "in den waagrechten Rohren", "oben": "im oberen Rohr", "unten": "im unteren Rohr",
             "alle": "in allen Rohren"}
ZIEL_WORTE = (("streben", r"\w*streb\w*|sprosse\w*|füllst\w*|fuellst\w*|stäbe\w*|staebe\w*|stab\w*|querrohr\w*"),
              ("pfosten", r"\w*pfosten\w*"), ("senkrecht", r"senkrecht\w*|bein\w*|tischbein\w*"),
              ("waagrecht", r"waagrecht\w*|holme\b|zarge\w*"),
              ("oben", r"handlauf\w*|obergurt\w*|holm"), ("unten", r"untergurt\w*"),
              ("alle", r"rahmen\w*|rohre[n]?\b|alle[n]?\b"))
ZAHL = r"\d+(?:[.,]\d+)?"
ZAHLWORTE = {"ein": 1, "eine": 1, "einen": 1, "einer": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "fuenf": 5,
             "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12, "zwoelf": 12,
             "beide": 2, "beiden": 2}
ANZAHL = r"(\d+|" + "|".join(sorted(ZAHLWORTE, key=len, reverse=True)) + r")"
WERKSTOFF_WORTE = r"(S235\w*|S355\w*|E235\w*|E355\w*|1\.4\d{3}|edelstahl|v2a|v4a|aluminium|alu|almgsi\w*|en ?aw-?\d+)"
# Schlüsselwörter: Klasse der folgenden Maßangabe
KLASSEN = (("platte", r"befestigungsplatte\w*|fußplatte\w*|fussplatte\w*|kopfplatte\w*|montageplatte\w*|platte\w*|"
                      r"lasche\w*"),
           ("strebe", r"querstrebe\w*|zwischenstrebe\w*|mittelstrebe\w*|strebe\w*|querrohr\w*|traverse\w*|"
                      r"\w*pfosten|sprosse\w*|füllstab\w*|fuellstab\w*|stäbe|staebe|stab\b"),
           ("rahmen", r"\w*rahmen\w*|gestell\w*|quader\w*|außenma\w*|aussenma\w*|größe|groesse|abmessung\w*|"
                      r"geländer\w*|gelaender\w*|\w*tisch\w*"),
           ("winkel", r"l-winkel\w*|winkel\w*"),
           ("flansch", r"flansch\w*"),
           ("profil", r"aus|profil\w*|\w*rohr\b|\w*rohres|vierkant\w*|rundrohr\w*"))
DIM = re.compile(rf"(Ø\s*)?({ZAHL})\s*(?:mm\s*)?[x×*]\s*(Ø\s*)?({ZAHL})(?:\s*(?:mm\s*)?[x×*]\s*({ZAHL}))?(\s*(?:mm|cm|m)\b)?",
                 re.IGNORECASE)


def _f(s):
    return float(str(s).replace(",", "."))


def _rohr_ziel(nach):
    """Ziel der Bohrungen aus dem Text nach „… Bohrungen Ø 9“: „in den Querstreben“ → 'streben', „im oberen Rohr“ →
    'oben' usw., sonst None (= Bohrungen der Platte bzw. des Blechteils)."""
    m = re.match(r"\s*(?:mm\s*)?(?:je\s+)?(?:in|im|an|am|durch)\s+((?:\w+\s*){1,3})", nach)
    if not m:
        return None
    worte = [x for x in m.group(1).split() if x not in ("den", "die", "der", "dem", "das", "jedem", "jeder", "jede")]
    if any(re.fullmatch(r"oberen?|obere[ms]", x) for x in worte[:2]):
        return "oben"
    if any(re.fullmatch(r"unteren?|untere[ms]", x) for x in worte[:2]):
        return "unten"
    for x in worte[:2]:
        for ziel, muster in ZIEL_WORTE:
            if re.fullmatch(muster, x):
                return ziel
    return None


def _treffer(muster, t, belegt):
    """Wie re.finditer, aber auch überlappend („40 x 3 mit vier Querstreben“: die 3 gehört zum Profil, gezählt wird
    vier) und ohne Zahlen, die schon belegt sind oder ein Ø sind („Bohrungen Ø 9 in den Querstreben“)."""
    rx = re.compile(muster)
    for v in re.finditer(rf"(?=(?:{muster}))", t):
        m = rx.match(t, v.start())
        if not m or any(a <= m.start() < b for a, b in belegt) or \
                re.search(r"(ø|d\s*=|durchmesser|ø\s*\d+[.,]?\d*\s*x)\s*$", t[max(0, m.start() - 14):m.start()]):
            continue
        yield m


def _anzahl(w):
    w = w.lower()
    return int(w) if w.isdigit() else ZAHLWORTE.get(w)


def vorgabe():
    """Leerer Stand: alles None = nicht genannt (bauen setzt dann eine gekennzeichnete Annahme oder meldet)."""
    return dict(art=None, form=None, b=None, h=None, t=None, profil=None, ecken=None, hochkant=None, streben=None,
                streben_richtung=None, streben_profil=None, platten=None, platte=None, platten_lage=None,
                bohrungen=None, werkstoff_wort=None, saetze=None, name=None, blech=None, vorlage=None, pfosten=None,
                pfosten_inkl=None, rohr_bohrungen=None, rohr_seite=None, streben_wort=None)


def _profil(werte, rund):
    """Profil dict(form, a, b, wand) aus 2 (Rundrohr Ø × Wand) oder 3 Maßen; None bei unmöglichen Maßen."""
    if rund or len(werte) == 2:
        if len(werte) < 2 or werte[1] <= 0 or werte[1] * 2 >= werte[0]:
            return None
        return dict(form="Rundrohr", a=werte[0], b=None, wand=werte[1])
    a, b, s = werte
    if s <= 0 or 2 * s >= min(a, b):
        return None
    if abs(a - b) < 1e-6:
        return dict(form="Quadratrohr", a=a, b=a, wand=s)
    return dict(form="Rechteckrohr", a=max(a, b), b=min(a, b), wand=s)


def profil_text(p):
    """'QR 40x40x3' wie die Profil-IDs der Stammdaten."""
    if not p:
        return "–"
    z = lambda v: f"{v:g}".replace(".", ",")      # noqa: E731
    if p["form"] == "Rundrohr":
        return f"RR {z(p['a'])}x{z(p['wand'])}"
    return f"{'QR' if p['form'] == 'Quadratrohr' else 'RE'} {z(p['a'])}x{z(p['b'])}x{z(p['wand'])}"


def _klasse_vor(text, start):
    """Klasse des nächsten Schlüsselworts vor start (gleicher Satzteil); 'aus' direkt nach einer Strebe gilt für die
    Strebe. Ergebnis: Klasse oder None."""
    davor = text[max(0, start - 60):start]
    treffer = []
    for kl, muster in KLASSEN:
        for m in re.finditer(rf"\b(?:{muster})", davor):
            treffer.append((m.end(), m.start(), kl, m.group(0)))
    if not treffer:
        return None
    treffer.sort()
    ende, _, kl, wort = treffer[-1]
    if kl == "profil" and wort == "aus" and len(treffer) > 1 and treffer[-2][2] in ("strebe", "platte", "winkel",
                                                                                      "flansch"):
        return treffer[-2][2]
    return kl


def lesen(text, art=None):
    """Text → (werte {nur erkannte Schlüssel}, erkannt [Texte], unklar [Texte]). Ohne Datenbank. art: Art des
    vorhandenen Stands (Änderung): Maße werden für diese Art gelesen, die Art bleibt."""
    roh = " " + (text or "").replace("\n", " ") + " "
    t = roh.lower()
    w, erkannt, unklar = {}, [], []
    belegt = []                     # Spannen der verarbeiteten Zahlen

    def merken(m, was):
        belegt.append(m.span())
        erkannt.append(was)

    # ---- Art
    if art:
        w["art"] = art
        if art == BLECH:
            w["blech"] = {}
    elif re.search(r"rahmen|gestell|quader|tisch|regal|geländer|gelaender", t):
        w["art"] = RAHMEN
    elif re.search(r"flansch", t):
        w["art"], w["blech"] = BLECH, dict(typ=FLANSCH)
    elif re.search(r"l-winkel|winkel", t) and not re.search(r"\d\s*°", t):
        w["art"], w["blech"] = BLECH, dict(typ=WINKEL)
    elif re.search(r"platte|lasche|blech", t) and not re.search(r"rohr", t):
        w["art"], w["blech"] = BLECH, dict(typ=PLATTE)
    if w.get("art") == RAHMEN and re.search(r"geländer|gelaender", t):
        w["vorlage"] = GELAENDER
        erkannt.append("Vorlage Geländer (Endpfosten, Handlauf, Untergurt, Füllstäbe)")
    elif w.get("art") == RAHMEN and re.search(r"tisch", t):
        w["vorlage"] = TISCH
        erkannt.append("Vorlage Tischgestell (Beine, Zargen, Bodenstreben)")
    if re.search(r"gestell|quader|würfel|wuerfel|tisch|regal|räumlich|raeumlich", t):
        w["form"] = rahmen.QUADER
    elif re.search(r"\w*rahmen|geländer|gelaender", t) and art != RAHMEN:
        w["form"] = rahmen.RAHMEN
    # ---- Maßgruppen a × b (× c)
    for m in DIM.finditer(t):
        werte = [_f(x) for x in (m.group(2), m.group(4), m.group(5)) if x]
        einheit = (m.group(6) or "").strip()
        if einheit in ("m", "cm"):
            werte = [v * (1000 if einheit == "m" else 10) for v in werte]
        rund = bool(m.group(1) or m.group(3)) or bool(re.search(r"rund", t[m.end():m.end() + 25]))
        kl = _klasse_vor(t, m.start())
        nach = t[m.end():m.end() + 30]
        if re.match(r"\s*(mm\s*)?[\w-]*(rohr|profil)", nach) and kl not in ("strebe",):
            kl = "profil"
        if kl is None:
            kl = "profil" if (len(werte) == 3 and werte[2] <= 25 and max(werte[:2]) <= 400) or (rund and len(werte) == 2) \
                else "rahmen"
        if kl == "profil" and (werte[-1] > 25 or max(werte) > 600):
            kl = "rahmen"           # keine Wandstärke: Rahmenmaße direkt nach dem Profilwort („Rundrohr …, 1000 x 600“)
        art = w.get("art")
        if art == BLECH and kl in ("platte", "winkel", "flansch", "rahmen", None, "profil"):
            b = dict(w.get("blech") or {})
            if b.get("typ") == WINKEL and len(werte) == 3:
                b.update(schenkel1=werte[0], schenkel2=werte[1], dicke=werte[2])
                merken(m, f"L-Winkel Schenkel {werte[0]:g} × {werte[1]:g} mm, Dicke {werte[2]:g} mm")
            elif b.get("typ") == FLANSCH and len(werte) >= 2:
                b.update(aussen=max(werte[:2]), innen=min(werte[:2]))
                if len(werte) == 3:
                    b["dicke"] = werte[2]
                merken(m, f"Flanschring Ø {max(werte[:2]):g} / Ø {min(werte[:2]):g} mm")
            elif len(werte) >= 2:
                b.update(laenge=max(werte[:2]), breite=min(werte[:2]))
                if len(werte) == 3:
                    b["dicke"] = werte[2]
                merken(m, f"Platte {max(werte[:2]):g} × {min(werte[:2]):g} mm" +
                       (f", Dicke {werte[2]:g} mm" if len(werte) == 3 else ""))
            w["blech"] = b
            continue
        if kl == "platte":
            if len(werte) == 3:
                w["platte"] = dict(laenge=max(werte[:2]), breite=min(werte[:2]), dicke=werte[2])
                merken(m, f"Platten {max(werte[:2]):g} × {min(werte[:2]):g} × {werte[2]:g} mm")
            elif len(werte) == 2:
                w["platte"] = dict(laenge=max(werte), breite=min(werte), dicke=None)
                merken(m, f"Platten {max(werte):g} × {min(werte):g} mm")
            continue
        if kl in ("profil", "strebe"):
            p = _profil(werte, rund)
            if not p:
                unklar.append(f"Profil {' × '.join(f'{v:g}' for v in werte)}: Wandstärke passt nicht")
                belegt.append(m.span())
                continue
            schluessel = "streben_profil" if kl == "strebe" else "profil"
            if schluessel == "profil" and w.get("profil"):      # zweites Profil im Text: Streben
                schluessel = "streben_profil"
            w[schluessel] = p
            merken(m, ("Streben-Profil " if schluessel == "streben_profil" else "Profil ") + profil_text(p))
            continue
        # Rahmenmaße
        if len(werte) == 3:
            w["b"], w["t"], w["h"] = werte[0], werte[1], werte[2]
            w.setdefault("form", rahmen.QUADER)
            merken(m, f"Gestell B {werte[0]:g} × T {werte[1]:g} × H {werte[2]:g} mm")
        else:
            w["b"], w["h"] = werte[0], werte[1]
            merken(m, f"Außenmaß B {werte[0]:g} × H {werte[1]:g} mm")
    # ---- einzelne Maße: Breite/Höhe/Tiefe/Länge 1200 (auch „auf 1,2 m“)
    for m in re.finditer(rf"\b(breite|höhe|hoehe|tiefe|länge|laenge)\w*\D{{0,14}}?({ZAHL})\s*(mm|cm|m)?\b", t):
        if any(a <= m.start(2) < b for a, b in belegt):
            continue
        v = _f(m.group(2)) * {"m": 1000, "cm": 10}.get(m.group(3) or "", 1)
        name = {"breite": "b", "höhe": "h", "hoehe": "h", "tiefe": "t", "länge": "laenge", "laenge": "laenge"}[m.group(1)]
        if name == "laenge":
            if w.get("art") == BLECH or (w.get("blech") and not w.get("art") == RAHMEN):
                w["blech"] = dict(w.get("blech") or {}, laenge=v) if (w.get("blech") or {}).get("typ") != WINKEL \
                    else dict(w["blech"], kantlaenge=v)
                merken(m, f"Länge {v:g} mm")
                continue
            if (w.get("art") or art) != RAHMEN:
                continue
            name = "b"              # Geländer, Tisch, Rahmen: Länge = Breite (Maß längs)
        w[name] = v
        if name == "t":
            w.setdefault("form", rahmen.QUADER)
        merken(m, f"{ {'b': 'Breite' if m.group(1)[0] == 'b' else 'Länge', 'h': 'Höhe', 't': 'Tiefe'}[name]} {v:g} mm")
    # „2000 lang“, „1100 hoch“, „600 breit“, „500 tief“ (Rohrteile)
    for m in re.finditer(rf"\b({ZAHL})\s*(mm|cm|m)?\s+(lang|breit|hoch|tief)\b", t):
        if any(a <= m.start() < b for a, b in belegt) or (w.get("art") or art) != RAHMEN:
            continue
        v = _f(m.group(1)) * {"m": 1000, "cm": 10}.get(m.group(2) or "", 1)
        name = {"lang": "b", "breit": "b", "hoch": "h", "tief": "t"}[m.group(3)]
        w[name] = v
        merken(m, f"{ {'b': 'Länge', 'h': 'Höhe', 't': 'Tiefe'}[name]} {v:g} mm")
    # ---- Dicke (Platten, Blech): „8 mm dick“, „Dicke 8“, „t = 8“, „8 mm stark“
    for m in re.finditer(rf"(?:dicke|stärke|staerke|blechdicke)\D{{0,8}}?({ZAHL})|({ZAHL})\s*mm\s*(?:dick|stark)", t):
        if any(a <= m.start() < b for a, b in belegt):
            continue
        v = _f(m.group(1) or m.group(2))
        if w.get("art") == BLECH:
            w["blech"] = dict(w.get("blech") or {}, dicke=v)
        else:
            w["platte"] = dict(w.get("platte") or {}, dicke=v)
        merken(m, f"Dicke {v:g} mm")
    # ---- Anzahl Streben / Platten / Bohrungen, „ohne …“
    for m in _treffer(rf"\b{ANZAHL}\s+(?:\w+\s+){{0,2}}?(querstreb|zwischenstreb|mittelstreb|streb|querrohr|"
                         rf"traverse|zwischenpfost|pfost|sprosse|füllstab|fuellstab|füllstäb|fuellstaeb|stäbe|staebe|"
                         rf"stab\b)", t, belegt):
        n = _anzahl(m.group(1))
        if n is None:
            continue
        if m.group(2) == "pfost":           # Pfosten gesamt (mit den Endpfosten) oder zusätzlich – Rückfrage
            w["pfosten"], w["streben"] = n, None
            if re.match(r"\w*\s+(einschließlich|einschliesslich|inklusive|inkl|mit den|samt)\b", t[m.end():]):
                w["pfosten_inkl"] = True
            elif re.match(r"\w*\s+(zusätzlich|zusaetzlich|ohne die|außer|ausser)\b", t[m.end():]):
                w["pfosten"], w["streben"] = None, n
            merken(m, f"{n} Pfosten")
            continue
        w["streben"], w["pfosten"] = n, None
        w["streben_wort"] = "pfosten" if m.group(2) == "zwischenpfost" else "strebe"
        merken(m, f"{n} Querstrebe{'n' if n != 1 else ''}")
    if re.search(r"\bmittelstrebe\b", t) and w.get("streben") is None:
        w["streben"] = 1
        erkannt.append("1 Mittelstrebe")
    for m in _treffer(rf"\b{ANZAHL}\s+(?:\w+\s+){{0,2}}?(befestigungsplatt|fußplatt|fussplatt|kopfplatt|"
                         rf"montageplatt|platte|platten|lasche)", t, belegt):
        n = _anzahl(m.group(1))
        if n is not None and w.get("art") != BLECH:
            w["platten"] = n
            merken(m, f"{n} Befestigungsplatte{'n' if n != 1 else ''}")
    if re.search(r"(ohne|keine)\s+(\w+\s+)?(quer)?streb", t):
        w["streben"] = 0
        erkannt.append("ohne Querstreben")
    if re.search(r"(ohne|keine)\s+(\w+\s+)?(befestigungs|fuß|fuss|kopf)?platte", t):
        w["platten"] = 0
        erkannt.append("ohne Platten")
    for m in _treffer(rf"\b{ANZAHL}\s+(?:\w+\s+)?(bohrung|bohrungen|löcher|loecher|loch)\b"
                         rf"(?:\s*(?:mit\s*)?(?:je\s*)?(?:ø|d\s*=?|durchmesser)?\s*({ZAHL})\s*(?:mm)?)?", t, belegt):
        n = _anzahl(m.group(1))
        if n is None:
            continue
        d = _f(m.group(3)) if m.group(3) else None
        ziel = _rohr_ziel(t[m.end():m.end() + 45])
        if ziel:                            # Bohrungen in Rohren („in den Querstreben“, „im Handlauf“)
            rb = [x for x in (w.get("rohr_bohrungen") or []) if x["ziel"] != ziel]
            w["rohr_bohrungen"] = rb + [dict(anzahl=n, d=d, ziel=ziel)]
            merken(m, f"{n} Bohrung{'en' if n != 1 else ''}" + (f" Ø {d:g} mm" if d else "") + f" {ZIEL_TEXT[ziel]}")
            continue
        w["bohrungen"] = dict(anzahl=n, d=d)
        merken(m, f"{n} Bohrung{'en' if n != 1 else ''}" + (f" Ø {d:g} mm" if d else ""))
    m = re.search(r"(ohne|keine)\s+(bohrung\w*|löcher|loecher)", t)
    if m and _rohr_ziel(t[m.end():m.end() + 45]):
        w["rohr_bohrungen"] = []
        erkannt.append("ohne Bohrungen in den Rohren")
    elif m:
        w["bohrungen"] = dict(anzahl=0, d=None)
        erkannt.append("ohne Bohrungen")
    m = re.search(r"(?:bohrung\w*|löcher|loecher)\b[^.;]{0,70}?\b(?:von|ab)\s+(vorne|oben|unten|hinten)|"
                  r"(?:bohrung\w*|löcher|loecher)\b[^.;]{0,70}?\b(durchgehend|beidseitig|durch beide)", t)
    if m:
        w["rohr_seite"] = m.group(1) or DURCH
        erkannt.append("Rohrbohrungen " + ("durch beide Wände" if w["rohr_seite"] == DURCH else
                                           f"von {w['rohr_seite']}"))
    m = re.search(rf"lochkreis\D{{0,6}}({ZAHL})", t)
    if m:
        w["blech"] = dict(w.get("blech") or {}, lochkreis=_f(m.group(1)))
        merken(m, f"Lochkreis Ø {_f(m.group(1)):g} mm")
    # ---- Richtung, Ecken, Lage, Stück, Werkstoff
    if re.search(r"waagrecht\w*\s+(\w+\s+)?(quer)?streb|streb\w*\s+(\w+\s+)?(waagrecht|horizontal)|horizontal\w*\s+"
                 r"(quer)?streb", t):
        w["streben_richtung"] = WAAGRECHT
        erkannt.append("Streben waagrecht")
    elif re.search(r"senkrecht\w*\s+(\w+\s+)?(quer)?streb|streb\w*\s+(\w+\s+)?(senkrecht|vertikal)|vertikal\w*\s+"
                   r"(quer)?streb", t):
        w["streben_richtung"] = SENKRECHT
        erkannt.append("Streben senkrecht")
    if re.search(r"gehrung|45\s*°", t):
        w["ecken"] = rahmen.GEHRUNG
        erkannt.append("Ecken mit Gehrung")
    elif re.search(r"steck", t):
        w["ecken"] = rahmen.STECKEN
        erkannt.append("Ecken stumpf mit Steckverbindungen")
    elif re.search(r"stumpf", t):
        w["ecken"] = rahmen.STUMPF
        erkannt.append("Ecken stumpf")
    if re.search(r"hochkant", t):
        w["hochkant"] = True
        erkannt.append("Rechteckrohr hochkant")
    if re.search(r"kopfplatt|platte\w*\s+oben|oben\s+(\w+\s+)?platte", t):
        w["platten_lage"] = OBEN
        erkannt.append("Platten oben (Kopfplatten)")
    elif re.search(r"fußplatt|fussplatt|platte\w*\s+unten|unten\s+(\w+\s+)?platte", t):
        w["platten_lage"] = UNTEN
        erkannt.append("Platten unten (Fußplatten)")
    m = re.search(r"\b(\d+)\s*(?:x\s*)?(stück|stk|sätze|saetze|satz|mal)\b", t)
    if m:
        w["saetze"] = int(m.group(1))
        merken(m, f"{m.group(1)} Stück")
    ws = list(re.finditer(rf"\b{WERKSTOFF_WORTE}\b", t, re.IGNORECASE))
    if ws:          # genaueste Angabe zuerst: Werkstoffnummer/Kurzname vor Gruppe (Edelstahl, Alu)
        m = next((x for x in ws if re.match(r"[se]\d|1\.4|en", x.group(1))), ws[0])
        w["werkstoff_wort"] = roh[m.start(1):m.end(1)].strip()
        erkannt.append(f"Werkstoff „{w['werkstoff_wort']}“")
        belegt.extend(x.span() for x in ws)
    # ---- nicht zugeordnete Zahlen
    for m in re.finditer(ZAHL, t):
        if any(a <= m.start() < b for a, b in belegt):
            continue
        if re.match(r"\s*°", t[m.end():m.end() + 2]) or (m.start() and t[m.start() - 1].isalpha()):
            continue            # Winkelangaben und Kürzel wie M12, AW6060
        unklar.append(f"Zahl {m.group(0)} nicht zugeordnet")
    return w, erkannt, unklar


def aendern(werte, text):
    """Änderung per Text: (neue Werte, erkannt, unklar). Überschreibt nur, was der Text nennt; Art und Form bleiben,
    außer der Text nennt sie ausdrücklich."""
    neu, erkannt, unklar = lesen(text, werte.get("art"))
    out = dict(werte)
    for k, v in neu.items():
        if k in ("platte", "blech", "bohrungen") and isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = dict(out[k], **{a: b for a, b in v.items() if b is not None})
        elif k == "rohr_bohrungen" and v and out.get(k):      # je Ziel ersetzen, andere Ziele bleiben
            ziele = {x["ziel"] for x in v}
            out[k] = [x for x in out[k] if x["ziel"] not in ziele] + v
        else:
            out[k] = v
    return out, erkannt, unklar


# ------------------------------------------------------------------ Rückfragen
def _frage(plan, frage, optionen, vorschlag=None):
    """Rückfrage statt stiller Annahme: optionen [(Knopftext, Änderungssatz)], der Satz geht wie eine getippte
    Änderung durch aendern(); vorschlag = Knopftext bzw. Wert, der gerade eingesetzt ist."""
    plan["rueckfragen"].append(dict(frage=frage, optionen=[dict(text=t, satz=z, vorschlag=vorschlag is not None and
                                                                 t.lower() == str(vorschlag).lower())
                                                            for t, z in optionen]))


def _profil_satz(p):
    z = lambda v: f"{v:g}".replace(".", ",")      # noqa: E731
    if p["form"] == "Rundrohr":
        return f"Ø {z(p['a'])} x {z(p['wand'])}"
    return f"{z(p['a'])} x {z(p['b'])} x {z(p['wand'])}"


def naechste_profile(p, profile, n=3):
    """Bis zu n vorhandene Profile gleicher Form, die dem gewünschten am nächsten kommen (Außenmaß vor Wand)."""
    kand = []
    for pid, q in (profile or {}).items():
        if q.get("form") != p["form"] or not q.get("a") or not q.get("wand"):
            continue
        a, b = max(q["a"], q.get("b") or q["a"]), min(q["a"], q.get("b") or q["a"])
        if p["form"] == "Rundrohr":
            b = None
        abst = abs(a - p["a"]) + abs((b or 0) - (p.get("b") or 0) if b is not None else 0) + \
            0.5 * abs(q["wand"] - p["wand"])
        kand.append((abst, str(pid), dict(form=p["form"], a=a, b=b, wand=float(q["wand"]))))
    kand.sort(key=lambda k: (k[0], k[1]))
    out = []
    for _, _, q in kand:
        if q not in out:
            out.append(q)
    return out[:n]


# ------------------------------------------------------------------ Vorlagen, Bohrungen in Rohren
def _namen(erg, w):
    """Teilenamen der Vorlage (Geländer: Endpfosten, Handlauf, Untergurt, Zwischenpfosten/Füllstab; Tisch: Bein,
    Mittelstrebe) bzw. oberes/unteres Rahmenrohr getrennt, wenn Bohrungen nur in einem davon sitzen. Gleiche Rohre
    mit gleichem Namen bleiben ein Teil."""
    vorlage, h = w.get("vorlage"), w["h"] or 0
    ziele = {x["ziel"] for x in (w.get("rohr_bohrungen") or [])}
    trennen = bool(ziele & {"oben", "unten"})

    def name(alt, lage):
        oben = lage[2] > h / 2
        if vorlage == GELAENDER:
            return {"Rahmen senkrecht": "Endpfosten", "Rahmen waagrecht": "Handlauf" if oben else "Untergurt",
                    "Querstrebe": "Zwischenpfosten" if w.get("pfosten") is not None or
                    w.get("streben_wort") == "pfosten" else "Füllstab"}.get(alt, alt)
        if vorlage == TISCH:
            alt = {"Rahmen senkrecht": "Bein",
                   "Bodenstrebe": "Mittelstrebe" if int(w.get("streben") or 0) == 1 else "Bodenstrebe"}.get(alt, alt)
        if trennen and alt == "Rahmen waagrecht":
            return "Rahmen oben" if oben else "Rahmen unten"
        return alt
    teile, schluessel = [], {}
    for t in erg["teile"]:
        for nr, lage in zip(t["koerper"], t["lagen"]):
            nm = name(t["name"], lage)
            key = (nm, t["laenge"], json.dumps(t["eingaben"], sort_keys=True), t.get("profil"))
            if key not in schluessel:
                schluessel[key] = len(teile)
                teile.append(dict(t, name=nm, lagen=[], koerper=[]))
            teile[schluessel[key]]["lagen"].append(lage)
            teile[schluessel[key]]["koerper"].append(nr)
    return dict(erg, teile=teile)


RUND_SEITE = {"oben": "oben (0°)", "vorne": "vorne (90°)", "unten": "unten (180°)", "hinten": "hinten (270°)"}
GEGEN = {"vorne": "hinten", "hinten": "vorne", "oben": "unten", "unten": "oben"}


def _rohr_bohrungen(erg, w, plan):
    """Bohrungen in Rohren als Konturen des Schneidweg-Rechners (art Bohrung, anzahl, d, x = erste Bohrung ab
    Anfang, abstand, seite): gleichmäßig über die Länge (Teilung L / (n + 1)), durch eine Wand (Seite vorne,
    Annahme mit Rückfrage) oder durch beide. Prüft Ø gegen die Rohrseite und den Abstand zu Ende und Nachbar."""
    liste = w.get("rohr_bohrungen") or []
    if not liste:
        return
    seite = w.get("rohr_seite")
    if not seite:
        seite = "vorne"
        plan["annahmen"].append("Rohrbohrungen von vorne durch eine Wand (Seite nicht genannt)")
        _frage(plan, "Von welcher Seite werden die Rohre gebohrt?",
               [("von vorne", "Bohrungen von vorne"), ("von oben", "Bohrungen von oben"),
                ("durch beide Wände", "Bohrungen durchgehend")], "von vorne")
    seiten = ["vorne", "hinten"] if seite == DURCH else [seite]
    for rb in liste:
        n, d = int(rb.get("anzahl") or 0), rb.get("d")
        if not n:
            continue
        if not d:
            d = 9.0
            plan["annahmen"].append(f"Bohrungen {ZIEL_TEXT[rb['ziel']]} Ø 9 mm (Ø nicht genannt)")
        namen = ZIELE[rb["ziel"]]
        treffer = [t for t in erg["teile"] if namen is None or t["name"] in namen]
        if not treffer:
            plan["fehler"].append(f"Bohrungen {ZIEL_TEXT[rb['ziel']]}: solche Rohre gibt es in diesem Bauteil nicht.")
            continue
        for t in treffer:
            p = w["streben_profil"] if t.get("profil") and w.get("streben_profil") else w["profil"]
            rund = p["form"] == "Rundrohr"
            seite_mass = p["a"] if rund else min(p["a"], p.get("b") or p["a"])
            if d > seite_mass - 2 * p["wand"] - 2:
                plan["fehler"].append(f"{t['name']}: Bohrung Ø {d:g} passt nicht in die Rohrseite "
                                      f"({seite_mass:g} mm, Wand {p['wand']:g} mm).")
                continue
            teilung = t["laenge"] / (n + 1)
            if teilung - d < d:
                plan["hinweise"].append(f"{t['name']}: Bohrungen sehr dicht (Steg {teilung - d:.0f} mm < Ø {d:g}).")
            if teilung - d / 2 < seite_mass:
                plan["hinweise"].append(f"{t['name']}: erste Bohrung nur {teilung:.0f} mm vom Ende (Stoß/Naht "
                                        "prüfen).")
            konturen = list(t["eingaben"].get("konturen") or [])
            for s_ in seiten:
                konturen.append(dict(art="Bohrung", anzahl=n, d=float(d), x=round(teilung, 1),
                                     abstand=round(teilung, 1) if n > 1 else 0.0,
                                     seite=RUND_SEITE[s_] if rund else s_, q=0.0))
            t["eingaben"] = dict(t["eingaben"], konturen=konturen)


# ------------------------------------------------------------------ Geometrie
def _lochbild(laenge, breite, d, n):
    """Bohrungen (Mitte x, y ab der Ecke) in einer Platte: 4 in den Ecken, 2 längs in der Mitte, 1 mittig, sonst
    gleichmäßig auf zwei Reihen. Randabstand = max(1,5 × Ø, 15 mm)."""
    if n <= 0:
        return []
    a = max(1.5 * d, 15.0)
    if n == 1:
        return [(laenge / 2, breite / 2)]
    if n == 2:
        return [(a, breite / 2), (laenge - a, breite / 2)]
    if n == 4:
        return [(a, a), (laenge - a, a), (a, breite - a), (laenge - a, breite - a)]
    oben = (n + 1) // 2
    out = []
    for reihe, k in ((a, oben), (breite - a, n - oben)):
        for i in range(k):
            out.append((a + i * (laenge - 2 * a) / max(k - 1, 1), reihe))
    return out


def platte_eingaben(laenge, breite, dicke, werkstoff, bohrungen=None):
    """Eingaben des Blech-Editors für eine Rechteckplatte mit Bohrungen (x/y = Mitte im Zuschnitt)."""
    from . import blech
    from . import schneidweg as sw
    e = dict(werkstoff=werkstoff, dicke=dicke, art=blech.ZUSCHNITT, form=blech.RECHTECK, laenge=laenge,
             breite=breite, eckradius=0.0, konturen=[])
    b = bohrungen or {}
    if b.get("anzahl") and b.get("d"):
        e["konturen"] = [dict(art=sw.BOHRUNG, d=b["d"], anzahl=1, x=round(x, 2), y=round(y, 2))
                         for x, y in _lochbild(laenge, breite, b["d"], int(b["anzahl"]))]
    return e


def _blech_eingaben(b, werkstoff, bohrungen):
    """Eingaben des Blech-Editors für ein einzelnes Blechteil (Platte, L-Winkel, Flanschring)."""
    from . import blech
    from . import schneidweg as sw
    if b["typ"] == WINKEL:      # Bohrungen ohne Lage (Anzahl je Teil zählt für Schneidweg und Einstiche)
        bo = bohrungen or {}
        return dict(werkstoff=werkstoff, dicke=b["dicke"], art=blech.KANTTEIL, kantlaenge=b["kantlaenge"],
                    schenkel=[dict(laenge=b["schenkel1"], winkel=90.0), dict(laenge=b["schenkel2"])],
                    konturen=[dict(art=sw.BOHRUNG, d=bo["d"], anzahl=int(bo["anzahl"]))]
                    if bo.get("anzahl") and bo.get("d") else [])
    if b["typ"] == FLANSCH:
        r, n_pkt = b["aussen"] / 2, 72
        pk = [(round(r + r * math.cos(2 * math.pi * i / n_pkt), 3), round(r + r * math.sin(2 * math.pi * i / n_pkt), 3))
              for i in range(n_pkt)]
        e = dict(werkstoff=werkstoff, dicke=b["dicke"], art=blech.ZUSCHNITT, form=blech.POLYGON,
                 punkte="; ".join(f"{x},{y}" for x, y in pk),
                 konturen=[dict(art=sw.BOHRUNG, d=b["innen"], anzahl=1, x=r, y=r)])
        bo = bohrungen or {}
        if bo.get("anzahl") and bo.get("d"):
            lk = b.get("lochkreis") or (b["aussen"] + b["innen"]) / 2
            for i in range(int(bo["anzahl"])):
                wi = 2 * math.pi * i / int(bo["anzahl"])
                e["konturen"].append(dict(art=sw.BOHRUNG, d=bo["d"], anzahl=1, x=round(r + lk / 2 * math.cos(wi), 2),
                                          y=round(r + lk / 2 * math.sin(wi), 2)))
        return e
    return platte_eingaben(b["laenge"], b["breite"], b["dicke"], werkstoff, bohrungen)


def _koerper(erg):
    """Körper aus rahmen.bauen nach Nummer: {nr: (name, laenge, eingaben, lage)}."""
    out = {}
    for t in erg["teile"]:
        for nr, lage in zip(t["koerper"], t["lagen"]):
            out[nr] = (t["name"], t["laenge"], t["eingaben"], lage)
    return out


def _stoss(koerper, auf, st, ende, punkt):
    la, ls = koerper[auf][3], koerper[st][3]
    z_auf = rahmen._skalar([punkt[i] - la[i] for i in range(3)], la[3:6])
    hin = ls[3:6] if ende == "a" else [-c for c in ls[3:6]]
    w = rahmen._winkel(la, hin)
    return dict(aufnahme=auf, stecker=st, ende=ende, z=round(z_auf, 3), winkel=w,
                seite=f"{int(round(w / 90.0) * 90) % 360}°", achswinkel=90.0)


def streben(erg, form, b, h, t, profil, n, richtung=SENKRECHT, strebenprofil=None, hochkant=False):
    """Querstreben zum Rahmen dazu (gleichmäßig im lichten Maß, stumpf an die Rahmenrohre, Stöße wie aus der STEP).
    Ergebnis: neues erg wie rahmen.bauen (gleiche Rohre ein Teil, Teile mit Schlüssel 'profil' = Strebenprofil oder
    None) und Hinweise. ValueError bei unmöglichen Streben."""
    if not n:
        return erg, []
    sp = strebenprofil or profil
    d, tief, rund = rahmen.masse(profil, hochkant)
    ds, _, rund_s = rahmen.masse(sp)
    if rund and not rund_s:
        raise ValueError("Bauteil-Generator: Streben aus Quadrat- oder Rechteckrohr an Rundrohr gehen nicht "
                         "(Sattel nur Rund an Rund).")
    koerper = _koerper(erg)
    nr = max(koerper)
    neu, stoesse, hinweise = [], list(erg["stoesse"]), []
    ende_rund = {"sattel": round(d, 3)} if rund else {}
    enden = dict(a=dict(ende_rund), b=dict(ende_rund), konturen=[])
    if form == rahmen.QUADER:
        laenge = (t - tief) if rund else (t - 2 * tief)
        lichte = b - 2 * d
        y0 = tief / 2 if rund else tief
        for i in range(1, n + 1):
            x = d + i * lichte / (n + 1)
            lage = rahmen._lage((x, y0, d / 2), (0, 1, 0), rahmen._achsen((0, 1, 0), (0, 0, 1), rund_s, False))
            nr += 1
            koerper[nr] = ("Bodenstrebe", round(laenge, 1), enden, lage)
            neu.append(nr)
            stoesse.append(_stoss(koerper, 1, nr, "a", (x, tief / 2, d / 2)))
            stoesse.append(_stoss(koerper, 5, nr, "b", (x, t - tief / 2, d / 2)))
        abstand = lichte / (n + 1)
    elif richtung == WAAGRECHT:
        laenge = (b - d) if rund else (b - 2 * d)
        lichte = h - 2 * d
        x0 = d / 2 if rund else d
        for i in range(1, n + 1):
            z = d + i * lichte / (n + 1)
            lage = rahmen._lage((x0, 0.0, z), (1, 0, 0), rahmen._achsen((1, 0, 0), (0, 0, 1), rund_s, False))
            nr += 1
            koerper[nr] = ("Querstrebe waagrecht", round(laenge, 1), enden, lage)
            neu.append(nr)
            stoesse.append(_stoss(koerper, 3, nr, "a", (d / 2, 0.0, z)))
            stoesse.append(_stoss(koerper, 4, nr, "b", (b - d / 2, 0.0, z)))
        abstand = lichte / (n + 1)
    else:
        laenge = (h - d) if rund else (h - 2 * d)
        lichte = b - 2 * d
        z0 = d / 2 if rund else d
        for i in range(1, n + 1):
            x = d + i * lichte / (n + 1)
            lage = rahmen._lage((x, 0.0, z0), (0, 0, 1), rahmen._achsen((0, 0, 1), (1, 0, 0), rund_s, False))
            nr += 1
            koerper[nr] = ("Querstrebe", round(laenge, 1), enden, lage)
            neu.append(nr)
            stoesse.append(_stoss(koerper, 1, nr, "a", (x, 0.0, d / 2)))
            stoesse.append(_stoss(koerper, 2, nr, "b", (x, 0.0, h - d / 2)))
        abstand = lichte / (n + 1)
    if laenge <= 10:
        raise ValueError("Bauteil-Generator: Für Querstreben ist kein Platz im Rahmen.")
    if abstand - ds < ds:
        hinweise.append(f"Streben sehr dicht: lichter Abstand {abstand - ds:.0f} mm < Strebenbreite {ds:g} mm "
                        "(Schweißen/Schleifen schwierig).")
    teile, schluessel = [], {}
    for k in sorted(koerper):
        name, lg, e, lage = koerper[k]
        pr = profil_text(sp) if k in neu and strebenprofil else None
        key = (name, lg, json.dumps(e, sort_keys=True), pr)
        if key not in schluessel:
            schluessel[key] = len(teile)
            teile.append(dict(name=name, laenge=lg, eingaben=e, lagen=[], koerper=[], profil=pr))
        teile[schluessel[key]]["lagen"].append(lage)
        teile[schluessel[key]]["koerper"].append(k)
    return dict(erg, teile=teile, stoesse=stoesse), hinweise


def platten_lagen(form, b, h, t, profil, n, platte, lage=UNTEN, hochkant=False):
    """Einbaulagen der Befestigungsplatten [lage] (Plattenebene = XY, Dicke nach unten bzw. oben): Rahmen n Platten
    gleichmäßig unter dem unteren (oben: auf dem oberen) Rohr, außen bündig; Gestell an den Ecken (höchstens 4)."""
    d, tief, _ = rahmen.masse(profil, hochkant)
    lg, br, s = platte["laenge"], platte["breite"], platte["dicke"]
    # Blech-Netz (blech3d): x längs, y = Dicke (Mitte 0), z = Breite → Welt X, −Z, Y
    zc = -s / 2 if lage == UNTEN else h + s / 2
    out = []
    if form == rahmen.QUADER:
        for x0, y0 in ((0, 0), (b - lg, 0), (0, t - br), (b - lg, t - br))[:n]:
            out.append(rahmen._lage((x0, y0, zc), (0, 1, 0), (1, 0, 0)))
        return out
    for i in range(n):
        x0 = (b - lg) / 2 if n == 1 else i * (b - lg) / (n - 1)
        out.append(rahmen._lage((x0, -br / 2, zc), (0, 1, 0), (1, 0, 0)))
    return out


def bauen(werte, profile=None, stange=6000.0):
    """Werte (aus lesen/aendern) → Plan dict(fehler, hinweise, annahmen, art, erg (Rohre wie rahmen.bauen + Streben),
    profil_id, streben_profil_id, fehlende_profile, platten {e, lagen, anzahl}, blech {e}, werte (vollständig)).
    profile: Stammdaten {ID: Zeile}; fehlt ein Profil dort, steht es unter fehlende_profile (anlegen anbieten)."""
    from . import step
    w = dict(vorgabe(), **{k: v for k, v in (werte or {}).items() if v is not None})
    plan = dict(fehler=[], hinweise=[], annahmen=[], rueckfragen=[], art=w["art"], erg=None, profil_id=None,
                streben_profil_id=None, fehlende_profile=[], platten=None, blech=None, werte=w)
    if not w["art"]:
        if w.get("profil") or w.get("b"):
            w["art"] = plan["art"] = RAHMEN
            plan["annahmen"].append("Art: Rohrrahmen (kein Wort wie Rahmen, Gestell, Platte erkannt)")
        else:
            plan["fehler"].append("Was soll entstehen? Z. B. „Rohrrahmen 1000 x 600 aus 40 x 40 x 3“, „Gestell "
                                  "1200 x 800 x 900 aus 40 x 40 x 3“, „Lasche 80 x 40 x 5 mit 2 Bohrungen Ø 9“.")
            return plan
    if w["art"] == BLECH:
        return _bauen_blech(w, plan)
    if w["vorlage"] == GELAENDER:
        w["form"] = rahmen.RAHMEN
        if not w["h"]:
            plan["fehler"].append("Geländer: Höhe fehlt („Höhe 1100“).")
            _frage(plan, "Wie hoch soll das Geländer werden?", [("1000 mm", "Höhe 1000"), ("1100 mm", "Höhe 1100")])
    elif w["vorlage"] == TISCH:
        w["form"] = rahmen.QUADER
    if not w["profil"]:
        plan["fehler"].append("Profil fehlt: z. B. „aus 40 x 40 x 3“ (Quadratrohr), „aus 60 x 40 x 3“ (Rechteckrohr) "
                              "oder „aus Ø 48,3 x 2,6“ (Rundrohr).")
    if (not w["b"] or not w["h"]) and not (w["vorlage"] == GELAENDER and w["b"]):
        plan["fehler"].append("Außenmaße fehlen: z. B. „1000 x 600 mm“ (Breite × Höhe) oder für ein Gestell "
                              "„1200 x 800 x 900“ (Breite × Tiefe × Höhe).")
    if plan["fehler"]:
        return plan
    if not w["form"]:
        w["form"] = rahmen.QUADER if w["t"] else rahmen.RAHMEN
    if w["form"] == rahmen.QUADER and not w["t"]:
        plan["fehler"].append("Gestell: Tiefe fehlt („Tiefe 500“ oder „1200 x 500 x 900“).")
        return plan
    if w["vorlage"] == GELAENDER:
        w["streben_richtung"] = SENKRECHT
        if w["pfosten"] is not None:
            w["streben"] = max(0, int(w["pfosten"]) - 2)
            if not w["pfosten_inkl"]:
                plan["annahmen"].append(f"{w['pfosten']} Pfosten einschließlich der beiden Endpfosten → "
                                        f"{w['streben']} Zwischenpfosten")
                _frage(plan, f"Sind die {w['pfosten']} Pfosten mit den beiden Endpfosten gezählt?",
                       [("ja, gesamt", f"{w['pfosten']} Pfosten einschließlich Endpfosten"),
                        (f"nein, {w['pfosten']} zusätzlich", f"{w['pfosten']} Zwischenpfosten")])
    if not w["ecken"]:
        w["ecken"] = rahmen.GEHRUNG if w["form"] == rahmen.RAHMEN and w["vorlage"] != GELAENDER else rahmen.STUMPF
        plan["annahmen"].append(f"Ecken: {w['ecken']} (nicht genannt)")
        _frage(plan, "Wie sollen die Ecken verbunden werden?",
               [("Gehrung", "Ecken mit Gehrung"), ("stumpf", "Ecken stumpf"),
                ("stumpf mit Steckverbindung", "Ecken mit Steckverbindung")], w["ecken"])
    if w["streben"] and not w["streben_richtung"] and w["form"] == rahmen.RAHMEN:
        w["streben_richtung"] = SENKRECHT
        plan["annahmen"].append("Querstreben senkrecht zwischen oberem und unterem Rohr (nicht genannt)")
        _frage(plan, "Wie sollen die Querstreben laufen?",
               [("senkrecht", "senkrechte Querstreben"), ("waagrecht", "waagrechte Querstreben")], SENKRECHT)
    if w["form"] == rahmen.QUADER and w["streben"]:
        plan["annahmen"].append("Gestell: Querstreben als Bodenstreben längs der Tiefe")
    if not w["saetze"]:
        w["saetze"] = 1
    for schluessel, ziel in (("profil", "profil_id"), ("streben_profil", "streben_profil_id")):
        p = w.get(schluessel)
        if not p:
            continue
        m = dict(profilform=p["form"], abm_a=p["a"], abm_b=p.get("b") or p["a"], wandstaerke=p["wand"])
        pid = step.finde_profil(m, profile or {}) if profile is not None else None
        plan[ziel] = pid
        if profile is not None and not pid:
            plan["fehlende_profile"].append(profil_text(p))
            plan["fehler"].append(f"Profil {profil_text(p)} fehlt in den Stammdaten: „Profil anlegen“ oder ein "
                                  "vorhandenes Profil nennen.")
            nahe = naechste_profile(p, profile)
            if nahe:
                vor = "Streben aus " if schluessel == "streben_profil" else "Profil "
                _frage(plan, f"{profil_text(p)} gibt es nicht. Welches vorhandene Profil?",
                       [(profil_text(q), vor + _profil_satz(q)) for q in nahe])
    ecken = w["ecken"]
    if ecken == rahmen.KNICK:
        plan["fehler"].append("Knickrahmen bitte über den Rahmen-Assistenten anlegen.")
        return plan
    try:
        erg = rahmen.bauen(w["profil"], w["form"], w["b"], w["h"], w["t"], ecken=ecken, hochkant=bool(w["hochkant"]))
        erg, hinw = streben(erg, w["form"], w["b"], w["h"], w["t"], w["profil"], int(w["streben"] or 0),
                            w["streben_richtung"] or SENKRECHT, w.get("streben_profil"), bool(w["hochkant"]))
        plan["hinweise"].extend(hinw)
    except ValueError as x:
        plan["fehler"].append(str(x).replace("Rahmen-Assistent", "Bauteil-Generator"))
        return plan
    erg = _namen(erg, w)
    _rohr_bohrungen(erg, w, plan)
    plan["erg"] = erg
    for t_ in erg["teile"]:
        if t_["laenge"] > (stange or 6000.0):
            plan["fehler"].append(f"{t_['name']} {t_['laenge']:g} mm ist länger als die Stange {stange:g} mm: "
                                  "Maß verkleinern oder Rohr teilen.")
        elif t_["laenge"] < 30:
            plan["hinweise"].append(f"{t_['name']} nur {t_['laenge']:g} mm lang: Spannbarkeit an der Maschine prüfen.")
    # ---- Befestigungsplatten
    n = int(w["platten"] or 0)
    if n:
        d, tief, _ = rahmen.masse(w["profil"], bool(w["hochkant"]))
        pl = dict(w["platte"] or {})
        if not pl.get("laenge"):
            seite = max(100.0, math.ceil((max(d, tief) + 60) / 10) * 10)
            pl.update(laenge=seite, breite=seite)
            plan["annahmen"].append(f"Plattengröße {seite:g} × {seite:g} mm (nicht genannt)")
            dk = pl.get("dicke") or 8
            _frage(plan, "Wie groß sollen die Befestigungsplatten sein?",
                   [(f"{a:g} × {a:g} × {s_:g}", f"Platten {a:g} x {a:g} x {s_:g}".replace(".", ","))
                    for a, s_ in ((seite, dk), (seite + 20, max(dk, 10)), (seite + 50, max(dk, 12)))],
                   f"{seite:g} × {seite:g} × {dk:g}")
        if not pl.get("dicke"):
            pl["dicke"] = 8.0
            plan["annahmen"].append("Plattendicke 8 mm (nicht genannt)")
        lage = w["platten_lage"] or UNTEN
        if not w["platten_lage"]:
            plan["annahmen"].append("Platten unten als Fußplatten (nicht genannt)")
        if w["form"] == rahmen.QUADER and n > 4:
            plan["hinweise"].append(f"Gestell: {n} Platten genannt, an den 4 Ecken sind 4 gesetzt.")
            n = 4
        bo = w["bohrungen"]
        if bo is None:
            bo = dict(anzahl=4, d=13.0)
            plan["annahmen"].append("Je Platte 4 Bohrungen Ø 13 mm für M12 (nicht genannt; „ohne Bohrungen“ "
                                    "entfernt sie)")
            _frage(plan, "Welche Bohrungen bekommen die Platten?",
                   [("4 × Ø 13 (M12)", "4 Bohrungen Ø 13"), ("4 × Ø 11 (M10)", "4 Bohrungen Ø 11"),
                    ("2 × Ø 13", "2 Bohrungen Ø 13"), ("keine", "ohne Bohrungen")], "4 × Ø 13 (M12)")
        elif bo.get("anzahl") and not bo.get("d"):
            bo = dict(bo, d=13.0)
            plan["annahmen"].append("Bohrungen Ø 13 mm (Ø nicht genannt)")
        if pl["breite"] < tief or pl["laenge"] < d:
            plan["fehler"].append(f"Platte {pl['laenge']:g} × {pl['breite']:g} mm ist kleiner als das Rohr "
                                  f"({d:g} × {tief:g} mm).")
        if pl["laenge"] * (n if w["form"] == rahmen.RAHMEN else 2) > w["b"] + 1e-6:
            plan["fehler"].append(f"{n} Platten à {pl['laenge']:g} mm passen nicht in die Breite {w['b']:g} mm.")
        lochbild = _lochbild(pl["laenge"], pl["breite"], bo.get("d") or 0, int(bo.get("anzahl") or 0))
        for x, y in lochbild:
            if min(x, y, pl["laenge"] - x, pl["breite"] - y) < (bo.get("d") or 0):
                plan["hinweise"].append("Bohrung näher als 1 × Ø am Plattenrand.")
                break
        if w["form"] == rahmen.RAHMEN and any(abs(y - pl["breite"] / 2) < tief / 2 + (bo.get("d") or 0) / 2
                                              for _, y in lochbild):
            plan["hinweise"].append("Bohrungen liegen unter dem Rohr: nicht verschraubbar. Platte breiter wählen "
                                    "oder 4 Bohrungen in den Ecken.")
        plan["platten"] = dict(werte=dict(pl, bohrungen=bo), anzahl=n, lage=lage,
                               lagen=platten_lagen(w["form"], w["b"], w["h"], w["t"], w["profil"], n, pl, lage,
                                                   bool(w["hochkant"])))
    return plan


def _bauen_blech(w, plan):
    b = dict(w.get("blech") or {})
    typ = b.get("typ") or PLATTE
    b["typ"] = typ
    if typ == WINKEL:
        if not (b.get("schenkel1") and b.get("schenkel2")):
            plan["fehler"].append("L-Winkel: Schenkel und Dicke fehlen, z. B. „L-Winkel 60 x 40 x 5, Länge 100“.")
            return plan
        if not b.get("kantlaenge"):
            b["kantlaenge"] = b.get("laenge") or 100.0
            if not b.get("laenge"):
                plan["annahmen"].append("Winkellänge 100 mm (nicht genannt)")
    elif typ == FLANSCH:
        if not b.get("aussen"):
            plan["fehler"].append("Flanschring: Durchmesser fehlen, z. B. „Flanschring Ø 200 x Ø 100 x 8 mit 6 "
                                  "Bohrungen Ø 11 auf Lochkreis 160“.")
            return plan
        if b["innen"] >= b["aussen"] - 10:
            plan["fehler"].append("Flanschring: Innen-Ø muss mindestens 10 mm kleiner als außen sein.")
            return plan
    elif not (b.get("laenge") and b.get("breite")):
        plan["fehler"].append("Platte/Lasche: Maße fehlen, z. B. „Lasche 80 x 40 x 5 mit 2 Bohrungen Ø 9“.")
        return plan
    if not b.get("dicke"):
        b["dicke"] = 5.0
        plan["annahmen"].append("Blechdicke 5 mm (nicht genannt)")
    if not w["saetze"]:
        w["saetze"] = 1
    bo = w["bohrungen"]
    if bo and bo.get("anzahl") and not bo.get("d"):
        bo = dict(bo, d=9.0)
        plan["annahmen"].append("Bohrungen Ø 9 mm (Ø nicht genannt)")
    if typ == PLATTE and bo and bo.get("d"):
        for x, y in _lochbild(b["laenge"], b["breite"], bo["d"], int(bo.get("anzahl") or 0)):
            if min(x, y, b["laenge"] - x, b["breite"] - y) < bo["d"]:
                plan["hinweise"].append("Bohrung näher als 1 × Ø am Rand: Platte größer oder Bohrung kleiner.")
                break
    if typ == FLANSCH and bo and bo.get("d"):
        lk = b.get("lochkreis") or (b["aussen"] + b["innen"]) / 2
        if lk / 2 - bo["d"] / 2 < b["innen"] / 2 + 2 or lk / 2 + bo["d"] / 2 > b["aussen"] / 2 - 2:
            plan["fehler"].append(f"Lochkreis Ø {lk:g} mit Bohrungen Ø {bo['d']:g} passt nicht in den Ring.")
    plan["blech"] = dict(werte=b, bohrungen=bo)
    return plan


def blech_e(plan, werkstoff):
    """Eingaben des Blech-Editors für das Blechteil bzw. die Befestigungsplatte des Plans (werkstoff = ID der
    Blech-Werkstoffe) oder None."""
    if plan.get("blech"):
        return _blech_eingaben(plan["blech"]["werte"], werkstoff, plan["blech"].get("bohrungen"))
    if plan.get("platten"):
        p = plan["platten"]["werte"]
        return platte_eingaben(p["laenge"], p["breite"], p["dicke"], werkstoff, p.get("bohrungen"))
    return None


def blech_werkstoff(blech_werkstoffe, kategorie=None, wort=None, rohr=None):
    """Blech-Werkstoff passend zum Rohr: Wort aus dem Text bzw. Güte des Rohrwerkstoffs (rohr, z. B. 'S235JRH' →
    S235JR) im Namen, sonst gleiche Kategorie (Stahl, Edelstahl, Aluminium), sonst der erste."""
    ids = sorted(blech_werkstoffe or {})
    if not wort and rohr and re.match(r"[SE]\d{3}|1\.4\d{3}", rohr.strip(), re.IGNORECASE):
        wort = re.match(r"[SE]\d{3}|1\.4\d{3}", rohr.strip(), re.IGNORECASE).group(0)
    if wort:
        treffer = [i for i in ids if wort.lower().replace(" ", "") in i.lower().replace(" ", "")]
        if treffer:
            return treffer[0]
        kat = {"edelstahl": "Edelstahl", "v2a": "Edelstahl", "v4a": "Edelstahl", "alu": "Aluminium",
               "aluminium": "Aluminium"}.get(wort.lower())
        if wort.startswith("1.4"):
            kat = "Edelstahl"
        kategorie = kat or kategorie
    passend = [i for i in ids if (blech_werkstoffe[i] or {}).get("kategorie") == kategorie] if kategorie else []
    return (passend or ids or [None])[0]


def zusammenfassung(plan):
    """Teileliste als Text ['4 × Querstrebe 520 mm QR 40x40x3', …]."""
    w = plan["werte"]
    out = []
    if plan.get("erg"):
        for t in plan["erg"]["teile"]:
            out.append(f"{len(t['lagen'])} × {t['name']} {t['laenge']:g} mm "
                       f"{t.get('profil') or profil_text(w['profil'])}")
    if plan.get("platten"):
        p = plan["platten"]["werte"]
        bo = p.get("bohrungen") or {}
        out.append(f"{plan['platten']['anzahl']} × Befestigungsplatte {p['laenge']:g} × {p['breite']:g} × "
                   f"{p['dicke']:g} mm" + (f" mit {bo['anzahl']} Bohrungen Ø {bo['d']:g}" if bo.get("anzahl") else ""))
    if plan.get("blech"):
        b, bo = plan["blech"]["werte"], plan["blech"].get("bohrungen") or {}
        if b["typ"] == WINKEL:
            txt = f"L-Winkel {b['schenkel1']:g} × {b['schenkel2']:g} × {b['dicke']:g} mm, Länge {b['kantlaenge']:g} mm"
        elif b["typ"] == FLANSCH:
            txt = f"Flanschring Ø {b['aussen']:g} / Ø {b['innen']:g} × {b['dicke']:g} mm"
        else:
            txt = f"Platte {b['laenge']:g} × {b['breite']:g} × {b['dicke']:g} mm"
        out.append(f"{w.get('saetze') or 1} × {txt}" + (f" mit {bo['anzahl']} Bohrungen Ø {bo['d']:g}"
                                                         if bo.get("anzahl") else ""))
    return out


def name_vorschlag(plan):
    w = plan["werte"]
    if plan.get("blech"):
        return plan["blech"]["werte"]["typ"].split("/")[0]
    if w.get("vorlage") == GELAENDER:
        return f"Geländer {w['b']:g}×{w['h']:g}"
    if w.get("vorlage") == TISCH:
        return f"Tischgestell {w['b']:g}×{w['t']:g}×{w['h']:g}"
    if w.get("form") == rahmen.QUADER:
        return f"Gestell {w['b']:g}×{w['t']:g}×{w['h']:g}"
    return f"Rahmen {w['b']:g}×{w['h']:g}"


def vorschau(plan, platte_e=None):
    """Alle Teile des Plans in Einbaulage als ein Netz (gleiche Teile gleiche Farbe, Platten als Blech) oder None.
    platte_e: Blech-Eingaben der Platte bzw. des Blechteils (blech_e)."""
    from . import blech, blech3d
    from .ansicht3d import baugruppe
    w = plan["werte"]
    netze, farben = [], []
    if plan.get("erg"):
        for nr, t in enumerate(plan["erg"]["teile"]):
            p = w["streben_profil"] if t.get("profil") and w.get("streben_profil") else w["profil"]
            n = rahmen.netz(t, p)
            for lage in n.get("lagen") or ():
                netze.append(dict(n, lage=lage))
                farben.append(nr)
    if platte_e:
        try:
            zs = blech.zuschnitt(platte_e)
        except ValueError:
            zs = None
        n = blech3d.netz(platte_e, zs) if zs else None
        if n:
            lagen = (plan.get("platten") or {}).get("lagen") or [None]
            for lage in lagen:
                netze.append(dict(n, lage=lage) if lage else dict(n))
                farben.append(99)
    if not netze:
        return None
    if len(netze) == 1 and not netze[0].get("lage"):
        return netze[0]
    return baugruppe(netze, (), farben)[0]
