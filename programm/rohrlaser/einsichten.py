"""Weitere Einsichten aus den eigenen Daten (Plan „Mehr Intelligenz“ I7–I12, Patrick 10.11.2026, Freigabe „Alle sechs“).

Alles nur Vorschlag oder Hinweis; nichts ändert sich ohne Klick, Preise und Gewinn nie.
- I7 kundenvorschlaege: stehen in den letzten KUNDE_MIN Angeboten eines Kunden dieselben Kopfwerte (Maschine, Material
  neuer Positionen, Lieferzeit in Arbeitstagen/Wochen), die weder die Einstellungen noch seine Kundenvorgaben so
  vorgeben -> Vorschlag „als Kundenvorgabe speichern“ (Lernzentrale, Übernehmen mit Rückgängig).
- I8 reklamation_punkte: Wiederholteil, zu dessen früherer Position (oder ganzem Auftrag) eine Reklamation erfasst ist
  -> Hinweis im Angebots-Check mit Datum, Fehlerart und Ursache.
- I9 nachkalk_hinweis: die nachkalkulierten Aufträge desselben Kunden (sonst: mit einem Profil dieses Angebots) brauchten
  am Laser im Mittel deutlich länger/kürzer als geplant -> Hinweis im Angebots-Check. (Für dasselbe Teil meldet das
  schon wiederholteile.check_punkte.)
- I11 zeit_vorschlaege: Programmierzeit wird regelmäßig von Hand in dieselbe Richtung überschrieben -> Vorschlag, die
  Vorgaben (Grundzeit und Zeit je Innenkontur) um den mittleren Faktor anzupassen; Schneidzeit wird auf einer Maschine
  oft von Hand gesetzt -> Hinweis, die Schneiddaten zu prüfen (ohne Übernehmen).
- I12 verlustmuster: Gruppen (Werkstoff-Kategorie × Preisklasse, Kunde), in denen auffällig oft verloren wird, mit dem
  häufigsten Absagegrund -> Startseite und Monatsbericht.
I10 (Selbstkorrektur) steht in lernen.py. Schalter (funktionen.py): I7/I11 „Vorschläge aus Handeinträgen“, I8/I9/I12
„Preis- und Termin-Hinweise“. Abgelehnte Vorschläge stehen wie bei muster.py in der Einstellung muster.ABGELEHNT (über
den gemeinsamen Ordner geteilt). Ohne Qt."""
import datetime
import json
import statistics

from . import funktionen
from . import db_verbindung

KUNDE_MIN = 3                   # I7: so viele Angebote des Kunden hintereinander mit demselben Wert
KUNDE_FELDER = {"maschine": "Maschine", "material_vorgabe": "Material neuer Positionen", "lieferzeit": "Lieferzeit"}
NACHKALK_MIN = 3                # I9: so viele nachkalkulierte Aufträge mindestens
NACHKALK_MAX = 10               # die letzten so vielen
NACHKALK_AB = 0.10              # ab so viel Abweichung der Laserzeit (Median Ist ÷ Soll − 1)
ZEIT_MIN = 5                    # I11: so viele Angebote mit Handwert mindestens
ZEIT_ANTEIL = 0.8               # so viele davon in dieselbe Richtung
ZEIT_AB = 0.2                   # mittlere Abweichung mindestens
ZEIT_MAX_ANGEBOTE = 60          # betrachtet werden die letzten so vielen Angebote
SCHNEID_ANTEIL = 0.5            # Schneidzeit von Hand in mindestens so vielen Angeboten der Maschine
VERLUST_MIN = 5                 # I12: so viele entschiedene Angebote in der Gruppe
VERLUST_QUOTE = 0.34            # Trefferquote der Gruppe höchstens
VERLUST_ABSTAND = 0.15          # und so viel unter der Gesamtquote
VERLUST_TAGE = 365
VERLUST_MAX = 2                 # so viele Muster höchstens


def _abgelehnt(db):
    from . import muster
    return muster._abgelehnt(db)


def _stand(db):
    return (db.con.total_changes, db_verbindung.aenderungsstand(db.con))


_CACHE = {}


def _gemerkt(db, name, fn):
    """fn() je Datenbank und Stand der Datendatei einmal rechnen; scheitert nie laut."""
    try:
        stand = _stand(db)
        alt = _CACHE.get((id(db), name))
        if alt and alt[0] == stand:
            return alt[1]
        wert = fn()
    except Exception:
        return []
    _CACHE[(id(db), name)] = (stand, wert)
    return wert


