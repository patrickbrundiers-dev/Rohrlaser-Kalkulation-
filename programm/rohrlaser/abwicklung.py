"""Exakte Abwicklung der Rohraußenhaut (ohne Oberfläche, damit testbar; Plan 3D/Abwicklung P4.1, 20.11.2026).

Die Skizze (skizze.py) rechnet die Lage am Umfang mit der scharfkantigen Abwicklung s (Umfang 2 (B + H) beim
Quadrat-/Rechteckrohr). Die echte Außenhaut hat an jeder Ecke einen Bogen mit dem Außenradius r; ihre Länge ist
2 (B + H) − 8 r + 2 π r. Mantel bildet s auf die echte Länge t der Außenhaut ab (und zurück), genau so, wie
skizze.rund_ort einen Punkt der scharfkantigen Skizze radial auf den Bogen legt (und uv_zu_s ihn zurückholt): s = 0
ist die scharfe Ecke oben hinten, t = 0 die Mitte ihres Bogens. Ohne Radius (Rundrohr, offene Profile, Flachstahl)
ist t = s.

Geschnittene Konturen (Bohrung, Langloch, Rechteck …) liegen in der Abwicklung genau dort, wo sie im 3D und im
Schnittkörper liegen (rohr3d.loch_poly: 2D innen maßhaltig und außen breiter, 3D eben am Eckradius); es gibt dafür
keine zweite Rechnung.

Die Schnittlänge rechnet weiter nur schneidweg.py (keine zweite Rechnung, keine Formel geändert).
"""
import bisect
import math

from . import optimierung as opt
from .schneidweg import GRAVUREN, TEXT_GRAVUR, _z


class Mantel:
    """Abbildung scharfkantige Abwicklung s <-> echte Außenhaut t für einen skizze.Querschnitt."""

    def __init__(self, qs):
        self.qs = qs
        self.U_s = float(qs.umfang or 0.0)
        r = float(getattr(qs, "radius", 0.0) or 0.0)
        flaechen = getattr(qs, "flaechen", None) or []
        ok = (not qs.r and qs.form in opt.RADIUS_FORMEN and len(flaechen) == 4 and r > 1e-6
              and all(f.breite >= 2 * r - 1e-9 for f in flaechen))
        self.r = r if ok else 0.0
        self.flaechen = []              # [(Name, s0, Breite b, t0, echte Breite)]
        s0 = t0 = 0.0
        for f in flaechen:
            echt = f.breite - 2 * self.r + math.pi * self.r / 2 if self.r else f.breite
            self.flaechen.append((f.name, s0, f.breite, t0, echt))
            s0 += f.breite
            t0 += echt
        self.umfang = t0 if self.flaechen and self.r else self.U_s

    @property
    def exakt(self):
        """True, wenn sich t von s unterscheidet (Eckradius)."""
        return bool(self.r)

    # ------------------------------------------------------------------ s -> t
    def t(self, s):
        """Echte Länge der Außenhaut zur Stelle s der scharfkantigen Abwicklung (periodisch über den Umfang)."""
        if not self.r or not self.U_s:
            return s
        k, s_ = divmod(s, self.U_s)
        return k * self.umfang + self._t_innen(s_)

    def _t_innen(self, s):
        r, viertel = self.r, math.pi * self.r / 4
        for _, s0, b, t0, _ in self.flaechen:
            c = s - s0
            if c <= b + 1e-12:
                c = min(max(c, 0.0), b)
                if c < r:
                    return t0 + viertel - r * math.atan((r - c) / r)
                if c > b - r:
                    return t0 + viertel + (b - 2 * r) + r * math.atan((r - (b - c)) / r)
                return t0 + viertel + (c - r)
        return self.umfang

    # ------------------------------------------------------------------ t -> s
    def s(self, t):
        """Umkehrung von t: Stelle s der scharfkantigen Abwicklung zur echten Länge t."""
        if not self.r or not self.umfang:
            return t
        k, t_ = divmod(t, self.umfang)
        return k * self.U_s + self._s_innen(t_)

    def _s_innen(self, t):
        r, viertel = self.r, math.pi * self.r / 4
        for _, s0, b, t0, echt in self.flaechen:
            tau = t - t0
            if tau <= echt + 1e-12:
                tau = min(max(tau, 0.0), echt)
                if tau < viertel:
                    return s0 + r - r * math.tan((viertel - tau) / r)
                rest = tau - viertel - (b - 2 * r)
                if rest > 0:
                    return s0 + b - (r - r * math.tan(rest / r))
                return s0 + r + (tau - viertel)
        return self.U_s

    # ------------------------------------------------------------------ Streifen und Kanten
    def streifen(self):
        """[(Name, t0, t1)] der Seiten auf der echten Außenhaut (Grenze = Mitte des Eckbogens); ohne Radius wie
        Querschnitt.abwicklung_streifen."""
        if not self.r:
            return list(self.qs.abwicklung_streifen())
        return [(n, t0, t0 + echt) for n, _, _, t0, echt in self.flaechen]

    def radius_linien(self):
        """[(t, Art)] der Übergänge eben/Bogen (Art 'radius') und der Bogenmitten (Art 'kante') auf der echten
        Außenhaut; ohne Radius nur die Kanten."""
        out = []
        viertel = math.pi * self.r / 4
        for _, _, _, t0, echt in self.flaechen:
            out.append((t0, "kante"))
            if self.r:
                out += [(t0 + viertel, "radius"), (t0 + echt - viertel, "radius")]
        return sorted(out)


