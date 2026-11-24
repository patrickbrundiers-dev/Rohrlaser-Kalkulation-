"""BLM/Adige-Rohrprogramme (ArTube) wie eine STEP-Datei messen (Patrick 24.11.2026: „Artube und bpf importieren
möglich machen“).

BPF (Programm für LT7/LT8 usw.): kein Klartext, sondern komprimiertes XML (Kopf „(c) Adige S.p.A. BLMGroup“, danach
zlib-Blöcke). Jeder Teil beginnt mit dem Kennzeichen E5 E3 D2 9E: Kopf mit den Größen der Datenbehälter, Wörterbuch der
Elementnamen (Länge, Bit 0x40 = Attribut), Strukturstrom (Element = Nummer + 5, 0 = Ende, Text = Behälter) und die
Behälter mit den Werten (je Wert Länge + Text); kleine Behälter liegen im Kopf, große in eigenen Blöcken. Zahlen sind
Varints (1 Byte < 0x80, 2 Bytes 10xxxxxx, 4 Bytes 11xxxxxx). Daraus kommt das XML „Progetto“ mit
- info_tubo/sezione: Querschnitt exakt (Topologie aus Strecken und Bögen, außen und innen), Maße, Werkstoff,
- info_pezzo: Länge, Volumen, Maschine,
- geometrie: je Kontur der Schneidweg als Punkte auf dem Rohr (pt_3d, x längs) mit Brennerrichtung (versore).
Der Körper entsteht exakt aus dem Querschnitt; jede Kontur wird mit einem Werkzeug entlang des Schneidwegs (Brenner-
richtung, durch die ganze Wand) ausgeschnitten. Anfahrwege (Fläche Art 2) zählen nicht zur Kontur. Teilstücke einer
Kontur, die das CAM getrennt schneidet (offen, Spalt kleiner als die Schnittfuge), werden über die Fuge geschlossen.
Kreise des Schneidwegs werden exakte Bohrungen, alle anderen Bögen bleiben Vielecke in der CAM-Toleranz.

ARTUBE (Projekt aus ArTube): tar-Archiv, Einträge zlib-gepackt: _files/metadata (JSON: Teile mit Name, Länge,
Querschnitt, Werkstoff, Programmpfad), _files/obj/parts/<Schlüssel>.obj (Dreiecksnetz in m), _files/artube (Parasolid,
nicht frei lesbar). Liegt das BPF des Teils daneben (gleicher Name im selben Ordner), gilt das BPF (Querschnitt exakt);
sonst wird das Netz wie bei TUBX (step_tubx) zum Körper genäht und jede Bohrung (Kreis aus Netzpunkten außen und innen)
exakt nachgebohrt. Ergebnis wie step_geometrie.lies_step_info. Ohne Qt; OpenCascade nur beim Bauen."""
import json
import math
import re
import tarfile
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

ENDUNGEN = (".bpf", ".artube")
KENNUNG = b"\xe5\xe3\xd2\x9e"
UEBER = 1.0             # Werkzeug ragt so weit über die Wand hinaus [mm]
FUGE = 0.3              # offene Teilstücke: Schließsehne so weit nach außen (überbrückt Spalt bis Schnittfuge) [mm]
FERN = 5.0              # Werkzeug eines Endes reicht so weit über das Teil hinaus [mm]
EBEN_TOL = 0.01         # Ende gilt als gerade bis zu dieser Abweichung [mm]
KREIS_TOL = 0.005       # Schneidweg bzw. Netzpunkte gelten als Kreis bis zu dieser Abweichung [mm]
KREIS_MIN_PUNKTE = 8
UNSCHAERFE = 1e-4       # Boolesche Operationen [mm]


def ist_blm(pfad):
    return Path(str(pfad)).suffix.lower() in ENDUNGEN


# ------------------------------------------------------------------ BPF: komprimiertes XML lesen
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


def _f(e, pfad, vorgabe=0.0):
    x = e.find(pfad) if pfad else e
    try:
        return float(x.text) if x is not None and x.text is not None else vorgabe
    except ValueError:
        return vorgabe


def _p(e):
    return (float(e.get("x") or 0), float(e.get("y") or 0), float(e.get("z") or 0)) if e is not None else None