# ---------------------------------------------------------------------- I7 Kundenvorgaben vorschlagen
def _lieferzeit(z):
    from .stammdaten import ARBEITSTAGE, WOCHEN
    art, wert = z.get("lieferzeit_art"), str(z.get("lieferzeit_wert") or "").strip()
    return f"{art}|{wert}" if art in (ARBEITSTAGE, WOCHEN) and wert else None


def _lz_text(w):
    art, wert = w.split("|", 1)
    return f"{wert} {art}"


def kundenvorschlaege(db):
    """[dict(art 'kunde', schluessel, kundennr, feld, wert, text, angebote)]."""
    if not funktionen.an(funktionen.REGELVORSCHLAEGE, db):
        return []
    return _gemerkt(db, "kunde", lambda: _kundenvorschlaege(db))


def _kundenvorschlaege(db):
    from . import kundenvorgabe
    zeilen = [dict(r) for r in db.con.execute(
        "SELECT id, kundennr, maschine, material_vorgabe, lieferzeit_art, lieferzeit_wert FROM angebote WHERE "
        "COALESCE(ersetzt_durch, '') = '' AND COALESCE(kundennr, '') <> '' ORDER BY id DESC LIMIT 2000")]
    je = {}
    for z in zeilen:
        je.setdefault(str(z["kundennr"]), []).append(z)
    einst = db.kopf_vorgaben()
    einst_werte = dict(maschine=einst.get("maschine"), material_vorgabe=einst.get("material_vorgabe"),
                       lieferzeit=_lieferzeit(einst))
    kunden = {str(z.get("kundennr")): z.get("name") or "" for z in db.zeilen("kunden")}
    abgelehnt = _abgelehnt(db)
    out = []
    for nr, liste in je.items():
        if nr not in kunden or len(liste) < KUNDE_MIN:
            continue
        v = kundenvorgabe.fuer_kunde(db, nr) or {}
        hat = dict(maschine=v.get("maschine"), material_vorgabe=v.get("material_vorgabe"), lieferzeit=_lieferzeit(v))
        for feld, titel in KUNDE_FELDER.items():
            werte = [_lieferzeit(z) if feld == "lieferzeit" else z.get(feld) for z in liste[:KUNDE_MIN]]
            w = werte[0]
            if w in (None, "") or any(x != w for x in werte) or w == einst_werte[feld] or w == hat[feld]:
                continue
            schl = f"kunde|{nr}|{feld}|{w}"
            if schl in abgelehnt:
                continue
            n = 0
            for z in liste:         # wie viele Angebote hintereinander
                if (_lieferzeit(z) if feld == "lieferzeit" else z.get(feld)) != w:
                    break
                n += 1
            zeige = _lz_text(w) if feld == "lieferzeit" else w
            out.append(dict(art="kunde", schluessel=schl, kundennr=nr, kunde=f"{nr} {kunden[nr]}".strip(), feld=feld,
                            wert=w, angebote=n, bereich="Vorschlag: Kundenvorgabe",
                            text=f"{titel} „{zeige}“ in den letzten {n} Angeboten dieses Kunden – als "
                                 "Kundenvorgabe speichern?"))
    return out


def _kunde_uebernehmen(db, v):
    from . import kundenvorgabe
    if v["feld"] == "lieferzeit":
        art, wert = v["wert"].split("|", 1)
        neu = dict(lieferzeit_art=art, lieferzeit_wert=wert)
    else:
        neu = {v["feld"]: v["wert"]}
    z = kundenvorgabe.fuer_kunde(db, v["kundennr"])
    if z is None:
        rid = db.neu("kundenvorgaben", dict(kundennr=v["kundennr"], **neu))
        zurueck = lambda: db.loeschen("kundenvorgaben", [rid])      # noqa: E731
    else:
        alt = {f: z.get(f) for f in neu}
        for f, w in neu.items():
            db.aendern("kundenvorgaben", z["id"], f, w)
        zurueck = lambda: [db.aendern("kundenvorgaben", z["id"], f, w) for f, w in alt.items()]     # noqa: E731
    return f"Kundenvorgabe für {v['kunde']} gespeichert: {KUNDE_FELDER[v['feld']]}.", zurueck


