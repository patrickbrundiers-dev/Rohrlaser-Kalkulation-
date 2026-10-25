"""DXF-Zeichnung eines Rohrlaserteils (2D-Ansichten) -> Rohrteil im Rohr-Editor (Plan 3E-12, Patrick 25.10.2026
„b a a a a a a a“). Aus dem Rohr-Editor wird auf Knopfdruck eine STEP-Datei (step_export, 3E-8).

Die Zeichnung zeigt das Rohr in Ansichten (Vorderansicht, Draufsicht, Schnitt, oft eine Isometrie), so wie CAD-
Programme sie ableiten. Erkannt wird:
- Ansichten: Gruppen sichtbarer Kanten (dxf_ansichten.gruppen); die Isometrie fällt weg.
- Maßstab je Ansicht aus der Bemaßung (Maßzahl ÷ Abstand der Maßhilfslinien, auch aufgelöste Maße aus Linien und Text;
  DIMENSION mit Messwert), sonst aus dem Schriftfeld („Maßstab 1:5“). Der Schnitt ist oft größer gezeichnet.
- Schnitt (Querschnitt): Außen- und Innenkante gleich weit auseinander -> Rohrform, Außenmaße und Wand. Ohne Schnitt
  aus dem Text („Quadratrohr 40x40x3“); ohne beides ist es keine Rohrzeichnung (ein schmales Blech bleibt Blech).
- Längsansichten: ihre schmale Seite ist so groß wie das Profil. DIN-Anordnung (Projektionsmethode 1): oben die
  Vorderansicht (Seite vorne), darunter die Draufsicht (Seite oben); Ende A links. Beim Rechteckrohr entscheidet die
  Breite: Breitseite = Draufsicht (die Breitseite liegt im Rohr-Editor oben).
- Enden: die Endkante je Längsansicht (Gerade durch die Kante zwischen 20 % und 80 % der Höhe); ihre Neigung in zwei
  Ansichten ergibt Gehrung bzw. Schrägschnitt zweiachsig mit der längsten Seite.
- Konturen: was in einer Längsansicht zwischen den Endbereichen und abseits der durchgehenden Längskanten sichtbar ist
  (Kreise, geschlossene Züge, zum Ende offene Ausschnitte). Bohrung, Langloch, Rechteck (mit Eckradius) und
  Ausklinkung am Ende werden mit Maßen erkannt, sonst Sonderkontur mit Umriss. Welche Wand: Kanten in der anderen
  Ansicht genau an den Rändern der Kontur in der Wand oben bzw. unten (auch verdeckt); beide = durchgehend; ohne
  Hinweis die Wand, auf die man blickt.
- Texte: Profil, Länge („L = 1000“), Werkstoff, Benennung und Zeichnungsnummer aus dem Schriftfeld.

Verschiedene Zeichnungen (3E-15, Patrick 25.10.2026 „Alle a“: „nicht jede Zeichnung ist gleich“):
- Projektionsmethode aus dem Zeichen bzw. Text (Projektionsmethode 1/3, first/third angle, ISO-E/ISO-A), sonst
  deutsches Schriftfeld = DIN (Methode 1). Methode 1: die obere von zwei übereinander liegenden Längsansichten ist
  die Vorderansicht, die untere die Draufsicht; Methode 3 umgekehrt (Draufsicht oben).
- Senkrecht gezeichnete Rohre: die Zeichnung wird um 90° gedreht (Ende A = oberes Ende).
- Rahmen und Schriftfeld (eine Gruppe, die andere Ansichten umschließt) zählen nicht als Ansicht.
- Bemaßung auch auf Layern anderer CAD-Programme (Inventor, AutoCAD Mechanical AM_5, Dimension …).
- Mehrere Teile auf einem Blatt: Längsansichten gleicher Länge bilden ein Teil; vorgaben['teil'] wählt.
- Unsicher (unsicher = Gründe): Projektionsmethode unbekannt und wichtig, mehrere Teile, Maßstab nur angenommen. Dann
  zeigt der Import das Zuordnungsfenster (dxf_rohr_dialog), vorgaben = {projektion, drehung, teil, rollen {Nr. der
  Ansicht: 'vorne' | 'oben' | 'schnitt' | 'weg'}}.

Nur Rechnung ohne Oberfläche. Ergebnis von erkennen(): dict, siehe dort.
"""
import math
import re

from . import dxf_ansichten as da, dxf_import as di, schneidweg as sw

VERDECKT_WORTE = ("VERDECK", "HIDDEN", "UNSICHT", "AM_3")
MITTEL_WORTE = ("MITTEL", "CENTER", "ACHS", "AM_7")
MASS_WORTE = ("BEMA", "DIM", "MASSE", "MASS_", "MASSLIN", "MASSHILF", "MASZ", "MAßE", "AM_5", "COTE")
PROJEKTION_1 = r"FIRST\s*ANGLE|1ST\s*ANGLE|PROJEKTIONSMETHODE\s*1|ISO[\s-]*E\b|METHODE\s*E\b|EUROP"
PROJEKTION_3 = r"THIRD\s*ANGLE|3RD\s*ANGLE|PROJEKTIONSMETHODE\s*3|ISO[\s-]*A\b|METHODE\s*A\b|AMERIK"
DEUTSCH_WORTE = ("benennung", "werkstoff", "maßstab", "massstab", "zeichnungsnummer", "gezeichnet", "geprüft")
ROLLEN = {"vorne": "Vorderansicht", "oben": "Draufsicht", "schnitt": "Schnitt", "weg": "nicht verwenden"}
PROFIL_WORTE = {"Quadratrohr": "Quadratrohr", "QR": "Quadratrohr", "VKR": "Quadratrohr", "Vierkantrohr": "Quadratrohr",
                "Rechteckrohr": "Rechteckrohr", "RE": "Rechteckrohr", "RR": "Rundrohr", "Rundrohr": "Rundrohr",
                "Rohr": None}
END_PROBEN = (0.2, 0.35, 0.5, 0.65, 0.8)    # Höhen (Anteil), an denen die Endkante abgetastet wird
EBEN_TOL = 0.02         # Endkante gerade, wenn alle Proben so nah an der Geraden liegen (Anteil der Höhe)
LAENGS_ANTEIL = 0.3     # waagrechte Linien, die zusammen so viel der Länge ausmachen, sind Längskanten
WINKEL_STUFE = 0.1      # Gehrungswinkel auf 0,1° runden


def zahl(text):
    """Maßzahl aus einem Bemaßungstext ('1.018,8', '40', '%%c10' -> 10, 'R5' -> None) oder None."""
    t = str(text or "").strip()
    t = re.sub(r"\\[A-Za-z][^;]*;|[{}]", "", t)
    if re.match(r"^\s*R\s*\d", t, re.IGNORECASE):
        return None
    t = re.sub(r"^(%%[cC]|Ø|⌀|\\U\+2205)\s*", "", t).strip()
    m = re.match(r"^(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)(?:\s*(?:mm|°))?$", t)
    if not m:
        return None
    s = m.group(1)
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.match(r"^\d{1,3}(\.\d{3})+$", s):
        s = s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v > 0 else None


def _durchmesser(text):
    return bool(re.match(r"^\s*(%%[cC]|Ø|⌀)", str(text or "")))


