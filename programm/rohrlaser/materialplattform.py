"""Materialplattform (Patrick 23.11.2026, Master-Auftrag „Materialfenster Next Level“): alles zu einem Material an
einer Stelle, ohne zweite Materialverwaltung. Ohne Qt.

Ein Material ist im Programm die Kombination Abmessung (Profil) + Werkstoff. Materialgruppe = Kategorie des
Werkstoffs (Einstellung „kategorien“, frei erweiterbar). Varianten eines Werkstoffs = alle seine Abmessungen,
Wandstärken und Handelslängen. Alle Werte kommen aus den vorhandenen Tabellen profile, werkstoffe, preise,
lieferlaengen und material_lieferanten und werden mit denselben Formeln wie im Angebot gerechnet (Querschnitt ×
Dichte, Preisbasis €/kg, €/m oder €/Stange, Tonnenpreis inkl. Materialindex des Monats). Der Teuerungszuschlag des
Werkstoffs und Aufpreise der Oberfläche kommen erst in der Position dazu; die Liste zeigt den Grundpreis.

Bausteine:
- varianten(): eine Zeile je Material mit Gewicht, Innenmaß, €/kg, €/m, €/Stange, Handelslängen, Lieferanten,
  Mindestabnahme, Preisstand, Nutzung in Angeboten, Bestand (optionales Lager), Favorit, archiviert.
- suche_zerlegen() / passt(): intelligente Suche („60x40x3 Edelstahl“, „Rundrohr 42,4x2“, „S235“, „1.4301“, „V2A“).
- filtern(), sortieren(), facetten(): Filter mit Anzahl je Wert.
- vergleich() und alternativen(): mehrere Materialien nebeneinander; Alternativen nur mit demselben Werkstoff
  (anderer Lieferant, andere Handelslänge), andere Güten nur als Hinweis (die Qualität ändert sich nie von selbst).
- bilanz(): theoretischer Verbrauch gegen tatsächlichen Einkauf einer Abmessung des Angebots, Reste nur gemeldet
  (kein Restelager).
- Schreiben (über die Datenbank-Funktionen neu/aendern, also mit Änderungsverlauf, Abgleich und Sperre):
  duplizieren(), archivieren(), mehrfach_aendern(), lieferant_uebernehmen(), csv_export()/csv_lesen()/
  csv_importieren().
"""
import csv
import datetime
import io
import math
import re

from . import masstext
from .stammdaten import flaeche_wirksam

EPS = 1e-9
JA = "ja"
ARCHIV = "archiviert"
FAVORITEN = "material_favoriten"        # Einstellung nur für diesen Arbeitsplatz (teilen.LOKAL)
LIEFERANTEN_TABELLE = "material_lieferanten"
STAMM_TABELLE = "materialstamm"
QUELLE_PREISE, QUELLE_LIEFERLAENGE, QUELLE_TONNE, QUELLE_FEHLT = "Preise", "Lieferlänge", "Tonnenpreis", "fehlt"
STAND_ALT_TAGE = 30                      # wie preisalter.VORGABE_TAGE

# Profilformen in der Suche: Wörter und Kürzel
FORM_WORTE = {
    "rundrohr": "Rundrohr", "rund": "Rundrohr", "rr": "Rundrohr", "rohr": None, "ø": "Rundrohr",
    "quadratrohr": "Quadratrohr", "quadrat": "Quadratrohr", "vierkant": "Quadratrohr", "vierkantrohr": "Quadratrohr",
    "qr": "Quadratrohr", "vkt": "Quadratrohr",
    "rechteckrohr": "Rechteckrohr", "rechteck": "Rechteckrohr", "re": "Rechteckrohr",
    "flachstahl": "Flachstahl", "flach": "Flachstahl", "fl": "Flachstahl",
    "u-profil": "U-Profil", "uprofil": "U-Profil", "c-profil": "C-Profil", "l-profil": "L-Profil", "winkel": "L-Profil",
    "flachoval": "Flachoval", "oval": "Flachoval",
}
VORSILBEN = ("aisi", "aw", "enaw", "st")                # Zahl danach gehört zum Werkstoffnamen
_WNR = re.compile(r"^\d\.\d{4}$")                       # Werkstoffnummer 1.4301
_MASS = re.compile(r"^(?:ø|d)?(\d+(?:[.,]\d+)?)(?:x(\d+(?:[.,]\d+)?))?(?:x(\d+(?:[.,]\d+)?))?(?:mm)?$")


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _leer(v):
    return v is None or (isinstance(v, str) and not v.strip())


def schluessel(z):
    return (z.get("profil_id"), z.get("werkstoff_id"))


def archiviert(z):
    return str((z or {}).get("archiviert") or "").strip().lower() == JA


# ------------------------------------------------------------------ Kennwerte
def kg_je_m(profil, werkstoff):
    fl = flaeche_wirksam(profil) if profil else None
    d = _n((werkstoff or {}).get("dichte"))
    return fl * d / 1000 if fl is not None and d is not None else None


def innenmass(profil):
    """Innenmaß als Text: Rundrohr Innen-Ø, Quadrat-/Rechteckrohr Breite × Höhe innen, sonst None."""
    form, a, b, s = (profil or {}).get("form"), _n((profil or {}).get("a")), _n((profil or {}).get("b")), \
        _n((profil or {}).get("wand"))
    if a is None or s is None:
        return None
    if form == "Rundrohr":
        return dict(text=f"Ø {_mm(a - 2 * s)}", d=a - 2 * s)
    if form == "Quadratrohr":
        return dict(text=f"{_mm(a - 2 * s)} × {_mm(a - 2 * s)}", d=None)
    if form == "Rechteckrohr" and b is not None:
        return dict(text=f"{_mm(a - 2 * s)} × {_mm(b - 2 * s)}", d=None)
    return None


def _mm(x):
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def je_meter(basis, preis, kgm, laenge):
    """Preis einer Zeile (Preise, Lieferlängen, Lieferanten) in €/m; None, wenn nicht umrechenbar."""
    p = _n(preis)
    if p is None or p <= 0:
        return None
    if basis == "€/m":
        return p
    if basis == "€/kg":
        return p * kgm if kgm is not None else None
    if basis == "€/Stange":
        lg = _n(laenge)
        return p * 1000 / lg if lg and lg > 0 else None
    return None


def je_kg(preis_m, kgm):
    return preis_m / kgm if preis_m is not None and kgm else None


def _datum(w):
    try:
        return datetime.date.fromisoformat(str(w or "")[:10])
    except ValueError:
        return None


