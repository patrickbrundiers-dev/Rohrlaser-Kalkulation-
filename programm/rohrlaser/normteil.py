"""PART-004 Normteilbibliothek (Roadmap Kalkulation Phase 2, Paket 2e, 13.11.2026).

Zukaufartikel vom Typ Normteil haben Merkmale: Norm (DIN 933, ISO 4017 …), Größe (M8), Länge [mm], Festigkeit
(8.8, A2-70 …) und Oberfläche (verzinkt …). Leere Merkmale liest das Programm aus der Bezeichnung
('Sechskantschraube DIN 933 M8 x 20 8.8 verzinkt'). Gleichwertige Normen (DIN 933 = ISO 4017, DIN 934 = ISO 4032 …)
gelten als gleich. So findet der STEP-Import ein Normteil der Preisliste auch unter anderer Schreibweise
(ISO 4017 M8x20 statt DIN 933 M8 x 20), und die Preisliste des Lieferanten (normteil_preise) ordnet nach Merkmalen zu.
Festigkeit und Oberfläche zählen nur, wenn beide Seiten sie nennen. Ohne Qt.
"""
import re

FELDER = ("norm", "groesse", "laenge", "festigkeit", "norm_oberflaeche")

# gleichwertige Normen: DIN -> ISO (bzw. EN ISO); verglichen wird mit der ISO-Nummer
GLEICH = {"931": "4014", "933": "4017", "934": "4032", "912": "4762", "125": "7089", "985": "7040", "7991": "10642",
          "7985": "7045", "963": "2009", "965": "7046", "7380": "7380", "6921": "4162", "439": "4035", "936": "8675",
          "1587": "1587", "127": "127", "9021": "7093", "7984": "7984", "913": "4026", "914": "4027", "916": "4029",
          "94": "1234", "1481": "8752", "7979": "8735", "6325": "8734", "7346": "13337"}

FESTIGKEITEN = ("12.9", "10.9", "8.8", "6.8", "5.8", "5.6", "4.8", "4.6", "A4-80", "A4-70", "A2-80", "A2-70",
                "A4", "A2")
OBERFLAECHEN = (("feuerverzinkt", "feuerverzinkt"), ("tZn", "feuerverzinkt"), ("galvanisch verzinkt", "verzinkt"),
                ("verzinkt", "verzinkt"), ("gal Zn", "verzinkt"), ("galv", "verzinkt"), ("zinklamelle", "Zinklamelle"),
                ("blank", "blank"), ("schwarz", "schwarz brüniert"), ("brüniert", "schwarz brüniert"),
                ("Edelstahl", "Edelstahl"))


def _zahl(t):
    try:
        return float(str(t).replace(",", "."))
    except (TypeError, ValueError):
        return None


def merkmale(text):
    """Merkmale aus einer Bezeichnung: {norm, groesse, laenge, festigkeit, norm_oberflaeche}, fehlende leer."""
    t = " " + str(text or "").replace("×", "x").replace("X", "x") + " "
    out = dict.fromkeys(FELDER)
    n = re.search(r"\b(DIN|ISO|EN)\s*(?:EN\s*)?(?:ISO\s*)?(\d{2,5})\b", t, re.I)
    if n:
        out["norm"] = f"{n.group(1).upper()} {n.group(2)}"
    g = re.search(r"\bM\s*(\d+(?:[.,]\d+)?)(?:\s*x\s*(\d+(?:[.,]\d+)?))?(?:\s*x\s*(\d+(?:[.,]\d+)?))?", t)
    if g:
        out["groesse"] = "M" + g.group(1).replace(",", ".")
        # M8 x 1 x 20 (Feingewinde): die letzte Zahl ist die Länge; M8 x 20: Länge 20; M8 x 1: Steigung, keine Länge
        lang = g.group(3) or g.group(2)
        if lang and (g.group(3) or (_zahl(lang) or 0) >= 3):
            out["laenge"] = _zahl(lang)
    else:
        d = re.search(r"(?:Ø|ø|\bd\s*=?)\s*(\d+(?:[.,]\d+)?)", t)          # Scheiben, Stifte, Kugeln: Ø
        if d:
            out["groesse"] = "Ø" + d.group(1).replace(",", ".")
    for f in FESTIGKEITEN:
        if re.search(r"(?<![\w.,-])" + re.escape(f) + r"(?![\w.,]|-\d)", t, re.I):
            out["festigkeit"] = f.upper()
            break
    for wort, name in OBERFLAECHEN:
        if re.search(r"(?<!\w)" + re.escape(wort), t, re.I):
            out["norm_oberflaeche"] = name
            break
    return out


def von_artikel(a):
    """Merkmale eines Zukaufartikels: eingetragene Felder, leere aus der Bezeichnung."""
    m = merkmale((a or {}).get("bezeichnung"))
    for f in FELDER:
        w = (a or {}).get(f)
        if w not in (None, ""):
            m[f] = w
    return m


def norm_kennung(norm):
    """'DIN 933' und 'ISO 4017' -> '4017' (gleichwertig); '' ohne Norm."""
    n = re.search(r"(\d{2,5})", str(norm or ""))
    if not n:
        return ""
    nr = n.group(1)
    return GLEICH.get(nr, nr) if str(norm).upper().lstrip().startswith("DIN") else nr


def schluessel(m):
    """(Norm, Größe, Länge) zum Vergleichen; None ohne Norm oder Größe."""
    norm, gr = norm_kennung(m.get("norm")), str(m.get("groesse") or "").upper().replace(" ", "")
    if not norm or not gr:
        return None
    lang = _zahl(m.get("laenge"))
    return norm, gr, f"{lang:g}" if lang else ""


def gleich(m1, m2):
    """Gleiches Normteil? Norm (gleichwertig), Größe und Länge gleich; Festigkeit und Oberfläche nur, wenn beide sie
    nennen."""
    s1, s2 = schluessel(m1), schluessel(m2)
    if not s1 or s1 != s2:
        return False
    for f in ("festigkeit", "norm_oberflaeche"):
        a, b = str(m1.get(f) or "").upper(), str(m2.get(f) or "").upper()
        if a and b and a != b:
            return False
    return True


def finden(artikel, m):
    """Zukaufartikel (nicht archiviert) mit gleichen Merkmalen wie m; None ohne oder bei mehreren Treffern."""
    if not schluessel(m):
        return None
    treffer = [a for a in artikel or () if a.get("status") != "archiviert" and gleich(von_artikel(a), m)]
    return treffer[0] if len(treffer) == 1 else None


def text(m):
    """Merkmale kurz, z. B. 'ISO 4017 · M8 × 20 · 8.8 · verzinkt'."""
    gr = str(m.get("groesse") or "")
    lang = _zahl(m.get("laenge"))
    if gr and lang:
        gr += f" × {lang:g}"
    return " · ".join(str(x) for x in (m.get("norm"), gr, m.get("festigkeit"), m.get("norm_oberflaeche")) if x)
