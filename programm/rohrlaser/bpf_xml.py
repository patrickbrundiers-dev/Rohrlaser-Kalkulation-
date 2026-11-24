"""BLM-BPF als XML lesen, für die Produktionsdaten-Intelligenz (maschinendaten.py). Kopie der reinen Lesefunktionen aus
step_messung/step_blm.py: das Paket step_messung gehört zur STEP-Messung (eigener Prozess mit OCP) und steht im
Windows-Paket des Hauptprogramms nicht zum Import bereit. Nur Standardbibliothek. tests/test_produktionsdaten_intelligenz.py
prüft, dass beide gleich lesen. Ohne Qt."""
import math
import xml.etree.ElementTree as ET
import zlib

KENNUNG = b"\xe5\xe3\xd2\x9e"
KREIS_TOL = 0.005       # Schneidweg bzw. Netzpunkte gelten als Kreis bis zu dieser Abweichung [mm]
KREIS_MIN_PUNKTE = 8


def _vi(b, p):
    c = b[p]
    if c < 0x80:
        return c, 1, p + 1
    if c < 0xC0:
        return ((c & 0x3F) << 8) | b[p + 1], 2, p + 2
    return ((c & 0x3F) << 24) | (b[p + 1] << 16) | (b[p + 2] << 8) | b[p + 3], 4, p + 4


def _bloecke(daten):
    """Alle zlib-Blöcke der Datei in Reihenfolge (entpackt)."""
    out, i = [], 0
    while True:
        j = daten.find(b"\x78\xda", i)
        if j < 0:
            return out
        try:
            o = zlib.decompressobj()
            r = o.decompress(daten[j:])
            if not o.eof:
                raise zlib.error("unvollständig")
            out.append(r)
            i = len(daten) - len(o.unused_data)
        except zlib.error:
            i = j + 1


def _dokument(bl):
    """Ein XML-Dokument ab bl[0] (Kopf). Ergebnis (Wurzel, Zahl der benutzten Blöcke)."""
    h = bl[0]
    p, kopf = 4, []
    for _ in range(10):
        v, _n, p = _vi(h, p)
        kopf.append(v)
    groessen = []
    while True:
        a, _n, p2 = _vi(h, p)
        if a != 1:
            break
        _b, _n, p2 = _vi(h, p2)
        s, _n, p2 = _vi(h, p2)
        groessen.append(s)
        p = p2
    n_namen, _n, p = _vi(h, p)
    namen = []
    for _ in range(n_namen):
        c = h[p]
        p += 1
        namen.append((bool(c & 0x40), h[p:p + (c & 0x3F)].decode("latin-1")))
        p += c & 0x3F
    bi = 1
    struktur = None
    if bi < len(bl) and len(bl[bi]) == kopf[7] and bl[bi][:4] != KENNUNG:
        struktur, bi = bl[bi], bi + 1
    beh = [None] * len(groessen)
    for k, s in enumerate(groessen):
        if bi < len(bl) and s >= 2048 and len(bl[bi]) == s and bl[bi][:4] != KENNUNG:
            beh[k], bi = bl[bi], bi + 1
    im_kopf = sum(s for k, s in enumerate(groessen) if beh[k] is None)
    ende_sonder = len(h) - im_kopf
    if struktur is None:            # kleine Dokumente: Struktur im Kopf nach dem Wörterbuch
        struktur = h[p + 1:p + 1 + kopf[7]]
        p += kopf[7]
    sonder, q = [], p + 1           # feste Texte (CDATA) für Struktur-Zeichen 1-4
    while q < ende_sonder:
        n, _n, q = _vi(h, q)
        sonder.append(h[q:q + n].decode("latin-1"))
        q += n
    q = ende_sonder
    for k, s in enumerate(groessen):
        if beh[k] is None:
            beh[k] = h[q:q + s]
            q += s
    lage = [0] * len(beh)

    def wert(k):
        b = beh[k]
        n, _n, pp = _vi(b, lage[k])
        lage[k] = pp + n
        return b[pp:pp + n].decode("latin-1")
    wurzel = ET.Element("bpf")
    stapel, attr, si, p = [wurzel], None, 0, 0
    while p < len(struktur):
        v, n, p = _vi(struktur, p)
        if n == 1:
            text_, k = 0x40 <= v < 0x80, v - 0x40
        else:
            text_, k = bool(v & 0x2000), v & 0x1FFF
        if text_:
            t = wert(k - 1)
            if attr is not None:
                stapel[-1].set(attr, t)
            else:
                stapel[-1].text = (stapel[-1].text or "") + t
        elif v == 0:
            if attr is not None:
                attr = None
            elif len(stapel) > 1:
                stapel.pop()
        elif v < 5:
            t = sonder[si] if si < len(sonder) else ""
            si += 1
            if attr is None:
                stapel[-1].text = (stapel[-1].text or "") + t
        else:
            ist_attr, name = namen[v - 5]
            if ist_attr:
                attr = name
            else:
                stapel.append(ET.SubElement(stapel[-1], name))
    return wurzel, bi


