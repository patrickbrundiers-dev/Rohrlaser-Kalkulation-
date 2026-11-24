"""Lernsystem L4 und L5: aus den gemessenen Zeiten der LST-Teile Faktoren lernen und verwalten (Plan
„Selbstlernende Kalkulation aus LST-Daten“, Patrick 20.11.2026 „Alles einbauen nach allen Empfehlungen“). Ohne Qt.

Kein eigenes System daneben: die Fälle gehen in die vorhandenen Kennwerte (Quellen lst_…, Freigabe und Zurücknehmen
über die Kennwerte-Historie) und in die Kalibrierung je Baustein (kalibrierung.faelle_bausteine, dort bekommt das
Einstechen seinen eigenen Faktor; die Einstichzeit bleibt ein eigener Posten).

Fall = zugeordnetes, vollständiges LST-Teil mit gemessener Zeit und passender Geometrie (lst_vergleich.vergleich,
lernbar). Gewicht je Fall nach Alter: Halbwertszeit HALBWERT_TAGE. Je Gruppe: gewichteter Median von Ist ÷ Soll,
Ausreißer über MAD_GRENZE × MAD ausgeschlossen; Vorschlag erst ab MINDEST_TEILE Teilen aus MINDEST_PROGRAMME
Programmen. Ebenen (von grob nach fein):
1. Maschine × Werkstoffgruppe → Vorschübe der Schneiddaten dieser Maschine und Gruppe
2. Werkstoff × Profil → nur Hinweis (es gibt keinen Stammdatenwert je Profil)
3. Wandbereich (Maschine, Werkstoff, bis 3 / 3–6 / über 6 mm) → Vorschübe des Bereichs
4. Merkmal (viele Einstiche, kurze/lange Teile, Rundrohr) → nur Hinweis
Für die Vorschübe (Ebenen 1 und 3) zählt nur der Schneidanteil: Soll = Schneidzeit, Ist = gemessene Zeit − übrige
Zeit der Kalkulation; so ändert sich nur, was der Vorschub bestimmt.

Verwalten (L5): Freigeben (mit Begründung, Preiswirkung wird angezeigt; über PREIS_GRENZE % oder Faktor außerhalb
FAKTOR_BEREICH nur mit ausdrücklicher Bestätigung), Ablehnen (Vorschlag ruht, bis sich der Faktor um mehr als
RUHE_FAKTOR ändert oder RUHE_TEILE neue Teile dazukommen), Zurücksetzen (Kennwerte-Historie) und Protokoll.

Gegenprobe (Produktionsdaten-Intelligenz, Patrick 24.11.2026): jeder Vorschlag wird vor der Freigabe an den
Referenzdaten geprüft (validieren: je Programm aus den übrigen gelernt). Sagt der Faktor die Teile nicht besser voraus
als die bisherige Rechnung, geht die Freigabe nur mit ausdrücklicher Bestätigung."""
import datetime
import json
import statistics

from . import kennwerte, lst_vergleich
from .stammdaten import Feld, Tabelle

HALBWERT_TAGE = 180
MAD_GRENZE = 3.0
MINDEST_TEILE = 10
MINDEST_PROGRAMME = 3
FAKTOR_BEREICH = (0.7, 1.3)
PREIS_GRENZE = 15.0             # % Preiswirkung: darüber nur mit ausdrücklicher Bestätigung
RUHE_FAKTOR = 0.03
RUHE_TEILE = 5
VIELE_EINSTICHE, KURZ_MM, LANG_MM = 10, 200.0, 3000.0

Q_MASCHINE, Q_PROFIL, Q_BEREICH, Q_MERKMAL = "lst_maschine", "lst_profil", "lst_wandbereich", "lst_merkmal"
EBENEN = ((Q_MASCHINE, "LST: Maschine × Werkstoffgruppe → Vorschübe"),
          (Q_PROFIL, "LST: Werkstoff × Profil (nur Hinweis)"),
          (Q_BEREICH, "LST: Wandbereich → Vorschübe des Bereichs"),
          (Q_MERKMAL, "LST: Merkmal (nur Hinweis)"))
