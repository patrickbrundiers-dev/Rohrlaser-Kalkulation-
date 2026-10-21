"""PDF-Ausgabe: Angebot, Werkstattpapiere (Schnittpläne mit Stangenbild) und Kalkulation.

Die Inhalte kommen aus ausgabe.py; hier wird nur gesetzt (reportlab, A4).
"""
import base64
import datetime
import io
from itertools import zip_longest

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether, LongTable,
                                Image, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.pdfgen import canvas as rl_canvas

from . import ausgabe, rechnen
from .rechnen import kostenarten
from .stammdaten import zahl_als_text

SCHRIFT, FETT = "Helvetica", "Helvetica-Bold"
BLAU = colors.HexColor("#1F4E78")
HELLBLAU = colors.HexColor("#DDEBF7")
RAHMEN = colors.HexColor("#BFBFBF")
ROT = colors.HexColor("#C00000")
TEILFARBEN = ["#BDD7EE", "#C6E0B4", "#FFE699", "#D9D2E9", "#B4C6E7", "#F8CBAD", "#CCECFF", "#E2EFDA", "#EDEDBE"]

S = ParagraphStyle("normal", fontName=SCHRIFT, fontSize=9, leading=11)
S_KLEIN = ParagraphStyle("klein", parent=S, fontSize=8, leading=9.5)
S_FETT = ParagraphStyle("fett", parent=S, fontName=FETT)
S_KOPF = ParagraphStyle("kopf", parent=S, fontName=FETT, textColor=colors.white, fontSize=8, leading=9.5)
S_RECHTS = ParagraphStyle("rechts", parent=S, alignment=TA_RIGHT)
S_TITEL = ParagraphStyle("titel", parent=S, fontName=FETT, fontSize=16, leading=20, spaceAfter=4)
S_H2 = ParagraphStyle("h2", parent=S, fontName=FETT, fontSize=11, leading=14, spaceBefore=6, spaceAfter=3)


def _z(w, stellen=2):
    return zahl_als_text(w, stellen) if isinstance(w, (int, float)) and not isinstance(w, bool) else ("" if w is None else str(w))


def _p(text, stil=S):
    t = "" if text is None else str(text)
    return Paragraph(t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>"), stil)


class _Seitenzahlen(rl_canvas.Canvas):
    """Canvas mit 'Seite x von y' und Fußzeilentext auf jeder Seite."""
    fuss = ""
    linie = None        # Farbe einer feinen Linie über der Fußzeile (Angebot), None = keine

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


def _dokument(pfad, titel, fuss, quer=False, auch_quer=False):
    hoch = landscape(A4) if quer else A4
    doc = BaseDocTemplate(str(pfad), pagesize=hoch, title=titel, author="Rohrlaser-Angebotskalkulation",
                          leftMargin=12 * mm, rightMargin=12 * mm, topMargin=12 * mm, bottomMargin=15 * mm)
    vorlagen = [PageTemplate(id="hoch", pagesize=hoch,
                             frames=[Frame(12 * mm, 15 * mm, hoch[0] - 24 * mm, hoch[1] - 27 * mm, id="f1")])]
    if auch_quer:
        q = landscape(A4)
        vorlagen.append(PageTemplate(id="quer", pagesize=q,
                                     frames=[Frame(12 * mm, 15 * mm, q[0] - 24 * mm, q[1] - 27 * mm, id="f2")]))
    doc.addPageTemplates(vorlagen)
    leinwand = type("Leinwand", (_Seitenzahlen,), {"fuss": fuss})
    return doc, leinwand


def _tabelle(daten, breiten, kopfzeilen=1, rechts=(), fett_zeilen=(), wiederholen=True):
    t = LongTable(daten, colWidths=breiten, repeatRows=kopfzeilen if wiederholen else 0)
    stil = [("FONT", (0, 0), (-1, -1), SCHRIFT, 8.5), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.4, RAHMEN), ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2), ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3)]
    if kopfzeilen:
        stil += [("BACKGROUND", (0, 0), (-1, kopfzeilen - 1), BLAU), ("VALIGN", (0, 0), (-1, kopfzeilen - 1), "MIDDLE")]
    for c in rechts:
        stil.append(("ALIGN", (c, kopfzeilen), (c, -1), "RIGHT"))
    for r in fett_zeilen:
        stil.append(("FONT", (0, r), (-1, r), FETT, 8.5))
    t.setStyle(TableStyle(stil))
    return t


