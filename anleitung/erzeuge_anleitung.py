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
    """Sammelt die Flowables; Kurzformen für Text, Listen, Bilder, Legenden und Hinweise."""

    def __init__(self, bilder):
        self.bilder, self.f, self.kapitel_nr, self.abschnitt_nr = bilder, [], 0, 0

    def kapitel(self, titel):
        self.kapitel_nr += 1
        self.abschnitt_nr = 0
        if self.f:
            self.f.append(PageBreak())
        self.f.append(Paragraph(f"{self.kapitel_nr}&nbsp;&nbsp;{titel}", S_H1))

    def abschnitt(self, titel):
        self.abschnitt_nr += 1
        self.f.append(CondPageBreak(45 * mm))
        self.f.append(Paragraph(f"{self.kapitel_nr}.{self.abschnitt_nr}&nbsp;&nbsp;{titel}", S_H2))

    def text(self, *absaetze):
        self.f.extend(Paragraph(a, S) for a in absaetze)

    def liste(self, *punkte, nummeriert=False):
        for i, p in enumerate(punkte, 1):
            self.f.append(Paragraph(p, S_LISTE, bulletText=f"{i}." if nummeriert else "•"))
        self.f.append(Spacer(1, 3))

    def bild(self, name, unterschrift="", hoehe=125 * mm, legende=()):
        self.bilder_nebeneinander([name], unterschrift, hoehe, legende)

    def bilder_nebeneinander(self, namen, unterschrift="", hoehe=125 * mm, legende=()):
        pfade = [self.bilder["_ordner"] / self.bilder[n]["datei"] for n in namen]
        oben = [self.f.pop()] if self.f and isinstance(self.f[-1], Paragraph) and self.f[-1].style.name == "h2" else []
        unten = ([Paragraph(unterschrift, S_BILD)] if unterschrift else []) + ([self._legende(legende)] if legende else [])
        self.f.append(BildBlock(pfade, hoehe, oben, unten))

    def _legende(self, punkte):
        zeilen = [[Nummer(nr), Paragraph(text, S_LEGENDE)] for nr, text in punkte]
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
        t = Table([[Paragraph(f"<b>{titel}:</b> {text}", S_TIPP)]], colWidths=[BREITE])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HELLBLAU),
                               ("LINEBEFORE", (0, 0), (0, -1), 3, BLAU),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        self.f.extend([Spacer(1, 3), t, Spacer(1, 6)])

    def tabelle(self, kopf, zeilen, breiten):
        daten = [[Paragraph(f"<b>{k}</b>", S_LEGENDE) for k in kopf]]
        daten += [[Paragraph(str(z), S_LEGENDE) for z in zeile] for zeile in zeilen]
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
    i.kapitel("Überblick")
    i.text("Die Rohrlaser Angebotskalkulation plant für ein Angebot, wie die Teile aus Stangen geschnitten werden, und "
           "rechnet daraus Materialbedarf, Laserzeit und Angebotspreis. Alles liegt in einer Datendatei. Das Programm "
           "gibt es zum Installieren (für den eigenen Benutzer, ohne Administratorrechte) und als portable Version "
           "ohne Installation; beide rechnen gleich (Kapitel 2).",
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
    i.text("Die Stammdaten (Profile, Werkstoffe, Oberflächen, Preise, Maschinen, Schneiddaten, Gewinde, Zusatzarbeiten) und die "
           "Einstellungen werden einmal eingerichtet (Kapitel 3 und 4): das Programm startet mit Beispielwerten, die "
           "durch die eigenen ersetzt werden.")
    i.abschnitt("Aufbau des Fensters")
    i.text("Das Hauptfenster besteht aus Reitern. Die festen Reiter sind <i>Start</i>, <i>Angebote</i>, <i>Kunden</i> "
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
    i.kapitel("Installation und erster Start")
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
           "(Abschnitt <i>Datensicherung und Umzug</i>).")
    i.abschnitt("Programm installieren")
    i.liste("Auf GitHub unter <b>Releases → aktuell</b> die Datei <b>Rohrlaser-Angebotskalkulation-Setup.exe</b> "
            "herunterladen und starten.",
            "Warnt Windows, siehe Abschnitt <i>Windows-Warnungen</i>. Das Setup fragt nach der Desktop-Verknüpfung "
            "und installiert nur für den angemeldeten Benutzer.",
            "Das Programm aus dem Startmenü starten (<i>Rohrlaser Angebotskalkulation</i>; daneben liegt die "
            "Bedienungsanleitung).",
            "Eine neue Version des Setups lässt sich jederzeit über die alte installieren; die Daten bleiben. Meist "
            "reicht aber das Online-Update (Abschnitt <i>Updates</i>).", nummeriert=True)
    i.text("Deinstallieren: <i>Einstellungen → Apps → Rohrlaser Angebotskalkulation → Deinstallieren</i>. Entfernt "
           "werden nur die Programmdateien. Datendatei, Sicherungen und PDF bleiben, eine spätere Installation findet "
           "sie wieder.")
    i.abschnitt("Portable Version entpacken")
    i.liste("Unter <b>Releases → aktuell</b> die Datei <b>Rohrlaser-Angebotskalkulation.zip</b> herunterladen.",
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
        ["Portabel.ini", "macht das Programm portabel: Daten im Ordner daneben. Darin lässt sich auch ein anderer "
                         "Datenordner eintragen (Zeile <i>daten = …</i>). Nicht löschen, sonst sucht das Programm "
                         "die Daten im Benutzerprofil."],
        ["STEP-Import\\", "Messprogramm für STEP-Dateien. Muss neben der .exe liegen bleiben."],
        ["_internal\\", "Programmbibliotheken, nicht verändern"],
        ["Daten\\rohrlaser.db", "Datendatei: Stammdaten, Einstellungen, alle Angebote. Wird beim ersten Start "
                                "angelegt."],
        ["Daten\\Sicherung\\", "automatische Sicherungen der Datendatei (Abschnitt <i>Datensicherung und Umzug</i>)"],
        ["Angebote\\", "Ablage für PDF und CSV-Export (wenn in den Einstellungen nichts anderes steht)"],
        ["Update.json", "Liste der Programmdateien des installierten Stands (für das Update, Abschnitt "
                        "<i>Updates</i>)"]],
        [60, 205])
    i.text("Eine ältere portable Version ohne <i>Portabel.ini</i> erkennt das Programm am Ordner <i>Daten</i> neben "
           "der .exe und arbeitet dort weiter wie bisher.")
    i.abschnitt("Windows-Warnungen (SmartScreen, Defender)")
    i.text("Programm und Setup sind nicht digital signiert und werden mit PyInstaller gebaut. Programme dieser Art "
           "hält Windows anfangs oft für verdächtig, obwohl nichts Schädliches darin ist. Das Programm braucht keine "
           "Administratorrechte, geht nur für die Suche nach Updates ins Internet (Abschnitt <i>Updates</i>) und "
           "schreibt nur in seinen Programm- und Datenordner und in die eingestellten Ablage- und Sicherungsordner. Damit Virenscanner möglichst selten anschlagen, enthält "
           "jede .exe Hersteller-, Produkt- und Versionsangaben (rechte Maustaste → Eigenschaften → Details), und das "
           "Startprogramm wird für dieses Programm eigens übersetzt.")
    i.liste("<b>Vor dem Entpacken</b> des ZIP: rechte Maustaste auf das heruntergeladene ZIP → <i>Eigenschaften</i> → unten "
            "<i>Zulassen</i> anhaken → OK. Sonst trägt Windows jede entpackte Datei als „aus dem Internet“ ein und "
            "prüft sie bei jedem Start besonders.",
            "Meldet Windows beim ersten Start des Programms oder des Setups „Der Computer wurde durch Windows "
            "geschützt“: auf <i>Weitere Informationen</i> und dann <i>Trotzdem ausführen</i> klicken. Danach fragt "
            "Windows nicht mehr.",
            "Hat der Microsoft Defender eine Datei in Quarantäne verschoben: <i>Windows-Sicherheit → Viren- &amp; "
            "Bedrohungsschutz → Schutzverlauf</i>, den Eintrag öffnen, <i>Aktionen → Wiederherstellen</i> bzw. "
            "<i>Auf Gerät zulassen</i>. Den Fehlalarm bitte an Microsoft melden "
            "(www.microsoft.com/wdsi/filesubmission, Datei hochladen, „Incorrectly detected as malware“); "
            "nach der Prüfung nimmt Microsoft die Erkennung meist innerhalb weniger Tage zurück.",
            "Ob ZIP oder Setup unverändert von GitHub kommen, zeigt die Prüfsumme: im Release liegen "
            "<i>Rohrlaser-Angebotskalkulation.zip.sha256</i> und <i>Rohrlaser-Angebotskalkulation-Setup.exe.sha256</i>. "
            "In PowerShell <i>Get-FileHash</i> mit dem Dateinamen eingeben; die Zahl muss gleich sein.",
            "Wahlweise den Programmordner unter <i>Viren- &amp; Bedrohungsschutz → "
            "Einstellungen verwalten → Ausschlüsse</i> eintragen. Dann prüft der Defender die Programmdateien nicht "
            "bei jedem Start, Programm und STEP-Import starten schneller. Nur diesen Ordner ausschließen, niemals "
            "<i>Downloads</i> oder ganze Laufwerke; in Firmen entscheidet das die IT.", nummeriert=True)
    i.abschnitt("Updates")
    i.text("Das Programm sucht bei jedem Start im Hintergrund nach einer neueren Version (Release <i>aktuell</i> auf "
           "GitHub), installiert wie portabel. Gibt es eine, erscheint ein Hinweis mit dem installierten und dem neuen Stand und der letzten "
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
            "Das Update funktioniert ab Version 0.3.0. Wer eine ältere Version hat, holt sich einmal das neue Setup "
            "oder ZIP und übernimmt die Daten (Abschnitt <i>Datensicherung und Umzug</i>).")
    i.abschnitt("Startseite")
    i.text("Beim ersten Start fragt das Programm, ob vorhandene Daten übernommen werden sollen (z. B. aus einer "
           "portablen Version oder einer Export-Datei, siehe unten). Ohne Übernahme legt es die Datendatei mit "
           "Beispiel-Stammdaten an. Die Startseite zeigt in Rot, dass es sich um Beispielwerte handelt, und hinter "
           "der Datendatei, ob das Programm installiert oder portabel läuft.")
    i.bild("start_beispiel", "Startseite nach dem ersten Start (Beispiel-Stammdaten)", hoehe=112 * mm, legende=[
        (1, "<b>Datensicherung erstellen</b>: geprüfte Kopie der Datendatei in den Ordner <i>Sicherung</i> und, "
            "falls eingestellt, in den zweiten Sicherungsordner."),
        (2, "<b>Sicherung wiederherstellen …</b>: einen früheren Stand zurückholen (siehe unten)."),
        (3, "<b>Datenordner öffnen</b>: zeigt den Ordner mit der Datendatei im Explorer.")])
    i.text("Die Beispielwerte in den Stammdaten (Kapitel 3) und den Vorgaben (Kapitel 4) im Reiter Einstellungen durch die "
           "eigenen ersetzen: Preise, Maschinen, Schneiddaten, Briefkopf und Zuschläge. Danach rechnet das Programm "
           "mit den eigenen Werten.")
    i.abschnitt("Datensicherung und Umzug")
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


