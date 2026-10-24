"""Erzeugt anleitung/Bedienungsanleitung.pdf und Kurzanleitung.pdf: bebilderte Anleitungen des Programms.

Die Bilder kommen aus dem echten Programm (anleitung/bilder.py, unsichtbar mit Beispieldaten), der Text
steht unten in den Funktionen kapitel_…. Beide PDF entstehen aus denselben Kapiteln: die Kurzanleitung nimmt
Teil A bis C (ohne Anhang) und davon nur Bildfolgen, Bildschirmfotos mit Legende und was kurz=True hat (Inhalt).
Nach Änderungen am Programm einfach neu erzeugen:

    python anleitung/erzeuge_anleitung.py [--ziel DATEI.pdf] [--kurz KURZ.pdf] [--bilder ORDNER]

Braucht PySide6, reportlab, openpyxl, OpenCascade (für den STEP-Import der Testteile) und pdftoppm
(Poppler, für die Seitenbilder der PDF-Ausgaben). Unter Linux zusätzlich libegl1.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, KeepTogether, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.flowables import HRFlowable
from reportlab.platypus.tableofcontents import TableOfContents

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import NAME, VERSION  # noqa: E402
from rohrlaser.neuerungen import IN_ANLEITUNG, NEUERUNGEN  # noqa: E402
from rohrlaser.tastatur import UEBERSICHT as TASTENKUERZEL  # noqa: E402

SEITE = landscape(A4)
RAND = 14 * mm
BREITE = SEITE[0] - 2 * RAND
# Farben wie im Angebots-PDF (programm/rohrlaser/pdf.py): Dunkelblau als einzige Akzentfarbe, keine Gitter
BLAU = colors.HexColor("#1F4E78")
HELLBLAU = colors.HexColor("#EAF1F8")
MITTELBLAU = colors.HexColor("#8EA9C1")
ROT = colors.HexColor("#D0021B")
GRAU = colors.HexColor("#595959")
LINIE = colors.HexColor("#D9D9D9")
KOPF_H = 7 * mm              # Kopfzeile mit Teil und Kapitel
TITEL_BAND = 78 * mm         # dunkelblaues Band oben auf der Titelseite

S = ParagraphStyle("text", fontName="Helvetica", fontSize=10, leading=13.5, spaceAfter=4)
S_LISTE = ParagraphStyle("liste", parent=S, leftIndent=12, bulletIndent=2, spaceAfter=2)
S_H1 = ParagraphStyle("h1", parent=S, fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=BLAU,
                      spaceBefore=0, spaceAfter=3)
S_TEIL = ParagraphStyle("teil", parent=S_H1, fontSize=30, leading=36, spaceAfter=4)
S_TEIL_NR = ParagraphStyle("teil_nr", parent=S, fontName="Helvetica-Bold", fontSize=13, leading=16,
                           textColor=MITTELBLAU, spaceAfter=2)
S_TEIL_KURZ = ParagraphStyle("teil", parent=S_TEIL_NR, fontSize=11, spaceAfter=6)   # Name "teil": Stufe 0 im Inhalt
S_H2 = ParagraphStyle("h2", parent=S, fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=BLAU,
                      spaceBefore=8, spaceAfter=4)
S_BILD = ParagraphStyle("bild", parent=S, fontSize=8.5, leading=10.5, textColor=GRAU, alignment=TA_CENTER,
                        spaceBefore=2, spaceAfter=8)
S_LEGENDE = ParagraphStyle("legende", parent=S, fontSize=9.5, leading=12.5, spaceAfter=0)
S_TIPP = ParagraphStyle("tipp", parent=S, fontSize=9.5, leading=12.5, spaceAfter=0)
S_TOC0 = ParagraphStyle("toc0", parent=S, fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=BLAU,
                        spaceBefore=8, spaceAfter=2, leftIndent=0)
S_TOC1 = ParagraphStyle("toc1", parent=S, fontName="Helvetica-Bold", fontSize=10.5, leading=15, leftIndent=8,
                        spaceBefore=2)
S_TOC2 = ParagraphStyle("toc2", parent=S, fontSize=9.5, leading=12.5, leftIndent=24, textColor=colors.HexColor("#404040"))
S_KASTEN = ParagraphStyle("kasten", parent=S, fontSize=9.5, leading=12.5, spaceAfter=0)
S_KASTEN_KOPF = ParagraphStyle("kasten_kopf", parent=S_KASTEN, fontName="Helvetica-Bold", textColor=BLAU)
# Kasten „Genauer“: Einzelheiten zum Nachlesen, kleiner gesetzt; fehlen in der Kurzanleitung
S_GENAUER_KOPF = ParagraphStyle("genauer_kopf", parent=S, fontName="Helvetica-Bold", fontSize=9.5, leading=12,
                                textColor=BLAU, backColor=HELLBLAU, borderPadding=(3, 4, 3, 4), spaceBefore=10,
                                spaceAfter=7)
S_KLEIN = ParagraphStyle("klein_text", parent=S, fontSize=9, leading=12, spaceAfter=3, textColor=colors.HexColor("#262626"))
S_KLEIN_LISTE = ParagraphStyle("klein_liste", parent=S_KLEIN, leftIndent=12, bulletIndent=2, spaceAfter=1.5)
S_SCHRITT = ParagraphStyle("schritt", parent=S, fontSize=9.5, leading=12.5, spaceAfter=0)


# ---------------------------------------------------------------- Bausteine
class Nummer(Flowable):
    """Rote Nummer wie im Bildschirmfoto."""

    def __init__(self, nr, d=5.2 * mm):
        super().__init__()
        self.nr, self.d = nr, d
        self.width = self.height = d

    def draw(self):
        c = self.canv
        c.setFillColor(ROT)
        c.circle(self.d / 2, self.d / 2, self.d / 2, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawCentredString(self.d / 2, self.d / 2 - 3, str(self.nr))


class BildBlock(Flowable):
    """Bilder nebeneinander mit Überschrift, Unterschrift und Legende als ein Block, der nicht getrennt wird.
    Passt er nicht mehr ganz auf die Seite, werden die Bilder bis auf 70 % verkleinert; reicht das nicht,
    beginnt der Block auf der nächsten Seite in voller Größe."""

    ABSTAND = 6 * mm

    def __init__(self, pfade, max_hoehe, oben=(), unten=()):
        super().__init__()
        from reportlab.lib.utils import ImageReader
        self.groessen = [ImageReader(str(p)).getSize() for p in pfade]
        self.pfade, self.max_hoehe, self.oben, self.unten = pfade, max_hoehe, list(oben), list(unten)

    def _bilder(self, breite, hoehe):
        je = (breite - self.ABSTAND * (len(self.pfade) - 1)) / len(self.pfade)
        return [(p, min(je / w, hoehe / h) * w, min(je / w, hoehe / h) * h) for p, (w, h) in zip(self.pfade, self.groessen)]

    def wrap(self, verf_breite, verf_hoehe):
        self.breite = verf_breite
        texte = sum(f.wrap(verf_breite, verf_hoehe)[1] + f.getSpaceBefore() + f.getSpaceAfter()
                    for f in self.oben + self.unten)
        voll = max(h for _, _, h in self._bilder(verf_breite, self.max_hoehe))
        platz = verf_hoehe - texte - 2
        bild_h = voll if platz >= voll or platz < 0.7 * voll else platz
        self.liste = self._bilder(verf_breite, bild_h)
        self.bild_h = max(h for _, _, h in self.liste)
        self.height = texte + self.bild_h + 2
        return verf_breite, self.height

    def draw(self):
        c, y = self.canv, self.height
        for f in self.oben:
            _, h = f.wrap(self.breite, y)
            y -= f.getSpaceBefore() + h
            f.drawOn(c, 0, y)
            y -= f.getSpaceAfter()
        gesamt = sum(w for _, w, _ in self.liste) + self.ABSTAND * (len(self.liste) - 1)
        x = (self.breite - gesamt) / 2
        for pfad, w, h in self.liste:
            c.drawImage(str(pfad), x, y - h, w, h)
            c.setStrokeColor(LINIE)
            c.setLineWidth(0.6)
            c.rect(x, y - h, w, h)
            x += w + self.ABSTAND
        y -= self.bild_h + 2
        for f in self.unten:
            _, h = f.wrap(self.breite, y)
            y -= f.getSpaceBefore() + h
            f.drawOn(c, 0, y)
            y -= f.getSpaceAfter()


class Anleitung(BaseDocTemplate):
    """Seiten wie das Angebots-PDF: Titelseite mit dunkelblauem Band, sonst Kopfzeile (Teil, Kapitel) und Fuß
    (Programm, Seite) mit feiner Linie."""

    def __init__(self, ziel, art="Bedienungsanleitung"):
        self.art = art
        super().__init__(str(ziel), pagesize=SEITE, leftMargin=RAND, rightMargin=RAND, topMargin=RAND,
                         bottomMargin=RAND + 4 * mm, title=f"{NAME} – {art}",
                         author=NAME, subject=f"{art} Version {VERSION}")
        titel = Frame(RAND, RAND + 4 * mm, BREITE, SEITE[1] - RAND - 4 * mm - TITEL_BAND - 8 * mm, id="titel",
                      leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        rahmen = Frame(RAND, RAND + 4 * mm, BREITE, SEITE[1] - 2 * RAND - 4 * mm - KOPF_H, id="text",
                       leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate("titel", [titel], onPage=self._titelband),
                               PageTemplate("normal", [rahmen], onPageEnd=self._kopf_fuss)])
        self._kapitel = self._teil = ""

    def beforeDocument(self):
        # multiBuild läuft mehrmals; sonst stünde das letzte Kapitel im Kopf des Inhaltsverzeichnisses
        self._kapitel = self._teil = ""

    def _titelband(self, c, doc):
        c.saveState()
        c.setFillColor(BLAU)
        c.rect(0, SEITE[1] - TITEL_BAND, SEITE[0], TITEL_BAND, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 32)
        c.drawString(RAND + 4 * mm, SEITE[1] - 34 * mm, NAME)
        c.setFont("Helvetica", 20)
        c.drawString(RAND + 4 * mm, SEITE[1] - 47 * mm, self.art)
        c.setFillColor(colors.HexColor("#C9D7E5"))
        c.setFont("Helvetica", 11)
        c.drawString(RAND + 4 * mm, SEITE[1] - 62 * mm, "Angebotskalkulation und Materialoptimierung für Rohrlaserteile")
        c.drawRightString(SEITE[0] - RAND - 4 * mm, SEITE[1] - 62 * mm, f"Programmversion {VERSION} · Stand {doc.stand}")
        c.restoreState()

    def _kopf_fuss(self, c, doc):
        c.saveState()
        oben = SEITE[1] - RAND
        c.setFont("Helvetica", 8)
        c.setFillColor(GRAU)
        c.drawString(RAND, oben - 3 * mm, self._teil)
        c.setFillColor(BLAU)
        c.setFont("Helvetica-Bold", 8)
        c.drawRightString(SEITE[0] - RAND, oben - 3 * mm, self._kapitel)
        c.setStrokeColor(BLAU)
        c.setLineWidth(0.8)
        c.line(RAND, oben - 5 * mm, SEITE[0] - RAND, oben - 5 * mm)
        c.setStrokeColor(LINIE)
        c.setLineWidth(0.5)
        c.line(RAND, RAND + 1 * mm, SEITE[0] - RAND, RAND + 1 * mm)
        c.setFont("Helvetica", 8)
        c.setFillColor(GRAU)
        c.drawString(RAND, RAND - 3 * mm, f"{NAME} {VERSION} – {self.art}")
        c.setFillColor(BLAU)
        c.setFont("Helvetica-Bold", 8)
        c.drawRightString(SEITE[0] - RAND, RAND - 3 * mm, f"Seite {doc.page}")
        c.restoreState()

    def afterFlowable(self, f):
        if isinstance(f, (BildBlock, KeepTogether)):
            for x in (f.oben if isinstance(f, BildBlock) else f._content):
                self.afterFlowable(x)
            return
        stufen = {"teil": 0, "h1": 1, "h2": 2}
        if isinstance(f, Paragraph) and f.style.name in stufen:
            text = getattr(f, "toc_text", None) or f.getPlainText()
            stufe = stufen[f.style.name]
            if stufe == 0:
                self._teil, self._kapitel = text, ""
            elif stufe == 1:
                self._kapitel = text
            if stufe == 2 and self.art == "Kurzanleitung":
                return
            schluessel = f"k{id(f)}"
            self.canv.bookmarkPage(schluessel)
            self.canv.addOutlineEntry(text, schluessel, level=stufe, closed=stufe == 1)
            self.notify("TOCEntry", (stufe, text, self.page, schluessel))


class Inhalt:
    """Sammelt die Flowables; Kurzformen für Text, Listen, Bilder, Legenden und Hinweise.

    Verweise stehen im Text als [[marke]] und werden zu „Kapitel 6.7“ mit Link auf die Überschrift, die mit
    marke="…" angelegt ist. Die Nummern kennt erst ein vollständiger Durchlauf: pdf_bauen sammelt sie im
    ersten Durchlauf (marken=None) und setzt sie im zweiten ein; eine unbekannte Marke ist dann ein Fehler."""

    VERWEIS = re.compile(r"\[\[([a-z0-9_]+)\]\]")

    def __init__(self, bilder, vorlauf=None, kurz=False):
        """vorlauf: das Inhalt-Objekt des 1. Durchlaufs (Kapitelnummern, Titel und Kapitel je Teil).

        kurz: Kurzanleitung aus denselben Kapiteln. Sie zeigt nur Überschriften, Steckbriefe, Bildfolgen
        (schritte), Bildschirmfotos mit Legende und was ausdrücklich kurz=True hat; Fließtext, Listen, Tabellen und
        die Kästen „Genauer“ bleiben weg. Kapitel- und Abschnittsnummern sind dieselben wie in der
        Bedienungsanleitung, Verweise lauten „Anleitung 6.3“."""
        self.bilder, self.f, self.kapitel_nr, self.abschnitt_nr = bilder, [], 0, 0
        self.marken = vorlauf.neue_marken if vorlauf else None
        self.titel = vorlauf.neue_titel if vorlauf else {}
        self.teile = vorlauf.neue_teile if vorlauf else {}
        self.neue_marken, self.neue_titel, self.neue_teile, self.benutzte_bilder = {}, {}, {}, set()
        self.verweise, self._teil = {}, None
        self.kurz, self._genauer, self._offen = kurz, False, []    # _offen: Abschnitt wartet auf ein Bild (kurz)

    def _zeigen(self, kurz):
        """Steht der Baustein im aktuellen Dokument? In der Kurzanleitung nur mit kurz=True und nie in „Genauer“.
        Wenn ja, kommt vorher eine noch offene Abschnittsüberschrift."""
        zeigen = not self.kurz or (kurz and not self._genauer)
        if zeigen:
            self._offene_abschnitte()
        return zeigen

    def _offene_abschnitte(self):
        self.f.extend(self._offen)
        self._offen = []

    def _marke(self, marke, nummer):
        if not marke:
            return ""
        if marke in self.neue_marken:
            raise ValueError(f"Marke [[{marke}]] doppelt vergeben")
        self.neue_marken[marke] = nummer
        return f'<a name="{marke}"/>'

    def _t(self, text):
        """[[marke]] -> „Kapitel 6.7“ als Link; im ersten Durchlauf nur Platzhalter."""
        def ersetzen(m):
            if self.marken is None:
                return "Kapitel ?"
            if m.group(1) not in self.marken:
                raise ValueError(f"Verweis auf unbekannte Marke [[{m.group(1)}]]")
            if self.kurz:      # Kurzanleitung: Verweis in die Bedienungsanleitung, ohne Link
                return f'<font color="#1F4E78">Anleitung {self.marken[m.group(1)]}</font>'
            return f'<a href="#{m.group(1)}" color="#1F4E78">Kapitel {self.marken[m.group(1)]}</a>'
        return self.VERWEIS.sub(ersetzen, str(text))

    def teil(self, buchstabe, titel, text):
        """Trennseite eines Teils: Titel, ein Satz dazu und die Kapitel mit „Wofür“ aus STECKBRIEFE (im
        1. Durchlauf noch leer: welche Kapitel dazugehören, steht erst danach fest)."""
        self._teil = buchstabe
        self.neue_teile[buchstabe] = []
        marken = self.teile.get(buchstabe, [])
        if self.kurz:                    # Kurzanleitung: nur die Überschrift des Teils, keine Trennseite
            name = f"Teil {buchstabe}" if len(buchstabe) == 1 else buchstabe
            self.f.extend([PageBreak(), Paragraph(f"{name} · {titel}", S_TEIL_KURZ)])
            return
        if self.f:
            self.f.append(PageBreak())
        self.f.append(Spacer(1, 30 * mm))
        name = f"Teil {buchstabe}" if len(buchstabe) == 1 else buchstabe
        self.f.append(Paragraph(name, S_TEIL_NR))
        kopf = Paragraph(titel, S_TEIL)
        kopf.toc_text = f"{name} · {titel}"          # so im Inhaltsverzeichnis und in der Kopfzeile
        self.f.append(kopf)
        self.f.append(HRFlowable(width="100%", thickness=1.2, color=BLAU, spaceBefore=2, spaceAfter=8))
        self.f.append(Paragraph(self._t(text), S))
        self.f.append(Spacer(1, 4 * mm))
        zeilen = []
        for m in marken:
            nr = self.marken.get(m, "?") if self.marken else "?"
            zeilen.append([Paragraph(f'<a href="#{m}" color="#1F4E78"><b>{nr}</b></a>', S_KASTEN_KOPF),
                           Paragraph(f'<a href="#{m}" color="#1F4E78"><b>{self.titel.get(m, "")}</b></a>', S_KASTEN),
                           Paragraph(self._t(STECKBRIEFE[m][0]), S_KASTEN)])
        if not zeilen:
            zeilen = [["", "", ""]]
        t = Table(zeilen, colWidths=[12 * mm, 75 * mm, BREITE - 87 * mm])
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 2),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                               ("LINEBELOW", (0, 0), (-1, -2), 0.5, LINIE), ("LINEBELOW", (0, -1), (-1, -1), 1, BLAU)]))
        self.f.append(t)
        if not self.kurz:                # Kurzanleitung: Kapitel folgen gleich auf derselben Seite
            self.f.append(PageBreak())

    def kapitel(self, titel, marke=None):
        self.kapitel_nr += 1
        self.abschnitt_nr = 0
        self._offen, self._genauer = [], False
        if self.kurz:                    # Kurzanleitung: neues Kapitel nur auf neuer Seite, wenn wenig Platz bleibt
            self.f.append(CondPageBreak(120 * mm))
        elif self.f and not isinstance(self.f[-1], PageBreak):
            self.f.append(PageBreak())
        anker = self._marke(marke, f"{self.kapitel_nr}")
        if marke:
            self.neue_titel[marke] = titel
            if self._teil:
                self.neue_teile[self._teil].append(marke)
        self.f.append(Paragraph(f'{anker}<font color="#8EA9C1">{self.kapitel_nr}</font>&nbsp;&nbsp;{titel}', S_H1))
        self.f.append(HRFlowable(width="100%", thickness=1.2, color=BLAU, spaceBefore=1, spaceAfter=7))
        if marke in STECKBRIEFE:
            self.steckbrief(*STECKBRIEFE[marke])

    def steckbrief(self, wofuer, wo):
        """Kurzer Kasten unter der Kapitelüberschrift: wofür das Kapitel ist und wo es im Programm steht."""
        t = Table([[Paragraph("Wofür", S_KASTEN_KOPF), Paragraph(self._t(wofuer), S_KASTEN),
                    Paragraph("Wo im Programm", S_KASTEN_KOPF), Paragraph(self._t(wo), S_KASTEN)]],
                  colWidths=[17 * mm, BREITE / 2 - 17 * mm - 5 * mm, 34 * mm, BREITE / 2 - 34 * mm + 5 * mm])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HELLBLAU), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        self.f.extend([t, Spacer(1, 8)])

    def abschnitt(self, titel, marke=None):
        """Abschnittsüberschrift. Im Kasten „Genauer“ als dessen Kopfzeile. In der Kurzanleitung erscheint sie erst,
        wenn danach ein Bild oder eine Bildfolge kommt."""
        self.abschnitt_nr += 1
        self._genauer = False
        anker = self._marke(marke, f"{self.kapitel_nr}.{self.abschnitt_nr}")
        teile = [CondPageBreak(45 * mm), Paragraph(f"{anker}{self.kapitel_nr}.{self.abschnitt_nr}&nbsp;&nbsp;{titel}", S_H2)]
        if self.kurz:
            self._offen = teile
        else:
            self.f.extend(teile)

    def genauer(self, titel=""):
        """Ab hier bis zum nächsten Abschnitt: Einzelheiten zum Nachlesen, kleiner gesetzt unter einer hellblauen
        Kopfzeile „Genauer“. Die Hauptsache steht davor in Bildern, Legenden und Schritten; die Kurzanleitung lässt
        „Genauer“ ganz weg."""
        self._genauer = True
        if not self.kurz:
            self.f.append(CondPageBreak(45 * mm))
            self.f.append(Paragraph("Genauer" + (f": {titel}" if titel else ""), S_GENAUER_KOPF))

    def text(self, *absaetze, kurz=False):
        if self._zeigen(kurz):
            self.f.extend(Paragraph(self._t(a), S_KLEIN if self._genauer else S) for a in absaetze)

    def liste(self, *punkte, nummeriert=False, kurz=False):
        if not self._zeigen(kurz):
            return
        for i, p in enumerate(punkte, 1):
            self.f.append(Paragraph(self._t(p), S_KLEIN_LISTE if self._genauer else S_LISTE,
                                    bulletText=f"{i}." if nummeriert else "•"))
        self.f.append(Spacer(1, 3))

    def bild(self, name, unterschrift="", hoehe=125 * mm, legende=(), kurz=True):
        self.bilder_nebeneinander([name], unterschrift, hoehe, legende, kurz)

    def bilder_nebeneinander(self, namen, unterschrift="", hoehe=125 * mm, legende=(), kurz=True):
        """Bildschirmfotos mit Unterschrift und Legende zu den roten Nummern. Stehen auch in der Kurzanleitung,
        außer mit kurz=False oder im Kasten „Genauer“."""
        self.benutzte_bilder.update(namen)
        if not self._zeigen(kurz):
            return
        if self._genauer or self.kurz:
            hoehe = min(hoehe, 95 * mm)
        pfade = [self.bilder["_ordner"] / self.bilder[n]["datei"] for n in namen]
        oben = [self.f.pop()] if self.f and isinstance(self.f[-1], Paragraph) and self.f[-1].style.name == "h2" else []
        unten = ([Paragraph(self._t(unterschrift), S_BILD)] if unterschrift else []) + ([self._legende(legende)] if legende else [])
        self.f.append(BildBlock(pfade, hoehe, oben, unten))

    def _ausschnitt(self, name, anteile):
        """Teil eines Bildschirmfotos als eigene Datei (im Bilderordner, Unterordner _ausschnitte)."""
        from PIL import Image as PILBild
        ziel = self.bilder["_ordner"] / "_ausschnitte" / f"{name}_{'_'.join(f'{a:.3f}' for a in anteile)}.png"
        if not ziel.is_file():
            ziel.parent.mkdir(exist_ok=True)
            with PILBild.open(self.bilder["_ordner"] / self.bilder[name]["datei"]) as bild:
                w, h = bild.size
                l, o, r, u = anteile
                bild.crop((round(l * w), round(o * h), round(r * w), round(u * h))).save(ziel)
        return ziel

    def schritte(self, schritte, spalten=None, hoehe=62 * mm):
        """Bildfolge Schritt 1, 2, 3 …: je Schritt ein Bild und ein kurzer Satz darüber, zwei oder drei
        nebeneinander. schritte = [(bild oder None, text), …] oder (bild, text, ausschnitt) mit ausschnitt =
        (links, oben, rechts, unten) als Anteil 0…1 des Bildes, damit im kleinen Bild das Wichtige groß genug ist.
        Steht immer auch in der Kurzanleitung."""
        self.benutzte_bilder.update(s[0] for s in schritte if s[0])
        if self.kurz and self._genauer:
            return
        self._offene_abschnitte()
        from reportlab.platypus import Image
        spalten = spalten or (3 if len(schritte) in (3, 5, 6, 9) else 2)
        abstand = 6 * mm
        breite = (BREITE - abstand * (spalten - 1)) / spalten
        zellen = []
        for nr, (name, text, *ausschnitt) in enumerate(schritte, 1):
            kopf = Table([[Nummer(nr, 6 * mm), Paragraph(self._t(text), S_SCHRITT)]], colWidths=[8 * mm, breite - 8 * mm])
            kopf.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                      ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                      ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
            inhalt = [kopf]
            if name:
                pfad = self._ausschnitt(name, ausschnitt[0]) if ausschnitt else self.bilder["_ordner"] / self.bilder[name]["datei"]
                from reportlab.lib.utils import ImageReader
                w, h = ImageReader(str(pfad)).getSize()
                s = min(breite / w, hoehe / h)
                bild = Image(str(pfad), w * s, h * s)
                rahmen = Table([[bild]], colWidths=[w * s])
                rahmen.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, LINIE), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                            ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
                rahmen.hAlign = "LEFT"
                inhalt.append(rahmen)
            zellen.append(inhalt)
        zeilen = [zellen[k:k + spalten] for k in range(0, len(zellen), spalten)]
        zeilen[-1] += [""] * (spalten - len(zeilen[-1]))
        breiten = []
        for k in range(spalten):
            breiten += [breite] + ([abstand] if k < spalten - 1 else [])
        daten = [sum(([z] + ([""] if k < spalten - 1 else []) for k, z in enumerate(zeile)), []) for zeile in zeilen]
        t = Table(daten, colWidths=breiten)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 2),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
        oben = [self.f.pop()] if self.f and isinstance(self.f[-1], Paragraph) and self.f[-1].style.name == "h2" else []
        self.f.append(KeepTogether(oben + [t]) if oben else t)
        self.f.append(Spacer(1, 4))

    def _legende(self, punkte):
        zeilen = [[Nummer(nr), Paragraph(self._t(text), S_LEGENDE)] for nr, text in punkte]
        halb = (len(zeilen) + 1) // 2
        if len(zeilen) > 3:   # zweispaltig
            links, rechts = zeilen[:halb], zeilen[halb:] + [["", ""]] * (2 * halb - len(zeilen))
            daten = [l + r for l, r in zip(links, rechts)]
            breiten = [8 * mm, BREITE / 2 - 10 * mm, 8 * mm, BREITE / 2 - 6 * mm]
        else:
            daten, breiten = zeilen, [8 * mm, BREITE - 8 * mm]
        t = Table(daten, colWidths=breiten)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
        return t

    def hinweis(self, text, titel="Hinweis", kurz=False):
        if not self._zeigen(kurz):
            return
        t = Table([[Paragraph(self._t(f"<b>{titel}:</b> {text}"), S_TIPP)]], colWidths=[BREITE])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HELLBLAU),
                               ("LINEBEFORE", (0, 0), (0, -1), 3, BLAU),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        self.f.extend([Spacer(1, 3), t, Spacer(1, 6)])

    def tabelle(self, kopf, zeilen, breiten, kurz=False):
        """Tabelle wie im Angebots-PDF: ohne Gitter, blaue Linie unter dem Kopf und am Ende, dazwischen fein grau."""
        if not self._zeigen(kurz):
            return
        daten = [[Paragraph(f'<font color="#1F4E78"><b>{k}</b></font>', S_LEGENDE) for k in kopf]]
        daten += [[Paragraph(self._t(z), S_LEGENDE) for z in zeile] for zeile in zeilen]
        t = Table(daten, colWidths=[b * mm for b in breiten], repeatRows=1)
        t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 1, BLAU),
                               ("LINEBELOW", (0, 1), (-1, -2), 0.5, LINIE),
                               ("LINEBELOW", (0, -1), (-1, -1), 1, BLAU),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
                               ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]))
        self.f.extend([t, Spacer(1, 6)])


# ---------------------------------------------------------------- Inhalt der Anleitung
def titelseite(inh, stand):
    """Titelseite: Name, Version und Stand stehen im blauen Band (Anleitung._titelband), darunter das Stangenbild
    und die drei Teile der Anleitung; danach das Inhaltsverzeichnis."""
    f = inh.f
    inh.bild("erg_stangenbild", hoehe=64 * mm)
    zellen = [Paragraph(f'<font color="#8EA9C1"><b>{"TEIL " + b if len(b) == 1 else b.upper()}</b></font><br/>'
                        f'<font color="#1F4E78"><b>{titel}</b></font><br/>{text}', S_KASTEN)
              for b, titel, text, _ in (TEILE[:2] if inh.kurz else TEILE)]
    t = Table([zellen], colWidths=[BREITE / len(zellen)] * len(zellen))
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 10), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("LINEABOVE", (0, 0), (-1, 0), 1, BLAU)]))
    f.append(t)
    f.append(Spacer(1, 3 * mm))
    f.append(Paragraph("Alle Bildschirmfotos stammen aus dem Programm selbst. Firmen, Kunden, Angebote und Preise sind "
                       "Beispielwerte. " + (
                           "Die Kurzanleitung zeigt den täglichen Ablauf und das Einrichten in Bildern. Einzelheiten "
                           "stehen in der Bedienungsanleitung (<i>Hilfe → Bedienungsanleitung</i>, F1); "
                           "„Anleitung 6.3“ verweist dorthin, gleiche Kapitelnummern." if inh.kurz else
                           "Blaue Kapitelverweise sind im PDF anklickbar. Eine bebilderte Kurzfassung von Teil A bis C "
                           "ist die <b>Kurzanleitung</b> (<i>Hilfe → Kurzanleitung (PDF)</i>)."),
                       ParagraphStyle("klein", parent=S, fontSize=8.5, textColor=GRAU)))
    from reportlab.platypus.doctemplate import NextPageTemplate
    f.append(NextPageTemplate("normal"))
    f.append(PageBreak())
    f.append(Paragraph("Inhalt", ParagraphStyle("inhalt", parent=S_H1)))
    f.append(HRFlowable(width="100%", thickness=1.2, color=BLAU, spaceBefore=1, spaceAfter=4))
    toc = TableOfContents()
    toc.levelStyles = [S_TOC0, S_TOC1, S_TOC2]
    toc.dotsMinLevel = 99          # keine Punktreihen: die Seitenzahl steht rechtsbündig
    f.append(toc)


def kapitel_ueberblick(i):
    i.kapitel("Überblick", marke="ueberblick")
    i.text("Das Programm plant, wie die Teile eines Angebots aus Stangen geschnitten werden, und rechnet daraus "
           "Material, Laserzeit und Preis. Ein Angebot entsteht immer in derselben Reihenfolge:", kurz=True)
    i.schritte([
        ("angebote", "<b>Angebot anlegen</b> ([[angebote]])", (0, 0, 0.42, 0.28)),
        ("step_pruefen", "<b>Positionen</b> per STEP-Import oder von Hand ([[step]], [[angebot]])", (0, 0, 0.6, 0.55)),
        ("angebot_optimiert", "<b>Optimieren</b> (F9): Teile auf Stangen, Preis ([[optimieren]])", (0.79, 0.03, 1, 0.62)),
        ("erg_stangenbild", "<b>Ergebnis prüfen</b>: Schnittplan, Stangenbild ([[kalkulation]])", (0, 0, 0.5, 0.62)),
        ("staffeln", "Bei Bedarf <b>Staffeln, Fracht, Zukaufteile</b> ([[staffeln]], [[fracht]])", (0, 0, 0.8, 0.75)),
        ("pdf_angebot_1", "<b>Angebot (PDF)</b> an den Kunden ([[ausgabe]])")], hoehe=58 * mm)
    i.genauer("Aufbau dieser Anleitung")
    i.text("<b>Teil A</b> richtet das Programm ein und führt einmal durch ein ganzes Angebot ([[schnellstart]]). "
           "<b>Teil B</b> ([[angebote]] bis [[nachkalkulation]]) folgt dem Ablauf eines Angebots. <b>Teil C</b> "
           "([[einstellungen]] bis [[pflege]]) beschreibt, was einmal eingerichtet und gepflegt wird: die Stammdaten "
           "(Profile, Werkstoffe, Oberflächen, Preise, Lieferlängen, Maschinen, Schneiddaten, Gewinde, Zusatzarbeiten) "
           "und die Einstellungen. Das Programm startet mit Beispielwerten, die durch die eigenen ersetzt werden. Im "
           "<b>Anhang</b>: STEP-Messung ([[step_messung]]), Tastenkürzel ([[tastenkuerzel]]), häufige Fragen "
           "([[fragen]]) und Neuerungen ([[neu]]).",
           "Jedes Kapitel beginnt mit dem Kasten <i>Wofür / Wo im Programm</i>. Danach kommt das Wichtigste in "
           "Bildern: rote Nummern im Bild, darunter die Erklärung. Einzelheiten stehen kleiner gesetzt unter "
           "<i>Genauer</i>. Die <b>Kurzanleitung</b> (<i>Hilfe → Kurzanleitung (PDF)</i>) enthält nur die Bilder von "
           "Teil A bis C.")
    i.abschnitt("Aufbau des Fensters")
    i.bild("angebot_optimiert", "Hauptfenster mit geöffnetem Angebot nach dem Optimieren", hoehe=112 * mm, legende=[
        (1, "Stand des Angebots: grün <i>Optimierung abgeschlossen</i>, gelb <i>Noch nicht optimiert</i>, rot "
            "<i>Veraltet</i> ([[veraltet]]).")])
    i.text("Oben die Reiter <i>Start</i>, <i>Angebote</i>, <i>Kunden</i>, <i>Frachtkosten</i> ([[frachtkosten]]), "
           "<i>Zukaufartikel</i> ([[zukauf]]) und <i>Einstellungen</i> (mit Passwort). Geöffnete Angebote stehen "
           "in einer eigenen Zeile unter <i>Angebote</i>: ganz links die <i>Angebotsliste</i>, daneben je Angebot ein "
           "Reiter, der sich mit dem × schließt. Die Zeile erscheint, solange <i>Angebote</i> gewählt ist; ein Klick "
           "auf <i>Angebote</i> führt zum zuletzt gezeigten Angebot zurück. Die Statuszeile unten meldet, was gespeichert oder "
           "gerechnet wurde, Fehler in Rot.", kurz=True)
    i.genauer()
    i.text("Das Programm öffnet sich maximiert im Reiter <i>Angebote</i>. Die Einstellungen enthalten die Vorgaben "
           "und die übrigen Stammdaten als Seiten in der Navigation links. Zahlen mit Komma eingeben (1385,5). Jede Änderung wird sofort "
           "gespeichert, einen Speichern-Knopf gibt es nicht. Strg+C/Strg+V kopieren und fügen Zellen ein (auch Blöcke "
           "aus Excel), Entf löscht markierte Zeilen nach Rückfrage, Strg+Z nimmt im Angebot die letzte Änderung "
           "zurück ([[tastenkuerzel]]).")
    i.abschnitt("Farben in den Tabellen")
    i.tabelle(["Farbe", "Bedeutung"], [
        ["hellgelb", "<b>Eingabefeld</b>: lostippen, F2 oder Doppelklick ([[doppelklick]])."],
        ["hellgrau", "<b>Berechnet</b>, nicht änderbar."],
        ["grau <b>OK</b>", "Zeile vollständig und stimmig (bewusst unauffällig)."],
        ["gelb <b>WARNUNG / HINWEIS</b>", "Wird gerechnet, sollte aber geprüft werden."],
        ["rot <b>FEHLER</b>", "Wird nicht gerechnet, der Text sagt, was fehlt. <b>Doppelklick auf den Status</b> "
                              "führt zur Lösung."]], [60, 205], kurz=True)


def kapitel_start(i):
    i.kapitel("Installation und erster Start", marke="start")
    i.abschnitt("Installieren oder portabel")
    i.text("Zwei Formen, gleiche Programmdateien, gleiches Online-Update. Unterschied: wo die Daten liegen.")
    i.tabelle(["", "Installation (empfohlen)", "Portable Version (ZIP)"], [
        ["Datei im Release <i>aktuell</i>", "Rohrlaser-Angebotskalkulation-Setup.exe", "Rohrlaser-Angebotskalkulation.zip"],
        ["Gedacht für", "den Arbeitsplatz, an dem dauerhaft kalkuliert wird",
         "Tests, einen Rechner ohne Erlaubnis für Setup-Programme, Mitnahme auf einem USB-Stick"],
        ["Programm", "%LOCALAPPDATA%\\Programs\\Rohrlaser Angebotskalkulation", "beliebiger Ordner, z. B. C:\\Rohrlaser"],
        ["Daten", "%LOCALAPPDATA%\\Rohrlaser Angebotskalkulation\\Daten", "Ordner <i>Daten</i> neben dem Programm"],
        ["PDF und CSV", "Dokumente\\Rohrlaser Angebote", "Ordner <i>Angebote</i> neben dem Programm"],
        ["Startmenü, Desktop", "ja", "Verknüpfung selbst anlegen"],
        ["Entfernen", "Einstellungen → Apps; die Daten bleiben", "Ordner löschen; <b>die Daten sind dann mit weg</b>"]],
        [40, 112, 112])
    i.genauer()
    i.text("Administratorrechte braucht keine der beiden Formen. Die Daten der installierten Version liegen bewusst "
           "nicht unter <i>Dokumente</i>: diesen Ordner gleicht OneDrive oft ab, und eine geöffnete Datendatei verträgt "
           "das schlecht. Für eine Kopie auf OneDrive oder ein Netzlaufwerk ist der <b>zweite Sicherungsordner</b> da "
           "([[datensicherung]]).")
    i.abschnitt("Programm installieren")
    i.liste("Auf GitHub unter <b>Releases → aktuell</b> die Datei <b>Rohrlaser-Angebotskalkulation-Setup.exe</b> "
            "herunterladen.",
            "Beim ersten Mal: rechte Maustaste auf die Datei → <i>Eigenschaften</i> → unten <i>Zulassen</i> anhaken → "
            "OK ([[windows_warnungen]]). Dann das Setup starten.",
            "Warnt Windows trotzdem, siehe [[windows_warnungen]]. Das Setup fragt nach der Desktop-Verknüpfung "
            "und installiert nur für den angemeldeten Benutzer.",
            "Das Programm aus dem Startmenü starten (<i>Rohrlaser Angebotskalkulation</i>; daneben liegt die "
            "Bedienungsanleitung).",
            "Eine neue Version des Setups lässt sich jederzeit über die alte installieren; die Daten bleiben. Meist "
            "reicht aber das Online-Update ([[updates]]).", nummeriert=True)
    i.genauer()
    i.text("Deinstallieren: <i>Einstellungen → Apps → Rohrlaser Angebotskalkulation → Deinstallieren</i>. Entfernt "
           "werden nur die Programmdateien. Datendatei, Sicherungen und PDF bleiben, eine spätere Installation findet "
           "sie wieder.")
    i.abschnitt("Portable Version entpacken")
    i.liste("Unter <b>Releases → aktuell</b> die Datei <b>Rohrlaser-Angebotskalkulation.zip</b> herunterladen.",
            "<b>Vor dem Entpacken</b>: rechte Maustaste auf das ZIP → <i>Eigenschaften</i> → unten <i>Zulassen</i> "
            "anhaken → OK ([[windows_warnungen]]).",
            "In einen Ordner entpacken, in dem man schreiben darf, z. B. <i>C:\\Rohrlaser</i>. Nicht nach "
            "<i>C:\\Programme</i>, dort darf das Programm seine Daten nicht ablegen.",
            "<b>Rohrlaser-Angebotskalkulation.exe</b> starten. Wer will, legt sich eine Verknüpfung auf den Desktop "
            "(rechte Maustaste → Senden an → Desktop).", nummeriert=True)
    i.genauer("Programmordner")
    i.text("Der Programmordner der portablen Version sieht danach so aus (die installierte Version hat dieselben "
           "Programmdateien, aber keine <i>Portabel.ini</i>, keinen Ordner <i>Daten</i> und keinen Ordner "
           "<i>Angebote</i>):")
    i.tabelle(["Datei / Ordner", "Inhalt"], [
        ["Rohrlaser-Angebotskalkulation.exe", "das Programm"],
        ["Bedienungsanleitung.pdf", "diese Anleitung (auch über <i>Hilfe → Bedienungsanleitung</i> oder F1)"],
        ["Kurzanleitung.pdf", "der tägliche Ablauf in Bildern (auch über <i>Hilfe → Kurzanleitung (PDF)</i>)"],
        ["Windows-Vertrauen-einrichten.cmd", "gibt Programmdateien frei und trägt das Signatur-Zertifikat ein "
                                             "([[windows_vertrauen]])"],
        ["Portabel.ini", "macht das Programm portabel: Daten im Ordner daneben. Darin lässt sich auch ein anderer "
                         "Datenordner eintragen (Zeile <i>daten = …</i>). Nicht löschen, sonst sucht das Programm "
                         "die Daten im Benutzerprofil."],
        ["STEP-Import\\", "Messprogramm für STEP-Dateien. Muss neben der .exe liegen bleiben."],
        ["_internal\\", "Programmbibliotheken, nicht verändern"],
        ["Daten\\rohrlaser.db", "Datendatei: Stammdaten, Einstellungen, alle Angebote. Wird beim ersten Start "
                                "angelegt."],
        ["Daten\\Sicherung\\", "automatische Sicherungen der Datendatei ([[datensicherung]])"],
        ["Angebote\\", "Ablage für PDF und CSV-Export (wenn in den Einstellungen nichts anderes steht)"],
        ["Update.json", "Liste der Programmdateien des installierten Stands (für das Update, Abschnitt "
                        "<i>Updates</i>)"]],
        [60, 205])
    i.text("Eine ältere portable Version ohne <i>Portabel.ini</i> erkennt das Programm am Ordner <i>Daten</i> neben "
           "der .exe und arbeitet dort weiter wie bisher.")
    i.abschnitt("Windows-Warnungen (SmartScreen, Defender)", marke="windows_warnungen")
    i.text("<b>Ohne Adminrechte:</b> die heruntergeladene Datei <b>vor</b> dem Entpacken bzw. Starten freigeben.")
    i.liste("Im Explorer (meist <i>Downloads</i>) rechte Maustaste auf <i>Rohrlaser-Angebotskalkulation.zip</i> bzw. "
            "<i>Rohrlaser-Angebotskalkulation-Setup.exe</i> → <i>Eigenschaften</i>.",
            "Reiter <i>Allgemein</i>, unten bei <i>Sicherheit</i>: <b>Zulassen</b> anhaken → <i>OK</i>. Fehlt das "
            "Kästchen, ist die Datei schon frei.",
            "Erst jetzt entpacken bzw. das Setup starten.", nummeriert=True)
    i.genauer("Warum Windows warnt")
    i.text("Windows merkt sich bei jeder heruntergeladenen Datei, dass sie „aus dem Internet“ stammt. Beim Entpacken "
           "eines ZIP bekommt jede der rund 800 Programmdateien diese Markierung, und der Microsoft Defender prüft dann "
           "jede einzeln besonders gründlich; ein Setup mit der Markierung meldet beim Start „Der Computer wurde durch "
           "Windows geschützt“. Das Programm braucht keine Administratorrechte, geht nur für die Suche nach Updates ins "
           "Internet ([[updates]]) und schreibt nur in seinen Programm- und Datenordner und in die eingestellten "
           "Ablage- und Sicherungsordner. Updates aus dem Programm haben die Markierung nicht, die Warnungen betreffen "
           "also nur das erste Herunterladen.")
    i.text("Nach <i>Zulassen</i> haben die entpackten Dateien keine Markierung, Windows warnt nicht und der Defender "
           "prüft wie bei jeder anderen Datei.")
    i.abschnitt("Windows-Vertrauen einrichten (Signatur)", marke="windows_vertrauen")
    i.text("Einmal je PC und Benutzer, ohne Adminrechte: <b>Windows-Vertrauen-einrichten.cmd</b> trägt das "
           "Signatur-Zertifikat ein und gibt die Dateien frei.")
    i.genauer()
    i.text("Programm, STEP-Import, Setup und Deinstallationsprogramm sind mit dem eigenen, kostenlosen Zertifikat "
           "<b>Patrick Brundiers</b> digital signiert (rechte Maustaste → <i>Eigenschaften → Digitale Signaturen</i>). "
           "Ein solches Zertifikat kennt Windows nicht von sich aus. Die Datei <b>Windows-Vertrauen-einrichten.cmd</b> "
           "trägt es für den angemeldeten Benutzer ein und gibt gleich die Dateien frei. Sie braucht <b>keine "
           "Administratorrechte</b> und ist einmal je PC und Benutzer nötig.")
    i.liste("Unter <b>Releases → aktuell</b> <i>Windows-Vertrauen-einrichten.cmd</i> in denselben Ordner laden wie "
            "Setup bzw. ZIP (z. B. <i>Downloads</i>).",
            "Doppelklick auf die Datei. Fragt Windows „Möchten Sie diese Datei ausführen?“ oder zeigt „Der Computer "
            "wurde durch Windows geschützt“: <i>Ausführen</i> bzw. <i>Weitere Informationen → Trotzdem ausführen</i>.",
            "Die Datei gibt Setup und ZIP im selben Ordner frei (wie <i>Zulassen</i> oben). Windows fragt einmal "
            "„Möchten Sie dieses Zertifikat installieren?“ für <i>Patrick Brundiers</i>: mit <b>Ja</b> bestätigen.",
            "Mit der Eingabetaste schließen, dann Setup starten bzw. ZIP entpacken.", nummeriert=True)
    i.text("Dieselbe Datei liegt auch im Programmordner. Dort gestartet gibt sie alle Programmdateien frei, z. B. "
           "wenn ein ZIP ohne <i>Zulassen</i> entpackt wurde. Rückgängig machen: in der Eingabeaufforderung "
           "<i>Windows-Vertrauen-einrichten.cmd entfernen</i> eingeben; das Zertifikat wird wieder ausgetragen.")
    i.text("Ganz ohne Warnung auf jedem fremden PC ginge es nur mit einem gekauften Zertifikat einer anerkannten "
           "Stelle. Das kostenlose Programm SignPath für Open Source scheidet aus, weil dafür der Quellcode öffentlich "
           "sein müsste.")
    i.abschnitt("Wenn der Defender trotzdem anschlägt")
    i.genauer()
    i.liste("Meldet Windows beim ersten Start „Der Computer wurde durch Windows geschützt“: auf <i>Weitere "
            "Informationen</i> und dann <i>Trotzdem ausführen</i> klicken. Danach fragt Windows nicht mehr.",
            "Hat der Microsoft Defender eine Datei in Quarantäne verschoben: <i>Windows-Sicherheit → Viren- &amp; "
            "Bedrohungsschutz → Schutzverlauf</i>, den Eintrag öffnen, <i>Aktionen → Wiederherstellen</i> bzw. "
            "<i>Auf Gerät zulassen</i>. Den Fehlalarm bitte an Microsoft melden "
            "(www.microsoft.com/wdsi/filesubmission, Datei hochladen, „Incorrectly detected as malware“); "
            "nach der Prüfung nimmt Microsoft die Erkennung meist innerhalb weniger Tage zurück.",
            "Ob ZIP oder Setup unverändert von GitHub kommen, zeigt die Prüfsumme: im Release liegen "
            "<i>Rohrlaser-Angebotskalkulation.zip.sha256</i> und <i>Rohrlaser-Angebotskalkulation-Setup.exe.sha256</i>. "
            "In PowerShell <i>Get-FileHash</i> mit dem Dateinamen eingeben; die Zahl muss gleich sein.",
            "Wer Adminrechte hat, kann zusätzlich den Programmordner unter <i>Viren- &amp; Bedrohungsschutz → "
            "Einstellungen verwalten → Ausschlüsse</i> eintragen. Dann prüft der Defender die Programmdateien nicht "
            "bei jedem Start, Programm und STEP-Import starten schneller. Nur diesen Ordner ausschließen, niemals "
            "<i>Downloads</i> oder ganze Laufwerke; in Firmen entscheidet das die IT. Nötig ist das nicht.",
            nummeriert=True)
    i.abschnitt("Startseite")
    i.bild("start_beispiel", "Startseite nach dem ersten Start (Beispiel-Stammdaten)", hoehe=112 * mm, legende=[
        (1, "<b>Datensicherung erstellen</b>: geprüfte Kopie der Datendatei in den Ordner <i>Sicherung</i> und, "
            "falls eingestellt, in den zweiten Sicherungsordner."),
        (2, "<b>Sicherung wiederherstellen …</b>: einen früheren Stand zurückholen ([[datensicherung]])."),
        (3, "<b>Datenordner öffnen</b>: zeigt den Ordner mit der Datendatei im Explorer.")])
    i.text("Vier Karten: <b>Angebote</b> (<b>Neues Angebot</b>, <b>Aus STEP …</b> "
           "([[angebot_aus_step]]), <b>Alle Angebote</b>, die zuletzt bearbeiteten; "
           "Doppelklick öffnet), <b>Heute</b> (eigene Angebote je Vorgang, Wiedervorlage), <b>Stammdaten</b> (Stand, "
           "Hinweis auf Beispielwerte, aufklappbar die Anzahl je Tabelle, <b>Einstellungen öffnen</b>) "
           "und <b>Daten und Sicherung</b>.", kurz=True)
    i.liste("<b>Heute, Eigene Angebote</b>: Anzahl und Verkaufspreis netto der eigenen Angebote je Vorgang (Entwurf, "
            "Verschickt, Beauftragt, Abgelehnt), dieselben Summen wie in der Angebotsliste. Ein Klick auf den Vorgang "
            "öffnet die Angebotsliste mit diesem Filter ([[angebote]]).",
            "<b>Wiedervorlage</b>: eigene Angebote zum Nachfassen, mit Grund: verschickt und seit einigen Tagen ohne "
            "Antwort, Gültigkeit ([[vorgaben]], <i>Gültigkeit</i>) endet in den nächsten 7 Tagen oder ist vorbei, "
            "oder eine Wiedervorlage von Hand ist erreicht; überfällige rot. Doppelklick bzw. <b>Öffnen</b> öffnet "
            "das Angebot, <b>Nachfassen vermerken …</b> und <b>Wiedervorlage …</b> gelten für das markierte "
            "([[nachfassen]]).",
            "<b>Letzte 90 Tage</b> (nur mit Admin-Lizenz): Zahl und Summe der Angebote, Durchschnittswert, beauftragte "
            "Angebote mit Auftragswert und die Trefferquote (beauftragt geteilt durch beauftragt + abgelehnt).")
    i.abschnitt("Suchen und ausführen (Strg+K)", marke="befehlspalette")
    i.text("<b>Strg+K</b> oder <i>Ansicht → Suchen und ausführen …</i> öffnet von überall ein Suchfeld für "
           "Angebote (Nummer, Kunde), Kunden, Profile, Werkstoffe, Einstellungen, Reiter und alle Menübefehle mit "
           "ihrem Tastenkürzel. Tippen filtert (alle Wörter müssen vorkommen, z. B. „40x3 re“), <b>↑/↓</b> wählt, "
           "<b>Enter</b> öffnet das Angebot, zeigt Kunde oder Profil, springt zur Einstellung (Einstellungen mit "
           "gefilterter Suche) oder führt den Befehl aus; <b>Esc</b> schließt.", kurz=True)
    i.genauer("Erster Start")
    i.text("Beim ersten Start fragt das Programm, ob vorhandene Daten übernommen werden sollen (z. B. aus einer "
           "portablen Version oder einer Export-Datei, [[datensicherung]]): <b>Daten übernehmen …</b> wählt die Quelle, "
           "<b>Mit Beispieldaten beginnen</b> legt die Datendatei mit Beispiel-Stammdaten an. Danach fragt es nach "
           "<b>Name und Kürzel</b> des Benutzers; das Kürzel zeigt, wer ein Angebot bearbeitet. Arbeiten "
           "mehrere Mitarbeiter mit dem Programm, kommt hier auch der gemeinsame Ordner hinein "
           "([[mehrere_arbeitsplaetze]]).",
           "Die Karte Angebote zeigt die zuletzt bearbeiteten Angebote mit Status und Verkaufspreis; die Karte Daten "
           "und Sicherung zeigt die Datendatei und dahinter, ob das Programm installiert oder portabel läuft. Die "
           "Beispielwerte in den Stammdaten ([[stammdaten]]) und den Vorgaben ([[vorgaben]]) durch die eigenen "
           "ersetzen: Preise, Maschinen, Schneiddaten, Briefkopf und Zuschläge.")


def kapitel_angebote(i):
    i.kapitel("Angebote verwalten", marke="angebote")
    i.bild("angebote", "Reiter Angebote: Doppelklick öffnet ein Angebot in einem eigenen Reiter", hoehe=112 * mm, legende=[
        (1, "Reiter <b>Angebote</b>: alle Angebote, die neuesten oben."),
        (2, "<b>Neues Angebot</b>: nächste Nummer, heutiges Datum, Standard-Maschine und -Stangenlänge."),
        (3, "<b>Kopieren</b>: Kopie mit neuer Nummer, z. B. für eine Nachbestellung oder einen anderen Kunden. "
            "Daneben <b>Öffnen</b> und <b>Löschen</b>."),
        (4, "<b>Suchen</b> nach Nummer, Kunde, Kundennummer, Bemerkung, Artikelnummer oder Bezeichnung.")])
    i.tabelle(["Spalte", "Farben und Werte"], [
        ["Status", "<i>Nicht optimiert</i> gelb · <i>Optimiert</i> grün · <i>Veraltet</i> rot (neu optimieren) · "
                   "<i>Nachkalkuliert</i> blau"],
        ["Vorgang", "<i>Entwurf</i> · <i>Verschickt</i> blau (setzt das Angebots-PDF) · <i>Beauftragt</i> grün · "
                    "<i>Abgelehnt</i> grau · „Verschickt (abgelaufen)“ rot"]], [30, 235], kurz=True)
    i.text("Die Spalten <b>Bearbeiter</b> und <b>Nachkalkuliert</b> erscheinen nur, wenn mindestens ein Angebot dort "
           "einen Eintrag hat.", kurz=True)
    i.genauer()
    i.text("<b>Verkaufspreis netto</b> ist der Preis aus der Übersicht des Angebots; das Programm merkt ihn sich beim "
           "Anzeigen eines Angebots (Mauszeiger darauf: <i>Stand vom …</i>). Ältere Angebote, die seit dem Update noch "
           "nicht geöffnet wurden, haben dort noch keinen Wert.",
           "<b>Vorgang ▾</b> setzt den Vorgang des markierten Angebots von Hand; vor <i>Verschickt</i> öffnet sich "
           "das Angebot mit dem Angebots-Check, wenn noch etwas offen ist ([[angebots_check]]). <b>Gültig bis</b> ist das "
           "Angebotsdatum plus die Gültigkeit aus den Einstellungen (Angebots-PDF). Die Auswahl links neben der Suche "
           "zeigt nur Angebote eines Vorgangs, z. B. <i>Offen (Entwurf, Verschickt)</i>, <i>Verschickt und "
           "abgelaufen</i> oder <i>Wiedervorlage fällig</i> zum Nachfassen ([[nachfassen]]), <i>Nachkalkulation offen</i> zeigt beauftragte Angebote ohne Ist-Werte "
           "([[nachkalkulation]]). Ältere Angebote mit Angebots-PDF stehen nach dem Update auf Verschickt. "
           "Gelöschte Angebote enthält die tägliche Sicherung weiter.",
           "Die Spalte <b>Bearbeiter</b> zeigt das Kürzel des Mitarbeiters, der ein Angebot angelegt hat. Mit "
           "gemeinsamem Ordner stehen auch die Angebote der Kollegen in der Liste, <b>grau und kursiv</b>; die Auswahl "
           "<b>Meine Angebote / Alle Mitarbeiter / Kürzel</b> filtert danach, <b>Abgleichen</b> holt den neuesten "
           "Stand ([[mehrere_arbeitsplaetze]]). Ein Angebot eines Kollegen lässt sich öffnen, ansehen und als PDF "
           "ausgeben, aber nicht ändern, löschen oder auf einen anderen Vorgang setzen; <b>Kopieren</b> macht daraus "
           "ein eigenes Angebot mit eigener Nummer.")
    i.bild("kopieren_dialog", "Angebot kopieren: Kunde der Kopie wählen", hoehe=40 * mm)
    i.text("Beim Kopieren ist der bisherige Kunde vorgeschlagen. Ein anderer Kunde bringt Name und "
           "Zahlungsbedingungen aus dem Kundenstamm mit; Positionen und Staffeln werden mitkopiert.",
           "Tastatur: <b>Eingabe</b> öffnet das markierte Angebot, <b>Strg+N</b> legt ein neues an, <b>Entf</b> löscht "
           "nach Rückfrage, <b>Strg+F</b> springt ins Suchfeld, <b>Esc</b> leert es. <b>Strg+Tab</b> wechselt zwischen "
           "offenen Angeboten, <b>Strg+W</b> schließt das aktuelle ([[tastenkuerzel]]).")
    i.abschnitt("Nachfassen und Wiedervorlage", marke="nachfassen")
    i.text("Verschickte Angebote ohne Antwort kommen nach einigen Tagen (Einstellung <i>Nachfassen: Wiedervorlage "
           "nach Tagen</i>, Vorgabe 10) von selbst auf die Startseite unter <b>Wiedervorlage</b> und in den Filter "
           "<i>Wiedervorlage fällig</i>. Nach dem Anruf oder der E-Mail an den Kunden <b>Nachfassen vermerken …</b>.",
           kurz=True)
    i.liste("<b>Nachfassen vermerken …</b> (Angebotsliste <i>Vorgang ▾</i>, Startseite, im Angebot <i>Ausgaben</i>): "
            "heute nachgefasst, per Telefon, E-Mail oder persönlich. Das steht mit Datum im Versandverlauf "
            "(Mauszeiger auf <i>Preise festgeschrieben</i> in der Übersicht), und die Tage zählen ab dann neu. "
            "Die E-Mail selbst schreibt man wie bisher im Mailprogramm.",
            "<b>Wiedervorlage …</b>: ein eigenes Datum, auch für einen Entwurf (z. B. „Kunde meldet sich Mitte "
            "November“). Bis dahin ruht das automatische Nachfassen; am Tag steht das Angebot in der Wiedervorlage. "
            "<b>Keine Wiedervorlage</b> nimmt das Datum wieder weg.",
            "Mit Beauftragt oder Abgelehnt fällt ein Angebot aus der Wiedervorlage. Angebote der Kollegen erscheinen "
            "dort nicht; vermerken kann nur, wer das Angebot angelegt hat.")
    i.genauer()
    i.text("<i>Nachfassen: Wiedervorlage nach Tagen</i> = 0 schaltet das automatische Nachfassen ab; Gültigkeit und "
           "Wiedervorlagen von Hand bleiben.")
    i.abschnitt("Neue Fassung", marke="neue_fassung")
    i.text("Fragt der Kunde ein Angebot noch einmal an (geänderte Mengen, neuer Termin), legen Sie statt einer Kopie "
           "eine <b>neue Fassung</b> an: <i>Datei → Neue Fassung des Angebots</i> (für das offene oder das in der "
           "Liste markierte Angebot) oder im Dialog <b>Kopieren</b> der Haken <i>Neue Fassung … statt Kopie</i>.",
           kurz=True)
    i.genauer()
    i.text("Die neue Fassung behält die Nummer mit dem Zusatz <b>-2</b>, <b>-3</b> … (aus A-2026-0123 wird "
           "A-2026-0123-2, aus der -2 die -3), den Kunden, die Positionen und die Staffeln. Sie bekommt das heutige "
           "Datum, den Vorgang Entwurf und rechnet mit den aktuellen Preisen und Stundensätzen; festgeschrieben ist "
           "noch nichts ([[preise_festschreiben]]). Der Zähler der Angebotsnummern zählt dabei nicht weiter.",
           "Die bisherige Fassung steht danach in der Angebotsliste auf <b>Ersetzt durch …</b> (grau). Sie zählt auf "
           "der Startseite in keinem Vorgang, erscheint nicht in der Wiedervorlage und nicht unter <i>Offen</i>; der "
           "Filter <i>Ersetzt (alte Fassungen)</i> zeigt alle alten Fassungen. Ihr Reiter schließt sich, öffnen und "
           "ansehen lässt sie sich weiter. Angebote der Kollegen bekommen keine Fassung, dort hilft <b>Kopieren</b>.")
    i.abschnitt("Neues Angebot aus STEP", marke="angebot_aus_step")
    i.text("STEP-Dateien oder einen Ordner auf die Angebotsliste oder die Startseite ziehen, oder <i>Datei → Neues "
           "Angebot aus STEP …</i> (Startseite: <b>Aus STEP …</b>): Kunde bestätigen, das Programm legt das Angebot an und "
           "startet gleich den STEP-Import.", kurz=True)
    i.genauer()
    i.text("Den Kunden schlägt das Programm aus dem Ordnernamen vor: Steht der Kundenname (ab 3 Zeichen) oder die "
           "Kundennummer im Ordner der Dateien oder bis zu drei Ordnern darüber, z. B. <i>Anfragen\\Müller GmbH\\"
           "2026-10</i>, ist dieser Kunde gewählt. Sonst steht der Kunde des zuletzt geänderten eigenen Angebots mit "
           "Importprofil ([[importprofile]]) vorne; <i>(ohne Kunde)</i> geht auch. Das neue Angebot bekommt die "
           "Kundenvorgaben ([[kundenvorgaben]]) und öffnet sich; danach läuft der Import wie mit <b>STEP "
           "importieren</b> mit allen STEP-Dateien des Ordners samt Unterordnern ([[step]]). Andere Dateien (z. B. "
           "PDF) bleiben unbeachtet; sind keine STEP-Dateien dabei, legt das Programm kein Angebot an.")


def kapitel_angebot(i):
    i.kapitel("Angebot anlegen und bearbeiten", marke="angebot")
    i.bild("angebot_positionen", "Angebot A-2026-0041 vor dem Optimieren", hoehe=105 * mm, legende=[
        (1, "<b>Angebotskopf</b> (aufgeklappt): Angebotsnummer, Kunde und Maschine fett in der ersten Zeile, "
            "darunter Datum, Kundenname und Standard-Stangenlänge; dann paarweise Anfrage und Bemerkung, Lieferzeit "
            "und Material neuer Positionen, darunter der Bearbeiter. Ganz unten die aufklappbaren Maschinenparameter."),
        (2, "<b>Übersicht</b> rechts über die ganze Höhe: Stand der Optimierung, Herstellkosten und Verkaufspreis "
            "groß, Meldungen, Kennzahlen, Preisaufbau und Zeiten."),
        (3, "<b>Positionen</b>: eine Zeile je Teil mit Stückzahl, Spalte Status direkt nach der Positionsnummer. "
            "Der Status hat zusätzlich zur Farbe ein Symbol: grüner Haken = OK, blaues i = Hinweis, gelbes Dreieck = "
            "Warnung oder veraltet, rotes Kreuz = Fehler. Eingabefelder sind hell gelb, berechnete Werte grau."),
        (4, "<b>Neue Position</b> (fragt zuerst den Typ, [[neue_position]]); löschen: Rechtsklick oder Entf."),
        (5, "<b>Zusatzarbeiten …</b>: Gewinde und Zusatzarbeiten der markierten Positionen ([[zusatzarbeiten_angebot]]). "
            "Daneben <b>Zukaufteile …</b> mit <i>Zukaufteile bearbeiten …</i> (eingekaufte Teile je Position) "
            "<i>Neuer Zukaufartikel …</i> (z. B. Bleche schnell als eigene Positionen anlegen, [[zukauf_angebot]]) und "
            "<i>EK eintragen …</i> (Einkaufspreis fehlender Zukaufteile direkt im Angebot, [[zukauf_positionen]])."),
        (6, "<b>STEP importieren</b>: Positionen aus Konstruktionsdaten ([[step]])."),
        (7, "<b>Optimieren</b>: Stangen planen und Kalkulation rechnen ([[optimieren]])."),
        (8, "Zeile über der Positionsliste: links Anzahl der Positionen und ausgeblendeten optionalen Spalten, "
            "rechts <b>Weitere Spalten</b>, <b>STEP-Werte (aus CAD)</b> und <b>Berechnete Werte (Programm)</b>."),
        (9, "<b>Schrittanzeige</b>: erledigte Schritte grün mit Haken, der nächste blau (Tooltip: was zu tun ist).")])
    i.text("Die Knöpfe stehen in drei Gruppen: <i>Erfassen</i> (Neue Position, STEP importieren, Ablagefeld), "
           "<i>Rechnen</i> (<b>Optimieren</b> dunkelblau, Zusatzarbeiten, Zukaufteile, Material, 3D-Ansicht) und rechts "
           "<i>Ausgeben</i> (<b>Angebot (PDF)</b> dunkelblau, alles Weitere im Menü <b>Ausgaben</b>, [[ausgabe]]). "
           "Die Übersicht rechts bleibt in jedem Reiter sichtbar.", kurz=True)
    i.genauer("Karten auf- und zuklappen, Spaltenbreiten")
    i.text("Links oben stehen die Karten <b>Angebotskopf</b>, <b>Kalkulation dieses Angebots</b> und <b>Fracht</b>. "
           "Der Angebotskopf ist bei einem neuen Angebot aufgeklappt; sobald Kunde und Positionen eingetragen sind, "
           "klappt er beim Öffnen auf eine Zeile zu („A-2026-0041 · 10233 Anlagenbau Hessler · T03 · 6.000 mm · …“). "
           "Ein Klick auf Titel oder Zeile klappt ihn auf; die Wahl gilt, solange das Angebot offen ist. Die Karte "
           "<b>Fracht</b> zeigt zugeklappt Frachtart und Betrag, <b>Fracht berechnen …</b> steht auch zugeklappt "
           "bereit. Die Karte <b>Kalkulation dieses Angebots</b> zeigt zugeklappt eine Kurzfassung aller Werte "
           "ungleich 0, abweichende Werte orange „(n abweichend von den Einstellungen)“. Auf- und Zuklappen von "
           "Fracht und Kalkulation gilt für alle Angebote. Die Trennlinien zwischen oben und unten und zur Übersicht "
           "lassen sich mit der Maus verschieben; bei kleinen Fenstern rollt der obere Teil. <b>Ablage öffnen</b> "
           "und der <b>CSV-Export</b> liegen im Menü <b>Ausgaben</b>.",
           "<b>Spaltenbreite und Zeilenhöhe</b> passen sich in allen Tabellen dem Inhalt an (höchstens etwa 260 "
           "Punkte, Zeiten 420; die letzte Spalte füllt den Rest). Langer Text bricht um, höchstens drei Zeilen, der "
           "Rest steht gekürzt mit „…“ und vollständig im Tooltip. Beim Tippen werden Spalten nur breiter. Eine von "
           "Hand gezogene Spalte behält ihre Breite, auch nach einem Neustart (gemerkt je Tabelle, nur an diesem "
           "Arbeitsplatz); Doppelklick auf die Trennlinie passt sie einmal an, Rechtsklick auf den Spaltenkopf → "
           "<b>Spaltenbreiten zurücksetzen</b> vergisst die gemerkten Breiten der Tabelle. Ab 500 Zeilen bleiben "
           "die Zeilen einzeilig. Die Hauptknöpfe tragen ein schlichtes Symbol vor dem Text (z. B. Blitz für "
           "Optimieren, Würfel für STEP).")
    i.abschnitt("Neue Position: erst der Typ", marke="neue_position")
    i.text("<b>Neue Position</b> (Strg+N) fragt zuerst: <i>Welche Art von Position?</i>", kurz=True)
    i.tabelle(["Typ", "öffnet"], [
               ["<b>Rohr / Profil</b>", "den Schneidweg-Rechner mit Profil, Werkstoff, Länge, Stückzahl "
                "([[schneidweg_rechner]])"],
               ["<b>Blech / Kantteil</b>", "den Blech-Editor; der Richtpreis wird Einkaufspreis ([[blech_editor]])"],
               ["<b>Zukaufteil</b>", "die Schnellanlage für Normteile, Schrauben, Handelsware"],
               ["<b>Schweißbaugruppe</b>", "den Editor der Baugruppe; markierte Positionen sind als Einzelteile "
                "vorgewählt ([[schweissbaugruppe]])"],
               ["<b>Leere Zeile</b>", "eine leere Zeile, alle Werte von Hand"]], [38, 132], kurz=True)
    i.genauer()
    i.tabelle(["Typ", "Was passiert"], [
               ["<b>Rohr / Profil</b>", "Der Schneidweg-Rechner öffnet mit einer Kopfzeile: "
                "Artikel, Bezeichnung, <b>Profilform</b> (Quadratrohr, Rechteckrohr, Rundrohr …; die Profilliste "
                "daneben zeigt dann nur diese Form, <i>alle Profilformen</i> zeigt alle), Profil (Eintippen sucht, "
                "z. B. 40x40), Werkstoff, Teilelänge und Stückzahl. Profil und Werkstoff sind von der letzten "
                "Rohrposition vorbelegt. Ein anderes Profil baut Skizze, Enden und Naht sofort neu auf. Fehlt das "
                "Profil, legt <b>Neu …</b> neben der Liste es an: Fenster <i>Neues Profil</i> mit Profilform, "
                "Abmessungen und Wandstärke; die Profil-ID wird aus den Maßen vorgeschlagen (z. B. RE 70x35x2,5; Träger, "
                "T- und U-Profile mit passenden Maßen mit ihrer Normbezeichnung wie IPE 200, HEA 200, HEB 160, "
                "UPN 100), "
                "Querschnitt, kg/m und Hüllkreis rechnet das Programm. <b>Profil anlegen</b> schreibt es in die "
                "Stammdaten ([[stammdaten]]) und wählt es; den Materialpreis danach unter Einstellungen oder als "
                "Meterpreis im Angebot eintragen. Ohne Profil aus den Stammdaten oder ohne Teilelänge bleibt "
                "<b>Position anlegen</b> gesperrt. Danach steht die Position mit Schneidweg, Einstichen und Naht in "
                "der Liste."],
               ["<b>Blech / Kantteil</b>", "Zuschnitt oder Kantteil beschreiben; der Richtpreis wird Einkaufspreis "
                "eines neuen Zukaufartikels (Kategorie Blechteile)."],
               ["<b>Zukaufteil</b>", "Dieselbe Schnellanlage ohne vorgewählte Kategorie."],
               ["<b>Schweißbaugruppe</b>", "Editor mit Struktur, Nahtgruppen und Arbeitsgängen; die Baugruppe "
                "kommt als eigene Position in die Liste, ihre Einzelteile bleiben Positionen ([[schweissbaugruppe]])."]],
              [38, 132])
    i.abschnitt("Angebotskopf", marke="angebotskopf")
    i.schritte([
        ("angebot_positionen", "<b>Kunde</b> aus der Liste wählen: Name und Zahlungsbedingungen kommen aus dem "
                               "Kundenstamm.", (0, 0.05, 0.62, 0.21)),
        ("angebot_positionen", "<b>Maschine</b> und <b>Standard-Stangenlänge</b> prüfen (vorbelegt).",
         (0.5, 0.05, 0.8, 0.21)),
        ("angebot_positionen", "<b>Lieferzeit</b>, <b>Material neuer Positionen</b> und <b>Bemerkung</b> nach Bedarf.",
         (0, 0.15, 0.62, 0.34))], hoehe=40 * mm)
    i.genauer("alle Felder des Kopfs")
    i.liste("<b>Maschine</b> bestimmt Endbeschnitt, Greiferrest, Schnittverlust, Konturgrenzen, Stundensatz und die "
            "Schneiddaten. Die Zeile <b>Maschinenparameter</b> zeigt Endbeschnitt, Greiferrest, Schnittverlust und "
            "max. Stangenlänge auch zugeklappt (immer, auch wenn ein Wert 0 ist); aufgeklappt kommen Abstand "
            "getrennte Schnitte, Konturgrenzen und, wenn gesetzt, max. Hüllkreis-Ø und max. Metergewicht dazu. "
            "Geändert werden sie in den Stammdaten Maschinen.",
            "<b>Standard-Stangenlänge</b> gilt für alle Positionen ohne abweichende Stangenlänge.",
            "<b>Frachtkosten</b> kommen ohne Zuschläge auf den Angebotspreis; wie, steht in der Karte <b>Fracht</b> "
            "([[fracht_angebot]]).",
            "<b>Kundennummer</b>: Kunden aus der Liste wählen (Nummer und Name) oder eine Nummer eintippen. Steht der "
            "Kunde im Kundenstamm, übernimmt das Programm Kundenname und Zahlungsbedingungen; eine unbekannte Nummer "
            "wird nur gespeichert.",
            "<b>Ihre Anfrage / Zeichen</b>: Anfragenummer oder Zeichen des Kunden (z. B. „Anfrage 4711 vom "
            "20.10.2026“); steht im Angebots-PDF unter der Kundennummer als <i>Ihre Anfrage</i>. Leer = keine Zeile.",
            "<b>Lieferzeit</b> dieses Angebots ([[lieferzeit]]): Angabe als <i>Arbeitstage</i>, <i>Wochen</i>, "
            "<i>Kalenderwoche</i>, <i>Lieferdatum</i> oder <i>nur Text</i>, dazu der passende Wert und ein Freitext "
            "für <b>Lieferbedingungen</b>. Darunter steht, wie es im Angebot erscheint.",
            "<b>Skonto</b>, <b>Skontofrist</b>, <b>Zahlungsziel netto</b>: Zahlungsbedingung dieses Angebots, "
            "vorbelegt vom Kunden bzw. aus den Einstellungen und hier änderbar. Das Skonto wird in den Preis "
            "eingerechnet: Verkaufspreis = Preis ohne Skonto ÷ (1 − Skonto). Zahlt der Kunde mit Skonto, bleibt "
            "genau der kalkulierte Preis. 0 % = kein Skonto.",
            "<b>Kalkulation dieses Angebots</b>: Zuschlag Fremdleistung, Gewinn, Rüstzeit und "
            "Pauschale je Abmessung, Programmierzeit je Position und Angebotsaufschlag. Mindestpreis, Zuschlag "
            "Material und Zuschlag Fertigung gelten immer aus den Einstellungen und sind im Angebot nicht änderbar; "
            "das Häkchen <b>Mindestauftragswert anwenden</b> schaltet den Mindestpreis nur für dieses Angebot ab "
            "([[mindestpreis]]). Ein neues Angebot übernimmt die "
            "Werte aus den Einstellungen (Gruppe Kalkulation); hier lassen sie sich für dieses Angebot ändern, ohne "
            "die Einstellungen zu ändern. Werte, die von den Einstellungen abweichen, sind <b>gelb</b> hinterlegt "
            "(Tooltip: Standardwert); darunter steht, welche Werte abweichen, auch Stundensätze und Zeitvorgaben aus "
            "dem Reiter Zeiten & Arbeitskosten, und zugeklappt zeigt die Kurzfassung die Anzahl („3 abweichend“). "
            "Nach jeder Änderung eines Kalkulationswerts nennt die Statuszeile den Verkaufspreis vorher und nachher "
            "(z. B. „Verkaufspreis netto 1.234,00 € → 1.290,50 €.“). Ändert jemand die Einstellungen, bleiben "
            "bestehende Angebote unverändert; nur neue Angebote übernehmen die neuen Werte. "
            "<b>Vorgaben aus Einstellungen</b> setzt Kalkulationswerte, Stundensätze und Zeitvorgaben wieder auf die "
            "Einstellungen bzw. Stammdaten; die Rückfrage nennt jede Änderung (alt → neu). Von Hand eingetragene "
            "Werte an den Positionen (Meterpreis, Schneidzeit, Zukaufteile) bleiben. "
            "Angebote aus älteren Programmversionen rechnen mit den Einstellungen, bis hier ein Wert geändert wird. "
            "Beim Kopieren gehen die Werte mit.",
            "Die Kalkulationswerte stehen in vier Gruppen: <b>Material und Fertigung</b> (Zuschläge), <b>Zeit und "
            "Rüsten</b> (Rüstzeit je Maschine, Stangenwechsel und Stundensatz der Maschine zur Information, Rüstzeit "
            "je Abmessung, Programmierzeit je Position und je Innenkontur), <b>Verkauf und Gewinn</b> (Gewinn, Angebotsaufschlag, Pauschale je "
            "Abmessung, Frachtkosten, Mindestpreis) und <b>Zahlungsbedingungen</b>.")
    i.abschnitt("Lieferzeit im Angebot", marke="lieferzeit")
    i.text("Jedes Angebot hat seine eigene Lieferzeit, vorbelegt aus den Einstellungen ([[einstellungen]]). Sie "
           "ändert keine Preise.")
    i.tabelle(["Lieferzeit als", "Wert", "im Angebot"], [
        ["Arbeitstage", "ganze Zahl, z. B. 10", "Lieferzeit: ca. 10 Arbeitstage nach Auftragseingang."],
        ["Wochen", "ganze Zahl, z. B. 3", "Lieferzeit: ca. 3 Wochen nach Auftragseingang."],
        ["Kalenderwoche", "KW/Jahr, z. B. 46/2026 (ohne Jahr: Jahr des Angebotsdatums)", "Lieferzeit: KW 46/2026."],
        ["Lieferdatum", "Datum TT.MM.JJJJ", "Lieferzeit: bis 15.11.2026."],
        ["nur Text", "– (Feld gesperrt)", "Lieferzeit: und der Freitext, z. B. „nach Absprache“"]], [30, 60, 90],
        kurz=True)
    i.genauer()
    i.liste("Der Freitext (<b>Lieferbedingungen</b>) steht hinter dem Wert, z. B. „…, Teillieferung möglich.“",
            "Ungültige Eingaben weist das Programm ab und behält den alten Wert: keine ganze Zahl bei Arbeitstagen "
            "und Wochen, eine Kalenderwoche, die es im Jahr nicht gibt (1 bis 52 bzw. 53), ein ungültiges Datum. "
            "Ein Freitext wird nie als Datum gelesen. Liegt das Lieferdatum vor dem Angebotsdatum, kommt ein "
            "Hinweis.",
            "Wechselt die Art, bleibt der Wert nur, wenn er weiter passt (10 Arbeitstage → 10 Wochen), sonst wird "
            "er leer.",
            "Im Angebots-PDF steht die Lieferzeit vor Fracht, Zahlungsbedingung und den Bedingungen. Hat das Angebot "
            "eine eigene Lieferzeit, lässt das Programm einen Satz über die Lieferzeit in den Bedingungen (z. B. "
            "„Lieferzeit nach Absprache.“) weg, damit sich das Angebot nicht widerspricht.",
            "Eine geänderte Vorgabe in den Einstellungen ändert bestehende Angebote nicht. Die Lieferzeit macht die "
            "Optimierung nicht veraltet. Angebote aus älteren Programmversionen haben keine eigene Lieferzeit: dort "
            "gilt wie bisher nur der Text der Bedingungen.")
    i.abschnitt("Kundenmaterial", marke="kundenmaterial")
    i.text("Stellt der Kunde das Material bei: Spalte <b>Material</b> der Position auf <i>Kunde beigestellt</i>. Im "
           "Angebotskopf gilt <b>Material neuer Positionen</b> für neue Positionen (auch STEP), <b>Für alle "
           "Positionen</b> stellt alle um. Gerechnet wird dann ohne Materialkosten.")
    i.genauer()
    i.text("Leer = Eigenmaterial. Jede Position bleibt einzeln änderbar, so können in einem Angebot beigestellte und "
           "eigene Teile stehen.")
    i.liste("Optimierung: Kundenmaterial ist eine eigene Stangengruppe und kommt nie mit eigenem Material auf eine "
            "Stange. Der Stangenbedarf wird wie sonst optimiert: so viele Stangen muss der Kunde liefern. Einen "
            "Vergleich der Lieferlängen gibt es für Kundenmaterial nicht.",
            "Kalkulation: keine Materialkosten, kein Zuschlag Material, kein Verschnittwert und kein Meterpreis. "
            "Laser, Gewinde, Rüsten, Stangenwechsel, Arbeitsschritte, Zusatzarbeiten, Programmierung und "
            "Pauschalen bleiben. Materialkosten anderer Positionen ändern sich nicht. Spalte <i>Kundenmaterial</i> "
            "im Reiter Kalkulation, Status „HINWEIS: Material vom Kunden beigestellt“.",
            "<b>Handling Kundenmaterial</b> [€/m]: optional für Prüfen, Einlagern und Transport, je Meter der "
            "beigestellten Stangen, mit Zuschlag Fertigung und Gewinn (Kostenart <i>Handling Kundenmaterial</i>). "
            "Vorgabe 0 = keins; Einstellung in der Gruppe Kalkulation, je Angebot änderbar.",
            "Angebot: Die Position heißt „Material S235 EN10219 vom Kunden beigestellt“ statt „inkl. Material …“; "
            "vor den Bedingungen steht „Material wird vom Kunden beigestellt: 2 Stangen Quadratrohr 40 x 40 x 3, "
            "S235 EN10219, à 6.000 mm.“ (abschaltbar mit der Einstellung <i>Angebots-PDF: Hinweis zum "
            "Kundenmaterial mit Stangenbedarf</i>). Werkstattpapier und Nachkalkulation führen das Kundenmaterial "
            "als eigene Zeile.",
            "Staffelpreise rechnen das Kundenmaterial in jeder Stufe ohne Materialkosten.")
    i.abschnitt("Mindestpreis", marke="mindestpreis")
    i.text("Liegt ein Angebot unter dem <b>Mindestpreis</b> (Mindestauftragswert, Vorgabe 200,00 € netto), hebt das "
           "Programm alle Stückpreise im gleichen Verhältnis an. Der Betrag steht nur in den Einstellungen; je "
           "Angebot lässt er sich mit dem Häkchen <b>Mindestauftragswert anwenden</b> (Karte <i>Kalkulation dieses "
           "Angebots</i>) ausschalten.", kurz=True)
    i.genauer()
    i.text("Es entsteht keine zusätzliche Position, und Zeiten, Material und Herstellkosten bleiben wie kalkuliert. "
           "Der Mindestpreis ist netto: nach eingerechnetem Skonto und vor der Umsatzsteuer.")
    i.liste("Beispiel: kalkuliert 148,00 € netto, Mindestpreis 200,00 € → jeder Stückpreis × 200 ÷ 148; "
            "Angebotspreis netto 200,00 €. In Übersicht, Reiter Kalkulation und Kalkulations-PDF steht die "
            "Differenz als Kostenart <b>Anhebung auf Mindestpreis</b> (mit kalkuliertem Preis und Mindestpreis), "
            "je Position in der Spalte <i>Mindestpreis je Teil</i>.",
            "Im Angebots-PDF sieht der Kunde nur die angehobenen Stückpreise und den Hinweis „Mindestauftragswert "
            "200,00 € netto.“. Die angehobenen Stückpreise sind auf den Cent aufgerundet, damit die Summe nie unter "
            "dem Mindestpreis liegt (200 € bei 7 Stück: 28,58 € je Stück = 200,06 €).",
            "Genau beim Mindestpreis oder darüber ändert sich nichts. Der Mindestpreis gilt einmal je Angebot, nicht "
            "je Position; ein Angebot ohne Preis (keine Stückzahl) bleibt bei 0 €.",
            "Staffelpreise: jede Mengenstufe ist ein eigenes Angebot und wird für sich mit dem Mindestpreis "
            "verglichen ([[staffeln]]).",
            "Der Wert steht nur in den Einstellungen (Gruppe Kalkulation, durch das Passwort geschützt) und gilt für "
            "alle Angebote, auch für ältere; im Angebot selbst lässt sich der Betrag nicht ändern. 0 = kein "
            "Mindestpreis.",
            "<b>Mindestauftragswert anwenden</b> (Karte <i>Kalkulation dieses Angebots</i>, oben unter den "
            "Hinweisen): Vorgabe an. Ohne Haken rechnet das Angebot ohne Mindestpreis, auch in den Staffelpreisen "
            "und im Angebots-PDF (kein Hinweis „Mindestauftragswert …“); die Kurzzeile der zugeklappten Karte zeigt "
            "dann „ohne Mindestauftragswert“. Die Statuszeile nennt, wie sich der Preis dadurch ändert.",
            "Die Prüfung läuft bei jeder Änderung neu (Position, Stückzahl, Zuschläge, Staffelstufe, PDF). Die "
            "Werte des Angebots (Gewinn, Zuschläge …) bleiben dabei unverändert; steigt der Preis über den "
            "Mindestpreis, entfällt die Anhebung von selbst.")
    i.abschnitt("Nullwerte und Erweiterte Einstellungen")
    i.text("Werte, die 0 sind und nur optional etwas kosten würden, stehen im aufklappbaren Bereich <b>Erweiterte "
           "Einstellungen</b> (Titel z. B. „1 Wert auf 0“). Sobald ein Wert nicht 0 ist, steht er wieder oben.")
    i.bild("angebot_erweitert", "Erweiterte Einstellungen und Maschinenparameter aufgeklappt (Frachtkosten 0 €)",
           hoehe=85 * mm, kurz=False)
    i.genauer()
    i.text("Gespeichert, gerechnet und ausgegeben wird immer alles, auch was ausgeblendet ist. Ob ein Wert 0 ist, "
           "prüft das Programm an der Zahl, nicht am Text: „0,00 €“ und „0 %“ sind 0, „10,00 €“ nicht.")
    i.tabelle(["Bereich", "ausgeblendet, wenn 0 oder leer", "immer sichtbar"], [
        ["Angebotskopf", "Frachtkosten, Skonto, Skontofrist, Zahlungsziel, Zuschläge, Gewinn, Rüstzeit und Pauschale "
                         "je Abmessung, Programmierzeit, Angebotsaufschlag",
         "Angebotsnummer, Kunde, Datum, Maschine, Standard-Stangenlänge, Bemerkung"],
        ["Maschinenparameter", "Abstand getrennte Schnitte, Konturgrenzen, max. Hüllkreis-Ø, max. Metergewicht",
         "Endbeschnitt, Greiferrest, Schnittverlust, max. Stangenlänge"],
        ["Übersicht", "jede Kostenart mit 0,00 €", "Material, Herstellkosten, Verkaufspreis, Kennzahlen"],
        ["Positionen", "Oberfläche, Stangenlänge abweichend, Satz, Stück je Satz, Gewinde "
                       "geprüft, Zusatzarbeiten (solange keine Position einen Wert hat)",
         "Pos., Artikelnummer, Bezeichnung, Profil-ID, Werkstoff-ID, Teilelänge, Stückzahl, Schneidweg, Einstiche, "
         "Schneidzeit, Materialpreis, Status"]], [32, 80, 70])
    i.abschnitt("Übersicht")
    i.text("Rechts im Angebot: Stand, <b>Herstellkosten</b> und <b>Verkaufspreis</b> groß, darunter Meldungen, "
           "<b>Angebots-Check</b>, Kennzahlen, <b>Preisaufbau</b> und Zeiten. Vor dem Optimieren stehen die "
           "Preise grau mit „(vorläufig)“.")
    i.genauer()
    i.liste("Ganz oben der <b>Stand der Optimierung</b>: <i>Noch nicht optimiert</i> (gelb), <i>Optimierung "
            "abgeschlossen</i> (grün) oder <i>Veraltet</i> (rot, [[veraltet]]).",
            "Darunter der <b>Preisstand</b>: <i>Preise: aktuelle Stammdaten</i>, solange noch kein "
            "Angebots-PDF erzeugt wurde, danach <i>Preise festgeschrieben am …</i>. Haben sich die Stammdaten "
            "seitdem geändert, steht er gelb mit der Anzahl der Änderungen (Mauszeiger darauf zeigt sie einzeln), "
            "und der Knopf <b>Aktuelle Preise übernehmen …</b> erscheint ("
            "[[preise_festschreiben]]).",
            "Darunter groß <b>Herstellkosten</b> und <b>Verkaufspreis</b>, damit sie auch auf kleinen Bildschirmen "
            "ohne Rollen zu sehen sind. Vor dem Optimieren (oder wenn die Optimierung veraltet ist) stehen sie grau "
            "mit „(vorläufig)“: Material, Stangenwechsel und Verschnitt fehlen dann noch.",
            "<b>Meldungen</b>: die Anzahl der Fehler, Warnungen und Hinweise der Positionen (rot, gelb); aufklappen "
            "zeigt jede Meldung mit ihrer Positionsnummer.",
            "<b>Angebots-Check</b>: alle offenen Punkte vor dem Versand laufend in einer Liste, jeder mit "
            "<b>Hinspringen</b> zur Stelle (Position, Feld im Kopf, Staffeln …). Der Titel zählt die offenen Punkte "
            "(FEHLER, WARNUNG) und die Hinweise; ist alles erledigt, steht dort grün „alles erledigt“. Welche Punkte "
            "es gibt und wie die eine Rückfrage vor dem PDF aussieht: [[angebots_check]].",
            "Kennzahlen: Positionen, Stückzahl und Gewicht. Stangenbedarf und Längen stehen je Abmessung in den "
            "Reitern <i>Schnittplan</i> und <i>Stangenbild</i>.",
            "<b>Preisaufbau</b> Schritt für Schritt: Material, + Laser schneiden, + Rüsten (Rüsten Maschine, Rüsten "
            "je Abmessung, Stangenwechsel), + Zusätzliche Bearbeitung (Gewinde, Zusatzarbeiten), + Zuschläge, "
            "= <b>Herstellkosten</b>, + Programmierkosten, + Pauschalen und Aufschläge (Pauschale je Abmessung, "
            "Angebotsaufschlag), + Zukaufteile, = <b>Selbstkosten</b>, + Gewinn (auf die Selbstkosten), + Fracht "
            "(ohne Gewinn), + Skonto, = <b>Verkaufspreis</b> ([[gewinn_basis]]). Ein Klick auf "
            "eine Gruppe mit ▸ klappt ihre Kostenarten auf. <b>Kostenarten einzeln</b> zeigt alle Kostenarten mit "
            "ihrer Mengenangabe, der <b>Kostenwasserfall</b> dieselben Gruppen als Balken: jeder beginnt dort, wo der "
            "vorige endet, die Summen (Herstellkosten, Selbstkosten, Verkaufspreis) reichen von 0 bis zum Betrag. So ist auf einen Blick zu "
            "sehen, welcher Posten den Preis treibt.")
    i.abschnitt("Wiederholteile", marke="wiederholteile")
    i.text("Wurde ein Teil schon einmal angeboten, auch von einem Kollegen, zeigt die Übersicht <b>Wiederholteile</b>: "
           "wie oft, zuletzt wann und in welchem Angebot, den damaligen Preis je Stück aus den Staffelpreisen und ob "
           "das Angebot beauftragt war.", kurz=True)
    i.liste("<b>sicher</b>: gleiche Artikelnummer beim selben Kunden; <b>prüfen</b>: gleiche Artikelnummer bei einem "
            "anderen Kunden; <b>ähnlich</b>: ohne passende Nummer, aber gleiches Profil und gleicher Werkstoff, Länge "
            "± 0,5 mm, Schneidweg ± 1 % und gleich viele Konturen. Beauftragte und neuere Angebote stehen vorn.",
            "<b>Werte übernehmen …</b> bietet die Eingaben der alten Position an, die man sonst von Hand wiederholt "
            "(Schneidzeit von Hand, Programmierzeit, Einstiche, Zusatzarbeiten, Gewinde, Schweißnaht); jeder Wert "
            "lässt sich einzeln abwählen, Strg+Z nimmt die Übernahme zurück.",
            "Der <b>Preis wird nie übernommen</b>, er entsteht immer neu aus der Kalkulation mit den heutigen "
            "Stammdaten. <b>Angebot öffnen</b> zeigt das alte Angebot, <b>Hinspringen</b> markiert die Position.")
    i.abschnitt("Positionen", marke="positionen")
    i.text("Eine Zeile je Teil. Pflicht sind <b>Profil-ID</b>, <b>Werkstoff-ID</b>, <b>Teilelänge</b> und "
           "<b>Stückzahl</b>; gelbe Felder sind Eingaben, graue rechnet das Programm. Optionale Spalten erscheinen, "
           "sobald eine Position dort einen Wert hat, oder über <b>Weitere Spalten</b>.", kurz=True)
    i.genauer("alle Spalten")
    i.tabelle(["Spalte", "Eintrag"], [
        ["Pos., Artikelnummer, Bezeichnung", "frei; die Artikelnummer erscheint in Angebot und Werkstattpapieren"],
        ["Positionsart", "leer bzw. <i>Rohrlaserteil</i> = Teil aus Profil, wird optimiert und gelasert; "
                         "<i>Zukaufteil</i> = eingekauftes Teil ohne Fertigung, z. B. ein Blech aus dem STEP-Import "
                         "([[zukauf_positionen]]). Die Spalte erscheint, sobald eine Position eine "
                         "Art hat"],
        ["Profil-ID, Werkstoff-ID", "aus der Auswahlliste der Stammdaten (Pflicht), Werkstoffe nach Kategorie "
                                    "gruppiert. Optimiert wird je Profil + Werkstoff + Oberfläche + Stangenlänge, "
                                    "nie gemischt."],
        ["Oberfläche", "z. B. K240 oder gestrahlt (Stammdaten Oberflächen); leer = roh. Der Aufpreis kommt auf den "
                       "Materialpreis, der Text ins Angebot."],
        ["Teilelänge [mm], Stückzahl", "Pflicht"],
        ["Schneidweg je Teil [mm], Einstiche je Teil", "für die Laserzeit; der STEP-Import oder der "
                                                       "Schneidweg-Rechner ([[schneidweg_rechner]]) füllt sie aus. Anfangs- "
                                                       "und Endschnitt zählen je nach Profil mehrere Einstiche: "
                                                       "I-/H-Träger und U-Profil 4, T-Profil 2, alle anderen 1 "
                                                       "(z. B. IPE 200 ohne Bohrungen: 8 Einstiche)"],
        ["Schneidzeit je Teil [s]", "grau = berechnet; anpassen ersetzt die berechnete Schneidzeit ([[schneidzeit]])"],
        ["Programmierzeit [min]", "grau = Grundzeit je Position + Zeit je Innenkontur × Innenkonturen; anpassen "
                                  "(fett) ersetzt sie für diese Position, leeren = wieder berechnet ([[stundensaetze]])"],
        ["Stangenlänge abweichend", "nur wenn diese Position aus einer anderen Stangenlänge geschnitten wird"],
        ["Satz, Stück je Satz", "Zusammengehörige Teile (z. B. ein Gestell) für Staffelpreise je Satz ([[staffeln]])"],
        ["Materialpreis [€/m]", "grau = berechneter Meterpreis; anpassen ersetzt ihn für dieses Angebot "
                                "([[meterpreis]])"],
        ["Gewinde geprüft", "z. B. <i>4xM6; 2xM8</i> (Trennung mit Semikolon oder Komma, x oder ×). Nur was hier "
                            "steht, wird als Gewinde gerechnet; ein Gewinde, das nicht in den Stammdaten steht, "
                            "meldet eine WARNUNG. Doppelklick öffnet <i>Bohrungen prüfen</i> "
                            "([[bohrungen_pruefen]])."],
        ["Zusatzarbeiten", "Kurzanzeige der gewählten Zusatzarbeiten; Doppelklick öffnet die Auswahl ([[zusatzarbeiten_angebot]])"],
        ["Zukaufteile", "Kurzanzeige der Zukaufteile mit Menge je Teil bzw. je Satz (z. B. 20 St/Satz); Doppelklick öffnet die Auswahl ([[zukauf_angebot]])"],
        ["Gewicht je Teil [kg]", "nur für Zukaufteil-Positionen: Gewicht für die Fracht nach Gewicht (der STEP-Import "
                                 "rechnet es aus Volumen × Dichte, wenn der Werkstoff gewählt ist; sonst leer)"],
        ["Abweichung Schneidweg zu STEP [mm]", "nur sichtbar, wenn der Schneidweg einer importierten Position von Hand "
                                               "geändert wurde: eingetragener Schneidweg minus Anfangsschnitt + "
                                               "Endschnitt + Innenkonturen aus STEP (gelb)"]],
        [75, 190])
    i.text("Die Spalten Oberfläche, Stangenlänge abweichend, Satz, Stück je Satz, Gewinde geprüft, Zusatzarbeiten und "
           "Zukaufteile erscheinen von selbst, sobald eine Position dort einen "
           "Wert hat. Mit <b>Weitere Spalten</b> (in der Zeile über der Tabelle) lässt sich jede dieser Spalten fest ein- "
           "oder ausblenden, z. B. um bei einem neuen Angebot gleich Sätze einzutragen; leere Spalten sind dort mit "
           "„(leer)“ markiert. Die Wahl gilt für alle Angebote, bis <i>Automatisch: Spalten mit Werten zeigen</i> sie "
           "zurücksetzt. Ausgeblendete Spalten verlieren keine Werte.")
    i.abschnitt("Zusatzarbeiten und Gewinde je Bauteil", marke="zusatzarbeiten_angebot")
    i.text("Positionen markieren → <b>Zusatzarbeiten …</b> (oder Doppelklick in die Spalte <i>Zusatzarbeiten</i>).",
           kurz=True)
    i.bild("zusatz_dialog", "Zusatzarbeiten für eine Position: Gewinde, Feuerverzinken und eine zusätzliche Gravur",
           hoehe=80 * mm, legende=[
               (1, "<b>Gewinde (geprüft)</b>: Anzahl x Größe, mehrere mit Semikolon. Darunter der Festpreis je Teil "
                   "aus den Stammdaten Gewinde."),
               (2, "<b>Zusatzarbeit</b> aus der Liste wählen; die Abrechnung (€/kg, €/m², €/m, €/Stück, s/Stück, "
                   "€/h) kommt aus den Stammdaten."),
               (3, "<b>Menge je Teil</b> und <b>Preis bzw. Zeit</b>: leer lassen = automatisch (grau angezeigt). "
                   "Ein Eintrag gilt nur für diese Position, z. B. eine andere Fläche oder ein Sonderpreis."),
               (4, "<b>Text</b> für das Angebot, z. B. die RAL-Farbe beim Pulverbeschichten."),
               (5, "<b>Zusatzarbeit hinzufügen</b> / <b>Markierte entfernen</b> / <b>Preise aus Stammdaten "
                   "übernehmen</b>.")])
    i.genauer()
    i.text("Oben die Gewinde, darunter beliebig viele Zusatzarbeiten aus den Stammdaten. Gewinde lassen sich tippen "
           "oder mit Anzahl, Gewinde aus der Liste und <b>Gewinde hinzufügen</b> anhängen. Eine Angabe, die das "
           "Programm nicht erkennt (z. B. „4xM7“ ohne Stammdaten), steht rot darunter, weil sie mit 0 € rechnen würde. "
           "Bei einer einzelnen Position führen <b>Schweißnaht …</b> und <b>Bohrungen prüfen …</b> unten rechts zur "
           "übrigen Bearbeitung derselben Position.")
    i.liste("Sind mehrere Positionen markiert, gilt die Auswahl für alle. Die automatische Menge (Gewicht, Fläche, "
            "Länge) rechnet jede Position für sich.",
            "Die Kosten erscheinen in der Kalkulation in der Spalte <i>Zusatzarbeiten je Teil</i> und in der Summe "
            "<i>Zusatzarbeiten</i>; Zeiten (s/Stück, z. B. Gravur extra) erhöhen die Laserzeit.",
            "<b>Schweißen</b> (Abrechnung €/h): in <i>Menge bzw. Sekunden je Teil</i> die Schweißzeit je Teil in "
            "Sekunden eintragen, gerechnet wird Sekunden ÷ 3600 × Stundensatz (Vorgabe 75 €/h, Stundensatz "
            "<i>Schweißen</i>), z. B. 48 s → 1,00 € je Teil. Ein Wert in der Preisspalte ist ein eigener Stundensatz "
            "nur für diese Position. Ohne Sekunden zeigt der Status <b>WARNUNG: Schweißen ohne Zeit</b> und es "
            "rechnet 0 €. Die Schweißzeit kommt nicht zur Laserzeit; danach Zuschlag Fertigung und Gewinn wie bei "
            "den übrigen Zusatzarbeiten. Im Angebot steht „inkl. geschweißt“.",
            "Im Angebot steht jede Arbeit mit ihrem Text hinter <i>Zusatzarbeiten:</i>.",
            "Die Liste zeigt nur aktive Zusatzarbeiten: zuerst die häufig verwendeten, dann nach Kategorie.",
            "Der Preis der Stammdaten wird beim Hinzufügen in der Position gespeichert (Preisstand, im Feld Preis grau "
            "mit Datum). Haben sich die Stammdaten seitdem geändert, holt <b>Preise aus Stammdaten übernehmen</b> die "
            "aktuellen Werte für alle Zeilen (gilt nach OK).",
            "Steht in einer älteren Position (ohne Preisstand) eine Zusatzarbeit, die es in den Stammdaten nicht mehr "
            "gibt, zeigt der Status <b>WARNUNG: Zusatzarbeit … unbekannt</b> und sie wird nicht gerechnet.")
    i.abschnitt("Schneidzeit anpassen", marke="schneidzeit")
    i.text("Doppelklick in <b>Schneidzeit je Teil [s]</b>, eigene Zeit eintragen: sie steht fett und ersetzt die "
           "berechnete. Feld leeren = wieder berechnet.")
    i.genauer()
    i.text("Die Spalte <b>Schneidzeit je Teil [s]</b> zeigt in Grau die berechnete Schneidzeit (Schneidweg, "
           "Konturklassen, Gravur und Einstiche mit den Vorschüben aus den Schneiddaten; ohne Einsparung gemeinsamer "
           "Schnitte). Ist sie nicht passend (z. B. aus einer Probe oder der Maschinensoftware bekannt), doppelt "
           "klicken: die berechnete Zeit steht im Feld und lässt sich ändern. Die eingetragene Zeit steht dann fett "
           "und ersetzt "
           "die berechnete Zeit ganz, auch die Einsparung durch gemeinsame Schnitte wird nicht mehr abgezogen. Zeiten "
           "aus Zusatzarbeiten (Gravur extra) kommen weiterhin dazu. Der Status zeigt <b>HINWEIS: Schneidzeit "
           "manuell</b>, die Kalkulation in der Spalte <i>Schneidzeit manuell</i> ein „ja“. Feld leeren = wieder "
           "berechnet.")
    i.abschnitt("Meterpreis anpassen", marke="meterpreis")
    i.text("Doppelklick in <b>Materialpreis [€/m]</b>, eigenen Preis eintragen: er steht fett und gilt für alle "
           "Positionen derselben Stangengruppe. Feld leeren = wieder berechnet. Der Mauszeiger zeigt die Herkunft "
           "des berechneten Preises.")
    i.genauer()
    i.text("Die Spalte <b>Materialpreis [€/m]</b> zeigt in Grau den berechneten Einkaufspreis je Meter für Profil, "
           "Werkstoff und Stangenlänge der Position: Preis der Lieferlänge, sonst <i>Preise</i>, sonst Tonnenpreis des "
           "Werkstoffs, jeweils mit dem Aufpreis der Oberfläche. Bei festgeschriebenen Preisen gilt der Stand des "
           "Angebots ([[preise_festschreiben]]). Ist der Preis günstiger oder teurer zu bekommen (z. B. ein aktuelles "
           "Lieferantenangebot), doppelt klicken: der berechnete Preis steht im Feld und lässt sich ändern.")
    i.text("Der Mauszeiger auf dem Preis nennt die <b>Herkunft</b>: Lieferlängen, Preise oder Tonnenpreis, mit Preis, "
           "Lieferant und Gültig ab. Ist der Preis älter als 6 Monate, steht „Achtung: über 6 Monate alt, Preis "
           "prüfen“ dabei.")
    i.liste("Der eingetragene Preis steht fett und ersetzt Preis und Oberflächen-Aufpreis. Er gilt für alle Stangen "
            "mit gleichem Profil, Werkstoff, Oberfläche und Stangenlänge, weil diese Positionen gemeinsam aus "
            "denselben Stangen geschnitten werden. Die anderen Positionen dieser Gruppe zeigen ihn kursiv.",
            "Die Kalkulation, der Lieferlängen-Vergleich und die Staffelpreise rechnen mit dem eingetragenen Preis; "
            "Materialzuschläge der Staffeln kommen wie gewohnt dazu.",
            "Der Status zeigt <b>HINWEIS: Meterpreis manuell</b>. Feld leeren (oder 0 eintragen) = wieder berechnet. "
            "Wird der berechnete Preis unverändert bestätigt, bleibt er berechnet.")
    i.abschnitt("Material je Abmessung (Fenster Material …)", marke="material_fenster")
    i.text("<b>Material …</b> (rechts neben den Ausgaben oder Rechtsklick auf eine Position): alles zum Material je "
           "Abmessung in einem Fenster; <b>Übernehmen</b> gilt für alle Positionen der Abmessung.", kurz=True)
    i.bild("material_fenster", "Material je Abmessung", hoehe=85 * mm, legende=[
        (1, "<b>Querschnitt</b> des Profils (RP-Profile mit ihrer Kontur aus dem MegaCAD-Makro); der Mauszeiger auf "
            "der Abmessung zeigt Teilelänge gesamt und Ausnutzung."),
        (2, "<b>Werkstoff</b>, <b>Oberfläche</b>, <b>Lieferlänge [mm]</b> (Auswahl aus den Stammdaten <i>Lieferlängen</i> oder eintippen) "
            "und <b>Material</b> (Eigenmaterial / Kunde beigestellt). Danach neu optimieren."),
        (3, "<b>Materialeinsatz</b> laut Schnittplan: Stangen, Meter, Gewicht und Materialkosten; darunter die Summe."),
        (4, "<b>Meterpreis [€/m]</b>: grau steht der berechnete Preis ([[meterpreis]]); ein eigener Wert steht fett, "
            "Feld leeren = wieder berechnet. Bei Kundenmaterial gesperrt."),
        (5, "<b>Handling Kundenmaterial [€/m]</b> des Angebots; daneben zur Info Zuschlag Material und "
            "Händler-Mehrlänge aus den Einstellungen.")])
    i.genauer()
    i.text("Abmessung = Profil, Werkstoff, Oberfläche und Stangenlänge. Der Knopf steht vor <i>Materialanfrage "
           "(E-Mail)</i>.")
    i.liste("Der Meterpreis wird wie in der Spalte <i>Materialpreis [€/m]</i> an den Positionen gespeichert; der "
            "Status zeigt dann <b>HINWEIS: Meterpreis manuell</b>.",
            "Ohne Optimierung stehen Stangen, Meter und Gewicht auf „–“; passt der Schnittplan nicht mehr zu den "
            "Positionen, steht oben ein roter Hinweis.",
            "Den Materialeinsatz zeigt auch das Kalkulation-PDF ([[ausgabe]]).")
    i.abschnitt("Abmessung genauer ansehen (Doppelklick im Fenster Material …)", marke="abmessung_fenster")
    i.text("Im Fenster <b>Material …</b> öffnet ein <b>Doppelklick auf Stangen</b> die Abmessung in einem eigenen "
           "Fenster: Stangenbild, Schnittmuster, Bilanz und alle Teile dieser Abmessung.", kurz=True)
    i.bild("abmessung_fenster", "Abmessung im eigenen Fenster", hoehe=110 * mm, legende=[
        (1, "<b>Stangenbild</b> nur dieser Abmessung (wie im Reiter Schnittplan, [[optimieren]]). Klick auf ein Teil "
            "zeigt es in der Teileliste, Doppelklick springt zur Position."),
        (2, "<b>Schnittmuster</b>: gleich belegte Stangen einmal, mit Anzahl, Stangennummern, Teilen je Stange, Rest, "
            "Ausnutzung und Material je Stange. Klick zeigt das Muster im Stangenbild."),
        (3, "<b>Meter- und Gewichtsbilanz</b>: Lieferlänge gesamt = Teile + Schnittfugen + Endbeschnitt + "
            "Greiferrest + Rest (Verschnitt), bei 12-m-Stangen dazu der Zuschnitt beim Lieferanten."),
        (4, "<b>Teile</b> je Position: Länge, Stück, Enden, Naht/Drehung, eingeplant (rot, wenn Teile fehlen), auf "
            "welchen Stangen, Meter, Gewicht, Anteil, Material je Teil, Laserzeit und Verkaufspreis je Teil. "
            "Rechtsklick auf die Kopfzeile blendet Spalten aus."),
        (5, "<b>Knöpfe</b>: Neu optimieren (nur wenn nötig), 12-m-Lösung ansehen, Materialanfrage, Schnittplan drucken "
            "(Werkstattpapiere nur dieser Abmessung) und Positionen markieren.")])
    i.genauer()
    i.text("Doppelklick je Spalte im Fenster <b>Material …</b>:")
    i.liste("<b>Querschnitt</b> oder <b>Abmessung</b>: Profil-Info mit großem Querschnitt, Maßen, Metergewicht, "
            "Hüllkreis-Ø und welche Maschinen das Profil laden können.",
            "<b>Pos.</b>, <b>Stangen</b>: Abmessungs-Fenster; <b>Meter</b>, <b>Gewicht</b>: dasselbe Fenster, die "
            "Bilanz ist orange umrandet.",
            "<b>Material €</b>, <b>berechnet €/m</b>: Preis-Aufbau mit der Herkunft des Meterpreises (Lieferant, "
            "Gültig ab), Einkauf je Lieferlänge mit Händler-Mehrlänge, Zuschlag Material und Verteilung auf die "
            "Positionen.",
            "<b>Rechtsklick</b> auf eine Zeile: alle Fenster und Schritte dieser Abmessung, auch 12-m-Lösung, "
            "Materialanfrage, Schnittplan drucken und Positionen markieren.",
            "Zur Position, Positionen markieren, Neu optimieren, 12-m-Lösung und Materialanfrage schließen das Fenster "
            "<b>Material …</b> wie <b>Übernehmen</b>: Eingaben werden gespeichert. Bei einer ungültigen Eingabe bleibt "
            "es offen. Nach Neu optimieren öffnet es sich mit dem neuen Schnittplan wieder.")
    i.abschnitt("Schweißnaht", marke="schweissnaht")
    i.text("Fordert der Kunde eine Lage der Schweißnaht: Position(en) markieren → <b>Schweißnaht …</b> (Rechtsklick, "
           "<i>Ausgaben</i> oder Doppelklick in die Spalte <b>Schweißnaht</b>), im Querschnitt die Stelle "
           "anklicken und <i>feste Position</i> wählen. Das Teil wird dann nicht gedreht.")
    i.genauer()
    i.text("Das Fenster <i>Schweißnaht – Pos. …</i> zeigt den Rohrquerschnitt.")
    i.liste("<b>Winkel</b>: der Querschnitt wird immer <b>von Ende A in Richtung Ende B</b> gesehen; 0° oben, 90° "
            "rechts, 180° unten, 270° links (im Uhrzeigersinn). Ein Klick in das Bild setzt den Winkel, oder er wird "
            "in das Zahlenfeld eingegeben; 360° wird zu 0°, −90° zu 270°. Bei Rechteck- und Quadratrohr gibt es nur "
            "<b>0°, 90°, 180° und 270°</b> (Mitte einer Seite): der Klick rastet dort ein, die Pfeile springen um "
            "90°. Die Naht lässt sich auch im Schneidweg-Rechner wählen ([[schneidweg_rechner]]).",
            "<b>Nahtvorgabe</b>: <i>keine Vorgabe</i> (Standard, auch für ältere und per STEP importierte "
            "Positionen) = die Optimierung darf das Teil um die eigene Achse drehen (Rechteckrohr 0° und 180°, "
            "Quadrat- und Rundrohr 0°, 90°, 180°, 270°); <i>feste Position</i> = Winkel und Quelle (Kunde, "
            "Zeichnung, manuell, Import) werden gespeichert, das Teil wird nicht gedreht; <i>unbekannt</i> = das "
            "Teil wird ebenfalls nicht gedreht. Gewendet (Ende B nach vorn) wird ein Teil nie.",
            "<b>Querschnittslage</b> (nur Rechteckrohr): <i>Breitseite oben</i> ist der Standard. Liegt das Rohr in "
            "der Zeichnung hochkant, <i>Schmalseite oben</i> wählen und den Winkel so eingeben, wie er in der "
            "Zeichnung steht. Beim Umschalten bleibt die Naht an derselben Stelle des Rohrs, nur der Winkel der "
            "Ansicht ändert sich.",
            "Das Fenster nennt die getroffene Seite: bei Rechteckrohr <i>Breitseite</i> (die längere Seite) oder "
            "<i>Schmalseite</i>, bei Quadratrohr nur die Richtung, bei Rundrohr nur den Winkel. Liegt der Winkel auf "
            "einer Ecke, ist die Seite nicht eindeutig (Warnung).",
            "<b>Naht der Lieferstange</b> (nur Rechteckrohr, bei fester Position): auf welcher Seite die bestellte "
            "Stange ihre Schweißnaht hat, <i>Breitseite</i> oder <i>Schmalseite</i>. Das ist eine Angabe des "
            "<b>Angebots</b>, nicht der Stammdaten: sie gilt in diesem Angebot für alle Positionen mit gleichem "
            "Profil und Werkstoff. <i>aus den Teilen</i> (Standard) = die Seite, die die Teile mit fester Naht "
            "verlangen. Sie steht in der Materialanfrage und lässt sich dort auch ändern ([[materialanfrage]]).",
            "Status: <b>FEHLER: Naht auf … gefordert, Lieferstange hat sie auf der …</b>, wenn eine im Angebot "
            "eingetragene Naht der Lieferstange nicht zur Seite der Position passt; <b>FEHLER: Nahtwinkel fehlt</b> "
            "bei fester Position ohne Winkel. Ohne Eintrag gibt es keinen Hinweis. Die Schweißnaht steht nicht in "
            "STEP-Dateien und wird nie automatisch erkannt.",
            "<b>Stangenwechsel SN</b>: jede Stange, auf der mindestens ein Teil die Nahtvorgabe <i>feste Position</i> "
            "hat, rechnet mit dem <i>Stangenwechsel SN</i> der Maschine (Vorgabe 29 s, die Naht wird ausgerichtet), "
            "alle anderen Stangen mit dem normalen <i>Stangenwechsel</i> (Vorgabe 24 s). Beide Zeiten stehen je "
            "Maschine in den Stammdaten ([[stammdaten]]); der Reiter Zeiten zeigt die Aufteilung, z. B. "
            "„3 × 24 s + 2 × 29 s (SN)“ ([[zeiten]]).")
    i.abschnitt("Rückgängig, Kopieren und Einfügen", marke="rueckgaengig")
    i.tabelle(["Taste", "Wirkung im Angebot"], [
        ["Strg+Z / Strg+Y", "letzte Änderung zurücknehmen / wiederherstellen (bis 100 Schritte)"],
        ["Strg+C / Strg+V", "Zellen kopieren / einfügen, auch Blöcke aus Excel"],
        ["Entf", "markierte Positionen löschen (mit Rückfrage)"],
        ["Strg+N · Strg+I · F9 · Strg+P", "neue Position · STEP-Import · Optimieren · Angebots-PDF"],
        ["F8 · Strg+Umschalt+P / K / M", "Staffelpreise rechnen · Werkstattpapiere · Kalkulation (PDF) · "
                                         "Materialanfrage"],
        ["Strg+Umschalt+S", "Stückzahl ändern (× Faktor oder = Wert)"]], [55, 210],
        kurz=True)
    i.genauer()
    i.text("<b>Strg+Z</b> (oder <i>Bearbeiten → Rückgängig</i>) nimmt die letzte Änderung am geöffneten Angebot "
           "zurück, <b>Strg+Y</b> stellt sie wieder her. Das gilt für jede Änderung: Eingaben in Positionen und Kopf, "
           "neue oder gelöschte Positionen (samt 3D-Ansicht), STEP-Import, Zusatzarbeiten, Zukaufteile, Staffeln, "
           "Zeiten und Optimierung. Die Statuszeile nennt, was zurückgenommen wurde (z. B. „Rückgängig: Teilelänge "
           "[mm] Pos. 20“). Bis zu 100 Schritte gehen zurück, solange das Angebot geöffnet ist; nach dem Schließen "
           "beginnt der Verlauf neu. Stammdaten und Einstellungen haben kein Rückgängig.")
    i.liste("<b>Strg+C</b> kopiert die markierten Zellen, auch mehrere Zeilen und Spalten, so wie sie angezeigt "
            "werden; in Excel lassen sie sich direkt einfügen.",
            "<b>Strg+V</b> fügt ab der markierten Zelle ein. Ein Block aus Excel füllt die Zellen nach rechts und "
            "unten; ein einzelner Wert füllt alle markierten Zellen (z. B. dieselbe Stückzahl für mehrere "
            "Positionen). Grau berechnete Zellen bleiben unverändert, falsche Werte meldet die Statuszeile. Ein "
            "Einfügen ist ein Schritt für Strg+Z.",
            "<b>Stückzahl ändern …</b> (Rechtsklick auf eine Position oder Strg+Umschalt+S): Stückzahl der markierten "
            "Positionen, ohne Markierung aller Positionen: <b>Stückzahl × Faktor</b> (z. B. 2 oder 0,5, kaufmännisch gerundet, "
            "mindestens 1) oder <b>Stückzahl =</b> Wert. Positionen ohne Stückzahl bleiben beim Faktor leer. Ein Schritt für "
            "Strg+Z.",
            "<b>Strg+X</b> kopiert und leert die markierten Eingabezellen.",
            "<b>Entf</b> in der Positionsliste löscht die markierten Positionen nach Rückfrage, <b>Strg+N</b> legt "
            "eine neue Position an, <b>Strg+I</b> startet den STEP-Import, <b>F9</b> optimiert und <b>Strg+P</b> "
            "erzeugt das Angebots-PDF.")
    i.text("In Textfeldern (Kopf, Suchfelder, eine Zelle in Bearbeitung) wirken Strg+Z, Strg+C, Strg+V und Entf wie "
           "gewohnt nur im Text. Alle Kürzel stehen im Anhang ([[tastenkuerzel]]) und im Programm unter "
           "<i>Hilfe → Tastenkürzel …</i>.")


def kapitel_step(i):
    i.kapitel("STEP-Import", marke="step")
    i.schritte([
        ("angebot_positionen", "<b>STEP importieren …</b> (Strg+I) oder STEP-Dateien bzw. Ordner auf das Feld "
                               "<b>STEP-Dateien hierher ziehen</b>.", (0, 0.44, 0.45, 0.52)),
        ("step_pruefen", "Im Fenster <b>STEP-Import prüfen</b> je Teil Häkchen, Profil, Werkstoff und Stückzahl "
                         "prüfen.", (0, 0, 0.6, 0.55)),
        ("step_positionen", "<b>Übernehmen</b>: je Rohr eine Position mit Schneidweg, Einstichen und Konturen.",
         (0, 0.42, 0.8, 0.8)),
        ("bohrbild_dialog", "Gelbe Positionen „Bohrungen prüfen“: Doppelklick, Gewinde und Bohrungen "
                            "<b>Bestätigen</b> ([[bohrungen_pruefen]]).")], spalten=2, hoehe=62 * mm)
    i.genauer("Ablauf im Einzelnen")
    i.text("Der STEP-Import liest Konstruktionsdaten (.step/.stp, ein oder mehrere Rohre je Datei) und legt je "
           "Rohr eine Position an. Gemessen werden Profil, Teilelänge, Schneidweg, Einstiche, Anfangs- und "
           "Endschnitt (gerade oder schräg), Innenkonturen nach Größe, Gravuren, Bohrungen und ein "
           "Gewinde-Vorschlag. Die Messung übernimmt das Programm <i>STEP-Import.exe</i> im Ordner "
           "<i>STEP-Import</i> neben dem Programm.")
    i.liste("Im Angebot auf <b>STEP importieren …</b> klicken und die Dateien wählen (Mehrfachauswahl mit Strg oder "
            "Umschalt). Der Dateidialog startet im Ordner aus der Einstellung <i>STEP-Import: Standardordner</i>; "
            "ist dort keiner eingetragen, im zuletzt benutzten STEP-Ordner.",
            "Oder die STEP-Dateien bzw. ganze Ordner aus dem Explorer per <b>Drag &amp; Drop</b> auf das gestrichelte "
            "Feld <b>STEP-Dateien hierher ziehen</b> neben dem Knopf ziehen (es geht auch irgendwo sonst ins "
            "Angebotsfenster; beim Ziehen färbt sich das Feld blau). Ein leeres Angebot zeigt statt der leeren "
            "Positionsliste ein großes Ablagefeld; ein Klick auf eines der Felder öffnet den Dateidialog wie "
            "<i>STEP importieren …</i>. Aus Ordnern (samt Unterordnern) werden alle .step/.stp-Dateien genommen. "
            "Der Explorer ist gleich nach dem Loslassen wieder frei; das Programm kommt nach vorne und misst. "
            "Während ein Import läuft, nimmt es keine weiteren Dateien an (Hinweis unten im Fenster).",
            "Während der Messung zeigt das Fenster Datei, Körper und die Restzeit. Bleibt ein Körper hängen "
            "(Einstellung <i>Messung: Zeitlimit je Körper</i>, Vorgabe 120 s), wird nur er ausgelassen und die "
            "Datei weiter gemessen. Gleiche Teile einer Baugruppe (z. B. acht gleiche Stützen, im CAD nur "
            "verschoben) werden nur einmal gemessen, und eine große Datei wird auf mehrere Messprozesse verteilt. "
            "Schon gemessene Dateien kommen beim nächsten Import sofort aus dem "
            "Zwischenspeicher. <b>Abbrechen</b> fragt, ob die bis dahin gemessenen Dateien übernommen werden "
            "sollen ([[einstellungen]]).",
            "Nach der Messung zeigt der Dialog <b>STEP-Import prüfen</b> die Rohre einer STEP-Datei, gegliedert "
            "nach Profil, mit drehbarer 3D-Ansicht des markierten Teils (siehe unten). Bei mehreren Dateien wechseln "
            "die Pfeil-Knöpfe oben zwischen den Dateien (<i>Datei 2 von 7: …</i>). Dort je Teil festlegen, ob es "
            "übernommen wird, und Profil, Werkstoff und Stückzahl wählen. <b>Übernehmen</b> legt die Positionen "
            "aller Dateien an, <b>Abbrechen</b> verwirft die Messung.",
            "Enthält eine STEP mehrere Teile, steht sie als <b>Baugruppe</b> in der Liste und die 3D-Ansicht zeigt "
            "sie zusammengebaut. Oben steht das Feld <b>Sätze</b>, vorbelegt mit 1: die Baugruppe wird ein Satz; "
            "leer = jedes Teil als Einzelposition (siehe Baugruppen als Satz).",
            "Fehlen Profile in den Stammdaten, fragt das Programm, ob sie aus den Messwerten angelegt werden sollen "
            "(danach im Reiter <i>Profile</i> prüfen). Stehen Artikel schon im Angebot, fragt es vor dem doppelten "
            "Eintragen.",
            "Am Ende meldet es, wie viele Positionen übernommen wurden; <i>Details</i> zeigt den Bericht je Datei.",
            nummeriert=True)
    i.abschnitt("Rohrliste prüfen")
    i.bild("step_pruefen", "STEP-Import prüfen: eine Datei je Ansicht, Eingaben je Teil und 3D-Ansicht",
           hoehe=100 * mm, legende=[
               (1, "Pfeil-Knöpfe links/rechts: zwischen den STEP-Dateien wechseln; daneben Nummer und Name der Datei."),
               (2, "Rohrliste der Datei: Häkchen, Profil-ID, Werkstoff-ID und Stückzahl je Teil."),
               (3, "Werkstoff und Stückzahl für alle oder die markierten Zeilen setzen.")])
    i.text("Rote Gruppenzeile = Profil fehlt in den Stammdaten (wird beim Übernehmen angelegt). Gelber Hinweis = "
           "prüfen. Abgewählte Teile werden nicht übernommen. Spalte <b>Art</b>: Bauteilart umstellen, wenn falsch "
           "erkannt.", kurz=True)
    i.genauer()
    i.liste("Jede Zeile ist ein Teil. Gleiche Teile aus einer Datei (Baugruppe) stehen in einer Zeile; die Spalte "
            "<b>In Datei</b> zeigt, wie oft es in der Datei vorkommt.",
            "Die Spalte <b>Art</b> zeigt die erkannte Bauteilart und ist bei jeder Zeile eine Auswahl. Bei "
            "Flachstahl/Blech und Profil/Kantteil steht dort zuerst die andere Messung (siehe Bleche beim "
            "STEP-Import). Bei Rohren und Profilen kann jede andere Profilform gewählt werden: Die Messwerte bleiben, "
            "Profil-ID zeigt dann die Profile dieser Form, der Hinweis nennt die gemessene Form.",
            "Die Teile sind nach gemessenem Profil gruppiert. Eine rote Gruppenzeile heißt: dieses Profil steht nicht in "
            "den Stammdaten (beim Übernehmen fragt das Programm, ob es angelegt werden soll).",
            "<b>Häkchen</b> vor dem Teil: übernehmen ja/nein. Abgewählte Teile stehen nur im STEP-Protokoll.",
            "<b>Profil-ID</b>: vorgeschlagen ist das passende Profil der Stammdaten. Ein anderes wählen oder eine neue "
            "ID eintippen, z. B. wenn ein Teil aus einem anderen Rohr gefertigt wird.",
            "<b>Werkstoff-ID</b> (nach Kategorie gruppiert) und <b>Stückzahl</b> je Teil; leer = später im Angebot eintragen. "
            "Vorbelegt sind bei Rohren und Profilen der Werkstoff aus der Einstellung <i>STEP-Import: Standard-Werkstoff</i> "
            "(Vorgabe S235-10219 = S235 EN10219) und bei Einzelteilen die Stückzahl 1. Bleche bekommen keinen Werkstoff "
            "vorbelegt. Ist oben eine Anzahl Sätze eingetragen, heißt die Spalte <b>Stück je Satz</b> (siehe Baugruppen "
            "als Satz).",
            "Für viele Teile auf einmal: unten Werkstoff und/oder Stückzahl wählen und <b>Für alle</b> klicken (gilt "
            "für alle Teile aller Dateien, die Stückzahl nur für Teile ohne Satz), oder Zeilen der gezeigten Datei "
            "markieren (Strg/Umschalt) und <b>Für markierte</b>. <b>Alle wählen</b> / <b>Keine wählen</b> setzen "
            "die Häkchen aller Dateien.",
            "<b>3D-Schnittbearbeitung aktivieren</b> (seit 0.8.19, unter <i>Werte setzen</i>, gilt für alle Teile): "
            "3D heißt: die Schnittfläche steht nicht senkrecht (90°) zur Rohroberfläche. Der Import misst dafür an "
            "jedem Ende und jeder Kontur den Winkel zwischen Schnittfläche und Oberfläche (ab 0,5° = 3D). Eine "
            "Gehrung, die im CAD als ebene Fläche gezeichnet ist, steht an den schräg geschnittenen Wänden nicht "
            "senkrecht und ist damit 3D; ist sie so gezeichnet, wie ein 2D-Laser schneidet (überall senkrecht zur "
            "Wand), bleibt sie 2D. Schräge Langlöcher und Ausschnitte bekommen nur „3D prüfen“. Mit Häkchen werden "
            "Gehrungen an den Enden, die nicht senkrecht zur Oberfläche stehen, und schräge Bohrungen (Achse ab 0,5° gegen die Wand geneigt) werden in 3D "
            "übernommen, die Bohrungen mit gemessener Neigung längs und quer. Daneben steht, wie viele Gehrungen und "
            "schrägen Bohrungen gefunden wurden. Ohne Häkchen bleibt alles 2D; Teile mit schrägen Bohrungen bekommen "
            "im Bericht „3D prüfen“. Fasen werden nie in 3D gerechnet. Über der Grenze der Maschine wird begrenzt "
            "(WARNUNG im Status). Ändern je Teil im Schneidweg-Rechner ([[schneidweg_rechner]]); bei Rundrohren ist "
            "die gemessene Querneigung auf etwa ±1,5° genau.",
            "<b>Fasen an den Enden</b> (seit 0.8.27): Eine Fase am Rohrende wird nicht gelasert. Der Import erkennt "
            "sie, schreibt den Hinweis „Ende B: Fase erkannt …“ in den Bericht und nimmt Länge und Schneidweg an der "
            "längsten Stelle an: Länge = längste Länge des Teils, Endschnitt = gerader Schnitt an der Außenkontur. "
            "Das Teil bleibt <i>plausibel</i> und wird ohne Häkchen-Prüfung übernommen.",
            "Teile, die nicht gemessen werden konnten, stehen unten unter <i>Nicht übernehmbar</i>. Die Zeile nennt "
            "den Grund und das Hüllmaß des Körpers (zum Wiederfinden im CAD). In der 3D-Baugruppe sind diese Teile "
            "<b>magenta</b>; ein Klick auf die Zeile hebt das Teil blau hervor, ein Klick auf <i>Nicht übernehmbar</i> "
            "alle. So sieht man, welches Teil fehlt und wo es sitzt.",
            "<b>Von Hand nachtragen</b>: Unter jedem nicht übernehmbaren Teil steht die Zeile <i>Von Hand "
            "nachtragen</i>. Profilform wählen, bei Profil-ID ein Profil der Stammdaten wählen oder eine neue ID "
            "eintippen (z. B. QR 40x40x3, die Maße kommen dann aus dem Namen) und <b>Nachtragen</b> klicken. Das Teil "
            "wandert in die Profilgruppe: Länge = größtes Hüllmaß, zwei gerade Enden, Prüfstatus "
            "<i>prüfen</i>, angehakt. Gleiche nicht übernehmbare Körper der Datei (gleiches Hüllmaß) werden mit "
            "nachgetragen. Hat die Messung Konturen in Längsrichtung gefunden (Länge passt zum Hüllmaß), bleiben sie "
            "samt Schneidweg erhalten, sonst Bohrungen und Ausschnitte im Schneidweg-Rechner ergänzen. Auch wenn "
            "man im Angebot später das Profil einer STEP-Position ändert, rechnet der Schneidweg-Rechner beim Öffnen "
            "die Konturen für das neue Profil um (Hinweis <i>Profil geändert</i>). In der Spalte Art macht "
            "<i>Nachtrag zurücknehmen</i> das rückgängig.")
    i.bild("step_positionen", "Übernommene Positionen mit eingeblendeten STEP-Werten", hoehe=125 * mm, legende=[
        (1, "<b>STEP-Werte</b> zeigt Anfangs-/Endschnitt, Innenkonturen nach Größe, Gravur, Bohrungen und den "
            "Gewinde-Vorschlag.")])
    i.hinweis("Gewinde, Senkungen, Fließlochbohrungen und Bohrungen kleiner als 0,7 × Wandstärke werden nur "
              "vorgeschlagen (Status HINWEIS: Bohrungen prüfen (Doppelklick)). Gerechnet werden Gewinde und die "
              "Arbeitsschritte Senken, Flowdrill und Bohren erst, wenn sie im Fenster <b>Bohrungen prüfen</b> "
              "bestätigt sind ([[bohrungen_pruefen]]).", kurz=True)
    i.abschnitt("Bohrungen prüfen: Gewinde, Senken, Flowdrill, Bohren", marke="bohrungen_pruefen")
    i.text("Doppelklick auf den Status <b>HINWEIS: Bohrungen prüfen (Doppelklick)</b>, je Zeile <b>Bestätigen</b> oder "
           "<b>Ablehnen</b>, dann <b>Übernehmen</b>. Erst bestätigte Gewinde und Arbeiten werden gerechnet.", kurz=True)
    i.bild("bohrbild_dialog", "Fenster Bohrungen prüfen: Senkung und Flowdrill eines Rechteckrohrs", hoehe=70 * mm,
           legende=[
               (1, "Je Zeile Art, Ø, Anzahl je Teil, Gewinde (änderbar), Preis je Gewinde und je Arbeit (grau = "
                   "Einstellungen, änderbar), was der Laser macht und Bestätigen/Ablehnen."),
               (2, "<b>Alle bestätigen</b> setzt alle Zeilen auf bestätigt."),
               (3, "Gewinde ohne Zeile (z. B. aus der Zeichnung) von Hand ergänzen, z. B. <i>2xM10</i>."),
               (4, "Auswirkung je Teil: Schneidweg, Gravur, Einstiche und Gewinde vorher → nachher, dazu die "
                   "Zusatzarbeiten (z. B. 2× Senken, 4× Bohren).")])
    i.genauer()
    i.text("Der STEP-Import und der Schneidweg-Rechner erkennen vier Arten von Bohrungen, die nach der Zeichnung "
           "geprüft werden müssen:")
    i.liste("<b>Bohrung mit Gewinde-Vorschlag</b>: der Ø passt zum Kernloch eines Gewindes der Stammdaten "
            "(z. B. Ø 5 → M6). Der Laser schneidet die Bohrung; das Gewinde wird erst nach dem Bestätigen gerechnet.",
            "<b>Senkung</b>: Bohrung mit Kegel (z. B. Ø 6,6 / 12,4). Der Laser schneidet die Bohrung Ø 6,6, die "
            "Senkung selbst ist Nacharbeit. Auf Wunsch wird der Senk-Ø als Gravur eingerechnet (Häkchen "
            "<i>Senk-Ø gravieren</i>, je Senkung π × Senk-Ø).",
            "<b>Flowdrill (Fließlochbohrung)</b>: Bohrung mit Kragen. Der Laser macht nur eine Markierung, je nach "
            "Auswahl eine <i>Gravur Ø0,5</i> oder ein <i>Loch Ø0,5</i> (Schneidweg und Einstich). Die Vorgabe steht in "
            "der Einstellung <i>STEP-Import: Flowdrill-Bohrung am Laser</i>. Das Gewinde wird nach dem "
            "Kernloch fürs Gewindeformen vorgeschlagen (z. B. Ø 7,3 → M8). <b>Ablehnen</b> heißt: es ist eine "
            "normale Bohrung, die der Laser schneidet.",
            "<b>Bohren</b>: Bohrung kleiner als 0,7 × Wandstärke (z. B. Ø 5 in 8 mm Wand, Grenze 5,6 mm), die der "
            "Laser kaum sauber schneidet ([[konturklassen]]). <b>Bestätigen</b> heißt: der Laser markiert nur "
            "(Gravur Ø0,5 oder Loch Ø0,5 wie beim Flowdrill, die Bohrung fällt aus Schneidweg und Konturliste), "
            "danach wird aufgebohrt. <b>Ablehnen</b> heißt: der Laser schneidet die Bohrung trotzdem, die Warnung "
            "<i>Kontur kleiner als 0,7 × Wandstärke</i> entfällt. Die Markierung Ø0,5 selbst wird nie vorgeschlagen.")
    i.text("<b>Arbeitsschritte als Zusatzarbeit:</b> Bestätigte Senkungen, Flowdrill und Bohren trägt "
           "<b>Übernehmen</b> als Zusatzarbeit <i>Senken</i>, <i>Flowdrill</i> bzw. <i>Bohren</i> mit der Anzahl je "
           "Teil in die Position ein (Spalte <i>Zusatzarbeiten</i>, Preisstand der Stammdaten, "
           "[[zusatzarbeiten_angebot]]). Offene und abgelehnte Zeilen tragen nichts ein; wird eine Zeile später "
           "abgelehnt, fällt die Zusatzarbeit wieder weg. Steht dieselbe Zusatzarbeit schon von Hand in der Position, "
           "bekommt sie nur die neue Anzahl. Die drei Zusatzarbeiten legt das Programm einmalig mit Beispielpreisen "
           "je Stück an (Senken 0,40 €, Flowdrill 0,60 €, Bohren 0,40 €, ohne Zeiten); die Preise in "
           "Einstellungen › Zusatzarbeiten anpassen ([[zusatzarbeiten_verwalten]]). Fehlt eine davon in den "
           "Stammdaten, meldet das Fenster es rot.")
    i.text("<b>Preise je Stück:</b> Gewinde, Senken, Flowdrill und Bohren rechnen nur mit einem Preis je Stück, "
           "nie mit Zeiten. Vorgabe sind die Preise aus Einstellungen › Gewinde bzw. › Zusatzarbeiten; sie stehen "
           "grau in den Spalten <i>Gewinde [€/Stk]</i> und <i>Arbeit [€/Stk]</i>. Ein eingetragener Preis gilt nur "
           "für diese Position (z. B. Sonderpreis); leeren holt wieder die Einstellungen. Die Auswirkung zeigt den "
           "Betrag je Teil. Ein Gewinde ohne Preis rechnet mit 0 € und die Position meldet <i>WARNUNG: Gewinde … "
           "ohne Preis je Stück</i>.")
    i.text("Positionen mit offenen Bohrungen zeigen den Status <b>HINWEIS: Bohrungen prüfen (Doppelklick)</b>. Ein "
           "<b>Doppelklick</b> auf den Status, die Spalte <i>Gewinde geprüft</i>, <i>Bohrungen</i> oder "
           "<i>Gewinde-Vorschlag</i> öffnet das Fenster (auch Rechtsklick, <i>Bohrungen prüfen …</i>). Je Zeile "
           "<b>Bestätigen</b> oder <b>Ablehnen</b>; <b>Übernehmen</b> ändert Schneidweg, Einstiche, Gravur, "
           "Konturklassen, <i>Gewinde geprüft</i> und die Zusatzarbeiten der Position. Das Fenster lässt sich jederzeit wieder öffnen "
           "und die Wahl ändern.")
    i.bild("step_protokoll", "Reiter STEP-Protokoll: alle Messwerte je Datei und Körper; Doppelklick auf eine Zeile "
           "springt zur Position", hoehe=80 * mm, kurz=False)
    i.bild("step_optimiert", "Aus STEP übernommene Positionen nach dem Optimieren: Schneidweg, Einstiche und "
           "Schneidzeit kommen aus der Messung", hoehe=110 * mm, kurz=False)
    i.abschnitt("3D-Ansicht", marke="step_3d_ansicht")
    i.text("<b>3D-Ansicht …</b> zeigt die STEP-Teile drehbar: Anfangsschnitt orange, Endschnitt violett, "
           "Innenkonturen rot, Gravur grün. Linke Maustaste drehen, Mausrad zoomen, Doppelklick zurück. Große "
           "Baugruppen zeigt die Ansicht beim Drehen und Zoomen vereinfacht (ohne kleine Rundungen, Bohrungen und "
           "Linien), damit sie flüssig bleibt; beim Loslassen wieder vollständig.", kurz=True)
    i.bild("step_3d", "3D-Ansicht der Positionen (Knopf 3D-Ansicht …)", hoehe=95 * mm, legende=[
        (1, "Feste Blickrichtungen: <b>Schräg</b>, <b>Vorn</b>, <b>Oben</b> und <b>Stirnseite</b>.")])
    i.genauer()
    i.text("Jedes per STEP-Import angelegte Teil wird mit seinem 3D-Modell gespeichert. In der Positionsliste steht "
           "neben der Artikelnummer ein kleines Vorschaubild. Selbst angelegte Teile bekommen ebenfalls ein Bild: "
           "Rohre und Profile die Draufsicht (oder die Seitenansicht, wenn sie mehr zeigt) mit Gehrungen und "
           "Innenkonturen aus dem Schneidweg-Rechner, Blech- und Kantteile den Zuschnitt aus dem Blech-Editor. "
           "Ändert sich das Teil im Editor oder eine neue STEP-Datei, wird das Bild neu gezeichnet. Doppelklick "
           "aufs Bild öffnet den passenden Editor ([[schneidweg_rechner]], [[blech_editor]]). <b>3D-Ansicht …</b> in der Knopfleiste des Angebots "
           "öffnet alle Positionen mit großer Ansicht, beginnend mit der markierten Zeile. Beim Kopieren eines "
           "Angebots gehen die 3D-Modelle mit.")
    i.liste("Linke Maustaste ziehen: drehen. Rechte oder mittlere Maustaste ziehen: verschieben. Mausrad: zoomen. "
            "Doppelklick: zurück zur Ausgangsansicht.",
            "Farben: Außenwand grau, Innenwand dunkelgrau, <b>Anfangsschnitt orange</b>, <b>Endschnitt violett</b>, "
            "<b>Innenkonturen rot</b>, <b>Gravur grün</b>. So ist auf einen Blick zu sehen, was die Messung als "
            "Schneidweg zählt.",
            "Positionen ohne STEP-Import (von Hand angelegt) haben keine 3D-Ansicht.",
            "Die Ansicht zeichnet mit der Grafikkarte (OpenGL), wenn der Rechner das kann; dann bleiben auch große "
            "Baugruppen beim Drehen fein. Sonst und über Remote-Desktop zeichnet sie wie bisher ohne Grafikkarte. "
            "Einstellen unter Vorgaben, Gruppe Ansicht, <i>3D-Ansicht: Darstellung</i> ([[einstellungen]]).")
    i.hinweis("Der STEP-Import misst schneller als früher. Bei vielen Dateien (ab 6) misst er auf mehreren "
              "Prozessorkernen gleichzeitig.")
    i.abschnitt("Biegerohre", marke="biegerohre")
    i.text("Ein <b>gebogenes Rundrohr</b> (Geraden und Bögen) erkennt der Import selbst. Er rechnet die gestreckte "
           "Länge, setzt die Bohrungen an die richtige Stelle am geraden Rohr und liefert die Biegedaten. Der "
           "Prüfstatus ist immer <i>prüfen</i>. Rahmen aus Einzelrohren mit Gehrung werden auf Wunsch ein Knickrahmen "
           "([[knickverbindung]]).", kurz=True)
    i.bild("biegerohr_rechner", "Biegerohr im Schneidweg-Rechner: Abwicklung des gestreckten Rohrs mit den "
           "Biegezonen", hoehe=110 * mm, legende=[
               (1, "Gruppe <b>Biegungen</b>: je Biegung L (Gerade davor), R (Drehung der Biegeebene), A (Winkel) und "
                   "Radius, dazu gestreckte Länge und die Eckpunkte XYZ."),
               (2, "<b>Biegezonen</b> schraffiert mit Nummer und Winkel, Bohrungen am gestreckten Rohr."),
               (3, "Prüfmeldung <b>Kontur in der Biegezone</b>.")])
    i.genauer()
    i.liste("<b>Erkennung</b>: Außenmantel aus Zylindern (Geraden) und Tori (Bögen) mit gleichem Rohrradius und einem "
            "Biegeradius größer als der Rohrradius. Aus den Achsen und Mittenkreisen entsteht die <b>Mittellinie</b>; "
            "Außen-Ø und Wand kommen aus den Radien.",
            "<b>Gestreckte Länge</b> = Summe der Geraden + Faktor × Summe der Bögen (Radius × Winkel). Der Faktor ist "
            "die Lage der neutralen Faser, Vorgabe 1,0 = Rohrmitte. Einstellung <i>Biegerohr: Faktor neutrale Faser "
            "für die gestreckte Länge (1,0 = Rohrmitte)</i> unter STEP-Import ([[einstellungen]]); er gilt beim "
            "Übernehmen.",
            "<b>Konturen</b>: Lage x ab Ende A am gestreckten Rohr, Winkel um die Rohrachse (0° = Innenseite der "
            "ersten Biegung). Liegt eine Kontur in einem Bogen, meldet die Fertigungsprüfung <i>Kontur in der "
            "Biegezone</i>; eine zu kurze Gerade zwischen zwei Biegungen meldet <i>Gerade zwischen Biegungen zu "
            "kurz</i> (Vorgabe 1,5 × Außen-Ø, [[pruefregeln]]).",
            "<b>Biegedaten</b>: LRA je Biegung (L = Gerade davor, R = Drehung der Biegeebene gegen die vorige, A = "
            "Biegewinkel) und XYZ = Eckpunkte der verlängerten Geraden ab Ende A. Sie stehen im Teile-Editor "
            "([[teile_editor]]) und im Messergebnis (JSON).",
            "<b>Zusatzarbeit Biegen</b>: € je Biegung (Beispielpreis 1,50 €, Stammdaten Zusatzarbeiten); der Import "
            "trägt die Zahl der Biegungen als Menge ein.")
    i.abschnitt("Bleche erkennen", marke="bleche")
    i.text("Bleche erkennt der Import selbst. Sie werden nicht gelasert, sondern <b>Zukaufteil-Positionen</b> mit "
           "einem Blechartikel; im Prüfdialog stehen sie in der grünen Gruppe <b>Bleche (Zukaufteile, nicht "
           "lasern)</b>. Werkstoff wählen, dann gibt es einen Richtpreis.")
    i.genauer()
    i.text("Vor der Profilmessung prüft der STEP-Import, ob ein Körper ein <b>Blech</b> ist. Ein Blech hat zwei "
           "parallele Hauptflächen, ist überall gleich dick (das Volumen entspricht Hauptfläche × Dicke) und ist "
           "höchstens ein Fünftel so dick wie breit. Bohrungen, Ausschnitte, Langlöcher, Fasen und eine freie "
           "Außenkontur sind erlaubt.")
    i.liste("<b>Dicke</b> = Abstand der beiden Hauptflächen. Sie stimmt auch, wenn das Blech im Modell gedreht "
            "oder schräg liegt (nicht einfach die kleinste Kante des Hüllquaders).",
            "<b>Länge und Breite</b> = kleinstes Rechteck, das die Außenkontur umschließt. Die Kontur heißt "
            "<i>rechteckig</i> oder <i>frei</i> (z. B. schräge Ecke). Dazu kommen die Innenkonturen mit Art "
            "(Bohrung, Langloch, Rechteck, sonst Polygon), Maßen und <b>Lage</b> (Mitte x längs ab der linken, y "
            "quer ab der unteren Kante des Zuschnitts) und bei freier Kontur ihre Eckpunkte.",
            "<b>Flachstahl oder Blech</b>: Ebene flache Teile (auch mit Bohrungen und Senkungen) erkennt der Import "
            "als <b>Blech</b> (Einstellung <i>STEP-Import: ebene flache Teile vorgeben als</i>, Vorgabe Blech). "
            "Flachstahl ist in der Spalte <b>Art</b> bei jedem flachen Teil wählbar und wird dann wie ein Rohr "
            "übernommen und kalkuliert. Steht die Einstellung auf <i>Flachstahl bis Breite</i>, gilt die alte "
            "Abgrenzung: Flachstahl, wenn das Teil höchstens so breit ist wie in <i>STEP-Import: Flachstahl bis "
            "Breite</i> (Vorgabe 150 mm), mindestens dreimal so lang wie breit ist und gerade Längsseiten hat; alles "
            "andere Flache ist ein Blech.",
            "<b>Gekantete Bleche</b> (gleich dicke Schenkel mit Biegeradien oder scharfen Kanten) heißen <i>Blech "
            "gekantet</i>, immer mit Prüfstatus <i>prüfen</i>. Der Import wickelt das Teil ab (k = 0,33, scharfe "
            "Kante: Innenradius = Blechdicke): Zuschnitt, Schenkel-Außenmaße, Biegelinien, alle Innenkonturen und "
            "der Schneidweg kommen aus der Abwicklung. Auch mehrachsig gekantete Teile (Schale, Kasten) werden "
            "abgewickelt, der Zuschnitt ist dann ein Polygon mit gezählten Kantungen. Ein Kantteil mit "
            "gleichbleibendem Querschnitt über die ganze Länge bleibt ein L-, U- oder C-Profil, weil es als "
            "Stangenmaterial auf dem Rohrlaser geschnitten werden kann; als Art lässt sich <i>Kantteil</i> wählen. "
            "Ist es scharfkantig gezeichnet (ohne Biegeradien), ist im Prüfdialog das Profil nur vorbelegt, wenn "
            "ein passendes Profil in den Stammdaten steht, sonst das Kantteil.",
            "<b>Art umstellen, wenn falsch erkannt</b>: Bei Grenzfällen misst der Import das Teil in beiden Arten. "
            "Grenzfälle sind alle flachen Teile (Flachstahl oder Blech) und alle Teile mit Biegezonen (L-, U-, "
            "C-Profil oder Kantteil). Im Prüfdialog steht dann in der Spalte <b>Art</b> eine Auswahl, vorbelegt mit "
            "dem Erkannten. Wird die andere Art gewählt, wandert die Zeile in die passende Gruppe. Profil bzw. "
            "Zukaufartikel und Werkstoff werden neu vorbelegt (Blech: Werkstoff leer), die Stückzahl bleibt. Lässt "
            "sich ein Teil in der anderen Art nicht messen, z. B. ein Kantteil mit ungleichen Schenkeln als "
            "L-Profil, steht <i>Ersatzwerte</i> dabei. Die Werte kommen dann aus den Blechmaßen (Länge × Breite, "
            "Schnitte nur an den Enden), das Teil ist nicht angehakt und muss geprüft werden.",
            "Eine dünne Platte mit Tasche oder Absatz ist <b>kein Blech</b> (nicht überall gleich dick) und steht mit "
            "Prüfstatus <i>prüfen</i> da.",
            "Bleche sind keine Rohrlaserteile und werden nie als Profil übernommen. Sie werden <b>Zukaufteil-"
            "Positionen</b> ([[zukauf_positionen]]) mit einem Zukaufartikel vom Typ Blech ([[blechartikel]]). Rohre derselben "
            "Baugruppe werden wie gewohnt übernommen.",
            "Im Dialog STEP-Import prüfen stehen die Bleche je Datei in der grünen Gruppe <b>Bleche (Zukaufteile, "
            "nicht lasern)</b>; gleiche Bleche einer Datei stehen in einer Zeile. In der Spalte Profil-ID wird hier "
            "der <b>Zukaufartikel</b> gewählt: <i>automatisch</i> nimmt einen gleichen vorhandenen Blechartikel "
            "(Dubletten: gleiche Maße, Dicke, Werkstoff und Kontur) oder legt einen neuen ohne Einkaufspreis an; "
            "darunter stehen gleiche und ähnliche Artikel zur Wahl. Die Hinweis-Spalte nennt <i>vorhanden</i>, "
            "<i>ähnlich</i> oder <i>neuer Zukaufartikel, EK fehlt</i>.",
            "Der <b>Werkstoff</b> eines Blechs ist leer (offen), bis er in der Zeile gewählt wird; die Vorgabe für "
            "die Rohre gilt nicht für Bleche. Zur Wahl stehen die <b>Blech-Werkstoffe</b> des Blech-Editors "
            "([[blech_stammdaten]]), nicht die Rohr-Werkstoffe. Mit Werkstoff bekommt ein neuer Blechartikel den "
            "<b>Blech-Richtpreis</b> als EK (gerechnet wie im Blech-Editor, [[blech_editor]]). Ohne Werkstoff heißt "
            "der neue Artikel z. B. <i>Blech 400 × 200 × 4 mm (Werkstoff offen)</i>, die Position hat kein Gewicht "
            "und der EK fehlt.",
            "Jedes übernommene Blech trägt seine Maße als Eingaben des Blech-Editors: Zuschnitt (Hüllrechteck, "
            "freie Außenkontur als Polygon, gekantet mit der Abwicklungsfläche) und jede Innenkontur als eigene "
            "Zeile an ihrer Stelle (Mitte x/y), so wie sie im Modell sitzt; Skizze und Vorschaubild zeigen das Teil "
            "wie in der STEP-Datei. Gekantete Bleche haben noch keine Konturen mit Lage. <b>Doppelklick aufs Bild</b> vor der Artikelnummer öffnet den Blech-Editor (dort z. B. "
            "ein gekantetes Teil als Kantteil mit Schenkeln nachtragen), Doppelklick auf die Nummer die 3D-Ansicht.",
            "Bleche mit Prüfstatus <i>prüfen</i> (z. B. gekantete) sind nicht angehakt und werden erst nach "
            "Anhaken übernommen. Ein Blech, dessen Artikelnummer schon im Angebot steht, wird übersprungen; ein "
            "erneuter Import legt keinen zweiten Zukaufartikel an.",
            "Ist die STEP-Datei eine Baugruppe (z. B. Rohr mit zwei Laschen), zählt sie mit den Blechen als "
            "mehrteilig: mit <i>Sätze</i> werden Rohr und Bleche ein Satz, gleiche Bleche eine Position mit "
            "Stück je Satz.",
            "Neue Zukaufartikel bekommen Kategorie Blechteile, Einheit Stück, Lieferant Technik, die STEP-Datei und "
            "die Geometrie-Kennung. Der Bericht nennt die Anzahl; den Einkaufspreis (statt des Richtpreises bzw. "
            "wenn er fehlt) direkt im Angebot mit "
            "<b>Zukaufteile … → EK eintragen …</b> (mit Stückzahl, [[zukauf_positionen]]) oder unter Zukaufartikel mit "
            "<b>EK eintragen …</b> nachtragen (Filter <i>EK fehlt</i>).",
            "In den Messwerten stehen die Spalten <i>bauteiltyp</i> (Profil, Blech, Blech gekantet) und <i>blech</i> "
            "(alle Blechmaße). Im JSON-Messergebnis (ab Version 1.1) steht je Blech der Block <i>blech</i>; die "
            "Profilwerte (Querschnitt, Wandstärke) sind dort <i>null</i>. Ab Version 1.2 steht bei Grenzfällen der "
            "Block <i>alternative</i> (das Teil in der anderen Art) und <i>ersatzwerte</i> (true = abgeleitet, "
            "nicht gemessen).")
    i.abschnitt("Baugruppen als Satz")
    i.text("Mehrere Teile in einer STEP-Datei = <b>Baugruppe</b>. Feld <b>Sätze</b> (Vorgabe 1): gleiche Teile werden "
           "eine Position mit <b>Stück je Satz</b>; leer = jedes Teil einzeln.", kurz=True)
    i.bild("step_satz_pruefen", "Baugruppe im Prüfdialog: 4 Sätze eingetragen", hoehe=80 * mm, legende=[
        (1, "<b>Sätze</b>: Anzahl Sätze (Vorgabe 1); leer = Einzelpositionen. Rechts daneben der Satzname."),
        (2, "Die Baugruppe mit ihren Teilen; die Spalte zeigt <b>Stück je Satz</b>."),
        (3, "3D-Ansicht der zusammengebauten Baugruppe, gleiche Teile in gleicher Farbe.")])
    i.bild("step_satz_positionen", "Baugruppe als Satz: 3 gleiche Quadratrohre und 1 Rundrohr, 4 Sätze",
           hoehe=110 * mm, legende=[(1, "Spalten <b>Satz</b>, <b>Stück je Satz</b> und <b>Stückzahl</b>.")])
    i.genauer()
    i.text("Liegen in einer STEP-Datei mehrere Teile, zeigt der Dialog STEP-Import prüfen sie als Baugruppe:")
    i.liste("Oberste Zeile <b>Baugruppe „Name“</b> mit Anzahl Teile, Anzahl verschiedener Teile und Sätzen; "
            "darunter die Teile nach Profil gruppiert (Bleche in ihrer eigenen Gruppe).",
            "Die 3D-Ansicht zeigt die ganze Baugruppe zusammengebaut. Die Lage jedes Teils kommt aus der STEP-Datei. "
            "Gleiche Teile haben dieselbe Farbe; das farbige Quadrat vor dem Teil in der Liste zeigt sie.",
            "Klick auf eine Profilgruppe: die Baugruppe mit diesen Teilen blau, den Rest hellgrau. Klick auf ein "
            "Teil: das Einzelteil mit Schnitten und Konturen. Klick auf die Baugruppen-Zeile: wieder alles.")
    i.text("Das Feld <b>Sätze</b> oben ist mit <b>1</b> vorbelegt, die Baugruppe wird also ein Satz. Ist eine "
           "Anzahl eingetragen:")
    i.liste("Der Satz heißt wie die Datei (ohne Endung) und steht in der Spalte <b>Satz</b> jeder Position.",
            "Gleiche Teile (gleiche Maße, Konturen und Bohrungen, Lage im Raum egal) werden eine Position; "
            "<b>Stück je Satz</b> ist ihre Anzahl in der Baugruppe.",
            "Die Spalte der Rohrliste heißt dann <b>Stück je Satz</b> (vorgegeben: Anzahl in der Baugruppe, "
            "änderbar). Stückzahl der Position = Sätze × Stück je Satz.",
            "Das STEP-Protokoll zeigt weiter jeden Körper, die gleichen mit dem Hinweis <i>gleich wie …</i>.")
    i.text("Wird das Feld <b>geleert</b> (auf 0), wird jeder Körper eine eigene Position ohne Satz, mit der Stückzahl aus "
           "der Rohrliste. Bei mehreren Dateien gilt das Feld je Datei. Staffelpreise und Angebot rechnen den Satz "
           "wie einen von Hand angelegten ([[staffeln]]).")
    i.text("Neben dem Feld steht das Häkchen <b>als Schweißbaugruppe</b> (nur mit Sätzen, Vorgabe aus). Damit wird "
           "der Satz zusätzlich eine Position der Art Schweißbaugruppe ([[schweissbaugruppe]]): die Unterbaugruppen "
           "mit ihrer Menge kommen aus der Struktur der STEP-Datei, jedes Teil steht in seiner Unterbaugruppe mit "
           "Stück je Unterbaugruppe. Liegen gleiche Teile in mehreren Unterbaugruppen, hängen sie direkt an der "
           "Baugruppe (Hinweis im Bericht, Stückzahl stimmt). Nahtgruppen und Arbeitsgänge legt der Import nicht an: "
           "die STEP-Datei kennt keine Nähte, also im Editor ergänzen.")
    i.text("Liefert der Kunde Unterbaugruppen als eigene Dateien, alle zusammen einlesen und bei der Unterbaugruppe "
           "rechts neben dem Häkchen statt <i>eigene Baugruppe</i> den Eintrag <b>in Baugruppe „…“</b> wählen. Die "
           "Datei wird dann eine Unterbaugruppe der anderen Schweißbaugruppe (mit ihrer eigenen Struktur darunter); "
           "<i>Sätze</i> gilt bei ihr als Stück je übergeordneter Baugruppe. Die andere Datei wird dabei selbst "
           "Schweißbaugruppe. Es entsteht nur eine Baugruppen-Position; der Bericht nennt die eingehängten Dateien.")
    i.abschnitt("Bauteilnamen, Normteile und Importprofile", marke="importprofile")
    i.text("Hat die Konstruktion Namen, wird der <b>Bauteilname</b> die Artikelnummer. <b>Normteile</b> (Schrauben, "
           "Muttern …) sind abgewählt. Ein <b>Importprofil</b> legt das je Kunde fest.", kurz=True)
    i.genauer()
    i.liste("Die Messung liest die Baugruppenstruktur und die Namen der Bauteile aus der STEP-Datei. Wie die "
            "Artikelnummer entsteht, steht in der Einstellung <i>Artikelnummer aus (Bauteilname, Dateiname oder "
            "beides)</i> (Vorgabe Bauteilname). Ohne Namen in der Datei bleibt es wie bisher beim Dateinamen mit "
            "Körpernummer (<i>Gestell-K3</i>). Der Tooltip auf dem Artikel im Prüfdialog zeigt die Lage in der "
            "Baugruppe, z. B. <i>Gestell/Rahmenseite[2]/Strebe</i>.",
            "Steht im Bauteilnamen ein Begriff aus der Einstellung <i>Normteile: Begriffe im Bauteilnamen (mit ; "
            "getrennt)</i> als eigenes Wort (Vorgabe ISO, DIN, Schraube, Mutter, Scheibe, Stift, Niet, Normteil), "
            "ist das Teil ein Normteil. Es ist im Prüfdialog abgewählt (Hinweis <i>Normteil … – zum Übernehmen "
            "anhaken</i>) und steht im Bericht als nicht übernommen.",
            "Unterreiter <b>Importprofile (STEP)</b> in den Einstellungen: je Kunde eine Zeile. In Angeboten dieses "
            "Kunden gilt sie beim STEP-Import, leere Felder wie in den Einstellungen.")
    i.tabelle(["Importprofile (STEP)", "Bedeutung"], [
        ["<b>Kunde</b>", "Kundennummer; das Profil gilt in allen Angeboten dieses Kunden"],
        ["Artikel aus", "Bauteilname, Dateiname oder Dateiname + Bauteilname (leer = Einstellung)"],
        ["Artikelnummer im Namen (Muster)", "regulärer Ausdruck: sein erster Klammerausdruck (sonst der ganze "
                                            "Treffer) wird die Artikelnummer, der ganze Name die Bezeichnung der "
                                            "Position. Beispiel <i>^(\\d+)</i>: aus <i>4711 Strebe</i> wird Artikel "
                                            "4711, Bezeichnung <i>4711 Strebe</i>"],
        ["Normteile zusätzlich (Begriffe mit ; getrennt)", "weitere Wörter für Normteile dieses Kunden, z. B. "
                                                            "Kaufteil; Zukauf"],
        ["Werkstoff Rohre/Profile, Flache Teile als, Anbauteile nicht übernehmen",
         "Vorbelegung im Prüfdialog statt der Einstellungen <i>Standard-Werkstoff</i>, <i>ebene flache Teile "
         "vorgeben als</i> und des Häkchens für Anbauteile"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.bild("stamm_importprofile", "Einstellungen, Importprofile (STEP): je Kunde eine Zeile", hoehe=70 * mm)
    i.abschnitt("Prüfstatus und Messergebnis als Datei")
    i.text("<i>plausibel</i> = Messung stimmig, <i>prüfen</i> = bitte ansehen, <i>nicht messbar</i> = kein Profil "
           "erkannt. Unsichere Teile sind nicht angehakt.")
    i.genauer()
    i.liste("Jedes Teil bekommt einen <b>Prüfstatus</b>. <i>plausibel</i> heißt, dass die Messung in sich stimmig "
            "ist; eine Fertigungsfreigabe ist das nicht. <i>prüfen</i> bedeutet, dass es Hinweise gibt, ein Merkmal "
            "unsicher ist oder die Geometrie ungültig ist. <i>nicht messbar</i> heißt, dass kein Profil erkannt wurde. "
            "Im Dialog STEP-Import prüfen ist die Hinweis-Spalte bei <i>prüfen</i> gelb hinterlegt, und unter der "
            "Rohrliste steht der Prüfstatus des gewählten Teils.",
            "Ist ein Merkmal <b>unsicher</b> (z. B. Wandstärke nicht einheitlich), ist das Teil im Prüfdialog "
            "<b>nicht angehakt</b> und trägt den Hinweis <i>UNSICHER: … – zum Übernehmen anhaken</i>. Übernommen "
            "wird es erst, wenn es von Hand angehakt wird. Ohne Bestätigung steht im Bericht <i>nicht übernommen: "
            "Erkennung unsicher</i>.",
            "<b>Anderes Profil wählen</b> (Spalte Profil-ID): weicht der gemessene Querschnitt vom gewählten Profil "
            "ab (Maße ±0,3 mm, Wand ±0,15 mm, Fläche ±1,5 %), steht in der Hinweis-Spalte gelb eine <i>WARNUNG</i> mit "
            "den Werten aus der STEP-Datei und denen des Profils, ebenso im Bericht. Beim Übernehmen rechnet das "
            "Programm Anfangs- und Endschnitt mit der gemessenen Form für das gewählte Profil neu: gerade = "
            "Schnittlänge des Profils, Gehrung und Schrägschnitt zweiachsig mit den gemessenen Winkeln, 3D-Enden "
            "(Spitze aus mehreren Ebenen, Ausklinkung auf ein Rundrohr) aus den gemessenen Schnittflächen "
            "([[schneidweg_rechner]]). Auch die <b>Innenkonturen</b> gehen mit: Bohrungen, Langlöcher und Rechtecke "
            "rechnen mit ihren Maßen neu, eine Sonderkontur oder Gravur mit echtem Umriss wird auf den neuen "
            "Querschnitt übertragen (jeder Punkt bleibt auf seiner Wand an derselben Stelle, eine Ecke bleibt eine "
            "Ecke; der Teil auf einer breiteren Wand wird länger). Der Bericht nennt <i>Schneidweg alt → neu</i>. "
            "Lässt sich ein Ende oder eine Kontur nicht neu rechnen (z. B. sonstige Kontur, Wechsel auf ein offenes "
            "Profil), gilt die gemessene Länge mit Hinweis; im Schneidweg-Rechner ist die Zeile <b>gelb</b>.",
            "Bei jedem STEP-Import legt das Programm das vollständige Messergebnis als <b>JSON-Datei</b> in die "
            "Ablage: <i>&lt;Angebot&gt; STEP-Messung &lt;Datum Uhrzeit&gt;.json</i>. Der Pfad steht im Bericht. Die "
            "Datei enthält je STEP-Datei den Importstatus, die Einheit und die Meldungen. Je Körper kommen dazu "
            "Profiltyp, Außen- und Innenmaße, Wandstärke mit allen Einzelmessungen, Länge, Längsachse, Konturen "
            "mit Lage, Schnittwinkel, Prüfstatus, Warnungen und die Erkennungssicherheit je Merkmal. Werte, die "
            "nicht gemessen werden konnten, stehen als <i>null</i> darin, nie als 0 oder Schätzwert. Das Format "
            "trägt eine Versionsnummer (<i>schema_version</i>). Bei Baugruppen steht dort ab Version 1.13 auch die "
            "<b>Baugruppenstruktur</b> aus der STEP-Datei: Unterbaugruppen mit Menge, je Körper der Bauteilname "
            "aus der Konstruktion und sein Pfad (z. B. <i>Gestell/Rahmenseite[2]/Strebe</i>). Ab Version 1.14 kommen "
            "<b>Nahtkandidaten</b> dazu: je Paar sich berührender Teile eine mögliche Schweißnaht mit Länge (Umfang "
            "am Rohrende bzw. der Berührung), Stoßart (Kehlnaht, Stumpfnaht in einer Flucht, Ecknaht bei Gehrung) "
            "und Dicke der dünneren Wand. Sie sind nur ein Vorschlag mit Status <i>prüfen</i> für die "
            "Schweißbaugruppen.",
            "<i>STEP-Import.exe</i> kann auch ohne das Programm messen: <i>STEP-Import.exe --ausgabe messwerte.txt "
            "--json ergebnis.json Ordner</i>.")
    i.text("Wie die Messung Profil, Schneidweg, Konturen und Enden bestimmt, welche Fälle geprüft sind und wo die "
           "Grenzen liegen, steht im Anhang ([[step_messung]]).")


def kapitel_optimieren(i):
    i.kapitel("Optimieren und Kalkulation", marke="optimieren")
    i.text("<b>Optimieren</b> (F9) verteilt die Teile auf Stangen, prüft jede Stange gegen Überlast und rechnet den "
           "Preis. Danach steht die Übersicht grün auf <b>Optimierung abgeschlossen</b>; die Ergebnisse stehen in "
           "den Reitern <i>Kalkulation</i> und <i>Schnittplan</i>.", kurz=True)
    i.genauer()
    i.text("<b>Optimieren</b> verteilt alle gültigen Positionen auf Stangen, prüft jede Stange gegen Überlast und "
           "rechnet die Kalkulation. Danach zeigt die Übersicht <b>Optimierung abgeschlossen</b> (grün).")
    i.text("Das Angebot hat sieben Reiter: <i>Positionen</i>, <i>Kalkulation</i> (mit den Unterreitern "
           "<i>Kalkulation</i> und <i>Zeiten & Arbeitskosten</i>), <i>Zukaufteile</i>, <i>Schnittplan</i> (mit den "
           "Unterreitern <i>Schnittplan</i>, <i>Stangenbild</i> und <i>Auswertung</i>), <i>Staffeln</i>, "
           "<i>Nachkalkulation</i> und <i>STEP-Protokoll</i>. Strg+Bild↓/↑ blättert durch die sieben Reiter, die "
           "Unterreiter wählt ein Klick.")
    i.abschnitt("Automatisch optimieren")
    i.text("Entwürfe bis 100 Positionen optimieren sich kurz nach jeder Änderung selbst; F9 ist dann meist nicht "
           "nötig.", kurz=True)
    i.genauer()
    i.text("Ist ein Angebot im Vorgang <i>Entwurf</i> und hat es höchstens so viele aktive Positionen wie die "
           "Einstellung <i>Automatisch optimieren: Entwürfe bis Positionen (0 = aus)</i> (Vorgabe 100) und weniger "
           "als 500 Teile, optimiert das Programm etwa 0,8 Sekunden nach der letzten Änderung von selbst. Das "
           "Ergebnis ist dasselbe wie mit <b>Optimieren</b> (F9); die Statuszeile meldet <i>Automatisch optimiert</i>. "
           "Verschickte oder beauftragte Angebote, Angebote anderer Benutzer und der Lesemodus behalten ihren "
           "Schnittplan, bis Sie selbst optimieren. Klappt das automatische Optimieren nicht (z. B. eine Position "
           "passt auf keine Stange), steht der Grund nur in der Statuszeile, ohne Meldungsfenster; versucht wird es "
           "erst nach der nächsten Änderung wieder. Mit F9 sehen Sie die vollständige Meldung.")
    i.abschnitt("Regeln der Optimierung")
    i.text("Getrennt je Profil, Werkstoff, Oberfläche und Stangenlänge, nie gemischt. Endbeschnitt, Schnittverlust "
           "und Greiferrest werden abgezogen, gerade Enden teilen sich einen Schnitt.", kurz=True)
    i.genauer()
    i.liste("Je Profil + Werkstoff + Oberfläche + Stangenlänge getrennt, ohne Vermischung.",
            "Belegung einer Stange = Endbeschnitt + Teile + Trennschnitte + Schnittverlust des letzten Schnitts; "
            "der Greiferrest muss frei bleiben.",
            "<b>3D-Greifmaß</b>: hat das letzte Teil einer Stange eine 3D-Bearbeitung nahe seinem Ende B, muss sie "
            "mindestens das Greifmaß der Maschine (Vorgabe 300 mm) vom Stangenende entfernt sein. Hinter dem Teil "
            "bleibt dann statt des Greiferrests Greifmaß − Abstand der Bearbeitung vom Ende B frei (Gehrung in 3D an "
            "Ende B: das volle Greifmaß), nur wenn das mehr ist als der Greiferrest; beides zusammen wird nie "
            "abgezogen. Die Optimierung legt dafür nach Möglichkeit ein Teil ohne 3D ans Ende. Beispiel: 6.000 mm, "
            "Greiferrest 142 mm, 3D-Gehrung am Ende B des letzten Teils: nutzbar bis 5.700 statt 5.858 mm.",
            "Zwei Teile mit geraden, aneinanderliegenden Enden teilen sich einen Schnitt (einmal Schnittverlust, die "
            "Einstiche eines Endes gespart: bei Trägern und U-Profilen 4, beim T-Profil 2, sonst 1). Sonst zwei Schnitte mit dem Abstand aus <i>Maschinen</i>. Dafür wird die "
            "Reihenfolge der Teile gewählt; gewendet (Ende B nach vorn) wird ein Teil nie.",
            "<b>Gehrungen ineinander</b>: zwei schräge Enden mit bekannter Richtung (STEP-Import oder "
            "Schneidweg-Rechner) legt die Optimierung ineinander, indem sie Teile um die eigene Achse dreht "
            "(Rechteckrohr 0° und 180°, Quadrat- und Rundrohr 0°, 90°, 180°, 270°). Es bleiben zwei Schnitte; der "
            "Abstand aus <i>Maschinen</i> gilt senkrecht zur Schnittfläche an der engsten Stelle. Das geht auch bei "
            "verschiedenen Winkeln (z. B. 45° neben 20°), es spart dann weniger. Teile mit fester oder unbekannter "
            "Schweißnaht ([[schweissnaht]]) werden nicht frei gedreht; Teile mit fester Naht auf der Breitseite und "
            "auf der Schmalseite eines Rechteckrohrs kommen nie auf dieselbe Stange. Im Schnittplan steht dann "
            "<i>Gehrung ineinander</i> und die Lage (<i>normal</i> oder <i>gedreht 180°</i>). Steht im "
            "Schneidweg-Rechner die längste Seite auf <i>automatisch</i> (Vorgabe), nimmt das Programm sie aus "
            "<i>gekippt über</i> an und die Optimierung legt frei drehbare Teile (Schweißnaht ohne Vorgabe) "
            "ineinander: gedreht passen sie in jeder Lage gleich gut, nur die Drehangabe ist dann "
            "angenommen (<i>gedreht 180° (Gehrungsrichtung angenommen)</i>).",
            "Verfahren: First-Fit und Best-Fit, danach Nachbesserung. Ist das nicht nachweislich optimal, rechnet "
            "die <b>Schnittmuster-Optimierung</b>: gleiche Teile werden zusammengefasst, das Programm sucht die "
            "besten Schnittmuster je Stange und die Kombination mit den wenigsten Stangen. Sie liefert zugleich eine "
            "Schranke, unter die es nicht gehen kann; wird sie erreicht, ist das Ergebnis nachweislich optimal, "
            "auch bei großen Aufträgen. Bei Gruppen bis 60 Teile folgt bei Bedarf noch eine exakte Suche. Alle "
            "Suchen sind nach Schritten begrenzt, nicht nach Zeit: dasselbe Angebot ergibt auf jedem Rechner "
            "denselben Schnittplan.",
            "Keine Restverwaltung: Reste zählen als Verschnitt.")
    i.abschnitt("Optimierung veraltet", marke="veraltet")
    i.bild("angebot_veraltet", "Nach einer Änderung der Stückzahl: Stand Veraltet", hoehe=125 * mm,
           legende=[(1, "Stand der Optimierung: grün Optimierung abgeschlossen, gelb noch nicht optimiert, rot "
                        "Veraltet.")])
    i.text("Nach jeder Änderung steht das Angebot rot auf <b>Veraltet</b>: einfach neu optimieren.", kurz=True)
    i.genauer()
    i.text("Ändert sich danach etwas am Angebot oder an den Stammdaten, zeigt die Übersicht <b>Veraltet</b>. Die "
           "Ergebnisse gelten dann nicht mehr; einfach neu optimieren. Vor einer Ausgabe mit veraltetem Stand optimiert "
           "das Programm ohne Rückfrage neu, damit kein PDF mit altem Materialbedarf entsteht.")
    i.text("Große Angebote (ab 150 Teilen) rechnen im Hintergrund: ein Fenster zeigt die gerade geplante Abmessung "
           "und die Zeit, <b>Abbrechen</b> beendet die Optimierung nach der laufenden Abmessung, ohne etwas zu "
           "speichern.")
    i.text("Die Stammdaten liest das Programm nur neu, wenn sie sich geändert haben (auch durch den Abgleich mit "
           "Kollegen oder eine Wiederherstellung). Jede Änderung am Angebot wird deshalb spürbar schneller angezeigt; "
           "der Stand <b>Veraltet</b> wird dabei weiter zuverlässig erkannt.")
    i.abschnitt("Kalkulation", marke="kalkulation")
    i.bild("erg_kalkulation", "Reiter Kalkulation, kompakte Übersicht", hoehe=80 * mm, legende=[
        (1, "<b>Kompakte Übersicht</b> je Bauteil: Profil, Stückzahl, Länge, Material, Oberfläche, "
            "<i>Laserzeit berechnet</i> und <i>Laserzeit genutzt</i> je Teil, genutzte Laserzeit der Position in "
            "Minuten, Verkaufspreis je Teil und Position. Doppelklick springt zur Position."),
        (2, "Häkchen <b>Kompakt</b> aus: alle Spalten der Kalkulation (Wahl gilt für alle Angebote).")])
    i.text("Oben die Summen des Angebots, darunter je Bauteil das Wichtigste auf einen Blick; ohne Häkchen "
           "<b>Kompakt</b> alle Spalten.", kurz=True)
    i.genauer()
    i.text("<i>Laserzeit berechnet</i> ist die Schneidzeit aus Schneidweg, Konturklassen, Gravur und Einstichen "
           "(Laserzeit brutto). <i>Laserzeit genutzt</i> ist die Zeit, die in den Preis eingeht: ohne die "
           "gemeinsamen Schnitte mit dem Nachbarteil, mit Zeiten aus Zusatzarbeiten und Prüfzeit; bei einer "
           "Schneidzeit von Hand ([[schneidzeit]]) diese Zeit, die Spalte <i>Schneidzeit manuell</i> zeigt dann "
           "„ja“. Die Spalte <i>Hinweis</i> erscheint nur, wenn eine Position einen Hinweis hat.")
    i.text("Ohne Häkchen <b>Kompakt</b> zeigt der Reiter <i>Kalkulation</i> je Position "
           "Material, Laserzeit, Gewinde, Rüsten, Herstellkosten und Verkaufspreis je Teil und je Position. Beträge "
           "stehen mit 2 Nachkommastellen da, der genaue Wert (3 Stellen) im Tooltip; das Kalkulations-PDF "
           "rechnet weiter genau. Spalten, die in allen Positionen 0 oder leer sind (z. B. Gewindezeit, "
           "Zusatzarbeiten, Handling Kundenmaterial), sind ausgeblendet; die Zeile über der Tabelle nennt ihre "
           "Anzahl. Pos., Artikelnummer, Stückzahl, Material, Herstellkosten und Verkaufspreis bleiben immer.")
    i.text("Reiter Kalkulation und Kalkulations-PDF führen jede Kostenart des Angebots einzeln auf "
           "(die Übersicht nach Gruppen, einzeln unter <i>Kostenarten einzeln</i>); im Reiter fehlen Kostenarten "
           "mit 0,00 €, das PDF enthält alle: Material, Laser schneiden, Gewinde, Rüsten Maschine, Rüsten je "
           "Abmessung, Stangenwechsel, Weitere Arbeitsschritte, Zusatzarbeiten, Zuschlag Material, Zuschlag Fertigung, Zuschlag "
           "Fremdleistung ergeben die <b>Herstellkosten</b>; dazu Programmierkosten, Pauschale je Abmessung, "
           "Angebotsaufschlag und Zukaufteile ergeben die <b>Selbstkosten</b>; dazu Gewinn, Fracht, Skonto und ggf. "
           "die Anhebung auf Mindestpreis ([[mindestpreis]]) ergeben den <b>Verkaufspreis</b>. In Klammern stehen "
           "Zeiten, Anzahl und Prozentsätze, aus denen der Betrag entsteht.")
    i.liste("<b>Material</b>: Kosten der geplanten Stangen je Gruppe, nach Längenanteil auf die Positionen verteilt "
            "(Verschnitt ist enthalten). Preis: abweichender Preis der Position, sonst <i>Preise</i>, sonst "
            "Tonnenpreis des Werkstoffs; bei den beiden letzten kommt der Aufpreis der Oberfläche je m dazu.",
            "<b>Laser</b>: Vorschübe aus den Schneiddaten (Werkstoff, sonst Kategorie; N₂ vor O₂). Schneidweg je "
            "Konturklasse durch deren Vorschub, Gravur mit eigenem Vorschub, plus "
            "Einstiche × Einstechzeit; gemeinsame Schnitte sind abgezogen. Eine manuelle Schneidzeit ersetzt diesen "
            "Wert; Zeiten aus Zusatzarbeiten (s/Stück) kommen dazu. Die Spalten <i>davon Kontur groß + Rest</i>, "
            "<i>davon Kontur mittel</i>, <i>davon Kontur klein</i>, <i>davon Gravur</i>, <i>davon Einstiche</i> "
            "und <i>davon Mehrzeit 3D</i> zeigen, wie sich die Laserzeit brutto zusammensetzt ([[konturklassen]]).",
            "<b>3D-Bearbeitung</b> (nur Teile mit Häkchen <i>3D-Schnittbearbeitung</i> auf einer Maschine mit "
            "<i>3D: Bearbeitung verfügbar = ja</i>): Gehrungen in 3D und schräge Bohrungen rechnen mit den "
            "Schneiddaten der wirksamen Dicke Wand ÷ cos(Winkel), z. B. 3 mm Wand bei 30° wie 3,46 mm, bei 45° wie "
            "4,24 mm, × <i>3D: Faktor Schneidzeit</i> + <i>3D: Zusatzzeit je Bearbeitung</i>. <i>davon Mehrzeit 3D</i> "
            "ist der Unterschied zu demselben Weg in 2D, <i>3D-Bearbeitung je Teil</i> die ganze 3D-Zeit. Winkel über "
            "der Grenze der Maschine (Vorgabe ±45°) werden auf die Grenze begrenzt und so gerechnet, die Position "
            "bekommt die WARNUNG <i>3D-Winkel begrenzt, Kontur nicht maßhaltig</i>. 3D auf einer Maschine ohne 3D ist "
            "ein FEHLER, es wird nichts stillschweigend als 2D gerechnet.",
            "<b>Gewinde</b>: Anzahl × Preis je Gewinde (Stammdaten); ohne Preis Anzahl × Zeit mit dem Stundensatz "
            "des Arbeitsschritts Gewinde.",
            "<b>Zusatzarbeiten</b>: Menge × Preis je Teil, ggf. auf den Mindestbetrag angehoben; Fremdleistungen mit "
            "dem Zuschlag Fremdleistung.",
            "<b>Rüsten</b>: Rüstzeit je Angebot (Maschine), Rüstzeit je Abmessung (Einstellungen) und "
            "Stangenwechsel je Stange (Stangen mit fester Schweißnaht-Lage mit dem Stangenwechsel SN), gleichmäßig "
            "auf alle Teile verteilt, je mit dem Stundensatz ihres Arbeitsschritts.",
            "<b>Weitere Arbeitsschritte</b>: Zeiten aus den Arbeitsschritten ([[stundensaetze]]) × Stundensatz, auf die "
            "Teile verteilt (Spalte <i>Weitere Arbeitsschritte je Teil</i>).",
            "<b>Programmierkosten</b>: Programmierzeit der Position × Stundensatz <i>Programmierung</i> "
            "([[stundensaetze]]), einmal je Position mit Stückzahl, egal wie viele Stück, ohne Zuschläge in die "
            "Selbstkosten (Spalten <i>Programmierzeit [min]</i> und <i>Programmierung je Teil</i>). Die Zeit ist "
            "<i>Programmierzeit je Position</i> + <i>Programmierzeit je Innenkontur</i> × Anzahl Innenkonturen "
            "(klein + mittel + groß aus STEP-Import oder Schneidweg-Rechner), oder von Hand in der Spalte "
            "<i>Programmierzeit [min]</i> der Position. Nur Angebote, die vor Version 0.8.22 verschickt und damit "
            "festgeschrieben wurden ([[preise_festschreiben]]), rechnen weiter mit ihrem Betrag je Position "
            "(<i>Programmierkosten je Position (alt) [€]</i>, auch in einer Staffel-Stufe).",
            "<b>Pauschale je Abmessung, Angebotsaufschlag</b>: ohne Zuschläge in die Selbstkosten.",
            "<b>Zukaufteile</b>: Einstand und Aufschlag der Zukaufteile der Position ([[zukauf_angebot]]), ohne "
            "Zuschläge in die Selbstkosten (Spalte <i>Zukaufteile je Teil</i>).",
            "<b>Selbstkosten</b> = Herstellkosten + Programmierkosten + Pauschale je Abmessung + Angebotsaufschlag + "
            "Zukaufteile (Spalte <i>Selbstkosten je Teil</i>).",
            "<b>Gewinn</b> = Selbstkosten × Gewinn %.",
            "<b>Fracht</b>: nach dem Gewinn, ohne Zuschläge und ohne Gewinn (reine Fremdkosten).",
            "<b>Skonto</b>: der Betrag, um den der Preis steigt, damit nach Abzug des Skontos der Preis mit Gewinn "
            "bleibt (Skonto % des Verkaufspreises, „im Hundert“). Je Teil in der Spalte <i>Skonto je Teil</i>.")
    i.abschnitt("Worauf der Gewinn rechnet", marke="gewinn_basis")
    i.text("Der Gewinn rechnet auf <b>alle Kosten</b> (Selbstkosten): Herstellkosten, Programmierung, Pauschalen, "
           "Angebotsaufschlag und Zukaufteile. Nur die Fracht bekommt keinen Gewinn. Das Skonto kommt zuletzt auf "
           "den Preis mit Gewinn.", kurz=True)
    i.text("Bis Oktober 2026 rechnete der Gewinn nur auf die Herstellkosten; Programmierung, Pauschalen, "
           "Angebotsaufschlag, Fracht und Zukaufteile kamen ohne Gewinn danach. Angebote, deren Preise vorher "
           "festgeschrieben (verschickt) wurden ([[preise_festschreiben]]), rechnen weiter so, damit ihr Preis "
           "gleich bleibt; die Übersicht zeigt dann „Gewinn (… % auf Herstellkosten)“. <b>Aktuelle Preise "
           "übernehmen …</b> stellt sie um (der Dialog nennt „Gewinn auf Herstellkosten → auf Selbstkosten“). Mit "
           "gleichem Gewinn-Prozentsatz steigen die Preise dadurch; bei den Prüfangeboten mit 25 % Gewinn um 1,6 bis "
           "8 %, bei kleinen Aufträgen am meisten.")
    i.abschnitt("Zeiten & Arbeitskosten", marke="zeiten")
    i.bild("erg_zeiten", "Reiter Zeiten & Arbeitskosten mit Beispielzeiten (Beispielwerte, keine gemessenen Zeiten)",
           hoehe=95 * mm, legende=[
               (1, "<b>Alle Arbeitsschritte zeigen</b>: auch Schritte ohne Zeit und Kosten (sonst ausgeblendet, "
                   "Laser schneiden immer sichtbar)."),
               (2, "<b>Stundensätze aus Einstellungen</b>: Stundensätze und Zeitvorgaben dieses Angebots auf die "
                   "aktuellen Einstellungen setzen (eigene Werte des Angebots gehen verloren)."),
               (3, "Summen: Maschinenzeit (davon Rüsten Maschine), Personalzeit (davon parallel zur Maschine), "
                   "Arbeitszeit gesamt, Durchlaufzeit (Maschine + Personal, das nicht parallel läuft), Ø Arbeitszeit "
                   "je Teil, Arbeitskosten, Material, Zuschläge, Herstellkosten, Selbstkosten, Gewinn, "
                   "Verkaufspreis. Werte mit 0 sind ausgeblendet.")])
    i.text("Je Arbeitsschritt Menge, Zeit, Stundensatz und Kosten. Gelbe Felder gelten nur für dieses Angebot.", kurz=True)
    i.genauer()
    i.text("Der Reiter <i>Zeiten & Arbeitskosten</i> zeigt je Arbeitsschritt Art, Menge, Rüstzeit, Zeit je Einheit, "
           "Gesamtzeit, Stundensatz, Kosten, Quelle und die Berechnung. Die Beträge sind dieselben wie in der "
           "Kalkulation; jede Kostenart kommt genau einmal vor. Gewinde mit Festpreis, Zusatzarbeiten ohne "
           "Zeitaufwand und Fremdleistungen stehen als Betrag <i>ohne Zeit</i> darin. Zusatzarbeiten mit Zeit "
           "(Schweißen in €/h, Zeitaufwand aus den Stammdaten) und die Schweißbaugruppen (Schweißen und eigene "
           "Arbeitsgänge) zählen als Personalzeit.")
    i.liste("Gelbe Felder gelten nur für dieses Angebot: Rüstzeit und Zeit je Einheit der weiteren Arbeitsschritte "
            "und der Stundensatz (er gilt dann für alle Schritte dieses Angebots mit demselben Satz). Die Quelle "
            "zeigt dann <i>von Hand (Angebot)</i>.",
            "Ältere Angebote ohne gespeicherte Stundensätze rechnen mit den aktuellen Einstellungen; der Reiter "
            "sagt das. Die erste Änderung oder <i>Stundensätze aus Einstellungen</i> speichert sie im Angebot.",
            "Die Übersicht rechts zeigt unter <b>Zeiten</b> Maschine und Personal mit Zeit und Kosten; ein Klick "
            "auf ▸ klappt die Arbeitsschritte auf (parallele Schritte mit „(parallel)“). Die Rüstzeit steht als "
            "„davon Rüsten“, weil sie schon in der Zeit enthalten ist. Darunter Arbeitszeit gesamt, Durchlaufzeit, "
            "Ø Arbeitszeit je Teil und Kosten ohne Zeit. Das Kalkulations-PDF enthält die Tabelle der "
            "Arbeitsschritte nach Maschine und Personal geordnet und dieselben Summen.",
            "Die Zeiten sind Vorgabewerte aus Schneiddaten, Maschinen und Arbeitsschritten, keine gemessenen "
            "Zeiten. Ist-Zeiten gehören in die Nachkalkulation ([[nachkalkulation]]).")
    i.abschnitt("Schneidweg-Rechner", marke="schneidweg_rechner")
    i.bild("schneidweg_dialog", "Schneidweg-Rechner: Gehrung 45° am Anfang, Bohrungen als Muster, Langlöcher vorne "
           "und ein Rechteck, Naht unten; Skizze vergrößert auf die erste Hälfte",
           hoehe=125 * mm, legende=[
               (1, "<b>Enden</b>: Gehrungswinkel, gekippt über, längste Seite (Vorgabe <i>automatisch</i>: aus "
                   "<i>gekippt über</i> angenommen, die Skizze zeigt sie, die Optimierung dreht das Teil passend; von "
                   "Hand nur bei fester Lage), beim Rundrohr Ausklinkung; rechts der gemessene Wert aus dem "
                   "STEP-Import."),
               (2, "<b>Innenkonturen</b>: Art, Anzahl, Maße, Lage ab Ende A, Abstand Muster, Seite, Versatz quer, "
                   "3D mit Neigung längs und quer."),
               (3, "<b>+ Bohrung</b>, <b>+ Senkung</b> … fügt eine Zeile hinzu; Kopieren, Vorlagen, Entfernen daneben."),
               (4, "<b>Ergebnis je Teil</b>: jeder Schnitt mit Länge, Einstichen, Hüllmaß und Klasse."),
               (5, "Schneidweg, Einstiche, Klassen und Schneidzeit je Teil; Hinweise und Fehler in Farbe."),
               (6, "<b>Skizze</b> maßstäblich mit Lage und Maß jeder Kontur und Schweißnaht SN."),
               (7, "<b>Schweißnaht (SN)</b>: Vorgabe, Lage, Quelle; Rechteck-/Quadratrohr nur 0°/90°/180°/270°."),
               (8, "<b>Erklärung</b> der markierten Zeile: welches Maß in Maß 1, 2 und 3 gehört."),
               (9, "<b>Zeichnung als PDF …</b>, daneben <b>STEP neu einlesen …</b>."),
               (10, "<b>Merkmale</b> mit Herkunft STEP, manuell oder Vorgabe ([[teile_editor]])."),
               (11, "<b>Prüfmeldungen</b>: Klick zeigt die Stelle in Tabelle, Skizze und 3D."),
               (12, "<b>Rückgängig</b>, <b>Wiederholen</b>, <b>Auf STEP-Wert zurücksetzen</b> und <b>Messen</b>.")])
    i.text("Für Teile ohne STEP-Datei: Position markieren, Doppelklick auf Schneidweg oder das kleine Bild. Enden, "
           "Bohrungen und Ausschnitte eintragen, das Programm rechnet Schneidweg, Einstiche und Konturklassen.", kurz=True)
    i.genauer()
    i.text("Für Teile ohne STEP-Datei rechnet der <b>Schneidweg-Rechner</b> Schneidweg, Einstiche und Konturklassen "
           "aus wenigen Angaben. Eine Position markieren und <b>Schneidweg berechnen …</b> wählen (Rechtsklick auf "
           "die Position oder <i>Ausgaben</i>, Doppelklick auf Schneidweg oder auf das kleine Bild vor "
           "der Artikelnummer). Das Profil muss in den Stammdaten stehen. Bei Teilen aus dem STEP-Import zeigt er die "
           "gemessenen Enden, Bohrungen, Konturen und die Gravur in Tabelle und Skizze; dort lassen sie sich prüfen "
           "und ändern. Die Schweißnaht wird hier ebenfalls gewählt, und <b>Zeichnung als PDF …</b> macht aus allem "
           "eine maßstäbliche Zeichnung.")
    i.text("Aufbau des Fensters: links die Merkmale, oben die Eingaben mit der Konturtabelle (Platz für mindestens "
           "fünf Zeilen ohne Rollen), darunter links Skizze und 3D-Ansicht als Reiter und rechts das Ergebnis je "
           "Teil, ganz unten die Prüfmeldungen. Die Trennlinien dazwischen lassen sich ziehen, z. B. für mehr "
           "Konturzeilen. Das Fenster öffnet so groß, wie der Bildschirm erlaubt. Merkmale, Prüfmeldungen, "
           "Rückgängig und Messen sind im Teile-Editor ([[teile_editor]]) beschrieben.")
    i.bild("schneidweg_abwicklung", "Skizze als Abwicklung: jede Fläche ein Streifen (Rechteckrohr oben, vorne, "
           "unten, hinten), die Enden als Schnittlinie, die Konturen an ihrer Stelle", hoehe=48 * mm)
    i.liste("<b>Anfangs- und Endschnitt</b>: Gehrung in Grad als Abweichung vom rechtwinkligen Schnitt (0° = gerade, "
            "höchstens 79,9°). Rundrohr: Schnittlänge als Ellipse. Alle anderen Profile: wählbar, ob die Gehrung "
            "<i>über Höhe</i> (Maß a) oder <i>über Breite</i> (Maß b) läuft; der Anteil der gekippten Richtung wird "
            "mit 1 / cos Winkel gestreckt (Quadratrohr 40 × 40, 45°: 2 × 40 / cos 45° + 2 × 40 = 193,1 mm; beim "
            "Träger Steg bzw. Flansche). Nur bei einer unbekannten Profilform ist die Gehrung eine "
            "<i>Schätzung</i> (gerade Schnittlänge / cos Winkel); der Dialog kennzeichnet sie. Je Ende zählen die "
            "Einstiche wie beim STEP-Import (Träger und U-Profil 4, T-Profil 2, sonst 1).",
            "<b>Schrägschnitt zweiachsig</b>: bei <i>gekippt über</i> „über Höhe und Breite“ wählen; dann ist der "
            "Gehrungswinkel die Neigung über Höhe und <i>Winkel über Breite</i> die zweite Neigung. Jede Kante wird "
            "mit ihrer Richtung gestreckt (Rechteckrohr: Anteil Höhe × √(1 + tan² Höhe) + Anteil Breite × "
            "√(1 + tan² Breite), Rundrohr als Ellipse mit der Gesamtneigung, RP-Profil je Konturstück). In 3D "
            "schwenkt der Kopf auf die Gesamtneigung der Ebene.",
            "<b>3D-Enden aus dem STEP-Import</b> (Spitze oder Kerbe aus mehreren Ebenen, Ausklinkung auf ein "
            "Rundrohr): die Messung liefert die Schnittflächen mit. Solange das Profil der Position das gemessene ist, "
            "gilt die gemessene Länge; mit einem anderen Profil rechnet der Rechner die Schnittkurve auf dessen "
            "Außenkontur neu (Rund-, Quadrat-, Rechteckrohr, RP-Profil), Text <i>STEP-Form, für … gerechnet</i>. "
            "Dasselbe gilt für gerade, Gehrungs- und zweiachsige Enden aus dem STEP-Import. Das braucht "
            "STEP-Import.exe ab 0.8.30; ältere Messungen behalten bei komplexen Enden die gemessene Länge.",
            "<b>Richtung der Gehrung</b> (Rund-, Quadrat- und Rechteckrohr): an welcher Seite das Teil an diesem "
            "Ende am längsten ist, z. B. <i>länger oben (0°)</i> oder <i>länger rechts (90°)</i>, gesehen von Ende A "
            "wie bei der Schweißnaht ([[schweissnaht]]), Rechteckrohr mit der Breitseite oben. Damit kann die "
            "Optimierung Gehrungen benachbarter Teile ineinanderlegen. <i>Nicht angegeben</i>: frei drehbare Teile "
            "(Schweißnaht ohne Vorgabe) legt die Optimierung mit angenommener Richtung trotzdem ineinander, Teile mit "
            "Nahtvorgabe bleiben getrennt; der Dialog weist darauf hin. Für richtige Drehangaben in den "
            "Werkstattpapieren die Richtung eintragen. Beim Rechteckrohr muss die Richtung zur Gehrungsachse passen (0°/180° kippt über "
            "die kürzere Seite, 90°/270° über die längere), sonst meldet der Dialog einen Fehler.",
            "<b>Ausklinkung auf Rundrohr Ø</b> (nur Rundrohr): das Ende wird rechtwinklig auf ein Rundrohr mit "
            "diesem Durchmesser gesetzt (Sattelschnitt); das Programm rechnet die Länge der Schnittkurve. Der "
            "Durchmesser muss mindestens so groß sein wie das eigene Rohr; eine Gehrung zusätzlich geht nicht.",
            "<b>Innenkonturen</b> mit Anzahl je Teil: <i>Bohrung</i> (Ø: π × d; im Rundrohr etwas mehr, siehe "
            "unten), <i>Senkung</i> (Bohrung Ø d und "
            "Senk-Ø D: geschnitten wird nur die Bohrung π × d, Senken kommt als Zusatzarbeit in die Position), "
            "<i>Flowdrill</i> (Kernloch-Ø: nicht geschnitten, nur markiert mit Gravur oder Loch Ø 0,5; Flowdrill "
            "kommt als Zusatzarbeit in die Position), <i>Langloch</i> (Länge, Breite: "
            "2 × (l − b) + π × b), <i>Rechteck</i> (Breite, Höhe, Eckradius: 2 × (b + h) − 8 r + 2 π r), "
            "<i>Schlitz</i> offen vom Rand (Tiefe, Breite: 2 × l + b), <i>Ausklinkung</i> am Ende als Rechteck "
            "(Länge ab Ende, Breite, Eckradius innen: 2 × (l − r) + (b − 2 r) + π × r; ohne Lage an Ende A, für "
            "Ende B Lage = Teilelänge − l/2; der Endschnitt wird dafür nicht gekürzt, das ist die sichere Seite), "
            "<i>Polygon</i> aus Eckpunkten in Maß 1 "
            "(<i>x,y; x,y; …</i> in mm, geschlossen, z. B. 0,0; 40,0; 40,20; 0,20 = 120 mm, Hüllmaß 40) und "
            "<i>sonstige Kontur</i> mit Schnittlänge von Hand und Hüllmaß (leer = groß), <i>Sonderkontur</i> (freie "
            "Form, auch über mehrere Flächen; aus dem STEP-Import mit ihrem echten Umriss, der in Skizze, Abwicklung "
            "und Zeichnung über die Kanten läuft) und <i>Gravur</i> (Gravurlänge an dieser Stelle, grün gezeichnet, "
            "nie im Schneidweg, zählt zur Gravur), dazu der <i>V-Ausschnitt</i> für einen Knickrahmen (Knickwinkel, "
            "Freistich-Ø; Seite = Stegwand, [[knickrahmen]]). Jede Kontur außer Gravur und Flowdrill ist ein Einstich. "
            "Unmögliche Maße (Langloch kürzer als "
            "breit, Eckradius über der halben Seite) werden rot gemeldet, <i>In Position übernehmen</i> ist dann "
            "gesperrt.",
            "<b>Gravur</b>: Länge weiterer Gravurlinien in mm (zusätzlich zu den Zeilen der Art Gravur), wird "
            "mit dem Vorschub Gravur gerechnet.",
            "<b>Vorlagen</b>: <i>Vorlagen → Als Vorlage speichern …</i> merkt sich Enden, Konturen (mit Lage, Seite, "
            "Muster) und Gravur unter einem Namen, für alle Angebote; <i>Vorlage laden</i> ersetzt damit die "
            "Eingaben, <i>Vorlage löschen</i> entfernt sie. Eine Vorlage eines anderen Profils trägt die Profilform "
            "im Namen; Seiten, die das Profil nicht hat, landen auf der ersten Fläche. <b>Aus Position kopieren …</b> "
            "hängt die Konturen einer anderen Position dieses Angebots an (Enden bleiben).",
            "<b>Lage der Konturen</b> (nur für die Skizze, ändert den Schneidweg nicht): <i>Lage ab Anfang</i> = "
            "Mitte der Kontur in mm ab Ende A (leer = gleichmäßig verteilt, Schlitz ohne Lage am Ende A). "
            "<i>Abstand</i> macht aus der Anzahl ein <b>Muster</b>: 4 Bohrungen, Lage 200, Abstand 100 liegen bei "
            "200, 300, 400 und 500 mm. <i>Seite</i> ist die Fläche, auf der die Kontur sitzt, von Ende A gesehen: "
            "Rechteckrohr und Quadratrohr nur <i>0° oben, 90° vorne (rechts), 180° unten, 270° hinten (links)</i> "
            "(Rechteckrohr mit der Breitseite oben, wie bei Schweißnaht und Gehrungsrichtung); Flachstahl <i>oben, "
            "vorne, unten, hinten</i>; U-/C-Profil und Träger <i>Flansch oben, "
            "Steg, Flansch unten</i>; T-Profil <i>Flansch, Steg</i>; L-Profil <i>Schenkel a, Schenkel b</i>. Beim "
            "Rundrohr steht dort der Winkel am Umfang (0° oben, 90° vorne, 180° unten, 270° hinten, auch frei, z. B. "
            "45°). <i>Versatz quer</i> verschiebt die Kontur von der Flächenmitte zur nächsten Fläche hin (mm). "
            "Langlöcher und Rechtecke liegen mit ihrer Länge bzw. Breite längs zum Teil.",
            "<b>Bohrungen im Rundrohr</b> (seit 0.8.35): Beim 2D-Schnitt zeigt der Strahl immer zur Rohrmitte. Innen "
            "hat das Loch den Ø der Konstruktion, außen ist es quer zur Rohrachse breiter und leicht elliptisch "
            "(Außen- ÷ Innenradius). Gerechnet wird diese Kontur auf der Außenhaut, z. B. Ø 10 in Rundrohr 40 × 2: "
            "33,4 mm statt π × 10 = 31,4 mm; Ø 5 in 20 × 2: 17,9 statt 15,7 mm. Das gilt für Bohrungen und Senkungen "
            "senkrecht zur Oberfläche (auch beim STEP-Import); schräge Bohrungen in 3D rechnen weiter als Ellipse "
            "auf der Wand. Das Hüllmaß für die Konturklasse bleibt der Ø.",
            "<b>3D-Schnittbearbeitung</b> (seit 0.8.18, nur wenn ausgewählt): 3D ist ein Schnitt nur, wenn die "
            "Schnittfläche nicht senkrecht (90°) zur Rohroberfläche steht und der Laserkopf dafür geschwenkt wird. "
            "Bleibt der Strahl senkrecht zur Oberfläche, ist es 2D, auch bei einer Gehrung. Das Häkchen <i>3D-Schnittbearbeitung "
            "aktivieren</i> über den Enden schaltet sie für das Teil ein; daneben steht, ob die Maschine 3D kann, "
            "ihr Schwenkwinkel und das Greifmaß (rot, wenn die Maschine kein 3D kann, die Position bekommt dann einen "
            "FEHLER). Danach je Ende <i>Gehrung in 3D</i> (nur mit Gehrung: der Kopf wird auf den Gehrungswinkel "
            "geschwenkt, die Schnittfläche ist eben durch die Wand) und je Bohrung die Spalte <i>3D</i> mit "
            "<i>Neigung längs</i> (+ Richtung Ende B) und <i>Neigung quer</i> (+ im Uhrzeigersinn von Ende A, "
            "Richtung 90°), Schnellauswahl −45°, −30°, 0°, +30°, +45° oder eine Zahl. Die Neigung ist der Winkel "
            "der Bohrungsachse gegen die Wand, nicht der Umfangswinkel (der steht in <i>Seite</i>). Die Bohrung "
            "wird als Ellipse gerechnet (Hüllmaß d / cos Gesamtneigung) und in der Skizze so gezeichnet, mit "
            "<i>3D</i> und den Winkeln. Über der Grenze der Maschine (Vorgabe ±45°) wird der Winkel begrenzt, der "
            "Dialog zeigt den Hinweis, die Position bekommt „WARNUNG: 3D-Winkel begrenzt, Kontur nicht "
            "maßhaltig“. Fasen werden nicht in 3D gerechnet. Ohne Häkchen am Teil bleibt alles 2D, auch wenn "
            "Zeilen <i>3D</i> haben. Zeit und Greifmaß: [[kalkulation]], [[optimieren]].",
            "<b>Skizze</b> (maßstäblich, gleicher Maßstab in Länge und Höhe): <i>Draufsicht und Seitenansicht</i> "
            "(Blick von oben und auf die Fläche vorne) oder <i>Abwicklung</i> (alle Flächen als Streifen, beim "
            "Rundrohr der Umfang in Vierteln). Gehrungen erscheinen mit ihrer Richtung, die sichtbare Schnittfläche "
            "hellblau; verdeckte Kanten und Konturen auf der Rückseite sind gestrichelt, verteilte Konturen ohne "
            "Lage blasser. Oben stehen die Lagen ab Anfang, unten die Länge; rechts oben die <i>Ansicht von A</i> "
            "mit den Flächennamen. <b>Mausrad</b> = Zoom an der Mausposition, Ziehen auf freier Fläche verschiebt "
            "das Bild, <b>Doppelklick</b> oder <i>Einpassen</i> zeigt wieder alles. Ein <b>Klick auf eine Kontur</b> "
            "markiert ihre Zeile in der Tabelle (und umgekehrt), <b>Ziehen</b> verschiebt sie: längs ändert die "
            "Lage (ein Muster wandert als Ganzes), quer ändert in der Abwicklung Seite und Versatz, in Draufsicht "
            "und Seitenansicht den Versatz bzw. beim Rundrohr den Winkel. Die Werte stehen danach in der Tabelle. "
            "Fehlt die Teilelänge, zeichnet die Skizze mit 1000 mm. Flanschdicken, die das Profil nicht hat "
            "(kein Normprofil), zeichnet sie mit der Wandstärke; gerechnet wird damit nichts.",
            "<b>Spalte Gewinde</b> (Bohrung und Flowdrill): <i>automatisch</i> nimmt das Gewinde zum Kernloch-Ø "
            "aus den Stammdaten (z. B. Ø 8,5 für M10), <i>kein Gewinde</i> oder ein Gewinde aus der Liste gilt wie "
            "gewählt. Was im Rechner eingegeben ist, gilt als <b>bestätigt</b>: Mit OK kommen Gewinde, Senken, "
            "Flowdrill und Bohren (Bohrung kleiner als 0,7 × Wand) mit Anzahl und Preis je Stück direkt in die "
            "Position, ohne Prüfhinweis. Ändern lässt sich das jederzeit im Fenster <i>Bohrungen prüfen</i> "
            "([[bohrungen_pruefen]]).",
            "Unter <i>Ergebnis je Teil</i> stehen sofort alle Schnitte mit Länge, Einstichen, Hüllmaß und Klasse "
            "(klein/mittel/groß nach den Konturgrenzen der Maschine, [[konturklassen]]), darunter Schneidweg und "
            "Schneidzeit je Teil mit den Schneiddaten der Maschine. Ohne passende Schneiddaten erscheint ein "
            "Hinweis; das Programm erfindet keine Werte, die Schneidzeit wird dann von Hand eingetragen.",
            "<b>Teile aus dem STEP-Import</b> (seit 0.6.29): Der Import legt die gemessenen Konturen und Enden im "
            "Rechner ab. Beim Öffnen stehen sie mit Art, Maßen, Lage ab Anfang und Seite (Rundrohr Winkel, "
            "Rechteckrohr Fläche und Versatz) in der Tabelle und in der Skizze, die Gravur als Länge; grün markierte "
            "Zeilen und Enden rechnen mit der <b>gemessenen</b> Schnittlänge (rechts neben dem Ende steht sie als "
            "<i>gemessen … mm</i>). Ändert man Art oder Maße einer Zeile bzw. Winkel, Achse oder Richtung eines "
            "Endes, rechnet sie mit den Formeln. Freie Ausschnitte und Ausschnitte über mehrere Wände erscheinen "
            "als <i>Sonderkontur</i> mit gemessener Länge, Hüllmaß und echtem Umriss; Prägungen und Markierungen als "
            "<i>Gravur</i>-Zeilen mit Lage und Tiefe (grün), die übrige Gravur (z. B. an Anbauteilen) als Länge. Ein "
            "komplexes Ende (Ausklinkung, Formschnitt) zeigt in der Abwicklung seinen gemessenen Verlauf. Merkmale "
            "nur auf der Innenseite fehlen (nicht im Schneidweg). Bei "
            "offenen Profilen (U-, C-, L-, T-Profil, Träger, Flachstahl) legt der Import jede Kontur auf ihre Fläche "
            "(Steg, Flansch oben/unten, Schenkel a/b) mit Versatz quer; ein L-Profil, das von Ende A gesehen "
            "spiegelverkehrt liegt, erscheint wie in der Skizze (Fläche und Abstand von der Ecke stimmen). Bei Quadrat- und Rechteckrohren mit Eckradius wird der <i>Versatz quer</i> aus dem "
            "Umfangswinkel gemessen und sitzt genau; vor 0.8.23 importierte Teile lagen bis zu einigen mm daneben "
            "und werden mit <b>STEP neu einlesen …</b> korrigiert.",
            "<b>Ältere STEP-Positionen</b> (vor 0.6.29 importiert): Der Rechner zeigt die gespeicherten Werte der "
            "Position: Enden mit gemessener Länge und Gehrung, Gravur, Bohrungen (Länge = π × Ø) und übrige Konturen "
            "mit Größe und Schnittlänge. Ihre Lage ist nicht gespeichert, sie stehen in der Skizze verteilt, ein "
            "gelber Hinweis sagt das. <b>STEP neu einlesen …</b> wählt die STEP-Datei des Teils, misst sie und "
            "ersetzt die Eingaben durch die Messung mit Lage, Seite und Maßen (bei mehreren Rohrteilen in der Datei "
            "zuerst das mit derselben Artikelnummer, sonst Auswahl). Erst <i>In Position übernehmen</i> speichert.",
            "<b>Schweißnaht (SN)</b>: Vorgabe (keine Vorgabe, feste Position, unbekannt), Lage und Quelle wie im "
            "Fenster Schweißnaht ([[schweissnaht]]); Rechteck- und Quadratrohr nur 0° oben, 90° vorne (rechts), 180° "
            "unten, 270° hinten (links), Rundrohr frei im Winkel. Die Naht erscheint rot strichpunktiert (SN) in "
            "Skizze und Zeichnung. Gespeichert wird sie mit <i>In Position übernehmen</i>, nur wenn sie im Rechner "
            "geändert wurde.",
            "<b>Zeichnung als PDF …</b>: maßstäbliche Zeichnung des Teils (A4 quer, gleiches Design wie Angebot und "
            "Kalkulation) mit Draufsicht, Seitenansicht, Ansicht von A und Abwicklung, Lage und Maß jeder Kontur, "
            "Schweißnaht, Maßstab, dazu Tabellen der Enden und Innenkonturen (Art, Maße, Lage ab Ende A, Seite, "
            "Versatz, Schnittlänge, Klasse) sowie Schneidweg, Einstiche, Gravur und Schneidzeit. Die Datei landet in "
            "der Ablage des Angebots und öffnet sich. Konturen ohne Lage stehen als <i>verteilt</i> darin.",
            "<b>In Position übernehmen</b> schreibt Schneidweg, Einstiche, Anfangs-/Endschnitt (gerade ja/nein), "
            "Innenkonturen, Gravur, Konturliste und Konturklassen in die Position, also dieselben Felder wie der "
            "STEP-Import. Hat die Position schon Werte aus dem STEP-Import, fragt das Programm vorher. Die Eingaben "
            "bleiben gespeichert und erscheinen beim nächsten Öffnen wieder.",
            "Eine von Hand eingetragene Schneidzeit gilt weiter, bis sie in der Positionsliste gelöscht wird.")
    i.abschnitt("Knickrahmen", marke="knickrahmen")
    i.text("Ein <b>Knickrahmen</b> ist ein Rahmen aus einem einzigen Quadrat- oder Rechteckrohr. Der Laser schneidet "
           "an jeder Ecke einen V-Ausschnitt, nur die <b>Stegwand</b> bleibt stehen; daran wird das Rohr geknickt. "
           "Im Schneidweg-Rechner: <b>Knickrahmen …</b>, Schenkel eingeben, fertig.", kurz=True)
    i.bild("knickrahmen_rechner", "Knickrahmen 500 × 300 aus QR 40 × 40 × 3 im Schneidweg-Rechner: Abwicklung mit "
           "drei V-Ausschnitten", hoehe=110 * mm, legende=[
               (1, "Knopf <b>Knickrahmen …</b>: Schenkel, Knickwinkel, Stegwand, Freistich, Knickzugabe, K-Faktor."),
               (2, "Drei Zeilen <b>V-Ausschnitt</b> mit Knickwinkel und Lage der Knicke, Seite = Stegwand."),
               (3, "<b>Abwicklung</b>: V über Innenwand und Seitenwände, Spitzen an der Stegwand; Gehrung 45° an "
                   "beiden Enden (Stoß)."),
               (4, "Ergebnis mit gestreckter Länge und Hinweis zum Stoß.")])
    i.genauer()
    i.liste("<b>Schenkel</b> = Außenmaße entlang der Stegwand in Reihenfolge ab Ende A, getrennt mit Semikolon, "
            "z. B. <i>500; 300; 500; 300</i>. <b>Geschlossen</b>: Anfang und Ende stoßen an einer Ecke zusammen, "
            "beide Enden bekommen die halbe Gehrung des Stoßes (Rechteck 45°), längste Seite = Stegwand. "
            "<b>Offen</b> (U-Rahmen): die Enden bleiben, wie sie sind.",
            "<b>Knickwinkel β</b> = Umlenkung am Knick (Rechteck 90°, Dreieck 120°), eine Zahl für alle Knicke oder "
            "je Knick. <b>Stegwand</b> = Wand, die stehen bleibt (Vorgabe unten); das Maß quer dazu ist h.",
            "<b>V-Ausschnitt</b>: Breite an der Innenwand w = 2 × (h − s) × tan(β/2), Schnittlänge je Knick "
            "2 × b + 4 × (h − s) / cos(β/2), 1 Einstich. Mit <b>Freistich</b> kommt an jeder Spitze ein Loch dazu "
            "(2 × π × Ø). Beispiel QR 40 × 40 × 2, β = 90°: w = 76 mm, 295,0 mm je Knick.",
            "<b>Gestreckte Länge</b> = Summe der Schenkel − Knicke × (v − z). v ist der Ausgleichswert nach DIN 6935 "
            "für die Stegwand (Innenradius 0, K-Faktor 0,5 = Wandmitte), z die Knickzugabe je Knick. Beispiel "
            "Rahmen 500 × 300 aus QR 40 × 40 × 2: 1600 − 3 × 2,43 = <b>1592,7 mm</b>. Mit <i>In Position "
            "übernehmen</i> wird das die Teilelänge.",
            "Einstellungen unter <b>Knickrahmen</b>: <i>Knickrahmen: Knickzugabe je Knick [mm] (+ = Rohr länger)</i>, "
            "<i>Knickrahmen: Freistich-Ø an den Spitzen des V [mm] (0 = ohne)</i> und <i>Knickrahmen: K-Faktor der "
            "Stegwand (0,5 = Wandmitte)</i>; sie sind die Vorgaben im Fenster Knickrahmen ([[einstellungen]]).",
            "<b>Zusatzarbeit Knicken</b>: € je Knick (Beispielpreis 2,00 €, Stammdaten Zusatzarbeiten); der Rechner "
            "trägt die Zahl der V-Ausschnitte als Menge ein. Beim geschlossenen Rahmen erinnert ein Hinweis an das "
            "Schweißen des Stoßes.",
            "Ein einzelner Knick geht auch ohne Rahmen: <b>+ V-Ausschnitt</b> in der Tabelle, Lage und Stegwand "
            "eintragen. Die Teilelänge bleibt dann, wie sie ist.",
            "<b>Innenwand schräg (3D)</b>: Die Wand gegenüber der Stegwand wird um β/2 geschwenkt geschnitten, damit "
            "die Stirnflächen nach dem Knicken voll aufeinanderliegen. Vorgabe aus: der gerade Schnitt lässt sich "
            "ebenso knicken, innen bleibt dann ein kleiner Keilspalt. Mit Haken ist das Teil eine 3D-Bearbeitung "
            "(Maschine mit 3D, [[schneidweg_rechner]]).",
            "<b>Prüfregeln</b> ([[pruefregeln]]): <i>Schenkel zu kurz</i>, <i>Kontur im Knickbereich</i> und "
            "<i>Wand zu dick zum Knicken</i>. <b>Knickrahmen entfernen</b> im Fenster nimmt Schenkel und "
            "V-Ausschnitte wieder heraus.")
    i.abschnitt("Knickverbindung aus Einzelrohren (STEP)", marke="knickverbindung")
    i.text("Ist der Rahmen in der STEP-Datei aus <b>einzelnen Rohren mit Gehrung</b> gezeichnet, schlägt der "
           "Prüfdialog über der Rohrliste <b>Knickrahmen möglich</b> vor. <b>Knickverbindung erstellen …</b> macht "
           "aus den Rohren eine Position: das gestreckte Rohr mit den V-Ausschnitten.", kurz=True)
    i.bild("knickverbindung", "Knickverbindung aus vier Rohren QR 40 × 40 × 2 (Rahmen 500 × 300)", hoehe=70 * mm,
           legende=[(1, "<b>Erster Schenkel</b> = Ende A des gestreckten Rohrs; beim geschlossenen Rahmen liegt "
                        "dort der Stoß."),
                    (2, "<b>Laufrichtung umkehren</b>: die Schenkel in der anderen Reihenfolge."),
                    (3, "<b>Innenwand schräg (3D)</b>, Vorgabe aus."),
                    (4, "Schenkel in Reihenfolge, Stegwand, gestreckte Länge und Lage der Knicke.")])
    i.genauer()
    i.liste("<b>Erkennung</b>: gleiches Quadrat- oder Rechteckrohr, je zwei Enden mit Gehrung berühren sich, der "
            "Winkel zwischen den Rohren ist die Summe der beiden Gehrungen (45° + 45° = 90°), alle Rohre liegen in "
            "einer Ebene. Ein räumlicher Rahmen wird nicht vorgeschlagen. Die Stegwand ist die Außenseite der Ecken "
            "(längste Seite der Gehrung).",
            "<b>Eigene Auswahl</b>: Rohre in der Liste markieren (Strg), Rechtsklick → <b>Knickverbindung "
            "erstellen …</b>. Passen die Rohre nicht zusammen, nennt das Programm den Grund.",
            "<b>Schenkel</b> = gemessene Länge der Rohre (Außenmaß an der Stegwand). Knickzugabe, Freistich und "
            "K-Faktor kommen aus den Einstellungen und sind im Fenster änderbar.",
            "<b>Übernehmen</b>: Das erste Rohr wird die Position mit gestreckter Länge, V-Ausschnitten, Gehrung am "
            "Stoß und der Zusatzarbeit Knicken. Bohrungen und Konturen aller Rohre stehen an ihrer Stelle auf dem "
            "gestreckten Rohr. Die übrigen Rohre werden nicht einzeln übernommen (Bericht: <i>Schenkel des "
            "Knickrahmens …</i>). Die 3D-Ansicht zeigt den gefalteten Rahmen.",
            "<b>Schweißbaugruppe</b>: Nahtkandidaten an den Knicken fallen weg, der Stoß bleibt als Vorschlag. Im "
            "Baugruppen-Editor gibt es die Knickverbindung nicht (dort sind gleiche Rohre schon eine Position und ihre "
            "Lage fehlt); er erinnert bei Rohren mit Gehrung daran, die STEP-Datei neu einzulesen.",
            "<b>Lösen</b>: Rechtsklick auf die Zeile → <b>Knickverbindung lösen</b>; die Rohre stehen wieder einzeln "
            "in der Liste.")
    i.abschnitt("Teile-Editor: Merkmale, Prüfmeldungen, Rückgängig", marke="teile_editor")
    i.text("Schneidweg-Rechner und Blech-Editor haben denselben Rahmen: links die <b>Merkmale</b> des Teils mit ihrer "
           "Herkunft, unten die <b>Prüfmeldungen</b>, oben <b>Rückgängig</b>, <b>Wiederholen</b>, <b>Auf STEP-Wert "
           "zurücksetzen</b> und <b>Messen</b>. Ein Klick auf ein Merkmal oder eine Meldung zeigt die Stelle in "
           "Tabelle, Skizze und 3D-Ansicht.", kurz=True)
    i.genauer()
    i.liste("<b>Merkmale</b>: Teil (Länge bzw. Werkstoff, Dicke und Zuschnitt), Enden, Innenkonturen, Biegungen, "
            "Anbauteile, Schweißnaht und Gravur, je Eintrag mit der <b>Herkunft</b>: <i>STEP</i> (grün) = wie im "
            "STEP-Import gemessen, <i>manuell (STEP geändert)</i> (orange) = gemessen und von Hand geändert, "
            "<i>manuell</i> = von Hand eingetragen, <i>Vorgabe</i> (grau) = unveränderter Grundwert. Beim Blech "
            "bleibt die Herkunft mit der Position gespeichert; beim Rohr gilt sie, solange der Rechner offen ist "
            "(danach zählen die gemessenen Werte, solange Art und Maße einer Zeile unverändert sind).",
            "<b>Auf STEP-Wert zurücksetzen</b>: setzt das gewählte Merkmal mit Herkunft <i>manuell (STEP "
            "geändert)</i> wieder auf die Messung, z. B. eine Bohrung oder ein Ende; die gemessene Schnittlänge gilt "
            "dann wieder.",
            "<b>Prüfmeldungen</b>: die Befunde der Fertigungsprüfung ([[pruefregeln]]) sowie Fehler und Hinweise der "
            "Rechnung, Fehler zuerst. Ein Klick wählt das betroffene Merkmal; bei einem zu schmalen Steg sind beide "
            "Konturen markiert, in der Skizze und in der 3D-Ansicht blau hervorgehoben.",
            "<b>Auswahl überall gleich</b>: Klick auf eine Zeile der Tabelle, ein Merkmal, eine Kontur in der Skizze "
            "oder eine Linie in der 3D-Ansicht wählt überall dasselbe Merkmal. Die 3D-Ansicht des Rohrs zeigt das "
            "Netz aus dem STEP-Import (Reiter <i>3D</i> neben der Skizze); dort ist der Bereich der gewählten Kontur "
            "bzw. des Endes längs der Rohrachse hervorgehoben. Beim Blech ist es die Kontur bzw. Biegelinie selbst.",
            "<b>Messen</b>: Knopf drücken, dann in der 3D-Ansicht zwei Punkte anklicken; das Programm fängt die "
            "nächste Ecke des Modells und zeigt den Abstand in mm mit Δx, Δy und Δz. Noch einmal drücken beendet "
            "das Messen.",
            "<b>Rückgängig</b> (Strg+Z) und <b>Wiederholen</b> (Strg+Y) nehmen Eingaben im Fenster zurück bzw. "
            "stellen sie wieder her, mit den gemessenen Werten. In einem Eingabefeld mit Cursor wirkt Strg+Z zuerst "
            "im Text.",
            "Merkmale und Prüfmeldungen werden kurz nach der letzten Eingabe neu aufgebaut (etwa 0,15 s), damit "
            "beim Tippen nichts hängt. Gerechnet wird wie bisher im Schneidweg-Rechner bzw. Blech-Editor; der "
            "Rahmen rechnet nichts eigenes.")
    i.abschnitt("Konturklassen in der Schneidzeit", marke="konturklassen")
    i.bild("angebot_zusatz", "Positionen mit Zusatzarbeiten und angepasster Schneidzeit", hoehe=110 * mm, legende=[
        (1, "Spalte <b>Schneidzeit je Teil [s]</b>: grau berechnet, fett angepasst."),
        (2, "Spalte <b>Zusatzarbeiten</b>: Doppelklick öffnet die Auswahl."),
        (3, "Status <b>HINWEIS: Schneidzeit manuell</b>.")])
    i.text("Innenkonturen und Enden zählen je nach Größe als klein, mittel oder groß; kleine Konturen werden "
           "langsamer geschnitten.", kurz=True)
    i.genauer()
    i.text("Der STEP-Import teilt jede Innenkontur und auch den <b>Anfangs- und Endschnitt</b> nach ihrer Größe "
           "(Hüllmaß) in <b>klein</b>, <b>mittel</b> oder <b>groß</b> ein; die Grenzen stehen je Maschine in den "
           "Stammdaten Maschinen (Vorgabe 10 und 50 mm, ein Wert genau auf der Grenze zählt zur kleineren Klasse). "
           "Seit Version 0.6.19 zählt zusätzlich das Verhältnis <b>Hüllmaß ÷ Wandstärke</b>: klein bis 3 × Wand, "
           "mittel bis 8 × Wand (Faktoren je Maschine änderbar). Es gilt die <b>strengere</b> (kleinere) der beiden "
           "Klassen, denn eine Kontur, die kaum größer als die Wand ist, schneidet sich langsam (Leistungsrampe, "
           "Einstich nah am Schnitt). Beispiel: Ø 20 bei 8 mm Wand = 2,5 × Wand, also klein statt mittel; Ø 20 bei "
           "2 mm Wand = 10 × Wand, bleibt mittel. Die Wandstärke ist die größte Wandstärke des Profils (wie bei den "
           "Schneiddaten). Gerechnet wird dann der <b>Schnittweg</b> jeder Klasse mit ihrem Vorschub aus den "
           "Schneiddaten:")
    i.liste("Hüllmaß einer Bohrung = Durchmesser. Bei anderen Innenkonturen die größere Seite des kleinsten "
            "Rechtecks um die abgewickelte Kontur: ein schräges Langloch zählt mit seiner wahren Länge, ein Schlitz "
            "um ein Rundrohr mit der Bogenlänge.",
            "Hüllmaß eines Endes = größere Seite der Schnittfläche: gerader Schnitt QR 40x40 = 40 mm, RR 42,4 = "
            "42,4 mm, Gehrung 45° über die 60er Seite eines RE 60x40 = 84,9 mm.",
            "Kontur klein [mm] / Vorschub klein, Kontur mittel [mm] / Vorschub mittel (leer = nächstgrößerer "
            "Vorschub).",
            "Der Rest des Schneidwegs (große Konturen und Enden, von Hand ergänzter Schneidweg) / Vorschub groß. Der "
            "Rest ist nie kleiner als 0.",
            "Gravur [mm] / Vorschub Gravur und Einstiche × Einstechzeit.",
            "Gemeinsame Schnitte (zwei gerade Enden teilen sich einen Schnitt): die Einsparung wird mit dem Vorschub "
            "der Klasse des geraden Endes abgezogen.",
            "Eine Innenkontur ab 0,7 × Wandstärke ist in der Regel schneidbar. Ist sie <b>kleiner als 0,7 × "
            "Wandstärke</b> (z. B. Bohrung Ø 5 in 8 mm Wand, Grenze 5,6 mm), zeigt die Position die Warnung "
            "<i>Kontur kleiner als 0,7 × Wandstärke, Schneidbarkeit prüfen (ggf. nur gravieren und aufbohren)</i>: "
            "dann die Kontur ggf. nur gravieren und das Loch anschließend aufbohren. Gerechnet wird weiter. Für "
            "Bohrungen schlägt das Fenster Bohrungen prüfen dafür den Arbeitsschritt <i>Bohren</i> vor "
            "([[bohrungen_pruefen]]).")
    i.text("Die Liste aller Konturen steht in der Position (Spalte <i>Konturen Hüllmaß x Schnittweg [mm]</i>), die "
           "Regel, mit der sie eingeteilt wurde, in der Spalte <i>Konturgrenzen</i> (z. B. <i>10/50; 3×/8× Wand "
           "4</i>). Wird im Angebotskopf eine andere Maschine oder in der Position ein anderes Profil gewählt oder "
           "ändern sich Grenzen oder Faktoren in den Stammdaten, teilt "
           "das Programm die Positionen beim nächsten Öffnen bzw. Neuberechnen neu ein und meldet das in der "
           "Statuszeile. Die Konturliste lässt sich auch von Hand ändern; die Klassen werden dann neu eingeteilt. "
           "Positionen aus einem STEP-Import vor Version 0.5.7 haben keine Konturliste: dort laufen Anfangs- und "
           "Endschnitt weiter mit Vorschub groß, bis das Teil neu importiert wird.")
    i.text("Beispiel mit Vorschub groß 3000, mittel 2000, klein 1000 mm/min und 0,5 s je Einstich, Teil aus RE "
           "80x60 (Enden 80 mm, groß): Anfangs- und "
           "Endschnitt je 120 mm, 4 × Ø10 (125,7 mm, klein), ein Langloch 40×10 (91,4 mm, mittel), ein Ausschnitt "
           "80×40 (240 mm, groß), 8 Einstiche ergeben 9,6 + 2,7 + 7,5 + 4,0 = <b>23,9 s</b>. Bei einem QR 40x40 "
           "lägen die Enden mit 40 mm in der Klasse mittel. Die Anteile stehen im "
           "Reiter Kalkulation (Spalten <i>davon …</i>) und im Kalkulation-PDF in der Tabelle <i>Schneidzeit je Teil "
           "nach Konturklassen</i>. Widersprechen sich Schneidweg und Konturklassen, zeigt der Status eine WARNUNG "
           "([[fragen]]).")
    i.abschnitt("Schnittplan")
    i.bild("erg_schnittplan", "Reiter Schnittplan, Stange 3 gewählt", hoehe=85 * mm)
    i.text("Oben alle Stangen mit Belegung, Rest und Ausnutzung; unten die Teile der gewählten Stange in "
           "Schnittreihenfolge.", kurz=True)
    i.genauer()
    i.text("Oben stehen alle Stangen mit Belegung, Rest und Ausnutzung. Was für alle Stangen gleich ist (z. B. "
           "Stangenlänge, Endbeschnitt, Greiferrest, Profil), steht nur einmal in der Zeile darüber („für alle gleich: "
           "Stangenlänge 6.000 mm · Endbeschnitt 10 mm · …“) und nicht in jeder Zeile. Unten stehen die Teile der "
           "gewählten Stange in Schnittreihenfolge mit Lage (von/bis), Drehung und Art der Trennung; nach dem "
           "Optimieren ist die erste Stange schon gewählt, ein Klick auf eine andere Stange zeigt deren Teile.")
    i.text("Bei Gehrungen zeigt die Spalte <b>Lage</b>, ob das Teil um die eigene Achse gedreht liegt (<i>normal</i> "
           "oder <i>gedreht 180°</i>), die Spalte <b>Schweißnaht</b> eine feste oder unbekannte Naht "
           "(<i>Naht 90° fest</i>, <i>Naht unbekannt, nicht drehen</i>; leer = frei drehbar, [[schweissnaht]]). "
           "Liegen zwei Gehrungen ineinander, steht als Trennung <i>Gehrung ineinander</i> und in "
           "<b>Eingespartes Material [mm]</b>, wie viel kürzer die Belegung gegenüber zwei Schnitten mit Abstand ist. "
           "Die Werkstattpapiere zeigen Lage und Naht in derselben Spalte.")
    i.text("Ein Doppelklick auf ein Teil in der unteren Liste springt zu seiner Position.")
    i.abschnitt("Stangenbild")
    i.bild("erg_stangenbild", "Reiter Stangenbild", hoehe=85 * mm)
    i.text("Jede Stange als Balken: Teile farbig mit Positionsnummer, Rest hellgrau, Greiferrest rot. Doppelklick "
           "auf ein Teil springt zur Position.", kurz=True)
    i.genauer()
    i.text("Jede Stange als maßstäblicher Balken: Endbeschnitt grau, Teile farbig mit Positionsnummer und Länge, "
           "dicke Linie = Schnitt, Rest hellgrau, Greiferrest rot (mit <i>3D</i> beschriftet, wenn dort das größere "
           "3D-Greifmaß frei bleibt). Gleich belegte Stangen stehen einmal da "
           "(<i>2 × Stange 1, 2</i>). Schräge Enden mit bekannter Richtung erscheinen als schräge Linie, "
           "ineinanderliegende Gehrungen also als verzahnte Trapeze. Gezeigt wird die Ansicht von der Seite (0° "
           "oben); sind die Gehrungen über die Seitenflächen geschnitten, die Ansicht von oben (Hinweis "
           "<i>Ansicht von oben</i> in der Kopfzeile). Ein Doppelklick auf ein Teil springt zu seiner Position.")
    i.text("<b>Schweißnaht:</b> Hat ein Teil eine feste Naht, liegt auf dem Teil ein <b>roter Strich</b> in der "
           "Höhe der Naht: oben am Balken = Naht oben (0°), unten = 180°, in der Mitte = seitlich. Durchgezogen liegt "
           "die Naht auf der sichtbaren Seite (Ansicht von der Seite: 90°, Ansicht von oben: 0°), gestrichelt auf der "
           "Rückseite. Hinter dem Stangentitel steht dazu einmal je Stange ein kleiner Querschnitt (von Ende A "
           "gesehen, Rechteckrohr mit der Breitseite oben) mit <b>rotem Punkt an der Naht</b> und dem Winkel, z. B. "
           "<i>Naht 90°</i>, sowie die Zahl der um die eigene Achse gedrehten Teile (<i>3 Teile gedreht</i>) oder "
           "<i>Naht unbekannt: nicht drehen</i>. Ohne Nahtvorgabe und ohne Drehung bleibt beides leer. Bleibt man "
           "mit der Maus auf einem Teil stehen, zeigt der Tooltip Naht, Drehung und Trennung zum Vorgänger.",
           "<b>Gehrungen ineinander</b> sind am Stoß mit grünen Schnittkanten markiert. Das gesparte Material steht "
           "einmal je Stange rechts oben (<i>Gehrungen ineinander: 173,4 mm gespart</i>). Diese Ersparnis ist in "
           "<b>Rest</b> und <b>Ausnutzung</b> schon enthalten: die Teile liegen um diesen Betrag enger, der Rest "
           "wird entsprechend länger. Das Stangenbild der Werkstattpapiere zeigt dasselbe.")
    i.abschnitt("Auswertung und nicht eingeplante Teile")
    i.bild("erg_auswertung", "Reiter Auswertung", hoehe=85 * mm)
    i.text("Je Gruppe: Stangen optimiert gegen eine einfache Einteilung von Hand, Verschnitt und Ausnutzung. Grün "
           "<b>✓ Alle Teile eingeplant.</b> oder rot die nicht eingeplanten Teile.", kurz=True)
    i.genauer()
    i.text("Je Gruppe (Profil + Werkstoff + Stangenlänge): Stangen optimiert gegen eine einfache manuelle Einteilung "
           "(Eingabereihenfolge, Stange voll, dann nächste), die rechnerische Untergrenze, Ersparnis, Verschnitt, "
           "Ausnutzung und eine Bewertung, ob das Ergebnis nachweislich optimal ist.",
           "Mit drehbaren Gehrungen rechnet die Optimierung die Gruppe zum Vergleich noch einmal ohne Drehen: "
           "<b>Stangen ohne Drehen</b> und <b>Gehrungen ineinander [mm]</b> zeigen den Unterschied, die Bewertung "
           "nennt ihn (<i>Drehen spart 1 Stange …</i>, <i>… Drehen spart keine Stange</i> oder <i>Drehen bringt "
           "keine Verbesserung</i>).",
           "Darunter steht grün <b>✓ Alle Teile eingeplant.</b> oder rot <b>Nicht eingeplante Teile</b> mit einer "
           "Tabelle: je Teil der Grund, z. B. Teil länger als die Nutzlänge der Stange, Profil über der "
           "Maschinengrenze oder fehlende Angaben. Diese Teile fehlen in Schnittplan, Kalkulation und Angebot, bis "
           "der Grund behoben ist.")
    i.abschnitt("Lieferlängen: 6 m gegen 12 m", marke="lieferlaengen")
    i.bild("erg_lieferlaengen", "Fenster Lieferlängen (Knopf 12-m-Lösung ansehen …): 30 Stützen 3.100 mm, 12 m "
                                "spart ein Drittel Material", hoehe=110 * mm,
           legende=[(1, "Vergleich je Gruppe mit Empfehlung, Begründung und Link zum Übernehmen")])
    i.text("Gibt es ein Profil auch in 12 m, vergleicht das Programm 6 m gegen 12 m. Lohnt sich 12 m, erscheint in "
           "der Auswertung <b>12-m-Lösung ansehen …</b>.", kurz=True)
    i.genauer()
    i.text("Gibt es für ein Profil + Werkstoff weitere Lieferlängen (Stammdaten <i>Lieferlängen</i>, z. B. "
           "12.000 mm), plant das Programm beim Optimieren jede Länge unter gleichen Bedingungen (gleiche Teile, "
           "Endbeschnitt, Greiferrest, Schnittverlust, gemeinsame Schnitte) und vergleicht sie. <b>Nur wenn eine "
           "sinnvolle Lösung gefunden wurde</b> (12 m empfohlen, nur 12 m lieferbar oder 12 m schon geplant), "
           "erscheint im Reiter <i>Auswertung</i> unten der Knopf <b>12-m-Lösung ansehen …</b> mit einem Kurztext; er "
           "öffnet den Vergleich <b>Lieferlängen: 6 m gegen 12 m</b> groß in einem eigenen Fenster. Ohne Eintrag gilt das für Profile mit "
           "Hüllkreis-Ø über 70 mm (Einstellung). Kleinere Profile ohne Eintrag und Profile mit "
           "<i>Lieferlängen vergleichen = nein</i> werden nie mit 12 m geplant. <b>Verglichen wird nur, wenn es in den "
           "Einstellungen (Gruppe Lieferlängen) eingeschaltet ist</b>: <i>beim Optimieren andere Lieferlängen "
           "vergleichen</i> = ja. Vorgabe ist <i>nein</i>, weil der Vergleich bei großen Gruppen Zeit kostet; "
           "dann wird nur mit der Stangenlänge des Angebots geplant, außer sie ist für ein Profil nicht lieferbar.")
    i.liste("<b>Die Maschine lädt nie eine 12-m-Stange.</b> Ist eine Lieferlänge länger als die <i>Max. "
            "Stangenlänge</i> der Maschine (Beladelänge, T03: 6.500 mm), schneidet der Lieferant jede Stange in "
            "Werkstücke, die einzeln geladen werden, z. B. 3 × 4.000 mm, 2 × 6.000 mm oder 6.500 + 5.497 mm. Kein "
            "Werkstück ist länger als die Beladelänge.",
            "<b>Keine zugeschnittene Stange ist kürzer als die <i>Min. Stangenlänge Zuschnitt</i> der Maschine</b> "
            "(Vorgabe 2.500 mm), damit die automatische Stangenladung sie nimmt. Eine kürzere Stange (z. B. für die "
            "letzten Teile einer Abmessung) wird auf die Mindestlänge verlängert, der Mehrbedarf ist Verschnitt. "
            "Ziel-Längen "
            "unter der Mindestlänge (z. B. 12 m / 5) werden nicht ausprobiert.",
            "<b>Die Restlänge der 12-m-Stange kommt an die letzte Stange</b>, solange diese dadurch nicht länger als "
            "die Beladelänge wird. Das spart einen Sägeschnitt. Beispiel (T03, 50 mm Puffer): 2 × 4.000 + 1 × 2.900 "
            "mm werden zu 4.203 + 4.203 + 3.588 mm statt 4.203 + 4.203 + 3.103 mm + Abfall – eine 12-m-Stange statt "
            "drei 6-m-Stangen. "
            "Passt die Restlänge nicht dran, ist sie Abfall und erscheint nicht als Stange.",
            "Ein Werkstück = Endbeschnitt + Teile + Trennschnitte + Schnittverlust + Greiferrest, auf ganze mm "
            "aufgerundet, plus <b>Puffer</b> (Einstellung, Vorgabe 50 mm), damit nicht auf den Millimeter genau "
            "zugeschnitten wird; der Puffer ist Verschnitt. Zwischen zwei Werkstücken geht der Schnittverlust des Zuschnitts verloren (Einstellung, "
            "Vorgabe 3 mm). Passen Werkstücke deshalb nicht mehr zusammen in die Stange, kommen sie auf die nächste.",
            "Gerechnet wird zweistufig: erst die Teile zu Werkstücken (dieselbe Optimierung wie bei normalen "
            "Stangen, mit mehreren Ziel-Längen: Beladelänge, Lieferlänge / 2, / 3 …), dann die Werkstücke auf die "
            "Lieferstangen. Es gilt die Planung mit den wenigsten Stangen, dann den wenigsten Beladungen. Eine "
            "eigene Kontrolle prüft, dass kein Werkstück und keine Stange überbelegt ist und jedes Teil genau einmal "
            "vorkommt.",
            "Längen bis zur Beladelänge (z. B. 6.500 mm) werden direkt geladen, ohne Zuschnitt.",
            "Reste bleiben Verschnitt. Es gibt keine Reststückverwaltung: nichts wird gespeichert oder in einem "
            "späteren Angebot wiederverwendet; ein Reststückwert wird nicht angerechnet.")
    i.text("<b>Gesamtkosten je Variante</b> = Materialkosten (Stangen × Preis der Lieferlänge) + Stangenwechsel und "
           "Arbeitsschritte je Stange für jede Beladung + Kosten je Zuschnitt beim Lieferanten (Vorgabe 0 €: die "
           "12-m-Stangen kommen geschnitten ohne Zusatzkosten). Laserzeit und Schnittwege sind in allen Varianten "
           "gleich. Die Tabelle zeigt je Variante Stangen, Beladungen, Zuschnitte, Stangenlängen nach Zuschnitt, Materiallänge, "
           "Materialkosten, Stangenwechsel, Zuschnittkosten, Reststückwert (nicht angerechnet), Gesamtkosten, "
           "Verschnitt in mm und % und fehlende Angaben.")
    i.tabelle(["Empfehlung", "Wann"], [
        ["<b>6-m-Stangen empfohlen</b>", "Profil ausgenommen oder keine ausführbare andere Lieferlänge"],
        ["<b>12-m-Stangen wirtschaftlich sinnvoll</b>",
         "die Ersparnis erreicht beide Mindestwerte aus den Einstellungen (Vorgabe 20 € und 3 % je Gruppe)"],
        ["<b>Kein ausreichender Kostenvorteil für 12 m</b>", "Ersparnis unter einem Mindestwert, gleiche Kosten "
                                                             "oder 12 m teurer (z. B. durch einen Längenzuschlag)"],
        ["<b>Vergleich nicht möglich – Angaben fehlen</b>",
         "ein Preis fehlt (z. B. Preise in €/Stange für 6 m, aber kein Preis für 12 m) oder der Stangenwechsel der "
         "Maschine fehlt, obwohl die Varianten verschieden viele Beladungen haben. Fehlende Werte zählen nie als 0."],
        ["<b>6 m nicht lieferbar – 12-m-Stangen verwenden</b>",
         "für Profil + Werkstoff ist die Stangenlänge des Angebots nicht als Lieferlänge hinterlegt; es gibt keine "
         "künstliche 6-m-Variante, das Programm plant gleich mit 12 m"]], [70, 195])
    i.text("<b>Übernehmen erst auf Klick:</b> Die Planung bleibt bei der Stangenlänge des Angebots, bis unter dem "
           "Vergleich <i>12-m-Stangen übernehmen</i> geklickt wird. Dann optimiert das Programm neu: Schnittplan, "
           "Stangenbild, Material, Stangenwechsel (je Beladung), Kalkulation, Werkstattpapiere und Nachkalkulation "
           "rechnen mit den 12-m-Stangen. <i>Wieder 6-m-Stangen verwenden</i> macht es rückgängig. Die Wahl gilt je "
           "Gruppe und bleibt bei Kopien des Angebots erhalten.")
    i.text("<b>Schnittplan, Stangenbild und Werkstattpapiere zeigen die Stangen so, wie die Maschine sie lädt:</b> "
           "jedes zugeschnittene Stück erscheint als eigene Stange mit Endbeschnitt, Teilen, Schnittverlust und "
           "Greiferrest, genau wie eine normale Stange. Der Zuschnitt der 12-m-Stange selbst wird dort nicht gezeigt. "
           "Gerechnet wird er trotzdem: Material und Kosten zählen die 12-m-Stangen, der Schnittverlust des Zuschnitts "
           "(Einstellung, Vorgabe 3 mm) ist eingerechnet. Es wird immer die ganze 12-m- bzw. 6-m-Stange berechnet; "
           "Abfall verteilt sich gleichmäßig nach Länge auf alle Teile und Stücke der Gruppe – auch ein Stück, das "
           "allein auf einer 12-m-Stange liegt, trägt nur seinen Längenanteil.")
    i.text("<b>Händler-Mehrlänge:</b> Der Händler berechnet je Stange etwas mehr Länge, als geliefert wird (Vorgabe "
           "+50 mm bis 6.500 mm, z. B. 6 m, und +100 mm darüber, z. B. 12 m; Einstellungen, Gruppe Lieferlängen). "
           "Das gilt nur für den Materialpreis nach Länge oder Gewicht (€/m, €/kg, Tonnenpreis), nicht für die "
           "Längenplanung und nicht für Preise je Stange. Der angezeigte Meterpreis im Angebot bleibt ohne "
           "Mehrlänge.")
    i.bild("erg_lieferlaengen_bild", "Stangenbild nach dem Übernehmen: jedes zugeschnittene Stück als eigene Stange mit "
                                     "Endbeschnitt und Greiferrest", hoehe=80 * mm)
    i.liste("Schnittplan: je Stück eine Zeile mit seiner Länge (z. B. 3.253 mm), Von/Bis der Teile im Stück.",
            "Werkstattpapiere: die Materialliste nennt die zu ladenden Stücke (Länge und Anzahl), die Schnittpläne "
            "gelten je Stück.",
            "Staffelpreise: je Mengenstufe vergleicht das Programm selbst und nimmt die empfohlene Lieferlänge "
            "([[staffeln]]).")
    i.bild("erg_lieferlaengen_geplant", "Nach dem Übernehmen: 12-m-Variante geplant, Link zurück auf 6 m",
           hoehe=90 * mm)


def kapitel_staffeln(i):
    i.kapitel("Staffelpreise", marke="staffeln")
    i.bild("staffeln_vorher", "Stufen für den Satz „MG 2000“ (ein Maschinengestell)", hoehe=80 * mm, legende=[
        (1, "<b>Neue Stufe …</b> legt eine Stufe mit den Mengen des Angebots an und öffnet ihr Fenster; dort die "
            "Mengen ändern. <b>Stufen löschen</b> entfernt die markierten Stufen mit ihren Mengen. "
            "<b>Standard-Staffeln</b> legt je Faktor aus den Einstellungen eine Stufe mit den Mengen des Angebots × "
            "Faktor an (Vorgabe 1; 2; 5)."),
        (2, "<b>Stufe bearbeiten …</b> (oder Doppelklick auf die Stufe) öffnet das Fenster der Stufe."),
        (3, "Je Zeile eine Stufe: Bezeichnung, Mengen, eigene Werte (oder „wie Angebot“), Netto gesamt und "
            "Prüfung („gemeinsamer Auftrag“ bei mehreren Sätzen und Positionen, sonst der Fehler)."),
        (4, "<b>Staffelpreise rechnen</b> rechnet alle Stufen neu. Nötig ist das selten: Gewinn und Zuschläge wirken "
            "sofort, neue Mengen, Materialpreise, Fracht und Änderungen am Angebot rechnet das Programm nach kurzer "
            "Zeit im Hintergrund nach.")])
    i.text("Reiter <i>Staffeln</i>: Preise für weitere Mengen. Jede <b>Stufe</b> wird wie ein eigener Auftrag "
           "optimiert und kalkuliert; Rüsten, Verschnitt und Pauschalen verteilen sich auf ihre Menge. Ein "
           "Doppelklick auf eine Stufe öffnet ihre Werte.", kurz=True)
    i.genauer()
    i.text("Im Reiter <i>Staffeln</i> rechnet das Programm Preise für andere Mengen. Eine <b>Stufe</b> ist wie ein "
           "eigener Auftrag: Sie hat Mengen für einen oder mehrere Sätze und Positionen, und alle werden zusammen "
           "optimiert und kalkuliert. Rüsten, Stangenwechsel, Verschnitt, Programmierkosten, Pauschalen, "
           "Angebotsaufschlag, Fracht und Mindestpreis verteilen sich auf alle Positionen der Stufe, genau wie im "
           "Angebot. Hat eine Stufe dieselben Mengen wie das Angebot und keine eigenen Werte, ergibt sie Cent für "
           "Cent die Preise des Angebots. Das eigentliche Angebot bleibt unverändert.")
    i.text("Jede Stufe hat dieselben Einstellungen wie das Angebot (Gewinn, Zuschlag Fremdleistung, Rüstzeit und "
           "Pauschale je Abmessung, Programmierkosten, Angebotsaufschlag, Handling Kundenmaterial, Fracht, Skonto) "
           "und einen eigenen Materialpreis €/m je Abmessung. Leere Felder nehmen den Wert des Angebots. Die "
           "Lieferlängen sind dieselben wie im Angebot; mit <b>Lieferlänge je Stufe wählen</b> = ja (unter "
           "Erweitert) nimmt die Stufe die empfohlene Lieferlänge für ihre Mengen ([[lieferlaengen]]), bei großen "
           "Mengen also z. B. 12 m.")
    i.bild("staffel_stufe", "Fenster einer Stufe: Einstellungen, Materialpreise und Mengen", hoehe=110 * mm, legende=[
        (1, "Einstellungen wie im Angebot. Leere Felder zeigen grau den Wert des Angebots."),
        (2, "<b>Frachtkosten</b>: fester Betrag für die ganze Stufe; leer = Fracht wie im Angebot (mit der Frachtart "
            "<i>berechnet</i> für die Mengen der Stufe)."),
        (3, "<b>Erweitert</b>: Materialzuschlag, Verlust, Grundpreis, Gemeinkosten, Rüsten separat, zusätzlicher "
            "Arbeitsgang, Nebenkosten, Rabatt und Lieferlänge je Stufe (Tabelle unten)."),
        (4, "<b>Materialpreis je Abmessung</b> (Profil · Werkstoff): €/m im Angebot grau, daneben der Preis für diese "
            "Stufe (leer = wie im Angebot). Er gilt für alle Positionen dieser Abmessung in der Stufe."),
        (5, "<b>Positionen und Mengen</b>: Häkchen = Satz bzw. Position gehört zur Stufe (neue Stufe: alle "
            "angehakt; <b>Alle</b> / <b>Keine</b> haken alle an bzw. ab). Mengen in Sätzen bzw. Stück; eine Menge "
            "eintragen hakt die Zeile an. <b>Mengen des Angebots</b>, <b>× 2</b>, <b>× 5</b> und <b>× 10</b> füllen "
            "die angehakten Zeilen. <b>Menge bis</b> ist freiwillig.")])
    i.text("<b>Standard-Staffeln automatisch</b>: Hat das Angebot noch keine Stufe, legt das <b>Angebots-PDF</b> die "
           "Standard-Staffeln selbst an und rechnet sie, z. B. für 10 Stück die Stufen 10, 20 und 50. Die Faktoren "
           "stehen in den Einstellungen, Gruppe Angebot, unter <i>Standard-Staffeln: Faktoren auf die "
           "Bestellmenge</i> (leer = aus; Komma für Dezimalzahlen, z. B. 0,5); eigene Faktoren je Kunde stehen in den "
           "Kundenvorgaben ([[kundenvorgaben]]). Wer alle Stufen löscht, bekommt sie "
           "beim nächsten PDF nicht wieder, solange das Angebot geöffnet bleibt.")
    i.text("Für Sätze in den Positionen die Spalten <b>Satz</b> (gleicher Name für alle Teile des Satzes) und "
           "<b>Stück je Satz</b> ausfüllen. Im Beispiel gehören zu einem Gestell 4 Stiele, 4 lange Riegel, "
           "8 kurze Riegel, 16 Streben, 2 Holme und 3 Traversen.")
    i.abschnitt("Werte je Stufe")
    i.tabelle(["Feld", "Bedeutung (leer = …)"], [
        ["Gewinn, Zuschlag Fremdleistung, Rüstzeit und Pauschale je Abmessung, Programmierkosten, "
         "Angebotsaufschlag, Handling Kundenmaterial, Skonto", "wie die Felder im Angebot, nur für diese Stufe "
                                                              "(leer = Wert des Angebots)"],
        ["Frachtkosten", "fester Betrag für die Stufe (leer = wie im Angebot)"],
        ["Materialpreis je Abmessung", "€/m für alle Positionen dieser Abmessung in der Stufe (leer = wie im "
                                       "Angebot)"],
        ["Häkchen", "Satz bzw. Position gehört zur Stufe; ohne Häkchen ist sie nicht in dieser Stufe (ihre Menge "
                    "zählt nicht)"],
        ["Menge ab", "Kalkulationsmenge der Stufe (Mindestmenge) in Sätzen bzw. Stück je Satz bzw. Position"],
        ["Menge bis", "Höchstmenge; leer = bis zur nächsten Stufe desselben Satzes bzw. derselben Position − 1, "
                      "bei der höchsten Stufe offen („ab …“)"],
        ["Materialzuschlag, Zuschlag in", "Zuschlag auf die Materialkosten nach Verlust, in % oder als fester "
                                          "Betrag €/Einheit. Ersetzt für diese Stufe den Zuschlag Material der "
                                          "Einstellungen (leer = Zuschlag Material der Einstellungen)"],
        ["Gewinn", "in % auf die Selbstkosten (leer = Gewinn des Angebots)"],
        ["Materialverlust / Ausschuss", "in % auf die Material-Grundkosten, zusätzlich zum echten Verschnitt der "
                                        "Stangen (der steckt schon in den Grundkosten); leer = 0"],
        ["Material-Grundpreis abweichend", "fester Material-Grundpreis €/Einheit statt der gerechneten "
                                           "Stangenkosten"],
        ["Gemeinkosten Fertigung", "in % auf Fertigung und Rüsten, nicht auf Material (leer = Zuschlag "
                                   "Fertigung des Angebots)"],
        ["Rüstkosten", "umlegen (leer) = im Stückpreis; separat = im Reiter als einmalige Rüstkosten neben dem "
                       "Stückpreis (im Angebots-PDF trotzdem im Preis je Einheit enthalten)"],
        ["Zusätzlicher Arbeitsgang", "Bezeichnung, Arbeitsgang [min/Einheit] mit Arbeitsgang Stundensatz "
                                     "(leer = Maschinenstundensatz) und/oder Arbeitsgang [€/Einheit]"],
        ["Verpackung / Nebenkosten", "€/Einheit und Nebenkosten pauschal € für die Stufe; zählen zu den "
                                     "Selbstkosten"],
        ["Rabatt erlaubt", "ja = negativer Materialzuschlag und negativer Gewinn sind erlaubt (sonst abgelehnt)"],
        ["Lieferlänge je Stufe wählen", "ja = empfohlene Lieferlänge für die Mengen der Stufe (leer = Lieferlängen "
                                        "des Angebots)"],
    ], [55 * mm, 200 * mm])
    i.abschnitt("Blechteile je Stufe")
    i.text("Blech- und Kantteile bekommen in jeder Stufe den Preis für deren Stückzahl.", kurz=True)
    i.genauer()
    i.text("Blech- und Kantteile aus dem Blech-Editor ([[blech_editor]]) bekommen in jeder Stufe den Preis für "
           "deren Stückzahl: Hat der Einkauf beim Zukaufartikel einen Einkaufspreis ab einer Stückzahl eingetragen, "
           "die die Stufe erreicht, gilt dieser EK. Sonst rechnet das Programm den Richtpreis für die Stückzahl der "
           "Stufe neu (das Rüsten verteilt sich auf mehr oder weniger Teile). Die Prüfung der Stufe zeigt, was "
           "galt, z. B. „Pos. 3 Blech: EK Einkauf ab 50 St“. Hat die Stufe die Stückzahl des Angebots, bleibt der "
           "Preis des Angebots. Einen neuen EK aus dem Einkauf holt <b>Aus Stammdaten aktualisieren …</b> im Dialog "
           "Zukaufteile der Position bzw. <b>Im Angebot aktualisieren …</b> unter Preisänderungen ins Angebot "
           "([[zukauf]]).")
    i.abschnitt("Rechenweg je Stufe")
    i.bild("staffeln", "Ergebnis mit Materialzuschlag 20/15/10/5 %: der Preis je Gestell sinkt mit der Menge",
           hoehe=95 * mm, legende=[
               (1, "Wert direkt in der Stufe ändern: der Preis rechnet sofort neu, ohne neue Optimierung."),
               (2, "Kostenpositionen in Gruppen; ▸ klappt sie auf (<b>Alle aufklappen</b> öffnet alle). Je Stufe "
                   "zwei Spalten: € je Einheit und gesamt."),
               (3, "<b>Selbstkosten</b>"),
               (4, "<b>Verkaufspreis netto je Einheit</b>, darunter Gewinn und Gewinnmarge (vom Nettopreis)."),
               (5, "<b>Gesamtpreis netto</b>, <b>Umsatzsteuer</b> und <b>Gesamtpreis brutto</b>."),
               (6, "<b>Staffelkurve</b>: Verkaufspreis netto je Einheit über die Mengen, je Satz bzw. Position ein "
                   "eigenes Feld mit Preis an jedem Punkt; die Achse beginnt bei 0."),
               (7, "Stand: aktuell, VERALTET (wird im Hintergrund neu gerechnet) oder Stufen mit FEHLER.")])
    i.text("Von den Kosten der Stufe über Materialzuschlag, Gewinn und Nebenkosten bis zum Stückpreis brutto; "
           "<b>Details</b> zeigt jeden Schritt.", kurz=True)
    i.genauer()
    i.text("Die Stufe wird mit ihren Mengen optimiert und kalkuliert wie ein Auftrag. Daraus kommen je Satz bzw. "
           "Position die Kostenbausteine; darauf wirken die Werte der Stufe in dieser Reihenfolge:")
    i.liste("<b>Material-Grundkosten</b>: Stangenkosten dieser Menge inkl. echtem Verschnitt (oder Grundpreis "
            "abweichend × Menge).",
            "<b>Materialverlust</b>: Grundkosten × Verlust %.",
            "<b>Materialzuschlag</b>: (Grundkosten + Verlust) × Zuschlag % oder Zuschlag € × Menge.",
            "<b>Fertigungskosten</b>: je Arbeitsschritt Zeit × Stundensatz (Reiter Zeiten &amp; Arbeitskosten) plus "
            "zusätzlicher Arbeitsgang; <b>Rüsten</b> (Rüstzeiten × Stundensatz) einmal je Stufe, getrennt davon.",
            "<b>Gemeinkosten</b>: (Fertigung + Rüsten) × Gemeinkosten Fertigung; Fremdleistung × Zuschlag "
            "Fremdleistung.",
            "<b>Herstellkosten</b> = Material + Fertigung + Rüsten + Gemeinkosten + Fremdleistung + Verpackung / "
            "Nebenkosten.",
            "<b>Selbstkosten</b> = Herstellkosten + Programmierung, Pauschalen, Aufschlag (ohne Zuschläge) + "
            "Zukaufteile (eigener Aufschlag statt Zuschläge).",
            "<b>Gewinn</b> = Selbstkosten × Gewinn % ([[gewinn_basis]]); dazu die Fracht ohne Gewinn, Skonto "
            "eingerechnet = <b>Gesamtpreis netto</b>; dazu Umsatzsteuer = <b>Gesamtpreis brutto</b>.",
            nummeriert=True)
    i.text("Gerechnet wird ungerundet; erst der Verkaufspreis netto je Einheit wird auf Cent gerundet "
           "(kaufmännisch), der Gesamtpreis ist Stückpreis × Menge (plus einmalige Rüstkosten). Ohne Werte je Stufe "
           "ergibt das genau den Preis der Kalkulation. Im Angebots-PDF stehen keine Extra-Kosten: einmalige "
           "Rüstkosten sind dort in den Preis je Einheit eingerechnet (auf den Cent aufgerundet).")
    i.text("<b>Fracht je Menge</b>: Mit der Frachtart <i>berechnet</i> (Karte Fracht im Angebot) rechnet jede Stufe "
           "ihre eigene Fracht: Nettogewicht und längstes Teil der Stufe, Ladungsträger per Packvorschlag, Fracht mit "
           "der gespeicherten Tarifkopie des Angebots. Verpackungsgewicht und frachtpflichtiges Gewicht von Hand "
           "gelten nur für die Menge des Angebots; die Stufen rechnen nach Tarif. Der Hinweis der Stufe nennt die "
           "Fracht, das Bruttogewicht und die Ladungsträger, z. B. „Fracht 445,48 €: 1.081,5 kg brutto, 1 × LG“. "
           "Innerhalb der Stufe wird die Fracht wie im Angebot je Stück oder nach Gewicht verteilt. Ändert sich die "
           "Frachtberechnung, sind die Stufen veraltet und werden neu gerechnet. Fehlt die Berechnung oder ein "
           "Gewicht, bekommt die Stufe keinen Preis und den Hinweis „Fracht nicht berechnet: …“, statt still mit "
           "0 € zu rechnen. In den übrigen Frachtarten gilt der Frachtbetrag des Angebots für alle Mengen gleich.")
    i.bild("staffeln_details", "Aufgeklappt mit erweiterten Einstellungen: Arbeitsschritte, Rüsten separat, "
                               "Nebenkosten", hoehe=95 * mm, legende=[
               (1, "Fertigung je Arbeitsschritt; der Tooltip zeigt Zeit und Stundensatz."),
               (2, "Rüsten Maschine, Rüsten je Abmessung und Rüstzeiten weiterer Arbeitsschritte."),
               (3, "Gemeinkosten mit ihrer Basis."),
               (4, "Einmalige Rüstkosten (Rüstkosten = separat): nicht im Stückpreis, aber im Gesamtpreis."),
               (5, "Änderung des Preises je Einheit zur letzten Eingabe, in € und %.")])
    i.abschnitt("Prüfung und Fehler")
    i.text("Rote Stufen haben einen FEHLER (z. B. keine Menge oder überschneidende Mengen) und werden nicht "
           "ausgegeben.", kurz=True)
    i.genauer()
    i.liste("Rot markiert und mit FEHLER in der Prüfung: keine Menge, Menge doppelt (gleicher Satz bzw. Position in "
            "zwei Stufen mit denselben Sätzen und Positionen), "
            "Menge bis kleiner als Menge ab, sich überschneidende Mengenbereiche, Prozentwerte außerhalb des "
            "zulässigen Bereichs, negative Werte ohne „Rabatt erlaubt“.",
            "Fehlt der Materialpreis (keine Preise in den Stammdaten, kein Schnittplan), rechnet das Programm nicht "
            "mit 0: die Stufe zeigt „FEHLER: Materialpreis fehlt“ und bekommt keinen Preis.",
            "Stufen mit FEHLER kommen nicht ins Angebot.")
    i.text("Die Staffelpreise erscheinen im Angebots-PDF direkt in ihrer Position: unter der Zeile mit "
           "Menge und Preis je Einheit eingerückt je Stufe eine Zeile „Ab 50 Stk. je“ (bei Sätzen „Ab 4 Sätze je“) "
           "mit dem Staffelpreis, aufsteigend nach Menge, danach der übrige Positionstext. Staffelzeilen haben keinen "
           "Gesamtpreis und zählen nicht zur Summe. Hat eine Stufe mehrere Sätze bzw. Positionen, beginnt die Zeile mit "
           "der Stufe („Stufe 2: Ab 50 Stk. je“), und darunter steht grau „Staffelpreise je Stufe bei gemeinsamer "
           "Bestellung aller Positionen dieser Stufe“. Bei einer Stufe mit nur einer Position steht dort "
           "„Staffelpreise bei Einzelbestellung dieser Position“ (bzw. „dieses Satzes“): Sie trägt Rüsten, "
           "Pauschalen und Mindestpreis allein und kann deshalb teurer sein als der Preis im Gesamtangebot. Eine "
           "Stufe mit gleicher Menge und gleichem Preis wie die Position entfällt dort. Ändert sich etwas am "
           "Angebot, zeigt der Reiter VERALTET und rechnet nach; das Angebot rechnet veraltete Staffelpreise "
           "vor dem Drucken ebenfalls selbst neu.")
    i.text("Ältere Angebote (vor Version 0.8.0): Beim ersten Öffnen mit dieser Version werden ihre Mengenstufen zu "
           "Stufen zusammengefasst, je Satz bzw. Position der Größe nach: die kleinste Menge in Stufe 1, die nächste in "
           "Stufe 2 usw. Widersprechen sich die Werte zweier Zeilen (z. B. verschiedener Gewinn), bekommt die Zeile "
           "eine eigene Stufe. Vorher legt das Programm im Ordner Sicherung die Sicherung „vor_Schema_36“ an.")


def kapitel_fracht(i):
    i.kapitel("Fracht im Angebot", marke="fracht")
    i.text("Fracht kommt über die Karte <b>Fracht</b> ins Angebot: manuell, berechnet oder automatisch. "
           "Gerechnet wird mit den Tarifen aus dem Reiter <i>Frachtkosten</i> ([[frachtkosten]]).", kurz=True)
    i.genauer()
    i.text("Die Fracht kommt auf zwei Wegen ins Angebot: über die Karte <b>Fracht</b> im Angebot (manuell, "
           "berechnet oder automatisch) und über den Frachtrechner im Reiter <i>Frachtkosten</i>. Zonen, Tarife, "
           "Ladehilfsmittel und Zuschläge, mit denen gerechnet wird, werden im Reiter <i>Frachtkosten</i> gepflegt "
           "([[frachtkosten]]).")
    i.abschnitt("Karte Fracht im Angebot", marke="fracht_angebot")
    i.bild("angebot_fracht", "Karte Fracht: Frachtart berechnet, verteilt nach Gewicht", hoehe=40 * mm, legende=[
        (1, "<b>Frachtart</b>"), (2, "<b>Fracht verteilen</b>"), (3, "<b>Fracht berechnen …</b>"),
        (4, "Betrag, Tarif, Gewicht, Ladungsträger und Ziel der Berechnung"),
        (5, "<b>Fracht automatisch berechnen</b> mit Ziel-PLZ und Land (unten)")])
    i.text("<b>Frachtart</b> wählen: <i>manuell</i> (Betrag eintragen), <i>berechnet</i> (mit <b>Fracht berechnen "
           "…</b>), <i>keine Fracht</i> oder <i>im Artikelpreis enthalten</i>. Mit dem Haken <b>Fracht automatisch "
           "berechnen</b> und der Ziel-PLZ hält das Programm die Fracht selbst aktuell.", kurz=True)
    i.genauer()
    i.text("Unter der Kalkulation steht die Karte <b>Fracht</b>. Sie legt fest, wie die Fracht in dieses Angebot "
           "eingeht.")
    i.tabelle(["Frachtart", "Wirkung"], [
        ["manuell", "wie bisher: der Betrag im Feld Frachtkosten (Gruppe Verkauf und Gewinn); in den Staffelpreisen "
                    "gilt er für alle Mengen gleich. Ältere Angebote haben diese Frachtart."],
        ["berechnet", "Betrag aus <b>Fracht berechnen …</b>; das Feld Frachtkosten ist dann nur zur Anzeige. In den "
                      "Staffelpreisen rechnet jede Menge ihre eigene Fracht ([[staffeln]])."],
        ["keine Fracht", "Abholung oder ab Werk: 0 € Fracht in der Kalkulation; das Angebots-PDF nennt „Lieferung ab "
                         "Werk; Frachtkosten sind nicht enthalten.“"],
        ["im Artikelpreis enthalten", "0 € Fracht in der Kalkulation, damit die Fracht nicht doppelt berechnet wird; "
                                      "das Angebots-PDF nennt „Die Frachtkosten sind in den Preisen enthalten.“"]],
        [45, 220])
    i.liste("<b>Fracht verteilen</b>: <i>je Stück</i> (jedes Teil trägt gleich viel, wie bisher) oder <i>nach "
            "Gewicht</i>: Fracht je Teil = Fracht gesamt × Teilegewicht ÷ Gesamtgewicht aller Teile. Beispiel: 120 € "
            "Fracht, Pos. 1 mit 100 Stück zu 2 kg, Pos. 2 mit 10 Stück zu 20 kg: je 200 kg, also 0,60 € je Teil in "
            "Pos. 1 und 6,00 € je Teil in Pos. 2. Neue Angebote verteilen nach Gewicht; ältere Angebote und ihre "
            "Kopien bleiben bei je Stück, damit sich ihre Preise nicht ändern. Fehlt einer Position das Gewicht "
            "(kein Profil oder Werkstoff mit Dichte), verteilt das Programm in diesem Angebot je Stück und zeigt den "
            "Hinweis „Gewicht fehlt bei Pos. …“ in der Karte.",
            "<b>Fracht berechnen …</b> öffnet den Frachtrechner ([[fracht_rechner]]), vorbelegt mit dem Nettogewicht und dem "
            "längsten Teil aus den Positionen, dem Kunden (PLZ, Land, Lieferbedingung aus dem Kundenstamm), dem "
            "Angebotsdatum und einem Packvorschlag. Eine schon gespeicherte Berechnung wird mit ihren Eingaben "
            "wieder geöffnet; Gewicht und längstes Teil kommen immer neu aus dem Angebot. <b>Ins Angebot "
            "übernehmen</b> schreibt den Betrag ins Feld Frachtkosten, setzt die Frachtart auf berechnet und "
            "speichert die Eingaben mit einer Kopie aller Tarifwerte (Feld Frachtberechnung (Eingaben und "
            "Tarif-Snapshot), nicht sichtbar) sowie einen Eintrag in der Historie der Frachtkosten. Spätere "
            "Änderungen an Tarifen ändern das Angebot nicht; für neue Tarifwerte die Fracht neu berechnen und "
            "übernehmen. Mit der Lieferbedingung unfrei, ab Werk oder Abholung wird die Frachtart keine Fracht.",
            "Ist die Frachtart berechnet und der Betrag größer 0, nennt das Angebots-PDF „Die Preise enthalten die "
            "Fracht frei Haus nach DE 25980.“ (Land und PLZ der Berechnung).")
    i.text("<b>Fracht automatisch berechnen</b> (Haken in der Karte Fracht, bei neuen Angeboten aus): Das Programm "
           "rechnet die Fracht selbst und hält sie bei jeder Änderung der Positionen aktuell. Daneben stehen "
           "<b>Ziel-PLZ</b> und <b>Land</b> (Felder Ziel-PLZ (Fracht) und Zielland (Fracht)); die ersten zwei Ziffern "
           "reichen, z. B. 25 für alle PLZ, die mit 25 beginnen.")
    i.liste("Beim Setzen des Hakens kommen Ziel-PLZ (volle PLZ, damit die Zone genau stimmt) und Land aus dem "
            "Kunden: abweichende Lieferanschrift, sonst PLZ bzw. PLZ Ort der Anschrift. Wechselt der Kunde, wechselt auch das Ziel.",
            "Gewicht und längstes Teil kommen aus den Positionen, die Ladungsträger aus dem Packvorschlag, der Tarif "
            "wird automatisch gewählt. Die Versandart steht in den Einstellungen der Frachtkosten (<b>Versandart für "
            "automatische Fracht</b>, z. B. Stückgut). Ohne sie können zwei Tarife gleich gut passen; dann rechnet "
            "das Programm nicht, sondern meldet es. Zuschläge gelten nur mit der Bedingung <i>immer</i> bzw. über "
            "Zone und Gewicht, keine Zusatzleistungen wie Avis oder Hebebühne.",
            "Tarifkopie: Zone und alle Tarifwerte werden beim Setzen des Hakens und beim Ändern der Ziel-PLZ "
            "festgehalten. Jede Änderung am Angebot (Stückzahl, Länge, Profil, Werkstoff, neue oder gelöschte "
            "Position) rechnet die Fracht sofort mit dieser Kopie neu und schreibt sie ins Feld Frachtkosten. Spätere "
            "Tarifänderungen wirken erst, wenn die Ziel-PLZ neu eingegeben oder der Haken neu gesetzt wird.",
            "Liegt der PLZ-Bereich in mehreren Zonen (z. B. 25 mit Festland und Inseln), rechnet das Programm jede "
            "Zone und nimmt die teurere; die Karte nennt alle Zonen mit ihrem Betrag.",
            "In den Staffelpreisen rechnet jede Menge ihre eigene Fracht ([[staffeln]]).",
            "Kann das Programm nicht rechnen (Ziel-PLZ fehlt, Gewicht fehlt, kein Tarif), steht der Grund rot in der "
            "Karte, das Feld Frachtkosten ist leer, die Kalkulation rechnet bis dahin ohne Fracht und der Angebots-Check "
            "nennt es in seiner Rückfrage vor dem Angebots-PDF ([[angebots_check]]). Es setzt nie still 0 € ein. Ist der Grund behoben (Gewicht "
            "eingetragen, Versandart in den Einstellungen gesetzt), rechnet die nächste Änderung oder das Zurückkehren "
            "ins Angebot die Fracht von selbst neu.",
            "Solange der Haken gesetzt ist, ist die Frachtart fest auf berechnet. Haken aus: der letzte Betrag bleibt "
            "stehen und die Frachtart ist wieder wählbar. <b>Fracht berechnen …</b> und <b>Ins Angebot übernehmen</b> "
            "nimmt den Haken heraus, damit die Automatik den Betrag von Hand nicht überschreibt.")
    i.abschnitt("Frachtrechner (Fracht kalkulieren)", marke="fracht_rechner")
    i.bild("fracht_rechner", "Fracht kalkulieren: Eingabe links, aufgeschlüsselte Kostenübersicht rechts "
           "(Beispieltarif)", hoehe=115 * mm, legende=[
        (1, "Unterreiter <i>Fracht kalkulieren</i>"), (2, "Versanddaten"), (3, "erkannte Frachtzone"),
        (4, "Gewicht"), (5, "Ladehilfsmittel"), (6, "<b>Packvorschlag</b>"), (7, "Zusatzleistungen"),
        (8, "Ergebnis"), (9, "<b>In Historie speichern</b>")])
    i.text("<b>Fracht berechnen …</b>: PLZ, Versandart und Ladehilfsmittel wählen, das Programm sucht den Tarif und "
           "zeigt rechts die Fracht mit allen Zuschlägen.", kurz=True)
    i.genauer()
    i.tabelle(["Nr.", "Bereich", "Bedeutung"], [
        ["2", "Versanddaten", "Absender-PLZ (Vorgabe aus den Einstellungen) und Empfänger-PLZ mit Land, Versandart, "
                              "Kunde (optional; füllt PLZ, Land und Lieferbedingung aus dem Kundenstamm), Frachtführer "
                              "(optional), Tarif (<i>automatisch</i> oder von Hand), Lieferbedingung, Datum (entscheidet "
                              "über gültige Tarife und den Dieselpreis) und eine Bezeichnung für die Historie"],
        ["3", "Frachtzone", "erscheint sofort unter der PLZ: grün mit der verwendeten Regel, gelb <i>keiner Zone "
                            "zugeordnet – Standardzone …</i>, rot ohne Zone oder bei mehrdeutigen Regeln"],
        ["4", "Gewicht", "Nettogewicht der Ware; darunter das Gesamtbruttogewicht = Netto + Verpackung (Eigengewicht "
                         "der Ladungsträger)"],
        ["5", "Ladehilfsmittel", "je Zeile Ladungsträger, Anzahl und optional Brutto je Stück (dann gilt die Summe als "
                                 "Bruttogewicht). <b>+ Ladungsträger</b> fügt eine Zeile an, <b>Ladungsträger "
                                 "entfernen</b> löscht die markierte. Darunter Anzahl, Stellplätze, Eigengewicht und "
                                 "Volumen."],
        ["6", "Packvorschlag", "füllt die Liste aus Nettogewicht und längstem Teil: Anzahl = Gewicht ÷ Nutzlast "
                               "(aufgerundet); Teile länger als die max. Teillänge des Ladungsträgers kommen auf "
                               "Langgut. Danach von Hand änderbar."],
        ["7", "Zusatzleistungen", "Zuschläge mit der Bedingung „nur wenn gewählt“ zum Ankreuzen (im Beispiel "
                                  "Avisierung, Hebebühne, Wartezeit mit Stunden). Ohne solche Zuschläge ist der Bereich "
                                  "ausgeblendet."],
        ["8", "Ergebnis", "verwendeter Frachtführer und Tarif mit dem Grund der Auswahl, Frachtzone, Gewicht und "
                          "frachtpflichtiges Gewicht mit Rechenweg, Ladehilfsmittel, verwendete Preisstaffel, jede "
                          "Position mit Betrag und Rechnung, Gesamtfrachtkosten, dazu Fehler, Warnungen, Hinweise, "
                          "nicht angewendete Zuschläge und weitere passende Tarife mit ihrem Preis"],
        ["9", "In Historie speichern", "legt die Kalkulation mit allen verwendeten Tarifwerten ab"]], [12, 40, 213])
    i.text("Unter <i>Erweiterte Einstellungen</i> (zugeklappt) stehen Verpackungsgewicht [kg] (leer = Eigengewicht der "
           "Ladungsträger), frachtpflichtiges Gewicht [kg] (leer = nach Tarif), Entfernung [km] (leer = Entfernung "
           "der Zone) und längstes Teil [mm] (für Langgut- und Überlängenzuschläge und den Packvorschlag).")
    i.text("Im schmalen Fenster (unter 1.100 Pixel Breite) steht das Ergebnis unter der Eingabe; ab 1.024 × 700 "
           "Pixel ist alles ohne waagrechtes Scrollen bedienbar. Das Programm läuft unter Windows, nicht auf dem "
           "Smartphone.")
    i.bild("fracht_schmal", "Rechner im Fenster 1024 × 700", hoehe=95 * mm)
    i.abschnitt("So rechnet das Programm")
    i.genauer()
    i.liste("<b>Zone</b> der Empfänger-PLZ aus den PLZ-Zuordnungen (Regeln unten), sonst die Standardzone des Landes "
            "mit Warnung.",
            "<b>Tarif</b>: aktiv, am Datum gültig, Land, Zone, Versandart, Frachtführer und Kunde passen. Vorrang: "
            "Kundentarif vor Rahmenvertrag vor Sondertarif vor Standardtarif, dann die kleinere Priorität. Passen "
            "zwei gleich gut, rechnet das Programm nicht still mit einem davon: es zeigt <i>Tarif wählen</i> und alle "
            "Kandidaten mit Preis. Interne Verrechnungstarife gelten nur, wenn sie von Hand gewählt sind.",
            "<b>Frachtpflichtiges Gewicht</b>: das Bruttogewicht oder, wenn der Tarif Faktoren hat, der größte Wert "
            "aus Volumen × kg je m³, Stellplätzen × kg je Stellplatz und Lademetern × kg je Lademeter; danach "
            "aufgerundet nach dem Tarif. Volumen und Stellplätze zählen nur, wenn der Tarif sie verwendet.",
            "<b>Grundfracht</b> aus den Preisstaffeln des Tarifs ([[tarife]]).",
            "<b>Rabatt</b> des Tarifs, danach <b>Anhebung auf Mindestfracht</b> als eigene Zeile.",
            "<b>Zuschläge</b>: erst die Beträge in Euro (je Sendung, kg, 100 kg, Ladungsträger, Stellplatz, Stunde), "
            "dann die Prozentzuschläge auf ihre Grundlage. Ein Prozentzuschlag rechnet nie auf sich selbst oder einen "
            "anderen Prozentzuschlag; so entstehen keine doppelten Zuschläge.",
            "<b>Währung</b>: Tarife in fremder Währung werden mit dem gepflegten Kurs in Euro umgerechnet.",
            "<b>Rundung</b>: jede Zeile kaufmännisch auf Cent; Gesamtfrachtkosten = Summe der Zeilen.",
            nummeriert=True)


def kapitel_zukauf_angebot(i):
    i.kapitel("Zukaufteile im Angebot", marke="zukauf_im_angebot")
    i.text("Eingekaufte Teile kommen als eigene <b>Zukaufteil-Position</b> (z. B. ein Blech) oder als <b>Zukaufteile"
           " an einer Position</b> (z. B. Schrauben je Rahmen) ins Angebot.", kurz=True)
    i.genauer()
    i.text("Eingekaufte Teile kommen auf zwei Arten ins Angebot: als eigene <b>Zukaufteil-Position</b> (z. B. ein "
           "Blech, das mitgeliefert wird) oder als <b>Zukaufteile an einer Position</b> (z. B. Schrauben je Rahmen). "
           "Die Artikel selbst, ihre Preise und Aufschläge werden im Reiter <i>Zukaufartikel</i> gepflegt "
           "([[zukauf]]).")
    i.abschnitt("Zukaufteil-Positionen", marke="zukauf_positionen")
    i.bild("angebot_berechnet", "Mit Häkchen „Berechnete Werte“: Gewicht, Laserzeit, Stück- und Positionspreis je "
                                "Zeile", hoehe=125 * mm)
    i.text("Eine Zukaufteil-Position braucht nur Stückzahl und Zukaufartikel; ihr Preis ist Einstand + Aufschlag + "
           "Frachtanteil.", kurz=True)
    i.genauer()
    i.text("Eine Position der Art <b>Zukaufteil</b> ist ein eingekauftes Teil, das mit dem Auftrag geliefert wird, "
           "z. B. ein Blech, das der STEP-Import erkannt hat. Sie braucht kein Profil und keinen Werkstoff, nur "
           "Stückzahl und einen Zukaufartikel (Spalte <i>Zukaufteile</i>, Menge 1 je Teil).")
    i.liste("<b>Preis je Teil</b> = Einstand + Aufschlag des Zukaufartikels ([[zukauf]]) + Frachtanteil, mit "
            "Skonto. Material, Laser, Rüsten, Zuschläge, Gewinn, Pauschalen, Programmierkosten und Angebotsaufschlag "
            "gibt es für Zukaufteile nicht; sie verteilen sich weiter nur auf die Rohrlaserteile.",
            "Zukaufteile kommen nicht in den Schnittplan. Die Kennzahl <i>Teile</i> zählt nur Rohrlaserteile.",
            "<b>Fracht</b>: Zukaufteile tragen ihren Anteil wie die anderen Teile, je Stück oder nach Gewicht (Spalte "
            "<i>Gewicht je Teil</i>; fehlt es, wird je Stück verteilt und die Kalkulation nennt die Position).",
            "<b>Status</b>: <i>FEHLER: Zukaufartikel fehlt</i> ohne Zukaufartikel, <i>WARNUNG: EK fehlt</i>, solange "
            "der Artikel keinen Einkaufspreis über 0 € hat. Dann steht in der Kalkulation der Hinweis <i>Zukaufteil: "
            "kein Einkaufspreis</i>, der Preis ist ohne Zukaufteil gerechnet und die Staffelpreise melden "
            "<i>Zukaufteil ohne Einkaufspreis</i>. 0 € gilt nie als Einkaufspreis.",
            "Im <b>Angebot</b> steht die Bezeichnung des Zukaufartikels, z. B. <i>Blech S235 500 × 300 × 5 mm</i>; in "
            "einem Satz als Teil des Satzes. In den <b>Staffelpreisen</b> zählen Zukaufteil-Positionen wie die "
            "anderen (je Satz oder als eigene Position). Die <b>Werkstattpapiere</b> listen sie unter <i>Zukaufteile "
            "(nicht lasern, zum Auftrag bereitstellen)</i>, die <b>Nachkalkulation</b> hat die Zeile "
            "<i>Zukaufteile (Einstand)</i>.",
            "Von Hand: Position anlegen, <i>Positionsart</i> = Zukaufteil, Stückzahl eintragen und unter "
            "<b>Zukaufteile … → Zukaufteile bearbeiten …</b> den Artikel wählen. Schneller mit neuem Artikel: "
            "<b>Zukaufteile … → Neuer Zukaufartikel …</b> ([[zukauf_angebot]]) legt Artikel und Position in einem Schritt "
            "an.",
            "<b>EK direkt im Angebot eintragen</b> (z. B. Bleche aus dem STEP-Import, die noch keinen EK haben): "
            "<b>Zukaufteile … → EK eintragen …</b>. Ohne Markierung listet der Dialog alle Zukaufteile des Angebots "
            "ohne EK, mit Markierung die Zukaufteile der markierten Positionen. Je Zeile stehen Pos., Artikel, "
            "Lieferant, Stückzahl (Verbrauch der Position) und der bisherige EK; in der letzten Spalte den "
            "Einkaufspreis netto je Stück eintragen, leere Zeilen bleiben unverändert.",
            "Der Preis wird im Zukaufartikel beim Lieferanten (bei Blechen ohne Lieferant <i>Technik</i>) als "
            "Staffelzeile <i>ab Stückzahl</i> gespeichert, z. B. 40 Bleche zu 12,50 € = <i>ab 40 St 12,50 €</i>. "
            "Vorhandene Staffelzeilen über 0 € bleiben, eine Zeile mit derselben Stückzahl wird ersetzt. Kleinere "
            "Mengen in anderen Angeboten nehmen die erste Staffelzeile. Die Änderung steht im Protokoll der "
            "Preisänderungen (<i>EK aus Angebot …</i>), die Position bekommt sofort den neuen Preisstand und die "
            "Warnung <i>EK fehlt</i> verschwindet.")
    i.liste("<b>STEP-Werte (aus CAD)</b>: aus dem importierten CAD-Modell gemessene Werte (Anfangs- und Endschnitt, "
            "Innenkonturen, Gravur, Bohrungen, Konturgrößen) und die Abweichung des Schneidwegs. Dazu gehören "
            "<b>Konturen Hüllmaß x Schnittweg [mm]</b> (je Kontur Hüllmaß und Schnittweg, Anfangs- und Endschnitt "
            "mit <i>A:</i> und <i>E:</i> vorn, z. B. <i>A:40x149,7; E:40x149,7; 10x31,4</i>) und <b>Konturgrenzen "
            "klein/mittel [mm]</b> (mit welchen Grenzen eingeteilt wurde, z. B. <i>10/50</i>).",
            "<b>Berechnete Werte (Programm)</b>: vom Programm ermittelte Werte wie Profilform, Gewicht, wirksame "
            "Stangenlänge, Vorschub und eingeplante Teile.")
    i.abschnitt("Zukaufteile an Positionen", marke="zukauf_angebot")
    i.bild("zukauf_dialog", "Dialog Zukaufteile: 4 Schrauben, 4 Muttern und 2 Laschen je Teil (Beispielwerte)",
           hoehe=60 * mm, legende=[
               (1, "Artikel wählen (Artikelnummer oder Bezeichnung eintippen), dann <b>Hinzufügen</b>"),
               (2, "Menge in der Einheit des Artikels, <i>je Teil</i> oder <i>je Satz</i> (bei Positionen in "
                   "einem Satz vorgewählt)"),
               (3, "je Zeile Artikel, Menge, je Teil/je Satz und <i>Aufschlag Position</i> (änderbar), "
                   "Lieferant, Aufschlagsregel, Einstand und VK je Teil, Preisstand"),
               (4, "<b>Entfernen</b>, <b>Duplizieren</b> und <b>Aus Stammdaten aktualisieren …</b>"),
               (5, "Vorschau für die Stückzahl dieser Position"),
               (6, "<b>Neuer Artikel …</b>: Schnellanlage, der neue Artikel wird gleich hinzugefügt")])
    i.text("Position markieren → <b>Zukaufteile …</b>, Artikel und <i>Menge je Teil</i> (oder je Satz) wählen.", kurz=True)
    i.genauer()
    i.text("Zukaufteile gehören zu einer Position: <i>Menge je Teil</i> × Stückzahl der Position ergibt den "
           "Verbrauch. Mit <i>je Satz</i> gilt die Menge je Satz: <i>Menge je Satz</i> × Sätze (Stückzahl ÷ Stück "
           "je Satz der Position). Beispiel Rahmen aus Rohren mit 20 Blechen: die Bleche an eine Rohrposition des "
           "Satzes hängen, Menge 20 je Satz; bei 10 Rahmen rechnet das Angebot 200 Bleche, die Staffelstufe 50 "
           "Rahmen 1000. Ohne Satzangabe zählt jedes Teil als ein Satz. Position(en) markieren und <b>Zukaufteile … → Zukaufteile bearbeiten …</b> wählen oder in der Spalte "
           "<i>Zukaufteile</i> doppelklicken. Umgekehrt übernimmt <b>In Angebot übernehmen …</b> im Unterreiter "
           "Artikel den markierten Artikel in eine Position: Angebot und Position wählen, Menge je Teil eingeben. "
           "Archivierte Artikel lassen sich nicht übernehmen.")
    i.liste("<b>Aufschlag Position [%]</b> leer lassen: es gilt die Regel des Artikels. Eine Zahl ersetzt sie "
            "für diese Position (% auf den Einstandspreis).",
            "Beim Hinzufügen speichert das Programm den <b>Preisstand</b> des Artikels in der Position: "
            "Einkaufspreise und Bezugskosten des bevorzugten Lieferanten und die Aufschlagsregel. Spätere "
            "Änderungen am Artikel, an der Kategorie oder am Standardaufschlag ändern gespeicherte Angebote nicht. "
            "Hat sich der Artikel geändert, steht in der Spalte Preisstand <i>neuer Stand in den Stammdaten</i>.",
            "<b>Aus Stammdaten aktualisieren …</b> (markierte Zeilen, ohne Markierung alle) zeigt je Artikel den "
            "VK je Teil alt und neu und übernimmt den neuen Stand erst nach Bestätigung und <b>OK</b>.",
            "Mit mehreren markierten Positionen gilt die Liste nach OK für alle (sie ersetzt deren Zukaufteile).")
    i.text("<b>Schnellanlage</b>, z. B. für Bleche: in der Knopfleiste des Angebots <b>Zukaufteile … → Neuer "
           "Zukaufartikel …</b> wählen. Das kurze Formular legt den Artikel in den Stammdaten an, und <b>jeder Artikel "
           "wird eine eigene Position</b> der Art <i>Zukaufteil</i> (nicht gelasert, Preis aus Einstand + Aufschlag, "
           "[[zukauf_positionen]]). Die Menge bezieht sich auf die markierte Position:")
    i.liste("<b>je Satz</b> (vorgewählt, wenn die markierte Position zu einem Satz gehört): die neue Position kommt "
            "in denselben Satz, <i>Stück je Satz</i> = Menge. Beispiel Rahmen: 20 Bleche je Rahmen, bei 10 Rahmen "
            "Stückzahl 200; die Staffelstufe 50 Rahmen rechnet 1000.",
            "<b>je Teil</b>: Stückzahl = Menge × Stückzahl der markierten Position.",
            "Ohne markierte Position fragt das Formular nur die <b>Stückzahl</b>.",
            "Eigene Positionen haben ganze Stückzahlen; die markierte Position bleibt unverändert.")
    i.text("Soll ein Blech dagegen im Preis eines Rohrs enthalten sein, im Dialog Zukaufteile der Rohrposition "
           "<b>Neuer Artikel …</b> nehmen: dort wird der neue Artikel an die Position gehängt.")
    i.bild("zukauf_schnell", "Schnellanlage eines Blechs (Beispielwerte)", hoehe=62 * mm, legende=[
        (1, "<b>Bezeichnung</b> (Pflicht) und optional Artikelnummer"),
        (2, "<b>Kategorie</b>: vorgewählt Blechteile. Bei Blechteilen oder <i>Blech</i> in der Bezeichnung ist "
            "der <b>Lieferant</b> <i>Technik</i> vorbelegt; überschreiben ist jederzeit möglich"),
        (3, "<b>EK je Stück</b> und <b>Aufschlag [%]</b>; leer = Aufschlag der Kategorie bzw. Standard"),
        (4, "<b>Menge</b> je Teil oder je Satz der markierten Position"),
        (5, "<b>Speichern + nächster</b> leert das Formular für das nächste Blech (Kategorie, Lieferant, Aufschlag "
            "und je bleiben), <b>Speichern + schließen</b> beendet")])
    i.text("Der Artikel bekommt Einheit Stück, Preiseinheit 1 und einen bevorzugten Lieferanten. Weitere Angaben "
           "(Mindestmenge, Bezugskosten, Preisstaffel) lassen sich später im Reiter Zukaufartikel ergänzen; das "
           "Protokoll der Preisänderungen vermerkt <i>Schnellanlage im Angebot</i>.")
    i.text("So rechnet das Angebot ([[kalkulation]]):")
    i.liste("Gleiche Artikel mit gleichem Preisstand aus allen Positionen werden zu <b>einer Bestellung</b> "
            "zusammengezählt. Für den ganzen Verbrauch gelten Mindestbestellmenge, Verpackungseinheit und Preisstaffel; "
            "Bezugskosten je Bestellung fallen einmal an und werden nach Verbrauch auf die Positionen verteilt.",
            "Der Verkaufspreis der Zukaufteile (Einstand + Aufschlag) kommt <b>nach dem Gewinn</b> in den "
            "Stückpreis: ohne Zuschlag Fertigung, Fremdleistung und ohne Gewinn des Angebots, denn der Aufschlag des "
            "Artikels ersetzt sie. Nur das Skonto wird eingerechnet. Die Herstellkosten enthalten keine Zukaufteile.",
            "Die Kosten zeigen <i>Zukaufteile (Einstand)</i> und <i>Aufschlag Zukaufteile</i> getrennt.",
            "Fehlt ein Einkaufspreis, zeigt die Position den Hinweis <i>Zukaufteil: kein Einkaufspreis</i>; die "
            "Staffelpreise melden <i>Zukaufteil ohne Einkaufspreis</i> statt eines Preises.",
            "Artikel mit <i>im Angebotstext der Position nennen</i> erscheinen im Angebots-PDF im Text der Position "
            "in einer eigenen Zeile mit Menge je Teil und Bezeichnung, z. B. <i>inkl. 4 St "
            "Sechskantschraube M6x20</i> ([[ausgabe]]).")
    i.bild("angebot_zukaufteile", "Reiter Zukaufteile im Angebot (Beispielwerte)", hoehe=70 * mm, legende=[
        (1, "Reiter <b>Zukaufteile</b>"), (2, "Summen: Einstand, Aufschlag, Verkauf"),
        (3, "je Artikel und Preisstand: Positionen, Verbrauch, Bestellmenge, Mehrmenge, Preisstaffel, EK je "
            "Einheit, Einkauf, Bezugskosten, Einstand, Aufschlagsregel, Aufschlag, Verkauf netto, Deckungsbeitrag "
            "[% vom VK], Preisstand und Hinweis")])
    i.text("In den <b>Staffelpreisen</b> ([[staffeln]]) rechnet jede Mengenstufe die Zukaufteile mit ihrem eigenen "
           "Verbrauch neu: 10 Baugruppen bestellen andere Mengen (und Staffelpreise) als 500. Das Ergebnis zeigt die "
           "Gruppe <i>Zukaufteile (eigener Aufschlag statt Zuschläge und Gewinn)</i> mit <i>Einstand Zukaufteile "
           "(Einkauf + Bezugskosten)</i> und <i>Aufschlag Zukaufteile</i>. Materialzuschlag und Gewinn der Stufe "
           "wirken nicht auf Zukaufteile.")
    i.abschnitt("Blech-Editor (Richtpreis)", marke="blech_editor")
    i.bild("blech_editor", "Blech-Editor: U-Profil aus 1.4301, 2 mm, mit Bohrung und Langloch", hoehe=95 * mm,
           legende=[
               (1, "<b>Bezeichnung</b> (leer = Vorschlag aus den Maßen), Artikelnummer, Lieferant (Technik "
                   "vorbelegt) und <b>Stückzahl</b>; auf sie wird das Rüsten umgelegt."),
               (2, "<b>Blech-Werkstoff</b> und <b>Dicke</b>."),
               (3, "<b>Art</b>: <i>Zuschnitt (flach)</i> mit Länge, Breite, Eckradius und <b>Kantungen</b> "
                   "(mehrachsig gekantete Teile, z. B. eine Schale; 0 = flach) oder <i>Kantteil</i>."),
               (4, "Kantteil: <b>Kantlänge</b> und je Zeile ein Schenkel mit Außenmaß, Biegewinkel zum nächsten "
                   "Schenkel (+ nach oben, − nach unten) und Innenradius (leer = Blechdicke). <b>Vorlage …</b> "
                   "setzt Winkel, U-, Z- oder Hutprofil; <b>+ Schenkel</b> und <b>Schenkel entfernen</b> ändern "
                   "die Liste."),
               (5, "<b>Innenkonturen</b> wie im Schneidweg-Rechner: Art, Anzahl, Maße (die Überschriften Maß 1–3 "
                   "nennen das Maß der markierten Zeile) und optional die Mitte x/y in der Abwicklung. "
                   "<b>Markierte entfernen</b> löscht Zeilen."),
               (6, "<b>Skizze</b>: Abwicklung mit Biegelinien (B1, B2 … mit Winkel, Richtung und Radius) und "
                   "Innenkonturen, beim Kantteil rechts die Seitenansicht mit den Außenmaßen."),
               (7, "<b>Richtpreis je Stück</b> mit Zuschnitt, Gewicht, Schneidweg, Einstichen, Laserzeit und den "
                   "Kosten Material, Laser, Kanten und Rüsten."),
               (8, "<b>Als Zukaufteil anlegen</b>: neuer Zukaufartikel (Kategorie Blechteile, Artikeltyp Blech, "
                   "Maße, Werkstoff) mit dem Richtpreis als EK und eine neue Position der Art Zukaufteil."),
               (9, "<b>3D-Ansicht</b>: das Teil aus den Eingaben gefaltet, Innenkonturen rot, Biegelinien grün. "
                   "Drehen mit der linken Maustaste, Knöpfe für feste Blickrichtungen."),
               (10, "<b>Außenkontur</b>: <i>Rechteck</i> aus den Maßen (Kantteil: Kantlänge × Abwicklung) oder "
                    "<i>Polygon</i> mit Eckpunkten x,y der Abwicklung, z. B. mit Ausklinkungen."),
               (11, "<b>Merkmale</b> mit Herkunft (Teil, Biegungen, Innenkonturen; [[teile_editor]])."),
               (12, "<b>Prüfmeldungen</b>: Klick hebt die Kontur bzw. Biegung in Skizze und 3D blau hervor.")])
    i.text("<b>Neue Position</b> → <i>Blech / Kantteil</i>: Zuschnitt oder Kantteil beschreiben, das Programm "
           "schätzt einen Richtpreis als Einkaufspreis.", kurz=True)
    i.genauer()
    i.text("Für Blech- und Kantteile, die ein Blechlaser liefert, schätzt der <b>Blech-Editor</b> vorab einen "
           "<b>Richtpreis</b>, der als Einkaufspreis des Zukaufteils dient. Er öffnet über <b>Neue Position</b> → "
           "<i>Blech / Kantteil</i> ([[neue_position]]). Er rechnet nur mit eigenen Daten: <i>Blech-Werkstoffe</i> "
           "und <i>Blechlaser (Richtwerte)</i> ([[blech_stammdaten]]) sowie den Einstellungen der Gruppe "
           "<i>Blech-Richtpreis</i>. Werkstoffe, Maschinen und Schneiddaten des Rohrlasers werden weder gelesen "
           "noch geändert.")
    i.text("Aufbau des Fensters: ganz links die Merkmale, daneben die Eingaben (Kopf, Zuschnitt bzw. Schenkel, "
           "Innenkonturen), rechts Skizze, 3D-Ansicht und Richtpreis, unten die Prüfmeldungen; Rückgängig, "
           "Zurücksetzen und Messen wie im Teile-Editor ([[teile_editor]]). Die Trennlinien lassen sich ziehen. Ist die Skizze höher als breit, steht die "
           "Seitenansicht unter der Abwicklung, im selben Maßstab, solange sie passt. In der Positionsliste "
           "zeigt das kleine Bild vor der Artikelnummer den Zuschnitt; Doppelklick darauf öffnet den Editor wieder.")
    i.text("<b>Aus dem STEP-Import</b>: Gekantete Bleche kommen vollständig an. Ein Kantteil mit parallelen "
           "Biegungen (Winkel, U, Z, Hut) hat Kantlänge, Schenkel mit Winkel und Radius, die Innenkonturen an ihrer "
           "Stelle und bei Ausklinkungen die Außenkontur als Polygon. Ein mehrachsig gekantetes Teil (Schale, "
           "Kasten) kommt als Zuschnitt mit der Außenkontur der Abwicklung, den gezählten Kantungen und den "
           "Biegelinien für Skizze und 3D-Ansicht. Der Schneidweg ist dann der der STEP-Abwicklung. Passt ein "
           "Polygon nicht mehr zu Kantlänge und Schenkeln (nach einer Änderung), steht unter dem Richtpreis ein "
           "Hinweis.")
    i.text("So rechnet der Blech-Editor:")
    i.liste("<b>Abwicklung</b> beim Kantteil: Summe der Schenkel-Außenmaße minus Ausgleichswert je Biegung "
            "v = 2·(r + s)·tan(φ/2) − π·φ/180·(r + k·s) (bis 90°; darüber 2·(r + s) − π·φ/180·(r + k·s)) mit "
            "Innenradius r, Dicke s, Biegewinkel φ und K-Faktor k je Biegung aus der Tabelle K-Faktoren "
            "([[blech_stammdaten]]; ohne passende Zeile der des Blech-Werkstoffs, Vorgabe 0,33). Beispiel "
            "Winkel 50 × 80 aus 2 mm, r = 2: v = 3,8 mm, Zuschnitt 126,2 mm.",
            "<b>Material</b> = Tafelbedarf der Stückzahl ÷ Stückzahl × Dicke × Dichte × Preis je kg "
            "([[blech_tafel]]).",
            "<b>Laser</b> = (Außenkontur ÷ Vorschub Außenkontur + Innenkonturen ÷ Vorschub Innenkonturen + "
            "Einstiche × Einstechzeit) × Stundensatz Blechlaser; Einstiche = 1 + Anzahl der Innenkonturen.",
            "<b>Kanten</b> = Anzahl Kantungen × Preis je Kantung; <b>Rüsten</b> = (Rüsten und Programmieren "
            "Blechlaser + beim Kantteil Rüsten Kanten) ÷ Stückzahl.",
            "<b>Richtpreis</b> = Summe × (1 + Aufschlag des Lieferanten), kaufmännisch auf Cent.")
    i.text("Später ändern: Rechtsklick auf die Position → <b>Blech-Editor …</b> oder Doppelklick auf die Position "
           "(außer in der Spalte Zukaufteile). Mit <b>Richtpreis übernehmen</b> kommt der neue Preis als "
           "Staffelzeile <i>ab Stückzahl der Position</i> in den Artikel, und die Position bekommt den neuen "
           "Preisstand. Der Richtpreis ersetzt kein Angebot des Blechlieferanten; liegt eines vor, den echten EK "
           "mit <b>EK eintragen …</b> ([[zukauf_positionen]]) oder im Reiter Zukaufartikel eintragen.")
    i.abschnitt("Tafelausnutzung", marke="blech_tafel")
    i.text("Das Material eines Blechteils kommt aus dem <b>Tafelbedarf</b> der Stückzahl, nicht aus einem festen "
           "Verschnitt. Größere Lose nutzen die Tafel besser; deshalb sinkt der Materialanteil je Stück mit der "
           "Stückzahl, auch in den Staffelpreisen.", kurz=True)
    i.liste("Das Programm legt die Hüllrechtecke der Teile mit Steg auf jedes Tafelformat: als Raster in einer Lage, "
            "den Reststreifen gedreht. Gewählt wird das Format mit dem kleinsten Bedarf.",
            "Volle Tafeln zählen ganz. Die letzte Tafel zählt nur mit der belegten Fläche samt Rand, denn der Rest "
            "der Tafel bleibt beim Lieferanten.",
            "Unter dem Richtpreis steht zum Beispiel <i>Tafel 3000 × 1500: 203 Stück je Tafel, Bedarf 0,49 Tafeln "
            "für 100 Stück, Ausnutzung 91 %</i> (Zuschnitt 200 × 100 mm).",
            "Freie Außenkonturen zählen mit ihrem Hüllrechteck; verschiedene Teile auf einer Tafel schachtelt das "
            "Programm nicht zusammen.",
            "Passt ein Zuschnitt auf kein Tafelformat, gilt der pauschale Verschnitt, und unter dem Richtpreis steht "
            "ein Hinweis. Mit der Einstellung <i>Material: pauschaler Verschnitt</i> gilt er immer "
            "([[einstellungen]]).")
    i.abschnitt("Kantbarkeit prüfen", marke="blech_kantbarkeit")
    i.text("Bei Kantteilen und mehrachsig gekanteten Zuschnitten prüft der Blech-Editor einfache Regeln und zeigt "
           "Befunde als <b>Hinweis: Kantbarkeit …</b> unter dem Richtpreis. Der Preis bleibt gleich; die Hinweise "
           "sagen nur, was mit der Kanterei oder dem Lieferanten zu klären ist.", kurz=True)
    i.liste("<b>Kleinster Schenkel</b>: Außenmaß mindestens 0,7 × V-Öffnung, V-Öffnung = 8 × Blechdicke (2 mm: "
            "11,2 mm).",
            "<b>Innenradius</b> mindestens 0,5 × Blechdicke.",
            "<b>Innenkontur an der Biegelinie</b>: der Rand einer Bohrung oder Kontur mindestens Innenradius + "
            "2 × Dicke von der Biegelinie entfernt, sonst verzieht sie sich beim Kanten (nur Konturen mit Mitte x/y).",
            "<b>Freischnitt</b>: kreuzen sich Biegelinien eines mehrachsig gekanteten Rechtecks, fehlt der "
            "Freischnitt an den Biegeecken.",
            "Biegefolge und Werkzeugkollision prüft das Programm nicht; das steht bei jedem Befund dabei.",
            "Die Faktoren stehen unter Einstellungen, Gruppe Blech-Richtpreis; Faktor 0 schaltet eine Regel ab "
            "([[einstellungen]]).")
    i.abschnitt("DXF der Abwicklung", marke="blech_dxf")
    i.text("<b>DXF speichern …</b> unten im Blech-Editor speichert den Zuschnitt als DXF-Datei (Format R12, Maße in "
           "mm), zum Beispiel für den Blechlaser oder für die Anfrage beim Lieferanten. Die Datei hat eigene Layer "
           "für Außenkontur, Innenkonturen, Biegelinien nach oben, Biegelinien nach unten, Gravur und die "
           "Beschriftung (Artikelnummer und Bezeichnung). Rundungen sind echte Bögen.", kurz=True)
    i.liste("Innenkonturen stehen an ihrer Mitte x/y. Fehlt die Lage, zeichnet die Datei sie nur verteilt auf der "
            "Mittellinie ein; eine Kontur mit Anzahl größer 1 steht nur einmal darin; eine sonstige Kontur ohne "
            "Form fehlt. Das meldet der Editor nach dem Speichern, damit die Datei vor der Weitergabe geprüft wird.",
            "Layernamen und ob Biegelinien in die Datei kommen, stehen unter Einstellungen, Gruppe "
            "Blech-Richtpreis ([[einstellungen]]).")


def kapitel_baugruppen(i):
    i.kapitel("Schweißbaugruppen", marke="schweissbaugruppe")
    i.text("Eine <b>Schweißbaugruppe</b> fasst Einzelteile des Angebots zusammen und rechnet dazu, was am Ganzen "
           "anfällt: Schweißen, Vorrichten, Schleifen, Vorrichtungen und Fremdleistungen. Anlegen: Einzelteile "
           "markieren → <b>Neue Position</b> → <b>Schweißbaugruppe</b>. Bearbeiten: Doppelklick auf die Zeile der "
           "Baugruppe oder auf ihren Status.", kurz=True)
    i.bild("baugruppe_struktur", "Editor Schweißbaugruppe, Reiter Struktur und Teile", hoehe=70 * mm, legende=[
        (1, "<b>Bezeichnung</b> und <b>Artikelnummer</b> der Baugruppe; die Bezeichnung ist der Satzname im "
            "Angebot."),
        (2, "<b>Anzahl Baugruppen</b>: Stückzahl der Baugruppe; alle Einzelteile folgen."),
        (3, "<b>Unterbaugruppen</b> mit <b>Menge</b> je übergeordneter Baugruppe (<b>Unterbaugruppe hinzufügen</b>,"
            " <b>Unterbaugruppe entfernen</b>); <i>gehört zu</i> hängt sie unter eine andere."),
        (4, "<b>Einzelteile</b>: Haken <i>in Baugruppe</i>, Unterbaugruppe und Stück je Unterbaugruppe; daneben "
            "das Stück je Baugruppe."),
        (5, "Kosten je Baugruppe, Zeit und <b>Status</b>, bei jeder Eingabe neu gerechnet.")])
    i.text("Die Einzelteile bleiben normale Positionen: sie werden optimiert und kalkuliert wie bisher. Die Baugruppe "
           "rechnet nur ihre eigenen Leistungen dazu, nichts doppelt.", kurz=True)
    i.genauer()
    i.text("Im Angebot verhält sich die Baugruppe wie ein <b>Satz</b>: Satz = Bezeichnung der Baugruppe, Stück je "
           "Satz der Teile = Stück je Unterbaugruppe × Menge der Unterbaugruppen, Stückzahl = Stück je Satz × Anzahl "
           "Baugruppen. Das Programm hält diese Werte selbst aktuell: Ändert man die Stückzahl der Baugruppe in der "
           "Positionsliste, ziehen die Teile nach (Meldung unten). Ein Teil kann nur zu einer Baugruppe gehören; "
           "Teile anderer Baugruppen fehlen in der Liste des Editors. Nimmt man ein Teil heraus (Haken weg), verliert "
           "es Satz und Stück je Satz der Baugruppe. Eine Unterbaugruppe kann nicht unter sich selbst hängen; der "
           "Editor weist das sofort ab. <b>Unterbaugruppe entfernen</b> hängt ihre Teile, Nähte und Arbeitsgänge "
           "eine Ebene höher.")
    i.text("Zukaufteile, die nur zur Baugruppe gehören (Schrauben, Muttern), kommen als <i>Zukaufteile an der "
           "Position</i> an die Zeile der Baugruppe ([[zukauf_angebot]]); eigene Zukaufteil-Positionen können auch "
           "Einzelteile sein. Gewicht und Fracht rechnen über die Einzelteile.")
    i.abschnitt("Strukturbaum und 3D", marke="baugruppe_baum")
    i.text("Der Reiter <b>Strukturbaum und 3D</b> zeigt die Baugruppe als Baum (Baugruppe → Unterbaugruppen → "
           "Einzelteile und Nahtgruppen, mit Menge und Stück je Baugruppe) und rechts in 3D in Einbaulage, wenn die "
           "Teile aus dem STEP-Import kommen. Ein Klick auf eine Unterbaugruppe, ein Teil oder eine Nahtgruppe hebt "
           "die Teile blau hervor. Die Schweißnähte sind als Linien eingezeichnet: Nahtgruppen orange, noch offene "
           "Nahtvorschläge aus dem STEP-Import hellorange, die gewählte Nahtgruppe rot.", kurz=True)
    i.bild("baugruppe_baum", "Reiter Strukturbaum und 3D, Unterbaugruppe gewählt", hoehe=70 * mm, legende=[
        (1, "<b>Strukturbaum</b>: Baugruppe, Unterbaugruppen mit Menge, darin Einzelteile und Nahtgruppen."),
        (2, "Gewählte Zeile: ihre Teile sind rechts blau, alle anderen grau."),
        (3, "3D-Ansicht der ganzen Baugruppe in Einbaulage mit den Schweißnähten (Knöpfe Schräg, Vorn, Oben, "
            "Stirnseite).")])
    i.genauer()
    i.text("Ohne Auswahl zeigt die Ansicht gleiche Teile in gleicher Farbe. Bei einer Nahtgruppe aus den "
           "Nahtkandidaten sind die beiden gestoßenen Teile blau; bei einer von Hand angelegten Nahtgruppe die Teile "
           "ihrer Unterbaugruppe. Ein Einzelteil lässt sich mit der Maus auf eine andere Unterbaugruppe oder die "
           "Baugruppe selbst ziehen: das ändert seine Zuordnung wie im Reiter Struktur und Teile, das Stück je "
           "Baugruppe bleibt, wenn die Teilung aufgeht. Je Teil zeigt die 3D-Ansicht alle gleichen Körper der "
           "STEP-Datei; bei Teilen aus einem Import vor Version 0.9.52 nur einen, Teile ohne STEP-Import fehlen "
           "(die Zeile unter der Ansicht nennt, wie viele).")
    i.text("Den Nahtverlauf liefert der STEP-Import ab Version 0.9.56 (die Schnittkante der sich berührenden "
           "Körper). Nähte sind immer sichtbar, auch wenn ein Teil davor liegt. Von Hand angelegte Nahtgruppen und "
           "Nahtgruppen aus einem älteren Import haben keinen Verlauf; die Zeile unter der Ansicht nennt, wie viele "
           "(STEP-Datei neu importieren, dann erscheinen sie).")
    i.abschnitt("Nahtgruppen")
    i.text("Je Zeile eine Gruppe gleicher Nähte. Die Schweißzeit kommt aus den Kennwerten unter Einstellungen "
           "([[schweiss_stammdaten]]), nie aus einer Schätzung: fehlt ein Kennwert oder das a-Maß, ist die Zeile gelb "
           "markiert (Warnzeichen an der Zeilennummer, Grund in der Spalte <i>Hinweis</i>) und die Baugruppe zeigt "
           "eine WARNUNG.", kurz=True)
    i.bild("baugruppe_naehte", "Reiter Nahtgruppen (Kennwerte hier aus den Richtwerten)", hoehe=60 * mm, legende=[
        (1, "<b>Verfahren</b> und <b>Nahtart</b> (Kehlnaht, Stumpfnaht, Ecknaht)."),
        (2, "<b>a-Maß / Dicke</b>: Kehlnaht a-Maß, Stumpf- und Ecknaht Blechdicke; dazu Länge je Naht und Anzahl."),
        (3, "<b>beidseitig</b> zählt die Naht doppelt; Heftpunkte je Naht rechnen mit der Zeit je Heftpunkt."),
        (4, "<b>Lage</b> (PA … PG), Zugänglichkeit und Qualität: Faktoren auf die Lichtbogenzeit."),
        (5, "<b>Zeit von Hand</b> geht immer vor (Zeit je Stück der Unterbaugruppe)."),
        (6, "Zeit und Kosten je Baugruppe (× Menge der Unterbaugruppe) und <b>Hinweis</b>: Nahtlänge, Etikett "
            "<i>Richtwert</i>, Datum der gemerkten Kennwerte oder gelb, was fehlt.")])
    i.genauer()
    i.text("Beim Speichern merkt sich jede Nahtgruppe die Kennwerte, mit denen sie gerechnet hat (Hinweis "
           "<i>Kennwerte vom …</i>). Spätere Änderungen unter Einstellungen ändern das Angebot nicht. Ändert man "
           "Verfahren, Nahtart, Nahtgröße, Lage, Zugänglichkeit oder Qualität, gelten für diese Zeile die aktuellen "
           "Stammdaten; <b>Kennwerte neu aus Stammdaten</b> setzt alle Zeilen auf die aktuellen Werte. Rechnet eine "
           "Zeile mit Richtwerten, zeigt die Baugruppe den HINWEIS <i>Schweißzeit aus ungeprüften Richtwerten</i>. "
           "<b>Nahtgruppe hinzufügen</b> legt eine Zeile mit Verfahren und Nahtart der letzten an; <b>Markierte "
           "kopieren</b> und <b>Markierte entfernen</b> arbeiten auf den markierten Zeilen.")
    i.text("Kommt die Baugruppe aus dem STEP-Import ([[step]]), stehen unter den Nahtgruppen die <b>Nahtkandidaten aus "
           "STEP</b>: Stellen, an denen sich Teile berühren, gleiche zusammengefasst (Stoßart, Länge je Naht, Anzahl "
           "je Stück der Unterbaugruppe, Dicke, Körper). Sie rechnen nicht mit. <b>Markierte übernehmen</b> macht "
           "daraus Nahtgruppen: Stumpf- und Ecknaht mit der gemessenen Dicke, Kehlnaht ohne a-Maß (die STEP-Datei "
           "kennt keins; bis es eingetragen ist, zeigt die Zeile <i>a-Maß fehlt</i>). Verfahren, Lage und "
           "Heftpunkte prüfen. <b>Markierte verwerfen</b> löscht Vorschläge, die keine Naht sind.")
    i.bild("baugruppe_vorschlaege", "Nahtkandidaten aus STEP im Reiter Nahtgruppen", hoehe=45 * mm, kurz=False,
           legende=[(1, "Je Zeile gleiche Nähte einer Unterbaugruppe: Stoßart, Länge je Naht, Anzahl je Stück, "
                        "Dicke und beteiligte Körper."),
                    (2, "<b>Markierte übernehmen</b> legt daraus Nahtgruppen an."),
                    (3, "<b>a-Maß nach Regel vorschlagen</b>: Kehlnaht mit a = Faktor × Wanddicke, bis zur "
                        "Bestätigung gelb.")])
    i.text("Mit dem Häkchen <b>a-Maß nach Regel vorschlagen</b> bekommt eine übernommene Kehlnaht ein a-Maß = Faktor × "
           "kleinere Wanddicke, abgerundet auf 0,5 mm (Faktor 0,7 unter Einstellungen → Vorgaben, Einstellung "
           "<i>Schweißbaugruppen: a-Maß-Regel, a = Faktor × kleinere Wanddicke (Vorschlag)</i>; z. B. Wand 4 mm → "
           "a 2,5 mm). Der Vorschlag ist gelb markiert und der Status "
           "zeigt den HINWEIS <i>a-Maß nach Regel, bitte bestätigen</i>, bis du das a-Maß prüfst und <b>a-Maß "
           "bestätigen</b> drückst oder einen anderen Wert einträgst.")
    i.abschnitt("Arbeitsgänge und Vorrichtungen")
    i.text("Alles außer dem Schweißen selbst: Vorrichten, Heften, Richten, Schleifen, Prüfen, Verpacken, "
           "Fremdleistungen wie Verzinken, dazu Einmalkosten für Vorrichtungen und Lehren.", kurz=True)
    i.bild("baugruppe_arbeitsgaenge", "Reiter Arbeitsgänge und Vorrichtungen", hoehe=60 * mm, legende=[
        (1, "<b>Stundensatz</b> aus den Stundensätzen des Angebots ([[stundensaetze]])."),
        (2, "<b>Einmalbetrag</b> (Vorrichtung, Lehre, Programm) und Rüstzeit: einmal je Auftrag bzw. Staffelstufe."),
        (3, "<b>Umlage</b>: <i>je Auftrag</i> ganz, <i>anteilig</i> mit dem Anteil in %, <i>wiederverwendbar</i> "
            "gar nicht (Vorrichtung schon vorhanden)."),
        (4, "<b>Fremd</b>: Fremdleistung mit Zuschlag Fremdleistung statt Fertigung."),
        (5, "<b>Arbeitsgang hinzufügen</b> bzw. <b>Vorrichtung hinzufügen</b>.")])
    i.genauer()
    i.text("<b>Aus Zusatzarbeiten …</b> übernimmt eine Zusatzarbeit der Stammdaten ([[zusatzarbeiten_verwalten]]) als "
           "Arbeitsgang: Stundensatz-ID bzw. eigener Stundensatz, Zeitaufwand (in Minuten umgerechnet), Festpreis "
           "und Material als Kosten je Einheit (bei €/kg, €/m², €/m die Menge in kg, m² bzw. m im Arbeitsgang "
           "eintragen), €/Angebot als Einmalbetrag und Fremdleistung. Danach lässt sich alles im Arbeitsgang ändern; "
           "spätere Änderungen der Zusatzarbeit ändern den Arbeitsgang nicht.")
    i.text("Laufende Kosten je Stück der Unterbaugruppe: Zeit je Einheit × Menge × Stundensatz + Kosten je Einheit "
           "× Menge. Einmalkosten werden durch die Anzahl Baugruppen geteilt, in den Staffeln durch die Menge der "
           "Stufe: kleine Mengen tragen mehr davon. Eine wiederverwendbare Vorrichtung mit Betrag zeigt den HINWEIS "
           "<i>wiederverwendbare Vorrichtung nicht berechnet</i>, damit das bewusst bleibt. Der Reiter "
           "<i>Stammdaten</i> nimmt Zeichnungsnummer, Revisionsstand, Werkstoff, Oberfläche und Bemerkungen auf; "
           "Zeichnung, Revision, Werkstoff und Oberfläche stehen im Angebotstext. Der Reiter <i>Übersicht</i> listet "
           "oben einen <b>Kostenbalken</b> (Schweißen, Arbeitsgänge, umgelegte Einmalkosten, Fremdleistung je "
           "Baugruppe) und darunter alle Nahtgruppen und Arbeitsgänge mit Zeit und Kosten je Baugruppe.")
    i.text("Aus einer STEP-Baugruppe: im Prüfdialog des STEP-Imports bei <b>Sätze</b> das Häkchen <b>als "
           "Schweißbaugruppe</b> setzen ([[step]]); Unterbaugruppen und Zuordnung der Teile kommen dann aus der "
           "Datei.")
    i.abschnitt("Vorkalkulation: Rüsten, Positionieren, Heften, Verputzen", marke="vorkalkulation_baugruppe")
    i.text("<b>Vorkalkulation rechnen</b> unten im Editor füllt, was sich aus Struktur und Teilen ableiten lässt: "
           "Heftpunkte und Nacharbeit je Nahtgruppe, die Positionierhilfe je Einzelteil und die Arbeitsgänge "
           "<i>Rüsten Schweißplatz</i>, <i>Teile positionieren</i>, <i>Wenden / Umspannen</i> und <i>Verputzen</i>. "
           "Gelbe Felder sind Vorschläge, der Tooltip zeigt Formel und Zahlen. <b>Vorschläge bestätigen</b> macht sie "
           "weiß; einen Wert, den du änderst, lässt jede neue Vorkalkulation stehen.", kurz=True)
    i.bild("baugruppe_vorkalk", "Reiter Arbeitsgänge nach Vorkalkulation rechnen (Regeln aus den Richtwerten)",
           hoehe=60 * mm, legende=[
               (1, "<b>Vorkalkulation rechnen</b>: Vorschläge aus Struktur, Teilen und den Regeln."),
               (2, "Gelb = Vorschlag, im Tooltip die Rechnung (z. B. 15 + 1 × 3 Teilenummern = 18 min)."),
               (3, "<b>Wendevorgänge je Baugruppe</b>: Zeit je Wenden × Faktor nach Gewicht (Reiter Stammdaten)."),
               (4, "Ergebnis der Vorkalkulation und was fehlt (fehlende Regel, Wanddicke, Gewicht)."),
               (5, "<b>Vorschläge bestätigen</b>: alle gelben Werte als geprüft übernehmen.")])
    i.genauer()
    i.tabelle(["Wert", "Rechnung (Werte aus Einstellungen → Schweiß-Vorkalkulation)"], [
        ["Rüsten (einmalig)", "Grundrüstzeit + Zeit je Teilenummer × Einzelteil-Positionen, mit Arbeitsgang "
                              "Vorrichtung + Rüsten Vorrichtung; Umlage je Auftrag"],
        ["Positionieren", "je Unterbaugruppe das erste Teil als Basisteil, jedes weitere Stück × Zeit seiner "
                          "Positionierhilfe; eingebaute Unterbaugruppen zählen als Teil <i>frei</i>"],
        ["Positionierhilfe", "Steckverbindung (Teil einer Steckverbindung der Baugruppe), Vorrichtung (Arbeitsgang "
                             "Vorrichtung an seiner Unterbaugruppe), Gravur (Zukaufteil, dessen Lage auf dem Rohr "
                             "graviert ist: Anbauteil mit Umriss oder Marke), sonst frei"],
        ["Heftpunkte je Naht", "größer von Mindestzahl (gerade, rundum, gesteckt) und Nahtlänge ÷ Heftabstand; "
                               "Heftabstand nach der kleineren <b>Wanddicke</b>, gesteckt × Faktor"],
        ["Verputzen", "Naht [m] × min je m der <b>Nacharbeit</b> × Faktor Zugänglichkeit; Nacharbeit aus Qualität "
                      "(erhöht = verschleifen, Sichtnaht = bündig planschleifen) bzw. Oberfläche (beschichtet, "
                      "verzinkt = Spritzer entfernen)"],
        ["Wenden", "Wendevorgänge × Zeit je Wenden × Faktor nach Gewicht der Baugruppe"]], [40, 225])
    i.text("Im Reiter Nahtgruppen gehören dazu die Spalten <b>Wanddicke</b>, <b>gesteckt</b>, <b>rundum</b> und "
           "<b>Nacharbeit</b>; in der Teileliste die Spalten <b>Positionierhilfe</b> (leer = Vorschlag, daneben "
           "<i>Vorschlag</i> mit Grund) und Stück je Baugruppe. Fehlt eine Regel oder ein Wert, gibt es keinen "
           "Vorschlag, sondern einen Hinweis unter der Summe: das Programm erfindet nichts. Gerechnet wird wie immer "
           "über Nahtgruppen und Arbeitsgänge; die vorgeschlagenen Arbeitsgänge laufen mit dem Stundensatz aus den "
           "Einstellungen <i>Schweißbaugruppen: Stundensatz für Rüsten, Positionieren und Wenden</i> bzw. "
           "<i>Schweißbaugruppen: Stundensatz für Verputzen und Schleifen</i>.")
    i.text("Solange Vorschläge offen sind, zeigt der Status den HINWEIS <i>… Vorschläge der Vorkalkulation offen</i>; "
           "Doppelklick führt zur ersten gelben Zeile. Drucken geht trotzdem; die Kalkulation (PDF) schreibt bei "
           "diesen Zeilen <i>(Vorschlag)</i> in die Spalte Herkunft. Mit der Einstellung <i>Schweißbaugruppen: "
           "Vorkalkulation beim STEP-Import (Vorschläge sofort rechnen)</i> auf <i>ja</i> rechnet das Programm "
           "die Vorschläge gleich für jede Schweißbaugruppe aus dem STEP-Import ([[step]]); der Bericht nennt das "
           "Ergebnis.")
    i.abschnitt("Im Angebot und in den Staffeln")
    i.text("Das Angebot zeigt <b>eine Zeile je Baugruppe</b>: <i>Schweißbaugruppe</i> mit Bezeichnung, darunter "
           "Zeichnung, Werkstoff und Oberfläche, Menge in Stück, Preis je Baugruppe. Die Einzelteile stehen nur "
           "darunter, wenn im Reiter <i>Stammdaten</i> das Häkchen <b>Stückliste im Angebot zeigen</b> gesetzt ist "
           "(ohne Preise).", kurz=True)
    i.text("In der <b>Positionsliste</b> stehen die Einzelteile direkt unter ihrer Baugruppe, im Zeilenkopf mit └ "
           "markiert. Ein Klick auf ▾ im Zeilenkopf der Baugruppe klappt ihre Teile zu (▸), ein weiterer wieder "
           "auf. Das ändert nur die Anzeige; Pos.-Nummern, Rechnung und Dokumente bleiben gleich. Im Angebot eines "
           "Kollegen ([[mehrere_arbeitsplaetze]]) und im Lesemodus öffnet der Editor nur zum Ansehen (OK ist grau).")
    i.text("Einmalkosten (Rüstzeit, Vorrichtungen, Lehren) sind normalerweise im Preis je Baugruppe enthalten. Mit "
           "dem Häkchen <b>Einmalkosten als eigene Zeile im Angebot</b> stehen sie als eigene Zeile <i>Einmalkosten "
           "Schweißbaugruppe … einmalig je Auftrag</i> (pausch.) unter der Baugruppe; die Summe des Angebots bleibt "
           "gleich. In den Staffeln zählen die Einmalkosten wie Rüsten (<i>Schweißbaugruppe einmalig</i>, umgelegt "
           "oder separat nach der Einstellung der Stufe); mit dem Häkchen zeigt das Angebots-PDF je Stufe den Preis "
           "je Stück ohne sie und den Zusatz <i>zzgl. einmalig … €</i>.")
    i.text("In der Kalkulation stehen die Kosten als <b>Schweißbaugruppen: Schweißen und Arbeitsgänge</b> (mit "
           "Zuschlag Fertigung) und <b>Schweißbaugruppen: Fremdleistungen</b> (mit Zuschlag Fremdleistung); danach "
           "Gewinn und Skonto wie bei jeder Position. Der Status der Baugruppe führt per Doppelklick in den Editor, "
           "direkt zur betroffenen Zeile (Nahtgruppe, Arbeitsgang, Unterbaugruppe oder Einzelteil), auch der Status "
           "eines Einzelteils mit einem Fehler der Zuordnung. Sind die gespeicherten Daten einer Baugruppe "
           "beschädigt, nennt der Status, was und wo (z. B. <i>Nahtgruppe 3 hat eine doppelte Kennung</i>).")
    i.text("Rechts in der <b>Übersicht</b> des Angebots steht je Baugruppe ein <b>Kostenbalken</b>: Schweißen, "
           "Arbeitsgänge, umgelegte Einmalkosten und Fremdleistung je Baugruppe mit Anteil in %, darunter die drei "
           "größten Posten. So sieht man sofort, wo sich das Nachprüfen von Kennwerten oder Vorrichtungen lohnt. "
           "Angebote ohne Baugruppe zeigen den Bereich nicht.")

    i.abschnitt("Schweißplan, Kalkulation und CSV")
    i.text("Die <b>Werkstattpapiere</b> ([[ausgabe]]) bekommen je Baugruppe eine Seite <b>Schweißplan</b> ohne Preise: "
           "Struktur mit Mengen, Einzelteile mit Pos. und Kästchen zum Bereitstellen, Nahtgruppen (Verfahren, a-Maß "
           "bzw. Dicke, Länge, Anzahl, Lage, Heftpunkte), Arbeitsgänge und Vorrichtungen in Reihenfolge zum Abhaken "
           "und die Vorgabezeit je Baugruppe und gesamt.", kurz=True)
    i.text("Die <b>Kalkulation (PDF)</b> zeigt je Baugruppe einen Abschnitt mit allen Nahtgruppen und Arbeitsgängen: "
           "Stück je Baugruppe, Zeit und Kosten je Baugruppe, Einmalbetrag und Herkunft der Zeit (Kennwert, "
           "Richtwert, von Hand, Fremdleistung oder was fehlt). Der <b>CSV-Export</b> als ZIP enthält bei Angeboten "
           "mit Baugruppen zusätzlich <i>Schweissbaugruppen.csv</i> mit einer Zeile je Baugruppe (Schweißzeit, "
           "Nahtlänge, Zeit, Fertigung, Fremdleistung, Einmalkosten, Herstellkosten und Preis je Baugruppe); "
           "Angebotskopf.csv und Angebotspositionen.csv bleiben unverändert.")
    i.abschnitt("Vorlagen und Kopie in ein anderes Angebot")
    i.text("Wiederkehrende Baugruppen nicht jedes Mal neu erfassen: <b>Als Vorlage speichern …</b> unten im Editor "
           "merkt Stammdaten, Unterbaugruppen, Nahtgruppen und Arbeitsgänge (ohne Einzelteile) unter einem Namen; "
           "<b>Vorlage einsetzen …</b> übernimmt sie in eine neue oder vorhandene Baugruppe.", kurz=True)
    i.text("Beim Einsetzen werden Stammdaten, Unterbaugruppen, Nahtgruppen und Arbeitsgänge der Baugruppe ersetzt; "
           "zugeordnete Einzelteile bleiben drin (Teile in einer Unterbaugruppe, die es in der Vorlage nicht gibt, "
           "hängen danach direkt an der Baugruppe). Die Kennwerte der Nahtgruppen gelten aus den aktuellen "
           "Stammdaten und werden beim Speichern wie immer gemerkt. Danach die Einzelteile per Häkchen zuordnen. "
           "Gibt es den Namen schon, fragt das Programm vor dem Überschreiben. Vorlagen werden mit den übrigen "
           "Stammdaten zwischen Arbeitsplätzen geteilt.")
    i.text("Für Folgeaufträge mit anderem Kunden: Rechtsklick auf die Baugruppe oder eines ihrer Teile → <b>Baugruppe "
           "in anderes Angebot kopieren …</b> und das Ziel wählen. Die Baugruppe kommt mit allen Einzelteilen, ihren "
           "Stückzahlen und 3D-Modellen ans Ende des anderen Angebots, mit eigener Kennung; das Original bleibt "
           "unverändert.")


def kapitel_ausgabe(i, seiten, ablage):
    i.kapitel("Ausgabe: Angebot, Werkstattpapiere, Kalkulation", marke="ausgabe")
    i.bild("ausgabe_leiste", hoehe=60 * mm, legende=[
        (1, "<b>Angebot (PDF)</b> (Strg+P) für den Kunden, mit Staffelpreisen und Konditionen."),
        (2, "Menü <b>Ausgaben</b>: <b>Werkstattpapiere (PDF)</b> (Materialliste und Schnittpläne zum Abhaken, "
            "Stangenbild), <b>Kalkulation (PDF)</b> (alle Kosten und Zeiten für die interne Ablage), "
            "<b>Materialanfrage (E-Mail)</b> (Stangenbedarf beim Lieferanten anfragen, [[materialanfrage]]), "
            "<b>CSV-Export</b> (Angebotskopf und Angebotspositionen, einzeln oder zusammen als ZIP, [[csv_export]]), "
            "darunter <b>Schneidweg berechnen …</b>, <b>Schweißnaht …</b> und <b>Ablage öffnen</b>."),
        (3, "<b>Schrittanzeige</b>: ④ Verschickt wird erledigt, sobald das Angebot verschickt ist (Vorgang, [[angebote]]).")])
    i.text("Jede Datei wird im Ablageordner gespeichert und gleich geöffnet. Ist die Optimierung veraltet, fragt das "
           "Programm vorher.", kurz=True)
    i.genauer()
    i.text("Bei schmalem Fenster (z. B. 1366 px Bildschirmbreite) rücken <b>Angebot (PDF)</b> und <b>Ausgaben</b> "
           "rechtsbündig in eine zweite Zeile unter die Arbeitsknöpfe.",
           "<b>Angebot (PDF)</b>: Briefkopf mit Firmenlogo (Einstellung <i>Firmenlogo</i>), Anschriftfeld "
           "links, Angebotsdaten rechts (Angebots-Nr., Datum, Gültig bis, Kunden-Nr., Ihre Anfrage), Positionen "
           "ohne Gitterlinien mit Bezeichnung, Menge, Einheit, Preis je Einheit und Gesamtpreis, darunter die "
           "Staffelpreise der Position „Ab 50 Stk. je“ ([[staffeln]]), Sätze, Summe mit MwSt. und Gesamtbetrag, "
           "darunter die Konditionen: Lieferzeit ([[lieferzeit]]), Zahlungsbedingung (z. B. „Zahlung innerhalb "
           "10 Tagen mit 2 % Skonto oder innerhalb 30 Tagen netto.“), ggf. „Mindestauftragswert 200,00 € netto.“ "
           "([[mindestpreis]]) und Bedingungen, jede Angabe in einer eigenen Zeile. Stückpreise sind kaufmännisch "
           "auf den Cent gerundet (2,675 € → 2,68 €); der Gesamtpreis jeder Zeile ist Stückpreis × Menge, die Summe "
           "genau die Summe der Zeilen.",
           "<b>Werkstattpapiere (PDF)</b>: Materialliste und je Stangenmuster der Schnittplan mit Kästchen zum "
           "Abhaken, danach das Stangenbild.",
           "<b>Kalkulation (PDF)</b>: oben die Kennzahlen (Verkaufspreis, Herstellkosten, Gewinn, Material, "
           "Maschinenzeit, Stangen, Teile), darunter die Kostenarten mit Anteil am Verkaufspreis in % und als Balken "
           "(ohne 0,00 €, Herstellkosten und Verkaufspreis hervorgehoben), der Materialeinsatz je Abmessung mit "
           "Querschnitt ([[material_fenster]]), Zeiten je Arbeitsschritt, alle Kalkulationswerte je Position für die "
           "interne Ablage und die Schneidzeit je Teil nach Konturklassen; zum Schluss das Stangenbild wie in den "
           "Werkstattpapieren. Spalten ohne Wert (z. B. Gewinde, Gravur, Mehrzeit 3D) sind ausgeblendet.",
           "<b>CSV-Export</b> schreibt Angebotskopf und Angebotspositionen im festen Spaltenformat "
           "([[csv_export]]); <b>Ablage öffnen</b> (im Menü Ausgaben) zeigt den Ablageordner im Explorer.")
    i.text("<b>Angebotstext einer Position</b>: jede Angabe steht in einer eigenen Zeile, nicht hintereinander. "
           "Reihenfolge: Profil, Länge, Werkstoff (<i>inkl. Material</i> mit dem Text im Angebot des Werkstoffs), "
           "Oberfläche, dann je Zusatzarbeit, Gewinde oder Gravur eine Zeile <i>inkl. …</i> und je Zukaufteil mit "
           "<i>im Angebotstext der Position nennen</i> eine Zeile mit Menge je Teil, z. B.:<br/>"
           "<i>Quadratrohr 40 x 40 x 3<br/>L = 550 mm<br/>inkl. Material S235 EN10219<br/>inkl. Gewinde 4xM6<br/>"
           "inkl. Senken</i><br/>"
           "Bei Sätzen steht der Text jedes Satzteils eingerückt unter der Satzzeile.")
    i.text("Die Dateien heißen nach der Angebotsnummer, z. B.: " + ", ".join(f"<i>{a}</i>" for a in ablage) + ".")
    i.abschnitt("CSV-Export: Angebotskopf und Angebotspositionen", marke="csv_export")
    i.text("<b>CSV-Export</b> → <b>Kopf + Positionen (ZIP)</b> speichert <i>Angebot_&lt;Nr&gt;.zip</i> mit "
           "<i>Angebotskopf.csv</i> (eine Zeile) und <i>Angebotspositionen.csv</i> (eine Zeile je Position) in der "
           "Ablage; <b>Nur Angebotskopf</b> bzw. <b>Nur Angebotspositionen</b> speichern eine Datei.", kurz=True)
    i.genauer()
    i.text("Format: Semikolon, UTF-8 mit BOM, Zeilenende CRLF (Windows), Dezimalpunkt (79.98) ohne Tausendertrennzeichen, Beträge mit "
           "2 Stellen, Zeiten <i>HH:MM:SS</i>, Datum <i>TT.MM.JJJJ</i>. Texte mit Semikolon, Anführungszeichen oder "
           "Zeilenumbruch stehen in Anführungszeichen. Spaltentitel und Reihenfolge sind fest vorgegeben, es gibt "
           "keine zusätzlichen Spalten. Der Export ändert nichts am Angebot; die Werte stammen aus derselben "
           "Rechnung wie Übersicht und Kalkulation, Stückpreis und Preis genau wie im Angebots-PDF. Staffelmengen "
           "sind nicht enthalten, nur die Menge der Position. Werte, die es im Programm nicht gibt, bleiben leer.")
    i.tabelle(["Angebotskopf.csv", "Inhalt"], [
        ["Erstellungsdatum / Datum Kunde:", "Anlagedatum des Angebots / Angebotsdatum"],
        ["Kunden Nr., Kunde:, Nachname", "Kundennummer, Kundenname, Ansprechpartner des Kunden"],
        ["Versandzone:", "Zone der Frachtberechnung, sonst Lieferbedingung des Kunden"],
        ["Kundenanfrage:, Kommentar", "Ihre Anfrage / Zeichen, Bemerkung"],
        ["Versandkosten, Feste Versandkosten, Versand inkl.", "Fracht in €; True bei Frachtart manuell; True bei "
         "<i>im Artikelpreis enthalten</i>"],
        ["Lieferzeit", "z. B. <i>ca. 2 Wochen nach Auftragseingang</i> ([[lieferzeit]])"],
        ["%Kunde Mat, %Kunde Arb., %Fremdarb., %Aufschlag", "Zuschlag Material, Fertigung, Fremdleistung und Gewinn "
         "in % (2 = 2 %)"],
        ["Bearbeitungszeit, Gesamtzeit", "Summe der Spalten der Positionen"],
        ["Restblech min.€", "Mindestauftragswert, wenn er für das Angebot gilt ([[mindestpreis]])"],
        ["Preis", "Angebotssumme netto wie im Angebots-PDF"],
        ["Aufrunden, Angebot erstellt von", "+0.01 (Rundung auf den Cent); Name bzw. Kürzel des Bearbeiters"],
        ["Kundenkurzbez., Position, Anrede, Rabatt(Euros)", "leer (gibt es im Programm nicht)"]],
        [150, 115])
    i.tabelle(["Angebotspositionen.csv", "Inhalt"], [
        ["Angebot, Art, ArtikelNr., Pos.", "Angebotsnummer, laufende Nummer 1, 2 …, Artikelnummer, Pos. der Position"],
        ["Bestellt, Preis geändert, zum Schneiden", "0 bzw. 1; Preis geändert = 1 bei Meterpreis oder Schneidzeit von "
         "Hand"],
        ["Format, Anz. Baugruppe, Menge", "Stangenlänge [mm], Stück je Satz (sonst 1), Stückzahl"],
        ["Stückpr., Preis", "Preis je Teil und Positionspreis wie im Angebots-PDF"],
        ["Werkstoff, Werkstofftyp, Dicke", "Kategorie (Stahl …), Text im Angebot des Werkstoffs, Wandstärke [mm]"],
        ["Fläche, Gew., Umfang, L.", "Mantelfläche außen [m²], Gewicht je Teil [kg], Schneidweg je Teil [mm], "
         "Teilelänge [mm]"],
        ["Maschine, Schneiden, Date", "Maschine des Angebots, Schneidgas, Angebotsdatum"],
        ["Artikeltext", "Angebotstext der Position in einer Zeile"],
        ["Bearbeitungszeit, Gesamtzeit", "Laserzeit je Teil; Laserzeit × Menge + Anteil Rüsten, Stangenwechsel, "
         "Rüsten je Abmessung + Programmierzeit"],
        ["Gesamt HK(€), HK(), Marge Netto(), Marge Netto%", "Herstellkosten der Position und je Teil; Preis − "
         "Herstellkosten, in % der Herstellkosten"],
        ["Kommentar", "Hinweis der Kalkulation"],
        ["Einsatzgewicht, Gesamt Einkauf(Kg), Verschnitt", "Stangengewicht anteilig je Teil bzw. × Menge; "
         "(Einsatz − Gewicht) ÷ Einsatz in %"],
        ["Gesamt Einkauf(), Preis/Kg", "Material + Einkauf Zukaufteile der Position; Material € je kg Einsatz"],
        ["Liste der Arbeitsgänge", "<i>Profile [Rechteckrohr 120x60x3], Gewinde [4xM6], Zusatzarbeit […]</i>, "
         "durch Komma getrennt"],
        ["Pos.Nr., Anzahl Tafeln, Arb., B.", "leer (Blech-Angaben, gibt es beim Rohr nicht)"]],
        [150, 115])
    i.abschnitt("Preise festschreiben", marke="preise_festschreiben")
    i.text("Mit dem Angebots-PDF schreibt das Programm die Preise fest: spätere Änderungen der Stammdaten (z. B. "
           "Stahlpreis) ändern das verschickte Angebot nicht. <b>Aktuelle Preise übernehmen …</b> holt sie bei Bedarf.")
    i.genauer()
    i.text("Beim Erzeugen des <b>Angebots-PDF</b> speichert das Programm im Angebot die Materialpreise und "
           "Schneiddaten, mit denen es gerechnet hat: die Zeilen aus <i>Preise</i> je Profil + Werkstoff der "
           "Positionen (auch, dass es keine Zeile gab und der Tonnenpreis galt), die Tonnenpreise der Werkstoffe, "
           "die Aufpreise der Oberflächen und die Schneiddaten der gewählten Maschine, außerdem die Gewinde (Preis "
           "und Zeit), die Einstellungen, die den Preis ändern (Zuschlag Material und Fertigung, Mindestpreis, "
           "Händler-Mehrlänge), die Zeilen der Profile und der Maschine sowie den Verkaufspreis netto des PDFs. "
           "Ändern sich danach die Stammdaten oder Einstellungen, z. B. der Stahlpreis, bleibt der Preis des Angebots "
           "wie im PDF beim Kunden.")
    i.text("Ändert sich danach das Angebot selbst (z. B. eine Stückzahl), steht in der Übersicht orange "
           "„Weicht vom verschickten Angebot (Datum: Betrag) ab: +… €“. Das nächste Angebots-PDF setzt den "
           "verschickten Stand neu. Jedes Angebots-PDF merkt sich das Programm mit Datum, Nettobetrag und Dateiname; "
           "der Mauszeiger auf dem Preisstand zeigt diesen Verlauf („Verschickt: …“).")
    i.liste("Neue Positionen mit anderem Profil, Werkstoff oder anderer Oberfläche rechnen mit den aktuellen "
            "Stammdaten; das nächste Angebots-PDF nimmt sie dazu, schon festgeschriebene Werte bleiben.",
            "Wird eine andere Maschine gewählt, gelten deren aktuelle Schneiddaten.",
            "<b>Aktuelle Preise übernehmen …</b> in der Übersicht (nur sichtbar, wenn die Stammdaten abweichen) "
            "zeigt die Änderungen und setzt das Angebot nach Rückfrage auf die aktuellen Stammdaten; der Preis "
            "ändert sich dann. Das nächste Angebots-PDF schreibt die neuen Werte wieder fest.",
            "Eine <b>Kopie</b> eines Angebots rechnet mit den aktuellen Stammdaten.",
            "Stundensätze und Zeitvorgaben sind schon beim Anlegen im Angebot gespeichert ("
            "[[zeiten]]), Zusatzarbeiten und Zukaufteile mit ihrem Preisstand.")
    i.abschnitt("Angebots-Check vor dem Versand", marke="angebots_check")
    i.text("Vor dem <b>Angebot (PDF)</b> und vor dem Vorgang <i>Verschickt</i> prüft das Programm das Angebot. Nur "
           "wenn ein FEHLER oder eine WARNUNG offen ist, kommt <b>eine</b> Rückfrage mit allen Punkten; Hinweise "
           "allein fragen nicht.", kurz=True)
    i.liste("<b>Hinspringen</b> schließt das Fenster und springt zur Stelle; danach einfach erneut <b>Angebot "
            "(PDF)</b>.",
            "Bei WARNUNG geht es mit <b>Angebot erstellen</b> (bzw. <b>Als verschickt markieren</b>) weiter.",
            "Bei FEHLER heißt der Knopf <b>Trotzdem weiter</b> und geht erst mit einer <b>Begründung</b>. Die "
            "übergangenen Punkte und die Begründung stehen danach im Versandverlauf (Mauszeiger auf den Preisstand "
            "in der Übersicht).",
            "Ein veralteter Schnittplan wird vorher ohne Rückfrage neu optimiert. Werkstattpapiere, Kalkulation und "
            "Materialanfrage fragen nur, wenn die Fracht nicht berechnet ist.",
            "Jederzeit ansehen: <i>Ausgaben → Angebots-Check …</i> oder Strg+K „Angebots-Check“; laufend steht die "
            "Liste in der Übersicht.", kurz=True)
    i.tabelle(["Prüfung", "Stufe", "Hinspringen zu"], [
        ["keine Positionen; Positionen mit FEHLER (z. B. Profil fehlt, Schweißbaugruppe ohne Werte)", "FEHLER",
         "erste betroffene Position"],
        ["Positionen mit WARNUNG (z. B. Gewinde ohne Preis), ungeprüfte Bohrungen/Gewinde-Vorschläge und "
         "Anbauteile, Hinweis in der Kalkulation (z. B. kein Preis, nicht eingeplant), Zukaufteil ohne "
         "Einkaufspreis", "WARNUNG", "erste betroffene Position"],
        ["kein Kunde; Schnittplan nicht aktuell; Fracht nicht berechnet", "WARNUNG", "Kunde, Optimieren, Fracht"],
        ["Marge unter der Mindestmarge (Einstellung, 0 = aus; Zahlen nur im Admin-Bereich)", "WARNUNG",
         "Reiter Kalkulation"],
        ["Staffelstufen veraltet; Mindestauftragswert greift (Preis angehoben); Stammdaten seit dem Festschreiben "
         "geändert; Preis weicht vom verschickten Angebot ab", "HINWEIS",
         "Staffeln, Mindestauftragswert, Aktuelle Preise übernehmen …"],
        ["Kunde ohne E-Mail-Adresse; Lieferzeit leer; Kundenreferenz leer; Gültigkeit abgelaufen", "HINWEIS",
         "Kunde bzw. Feld im Angebotskopf"]], [95, 22, 55])
    i.genauer()
    i.text("Die <b>Mindestmarge</b> steht in den Einstellungen unter <i>Angebot</i> (<i>Angebots-Check: "
           "Mindestmarge (Gewinn am Verkaufspreis, 0 = aus)</i>, Vorgabe 0). Gemeint ist der Gewinn aus dem "
           "Preisaufbau geteilt durch den Verkaufspreis. Angebote der Kollegen lassen sich ansehen und ausgeben, "
           "ohne dass der Check fragt.")
    i.abschnitt("Angebot (PDF)")
    i.bilder_nebeneinander(["pdf_angebot_1"], "Angebot A-2026-0041 (Seite 1)", hoehe=150 * mm)
    i.abschnitt("Werkstattpapiere (PDF)")
    letzte = f"pdf_werkstatt_{seiten['werkstatt']}"
    i.bilder_nebeneinander(["pdf_werkstatt_1", letzte],
                           "Werkstattpapiere: Materialliste und Schnittpläne (links), Stangenbild (rechts)",
                           hoehe=150 * mm)
    i.genauer()
    i.text("Alle PDFs haben dasselbe Aussehen wie das Angebot: Firmenname und kleines Firmenlogo oben, Titel in "
           "Dunkelblau, darunter Angebot, Kunde, Maschine und Erstellzeit, Listen ohne Gitter mit feinen Linien und "
           "jeder zweiten Zeile leicht hinterlegt, Fußzeile mit Firmenname und Seitenzahl.")
    i.text("Je Stangenmuster steht eine Kopfzeile mit Stangennummern, Profil, Werkstoff und Anzahl gleicher "
           "Stangen, darunter Stangenlänge, Endbeschnitt, Greiferrest, Rest und Ausnutzung. In der Liste sind Pos. "
           "und Länge fett, die Spalte <i>erl.</i> hat ein Kästchen zum Abhaken.")
    i.text("Hat das Angebot Zukaufteil-Positionen (z. B. Bleche), steht unter der Materialliste die Liste "
           "<i>Zukaufteile (nicht lasern, zum Auftrag bereitstellen)</i> mit Pos., Artikelnummer, Bezeichnung, "
           "Zukaufartikel, Stückzahl und Kästchen <i>bereit</i>.")
    i.abschnitt("Kalkulation (PDF)")
    i.bilder_nebeneinander(["pdf_kalkulation_1", f"pdf_kalkulation_{seiten['kalkulation']}"],
                           "Kalkulation A-2026-0041: Kennzahlen, Kostenarten und Materialeinsatz (links), Stangenbild "
                           "am Ende (rechts)", hoehe=150 * mm)
    i.abschnitt("Materialanfrage per E-Mail", marke="materialanfrage")
    i.text("<b>Materialanfrage (E-Mail)</b> bereitet nach dem Optimieren eine Anfrage an den Lieferanten vor; "
           "verschickt wird in Outlook.", kurz=True)
    i.bild("materialanfrage", "Materialanfrage an einen Lieferanten", hoehe=120 * mm,
           legende=[(1, "<b>Anfrage an Lieferant</b>: Lieferanten aus <i>Lieferlängen</i> bzw. <i>Preise</i> (Spalte "
                        "Lieferant); die E-Mail-Adresse kommt aus den Lieferanten der Zukaufartikel."),
                    (2, "Bedarf je Profil, Werkstoff, Oberfläche und Lieferlänge mit Anzahl Stangen (änderbar) und "
                        "Positionen; Häkchen weg = nicht anfragen. Kundenmaterial fehlt, das liefert der Kunde. "
                        "Spalte <b>Zuschnitt</b>: nur bei Stangen, die der Lieferant nach der Planung zuschneidet "
                        "(z. B. 12 m); Häkchen = Zuschnitt mit anfragen. Spalte <b>Schweißnaht</b>: nur bei "
                        "Rechteckrohr mit Teilen fester Naht, Seite der Naht der Lieferstange (änderbar)."),
                    (3, "<b>An</b>, <b>Betreff</b> und Text, frei änderbar. Betreff und Text kommen aus den Vorlagen "
                        "in den Einstellungen; der Text wird bei jeder Änderung der Zeilen neu erstellt, bis er von "
                        "Hand geändert wurde. Darunter steht, woher die Signatur kommt."),
                    (4, "<b>In Outlook öffnen</b> bzw. <b>Als E-Mail-Datei speichern</b>. Zeichnungen bei Bedarf in "
                        "Outlook selbst anhängen.")])
    i.genauer()
    i.text("Der Knopf steht rechts neben den Ausgaben im Angebot (immer sichtbar). Der Stangenbedarf kommt aus der "
           "Optimierung, deshalb zuerst <b>Optimieren</b>.")
    i.liste("<b>Gesendet wird nur in Outlook.</b> Das Programm öffnet die fertige E-Mail mit Empfänger, Betreff und Text "
            "im <i>klassischen</i> Outlook; erst der Klick auf <i>Senden</i> in Outlook verschickt sie.",
            "Ohne klassisches Outlook (z. B. das <i>neue</i> Outlook, das keine Programmsteuerung erlaubt) speichert "
            "das Programm eine E-Mail-Datei (<i>&lt;Angebot&gt; Materialanfrage.eml</i>) in der Ablage und öffnet sie "
            "im Standard-Mailprogramm. Sie ist als Entwurf markiert; dort prüfen und senden. "
            "<b>Als E-Mail-Datei speichern</b> geht diesen Weg direkt.",
            "Mehrere Lieferanten: je Lieferant eine Anfrage (oben wählen, öffnen, dann den nächsten). Zeilen ohne "
            "Lieferant stehen unter „(ohne Lieferant)“; die Adresse dann von Hand eintragen.",
            "Lieferanten und ihre E-Mail-Adressen pflegen: Zukaufartikel → Lieferanten; den Lieferanten eines "
            "Profils in den Stammdaten <i>Preise</i> bzw. <i>Lieferlängen</i>.")
    i.text("<b>Zuschnitt.</b> Ist eine Gruppe mit einer langen Lieferlänge geplant (z. B. 12-m-Lösung übernommen, "
           "[[lieferlaengen]]), steht unter der Materialzeile, wie der Lieferant die Stangen schneiden soll, z. B. "
           "<i>je Stange geschnitten auf 2 x 5.950 mm</i> oder bei verschiedenen Zuschnitten <i>davon 2 Stangen "
           "geschnitten auf …, 1 Stange geschnitten auf …</i>. Die Längen sind die Stangenlängen der Planung "
           "(mit Puffer, siehe Einstellungen <i>Lieferlängen</i>). Ohne Häkchen in der Spalte Zuschnitt wird nur die "
           "ganze Stange angefragt. Wird die Anzahl Stangen von Hand geändert, bleibt der Zuschnitt der Planung "
           "stehen; dann den Text prüfen.")
    i.text("<b>Schweißnaht der Lieferstange.</b> Hat eine Gruppe Rechteckrohr Teile mit fester Schweißnaht "
           "([[schweissnaht]]), steht unter der Materialzeile z. B. <i>Schweißnaht auf der Breitseite</i>. "
           "Vorgabe ist die Seite aus dem Angebot bzw. aus den Teilen; in der Spalte <b>Schweißnaht</b> geändert, "
           "gilt die neue Seite auch im Angebot (Profil und Werkstoff). Quadrat- und Rundrohr bekommen keine Angabe, "
           "dort passt jede Seite.")
    i.text("<b>Anforderungen je Werkstoff.</b> In den Stammdaten <i>Werkstoffe</i> lassen sich je Werkstoff "
           "<i>Anfrage: Prüfbescheinigung</i> (2.2, 3.1 oder 3.2 nach EN 10204), <i>Anfrage: Herkunft EU</i> und "
           "<i>Anfrage: Maßtoleranzen nach Norm</i> ankreuzen. Sie stehen eingerückt unter jeder Materialzeile "
           "dieses Werkstoffs, z. B. <i>Abnahmeprüfzeugnis 3.1 nach EN 10204, Herkunft EU</i> ([[stammdaten]]).")
    i.text("<b>Text und Signatur.</b> Die Vorlagen stehen in den Einstellungen, Gruppe <i>Materialanfrage</i> "
           "([[vorgaben]]). Platzhalter: <i>{angebot}</i> (Angebotsnummer), <i>{kunde}</i>, <i>{positionen}</i> "
           "(die Materialliste), <i>{datum}</i> (heute) und <i>{absender}</i> (Briefkopf). Unbekannte Platzhalter "
           "bleiben unverändert stehen. Mit <i>Signatur aus Outlook verwenden = ja</i> zeigt das Programm die "
           "E-Mail in Outlook an, Outlook setzt dabei seine Standardsignatur für neue E-Mails ein, und der Text "
           "kommt davor. Dafür muss in Outlook unter <i>Datei → Optionen → E-Mail → Signaturen</i> eine "
           "Standardsignatur für neue Nachrichten gewählt sein. Die E-Mail-Datei (neues Outlook, kein Outlook) "
           "erreicht die Outlook-Signatur nicht; sie bekommt die <i>eigene Signatur</i> aus den Einstellungen "
           "(leer = Briefkopf). Mit <i>nein</i> gilt die eigene Signatur auch in Outlook.")


def kapitel_nachkalkulation(i):
    i.kapitel("Nachkalkulation", marke="nachkalkulation")
    i.bild("nachkalkulation", "Reiter Nachkalkulation nach dem Auftrag", hoehe=95 * mm, legende=[
        (1, "<b>Stangen Ist</b> je Profil, Werkstoff und Stangenlänge: tatsächlich verbrauchte Stangen. Daneben "
            "<b>EK-Meterpreis Soll</b> (kalkuliert laut Schnittplan) und <b>EK-Meterpreis Ist</b> [€/m] zum "
            "Eintragen, z. B. laut Lieferantenrechnung; leer = kalkulierter Meterpreis. Material Ist = Stangen Ist "
            "× Meterpreis × Stangenlänge."),
        (2, "<b>Laserzeit Ist</b> [h] (z. B. aus dem Maschinenprotokoll), <b>Rüsten + Stangenwechsel Ist</b> "
            "[min], beide mit dem Stundensatz der Maschine bewertet; <b>Gewinde und Zusatzarbeiten Ist</b> [€] "
            "(z. B. Rechnung der Verzinkerei), <b>Zukaufteile Ist (Einkauf + Bezugskosten)</b> [€] (Rechnung "
            "des Lieferanten, z. B. für Bleche), <b>Sonstige Kosten Ist</b> [€] (z. B. Nacharbeit), <b>Erlös laut "
            "Rechnung</b> [€] und eine <b>Bemerkung Nachkalkulation</b>. Grau steht im leeren Feld das Soll."),
        (3, "Vergleich je Kostenart: Menge und Betrag Soll und Ist, Abweichung in € und %. Darunter Einzelkosten, "
            "Erlös und <b>Deckungsbeitrag</b> (Erlös − Einzelkosten)."),
        (4, "<b>Nachkalkulation (PDF)</b> speichert den Vergleich im Ablageordner: oben Kacheln mit Erlös, "
            "Einzelkosten Ist, Abweichung und Deckungsbeitrag Ist/Soll, Abweichungen farbig (rot = teurer bzw. "
            "schlechter als kalkuliert, grün = günstiger bzw. besser). <b>Ist-Werte löschen</b> setzt "
            "alles zurück. <b>Rest wie geplant</b> setzt alle noch leeren Ist-Werte auf das Soll, so dass nur die "
            "Abweichungen eingetragen werden müssen.")])
    i.text("Nach dem Auftrag die tatsächlichen Werte in <b>Ist-Werte nach dem Auftrag</b> eintragen (leer = wie "
           "kalkuliert). Das Programm vergleicht sie mit der Kalkulation.", kurz=True)
    i.genauer()
    i.text("Nach dem Auftrag zeigt der Reiter <i>Nachkalkulation</i>, ob die Kalkulation gestimmt hat. Eingetragen "
           "werden die tatsächlichen Werte im Feld <b>Ist-Werte nach dem Auftrag</b> (leer = wie kalkuliert); das Programm stellt sie den Werten aus Schnittplan und Kalkulation (Soll) "
           "gegenüber. Verglichen werden die <b>Einzelkosten</b> ohne Zuschläge und Gewinn, denn nur sie lassen sich "
           "in der Fertigung messen. Voraussetzung ist ein aktueller Schnittplan (vorher optimieren).")
    i.liste("Jede Eingabe wird sofort gespeichert. Leere Felder zählen wie kalkuliert; die Spalte <i>Ist erfasst</i> "
            "zeigt, welche Werte wirklich eingetragen sind. Schneller geht es mit <b>Rest wie geplant</b>: zuerst die "
            "Abweichungen eintragen (z. B. eine Stange mehr), dann den Knopf drücken; alle übrigen Werte gelten als "
            "erfasst wie kalkuliert (Meterpreis bleibt kalkuliert, Sonstige Kosten 0, Erlös = Verkaufspreis).",
            "Im Reiter <i>Angebote</i> zeigt die Spalte <b>Nachkalkuliert</b>, für welche Angebote Ist-Werte "
            "vorliegen, der Filter <i>Nachkalkulation offen</i> die beauftragten Angebote, die noch fehlen. Beim "
            "Kopieren werden die Ist-Werte nicht mitkopiert.",
            "Ein positiver Wert in <i>Abweichung</i> heißt: teurer als kalkuliert. Wiederholt sich das bei einer "
            "Kostenart, lohnt ein Blick in die Stammdaten (Schneiddaten, Rüstzeiten, Preise).")
    i.abschnitt("Schweißbaugruppen nachkalkulieren")
    i.text("Hat das Angebot Schweißbaugruppen ([[schweissbaugruppe]]), erscheint unter den Ist-Werten die Tabelle "
           "<b>Schweißbaugruppen (leer = wie kalkuliert)</b>: je Baugruppe Soll und Ist für den ganzen Auftrag.",
           kurz=True)
    i.liste("<b>Schweißen</b> [h]: Schweißzeit aller Nahtgruppen; Ist mit dem Stundensatz des Solls bewertet.",
            "<b>Arbeitsgänge</b> [h]: laufende Zeiten und Rüstzeiten der eigenen Arbeitsgänge, ebenso bewertet.",
            "<b>Material und Einmalbeträge</b> [€]: Kosten je Einheit, Vorrichtungen und Lehren.",
            "<b>Fremdleistungen</b> [€]: z. B. Verzinken laut Rechnung.",
            "<b>Abweichungsgrund</b>: Text, z. B. Nacharbeit oder Ausschuss; steht auch im PDF.",
            "<b>Schweißen Soll/Ist [min/m Naht]</b>: Schweißzeit je Meter Naht. Weicht das Ist bei mehreren "
            "Aufträgen in dieselbe Richtung ab, die Schweiß-Kennwerte ([[schweiss_stammdaten]]) prüfen und von Hand "
            "anpassen; die Nachkalkulation ändert keine Stammdaten und keine Angebote.")
    i.text("Die Zeilen der Baugruppen stehen im Vergleich als <i>Name: Schweißen</i>, <i>Name: Arbeitsgänge</i> usw. "
           "und zählen zu den Einzelkosten. Angebote ohne Baugruppe zeigen die Tabelle nicht. Ein Ist, das mindestens "
           "10 % über dem Soll liegt, ist rot hinterlegt, mindestens 10 % darunter grün. Stammt die Baugruppe aus "
           "einer Vorlage, zeigt der Tooltip ihres Namens die Schweißzeit Ist ÷ Soll der bisherigen Aufträge aus "
           "derselben Vorlage. Aus den nachkalkulierten "
           "Baugruppen schlägt das Programm geänderte Schweiß-Kennwerte vor ([[schweiss_stammdaten]]).")
    i.bilder_nebeneinander(["pdf_nachkalkulation_1"], "Nachkalkulation als PDF", hoehe=150 * mm)


def kapitel_einstellungen(i):
    i.kapitel("Einstellungen", marke="einstellungen")
    i.text("Der Reiter <i>Einstellungen</i> enthält alle Voreinstellungen: die Seite <i>Vorgaben</i> mit den "
           "Werten, die für alle Angebote gelten, und die Stammdaten außer den Kunden ([[stammdaten]]). Links steht "
           "die Navigation nach Themen: <i>Kalkulation</i> (Vorgaben, Stundensätze und Zeitvorgaben, Zusatzarbeiten), "
           "<i>Material</i> (Profile, Werkstoffe, Oberflächen, Preise, Lieferlängen), <i>Maschinen</i> (Maschinen, "
           "Schneiddaten, Gewinde, Prüfregeln), <i>Blech</i>, <i>Schweißen</i> und <i>STEP-Import</i>. Darüber das "
           "<b>Suchfeld</b>: es zeigt nur die Seiten, deren Titel, Spalten oder Vorgaben zum Suchwort passen, und auf "
           "der Seite Vorgaben nur die passenden Einstellungen (z. B. „gewinn“). Enter öffnet den ersten Treffer, "
           "das × im Feld zeigt wieder alles. Unten links: <b>Einstellungen sperren</b>.", kurz=True)
    i.bild("einstellungen_suche", "Einstellungen: Suche nach „gewinn“", hoehe=60 * mm, legende=[
        (1, "<b>Suchfeld</b>"), (2, "Navigation: nur Seiten mit Treffern"),
        (3, "Seite Vorgaben: nur die passenden Einstellungen")])
    i.abschnitt("Passwort", marke="passwort")
    i.bild("einstellungen_gesperrt", "Reiter Einstellungen gesperrt", hoehe=45 * mm, legende=[
        (1, "Reiter Einstellungen"), (2, "Passwort eingeben"), (3, "<b>Einstellungen öffnen</b>")])
    i.text("Passwort eintippen, Enter. Der Reiter bleibt offen, bis <b>Einstellungen sperren</b> gedrückt oder das "
           "Programm beendet wird.", kurz=True)
    i.genauer()
    i.text("Der Reiter öffnet sich erst nach Eingabe des Passworts. Passwort eintippen und Enter oder "
           "<b>Einstellungen öffnen</b> drücken. Er bleibt offen, bis <b>Einstellungen sperren</b> gedrückt oder das "
           "Programm beendet wird. Das Passwort steht unter Vorgaben, Gruppe Zugang (<i>Passwort für die "
           "Einstellungen</i>). Das Feld bleibt leer, auch wenn ein Passwort vergeben ist: Das Programm speichert das "
           "Passwort nur verschlüsselt (als Prüfwert, nicht lesbar). Zum Ändern das neue Passwort eintippen und das "
           "Feld verlassen; <b>Entfernen</b> = Einstellungen ohne Passwort. Ein Passwort aus einer älteren Version gilt "
           "unverändert weiter. Das Passwort bitte beim Verantwortlichen erfragen.")
    i.abschnitt("Vorgaben", marke="vorgaben")
    i.bild("einstellungen", "Einstellungen, Seite Vorgaben (oberer Teil)", hoehe=125 * mm, legende=[
        (1, "Seite Vorgaben in der Navigation links, darunter die Stammdaten nach Themen"),
        (2, "<b>Einstellungen sperren</b>")])
    i.text("Wert ändern, Feld verlassen: gespeichert. Er gilt ab der nächsten Rechnung für alle Angebote. Jede "
           "Gruppe (Kalkulation, Angebot, STEP-Import, Ablage …) ist eine eigene Karte.", kurz=True)
    i.bild("einstellungen_unten", "Einstellungen, Seite Vorgaben (unterer Teil): Briefkopf, Ablage, "
           "Auswahllisten und Passwort", hoehe=110 * mm, kurz=False)
    i.genauer("alle Vorgaben")
    i.text("Änderungen werden beim Verlassen des Feldes gespeichert und wirken ab der nächsten Rechnung. "
           "Ausnahme: Stundensätze und Zeitvorgaben ([[stundensaetze]]) speichert jedes Angebot beim Anlegen. "
           "Jede Gruppe steht in einer eigenen Karte; bei breitem Fenster (z. B. 1920 px) in zwei Spalten, bei "
           "schmalem untereinander.")
    i.tabelle(["Gruppe", "Einstellung", "Wirkung"], [
        ["Kalkulation", "Zuschlag Material, Zuschlag Fertigung, Zuschlag Fremdleistung, Gewinn",
         "Herstellkosten = Material × (1 + Zuschlag Material) + Fertigung und eigene Zusatzarbeiten × (1 + Zuschlag "
         "Fertigung) + Fremdleistungen × (1 + Zuschlag Fremdleistung); Verkaufspreis = Herstellkosten × (1 + Gewinn). Zuschlag Material "
         "und Zuschlag Fertigung (Vorgabe je 0 %) gelten für alle Angebote und sind im Angebot nicht änderbar; "
         "beim Update auf 0.6.5 einmalig auf 0 gesetzt."],
        ["Kalkulation", "Standardaufschlag Zukaufteile [% auf Einstand] (leer = keiner)",
         "gilt für Zukaufartikel, die weder einen eigenen Aufschlag noch einen Aufschlag ihrer Kategorie haben "
         "([[zukauf_kategorien]]); "
         "leer = kein Standardaufschlag, das Programm weist dann darauf hin. Neue Werte gelten nur für Zukaufteile, "
         "die danach ins Angebot kommen."],
        ["Kalkulation", "Rüstzeit je Abmessung [min]",
         "je verschiedenem Profil im Angebot, über den Stundensatz der Maschine mit Zuschlägen gerechnet"],
        ["Kalkulation", "Programmierzeit je Position [min], Programmierzeit je Innenkontur [min]",
         "Grundzeit je Position mit Stückzahl (Vorgabe 5 min) + Zeit je Innenkontur (Vorgabe 0,5 min) × Stundensatz "
         "<i>Programmierung</i>, auf deren Stückzahl verteilt, ohne Zuschläge auf den Preis; je Position von Hand "
         "änderbar; bei Staffelpreisen je Mengenstufe"],
        ["Kalkulation", "Pauschale je Abmessung [€], Angebotsaufschlag je Angebot [€]",
         "fester Betrag ohne Zuschläge auf den Preis; verteilt auf die Teile"],
        ["Kalkulation", "Prüfzeit je Teil mit unsicher erkannten Anbauteilen [min]",
         "eigener Zeitanteil der Laserzeit (Stundensatz Laser) je Teil, dessen Anbauteile aus dem STEP-Import "
         "unsicher erkannt und nicht ausgeschlossen sind ([[anbauteile]]); Vorgabe 0 = aus."],
        ["Kalkulation", "Handling Kundenmaterial je m Stangenlänge [€/m] (0 = keins)",
         "Kosten für beigestelltes Material je Meter der Stangen, mit Zuschlag Fertigung und Gewinn ([[kundenmaterial]]); "
         "Vorgabe 0."],
        ["Angebots-PDF", "Angebots-PDF: Hinweis zum Kundenmaterial mit Stangenbedarf",
         "ja = Hinweis „Material wird vom Kunden beigestellt: …“ mit Anzahl und Länge der Stangen im Angebot."],
        ["Kalkulation", "Mindestpreis je Angebot netto [€] (0 = keiner)",
         "Vorgabe 200,00 €; gilt für alle Angebote, darunter werden die Stückpreise anteilig angehoben "
         "([[mindestpreis]])."],
        ["Angebot", "Lieferzeit neuer Angebote: Angabe als, Lieferzeit neuer Angebote: Wert (Arbeitstage, Wochen, "
                    "KW/Jahr oder Datum), Lieferzeit neuer Angebote: Freitext",
         "Vorgabe der Lieferzeit für neue Angebote (Vorgabe <i>nur Text</i> + „nach Absprache“); ein ungültiger "
         "Wert bleibt im neuen Angebot leer ([[lieferzeit]])."],
        ["Angebot", "Standard-Maschine, Standard-Stangenlänge", "Vorgabe für neue Angebote"],
        ["Angebot", "Automatisch optimieren: Entwürfe bis Positionen (0 = aus)",
         "Vorgabe 100: Entwürfe mit höchstens so vielen Positionen (und weniger als 500 Teilen) optimieren sich "
         "kurz nach jeder Änderung selbst; 0 schaltet das ab ([[optimieren]])."],
        ["Angebot", "Standard-Staffeln: Faktoren auf die Bestellmenge, z. B. 1; 2; 5 (leer = aus)",
         "Vorgabe 1; 2; 5: Stufen, die der Knopf <b>Standard-Staffeln</b> und das erste Angebots-PDF ohne Stufe "
         "anlegen ([[staffeln]])."],
        ["Ansicht", "Hilfetexte über Tabellen und Seiten",
         "<i>aufklappbar</i> (Vorgabe): erster Satz, <b>ⓘ mehr</b> zeigt den ganzen Text; <i>nur Tooltip</i>: nur "
         "<b>ⓘ Hilfe</b>, der Text erscheint beim Zeigen mit der Maus. Gilt sofort für alle Tabellen, auch für "
         "die Hinweise in den Dialogen STEP prüfen, Bohrungen prüfen und Blech-Editor "
         "([[stammdaten]]) und die Staffeln."],
        ["Ansicht", "3D-Ansicht: Darstellung (Automatisch, Software oder OpenGL)",
         "<i>Automatisch</i> (Vorgabe): die 3D-Ansicht zeichnet mit der Grafikkarte (OpenGL), wenn der Rechner das "
         "kann und nicht über Remote-Desktop läuft, sonst wie bisher; <i>Software</i>: immer ohne Grafikkarte; "
         "<i>OpenGL</i>: immer mit Grafikkarte, wenn möglich. Klappt OpenGL nicht, zeichnet die Ansicht von selbst "
         "ohne Grafikkarte weiter ([[step_3d_ansicht]]). Gilt für neu geöffnete Ansichten, nur an diesem Arbeitsplatz."],
        ["Ansicht", "Farbschema (Hell, Dunkel, Hoher Kontrast, Wie Windows)",
         "<i>Hell</i> (Vorgabe) wie bisher; <i>Dunkel</i>: dunkle Flächen, helle Schrift, für dunkle Räume und lange "
         "Arbeit am Bildschirm; <i>Hoher Kontrast</i>: dunklere Schrift und deutlich umrandete Knöpfe; <i>Wie "
         "Windows</i>: hell oder dunkel wie in den Windows-Einstellungen. Der Tastaturfokus ist in Dunkel und Hoher "
         "Kontrast blau bzw. schwarz umrandet. Zeichnungen (3D-Ansicht, Skizzen, Stangenbild) bleiben hell. Gilt ab "
         "dem nächsten Start, nur an diesem Arbeitsplatz."],
        ["Ansicht", "Schriftgröße [%] (90 bis 150)",
         "Schrift im ganzen Programm größer oder kleiner (Vorgabe 100 %), z. B. 120 % für große Bildschirme. Gilt ab "
         "dem nächsten Start, nur an diesem Arbeitsplatz."],
        ["Ansicht", "Dichte (kompakt, normal, komfortabel)",
         "Zeilenhöhe der Tabellen und Abstand in Knöpfen und Feldern: <i>kompakt</i> zeigt mehr Zeilen, "
         "<i>komfortabel</i> mehr Luft (Vorgabe normal). Gilt ab dem nächsten Start, nur an diesem Arbeitsplatz."],
        ["Lieferlängen", "Lieferlängen: beim Optimieren andere Lieferlängen vergleichen (z. B. 12 m)",
         "ja = beim Optimieren auch andere Lieferlängen planen und vergleichen ([[lieferlaengen]]); Vorgabe nein "
         "(schneller). Ist die Stangenlänge des Angebots nicht lieferbar, wird trotzdem mit einer lieferbaren Länge "
         "geplant."],
        ["Lieferlängen", "Lieferlängen: Mindestersparnis je Gruppe in €, Lieferlängen: Mindestersparnis je Gruppe in %",
         "Eine andere Lieferlänge (z. B. 12 m) wird nur empfohlen, wenn sie gegenüber der Stangenlänge des Angebots "
         "mindestens so viel spart, in € und in % (Vorgabe 20 € und 3 %)."],
        ["Lieferlängen", "Lieferlängen: ohne Eintrag lieferbar ab Hüllkreis-Ø [mm] (0 = aus), Lieferlängen: Länge "
                         "für Profile ab diesem Hüllkreis-Ø [mm]",
         "Profile ohne Zeile in Lieferlängen mit größerem Hüllkreis-Ø gelten zusätzlich in dieser Länge als lieferbar "
         "(Vorgabe 70 mm und 12.000 mm), Preis wie unter Preise; 0 = aus."],
        ["Lieferlängen", "Lieferlängen: Schnittverlust je Zuschnitt beim Lieferanten [mm], Lieferlängen: Kosten je "
                         "Zuschnitt beim Lieferanten [€]",
         "Materialverlust und Kosten, wenn der Lieferant eine lange Stange in Werkstücke schneidet (Vorgabe 3 mm und "
         "0 €: die Stangen kommen geschnitten ohne Zusatzkosten)."],
        ["Lieferlängen", "Materialpreis: Mehrlänge je Stange, die der Händler berechnet, bis zur Grenze (z. B. 6 m) "
                         "[mm], Materialpreis: Mehrlänge je Stange über der Grenze (z. B. 12 m) [mm], "
                         "Materialpreis: Grenze kurze/lange Stange [mm]",
         "Länge, die der Händler je Stange zusätzlich berechnet (Vorgabe 50 mm bis 6.500 mm, 100 mm darüber); nur "
         "im Materialpreis, nicht in der Längenplanung ([[lieferlaengen]])."],
        ["Lieferlängen", "Lieferlängen: Puffer je zugeschnittener Stange [mm]",
         "So viel länger als rechnerisch nötig wird jede zugeschnittene Stange bestellt (Vorgabe 50 mm, 0 = auf den "
         "mm genau) ([[lieferlaengen]])."],
        ["Angebot", "Skonto [%], Skontofrist [Tage], Zahlungsziel netto [Tage]",
         "Zahlungsbedingungen neuer Angebote, wenn der Kunde im Kundenstamm keine eigenen hat (Vorgabe 2 % Skonto "
         "bei Zahlung in 10 Tagen, 30 Tage netto). Das Skonto wird in den Preis eingerechnet. Bestehende Angebote "
         "behalten ihre Werte."],
        ["Angebot", "Letzte Angebotsnummer", "Ein neues Angebot bekommt die nächste Nummer (2026-00041 → "
                                             "2026-00042); hier lässt sich der Startwert setzen "
                                             "([[mehrere_arbeitsplaetze]])."],
        ["STEP-Import", "STEP-Import: ebene flache Teile vorgeben als",
         "Blech (Vorgabe): jedes ebene flache Teil kommt als Blech (Zukaufteil), Flachstahl ist im Prüfdialog in der "
         "Spalte Art wählbar. Flachstahl bis Breite: Abgrenzung nach der nächsten Einstellung ([[bleche]])."],
        ["STEP-Import", "STEP-Import: Flachstahl bis Breite [mm] (breitere flache Teile sind Bleche)",
         "Nur bei <i>ebene flache Teile vorgeben als: Flachstahl bis Breite</i>. Grenze zwischen Flachstahl und "
         "Blech beim STEP-Import (Vorgabe 150 mm). Ein flaches Teil gilt nur als "
         "Flachstahl, wenn es höchstens so breit ist, mindestens dreimal so lang wie breit ist und gerade "
         "Längsseiten hat. Alles andere Flache ist ein Blech ([[bleche]])."],
        ["STEP-Import", "STEP-Import: Flowdrill-Bohrung am Laser",
         "Was der Laser bei einer erkannten Fließlochbohrung macht: Gravur Ø0,5 (Vorgabe) oder Loch Ø0,5. Im Fenster "
         "Bohrungen prüfen je Zeile änderbar ([[bohrungen_pruefen]])."],
        ["STEP-Import", "STEP-Import: Standardordner (leer = zuletzt benutzter Ordner)",
         "Ordner, in dem der Dateidialog <i>STEP importieren …</i> startet, z. B. das Laufwerk mit den "
         "Kundenzeichnungen. <b>Ordner wählen …</b> sucht ihn aus, <b>Leeren</b> nimmt ihn heraus; leer (oder der "
         "Ordner ist nicht erreichbar) = der Dialog startet im zuletzt benutzten STEP-Ordner ([[step]])."],
        ["STEP-Import", "STEP-Import: Standard-Werkstoff für Rohre und Profile (leer = keiner)",
         "Werkstoff, mit dem der STEP-Prüfdialog Rohre und Profile vorbelegt (Vorgabe S235-10219 = S235 EN10219). "
         "Bleche bekommen nie einen Werkstoff vorbelegt. Leer = kein Werkstoff vorbelegt."],
        ["STEP-Import", "Artikelnummer aus (Bauteilname, Dateiname oder beides), Normteile: Begriffe im "
                        "Bauteilnamen (mit ; getrennt)",
         "Wie aus den Namen in der STEP-Datei Artikelnummern werden und welche Teile als Normteil abgewählt sind; "
         "je Kunde änderbar im Importprofil ([[importprofile]])."],
        ["STEP-Import", "Messung: gleichzeitige Messprozesse (0 = automatisch, Kerne − 1)",
         "So viele Dateien misst <i>STEP-Import.exe</i> gleichzeitig (Vorgabe 0 = Prozessorkerne − 1); eine "
         "einzelne große Baugruppe wird auf so viele Prozesse verteilt (mit Zeitlimit). Weniger "
         "Prozesse entlasten einen langsamen Arbeitsplatz. Gilt nur für diesen Arbeitsplatz."],
        ["STEP-Import", "Messung: Zeitlimit je Körper [s] (0 = ohne; länger = Körper nicht gemessen)",
         "Braucht ein einzelner Körper länger (Vorgabe 120 s) oder stürzt seine Messung ab, wird nur dieser "
         "Körper ausgelassen: er steht im Prüfdialog als nicht übernehmbar mit dem Hinweis <i>nicht gemessen: "
         "Zeitlimit … überschritten</i>, alle anderen Körper der Datei werden gemessen ([[step]]). Gleiche "
         "Kopien dieses Körpers ebenso. Dauern die Auswertungen über die ganze Baugruppe (Anbauteile, "
         "Nahtkandidaten) zu lange, fehlen nur diese, mit Hinweis am ersten Teil."],
        ["STEP-Import", "Messung: Zwischenspeicher (gleiche Datei nicht neu messen), Messung: Zwischenspeicher "
                        "höchstens [MB]",
         "ja (Vorgabe) = eine schon gemessene Datei mit gleichem Inhalt, gleicher Programmversion und gleichen "
         "Einstellungen kommt sofort aus dem Ordner <i>STEP-Cache</i> neben der Datenbank. Ist er größer als "
         "angegeben (Vorgabe 500 MB), fallen die am längsten nicht benutzten Messungen weg. <b>Zwischenspeicher "
         "leeren</b> löscht alle gemerkten Messungen. Messungen mit ausgelassenen Körpern werden nicht gemerkt. "
         "Gilt nur für diesen Arbeitsplatz."],
        ["STEP-Import", "Toleranz Profil aus den Stammdaten ± [mm], Toleranz gleiche Teile einer Baugruppe ± [mm], "
                        "Toleranz Kernloch für Gewinde-Vorschlag ± [mm]",
         "Wie genau die Messung zu einem Profil der Stammdaten passen muss (Vorgabe 0,15 mm), ab wann Körper einer "
         "Baugruppe als gleiches Teil zusammengefasst werden (0,2 mm) und wie nah eine Bohrung am Kernloch-Ø liegen "
         "muss, damit ein Gewinde vorgeschlagen wird (0,05 mm)."],
        ["STEP-Import", "Biegerohr: Faktor neutrale Faser für die gestreckte Länge (1,0 = Rohrmitte)",
         "Gestreckte Länge eines Biegerohrs = Geraden + Faktor × Bögen (Vorgabe 1,0, [[biegerohre]]); gilt beim "
         "Übernehmen aus dem STEP-Import."],
        ["Knickrahmen", "Knickrahmen: Knickzugabe je Knick [mm] (+ = Rohr länger), Knickrahmen: Freistich-Ø an "
                        "den Spitzen des V [mm] (0 = ohne), Knickrahmen: K-Faktor der Stegwand (0,5 = Wandmitte)",
         "Vorgaben im Fenster Knickrahmen des Schneidweg-Rechners: Zugabe je Knick (Vorgabe 0), Freistich (Vorgabe "
         "ohne) und Lage der neutralen Faser für den Ausgleichswert nach DIN 6935 (Vorgabe 0,5, [[knickrahmen]])."],
        ["STEP-Import", "Experte: Flachstahl ab Länge × Breite, Experte: gekantetes Blech statt Profil, wenn Volumen "
                        "unter Anteil von Querschnitt × Länge",
         "Grenzwerte der Erkennung, nur nach Rücksprache ändern: ein flaches Teil ist erst ab dieser Länge "
         "(Vorgabe 3 × Breite) Flachstahl; ein gekantetes Teil gilt als Blech statt Profil, wenn sein Volumen unter "
         "diesem Anteil (Vorgabe 85 %) von Querschnitt × Länge liegt ([[bleche]])."],
        ["Blech-Richtpreis", "Stundensatz Blechlaser [€/h], Rüsten und Programmieren Blechlaser je Auftrag [€], "
                             "Verschnitt Tafel (auf das Hüllrechteck), Kanten: Preis je Kantung [€], Kanten: "
                             "Rüsten je Auftrag [€], Aufschlag des Lieferanten (Gewinn)",
         "Sätze für den Richtpreis im Blech-Editor (Vorgabe 120 €/h, 30 €, 15 %, 1,20 €, 25 €, 15 %); sie gelten "
         "nur dort, nie für den Rohrlaser ([[blech_editor]])."],
        ["Blech-Richtpreis", "DXF: Layernamen (Außenkontur; Innenkontur; Biegelinie hoch; Biegelinie runter; "
                             "Gravur; Beschriftung), DXF: Biegelinien ausgeben",
         "Layer der DXF-Datei aus dem Blech-Editor in dieser Reihenfolge, mit ; getrennt (leer = Vorgabe "
         "AUSSENKONTUR, INNENKONTUR, BIEGUNG_HOCH, BIEGUNG_RUNTER, GRAVUR, BESCHRIFTUNG); Biegelinien ausgeben "
         "Vorgabe ja ([[blech_dxf]])."],
        ["Blech-Richtpreis", "Kantbarkeit: V-Öffnung = Faktor × Blechdicke, Kantbarkeit: kleinstes "
                             "Schenkel-Außenmaß = Faktor × V-Öffnung, Kantbarkeit: Abstand Innenkontur–Biegelinie "
                             "mindestens Innenradius + Faktor × Dicke, Kantbarkeit: kleinster Innenradius = Faktor × "
                             "Dicke",
         "Regeln der Kantbarkeits-Hinweise im Blech-Editor (Vorgabe 8; 0,7; 2; 0,5); Faktor 0 schaltet eine Regel "
         "ab ([[blech_kantbarkeit]])."],
        ["Blech-Richtpreis", "Material: Tafelausnutzung oder pauschaler Verschnitt, Tafelformate: Länge × Breite "
                             "in mm, mit ; getrennt, Tafel: Randabstand [mm], Tafel: Steg zwischen den Teilen [mm]",
         "<i>Tafelausnutzung</i> (Vorgabe): Material aus dem Tafelbedarf der Stückzahl; <i>pauschaler "
         "Verschnitt</i>: Hüllrechteck × (1 + Verschnitt Tafel). Tafelformate als Beispiel 3000 × 1500 und "
         "2500 × 1250, Randabstand 10 mm, Steg 5 mm; bitte an die eigenen Tafeln anpassen ([[blech_tafel]])."],
        ["Blech-Richtpreis", "Abwicklung: K-Faktor aus (K-Faktor-Tabelle oder je Werkstoff)",
         "<i>K-Faktor-Tabelle</i> (Vorgabe): je Biegung aus der Tabelle K-Faktoren nach Dicke und Innenradius; "
         "<i>je Werkstoff</i>: der K-Faktor des Blech-Werkstoffs für alle Biegungen ([[blech_stammdaten]])."],
        ["Angebots-PDF", "Firmenlogo (rechts oben im Angebot)",
         "<b>Bild wählen …</b> nimmt eine PNG- oder JPG-Datei (große Bilder werden verkleinert); das Logo steht im "
         "Angebots-PDF rechts oben im Briefkopf, eingepasst in 55 × 24 mm, klein (32 × 13 mm) auch auf "
         "Werkstattpapieren, Kalkulation und Nachkalkulation. Es wird in der Datendatei gespeichert, "
         "wandert also mit Sicherung und Export mit. <b>Entfernen</b> = Angebot ohne Logo."],
        ["Angebots-PDF", "Briefkopf Zeile 1 (Firma), Briefkopf Zeile 2, Briefkopf Zeile 3, Briefkopf Zeile 4, MwSt.-Satz, "
                    "Gültigkeit, Bedingungen", "Kopf und Text des Angebots-PDF; Zeile 1 bis 3 stehen klein als "
                    "Absenderzeile über der Anschrift, alle Zeilen in der Fußzeile. Die Zahlungsbedingung (Skonto, "
                    "Zahlungsziel) setzt das Programm aus dem Angebotskopf vor die Bedingungen, sie gehört nicht in "
                    "dieses Feld."],
        ["Ablage", "Ablageordner", "Ziel für PDF und CSV-Export; leer = Ordner <i>Angebote</i> neben dem "
                                   "Programm (portabel) bzw. <i>Dokumente\\Rohrlaser Angebote</i> (installiert). "
                                   "Auch ein Netzlaufwerk ist möglich."],
        ["Ablage", "Zweiter Sicherungsordner", "zusätzliche Sicherung beim Beenden und mit <i>Datensicherung "
                                               "erstellen</i>, z. B. Netzlaufwerk, OneDrive oder USB-Stick; leer = "
                                               "keiner ([[datensicherung]])"],
        ["Auswahllisten", "Profilformen", "Einträge der Auswahl „Profilform“ in den Profilen"],
        ["Auswahllisten", "Werkstoff-Kategorien", "Kategorien für Werkstoffe, Oberflächen und Schneiddaten "
                                                  "(Vorgabe Stahl, Edelstahl, Aluminium)"],
        ["Frachtkosten", "Absender-PLZ (Versandort), Absender-Land, Versandart für automatische Fracht, "
                         "Ladungsträger im Packvorschlag, Ladungsträger für lange Teile (Langgut)", "stehen im Reiter Frachtkosten unter <i>Historie und "
                         "Einstellungen</i> ([[fracht_einstellungen]]), nicht unter Vorgaben"],
        ["Materialanfrage", "Materialanfrage: Betreff, Materialanfrage: Text der E-Mail",
         "Vorlagen der Materialanfrage mit Platzhaltern {angebot}, {kunde}, {positionen}, {datum}, {absender}; "
         "leer = Vorgabe ([[materialanfrage]])"],
        ["Materialanfrage", "Materialanfrage: Signatur aus Outlook verwenden, Materialanfrage: eigene Signatur "
                            "(E-Mail-Datei; leer = Briefkopf)",
         "ja = Outlook setzt seine Standardsignatur, der Text kommt davor; die E-Mail-Datei bekommt die eigene "
         "Signatur. nein = eigene Signatur auch in Outlook ([[materialanfrage]])"],
        ["Nachfassen", "Nachfassen: Wiedervorlage nach Tagen ohne Entscheidung (0 = aus)",
         "Tage bis zur automatischen Wiedervorlage eines verschickten Angebots ([[nachfassen]])"],
        ["Zugang", "Passwort für die Einstellungen", "Passwort für den Reiter Einstellungen und die Pflegebereiche der "
                                                    "Frachtkosten, zugleich Admin-Passwort beim Start; verschlüsselt gespeichert, Feld bleibt "
                                                    "leer; <b>Entfernen</b> = ohne Passwort"]],
        [28, 80, 157])
    i.abschnitt("Stundensätze und Zeitvorgaben", marke="stundensaetze")
    i.bild("stamm_arbeitsschritte", "Einstellungen, Stundensätze und Zeitvorgaben (Beispielwerte)", hoehe=95 * mm)
    i.text("Links die <b>Stundensätze</b> (€/h), rechts die <b>Arbeitsschritte</b> mit Zeit und Stundensatz. Kosten "
           "= Zeit × Stundensatz. Neue Angebote merken sich die Werte beim Anlegen.", kurz=True)
    i.genauer()
    i.text("Der Unterreiter <i>Stundensätze und Zeitvorgaben</i> zeigt links die <b>Stundensätze</b> und rechts die "
           "<b>Arbeitsschritte</b>. Jeder Arbeitsschritt wird mit genau einem Stundensatz gerechnet; der Satz "
           "<i>Maschine</i> ist der Stundensatz der gewählten Maschine ([[stammdaten]]).")
    i.tabelle(["Stundensätze", "Bedeutung"], [
        ["<b>Stundensatz-ID</b>", "Kurzname, z. B. <i>Rüstpersonal</i>; Auswahl in den Arbeitsschritten"],
        ["Bezeichnung", "Klartext, z. B. Arbeitsplatz oder Kostenstelle"],
        ["<b>Stundensatz [€/h]</b>", "Kosten je Stunde; vorbelegt mit Beispielwerten, bitte eigene eintragen"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.tabelle(["Arbeitsschritte", "Bedeutung"], [
        ["<b>Arbeitsschritt</b>", "Name. Laser schneiden, Gewinde, Rüsten Maschine, Rüsten je Abmessung, "
                                  "Stangenwechsel und Programmierung rechnet das Programm selbst (Zeit aus Schneiddaten, Gewinde, "
                                  "Maschine und Vorgaben); dort wird nur der Stundensatz gewählt."],
        ["<b>Stundensatz</b>", "<i>Maschine</i> oder eine Stundensatz-ID. Vorgabe für Gewinde, Rüsten und "
                               "Stangenwechsel ist Maschine (wie bisher), umstellbar z. B. auf Rüstpersonal; "
                               "Programmierung rechnet mit dem Satz <i>Programmierung</i>."],
        ["<b>Art</b>", "Maschine oder Personal: für Maschinenzeit, Personalzeit und Durchlaufzeit"],
        ["Parallel zur Maschine", "ja = die Personalzeit läuft während die Maschine schneidet (z. B. Entgraten); "
                                  "sie kostet, verlängert aber die Durchlaufzeit nicht"],
        ["Rüstzeit [min], Rüstzeit je", "einmal je Angebot oder je Abmessung (Profil)"],
        ["Zeit je Einheit [s], Einheit", "Zeit je Teil, je Stange oder je Position"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.text("Gerechnet wird je Arbeitsschritt <b>Gesamtzeit = Rüstzeit × Anzahl Rüstvorgänge + Zeit je Einheit × "
           "Menge</b> und <b>Kosten = Gesamtzeit in Minuten / 60 × Stundensatz</b>. Die weiteren Arbeitsschritte "
           "(Materialbereitstellung, Entgraten / Nachbearbeitung, Qualitätskontrolle, Verpackung, Sonstige "
           "Arbeiten) sind mit Zeit 0 vorbelegt und kosten erst etwas, wenn eine Zeit eingetragen ist. Ihre Kosten "
           "stehen als Kostenart <i>Weitere Arbeitsschritte</i> in der Kalkulation, mit Zuschlag Fertigung.")
    i.text("<b>Programmierung</b> ist ein Arbeitsschritt mit Zeit: je Position mit Stückzahl <i>Programmierzeit je "
           "Position</i> + <i>Programmierzeit je Innenkontur</i> × Anzahl Innenkonturen (Vorgaben, im Angebot "
           "änderbar; je Position von Hand in der Spalte <i>Programmierzeit [min]</i>) × Stundensatz "
           "<i>Programmierung</i> (Vorgabe in der Tabelle Arbeitsschritte, Art Personal, parallel zur Maschine). Im "
           "Reiter <i>Zeiten &amp; Arbeitskosten</i> steht sie mit Zeit und Stundensatz; die Kosten gehen wie bisher "
           "ohne Zuschläge und Gewinn in den Preis. Zusatzarbeiten und Gewinde mit Festpreis werden über ihren Preis "
           "gerechnet.")
    i.text("<b>Snapshot im Angebot</b>: Ein neues Angebot speichert beim Anlegen alle Stundensätze, die "
           "Arbeitsschritte und Stundensatz, Rüstzeit und Stangenwechsel der Maschine. Spätere Änderungen hier "
           "ändern bestehende Angebote nicht; im Angebot holt sie der Knopf <i>Stundensätze aus Einstellungen</i> "
           "([[zeiten]]). Eine Kopie übernimmt die Werte des Originals. Wird die Maschine eines Angebots "
           "gewechselt, gelten deren aktuelle Werte.")


def kapitel_mehrere(i):
    i.kapitel("Mehrere Arbeitsplätze: Kürzel, Nummernkreis und gemeinsamer Ordner", marke="mehrere_arbeitsplaetze")
    i.text("Jeder Mitarbeiter hat das Programm auf seinem Rechner, mit eigener Datendatei. Damit trotzdem jeder die "
           "Angebote der anderen sieht und alle mit denselben Stammdaten rechnen, gibt es das <b>Kürzel</b> und einen "
           "<b>gemeinsamen Ordner</b>.", kurz=True)
    i.bild("benutzer_dialog", "Datei → Benutzer und gemeinsamer Ordner …", hoehe=80 * mm)
    i.liste("<b>Kürzel</b> eintragen (z. B. PB): es zeigt, wer ein Angebot bearbeitet.",
            "<b>Gemeinsamer Ordner</b>: bei allen derselbe (Netzlaufwerk, NAS oder OneDrive).",
            "<b>Abgleichen</b> im Reiter Angebote holt die Angebote der Kollegen; beim Start und Beenden geht das "
            "von selbst.", nummeriert=True, kurz=True)
    i.abschnitt("Benutzer und Kürzel")
    i.genauer()
    i.liste("<b>Datei → Benutzer und gemeinsamer Ordner …</b> (beim ersten Start von selbst): Name, Kürzel, E-Mail "
            "und Telefon eintragen. Dieselben Felder stehen in den Einstellungen in der Gruppe <i>Benutzer</i>.",
            "Das <b>Kürzel</b> (Buchstaben und Ziffern, höchstens 5, z. B. PB) steht in der Spalte "
            "<b>Bearbeiter</b> und im Angebotskopf (Kürzel und Name), im Angebots-PDF rechts oben als "
            "<b>Ansprechpartner</b> mit Telefon und E-Mail. Eine Kopie bekommt immer das eigene Kürzel. In der "
            "Angebotsnummer steht es nicht (siehe Angebotsnummern).")
    i.abschnitt("Angebotsnummern")
    i.text("Alle Mitarbeiter zählen gemeinsam: <b>2026-00001</b>, 2026-00002 … Keine Nummer kommt doppelt vor.",
           kurz=True)
    i.genauer()
    i.liste("Die Nummer besteht aus dem Jahr und einem fünfstelligen Zähler. Der Zähler läuft über den "
            "Jahreswechsel weiter (2026-00731 → 2027-00732), er beginnt also nicht jedes Jahr neu.",
            "Bei <b>Neues Angebot</b> und <b>Kopieren</b> reserviert das Programm die nächste Nummer im gemeinsamen "
            "Ordner (Unterordner <i>Nummern</i>, je Nummer eine kleine Datei). Legen zwei Mitarbeiter im selben "
            "Augenblick ein Angebot an, bekommt der zweite automatisch die nächste Nummer.",
            "Eine vergebene Nummer wird nie wieder vergeben, auch wenn das Angebot gelöscht wird. Lücken in der "
            "Reihe sind deshalb möglich.",
            "<b>Ordner nicht erreichbar</b> (Laptop unterwegs, Netz weg): das Angebot bekommt eine <b>vorläufige "
            "Nummer</b> (V-PB-1); der Reiter zeigt <i>(vorläufige Nummer)</i>. Die endgültige Nummer kommt beim "
            "nächsten Abgleich von selbst (Meldung in der Statuszeile). Angebots-PDF und Materialanfrage gehen erst "
            "mit endgültiger Nummer: das Programm versucht sie dann sofort zu holen.",
            "Ohne gemeinsamen Ordner (nur ein Arbeitsplatz) zählt das Programm im gleichen Format auf diesem Rechner. "
            "Den Startwert setzt die Einstellung <i>Letzte Angebotsnummer</i> (z. B. 2026-00500: das nächste Angebot "
            "bekommt 2026-00501).",
            "Ältere Angebote behalten ihre Nummer (A-2026-0041, PB-2026-0001 …); sie zählen beim neuen Nummernkreis "
            "nicht mit.",
            "Gibt jemand eine Nummer von Hand doppelt ein, meldet der Abgleich das (<i>doppelte Angebotsnummer</i>); "
            "dann bei einem der beiden Angebote die Nummer im Angebotskopf ändern.")
    i.hinweis("Für einen garantiert eindeutigen Nummernkreis gehört der gemeinsame Ordner auf ein "
              "<b>Netzlaufwerk</b> (Server oder NAS im Firmennetz). Bei OneDrive/SharePoint kommt die Reservierung "
              "erst mit der Synchronisierung bei den Kollegen an; legen zwei in diesem Moment ein Angebot an, kann "
              "eine Nummer selten doppelt entstehen. Der Abgleich meldet das.")
    i.abschnitt("Gemeinsamer Ordner")
    i.genauer()
    i.text("Ein Ordner, den alle erreichen: ein Netzlaufwerk, eine NAS oder ein OneDrive-/SharePoint-Ordner, den "
           "alle synchronisieren. Jeder trägt denselben Ordner ein (im Dialog oder in den Einstellungen, Gruppe "
           "Benutzer: <i>Gemeinsamer Ordner der Mitarbeiter</i>; leer = nicht teilen). Darin legt jedes Programm genau eine Datei an, "
           "<i>Rohrlaser_PB.sqlite</i>, <i>Rohrlaser_MK.sqlite</i> …, und schreibt nur in seine eigene. Deshalb kann "
           "nichts kaputtgehen, wenn zwei gleichzeitig abgleichen, auch nicht über OneDrive. Die eigene Datei enthält "
           "alle eigenen Angebote (mit Positionen, Staffeln, STEP-Protokoll und 3D-Ansicht), die Stammdaten und die "
           "gemeinsamen Einstellungen.")
    i.tabelle(["Wann", "Was passiert"], [
        ["Programmstart", "holt Angebote und Stammdaten der Kollegen (ohne Fenster; Fehler nur in der Statuszeile)"],
        ["Knopf <b>Abgleichen</b> (Reiter Angebote) oder <i>Datei → Mit den Kollegen abgleichen</i> (Strg+Umschalt+A)",
         "holt den Stand der Kollegen und legt den eigenen in den Ordner"],
        ["Beenden", "legt die eigenen Angebote und Stammdaten in den Ordner; ist er nicht erreichbar, fragt das "
                    "Programm, ob trotzdem beendet werden soll"]],
        [80, 185])
    i.abschnitt("Angebote der Kollegen")
    i.text("Angebote der Kollegen stehen grau in der Liste: ansehen und drucken ja, ändern nein. <b>Als Kopie "
           "übernehmen</b> macht ein eigenes daraus.", kurz=True)
    i.genauer()
    i.liste("Stehen im Reiter Angebote grau und kursiv mit dem Kürzel des Kollegen ([[angebote]]).",
            "Geöffnet zeigt ein gelber Hinweis <i>Angebot von … – nur zum Ansehen</i>. Kopf, Positionen und die "
            "Knöpfe zum Bearbeiten sind gesperrt; Kalkulation, Staffeln, Stangenbild und die PDF-Ausgabe gehen. Ein "
            "solches PDF schreibt keine Preise fest und setzt keinen Vorgang.",
            "<b>Als Kopie übernehmen</b> (im Hinweis oder <i>Kopieren</i> in der Liste) legt ein eigenes Angebot mit "
            "eigener Nummer und heutigem Datum an.",
            "Ändert oder löscht der Kollege sein Angebot, zeigt der nächste Abgleich das auch hier; ein offenes "
            "Fenster lädt neu bzw. schließt sich.")
    i.abschnitt("Gemeinsame Stammdaten")
    i.text("Stammdaten und Einstellungen gelten für alle; bei gleichzeitigen Änderungen gewinnt die neueste.",
           kurz=True)
    i.genauer()
    i.text("Kunden, Profile, Werkstoffe, Preise, Lieferlängen, Maschinen, Schneiddaten, Gewinde, Zusatzarbeiten, "
           "Stundensätze, Zeitvorgaben, Blech-Richtwerte, Frachtkosten, Zukaufartikel und die Einstellungen gelten "
           "für alle. Geändert wird wie bisher an jedem Arbeitsplatz; der Abgleich bringt die Änderung zu den "
           "anderen. Für jede Zeile gilt die <b>neueste Änderung</b>: haben zwei dieselbe Zeile zwischen zwei "
           "Abgleichen geändert, gewinnt die spätere. Gelöschte Zeilen verschwinden auch bei den anderen. Legen zwei "
           "dieselbe Zeile getrennt an (z. B. dasselbe Profil), wird daraus eine.")
    i.text("Nur für den eigenen Arbeitsplatz gelten: Benutzer (Name, Kürzel, E-Mail, Telefon), gemeinsamer Ordner, "
           "Ablageordner, zweiter Sicherungsordner, STEP-Standardordner, Hilfetexte und die Signatur der "
           "Materialanfrage.")
    i.abschnitt("Erster Abgleich, neuer Rechner")
    i.genauer()
    i.liste("Liegen im Ordner schon Dateien von Kollegen, fragt der erste Abgleich: <b>Übernehmen</b> (empfohlen "
            "bei einer neuen Installation) ersetzt die eigenen Stammdaten durch die gemeinsamen, nach einer "
            "Sicherung (<i>_vor_Uebernahme</i>); eigene Angebote und Zukaufartikel bleiben. <b>Zusammenführen</b> "
            "bringt eigene Zeilen dazu, bei gleichen Zeilen gilt der gemeinsame Stand. Bis zu dieser Antwort "
            "schreibt das Programm nichts in den Ordner.",
            "Gibt es die Datei des eigenen Kürzels schon von einem anderen Rechner, fragt das Programm. Wer selbst "
            "an einem neuen Rechner sitzt, sagt <b>Ja</b>: die eigenen Angebote kommen von dort zurück und der "
            "Nummernzähler läuft weiter. Gehört das Kürzel einem Kollegen: <b>Nein</b> und ein anderes Kürzel "
            "eintragen.",
            "Arbeitet ein Kollege schon mit einer neueren Programmversion, übernimmt das Programm dessen Stammdaten "
            "erst nach dem eigenen Update (Hinweis beim Abgleich); seine Angebote kommen trotzdem.")
    i.hinweis("Das Kürzel ist eine Kennung, kein Zugriffsschutz: wer den gemeinsamen Ordner öffnen kann, sieht alle "
              "Angebote. Die Rechte am Ordner legt die IT bzw. der Ordnerbesitzer fest. Kollegen sehen den Stand des "
              "letzten Abgleichs, nicht live.")


def kapitel_stammdaten(i):
    i.kapitel("Stammdaten und Kunden", marke="stammdaten")
    i.abschnitt("Tabellen bearbeiten")
    i.text("Alle Tabellen funktionieren gleich: Zelle anklicken und lostippen, Enter speichert.", kurz=True)
    i.text("Die Kunden haben einen eigenen Reiter. Alle anderen Stammdaten (Profile, Werkstoffe, Oberflächen, Preise, "
           "Maschinen, Schneiddaten, Gewinde, Zusatzarbeiten, Stundensätze und Arbeitsschritte) stehen als Seiten in der "
           "Navigation links im Reiter <i>Einstellungen</i> ([[einstellungen]]), "
           "der mit einem Passwort geschützt ist ([[passwort]]). Alle Tabellen sind gleich aufgebaut:")
    i.bild("stamm_profile", "Einstellungen, Seite Profile", hoehe=125 * mm, legende=[
        (1, "Seite der Tabelle in der Navigation links. Oben steht der erste Satz des Hilfetextes, was in die Spalten gehört; "
            "<b>ⓘ mehr</b> zeigt den ganzen Text, <b>ⓘ weniger</b> klappt ihn wieder zu (bleibt je Tabelle so)."),
        (2, "<b>Neue Zeile</b> hängt eine leere Zeile an und springt hinein."),
        (3, "<b>Zeilen löschen</b> löscht die markierten Zeilen (vorher Rückfrage; verweisen andere Tabellen "
            "darauf, sagt das Programm wie viele)."),
        (4, "<b>Suchen</b> filtert die Tabelle nach jedem Text in jeder Spalte."),
        (5, "<b>Prüfung</b>: OK (grau), WARNUNG (gelb) oder FEHLER (rot) mit Begründung.")])
    i.liste("Seite links wählen, z. B. <i>Profile</i> (oder ins Suchfeld tippen).", "<b>Neue Zeile</b>, Werte eintippen, Enter.",
            "Rote oder gelbe Prüfung: Begründung lesen und den Wert korrigieren.", nummeriert=True, kurz=True)
    i.genauer()
    i.liste("Bearbeiten: Zelle doppelklicken oder einfach lostippen, mit Enter bestätigen. Felder mit fester Auswahl "
            "(Profilform, Preisbasis, Profil-ID …) zeigen eine Liste. Im Reiter <i>Kunden</i> zeigt der Doppelklick "
            "die Angebote des Kunden; dort wird durch Tippen oder F2 geändert.",
            "<b>Nur Fehler und Warnungen</b> (rechts neben der Suche) zeigt nur die Zeilen, die geprüft werden "
            "müssen; rechts daneben steht, wie viele Zeilen FEHLER und WARNUNG haben.",
            "Hilfetexte: unter Vorgaben, Gruppe Ansicht, <i>Hilfetexte über Tabellen und Seiten</i> = "
            "<i>aufklappbar</i> (erster Satz und ⓘ mehr) oder <i>nur Tooltip</i> (nur <b>ⓘ Hilfe</b>, der Text "
            "erscheint beim Zeigen mit der Maus) ([[vorgaben]]).",
            "Sortieren: auf den Spaltenkopf klicken. Spaltenbreite und Zeilenhöhe passen sich dem Inhalt an "
            "([[angebot]]); von Hand ändern: Trennlinie im Kopf ziehen.",
            "Wird eine Profil-, Werkstoff- oder Maschinen-ID umbenannt, ändern sich die Verweise in Preisen und "
            "Schneiddaten mit. Bei einer Maschinen-ID ändern sich auch die Angebote (mit ihren festgeschriebenen "
            "Werten) und die Standard-Maschine mit.")
    i.abschnitt("Was in welche Tabelle gehört")
    i.genauer()
    i.tabelle(["Tabelle", "Inhalt", "Wichtig"], [
        ["Kunden", "Kundennummer, Name, Anschrift, Ansprechpartner, Zahlungsbedingungen",
         "Im Angebotskopf die Kundennummer wählen: Name, Anschrift (im Angebots-PDF) und Zahlungsbedingungen "
         "kommen mit. Leere Zahlungsbedingungen = Vorgabe aus den Einstellungen."],
        ["Profile", "Profil-ID (z. B. <i>QR 40x40x3</i>), Form, Abmessungen, Wandstärke",
         "Abmessung A = Ø bzw. Breite, B = Höhe (nur Rechteckrohr). Endbeschnitt und Greiferrest nur bei "
         "Abweichung von der Maschine. Unbekannte Profile im Angebot legt das Programm aus der ID selbst an "
         "(RR/QR/RE-Schema)."],
        ["Werkstoffe", "Werkstoff-ID, Kategorie (Stahl, Edelstahl, Aluminium), Dichte, Tonnenpreis, Text im Angebot",
         "Der Tonnenpreis ergibt den Preis je kg, je m und je Stange, wenn unter Preise nichts steht. Die Kategorie "
         "ordnet die Auswahl im Angebot und liefert Schneiddaten, wenn der Werkstoff keine eigenen hat."],
        ["Oberflächen", "Oberfläche (z. B. roh, K240, gestrahlt), Kategorie, Aufpreis [€/m], Text im Angebot",
         "Je Position wählbar, leer = roh. Der Aufpreis kommt je Meter Stange auf den Materialpreis."],
        ["Preise", "Preis je Profil + Werkstoff in €/kg, €/m oder €/Stange",
         "Je Kombination höchstens eine Zeile. €/Stange bezieht sich auf die Liefer-Stangenlänge."],
        ["Lieferlängen", "weitere lieferbare Stangenlängen je Profil + Werkstoff (z. B. 12.000 mm), Preis",
         "Das Angebot vergleicht sie mit der Stangenlänge des Angebots ([[lieferlaengen]]). Kleine Profile, die es nicht in 12 m gibt, einfach "
         "nicht eintragen."],
        ["Maschinen", "Endbeschnitt, Greiferrest, Schnittverlust, max. Stangenlänge, Stundensatz, Konturgrenzen, "
                      "Rüstzeit, Stangenwechsel, max. Hüllkreis und Metergewicht",
         "Profile über dem max. Hüllkreis-Ø oder Metergewicht bekommen im Angebot FEHLER und werden nicht "
         "eingeplant (leer = keine Grenze)."],
        ["Schneiddaten", "Vorschübe je Maschine + Werkstoff oder Kategorie + Schneidgas (N₂/O₂), gestaffelt nach "
                         "Wandstärke; Einstechzeit",
         "Es gilt die Zeile mit der kleinsten „Wandstärke bis“, die mindestens der Profilwandstärke entspricht. "
         "N₂ solange es dafür eine Zeile gibt, darüber O₂."],
        ["Gewinde", "Gewinde, Kernloch-Ø, Zeit je Gewinde (wird nicht gerechnet), Preis je Gewinde [€]",
         "Der STEP-Import erkennt Kernlochbohrungen an diesem Durchmesser (±0,05 mm). Gerechnet wird nur der "
         "Preis je Gewinde (€ je Stück), je Position in Bohrungen prüfen änderbar ([[bohrungen_pruefen]])."],
        ["Zusatzarbeiten", "Zusatzarbeit (Name), Abrechnung, Preis [€] bzw. Zeit [s] je Einheit, Mindestbetrag je "
                           "Angebot [€], Fremdleistung, Text im Angebot",
         "Auswahl für den Knopf <i>Zusatzarbeiten …</i> im Angebot ([[zusatzarbeiten_angebot]]). Vorbelegt mit Beispielpreisen, "
         "bitte eigene eintragen."],
        ["Stundensätze", "Stundensatz-ID, Bezeichnung, Stundensatz [€/h]",
         "Sätze für Personal und Arbeitsplätze (Programmierung, Rüstpersonal, Nachbearbeitung …). Der Satz der "
         "Maschine steht bei der Maschine ([[stundensaetze]])."],
        ["Arbeitsschritte", "Arbeitsschritt, Stundensatz, Art, Rüstzeit, Zeit je Einheit",
         "Welcher Arbeitsschritt mit welchem Stundensatz und welcher Zeitvorgabe gerechnet wird ([[stundensaetze]])."]],
        [30, 95, 140])
    i.abschnitt("Kunden")
    i.bild("stamm_kunden", "Reiter Kunden", hoehe=100 * mm)
    i.text("Im Reiter <i>Kunden</i>: Kundennummer, Name und Anschrift eintragen. Im Angebotskopf die Kundennummer "
           "wählen, dann kommen Anschrift, Fracht-PLZ und Zahlungsbedingungen mit.", kurz=True)
    i.genauer("Felder")
    i.text("Die Spalten der Tabellen im Einzelnen. Pflichtfelder sind fett; was leer bleiben darf, rechnet das "
           "Programm wie angegeben.")
    i.tabelle(["Kunden", "Bedeutung"], [
        ["<b>Kundennummer</b>, <b>Kundenname</b>", "Schlüssel und Name; eine geänderte Kundennummer ändert sich auch "
                                                   "in den Angeboten"],
        ["Straße, PLZ Ort, Ansprechpartner", "Anschrift im Angebots-PDF (Ansprechpartner als „z. Hd.“)"],
        ["PLZ, Land", "Postleitzahl und Ländercode (z. B. DE) für die Frachtzone ([[frachtzonen]]); PLZ leer = Zahl aus "
                      "„PLZ Ort“, Land leer = DE"],
        ["Liefer-PLZ abweichend, Lieferland abweichend", "abweichende Lieferanschrift; wenn ausgefüllt, gilt sie für "
                                                         "die Fracht statt PLZ und Land"],
        ["Lieferbedingung", "frei Haus, frei Frachtführer, unfrei, ab Werk oder Abholung; bei unfrei, ab Werk und "
                            "Abholung trägt der Kunde die Fracht (Frachtkosten 0 €)"],
        ["Telefon, E-Mail", "zur Info"],
        ["Skonto [%], Skontofrist [Tage], Zahlungsziel netto [Tage]",
         "Zahlungsbedingungen des Kunden für neue Angebote; leer = Vorgabe aus den Einstellungen. Das Skonto wird in "
         "den Preis eingerechnet ([[kalkulation]])."],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.abschnitt("Kundenvorgaben", marke="kundenvorgaben")
    i.text("Einstellungen → <b>Kundenvorgaben</b>: je Kunde Maschine, Stangenlänge, Gewinn, Lieferzeit, Material und "
           "Standard-Staffeln. Wählen Sie den Kunden im Angebot, sind diese Kopffelder gleich richtig gefüllt.",
           kurz=True)
    i.genauer()
    i.text("Die Kundenvorgaben sind eine eigene Tabelle, getrennt von den Importprofilen (STEP) "
           "([[importprofile]]): je Kunde eine Zeile, leere Felder = Einstellungen. Ein neues Angebot für den Kunden "
           "bekommt die Vorgaben statt der Einstellungen. Wählen Sie den Kunden in einem vorhandenen Angebot, ersetzt "
           "das Programm ein Kopffeld nur, solange es leer ist oder noch die Vorgabe aus den Einstellungen bzw. des "
           "vorher gewählten Kunden hat. Von Hand geänderte Werte bleiben. Die Statuszeile nennt, was übernommen "
           "wurde. Wechseln Sie auf einen Kunden ohne Vorgabe, gelten für diese Felder wieder die Einstellungen.")
    i.bild("stamm_kundenvorgaben", "Einstellungen, Kundenvorgaben: je Kunde eine Zeile", hoehe=70 * mm)
    i.tabelle(["Kundenvorgaben", "Bedeutung"], [
        ["<b>Kunde</b>", "Kundennummer aus dem Reiter Kunden"],
        ["Maschine, Stangenlänge [mm], Gewinn [%]", "statt Standard-Maschine, Standard-Stangenlänge und Gewinn aus den "
                                                     "Einstellungen"],
        ["Lieferzeit als, Lieferzeit, Lieferbedingungen (Freitext)",
         "wie im Angebotskopf ([[lieferzeit]]); passt der Wert nicht zur Art, wird die Lieferzeit nicht übernommen"],
        ["Material neuer Positionen", "z. B. <i>Kunde beigestellt</i> für Kunden, die ihr Material immer selbst "
                                      "liefern ([[kundenmaterial]])"],
        ["Standard-Staffeln (Faktoren, 0 = keine)", "Faktoren wie in der Einstellung <i>Standard-Staffeln</i>, z. B. "
                                                    "1; 3; 10; 0 = für diesen Kunden keine Standard-Staffeln "
                                                    "([[staffeln]])"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.abschnitt("Kundenliste als CSV", marke="kunden_csv")
    i.liste("<b>CSV exportieren</b>: alle Kunden als Datei für Excel.",
            "<b>CSV importieren …</b>: Datei wählen, Vorschau prüfen (grün neu, gelb geändert, rot Fehler), dann "
            "<b>Importieren</b>.", nummeriert=True, kurz=True)
    i.genauer()
    i.text("Im Reiter <i>Kunden</i> speichert <b>CSV exportieren</b> alle Kunden als CSV-Datei (Semikolon, mit Excel "
           "zu öffnen): eine Zeile je Kunde, Kopfzeile mit den Spaltentiteln wie im Reiter, Zahlen mit Komma. So "
           "lässt sich die Liste in Excel bearbeiten oder aus einem anderen Programm übernehmen.",
           "<b>CSV importieren …</b> liest eine solche Datei und zeigt zuerst eine Vorschau: je Zeile <i>neu</i> "
           "(grün), <i>ändern</i> (gelb, mit alt → neu), <i>unverändert</i>, <i>übersprungen</i> (grau) oder "
           "<i>Fehler</i> (rot). Übernommen wird erst mit <b>Importieren</b>.")
    i.liste("Pflicht sind die Spalten Kundennummer und Kundenname; die Reihenfolge der Spalten ist egal, fehlende "
            "Spalten bleiben beim Kunden unverändert. Auch Kopfzeilen wie <i>Kundennr.</i>, <i>Name</i> oder "
            "<i>Ort</i> werden erkannt.",
            "Gibt es die Kundennummer schon, ändert der Import diesen Kunden: die Werte aus der Datei ersetzen die "
            "alten (eine leere Zelle leert das Feld). Mit dem Häkchen <b>Vorhandene Kunden nicht ändern (nur neue "
            "anlegen)</b> bleiben sie unverändert und stehen als <i>übersprungen</i> in der Vorschau.",
            "Nicht übernommen werden Zeilen mit Fehler: Pflichtfeld leer, Kundennummer doppelt in der Datei, Zahl "
            "außerhalb des Bereichs (z. B. Skonto über 20 %), unbekannte Lieferbedingung, Land nicht als Ländercode.",
            "Excel entfernt führende Nullen. Eine deutsche PLZ mit vier Ziffern (z. B. 1067) ergänzt der Import "
            "wieder zu 01067 und sagt das in der Vorschau. Kundennummern mit führender Null in Excel als Text "
            "formatieren.",
            "Vor dem Import legt das Programm eine Datensicherung an (Name endet auf <i>_vor_Kundenimport</i>), "
            "der alte Stand lässt sich zurückholen ([[datensicherung]]).")
    i.abschnitt("Profile")
    i.text("Profil-ID, Form, Maße und Wandstärke. Unbekannte Rohre im Angebot oder STEP-Import legt das Programm "
           "selbst an.", kurz=True)
    i.genauer("Felder")
    i.tabelle(["Profile", "Bedeutung"], [
        ["<b>Profil-ID</b>", "Name des Profils, z. B. <i>RR 42,4x2,0</i>, <i>QR 40x40x3</i>, <i>RE 60x40x3</i>, "
                             "<i>U 50x30x3</i>, <i>C 100x50x3</i>, <i>L 40x40x4</i>, <i>FL 40x5</i>, Normprofile "
                             "wie <i>IPE 200</i>, <i>HEB 160</i>, <i>UPN 100</i>, <i>T 50</i>, sonst Träger als "
                             "<i>I Höhe x Breite x Steg x Flansch</i> (z. B. <i>I 150x80x5x7</i>, <i>T 60x40x5x7</i>). Im "
                             "Angebotstext stehen Träger, T- und U-Profile mit ihrer Normbezeichnung (IPE, HEA, HEB, "
                             "HEM, IPN, UPN, T), wenn Höhe, Breite und Steg zur Normtabelle passen, auch bei einer "
                             "Profil-ID mit Maßen; sonst z. B. „I-Träger 150 x 80 x 5“."],
        ["<b>Profilform</b>", "Rundrohr, Quadratrohr, Rechteckrohr, U-Profil, C-Profil, L-Profil, Flachstahl, "
                              "I-/H-Träger, T-Profil, RP-Profil oder Sonderprofil (Liste in den Einstellungen)"],
        ["<b>Abmessung A [mm]</b>, Abmessung B [mm]",
         "Rohre: A = Ø bzw. Breite, B = Höhe (nur Rechteckrohr). U- und C-Profil: A = Steg, B = Flansch. "
         "L-Profil: A und B = Schenkel. Flachstahl: A = Breite, B leer. I-/H-Träger und T-Profil: A = Höhe, "
         "B = Flanschbreite. RP-Profil: A = Breite, B = Höhe, Wandstärke = Blechdicke"],
        ["<b>Wandstärke [mm]</b>", "bestimmt Querschnitt, Gewicht und die Zeile der Schneiddaten; bei offenen "
                                   "Profilen die Blechdicke, bei Flachstahl die Dicke, bei Trägern und T-Profilen die "
                                   "Stegdicke"],
        ["Fläche manuell [mm²]", "Querschnitt vom Hersteller (Eckradien, Sonderprofile); leer = aus den Maßen. "
                                 "Beim C-Profil Pflicht, weil die Abkantung nicht in den Maßen steht (der STEP-Import "
                                 "trägt die gemessene Fläche ein). Bei I-/H-Trägern und T-Profilen kommt der "
                                 "Querschnitt aus der Normtabelle (IPE, IPN, HEA, HEB, HEM, T nach EN 10365 und "
                                 "EN 10055), sonst ist Fläche manuell Pflicht, weil die Flanschdicke nicht in den "
                                 "Maßen steht"],
        ["Endbeschnitt abweichend [mm], Greiferrest abweichend [mm]",
         "nur eintragen, wenn das Profil andere Werte braucht als die Maschine"],
        ["Wandstärke max. [mm]", "dickste Stelle des Profils, z. B. die Flanschdicke eines Trägers oder die dickere "
                                 "Wand eines Sonderprofils. Die <b>Schneidzeit</b> (Vorschub, Einstechzeit, Schneidgas) "
                                 "rechnet immer mit der größeren der beiden Wandstärken; Gewicht und Querschnitt "
                                 "bleiben bei der Wandstärke. Leer = bei Normprofilen (IPE, HEA, HEB, HEM, IPN, UPN, "
                                 "T) die Flanschdicke aus der Normtabelle, sonst die Wandstärke. Der STEP-Import trägt "
                                 "bei neu angelegten Profilen die größte gemessene Wand bzw. Flanschdicke ein. Ein "
                                 "Sonderprofil ohne beide Werte bekommt die Warnung <i>Wandstärke fehlt</i>, weil es "
                                 "ohne sie keine Schneidzeit gibt."],
        ["Lieferlängen vergleichen", "leer oder ja = Lieferlängen aus der Tabelle Lieferlängen werden verglichen; "
                                     "nein = das Profil wird nur mit der Stangenlänge des Angebots geplant (z. B. "
                                     "kleine Rohre, auch wenn es eine 12-m-Zeile gibt)"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.abschnitt("RP-Profile (Rohre mit Anschlag)", marke="rp_profile")
    i.text("RP-Profile sind mitgeliefert. Neue kommen mit <b>RP-Profile aus MegaCAD laden …</b> aus den .mac-Dateien; "
           "<b>RP-Querschnitt …</b> zeigt die Kontur.", kurz=True)
    i.genauer()
    i.text("RP-Profile sind kaltgeformte Stahlrohre mit einem Anschlag aus doppelt umgelegtem Blech (Serien mit "
           "34, 40, 50, 60 und 80 mm Bautiefe). Ihr Querschnitt hat keine einfachen Maße, deshalb rechnet das "
           "Programm Fläche, Gewicht, Außenumfang und Schnittlänge aus der <b>Kontur</b> des MegaCAD-Makros.")
    i.liste("<b>Mitgeliefert</b>: die Bibliothek RP-ROHRE (Serie-34 bis Serie-80 und Zubehör-Rohre, gut 140 "
            "Profile) steht schon in den Profilen, Profilform <i>RP-Profil</i>, Profil-ID <b>RP</b> + Dateiname "
            "des Makros, z. B. <i>RP 0106-35</i> (RP-Nummer und Kammerbreite). Ältere Datendateien bekommen sie beim "
            "ersten Start dazu; vorhandene Zeilen bleiben unverändert.",
            "<b>RP-Profile aus MegaCAD laden …</b> (über der Tabelle Profile): eine oder mehrere .mac-Dateien "
            "wählen. Neue Profile werden angelegt, eine vorhandene Zeile mit derselben Profil-ID bekommt Form, Maße, "
            "Blechdicke und Fläche aus dem Makro. Die Kontur bleibt in der Datendatei gespeichert.",
            "Nicht übernommen (Meldung unten im Fenster): offene Profile ohne Kammer (Zubehör wie 400180 bis "
            "400330, kein Rohrlaser-Teil) und Zeichnungen ohne erkennbare Blechdicke (z. B. Befestigungen).",
            "<b>RP-Querschnitt …</b> zeigt die Kontur der markierten Zeile mit Breite, Höhe, Blechdicke, Fläche, "
            "Gewicht je Meter, Außenumfang, Schnittlänge und Zahl der Ecken.",
            "<b>Schnittlänge</b>: Außenumfang ohne die doppelt liegende Blechlage, denn der Anschlag wird mit einem "
            "Schnitt durch beide Lagen getrennt. Bei Gehrungen rechnet der Schneidweg-Rechner jede Kante mit ihrer "
            "Richtung zur Gehrungsachse ([[schneidweg_rechner]]). Hüllkreis = Diagonale aus Breite und Höhe.",
            "<b>Schneidzeit</b>: der Schnitt durch den Anschlag (Doppellage) läuft mit den Schneiddaten der "
            "doppelten Wand (bei 2 mm Blech die 4-mm-Zeile), der Rest mit der Blechdicke; bei schrägen Enden "
            "entsprechend länger. Dazu kommt je Ecke der Kontur die <i>Zeit je Ecke</i> der Schneiddaten. Beides "
            "steht in den Spalten <i>davon Ecken</i> und <i>davon Anschlag doppelt</i>. Fehlt die Zeile für die "
            "doppelte Wand, meldet die Position eine WARNUNG.",
            "<b>Maschine</b>: <i>RP-/Sonderprofile spannbar</i>, <i>Rüstzuschlag Sonderprofil</i> und "
            "<i>Mindestabstand Düse</i> in den Maschinen legen fest, ob die Maschine RP-Profile spannt, wie viel "
            "Rüstzeit je RP-Abmessung dazukommt und ab wann Innenkonturen unter dem Anschlag geprüft werden müssen.")
    i.abschnitt("Werkstoffe und Oberflächen")
    i.bild("stamm_werkstoffe", "Einstellungen, Werkstoffe mit Kategorie", hoehe=100 * mm)
    i.text("Werkstoff mit Kategorie (Stahl, Edelstahl, Aluminium), Dichte und Tonnenpreis. Oberflächen mit Aufpreis "
           "je Meter.", kurz=True)
    i.bild("stamm_oberflaechen", "Einstellungen, Oberflächen mit Beispiel-Aufpreisen", hoehe=80 * mm, kurz=False)
    i.genauer("Felder")
    i.tabelle(["Werkstoffe", "Bedeutung"], [
        ["<b>Werkstoff-ID</b>", "Schlüssel für Preise, Schneiddaten und Positionen, z. B. <i>S235-10219</i>"],
        ["Kategorie", "Stahl, Edelstahl oder Aluminium (Liste in den Einstellungen). Im Angebot sind die Werkstoffe "
                      "danach gruppiert; ohne eigene Schneiddaten gelten die der Kategorie."],
        ["Werkstoff, Werkstoff-Nr., Norm / Qualität", "Bezeichnung, Nummer (z. B. 1.0039) und Norm, nur zur Info"],
        ["<b>Dichte [kg/dm³]</b>", "für Gewicht und Preis je kg"],
        ["Tonnenpreis [€/t]", "Materialpreis, wenn unter Preise nichts steht"],
        ["Text im Angebot", "so steht der Werkstoff in der Bezeichnung im Angebot"],
        ["Anfrage: Prüfbescheinigung, Anfrage: Herkunft EU, Anfrage: Maßtoleranzen nach Norm",
         "Anforderungen, die in der Materialanfrage unter dem Werkstoff stehen: Prüfbescheinigung 2.2, 3.1 oder 3.2 "
         "nach EN 10204, ja/nein für Herkunft EU und Maßtoleranzen nach Norm; leer = keine ([[materialanfrage]])"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.text("Vorbelegt sind Stahl (S235JRH, S355J2H, E235, E355), Edelstahl (1.4301, 1.4307, 1.4404, 1.4571, "
           "1.4509) und Aluminium (EN AW-6060, 6063, 6082) mit Beispiel-Tonnenpreisen. Ältere Datendateien "
           "bekommen beim ersten Start die fehlenden Werkstoffe dazu; vorhandene bleiben unverändert und erhalten "
           "eine Kategorie (Dichte unter 4 = Aluminium, 1.4… = Edelstahl, sonst Stahl).")
    i.tabelle(["Oberflächen", "Bedeutung"], [
        ["<b>Oberfläche</b>", "Name, z. B. <i>roh</i>, <i>K240</i>, <i>gestrahlt</i>; Auswahl in der Position"],
        ["Kategorie (leer = alle)", "für welche Werkstoffe die Oberfläche passt; sonst Warnung in der Position"],
        ["Aufpreis [€/m]", "kommt je Meter Stange auf den Materialpreis (Preise bzw. Tonnenpreis). Ein abweichender "
                           "Materialpreis in der Position ersetzt Preis und Aufpreis."],
        ["Text im Angebot", "steht hinter dem Werkstoff in der Bezeichnung, z. B. „Oberfläche K240 geschliffen“"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.text("Teile mit unterschiedlicher Oberfläche kommen nie auf dieselbe Stange: optimiert wird je Profil + "
           "Werkstoff + Oberfläche + Stangenlänge. Leer und <i>roh</i> sind gleich.")
    i.abschnitt("Preise und Lieferlängen")
    i.bild("stamm_preise", "Einstellungen, Preise je Profil und Werkstoff", hoehe=95 * mm)
    i.text("<b>Preise</b>: Materialpreis je Profil und Werkstoff in €/kg, €/m oder €/Stange. <b>Lieferlängen</b>: "
           "weitere lieferbare Längen, z. B. 12 m.", kurz=True)
    i.bild("stamm_lieferlaengen", "Einstellungen, Lieferlängen: 12-m-Stangen für ein Rundrohr", hoehe=70 * mm, kurz=False)
    i.genauer("Felder")
    i.tabelle(["Preise", "Bedeutung"], [
        ["<b>Profil-ID</b>, <b>Werkstoff-ID</b>", "Kombination, für die der Preis gilt"],
        ["<b>Preisbasis</b>, <b>Preis [€]</b>", "€/kg, €/m oder €/Stange und der Betrag"],
        ["Liefer-Stangenlänge [mm]", "Pflicht bei €/Stange: Länge, auf die sich der Stangenpreis bezieht"],
        ["Gültig ab, Lieferant, Bemerkung", "zur Info, z. B. Datum des Lieferantenangebots"]], [75, 190])
    i.tabelle(["Lieferlängen", "Bedeutung"], [
        ["<b>Profil-ID</b>, <b>Werkstoff-ID</b>, <b>Lieferlänge [mm]</b>",
         "Kombination und Länge, in der das Material zusätzlich lieferbar ist, z. B. <i>QR 40x40x3</i>, "
         "<i>S235-10219</i>, 12.000. Je Kombination beliebig viele Längen."],
        ["Preisbasis (leer = wie Preise), Preis [€]",
         "eigener Preis dieser Länge in €/kg, €/m oder €/Stange (je Stange dieser Länge), z. B. mit "
         "Längenzuschlag. Beide leer = €/kg- bzw. €/m-Preis aus <i>Preise</i>, ohne Zeile dort der Tonnenpreis. Steht "
         "in Preise ein Preis je Stange einer anderen Länge, ist hier ein eigener Preis nötig, sonst meldet der "
         "Vergleich <i>Angaben fehlen</i>."],
        ["Gültig ab, Lieferant, Bemerkung", "zur Info"]], [75, 190])
    i.liste("Ohne Zeile in Lieferlängen gelten Profile mit Hüllkreis-Ø über 70 mm (Einstellung, 0 = aus) "
            "zusätzlich als 12 m lieferbar, zum Preis aus <i>Preise</i> bzw. zum Tonnenpreis. Kleinere Profile ohne "
            "Zeile werden nie mit 12 m geplant. Eine eigene Zeile geht immer vor; <i>Lieferlängen vergleichen = "
            "nein</i> am Profil schließt es ganz aus.",
            "Gibt es für Profil + Werkstoff Zeilen, ist die Stangenlänge des Angebots (meist 6.000 mm) nur lieferbar, "
            "wenn sie hier oder als Liefer-Stangenlänge in <i>Preise</i> steht. Steht dort nur 12.000, plant das "
            "Programm keine künstliche 6-m-Variante.",
            "Längen über der <i>Max. Stangenlänge</i> der Maschine (Beladelänge, z. B. 6.500 mm) werden nie als "
            "ein Stück geladen: der Lieferant schneidet sie auf die geplanten Stangenlängen zu.")
    i.abschnitt("Maschinen, Schneiddaten und Gewinde")
    i.bild("stamm_maschinen", "Einstellungen, Maschinen: die Werte gelten für jedes Angebot mit dieser Maschine",
           hoehe=125 * mm)
    i.text("<b>Maschinen</b>: Stundensatz, Reste, Stangenlänge und Grenzen. <b>Schneiddaten</b>: Vorschub und "
           "Einstechzeit je Wandstärke und Gas. <b>Gewinde</b>: Kernloch und Preis je Gewinde.", kurz=True)
    i.bild("stamm_schneiddaten", "Einstellungen, Schneiddaten: Zeilen je Kategorie und Schneidgas", hoehe=110 * mm, kurz=False)
    i.bild("stamm_gewinde", "Einstellungen, Gewinde mit Kernloch, Zeit und Preis", hoehe=95 * mm, kurz=False)
    i.genauer("Felder")
    i.text("Vorbelegt sind die Maschinen T03 (Trumpf, CO₂-Laser), T11 (Trumpf, Faserlaser) und LT7 (Adige, "
           "Faserlaser): Endbeschnitt 10 mm, Schnittverlust 0,2 mm, max. Stangenlänge 6.500 mm, 150 €/h, Konturgrenzen "
           "10 und 50 mm, Abstand getrennte Schnitte 5 mm, Rüstzeit 5 min; Greiferrest 142 mm (LT7 120 mm), "
           "Stangenwechsel 24 s, Stangenwechsel SN 29 s, Hüllkreis-Ø 255 mm (LT7 214 mm), Metergewicht 36 kg/m "
           "(LT7 23 kg/m), min. Stangenlänge im Zuschnitt 2.500 mm. Ältere Datendateien: T03, T11 und LT7 mit dem "
           "alten Stangenwechsel (29 bzw. 25 s) bekommen 24 s und SN 29 s, jede andere Maschine nimmt ihren "
           "Stangenwechsel auch als SN-Zeit. "
           "Standard-Maschine ist T03. Beim Update einer älteren Datendatei werden unveränderte Beispielmaschinen "
           "RL-1 und RL-2 zu T03 und T11 (mit ihren Angeboten), LT7 kommt dazu, unveränderte alte "
           "Beispiel-Schneiddaten werden durch die neuen Richtwerte ersetzt; eigene Werte bleiben, vorher wird eine "
           "Sicherung angelegt.")
    i.tabelle(["Maschinen", "Bedeutung"], [
        ["<b>Maschinen-ID</b>, Bezeichnung", "Kurzname (Auswahl im Angebotskopf) und Klartext"],
        ["Endbeschnitt [mm], Greiferrest [mm]", "Anschnitt am Stangenanfang und nicht nutzbares Ende im Greifer"],
        ["Schnittverlust je Schnitt [mm]", "Materialverlust je Trennschnitt (Schnittbreite)"],
        ["Abstand getrennte Schnitte [mm]", "Steg zwischen zwei Teilen, wenn sich die Enden keinen Schnitt teilen"],
        ["Max. Stangenlänge [mm]", "längste Stange, die die Maschine laden kann (Beladelänge); auch die Grenze für "
                                   "Werkstücke aus längeren Lieferstangen"],
        ["Stundensatz [€/h]", "Stundensatz <i>Maschine</i>: für Laserzeit, Gewinde ohne Festpreis, Rüsten und "
                              "Stangenwechsel, solange unter Arbeitsschritte nichts anderes gewählt ist"],
        ["Kontur klein bis [mm], Kontur mittel bis [mm]",
         "Grenzen der Konturklassen nach Hüllmaß für Innenkonturen, Anfangs- und Endschnitt (Vorgabe 10 und 50 mm), "
         "je Klasse eigener Vorschub. Nach einer Änderung werden die Positionen beim nächsten Öffnen des Angebots "
         "neu eingeteilt ([[konturklassen]])"],
        ["Kontur klein bis [× Wand], Kontur mittel bis [× Wand]",
         "zusätzliche Grenzen nach Hüllmaß ÷ Wandstärke (Vorgabe 3 und 8); es gilt die strengere Klasse aus mm- und "
         "Wand-Grenze ([[konturklassen]])"],
        ["Min. Stangenlänge Zuschnitt [mm]", "kürzeste Stange, die die automatische Stangenladung nimmt (Vorgabe "
                                             "2.500 mm); keine aus einer Lieferstange zugeschnittene Stange "
                                             "wird kürzer ([[lieferlaengen]]), leer oder 0 = keine Grenze"],
        ["Rüstzeit je Angebot [min], Stangenwechsel je Stange [s]", "Zeiten, die auf alle Teile verteilt werden"],
        ["Stangenwechsel SN je Stange [s]", "Stangenwechsel für Stangen, auf denen ein Teil eine feste "
                                           "Schweißnaht-Lage hat (Naht ausrichten, Vorgabe 29 s); leer = wie "
                                           "Stangenwechsel ([[schweissnaht]])"],
        ["Max. Hüllkreis-Ø [mm], Max. Metergewicht [kg/m]",
         "Grenzen der Maschine; größere oder schwerere Profile werden nicht eingeplant (leer = keine Grenze)"],
        ["3D: Bearbeitung verfügbar", "ja = die Maschine kann den Laserkopf schwenken (Gehrungen in 3D, schräge "
                                      "Bohrungen). Vorgabe nein: 3D wird nur kalkuliert, wenn es hier eingeschaltet "
                                      "ist"],
        ["3D: Schwenkwinkel min. [°], 3D: Schwenkwinkel max. [°]", "Grenzen des Kopfschwenks (Vorgabe −45° und +45°); größere Winkel "
                                              "werden auf die Grenze begrenzt. Eine Gehrung in 3D braucht beide "
                                              "Richtungen, dort gilt die kleinere Grenze"],
        ["3D: Greifmaß [mm]", "Abstand, den eine 3D-Bearbeitung am letzten Teil einer Stange vom Stangenende "
                              "braucht (Vorgabe 300 mm). Zählt statt des Greiferrests, wenn größer, nie zusätzlich"],
        ["3D: Zusatzzeit je Bearbeitung [s], 3D: Faktor Schneidzeit",
         "Zeit je 3D-Bearbeitung (Kopf schwenken, Vorgabe 0 s) und Faktor auf die 3D-Schneidzeit (Vorgabe 1,0); "
         "erst mit echten Zeiten der Maschine ändern"],
        ["RP-/Sonderprofile spannbar", "nein = Positionen mit RP-Profil oder Sonderprofil bekommen die WARNUNG "
                                       "<i>Maschine prüfen</i>; leer = ja ([[rp_profile]])"],
        ["Rüstzuschlag Sonderprofil [min je Abmessung]", "zusätzliche Rüstzeit je RP-/Sonderprofil-Abmessung "
                                                          "(Spannbacken, Anlage), wie Rüsten je Abmessung bewertet "
                                                          "und auf deren Teile verteilt; gilt für Angebote mit den "
                                                          "aktuellen Zeitvorgaben"],
        ["Mindestabstand Düse [mm]", "steht der Anschlag eines RP-Profils weiter über, bekommen Positionen mit "
                                     "Innenkonturen die WARNUNG <i>Innenkonturen unter dem Anschlag prüfen</i> "
                                     "(die Düse kommt unter dem Anschlag schlecht an die Wand); leer = keine "
                                     "Prüfung"],
        ["Kürzestes Teil [mm]", "kürzere Teile kann die Maschine nicht fertigen; sie bekommen die Stufe der "
                                "Prüfregel <i>Teil zu kurz für die Maschine</i> ([[pruefregeln]]); leer = keine "
                                "Grenze"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.tabelle(["Schneiddaten", "Bedeutung"], [
        ["<b>Maschinen-ID</b>, <b>Wandstärke bis [mm]</b>",
         "für welche Maschine und bis zu welcher Wandstärke die Zeile gilt"],
        ["Werkstoff-ID oder Kategorie",
         "eins von beiden: eine Zeile mit Werkstoff-ID gilt nur für diesen Werkstoff und geht vor; eine Zeile mit "
         "Kategorie (Werkstoff-ID leer) gilt für alle Werkstoffe der Kategorie ohne eigene passende Zeile"],
        ["Schneidgas", "N₂ (Stickstoff) oder O₂ (Sauerstoff); die Vorschübe gelten für dieses Gas. Das Programm "
                       "nimmt N₂, solange es eine N₂-Zeile für die Wandstärke gibt, darüber O₂. Wo die N₂-Zeilen "
                       "enden, legt also fest, ab welcher Wandstärke nur noch mit O₂ geschnitten wird."],
        ["<b>Vorschub groß / Trennschnitt [mm/min]</b>", "für große Konturen und Enden sowie den Schneidweg ohne "
                                                          "Klasse (z. B. von Hand eingetragen)"],
        ["Vorschub mittel [mm/min], Vorschub klein [mm/min]",
         "für mittlere und kleine Konturen und Enden; leer = nächstgrößerer Vorschub"],
        ["Vorschub Gravur [mm/min]", "für Gravuren; leer = nächstgrößerer Vorschub"],
        ["Einstechzeit [s]", "Zeit je Einstich"],
        ["Bemerkung", "freier Text"],
        ["Zeit je Ecke [s]", "Zuschlag je Ecke im Anfangs- und Endschnitt (der Laser bremst in der Ecke): "
                             "RP-Profile nach der Zahl der Ecken ihrer Kontur, Quadrat- und Rechteckrohr 4 je Ende, "
                             "andere Profile 0; leer = 0. Ein gemeinsamer Schnitt spart auch diese Zeit"]], [75, 190])
    i.text("Vorbelegt sind Richtwerte je Kategorie für die Maschinen T03 (Trumpf, CO₂-Laser 3,2 kW), T11 (Trumpf, "
           "Faserlaser 4 kW) und LT7 (Adige, Faserlaser 3 kW). Seit Version 0.6.19 stammen die Faserlaser-Werte aus "
           "Rohr-Schnitttabellen für 3 und 4 kW: Am Rohr begrenzt bei dünnen Wänden die Drehachse, darum höchstens "
           "8.000 mm/min bis 2 mm Wand (Stahl 1 mm 8.000, 2 mm 7.000, 3 mm 4.500 mm/min mit N₂ auf LT7). Mehr "
           "Leistung hilft erst ab 3 mm: T11 hat bis 2 mm dieselben Werte wie LT7, darüber rund 30 % mehr (z. B. "
           "Stahl 8 mm mit O₂ 2.100 statt 1.300 mm/min). Die CO₂-Werte sind Schätzwerte. Es sind keine "
           "Herstellerwerte, bitte mit echten Schnittzeiten der Maschine vergleichen und anpassen. Faserlaser: Stahl "
           "mit N₂ bis 4 mm, darüber O₂ bis 12 mm, Edelstahl mit N₂ bis 10 mm, Aluminium mit N₂ bis 8 mm. CO₂-Laser: "
           "Stahl mit N₂ bis 2 mm, darüber O₂ bis 12 mm, Edelstahl mit N₂ bis 8 mm, Aluminium mit N₂ bis 6 mm. "
           "Vorschub mittel ist 60 %, klein 30 % von groß, Vorschub Gravur 3.000 mm/min. Beim ersten Start von "
           "0.6.19 bekommen unveränderte Richtwert-Zeilen älterer Datendateien die neuen Werte (vorher wird eine "
           "Sicherung angelegt); von Hand geänderte Zeilen bleiben. Eigene Schneiddaten älterer Datendateien bleiben "
           "erhalten und gehen vor; ohne Schneidgas zählen sie nach N₂ und O₂. Welche Wandstärke-Stufe und welches "
           "Gas eine Position nutzt, zeigt der Reiter Kalkulation (Spalten Wandstärke-Stufe und Schneidgas).")
    i.text("Die Prüfspalte warnt, wenn ein Vorschub nicht passt: Vorschub mittel oder klein größer als groß, oder "
           "ein höherer Vorschub als bei der nächstdünneren Wandstärke derselben Maschine, desselben Werkstoffs "
           "bzw. derselben Kategorie und desselben Gases. In den Maschinen warnt sie, wenn einer Maschine "
           "Schneiddaten ganz oder für eine Kategorie fehlen.")
    i.tabelle(["Gewinde", "Bedeutung"], [
        ["<b>Gewinde</b>, <b>Kernloch Ø [mm]</b>",
         "z. B. M6 mit 5,0 mm; der STEP-Import schlägt Gewinde an diesem Durchmesser vor"],
        ["Zeit je Gewinde [s] (wird nicht gerechnet), Preis je Gewinde [€]",
         "nur der Preis je Stück zählt; ohne Preis 0 € und eine Warnung an der Position"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.abschnitt("Schneiddaten auf Standard zurücksetzen", marke="schneiddaten_standard")
    i.text("<b>Auf Standard zurücksetzen …</b> im Unterreiter Schneiddaten holt die mitgelieferten Richtwerte "
           "zurück; eigene Werte der gewählten Maschine gehen dabei verloren.", kurz=True)
    i.genauer()
    i.text("Im Unterreiter <i>Schneiddaten</i> stellt die Schaltfläche <b>Auf Standard zurücksetzen …</b> (rechts "
           "neben <i>Zeilen löschen</i>) die mitgelieferten Richtwerte wieder her, z. B. wenn eigene Versuche die "
           "Tabelle durcheinandergebracht haben:")
    i.liste("In der Auswahl <i>Alle Maschinen (T03, T11, LT7)</i> oder eine einzelne Maschine wählen.",
            "Die Sicherheitsabfrage nennt, wie viele Zeilen gelöscht werden. Erst mit <b>Ja</b> wird zurückgesetzt; "
            "vorgewählt ist <b>Nein</b>.",
            "Alle Zeilen der gewählten Maschine(n) werden gelöscht, auch eigene Werte und Zeilen je Werkstoff, und "
            "durch die Richtwerte je Kategorie ersetzt. Die Statuszeile meldet, wie viele Zeilen entfernt und "
            "eingefügt wurden.", nummeriert=True)
    i.hinweis("Schneiddaten anderer, selbst angelegter Maschinen bleiben unverändert, für sie gibt es keine "
              "Richtwerte. Angebote mit festgeschriebenen Preisen rechnen mit ihren Schneiddaten weiter "
              "([[preise_festschreiben]]). Rückgängig machen geht nur über eine Datensicherung ([[datensicherung]]), "
              "deshalb vor dem Zurücksetzen eigene Werte bei Bedarf sichern.")
    i.abschnitt("Blech-Werkstoffe und Blechlaser (Richtwerte)", marke="blech_stammdaten")
    i.text("Die Unterreiter <i>Blech-Werkstoffe</i>, <i>Blechlaser (Richtwerte)</i> und <i>K-Faktoren "
           "(Abwicklung)</i> gehören nur zum "
           "Blech-Editor ([[blech_editor]]). Sie sind von den Werkstoffen, Maschinen und Schneiddaten des "
           "Rohrlasers getrennt: was hier steht, ändert keine Rohrkalkulation.", kurz=True)
    i.bild("stamm_blech_werkstoffe", "Einstellungen, Blech-Werkstoffe mit Preis je kg und K-Faktor", hoehe=80 * mm)
    i.bild("stamm_blechlaser", "Einstellungen, Blechlaser (Richtwerte) je Kategorie, Gas und Blechdicke",
           hoehe=100 * mm, kurz=False)
    i.bild("stamm_blech_kfaktoren", "Einstellungen, K-Faktoren (Abwicklung) je Kategorie, Blechdicke und "
           "Innenradius ÷ Dicke", hoehe=90 * mm, kurz=False)
    i.genauer("Felder")
    i.tabelle(["Blech-Werkstoffe", "Bedeutung"], [
        ["<b>Blech-Werkstoff</b>, Bezeichnung / Norm", "Name in der Auswahl des Blech-Editors (z. B. S235JR, "
                                                       "1.4301 2B, AlMg3) und Beschreibung"],
        ["<b>Kategorie</b>", "Stahl, Edelstahl oder Aluminium; wählt die Blechlaser-Richtwerte"],
        ["<b>Dichte [kg/dm³]</b>, <b>Preis [€/kg]</b>", "für Gewicht und Materialpreis je kg Tafel"],
        ["K-Faktor", "Lage der neutralen Faser als Anteil der Blechdicke für die Abwicklung (leer = 0,33)"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.tabelle(["Blechlaser (Richtwerte)", "Bedeutung"], [
        ["<b>Kategorie</b>, <b>Schneidgas</b>, <b>Blechdicke bis [mm]</b>",
         "es gilt die Zeile mit der kleinsten Blechdicke bis, die mindestens der Dicke entspricht; N₂, solange es "
         "eine N₂-Zeile gibt, darüber O₂"],
        ["<b>Vorschub Außenkontur [mm/min]</b>, Vorschub Innenkonturen [mm/min]",
         "für Außenkontur bzw. Innenkonturen; Innenkonturen leer = halber Vorschub Außenkontur"],
        ["Einstechzeit [s]", "Zeit je Einstich"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.text("Vorbelegt sind Richtwerte eines Faserlasers mit etwa 6 kW: Stahl mit N₂ bis 6 mm (1 mm 30.000, 3 mm "
           "10.000, 6 mm 3.200 mm/min), darüber O₂ bis 20 mm (10 mm 2.000, 20 mm 800 mm/min); Edelstahl und "
           "Aluminium mit N₂ bis 20 mm. Es sind Schätzwerte für die Kalkulation vorab, keine Herstellerwerte; bitte "
           "an den eigenen Blechlaser bzw. die Preise des Lieferanten anpassen. Ältere Datendateien bekommen beide "
           "Tabellen beim ersten Start von Version 0.8.2 (Schema 37).")
    i.tabelle(["K-Faktoren (Abwicklung)", "Bedeutung"], [
        ["<b>Kategorie</b>, <b>Blechdicke bis [mm]</b>, <b>Innenradius ÷ Dicke bis</b>",
         "je Biegung gilt die Zeile der Kategorie mit der kleinsten Blechdicke bis ≥ Dicke, darin die kleinste "
         "Grenze Innenradius ÷ Dicke ≥ der Biegung (größer als alle: die größte Zeile)"],
        ["<b>K-Faktor</b>", "Lage der neutralen Faser als Anteil der Blechdicke von innen (0,1 bis 0,5)"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.text("Vorbelegt sind Beispielwerte nach DIN 6935 für alle Kategorien: Innenradius ÷ Dicke bis 0,5 → 0,25; "
           "bis 1 → 0,33; bis 2 → 0,40; bis 3 → 0,44; darüber 0,50. Innenradius = Blechdicke ergibt 0,33 wie "
           "bisher. Passt keine Zeile, gilt der K-Faktor des Blech-Werkstoffs; mit der Einstellung <i>Abwicklung: "
           "K-Faktor aus</i> = <i>je Werkstoff</i> gilt nur dieser ([[einstellungen]]). Bitte an die eigene "
           "Abkantpresse bzw. den Lieferanten anpassen. Ältere Datendateien bekommen die Tabelle beim ersten Start "
           "von Version 0.9.14 (Schema 47).")
    i.abschnitt("Prüfregeln (Fertigung)", marke="pruefregeln")
    i.text("Die <b>Fertigungsprüfung</b> sieht sich jedes Rohr-, Profil- und Blechteil an und meldet, was sich "
           "schlecht fertigen lässt. Der Befund steht im Status der Position (mit Lage am Teil, z. B. <i>bei x = "
           "120 mm, oben</i>), im Schneidweg-Rechner und im Blech-Editor. Jede Regel ist im Unterreiter "
           "<b>Prüfregeln (Fertigung)</b> einzeln an- oder abschaltbar und hat einen Grenzwert und eine Stufe.",
           kurz=True)
    i.bild("stamm_pruefregeln", "Einstellungen, Prüfregeln (Fertigung)", hoehe=60 * mm)
    i.genauer()
    i.tabelle(["Prüfregeln (Fertigung)", "Bedeutung"], [
        ["<b>Regel</b>", "Bohrung zu klein, Steg zu schmal, Kontur zu nah am Rand, Teil zu kurz für die Maschine, "
                         "Gravur über Kante, Kantbarkeit, Kontur in der Biegezone, Gerade zwischen Biegungen zu "
                         "kurz"],
        ["Aktiv", "<i>nein</i> schaltet die Regel ab"],
        ["Grenzwert [× Wand bzw. Dicke]", "Faktor auf die Wandstärke des Profils bzw. die Blechdicke (bei "
                                          "<i>Gerade zwischen Biegungen zu kurz</i> auf den Außen-Ø); leer = "
                                          "Vorgabe"],
        ["Stufe", "HINWEIS, WARNUNG oder FEHLER: so erscheint der Befund im Status; FEHLER sperrt die Position "
                  "wie jeder andere Fehler"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.liste("<b>Bohrung zu klein</b>: Bohrung oder Senkung mit Ø unter 1,0 × Wand (Vorgabe WARNUNG). Unter "
            "0,7 × Wand bleibt zusätzlich die Warnung, dass gebohrt werden muss ([[bohrungen_pruefen]]).",
            "<b>Steg zu schmal</b>: zwei Konturen näher als 1,5 × Wand beieinander, auch über eine Kante des "
            "Profils hinweg (Abwicklung).",
            "<b>Kontur zu nah am Rand</b>: Kontur näher als 1,0 × Wand am Ende des Teils bzw. an der Blechkante. "
            "Schlitze und Ausklinkungen sind zum Ende offen und zählen nicht; Gehrungen rechnen mit dem Ende bei "
            "x = 0 bzw. x = Länge.",
            "<b>Teil zu kurz für die Maschine</b>: kürzer als <i>Kürzestes Teil</i> der Maschine (Vorgabe FEHLER).",
            "<b>Gravur über Kante</b>: eine Gravur aus dem STEP-Import läuft über mehrere Flächen.",
            "<b>Kantbarkeit</b>: die Hinweise der Kantbarkeit ([[blech_kantbarkeit]]) im Status der Blech-Position "
            "(Vorgabe HINWEIS).",
            "<b>Kontur in der Biegezone</b> (Biegerohr): Kontur in einem Bogen oder näher als Grenzwert × Wand daran "
            "(Vorgabe 0 = nur im Bogen, WARNUNG, [[biegerohre]]).",
            "<b>Gerade zwischen Biegungen zu kurz</b> (Biegerohr): Gerade zwischen zwei Biegungen kürzer als "
            "Grenzwert × Außen-Ø (Vorgabe 1,5, Spannlänge der Biegemaschine).",
            "<b>Schenkel zu kurz</b> (Knickrahmen): Schenkel kürzer als Grenzwert × Rohrmaß h in der Rahmenebene "
            "(Vorgabe 2,0, WARNUNG, [[knickrahmen]]).",
            "<b>Kontur im Knickbereich</b> (Knickrahmen): Kontur näher am V-Ausschnitt als Grenzwert × Wand (Vorgabe "
            "2,0, WARNUNG).",
            "<b>Wand zu dick zum Knicken</b> (Knickrahmen): Wandstärke über dem Grenzwert in mm (Vorgabe 4, HINWEIS).",
            "Konturen ohne Lage (ohne x bzw. x/y) prüft das Programm nur auf <i>Bohrung zu klein</i>.")
    i.text("Alle Vorgaben sind Startwerte, bitte an die eigene Fertigung anpassen. Ältere Datendateien bekommen die "
           "Tabelle mit den Vorgaben beim ersten Start von Version 0.9.18 (Schema 48), die beiden Regeln für "
           "Biegerohre und die Zusatzarbeit Biegen beim ersten Start von Version 0.9.39, die drei Regeln für "
           "Knickrahmen und die Zusatzarbeit Knicken beim ersten Start von Version 0.9.49.")
    i.abschnitt("Schweißverfahren, Schweiß-Kennwerte und Faktoren", marke="schweiss_stammdaten")
    i.text("Diese drei Unterreiter sind die Grundlage der Schweißzeit in Schweißbaugruppen. Die Schweißzeit einer "
           "Nahtgruppe kommt nicht aus einem Prozentsatz, sondern aus der Nahtlänge und Kennwerten, die du hier "
           "pflegst. Neue Datendateien bekommen die Tabellen leer; ohne Kennwert rechnet das Programm keine Zeit, "
           "sondern zeigt eine Warnung.", kurz=True)
    i.tabelle(["Tabelle", "Inhalt"], [
        ["<b>Schweißverfahren</b>", "Verfahren (MAG, MIG, WIG, E-Hand, Heften, Roboter …, frei erweiterbar), "
                                    "Stundensatz-ID, <b>Lichtbogenzeitfaktor [%]</b> (Anteil der Lichtbogenzeit an "
                                    "der Schweißarbeitszeit) und Zeit je Heftpunkt [s]"],
        ["<b>Schweiß-Kennwerte</b>", "Lichtbogenzeit in min je m Naht nach Verfahren, Nahtart (Kehl-, Stumpf-, "
                                     "Ecknaht) und Nahtgröße: Kehlnaht nach a-Maß, Stumpf- und Ecknaht nach "
                                     "Blechdicke (Spalte <i>a-Maß bzw. Blechdicke bis [mm]</i>). Es gilt die Zeile "
                                     "mit dem kleinsten <i>bis</i>, das die Nahtgröße abdeckt; <i>Herkunft / "
                                     "Bemerkung</i> sagt, woher der Wert stammt."],
        ["<b>Schweiß-Faktoren</b>", "Zuschläge auf die Lichtbogenzeit für Schweißlage (PA … PG), Zugänglichkeit und "
                                    "Qualitätsanforderung: je Art und <i>Ausprägung</i> ein <i>Faktor auf die "
                                    "Lichtbogenzeit</i>; nicht eingetragen = Faktor 1"],
        ["<b>Schweiß-Vorkalkulation</b>", "Regeln für <b>Vorkalkulation rechnen</b> im Baugruppen-Editor "
                                          "([[vorkalkulation_baugruppe]]): je Art (Rüsten, Positionieren, Heften, "
                                          "Heftabstand, Wenden, Nacharbeit) und Ausprägung ein Wert mit Einheit; "
                                          "Heftabstand und Wenden in Stufen über <i>bis Wanddicke [mm] bzw. Gewicht "
                                          "[kg]</i> (es gilt das kleinste <i>bis</i>, das passt, sonst die Zeile ohne "
                                          "<i>bis</i>)"]], [45, 220])
    i.bild("stamm_schweiss_kennwerte", "Einstellungen, Schweiß-Kennwerte nach Richtwerte laden", hoehe=85 * mm,
           legende=[(1, "Unterreiter <b>Schweißverfahren</b>, <b>Schweiß-Kennwerte</b>, <b>Schweiß-Faktoren</b>."),
                    (2, "<b>Richtwerte laden</b> trägt fehlende Verfahren, Kennwerte und Faktoren als Richtwerte ein; "
                        "vorhandene Zeilen bleiben unverändert (auch eigene Werte)."),
                    (3, "Je Zeile Verfahren, Nahtart, Nahtgröße <i>bis</i>, Lichtbogenzeit je m und <b>Status</b> "
                        "(Richtwert oder geprüft).")])
    i.genauer()
    i.text("Rechnung je Nahtgruppe: Naht [m] = Länge je Naht × Anzahl (beidseitig doppelt); Lichtbogenzeit = Naht × "
           "Kennwert × Faktoren; Schweißzeit = Lichtbogenzeit ÷ Lichtbogenzeitfaktor + Heftpunkte × Zeit je "
           "Heftpunkt. Lichtbogenzeit und Arbeitszeit sind nicht dasselbe: der Lichtbogenzeitfaktor deckt die "
           "Nebenzeiten am Platz ab (Brenner ansetzen, Schlacke, Drahtwechsel). Rüsten, Vorrichten, Wenden und "
           "Schleifen sind eigene Arbeitsgänge der Baugruppe. Ist eine Zeit von Hand eingetragen, gilt sie. In der "
           "Kalkulation stehen die Kosten als Kostenarten <b>Schweißbaugruppen: Schweißen und Arbeitsgänge</b> "
           "(mit Zuschlag Fertigung) und <b>Schweißbaugruppen: Fremdleistungen</b> (mit Zuschlag Fremdleistung).")
    i.text("<b>Schweißzusatz und Schutzgas</b> (wahlweise): Trägt man beim Schweißverfahren <i>Dichte Schweißzusatz "
           "[kg/dm³]</i>, <i>Preis Schweißzusatz [€/kg]</i>, <i>Schutzgas [l/min]</i> und <i>Preis Schutzgas "
           "[€/l]</i> ein, rechnet jede Nahtgruppe dazu "
           "Draht = Nahtquerschnitt × Nahtlänge × Dichte und Gas = Lichtbogenzeit × l/min, jeweils × Preis. Leer "
           "bleibt es wie bisher (Zusatz und Gas stecken im Stundensatz). Fehlt nur ein Teil der Werte, zählt dieser "
           "Teil 0 € und der Editor nennt, was fehlt. Im Kostenbalken steht der Betrag als <i>Schweißzusatz und "
           "Gas</i>.")
    i.text("Jede Zeile hat einen <b>Status</b>: <i>Richtwert</i> oder <i>geprüft</i>. Richtwerte sind aus dem "
           "Nahtquerschnitt hergeleitet (Kehlnaht a² × 1,1; V-Naht 60° mit 1,5 mm Spalt; × Dichte ÷ "
           "Abschmelzleistung des Verfahrens, z. B. MAG 3,5 kg/h) und keine Erfahrungswerte der eigenen Fertigung. "
           "Solange eine Baugruppe mit Richtwerten rechnet, zeigt ihr Status einen HINWEIS. Stelle die Werte nach "
           "den ersten Aufträgen auf <i>geprüft</i>. Verschickte Angebote ändern sich nicht: jede Nahtgruppe merkt "
           "sich die Kennwerte, mit denen sie gerechnet wurde.")
    i.text("<b>Kennwerte aus Nachkalkulation …</b> (Unterreiter Schweiß-Kennwerte) öffnet das Fenster "
           "<i>Kennwerte aus der Nachkalkulation</i>. Es wertet alle nachkalkulierten "
           "Schweißbaugruppen aus ([[nachkalkulation]]): je Verfahren und Nahtart der Faktor Ist ÷ Soll der "
           "Schweißzeit als Median, Ausreißer (mehr als 3 × die mittlere Abweichung) zählen nicht und stehen in der "
           "Spalte <i>Ausreißer</i> mit Angebotsnummer. Es zählen nur Baugruppen, deren Nahtgruppen alle dasselbe "
           "Verfahren und dieselbe Nahtart haben und keine Zeit von Hand. Unter 5 Fällen (einstellbar) steht "
           "<i>zu wenig Daten</i>. Gelb = mindestens 10 % Abweichung.")
    i.text("Geändert wird erst mit <b>Gewählten Vorschlag freigeben</b> und einer Begründung: dann werden alle "
           "Kennwerte dieses Verfahrens und dieser Nahtart mit dem Faktor multipliziert. Jede Freigabe steht mit "
           "Datum, Begründung und Programmversion unter <i>Bisherige Freigaben</i>; <b>Gewählte Freigabe "
           "zurücknehmen</b> stellt die alten Werte wieder her (Werte, die du seitdem von Hand geändert hast, "
           "bleiben). Verschickte Angebote ändern sich nie.")
    i.text("Der Unterreiter <b>Schweiß-Vorkalkulation</b> hält die Regeln für <b>Vorkalkulation rechnen</b> "
           "([[vorkalkulation_baugruppe]]). Neue Datendateien bekommen ihn leer; <b>Richtwerte laden</b> trägt die "
           "fehlenden Zeilen mit Status <i>Richtwert</i> ein. Ändere die Werte nach den ersten Aufträgen und stelle "
           "sie auf <i>geprüft</i>.")
    i.bild("stamm_schweiss_regeln", "Einstellungen, Schweiß-Vorkalkulation nach Richtwerte laden", hoehe=85 * mm,
           kurz=False)
    i.abschnitt("Zusatzarbeiten", marke="zusatzarbeiten_verwalten")
    i.text("Hier stehen alle Arbeiten, die zusätzlich zum Laserschneiden je Bauteil gewählt werden können, z. B. "
           "Feuerverzinken, galvanisch Verzinken, Pulverbeschichten, Entgraten oder eine Gravur, die nicht im "
           "STEP-Modell ist. Der Unterreiter zeigt eine Übersicht; angelegt und geändert wird in einem Formular.",
           kurz=True)
    i.bild("stamm_zusatzarbeiten", "Einstellungen, Zusatzarbeiten: Übersicht mit den Beispielwerten", hoehe=110 * mm,
           legende=[(1, "Unterreiter <b>Zusatzarbeiten</b>"),
                    (2, "<b>+ Zusatzarbeit hinzufügen</b> öffnet ein leeres Formular"),
                    (3, "<b>Suchen</b> in Name, Kategorie, Beschreibung und Text im Angebot"),
                    (4, "Filter <b>Kategorie</b> und <b>Status</b> (Alle, Aktive, Inaktive), daneben <b>Sortieren "
                        "nach</b> Name, Preis, Zeitaufwand oder Kategorie"),
                    (5, "<b>Bearbeiten</b>, <b>Duplizieren</b>, <b>Deaktivieren</b> bzw. <b>Aktivieren</b> und "
                        "<b>Löschen</b> für den markierten Eintrag (auch mit der rechten Maustaste)"),
                    (6, "Detailbereich: die vollständige Berechnung des markierten Eintrags")])
    i.genauer()
    i.liste("Die Übersicht zeigt immer Name, Kategorie, Abrechnung, Preis je Einheit, Verkaufspreis (Vorgaben) und "
            "Status. Spalten wie Zeitaufwand, Stundensatz, Arbeitskosten, Material, Materialzuschlag, weitere "
            "Zuschläge oder Mindestbetrag erscheinen nur, wenn ein Eintrag dort einen Wert hat. Bei schmalem Fenster "
            "fallen weitere Detailspalten weg; sie stehen im Detailbereich.",
            "Doppelklick auf eine Zeile = <b>Bearbeiten</b>. Inaktive Einträge stehen grau.",
            "<b>Verkaufspreis (Vorgaben)</b> = Preis je Einheit mit Zuschlag Fertigung bzw. Fremdleistung und Gewinn aus "
            "den Vorgaben. Im Angebot gelten dessen Werte bzw. die der Staffel.")
    i.abschnitt("Zusatzarbeit anlegen und bearbeiten")
    i.liste("<b>+ Zusatzarbeit hinzufügen</b> (oder Doppelklick auf eine Zeile).",
            "Name, Abrechnung und Preis bzw. Zeit × Stundensatz eintragen; rechts unten rechnet der Preis mit.",
            "<b>Speichern</b>.", nummeriert=True, kurz=True)
    i.bild("zusatz_formular", "Formular einer neuen Zusatzarbeit (schmales Fenster): 5 min × 60 €/h + 2 € Material "
                              "+ 10 % = 7,20 €",
           hoehe=120 * mm, legende=[
               (1, "<b>Allgemeine Angaben</b>: Name, Kategorie, Beschreibung, Abrechnung und das Häkchen <b>aktiv "
                   "(im Angebot auswählbar)</b>"),
               (2, "<b>Arbeitszeit und Kosten</b>: Festpreis je Einheit, Zeitaufwand mit Zeiteinheit (s, min, h), "
                   "Stundensatz aus den Stammdaten oder eigener Stundensatz; die Arbeitskosten rechnet das Programm"),
               (3, "<b>Material und Zuschläge</b>: Materialkosten je Einheit und Materialzuschlag in % oder €"),
               (4, "<b>Weitere Optionen</b> (zugeklappt): weiterer Zuschlag, Mindestbetrag, Fremdleistung, Text im "
                   "Angebot"),
               (5, "<b>Ergebnis</b>: Selbstkosten, Zuschläge und Verkaufspreis je Einheit, darunter die "
                   "Berechnungsgrundlage im Angebot"),
               (6, "<b>Speichern</b> / <b>Abbrechen</b>")])
    i.genauer("Felder und Rechenweg")
    i.text("Anlegen, Bearbeiten und Duplizieren nutzen dasselbe Formular. Es steht rechts neben der Tabelle, bei "
           "schmalem Fenster (unter 1280 Pixel) in einem eigenen Fenster. Der Preis rechnet sich beim Tippen neu. "
           "Gespeichert wird erst mit <b>Speichern</b>; <b>Abbrechen</b> verwirft alle Änderungen. Wer mit "
           "ungespeicherten Änderungen einen anderen Eintrag öffnet, wird gefragt, ob sie verworfen werden sollen.")
    i.tabelle(["Feld", "Bedeutung"], [
        ["Zusatzarbeit (Name)", "Pflicht, eindeutig. Umbenennen ändert den Namen auch in den Positionen der Angebote."],
        ["Kategorie", "frei wählbar, z. B. Oberfläche, Nachbearbeitung, Laser; Filter und Gruppen in der Auswahl"],
        ["Beschreibung", "kurzer Text für die Übersicht"],
        ["Abrechnung", "wonach gerechnet wird, siehe Tabelle unten"],
        ["Aktiv", "nur aktive Zusatzarbeiten lassen sich im Angebot neu wählen"],
        ["Festpreis [€] bzw. Zeit [s] je Einheit", "fester Preis je Einheit (z. B. Preis der Verzinkerei); bei "
                                                    "s/Stück die Maschinenzeit je Stück"],
        ["Zeitaufwand je Einheit, Zeiteinheit", "Arbeitszeit je Einheit in s, min oder h; bei €/h die "
                                                "<i>Vorgabezeit je Teil</i> (leer = im Angebot je Position eintragen)"],
        ["Stundensatz-ID, Stundensatz eigener", "Stundensatz aus Stundensätze und Zeitvorgaben oder ein eigener Wert "
                                                "in €/h"],
        ["Materialkosten je Einheit", "Material, das die Zusatzarbeit selbst braucht (z. B. Schutzkappen)"],
        ["Materialzuschlag, Materialzuschlag in", "Zuschlag nur auf dieses Material, in % oder als Betrag in €"],
        ["Weiterer Zuschlag, Weiterer Zuschlag auf", "Zuschlag in % auf Arbeit, Material oder Arbeit und Material"],
        ["Mindestbetrag je Angebot", "liegt die Summe dieser Zusatzarbeit im ganzen Angebot darunter, wird sie auf den "
                                     "Mindestbetrag angehoben und anteilig auf die Teile verteilt (typisch für "
                                     "Verzinkereien). Bei Staffelpreisen gilt er je Mengenstufe."],
        ["Fremdleistung", "ja: Aufschlag mit dem <i>Zuschlag Fremdleistung</i> (Einstellungen), sonst mit dem "
                          "Zuschlag Fertigung wie eigene Arbeit"],
        ["Text im Angebot", "so erscheint die Arbeit im Angebotstext der Position, je Arbeit eine eigene Zeile, "
                            "z. B. <i>inkl. feuerverzinkt</i> ([[ausgabe]])"]], [65, 200])
    i.text("<b>Rechenweg</b> (für jede Einheit): Preis je Einheit = Festpreis + Zeitaufwand × Stundensatz + "
           "Material mit Materialzuschlag + weiterer Zuschlag. Beispiel: 5 min × 60 €/h = 5,00 €, Material 2,00 € + "
           "10 % = 2,20 €, Selbstkosten 7,20 € je Stück. Im Angebot kommt danach einmal der Zuschlag Fertigung "
           "(bzw. Fremdleistung) und der Gewinn des Angebots bzw. der Staffel dazu, Skonto und Rundung wie beim übrigen "
           "Angebot. Der Zuschlag Material (Einstellungen) gilt nur für das Stangenmaterial, nie für Zusatzarbeiten. "
           "Einträge, die nur einen Festpreis haben, rechnen genau wie bisher.")
    i.tabelle(["Abrechnung", "Menge je Teil (automatisch)", "Gerechnet wird"], [
        ["€/Stück", "1", "Menge × Preis, z. B. Entgraten"],
        ["€/Angebot", "1", "einmal je Angebot (pauschal), verteilt auf die Teile der Positionen mit dieser Arbeit, "
                           "z. B. Prüfprotokoll"],
        ["€/kg", "Teilegewicht aus Profil, Länge und Dichte", "Menge × Preis, z. B. Feuerverzinken nach Gewicht"],
        ["€/m²", "Außenfläche = Umfang × Länge (ohne Innenseite und Stirnflächen)",
         "Menge × Preis, z. B. Pulverbeschichten"],
        ["€/m", "Teilelänge in m", "Menge × Preis"],
        ["s/Stück", "1 (Anzahl, z. B. 2 Gravuren)",
         "Menge × Zeit in Sekunden kommt zur Schneidzeit dazu und wird mit dem Stundensatz der Maschine gerechnet "
         "(z. B. <i>Gravur extra</i>)."],
        ["€/h", "keine: Sekunden je Teil im Angebot (sonst die Vorgabezeit)",
         "Sekunden ÷ 3600 × Stundensatz, z. B. <i>Schweißen</i> mit 75 €/h; Festpreis und Material zählen nicht, "
         "nicht zur Laserzeit"]], [30, 95, 140])
    i.abschnitt("Duplizieren, Deaktivieren und Löschen")
    i.genauer()
    i.liste("<b>Duplizieren</b> öffnet das Formular mit allen Werten des markierten Eintrags und dem Namen „… (Kopie)“. "
            "Angelegt wird die Kopie erst mit <b>Speichern</b>.",
            "<b>Deaktivieren</b>: die Zusatzarbeit ist im Angebot nicht mehr wählbar, Angebote, in denen sie schon "
            "steht, rechnen unverändert weiter. <b>Aktivieren</b> macht das rückgängig.",
            "<b>Löschen</b> fragt immer nach. Wird die Zusatzarbeit in Angeboten verwendet, nennt die Abfrage diese "
            "Angebote und empfiehlt <b>Deaktivieren</b>; <b>Trotzdem löschen</b> entfernt sie aus den Stammdaten.",
            "<b>Preisstand</b>: Beim Hinzufügen zu einer Position speichert das Programm den Preis je Einheit, die "
            "Abrechnung, den Mindestbetrag und die Fremdleistung in der Position. Spätere Änderungen in den "
            "Stammdaten (oder Löschen) ändern bestehende Angebote deshalb nicht. Positionen aus älteren Versionen "
            "ohne Preisstand rechnen wie bisher mit den aktuellen Stammdaten.")


def kapitel_zukauf(i):
    i.kapitel("Zukaufartikel verwalten", marke="zukauf")
    i.text("Zukaufartikel sind Teile, die eingekauft und mit dem Bauteil geliefert oder verbaut werden: Blechteile und "
           "Laserzuschnitte, Schrauben, Muttern und Unterlegscheiben, Normteile, Kaufteile und Handelsware, Dreh- und "
           "Frästeile von Lieferanten, fremdgefertigte Bauteile, Profile und Rohre. Jeder Artikel hat eigene "
           "Einkaufspreise je Lieferant, eine Mengeneinheit und eine eigene Aufschlagsregel. Arbeiten am Teil "
           "(Verzinken, Entgraten) bleiben Zusatzarbeiten ([[stammdaten]]).",
           "Der Reiter <i>Zukaufartikel</i> ist ohne Passwort zugänglich und hat vier Unterreiter: <b>Artikel</b>, "
           "<b>Kategorien</b>, <b>Lieferanten</b> und <b>Preisänderungen</b>.")
    i.text("Eingekaufte Teile (Bleche, Schrauben, Normteile …) mit Einkaufspreis je Lieferant und Aufschlag. Reiter "
           "<i>Zukaufartikel</i>, ohne Passwort.", kurz=True)
    i.abschnitt("Übersicht der Artikel")
    i.bild("zukauf_uebersicht", "Zukaufartikel, Unterreiter Artikel (Beispielwerte)", hoehe=105 * mm, legende=[
        (1, "Reiter <b>Zukaufartikel</b> mit den Unterreitern Artikel, Kategorien und Lieferanten"),
        (2, "<b>+ Neuer Artikel</b> öffnet das leere Formular"),
        (3, "Suche nach Artikelnummer, Bezeichnung, Lieferantenartikelnummer oder EAN"),
        (4, "Filter Kategorie, Lieferant und Status (aktive, <i>EK fehlt</i>, archivierte, alle), Sortieren nach Kategorie, "
            "Lieferant, Artikelnummer, Bezeichnung oder EK je Einheit"),
        (5, "<b>Bearbeiten</b> (auch Doppelklick), <b>Duplizieren</b>, <b>Archivieren</b> bzw. <b>Wieder "
            "aktivieren</b>, <b>EK eintragen …</b> ([[blechartikel]]) und <b>In Angebot übernehmen …</b> ([[zukauf_angebot]]); dieselben Befehle mit der rechten "
            "Maustaste. Rechts <b>CSV exportieren</b> und <b>CSV importieren …</b> ([[zukauf_csv]])"),
        (6, "Details des markierten Artikels: alle Lieferanten mit Staffelpreisen und die Rechnung je Einheit")])
    i.text("Rot = <b>kein Preis</b> oder <b>kein Aufschlag</b>, gelb = Preis abgelaufen. Doppelklick öffnet den "
           "Artikel.", kurz=True)
    i.genauer()
    i.text("Die Spalten zeigen je Artikel Artikelnr., Bezeichnung, Kategorie, bevorzugten Lieferant, Einheit, "
           "<i>EK je Einheit</i> (Einkaufspreis netto bei der kleinsten Bestellmenge), <i>Bezugskosten</i> (je "
           "Bestellung und je Einheit; die Spalte erscheint nur, wenn ein Artikel welche hat), <i>Aufschlag</i> mit "
           "seiner Herkunft (Kat. = Kategorie, indiv. = individuell, Std. = Standard der Einstellungen), <i>VK je "
           "Einheit</i> und Status. <b>kein Preis</b> und <b>kein Aufschlag</b> stehen rot, ein abgelaufener "
           "Einkaufspreis gelb (<i>Preis abgelaufen</i>).")
    i.liste("<b>Duplizieren</b> legt eine Kopie mit allen Lieferanten und Preisen an; die Artikelnummer bekommt "
            "<i>-K</i> (Z-1001-K, dann Z-1001-K2), die Bezeichnung <i>(Kopie)</i>. Angelegt wird sie erst mit "
            "<b>Speichern</b>.",
            "<b>Archivieren</b> nimmt den Artikel aus der Auswahl im Angebot. Angebote, die ihn schon enthalten, "
            "rechnen mit ihrem gespeicherten Preisstand weiter. Gelöscht werden Artikel nicht.")
    i.abschnitt("Artikel anlegen und bearbeiten")
    i.liste("<b>+ Neuer Artikel</b>.", "A: Bezeichnung, Kategorie und Einheit.",
            "B: Lieferant und Einkaufspreis (ab Menge).", "Preisvorschau prüfen, <b>Speichern</b>.",
            nummeriert=True, kurz=True)
    i.bild("zukauf_formular", "Formular mit Preisvorschau: Schrauben, 12,00 € je 100 Stück, 5,00 € Eingangsfracht, "
                              "25 % Aufschlag (Beispielwerte)", hoehe=200 * mm, legende=[
        (1, "A Stammdaten"), (2, "B Einkaufspreis: Lieferanten des Artikels, Preiseinheit und Staffelpreise"),
        (3, "C Aufschlag: Herkunft und Methode"), (4, "<b>Weitere Details</b> aufklappen"),
        (5, "Preisvorschau für eine Verbrauchsmenge"), (6, "<b>Speichern</b>")])
    i.genauer("Felder")
    i.text("Neu, Bearbeiten und Duplizieren öffnen dasselbe Formular, bei breitem Fenster rechts neben der Tabelle, "
           "sonst als eigenes Fenster. Gespeichert wird erst mit <b>Speichern</b>; <b>Abbrechen</b> verwirft alle "
           "Eingaben. Ungültige Eingaben werden rot umrandet und unten im Formular genannt. Die Abschnitte A, B, C "
           "und Preisvorschau klappen mit einem Klick auf ihre Überschrift zu und auf; zugeklappt steht daneben eine "
           "Kurzfassung (z. B. bei C <i>Standard der Kategorie</i>). C Aufschlag ist anfangs zu, weil meist die "
           "Kategorie den Aufschlag liefert; das Programm merkt sich, welche Abschnitte offen sind.")
    i.tabelle(["Bereich", "Feld", "Bedeutung"], [
        ["A Stammdaten", "Artikelnummer", "eindeutig, darf leer bleiben"],
        ["", "Artikelbezeichnung", "Pflichtfeld"],
        ["", "Kategorie", "aus den Kategorien ([[zukauf_kategorien]]); bestimmt den vorgeschlagenen Aufschlag"],
        ["", "Mengeneinheit", "Stück, Meter, Kilogramm, Satz oder frei eingeben"],
        ["", "Artikeltyp", "<i>normaler Zukaufartikel</i> oder <i>Blech</i>; bei Blech zusätzlich Länge × Breite × "
                           "Dicke in mm und Werkstoff ([[blechartikel]])"],
        ["", "archiviert", "im Angebot nicht mehr wählbar"],
        ["B Einkaufspreis", "Lieferanten", "Liste der Lieferanten des Artikels; ★ = bevorzugt. <b>+ Lieferant</b> "
                                           "fügt einen hinzu, <b>Entfernen</b> löscht den markierten, <b>Als "
                                           "bevorzugt</b> macht ihn zum Standard für neue Angebote"],
        ["", "Lieferant", "aus der Liste wählen oder neu eintippen (wird beim Speichern unter Lieferanten angelegt)"],
        ["", "Preis gilt für", "Preiseinheit: 100 bei einem Preis je 100 Stück. 12,00 € je 100 Stück ergeben "
                               "0,12 € je Stück"],
        ["", "Einkaufspreise", "Staffel: <i>ab Menge</i> und <i>Einkaufspreis netto</i> je Preiseinheit, z. B. ab 1: "
                               "1,20 €, ab 100: 0,95 €, ab 500: 0,80 €. Es gilt die Zeile mit der größten Menge, die "
                               "die Bestellmenge erreicht. Ohne Zeile: <b>kein Preis</b>"],
        ["", "Verpackung je Bestellung, Eingangsfracht, Weitere Bezugskosten",
         "Bezugskosten des Lieferanten, je Bestellung (einmal je Angebot bzw. Staffel) oder je Einheit"],
        ["C Aufschlag", "Aufschlag aus", "<i>Standard der Kategorie</i> (Vorgabe), <i>individuell für diesen "
                                         "Artikel</i> oder <i>Standard der Anwendung (Einstellungen)</i>"],
        ["", "Methode, Aufschlag", "nur bei individuell: % auf Einstand, € je Einheit, € je Bestellung, Mengenstaffel "
                                   "% (Staffel nach Verbrauch) oder Zielmarge %"],
        ["", "zusätzlich zum Kategorieaufschlag", "beide Aufschläge addieren statt ersetzen"],
        ["Weitere Details", "Beschreibung, EAN / Referenzcode, Lieferantenartikelnummer, Bemerkung", "zur Information"],
        ["", "Mindestbestellmenge, Verpackungseinheit", "die Bestellmenge ist mindestens die Mindestbestellmenge und "
                                                        "wird auf ganze Verpackungseinheiten aufgerundet"],
        ["", "Lieferzeit", "in Tagen, zur Information"],
        ["", "Mindermengenzuschlag", "€ je Bestellung, wenn die Bestellmenge unter der genannten Menge liegt"],
        ["", "Mengenrabatt", "% auf den Einkaufspreis"],
        ["", "Preis gültig von … bis", "außerhalb des Zeitraums warnt das Programm (Preis abgelaufen bzw. noch nicht "
                                       "gültig)"],
        ["", "Mehrmenge geht ins Lager", "ohne Haken trägt der Auftrag die ganze Bestellmenge; mit Haken nur den "
                                         "Verbrauch, die Bezugskosten anteilig"],
        ["", "im Angebotstext der Position nennen", "der Artikel erscheint im Text der Position im Angebot"]],
              [28, 55, 92])
    i.abschnitt("Preisvorschau und Rechenweg")
    i.text("Verkaufspreis = Einkauf + Bezugskosten (Einstand) + Aufschlag.", kurz=True)
    i.genauer()
    i.text("Die Vorschau rechnet bei jeder Eingabe mit derselben Rechnung wie das Angebot, für die eingetragene "
           "Verbrauchsmenge (Vorgabe: kleinste Bestellmenge). Sie zeigt je Einheit und für die ganze Menge:")
    i.tabelle(["Position", "Rechnung (Beispielwerte)"], [
        ["Einkaufspreis netto", "Staffelpreis für die Bestellmenge ÷ Preiseinheit × (1 − Mengenrabatt); 12,00 € ÷ "
                                "100 = 0,12 € je Stück"],
        ["Bezugskostenanteil", "Verpackung + Eingangsfracht + weitere Bezugskosten + ggf. Mindermengenzuschlag, "
                               "einmal je Bestellung; 5,00 € bei 100 Stück = 0,05 € je Stück"],
        ["Einstandspreis", "Einkauf + Bezugskosten; 0,17 € je Stück"],
        ["Aufschlag", "nach der Regel, z. B. 25 % auf Einstand = 0,0425 €"],
        ["Verkaufspreis netto", "Einstand + Aufschlag = 0,2125 € je Stück"],
        ["MwSt., Bruttopreis", "mit dem MwSt.-Satz der Einstellungen, nur zur Information"],
        ["Deckungsbeitrag", "Verkaufspreis − Einstand"],
        ["Aufschlag auf Einstand / Marge vom Verkaufspreis", "25 % / 20 %"]], [55, 120])
    i.hinweis("Ein Aufschlag ist nicht dasselbe wie eine Marge. Bei 10,00 € Einstand ergeben 20 % Aufschlag "
              "12,00 €, 20 % Zielmarge dagegen 12,50 € (10,00 € ÷ 0,80). Die Vorschau nennt die verwendete Methode "
              "und zeigt beide Prozentwerte.", "Aufschlag und Marge")
    i.text("Liegt die Bestellmenge über dem Verbrauch (Mindestbestellmenge, Verpackungseinheit), nennt die Vorschau "
           "beide Mengen. Fehlt der Einkaufspreis, steht dort rot <i>Kein Einkaufspreis</i>; gerechnet wird dann "
           "nicht mit 0 €.")
    i.abschnitt("Kategorien und Aufschlagsregeln", marke="zukauf_kategorien")
    i.bild("zukauf_kategorien", "Zukaufartikel, Unterreiter Kategorien (Beispiel: 30 % für Schrauben und Muttern)",
           hoehe=80 * mm, legende=[(1, "Unterreiter <b>Kategorien</b>")])
    i.text("Je Kategorie ein Standardaufschlag. Vorrang: Aufschlag der Position vor dem des Artikels vor dem der "
           "Kategorie vor dem Standard der Einstellungen.", kurz=True)
    i.genauer()
    i.text("Unter <b>Kategorien</b> steht je Kategorie ein Standardaufschlag: Kategorie, Standard-Aufschlagsmethode "
           "(% auf Einstand, € je Einheit, € je Bestellung oder Zielmarge %), Standardaufschlag [% bzw. €], Aktiv "
           "und Beschreibung. Mengenstaffeln gibt es nur am Artikel. Die Kategorien sind mit Namen vorbelegt "
           "(Blechteile, Schrauben und Muttern, Normteile, Kaufteile, Fremdfertigung, Profile und Rohre, Sonstige "
           "Zukaufartikel), aber <b>ohne Aufschläge</b>: die Werte trägt der Betrieb selbst ein. Bedient wird die "
           "Tabelle wie die Stammdaten ([[stammdaten]]).",
           "Welcher Aufschlag gilt, entscheidet diese Reihenfolge; die höhere Stufe ersetzt die niedrigere:")
    i.liste("Positionsaufschlag im Angebot (nur für diese Position)",
            "individueller Artikelaufschlag",
            "Aufschlag der Kategorie",
            "Standardaufschlag Zukaufteile der Einstellungen ([[vorgaben]]); leer = keiner, das Programm zeigt dann "
            "<i>kein Aufschlag hinterlegt</i>", nummeriert=True)
    i.text("Nur wenn am Artikel <i>zusätzlich zum Kategorieaufschlag</i> angehakt ist, werden Kategorie und "
           "individueller Aufschlag addiert; die Vorschau zeigt dann beide. Wird der Aufschlag einer Kategorie "
           "geändert, ändert das Artikel mit individuellem Aufschlag nicht. Beim Umbenennen einer Kategorie "
           "ändert sich der Name in allen Artikeln mit.")
    i.abschnitt("Lieferanten")
    i.genauer()
    i.text("Unter <b>Lieferanten</b> stehen Lieferant, Lieferantennummer, Ansprechpartner, Telefon, E-Mail, "
           "Lieferzeit und Bemerkung. Lieferanten, die im Artikelformular neu eingetippt werden, legt das Programm "
           "hier mit ihrem Namen an. Beim Umbenennen ändert sich der Name in allen Artikeln mit. Preise, "
           "Mindestmengen und Lieferzeiten je Artikel stehen beim Artikel.")
    i.abschnitt("Preisänderungen")
    i.text("Jede Preisänderung steht im Protokoll. Angebote mit altem Preis stehen darunter; <b>Im Angebot "
           "aktualisieren …</b> setzt den neuen Preis.", kurz=True)
    i.bild("zukauf_preise", "Unterreiter Preisänderungen: Schrauben von 12,00 auf 12,80 € je 100 Stück "
                            "(Beispielwerte)", hoehe=100 * mm, legende=[
        (1, "Unterreiter <b>Preisänderungen</b>"), (2, "Protokoll mit altem und neuem Wert"),
        (3, "Angebote, die den markierten Artikel noch mit einem älteren Preisstand enthalten: Positionen, "
            "Preisstand, Verbrauch, VK alt und neu (netto für den ganzen Verbrauch im Angebot) und Differenz"),
        (4, "<b>Angebot öffnen</b> (auch Doppelklick)"),
        (5, "<b>Im Angebot aktualisieren …</b>: zeigt alt und neu und setzt nach Bestätigung den aktuellen "
            "Preisstand in allen Positionen dieses Angebots")])
    i.genauer()
    i.text("Jede Änderung an Einkaufspreisen, Bezugskosten, Mindestmengen, Gültigkeit oder Aufschlag eines Artikels "
           "schreibt das Programm beim Speichern ins Protokoll: Datum, Artikel, Lieferant, Was, Alt, Neu und "
           "Bemerkung (z. B. <i>CSV-Import</i>). Der Unterreiter <b>Preisänderungen</b> zeigt das Protokoll, neueste "
           "zuerst, mit Suche und Filter nach Artikel.")
    i.text("Gespeicherte Angebote ändern sich nie von selbst. Aktualisiert wird nur ausdrücklich: hier je Angebot "
           "oder im Dialog Zukaufteile einer Position mit <b>Aus Stammdaten aktualisieren …</b>.")
    i.abschnitt("CSV-Import und -Export", marke="zukauf_csv")
    i.liste("<b>CSV exportieren</b>: alle Artikel als Datei für Excel.",
            "<b>CSV importieren …</b>: Vorschau prüfen (grün neu, gelb geändert, rot Fehler), dann <b>Importieren</b>.",
            nummeriert=True, kurz=True)
    i.bild("zukauf_csv", "Vorschau des CSV-Imports (Beispielwerte)", hoehe=55 * mm, legende=[
        (1, "Zusammenfassung: neu, ändern, unverändert, mit Fehler"),
        (2, "je Zeile der Datei die Aktion mit den Änderungen bzw. Fehlern; neu grün, ändern gelb, Fehler rot"),
        (3, "<b>Importieren</b>")])
    i.genauer()
    i.text("<b>CSV exportieren</b> im Unterreiter Artikel speichert alle Artikel als CSV-Datei (Semikolon, mit "
           "Excel zu öffnen): eine Zeile je Artikel und Lieferant, Kopfzeile mit den Feldnamen wie im Formular. "
           "Einkaufspreise stehen als Staffel <i>ab 1: 12,00 | ab 500: 9,00</i> (Preis je Preiseinheit); ein "
           "einzelner Preis genügt (<i>12,00</i> = ab 1).",
           "<b>CSV importieren …</b> liest eine solche Datei und zeigt zuerst eine Vorschau. Übernommen wird erst "
           "mit <b>Importieren</b>:")
    i.liste("Artikel mit vorhandener Artikelnummer werden geändert: Angaben aus der Datei ersetzen die alten, der "
            "Einkauf beim genannten Lieferanten wird ersetzt, andere Lieferanten bleiben. Mehrere Zeilen mit "
            "derselben Artikelnummer und verschiedenen Lieferanten ergeben einen Artikel mit mehreren Lieferanten.",
            "Fehler, die das Programm erkennt: fehlende Artikelnummer oder Bezeichnung, unlesbare oder negative "
            "Preise, nicht aufsteigende Staffeln, doppelte Zeilen (gleiche Artikelnummer und gleicher Lieferant), "
            "unbekannte Werte bei Status, Aufschlag aus und Methode, Einkaufsdaten ohne Lieferant. Zeilen mit Fehler "
            "werden nie übernommen.",
            "Unbekannte Kategorien legt der Import an (ohne Aufschlag). Preisänderungen kommen ins Protokoll; "
            "gespeicherte Angebote behalten ihren Preisstand.")
    i.text("Die Spalten der CSV-Datei, in dieser Reihenfolge (Kopfzeile mit diesen Namen, Groß-/Kleinschreibung egal). "
           "Pflicht sind nur <i>Artikelnummer</i> und <i>Artikelbezeichnung</i>, die übrigen Spalten dürfen fehlen:")
    i.tabelle(["Spalten", "Inhalt"], [
        ["Artikelnummer, Artikelbezeichnung, Kategorie, Mengeneinheit, Status, Beschreibung, EAN / Referenzcode",
         "Stammdaten des Artikels wie im Formular (Bereich A)"],
        ["Aufschlag aus, Aufschlagsmethode, Aufschlag [% bzw. €]",
         "Aufschlagsregel ([[zukauf_kategorien]]): Kategorie, individuell oder Standard; Methode und Wert"],
        ["Mehrmenge geht ins Lager, Im Angebotstext nennen, Bemerkung", "ja/nein bzw. freier Text"],
        ["Lieferant, Lieferantenartikelnummer, Preiseinheit [Menge], Einkaufspreise (ab Menge: Preis je Preiseinheit)",
         "Einkauf bei diesem Lieferanten; die Preise als Staffel <i>ab 1: 12,00 | ab 500: 9,00</i>"],
        ["Mindestbestellmenge, Verpackungseinheit, Lieferzeit [Tage]", "Bestellregeln des Lieferanten"],
        ["Verpackung je Bestellung [€], Mindermengenzuschlag [€], Mindermengenzuschlag unter [Menge], "
         "Eingangsfracht je Bestellung [€], Eingangsfracht je Einheit [€], Weitere Bezugskosten je Bestellung [€]",
         "Bezugskosten; der Mindermengenzuschlag gilt, wenn die Bestellmenge unter der genannten Menge liegt"],
        ["Mengenrabatt [%], Preis gültig von, Preis gültig bis", "Rabatt auf den Staffelpreis und Gültigkeit"]],
        [150, 115])
    i.text("Im Formular und in der Artikeltabelle heißen zwei Angaben etwas anders: die Mengenstaffel der Methode "
           "<i>Mengenstaffel %</i> ist die <b>Aufschlagsstaffel</b>, und <i>zusätzlich zum Kategorieaufschlag</i> "
           "steht in der Tabelle als <b>Kategorie + individuell kombinieren</b>. Im Protokoll der Preisänderungen "
           "verweist die <b>Artikel-ID</b> auf den Artikel; <b>Einkauf je Lieferant</b> ist die Tabelle mit den "
           "Einkaufsdaten je Lieferant.")
    i.abschnitt("Blechartikel und fehlender Einkaufspreis", marke="blechartikel")
    i.text("Bleche sind Zukaufartikel vom Typ <b>Blech</b>. Fehlt der Einkaufspreis, steht rot <i>EK fehlt</i>; "
           "<b>EK eintragen …</b> trägt ihn nach.", kurz=True)
    i.genauer()
    i.text("Bleche schneidet der Rohrlaser nicht; sie werden als Zukaufartikel mit dem Artikeltyp <b>Blech</b> "
           "geführt. Ein Blechartikel hat zusätzlich Länge, Breite und Dicke in mm und einen Werkstoff. Der "
           "STEP-Import kann solche Artikel selbst anlegen ([[step]]); er trägt dann <i>Angelegt aus STEP-Import</i>, "
           "den Namen der STEP-Datei und eine Geometrie-Kennung (Kontur, Bohrungen, Ausschnitte) ein. Die "
           "Bezeichnung entsteht aus den Maßen, z. B. <i>Blech S235 500 × 300 × 5 mm</i>.")
    i.liste("<b>Werkstoff</b>: steht er nicht fest, bleibt das Feld leer und die Bezeichnung endet auf <i>(Werkstoff "
            "offen)</i>. Das Programm nimmt nie einen Werkstoff an (auch nicht S235); er kann im Formular aus den "
            "Werkstoffen der Stammdaten gewählt oder eingetippt werden.",
            "<b>EK fehlt</b>: ein Artikel ohne Einkaufspreis über 0 € hat keinen EK. 0 € gilt nie als Einkaufspreis: "
            "die Kalkulation rechnet nicht damit, sondern meldet <i>kein Einkaufspreis</i>, und das Angebot bleibt "
            "unvollständig, bis der Preis eingetragen ist. In der Übersicht steht in der Spalte EK rot <i>EK "
            "fehlt</i>; der Filter <b>Status: EK fehlt</b> zeigt alle aktiven Artikel ohne Preis.",
            "<b>EK eintragen …</b> (Knopf unter der Tabelle oder rechte Maustaste) fragt den Einkaufspreis netto je "
            "Einheit ab und trägt ihn beim bevorzugten Lieferanten ab Menge 1 ein; ohne Lieferant bei Blechteilen "
            "beim Lieferanten <i>Technik</i>. Die Änderung kommt ins Protokoll der Preisänderungen. Staffeln und "
            "weitere Bedingungen werden im Formular gepflegt. Im Angebot trägt <b>Zukaufteile … → EK eintragen …</b> den "
            "Preis ab der Stückzahl der Position ein ([[zukauf_positionen]]).",
            "<b>Dubletten</b>: vor dem Anlegen sucht der STEP-Import vorhandene aktive Blechartikel mit gleicher Dicke "
            "(± 0,05 mm), gleicher Länge und Breite (± 0,5 mm, auch um 90° gedreht), gleichem Werkstoff und gleicher "
            "Geometrie-Kennung und verwendet diesen Artikel, statt einen zweiten anzulegen. Stimmen nur die Maße, "
            "schlägt er den Artikel zur Auswahl vor. Archivierte Artikel zählen nicht.",
            "<b>Duplizieren</b> übernimmt Maße und Werkstoff, aber nicht STEP-Datei und Kennung: die Kopie gilt als "
            "von Hand angelegt.")


def kapitel_frachtkosten(i):
    i.kapitel("Frachtkosten verwalten", marke="frachtkosten")
    i.text("Der Reiter <i>Frachtkosten</i> rechnet Frachtkosten aus Postleitzahl, Gewicht, Ladehilfsmitteln, Tarif und "
           "Zuschlägen. Alle Preise, Zonen und Zuschläge werden selbst gepflegt; das Programm erfindet keine Tarife und "
           "holt keine Dieselpreise aus dem Internet. Eine neue Datendatei bringt Beispielwerte mit, die mit "
           "<b>BEISPIEL</b> gekennzeichnet sind; jede Rechnung damit zeigt die Warnung <i>Beispieltarif – keine "
           "echten Preise</i>. Ältere Datendateien bekommen die Frachttabellen leer.")
    i.text("Hier stehen Zonen, Tarife, Paletten und Zuschläge, mit denen die Fracht gerechnet wird. Der Rechner ist "
           "frei; zum Pflegen <b>Frachtdaten öffnen</b> mit dem Passwort der Einstellungen.", kurz=True)
    i.text("Der Reiter hat sieben Unterreiter: <i>Fracht kalkulieren</i>, <i>Frachtzonen und Postleitzahlen</i>, "
           "<i>Tarifverwaltung</i>, <i>Paletten und Ladehilfsmittel</i>, <i>Zuschläge</i>, <i>Dienstleister und "
           "Kundentarife</i> sowie <i>Historie und Einstellungen</i>. Der Rechner ist frei; die übrigen sechs öffnen "
           "mit dem Passwort der Einstellungen (Passwort eintippen, <b>Frachtdaten öffnen</b>). Einmal geöffnet gilt "
           "das für beide Reiter, bis <i>Einstellungen sperren</i> gedrückt wird.")
    i.bild("fracht_gesperrt", "Pflegebereich der Frachtkosten gesperrt", hoehe=45 * mm, legende=[
        (1, "Reiter Frachtkosten"), (2, "Passwort der Einstellungen"), (3, "<b>Frachtdaten öffnen</b>")])
    i.abschnitt("Frachtzonen und Postleitzahlen", marke="frachtzonen")
    i.bild("fracht_zonen", "Frachtzonen und Postleitzahlen (Beispielwerte)", hoehe=110 * mm, legende=[
        (1, "<b>PLZ testen</b>: Land und PLZ eintippen, daneben steht die Zone und die Regel."),
        (2, "<b>CSV exportieren</b> schreibt alle PLZ-Zuordnungen als CSV (Semikolon, für Excel)."),
        (3, "<b>CSV importieren</b> liest eine solche Datei. Gleiche Regeln (Land, PLZ von, PLZ bis, Richtung, "
            "Dienstleister, Kunde) werden ersetzt, neue angefügt. Fehlerhafte Zeilen (unbekannte Zone, PLZ bis vor "
            "PLZ von …) meldet das Programm mit Zeilennummer und übernimmt sie nicht. Nötig sind die Spalten PLZ von "
            "und Zone; Land leer = DE."),
        (4, "Unterreiter <i>Länder</i> neben <i>Frachtzonen</i>"),
        (5, "<b>Auf Standard zurücksetzen …</b> stellt die Standardzonen wieder her ([[fracht_zonen_standard]]).")])
    i.text("Jede Zone fasst PLZ-Bereiche zusammen; im Feld <b>PLZ testen</b> sieht man sofort, in welche Zone eine PLZ fällt.", kurz=True)
    i.genauer()
    i.tabelle(["Frachtzonen", "Bedeutung"], [
        ["<b>Zone</b>, <b>Bezeichnung</b>", "Kurzname und freie Bezeichnung, z. B. Z1 Nahbereich"],
        ["<b>Land</b>", "Ländercode aus den Ländern"],
        ["Zonenart", "normal, Insel, Randgebiet, Sondergebiet oder Ausland; Insel, Randgebiet und Sondergebiet lösen "
                     "Zuschläge mit der Bedingung „Zonenart …“ aus"],
        ["Standardzone", "ja = gilt für PLZ des Landes ohne Zuordnung (mit Warnung); je Land höchstens eine"],
        ["Entfernung [km]", "für Tarife mit Preisen je km"],
        ["Aktiv", "nein = Zone deaktiviert, wird nicht mehr zugeordnet (leer = ja)"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.tabelle(["PLZ-Zuordnungen", "Bedeutung"], [
        ["<b>Land</b>, <b>PLZ von</b>, PLZ bis", "eine PLZ (nur PLZ von), ein Bereich (01067 bis 01099) oder ein Präfix "
                                                 "(80* oder kurz 80: bis drei Ziffern ohne PLZ bis gelten als Präfix, "
                                                 "auch im CSV-Import). Mehrere Bereiche je Zone sind mehrere Zeilen."],
        ["<b>Zone</b>", "Zone, in die die PLZ fällt"],
        ["Richtung", "beide, Empfang oder Versand (unterschiedliche Zonen für Versand und Empfang); leer = beide"],
        ["Dienstleister, Kundennummer", "Regel gilt nur für diesen Frachtführer bzw. Kunden (Ausnahmen)"],
        ["Priorität (1 = zuerst)", "entscheidet, wenn sonst zwei Regeln gleich gut passen"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.text("<b>Rangfolge</b>, wenn mehrere Regeln passen: Kunde + Dienstleister vor Kunde vor Dienstleister vor "
           "allgemein; dann einzelne PLZ vor dem engsten Bereich vor dem kürzesten Präfix; dann die kleinere "
           "Priorität. Bleibt ein Gleichstand mit verschiedenen Zonen, meldet das Programm <i>mehrdeutig</i> und "
           "rechnet nicht.")
    i.text("<b>Zweistellige PLZ</b> (im Rechner, beim PLZ testen und im Angebot): Kürzere Eingaben als die PLZ-Länge "
           "des Landes stehen für den ganzen Bereich, z. B. 40 für 40000–40999. Liegt er ganz in einer Zuordnung, "
           "gilt deren Zone. Berührt er mehrere Zonen, rechnet das Programm jede davon und nimmt die teurere (mit "
           "Hinweis); Teile des Bereichs ohne Zuordnung gehören zur Standardzone. Beispiel mit den Beispielwerten: "
           "25 liegt in Z5 (Inseln 25938–25999) und für den Rest in der Standardzone Z3; es gilt Z5.")
    i.tabelle(["Länder", "Bedeutung"], [
        ["<b>Land</b>", "zweistelliger Ländercode, z. B. DE, AT, CH"],
        ["Bezeichnung, PLZ-Stellen, Währung", "Name, Stellenzahl der PLZ (für die Prüfung), Währung (leer = EUR)"],
        ["Aktiv, Bemerkung", "leer = aktiv; freier Text"]], [75, 190])
    i.abschnitt("Frachtzonen auf Standard zurücksetzen", marke="fracht_zonen_standard")
    i.text("<b>Auf Standard zurücksetzen …</b> holt die mitgelieferten Zonen zurück; vorher legt das Programm eine "
           "Sicherung an.", kurz=True)
    i.genauer()
    i.text("Sind die Zonen oder PLZ-Zuordnungen durcheinandergeraten, stellt <b>Auf Standard zurücksetzen …</b> "
           "(oben rechts auf dem Unterreiter <i>Frachtzonen und Postleitzahlen</i>) den mitgelieferten Stand wieder "
           "her. Der Standard sind die Zonen der Richtwerte Palettenversand ([[fracht_richtwerte]]): vier Zonen nach "
           "Entfernung vom Versandort (Absender-PLZ in den Einstellungen) und die Inselzone.")
    i.liste("Vorher fragt das Programm nach und nennt, wie viele Zonen und PLZ-Zuordnungen gelöscht werden. Auch "
            "eigene Zonen und Zuordnungen verschwinden.",
            "Vor dem Zurücksetzen legt das Programm eine Datensicherung an (Name endet auf "
            "<i>_vor_Frachtzonen_Standard</i>). Mit <b>Sicherung wiederherstellen …</b> lässt sich der alte Stand "
            "zurückholen ([[datensicherung]]).",
            "Die Preise des Richtwert-Tarifs werden passend zu den Zonen neu geschrieben. Andere Tarife, Zuschläge "
            "und Ladehilfsmittel bleiben. Verweisen Preise anderer Tarife auf Zonen, die es danach nicht mehr gibt, "
            "sagt das die Rückfrage; diese Preise gelten dann nicht mehr.",
            "Angebote mit gespeicherter Frachtberechnung behalten ihre Tarifkopie.")
    i.abschnitt("Tarifverwaltung", marke="tarife")
    i.bild("fracht_tarife", "Tarifverwaltung: Tarife oben, Preisstaffeln des markierten Tarifs unten", hoehe=110 * mm,
           legende=[
        (1, "<b>Neue Version …</b> kopiert den markierten Tarif mit allen Preisen und neuem „Gültig ab“; der alte "
            "Tarif gilt bis zum Vortag. So bleiben Tarifwechsel lückenlos und nachvollziehbar."),
        (2, "Unten stehen nur die Preisstaffeln des markierten Tarifs; neue Zeilen bekommen ihn automatisch."),
        (3, "<b>Preise aller Tarife zeigen</b> hebt den Filter auf.")])
    i.text("Oben die Tarife, unten die Preise des markierten Tarifs je Zone und Gewicht.", kurz=True)
    i.genauer()
    i.tabelle(["Tarife", "Bedeutung"], [
        ["<b>Tarif</b>, Bezeichnung", "Kurzname und Klartext"],
        ["Dienstleister, Tarifart", "Frachtführer; Standardtarif, Rahmenvertrag, Sondertarif, Kundentarif oder interner "
                                    "Verrechnungstarif (leer = Standardtarif)"],
        ["<b>Tarifmodell</b>", "Gewichtstarif (Preise nach kg), Palettentarif und Gitterboxtarif (nach Ladungsträgern "
                               "oder Stellplätzen), Kombinationstarif und Individueller Tarif (alle Bezugseinheiten, "
                               "z. B. Grundpreis je Sendung + kg + Paletten)"],
        ["Versandart, Länder, Zonen, Kundennummer", "wofür der Tarif gilt; leer = alle. Mehrere Länder oder Zonen mit "
                                                    "Komma trennen."],
        ["Gültig ab, Gültig bis, Währung", "Gültigkeitszeitraum (leer = unbegrenzt) und Währung (leer = EUR)"],
        ["Mindestfracht, Rabatt", "Mindestbetrag der Grundfracht; Rabatt in % auf die Grundfracht (vor der "
                                  "Mindestfracht)"],
        ["Frachtpfl. Gewicht je m³ [kg], Frachtpfl. Gewicht je Stellplatz [kg], Frachtpfl. Gewicht je Lademeter [kg]", "Faktoren für das frachtpflichtige Gewicht; leer = "
                                                                   "nicht verwendet"],
        ["Gewicht aufrunden auf", "z. B. 1 oder 10 kg"],
        ["Priorität (1 = zuerst), Version, Aktiv, Bemerkung", "Vorrang bei gleicher Tarifart, Versionsangabe, "
                                                             "aktiv/inaktiv, freier Text"]], [75, 190])
    i.tabelle(["Preisstaffeln", "Bedeutung"], [
        ["<b>Tarif</b>, Zone", "zu welchem Tarif die Zeile gehört; Zone leer = alle Zonen (eine Zeile für die Zone "
                               "geht vor)"],
        ["<b>Bezugseinheit</b>", "Sendung, kg, 100 kg, Ladungsträger, Stellplatz, km oder Lademeter: worauf sich der "
                                 "Preis bezieht"],
        ["Ladehilfsmittel", "Art, für die die Zeile gilt (z. B. Gitterbox mit eigenem Preis); leer = alle übrigen"],
        ["bis Menge", "Obergrenze der Stufe in der Bezugseinheit (bei kg und 100 kg immer in kg, beide bilden eine "
                      "Gewichtsstaffel); leer = ohne Obergrenze. Es gilt die erste Stufe, in die die Menge fällt "
                      "(genau auf der Grenze gehört zur Stufe)."],
        ["Preis, Preisart", "Festpreis = Preis der ganzen Stufe; je Einheit = Preis × Menge (bei 100 kg: Preis × kg ÷ "
                            "100). Preis leer = individuelle Berechnung: das Programm rechnet diese Stufe nicht und "
                            "meldet es."],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.text("Beispiel Gewichtstarif: Zeilen kg bis 100, 250, 500, 1.000 mit Festpreis und eine Zeile 100 kg ohne "
           "Obergrenze je Einheit. Beispiel Palettentarif: Stellplatz bis 1, bis 3, bis 6 je Einheit und eine Zeile "
           "ohne Preis („mehr als 6 Paletten individuell“). In einer gemischten Sendung braucht jede Art von "
           "Ladungsträger eine passende Zeile, sonst meldet das Programm <i>Tarif ohne Preis für …</i> statt mit 0 € "
           "zu rechnen.")
    i.abschnitt("Paletten und Ladehilfsmittel")
    i.bild("fracht_lht", "Paletten und Ladehilfsmittel (Beispielwerte)", hoehe=90 * mm)
    i.text("Paletten mit Eigengewicht, Nutzlast, Stellplätzen und größter Teillänge (für den Packvorschlag).",
           kurz=True)
    i.genauer()
    i.tabelle(["Ladehilfsmittel", "Bedeutung"], [
        ["<b>Ladehilfsmittel</b>, Bezeichnung", "Kurzname und Klartext"],
        ["<b>Art</b>", "Europalette, Einwegpalette, Industriepalette, Gitterbox, Sonderpalette, Langgut oder "
                       "Sonderladung"],
        ["Länge, Breite, Höhe [mm]", "für Volumen und Lademeter; fehlt ein Maß, rechnet das Programm ohne Volumen"],
        ["Eigengewicht, Nutzlast [kg]", "Eigengewicht = Verpackungsgewicht; Nutzlast für Packvorschlag und Warnung"],
        ["Max. Teillänge [mm]", "längere Teile kommen im Packvorschlag auf Langgut"],
        ["Stapelbar, Stapelfaktor", "wie viele übereinander einen Stellplatz teilen"],
        ["Stellplätze je Stück", "z. B. 1 für eine Europalette, 3 für Langgut (leer = 1)"],
        ["Aktiv, Bemerkung", "leer = aktiv; freier Text"]], [75, 190])
    i.abschnitt("Zuschläge")
    i.bild("fracht_zuschlaege", "Zuschläge, darunter Dieselpreise, Dieselstaffel und Währungen", hoehe=105 * mm,
           legende=[(1, "Unterreiter <i>Dieselpreise</i>"), (2, "Unterreiter <i>Dieselstaffel</i>"),
                    (3, "Unterreiter <i>Währungen</i>")])
    i.text("Zuschläge in € oder % mit Bedingung (immer, ab Gewicht, nur wenn gewählt …), darunter Diesel und "
           "Währungen.", kurz=True)
    i.genauer()
    i.tabelle(["Zuschläge", "Bedeutung"], [
        ["<b>Zuschlag</b>, Bezeichnung", "Kurzname und Text in der Kostenübersicht"],
        ["<b>Typ</b>", "Diesel, Maut, Energie, Gefahrgut, Langgut / Überlänge, Sperrgut, Insel- und Randgebiet, "
                       "Avisierung, Hebebühne, Express, Fixtermin, Mindermenge, Wartezeit, Be- und Entladung, "
                       "Sonderhandling oder sonstiger Zuschlag. Je Typ gilt nur ein Zuschlag: der speziellere (Kunde vor "
                       "Dienstleister vor Tarif vor allgemein); die anderen stehen unter „nicht angewendet“."],
        ["<b>Berechnungsart</b>", "%, € je Sendung, € je kg, € je 100 kg, € je Ladungsträger, € je Stellplatz, € je "
                                  "Stunde oder Dieselstaffel"],
        ["Berechnungsgrundlage, Grundlage Zuschläge", "für Prozentzuschläge: Grundfracht, Grundfracht + "
                                                      "Leistungszuschläge oder gewählte Zuschläge (Kurznamen mit Komma, "
                                                      "auch „Grundfracht“). Die Kostenübersicht nennt die Grundlage."],
        ["Wert [% bzw. €]", "Prozentsatz oder Betrag"],
        ["Mindestbetrag, Höchstbetrag", "Grenzen des Zuschlags"],
        ["Gültig ab, Gültig bis", "Zeitraum; außerhalb wirkt der Zuschlag nicht"],
        ["Länder, Zonen, Tarife, Dienstleister, Kundennummer", "wofür der Zuschlag gilt; leer = alle"],
        ["Bedingung, Grenze", "immer, nur wenn gewählt (Zusatzleistung im Rechner), Gewicht unter / über Grenze [kg] "
                              "(z. B. Mindermengenzuschlag), Gewicht je Stellplatz über Grenze [kg] (schwere "
                              "Paletten; meist mit € je Stellplatz), Teillänge über Grenze [mm] (Überlänge) oder Zonenart "
                              "Insel/Randgebiet/Sondergebiet"],
        ["Aktiv, Bemerkung", "leer = aktiv; freier Text"]], [75, 190])
    i.text("<b>Dieselzuschlag</b>: als Prozent auf die Grundfracht oder eine andere Grundlage, als Festbetrag je "
           "Sendung oder über die Dieselstaffel. Für die Dieselstaffel trägt man unter <i>Dieselpreise</i> den "
           "Dieselpreis mit Datum ein (Gültig ab, Dieselpreis [€/l], Quelle) und unter <i>Dieselstaffel</i> die "
           "Schwellen (Zuschlag, Dieselpreis ab [€/l], Zuschlag [% bzw. €]). Es gilt der letzte Dieselpreis bis zum "
           "Datum der Kalkulation und die höchste erreichte Schwelle. Fehlt ein Dieselpreis, rechnet das Programm "
           "den Zuschlag nicht und warnt.")
    i.tabelle(["Währungen", "Bedeutung"], [
        ["<b>Währung</b>", "z. B. CHF"],
        ["Kurs (1 Einheit = … €), Stand", "Umrechnungskurs und Datum; ohne Kurs rechnet ein Tarif in dieser Währung nicht"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.abschnitt("Dienstleister und Kundentarife")
    i.bild("fracht_dienstleister", "Dienstleister und Kundentarife", hoehe=95 * mm, legende=[
        (1, "<b>Kundentarif anlegen</b> legt einen Tarif mit Tarifart Kundentarif an und öffnet die Tarifverwaltung; "
            "dort Tarif-ID, Kundennummer und Preise eintragen."),
        (2, "Übersicht aller Kundentarife, Rahmenverträge und Sondertarife; Doppelklick öffnet den Tarif.")])
    i.text("Speditionen und eigene Tarife für einzelne Kunden.", kurz=True)
    i.genauer()
    i.tabelle(["Dienstleister", "Bedeutung"], [
        ["<b>Dienstleister</b>, Name", "Kurzname und Name des Frachtführers"],
        ["Versandarten", "mit Komma getrennt, erscheinen im Rechner zur Auswahl"],
        ["Unsere Kundennummer beim Dienstleister", "zur Info"],
        ["Aktiv, Bemerkung", "leer = aktiv; freier Text"]], [75, 190])
    i.abschnitt("Historie und Einstellungen", marke="fracht_einstellungen")
    i.bild("fracht_historie", "Historie und Einstellungen", hoehe=100 * mm, legende=[
        (1, "Gespeicherte Kalkulationen: Datum, Bezeichnung, Empfänger, Zone, Tarif, frachtpflichtiges Gewicht, "
            "Gesamt"),
        (2, "<b>Kalkulation anzeigen</b> (oder Doppelklick) zeigt die Kostenübersicht wie beim Speichern."),
        (3, "Einstellungen der Frachtkosten: Absender-PLZ (Versandort), Absender-Land, Versandart für automatische "
            "Fracht ([[fracht_angebot]]), Ladungsträger im Packvorschlag, Ladungsträger für lange Teile "
            "(Langgut)"),
        (4, "<b>Beispieldaten laden</b> fügt die Beispiel-Zonen, -Tarife, -Ladehilfsmittel und -Zuschläge hinzu "
            "(BEISPIEL); vorhandene Einträge bleiben."),
        (5, "<b>Richtwerte laden</b> ersetzt die Beispielwerte durch Richtwerte für den Palettenversand (unten).")])
    i.text("Gespeicherte Frachtrechnungen und die Einstellungen: Absender-PLZ, Versandart der automatischen Fracht, "
           "Paletten im Packvorschlag.", kurz=True)
    i.genauer()
    i.abschnitt("Richtwerte Palettenversand", marke="fracht_richtwerte")
    i.text("Ohne Preise der eigenen Spedition rechnet das Programm mit Richtwerten (eher etwas zu teuer). "
           "<b>Richtwerte laden</b> setzt sie neu; eigene Einträge bleiben.", kurz=True)
    i.genauer()
    i.text("Solange keine Preise der eigenen Spedition vorliegen, rechnet das Programm mit <b>Richtwerten</b>: "
           "Marktpreise aus Online-Frachtrechnern (Stand 10/2026, netto, Maut und Diesel enthalten), angesetzt an der "
           "Obergrenze der üblichen Spanne plus 10 % Puffer, also eher etwas zu teuer als zu günstig. Alle Zeilen "
           "tragen RICHTWERT in der Bemerkung, jede Rechnung damit zeigt den Hinweis <i>Richtwert – kein "
           "Speditionsangebot</i>. <b>Richtwerte laden</b> fragt nach (ohne Absender-PLZ zuerst nach dem Versandort), "
           "löscht alle Zeilen mit BEISPIEL oder RICHTWERT in der Bemerkung und lädt die Richtwerte neu; eigene "
           "Einträge bleiben. Leere Absender-PLZ und die Versandart (Palettenversand statt Stückgut) werden gesetzt. "
           "Angebote mit gespeicherter Frachtberechnung behalten ihre Tarifkopie, bis die Ziel-PLZ neu eingegeben "
           "oder der Haken neu gesetzt wird.")
    i.tabelle(["Zone (Straßen-km ab Versandort)", "1 Palette", "2–3 Paletten je Stück", "4–6 Paletten je Stück"], [
        ["RW1 bis 200 km", "100,00 €", "85,00 €", "70,00 €"],
        ["RW2 200–450 km", "115,00 €", "97,75 €", "80,50 €"],
        ["RW3 450–650 km", "125,00 €", "106,25 €", "87,50 €"],
        ["RW4 über 650 km und RW-INSEL", "140,00 €", "119,00 €", "98,00 €"]], [70, 45, 75, 75])
    i.liste("Die Zone kommt aus den ersten zwei Ziffern der Ziel-PLZ: Entfernung vom Versandort zum Mittelpunkt der "
            "PLZ-Region (Luftlinie × 1,25). Ab 33129 Delbrück liegen z. B. Bielefeld und Dortmund in RW1, Hamburg, "
            "Berlin, Frankfurt und Stuttgart in RW2, Dresden und München in RW3. Inseln ohne Brücke (Sylt, Föhr, "
            "Amrum, Pellworm, Halligen, Ostfriesische Inseln, Helgoland, Hiddensee) sind die Zone RW-INSEL.",
            "Mehr als 6 Stellplätze: Teilladung, Preis anfragen (das Programm rechnet nicht still weiter).",
            "Paletten: Europalette und Einwegpalette bis 800 kg Nutzlast im Packvorschlag, Industriepalette 1,25 "
            "Stellplätze, Sonderpalette bis 2,40 m 2 Stellplätze, Langgut bis 6,5 m 3 Stellplätze.",
            "Zuschläge: schwere Palette 40 € je Stellplatz ab 300 kg je Stellplatz, Überlänge (Teile über 2,40 m) "
            "60 €, Inselzuschlag 60 €; nur wenn gewählt: Avisierung 25 €, Hebebühne 40 €, Wartezeit 60 € je Stunde "
            "(Hebebühne und Wartezeit geschätzt). Kein Diesel- und kein Mautzuschlag, beide sind im Preis enthalten.",
            "Beispiele ab Delbrück: 1 Palette 190 kg nach Hamburg 115 €, nach München 125 €; schwere Palette 450 kg "
            "nach Hamburg 155 €; Langgut 6 m mit 500 kg nach Hamburg 353,25 €; Sylt 200 €.",
            "Der Dienstleister SLH (Spedition u. Logistik Haaren, Keimeier u. Finke) ist angelegt; öffentliche "
            "Preise gibt es nicht. Liegt ein Angebot vor, die Preise als eigenen Tarif für SLH eintragen; er gilt "
            "dann vor dem Richtwert, wenn er eine kleinere Priorität hat (Richtwert: 50).")
    i.text("Fracht im Angebot und je Staffelmenge: [[fracht_angebot]] und [[staffeln]].")
    i.text("Jede gespeicherte Kalkulation enthält eine vollständige Kopie aller verwendeten Werte: Tarif und Version, "
           "Preisstaffeln, Zone und PLZ-Regel, Zuschläge, Dieselpreis, Kurs, Gewicht und Ladehilfsmittel. Spätere "
           "Änderungen an Tarifen oder Zuschlägen ändern gespeicherte Kalkulationen nicht.")


def kapitel_pflege(i):
    i.kapitel("Updates und Datensicherung", marke="pflege")
    i.text("Das Programm holt Updates auf Knopfdruck aus dem Internet und sichert die Datendatei selbst. Hier steht, "
           "wie beides geht und wie die Daten auf einen anderen Rechner umziehen.")
    i.abschnitt("Updates", marke="updates")
    i.bild("update_hinweis", "Hinweis auf eine neue Version", hoehe=55 * mm, legende=[
        (1, "<b>Jetzt aktualisieren</b>: lädt die neue Version, schließt alles, tauscht die Dateien aus und "
            "startet das Programm neu. <b>Später</b>: "
            "nichts ändern, beim nächsten Start kommt der Hinweis wieder.")])
    i.text("Gibt es eine neue Version, meldet sich das Programm beim Start: <b>Jetzt aktualisieren</b>. Von Hand: "
           "<b>Hilfe → Nach Updates suchen …</b>. Vorher sichert es die Daten und schließt alles, was den Austausch "
           "behindern könnte.", kurz=True)
    i.genauer()
    i.text("Das Programm sucht bei jedem Start im Hintergrund nach einer neueren Version (öffentliches Verzeichnis "
           "<i>Rohrlaser-Updates</i> auf GitHub, ohne Anmeldung), installiert wie portabel. Gibt es eine, erscheint das Fenster <b>Update verfügbar</b> mit dem installierten und dem neuen Stand und der letzten "
           "Änderung. Ohne Internet oder bei einem Fehler meldet sich das Programm beim Start nicht. Von Hand: "
           "<b>Hilfe → Nach Updates suchen …</b>; dort steht auch, wenn das Programm schon aktuell ist. Welcher Stand "
           "installiert ist, zeigen Fenstertitel, Startseite und <i>Hilfe → Über …</i>.")
    i.liste("Das Programm vergleicht jede Programmdatei über ihre Prüfsumme mit der neuen Version und lädt <b>nur die "
            "geänderten Dateien</b>. Meist sind das wenige MB statt des ganzen ZIP mit rund 180 MB. Beschädigte oder "
            "fehlende Programmdateien werden dabei gleich mit ersetzt.",
            "Nach dem Laden legt es eine geprüfte Sicherung der Datendatei an (Ordner <i>Sicherung</i> im "
            "Datenordner, Name endet auf <i>_vor_update</i>). Scheitert diese Sicherung, bricht das Update ab.",
            "Dann <b>schließt das Programm alles</b>, was den Austausch behindern kann: weitere Fenster und Dialoge, "
            "eine laufende STEP-Messung, Hintergrund-Rechnungen (Staffelpreise), es legt die Angebote in den "
            "gemeinsamen Ordner, sichert wie beim Beenden und gibt die Datendatei frei. Erst danach tauscht es die "
            "Dateien aus und startet neu; die Statuszeile meldet <i>Update eingespielt</i>.",
            "Hält ein anderes Programm eine Datei fest (Virenscanner, Explorer-Vorschau), wartet das Programm bis zu "
            "30 Sekunden. Ist dann nur die Anleitung (PDF) noch gesperrt, aktualisiert es trotzdem und tauscht die "
            "Anleitung beim nächsten Start. Bei anderen Dateien nennt es Datei und das Programm, das sie festhält: "
            "dieses schließen und "
            "<b>Wiederholen</b>, oder <b>Abbrechen</b>. Bei Abbruch oder Fehler stellt es alle Dateien zurück und "
            "startet die bisherige Version wieder; nichts ist verändert. Einzelheiten stehen im Protokoll "
            "(<i>Daten\\Protokoll\\fehler.log</i>).",
            "<i>Hilfe → Bedienungsanleitung</i> öffnet eine Kopie im Datenordner (Ordner <i>Anleitung</i>). Eine "
            "offene Anleitung blockiert das Update deshalb nicht mehr.",
            "Ist zwischen Suche und Klick auf <i>Jetzt aktualisieren</i> schon eine noch neuere Version erschienen, "
            "holt das Programm von selbst deren Dateiliste und spielt gleich diese ein. Meldet es trotzdem "
            "<i>HTTP Error 404</i>, einfach <i>Hilfe → Nach Updates suchen …</i> noch einmal aufrufen.",
            "Angefasst werden nur die Programmdateien: Daten, Ablage, <i>Portabel.ini</i> und eigene Dateien im "
            "Programmordner bleiben, wie sie sind. Die alten Programmdateien liegen bis zum nächsten Start in "
            "<i>_update</i> und werden dann gelöscht.",
            "Braucht eine neue Version eine erweiterte Datendatei, sichert das Programm sie vorher (Name endet auf "
            "<i>_vor_Schema_…</i>). Eine ältere Programmversion öffnet eine so erweiterte Datei nicht mehr, sondern "
            "meldet, dass sie von einer neueren Version stammt.",
            "Das Update funktioniert ab Version 0.5.5. Ältere Versionen suchen noch im privaten Programmverzeichnis, "
            "das ohne Anmeldung nicht erreichbar ist, und melden <i>Keine Verbindung zum Update</i>. Dann einmal das "
            "neue Setup über die alte Installation installieren bzw. das neue ZIP entpacken und die Daten übernehmen "
            "([[datensicherung]]); danach geht es online weiter.")
    i.abschnitt("Datensicherung und Umzug", marke="datensicherung")
    i.liste("Das Programm sichert von selbst: täglich, beim Beenden und vor jedem Update oder Import.",
            "Selbst sichern: <b>Datensicherung erstellen</b> (Startseite oder Menü Datei).",
            "Zurückholen: <b>Sicherung wiederherstellen …</b>, Sicherung wählen, <b>Wiederherstellen</b>.",
            kurz=True)
    i.bild("sicherung_wiederherstellen", "Sicherung wiederherstellen", hoehe=80 * mm, legende=[
        (1, "Sicherungen aus dem Datenordner und dem zweiten Sicherungsordner, neueste oben, mit Art, Anzahl "
            "Angebote und Positionen. Grau: beschädigt oder von einer neueren Programmversion."),
        (2, "<b>Wiederherstellen</b>: ersetzt alle Daten durch die gewählte Sicherung (Doppelklick geht auch). "
            "<b>Andere Datei …</b>: eine Sicherung, Datendatei oder Export-Datei von woanders wählen.")])
    i.genauer()
    i.text("Das Programm sichert die Datendatei in den Ordner <i>Sicherung</i> im Datenordner:")
    i.liste("beim ersten Start jedes Tages,",
            "beim Beenden (eine je Tag, wird bei jedem Beenden erneuert, Name endet auf <i>_beenden</i>),",
            "mit <b>Datensicherung erstellen</b> (Startseite oder Menü <i>Datei</i>),",
            "vor einem Update (<i>_vor_update</i>), vor dem Erweitern der Datendatei (<i>_vor_Schema_…</i>), vor dem "
            "Wiederherstellen (<i>_vor_Wiederherstellung</i>), vor einem Import (<i>_vor_Import</i>), vor dem "
            "Zurücksetzen der Frachtzonen (<i>_vor_Frachtzonen_Standard</i>, [[fracht_zonen_standard]]) und vor dem "
            "CSV-Import der Kunden (<i>_vor_Kundenimport</i>, [[kunden_csv]]).")
    i.text("Jede Sicherung wird gleich nach dem Schreiben geprüft: die Datei muss unbeschädigt sein und gleich viele "
           "Angebote und Positionen enthalten wie die Datendatei. Daneben liegt eine gleichnamige <i>.json</i>-Datei "
           "mit Programmversion, Zeit, Anzahl Angebote und Prüfsumme. Von den laufenden Sicherungen bleiben die "
           "letzten 30, von jeder Art der Sicherungen „vor …“ die letzten 10; sie werden also nicht von den "
           "täglichen Sicherungen verdrängt. Gelöscht werden nur ältere Sicherungen, nie Angebote oder Stammdaten.",
           "<b>Zweiter Sicherungsordner</b> (Einstellungen, Gruppe Ablage): z. B. ein Netzlaufwerk, OneDrive oder ein "
           "USB-Stick. Beim Beenden, mit <i>Datensicherung erstellen</i> und vor Updates geht dann zusätzlich eine "
           "Kopie dorthin. Ist der Ordner nicht erreichbar, meldet das Programm das beim Beenden und fragt, ob "
           "trotzdem beendet werden soll; die Sicherung im Datenordner ist dann trotzdem angelegt. Für die "
           "installierte Version ist ein zweiter Ordner besonders zu empfehlen.")
    i.liste("<b>Sicherung wiederherstellen …</b> (Startseite oder Menü <i>Datei</i>): Das Programm prüft die "
            "gewählte Sicherung, sichert vorher den jetzigen Stand (<i>_vor_Wiederherstellung</i>, damit lässt sich "
            "das Wiederherstellen selbst rückgängig machen), schließt offene Angebote und lädt alles neu. Eine "
            "Sicherung einer neueren Programmversion wird abgelehnt; erst das Programm aktualisieren.",
            "<b>Datei → Daten exportieren …</b> schreibt alle Daten in eine Export-Datei (ZIP mit Datendatei und "
            "Beschreibung). <b>Datei → Daten importieren …</b> liest eine Export-Datei, eine Sicherung oder eine "
            "Datendatei <i>rohrlaser.db</i> ein und ersetzt damit alle Daten; vorher sichert es den jetzigen Stand "
            "(<i>_vor_Import</i>). Eine beschädigte Export-Datei erkennt das Programm an der Prüfsumme.",
            "Lässt sich die Datendatei beim Start nicht öffnen (beschädigt, von einer neueren Version), bietet das "
            "Programm an, eine Sicherung zu wählen. Die nicht lesbare Datei wird dabei nicht gelöscht, sondern in den "
            "Ordner Sicherung verschoben (Name endet auf <i>_vor_Uebernahme</i>).")
    i.text("<b>Umziehen</b> von der portablen auf die installierte Version (oder auf einen anderen Rechner): in der "
           "alten Version <i>Daten exportieren …</i>, in der neuen <i>Daten importieren …</i>. Einfacher beim "
           "ersten Start der neuen Version: auf die Frage nach vorhandenen Daten <b>Daten übernehmen …</b> wählen "
           "und die Datei <i>Daten\\rohrlaser.db</i> der portablen Version, eine Sicherung oder eine Export-Datei "
           "angeben. Übernommen wird eine Kopie, die Quelle bleibt unverändert. Danach mit der neuen Version "
           "weiterarbeiten und die alte nicht mehr benutzen, sonst laufen zwei Datenbestände auseinander.",
           "Jeder Arbeitsplatz hat seine eigene Datendatei; geteilt wird über den gemeinsamen Ordner "
           "([[mehrere_arbeitsplaetze]]), nicht über eine gemeinsame Datendatei. Solange das Programm läuft, sperrt "
           "es seine Datendatei: Ein "
           "zweites Programm mit derselben Datendatei (die andere Version, ein zweites Fenster oder ein anderer "
           "Rechner auf einem Netzlaufwerk) meldet <b>„schon in einem anderen Programm geöffnet“</b> mit Rechner und "
           "Benutzer und startet nicht.")


def kapitel_step_messung(i):
    i.kapitel("Anhang: STEP-Messung im Detail", marke="step_messung")
    i.text("Dieser Anhang erklärt für Fachleute, wie <i>STEP-Import.exe</i> misst. Für die Bedienung reicht "
           "[[step]].")
    i.abschnitt("So erkennt die Messung das Rohr")
    i.liste("Die <b>Rohrachse</b> ergibt sich aus der Geometrie selbst: Außen- und Innenmantel liegen parallel zur "
            "Achse. Das klappt bei jeder Lage im Raum (gedreht, verschoben) und unabhängig davon, wie das CAD die "
            "Flächen speichert, auch bei <b>Freiformflächen</b> (B-Spline). Danach wird die Achse über die "
            "Schwerpunkte zweier weit auseinanderliegender Querschnitte genau ausgerichtet.",
            "<b>Breite und Höhe</b> eines Kastenrohrs werden quer zur Achse am kleinsten umschreibenden Rechteck des "
            "Querschnitts gemessen. Ein um die eigene Achse verdrehtes Rohr wird deshalb nicht zu groß gemessen.",
            "Die <b>Wandstärke</b> ist der kleinste Abstand zwischen Außen- und Innenkontur des Querschnitts. "
            "Zur Gegenprobe wird sie an mehreren Stellen gemessen: in drei Querschnitten entlang des Rohrs, je "
            "Querschnitt auf jeder geraden Seite bei 25, 50 und 75 % (in den Rundungen nicht), beim Rundrohr an 8 "
            "Stellen rundum. Weichen die Werte um mehr als 0,05 mm voneinander ab (ungleiche Wände, außermittiges "
            "Innenrohr), kommt der Hinweis <i>Wandstärke nicht einheitlich: … bis … mm</i>. Dann bitte das Profil "
            "prüfen.",
            "Neben den Außenmaßen misst die Messung auch die <b>Innenmaße</b> (Innen-Ø bzw. innere Breite und Höhe).",
            "Erkannt werden <b>Rundrohr, Quadratrohr und Rechteckrohr</b>, dazu <b>U-, C- und L-Profile</b> sowie "
            "<b>Flach-, Vierkant- und Rundstahl</b>, auch gedreht und mit Walz- oder Biegeradien. U-, C-, L-Profile "
            "und Flachstahl werden wie Rohre übernommen und kalkuliert. Vierkant- und Rundstahl werden nur gemeldet: "
            "Sie stehen im Dialog STEP-Import prüfen unter <i>Nicht übernehmbar</i> mit dem Hinweis <i>… wird noch "
            "nicht kalkuliert</i>. Bei C-Profilen steht die Länge der Abkantung im Hinweis, bei U-Profilen mit "
            "verschieden dickem Steg und Flansch beide Werte.",
            "<b>RP-Profile</b> (Rohre mit Anschlag aus doppeltem Blech) erkennt die Messung per <i>Fingerabdruck</i> "
            "aus der RP-Bibliothek: Breite, Höhe, Fläche, Länge der Außenkontur und Zahl der Kammern müssen passen "
            "(Maße ±0,3 mm, Fläche und Kontur ±1,5 %). Das Teil bekommt Profilform <i>RP-Profil</i> und die "
            "Profil-ID der Bibliothek (z. B. <i>RP 0106-35</i>); haben mehrere RP-Profile denselben Querschnitt, "
            "nennt der Hinweis die anderen. Der doppelt liegende Anschlag gilt nicht als ungleiche Wand. Beim "
            "Übernehmen wird die Doppellage nur einmal geschnitten: Ein gerades Ende bekommt die Schnittlänge der "
            "Kontur, ein schräges die gemessene Länge anteilig; der Bericht nennt, um wie viel der Schneidweg kürzer "
            "ist. Selbst geladene RP-Profile ([[rp_profile]]) findet der Import ebenso, wenn die Messung ein "
            "<i>Sonderprofil</i> meldet; von Hand: Art <i>RP-Profil</i> wählen, dann die Profil-ID.",
            "<b>Mehrkammerprofile</b> (mehrere Kammern in einer Außenkontur) werden gemessen und als Sonderprofil zum "
            "Prüfen gemeldet; die Zwischenwände kommen näherungsweise zum Schnitt der Enden dazu (Hinweis). "
            "<b>Verbundprofile</b>: Liegt ein zweiter Körper ganz in der Kammer (Kern aus Kunststoff o. ä.), wird "
            "er als <i>Verbundkern</i> nicht übernommen und das Profil mit Hinweis zum Prüfen gemeldet.",
            "<b>I-/H-Träger und T-Profile</b> werden ebenfalls erkannt und kalkuliert. Gemessen werden Höhe, "
            "Flanschbreite, Stegdicke (Strahl quer durch den Steg) und Flanschdicke (bei einem Viertel der "
            "Flanschbreite neben dem Steg, wie die Norm misst), dazu ob das Profil <i>symmetrisch</i> ist und die "
            "ungefähre Ausrundung zwischen Steg und Flansch. Unsymmetrische Träger (z. B. verschieden dicke "
            "Flansche) stehen mit Prüfstatus <i>prüfen</i> und Hinweis da.",
            "<b>Normprofile</b>: Passen alle Maße zu einem Normprofil (IPE, IPN, HEA, HEB, HEM, UPN, T, Winkel nach "
            "EN 10056) – Höhe und Breite auf ±0,5 mm, Steg und Flansch auf ±0,3 mm (geneigte Flansche ±0,6 mm) und "
            "die gemessene Querschnittsfläche auf 3 % –, schlägt der Import den Normnamen als Profil-ID vor, z. B. "
            "<i>IPE 200</i>. Sonst bleibt es bei den gemessenen Maßen, z. B. <i>I 150x80x5x7</i>. Ein Normname wird "
            "nie ohne diese Prüfung vergeben.",
            "<b>Schnitte an offenen Profilen</b>: Der Laser schneidet jede Wand einmal. Als Schnittlänge eines "
            "Endes, einer Bohrung oder eines Ausschnitts zählt darum die halbe Länge der Konturkanten (Ober- und "
            "Unterseite der Wand). Ein Merkmal, das nur eine Seite der Wand berührt, ist eine Gravur bzw. "
            "Sackbohrung. Die Lage steht entlang der Achse (z ab Ende A), aber nicht um das Profil herum.",
            "Je Merkmal (Achse, Länge, Profil, Wandstärke) bewertet die Messung, wie <b>sicher</b> das Ergebnis ist: "
            "<i>sicher</i>, <i>wahrscheinlich</i> oder <i>unsicher</i>. Die Bewertung steht in den Messwerten "
            "(Spalte <i>sicherheit</i>).",
            "<b>Gegenprobe</b>: Bei einem Rohrteil sind Schnitt- und Konturflächen viel kleiner als der Außenmantel. "
            "Ist das nicht so, war die Lage nicht eindeutig. Dann übernimmt die Messung keine Maße und meldet "
            "<i>Erkennung unsicher</i>.")
    i.abschnitt("Konturen und ihre Lage auf dem Rohr")
    i.text("Jede Kontur wird mit Art, Maßen und Lage erfasst (Messwerte, Spalte <i>konturen_liste</i>). Die Lage gilt "
           "im <b>Rohrkoordinatensystem</b>:")
    i.liste("<b>z</b>: Abstand entlang der Rohrachse ab <b>Ende A</b> in mm (Mitte der Kontur). Ende A ist das Ende, "
            "das in der Datei vorn liegt (kleinere Koordinate in der Hauptrichtung des Rohrs).",
            "<b>Winkel</b>: Lage auf dem Umfang in Grad, rechtsdrehend um die Achse (Daumen der rechten Hand zeigt "
            "von Ende A nach Ende B). <b>0°</b> ist bei Kastenprofilen die Mitte der breiten Seite, die in der Datei "
            "nach oben zeigt (liegt das Rohr senkrecht: nach +Y). Bei Rundrohren ist 0° die oberste Stelle.",
            "<b>u</b>: dieselbe Lage als abgewickelte Länge auf dem Außenumfang ab 0° in mm.",
            "<b>Seite</b> bei Kastenprofilen: 0°, 90°, 180° oder 270°, bzw. <i>Ecke</i>, wenn die Kontur in einer "
            "Rundung liegt.")
    i.text("Erkannte Arten:")
    i.liste("<b>Bohrung</b> mit Durchmesser. <i>schräg</i> gibt an, wie weit die Bohrachse von der Senkrechten "
            "zur Wand abweicht (schräge Durchdringung). <i>gegenüber</i> kennzeichnet zwei Bohrungen auf einer Achse "
            "(eine Bohrung durch beide Wände, zwei Konturen). Im Rundrohr ist die Schnittlänge einer Bohrung "
            "senkrecht zur Oberfläche die Kontur beim 2D-Schnitt: Innenkante radial auf die Außenhaut geschoben "
            "(außen breiter als die Konstruktion, STEP-JSON 1.11).",
            "<b>Langloch</b> und <b>Rechteckausschnitt</b> mit Länge, Breite und Richtung (90° = längs zur "
            "Rohrachse).",
            "<b>Sonderkontur</b>: jede andere Kontur und jede Kontur über mehrere Wände (z. B. ein Ausschnitt über "
            "die Ecke). Sie hat Hüllmaße, die beteiligten Wände und ihren echten <i>Umriss</i> als Punktfolge in "
            "der Abwicklung (u, z; STEP-JSON 1.12). Komplexe Enden bekommen ebenfalls ihren Umriss.",
            "<b>Gravur</b>: Vertiefung bis 0,5 mm (z. B. eine Prägung von 0,2 mm), mit <i>Tiefe</i> und Lage, runde "
            "mit Durchmesser. Tiefere, nicht durchgehende Merkmale sind <b>Sackbohrungen</b> mit dem Hinweis, dass "
            "sie mit dem Laser nicht herstellbar sind. Beide zählen nicht zum Schneidweg.",
            "<b>Innenmerkmal</b>: nur auf der Innenseite, von außen nicht sichtbar. Es wird gemeldet, aber nicht "
            "gerechnet.",
            "<b>Ende A / Ende B</b>: <i>gerade</i>, <i>Gehrung</i> (Neigung um eine Querachse), <i>Schrägschnitt "
            "zweiachsig</i> oder <i>komplex</i> (Ausklinkung, Sattel- oder Formschnitt). Dazu kommen die "
            "Gesamtneigung und die Neigung um beide Querachsen in Grad. Bei ebenen schrägen Enden kommt die "
            "<i>Richtung</i> dazu: der Umfangswinkel (von Ende A gesehen, 0° oben, 90° rechts), in dem das Teil an "
            "diesem Ende am längsten ist. Der Import übernimmt Winkel und Richtung in die Position, damit die "
            "Optimierung Gehrungen ineinanderlegen kann.")
    i.abschnitt("Anbauteile: aufgeschweißte Bolzen, Laschen, Bleche", marke="anbauteile")
    i.text("Manche Kunden konstruieren das Rohr zusammen mit aufgeschweißten Teilen als <b>einen</b> Körper. Diese "
           "Anbauteile gehören nicht zum Rohr: Der Import trennt sie ab, damit Profil, Länge und Schneidweg nur vom "
           "Rohr kommen. Das Originalmodell bleibt unverändert.")
    i.liste("<b>So wird getrennt</b>: Der häufigste Querschnitt entlang der Achse ist das Rohr (Bohrungen machen "
            "einzelne Schnitte kleiner, Anbauteile größer). Seine Außenkontur über die Länge der Rohrwände ist die "
            "<i>Rohrhülle</i>. Bearbeitungen liegen immer in der Hülle, Anbauteile ragen heraus. Was in der Hülle "
            "liegt, wird wie jedes Rohr gemessen; was herausragt, ist ein Anbauteil. Unter einem Anbauteil bleibt "
            "die Rohrwand geschlossen, eine Bohrung unter einer aufgeschweißten Mutter bleibt eine Bohrung.",
            "<b>Arten</b>: <i>Bolzen</i> (runder Fuß, höher als halber Ø), <i>Mutter</i> (Fuß mit Loch), "
            "<i>Lasche</i> (Platte hochkant), <i>Blech</i> (Platte flach oder runde Scheibe), <i>Kopfplatte</i> "
            "(jenseits eines Rohrendes), sonst <i>Sonstiges</i>. Je Anbauteil stehen Lage (z ab Ende A, Winkel und "
            "Seite wie bei Bohrungen), Aufstandsfläche (Form, Maße, Umfang) und Höhe in den Messwerten.",
            "<b>Gravur</b>: Bolzen bekommen eine Positionsmarke (Kreuz aus zwei Strichen je 10 mm = 20 mm Gravur), "
            "Laschen, Bleche, Muttern und Sonstiges den Umriss der Aufstandsfläche, Kopfplatten nichts. Die Gravur "
            "zählt zur Gravurlänge der Position (Vorschub Gravur), nie zum Schneidweg; im Prüfdialog steht sie "
            "getrennt als <i>Gravur</i> der Anbauteile. Geschweißt wird nicht kalkuliert.",
            "<b>Eigene Körper</b> einer Baugruppe (Bleche, Bolzen als Rundstahl), die ein Rohr berühren: Das Rohr "
            "bekommt die Gravur an ihrer Stelle. Im Prüfdialog ist dann <b>Anbauteile nicht ins Angebot "
            "übernehmen</b> angehakt (Vorgabe): Diese Körper werden nicht als eigene Positionen übernommen, ihre "
            "Zeile ist abgewählt mit dem Hinweis <i>Anbauteil von …</i>. Einzelne lassen sich trotzdem anhaken; ohne "
            "Haken an der Option werden sie wie andere Teile übernommen (Bleche als Zukaufteil). Rohre, die andere "
            "Rohre berühren (Gestell), bleiben unberührt.",
            "<b>Unsicher</b> (Prüfstatus <i>prüfen</i>, Übernahme nur mit Häkchen): Anbauteil an einer Ecke oder "
            "der Art <i>Sonstiges</i>, Anbau über (fast) die ganze Länge (das Rohr wird dann aus Innenkontur und "
            "Wandstärke angenommen), Anbauteile schwerer als das Rohr. Zum Vergleich steht im Prüfdialog, was ohne "
            "Trennung gemessen worden wäre.",
            "In der 3D-Ansicht sind Anbauteile sandfarben, ihre Gravur türkis.",
            "Grenzen: Teile <b>im</b> Rohr (eingeschweißte Mutter innen, Stopfen) werden nicht abgetrennt, sondern "
            "wie bisher als Innenmerkmal gemeldet. Eine Kopfplatte genau so groß wie das Rohr ist vom Rohr nicht "
            "zu unterscheiden.")
    i.text("<b>Anbauteile prüfen</b>: Im Prüfdialog des STEP-Imports zeigt die Spalte <i>Anbauteile</i> je Teil, "
           "was abgetrennt wurde, z. B. <i>2 Bolzen, 1 Lasche</i>; gelb mit <i>– 1 prüfen</i>, solange ein unsicher "
           "erkanntes Anbauteil offen ist. Bei Teilen mit Anbauteilen hat die 3D-Ansicht drei Knöpfe: "
           "<b>Original</b> (Rohr mit Anbauteilen), <b>Rohrgeometrie</b> (nur was der Laser bearbeitet) und "
           "<b>Gravurkonturen</b> (Rohr mit allen Gravurlinien, ohne Schnittlinien). In der Auswahl <i>Art</i> "
           "steht neben dem Profil <i>– Anbauteile abgetrennt</i>; dort lässt sich auf die Messung "
           "<i>– ohne Trennung</i> umschalten, wenn die Trennung falsch ist.")
    i.bild("anbau_pruefen", "Prüfdialog mit einem Rohr mit Kopfplatte, Mutter und einer Lasche an der Ecke",
           hoehe=80 * mm, legende=[
               (1, "Spalte <b>Anbauteile</b>: gelb, solange ein unsicher erkanntes Anbauteil offen ist. "
                   "<b>Doppelklick</b> öffnet das Fenster <i>Anbauteile prüfen</i>."),
               (2, "Vorschau <b>Original</b>, <b>Rohrgeometrie</b> oder <b>Gravurkonturen</b>."),
               (3, "Messwerte mit den Anbauteilen und dem Vergleich ohne Trennung.")])
    i.text("Ein <b>Doppelklick</b> auf die Spalte <i>Anbauteile</i> öffnet das Fenster <b>Anbauteile prüfen</b>. "
           "Je Zeile stehen Nr., Art, Lage (z ab Ende A, Seite bzw. Winkel), Aufstand, Höhe, Bearbeitung, Gravur "
           "und Erkennung (<i>sicher</i> oder <i>prüfen</i>):")
    i.liste("<b>Art</b> ändern, wenn sie falsch erkannt ist; Bearbeitung und Gravur springen auf die Vorgabe der "
            "Art.",
            "<b>Bearbeitung</b>: <i>Umriss</i> (Umfang der Aufstandsfläche), <i>Positionsmarke</i> (Kreuz 2 × 10 mm "
            "= 20 mm), <i>Punktmarke</i> (Kreuz 2 × 2 mm = 4 mm) oder <i>keine</i>. Die <b>Gravur [mm]</b> ist von "
            "Hand änderbar.",
            "<b>Bestätigen</b> oder <b>Ausschließen</b> (keine Gravur, das Anbauteil bleibt in der Liste). "
            "<b>Alle bestätigen</b> bestätigt alle Zeilen.",
            "<b>Ist kein Anbauteil: Messung ohne Trennung verwenden</b>: Das Teil gilt so, wie es ohne Abtrennen "
            "gemessen wurde (wie die Umschaltung bei <i>Art</i>).",
            "<b>Übernehmen</b> ändert die Gravur des Teils um den Unterschied und gilt für alle gleichen Teile der "
            "Zeile. Sind alle unsicher erkannten Anbauteile entschieden, gilt die Erkennung als geprüft und das "
            "Teil wird angehakt. <b>Abbrechen</b> lässt alles, wie es war.")
    i.bild("anbau_dialog", "Fenster Anbauteile prüfen: die Lasche an der Ecke war als Sonstiges erkannt",
           hoehe=62 * mm, legende=[
               (1, "Je Anbauteil Art, Lage, Aufstand, Bearbeitung, Gravur, Erkennung und Bestätigen/Ausschließen."),
               (2, "<b>Alle bestätigen</b> setzt alle Zeilen auf bestätigt."),
               (3, "Trennung falsch: die Messung ohne Trennung verwenden."),
               (4, "Auswirkung je Teil: Gravur vorher → nachher und offene Anbauteile.")])
    i.bild("anbau_gravur", "Vorschau Gravurkonturen: Rohr ohne Anbauteile mit den Gravurlinien (türkis)",
           hoehe=55 * mm, legende=[(1, "Vorschau umschalten.")])
    i.text("<b>Im Angebot</b> stehen die Anbauteile in der Spalte <i>Anbauteile</i> der Positionen (erscheint, "
           "sobald eine Position welche hat). Solange ein unsicher erkanntes Anbauteil offen ist, zeigt der Status "
           "<b>HINWEIS: Anbauteile prüfen (Doppelklick)</b>, und der <i>Angebots-Check</i> meldet „Anbauteile "
           "ungeprüft“. Ein <b>Doppelklick</b> auf die Spalte oder den Status (oder Rechtsklick, <i>Anbauteile prüfen "
           "…</i>) öffnet dasselbe Fenster; <b>Übernehmen</b> ändert die Gravur der Position um den Unterschied.")
    i.bild("anbau_position", "Position mit Anbauteilen im Angebot: Spalte Anbauteile (hier alle geprüft)",
           hoehe=28 * mm)
    i.liste("<b>Gravur Anbauteile</b> ist ein Teil der Gravur und wird nicht doppelt gezählt: In den Spalten der "
            "Kalkulation steht <i>davon Gravur Anbauteile [s]</i>, im Preisaufbau bei <i>Laser schneiden</i> "
            "„davon Gravur Anbauteile … €“, in der Kalkulation-PDF die Spalte <i>davon Anbauteile [s]</i> und im "
            "Schneidweg-Rechner unter der Gravur „davon Anbauteile … mm“.",
            "<b>Prüfzeit</b>: Mit der Einstellung <i>Prüfzeit je Teil mit unsicher erkannten Anbauteilen [min]</i> "
            "(Vorgabe 0) kommt je Teil, dessen Anbauteile unsicher erkannt und nicht ausgeschlossen sind, diese Zeit "
            "zur Laserzeit. Sie steht als <i>Prüfzeit Anbauteile je Teil [s]</i> in der Kalkulation und im "
            "Preisaufbau bei <i>Laser schneiden</i>.",
            "Schweißen wird nicht kalkuliert.")
    i.hinweis("Eine STEP-Datei enthält nur Geometrie, keine Fertigungsmerkmale. Ob eine Fläche ein Schnitt ist, "
              "leitet die Messung daraus ab, ob sie auf dem Außen- oder Innenmantel liegt. Durchgehend ist ein "
              "Merkmal, wenn es bis zur Innenwand reicht. Kanten, die den Mantel nur in mehrere Flächen teilen, sind "
              "keine Kontur.")
    i.abschnitt("Messregeln")
    i.liste("Gerade Rohre mit konstantem Querschnitt (keine Biegeteile). Rund-, Quadrat- und Rechteckrohr werden "
            "erkannt, alles andere als Sonderprofil gemeldet.",
            "Teilelänge = größte Ausdehnung der Rohrwände entlang der Achse (bei Gehrung die lange Seite; "
            "Anbauteile wie Kopfplatten zählen nicht, [[anbauteile]]).",
            "Schneidweg = Anfangsschnitt + Endschnitt + Innenkonturen auf der Außenhaut. Gravuren (nicht durch die "
            "Wand) zählen getrennt.",
            "Innenkonturen, Anfangs- und Endschnitt werden nach ihrem Hüllmaß klein, mittel oder groß eingestuft "
            "(Grenzen je Maschine, Vorgabe 10 und 50 mm, zusätzlich 3 und 8 × Wandstärke; [[konturklassen]]); jede "
            "Klasse hat ihren eigenen Vorschub.",
            "Profilabgleich mit den Stammdaten über Form und Maße (±0,15 mm).")
    i.abschnitt("Einlesen: Einheiten, Flächenmodelle, defekte Dateien")
    i.liste("<b>Einheit</b>: Die Datei darf in mm, cm, m oder Zoll gespeichert sein; gemessen wird immer in mm. Die "
            "Einheit der Datei steht in den Messwerten.",
            "<b>Flächenmodell</b> (nur Flächen, kein Volumenkörper): Geschlossene Flächen werden zu einem Volumen "
            "zusammengenäht und gemessen, mit dem Hinweis <i>Flächenmodell: zu einem Volumen zusammengenäht</i>. "
            "Offene Flächen sind nicht messbar und stehen mit Hinweis im STEP-Protokoll, statt still zu fehlen.",
            "Jeder Körper wird mit der Geometrieprüfung von OpenCascade geprüft. Fällt er durch, steht der Hinweis "
            "<i>Geometrie laut Prüfung ungültig</i> dabei.",
            "Meldungen beim Lesen der Datei erscheinen als Hinweis <i>STEP-Leser meldet: …</i>. Eine defekte oder "
            "leere Datei erscheint im Protokoll als FEHLER <i>STEP-Datei nicht lesbar</i>.",
            "Zu jedem Körper stehen in den Messwerten zusätzlich Volumen, Oberfläche, Anzahl Flächen und Kanten und "
            "der Hüllquader in der Lage der Datei.")
    i.abschnitt("Geprüfte Fälle und bekannte Grenzen")
    i.text("Die Messung wird bei jeder Programmänderung mit Referenzteilen geprüft, deren Maße aus der Konstruktion "
           "bekannt sind: Rechteckrohr 60x40x2, Quadratrohr 40x40x2, Rundrohr 42,4x2, Rohr mit bekannten Bohrungen, "
           "Langloch und Ausschnitt, 45°-Gehrung, zweiachsiger Schrägschnitt, gedrehte und verschobene Teile, "
           "Baugruppe, defekte Datei, STEP-Varianten AP203/AP214/AP242, Zoll und Meter, CAD-Toleranzen "
           "(z. B. 60,02 statt 60) und Freiformflächen. Dazu Bleche: rechteckig, mit Bohrungen, mit Ausschnitt und "
           "Langloch, freie Kontur, gedreht, schräg liegend, mit Fase, kleines Reststück, gekantet, Baugruppe aus "
           "Rohr und Blechen, Abgrenzung zum Flachstahl und eine Platte mit Tasche als Gegenbeispiel. Maße stimmen "
           "dabei auf 0,01 mm, Winkel auf 0,1°.")
    i.text("Bekannte Grenzen:")
    i.liste("Rohre mit veränderlichem Querschnitt: keine Maße, Prüfstatus <i>nicht messbar</i>. Gebogene "
            "Rundrohre misst der Import als Biegerohr ([[biegerohre]]), gebogene Kastenprofile noch nicht.",
            "Rohre mit Sicke oder anderem nicht konvexem Querschnitt werden über ihr umschließendes Rechteck "
            "gemessen und stehen mit Prüfstatus <i>prüfen</i> da.",
            "Gewinde werden nur als Kernloch erkannt; der Gewindevorschlag ist von Hand zu prüfen.",
            "Bei U-, L-, C-Profilen und Flachstahl steht die Lage einer Kontur nur entlang der Achse, nicht ob sie "
            "im Steg oder im Flansch liegt. Vierkant- und Rundstahl sowie andere offene Profile (z. B. Z-Profil, "
            "<i>offenes Sonderprofil</i>) werden nur gemeldet, nicht übernommen.",
            "Träger mit geneigten Flanschen (IPN, UPN) werden an der Normmessstelle gemessen; der Schneidweg gilt "
            "für scharfkantige Flansche. Die Normtabelle bitte stichprobenartig mit der Lieferantentabelle "
            "vergleichen.",
            "Schräge Bohrungen werden über ihre Zylinderfläche erkannt; andere schräge Durchbrüche erscheinen als "
            "Ausschnitt.",
            "Flächenmodelle werden nur gemessen, wenn sie sich zu einem geschlossenen Körper vernähen lassen; "
            "lose Flächen daneben stehen als <i>Flächenmodell offen</i> im Protokoll.",
            "Gekantete Bleche: die Abwicklung ist eine Näherung ohne Biegefaktor; den Zuschnitt bitte prüfen.",
            "<i>plausibel</i> heißt: die Messung ist in sich stimmig. Es ist keine Fertigungsfreigabe.")


def kapitel_tastenkuerzel(i):
    i.kapitel("Anhang: Tastenkürzel, Doppelklick und Mausrad", marke="tastenkuerzel")
    i.text("Das Programm kennt die üblichen Windows-Tastenkürzel. Sie stehen auch in den Menüs <i>Bearbeiten</i> "
           "und <i>Ansicht</i> und unter <i>Hilfe → Tastenkürzel …</i>. Welche Seite ein Kürzel ausführt, richtet "
           "sich danach, wo der Cursor steht: Strg+N in der Angebotsliste legt ein Angebot an, im Angebot eine "
           "Position, in den Staffeln eine Stufe, in den Stammdaten eine Zeile. Rückgängig und Wiederholen sind in "
           "[[rueckgaengig]] beschrieben.")
    i.tabelle(["Taste", "Wirkung", "Wo"], [list(z) for z in TASTENKUERZEL], [28, 170, 67])
    i.text("In Textfeldern wirken Strg+Z, Strg+C, Strg+V, Strg+X und Entf wie gewohnt im Text. Gespeichert wird jede "
           "Eingabe sofort; Strg+S schließt nur eine offene Eingabe ab.")
    i.abschnitt("Doppelklick", marke="doppelklick")
    i.text("Ein Doppelklick führt meist direkt dorthin, wo etwas zu tun ist. Wo er einen Dialog öffnet, bearbeitet "
           "<b>Tippen</b> oder <b>F2</b> die Zelle weiterhin direkt. Der Tooltip (Maus kurz auf der Zelle lassen) "
           "sagt, was der Doppelklick macht.")
    i.tabelle(["Wo", "Doppelklick auf", "Wirkung"], [
        ["Angebot, Positionen", "Status", "führt zur Lösung: Bei <i>Schneidweg fehlt</i> oder einem Kontur-Hinweis "
                                          "öffnet sich der Schneidweg-Rechner, bei <i>EK fehlt</i> das EK-Fenster, "
                                          "bei <i>Zusatzarbeit unbekannt</i> die Auswahl, bei <i>Bohrungen prüfen</i> "
                                          "dieses Fenster, bei <i>nicht vollständig eingeplant</i> wird optimiert. Fehlt "
                                          "ein Wert (Länge, Stückzahl, Profil, Werkstoff, Meterpreis …), öffnet sich die "
                                          "passende Zelle zum Eintragen (ausgeblendete Spalten werden eingeblendet)."],
        ["Angebot, Positionen", "Schneidweg, Einstiche, STEP-Werte",
         "Schneidweg-Rechner der Position ([[schneidweg_rechner]])"],
        ["Angebot, Positionen", "kleines Bild vor der Artikelnummer",
         "Schneidweg-Rechner der Position ([[schneidweg_rechner]]), bei Blechteilen der Blech-Editor "
         "([[blech_editor]])"],
        ["Angebot, Positionen", "Artikelnummer neben dem STEP-Bild", "3D-Ansicht der Position (ohne STEP: Nummer "
                                                                     "bearbeiten)"],
        ["Angebot, Positionen", "Zusatzarbeiten, Zukaufteile, Schweißnaht",
         "Auswahl-Dialog ([[zusatzarbeiten_angebot]], [[zukauf_angebot]], [[schweissnaht]])"],
        ["Angebot, Positionen", "Gewinde geprüft, Bohrungen, Gewinde-Vorschlag",
         "Bohrungen prüfen ([[bohrungen_pruefen]])"],
        ["Angebot, Positionen", "jede andere Eingabezelle", "Zelle bearbeiten"],
        ["Angebot, Kopf", "Kundenname oder Kundennummer", "Kunde im Reiter Kunden"],
        ["Angebot, Schnittplan", "Teil in der unteren Liste", "springt zur Position"],
        ["Angebot, Stangenbild", "Teil im Balken", "springt zur Position"],
        ["Angebot, STEP-Protokoll", "Zeile", "springt zur Position mit derselben Pos.-Nummer"],
        ["Angebote", "Angebot", "öffnet das Angebot"],
        ["Kunden", "Kunde", "Reiter Angebote, gefiltert auf diesen Kunden"],
        ["Start", "zuletzt bearbeitetes Angebot", "öffnet das Angebot"],
    ], [38, 62, 165])


    i.abschnitt("Mausrad", marke="mausrad")
    i.text("Das Mausrad rollt immer die Seite, Tabelle oder Liste unter dem Mauszeiger. Über Zahlen- und "
           "Datumsfeldern, Auswahllisten und Schiebereglern verstellt es <b>keine Werte</b> – auch nicht, wenn der "
           "Cursor im Feld steht, und auch nicht in Dialogen oder in Tabellenzellen. So ändert sich beim Blättern "
           "nichts aus Versehen. Werte ändern Sie mit der Tastatur (Eintippen, Pfeiltasten ↑/↓) oder mit den "
           "kleinen Pfeilen am Feld; eine aufgeklappte Auswahlliste rollt wie gewohnt. In Skizzen und in der 3D-Ansicht "
           "zoomt das Rad weiterhin.")


def kapitel_lizenz(i):
    i.kapitel("Lizenz", marke="lizenz")
    i.text("Das Programm braucht eine Lizenz. Sie ist eine kleine Datei (<i>.lizenz</i>), die Patrick für einen "
           "Rechner ausstellt. Sie gilt ohne Internet und ohne Anmeldung. Ohne gültige Lizenz bleiben alle Angebote "
           "und Daten erhalten und lassen sich ansehen und exportieren, nur ändern geht dann nicht mehr.")
    i.bild("lizenz_dialog", "Hilfe → Lizenz …", hoehe=85 * mm, legende=[
        (1, "Zustand der Lizenz: gültig bis, läuft bald ab, abgelaufen oder Lesemodus"),
        (2, "<b>Rechner-ID</b> dieses Rechners"),
        (3, "<b>Kopieren</b>: Rechner-ID in die Zwischenablage"),
        (4, "<b>E-Mail an Patrick …</b>: fertige E-Mail mit der Rechner-ID"),
        (5, "<b>Lizenzdatei laden …</b>: erhaltene Datei übernehmen (oder auf das Fenster ziehen)")])
    i.abschnitt("Lizenz bekommen und laden", marke="lizenz_laden")
    i.liste("<b>Rechner-ID senden</b>: <i>Hilfe → Lizenz …</i>, <b>E-Mail an Patrick …</b> oder <b>Kopieren</b>.",
            "<b>Lizenzdatei erhalten</b>: Patrick schickt eine Datei wie <i>L-2026-0007_Musterbau_….lizenz</i>.",
            "<b>Laden</b>: <i>Hilfe → Lizenz …</i>, <b>Lizenzdatei laden …</b> oder die Datei auf das Fenster ziehen.",
            nummeriert=True, kurz=True)
    i.text("Das Programm prüft die Datei vor dem Übernehmen. Eine ungültige, abgelaufene oder für einen anderen "
           "Rechner ausgestellte Datei wird abgelehnt; die bisherige Lizenz bleibt dann, wie sie war.")
    i.genauer()
    i.liste("Eine <b>Benutzerlizenz</b> gilt in der Regel 3 Monate und für einen Rechner; danach schickt Patrick "
            "eine neue Datei. Für die portable Version "
            "auf einem USB-Stick an mehreren PCs gibt es Lizenzen für mehrere oder beliebige Rechner.",
            "Eine <b>Testlizenz</b> gilt kurz (meist 30 Tage). Alle PDFs tragen dann den Aufdruck <i>TESTVERSION</i>.",
            "Die <b>Admin-Lizenz</b> ist unbefristet. Beim Start fragt das Programm dann das <b>Admin-Passwort</b> "
            "ab, das ist das Passwort der Einstellungen ([[passwort]]); ist keins vergeben, entfällt die Frage. Mit "
            "richtigem Passwort öffnen sich die Einstellungen ohne weitere Abfrage. Nach <b>Abbrechen</b> oder dreimal "
            "falsch startet das Programm ohne Admin-Rechte, wie mit einer Benutzerlizenz: Einstellungen nur mit "
            "Passwort, gelber Hinweis unten rechts. <i>Hilfe → Lizenz …</i>, <b>Admin freischalten …</b> holt die "
            "Admin-Rechte ohne Neustart nach.",
            "<b>Gesperrte Lizenzen</b> erfährt ein Rechner bei der Suche nach Updates. Ein Rechner, der nie online "
            "ist, arbeitet bis zum Ablaufdatum seiner Lizenz weiter; deshalb sind die Laufzeiten kurz.",
            "Neuer PC oder Windows neu installiert: Die Rechner-ID ändert sich, es braucht eine neue Lizenz.",
            "Die Lizenz liegt im Datenordner im Unterordner <i>Lizenz</i>, nicht in der Datendatei. Sicherung, "
            "Wiederherstellen und Daten exportieren nehmen sie deshalb nicht mit auf einen anderen Rechner.",
            "<i>Hilfe → Über …</i> zeigt die Lizenz und die Rechner-ID ebenfalls.")
    i.abschnitt("Ablauf und Lesemodus", marke="lesemodus")
    i.tabelle(["Zustand", "Wann", "Programm"], [
        ["Gültig", "mehr als 30 Tage Restlaufzeit", "alles frei"],
        ["Läuft bald ab", "30 Tage oder weniger", "alles frei, gelber Hinweis unten rechts; ab 7 Tagen auch beim Start"],
        ["Kulanz", "bis 14 Tage nach Ablauf", "alles frei, roter Hinweis mit dem Datum des Lesemodus"],
        ["Lesemodus", "länger abgelaufen, keine oder falsche Lizenz, gesperrt, Uhr zurückgestellt",
         "nur ansehen, mit Begründung unten rechts"]], [28, 55, 95])
    i.text("Im <b>Lesemodus</b> lassen sich alle Angebote, Positionen, Kalkulationen und Stammdaten ansehen. Daten "
           "exportieren, Sicherungen anlegen und wiederherstellen, nach Updates suchen und eine Lizenz laden geht "
           "weiter. Gesperrt sind Anlegen, Ändern, Kopieren und Löschen, STEP-Import, Optimieren, PDFs, CSV und "
           "Materialanfrage. Daten werden nie gelöscht. Nach dem Laden einer gültigen Lizenz das Programm einmal neu "
           "starten, dann sind alle Knöpfe wieder frei.")
    i.genauer()
    i.liste("<b>Systemzeit prüfen</b>: Liegt das Datum des Rechners mehr als 2 Tage vor dem zuletzt gesehenen Datum, "
            "geht das Programm in den Lesemodus. Stimmt die Uhr wieder, ist alles normal.",
            "Beim Update-Check holt das Programm die Sperrliste mit. Eine gesperrte Lizenz (z. B. bei einem verlorenen "
            "Laptop) geht dann in den Lesemodus.",
            "Updates gehen auch mit abgelaufener Lizenz ([[updates]]).",
            "Einführung: Zuerst zeigt das Programm ohne Lizenz nur einen Hinweis (<i>Demnächst braucht das Programm "
            "eine Lizenz</i>) und sperrt nichts. Erst eine spätere Version schaltet den Lesemodus ein; bis dahin bitte "
            "die Rechner-ID an Patrick senden.")


def kapitel_fragen(i):
    i.kapitel("Anhang: Häufige Fragen und Meldungen", marke="fragen")
    i.tabelle(["Meldung / Frage", "Ursache und Abhilfe"], [
        ["Startseite rot: <i>Die Stammdaten sind Beispielwerte</i>",
         "Die Stammdaten wurden noch nicht bearbeitet. Eigene Werte im Reiter Einstellungen eintragen "
         "([[stammdaten]]); nach der ersten Änderung verschwindet der Hinweis."],
        ["Position mit <b>FEHLER: Profil fehlt</b> o. ä.",
         "Profil-ID oder Werkstoff-ID steht nicht in den Stammdaten oder ist falsch geschrieben. Aus der "
         "Auswahlliste wählen oder in den Stammdaten anlegen."],
        ["Teil unter <b>nicht eingeplante Teile</b>",
         "Teil länger als die Nutzlänge (Stange − Endbeschnitt − Greiferrest bzw. 3D-Greifmaß bei einer "
         "3D-Bearbeitung am Ende), Profil über max. Hüllkreis oder "
         "Metergewicht der Maschine, oder Pflichtangaben fehlen. Grund steht in der Auswertung."],
        ["Übersicht zeigt <b>Veraltet</b>", "Nach der letzten Optimierung wurde etwas geändert. Neu optimieren."],
        ["Kurze Meldung unten rechts, die von selbst verschwindet",
         "Hinweise und Erfolgsmeldungen (z. B. <i>CSV gespeichert</i>) erscheinen als Einblendung unten rechts und "
         "verschwinden nach einigen Sekunden; ein Klick schließt sie sofort. Verpasst? <b>Meldungen (N)</b> rechts "
         "in der Statusleiste zeigt die letzten 20 mit Uhrzeit (am Anfang: <i>Noch keine Meldungen</i>). Rückfragen vor dem Löschen und Fehler bleiben "
         "Fenster, die bestätigt werden müssen."],
        ["Meldung <b>Unerwarteter Fehler</b>", "Ein Programmfehler bei dieser Aktion. Gespeicherte Daten bleiben "
         "erhalten, das Programm läuft weiter. Die Details stehen in <i>Daten/Protokoll/fehler.log</i> im Datenordner "
         "(Datei → Datenordner öffnen); diese Datei zur Fehlersuche weitergeben."],
        ["Übersicht: <b>Preise festgeschrieben am …, Stammdaten seitdem geändert</b>",
         "Materialpreise, Schneiddaten, Gewinde, Einstellungen, Profile oder Maschine wurden nach dem Angebots-PDF "
         "geändert; das Angebot rechnet weiter mit den "
         "alten Werten. Gewollt? Dann nichts tun. Sonst <b>Aktuelle Preise übernehmen …</b> ([[preise_festschreiben]])."],
        ["Frachtkosten: <b>keiner Zone zugeordnet</b>", "Für die PLZ gibt es keine PLZ-Zuordnung. Mit Standardzone "
         "rechnet das Programm weiter (gelb), ohne nicht (rot). Zuordnung im Unterreiter Frachtzonen und "
         "Postleitzahlen ergänzen ([[frachtzonen]])."],
        ["Frachtkosten: <b>Tarif wählen</b> / <b>mehrdeutig</b>", "Mehrere Tarife oder PLZ-Regeln passen gleich gut. "
         "Tarif im Rechner von Hand wählen oder eine Priorität vergeben."],
        ["Frachtkosten: <b>individuelle Berechnung nötig</b>", "Die Menge liegt über der letzten Stufe oder die Stufe "
         "hat keinen Preis. Preis beim Frachtführer anfragen oder die Preisstaffel ergänzen."],
        ["Windows meldet einen <b>Virus</b> oder <b>„Der Computer wurde durch Windows geschützt“</b>",
         "Fehlalarm bei einem nicht signierten Programm. Abschnitt <i>Windows-Warnungen</i> ([[windows_warnungen]]): ZIP vor dem "
         "Entpacken zulassen, Trotzdem ausführen, Datei aus der Quarantäne wiederherstellen und an Microsoft "
         "melden."],
        ["<b>Das Update ist nicht gelungen</b>",
         "Eine Programmdatei ließ sich nicht austauschen, meist weil sie gerade offen ist (Bedienungsanleitung im "
         "PDF-Programm, laufender STEP-Import). Das Programm hat alles zurückgestellt. Datei schließen und "
         "<i>Hilfe → Nach Updates suchen …</i> noch einmal aufrufen."],
        ["<b>Keine Verbindung zum Update</b>",
         "Kein Internet, oder eine Firewall sperrt github.com. Bei einer Version vor 0.5.5 liegt es an der alten "
         "Update-Adresse ([[updates]]). Später noch einmal versuchen; sonst das Setup "
         "(installiert) bzw. das ZIP (portabel) von Hand holen und die Daten übernehmen."],
        ["<b>STEP-Import.exe wurde nicht gefunden</b>",
         "Der Ordner <i>STEP-Import</i> muss im Programmordner neben <i>Rohrlaser-Angebotskalkulation.exe</i> liegen. "
         "Setup neu installieren bzw. neu aus dem ZIP entpacken."],
        ["STEP: <b>Erkennung unsicher</b> oder <b>kein Rohrteil erkannt</b>",
         "Die Messung konnte Achse oder Querschnitt nicht eindeutig bestimmen und übernimmt bewusst keine Maße. "
         "Modell im CAD prüfen (ein Volumenkörper je Rohr, konstanter Querschnitt) oder die Position von Hand "
         "anlegen."],
        ["STEP: <b>Profil fehlt in den Stammdaten</b>",
         "Mit Ja aus den Messwerten anlegen lassen, danach unter Einstellungen, Profile prüfen (Bemerkung, Preis)."],
        ["Gewinde wird nicht gerechnet", "Nur bestätigte Gewinde (<b>Gewinde geprüft</b>) zählen, nicht der "
                                         "Vorschlag. Doppelklick auf die Position: Bohrungen prüfen."],
        ["<b>WARNUNG: Zusatzarbeit … unbekannt</b>",
         "Die Zusatzarbeit wurde in den Stammdaten umbenannt oder gelöscht. Über <i>Zusatzarbeiten …</i> neu wählen."],
        ["<b>HINWEIS: Schneidzeit manuell</b>",
         "Für die Position ist eine Schneidzeit von Hand eingetragen; sie ersetzt die berechnete Zeit."],
        ["<b>HINWEIS: Meterpreis manuell</b>",
         "Für die Position ist ein Materialpreis je m von Hand eingetragen; er ersetzt den berechneten Preis "
         "([[meterpreis]])."],
        ["<b>WARNUNG: Konturen klein + mittel länger als Schneidweg</b>",
         "Der Schneidweg wurde von Hand kleiner eingetragen als die kleinen und mittleren Konturen zusammen. Der "
         "Anteil mit Vorschub groß wird mit 0 gerechnet. Schneidweg oder die Spalten Kontur klein/mittel [mm] "
         "prüfen."],
        ["<b>WARNUNG: Konturklassen länger als Innenkonturen + Anfangs-/Endschnitt</b>",
         "Kontur klein + mittel + groß [mm] ist größer als Innenkonturen + Anfangs- + Endschnitt [mm] (z. B. eine "
         "Spalte von Hand geändert). Die STEP-Werte der Position prüfen."],
        ["Zusatzarbeit kostet mehr als Menge × Preis",
         "Der Mindestbetrag je Angebot greift; er wird auf alle Teile mit dieser Zusatzarbeit verteilt."],
        ["<b>FEHLER: Oberfläche unbekannt</b>",
         "Die Oberfläche der Position steht nicht in den Stammdaten Oberflächen. Aus der Auswahl wählen oder anlegen."],
        ["<b>WARNUNG: Oberfläche … ist für …</b>",
         "Die Oberfläche passt laut Stammdaten nicht zur Kategorie des Werkstoffs, z. B. K240 bei Stahl. Gerechnet "
         "wird trotzdem; Oberfläche oder Werkstoff prüfen."],
        ["<b>HINWEIS: keine Schneiddaten</b>",
         "Weder der Werkstoff noch seine Kategorie hat für Maschine und Wandstärke eine Zeile in den Schneiddaten. "
         "Kategorie beim Werkstoff eintragen oder Schneiddaten ergänzen."],
        ["<b>WARNUNG: kein gültiger Materialpreis</b>", "Weder Preis noch Tonnenpreis für Profil + Werkstoff "
                                                        "hinterlegt. Unter Einstellungen Preise oder Werkstoffe ergänzen."],
        ["<b>WARNUNG: Stückzahl ist kein Vielfaches von Stück je Satz</b>",
         "Stückzahl und Stück je Satz der Position passen nicht zusammen (z. B. 7 Teile bei 2 je Satz)."],
        ["<b>WARNUNG: Satz … unterschiedliche Anzahl Sätze</b>",
         "Die Positionen eines Satzes ergeben verschieden viele Sätze (z. B. 10 Stiele, aber 6 Riegel bei je 1 "
         "Stück je Satz). Das Angebots-PDF rechnet den Satz mit der größten Anzahl, die Kalkulation mit den "
         "Stückzahlen; Stückzahlen angleichen. Vor dem PDF fragt das Programm nach."],
        ["<b>WARNUNG: Gewinde '…' nicht erkannt</b>",
         "Die Angabe in <i>Gewinde geprüft</i> hat kein lesbares Format (Anzahl x Gewinde, ganze Zahl) oder das "
         "Gewinde steht nicht in den Stammdaten Gewinde. Sie wird nicht gerechnet. Korrigieren, z. B. "
         "<i>4xM6; 2xM8</i>."],
        ["<b>FEHLER: … darf nicht negativ sein</b>",
         "Ein Zahlenwert der Position ist negativ (z. B. aus einer geänderten Datei). Wert korrigieren; Text in "
         "Zahlenfeldern lehnt das Programm ab, aus einer Datei gelesen gilt er als leer."],
        ["Preise sind höher als vor dem Update",
         "Neue Angebote rechnen das Skonto ein (Vorgabe 2 %). Im Angebotskopf Skonto 0 eintragen oder in den "
         "Einstellungen bzw. beim Kunden die Vorgabe ändern."],
        ["Beim Beenden: <b>Sicherung nicht vollständig</b>",
         "Der zweite Sicherungsordner ist nicht erreichbar (Netzlaufwerk getrennt, USB-Stick fehlt). Die Sicherung "
         "im Datenordner ist angelegt; Ordner verbinden und <i>Datensicherung erstellen</i> wählen."],
        ["Ablageordner lässt sich nicht öffnen", "Pfad in den Einstellungen prüfen (Netzlaufwerk verbunden?). Leer "
                                                 "lassen = Vorgabe (portabel Ordner Angebote neben dem Programm, "
                                                 "installiert Dokumente\\Rohrlaser Angebote)."],
        ["Daten versehentlich gelöscht oder Datendatei beschädigt",
         "<i>Sicherung wiederherstellen …</i> (Startseite oder Menü Datei) und einen Stand vor dem Fehler wählen "
         "([[datensicherung]]). Startet das Programm wegen einer beschädigten Datei nicht, bietet "
         "es das Wiederherstellen beim Start an."],
        ["<b>Die Datendatei … ist schon in einem anderen Programm geöffnet</b>",
         "Ein zweites Programm (die andere Version, ein zweites Fenster oder ein anderer Rechner) arbeitet mit "
         "derselben Datendatei. Dort beenden. Nach einem Absturz verschwindet die Sperre von selbst."],
        ["Nach dem Installieren sind die <b>Angebote weg</b>",
         "Die installierte Version hat ihre Daten im Benutzerprofil, die portable im Ordner Daten neben dem "
         "Programm. In der installierten Version <i>Datei → Daten importieren …</i> und die Datei "
         "<i>Daten\\rohrlaser.db</i> der portablen Version wählen."],
        ["<b>Sicherung … stammt von einer neueren Programmversion</b>",
         "Die Datei wurde schon mit einer neueren Version bearbeitet. Erst das Programm aktualisieren "
         "(<i>Hilfe → Nach Updates suchen …</i>), dann wiederherstellen bzw. importieren."]], [85, 180])


def kapitel_neu(i):
    i.kapitel("Anhang: Was ist neu", marke="neu")
    i.text(f"Die wichtigsten Neuerungen der letzten {IN_ANLEITUNG} Versionen, neueste zuerst. Alle Versionen mit "
           "allen Einzelheiten zeigt das Programm unter <b>Hilfe → Was ist neu …</b>; die installierte Version steht "
           "unter <i>Hilfe → Über …</i>.")
    i.tabelle(["Version", "Neu"], [[v, kurz] for v, _, kurz in NEUERUNGEN[:IN_ANLEITUNG]], [30, 235])


# ---------------------------------------------------------------- Ablauf
def bilder_erzeugen(ordner):
    umgebung = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR="2")
    subprocess.run([sys.executable, str(HIER / "bilder.py"), str(ordner)], check=True, env=umgebung)


# Bildschirmfotos, die bilder.py mit erzeugt, die aber bewusst nicht in der Anleitung stehen
OHNE_STELLE = {"stamm_stundensaetze",     # gleiche Seite wie stamm_arbeitsschritte
               # Schweiß-Stammdaten: Bild der Kennwerte steht für alle drei Unterreiter
               "stamm_schweissverfahren", "stamm_schweiss_faktoren"}


def kapitel_schnellstart(i):
    i.kapitel("Schnellstart: das erste Angebot in 10 Schritten", marke="schnellstart")
    i.text("Für das erste Angebot reichen die fett gedruckten Handgriffe; die Verweise führen zu den Einzelheiten.",
           kurz=True)
    i.schritte([
        ("angebote", "Reiter <i>Angebote</i> → <b>Neues Angebot</b> (Strg+N) ([[angebote]])", (0, 0, 0.42, 0.28)),
        ("angebot_positionen", "<b>Kunde</b> wählen; Maschine, Stangenlänge, Lieferzeit sind vorbelegt "
                               "([[angebotskopf]])", (0, 0.05, 0.62, 0.34)),
        ("step_pruefen", "<b>STEP importieren …</b> (Strg+I) oder Dateien ins Fenster ziehen, Werkstoff und Stückzahl "
                         "prüfen, <b>Übernehmen</b> ([[step]])", (0, 0, 0.6, 0.55)),
        ("angebot_positionen", "… oder von Hand: <b>Neue Position</b>, dann Profil, Werkstoff, Länge, Stückzahl in "
                               "die gelben Felder ([[positionen]])", (0, 0.44, 0.45, 0.78)),
        ("zusatz_dialog", "Position markieren → <b>Zusatzarbeiten …</b>: Gewinde, Verzinken, Pulvern "
                          "([[zusatzarbeiten_angebot]])", (0, 0, 0.75, 0.62)),
        ("zukauf_schnell", "Schrauben, Bleche u. Ä.: <b>Zukaufteile …</b> ([[zukauf_im_angebot]])"),
        ("angebot_optimiert", "<b>Optimieren</b> (F9). Grün = fertig; rote FEHLER zuerst beheben ([[optimieren]])",
         (0.79, 0.03, 1, 0.62)),
        ("erg_stangenbild", "Ergebnis ansehen: Kalkulation, Schnittplan, <b>Stangenbild</b> ([[kalkulation]])",
         (0, 0, 0.5, 0.62)),
        ("staffeln", "Reiter <i>Staffeln</i> für weitere Mengen; Karte <b>Fracht</b> ([[staffeln]], [[fracht]])",
         (0, 0, 0.8, 0.75)),
        ("pdf_angebot_1", "<b>Angebot (PDF)</b> (Strg+P). Bei Auftrag <b>Werkstattpapiere (PDF)</b>, danach "
                          "Nachkalkulation ([[ausgabe]], [[nachkalkulation]])")], spalten=4, hoehe=50 * mm)
    i.hinweis("Jede Eingabe wird sofort gespeichert. Strg+Z nimmt im Angebot die letzte Änderung zurück "
              "([[rueckgaengig]]).", titel="Gut zu wissen", kurz=True)
    i.hinweis("Vor dem ersten echten Angebot die Beispielwerte durch die eigenen ersetzen: Preise, Maschinen, "
              "Schneiddaten, Stundensätze, Briefkopf und Zuschläge ([[einstellungen]], [[stammdaten]]).",
              titel="Vorher einmal", kurz=True)


# Je Kapitel (Marke): wofür es da ist und wo es im Programm steht. Erscheint als Kasten unter der Überschrift und
# auf der Trennseite des Teils; test_anleitung.py prüft, dass jedes Kapitel einen Eintrag hat.
STECKBRIEFE = {
    "ueberblick": ("Was das Programm kann, wie ein Angebot abläuft und was die Farben bedeuten.",
                   "Hauptfenster mit den Reitern Start, Angebote, Kunden, Frachtkosten, Zukaufartikel, Einstellungen"),
    "start": ("Programm installieren oder portabel entpacken, Windows-Warnungen, erster Start.",
              "Release <i>aktuell</i> auf GitHub; im Programm der Reiter <i>Start</i>"),
    "schnellstart": ("Einmal durch ein ganzes Angebot, vom Anlegen bis zum PDF.",
                     "Reiter <i>Angebote</i> und das geöffnete Angebot"),
    "angebote": ("Angebote finden, öffnen, kopieren und löschen.", "Reiter <i>Angebote</i>"),
    "angebot": ("Kopf, Positionen, Zusatzarbeiten und Einzelwerte eines Angebots eingeben.",
                "Geöffnetes Angebot: Kopf, Übersicht, Reiter <i>Positionen</i>"),
    "step": ("Positionen aus Konstruktionsdaten (.step/.stp) einlesen, auch Bleche und Baugruppen.",
             "Im Angebot <b>STEP importieren …</b> (Strg+I) oder Dateien ins Fenster ziehen"),
    "optimieren": ("Teile auf Stangen verteilen, Kalkulation, Zeiten, Schnittplan und Lieferlängen prüfen.",
                   "Im Angebot <b>Optimieren</b> (F9); Reiter Kalkulation, Zeiten, Schnittplan, Stangenbild, "
                   "Auswertung"),
    "staffeln": ("Preise für weitere Mengen, je Stufe mit eigenen Zuschlägen.", "Im Angebot Reiter <i>Staffeln</i>"),
    "fracht": ("Frachtkosten ins Angebot bringen: manuell, berechnet oder automatisch.",
               "Im Angebot Karte <b>Fracht</b>; Reiter <i>Frachtkosten</i> → Frachtrechner"),
    "zukauf_im_angebot": ("Eingekaufte Teile als eigene Position oder an einer Position mitkalkulieren.",
                          "Im Angebot <b>Zukaufteile …</b> bzw. <b>Ausgaben</b>"),
    "schweissbaugruppe": ("Einzelteile zu einer Schweißbaugruppe zusammenfassen und Schweißen, Arbeitsgänge und "
                          "Vorrichtungen dazurechnen.",
                          "<b>Neue Position</b> → <b>Schweißbaugruppe</b>; Doppelklick auf die Baugruppe"),
    "ausgabe": ("Angebot, Werkstattpapiere und Kalkulation als PDF, CSV, Materialanfrage.",
                "Im Angebot die Knöpfe rechts neben <b>Ausgabe</b>"),
    "nachkalkulation": ("Nach dem Auftrag Ist-Werte eintragen und mit der Kalkulation vergleichen.",
                        "Im Angebot Reiter <i>Nachkalkulation</i>"),
    "einstellungen": ("Zuschläge, Briefkopf, Ablage, Vorgaben für neue Angebote, Stundensätze.",
                      "Reiter <i>Einstellungen</i> (Passwort) → <i>Vorgaben</i>"),
    "stammdaten": ("Kunden (auch per CSV), Profile, Werkstoffe, Preise, Maschinen, Schneiddaten und weitere Tabellen "
                   "pflegen.",
                   "Reiter <i>Kunden</i>; Reiter <i>Einstellungen</i> mit den Unterreitern"),
    "zukauf": ("Zukaufartikel, Lieferanten, Einkaufspreise und Aufschläge verwalten.", "Reiter <i>Zukaufartikel</i>"),
    "frachtkosten": ("Frachtzonen, Tarife, Ladehilfsmittel und Zuschläge pflegen, Fracht kalkulieren.",
                     "Reiter <i>Frachtkosten</i>"),
    "mehrere_arbeitsplaetze": ("Kürzel als Bearbeiter, gemeinsamer Nummernkreis 2026-00001; Angebote und Stammdaten "
                               "mit den Kollegen über einen gemeinsamen Ordner teilen.",
                               "<i>Datei → Benutzer und gemeinsamer Ordner …</i>; Knopf <i>Abgleichen</i> im Reiter "
                               "Angebote"),
    "pflege": ("Updates einspielen, Daten sichern, wiederherstellen und umziehen.",
               "<i>Hilfe → Nach Updates suchen …</i>; Reiter <i>Start</i>"),
    "lizenz": ("Lizenz bekommen und laden, Ablauf, Lesemodus.",
               "<i>Hilfe → Lizenz …</i>; Hinweis unten rechts in der Statusleiste"),
    "step_messung": ("Für Fachleute: wie die STEP-Messung Rohr, Schnitte und Konturen erkennt.",
                     "<i>STEP-Import.exe</i> im Programmordner"),
    "tastenkuerzel": ("Alle Tastenkürzel und Doppelklicks auf einen Blick, dazu das Mausrad.", "<i>Hilfe → Tastenkürzel …</i>"),
    "fragen": ("Meldungen des Programms und was dagegen hilft.", "Statuszeile und Meldungsfenster"),
    "neu": ("Die wichtigsten Neuerungen der letzten Versionen.",
            "<i>Hilfe → Was ist neu …</i> zeigt alle Versionen, <i>Hilfe → Über …</i> die installierte"),
}

# Teile der Anleitung: Buchstabe, Titel, ein Satz dazu, Kapitel in der Reihenfolge der Arbeit.
# Ein neues Kapitel hier an der passenden Stelle einsortieren und in STECKBRIEFE eintragen.
TEILE = [
    ("A", "Erste Schritte", "Installieren, das Fenster kennenlernen und einmal ein ganzes Angebot rechnen.",
     [kapitel_ueberblick, kapitel_start, kapitel_schnellstart]),
    ("B", "Ein Angebot rechnen", "Alle Schritte eines Angebots in der Reihenfolge der Arbeit, vom Anlegen bis zur "
     "Nachkalkulation.",
     [kapitel_angebote, kapitel_angebot, kapitel_step, kapitel_optimieren, kapitel_staffeln,
      kapitel_fracht, kapitel_zukauf_angebot, kapitel_baugruppen, kapitel_ausgabe, kapitel_nachkalkulation]),
    ("C", "Einrichten und pflegen", "Was einmal eingerichtet und ab und zu gepflegt wird: Einstellungen, "
     "Stammdaten, Zukaufartikel, Frachtkosten, Updates, Datensicherung und Lizenz.",
     [kapitel_einstellungen, kapitel_mehrere, kapitel_stammdaten, kapitel_zukauf, kapitel_frachtkosten,
      kapitel_pflege, kapitel_lizenz]),
    ("Anhang", "Nachschlagen", "STEP-Messung im Detail, Tastenkürzel, häufige Fragen und die Neuerungen je "
     "Version.",
     [kapitel_step_messung, kapitel_tastenkuerzel, kapitel_fragen, kapitel_neu]),
]


def inhalt_sammeln(daten, bilder, vorlauf=None, kurz=False):
    stand = datetime.date.today().strftime("%d.%m.%Y")
    inh = Inhalt(bilder, vorlauf, kurz)
    titelseite(inh, stand)
    for buchstabe, name, text, kapitel_liste in (TEILE[:3] if kurz else TEILE):     # Kurzanleitung: ohne Anhang
        inh.teil(buchstabe, name, text)
        for kapitel in kapitel_liste:
            if kapitel is kapitel_ausgabe:
                kapitel(inh, daten["seiten"], daten["ablage"])
            else:
                kapitel(inh)
    return inh


def pdf_bauen(bilder_ordner, ziel, kurz_ziel=None):
    """Bedienungsanleitung nach ziel, Kurzanleitung (Teil A bis C, nur Bilder, Schritte und Legenden) nach kurz_ziel."""
    daten = json.loads((Path(bilder_ordner) / "bilder.json").read_text(encoding="utf-8"))
    bilder = dict(daten["bilder"], _ordner=Path(bilder_ordner))
    # 1. Durchlauf: Kapitelnummern der Marken, 2. Durchlauf: Verweise einsetzen
    vorlauf = inhalt_sammeln(daten, bilder)
    inh = inhalt_sammeln(daten, bilder, vorlauf)
    ungenutzt = sorted(n for n in set(daten["bilder"]) - inh.benutzte_bilder - OHNE_STELLE
                       if not n.startswith("pdf_"))      # Seitenbilder der PDF-Ausgaben: nur einzelne Seiten gezeigt
    if ungenutzt:
        raise ValueError("Bildschirmfotos ohne Stelle in der Anleitung (bilder.py erzeugt sie umsonst): "
                         + ", ".join(ungenutzt))
    stand = datetime.date.today().strftime("%d.%m.%Y")
    doc = Anleitung(ziel)
    doc.stand = stand
    doc.multiBuild(inh.f)
    if kurz_ziel:
        kurz = Anleitung(kurz_ziel, "Kurzanleitung")
        kurz.stand = stand
        kurz.multiBuild(inhalt_sammeln(daten, bilder, vorlauf, kurz=True).f)
    return ziel


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ziel", default=str(HIER / "Bedienungsanleitung.pdf"))
    ap.add_argument("--kurz", help="Kurzanleitung.pdf (Vorgabe: neben --ziel)")
    ap.add_argument("--bilder", help="vorhandene Bilder verwenden (Ordner mit bilder.json)")
    a = ap.parse_args()
    kurz = a.kurz or str(Path(a.ziel).with_name("Kurzanleitung.pdf"))
    if a.bilder:
        ziel = pdf_bauen(a.bilder, a.ziel, kurz)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            bilder_erzeugen(tmp)
            ziel = pdf_bauen(tmp, a.ziel, kurz)
    for datei in (ziel, kurz):
        print(f"{datei}: {Path(datei).stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