# ---------------------------------------------------------------------- I11 überschriebene Zeiten
def zeit_vorschlaege(db):
    """[dict(art 'progzeit' (übernehmbar) | 'schneidzeit' (nur Hinweis), schluessel, text, ...)]."""
    if not funktionen.an(funktionen.REGELVORSCHLAEGE, db):
        return []
    return _gemerkt(db, "zeit", lambda: _zeit_vorschlaege(db))


def _zeit_vorschlaege(db):
    from .rechnen import konturen_anzahl
    from .stammdaten import zahl_als_text as zahl
    ids = [r[0] for r in db.con.execute("SELECT id FROM angebote WHERE COALESCE(ersetzt_durch, '') = '' ORDER BY id "
                                        "DESC LIMIT ?", (ZEIT_MAX_ANGEBOTE,))]
    if not ids:
        return []
    marken = ",".join("?" * len(ids))
    pos = [dict(r) for r in db.con.execute(
        f"SELECT p.*, a.maschine AS _maschine FROM positionen p JOIN angebote a ON a.id = p.angebot_id WHERE "
        f"p.angebot_id IN ({marken}) AND COALESCE(p.profil_id, '') <> ''", ids)]
    einst = db.einstellungen()
    abgelehnt = _abgelehnt(db)
    out = []
    grund, kontur = einst.get("programmierung_zeit"), einst.get("programmierung_kontur") or 0
    if isinstance(grund, (int, float)) and grund > 0:
        je = {}             # Angebot -> Faktoren Hand ÷ Vorgabe
        for p in pos:
            hand = p.get("prog_zeit")
            if not isinstance(hand, (int, float)) or hand <= 0:
                continue
            soll = grund + (kontur if isinstance(kontur, (int, float)) else 0) * konturen_anzahl(p)
            if soll > 0:
                je.setdefault(p["angebot_id"], []).append(hand / soll)
        faktoren = [statistics.median(f) for f in je.values()]
        if len(faktoren) >= ZEIT_MIN:
            f = statistics.median(faktoren)
            richtung = sum(1 for x in faktoren if (x > 1) == (f > 1) and abs(x - 1) > 0.02) / len(faktoren)
            schl = f"progzeit|{round(grund, 2)}|{'+' if f > 1 else '-'}"
            if abs(f - 1) >= ZEIT_AB and richtung >= ZEIT_ANTEIL and schl not in abgelehnt:
                neu_g = round(grund * f, 1)
                neu_k = round(kontur * f, 2) if isinstance(kontur, (int, float)) and kontur else kontur
                out.append(dict(art="progzeit", schluessel=schl, faktor=f, angebote=len(faktoren), kunde="alle Kunden",
                                neu=dict(programmierung_zeit=neu_g, programmierung_kontur=neu_k),
                                bereich="Vorschlag: Programmierzeit",
                                text=f"Programmierzeit in {len(faktoren)} Angeboten von Hand überschrieben, im Mittel "
                                     f"{zahl(abs(100 * (f - 1)), 0)} % {'höher' if f > 1 else 'niedriger'} als die "
                                     f"Vorgabe – Grundzeit {zahl(grund, 1)} → {zahl(neu_g, 1)} min"
                                     + (f", je Innenkontur {zahl(kontur, 2)} → {zahl(neu_k, 2)} min" if neu_k else "")
                                     + " setzen?"))
    alle, hand = {}, {}
    for p in pos:
        m = p.get("_maschine") or ""
        if not m:
            continue
        alle.setdefault(m, set()).add(p["angebot_id"])
        if isinstance(p.get("zeit_manuell"), (int, float)) and p["zeit_manuell"] > 0:
            hand.setdefault(m, set()).add(p["angebot_id"])
    for m, mit in sorted(hand.items()):
        schl = f"schneidzeit|{m}"
        if len(mit) >= ZEIT_MIN and len(mit) / len(alle[m]) >= SCHNEID_ANTEIL and schl not in abgelehnt:
            out.append(dict(art="schneidzeit", schluessel=schl, angebote=len(mit), kunde="alle Kunden",
                            bereich="Hinweis: Schneidzeit",
                            text=f"Maschine {m}: Schneidzeit in {len(mit)} von {len(alle[m])} Angeboten von Hand "
                                 "gesetzt – Schneiddaten prüfen (Einstellungen → Kennwerte lernen bzw. Schneiddaten)"))
    return out


