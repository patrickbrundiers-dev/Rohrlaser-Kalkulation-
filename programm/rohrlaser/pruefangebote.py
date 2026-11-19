"""Prüfangebote (Plan Angebotskalkulation 16.11.2026, Paket K4, F5a; erledigt QA-002 ohne Dateien). Ohne Qt.

Der Hauptadmin hakt bestätigte Angebote als „Prüfangebot“ an. Dabei merkt sich das Programm die Referenz: Verkaufspreis
und Kostenarten, wie das Angebot heute rechnet, dazu die Preise und Zeiten (Preis- und Zeitbasis), mit denen es
rechnet (Zusatzdaten 'pruefangebot'). Nach jedem Update rechnet das Programm alle Prüfangebote mit genau dieser Basis
neu und zeigt alter Preis, neuer Preis, Abweichung und die Kostenarten, die sich am meisten bewegt haben. Ab
MELDEN_AB (2 %) kommt nach dem Update eine Meldung. Gespeichert wird dabei nichts am Angebot; festgeschriebene
Angebote bleiben, wie sie sind. „Als neue Referenz übernehmen“ setzt die Referenz bewusst neu (z. B. nach einer
gewollten Änderung der Stammdaten).

Abweichungen kommen aus Programm-Updates (Rechenwege) oder aus Stammdaten, die nicht in der Preis- und Zeitbasis
stehen (z. B. Zusatzarbeiten, Einstellungen).
"""
import datetime

from . import preis_simulator, rechnen

SCHLUESSEL = "pruefangebot"
MELDEN_AB = 0.02
VERSION_EINST = "pruefangebote_version"
BAUSTEINE = 3          # so viele Kostenarten nennt eine Zeile


def ist_pruefangebot(db, angebot_id):
    return isinstance(db.zusatz(angebot_id, SCHLUESSEL), dict)


def ids(db):
    return [r[0] for r in db.con.execute("SELECT id FROM angebote WHERE zusatz LIKE '%pruefangebot%'")
            if ist_pruefangebot(db, r[0])]


def _rechnen(db, a, ref=None):
    """summen des Angebots, mit der Basis der Referenz (falls angegeben)."""
    a2 = dict(a)
    if ref:
        a2["preisbasis"] = ref.get("preisbasis")
        a2["zeitbasis"] = ref.get("zeitbasis")
    pos = db.positionen(a["id"])
    k, tab, e = preis_simulator.grundlage(db, a2)
    from . import dauermerker
    with dauermerker.ohne():        # Prüfrechnung: der Rechenweg selbst, nicht der Angebots-Cache
        return rechnen.kalkulation(a2, pos, a["ergebnis"], k, tab, e)[1], (k, tab, pos)


def _kosten(summen):
    return {schl: round(float(summen.get(schl) or 0), 2) for _, schl, _ in rechnen.KOSTENARTEN}


def markieren(db, angebot_id, version, heute=None):
    """Angebot als Prüfangebot mit Referenz von heute. ValueError ohne Schnittplan oder nicht rechenbar."""
    a = db.angebot(angebot_id)
    if not a or a.get("fremd"):
        raise ValueError("Nur eigene Angebote können Prüfangebot sein.")
    if not (a.get("ergebnis") or {}).get("stangen"):
        raise ValueError(f"Angebot {a.get('nummer')}: bitte zuerst optimieren (kein Schnittplan).")
    try:
        summen, (k, tab, pos) = _rechnen(db, a)
    except (ValueError, KeyError, TypeError, ZeroDivisionError) as e:
        raise ValueError(f"Angebot {a.get('nummer')} lässt sich nicht rechnen: {e}") from e
    basis = a.get("preisbasis") if isinstance(a.get("preisbasis"), dict) else rechnen.preisbasis_aus(a, pos, k, tab)
    zb = a.get("zeitbasis") if isinstance(a.get("zeitbasis"), dict) else rechnen.zeitbasis_aus(a.get("maschine"), k,
                                                                                               tab)
    ref = dict(seit=(heute or datetime.date.today()).isoformat(), version=version, preisbasis=basis, zeitbasis=zb)
    summen, _ = _rechnen(db, a, ref)
    ref.update(verkauf=round(float(summen["verkauf"]), 2), kosten=_kosten(summen))
    db.zusatz_setzen(angebot_id, SCHLUESSEL, ref)
    return ref


