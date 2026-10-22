"""Maßstäbliche Skizze des Schneidweg-Rechners (ohne Oberfläche, damit testbar): Querschnitt je Profilform mit
Flächen, Lage der Konturen auf dem Teil (Seite bzw. Winkel, Versatz quer, Lage ab Anfang, Muster), Schnittlinien der
Enden (gerade, Gehrung mit Richtung, Ausklinkung) und die Projektionen für Draufsicht, Seitenansicht, Ansicht von A
und Abwicklung. Die Zeichnung zeigt nur, was eingegeben ist; Maße, die das Profil nicht hat (Flanschdicke ohne
Normprofil), werden zum Zeichnen mit der Wandstärke angenommen und rechnen nirgends mit.

Koordinaten: x entlang des Teils ab Ende A [mm], Querschnitt u (quer, + = vorne) und v (+ = oben), Mitte des
Hüllrechtecks = 0. Rechteckrohre liegen mit der Breitseite oben (wie Schweißnaht und Gehrungsrichtung). Blick von Ende A: oben 0°, vorne 90° (rechts), unten 180°, hinten 270° wie die Gehrungsrichtung.
Draufsicht = Blick von oben (vorne unten im Bild), Seitenansicht = Blick auf vorne.

Eine Kontur steht auf einer Fläche (Seite): Rundrohr mit dem Winkel (0° oben, 90° vorne …), alle anderen Profile
mit dem Namen der Fläche und dem Versatz q [mm] quer zur Flächenmitte. Ohne Seite liegt sie auf der ersten Fläche.
"""
import math

from . import normprofile, rp_profile
from .schneidweg import (AUSKLINKUNG, BOHRUNG, LANGLOCH, OHNE_HUELLE, POLYGON, RECHTECK, SCHLITZ, SENKUNG, _z, kontur,
                         punkte)

RUND_SEITEN = {"oben (0°)": 0.0, "vorne (90°)": 90.0, "unten (180°)": 180.0, "hinten (270°)": 270.0}
KASTEN = ("Quadratrohr", "Rechteckrohr", "Flachstahl")
# Quadrat- und Rechteckrohr: Seite nur 0°/90°/180°/270° (Patrick 22.10.2026), Anzeige mit Winkel, gespeichert der
# Flächenname; vorne = rechts von Ende A gesehen (wie die Schweißnaht)
KASTEN_SEITEN = {"0° oben": "oben", "90° vorne": "vorne", "180° unten": "unten", "270° hinten": "hinten"}


class Flaeche:
    """Ebene Fläche des Querschnitts: Strecke p0 -> p1 in (u, v), Normale nach außen; q = 0 in der Mitte, + Richtung
    p1."""

    def __init__(self, name, p0, p1, normale):
        self.name, self.p0, self.p1, self.n = name, p0, p1, normale
        self.breite = math.dist(p0, p1)
        self.mitte = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
        self.dir = ((p1[0] - p0[0]) / (self.breite or 1), (p1[1] - p0[1]) / (self.breite or 1))

    def punkt(self, q):
        return self.mitte[0] + q * self.dir[0], self.mitte[1] + q * self.dir[1]


