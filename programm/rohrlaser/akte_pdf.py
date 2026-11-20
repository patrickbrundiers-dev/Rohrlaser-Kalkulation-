"""Angebotsakte als PDF (Patrick 18.11.2026): neues Dokumentsystem mit eigenem Design, unabhängig von pdf.py.

Setzt die Daten aus angebotsakte.sammeln, rechnet nichts. Drei Dokumente aus derselben Akte:
- kunde:  Seite 1 Kundenangebot, Seite 2 Technische Bauteilübersicht (petrolfarbene Randleiste, Firmenfuß),
- intern: Seiten 3–7 (bernsteinfarbene Leiste „INTERN · NICHT AN KUNDEN“, Fuß mit Kalkulationsstand und Version),
- gesamt: alle Seiten.
Jede „Seite“ läuft bei vielen Positionen über mehrere Blätter (Tabellenköpfe wiederholen sich). Kopf jedes Blatts:
Abschnitt, Angebotsnummer, „Seite x von y“. Schrift IBM Plex Sans/Mono (schriften/, OFL), sonst Helvetica.

kunde_pruefen(pfad) liest das fertige Kunden-PDF und sucht interne Begriffe (Schutztest vor dem Speichern)."""
import base64
import datetime
import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, Image, KeepTogether, LongTable,
                                NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

from . import angebotsakte as akte_
from .angebotsakte import FEHLER, HINWEIS, OK, WARNUNG

# ------------------------------------------------------------------ Gestaltung (eigene Werte dieses Dokuments)
TINTE = colors.HexColor("#16212B")      # Text, Linien unter Tabellenköpfen
STAHL = colors.HexColor("#5B6773")      # Nebentext, Beschriftungen
LINIE = colors.HexColor("#D9DEE3")      # feine Tabellenlinien
FLAECHE = colors.HexColor("#F2F4F6")    # Kacheln, Summenzeilen
KUNDE = colors.HexColor("#0B5563")      # Petrol: Kundenseiten
KUNDE_FL = colors.HexColor("#E3F0F2")
INTERN = colors.HexColor("#B86E00")     # Bernstein: interne Seiten
INTERN_FL = colors.HexColor("#FFF3E0")
GUT, GUT_FL = colors.HexColor("#1E6B34"), colors.HexColor("#E3F4E8")
ROT, ROT_FL = colors.HexColor("#B42318"), colors.HexColor("#FDECEA")
TEIL_FL = colors.HexColor("#D7E8EC")    # Teil im Schnittschema
REST_FL = colors.HexColor("#FBD9A5")
WEISS = colors.white

BLATT_B, BLATT_H = A4
RAND_L, RAND_R, RAND_O, RAND_U = 22 * mm, 15 * mm, 27 * mm, 26 * mm
BREITE = BLATT_B - RAND_L - RAND_R

SCHRIFTEN = {"Akte": ("IBMPlexSans-Regular.ttf", "Helvetica"), "Akte-Medium": ("IBMPlexSans-Medium.ttf", "Helvetica"),
             "Akte-SemiBold": ("IBMPlexSans-SemiBold.ttf", "Helvetica-Bold"),
             "Akte-Bold": ("IBMPlexSans-Bold.ttf", "Helvetica-Bold"),
             "Akte-Italic": ("IBMPlexSans-Italic.ttf", "Helvetica-Oblique"),
             "AkteMono": ("IBMPlexMono-Regular.ttf", "Helvetica"),
             "AkteMono-Medium": ("IBMPlexMono-Medium.ttf", "Helvetica-Bold")}
_NAMEN = {}


def schrift(name):
    """Name der registrierten Schrift (Plex), beim ersten Aufruf geladen; fehlt die Datei: Helvetica."""
    if not _NAMEN:
        ordner = Path(__file__).resolve().parent / "schriften"
        for n, (datei, ersatz) in SCHRIFTEN.items():
            try:
                pdfmetrics.registerFont(TTFont(n, str(ordner / datei)))
                _NAMEN[n] = n
            except Exception:       # noqa: BLE001 – Datei fehlt oder ist beschädigt: Standardschrift
                _NAMEN[n] = ersatz
        try:
            from reportlab.lib.fonts import addMapping
            if _NAMEN["Akte"] == "Akte":
                addMapping("Akte", 0, 0, "Akte")
                addMapping("Akte", 1, 0, "Akte-SemiBold")
                addMapping("Akte", 0, 1, "Akte-Italic")
                addMapping("Akte", 1, 1, "Akte-SemiBold")
        except Exception as e:       # noqa: BLE001 – ohne Zuordnung fett/kursiv: Grundschnitt
            from . import protokoll
            protokoll.warnung(f"Angebotsakte: Schriftschnitte nicht zugeordnet ({type(e).__name__}: {e})")
    return _NAMEN.get(name, "Helvetica")


def plex_geladen():
    return schrift("Akte") == "Akte"


def _stile():
    s, sb, sm, mono, monom = (schrift("Akte"), schrift("Akte-SemiBold"), schrift("Akte-Medium"), schrift("AkteMono"),
                              schrift("AkteMono-Medium"))
    st = dict(
        text=ParagraphStyle("a_text", fontName=s, fontSize=9, leading=12.2, textColor=TINTE),
        klein=ParagraphStyle("a_klein", fontName=s, fontSize=7.6, leading=9.8, textColor=STAHL),
        zelle=ParagraphStyle("a_zelle", fontName=s, fontSize=8.2, leading=10.2, textColor=TINTE),
        zelle_f=ParagraphStyle("a_zelle_f", fontName=sb, fontSize=8.2, leading=10.2, textColor=TINTE),
        zelle_r=ParagraphStyle("a_zelle_r", fontName=s, fontSize=8.2, leading=10.2, textColor=TINTE,
                               alignment=TA_RIGHT),
        kopf=ParagraphStyle("a_kopf", fontName=sm, fontSize=7.2, leading=9, textColor=STAHL),
        kopf_r=ParagraphStyle("a_kopf_r", fontName=sm, fontSize=7.2, leading=9, textColor=STAHL, alignment=TA_RIGHT),
        titel=ParagraphStyle("a_titel", fontName=sb, fontSize=18, leading=22, textColor=KUNDE, spaceAfter=1 * mm),
        titel_i=ParagraphStyle("a_titel_i", fontName=sb, fontSize=15, leading=19, textColor=TINTE, spaceAfter=1 * mm),
        unter=ParagraphStyle("a_unter", fontName=s, fontSize=9.5, leading=13, textColor=STAHL),
        h2=ParagraphStyle("a_h2", fontName=sb, fontSize=10.5, leading=13.5, textColor=TINTE, spaceBefore=2 * mm,
                          spaceAfter=1.6 * mm),
        h3=ParagraphStyle("a_h3", fontName=sm, fontSize=8.8, leading=11.5, textColor=TINTE, spaceAfter=0.8 * mm),
        label=ParagraphStyle("a_label", fontName=sm, fontSize=6.8, leading=8.4, textColor=STAHL),
        wert=ParagraphStyle("a_wert", fontName=sb, fontSize=12.5, leading=15, textColor=TINTE),
        wert_t=ParagraphStyle("a_wert_t", fontName=s, fontSize=8.8, leading=11.5, textColor=TINTE),
        mono=mono, monom=monom, sans=s, semi=sb, medium=sm)
    return st


# ------------------------------------------------------------------ Zahlen
def _de(x, stellen=2):
    if x is None:
        return "–"
    try:
        t = f"{float(x):,.{stellen}f}"
    except (TypeError, ValueError):
        return str(x)
    return t.replace(",", "_").replace(".", ",").replace("_", ".")


def geld(x, stellen=2):
    return "–" if x is None else f"{_de(x, stellen)} €"


def prozent(x, stellen=1):
    return "–" if x is None else f"{_de(x * 100, stellen)} %"


def menge(x):
    if x is None or x == "":
        return ""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    return _de(f, 0) if f == int(f) else _de(f, 2)


def mm_(x, stellen=1):
    if x is None:
        return "–"
    f = float(x)
    return f"{_de(f, 0 if f == int(f) else stellen)} mm"


def minuten(x):
    if x is None:
        return "–"
    x = float(x)
    if x >= 90:
        return f"{_de(x / 60, 2)} h"
    return f"{_de(x, 1)} min"


def datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(iso or "")


