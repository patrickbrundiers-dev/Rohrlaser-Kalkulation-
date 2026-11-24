"""Lernsystem L2: LST-Teile Angeboten und Positionen zuordnen und mit der Kalkulation vergleichen (Plan
„Selbstlernende Kalkulation aus LST-Daten“, Patrick 20.11.2026 „Alles einbauen nach allen Empfehlungen“). Ohne Qt.

Zuordnung je LST-Teil (produktion_lst.teile), in dieser Reihenfolge:
1. von Hand gemerkt (Tabelle lst_zuordnung, über den gemeinsamen Ordner geteilt; „keine“ = nie zuordnen)
2. PPEASE-Nummer (Dateiname, Jobname, Fertigungsauftrag): Angebot mit dieser Nummer oder mit der PPEASE-Nummer in den
   Zusatzdaten (ppease_ablage); darin die Position mit gleicher Artikelnummer, sonst gleichen Merkmalen
3. Artikelnummer: neueste Position mit derselben Artikelnummer in den letzten ZEITRAUM_TAGE Tagen
4. Merkmale: gleiches Profil (Form und Maße), gleicher Werkstoff, Länge ± LAENGE_TOL, Schneidweg ± WEG_TOL in den
   letzten ZEITRAUM_TAGE Tagen; passen mehrere Angebote, gilt die neueste Position als „unsicher“

Vergleich: „Berechnet“ ist die normale Laserzeit der Kalkulation (Laserzeit netto je Teil des gespeicherten Angebots,
nachkalkulation.teile_soll) ohne die Nebenzeit (Ausschieben, Entladen, Messen), die in der TRUMPF-Teilezeit nicht
steckt. Die Einstichzeit bleibt eigener Posten: sie steckt in beiden Zeiten, gelernt wird sie in L4 als eigener
Baustein. Gegenüber steht die gemessene Zeit der Maschine (sonst die TRUMPF-Rechnung) absolut und in %.
Weichen Schneidweg, Einstiche oder Länge der Position von der LST ab, kommt das Teil in die Liste „STEP-Messung
prüfen“ (dann stimmt die Geometrie nicht, nicht die Zeit) und zählt nicht fürs Lernen."""
import datetime
import json

from . import produktion_lst as pl
from . import trumpf_programm as tp
from .stammdaten import Feld, Tabelle

ZEITRAUM_TAGE = 183             # Rückfall ohne PPEASE-Nummer: Angebote der letzten 6 Monate
LAENGE_TOL = 0.5                # mm
WEG_TOL = 0.02                  # Schneidweg ± 2 %
MASS_TOL = 0.3                  # mm Profilmaße
GEOMETRIE_WEG = 0.05            # STEP-Messung prüfen: Schneidweg weicht mehr als 5 % ab
GEOMETRIE_STICHE = 1            # … oder mehr als 1 Einstich
HAND, PPEASE, ARTIKEL, MERKMALE, KEINE = "von Hand", "PPEASE-Nummer", "Artikelnummer", "Merkmale", "keine"

ZUORDNUNG = Tabelle(
    "lst_zuordnung", "LST-Zuordnung",
    (Feld("programm", "Programm", pflicht=True, breite=160),
     Feld("teil_nr", "Teil", "ganz", pflicht=True, breite=50),
     Feld("nummer", "Angebot", breite=110),               # leer = nie zuordnen
     Feld("pos", "Position", "ganz", breite=60),
     Feld("am", "Am", breite=130),
     Feld("benutzer", "Von", breite=80)),
    ("programm", "teil_nr"),
    "Von Hand gemerkte Zuordnungen der LST-Teile zu Angebot und Position (Lernsystem).")


def _jetzt():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _norm(text):
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


# ------------------------------------------------------------------ Merkmale
def profil_passt(t, prof):
    """LST-Rohr (profilform, a, b, wand) gleich dem Profil der Stammdaten (form, a, b, wand)?"""
    if not prof or not t.get("profilform") or not t.get("a"):
        return False
    if prof.get("form") != t["profilform"] or abs((prof.get("wand") or 0) - (t.get("wand") or 0)) > MASS_TOL:
        return False
    pa, pb = prof.get("a") or 0, prof.get("b") or prof.get("a") or 0
    ta, tb = t["a"], t.get("b") or t["a"]
    return abs(max(pa, pb) - max(ta, tb)) <= MASS_TOL and abs(min(pa, pb) - min(ta, tb)) <= MASS_TOL


def werkstoff_passt(t, werkstoff_id, werkstoffe):
    """LST-Werkstoff (St37, 1.4301 …) passt zur Werkstoff-ID der Position; ohne Werkstoff in der LST: ja."""
    wort = _norm(tp.werkstoff_wort(t))
    if not wort:
        return True
    w = werkstoffe.get(werkstoff_id) or {}
    return any(wort in _norm(x) for x in (werkstoff_id, w.get("name"), w.get("bezeichnung"), w.get("werkstoffnr")))


