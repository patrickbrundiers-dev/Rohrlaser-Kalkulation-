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
import bisect
import math

from . import durchdringung as dd, normprofile, optimierung as opt, rp_profile
from .schneidweg import (AUSKLINKUNG, BOHRUNG, FLOWDRILL, GRAVUR, GRAVUREN, LANGLOCH, LOCHFELD, OHNE_HUELLE, POLYGON,
                         RECHTECK, SCHLITZ, SENKUNG, SONDERKONTUR, TEXT_GRAVUR, _z, kontur, punkte)

DREH_OHNE = (BOHRUNG, SENKUNG, FLOWDRILL, GRAVUR)     # rund bzw. Kreuz: Drehwinkel ohne Wirkung
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
        self.radius, self.wand = 0.0, t     # Außenradius (Quadrat-/Rechteckrohr), nur für Bilder (umriss_rund)
        self.dicke = 0.0                # offene Profile, Flachstahl: größte Wanddicke (Gehrung in 2D, schnitt_x)
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
            self.dicke = max(t, tf)
            u1, v1 = br / 2, h / 2
            if form == "L-Profil":       # Schenkel a senkrecht vorne, Schenkel b unten
                self.umriss = [[(u1, v1), (u1, -v1), (-u1, -v1), (-u1, -v1 + t), (u1 - t, -v1 + t), (u1 - t, v1)]]
                self.flaechen = [Flaeche("Schenkel a", (u1, v1), (u1, -v1), (1, 0)),
                                 Flaeche("Schenkel b", (u1, -v1), (-u1, -v1), (0, -1))]
            elif form == "C-Profil":    # wie U, Abkantung (Lippe) nach innen: aus der STEP, sonst geschätzt
                c = _z(profil.get("lippe")) or min(br / 3, h / 4)
                c = max(t, min(c, v1))
                self.umriss = [[(u1, -v1), (-u1, -v1), (-u1, -v1 + c), (-u1 + t, -v1 + c), (-u1 + t, -v1 + t),
                                (u1 - t, -v1 + t), (u1 - t, v1 - t), (-u1 + t, v1 - t), (-u1 + t, v1 - c),
                                (-u1, v1 - c), (-u1, v1), (u1, v1)]]
                self.flaechen = [Flaeche("Flansch oben", (-u1, v1), (u1, v1), (0, 1)),
                                 Flaeche("Steg", (u1, v1), (u1, -v1), (1, 0)),
                                 Flaeche("Flansch unten", (u1, -v1), (-u1, -v1), (0, -1))]
            elif form == "U-Profil":    # Steg senkrecht vorne, Flansche nach hinten
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
                self.dicke = self.H
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
        self.radius = opt.aussenradius(form, a, b, t, profil.get("r_aussen")) if form in opt.RADIUS_FORMEN else 0.0

    def umriss_rund(self, teile=6):
        """Umriss für Bilder (3D, Ansicht von A): Quadrat-/Rechteckrohr mit Außenradius (innen Radius − Wand), je
        Ecke teile Stücke; außen und innen gleich viele Punkte. Sonst umriss. Die Rechnung (Konturlage, Schnittkanten)
        bleibt beim scharfkantigen umriss."""
        if not self.radius or self.form not in opt.RADIUS_FORMEN:
            return self.umriss
        u1, v1 = self.B / 2, self.H / 2

        def ecken(du, dv, r):
            pts = []
            for cu, cv, w0 in ((-du + r, dv - r, 90), (du - r, dv - r, 0), (du - r, -dv + r, -90), (-du + r, -dv + r, -180)):
                for k in range(teile + 1):
                    w = math.radians(w0 + 90 - 90 * k / teile)
                    pts.append((cu + r * math.cos(w), cv + r * math.sin(w)))
            return pts
        out = [ecken(u1, v1, self.radius)]
        if len(self.umriss) > 1 and 0 < self.wand < min(u1, v1):
            out.append(ecken(u1 - self.wand, v1 - self.wand, max(0.0, self.radius - self.wand)))
        return out

    # ------------------------------------------------------------------ Seiten
    def seiten(self):
        """Auswahl für die Spalte Seite: Rundrohr Winkeltexte, sonst Flächennamen."""
        return list(RUND_SEITEN) if self.r else [f.name for f in self.flaechen]

    def flaeche(self, name):
        return next((f for f in self.flaechen if f.name == name), self.flaechen[0] if self.flaechen else None)

    def ausdehnung(self, richtung):
        """Größte Ausdehnung des Umrisses in Richtung (0 = oben, 90 = vorne …) ab der Mitte [mm]. Quadrat-/
        Rechteckrohr mit Außenradius: bis zur gerundeten Ecke (dort liegt die Spitze eines schrägen Schnitts über die
        Ecke wie in der STEP, nicht an der scharfen Ecke der Skizze)."""
        if not hasattr(self, "_aus"):
            self._aus = {}
        if richtung not in self._aus:
            s, c = math.sin(math.radians(richtung)), math.cos(math.radians(richtung))
            r = self.radius if self.form in ("Quadratrohr", "Rechteckrohr") else 0.0
            if r and not self.r and self.flaechen and 0 < r <= min(self.B, self.H) / 2:
                self._aus[richtung] = (self.B / 2 - r) * abs(s) + (self.H / 2 - r) * abs(c) + r
            else:
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
    if art == FLOWDRILL:
        return f"Flowdrill Ø {zahl(_z(e.get('d')), 2)}" + (f" {e['gewinde']}" if e.get("gewinde") else "")
    if art == LANGLOCH:
        return f"LL {zahl(_z(e.get('l')), 2)} × {zahl(_z(e.get('b')), 2)}"
    if art == RECHTECK:
        return f"Rechteck {zahl(_z(e.get('b')), 2)} × {zahl(_z(e.get('h')), 2)}" + (f" R{zahl(_z(e.get('r')), 2)}"
                                                                             if _z(e.get("r")) else "")
    if art in (SCHLITZ, AUSKLINKUNG):
        return f"{art} {zahl(_z(e.get('l')), 2)} × {zahl(_z(e.get('b')), 2)}"
    if art == POLYGON:
        return "Polygon"
    if art == SONDERKONTUR:
        return f"Sonderkontur L {zahl(_z(e.get('laenge')), 1)}" + (
            f" über {len(e['waende'])} Wände" if len(e.get("waende") or ()) > 1 else "")
    if art == TEXT_GRAVUR:
        return f"Text-Gravur „{e.get('text') or ''}“ h {zahl(_z(e.get('hoehe')), 1)}"
    if art == GRAVUR:
        return f"Gravur {zahl(_z(e.get('laenge')), 1)}" + (f", {zahl(_z(e.get('tiefe')), 2)} tief"
                                                          if _z(e.get("tiefe")) else "")
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
def schnitt_x(qs, e, u, v, aussen=False):
    """Wie weit die Schnittkante eines Endes an der Stelle (u, v) des Querschnitts hinter der äußersten Spitze liegt
    [mm, ≥ 0]. e = Eingabe des Endes {winkel, achse, richtung, sattel | gegen} (Gegenrohr: durchdringung).
    Gehrung in 2D (ohne 'd3'): Innenkante maßhaltig, die lange Seite wird kürzer (innen_lage); 'aussen_mass' (STEP,
    Außenkante auf der Gehrungsfläche) bzw. aussen=True: die Außenkante auf der Fläche (Schnittlänge wie bisher)."""
    e = e or {}
    g = dd.gegen_lesen(e)
    if g and (qs.r or e.get("gegen")):      # Gegenrohr (auch die alte Ausklinkung auf Rundrohr)
        try:
            return dd.schnitt_x(qs, g, u, v)
        except (ValueError, ZeroDivisionError):
            return 0.0
    w = abs(_z(e.get("winkel")))
    if not w and e.get("umriss"):           # komplexes Ende aus dem STEP-Import: gemessener Verlauf
        um = _ende_umriss_merken(qs, e["umriss"])
        return um(uv_zu_s(qs, u, v)) if um else 0.0
    if not w or w >= 80:
        return 0.0
    th = _richtung(qs, e)
    s, c = math.sin(math.radians(th)), math.cos(math.radians(th))
    ext = qs.ausdehnung(th)
    tw = math.tan(math.radians(w))
    x = max(0.0, (ext - (u * s + v * c)) * tw)
    # 'aussen_mass' nur für Gehrungen, die schon in der STEP 2D (90° zur Oberfläche) sind; eine ebene STEP-Gehrung
    # ('schwenk' ab 0,5°, auch ältere Importe) wird in 2D wie gefertigt kürzer (Patrick 28.10.2026, Variante a)
    if not aussen and not e.get("d3") and not (e.get("aussen_mass") and _z(e.get("schwenk")) < 0.5):
        if (qs.wand or 0) > 0 and (qs.r or qs.form in ("Quadratrohr", "Rechteckrohr")):
            x = max(x, (ext - innen_lage(qs, u, v, s, c)) * tw, qs.wand * tw)
        elif qs.dicke > 0 and not qs.r and len(qs.umriss) == 1:
            x = max(x, (ext - wand_lage_offen(qs, u, v, s, c)) * tw)
    return x