def _topologie(e):
    out = []
    for t in e.iter("top"):
        if (t.findtext("tipot") or "").strip() == "1":
            out.append(dict(art="strecke", a=_p(t.find("p_ini")), b=_p(t.find("p_fin"))))
        else:
            out.append(dict(art="bogen", c=_p(t.find("centro")), r=_f(t, "raggio"), w=_f(t, "angolo"),
                            n=_p(t.find("normale"))))
    return out


def bpf_teil(daten, name=""):
    """Teil aus einer BPF-Datei: dict(name, laenge, volumen, querschnitt {form_nr, name, a, b, wand, r, aussen, innen},
    werkstoff, maschine, konturen [dict(nr, art, punkte [(x, y, z)], richtung [(vx, vy, vz)], laenge)])."""
    docs = bpf_dokumente(daten)
    proj = next((d.find("Progetto") for d in docs if d.find("Progetto") is not None), None)
    if proj is None:
        raise ValueError("BPF-Datei ohne Projekt (Progetto)")
    sez = proj.find("info_tubo/sezione")
    pez = proj.find("info_pezzo")
    if sez is None or pez is None:
        raise ValueError("BPF-Datei ohne Rohrangaben (info_tubo/info_pezzo)")
    qs = dict(form_nr=int(_f(sez, "tipo")), name=(sez.findtext("nome_sezione") or "").strip(),
              a=_f(sez, "dim_x"), b=_f(sez, "dim_y"), wand=_f(sez, "spessore"), r=_f(sez, "raggiatura"),
              aussen=_topologie(sez.find("profili/profilo_esterno")) if sez.find("profili/profilo_esterno")
              is not None else [],
              innen=_topologie(sez.find("profili/profilo_interno")) if sez.find("profili/profilo_interno")
              is not None else [])
    konturen = []
    for g in proj.findall("geometrie/info_geo"):
        pk, rk = [], []
        for fa in g.findall("facce/info_faccia"):
            if (fa.findtext("tipo_faccia") or "").strip() == "2":       # Anfahrweg
                continue
            for pu in fa.findall("punti/punto"):
                p, v = _p(pu.find("pt_3d")), _p(pu.find("versore"))
                if p is None:
                    continue
                if pk and math.dist(pk[-1], p) < 1e-6:
                    continue
                pk.append(p)
                rk.append(v or (0.0, 0.0, 0.0))
        if len(pk) >= 2:
            konturen.append(dict(nr=int(g.get("id") or len(konturen) + 1), art=(g.findtext("tipogeo") or "").strip(),
                                 punkte=pk, richtung=rk, laenge=_f(g, "dimensioni/l")))
    maschine = proj.find("info_pezzo/macchine/macchina_valida")
    return dict(name=(pez.findtext("nome") or "").strip() or name, laenge=_f(pez, "lunghezza"),
                volumen=_f(pez, "volume"), querschnitt=qs, werkstoff=(proj.findtext("info_tubo/materiale") or "").strip(),
                maschine=(maschine.findtext("famiglia") or "").strip() if maschine is not None else "",
                konturen=konturen)


# ------------------------------------------------------------------ ARTUBE: Archiv lesen
def _gepackt(b):
    try:
        return zlib.decompress(b)
    except zlib.error:
        return b


def artube_inhalt(pfad):
    """dict(metadaten (JSON), teile [dict(schluessel, name, laenge, material, querschnitt, programm, punkte, ix)])."""
    try:
        tf = tarfile.open(str(pfad), "r:")
    except (OSError, tarfile.TarError) as e:
        raise ValueError(f"ARTUBE-Datei nicht lesbar (kein Archiv oder beschädigt): {e}") from e
    with tf:
        eintraege = {m.name: m for m in tf.getmembers() if m.isfile()}

        def lies(n):
            return _gepackt(tf.extractfile(eintraege[n]).read())
        if "_files/metadata" not in eintraege:
            raise ValueError("ARTUBE-Datei ohne Teiledaten (_files/metadata fehlt)")
        try:
            meta = json.loads(lies("_files/metadata").decode("utf-8", "replace"))
        except ValueError as e:
            raise ValueError(f"ARTUBE-Teiledaten nicht lesbar: {e}") from e
        doc = (meta.get("artubeMetadata") or {}).get("document") or {}
        teile = []
        for t in ((doc.get("assembly") or {}).get("parts") or []):
            t = t.get("part") or t
            key = str(t.get("key"))
            prog = ""
            for pr in t.get("projects") or []:
                for ma in (pr.get("project") or {}).get("machines") or []:
                    prog = prog or ((ma.get("machine") or {}).get("partProgram") or "")
            n = f"_files/obj/parts/{key}.obj"
            punkte, ix = obj_netz(lies(n).decode("latin-1")) if n in eintraege else ([], [])
            teile.append(dict(schluessel=key, name=str(t.get("name") or key), laenge=float(t.get("length") or 0) * 1000,
                              material=t.get("material"), querschnitt=t.get("section") or {}, programm=prog,
                              punkte=punkte, ix=ix))
    return dict(metadaten=meta, teile=teile)


