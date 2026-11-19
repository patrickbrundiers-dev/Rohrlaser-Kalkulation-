"""Stehende Maße im 3D und Messprotokoll (Messplan 19.11.2026, Phase M2). Ohne Fenster.

Ein Maß ist ein kleines Datenobjekt (Konzept „Befehle als Daten“): Punkte, Text und dazu Art, Wert, Einheit, Name
und sichtbar. Damit gehen Anzeige, Ein-/Ausblenden, Löschen, Kopieren, CSV und PDF-Messprotokoll auf einem Weg.
Mass ist ein Tupel (Punkte, Text) wie bisher (ansicht3d.masse_fest), mit den übrigen Angaben als Attribute; alter
Code, der (punkte, text) auspackt, läuft unverändert weiter. Messen ändert nie etwas am Teil."""
import csv
import io
import math

from .mess_kern import winkel_bei, zahl

ABSTAND, WINKEL, LINIENZUG = "Abstand", "Winkel", "Linienzug"


class Mass(tuple):
    """Stehendes Maß: (Punkte, Text) mit art, wert, einheit, name, sichtbar, arten (Fangart je Punkt)."""

    def __new__(cls, punkte, text, art=None, wert=None, einheit=None, name="", sichtbar=True, arten=None):
        punkte = [tuple(float(c) for c in q) for q in punkte]
        m = super().__new__(cls, (punkte, text))
        if art is None:
            art = WINKEL if len(punkte) == 3 and text and str(text).startswith("Winkel") else \
                ABSTAND if len(punkte) == 2 else LINIENZUG
        m.art = art
        if wert is None and punkte:
            if art == WINKEL and len(punkte) == 3:
                wert = winkel_bei(*punkte)
            else:
                wert = sum(math.dist(a, b) for a, b in zip(punkte, punkte[1:]))
        m.wert = wert
        m.einheit = einheit or ("°" if art == WINKEL else "mm")
        m.name = name or ""
        m.sichtbar = bool(sichtbar)
        m.arten = list(arten) if arten else [None] * len(punkte)
        return m

    @property
    def punkte(self):
        return self[0]

    @property
    def text(self):
        return self[1]

    def kopie(self, **aenderung):
        d = self.als_dict()
        d.update(aenderung)
        return aus_dict(d)

    def als_dict(self):
        return dict(punkte=[list(q) for q in self.punkte], text=self.text, art=self.art, wert=self.wert,
                    einheit=self.einheit, name=self.name, sichtbar=self.sichtbar, arten=list(self.arten))


def aus_dict(d):
    return Mass(d.get("punkte") or [], d.get("text") or "", d.get("art"), d.get("wert"), d.get("einheit"),
                d.get("name") or "", d.get("sichtbar", True), d.get("arten"))


def wert_aus_text(text):
    """(Wert, Einheit) aus dem Hauptwert einer Messung („Abstand Fläche–Fläche 12,500 mm“, „Winkel 90,00°“) oder
    None. Ein „≈“ bleibt im Text, der Wert ist dann der genäherte."""
    import re
    m = re.search(r"(-?\d[\d.]*,\d+|-?\d+)\s*(mm²|mm|°)", str(text or ""))
    if not m:
        return None
    return float(m.group(1).replace(".", "").replace(",", ".")), m.group(2)


def als_mass(m):
    """Altes (Punkte, Text)-Tupel oder Mass -> Mass."""
    return m if isinstance(m, Mass) else Mass(m[0], m[1])


def wert_text(m):
    m = als_mass(m)
    if m.wert is None:
        return ""
    return f"{zahl(m.wert, 2 if m.einheit == '°' else 3)}{'' if m.einheit == '°' else ' '}{m.einheit}"


def zeilen(masse, lage=None):
    """Tabellenzeilen [Nr, Name, Art, Wert, Messung, Punkte] für Liste, CSV und PDF. lage(p) -> Text."""
    out = []
    for nr, m in enumerate((als_mass(x) for x in masse), 1):
        pk = " | ".join(lage(q) if lage is not None else " / ".join(zahl(c) for c in q) for q in m.punkte)
        out.append([str(nr), m.name or f"Maß {nr}", m.art, wert_text(m), m.text or "", pk])
    return out


KOPF = ["Nr.", "Name", "Art", "Wert", "Messung", "Punkte"]


def csv_text(masse, lage=None, kopf=()):
    """Maße als CSV (Trennzeichen ;, deutsche Zahlen) – öffnet sich in Excel mit richtigen Spalten. kopf: Zeilen
    [(Name, Wert)] davor (Teil, Datum …)."""
    f = io.StringIO()
    w = csv.writer(f, delimiter=";", lineterminator="\r\n")
    for k, v in kopf:
        w.writerow([k, v])
    if kopf:
        w.writerow([])
    w.writerow(KOPF)
    for z in zeilen(masse, lage):
        w.writerow(z)
    return f.getvalue()


def klartext(masse, lage=None):
    return "\n".join(f"{z[0]}  {z[1]}: {z[4] or z[3]}" for z in zeilen(masse, lage))


def _pdf_text(t):
    """Standardschrift des PDF (WinAnsi) kennt ≈ und Δ nicht: lesbar ersetzen."""
    return str(t).replace("≈ ", "ca. ").replace("≈", "ca. ").replace("Δ", "d")


def pdf_schreiben(pfad, masse, titel="Messprotokoll", angaben=(), bild_png=None, lage=None, einst=None):
    """Messprotokoll als PDF (A4): Kopf mit Angaben [(Name, Wert)], optional Bild der 3D-Ansicht (PNG-Bytes),
    Tabelle aller Maße. Ergebnis: pfad."""
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image, Spacer

    from . import pdf as p_
    einst = einst or {}
    doc, leinwand = p_._dokument(pfad, titel, p_._fuss(einst, titel))
    breite = 186 * mm
    inhalt = p_._dok_kopf(titel, {}, einst, breite, list(angaben) or None)
    if bild_png:
        r = ImageReader(io.BytesIO(bild_png))
        bw, bh = r.getSize()
        b = min(breite, bw)
        h = b * bh / bw
        if h > 110 * mm:
            h, b = 110 * mm, 110 * mm * bw / bh
        inhalt += [Image(io.BytesIO(bild_png), width=b, height=h), Spacer(1, 4 * mm)]
    daten = [p_._kopfzeile(KOPF[:5])]
    for z in zeilen(masse, lage):
        daten.append([z[0], p_._p(_pdf_text(z[1]), p_.S_KLEIN), z[2], z[3], p_._p(_pdf_text(z[4]), p_.S_KLEIN)])
    if len(daten) == 1:
        daten.append(["–", "keine Maße", "", "", ""])
    inhalt.append(p_._tabelle(daten, [w * mm for w in (10, 38, 22, 30, 86)], rechts=(3,), zebra=True))
    inhalt += [Spacer(1, 4 * mm), p_._p("Lage der Punkte", p_.S_H2)]
    daten = [p_._kopfzeile(["Nr.", "Punkte"])] + [[z[0], p_._p(z[5], p_.S_KLEIN)] for z in zeilen(masse, lage)]
    if len(daten) > 1:
        inhalt.append(p_._tabelle(daten, [10 * mm, 176 * mm], zebra=False))
    inhalt.append(p_._p("Gemessen am 3D-Modell mit dem Messkern des Programms; Werte mit „ca.“ sind am Netz "
                        "gewölbter Flächen genähert. Das Messen ändert nichts am Teil.", p_.S_KLEIN))
    doc.build(inhalt, canvasmaker=leinwand)
    return pfad