# ------------------------------------------------------------------ Varianten
def varianten(k, tabellen, lieferanten=(), nutzung=None, bestand=None, favoriten=(), alle=False,
              mit_archiv=False, heute=None, stange=None, erp=None, stamm=None):
    """Eine Zeile je Material (Profil + Werkstoff).

    alle=False: nur Kombinationen, die es schon gibt (Zeile in Preise, Lieferlängen oder Lieferanten, oder in einer
    Angebotsposition verwendet); alle=True: jede Abmessung mit jedem Werkstoff (Pflege, neue Kombinationen).
    nutzung = {(profil, werkstoff): (Anzahl Angebote, zuletzt ISO)}, bestand = {(profil, werkstoff): dict(stangen,
    reste)} (nur mit eingeschaltetem Lager), favoriten = [[profil, werkstoff]], stange = Stangenlänge des Angebots
    für €/Stange (Vorgabe 6.000 mm), erp = {(profil, werkstoff): ERP-Gruppe aus erp_gruppen()} (Einkauf aus der
    ERP-CSV, nur Anzeige), stamm = Zeilen des Materialstamms (Materialnummer, Bezeichnung, Aktiv; jede Zeile ist eine
    Kombination). Archivierte Profile und Werkstoffe nur mit mit_archiv."""
    heute = heute or datetime.date.today()
    nutzung, bestand, erp = nutzung or {}, bestand or {}, erp or {}
    fav = {tuple(f) for f in favoriten or () if isinstance(f, (list, tuple)) and len(f) == 2}
    preise = {}
    for z in (tabellen or {}).get("preise") or ():
        preise.setdefault(schluessel(z), z)
    laengen, lief = {}, {}
    for z in (tabellen or {}).get("lieferlaengen") or ():
        laengen.setdefault(schluessel(z), []).append(z)
    for z in lieferanten or ():
        lief.setdefault(schluessel(z), []).append(z)
    st = {}
    for z in sorted(stamm or (), key=lambda z: bool(z.get("oberflaeche"))):    # ohne Oberfläche zuerst
        st.setdefault(schluessel(z), z)
    if alle:
        kombis = [(p, w) for p in k.profile for w in k.werkstoffe]
    else:
        kombis = list(dict.fromkeys(list(st) + list(preise) + list(laengen) + list(lief) + list(nutzung) + list(fav)
                                    + list(erp)))
    std = _n(stange) or 6000.0
    out = []
    for pid, wid in kombis:
        pr, ws = k.profile.get(pid), k.werkstoffe.get(wid)
        if pr is None or ws is None:
            continue
        arch = archiviert(pr) or archiviert(ws)
        if arch and not mit_archiv:
            continue
        out.append(_zeile(pid, wid, pr, ws, preise.get((pid, wid)), laengen.get((pid, wid), []),
                          lief.get((pid, wid), []), nutzung.get((pid, wid)), bestand.get((pid, wid)),
                          (pid, wid) in fav, arch, heute, std, erp.get((pid, wid)), st.get((pid, wid))))
    return out


def _stamm_felder(sz):
    sz = sz or {}
    return dict(materialnr=sz.get("materialnr") or "", material_bez=sz.get("bezeichnung") or "",
                handelsname=sz.get("handelsname") or "", im_stamm=bool(sz), inaktiv=sz.get("aktiv") == "nein",
                stamm_quelle=sz.get("quelle") or "")


def _zeile(pid, wid, pr, ws, preis, laengen, lief, nutz, best, fav, arch, heute, std, erp=None, sz=None):
    kgm = kg_je_m(pr, ws)
    quelle, preis_m, stand, lieferant, mindest = QUELLE_FEHLT, None, None, "", None
    if preis is not None:
        preis_m = je_meter(preis.get("basis"), preis.get("preis"), kgm, preis.get("lieferlaenge") or std)
        if preis_m is not None:
            quelle, stand, lieferant, mindest = QUELLE_PREISE, preis.get("gueltig_ab"), preis.get("lieferant") or "", \
                preis.get("mindest_stangen")
    if preis_m is None:
        for z in sorted(laengen, key=lambda z: abs(_n(z.get("laenge")) or 0 - std)):
            pm = je_meter(z.get("basis") or (preis or {}).get("basis"), z.get("preis"), kgm, z.get("laenge"))
            if pm is not None:
                quelle, preis_m, stand, lieferant, mindest = QUELLE_LIEFERLAENGE, pm, z.get("gueltig_ab"), \
                    z.get("lieferant") or "", z.get("mindest_stangen")
                break
    if preis_m is None:
        tonne = _n(ws.get("tonnenpreis"))
        if tonne is not None and kgm is not None:
            quelle, preis_m = QUELLE_TONNE, kgm * tonne / 1000
    handel = sorted({int(_n(z.get("laenge"))) for z in laengen if _n(z.get("laenge"))}
                    | ({int(_n(preis.get("lieferlaenge")))} if preis and _n(preis.get("lieferlaenge")) else set()))
    namen = [lieferant] if lieferant else []
    for z in lief:
        if z.get("lieferant") and z["lieferant"] not in namen:
            namen.append(z["lieferant"])
    d = _datum(stand)
    alter = (heute - d).days if d else None
    innen = innenmass(pr)
    a, b, s = _n(pr.get("a")), _n(pr.get("b")), _n(pr.get("wand"))
    return dict(
        profil_id=pid, werkstoff_id=wid, form=pr.get("form") or "", a=a, b=b, wand=s,
        kategorie=ws.get("kategorie") or "", werkstoff=ws.get("werkstoff") or "", werkstoff_nr=ws.get("werkstoff_nr") or "",
        norm=ws.get("norm") or "", dichte=_n(ws.get("dichte")), kgm=kgm, innen=innen["text"] if innen else "",
        preis_m=preis_m, preis_kg=je_kg(preis_m, kgm), preis_stange=preis_m * std / 1000 if preis_m is not None else None,
        quelle=quelle, stand=str(stand or "")[:10], alter_tage=alter, lieferant=lieferant,
        lieferanten=namen, n_lieferanten=len(namen), mindest=_n(mindest),
        handelslaengen=handel, tonnenpreis=_n(ws.get("tonnenpreis")),
        nutzung=(nutz or (0, ""))[0], zuletzt=str((nutz or (0, ""))[1] or "")[:10],
        bestand_stangen=(best or {}).get("stangen"), bestand_reste=(best or {}).get("reste"),
        favorit=fav, archiviert=arch, bemerkung=pr.get("bemerkung") or "",
        **_erp_felder(erp, preis_m if quelle != QUELLE_TONNE else None), **_stamm_felder(sz),
        _such=_suchtext(pid, wid, pr, ws, namen + [x for x in ((sz or {}).get("materialnr"), (sz or {}).get(
            "bezeichnung"), (sz or {}).get("handelsname")) if x]))


def _erp_felder(g, preis_m):
    """ERP-Einkauf eines Materials: Ø €/m (nach Menge gewichtet, Zeitraum erp_monate), letzter Kauf, Meter, Anzahl
    und Abweichung des Ø vom Stammdatenpreis in % (nur gegen Preise/Lieferlängen, nicht gegen den Tonnenpreis)."""
    if not g:
        return dict(erp_schnitt=None, erp_letzter=None, erp_datum="", erp_meter=None, erp_anzahl=0, erp_abw=None,
                    erp_ober="", erp_lieferzeit=None, erp_lz=None)
    schnitt = g.get("durchschnitt")
    d = g.get("letzter_datum")
    return dict(erp_schnitt=schnitt, erp_letzter=g.get("letzter"), erp_datum=d.isoformat() if d else "",
                erp_meter=g.get("meter"), erp_anzahl=len(g.get("kaeufe") or ()),
                erp_abw=(schnitt / preis_m - 1) * 100 if schnitt and preis_m and not g.get("oberflaeche") else None,
                erp_ober=g.get("oberflaeche") or "", erp_lz=g.get("lieferzeit"),
                erp_lieferzeit=(g.get("lieferzeit") or {}).get("tage"))


_WS_TEXT = {}


def _werkstoff_text(wid, ws):
    """Suchtext des Werkstoffs mit gleichwertigen Namen (einmal je Werkstoff, nicht je Variante)."""
    schl = (wid, ws.get("werkstoff"), ws.get("werkstoff_nr"), ws.get("norm"), ws.get("kategorie"))
    t = _WS_TEXT.get(schl)
    if t is None:
        from . import werkstoff_namen
        gl = set()
        for n in (wid, ws.get("werkstoff"), ws.get("werkstoff_nr")):
            gl |= werkstoff_namen.gleichnamen(n)
        t = _wortnorm(" ".join(str(x) for x in schl if x) + " " + " ".join(sorted(gl)))
        if len(_WS_TEXT) > 5000:
            _WS_TEXT.clear()
        _WS_TEXT[schl] = t
    return t


def _suchtext(pid, wid, pr, ws, namen):
    teile = [pid, pr.get("form"), pr.get("bemerkung")] + list(namen)
    return " " + _wortnorm(" ".join(str(x) for x in teile if x)) + " " + _werkstoff_text(wid, ws) + " "


