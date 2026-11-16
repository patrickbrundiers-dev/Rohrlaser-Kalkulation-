"""Preisabweichung zum Wiederholteil erklären (Roadmap Kalkulation Phase 2, OFFER-008; Freigabe Patrick 13.11.2026
„Ganze Phase 2 nach Empfehlung“).

Ein Wiederholteil (wiederholteile.py) zeigt den Preis von damals. Hier wird der Unterschied zum Preis heute in seine
Ursachen zerlegt, Schritt für Schritt mit derselben Rechnung wie eine Staffelstufe (Position allein gerechnet,
staffeln.stufe_rechnen):

  P0  Preis damals je Stück (gespeicherte Staffelpreise des alten Angebots; ohne Staffelpreise: die alte Position
      mit den Preisen und Kalkulationswerten von damals nachgerechnet)
  P1  die Position heute, mit den Preisen und Kalkulationswerten von damals, bei der Menge von damals
      -> P1 − P0 = „Teil oder Eingaben geändert“ (Geometrie, Zusatzarbeiten, Zukauf, Qualität)
  P2  dasselbe mit den Preisen und Kalkulationswerten von heute
      -> P2 − P1 = „Preise und Kalkulationswerte seit damals“ (Material, Schneiddaten, Stundensätze, Gewinn …)
  P3  dasselbe bei der Menge von heute
      -> P3 − P2 = „Menge“ (Rüsten, Programmierung und Stangen verteilen sich anders)
  P4  Preis im Angebot heute (alle Positionen zusammen gerechnet)
      -> P4 − P3 = „Gemeinsam mit den anderen Positionen“

Die Schritte ergeben zusammen genau den Unterschied P4 − P0. Dazu ein Satz für den Kunden. Nur Anzeige: kein Preis
ändert sich. Ohne Qt."""
from .stammdaten import zahl_als_text as zahl

GRENZE = 0.005              # € je Stück: kleinere Schritte nennt der Satz für den Kunden nicht


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _allein(kopf, positionen, i, menge, k, tabellen, einst):
    """Preis je Stück der Position i allein bei der Menge (wie eine Staffelstufe) oder None."""
    from .staffeln import stufe_rechnen, txt
    schl = txt(positionen[i].get("pos"))
    if not schl or menge <= 0:
        return None
    lauf = [dict(p, satz=None, je_satz=None) if j == i else p for j, p in enumerate(positionen)]
    try:
        x = stufe_rechnen(kopf, lauf, schl, menge, k, tabellen, einst)
    except Exception:       # noqa: BLE001 – Erklärung nur, wenn die Rechnung geht
        return None
    return _n(x.get("preis_gesamt")) / menge if x.get("preis_gesamt") is not None else None


def basis_alt(alt_kopf, kopf, k_akt, tab_akt, einst_db):
    """(k, tabellen, einst) mit den festgeschriebenen Preisen und Kalkulationswerten des alten Angebots; ohne Snapshot
    die aktuellen Stammdaten mit den Kalkulationswerten des alten Angebots."""
    from . import rechnen
    pb = (alt_kopf or {}).get("preisbasis")
    k, tab = rechnen.preisbasis_anwenden(dict(kopf, preisbasis=pb), k_akt, tab_akt) if isinstance(pb, dict) \
        else (k_akt, tab_akt)
    einst = rechnen.einstellungen_angebot(alt_kopf, rechnen.einstellungen_fest(tab, einst_db))
    return k, tab, einst