def _esc(t):
    return str(t if t is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _p(text, stil):
    return Paragraph(_esc(text).replace("\n", "<br/>"), stil)


# ------------------------------------------------------------------ Blatt: Kopf, Fuß, Randleiste
class _Abschnitt(Flowable):
    """Unsichtbare Marke: ab hier gehört das Blatt zu Seite nr (Titel und Art für Kopf und Randleiste)."""
    def __init__(self, nr, titel, art):
        super().__init__()
        self.nr, self.titel, self.art = nr, titel, art
        self.width = self.height = 0

    def wrap(self, *a):
        return 0, 0

    def draw(self):
        self.canv._akte_abschnitt = (self.nr, self.titel, self.art)


class _Leinwand(rl_canvas.Canvas):
    """Canvas mit Kopf, Fuß und Randleiste je Blatt; „Seite x von y“ nach dem letzten Blatt."""
    akte = None
    art = "gesamt"
    st = None
    version = None
    spalten = ()
    logo = None

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._blaetter = []
        self._akte_abschnitt = (1, "", akte_.KUNDE)

    def showPage(self):
        self._blaetter.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._blaetter)
        for i, zustand in enumerate(self._blaetter, start=1):
            self.__dict__.update(zustand)
            self._rahmen(i, n)
            super().showPage()
        super().save()

    def _rahmen(self, i, n):
        nr, titel, art = self._akte_abschnitt
        st = self.st
        intern = art == akte_.INTERN
        nummer = (self.akte or {}).get("nummer") or ""
        # Randleiste links
        self.saveState()
        if intern:
            self.setFillColor(INTERN)
            self.rect(0, 0, 9 * mm, BLATT_H, stroke=0, fill=1)
            self.setFillColor(WEISS)
            self.setFont(st["semi"], 7.5)
            self.translate(5.9 * mm, BLATT_H / 2)
            self.rotate(90)
            self.drawCentredString(0, 0, "INTERN  ·  NICHT AN KUNDEN WEITERGEBEN  ·  INTERN")
        else:
            self.setFillColor(KUNDE)
            self.rect(0, 0, 3.2 * mm, BLATT_H, stroke=0, fill=1)
        self.restoreState()
        # Kopf
        oben = BLATT_H - 13 * mm
        self.setFillColor(STAHL)
        self.setFont(st["medium"], 7.2)
        links = f"{nr}  ·  {titel}" if titel else ""
        if intern:
            self.setFillColor(INTERN)
            self.drawString(RAND_L, oben + 3.6 * mm, "INTERNE KALKULATION")
            self.setFillColor(TINTE)
            self.setFont(st["semi"], 9)
            self.drawString(RAND_L, oben - 0.6 * mm, links)
        elif not (nr == 1 and self._erste_kundenseite(i)):
            self.setFillColor(KUNDE)
            self.drawString(RAND_L, oben + 3.6 * mm, (self.akte or {}).get("firma") or "")
            self.setFillColor(TINTE)
            self.setFont(st["semi"], 9)
            self.drawString(RAND_L, oben - 0.6 * mm, titel)
        rechts = f"Angebot {nummer}" if nummer else "Angebot"
        self.setFont(st["semi"], 9)
        self.setFillColor(TINTE)
        if not (nr == 1 and self._erste_kundenseite(i) and not intern):
            self.drawRightString(BLATT_B - RAND_R, oben - 0.6 * mm, rechts)
            self.setFont(st["sans"], 7.2)
            self.setFillColor(STAHL)
            self.drawRightString(BLATT_B - RAND_R, oben + 3.6 * mm, f"Seite {i} von {n}")
            self.setStrokeColor(TINTE)
            self.setLineWidth(0.8)
            self.line(RAND_L, oben - 3.2 * mm, BLATT_B - RAND_R, oben - 3.2 * mm)
        # Fuß
        self.setStrokeColor(LINIE)
        self.setLineWidth(0.5)
        self.line(RAND_L, 17.5 * mm, BLATT_B - RAND_R, 17.5 * mm)
        if intern:
            a = self.akte or {}
            self.setFont(st["sans"], 6.8)
            self.setFillColor(STAHL)
            teile = [f"Kalkulationsstand {a.get('fingerabdruck') or '–'}"]
            if self.version:
                teile.append(f"Version {self.version}")
            teile.append(f"erstellt {datum(a.get('erstellt'))} {str(a.get('erstellt') or '')[11:16]}")
            if a.get("bearbeiter"):
                teile.append(a["bearbeiter"])
            self.drawString(RAND_L, 13.2 * mm, "  ·  ".join(teile))
            self.setFillColor(INTERN)
            self.setFont(st["semi"], 6.8)
            self.drawRightString(BLATT_B - RAND_R, 13.2 * mm, "INTERN")
        else:
            self._firmenfuss(i, n)

    def _erste_kundenseite(self, i):
        """Erstes Blatt der Seite 1 (Briefbogen): dort steht der Briefkopf statt des laufenden Kopfs."""
        return getattr(self, "_akte_erstes", None) in (None, i)

    def _firmenfuss(self, i, n):
        st = self.st
        nummer = (self.akte or {}).get("nummer") or ""
        self.setFont(st["semi"], 6.8)
        self.setFillColor(TINTE)
        self.drawRightString(BLATT_B - RAND_R, 13.4 * mm, f"Seite {i} von {n}")
        self.setFont(st["sans"], 6.8)
        self.setFillColor(STAHL)
        self.drawRightString(BLATT_B - RAND_R, 10.3 * mm, f"Angebot {nummer}" if nummer else "")
        spalten = self.spalten or ()
        if not spalten:
            return
        platz = BREITE - 30 * mm
        w = platz / len(spalten)
        for j, spalte in enumerate(spalten):
            for z, zeile in enumerate(spalte[:3]):
                f = st["semi"] if (j == 0 and z == 0) else st["sans"]
                self.setFont(f, 6.8)
                self.setFillColor(TINTE if (j == 0 and z == 0) else STAHL)
                text = zeile
                while text and stringWidth(text, f, 6.8) > w - 3 * mm:
                    text = text[:-2] + "…" if len(text) > 2 else ""
                    if text.endswith("……"):
                        text = text[:-1]
                self.drawString(RAND_L + j * w, (13.4 - 3.1 * z) * mm, text)


def _erstes_blatt_merken(canv, doc):
    """Beim ersten Blatt der Seite 1 dessen Nummer merken (Briefbogen ohne laufenden Kopf)."""
    if getattr(canv, "_akte_erstes", None) is None:
        canv._akte_erstes = canv.getPageNumber()


# ------------------------------------------------------------------ Bausteine
def _tabelle(daten, breiten, rechts=(), kopf=1, summen=(), stil=None, hervor=(), wiederholen=True, klein=False):
    """Tabelle im Stil der Akte: Kopf grau klein, Linie in Tinte darunter, feine Linien zwischen Zeilen, Zahlen rechts
    in Mono. Zellen als Text werden in Absätze gesetzt (Umbruch statt Überlauf)."""
    st = stil
    zeilen = []
    for r, zeile in enumerate(daten):
        neu = []
        for c, x in enumerate(zeile):
            if isinstance(x, str):
                if r < kopf:
                    x = Paragraph(_esc(x), st["kopf_r"] if c in rechts else st["kopf"])
                elif c in rechts:
                    x = Paragraph(_esc(x).replace("\n", "<br/>"), st["zelle_r"] if r not in summen else
                                  ParagraphStyle("sr", parent=st["zelle_r"], fontName=st["semi"]))
                else:
                    x = Paragraph(_esc(x).replace("\n", "<br/>"), st["zelle_f"] if r in summen else st["zelle"])
                if klein and r >= kopf:
                    x.style = ParagraphStyle("k", parent=x.style, fontSize=7.4, leading=9.2)
            neu.append(x)
        zeilen.append(neu)
    t = LongTable(zeilen, colWidths=breiten, repeatRows=kopf if wiederholen else 0)
    befehle = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2.2),
               ("RIGHTPADDING", (0, 0), (-1, -1), 2.2), ("TOPPADDING", (0, 0), (-1, -1), 2.1),
               ("BOTTOMPADDING", (0, 0), (-1, -1), 2.3), ("LINEBELOW", (0, kopf - 1), (-1, kopf - 1), 0.8, TINTE),
               ("LINEBELOW", (0, kopf), (-1, -1), 0.35, LINIE)] if kopf else [
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINIE)]
    for r in summen:
        befehle += [("BACKGROUND", (0, r), (-1, r), FLAECHE), ("LINEABOVE", (0, r), (-1, r), 0.6, TINTE)]
    for r, farbe in hervor:
        befehle += [("BACKGROUND", (0, r), (-1, r), farbe)]
    t.setStyle(TableStyle(befehle))
    return t


def _kacheln(werte, st, breite=BREITE, flaeche=FLAECHE, je_zeile=None):
    """Kennzahlen als ruhige Felder: [(Beschriftung, Wert, Zusatz)]."""
    werte = [w for w in werte if w]
    if not werte:
        return Spacer(1, 0)
    n = je_zeile or min(len(werte), 5)
    zeilen = [werte[i:i + n] for i in range(0, len(werte), n)]
    luecke = 2.5 * mm
    w = (breite - luecke * (n - 1)) / n
    daten = []
    for z in zeilen:
        reihe = []
        for x in z:
            b, v = x[0], x[1]
            zusatz = x[2] if len(x) > 2 else ""
            inhalt = [_p(b.upper(), st["label"]), _p(v, st["wert"])]
            if zusatz:
                inhalt.append(_p(zusatz, st["klein"]))
            reihe.append(inhalt)
        reihe += [""] * (n - len(reihe))
        daten.append(reihe)
    t = Table([sum(([c, ""] for c in r), [])[:-1] for r in daten],
              colWidths=sum(([w, luecke] for _ in range(n)), [])[:-1])
    befehle = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
               ("TOPPADDING", (0, 0), (-1, -1), 2.4 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6 * mm)]
    for r, z in enumerate(daten):
        for c in range(len([x for x in z if x != ""])):
            befehle.append(("BACKGROUND", (2 * c, r), (2 * c, r), flaeche))
    t.setStyle(TableStyle(befehle))
    return t


def _kv(paare, st, breiten=(30 * mm, None), breite=None):
    """Beschriftung/Wert untereinander (Datenblock)."""
    paare = [(a, b) for a, b in paare if b not in (None, "")]
    if not paare:
        return Spacer(1, 0)
    b0 = breiten[0]
    b1 = breiten[1] or ((breite or BREITE) - b0)
    t = Table([[_p(a, st["klein"]), _p(b, st["zelle"])] for a, b in paare], colWidths=[b0, b1])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 0.9),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0.9)]))
    return t


def _ueberschrift(text, st, zusatz=""):
    out = [CondPageBreak(32 * mm), _p(text, st["h2"])]
    if zusatz:
        out.append(_p(zusatz, st["klein"]))
        out.append(Spacer(1, 1.2 * mm))
    return out


def _seiten_titel(nr, titel, art, st, unter=""):
    stil = st["titel"] if art == akte_.KUNDE else st["titel_i"]
    out = [_Abschnitt(nr, titel, art), _p(titel, stil)]
    if unter:
        out.append(_p(unter, st["unter"]))
    out.append(Spacer(1, 4 * mm))
    return out


def _logo(einst, breite=52 * mm, hoehe=20 * mm):
    daten = (einst or {}).get("logo") or ""
    if not daten:
        return None
    try:
        roh = io.BytesIO(base64.b64decode(daten.split(",", 1)[-1]))
        b, h = ImageReader(roh).getSize()
        f = min(breite / b, hoehe / h)
        roh.seek(0)
        bild = Image(roh, width=b * f, height=h * f, mask="auto")
    except Exception:       # noqa: BLE001 – beschädigtes Logo: ohne
        return None
    bild.hAlign = "RIGHT"
    return bild