def _wortnorm(t):
    """Kleinbuchstaben, Trennzeichen außer Punkt und Komma als Leerzeichen (Wortanfang über ' ' + Wort prüfbar)."""
    return re.sub(r"[^0-9a-zäöüß.,ø]+", " ", str(t or "").lower()).strip()


# ------------------------------------------------------------------ Suche
def _zahl(t):
    return float(t.replace(",", ".")) if t else None


def suche_zerlegen(text):
    """Suchtext in Profilform, Maße und Wörter: dict(form, masse=[Zahlen in Reihenfolge], ganz=[bool je Maß: ohne
    Nachkomma eingegeben], worte=[…]). Schreibweisen: „40 x 40 x 2“, „40*40*2“, „40×40×2“, „42,4x2“, „Ø42,4x2“."""
    t = str(text or "").lower().replace("×", "x").replace("*", "x")
    t = re.sub(r"\s*x\s*", "x", t)
    form, masse, ganz, worte = None, [], [], []
    for w in t.split():
        w = w.strip(";:")
        if not w:
            continue
        if _WNR.match(w):
            worte.append(w)
            continue
        if worte and worte[-1] in VORSILBEN and re.match(r"^\d", w):     # „AISI 304“, „EN AW 6060“
            worte[-1] += w
            continue
        if w in FORM_WORTE:
            form = FORM_WORTE[w] or form
            continue
        mw = _MASS.match(w)
        if mw and not masse:
            for g in mw.groups():
                if g is not None:
                    masse.append(_zahl(g))
                    ganz.append("," not in g and "." not in g)
            continue
        m2 = re.match(r"^(rr|qr|re|fl)(\d.*)$", w)         # „QR40x40x2“ ohne Leerzeichen
        if m2 and _MASS.match(m2.group(2)) and not masse:
            form = FORM_WORTE[m2.group(1)]
            for g in _MASS.match(m2.group(2)).groups():
                if g is not None:
                    masse.append(_zahl(g))
                    ganz.append("," not in g and "." not in g)
            continue
        worte.append(w)
    return dict(form=form, masse=masse, ganz=ganz, worte=worte)


def _formen_masse(z):
    """Mögliche Schreibweisen der Maße einer Zeile (je Folge von Zahlen)."""
    a, b, s, form = z.get("a"), z.get("b"), z.get("wand"), z.get("form")
    if a is None:
        return []
    if form == "Rundrohr" or form == "Flachstahl":
        return [(a, s)]
    if form == "Quadratrohr":
        return [(a, a, s), (a, s)]
    if b is not None:
        return [(a, b, s), (b, a, s)]
    return [(a, s)]


def _mass_gleich(q, v, ganz):
    if v is None:
        return False
    if abs(q - v) < 0.051:
        return True
    return bool(ganz) and math.floor(v + EPS) == q     # „42“ findet 42,4 (unvollständige Eingabe)


def passt(z, s):
    """True, wenn die Zeile z zur zerlegten Suche s passt; Wert für die Reihenfolge über treffer()."""
    return treffer(z, s) is not None


def treffer(z, s):
    """None, wenn die Zeile nicht passt, sonst Rang (kleiner = besser: genaue Maße vor ungefähren)."""
    if s.get("form") and z.get("form") != s["form"]:
        return None
    rang = 0
    q = s.get("masse") or []
    if q:
        best = None
        for folge in _formen_masse(z):
            if len(q) > len(folge):
                continue
            ok, ungefaehr = True, 0
            for qi, vi, g in zip(q, folge, s.get("ganz") or [False] * len(q)):
                if abs(qi - (vi or -1)) < 0.051:
                    continue
                if _mass_gleich(qi, vi, g):
                    ungefaehr += 1
                    continue
                ok = False
                break
            if ok:
                best = ungefaehr if best is None else min(best, ungefaehr)
        if best is None:
            return None
        rang += best * 10 + (0 if len(q) == len(_formen_masse(z)[0]) else 1)
    such = z.get("_such") or ""
    for w in s.get("worte") or ():
        if " " + _wortnorm(w) not in such:       # am Wortanfang: „stahl“ findet nicht „edelstahl“
            return None
    return rang - (5 if z.get("favorit") else 0) - min(z.get("nutzung") or 0, 50) / 100


def suchen(zeilen, text):
    """Passende Zeilen, beste zuerst (bei leerem Text alle in ihrer Reihenfolge)."""
    s = suche_zerlegen(text)
    if not s["masse"] and not s["worte"] and not s["form"]:
        return list(zeilen)
    bewertet = [(r, i, z) for i, z in enumerate(zeilen) if (r := treffer(z, s)) is not None]
    bewertet.sort(key=lambda x: (x[0], x[1]))
    return [z for _, _, z in bewertet]


# ------------------------------------------------------------------ Filter
FILTER = (("kategorie", "Materialgruppe"), ("form", "Profilart"), ("wand", "Wandstärke"),
          ("werkstoff_id", "Werkstoff"), ("lieferant", "Lieferant"), ("zustand", "Zustand"))
ZUSTAND_ALT, ZUSTAND_OHNE, ZUSTAND_TONNE, ZUSTAND_ARCHIV, ZUSTAND_FAV, ZUSTAND_BENUTZT = (
    "Preis älter als 30 Tage", "ohne Preis", "nur Tonnenpreis", "archiviert", "Favorit", "in Angeboten")
ZUSTAND_ERP, ZUSTAND_ERP_ABW, ZUSTAND_VORSCHLAG = "mit ERP-Einkauf", "ERP weicht über 10 % ab", "mit Preisvorschlag"
ZUSTAND_STAMM, ZUSTAND_INAKTIV, ZUSTAND_OHNE_STAMM = "im Materialstamm", "inaktiv", "nicht im Materialstamm"
ERP_ABW_PCT = 10.0


def zustaende(z, alt_tage=STAND_ALT_TAGE):
    out = []
    if z.get("favorit"):
        out.append(ZUSTAND_FAV)
    if z.get("quelle") == QUELLE_FEHLT:
        out.append(ZUSTAND_OHNE)
    elif z.get("quelle") == QUELLE_TONNE:
        out.append(ZUSTAND_TONNE)
    if z.get("alter_tage") is not None and z["alter_tage"] > alt_tage:
        out.append(ZUSTAND_ALT)
    if z.get("archiviert"):
        out.append(ZUSTAND_ARCHIV)
    if z.get("nutzung"):
        out.append(ZUSTAND_BENUTZT)
    if z.get("erp_anzahl"):
        out.append(ZUSTAND_ERP)
        if z.get("erp_abw") is not None and abs(z["erp_abw"]) > ERP_ABW_PCT:
            out.append(ZUSTAND_ERP_ABW)
    if z.get("vorschlag_m") is not None:
        out.append(ZUSTAND_VORSCHLAG)
    out.append(ZUSTAND_STAMM if z.get("im_stamm") else ZUSTAND_OHNE_STAMM)
    if z.get("inaktiv"):
        out.append(ZUSTAND_INAKTIV)
    return out


def _werte(z, feld):
    if feld == "zustand":
        return zustaende(z)
    if feld == "lieferant":
        return list(z.get("lieferanten") or []) or ["ohne Lieferant"]
    if feld == "wand":
        return [_mm(z["wand"])] if z.get("wand") is not None else []
    v = z.get(feld)
    return [v] if not _leer(v) else []


def filtern(zeilen, auswahl):
    """auswahl = {feld: {Werte}}: je Feld muss einer der Werte passen (UND über die Felder)."""
    aktiv = {f: set(w) for f, w in (auswahl or {}).items() if w}
    if not aktiv:
        return list(zeilen)
    return [z for z in zeilen if all(set(_werte(z, f)) & w for f, w in aktiv.items())]


