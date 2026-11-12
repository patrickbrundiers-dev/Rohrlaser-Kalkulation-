"""Kontur aus einem Scan oder Raster-PDF nachzeichnen (Plan Paket K2).

Ablauf: Bild bzw. PDF-Seite laden (Graustufen), auf höchstens MAX_PIXEL verkleinern, dunkel/hell trennen. Zwei Arten:
- Linienzeichnung (Umriss und Löcher als Striche): Außen ist, was vom Bildrand hell erreichbar ist. Der Teil-Umriss
  ist die Mitte des äußeren Strichs (Silhouette um die halbe Strichbreite verkleinert), jedes Loch die Mitte seines
  Strichs (helle Fläche im Teil um die halbe Strichbreite vergrößert).
- Fläche (gefülltes Teil, z. B. Schattenriss): der Rand der größten dunklen Fläche und ihre hellen Löcher.
Die Pixelränder werden geglättet, Abschnitte auf einem Kreis werden echte Bögen (dxf.boegen, Toleranz ein Pixel),
gerade Stücke werden zusammengefasst. Das Ergebnis geht als DXF-Text durch den DXF-Import (dxf_import.importieren),
damit Bohrungen, Langlöcher und Rechtecke genauso erkannt werden wie aus einer echten DXF.

Maßstab: Breite des Teils in mm (Vorgabe aus der Auflösung des Bildes, wenn bekannt). Genauigkeit: etwa ein Pixel;
das Ergebnis ist ein Vorschlag zum Prüfen, kein Ersatz für eine CAD-Datei.
"""
import math
from pathlib import Path

MAX_PIXEL = 1600            # längere Bildseite höchstens so viele Pixel (Rechenzeit in Python)
PDF_DPI = 200               # PDF-Seiten so rendern
MIN_LOCH_PX = 12            # kleinere helle Flächen (Schmutz, Schrift) sind keine Löcher [Pixel Fläche]
GLAETTEN = 2                # gleitender Mittelwert über ±so viele Randpunkte (Treppen der Pixel weg)
GERADE_PX = 3               # Bögen mit höchstens so viel Pixel Pfeilhöhe sind im Scan Geraden
ECKE_ABSTAND = 4            # Ecken: Richtung über ±so viele Randpunkte (Pixel) vergleichen
ECKE_WINKEL = 30.0          # ab so viel Grad Richtungswechsel ist dort eine Ecke
LINIEN, FLAECHE, AUTO = "Linienzeichnung", "Fläche (gefüllt)", "Automatisch"
ARTEN = (AUTO, LINIEN, FLAECHE)
BILD_FILTER = "Bild oder PDF (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.gif *.pdf)"


# ------------------------------------------------------------------ Bild
def laden(pfad, seite=0):
    """(Graustufenbild PIL, mm je Pixel oder None, Seitenzahl). PDF: Seite mit PDF_DPI gerendert (mm je Pixel aus
    der Seitengröße); Bild: aus der gespeicherten Auflösung, wenn vorhanden."""
    from PIL import Image
    pfad = Path(pfad)
    if pfad.suffix.lower() == ".pdf":
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(pfad))
        try:
            n = len(pdf)
            s = pdf[max(0, min(int(seite), n - 1))]
            b = s.render(scale=PDF_DPI / 72).to_pil().convert("L")
        finally:
            pdf.close()
        return b, 25.4 / PDF_DPI, n
    with Image.open(pfad) as roh:
        dpi = (roh.info or {}).get("dpi")
        b = roh.convert("L")
    mm = None
    if dpi and float(dpi[0] or 0) > 1 and abs(float(dpi[0]) - 72) > 0.5:     # 72 dpi = keine echte Angabe
        mm = 25.4 / float(dpi[0])
    return b, mm, 1


def verkleinert(b):
    """(Bild, Faktor alte Pixel je neuem Pixel)."""
    f = max(b.width, b.height) / MAX_PIXEL
    if f <= 1:
        return b, 1.0
    from PIL import Image
    return b.resize((max(1, round(b.width / f)), max(1, round(b.height / f))), Image.LANCZOS), f