def firmen_spalten(einst):
    """Firmenangaben in bis zu drei Spalten (Anschrift, Kontakt, Register/Bank) aus den Briefkopfzeilen."""
    from .pdf import brief_spalten     # nur das Lesen der Briefkopf-Einstellungen, keine Gestaltung
    return brief_spalten(einst or {})


def firmenname(einst):
    sp = firmen_spalten(einst)
    return sp[0][0] if sp and sp[0] else ""


# ------------------------------------------------------------------ Seite 1: Kundenangebot
def _seite_kunde(a, einst, st):
    k = a.get("kunde") or {}
    out = [_Abschnitt(1, "Kundenangebot", akte_.KUNDE)]
    logo = _logo(einst)
    firma = firmenname(einst)
    sp = firmen_spalten(einst)
    absender = " · ".join(sp[0][:3]) if sp else firma
    kopf_rechts = logo if logo is not None else _p(firma, ParagraphStyle("fn", parent=st["titel"], fontSize=13,
                                                                        leading=16, alignment=TA_RIGHT))
    kopf = Table([[_p("", st["klein"]), kopf_rechts]], colWidths=[BREITE - 60 * mm, 60 * mm],
                 rowHeights=[20 * mm])
    kopf.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    out += [kopf, Spacer(1, 2 * mm)]
    anschrift = [_p(absender, ParagraphStyle("abs", parent=st["klein"], fontSize=6.6, leading=8)),
                 Spacer(1, 1.5 * mm)]
    zeilen = [x for x in (k.get("anschrift") or []) if x] or [k.get("kunde") or ""]
    anschrift += [_p("\n".join(zeilen), ParagraphStyle("an", parent=st["text"], fontSize=9.6, leading=13))]
    ap = k.get("ansprechpartner") or {}
    info = [("Angebot", k.get("nummer")), ("Datum", datum(k.get("datum"))), ("Kunden-Nr.", k.get("kundennr")),
            ("Ihre Anfrage", k.get("kundenreferenz")), ("Projekt", k.get("projekt")), ("Ansprechpartner", ap.get("name")),
            ("Telefon", ap.get("telefon")), ("E-Mail", ap.get("email")),
            ("Gültig bis", datum(k.get("gueltig_bis")) if k.get("gueltig_bis") else "")]
    block = Table([[anschrift, _kv(info, st, (26 * mm, 46 * mm))]], colWidths=[BREITE - 74 * mm, 74 * mm],
                  rowHeights=[38 * mm])
    block.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    out += [block, Spacer(1, 6 * mm), _p(f"Angebot {k.get('nummer') or ''}", st["titel"])]
    if k.get("projekt"):
        out.append(_p(f"Projekt: {k['projekt']}" + (f" · Ihre Anfrage: {k['kundenreferenz']}"
                                                   if k.get("kundenreferenz") else ""), st["unter"]))
    elif k.get("kundenreferenz"):
        out.append(_p(f"Projekt / Ihre Anfrage: {k['kundenreferenz']}", st["unter"]))
    out += [Spacer(1, 2.5 * mm), _p("Vielen Dank für Ihre Anfrage. Wir bieten Ihnen die folgenden Teile an:",
                                    st["text"]), Spacer(1, 3 * mm)]
    # Positionen
    b = [12 * mm, None, 18 * mm, 25 * mm, 27 * mm]
    b[1] = BREITE - sum(x for x in b if x)
    daten = [["Pos.", "Bauteil", "Menge", "Einzelpreis", "Gesamtpreis"]]
    for z in k.get("zeilen") or ():
        text = f"<font name='{st['semi']}'>{_esc(z.get('artikel'))}</font>" if z.get("artikel") else ""
        rest = _esc(z.get("text") or "").replace("\n", "<br/>")
        text = text + ("<br/>" if text and rest else "") + rest
        if z.get("staffeln"):
            text += "<br/><font size='7.2' color='#5B6773'>Staffel: " + " · ".join(
                f"{_esc(s.get('bereich'))} {_esc(z.get('einheit') or 'Stk.')} je {_esc(geld(s.get('preis')))}"
                for s in z["staffeln"]) + "</font>"
        if z.get("muster"):
            text += "<br/><font size='7.2' color='#5B6773'>Musterteil</font>"
        daten.append([z.get("pos") or "", Paragraph(text, st["zelle"]),
                      f"{menge(z.get('menge'))} {z.get('einheit') or ''}".strip(), geld(z.get("preis")),
                      geld(z.get("gesamt"))])
    out.append(_tabelle(daten, b, rechts=(2, 3, 4), stil=st))
    # Summen
    mw = k.get("mwst_satz") or 0
    summe = Table([[_p("Netto-Zwischensumme", st["zelle"]), _p(geld(k.get("netto")), st["zelle_r"])],
                   [_p(f"Mehrwertsteuer {_de(mw * 100, 0)} %", st["zelle"]), _p(geld(k.get("mwst")), st["zelle_r"])],
                   [_p("Gesamtsumme brutto", ParagraphStyle("bs", parent=st["zelle_f"], fontSize=10, leading=13,
                                                            textColor=KUNDE)),
                    _p(geld(k.get("brutto")), ParagraphStyle("bw", parent=st["zelle_r"], fontName=st["semi"],
                                                             fontSize=10.5, leading=13, textColor=KUNDE))]],
                  colWidths=[48 * mm, 32 * mm])
    summe.setStyle(TableStyle([("LINEABOVE", (0, 2), (-1, 2), 1, KUNDE), ("BACKGROUND", (0, 2), (-1, 2), KUNDE_FL),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4),
                               ("LEFTPADDING", (0, 0), (-1, -1), 3)]))
    aussen = Table([["", summe]], colWidths=[BREITE - 80 * mm, 80 * mm])
    aussen.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    # Konditionen
    tage = k.get("gueltig_tage")
    gueltig = f"{tage} Tage" if tage else ""
    if k.get("gueltig_bis"):
        gueltig = (gueltig + f", bis {datum(k['gueltig_bis'])}").strip(", ")
    felder = [("Lieferzeit", k.get("lieferzeit") or "nach Absprache"), ("Angebotsgültigkeit", gueltig or "–"),
              ("Zahlungsbedingungen", k.get("zahlung") or "–")]
    # Angebotswesen P3: zweite Reihe Versand, Verpackung, Rabatt (nur wenn bekannt; ältere Akten ohne die Werte)
    zweite = [(t, v) for t, v in (("Versand", k.get("versand")), ("Verpackung", k.get("verpackung")),
                                  ("Rabatt", f"{_de(k['rabatt_satz'], 1)} % in den Preisen berücksichtigt"
                                   if k.get("rabatt_satz") else "")) if v]
    fw = (BREITE - 2 * 2.5 * mm) / 3
    reihen = [felder] + ([zweite] if zweite else [])
    zellen = []
    for r in reihen:
        r = list(r) + [None] * (3 - len(r))
        zellen.append(sum(([[_p(t.upper(), st["label"]), _p(v, st["wert_t"])] if t else "", ""] for t, v in
                           (x or (None, None) for x in r)), [])[:-1])
    kond = Table(zellen, colWidths=[fw, 2.5 * mm, fw, 2.5 * mm, fw])
    kond.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 2.2 * mm),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6 * mm), ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm)]
                             + [("BACKGROUND", (2 * c, r), (2 * c, r), FLAECHE) for r, reihe in enumerate(reihen)
                                for c in range(len(reihe))]
                             + ([("TOPPADDING", (0, 1), (-1, 1), 1.2 * mm)] if len(reihen) > 1 else [])))
    schluss = [Spacer(1, 4 * mm), aussen, Spacer(1, 6 * mm), kond, Spacer(1, 3 * mm)]
    if k.get("termine"):
        daten = [["Liefertermin", "Angebotspreis netto", "gegenüber diesem Angebot"]]
        for t in k["termine"]:
            d = t.get("differenz") or 0
            daten.append([t["termin"], geld(t["netto"]), "–" if abs(d) < 0.005 else
                          (("+" if d > 0 else "−") + geld(abs(d)))])
        b = [None, 40 * mm, 46 * mm]
        b[0] = BREITE - sum(x for x in b if x)
        schluss += [KeepTogether([_p("Preis nach Liefertermin", st["h3"]),
                                  _tabelle(daten, b, rechts=(1, 2), stil=st, wiederholen=False)]), Spacer(1, 3 * mm)]
    for t in [k.get("bedingungen")] + list(k.get("texte") or ()) + [k.get("agb")]:
        if t:
            schluss.append(_p(t, st["text"]))
            schluss.append(Spacer(1, 1.2 * mm))
    schluss += [Spacer(1, 4 * mm), _p("Mit freundlichen Grüßen", st["text"]), Spacer(1, 1 * mm),
                _p(" · ".join(x for x in (ap.get("name"), firma) if x), st["zelle_f"])]
    out.append(KeepTogether(schluss[:4]))
    out += schluss[4:]
    return out


# ------------------------------------------------------------------ Seite 2: Technik
class _OhneBild(Flowable):
    """Platzhalter ohne 3D-Daten: Querschnitt angedeutet und Hinweis."""
    def __init__(self, w, h, profil, st):
        super().__init__()
        self.w, self.h, self.profil, self.st = w, h, profil, st

    def wrap(self, *a):
        return self.w, self.h

    def draw(self):
        c = self.canv
        c.setFillColor(FLAECHE)
        c.roundRect(0, 0, self.w, self.h, 1.5 * mm, stroke=0, fill=1)
        c.setStrokeColor(STAHL)
        c.setLineWidth(1.2)
        x, y, r = self.w / 2, self.h / 2 + 3 * mm, 6 * mm
        if str(self.profil or "").upper().startswith(("RR", "Ø", "ROHR")):
            c.circle(x, y, r, stroke=1, fill=0)
            c.circle(x, y, r - 1.2 * mm, stroke=1, fill=0)
        else:
            c.rect(x - r, y - r * 0.75, 2 * r, 1.5 * r, stroke=1, fill=0)
            c.rect(x - r + 1.2 * mm, y - r * 0.75 + 1.2 * mm, 2 * r - 2.4 * mm, 1.5 * r - 2.4 * mm, stroke=1, fill=0)
        c.setFillColor(STAHL)
        c.setFont(self.st["sans"], 6.8)
        c.drawCentredString(x, 4 * mm, "keine 3D-Daten")