EBENE_TEXT = dict(EBENEN)

ENTSCHEIDUNGEN = Tabelle(
    "lst_entscheidungen", "LST-Entscheidungen",
    (Feld("quelle", "Ebene", pflicht=True, breite=110),
     Feld("schluessel", "Gruppe", pflicht=True, breite=200),     # JSON-Liste
     Feld("entscheidung", "Entscheidung", breite=80),             # abgelehnt
     Feld("faktor", "Faktor", "zahl", stellen=3, breite=60),
     Feld("n", "Teile", "ganz", breite=50),
     Feld("am", "Am", breite=130),
     Feld("benutzer", "Von", breite=80),
     Feld("grund", "Grund", breite=200)),
    ("quelle", "schluessel"),
    "Abgelehnte Vorschläge des Lernsystems (ruhen, bis sich die Daten deutlich ändern).")


class BestaetigungNoetig(ValueError):
    """Freigabe über der Preisgrenze oder mit ungewöhnlichem Faktor: nur mit ausdrücklicher Bestätigung."""


def _datum(t):
    """Fertigungsdatum des LST-Teils (TT.MM.JJJJ aus der LST, sonst Einlesezeit) als date."""
    d = str(t.get("datum") or "").strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return datetime.datetime.strptime(d[:10], fmt).date()
        except ValueError:
            continue
    try:
        return datetime.date.fromisoformat(str(t.get("gelesen") or "")[:10])
    except ValueError:
        return datetime.date.today()


def gewicht(datum, heute=None):
    alter = max(0, ((heute or datetime.date.today()) - datum).days)
    return 0.5 ** (alter / HALBWERT_TAGE)


def _merkmale(t):
    out = []
    if (t.get("einstiche") or 0) >= VIELE_EINSTICHE:
        out.append(f"viele Einstiche (ab {VIELE_EINSTICHE})")
    if t.get("laenge") and t["laenge"] < KURZ_MM:
        out.append(f"kurze Teile (unter {KURZ_MM:.0f} mm)")
    if t.get("laenge") and t["laenge"] > LANG_MM:
        out.append(f"lange Teile (über {LANG_MM:.0f} mm)")
    if t.get("profilform") == "Rundrohr":
        out.append("Rundrohr")
    return out


def _kategorie(wer, k):
    from . import rechnen
    return wer[len("Kategorie "):] if str(wer).startswith("Kategorie ") else rechnen.kategorie(wer, k)


def faelle(db, zeilen=None, heute=None):
    """Lernbare Fälle [dict(teil, programm, soll, ist, soll_schneiden, ist_schneiden, gewicht, datum, maschine,
    werkstoff (Schneiddaten), kategorie, profil, wand_bis, gas, merkmale, preis_teil, laser_teil, angebot)]."""
    from . import kalibrierung
    zeilen = zeilen if zeilen is not None else lst_vergleich.vergleich(db, heute=heute)
    k = db.kontext()
    out = []
    for z in zeilen:
        if not z["lernbar"] or not z["soll_s"] or not z["ist_s"]:
            continue
        t, schl = z["teil"], z["schluessel"]
        bst = z.get("bausteine") or {}
        schneiden = z["f_laser"] * (bst.get("schneiden") or 0.0)
        rest = z["soll_s"] - schneiden
        d = _datum(t)
        pos = z["zuordnung"]
        out.append(dict(teil=t, programm=t["programm"], soll=z["soll_s"], ist=z["ist_s"],
                        soll_schneiden=schneiden if schneiden > 0 else None,
                        ist_schneiden=(z["ist_s"] - rest) if schneiden > 0 and z["ist_s"] - rest > 0 else None,
                        gewicht=gewicht(d, heute), datum=d.isoformat(), maschine=schl[0], werkstoff=schl[1],
                        kategorie=_kategorie(schl[1], k), wand_bis=schl[2], gas=schl[3],
                        bereich=kalibrierung.bereich(schl[2]), merkmale=_merkmale(t),
                        profil=_profil_von(db, pos.get("position_id")), preis_teil=z.get("preis_teil"),
                        laser_teil=z.get("laser_teil"), angebot=pos.get("nummer") or "", zeile=z))
    return out


