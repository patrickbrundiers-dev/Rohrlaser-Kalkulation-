"""Am 3D-Modell bearbeiten (Plan 3D-Editor 3E-3, wie in ArTube/AlmaCAM): Werkzeug der 3D-Ansicht im Teile-Editor.

- C1 Griffe: die gewählte Kontur bekommt einen Pfeil längs (verschieben entlang des Rohrs) und einen quer (um den
  Umfang bzw. auf die Nachbarfläche); beim Ziehen steht das Maß am Mauszeiger, das Modell zieht live mit.
- C2 Fangen: Raster (Vorgabe 5 mm bzw. 15° am Rundrohr), Teilmitte und Flächenmitte; Alt beim Ziehen = frei.
- G1 Schnittebenen: an Ende A/B eine halb durchsichtige Ebene; der Griff an der Ebene stellt den Gehrungswinkel
  (fängt 1°-Schritte und die Vielfachen von 15°), der Winkel steht daneben.
- B4 Maße am Modell: Lage der gewählten Kontur ab Ende A, bis Ende B und zur Nachbarkontur auf derselben Seite;
  Doppelklick auf ein Maß öffnet ein Eingabefeld an Ort und Stelle (Rechnungen wie L/2 gehen).
- B6 Pfeiltasten: links/rechts verschieben längs, hoch/runter quer um einen Rasterschritt (Umschalt = ×10); bei
  einem gewählten Ende ändern hoch/runter den Gehrungswinkel um 1° (Umschalt 10°).
- C4 Kontextmenü (Rechtsklick ohne Ziehen in der 3D-Ansicht und im Merkmalsbaum): Duplizieren, Spiegeln zur
  Teilmitte, auf die Gegenseite, auf STEP-Wert zurück, Entfernen, Messen von hier, Enden gerade/45°, Darstellung.

Gerechnet wird nichts Neues: Lage und Seite gehen wie beim Ziehen in der Skizze an SchneidwegDialog._verschoben,
der Winkel an das Feld des Endes. Während des Ziehens schweigt der Rahmen (kein Rückgängig-Schritt je Mausbewegung);
beim Loslassen entsteht genau ein Schritt. Geometrie wie rohr3d (Rohrachse = Z ab Ende A, X = −u, Y = v).
"""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QFont, QPen, QPolygonF
from PySide6.QtWidgets import QMenu

from . import durchdringung as dd, rechnen, schneidweg as sw, skizze as sk, stil
from .ansicht3d import DARSTELLUNGEN
from .rechenfeld import RechenFeld

RASTER, RASTER_WINKEL = 5.0, 15.0   # Vorgaben Fangen (Einstellungen editor_raster / editor_raster_winkel)
WINKEL_FANG = 15.0                  # Schnittebene: Vielfache davon fangen auf ±2°
GRIFF_PX, FANG_PX = 44, 9           # Pfeillänge und Fangabstand der Griffe [Bildpunkte]
MASS_PX = 16                        # Maßlinie so weit über der Oberfläche [Bildpunkte]
LAENGS, QUER, EBENE = "#1565C0", "#00838F", "#B35C00"
EBENE_FARBE = {"a": QColor(242, 142, 43, 55), "b": QColor(176, 122, 161, 55)}     # wie Anfangs-/Endschnitt
MASS = stil.farbe_fest("#1F2937")
GEGENSEITE = {"oben": "unten", "unten": "oben", "vorne": "hinten", "hinten": "vorne"}


def _xyz(x, u, v):
    return (-u, v, x)


def fangen(wert, raster, marken=(), an=True):
    """Wert auf das Raster setzen; Marken (Teilmitte, Flächenmitte) gewinnen, wenn sie näher liegen als der
    Rasterpunkt und höchstens einen halben Rasterschritt entfernt sind."""
    if not an or not raster or raster <= 0:
        return round(wert, 1)
    beste = round(wert / raster) * raster
    for m in marken:
        if abs(wert - m) <= raster / 2 and abs(wert - m) < abs(wert - beste):
            beste = m
    return round(beste, 3)


def winkel_fangen(w, an=True):
    """Gehrungswinkel beim Ziehen der Schnittebene: 1°-Schritte, Vielfache von 15° fangen auf ±2°; 0 … 79,9°."""
    w = max(0.0, min(79.9, w))
    if not an:
        return round(w, 1)
    f = round(w / WINKEL_FANG) * WINKEL_FANG
    return float(min(79.9, f if abs(w - f) <= 2 else round(w)))


