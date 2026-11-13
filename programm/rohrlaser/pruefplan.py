"""Prüfplan und Messprotokoll je Position (Vorschlag S1, Patrick 02.11.2026 „S1a“).

Die Sollmaße kommen unverändert aus der Position, also aus der STEP-Messung bzw. dem Schneidweg-Rechner
(positionen.technik, schneidweg.py) und der Teilelänge: Länge, Gehrungswinkel an Anfang und Ende, je Kontur die Lage
ab Ende A (x), das Maß (Ø, Länge × Breite …) und bei Mustern die Teilung. Nichts wird umgerechnet oder verschoben
(Grundregel „Konturen wie STEP“). Toleranzen nach ISO 2768 (Einstellung pruef_toleranz: fein, mittel, grob) oder
leer = Kundenvorgabe von Hand.

Das PDF hat je Merkmal eine leere Spalte Ist und Unterschrift/Datum (Erstmusterprüfung, Prüfbericht für den Kunden).
Optional die Zusatzarbeit „Erstmusterprüfung“ (€ je Angebot, Einstellung erstmuster_preis) an die Position hängen.
Ohne Qt außer dem PDF (reportlab über pdf.py)."""
import json

from .schneidweg import (AUSKLINKUNG, AUSSCHNITT, BOHRUNG, DURCHBRUCH, FLOWDRILL, GRAVUREN, LANGLOCH, LOCHFELD, RECHTECK,
                         SCHLITZ, SENKUNG)

# ISO 2768-1 Grenzabmaße für Längenmaße [mm]: (bis Nennmaß, fein f, mittel m, grob c)
ISO_LAENGE = ((6, 0.05, 0.1, 0.2), (30, 0.1, 0.2, 0.5), (120, 0.15, 0.3, 0.8), (400, 0.2, 0.5, 1.2),
              (1000, 0.3, 0.8, 2.0), (2000, 0.5, 1.2, 3.0), (4000, 0.8, 2.0, 4.0), (8000, 1.2, 3.0, 5.0),
              (12000, 2.0, 4.0, 6.0))
# ISO 2768-1 Winkel nach der Länge des kürzeren Schenkels [mm]: (bis, f/m, c) in Grad
ISO_WINKEL = ((10, 1.0, 1.5), (50, 0.5, 1.0), (120, 1 / 3, 0.5), (400, 1 / 6, 0.25), (1e9, 1 / 12, 1 / 6))
KLASSEN = {"ISO 2768-f": 1, "ISO 2768-m": 2, "ISO 2768-c": 3}
VORGABE = "ISO 2768-m"
# Maßbezug je Kontur (Plan Paket 7 nach LT8.20 Kapitel 3); leer = Flächenmitte
MASSBEZUEGE = ("Flächenmitte", "Kante vorherige Fläche", "Kante folgende Fläche")
ZUSATZ = "Erstmusterprüfung"


def _n(w):
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else None


def toleranz(mass, klasse=VORGABE):
    """± Grenzabmaß [mm] für ein Längenmaß nach ISO 2768 (None ohne Klasse oder Maß)."""
    s = KLASSEN.get(klasse)
    if s is None or _n(mass) is None:
        return None
    for bis, *werte in ISO_LAENGE:
        if abs(mass) <= bis:
            return werte[s - 1]
    return ISO_LAENGE[-1][s]


def toleranz_winkel(schenkel, klasse=VORGABE):
    """± Grenzabmaß [°] für einen Winkel nach ISO 2768 (kürzerer Schenkel in mm)."""
    s = KLASSEN.get(klasse)
    if s is None:
        return None
    for bis, fm, c in ISO_WINKEL:
        if (schenkel or 50) <= bis:
            return c if s == 3 else fm
    return None


def technik(p):
    try:
        t = json.loads(p.get("technik") or "{}")
    except (TypeError, ValueError):
        return {}
    return t if isinstance(t, dict) else {}