def facetten(zeilen):
    """Anzahl je Wert und Filterfeld: {feld: [(Wert, Anzahl)]}, häufigste zuerst (Wandstärke nach Zahl)."""
    out = {}
    for f, _ in FILTER:
        zaehl = {}
        for z in zeilen:
            for w in _werte(z, f):
                zaehl[w] = zaehl.get(w, 0) + 1
        if f == "wand":
            out[f] = sorted(zaehl.items(), key=lambda x: float(x[0].replace(",", ".")))
        else:
            out[f] = sorted(zaehl.items(), key=lambda x: (-x[1], str(x[0])))
    return out


def zuletzt(zeilen, anzahl=20):
    return sorted([z for z in zeilen if z.get("zuletzt")], key=lambda z: z["zuletzt"], reverse=True)[:anzahl]


def haeufig(zeilen, anzahl=20):
    return sorted([z for z in zeilen if z.get("nutzung")], key=lambda z: -z["nutzung"])[:anzahl]


# ------------------------------------------------------------------ Vergleich
VERGLEICH = (("preis_m", "Preis [€/m]", 2), ("preis_kg", "Preis [€/kg]", 2), ("kgm", "Gewicht [kg/m]", 3),
             ("werkstoff_id", "Werkstoff / Güte", None), ("norm", "Norm", None), ("quelle", "Preisquelle", None),
             ("stand", "Preisstand", None), ("handelslaengen", "Handelslängen [mm]", None),
             ("lieferanten", "Lieferanten", None), ("mindest", "Mindestabnahme [Stangen]", 0),
             ("bestand_stangen", "Bestand [Stangen]", 0), ("erp_schnitt", "ERP-Einkauf Ø [€/m]", 2),
             ("erp_lieferzeit", "Lieferzeit Ø [Tage]", 0), ("verschnitt", "Verschnitt bei den Teilen", None))


def vergleich(zeilen, teile_mm=None, maschine=None):
    """Vergleichstabelle: dict(spalten=[Material-Name], zeilen=[(Titel, [Werte], bestes Index oder None)]).
    teile_mm = Teilelängen [mm] (z. B. die Positionen eines Angebots) für das Verschnittpotenzial je Handelslänge,
    als Liste für alle Spalten oder {Profil-ID: Liste} (jede Abmessung mit ihren eigenen Teilen)
    (verschnitt_schaetzen); maschine = dict(endbeschnitt, greiferrest, kerf)."""
    namen = [f"{z['profil_id']} · {z['werkstoff_id']}" for z in zeilen]
    out = []
    for feld, titel, stellen in VERGLEICH:
        werte = []
        for z in zeilen:
            if feld == "verschnitt":
                t = teile_mm.get(z["profil_id"]) if isinstance(teile_mm, dict) else teile_mm
                werte.append(verschnitt_text(z, t, maschine) if t else None)
            else:
                werte.append(z.get(feld))
        bestes = None
        if feld in ("preis_m", "preis_kg"):
            nums = [(w, i) for i, w in enumerate(werte) if isinstance(w, (int, float))]
            bestes = min(nums)[1] if len(nums) > 1 else None
        out.append((titel, werte, bestes))
    return dict(spalten=namen, zeilen=out, hinweise=guete_hinweise(zeilen))


def guete_hinweise(zeilen):
    """Vergleich mit unterschiedlichen Werkstoffen: Hinweis, dass eine andere Güte eine technische Entscheidung ist."""
    ws = {z.get("werkstoff_id") for z in zeilen}
    if len(ws) > 1:
        return ["Unterschiedliche Werkstoffe: ein günstigeres Material mit anderer Güte ist nur ein Hinweis. "
                "Ob es technisch passt, entscheidet der Anwender bzw. der Kunde; das Programm ändert die Güte nie."]
    return []


def verschnitt_schaetzen(teile_mm, stange, endbeschnitt=10.0, greiferrest=140.0, kerf=0.2):
    """Stangen und Verschnitt für gerade Teile (Teilelängen in mm) auf Stangen der Länge stange, mit der Optimierung
    des Programms (optimierung.optimiere, gleiche Prüfung gegen Überbelegung). dict(stangen, verschnitt_m,
    ausnutzung, passt_nicht)."""
    from . import optimierung as opt
    teile, nicht = [], 0
    nutz = stange - endbeschnitt - greiferrest - kerf
    for i, lg in enumerate(teile_mm or ()):
        if lg <= 0:
            continue
        if lg > nutz + EPS:
            nicht += 1
            continue
        teile.append(opt.Teil(i, i + 1, f"T{i + 1}", 1, float(lg), True, True, 0.0, 0.0))
    if not teile:
        return dict(stangen=0, verschnitt_m=0.0, ausnutzung=None, passt_nicht=nicht)
    g = opt.Gruppe("Vergleich", "", float(stange), float(endbeschnitt), float(greiferrest), float(kerf), 0.0,
                   teile=teile)
    folgen = opt.optimiere(g)
    summe = sum(t.laenge for t in teile)
    gesamt = len(folgen) * stange
    return dict(stangen=len(folgen), verschnitt_m=(gesamt - summe) / 1000, ausnutzung=summe / gesamt if gesamt else None,
                passt_nicht=nicht)


def verschnitt_text(z, teile_mm, maschine=None):
    m = maschine or {}
    teile = []
    for lg in z.get("handelslaengen") or [6000]:
        e = verschnitt_schaetzen(teile_mm, lg, m.get("endbeschnitt", 10.0), m.get("greiferrest", 140.0),
                                 m.get("kerf", 0.2))
        if e["stangen"]:
            m_txt = f"{lg / 1000:g}".replace(".", ",")
            pct = f"{e['ausnutzung'] * 100:.1f}".replace(".", ",")
            teile.append(f"{m_txt} m: {e['stangen']} St., {pct} %")
    return " · ".join(teile) or None


def alternativen(zeile, lieferanten, k, tabellen, heute=None):
    """Wirtschaftliche Alternativen zum Material ohne Änderung der Güte: andere Lieferanten (gültige Preise) und
    andere Handelslängen desselben Profils + Werkstoffs, günstigste zuerst. Gleichwertige Werkstoffnamen (z. B. V2A =
    1.4301) mit eigener Stammdatenzeile stehen als Hinweis dabei. Je Eintrag dict(art, text, preis_m, ersparnis_pct,
    quelle)."""
    heute = heute or datetime.date.today()
    pid, wid = zeile["profil_id"], zeile["werkstoff_id"]
    kgm, basis = zeile.get("kgm"), zeile.get("preis_m")
    out = []
    for z in lieferanten or ():
        if schluessel(z) != (pid, wid) or not gueltig(z, heute):
            continue
        pm = je_meter(z.get("basis"), z.get("preis"), kgm, z.get("laenge") or 6000)
        if pm is None or (z.get("lieferant") or "") == zeile.get("lieferant") and basis and abs(pm - basis) < 0.005:
            continue
        out.append(dict(art="Lieferant", text=f"{z.get('lieferant')}"
                        + (f", {int(z['laenge'])} mm" if _n(z.get("laenge")) else "")
                        + (f", Lieferzeit {int(z['lieferzeit'])} Tage" if _n(z.get("lieferzeit")) else "")
                        + (f", gültig bis {_datum(z.get('gueltig_bis')).strftime('%d.%m.%Y')}"
                           if _datum(z.get("gueltig_bis")) else ""),
                        preis_m=pm, ersparnis_pct=(basis - pm) / basis * 100 if basis else None, quelle=z))
    for z in (tabellen or {}).get("lieferlaengen") or ():
        if schluessel(z) != (pid, wid):
            continue
        pm = je_meter(z.get("basis") or "€/kg", z.get("preis"), kgm, z.get("laenge"))
        if pm is None:
            continue
        out.append(dict(art="Handelslänge", text=f"{int(_n(z['laenge']) or 0)} mm" +
                        (f" bei {z['lieferant']}" if z.get("lieferant") else ""),
                        preis_m=pm, ersparnis_pct=(basis - pm) / basis * 100 if basis else None, quelle=z))
    out.sort(key=lambda a: a["preis_m"])
    from . import werkstoff_namen
    gleich = werkstoff_namen.passende(wid, list(k.werkstoffe.values()))
    for w in gleich:
        if w != wid:
            out.append(dict(art="Gleichwertig (Hinweis)", text=f"{w} ist laut Werkstoffliste gleichwertig zu {wid}; "
                            "eigene Stammdatenzeile, Wahl nur von Hand", preis_m=None, ersparnis_pct=None, quelle=None))
    return out


