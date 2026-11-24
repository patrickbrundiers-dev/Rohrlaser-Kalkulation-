"""Explosionszeichnung (Auftrag Patrick 20.11.2026): Bild der Explosionsansicht, wie gerade zu sehen (mit
Positionsnummern), und Stückliste als PDF (A4 quer) oder PNG. Nur Druck: immer weißes Blatt, feste Farben."""
from PySide6.QtCore import QRectF, Qt

SPALTEN = (("nr", "Nr."), ("pos", "Pos."), ("artikel", "Artikel"), ("bezeichnung", "Bezeichnung"),
           ("werkstoff", "Werkstoff"), ("profil", "Profil"), ("wand", "Wand"), ("menge", "Anz."))


def _wert(z, n):
    v = z.get(n)
    if v in (None, ""):
        return ""
    if n == "wand":
        try:
            return f"{float(v):g} mm"
        except (TypeError, ValueError):
            return str(v)
    return str(v)


def _malen(p, breite, hoehe, bild, zeilen, titel):
    """Explosionszeichnung auf p: Titel, Bild der Ansicht (links bzw. oben), Stückliste (rechts bzw. unten)."""
    from PySide6.QtGui import QColor, QFont, QPen
    p.fillRect(QRectF(0, 0, breite, hoehe), QColor("#FFFFFF"))
    f = QFont(p.font())
    f.setPointSizeF(13)
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#1F3F73"))
    p.drawText(QRectF(0, 0, breite, hoehe * 0.06), Qt.AlignLeft | Qt.AlignVCenter, titel)
    f.setBold(False)
    f.setPointSizeF(8)
    p.setFont(f)
    p.setPen(QColor("#555555"))
    p.drawText(QRectF(0, 0, breite, hoehe * 0.06), Qt.AlignRight | Qt.AlignVCenter,
               "Explosionsdarstellung – nur Anzeige, Lage der Teile laut STEP")
    oben = hoehe * 0.07
    quer = breite > hoehe
    tab_b = breite * 0.36 if quer else breite
    bild_r = QRectF(0, oben, breite - tab_b - 12, hoehe - oben) if quer else QRectF(0, oben, breite, (hoehe - oben) * 0.6)
    sk = min(bild_r.width() / max(1, bild.width()), bild_r.height() / max(1, bild.height()))
    p.drawImage(QRectF(bild_r.x(), bild_r.y(), bild.width() * sk, bild.height() * sk), bild, QRectF(bild.rect()))
    tab = QRectF(breite - tab_b, oben, tab_b, hoehe - oben) if quer else QRectF(0, bild_r.bottom() + 10, breite,
                                                                                  hoehe - bild_r.bottom() - 10)
    spalten = list(SPALTEN)
    gewicht = [0.07, 0.08, 0.2, 0.25, 0.14, 0.14, 0.07, 0.05]
    if all(str(z.get("pos") or "") in ("", str(z["nr"])) for z in zeilen):     # Nr. = Pos.: eine Spalte
        del spalten[1], gewicht[1]
        gewicht[2] += 0.08
    zeile_h = max(10.0, min(tab.height() / max(2, len(zeilen) + 1), hoehe * 0.024))
    f.setPointSizeF(max(5.0, min(8.0, zeile_h * 72 / max(1, p.device().logicalDpiY()) * 0.62)))
    p.setFont(f)
    x = tab.x()
    xs = []
    for g in gewicht:
        xs.append(x)
        x += g * tab.width()
    p.setPen(QPen(QColor("#1F3F73"), 1))
    for i, (_, kopf) in enumerate(spalten):
        p.fillRect(QRectF(xs[i], tab.y(), gewicht[i] * tab.width(), zeile_h), QColor("#E8EEF6"))
        p.drawText(QRectF(xs[i] + 2, tab.y(), gewicht[i] * tab.width() - 4, zeile_h), Qt.AlignLeft | Qt.AlignVCenter,
                   kopf)
    p.setPen(QColor("#202020"))
    platz = int((tab.height() - zeile_h) // zeile_h)
    for r, z in enumerate(zeilen[:platz]):
        y = tab.y() + zeile_h * (r + 1)
        if r % 2:
            p.fillRect(QRectF(tab.x(), y, tab.width(), zeile_h), QColor("#F6F8FB"))
        for i, (n, _) in enumerate(spalten):
            p.drawText(QRectF(xs[i] + 2, y, gewicht[i] * tab.width() - 4, zeile_h), Qt.AlignLeft | Qt.AlignVCenter,
                       _wert(z, n))
    if len(zeilen) > platz:
        p.drawText(QRectF(tab.x(), tab.bottom() - zeile_h, tab.width(), zeile_h), Qt.AlignLeft | Qt.AlignVCenter,
                   f"… und {len(zeilen) - platz} weitere Positionen")


def zeichnung_speichern(a, pfad):
    """Explosionszeichnung (Bild der Ansicht, wie gerade zu sehen, mit Positionsnummern und Stückliste) als PDF
    (A4 quer) oder PNG. Ergebnis: Pfad."""
    from PySide6.QtCore import QMarginsF
    from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter, QPdfWriter
    if a.explo.beschriftung == "Aus":
        a.explo.beschriftung = "Positionsnummer"
        a.update()
    bild = a.grab().toImage()
    from .explosion_dialog import stueckliste
    zeilen = stueckliste(a)
    titel = " · ".join(t for t in (a.titel or "Baugruppe", "Explosionszeichnung") if t)
    pfad = str(pfad)
    if pfad.lower().endswith(".pdf"):
        w = QPdfWriter(pfad)
        w.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Landscape, QMarginsF(10, 10, 10, 10)))
        w.setResolution(150)
        w.setTitle(titel)
        p = QPainter(w)
        try:
            r = p.viewport()
            _malen(p, r.width(), r.height(), bild, zeilen, titel)
        finally:
            p.end()
    else:
        if not pfad.lower().endswith(".png"):
            pfad += ".png"
        ziel = QImage(1754, 1240, QImage.Format_RGB32)
        p = QPainter(ziel)
        try:
            _malen(p, ziel.width(), ziel.height(), bild, zeilen, titel)
        finally:
            p.end()
        ziel.save(pfad, "PNG")
    return pfad
