"""Schneiddaten aus Ist-Zeiten kalibrieren (Plan Phase 3 und 4, Paket D, Patrick 13.11.2026 „Alles einbauen“, E2:
nur Vorschlag mit Knopf „Übernehmen“).

D1 MACH-005: Je Schneiddaten-Zeile (Maschine, Werkstoff bzw. Kategorie, Wandstärke bis, Gas) aus den Laufzeiten je
   Teil der Nachkalkulation (nachkalkulation.faelle_laserzeit_teil) ein Faktor Ist ÷ Soll (Median ohne Ausreißer,
   kennwerte.auswerten). Übernommen wird nur per Knopf: die Vorschübe der Zeile ÷ Faktor, Quelle „Nachkalkulation“,
   Stand = heute, mit Eintrag in der Kennwerte-Historie (zurücknehmbar).
D2 MACH-012: Bandbreite der Laserzeit (von–bis) aus der Streuung Ist ÷ Soll der Aufträge je Maschine: 10. und 90.
   Perzentil, ab BAND_MINDESTENS Aufträgen. Nur Anzeige (Kachel Laserzeit im Angebot), keine Zahl ändert sich.
D3 MACH-004: Vorschub-Abminderung nach Wandbereich (bis 3 mm, 3–6 mm, über 6 mm) je Maschine und Werkstoff, wenn
   genug Fälle im Bereich zusammenkommen; gilt für alle Zeilen des Bereichs. Wie D1 nur per Knopf, mit Historie.

KI erfindet hier nichts: jeder Faktor kommt aus erfassten Ist-Zeiten und nennt Fälle, Streuung und Aufträge."""
import datetime
import json
import statistics

from . import kennwerte, nachkalkulation, rechnen

QUELLE_SD = "Nachkalkulation"
MINDESTENS = 3                  # Fälle je Vorschlag (Vorgabe im Fenster änderbar)
BAND_MINDESTENS = 3             # Aufträge je Maschine für die Bandbreite
BEREICHE = ((3.0, "bis 3 mm"), (6.0, "3–6 mm"), (None, "über 6 mm"))
QUELLE_TEIL, QUELLE_BEREICH = "laserzeit_teil", "laserzeit_bereich"


def bereich(wand):
    """Wandbereich-Text zu „Wandstärke bis“."""
    w = wand if isinstance(wand, (int, float)) else 0.0
    return next(t for grenze, t in BEREICHE if grenze is None or w <= grenze)


def _quantil(werte, q):
    s = sorted(werte)
    if not s:
        return None
    pos = (len(s) - 1) * q
    i = int(pos)
    return s[i] + (s[min(i + 1, len(s) - 1)] - s[i]) * (pos - i)


def band(faktoren):
    """(unten, oben) = 10. und 90. Perzentil der Faktoren Ist ÷ Soll, None bei zu wenigen."""
    f = [x for x in faktoren if isinstance(x, (int, float)) and x > 0]
    if len(f) < BAND_MINDESTENS:
        return None
    return _quantil(f, 0.1), _quantil(f, 0.9)


def laserzeit_band(db, maschine, fl=None):
    """D2: dict(unten, oben, n, median) der Laserzeit Ist ÷ Soll je Auftrag auf dieser Maschine oder None."""
    q = []
    for f in nachkalkulation.faelle(db)[0] if fl is None else fl:
        s, z = f["soll"], nachkalkulation._zeile(f["soll"], "Laserzeit")
        if z and z[7] and s.get("maschine") == maschine and not s.get("maschinen") and nachkalkulation._n(z[3]) and \
                nachkalkulation._n(z[4]) is not None:
            q.append(z[4] / z[3])
    b = band(q)
    if b is None:
        return None
    return dict(unten=b[0], oben=b[1], n=len(q), median=statistics.median(q))


def band_text(b, minuten):
    """„erfahrungsgemäß 1:52–2:10 h (7 Aufträge)“ zur kalkulierten Laserzeit in Minuten, '' ohne Band."""
    if not b or not isinstance(minuten, (int, float)) or minuten <= 0:
        return ""
    return (f"erfahrungsgemäß {rechnen.zeit_text(minuten * b['unten'])}–{rechnen.zeit_text(minuten * b['oben'])} "
            f"({b['n']} Aufträge)")