def kapitel_stammdaten(i):
    i.kapitel("Stammdaten")
    i.abschnitt("Tabellen bearbeiten")
    i.text("Die Kunden haben einen eigenen Reiter. Alle anderen Stammdaten (Profile, Werkstoffe, Oberflächen, Preise, "
           "Maschinen, Schneiddaten, Gewinde, Zusatzarbeiten, Stundensätze und Arbeitsschritte) stehen als Unterreiter "
           "im Reiter <i>Einstellungen</i>, "
           "der mit einem Passwort geschützt ist (Kapitel 4). Alle Tabellen sind gleich aufgebaut:")
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
            "Schneiddaten mit.")
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
         "Auswahl für den Knopf <i>Zusatzarbeiten …</i> im Angebot (Kapitel 6.5). Vorbelegt mit Beispielpreisen, "
         "bitte eigene eintragen."],
        ["Stundensätze", "Stundensatz-ID, Bezeichnung, Stundensatz [€/h]",
         "Sätze für Personal und Arbeitsplätze (Programmierung, Rüstpersonal, Nachbearbeitung …). Der Satz der "
         "Maschine steht bei der Maschine (Kapitel 4.3)."],
        ["Arbeitsschritte", "Arbeitsschritt, Stundensatz, Art, Rüstzeit, Zeit je Einheit",
         "Welcher Arbeitsschritt mit welchem Stundensatz und welcher Zeitvorgabe gerechnet wird (Kapitel 4.3)."]],
        [30, 95, 140])
    i.abschnitt("Felder der Tabellen")
    i.text("Die Spalten jeder Tabelle im Einzelnen. Pflichtfelder sind fett; was leer bleiben darf, rechnet das "
           "Programm wie angegeben.")
    i.tabelle(["Kunden", "Bedeutung"], [
        ["<b>Kundennummer</b>, <b>Kundenname</b>", "Schlüssel und Name; eine geänderte Kundennummer ändert sich auch "
                                                   "in den Angeboten"],
        ["Straße, PLZ Ort, Ansprechpartner", "Anschrift im Angebots-PDF (Ansprechpartner als „z. Hd.“)"],
        ["Telefon, E-Mail", "zur Info"],
        ["Skonto [%], Skontofrist [Tage], Zahlungsziel netto [Tage]",
         "Zahlungsbedingungen des Kunden für neue Angebote; leer = Vorgabe aus den Einstellungen. Das Skonto wird in "
         "den Preis eingerechnet (Kapitel 8.3)."],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.bild("stamm_kunden", "Reiter Kunden", hoehe=100 * mm)
    i.tabelle(["Profile", "Bedeutung"], [
        ["<b>Profil-ID</b>", "Name des Profils, z. B. <i>RR 42,4x2,0</i>, <i>QR 40x40x3</i>, <i>RE 60x40x3</i>, "
                             "<i>U 50x30x3</i>, <i>C 100x50x3</i>, <i>L 40x40x4</i>, <i>FL 40x5</i>"],
        ["<b>Profilform</b>", "Rundrohr, Quadratrohr, Rechteckrohr, U-Profil, C-Profil, L-Profil, Flachstahl oder "
                              "Sonderprofil (Liste in den Einstellungen)"],
        ["<b>Abmessung A [mm]</b>, Abmessung B [mm]",
         "Rohre: A = Ø bzw. Breite, B = Höhe (nur Rechteckrohr). U- und C-Profil: A = Steg, B = Flansch. "
         "L-Profil: A und B = Schenkel. Flachstahl: A = Breite, B leer"],
        ["<b>Wandstärke [mm]</b>", "bestimmt Querschnitt, Gewicht und die Zeile der Schneiddaten; bei offenen "
                                   "Profilen die Blechdicke, bei Flachstahl die Dicke"],
        ["Fläche manuell [mm²]", "Querschnitt vom Hersteller (Eckradien, Sonderprofile); leer = aus den Maßen. "
                                 "Beim C-Profil Pflicht, weil die Abkantung nicht in den Maßen steht (der STEP-Import "
                                 "trägt die gemessene Fläche ein)"],
        ["Endbeschnitt abweichend [mm], Greiferrest abweichend [mm]",
         "nur eintragen, wenn das Profil andere Werte braucht als die Maschine"],
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
    i.tabelle(["Preise", "Bedeutung"], [
        ["<b>Profil-ID</b>, <b>Werkstoff-ID</b>", "Kombination, für die der Preis gilt"],
        ["<b>Preisbasis</b>, <b>Preis [€]</b>", "€/kg, €/m oder €/Stange und der Betrag"],
        ["Liefer-Stangenlänge [mm]", "Pflicht bei €/Stange: Länge, auf die sich der Stangenpreis bezieht"],
        ["Gültig ab, Lieferant, Bemerkung", "zur Info, z. B. Datum des Lieferantenangebots"]], [75, 190])
    i.tabelle(["Maschinen", "Bedeutung"], [
        ["<b>Maschinen-ID</b>, Bezeichnung", "Kurzname (Auswahl im Angebotskopf) und Klartext"],
        ["Endbeschnitt [mm], Greiferrest [mm]", "Anschnitt am Stangenanfang und nicht nutzbares Ende im Greifer"],
        ["Schnittverlust je Schnitt [mm]", "Materialverlust je Trennschnitt (Schnittbreite)"],
        ["Abstand getrennte Schnitte [mm]", "Steg zwischen zwei Teilen, wenn sich die Enden keinen Schnitt teilen"],
        ["Max. Stangenlänge [mm]", "längste Stange, die die Maschine laden kann"],
        ["Stundensatz [€/h]", "Stundensatz <i>Maschine</i>: für Laserzeit, Gewinde ohne Festpreis, Rüsten und "
                              "Stangenwechsel, solange unter Arbeitsschritte nichts anderes gewählt ist"],
        ["Kontur klein bis [mm], Kontur mittel bis [mm]",
         "Grenzen der Konturklassen nach größtem Hüllmaß (Vorgabe 10 und 50 mm), je Klasse eigener Vorschub"],
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
        ["<b>Vorschub groß / Trennschnitt [mm/min]</b>", "für Anfangs- und Endschnitte und große Innenkonturen"],
        ["Vorschub mittel [mm/min], Vorschub klein [mm/min]",
         "für mittlere und kleine Innenkonturen; leer = nächstgrößerer Vorschub"],
        ["Vorschub Gravur [mm/min]", "für Gravuren; leer = nächstgrößerer Vorschub"],
        ["Einstechzeit [s]", "Zeit je Einstich"],
        ["Bemerkung", "freier Text"]], [75, 190])
    i.text("Vorbelegt sind Beispielwerte je Kategorie für RL-1 und RL-2 von 1 bis 10 mm: Stahl mit N₂ bis 4 mm, "
           "Edelstahl mit N₂ bis 8 mm, Aluminium mit N₂ bis 6 mm, darüber O₂. Eigene Schneiddaten älterer "
           "Datendateien bleiben erhalten und gehen vor; ohne Schneidgas zählen sie nach N₂ und O₂. Welche "
           "Wandstärke-Stufe und welches Gas eine Position nutzt, zeigt der Reiter Kalkulation (Spalten "
           "Wandstärke-Stufe und Schneidgas).")
    i.bild("stamm_schneiddaten", "Einstellungen, Schneiddaten: Zeilen je Kategorie und Schneidgas", hoehe=110 * mm)
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
        ["Text im Angebot", "so erscheint die Arbeit in der Bezeichnung des Angebots, z. B. <i>…, Zusatzarbeiten: "
                            "Gewinde 4xM6, feuerverzinkt</i>"]], [65, 200])
    i.text("<b>Rechenweg</b> (für jede Einheit): Preis je Einheit = Festpreis + Zeitaufwand × Stundensatz + "
           "Material mit Materialzuschlag + weiterer Zuschlag. Beispiel: 5 min × 60 €/h = 5,00 €, Material 2,00 € + "
           "10 % = 2,20 €, Selbstkosten 7,20 € je Stück. Im Angebot kommt danach einmal der Zuschlag Fertigung "
           "(bzw. Fremdleistung) und der Gewinn des Angebots bzw. der Staffel dazu, Skonto und Rundung wie beim übrigen "
           "Angebot. Der Zuschlag Material des Angebots gilt nur für das Stangenmaterial, nie für Zusatzarbeiten. "
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


def kapitel_einstellungen(i):
    i.kapitel("Einstellungen")
    i.text("Der Reiter <i>Einstellungen</i> enthält alle Voreinstellungen: den Unterreiter <i>Vorgaben</i> mit den "
           "Werten, die für alle Angebote gelten, und die Stammdaten außer den Kunden (Kapitel 3).")
    i.abschnitt("Passwort")
    i.text("Der Reiter öffnet sich erst nach Eingabe des Passworts. Passwort eintippen und Enter oder "
           "<b>Einstellungen öffnen</b> drücken. Er bleibt offen, bis <b>Einstellungen sperren</b> gedrückt oder das "
           "Programm beendet wird. Das Passwort steht unter Vorgaben, Gruppe Zugang (<i>Passwort für die "
           "Einstellungen</i>); leer = Einstellungen ohne Passwort. Das Passwort bitte beim Verantwortlichen "
           "erfragen.")
    i.bild("einstellungen_gesperrt", "Reiter Einstellungen gesperrt", hoehe=45 * mm, legende=[
        (1, "Reiter Einstellungen"), (2, "Passwort eingeben"), (3, "<b>Einstellungen öffnen</b>")])
    i.abschnitt("Vorgaben")
    i.text("Änderungen werden beim Verlassen des Feldes gespeichert und wirken ab der nächsten Rechnung. "
           "Ausnahme: Stundensätze und Zeitvorgaben (Kapitel 4.3) speichert jedes Angebot beim Anlegen.")
    i.bild("einstellungen", "Einstellungen, Unterreiter Vorgaben (oberer Teil)", hoehe=125 * mm, legende=[
        (1, "Unterreiter Vorgaben, daneben die Stammdaten"), (2, "<b>Einstellungen sperren</b>")])
    i.tabelle(["Gruppe", "Einstellung", "Wirkung"], [
        ["Kalkulation", "Zuschlag Material, Zuschlag Fertigung, Zuschlag Fremdleistung, Gewinn",
         "Herstellkosten = Material × (1 + Zuschlag Material) + Fertigung und eigene Zusatzarbeiten × (1 + Zuschlag "
         "Fertigung) + Fremdleistungen × (1 + Zuschlag Fremdleistung); Verkaufspreis = Herstellkosten × (1 + Gewinn)."],
        ["Kalkulation", "Rüstzeit je Abmessung [min]",
         "je verschiedenem Profil im Angebot, über den Stundensatz der Maschine mit Zuschlägen gerechnet"],
        ["Kalkulation", "Programmierkosten je Teil (Position) [€]",
         "einmal je Position mit Stückzahl (Vorgabe 8,50 €), auf deren Stückzahl verteilt, ohne Zuschläge auf den "
         "Preis; bei Staffelpreisen je Mengenstufe"],
        ["Kalkulation", "Pauschale je Abmessung [€], Angebotsaufschlag je Angebot [€]",
         "fester Betrag ohne Zuschläge auf den Preis; verteilt auf die Teile"],
        ["Angebot", "Standard-Maschine, Standard-Stangenlänge", "Vorgabe für neue Angebote"],
        ["Angebot", "Skonto [%], Skontofrist [Tage], Zahlungsziel netto [Tage]",
         "Zahlungsbedingungen neuer Angebote, wenn der Kunde im Kundenstamm keine eigenen hat (Vorgabe 2 % Skonto "
         "bei Zahlung in 10 Tagen, 30 Tage netto). Das Skonto wird in den Preis eingerechnet. Bestehende Angebote "
         "behalten ihre Werte."],
        ["Angebot", "Letzte Angebotsnummer", "Ein neues Angebot bekommt die nächste Nummer (A-2026-0041 → "
                                             "A-2026-0042)."],
        ["Angebots-PDF", "Briefkopf Zeile 1 (Firma), Briefkopf Zeile 2, Briefkopf Zeile 3, Briefkopf Zeile 4, MwSt.-Satz, "
                    "Gültigkeit, Bedingungen", "Kopf und Text des Angebots-PDF. Die Zahlungsbedingung (Skonto, "
                    "Zahlungsziel) setzt das Programm aus dem Angebotskopf vor die Bedingungen, sie gehört nicht in "
                    "dieses Feld."],
        ["Ablage", "Ablageordner", "Ziel für PDF und CSV-Export; leer = Ordner <i>Angebote</i> neben dem "
                                   "Programm (portabel) bzw. <i>Dokumente\\Rohrlaser Angebote</i> (installiert). "
                                   "Auch ein Netzlaufwerk ist möglich."],
        ["Ablage", "Zweiter Sicherungsordner", "zusätzliche Sicherung beim Beenden und mit <i>Datensicherung "
                                               "erstellen</i>, z. B. Netzlaufwerk, OneDrive oder USB-Stick; leer = "
                                               "keiner (Kapitel 2, Datensicherung und Umzug)"],
        ["Auswahllisten", "Profilformen", "Einträge der Auswahl „Profilform“ in den Profilen"],
        ["Auswahllisten", "Werkstoff-Kategorien", "Kategorien für Werkstoffe, Oberflächen und Schneiddaten "
                                                  "(Vorgabe Stahl, Edelstahl, Aluminium)"],
        ["Zugang", "Passwort für die Einstellungen", "Passwort für den Reiter Einstellungen; leer = ohne Passwort"]],
        [28, 80, 157])
    i.abschnitt("Stundensätze und Zeitvorgaben")
    i.text("Der Unterreiter <i>Stundensätze und Zeitvorgaben</i> zeigt links die <b>Stundensätze</b> und rechts die "
           "<b>Arbeitsschritte</b>. Jeder Arbeitsschritt wird mit genau einem Stundensatz gerechnet; der Satz "
           "<i>Maschine</i> ist der Stundensatz der gewählten Maschine (Kapitel 3).")
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
           "(Kapitel 8.4). Eine Kopie übernimmt die Werte des Originals. Wird die Maschine eines Angebots "
           "gewechselt, gelten deren aktuelle Werte.")


def kapitel_angebote(i):
    i.kapitel("Angebote verwalten")
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
    i.kapitel("Angebot bearbeiten")
    i.text("Ein geöffnetes Angebot zeigt oben links den Angebotskopf und die Kalkulation dieses Angebots, rechts die "
           "Übersicht, darunter die Aktionen und die Reiter mit Positionen und Ergebnissen. Die Trennlinie zwischen "
           "oben und unten lässt sich mit der Maus verschieben; bei kleinen Fenstern rollt der obere Teil.")
    i.text("Ein Klick auf den Titel <b>Kalkulation dieses Angebots</b> klappt die Kalkulationswerte zu. Zugeklappt "
           "steht in der Titelzeile eine Kurzfassung aller Werte ungleich 0 (z. B. „Zuschlag Material 10,0 % · "
           "Gewinn 10,0 % · …“), und die Positionen bekommen mehr Platz. Die Wahl gilt für alle Angebote. Ohne eigene "
           "Wahl ist die Karte auf kleinen Bildschirmen (z. B. 1280 × 720) zu Beginn zugeklappt. Spaltenbreiten der "
           "Positionsliste, der Kalkulation und der Zeiten richten sich beim Öffnen nach Inhalt und Spaltenkopf.")
    i.bild("angebot_positionen", "Angebot A-2026-0041 vor dem Optimieren", hoehe=125 * mm, legende=[
        (1, "<b>Angebotskopf</b>: Angebotsnummer, Kunde und Maschine fett in der ersten Zeile, darunter Datum, "
            "Kundenname, Standard-Stangenlänge und Bemerkung. Ganz unten die aufklappbaren Maschinenparameter."),
        (2, "<b>Übersicht</b>: Stand der Optimierung, Herstellkosten und Verkaufspreis groß, Meldungen, "
            "Kennzahlen und Kosten nach Gruppen."),
        (3, "<b>Positionen</b>: eine Zeile je Teil mit Stückzahl, Spalte Status ganz rechts."),
        (4, "<b>Neue Position</b>; daneben <b>Positionen löschen</b> (markierte Zeilen)."),
        (5, "<b>Zusatzarbeiten …</b>: Gewinde und Zusatzarbeiten der markierten Positionen (Kapitel 6.5)."),
        (6, "<b>STEP importieren</b>: Positionen aus Konstruktionsdaten (Kapitel 7)."),
        (7, "<b>Optimieren</b>: Stangen planen und Kalkulation rechnen (Kapitel 8)."),
        (8, "Zeile über der Positionsliste: links Anzahl der Positionen und ausgeblendeten optionalen Spalten, "
            "rechts <b>Weitere Spalten</b>, <b>STEP-Werte (aus CAD)</b> und <b>Berechnete Werte (Programm)</b>.")])
    i.text("Die blau hinterlegten Knöpfe sind die Hauptaktionen <b>Neue Position</b>, <b>STEP importieren</b>, "
           "<b>Optimieren</b> und <b>3D-Ansicht</b>. Rechts stehen die Ausgaben; CSV-Export und Ablage öffnen liegen "
           "unter <b>Weitere Aktionen</b> (Kapitel 11).")
    i.abschnitt("Angebotskopf")
    i.liste("<b>Maschine</b> bestimmt Endbeschnitt, Greiferrest, Schnittverlust, Konturgrenzen, Stundensatz und die "
            "Schneiddaten. Die Zeile <b>Maschinenparameter</b> zeigt Endbeschnitt, Greiferrest, Schnittverlust und "
            "max. Stangenlänge auch zugeklappt (immer, auch wenn ein Wert 0 ist); aufgeklappt kommen Abstand "
            "getrennte Schnitte, Konturgrenzen und, wenn gesetzt, max. Hüllkreis-Ø und max. Metergewicht dazu. "
            "Geändert werden sie in den Stammdaten Maschinen.",
            "<b>Standard-Stangenlänge</b> gilt für alle Positionen ohne abweichende Stangenlänge.",
            "<b>Frachtkosten</b> kommen ohne Zuschläge auf das Angebotspreis.",
            "<b>Kundennummer</b>: Kunden aus der Liste wählen (Nummer und Name) oder eine Nummer eintippen. Steht der "
            "Kunde im Kundenstamm, übernimmt das Programm Kundenname und Zahlungsbedingungen; eine unbekannte Nummer "
            "wird nur gespeichert.",
            "<b>Skonto</b>, <b>Skontofrist</b>, <b>Zahlungsziel netto</b>: Zahlungsbedingung dieses Angebots, "
            "vorbelegt vom Kunden bzw. aus den Einstellungen und hier änderbar. Das Skonto wird in den Preis "
            "eingerechnet: Verkaufspreis = Preis ohne Skonto ÷ (1 − Skonto). Zahlt der Kunde mit Skonto, bleibt "
            "genau der kalkulierte Preis. 0 % = kein Skonto.",
            "<b>Kalkulation dieses Angebots</b>: Zuschlag Material, Fertigung und Fremdleistung, Gewinn, Rüstzeit und "
            "Pauschale je Abmessung, Programmierkosten je Teil und Angebotsaufschlag. Ein neues Angebot übernimmt die "
            "Werte aus den Einstellungen (Gruppe Kalkulation); hier lassen sie sich für dieses Angebot ändern, ohne "
            "die Einstellungen zu ändern. <b>Vorgaben aus Einstellungen</b> setzt sie wieder auf die Einstellungen. "
            "Angebote aus älteren Programmversionen rechnen mit den Einstellungen, bis hier ein Wert geändert wird. "
            "Beim Kopieren gehen die Werte mit.",
            "Die Kalkulationswerte stehen in vier Gruppen: <b>Material und Fertigung</b> (Zuschläge), <b>Zeit und "
            "Rüsten</b> (Rüstzeit je Maschine, Stangenwechsel und Stundensatz der Maschine zur Information, Rüstzeit "
            "je Abmessung), <b>Verkauf und Gewinn</b> (Gewinn, Angebotsaufschlag, Programmierkosten, Pauschale je "
            "Abmessung, Frachtkosten) und <b>Zahlungsbedingungen</b>.")
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
        ["Positionen", "Oberfläche, Stangenlänge abweichend, Satz, Stück je Satz, Materialpreis abweichend, Gewinde "
                       "geprüft, Zusatzarbeiten (solange keine Position einen Wert hat)",
         "Pos., Artikelnummer, Bezeichnung, Profil-ID, Werkstoff-ID, Teilelänge, Stückzahl, Schneidweg, Einstiche, "
         "Schneidzeit, Status"]], [32, 80, 70])
    i.text("Ob ein Wert 0 ist, prüft das Programm an der Zahl, nicht am Text: „0,00 €“ und „0 %“ sind 0, "
           "„10,00 €“ nicht.")
    i.bild("angebot_erweitert", "Erweiterte Einstellungen und Maschinenparameter aufgeklappt (Frachtkosten 0 €)",
           hoehe=90 * mm)
    i.abschnitt("Übersicht")
    i.liste("Ganz oben der <b>Stand der Optimierung</b>: <i>Noch nicht optimiert</i> (gelb), <i>Optimierung "
            "abgeschlossen</i> (grün) oder <i>Veraltet</i> (rot, Kapitel 8.2).",
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
        ["Profil-ID, Werkstoff-ID", "aus der Auswahlliste der Stammdaten (Pflicht), Werkstoffe nach Kategorie "
                                    "gruppiert. Optimiert wird je Profil + Werkstoff + Oberfläche + Stangenlänge, "
                                    "nie gemischt."],
        ["Oberfläche", "z. B. K240 oder gestrahlt (Stammdaten Oberflächen); leer = roh. Der Aufpreis kommt auf den "
                       "Materialpreis, der Text ins Angebot."],
        ["Teilelänge [mm], Stückzahl", "Pflicht"],
        ["Schneidweg je Teil [mm], Einstiche je Teil", "für die Laserzeit; der STEP-Import füllt sie aus"],
        ["Schneidzeit je Teil [s]", "grau = berechnet; anpassen ersetzt die berechnete Schneidzeit (Kapitel 6.6)"],
        ["Stangenlänge abweichend", "nur wenn diese Position aus einer anderen Stangenlänge geschnitten wird"],
        ["Satz, Stück je Satz", "Zusammengehörige Teile (z. B. ein Gestell) für Staffelpreise je Satz (Kapitel 9)"],
        ["Materialpreis abweichend [€/m]", "Sonderpreis nur für dieses Angebot; geht vor Preise und Tonnenpreis"],
        ["Gewinde geprüft", "z. B. <i>4xM6; 2xM8</i>. Nur was hier steht, wird als Gewinde gerechnet."],
        ["Zusatzarbeiten", "Kurzanzeige der gewählten Zusatzarbeiten; Doppelklick öffnet die Auswahl (Kapitel 6.5)"],
        ["Abweichung Schneidweg zu STEP [mm]", "nur sichtbar, wenn der Schneidweg einer importierten Position von Hand "
                                               "geändert wurde: eingetragener Schneidweg minus Anfangsschnitt + "
                                               "Endschnitt + Innenkonturen aus STEP (gelb)"]],
        [75, 190])
    i.text("Die Spalten von Oberfläche bis Zusatzarbeiten erscheinen von selbst, sobald eine Position dort einen "
           "Wert hat. Mit <b>Weitere Spalten</b> (in der Zeile über der Tabelle) lässt sich jede dieser Spalten fest ein- "
           "oder ausblenden, z. B. um bei einem neuen Angebot gleich Sätze einzutragen; leere Spalten sind dort mit "
           "„(leer)“ markiert. Die Wahl gilt für alle Angebote, bis <i>Automatisch: Spalten mit Werten zeigen</i> sie "
           "zurücksetzt. Ausgeblendete Spalten verlieren keine Werte.")
    i.liste("<b>STEP-Werte (aus CAD)</b>: aus dem importierten CAD-Modell gemessene Werte (Anfangs- und Endschnitt, "
            "Innenkonturen, Gravur, Bohrungen, Konturgrößen) und die Abweichung des Schneidwegs.",
            "<b>Berechnete Werte (Programm)</b>: vom Programm ermittelte Werte wie Profilform, Gewicht, wirksame "
            "Stangenlänge, Vorschub und eingeplante Teile.")
    i.bild("angebot_berechnet", "Mit Häkchen „Berechnete Werte“: Gewicht, Laserzeit, Stück- und Positionspreis je "
                                "Zeile", hoehe=125 * mm)


    i.abschnitt("Zusatzarbeiten und Gewinde je Bauteil")
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
    i.abschnitt("Schneidzeit anpassen")
    i.text("Die Spalte <b>Schneidzeit je Teil [s]</b> zeigt in Grau die berechnete Schneidzeit (Schneidweg, "
           "Konturklassen, Gravur und Einstiche mit den Vorschüben aus den Schneiddaten; ohne Einsparung gemeinsamer "
           "Schnitte). Ist sie nicht passend (z. B. aus einer Probe oder der Maschinensoftware bekannt), doppelt "
           "klicken: die berechnete Zeit steht im Feld und lässt sich ändern. Die eingetragene Zeit steht dann fett "
           "und ersetzt "
           "die berechnete Zeit ganz, auch die Einsparung durch gemeinsame Schnitte wird nicht mehr abgezogen. Zeiten "
           "aus Zusatzarbeiten (Gravur extra) kommen weiterhin dazu. Der Status zeigt <b>HINWEIS: Schneidzeit "
           "manuell</b>, die Kalkulation in der Spalte <i>Schneidzeit manuell</i> ein „ja“. Feld leeren = wieder "
           "berechnet.")
    i.bild("angebot_zusatz", "Positionen mit Zusatzarbeiten und angepasster Schneidzeit", hoehe=110 * mm, legende=[
        (1, "Spalte <b>Schneidzeit je Teil [s]</b>: grau berechnet, fett angepasst."),
        (2, "Spalte <b>Zusatzarbeiten</b>: Doppelklick öffnet die Auswahl."),
        (3, "Status <b>HINWEIS: Schneidzeit manuell</b>.")])