# ------------------------------------------------------------------ Linien der Zeichnung
class _Linien:
    """Elemente der DXF (Einheit mm, Maßstab 1) nach Art: sicht/verdeckt/mass [(p, q)], kreise [(c, r)] (sichtbar),
    texte [(layer, p, h, w, text)], dims [dict(wert, a, b)] aus DIMENSION."""

    def __init__(self, roh, namen=None, weg=()):
        self.sicht, self.verdeckt, self.mass, self.kreise, self.texte = [], [], [], [], []
        for el in di.elemente(roh):
            layer = el[1]
            if el[0] == "T":
                self.texte.append(el[1:6])
                continue
            mass = di._hat(layer, MASS_WORTE)
            verdeckt = di._hat(layer, VERDECKT_WORTE) or (el[-1] and not di._hat(layer, MITTEL_WORTE) and not mass)
            art = di.layer_art(layer, namen, weg)
            if not (mass or verdeckt) and (art != "schnitt" or el[-1]):
                continue
            if el[0] == "K":
                if not (mass or verdeckt):
                    self.kreise.append((el[2], el[3]))
                continue
            p, q, b = el[2], el[3], el[4]
            zug = [p] + sw.bogen_punkte(p, q, b) if b else [p, q]
            ziel = self.mass if mass else self.verdeckt if verdeckt else self.sicht
            ziel += [(a, c) for a, c in zip(zug, zug[1:]) if math.dist(a, c) > 1e-9]
        self.dims = _dimensionen(roh)
        self.layer = sorted({str(el[1]).upper() for el in di.elemente(roh)})

    def gedreht(self):
        """Dieselben Linien um 90° gegen den Uhrzeigersinn gedreht (senkrecht gezeichnetes Rohr liegt dann waagrecht,
        das obere Ende links)."""
        def d(p):
            return (-p[1], p[0])
        neu = _Linien.__new__(_Linien)
        neu.sicht = [(d(p), d(q)) for p, q in self.sicht]
        neu.verdeckt = [(d(p), d(q)) for p, q in self.verdeckt]
        neu.mass = [(d(p), d(q)) for p, q in self.mass]
        neu.kreise = [(d(c), r) for c, r in self.kreise]
        neu.texte = [(layer, d(p), h, (w or 0.0) + 90.0, t) for layer, p, h, w, t in self.texte]
        neu.dims = [dict(m, a=d(m["a"]), b=d(m["b"])) for m in self.dims]
        neu.layer = self.layer
        return neu


def _dimensionen(roh):
    """DIMENSION (linear bzw. ausgerichtet) mit Messwert: [dict(wert, a, b)] (Fußpunkte a, b in mm)."""
    out = []
    s = roh["einheit"]
    for typ, d in roh["entitaeten"]:
        if typ != "DIMENSION" or (int(di._wert(d, 70, 0, int) or 0) & 7) not in (0, 1):
            continue
        p1, p2, mess = (di._wert(d, 13), di._wert(d, 23)), (di._wert(d, 14), di._wert(d, 24)), di._wert(d, 42)
        if None in p1 + p2 or not mess:
            continue
        w = math.radians(di._wert(d, 50, 0.0) or 0.0)
        lg = (abs((p2[0] - p1[0]) * math.cos(w) + (p2[1] - p1[1]) * math.sin(w))
              if int(di._wert(d, 70, 0, int) or 0) & 7 == 0 else math.dist(p1, p2))
        if lg > 1e-9:
            out.append(dict(wert=mess * s, laenge=lg * s, a=(p1[0] * s, p1[1] * s), b=(p2[0] * s, p2[1] * s)))
    return out


def masse_aufgeloest(mass, texte):
    """Aufgelöste Bemaßung (Linien + Text auf dem Maß-Layer): je Maßzahl die zwei Maßhilfslinien quer zur
    Schreibrichtung, die den Text einschließen bzw. ihm am nächsten liegen -> [dict(wert, laenge, a, b, durchmesser)].
    a, b = Enden der Hilfslinien zur Ansicht hin (Fußpunkte)."""
    out = []
    for layer, p, h, w, text in texte:
        if not di._hat(layer, MASS_WORTE):
            continue
        v = zahl(text)
        if v is None:
            continue
        h = h or 2.5
        u = (math.cos(math.radians(w)), math.sin(math.radians(w)))
        n = (-u[1], u[0])
        kand = []
        for a, b in mass:
            d = (b[0] - a[0], b[1] - a[1])
            lg = math.hypot(*d)
            if lg < 1.5 * h or abs(d[0] * u[0] + d[1] * u[1]) > 0.05 * lg:
                continue
            ua = a[0] * u[0] + a[1] * u[1]
            na, nb = a[0] * n[0] + a[1] * n[1], b[0] * n[0] + b[1] * n[1]
            nt = p[0] * n[0] + p[1] * n[1]
            if min(na, nb) - 2 * h <= nt <= max(na, nb) + 2 * h:
                # Fußpunkt: das Ende weiter weg vom Text
                fuss = a if abs(na - nt) > abs(nb - nt) else b
                kand.append((ua, fuss))
        kand.sort(key=lambda k: k[0])
        uniq = []
        for k in kand:
            if not uniq or k[0] - uniq[-1][0] > 1e-6:
                uniq.append(k)
        if len(uniq) < 2:
            continue
        ut = p[0] * u[0] + p[1] * u[1] + 0.5 * len(str(text)) * 0.7 * h     # Mitte des Texts etwa
        paare = list(zip(uniq, uniq[1:]))
        drin = [pq for pq in paare if pq[0][0] <= ut <= pq[1][0]]
        a, b = drin[0] if drin else min(paare, key=lambda pq: min(abs(pq[0][0] - ut), abs(pq[1][0] - ut)))
        out.append(dict(wert=v, laenge=b[0] - a[0], a=a[1], b=b[1], durchmesser=_durchmesser(text)))
    return out


def _abstand_bb(p, bb):
    dx = max(bb[0] - p[0], 0.0, p[0] - bb[2])
    dy = max(bb[1] - p[1], 0.0, p[1] - bb[3])
    return math.hypot(dx, dy)