def wand_lage_offen(qs, u, v, s, c):
    """Gehrung in 2D an offenen Profilen und Flachstahl (Patrick 28.10.2026, wie innen_lage beim Rohr): der Strahl
    steht senkrecht zur Fläche des Schenkels, die ganze Dicke unter dem Punkt (u, v) wird an derselben Stelle
    geschnitten. Ergebnis: kleinste Lage in Richtung (s, c) der langen Seite über diese Dicke, also die Seite, die
    sonst über die Gehrungsfläche ragen würde (der Schenkel wird dort um Dicke · tan(Winkel) kürzer). Ein Punkt im
    Eckblock gehört zu beiden Schenkeln (wie die Ecken beim Rohr); Punkte außerhalb der Schenkel (Abkantung des
    C-Profils) bleiben auf der Fläche."""
    lage = u * s + v * c
    for (nu, nv), d0, d1, q0, q1 in _schenkel(qs):
        tief = u * nu + v * nv          # Lage quer zur Wand (außen d1, innen d0)
        quer = -u * nv + v * nu         # Lage entlang der Wand
        if d0 - 1e-6 <= tief <= d1 + 1e-6 and q0 - 1e-6 <= quer <= q1 + 1e-6:
            d = (d1 - tief, d0 - tief)          # bis zur Außen- und Innenseite
            lage = min([lage] + [(u + k * nu) * s + (v + k * nv) * c for k in d])
    return lage