def gueltig(z, heute=None):
    """Lieferantenpreis gültig: ab-Datum nicht in der Zukunft, bis-Datum nicht überschritten."""
    heute = heute or datetime.date.today()
    ab, bis = _datum(z.get("gueltig_ab")), _datum(z.get("gueltig_bis"))
    return (ab is None or ab <= heute) and (bis is None or bis >= heute)


# ------------------------------------------------------------------ Bilanz (Phase 5)
def bilanz(gruppe, paare, kgm, preis_m, einkauf_eur=None, rest_min=None, mindest=None):
    """Theoretischer Materialverbrauch gegen tatsächlichen Einkauf einer Abmessung des Angebots.

    gruppe = Zeile aus rechnen.material_abmessungen, paare = abmessung.lieferstangen(...), kgm, preis_m = wirksamer
    Preis €/m, einkauf_eur = Materialkosten der Stangen (Summe stangen_werte 'kosten'), rest_min = kleinste Restlänge,
    die als wiederverwendbar gemeldet wird [mm] (None/0 = keine Meldung), mindest = Mindestabnahme [Stangen].
    Ergebnis dict(theorie_m, theorie_kg, theorie_eur, einkauf_stangen, einkauf_m, einkauf_kg, einkauf_eur,
    mehr_eur, verschnitt_pct, mindest_mehr, reste=[Länge mm, längste zuerst], reste_m). Reste werden nur gemeldet,
    nicht eingelagert und nicht verrechnet (Patrick: kein Restelager)."""
    teile_m = sum(t["laenge"] for s, _ in paare for t in s["teile"]) / 1000
    einkauf_m = sum(s["stange"] for s, _ in paare) / 1000
    n = len(paare)
    reste = []
    for s, _ in paare:
        if s.get("zugeschnitten"):
            continue
        rest = s["stange"] - s["end"] - sum(t["laenge"] for t in s["teile"]) - s["verlust"] - s["greif"]
        if rest_min and rest + s["greif"] >= rest_min - EPS:
            reste.append(round(rest + s["greif"]))       # das Stück hinter dem letzten Schnitt inkl. Greiferrest
    reste.sort(reverse=True)
    theorie_eur = teile_m * preis_m if preis_m is not None else None
    eink = einkauf_eur if einkauf_eur is not None else (einkauf_m * preis_m if preis_m is not None else None)
    mehr = max(int(mindest) - n, 0) if _n(mindest) else 0
    return dict(theorie_m=teile_m, theorie_kg=teile_m * kgm if kgm is not None else None, theorie_eur=theorie_eur,
                einkauf_stangen=n, einkauf_m=einkauf_m, einkauf_kg=einkauf_m * kgm if kgm is not None else None,
                einkauf_eur=eink, mehr_eur=eink - theorie_eur if eink is not None and theorie_eur is not None else None,
                verschnitt_pct=(1 - teile_m / einkauf_m) * 100 if einkauf_m else None, mindest_mehr=mehr,
                reste=reste, reste_m=sum(reste) / 1000)


# ------------------------------------------------------------------ Datenbank lesen
def nutzung(db):
    """{(Profil, Werkstoff): (Anzahl Angebote, zuletzt geändert)} aus allen Positionen (eine Abfrage)."""
    out = {}
    try:
        for r in db.con.execute(
                "SELECT p.profil_id, p.werkstoff_id, COUNT(DISTINCT p.angebot_id), MAX(a.geaendert) FROM positionen p "
                "JOIN angebote a ON a.id = p.angebot_id WHERE p.profil_id IS NOT NULL AND p.werkstoff_id IS NOT NULL "
                "GROUP BY p.profil_id, p.werkstoff_id"):
            out[(r[0], r[1])] = (int(r[2] or 0), r[3] or "")
    except Exception:           # noqa: BLE001  (ältere Datei ohne Spalten: keine Nutzung)
        from . import protokoll
        protokoll.warnung("Materialplattform: Nutzung nicht lesbar")
    return out


def lager_bestand(db):
    """{(Profil, Werkstoff): dict(stangen, reste)} verfügbar im optionalen Lager; leer ohne Lager."""
    from . import lager
    try:
        if not lager.aktiv(db):
            return {}
        out = {}
        for z in lager.bestand(db):
            e = out.setdefault((z.get("profil"), z.get("werkstoff")), dict(stangen=0, reste=0))
            e["reste" if str(z.get("kennung") or "").startswith("R") else "stangen"] += max(z.get("verfuegbar") or 0, 0)
        return out
    except Exception:           # noqa: BLE001
        return {}


def favoriten(db):
    w = db.einstellung(FAVORITEN)
    return [list(f) for f in w if isinstance(f, (list, tuple)) and len(f) == 2] if isinstance(w, list) else []


def favorit_setzen(db, profil_id, werkstoff_id, an=True):
    f = [x for x in favoriten(db) if tuple(x) != (profil_id, werkstoff_id)]
    if an:
        f.append([profil_id, werkstoff_id])
    db.einstellung_setzen(FAVORITEN, f)
    return f


def alle_varianten(db, alle=False, mit_archiv=False):
    """varianten() mit den Daten der Datenbank (Kontext, Tabellen, Lieferanten, Nutzung, Lager, Favoriten, ERP)."""
    return varianten(db.kontext(), db.tabellen(), db.zeilen(LIEFERANTEN_TABELLE), nutzung(db), lager_bestand(db),
                     favoriten(db), alle=alle, mit_archiv=mit_archiv, erp=erp_gruppen(db), stamm=db.zeilen(STAMM_TABELLE))


def erp_gruppen(db, heute=None):
    """ERP-Einkauf je Material aus der eingelesenen EK-CSV (erp_preise.auswerten, Zeitraum erp_monate, Ausreißer
    erp_ausreisser): {(profil, werkstoff): Gruppe}. Rohware geht vor; nur mit Oberfläche gekauft: diese Gruppe.
    Nur die zugeordneten Artikel (grün). Leer ohne Käufe. Ändert keine Preise (Patrick 30.10.2026)."""
    from . import erp_preise
    try:
        kaeufe = erp_preise.gespeicherte(db)
    except Exception:           # noqa: BLE001  (Datei ohne ERP-Tabellen)
        return {}
    if not kaeufe:
        return {}
    k = db.kontext()
    art = erp_preise.artikel(kaeufe, erp_preise.zuordnungen(db), k, erp_preise.nummern_von(db))
    monate = _n(db.einstellung("erp_monate")) or 12
    grenze = _n(db.einstellung("erp_ausreisser")) or 0.25
    out = {}
    for g in erp_preise.auswerten(kaeufe, art, k, db.tabellen(), heute=heute, monate=int(monate), grenze=grenze):
        schl = (g["profil_id"], g["werkstoff_id"])
        if schl not in out or (out[schl].get("oberflaeche") and not g["oberflaeche"]):
            out[schl] = g
    return out


def _zeile_von(db, tabelle, feld, wert):
    for z in db.zeilen(tabelle):
        if z.get(feld) == wert:
            return z
    return None


