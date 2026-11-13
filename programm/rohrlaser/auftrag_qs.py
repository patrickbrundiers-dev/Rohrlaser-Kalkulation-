"""Qualitätskontrolle, Fertigstellung, Auslieferung und Abschluss (Plan Auftragsworkflow 13.11.2026, Paket 5). Ohne Qt.

Alles sind Ereignisse am Auftrag, nichts wird überschrieben:
  qs_pruefung  je Position: geprüfte Menge, gut, Ausschuss, Nacharbeit, Ergebnis (i.O., Teilweise i.O., n.i.O.,
               Sonderfreigabe), Datum, Prüfer, Dokumente/Fotos; Storno einer falschen Prüfung mit Grund
  lieferung    Versand, Abholung oder eigene Lieferung mit Datum, Mengen je Position, Verpackung, Paletten,
               Lieferscheinnummern und Dokumenten
  dokument     eine Datei (Foto, Prüfbericht, Lieferpapier) im Ordner des Auftrags

Daraus gerechnet:
  QS je Position     „fertig geprüft“, wenn gut ≥ Auftragsmenge oder eine Sonderfreigabe mit Grund vorliegt
  Produktion fertig  alle aktiven Arbeitsgänge der Position fertig, ausgenommen Qualitätskontrolle (kommt aus den
                     Prüfungen) und Verpackung (kommt aus der Auslieferung)
  Auftragsstatus     wird nur vorwärts nachgezogen: Produktion fertig -> Qualitätskontrolle; einzelne Positionen
                     fertig -> Teilweise fertiggestellt; alle fertig -> Fertiggestellt; alles geliefert ->
                     Ausgeliefert. „Fertiggestellt“ ohne erfüllte Bedingungen nur mit Sonderfreigabe (Grund).
  Lieferbar          je Position die i.O. geprüfte Menge minus schon geliefert; mehr nur mit Grund

Eine Prüfung meldet ihre gute Menge auch an den Arbeitsgang „Qualitätskontrolle“, eine Lieferung an „Verpackung“
(Rückmeldung mit Quelle), damit Fortschritt und Seite Produktion stimmen. Beim Abschluss werden die Ist-Werte
(Laserzeit, Ausschuss) in die leeren Felder der Nachkalkulation der Angebote übernommen.
"""
import datetime
import shutil
from pathlib import Path

from . import auftraege as au
from . import auftrag_produktion as ap

IO, TEIL_IO, NIO, SONDER = "i.O.", "Teilweise i.O.", "n.i.O.", "Sonderfreigabe"
ERGEBNISSE = (IO, TEIL_IO, NIO, SONDER)
STORNO = "Storno"
LIEFERARTEN = ("Versand (Spedition / Paket)", "Abholung durch den Kunden", "Eigene Lieferung")
BEREICHE = ("Qualität", "Auslieferung", "Sonstiges")
QS_ERLAUBT = (au.BEREIT, au.PRODUKTION, au.QS, au.TEILWEISE, au.FERTIG)
LIEFERN_ERLAUBT = (au.PRODUKTION, au.QS, au.TEILWEISE, au.FERTIG)
FERTIGMELDEN_ERLAUBT = (au.BEREIT, au.PRODUKTION, au.QS, au.TEILWEISE)
QUELLE_QS, QUELLE_LIEFERUNG = "Qualitätskontrolle", "Auslieferung"
OHNE_PRODUKTION = ("qualität", "verpack")     # Arbeitsgänge, die nicht die Werkstatt zurückmeldet
QS_OFFEN, QS_TEIL, QS_NACHARBEIT, QS_FERTIG, QS_SONDER = (
    "Offen", "Teilweise geprüft", "Nacharbeit", "Geprüft i.O.", "Sonderfreigabe")
EPS = 1e-9


def _art(ag):
    from .auftrag_av import _schluessel
    return _schluessel(ag.get("name"))


def _gang(p, art):
    return next((x for x in p.get("arbeitsgaenge") or () if x.get("aktiv") and _art(x) == art), None)


def _heute():
    return datetime.date.today().isoformat()


def _zahl(w, was):
    v = au._wert("menge", w or 0)
    if v is None or v < 0:
        raise au.AuftragFehler(f"{was}: bitte eine Zahl ab 0 eingeben.")
    return v


def _fmt(x):
    return f"{au._n(x):g}".replace(".", ",")