def massstab_je_ansicht(ansichten, masse, vorgabe):
    """Maßstab (Faktor Zeichnung -> echt) je Ansicht aus den Maßen, deren Fußpunkte an ihr liegen; Ansichten ohne
    eigenes Maß: vorgabe. Ergebnis: Liste [(Faktor, Quelle)] parallel zu ansichten."""
    je = [[] for _ in ansichten]
    for m in masse:
        if m.get("durchmesser") or m["laenge"] <= 1e-9:
            continue
        beste = min(((_abstand_bb(m["a"], a.bb) + _abstand_bb(m["b"], a.bb), i) for i, a in enumerate(ansichten)
                     if not a.iso), default=None)
        if beste is None:
            continue
        groesse = max(ansichten[beste[1]].lang, 1.0)
        if beste[0] <= 0.1 * groesse + 5:
            je[beste[1]].append(m["wert"] / m["laenge"])
    out = []
    for werte in je:
        if not werte:
            out.append(vorgabe)
            continue
        # Stimmen je Normmaßstab (auf 1 %); ohne Normmaßstab der Median. Kettenmaße, deren Text weit weg steht,
        # paaren manchmal falsche Hilfslinien: die überstimmt die Mehrheit
        stimmen = {}
        for f in werte:
            best = min(di.MASSSTAEBE, key=lambda s: abs(s - f) / s)
            if abs(best - f) / best < 0.01:
                stimmen[best] = stimmen.get(best, 0) + 1
        if stimmen:
            out.append((max(stimmen, key=lambda s: (stimmen[s], -s)), "Bemaßung"))
            continue
        werte.sort()
        out.append((round(werte[len(werte) // 2], 4), "Bemaßung"))
    return out


# ------------------------------------------------------------------ Querschnitt
def _schnittpunkte(strecken, y=None, x=None):
    """Schnitte der Waagerechten y (bzw. Senkrechten x) mit den Strecken: sortierte Liste der anderen Koordinate."""
    out = []
    for p, q in strecken:
        if y is not None:
            if (p[1] - y) * (q[1] - y) > 0 or p[1] == q[1]:
                continue
            out.append(p[0] + (y - p[1]) * (q[0] - p[0]) / (q[1] - p[1]))
        else:
            if (p[0] - x) * (q[0] - x) > 0 or p[0] == q[0]:
                continue
            out.append(p[1] + (x - p[0]) * (q[1] - p[1]) / (q[0] - p[0]))
    return sorted(out)


def _wand_aus(werte, lo, hi):
    """Aus Schnittpunkten einer Mittellinie: Wand links/rechts (Abstand der ersten zwei bzw. letzten zwei Punkte)
    und leeres Inneres; sonst None."""
    werte = [w for w in werte if lo - 1e-6 <= w <= hi + 1e-6]
    if len(werte) < 4:
        return None
    t1, t2 = werte[1] - werte[0], werte[-1] - werte[-2]
    if t1 <= 1e-6 or t2 <= 1e-6 or abs(t1 - t2) > max(0.02, 0.08 * max(t1, t2)):
        return None
    if any(werte[1] + 1e-3 < w < werte[-2] - 1e-3 for w in werte):      # Linien im Inneren: kein Rohrschnitt
        return None
    return (t1 + t2) / 2


def querschnitt(ansicht, strecken, kreise):
    """Ist die Ansicht ein Rohrschnitt? -> dict(form, B, H, wand) in Zeichnungsmaß (B waagrecht) oder None."""
    if ansicht.iso or ansicht.kurz <= 0 or ansicht.lang > 4 * ansicht.kurz:
        return None
    x0, y0, x1, y1 = ansicht.bb
    st = [strecken[i] for i in ansicht.strecken]
    kr = [kreise[i] for i in ansicht.kreise]
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    if len(kr) >= 2:            # Rundrohr aus zwei Kreisen
        kr = sorted(kr, key=lambda k: -k[1])
        (c1, r1), (c2, r2) = kr[0], kr[1]
        if math.dist(c1, c2) < 0.02 * r1 and 0 < r1 - r2 < 0.5 * r1:
            return dict(form="Rundrohr", B=2 * r1, H=2 * r1, wand=r1 - r2)
    for k in kr:                # Kreise als Strecken (Rundrohr: ein Kreis gezeichnet, der andere als Bögen)
        n = 72
        st += [((k[0][0] + k[1] * math.cos(2 * math.pi * i / n), k[0][1] + k[1] * math.sin(2 * math.pi * i / n)),
                (k[0][0] + k[1] * math.cos(2 * math.pi * (i + 1) / n), k[0][1] + k[1] * math.sin(2 * math.pi * (i + 1) / n)))
               for i in range(n)]
    tw = _wand_aus(_schnittpunkte(st, y=my + 1e-4 * (y1 - y0)), x0, x1)
    th = _wand_aus(_schnittpunkte(st, x=mx + 1e-4 * (x1 - x0)), y0, y1)
    if tw is None or th is None or abs(tw - th) > max(0.02, 0.08 * max(tw, th)):
        return None
    t = (tw + th) / 2
    B, H = x1 - x0, y1 - y0
    if t > 0.25 * min(B, H):
        return None
    # rund: Punkte alle auf zwei Kreisen um die Mitte
    pts = [p for s in st for p in s]
    R = (B + H) / 4
    rund = da.gleich(B, H) and pts and sum(1 for p in pts if min(abs(math.dist(p, (mx, my)) - R),
                                                                 abs(math.dist(p, (mx, my)) - (R - t))) < 0.03 * R) \
        >= 0.9 * len(pts)
    if rund:
        return dict(form="Rundrohr", B=2 * R, H=2 * R, wand=t)
    return dict(form="Quadratrohr" if da.gleich(B, H) else "Rechteckrohr", B=B, H=H, wand=t)


def profil_aus_text(texte):
    """Profil aus Texten wie 'Quadratrohr 40x40x3', 'RR 33,7x2', 'QR 40 x 3', 'Ø42,4x2': dict(form, a, b, wand) oder
    None."""
    for t in texte:
        s = str(t)
        m = re.match(r"^\s*(?:Ø|⌀|%%[cC])\s*(\d+(?:[.,]\d+)?)\s*[xX×*]\s*(\d+(?:[.,]\d+)?)\s*$", s)
        if m:
            a, t_ = (float(g.replace(",", ".")) for g in m.groups())
            if 0 < t_ < a / 2:
                return dict(form="Rundrohr", a=a, b=a, wand=t_)
        m = re.search(r"\b(Quadratrohr|Vierkantrohr|Rechteckrohr|Rundrohr|VKR|QR|RE|RR|Rohr)\b\.?\s*(?:Ø|%%c)?\s*"
                      r"(\d+(?:[.,]\d+)?)\s*[xX×*]\s*(\d+(?:[.,]\d+)?)(?:\s*[xX×*]\s*(\d+(?:[.,]\d+)?))?", s,
                      re.IGNORECASE)
        if not m:
            continue
        wort = next((v for k, v in PROFIL_WORTE.items() if k.upper() == m.group(1).upper()), None)
        z = [float(g.replace(",", ".")) for g in m.groups()[1:] if g]
        if len(z) == 3:
            a, b, t_ = z
            form = wort or ("Quadratrohr" if abs(a - b) < 1e-6 else "Rechteckrohr")
            if form == "Quadratrohr" and abs(a - b) > 1e-6:
                form = "Rechteckrohr"
            return dict(form=form, a=max(a, b), b=min(a, b), wand=t_)
        a, t_ = z
        form = wort or "Rundrohr"
        if form == "Rechteckrohr":
            continue
        return dict(form=form, a=a, b=a, wand=t_)
    return None


def laenge_aus_text(texte):
    for t in texte:
        m = re.search(r"\bL\s*[=:]\s*(\d+(?:[.,]\d+)?)", str(t))
        if m:
            return float(m.group(1).replace(",", "."))
    return None


def schriftfeld(texte, worte):
    """Wert unter einer Feldbeschriftung des Schriftfelds (z. B. 'Benennung'): der nächste größere Text darunter."""
    for layer, p, h, w, t in texte:
        if not any(str(t).strip().lower().startswith(x) for x in worte):
            continue
        beste = None
        for _l, q, h2, _w, t2 in texte:
            dy, dx = p[1] - q[1], abs(q[0] - p[0])
            if 0 < dy <= 8 * max(h, 1.0) and dx <= 5 * max(h, 1.0) and h2 > 1.2 * h and str(t2).strip():
                if beste is None or dy < beste[0]:
                    beste = (dy, str(t2).strip())
        if beste:
            return beste[1]
    return None


def projektion(texte):
    """Projektionsmethode (1 = Europa/DIN, 3 = USA) und Quelle aus den Texten, sonst (None, None)."""
    alles = " ".join(str(t) for t in texte).upper()
    if re.search(PROJEKTION_3, alles):
        return 3, "Zeichnung (Projektionsmethode 3)"
    if re.search(PROJEKTION_1, alles):
        return 1, "Zeichnung (Projektionsmethode 1)"
    if sum(1 for t in texte if str(t).strip().lower().startswith(DEUTSCH_WORTE)) >= 2:
        return 1, "deutsches Schriftfeld (DIN)"
    return None, None


def fingerabdruck(text):
    """Kennung des Zeichnungsstils (Layernamen), unter der sich das Programm die Projektionsmethode merkt."""
    try:
        roh = di.roh_lesen(text)
    except ValueError:
        return ""
    return "|".join(sorted({str(el[1]).upper() for el in di.elemente(roh)}))


def ohne_rahmen(ansichten):
    """Gruppen, die zwei oder mehr andere größere Gruppen umschließen (Blattrahmen, Schriftfeld), fallen weg; Löcher
    in einer Ansicht (kleine eigene Gruppen) zählen nicht."""
    def drin(a, b):
        return a.bb[0] <= b.bb[0] and a.bb[1] <= b.bb[1] and a.bb[2] >= b.bb[2] and a.bb[3] >= b.bb[3]
    return [a for a in ansichten
            if sum(1 for b in ansichten if b is not a and drin(a, b) and b.lang >= 0.15 * a.lang) < 2]


# ------------------------------------------------------------------ Längsansichten
class Laengsansicht:
    """Längsansicht in Zeichnungsmaß: bb, f (Maßstab), seite ('vorne' bzw. 'oben' = Fläche, auf die man blickt),
    strecken (sichtbar), kreise, verdeckt."""

    def __init__(self, ansicht, f, sicht, kreise, verdeckt):
        self.a, self.bb, self.f = ansicht, ansicht.bb, f
        x0, y0, x1, y1 = self.bb
        tol = 0.01 * (y1 - y0) + 1e-6
        def drin(p):
            return x0 - tol <= p[0] <= x1 + tol and y0 - tol <= p[1] <= y1 + tol
        # alles im Umriss, auch was die Kanten nicht berührt (Bohrungen in der Fläche bilden eigene Gruppen)
        self.strecken = [s for s in sicht if drin(s[0]) and drin(s[1])]
        self.kreise = [k for k in kreise if drin(k[0])]
        self.verdeckt = [s for s in verdeckt if drin(s[0]) and drin(s[1])]
        self.seite = None

    @property
    def yc(self):
        return (self.bb[1] + self.bb[3]) / 2

    @property
    def hoehe(self):
        return self.bb[3] - self.bb[1]

    def endkante(self, links):
        """Gerade x = c + s·(y − yc) durch die Endkante (links = Ende A) oder None; (c, s, eben)."""
        ys = [self.bb[1] + f * self.hoehe for f in END_PROBEN]
        xs = []
        for y in ys:
            w = _schnittpunkte(self.strecken, y=y)
            if not w:
                return None
            xs.append(w[0] if links else w[-1])
        n = len(ys)
        my, mx = sum(ys) / n, sum(xs) / n
        syy = sum((y - my) ** 2 for y in ys)
        s = sum((y - my) * (x - mx) for y, x in zip(ys, xs)) / syy if syy else 0.0
        c = mx + s * (self.yc - my)
        eben = all(abs(c + s * (y - self.yc) - x) <= EBEN_TOL * self.hoehe for y, x in zip(ys, xs))
        return c, s, eben


def _waagrecht(p, q, tol):
    return abs(q[1] - p[1]) <= tol * max(abs(q[0] - p[0]), 1e-9)


def _laengskanten(st, laenge):
    """Indizes der Strecken, die zu durchgehenden waagrechten Längskanten gehören (Außenkanten, Radiusübergänge):
    waagrechte Strecken auf gleicher Höhe, die lückenlos aneinander anschließen und zusammen wenigstens
    LAENGS_ANTEIL der Länge lang sind. Kurze Kanten von Ausschnitten auf fast gleicher Höhe bleiben."""
    tol = 1e-4 * laenge + 1e-6
    je = {}
    for i, (p, q) in enumerate(st):
        if _waagrecht(p, q, 0.002):
            je.setdefault(round((p[1] + q[1]) / 2 / tol), []).append(i)
    out = set()
    for idx in je.values():
        idx.sort(key=lambda i: min(st[i][0][0], st[i][1][0]))
        lauf, ende, lg = [], None, 0.0
        for i in idx + [None]:
            if i is not None:
                a, b = sorted((st[i][0][0], st[i][1][0]))
            if i is None or (ende is not None and a > ende + tol):
                if lg >= LAENGS_ANTEIL * laenge:
                    out.update(lauf)
                if i is None:
                    break
                lauf, ende, lg = [], None, 0.0
            lauf.append(i)
            lg += b - max(a, ende) if ende is not None and b > ende else (b - a if ende is None else 0.0)
            ende = b if ende is None else max(ende, b)
    return out


def _cluster(strecken, kreise, abstand):
    if not strecken and not kreise:
        return []
    return da.gruppen(strecken, kreise, abstand)


def _zug_flaeche(pk):
    n = len(pk)
    return sum(pk[i][0] * pk[(i + 1) % n][1] - pk[(i + 1) % n][0] * pk[i][1] for i in range(n)) / 2


def _form(pk, l_, w_):
    """Form eines geschlossenen Zugs (dichte Punkte) mit Hüllmaß l_ (längs) × w_ (quer): (art, maße) oder None."""
    A = abs(_zug_flaeche(pk))
    if A <= 0:
        return None
    kurz, lang = min(l_, w_), max(l_, w_)
    stadion = (lang - kurz) * kurz + math.pi * kurz * kurz / 4
    if lang > kurz * 1.05 and abs(A - stadion) <= 0.02 * A:
        return sw.LANGLOCH, dict(l=lang, b=kurz, quer=w_ > l_)
    rest = l_ * w_ - A
    if rest <= 0.01 * l_ * w_:
        return sw.RECHTECK, dict(b=l_, h=w_, r=0.0)
    r = math.sqrt(max(rest, 0.0) / (4 - math.pi))
    if r < kurz / 2 * 0.98:
        return sw.RECHTECK, dict(b=l_, h=w_, r=r)
    return None


def konturen(lv, zone_a, zone_b):
    """Konturen in der Längsansicht lv: [dict(art, x0, x1, y0, y1, cx, cy, maße, ende, umriss)] in Zeichnungsmaß.
    zone_a/zone_b = x-Bereich der Enden (Schnittflächen), was ganz darin liegt, gehört zum Ende."""
    x0, y0, x1, y1 = lv.bb
    h = lv.hoehe
    tol = max(0.01 * h, 1e-3)
    kanten = _laengskanten(lv.strecken, x1 - x0)
    rest = []
    for i, (p, q) in enumerate(lv.strecken):
        if i in kanten:
            continue
        if max(p[0], q[0]) <= zone_a[1] + tol or min(p[0], q[0]) >= zone_b[0] - tol:
            continue
        rest.append((p, q))
    kreise = [k for k in lv.kreise if zone_a[1] - k[1] < k[0][0] < zone_b[0] + k[1]]
    out = []
    for g in _cluster(rest, kreise, max(0.02 * h, 0.05)):
        gx0, gy0, gx1, gy1 = g.bb
        if max(gx1 - gx0, gy1 - gy0) < 0.03 * h:
            continue
        st = [rest[i] for i in g.strecken]
        kr = [kreise[i] for i in g.kreise]
        k = dict(x0=gx0, x1=gx1, y0=gy0, y1=gy1, cx=(gx0 + gx1) / 2, cy=(gy0 + gy1) / 2, ende=None)
        if kr and len(kr) == 1 and all(math.dist(p, kr[0][0]) <= kr[0][1] * 1.05 for s in st for p in s):
            (cx, cy), r = kr[0]
            k.update(art=sw.BOHRUNG, d=2 * r, cx=cx, cy=cy, x0=cx - r, x1=cx + r, y0=cy - r, y1=cy + r)
            out.append(k)
            continue
        if gx0 <= zone_a[1] + 2 * tol:
            k["ende"] = "a"
        elif gx1 >= zone_b[0] - 2 * tol:
            k["ende"] = "b"
        if k["ende"]:
            # zum Ende offener Ausschnitt: Breite quer, Länge ab der Kante der Fläche, Eckradius aus der Fläche
            # (Rechteck l × b mit zwei runden Ecken: A = l·b − (2 − π/2)·r²), sonst aus der Stirnkante
            l_, b_ = gx1 - gx0, gy1 - gy0
            r = None
            zuege = [z for z in di.verketten([(p, q, 0.0, "") for p, q in st]) if not z.geschlossen]
            if zuege:
                pk = max(zuege, key=lambda z: z.laenge()).dicht()
                offen_x = gx0 if k["ende"] == "a" else gx1        # beide Enden des Zugs an der Kante der Fläche
                if len(pk) > 3 and abs(pk[0][0] - offen_x) <= 2 * tol and abs(pk[-1][0] - offen_x) <= 2 * tol:
                    rest_a = l_ * b_ - abs(_zug_flaeche(pk))
                    if rest_a >= -0.01 * l_ * b_:
                        r = math.sqrt(max(rest_a, 0.0) / (2 - math.pi / 2))
            if r is None:
                stirn = gx1 if k["ende"] == "a" else gx0
                ys = [p[1] for s in st for p in s if abs(p[0] - stirn) <= 2 * tol]
                r = max(0.0, (b_ - ((max(ys) - min(ys)) if ys else b_)) / 2)
            k.update(art=sw.AUSKLINKUNG, l=l_, b=b_, r=min(r, b_ / 2, l_))
            out.append(k)
            continue
        zuege = di.verketten([(p, q, 0.0, "") for p, q in st])
        zu = max((z for z in zuege if z.geschlossen), key=lambda z: abs(z.flaeche), default=None)
        pk = zu.dicht() if zu else None
        ist_kreis = pk and da.gleich(gx1 - gx0, gy1 - gy0) and all(
            abs(math.dist(p, (k["cx"], k["cy"])) - (gx1 - gx0) / 2) <= 0.03 * (gx1 - gx0) for p in pk)
        if ist_kreis:
            k.update(art=sw.BOHRUNG, d=gx1 - gx0)
        elif pk and (f := _form(pk, gx1 - gx0, gy1 - gy0)):
            k.update(art=f[0], **f[1])
        else:
            if pk is None:          # kein geschlossener Zug: Hülle als Umriss (bitte prüfen)
                pk = [(gx0, gy0), (gx1, gy0), (gx1, gy1), (gx0, gy1)]
                k["unsicher"] = True
            k.update(art=sw.SONDERKONTUR, umriss=pk)
        out.append(k)
    return out


def wand_hinweis(k, andere, wand_z):
    """Welche Wand trägt die Kontur k (aus Ansicht A) laut der anderen Längsansicht B? Kanten in B, die an den Rändern
    x0/x1 von k quer durch die obere bzw. untere Wand laufen. -> (oben, unten) als bool. wand_z = Wand in
    Zeichnungsmaß der Ansicht B."""
    if andere is None:
        return False, False
    y0, y1 = andere.bb[1], andere.bb[3]
    tol = max(0.01 * andere.hoehe, 1e-3)
    oben = unten = False
    for p, q in andere.strecken + andere.verdeckt:
        if abs(q[0] - p[0]) > 0.2 * max(abs(q[1] - p[1]), 1e-9):
            continue            # nur Kanten quer zur Achse
        x = (p[0] + q[0]) / 2
        if not any(abs(x - r) <= tol for r in (k["x0"], k["x1"])):
            continue
        ya, yb = min(p[1], q[1]), max(p[1], q[1])
        if yb >= y1 - wand_z - tol and ya >= y1 - wand_z - 2 * tol:
            oben = True
        if ya <= y0 + wand_z + tol and yb <= y0 + wand_z + 2 * tol:
            unten = True
    return oben, unten


# ------------------------------------------------------------------ Gesamt
def _rund(v, stellen=2):
    v = round(v, stellen)
    return 0.0 if v == 0 else v


def gehrung(tu, tv, ende_b, profil):
    """Ende aus den Neigungen dz/du (zu vorne) und dz/dv (nach oben) -> Eingaben des Rohr-Editors (dict)."""
    w = math.degrees(math.atan(math.hypot(tu, tv)))
    if w < 0.2:
        return {}
    du, dv = (tu, tv) if ende_b else (-tu, -tv)      # zur längsten Seite
    richtung = math.degrees(math.atan2(du, dv)) % 360
    form = profil.get("form")
    a_, b_ = float(profil.get("a") or 0), float(profil.get("b") or profil.get("a") or 0)
    breit, schmal = max(a_, b_), min(a_, b_)
    wu, wv = math.degrees(math.atan(abs(tu))), math.degrees(math.atan(abs(tv)))
    stufe = lambda x: round(round(x / WINKEL_STUFE) * WINKEL_STUFE, 1)
    if form == "Rundrohr":
        return dict(winkel=stufe(w))
    if min(wu, wv) < 0.2:
        r = round(richtung / 90) * 90 % 360
        quer = schmal if r % 180 == 0 else breit
        return dict(winkel=stufe(w), richtung=r, achse=sw.ACHSEN[0] if abs(quer - a_) < 1e-6 else sw.ACHSEN[1])
    a_senk = abs(schmal - a_) < 1e-6        # Maß a senkrecht (Quadratrohr): über Höhe = Neigung über v
    wh, wb = (wv, wu) if a_senk else (wu, wv)
    return dict(achse=sw.ACHSE_ZWEI, winkel_h=stufe(wh), winkel_b=stufe(wb), winkel=stufe(w), richtung=round(richtung, 1))


def erkennen(text, dateiname="", namen=None, weg=(), vorgaben=None):
    """DXF-Text einer Rohrzeichnung -> dict(ok, profil (form, a, b, wand), profil_quelle, profil_text, laenge,
    laenge_text, eingaben (Rohr-Editor), werkstoff_text, name, artikel, ansichten [dict(nr, rolle, bb, massstab,
    quelle)], warnungen, hinweise, unsicher (Gründe für das Zuordnungsfenster), rohrartig (Schnitt oder Profiltext),
    projektion, drehung, teile (Anzahl Teile), linien (Strecken für die Vorschau)). ok False: keine Rohrzeichnung
    (warnungen sagt warum). vorgaben: siehe Kopf (Zuordnungsfenster)."""
    vorgaben = dict(vorgaben or {})
    roh = di.roh_lesen(text)
    roh["entitaeten"] = di._polylinien_zusammen(roh["entitaeten"])
    roh["bloecke"] = {n: (b, di._polylinien_zusammen(ents)) for n, (b, ents) in roh["bloecke"].items()}
    li0 = _Linien(roh, namen, weg)
    if vorgaben.get("drehung") is not None:
        return _erkennen(roh, li0.gedreht() if vorgaben["drehung"] else li0, dateiname, vorgaben)
    erg = _erkennen(roh, li0, dateiname, dict(vorgaben, drehung=0))
    if not erg["ok"] and erg.get("senkrecht"):
        erg90 = _erkennen(roh, li0.gedreht(), dateiname, dict(vorgaben, drehung=90))
        if erg90["ok"]:
            return erg90
    return erg


def _erkennen(roh, li, dateiname, vorgaben):
    texte = [t[4] for t in li.texte]
    warn, hinweise, unsicher = [], [], []
    rollen = {int(k): v for k, v in (vorgaben.get("rollen") or {}).items()}
    erg = dict(ok=False, warnungen=warn, hinweise=hinweise, unsicher=unsicher, ansichten=[], profil=None,
               eingaben=None, drehung=vorgaben.get("drehung") or 0, teile=1, rohrartig=False,
               linien=[[round(c, 2) for c in (*p, *q)] for p, q in li.sicht],
               werkstoff_text=schriftfeld(li.texte, ("werkstoff", "material")),
               name=schriftfeld(li.texte, ("benennung", "bezeichnung", "titel")),
               artikel=schriftfeld(li.texte, ("zeichnungsnummer", "zeichnungs-nr", "zeichn.-nr", "artikelnummer",
                                              "artikel-nr", "teilenummer", "sachnummer")),
               laenge_text=laenge_aus_text(texte), profil_text=profil_aus_text([dateiname] + texte))
    ansichten = ohne_rahmen(da.gruppen(li.sicht, li.kreise))
    proj, proj_quelle = (vorgaben["projektion"], "Vorgabe") if vorgaben.get("projektion") in (1, 3) \
        else projektion(texte)
    erg["projektion"] = proj or 1

    def ansichten_liste(rolle_von, f_je):
        return [dict(nr=i, rolle=rolle_von(a), bb=a.bb, massstab=f, quelle=quelle, vorgabe=rollen.get(i))
                for i, (a, (f, quelle)) in enumerate(zip(ansichten, f_je))]
    if not ansichten:
        warn.append("In der DXF sind keine sichtbaren Kanten.")
        return erg
    vorgabe = di.massstab_vorschlag(roh, texte)
    if vorgabe[1] is None:          # Schriftfeld mit Feld „Maßstab“ und dem Wert darunter
        m = re.match(r"^\s*(\d+(?:[.,]\d+)?)\s*:\s*(\d+(?:[.,]\d+)?)\s*$",
                     schriftfeld(li.texte, ("maßstab", "massstab", "maszstab", "scale")) or "")
        if m and float(m.group(1).replace(",", ".")) > 0:
            vorgabe = (float(m.group(2).replace(",", ".")) / float(m.group(1).replace(",", ".")), "Schriftfeld")
    masse = masse_aufgeloest(li.mass, li.texte) + li.dims
    f_je = massstab_je_ansicht(ansichten, masse, (vorgabe[0], vorgabe[1] or "Vorgabe 1:1"))
    # Schnitt (Zuordnung von Hand: nur die Ansicht mit Rolle Schnitt)
    qs, schnitte = None, 0
    for i, (a, (f, quelle)) in enumerate(zip(ansichten, f_je)):
        if rollen.get(i) in ("weg", "vorne", "oben") or ("schnitt" in rollen.values() and rollen.get(i) != "schnitt"):
            continue
        q = querschnitt(a, li.sicht, li.kreise)
        if q:
            schnitte += 1
            qs = qs or (a, q, f, quelle)
    pt = erg["profil_text"]
    erg["rohrartig"] = bool(qs or pt)
    erg["ansichten"] = ansichten_liste(lambda a: "Schnitt" if qs and a is qs[0] else "Isometrie" if a.iso else
                                       "nicht verwendet", f_je)
    if qs and qs[3] != "Bemaßung" and pt:      # Schnitt ohne eigenes Maß: Maßstab aus dem Profiltext
        f = pt["a"] / max(qs[1]["B"], qs[1]["H"])
        best = min(di.MASSSTAEBE, key=lambda s_: abs(s_ - f) / s_)
        if abs(best - f) / best < 0.01:
            qs = (qs[0], qs[1], best, "Profiltext")
    if not qs and not pt:
        warn.append("Kein Rohrschnitt und kein Profiltext (z. B. „Quadratrohr 40x40x3“): keine Rohrzeichnung.")
        return erg
    # Profil: aus dem Schnitt, sonst aus dem Text
    if qs:
        a_, f = qs[1], qs[2]
        B, H, t = a_["B"] * f, a_["H"] * f, a_["wand"] * f
        profil = dict(form=a_["form"], a=_rund(max(B, H)), b=_rund(min(B, H)), wand=_rund(t))
        erg["profil_quelle"] = f"Schnitt ({_massstab_text(f)})"
        if pt and (pt["form"] != profil["form"] or abs(pt["a"] - profil["a"]) > 0.3 or
                   abs(pt["b"] - profil["b"]) > 0.3 or abs(pt["wand"] - profil["wand"]) > 0.15):
            warn.append(f"Profil im Text ({_profil_text(pt)}) weicht vom Schnitt ({_profil_text(profil)}) ab: "
                        "der Schnitt gilt, bitte prüfen.")
    else:
        profil = dict(pt)
        erg["profil_quelle"] = "Text"
    seiten_echt = (profil["a"], profil["b"])
    # Längsansichten: die schmale Seite ist so groß wie eine Profilseite (Ansicht ohne eigenes Maß: auch mit einem
    # anderen Normmaßstab, wenn der passt)
    laengs, senkrecht = [], False
    for i, (a, (f, quelle)) in enumerate(zip(ansichten, f_je)):
        if a.iso or (qs and a is qs[0]) or rollen.get(i) in ("weg", "schnitt"):
            continue
        hoch = a.hoehe if a.breite >= a.hoehe else a.breite
        if not any(da.gleich(hoch * f, s_) for s_ in seiten_echt) and quelle != "Bemaßung":
            f = next((m for m in di.MASSSTAEBE if any(da.gleich(hoch * m, s_) for s_ in seiten_echt)), f)
        passt = any(da.gleich(hoch * f, s_) for s_ in seiten_echt)
        if a.breite < a.hoehe:
            senkrecht |= passt and a.hoehe > a.breite * 1.05
            continue
        if (passt and a.breite > a.hoehe * 1.05) or rollen.get(i) in ("vorne", "oben"):
            laengs.append((a, f, quelle, i))
    if not laengs:
        erg["senkrecht"] = senkrecht
        warn.append(f"Keine Längsansicht passt zum Profil {_profil_text(profil)} (waagrecht liegend, Ende A links).")
        return erg
    # mehrere Teile auf dem Blatt: Längsansichten gleicher Länge gehören zusammen
    teile = []
    for x in sorted(laengs, key=lambda x: -x[0].breite * x[1]):
        lg = x[0].breite * x[1]
        gruppe = next((g for g in teile if abs(g[0][0].breite * g[0][1] - lg) <= 0.5), None)
        if gruppe is None:
            teile.append([x])
        else:
            gruppe.append(x)
    erg["teile"] = len(teile)
    if len(teile) > 1 or schnitte > 1:
        nr = min(max(int(vorgaben.get("teil") or 0), 0), len(teile) - 1)
        laengs = teile[nr]
        if not vorgaben.get("teil_gewaehlt"):
            unsicher.append(f"{max(len(teile), schnitte)} Teile auf dem Blatt: Teil {nr + 1} übernommen "
                            f"({_z(_rund(laengs[0][0].breite * laengs[0][1], 1))} mm lang).")
    erg["profil"] = profil
    # Rollen der Längsansichten: von Hand; sonst Rechteckrohr nach Breite; sonst nach der Projektionsmethode (1: die
    # obere ist die Vorderansicht, die untere die Draufsicht; 3: umgekehrt)
    lvs = []
    for a, f, _q, i in laengs:
        lv = Laengsansicht(a, f, li.sicht, li.kreise, li.verdeckt)
        lv.nr = i
        lvs.append(lv)
    lvs.sort(key=lambda lv: -lv.bb[3])
    von_hand = [lv for lv in lvs if rollen.get(lv.nr) in ("vorne", "oben")]
    if von_hand:
        for lv in lvs:
            lv.seite = rollen.get(lv.nr) if lv in von_hand else None
    elif profil["form"] == "Rechteckrohr":
        for lv in lvs:
            lv.seite = "oben" if da.gleich(lv.hoehe * lv.f, profil["a"]) else "vorne"
    elif len(lvs) == 1:
        lvs[0].seite = "oben"
    else:
        lvs[0].seite, lvs[1].seite = ("oben", "vorne") if proj == 3 else ("vorne", "oben")
        if proj is None:
            unsicher.append("Projektionsmethode nicht in der Zeichnung: Europa/DIN angenommen (obere Längsansicht = "
                            "Vorderansicht).")
    lvs = [lv for lv in lvs if lv.seite][:2]
    if len({lv.seite for lv in lvs}) < len(lvs):
        lvs = lvs[:1]
    if all(quelle.startswith("Vorgabe") for _a, _f, quelle, _i in laengs) and not masse:
        unsicher.append("Keine Bemaßung und kein Maßstab im Schriftfeld: Maßstab 1:1 angenommen.")
    # Länge
    laengen = [lv.a.breite * lv.f for lv in lvs]
    L = max(laengen)
    if max(laengen) - min(laengen) > 0.5:
        warn.append("Die Längsansichten sind verschieden lang: " +
                    " / ".join(f"{_z(x)} mm" for x in laengen) + ", die größte gilt.")
    erg["laenge"] = _rund(L, 1)
    if erg["laenge_text"] and abs(erg["laenge_text"] - erg["laenge"]) > 0.5:
        hinweise.append(f"Länge gemessen {_z(erg['laenge'])} mm (Spitze bis Spitze), im Text L = "
                        f"{_z(erg['laenge_text'])} mm.")
    # Enden
    eing = dict(quelle=sw.QUELLE, a={}, b={}, konturen=[], dxf=dateiname or True)
    zonen = {}
    for seite_ende, links in (("a", True), ("b", False)):
        tu = tv = 0.0
        lo, hi = math.inf, -math.inf
        for lv in lvs:
            k = lv.endkante(links)
            if k is None:
                continue
            c, s, eben = k
            if not eben:
                warn.append(f"Ende {seite_ende.upper()}: Endkante in der {_ansicht_name(lv)} nicht gerade "
                            "(Ausklinkung oder Sattel?): als gerader Schnitt angenommen, bitte im Rohr-Editor prüfen.")
                s = 0.0
            for y in (lv.bb[1], lv.bb[3]):
                x = c + s * (y - lv.yc)
                lo, hi = min(lo, x), max(hi, x)
            if lv.seite == "vorne":
                tv = s
            else:
                tu = -s
        if lo > hi:
            x = lvs[0].bb[0] if links else lvs[0].bb[2]
            lo = hi = x
        zonen[seite_ende] = (lo, hi)
        eing[seite_ende] = gehrung(tu, tv, not links, profil)
        if eing[seite_ende] and len(lvs) < 2:
            hinweise.append(f"Ende {seite_ende.upper()}: nur eine Längsansicht, die Neigung über die andere "
                            "Richtung ist als 0° angenommen.")
    # Konturen je Längsansicht, mit Wand aus der anderen Ansicht
    for lv in lvs:
        andere = next((x for x in lvs if x is not lv), None)
        wand_z = profil["wand"] / andere.f if andere and profil["wand"] else 0.0
        x_ref = lv.bb[0]
        for k in konturen(lv, zonen["a"], zonen["b"]):
            ob, un = wand_hinweis(k, andere, wand_z)
            fern = un if lv.seite == "oben" else ob         # Hinweis auf die gegenüberliegende Wand
            nah = ob if lv.seite == "oben" else un
            z = _kontur_zeile(k, lv, "fern" if fern and not nah else "nah", x_ref, profil, zonen)
            if fern and nah:
                z["wand"] = "beide"          # durchgehend (Plan 3D-Editor 3E-4: Kopie auf der Gegenwand)
            eing["konturen"].append(z)
            if k.get("unsicher"):
                warn.append(f"Kontur bei x = {_z(_rund((k['cx'] - x_ref) * lv.f, 1))} mm nicht geschlossen: als "
                            "Sonderkontur mit der Hülle übernommen, bitte prüfen.")
    eing["konturen"] = muster(eing["konturen"])
    erg["eingaben"] = eing
    erg["ansichten"] = ansichten_liste(lambda a: "Schnitt" if qs and a is qs[0] else "Isometrie" if a.iso else
                                       next((_ansicht_name(lv) for lv in lvs if lv.a is a), "nicht verwendet"), f_je)
    methode = "von Hand zugeordnet" if von_hand else \
        f"Projektionsmethode {proj or 1} ({proj_quelle or 'angenommen'})"
    hinweise.insert(0, f"Ansichten {methode}: " + ", ".join(f"{_ansicht_name(lv)} = Seite {lv.seite}" for lv in lvs)
                    + (", Zeichnung um 90° gedreht (oberes Ende = Ende A)" if vorgaben.get("drehung") else
                       ", Ende A links") + ".")
    erg["ok"] = True
    return erg


def _kontur_zeile(k, lv, wand, x_ref, profil, zonen):
    """Kontur k der Längsansicht lv als Zeile des Rohr-Editors; wand 'oben'/'vorn' (die Fläche, auf die man blickt),
    'nah'/'fern' (beide bzw. die gegenüberliegende)."""
    f = lv.f
    blick = "oben" if lv.seite == "oben" else "vorne"
    gegen = {"oben": "unten", "vorne": "hinten"}[blick]
    seite = gegen if wand == "fern" else blick
    form = profil.get("form")
    a_, b_ = float(profil.get("a") or 0), float(profil.get("b") or profil.get("a") or 0)
    B, H = max(a_, b_), min(a_, b_)
    if form == "Rundrohr":
        B = H = a_
    # quer in der Zeichnung (y) -> Punkt (u, v) des Querschnitts
    def uv(y):
        d = (y - lv.yc) * f
        if blick == "oben":                 # Draufsicht: unten in der Zeichnung = vorne
            return -d, (H / 2 if seite == "oben" else -H / 2)
        return (B / 2 if seite == "vorne" else -B / 2), d
    z = dict(art=k["art"], anzahl=1)
    if k["art"] == sw.AUSKLINKUNG:
        # ab der Kante der Fläche, um Eckradius und Wand über das Ende hinaus (offen durch die ganze Wand, auch
        # bei Gehrung; die Ecken mit Radius liegen außerhalb), höchstens bis zur Spitze des Endes
        r = k.get("r") or 0.0
        ueber = r + (profil.get("wand") or 0.0) / f
        if k["ende"] == "a":
            xa, xb = max(zonen["a"][0], k["x0"] - ueber), k["x1"]
        else:
            xa, xb = k["x0"], min(zonen["b"][1], k["x1"] + ueber)
        z.update(l=_rund((xb - xa) * f, 1), b=_rund(k["b"] * f, 1), r=_fangen(r * f),
                 x=_rund(((xa + xb) / 2 - x_ref) * f, 1))
    else:
        z["x"] = _rund((k["cx"] - x_ref) * f, 1)
        if k["art"] == sw.BOHRUNG:
            z["d"] = _rund((k["x1"] - k["x0"]) * f, 2)
        elif k["art"] == sw.LANGLOCH:
            z.update(l=_rund(k["l"] * f, 2), b=_rund(k["b"] * f, 2))
            if k.get("quer"):
                z["quer"] = True
        elif k["art"] == sw.RECHTECK:
            z.update(b=_rund(k["b"] * f, 2), h=_rund(k["h"] * f, 2), r=_fangen(k["r"] * f))
    if form == "Rundrohr":         # Winkel am Umfang (0° oben, 90° vorne) aus dem Versatz quer zur Blickrichtung
        d = max(-1.0, min(1.0, (k["cy"] - lv.yc) * f / (B / 2)))
        w = math.degrees(math.asin(d))
        winkel = {"oben": -w, "unten": 180 + w, "vorne": 90 - w, "hinten": 270 + w}[seite]
        z["seite"] = _rund(winkel % 360, 1)
    else:
        from . import skizze as sk
        fl = sk.Querschnitt(dict(form=form, a=a_, b=b_, wand=profil.get("wand"))).flaeche(seite)

        def q_von(y):
            p = uv(y)
            return (p[0] - fl.mitte[0]) * fl.dir[0] + (p[1] - fl.mitte[1]) * fl.dir[1]
        q = q_von(k["cy"])
        if abs(q) > 0.05:
            z["q"] = _rund(q, 1)
        if seite != "oben":
            z["seite"] = seite
        if k["art"] == sw.SONDERKONTUR:
            pk = k["umriss"]
            z["umriss"] = [[_rund((x - k["cx"]) * f, 2), _rund(q_von(y) - q, 2)] for x, y in pk]
            lg = sum(math.dist(p, pk[(i + 1) % len(pk)]) for i, p in enumerate(pk)) * f
            z.update(laenge=_rund(lg, 1), huelle=_rund(max(k["x1"] - k["x0"], k["y1"] - k["y0"]) * f, 1))
    if k["art"] == sw.SONDERKONTUR and form == "Rundrohr":     # Rundrohr: nur Länge und Hülle, Lage über Winkel
        pk = k["umriss"]
        lg = sum(math.dist(p, pk[(i + 1) % len(pk)]) for i, p in enumerate(pk)) * f
        z.update(art=sw.SONSTIGE, laenge=_rund(lg, 1), huelle=_rund(max(k["x1"] - k["x0"], k["y1"] - k["y0"]) * f, 1))
    return z


def _fangen(r):
    """Eckradius aus gezeichneten (in Stücke zerlegten) Bögen: auf 0,5 mm, wenn er höchstens 0,2 mm daneben liegt."""
    n = round(r * 2) / 2
    return _rund(n if abs(n - r) <= 0.2 else r, 1)


def muster(zeilen):
    """Gleiche Konturen (Art, Maße, Seite, Versatz) in gleichem Abstand längs als eine Zeile mit Anzahl und Abstand
    (ab drei Stück)."""
    def schluessel(z):
        return tuple(sorted((k_, json_wert(v)) for k_, v in z.items() if k_ != "x"))
    gruppen = {}
    for z in zeilen:
        gruppen.setdefault(schluessel(z), []).append(z)
    out = []
    for gr in gruppen.values():
        gr = sorted(gr, key=lambda z: z["x"])
        i = 0
        while i < len(gr):
            j = i + 1
            if j < len(gr):
                ab = gr[j]["x"] - gr[i]["x"]
                while j + 1 < len(gr) and abs(gr[j + 1]["x"] - gr[j]["x"] - ab) <= 0.15:
                    j += 1
                if j - i + 1 >= 3 and ab > 0:
                    out.append(dict(gr[i], anzahl=j - i + 1, abstand=_rund(ab, 1)))
                    i = j + 1
                    continue
            out.append(gr[i])
            i += 1
    return sorted(out, key=lambda z: z["x"])


def json_wert(v):
    return tuple(map(json_wert, v)) if isinstance(v, list) else v


def _ansicht_name(lv):
    return "Vorderansicht" if lv.seite == "vorne" else "Draufsicht"


def _massstab_text(f):
    return f"1:{_z(f)}" if f >= 1 else f"{_z(1 / f)}:1"


def _z(v):
    return f"{v:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _profil_text(p):
    kurz = {"Rundrohr": "RR", "Quadratrohr": "QR", "Rechteckrohr": "RE"}.get(p.get("form"), p.get("form") or "")
    mass = _z(p["a"]) if p.get("form") == "Rundrohr" else f"{_z(p['a'])} × {_z(p['b'])}"
    return f"{kurz} {mass} × {_z(p.get('wand') or 0)}"


def profil_id(profil, profile):
    """Profil der Stammdaten zum erkannten Profil (wie beim STEP-Import, step.finde_profil) oder None."""
    from .step import finde_profil
    if not profil:
        return None
    return finde_profil(dict(profilform=profil["form"], abm_a=profil["a"], abm_b=profil["b"],
                             wandstaerke=profil["wand"]), profile)


def ersatz_profil(profil, profile):
    """Ohne passendes Profil: das ähnlichste der gleichen Form (Außenmaß, dann Wand), sonst None."""
    gleich_ = [(pid, p) for pid, p in profile.items() if p.get("form") == (profil or {}).get("form")]
    if not gleich_:
        return None
    return min(gleich_, key=lambda x: (abs(float(x[1].get("a") or 0) - profil["a"]) +
                                       abs(float(x[1].get("b") or x[1].get("a") or 0) - profil["b"]),
                                       abs(float(x[1].get("wand") or 0) - profil["wand"])))[0]


def werkstoff_id(erg, werkstoffe, dateiname=""):
    """Werkstoff der Stammdaten aus Dateiname, Schriftfeld und Texten (dxf_import.werkstoff_aus) oder None."""
    gefunden = di.werkstoff_aus([dateiname], werkstoffe) or di.werkstoff_aus([erg.get("werkstoff_text") or ""],
                                                                             werkstoffe)
    if gefunden:
        return gefunden
    # Rohr-Werkstoffe heißen oft mit Norm (S235-10219): der Teil vor der Norm genügt („Stahl S235JR“)
    text = " ".join((dateiname or "", erg.get("werkstoff_text") or "")).upper()
    for wid in sorted(werkstoffe, key=str.lower):
        basis = re.split(r"[-\s/]", wid.upper())[0]
        if len(basis) >= 4 and re.search(rf"(?<![A-Z0-9.]){re.escape(basis)}(?![0-9])", text):
            return wid
    return None


def _ende_text(e):
    if not e or not e.get("winkel"):
        return "gerade"
    if e.get("achse") == sw.ACHSE_ZWEI:
        return f"schräg {_z(e['winkel_h'])}° / {_z(e['winkel_b'])}°"
    return f"Gehrung {_z(e['winkel'])}°"


def bericht(erg, pid=None):
    """Zusammenfassung für den Rohr-Editor (eine Zeile je Punkt)."""
    eing = erg.get("eingaben") or {}
    n = sum(int(z.get("anzahl") or 1) * (2 if z.get("wand") == "beide" else 1) for z in eing.get("konturen") or ())
    zeilen = [f"Aus DXF: {_profil_text(erg['profil'])} (aus {erg.get('profil_quelle')}), Länge "
              f"{_z(erg['laenge'])} mm, Ende A {_ende_text(eing.get('a'))}, Ende B {_ende_text(eing.get('b'))}, "
              f"{n} Kontur{'en' if n != 1 else ''}."]
    if pid is None:
        zeilen.append(f"Profil {_profil_text(erg['profil'])} fehlt in den Stammdaten: bitte mit „Neu …“ anlegen "
                      "oder ein anderes wählen.")
    return zeilen + list(erg.get("hinweise") or ()) + list(erg.get("warnungen") or ())


def ist_rohrzeichnung(text, dateiname=""):
    """Schnelltest für den DXF-Import: erkennen() ok?"""
    try:
        return erkennen(text, dateiname)["ok"]
    except (ValueError, KeyError, TypeError, ZeroDivisionError):
        return False