def merkmale_passen(t, p, k, weg=True):
    if not profil_passt(t, k.profile.get(p.get("profil_id"))):
        return False
    if not werkstoff_passt(t, p.get("werkstoff_id"), k.werkstoffe):
        return False
    if not t.get("laenge") or not p.get("laenge") or abs(t["laenge"] - p["laenge"]) > LAENGE_TOL:
        return False
    if weg and t.get("schneidweg") and p.get("schneidweg"):
        return abs(t["schneidweg"] - p["schneidweg"]) <= WEG_TOL * max(t["schneidweg"], p["schneidweg"])
    return True


# ------------------------------------------------------------------ Zuordnung
def hand_zuordnungen(db):
    return {(z["programm"], z["teil_nr"]): z for z in db.zeilen(ZUORDNUNG.name)}


def merken(db, teil, nummer, pos, benutzer=""):
    """Zuordnung von Hand merken (nummer leer = dieses Teil nie zuordnen); ersetzt eine frühere."""
    alt = hand_zuordnungen(db).get((teil["programm"], teil["teil_nr"]))
    werte = dict(programm=teil["programm"], teil_nr=teil["teil_nr"], nummer=nummer or "", pos=pos, am=_jetzt(),
                 benutzer=benutzer or "")
    if alt:
        for f in ("nummer", "pos", "am", "benutzer"):
            db.aendern(ZUORDNUNG.name, alt["id"], f, werte[f])
        return alt["id"]
    return db.neu(ZUORDNUNG.name, werte)


def vergessen(db, teil):
    alt = hand_zuordnungen(db).get((teil["programm"], teil["teil_nr"]))
    if alt:
        db.loeschen(ZUORDNUNG.name, [alt["id"]])


class _Bestand:
    """Angebote und Positionen einmal lesen (für viele LST-Teile)."""

    def __init__(self, db, heute=None):
        self.db = db
        self.k = db.kontext()
        heute = heute or datetime.date.today()
        self.ab = (heute - datetime.timedelta(days=ZEITRAUM_TAGE)).isoformat()
        self.angebote = {}
        self.nach_nummer = {}
        for aid, nummer, datum, zusatz in db.con.execute("SELECT id, nummer, datum, zusatz FROM angebote"):
            try:
                pp = ((json.loads(zusatz) if zusatz else {}).get("ppease") or {}).get("nummer") or ""
            except (ValueError, AttributeError):
                pp = ""
            a = dict(id=aid, nummer=nummer or "", datum=str(datum or ""), ppease=pp)
            self.angebote[aid] = a
            for n in {a["nummer"], pp} - {""}:
                self.nach_nummer.setdefault(n, []).append(a)
        self._pos = None

    def positionen(self):
        """Alle Laserpositionen [dict] (mit angebot = Kopfdaten), neueste Angebote zuerst."""
        if self._pos is None:
            self._pos = []
            for r in self.db.con.execute("SELECT id, angebot_id, pos, artikel, profil_id, werkstoff_id, laenge, "
                                         "schneidweg, einstiche FROM positionen WHERE profil_id IS NOT NULL"):
                p = dict(zip(("id", "angebot_id", "pos", "artikel", "profil_id", "werkstoff_id", "laenge",
                              "schneidweg", "einstiche"), r))
                p["angebot"] = self.angebote.get(p["angebot_id"]) or {}
                self._pos.append(p)
            self._pos.sort(key=lambda p: (p["angebot"].get("datum") or "", p["angebot_id"]), reverse=True)
            self._je_angebot, self._je_artikel, self._je_profil, self._profile_zu = {}, {}, {}, {}
            for p in self._pos:     # Verzeichnisse: bei vielen Teilen und Angeboten nicht jedes Mal alle Positionen
                self._je_angebot.setdefault(p["angebot_id"], []).append(p)
                self._je_artikel.setdefault(_norm(p.get("artikel")), []).append(p)
                self._je_profil.setdefault(p["profil_id"], []).append(p)
        return self._pos

    def von(self, aid):
        self.positionen()
        return self._je_angebot.get(aid, [])

    def mit_artikel(self, art):
        self.positionen()
        return self._je_artikel.get(art, [])

    def mit_profil(self, t):
        """Positionen mit einem Profil, das zum LST-Rohr passt (neueste zuerst)."""
        self.positionen()
        schl = (t.get("profilform"), t.get("a"), t.get("b"), t.get("wand"))
        if schl not in self._profile_zu:
            pids = [pid for pid, prof in self.k.profile.items() if profil_passt(t, prof)]
            liste = [p for pid in pids for p in self._je_profil.get(pid, [])]
            liste.sort(key=lambda p: (p["angebot"].get("datum") or "", p["angebot_id"]), reverse=True)
            self._profile_zu[schl] = liste
        return self._profile_zu[schl]


