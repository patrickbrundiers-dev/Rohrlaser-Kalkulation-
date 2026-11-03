"""Lieferantenantwort einlesen (Automationen 03.11.2026, Vorschlag 7a).

Die Antwort des Lieferanten auf die Materialanfrage (Mail .msg/.eml oder PDF mit Text) wird ausgelesen: je
Abmessung des Angebots (Profil + Werkstoff) eine Zeile mit Preis und Preisbasis (€/kg, €/m, €/Stange, auch „je 100
kg“, „pro t“), dazu Lieferzeit und „gültig bis“. Die Zeilen erscheinen in den Lieferantenangeboten als „eingelesen“
(gelb) zum Prüfen; „Übernehmen“ in die Stammdaten bleibt ein Klick. Der Lieferant kommt aus der Absenderadresse
(Lieferanten der Zukaufartikel), sonst aus dem Namen im Text. Ohne Qt."""
import datetime
import re

ZAHL = r"(\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:[.,]\d+)?)"
PREIS = re.compile(ZAHL + r"\s*(?:€|EUR|Euro)?\s*(?:/|je|pro|per)\s*(100\s*kg|kg|t|to|tonne|m|lfm|meter|stange|stg|stck|"
                   r"stk|stück)\b", re.I)
PREIS_VOR = re.compile(r"(?:€|EUR)\s*" + ZAHL + r"\s*(?:/|je|pro|per)\s*(100\s*kg|kg|t|m|lfm|stange|stg)\b", re.I)
LIEFERZEIT = re.compile(r"Lieferzeit\D{0,20}?(\d{1,3})\s*(Arbeitstag\w*|Werktag\w*|AT\b|Tag\w*|Woche\w*|Wo\.?)", re.I)
LIEFER_KW = re.compile(r"Liefer\w*\D{0,30}?KW\s*(\d{1,2})(?:\s*/\s*(\d{2,4}))?", re.I)
GUELTIG = re.compile(r"(?:gültig|gueltig|Bindefrist|freibleibend)\D{0,20}?(\d{1,2})\.(\d{1,2})\.(\d{2,4})", re.I)
LAENGE = re.compile(r"(?:à|a|á|Länge|Lieferlänge|in)\s*(\d{1,2}(?:[.,]\d{1,3})?)\s*(m|mm)\b", re.I)


def _zahl(t):
    t = t.strip()
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return None


def basis_umrechnen(wert, einheit):
    """(Preis, Basis) in den Basen der Stammdaten (€/kg, €/m, €/Stange)."""
    e = einheit.lower().replace(" ", "")
    if e == "100kg":
        return wert / 100, "€/kg"
    if e in ("t", "to", "tonne"):
        return wert / 1000, "€/kg"
    if e == "kg":
        return wert, "€/kg"
    if e in ("m", "lfm", "meter"):
        return wert, "€/m"
    return wert, "€/Stange"


def _profil_muster(profil_id, profil):
    """Schreibweisen einer Abmessung im Text: 'QR 40x40x3', '40 x 40 x 3', '40x3' (Rundrohr 'RR 48,3x2,6')."""
    a, b, w = profil.get("a"), profil.get("b"), profil.get("wand")

    def z(x):
        return f"{float(x):g}".replace(".", "[.,]") if x not in (None, "") else None
    muster = [re.escape(str(profil_id)).replace(r"\ ", r"\s*")]
    if a and w:
        teile = [z(a)] + ([z(b)] if b and float(b) != float(a) else []) + [z(w)]
        muster.append(r"(?<![\d.,])" + r"\s*[x×*]\s*".join(teile) + r"(?![\d.,])")
        if b and float(b) == float(a):
            muster.append(r"(?<![\d.,])" + r"\s*[x×*]\s*".join([z(a), z(a), z(w)]) + r"(?![\d.,])")
    return [re.compile(m, re.I) for m in muster if m]


def lieferant_finden(absender, text, lieferanten):
    """Name des Lieferanten: Absenderadresse bzw. -domain passt zur E-Mail eines Lieferanten, sonst Name im Text."""
    absender = (absender or "").lower()
    dom = absender.rpartition("@")[2]
    for z in lieferanten:
        mails = [m.lower() for m in re.findall(r"[\w.+-]+@[\w.-]+", str(z.get("email") or ""))]
        if absender and (absender in mails or (dom and any(m.rpartition("@")[2] == dom for m in mails))):
            return z.get("name")
    for z in lieferanten:
        n = str(z.get("name") or "").strip()
        if len(n) >= 3 and n.casefold() in (text or "").casefold():
            return n
    return None


