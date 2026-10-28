"""Palettenanzahl und Packliste (Plan Palettenbegleitschein, Patrick 24.10.2026, Freigabe „a a a a a a a a b a“;
Nachtrag Patrick 24.10.: „so genau wie möglich – nicht 3 rechnen, wenn es in Wirklichkeit 9 sind“).

Gerechnet wird lagenweise wie beim Packen, nicht über einen Raumanteil: jede Palette ist ein Stapel aus Lagen, jede
Lage gehört zu einer Position, ihre Teile liegen nebeneinander. So ist jede Zahl nachprüfbar (Text 'aufbau' je
Palette, z. B. „Pos. 10: 7 Lagen × 16 Stück (1 Reihe, 50 mm Überstand) = 112 Stück, Stapel 1.019 mm, 279 kg“).

Packstück je Position (was zusammen versandt wird):
  Rohr/Profil      Teilelänge × Außenmaß (Rundrohr Ø × Ø, Flachstahl Breite × Dicke, offene Profile A × B)
  Knickrahmen      Rahmen in der Ebene (Hüllrechteck der Schenkel) × größeres Rohrmaß
  Biegerohr        Hüllquader des Tangentenzugs + Rohr-Ø
  Blech (Editor)   Zuschnitt Länge × Breite × Dicke, Kantteil Kantlänge × Hüllmaß der Seitenansicht
  Schweißbaugruppe Abmessungen aus den Stammdaten der Baugruppe ('1200 x 800 x 600'), Gewicht je Baugruppe aus
                   'Gewicht je Teil', sonst Summe der Einzelteile; die Einzelteile reisen in der Baugruppe mit
  sonst            ohne Maße: nur nach Gewicht (Hinweis)

Ladungsträger (Tabelle Ladehilfsmittel der Frachtkosten): Teile bis zur 'max. Teillänge' des Standard-Ladungsträgers
kommen auf ihn, längere auf Langgut, noch längere sind Sonderladung (Hinweis).

Lage: die längste Seite liegt immer waagrecht; probiert werden die liegenden Ausrichtungen,
  Reihen längs = ⌊Palettenlänge / Maß längs⌋ (länger als die Palette bis 'max. Teillänge': 1 Reihe mit Überstand),
  Teile quer   = ⌊Palettenbreite / Maß quer⌋, Teile je Lage = Reihen × quer × Lagenausnutzung (abgerundet, ≥ 1;
                 Bündel, Umreifung, Kanten­schutz).
  Rundrohre liegen wahlweise versetzt (jede zweite Lage in den Mulden: Lagenabstand Ø·√3/2, je nach Breite ein
  Rohr weniger); es gilt, was mehr Stück ergibt.
  Stapelhöhe = erste Lage + je weitere Lage (Lagenabstand + Zwischenlage), höchstens 'max. Höhe inkl.
  Ladungsträger' − Höhe des Ladungsträgers (Gitterbox: ihre Innenhöhe).
Gewicht: je Palette höchstens 'max. Bruttogewicht' − Eigengewicht bzw. die Nutzlast (das kleinere).

Packen: je Ladungsträger-Art. 'Positionen mischen' (Patrick 24.10.: „Vorgabe einzeln packen, wenn Platz ist, auch
zusammen“):
  Reste zusammenpacken (Vorgabe)  jede Position zuerst auf eigene Paletten, je Palette so viele Lagen, wie Höhe und
                                  Gewicht zulassen; danach kommen angefangene Paletten als ganzer Stapel auf eine
                                  andere angefangene Palette, wenn Höhe und Gewicht reichen (lange unten)
  nie                             jede Position nur auf eigenen Paletten
  immer                           Positionen teilen sich Paletten lagenweise, lange unten
Eine angefangene Lage zählt immer mit ihrer vollen Höhe. 'Max. Stück je Palette' von Hand ersetzt die Lagenrechnung der
Position (sie liegt dann allein auf der Palette). Ergebnis ist reproduzierbar (keine Zufallswahl).
"""
import json
import math
import re

from . import baugruppe, biegerohr, blech, knickrahmen
from .angebot import BAUGRUPPE, ist_baugruppe
from .stammdaten import zahl_als_text