def kapitel_step(i):
    i.kapitel("STEP-Import")
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
            "Die Teile sind nach gemessenem Profil gruppiert. Eine rote Gruppenzeile heißt: dieses Profil steht nicht in "
            "den Stammdaten (beim Übernehmen fragt das Programm, ob es angelegt werden soll).",
            "<b>Häkchen</b> vor dem Teil: übernehmen ja/nein. Abgewählte Teile stehen nur im STEP-Protokoll.",
            "<b>Profil-ID</b>: vorgeschlagen ist das passende Profil der Stammdaten. Ein anderes wählen oder eine neue "
            "ID eintippen, z. B. wenn ein Teil aus einem anderen Rohr gefertigt wird.",
            "<b>Werkstoff-ID</b> (nach Kategorie gruppiert) und <b>Stückzahl</b> je Teil; leer = später im Angebot eintragen. Ist oben eine "
            "Anzahl Sätze eingetragen, heißt die Spalte <b>Stück je Satz</b> (siehe Baugruppen als Satz).",
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
           "(z. B. 60,02 statt 60) und Freiformflächen. Maße stimmen dabei auf 0,01 mm, Winkel auf 0,1°.")
    i.text("Bekannte Grenzen:")
    i.liste("Gebogene Rohre und Rohre mit veränderlichem Querschnitt: keine Maße, Prüfstatus <i>nicht messbar</i>.",
            "Rohre mit Sicke oder anderem nicht konvexem Querschnitt werden über ihr umschließendes Rechteck "
            "gemessen und stehen mit Prüfstatus <i>prüfen</i> da.",
            "Gewinde werden nur als Kernloch erkannt; der Gewindevorschlag ist von Hand zu prüfen.",
            "Bei U-, L-, C-Profilen und Flachstahl steht die Lage einer Kontur nur entlang der Achse, nicht ob sie "
            "im Steg oder im Flansch liegt. Vierkant- und Rundstahl sowie andere offene Profile (z. B. T-Profil, "
            "<i>offenes Sonderprofil</i>) werden nur gemeldet, nicht übernommen.",
            "Schräge Bohrungen werden über ihre Zylinderfläche erkannt; andere schräge Durchbrüche erscheinen als "
            "Ausschnitt.",
            "Flächenmodelle werden nur gemessen, wenn sie sich zu einem geschlossenen Körper vernähen lassen; "
            "lose Flächen daneben stehen als <i>Flächenmodell offen</i> im Protokoll.",
            "<i>plausibel</i> heißt: die Messung ist in sich stimmig. Es ist keine Fertigungsfreigabe.")
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
           "wie einen von Hand angelegten (Kapitel Staffelpreise).")
    i.bild("step_satz_pruefen", "Baugruppe im Prüfdialog: 4 Sätze eingetragen", hoehe=80 * mm, legende=[
        (1, "<b>Sätze</b>: Anzahl Sätze; leer = Einzelpositionen. Rechts daneben der Satzname."),
        (2, "Die Spalte zeigt jetzt <b>Stück je Satz</b>.")])
    i.bild("step_satz_positionen", "Baugruppe als Satz: 3 gleiche Quadratrohre und 1 Rundrohr, 4 Sätze",
           hoehe=110 * mm, legende=[(1, "Spalten <b>Satz</b>, <b>Stück je Satz</b> und <b>Stückzahl</b>.")])
    i.abschnitt("Messregeln")
    i.liste("Gerade Rohre mit konstantem Querschnitt (keine Biegeteile). Rund-, Quadrat- und Rechteckrohr werden "
            "erkannt, alles andere als Sonderprofil gemeldet.",
            "Teilelänge = größte Ausdehnung entlang der Rohrachse (bei Gehrung die lange Seite).",
            "Schneidweg = Anfangsschnitt + Endschnitt + Innenkonturen auf der Außenhaut. Gravuren (nicht durch die "
            "Wand) zählen getrennt.",
            "Innenkonturen werden nach ihrem größten Hüllmaß klein, mittel oder groß eingestuft (Grenzen je "
            "Maschine, Vorgabe 10 und 50 mm); jede Klasse hat ihren eigenen Vorschub.",
            "Profilabgleich mit den Stammdaten über Form und Maße (±0,15 mm).")