def _mass_text(k):
    art, z = k.get("art"), lambda n: _n(k.get(n))
    if art in (BOHRUNG, FLOWDRILL, DURCHBRUCH, LOCHFELD) and z("d") is not None:
        return f"Ø {_t(z('d'))}", z("d")
    if art == SENKUNG and z("d") is not None:
        return f"Ø {_t(z('d'))} / Senk-Ø {_t(z('D'))}" if z("D") else f"Ø {_t(z('d'))}", z("d")
    if art in (LANGLOCH, SCHLITZ, AUSKLINKUNG) and z("l") is not None:
        return f"{_t(z('l'))} × {_t(z('b'))}", z("l")
    if art == AUSSCHNITT and z("b") is not None:
        rund = k.get("kontur_form") == "Rund"
        return ((f"Ø {_t(z('b'))}" if rund else f"{_t(z('b'))} × {_t(z('h'))}")
                + (f", Tiefe {_t(z('tiefe'))}" if z("tiefe") else "")), max(z("b"), 0 if rund else z("h") or 0)
    if art == RECHTECK and z("b") is not None:
        return f"{_t(z('b'))} × {_t(z('h'))}" + (f", r {_t(z('r'))}" if z("r") else ""), max(z("b"), z("h") or 0)
    if z("huelle") is not None:
        return f"Hüllmaß {_t(z('huelle'))}", z("huelle")
    return "", None


def _t(w, stellen=2):
    from .stammdaten import zahl_als_text
    if w is None:
        return ""
    t = zahl_als_text(w, stellen)
    return t.rstrip("0").rstrip(",") if "," in t else t


def merkmale(p, klasse=VORGABE, schenkel=None):
    """Prüfmerkmale einer Position: [dict(nr, merkmal, soll, toleranz, lage)] (toleranz als Text ±…; '' ohne Klasse).
    schenkel = kürzerer Schenkel für die Winkeltoleranz (Profilhöhe), Vorgabe 50 mm."""
    out = []

    def neu(merkmal, soll, tol, lage=""):
        out.append(dict(nr=len(out) + 1, merkmal=merkmal, soll=soll, toleranz=tol, lage=lage))
    laenge = _n(p.get("laenge"))
    if laenge:
        tol = toleranz(laenge, klasse)
        neu("Teilelänge", f"{_t(laenge, 1)} mm", f"± {_t(tol)} mm" if tol is not None else "")
    t = technik(p)
    for ende, titel in (("a", "Anfang (Ende A)"), ("b", "Ende (Ende B)")):
        e = t.get(ende) if isinstance(t.get(ende), dict) else {}
        w = _n(e.get("winkel"))
        if w is None:
            try:
                w = _n(json.loads(p.get(f"{ende}_ende") or "{}").get("winkel"))
            except (TypeError, ValueError, AttributeError):
                w = None
        if w:
            tw = toleranz_winkel(schenkel, klasse)
            neu(f"Gehrung {titel}", f"{_t(w, 2)}° (zu rechtwinklig)", f"± {_t(tw, 2)}°" if tw is not None else "")
    for k in t.get("konturen") or ():
        if not isinstance(k, dict) or k.get("art") in GRAVUREN:
            continue
        text, mass = _mass_text(k)
        n = int(_n(k.get("anzahl")) or 1)
        lage = " ".join(x for x in (f"Seite {k['seite']}" if k.get("seite") not in (None, "") else "",
                                    f"quer {_t(_n(k.get('q')))} mm" if _n(k.get("q")) else "") if x)
        art = k.get("art") or "Kontur"
        genau = _n(k.get("genauigkeit"))       # Plan Paket 7: verlangte Genauigkeit geht vor der Allgemeintoleranz
        if k.get("massbezug"):
            lage = " ".join(x for x in (lage, f"Bezug {k['massbezug']}") if x)

        def tol_text(wert):
            if genau:
                return f"± {_t(genau)} mm (verlangt)"
            tol = toleranz(wert, klasse)
            return f"± {_t(tol)} mm" if tol is not None else ""
        if text:
            neu(f"{art}{f' ({n}×)' if n > 1 else ''}: Maß", text + " mm", tol_text(mass), lage)
        x = _n(k.get("x"))
        if x is not None and genau:
            neu(f"{art}: Lage x ab Ende A", f"{_t(x, 1)} mm", tol_text(x), lage)
        elif x is not None:
            tol = toleranz(x, klasse)
            neu(f"{art}: Lage x ab Ende A", f"{_t(x, 1)} mm", f"± {_t(tol)} mm" if tol is not None else "", lage)
        a = _n(k.get("abstand"))
        if n > 1 and a:
            tol = toleranz(a, klasse)
            neu(f"{art}: Teilung", f"{n - 1} × {_t(a, 1)} mm", f"± {_t(tol)} mm" if tol is not None else "", lage)
    return out


