"""Termin-Staffel (Angebotswesen P3, 20.11.2026): Preis des Angebots je Liefertermin, z. B. Eilfertigung teurer,
früh bestellt mit langer Lieferzeit günstiger. Nur eine Darstellung im Kundenangebot und in der internen Kalkulation:
die Kalkulation und die Stückpreise des Angebots bleiben unverändert.

Einstellung termin_staffel: „1 Woche: +15; 3 Wochen: 0; 6 Wochen: -3“ (Lieferzeit: Zu- bzw. Abschlag in % auf den
Netto-Angebotspreis). Leer = aus. Ein Abschlag wird nur so weit gewährt, wie die Mindestmarge (Einstellung
mindestmarge, Gewinn am Warenwert ohne Fracht und Skonto) es erlaubt, wie bei den Staffeln (staffeln.marge_anhebung).
"""
import re

from . import rechnen
from .ausgabe import kaufm_runden

_TEIL = re.compile(r"^\s*(?P<termin>[^:=]+?)\s*[:=]\s*(?P<satz>[+\-−]?\s*\d+(?:[.,]\d+)?)\s*%?\s*$")


def lesen(text):
    """[(Termin, Satz als Anteil)] aus dem Text der Einstellung; unlesbare Teile werden übergangen."""
    out = []
    for teil in re.split(r"[;\n]", str(text or "")):
        m = _TEIL.match(teil)
        if not m:
            continue
        satz = m.group("satz").replace("−", "-").replace(" ", "").replace(",", ".")
        try:
            out.append((m.group("termin").strip(), float(satz) / 100))
        except ValueError:
            continue
    return out


def fehler(text):
    """Teile des Textes, die nicht gelesen werden können (für die Prüfung der Einstellung)."""
    return [t.strip() for t in re.split(r"[;\n]", str(text or "")) if t.strip() and not _TEIL.match(t)]


def rechnen_termine(einst, netto, summen):
    """Je Termin der Netto-Angebotspreis und die Marge. netto = Netto des Angebots (gerundete Positionen), summen =
    Summen der Kalkulation (selbst, gewinn, skonto_satz). Ergebnis: [dict(termin, satz, satz_wirksam, netto, differenz,
    marge, begrenzt)], leer ohne Einstellung."""
    termine = lesen((einst or {}).get("termin_staffel"))
    if not termine or not netto:
        return []
    selbst = rechnen._n(summen.get("selbst"))
    gewinn = rechnen._n(summen.get("gewinn"))
    sk = rechnen._n(summen.get("skonto_satz"))
    sk = sk if 0 <= sk < 1 else 0.0
    m = rechnen._n((einst or {}).get("mindestmarge"))
    m = m if 0 < m < 1 else 0.0
    out = []
    for termin, satz in termine:
        diff = netto * satz
        begrenzt = False
        if satz < 0 and m and selbst > 0:
            # kleinster erlaubter Unterschied auf den Warenwert: Gewinn + Δ·(1 − Skonto) ≥ m·S/(1 − m)
            grenze = (m * selbst / (1 - m) - gewinn) / (1 - sk)
            if diff < grenze:
                diff, begrenzt = min(0.0, grenze), True
        neu = kaufm_runden(netto + diff, 2)
        g = gewinn + (neu - netto) * (1 - sk)
        ware = selbst + g
        out.append(dict(termin=termin, satz=satz, satz_wirksam=(neu - netto) / netto, netto=neu,
                        differenz=kaufm_runden(neu - netto, 2), marge=g / ware if ware > 0 else None,
                        begrenzt=begrenzt))
    return out