# ------------------------------------------------------------------ Schreiben
def duplizieren(db, profil_id, neue_id, **aenderungen):
    """Profil kopieren (z. B. andere Wandstärke): neue Zeile mit neuer Profil-ID und geänderten Werten. Preise und
    Lieferlängen werden nicht mitkopiert (sie gelten für die alte Abmessung). Ergebnis: neue Zeilen-id."""
    alt = _zeile_von(db, "profile", "profil_id", profil_id)
    if alt is None:
        raise ValueError(f"Profil '{profil_id}' gibt es nicht.")
    if _leer(neue_id) or _zeile_von(db, "profile", "profil_id", neue_id) is not None:
        raise ValueError(f"Profil-ID '{neue_id}' ist leer oder gibt es schon.")
    werte = {k: v for k, v in alt.items() if k not in ("id", "uid", ARCHIV)}
    werte.update(aenderungen, profil_id=neue_id)
    return db.neu("profile", werte)


def werkstoff_duplizieren(db, werkstoff_id, neue_id, **aenderungen):
    alt = _zeile_von(db, "werkstoffe", "werkstoff_id", werkstoff_id)
    if alt is None:
        raise ValueError(f"Werkstoff '{werkstoff_id}' gibt es nicht.")
    if _leer(neue_id) or _zeile_von(db, "werkstoffe", "werkstoff_id", neue_id) is not None:
        raise ValueError(f"Werkstoff-ID '{neue_id}' ist leer oder gibt es schon.")
    werte = {k: v for k, v in alt.items() if k not in ("id", "uid", ARCHIV)}
    werte.update(aenderungen, werkstoff_id=neue_id)
    return db.neu("werkstoffe", werte)


def archivieren(db, tabelle, schluessel_wert, an=True):
    """Profil oder Werkstoff archivieren (bzw. zurückholen): nicht mehr in neuen Auswahllisten, bestehende Angebote
    rechnen unverändert weiter. Nichts wird gelöscht."""
    feld = {"profile": "profil_id", "werkstoffe": "werkstoff_id"}[tabelle]
    z = _zeile_von(db, tabelle, feld, schluessel_wert)
    if z is None:
        raise ValueError(f"'{schluessel_wert}' gibt es nicht.")
    db.aendern(tabelle, z["id"], ARCHIV, JA if an else None)


# Felder, die Mehrfach ändern setzen darf (Tabelle, Feld): kaufmännische Werte; Güte, Dichte und Maße nie
MEHRFACH_FELDER = {("preise", "lieferant"), ("preise", "gueltig_ab"), ("preise", "mindest_stangen"),
                   ("preise", "lieferlaenge"), ("preise", "bemerkung"), ("profile", "bemerkung"),
                   ("profile", "endbeschnitt"), ("profile", "greiferrest"), ("profile", "laengenvergleich")}


def mehrfach_aendern(db, zeilen, tabelle, feld, wert, preis_faktor=None):
    """Mehrere Materialien auf einmal ändern. zeilen = Varianten (profil_id, werkstoff_id). tabelle/feld aus
    MEHRFACH_FELDER; preis_faktor (z. B. 1.03 = +3 %) ändert statt dessen den Preis der vorhandenen Zeilen in
    'Preise'. Fehlt die Preise-Zeile, wird sie nicht angelegt. Ergebnis: Anzahl geänderter Zeilen."""
    if preis_faktor is None and (tabelle, feld) not in MEHRFACH_FELDER:
        raise ValueError(f"{tabelle}.{feld} lässt sich nicht für mehrere Materialien ändern.")
    n = 0
    if tabelle == "profile":
        ids = {z["profil_id"] for z in zeilen}
        for p in db.zeilen("profile"):
            if p.get("profil_id") in ids:
                db.aendern("profile", p["id"], feld, wert)
                n += 1
        return n
    ziel = {schluessel(z) for z in zeilen}
    for p in db.zeilen("preise"):
        if schluessel(p) not in ziel:
            continue
        if preis_faktor is not None:
            if _n(p.get("preis")):
                db.aendern("preise", p["id"], "preis", round(p["preis"] * preis_faktor, 4))
                n += 1
        else:
            db.aendern("preise", p["id"], feld, wert)
            n += 1
    return n


def lieferant_uebernehmen(db, lz, heute=None):
    """Preis eines Lieferanten (Zeile aus material_lieferanten) als aktiven Preis übernehmen: mit Lieferlänge in
    'Lieferlängen', ohne in 'Preise' (Preis, Basis, Lieferant, Gültig ab, Mindestabnahme). Wie Lieferantenangebote
    und Online-Preise; der Preiswächter meldet danach betroffene offene Angebote, festgeschriebene bleiben."""
    heute = (heute or datetime.date.today()).isoformat()
    werte = dict(profil_id=lz["profil_id"], werkstoff_id=lz["werkstoff_id"], basis=lz.get("basis") or "€/kg",
                 preis=lz.get("preis"), lieferant=lz.get("lieferant"), gueltig_ab=lz.get("gueltig_ab") or heute,
                 mindest_stangen=lz.get("mindest_stangen"))
    if _n(lz.get("preis")) is None:
        raise ValueError("Der Lieferant hat keinen Preis.")
    vorhanden = next((p for p in db.zeilen("preise") if schluessel(p) == schluessel(lz)), None)
    if vorhanden is not None:
        if _n(lz.get("laenge")) and _n(vorhanden.get("lieferlaenge")) not in (None, _n(lz.get("laenge"))):
            return _als_lieferlaenge(db, lz, werte)
        for f in ("basis", "preis", "lieferant", "gueltig_ab", "mindest_stangen"):
            if vorhanden.get(f) != werte[f]:
                db.aendern("preise", vorhanden["id"], f, werte[f])
        if _n(lz.get("laenge")) and not _n(vorhanden.get("lieferlaenge")):
            db.aendern("preise", vorhanden["id"], "lieferlaenge", int(lz["laenge"]))
        return "Preise"
    if _n(lz.get("laenge")):
        werte["lieferlaenge"] = int(lz["laenge"])
    db.neu("preise", werte)
    return "Preise"


def _als_lieferlaenge(db, lz, werte):
    lg = int(_n(lz["laenge"]))
    z = next((r for r in db.zeilen("lieferlaengen") if schluessel(r) == schluessel(lz) and _n(r.get("laenge")) == lg),
             None)
    neu = dict(profil_id=werte["profil_id"], werkstoff_id=werte["werkstoff_id"], laenge=lg, basis=werte["basis"],
               preis=werte["preis"], gueltig_ab=werte["gueltig_ab"], lieferant=werte["lieferant"],
               mindest_stangen=werte["mindest_stangen"])
    if z is None:
        db.neu("lieferlaengen", neu)
    else:
        for f, v in neu.items():
            if z.get(f) != v:
                db.aendern("lieferlaengen", z["id"], f, v)
    return "Lieferlängen"


# ------------------------------------------------------------------ Export / Import
EXPORT = (("profil_id", "Profil-ID"), ("form", "Profilform"), ("a", "A [mm]"), ("b", "B [mm]"), ("wand", "Wand [mm]"),
          ("werkstoff_id", "Werkstoff-ID"), ("kategorie", "Materialgruppe"), ("werkstoff_nr", "Werkstoff-Nr."),
          ("dichte", "Dichte [kg/dm³]"), ("kgm", "Gewicht [kg/m]"), ("preis_kg", "Preis [€/kg]"),
          ("preis_m", "Preis [€/m]"), ("quelle", "Preisquelle"), ("stand", "Preisstand"),
          ("lieferant", "Lieferant"), ("handelslaengen", "Handelslängen [mm]"), ("mindest", "Mindestabnahme"),
          ("nutzung", "Angebote"), ("erp_schnitt", "ERP-Einkauf Ø [€/m]"), ("erp_letzter", "ERP letzter Kauf [€/m]"),
          ("erp_datum", "ERP letzter Kauf am"), ("erp_abw", "ERP Abweichung [%]"),
          ("erp_lieferzeit", "Lieferzeit Ø [Tage]"))