def kapitel_optimieren(i):
    i.kapitel("Optimieren und Ergebnisse")
    i.text("<b>Optimieren</b> verteilt alle gültigen Positionen auf Stangen, prüft jede Stange gegen Überlast und "
           "rechnet die Kalkulation. Danach zeigt die Übersicht <b>Optimierung abgeschlossen</b> (grün).")
    i.abschnitt("Regeln der Optimierung")
    i.liste("Je Profil + Werkstoff + Oberfläche + Stangenlänge getrennt, ohne Vermischung.",
            "Belegung einer Stange = Endbeschnitt + Teile + Trennschnitte + Schnittverlust des letzten Schnitts; "
            "der Greiferrest muss frei bleiben.",
            "Zwei Teile mit geraden, aneinanderliegenden Enden teilen sich einen Schnitt (einmal Schnittverlust, ein "
            "Einstich gespart). Sonst zwei Schnitte mit dem Abstand aus <i>Maschinen</i>. Teile werden dafür "
            "gedreht; schräge Enden kommen an Stangenanfang oder -ende.",
            "Verfahren: First-Fit und Best-Fit, danach Nachbesserung; bei Gruppen bis 60 Teile zusätzlich eine "
            "exakte Suche, die beweist, ob es mit weniger Stangen ginge.",
            "Keine Restverwaltung: Reste zählen als Verschnitt.")
    i.abschnitt("Optimierung veraltet")
    i.text("Ändert sich danach etwas am Angebot oder an den Stammdaten, zeigt die Übersicht <b>Veraltet</b>. Die "
           "Ergebnisse gelten dann nicht mehr; einfach neu optimieren. Vor einer Ausgabe mit veraltetem Stand fragt "
           "das Programm nach.")
    i.bild("angebot_veraltet", "Nach einer Änderung der Stückzahl: Stand Veraltet", hoehe=125 * mm,
           legende=[(1, "Stand der Optimierung: grün Optimierung abgeschlossen, gelb noch nicht optimiert, rot "
                        "Veraltet.")])
    i.abschnitt("Kalkulation")
    i.text("Der Reiter <i>Kalkulation</i> zeigt oben die Summen des Angebots und darunter je Position Material, "
           "Laserzeit, Gewinde, Rüsten, Herstellkosten und Verkaufspreis je Teil und je Position.")
    i.text("Reiter Kalkulation, Kalkulations-PDF und CSV-Export führen jede Kostenart des Angebots einzeln auf "
           "(die Übersicht nach Gruppen, einzeln unter <i>Kostenarten einzeln</i>); im Reiter fehlen Kostenarten "
           "mit 0,00 €, PDF und CSV enthalten alle: Material, Laser schneiden, Gewinde, Rüsten Maschine, Rüsten je "
           "Abmessung, Stangenwechsel, Weitere Arbeitsschritte, Zusatzarbeiten, Zuschlag Material, Zuschlag Fertigung, Zuschlag "
           "Fremdleistung ergeben die <b>Herstellkosten</b>; dazu Gewinn, Pauschale je Abmessung, "
           "Programmierkosten, Angebotsaufschlag, Fracht und Skonto ergeben den <b>Verkaufspreis</b>. In Klammern stehen "
           "Zeiten, Anzahl und Prozentsätze, aus denen der Betrag entsteht.")
    i.bild("erg_kalkulation", "Reiter Kalkulation", hoehe=80 * mm)
    i.liste("<b>Material</b>: Kosten der geplanten Stangen je Gruppe, nach Längenanteil auf die Positionen verteilt "
            "(Verschnitt ist enthalten). Preis: abweichender Preis der Position, sonst <i>Preise</i>, sonst "
            "Tonnenpreis des Werkstoffs; bei den beiden letzten kommt der Aufpreis der Oberfläche je m dazu.",
            "<b>Laser</b>: Vorschübe aus den Schneiddaten (Werkstoff, sonst Kategorie; N₂ vor O₂). Schneidweg je "
            "Konturklasse durch deren Vorschub, Gravur mit eigenem Vorschub, plus "
            "Einstiche × Einstechzeit; gemeinsame Schnitte sind abgezogen. Eine manuelle Schneidzeit ersetzt diesen "
            "Wert; Zeiten aus Zusatzarbeiten (s/Stück) kommen dazu.",
            "<b>Gewinde</b>: Anzahl × Preis je Gewinde (Stammdaten); ohne Preis Anzahl × Zeit mit dem Stundensatz "
            "des Arbeitsschritts Gewinde.",
            "<b>Zusatzarbeiten</b>: Menge × Preis je Teil, ggf. auf den Mindestbetrag angehoben; Fremdleistungen mit "
            "dem Zuschlag Fremdleistung.",
            "<b>Rüsten</b>: Rüstzeit je Angebot (Maschine), Rüstzeit je Abmessung (Einstellungen) und "
            "Stangenwechsel je Stange, gleichmäßig auf alle Teile verteilt, je mit dem Stundensatz ihres "
            "Arbeitsschritts.",
            "<b>Weitere Arbeitsschritte</b>: Zeiten aus den Arbeitsschritten (Kapitel 4.3) × Stundensatz, auf die "
            "Teile verteilt (Spalte <i>Weitere Arbeitsschritte je Teil</i>).",
            "<b>Pauschale je Abmessung, Programmierkosten je Teil, Angebotsaufschlag, Fracht</b>: ohne Zuschläge auf "
            "den Preis. Die Programmierkosten fallen einmal je Position an, egal wie viele Stück.",
            "<b>Skonto</b>: der Betrag, um den der Preis steigt, damit nach Abzug des Skontos der Preis ohne Skonto "
            "bleibt (Skonto % des Verkaufspreises). Je Teil in der Spalte <i>Skonto je Teil</i>.")
    i.abschnitt("Zeiten & Arbeitskosten")
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
            "Zeiten. Ist-Zeiten gehören in die Nachkalkulation (Kapitel 10).")
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