def mitte_uv(qs, e):
    """Mitte einer Kontur im Querschnitt: Punkt (u, v), Normale (nu, nv) und Richtung quer (tu, tv), in die die
    Stelle s der Abwicklung wächst (Rundrohr: der Winkel)."""
    if qs.r:
        phi = math.radians(sk.winkel_aus_text(e.get("seite")) or 0.0)
        s, c = math.sin(phi), math.cos(phi)
        return (qs.r * s, qs.r * c), (s, c), (c, -s)
    if not qs.flaechen:
        return (0.0, qs.H / 2), (0.0, 1.0), (1.0, 0.0)
    s = sk.s_lage(qs, e) % qs.umfang
    pt, n = qs.s_zu_uv(s)
    f = qs.flaeche(e.get("seite")) if not e.get("umriss") else None
    if f is not None:
        return pt, f.n, f.dir
    t = (n[1], -n[0])
    nach = qs.s_zu_uv(min(s + 0.5, qs.umfang))[0]
    if (nach[0] - pt[0]) * t[0] + (nach[1] - pt[1]) * t[1] < 0:
        t = (-t[0], -t[1])
    return pt, n, t


def quer_neu(qs, e, delta, raster, an=True):
    """Neue Seite/Versatz einer Kontur nach delta [mm] quer (Rundrohr: am Umfang). Ergebnis wie
    Skizze.neue_lage: {seite, q} für SchneidwegDialog._verschoben."""
    if qs.r:
        w0 = sk.winkel_aus_text(e.get("seite")) or 0.0
        w = math.degrees(math.radians(w0) + delta / qs.r)
        w = fangen(w, raster, an=an) % 360
        return dict(seite=None if not w else round(w, 1), q=None)
    if not qs.flaechen:
        return {}
    s = sk.s_lage(qs, e) + delta
    seite, q = sk.s_zu_seite(qs, s % qs.umfang)
    f = qs.flaeche(seite)
    if f is not None:
        q = max(-f.breite / 2, min(f.breite / 2, fangen(q, raster, (0.0,), an)))
    erste = qs.seiten()[0] if qs.seiten() else None
    return dict(seite=None if seite == erste else seite, q=q or None)


def x_neu(e, lage, x, L):
    """Neue Lage der ersten Kontur einer Zeile; eine gleichmäßig verteilte Reihe wird zum Muster mit gleichem Abstand
    (wie beim Ziehen in der Skizze)."""
    n = int(sw._z(e.get("anzahl")) or 1)
    x = round(max(0.0, min(L, x)), 3)
    if e.get("x") is not None or n == 1 or sw._z(e.get("abstand")):
        return dict(x=x)
    return dict(x=x, abstand=round(L / (n + 1), 1))


def gespiegelt(e, lagen_zeile, L):
    """Spiegeln zur Teilmitte: neue Lage der ersten Kontur (die letzte des Musters wandert nach vorn); eine
    gleichmäßig verteilte Reihe wird zum Muster mit ihrem Abstand."""
    xs = sorted(d["x"] for d in lagen_zeile or ())
    if not xs:
        return {}
    neu = dict(x=round(max(0.0, L - xs[-1]), 3))
    if len(xs) > 1 and not sw._z(e.get("abstand")):
        neu["abstand"] = round(xs[1] - xs[0], 3)
    return neu


def gegenseite(qs, e):
    """Auf die gegenüberliegende Seite (Rundrohr +180°; Kasten oben↔unten, vorne↔hinten, Versatz bleibt – die
    Gegenseite läuft andersherum, so liegt die Kontur genau gegenüber)."""
    if qs.r:
        w = ((sk.winkel_aus_text(e.get("seite")) or 0.0) + 180) % 360
        return dict(seite=None if not w else w, q=None)
    seite = e.get("seite") or (qs.seiten()[0] if qs.seiten() else None)
    neu = GEGENSEITE.get(seite)
    if neu is None and len(qs.flaechen) == 4:
        namen = [f.name for f in qs.flaechen]
        neu = namen[(namen.index(seite) + 2) % 4] if seite in namen else None
    if neu is None:
        return {}
    erste = qs.seiten()[0] if qs.seiten() else None
    return dict(seite=None if neu == erste else neu, q=e.get("q"))