def _profil_von(db, position_id):
    if not position_id:
        return ""
    r = db.con.execute("SELECT profil_id FROM positionen WHERE id=?", (position_id,)).fetchone()
    return (r[0] if r else "") or ""


def _gruppen(fl):
    """{(Quelle, Schlüssel): [(Fall, soll, ist)]} der vier Ebenen."""
    g = {}
    for f in fl:
        if f["soll_schneiden"] and f["ist_schneiden"]:
            g.setdefault((Q_MASCHINE, (f["maschine"], f["kategorie"])), []).append(
                (f, f["soll_schneiden"], f["ist_schneiden"]))
            g.setdefault((Q_BEREICH, (f["maschine"], f["werkstoff"], f["bereich"])), []).append(
                (f, f["soll_schneiden"], f["ist_schneiden"]))
        g.setdefault((Q_PROFIL, (f["maschine"], f["werkstoff"], f["profil"])), []).append((f, f["soll"], f["ist"]))
        for m in f["merkmale"]:
            g.setdefault((Q_MERKMAL, (f["maschine"], m)), []).append((f, f["soll"], f["ist"]))
    return g


def _gew_median(paare):
    """Gewichteter Median [(Wert, Gewicht)]."""
    s = sorted(paare)
    ges = sum(w for _, w in s)
    if not s or ges <= 0:
        return None
    lauf = 0.0
    for x, w in s:
        lauf += w
        if lauf >= ges / 2:
            return x
    return s[-1][0]


def auswerten(eintraege, mindest_teile=MINDEST_TEILE, mindest_programme=MINDEST_PROGRAMME):
    """eintraege [(Fall, soll, ist)] → dict(faktor, n, programme, streuung, ausreisser, faelle, status, warnung)."""
    q = [(ist / soll, f["gewicht"], f) for f, soll, ist in eintraege if soll and soll > 0 and ist and ist > 0]
    leer = dict(faktor=None, n=0, programme=0, streuung=None, ausreisser=[], faelle=[], status="zu wenig Daten",
                warnung="")
    if not q:
        return leer
    med = statistics.median(x for x, _, _ in q)
    mad = statistics.median(abs(x - med) for x, _, _ in q)
    drin = [e for e in q if mad <= 0 or abs(e[0] - med) <= MAD_GRENZE * mad]
    raus = [e[2] for e in q if e not in drin]
    faktor = _gew_median([(x, w) for x, w, _ in drin])
    streuung = statistics.median(abs(x - faktor) for x, _, _ in drin)
    progs = len({e[2]["programm"] for e in drin})
    ok = len(drin) >= mindest_teile and progs >= mindest_programme
    warnung = "" if FAKTOR_BEREICH[0] <= faktor <= FAKTOR_BEREICH[1] else \
        f"Faktor {faktor:.2f} außerhalb {FAKTOR_BEREICH[0]:.1f}–{FAKTOR_BEREICH[1]:.1f}: Daten prüfen"
    return dict(faktor=round(faktor, 3), n=len(drin), programme=progs, streuung=round(streuung, 3), ausreisser=raus,
                faelle=[e[2] for e in drin], status="ok" if ok else "zu wenig Daten", warnung=warnung)


