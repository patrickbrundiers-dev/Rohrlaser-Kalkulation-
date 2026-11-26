"""Lernende Zeitvorschläge für Schweißbaugruppen (Editor 2.0, Patrick 19.11.2026). Ohne Qt.

Jede Zeit von Hand an einer Schweißbaugruppe ist eine Kalkulationsentscheidung. Beim Speichern des Fensters wird sie
mit den Merkmalen der Baugruppe in die Tabelle 'bg_zeiten' geschrieben: eine Zeile je Angebot und Baugruppe
(Schlüssel angebot + bg_id). Dieselbe Entscheidung wird also nie doppelt gezählt; wird sie geändert, ersetzt der neue
Stand den alten (der alte bleibt im Protokoll der Baugruppe, bg_vorgabe.protokoll). Wird die Zeit zurückgesetzt,
bleibt die Zeile mit Status ZURUECK stehen und zählt nicht mehr. Die Tabelle geht wie Stammdaten über den
gemeinsamen Ordner (teilen.GETEILT).

Für eine neue Baugruppe sucht vorschlag() vergleichbare Entscheidungen:
  getrennt        nur dieselbe Baugruppenart: gleiche Werkstoffgruppe und gleiches Schweißverfahren (wenn beides
                  bekannt ist) und dieselbe Art der Vorgabe-Grundlage (mit automatischer Zeit)
  Ähnlichkeit     Nahtlänge, Anzahl Einzelteile, Gewicht, Anzahl Nähte, größte Wanddicke, verschiedene Teile:
                  je Merkmal kleiner ÷ größer (1 = gleich), gewichtet gemittelt (GEWICHTE). Vergleichbar ab AEHNLICH_AB.
  Gewicht         Ähnlichkeit² × Alter (halbiert alle HALBWERT_TAGE)
  Ausreißer       Verhältnis Hand ÷ automatisch weiter als AUSREISSER × MAD vom Median: wird genannt, zählt nicht
  Vorschlag       automatische Zeit × gewichtetes Mittel der Verhältnisse; ab VORSCHLAG_AB Datensätzen
  Prüfung         ab PRUEF_AB Datensätzen wird jede Entscheidung einmal weggelassen und aus den anderen vorhergesagt
                  (Leave-one-out). Daneben eine gewichtete Ausgleichsgerade Hand = a + b × automatisch; sie wird nur
                  genommen, wenn ihr Fehler in dieser Prüfung um mindestens BESSER_UM kleiner ist.
Ein Vorschlag ändert nie von allein etwas: er wird angezeigt und erst mit dem Knopf übernommen.

Zeiten von Hand sind Kalkulationsvorgaben, keine gemessenen Ist-Zeiten. Gemessene Zeiten kommen aus der
Nachkalkulation (bg_erfahrung) und werden getrennt gezeigt.
"""
import datetime
import json
import math

from .stammdaten import Feld, Tabelle
from .zahlen import jetzt_text as _jetzt  # Audit 26.11.2026 R-01: gemeinsame Hilfsfunktion

TABELLE = "bg_zeiten"
FREI, AUS, ZURUECK = "", "aus", "zurück"        # Status: freigegeben | nicht fürs Lernen | Zeit zurückgesetzt
BG_ZEITEN = Tabelle(
    TABELLE, "Schweißbaugruppen: Zeiten von Hand",
    (Feld("angebot", "Angebot", breite=90),
     Feld("bg_id", "Baugruppe (Kennung)", breite=90),
     Feld("titel", "Baugruppe", breite=200),
     Feld("art", "Art", breite=120),                      # Baugruppenart: Werkstoffgruppe · Verfahren
     Feld("merkmale", "Merkmale", breite=200),            # JSON
     Feld("anzahl", "Stück", "zahl", breite=50),
     Feld("auto_min", "Automatisch [min]", "zahl", breite=80),    # je Baugruppe, mit Rüstanteil
     Feld("hand_min", "Von Hand [min]", "zahl", breite=80),       # je Baugruppe, mit Rüstanteil
     Feld("quelle", "Vorgabe", breite=80),                # Gesamtzeit | Stückzeit | Bereiche
     Feld("vorschlag_min", "Lernvorschlag [min]", "zahl", breite=80),
     Feld("grund", "Grund", breite=160),
     Feld("version", "Version", "ganz", breite=50),
     Feld("status", "Status", breite=60),
     Feld("kuerzel", "Wer", breite=50),
     Feld("geaendert", "Geändert", breite=130)),
    ("angebot", "bg_id"),
    "Zeiten von Hand an Schweißbaugruppen mit ihren Merkmalen (Lernvorschläge, bg_zeitlernen.py).")