def ebene_griff(qs, e):
    """Schnittebene eines Endes: (Punkt (u, v) des Griffs, Abstand des Griffs zur Spitze quer [mm]) – der Griff sitzt
    gegenüber der längsten Seite, dort liegt die Schnittkante 2·ext·tan(w) hinter der Spitze. None: Sattel bzw.
    Schrägschnitt zweiachsig (Ebene ohne Griff)."""
    e = e or {}
    if dd.gegen_lesen(e) or e.get("achse") == sw.ACHSE_ZWEI:
        return None
    th = math.radians(sk._richtung(qs, e))
    ext = qs.ausdehnung(math.degrees(th))
    return (-math.sin(th) * ext, -math.cos(th) * ext), 2 * ext


def nasen_plus(e):
    """Nasen einer Steckverbindung am Ende e: um ihre Länge liegt der Schnitt weiter innen (wie rohr3d.netz)."""
    from . import steckverbindung as stv
    n = stv.nasen(e)
    return sw._z(n.get("laenge_plus")) if n else 0.0


def ebene_ecken(qs, e, L, seite, rand=8.0):
    """4 Ecken (x, u, v) der Schnittebene eines Endes, etwas größer als der Querschnitt; mit Nasen am Ende um ihre
    Länge nach innen (dort liegt der Schnitt, die Nasen ragen bis zum Teilende)."""
    us = [p[0] for p in qs.umriss[0]] if qs.umriss else [-qs.B / 2, qs.B / 2]
    vs = [p[1] for p in qs.umriss[0]] if qs.umriss else [-qs.H / 2, qs.H / 2]
    u0, u1, v0, v1 = min(us) - rand, max(us) + rand, min(vs) - rand, max(vs) + rand
    out = []
    for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
        z = (sk.schnitt_x(qs, e, u, v) if not dd.gegen_lesen(e) else 0.0) + nasen_plus(e)
        out.append((z if seite == "a" else L - z, u, v))
    return out


def _pfeil(p, a, b, farbe, breite=2.4):
    """Doppelpfeil a–b (Bildpunkte)."""
    p.setPen(QPen(farbe, breite, Qt.SolidLine, Qt.RoundCap))
    p.drawLine(a, b)
    d = b - a
    lg = math.hypot(d.x(), d.y()) or 1.0
    ux, uy = d.x() / lg, d.y() / lg
    p.setBrush(QBrush(farbe))
    for spitze, s in ((b, 1), (a, -1)):
        hinten = QPointF(spitze.x() - s * ux * 10, spitze.y() - s * uy * 10)
        p.drawPolygon(QPolygonF([spitze, QPointF(hinten.x() - uy * 5, hinten.y() + ux * 5),
                                 QPointF(hinten.x() + uy * 5, hinten.y() - ux * 5)]))
    p.setBrush(Qt.NoBrush)


def _abstand_strecke(pos, a, b):
    dx, dy = b.x() - a.x(), b.y() - a.y()
    lg = dx * dx + dy * dy
    t = 0.0 if lg < 1e-9 else max(0.0, min(1.0, ((pos.x() - a.x()) * dx + (pos.y() - a.y()) * dy) / lg))
    return math.hypot(a.x() + t * dx - pos.x(), a.y() + t * dy - pos.y())