def validieren(eintraege):
    """Gegenprobe mit Referenzdaten (Produktionsdaten-Intelligenz 24.11.2026, Schritt 9 „mit Referenzdaten testen“):
    je Programm den Faktor nur aus den ANDEREN Programmen lernen und damit die Teile dieses Programms vorhersagen.
    Ergebnis dict(programme, teile, fehler_vorher (Median |Ist ÷ Soll − 1| in %), fehler_nachher (mit dem gelernten
    Faktor), besser (nachher kleiner), text); mit weniger als 2 Programmen: programme < 2, besser None."""
    progs = sorted({f["programm"] for f, soll, ist in eintraege if soll and ist})
    leer = dict(programme=len(progs), teile=0, fehler_vorher=None, fehler_nachher=None, besser=None,
                text="Gegenprobe braucht Teile aus mindestens 2 Programmen")
    if len(progs) < 2:
        return leer
    vorher, nachher = [], []
    for p in progs:
        lern = [e for e in eintraege if e[0]["programm"] != p]
        fk = auswerten(lern, mindest_teile=1, mindest_programme=1)["faktor"]
        if not fk:
            continue
        for f, soll, ist in eintraege:
            if f["programm"] == p and soll and ist and soll > 0 and ist > 0:
                vorher.append(abs(ist / soll - 1.0))
                nachher.append(abs(ist / (soll * fk) - 1.0))
    if not vorher:
        return leer
    a, b = 100 * statistics.median(vorher), 100 * statistics.median(nachher)
    return dict(programme=len(progs), teile=len(vorher), fehler_vorher=round(a, 1), fehler_nachher=round(b, 1),
                besser=b < a, text=f"Gegenprobe an {len(vorher)} Teilen aus {len(progs)} Programmen: Abweichung "
                                   f"{a:.1f} % → {b:.1f} %".replace(".", ","))


def preiswirkung(v):
    """Mittlere Wirkung auf den Teilepreis [%] der Fälle eines Vorschlags (Laserkosten × (Faktor − 1) × Anteil)."""
    w = []
    for f in v.get("faelle") or ():
        if not f.get("preis_teil") or f.get("laser_teil") is None or not f["soll"]:
            continue
        anteil = (f["soll_schneiden"] or 0.0) / f["soll"] if v["quelle"] in (Q_MASCHINE, Q_BEREICH) else 1.0
        w.append(100.0 * f["laser_teil"] * (v["faktor"] - 1.0) * anteil / f["preis_teil"])
    return round(statistics.median(w), 1) if w else None


def _abgelehnt(db):
    return {(z["quelle"], z["schluessel"]): z for z in db.zeilen(ENTSCHEIDUNGEN.name)}


def vorschlaege(db, zeilen=None, heute=None, mit_ruhenden=False):
    """Vorschläge aller Ebenen [dict(quelle, titel, schluessel, faktor, n, programme, streuung, status, warnung,
    preiswirkung, anwendbar, ruht, faelle)], sortiert nach Ebene und Gruppe."""
    fl = faelle(db, zeilen, heute)
    ab = _abgelehnt(db)
    reihen = {q: i for i, (q, _) in enumerate(EBENEN)}
    out = []
    for (quelle, schl), e in sorted(_gruppen(fl).items(), key=lambda x: (reihen[x[0][0]], [str(s) for s in x[0][1]])):
        v = dict(quelle=quelle, titel=EBENE_TEXT[quelle], schluessel=schl, **auswerten(e))
        v["anwendbar"] = quelle in (Q_MASCHINE, Q_BEREICH) and kennwerte.QUELLEN.get(quelle, (0, 0, None))[2] is not None
        v["preiswirkung"] = preiswirkung(v) if v["faktor"] else None
        v["validierung"] = validieren(e) if v["faktor"] else None
        a = ab.get((quelle, json.dumps(list(schl), ensure_ascii=False)))
        v["ruht"] = bool(a) and v["faktor"] is not None and abs(v["faktor"] - (a.get("faktor") or 0)) <= RUHE_FAKTOR \
            and v["n"] < (a.get("n") or 0) + RUHE_TEILE
        if v["ruht"] and not mit_ruhenden:
            continue
        out.append(v)
    return out


def text_schluessel(v):
    return " · ".join(str(s) for s in v["schluessel"] if s not in (None, ""))


