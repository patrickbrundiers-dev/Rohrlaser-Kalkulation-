"""Grundwerte-Check der Kalkulation (Prüfung Kalkulationsbasis 1 und 5, Patrick 02.11.2026 „Alle Empfehlungen“).

Zeigt, welche Grundwerte leer sind und deshalb nicht mitrechnen, und wo dieselben Kosten doppelt zählen. Ändert keinen
Preis. Genutzt von der Seite „Grundwerte prüfen“ (Einstellungen → Kosten und Stundensatz) und vom Angebots-Check.

1. Leere Grundwerte: Nebenzeit je Teil und Zeit je Kontur der Maschine (Laserzeit dann nur reines Schneiden),
   Stundensätze mit der Bemerkung „Beispielwert“, Zuschlag Material 0, Schneidgas beim ermittelten Stundensatz
   ohne Gaspreis und ohne €/h. Im Angebot dazu die Wirkung in €: derselbe Preis mit den Richtwerten (RICHTWERTE).
5. Doppelzählung: ermittelter Stundensatz mit Gemeinkosten und zusätzlich Zuschlag Fertigung; Staffel-Feld
   „Materialverlust / Ausschuss“ und Einstellung Ausschuss; Zusatzarbeit Entgraten und Arbeitsschritt Entgraten
   mit Zeit. Ohne Qt."""
import dataclasses

# Richtwerte für die €-Wirkung leerer Maschinenfelder (geschätzt, an der Maschine messen)
RICHTWERTE = {"zeit_teil": 8.0, "zeit_kontur": 1.5}
FELD_TEXT = {"zeit_teil": "Nebenzeit je Teil (Ausschieben/Entnehmen)", "zeit_kontur": "Zeit je Kontur (Anfahren/Drehen)"}
BEISPIEL = "beispielwert"


def _n(w):
    return float(w) if isinstance(w, (int, float)) and not isinstance(w, bool) else 0.0


def _leer(w):
    return w is None or w == "" or (isinstance(w, (int, float)) and not isinstance(w, bool) and w == 0)


def _z(w, stellen=2):
    from .stammdaten import zahl_als_text
    return zahl_als_text(w, stellen)


def maschine_leer(m):
    """Leere Zeitfelder einer Maschinenzeile: [Feldname]."""
    return [n for n in RICHTWERTE if _leer((m or {}).get(n))]


def doppelt_stundensatz(m, einst):
    """Text, wenn der ermittelte Stundensatz Gemeinkosten enthält und zusätzlich ein Zuschlag Fertigung gilt."""
    from . import stundensatz
    gk, zf = _n((einst or {}).get("gemeinkosten")), _n((einst or {}).get("zuschlag_fertigung"))
    if stundensatz.ermittelt(m) and stundensatz.ermitteln(m, einst) is not None and gk > 0 and zf > 0:
        return (f"Maschine {m.get('maschinen_id')}: Der ermittelte Stundensatz enthält {_z(100 * gk, 1)} % Gemeinkosten, "
                f"dazu kommt der Zuschlag Fertigung {_z(100 * zf, 1)} %. Gemeinkosten zählen so doppelt.")
    return None


def doppelt_entgraten(tabellen, namen=None):
    """Text, wenn ein Arbeitsschritt „Entgraten …“ eine Zeit hat und die Zusatzarbeit Entgraten (namen = im Angebot
    genutzte Zusatzarbeiten; None = aktiv in den Stammdaten) ebenfalls gerechnet wird."""
    schritte = [z for z in (tabellen or {}).get("arbeitsschritte") or ()
                if "entgrat" in str(z.get("schritt") or "").lower() and (_n(z.get("zeit")) or _n(z.get("ruestzeit")))]
    if not schritte:
        return None
    if namen is None:
        namen = [z.get("name") for z in (tabellen or {}).get("zusatzarbeiten") or ()
                 if str(z.get("aktiv") or "ja") != "nein" and _n(z.get("preis"))]
    if not any("entgrat" in str(n or "").lower() for n in namen):
        return None
    return (f"Arbeitsschritt „{schritte[0].get('schritt')}“ hat eine Zeit und die Zusatzarbeit Entgraten wird auch "
            "gerechnet: Entgraten zählt doppelt.")


def doppelt_ausschuss(einst, stufen=()):
    """Text, wenn Staffelstufen einen eigenen Materialverlust haben und zusätzlich die Einstellung Ausschuss gilt."""
    a = _n((einst or {}).get("ausschuss"))
    st = [s for s in stufen or () if _n(s.get("verlust")) > 0]
    if a <= 0 or not st:
        return None
    return (f"{len(st)} Staffelstufe(n) mit eigenem Materialverlust/Ausschuss, dazu Ausschuss {_z(100 * a, 1)} % "
            "in den Einstellungen: der Materialverlust zählt doppelt.")