def kapitel_staffeln(i):
    i.kapitel("Staffelpreise")
    i.text("Im Reiter <i>Staffeln</i> rechnet das Programm Preise für andere Mengen. Jede Mengenstufe wird als "
           "eigenes Angebot neu optimiert und kalkuliert, weil Rüsten, Stangenwechsel und Verschnitt je Menge neu "
           "anfallen. Das eigentliche Angebot bleibt unverändert. Jede Stufe kann eigene Werte haben "
           "(Materialzuschlag, Gewinn, Nebenkosten …); leere Felder nehmen den Wert des Angebots.")
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
                                          "Betrag €/Einheit. Ersetzt für diese Stufe den Zuschlag Material des "
                                          "Angebots (leer = Zuschlag Material des Angebots)"],
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


def kapitel_nachkalkulation(i):
    i.kapitel("Nachkalkulation")
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
            "(z. B. Rechnung der Verzinkerei), <b>Sonstige Kosten Ist</b> [€] (z. B. Nacharbeit), <b>Erlös laut "
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


def kapitel_ausgabe(i, seiten, ablage):
    i.kapitel("Ausgabe: Angebot, Werkstattpapiere, Kalkulation")
    i.text("Die Knöpfe rechts neben <b>Ausgabe</b> im Angebot erzeugen die Unterlagen. Jede Datei wird im Ablageordner gespeichert "
           "und gleich geöffnet. Ist die Optimierung veraltet, fragt das Programm vorher.")
    i.bild("ausgabe_leiste", hoehe=60 * mm, legende=[
        (1, "<b>Angebot (PDF)</b>: Briefkopf, Kunde mit Anschrift aus dem Kundenstamm, Positionen mit "
            "Bezeichnung, Stück- und Gesamtpreis, Sätze, Summe mit MwSt., Preistreppe der Staffeln, "
            "Zahlungsbedingung (z. B. „Zahlung innerhalb 10 Tagen mit 2 % Skonto oder innerhalb 30 Tagen netto.“) "
            "und Bedingungen."),
        (2, "<b>Werkstattpapiere (PDF)</b>: Materialliste und je Stangenmuster der Schnittplan zum Abhaken, "
            "danach das Stangenbild."),
        (3, "<b>Kalkulation (PDF)</b>: alle Kalkulationswerte je Position für die interne Ablage."),
        (4, "<b>Weitere Aktionen</b>: <b>CSV-Export</b> schreibt Angebotskopf, alle Kostenarten und die "
            "Kalkulation je Position als CSV-Datei (Semikolon, Dezimalkomma), z. B. zum Weiterverarbeiten in einer "
            "Tabellenkalkulation; <b>Ablage öffnen</b> zeigt den Ablageordner im Explorer.")])
    i.text("Die Dateien heißen nach der Angebotsnummer, z. B.: " + ", ".join(f"<i>{a}</i>" for a in ablage) + ".")
    i.abschnitt("Angebot")
    i.bilder_nebeneinander(["pdf_angebot_1"], "Angebot A-2026-0041 (Seite 1)", hoehe=150 * mm)
    i.abschnitt("Werkstattpapiere")
    letzte = f"pdf_werkstatt_{seiten['werkstatt']}"
    i.bilder_nebeneinander(["pdf_werkstatt_1", letzte],
                           "Werkstattpapiere: Materialliste und Schnittpläne (links), Stangenbild (rechts)",
                           hoehe=150 * mm)
    i.abschnitt("Kalkulation")
    i.bilder_nebeneinander(["pdf_kalkulation_1"], "Kalkulation A-2026-0041", hoehe=150 * mm)


