"""PDF-Ausgabe: Angebot, Werkstattpapiere (Schnittpläne mit Stangenbild) und Kalkulation.

Die Inhalte kommen aus ausgabe.py; hier wird nur gesetzt (reportlab, A4).
"""
import base64
import datetime
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether, LongTable,
                                Image, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.pdfgen import canvas as rl_canvas

from . import ausgabe, querschnitt, rechnen
from .rechnen import kostenarten
from .stammdaten import zahl_als_text

SCHRIFT, FETT = "Helvetica", "Helvetica-Bold"
BLAU = colors.HexColor("#1F4E78")
HELLBLAU = colors.HexColor("#DDEBF7")
STAFFEL_FLAECHE = colors.HexColor("#F3F6FA")     # Kasten der Staffelpreise im Angebot
ROT = colors.HexColor("#C00000")
TEILFARBEN = ["#BDD7EE", "#C6E0B4", "#FFE699", "#D9D2E9", "#B4C6E7", "#F8CBAD", "#CCECFF", "#E2EFDA", "#EDEDBE"]

S = ParagraphStyle("normal", fontName=SCHRIFT, fontSize=9, leading=11)
S_KLEIN = ParagraphStyle("klein", parent=S, fontSize=8, leading=9.5)
S_FETT = ParagraphStyle("fett", parent=S, fontName=FETT)
S_KOPF = ParagraphStyle("kopf", parent=S, fontName=FETT, textColor=BLAU, fontSize=8, leading=9.5)
S_RECHTS = ParagraphStyle("rechts", parent=S, alignment=TA_RIGHT)
S_TITEL = ParagraphStyle("titel", parent=S, fontName=FETT, fontSize=18, leading=22, textColor=BLAU)
S_H2 = ParagraphStyle("h2", parent=S, fontName=FETT, fontSize=11, leading=14, spaceBefore=6, spaceAfter=3,
                      textColor=BLAU)
S_ROT = ParagraphStyle("rot", parent=S_FETT, textColor=ROT)
ZEBRA = colors.HexColor("#F3F7FB")
LINIE = colors.HexColor("#D9D9D9")
GRAU = colors.HexColor("#595959")
GRUEN = colors.HexColor("#2E7D32")


def _z(w, stellen=2):
    if not isinstance(w, (int, float)) or isinstance(w, bool):
        return "" if w is None else str(w)
    if stellen is not None and round(w, stellen) == 0:      # kein "-0,00" aus Gleitkommaresten
        w = 0
    return zahl_als_text(w, stellen)


def _p(text, stil=S):
    t = "" if text is None else str(text)
    return Paragraph(t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>"), stil)


class _Seitenzahlen(rl_canvas.Canvas):
    """Canvas mit 'Seite x von y' und Fußzeilentext auf jeder Seite."""
    fuss = ""
    linie = None        # Farbe einer feinen Linie über der Fußzeile, None = keine

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._seiten = []

    def showPage(self):
        self._seiten.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._seiten)
        for i, zustand in enumerate(self._seiten, start=1):
            self.__dict__.update(zustand)
            breite = self._pagesize[0]
            if self.linie is not None:
                self.setStrokeColor(self.linie)
                self.setLineWidth(0.5)
                self.line(12 * mm, 11.5 * mm, breite - 12 * mm, 11.5 * mm)
            self.setFont(SCHRIFT, 7.5)
            self.setFillColor(colors.HexColor("#595959"))
            self.drawString(12 * mm, 8 * mm, self.fuss)
            self.drawRightString(breite - 12 * mm, 8 * mm, f"Seite {i} von {n}")
            super().showPage()
        super().save()


OHNE_RAND = dict(leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)


def _dokument(pfad, titel, fuss, quer=False, auch_quer=False):
    hoch = landscape(A4) if quer else A4
    doc = BaseDocTemplate(str(pfad), pagesize=hoch, title=titel, author="Rohrlaser-Angebotskalkulation",
                          leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=15 * mm)
    vorlagen = [PageTemplate(id="hoch", pagesize=hoch,
                             frames=[Frame(12 * mm, 15 * mm, hoch[0] - 24 * mm, hoch[1] - 27 * mm, id="f1", **OHNE_RAND)])]
    if auch_quer:
        q = landscape(A4)
        vorlagen.append(PageTemplate(id="quer", pagesize=q,
                                     frames=[Frame(12 * mm, 15 * mm, q[0] - 24 * mm, q[1] - 27 * mm, id="f2", **OHNE_RAND)]))
    doc.addPageTemplates(vorlagen)
    leinwand = type("Leinwand", (_Seitenzahlen,), {"fuss": fuss, "linie": BLAU})
    return doc, leinwand


def _tabelle(daten, breiten, kopfzeilen=1, rechts=(), fett_zeilen=(), wiederholen=True, zebra=True):
    """Liste im Stil des Angebots: ohne Gitter, Kopf dunkelblau mit Linie, feine Linien zwischen den Zeilen, jede
    zweite Zeile leicht hinterlegt; fett_zeilen (Summen) hellblau."""
    for zeile in daten[:kopfzeilen]:       # Kopf über Zahlenspalten rechtsbündig wie die Werte
        for c in rechts:
            if isinstance(zeile[c], Paragraph):
                zeile[c].style = ParagraphStyle(zeile[c].style.name + "_r", parent=zeile[c].style, alignment=TA_RIGHT)
    t = LongTable(daten, colWidths=breiten, repeatRows=kopfzeilen if wiederholen else 0)
    stil = [("FONT", (0, 0), (-1, -1), SCHRIFT, 8.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (0, kopfzeilen), (-1, -1), 0.3, LINIE)]
    if kopfzeilen:
        stil += [("LINEBELOW", (0, kopfzeilen - 1), (-1, kopfzeilen - 1), 1, BLAU),
                 ("VALIGN", (0, 0), (-1, kopfzeilen - 1), "BOTTOM"), ("FONT", (0, 0), (-1, kopfzeilen - 1), FETT, 8)]
    if zebra:
        stil.append(("ROWBACKGROUNDS", (0, kopfzeilen), (-1, -1), [colors.white, ZEBRA]))
    for c in rechts:
        stil.append(("ALIGN", (c, kopfzeilen), (c, -1), "RIGHT"))
    for r in fett_zeilen:
        stil += [("FONT", (0, r), (-1, r), FETT, 8.5), ("BACKGROUND", (0, r), (-1, r), HELLBLAU)]
    t.setStyle(TableStyle(stil))
    return t


def _dok_kopf(titel, kopf, einst, breite, angaben=None, warnung=None):
    """Kopf der internen PDFs: Firmenname klein, Titel groß, kleines Logo rechts, Linie; darunter die Angaben
    (Bezeichnung grau über dem Wert) und ggf. eine rote Warnung."""
    firma = (einst or {}).get("briefkopf_1") or ""
    links = ([_p(firma, ParagraphStyle("fk", parent=S, fontSize=8, textColor=GRAU))] if firma else []) + \
        [_p(titel, S_TITEL)]
    logo = logo_bild(einst, 32 * mm, 13 * mm)
    t = Table([[links, logo or ""]], colWidths=[breite - 40 * mm, 40 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LINEBELOW", (0, 0), (-1, 0), 1.2, BLAU)]))
    if angaben is None:
        angaben = [("Angebot", kopf.get("nummer")), ("Kunde", kopf.get("kunde")), ("Maschine", kopf.get("maschine")),
                   ("erstellt", _erstellt())]
    angaben = [(a, b) for a, b in angaben if b not in (None, "")]
    inhalt = [t, Spacer(1, 3 * mm)]
    if angaben:
        grau = ParagraphStyle("ag", parent=S, fontSize=7, leading=8.5, textColor=GRAU)
        a = Table([[_p(x, grau) for x, _ in angaben], [_p(y, S_FETT) for _, y in angaben]],
                  colWidths=[min(55 * mm, breite / len(angaben))] * len(angaben), hAlign="LEFT")
        a.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5)]))
        inhalt.append(a)
    if warnung:
        inhalt += [Spacer(1, 2 * mm), _p(warnung, S_ROT)]
    return inhalt + [Spacer(1, 4 * mm)]