def lieferzeit_tage(text, heute=None):
    """Lieferzeit in Kalendertagen (Arbeitstage × 7/5, Wochen × 7, KW bis Freitag) oder None."""
    heute = heute or datetime.date.today()
    m = LIEFERZEIT.search(text or "")
    if m:
        n, e = int(m.group(1)), m.group(2).lower()
        if e.startswith("wo"):
            return n * 7
        if e.startswith(("arbeit", "werk", "at")):
            return round(n * 7 / 5)
        return n
    m = LIEFER_KW.search(text or "")
    if m:
        jahr = int(m.group(2)) if m.group(2) else heute.isocalendar()[0]
        jahr = 2000 + jahr if jahr < 100 else jahr
        try:
            ziel = datetime.date.fromisocalendar(jahr, int(m.group(1)), 5)
        except ValueError:
            return None
        if ziel < heute:
            try:
                ziel = datetime.date.fromisocalendar(jahr + 1, int(m.group(1)), 5)
            except ValueError:
                return None
        return (ziel - heute).days
    return None


def gueltig_bis(text):
    m = GUELTIG.search(text or "")
    if not m:
        return None
    t, mo, j = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return datetime.date(2000 + j if j < 100 else j, mo, t).isoformat()
    except ValueError:
        return None


def auslesen(text, paare, profile, stange=None):
    """Zeilen der Antwort: [dict(profil_id, werkstoff_id, preis, basis, laenge, zeile)] für die Abmessungen paare
    [(Profil-ID, Werkstoff-ID)] des Angebots. Gesucht wird je Abmessung die erste Zeile (bzw. die zwei folgenden),
    die die Abmessung und einen Preis mit Einheit nennt."""
    zeilen = [z for z in (text or "").split("\n")]
    out = []
    for pid, ws in paare:
        muster = _profil_muster(pid, profile.get(pid) or {})
        for i, z in enumerate(zeilen):
            if not any(m.search(z) for m in muster):
                continue
            bereich = " ".join(zeilen[i:i + 3])
            mp = PREIS.search(bereich) or PREIS_VOR.search(bereich)
            if not mp:
                continue
            wert = _zahl(mp.group(1))
            if not wert:
                continue
            preis, basis = basis_umrechnen(wert, mp.group(2))
            laenge = None
            ml = LAENGE.search(bereich)
            if ml:
                v = _zahl(ml.group(1))
                laenge = v * 1000 if v and ml.group(2).lower() == "m" else v
            out.append(dict(profil_id=pid, werkstoff_id=ws, preis=round(preis, 4), basis=basis,
                            laenge=laenge or (stange if basis == "€/Stange" else None), zeile=z.strip()[:120]))
            break
    return out


def einlesen(db, angebot_id, text, absender="", paare=(), profile=None, stange=None, heute=None):
    """Antwort auslesen und als 'eingelesen' in die Lieferantenangebote eintragen. Ergebnis: (Lieferant, [Indizes]).
    ValueError, wenn nichts erkannt wurde."""
    from . import automatik, lieferantenangebote as la
    lief = lieferant_finden(absender, text, db.zeilen("zukauf_lieferanten")) or (absender or "unbekannt")
    zeilen = auslesen(text, paare, profile or {}, stange)
    if not zeilen:
        raise ValueError("In der Antwort steht zu keiner Abmessung des Angebots ein Preis mit Einheit (€/kg, €/m, "
                         "€/Stange). Bitte von Hand erfassen.")
    tage, bis = lieferzeit_tage(text, heute), gueltig_bis(text)
    vorher = la.liste(db, angebot_id)
    neu = []
    for z in zeilen:
        neu.append(la.erfassen(db, angebot_id, lief, z["profil_id"], z["werkstoff_id"], z["basis"], z["preis"],
                               tage, z["laenge"], bis, heute))
    alle = la.liste(db, angebot_id)
    for i in neu:
        alle[i]["eingelesen"] = True
    db.zusatz_setzen(angebot_id, la.SCHLUESSEL, alle)
    automatik.merken(db, "lieferantenantwort", f"{lief}: {len(neu)} Preis(e) eingelesen", angebot_id,
                     dict(art="zusatz", angebot_id=angebot_id, schluessel=la.SCHLUESSEL, alt=vorher or None))
    return lief, neu