def _progzeit_uebernehmen(db, v):
    alt = {n: db.einstellung(n) for n in v["neu"]}
    for n, w in v["neu"].items():
        db.einstellung_setzen(n, w)
    return ("Programmierzeit-Vorgaben angepasst (gilt für neue Rechnungen; verschickte Angebote bleiben).",
            lambda: [db.einstellung_setzen(n, w) for n, w in alt.items()])


# ---------------------------------------------------------------------- Lernzentrale: gemeinsam
def vorschlaege(db):
    return kundenvorschlaege(db) + zeit_vorschlaege(db)


def text(db):
    """Zeile für die Startseite oder None."""
    n = len(vorschlaege(db))
    if not n:
        return None
    return (f"{n} {'Vorschläge' if n > 1 else 'Vorschlag'} aus Ihren Angeboten (Kundenvorgabe, Programmierzeit, Schneidzeit; "
            "Doppelklick: Lernzentrale)")


def uebernehmbar(v):
    return v.get("art") in ("kunde", "progzeit")


def uebernehmen(db, v):
    """Ergebnis: (Text, Rückgängig-Funktion)."""
    if v["art"] == "kunde":
        return _kunde_uebernehmen(db, v)
    if v["art"] == "progzeit":
        return _progzeit_uebernehmen(db, v)
    raise ValueError("Dieser Eintrag ist nur ein Hinweis; „Vergessen“ blendet ihn aus.")


def ablehnen(db, v):
    from . import muster
    d = dict(_abgelehnt(db))
    d[v["schluessel"]] = datetime.date.today().isoformat()
    db.einstellung_setzen(muster.ABGELEHNT, d)
    return f"Nicht übernommen: {v['text']}"


# ---------------------------------------------------------------------- I8 Reklamation bei Wiederholteilen
def reklamation_punkte(db, treffer, positionen):
    """Angebots-Check: [(Art, Text, Zeile)] für Wiederholteile (sicher bzw. zu prüfen) mit einer Reklamation."""
    from . import wiederholteile
    if not treffer or not funktionen.an(funktionen.PREIS_HINWEISE, db) or not funktionen.an("funktion_reklamation", db):
        return []
    out = []
    for i, p in enumerate(positionen):
        for t in treffer.get(p.get("id")) or ():
            if t.art == wiederholteile.AEHNLICH:
                continue
            try:
                r = db.con.execute(
                    "SELECT datum, fehlerart, ursache, position_id FROM reklamationen WHERE angebot_id=? AND "
                    "(position_id=? OR position_id IS NULL) ORDER BY position_id IS NULL, id DESC LIMIT 1",
                    (t.angebot["id"], t.position["id"])).fetchone()
            except Exception:
                return out
            if r is None:
                continue
            try:
                datum = datetime.date.fromisoformat(str(r["datum"])[:10]).strftime("%d.%m.%Y")
            except ValueError:
                datum = str(r["datum"] or "")
            was = ", ".join(x for x in (r["fehlerart"], f"Ursache {r['ursache']}" if r["ursache"] else "") if x)
            wo = "dieses Teil" if r["position_id"] is not None else "der Auftrag"
            out.append(("HINWEIS", f"Pos. {p.get('pos')}: Wiederholteil aus {t.angebot.get('nummer')} – {wo} wurde "
                                   f"reklamiert ({datum}{': ' + was if was else ''})", i))
            break
    return out


# ---------------------------------------------------------------------- I9 Nachkalkulation ähnlicher Aufträge
def _nachkalk_faelle(db):
    """[dict(id, kundennr, profile, abw)] der nachkalkulierten Aufträge mit erfasster Laserzeit, neueste zuerst."""
    out = []
    for r in db.con.execute("SELECT id, kundennr, nachkalkulation FROM angebote WHERE COALESCE(nachkalkulation, '') "
                            "NOT IN ('', 'null') AND COALESCE(ersetzt_durch, '') = '' ORDER BY id DESC LIMIT 500"):
        try:
            nk = json.loads(r["nachkalkulation"])
        except (TypeError, ValueError):
            continue
        soll = nk.get("soll") if isinstance(nk, dict) else None
        if not isinstance(soll, dict):
            continue
        z = next((z for z in soll.get("zeilen") or () if z and z[0] == "Laserzeit"), None)
        if not z or len(z) < 8 or not z[7] or not isinstance(z[3], (int, float)) or z[3] <= 0 \
                or not isinstance(z[4], (int, float)):
            continue
        out.append(dict(id=r["id"], kundennr=str(r["kundennr"] or ""), profile=set(soll.get("profile") or ()),
                        abw=z[4] / z[3] - 1))
    return out