def bpf_dokumente(daten):
    """Alle XML-Dokumente einer BPF-Datei (Projekt, Verschachtelung …) als Element-Bäume."""
    bl = _bloecke(daten)
    out, i = [], 0
    while i < len(bl):
        if bl[i][:4] != KENNUNG:
            i += 1
            continue
        try:
            w, n = _dokument(bl[i:])
        except (IndexError, UnicodeDecodeError) as e:
            raise ValueError(f"BPF-Datei beschädigt: {e}") from e
        out.append(w)
        i += n
    if not out:
        raise ValueError("keine BLM-BPF-Datei (kein Programm gefunden)")
    return out


def _p(e):
    return (float(e.get("x") or 0), float(e.get("y") or 0), float(e.get("z") or 0)) if e is not None else None



def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b, f=1.0):
    return (a[0] + b[0] * f, a[1] + b[1] * f, a[2] + b[2] * f)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _kreuz(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _norm(a):
    lg = math.sqrt(_dot(a, a))
    return (a[0] / lg, a[1] / lg, a[2] / lg) if lg > 1e-12 else (0.0, 0.0, 0.0)


def kreis_aus_punkten(pk, normale=None):
    """Kreis durch ebene Punkte (Kasa-Ausgleich in der Ebene): (Mitte, Radius, Normale) oder None, wenn die Punkte
    nicht auf einem Kreis liegen (Abweichung > KREIS_TOL) oder nicht eben sind."""
    if len(pk) < KREIS_MIN_PUNKTE:
        return None
    m = tuple(sum(p[i] for p in pk) / len(pk) for i in range(3))
    n = normale
    if n is None:
        best = (0.0, None)
        for i in range(len(pk)):
            a, b = _sub(pk[i], m), _sub(pk[(i + len(pk) // 3) % len(pk)], m)
            k = _kreuz(a, b)
            lg = math.sqrt(_dot(k, k))
            if lg > best[0]:
                best = (lg, k)
        if best[1] is None:
            return None
        n = best[1]
    n = _norm(n)
    if any(abs(_dot(_sub(p, m), n)) > KREIS_TOL for p in pk):
        return None
    e1 = _norm(_sub(pk[0], m)) if math.dist(pk[0], m) > 1e-9 else _norm(_kreuz(n, (1.0, 0.0, 0.0)))
    e2 = _kreuz(n, e1)
    uv = [(_dot(_sub(p, m), e1), _dot(_sub(p, m), e2)) for p in pk]
    # Kasa: u² + v² + D u + E v + F = 0
    suu = sum(u * u for u, _ in uv)
    svv = sum(v * v for _, v in uv)
    suv = sum(u * v for u, v in uv)
    su = sum(u for u, _ in uv)
    sv = sum(v for _, v in uv)
    n_ = len(uv)
    rz = [-sum((u * u + v * v) * u for u, v in uv), -sum((u * u + v * v) * v for u, v in uv),
          -sum(u * u + v * v for u, v in uv)]
    a_ = [[suu, suv, su], [suv, svv, sv], [su, sv, n_]]
    try:
        d_, e_, f_ = _loesen(a_, rz)
    except ZeroDivisionError:
        return None
    cu, cv = -d_ / 2, -e_ / 2
    r2 = cu * cu + cv * cv - f_
    if r2 <= 0:
        return None
    r = math.sqrt(r2)
    if any(abs(math.hypot(u - cu, v - cv) - r) > KREIS_TOL for u, v in uv):
        return None
    # ganz herum (keine Bögen): Winkel deckt den Umfang ab
    w = sorted(math.atan2(v - cv, u - cu) for u, v in uv)
    luecke = max([w[i + 1] - w[i] for i in range(len(w) - 1)] + [w[0] + 2 * math.pi - w[-1]])
    if luecke > math.radians(60):
        return None
    c = _add(_add(m, e1, cu), e2, cv)
    return c, r, n


def _loesen(a, b):
    """3×3-Gleichungssystem (Gauß)."""
    m = [list(a[i]) + [b[i]] for i in range(3)]
    for k in range(3):
        piv = max(range(k, 3), key=lambda i: abs(m[i][k]))
        if abs(m[piv][k]) < 1e-12:
            raise ZeroDivisionError
        m[k], m[piv] = m[piv], m[k]
        for i in range(k + 1, 3):
            f = m[i][k] / m[k][k]
            for j in range(k, 4):
                m[i][j] -= f * m[k][j]
    x = [0.0] * 3
    for i in (2, 1, 0):
        x[i] = (m[i][3] - sum(m[i][j] * x[j] for j in range(i + 1, 3))) / m[i][i]
    return x