def punkte(k, tabellen, einst, maschinen=None):
    """Grundwerte-Check der Stammdaten und Einstellungen: [(Art, Bereich, Text)], Art 'WARNUNG' (Doppelzählung) oder
    'HINWEIS' (leer). maschinen = Maschinen-IDs (None = alle)."""
    from . import stundensatz
    out = []
    for mid, m in sorted((k.maschinen if k else {}).items()):
        if maschinen is not None and mid not in maschinen:
            continue
        for n in maschine_leer(m):
            out.append(("HINWEIS", f"Maschine {mid}", f"{FELD_TEXT[n]} ist leer: die Laserzeit enthält diese Zeit "
                                                      f"nicht (Richtwert {_z(RICHTWERTE[n], 1)} s, bitte messen)."))
        if stundensatz.gas_rechnen(m) and not _n((einst or {}).get("gaspreis_n2")) and not _n(m.get("gas_n2")) \
                and (einst or {}).get("gas_rechnen") != "nein":
            out.append(("HINWEIS", f"Maschine {mid}", "Schneidgas soll zusätzlich zum Stundensatz zählen, es gibt aber "
                                                      "weder Gaspreis N₂ noch €/h für N₂: Gas rechnet mit 0."))
        t = doppelt_stundensatz(m, einst)
        if t:
            out.append(("WARNUNG", f"Maschine {mid}", t))
    for z in (tabellen or {}).get("stundensaetze") or ():
        if BEISPIEL in str(z.get("bemerkung") or "").lower():
            out.append(("HINWEIS", "Stundensätze", f"Stundensatz „{z.get('satz_id')}“ ({_z(_n(z.get('satz')))} €/h) "
                                                   "ist noch ein Beispielwert."))
    if not _n((einst or {}).get("zuschlag_material")):
        out.append(("HINWEIS", "Zuschläge", "Zuschlag Material ist 0: Einkauf, Lager und Kapitalbindung des Materials "
                                            "rechnen nicht mit."))
    t = doppelt_entgraten(tabellen)
    if t:
        out.append(("WARNUNG", "Arbeitsschritte", t))
    return out


def wirkung(kopf, positionen, ergebnis, k, tabellen, einst):
    """€-Wirkung der leeren Zeitfelder der Angebotsmaschine: dict(felder, vorher, nachher, plus, prozent) mit den
    Richtwerten gerechnet, oder None (nichts leer, keine Rechnung)."""
    from . import rechnen
    m = rechnen.maschine(kopf, k)
    leer = maschine_leer(m)
    if not m or not leer or not ergebnis:
        return None
    try:
        _, s0 = rechnen.kalkulation(kopf, positionen, ergebnis, k, tabellen, einst)
        m2 = dict(m, **{n: RICHTWERTE[n] for n in leer})
        k2 = dataclasses.replace(k, maschinen=dict(k.maschinen, **{kopf.get("maschine"): m2}))
        _, s1 = rechnen.kalkulation(kopf, positionen, ergebnis, k2, tabellen, einst)
    except Exception:           # Hinweis, nie wichtiger als das Angebot
        return None
    vorher, nachher = _n(s0.get("verkauf")), _n(s1.get("verkauf"))
    if vorher <= 0:
        return None
    return dict(felder=leer, vorher=vorher, nachher=nachher, plus=nachher - vorher, prozent=100 * (nachher / vorher - 1))


def angebot_punkte(kopf, positionen, ergebnis, k, tabellen, einst, stufen=(), wirkung_=None):
    """Angebots-Check: [(Art, Text, None)] – leere Zeitfelder der Maschine mit €-Wirkung und die Doppelzählungen,
    die dieses Angebot betreffen."""
    from . import rechnen
    out = []
    w = wirkung_ if wirkung_ is not None else wirkung(kopf, positionen, ergebnis, k, tabellen, einst)
    if w and abs(w["plus"]) >= 0.005:
        felder = " und ".join(FELD_TEXT[n] for n in w["felder"])
        out.append(("HINWEIS", f"Maschine {kopf.get('maschine')}: {felder} leer. Mit Richtwerten "
                               f"({', '.join(_z(RICHTWERTE[n], 1) + ' s' for n in w['felder'])}) läge das Angebot bei "
                               f"{_z(w['nachher'])} € statt {_z(w['vorher'])} € ({'+' if w['plus'] >= 0 else ''}"
                               f"{_z(w['prozent'], 1)} %). Zeiten unter Stammdaten → Maschinen eintragen.", None))
    m = rechnen.maschine(kopf, k)
    t = doppelt_stundensatz(m, einst) if m else None
    if t:
        out.append(("WARNUNG", t, None))
    namen = {e.get("name") for p in positionen for e in rechnen.zusatz_liste(p) if isinstance(e, dict)}
    t = doppelt_entgraten(tabellen, namen) if namen else None
    if t:
        out.append(("WARNUNG", t, None))
    t = doppelt_ausschuss(einst, stufen)
    if t:
        out.append(("WARNUNG", t, None))
    return out