class Querschnitt:
    """form, B (Breite u), H (Höhe v), r (Rundrohr) oder None, umriss [Polygone (u, v)] für die Ansicht von A,
    flaechen [Flaeche] (Rundrohr leer), umfang = Länge der Abwicklung."""

    def __init__(self, profil):
        form = profil.get("form")
        a, b, t = _z(profil.get("a")) or 40.0, _z(profil.get("b")), _z(profil.get("wand"))
        self.form, self.r, self.flaechen, self.umriss = form, None, [], []
        self.a_waagrecht = False        # Maß a liegt waagrecht (Gehrung "über Höhe" kippt dann über u)
        if form == "Rundrohr":
            self.r = a / 2
            self.B = self.H = a
            n = 72
            self.umriss = [[(self.r * math.sin(2 * math.pi * i / n), self.r * math.cos(2 * math.pi * i / n))
                            for i in range(n)]]
            if 0 < t < self.r:
                ri = self.r - t
                self.umriss.append([(ri * math.sin(2 * math.pi * i / n), ri * math.cos(2 * math.pi * i / n))
                                    for i in range(n)])
            self.umfang = math.pi * a
            return
        norm = normprofile.daten(profil.get("profil_id")) or {}
        tf = _z(norm.get("tf")) or t
        if form in ("L-Profil", "U-Profil", "C-Profil", "I-/H-Träger", "T-Profil"):
            h, br = a, b or a
            t = t or max(1.0, min(h, br) / 10)
            tf = tf or t
            self.B, self.H = br, h
            u1, v1 = br / 2, h / 2
            if form == "L-Profil":       # Schenkel a senkrecht vorne, Schenkel b unten
                self.umriss = [[(u1, v1), (u1, -v1), (-u1, -v1), (-u1, -v1 + t), (u1 - t, -v1 + t), (u1 - t, v1)]]
                self.flaechen = [Flaeche("Schenkel a", (u1, v1), (u1, -v1), (1, 0)),
                                 Flaeche("Schenkel b", (u1, -v1), (-u1, -v1), (0, -1))]
            elif form in ("U-Profil", "C-Profil"):      # Steg senkrecht vorne, Flansche nach hinten
                self.umriss = [[(u1, -v1), (-u1, -v1), (-u1, -v1 + t), (u1 - t, -v1 + t), (u1 - t, v1 - t),
                                (-u1, v1 - t), (-u1, v1), (u1, v1)]]
                self.flaechen = [Flaeche("Flansch oben", (-u1, v1), (u1, v1), (0, 1)),
                                 Flaeche("Steg", (u1, v1), (u1, -v1), (1, 0)),
                                 Flaeche("Flansch unten", (u1, -v1), (-u1, -v1), (0, -1))]
            elif form == "I-/H-Träger":
                s = t / 2
                self.umriss = [[(-u1, v1), (u1, v1), (u1, v1 - tf), (s, v1 - tf), (s, -v1 + tf), (u1, -v1 + tf),
                                (u1, -v1), (-u1, -v1), (-u1, -v1 + tf), (-s, -v1 + tf), (-s, v1 - tf),
                                (-u1, v1 - tf)]]
                self.flaechen = [Flaeche("Flansch oben", (-u1, v1), (u1, v1), (0, 1)),
                                 Flaeche("Steg", (s, v1 - tf), (s, -v1 + tf), (1, 0)),
                                 Flaeche("Flansch unten", (u1, -v1), (-u1, -v1), (0, -1))]
            else:                       # T-Profil: Flansch oben, Steg nach unten
                s = t / 2
                self.umriss = [[(-u1, v1), (u1, v1), (u1, v1 - tf), (s, v1 - tf), (s, -v1), (-s, -v1),
                                (-s, v1 - tf), (-u1, v1 - tf)]]
                self.flaechen = [Flaeche("Flansch", (-u1, v1), (u1, v1), (0, 1)),
                                 Flaeche("Steg", (s, v1 - tf), (s, -v1), (1, 0))]
        elif form == rp_profile.FORM and rp_profile.daten(profil.get("profil_id")):
            # RP-Profil: Kontur der Bibliothek (A = Breite waagrecht, B = Höhe), Seiten wie beim Rechteckrohr
            e = rp_profile.daten(profil.get("profil_id"))
            self.B, self.H, self.a_waagrecht = e["breite"], e["hoehe"], True
            self.umriss = rp_profile.umriss(e)
            u1, v1 = self.B / 2, self.H / 2
            self.flaechen = [Flaeche("oben", (-u1, v1), (u1, v1), (0, 1)),
                             Flaeche("vorne", (u1, v1), (u1, -v1), (1, 0)),
                             Flaeche("unten", (u1, -v1), (-u1, -v1), (0, -1)),
                             Flaeche("hinten", (-u1, -v1), (-u1, v1), (-1, 0))]
        else:
            if form == "Flachstahl":
                self.B, self.H = a, (t or max(1.0, a / 10))
                self.a_waagrecht = True
            else:                       # Quadrat-, Rechteckrohr, unbekannte Form: Breitseite oben (wie die Naht)
                self.B, self.H = max(a, b or a), min(a, b or a)
                self.a_waagrecht = a > (b or a)
            u1, v1 = self.B / 2, self.H / 2
            self.umriss = [[(-u1, v1), (u1, v1), (u1, -v1), (-u1, -v1)]]
            if form in ("Quadratrohr", "Rechteckrohr") and 0 < t < min(u1, v1):
                self.umriss.append([(-u1 + t, v1 - t), (u1 - t, v1 - t), (u1 - t, -v1 + t), (-u1 + t, -v1 + t)])
            self.flaechen = [Flaeche("oben", (-u1, v1), (u1, v1), (0, 1)),
                             Flaeche("vorne", (u1, v1), (u1, -v1), (1, 0)),
                             Flaeche("unten", (u1, -v1), (-u1, -v1), (0, -1)),
                             Flaeche("hinten", (-u1, -v1), (-u1, v1), (-1, 0))]
        self.umfang = sum(f.breite for f in self.flaechen)

    # ------------------------------------------------------------------ Seiten
    def seiten(self):
        """Auswahl für die Spalte Seite: Rundrohr Winkeltexte, sonst Flächennamen."""
        return list(RUND_SEITEN) if self.r else [f.name for f in self.flaechen]

    def flaeche(self, name):
        return next((f for f in self.flaechen if f.name == name), self.flaechen[0] if self.flaechen else None)

    def ausdehnung(self, richtung):
        """Größte Ausdehnung des Umrisses in Richtung (0 = oben, 90 = vorne …) ab der Mitte [mm]."""
        if not hasattr(self, "_aus"):
            self._aus = {}
        if richtung not in self._aus:
            s, c = math.sin(math.radians(richtung)), math.cos(math.radians(richtung))
            self._aus[richtung] = self.r if self.r else max(u * s + v * c for u, v in self.umriss[0])
        return self._aus[richtung]

    # ------------------------------------------------------------------ Abwicklung
    def abwicklung_streifen(self):
        """[(Name, s0, s1)] der Abwicklung von oben nach unten [mm]; Rundrohr in Vierteln ab 315°."""
        if self.r:
            v = self.umfang / 4
            return [(n.split(" ")[0], i * v, (i + 1) * v) for i, n in enumerate(RUND_SEITEN)]
        out, s = [], 0.0
        for f in self.flaechen:
            out.append((f.name, s, s + f.breite))
            s += f.breite
        return out

    def s_zu_uv(self, s):
        """Punkt (u, v) und Normale zur Stelle s der Abwicklung."""
        if self.r:
            phi = math.radians(s / self.umfang * 360 - 45)
            return (self.r * math.sin(phi), self.r * math.cos(phi)), (math.sin(phi), math.cos(phi))
        s0 = 0.0
        for f in self.flaechen:
            if s <= s0 + f.breite or f is self.flaechen[-1]:
                q = min(max(s - s0, 0), f.breite) - f.breite / 2
                return f.punkt(q), f.n
            s0 += f.breite
        return (0.0, 0.0), (0, 1)