def obj_netz(text, faktor=1000.0):
    """OBJ-Text (ArTube: Meter) -> (Punkte [(x, y, z)] in mm, Dreiecks-Indizes)."""
    punkte, ix = [], []
    for z in text.splitlines():
        if z.startswith("v "):
            w = z.split()
            punkte.append((float(w[1]) * faktor, float(w[2]) * faktor, float(w[3]) * faktor))
        elif z.startswith("f "):
            ecken = [int(w.split("/")[0]) for w in z.split()[1:]]
            ecken = [e - 1 if e > 0 else len(punkte) + e for e in ecken]
            for k in range(1, len(ecken) - 1):          # Vielecke als Fächer
                ix += [ecken[0], ecken[k], ecken[k + 1]]
    return punkte, ix


# ------------------------------------------------------------------ Geometrie-Hilfen (ohne OpenCascade)
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


def _ohrschnitt(pk2):
    """Einfaches Vieleck (2D) in Dreiecke [(i, j, k)]."""
    n = len(pk2)
    fl = sum(pk2[i][0] * pk2[(i + 1) % n][1] - pk2[(i + 1) % n][0] * pk2[i][1] for i in range(n))
    idx = list(range(n)) if fl > 0 else list(range(n))[::-1]

    def kr(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    def drin(p, a, b, c):
        return kr(a, b, p) >= -1e-12 and kr(b, c, p) >= -1e-12 and kr(c, a, p) >= -1e-12
    out, schutz = [], 0
    while len(idx) > 3 and schutz < 10 * n * n:
        schutz += 1
        for k in range(len(idx)):
            i, j, m = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = pk2[i], pk2[j], pk2[m]
            if kr(a, b, c) <= 1e-12:
                continue
            if any(drin(pk2[q], a, b, c) for q in idx if q not in (i, j, m)):
                continue
            out.append((i, j, m))
            idx.pop(k)
            break
        else:           # entartet: Rest als Fächer
            break
    for k in range(1, len(idx) - 1):
        out.append((idx[0], idx[k], idx[k + 1]))
    return out


def _winkel_lauf(pk, mitte=(0.0, 0.0)):
    """Winkel um die Rohrachse (x) je Punkt, stetig fortgesetzt [rad]."""
    out, alt = [], None
    for p in pk:
        w = math.atan2(p[2] - mitte[1], p[1] - mitte[0])
        if alt is not None:
            while w - alt > math.pi:
                w -= 2 * math.pi
            while w - alt < -math.pi:
                w += 2 * math.pi
        out.append(w)
        alt = w
    return out


def kontur_aufbereiten(k):
    """Kontur für das Werkzeug: dict(art 'ende' | 'bohrung' | 'kontur', ...). Ende: Ring um das Rohr; Bohrung: Kreis
    (Mitte, r, Achse); Kontur: geschlossener Zug (offene Teilstücke über die Schnittfuge geschlossen)."""
    pk, rk = list(k["punkte"]), list(k["richtung"])
    w = _winkel_lauf(pk)
    if abs(w[-1] - w[0]) > math.radians(300):
        return dict(art="ende", punkte=pk, richtung=rk)
    if math.dist(pk[0], pk[-1]) < 1e-3:
        pk, rk = pk[:-1], rk[:-1]
        v0 = _norm(tuple(sum(v[i] for v in rk) for i in range(3)))
        if all(_dot(_norm(v), v0) > 0.9999 for v in rk):
            kr = kreis_aus_punkten(pk, v0)
            if kr:
                return dict(art="bohrung", mitte=kr[0], r=kr[1], achse=v0)
        return dict(art="kontur", punkte=pk, richtung=rk)
    # offenes Teilstück: Schließsehne um FUGE nach außen (weg vom Inneren der Kontur, in der Wandebene)
    a, b = pk[-1], pk[0]
    s = _norm(_sub(b, a))
    mitte = tuple(sum(p[i] for p in pk) / len(pk) for i in range(3))
    n = _norm(_add(rk[-1], rk[0]))
    innen = _sub(mitte, _add(a, _sub(b, a), 0.5))
    innen = _add(innen, s, -_dot(innen, s))
    innen = _add(innen, n, -_dot(innen, n))
    aus = _norm(innen)
    aus = (-aus[0], -aus[1], -aus[2])
    pk += [_add(a, aus, FUGE), _add(b, aus, FUGE)]
    rk += [rk[-1], rk[0]]
    return dict(art="kontur", punkte=pk, richtung=rk)


def werkzeug_dreiecke(pk, rk, tiefe):
    """Dreiecke eines Werkzeugs entlang eines geschlossenen Schneidwegs: außen UEBER über der Oberfläche, innen
    tiefe + UEBER in Brennerrichtung. Deckel über die Abwicklung (x, Winkel) trianguliert."""
    n = len(pk)
    oben = [_add(p, _norm(v), UEBER) for p, v in zip(pk, rk)]
    unten = [_add(p, _norm(v), -(tiefe + UEBER)) for p, v in zip(pk, rk)]
    w = _winkel_lauf(pk)
    rm = sum(math.hypot(p[1], p[2]) for p in pk) / n or 1.0
    flach = _ohrschnitt([(p[0], wi * rm) for p, wi in zip(pk, w)])
    tri = []
    for i in range(n):
        j = (i + 1) % n
        tri += [(oben[i], oben[j], unten[j]), (oben[i], unten[j], unten[i])]
    for i, j, m in flach:
        tri += [(oben[i], oben[m], oben[j]), (unten[i], unten[j], unten[m])]
    return tri


def ende_dreiecke(pk, rk, tiefe, nach_minus):
    """Dreiecke des Werkzeugs für ein nicht gerades Ende: vom Schneidweg (Ring) bis FERN über das Ende hinaus."""
    n = len(pk)
    if math.dist(pk[0], pk[-1]) < 1e-3:
        pk, rk, n = pk[:-1], rk[:-1], n - 1
    x_fern = (min(p[0] for p in pk) - FERN) if nach_minus else (max(p[0] for p in pk) + FERN)
    o = [_add(p, _norm(v), UEBER) for p, v in zip(pk, rk)]
    u = [_add(p, _norm(v), -(tiefe + UEBER)) for p, v in zip(pk, rk)]
    of = [(x_fern, p[1], p[2]) for p in o]
    uf = [(x_fern, p[1], p[2]) for p in u]
    tri = []
    for i in range(n):
        j = (i + 1) % n
        for a, b, c, d in ((o[i], o[j], u[j], u[i]), (of[i], of[j], o[j], o[i]), (u[i], u[j], uf[j], uf[i]),
                           (uf[i], uf[j], of[j], of[i])):
            tri += [(a, b, c), (a, c, d)]
    return tri


# ------------------------------------------------------------------ OpenCascade
def _occ_dreiecke_koerper(tri):
    from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeSolid,
                                    BRepBuilderAPI_Sewing)
    from OCP.BRepLib import BRepLib
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    naht = BRepBuilderAPI_Sewing(1e-4)
    for a, b, c in tri:
        if math.dist(a, b) < 1e-7 or math.dist(b, c) < 1e-7 or math.dist(a, c) < 1e-7:
            continue
        poly = BRepBuilderAPI_MakePolygon(gp_Pnt(*a), gp_Pnt(*b), gp_Pnt(*c), True)
        f = BRepBuilderAPI_MakeFace(poly.Wire(), True)
        if f.IsDone():
            naht.Add(f.Face())
    naht.Perform()
    ms = BRepBuilderAPI_MakeSolid()
    ex = TopExp_Explorer(naht.SewedShape(), TopAbs_SHELL)
    n = 0
    while ex.More():
        ms.Add(TopoDS.Shell_s(ex.Current()) if hasattr(TopoDS, "Shell_s") else TopoDS.Shell(ex.Current()))
        n += 1
        ex.Next()
    if not n:
        return None
    s = ms.Solid()
    BRepLib.OrientClosedSolid_s(s)
    return s