def _schenkel(qs):
    """Wände eines offenen Profils aus seinen Flächen: [(Normale, d0 innen, d1 außen, q0, q1)] je Fläche, die länger
    als die Dicke ist; Dicke bis zur Gegenseite (Strahl von der Flächenmitte), höchstens qs.dicke."""
    if getattr(qs, "_schenkel", None) is not None:
        return qs._schenkel
    poly, out = qs.umriss[0], []
    n = len(poly)
    for f in qs.flaechen:
        if f.breite <= qs.dicke * 1.05:
            continue
        nu, nv = f.n
        tiefe = qs.dicke
        for k in range(n):
            (a0, b0), (a1, b1) = poly[k], poly[(k + 1) % n]
            ea, eb = a1 - a0, b1 - b0
            det = nu * eb - nv * ea         # Mitte − t·n = (a0, b0) + g·e  ->  t, g
            if abs(det) < 1e-12:
                continue
            t = (-(a0 - f.mitte[0]) * eb + (b0 - f.mitte[1]) * ea) / det
            g = (-nu * (b0 - f.mitte[1]) + nv * (a0 - f.mitte[0])) / det
            if 1e-6 < t < tiefe and -1e-9 <= g <= 1 + 1e-9:
                tiefe = t
        d1 = f.mitte[0] * nu + f.mitte[1] * nv
        q = sorted(-p[0] * nv + p[1] * nu for p in (f.p0, f.p1))
        out.append(((nu, nv), d1 - tiefe, d1, q[0], q[1]))
    qs._schenkel = out
    return out


def innen_lage(qs, u, v, s, c):
    """Gehrung in 2D (Strahl senkrecht zur Oberfläche, Patrick 27.10.2026): Lage des Innenpunkts unter (u, v) in
    Richtung (s, c) der langen Seite. Die Innenkante ist maßhaltig, wo sie sonst über die Gehrungsfläche ragen würde:
    die Wand, die zur langen Seite zeigt, wird um Wand · tan(Winkel) kürzer geschnitten (am Eckradius entsprechend
    der Rundung); an der kurzen Seite bleibt die Außenkante (innen liegt dort ohnehin hinter der Fläche). Punkt der
    Skizze auf der Rundung wie die 3D-Ansicht (rund_ort); an den Ecken hält schnitt_x zusätzlich Wand · tan(Winkel)
    ein (der Eckblock gehört zu beiden Wänden). Nur geschlossene Rohre."""
    t = qs.wand or 0.0
    if qs.r:
        lg = math.hypot(u, v)
        if lg < 1e-9:
            return u * s + v * c
        return (u - t * u / lg) * s + (v - t * v / lg) * c
    ur, vr, n = rund_ort(qs, u, v)
    if n is None or math.hypot(ur - u, vr - v) > 1e-6:      # auf einer Fläche (auch Punkt der scharfkantigen Skizze)
        ur, vr = u, v
        _, n = qs.s_zu_uv(uv_zu_s(qs, u, v))
    return (ur - t * n[0]) * s + (vr - t * n[1]) * c


