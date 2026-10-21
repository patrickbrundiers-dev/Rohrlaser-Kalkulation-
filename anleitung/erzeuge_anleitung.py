"""Erzeugt anleitung/Bedienungsanleitung.pdf: bebilderte Bedienungsanleitung des Programms.

Die Bilder kommen aus dem echten Programm (anleitung/bilder.py, unsichtbar mit Beispieldaten), der Text
steht unten in KAPITEL. Nach Änderungen am Programm einfach neu erzeugen:

    python anleitung/erzeuge_anleitung.py [--ziel DATEI.pdf] [--bilder ORDNER]

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
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import NAME, VERSION  # noqa: E402

SEITE = landscape(A4)
RAND = 14 * mm
BREITE = SEITE[0] - 2 * RAND
BLAU = colors.HexColor("#1F4E78")
HELLBLAU = colors.HexColor("#DDEBF7")
ROT = colors.HexColor("#D0021B")
GRAU = colors.HexColor("#595959")

S = ParagraphStyle("text", fontName="Helvetica", fontSize=10, leading=13.5, spaceAfter=4)
S_LISTE = ParagraphStyle("liste", parent=S, leftIndent=12, bulletIndent=2, spaceAfter=2)
S_H1 = ParagraphStyle("h1", parent=S, fontName="Helvetica-Bold", fontSize=18, leading=22, textColor=BLAU,
                      spaceBefore=0, spaceAfter=8)
S_H2 = ParagraphStyle("h2", parent=S, fontName="Helvetica-Bold", fontSize=12.5, leading=16, textColor=BLAU,
                      spaceBefore=8, spaceAfter=4)
S_BILD = ParagraphStyle("bild", parent=S, fontSize=8.5, leading=10.5, textColor=GRAU, alignment=TA_CENTER,
                        spaceBefore=2, spaceAfter=8)
S_LEGENDE = ParagraphStyle("legende", parent=S, fontSize=9.5, leading=12.5, spaceAfter=0)
S_TIPP = ParagraphStyle("tipp", parent=S, fontSize=9.5, leading=12.5, spaceAfter=0)
S_TOC1 = ParagraphStyle("toc1", parent=S, fontName="Helvetica-Bold", fontSize=11, leading=16, leftIndent=0)
S_TOC2 = ParagraphStyle("toc2", parent=S, fontSize=10, leading=13, leftIndent=16)


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
            c.setStrokeColor(colors.HexColor("#A6A6A6"))
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
    def __init__(self, ziel):
        super().__init__(str(ziel), pagesize=SEITE, leftMargin=RAND, rightMargin=RAND, topMargin=RAND,
                         bottomMargin=RAND + 4 * mm, title=f"{NAME} – Bedienungsanleitung",
                         author=NAME, subject=f"Bedienungsanleitung Version {VERSION}")
        rahmen = Frame(RAND, RAND + 4 * mm, BREITE, SEITE[1] - 2 * RAND - 4 * mm, id="text",
                       leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        self.addPageTemplates([PageTemplate("titel", [rahmen]),
                               PageTemplate("normal", [rahmen], onPageEnd=self._fuss)])
        self._kapitel = ""

    def beforeDocument(self):
        self._kapitel = ""     # multiBuild läuft mehrmals; sonst stünde das letzte Kapitel im Fuß des Inhaltsverzeichnisses

    def _fuss(self, c, doc):
        c.saveState()
        c.setStrokeColor(colors.HexColor("#BFBFBF"))
        c.line(RAND, RAND + 1 * mm, SEITE[0] - RAND, RAND + 1 * mm)
        c.setFont("Helvetica", 8)
        c.setFillColor(GRAU)
        c.drawString(RAND, RAND - 3 * mm, f"{NAME} {VERSION} – Bedienungsanleitung")
        c.drawCentredString(SEITE[0] / 2, RAND - 3 * mm, self._kapitel)
        c.drawRightString(SEITE[0] - RAND, RAND - 3 * mm, f"Seite {doc.page}")
        c.restoreState()

    def afterFlowable(self, f):
        if isinstance(f, BildBlock):
            for x in f.oben:
                self.afterFlowable(x)
            return
        if isinstance(f, Paragraph) and f.style.name in ("h1", "h2"):
            text = f.getPlainText()
            stufe = 0 if f.style.name == "h1" else 1
            if stufe == 0:
                self._kapitel = text
            schluessel = f"k{id(f)}"
            self.canv.bookmarkPage(schluessel)
            self.canv.addOutlineEntry(text, schluessel, level=stufe, closed=stufe == 0)
            self.notify("TOCEntry", (stufe, text, self.page, schluessel))


class Inhalt:
    """Sammelt die Flowables; Kurzformen für Text, Listen, Bilder, Legenden und Hinweise.

    Verweise stehen im Text als [[marke]] und werden zu „Kapitel 6.7“ mit Link auf die Überschrift, die mit
    marke="…" angelegt ist. Die Nummern kennt erst ein vollständiger Durchlauf: pdf_bauen sammelt sie im
    ersten Durchlauf (marken=None) und setzt sie im zweiten ein; eine unbekannte Marke ist dann ein Fehler."""

    VERWEIS = re.compile(r"\[\[([a-z0-9_]+)\]\]")

    def __init__(self, bilder, marken=None):
        self.bilder, self.f, self.kapitel_nr, self.abschnitt_nr = bilder, [], 0, 0
        self.marken, self.verweise = marken, {}
        self.neue_marken, self.benutzte_bilder = {}, set()

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
            return f'<a href="#{m.group(1)}" color="#1F4E78">Kapitel {self.marken[m.group(1)]}</a>'
        return self.VERWEIS.sub(ersetzen, str(text))

    def kapitel(self, titel, marke=None):
        self.kapitel_nr += 1
        self.abschnitt_nr = 0
        if self.f:
            self.f.append(PageBreak())
        anker = self._marke(marke, f"{self.kapitel_nr}")
        self.f.append(Paragraph(f"{anker}{self.kapitel_nr}&nbsp;&nbsp;{titel}", S_H1))

    def abschnitt(self, titel, marke=None):
        self.abschnitt_nr += 1
        self.f.append(CondPageBreak(45 * mm))
        anker = self._marke(marke, f"{self.kapitel_nr}.{self.abschnitt_nr}")
        self.f.append(Paragraph(f"{anker}{self.kapitel_nr}.{self.abschnitt_nr}&nbsp;&nbsp;{titel}", S_H2))

    def text(self, *absaetze):
        self.f.extend(Paragraph(self._t(a), S) for a in absaetze)

    def liste(self, *punkte, nummeriert=False):
        for i, p in enumerate(punkte, 1):
            self.f.append(Paragraph(self._t(p), S_LISTE, bulletText=f"{i}." if nummeriert else "•"))
        self.f.append(Spacer(1, 3))

    def bild(self, name, unterschrift="", hoehe=125 * mm, legende=()):
        self.bilder_nebeneinander([name], unterschrift, hoehe, legende)

    def bilder_nebeneinander(self, namen, unterschrift="", hoehe=125 * mm, legende=()):
        self.benutzte_bilder.update(namen)
        pfade = [self.bilder["_ordner"] / self.bilder[n]["datei"] for n in namen]
        oben = [self.f.pop()] if self.f and isinstance(self.f[-1], Paragraph) and self.f[-1].style.name == "h2" else []
        unten = ([Paragraph(self._t(unterschrift), S_BILD)] if unterschrift else []) + ([self._legende(legende)] if legende else [])
        self.f.append(BildBlock(pfade, hoehe, oben, unten))

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

    def hinweis(self, text, titel="Hinweis"):
        t = Table([[Paragraph(self._t(f"<b>{titel}:</b> {text}"), S_TIPP)]], colWidths=[BREITE])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HELLBLAU),
                               ("LINEBEFORE", (0, 0), (0, -1), 3, BLAU),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        self.f.extend([Spacer(1, 3), t, Spacer(1, 6)])

    def tabelle(self, kopf, zeilen, breiten):
        daten = [[Paragraph(f"<b>{k}</b>", S_LEGENDE) for k in kopf]]
        daten += [[Paragraph(self._t(z), S_LEGENDE) for z in zeile] for zeile in zeilen]
        t = Table(daten, colWidths=[b * mm for b in breiten], repeatRows=1)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), HELLBLAU),
                               ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BFBFBF")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        self.f.extend([t, Spacer(1, 6)])


# ---------------------------------------------------------------- Inhalt der Anleitung
def titelseite(inh, stand):
    f = inh.f
    f.append(Spacer(1, 22 * mm))
    f.append(Paragraph(NAME, ParagraphStyle("t1", parent=S_H1, fontSize=30, leading=36)))
    f.append(Paragraph("Bedienungsanleitung", ParagraphStyle("t2", parent=S_H1, fontSize=20, leading=26,
                                                              textColor=GRAU)))
    f.append(Spacer(1, 4 * mm))
    f.append(Paragraph(f"Angebotskalkulation und Materialoptimierung für Rohrlaserteile<br/>Programmversion {VERSION} · "
                       f"Stand {stand}", S))
    f.append(Spacer(1, 8 * mm))
    inh.bild("erg_stangenbild", hoehe=95 * mm)
    f.append(Spacer(1, 4 * mm))
    f.append(Paragraph("Alle Bildschirmfotos stammen aus dem Programm selbst. Firmen, Kunden, Angebote und Preise sind "
                       "Beispielwerte.", ParagraphStyle("klein", parent=S, fontSize=8.5, textColor=GRAU)))
    from reportlab.platypus.doctemplate import NextPageTemplate
    f.append(NextPageTemplate("normal"))
    f.append(PageBreak())
    f.append(Paragraph("Inhalt", ParagraphStyle("inhalt", parent=S_H1)))
    toc = TableOfContents()
    toc.levelStyles = [S_TOC1, S_TOC2]
    toc.dotsMinLevel = 0
    f.append(toc)


def kapitel_ueberblick(i):
    i.kapitel("Überblick", marke="ueberblick")
    i.text("Die Rohrlaser Angebotskalkulation plant für ein Angebot, wie die Teile aus Stangen geschnitten werden, und "
           "rechnet daraus Materialbedarf, Laserzeit und Angebotspreis. Alles liegt in einer Datendatei. Das Programm "
           "gibt es zum Installieren (für den eigenen Benutzer, ohne Administratorrechte) und als portable Version "
           "ohne Installation; beide rechnen gleich ([[start]]).",
           "Der normale Arbeitsablauf für ein Angebot:")
    i.liste("<b>Angebot anlegen</b> (Reiter <i>Angebote</i> → <i>Neues Angebot</i>) und den Kopf ausfüllen: Kunde, "
            "Maschine, Stangenlänge.",
            "<b>Positionen erfassen</b>: von Hand eintippen oder Konstruktionsdaten per <i>STEP importieren</i> "
            "einlesen (Länge, Profil, Schneidweg, Einstiche, Gewinde-Vorschlag).",
            "<b>Zusatzarbeiten</b> wählen, wo nötig: Gewinde, Verzinken, Pulverbeschichten, Gravur extra u. a.",
            "<b>Optimieren</b>: das Programm verteilt die Teile auf möglichst wenige Stangen und rechnet die "
            "Kalkulation.",
            "<b>Ergebnis prüfen</b>: Schnittplan, Stangenbild, Auswertung, nicht eingeplante Teile.",
            "Bei Bedarf <b>Staffelpreise</b> für weitere Mengen rechnen.",
            "<b>Ausgeben</b>: Angebot, Werkstattpapiere und Kalkulation als PDF, auf Wunsch CSV-Export.",
            nummeriert=True)
    i.text("Die Stammdaten (Profile, Werkstoffe, Oberflächen, Preise, Lieferlängen, Maschinen, Schneiddaten, Gewinde, Zusatzarbeiten) und die "
           "Einstellungen werden einmal eingerichtet ([[stammdaten]] und [[einstellungen]]): das Programm startet mit Beispielwerten, die "
           "durch die eigenen ersetzt werden.")
    i.text("<b>Aufbau dieser Anleitung:</b> [[start]] richtet das Programm ein. [[angebote]] bis [[nachkalkulation]] "
           "folgen dem Arbeitsablauf eines Angebots: anlegen, Positionen per STEP einlesen, optimieren, Staffelpreise, "
           "Fracht, Zukaufteile, Ausgabe und Nachkalkulation. [[einstellungen]] bis [[pflege]] beschreiben, was "
           "einmal eingerichtet und gepflegt wird: Einstellungen, Stammdaten, Zukaufartikel, Frachtkosten, Updates und "
           "Datensicherung. Im Anhang stehen die Einzelheiten der STEP-Messung ([[step_messung]]), häufige Fragen "
           "([[fragen]]) und was sich je Programmversion geändert hat ([[neu]]).")
    i.abschnitt("Aufbau des Fensters")
    i.text("Das Programm öffnet sich immer maximiert (bildschirmfüllend, die Taskleiste bleibt sichtbar) und gleich "
           "im Reiter <i>Angebote</i>. Die übrigen Reiter sind von dort mit einem Klick erreichbar.")
    i.text("Das Hauptfenster besteht aus Reitern. Die festen Reiter sind <i>Start</i>, <i>Angebote</i>, <i>Kunden</i>, "
           "<i>Frachtkosten</i> ([[frachtkosten]]), <i>Zukaufartikel</i> ([[zukauf]]) "
           "und <i>Einstellungen</i> (mit Passwort; darin die Vorgaben und die übrigen Stammdaten als Unterreiter). Jedes geöffnete Angebot bekommt einen eigenen Reiter "
           "(<i>Angebot A-2026-0041</i>), der sich mit dem kleinen × schließen lässt. Unten in der Statuszeile "
           "meldet das Programm, was es gerade gespeichert oder gerechnet hat; Fehlermeldungen erscheinen dort rot.")
    i.bild("angebot_optimiert", "Hauptfenster mit geöffnetem Angebot nach dem Optimieren", hoehe=125 * mm)
    i.abschnitt("Farben in den Tabellen")
    i.text("Zahlen werden mit Komma eingegeben (1385,5). Jede Änderung wird sofort gespeichert; einen "
           "Speichern-Knopf gibt es nicht. Die Farben zeigen, was eingegeben werden kann und was geprüft werden "
           "sollte:")
    i.tabelle(["Farbe", "Bedeutung"], [
        ["hellgelb", "Eingabefeld: hier wird eingetragen (Doppelklick oder einfach lostippen)."],
        ["hellgrau", "Berechneter Wert, nicht änderbar."],
        ["grün <b>OK</b>", "Zeile ist vollständig und stimmig."],
        ["gelb <b>WARNUNG / HINWEIS</b>", "Zeile wird gerechnet, sollte aber geprüft werden (z. B. Gewinde-Vorschlag "
                                          "aus dem STEP-Import)."],
        ["rot <b>FEHLER</b>", "Zeile kann nicht gerechnet werden; der Text sagt, was fehlt. Teile mit FEHLER werden "
                              "nicht eingeplant."]], [60, 205])


def kapitel_start(i):
    i.kapitel("Installation und erster Start", marke="start")
    i.abschnitt("Installieren oder portabel")
    i.text("Es gibt das Programm in zwei Formen. Beide enthalten dieselben Programmdateien, rechnen gleich und "
           "werden über dasselbe Online-Update aktuell gehalten. Sie unterscheiden sich nur darin, wo die Daten "
           "liegen.")
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
    i.text("Der Programmordner der portablen Version sieht danach so aus (die installierte Version hat dieselben "
           "Programmdateien, aber keine <i>Portabel.ini</i>, keinen Ordner <i>Daten</i> und keinen Ordner "
           "<i>Angebote</i>):")
    i.tabelle(["Datei / Ordner", "Inhalt"], [
        ["Rohrlaser-Angebotskalkulation.exe", "das Programm"],
        ["Bedienungsanleitung.pdf", "diese Anleitung (auch über <i>Hilfe → Bedienungsanleitung</i> oder F1)"],
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
    i.text("Windows merkt sich bei jeder heruntergeladenen Datei, dass sie „aus dem Internet“ stammt. Beim Entpacken "
           "eines ZIP bekommt jede der rund 800 Programmdateien diese Markierung, und der Microsoft Defender prüft dann "
           "jede einzeln besonders gründlich; ein Setup mit der Markierung meldet beim Start „Der Computer wurde durch "
           "Windows geschützt“. Das Programm braucht keine Administratorrechte, geht nur für die Suche nach Updates ins "
           "Internet ([[updates]]) und schreibt nur in seinen Programm- und Datenordner und in die eingestellten "
           "Ablage- und Sicherungsordner. Updates aus dem Programm haben die Markierung nicht, die Warnungen betreffen "
           "also nur das erste Herunterladen.")
    i.text("<b>Der einfachste Weg, ganz ohne Adminrechte:</b> die heruntergeladene Datei <b>vor</b> dem Entpacken bzw. "
           "Starten freigeben.")
    i.liste("Im Explorer (meist Ordner <i>Downloads</i>) mit der rechten Maustaste auf "
            "<i>Rohrlaser-Angebotskalkulation.zip</i> bzw. <i>Rohrlaser-Angebotskalkulation-Setup.exe</i> klicken → "
            "<i>Eigenschaften</i>.",
            "Im Reiter <i>Allgemein</i> steht unten bei <i>Sicherheit</i>: „Die Datei stammt von einem anderen "
            "Computer …“. Dort <b>Zulassen</b> anhaken → <i>OK</i>. Fehlt das Kästchen, ist die Datei schon "
            "freigegeben.",
            "Erst jetzt das ZIP entpacken bzw. das Setup starten. Die entpackten Dateien haben dann keine Markierung, "
            "Windows warnt nicht und der Defender prüft wie bei jeder anderen Datei.", nummeriert=True)
    i.abschnitt("Windows-Vertrauen einrichten (Signatur)", marke="windows_vertrauen")
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
    i.text("Beim ersten Start fragt das Programm, ob vorhandene Daten übernommen werden sollen (z. B. aus einer "
           "portablen Version oder einer Export-Datei, [[datensicherung]]). Ohne Übernahme legt es die Datendatei mit "
           "Beispiel-Stammdaten an. Die Startseite zeigt in Rot, dass es sich um Beispielwerte handelt, und hinter "
           "der Datendatei, ob das Programm installiert oder portabel läuft.")
    i.bild("start_beispiel", "Startseite nach dem ersten Start (Beispiel-Stammdaten)", hoehe=112 * mm, legende=[
        (1, "<b>Datensicherung erstellen</b>: geprüfte Kopie der Datendatei in den Ordner <i>Sicherung</i> und, "
            "falls eingestellt, in den zweiten Sicherungsordner."),
        (2, "<b>Sicherung wiederherstellen …</b>: einen früheren Stand zurückholen ([[datensicherung]])."),
        (3, "<b>Datenordner öffnen</b>: zeigt den Ordner mit der Datendatei im Explorer.")])
    i.text("Die Beispielwerte in den Stammdaten ([[stammdaten]]) und den Vorgaben ([[vorgaben]]) im Reiter Einstellungen durch die "
           "eigenen ersetzen: Preise, Maschinen, Schneiddaten, Briefkopf und Zuschläge. Danach rechnet das Programm "
           "mit den eigenen Werten.")


def kapitel_angebote(i):
    i.kapitel("Angebote verwalten", marke="angebote")
    i.text("Der Reiter <i>Angebote</i> listet alle Angebote, die neuesten oben. Doppelklick öffnet ein Angebot in "
           "einem eigenen Reiter.")
    i.bild("angebote", "Reiter Angebote", hoehe=125 * mm, legende=[
        (1, "Reiter <b>Angebote</b>: Übersicht mit Positionen, Teilen und Zeitpunkt der letzten Optimierung."),
        (2, "<b>Neues Angebot</b>: legt ein Angebot mit der nächsten Nummer, dem heutigen Datum, der "
            "Standard-Maschine und -Stangenlänge an und öffnet es."),
        (3, "<b>Kopieren</b>: Kopie des markierten Angebots mit neuer Nummer, z. B. für eine Nachbestellung. "
            "Daneben <b>Öffnen</b> und <b>Löschen</b> (die tägliche Sicherung enthält gelöschte Angebote weiter)."),
        (4, "<b>Suchen</b> nach Angebotsnummer, Kunde, Kundennummer, Bemerkung, Artikelnummer oder Bezeichnung.")])
    i.text("Beim Kopieren fragt das Programm nach dem Kunden der Kopie. Vorgeschlagen ist der bisherige Kunde; "
           "wer ein Angebot für einen anderen Kunden wiederverwenden will, wählt ihn aus der Liste. Name und "
           "Zahlungsbedingungen kommen dann aus dem Kundenstamm, Positionen und Staffeln werden mitkopiert.")
    i.bild("kopieren_dialog", "Angebot kopieren: Kunde der Kopie wählen", hoehe=45 * mm)


def kapitel_angebot(i):
    i.kapitel("Angebot anlegen und bearbeiten", marke="angebot")
    i.text("Ein geöffnetes Angebot zeigt oben links den Angebotskopf und die Kalkulation dieses Angebots, rechts die "
           "Übersicht, darunter die Aktionen und die Reiter mit Positionen und Ergebnissen. Die Trennlinie zwischen "
           "oben und unten lässt sich mit der Maus verschieben; bei kleinen Fenstern rollt der obere Teil.")
    i.text("Ein Klick auf den Titel <b>Kalkulation dieses Angebots</b> klappt die Kalkulationswerte zu. Zugeklappt "
           "steht in der Titelzeile eine Kurzfassung aller Werte ungleich 0 (z. B. „Gewinn 10,0 % · "
           "Rüstzeit je Abmessung 15,0 min · …“), und die Positionen bekommen mehr Platz. Die Wahl gilt für alle Angebote. Ohne eigene "
           "Wahl ist die Karte auf kleinen Bildschirmen (z. B. 1280 × 720) zu Beginn zugeklappt. Spaltenbreiten der "
           "Positionsliste, der Kalkulation und der Zeiten richten sich beim Öffnen nach Inhalt und Spaltenkopf.")
    i.bild("angebot_positionen", "Angebot A-2026-0041 vor dem Optimieren", hoehe=125 * mm, legende=[
        (1, "<b>Angebotskopf</b>: Angebotsnummer, Kunde und Maschine fett in der ersten Zeile, darunter Datum, "
            "Kundenname, Standard-Stangenlänge und Bemerkung. Ganz unten die aufklappbaren Maschinenparameter."),
        (2, "<b>Übersicht</b>: Stand der Optimierung, Herstellkosten und Verkaufspreis groß, Meldungen, "
            "Kennzahlen und Kosten nach Gruppen."),
        (3, "<b>Positionen</b>: eine Zeile je Teil mit Stückzahl, Spalte Status ganz rechts."),
        (4, "<b>Neue Position</b>; daneben <b>Positionen löschen</b> (markierte Zeilen)."),
        (5, "<b>Zusatzarbeiten …</b>: Gewinde und Zusatzarbeiten der markierten Positionen ([[zusatzarbeiten_angebot]]). "
            "Daneben <b>Zukaufteile …</b> mit <i>Zukaufteile bearbeiten …</i> (eingekaufte Teile je Position) "
            "<i>Neuer Zukaufartikel …</i> (z. B. Bleche schnell als eigene Positionen anlegen, [[zukauf_angebot]]) und "
            "<i>EK eintragen …</i> (Einkaufspreis fehlender Zukaufteile direkt im Angebot, [[zukauf_positionen]])."),
        (6, "<b>STEP importieren</b>: Positionen aus Konstruktionsdaten ([[step]])."),
        (7, "<b>Optimieren</b>: Stangen planen und Kalkulation rechnen ([[optimieren]])."),
        (8, "Zeile über der Positionsliste: links Anzahl der Positionen und ausgeblendeten optionalen Spalten, "
            "rechts <b>Weitere Spalten</b>, <b>STEP-Werte (aus CAD)</b> und <b>Berechnete Werte (Programm)</b>.")])
    i.text("Die blau hinterlegten Knöpfe sind die Hauptaktionen <b>Neue Position</b>, <b>STEP importieren</b>, "
           "<b>Optimieren</b> und <b>3D-Ansicht</b>. Rechts stehen die Ausgaben; CSV-Export und Ablage öffnen liegen "
           "unter <b>Weitere Aktionen</b> ([[ausgabe]]).")
    i.abschnitt("Angebotskopf")
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
            "Pauschale je Abmessung, Programmierkosten je Teil und Angebotsaufschlag. Mindestpreis, Zuschlag "
            "Material und Zuschlag Fertigung gelten immer aus den Einstellungen und sind im Angebot nicht änderbar "
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
            "je Abmessung), <b>Verkauf und Gewinn</b> (Gewinn, Angebotsaufschlag, Programmierkosten, Pauschale je "
            "Abmessung, Frachtkosten, Mindestpreis) und <b>Zahlungsbedingungen</b>.")
    i.abschnitt("Lieferzeit im Angebot", marke="lieferzeit")
    i.text("Jedes Angebot hat seine eigene Lieferzeit. Ein neues Angebot übernimmt die Vorgabe aus den Einstellungen "
           "(Gruppe Angebot, [[einstellungen]]); eine Änderung gilt nur für dieses Angebot. Bestehende Angebote "
           "ändern sich nicht, wenn die Vorgabe geändert wird. Die Lieferzeit ändert keine Preise und macht die "
           "Optimierung nicht veraltet.")
    i.tabelle(["Lieferzeit als", "Wert", "im Angebot"], [
        ["Arbeitstage", "ganze Zahl, z. B. 10", "Lieferzeit: ca. 10 Arbeitstage nach Auftragseingang."],
        ["Wochen", "ganze Zahl, z. B. 3", "Lieferzeit: ca. 3 Wochen nach Auftragseingang."],
        ["Kalenderwoche", "KW/Jahr, z. B. 46/2026 (ohne Jahr: Jahr des Angebotsdatums)", "Lieferzeit: KW 46/2026."],
        ["Lieferdatum", "Datum TT.MM.JJJJ", "Lieferzeit: bis 15.11.2026."],
        ["nur Text", "– (Feld gesperrt)", "Lieferzeit: und der Freitext, z. B. „nach Absprache“"]], [30, 60, 90])
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
            "Angebote aus älteren Programmversionen haben keine eigene Lieferzeit: dort gilt wie bisher nur der "
            "Text der Bedingungen.")
    i.abschnitt("Kundenmaterial", marke="kundenmaterial")
    i.text("Stellt der Kunde das Material bei, steht in der Spalte <b>Material</b> der Position <i>Kunde "
           "beigestellt</i> statt <i>Eigenmaterial</i> (leer = Eigenmaterial, wie bisher). Im Angebotskopf legt "
           "<b>Material neuer Positionen</b> fest, was neue Positionen (auch aus dem STEP-Import) bekommen; "
           "<b>Für alle Positionen</b> trägt die Auswahl in alle Rohrlaserteil-Positionen ein. Jede Position bleibt "
           "einzeln änderbar, so können in einem Angebot beigestellte und eigene Teile stehen.")
    i.liste("Optimierung: Kundenmaterial ist eine eigene Stangengruppe und kommt nie mit eigenem Material auf eine "
            "Stange. Der Stangenbedarf wird wie sonst optimiert: so viele Stangen muss der Kunde liefern. Einen "
            "Vergleich der Lieferlängen gibt es für Kundenmaterial nicht.",
            "Kalkulation: keine Materialkosten, kein Zuschlag Material, kein Verschnittwert und kein Meterpreis. "
            "Laser, Gewinde, Rüsten, Stangenwechsel, Arbeitsschritte, Zusatzarbeiten, Programmierung und "
            "Pauschalen bleiben. Materialkosten anderer Positionen ändern sich nicht. Spalte <i>Kundenmaterial</i> "
            "im Reiter Kalkulation, Status „HINWEIS: Material vom Kunden beigestellt“.",
            "<b>Handling Kundenmaterial</b> [€/kg]: optional für Prüfen, Einlagern und Transport, je kg der "
            "beigestellten Stangen, mit Zuschlag Fertigung und Gewinn (Kostenart <i>Handling Kundenmaterial</i>). "
            "Vorgabe 0 = keins; Einstellung in der Gruppe Kalkulation, je Angebot änderbar.",
            "Angebot: Die Position heißt „Material S235 EN10219 vom Kunden beigestellt“ statt „inkl. Material …“; "
            "vor den Bedingungen steht „Material wird vom Kunden beigestellt: 2 Stangen Quadratrohr 40 x 40 x 3, "
            "S235 EN10219, à 6.000 mm.“ (abschaltbar mit der Einstellung <i>Angebots-PDF: Hinweis zum "
            "Kundenmaterial mit Stangenbedarf</i>). Werkstattpapier und Nachkalkulation führen das Kundenmaterial "
            "als eigene Zeile.",
            "Staffelpreise rechnen das Kundenmaterial in jeder Stufe ohne Materialkosten.")
    i.abschnitt("Mindestpreis", marke="mindestpreis")
    i.text("Liegt der Verkaufspreis eines Angebots unter dem <b>Mindestpreis</b> (Mindestauftragswert, Vorgabe "
           "200,00 € netto), "
           "hebt das Programm alle Stückpreise im gleichen Verhältnis an, bis die Angebotssumme den Mindestpreis "
           "erreicht. Es entsteht keine zusätzliche Position, und Zeiten, Material und Herstellkosten bleiben wie "
           "kalkuliert. Der Mindestpreis ist netto: nach eingerechnetem Skonto und vor der Umsatzsteuer.")
    i.liste("Beispiel: kalkuliert 148,00 € netto, Mindestpreis 200,00 € → jeder Stückpreis × 200 ÷ 148; "
            "Angebotspreis netto 200,00 €. In Übersicht, Reiter Kalkulation, Kalkulations-PDF und CSV steht die "
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
            "alle Angebote, auch für ältere; im Angebot selbst lässt er sich nicht ändern. 0 = kein Mindestpreis.",
            "Die Prüfung läuft bei jeder Änderung neu (Position, Stückzahl, Zuschläge, Staffelstufe, PDF). Die "
            "Werte des Angebots (Gewinn, Zuschläge …) bleiben dabei unverändert; steigt der Preis über den "
            "Mindestpreis, entfällt die Anhebung von selbst.")
    i.abschnitt("Nullwerte und Erweiterte Einstellungen")
    i.text("Damit das Angebot übersichtlich bleibt, zeigt das Programm Werte, die 0 sind und nur optional etwas "
           "kosten würden, nicht in der Hauptansicht. Sie stehen im aufklappbaren Bereich <b>Erweiterte "
           "Einstellungen</b> (der Titel nennt die Anzahl, z. B. „1 Wert auf 0“) und lassen sich dort jederzeit "
           "ändern. Sobald ein Wert nicht mehr 0 ist, steht er sofort wieder oben in seiner Gruppe. Gespeichert, "
           "gerechnet und ausgegeben wird immer alles, auch was ausgeblendet ist.")
    i.tabelle(["Bereich", "ausgeblendet, wenn 0 oder leer", "immer sichtbar"], [
        ["Angebotskopf", "Frachtkosten, Skonto, Skontofrist, Zahlungsziel, Zuschläge, Gewinn, Rüstzeit und Pauschale "
                         "je Abmessung, Programmierkosten, Angebotsaufschlag",
         "Angebotsnummer, Kunde, Datum, Maschine, Standard-Stangenlänge, Bemerkung"],
        ["Maschinenparameter", "Abstand getrennte Schnitte, Konturgrenzen, max. Hüllkreis-Ø, max. Metergewicht",
         "Endbeschnitt, Greiferrest, Schnittverlust, max. Stangenlänge"],
        ["Übersicht", "jede Kostenart mit 0,00 €", "Material, Herstellkosten, Verkaufspreis, Kennzahlen"],
        ["Positionen", "Oberfläche, Stangenlänge abweichend, Satz, Stück je Satz, Gewinde "
                       "geprüft, Zusatzarbeiten (solange keine Position einen Wert hat)",
         "Pos., Artikelnummer, Bezeichnung, Profil-ID, Werkstoff-ID, Teilelänge, Stückzahl, Schneidweg, Einstiche, "
         "Schneidzeit, Materialpreis, Status"]], [32, 80, 70])
    i.text("Ob ein Wert 0 ist, prüft das Programm an der Zahl, nicht am Text: „0,00 €“ und „0 %“ sind 0, "
           "„10,00 €“ nicht.")
    i.bild("angebot_erweitert", "Erweiterte Einstellungen und Maschinenparameter aufgeklappt (Frachtkosten 0 €)",
           hoehe=90 * mm)
    i.abschnitt("Übersicht")
    i.liste("Ganz oben der <b>Stand der Optimierung</b>: <i>Noch nicht optimiert</i> (gelb), <i>Optimierung "
            "abgeschlossen</i> (grün) oder <i>Veraltet</i> (rot, [[veraltet]]).",
            "Darunter der <b>Preisstand</b>: <i>Materialpreise: aktuelle Stammdaten</i>, solange noch kein "
            "Angebots-PDF erzeugt wurde, danach <i>Preise festgeschrieben am …</i>. Haben sich die Stammdaten "
            "seitdem geändert, steht er gelb mit der Anzahl der Änderungen (Mauszeiger darauf zeigt sie einzeln), "
            "und der Knopf <b>Aktuelle Preise übernehmen …</b> erscheint ("
            "[[preise_festschreiben]]).",
            "Darunter groß <b>Herstellkosten</b> und <b>Verkaufspreis</b>, damit sie auch auf kleinen Bildschirmen "
            "ohne Rollen zu sehen sind. Vor dem Optimieren (oder wenn die Optimierung veraltet ist) stehen sie grau "
            "mit „(vorläufig)“: Material, Stangenwechsel und Verschnitt fehlen dann noch.",
            "<b>Meldungen</b>: die Anzahl der Fehler, Warnungen und Hinweise der Positionen (rot, gelb); aufklappen "
            "zeigt jede Meldung mit ihrer Positionsnummer.",
            "Kennzahlen: Positionen, Stückzahl, Gesamtlänge, Gewicht und Stangen.",
            "Kosten nach Gruppen: Material, Laser schneiden, Rüsten (Rüsten Maschine, Rüsten je Abmessung, "
            "Stangenwechsel), Zusätzliche Bearbeitung (Gewinde, Zusatzarbeiten), Zuschläge, <b>Herstellkosten</b>, "
            "Gewinn, Programmierkosten, Pauschalen und Aufschläge (Pauschale je Abmessung, Angebotsaufschlag, "
            "Fracht), Skonto und <b>Verkaufspreis</b>. <b>Kostenarten einzeln</b> klappt jede Kostenart mit ihrer "
            "Mengenangabe auf.")
    i.abschnitt("Positionen")
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
        ["Stangenlänge abweichend", "nur wenn diese Position aus einer anderen Stangenlänge geschnitten wird"],
        ["Satz, Stück je Satz", "Zusammengehörige Teile (z. B. ein Gestell) für Staffelpreise je Satz ([[staffeln]])"],
        ["Materialpreis [€/m]", "grau = berechneter Meterpreis; anpassen ersetzt ihn für dieses Angebot "
                                "([[meterpreis]])"],
        ["Gewinde geprüft", "z. B. <i>4xM6; 2xM8</i>. Nur was hier steht, wird als Gewinde gerechnet."],
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
    i.text("Positionen markieren (eine oder mehrere) und auf <b>Zusatzarbeiten …</b> klicken, oder in der Spalte "
           "<i>Zusatzarbeiten</i> doppelklicken. Im Fenster stehen oben die Gewinde, darunter beliebig viele "
           "Zusatzarbeiten aus den Stammdaten.")
    i.bild("zusatz_dialog", "Zusatzarbeiten für eine Position: Gewinde, Feuerverzinken und eine zusätzliche Gravur",
           hoehe=80 * mm, legende=[
               (1, "<b>Gewinde (geprüft)</b>: Anzahl x Größe, mehrere mit Semikolon. Darunter der Festpreis je Teil "
                   "aus den Stammdaten Gewinde."),
               (2, "<b>Zusatzarbeit</b> aus der Liste wählen; die Abrechnung (€/kg, €/m², €/m, €/Stück, s/Stück) "
                   "kommt aus den Stammdaten."),
               (3, "<b>Menge je Teil</b> und <b>Preis bzw. Zeit</b>: leer lassen = automatisch (grau angezeigt). "
                   "Ein Eintrag gilt nur für diese Position, z. B. eine andere Fläche oder ein Sonderpreis."),
               (4, "<b>Text</b> für das Angebot, z. B. die RAL-Farbe beim Pulverbeschichten."),
               (5, "<b>Zusatzarbeit hinzufügen</b> / <b>Markierte entfernen</b> / <b>Preise aus Stammdaten "
                   "übernehmen</b>.")])
    i.liste("Sind mehrere Positionen markiert, gilt die Auswahl für alle. Die automatische Menge (Gewicht, Fläche, "
            "Länge) rechnet jede Position für sich.",
            "Die Kosten erscheinen in der Kalkulation in der Spalte <i>Zusatzarbeiten je Teil</i> und in der Summe "
            "<i>Zusatzarbeiten</i>; Zeiten (s/Stück, z. B. Gravur extra) erhöhen die Laserzeit.",
            "Im Angebot steht jede Arbeit mit ihrem Text hinter <i>Zusatzarbeiten:</i>.",
            "Die Liste zeigt nur aktive Zusatzarbeiten: zuerst die häufig verwendeten, dann nach Kategorie.",
            "Der Preis der Stammdaten wird beim Hinzufügen in der Position gespeichert (Preisstand, im Feld Preis grau "
            "mit Datum). Haben sich die Stammdaten seitdem geändert, holt <b>Preise aus Stammdaten übernehmen</b> die "
            "aktuellen Werte für alle Zeilen (gilt nach OK).",
            "Steht in einer älteren Position (ohne Preisstand) eine Zusatzarbeit, die es in den Stammdaten nicht mehr "
            "gibt, zeigt der Status <b>WARNUNG: Zusatzarbeit … unbekannt</b> und sie wird nicht gerechnet.")
    i.abschnitt("Schneidzeit anpassen", marke="schneidzeit")
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
    i.text("Die Spalte <b>Materialpreis [€/m]</b> zeigt in Grau den berechneten Einkaufspreis je Meter für Profil, "
           "Werkstoff und Stangenlänge der Position: Preis der Lieferlänge, sonst <i>Preise</i>, sonst Tonnenpreis des "
           "Werkstoffs, jeweils mit dem Aufpreis der Oberfläche. Bei festgeschriebenen Preisen gilt der Stand des "
           "Angebots ([[preise_festschreiben]]). Ist der Preis günstiger oder teurer zu bekommen (z. B. ein aktuelles "
           "Lieferantenangebot), doppelt klicken: der berechnete Preis steht im Feld und lässt sich ändern.")
    i.liste("Der eingetragene Preis steht fett und ersetzt Preis und Oberflächen-Aufpreis. Er gilt für alle Stangen "
            "mit gleichem Profil, Werkstoff, Oberfläche und Stangenlänge, weil diese Positionen gemeinsam aus "
            "denselben Stangen geschnitten werden. Die anderen Positionen dieser Gruppe zeigen ihn kursiv.",
            "Die Kalkulation, der Lieferlängen-Vergleich und die Staffelpreise rechnen mit dem eingetragenen Preis; "
            "Materialzuschläge der Staffeln kommen wie gewohnt dazu.",
            "Der Status zeigt <b>HINWEIS: Meterpreis manuell</b>. Feld leeren (oder 0 eintragen) = wieder berechnet. "
            "Wird der berechnete Preis unverändert bestätigt, bleibt er berechnet.")


def kapitel_step(i):
    i.kapitel("STEP-Import", marke="step")
    i.text("Der STEP-Import liest Konstruktionsdaten (.step/.stp, ein oder mehrere Rohre je Datei) und legt je "
           "Rohr eine Position an. Gemessen werden Profil, Teilelänge, Schneidweg, Einstiche, Anfangs- und "
           "Endschnitt (gerade oder schräg), Innenkonturen nach Größe, Gravuren, Bohrungen und ein "
           "Gewinde-Vorschlag. Die Messung übernimmt das Programm <i>STEP-Import.exe</i> im Ordner "
           "<i>STEP-Import</i> neben dem Programm.")
    i.liste("Im Angebot auf <b>STEP importieren …</b> klicken und die Dateien wählen (Mehrfachauswahl mit Strg oder "
            "Umschalt). Oder die STEP-Dateien bzw. ganze Ordner aus dem Explorer per <b>Drag &amp; Drop</b> in das "
            "Angebotsfenster ziehen; aus Ordnern (samt Unterordnern) werden alle .step/.stp-Dateien genommen.",
            "Nach der Messung zeigt der Dialog <b>STEP-Import prüfen</b> die Rohre einer STEP-Datei, gegliedert "
            "nach Profil, mit drehbarer 3D-Ansicht des markierten Teils (siehe unten). Bei mehreren Dateien wechseln "
            "die Pfeil-Knöpfe oben zwischen den Dateien (<i>Datei 2 von 7: …</i>). Dort je Teil festlegen, ob es "
            "übernommen wird, und Profil, Werkstoff und Stückzahl wählen. <b>Übernehmen</b> legt die Positionen "
            "aller Dateien an, <b>Abbrechen</b> verwirft die Messung.",
            "Enthält eine STEP mehrere Teile (Baugruppe), steht oben das Feld <b>Sätze</b>: Anzahl eintragen = als "
            "Satz anlegen, leer lassen = jedes Teil als Einzelposition (siehe unten).",
            "Fehlen Profile in den Stammdaten, fragt das Programm, ob sie aus den Messwerten angelegt werden sollen "
            "(danach im Reiter <i>Profile</i> prüfen). Stehen Artikel schon im Angebot, fragt es vor dem doppelten "
            "Eintragen.",
            "Am Ende meldet es, wie viele Positionen übernommen wurden; <i>Details</i> zeigt den Bericht je Datei.",
            nummeriert=True)
    i.abschnitt("Rohrliste prüfen")
    i.liste("Jede Zeile ist ein Teil. Gleiche Teile aus einer Datei (Baugruppe) stehen in einer Zeile; die Spalte "
            "<b>In Datei</b> zeigt, wie oft es in der Datei vorkommt.",
            "Die Spalte <b>Art</b> zeigt die erkannte Bauteilart. Bei Flachstahl/Blech und Profil/Kantteil ist sie "
            "eine Auswahl (siehe Bleche beim STEP-Import).",
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
            "Teile, die nicht gemessen werden konnten, stehen unten unter <i>Nicht übernehmbar</i> mit dem Grund.")
    i.bild("step_pruefen", "STEP-Import prüfen: eine Datei je Ansicht, Eingaben je Teil und 3D-Ansicht",
           hoehe=100 * mm, legende=[
               (1, "Pfeil-Knöpfe links/rechts: zwischen den STEP-Dateien wechseln; daneben Nummer und Name der Datei."),
               (2, "Rohrliste der Datei: Häkchen, Profil-ID, Werkstoff-ID und Stückzahl je Teil."),
               (3, "Werkstoff und Stückzahl für alle oder die markierten Zeilen setzen.")])
    i.bild("step_positionen", "Übernommene Positionen mit eingeblendeten STEP-Werten", hoehe=125 * mm, legende=[
        (1, "<b>STEP-Werte</b> zeigt Anfangs-/Endschnitt, Innenkonturen nach Größe, Gravur, Bohrungen und den "
            "Gewinde-Vorschlag.")])
    i.hinweis("Gewinde werden nur vorgeschlagen (Status HINWEIS: Gewinde-Vorschlag prüfen). Erst wenn das Gewinde "
              "nach Prüfung der Zeichnung in die Spalte <b>Gewinde geprüft</b> eingetragen ist, wird es gerechnet.")
    i.bild("step_protokoll", "Reiter STEP-Protokoll: alle Messwerte je Datei und Körper", hoehe=80 * mm)
    i.bild("step_optimiert", "Aus STEP übernommene Positionen nach dem Optimieren: Schneidweg, Einstiche und "
           "Schneidzeit kommen aus der Messung", hoehe=110 * mm)
    i.abschnitt("3D-Ansicht")
    i.text("Jedes per STEP-Import angelegte Teil wird mit seinem 3D-Modell gespeichert. In der Positionsliste steht "
           "neben der Artikelnummer ein kleines Vorschaubild. <b>3D-Ansicht …</b> in der Knopfleiste des Angebots "
           "öffnet alle Positionen mit großer Ansicht, beginnend mit der markierten Zeile. Beim Kopieren eines "
           "Angebots gehen die 3D-Modelle mit.")
    i.liste("Linke Maustaste ziehen: drehen. Rechte oder mittlere Maustaste ziehen: verschieben. Mausrad: zoomen. "
            "Doppelklick: zurück zur Ausgangsansicht.",
            "Farben: Außenwand grau, Innenwand dunkelgrau, <b>Anfangsschnitt orange</b>, <b>Endschnitt violett</b>, "
            "<b>Innenkonturen rot</b>, <b>Gravur grün</b>. So ist auf einen Blick zu sehen, was die Messung als "
            "Schneidweg zählt.",
            "Positionen ohne STEP-Import (von Hand angelegt) haben keine 3D-Ansicht.")
    i.bild("step_3d", "3D-Ansicht der Positionen (Knopf 3D-Ansicht …)", hoehe=95 * mm, legende=[
        (1, "Feste Blickrichtungen: <b>Schräg</b>, <b>Vorn</b>, <b>Oben</b> und <b>Stirnseite</b>.")])
    i.hinweis("Der STEP-Import misst schneller als früher. Bei vielen Dateien (ab 6) misst er auf mehreren "
              "Prozessorkernen gleichzeitig.")
    i.abschnitt("Bleche erkennen", marke="bleche")
    i.text("Vor der Profilmessung prüft der STEP-Import, ob ein Körper ein <b>Blech</b> ist. Ein Blech hat zwei "
           "parallele Hauptflächen, ist überall gleich dick (das Volumen entspricht Hauptfläche × Dicke) und ist "
           "höchstens ein Fünftel so dick wie breit. Bohrungen, Ausschnitte, Langlöcher, Fasen und eine freie "
           "Außenkontur sind erlaubt.")
    i.liste("<b>Dicke</b> = Abstand der beiden Hauptflächen. Sie stimmt auch, wenn das Blech im Modell gedreht "
            "oder schräg liegt (nicht einfach die kleinste Kante des Hüllquaders).",
            "<b>Länge und Breite</b> = kleinstes Rechteck, das die Außenkontur umschließt. Die Kontur heißt "
            "<i>rechteckig</i> oder <i>frei</i> (z. B. schräge Ecke). Dazu kommen Anzahl der Innenkonturen und die "
            "Bohrungen je Durchmesser.",
            "<b>Flachstahl oder Blech</b>: Ein flaches Teil ist Flachstahl, wenn es höchstens so breit ist wie in "
            "der Einstellung <i>STEP-Import: Flachstahl bis Breite</i> (Vorgabe 150 mm), mindestens dreimal so lang "
            "wie breit ist und gerade Längsseiten hat. Die Enden dürfen schräg oder ausgeklinkt sein. Flachstahl wird "
            "wie bisher übernommen und kalkuliert. Alles andere Flache ist ein Blech.",
            "<b>Gekantete Bleche</b> (gleich dicke Schenkel mit Biegeradien) heißen <i>Blech gekantet</i>, immer mit "
            "Prüfstatus <i>prüfen</i>. Der Hinweis nennt die Außenmaße und die ungefähre Abwicklungsfläche ohne "
            "Biegefaktor. Ein Kantteil mit gleichbleibendem Querschnitt über die ganze Länge bleibt ein L-, U- oder "
            "C-Profil, weil es als Stangenmaterial auf dem Rohrlaser geschnitten werden kann.",
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
            "die Rohre gilt nicht für Bleche. Ohne Werkstoff heißt der neue Artikel z. B. <i>Blech 400 × 200 × 4 mm "
            "(Werkstoff offen)</i> und die Position hat kein Gewicht.",
            "Bleche mit Prüfstatus <i>prüfen</i> (z. B. gekantete) sind nicht angehakt und werden erst nach "
            "Anhaken übernommen. Ein Blech, dessen Artikelnummer schon im Angebot steht, wird übersprungen; ein "
            "erneuter Import legt keinen zweiten Zukaufartikel an.",
            "Ist die STEP-Datei eine Baugruppe (z. B. Rohr mit zwei Laschen), zählt sie mit den Blechen als "
            "mehrteilig: mit <i>Sätze</i> werden Rohr und Bleche ein Satz, gleiche Bleche eine Position mit "
            "Stück je Satz.",
            "Neue Zukaufartikel bekommen Kategorie Blechteile, Einheit Stück, Lieferant Technik, die STEP-Datei und "
            "die Geometrie-Kennung. Der Bericht nennt die Anzahl; den Einkaufspreis direkt im Angebot mit "
            "<b>Zukaufteile … → EK eintragen …</b> (mit Stückzahl, [[zukauf_positionen]]) oder unter Zukaufartikel mit "
            "<b>EK eintragen …</b> nachtragen (Filter <i>EK fehlt</i>).",
            "In den Messwerten stehen die Spalten <i>bauteiltyp</i> (Profil, Blech, Blech gekantet) und <i>blech</i> "
            "(alle Blechmaße). Im JSON-Messergebnis (ab Version 1.1) steht je Blech der Block <i>blech</i>; die "
            "Profilwerte (Querschnitt, Wandstärke) sind dort <i>null</i>. Ab Version 1.2 steht bei Grenzfällen der "
            "Block <i>alternative</i> (das Teil in der anderen Art) und <i>ersatzwerte</i> (true = abgeleitet, "
            "nicht gemessen).")
    i.abschnitt("Baugruppen als Satz")
    i.text("Liegen in einer STEP-Datei mehrere Rohrteile, steht im Dialog STEP-Import prüfen oben das Feld "
           "<b>Sätze</b>. Ist eine Anzahl eingetragen:")
    i.liste("Der Satz heißt wie die Datei (ohne Endung) und steht in der Spalte <b>Satz</b> jeder Position.",
            "Gleiche Teile (gleiche Maße, Konturen und Bohrungen, Lage im Raum egal) werden eine Position; "
            "<b>Stück je Satz</b> ist ihre Anzahl in der Baugruppe.",
            "Die Spalte der Rohrliste heißt dann <b>Stück je Satz</b> (vorgegeben: Anzahl in der Baugruppe, "
            "änderbar). Stückzahl der Position = Sätze × Stück je Satz.",
            "Das STEP-Protokoll zeigt weiter jeden Körper, die gleichen mit dem Hinweis <i>gleich wie …</i>.")
    i.text("Bleibt das Feld <b>leer</b>, wird jeder Körper eine eigene Position ohne Satz, mit der Stückzahl aus "
           "der Rohrliste. Bei mehreren Dateien gilt das Feld je Datei. Staffelpreise und Angebot rechnen den Satz "
           "wie einen von Hand angelegten ([[staffeln]]).")
    i.bild("step_satz_pruefen", "Baugruppe im Prüfdialog: 4 Sätze eingetragen", hoehe=80 * mm, legende=[
        (1, "<b>Sätze</b>: Anzahl Sätze; leer = Einzelpositionen. Rechts daneben der Satzname."),
        (2, "Die Spalte zeigt jetzt <b>Stück je Satz</b>.")])
    i.bild("step_satz_positionen", "Baugruppe als Satz: 3 gleiche Quadratrohre und 1 Rundrohr, 4 Sätze",
           hoehe=110 * mm, legende=[(1, "Spalten <b>Satz</b>, <b>Stück je Satz</b> und <b>Stückzahl</b>.")])
    i.abschnitt("Prüfstatus und Messergebnis als Datei")
    i.liste("Jedes Teil bekommt einen <b>Prüfstatus</b>. <i>plausibel</i> heißt, dass die Messung in sich stimmig "
            "ist; eine Fertigungsfreigabe ist das nicht. <i>prüfen</i> bedeutet, dass es Hinweise gibt, ein Merkmal "
            "unsicher ist oder die Geometrie ungültig ist. <i>nicht messbar</i> heißt, dass kein Profil erkannt wurde. "
            "Im Dialog STEP-Import prüfen ist die Hinweis-Spalte bei <i>prüfen</i> gelb hinterlegt, und unter der "
            "Rohrliste steht der Prüfstatus des gewählten Teils.",
            "Ist ein Merkmal <b>unsicher</b> (z. B. Wandstärke nicht einheitlich), ist das Teil im Prüfdialog "
            "<b>nicht angehakt</b> und trägt den Hinweis <i>UNSICHER: … – zum Übernehmen anhaken</i>. Übernommen "
            "wird es erst, wenn es von Hand angehakt wird. Ohne Bestätigung steht im Bericht <i>nicht übernommen: "
            "Erkennung unsicher</i>.",
            "Bei jedem STEP-Import legt das Programm das vollständige Messergebnis als <b>JSON-Datei</b> in die "
            "Ablage: <i>&lt;Angebot&gt; STEP-Messung &lt;Datum Uhrzeit&gt;.json</i>. Der Pfad steht im Bericht. Die "
            "Datei enthält je STEP-Datei den Importstatus, die Einheit und die Meldungen. Je Körper kommen dazu "
            "Profiltyp, Außen- und Innenmaße, Wandstärke mit allen Einzelmessungen, Länge, Längsachse, Konturen "
            "mit Lage, Schnittwinkel, Prüfstatus, Warnungen und die Erkennungssicherheit je Merkmal. Werte, die "
            "nicht gemessen werden konnten, stehen als <i>null</i> darin, nie als 0 oder Schätzwert. Das Format "
            "trägt eine Versionsnummer (<i>schema_version</i>).",
            "<i>STEP-Import.exe</i> kann auch ohne das Programm messen: <i>STEP-Import.exe --ausgabe messwerte.txt "
            "--json ergebnis.json Ordner</i>.")
    i.text("Wie die Messung Profil, Schneidweg, Konturen und Enden bestimmt, welche Fälle geprüft sind und wo die "
           "Grenzen liegen, steht im Anhang ([[step_messung]]).")


def kapitel_optimieren(i):
    i.kapitel("Optimieren und Kalkulation", marke="optimieren")
    i.text("<b>Optimieren</b> verteilt alle gültigen Positionen auf Stangen, prüft jede Stange gegen Überlast und "
           "rechnet die Kalkulation. Danach zeigt die Übersicht <b>Optimierung abgeschlossen</b> (grün).")
    i.abschnitt("Regeln der Optimierung")
    i.liste("Je Profil + Werkstoff + Oberfläche + Stangenlänge getrennt, ohne Vermischung.",
            "Belegung einer Stange = Endbeschnitt + Teile + Trennschnitte + Schnittverlust des letzten Schnitts; "
            "der Greiferrest muss frei bleiben.",
            "Zwei Teile mit geraden, aneinanderliegenden Enden teilen sich einen Schnitt (einmal Schnittverlust, die "
            "Einstiche eines Endes gespart: bei Trägern und U-Profilen 4, beim T-Profil 2, sonst 1). Sonst zwei Schnitte mit dem Abstand aus <i>Maschinen</i>. Teile werden dafür "
            "gedreht; schräge Enden kommen an Stangenanfang oder -ende.",
            "Verfahren: First-Fit und Best-Fit, danach Nachbesserung. Ist das nicht nachweislich optimal, rechnet "
            "die <b>Schnittmuster-Optimierung</b>: gleiche Teile werden zusammengefasst, das Programm sucht die "
            "besten Schnittmuster je Stange und die Kombination mit den wenigsten Stangen. Sie liefert zugleich eine "
            "Schranke, unter die es nicht gehen kann; wird sie erreicht, ist das Ergebnis nachweislich optimal, "
            "auch bei großen Aufträgen. Bei Gruppen bis 60 Teile folgt bei Bedarf noch eine exakte Suche. Alle "
            "Suchen sind nach Schritten begrenzt, nicht nach Zeit: dasselbe Angebot ergibt auf jedem Rechner "
            "denselben Schnittplan.",
            "Keine Restverwaltung: Reste zählen als Verschnitt.")
    i.abschnitt("Optimierung veraltet", marke="veraltet")
    i.text("Ändert sich danach etwas am Angebot oder an den Stammdaten, zeigt die Übersicht <b>Veraltet</b>. Die "
           "Ergebnisse gelten dann nicht mehr; einfach neu optimieren. Vor einer Ausgabe mit veraltetem Stand fragt "
           "das Programm nach.")
    i.bild("angebot_veraltet", "Nach einer Änderung der Stückzahl: Stand Veraltet", hoehe=125 * mm,
           legende=[(1, "Stand der Optimierung: grün Optimierung abgeschlossen, gelb noch nicht optimiert, rot "
                        "Veraltet.")])
    i.abschnitt("Kalkulation", marke="kalkulation")
    i.text("Der Reiter <i>Kalkulation</i> zeigt oben die Summen des Angebots und darunter je Position Material, "
           "Laserzeit, Gewinde, Rüsten, Herstellkosten und Verkaufspreis je Teil und je Position.")
    i.text("Reiter Kalkulation, Kalkulations-PDF und CSV-Export führen jede Kostenart des Angebots einzeln auf "
           "(die Übersicht nach Gruppen, einzeln unter <i>Kostenarten einzeln</i>); im Reiter fehlen Kostenarten "
           "mit 0,00 €, PDF und CSV enthalten alle: Material, Laser schneiden, Gewinde, Rüsten Maschine, Rüsten je "
           "Abmessung, Stangenwechsel, Weitere Arbeitsschritte, Zusatzarbeiten, Zuschlag Material, Zuschlag Fertigung, Zuschlag "
           "Fremdleistung ergeben die <b>Herstellkosten</b>; dazu Gewinn, Pauschale je Abmessung, "
           "Programmierkosten, Angebotsaufschlag, Fracht, Skonto und ggf. die Anhebung auf Mindestpreis "
           "([[mindestpreis]]) ergeben den <b>Verkaufspreis</b>. In Klammern stehen "
           "Zeiten, Anzahl und Prozentsätze, aus denen der Betrag entsteht.")
    i.bild("erg_kalkulation", "Reiter Kalkulation", hoehe=80 * mm)
    i.liste("<b>Material</b>: Kosten der geplanten Stangen je Gruppe, nach Längenanteil auf die Positionen verteilt "
            "(Verschnitt ist enthalten). Preis: abweichender Preis der Position, sonst <i>Preise</i>, sonst "
            "Tonnenpreis des Werkstoffs; bei den beiden letzten kommt der Aufpreis der Oberfläche je m dazu.",
            "<b>Laser</b>: Vorschübe aus den Schneiddaten (Werkstoff, sonst Kategorie; N₂ vor O₂). Schneidweg je "
            "Konturklasse durch deren Vorschub, Gravur mit eigenem Vorschub, plus "
            "Einstiche × Einstechzeit; gemeinsame Schnitte sind abgezogen. Eine manuelle Schneidzeit ersetzt diesen "
            "Wert; Zeiten aus Zusatzarbeiten (s/Stück) kommen dazu. Die Spalten <i>davon Kontur groß + Rest</i>, "
            "<i>davon Kontur mittel</i>, <i>davon Kontur klein</i>, <i>davon Gravur</i> und <i>davon Einstiche</i> "
            "zeigen, wie sich die Laserzeit brutto zusammensetzt ([[konturklassen]]).",
            "<b>Gewinde</b>: Anzahl × Preis je Gewinde (Stammdaten); ohne Preis Anzahl × Zeit mit dem Stundensatz "
            "des Arbeitsschritts Gewinde.",
            "<b>Zusatzarbeiten</b>: Menge × Preis je Teil, ggf. auf den Mindestbetrag angehoben; Fremdleistungen mit "
            "dem Zuschlag Fremdleistung.",
            "<b>Rüsten</b>: Rüstzeit je Angebot (Maschine), Rüstzeit je Abmessung (Einstellungen) und "
            "Stangenwechsel je Stange, gleichmäßig auf alle Teile verteilt, je mit dem Stundensatz ihres "
            "Arbeitsschritts.",
            "<b>Weitere Arbeitsschritte</b>: Zeiten aus den Arbeitsschritten ([[stundensaetze]]) × Stundensatz, auf die "
            "Teile verteilt (Spalte <i>Weitere Arbeitsschritte je Teil</i>).",
            "<b>Pauschale je Abmessung, Programmierkosten je Teil, Angebotsaufschlag, Fracht</b>: ohne Zuschläge auf "
            "den Preis. Die Programmierkosten fallen einmal je Position an, egal wie viele Stück.",
            "<b>Zukaufteile</b>: Einstand und Aufschlag der Zukaufteile der Position ([[zukauf_angebot]]), nach dem "
            "Gewinn und ohne Zuschläge (Spalte <i>Zukaufteile je Teil</i>).",
            "<b>Skonto</b>: der Betrag, um den der Preis steigt, damit nach Abzug des Skontos der Preis ohne Skonto "
            "bleibt (Skonto % des Verkaufspreises). Je Teil in der Spalte <i>Skonto je Teil</i>.")
    i.abschnitt("Zeiten & Arbeitskosten", marke="zeiten")
    i.text("Der Reiter <i>Zeiten & Arbeitskosten</i> zeigt je Arbeitsschritt Art, Menge, Rüstzeit, Zeit je Einheit, "
           "Gesamtzeit, Stundensatz, Kosten, Quelle und die Berechnung. Die Beträge sind dieselben wie in der "
           "Kalkulation; jede Kostenart kommt genau einmal vor. Programmierung, Gewinde mit Festpreis und "
           "Zusatzarbeiten stehen als Betrag <i>ohne Zeit</i> darin.")
    i.bild("erg_zeiten", "Reiter Zeiten & Arbeitskosten mit Beispielzeiten (Beispielwerte, keine gemessenen Zeiten)",
           hoehe=95 * mm, legende=[
               (1, "<b>Alle Arbeitsschritte zeigen</b>: auch Schritte ohne Zeit und Kosten (sonst ausgeblendet, "
                   "Laser schneiden immer sichtbar)."),
               (2, "<b>Stundensätze aus Einstellungen</b>: Stundensätze und Zeitvorgaben dieses Angebots auf die "
                   "aktuellen Einstellungen setzen (eigene Werte des Angebots gehen verloren)."),
               (3, "Summen: Maschinenzeit, Personalzeit, Rüstzeit, Bearbeitungszeit, Durchlaufzeit (parallele "
                   "Personalzeit nicht addiert), Arbeitskosten, Material, Zuschläge, Herstellkosten, Gewinn, "
                   "Verkaufspreis. Werte mit 0 sind ausgeblendet.")])
    i.liste("Gelbe Felder gelten nur für dieses Angebot: Rüstzeit und Zeit je Einheit der weiteren Arbeitsschritte "
            "und der Stundensatz (er gilt dann für alle Schritte dieses Angebots mit demselben Satz). Die Quelle "
            "zeigt dann <i>von Hand (Angebot)</i>.",
            "Ältere Angebote ohne gespeicherte Stundensätze rechnen mit den aktuellen Einstellungen; der Reiter "
            "sagt das. Die erste Änderung oder <i>Stundensätze aus Einstellungen</i> speichert sie im Angebot.",
            "Die Übersicht rechts oben zeigt Maschinenzeit, Personalzeit, Rüstzeit, Durchlaufzeit und "
            "Arbeitskosten; das Kalkulations-PDF und der CSV-Export enthalten die Tabelle der Arbeitsschritte mit "
            "Zeit oder Kosten.",
            "Die Zeiten sind Vorgabewerte aus Schneiddaten, Maschinen und Arbeitsschritten, keine gemessenen "
            "Zeiten. Ist-Zeiten gehören in die Nachkalkulation ([[nachkalkulation]]).")
    i.abschnitt("Schneidweg-Rechner", marke="schneidweg_rechner")
    i.text("Für Teile ohne STEP-Datei rechnet der <b>Schneidweg-Rechner</b> Schneidweg, Einstiche und Konturklassen "
           "aus wenigen Angaben. Eine Position markieren und <b>Schneidweg berechnen …</b> wählen (Rechtsklick auf "
           "die Position oder <i>Weitere Aktionen</i>). Das Profil muss in den Stammdaten stehen.")
    i.bild("schneidweg_dialog", "Schneidweg-Rechner: Gehrung 45° am Anfang, Bohrungen, Langlöcher und ein Rechteck",
           hoehe=110 * mm, legende=[
               (1, "<b>Gehrung</b> je Ende in Grad (0 = gerade), bei Quadrat-/Rechteckrohr mit Richtung."),
               (2, "<b>Innenkonturen</b>: Art, Anzahl je Teil und Maße; der Tooltip jeder Zelle nennt das Maß."),
               (3, "<b>+ Bohrung</b>, <b>+ Langloch</b> … fügt eine Zeile hinzu, <b>Markierte entfernen</b> löscht."),
               (4, "<b>Ergebnis je Teil</b>: jeder Schnitt mit Länge, Einstichen, Hüllmaß und Konturklasse."),
               (5, "Schneidweg, Einstiche, Klassen und Schneidzeit je Teil; Hinweise und Fehler in Farbe.")])
    i.liste("<b>Anfangs- und Endschnitt</b>: Gehrung in Grad als Abweichung vom rechtwinkligen Schnitt (0° = gerade, "
            "höchstens 79,9°). Rundrohr: Schnittlänge als Ellipse; Quadrat- und Rechteckrohr: wählbar, ob die "
            "Gehrung <i>über Höhe</i> oder <i>über Breite</i> läuft (2 × gekippte Seite / cos Winkel + 2 × andere "
            "Seite). Bei anderen Profilen (Träger, U, Winkel, Flach) ist die Gehrung eine <i>Schätzung</i>: gerade "
            "Schnittlänge / cos Winkel; der Dialog kennzeichnet sie. Je Ende zählen die Einstiche wie beim "
            "STEP-Import (Träger und U-Profil 4, T-Profil 2, sonst 1).",
            "<b>Innenkonturen</b> mit Anzahl je Teil: <i>Bohrung</i> (Ø: π × d), <i>Langloch</i> (Länge, Breite: "
            "2 × (l − b) + π × b), <i>Rechteck</i> (Breite, Höhe, Eckradius: 2 × (b + h) − 8 r + 2 π r), "
            "<i>Schlitz</i> offen vom Rand (Tiefe, Breite: 2 × l + b) und <i>sonstige Kontur</i> mit Schnittlänge "
            "von Hand und Hüllmaß (leer = groß). Jede Kontur ist ein Einstich. Unmögliche Maße (Langloch kürzer als "
            "breit, Eckradius über der halben Seite) werden rot gemeldet, <i>In Position übernehmen</i> ist dann "
            "gesperrt.",
            "<b>Gravur</b>: Länge in mm, wird mit dem Vorschub Gravur gerechnet.",
            "Unter <i>Ergebnis je Teil</i> stehen sofort alle Schnitte mit Länge, Einstichen, Hüllmaß und Klasse "
            "(klein/mittel/groß nach den Konturgrenzen der Maschine, [[konturklassen]]), darunter Schneidweg und "
            "Schneidzeit je Teil mit den Schneiddaten der Maschine. Ohne passende Schneiddaten erscheint ein "
            "Hinweis; das Programm erfindet keine Werte, die Schneidzeit wird dann von Hand eingetragen.",
            "<b>In Position übernehmen</b> schreibt Schneidweg, Einstiche, Anfangs-/Endschnitt (gerade ja/nein), "
            "Innenkonturen, Gravur, Konturliste und Konturklassen in die Position, also dieselben Felder wie der "
            "STEP-Import. Hat die Position schon Werte aus dem STEP-Import, fragt das Programm vorher. Die Eingaben "
            "bleiben gespeichert und erscheinen beim nächsten Öffnen wieder.",
            "Eine von Hand eingetragene Schneidzeit gilt weiter, bis sie in der Positionsliste gelöscht wird.")
    i.abschnitt("Konturklassen in der Schneidzeit", marke="konturklassen")
    i.text("Der STEP-Import teilt jede Innenkontur und auch den <b>Anfangs- und Endschnitt</b> nach ihrer Größe "
           "(Hüllmaß) in <b>klein</b>, <b>mittel</b> oder <b>groß</b> ein; die Grenzen stehen je Maschine in den "
           "Stammdaten Maschinen (Vorgabe 10 und 50 mm, ein Wert genau auf der Grenze zählt zur kleineren Klasse). "
           "Gerechnet wird dann der <b>Schnittweg</b> jeder Klasse mit ihrem Vorschub aus den Schneiddaten:")
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
            "der Klasse des geraden Endes abgezogen.")
    i.text("Die Liste aller Konturen steht in der Position (Spalte <i>Konturen Hüllmaß x Schnittweg [mm]</i>). "
           "Wird im Angebotskopf eine andere Maschine gewählt oder ändern sich die Grenzen in den Stammdaten, teilt "
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
    i.bild("angebot_zusatz", "Positionen mit Zusatzarbeiten und angepasster Schneidzeit", hoehe=110 * mm, legende=[
        (1, "Spalte <b>Schneidzeit je Teil [s]</b>: grau berechnet, fett angepasst."),
        (2, "Spalte <b>Zusatzarbeiten</b>: Doppelklick öffnet die Auswahl."),
        (3, "Status <b>HINWEIS: Schneidzeit manuell</b>.")])
    i.abschnitt("Schnittplan")
    i.text("Oben stehen alle Stangen mit Belegung, Rest und Ausnutzung. Ein Klick auf eine Stange zeigt unten ihre "
           "Teile in Schnittreihenfolge mit Lage (von/bis), Drehung und Art der Trennung.")
    i.bild("erg_schnittplan", "Reiter Schnittplan, Stange 3 gewählt", hoehe=85 * mm)
    i.abschnitt("Stangenbild")
    i.text("Jede Stange als maßstäblicher Balken: Endbeschnitt grau, Teile farbig mit Positionsnummer und Länge, "
           "dicke Linie = Schnitt, Rest hellgrau, Greiferrest rot. Gleich belegte Stangen stehen einmal da "
           "(<i>2 × Stange 1, 2</i>).")
    i.bild("erg_stangenbild", "Reiter Stangenbild", hoehe=85 * mm)
    i.abschnitt("Auswertung und nicht eingeplante Teile")
    i.text("Je Gruppe (Profil + Werkstoff + Stangenlänge): Stangen optimiert gegen eine einfache manuelle Einteilung "
           "(Eingabereihenfolge, Stange voll, dann nächste), die rechnerische Untergrenze, Ersparnis, Verschnitt, "
           "Ausnutzung und eine Bewertung, ob das Ergebnis nachweislich optimal ist.",
           "Darunter stehen die <b>nicht eingeplanten Teile</b> mit Grund, z. B. Teil länger als die Nutzlänge der "
           "Stange, Profil über der Maschinengrenze oder fehlende Angaben. Diese Teile fehlen in Schnittplan, "
           "Kalkulation und Angebot, bis der Grund behoben ist.")
    i.bild("erg_auswertung", "Reiter Auswertung", hoehe=85 * mm)
    i.abschnitt("Lieferlängen: 6 m gegen 12 m", marke="lieferlaengen")
    i.text("Gibt es für ein Profil + Werkstoff weitere Lieferlängen (Stammdaten <i>Lieferlängen</i>, z. B. "
           "12.000 mm), plant das Programm beim Optimieren jede Länge unter gleichen Bedingungen (gleiche Teile, "
           "Endbeschnitt, Greiferrest, Schnittverlust, gemeinsame Schnitte) und vergleicht sie im Reiter "
           "<i>Auswertung</i> unter <b>Lieferlängen: 6 m gegen 12 m</b>. Ohne Eintrag gilt das für Profile mit "
           "Hüllkreis-Ø über 70 mm (Einstellung). Kleinere Profile ohne Eintrag und Profile mit "
           "<i>Lieferlängen vergleichen = nein</i> werden nie mit 12 m geplant.")
    i.liste("<b>Die Maschine lädt nie eine 12-m-Stange.</b> Ist eine Lieferlänge länger als die <i>Max. "
            "Stangenlänge</i> der Maschine (Beladelänge, T03: 6.500 mm), schneidet der Lieferant jede Stange in "
            "Werkstücke, die einzeln geladen werden, z. B. 3 × 4.000 mm, 2 × 6.000 mm oder 6.500 + 5.497 mm. Kein "
            "Werkstück ist länger als die Beladelänge.",
            "Ein Werkstück = Endbeschnitt + Teile + Trennschnitte + Schnittverlust + Greiferrest, auf ganze mm "
            "aufgerundet. Zwischen zwei Werkstücken geht der Schnittverlust des Zuschnitts verloren (Einstellung, "
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
           "gleich. Die Tabelle zeigt je Variante Stangen, Beladungen, Zuschnitte, Werkstücklängen, Materiallänge, "
           "Materialkosten, Stangenwechsel, Zuschnittkosten, Reststückwert (nicht angerechnet), Gesamtkosten, "
           "Verschnitt in mm und % und fehlende Angaben.")
    i.bild("erg_lieferlaengen", "Reiter Auswertung, Lieferlängen: 30 Stützen 3.100 mm, 12 m spart ein Drittel "
                                "Material", hoehe=110 * mm,
           legende=[(1, "Vergleich je Gruppe mit Empfehlung, Begründung und Link zum Übernehmen")])
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
    i.bild("erg_lieferlaengen_bild", "Stangenbild nach dem Übernehmen: je 12-m-Stange drei Werkstücke mit eigenem "
                                     "Endbeschnitt und Greiferrest", hoehe=80 * mm)
    i.liste("Schnittplan: Spalten <i>Werkstücke (Beladungen)</i> und <i>Zuschnitt beim Lieferanten</i> (z. B. "
            "„Zuschnitt beim Lieferanten: 3.253 + 3.253 + 3.253 mm, Rest 2.235 mm“); je Teil die Spalte "
            "<i>Werkstück</i>.",
            "Werkstattpapiere: Materialliste mit den 12-m-Stangen, je Stange der Zuschnitt; Von/Bis der Teile gelten "
            "im Werkstück, die Lage nennt das Werkstück (W1, W2 …).",
            "Staffelpreise: je Mengenstufe vergleicht das Programm selbst und nimmt die empfohlene Lieferlänge "
            "([[staffeln]]).")
    i.bild("erg_lieferlaengen_geplant", "Nach dem Übernehmen: 12-m-Variante geplant, Link zurück auf 6 m",
           hoehe=90 * mm)


def kapitel_staffeln(i):
    i.kapitel("Staffelpreise", marke="staffeln")
    i.text("Im Reiter <i>Staffeln</i> rechnet das Programm Preise für andere Mengen. Jede Mengenstufe wird als "
           "eigenes Angebot neu optimiert und kalkuliert, weil Rüsten, Stangenwechsel und Verschnitt je Menge neu "
           "anfallen. Das eigentliche Angebot bleibt unverändert. Jede Stufe kann eigene Werte haben "
           "(Materialzuschlag, Gewinn, Nebenkosten …); leere Felder nehmen den Wert des Angebots.")
    i.text("Gibt es für ein Profil weitere Lieferlängen (z. B. 12 m, [[lieferlaengen]]), "
           "vergleicht das Programm sie für jede Mengenstufe neu und nimmt automatisch die empfohlene, also nur bei "
           "ausreichender Ersparnis die längere. Bei kleinen Mengen bleibt es so oft bei 6 m, bei großen kann es 12 m "
           "sein; die Spalte Stangen zeigt die Anzahl der geplanten Stangen.")
    i.bild("staffeln_vorher", "Mengenstufen für den Satz „MG 2000“ (ein Maschinengestell)", hoehe=80 * mm, legende=[
        (1, "<b>Neue Stufe</b> fügt eine Zeile an; <b>Stufen löschen</b> entfernt die markierten."),
        (2, "<b>Stufen aus Angebot</b> legt für jeden Satz und jede Position ohne Satz, die noch fehlt, eine Stufe "
            "mit der Menge aus dem Angebot an. Weitere Mengen danach mit <b>Neue Stufe</b> ergänzen."),
        (3, "Je Zeile: <b>Satz oder Pos.</b> per Doppelklick aus der Liste wählen; die Liste zeigt alle Sätze "
            "(mit ihren Positionen) und alle Positionen ohne Satz dieses Angebots. Eintippen geht weiterhin. Dazu "
            "<b>Menge ab</b> in Sätzen bzw. Stück, <b>Materialzuschlag</b>, <b>Zuschlag in</b> (% oder €/Einheit), "
            "<b>Gewinn</b> und Bemerkung. Graue Werte gelten, solange das Feld leer ist. Die Prüfung zeigt, was "
            "erkannt wurde, oder den Fehler."),
        (4, "<b>Staffelpreise rechnen</b> rechnet alle Stufen neu. Nötig ist das selten: Zuschläge wirken sofort, "
            "neue Mengen und Änderungen am Angebot rechnet das Programm nach kurzer Zeit im Hintergrund nach."),
        (5, "<b>Erweiterte Einstellungen</b> zeigt die übrigen Felder je Stufe (Tabelle unten). Spalten, in denen "
            "eine Stufe einen Wert hat, bleiben immer sichtbar.")])
    i.text("Für Sätze in den Positionen die Spalten <b>Satz</b> (gleicher Name für alle Teile des Satzes) und "
           "<b>Stück je Satz</b> ausfüllen. Im Beispiel gehören zu einem Gestell 4 Stiele, 4 lange Riegel, "
           "8 kurze Riegel, 16 Streben, 2 Holme und 3 Traversen.")
    i.abschnitt("Werte je Stufe")
    i.tabelle(["Feld", "Bedeutung (leer = …)"], [
        ["Menge ab", "Kalkulationsmenge der Stufe (Mindestmenge) in Sätzen bzw. Stück; Pflicht"],
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
        ["Rüstkosten", "umlegen (leer) = im Stückpreis; separat = als einmalige Rüstkosten neben dem Stückpreis"],
        ["Zusätzlicher Arbeitsgang", "Bezeichnung, Arbeitsgang [min/Einheit] mit Arbeitsgang Stundensatz "
                                     "(leer = Maschinenstundensatz) und/oder Arbeitsgang [€/Einheit]"],
        ["Verpackung / Nebenkosten", "€/Einheit und Nebenkosten pauschal € für die Stufe; zählen zu den "
                                     "Selbstkosten"],
        ["Rabatt erlaubt", "ja = negativer Materialzuschlag und negativer Gewinn sind erlaubt (sonst abgelehnt)"],
    ], [55 * mm, 200 * mm])
    i.abschnitt("Rechenweg je Stufe")
    i.liste("<b>Material-Grundkosten</b>: Stangenkosten dieser Menge inkl. echtem Verschnitt (oder Grundpreis "
            "abweichend × Menge).",
            "<b>Materialverlust</b>: Grundkosten × Verlust %.",
            "<b>Materialzuschlag</b>: (Grundkosten + Verlust) × Zuschlag % oder Zuschlag € × Menge.",
            "<b>Fertigungskosten</b>: je Arbeitsschritt Zeit × Stundensatz (Reiter Zeiten &amp; Arbeitskosten) plus "
            "zusätzlicher Arbeitsgang; <b>Rüsten</b> (Rüstzeiten × Stundensatz) einmal je Stufe, getrennt davon.",
            "<b>Gemeinkosten</b>: (Fertigung + Rüsten) × Gemeinkosten Fertigung; Fremdleistung × Zuschlag "
            "Fremdleistung.",
            "<b>Selbstkosten</b> = Material + Fertigung + Rüsten + Gemeinkosten + Fremdleistung + Verpackung / "
            "Nebenkosten.",
            "<b>Gewinn</b> = Selbstkosten × Gewinn %; dazu als <b>Weitere Kosten</b> Pauschalen, Programmierkosten, "
            "Angebotsaufschlag und Fracht ohne Zuschläge, Skonto eingerechnet = <b>Gesamtpreis netto</b>; dazu Umsatzsteuer = "
            "<b>Gesamtpreis brutto</b>.", nummeriert=True)
    i.text("Gerechnet wird ungerundet; erst der Verkaufspreis netto je Einheit wird auf Cent gerundet "
           "(kaufmännisch), der Gesamtpreis ist Stückpreis × Menge (plus einmalige Rüstkosten). Ohne Werte je Stufe "
           "ergibt das genau den Preis der Kalkulation.")
    i.text("<b>Fracht je Menge</b>: Mit der Frachtart <i>berechnet</i> (Karte Fracht im Angebot) rechnet jede Stufe "
           "ihre eigene Fracht: Nettogewicht und längstes Teil der Stufe, Ladungsträger per Packvorschlag, Fracht mit "
           "der gespeicherten Tarifkopie des Angebots. Verpackungsgewicht und frachtpflichtiges Gewicht von Hand "
           "gelten nur für die Menge des Angebots; die Stufen rechnen nach Tarif. Der Hinweis der Stufe nennt die "
           "Fracht, das Bruttogewicht und die Ladungsträger, z. B. „Fracht 445,48 €: 1.081,5 kg brutto, 1 × LG“. "
           "Innerhalb der Stufe wird die Fracht wie im Angebot je Stück oder nach Gewicht verteilt. Ändert sich die "
           "Frachtberechnung, sind die Stufen veraltet und werden neu gerechnet. Fehlt die Berechnung oder ein "
           "Gewicht, bekommt die Stufe keinen Preis und den Hinweis „Fracht nicht berechnet: …“, statt still mit "
           "0 € zu rechnen. In den übrigen Frachtarten gilt der Frachtbetrag des Angebots für alle Mengen gleich.")
    i.bild("staffeln", "Ergebnis mit Materialzuschlag 20/15/10/5 %: der Preis je Gestell sinkt mit der Menge",
           hoehe=95 * mm, legende=[
               (1, "Wert direkt in der Stufe ändern: der Preis rechnet sofort neu, ohne neue Optimierung."),
               (2, "Kostenpositionen in Gruppen; ▸ klappt sie auf (<b>Alle aufklappen</b> öffnet alle). Je Stufe "
                   "zwei Spalten: € je Einheit und gesamt."),
               (3, "<b>Selbstkosten</b>"),
               (4, "<b>Verkaufspreis netto je Einheit</b>, darunter Gewinn und Gewinnmarge (vom Nettopreis)."),
               (5, "<b>Gesamtpreis netto</b>, <b>Umsatzsteuer</b> und <b>Gesamtpreis brutto</b>."),
               (6, "Vergleich: Verkaufspreis netto je Einheit über die Mengen, je Satz bzw. Position."),
               (7, "Stand: aktuell, VERALTET (wird im Hintergrund neu gerechnet) oder Stufen mit FEHLER.")])
    i.bild("staffeln_details", "Aufgeklappt mit erweiterten Einstellungen: Arbeitsschritte, Rüsten separat, "
                               "Nebenkosten", hoehe=95 * mm, legende=[
               (1, "Fertigung je Arbeitsschritt; der Tooltip zeigt Zeit und Stundensatz."),
               (2, "Rüsten Maschine, Rüsten je Abmessung und Rüstzeiten weiterer Arbeitsschritte."),
               (3, "Gemeinkosten mit ihrer Basis."),
               (4, "Einmalige Rüstkosten (Rüstkosten = separat): nicht im Stückpreis, aber im Gesamtpreis."),
               (5, "Änderung des Preises je Einheit zur letzten Eingabe, in € und %.")])
    i.abschnitt("Prüfung und Fehler")
    i.liste("Rot markiert und mit FEHLER in der Prüfung: Menge fehlt, Menge doppelt (gleicher Satz bzw. Position), "
            "Menge bis kleiner als Menge ab, sich überschneidende Mengenbereiche, Prozentwerte außerhalb des "
            "zulässigen Bereichs, negative Werte ohne „Rabatt erlaubt“.",
            "Fehlt der Materialpreis (keine Preise in den Stammdaten, kein Schnittplan), rechnet das Programm nicht "
            "mit 0: die Stufe zeigt „FEHLER: Materialpreis fehlt“ und bekommt keinen Preis.",
            "Stufen mit FEHLER kommen nicht ins Angebot.")
    i.text("Die Staffelpreise erscheinen im Angebot als Preistreppe unter den Positionen, mit Mengenbereich "
           "(z. B. „1“, „2–4“, „ab 10“) und gegebenenfalls einmaligen Rüstkosten. Ändert sich etwas am "
           "Angebot, zeigt der Reiter VERALTET und rechnet nach; das Angebot rechnet veraltete Staffelpreise "
           "vor dem Drucken ebenfalls selbst neu. Ältere Angebote rechnen unverändert weiter: ihre Stufen haben "
           "leere Felder, also die Werte des Angebots. Vor dem Umstellen einer älteren Datendatei legt das "
           "Programm eine Sicherung „vor_Schema_14“ im Ordner Sicherung an.")


def kapitel_fracht(i):
    i.kapitel("Fracht im Angebot", marke="fracht")
    i.text("Die Fracht kommt auf zwei Wegen ins Angebot: über die Karte <b>Fracht</b> im Angebot (manuell, "
           "berechnet oder automatisch) und über den Frachtrechner im Reiter <i>Frachtkosten</i>. Zonen, Tarife, "
           "Ladehilfsmittel und Zuschläge, mit denen gerechnet wird, werden im Reiter <i>Frachtkosten</i> gepflegt "
           "([[frachtkosten]]).")
    i.abschnitt("Karte Fracht im Angebot", marke="fracht_angebot")
    i.text("Unter der Kalkulation steht die Karte <b>Fracht</b>. Sie legt fest, wie die Fracht in dieses Angebot "
           "eingeht.")
    i.bild("angebot_fracht", "Karte Fracht: Frachtart berechnet, verteilt nach Gewicht", hoehe=40 * mm, legende=[
        (1, "<b>Frachtart</b>"), (2, "<b>Fracht verteilen</b>"), (3, "<b>Fracht berechnen …</b>"),
        (4, "Betrag, Tarif, Gewicht, Ladungsträger und Ziel der Berechnung"),
        (5, "<b>Fracht automatisch berechnen</b> mit Ziel-PLZ und Land (unten)")])
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
    i.liste("Beim Setzen des Hakens kommen Ziel-PLZ (zwei Stellen) und Land aus dem Kunden: abweichende "
            "Lieferanschrift, sonst PLZ bzw. PLZ Ort der Anschrift. Wechselt der Kunde, wechselt auch das Ziel.",
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
            "Karte, das Feld Frachtkosten ist leer, die Kalkulation rechnet bis dahin ohne Fracht und vor dem "
            "Angebots-PDF fragt das Programm nach. Es setzt nie still 0 € ein. Ist der Grund behoben (Gewicht "
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
    i.text("Eingekaufte Teile kommen auf zwei Arten ins Angebot: als eigene <b>Zukaufteil-Position</b> (z. B. ein "
           "Blech, das mitgeliefert wird) oder als <b>Zukaufteile an einer Position</b> (z. B. Schrauben je Rahmen). "
           "Die Artikel selbst, ihre Preise und Aufschläge werden im Reiter <i>Zukaufartikel</i> gepflegt "
           "([[zukauf]]).")
    i.abschnitt("Zukaufteil-Positionen", marke="zukauf_positionen")
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
    i.bild("angebot_berechnet", "Mit Häkchen „Berechnete Werte“: Gewicht, Laserzeit, Stück- und Positionspreis je "
                                "Zeile", hoehe=125 * mm)
    i.abschnitt("Zukaufteile an Positionen", marke="zukauf_angebot")
    i.text("Zukaufteile gehören zu einer Position: <i>Menge je Teil</i> × Stückzahl der Position ergibt den "
           "Verbrauch. Mit <i>je Satz</i> gilt die Menge je Satz: <i>Menge je Satz</i> × Sätze (Stückzahl ÷ Stück "
           "je Satz der Position). Beispiel Rahmen aus Rohren mit 20 Blechen: die Bleche an eine Rohrposition des "
           "Satzes hängen, Menge 20 je Satz; bei 10 Rahmen rechnet das Angebot 200 Bleche, die Staffelstufe 50 "
           "Rahmen 1000. Ohne Satzangabe zählt jedes Teil als ein Satz. Position(en) markieren und <b>Zukaufteile … → Zukaufteile bearbeiten …</b> wählen oder in der Spalte "
           "<i>Zukaufteile</i> doppelklicken. Umgekehrt übernimmt <b>In Angebot übernehmen …</b> im Unterreiter "
           "Artikel den markierten Artikel in eine Position: Angebot und Position wählen, Menge je Teil eingeben. "
           "Archivierte Artikel lassen sich nicht übernehmen.")
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


def kapitel_ausgabe(i, seiten, ablage):
    i.kapitel("Ausgabe: Angebot, Werkstattpapiere, Kalkulation", marke="ausgabe")
    i.text("Die Knöpfe rechts neben <b>Ausgabe</b> im Angebot erzeugen die Unterlagen. Jede Datei wird im Ablageordner gespeichert "
           "und gleich geöffnet. Ist die Optimierung veraltet, fragt das Programm vorher.")
    i.bild("ausgabe_leiste", hoehe=60 * mm, legende=[
        (1, "<b>Angebot (PDF)</b>: Briefkopf, Kunde mit Anschrift aus dem Kundenstamm, Positionen mit "
            "Bezeichnung, Stück- und Gesamtpreis, Sätze, Summe mit MwSt., Preistreppe der Staffeln, "
            "Ihre Anfrage (Kundenreferenz), Lieferzeit ([[lieferzeit]]), Zahlungsbedingung (z. B. „Zahlung innerhalb "
            "10 Tagen mit 2 % Skonto oder innerhalb 30 Tagen netto.“), ggf. „Mindestauftragswert 200,00 € netto.“ "
            "([[mindestpreis]]) und Bedingungen. Stückpreise sind kaufmännisch auf den Cent gerundet (2,675 € → 2,68 €); der "
            "Gesamtpreis jeder Zeile ist Stückpreis × Menge, die Summe genau die Summe der Zeilen."),
        (2, "<b>Werkstattpapiere (PDF)</b>: Materialliste und je Stangenmuster der Schnittplan zum Abhaken, "
            "danach das Stangenbild."),
        (3, "<b>Kalkulation (PDF)</b>: alle Kalkulationswerte je Position für die interne Ablage, dazu die "
            "Schneidzeit je Teil nach Konturklassen (Schneidweg, Vorschub und Zeit je Klasse)."),
        (4, "<b>Weitere Aktionen</b>: <b>CSV-Export</b> schreibt Angebotskopf, alle Kostenarten und die "
            "Kalkulation je Position als CSV-Datei (Semikolon, Dezimalkomma), z. B. zum Weiterverarbeiten in einer "
            "Tabellenkalkulation; <b>Ablage öffnen</b> zeigt den Ablageordner im Explorer.")])
    i.text("<b>Angebotstext einer Position</b>: jede Angabe steht in einer eigenen Zeile, nicht hintereinander. "
           "Reihenfolge: Profil, Länge, Werkstoff (<i>inkl. Material</i> mit dem Text im Angebot des Werkstoffs), "
           "Oberfläche, dann je Zusatzarbeit, Gewinde oder Gravur eine Zeile <i>inkl. …</i> und je Zukaufteil mit "
           "<i>im Angebotstext der Position nennen</i> eine Zeile mit Menge je Teil, z. B.:<br/>"
           "<i>Quadratrohr 40 x 40 x 3<br/>L = 550 mm<br/>inkl. Material S235 EN10219<br/>inkl. Gewinde 4xM6<br/>"
           "inkl. Senken</i><br/>"
           "Bei Sätzen steht der Text jedes Satzteils eingerückt unter der Satzzeile.")
    i.text("Die Dateien heißen nach der Angebotsnummer, z. B.: " + ", ".join(f"<i>{a}</i>" for a in ablage) + ".")
    i.abschnitt("Preise festschreiben", marke="preise_festschreiben")
    i.text("Beim Erzeugen des <b>Angebots-PDF</b> speichert das Programm im Angebot die Materialpreise und "
           "Schneiddaten, mit denen es gerechnet hat: die Zeilen aus <i>Preise</i> je Profil + Werkstoff der "
           "Positionen (auch, dass es keine Zeile gab und der Tonnenpreis galt), die Tonnenpreise der Werkstoffe, "
           "die Aufpreise der Oberflächen und die Schneiddaten der gewählten Maschine. Ändern sich danach die "
           "Stammdaten, z. B. der Stahlpreis, bleibt der Preis des Angebots wie im PDF beim Kunden.")
    i.liste("Neue Positionen mit anderem Profil, Werkstoff oder anderer Oberfläche rechnen mit den aktuellen "
            "Stammdaten; das nächste Angebots-PDF nimmt sie dazu, schon festgeschriebene Werte bleiben.",
            "Wird eine andere Maschine gewählt, gelten deren aktuelle Schneiddaten.",
            "<b>Aktuelle Preise übernehmen …</b> in der Übersicht (nur sichtbar, wenn die Stammdaten abweichen) "
            "zeigt die Änderungen und setzt das Angebot nach Rückfrage auf die aktuellen Stammdaten; der Preis "
            "ändert sich dann. Das nächste Angebots-PDF schreibt die neuen Werte wieder fest.",
            "Eine <b>Kopie</b> eines Angebots rechnet mit den aktuellen Stammdaten.",
            "Stundensätze und Zeitvorgaben sind schon beim Anlegen im Angebot gespeichert ("
            "[[zeiten]]), Zusatzarbeiten und Zukaufteile mit ihrem Preisstand.")
    i.abschnitt("Angebot (PDF)")
    i.bilder_nebeneinander(["pdf_angebot_1"], "Angebot A-2026-0041 (Seite 1)", hoehe=150 * mm)
    i.abschnitt("Werkstattpapiere (PDF)")
    letzte = f"pdf_werkstatt_{seiten['werkstatt']}"
    i.bilder_nebeneinander(["pdf_werkstatt_1", letzte],
                           "Werkstattpapiere: Materialliste und Schnittpläne (links), Stangenbild (rechts)",
                           hoehe=150 * mm)
    i.text("Hat das Angebot Zukaufteil-Positionen (z. B. Bleche), steht unter der Materialliste die Liste "
           "<i>Zukaufteile (nicht lasern, zum Auftrag bereitstellen)</i> mit Pos., Artikelnummer, Bezeichnung, "
           "Zukaufartikel und Stückzahl.")
    i.abschnitt("Kalkulation (PDF)")
    i.bilder_nebeneinander(["pdf_kalkulation_1"], "Kalkulation A-2026-0041", hoehe=150 * mm)


def kapitel_nachkalkulation(i):
    i.kapitel("Nachkalkulation", marke="nachkalkulation")
    i.text("Nach dem Auftrag zeigt der Reiter <i>Nachkalkulation</i>, ob die Kalkulation gestimmt hat. Eingetragen "
           "werden die tatsächlichen Werte; das Programm stellt sie den Werten aus Schnittplan und Kalkulation (Soll) "
           "gegenüber. Verglichen werden die <b>Einzelkosten</b> ohne Zuschläge und Gewinn, denn nur sie lassen sich "
           "in der Fertigung messen. Voraussetzung ist ein aktueller Schnittplan (vorher optimieren).")
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
        (4, "<b>Nachkalkulation (PDF)</b> speichert den Vergleich im Ablageordner. <b>Ist-Werte löschen</b> setzt "
            "alles zurück.")])
    i.liste("Jede Eingabe wird sofort gespeichert. Leere Felder zählen wie kalkuliert; die Spalte <i>Ist erfasst</i> "
            "zeigt, welche Werte wirklich eingetragen sind.",
            "Im Reiter <i>Angebote</i> zeigt die Spalte <b>Nachkalkuliert</b>, für welche Angebote Ist-Werte "
            "vorliegen. Beim Kopieren werden die Ist-Werte nicht mitkopiert.",
            "Ein positiver Wert in <i>Abweichung</i> heißt: teurer als kalkuliert. Wiederholt sich das bei einer "
            "Kostenart, lohnt ein Blick in die Stammdaten (Schneiddaten, Rüstzeiten, Preise).")
    i.bilder_nebeneinander(["pdf_nachkalkulation_1"], "Nachkalkulation als PDF", hoehe=150 * mm)


def kapitel_einstellungen(i):
    i.kapitel("Einstellungen", marke="einstellungen")
    i.text("Der Reiter <i>Einstellungen</i> enthält alle Voreinstellungen: den Unterreiter <i>Vorgaben</i> mit den "
           "Werten, die für alle Angebote gelten, und die Stammdaten außer den Kunden ([[stammdaten]]).")
    i.abschnitt("Passwort", marke="passwort")
    i.text("Der Reiter öffnet sich erst nach Eingabe des Passworts. Passwort eintippen und Enter oder "
           "<b>Einstellungen öffnen</b> drücken. Er bleibt offen, bis <b>Einstellungen sperren</b> gedrückt oder das "
           "Programm beendet wird. Das Passwort steht unter Vorgaben, Gruppe Zugang (<i>Passwort für die "
           "Einstellungen</i>); leer = Einstellungen ohne Passwort. Das Passwort bitte beim Verantwortlichen "
           "erfragen.")
    i.bild("einstellungen_gesperrt", "Reiter Einstellungen gesperrt", hoehe=45 * mm, legende=[
        (1, "Reiter Einstellungen"), (2, "Passwort eingeben"), (3, "<b>Einstellungen öffnen</b>")])
    i.abschnitt("Vorgaben", marke="vorgaben")
    i.text("Änderungen werden beim Verlassen des Feldes gespeichert und wirken ab der nächsten Rechnung. "
           "Ausnahme: Stundensätze und Zeitvorgaben ([[stundensaetze]]) speichert jedes Angebot beim Anlegen.")
    i.bild("einstellungen", "Einstellungen, Unterreiter Vorgaben (oberer Teil)", hoehe=125 * mm, legende=[
        (1, "Unterreiter Vorgaben, daneben die Stammdaten"), (2, "<b>Einstellungen sperren</b>")])
    i.bild("einstellungen_unten", "Einstellungen, Unterreiter Vorgaben (unterer Teil): Briefkopf, Ablage, "
           "Auswahllisten und Passwort", hoehe=110 * mm)
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
        ["Kalkulation", "Programmierkosten je Teil (Position) [€]",
         "einmal je Position mit Stückzahl (Vorgabe 8,50 €), auf deren Stückzahl verteilt, ohne Zuschläge auf den "
         "Preis; bei Staffelpreisen je Mengenstufe"],
        ["Kalkulation", "Pauschale je Abmessung [€], Angebotsaufschlag je Angebot [€]",
         "fester Betrag ohne Zuschläge auf den Preis; verteilt auf die Teile"],
        ["Kalkulation", "Handling Kundenmaterial je kg Stangengewicht [€/kg] (0 = keins)",
         "Kosten für beigestelltes Material je kg der Stangen, mit Zuschlag Fertigung und Gewinn ([[kundenmaterial]]); "
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
        ["Angebot", "Skonto [%], Skontofrist [Tage], Zahlungsziel netto [Tage]",
         "Zahlungsbedingungen neuer Angebote, wenn der Kunde im Kundenstamm keine eigenen hat (Vorgabe 2 % Skonto "
         "bei Zahlung in 10 Tagen, 30 Tage netto). Das Skonto wird in den Preis eingerechnet. Bestehende Angebote "
         "behalten ihre Werte."],
        ["Angebot", "Letzte Angebotsnummer", "Ein neues Angebot bekommt die nächste Nummer (A-2026-0041 → "
                                             "A-2026-0042)."],
        ["Angebot", "STEP-Import: Flachstahl bis Breite [mm] (breitere flache Teile sind Bleche)",
         "Grenze zwischen Flachstahl und Blech beim STEP-Import (Vorgabe 150 mm). Ein flaches Teil gilt nur als "
         "Flachstahl, wenn es höchstens so breit ist, mindestens dreimal so lang wie breit ist und gerade "
         "Längsseiten hat. Alles andere Flache ist ein Blech ([[bleche]])."],
        ["Angebot", "STEP-Import: Standard-Werkstoff für Rohre und Profile (leer = keiner)",
         "Werkstoff, mit dem der STEP-Prüfdialog Rohre und Profile vorbelegt (Vorgabe S235-10219 = S235 EN10219). "
         "Bleche bekommen nie einen Werkstoff vorbelegt. Leer = kein Werkstoff vorbelegt."],
        ["Angebots-PDF", "Briefkopf Zeile 1 (Firma), Briefkopf Zeile 2, Briefkopf Zeile 3, Briefkopf Zeile 4, MwSt.-Satz, "
                    "Gültigkeit, Bedingungen", "Kopf und Text des Angebots-PDF. Die Zahlungsbedingung (Skonto, "
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
        ["Zugang", "Passwort für die Einstellungen", "Passwort für den Reiter Einstellungen und die Pflegebereiche der "
                                                    "Frachtkosten; leer = ohne Passwort"]],
        [28, 80, 157])
    i.abschnitt("Stundensätze und Zeitvorgaben", marke="stundensaetze")
    i.text("Der Unterreiter <i>Stundensätze und Zeitvorgaben</i> zeigt links die <b>Stundensätze</b> und rechts die "
           "<b>Arbeitsschritte</b>. Jeder Arbeitsschritt wird mit genau einem Stundensatz gerechnet; der Satz "
           "<i>Maschine</i> ist der Stundensatz der gewählten Maschine ([[stammdaten]]).")
    i.bild("stamm_arbeitsschritte", "Einstellungen, Stundensätze und Zeitvorgaben (Beispielwerte)", hoehe=95 * mm)
    i.tabelle(["Stundensätze", "Bedeutung"], [
        ["<b>Stundensatz-ID</b>", "Kurzname, z. B. <i>Rüstpersonal</i>; Auswahl in den Arbeitsschritten"],
        ["Bezeichnung", "Klartext, z. B. Arbeitsplatz oder Kostenstelle"],
        ["<b>Stundensatz [€/h]</b>", "Kosten je Stunde; vorbelegt mit Beispielwerten, bitte eigene eintragen"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.tabelle(["Arbeitsschritte", "Bedeutung"], [
        ["<b>Arbeitsschritt</b>", "Name. Laser schneiden, Gewinde, Rüsten Maschine, Rüsten je Abmessung und "
                                  "Stangenwechsel rechnet das Programm selbst (Zeit aus Schneiddaten, Gewinde, "
                                  "Maschine und Vorgaben); dort wird nur der Stundensatz gewählt."],
        ["<b>Stundensatz</b>", "<i>Maschine</i> oder eine Stundensatz-ID. Vorgabe für Gewinde, Rüsten und "
                               "Stangenwechsel ist Maschine (wie bisher), umstellbar z. B. auf Rüstpersonal."],
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
    i.text("Die Programmierung bleibt ein Betrag je Position (<i>Programmierkosten je Teil (Position)</i> unter "
           "Vorgaben), ohne Zeit. Zusatzarbeiten und Gewinde mit Festpreis werden über ihren Preis gerechnet.")
    i.text("<b>Snapshot im Angebot</b>: Ein neues Angebot speichert beim Anlegen alle Stundensätze, die "
           "Arbeitsschritte und Stundensatz, Rüstzeit und Stangenwechsel der Maschine. Spätere Änderungen hier "
           "ändern bestehende Angebote nicht; im Angebot holt sie der Knopf <i>Stundensätze aus Einstellungen</i> "
           "([[zeiten]]). Eine Kopie übernimmt die Werte des Originals. Wird die Maschine eines Angebots "
           "gewechselt, gelten deren aktuelle Werte.")


def kapitel_stammdaten(i):
    i.kapitel("Stammdaten und Kunden", marke="stammdaten")
    i.abschnitt("Tabellen bearbeiten")
    i.text("Die Kunden haben einen eigenen Reiter. Alle anderen Stammdaten (Profile, Werkstoffe, Oberflächen, Preise, "
           "Maschinen, Schneiddaten, Gewinde, Zusatzarbeiten, Stundensätze und Arbeitsschritte) stehen als Unterreiter "
           "im Reiter <i>Einstellungen</i>, "
           "der mit einem Passwort geschützt ist ([[passwort]]). Alle Tabellen sind gleich aufgebaut:")
    i.bild("stamm_profile", "Einstellungen, Unterreiter Profile", hoehe=125 * mm, legende=[
        (1, "Unterreiter der Tabelle. Oben steht ein kurzer Hinweis, was in die Spalten gehört."),
        (2, "<b>Neue Zeile</b> hängt eine leere Zeile an und springt hinein."),
        (3, "<b>Zeilen löschen</b> löscht die markierten Zeilen (vorher Rückfrage; verweisen andere Tabellen "
            "darauf, sagt das Programm wie viele)."),
        (4, "<b>Suchen</b> filtert die Tabelle nach jedem Text in jeder Spalte."),
        (5, "<b>Prüfung</b>: OK, WARNUNG oder FEHLER mit Begründung.")])
    i.liste("Bearbeiten: Zelle doppelklicken oder einfach lostippen, mit Enter bestätigen. Felder mit fester Auswahl "
            "(Profilform, Preisbasis, Profil-ID …) zeigen eine Liste.",
            "Sortieren: auf den Spaltenkopf klicken. Spaltenbreite: Trennlinie im Kopf ziehen.",
            "Wird eine Profil-, Werkstoff- oder Maschinen-ID umbenannt, ändern sich die Verweise in Preisen und "
            "Schneiddaten mit. Bei einer Maschinen-ID ändern sich auch die Angebote (mit ihren festgeschriebenen "
            "Werten) und die Standard-Maschine mit.")
    i.abschnitt("Was in welche Tabelle gehört")
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
        ["Gewinde", "Gewinde, Kernloch-Ø, Zeit je Gewinde, Preis je Gewinde [€]",
         "Der STEP-Import erkennt Kernlochbohrungen an diesem Durchmesser (±0,05 mm). Gerechnet wird der feste "
         "Preis je Gewinde; ist er leer, die Zeit je Gewinde mit dem Stundensatz der Maschine."],
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
    i.abschnitt("Felder der Tabellen")
    i.text("Die Spalten jeder Tabelle im Einzelnen. Pflichtfelder sind fett; was leer bleiben darf, rechnet das "
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
    i.bild("stamm_kunden", "Reiter Kunden", hoehe=100 * mm)
    i.tabelle(["Profile", "Bedeutung"], [
        ["<b>Profil-ID</b>", "Name des Profils, z. B. <i>RR 42,4x2,0</i>, <i>QR 40x40x3</i>, <i>RE 60x40x3</i>, "
                             "<i>U 50x30x3</i>, <i>C 100x50x3</i>, <i>L 40x40x4</i>, <i>FL 40x5</i>, Normprofile "
                             "wie <i>IPE 200</i>, <i>HEB 160</i>, <i>UPN 100</i>, <i>T 50</i>, sonst Träger als "
                             "<i>I Höhe x Breite x Steg x Flansch</i> (z. B. <i>I 150x80x5x7</i>, <i>T 60x40x5x7</i>)"],
        ["<b>Profilform</b>", "Rundrohr, Quadratrohr, Rechteckrohr, U-Profil, C-Profil, L-Profil, Flachstahl, "
                              "I-/H-Träger, T-Profil oder Sonderprofil (Liste in den Einstellungen)"],
        ["<b>Abmessung A [mm]</b>, Abmessung B [mm]",
         "Rohre: A = Ø bzw. Breite, B = Höhe (nur Rechteckrohr). U- und C-Profil: A = Steg, B = Flansch. "
         "L-Profil: A und B = Schenkel. Flachstahl: A = Breite, B leer. I-/H-Träger und T-Profil: A = Höhe, "
         "B = Flanschbreite"],
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
    i.tabelle(["Werkstoffe", "Bedeutung"], [
        ["<b>Werkstoff-ID</b>", "Schlüssel für Preise, Schneiddaten und Positionen, z. B. <i>S235-10219</i>"],
        ["Kategorie", "Stahl, Edelstahl oder Aluminium (Liste in den Einstellungen). Im Angebot sind die Werkstoffe "
                      "danach gruppiert; ohne eigene Schneiddaten gelten die der Kategorie."],
        ["Werkstoff, Werkstoff-Nr., Norm / Qualität", "Bezeichnung, Nummer (z. B. 1.0039) und Norm, nur zur Info"],
        ["<b>Dichte [kg/dm³]</b>", "für Gewicht und Preis je kg"],
        ["Tonnenpreis [€/t]", "Materialpreis, wenn unter Preise nichts steht"],
        ["Text im Angebot", "so steht der Werkstoff in der Bezeichnung im Angebot"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.text("Vorbelegt sind Stahl (S235JRH, S355J2H, E235, E355), Edelstahl (1.4301, 1.4307, 1.4404, 1.4571, "
           "1.4509) und Aluminium (EN AW-6060, 6063, 6082) mit Beispiel-Tonnenpreisen. Ältere Datendateien "
           "bekommen beim ersten Start die fehlenden Werkstoffe dazu; vorhandene bleiben unverändert und erhalten "
           "eine Kategorie (Dichte unter 4 = Aluminium, 1.4… = Edelstahl, sonst Stahl).")
    i.bild("stamm_werkstoffe", "Einstellungen, Werkstoffe mit Kategorie", hoehe=100 * mm)
    i.tabelle(["Oberflächen", "Bedeutung"], [
        ["<b>Oberfläche</b>", "Name, z. B. <i>roh</i>, <i>K240</i>, <i>gestrahlt</i>; Auswahl in der Position"],
        ["Kategorie (leer = alle)", "für welche Werkstoffe die Oberfläche passt; sonst Warnung in der Position"],
        ["Aufpreis [€/m]", "kommt je Meter Stange auf den Materialpreis (Preise bzw. Tonnenpreis). Ein abweichender "
                           "Materialpreis in der Position ersetzt Preis und Aufpreis."],
        ["Text im Angebot", "steht hinter dem Werkstoff in der Bezeichnung, z. B. „Oberfläche K240 geschliffen“"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.text("Teile mit unterschiedlicher Oberfläche kommen nie auf dieselbe Stange: optimiert wird je Profil + "
           "Werkstoff + Oberfläche + Stangenlänge. Leer und <i>roh</i> sind gleich.")
    i.bild("stamm_oberflaechen", "Einstellungen, Oberflächen mit Beispiel-Aufpreisen", hoehe=80 * mm)
    i.bild("stamm_preise", "Einstellungen, Preise je Profil und Werkstoff", hoehe=95 * mm)
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
    i.bild("stamm_lieferlaengen", "Einstellungen, Lieferlängen: 12-m-Stangen für ein Rundrohr", hoehe=70 * mm)
    i.liste("Ohne Zeile in Lieferlängen gelten Profile mit Hüllkreis-Ø über 70 mm (Einstellung, 0 = aus) "
            "zusätzlich als 12 m lieferbar, zum Preis aus <i>Preise</i> bzw. zum Tonnenpreis. Kleinere Profile ohne "
            "Zeile werden nie mit 12 m geplant. Eine eigene Zeile geht immer vor; <i>Lieferlängen vergleichen = "
            "nein</i> am Profil schließt es ganz aus.",
            "Gibt es für Profil + Werkstoff Zeilen, ist die Stangenlänge des Angebots (meist 6.000 mm) nur lieferbar, "
            "wenn sie hier oder als Liefer-Stangenlänge in <i>Preise</i> steht. Steht dort nur 12.000, plant das "
            "Programm keine künstliche 6-m-Variante.",
            "Längen über der <i>Max. Stangenlänge</i> der Maschine (Beladelänge, z. B. 6.500 mm) werden nie als "
            "ein Stück geladen: der Lieferant schneidet sie auf die geplanten Werkstücklängen zu.")
    i.text("Vorbelegt sind die Maschinen T03 (Trumpf, CO₂-Laser), T11 (Trumpf, Faserlaser) und LT7 (Adige, "
           "Faserlaser): Endbeschnitt 10 mm, Schnittverlust 0,2 mm, max. Stangenlänge 6.500 mm, 150 €/h, Konturgrenzen "
           "10 und 50 mm, Abstand getrennte Schnitte 5 mm, Rüstzeit 5 min; Greiferrest 142 mm (LT7 120 mm), "
           "Stangenwechsel 29 s (LT7 25 s), Hüllkreis-Ø 255 mm (LT7 214 mm), Metergewicht 36 kg/m (LT7 23 kg/m). "
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
        ["Rüstzeit je Angebot [min], Stangenwechsel je Stange [s]", "Zeiten, die auf alle Teile verteilt werden"],
        ["Max. Hüllkreis-Ø [mm], Max. Metergewicht [kg/m]",
         "Grenzen der Maschine; größere oder schwerere Profile werden nicht eingeplant (leer = keine Grenze)"],
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
        ["Bemerkung", "freier Text"]], [75, 190])
    i.text("Vorbelegt sind Richtwerte je Kategorie für die Maschinen T03 (Trumpf, CO₂-Laser 3,2 kW), T11 (Trumpf, "
           "Faserlaser 4 kW) und LT7 (Adige, Faserlaser 3 kW). Die Richtwerte stammen aus üblichen Schnitttabellen "
           "für Faserlaser mit 3 kW und CO₂-Laser mit 3,2 kW, mit etwa 40 % Abschlag fürs Rohr; T11 hat mit 4 kW "
           "20 % mehr Vorschub. Es sind keine "
           "Herstellerwerte, bitte mit echten Schnittzeiten der Maschine vergleichen und anpassen. Faserlaser: Stahl "
           "mit N₂ bis 4 mm, darüber O₂ bis 12 mm, Edelstahl mit N₂ bis 10 mm, Aluminium mit N₂ bis 8 mm. CO₂-Laser: "
           "Stahl mit N₂ bis 2 mm, darüber O₂ bis 12 mm, Edelstahl mit N₂ bis 8 mm, Aluminium mit N₂ bis 6 mm. "
           "Vorschub mittel ist 60 %, klein 30 % von groß, Vorschub Gravur 3.000 mm/min. Eigene Schneiddaten älterer Datendateien bleiben "
           "erhalten und gehen vor; ohne Schneidgas zählen sie nach N₂ und O₂. Welche Wandstärke-Stufe und welches "
           "Gas eine Position nutzt, zeigt der Reiter Kalkulation (Spalten Wandstärke-Stufe und Schneidgas).")
    i.text("Die Prüfspalte warnt, wenn ein Vorschub nicht passt: Vorschub mittel oder klein größer als groß, oder "
           "ein höherer Vorschub als bei der nächstdünneren Wandstärke derselben Maschine, desselben Werkstoffs "
           "bzw. derselben Kategorie und desselben Gases. In den Maschinen warnt sie, wenn einer Maschine "
           "Schneiddaten ganz oder für eine Kategorie fehlen.")
    i.bild("stamm_schneiddaten", "Einstellungen, Schneiddaten: Zeilen je Kategorie und Schneidgas", hoehe=110 * mm)
    i.bild("stamm_gewinde", "Einstellungen, Gewinde mit Kernloch, Zeit und Preis", hoehe=95 * mm)
    i.tabelle(["Gewinde", "Bedeutung"], [
        ["<b>Gewinde</b>, <b>Kernloch Ø [mm]</b>",
         "z. B. M6 mit 5,0 mm; der STEP-Import schlägt Gewinde an diesem Durchmesser vor"],
        ["Zeit je Gewinde [s], Preis je Gewinde [€]", "Preis geht vor; ohne Preis zählt die Zeit mit dem Stundensatz"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.bild("stamm_maschinen", "Einstellungen, Maschinen: die Werte gelten für jedes Angebot mit dieser Maschine",
           hoehe=125 * mm)
    i.abschnitt("Zusatzarbeiten")
    i.text("Hier stehen alle Arbeiten, die zusätzlich zum Laserschneiden je Bauteil gewählt werden können, z. B. "
           "Feuerverzinken, galvanisch Verzinken, Pulverbeschichten, Entgraten oder eine Gravur, die nicht im "
           "STEP-Modell ist. Der Unterreiter zeigt eine Übersicht; angelegt und geändert wird in einem Formular.")
    i.bild("stamm_zusatzarbeiten", "Einstellungen, Zusatzarbeiten: Übersicht mit den Beispielwerten", hoehe=110 * mm,
           legende=[(1, "Unterreiter <b>Zusatzarbeiten</b>"),
                    (2, "<b>+ Zusatzarbeit hinzufügen</b> öffnet ein leeres Formular"),
                    (3, "<b>Suchen</b> in Name, Kategorie, Beschreibung und Text im Angebot"),
                    (4, "Filter <b>Kategorie</b> und <b>Status</b> (Alle, Aktive, Inaktive), daneben <b>Sortieren "
                        "nach</b> Name, Preis, Zeitaufwand oder Kategorie"),
                    (5, "<b>Bearbeiten</b>, <b>Duplizieren</b>, <b>Deaktivieren</b> bzw. <b>Aktivieren</b> und "
                        "<b>Löschen</b> für den markierten Eintrag (auch mit der rechten Maustaste)"),
                    (6, "Detailbereich: die vollständige Berechnung des markierten Eintrags")])
    i.liste("Die Übersicht zeigt immer Name, Kategorie, Abrechnung, Preis je Einheit, Verkaufspreis (Vorgaben) und "
            "Status. Spalten wie Zeitaufwand, Stundensatz, Arbeitskosten, Material, Materialzuschlag, weitere "
            "Zuschläge oder Mindestbetrag erscheinen nur, wenn ein Eintrag dort einen Wert hat. Bei schmalem Fenster "
            "fallen weitere Detailspalten weg; sie stehen im Detailbereich.",
            "Doppelklick auf eine Zeile = <b>Bearbeiten</b>. Inaktive Einträge stehen grau.",
            "<b>Verkaufspreis (Vorgaben)</b> = Preis je Einheit mit Zuschlag Fertigung bzw. Fremdleistung und Gewinn aus "
            "den Vorgaben. Im Angebot gelten dessen Werte bzw. die der Staffel.")
    i.abschnitt("Zusatzarbeit anlegen und bearbeiten")
    i.text("Anlegen, Bearbeiten und Duplizieren nutzen dasselbe Formular. Es steht rechts neben der Tabelle, bei "
           "schmalem Fenster (unter 1280 Pixel) in einem eigenen Fenster. Der Preis rechnet sich beim Tippen neu. "
           "Gespeichert wird erst mit <b>Speichern</b>; <b>Abbrechen</b> verwirft alle Änderungen. Wer mit "
           "ungespeicherten Änderungen einen anderen Eintrag öffnet, wird gefragt, ob sie verworfen werden sollen.")
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
    i.tabelle(["Feld", "Bedeutung"], [
        ["Zusatzarbeit (Name)", "Pflicht, eindeutig. Umbenennen ändert den Namen auch in den Positionen der Angebote."],
        ["Kategorie", "frei wählbar, z. B. Oberfläche, Nachbearbeitung, Laser; Filter und Gruppen in der Auswahl"],
        ["Beschreibung", "kurzer Text für die Übersicht"],
        ["Abrechnung", "wonach gerechnet wird, siehe Tabelle unten"],
        ["Aktiv", "nur aktive Zusatzarbeiten lassen sich im Angebot neu wählen"],
        ["Festpreis [€] bzw. Zeit [s] je Einheit", "fester Preis je Einheit (z. B. Preis der Verzinkerei); bei "
                                                    "s/Stück die Maschinenzeit je Stück"],
        ["Zeitaufwand je Einheit, Zeiteinheit", "Arbeitszeit je Einheit in s, min oder h"],
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
         "(z. B. <i>Gravur extra</i>)."]], [30, 95, 140])
    i.abschnitt("Duplizieren, Deaktivieren und Löschen")
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
    i.text("Neu, Bearbeiten und Duplizieren öffnen dasselbe Formular, bei breitem Fenster rechts neben der Tabelle, "
           "sonst als eigenes Fenster. Gespeichert wird erst mit <b>Speichern</b>; <b>Abbrechen</b> verwirft alle "
           "Eingaben. Ungültige Eingaben werden rot umrandet und unten im Formular genannt.")
    i.bild("zukauf_formular", "Formular mit Preisvorschau: Schrauben, 12,00 € je 100 Stück, 5,00 € Eingangsfracht, "
                              "25 % Aufschlag (Beispielwerte)", hoehe=200 * mm, legende=[
        (1, "A Stammdaten"), (2, "B Einkaufspreis: Lieferanten des Artikels, Preiseinheit und Staffelpreise"),
        (3, "C Aufschlag: Herkunft und Methode"), (4, "<b>Weitere Details</b> aufklappen"),
        (5, "Preisvorschau für eine Verbrauchsmenge"), (6, "<b>Speichern</b>")])
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
    i.text("Unter <b>Kategorien</b> steht je Kategorie ein Standardaufschlag: Kategorie, Standard-Aufschlagsmethode "
           "(% auf Einstand, € je Einheit, € je Bestellung oder Zielmarge %), Standardaufschlag [% bzw. €], Aktiv "
           "und Beschreibung. Mengenstaffeln gibt es nur am Artikel. Die Kategorien sind mit Namen vorbelegt "
           "(Blechteile, Schrauben und Muttern, Normteile, Kaufteile, Fremdfertigung, Profile und Rohre, Sonstige "
           "Zukaufartikel), aber <b>ohne Aufschläge</b>: die Werte trägt der Betrieb selbst ein. Bedient wird die "
           "Tabelle wie die Stammdaten ([[stammdaten]]).",
           "Welcher Aufschlag gilt, entscheidet diese Reihenfolge; die höhere Stufe ersetzt die niedrigere:")
    i.bild("zukauf_kategorien", "Zukaufartikel, Unterreiter Kategorien (Beispiel: 30 % für Schrauben und Muttern)",
           hoehe=80 * mm, legende=[(1, "Unterreiter <b>Kategorien</b>")])
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
    i.text("Unter <b>Lieferanten</b> stehen Lieferant, Lieferantennummer, Ansprechpartner, Telefon, E-Mail, "
           "Lieferzeit und Bemerkung. Lieferanten, die im Artikelformular neu eingetippt werden, legt das Programm "
           "hier mit ihrem Namen an. Beim Umbenennen ändert sich der Name in allen Artikeln mit. Preise, "
           "Mindestmengen und Lieferzeiten je Artikel stehen beim Artikel.")
    i.abschnitt("Preisänderungen")
    i.text("Jede Änderung an Einkaufspreisen, Bezugskosten, Mindestmengen, Gültigkeit oder Aufschlag eines Artikels "
           "schreibt das Programm beim Speichern ins Protokoll: Datum, Artikel, Lieferant, Was, Alt, Neu und "
           "Bemerkung (z. B. <i>CSV-Import</i>). Der Unterreiter <b>Preisänderungen</b> zeigt das Protokoll, neueste "
           "zuerst, mit Suche und Filter nach Artikel.")
    i.bild("zukauf_preise", "Unterreiter Preisänderungen: Schrauben von 12,00 auf 12,80 € je 100 Stück "
                            "(Beispielwerte)", hoehe=100 * mm, legende=[
        (1, "Unterreiter <b>Preisänderungen</b>"), (2, "Protokoll mit altem und neuem Wert"),
        (3, "Angebote, die den markierten Artikel noch mit einem älteren Preisstand enthalten: Positionen, "
            "Preisstand, Verbrauch, VK alt und neu (netto für den ganzen Verbrauch im Angebot) und Differenz"),
        (4, "<b>Angebot öffnen</b> (auch Doppelklick)"),
        (5, "<b>Im Angebot aktualisieren …</b>: zeigt alt und neu und setzt nach Bestätigung den aktuellen "
            "Preisstand in allen Positionen dieses Angebots")])
    i.text("Gespeicherte Angebote ändern sich nie von selbst. Aktualisiert wird nur ausdrücklich: hier je Angebot "
           "oder im Dialog Zukaufteile einer Position mit <b>Aus Stammdaten aktualisieren …</b>.")
    i.abschnitt("CSV-Import und -Export", marke="zukauf_csv")
    i.text("<b>CSV exportieren</b> im Unterreiter Artikel speichert alle Artikel als CSV-Datei (Semikolon, mit "
           "Excel zu öffnen): eine Zeile je Artikel und Lieferant, Kopfzeile mit den Feldnamen wie im Formular. "
           "Einkaufspreise stehen als Staffel <i>ab 1: 12,00 | ab 500: 9,00</i> (Preis je Preiseinheit); ein "
           "einzelner Preis genügt (<i>12,00</i> = ab 1).",
           "<b>CSV importieren …</b> liest eine solche Datei und zeigt zuerst eine Vorschau. Übernommen wird erst "
           "mit <b>Importieren</b>:")
    i.bild("zukauf_csv", "Vorschau des CSV-Imports (Beispielwerte)", hoehe=55 * mm, legende=[
        (1, "Zusammenfassung: neu, ändern, unverändert, mit Fehler"),
        (2, "je Zeile der Datei die Aktion mit den Änderungen bzw. Fehlern; neu grün, ändern gelb, Fehler rot"),
        (3, "<b>Importieren</b>")])
    i.liste("Artikel mit vorhandener Artikelnummer werden geändert: Angaben aus der Datei ersetzen die alten, der "
            "Einkauf beim genannten Lieferanten wird ersetzt, andere Lieferanten bleiben. Mehrere Zeilen mit "
            "derselben Artikelnummer und verschiedenen Lieferanten ergeben einen Artikel mit mehreren Lieferanten.",
            "Fehler, die das Programm erkennt: fehlende Artikelnummer oder Bezeichnung, unlesbare oder negative "
            "Preise, nicht aufsteigende Staffeln, doppelte Zeilen (gleiche Artikelnummer und gleicher Lieferant), "
            "unbekannte Werte bei Status, Aufschlag aus und Methode, Einkaufsdaten ohne Lieferant. Zeilen mit Fehler "
            "werden nie übernommen.",
            "Unbekannte Kategorien legt der Import an (ohne Aufschlag). Preisänderungen kommen ins Protokoll; "
            "gespeicherte Angebote behalten ihren Preisstand.")
    i.abschnitt("Blechartikel und fehlender Einkaufspreis", marke="blechartikel")
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
        (4, "Unterreiter <i>Länder</i> neben <i>Frachtzonen</i>")])
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
    i.abschnitt("Tarifverwaltung", marke="tarife")
    i.bild("fracht_tarife", "Tarifverwaltung: Tarife oben, Preisstaffeln des markierten Tarifs unten", hoehe=110 * mm,
           legende=[
        (1, "<b>Neue Version …</b> kopiert den markierten Tarif mit allen Preisen und neuem „Gültig ab“; der alte "
            "Tarif gilt bis zum Vortag. So bleiben Tarifwechsel lückenlos und nachvollziehbar."),
        (2, "Unten stehen nur die Preisstaffeln des markierten Tarifs; neue Zeilen bekommen ihn automatisch."),
        (3, "<b>Preise aller Tarife zeigen</b> hebt den Filter auf.")])
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
                              "(z. B. Mindermengenzuschlag), Teillänge über Grenze [mm] (Überlänge) oder Zonenart "
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
            "(BEISPIEL); vorhandene Einträge bleiben.")])
    i.text("Fracht im Angebot und je Staffelmenge: [[fracht_angebot]] und [[staffeln]].")
    i.text("Jede gespeicherte Kalkulation enthält eine vollständige Kopie aller verwendeten Werte: Tarif und Version, "
           "Preisstaffeln, Zone und PLZ-Regel, Zuschläge, Dieselpreis, Kurs, Gewicht und Ladehilfsmittel. Spätere "
           "Änderungen an Tarifen oder Zuschlägen ändern gespeicherte Kalkulationen nicht.")


def kapitel_pflege(i):
    i.kapitel("Updates und Datensicherung", marke="pflege")
    i.text("Das Programm holt Updates auf Knopfdruck aus dem Internet und sichert die Datendatei selbst. Hier steht, "
           "wie beides geht und wie die Daten auf einen anderen Rechner umziehen.")
    i.abschnitt("Updates", marke="updates")
    i.text("Das Programm sucht bei jedem Start im Hintergrund nach einer neueren Version (öffentliches Verzeichnis "
           "<i>Rohrlaser-Updates</i> auf GitHub, ohne Anmeldung), installiert wie portabel. Gibt es eine, erscheint ein Hinweis mit dem installierten und dem neuen Stand und der letzten "
           "Änderung. Ohne Internet oder bei einem Fehler meldet sich das Programm beim Start nicht. Von Hand: "
           "<b>Hilfe → Nach Updates suchen …</b>; dort steht auch, wenn das Programm schon aktuell ist. Welcher Stand "
           "installiert ist, zeigen Fenstertitel, Startseite und <i>Hilfe → Über …</i>.")
    i.bild("update_hinweis", "Hinweis auf eine neue Version", hoehe=55 * mm, legende=[
        (1, "<b>Jetzt aktualisieren</b>: lädt die neue Version und startet das Programm neu. <b>Später</b>: "
            "nichts ändern, beim nächsten Start kommt der Hinweis wieder.")])
    i.liste("Das Programm vergleicht jede Programmdatei über ihre Prüfsumme mit der neuen Version und lädt <b>nur die "
            "geänderten Dateien</b>. Meist sind das wenige MB statt des ganzen ZIP mit rund 180 MB. Beschädigte oder "
            "fehlende Programmdateien werden dabei gleich mit ersetzt.",
            "Vor dem Austausch legt es eine geprüfte Sicherung der Datendatei an (Ordner <i>Sicherung</i> im "
            "Datenordner, Name endet auf <i>_vor_update</i>), danach startet es neu. Scheitert diese Sicherung, "
            "bricht das Update ab.",
            "Klappt der Austausch einer Datei nicht (z. B. weil die Bedienungsanleitung gerade in einem PDF-Programm "
            "offen ist), stellt das Programm alle Dateien zurück und bleibt, wie es war. Datei schließen und noch "
            "einmal versuchen.",
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
    i.text("Das Programm sichert die Datendatei in den Ordner <i>Sicherung</i> im Datenordner:")
    i.liste("beim ersten Start jedes Tages,",
            "beim Beenden (eine je Tag, wird bei jedem Beenden erneuert, Name endet auf <i>_beenden</i>),",
            "mit <b>Datensicherung erstellen</b> (Startseite oder Menü <i>Datei</i>),",
            "vor einem Update (<i>_vor_update</i>), vor dem Erweitern der Datendatei (<i>_vor_Schema_…</i>), vor dem "
            "Wiederherstellen (<i>_vor_Wiederherstellung</i>) und vor einem Import (<i>_vor_Import</i>).")
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
    i.bild("sicherung_wiederherstellen", "Sicherung wiederherstellen", hoehe=80 * mm, legende=[
        (1, "Sicherungen aus dem Datenordner und dem zweiten Sicherungsordner, neueste oben, mit Art, Anzahl "
            "Angebote und Positionen. Grau: beschädigt oder von einer neueren Programmversion."),
        (2, "<b>Wiederherstellen</b>: ersetzt alle Daten durch die gewählte Sicherung (Doppelklick geht auch). "
            "<b>Andere Datei …</b>: eine Sicherung, Datendatei oder Export-Datei von woanders wählen.")])
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
           "Das Programm ist für einen Arbeitsplatz gedacht. Solange es läuft, sperrt es seine Datendatei: Ein "
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
            "(eine Bohrung durch beide Wände, zwei Konturen).",
            "<b>Langloch</b> und <b>Rechteckausschnitt</b> mit Länge, Breite und Richtung (90° = längs zur "
            "Rohrachse); alles andere ist ein <b>Ausschnitt</b> mit Hüllmaßen.",
            "<b>Sackbohrung</b> (nicht durchgehend) und <b>Gravur</b> (Vertiefung, Markierung). Sie zählen nicht "
            "zum Schneidweg. Bei einer Sackbohrung kommt der Hinweis, dass sie mit dem Laser nicht herstellbar ist.",
            "<b>Innenmerkmal</b>: nur auf der Innenseite, von außen nicht sichtbar. Es wird gemeldet, aber nicht "
            "gerechnet.",
            "<b>Ende A / Ende B</b>: <i>gerade</i>, <i>Gehrung</i> (Neigung um eine Querachse), <i>Schrägschnitt "
            "zweiachsig</i> oder <i>komplex</i> (Ausklinkung, Sattel- oder Formschnitt). Dazu kommen die "
            "Gesamtneigung und die Neigung um beide Querachsen in Grad.")
    i.hinweis("Eine STEP-Datei enthält nur Geometrie, keine Fertigungsmerkmale. Ob eine Fläche ein Schnitt ist, "
              "leitet die Messung daraus ab, ob sie auf dem Außen- oder Innenmantel liegt. Durchgehend ist ein "
              "Merkmal, wenn es bis zur Innenwand reicht. Kanten, die den Mantel nur in mehrere Flächen teilen, sind "
              "keine Kontur.")
    i.abschnitt("Messregeln")
    i.liste("Gerade Rohre mit konstantem Querschnitt (keine Biegeteile). Rund-, Quadrat- und Rechteckrohr werden "
            "erkannt, alles andere als Sonderprofil gemeldet.",
            "Teilelänge = größte Ausdehnung entlang der Rohrachse (bei Gehrung die lange Seite).",
            "Schneidweg = Anfangsschnitt + Endschnitt + Innenkonturen auf der Außenhaut. Gravuren (nicht durch die "
            "Wand) zählen getrennt.",
            "Innenkonturen, Anfangs- und Endschnitt werden nach ihrem Hüllmaß klein, mittel oder groß eingestuft "
            "(Grenzen je Maschine, Vorgabe 10 und 50 mm; [[konturklassen]]); jede Klasse hat ihren eigenen Vorschub.",
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
    i.liste("Gebogene Rohre und Rohre mit veränderlichem Querschnitt: keine Maße, Prüfstatus <i>nicht messbar</i>.",
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
         "Teil länger als die Nutzlänge (Stange − Endbeschnitt − Greiferrest), Profil über max. Hüllkreis oder "
         "Metergewicht der Maschine, oder Pflichtangaben fehlen. Grund steht in der Auswertung."],
        ["Übersicht zeigt <b>Veraltet</b>", "Nach der letzten Optimierung wurde etwas geändert. Neu optimieren."],
        ["Übersicht: <b>Preise festgeschrieben am …, Stammdaten seitdem geändert</b>",
         "Materialpreise oder Schneiddaten wurden nach dem Angebots-PDF geändert; das Angebot rechnet weiter mit den "
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
        ["Gewinde wird nicht gerechnet", "Nur Einträge in <b>Gewinde geprüft</b> zählen, nicht der Vorschlag."],
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


# Jede neue Programmversion bekommt hier eine Zeile (tests/test_anleitung.py prüft das), neueste zuerst.
NEUERUNGEN = [
    ["0.6.5", "Mindestpreis: gilt immer aus den Einstellungen für alle Angebote, auch ältere (dort stand bisher 0 €), "
              "und wird bei jeder Änderung geprüft; im Angebot nicht mehr änderbar ([[mindestpreis]]). Zuschlag "
              "Material und Zuschlag Fertigung ebenso nur noch in den Einstellungen, dort einmalig auf 0 % gesetzt."],
    ["0.6.4", "Vorschub Gravur der Richtwerte auf 3.000 mm/min gesenkt (bisher Faser 15.000, CO₂ 10.000); ältere "
              "Datendateien werden einmalig angepasst, von Hand geänderte Werte bleiben ([[stammdaten]])."],
    ["0.6.3", "Schneidweg-Rechner für Teile ohne STEP-Datei: Gehrungen, Bohrungen, Langlöcher, Rechtecke, Schlitze "
              "und sonstige Konturen eingeben, Schneidweg, Einstiche, Konturklassen und Schneidzeit sofort sehen und "
              "in die Position übernehmen (Rechtsklick auf die Position, [[schneidweg_rechner]])."],
    ["0.6.2", "Kundenmaterial: Spalte <i>Material</i> je Position (Eigenmaterial / Kunde beigestellt), Vorgabe im "
              "Angebotskopf, eigene Stangengruppe ohne Materialkosten, optional Handling je kg, Hinweis mit "
              "Stangenbedarf im Angebot ([[kundenmaterial]])."],
    ["0.6.1", "Angebot: Kalkulationswerte, die von den Einstellungen abweichen, sind gelb markiert und aufgelistet "
              "(auch Stundensätze), Preisänderung nach jeder Änderung in der Statuszeile, <i>Vorgaben aus "
              "Einstellungen</i> nennt jede Änderung ([[angebot]])."],
    ["0.6.0", "Angebot: eigene <b>Lieferzeit</b> je Angebot (Arbeitstage, Wochen, KW, Datum oder Text, [[lieferzeit]]), "
              "<b>Ihre Anfrage / Zeichen</b> im Kopf und im PDF, <b>Mindestpreis</b> 200 € netto: Stückpreise "
              "werden anteilig angehoben, Hinweis „Mindestauftragswert“ ([[mindestpreis]])."],
    ["0.5.17", "Angebot: Der Angebotstext jeder Position steht zeilenweise (Profil, Länge, Material, Oberfläche, je "
               "Zusatzarbeit und Zukaufteil eine Zeile <i>inkl. …</i>) statt hintereinander ([[ausgabe]])."],
    ["0.5.16", "Programm und Setup sind mit dem eigenen Zertifikat <i>Patrick Brundiers</i> signiert; neue Datei "
               "<i>Windows-Vertrauen-einrichten.cmd</i> (ohne Adminrechte) gibt Setup/ZIP frei und trägt das Zertifikat "
               "ein, Anleitung zu „Zulassen“ vor dem Entpacken ([[windows_warnungen]], [[windows_vertrauen]])."],
    ["0.5.15", "Angebot: Spalte <i>Materialpreis [€/m]</i> zeigt den berechneten Meterpreis grau und lässt ihn wie die "
               "Schneidzeit günstiger oder teurer überschreiben ([[meterpreis]])."],
    ["0.5.14", "Lieferlängen: 6-m- gegen 12-m-Stangen vergleichen, 12 m nur als vom Lieferanten geschnittene "
               "Werkstücke bis zur Beladelänge, Übernahme per Klick, Staffeln wählen selbst ([[lieferlaengen]])."],
    ["0.5.13", "Maschinen T03 (Trumpf, CO₂ 3,2 kW), T11 (Trumpf, Faser 4 kW) und LT7 (Adige, Faser 3 kW) statt RL-1/RL-2, "
               "neue Schneiddaten-Richtwerte je Laser, Prüfspalte warnt bei unplausiblen Vorschüben; beim Umbenennen "
               "einer Maschine ziehen Angebote und Standard-Maschine mit ([[stammdaten]])."],
    ["0.5.12", "Schneidzeit mit der größten Wandstärke (neues Feld <i>Wandstärke max.</i> bei den Profilen, "
               "Normprofile mit der Flanschdicke) und mehrere Einstiche je Anfangs-/Endschnitt: I-/H-Träger und "
               "U-Profil 4, T-Profil 2 ([[optimieren]])."],
    ["0.5.11", "Einkaufspreis fehlender Zukaufteile direkt im Angebot eintragen (<i>Zukaufteile … → EK eintragen …</i>), "
               "gespeichert ab der Stückzahl der Position ([[zukauf_positionen]])."],
    ["0.5.10", "Automatische Fracht rechnet nach jeder Änderung am Angebot sofort neu und schreibt den Betrag ins "
               "Feld Frachtkosten ([[fracht_angebot]])."],
    ["0.5.9", "STEP-Import: bei Grenzfällen ist die Art im Prüfdialog wählbar (Flachstahl oder Blech, Profil oder "
              "Kantteil) ([[step]])."],
    ["0.5.8", "Fracht automatisch berechnen mit Ziel-PLZ und Land, zweistellige Postleitzahlen in den Frachtzonen "
              "([[fracht]]). STEP-Import: Standard-Werkstoff für Rohre und Profile, Stückzahl 1 bei Einzelteilen."],
    ["0.5.7", "Konturklassen: Konturliste je Position, Neu-Einteilung, Enden nach Hüllmaß ([[konturklassen]])."],
    ["0.5.6", "Konturklassen: Zeitanteile je Klasse, Warnung bei widersprüchlichen Konturwerten."],
    ["0.5.4 – 0.5.5", "Bleche aus dem STEP-Import werden eigene Zukaufteil-Positionen ([[zukauf_positionen]])."],
    ["0.5.3", "Online-Update ohne Anmeldung aus einem öffentlichen Update-Verzeichnis ([[updates]]); Blechartikel "
              "mit Maßen, Werkstoff und fehlendem Einkaufspreis ([[blechartikel]])."],
    ["0.5.2", "STEP-Import erkennt I-/H-Träger und T-Profile."],
    ["0.5.1", "STEP-Import erkennt Bleche und grenzt sie vom Flachstahl ab ([[bleche]])."],
    ["0.5.0", "Preise je Angebot festschreiben ([[preise_festschreiben]]), Schnittmuster-Optimierung, "
              "kaufmännische Rundung im Angebot."],
]


def kapitel_neu(i):
    i.kapitel("Anhang: Was ist neu", marke="neu")
    i.text("Was sich je Programmversion für die Bedienung geändert hat, neueste zuerst. Die installierte Version "
           "steht unter <i>Hilfe → Über …</i> und auf der Titelseite dieser Anleitung.")
    i.tabelle(["Version", "Änderung"], NEUERUNGEN, [30, 235])


# ---------------------------------------------------------------- Ablauf
def bilder_erzeugen(ordner):
    umgebung = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR="2")
    subprocess.run([sys.executable, str(HIER / "bilder.py"), str(ordner)], check=True, env=umgebung)


# Bildschirmfotos, die bilder.py mit erzeugt, die aber bewusst nicht in der Anleitung stehen
OHNE_STELLE = {"stamm_stundensaetze"}     # gleiche Seite wie stamm_arbeitsschritte


def inhalt_sammeln(daten, bilder, marken=None):
    stand = datetime.date.today().strftime("%d.%m.%Y")
    inh = Inhalt(bilder, marken)
    titelseite(inh, stand)
    inh.f.append(PageBreak())
    for kapitel in (kapitel_ueberblick, kapitel_start,
                    # Teil B: ein Angebot rechnen, in der Reihenfolge der Arbeit
                    kapitel_angebote, kapitel_angebot, kapitel_step, kapitel_optimieren, kapitel_staffeln,
                    kapitel_fracht, kapitel_zukauf_angebot):
        kapitel(inh)
    kapitel_ausgabe(inh, daten["seiten"], daten["ablage"])
    # Teil C: einrichten und pflegen; danach der Anhang
    for kapitel in (kapitel_nachkalkulation, kapitel_einstellungen, kapitel_stammdaten, kapitel_zukauf,
                    kapitel_frachtkosten, kapitel_pflege, kapitel_step_messung, kapitel_fragen, kapitel_neu):
        kapitel(inh)
    # die erste Kapitelüberschrift soll keinen zusätzlichen Seitenumbruch erzeugen
    inh.f = [x for k, x in enumerate(inh.f) if not (isinstance(x, PageBreak) and k > 0
                                                     and isinstance(inh.f[k - 1], PageBreak))]
    return inh


def pdf_bauen(bilder_ordner, ziel):
    daten = json.loads((Path(bilder_ordner) / "bilder.json").read_text(encoding="utf-8"))
    bilder = dict(daten["bilder"], _ordner=Path(bilder_ordner))
    # 1. Durchlauf: Kapitelnummern der Marken, 2. Durchlauf: Verweise einsetzen
    inh = inhalt_sammeln(daten, bilder, inhalt_sammeln(daten, bilder).neue_marken)
    ungenutzt = sorted(n for n in set(daten["bilder"]) - inh.benutzte_bilder - OHNE_STELLE
                       if not n.startswith("pdf_"))      # Seitenbilder der PDF-Ausgaben: nur einzelne Seiten gezeigt
    if ungenutzt:
        raise ValueError("Bildschirmfotos ohne Stelle in der Anleitung (bilder.py erzeugt sie umsonst): "
                         + ", ".join(ungenutzt))
    doc = Anleitung(ziel)
    doc.multiBuild(inh.f)
    return ziel


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ziel", default=str(HIER / "Bedienungsanleitung.pdf"))
    ap.add_argument("--bilder", help="vorhandene Bilder verwenden (Ordner mit bilder.json)")
    a = ap.parse_args()
    if a.bilder:
        ziel = pdf_bauen(a.bilder, a.ziel)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            bilder_erzeugen(tmp)
            ziel = pdf_bauen(tmp, a.ziel)
    print(f"{ziel}: {Path(ziel).stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