def _auftrag(db, uid, erlaubt=None, was=""):
    if db.nur_lesen:
        raise au.AuftragFehler(f"Lesemodus – {db.nur_lesen}.")
    a = au.auftrag(db, uid)
    if a is None:
        raise au.AuftragFehler("Den Auftrag gibt es nicht mehr.")
    if erlaubt and a["status"] not in erlaubt:
        raise au.AuftragFehler(f"Auftrag {a['nummer']} steht auf „{a['status']}“. {was}")
    return a


def _position(a, position):
    p = next((x for x in a["positionen"] if x["uid"] == position), None)
    if p is None:
        raise au.AuftragFehler("Die Position gibt es im Auftrag nicht.")
    return p


# ------------------------------------------------------------------ Stand (gerechnet)
def pruefungen(p):
    """Gültige Prüfungen einer Position (ohne stornierte und ohne die Storno-Einträge), nach Zeit."""
    qs = list(p.get("_qs") or ())
    weg = {x.get("storno") for x in qs if x.get("storno")}
    return sorted((x for x in qs if not x.get("storno") and x.get("uid") not in weg), key=lambda x: x.get("am") or "")


def qs_verlauf(p):
    """Alle Prüfungen zum Anzeigen (neueste zuerst), stornierte markiert, Storno-Einträge weggelassen."""
    qs = list(p.get("_qs") or ())
    weg = {x.get("storno") for x in qs if x.get("storno")}
    return [dict(x, storniert=x.get("uid") in weg) for x in sorted(
        (x for x in reversed(qs) if not x.get("storno")), key=lambda x: x.get("am") or "", reverse=True)]


def qs_stand(p):
    """dict(menge, geprueft, gut, ausschuss, nacharbeit, offen, fertig, sonder, status, ergebnis, pruefer, datum)."""
    menge = au._n(p.get("menge"))
    pr = pruefungen(p)
    summe = {f: sum(au._n(x.get(f)) for x in pr) for f in ("geprueft", "gut", "ausschuss", "nacharbeit")}
    sonder = any(x.get("ergebnis") == SONDER for x in pr)
    fertig = sonder or (bool(pr) and summe["gut"] >= menge - EPS)
    letzte = pr[-1] if pr else {}
    if not pr:
        status = QS_OFFEN
    elif sonder:
        status = QS_SONDER
    elif fertig:
        status = QS_FERTIG
    elif letzte.get("ergebnis") in (NIO, TEIL_IO) and au._n(letzte.get("nacharbeit")) > 0:
        status = QS_NACHARBEIT
    else:
        status = QS_TEIL
    return dict(menge=menge, offen=max(0.0, menge - summe["gut"]), fertig=fertig, sonder=sonder, status=status,
                ergebnis=letzte.get("ergebnis") or "", pruefer=letzte.get("pruefer") or "",
                datum=letzte.get("datum") or "", anzahl=len(pr), **summe)


def produktion_offen(p):
    """Namen der Arbeitsgänge der Werkstatt, die an der Position noch nicht fertig sind."""
    zeilen, _ = ap.position_stand(p)
    return [x["name"] for x, z in zeilen if _art(x) not in OHNE_PRODUKTION and z["status"] != ap.FERTIG]


def position_fertig(p):
    return not produktion_offen(p) and qs_stand(p)["fertig"]


def lieferungen(a):
    """Gültige Lieferungen (ohne stornierte), nach Zeit."""
    alle = list(a["kopf"].get("_lieferungen") or ())
    weg = {x.get("storno") for x in alle if x.get("storno")}
    return sorted((x for x in alle if not x.get("storno") and x.get("uid") not in weg), key=lambda x: x.get("am") or "")


def geliefert(a):
    out = {}
    for x in lieferungen(a):
        for pos, m in (x.get("mengen") or {}).items():
            out[pos] = out.get(pos, 0.0) + au._n(m)
    return out


def liefer_stand(a):
    """Je Position dict(uid, nr, artikel, bezeichnung, menge, freigegeben (i.O. geprüft bzw. Sonderfreigabe), geliefert,
    offen (noch zu liefern), lieferbar (freigegeben und noch nicht geliefert))."""
    g = geliefert(a)
    out = []
    for p in a["positionen"]:
        q = qs_stand(p)
        menge = q["menge"]
        frei = menge if q["sonder"] else min(menge, q["gut"]) if menge > 0 else q["gut"]
        gel = g.get(p["uid"], 0.0)
        out.append(dict(uid=p["uid"], nr=p["nr"], artikel=p.get("artikel") or "",
                        bezeichnung=p.get("bezeichnung") or "", menge=menge, freigegeben=frei, geliefert=gel,
                        offen=max(0.0, menge - gel), lieferbar=max(0.0, frei - gel)))
    return out