def _stempeln(db, z, aend):
    """Quelle „Nachkalkulation“ und Stand heute an die Schneiddaten-Zeile, alte Werte in aend (zurücknehmbar)."""
    heute = datetime.date.today().isoformat()
    for feld, neu in (("quelle", QUELLE_SD), ("datum", heute)):
        if z.get(feld) != neu:
            db.aendern("schneiddaten", z["id"], feld, neu)
            aend.append(["schneiddaten", z["id"], feld, z.get(feld), neu])


def _vorschub_teilen(db, z, faktor, aend):
    for feld in rechnen.VORSCHUB_FELDER:
        if isinstance(z.get(feld), (int, float)):
            neu = max(1.0, round(z[feld] / faktor))
            db.aendern("schneiddaten", z["id"], feld, neu)
            aend.append(["schneiddaten", z["id"], feld, z[feld], neu])


def _passt(z, maschine, wer):
    kat = wer[len("Kategorie "):] if str(wer).startswith("Kategorie ") else None
    return z.get("maschinen_id") == maschine and (
        z.get("werkstoff_id") == wer if kat is None else not z.get("werkstoff_id") and z.get("kategorie") == kat)


def zeilen_zu(db, schluessel, quelle=QUELLE_TEIL):
    """Schneiddaten-Zeilen, die ein Vorschlag ändern würde."""
    if quelle == QUELLE_BEREICH:
        maschine, wer, ber = schluessel
        return [z for z in db.zeilen("schneiddaten") if _passt(z, maschine, wer) and bereich(z.get("wand_bis")) == ber]
    maschine, wer, wand_bis, gas = schluessel
    return [z for z in db.zeilen("schneiddaten") if _passt(z, maschine, wer) and z.get("wand_bis") == wand_bis
            and (z.get("gas") or "") == gas]


def anwenden_teil(db, schluessel, faktor):
    """D1: Vorschübe genau dieser Schneiddaten-Zeile(n) ÷ Faktor, Quelle Nachkalkulation."""
    aend = []
    for z in zeilen_zu(db, schluessel):
        _vorschub_teilen(db, z, faktor, aend)
        _stempeln(db, z, aend)
    return aend


def faelle_bereich(db):
    """D3: Fälle der Laufzeit je Teil, gruppiert nach (Maschine, Werkstoff/Kategorie, Wandbereich)."""
    return [dict(f, schluessel=(f["schluessel"][0], f["schluessel"][1], bereich(f["schluessel"][2])))
            for f in nachkalkulation.faelle_laserzeit_teil(db)]


def anwenden_bereich(db, schluessel, faktor):
    """D3: Vorschübe aller Zeilen dieses Wandbereichs ÷ Faktor, Quelle Nachkalkulation."""
    aend = []
    for z in zeilen_zu(db, schluessel, QUELLE_BEREICH):
        _vorschub_teilen(db, z, faktor, aend)
        _stempeln(db, z, aend)
    return aend


def vorschlaege(db, mindest_n=MINDESTENS):
    """Vorschläge D1 (je Zeile) und D3 (je Wandbereich): [dict(art, quelle, titel, schluessel, faktor, n, streuung,
    band, ausreisser, faelle, status, zeilen [(Zeilen-ID, Wand bis, Vorschub groß alt, neu)])]."""
    out = []
    for quelle, art, funktion in ((QUELLE_TEIL, "Wandstufe", nachkalkulation.faelle_laserzeit_teil),
                                  (QUELLE_BEREICH, "Wandbereich", faelle_bereich)):
        gruppen = {}
        for f in funktion(db):
            gruppen.setdefault(tuple(f["schluessel"]), []).append(f)
        for schl, fl in sorted(gruppen.items(), key=lambda x: [str(t) for t in x[0]]):
            v = dict(art=art, quelle=quelle, titel=kennwerte.QUELLEN[quelle][0], schluessel=schl,
                     **kennwerte.auswerten(fl, mindest_n))
            v["band"] = band([f["ist"] / f["soll"] for f in v["faelle"]])
            fk = v["faktor"]
            v["zeilen"] = [(z["id"], z.get("wand_bis"), z.get("vorschub_gross"),
                            max(1.0, round(z["vorschub_gross"] / fk)) if fk and isinstance(z.get("vorschub_gross"),
                                                                                         (int, float)) else None)
                           for z in zeilen_zu(db, schl, quelle)]
            if not v["zeilen"]:
                v["status"] = "keine Schneiddaten-Zeile"
            out.append(v)
    return out