def seite_anzeige(qs, name):
    """Text der Spalte Seite zu einem gespeicherten Flächennamen (Quadrat-/Rechteckrohr mit Winkel)."""
    if qs.form in ("Quadratrohr", "Rechteckrohr"):
        return next((t for t, n in KASTEN_SEITEN.items() if n == name), next(iter(KASTEN_SEITEN)))
    return name


def seite_name(qs, text):
    """Gespeicherter Flächenname zum Text der Spalte Seite (Umkehrung von seite_anzeige)."""
    return KASTEN_SEITEN.get(text, text)


def seiten_anzeige(qs):
    """Auswahl der Spalte Seite: Rundrohr Winkeltexte, Quadrat-/Rechteckrohr 0°/90°/180°/270°, sonst Flächennamen."""
    return [seite_anzeige(qs, n) for n in qs.seiten()]


def naht_punkt(qs, winkel):
    """Punkt (u, v) der Schweißnaht am Umriss (Winkel von Ende A gesehen: 0° oben, 90° vorne/rechts) oder None für
    Profile ohne Naht."""
    if winkel is None or not (qs.r or qs.form in ("Quadratrohr", "Rechteckrohr")):
        return None
    t = math.radians(float(winkel))
    dx, dy = math.sin(t), math.cos(t)
    if qs.r:
        return round(qs.r * dx, 6), round(qs.r * dy, 6)
    f = min(qs.B / 2 / abs(dx) if abs(dx) > 1e-9 else 1e9, qs.H / 2 / abs(dy) if abs(dy) > 1e-9 else 1e9)
    return round(dx * f, 6), round(dy * f, 6)


