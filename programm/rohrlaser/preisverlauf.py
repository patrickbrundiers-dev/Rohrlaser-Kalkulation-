"""Materialpreise als Zeitreihe (Roadmap Kalkulation Phase 2, MAT-008) und EK-Verlauf der Zukaufartikel (PART-013);
Freigabe Patrick 13.11.2026 „Ganze Phase 2 nach Empfehlung“.

Materialpreise: 'Preise' und 'Lieferlängen' haben je Profil + Werkstoff (+ Länge) weiter genau eine gültige Zeile, der
Werkstoff einen Tonnenpreis; gerechnet wird wie bisher damit. Neu merkt sich die Tabelle preis_verlauf jeden Stand: nach
jeder Änderung (und beim Öffnen der Datei, so kommen auch Abgleich und CSV-Import dazu) vergleicht abgleichen() die
aktuellen Zeilen mit dem letzten gemerkten Stand und trägt Abweichungen mit Datum ein (Datum = 'Gültig ab' der Zeile,
sonst heute). Daraus: Verlauf je Werkstoff/Abmessung, Durchschnitt der letzten 3/6/12 Monate (zeitgewichtet, nur
Stände mit derselben Preisbasis wie der aktuelle) und Änderung zum Stand vor 3/6/12 Monaten. Festgeschriebene Preise
(preisbasis) bleiben unverändert.

Zukauf: Preisänderungen stehen schon im Protokoll zukauf_historie (Feld „Einkaufspreise“, Text „ab 1: 1,20 | ab 100:
0,95“). ek_verlauf() liest daraus je Artikel und Lieferant den Preis der ersten Staffel; sprung() meldet Änderungen über
der Schwelle der Einstellung 'zukauf_preissprung' (0 = aus). Ohne Qt."""
import datetime
import re

TABELLE = "preis_verlauf"
ART_PREIS, ART_LIEFERLAENGE, ART_TONNE = "Preise", "Lieferlängen", "Tonnenpreis"
SPALTEN = ("id", "zeit", "datum", "art", "profil_id", "werkstoff_id", "laenge", "basis", "preis", "lieferant")
MONATE = (3, 6, 12)


def einrichten(con):
    """Tabelle anlegen; beim ersten Mal den heutigen Stand als Anfang eintragen (abgleichen)."""
    con.execute(f"CREATE TABLE IF NOT EXISTS {TABELLE} (id INTEGER PRIMARY KEY, zeit TEXT, datum TEXT, art TEXT, "
                "profil_id TEXT, werkstoff_id TEXT, laenge REAL, basis TEXT, preis REAL, lieferant TEXT)")
    con.execute(f"CREATE INDEX IF NOT EXISTS {TABELLE}_schluessel ON {TABELLE} (art, profil_id, werkstoff_id, laenge)")


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _heute():
    return datetime.date.today().isoformat()


def _stand(con):
    """Aktuelle Preise: {(art, profil, werkstoff, laenge): (basis, preis, gültig ab, lieferant)}."""
    out = {}
    for r in con.execute("SELECT profil_id, werkstoff_id, basis, preis, gueltig_ab, lieferant FROM preise"):
        if r[0] and r[1] and _n(r[3]) is not None:
            out[(ART_PREIS, r[0], r[1], None)] = (r[2] or "", _n(r[3]), r[4], r[5])
    for r in con.execute("SELECT profil_id, werkstoff_id, laenge, basis, preis, gueltig_ab, lieferant FROM lieferlaengen"):
        if r[0] and r[1] and _n(r[4]) is not None:
            out[(ART_LIEFERLAENGE, r[0], r[1], _n(r[2]))] = (r[3] or "", _n(r[4]), r[5], r[6])
    for r in con.execute("SELECT werkstoff_id, tonnenpreis FROM werkstoffe"):
        if r[0] and _n(r[1]) is not None:
            out[(ART_TONNE, None, r[0], None)] = ("€/t", _n(r[1]), None, None)
    return out