def uebernehmen(db, v, version, begruendung=None):
    """Vorschlag per Knopf übernehmen (kennwerte.freigeben mit Historie). Ergebnis: ID der Historie."""
    if v.get("status") != "ok":
        raise ValueError("Zu wenig Daten – der Vorschlag lässt sich nicht übernehmen.")
    text = begruendung or (f"Kalibrierung aus {v['n']} Fällen der Nachkalkulation ({v['art']} "
                           f"{' / '.join(str(s) for s in v['schluessel'])})")
    return kennwerte.freigeben(db, v, text, version)


kennwerte.register_quelle(QUELLE_TEIL, "Laufzeit je Teil (Maschine, Werkstoff, Wandstärke bis, Gas) → Vorschübe "
                          "dieser Schneiddaten", nachkalkulation.faelle_laserzeit_teil, anwenden_teil)
kennwerte.register_quelle(QUELLE_BEREICH, "Laufzeit je Teil nach Wandbereich (Maschine, Werkstoff, bis 3 / 3–6 / über "
                          "6 mm) → Vorschübe des Bereichs", faelle_bereich, anwenden_bereich)


# ------------------------------------------------------------------ Phase 4 E7: Laserzeit je Baustein (16.11.2026)
QUELLE_BAUSTEINE = "laserzeit_bausteine"
MINDESTENS_BAUSTEINE = 10       # Teile mit Ist-Laufzeit je Maschine
ANTEIL_MIN = 0.02               # Bausteine unter 2 % der Zeit bleiben bei ihrem Faktor (nicht bestimmbar)
GLAETTEN = 0.01                 # Zug zum bisherigen Faktor (stabil, wenn zwei Bausteine immer gemeinsam auftreten)
GRENZEN = (0.2, 5.0)


def faelle_bausteine(db):
    """Laserteile mit Ist-Laufzeit und Zeit je Baustein (gespeichert ab 16.11.2026): {Maschine: [dict(angebot, pid,
    soll, ist, roh {Baustein: s ohne Faktor}, f_laser, rest)]}; rest = Soll − Faktor Laserzeit × Bausteine (gemeinsame
    Schnitte, Zusatz- und Prüfzeiten, bleiben fest)."""
    out = {}
    for f in nachkalkulation.faelle(db)[0]:
        je = f["ist"].get("laufzeit") or {}
        for e in f["soll"].get("laufzeit") or ():
            if len(e) < 6 or not isinstance(e[3], dict):
                continue
            pid, soll_s, schl, bst, fak, fl = e[:6]
            ist_s = nachkalkulation._n(je.get(str(pid)))
            if ist_s is None or not nachkalkulation._n(soll_s):
                continue
            fl = nachkalkulation._n(fl) or 1.0
            roh = {b: nachkalkulation._n(bst.get(b)) / ((fak or {}).get(b) or 1.0) for b in rechnen.BAUSTEINE}
            summe = sum(nachkalkulation._n(bst.get(b)) for b in rechnen.BAUSTEINE)
            out.setdefault(schl[0] or "", []).append(dict(angebot=f["nummer"], pid=pid, soll=soll_s, ist=ist_s,
                                                          roh=roh, f_laser=fl, rest=soll_s - fl * summe))
    return out


def _anpassen(fl_faelle, start):
    """Faktoren je Baustein ≥ 0 mit kleinsten Quadraten der relativen Abweichung (je Teil gleich gewichtet), Zug
    GLAETTEN zum bisherigen Faktor; Koordinatenabstieg in den GRENZEN. Ergebnis {Baustein: Faktor}, frei (Liste)."""
    bst = list(rechnen.BAUSTEINE)
    zeilen = [([f["f_laser"] * f["roh"][b] / f["soll"] for b in bst], (f["ist"] - f["rest"]) / f["soll"])
              for f in fl_faelle]
    gesamt = sum(sum(x) for x, _ in zeilen) or 1.0
    frei = [i for i, b in enumerate(bst) if sum(x[i] for x, _ in zeilen) / gesamt >= ANTEIL_MIN]
    g = [start[b] for b in bst]
    diag = [sum(x[i] ** 2 for x, _ in zeilen) for i in range(len(bst))]
    for _ in range(200):
        alt = list(g)
        for i in frei:
            if diag[i] <= 0:
                continue
            lam = GLAETTEN * diag[i]
            r = sum(x[i] * (y - sum(x[j] * g[j] for j in range(len(bst)) if j != i)) for x, y in zeilen)
            g[i] = min(GRENZEN[1], max(GRENZEN[0], (r + lam * start[bst[i]]) / (diag[i] + lam)))
        if max(abs(a - b) for a, b in zip(g, alt)) < 1e-6:
            break
    return {b: g[i] for i, b in enumerate(bst)}, [bst[i] for i in frei]