def freigeben(db, v, version, begruendung="", bestaetigt=False):
    """Vorschlag übernehmen (über die Kennwerte: Historie, zurücknehmbar). Über PREIS_GRENZE oder mit Warnung nur
    mit bestaetigt=True (sonst BestaetigungNoetig). Ergebnis: ID der Historie."""
    if v.get("status") != "ok":
        raise ValueError("Zu wenig Daten für eine Freigabe (mindestens "
                         f"{MINDEST_TEILE} Teile aus {MINDEST_PROGRAMME} Programmen).")
    if not v.get("anwendbar"):
        raise ValueError("Diese Ebene ist nur ein Hinweis; es gibt keinen Stammdatenwert dafür.")
    pw = v.get("preiswirkung")
    val = v.get("validierung") or {}
    if not bestaetigt and val.get("besser") is False:
        raise BestaetigungNoetig(f"{val.get('text')}: der gelernte Faktor sagt die Referenzteile nicht besser voraus "
                                 "als die bisherige Kalkulation. Bitte ausdrücklich bestätigen.")
    if not bestaetigt and ((pw is not None and abs(pw) > PREIS_GRENZE) or v.get("warnung")):
        raise BestaetigungNoetig(
            (f"Preiswirkung {pw:+.1f} % liegt über {PREIS_GRENZE:.0f} %. " if pw is not None and abs(pw) > PREIS_GRENZE
             else "") + (v.get("warnung") or "") + " Bitte ausdrücklich bestätigen.")
    text = (begruendung or "").strip() or (
        f"Lernsystem LST: {v['n']} Teile aus {v['programme']} Programmen, Faktor {v['faktor']:.3f} (Streuung "
        f"{v['streuung']:.3f})" + (f", Preiswirkung {pw:+.1f} %" if pw is not None else "")
        + (f"; {val['text']}" if val.get("text") and val.get("besser") is not None else ""))
    return kennwerte.freigeben(db, dict(v, faktor=v["faktor"]), text, version)


def ablehnen(db, v, grund="", benutzer=""):
    """Vorschlag ruhen lassen (bis sich die Daten deutlich ändern)."""
    schl = json.dumps(list(v["schluessel"]), ensure_ascii=False)
    werte = dict(quelle=v["quelle"], schluessel=schl, entscheidung="abgelehnt", faktor=v.get("faktor"), n=v.get("n"),
                 am=datetime.datetime.now().isoformat(timespec="seconds"), benutzer=benutzer or "", grund=grund or "")
    alt = _abgelehnt(db).get((v["quelle"], schl))
    if alt:
        for f in ("faktor", "n", "am", "benutzer", "grund"):
            db.aendern(ENTSCHEIDUNGEN.name, alt["id"], f, werte[f])
        return alt["id"]
    return db.neu(ENTSCHEIDUNGEN.name, werte)


def wieder_aufnehmen(db, v):
    schl = json.dumps(list(v["schluessel"]), ensure_ascii=False)
    alt = _abgelehnt(db).get((v["quelle"], schl))
    if alt:
        db.loeschen(ENTSCHEIDUNGEN.name, [alt["id"]])


def protokoll(db):
    """Freigaben (Kennwerte-Historie der LST-Quellen, mit Zurücknahme) und Ablehnungen, neueste zuerst:
    [dict(art, am, ebene, gruppe, faktor, n, text, historie_id, zurueck)]."""
    out = []
    for h in kennwerte.historie(db):
        if not str(h.get("quelle") or "").startswith("lst") and h.get("quelle") != "laserzeit_bausteine":
            continue
        if h.get("quelle") == "laserzeit_bausteine" and "LST" not in str(h.get("begruendung") or ""):
            continue
        try:
            gruppe = " · ".join(str(s) for s in json.loads(h.get("schluessel") or "[]"))
        except ValueError:
            gruppe = str(h.get("schluessel") or "")
        out.append(dict(art="zurückgenommen" if h.get("zurueck") else "freigegeben", am=h.get("datum") or "",
                        ebene=EBENE_TEXT.get(h.get("quelle"), "Laserzeit je Baustein"), gruppe=gruppe,
                        faktor=h.get("faktor"), n=h.get("n"), text=h.get("begruendung") or "", historie_id=h["id"],
                        zurueck=h.get("zurueck") or ""))
    for a in db.zeilen(ENTSCHEIDUNGEN.name):
        try:
            gruppe = " · ".join(str(s) for s in json.loads(a.get("schluessel") or "[]"))
        except ValueError:
            gruppe = str(a.get("schluessel") or "")
        out.append(dict(art="abgelehnt", am=a.get("am") or "", ebene=EBENE_TEXT.get(a.get("quelle"), a.get("quelle")),
                        gruppe=gruppe, faktor=a.get("faktor"), n=a.get("n"),
                        text=a.get("grund") or "", historie_id=None, zurueck=""))
    return sorted(out, key=lambda x: (x["am"], x["historie_id"] or 0), reverse=True)