def _zelle(v, stellen=None):
    if isinstance(v, list):
        return " | ".join(str(x) for x in v)
    if isinstance(v, bool):
        return "ja" if v else ""
    if isinstance(v, float):
        return f"{v:.{stellen if stellen is not None else 4}f}".rstrip("0").rstrip(".").replace(".", ",")
    return "" if v is None else masstext.text(str(v))      # Abmessungen kompakt (masstext)


def csv_export(zeilen):
    """Materialliste als CSV-Text (Semikolon, deutsche Zahlen, für Excel)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow([t for _, t in EXPORT])
    for z in zeilen:
        w.writerow([_zelle(z.get(f)) for f, _ in EXPORT])
    return buf.getvalue()


def _xml(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def xlsx_export(zeilen, pfad, kopf=None, felder=None):
    """Materialliste als Excel-Datei (.xlsx, ein Blatt, ohne Zusatzpaket): Zahlen als Zahl, Rest als Text."""
    import zipfile
    felder = felder or [f for f, _ in EXPORT]
    kopf = kopf or [dict(EXPORT).get(f, f) for f in felder]

    def zelle(v):
        if isinstance(v, bool) or v is None:
            v = "" if v is None else ("ja" if v else "nein")
        if isinstance(v, (int, float)):
            return f"<c><v>{v}</v></c>"
        return f'<c t="inlineStr"><is><t xml:space="preserve">{_xml(masstext.text(str(v)))}</t></is></c>'
    reihen = [kopf] + [[z.get(f) for f in felder] for z in zeilen]
    blatt = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats'
             '.org/spreadsheetml/2006/main"><sheetData>' + "".join(
                 f'<row r="{i + 1}">' + "".join(zelle(v) for v in r) + "</row>" for i, r in enumerate(reihen))
             + "</sheetData></worksheet>")
    ns = "http://schemas.openxmlformats.org"
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", f'<?xml version="1.0" encoding="UTF-8"?><Types xmlns="{ns}/package/2006/'
                    f'content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.'
                    'relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName='
                    '"/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.'
                    'main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.'
                    'openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        zf.writestr("_rels/.rels", f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{ns}/package/2006/'
                    f'relationships"><Relationship Id="rId1" Type="{ns}/officeDocument/2006/relationships/'
                    'officeDocument" Target="xl/workbook.xml"/></Relationships>')
        zf.writestr("xl/workbook.xml", f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{ns}/spreadsheetml/'
                    f'2006/main" xmlns:r="{ns}/officeDocument/2006/relationships"><sheets><sheet name="Material" '
                    'sheetId="1" r:id="rId1"/></sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels", f'<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="{ns}/'
                    f'package/2006/relationships"><Relationship Id="rId1" Type="{ns}/officeDocument/2006/'
                    'relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        zf.writestr("xl/worksheets/sheet1.xml", blatt)
    return pfad


IMPORT_SPALTEN = {"profil-id": "profil_id", "profil": "profil_id", "werkstoff-id": "werkstoff_id",
                  "werkstoff": "werkstoff_id", "lieferant": "lieferant", "preis": "preis", "preis [€/kg]": "preis_kg",
                  "preis [€/m]": "preis_m", "€/kg": "preis_kg", "€/m": "preis_m", "€/stange": "preis_stange",
                  "lieferlänge": "laenge", "lieferlaenge": "laenge", "länge": "laenge", "laenge": "laenge",
                  "artikelnummer": "artikelnr", "artikelnr": "artikelnr", "artikel-nr.": "artikelnr",
                  "bestellnummer": "artikelnr", "gültig ab": "gueltig_ab", "gueltig ab": "gueltig_ab",
                  "gültig bis": "gueltig_bis", "gueltig bis": "gueltig_bis", "lieferzeit": "lieferzeit",
                  "lieferzeit [tage]": "lieferzeit", "mindestabnahme": "mindest_stangen", "basis": "basis"}


def _zahl_text(t):
    t = str(t or "").strip().replace("€", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _datum_text(t):
    t = str(t or "").strip()
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", t)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    if re.fullmatch(r"\d{5}", t):          # Excel-Tageszahl (aus .xlsx)
        return (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(t))).isoformat()
    return t[:10] if _datum(t) else None


def preisliste_lesen(text, lieferant=None, k=None):
    """Preisliste eines Lieferanten (CSV mit ; oder , oder Tab; Excel als CSV gespeichert bzw. aus xlsx gelesen) in
    Zeilen für material_lieferanten. Ergebnis dict(zeilen, fehler=[(Zeile, Grund)]). Unbekannte Profile oder
    Werkstoffe werden gemeldet, nie angelegt."""
    probe = str(text or "")[:2000]
    trenn = max((";", ",", "\t"), key=probe.count)
    r = csv.reader(io.StringIO(str(text or "")), delimiter=trenn)
    kopf = None
    zeilen, fehler = [], []
    for nr, roh in enumerate(r, 1):
        if not any(c.strip() for c in roh):
            continue
        if kopf is None:
            kopf = [IMPORT_SPALTEN.get(c.strip().lower()) for c in roh]
            if "profil_id" not in kopf or "werkstoff_id" not in kopf:
                return dict(zeilen=[], fehler=[(nr, "Kopfzeile braucht die Spalten Profil-ID und Werkstoff-ID")])
            continue
        d = {f: (roh[i].strip() if i < len(roh) else "") for i, f in enumerate(kopf) if f}
        z = dict(profil_id=d.get("profil_id"), werkstoff_id=d.get("werkstoff_id"),
                 lieferant=d.get("lieferant") or lieferant, artikelnr=d.get("artikelnr") or None,
                 laenge=_zahl_text(d.get("laenge")), gueltig_ab=_datum_text(d.get("gueltig_ab")),
                 gueltig_bis=_datum_text(d.get("gueltig_bis")), lieferzeit=_zahl_text(d.get("lieferzeit")),
                 mindest_stangen=_zahl_text(d.get("mindest_stangen")))
        for f, basis in (("preis_kg", "€/kg"), ("preis_m", "€/m"), ("preis_stange", "€/Stange")):
            if _zahl_text(d.get(f)) is not None:
                z["basis"], z["preis"] = basis, _zahl_text(d.get(f))
                break
        else:
            if _zahl_text(d.get("preis")) is not None:
                z["basis"] = d.get("basis") if d.get("basis") in ("€/kg", "€/m", "€/Stange") else "€/kg"
                z["preis"] = _zahl_text(d.get("preis"))
        if not z["profil_id"] or not z["werkstoff_id"]:
            fehler.append((nr, "Profil-ID oder Werkstoff-ID fehlt"))
            continue
        if not z.get("lieferant"):
            fehler.append((nr, "Lieferant fehlt"))
            continue
        if z.get("preis") is None or z["preis"] <= 0:
            fehler.append((nr, "Preis fehlt"))
            continue
        if k is not None and z["profil_id"] not in k.profile:     # andere Schreibweise ('QR 40 x 40 x 3') zuordnen
            z["profil_id"] = masstext.finde(z["profil_id"], k.profile) or z["profil_id"]
        if k is not None and z["profil_id"] not in k.profile:
            fehler.append((nr, f"Profil {z['profil_id']} fehlt in den Stammdaten"))
            continue
        if k is not None and z["werkstoff_id"] not in k.werkstoffe:
            fehler.append((nr, f"Werkstoff {z['werkstoff_id']} fehlt in den Stammdaten"))
            continue
        if z.get("mindest_stangen") is not None:
            z["mindest_stangen"] = int(z["mindest_stangen"])
        if z.get("lieferzeit") is not None:
            z["lieferzeit"] = int(z["lieferzeit"])
        if z.get("laenge") is not None:
            z["laenge"] = int(z["laenge"])
        zeilen.append(z)
    return dict(zeilen=zeilen, fehler=fehler)


def preisliste_importieren(db, zeilen):
    """Zeilen aus preisliste_lesen in material_lieferanten schreiben (vorher Datensicherung): gleiche Kombination
    Profil + Werkstoff + Lieferant + Länge wird geändert, sonst neu. Aktive Preise (Preise) bleiben unverändert;
    übernehmen geht danach je Zeile mit lieferant_uebernehmen. Ergebnis dict(neu, geaendert)."""
    try:
        db.sicherung(zusatz="vor_Preisliste")
    except Exception:           # noqa: BLE001  (Tests ohne Sicherungsordner)
        from . import protokoll
        protokoll.warnung("Materialplattform: abgefangen, ohne diese Angabe weiter")
    vorhanden = {(z.get("profil_id"), z.get("werkstoff_id"), z.get("lieferant"), _n(z.get("laenge"))): z
                 for z in db.zeilen(LIEFERANTEN_TABELLE)}
    neu = geaendert = 0
    for z in zeilen:
        schl = (z["profil_id"], z["werkstoff_id"], z["lieferant"], _n(z.get("laenge")))
        alt = vorhanden.get(schl)
        werte = {f: v for f, v in z.items() if v is not None}
        if alt is None:
            db.neu(LIEFERANTEN_TABELLE, werte)
            neu += 1
        else:
            for f, v in werte.items():
                if alt.get(f) != v:
                    db.aendern(LIEFERANTEN_TABELLE, alt["id"], f, v)
            geaendert += 1
    return dict(neu=neu, geaendert=geaendert)


def xlsx_als_csv(pfad):
    """Erstes Blatt einer Excel-Datei (.xlsx) als CSV-Text mit Semikolon (ohne Fremdpaket, stueckliste.xlsx_zeilen);
    Dezimalpunkt wird Komma. None, wenn die Datei nicht lesbar ist."""
    import zipfile
    from xml.etree import ElementTree

    from .stueckliste import xlsx_zeilen
    try:
        with open(pfad, "rb") as f:
            zeilen = xlsx_zeilen(f.read())
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
        return None
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    for z in zeilen:
        w.writerow([v.replace(".", ",") if re.fullmatch(r"-?\d+\.\d+", v) else v for v in z])
    return buf.getvalue()


# ------------------------------------------------------------------ Historie
def historie(db, profil_id, werkstoff_id):
    """Preisstände (preisverlauf) und Änderungen der Stammdatenzeilen (Änderungsverlauf) des Materials, neueste
    zuerst: [dict(zeit, art, text)]."""
    out = []
    from . import preisverlauf
    try:
        for z in reversed(preisverlauf.eintraege(db.con, profil_id=profil_id, werkstoff_id=werkstoff_id)):
            out.append(dict(zeit=str(z.get("datum") or z.get("zeit") or "")[:10], art=z.get("art") or "Preis",
                            text=f"{_zelle(_n(z.get('preis')), 2)} {z.get('basis') or ''}"
                                 + (f" · {int(z['laenge'])} mm" if _n(z.get('laenge')) else "")
                                 + (f" · {z['lieferant']}" if z.get("lieferant") else "")))
    except Exception:           # noqa: BLE001
        from . import protokoll
        protokoll.warnung("Materialplattform: abgefangen, ohne diese Angabe weiter")
    try:
        for r in db.con.execute("SELECT zeit, wer, tabelle, feld, alt, neu, bezug FROM teilen_verlauf WHERE tabelle IN "
                                "('profile', 'werkstoffe', 'preise', 'lieferlaengen') ORDER BY zeit DESC LIMIT 2000"):
            bezug = str(r[6] or "")
            if profil_id in bezug or werkstoff_id in bezug:
                out.append(dict(zeit=str(r[0] or "")[:16], art=f"{r[2]} geändert ({r[1] or '?'})",
                                text=f"{r[3]}: {r[4] or '–'} → {r[5] or '–'}"))
    except Exception:           # noqa: BLE001  (ohne Abgleich gibt es keinen Änderungsverlauf)
        from . import protokoll
        protokoll.warnung("Materialplattform: abgefangen, ohne diese Angabe weiter")
    for p in preis_punkte(db, profil_id, werkstoff_id)["erp"]:
        out.append(dict(zeit=p["datum"].isoformat(), art="ERP-Einkauf" + (f" {p['ober']}" if p["ober"] else ""),
                        text=f"{_zelle(p['preis'], 2)} €/m · {_zelle(p['menge'], 0)} m"
                             + (f" · {p['artikelnr']}" if p.get("artikelnr") else "")
                             + ("" if p["zaehlt"] else " · zählt nicht (Ausreißer/alt)")))
    for z in db.zeilen(LIEFERANTEN_TABELLE):
        if schluessel(z) == (profil_id, werkstoff_id):
            out.append(dict(zeit=str(z.get("gueltig_ab") or "")[:10], art=f"Lieferantenpreis {z.get('lieferant') or ''}",
                            text=f"{_zelle(_n(z.get('preis')), 2)} {z.get('basis') or ''}"
                                 + (f" · {int(z['laenge'])} mm" if _n(z.get("laenge")) else "")
                                 + (f" · gültig bis {_zelle(z.get('gueltig_bis'))}" if z.get("gueltig_bis") else "")))
    out.sort(key=lambda z: z["zeit"], reverse=True)
    return out


def preis_punkte(db, profil_id, werkstoff_id, gruppe=None):
    """Preishistorie eines Materials in €/m für die Kurve: dict(stamm=[(date, €/m)] Preisstände der Stammdaten
    (Preise/Lieferlängen, umgerechnet mit kg/m), erp=[dict(datum, preis, menge, zaehlt, ober, artikelnr)] Käufe aus
    der ERP-CSV, lieferanten=[dict(datum, preis, lieferant)], schnitt = ERP-Ø €/m oder None)."""
    from . import preisverlauf
    k = db.kontext()
    kgm = kg_je_m(k.profile.get(profil_id) or {}, k.werkstoffe.get(werkstoff_id) or {})
    stamm = {}
    try:
        for e in preisverlauf.eintraege(db.con, profil_id=profil_id, werkstoff_id=werkstoff_id):
            d, pm = _datum(e.get("datum")), je_meter(e.get("basis"), e.get("preis"), kgm, e.get("laenge") or 6000)
            if d is not None and pm is not None:
                stamm[d] = pm
    except Exception:           # noqa: BLE001
        from . import protokoll
        protokoll.warnung("Materialplattform: abgefangen, ohne diese Angabe weiter")
    g = gruppe if gruppe is not None else erp_gruppen(db).get((profil_id, werkstoff_id))
    erp = [dict(datum=x["datum"], preis=x["preis"], menge=x["menge"], zaehlt=bool(x.get("gerechnet")),
                ober=(g or {}).get("oberflaeche") or "", artikelnr=x.get("artikelnr") or "")
           for x in (g or {}).get("kaeufe") or ()]
    lief = []
    for z in db.zeilen(LIEFERANTEN_TABELLE):
        if schluessel(z) == (profil_id, werkstoff_id):
            d = _datum(z.get("gueltig_ab"))
            pm = je_meter(z.get("basis"), z.get("preis"), kgm, z.get("laenge") or 6000)
            if d is not None and pm is not None:
                lief.append(dict(datum=d, preis=pm, lieferant=z.get("lieferant") or "", gueltig=gueltig(z)))
    return dict(stamm=sorted(stamm.items()), erp=erp, lieferanten=sorted(lief, key=lambda x: x["datum"]),
                schnitt=(g or {}).get("durchschnitt"))