def _bild(png, w, h):
    try:
        roh = io.BytesIO(png)
        bw, bh = ImageReader(roh).getSize()
        f = min(w / bw, h / bh)
        roh.seek(0)
        return Image(roh, width=bw * f, height=bh * f)
    except Exception:       # noqa: BLE001
        return None


def _seite_technik(a, st):
    teile = a.get("technik") or []
    out = _seiten_titel(2, "Technische Bauteilübersicht", akte_.KUNDE, st,
                        f"{len(teile)} Position(en) · Abbildungen aus dem 3D-Modell, nicht maßstäblich")
    bw, bh = 64 * mm, 44 * mm
    for t in teile:
        bild = _bild(t["bild"], bw, bh) if t.get("bild") else None
        if bild is None:
            bild = _OhneBild(bw, bh, t.get("profil"), st)
        kopf = f"Pos. {t['pos']}  ·  {t['artikel'] or t['bezeichnung'] or t['art']}"
        werte = []
        if t.get("bezeichnung") and t.get("artikel"):
            werte.append(("Bezeichnung", t["bezeichnung"]))
        werte.append(("Art", t.get("art")))
        if t.get("material"):
            werte.append(("Material", t["material"] + (f" ({t['werkstoff']})" if t.get("werkstoff") else "")))
        if t.get("guete"):
            werte.append(("Werkstoffgüte", t["guete"] + (f", {t['norm']}" if t.get("norm") else "")))
        if t.get("profil"):
            werte.append(("Profil", " ".join(x for x in (t.get("form"), t["profil"]) if x)))
        if t.get("wand"):
            werte.append(("Wandstärke", mm_(t["wand"])))
        if t.get("laenge"):
            werte.append(("Bauteillänge", mm_(t["laenge"])))
        werte.append(("Stückzahl", menge(t.get("stueck"))))
        if t.get("oberflaeche"):
            werte.append(("Oberfläche", t["oberflaeche"]))
        if t.get("bearbeitung"):
            werte.append(("Bearbeitung", t["bearbeitung"]))
        if t.get("hinweise"):
            werte.append(("Hinweise", " · ".join(t["hinweise"])))
        rechts = [_p(kopf, st["h3"]), _kv(werte, st, (26 * mm, BREITE - bw - 6 * mm - 26 * mm))]
        karte = Table([[bild, rechts]], colWidths=[bw + 4 * mm, BREITE - bw - 4 * mm])
        karte.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                   ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
                                   ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
                                   ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINIE)]))
        out.append(KeepTogether([karte]))
    return out


# ------------------------------------------------------------------ Seite 3: Schnittschema
def _bereiche(nummern):
    """[1,2,3,5] -> '1–3, 5'."""
    out, start, vor = [], None, None
    for n in sorted(nummern):
        if start is None:
            start = vor = n
        elif n == vor + 1:
            vor = n
        else:
            out.append(f"{start}–{vor}" if vor > start else str(start))
            start = vor = n
    if start is not None:
        out.append(f"{start}–{vor}" if vor > start else str(start))
    return ", ".join(out)


class StangenSchema(Flowable):
    """Eine Stange maßstäblich: Endbeschnitt, Teile mit Pos.-Nr., Schnitte mit Schnittfolge, Teileabstand, Rest,
    Greiferrest, Maßstab in mm darunter."""
    HOEHE = 23 * mm

    def __init__(self, muster, st, breite=BREITE):
        super().__init__()
        self.m, self.st, self.breite = muster, st, breite

    def wrap(self, *a):
        return self.breite, self.HOEHE

    def draw(self):
        c, m, st = self.canv, self.m, self.st
        lang = max(1.0, m["stange"])
        x0, x1 = 0, self.breite
        f = (x1 - x0) / lang
        y, h = 9 * mm, 8 * mm

        def x(v):
            return x0 + v * f
        # Rohling
        c.setStrokeColor(TINTE)
        c.setLineWidth(0.6)
        c.setFillColor(WEISS)
        c.rect(x0, y, x1 - x0, h, stroke=1, fill=1)
        # Endbeschnitt (schraffiert grau)
        if m["end"] > 0:
            self._schraffur(x(0), y, max(0.6, m["end"] * f), h, STAHL)
        teile = sorted(m["teile"], key=lambda t: t["von"])
        ende = m["end"]
        for n, t in enumerate(teile, start=1):
            a, b = x(t["von"]), x(t["bis"])
            c.setFillColor(TEIL_FL)
            c.setStrokeColor(KUNDE)
            c.setLineWidth(0.4)
            c.rect(a, y, max(0.4, b - a), h, stroke=1, fill=1)
            label = t["pos"]
            c.setFillColor(TINTE)
            for gr in (6.6, 5.6, 4.8):
                if stringWidth(label, st["medium"], gr) < (b - a) - 1.2:
                    c.setFont(st["medium"], gr)
                    c.drawCentredString((a + b) / 2, y + h / 2 - gr * 0.35, label)
                    break
            # Schnitt am Teilende mit Nummer der Schnittfolge
            c.setStrokeColor(INTERN)
            c.setLineWidth(0.7)
            c.line(b, y - 0.8 * mm, b, y + h + 0.8 * mm)
            if (b - a) > 3.2 * mm or n == len(teile) or n % 2 == 1:
                c.setFillColor(INTERN)
                c.circle(b, y + h + 2.6 * mm, 1.45 * mm, stroke=0, fill=1)
                c.setFillColor(WEISS)
                c.setFont(st["semi"], 5 if n < 10 else 4.3)
                c.drawCentredString(b, y + h + 2.6 * mm - 1.6, str(n))
            ende = max(ende, t["bis"])
        greif_ab = m["stange"] - m["greif"]
        if greif_ab - ende > 0.5:
            self._schraffur(x(ende), y, (greif_ab - ende) * f, h, INTERN, REST_FL)
            if (greif_ab - ende) * f > 16 * mm:
                text = f"Rest {_de(greif_ab - ende, 0)} mm"
                tw = stringWidth(text, st["medium"], 6) + 2.4 * mm
                mx = (x(ende) + x(greif_ab)) / 2
                c.setFillColor(WEISS)
                c.rect(mx - tw / 2, y + h / 2 - 2 * mm, tw, 4 * mm, stroke=0, fill=1)
                c.setFillColor(INTERN)
                c.setFont(st["medium"], 6)
                c.drawCentredString(mx, y + h / 2 - 2, text)
        if m["greif"] > 0:
            c.setFillColor(STAHL)
            c.rect(x(greif_ab), y, m["greif"] * f, h, stroke=0, fill=1)
            if m["greif"] * f > 7 * mm:
                c.setFillColor(WEISS)
                c.setFont(st["medium"], 5)
                c.drawCentredString((x(greif_ab) + x1) / 2, y + h / 2 - 1.8, "Greifer")
        # Maßstab
        c.setStrokeColor(STAHL)
        c.setLineWidth(0.4)
        c.line(x0, y - 2.2 * mm, x1, y - 2.2 * mm)
        schritt = 1000 if lang > 3000 else 500 if lang > 1200 else 100
        c.setFont(st["sans"], 5.6)
        c.setFillColor(STAHL)
        v = 0
        while v <= lang + 0.1:
            c.line(x(v), y - 2.2 * mm, x(v), y - 3.3 * mm)
            if x1 - x(v) > 10 * mm or v == 0:
                c.drawCentredString(x(v) if v else x(v) + 2.5, y - 6 * mm, _de(v, 0))
            v += schritt
        c.drawRightString(x1, y - 6 * mm, f"{_de(lang, 0)} mm")

    def _schraffur(self, x, y, w, h, farbe, grund=None):
        c = self.canv
        c.saveState()
        if grund is not None:
            c.setFillColor(grund)
            c.rect(x, y, w, h, stroke=0, fill=1)
        p = c.beginPath()
        p.rect(x, y, w, h)
        c.clipPath(p, stroke=0, fill=0)
        c.setStrokeColor(farbe)
        c.setLineWidth(0.4)
        d = 1.6 * mm
        i = -h
        while i < w:
            c.line(x + i, y, x + i + h, y + h)
            i += d
        c.restoreState()


class _Legende(Flowable):
    def __init__(self, st):
        super().__init__()
        self.st = st

    def wrap(self, *a):
        return BREITE, 6 * mm

    def draw(self):
        c, st = self.canv, self.st
        x = 0
        for text, art in (("Teil (Pos.-Nr.)", "teil"), ("Schnitt mit Schnittfolge", "schnitt"),
                          ("Endbeschnitt", "end"), ("Rest (nur Info)", "rest"), ("Greiferrest", "greif")):
            if art == "teil":
                c.setFillColor(TEIL_FL)
                c.setStrokeColor(KUNDE)
                c.rect(x, 1.2 * mm, 6 * mm, 3 * mm, stroke=1, fill=1)
            elif art == "schnitt":
                c.setFillColor(INTERN)
                c.circle(x + 3 * mm, 2.7 * mm, 1.4 * mm, stroke=0, fill=1)
            elif art == "end":
                c.setFillColor(FLAECHE)
                c.setStrokeColor(STAHL)
                c.rect(x, 1.2 * mm, 6 * mm, 3 * mm, stroke=1, fill=1)
            elif art == "rest":
                c.setFillColor(REST_FL)
                c.setStrokeColor(INTERN)
                c.rect(x, 1.2 * mm, 6 * mm, 3 * mm, stroke=1, fill=1)
            else:
                c.setFillColor(STAHL)
                c.rect(x, 1.2 * mm, 6 * mm, 3 * mm, stroke=0, fill=1)
            c.setFillColor(STAHL)
            c.setFont(st["sans"], 6.8)
            c.drawString(x + 7.5 * mm, 1.8 * mm, text)
            x += 8 * mm + stringWidth(text, st["sans"], 6.8) + 6 * mm