GEWICHTE = dict(naht_m=0.30, teile_n=0.20, gewicht_kg=0.20, naht_n=0.12, dicke_mm=0.10, verschiedene=0.08)
AEHNLICH_AB = 0.60
HALBWERT_TAGE = 730.0
AUSREISSER = 3.0
MAD_MIN = 0.04              # Streuung der Verhältnisse mindestens (sonst wäre bei 3 gleichen alles andere Ausreißer)
VORSCHLAG_AB = 3
PRUEF_AB = 8
BESSER_UM = 0.10
WEIT_AB = 0.50              # Abweichung über 50 % von der automatischen Zeit: „besonders hohe Korrektur“


def _zahl(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


# ------------------------------------------------------------------ Merkmale
def merkmale(bg, positionen=None, k=None, erg=None):
    """Merkmale einer Baugruppe für Vergleich und Protokoll: teile_n, verschiedene, arten {Art: Anzahl}, profile,
    werkstoff, gruppe (Werkstoffgruppe), dicke_mm (größte Wanddicke), gewicht_kg, naht_m, naht_n, verfahren,
    vorlage, bereiche {Bereich: automatische min}. Unbekanntes fehlt (None)."""
    from . import baugruppe, bg_mengen
    from .angebot import ist_zukaufteil
    out = dict(teile_n=None, verschiedene=None, arten={}, profile=[], werkstoff=None, gruppe=None, dicke_mm=None,
               gewicht_kg=None, naht_m=None, naht_n=None, verfahren=None, vorlage=(bg or {}).get("vorlage") or "",
               bereiche={})
    if not bg:
        return out
    naehte = [n for n in bg.get("naehte") or () if isinstance(n, dict)]
    out["naht_n"] = sum(int(n["anzahl"]) if _zahl(n.get("anzahl")) and n["anzahl"] > 0 else 1 for n in naehte)
    verf = {}
    for n in naehte:
        if n.get("verfahren"):
            verf[n["verfahren"]] = verf.get(n["verfahren"], 0.0) + (baugruppe.naht_meter(n) or 0.0)
    if verf:
        out["verfahren"] = max(sorted(verf), key=lambda v: verf[v])
    if positionen is not None:
        try:
            m = bg_mengen.mengen(bg, positionen, k)
        except Exception:       # noqa: BLE001 – Merkmale sind Beiwerk
            m = None
        if m:
            out.update(teile_n=m["teile"], naht_m=m["naht"],
                       gewicht_kg=round(m["gewicht"], 2) if not m["fehlt"].get("gewicht") else None)
        ws, profile, dicke, arten, n_pos = {}, set(), None, {}, 0
        for i in baugruppe.teile(positionen, bg.get("id")):
            p = positionen[i]
            n_pos += 1
            pr = (getattr(k, "profile", None) or {}).get(p.get("profil_id")) if k is not None else None
            if ist_zukaufteil(p):
                art = "Zukaufteil"
            elif p.get("technik") and not p.get("profil_id"):
                art = "Blechteil"
            else:
                art = "Rohrteil"
            arten[art] = arten.get(art, 0) + 1
            if p.get("profil_id"):
                profile.add(str(p["profil_id"]))
            if p.get("werkstoff_id"):
                ws[p["werkstoff_id"]] = ws.get(p["werkstoff_id"], 0) + 1
            w = (pr or {}).get("wand")
            if _zahl(w) and (dicke is None or w > dicke):
                dicke = w
        out.update(verschiedene=n_pos, arten=arten, profile=sorted(profile)[:12], dicke_mm=dicke)
        if ws:
            out["werkstoff"] = max(sorted(ws), key=lambda w: ws[w])
            out["gruppe"] = _gruppe(k, out["werkstoff"])
    if out["naht_m"] is None:
        out["naht_m"] = round(sum(baugruppe.naht_meter(n) or 0.0 for n in naehte), 4)
    z = (erg or {}).get("zeiten") or {}
    out["bereiche"] = {x["bereich"]: round(x["auto_stueck"], 2) for x in z.get("bereiche") or () if x["auto_stueck"]}
    return out


def _gruppe(k, werkstoff):
    """Werkstoffgruppe (Stahl, Edelstahl, Aluminium …) aus den Stammdaten, sonst aus dem Namen geraten, sonst None."""
    for quelle in ("werkstoffe", "werkstoff"):
        w = (getattr(k, quelle, None) or {}).get(werkstoff) if k is not None else None
        if isinstance(w, dict):
            for feld in ("gruppe", "materialgruppe", "werkstoffgruppe"):
                if w.get(feld):
                    return str(w[feld])
    t = str(werkstoff or "").lower()
    if any(x in t for x in ("1.43", "1.44", "1.45", "edelstahl", "v2a", "v4a", "inox")):
        return "Edelstahl"
    if any(x in t for x in ("alu", "en aw", "almg")):
        return "Aluminium"
    if any(x in t for x in ("s235", "s355", "s275", "e235", "e355", "dc0", "stahl", "st37", "st52")):
        return "Stahl"
    return None


def art_text(m):
    """Baugruppenart für Trennung und Anzeige: 'Stahl · MAG'."""
    return " · ".join(str(x) for x in ((m or {}).get("gruppe"), (m or {}).get("verfahren")) if x) or "ohne Angabe"


# ------------------------------------------------------------------ Speichern
def _lesen(text):
    try:
        w = json.loads(text) if text else {}
    except (TypeError, ValueError):
        w = {}
    return w if isinstance(w, dict) else {}


def zeile(db, angebot, bg_id):
    r = db.con.execute("SELECT * FROM bg_zeiten WHERE COALESCE(angebot, '')=? AND COALESCE(bg_id, '')=?",
                       (str(angebot or ""), str(bg_id or ""))).fetchone()
    return dict(r) if r is not None else None


def merken(db, angebot, titel, bg, z, m, kuerzel=""):
    """Stand der Zeit von Hand einer Baugruppe festhalten (beim Speichern des Fensters bzw. Angebots). Eine Zeile je
    Angebot und Baugruppe; ohne Zeit von Hand wird eine vorhandene Zeile auf ZURUECK gesetzt. Ergebnis: 'neu',
    'geändert', 'zurück', None (nichts zu tun). Scheitert nie laut."""
    from . import bg_vorgabe
    if db is None or getattr(db, "nur_lesen", None) or not bg or not bg.get("id") or not angebot:
        return None
    try:
        alt = zeile(db, angebot, bg["id"])
        hand = bool(z and z.get("hand")) and bg_vorgabe.hat_vorgabe(bg)
        if not hand:
            if alt is None or alt.get("status") == ZURUECK:
                return None
            with db.con:
                db.con.execute("UPDATE bg_zeiten SET status=?, geaendert=?, kuerzel=? WHERE id=?",
                               (ZURUECK, _jetzt(), kuerzel, alt["id"]))
            _leeren()
            return "zurück"
        v = bg_vorgabe.vorgabe(bg)
        quelle = "Gesamtzeit" if z.get("hand_gesamt") else "Stückzeit" if z.get("hand_stueck") else \
            "Bereiche" if z.get("hand_bereiche") else "Rüstzeit"
        werte = dict(angebot=str(angebot), bg_id=str(bg["id"]), titel=titel or "", art=art_text(m),
                     merkmale=json.dumps(m or {}, ensure_ascii=False, sort_keys=True), anzahl=z.get("anzahl") or 0,
                     auto_min=round(z.get("auto_je_bg_min") or 0.0, 3), hand_min=round(z.get("je_bg_min") or 0.0, 3),
                     quelle=quelle, vorschlag_min=(v["vorschlag"] or {}).get("min"), grund=v["grund"],
                     version=bg_vorgabe.version(bg),
                     # gesperrt bleibt gesperrt, bis es in der Auswertung wieder freigegeben wird
                     status=AUS if not v["frei"] or (alt or {}).get("status") == AUS else FREI)
        if alt is not None and all(_gleich(alt.get(n), w) for n, w in werte.items()):
            return None                 # nichts geändert: kein neuer Zeitstempel, nichts doppelt
        werte.update(kuerzel=kuerzel or (alt or {}).get("kuerzel") or "", geaendert=_jetzt())
        with db.con:
            if alt is None:
                namen = ", ".join(f'"{n}"' for n in werte)
                db.con.execute(f"INSERT INTO bg_zeiten ({namen}) VALUES ({', '.join('?' * len(werte))})",
                               list(werte.values()))
            else:
                db.con.execute("UPDATE bg_zeiten SET " + ", ".join(f'"{n}"=?' for n in werte) + " WHERE id=?",
                               [*werte.values(), alt["id"]])
        _leeren()
        return "neu" if alt is None else "geändert"
    except Exception:           # noqa: BLE001 – Lernen darf das Speichern nie verhindern
        return None


def _gleich(a, b):
    if _zahl(a) and _zahl(b):
        return abs(a - b) < 1e-6
    return (a if a is not None else "") == (b if b is not None else "")


def status_setzen(db, zeilen_id, status):
    """Datensatz fürs Lernen sperren (AUS) oder wieder freigeben (FREI)."""
    with db.con:
        db.con.execute("UPDATE bg_zeiten SET status=?, geaendert=? WHERE id=?", (status, _jetzt(), zeilen_id))
    _leeren()


_CACHE = {}


def _leeren():
    _CACHE.clear()


def faelle(db, alle=False):
    """Datensätze als dicts mit gelesenen Merkmalen ('m') und Verhältnis ('faktor' = Hand ÷ automatisch, None ohne
    automatische Zeit). Ohne alle: nur freigegebene mit Zeit von Hand."""
    if db is None:
        return []
    try:
        roh = [dict(r) for r in db.con.execute("SELECT * FROM bg_zeiten ORDER BY id")]
    except Exception:           # noqa: BLE001 – Tabelle fehlt (alte Datei, nur lesen)
        return []
    out = []
    for r in roh:
        if not alle and (r.get("status") or "") != FREI:
            continue
        r["m"] = _lesen(r.get("merkmale"))
        a, h = r.get("auto_min"), r.get("hand_min")
        r["faktor"] = h / a if _zahl(a) and _zahl(h) and a > 1e-6 else None
        out.append(r)
    return out


# ------------------------------------------------------------------ Ähnlichkeit
def aehnlichkeit(a, b):
    """0..1 zwischen zwei Merkmal-dicts; 0, wenn die Baugruppenart verschieden ist (Werkstoffgruppe bzw. Verfahren,
    soweit bei beiden bekannt). Fehlt ein Merkmal bei einem von beiden, zählt es nicht mit; ohne ein einziges
    gemeinsames Merkmal 0."""
    for n in ("gruppe", "verfahren"):
        if a.get(n) and b.get(n) and a[n] != b[n]:
            return 0.0
    summe = gewicht = 0.0
    for n, g in GEWICHTE.items():
        x, y = a.get(n), b.get(n)
        if not _zahl(x) or not _zahl(y) or x < 0 or y < 0:
            continue
        s = 1.0 if max(x, y) < 1e-9 else min(x, y) / max(x, y)
        summe += s * g
        gewicht += g
    if gewicht < 0.3:           # zu wenig gemeinsame Merkmale für einen Vergleich
        return 0.0
    return summe / gewicht


def alter_gewicht(geaendert, heute=None):
    """Ältere Entscheidungen zählen weniger: halbiert alle HALBWERT_TAGE; ohne lesbares Datum 0,5."""
    try:
        d = datetime.date.fromisoformat(str(geaendert)[:10])
    except ValueError:
        return 0.5
    tage = max(0, ((heute or datetime.date.today()) - d).days)
    return 0.5 ** (tage / HALBWERT_TAGE)


def _median(werte):
    w = sorted(werte)
    n = len(w)
    return w[n // 2] if n % 2 else (w[n // 2 - 1] + w[n // 2]) / 2


def ausreisser(faktoren):
    """Indizes der Ausreißer: weiter als AUSREISSER × 1,4826 × MAD vom Median (MAD mindestens MAD_MIN)."""
    if len(faktoren) < 4:
        return set()
    med = _median(faktoren)
    mad = max(_median([abs(f - med) for f in faktoren]), MAD_MIN)
    return {i for i, f in enumerate(faktoren) if abs(f - med) > AUSREISSER * 1.4826 * mad}


def _mittel(paare):
    g = sum(w for _, w in paare)
    return sum(f * w for f, w in paare) / g if g > 1e-12 else None


def _gerade(punkte):
    """Gewichtete Ausgleichsgerade y = a + b·x aus [(x, y, w)]; None, wenn sie nicht bestimmbar ist."""
    g = sum(w for _, _, w in punkte)
    if g < 1e-12 or len(punkte) < 3:
        return None
    mx = sum(x * w for x, _, w in punkte) / g
    my = sum(y * w for _, y, w in punkte) / g
    sxx = sum(w * (x - mx) ** 2 for x, _, w in punkte)
    if sxx < 1e-9:
        return None
    b = sum(w * (x - mx) * (y - my) for x, y, w in punkte) / sxx
    return my - b * mx, b


def vergleichbare(db, m, ohne=None, heute=None, daten=None):
    """Vergleichbare freigegebene Entscheidungen zu den Merkmalen m, ähnlichste zuerst: Datensatz + 'aehnlich',
    'gewicht', 'ausreisser'. ohne = (angebot, bg_id) der eigenen Baugruppe (lernt nicht aus sich selbst)."""
    out = []
    for r in (daten if daten is not None else faelle(db)):
        if ohne and (str(r.get("angebot") or ""), str(r.get("bg_id") or "")) == (str(ohne[0] or ""), str(ohne[1] or "")):
            continue
        if r["faktor"] is None or r["faktor"] <= 0:
            continue
        s = aehnlichkeit(m, r["m"])
        if s + 1e-9 < AEHNLICH_AB:
            continue
        out.append(dict(r, aehnlich=s, gewicht=s * s * alter_gewicht(r.get("geaendert"), heute), ausreisser=False))
    for i in ausreisser([r["faktor"] for r in out]):
        out[i]["ausreisser"] = True
    out.sort(key=lambda r: (-r["aehnlich"], str(r.get("angebot")), str(r.get("bg_id"))))
    return out


def _pruefung(gut):
    """Leave-one-out über die vergleichbaren Datensätze: mittlerer Fehler [Anteil] des Mittelwert-Verfahrens und
    der Ausgleichsgerade (None, wenn nicht bestimmbar)."""
    f_mittel, f_gerade = [], []
    for i, r in enumerate(gut):
        rest = gut[:i] + gut[i + 1:]
        m = _mittel([(x["faktor"], x["gewicht"]) for x in rest])
        if m is not None:
            f_mittel.append(abs(r["auto_min"] * m - r["hand_min"]) / r["hand_min"])
        ab = _gerade([(x["auto_min"], x["hand_min"], x["gewicht"]) for x in rest])
        if ab is not None:
            f_gerade.append(abs(ab[0] + ab[1] * r["auto_min"] - r["hand_min"]) / r["hand_min"])
    fm = sum(f_mittel) / len(f_mittel) if f_mittel else None
    fg = sum(f_gerade) / len(f_gerade) if len(f_gerade) == len(gut) and f_gerade else None
    return fm, fg


def vorschlag(db, m, auto_min, ohne=None, heute=None, daten=None):
    """Zeitvorschlag je Baugruppe aus vergleichbaren Entscheidungen oder None (zu wenige, keine automatische Zeit).
    dict(min, faktor, n (gezählt), n_ausreisser, vergleichbare [..], verfahren 'Mittel'|'Gerade', fehler (Anteil aus
    der Prüfung oder None), spanne (min, max der Verhältnisse), text (Erklärung))."""
    from .bg_vorgabe import zeit_text
    if not _zahl(auto_min) or auto_min <= 1e-6:
        return None
    alle = vergleichbare(db, m, ohne, heute, daten)
    gut = [r for r in alle if not r["ausreisser"] and r["hand_min"] > 0]
    if len(gut) < VORSCHLAG_AB:
        return None
    faktor = _mittel([(r["faktor"], r["gewicht"]) for r in gut])
    if faktor is None:
        return None
    minuten, verfahren, fehler = auto_min * faktor, "Mittel", None
    if len(gut) >= PRUEF_AB:
        fm, fg = _pruefung(gut)
        fehler = fm
        ab = _gerade([(r["auto_min"], r["hand_min"], r["gewicht"]) for r in gut])
        lo, hi = min(r["auto_min"] for r in gut), max(r["auto_min"] for r in gut)
        if ab is not None and fg is not None and fm is not None and fg < fm * (1 - BESSER_UM) \
                and lo <= auto_min <= hi and ab[0] + ab[1] * auto_min > 0:       # nur innerhalb der Daten
            minuten, verfahren, fehler = ab[0] + ab[1] * auto_min, "Gerade", fg
            faktor = minuten / auto_min
    n_aus = sum(1 for r in alle if r["ausreisser"])

    def pct(f):
        w = round((f - 1) * 100)
        return ("+" if w >= 0 else "−") + f"{abs(w)} %"
    lo_f, hi_f = min(r["faktor"] for r in gut), max(r["faktor"] for r in gut)
    text = (f"{len(gut)} vergleichbare Baugruppen ({art_text(m)}) wurden von Hand im Mittel {pct(faktor)} gegenüber "
            f"der automatischen Zeit kalkuliert (von {pct(lo_f)} bis {pct(hi_f)}). Automatisch {zeit_text(auto_min)} "
            f"× {f'{faktor:.2f}'.replace('.', ',')} = {zeit_text(minuten)}.")
    if verfahren == "Gerade":
        text += " Gerechnet mit einer Ausgleichsgerade, weil sie in der Prüfung genauer war als das Mittel."
    if fehler is not None:
        text += f" Prüfung (jede Entscheidung einmal weggelassen): mittlerer Fehler ± {fehler * 100:.0f} %."
    if n_aus:
        text += f" {n_aus} Ausreißer nicht gezählt."
    text += " Grundlage sind Zeiten von Hand (Kalkulationsvorgaben), keine gemessenen Ist-Zeiten."
    return dict(min=round(minuten, 1), faktor=faktor, n=len(gut), n_ausreisser=n_aus, vergleichbare=alle,
                verfahren=verfahren, fehler=fehler, spanne=(lo_f, hi_f), text=text)


# ------------------------------------------------------------------ Auswertung
KLASSEN_GEWICHT = ((10.0, "bis 10 kg"), (50.0, "10–50 kg"), (200.0, "50–200 kg"), (None, "über 200 kg"))


def gewicht_klasse(kg):
    if not _zahl(kg):
        return "ohne Gewicht"
    return next(t for grenze, t in KLASSEN_GEWICHT if grenze is None or kg <= grenze)


def _gruppen(zeilen, schluessel):
    g = {}
    for r in zeilen:
        g.setdefault(schluessel(r), []).append(r["faktor"])
    return sorted(((k, len(v), sum(v) / len(v)) for k, v in g.items()), key=lambda x: (-x[1], str(x[0])))


def auswertung(db, daten=None):
    """Kennzahlen über alle Entscheidungen mit automatischer Zeit: dict(n, n_gesperrt, n_zurueck, mittel (mittlerer
    Faktor), median, zeilen (neueste zuerst, mit 'abw_min', 'abw_pct', 'weit'), nach_art / nach_material /
    nach_gewicht [(Titel, n, mittlerer Faktor)], haeufig [(Klasse der Abweichung, n)], hoch (größte Korrekturen),
    verlauf [(Datum, Faktor, laufendes Mittel)])."""
    alle = daten if daten is not None else faelle(db, alle=True)
    zeilen = [dict(r) for r in alle if (r.get("status") or "") != ZURUECK and r["faktor"] is not None]
    for r in zeilen:
        r["abw_min"] = r["hand_min"] - r["auto_min"]
        r["abw_pct"] = (r["faktor"] - 1) * 100
        r["weit"] = abs(r["faktor"] - 1) > WEIT_AB
    frei = [r for r in zeilen if (r.get("status") or "") == FREI]
    f = [r["faktor"] for r in frei]
    klassen = ((-1e9, -20, "über 20 % weniger"), (-20, -5, "5–20 % weniger"), (-5, 5, "± 5 %"),
               (5, 20, "5–20 % mehr"), (20, 50, "20–50 % mehr"), (50, 1e9, "über 50 % mehr"))
    haeufig = [(t, sum(1 for r in frei if lo < r["abw_pct"] <= hi)) for lo, hi, t in klassen]
    zeitlich = sorted(frei, key=lambda r: (str(r.get("geaendert") or ""), r.get("id") or 0))
    verlauf, summe = [], 0.0
    for i, r in enumerate(zeitlich, 1):
        summe += r["faktor"]
        verlauf.append((str(r.get("geaendert") or "")[:10], r["faktor"], summe / i))
    return dict(n=len(frei), n_gesperrt=sum(1 for r in zeilen if r.get("status") == AUS),
                n_zurueck=sum(1 for r in alle if r.get("status") == ZURUECK),
                mittel=sum(f) / len(f) if f else None, median=_median(f) if f else None,
                zeilen=sorted(zeilen, key=lambda r: str(r.get("geaendert") or ""), reverse=True),
                nach_art=_gruppen(frei, lambda r: r.get("art") or "ohne Angabe"),
                nach_material=_gruppen(frei, lambda r: r["m"].get("gruppe") or r["m"].get("werkstoff") or "ohne Angabe"),
                nach_gewicht=_gruppen(frei, lambda r: gewicht_klasse(r["m"].get("gewicht_kg"))),
                haeufig=haeufig, hoch=sorted(frei, key=lambda r: -abs(r["abw_pct"]))[:10], verlauf=verlauf)
