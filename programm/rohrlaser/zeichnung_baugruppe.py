"""Zeichnung einer Schweißbaugruppe lesen (Plan Spalt Naht Gravur S9, Patrick 26.10.2026 „Möglichkeit Zeichnung einer
Schweißbaugruppe zu lesen und zu analysieren?“ … „mit einbauen“).

Gelesen wird nur der Text: PDF aus dem CAD (pypdfium2), Scan oder Foto mit Tesseract (pdf_zeichnung.lesen, unsicher)
oder DXF (TEXT/MTEXT). Daraus:
- Schweißangaben nach DIN EN ISO 2553: „a4“, „a 3,5“, „z6“ (Schenkel, a = z ÷ √2), „s5“ (Stumpfnaht), mit Unterbrechung
  „a4 3×100 (200)“ (Anzahl × Länge, Abstand), Wörter „umlaufend/rundum“ und „beidseitig“ im selben Textstück;
- die Stückliste: Kopfzeile mit Pos. und Menge (Stück/Anz./Qty), Zeilen darunter in denselben Spalten.
anwenden(bg, …) setzt das a-Maß der Kehlnähte aus der Zeichnung (die Zeichnung ist maßgebend): eine Größe für alle,
mehrere je Nahtgruppe die zur Wanddicke passende (gelb bis bestätigt). abgleich(…) vergleicht die Stückliste mit den
Einzelteilen der Baugruppe. Ohne Qt."""
import math
import re
from pathlib import Path

from . import pdf_zeichnung

ZAHL = r"(\d+(?:[.,]\d+)?)"
# a4, a 4, a=4, a4,5 – nicht in Wörtern (Maß, Draht) und nicht „a4“ als Blattformat (A4, groß)
KEHL = re.compile(r"(?<![A-Za-zÄÖÜäöüß\d])([az])\s*=?\s*" + ZAHL + r"(?![\d])")
STUMPF = re.compile(r"(?<![A-Za-zÄÖÜäöüß\d])s\s*=?\s*" + ZAHL + r"(?![\d])")
UNTERBROCHEN = re.compile(r"(\d+)\s*[xX×*]\s*" + ZAHL + r"\s*(?:\(\s*" + ZAHL + r"\s*\))?")
MENGE_WORTE = ("menge", "stück", "stk", "stck", "anz", "anzahl", "qty", "quantity", "st.")
POS_WORTE = ("pos", "position", "item", "nr")
NAME_WORTE = ("benennung", "bezeichnung", "beschreibung", "description", "name", "titel", "artikel", "teil")
GROESSE_MAX = 30.0       # mm: größere Zahlen hinter a/z/s sind keine Nahtgröße


def _zahl(text):
    try:
        return float(text.replace(",", "."))
    except (TypeError, ValueError):
        return None


