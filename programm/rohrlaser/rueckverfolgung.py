"""Rückverfolgung im Stangenplan (Plan PROfirst-/LogiTRACE-Handbücher 12.11.2026, I1 und I2).

I1 Teil in früheren Stangenplänen finden: Suche nach Artikelnummer oder Bezeichnung über alle beauftragten Angebote
mit Schnittplan, mit Datum, Menge und Stangennummern. Doppelklick öffnet das alte Angebot (dort neu einplanen). Die
Wiederholteile (wiederholteile.py) finden nur frühere Angebote; hier geht es um den geschnittenen Stangenplan.

I2 Offene Menge je Teil: Im Reiter Fertigung „Stangen melden …“ bucht je geschnittener Stange die Teile darauf als
Rückmeldung des ersten Arbeitsschritts (Vorgabe „Geschnitten“, Tabelle rueckmeldungen, Code „STANGE n“). Jede Stange
zählt nur einmal. offen() zeigt je Position, was noch fehlt; restplan() plant nur den Rest neu (eigene Rechnung, das
Angebot und seine Preise bleiben unverändert)."""
import re

from . import etiketten, rechnen

CODE = "STANGE"


def _text(w):
    return str(w or "").strip()


# ------------------------------------------------------------------ I1
def suchen(db, text, nur_beauftragt=True, grenze=200):
    """Treffer [{angebot_id, nummer, datum, kunde, vorgang, pos, artikel, bezeichnung, stueck, profil, stangen
    (Nummern), anzahl_stangen}] neueste zuerst; leere Suche = []."""
    t = _text(text)
    if len(t) < 2:
        return []
    muster = f"%{t}%"
    sql = ("SELECT DISTINCT a.id, a.datum FROM positionen p JOIN angebote a ON a.id=p.angebot_id WHERE "
           "(p.artikel LIKE ? OR p.bezeichnung LIKE ?) AND a.ergebnis IS NOT NULL"
           + (" AND a.vorgang='Beauftragt'" if nur_beauftragt else "") + " ORDER BY a.datum DESC, a.id DESC")
    ids = [r[0] for r in db.con.execute(sql, (muster, muster)).fetchall()][:grenze]
    out, klein = [], t.lower()
    for aid in ids:
        a = db.angebot(aid)
        if not a or not a.get("ergebnis"):
            continue
        pos = db.positionen(aid)
        stangen = (a["ergebnis"] or {}).get("stangen") or ()
        for i, p in enumerate(pos):
            if klein not in f"{_text(p.get('artikel'))} {_text(p.get('bezeichnung'))}".lower():
                continue
            nrs = sorted({s["nr"] for s in stangen for x in s.get("teile") or () if x.get("index") == i})
            out.append(dict(angebot_id=aid, nummer=a.get("nummer"), datum=a.get("datum"), kunde=a.get("kunde"),
                            vorgang=a.get("vorgang"), pos=p.get("pos"), artikel=p.get("artikel"),
                            bezeichnung=p.get("bezeichnung"), stueck=p.get("stueck"), profil=p.get("profil_id"),
                            stangen=nrs, anzahl_stangen=len(nrs)))
    return out


def stangen_text(nrs):
    """[1, 2, 3, 5] -> '1–3, 5'."""
    teile, nrs = [], sorted(set(nrs))
    i = 0
    while i < len(nrs):
        j = i
        while j + 1 < len(nrs) and nrs[j + 1] == nrs[j] + 1:
            j += 1
        teile.append(str(nrs[i]) if i == j else f"{nrs[i]}–{nrs[j]}")
        i = j + 1
    return ", ".join(teile)


# ------------------------------------------------------------------ I2
def nummern_lesen(text):
    """'1-3, 5; 8' -> [1, 2, 3, 5, 8]; ValueError bei unlesbarem Text."""
    out = []
    for teil in re.split(r"[,;\s]+", _text(text)):
        if not teil:
            continue
        m = re.fullmatch(r"(\d+)\s*[-–]\s*(\d+)", teil)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            out += list(range(min(a, b), max(a, b) + 1))
        elif teil.isdigit():
            out.append(int(teil))
        else:
            raise ValueError(f"„{teil}“ ist keine Stangennummer")
    return sorted(set(out))