def ringe(qs):
    """(außen, innen, cum, cum_i) des Querschnitts wie im 3D und in den Schnittkörpern (schnittflaeche.ringe,
    rohr3d._laengen) oder None (offenes bzw. volles Profil)."""
    from . import schnittflaeche as sf
    from .rohr3d import _laengen
    r = sf.ringe(qs)
    if r is None:
        return None
    return r[0], r[1], _laengen(r[0]), _laengen(r[1])


def _ring_punkt(poly, cum, t):
    T = cum[-1]
    t %= T
    i = max(0, min(len(poly) - 1, bisect.bisect_right(cum, t) - 1))
    f = 0.0 if cum[i + 1] - cum[i] < 1e-12 else (t - cum[i]) / (cum[i + 1] - cum[i])
    (u0, v0), (u1, v1) = poly[i], poly[(i + 1) % len(poly)]
    return u0 + f * (u1 - u0), v0 + f * (v1 - v0)


def kontur_s(qs, d, eingaben, ring, schritt=2.0):
    """Rand einer geschnittenen Kontur (Lage d aus skizze.lagen) auf der echten Außenhaut wie im 3D und im
    Schnittkörper (rohr3d.loch_poly: 2D innen maßhaltig und außen breiter, 3D eben am Eckradius parallel zur Normalen)
    als [(x, s)] in der scharfkantigen Abwicklung (stetig um die Mitte der Kontur), oder None (keine geschnittene
    Kontur bzw. kein Ring). Ein Lochpunkt geht dazu über seinen Ort (u, v) radial zurück (skizze.uv_zu_s)."""
    if ring is None:
        return None
    from . import skizze as sk
    from .rohr3d import loch_poly
    aussen, _, cum, cum_i = ring
    poly = loch_poly(d, eingaben or {}, qs, aussen, cum, cum_i, schritt)
    if not poly:
        return None
    U = qs.umfang
    s_alt = sk.s_lage(qs, d["eingabe"])
    out = []
    for t, x in poly:
        s = sk.uv_zu_s(qs, *_ring_punkt(aussen, cum, t))
        s += U * round((s_alt - s) / U)
        out.append((x, s))
        s_alt = s
    return out


RADIUS_EXAKT_ARTEN = ("Bohrung", "Senkung", "Langloch", "Rechteck", "Schlitz", "Polygon")


def faktor_im_radius(qs, eingabe, eingaben, L, ring=None, mantel=None):
    """Faktor Schnittlänge auf der Außenhaut / gezeichnete Länge einer Kontur (Quadrat-/Rechteckrohr), wenn sie in den Eckradius reicht
    (Patrick 20.11.2026: „Berechnung auf den richtigen Wert umstellen“): dort ist sie außen breiter als gezeichnet
    (26.10.2026: innen maßhaltig, Strahl senkrecht zur Oberfläche). Umfang des Lochrands wie im 3D und in der
    Abwicklung (rohr3d.loch_poly) geteilt durch den gezeichneten Umfang, sonst None (ganz auf der ebenen Wand: die
    Formel gilt unverändert)."""
    from . import skizze as sk
    m = mantel or Mantel(qs)
    if not m.r or (eingabe or {}).get("art") not in RADIUS_EXAKT_ARTEN:
        return None
    ring = ring if ring is not None else ringe(qs)
    lage = next(iter(sk.lagen([eingabe], L or 1000.0, qs)), None)
    if lage is None or ring is None:
        return None
    pts = kontur_s(qs, lage, eingaben, ring, 0.5)
    if not pts or len(pts) < 3:
        return None
    U, r = qs.umfang, m.r

    def im_radius(s):
        s %= U
        for _, s0, b, _, _ in m.flaechen:
            c = s - s0
            if -1e-9 <= c <= b + 1e-9:
                return c < r - 1e-6 or c > b - r + 1e-6
        return False
    if not any(im_radius(s) for _, s in pts):
        return None
    pk = [(x, m.t(s)) for x, s in pts]
    aussen = sum(math.dist(a, b) for a, b in zip(pk, pk[1:] + pk[:1]))
    # gezeichneter Umriss gleich fein unterteilt: Verhältnis außen/gezeichnet hebt den Sehnenfehler der Bögen auf
    roh = sk._dicht(sk.umriss_kontur(eingabe) or [], 0.5)
    gezeichnet = sum(math.dist(a, b) for a, b in zip(roh, roh[1:] + roh[:1]))
    return aussen / gezeichnet if gezeichnet > 1e-9 else None