def _liste(formen):
    try:
        from OCP.TopTools import TopTools_ListOfShape
    except ImportError:         # neuere OCP-Versionen
        from OCP.collections import List_TopoDS_Shape as TopTools_ListOfShape
    li = TopTools_ListOfShape()
    for f in formen:
        li.Append(f)
    return li


def _bool(art, form, werkzeuge):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    op = BRepAlgoAPI_Cut() if art == "cut" else BRepAlgoAPI_Fuse()
    op.SetArguments(_liste([form]))
    op.SetTools(_liste(werkzeuge))
    op.SetFuzzyValue(UNSCHAERFE)
    op.SetRunParallel(True)
    op.Build()
    if not op.IsDone():
        raise ValueError("Boolesche Operation fehlgeschlagen")
    return op.Shape()


def _vereinheitlicht(form):
    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain
    from OCP.TopAbs import TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    u = ShapeUpgrade_UnifySameDomain(form, True, True, False)
    u.Build()
    form = u.Shape()
    if form.ShapeType() != TopAbs_SOLID:
        ex = TopExp_Explorer(form, TopAbs_SOLID)
        best, vol = None, -1.0
        while ex.More():
            s = TopoDS.Solid_s(ex.Current()) if hasattr(TopoDS, "Solid_s") else TopoDS.Solid(ex.Current())
            v = volumen(s)
            if v > vol:
                best, vol = s, v
            ex.Next()
        form = best if best is not None else form
    return form