def _kopfzeile(texte):
    return [_p(t, S_KOPF) for t in texte]


def _erstellt():
    return datetime.datetime.now().strftime("%d.%m.%Y %H:%M")


# ------------------------------------------------------------------ Angebot
GRAU = colors.HexColor("#595959")
LINIE = colors.HexColor("#D9D9D9")
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


def _staffel_text(st, satz=False):
    n = _z(st["menge"], 0)
    return f"Ab {n} {('Satz' if st['menge'] == 1 else 'Sätze') if satz else 'Stk.'} je"


def _angebot_kopf(kopf, ang, einst):
    """Briefkopf mit Logo, Anschriftfeld links und Angebotsdaten rechts, Titel (Breite 182 mm = Rahmen ohne
    Innenabstand)."""
    firma = [einst.get(f"briefkopf_{i}") or "" for i in range(1, 5)]
    links = [_p(firma[0], S_A_FIRMA)] if firma[0] else []
    links += [_p(t, S_A_GRAU) for t in firma[1:] if t]
    logo = logo_bild(einst)
    t = Table([[links or "", logo or ""]], colWidths=[116 * mm, 66 * mm])
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
    rechts = Table([[_p(a, S_A_GRAU), _p(b, S_A_RECHTS)] for a, b in daten if b not in (None, "")] or [[""]],
                   colWidths=[28 * mm, 38 * mm])
    rechts.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                ("TOPPADDING", (0, 0), (-1, -1), 0.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5)]))
    t = Table([[anschrift, rechts]], colWidths=[116 * mm, 66 * mm])
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
        for st in liste:
            r = zeile(["", "", _p(_staffel_text(st, satz), S_A_STAFFEL), "", "", _p(_z(st["preis"]), S_A_STAFFEL), ""])
            stil.append(("SPAN", (2, r), (3, r)))

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
    t = LongTable(daten, colWidths=[11 * mm, 25 * mm, 72 * mm, 15 * mm, 12 * mm, 23 * mm, 24 * mm], repeatRows=1)
    t.setStyle(TableStyle(stil))
    return t