def alles_geliefert(a):
    st = liefer_stand(a)
    return bool(st) and all(z["offen"] <= EPS for z in st)


def bedingungen(a):
    """Prüfliste für „Fertiggestellt“: [(Punkt, erfüllt, Text)]."""
    prod = [(p, produktion_offen(p)) for p in a["positionen"]]
    qs = [(p, qs_stand(p)) for p in a["positionen"]]
    p_offen = [f"Pos. {p['nr']}: {', '.join(o)}" for p, o in prod if o]
    q_offen = [f"Pos. {p['nr']}: {_fmt(q['gut'])} von {_fmt(q['menge'])} i.O." for p, q in qs if not q["fertig"]]
    return [("Produktion", not p_offen and bool(prod),
             "alle Arbeitsgänge fertig" if not p_offen else "offen: " + "; ".join(p_offen)),
            ("Qualitätskontrolle", not q_offen and bool(qs),
             "alle Positionen geprüft" if not q_offen else "offen: " + "; ".join(q_offen))]


def fertig_moeglich(a):
    return all(ok for _, ok, _ in bedingungen(a))


def _vor(alt, neu):
    return au.STATUS_LISTE.index(neu) > au.STATUS_LISTE.index(alt or au.NEU)


def status_nachziehen(db, uid):
    """Auftragsstatus aus Produktion, Prüfungen und Lieferungen vorwärts nachziehen (innerhalb der laufenden
    Transaktion). Nie zurück. Ergebnis: neuer Status oder None."""
    a = au.auftrag(db, uid)
    if a is None or not a["positionen"]:
        return None
    st, neu, grund = a["status"], None, ""
    if st in (au.BEREIT, au.PRODUKTION, au.QS, au.TEILWEISE):
        fertige = [p for p in a["positionen"] if position_fertig(p)]
        if len(fertige) == len(a["positionen"]):
            neu, grund = au.FERTIG, "alle Positionen produziert und geprüft"
        elif fertige:
            neu, grund = au.TEILWEISE, f"{len(fertige)} von {len(a['positionen'])} Positionen fertig"
        elif all(not produktion_offen(p) for p in a["positionen"]) and any(
                p.get("arbeitsgaenge") for p in a["positionen"]):
            neu, grund = au.QS, "Produktion fertig gemeldet"
    if neu and _vor(st, neu):
        au._ereignis(db, uid, au.STATUS, feld="status", alt=st, neu=neu, bemerkung=f"automatisch ({grund})")
        st = neu
    else:
        neu = None
    if st == au.FERTIG and alles_geliefert(au.auftrag(db, uid)):
        au._ereignis(db, uid, au.STATUS, feld="status", alt=st, neu=au.AUSGELIEFERT,
                     bemerkung="automatisch (alles geliefert)")
        neu = au.AUSGELIEFERT
    return neu


# ------------------------------------------------------------------ Dokumente
def auftragsordner(basis, nummer):
    """Ordner des Auftrags in der Ablage: <Angebotsordner>/Auftrag <Nummer> (oder None ohne Ablage)."""
    return Path(basis) / f"Auftrag {nummer}" if basis else None


def _ablegen(ordner, dateien, bereich):
    """Dateien in <ordner>/<bereich> kopieren (Namen nie überschreiben). Ohne Ordner bleibt der Pfad wie er ist.
    Ergebnis: [dict(name, pfad)]."""
    out = []
    for d in dateien or ():
        q = Path(d)
        if not q.is_file():
            raise au.AuftragFehler(f"Die Datei {q.name} gibt es nicht.")
        if ordner is None:
            out.append(dict(name=q.name, pfad=str(q)))
            continue
        ziel_ordner = Path(ordner) / bereich
        ziel_ordner.mkdir(parents=True, exist_ok=True)
        ziel, i = ziel_ordner / q.name, 2
        while ziel.exists():
            ziel = ziel_ordner / f"{q.stem} ({i}){q.suffix}"
            i += 1
        shutil.copy2(q, ziel)
        out.append(dict(name=ziel.name, pfad=str(ziel)))
    return out