def naht_s(qs, winkel):
    """Stelle s der Schweißnaht in der Abwicklung oder None."""
    pt = naht_punkt(qs, winkel)
    if pt is None:
        return None
    if qs.r:
        return ((float(winkel) + 45) % 360) / 360 * qs.umfang
    s0 = 0.0
    for f in qs.flaechen:
        q = (pt[0] - f.mitte[0]) * f.dir[0] + (pt[1] - f.mitte[1]) * f.dir[1]
        abstand = abs((pt[0] - f.mitte[0]) * f.n[0] + (pt[1] - f.mitte[1]) * f.n[1])
        if abstand < 1e-6 and abs(q) <= f.breite / 2 + 1e-6:
            return s0 + f.breite / 2 + q
        s0 += f.breite
    return None


def kurz(e):
    """Kurzbezeichnung einer Kontur für die Bemaßung der Skizze: Ø 8,5, Senkung Ø 6,6/Ø 12, LL 30 × 10 …"""
    from .rechnen import zahl
    art = e.get("art")
    m = [zahl(_z(e.get(k_)), 2) for k_ in ("d", "D", "l", "b", "h") if _z(e.get(k_))]
    if art == BOHRUNG:
        return f"Ø {zahl(_z(e.get('d')), 2)}" + (f" 3D {zahl(neigung[0], 1)}°/{zahl(neigung[1], 1)}°"
                                                 if (neigung := neigung_3d(e)) else "")
    if art == SENKUNG:
        return f"Ø {zahl(_z(e.get('d')), 2)} / Senk-Ø {zahl(_z(e.get('D')), 2)}"
    if art == LANGLOCH:
        return f"LL {zahl(_z(e.get('l')), 2)} × {zahl(_z(e.get('b')), 2)}"
    if art == RECHTECK:
        return f"Rechteck {zahl(_z(e.get('b')), 2)} × {zahl(_z(e.get('h')), 2)}" + (f" R{zahl(_z(e.get('r')), 2)}"
                                                                             if _z(e.get("r")) else "")
    if art in (SCHLITZ, AUSKLINKUNG):
        return f"{art} {zahl(_z(e.get('l')), 2)} × {zahl(_z(e.get('b')), 2)}"
    if art == POLYGON:
        return "Polygon"
    if _z(e.get("laenge")):
        return f"Kontur L {zahl(_z(e.get('laenge')), 1)}" + (f", Hülle {zahl(_z(e.get('huelle')), 1)}"
                                                            if _z(e.get("huelle")) else "")
    return " × ".join(m) or (art or "")


def neigung_3d(e):
    """Neigung (längs, quer) [°] einer Bohrung in 3D, begrenzt wie die Rechnung (dreid); None ohne 3D oder ungültig."""
    from . import dreid
    if not e.get("d3"):
        return None
    try:
        lg, qu, _, _ = dreid.neigung_begrenzen(dreid.winkel_zahl(e.get("neigung_l")),
                                               dreid.winkel_zahl(e.get("neigung_q")))
    except ValueError:
        return None
    return lg, qu


def winkel_aus_text(text):
    """'vorne (90°)' -> 90, '45' / '45°' -> 45, sonst None."""
    if text in RUND_SEITEN:
        return RUND_SEITEN[text]
    t = str(text or "").replace("°", "").replace(",", ".").strip()
    try:
        return float(t) % 360
    except ValueError:
        return None


def winkel_text(w):
    w = float(w) % 360
    return next((t for t, v in RUND_SEITEN.items() if abs(v - w) < 1e-6), f"{w:g}°")