def texte(pfad, programmordner=None):
    """Textstücke der Zeichnung: (Liste dict(text, x0, y0, x1, y1) mit y nach unten, ocr) oder ([], False)."""
    pfad = Path(pfad)
    if pfad.suffix.lower() == ".dxf":
        from . import dxf_import
        try:
            roh = dxf_import.roh_lesen(pfad.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            return [], False
        out = []
        for e in dxf_import.elemente(roh):
            if e and e[0] == "T":
                _, _, (x, y), h, _, t = e[:6]
                out.append(dict(text=t, x0=x, y0=-y - h, x1=x + 0.6 * h * len(t), y1=-y))
        return out, False
    erg = pdf_zeichnung.lesen(pfad, programmordner)
    if not erg:
        return [], False
    return erg["segmente"], bool(erg.get("ocr"))


def naehte(segmente):
    """Schweißangaben je Textstück: [dict(nahtart, mass (a-Maß bzw. Dicke), anzahl, laenge, abstand, rundum,
    beidseitig, text)]; z-Maß als a = z ÷ √2 (auf 0,01 mm, nicht abgerundet)."""
    out = []
    for s in segmente:
        t = s["text"]
        tl = t.lower()
        funde = [("Kehlnaht", m) for m in KEHL.finditer(t)] + [("Stumpfnaht", m) for m in STUMPF.finditer(t)]
        for art, m in sorted(funde, key=lambda f: f[1].start()):
            if art == "Kehlnaht":
                wert = _zahl(m.group(2))
                if wert and m.group(1) == "z":
                    wert = round(wert / math.sqrt(2), 2)      # nicht abrunden: a geht im Quadrat ins Schweißgut
            else:
                wert = _zahl(m.group(1))
            if not wert or wert <= 0 or wert > GROESSE_MAX:
                continue
            d = dict(nahtart=art, mass=wert, anzahl=None, laenge=None, abstand=None, text=t.strip(),
                     rundum=any(w in tl for w in ("umlaufend", "rundum", "ringsum", "all around")),
                     beidseitig=any(w in tl for w in ("beidseitig", "both sides")))
            u = UNTERBROCHEN.search(t, m.end())
            if u and u.start() - m.end() <= 6:
                d.update(anzahl=int(u.group(1)), laenge=_zahl(u.group(2)), abstand=_zahl(u.group(3)) if u.group(3)
                         else None)
            out.append(d)
    return out


def _zeilen(segmente):
    """Textstücke zu Zeilen (gleiche Höhe ± halbe Schrifthöhe), oben zuerst, je Zeile links zuerst."""
    zeilen = []
    for s in sorted(segmente, key=lambda s: ((s["y0"] + s["y1"]) / 2, s["x0"])):
        m = (s["y0"] + s["y1"]) / 2
        h = max(s["y1"] - s["y0"], 1.0)
        if zeilen and abs(zeilen[-1][0] - m) <= 0.5 * h:
            zeilen[-1][1].append(s)
        else:
            zeilen.append([m, [s]])
    return [sorted(z, key=lambda s: s["x0"]) for _, z in zeilen]


def _wort(text, worte):
    t = text.strip().lower().rstrip(".:")
    return any(t == w.rstrip(".") or t.startswith(w.rstrip(".") + ".") for w in worte)


def stueckliste(segmente):
    """Stückliste der Zeichnung: [dict(pos, menge, name)] (leer, wenn keine Kopfzeile mit Pos. und Menge da ist).
    Spalten nach der x-Lage der Kopfzeile; eine Zeile gilt, wenn Pos. und Menge ganze Zahlen sind."""
    zeilen = _zeilen(segmente)
    for i, z in enumerate(zeilen):
        pos = next((s for s in z if _wort(s["text"], POS_WORTE)), None)
        menge = next((s for s in z if _wort(s["text"], MENGE_WORTE)), None)
        if pos is None or menge is None:
            continue
        name = next((s for s in z if _wort(s["text"], NAME_WORTE)), None)
        spalten = sorted([s for s in (pos, menge, name) if s], key=lambda s: s["x0"])

        def spalte(s):
            mx = (s["x0"] + s["x1"]) / 2
            return min(spalten, key=lambda k: min(abs(mx - (k["x0"] + k["x1"]) / 2), abs(s["x0"] - k["x0"])))
        out = []
        for zz in zeilen[i + 1:] + zeilen[:i][::-1]:        # Liste unter der Kopfzeile oder (Schriftfeld) darüber
            werte = {}
            for s in zz:
                k = spalte(s)
                werte[id(k)] = (werte.get(id(k), "") + " " + s["text"]).strip()
            p, mg = werte.get(id(pos), ""), werte.get(id(menge), "")
            mz = re.fullmatch(r"(\d+)\s*(?:stk\.?|st\.?|x)?", mg.strip(), re.I)
            if not re.fullmatch(r"\d+", p.strip()) or not mz:
                if out and zz in zeilen[i + 1:]:
                    break                                  # Ende der Liste
                continue
            out.append(dict(pos=int(p), menge=int(mz.group(1)), name=werte.get(id(name), "") if name else ""))
        if out:
            return sorted(out, key=lambda r: r["pos"])
    return []


def lesen(pfad, programmordner=None):
    """Zeichnung lesen: dict(naehte, stueckliste, ocr, hinweise)."""
    seg, ocr = texte(pfad, programmordner)
    hinweise = []
    if not seg:
        hinweise.append("Kein Text in der Zeichnung gefunden")
    elif ocr:
        hinweise.append("Scan/Foto: Text per Texterkennung gelesen, alle Werte prüfen")
    n, sl = naehte(seg), stueckliste(seg)
    if seg and not n:
        hinweise.append("Keine Schweißangabe (a-Maß) gefunden")
    return dict(naehte=n, stueckliste=sl, ocr=ocr, hinweise=hinweise)


def a_masse(erg):
    """Verschiedene a-Maße der Kehlnähte der Zeichnung, aufsteigend."""
    return sorted({n["mass"] for n in erg["naehte"] if n["nahtart"] == "Kehlnaht"})


def _passend(masse, dicke, faktor):
    """a-Maß der Zeichnung, das zur Wanddicke passt: das größte bis Faktor × Dicke, sonst das kleinste."""
    if not dicke:
        return None
    bis = [a for a in masse if a <= faktor * dicke + 1e-9]
    return max(bis) if bis else min(masse)


def anwenden(bg, erg, faktor=0.7, alle=False):
    """a-Maß der Kehlnähte aus der Zeichnung setzen (Zeichnung maßgebend): ohne a-Maß bzw. mit a-Maß nach Regel,
    mit alle=True jede Kehlnaht. Eine Größe in der Zeichnung: diese, sicher; mehrere: je Nahtgruppe die zur Wanddicke
    passende, gelb bis zur Bestätigung (mass_regel). Ändert bg. Ergebnis: Anzahl geänderter Nahtgruppen."""
    masse = a_masse(erg)
    if not masse:
        return 0
    n_ = 0
    for n in bg.get("naehte") or ():
        if n.get("nahtart") != "Kehlnaht" or not (alle or not n.get("mass") or n.get("mass_regel") == n.get("mass")):
            continue
        a = masse[0] if len(masse) == 1 else _passend(masse, n.get("dicke"), faktor)
        if a is None:
            continue
        n["mass"] = a
        n["mass_quelle"] = "Zeichnung"
        if len(masse) == 1:
            n.pop("mass_regel", None)
        else:
            n["mass_regel"] = a
        n_ += 1
    return n_


def abgleich(erg, teile):
    """Stückliste der Zeichnung gegen die Einzelteile der Baugruppe: teile = [dict(name, menge)] (Benennung bzw.
    Artikel, Stück je Baugruppe). Ergebnis: [Text] je Abweichung (leer = passt oder keine Stückliste)."""
    out = []
    rest = list(teile)
    for z in erg["stueckliste"]:
        name = (z["name"] or "").strip().lower()
        t = next((x for x in rest if name and (name in str(x["name"]).lower() or str(x["name"]).lower() in name)),
                 None)
        if t is None:
            out.append(f"Pos. {z['pos']} {z['name']} ({z['menge']}×) fehlt in der Baugruppe")
            continue
        rest.remove(t)
        if t["menge"] != z["menge"]:
            out.append(f"Pos. {z['pos']} {z['name']}: Zeichnung {z['menge']}×, Baugruppe {t['menge']}×")
    if erg["stueckliste"]:
        out += [f"{x['name']} ({x['menge']}×) steht nicht in der Stückliste der Zeichnung" for x in rest]
    return out