def dokumente_ablegen(db, uid, dateien, bereich="Sonstiges", ordner=None, bemerkung=""):
    """Dateien (Fotos, Prüfberichte, Lieferpapiere) zum Auftrag ablegen. Ergebnis: [dict(name, pfad)]."""
    _auftrag(db, uid)
    if bereich not in BEREICHE:
        raise au.AuftragFehler(f"Bereich „{bereich}“ gibt es nicht.")
    liste_ = _ablegen(ordner, dateien, bereich)
    with db.con:
        for d in liste_:
            au._ereignis(db, uid, au.DOKUMENT, feld=bereich, neu=d["name"], daten=dict(d, bereich=bereich),
                         bemerkung=bemerkung)
    return liste_


def dokumente(a, bereich=None):
    return [d for d in a["kopf"].get("_dokumente") or () if bereich is None or d.get("bereich") == bereich]


# ------------------------------------------------------------------ Qualitätskontrolle
def pruefung_erfassen(db, uid, position, geprueft, gut, ausschuss=0, nacharbeit=0, ergebnis=None, pruefer="",
                      datum=None, bemerkung="", dokumente_=(), ordner=None):
    """Prüfung einer Position erfassen. Gut + Ausschuss + Nacharbeit = geprüfte Menge; Sonderfreigabe nur mit Grund
    (Bemerkung). Ergebnis: uid der Prüfung."""
    a = _auftrag(db, uid, QS_ERLAUBT, "Prüfen geht ab „Produktionsbereit“.")
    p = _position(a, position)
    gp, g = _zahl(geprueft, "Geprüft"), _zahl(gut, "Gut")
    aus, na = _zahl(ausschuss, "Ausschuss"), _zahl(nacharbeit, "Nacharbeit")
    if ergebnis not in (None, "") and ergebnis not in ERGEBNISSE:
        raise au.AuftragFehler(f"Ergebnis „{ergebnis}“ gibt es nicht.")
    if ergebnis == SONDER:
        if not str(bemerkung or "").strip():
            raise au.AuftragFehler("Sonderfreigabe nur mit Grund (Bemerkung, steht in der Historie).")
    elif gp <= 0:
        raise au.AuftragFehler("Bitte die geprüfte Menge angeben.")
    if gp > 0 and abs(g + aus + na - gp) > 1e-6:
        raise au.AuftragFehler(f"Gut ({_fmt(g)}) + Ausschuss ({_fmt(aus)}) + Nacharbeit ({_fmt(na)}) muss die geprüfte "
                               f"Menge ({_fmt(gp)}) ergeben.")
    if not ergebnis:
        ergebnis = IO if not aus and not na else (TEIL_IO if g > 0 else NIO)
    wer, name = au.benutzer(db)
    docs = _ablegen(ordner, dokumente_, "Qualität")
    daten = dict(geprueft=gp, gut=g, ausschuss=aus, nacharbeit=na, ergebnis=ergebnis,
                 pruefer=str(pruefer or "").strip() or name or wer, datum=str(datum or "") or _heute(), dokumente=docs)
    with db.con:
        e = au._ereignis(db, uid, au.QS_PRUEFUNG, ziel=position, neu=ergebnis, daten=daten, bemerkung=bemerkung)
        for d in docs:
            au._ereignis(db, uid, au.DOKUMENT, feld="Qualität", neu=d["name"], daten=dict(d, bereich="Qualität"),
                         bemerkung=f"Prüfung Pos. {p['nr']}")
        ag = _gang(p, "qualität")
        if ag is not None and (g > 0 or aus > 0 or ergebnis == SONDER):
            typ = ap.ABGESCHLOSSEN if ergebnis == SONDER else ap.TEILMENGE
            au._ereignis(db, uid, au.RUECKMELDUNG, ziel=position, feld=ag["uid"], neu=typ, alt=ag["name"],
                         daten={k: v for k, v in dict(menge=g or None, ausschuss=aus or None, quelle=QUELLE_QS,
                                                       qs=e["uid"]).items() if v},
                         bemerkung="aus der Qualitätsprüfung")
        status_nachziehen(db, uid)
    return e["uid"]