# ---------------------------------------------------------------------- Enden
def schnitt_x(qs, e, u, v):
    """Wie weit die Schnittkante eines Endes an der Stelle (u, v) des Querschnitts hinter der äußersten Spitze liegt
    [mm, ≥ 0]. e = Eingabe des Endes {winkel, achse, richtung, sattel}."""
    e = e or {}
    sat = _z(e.get("sattel"))
    if sat and qs.r:                # Ausklinkung: Gegenrohr quer (Achse u), Sattel in der Seitenansicht sichtbar
        R = max(sat / 2, qs.r)
        return R - math.sqrt(max(R * R - v * v, 0.0))
    w = abs(_z(e.get("winkel")))
    if not w or w >= 80:
        return 0.0
    th = _richtung(qs, e)
    s, c = math.sin(math.radians(th)), math.cos(math.radians(th))
    ext = qs.ausdehnung(th)
    return max(0.0, (ext - (u * s + v * c)) * math.tan(math.radians(w)))


def _richtung(qs, e):
    """Richtung (0 = oben, 90 = vorne …), in der das Teil an diesem Ende am längsten ist. Mit Angabe (Rund-,
    Quadrat-, Rechteckrohr, Breitseite oben) genau diese; ohne Angabe nach der Gehrungsachse: über Höhe kippt über
    Maß a, über Breite über Maß b, länger auf der Seite oben bzw. vorne."""
    r = e.get("richtung")
    if isinstance(r, (int, float)) and not isinstance(r, bool):
        return float(r) % 360
    if qs.r:
        return 0.0
    ueber_a = not (e.get("achse") or "").endswith("Breite")
    return 90.0 if ueber_a == qs.a_waagrecht else 0.0


def schnittpunkte(qs, w, ansicht):
    """Punkte (u, v) des Außenumrisses auf der Linie Querkoordinate = w (Draufsicht w = u, Seitenansicht w = v)."""
    idx = 0 if ansicht == "oben" else 1
    poly, out = qs.umriss[0], []
    for i in range(len(poly)):
        p0, p1 = poly[i], poly[(i + 1) % len(poly)]
        a, b = p0[idx], p1[idx]
        if min(a, b) - 1e-9 <= w <= max(a, b) + 1e-9:
            if abs(b - a) < 1e-9:
                out += [p0, p1]
            else:
                f = (w - a) / (b - a)
                out.append((p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f))
    return out


def silhouette(qs, e_a, e_b, L, ansicht, n=80):
    """Umriss des Teils in einer Ansicht ('oben': quer = u, Blick von oben; 'vorne': quer = v, Blick auf vorne):
    [(w, a_aussen, a_sicht, a_hinten, b_aussen, b_sicht, b_hinten)] je Streifen der Querrichtung. aussen = äußerste
    Kante (Umriss), sicht = Kante der vordersten Fläche (dazwischen sieht man die Schnittfläche), hinten = Kante der
    hintersten Fläche (verdeckt). Werte für Ende B als x ab Anfang. Die Schnittkanten sind linear (Gehrung) bzw.
    am Kreis (Ausklinkung), daher genügen die Schnittpunkte mit dem Umriss."""
    idx, tiefe = (0, 1) if ansicht == "oben" else (1, 0)
    poly = qs.umriss[0]
    lo, hi = min(p[idx] for p in poly), max(p[idx] for p in poly)
    out = []
    for i in range(n + 1):
        w = lo + (hi - lo) * i / n
        pk = schnittpunkte(qs, min(max(w, lo + 1e-7), hi - 1e-7), ansicht) or [min(poly, key=lambda p: abs(p[idx] - w))]
        vorn, hinten = max(pk, key=lambda p: p[tiefe]), min(pk, key=lambda p: p[tiefe])
        xa = [schnitt_x(qs, e_a, *p) for p in pk]
        xb = [schnitt_x(qs, e_b, *p) for p in pk]
        out.append((w, min(xa), schnitt_x(qs, e_a, *vorn), schnitt_x(qs, e_a, *hinten),
                    L - min(xb), L - schnitt_x(qs, e_b, *vorn), L - schnitt_x(qs, e_b, *hinten)))
    return out


def tiefe_oben(qs, w, ansicht):
    """Vorderste Stelle des Querschnitts (größtes v in der Draufsicht, größtes u in der Seitenansicht) bei der
    Querkoordinate w, aus den Kanten des Außenumrisses; None außerhalb."""
    idx, tiefe = (0, 1) if ansicht == "oben" else (1, 0)
    poly, best = qs.umriss[0], None
    for i in range(len(poly)):
        p0, p1 = poly[i], poly[(i + 1) % len(poly)]
        a, b = p0[idx], p1[idx]
        if min(a, b) - 1e-9 <= w <= max(a, b) + 1e-9:
            if abs(b - a) < 1e-9:
                d = max(p0[tiefe], p1[tiefe])
            else:
                d = p0[tiefe] + (p1[tiefe] - p0[tiefe]) * (w - a) / (b - a)
            best = d if best is None else max(best, d)
    return best