def _in_angebot(t, pos, k):
    """Position eines Angebots zum LST-Teil: Artikelnummer, sonst Merkmale (ohne Schneidweg, wenn eindeutig)."""
    art = _norm(t.get("artikel"))
    gleich = [p for p in pos if art and _norm(p.get("artikel")) == art]
    if len(gleich) == 1:
        return gleich[0]
    m = [p for p in (gleich or pos) if merkmale_passen(t, p, k)]
    if len(m) == 1:
        return m[0]
    m = [p for p in (gleich or pos) if merkmale_passen(t, p, k, weg=False)]
    return m[0] if len(m) == 1 else None


def zuordnen(db, teile=None, bestand=None):
    """Zuordnung je LST-Teil: {(programm, teil_nr): dict(art, sicher, nummer, angebot_id, position_id, pos, artikel)}
    (ohne Treffer: art KEINE)."""
    b = bestand or _Bestand(db)
    hand = hand_zuordnungen(db)
    out = {}
    for t in teile if teile is not None else pl.teile(db):
        schl = (t["programm"], t["teil_nr"])
        out[schl] = _zuordnen_eins(t, b, hand.get(schl))
    return out


def _treffer(art, p, sicher=True):
    a = p["angebot"]
    return dict(art=art, sicher=sicher, nummer=a.get("nummer") or "", angebot_id=p["angebot_id"],
                position_id=p["id"], pos=p.get("pos"), artikel=p.get("artikel") or "")


def _zuordnen_eins(t, b, hand):
    leer = dict(art=KEINE, sicher=False, nummer="", angebot_id=None, position_id=None, pos=None, artikel="")
    if hand is not None:
        if not hand.get("nummer"):
            return dict(leer, art=HAND)
        for a in b.nach_nummer.get(hand["nummer"], []):
            p = next((p for p in b.von(a["id"]) if p.get("pos") == hand.get("pos")), None)
            if p is not None:
                return _treffer(HAND, p)
        return dict(leer, art=HAND, nummer=hand["nummer"], pos=hand.get("pos"))
    if t.get("ppease"):
        for a in b.nach_nummer.get(t["ppease"], []):
            p = _in_angebot(t, b.von(a["id"]), b.k)
            if p is not None:
                return _treffer(PPEASE, p)
    art = _norm(t.get("artikel"))
    if art and art != _norm(t.get("programm")):
        gleich = [p for p in b.mit_artikel(art) if p["angebot"].get("datum", "") >= b.ab]
        if gleich:
            return _treffer(ARTIKEL, gleich[0], sicher=len({p["angebot_id"] for p in gleich}) == 1
                            or merkmale_passen(t, gleich[0], b.k))
    m = [p for p in b.mit_profil(t) if p["angebot"].get("datum", "") >= b.ab and merkmale_passen(t, p, b.k)]
    if m:
        return _treffer(MERKMALE, m[0], sicher=len({p["angebot_id"] for p in m}) == 1)
    return leer


# ------------------------------------------------------------------ Vergleich
def _rechnung(db, aid, cache):
    """{Positions-ID: dict(soll_s, vergleich_s, bausteine, schluessel, f_laser, kalk_zeile, maschine)} eines
    gespeicherten Angebots (None: nicht berechnet, kein Schnittplan)."""
    if aid in cache:
        return cache[aid]
    from . import nachkalk_rueckmeldung, nachkalkulation
    cache[aid] = None
    kopf = db.angebot(aid)
    r = nachkalk_rueckmeldung._rechnung(db, kopf) if kopf else None
    if r is None:
        return None
    pos, (zeilen, _), k, tab, _ = r
    z_von = {p.get("id"): z for p, z in zip(pos, zeilen)}
    out = {}
    try:
        soll = nachkalkulation.teile_soll(kopf, pos, zeilen, k, tab)
    except (ValueError, KeyError, TypeError, ZeroDivisionError, AttributeError):
        soll = []
    for s in soll:
        bst = s.get("bausteine")
        neben = (bst or {}).get("neben") or 0.0
        out[s["id"]] = dict(s, vergleich_s=round(s["soll_s"] - s.get("f_laser", 1.0) * neben, 2),
                            kalk_zeile=z_von.get(s["id"]) or {}, maschine=s["schluessel"][0])
    cache[aid] = out
    return out