def _seite_schnitt(a, st):
    s = a.get("schnitt") or {}
    out = _seiten_titel(3, "Schnittschema und Materialausnutzung", akte_.INTERN, st,
                        "Aus dem gespeicherten Schnittplan der Optimierung" + ("" if s.get("aktuell", True) else
                                                                              " – ACHTUNG: Schnittplan veraltet"))
    if not s.get("vorhanden"):
        out.append(_p("Kein Schnittplan vorhanden (keine Rohrlaserteile oder noch nicht optimiert).", st["text"]))
        return out + _nicht_eingeplant(s, st)
    su = s["summe"]
    out += [_kacheln([("Rohre", menge(su.get("stangen")), f"{menge(su.get('lieferstangen'))} Lieferstangen"
                      if su.get("lieferstangen") != su.get("stangen") else ""),
                      ("Materialverbrauch", f"{_de(su.get('meter'), 1)} m", f"{_de(su.get('kg'), 1)} kg"),
                      ("Ausnutzung", prozent(su.get("ausnutzung")), f"Nutzlänge {_de(su.get('nutz'), 2)} m"),
                      ("Verschnitt", f"{_de(su.get('verschnitt'), 2)} m", "Schnitt, Beschnitt, Rest"),
                      ("Materialrest", f"{_de(su.get('rest'), 2)} m", "ohne Greiferrest, nur Info")], st,
                     flaeche=INTERN_FL),
            Spacer(1, 3 * mm), _Legende(st), Spacer(1, 1 * mm)]
    for g in s.get("gruppen") or ():
        kopf = f"{g['profil']}  ·  {g['werkstoff']}" + (f"  ·  {g['oberflaeche']}" if g.get("oberflaeche") else "") \
            + f"  ·  Rohmaterial {mm_(g['stange'])}"
        zus = (f"{g['stangen']} Rohr(e), Einsatz {_de(g['meter'], 2)} m, Nutzlänge {_de(g['nutz'], 2)} m, "
               f"Ausnutzung {prozent(g.get('ausnutzung'))}, Verschnitt {_de(g['verschnitt'], 2)} m")
        vorweg = [_p(kopf, st["h2"]), _p(zus, st["klein"]), Spacer(1, 1.2 * mm)]
        for m in g["muster"]:
            nummern = [n for n in m["nummern"] if n is not None]
            welche = f"Rohr {_bereiche(nummern)}" if nummern else "Rohr"
            teile_text = ", ".join(f"{p}.{_bereiche(n)}" if len(n) == 1 else f"{p}.{min(n)}–{p}.{max(n)}"
                                   if n == list(range(min(n), max(n) + 1)) else f"{p}: {_bereiche(n)}"
                                   for p, n in m["teilnummern"].items())
            gemeinsam = sum(1 for t in m["teile"] if t["gemeinsam"])
            zeile = (f"<font name='{st['semi']}'>{_esc(welche)}</font>"
                     + (f"  <font name='{st['monom']}' color='#B86E00'>× {m['anzahl']}</font>" if m["anzahl"] > 1
                        else "")
                     + f"  ·  {len(m['teile'])} {'Teil' if len(m['teile']) == 1 else 'Teile'}  ·  Ausnutzung "
                       f"{prozent(m.get('ausnutzung'))}"
                     + f"  ·  Endbeschnitt {_de(m['end'], 1)}  ·  Greiferrest {_de(m['greif'], 1)}"
                     + f"  ·  Rest {_de(m['rest_frei'], 1)} mm")
            folge = f"Schnittfolge 1–{len(m['teile'])} von links" if len(m["teile"]) > 1 else "ein Schnitt"
            unten = (f"{'Teil' if len(m['teile']) == 1 else 'Teile'} {teile_text}  ·  {folge}"
                     + (f"  ·  {gemeinsam} gemeinsame Schnitte" if gemeinsam else "")
                     + (f"  ·  Teileabstand/Schnittverlust gesamt {_de(m['verlust'], 1)} mm" if m.get("verlust")
                        else "") + ("  ·  Werkstück einer zugeschnittenen Lieferstange" if m.get("zugeschnitten")
                                    else ""))
            out.append(KeepTogether(vorweg + [Paragraph(zeile, st["zelle"]), StangenSchema(m, st),
                                              _p(unten, st["klein"]), Spacer(1, 2.5 * mm)]))
            vorweg = []
    return out + _nicht_eingeplant(s, st)


def _nicht_eingeplant(s, st):
    liste = s.get("nicht_eingeplant") or []
    if not liste:
        return [Spacer(1, 2 * mm), _p("Alle Teile sind eingeplant.", ParagraphStyle("ok", parent=st["zelle"],
                                                                                   textColor=GUT))]
    daten = [["Pos.", "Artikel", "Nicht eingeplant"]]
    for x in liste:
        daten.append([x.get("pos") or "", x.get("artikel") or x.get("text") or "", menge(x.get("anzahl")) if
                      x.get("anzahl") else ""])
    return _ueberschrift("Nicht vollständig eingeplante Teile", st) + [
        _tabelle(daten, [16 * mm, BREITE - 56 * mm, 40 * mm], rechts=(2,), stil=st, hervor=[
            (r, ROT_FL) for r in range(1, len(daten))])]


# ------------------------------------------------------------------ Seite 4: Material
def _seite_material(a, st):
    m = a.get("material") or {}
    out = _seiten_titel(4, "Materialkalkulation", akte_.INTERN, st,
                        "Einkaufspreise aus den Stammdaten (Preise, Lieferlängen), Mengen aus dem Schnittplan")
    gr = m.get("gruppen") or []
    out += [_kacheln([("Material (Kalkulation)", geld(m.get("material"))),
                      ("Rohmaterial laut Schnittplan", geld(m.get("schnitt_kosten"))),
                      ("Verschnitt (Wert)", geld(sum(g["verschnitt_eur"] for g in gr))),
                      ("Schrotterlös", geld(m.get("schrott")))], st, flaeche=INTERN_FL), Spacer(1, 2 * mm)]
    out += _ueberschrift("Einkauf und Preise je Abmessung", st)
    b = [33 * mm, 24 * mm, 30 * mm, 26 * mm, 15 * mm, 15 * mm, None]
    b[-1] = BREITE - sum(x for x in b if x)
    daten = [["Profil", "Werkstoff", "Lieferant", "Einkaufspreis", "€/m", "€/kg", "Preisstand"]]
    for g in gr:
        prof = " ".join(x for x in (g["profil"], f"(Wand {_de(g['wand'], 1)})" if g.get("wand") else "") if x)
        ek = f"{_de(g['preis'], 2)} {g['basis']}" if g.get("preis") is not None else "–"
        ek = ek.replace("€/Stange", "€/St.")
        stand = (g.get("quelle") or "") + (f"\nab {datum(g['gueltig_ab'])}" if g.get("gueltig_ab") else "")
        if g.get("hand"):
            stand = "Meterpreis von Hand"
        if g.get("kunde"):
            stand, ek = "Kundenmaterial (beigestellt)", "–"
        daten.append([prof, f"{g['werkstoff']}\n{g.get('material') or ''}".strip(), g.get("lieferant") or "–", ek,
                      _de(g.get("eur_m"), 2) if g.get("eur_m") is not None else "–",
                      _de(g.get("eur_kg"), 2) if g.get("eur_kg") is not None else "–", stand])
    out.append(_tabelle(daten, b, rechts=(3, 4, 5), stil=st))
    out += _ueberschrift("Bedarf, Verbrauch und Verschnitt", st,
                         f"Reststücke ab {mm_(m.get('rest_min'))} nur als Info (kein Restelager); Verschnitt = Einsatz − "
                         "Nutzlänge (Schnittverlust, Endbeschnitt, Greiferrest, Rest)" if m.get("rest_min") else
                         "Verschnitt = Einsatz − Nutzlänge (Schnittverlust, Endbeschnitt, Greiferrest, Rest); kein Restelager")
    b = [36 * mm, 17 * mm, 12 * mm, 17 * mm, 17 * mm, 17 * mm, 24 * mm, 15 * mm, None]
    b[-1] = BREITE - sum(x for x in b if x)
    daten = [["Profil / Werkstoff", "Rohmaterial", "Rohre", "Bedarf Teile [m]", "Einsatz [m]", "Gewicht [kg]",
              "Verschnitt [m]", "Rest [m]", "Kosten"]]
    for g in gr:
        verschn = f"{_de(g['verschnitt_m'], 2)} ({prozent(1 - g['ausnutzung']) if g.get('ausnutzung') is not None else '–'})"
        daten.append([f"{g['profil']}\n{g['werkstoff']}", mm_(g["stange"]), menge(g["stangen"]),
                      _de(g["teile_m"], 2), _de(g["meter"], 2), _de(g["kg"], 1), verschn, _de(g["rest_m"], 2),
                      geld(g["kosten"])])
    if gr:
        daten.append(["Summe", "", menge(sum(g["stangen"] for g in gr)), _de(sum(g["teile_m"] for g in gr), 2),
                      _de(sum(g["meter"] for g in gr), 2), _de(sum(g["kg"] for g in gr), 1),
                      _de(sum(g["verschnitt_m"] for g in gr), 2), _de(sum(g["rest_m"] for g in gr), 2),
                      geld(sum(g["kosten"] for g in gr))])
    out.append(_tabelle(daten, b, rechts=(1, 2, 3, 4, 5, 6, 7, 8), stil=st, summen=(len(daten) - 1,) if gr else ()))
    rest = sum(g["restwert"] for g in gr)
    out += [Spacer(1, 2 * mm), _kv([("Verschnitt (Wert)", geld(sum(g["verschnitt_eur"] for g in gr))
                                     + " – im Material enthalten, wird nur gemeldet"),
                                    ("Restmaterialwert", geld(rest) + " – nur Info, kein Restelager" if rest else ""),
                                    ("Ausschuss Material", geld(m.get("ausschuss_material")) if m.get(
                                        "ausschuss_material") else ""),
                                    ("Lagerzins", geld(m.get("lagerzins")) if m.get("lagerzins") else "")],
                                   st, (36 * mm, None))]
    out += _ueberschrift("Materialkosten je Bauteil", st)
    b = [14 * mm, None, 34 * mm, 22 * mm, 16 * mm, 24 * mm, 26 * mm]
    b[1] = BREITE - sum(x for x in b if x)
    daten = [["Pos.", "Artikel", "Profil / Werkstoff", "Länge", "Stück", "Material je Stück", "Material gesamt"]]
    for t in m.get("teile") or ():
        daten.append([t["pos"], t["artikel"] + (" (Kundenmaterial)" if t.get("kunde") else ""),
                      f"{t['profil']}\n{t['werkstoff']}", mm_(t["laenge"]), menge(t["stueck"]), geld(t["teil"]),
                      geld(t["gesamt"])])
    if m.get("teile"):
        daten.append(["", "Summe Bauteile", "", "", "", "", geld(sum(t["gesamt"] for t in m["teile"]))])
    out.append(_tabelle(daten, b, rechts=(3, 4, 5, 6), stil=st, summen=(len(daten) - 1,) if m.get("teile") else ()))
    out.append(Spacer(1, 1.5 * mm))
    out.append(_p("Material der Kalkulation = Summe der Bauteile; der Wert laut Schnittplan kann davon abweichen "
                  "(Musterteile, Kundenmaterial, Mindermengen und Lieferlängen werden in der Kalkulation verteilt).",
                  st["klein"]))
    return out