def schwelle_otsu(b):
    """Grauwert, der dunkel und hell am besten trennt (Otsu)."""
    h = b.histogram()[:256]
    n = sum(h) or 1
    summe = sum(i * c for i, c in enumerate(h))
    best, wb, sb, gut = 128, 0, 0.0, -1.0
    for t in range(256):
        wb += h[t]
        if wb == 0 or wb == n:
            continue
        sb += t * h[t]
        mb, mf = sb / wb, (summe - sb) / (n - wb)
        v = wb * (n - wb) * (mb - mf) ** 2
        if v > gut:
            best, gut = t, v
    return best


# ------------------------------------------------------------------ Masken
def _maske(b, schwelle):
    """Bild mit Rand 1 Pixel hell: 255 = dunkel (Strich), 0 = hell."""
    from PIL import Image, ImageOps
    m = b.point(lambda v: 255 if v <= schwelle else 0)
    return ImageOps.expand(m, border=1, fill=0) if isinstance(m, Image.Image) else m


def _bereiche(m, wert):
    """[(Startpixel, Pixelzahl, Pixel)] der zusammenhängenden Flächen (4er-Nachbarn) mit diesem Wert."""
    w, h = m.size
    d = m.tobytes()
    frei = [v == wert for v in d]
    out = []
    for start in range(len(d)):
        if not frei[start]:
            continue
        stapel, pix = [start], []
        frei[start] = False
        while stapel:
            i = stapel.pop()
            pix.append(i)
            x = i % w
            for j in (i - 1 if x > 0 else -1, i + 1 if x < w - 1 else -1, i - w, i + w):
                if 0 <= j < len(d) and frei[j]:
                    frei[j] = False
                    stapel.append(j)
        out.append((start, len(pix), pix))
    return out