def kanten(qs, ansicht):
    """Längskanten des Querschnitts in einer Ansicht: [(w, sichtbar)] (ohne die Außenkanten). Sichtbar, wenn die
    vorderste Fläche dort springt (Stufe), sonst verdeckt."""
    if qs.r:
        return []
    idx = 0 if ansicht == "oben" else 1
    werte = sorted({round(p[idx], 4) for p in qs.umriss[0]})
    lo, hi = werte[0], werte[-1]
    out = []
    for w in werte[1:-1]:
        d = 1e-3 * max(hi - lo, 1)
        t1, t2 = tiefe_oben(qs, w - d, ansicht), tiefe_oben(qs, w + d, ansicht)
        out.append((w, t1 is not None and t2 is not None and abs(t1 - t2) > 1e-6))
    for poly in qs.umriss[1:]:          # Innenwand von Rohren
        ws = sorted({round(p[idx], 4) for p in poly})
        out += [(ws[0], False), (ws[-1], False)]
    return out


def ende_abwicklung(qs, e, n=120):
    """Schnittlinie eines Endes in der Abwicklung: [(s, Abstand von der Spitze)]."""
    out = []
    for i in range(n + 1):
        s = qs.umfang * i / n
        (u, v), _ = qs.s_zu_uv(s)
        out.append((s, schnitt_x(qs, e, u, v)))
    return out