# ------------------------------------------------------------------ Seite 5: Fertigung
def _seite_fertigung(a, st):
    f = a.get("fertigung") or {}
    la = f.get("laser") or {}
    out = _seiten_titel(5, "Fertigungskalkulation", akte_.INTERN, st,
                        f"Maschine {la.get('maschine') or '–'}" + (f" ({la['maschine_name']})" if la.get("maschine_name")
                                                                   else "") + f" · {menge(la.get('teile'))} Teile")
    out += [_kacheln([("Maschinenlaufzeit", minuten(la.get("lauf_min")), "Schneiden + Rüsten + Wechsel"),
                      ("Schneidzeit", minuten(la.get("schneid_min"))), ("Rüstzeit", minuten(la.get("ruest_min"))),
                      ("Programmierzeit", minuten(la.get("prog_min"))),
                      ("Stundensatz", f"{_de(la.get('satz'), 2)} €/h", "Maschine")], st, flaeche=INTERN_FL),
            Spacer(1, 2 * mm)]
    out += _ueberschrift("Rohrlaser", st)
    daten = [["Kostenart", "Menge", "Zeit", "Satz", "Kosten"]]
    daten += [["Schneiden (Laserzeit netto)", f"{menge(la.get('teile'))} Teile", minuten(la.get("schneid_min")),
               f"{_de(la.get('satz_laser'), 2)} €/h", geld(la.get("schneid_eur"))],
              ["Schneidgas", f"{_de(la.get('gas_m3'), 2)} m³", "", "", geld(la.get("gas_eur"))],
              ["Rüsten Maschine und Abmessungen", f"{menge(la.get('laeufe'))} Lauf/Läufe", minuten(la.get("ruest_min")),
               f"{_de(la.get('satz'), 2)} €/h", geld(la.get("ruest_eur"))],
              ["Materialhandling (Stangenwechsel)", f"{menge(la.get('wechsel'))} Wechsel", minuten(la.get("wechsel_min")),
               f"{_de(la.get('satz'), 2)} €/h", geld(la.get("wechsel_eur"))]]
    if la.get("bereit_eur") or la.get("bereit_min"):
        daten.append(["Materialbereitstellung", "", minuten(la.get("bereit_min")), "", geld(la.get("bereit_eur"))])
    daten.append(["Programmierung", "", minuten(la.get("prog_min")), "", geld(la.get("prog_eur"))])
    summe = sum(la.get(n) or 0 for n in ("schneid_eur", "gas_eur", "ruest_eur", "wechsel_eur", "bereit_eur",
                                         "prog_eur"))
    daten.append(["Summe Rohrlaser", "", "", "", geld(summe)])
    b = [None, 30 * mm, 24 * mm, 26 * mm, 28 * mm]
    b[0] = BREITE - sum(x for x in b if x)
    out.append(_tabelle(daten, b, rechts=(1, 2, 3, 4), stil=st, summen=(len(daten) - 1,)))
    je = f.get("je_pos") or []
    if je:
        out += _ueberschrift("Laser je Position", st, "Zeit je Teil = Laserzeit netto aus Schneiddaten und Schneidweg")
        daten = [["Pos.", "Artikel", "Stück", "Schneidweg", "Einstiche", "Zeit je Teil", "Laser je Teil", "Rüsten je Teil"]]
        for x in je:
            daten.append([x["pos"], x["artikel"], menge(x["stueck"]), mm_(x["schneidweg"]) if x["schneidweg"] else "–",
                          menge(x["einstiche"]) if x["einstiche"] else "–", f"{_de(x['laser_s'], 1)} s",
                          geld(x["laser_teil"], 3), geld(x["ruesten_teil"], 3)])
        b = [14 * mm, None, 14 * mm, 22 * mm, 16 * mm, 20 * mm, 22 * mm, 22 * mm]
        b[1] = BREITE - sum(x for x in b if x)
        out.append(_tabelle(daten, b, rechts=(2, 3, 4, 5, 6, 7), stil=st))
    schritte = f.get("schritte") or []
    out += _ueberschrift("Weitere Bearbeitungsschritte je Position", st,
                         "Jeder Schritt einzeln. Gewinde, Senken, Flowdrill und Bohren nur mit Preis je Stück.")
    if schritte:
        daten = [["Pos.", "Art", "Arbeitsschritt", "Menge", "Zeit", "je Stück", "Gesamt", ""]]
        for x in schritte:
            daten.append([x["pos"], x["art"], x["name"] + (f"\n{x['basis']}" if x.get("basis") else ""),
                          f"{menge(x['menge'])} {x.get('einheit') or ''}".strip(),
                          "" if x["art"] in akte_.NUR_STUECKPREIS or not x.get("min") else minuten(x["min"]),
                          geld(x["je"]) if x["je"] or not x["eur"] else "einmalig", geld(x["eur"]),
                          "fremd" if x.get("fremd") else "eigen"])
        daten.append(["", "", "Summe", "", "", "", geld(sum(x["eur"] for x in schritte)), ""])
        b = [12 * mm, 22 * mm, None, 18 * mm, 17 * mm, 20 * mm, 22 * mm, 12 * mm]
        b[2] = BREITE - sum(x for x in b if x)
        out.append(_tabelle(daten, b, rechts=(3, 4, 5, 6), stil=st, summen=(len(daten) - 1,), klein=True))
    else:
        out.append(_p("Keine weiteren Bearbeitungsschritte im Angebot.", st["klein"]))
    an = f.get("angebot_schritte") or []
    if an:
        out += _ueberschrift("Arbeitsschritte des Angebots", st, "Aus der Vorgabe Arbeitsschritte, für das ganze Angebot")
        daten = [["Arbeitsschritt", "Art", "Menge", "Zeit", "Satz", "Kosten"]]
        for x in an:
            daten.append([x["name"] + (f"\n{x['quelle']}" if x.get("quelle") else ""), x["art"],
                          f"{menge(x['menge'])} {x['einheit']}".strip(), minuten(x["min"]) if x["min"] else "",
                          f"{_de(x['satz'], 2)} €/h" if x["satz"] else "", geld(x["eur"])])
        b = [None, 24 * mm, 26 * mm, 20 * mm, 22 * mm, 24 * mm]
        b[0] = BREITE - sum(x for x in b if x)
        out.append(_tabelle(daten, b, rechts=(2, 3, 4, 5), stil=st, klein=True))
    return out


# ------------------------------------------------------------------ Seite 6: Zukauf
def _seite_zukauf(a, st):
    z = a.get("zukauf") or {}
    out = _seiten_titel(6, "Zukauf- und Normteile", akte_.INTERN, st,
                        "Zukaufteile, Normteile und Fremdleistungen nur mit Aufschlag, ohne Gewinn")
    artikel = z.get("artikel") or []
    if artikel:
        b = [22 * mm, 22 * mm, None, 12 * mm, 15 * mm, 17 * mm, 20 * mm, 18 * mm, 21 * mm]
        b[2] = BREITE - sum(x for x in b if x)
        for art in [x for x, _ in akte_.ZUKAUF_ARTEN] + ["Kaufteile"]:
            liste = [x for x in artikel if x["art"] == art]
            if not liste:
                continue
            out += _ueberschrift(art, st)
            daten = [["Art.-Nr.", "Lieferant", "Bezeichnung", "Pos.", "Menge", "EK je Einh.", "Einstand", "Aufschlag",
                      "Gesamt"]]
            for x in liste:
                daten.append([x["artikelnr"], x["lieferant"] or "–", x["bezeichnung"] + (f"\n{x['hinweis']}" if
                                                                                        x.get("hinweis") else ""),
                              ", ".join(x["positionen"]), f"{menge(x['menge'])}", geld(x["ek"], 3), geld(x["einstand"]),
                              f"{prozent(x['satz'], 0) if x.get('satz') is not None else ''}\n{geld(x['aufschlag'])}",
                              geld(x["gesamt"])])
            out.append(_tabelle(daten, b, rechts=(4, 5, 6, 7, 8), stil=st, klein=True))
    fremd = z.get("fremd") or []
    if fremd:
        out += _ueberschrift("Fremdfertigungsleistungen", st)
        daten = [["Pos.", "Leistung", "Menge", "je Stück", "Gesamt"]]
        for x in fremd:
            daten.append([x["pos"], x["name"], menge(x["menge"]), geld(x["je"]), geld(x["eur"])])
        b = [14 * mm, None, 20 * mm, 24 * mm, 26 * mm]
        b[1] = BREITE - sum(x for x in b if x)
        out.append(_tabelle(daten, b, rechts=(2, 3, 4), stil=st))
    out += [Spacer(1, 3 * mm), _kv([("Zukauf Einstand", geld(z.get("einstand"))),
                                    ("Aufschlag Zukauf", geld(z.get("aufschlag")) + " (ersetzt Zuschläge und Gewinn)"),
                                    ("Zukauf gesamt", geld(_n(z.get("einstand")) + _n(z.get("aufschlag")))),
                                    ("Zuschlag Fremdleistung", geld(z.get("zuschlag_fremd")) if z.get("zuschlag_fremd")
                                     else ""),
                                    ("Ohne Preis", f"{z['fehlt']} Artikel" if z.get("fehlt") else "")], st, (36 * mm, None))]
    return out


