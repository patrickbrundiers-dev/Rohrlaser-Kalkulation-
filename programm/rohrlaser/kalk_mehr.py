"""Kalkulation genauer (Roadmap Kalkulation Phase 2, Paket 2c; Freigabe Patrick 13.11.2026 „Ganze Phase 2 nach
Empfehlung“). Alle Einstellungen sind leer ausgeliefert = wie bisher. Ohne Qt.

CALC-010 Sägen statt Lasern: Teile ohne Innenkonturen und Einstiche mit geraden Enden – Sägekosten je Teil
         (Stundensatz Säge × Zeit je Schnitt + Rüsten ÷ Stückzahl) gegen die Laserkosten je Teil; nur Hinweis im
         Angebots-Check, nie automatisch umgestellt.
CALC-018 Ausschuss nach Regel: „Kategorie oder Werkstoff [bis Wand] = Prozent; …“ (z. B. „Edelstahl bis 1,5 = 2“)
         erhöht den Ausschuss der passenden Positionen um diese Prozentpunkte (größte passende Regel).
CALC-020 Programmierzeit je Gehrungsende (schräges Ende): Minuten je schrägem Ende zusätzlich zur Grundzeit."""
import re

EPS = 1e-9


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _zahl(t):
    return float(str(t).replace(",", "."))


# ---------------------------------------------------------------- CALC-020 Programmierzeit je schrägem Ende
def schraege_enden(p):
    """Anzahl schräger Enden (Gehrung a/b) der Position."""
    from .naht import ende_lesen
    return sum(1 for s in ("a_ende", "b_ende") if ende_lesen(p.get(s)))


# ---------------------------------------------------------------- CALC-018 Ausschuss nach Regel
def ausschuss_regeln(text):
    """„Name [bis Wand] = Prozent; …“ -> [(name klein, wand_bis oder None, prozent)]; unlesbare Teile entfallen."""
    out = []
    for teil in re.split(r"[;\n]+", str(text or "")):
        m = re.match(r"\s*(.+?)\s*(?:(?:bis|<=|≤)\s*([0-9]+(?:[.,][0-9]+)?)\s*(?:mm)?)?\s*=\s*\+?\s*"
                     r"([0-9]+(?:[.,][0-9]+)?)\s*%?\s*$", teil, re.IGNORECASE)
        if m and m.group(1).strip():
            out.append((m.group(1).strip().lower(), _zahl(m.group(2)) if m.group(2) else None, _zahl(m.group(3))))
    return out


def ausschuss_plus(p, k, text):
    """Zusätzliche Prozentpunkte Ausschuss der Position nach den Regeln (0 ohne passende Regel): Name passt auf die
    Kategorie, die Werkstoff-ID oder den Werkstoffnamen (Teil des Namens genügt), Wand bis … mm aus dem Profil."""
    regeln = ausschuss_regeln(text)
    if not regeln:
        return 0.0
    ws = (getattr(k, "werkstoffe", None) or {}).get(p.get("werkstoff_id")) or {}
    pr = (getattr(k, "profile", None) or {}).get(p.get("profil_id")) or {}
    namen = " ".join(str(x or "") for x in (ws.get("kategorie"), p.get("werkstoff_id"), ws.get("werkstoff"))).lower()
    wand = _n(pr.get("wand"))
    beste = 0.0
    for name, bis, pct in regeln:
        if name in namen and (bis is None or (wand > 0 and wand <= bis + EPS)):
            beste = max(beste, pct)
    return beste


# ---------------------------------------------------------------- CALC-010 Sägen statt Lasern
def saege_teil(stueck, einst):
    """Sägekosten je Teil [€] oder None, solange Stundensatz oder Zeit je Schnitt fehlen."""
    satz, s = _n((einst or {}).get("saege_satz")), _n((einst or {}).get("saege_s_schnitt"))
    if satz <= 0 or s <= 0 or _n(stueck) <= 0:
        return None
    ruesten = _n((einst or {}).get("saege_ruesten_min")) / 60 * satz
    return s / 3600 * satz + ruesten / _n(stueck)


def saegbar(p):
    """Gerades Teil ohne Innenkonturen und Gehrungen – Kandidat für die Säge."""
    from .rechnen import konturen_anzahl
    if konturen_anzahl(p) or _n(p.get("einstiche")) > 2 or schraege_enden(p):     # 2 Einstiche = die Enden
        return False
    return _n(p.get("laenge")) > 0


def saege_vergleich(positionen, zeilen, einst):
    """[(Index, Pos, Laser € je Teil, Säge € je Teil)] der Positionen, bei denen die Säge günstiger wäre."""
    out = []
    for i, p in enumerate(positionen or ()):
        z = zeilen[i] if zeilen and i < len(zeilen) else None
        c = _n(p.get("stueck"))
        if not z or not c or not saegbar(p):
            continue
        laser = _n(z.get("laser_teil"))
        saege = saege_teil(c, einst)
        if saege is not None and laser > 0 and saege < laser - 0.005:
            out.append((i, p.get("pos"), laser, saege))
    return out