def positionen(positionen_):
    """Positionen mit Prüfplan: Rohrlaserteile mit Länge."""
    from .angebot import kein_laserteil
    return [p for p in positionen_ if not kein_laserteil(p) and _n(p.get("laenge"))]


def zusatz_eintragen(db, position, preis):
    """Zusatzarbeit „Erstmusterprüfung“ (€ je Angebot) im Katalog anlegen, falls sie fehlt, und an die Position
    hängen. Ergebnis: True, wenn die Position sie neu bekam."""
    from . import rechnen
    if not any(z.get("name") == ZUSATZ for z in db.zeilen("zusatzarbeiten")):
        db.neu("zusatzarbeiten", dict(name=ZUSATZ, art="€/Angebot", preis=preis, angebotstext=ZUSATZ,
                                            bemerkung="Prüfplan/Messprotokoll (Vorschlag S1), einmal je Angebot",
                                            aktiv="ja"))
    liste = rechnen.zusatz_liste(position)
    if any(z.get("name") == ZUSATZ for z in liste):
        return False
    db.position_aendern(position["id"], "zusatz", json.dumps(liste + [dict(name=ZUSATZ)], ensure_ascii=False))
    return True


def pdf(pfad, kopf, positionen_, einst, profile=None):
    """Prüfplan-PDF (A4 hoch): je Position ein Abschnitt mit Merkmalen, Ist-Spalte und Unterschrift."""
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Spacer
    from . import pdf as p_
    einst = einst or {}
    klasse = einst.get("pruef_toleranz") or VORGABE
    nr = kopf.get("nummer") or ""
    doc, leinwand = p_._dokument(pfad, f"Prüfplan {nr}", p_._fuss(einst, f"Prüfplan {nr}"))
    breite = 186 * mm
    inhalt = p_._dok_kopf("Prüfplan und Messprotokoll", kopf, einst, breite,
                          [("Angebot", nr), ("Kunde", kopf.get("kunde")), ("Ihre Anfrage", kopf.get("kundenreferenz")),
                           ("Toleranz", klasse if klasse in KLASSEN else "nach Kundenvorgabe"),
                           ("erstellt", p_._erstellt())])
    for p in positionen(positionen_):       # fortlaufend, eine Position bleibt zusammen (F3, Patrick 12.11.2026)
        h = _n(((profile or {}).get(p.get("profil_id")) or {}).get("hoehe"))
        titel = " · ".join(str(x) for x in (f"Pos. {p.get('pos')}", p.get("artikel"), p.get("bezeichnung"),
                                            p.get("profil_id"), p.get("werkstoff_id")) if x not in (None, ""))
        daten = [p_._kopfzeile(["Nr.", "Merkmal", "Lage", "Soll", "Toleranz", "Ist", "i.O. / n.i.O."])]
        for m in merkmale(p, klasse, h):
            daten.append([str(m["nr"]), p_._p(m["merkmal"], p_.S_KLEIN), p_._p(m["lage"], p_.S_KLEIN),
                          p_._p(m["soll"], p_.S_KLEIN), m["toleranz"], "", ""])
        inhalt += [KeepTogether([p_._p(titel, p_.S_H2),
                   p_._p(f"Stückzahl {p_._z(p.get('stueck') or 0, 0)} · Sollmaße aus "
                         f"{technik(p).get('quelle') or 'der Position'}; Lage x ab Ende A", p_.S_KLEIN),
                   Spacer(1, 2 * mm),
                   p_._tabelle(daten, [w * mm for w in (9, 48, 26, 32, 22, 26, 23)], zebra=False),
                   Spacer(1, 6 * mm),
                   p_._tabelle([p_._kopfzeile(["Geprüfte Teile", "Ergebnis", "Datum", "Prüfer / Unterschrift"]),
                                ["", "i.O. ____   n.i.O. ____", "", ""]], [36 * mm, 50 * mm, 34 * mm, 66 * mm], zebra=False)]),
                   Spacer(1, 8 * mm)]
    if not positionen(positionen_):
        inhalt.append(p_._p("Keine Rohrlaserteile mit Länge im Angebot.", p_.S))
    doc.build(inhalt, canvasmaker=leinwand)
    return pfad