def volumen(form):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    g = GProp_GProps()
    BRepGProp.VolumeProperties_s(form, g)
    return g.Mass()


def _querschnitt_draht(topo):
    """Geschlossener Draht in der Ebene x = 0 aus Strecken und Bögen der BPF-Topologie."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt
    if not topo:
        return None
    if len(topo) == 1 and topo[0]["art"] == "bogen":
        t = topo[0]
        kreis = gp_Circ(gp_Ax2(gp_Pnt(*t["c"]), gp_Dir(1, 0, 0)), t["r"])
        return BRepBuilderAPI_MakeWire(BRepBuilderAPI_MakeEdge(kreis).Edge()).Wire()
    n = len(topo)
    # Endpunkte der Bögen: die Streckenenden im Abstand r von der Mitte (die Reihenfolge der Topologie ist nicht
    # immer der Umlauf); ohne passende Strecken aus den Nachbarn bzw. aus Mitte, Radius und Winkel
    strecken_enden = [p for t in topo if t["art"] == "strecke" for p in (t["a"], t["b"])]
    enden = [None] * n
    for i, t in enumerate(topo):
        if t["art"] == "strecke":
            enden[i] = (t["a"], t["b"])
        else:
            pk = [p for p in strecken_enden if abs(math.dist(p, t["c"]) - t["r"]) < 1e-4]
            if len(pk) == 2:
                enden[i] = (pk[0], pk[1])
    for _ in range(n):
        for i, t in enumerate(topo):
            if enden[i] is not None:
                continue
            vor, nach = enden[i - 1], enden[(i + 1) % n]
            if vor is not None and nach is not None:
                enden[i] = (vor[1], nach[0])
            elif vor is not None:
                enden[i] = (vor[1], _bogen_ende(t, vor[1]))
            elif nach is not None:
                enden[i] = (_bogen_ende(t, nach[0], rueck=True), nach[0])
    kanten = []
    for i, t in enumerate(topo):
        if enden[i] is None:
            raise ValueError("Querschnitt der BPF-Datei nicht lesbar (Bogen ohne Endpunkte)")
        a, b = enden[i]
        if math.dist(a, b) < 1e-7:
            continue
        if t["art"] == "strecke":
            kanten.append((a, b, None))
        else:
            c = t["c"]
            mitte = _norm(_sub(_add(a, _sub(b, a), 0.5), c))
            if mitte == (0.0, 0.0, 0.0):
                mitte = _norm(_kreuz(t["n"], _sub(a, c)))
            kanten.append((a, b, _add(c, mitte, t["r"])))
    # zum Umlauf ordnen
    kette = [kanten.pop(0)]
    while kanten:
        e = kette[-1][1]
        k = min(range(len(kanten)), key=lambda j: min(math.dist(e, kanten[j][0]), math.dist(e, kanten[j][1])))
        a, b, m = kanten.pop(k)
        if math.dist(e, a) > 1e-3 and math.dist(e, b) > 1e-3:
            raise ValueError("Querschnitt der BPF-Datei nicht geschlossen")
        kette.append((a, b, m) if math.dist(e, a) <= math.dist(e, b) else (b, a, m))
    mw = BRepBuilderAPI_MakeWire()
    vor = kette[-1][1]
    for a, b, m in kette:
        a = vor             # exakt anschließen
        if m is None:
            mw.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(*a), gp_Pnt(*b)).Edge())
        else:
            mw.Add(BRepBuilderAPI_MakeEdge(GC_MakeArcOfCircle(gp_Pnt(*a), gp_Pnt(*m), gp_Pnt(*b)).Value()).Edge())
        vor = b
    if not mw.IsDone():
        raise ValueError("Querschnitt der BPF-Datei nicht geschlossen")
    return mw.Wire()


def _bogen_ende(t, p, rueck=False):
    c, n = t["c"], _norm(t["n"] or (1.0, 0.0, 0.0))
    w = math.radians(t["w"]) * (-1 if rueck else 1)
    v = _sub(p, c)
    k = _kreuz(n, v)
    return _add(_add(c, v, math.cos(w)), k, math.sin(w))


def bpf_koerper(teil):
    """Volumenkörper aus dem BPF-Teil. Ergebnis (Shape, Meldungen)."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_Transform
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
    qs, L = teil["querschnitt"], teil["laenge"]
    meld = []
    aussen = _querschnitt_draht(qs["aussen"])
    if aussen is None:
        raise ValueError("BPF-Datei ohne Querschnitt")
    innen = _querschnitt_draht(qs["innen"])
    wand = qs.get("wand") or 0.0
    aufb = [kontur_aufbereiten(k) for k in teil["konturen"]]
    enden = [k for k in aufb if k["art"] == "ende"]
    x0, x1 = 0.0, L
    schraeg = []
    for e in enden:
        xs = [p[0] for p in e["punkte"]]
        mitte = (max(xs) + min(xs)) / 2
        if max(xs) - min(xs) <= EBEN_TOL:       # gerades Ende: Rohr beginnt bzw. endet dort
            if mitte < L / 2:
                x0 = mitte
            else:
                x1 = mitte
        else:
            schraeg.append((e, mitte < L / 2))
            if mitte < L / 2:
                x0 = min(xs)
            else:
                x1 = max(xs)
    rohr = BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(aussen, True).Face(), gp_Vec(x1 - x0, 0, 0)).Shape()
    if innen is not None:       # offene Profile haben keinen Innenumriss
        loch = BRepPrimAPI_MakePrism(BRepBuilderAPI_MakeFace(innen, True).Face(), gp_Vec(x1 - x0, 0, 0)).Shape()
        rohr = _vereinheitlicht(_bool("cut", rohr, [loch]))
    if abs(x0) > 1e-9:
        tr = gp_Trsf()
        tr.SetTranslation(gp_Vec(x0, 0, 0))
        rohr = BRepBuilderAPI_Transform(rohr, tr, True).Shape()
    werkzeuge = []
    for e, minus in schraeg:
        s = _occ_dreiecke_koerper(ende_dreiecke(e["punkte"], e["richtung"], max(wand, 1.0) * 3, minus))
        if s is not None:
            werkzeuge.append(s)
    nb = 0
    for k in aufb:
        if k["art"] == "bohrung":
            ax = _norm(k["achse"])
            p0 = _add(k["mitte"], ax, UEBER)
            werkzeuge.append(BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(*p0), gp_Dir(*(-c for c in ax))), k["r"],
                                                      wand * 3 + 2 * UEBER).Shape())
            nb += 1
        elif k["art"] == "kontur":
            s = _occ_dreiecke_koerper(werkzeug_dreiecke(k["punkte"], k["richtung"], max(wand, 1.0) * 1.5))
            if s is None:
                meld.append("eine Kontur des BPF ließ sich nicht als Werkzeug bauen (übersprungen)")
            else:
                werkzeuge.append(s)
    form = _vereinheitlicht(_bool("cut", rohr, werkzeuge)) if werkzeuge else rohr
    if nb:
        meld.append(f"{nb} Bohrung(en) aus dem Schneidweg exakt")
    return form, meld