def angebot_pdf(pfad, kopf, ang, einst):
    """ang = ausgabe.angebot(...)."""
    firma = " · ".join(t for t in (einst.get(f"briefkopf_{i}") or "" for i in range(1, 5)) if t)
    fuss = "   |   ".join(t for t in (firma, f"Angebot {kopf.get('nummer') or ''}".strip()) if t)
    doc, leinwand = _dokument(pfad, f"Angebot {kopf.get('nummer') or ''}", fuss)
    leinwand.linie = BLAU
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
    Rest hellgrau, Greiferrest rot."""
    HOEHE = 30 * mm

    def __init__(self, m, farben):
        super().__init__()
        self.m, self.farben = m, farben

    def wrap(self, breite, hoehe):
        self.breite = breite
        return breite, self.HOEHE

    def draw(self):
        c, m, s = self.canv, self.m, self.m["stange"]
        lang = s["stange"] or 1
        f = self.breite / lang
        y, h = 9 * mm, 11 * mm
        c.setFont(FETT, 8.5)
        c.setFillColor(colors.black)
        c.drawString(0, 25 * mm, f"{ausgabe.muster_titel(m)}   |   {s['profil']}   |   {rechnen.material_text(s['werkstoff'], s.get('oberflaeche'))}   |   "
                                 f"{_z(lang, 0)} mm   |   {len(m['teile'])} Teile   |   Rest {_z(m['rest'], 1)} mm   |   "
                                 f"Ausnutzung {_z(100 * m['ausnutzung'], 1)} %")

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
        for t in m["teile"]:
            rechteck(t["von"], t["bis"], colors.HexColor(self.farben.get(t["pos"], TEILFARBEN[0])))
            c.setStrokeColor(colors.black)
            c.setLineWidth(1.2)
            for x in (t["von"], t["bis"]):
                c.line(x * f, y - 1, x * f, y + h + 1)
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
        c.setFont(SCHRIFT, 6.5)
        c.setFillColor(colors.HexColor("#595959"))
        c.drawString(0, y - 8, "0")
        c.drawRightString(self.breite, y - 8, f"{_z(lang, 0)} mm")


def werkstatt_pdf(pfad, kopf, wp, aktuell=True):
    """wp = ausgabe.werkstatt(...). Schnittpläne hochkant, danach das Stangenbild quer – eine Datei."""
    doc, leinwand = _dokument(pfad, f"Werkstattpapiere {kopf.get('nummer') or ''}",
                              f"Werkstattpapier {kopf.get('nummer') or ''}", auch_quer=True)
    kopftext = (f"Angebot {kopf.get('nummer') or ''}   |   Kunde {kopf.get('kunde') or ''}   |   "
                f"Maschine {kopf.get('maschine') or ''}   |   erstellt {_erstellt()}")
    achtung = "ACHTUNG: Schnittplan passt nicht zum aktuellen Angebot (Optimierung veraltet)."
    inhalt = [_p("Werkstattpapiere – Schnittpläne", S_TITEL), _p(kopftext, S_KLEIN)]
    if not aktuell:
        inhalt.append(_p(achtung, ParagraphStyle("rot", parent=S_FETT, textColor=ROT)))
    inhalt += [Spacer(1, 4 * mm), _p("Materialliste", S_H2)]
    daten = [_kopfzeile(["Profil-ID", "Werkstoff-ID", "Stange [mm]", "Stangen [Stk]", "Gewicht [kg]"])]
    for m in wp["material"]:
        daten.append([_p(m["profil"]), _p(m["werkstoff"]), _z(m["stange"], 0), _z(m["stangen"], 0), _z(m["gewicht"], 1)])
    inhalt += [_tabelle(daten, [45 * mm, 40 * mm, 25 * mm, 25 * mm, 25 * mm], rechts=(2, 3, 4)), Spacer(1, 4 * mm)]
    if wp.get("zukaufteile"):        # Bleche usw.: werden nicht gelasert, nur bereitgestellt
        daten = [_kopfzeile(["Pos.", "Artikelnummer", "Bezeichnung", "Zukaufteil", "Stück"])]
        for z in wp["zukaufteile"]:
            daten.append([_z(z["pos"], 0), _p(z["artikel"], S_KLEIN), _p(z["bezeichnung"], S_KLEIN),
                          _p(z["text"], S_KLEIN), _z(z["stueck"], 0)])
        inhalt += [_p("Zukaufteile (nicht lasern, zum Auftrag bereitstellen)", S_H2),
                   _tabelle(daten, [12 * mm, 33 * mm, 40 * mm, 70 * mm, 15 * mm], rechts=(4,)), Spacer(1, 4 * mm)]
    breiten = [11 * mm, 11 * mm, 27 * mm, 33 * mm, 17 * mm, 17 * mm, 17 * mm, 14 * mm, 25 * mm, 14 * mm]
    for m in wp["muster"]:
        s = m["stange"]
        daten = [_kopfzeile(["Platz", "Pos.", "Artikelnummer", "Bezeichnung", "Länge [mm]", "Von [mm]", "Bis [mm]",
                             "Lage", "Trennung zum Vorgänger", "erledigt"])]
        for t in m["teile"]:
            daten.append([_z(t["platz"], 0), _z(t["pos"], 0), _p(t["artikel"], S_KLEIN), _p(t["bezeichnung"], S_KLEIN),
                          _z(t["laenge"], 1), _z(t["von"], 1), _z(t["bis"], 1),
                          t["lage"],
                          _p(t["trennung"], S_KLEIN), ""])
        tab = _tabelle(daten, breiten, rechts=(4, 5, 6), wiederholen=True)
        tab.setStyle(TableStyle([("ALIGN", (0, 1), (1, -1), "CENTER"), ("ALIGN", (7, 1), (7, -1), "CENTER")]))
        titel = Table([[_p(ausgabe.muster_titel(m), ParagraphStyle("mt", parent=S_FETT, fontSize=11, leading=13))]],
                      colWidths=[sum(breiten)])
        titel.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HELLBLAU)]))
        info = _p(f"{s['profil']}  |  {rechnen.material_text(s['werkstoff'], s.get('oberflaeche'))}  |  Stange {_z(s['stange'], 0)} mm  |  Endbeschnitt "
                  f"{_z(s['end'], 1)} mm  |  Greiferrest {_z(s['greif'], 1)} mm  |  Rest {_z(m['rest'], 1)} mm  |  "
                  f"Ausnutzung {_z(100 * m['ausnutzung'], 1)} %", S_KLEIN)
        kopfteil = [titel, info, Spacer(1, 1.5 * mm)]
        if len(m["teile"]) <= 30:
            inhalt.append(KeepTogether(kopfteil + [tab, Spacer(1, 5 * mm)]))
        else:
            inhalt += [CondPageBreak(60 * mm)] + kopfteil + [tab, Spacer(1, 5 * mm)]
    if wp["muster"]:
        farben, n = {}, 0
        for m in wp["muster"]:
            for t in m["teile"]:
                if t["pos"] not in farben:
                    farben[t["pos"]] = TEILFARBEN[n % len(TEILFARBEN)]
                    n += 1
        inhalt += [NextPageTemplate("quer"), PageBreak(), _p("Stangenbild – Verschachtelung je Stange", S_TITEL),
                   _p(kopftext, S_KLEIN)]
        if not aktuell:
            inhalt.append(_p(achtung.replace("Schnittplan", "Stangenbild"), ParagraphStyle("rot2", parent=S_FETT,
                                                                                              textColor=ROT)))
        inhalt += [_p("Grau = Endbeschnitt, farbig = Teil (Pos., Länge in mm; Farbe je Position), hellgrau = Rest / "
                      "Verschnitt, rot = Greiferrest. Dicke schwarze Linie = Schnitt. Maßstäblich je Stange.", S_KLEIN),
                   Spacer(1, 3 * mm)]
        inhalt += [StangenBalken(m, farben) for m in wp["muster"]]
    else:
        inhalt.append(_p("Der Schnittplan ist leer. Bitte zuerst optimieren.", S_FETT))
    doc.build(inhalt, canvasmaker=leinwand)


# ------------------------------------------------------------------ Kalkulation
KALK = [("Pos.", "pos", 0, 9), ("Artikelnummer", "artikel", None, 20), ("Stück", "stueck", 0, 10),
        ("Material je Teil [€]", "material_teil", 3, 18), ("Laserzeit netto je Teil [s]", "laser_netto", 1, 18),
        ("Gewindezeit je Teil [s]", "gewindezeit", 1, 16), ("Laser + Gewinde je Teil [€]", "laser_teil", 3, 18),
        ("Zusatzarbeiten je Teil [€]", "zusatz_teil", 3, 18), ("Rüsten + Stangenwechsel je Teil [€]", "ruesten_teil", 3, 18),
        ("Herstellkosten je Teil [€]", "herstell_teil", 3, 19),
        ("Pauschalen, Programmierung, Aufschlag, Fracht je Teil [€]", "pauschalen_teil", 3, 19),
        ("Skonto je Teil [€]", "skonto_teil", 3, 15),
        ("Verkaufspreis je Teil [€]", "preis_teil", 3, 19), ("Verkaufspreis Position [€]", "preis_position", 2, 18),
        ("Herstellkosten Position [€]", "herstell_position", 2, 18), ("Hinweis", "hinweis", None, 20)]
assert sum(s[3] for s in KALK) <= 273     # Breite A4 quer ohne Ränder [mm]
SCHNEID = [("Pos.", "pos", 0, 9), ("Artikelnummer", "artikel", None, 22),
           ("groß + Rest [mm]", "mm_gross", 1, 17), ("Vorschub groß [mm/min]", "vorschub_gross", 0, 15),
           ("Zeit groß [s]", "zeit_gross", 1, 13),
           ("Kontur mittel [mm]", "mm_mittel", 1, 15), ("Vorschub mittel [mm/min]", "vorschub_mittel", 0, 15),
           ("Zeit mittel [s]", "zeit_mittel", 1, 13),
           ("Kontur klein [mm]", "mm_klein", 1, 15), ("Vorschub klein [mm/min]", "vorschub_klein", 0, 15),
           ("Zeit klein [s]", "zeit_klein", 1, 13),
           ("Gravur [mm]", "mm_gravur", 1, 13), ("Zeit Gravur [s]", "zeit_gravur", 1, 13),
           ("Einstiche", "einstiche_teil", 0, 12), ("Zeit Einstiche [s]", "zeit_einstiche", 1, 14),
           ("Laserzeit brutto [s]", "laser_brutto", 1, 14), ("Einsparung [s]", "einsparung", 1, 14),
           ("Laserzeit netto [s]", "laser_netto", 1, 14)]
assert sum(s[3] for s in SCHNEID) <= 273


def kalkulation_pdf(pfad, kopf, zeilen, summen, einst, aktuell=True):
    doc, leinwand = _dokument(pfad, f"Kalkulation {kopf.get('nummer') or ''}", f"Kalkulation {kopf.get('nummer') or ''}",
                              quer=True)
    inhalt = [_p("Kalkulation", S_TITEL),
              _p(f"Angebot {kopf.get('nummer') or ''}   |   Kunde {kopf.get('kunde') or ''}   |   Maschine "
                 f"{kopf.get('maschine') or ''}   |   erstellt {_erstellt()}", S_KLEIN)]
    if not aktuell:
        inhalt.append(_p("ACHTUNG: Kalkulation passt nicht zum aktuellen Angebot (Optimierung veraltet).",
                         ParagraphStyle("rot", parent=S_FETT, textColor=ROT)))
    werte = [(f"{t} [€]", _z(w)) for t, w, _ in kostenarten(summen, einst)]
    angebot = [("Rüstzeit [min]", _z(summen["ruestzeit"], 0)),
               ("Abmessungen × Rüstzeit [min]", f"{summen['abmessungen']} × {_z(summen['ruestzeit_abmessung'], 0)}"),
               ("Stangenwechsel [s]", _z(summen["stangenwechsel"], 0)),
               ("Stangen", _z(summen["stangen"], 0)), ("Teile", _z(summen["teile"], 0))]
    t = Table([[_p(a, S_FETT), _p(b, S_RECHTS), "", _p(c, S_FETT), _p(d, S_RECHTS)] for (a, b), (c, d) in
               zip_longest(werte, angebot, fillvalue=("", ""))],
              colWidths=[75 * mm, 30 * mm, 15 * mm, 60 * mm, 25 * mm], hAlign="LEFT")
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (1, -1), 0.3, RAHMEN),
                           ("LINEBELOW", (3, 0), (4, len(angebot) - 1), 0.3, RAHMEN)]))
    inhalt += [Spacer(1, 3 * mm), t, Spacer(1, 5 * mm)]
    klein = ParagraphStyle("kopf7", parent=S_KOPF, fontSize=7, leading=8.5)
    # Zeiten und Kosten je Arbeitsschritt (Schritte ohne Zeit und Kosten ausgeblendet)
    daten = [[_p(t, klein) for t in ("Arbeitsschritt", "Art", "Menge", "Rüstzeit", "Zeit je Einheit", "Gesamtzeit",
                                     "Stundensatz [€/h]", "Kosten [€]", "Quelle", "Berechnung")]]
    for z in summen["zeiten"]:
        if rechnen.schritt_sichtbar(z):
            daten.append([_p(z["schritt"], S_KLEIN), _p(z["art"], S_KLEIN), *rechnen.schritt_texte(z),
                          _z(z["kosten"]), _p(z["quelle"], S_KLEIN), _p(z["formel"], S_KLEIN)])
    k = rechnen.zeit_summen(summen["zeiten"])
    inhalt += [_p("Zeiten und Arbeitskosten je Arbeitsschritt", S_H2),
               _tabelle(daten, [w * mm for w in (40, 20, 22, 18, 18, 18, 22, 18, 40, 57)], rechts=(2, 3, 4, 5, 6, 7)),
               _p(f"Maschinenzeit {rechnen.zeit_text(k['maschine_min'])} · Personalzeit "
                  f"{rechnen.zeit_text(k['personal_min'])} · Durchlaufzeit {rechnen.zeit_text(k['durchlauf_min'])} "
                  f"(parallele Personalzeit nicht addiert) · Arbeitskosten {_z(k['arbeitskosten'])} €", S_KLEIN),
               Spacer(1, 5 * mm)]
    daten = [[_p(s[0], klein) for s in KALK]]
    for z in zeilen:
        if z is None:
            continue
        daten.append([_p(z.get(s[1]), S_KLEIN) if s[2] is None else _z(z.get(s[1]), s[2]) for s in KALK])
    inhalt.append(_tabelle(daten, [s[3] * mm for s in KALK], rechts=[i for i, s in enumerate(KALK) if s[2] is not None]))
    # Schneidzeit je Teil nach Konturklassen: Schneidweg je Klasse / Vorschub der Klasse
    daten = [[_p(s[0], klein) for s in SCHNEID]]
    for z in zeilen:
        if z is None or z.get("zukaufteil"):
            continue
        daten.append([_p(z.get(s[1]), S_KLEIN) if s[2] is None else _z(z.get(s[1]), s[2]) for s in SCHNEID])
    if len(daten) > 1:
        inhalt += [Spacer(1, 5 * mm), _p("Schneidzeit je Teil nach Konturklassen", S_H2),
                   _tabelle(daten, [s[3] * mm for s in SCHNEID],
                            rechts=[i for i, s in enumerate(SCHNEID) if s[2] is not None]),
                   _p("Zeit je Klasse = Schneidweg der Klasse / Vorschub der Klasse × 60. Anfangs- und Endschnitt sind "
                      "wie die Innenkonturen nach Hüllmaß eingeteilt. groß + Rest = Schneidweg − Konturen klein und "
                      "mittel. Netto = brutto − Einsparung gemeinsamer Schnitte (mit dem Vorschub der Klasse des "
                      "Endes) + Zusatzzeit; bei angepasster Schneidzeit gilt die eingetragene Zeit.", S_KLEIN)]
    doc.build(inhalt, canvasmaker=leinwand)


# ------------------------------------------------------------------ Nachkalkulation
def nachkalkulation_pdf(pfad, kopf, v, ist, aktuell=True):
    """v = nachkalkulation.vergleich(...), ist = gespeicherte Ist-Werte."""
    doc, leinwand = _dokument(pfad, f"Nachkalkulation {kopf.get('nummer') or ''}",
                              f"Nachkalkulation {kopf.get('nummer') or ''}")
    inhalt = [_p("Nachkalkulation", S_TITEL),
              _p(f"Angebot {kopf.get('nummer') or ''}   |   Kunde {kopf.get('kunde') or ''}   |   Maschine "
                 f"{kopf.get('maschine') or ''} ({_z(v['satz'])} €/h)   |   erstellt {_erstellt()}", S_KLEIN)]
    if not aktuell:
        inhalt.append(_p("ACHTUNG: Die Optimierung ist veraltet, das Soll passt nicht zum aktuellen Angebot.",
                         ParagraphStyle("rot", parent=S_FETT, textColor=ROT)))
    if ist and ist.get("bemerkung"):
        inhalt.append(_p(f"Bemerkung: {ist['bemerkung']}"))
    inhalt += [Spacer(1, 4 * mm), _p("Stangen je Gruppe", S_H2)]
    daten = [_kopfzeile(["Profil-ID", "Werkstoff-ID", "Stangenlänge [mm]", "Stangen Soll", "Stangen Ist",
                         "€/m Soll", "€/m Ist", "Material Soll [€]", "Material Ist [€]"])]
    for g in v["gruppen"]:
        daten.append([_p(g["profil"]), _p(g["werkstoff"]), _z(g["stange"], 0), _z(g["soll"], 0),
                      _z(g["ist"], 0) if g["ist"] is not None else "–", _z(g["meterpreis"]),
                      _z(g["meterpreis_ist"]) if g["meterpreis_ist"] is not None else "–", _z(g["soll_kosten"]),
                      _z(g["ist_kosten"])])
    inhalt.append(_tabelle(daten, [28 * mm, 24 * mm, 20 * mm, 15 * mm, 15 * mm, 17 * mm, 17 * mm, 22 * mm, 22 * mm],
                           rechts=(2, 3, 4, 5, 6, 7, 8)))
    inhalt += [Spacer(1, 4 * mm), _p("Soll gegen Ist (Einzelkosten ohne Zuschläge und Gewinn)", S_H2)]
    daten = [_kopfzeile(["Kostenart", "Einheit", "Menge Soll", "Menge Ist", "Soll [€]", "Ist [€]", "Abweichung [€]",
                         "Abw. [%]", "erfasst"])]
    zeilen = v["zeilen"] + [v["summe"], v["erloes"], v["db"]]
    for z in zeilen:
        daten.append([_p(z["text"]), z["einheit"], _z(z["soll_menge"]) if z["soll_menge"] is not None else "",
                      _z(z["ist_menge"]) if z["ist_menge"] is not None else "", _z(z["soll"]), _z(z["ist"]),
                      _z(z["abweichung"]), _z(z["prozent"], 1) if z["prozent"] is not None else "", z["erfasst"]])
    n = len(v["zeilen"]) + 1
    inhalt.append(_tabelle(daten, [50 * mm, 13 * mm, 17 * mm, 17 * mm, 19 * mm, 19 * mm, 21 * mm, 15 * mm, 15 * mm],
                           rechts=(2, 3, 4, 5, 6, 7), fett_zeilen=(n, n + 2)))
    inhalt += [Spacer(1, 3 * mm),
               _p("Leere Ist-Werte zählen wie kalkuliert (Spalte erfasst = nein). Zeiten werden mit dem Stundensatz der "
                  "Maschine bewertet, Material mit dem EK-Meterpreis × Stangenlänge (leer = Meterpreis laut "
                  "Schnittplan).", S_KLEIN)]
    doc.build(inhalt, canvasmaker=leinwand)