def zuruecksetzen(db, historie_id):
    """Eine Freigabe zurücknehmen (alte Werte, kennwerte.zuruecknehmen). Ergebnis: Anzahl Werte."""
    return kennwerte.zuruecknehmen(db, historie_id)


# ------------------------------------------------------------------ Kalibrierung je Baustein (Einstechen getrennt)
def faelle_bausteine(db, zeilen=None):
    """Fälle für kalibrierung.faelle_bausteine: {Maschine: [dict(angebot, pid, soll, ist, roh, f_laser, rest,
    kategorie)]}; Soll ohne Nebenzeit (steckt nicht in der TRUMPF-Teilezeit), Nebenzeit-Baustein 0."""
    from . import rechnen
    out = {}
    for f in faelle(db, zeilen):
        z = f["zeile"]
        bst, fak = z.get("bausteine") or {}, z.get("faktoren") or {}
        roh = {b: (bst.get(b) or 0.0) / (fak.get(b) or 1.0) for b in rechnen.BAUSTEINE}
        roh["neben"] = 0.0
        summe = sum(bst.get(b) or 0.0 for b in rechnen.BAUSTEINE if b != "neben")
        out.setdefault(f["maschine"] or "", []).append(dict(
            angebot=f"LST {f['programm']}", pid=None, soll=f["soll"], ist=f["ist"], roh=roh, f_laser=z["f_laser"],
            rest=f["soll"] - z["f_laser"] * summe, kategorie=f["kategorie"], lst=True))
    return out


# ------------------------------------------------------------------ Kennwerte-Quellen (gleiche Fälle, gleiche Regeln)
_CACHE = {}


def stand(db):
    """Kurzer Fingerabdruck der Daten, aus denen gelernt wird (für den Zwischenspeicher der Kennwerte-Quellen)."""
    werte = []
    for sql in ("SELECT COUNT(*), MAX(id), MAX(gelesen) FROM lst_teile", f"SELECT COUNT(*), MAX(am) FROM "
                f"{lst_vergleich.ZUORDNUNG.name}", f"SELECT COUNT(*), MAX(am) FROM {ENTSCHEIDUNGEN.name}",
                f"SELECT COUNT(*), MAX(zurueck) FROM {kennwerte.HISTORIE.name}", "SELECT MAX(geaendert) FROM angebote",
                "SELECT COUNT(*) FROM schneiddaten"):
        werte.append(tuple(db.con.execute(sql).fetchone()))
    return (id(db), datetime.date.today().isoformat(), tuple(werte))


def _vorschlaege_gemerkt(db):
    s = stand(db)
    if _CACHE.get("stand") != s:
        _CACHE.clear()
        _CACHE.update(stand=s, v=vorschlaege(db, mit_ruhenden=True))
    return _CACHE["v"]


def _quelle(name):
    def funktion(db):
        out = []
        for v in _vorschlaege_gemerkt(db):
            if v["quelle"] != name or v["status"] != "ok":
                continue
            for f in v["faelle"]:
                soll, ist = (f["soll_schneiden"], f["ist_schneiden"]) if name in (Q_MASCHINE, Q_BEREICH) else \
                    (f["soll"], f["ist"])
                out.append(dict(schluessel=tuple(v["schluessel"]), soll=soll, ist=ist, angebot=f["angebot"] or
                                f"LST {f['programm']}", datum=f["datum"]))
        return out
    return funktion


def _registrieren():
    from . import kalibrierung, nachkalkulation
    anwenden = {Q_MASCHINE: nachkalkulation.anwenden_laserzeit, Q_BEREICH: kalibrierung.anwenden_bereich}
    for q, titel in EBENEN:
        kennwerte.register_quelle(q, titel, _quelle(q), anwenden.get(q))


_registrieren()
