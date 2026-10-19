"""CSV-Export eines Angebots (Werte): Angebotskopf, Kostenarten und Kalkulation je Position.

Semikolon als Trennzeichen, Dezimalkomma, UTF-8 mit BOM – so öffnen es deutsche Tabellenprogramme direkt.
Vorläufiger Inhalt, bis die genaue Aufteilung feststeht.
"""
import csv

from .angebot import KOPF
from .angebot_spalten import KALK_SPALTEN
from .rechnen import kostenarten
from .stammdaten import wert_als_text, zahl_als_text


def _zelle(w, stellen):
    if w is None:
        return ""
    if isinstance(w, bool):
        return "ja" if w else "nein"
    if isinstance(w, (int, float)):
        return zahl_als_text(w, stellen, tausender=False)
    return str(w)


def angebot_csv(pfad, kopf, kalk_zeilen, summen, einst):
    with open(pfad, "w", encoding="utf-8-sig", newline="") as datei:
        w = csv.writer(datei, delimiter=";")
        w.writerow(["Angebot"])
        for f in KOPF:
            w.writerow([f.titel, wert_als_text(f, kopf.get(f.name), bearbeiten=True)])
        w.writerow([])
        w.writerow(["Kostenart", "Betrag [€]"])
        for t, betrag, _ in kostenarten(summen, einst):
            w.writerow([t, _zelle(betrag, 2)])
        w.writerow([])
        w.writerow([t for t, _, _, _ in KALK_SPALTEN])
        for z in kalk_zeilen:
            if z:
                w.writerow([_zelle(s(z) if callable(s) else z.get(s), st) for _, s, st, _ in KALK_SPALTEN])