class Werkzeug:
    """Werkzeug der 3D-Ansicht für den Teile-Editor Rohr (rahmen: teile_editor.EditorRahmen). Griffe und Maße nur
    am Modell aus den Eingaben (beim STEP-Modell stimmen die Lagen nur ungefähr)."""

    def __init__(self, rahmen):
        self.r, self.d = rahmen, rahmen.d
        self.a = rahmen.ansicht()
        self.rohr = rahmen.art == "rohr"         # Blech: nur Kontextmenü und Darstellung (Griffe kommen mit 3E-4)
        self.fangen_an, self.raster, self.raster_winkel = True, RASTER, RASTER_WINKEL
        self.ebenen, self.masse = True, True
        self._zug, self._griffe, self._mass_felder, self._feld = None, [], [], None
        self.live = ""                      # Maß beim Ziehen (am Mauszeiger, Tests)

    # ------------------------------------------------------------------ Geometrie
    def aktiv(self):
        return (self.rohr and self.a is not None and self.a.modell is not None and self.r._modell_aus_eingaben()
                and not getattr(self.d, "biegerohr", None))

    def laenge(self):
        return self.r.teil_laenge()

    def zeile(self):
        return self.r._gewaehlte_zeile()

    def ende(self):
        art, _, s = (self.r.gewaehlt or "").partition(":")
        return s if art == "ende" and s in ("a", "b") else None

    def lagen(self, r=None):
        e = self.d.eingaben()
        alle = sk.lagen(e.get("konturen") or [], self.laenge(), getattr(self.d, "qs", None))
        return [x for x in alle if x["zeile"] == r] if r is not None else alle

    def kontur_geometrie(self, r):
        """Erste Kontur der Zeile r: (Lage-dict, Mitte (x, u, v), Normale, Richtung quer) oder None."""
        lg = self.lagen(r)
        if not lg:
            return None
        d0 = min(lg, key=lambda x: x["nr"])
        try:
            (u, v), n, t = mitte_uv(self.d.qs, d0["eingabe"])
        except (ValueError, TypeError, ZeroDivisionError, AttributeError):
            return None
        return d0, (d0["x"], u, v), n, t

    @staticmethod
    def _massstab(bild, p):
        """Bildpunkte je mm (Parallelprojektion: gleicher Maßstab in alle Richtungen)."""
        q = bild(p)
        summe = 0.0
        for k in range(3):
            v = list(p)
            v[k] += 1.0
            w = bild(tuple(v))
            summe += (w[0] - q[0]) ** 2 + (w[1] - q[1]) ** 2
        return math.sqrt(summe / 2) or 1.0

    # ------------------------------------------------------------------ Zeichnen
    def hinweis(self):
        if not self.aktiv():
            return None
        if self.zeile() is not None:
            return ("Pfeile ziehen verschiebt (Alt = ohne Fangen) · Pfeiltasten um den Rasterschritt (Umschalt ×10) · "
                    "Doppelklick aufs Maß ändert es · Rechtsklick Menü")
        if self.ende() is not None:
            return "Griff an der Schnittebene stellt die Gehrung · Pfeiltaste hoch/runter ±1° · Rechtsklick Menü"
        return "Linke Maustaste drehen · rechte verschieben · Mausrad zoomen · Rechtsklick Menü"

    def zeichnen(self, p, bild):
        self._griffe, self._mass_felder = [], []
        if not self.aktiv():
            return
        p.setRenderHint(p.RenderHint.Antialiasing, True)
        if self.ebenen:
            self._ebenen_zeichnen(p, bild)
        r = self.zeile()
        if r is not None:
            self._kontur_zeichnen(p, bild, r)
        if self.live and self._zug is not None:
            pos = self._zug.get("jetzt") or self._zug["start"]
            f = QFont(p.font())
            f.setBold(True)
            p.setFont(f)
            rect = QRectF(pos.x() + 14, pos.y() + 10, 320, 20)
            p.fillRect(QRectF(rect.x() - 3, rect.y(), p.fontMetrics().horizontalAdvance(self.live) + 8, 20),
                       stil.farbe("#FFFFFF", 220))
            p.setPen(MASS)
            p.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, self.live)

    def _punkt(self, bild, x, u, v):
        q = bild(_xyz(x, u, v))
        return QPointF(q[0], q[1])

    def _ebenen_zeichnen(self, p, bild):
        e = self.d.eingaben()
        L = self.laenge()
        qs = self.d.qs
        for s in ("a", "b"):
            ee = e.get(s) or {}
            if dd.gegen_lesen(ee):
                continue
            ecken = [self._punkt(bild, *c) for c in ebene_ecken(qs, ee, L, s)]
            gewaehlt = self.ende() == s
            farbe = QColor(EBENE_FARBE[s])
            if gewaehlt:
                farbe.setAlpha(90)
            p.setPen(QPen(QColor(farbe.red(), farbe.green(), farbe.blue(), 200), 1.2 if not gewaehlt else 2.0))
            p.setBrush(QBrush(farbe))
            p.drawPolygon(QPolygonF(ecken))
            p.setBrush(Qt.NoBrush)
            griff = ebene_griff(qs, ee)
            if griff is None:
                continue
            (u, v), _ = griff
            z = sk.schnitt_x(qs, ee, u, v) + nasen_plus(ee)
            pg = self._punkt(bild, z if s == "a" else L - z, u, v)
            p.setPen(QPen(stil.farbe(EBENE), 2.0))
            p.setBrush(QBrush(stil.farbe("#FFFFFF")))
            p.drawEllipse(pg, 6, 6)
            p.setBrush(Qt.NoBrush)
            w = sw._z(ee.get("winkel"))
            p.setPen(stil.farbe(EBENE))
            p.drawText(QRectF(pg.x() + 9, pg.y() - 20, 120, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       f"{rechnen.zahl(w, 1)}°" if w else "gerade")
            richtung = self._achsrichtung(bild, (z if s == "a" else L - z, u, v))
            self._griffe.append(dict(art="ende", seite=s, punkt=pg, richtung=richtung, w0=w, abstand=griff[1],
                                     rad=8.0))

    def _achsrichtung(self, bild, xuv):
        """Bildpunkte je mm entlang der Rohrachse an der Stelle (x, u, v)."""
        x, u, v = xuv
        a, b = bild(_xyz(x, u, v)), bild(_xyz(x + 1.0, u, v))
        return QPointF(b[0] - a[0], b[1] - a[1])

    def _kontur_zeichnen(self, p, bild, r):
        g = self.kontur_geometrie(r)
        if g is None:
            return
        d0, (x, u, v), n, t = g
        L = self.laenge()
        ab = 0.4
        mitte = _xyz(x, u + n[0] * ab, v + n[1] * ab)
        s = self._massstab(bild, mitte)
        lg = GRIFF_PX / s
        pm = bild(mitte)
        pm = QPointF(pm[0], pm[1])
        la, lb = (self._punkt(bild, x - lg, u + n[0] * ab, v + n[1] * ab),
                  self._punkt(bild, x + lg, u + n[0] * ab, v + n[1] * ab))
        qa, qb = (self._punkt(bild, x, u + n[0] * ab - t[0] * lg, v + n[1] * ab - t[1] * lg),
                  self._punkt(bild, x, u + n[0] * ab + t[0] * lg, v + n[1] * ab + t[1] * lg))
        if self.masse:
            self._masse_zeichnen(p, bild, d0, (x, u, v), n, s, L)
        _pfeil(p, la, lb, stil.farbe(LAENGS))
        if math.hypot(qb.x() - qa.x(), qb.y() - qa.y()) > 12:        # quer nur, wenn nicht genau von der Seite
            _pfeil(p, qa, qb, stil.farbe(QUER))
            self._griffe.append(dict(art="quer", a=qa, b=qb, richtung=(qb - qa) / (2 * lg), zeile=r))
        self._griffe.append(dict(art="laengs", a=la, b=lb, richtung=(lb - la) / (2 * lg), zeile=r))
        p.setPen(QPen(QColor("#FFFFFF"), 1.5))     # fest: weißer Rand um den farbigen Griff
        p.setBrush(QBrush(stil.farbe(LAENGS)))
        p.drawEllipse(pm, 4.5, 4.5)
        p.setBrush(Qt.NoBrush)

    def _masse_zeichnen(self, p, bild, d0, xuv, n, s, L):
        """Maße längs: ab Ende A, bis Ende B, zur nächsten Kontur auf derselben Seite (je Doppelklick änderbar)."""
        x, u, v = xuv
        hoch = MASS_PX / s
        e0 = d0["eingabe"]
        liste = [("a", 0.0, x, x), ("b", x, L, L - x)]
        nachbar = None
        for o in self.lagen():
            if o["zeile"] == d0["zeile"] or o["eingabe"].get("seite") != e0.get("seite"):
                continue
            if nachbar is None or abs(o["x"] - x) < abs(nachbar["x"] - x):
                nachbar = o
        if nachbar is not None and abs(nachbar["x"] - x) > 1e-6:
            liste.append(("nachbar", min(x, nachbar["x"]), max(x, nachbar["x"]), abs(nachbar["x"] - x)))
        p.setPen(QPen(MASS, 1.0))
        f = QFont(p.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 0.5))
        p.setFont(f)
        fm = p.fontMetrics()
        for art, x0, x1, wert in liste:
            h = 1.0 + (1.8 if art == "nachbar" else 0.0)
            ua, va = u + n[0] * hoch * h, v + n[1] * hoch * h
            a, b = self._punkt(bild, x0, ua, va), self._punkt(bild, x1, ua, va)
            p.setPen(QPen(MASS, 1.0))
            p.drawLine(a, b)
            for xx in (x0, x1):         # Hilfslinien von der Oberfläche
                p.setPen(QPen(stil.farbe("#1F2937", 120), 0.8, Qt.DashLine))
                p.drawLine(self._punkt(bild, xx, u, v), self._punkt(bild, xx, ua + n[0] * hoch * 0.3,
                                                                    va + n[1] * hoch * 0.3))
            p.setPen(QPen(MASS, 1.0))
            for spitze, gegen in ((a, b), (b, a)):
                d = gegen - spitze
                lg = math.hypot(d.x(), d.y()) or 1.0
                ux, uy = d.x() / lg, d.y() / lg
                p.drawLine(spitze, QPointF(spitze.x() + ux * 7 - uy * 3, spitze.y() + uy * 7 + ux * 3))
                p.drawLine(spitze, QPointF(spitze.x() + ux * 7 + uy * 3, spitze.y() + uy * 7 - ux * 3))
            text = rechnen.zahl(wert, 1)
            breite = fm.horizontalAdvance(text) + 8
            m = (a + b) / 2
            rect = QRectF(m.x() - breite / 2, m.y() - 17, breite, 15)
            p.fillRect(rect, stil.farbe("#FFFFFF", 215))
            p.drawText(rect, Qt.AlignCenter, text)
            self._mass_felder.append(dict(art=art, rect=rect, wert=wert,
                                          bezug=nachbar["x"] if art == "nachbar" else None))

    # ------------------------------------------------------------------ Maus
    def treffer(self, pos):
        """Griff unter dem Mauszeiger oder None."""
        for g in self._griffe:
            if g["art"] == "ende":
                if math.hypot(pos.x() - g["punkt"].x(), pos.y() - g["punkt"].y()) <= g["rad"] + 3:
                    return g
            elif _abstand_strecke(pos, g["a"], g["b"]) <= FANG_PX:
                return g
        return None

    def schweben(self, pos):
        g = self.treffer(pos) if self.aktiv() else None
        if g is None:
            self.a.setCursor(Qt.ArrowCursor)
        else:
            self.a.setCursor(Qt.SizeAllCursor if g["art"] == "ende" else Qt.OpenHandCursor)

    def druck(self, pos, knopf):
        if knopf != Qt.LeftButton or not self.aktiv():
            return False
        if not self._griffe:
            self.a.repaint()            # Griffe der aktuellen Auswahl erst noch zeichnen
        g = self.treffer(pos)
        if g is None:
            return False
        e = self.d.eingaben()
        zug = dict(g, start=pos, jetzt=pos, e=e, zuletzt=None)
        if g["art"] != "ende":
            zug["kontur"] = dict(e["konturen"][g["zeile"]])
            geo = self.kontur_geometrie(g["zeile"])
            zug["lage"], zug["x0"] = geo[0], geo[0]["x"]
        self._zug = zug
        self.r._still = True            # kein Rückgängig-Schritt je Mausbewegung
        self.a.setCursor(Qt.ClosedHandCursor)
        return True

    def _mm(self, zug, pos):
        """Mausweg seit dem Druck in mm entlang des Griffs."""
        d = pos - zug["start"]
        r = zug["richtung"]
        lg2 = r.x() * r.x() + r.y() * r.y()
        return 0.0 if lg2 < 1e-9 else (d.x() * r.x() + d.y() * r.y()) / lg2

    def ziehen(self, pos, tasten=Qt.NoModifier):
        z = self._zug
        if z is None:
            return
        z["jetzt"] = pos
        an = self.fangen_an and not (tasten & Qt.AltModifier)
        mm = self._mm(z, pos)
        L = self.laenge()
        d = self.d
        if z["art"] == "laengs":
            x = fangen(z["x0"] + mm, self.raster, (L / 2,), an)
            neu = x_neu(z["kontur"], z["lage"], x, L)
            self.live = f"ab Ende A {rechnen.zahl(neu['x'], 1)} mm · bis Ende B {rechnen.zahl(L - neu['x'], 1)} mm"
        elif z["art"] == "quer":
            neu = quer_neu(d.qs, z["kontur"], mm, self.raster_winkel if d.qs.r else self.raster, an)
            if d.qs.r:
                self.live = f"Winkel {rechnen.zahl(neu.get('seite') or 0.0, 1)}°"
            else:
                self.live = (f"Seite {sk.seite_anzeige(d.qs, neu.get('seite') or d.qs.seiten()[0])}, quer "
                             f"{rechnen.zahl(neu.get('q') or 0.0, 1)} mm")
        else:
            s = z["seite"]
            # Griff längs ziehen: Abstand der Schnittkante zur Spitze ändert sich, tan(w) = Abstand / Hebel
            alt = math.tan(math.radians(z["w0"])) * z["abstand"]
            neu_abstand = max(0.0, alt + (mm if s == "a" else -mm))
            w = winkel_fangen(math.degrees(math.atan2(neu_abstand, z["abstand"])), an)
            neu = dict(winkel=w)
            self.live = f"Gehrung Ende {s.upper()}: {rechnen.zahl(w, 1)}°" if w else f"Ende {s.upper()}: gerade"
        if neu != z["zuletzt"]:
            z["zuletzt"] = neu
            self._anwenden(z, neu)
        self.a.update()

    def _anwenden(self, z, neu):
        d = self.d
        if z["art"] == "ende":
            d.winkel[z["seite"]].setValue(neu["winkel"])
        else:
            d._verschoben(z["zeile"], neu)
        self.r._modell_zeigen(d.eingaben())

    def loslassen(self, pos=None):
        z, self._zug = self._zug, None
        self.live = ""
        self.r._still = False
        self.a.setCursor(Qt.ArrowCursor)
        if z is not None:
            self.r.aktualisieren()      # ein Rückgängig-Schritt für den ganzen Zug
            if z["art"] == "ende":
                self.r.waehlen(f"ende:{z['seite']}")
            else:
                self.r.waehlen(f"kontur:{z['zeile']}")

    def doppelklick(self, pos):
        """Doppelklick auf ein Maß: Eingabefeld an der Stelle (Enter übernimmt, Esc bricht ab)."""
        if not self.aktiv():
            return False
        feld = next((m for m in self._mass_felder if m["rect"].adjusted(-3, -3, 3, 3).contains(pos)), None)
        r = self.zeile()
        if feld is None or r is None:
            return False
        self.mass_bearbeiten(feld, r)
        return True

    def mass_bearbeiten(self, feld, r):
        L = self.laenge()
        f = RechenFeld(feld["wert"], dict(L=L), parent=self.a)
        f.setFixedWidth(90)
        f.move(int(feld["rect"].center().x() - 45), int(feld["rect"].top() - 4))
        f.selectAll()
        f.show()
        f.setFocus()
        self._feld = f

        def fertig(wert):
            self.mass_setzen(feld, r, wert)
            f.deleteLater()
            self._feld = None
        f.wert_geaendert.connect(fertig)
        return f

    def mass_setzen(self, feld, r, wert):
        """Maß am Modell geändert: Lage der Kontur daraus (ab A, bis B, zur Nachbarkontur)."""
        if wert is None:
            return False
        L = self.laenge()
        geo = self.kontur_geometrie(r)
        if geo is None:
            return False
        x = geo[0]["x"]
        if feld["art"] == "a":
            neu = wert
        elif feld["art"] == "b":
            neu = L - wert
        else:
            b = feld["bezug"]
            neu = b + wert if x >= b else b - wert
        self.d._verschoben(r, x_neu(self.d.eingaben()["konturen"][r], geo[0], neu, L))
        self.r.waehlen(f"kontur:{r}")
        return True

    def kontext(self, pos, global_pos):
        a = self.a
        punkt = None
        if not a.messen:
            treffer = a.klicken(pos.x(), pos.y())      # wählt das Merkmal unter der Maus
            punkt = (pos.x(), pos.y()) if treffer else None
        m = self.r.kontextmenue(self.r.gewaehlt, punkt)
        m.exec(global_pos)

    def taste(self, e):
        """Pfeiltasten: gewählte Kontur um den Rasterschritt (Umschalt ×10), Ende: Gehrung ±1° (Umschalt 10°)."""
        if not self.aktiv():
            return False
        k = e.key()
        if k not in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            return False
        faktor = 10 if e.modifiers() & Qt.ShiftModifier else 1
        return self.schritt(k, faktor)

    def schritt(self, k, faktor=1):
        d = self.d
        s = self.ende()
        if s is not None:
            if k not in (Qt.Key_Up, Qt.Key_Down):
                return False
            w = sw._z(d.winkel[s].value()) + (1 if k == Qt.Key_Up else -1) * faktor
            d.winkel[s].setValue(max(0.0, min(79.9, w)))
            return True
        r = self.zeile()
        if r is None:
            return False
        geo = self.kontur_geometrie(r)
        if geo is None:
            return False
        e = d.eingaben()["konturen"][r]
        L = self.laenge()
        schritt = (self.raster if self.fangen_an and self.raster else 1.0) * faktor
        if k in (Qt.Key_Left, Qt.Key_Right):
            neu = x_neu(e, geo[0], geo[0]["x"] + (schritt if k == Qt.Key_Right else -schritt), L)
        else:
            vor = 1 if k == Qt.Key_Up else -1
            if d.qs.r:
                schritt = (self.raster_winkel if self.fangen_an and self.raster_winkel else 1.0) * faktor
                neu = quer_neu(d.qs, e, vor * math.radians(schritt) * d.qs.r, 0, an=False)
                if neu.get("seite"):
                    neu["seite"] = round(neu["seite"]) % 360 or None
            else:
                neu = quer_neu(d.qs, e, vor * schritt, 0, an=False)
        if not neu:
            return False
        d._verschoben(r, neu)
        self.r.waehlen(f"kontur:{r}")
        return True