def linien(qs, eingaben, L, mantel=None):
    """Konturlinien der exakten Abwicklung für Zeichnung, Bemaßung und DXF: [dict(kennung, art, punkte [(x, t)],
    geschlossen, zeile)]. Kennungen: 'ende:a', 'ende:b', 'rand:0', 'rand:1' (Ränder der Abwicklung), 'kante:i' bzw.
    'radius:i' (Seitenkanten, Radiusübergänge) und 'kontur:<Zeile>:<Nr>' je Kontur (gleiche Kennung wie im 3D)."""
    from . import skizze as sk
    m = mantel or Mantel(qs)
    eingaben = eingaben or {}
    e_a, e_b = eingaben.get("a") or {}, eingaben.get("b") or {}
    la, lb = sk.ende_abwicklung(qs, e_a), sk.ende_abwicklung(qs, e_b)
    out = [dict(kennung="ende:a", art="ende", punkte=[(d, m.t(s)) for s, d in la], geschlossen=False, zeile=None),
           dict(kennung="ende:b", art="ende", punkte=[(L - d, m.t(s)) for s, d in lb], geschlossen=False,
                zeile=None)]

    def d_bei(linie, s):
        return min(linie, key=lambda z: abs(z[0] - s))[1]
    for i, s_ in enumerate((0.0, qs.umfang)):
        out.append(dict(kennung=f"rand:{i}", art="rand", punkte=[(d_bei(la, s_), m.t(s_)),
                                                                  (L - d_bei(lb, s_), m.t(s_))],
                        geschlossen=False, zeile=None))
    for i, (t_, art) in enumerate(m.radius_linien()):
        if art == "kante" and i == 0 and t_ <= 1e-9:
            continue                    # Rand der Abwicklung
        s_ = m.s(t_)
        out.append(dict(kennung=f"{art}:{i}", art=art, punkte=[(d_bei(la, s_), t_), (L - d_bei(lb, s_), t_)],
                        geschlossen=False, zeile=None))
    ring = ringe(qs)
    for d in sk.lagen(eingaben.get("konturen"), L, qs):
        e = d["eingabe"]
        geschnitten = kontur_s(qs, d, eingaben, ring)
        if geschnitten:
            pts = [(x, m.t(s)) for x, s in geschnitten]
        else:
            umr = sk.umriss_kontur(e)
            if not umr:
                continue
            s0 = sk.s_lage(qs, e)
            pts = [(d["x"] + dx, m.t(s0 + dq)) for dx, dq in umr]
        t_m = (min(t for _, t in pts) + max(t for _, t in pts)) / 2
        if t_m > m.umfang:              # Mitte im Streifen 0 … Umfang (über die Naht reicht die Kontur hinaus)
            pts = [(x, t - m.umfang) for x, t in pts]
        elif t_m < 0:
            pts = [(x, t + m.umfang) for x, t in pts]
        out.append(dict(kennung=f"kontur:{d['zeile']}:{d['nr']}", art=d["art"], punkte=pts,
                        geschlossen=len(pts) >= 3, zeile=d["zeile"]))
    return out