def pruefung_stornieren(db, uid, position, qs_uid, grund):
    """Falsche Prüfung unwirksam machen (mit Grund). Der Auftragsstatus geht dadurch nicht automatisch zurück."""
    a = _auftrag(db, uid)
    p = _position(a, position)
    if not any(x.get("uid") == qs_uid for x in pruefungen(p)):
        raise au.AuftragFehler("Die Prüfung gibt es nicht (oder sie ist schon storniert).")
    if not str(grund or "").strip():
        raise au.AuftragFehler("Storno nur mit Grund (steht in der Historie).")
    with db.con:
        au._ereignis(db, uid, au.QS_PRUEFUNG, ziel=position, neu=STORNO, daten=dict(storno=qs_uid), bemerkung=grund)
        ag = _gang(p, "qualität")
        for r in ap.rueckmeldungen(p, ag["uid"] if ag else None):
            if (r.get("daten") or {}).get("qs") == qs_uid and ag is not None:
                au._ereignis(db, uid, au.RUECKMELDUNG, ziel=position, feld=ag["uid"], neu=ap.STORNO, alt=ag["name"],
                             daten=dict(bezug=r["uid"], quelle=QUELLE_QS), bemerkung=grund)
    return True


# ------------------------------------------------------------------ Fertigstellung, Auslieferung, Abschluss
def fertigmelden(db, uid, grund=""):
    """Auftrag „Fertiggestellt“: bei erfüllten Bedingungen sofort, sonst nur mit Sonderfreigabe (Grund)."""
    a = _auftrag(db, uid, FERTIGMELDEN_ERLAUBT, "Fertigmelden geht ab „Produktionsbereit“.")
    ok = fertig_moeglich(a)
    if not ok and not str(grund or "").strip():
        offen = "; ".join(t for _, erfuellt, t in bedingungen(a) if not erfuellt)
        raise au.AuftragFehler(f"Noch nicht alles fertig ({offen}). Fertigmelden geht dann nur mit Grund "
                               "(Sonderfreigabe).")
    with db.con:
        au._ereignis(db, uid, au.STATUS, feld="status", alt=a["status"], neu=au.FERTIG,
                     bemerkung=("Sonderfreigabe: " + str(grund).strip()) if not ok else (grund or "fertig gemeldet"))
        status_nachziehen(db, uid)
    return True


def _angebots_position(db, pos_uid):
    """(angebot_id, positions_id) einer übernommenen Position oder None."""
    r = db.con.execute("SELECT angebot_id, id FROM positionen WHERE uid=?", (pos_uid,)).fetchone()
    if r:
        return r[0], r[1]
    try:
        a, p = str(pos_uid).split("-")
        return int(a), int(p)
    except ValueError:
        return None


def liefern(db, uid, mengen, art=LIEFERARTEN[0], datum=None, verpackung="", paletten=0, bemerkung="", dokumente_=(),
            ordner=None, lieferschein=True, grund=""):
    """Lieferung erfassen: {Positions-uid: Menge}. Mehr als die i.O. geprüfte Menge nur mit Grund; mehr als bestellt
    nie. lieferschein: für Positionen aus Angeboten den Lieferschein des Angebots anlegen (lieferschein.py).
    Ergebnis: dict(uid, lieferscheine, hinweise)."""
    a = _auftrag(db, uid, LIEFERN_ERLAUBT, "Liefern geht, sobald die Produktion läuft.")
    if art not in LIEFERARTEN:
        raise au.AuftragFehler(f"Lieferart „{art}“ gibt es nicht.")
    st = {z["uid"]: z for z in liefer_stand(a)}
    zeilen = {}
    for pos, m in (mengen or {}).items():
        m = _zahl(m, "Menge")
        if m <= 0:
            continue
        z = st.get(pos)
        if z is None:
            raise au.AuftragFehler("Die Position gibt es im Auftrag nicht.")
        if z["menge"] > 0 and m > z["offen"] + 1e-6:
            raise au.AuftragFehler(f"Pos. {z['nr']}: {_fmt(m)} Stück, offen sind nur {_fmt(z['offen'])}.")
        if m > z["lieferbar"] + 1e-6 and not str(grund or "").strip():
            raise au.AuftragFehler(f"Pos. {z['nr']}: nur {_fmt(z['lieferbar'])} Stück sind i.O. geprüft und noch nicht "
                                   "geliefert. Mehr nur mit Grund.")
        zeilen[pos] = m
    if not zeilen:
        raise au.AuftragFehler("Bitte mindestens eine Menge eingeben.")
    pal = int(_zahl(paletten, "Paletten"))
    docs = _ablegen(ordner, dokumente_, "Auslieferung")
    scheine, hinweise = [], []
    if lieferschein:
        from . import lieferschein as ls
        je_angebot = {}
        for pos, m in zeilen.items():
            ap_ = _angebots_position(db, pos)
            if ap_ and db.angebot(ap_[0]):
                je_angebot.setdefault(ap_[0], {})[ap_[1]] = m
        for aid, m in je_angebot.items():
            try:
                scheine.append(ls.anlegen(db, aid, m, bemerkung=f"Auftrag {a['nummer']}")["nummer"])
            except (ValueError, OSError) as ex:
                hinweise.append(f"Lieferschein Angebot {(db.angebot(aid) or {}).get('nummer') or aid}: {ex}")
    daten = dict(art=art, datum=str(datum or "") or _heute(), mengen=zeilen, verpackung=str(verpackung or ""),
                 paletten=pal, lieferscheine=scheine, dokumente=docs, grund=str(grund or "").strip() or None)
    with db.con:
        e = au._ereignis(db, uid, au.LIEFERUNG, neu=art, daten={k: v for k, v in daten.items() if v is not None},
                         bemerkung=bemerkung)
        for d in docs:
            au._ereignis(db, uid, au.DOKUMENT, feld="Auslieferung", neu=d["name"],
                         daten=dict(d, bereich="Auslieferung"), bemerkung=art)
        for p in a["positionen"]:
            ag = _gang(p, "verpack")
            if ag is not None and p["uid"] in zeilen:
                au._ereignis(db, uid, au.RUECKMELDUNG, ziel=p["uid"], feld=ag["uid"], neu=ap.TEILMENGE,
                             alt=ag["name"], daten=dict(menge=zeilen[p["uid"]], quelle=QUELLE_LIEFERUNG,
                                                        lieferung=e["uid"]), bemerkung="aus der Auslieferung")
        status_nachziehen(db, uid)
    return dict(uid=e["uid"], lieferscheine=scheine, hinweise=hinweise)