def _richtung(qs, e):
    """Richtung (0 = oben, 90 = vorne …), in der das Teil an diesem Ende am längsten ist. Mit Angabe (Rund-,
    Quadrat-, Rechteckrohr, Breitseite oben) genau diese; ohne Angabe nach der Gehrungsachse: über Höhe kippt über
    Maß a, über Breite über Maß b, länger auf der Seite oben bzw. vorne."""
    r = e.get("richtung")
    if isinstance(r, (int, float)) and not isinstance(r, bool):
        return float(r) % 360
    if qs.r:
        return 0.0
    if e.get("achse") == "über Höhe und Breite":     # zweiachsig: Richtung der steilsten Neigung
        th, tb = (math.tan(math.radians(abs(_z(e.get(k))))) for k in ("winkel_h", "winkel_b"))
        ra, rb = (90.0, 0.0) if qs.a_waagrecht else (0.0, 90.0)
        x = th * math.sin(math.radians(ra)) + tb * math.sin(math.radians(rb))
        y = th * math.cos(math.radians(ra)) + tb * math.cos(math.radians(rb))
        return math.degrees(math.atan2(x, y)) % 360
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
    ws = [lo + (hi - lo) * i / n for i in range(n + 1)]
    for e in (e_a, e_b):            # Knicke eines gemessenen Endes (Ausklinkung): Stufe genau, nicht schräg
        um = _ende_umriss_merken(qs, e["umriss"]) if e and e.get("umriss") and not _z(e.get("winkel")) else None
        for st in getattr(um, "stellen", ()) if um else ():
            w0 = qs.s_zu_uv(st % qs.umfang)[0][idx]
            ws += [w for w in (w0 - 1e-4, w0 + 1e-4) if lo < w < hi]
    out = []
    for w in sorted(set(ws)):
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
    """Schnittlinie eines Endes in der Abwicklung: [(s, Abstand von der Spitze)]. Mit umriss (komplexes Ende aus dem
    STEP-Import: [[s, Abstand vom Ende]]) der gemessene Verlauf. Nasen einer Steckverbindung (wie rohr3d.netz): der
    Schnitt liegt um ihre Länge weiter innen, die Nasen (Breite am Umfang) ragen bis zum Teilende."""
    um = _ende_umriss(qs, (e or {}).get("umriss"))

    def basis(s):
        if um:
            return um(s)
        (u, v), _ = qs.s_zu_uv(s)
        return schnitt_x(qs, e, u, v)
    stellen = [qs.umfang * i / n for i in range(n + 1)]
    if um:                              # Knicke des gemessenen Verlaufs genau treffen
        stellen = sorted(set(stellen + [x for x in um.stellen if 0 <= x <= qs.umfang]))
    nasen = _nasen_abwicklung(qs, e)
    if not nasen:
        return [(s, basis(s)) for s in stellen]
    lg, bereiche = nasen

    def in_nase(s):
        return any(min(abs(s - m), qs.umfang - abs(s - m)) < h - 1e-9 for m, h in bereiche)
    for m, h in bereiche:               # Kanten der Nasen als Stufe
        for k in (m - h, m + h):
            k %= qs.umfang
            stellen += [max(k - 1e-6, 0.0), min(k + 1e-6, qs.umfang)]
    return [(s, basis(s) + (0.0 if in_nase(s) else lg)) for s in sorted(set(stellen))]


def _nasen_abwicklung(qs, e):
    """(Nasenlänge, [(Mitte s, halbe Breite am Umfang)]) der Nasen am Ende e oder None."""
    from .rohr3d import nasen_lage
    try:
        n = nasen_lage(e or {}, qs)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    if not n:
        return None
    lg, winkel, h = n
    mitten = [naht_s(qs, w) for w in winkel]
    bereiche = [(m, h) for m in mitten if m is not None]
    return (lg, bereiche) if bereiche and lg > 0 else None


_umriss_merker = {}