def geometrie(t, p):
    """Abweichungen der Geometrie Position ↔ LST [Text] (leer = passt)."""
    out = []
    if t.get("schneidweg") and p.get("schneidweg"):
        d = p["schneidweg"] - t["schneidweg"]
        if abs(d) > GEOMETRIE_WEG * t["schneidweg"]:
            out.append(f"Schneidweg {p['schneidweg']:.0f} statt {t['schneidweg']:.0f} mm ({100 * d / t['schneidweg']:+.0f} %)")
    if t.get("einstiche") is not None and p.get("einstiche") is not None \
            and abs(p["einstiche"] - t["einstiche"]) > GEOMETRIE_STICHE:
        out.append(f"Einstiche {p['einstiche']:.0f} statt {t['einstiche']}")
    if t.get("laenge") and p.get("laenge") and abs(p["laenge"] - t["laenge"]) > LAENGE_TOL:
        out.append(f"Länge {p['laenge']:.1f} statt {t['laenge']:.1f} mm")
    return out


def vergleich(db, teile=None, heute=None):
    """Je LST-Teil eine Zeile: dict(teil, zuordnung, soll_s (unsere Laserzeit ohne Nebenzeit), lst_s (TRUMPF
    berechnet), ist_s (gemessen oder None), diff_s, diff_pct (Ist bzw. TRUMPF gegen unsere Zeit), geometrie [Text],
    lernbar, grund, schluessel (Schneiddaten), bausteine, f_laser, faktoren (der Maschine beim Rechnen), maschine,
    preis_teil, laser_teil (Laserkosten je Teil), soll_voll_s (mit Nebenzeit))."""
    b = _Bestand(db, heute)
    teile = teile if teile is not None else pl.teile(db)
    zu = zuordnen(db, teile, b)
    pos_von = {p["id"]: p for p in b.positionen()}
    cache, out = {}, []
    for t in teile:
        z = zu[(t["programm"], t["teil_nr"])]
        zeile = dict(teil=t, zuordnung=z, soll_s=None, lst_s=pl.zeit_s(t, gemessen=False),
                     ist_s=pl.zeit_s(t) if t.get("zeiten_gemessen") else None, diff_s=None, diff_pct=None,
                     geometrie=[], lernbar=False, grund="", schluessel=None, bausteine=None, f_laser=1.0,
                     faktoren=None, maschine="", preis_teil=None, laser_teil=None, soll_voll_s=None)
        out.append(zeile)
        if not z.get("position_id"):
            zeile["grund"] = "nicht zugeordnet"
            continue
        r = _rechnung(db, z["angebot_id"], cache)
        s = (r or {}).get(z["position_id"])
        if s is None:
            zeile["grund"] = "Angebot nicht berechnet (Schnittplan fehlt)" if r is None else "Position ohne Laserzeit"
            continue
        kz = s["kalk_zeile"]
        zeile.update(soll_s=s["vergleich_s"], schluessel=s["schluessel"], bausteine=s.get("bausteine"),
                     f_laser=s.get("f_laser", 1.0), faktoren=s.get("faktoren"), soll_voll_s=s["soll_s"], maschine=s["maschine"], preis_teil=kz.get("preis_teil"),
                     laser_teil=kz.get("laser_schneiden_teil"), kalk=kz)
        zeile["geometrie"] = geometrie(t, pos_von.get(z["position_id"]) or {})
        vgl = zeile["ist_s"] if zeile["ist_s"] is not None else zeile["lst_s"]
        if vgl is not None and s["vergleich_s"]:
            zeile["diff_s"] = round(vgl - s["vergleich_s"], 2)
            zeile["diff_pct"] = round(100.0 * (vgl / s["vergleich_s"] - 1.0), 1)
        if t.get("qualitaet") != tp.VOLL:
            zeile["grund"] = f"Datenqualität: {t.get('qualitaet')}"
        elif zeile["geometrie"]:
            zeile["grund"] = "STEP-Messung prüfen"
        elif zeile["ist_s"] is None:
            zeile["grund"] = "noch keine gemessene Zeit (LST vor dem Lauf gespeichert)"
        elif not z.get("sicher"):
            zeile["grund"] = "Zuordnung unsicher (bitte bestätigen)"
        elif s.get("bausteine") is None:
            zeile["grund"] = "Zeit von Hand in der Position"
        else:
            zeile["lernbar"] = True
    return out


def step_pruefen(zeilen):
    """Zeilen mit Geometrie-Abweichung (Liste „STEP-Messung prüfen“)."""
    return [z for z in zeilen if z["geometrie"]]


def kennzahlen(zeilen):
    """Für die Kacheln: dict(teile, zugeordnet, verglichen, lernbar, step_pruefen, abweichung_pct (Median |%|))."""
    import statistics
    pct = [abs(z["diff_pct"]) for z in zeilen if z["diff_pct"] is not None]
    return dict(teile=len(zeilen), zugeordnet=sum(1 for z in zeilen if z["zuordnung"].get("position_id")),
                verglichen=len(pct), lernbar=sum(1 for z in zeilen if z["lernbar"]),
                step_pruefen=len(step_pruefen(zeilen)),
                abweichung_pct=round(statistics.median(pct), 1) if pct else None)