def _letzte(con):
    out = {}
    for r in con.execute(f"SELECT art, profil_id, werkstoff_id, laenge, basis, preis, datum FROM {TABELLE} ORDER BY id"):
        out[(r[0], r[1], r[2], _n(r[3]))] = (r[4] or "", _n(r[5]), r[6] or "")
    return out


def abgleichen(con):
    """Neue bzw. geänderte Preise eintragen. Ergebnis: Anzahl neuer Einträge. Gelöschte Zeilen bleiben im Verlauf."""
    jetzt = datetime.datetime.now().isoformat(timespec="seconds")
    letzte = _letzte(con)
    neu = []
    for (art, profil, ws, laenge), (basis, preis, ab, lief) in _stand(con).items():
        alt = letzte.get((art, profil, ws, laenge))
        if alt is not None and alt[0] == basis and alt[1] is not None and abs(alt[1] - preis) < 1e-9:
            continue
        # Datum des Stands: 'Gültig ab' der Zeile, wenn es mit dem Preis neu eingetragen wurde (anders als beim letzten
        # Stand), sonst heute (ein altes 'Gültig ab' passt nicht zum neuen Preis)
        ab = str(ab)[:10] if ab else ""
        datum = ab if ab and (alt is None or ab != alt[2]) else _heute()
        neu.append((jetzt, datum, art, profil, ws, laenge, basis, preis, lief))
    if neu:
        con.executemany(f"INSERT INTO {TABELLE} (zeit, datum, art, profil_id, werkstoff_id, laenge, basis, preis, "
                        "lieferant) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", neu)
    return len(neu)


def eintraege(con, profil_id=None, werkstoff_id=None, art=None, laenge=None):
    """Einträge (dicts) nach Datum, älteste zuerst; ohne Profil: auch der Tonnenpreis des Werkstoffs."""
    sql, werte = f"SELECT {', '.join(SPALTEN)} FROM {TABELLE} WHERE 1=1", []
    for spalte, wert in (("profil_id", profil_id), ("werkstoff_id", werkstoff_id), ("art", art)):
        if wert is not None:
            sql += f" AND {spalte}=?"
            werte.append(wert)
    if laenge is not None:
        sql += " AND laenge=?"
        werte.append(float(laenge))
    return [dict(zip(SPALTEN, r)) for r in con.execute(sql + " ORDER BY datum, id", werte)]


def _datum(t):
    try:
        return datetime.date.fromisoformat(str(t)[:10])
    except ValueError:
        return None


def reihe(eintraege_):
    """[(date, Preis)] mit der Preisbasis des jüngsten Eintrags (andere Basis passt nicht in dieselbe Kurve); bei
    mehreren Einträgen am selben Tag zählt der letzte."""
    if not eintraege_:
        return []
    basis = eintraege_[-1].get("basis") or ""
    tage = {}
    for e in eintraege_:
        d = _datum(e.get("datum"))
        if d is not None and (e.get("basis") or "") == basis and _n(e.get("preis")) is not None:
            tage[d] = _n(e["preis"])
    return sorted(tage.items())


def mittel(punkte, monate, heute=None):
    """Zeitgewichteter Durchschnitt der Reihe über die letzten monate Monate (ein Preis gilt bis zum nächsten Stand)
    oder None, wenn es im Zeitraum keinen Preis gibt."""
    heute = heute or datetime.date.today()
    start = heute - datetime.timedelta(days=round(monate * 30.44))
    summe = tage = 0.0
    for i, (d, p) in enumerate(punkte):
        bis = punkte[i + 1][0] if i + 1 < len(punkte) else heute + datetime.timedelta(days=1)
        von = max(d, start)
        if bis <= von:
            continue
        n = (bis - von).days
        summe += p * n
        tage += n
    return summe / tage if tage else None


def preis_am(punkte, tag):
    """Preis, der am Tag galt (letzter Stand bis dahin) oder None."""
    out = None
    for d, p in punkte:
        if d <= tag:
            out = p
    return out