def _abweichung(fl_faelle, faktoren):
    """Mittlere Abweichung |Ist − Soll| ÷ Soll mit diesen Faktoren je Baustein."""
    d = [abs(f["ist"] - (f["rest"] + f["f_laser"] * sum(faktoren[b] * f["roh"][b] for b in rechnen.BAUSTEINE)))
         / f["soll"] for f in fl_faelle]
    return sum(d) / len(d) if d else None


def vorschlaege_bausteine(db, mindest_n=MINDESTENS_BAUSTEINE):
    """Vorschlag je Maschine: dict(maschine, n, alt {Baustein: Faktor}, neu, frei, anteil {Baustein: Anteil an der
    Soll-Zeit}, vorher, nachher (mittlere Abweichung), soll_h, ist_h, status). Nur Vorschau; übernommen wird nur mit
    uebernehmen_bausteine (Knopf)."""
    out = []
    masch = {z.get("maschinen_id"): z for z in db.zeilen("maschinen")}
    for m, fl in sorted(faelle_bausteine(db).items()):
        alt = rechnen.baustein_faktoren(masch.get(m))
        roh_sum = {b: sum(f["f_laser"] * f["roh"][b] * alt[b] for f in fl) for b in rechnen.BAUSTEINE}
        ges = sum(roh_sum.values()) or 1.0
        v = dict(maschine=m, n=len(fl), alt=alt, neu=dict(alt), frei=[], anteil={b: roh_sum[b] / ges for b in roh_sum},
                 vorher=_abweichung(fl, alt), nachher=None, soll_h=sum(f["soll"] for f in fl) / 3600,
                 ist_h=sum(f["ist"] for f in fl) / 3600, status="zu wenig Daten")
        if len(fl) >= mindest_n and m in masch:
            neu, frei = _anpassen(fl, alt)
            v.update(neu={b: round(x, 3) for b, x in neu.items()}, frei=frei)
            v["nachher"] = _abweichung(fl, v["neu"])
            v["status"] = "ok" if v["nachher"] < v["vorher"] - 1e-9 else "keine Verbesserung"
        elif m not in masch:
            v["status"] = "Maschine fehlt"
        out.append(v)
    return out


def uebernehmen_bausteine(db, v, version, begruendung=None):
    """Faktoren je Baustein in die Maschine schreiben (Felder faktor_<Baustein>), Historie unter Kennwerte
    (zurücknehmbar). Ergebnis: ID der Historie."""
    if v.get("status") != "ok":
        raise ValueError("Zu wenig Daten oder keine Verbesserung – der Vorschlag lässt sich nicht übernehmen.")
    z = next((x for x in db.zeilen("maschinen") if x.get("maschinen_id") == v["maschine"]), None)
    if z is None:
        raise ValueError(f"Maschine {v['maschine']} fehlt.")
    aend = []
    for b in v["frei"]:
        feld, neu = f"faktor_{b}", v["neu"][b]
        if z.get(feld) != neu:
            db.aendern("maschinen", z["id"], feld, neu)
            aend.append(["maschinen", z["id"], feld, z.get(feld), neu])
    text = begruendung or (f"Laserzeit je Baustein aus {v['n']} Teilen der Nachkalkulation, mittlere Abweichung "
                           f"{100 * v['vorher']:.0f} % → {100 * v['nachher']:.0f} %")
    ges = sum(v["anteil"][b] * v["neu"][b] / (v["alt"][b] or 1.0) for b in v["anteil"])
    return db.neu(kennwerte.HISTORIE.name, dict(
        datum=datetime.datetime.now().isoformat(timespec="seconds"), quelle=QUELLE_BAUSTEINE,
        schluessel=json.dumps([v["maschine"]], ensure_ascii=False), faktor=round(ges, 3), n=v["n"],
        streuung=round(v["nachher"], 3), begruendung=text, version=version,
        aenderungen=json.dumps(aend, ensure_ascii=False)))


def bericht_bausteine(db):
    """Soll/Ist-Bericht je Maschine und Baustein: [dict(maschine, baustein, text, anteil, alt, neu, n)]."""
    out = []
    for v in vorschlaege_bausteine(db):
        for b in rechnen.BAUSTEINE:
            out.append(dict(maschine=v["maschine"], baustein=b, text=rechnen.BAUSTEIN_TEXT[b], anteil=v["anteil"][b],
                            alt=v["alt"][b], neu=v["neu"][b], n=v["n"], frei=b in v["frei"]))
    return out