def nachkalk_hinweis(db, kopf, positionen, ohne_id=None):
    """Text für den Angebots-Check oder None."""
    from .stammdaten import zahl_als_text as zahl
    if not funktionen.an(funktionen.PREIS_HINWEISE, db) or not funktionen.an("funktion_nachkalkulation", db):
        return None
    faelle = [f for f in _gemerkt(db, "nachkalk", lambda: _nachkalk_faelle(db)) if f["id"] != ohne_id]
    nr = str((kopf or {}).get("kundennr") or "")
    profile = {str(p.get("profil_id")) for p in positionen or () if p.get("profil_id")}
    for wer, gruppe in (("dieses Kunden", [f for f in faelle if nr and f["kundennr"] == nr]),
                        ("mit diesen Profilen", [f for f in faelle if profile & f["profile"]])):
        gruppe = gruppe[:NACHKALK_MAX]
        if len(gruppe) < NACHKALK_MIN:
            continue
        m = statistics.median(f["abw"] for f in gruppe)
        if abs(m) < NACHKALK_AB:
            return None             # passt: kein Hinweis (auch nicht aus der gröberen Gruppe)
        return (f"Nachkalkulation: Die letzten {len(gruppe)} Aufträge {wer} brauchten am Laser im Mittel "
                f"{zahl(abs(100 * m), 0)} % {'länger' if m > 0 else 'kürzer'} als geplant – Zeiten prüfen")
    return None


# ---------------------------------------------------------------------- I12 Verlustmuster
def verlustmuster(db, heute=None):
    """Texte, wo auffällig oft verloren wird (letzte VERLUST_TAGE Tage, eigene Angebote)."""
    if not funktionen.an(funktionen.PREIS_HINWEISE, db):
        return []
    return _gemerkt(db, f"verlust{heute}", lambda: verlust_aus(
        db.angebote(), db.angebot_werkstoffe(), {w: z.get("kategorie") for w, z in db.kontext().werkstoffe.items()},
        heute))


def verlust_aus(zeilen, werkstoffe_je_angebot, kategorien, heute=None):
    from . import absage
    gruppen, ja, nein = {}, 0, 0
    for z in absage.auswahl(zeilen, heute, VERLUST_TAGE):
        v = z.get("vorgang") or "Entwurf"
        if v not in ("Beauftragt", "Abgelehnt"):
            continue
        ja += v == "Beauftragt"
        nein += v == "Abgelehnt"
        kat = absage.kategorie_des_angebots((werkstoffe_je_angebot or {}).get(z["id"]), kategorien or {})
        for name in ((f"{kat}, {absage.preisklasse(z.get('vk_netto'))}"),
                     "Kunde " + ((z.get("kunde") or "").strip() or "ohne Namen")):
            g = gruppen.setdefault(name, dict(ja=0, nein=0, wert=0.0, gruende={}))
            if v == "Beauftragt":
                g["ja"] += 1
            else:
                g["nein"] += 1
                g["wert"] += z.get("vk_netto") if isinstance(z.get("vk_netto"), (int, float)) else 0.0
                grund = (absage.letzte(z) or {}).get("grund") or absage.OHNE_GRUND
                g["gruende"][grund] = g["gruende"].get(grund, 0) + 1
    if ja + nein < VERLUST_MIN:
        return []
    gesamt = ja / (ja + nein)
    treffer = []
    for name, g in gruppen.items():
        n = g["ja"] + g["nein"]
        if n < VERLUST_MIN or g["ja"] / n > VERLUST_QUOTE or gesamt - g["ja"] / n < VERLUST_ABSTAND:
            continue
        grund, wie_oft = max(g["gruende"].items(), key=lambda x: x[1])
        zusatz = f", meist „{grund}“" if grund != absage.OHNE_GRUND and wie_oft * 2 >= g["nein"] else ""
        treffer.append((g["wert"], f"{name}: {g['nein']} von {n} abgelehnt{zusatz} (insgesamt "
                                   f"{100 * gesamt:.0f} % Trefferquote)"))
    return [t for _, t in sorted(treffer, key=lambda x: (-x[0], x[1]))[:VERLUST_MAX]]
