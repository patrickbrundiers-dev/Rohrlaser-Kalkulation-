"""Entfernung zwischen zwei deutschen Postleitzahlen (Frachtkosten, Patrick 11.11.2026), ohne Internet.

Datei plz_geo.json neben dieser Datei: Mittelpunkt (Breite, Länge) aller rund 8.300 fünfstelligen PLZ in Deutschland
aus dem GeoNames Postal Code Dataset (https://www.geonames.org, Lizenz CC BY 4.0); liegen mehrere Orte in einer PLZ,
gilt das Mittel der Orte. Fehlt eine PLZ (neu vergeben), gilt der Mittelpunkt der zweistelligen PLZ-Region
(fracht_richtwerte.REGIONEN) mit Hinweis "ungefähr".

Straßen-km = Luftlinie × Umwegfaktor (Einstellung fracht_umwegfaktor, Vorgabe 1,35: Stichproben ab Delbrück mit den
Straßen-km der Routenplaner (Lippstadt, Detmold, Dortmund, Hamburg) lagen bei 1,25 zu kurz, lieber etwas zu weit
als zu kurz).
Genauigkeit etwa ±10–15 %; bei großen Land-PLZ (viele Dörfer) kann der Mittelpunkt bis zu 20 km vom Ort entfernt sein.
Nur Deutschland (Freigabe F2a); für andere Länder gibt es keine km (dann gilt die Zone wie bisher).
"""
import json
import math
import os

UMWEG_VORGABE = 1.35
EINSTELLUNG = "fracht_umwegfaktor"
QUELLE_PLZ = "PLZ"               # km aus den PLZ-Mittelpunkten
QUELLE_HAND = "von Hand"         # km im Angebot bzw. im Frachtrechner eingetragen
_PUNKTE = None


def punkte():
    """{PLZ: (Breite, Länge)} aus plz_geo.json (einmal geladen); fehlt die Datei: leer."""
    global _PUNKTE
    if _PUNKTE is None:
        pfad = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plz_geo.json")
        try:
            with open(pfad, encoding="utf-8") as f:
                _PUNKTE = {k: tuple(v) for k, v in json.load(f)["plz"].items()}
        except (OSError, ValueError, KeyError):
            _PUNKTE = {}
    return _PUNKTE


def _ziffern(plz):
    return "".join(c for c in str(plz or "") if c.isdigit())


def punkt(plz, land="DE"):
    """(Breite, Länge, genau) einer deutschen PLZ: genau = True für die fünfstellige PLZ, False für den Mittelpunkt
    der PLZ-Region; None, wenn das Land nicht DE ist oder die PLZ keine fünf Ziffern hat."""
    if (land or "DE").strip().upper() != "DE":
        return None
    p = _ziffern(plz)
    if len(p) != 5:
        return None
    if p in punkte():
        return (*punkte()[p], True)
    from .fracht_richtwerte import REGIONEN
    r = REGIONEN.get(p[:2])
    return (*r, False) if r else None


def faktor(wert):
    """Umwegfaktor aus der Einstellung (1,0–2,0), sonst die Vorgabe."""
    try:
        f = float(str(wert).replace(",", "."))
    except (TypeError, ValueError):
        return UMWEG_VORGABE
    return f if 1.0 <= f <= 2.0 else UMWEG_VORGABE


def luftlinie(a, b):
    """km Luftlinie zwischen (Breite, Länge) a und b."""
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    d = math.radians(b[1] - a[1])
    c = math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(d)
    return 6371 * math.acos(max(-1.0, min(1.0, c)))


def km(von_plz, nach_plz, von_land="DE", nach_land="DE", umweg=None):
    """Straßen-km (geschätzt, ganze km, mindestens 1) zwischen zwei PLZ: (km, Text) oder (None, Grund)."""
    a, b = punkt(von_plz, von_land), punkt(nach_plz, nach_land)
    if a is None or b is None:
        fehlt = []
        if a is None:
            fehlt.append(f"Versandort {von_land or 'DE'} {von_plz or '(leer)'}")
        if b is None:
            fehlt.append(f"Ziel {nach_land or 'DE'} {nach_plz or '(leer)'}")
        return None, ("keine Entfernung (nur volle deutsche PLZ): " + ", ".join(fehlt))
    f = faktor(umweg)
    wert = max(1, round(luftlinie(a, b) * f))
    fs = f"{f:g}".replace(".", ",")
    text = f"ca. {wert} km (PLZ {_ziffern(von_plz)} → {_ziffern(nach_plz)}, Luftlinie × {fs})"
    if not (a[2] and b[2]):
        text += ", ungefähr: PLZ nicht in der Liste, Mittelpunkt der PLZ-Region"
    return wert, text


def ergaenzen(s):
    """Sendung s (dict) um die Entfernung ergänzen, wenn km fehlt: s['km'], s['km_quelle'] = 'PLZ', s['km_text'].
    Ein eingetragener km-Wert bleibt (km_quelle 'von Hand', wenn nicht gesetzt). Ergebnis: s."""
    if s.get("km") not in (None, ""):
        s.setdefault("km_quelle", QUELLE_HAND)
        if s.get("km_quelle") == QUELLE_HAND:
            s.setdefault("km_text", f"{s['km']:g} km von Hand".replace(".", ",") if isinstance(s["km"], (int, float))
                         else f"{s['km']} km von Hand")
        return s
    wert, text = km(s.get("absender_plz"), s.get("plz"), s.get("absender_land") or "DE", s.get("land") or "DE",
                    s.get("umwegfaktor"))
    if wert is not None:
        s.update(km=wert, km_quelle=QUELLE_PLZ, km_text=text)
    return s