def _bild_aus(pixel, w, rand=2):
    """(Bild 255 = Pixel der Liste, Versatz (x0, y0)): auf das umschließende Rechteck mit Rand zugeschnitten."""
    from PIL import Image
    xs = [i % w for i in pixel]
    ys = [i // w for i in pixel]
    x0, y0 = min(xs) - rand, min(ys) - rand
    m = Image.new("L", (max(xs) - x0 + rand + 1, max(ys) - y0 + rand + 1), 0)
    px = m.load()
    for x, y in zip(xs, ys):
        px[x - x0, y - y0] = 255
    return m, (x0, y0)


def _raender(m, versatz=(0, 0)):
    """Geschlossene Randzüge der Fläche 255 in m auf den Pixelecken (um versatz verschoben): [(Punkte, Fläche)],
    Fläche > 0 = Außenrand (y nach unten gezählt)."""
    w, h = m.size
    px = m.load()
    ox, oy = versatz

    def drin(x, y):
        return 0 <= x < w and 0 <= y < h and px[x, y] == 255
    nach = {}
    for y in range(h):
        for x in range(w):
            if px[x, y] != 255:
                continue
            if not drin(x - 1, y):
                nach.setdefault((x, y), []).append((x, y + 1))
            if not drin(x, y + 1):
                nach.setdefault((x, y + 1), []).append((x + 1, y + 1))
            if not drin(x + 1, y):
                nach.setdefault((x + 1, y + 1), []).append((x + 1, y))
            if not drin(x, y - 1):
                nach.setdefault((x + 1, y), []).append((x, y))
    out = []
    while nach:
        start = next(iter(nach))
        zug, p = [start], start
        while True:
            ziele = nach.get(p)
            if not ziele:
                break
            q = ziele.pop()
            if not ziele:
                del nach[p]
            if q == start:
                break
            zug.append(q)
            p = q
        if len(zug) >= 4:
            a = sum(zug[i][0] * zug[(i + 1) % len(zug)][1] - zug[(i + 1) % len(zug)][0] * zug[i][1]
                    for i in range(len(zug))) / 2
            out.append(([(x + ox, y + oy) for x, y in zug], a))
    return out


def _groesster_rand(m, versatz=(0, 0)):
    rr = _raender(m, versatz)
    return max(rr, key=lambda t: abs(t[1]))[0] if rr else None


def _filter(m, r, groesser):
    """Fläche 255 um r Pixel vergrößern bzw. verkleinern (Max-/Min-Filter)."""
    if r < 1:
        return m
    from PIL import ImageFilter
    return m.filter((ImageFilter.MaxFilter if groesser else ImageFilter.MinFilter)(2 * r + 1))


# ------------------------------------------------------------------ Züge
def _glatt(zug, k=GLAETTEN):
    n = len(zug)
    if n < 2 * k + 3:
        return [(float(x), float(y)) for x, y in zug]
    return [(sum(zug[(i + j) % n][0] for j in range(-k, k + 1)) / (2 * k + 1),
             sum(zug[(i + j) % n][1] for j in range(-k, k + 1)) / (2 * k + 1)) for i in range(n)]


def _umfang(zug):
    """Länge des geglätteten Randzugs [Pixel] (die Treppe der Pixelkanten wäre bei Schrägen zu lang)."""
    if not zug:
        return 0.0
    g = _glatt(zug)
    return sum(math.dist(g[i], g[(i + 1) % len(g)]) for i in range(len(g)))


def _dp(pk, tol):
    """Douglas-Peucker für einen offenen Zug."""
    if len(pk) < 3:
        return list(pk)
    a, b = pk[0], pk[-1]
    lg = math.dist(a, b) or 1e-12
    best, idx = -1.0, 0
    for i in range(1, len(pk) - 1):
        d = abs((b[0] - a[0]) * (a[1] - pk[i][1]) - (a[0] - pk[i][0]) * (b[1] - a[1])) / lg
        if d > best:
            best, idx = d, i
    if best <= tol:
        return [a, b]
    return _dp(pk[:idx + 1], tol)[:-1] + _dp(pk[idx:], tol)


def _ausduennen(zug, schritt=2):
    if len(zug) <= 40:
        return list(zug)
    out = list(zug[::schritt])
    if out[-1] != zug[-1]:
        out.append(zug[-1])
    return out


def _glatt_offen(pk, k=GLAETTEN):
    """Gleitender Mittelwert eines offenen Zugs; Anfang und Ende bleiben (Ecken)."""
    n = len(pk)
    out = []
    for i in range(n):
        h = min(k, i, n - 1 - i)
        out.append((sum(pk[j][0] for j in range(i - h, i + h + 1)) / (2 * h + 1),
                    sum(pk[j][1] for j in range(i - h, i + h + 1)) / (2 * h + 1)))
    return out


def ecken(zug, abstand=ECKE_ABSTAND, grenze=ECKE_WINKEL):
    """Indizes der Ecken eines geschlossenen Pixelzugs: Richtung ändert sich über ±abstand Punkte um mehr als
    grenze Grad (am stärksten in der Nachbarschaft)."""
    g = _glatt(zug)
    n = len(g)
    if n < 4 * abstand:
        return []
    w = []
    for i in range(n):
        a, b, c = g[i - abstand], g[i], g[(i + abstand) % n]
        t = math.degrees(math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(b[1] - a[1], b[0] - a[0]))
        w.append(abs((t + 180) % 360 - 180))
    return [i for i in range(n) if w[i] > grenze and all(w[i] >= w[(i + j) % n] for j in range(-abstand, abstand + 1))
            and not any(w[i] == w[(i + j) % n] and j < 0 for j in range(-abstand, 0))]


def _zug_elemente(pk, tol, tol_linie):
    """Offener Zug (mm) -> Linien und Bögen."""
    from . import dxf
    return _linien_zusammen(dxf._zug_boegen(dxf.AUSSEN, pk, tol, gerade_tol=GERADE_PX * tol), tol_linie)


def elemente(zuege, mm, hoehe, tol_px=1.0):
    """DXF-Elemente (dxf: LINE/ARC/CIRCLE) der geschlossenen Züge in mm, y nach oben: an Ecken geteilt (Ecken
    bleiben scharf), dazwischen Bögen, wo die Punkte auf einem Kreis liegen (tol_px), sonst Linien, gerade Stücke
    zusammengefasst."""
    from . import dxf
    out = []

    def in_mm(q):
        return q[0] * mm, (hoehe - q[1]) * mm
    for zug in zuege:
        rund = [in_mm(q) for q in _ausduennen(_glatt(zug))]
        kreis = dxf._vollkreis(rund, tol_px * mm) if len(rund) >= 8 else None
        if kreis is not None:               # ganzer Kreis (auch klein, wo der Ecken-Test anspräche)
            out.append(dxf._kreis(dxf.AUSSEN, kreis[0], kreis[1]))
            continue
        ek = ecken(zug)
        if not ek:
            pk = rund
            if len(pk) >= 3:
                out += _linien_zusammen(dxf.boegen(dxf._polygon(dxf.AUSSEN, pk), tol=tol_px * mm), 0.5 * tol_px * mm)
            continue
        el = []
        for a, b in zip(ek, ek[1:] + [ek[0] + len(zug)]):
            stueck = [zug[i % len(zug)] for i in range(a, b + 1)]
            pk = [in_mm(q) for q in _ausduennen(_glatt_offen(stueck))]
            if len(pk) >= 2:
                el.append(_zug_elemente(pk, tol_px * mm, 0.5 * tol_px * mm))
        kurz = 2 * ECKE_ABSTAND * mm        # Stummel an der Ecke (Treppe der Pixel) fallen weg
        for t in el:
            while len(t) > 1 and t[0][0] == "LINE" and math.dist(t[0][2], t[0][3]) < kurz:
                del t[0]
            while len(t) > 1 and t[-1][0] == "LINE" and math.dist(t[-1][2], t[-1][3]) < kurz:
                del t[-1]
        el = [t for t in el if t]
        for k in range(len(el)):           # Ecke: beide Geraden bis zum Schnittpunkt verlängern, sonst verbinden
            v, n = el[k - 1], el[k]
            p = None
            if v[-1][0] == "LINE" and n[0][0] == "LINE":
                p = _schnitt(v[-1][2], v[-1][3], n[0][2], n[0][3])
                if p is not None and math.dist(p, v[-1][3]) < 2 * kurz and math.dist(p, n[0][2]) < 2 * kurz:
                    v[-1] = dxf._linie(v[-1][1], v[-1][2], p)
                    n[0] = dxf._linie(n[0][1], p, n[0][3])
                else:
                    p = None
            if p is None:               # Lücke schließen: die einander nächsten Endpunkte verbinden
                ende, anfang = min(((q, w) for q in _ecken_punkte(v[-1]) for w in _ecken_punkte(n[0])),
                                   key=lambda t: math.dist(*t))
                if math.dist(ende, anfang) > 1e-9:
                    n.insert(0, dxf._linie(dxf.AUSSEN, ende, anfang))
        out += [x for t in el for x in t]
    return out


def _ecken_punkte(x):
    """Die beiden Endpunkte eines LINE/ARC."""
    if x[0] == "LINE":
        return [x[2], x[3]]
    m, r = x[2], x[3]
    return [(m[0] + r * math.cos(math.radians(w)), m[1] + r * math.sin(math.radians(w))) for w in (x[4], x[5])]


def _schnitt(a0, a1, b0, b1):
    """Schnittpunkt der Geraden a0-a1 und b0-b1 oder None (parallel)."""
    d1 = (a1[0] - a0[0], a1[1] - a0[1])
    d2 = (b1[0] - b0[0], b1[1] - b0[1])
    n = d1[0] * d2[1] - d1[1] * d2[0]
    if abs(n) < 1e-12:
        return None
    t = ((b0[0] - a0[0]) * d2[1] - (b0[1] - a0[1]) * d2[0]) / n
    return a0[0] + t * d1[0], a0[1] + t * d1[1]


def _linien_zusammen(el, tol):
    """Aufeinanderfolgende LINE-Stücke mit Douglas-Peucker zusammenfassen (Bögen und Kreise bleiben)."""
    from . import dxf
    out, lauf = [], []

    def fertig():
        if lauf:
            pk = [lauf[0][2]] + [x[3] for x in lauf]
            if len(pk) > 3 and math.dist(pk[0], pk[-1]) <= 1e-9:      # geschlossen: am fernsten Punkt teilen
                k = max(range(len(pk)), key=lambda i: math.dist(pk[0], pk[i]))
                pk = _dp(pk[:k + 1], tol)[:-1] + _dp(pk[k:], tol)
            else:
                pk = _dp(pk, tol)
            out.extend(dxf._linie(lauf[0][1], a, b) for a, b in zip(pk, pk[1:]) if math.dist(a, b) > 1e-9)
    for x in el:
        if x[0] == "LINE" and (not lauf or math.dist(lauf[-1][3], x[2]) <= 1e-9):
            lauf.append(x)
            continue
        fertig()
        lauf = [x] if x[0] == "LINE" else []
        if x[0] != "LINE":
            out.append(x)
    fertig()
    return out


# ------------------------------------------------------------------ Nachzeichnen
def nachzeichnen(b, schwelle=None, art=AUTO):
    """Bild (PIL, Graustufen) -> dict(zuege [Pixelzüge, der erste ist der Umriss], art, schwelle, strich [Pixel],
    groesse (w, h) des verkleinerten Bildes, faktor (Originalpixel je Pixel)). ValueError, wenn kein Teil da ist."""
    from PIL import ImageDraw
    k, faktor = verkleinert(b)
    schwelle = schwelle_otsu(k) if schwelle is None else int(schwelle)
    m = _maske(k, schwelle)
    dunkel = m.tobytes().count(255)
    if not dunkel:
        raise ValueError("Im Bild ist nichts Dunkles: Schwelle höher stellen oder anderes Bild wählen.")
    aussen = m.copy()
    ImageDraw.floodfill(aussen, (0, 0), 128)            # hell und vom Rand erreichbar = außen
    silh = aussen.point(lambda v: 0 if v == 128 else 255)
    flaeche = silh.tobytes().count(255)
    if art == AUTO:
        art = FLAECHE if dunkel > 0.6 * flaeche else LINIEN
    teile = _bereiche(silh, 255)
    if not teile:
        raise ValueError("Kein geschlossener Umriss im Bild.")
    _, _, pix = max(teile, key=lambda t: t[1])         # größtes Teil; Schrift und Bemaßung daneben fallen weg
    w = silh.size[0]
    md = m.tobytes()
    hell = [i for i in pix if md[i] == 0]
    flecken = []                                        # helle Flächen im Teil
    if hell:
        hm, hv = _bild_aus(hell, w, 1)
        flecken = [(n, [((i % hm.size[0]) + hv[0]) + ((i // hm.size[0]) + hv[1]) * w for i in p])
                   for _, n, p in _bereiche(hm, 255) if n >= MIN_LOCH_PX]
    strich = 0
    tm, tv = _bild_aus(pix, w, 2)
    if art == LINIEN:
        flecken.sort(key=lambda t: -t[0])
        loecher = flecken[1:]                           # der größte helle Fleck ist das Blech zwischen den Strichen
        dunkel_pix = [i for i in pix if md[i] == 255]
        rand = sum(_umfang(z) for z, _ in _raender(*_bild_aus(dunkel_pix, w, 1)))     # beide Seiten jedes Strichs
        strich = max(1, round(2 * (len(pix) - len(hell)) / max(rand, 1)))       # Strichbreite [Pixel]
        r = strich // 2
        umriss = _groesster_rand(_filter(tm, r, False), tv)
        if not umriss:
            raise ValueError("Der Umriss ist schmaler als der Strich: Bild mit höherer Auflösung wählen.")
        zuege = [umriss]
        for _, lp in loecher:
            lm, lv = _bild_aus(lp, w, r + 2)
            z = _groesster_rand(_filter(lm, r, True), lv)
            if z:
                zuege.append(z[::-1])
    else:
        umriss = _groesster_rand(tm, tv)
        zuege = [umriss] + [z[::-1] for z in (_groesster_rand(*_bild_aus(p, w, 1)) for _, p in flecken) if z]
    zuege = [[(x - 1, y - 1) for x, y in z] for z in zuege]          # Rand von _maske wieder ab
    return dict(zuege=zuege, art=art, schwelle=schwelle, strich=strich, groesse=k.size, faktor=faktor)


def mm_je_pixel(erg, breite_mm):
    """mm je Pixel des verkleinerten Bildes aus der gewünschten Breite des Umrisses."""
    b = breite_px(erg)
    if b <= 0 or not breite_mm or breite_mm <= 0:
        raise ValueError("Breite des Teils in mm eingeben.")
    return float(breite_mm) / b


def breite_px(erg):
    """Breite des geglätteten Umrisses [Pixel des verkleinerten Bildes]."""
    xs = [x for x, _ in _glatt(erg["zuege"][0])]
    return max(xs) - min(xs)


def dxf_text(erg, mm):
    """DXF-Text der nachgezeichneten Züge (Umriss und Löcher) in mm."""
    from . import dxf
    return dxf.schreiben(elemente(erg["zuege"], mm, erg["groesse"][1]))


def teil(erg, mm, name="Scan"):
    """Blech-Eingaben (dict wie aus dem DXF-Import: Form, Punkte, Konturen) und Zusammenfassung."""
    from . import dxf_import
    imp = dxf_import.importieren(dxf_text(erg, mm), name, massstab=1.0)
    if not imp.get("teile"):
        raise ValueError("Aus dem Bild ist kein geschlossenes Teil entstanden.")
    t = max(imp["teile"], key=lambda t: (t["e"].get("laenge") or 0) * (t["e"].get("breite") or 0))
    return t["e"], t.get("zusammenfassung") or ""


def rohr_konturen(e, laenge, mit_umriss):
    """Konturzeilen für den Rohr-Editor: Löcher (und auf Wunsch der Umriss als Polygon) auf der ersten Fläche (0°,
    oben), die Mitte des Bildes in der Mitte der Rohrlänge, quer mittig."""
    from . import blech, dxf_import, schneidweg as sw
    lg, br = float(e.get("laenge") or 0), float(e.get("breite") or 0)
    dx = float(laenge or 0) / 2 - lg / 2
    out = []
    if mit_umriss:
        if e.get("form") == blech.POLYGON and e.get("punkte"):
            roh = sw.punkte_roh(e["punkte"])
            pk = sw.punkte(e["punkte"])
            mx, my = sum(x for x, _ in pk) / len(pk), sum(y for _, y in pk) / len(pk)
            text = dxf_import.punkte_text([(x, y) for x, y, _ in roh], [b for *_, b in roh], mx, my)
            out.append(dict(art=sw.POLYGON, anzahl=1, punkte=text, x=round(mx + dx, 3), q=round(my - br / 2, 3)))
        else:
            out.append(dict(art=sw.RECHTECK, anzahl=1, b=round(lg, 3), h=round(br, 3), r=float(e.get("eckradius")
                                                                                              or 0),
                            x=round(lg / 2 + dx, 3), q=0.0))
    for z in e.get("konturen") or ():
        z = dict(z)
        y = float(z.pop("y", br / 2) or 0)
        z.update(x=round(float(z.get("x") or 0) + dx, 3), q=round(y - br / 2, 3))      # erste Fläche (0°)
        out.append(z)
    return out