def _n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------------ Seite 7: Gesamt
class _Anteile(Flowable):
    """Kostenanteile als ein gestapelter Balken mit Beschriftung darunter."""
    FARBEN = ["#16212B", "#0B5563", "#3E8A97", "#7FB3BD", "#B86E00", "#E0A54C", "#5B6773", "#9AA6B1", "#1E6B34",
              "#7FBF8E", "#C7CFD6", "#E9C46A"]

    def __init__(self, teile, gesamt, st):
        super().__init__()
        self.teile = [(t, b) for t, b in teile if b > 0.005]
        self.gesamt, self.st = gesamt, st
        self.zeilen = (len(self.teile) + 2) // 3

    def wrap(self, *a):
        return BREITE, 9 * mm + self.zeilen * 4.2 * mm

    def draw(self):
        c, st = self.canv, self.st
        summe = sum(b for _, b in self.teile) or 1
        y = self.zeilen * 4.2 * mm + 2 * mm
        x = 0
        for i, (_, b) in enumerate(self.teile):
            w = BREITE * b / summe
            c.setFillColor(colors.HexColor(self.FARBEN[i % len(self.FARBEN)]))
            c.rect(x, y, w, 5 * mm, stroke=0, fill=1)
            x += w
        spalte = BREITE / 3
        for i, (t, b) in enumerate(self.teile):
            r, s = divmod(i, 3)
            yy = y - 4.2 * mm * (r + 1) + 0.6 * mm
            c.setFillColor(colors.HexColor(self.FARBEN[i % len(self.FARBEN)]))
            c.rect(s * spalte, yy, 2.4 * mm, 2.4 * mm, stroke=0, fill=1)
            c.setFillColor(STAHL)
            c.setFont(st["sans"], 6.6)
            text = f"{t.split(' (')[0]} {_de(b / summe * 100, 1)} %"
            c.drawString(s * spalte + 3.6 * mm, yy + 0.3 * mm, text)


def _seite_gesamt(a, st):
    g = a.get("gesamt") or {}
    out = _seiten_titel(7, "Gesamtkalkulation", akte_.INTERN, st,
                        "Alle Werte aus der Kalkulation des Angebots; Gewinn auf die Selbstkosten ohne Zukaufteile")
    out += [_kacheln([("Selbstkosten", geld(g.get("selbst"), 0)), ("Verkaufspreis", geld(g.get("verkauf"), 0)),
                      ("Gewinn", geld(g.get("gewinn"), 0)), ("Gewinnmarge", prozent(g.get("marge"))),
                      ("Deckungsbeitrag", geld(g.get("deckungsbeitrag"), 0), prozent(g.get("db_satz")))],
                     st, flaeche=INTERN_FL), Spacer(1, 3 * mm)]
    stufe1 = [(x["titel"], x["betrag"]) for x in g.get("gruppen") or () if x["stufe"] == 1]
    out += [_p("Anteile an den Selbstkosten", st["h3"]), _Anteile(stufe1, g.get("selbst"), st), Spacer(1, 2 * mm)]
    out += _ueberschrift("Kostenaufbau bis zum Verkaufspreis", st)
    verkauf = g.get("verkauf") or 0
    daten = [["Kostenposition", "Betrag", "Anteil am Verkaufspreis"]]
    summen = []
    for x in [x for x in g.get("gruppen") or () if x["stufe"] == 1]:
        if abs(x["betrag"]) < 0.005:
            continue
        daten.append([x["titel"], geld(x["betrag"]), prozent(x["betrag"] / verkauf) if verkauf else "–"])
        if x["namen"][0] == "material" and g.get("verschnitt_eur"):
            daten.append(["      davon Verschnittkosten (nur Info, im Material enthalten)", geld(g["verschnitt_eur"]),
                          ""])
    daten.append(["Selbstkosten", geld(g.get("selbst")), prozent(g.get("selbst") / verkauf) if verkauf else "–"])
    summen.append(len(daten) - 1)
    for x in [x for x in g.get("gruppen") or () if x["stufe"] == 2]:
        if abs(x["betrag"]) < 0.005:
            continue
        titel = x["titel"]
        if x["namen"] == ("gewinn",) and g.get("gewinn_satz") is not None:
            titel += f" ({prozent(g['gewinn_satz'])}{' gestaffelt' if g.get('gewinn_gestaffelt') else ''} auf " \
                     f"{geld(g.get('gewinn_basis'))})"
        daten.append([titel, geld(x["betrag"]), prozent(x["betrag"] / verkauf) if verkauf else "–"])
    daten.append(["Kalkulierter Verkaufspreis (netto)", geld(verkauf), "100,0 %"])
    summen.append(len(daten) - 1)
    b = [None, 32 * mm, 38 * mm]
    b[0] = BREITE - sum(x for x in b if x)
    out.append(_tabelle(daten, b, rechts=(1, 2), stil=st, summen=summen,
                        hervor=[(len(daten) - 1, INTERN_FL)]))
    out += _ueberschrift("Ergebnis", st)
    out.append(_kv([("Verkaufspreis Angebot", f"{geld(g.get('angebot_netto'))} netto (Rundung der Stückpreise "
                                              f"{geld(g.get('rundung_stueck'))})"),
                    ("Verkaufspreis pro Stück", f"{geld(g.get('je_teil'))} im Mittel über {menge(g.get('teile'))} Teile"
                     if g.get("je_teil") else ""),
                    ("Gesamtverkaufspreis", f"{geld(g.get('verkauf'))} netto"),
                    ("Gewinn", f"{geld(g.get('gewinn'))} = {prozent(g.get('marge'))} vom Verkaufspreis"),
                    ("Gewinnbasis", f"{geld(g.get('gewinn_basis'))} (Selbstkosten ohne Zukaufteile: auf Zukauf und "
                                    "Bleche nur Aufschlag)"),
                    ("Deckungsbeitrag", f"{geld(g.get('deckungsbeitrag'))} = Verkaufspreis − variable Kosten "
                                        f"{geld(g.get('variabel'))} (Material, Schrott, Gas, Zukauf, Fremdleistung, "
                                        "Fracht, Skonto)"),
                    ("Preisuntergrenze", f"kurzfristig {geld(g.get('untergrenze_kurz'))}, langfristig "
                                         f"{geld(g.get('untergrenze_lang'))}" if g.get("untergrenze_lang") else "")],
                   st, (38 * mm, None)))
    if g.get("termine"):
        out += _ueberschrift("Preis nach Liefertermin", st, "Termin-Staffel der Einstellungen; Abschläge höchstens bis "
                                                            "zur Mindestmarge")
        daten = [["Liefertermin", "Satz", "Netto", "Unterschied", "Marge"]]
        for t in g["termine"]:
            satz = prozent(t["satz_wirksam"])
            if t.get("begrenzt"):
                satz += f"\n(statt {prozent(t['satz'])}, Mindestmarge {prozent(g.get('mindestmarge'))})"
            daten.append([t["termin"], satz, geld(t["netto"]), geld(t["differenz"]),
                          prozent(t["marge"]) if t.get("marge") is not None else "–"])
        b = [None, 40 * mm, 28 * mm, 26 * mm, 18 * mm]
        b[0] = BREITE - sum(x for x in b if x)
        out.append(_tabelle(daten, b, rechts=(1, 2, 3, 4), stil=st))
    je = g.get("je_pos") or []
    if je:
        out += _ueberschrift("Je Position", st)
        daten = [["Pos.", "Artikel", "Stück", "Selbstkosten/Stk", "Preis/Stk", "Gewinn/Stk", "Marge", "Gesamt"]]
        for x in je:
            daten.append([x["pos"], x["artikel"] + (f"\n{x['teil_von']}" if x.get("teil_von") else ""), menge(x["stueck"]),
                          geld(x["selbst"]), geld(x["preis"]),
                          geld(x["gewinn"]), prozent(x["marge"]) if x.get("marge") is not None else "–",
                          geld(x["gesamt"])])
        b = [12 * mm, None, 14 * mm, 25 * mm, 22 * mm, 22 * mm, 16 * mm, 24 * mm]
        b[1] = BREITE - sum(x for x in b if x)
        out.append(_tabelle(daten, b, rechts=(2, 3, 4, 5, 6, 7), stil=st))
    out += _pruefliste(a, st)
    return out


FARBE_STUFE = {OK: (GUT, GUT_FL, "OK"), HINWEIS: (STAHL, FLAECHE, "Hinweis"), WARNUNG: (INTERN, INTERN_FL, "Warnung"),
               FEHLER: (ROT, ROT_FL, "Fehler")}


def _pruefliste(a, st):
    liste = a.get("pruefung") or []
    if not liste:
        return []
    daten = []
    stile = []
    for r, (stufe, text) in enumerate(liste):
        farbe, fl, wort = FARBE_STUFE.get(stufe, FARBE_STUFE[HINWEIS])
        daten.append([_p(wort, ParagraphStyle("ps", parent=st["zelle_f"], textColor=farbe, fontSize=7.4)),
                      _p(text, st["zelle"])])
        stile.append(("BACKGROUND", (0, r), (0, r), fl))
    t = Table(daten, colWidths=[20 * mm, BREITE - 20 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINIE),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.8), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)] + stile))
    return _ueberschrift("Prüfliste", st, "Abgleich der Akte mit der Kalkulation vor der Freigabe") + [t]


def _sek(x):
    return "–" if x is None else f"{_de(x, 1)} s"