# ---------------------------------------------------------------------- Bemaßung (P4.2)
def bemassung(qs, eingaben, L, mantel=None):
    """Maße der exakten Abwicklung: dict(laenge, umfang (echte Außenhaut), umfang_scharf, seiten [(Name, Breite)],
    konturen [dict(kennung, zeile, text, x, t, breite_x, breite_t)] (Mitte und Hülle je Kontur, t ab Rand 0),
    kette [x] (Lagen längs, sortiert, für das Kettenmaß))."""
    from . import skizze as sk
    m = mantel or Mantel(qs)
    konturen = []
    for li in linien(qs, eingaben, L, m):
        if not li["kennung"].startswith("kontur:"):
            continue
        xs, ts = [p[0] for p in li["punkte"]], [p[1] for p in li["punkte"]]
        zeile = li["zeile"]
        e = ((eingaben or {}).get("konturen") or [])[zeile] if zeile is not None else {}
        konturen.append(dict(kennung=li["kennung"], zeile=zeile, text=sk.kurz(e) if e else li["art"],
                             x=round((min(xs) + max(xs)) / 2, 2), t=round((min(ts) + max(ts)) / 2, 2),
                             breite_x=round(max(xs) - min(xs), 2), breite_t=round(max(ts) - min(ts), 2)))
    kette = sorted({k["x"] for k in konturen})
    return dict(laenge=L, umfang=round(m.umfang, 3), umfang_scharf=round(qs.umfang, 3),
                seiten=[(n, round(t1 - t0, 3)) for n, t0, t1 in m.streifen()], konturen=konturen, kette=kette)


# ---------------------------------------------------------------------- DXF der Rohrabwicklung (P4.3)
ROHR_LAYER = "AUSSENKONTUR; INNENKONTUR; KANTE; RADIUS; GRAVUR; BESCHRIFTUNG"


def dxf_elemente(qs, eingaben, L, mit_mass=True, mantel=None):
    """Elemente für dxf.schreiben: x längs ab Ende A, y = Umfang − t (oben die Seite 'oben' wie in der Skizze).
    Layer (Namen ROHR_LAYER): Umriss (Enden, Ränder) außen, geschnittene Konturen innen, Seitenkanten, Radiuslinien,
    Gravuren, Beschriftung (Seiten, Maße, Kontur-Kurztexte)."""
    from . import dxf
    m = mantel or Mantel(qs)
    U = m.umfang

    def p(x, t):
        return (round(x, 4), round(U - t, 4))
    elem = []
    for li in linien(qs, eingaben, L, m):
        art = li["art"]
        layer = (dxf.AUSSEN if art in ("ende", "rand") else dxf.HOCH if art == "kante" else
                 dxf.RUNTER if art == "radius" else dxf.GRAVUR if art in GRAVUREN else dxf.INNEN)
        pts = li["punkte"]
        if art == TEXT_GRAVUR and li["zeile"] is not None:
            striche = _text_striche(qs, eingaben, li, m)
            if striche:
                for z in striche:
                    elem += [("LINE", dxf.GRAVUR, p(*a), p(*b)) for a, b in zip(z, z[1:])]
                continue
        zuege = [pts + pts[:1]] if li["geschlossen"] else [pts]
        if li["geschlossen"]:           # über die Naht: auch um den Umfang verschoben (wie in der Skizze)
            ts = [t for _, t in pts]
            if min(ts) < -1e-6:
                zuege.append([(x, t + U) for x, t in pts + pts[:1]])
            if max(ts) > U + 1e-6:
                zuege.append([(x, t - U) for x, t in pts + pts[:1]])
        for z in zuege:
            z = [(x, min(max(t, 0.0), U)) for x, t in z] if li["geschlossen"] and len(zuege) > 1 else z
            elem += [("LINE", layer, p(*a), p(*b)) for a, b in zip(z, z[1:]) if math.dist(a, b) > 1e-6]
    if mit_mass:
        b = bemassung(qs, eingaben, L, m)
        h = 3.5
        for (name, breite), (_, t0, t1) in zip(b["seiten"], m.streifen()):
            elem.append(("TEXT", dxf.TEXT, p(-60, (t0 + t1) / 2 + h / 2), h, f"{name} {_zahl(breite)}"))
        elem.append(("TEXT", dxf.TEXT, p(0, U + 10), h,
                     f"Abwicklung Außenhaut: Länge {_zahl(L)} mm, Umfang {_zahl(b['umfang'])} mm"))
        for k in b["konturen"]:
            elem.append(("TEXT", dxf.TEXT, p(k["x"] + k["breite_x"] / 2 + 2, k["t"]), 2.5,
                         f"{k['text']}  x {_zahl(k['x'])}  t {_zahl(k['t'])}"))     # masstext: Lage x/t
    return elem


def _zahl(x):
    from .rechnen import zahl
    return zahl(x, 1)