def netz_koerper(punkte, ix, achse=(1.0, 0.0, 0.0)):
    """Volumenkörper aus dem ArTube-Netz (wie TUBX), Bohrungen exakt aus den Netzkreisen. Ergebnis (Art, Shape, n)."""
    from step_tubx import bohrungen, koerper_bauen
    art, form = koerper_bauen(punkte, ix, [])
    if art == "Flächenmodell offen":
        return art, form, 0
    kreise = netz_kreise(form, achse)
    paare = bohrungen(kreise)
    if not paare:
        return art, form, 0
    _art, neu = koerper_bauen(punkte, ix, kreise)
    return art, neu, len(paare)


def netz_kreise(form, achse):
    """Kreise aus den inneren Rändern ebener Flächen (Bohrungen als Vielecke) quer zur Rohrachse."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
    from OCP.GeomAbs import GeomAbs_Plane
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.TopAbs import TopAbs_FACE, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    cast = (lambda f, s: getattr(TopoDS, f + "_s")(s)) if hasattr(TopoDS, "Face_s") else \
        (lambda f, s: getattr(TopoDS, f)(s))
    out = []
    ex = TopExp_Explorer(form, TopAbs_FACE)
    while ex.More():
        f = cast("Face", ex.Current())
        ex.Next()
        ad = BRepAdaptor_Surface(f)
        if ad.GetType() != GeomAbs_Plane:
            continue
        d = ad.Plane().Axis().Direction()
        n = (d.X(), d.Y(), d.Z())
        if abs(_dot(n, achse)) > 0.5:           # Stirnfläche: der Innenrand ist das Rohr selbst
            continue
        aussen = BRepTools.OuterWire_s(f) if hasattr(BRepTools, "OuterWire_s") else BRepTools.OuterWire(f)
        wx = TopExp_Explorer(f, TopAbs_WIRE)
        while wx.More():
            w = cast("Wire", wx.Current())
            wx.Next()
            if w.IsSame(aussen):
                continue
            pk = []
            we = BRepTools_WireExplorer(w)
            while we.More():
                p = BRep_Tool.Pnt_s(we.CurrentVertex()) if hasattr(BRep_Tool, "Pnt_s") else \
                    BRep_Tool.Pnt(we.CurrentVertex())
                pk.append((p.X(), p.Y(), p.Z()))
                we.Next()
            kr = kreis_aus_punkten(pk, n)
            if kr:
                out.append(dict(c=kr[0], r=kr[1], n=kr[2]))
    return out


# ------------------------------------------------------------------ Lesen wie lies_step_info
def _bpf_daneben(pfad, programm=""):
    p = Path(str(pfad))
    kand = [p.with_suffix(".bpf"), p.with_suffix(".BPF")]
    if programm:
        name = re.split(r"[\\/]", programm)[-1]
        kand.append(p.parent / name)
    return next((k for k in kand if k.is_file()), None)


def lies_blm_info(pfad):
    """BPF oder ARTUBE lesen: (Körper, Info) wie step_geometrie.lies_step_info."""
    pfad = Path(str(pfad))
    koerper, meld = [], []
    if pfad.suffix.lower() == ".bpf":
        teil = bpf_teil(pfad.read_bytes(), pfad.stem)
        form, m = bpf_koerper(teil)
        koerper.append(("Volumenkörper", form))
        meld += m
        meld.append(_bpf_text(teil, form))
    else:
        inh = artube_inhalt(pfad)
        if not inh["teile"]:
            raise ValueError("ARTUBE-Datei ohne Teile")
        for t in inh["teile"]:
            bpf = _bpf_daneben(pfad, t["programm"]) if len(inh["teile"]) == 1 else None
            if bpf is not None:
                try:
                    teil = bpf_teil(bpf.read_bytes(), t["name"])
                    form, m = bpf_koerper(teil)
                    koerper.append(("Volumenkörper", form))
                    meld += m
                    meld.append(f"{t['name']}: aus dem BPF daneben ({bpf.name}) – " + _bpf_text(teil, form))
                    continue
                except (ValueError, OSError) as e:
                    meld.append(f"{t['name']}: BPF daneben nicht lesbar ({e}), Netz der ARTUBE gemessen")
            if not t["punkte"]:
                meld.append(f"{t['name']}: ohne 3D-Netz in der ARTUBE")
                continue
            art, form, nb = netz_koerper(t["punkte"], t["ix"])
            if art == "Flächenmodell offen":
                meld.append(f"{t['name']}: 3D-Netz nicht geschlossen")
                koerper.append((art, form))
                continue
            koerper.append(("Volumenkörper", form))
            qs = t["querschnitt"] or {}
            meld.append(f"{t['name']}: aus ARTUBE-Netz, {nb} Bohrung(en) exakt, Rundungen als Vieleck"
                        + (f"; Profil laut ArTube {_mm(qs.get('width'))}×{_mm(qs.get('height'))}×"
                           f"{_mm(qs.get('thickness'))}, R {_mm(qs.get('edgesRadius'))}" if qs.get("width") else ""))
        if not koerper:
            raise ValueError("ARTUBE-Datei ohne messbares Teil (kein 3D-Netz, kein BPF daneben)")
    return koerper, dict(einheit="mm", meldungen=meld[:20], baugruppe=len(koerper) > 1, struktur=None, bauteile={})


def _mm(v):
    try:
        return f"{float(v) * 1000:g}"
    except (TypeError, ValueError):
        return "?"


def _bpf_text(teil, form):
    qs = teil["querschnitt"]
    t = (f"aus BLM-Programm (BPF{', ' + teil['maschine'] if teil['maschine'] else ''}): Profil {qs['name'] or ''} "
         f"{qs['a']:g}×{qs['b']:g}×{qs['wand']:g} exakt, {len(teil['konturen'])} Schneidwege, Länge {teil['laenge']:g} mm")
    if teil["werkstoff"]:
        t += f", Werkstoff im Programm {teil['werkstoff']}"
    try:
        v = volumen(form)
        if teil["volumen"] > 0:
            t += f", Volumen {v:.0f} mm³ (Programm {teil['volumen']:.0f} mm³)"
    except Exception as e:  # noqa: BLE001 – nur Bericht, Messung läuft weiter
        t += f", Volumen nicht berechenbar ({type(e).__name__})"
    return t


def zusammenfassung(pfad):
    """Kurzangaben ohne OpenCascade (Prüfung, Tests): dict(name, laenge, profil, werkstoff, konturen, schneidweg)."""
    pfad = Path(str(pfad))
    if pfad.suffix.lower() == ".bpf":
        t = bpf_teil(pfad.read_bytes(), pfad.stem)
        qs = t["querschnitt"]
        return dict(name=t["name"], laenge=t["laenge"], profil=(qs["name"], qs["a"], qs["b"], qs["wand"], qs["r"]),
                    werkstoff=t["werkstoff"], konturen=len(t["konturen"]),
                    schneidweg=round(sum(k["laenge"] for k in t["konturen"]), 2), volumen=t["volumen"])
    inh = artube_inhalt(pfad)
    t = inh["teile"][0] if inh["teile"] else {}
    qs = t.get("querschnitt") or {}
    return dict(name=t.get("name"), laenge=t.get("laenge"), profil=(qs.get("type"), (qs.get("width") or 0) * 1000,
                                                                    (qs.get("height") or 0) * 1000,
                                                                    (qs.get("thickness") or 0) * 1000,
                                                                    (qs.get("edgesRadius") or 0) * 1000),
                werkstoff=t.get("material"), teile=len(inh["teile"]), netz=len(t.get("punkte") or ()))


if __name__ == "__main__":     # Prüfen von Hand: python step_blm.py Datei.bpf
    import sys
    for a in sys.argv[1:]:
        print(a, json.dumps(zusammenfassung(a), ensure_ascii=False))