def kennzahlen(punkte, heute=None):
    """[dict(monate, mittel, damals, aenderung_pct)] für 3/6/12 Monate."""
    heute = heute or datetime.date.today()
    aktuell = punkte[-1][1] if punkte else None
    out = []
    for m in MONATE:
        damals = preis_am(punkte, heute - datetime.timedelta(days=round(m * 30.44)))
        out.append(dict(monate=m, mittel=mittel(punkte, m, heute), damals=damals,
                        aenderung_pct=(aktuell / damals - 1) * 100 if aktuell is not None and damals else None))
    return out


def bezeichnung(e):
    """'RR 42,4x2,0 / S235 (Preise)' bzw. 'S235 (Tonnenpreis)'."""
    from .stammdaten import zahl_als_text as zahl
    teile = [x for x in (e.get("profil_id"), e.get("werkstoff_id")) if x]
    zusatz = e.get("art") or ""
    if e.get("laenge"):
        zusatz += f" {zahl(e['laenge'], 0)} mm"
    return " / ".join(teile) + f" ({zusatz})"


# ---------------------------------------------------------------- PART-013 EK-Verlauf der Zukaufartikel
EK_FELD = "Einkaufspreise"
_ERSTE = re.compile(r"ab\s*[\d.,]+\s*:\s*(-?[\d.]*\d(?:,\d+)?)")


def erster_preis(text):
    """Preis der ersten Staffel aus 'ab 1: 1,20 | ab 100: 0,95' -> 1.2; None ohne Preis."""
    m = _ERSTE.search(str(text or ""))
    if not m:
        return None
    try:
        return float(m.group(1).replace(".", "").replace(",", "."))
    except ValueError:
        return None


def ek_verlauf(historie):
    """Aus zukauf_historie (neueste zuerst oder beliebig): {(artikel_id, lieferant): [dict(datum, preis, alt, artikel,
    bemerkung)]} nach Datum, älteste zuerst. Ein neuer Lieferant zählt mit seinem ersten Preis."""
    out = {}
    for h in sorted(historie or (), key=lambda h: (str(h.get("datum") or ""), h.get("id") or 0)):
        if h.get("feld") not in (EK_FELD, "Lieferant neu"):
            continue
        p = erster_preis(h.get("neu"))
        if p is None:
            continue
        out.setdefault((h.get("artikel_id"), h.get("lieferant") or ""), []).append(
            dict(datum=str(h.get("datum") or "")[:10], preis=p, alt=erster_preis(h.get("alt")),
                 artikel=h.get("artikel") or "", bemerkung=h.get("bemerkung") or ""))
    return out


def schwelle(einst):
    v = _n((einst or {}).get("zukauf_preissprung"))
    return v if v and v > 0 else 0.0


def spruenge(verlauf, grenze_pct):
    """Preissprünge über grenze_pct %: [dict(artikel_id, lieferant, artikel, datum, alt, neu, pct)], neueste zuerst."""
    if not grenze_pct:
        return []
    out = []
    for (aid, lief), reihe_ in (verlauf or {}).items():
        for e in reihe_:
            alt, neu = e.get("alt"), e.get("preis")
            if alt and neu is not None and abs(neu / alt - 1) * 100 > grenze_pct + 1e-9:
                out.append(dict(artikel_id=aid, lieferant=lief, artikel=e["artikel"], datum=e["datum"], alt=alt,
                                neu=neu, pct=(neu / alt - 1) * 100))
    return sorted(out, key=lambda x: x["datum"], reverse=True)


def sprung_text(s):
    from .stammdaten import zahl_als_text as zahl
    return (f"EK-Preissprung {s['artikel']}{' bei ' + s['lieferant'] if s['lieferant'] else ''}: "
            f"{zahl(s['alt'], 2)} → {zahl(s['neu'], 2)} € ({'+' if s['pct'] > 0 else '−'}{zahl(abs(s['pct']), 0)} %, "
            f"{s['datum']})")