def lieferung_stornieren(db, uid, lieferung_uid, grund):
    """Falsch erfasste Lieferung unwirksam machen (mit Grund). Lieferscheine bleiben bestehen (Nummernkreis)."""
    a = _auftrag(db, uid)
    if not any(x["uid"] == lieferung_uid for x in lieferungen(a)):
        raise au.AuftragFehler("Die Lieferung gibt es nicht (oder sie ist schon storniert).")
    if not str(grund or "").strip():
        raise au.AuftragFehler("Storno nur mit Grund (steht in der Historie).")
    with db.con:
        au._ereignis(db, uid, au.LIEFERUNG, neu=STORNO, daten=dict(storno=lieferung_uid), bemerkung=grund)
        for p in a["positionen"]:
            ag = _gang(p, "verpack")
            for r in ap.rueckmeldungen(p, ag["uid"] if ag else None):
                if ag is not None and (r.get("daten") or {}).get("lieferung") == lieferung_uid:
                    au._ereignis(db, uid, au.RUECKMELDUNG, ziel=p["uid"], feld=ag["uid"], neu=ap.STORNO,
                                 alt=ag["name"], daten=dict(bezug=r["uid"], quelle=QUELLE_LIEFERUNG), bemerkung=grund)
    return True


def abschliessen(db, uid, grund=""):
    """Auftrag „Abgeschlossen“: nach der Auslieferung, sonst nur mit Grund. Übernimmt die Ist-Werte in die leeren
    Felder der Nachkalkulation. Ergebnis: Anzahl vorbelegter Felder."""
    a = _auftrag(db, uid)
    if a["status"] == au.ABGESCHLOSSEN:
        return 0
    if a["status"] != au.AUSGELIEFERT and not str(grund or "").strip():
        raise au.AuftragFehler(f"Auftrag {a['nummer']} steht auf „{a['status']}“. Abschließen vor der Auslieferung "
                               "geht nur mit Grund.")
    with db.con:
        au._ereignis(db, uid, au.STATUS, feld="status", alt=a["status"], neu=au.ABGESCHLOSSEN,
                     bemerkung=str(grund or "").strip() or "abgeschlossen")
    return nachkalkulation_vorbelegen(db, uid)


