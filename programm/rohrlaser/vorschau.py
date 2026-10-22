"""Kleine Vorschaubilder der Positionsliste für Teile ohne STEP-Daten (selbst angelegt): Rohr / Profil als
Draufsicht mit Enden (Gehrung) und Innenkonturen aus dem Schneidweg-Rechner, Blechteil als Zuschnitt bzw. Abwicklung
aus dem Blech-Editor. Teile aus dem STEP-Import zeigen ihr 3D-Bild (ansicht3d.vorschaubild)."""
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QBrush, QPainter, QPen, QPixmap, QPolygonF

from . import blech, schneidweg as sw, skizze as sk
from .skizze_widget import FARBE_FLAECHE, FARBE_KONTUR, FARBE_TEIL

MIN_BAND = 6            # Breite des Rohrs im Bild mindestens [px], auch bei langen dünnen Teilen


def _leer(breite, hoehe, dpr):
    bild = QPixmap(int(breite * dpr), int(hoehe * dpr))
    bild.setDevicePixelRatio(dpr)
    bild.fill(Qt.transparent)
    return bild


def _schraege(sil):
    """Wie stark die Enden in dieser Ansicht schräg erscheinen [mm]."""
    return sum(max(z[i] for z in sil) - min(z[i] for z in sil) for i in (1, 4))


def rohr(p, profil, breite=64, hoehe=18, dpr=2.0):
    """Draufsicht (bzw. Seitenansicht, wenn dort die Gehrungen zu sehen sind) des Rohrs/Profils der Position p
    (Länge, Enden und Konturen aus positionen.technik) oder None ohne Profil oder Länge. Quer wird gestreckt, damit
    dünne Teile sichtbar bleiben."""
    L = sw._z(p.get("laenge"))
    if not profil or L <= 0:
        return None
    try:
        qs = sk.Querschnitt(profil)
        e = sw.aus_position(sw.lesen(p.get("technik")), p, profil)[0]
        lagen = sk.lagen(e.get("konturen"), L)
        formen = [sk.platzieren(qs, d) for d in lagen]
        # die Ansicht, die mehr zeigt (sichtbare Konturen, Gehrung zählt doppelt); gleich: Draufsicht
        silh = {a: sk.silhouette(qs, e["a"], e["b"], L, a, n=24) for a in ("oben", "vorne")}
        ansicht = max(("oben", "vorne"), key=lambda a: (
            sum(sk.sichtbar(n, a) >= 0.12 for _, n in formen) + (2 if _schraege(silh[a]) > 1 else 0), a == "oben"))
        sil = silh[ansicht]
    except (ValueError, KeyError, TypeError, ZeroDivisionError):
        return None
    oben = ansicht == "oben"
    lo, hi = (-qs.B / 2, qs.B / 2) if oben else (-qs.H / 2, qs.H / 2)
    sx = (breite - 2) / L
    band = min(max((hi - lo) * sx, MIN_BAND), hoehe - 2)
    sy = band / max(hi - lo, 1e-6)
    y0 = (hoehe - band) / 2

    def pkt(x, w):          # Draufsicht: w = u (vorne unten), Seitenansicht: w = v (oben oben)
        return QPointF(1 + x * sx, y0 + ((w - lo) if oben else (hi - w)) * sy)

    bild = _leer(breite, hoehe, dpr)
    g = QPainter(bild)
    g.setRenderHint(QPainter.Antialiasing)
    g.setPen(QPen(FARBE_TEIL, 1.0))
    g.setBrush(QBrush(FARBE_FLAECHE))
    g.drawPolygon(QPolygonF([pkt(z[1], z[0]) for z in sil] + [pkt(z[4], z[0]) for z in reversed(sil)]))
    g.setPen(QPen(FARBE_KONTUR, 0.8))
    g.setBrush(QBrush(FARBE_KONTUR))
    for pts3, n in formen:
        if sk.sichtbar(n, ansicht) < 0.12:
            continue                # auf der Rückseite oder von der Kante gesehen
        poly = QPolygonF([pkt(q[0], q[1 if oben else 2]) for q in pts3])
        r = poly.boundingRect()
        if r.width() < 2 and r.height() < 2:
            g.drawEllipse(r.center(), 1.0, 1.0)
        else:
            g.drawPolygon(poly)
    g.end()
    return bild


def blech_bild(e, breite=64, hoehe=18, dpr=2.0):
    """Zuschnitt bzw. Abwicklung des Blechteils (Eingaben des Blech-Editors) oder None ohne Maße."""
    from .blech_dialog import BlechSkizze
    try:
        zs = blech.zuschnitt(e)
    except (ValueError, TypeError, ZeroDivisionError):
        return None
    w = BlechSkizze(mini=True)
    w.setzen(e, zs)
    w.resize(breite, hoehe)
    bild = _leer(breite, hoehe, dpr)
    w.render(bild, QPointF(0, 0).toPoint(), renderFlags=w.RenderFlag.DrawChildren)
    return bild


def bild(p, profil, breite=64, hoehe=18, dpr=2.0):
    """Vorschau einer selbst angelegten Position: Blech-Editor-Teil oder Rohr/Profil; sonst None."""
    e = blech.lesen(p.get("technik"))
    if e:
        return blech_bild(e, breite, hoehe, dpr)
    return rohr(p, profil, breite, hoehe, dpr)