def aufheben(db, angebot_id):
    db.zusatz_setzen(angebot_id, SCHLUESSEL, None)


def pruefen(db, nur=None):
    """[dict(id, nummer, kunde, alt, neu, abweichung, prozent, bausteine [(Text, alt, neu)], seit, version, fehler)]
    nach |Abweichung| absteigend; nur = Angebots-IDs (None = alle Prüfangebote)."""
    out = []
    for aid in (nur if nur is not None else ids(db)):
        a = db.angebot(aid)
        ref = db.zusatz(aid, SCHLUESSEL) if a else None
        if not isinstance(ref, dict):
            continue
        zeile = dict(id=aid, nummer=a.get("nummer"), kunde=a.get("kunde") or "", alt=ref.get("verkauf"), neu=None,
                     abweichung=None, prozent=None, bausteine=[], seit=ref.get("seit") or "",
                     version=ref.get("version") or "", fehler="")
        try:
            summen, _ = _rechnen(db, a, ref)
        except (ValueError, KeyError, TypeError, ZeroDivisionError) as e:
            zeile["fehler"] = f"nicht rechenbar: {e}"
            out.append(zeile)
            continue
        neu = round(float(summen["verkauf"]), 2)
        alt_k, neu_k = ref.get("kosten") or {}, _kosten(summen)
        texte = {schl: text for text, schl, fett in rechnen.KOSTENARTEN if not fett}
        diff = sorted(((texte[s], alt_k.get(s, 0.0), neu_k[s]) for s in texte if abs(neu_k[s] - alt_k.get(s, 0.0))
                       >= 0.01), key=lambda x: -abs(x[2] - x[1]))
        zeile.update(neu=neu, abweichung=round(neu - (zeile["alt"] or 0), 2),
                     prozent=(neu / zeile["alt"] - 1) if zeile["alt"] else None, bausteine=diff[:BAUSTEINE])
        out.append(zeile)
    return sorted(out, key=lambda r: (not r["fehler"], -abs(r["prozent"] or 0)))


def auffaellig(liste, ab=MELDEN_AB):
    return [r for r in liste if r["fehler"] or (r["prozent"] is not None and abs(r["prozent"]) >= ab - 1e-9)]


def bausteine_text(r):
    from .stammdaten import zahl_als_text as zahl
    return "; ".join(f"{t} {zahl(alt, 2)} → {zahl(neu, 2)} €" for t, alt, neu in r["bausteine"])


def nach_update_noetig(db, version):
    """True, wenn es Prüfangebote gibt und sie für diese Programmversion noch nicht gerechnet wurden."""
    return str(db.einstellung(VERSION_EINST) or "") != version and bool(ids(db))


def nach_update_gerechnet(db, version):
    db.einstellung_setzen(VERSION_EINST, version)


def neue_referenz(db, angebot_ids, version):
    """Referenz neu setzen (Preis- und Zeitbasis bleiben, Preis und Kostenarten von heute)."""
    n = 0
    for aid in angebot_ids:
        a = db.angebot(aid)
        ref = db.zusatz(aid, SCHLUESSEL) if a else None
        if not isinstance(ref, dict):
            continue
        summen, _ = _rechnen(db, a, ref)
        ref.update(verkauf=round(float(summen["verkauf"]), 2), kosten=_kosten(summen), version=version,
                   seit=datetime.date.today().isoformat())
        db.zusatz_setzen(aid, SCHLUESSEL, ref)
        n += 1
    return n
