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