# ------------------------------------------------------------------ Soll/Ist und Nachkalkulation
def soll_ist(a):
    """Je Position und Arbeitsgang Soll- und Istzeit, gute Menge und Ausschuss (für den Abschluss und die
    Nachkalkulation): [dict(pos, artikel, name, sollzeit, istzeit, abweichung, gut, ausschuss, angebot)]."""
    out = []
    for p in a["positionen"]:
        zeilen, _ = ap.position_stand(p)
        for x, z in zeilen:
            soll = au._n(x.get("sollzeit"))
            out.append(dict(pos=p["nr"], artikel=p.get("artikel") or "", name=x["name"], art=_art(x), sollzeit=soll,
                            istzeit=z["istzeit"], abweichung=(z["istzeit"] - soll) / soll if soll > 0 and z["istzeit"]
                            else None, gut=z["gut"], ausschuss=z["ausschuss"], angebot=p.get("angebot")))
    return out


def nachkalkulation_werte(a):
    """{Angebots-uid: {laser_h, ausschuss_stk}} aus den Rückmeldungen (nur, was wirklich gemeldet ist)."""
    out = {}
    for z in soll_ist(a):
        if not z["angebot"]:
            continue
        d = out.setdefault(z["angebot"], {})
        if z["art"] == "laser" and z["istzeit"] > 0:
            d["laser_h"] = round(d.get("laser_h", 0.0) + z["istzeit"] / 60, 2)
    for p in a["positionen"]:
        if not p.get("angebot"):
            continue
        aus = qs_stand(p)["ausschuss"] + sum(z["ausschuss"] for x, z in ap.position_stand(p)[0]
                                             if _art(x) != "qualität")
        if aus > 0:
            d = out.setdefault(p["angebot"], {})
            d["ausschuss_stk"] = d.get("ausschuss_stk", 0.0) + aus
    return out


def nachkalkulation_vorbelegen(db, uid):
    """Ist-Werte in die LEEREN Felder der Nachkalkulation der Angebote schreiben (von Hand Eingetragenes bleibt).
    Ergebnis: Anzahl geschriebener Felder."""
    a = au.auftrag(db, uid)
    if a is None or db.nur_lesen:
        return 0
    n = 0
    for ang_uid, werte in nachkalkulation_werte(a).items():
        aid = au.angebot_id(db, ang_uid)
        kopf = db.angebot(aid) if aid else None
        if not kopf:
            continue
        ist = dict(kopf.get("nachkalkulation") or {})
        neu = {k: v for k, v in werte.items() if ist.get(k) in (None, "")}
        if not neu:
            continue
        ist.update(neu)
        ist["aus_auftrag"] = a["nummer"]
        ist.setdefault("am", datetime.datetime.now().isoformat(timespec="seconds"))
        db.nachkalkulation_speichern(aid, ist)
        n += len(neu)
    return n


# ------------------------------------------------------------------ Historie
def historie_zeile(db, e):
    """feld/neu einer Zeile der Historie für qs_pruefung, lieferung, dokument."""
    d = e.get("daten") or {}
    if e["art"] == au.QS_PRUEFUNG:
        p = db.con.execute("SELECT daten FROM auftrag_positionen WHERE uid=?", (e.get("ziel"),)).fetchone()
        pd = au._laden(p[0], {}) if p else {}
        feld = f"Pos. {pd.get('_nr') or '?'} {pd.get('artikel') or ''}".strip()
        if d.get("storno"):
            return dict(feld=feld, neu="Prüfung storniert")
        werte = [f"{t} {_fmt(d.get(k))}" for k, t in (("geprueft", "geprüft"), ("gut", "gut"),
                                                      ("ausschuss", "Ausschuss"), ("nacharbeit", "Nacharbeit"))
                 if au._n(d.get(k))]
        return dict(feld=feld, neu=" · ".join(werte + [d.get("ergebnis") or "", d.get("pruefer") or ""]).strip(" ·"))
    if e["art"] == au.LIEFERUNG:
        if d.get("storno"):
            return dict(feld="", neu="Lieferung storniert")
        nr = {r[0]: r[1] for r in db.con.execute("SELECT uid, nr FROM auftrag_positionen WHERE auftrag=?",
                                                 (e["auftrag"],))}
        teile = [f"Pos. {nr.get(k, '?')}: {_fmt(m)}" for k, m in (d.get("mengen") or {}).items()]
        return dict(feld=d.get("art") or "", neu=" · ".join(teile + list(d.get("lieferscheine") or ())
                                                            + ([d["datum"]] if d.get("datum") else [])))
    return dict(feld=d.get("bereich") or e.get("feld") or "", neu=d.get("name") or e.get("neu") or "")