def _ende_umriss_merken(qs, umriss):
    """_ende_umriss für viele Punkte desselben Endes (3D: je Punkt des Umrisses einer) nur einmal aufbauen."""
    k = (id(umriss), round(qs.umfang, 6))
    m = _umriss_merker.get(k)
    if m is None or m[0] is not umriss:
        if len(_umriss_merker) > 64:
            _umriss_merker.clear()
        m = _umriss_merker[k] = (umriss, _ende_umriss(qs, umriss))
    return m[1]


def uv_zu_s(qs, u, v):
    """Stelle s der Abwicklung zum Punkt (u, v) des Außenumrisses (Umkehrung von s_zu_uv). Ein Punkt auf dem Bogen
    einer Ecke mit Radius geht radial auf die scharfkantige Ecke (Umkehrung von rund_ort)."""
    if qs.r:
        return (math.degrees(math.atan2(u, v)) + 45) % 360 / 360 * qs.umfang
    if not qs.flaechen:
        return 0.0
    r = qs.radius if qs.form in opt.RADIUS_FORMEN else 0.0
    if r:
        cu, cv = qs.B / 2 - r, qs.H / 2 - r
        if abs(u) > cu + 1e-9 and abs(v) > cv + 1e-9:
            mu, mv = math.copysign(cu, u), math.copysign(cv, v)
            lg = math.hypot(u - mu, v - mv) or 1.0
            nu, nv = (u - mu) / lg, (v - mv) / lg
            f = r / max(abs(nu), abs(nv))
            u, v = mu + f * nu, mv + f * nv
    beste, s0 = None, 0.0
    for f in qs.flaechen:
        t = min(max((u - f.p0[0]) * f.dir[0] + (v - f.p0[1]) * f.dir[1], 0.0), f.breite)
        d = math.hypot(f.p0[0] + t * f.dir[0] - u, f.p0[1] + t * f.dir[1] - v)
        if beste is None or d < beste[0] - 1e-9:
            beste = (d, s0 + t)
        s0 += f.breite
    return beste[1] % qs.umfang


def _ende_umriss(qs, umriss):
    """Funktion s -> Abstand vom Ende aus dem gemessenen Umriss eines Endes (linear, über die Naht 0/Umfang
    hinweg), oder None."""
    try:
        pk = sorted((float(a) % qs.umfang, max(float(b), 0.0)) for a, b in umriss or ())
    except (TypeError, ValueError):
        return None
    if len(pk) < 2:
        return None
    pk = [(pk[-1][0] - qs.umfang, pk[-1][1])] + pk + [(pk[0][0] + qs.umfang, pk[0][1])]
    ss = [p[0] for p in pk]

    def d(s):
        s %= qs.umfang
        i = min(max(bisect.bisect_right(ss, s), 1), len(pk) - 1)
        (s0, d0), (s1, d1) = pk[i - 1], pk[i]
        return d0 + (d1 - d0) * ((s - s0) / (s1 - s0) if s1 > s0 else 0)
    d.stellen = [p[0] for p in pk[1:-1]]
    return d