def erklaeren(i, kopf, positionen, kalk_zeilen, k, tabellen, einst, treffer, alt_kopf, alt_positionen, k_akt, tab_akt,
              einst_db):
    """Zerlegung für Position i gegen den Treffer (wiederholteile.Treffer) des alten Angebots alt_kopf mit dessen
    Positionen. Ergebnis: dict(damals, heute, menge_damals, menge_heute, schritte=[dict(name, eur, text)], satz,
    nachgerechnet) oder None (nicht rechenbar)."""
    from . import rechnen
    p = positionen[i]
    alt_p = treffer.position
    menge_a = _n(treffer.preis[0]) if treffer.preis else _n(alt_p.get("stueck"))
    menge_n = _n(p.get("stueck"))
    if menge_a <= 0 or menge_n <= 0:
        return None
    k_a, tab_a, einst_a = basis_alt(alt_kopf, kopf, k_akt, tab_akt, einst_db)
    nachgerechnet = not treffer.preis
    if treffer.preis:
        p0 = _n(treffer.preis[1])
    else:
        voll = [q for q in alt_positionen if q.get("id") == alt_p.get("id")]
        if not voll:
            return None
        j = alt_positionen.index(voll[0])
        p0 = _allein(dict(alt_kopf, preisbasis=None), alt_positionen, j, menge_a, k_a, tab_a, einst_a)
    p1 = _allein(kopf, positionen, i, menge_a, k_a, tab_a, einst_a)
    p2 = _allein(kopf, positionen, i, menge_a, k, tabellen, einst)
    p3 = p2 if menge_a == menge_n else _allein(kopf, positionen, i, menge_n, k, tabellen, einst)
    p4 = _n((kalk_zeilen[i] or {}).get("preis_teil")) if kalk_zeilen and i < len(kalk_zeilen) else None
    if None in (p0, p1, p2, p3, p4):
        return None
    from .wiederholteile import aenderungen
    geaendert = aenderungen(p, alt_p)
    if (p.get("zusatz") or None) != (alt_p.get("zusatz") or None):
        geaendert.append("Zusatzarbeiten anders")
    if p.get("id") in rechnen.wiederholt_ids(kopf):
        geaendert.append("Programm schon vorhanden (keine neue Programmierung)")
    preise = rechnen.preisbasis_abweichung(dict(kopf, preisbasis=(alt_kopf or {}).get("preisbasis")), k, tabellen) \
        if isinstance((alt_kopf or {}).get("preisbasis"), dict) else []
    kalk = [f"Gewinn {zahl(100 * _n(einst_a.get('gewinn')), 0)} → {zahl(100 * _n(einst.get('gewinn')), 0)} %"] \
        if abs(_n(einst_a.get("gewinn")) - _n(einst.get("gewinn"))) > 1e-9 else []
    schritte = [
        dict(name="Teil oder Eingaben geändert", eur=p1 - p0, text=", ".join(geaendert)),
        dict(name="Preise und Kalkulationswerte seit damals", eur=p2 - p1, text="; ".join(preise[:4] + kalk)),
        dict(name="Menge", eur=p3 - p2,
             text=f"{zahl(menge_n, 0)} statt {zahl(menge_a, 0)} Stück" if menge_a != menge_n else ""),
        dict(name="Gemeinsam mit den anderen Positionen gerechnet", eur=p4 - p3,
             text="Stangen, Rüsten und Programmierung mit den übrigen Positionen geteilt"),
    ]
    return dict(damals=p0, heute=p4, menge_damals=menge_a, menge_heute=menge_n, schritte=schritte,
                nachgerechnet=nachgerechnet, nummer=(treffer.angebot or {}).get("nummer"),
                satz=satz_kunde(p0, p4, menge_a, menge_n, schritte, (treffer.angebot or {}).get("nummer")))


def satz_kunde(damals, heute, menge_a, menge_n, schritte, nummer=None):
    """Kurzer Satz für den Kunden: „Gegenüber unserem Angebot A-… (4,85 € je Stück bei 50 Stück) ist der Preis um
    0,40 € gestiegen: Materialpreise +0,30 €, kleinere Menge +0,10 €.“"""
    d = heute - damals
    bezug = f"unserem Angebot {nummer}" if nummer else "unserem letzten Angebot"
    kopf = (f"Gegenüber {bezug} ({zahl(damals, 2)} € je Stück bei {zahl(menge_a, 0)} Stück) ist der Preis je Stück "
            f"{'gleich geblieben' if abs(d) < GRENZE else ('um ' + zahl(abs(d), 2) + ' € ' + ('gestiegen' if d > 0 else 'gesunken'))}")
    namen = {"Teil oder Eingaben geändert": "geänderte Ausführung des Teils",
             "Preise und Kalkulationswerte seit damals": "geänderte Material- und Fertigungskosten",
             "Menge": ("größere" if menge_n > menge_a else "kleinere") + " Bestellmenge",
             "Gemeinsam mit den anderen Positionen gerechnet": "gemeinsame Fertigung mit den übrigen Positionen"}
    teile = [f"{namen[s['name']]} {'+' if s['eur'] > 0 else '−'}{zahl(abs(s['eur']), 2)} €"
             for s in sorted(schritte, key=lambda s: -abs(s["eur"])) if abs(s["eur"]) >= GRENZE]
    return kopf + (": " + ", ".join(teile) if teile and abs(d) >= GRENZE else "") + "."