EPS = 1e-9
HOEHE_GESAMT = 1200         # Vorgabe max. Höhe der beladenen Palette inkl. Ladungsträger [mm]
MAX_BRUTTO = 1500.0         # Vorgabe max. Bruttogewicht je Palette [kg] (Patrick 24.10.: 1,2 m und 1,5 t)
MISCHEN_RESTE, MISCHEN_NIE, MISCHEN_IMMER = "Reste zusammenpacken", "nie", "immer"
MISCHEN = (MISCHEN_RESTE, MISCHEN_NIE, MISCHEN_IMMER)
FUELLGRAD = 0.9             # Vorgabe Lagenausnutzung (Bündel, Umreifung, Kantenschutz)
GITTERBOX = "Gitterbox"
WURZEL3_2 = math.sqrt(3) / 2


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _zahl(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def vorgaben(einst):
    """Rechenwerte aus den Einstellungen (dict Name -> Wert; fehlende = Vorgabe)."""
    einst = einst or {}
    h = einst.get("palette_hoehe_gesamt")
    f = einst.get("palette_fuellgrad")
    b = einst.get("palette_max_brutto")
    z = einst.get("palette_zwischenlage")
    return dict(hoehe_gesamt=float(h) if _zahl(h) and h > 0 else HOEHE_GESAMT,
                fuellgrad=float(f) if _zahl(f) and 0 < f <= 1 else FUELLGRAD,
                max_brutto=float(b) if _zahl(b) and b > 0 else (None if "palette_max_brutto" in einst else MAX_BRUTTO),
                zwischenlage=float(z) if _zahl(z) and z > 0 else 0.0,
                mischen=einst.get("palette_mischen") if einst.get("palette_mischen") in MISCHEN else MISCHEN_RESTE)


def _mm(x):
    return zahl_als_text(x, 0)


# ------------------------------------------------------------------ Packmaß
def _technik(p):
    t = (p or {}).get("technik")
    if isinstance(t, dict):
        return t
    try:
        d = json.loads(t) if t else None
    except (TypeError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def abmessungen_text(text):
    """'1200 x 800 x 600', '1200×800×600 mm' -> (1200, 800, 600); sonst None."""
    zahlen = [float(z.replace(",", ".")) for z in re.findall(r"\d+(?:[.,]\d+)?", str(text or ""))]
    zahlen = [z for z in zahlen if z > 0]
    return tuple(zahlen[:3]) if len(zahlen) >= 3 else None


def _profil_quer(abm):
    """Querschnitt (b, h) aus (form, a, b, wand) der Position (rechnen.position_werte 'profil_abm')."""
    if not abm:
        return None
    form, a, b, wand = abm
    if not _zahl(a) or a <= 0:
        return None
    if form == "Flachstahl":
        return (a, wand) if _zahl(wand) and wand > 0 else None
    if form in ("Rundrohr", "Quadratrohr"):
        return (a, a)
    return (a, b) if _zahl(b) and b > 0 else (a, a)


def packmass(p, w):
    """Packstück-Maße (l, b, h) in mm (längste zuerst) oder None, wenn sie sich nicht bestimmen lassen."""
    p, w = p or {}, w or {}
    if ist_baugruppe(p):
        bg = baugruppe.lesen(p.get("baugruppe"))
        m = abmessungen_text(((bg or {}).get("stamm") or {}).get("abmessungen"))
        return tuple(sorted(m, reverse=True)) if m else None
    t = _technik(p)
    if t and blech.lesen(p.get("technik")):
        try:
            zs = blech.zuschnitt(t)
        except (ValueError, TypeError, KeyError, ZeroDivisionError):
            return None
        s = _n(t.get("dicke"))
        if t.get("art") == blech.KANTTEIL:
            pk = blech.querschnitt(t)
            xs, ys = [x for x, _ in pk], [y for _, y in pk]
            masse = (_n(t.get("kantlaenge")), max(xs) - min(xs) + s, max(ys) - min(ys) + s)
        else:
            masse = (zs["laenge"], zs["breite"], s)
        return tuple(sorted(masse, reverse=True)) if min(masse) > 0 else None
    quer = _profil_quer(w.get("profil_abm"))
    if quer is None:
        return None
    if t and knickrahmen.lesen(t):
        k = knickrahmen.lesen(t)
        x = y = 0.0
        punkte, richtung = [(0.0, 0.0)], 0.0
        winkel = k.get("beta")
        schenkel = [_n(s) for s in k.get("schenkel") or ()]
        betas = winkel if isinstance(winkel, list) else [winkel if _zahl(winkel) else 90.0] * (len(schenkel) - 1)
        for i, s in enumerate(schenkel):
            x += s * math.cos(math.radians(richtung))
            y += s * math.sin(math.radians(richtung))
            punkte.append((x, y))
            if i < len(betas):
                richtung += _n(betas[i]) or 90.0
        xs, ys = [q[0] for q in punkte], [q[1] for q in punkte]
        masse = (max(xs) - min(xs) + min(quer), max(ys) - min(ys) + min(quer), max(quer))
        return tuple(sorted(masse, reverse=True))
    br = biegerohr.lesen(t) if t else None
    if br and br.get("xyz"):
        d = max(quer)
        pk = [q for q in br["xyz"] if isinstance(q, (list, tuple)) and len(q) == 3]
        if len(pk) >= 2:
            masse = tuple(max(q[i] for q in pk) - min(q[i] for q in pk) + d for i in range(3))
            return tuple(sorted(masse, reverse=True))
    laenge = p.get("laenge")
    if not _zahl(laenge) or laenge <= 0:
        return None
    return tuple(sorted((float(laenge),) + tuple(float(q) for q in quer), reverse=True))


def _rund(p, w):
    """Gerades Rundrohr (darf versetzt gestapelt werden)."""
    abm = (w or {}).get("profil_abm")
    t = _technik(p)
    return bool(abm and abm[0] == "Rundrohr" and not (t and (knickrahmen.lesen(t) or biegerohr.lesen(t))))


def packstuecke(positionen, werte):
    """Packstücke der Ware: [{i (Index), pos, artikel, bezeichnung, stueck, gewicht (kg je Stück oder None),
    masse (l, b, h) oder None}]. Einzelteile einer Schweißbaugruppe reisen in ihr (ohne eigene Zeile); fehlt der
    Baugruppe das Gewicht, zählt die Summe ihrer Teile."""
    bgs = baugruppe.baugruppen(positionen)
    in_bg = {j for bg_id in bgs for j in baugruppe.teile(positionen, bg_id)}
    soll = baugruppe.soll_werte(positionen) if bgs else {}
    out = []
    for i, (p, w) in enumerate(zip(positionen, werte, strict=True)):
        if w is None or i in in_bg:
            continue
        n = p.get("stueck")
        if not _zahl(n) or n <= 0:
            continue
        g = w.get("gewicht")
        if p.get("art") == BAUGRUPPE and not (_zahl(g) and g > 0):
            bg = baugruppe.lesen(p.get("baugruppe"))
            teile = baugruppe.teile(positionen, bg["id"]) if bg else []
            summe, fehlt = 0.0, not teile
            for j in teile:
                gj = (werte[j] or {}).get("gewicht") if j < len(werte) else None
                je = (soll.get(j) or {}).get("je_satz") or positionen[j].get("je_satz") or 1
                if _zahl(gj) and gj > 0:
                    summe += gj * je
                else:
                    fehlt = True
            g = summe if not fehlt else None
        out.append(dict(i=i, pos=p.get("pos"), artikel=p.get("artikel") or "", bezeichnung=p.get("bezeichnung") or "",
                        stueck=int(n), gewicht=g if _zahl(g) and g > 0 else None, masse=packmass(p, w),
                        id=p.get("id"), rund=_rund(p, w)))
    return out


# ------------------------------------------------------------------ Ladungsträger
def _lht(lht_zeilen, lht_id):
    for z in lht_zeilen or ():
        if z.get("lht_id") == lht_id and (z.get("aktiv") or "ja") != "nein":
            return z
    return None


def _max_laenge(z):
    return _n(z.get("max_laenge")) or _n(z.get("laenge"))


def traeger_waehlen(masse, std, lg):
    """Ladungsträger für ein Packstück: (Zeile, Hinweis oder None)."""
    l = masse[0] if masse else 0.0
    if not std:
        return lg, None
    if not l or l <= _max_laenge(std) + EPS:
        return std, None
    if lg and l <= _max_laenge(lg) + EPS:
        return lg, None
    if lg:
        return lg, "länger als der Langgut-Ladungsträger: Sonderladung prüfen"
    return std, "länger als der Ladungsträger erlaubt (kein Langgut eingestellt): Sonderladung prüfen"




def stapelhoehe(z, v):
    """Für die Ladung nutzbare Höhe [mm]: max. Höhe inkl. Ladungsträger − dessen Höhe (Gitterbox: Innenhöhe)."""
    if z.get("art") == GITTERBOX and _n(z.get("hoehe")):
        return min(_n(z["hoehe"]), v["hoehe_gesamt"])
    return v["hoehe_gesamt"] - _n(z.get("hoehe"))


def nutzlast(z, v):
    """Zuladung je Ladungsträger [kg] (None = ohne Grenze)."""
    werte = []
    if _n(z.get("nutzlast")):
        werte.append(_n(z["nutzlast"]))
    if v["max_brutto"]:
        werte.append(v["max_brutto"] - _n(z.get("eigengewicht")))
    return max(0.0, min(werte)) if werte else None


# ------------------------------------------------------------------ Lagen
class Plan:
    """Lagenaufbau einer Position auf einem Ladungsträger: Stück je Lage (abwechselnd bei versetzten Rundrohren),
    Höhe der ersten Lage, Abstand jeder weiteren Lage (inkl. Zwischenlage), höchstens lagen_max Lagen."""

    def __init__(self, je_lage, erste, abstand, lagen_max, text, hand=False):
        self.je_lage, self.erste, self.abstand, self.lagen_max = je_lage, erste, abstand, lagen_max
        self.text, self.hand = text, hand

    def stueck(self, lagen):
        """Stück in so vielen vollen Lagen."""
        n = len(self.je_lage)
        return sum(self.je_lage[i % n] for i in range(lagen))

    def lagen_fuer(self, stueck):
        """Lagen, die stueck Teile brauchen (die letzte ggf. angefangen)."""
        lagen, summe = 0, 0
        while summe < stueck:
            summe += self.je_lage[lagen % len(self.je_lage)]
            lagen += 1
        return lagen

    def hoehe(self, lagen):
        return self.erste + (lagen - 1) * self.abstand if lagen else 0.0

    def lagen_in(self, hoehe):
        """Wie viele Lagen passen in diese Höhe?"""
        if hoehe + EPS < self.erste:
            return 0
        return 1 + int((hoehe - self.erste) // self.abstand + EPS) if self.abstand > EPS else self.lagen_max

    @property
    def voll(self):
        return self.stueck(self.lagen_max)


def lagenplan(masse, rund, z, v):
    """Bester Lagenaufbau eines Packstücks auf dem Ladungsträger z: (Plan oder None, Hinweis oder None)."""
    pl, pb = _n(z.get("laenge")), _n(z.get("breite"))
    if pb > pl:
        pl, pb = pb, pl
    hoehe = stapelhoehe(z, v)
    if not (pl and pb) or hoehe <= 0:
        return None, "Maße des Ladungsträgers fehlen: nur nach Gewicht"
    ml = max(_max_laenge(z), pl)
    f, zl = v["fuellgrad"], v["zwischenlage"]
    best = None
    lagen = {(masse[a], masse[b], masse[c]) for a, b, c in ((0, 1, 2), (0, 2, 1), (1, 0, 2), (2, 0, 1))}
    for x, y, h in sorted(lagen, reverse=True):
        reihen = math.floor(pl / x + EPS) if x <= pl + EPS else (1 if x <= ml + EPS else 0)
        quer = math.floor(pb / y + EPS)
        if not reihen or not quer or h > hoehe + EPS:
            continue
        ueber = x - pl if x > pl + EPS else 0.0
        arten = [([quer], h, "")]
        if rund and abs(y - h) < EPS and quer >= 1:
            quer2 = math.floor((pb - y / 2) / y + EPS)
            arten.append(([quer, quer2] if quer2 < quer else [quer], h * WURZEL3_2, ", versetzt gestapelt"))
        for quer_je, abstand, art in arten:
            je = [max(1, math.floor(reihen * q * f + EPS)) for q in quer_je if q > 0]
            if not je:
                continue
            p = Plan(je, h, abstand + zl, 0, "")
            p.lagen_max = p.lagen_in(hoehe)
            reihe = f"{reihen} Reihe{'n' if reihen != 1 else ''}" + (f", {_mm(ueber)} mm Überstand" if ueber else "")
            stk = "/".join(str(x) for x in je)
            p.text = f"{stk} Stück je Lage ({reihe}{art}; Teil {_mm(x)} × {_mm(y)} × {_mm(h)} mm)"
            if best is None or p.voll > best.voll:
                best = p
    if best is None:
        p = Plan([1], masse[2], masse[2] + zl, 1, f"größer als der Ladungsträger: 1 Stück, Teil {_mm(masse[0])} × "
                 f"{_mm(masse[1])} × {_mm(masse[2])} mm")
        return p, "größer als der Ladungsträger: 1 Stück je Ladungsträger, Sonderladung prüfen"
    return best, None


# ------------------------------------------------------------------ Packen
def _neue(paletten, z):
    pal = dict(lht=z, hoehe=0.0, gewicht=0.0, inhalt=[], aufbau=[], unbekannt=False)
    paletten.append(pal)
    return pal


def _passen(pal, it, frei, last):
    """(Stück, Lagen), die von it noch auf die Palette passen (Höhe, Gewicht, Rest der Position)."""
    plan, g = it["plan"], it["g"]
    n_g = math.inf if last is None or g <= EPS else math.floor((last - pal["gewicht"]) / g + 1e-7)
    if plan is None:
        return max(0, min(n_g, it["rest"])), 0
    hoehe = frei - pal["hoehe"] - (it["zl"] if pal["hoehe"] > EPS else 0.0)
    lagen = min(plan.lagen_in(hoehe), plan.lagen_max)
    n = min(plan.stueck(lagen), n_g, it["rest"])
    return (n, plan.lagen_fuer(n)) if n > 0 else (0, 0)


def _reste_zusammen(liste, frei, last, zl):
    """Angefangene Paletten (je eine Position) als ganzen Stapel auf eine frühere Palette setzen, wenn Höhe und
    Gewicht reichen; Paletten mit Teilen ohne Maße bleiben allein. Ergebnis: verbleibende Paletten."""
    for b in reversed(liste[1:]):
        if b["unbekannt"] or not b["hoehe"]:
            continue
        for a in liste:
            if a is b:
                break
            if a["unbekannt"] or not a["hoehe"] or a.get("weg"):
                continue
            if a["hoehe"] + zl + b["hoehe"] <= frei + EPS and (last is None or a["gewicht"] + b["gewicht"] <=
                                                                 last + 1e-6):
                a["hoehe"] += zl + b["hoehe"]
                a["gewicht"] += b["gewicht"]
                a["inhalt"] += b["inhalt"]
                a["aufbau"] += b["aufbau"]
                b["weg"] = True
                break
    return [p for p in liste if not p.get("weg")]


def packen(positionen, werte, lht_zeilen, std_id, lg_id, einst=None, max_je=None):
    """Packliste des Angebots. max_je = {Positions-ID: max. Stück je Palette von Hand}.
    Ergebnis: dict(paletten=[{nr, lht_id, bezeichnung, inhalt=[(Packstück-Index, Stück)], netto, brutto, hoehe
    (inkl. Ladungsträger), aufbau [Text je Position]}], anzahl, je_lht {lht_id: Anzahl}, stuecke (Packstücke mit
    plan_text, je_palette), hinweise, gesamt_stueck, netto, vorgaben)."""
    v = vorgaben(einst)
    std, lg = _lht(lht_zeilen, std_id), _lht(lht_zeilen, lg_id)
    stuecke = packstuecke(positionen, werte)
    hinweise = []
    leer = dict(paletten=[], anzahl=0, je_lht={}, stuecke=stuecke, hinweise=hinweise, vorgaben=v,
                gesamt_stueck=sum(s["stueck"] for s in stuecke), netto=None)
    if not std and not lg:
        hinweise.append(f"Ladungsträger '{std_id or ''}' fehlt (Frachtkosten › Ladehilfsmittel bzw. Einstellungen): "
                        "Paletten bitte von Hand eintragen")
        return leer
    gruppen = {}
    for k, s in enumerate(stuecke):
        z, h = traeger_waehlen(s["masse"], std, lg)
        name = f"Pos. {s['pos'] or '?'}"
        if h:
            hinweise.append(f"{name}: {h}")
        hand = (max_je or {}).get(str(s.get("id")))
        plan = None
        if _zahl(hand) and hand >= 1:
            plan = Plan([int(hand)], stapelhoehe(z, v), 0.0, 1, f"{int(hand)} Stück je Palette (von Hand)", hand=True)
        elif s["masse"]:
            plan, h = lagenplan(s["masse"], s.get("rund"), z, v)
            if h:
                hinweise.append(f"{name}: {h}")
        else:
            hinweise.append(f"{name}: Maße unbekannt, nur nach Gewicht gepackt")
        if s["gewicht"] is None:
            hinweise.append(f"{name}: Gewicht fehlt, Paletten nur nach Lagen")
        last = nutzlast(z, v)
        s["lht_id"] = z["lht_id"]
        s["plan_text"] = plan.text if plan else ""
        voll = plan.voll if plan else math.inf
        if last is not None and s["gewicht"]:
            voll = min(voll, math.floor(last / s["gewicht"] + 1e-7))
        s["je_palette"] = int(voll) if voll != math.inf else None
        if s["je_palette"] == 0:
            hinweise.append(f"{name}: ein Teil ist schwerer als die Zuladung der Palette")
        gruppen.setdefault(z["lht_id"], (z, []))[1].append(
            dict(k=k, n=s["stueck"], rest=s["stueck"], g=s["gewicht"] or 0.0, plan=plan,
                 l=(s["masse"] or (0.0,))[0], zl=v["zwischenlage"]))
    paletten, je_lht = [], {}
    for lht_id, (z, items) in sorted(gruppen.items(), key=lambda x: (x[0] != (std or {}).get("lht_id"), x[0])):
        items.sort(key=lambda it: (-it["l"], it["k"]))
        last, frei = nutzlast(z, v), stapelhoehe(z, v)
        liste = []
        for it in items:
            while it["rest"] > 0:
                kandidaten = liste if v["mischen"] == MISCHEN_IMMER else [p for p in liste if p["inhalt"] and
                                                         p["inhalt"][0][0] == it["k"]]
                ziel = None
                for pal in kandidaten:
                    n, lagen = _passen(pal, it, frei, last)
                    if n > 0:
                        ziel = (pal, n, lagen)
                        break
                if ziel is None:
                    pal = _neue(liste, z)
                    n, lagen = _passen(pal, it, frei, last)
                    n = max(1, n)                 # zu schwer/zu groß: trotzdem 1 Stück je Palette
                    lagen = lagen or (1 if it["plan"] else 0)
                    ziel = (pal, n, lagen)
                pal, n, lagen = ziel
                if it["plan"] is not None and lagen:
                    davor = pal["hoehe"] + (it["zl"] if pal["hoehe"] > EPS else 0.0)
                    pal["hoehe"] = davor + it["plan"].hoehe(lagen)
                pal["gewicht"] += n * it["g"]
                pal["unbekannt"] = pal["unbekannt"] or it["plan"] is None
                pal["inhalt"].append([it["k"], n])
                pal["aufbau"].append((it["k"], n, lagen))
                it["rest"] -= n
        if v["mischen"] == MISCHEN_RESTE:
            liste = _reste_zusammen(liste, frei, last, v["zwischenlage"])
        je_lht[lht_id] = len(liste)
        for pal in liste:
            netto = sum(stuecke[k]["gewicht"] * n for k, n in pal["inhalt"] if stuecke[k]["gewicht"] is not None)
            aufbau = []
            for k, n, lagen in pal["aufbau"]:
                s = stuecke[k]
                t = f"Pos. {s['pos'] or '?'}: {_mm(n)} Stück"
                if lagen:
                    t += f" in {lagen} Lage{'n' if lagen != 1 else ''} à {s['plan_text']}"
                if s["gewicht"]:
                    t += f", {zahl_als_text(s['gewicht'] * n, 0)} kg"
                aufbau.append(t)
            hoehe = pal["hoehe"] + (_n(z.get("hoehe")) if z.get("art") != GITTERBOX else 0.0) if pal["hoehe"] else None
            paletten.append(dict(lht_id=lht_id, bezeichnung=z.get("bezeichnung") or lht_id,
                                 inhalt=[(k, n) for k, n in pal["inhalt"]], netto=netto,
                                 brutto=netto + _n(z.get("eigengewicht")), hoehe=hoehe, aufbau=aufbau))
    for nr, pal in enumerate(paletten, start=1):
        pal["nr"] = nr
    gewichte = [s["gewicht"] for s in stuecke]
    return dict(leer, paletten=paletten, anzahl=len(paletten), je_lht=je_lht,
                netto=sum(g * s["stueck"] for g, s in zip(gewichte, stuecke, strict=True) if g is not None))


def ladung(positionen, werte, lht_zeilen, std_id, lg_id, einst=None):
    """Ladungsträger für die Fracht wie fracht.packvorschlag: ([{lht_id, anzahl}], hinweise)."""
    e = packen(positionen, werte, lht_zeilen, std_id, lg_id, einst)
    return [dict(lht_id=k, anzahl=n) for k, n in e["je_lht"].items() if n], e["hinweise"]


def kurz(e):
    """z. B. '3 Paletten (2 × EUR, 1 × LG)'."""
    n = e["anzahl"]
    if not n:
        return "keine Paletten berechnet"
    teile = ", ".join(f"{x} × {k}" for k, x in e["je_lht"].items())
    return f"{n} Palette{'n' if n != 1 else ''} ({teile})"