def _kacheln(werte, breite, je_zeile=None):
    """Kennzahlen als Kacheln: [(Bezeichnung, Wert[, Farbe])] nebeneinander, hellblau hinterlegt."""
    n = je_zeile or len(werte)
    abstand = 3 * mm
    w = (breite - abstand * (n - 1)) / n
    grau = ParagraphStyle("kg", parent=S, fontSize=7.5, leading=9, textColor=GRAU)
    zellen, spalten = [], []
    for i, x in enumerate(werte):
        farbe = x[2] if len(x) > 2 and x[2] is not None else BLAU
        zellen.append([_p(x[0], grau), _p(x[1], ParagraphStyle("kw", parent=S_FETT, fontSize=12.5, leading=15,
                                                              textColor=farbe))])
        spalten.append(w)
        if i < len(werte) - 1:
            zellen.append("")
            spalten.append(abstand)
    stil = [("LEFTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "TOP")]
    stil += [("BACKGROUND", (2 * i, 0), (2 * i, 0), HELLBLAU) for i in range(len(werte))]
    t = Table([zellen], colWidths=spalten, hAlign="LEFT")
    t.setStyle(TableStyle(stil))
    return t


class Kaestchen(Flowable):
    """Leeres Kästchen zum Abhaken (Werkstattpapiere)."""

    def wrap(self, breite, hoehe):
        return 4.5 * mm, 4.5 * mm

    def draw(self):
        self.canv.setStrokeColor(colors.HexColor("#404040"))
        self.canv.setLineWidth(0.8)
        self.canv.rect(0, 0.3 * mm, 4.2 * mm, 4.2 * mm, fill=0, stroke=1)


def _kopfzeile(texte):
    return [_p(t, S_KOPF) for t in texte]


def _erstellt():
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M")


# ------------------------------------------------------------------ Angebot
S_A = ParagraphStyle("a", parent=S, fontSize=9, leading=11.5)
S_A_FETT = ParagraphStyle("a_fett", parent=S_A, fontName=FETT)
S_A_GRAU = ParagraphStyle("a_grau", parent=S_A, textColor=GRAU)
S_A_RECHTS = ParagraphStyle("a_rechts", parent=S_A, alignment=TA_RIGHT)
S_A_STAFFEL = ParagraphStyle("a_staffel", parent=S_A_RECHTS, textColor=colors.HexColor("#404040"))
S_A_KOPF = ParagraphStyle("a_kopf", parent=S_A, fontName=FETT, textColor=BLAU, fontSize=8.5)
S_A_KOPF_R = ParagraphStyle("a_kopf_r", parent=S_A_KOPF, alignment=TA_RIGHT)
S_A_TITEL = ParagraphStyle("a_titel", parent=S, fontName=FETT, fontSize=18, leading=22, textColor=BLAU)
S_A_FIRMA = ParagraphStyle("a_firma", parent=S, fontName=FETT, fontSize=13, leading=16, textColor=BLAU)
S_A_ABSENDER = ParagraphStyle("a_absender", parent=S, fontSize=6.5, leading=8, textColor=GRAU)
S_A_ANSCHRIFT = ParagraphStyle("a_anschrift", parent=S, fontSize=10, leading=13)


def logo_bild(einst, breite=55 * mm, hoehe=24 * mm):
    """Firmenlogo aus der Einstellung 'logo' (Bilddaten als Base64) in die Box breite x hoehe eingepasst;
    None ohne oder mit unlesbarem Logo."""
    daten = (einst or {}).get("logo") or ""
    if not daten:
        return None
    try:
        roh = io.BytesIO(base64.b64decode(daten.split(",", 1)[-1]))
        b, h = ImageReader(roh).getSize()
        f = min(breite / b, hoehe / h)
        roh.seek(0)
        bild = Image(roh, width=b * f, height=h * f, mask="auto")
    except Exception:       # beschädigte Einstellung: Angebot ohne Logo statt Abbruch
        return None
    bild.hAlign = "RIGHT"
    return bild


STAFFEL_HINWEIS = "Staffelpreise bei Einzelbestellung dieser Position"
STAFFEL_HINWEIS_SATZ = "Staffelpreise bei Einzelbestellung dieses Satzes"
STAFFEL_HINWEIS_STUFE = "Staffelpreise je Stufe bei gemeinsamer Bestellung aller Positionen dieser Stufe"


def _staffel_text(st, satz=False):
    n = _z(st["menge"], 0)
    stufe = f"Stufe {st['stufe']}: " if st.get("gemeinsam") and st.get("stufe") else ""
    return f"{stufe}Ab {n} {('Satz' if st['menge'] == 1 else 'Sätze') if satz else 'Stk.'} je"


def _angebot_kopf(kopf, ang, einst):
    """Briefkopf mit Logo, Anschriftfeld links und Angebotsdaten rechts, Titel (Breite 186 mm)."""
    firma = [einst.get(f"briefkopf_{i}") or "" for i in range(1, 5)]
    links = [_p(firma[0], S_A_FIRMA)] if firma[0] else []
    links += [_p(t, S_A_GRAU) for t in firma[1:] if t]
    logo = logo_bild(einst)
    t = Table([[links or "", logo or ""]], colWidths=[120 * mm, 66 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                           ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LINEBELOW", (0, 0), (-1, 0), 1.2, BLAU)]))
    inhalt = [t, Spacer(1, 12 * mm)]

    absender = " · ".join(x for x in firma[:3] if x)
    kunde = [kopf.get("kunde")] + list(ang.get("anschrift") or ())
    anschrift = ([_p(absender, S_A_ABSENDER), Spacer(1, 2 * mm)] if absender else []) + \
        [_p("\n".join(str(x) for x in kunde if x), S_A_ANSCHRIFT)]
    bis = ausgabe.gueltig_bis(kopf, einst)
    daten = [("Angebots-Nr.", kopf.get("nummer")), ("Datum", ausgabe.datum_text(kopf.get("datum"))),
             ("Gültig bis", bis.strftime("%d.%m.%Y") if bis else ""), ("Kunden-Nr.", kopf.get("kundennr"))]
    if ang.get("kundenreferenz"):
        daten.append(("Ihre Anfrage", ang["kundenreferenz"]))
    ap = ang.get("ansprechpartner") or {}      # Bearbeiter des Angebots (Benutzer und Kürzel, teilen.mitarbeiter)
    daten += [("Ansprechpartner", ap.get("name")), ("Telefon", ap.get("telefon"))]
    zeilen = [[_p(a, S_A_GRAU), _p(b, S_A_RECHTS)] for a, b in daten if b not in (None, "")]
    stil = [("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5)]
    if ap.get("email"):         # E-Mail über die ganze Breite (lange Adressen ohne Umbruch)
        stil.append(("SPAN", (0, len(zeilen)), (1, len(zeilen))))
        zeilen.append([_p(ap["email"], S_A_RECHTS), ""])
    rechts = Table(zeilen or [[""]], colWidths=[28 * mm, 38 * mm])
    rechts.setStyle(TableStyle(stil))
    t = Table([[anschrift, rechts]], colWidths=[120 * mm, 66 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    inhalt += [t, Spacer(1, 14 * mm), _p(f"Angebot {kopf.get('nummer') or ''}".strip(), S_A_TITEL),
               Spacer(1, 5 * mm)]
    return inhalt


def _angebot_positionen(ang):
    """Positionstabelle ohne Raster: je Position Hauptzeile (Menge, Einheit, Preis, Gesamt), darunter eingerückt
    die Staffelpreise 'Ab 10 Stk. je', danach die übrigen Zeilen des Positionstexts; feine Linie zwischen Positionen."""
    kopf = ["Pos.", "Art.-Nr.", "Bezeichnung", "Menge", "Einh.", "Preis/Einh. €", "Gesamt €"]
    daten = [[_p(t, S_A_KOPF_R if i in (3, 5, 6) else S_A_KOPF) for i, t in enumerate(kopf)]]
    stil = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1), ("LINEBELOW", (0, 0), (-1, 0), 1, BLAU),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 4), ("ALIGN", (4, 1), (4, -1), "CENTER")]

    def zeile(werte):
        daten.append(werte)
        return len(daten) - 1

    def staffeln(liste, satz=False):
        # als eigener heller Kasten unter der Bezeichnung: nicht mit der Menge der Position zu verwechseln (C-9)
        von = len(daten)
        for st in liste:
            r = zeile(["", "", _p(_staffel_text(st, satz), S_A_STAFFEL), "", "", _p(_z(st["preis"]), S_A_STAFFEL), ""])
            stil.append(("SPAN", (2, r), (4, r)))
        if liste:           # jede Stufe ist eine eigene Bestellung (Rüsten, Pauschalen, Mindestpreis je Stufe)
            text = STAFFEL_HINWEIS_STUFE if all(st.get("gemeinsam") for st in liste) else \
                STAFFEL_HINWEIS_SATZ if satz else STAFFEL_HINWEIS
            if any(st.get("gemeinsam") for st in liste) and not all(st.get("gemeinsam") for st in liste):
                text += "; Zeilen mit Stufe: bei gemeinsamer Bestellung aller Positionen dieser Stufe"
            r = zeile(["", "", _p(text, S_A_GRAU), "", "", "", ""])
            stil.append(("SPAN", (2, r), (5, r)))
            stil.extend([("BACKGROUND", (2, von), (5, r), STAFFEL_FLAECHE), ("LINEBEFORE", (2, von), (2, r), 1.5, BLAU)])

    def text_zeilen(text, stil_text=S_A_GRAU):
        if text:
            r = zeile(["", "", _p(text, stil_text), "", "", "", ""])
            stil.append(("SPAN", (2, r), (4, r)))

    gruppen, start = [], None
    for z in ang["zeilen"]:
        if z["art"] != "satzteil":
            if start is not None:
                gruppen.append((start, len(daten) - 1))
            start = len(daten)
        if z["art"] == "satzteil":
            r = zeile([_p(_z(z["pos"], 0), S_A_GRAU), _p(z["artikel"], S_A_GRAU), _p(z["text"], S_A_GRAU), "", "", "", ""])
            stil.append(("SPAN", (2, r), (4, r)))
            continue
        erste, _, rest = (z["text"] or "").partition("\n")
        zeile([_p(_z(z["pos"], 0)), _p(z["artikel"]), _p(erste, S_A_FETT), _p(_z(z["menge"], 0), S_A_RECHTS),
               _p("Satz" if z["art"] == "satz" else "Stk."), _p(_z(z["preis"]), S_A_RECHTS),
               _p(_z(z["gesamt"]), S_A_RECHTS)])
        staffeln(z.get("staffeln") or (), z["art"] == "satz")
        text_zeilen(rest)
    ohne = [st for st in ang.get("staffeln") or () if not st.get("zugeordnet", True)]
    for st in ohne:            # Stufe ohne passende Angebotszeile: mit eigener Bezeichnung anhängen
        if start is not None:
            gruppen.append((start, len(daten) - 1))
        start = zeile([_p(st.get("pos")), "", _p(st.get("text"), S_A_FETT), "", "", "", ""])
        stil.append(("SPAN", (2, start), (4, start)))
        staffeln([st], st["art"] == "satz")
    if start is not None:
        gruppen.append((start, len(daten) - 1))
    for i, (von, bis) in enumerate(gruppen):
        stil += [("NOSPLIT", (0, von), (-1, bis)), ("TOPPADDING", (0, von), (-1, von), 5),
                 ("BOTTOMPADDING", (0, bis), (-1, bis), 5)]
        if i < len(gruppen) - 1:
            stil.append(("LINEBELOW", (0, bis), (-1, bis), 0.5, LINIE))
    stil.append(("LINEBELOW", (0, -1), (-1, -1), 1, BLAU))
    t = LongTable(daten, colWidths=[11 * mm, 25 * mm, 74 * mm, 16 * mm, 12 * mm, 24 * mm, 24 * mm], repeatRows=1)
    t.setStyle(TableStyle(stil))
    return t


def angebot_pdf(pfad, kopf, ang, einst):
    """ang = ausgabe.angebot(...)."""
    firma = " · ".join(t for t in (einst.get(f"briefkopf_{i}") or "" for i in range(1, 5)) if t)
    fuss = "   |   ".join(t for t in (firma, f"Angebot {kopf.get('nummer') or ''}".strip()) if t)
    doc, leinwand = _dokument(pfad, f"Angebot {kopf.get('nummer') or ''}", fuss)
    inhalt = _angebot_kopf(kopf, ang, einst)
    inhalt.append(_angebot_positionen(ang))

    satz = _z(100 * ang["mwst_satz"], 0 if float(100 * ang["mwst_satz"]).is_integer() else 1)
    summen = [[_p("Summe netto", S_A), _p(_z(ang["netto"]) + " €", S_A_RECHTS)],
              [_p(f"zzgl. MwSt. {satz} %", S_A), _p(_z(ang["mwst"]) + " €", S_A_RECHTS)],
              [_p("Gesamtbetrag", ParagraphStyle("g", parent=S_A_FETT, textColor=BLAU, fontSize=10)),
               _p(_z(ang["brutto"]) + " €", ParagraphStyle("gr", parent=S_A_FETT, alignment=TA_RIGHT, textColor=BLAU,
                                                            fontSize=10))]]
    t = Table(summen, colWidths=[52 * mm, 30 * mm], hAlign="RIGHT")
    t.setStyle(TableStyle([("BACKGROUND", (0, 2), (-1, 2), HELLBLAU), ("TOPPADDING", (0, 2), (-1, 2), 4),
                           ("BOTTOMPADDING", (0, 2), (-1, 2), 4), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    inhalt += [Spacer(1, 3 * mm), KeepTogether(t)]

    # Konditionen nach der Summe, jede Angabe eine Zeile; ältere Angebote ohne Lieferzeit: nur die Bedingungen
    bed = ang["bedingungen"] if "bedingungen" in ang else einst.get("bedingungen")
    texte = [t for t in (ang.get("lieferzeit"), ang.get("beistellung"), ang.get("fracht"), ang.get("zahlung"),
                         ang.get("mindestpreis"), bed) if t]
    if texte:
        inhalt += [Spacer(1, 8 * mm), KeepTogether([_p("Konditionen", S_A_KOPF), Spacer(1, 1.5 * mm)]
                                                   + [_p(t, S_A_GRAU) for t in texte])]
    doc.build(inhalt, canvasmaker=leinwand)


# ------------------------------------------------------------------ Werkstattpapiere mit Stangenbild
class StangenBalken(Flowable):
    """Ein Stangenmuster maßstäblich: Endbeschnitt grau, Teile farbig (Pos., Länge), dicke Linie = Schnitt,
    Rest hellgrau, Greiferrest rot. Schweißnaht als roter Strich auf jedem Teil; in der Titelzeile je Stange
    Querschnitt von Ende A mit rotem Punkt an der Naht, gedrehte Teile und die Ersparnis der Gehrungen ineinander
    (grüne Schnittkanten)."""
    HOEHE = 31 * mm
    GRUEN = colors.HexColor("#1E7B34")

    def __init__(self, m, farben):
        super().__init__()
        self.m, self.farben = m, farben

    def wrap(self, breite, hoehe):
        self.breite = breite
        return breite, self.HOEHE

    def _symbol(self, q, lage, x, y):
        """Querschnitt 2,6 mm ab (x, y) unten links, Naht als roter Punkt."""
        c, g = self.canv, 2.6 * mm
        b, h = rechnen.symbol_masse(q)
        mx, my = x + g / 2, y + g / 2
        c.setStrokeColor(colors.HexColor("#404040"))
        c.setLineWidth(0.5)
        if q and q[0] == "Kasten":
            c.rect(mx - b * g / 2, my - h * g / 2, b * g, h * g, fill=0, stroke=1)
        else:
            c.circle(mx, my, g / 2, fill=0, stroke=1)
        if lage is not None:
            nx, ny = rechnen.naht_punkt(q, lage)
            c.setFillColor(colors.HexColor("#D0021B"))
            c.circle(mx + nx * g, my + ny * g, 0.55 * mm, fill=1, stroke=0)

    def draw(self):
        c, m, s = self.canv, self.m, self.m["stange"]
        lang = s["stange"] or 1
        f = self.breite / lang
        y, h = 10 * mm, 11 * mm
        c.setFont(FETT, 9)
        c.setFillColor(BLAU)
        titel = ausgabe.muster_titel(m)
        c.drawString(0, 26.5 * mm, titel)
        c.setFont(SCHRIFT, 8.5)
        c.setFillColor(colors.black)
        gespart = m.get("gespart") or 0
        zeile = (f"{s['profil']}  ·  {rechnen.material_text(s['werkstoff'], s.get('oberflaeche'))}  ·  "
                     f"{_z(lang, 0)} mm  ·  {len(m['teile'])} Teile  ·  Rest {_z(m['rest'], 1)} mm  ·  "
                     f"Ausnutzung {_z(100 * m['ausnutzung'], 1)} %"
                     + (f"  ·  Gehrungen ineinander {_z(gespart, 1)} mm gespart" if gespart > 0 else ""))
        x = c.stringWidth(titel, FETT, 9) + 4 * mm
        c.drawString(x, 26.5 * mm, zeile)
        lage, q, zeichen = rechnen.stange_zeichen(s)
        if zeichen:                         # Naht und Drehung einmal je Stange
            x += c.stringWidth(zeile, SCHRIFT, 8.5) + 4 * mm
            self._symbol(q, lage, x, 26 * mm)
            c.setFont(SCHRIFT, 8.5)
            c.setFillColor(colors.black)
            c.drawString(x + 4.2 * mm, 26.5 * mm, zeichen)

        def rechteck(von, bis, farbe, rand=0.3):
            c.setFillColor(farbe)
            c.setStrokeColor(colors.HexColor("#7F7F7F"))
            c.setLineWidth(rand)
            c.rect(von * f, y, max(0.5, (bis - von) * f), h, fill=1, stroke=1)
        rechteck(0, lang, colors.HexColor("#F2F2F2"))
        if s["end"]:
            rechteck(0, s["end"], colors.HexColor("#7F7F7F"))
        if s["greif"]:
            rechteck(lang - s["greif"], lang, colors.HexColor("#FF9999"))
            if s.get("greif_3d"):       # 3D-Bearbeitung am letzten Teil: 3D-Greifmaß statt Greiferrest
                c.setFillColor(colors.HexColor("#202020"))
                c.setFont(FETT, 6)
                c.drawCentredString((lang - s["greif"] / 2) * f, y + h / 2 - 2, "3D")
        vorher = None
        oben = 270 if any(t.get("ansicht") == "von oben" for t in m["teile"]) else 0
        for t in m["teile"]:
            if t.get("kante_a") or t.get("kante_b"):        # schräge Enden: Umriss mit Schnittkanten
                ol, or_, ur, ul = rechnen.umriss(t)
                c.setFillColor(colors.HexColor(self.farben.get(t["pos"], TEILFARBEN[0])))
                c.setStrokeColor(colors.black)
                c.setLineWidth(1.2)
                pfad = c.beginPath()
                pfad.moveTo(ol * f, y + h)
                pfad.lineTo(or_ * f, y + h)
                pfad.lineTo(ur * f, y)
                pfad.lineTo(ul * f, y)
                pfad.close()
                c.drawPath(pfad, fill=1, stroke=1)
            else:
                rechteck(t["von"], t["bis"], colors.HexColor(self.farben.get(t["pos"], TEILFARBEN[0])))
                c.setStrokeColor(colors.black)
                c.setLineWidth(1.2)
                for x in (t["von"], t["bis"]):
                    c.line(x * f, y - 1, x * f, y + h + 1)
            if t.get("material_gespart") and vorher is not None:   # Gehrungen ineinander: Schnittkanten grün
                c.setStrokeColor(self.GRUEN)
                c.setLineWidth(2)
                for u, a, b in ((vorher, 1, 2), (t, 0, 3)):
                    x = rechnen.umriss(u)
                    c.line(x[a] * f, y + h, x[b] * f, y)
            strich = rechnen.naht_strich(t, oben)
            if strich:                      # Schweißnaht als roter Strich über die Länge des Teils
                ol, or_, ur, ul = rechnen.umriss(t)
                links, rechts = max(ol, ul) * f + 0.8 * mm, min(or_, ur) * f - 0.8 * mm
                if rechts > links:
                    hy = y + h / 2 + strich[0] * (h / 2 - 0.8 * mm)
                    c.setStrokeColor(colors.HexColor("#D0021B"))
                    c.setLineWidth(1.4)
                    c.setDash(*(() if strich[1] else ((3, 2),)))
                    c.line(links, hy, rechts, hy)
                    c.setDash()
            breite = (t["bis"] - t["von"]) * f
            c.setFillColor(colors.black)
            pos = "" if t["pos"] is None else _z(t["pos"], 0)
            if breite > 16 * mm:
                c.setFont(SCHRIFT, 7)
                c.drawCentredString((t["von"] + t["bis"]) / 2 * f, y + h / 2 + 0.5, f"Pos {pos}")
                c.drawCentredString((t["von"] + t["bis"]) / 2 * f, y + h / 2 - 7, f"{_z(t['laenge'], 1)}")
            elif breite > 5 * mm:
                c.setFont(SCHRIFT, 6.5)
                c.drawCentredString((t["von"] + t["bis"]) / 2 * f, y + h / 2 - 2, pos)
            vorher = t
        c.setFont(SCHRIFT, 6.5)
        c.setFillColor(colors.HexColor("#595959"))
        c.drawString(0, y - 3 * mm, "0")
        c.drawRightString(self.breite, y - 3 * mm, f"{_z(lang, 0)} mm")


def _stangenbild(kopf, einst, muster, warnung=None):
    """Seite(n) 'Stangenbild' (A4 quer, 273 mm breit) für Werkstattpapiere und Kalkulation: Kopf, Legende und je
    Stangenmuster ein maßstäblicher Balken (StangenBalken); Farbe je Position über alle Stangen gleich."""
    farben, n = {}, 0
    for m in muster:
        for t in m["teile"]:
            if t["pos"] not in farben:
                farben[t["pos"]] = TEILFARBEN[n % len(TEILFARBEN)]
                n += 1
    inhalt = _dok_kopf("Stangenbild – Verschachtelung je Stange", kopf, einst, 273 * mm, warnung=warnung)
    inhalt += [_p("Grau = Endbeschnitt, farbig = Teil (Pos., Länge in mm; Farbe je Position), hellgrau = Rest / "
                  "Verschnitt, rot = Greiferrest. Dicke schwarze Linie = Schnitt. Maßstäblich je Stange. "
                  "Schräge Linie = Gehrung (Ansicht von der Seite, 0° oben; bei Gehrungen über die Seitenflächen "
                  "von oben). Roter Strich = Schweißnaht (gestrichelt: hinten liegend); hinter den Stangendaten der "
                  "Querschnitt von Ende A mit rotem Punkt an der Naht und die Zahl gedrehter Teile (Lage je Teil im "
                  "Schnittplan). Grüne Linien = Gehrungen ineinandergelegt; das gesparte Material steht einmal je "
                  "Stange in der Titelzeile und ist in Rest und Ausnutzung schon enthalten.",
                  ParagraphStyle("le", parent=S_KLEIN, textColor=GRAU)), Spacer(1, 3 * mm)]
    return inhalt + [StangenBalken(m, farben) for m in muster]


def _fuss(einst, text):
    firma = (einst or {}).get("briefkopf_1") or ""
    return "   |   ".join(t for t in (firma, text) if t)


def werkstatt_pdf(pfad, kopf, wp, aktuell=True, einst=None):
    """wp = ausgabe.werkstatt(...). Schnittpläne hochkant, danach das Stangenbild quer – eine Datei."""
    nr = kopf.get("nummer") or ""
    doc, leinwand = _dokument(pfad, f"Werkstattpapiere {nr}", _fuss(einst, f"Werkstattpapier {nr}"), auch_quer=True)
    achtung = "ACHTUNG: Schnittplan passt nicht zum aktuellen Angebot (Optimierung veraltet)."
    inhalt = _dok_kopf("Werkstattpapiere – Schnittpläne", kopf, einst, 186 * mm, warnung=None if aktuell else achtung)
    inhalt.append(_p("Materialliste", S_H2))
    daten = [_kopfzeile(["Profil", "Werkstoff", "Stange [mm]", "Stangen", "Gewicht [kg]"])]
    for m in wp["material"]:
        daten.append([_p(m["profil"], S_FETT), _p(m["werkstoff"]), _z(m["stange"], 0), _z(m["stangen"], 0),
                      _z(m["gewicht"], 1)])
    tab = _tabelle(daten, [55 * mm, 55 * mm, 25 * mm, 25 * mm, 26 * mm], rechts=(2, 3, 4))
    tab.setStyle(TableStyle([("FONT", (3, 1), (3, -1), FETT, 8.5)]))
    inhalt += [tab, Spacer(1, 4 * mm)]
    if wp.get("zukaufteile"):        # Bleche usw.: werden nicht gelasert, nur bereitgestellt
        daten = [_kopfzeile(["Pos.", "Artikelnummer", "Bezeichnung", "Zukaufteil", "Stück", "bereit"])]
        for z in wp["zukaufteile"]:
            daten.append([_p(_z(z["pos"], 0), S_FETT), _p(z["artikel"], S_KLEIN), _p(z["bezeichnung"], S_KLEIN),
                          _p(z["text"], S_KLEIN), _z(z["stueck"], 0), Kaestchen()])
        tab = _tabelle(daten, [12 * mm, 33 * mm, 45 * mm, 69 * mm, 14 * mm, 13 * mm], rechts=(4,))
        tab.setStyle(TableStyle([("ALIGN", (5, 0), (5, -1), "CENTER")]))
        inhalt += [_p("Zukaufteile (nicht lasern, zum Auftrag bereitstellen)", S_H2), tab, Spacer(1, 4 * mm)]
    breiten = [11 * mm, 12 * mm, 27 * mm, 36 * mm, 18 * mm, 17 * mm, 17 * mm, 13 * mm, 24 * mm, 11 * mm]
    for m in wp["muster"]:
        s = m["stange"]
        daten = [_kopfzeile(["Platz", "Pos.", "Artikelnummer", "Bezeichnung", "Länge [mm]", "Von [mm]", "Bis [mm]",
                             "Lage", "Trennung zum Vorgänger", "erl."])]
        for t in m["teile"]:
            daten.append([_z(t["platz"], 0), _p(_z(t["pos"], 0), ParagraphStyle("pz", parent=S_FETT, alignment=1)),
                          _p(t["artikel"], S_KLEIN), _p(t["bezeichnung"], S_KLEIN),
                          _p(_z(t["laenge"], 1), ParagraphStyle("lg", parent=S_FETT, alignment=TA_RIGHT)),
                          _z(t["von"], 1), _z(t["bis"], 1),
                          _p(t["lage"] + (f"<br/><b>{t['naht_text']}</b>" if t.get("naht_text") else ""),
                             ParagraphStyle("la", parent=S_KLEIN, alignment=1)),
                          _p(t["trennung"], S_KLEIN), Kaestchen()])
        tab = _tabelle(daten, breiten, rechts=(4, 5, 6), wiederholen=True)
        tab.setStyle(TableStyle([
            ("ALIGN", (0, 0), (1, -1), "CENTER"), ("ALIGN", (7, 0), (7, -1), "CENTER"),
            ("ALIGN", (9, 0), (9, -1), "CENTER"), ("VALIGN", (0, 1), (-1, -1), "MIDDLE")]))
        gross = ParagraphStyle("mt", parent=S_FETT, fontSize=11, leading=13, textColor=BLAU)
        anzahl = "1 Stange" if m["anzahl"] == 1 else f"{m['anzahl']} Stangen gleich"
        titel = Table([[_p(ausgabe.muster_titel(m), gross),
                        _p(f"{s['profil']}  ·  {rechnen.material_text(s['werkstoff'], s.get('oberflaeche'))}  ·  "
                           f"{anzahl}", ParagraphStyle("mp", parent=S_FETT, fontSize=10, leading=13,
                                                        alignment=TA_RIGHT))]],
                      colWidths=[80 * mm, sum(breiten) - 80 * mm])
        titel.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HELLBLAU), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        info = _p(f"Stange {_z(s['stange'], 0)} mm  ·  Endbeschnitt {_z(s['end'], 1)} mm  ·  Greiferrest "
                  f"{_z(s['greif'], 1)} mm  ·  Rest {_z(m['rest'], 1)} mm  ·  Ausnutzung "
                  f"{_z(100 * m['ausnutzung'], 1)} %"
                  + (f"  ·  Gehrungen ineinander {_z(m['gespart'], 1)} mm gespart" if m.get("gespart") else ""),
                  ParagraphStyle("mi", parent=S_KLEIN, textColor=GRAU))
        kopfteil = [titel, Spacer(1, 1 * mm), info, Spacer(1, 1 * mm)]
        if len(m["teile"]) <= 30:
            inhalt.append(KeepTogether(kopfteil + [tab, Spacer(1, 6 * mm)]))
        else:
            inhalt += [CondPageBreak(60 * mm)] + kopfteil + [tab, Spacer(1, 6 * mm)]
    if wp["muster"]:
        inhalt += [NextPageTemplate("quer"), PageBreak()]
        inhalt += _stangenbild(kopf, einst, wp["muster"], None if aktuell else achtung.replace("Schnittplan", "Stangenbild"))
    else:
        inhalt.append(_p("Der Schnittplan ist leer. Bitte zuerst optimieren.", S_FETT))
    doc.build(inhalt, canvasmaker=leinwand)


# ------------------------------------------------------------------ Kalkulation
# Spalten der Tabellen: (Kopf, Schlüssel, Nachkommastellen (None = Text), Breite [mm], immer zeigen). Spalten, die in
# keiner Zeile einen Wert haben (alles 0 bzw. leer), blendet das PDF aus; die übrigen werden auf die volle Breite
# verteilt (Patrick 22.10.2026: Kalkulation übersichtlicher). Beträge und Zeiten je Teil, außer 'Position'.
KALK = [("Pos.", "pos", 0, 9, True), ("Artikelnummer", "artikel", None, 22, True), ("Stück", "stueck", 0, 10, True),
        ("Material [€]", "material_teil", 3, 16, True), ("Laser netto [s]", "laser_netto", 1, 15, True),
        ("Gewinde [s]", "gewindezeit", 1, 14, False), ("Laser + Gewinde [€]", "laser_teil", 3, 17, True),
        ("Zusatz [€]", "zusatz_teil", 3, 15, False), ("Rüsten + Wechsel [€]", "ruesten_teil", 3, 17, False),
        ("Herstellkosten [€]", "herstell_teil", 3, 17, True),
        ("Pauschalen, Programm., Aufschlag, Fracht [€]", "pauschalen_teil", 3, 20, False),
        ("Skonto [€]", "skonto_teil", 3, 13, False),
        ("Preis je Teil [€]", "preis_teil", 3, 17, True), ("Preis Position [€]", "preis_position", 2, 18, True),
        ("Herstellkosten Position [€]", "herstell_position", 2, 19, True), ("Hinweis", "hinweis", None, 30, False)]
SCHNEID = [("Pos.", "pos", 0, 9, True), ("Artikelnummer", "artikel", None, 22, True),
           ("groß + Rest [mm]", "mm_gross", 1, 15, True), ("Vorschub groß [mm/min]", "vorschub_gross", 0, 15, True),
           ("Zeit groß [s]", "zeit_gross", 1, 12, True),
           ("Kontur mittel [mm]", "mm_mittel", 1, 14, False), ("Vorschub mittel [mm/min]", "vorschub_mittel", 0, 15, False),
           ("Zeit mittel [s]", "zeit_mittel", 1, 12, False),
           ("Kontur klein [mm]", "mm_klein", 1, 14, False), ("Vorschub klein [mm/min]", "vorschub_klein", 0, 15, False),
           ("Zeit klein [s]", "zeit_klein", 1, 12, False),
           ("Gravur [mm]", "mm_gravur", 1, 12, False), ("Zeit Gravur [s]", "zeit_gravur", 1, 12, False),
           ("davon Anbauteile [s]", "zeit_gravur_anbau", 1, 12, False),
           ("Einstiche", "einstiche_teil", 0, 13, True), ("Zeit Einstiche [s]", "zeit_einstiche", 1, 13, True),
           ("Mehrzeit 3D [s]", "zeit_d3", 1, 13, False), ("Ecken [s]", "zeit_ecken", 1, 12, False),
           ("Anschlag doppelt [s]", "zeit_doppel", 1, 14, False), ("Laser brutto [s]", "laser_brutto", 1, 14, True),
           ("Einsparung [s]", "einsparung", 1, 14, False), ("Laser netto [s]", "laser_netto", 1, 14, True)]
S_KOPF7 = ParagraphStyle("kopf7", parent=S_KOPF, fontSize=7, leading=8.5)


def spalten_waehlen(spalten, zeilen, breite):
    """Spalten mit Wert in mindestens einer Zeile (bzw. 'immer zeigen'), Breiten auf breite [pt] verteilt; jede Spalte
    mindestens so breit wie das längste Wort ihres Kopfs, damit kein Wort getrennt wird. [(Spalte, Breite)]."""
    def hat_wert(s):
        for z in zeilen:
            w = z.get(s[1])
            if s[2] is None and w not in (None, ""):
                return True
            if s[2] is not None and isinstance(w, (int, float)) and round(w, s[2]) != 0:
                return True
        return False
    gewaehlt = [s for s in spalten if s[4] or hat_wert(s)]
    rl = rl_canvas.Canvas(io.BytesIO())
    minimum = [max(rl.stringWidth(w, FETT, 7) for w in s[0].split()) + 7 for s in gewaehlt]
    w = [max(s[3] * mm, m) for s, m in zip(gewaehlt, minimum)]
    f = breite / sum(w)
    if f < 1:           # zu breit: nur über das Minimum hinaus kürzen
        frei = sum(x - m for x, m in zip(w, minimum))
        zuviel = sum(w) - breite
        w = [x - (x - m) * min(1, zuviel / frei) if frei else x for x, m in zip(w, minimum)]
    else:
        w = [x * f for x in w]
    return list(zip(gewaehlt, w))


def _spalten_tabelle(spalten, zeilen, breite, fett=()):
    sp = spalten_waehlen(spalten, zeilen, breite)
    daten = [[_p(s[0], S_KOPF7) for s, _ in sp]]
    for z in zeilen:
        daten.append([_p(z.get(s[1]), S_KLEIN) if s[2] is None else _z(z.get(s[1]), s[2]) for s, _ in sp])
    tab = _tabelle(daten, [b for _, b in sp], rechts=[i for i, (s, _) in enumerate(sp) if s[2] is not None])
    spalten_fett = [i for i, (s, _) in enumerate(sp) if s[1] in fett]
    tab.setStyle(TableStyle([("FONT", (c, 1), (c, -1), FETT, 8.5) for c in spalten_fett]))
    return tab


class QuerschnittBild(Flowable):
    """Profilquerschnitt (querschnitt.kontur) in einer Box groesse × groesse, Wand hellblau gefüllt."""

    def __init__(self, profil, groesse=9 * mm):
        super().__init__()
        self.q, self.groesse = querschnitt.kontur(profil), groesse

    def wrap(self, breite, hoehe):
        return self.groesse, self.groesse

    def draw(self):
        if not self.q:
            return
        c, g = self.canv, self.groesse
        f, dx, dy = querschnitt.einpassen(self.q, g, g, rand=0.5 * mm)
        c.setStrokeColor(BLAU)
        c.setLineWidth(0.5)
        if self.q["flaechen"]:
            pfad = c.beginPath()
            for poly in self.q["flaechen"]:
                pfad.moveTo(dx + poly[0][0] * f, dy + poly[0][1] * f)
                for x, y in poly[1:]:
                    pfad.lineTo(dx + x * f, dy + y * f)
                pfad.close()
            c.setFillColor(colors.HexColor("#BDD7EE"))
            c.drawPath(pfad, fill=1, stroke=1, fillMode=0)       # 0 = Gerade-Ungerade (Rohrwand)
        for zug in self.q["linien"]:
            pfad = c.beginPath()
            pfad.moveTo(dx + zug[0][0] * f, dy + zug[0][1] * f)
            for x, y in zug[1:]:
                pfad.lineTo(dx + x * f, dy + y * f)
            c.drawPath(pfad, fill=0, stroke=1)


class AnteilBalken(Flowable):
    """Waagerechter Balken für den Anteil einer Kostenart am Verkaufspreis (0 … 1)."""

    def __init__(self, anteil, breite=28 * mm, farbe=BLAU):
        super().__init__()
        self.anteil, self.breite, self.farbe = max(0.0, min(1.0, anteil or 0)), breite, farbe

    def wrap(self, breite, hoehe):
        return self.breite, 3 * mm

    def draw(self):
        c = self.canv
        c.setFillColor(ZEBRA)
        c.rect(0, 0.4 * mm, self.breite, 2.4 * mm, fill=1, stroke=0)
        if self.anteil > 0:
            c.setFillColor(self.farbe)
            c.rect(0, 0.4 * mm, max(0.4, self.breite * self.anteil), 2.4 * mm, fill=1, stroke=0)


def _material_tabelle(material, profile):
    """Materialeinsatz je Abmessung (rechnen.material_abmessungen) mit Querschnitt; Meterpreis von Hand fett."""
    kopf = ["", "Abmessung", "Werkstoff · Oberfläche", "Lieferlänge", "Pos.", "Stangen", "Meter", "Gewicht [kg]",
            "Ausnutzung", "Meterpreis [€/m]", "Material [€]"]
    daten, fett = [_kopfzeile(kopf)], []
    rechts = (5, 6, 7, 8, 9, 10)
    for g in material:
        plan = g["stangen"] > 0
        if len(g["laengen"]) > 1:
            laenge = " + ".join(f"{n} × {_z(l, 0)}" for l, n in sorted(g["laengen"].items())) + " mm"
        else:
            laenge = f"{_z(next(iter(g['laengen']), g['stange']), 0)} mm"
        preis = "Kundenmaterial" if g["kunde"] else _z(g["wirksam"]) if g["wirksam"] is not None else "–"
        if g["manuell"] is not None and not g["kunde"]:
            fett.append(len(daten))
            preis += " *"
        daten.append([QuerschnittBild(profile.get(g["profil"])), _p(g["profil"], S_FETT),
                      _p(rechnen.material_text(g["werkstoff"], g["oberflaeche"]), S_KLEIN), _p(laenge, S_KLEIN),
                      _p(", ".join(_z(p, 0) for p in g["positionen"] if p is not None), S_KLEIN),
                      _z(g["stangen"], 0) if plan else "–", _z(g["meter"], 1) if plan else "–",
                      _z(g["kg"], 1) if plan else "–",
                      f"{_z(100 * g['ausnutzung'], 1)} %" if g["ausnutzung"] is not None else "–", preis,
                      _z(g["kosten"]) if plan else "–"])
    summe = sum(g["kosten"] for g in material)
    daten.append(["", _p("Summe", S_FETT), "", "", "", _z(sum(g["stangen"] for g in material), 0),
                  _z(sum(g["meter"] for g in material), 1), _z(sum(g["kg"] for g in material), 1), "", "", _z(summe)])
    tab = _tabelle(daten, [w * mm for w in (12, 32, 42, 31, 30, 16, 18, 22, 20, 26, 22)], rechts=rechts,
                   fett_zeilen=[len(daten) - 1])
    tab.setStyle(TableStyle([("VALIGN", (0, 1), (-1, -1), "MIDDLE")]
                            + [("FONT", (9, r), (9, r), FETT, 8.5) for r in fett]))
    return tab, bool(fett)


def kalkulation_pdf(pfad, kopf, zeilen, summen, einst, aktuell=True, material=None, muster=None, profile=None):
    """Kalkulation A4 quer. material = rechnen.material_abmessungen(...) (Materialeinsatz je Abmessung), muster =
    ausgabe.werkstatt(...)['muster'] (Stangenbild am Ende), profile = Stammdaten Profile {ID: Zeile} für die
    Querschnitte."""
    nr = kopf.get("nummer") or ""
    doc, leinwand = _dokument(pfad, f"Kalkulation {nr}", _fuss(einst, f"Kalkulation {nr}"), quer=True)
    breite = 273 * mm
    achtung = "ACHTUNG: Kalkulation passt nicht zum aktuellen Angebot (Optimierung veraltet)."
    inhalt = _dok_kopf("Kalkulation", kopf, einst, breite, warnung=None if aktuell else achtung)
    k = rechnen.zeit_summen(summen["zeiten"])
    verkauf, herstell = summen.get("verkauf") or 0, summen.get("herstell") or 0
    inhalt += [_kacheln([("Verkaufspreis netto", _z(verkauf) + " €"), ("Herstellkosten", _z(herstell) + " €"),
                         ("Gewinn", _z(summen.get("gewinn") or 0) + " €"), ("Material", _z(summen.get("material") or 0) + " €"),
                         ("Maschinenzeit", rechnen.zeit_text(k["maschine_min"])),
                         ("Stangen", _z(summen["stangen"], 0)), ("Teile", _z(summen["teile"], 0))], breite),
               Spacer(1, 5 * mm)]
    # Kostenarten ohne 0,00 € (Summenzeilen immer), Anteil am Verkaufspreis als Zahl und Balken, Summen hellblau
    daten, fett = [_kopfzeile(["Kostenart", "Betrag [€]", "Anteil", ""])], []
    for t, w, f in kostenarten(summen, einst):
        if not f and not round(w or 0, 2):
            continue
        if f:
            fett.append(len(daten))
        anteil = (w or 0) / verkauf if verkauf else 0
        daten.append([_p(t, S_FETT if f else S), _z(w), f"{_z(100 * anteil, 1)} %" if verkauf else "",
                      AnteilBalken(anteil, 30 * mm, BLAU if f else colors.HexColor("#5B9BD5")) if verkauf else ""])
    kosten = _tabelle(daten, [88 * mm, 25 * mm, 16 * mm, 33 * mm], rechts=(1, 2), fett_zeilen=fett, zebra=False)
    kosten.setStyle(TableStyle([("VALIGN", (0, 1), (-1, -1), "MIDDLE")]))
    angebot = [_kopfzeile(["Rüsten und Mengen", ""]),
               [_p("Rüstzeit Maschine [min]"), _z(summen["ruestzeit"], 0)],
               [_p("Abmessungen × Rüstzeit [min]"), f"{summen['abmessungen']} × {_z(summen['ruestzeit_abmessung'], 0)}"],
               [_p("Stangenwechsel [s]"), _z(summen["stangenwechsel"], 0)],
               *([[_p(f"Stangenwechsel SN [s] ({summen['beladungen_sn']} Stangen mit Schweißnaht)"),
                   _z(summen["stangenwechsel_sn"], 0)]] if summen.get("beladungen_sn") else []),
               [_p("Stangen"), _z(summen["stangen"], 0)], [_p("Teile"), _z(summen["teile"], 0)]]
    t = Table([[kosten, "", _tabelle(angebot, [70 * mm, 30 * mm], rechts=(1,), zebra=False)]],
              colWidths=[162 * mm, 11 * mm, 100 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    inhalt += [t, Spacer(1, 5 * mm)]
    if material:            # Materialeinsatz je Abmessung (Patrick 22.10.2026), eingestellt im Fenster 'Material …'
        tab, hand = _material_tabelle(material, profile or {})
        inhalt += [CondPageBreak(40 * mm), _p("Materialeinsatz je Abmessung", S_H2), tab]
        hinweis = ("Meterpreis = womit das Angebot rechnet (Lieferlängen, Preise bzw. Tonnenpreis mit Aufpreis der "
                   "Oberfläche); Material € je Stange mit Händler-Mehrlänge. Ausnutzung = Teilelängen / Stangenlänge.")
        if hand:
            hinweis += " * = Meterpreis von Hand (Fenster 'Material …' bzw. Spalte Materialpreis [€/m])."
        inhalt += [Spacer(1, 1.5 * mm), _p(hinweis, ParagraphStyle("mh", parent=S_KLEIN, textColor=GRAU)),
                   Spacer(1, 5 * mm)]
    # Zeiten und Kosten je Arbeitsschritt (Schritte ohne Zeit und Kosten ausgeblendet)
    daten = [[_p(t, S_KOPF7) for t in ("Arbeitsschritt", "Art", "Menge", "Rüstzeit", "Zeit je Einheit", "Gesamtzeit",
                                       "Stundensatz [€/h]", "Kosten [€]", "Quelle", "Berechnung")]]
    for z in summen["zeiten"]:
        if rechnen.schritt_sichtbar(z):
            daten.append([_p(z["schritt"], S_KLEIN), _p(z["art"], S_KLEIN), *rechnen.schritt_texte(z),
                          _z(z["kosten"]), _p(z["quelle"], S_KLEIN), _p(z["formel"], S_KLEIN)])
    inhalt += [CondPageBreak(40 * mm), _p("Zeiten und Arbeitskosten je Arbeitsschritt", S_H2),
               _tabelle(daten, [w * mm for w in (40, 20, 24, 18, 20, 20, 22, 20, 40, 49)], rechts=(2, 3, 4, 5, 6, 7)),
               Spacer(1, 1.5 * mm),
               _p(f"Maschinenzeit {rechnen.zeit_text(k['maschine_min'])} · Personalzeit "
                  f"{rechnen.zeit_text(k['personal_min'])} · Durchlaufzeit {rechnen.zeit_text(k['durchlauf_min'])} "
                  f"(parallele Personalzeit nicht addiert) · Arbeitskosten {_z(k['arbeitskosten'])} €",
                  ParagraphStyle("zs", parent=S_KLEIN, textColor=GRAU)),
               Spacer(1, 5 * mm)]
    liste = [z for z in zeilen if z is not None]
    inhalt += [CondPageBreak(40 * mm), _p("Kalkulation je Position", S_H2),
               _spalten_tabelle(KALK, liste, breite, fett=("pos", "preis_teil", "preis_position")),
               Spacer(1, 1.5 * mm),
               _p("Beträge und Zeiten je Teil, außer den Spalten 'Position'. Spalten ohne Wert sind ausgeblendet.",
                  ParagraphStyle("kh", parent=S_KLEIN, textColor=GRAU))]
    # Schneidzeit je Teil nach Konturklassen: Schneidweg je Klasse / Vorschub der Klasse
    liste = [z for z in zeilen if z is not None and not z.get("zukaufteil")]
    if liste:
        inhalt += [Spacer(1, 5 * mm), CondPageBreak(40 * mm), _p("Schneidzeit je Teil nach Konturklassen", S_H2),
                   _spalten_tabelle(SCHNEID, liste, breite), Spacer(1, 1.5 * mm),
                   _p("Zeit je Klasse = Schneidweg der Klasse / Vorschub der Klasse × 60. Anfangs- und Endschnitt sind "
                      "wie die Innenkonturen nach Hüllmaß eingeteilt. groß + Rest = Schneidweg − Konturen klein und "
                      "mittel. Netto = brutto − Einsparung gemeinsamer Schnitte (mit dem Vorschub der Klasse des "
                      "Endes) + Zusatzzeit; bei angepasster Schneidzeit gilt die eingetragene Zeit. Spalten ohne Wert "
                      "sind ausgeblendet.", ParagraphStyle("sh", parent=S_KLEIN, textColor=GRAU))]
    if muster:              # Stangenbild wie in den Werkstattpapieren, auf neuer Seite
        inhalt += [PageBreak()] + _stangenbild(kopf, einst, muster, None if aktuell else
                                               achtung.replace("Kalkulation", "Stangenbild"))
    doc.build(inhalt, canvasmaker=leinwand)


# ------------------------------------------------------------------ Nachkalkulation
def _abw_farbe(abweichung, erloes=False):
    """Kosten: mehr als kalkuliert = rot, weniger = grün; Erlös und Deckungsbeitrag umgekehrt."""
    w = round(abweichung or 0, 2)
    if not w:
        return None
    return (GRUEN if w > 0 else ROT) if erloes else (ROT if w > 0 else GRUEN)


def nachkalkulation_pdf(pfad, kopf, v, ist, aktuell=True, einst=None):
    """v = nachkalkulation.vergleich(...), ist = gespeicherte Ist-Werte."""
    nr = kopf.get("nummer") or ""
    doc, leinwand = _dokument(pfad, f"Nachkalkulation {nr}", _fuss(einst, f"Nachkalkulation {nr}"))
    breite = 186 * mm
    angaben = [("Angebot", nr), ("Kunde", kopf.get("kunde")),
               ("Maschine", f"{kopf.get('maschine') or ''} ({_z(v['satz'])} €/h)"), ("erstellt", _erstellt())]
    inhalt = _dok_kopf("Nachkalkulation", kopf, einst, breite, angaben, None if aktuell else
                       "ACHTUNG: Die Optimierung ist veraltet, das Soll passt nicht zum aktuellen Angebot.")
    if ist and ist.get("bemerkung"):
        inhalt += [_p(f"Bemerkung: {ist['bemerkung']}"), Spacer(1, 3 * mm)]
    summe, db = v["summe"], v["db"]
    inhalt += [_kacheln([("Erlös", _z(v["erloes"]["ist"]) + " €"),
                         ("Einzelkosten Ist", _z(summe["ist"]) + " €", _abw_farbe(summe["abweichung"])),
                         ("Abweichung Kosten", _z(summe["abweichung"]) + " €", _abw_farbe(summe["abweichung"])),
                         ("Deckungsbeitrag Ist", _z(db["ist"]) + " €", _abw_farbe(db["abweichung"], True)),
                         ("Deckungsbeitrag Soll", _z(db["soll"]) + " €")], breite),
               Spacer(1, 1.5 * mm),
               _p("Rot = teurer bzw. schlechter als kalkuliert, grün = günstiger bzw. besser.",
                  ParagraphStyle("nl", parent=S_KLEIN, textColor=GRAU)),
               Spacer(1, 3 * mm), _p("Stangen je Gruppe", S_H2)]
    daten = [_kopfzeile(["Profil", "Werkstoff", "Stange [mm]", "Stangen Soll", "Stangen Ist",
                         "€/m Soll", "€/m Ist", "Material Soll [€]", "Material Ist [€]"])]
    stil = []
    for g in v["gruppen"]:
        r = len(daten)
        daten.append([_p(g["profil"], S_FETT), _p(g["werkstoff"]), _z(g["stange"], 0), _z(g["soll"], 0),
                      _z(g["ist"], 0) if g["ist"] is not None else "–", _z(g["meterpreis"]),
                      _z(g["meterpreis_ist"]) if g["meterpreis_ist"] is not None else "–", _z(g["soll_kosten"]),
                      _z(g["ist_kosten"])])
        farbe = _abw_farbe((g["ist_kosten"] or 0) - (g["soll_kosten"] or 0))
        if farbe is not None:
            stil.append(("TEXTCOLOR", (8, r), (8, r), farbe))
    tab = _tabelle(daten, [28 * mm, 26 * mm, 20 * mm, 16 * mm, 16 * mm, 17 * mm, 17 * mm, 23 * mm, 23 * mm],
                   rechts=(2, 3, 4, 5, 6, 7, 8))
    tab.setStyle(TableStyle(stil))
    inhalt += [tab, Spacer(1, 5 * mm), _p("Soll gegen Ist (Einzelkosten ohne Zuschläge und Gewinn)", S_H2)]
    daten = [_kopfzeile(["Kostenart", "Einheit", "Menge Soll", "Menge Ist", "Soll [€]", "Ist [€]", "Abweichung [€]",
                         "Abw. [%]", "erfasst"])]
    zeilen = v["zeilen"] + [v["summe"], v["erloes"], v["db"]]
    n = len(v["zeilen"]) + 1
    stil = []
    for i, z in enumerate(zeilen):
        r = len(daten)
        daten.append([_p(z["text"]), z["einheit"], _z(z["soll_menge"]) if z["soll_menge"] is not None else "",
                      _z(z["ist_menge"]) if z["ist_menge"] is not None else "", _z(z["soll"]), _z(z["ist"]),
                      _z(z["abweichung"]), _z(z["prozent"], 1) if z["prozent"] is not None else "", z["erfasst"]])
        farbe = _abw_farbe(z["abweichung"], erloes=r > n)
        if farbe is not None:
            stil += [("TEXTCOLOR", (6, r), (7, r), farbe), ("FONT", (6, r), (7, r), FETT, 8.5)]
    tab = _tabelle(daten, [50 * mm, 13 * mm, 18 * mm, 18 * mm, 19 * mm, 19 * mm, 21 * mm, 15 * mm, 13 * mm],
                   rechts=(2, 3, 4, 5, 6, 7), fett_zeilen=(n, n + 2))
    tab.setStyle(TableStyle([("ALIGN", (8, 0), (8, -1), "CENTER")] + stil))
    inhalt += [tab, Spacer(1, 3 * mm),
               _p("Leere Ist-Werte zählen wie kalkuliert (Spalte erfasst = nein). Zeiten werden mit dem Stundensatz der "
                  "Maschine bewertet, Material mit dem EK-Meterpreis × Stangenlänge (leer = Meterpreis laut "
                  "Schnittplan).", ParagraphStyle("nh", parent=S_KLEIN, textColor=GRAU))]
    doc.build(inhalt, canvasmaker=leinwand)