# ---------------------------------------------------------------------- Konturen
def umriss_kontur(e, n=36):
    """Form einer Kontur als geschlossener Linienzug (dx längs, dq quer) um ihre Mitte [mm]; None ohne Maße.
    Langloch und Rechteck liegen längs (Länge bzw. Breite b in x), quer=True dreht sie um 90°."""
    art = e.get("art")
    try:
        _, hk, _ = kontur(dict(e, anzahl=1))
    except ValueError:
        return None
    if len(e.get("umriss") or ()) >= 3:     # echter Umriss (Sonderkontur, Gravur aus dem STEP-Import)
        try:
            return _dicht([(float(dx), float(dq)) for dx, dq in e["umriss"]])
        except (TypeError, ValueError):
            pass
    if art in GRAVUREN:                 # ohne Umriss: kleines Kreuz an der Stelle (Text-Gravur: Hüllrechteck)
        if art == TEXT_GRAVUR:
            from . import gravur_text
            b, h = gravur_text.masse(e.get("text"), _z(e.get("hoehe")))
            return [(-b / 2, -h / 2), (b / 2, -h / 2), (b / 2, h / 2), (-b / 2, h / 2)] if b and h else None
        return [(-3.0, 0.0), (3.0, 0.0), (0.0, 0.0), (0.0, 3.0), (0.0, -3.0), (0.0, 0.0)]
    if art in (BOHRUNG, SENKUNG, FLOWDRILL):
        r = _z(e.get("d")) / 2
        # schräge Bohrung (3D): Austritt auf der Wand als Ellipse, gestreckt um 1/cos der Neigung längs bzw. quer
        nl, nq = (neigung_3d(e) if art == BOHRUNG else None) or (0, 0)
        fx, fq = 1 / math.cos(math.radians(nl)), 1 / math.cos(math.radians(nq))
        pts = [(fx * r * math.cos(2 * math.pi * i / n), fq * r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    elif art == LOCHFELD and _z(e.get("lang")) <= _z(e.get("d")):     # ein Loch des Felds (lagen: _dx/_dq)
        r = _z(e.get("d")) / 2
        pts = [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    elif art in (LANGLOCH, LOCHFELD):
        l_, b_ = _z(e.get("l" if art == LANGLOCH else "lang")), _z(e.get("b" if art == LANGLOCH else "d"))
        r, m = b_ / 2, (l_ - b_) / 2
        pts = [(m + r * math.cos(a), r * math.sin(a)) for a in _bogen(-90, 90, n // 2)]
        pts += [(-m + r * math.cos(a), r * math.sin(a)) for a in _bogen(90, 270, n // 2)]
    elif art in (RECHTECK, SCHLITZ, AUSKLINKUNG):
        b_, h_ = (_z(e.get("b")), _z(e.get("h"))) if art == RECHTECK else (_z(e.get("l")), _z(e.get("b")))
        r = _z(e.get("r")) if art in (RECHTECK, AUSKLINKUNG) else 0.0
        f = _z(e.get("fase")) if art in (RECHTECK, AUSKLINKUNG) else 0.0
        pts = _rechteck_fase(b_, h_, f) if f else _rechteck(b_, h_, r)
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
    if e.get("_dx") or e.get("_dq"):    # Loch eines Lochfelds: Lage in der Reihe (dreht mit dem Feld)
        pts = [(x + _z(e.get("_dx")), q + _z(e.get("_dq"))) for x, q in pts]
    w = _z(e.get("drehung"))
    if w and art not in DREH_OHNE:      # Drehwinkel der Kontur auf der Fläche (+ = gegen den Uhrzeiger von außen)
        c, s_ = math.cos(math.radians(w)), math.sin(math.radians(w))
        pts = [(x * c - q * s_, x * s_ + q * c) for x, q in pts]
    if e.get("spiegeln"):               # Gegenwand einer durchgehenden Kontur: quer gespiegelt
        pts = [(x, -q) for x, q in pts]
    return pts


def muendung_ende(e, pts):
    """Kontur e mit offener Mündung am Ende (STEP-Import: Schlitz o. ä., der in das Ende läuft, 'muendung'): Index
    des letzten Punkts ihres Umrisses in pts (Umriss unterteilt, geschlossen); die Punkte danach liegen auf der
    Schließkante über der Mündung und werden nicht als Linie gezeichnet. None ohne Mündung."""
    if not e.get("muendung") or len(e.get("umriss") or ()) < 3 or not pts:
        return None
    try:
        lx, lq = (float(c) for c in e["umriss"][-1])
    except (TypeError, ValueError):
        return None
    for i in range(len(pts) - 1, -1, -1):
        if abs(pts[i][0] - lx) < 1e-6 and abs(pts[i][1] - lq) < 1e-6:
            return i
    return None


def ohne_muendung(qs, linie, muend):
    """Schnittlinie eines Endes in der Abwicklung [(s, Abstand)] ohne die Stücke in den Mündungen [s von, s bis] der
    Ausflüge (STEP-Import: Schlitz o. ä., der in das Ende läuft): Liste der Teilstücke."""
    if not muend:
        return [list(linie)]

    def offen(s):
        return any(0 < (s - a) % qs.umfang < (b - a) % qs.umfang for a, b in muend)
    out, teil = [], []
    for i, p in enumerate(linie):
        if i and offen((p[0] + linie[i - 1][0]) / 2):
            if len(teil) > 1:
                out.append(teil)
            teil = [p]
            continue
        teil.append(p)
    if len(teil) > 1:
        out.append(teil)
    return out


def _dicht(pts, schritt=3.0):
    """Geschlossenen Linienzug so unterteilen, dass kein Stück länger als schritt [mm] ist (damit ein Umriss über
    Kanten und Rundungen des Querschnitts der Oberfläche folgt)."""
    out = []
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        n = max(1, math.ceil(math.dist(a, b) / schritt))
        out += [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n)]
    return out


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


def _rechteck_fase(b, h, f):
    """Rechteck b × h um die Mitte mit gefasten Ecken (je Kante f von der Ecke)."""
    f = min(f, b / 2, h / 2)
    u, v = b / 2, h / 2
    return [(-u + f, -v), (u - f, -v), (u, -v + f), (u, v - f), (u - f, v), (-u + f, v), (-u, v - f), (-u, -v + f)]


def lochfeld(e):
    """Löcher eines Lochfelds: [(dx längs ab der ersten Spalte, dq quer zur Feldmitte)] je Loch (Reihen quer mit
    Teilung quer um die Mitte, jede 2. Reihe bei versetzt um die halbe Teilung längs verschoben)."""
    n, reihen = int(_z(e.get("anzahl")) or 1), int(_z(e.get("reihen")) or 1)
    ab, tq = _z(e.get("abstand")), _z(e.get("teilung_q"))
    out = []
    for r in range(reihen):
        dq = (r - (reihen - 1) / 2) * tq
        dx0 = ab / 2 if e.get("versetzt") and r % 2 else 0.0
        out += [(dx0 + i * ab, dq) for i in range(n)]
    return out


def laenge_x(e):
    """Ausdehnung einer Kontur in x [mm] (für Schlitze am Ende)."""
    pts = umriss_kontur(e)
    return (max(x for x, _ in pts) - min(x for x, _ in pts)) if pts else 0.0


def lagen(konturen, L, qs=None):
    """Jede Kontur einzeln mit Lage: [dict(zeile, nr, art, x, eingabe)]. x aus der Eingabe (Mitte der ersten),
    Muster mit Abstand längs (x + i × Abstand); ohne Lage gleichmäßig über die Länge verteilt (wie bisher), Schlitze
    und Ausklinkungen ohne Lage am Ende A. Kopien am Umfang (beide Wände, alle Seiten, am Umfang verteilt: Eingabe
    'kopien' aus umlauf, mit qs neu für diesen Querschnitt) folgen mit eigener Seite und kopie=True (nr ab Anzahl)."""
    liste = []
    for z, e in enumerate(konturen or ()):
        try:
            _, hk, n = kontur(e)
        except ValueError:
            continue
        x0, ab = e.get("x"), _z(e.get("abstand"))
        if x0 is None and e.get("art") in (SCHLITZ, AUSKLINKUNG):
            x0 = laenge_x(e) / 2
        elif x0 is None and e.get("art") == LOCHFELD:      # ohne Lage: Feld mittig auf dem Teil
            x0 = (L - (int(_z(e.get("anzahl")) or 1) - 1) * ab) / 2
        kopien = umlauf(qs, e) if qs is not None and e.get("wand") else e.get("kopien") or ()
        for j, k in enumerate([None] + list(kopien)):
            ein = e if k is None else dict(e, kopien=None, **k)
            if e.get("art") == LOCHFELD:        # jedes Loch einzeln, Lage x = erste Spalte
                for i, (dx, dq) in enumerate(lochfeld(e)):
                    d = dict(zeile=z, nr=j * n + i, art=LOCHFELD, x=x0, huelle=hk,
                             eingabe=dict(ein, _dx=dx or None, _dq=dq or None))
                    if k is not None:
                        d["kopie"] = True
                    liste.append(d)
                continue
            for i in range(n):
                x = None if x0 is None else (x0 + i * ab if ab else x0)
                d = dict(zeile=z, nr=j * n + i, art=e.get("art"), x=x, huelle=hk, eingabe=ein)
                if k is not None:
                    d["kopie"] = True
                liste.append(d)
    frei = [d for d in liste if d["x"] is None]
    for j, d in enumerate(frei):
        d["x"] = L * (j + 1) / (len(frei) + 1)
        d["verteilt"] = True
    return liste


def platzieren(qs, d, pts=None):
    """3D-Linienzug [(x, u, v)] einer Kontur und ihre Normale (u, v) in der Mitte. pts = eigener Linienzug (dx, dq)
    um die Mitte der Kontur statt ihres Umrisses (z. B. ein Strich einer Text-Gravur)."""
    e = d["eingabe"]
    pts = pts or umriss_kontur(e) or [(0.0, 0.0)]
    if e.get("umriss") and not qs.r and qs.flaechen:      # über mehrere Flächen: entlang der Abwicklung
        out = [(d["x"] + dx, *_um_kante(qs, sk_s)) for dx, sk_s in
               ((dx, s_lage(qs, e, dq)) for dx, dq in pts)]
        return out, qs.s_zu_uv(s_lage(qs, e) % qs.umfang)[1]
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


def rund_ort(qs, u, v):
    """Punkt (u, v) der scharfkantigen Skizze auf der Außenkontur mit Eckradius (Quadrat-/Rechteckrohr, wie die
    3D-Ansicht und die STEP-Datei): im Eckbereich der nächste Punkt auf dem Bogen, sonst unverändert. Ergebnis
    (u, v, Normale nach außen oder None = Normale der Fläche)."""
    r = qs.radius if not qs.r and qs.form in opt.RADIUS_FORMEN else 0.0
    if not r:
        return u, v, None
    cu, cv = qs.B / 2 - r, qs.H / 2 - r
    if abs(u) <= cu + 1e-9 or abs(v) <= cv + 1e-9:
        return u, v, None
    mu, mv = math.copysign(cu, u), math.copysign(cv, v)
    lg = math.hypot(u - mu, v - mv) or 1.0
    nu, nv = (u - mu) / lg, (v - mv) / lg
    return mu + r * nu, mv + r * nv, (nu, nv)


def _um_kante(qs, s):
    return qs.s_zu_uv(s % qs.umfang)[0]


def normalen(qs, d):
    """Normale (u, v) je Punkt des Linienzugs einer Kontur (für Konturen über mehrere Flächen)."""
    e = d["eingabe"]
    pts = umriss_kontur(e) or [(0.0, 0.0)]
    if qs.r:
        w = winkel_aus_text(e.get("seite")) or 0.0
        return [(math.sin(math.radians(w) + dq / qs.r), math.cos(math.radians(w) + dq / qs.r)) for _, dq in pts]
    if e.get("umriss") and qs.flaechen:
        return [qs.s_zu_uv(s_lage(qs, e, dq) % qs.umfang)[1] for _, dq in pts]
    n = platzieren(qs, d)[1]
    return [n] * len(pts)


WAENDE = {"": "nur diese Wand", "beide": "beide Wände (durchgehend)", "alle": "alle vier Seiten",
          "umfang": "am Umfang verteilt"}


def waende_arten(qs):
    """Auswahl „Wände“ einer Kontur für den Querschnitt: Schlüssel aus WAENDE (leer = nur diese Wand)."""
    if qs.r:
        return ["", "beide", "umfang"]
    namen = [f.name for f in qs.flaechen]
    if len(namen) == 4:
        return ["", "beide", "alle"]
    return ["", "beide"] if {"Flansch oben", "Flansch unten"} <= set(namen) else [""]


GEGENWAND = {"oben": "unten", "unten": "oben", "vorne": "hinten", "hinten": "vorne", "Flansch oben": "Flansch unten",
             "Flansch unten": "Flansch oben"}


def umlauf(qs, e):
    """Kopien einer Kontur am Umfang nach e['wand'] (Plan 3D-Editor 3E-4, AlmaCAM „eine/beide Wände“): 'beide' =
    durchgehend auf der gegenüberliegenden Wand (quer gespiegelt, Versatz −q), 'alle' = auf allen vier Seiten
    (gleiche Lage je Seite), 'umfang' = Rundrohr e['umfang_n'] Stück gleichmäßig am Umfang. Ergebnis
    [dict(seite, q, spiegeln)] ohne die Kontur selbst; [] wenn nichts passt."""
    art = e.get("wand")
    if art not in waende_arten(qs) or not art:
        return []
    if qs.r:
        w0 = winkel_aus_text(e.get("seite")) or 0.0
        n = 2 if art == "beide" else int(_z(e.get("umfang_n")))
        if n < 2:
            return []
        return [dict(seite=round((w0 + k * 360 / n) % 360, 3) or None, q=None, spiegeln=art == "beide" or None)
                for k in range(1, n)]
    namen = [f.name for f in qs.flaechen]
    seite = e.get("seite") if e.get("seite") in namen else namen[0]
    q = _z(e.get("q"))
    if art == "beide":
        neu = GEGENWAND.get(seite)
        return [dict(seite=neu, q=-q or None, spiegeln=True)] if neu in namen else []
    i = namen.index(seite)
    return [dict(seite=namen[(i + k) % 4], q=q or None, spiegeln=None) for k in range(1, 4)]


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