# ---------------------------------------------------------------------- Konturen
def umriss_kontur(e, n=36):
    """Form einer Kontur als geschlossener Linienzug (dx längs, dq quer) um ihre Mitte [mm]; None ohne Maße.
    Langloch und Rechteck liegen längs (Länge bzw. Breite b in x), quer=True dreht sie um 90°."""
    art = e.get("art")
    try:
        _, hk, _ = kontur(dict(e, anzahl=1))
    except ValueError:
        return None
    if art in (BOHRUNG, SENKUNG):
        r = _z(e.get("d")) / 2
        # schräge Bohrung (3D): Austritt auf der Wand als Ellipse, gestreckt um 1/cos der Neigung längs bzw. quer
        nl, nq = (neigung_3d(e) if art == BOHRUNG else None) or (0, 0)
        fx, fq = 1 / math.cos(math.radians(nl)), 1 / math.cos(math.radians(nq))
        pts = [(fx * r * math.cos(2 * math.pi * i / n), fq * r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    elif art == LANGLOCH:
        l_, b_ = _z(e.get("l")), _z(e.get("b"))
        r, m = b_ / 2, (l_ - b_) / 2
        pts = [(m + r * math.cos(a), r * math.sin(a)) for a in _bogen(-90, 90, n // 2)]
        pts += [(-m + r * math.cos(a), r * math.sin(a)) for a in _bogen(90, 270, n // 2)]
    elif art in (RECHTECK, SCHLITZ, AUSKLINKUNG):
        b_, h_ = (_z(e.get("b")), _z(e.get("h"))) if art == RECHTECK else (_z(e.get("l")), _z(e.get("b")))
        r = _z(e.get("r")) if art in (RECHTECK, AUSKLINKUNG) else 0.0
        pts = _rechteck(b_, h_, r)
    elif art == POLYGON:
        pk = punkte(e.get("punkte"))
        cx = (max(x for x, _ in pk) + min(x for x, _ in pk)) / 2
        cy = (max(y for _, y in pk) + min(y for _, y in pk)) / 2
        pts = [(x - cx, y - cy) for x, y in pk]
    else:                           # sonstige Kontur: Kreis mit dem Hüllmaß (nur Lage)
        r = (hk if hk and hk < OHNE_HUELLE else 20.0) / 2
        pts = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    if e.get("quer"):
        pts = [(-q, x) for x, q in pts]
    return pts


def _bogen(a0, a1, n):
    return [math.radians(a0 + (a1 - a0) * i / max(n - 1, 1)) for i in range(n)]


def _rechteck(b, h, r, n=6):
    r = min(r, b / 2, h / 2)
    if r <= 0:
        return [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)]
    pts = []
    for cx, cy, a0 in ((b / 2 - r, -h / 2 + r, -90), (b / 2 - r, h / 2 - r, 0), (-b / 2 + r, h / 2 - r, 90),
                       (-b / 2 + r, -h / 2 + r, 180)):
        pts += [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in _bogen(a0, a0 + 90, n)]
    return pts


def laenge_x(e):
    """Ausdehnung einer Kontur in x [mm] (für Schlitze am Ende)."""
    pts = umriss_kontur(e)
    return (max(x for x, _ in pts) - min(x for x, _ in pts)) if pts else 0.0


def lagen(konturen, L):
    """Jede Kontur einzeln mit Lage: [dict(zeile, nr, art, x, eingabe)]. x aus der Eingabe (Mitte der ersten),
    Muster mit Abstand längs (x + i × Abstand); ohne Lage gleichmäßig über die Länge verteilt (wie bisher), Schlitze
    und Ausklinkungen ohne Lage am Ende A."""
    liste = []
    for z, e in enumerate(konturen or ()):
        try:
            _, hk, n = kontur(e)
        except ValueError:
            continue
        x0, ab = e.get("x"), _z(e.get("abstand"))
        if x0 is None and e.get("art") in (SCHLITZ, AUSKLINKUNG):
            x0 = laenge_x(e) / 2
        for i in range(n):
            x = None if x0 is None else (x0 + i * ab if ab else x0)
            liste.append(dict(zeile=z, nr=i, art=e.get("art"), x=x, huelle=hk, eingabe=e))
    frei = [d for d in liste if d["x"] is None]
    for j, d in enumerate(frei):
        d["x"] = L * (j + 1) / (len(frei) + 1)
        d["verteilt"] = True
    return liste


def platzieren(qs, d):
    """3D-Linienzug [(x, u, v)] einer Kontur und ihre Normale (u, v) in der Mitte."""
    e = d["eingabe"]
    pts = umriss_kontur(e) or [(0.0, 0.0)]
    if qs.r:
        w = winkel_aus_text(e.get("seite"))
        phi = math.radians(w if w is not None else 0.0)
        out = [(d["x"] + dx, qs.r * math.sin(phi + dq / qs.r), qs.r * math.cos(phi + dq / qs.r)) for dx, dq in pts]
        return out, (math.sin(phi), math.cos(phi))
    f = qs.flaeche(e.get("seite"))
    if f is None:
        return [(d["x"] + dx, dq, qs.H / 2) for dx, dq in pts], (0, 1)
    q = _z(e.get("q"))
    out = []
    for dx, dq in pts:
        u, v = f.punkt(q + dq)
        out.append((d["x"] + dx, u, v))
    return out, f.n


def s_lage(qs, e, dq=0.0):
    """Stelle s der Abwicklung für eine Kontur (Mitte + dq quer)."""
    if qs.r:
        w = winkel_aus_text(e.get("seite"))
        w = (w if w is not None else 0.0) + 45
        return (w % 360) / 360 * qs.umfang + dq
    s0 = 0.0
    f = qs.flaeche(e.get("seite"))
    for g in qs.flaechen:
        if g is f:
            return s0 + g.breite / 2 + _z(e.get("q")) + dq
        s0 += g.breite
    return dq


def s_zu_seite(qs, s):
    """Umkehrung von s_lage: (Seite, q) bzw. für Rundrohr (Winkeltext, 0)."""
    if qs.r:
        return winkel_text(round((s / qs.umfang * 360 - 45) % 360, 1)), 0.0
    s0 = 0.0
    for f in qs.flaechen:
        if s < s0 + f.breite or f is qs.flaechen[-1]:
            q = min(max(s - s0, 0.0), f.breite) - f.breite / 2
            return f.name, round(q, 1)
        s0 += f.breite
    return None, 0.0


def sichtbar(normale, ansicht):
    """Anteil der Normale zur Blickrichtung: > 0 sichtbar, < 0 verdeckt (Rückseite)."""
    return normale[1] if ansicht == "oben" else normale[0]