def kapitel_fragen(i):
    i.kapitel("Häufige Fragen und Meldungen")
    i.tabelle(["Meldung / Frage", "Ursache und Abhilfe"], [
        ["Startseite rot: <i>Die Stammdaten sind Beispielwerte</i>",
         "Die Stammdaten wurden noch nicht bearbeitet. Eigene Werte im Reiter Einstellungen eintragen "
         "(Kapitel 3); nach der ersten Änderung verschwindet der Hinweis."],
        ["Position mit <b>FEHLER: Profil fehlt</b> o. ä.",
         "Profil-ID oder Werkstoff-ID steht nicht in den Stammdaten oder ist falsch geschrieben. Aus der "
         "Auswahlliste wählen oder in den Stammdaten anlegen."],
        ["Teil unter <b>nicht eingeplante Teile</b>",
         "Teil länger als die Nutzlänge (Stange − Endbeschnitt − Greiferrest), Profil über max. Hüllkreis oder "
         "Metergewicht der Maschine, oder Pflichtangaben fehlen. Grund steht in der Auswertung."],
        ["Übersicht zeigt <b>Veraltet</b>", "Nach der letzten Optimierung wurde etwas geändert. Neu optimieren."],
        ["Windows meldet einen <b>Virus</b> oder <b>„Der Computer wurde durch Windows geschützt“</b>",
         "Fehlalarm bei einem nicht signierten Programm. Abschnitt <i>Windows-Warnungen</i> in Kapitel 2: ZIP vor dem "
         "Entpacken zulassen, Trotzdem ausführen, Datei aus der Quarantäne wiederherstellen und an Microsoft "
         "melden."],
        ["<b>Das Update ist nicht gelungen</b>",
         "Eine Programmdatei ließ sich nicht austauschen, meist weil sie gerade offen ist (Bedienungsanleitung im "
         "PDF-Programm, laufender STEP-Import). Das Programm hat alles zurückgestellt. Datei schließen und "
         "<i>Hilfe → Nach Updates suchen …</i> noch einmal aufrufen."],
        ["<b>Keine Verbindung zum Update</b>",
         "Kein Internet, oder eine Firewall sperrt github.com. Später noch einmal versuchen; sonst das Setup "
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
         "(Kapitel 2, Datensicherung und Umzug). Startet das Programm wegen einer beschädigten Datei nicht, bietet "
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


# ---------------------------------------------------------------- Ablauf
def bilder_erzeugen(ordner):
    umgebung = dict(os.environ, QT_QPA_PLATFORM="offscreen", QT_SCALE_FACTOR="2")
    subprocess.run([sys.executable, str(HIER / "bilder.py"), str(ordner)], check=True, env=umgebung)


def pdf_bauen(bilder_ordner, ziel):
    daten = json.loads((Path(bilder_ordner) / "bilder.json").read_text(encoding="utf-8"))
    bilder = dict(daten["bilder"], _ordner=Path(bilder_ordner))
    stand = datetime.date.today().strftime("%d.%m.%Y")
    inh = Inhalt(bilder)
    titelseite(inh, stand)
    inh.f.append(PageBreak())
    for kapitel in (kapitel_ueberblick, kapitel_start, kapitel_stammdaten, kapitel_einstellungen,
                    kapitel_angebote, kapitel_angebot, kapitel_step, kapitel_optimieren, kapitel_staffeln,
                    kapitel_nachkalkulation):
        kapitel(inh)
    kapitel_ausgabe(inh, daten["seiten"], daten["ablage"])
    kapitel_fragen(inh)
    # die erste Kapitelüberschrift soll keinen zusätzlichen Seitenumbruch erzeugen
    inh.f = [x for k, x in enumerate(inh.f) if not (isinstance(x, PageBreak) and k > 0
                                                     and isinstance(inh.f[k - 1], PageBreak))]
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