def menue_bauen(rahmen, mid, punkt=None, parent=None):
    """Kontextmenü zum Merkmal mid (C4); punkt = Bildpunkt des Rechtsklicks im 3D (für „Messen von hier“)."""
    m = QMenu(parent)
    d = rahmen.d
    rohr = rahmen.art == "rohr"
    art, _, nr = (mid or "").partition(":")
    r = int(nr) if art == "kontur" and nr.isdigit() and int(nr) < d.tabelle.rowCount() else None
    w = getattr(rahmen, "werkzeug", None)
    merkmal = next((x for x in rahmen.merkmale if x.id == mid), None)
    from .teile_editor import GEAENDERT
    zurueck = merkmal is not None and merkmal.herkunft == GEAENDERT

    def eintrag(text, slot, an=True, taste=None):
        a = m.addAction(text + (f"\t{taste}" if taste else ""))
        a.setEnabled(bool(an))
        a.triggered.connect(slot)
        return a
    if r is not None:
        eintrag("Duplizieren", lambda: rahmen.duplizieren(r), taste="Strg+D")
        if rohr:
            eintrag("Spiegeln zur Teilmitte", lambda: rahmen.spiegeln(r))
            eintrag("Auf die Gegenseite", lambda: rahmen.gegenseite(r))
        eintrag("Auf STEP-Wert zurücksetzen", lambda: rahmen.zuruecksetzen(mid), zurueck)
        if rohr and d.tabelle.cellWidget(r, 0).currentText() in sw.MIT_FASE:      # G6: Ecken runden/fasen
            em = m.addMenu("Ecken")
            em.addAction("Runden …", lambda: rahmen.ecken_fragen(r, "runden"))
            em.addAction("Fasen …", lambda: rahmen.ecken_fragen(r, "fasen"))
            em.addAction("Scharf", lambda: rahmen.ecken(r, "scharf"))
        eintrag("Entfernen", lambda: rahmen.entfernen(r), taste="Entf")
        eintrag("Als Kontur-Vorlage speichern …", lambda: rahmen._vorlage_speichern_fragen(),
                getattr(d, "db", None) is not None)
    elif art == "ende" and rohr:
        eintrag("Gerade schneiden (0°)", lambda: d.winkel[nr].setValue(0))
        eintrag("Gehrung 45°", lambda: d.winkel[nr].setValue(45))
        eintrag("Gegenrohr …", lambda: d.gegenrohr(nr), d.gegen_knopf[nr].isEnabled())
        if d.gegen.get(nr):
            eintrag("Gegenrohr entfernen", lambda: d.gegenrohr(nr, None))
        eintrag("Auf STEP-Wert zurücksetzen", lambda: rahmen.zuruecksetzen(mid), zurueck)
    if punkt is not None and rahmen.ansicht() is not None:
        m.addSeparator()
        eintrag("Messen von hier", lambda: rahmen.messen_ab(punkt))
    a3 = rahmen.ansicht()
    if a3 is not None:
        m.addSeparator()
        dm = m.addMenu("Darstellung")
        gruppe = QActionGroup(dm)
        for name in DARSTELLUNGEN:
            x = QAction(name, dm, checkable=True)
            x.setChecked(a3.darstellung == name)
            x.triggered.connect(lambda _=False, n=name: rahmen.darstellung_setzen(n))
            gruppe.addAction(x)
            dm.addAction(x)
        dm.addSeparator()
        x = dm.addAction("Nur Gewähltes hervorheben")
        x.setCheckable(True)
        x.setChecked(a3.nur_gewaehlt)
        x.triggered.connect(lambda an: rahmen.darstellung_setzen(nur_gewaehlt=an))
        if rohr and w is not None:
            for text, attr in (("Schnittebenen", "ebenen"), ("Maße am Modell", "masse")):
                x = dm.addAction(text)
                x.setCheckable(True)
                x.setChecked(getattr(w, attr))
                x.triggered.connect(lambda an, attr=attr: rahmen.anzeige_setzen(attr, an))
        eintrag("Ausgangsansicht", lambda: a3.zuruecksetzen())
    return m