def _seite_kalkblatt(a, st):
    """Seite 8: Technisches Kalkulationsblatt (Angebotswesen P2). Je Position Schneidwege, Vorschübe, Zeitanteile und
    die Kosten je Teil bis zum Preis, alles aus der Kalkulation des Angebots."""
    teile = a.get("kalkblatt") or []
    out = _seiten_titel(8, "Technisches Kalkulationsblatt", akte_.INTERN, st,
                        f"{len(teile)} Position(en) · Zeiten je Teil in Sekunden, Kosten je Teil und je Position")
    if not teile:
        return out + [_p("Keine Positionen.", st["zelle"])]
    daten = [["Pos.", "Artikel", "Stück", "Laserzeit/Stk", "Herstell/Stk", "Selbst/Stk", "Preis/Stk", "Marge"]]
    for t in teile:
        daten.append([t["pos"], t["artikel"] or t["bezeichnung"] or t["art"], menge(t["stueck"]),
                      _sek(t["laser_netto"]) if t["laser"] else "–", geld(t["herstell"]), geld(t["selbst"]),
                      geld(t["preis"]), prozent(t["marge"]) if t.get("marge") is not None else "–"])
    b = [12 * mm, None, 14 * mm, 24 * mm, 24 * mm, 24 * mm, 22 * mm, 16 * mm]
    b[1] = BREITE - sum(x for x in b if x)
    out += [_tabelle(daten, b, rechts=(2, 3, 4, 5, 6, 7), stil=st), Spacer(1, 2 * mm)]
    halb = (BREITE - 6 * mm) / 2
    for t in teile:
        block = []
        block += _ueberschrift(f"Pos. {t['pos']}  ·  {t['artikel'] or t['bezeichnung'] or t['art']}", st,
                             t["bezeichnung"] if t.get("artikel") else "")
        links = [("Art", t["art"]), ("Profil", t["profil"]), ("Werkstoff", t["werkstoff"]),
                 ("Bauteillänge", mm_(t["laenge"]) if t.get("laenge") else ""), ("Stückzahl", menge(t["stueck"]))]
        rechts = [("Maschine", t["maschine"]), ("Schneidgas", t["gas"]),
                  ("Schneiddaten", " · ".join(x for x in (f"Wand bis {mm_(t['wand_stufe'])}" if t.get("wand_stufe")
                                                          else "", t.get("sd_herkunft") or "") if x)),
                  ("Laserzeit", "von Hand vorgegeben" if t.get("zeit_manuell") else
                   (f"Faktor {_de(t['faktor'], 2)}" if abs((t.get("faktor") or 1) - 1) > 1e-9 else "")),
                  ("Hinweis", t.get("hinweis") or "")]
        kopf = Table([[_kv(links, st, (24 * mm, halb - 24 * mm)), _kv(rechts, st, (24 * mm, halb - 24 * mm))]],
                     colWidths=[halb + 6 * mm, halb])
        kopf.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                  ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        block += [kopf, Spacer(1, 2 * mm)]
        if t["laser"] and (t["wege"] or t["zeiten"] or t["laser_netto"]):
            daten = [["Zeitanteil je Teil", "Weg", "Vorschub", "Anzahl", "Zeit"]]
            for w in t["wege"]:
                if "anzahl" in w:
                    daten.append([w["text"] + (f" (je {_de(w['einstechzeit'], 1)} s)" if w.get("einstechzeit")
                                               is not None else ""), "", "", menge(w["anzahl"]), _sek(w["s"])])
                else:
                    daten.append([w["text"], mm_(w["mm"]), f"{_de(w['vorschub'], 0)} mm/min"
                                  if w.get("vorschub") else "–", "", _sek(w["s"])])
            for z in t["zeiten"]:
                daten.append([z["text"], "", "", "", _sek(z["s"])])
            summen = []
            if t["einsparung"] and abs(t["laser_brutto"] - t["laser_netto"]) > 0.05:
                daten.append(["Laserzeit brutto", "", "", "", _sek(t["laser_brutto"])])
                daten.append(["Einsparung (gemeinsame Schnitte, Teile im Verbund)", "", "", "",
                              _sek(t["laser_netto"] - t["laser_brutto"])])
            daten.append(["Laserzeit genutzt je Teil", "", "", "", _sek(t["laser_netto"])])
            summen.append(len(daten) - 1)
            b = [None, 26 * mm, 28 * mm, 18 * mm, 22 * mm]
            b[0] = BREITE - sum(x for x in b if x)
            block += [_tabelle(daten, b, rechts=(1, 2, 3, 4), stil=st, summen=summen, klein=True),
                      Spacer(1, 2 * mm)]
        daten = [["Kosten", "je Teil", "Position", "Anteil am Preis"]]
        summen, hervor = [], []
        preis = t["preis"] or 0
        for k in t["kosten"]:
            daten.append([k["text"], geld(k["teil"], 4 if abs(k["teil"]) < 1 else 2), geld(k["position"]),
                          prozent(k["teil"] / preis) if preis else "–"])
            if k["stufe"]:
                summen.append(len(daten) - 1)
        hervor.append((len(daten) - 1, INTERN_FL))
        if t.get("vk_angebot") is not None and abs(t["vk_angebot"] - preis) > 0.005:
            daten.append(["Stückpreis im Angebot (gerundet bzw. von Hand)", geld(t["vk_angebot"]),
                          geld(t["vk_angebot"] * (t["stueck"] or 0)), ""])
        b = [None, 28 * mm, 28 * mm, 28 * mm]
        b[0] = BREITE - sum(x for x in b if x)
        block.append(_tabelle(daten, b, rechts=(1, 2, 3), stil=st, summen=summen, hervor=hervor, klein=True))
        out.append(KeepTogether(block))     # eine Position nicht über zwei Blätter, wenn sie auf eines passt
    return out


# ------------------------------------------------------------------ Dokument
BAUER = {1: lambda a, e, st: _seite_kunde(a, e, st), 2: lambda a, e, st: _seite_technik(a, st),
         3: lambda a, e, st: _seite_schnitt(a, st), 4: lambda a, e, st: _seite_material(a, st),
         5: lambda a, e, st: _seite_fertigung(a, st), 6: lambda a, e, st: _seite_zukauf(a, st),
         7: lambda a, e, st: _seite_gesamt(a, st), 8: lambda a, e, st: _seite_kalkblatt(a, st)}


def schreiben(pfad, akte, einst=None, art="gesamt", seiten=None, version=None):
    """PDF der Akte schreiben. art kunde/intern/gesamt, seiten = gewählte Seitennummern (None = alle der Art),
    version = Versionsnummer für den Fuß der internen Seiten. Ergebnis: Liste der gesetzten Seitennummern."""
    st = _stile()
    nummern = akte_.seiten_fuer(art, akte, seiten)
    if not nummern:
        raise ValueError("Keine Seite gewählt")
    akte = dict(akte, firma=firmenname(einst))
    titel = f"{akte_.ARTEN[art][0]} {akte.get('nummer') or ''}".strip()
    doc = BaseDocTemplate(str(pfad), pagesize=A4, leftMargin=RAND_L, rightMargin=RAND_R, topMargin=RAND_O,
                          bottomMargin=RAND_U, title=titel, author=akte["firma"] or "Rohrlaser-Kalkulation",
                          subject=f"Angebot {akte.get('nummer') or ''}", creator="Rohrlaser-Kalkulation Angebotsakte")
    rahmen = Frame(RAND_L, RAND_U, BREITE, BLATT_H - RAND_O - RAND_U, id="f", leftPadding=0, rightPadding=0,
                   topPadding=0, bottomPadding=0)
    erst = Frame(RAND_L, RAND_U, BREITE, BLATT_H - 12 * mm - RAND_U, id="e", leftPadding=0, rightPadding=0,
                 topPadding=0, bottomPadding=0)
    vorlagen = [PageTemplate("brief", [erst], onPage=_erstes_blatt_merken), PageTemplate("blatt", [rahmen])]
    doc.addPageTemplates(vorlagen if nummern[0] == 1 else vorlagen[::-1])
    inhalt = [] if nummern[0] == 1 else [_KeinBrief()]
    for j, nr in enumerate(nummern):
        if j:
            inhalt += [NextPageTemplate("blatt"), PageBreak()]
        if nr == 1:
            inhalt.append(NextPageTemplate("blatt"))
        inhalt += BAUER[nr](akte, einst or {}, st)
    leinwand = type("Leinwand", (_Leinwand,), dict(akte=akte, art=art, st=st, version=version,
                                                   spalten=firmen_spalten(einst)))
    doc.build(inhalt, canvasmaker=leinwand)
    return nummern


class _KeinBrief(Flowable):
    """Dokument ohne Seite 1: es gibt keinen Briefbogen, jedes Blatt hat den laufenden Kopf."""
    def wrap(self, *a):
        return 0, 0

    def draw(self):
        self.canv._akte_erstes = -1


# Begriffe, die im Kunden-PDF nie stehen dürfen (Schutztest)
INTERNE_BEGRIFFE = ("INTERN", "Selbstkosten", "Stundensatz", "Einkaufspreis", "Einstand", "Gewinn", "Marge",
                    "Deckungsbeitrag", "€/h", "Verschnitt", "Schnittschema", "Lieferant", "Aufschlag", "Kalkulation",
                    "Rüstzeit", "Schneidzeit", "Maschinenlaufzeit", "Preisuntergrenze", "Kalkulationsstand")


def text_der_seiten(pfad):
    import pypdfium2 as pdfium
    d = pdfium.PdfDocument(str(pfad))
    try:
        return [d[i].get_textpage().get_text_range() for i in range(len(d))]
    finally:
        d.close()


def kunde_pruefen(pfad, erlaubt=()):
    """Interne Begriffe im fertigen Kunden-PDF: [(Seite, Begriff)], leer = sauber. erlaubt: Begriffe, die der
    Benutzer selbst in Texte des Angebots geschrieben hat (z. B. „Lieferant“ im Freitext)."""
    funde = []
    for i, t in enumerate(text_der_seiten(pfad), start=1):
        for b in INTERNE_BEGRIFFE:
            if b in t and b not in erlaubt:
                funde.append((i, b))
    return funde