def gemeldet(db, angebot_id):
    """Nummern der schon gemeldeten Stangen."""
    out = set()
    for (code,) in db.con.execute("SELECT code FROM rueckmeldungen WHERE angebot_id=? AND code LIKE ?",
                                  (angebot_id, CODE + " %")):
        try:
            out.add(int(str(code).split()[1]))
        except (IndexError, ValueError):
            pass
    return out


def stangen_melden(db, angebot_id, nummern, wer=None):
    """Teile der Stangen (Nummern im Schnittplan) als geschnitten buchen. Ergebnis: dict(gemeldet=[Nummern],
    doppelt=[schon gemeldet], unbekannt=[nicht im Plan], teile={Positions-ID: Stück}, text)."""
    from .datenbank import Lesemodus
    if db.nur_lesen:
        raise Lesemodus(f"Lesemodus – {db.nur_lesen}.")
    a = db.angebot(angebot_id)
    stangen = {s["nr"]: s for s in ((a or {}).get("ergebnis") or {}).get("stangen") or ()}
    pos = db.positionen(angebot_id)
    schritt = etiketten.schritte(db)[0]
    schon = gemeldet(db, angebot_id)
    neu, doppelt, unbekannt, teile = [], [], [], {}
    wer = wer if wer is not None else (db.einstellung("benutzer_kuerzel") or "")
    with db.con:
        for nr in nummern:
            if nr not in stangen:
                unbekannt.append(nr)
                continue
            if nr in schon:
                doppelt.append(nr)
                continue
            je = {}
            for t in stangen[nr].get("teile") or ():
                i = t.get("index", -1)
                if 0 <= i < len(pos):
                    je[i] = je.get(i, 0) + 1
            for i, n in je.items():
                p = pos[i]
                db.con.execute("INSERT INTO rueckmeldungen (angebot_id, position_id, pos, schritt, menge, am, wer, code) "
                               "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               (angebot_id, p["id"], etiketten._pos_text(p.get("pos")), schritt, n, etiketten._jetzt(),
                                wer, f"{CODE} {nr}"))
                teile[p["id"]] = teile.get(p["id"], 0) + n
            neu.append(nr)
            schon.add(nr)
    text = (f"{len(neu)} Stange(n) gemeldet ({sum(teile.values())} Teile „{schritt}“)" if neu else "Nichts gemeldet")
    if doppelt:
        text += f"; schon gemeldet: {stangen_text(doppelt)}"
    if unbekannt:
        text += f"; nicht im Schnittplan: {stangen_text(unbekannt)}"
    return dict(gemeldet=neu, doppelt=doppelt, unbekannt=unbekannt, teile=teile, text=text + ".")


def offen(db, angebot_id):
    """Je aktiver Position: [{id, pos, artikel, stueck, geschnitten, offen}] (erster Arbeitsschritt der
    Rückmeldung, Stangen und Scans zusammen)."""
    schritt = etiketten.schritte(db)[0]
    out = []
    for z in etiketten.stand_je_position(db, angebot_id):
        g = z["schritte"].get(schritt, 0)
        out.append(dict(id=z["id"], pos=z["pos"], artikel=z.get("artikel"), stueck=z["stueck"] or 0, geschnitten=g,
                        offen=max((z["stueck"] or 0) - g, 0)))
    return out


def restplan(db, angebot_id):
    """Schnittplan nur für die offenen Mengen: (kopf, positionen mit offener Stückzahl, ergebnis) oder None, wenn
    nichts mehr offen ist. Rechnet mit der Preisgrundlage des Angebots; speichert nichts."""
    o = {z["id"]: z["offen"] for z in offen(db, angebot_id)}
    a = db.angebot(angebot_id)
    if a is None:
        return None
    rest = []
    for p in db.positionen(angebot_id):
        n = o.get(p["id"])
        if n:
            rest.append(dict(p, stueck=n))
    if not rest:
        return None
    k, tab = rechnen.preisbasis_anwenden(a, db.kontext(), db.tabellen())
    einst = rechnen.einstellungen_angebot(a, db.einstellungen())
    return a, rest, rechnen.optimieren(a, rest, k, tab, einst)