def _text_striche(qs, eingaben, li, m):
    """Striche einer Text-Gravur ohne Umriss in der Abwicklung [(x, t)] (Einstrich-Schrift wie in der Skizze)."""
    from . import gravur_text
    from . import skizze as sk
    e = ((eingaben or {}).get("konturen") or [])[li["zeile"]]
    if e.get("umriss"):
        return None
    zuege = gravur_text.linien(e.get("text"), _z(e.get("hoehe")))
    if not zuege:
        return None
    if _z(e.get("winkel")):
        zuege = gravur_text.gedreht(zuege, _z(e["winkel"]))
    xs = [x for x, _ in li["punkte"]]
    xm = (min(xs) + max(xs)) / 2
    s0 = sk.s_lage(qs, e)
    if s0 > qs.umfang:
        s0 -= qs.umfang
    return [[(xm + dx, m.t(s0 - dy)) for dx, dy in z] for z in zuege]


def dxf_speichern(pfad, qs, eingaben, L, mit_mass=True):
    """DXF R12 der Rohrabwicklung schreiben (Layer ROHR_LAYER, dichte Punktfolgen als Bögen)."""
    from . import dxf
    namen = dict(zip(dxf.LAYER, (n.strip() for n in ROHR_LAYER.split(";"))))
    dxf.speichern(pfad, dxf_elemente(qs, eingaben, L, mit_mass), namen)


# ---------------------------------------------------------------------- Gegenprobe (P6.1)
GEGENPROBE_GRENZE = 1.0         # % Abweichung, ab der die Gegenprobe meldet


def gegenprobe(qs, eingaben, L, ergebnis, grenze=GEGENPROBE_GRENZE):
    """Konturlänge je Zeile aus der Rechnung (schneidweg, laenge_stueck) gegen den Umfang derselben Kontur auf der
    Außenhaut der exakten Abwicklung. Nur Meldung, rechnet nichts neu und ändert keinen Preis: [dict(zeile, text,
    rechnung, abwicklung, prozent)] für Abweichungen über grenze %. Gravuren, Mündungen zum Ende und Konturen ohne
    eigene Zeile in der Rechnung bleiben außen vor."""
    zeilen = (eingaben or {}).get("konturen") or []
    nach_zeile = {}
    for st in ((ergebnis or {}).get("schritte") or ())[2:]:
        e = st.get("eingabe")
        z = next((i for i, k in enumerate(zeilen) if k is e), None)
        if z is not None and _z(st.get("laenge_stueck")) > 0:
            nach_zeile[z] = st
    if not nach_zeile:
        return []
    out = []
    for li in linien(qs, eingaben, L):
        if not li["kennung"].endswith(":0") or not li["kennung"].startswith("kontur:") or li["zeile"] not in nach_zeile:
            continue
        e = zeilen[li["zeile"]]
        if li["art"] in GRAVUREN or e.get("muendung") or not li["geschlossen"]:
            continue
        pk = li["punkte"]
        umfang = sum(math.dist(a, b) for a, b in zip(pk, pk[1:] + pk[:1]))
        st = nach_zeile[li["zeile"]]
        soll = _z(st["laenge_stueck"])
        prozent = (umfang - soll) / soll * 100
        if abs(prozent) > grenze:
            out.append(dict(zeile=li["zeile"], text=st.get("text") or li["art"], rechnung=round(soll, 2),
                            abwicklung=round(umfang, 2), prozent=round(prozent, 1)))
    return out


# ---------------------------------------------------------------------- Unsichere Merkmale (P3.1, aus #596)
def unsichere(qs, analyse, L=None):
    """Merkmale der Importanalyse (bauteil_analyse.aus_position) mit Konfidenz unter GRUEN_AB zum Anzeigen in 3D und
    Abwicklung: [dict(x, s (scharfkantig) oder None = Lage am Umfang unbekannt, text, konfidenz)]. Nur Anzeige."""
    from . import bauteil_analyse as ba
    from . import skizze as sk
    out = []
    for m in (analyse or {}).get("merkmale") or ():
        try:
            konf = float(m.get("konfidenz") if m.get("konfidenz") is not None else 100)
        except (TypeError, ValueError):
            continue
        if konf >= ba.GRUEN_AB:
            continue
        x = m.get("x")
        if x is None and m.get("ende") in ("A", "B") and L:
            x = 0.0 if m["ende"] == "A" else float(L)
        if x is None:
            continue
        s = None
        if qs.r and m.get("winkel") is not None:
            s = sk.s_lage(qs, dict(seite=float(m["winkel"]))) % qs.umfang
        elif not qs.r and m.get("seite") in qs.seiten():
            s = sk.s_lage(qs, dict(seite=m["seite"]))
        text = f"{m.get('merkmal') or m.get('art') or 'Merkmal'} {m.get('abmessung') or ''}".strip()
        out.append(dict(x=float(x), s=s, text=f"{text} · {konf:g} % (bitte prüfen)", konfidenz=konf,
                        hinweis=m.get("hinweis") or ""))
    return out
