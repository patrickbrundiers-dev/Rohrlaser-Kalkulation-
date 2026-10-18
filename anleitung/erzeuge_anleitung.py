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
    f.append(Paragraph(f"Kalkulation und Materialoptimierung von Rohrlaserteilen<br/>Programmversion {VERSION} · "
                       f"Stand {stand}", S))
    f.append(Spacer(1, 8 * mm))
    inh.bild("erg_stangenbild", hoehe=95 * mm)
    f.append(Spacer(1, 4 * mm))
    f.append(Paragraph("Alle Bildschirmfotos stammen aus dem Programm selbst. Firmen, Kunden, Aufträge und Preise sind "
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
    i.text("Die Rohrlaser-Kalkulation plant für einen Auftrag, wie die Teile aus Stangen geschnitten werden, und "
           "rechnet daraus Materialbedarf, Laserzeit und Verkaufspreis. Sie ersetzt die Excel-Mappe "
           "<i>Rohrlaser_Kalkulation_v02.xlsm</i> und rechnet genau wie diese. Alles liegt in einer Datendatei "
           "neben dem Programm; eine Installation ist nicht nötig.",
           "Der normale Arbeitsablauf für einen Auftrag:")
    i.liste("<b>Auftrag anlegen</b> (Reiter <i>Aufträge</i> → <i>Neuer Auftrag</i>) und den Kopf ausfüllen: Kunde, "
            "Maschine, Stangenlänge.",
            "<b>Positionen erfassen</b>: von Hand eintippen oder Konstruktionsdaten per <i>STEP importieren</i> "
            "einlesen (Länge, Profil, Schneidweg, Einstiche, Gewinde-Vorschlag).",
            "<b>Optimieren</b>: das Programm verteilt die Teile auf möglichst wenige Stangen und rechnet die "
            "Kalkulation.",
            "<b>Ergebnis prüfen</b>: Schnittplan, Stangenbild, Auswertung, nicht eingeplante Teile.",
            "Bei Bedarf <b>Staffelpreise</b> für weitere Mengen rechnen.",
            "<b>Ausgeben</b>: Angebot, Werkstattpapiere und Kalkulation als PDF, auf Wunsch Excel-Export.",
            nummeriert=True)
    i.text("Die Stammdaten (Profile, Werkstoffe, Preise, Maschinen, Schneiddaten, Gewinde) und die Einstellungen "
           "werden einmal eingerichtet, am einfachsten durch Übernahme aus der gepflegten Excel-Mappe (Kapitel 3).")
    i.abschnitt("Aufbau des Fensters")
    i.text("Das Hauptfenster besteht aus Reitern. Die festen Reiter sind <i>Start</i>, <i>Aufträge</i>, die sechs "
           "Stammdaten-Tabellen und <i>Einstellungen</i>. Jeder geöffnete Auftrag bekommt einen eigenen Reiter "
           "(<i>Auftrag A-2026-0041</i>), der sich mit dem kleinen × schließen lässt. Unten in der Statuszeile "
           "meldet das Programm, was es gerade gespeichert oder gerechnet hat; Fehlermeldungen erscheinen dort rot.")
    i.bild("auftrag_optimiert", "Hauptfenster mit geöffnetem Auftrag nach dem Optimieren", hoehe=125 * mm)
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
    i.abschnitt("Programm entpacken")
    i.liste("Auf GitHub unter <b>Releases → aktuell</b> die Datei <b>Rohrlaser-Programm.zip</b> herunterladen.",
            "In einen Ordner entpacken, in dem man schreiben darf, z. B. <i>C:\\Rohrlaser</i>. Nicht nach "
            "<i>C:\\Programme</i>, dort darf das Programm seine Daten nicht ablegen.",
            "<b>Rohrlaser-Kalkulation.exe</b> starten. Wer will, legt sich eine Verknüpfung auf den Desktop "
            "(rechte Maustaste → Senden an → Desktop).", nummeriert=True)
    i.text("Der Programmordner sieht danach so aus:")
    i.tabelle(["Datei / Ordner", "Inhalt"], [
        ["Rohrlaser-Kalkulation.exe", "das Programm"],
        ["Bedienungsanleitung.pdf", "diese Anleitung (auch über <i>Hilfe → Bedienungsanleitung</i> oder F1)"],
        ["STEP-Import\\", "Messprogramm für STEP-Dateien. Muss neben der .exe liegen bleiben."],
        ["_internal\\", "Programmbibliotheken, nicht verändern"],
        ["Daten\\rohrlaser.db", "Datendatei: Stammdaten, Einstellungen, alle Aufträge. Wird beim ersten Start "
                                "angelegt."],
        ["Daten\\Sicherung\\", "automatische Sicherungen der Datendatei (die letzten 30)"],
        ["Aufträge\\", "Ablage für PDF und Excel-Export (wenn in den Einstellungen nichts anderes steht)"]],
        [60, 205])
    i.hinweis("Meldet Windows beim ersten Start „Der Computer wurde durch Windows geschützt“, auf <i>Weitere "
              "Informationen</i> und dann <i>Trotzdem ausführen</i> klicken. Das Programm ist nicht signiert.",
              "Windows-Schutz")
    i.abschnitt("Startseite")
    i.text("Beim ersten Start legt das Programm die Datendatei mit Beispiel-Stammdaten an. Die Startseite zeigt in "
           "Rot, dass es sich um Beispielwerte handelt.")
    i.bild("start_beispiel", "Startseite nach dem ersten Start (Beispiel-Stammdaten)", hoehe=112 * mm, legende=[
        (1, "<b>Stammdaten aus Excel-Mappe übernehmen</b>: holt die gepflegten Stammdaten aus der Kalkulationsmappe "
            "(Kapitel 3.1)."),
        (2, "<b>Datensicherung erstellen</b>: Kopie der Datendatei nach <i>Daten\\Sicherung</i>."),
        (3, "<b>Datenordner öffnen</b>: zeigt den Ordner mit der Datendatei im Explorer.")])
    i.abschnitt("Datensicherung und Umzug")
    i.text("Beim ersten Start jedes Tages und vor jeder Übernahme aus einer Excel-Mappe legt das Programm "
           "automatisch eine Kopie der Datendatei in <i>Daten\\Sicherung</i> an; die letzten 30 bleiben erhalten. "
           "Zurückholen: Programm schließen, <i>Daten\\rohrlaser.db</i> umbenennen und die gewünschte Sicherung als "
           "<i>rohrlaser.db</i> in den Ordner <i>Daten</i> kopieren.",
           "Für einen anderen Rechner einfach den ganzen Programmordner kopieren. Das Programm ist für einen "
           "Arbeitsplatz gedacht; nicht von zwei Rechnern gleichzeitig mit derselben Datendatei arbeiten.")


def kapitel_stammdaten(i):
    i.kapitel("Stammdaten")
    i.abschnitt("Übernahme aus der Excel-Mappe")
    i.text("Wer die Kalkulationsmappe schon gepflegt hat, übernimmt die Stammdaten mit einem Klick: auf der "
           "Startseite oder im Menü <i>Datei</i> den Punkt <b>Stammdaten aus Excel-Mappe übernehmen …</b> wählen und "
           "die Mappe (Vorlage oder abgelegte Auftragsmappe, .xlsm oder .xlsx) auswählen. Das Programm zeigt vorher, "
           "was übernommen wird, und meldet doppelte Zeilen oder unlesbare Werte.")
    i.bilder_nebeneinander(["uebernahme_frage", "start_mappe"],
                           "Links: Rückfrage vor der Übernahme. Rechts: Startseite danach mit Herkunft und Stand.",
                           hoehe=80 * mm)
    i.text("Übernommen werden Profile, Werkstoffe, Preise, Maschinen, Schneiddaten, Gewinde, die Zuschläge, der "
           "Angebotskopf und die Auftragsvorgaben. Die bisherigen Stammdaten im Programm werden ersetzt; vorher wird "
           "eine Sicherung angelegt. Aufträge bleiben unberührt.")
    i.abschnitt("Tabellen bearbeiten")
    i.text("Jede Stammdaten-Tabelle hat einen eigenen Reiter. Alle sind gleich aufgebaut:")
    i.bild("stamm_profile", "Reiter Profile", hoehe=125 * mm, legende=[
        (1, "Reiter der Tabelle. Oben steht ein kurzer Hinweis, was in die Spalten gehört."),
        (2, "<b>Neue Zeile</b> hängt eine leere Zeile an und springt hinein."),
        (3, "<b>Zeilen löschen</b> löscht die markierten Zeilen (vorher Rückfrage; verweisen andere Tabellen "
            "darauf, sagt das Programm wie viele)."),
        (4, "<b>Suchen</b> filtert die Tabelle nach jedem Text in jeder Spalte."),
        (5, "<b>Prüfung</b>: OK, WARNUNG oder FEHLER mit Begründung, wie in der Mappe.")])
    i.liste("Bearbeiten: Zelle doppelklicken oder einfach lostippen, mit Enter bestätigen. Felder mit fester Auswahl "
            "(Profilform, Preisbasis, Profil-ID …) zeigen eine Liste.",
            "Sortieren: auf den Spaltenkopf klicken. Spaltenbreite: Trennlinie im Kopf ziehen.",
            "Wird eine Profil-, Werkstoff- oder Maschinen-ID umbenannt, ändern sich die Verweise in Preisen und "
            "Schneiddaten mit.")
    i.abschnitt("Was in welche Tabelle gehört")
    i.tabelle(["Tabelle", "Inhalt", "Wichtig"], [
        ["Profile", "Profil-ID (z. B. <i>QR 40x40x3</i>), Form, Abmessungen, Wandstärke",
         "Abmessung A = Ø bzw. Breite, B = Höhe (nur Rechteckrohr). Endbeschnitt und Greiferrest nur bei "
         "Abweichung von der Maschine. Unbekannte Profile im Auftrag legt das Programm aus der ID selbst an "
         "(RR/QR/RE-Schema)."],
        ["Werkstoffe", "Werkstoff-ID, Dichte, Tonnenpreis, Text im Angebot",
         "Der Tonnenpreis ergibt den Preis je kg, je m und je Stange, wenn unter Preise nichts steht."],
        ["Preise", "Preis je Profil + Werkstoff in €/kg, €/m oder €/Stange",
         "Je Kombination höchstens eine Zeile. €/Stange bezieht sich auf die Liefer-Stangenlänge."],
        ["Maschinen", "Endbeschnitt, Greiferrest, Schnittverlust, max. Stangenlänge, Stundensatz, Konturgrenzen, "
                      "Rüstzeit, Stangenwechsel, max. Hüllkreis und Metergewicht",
         "Profile über dem max. Hüllkreis-Ø oder Metergewicht bekommen im Auftrag FEHLER und werden nicht "
         "eingeplant (leer = keine Grenze)."],
        ["Schneiddaten", "Vorschübe je Maschine + Werkstoff, gestaffelt nach Wandstärke; Einstechzeit",
         "Es gilt die Zeile mit der kleinsten „Wandstärke bis“, die mindestens der Profilwandstärke entspricht."],
        ["Gewinde", "Gewinde, Kernloch-Ø, Zeit je Gewinde",
         "Der STEP-Import erkennt Kernlochbohrungen an diesem Durchmesser (±0,05 mm)."]], [30, 95, 140])
    i.bild("stamm_maschinen", "Reiter Maschinen: die Werte gelten für jeden Auftrag mit dieser Maschine",
           hoehe=125 * mm)


def kapitel_einstellungen(i):
    i.kapitel("Einstellungen")
    i.text("Im Reiter <i>Einstellungen</i> stehen die Werte, die für alle Aufträge gelten. Änderungen werden beim "
           "Verlassen des Feldes gespeichert und wirken ab der nächsten Rechnung.")
    i.bild("einstellungen", "Reiter Einstellungen (oberer Teil)", hoehe=125 * mm)
    i.tabelle(["Gruppe", "Einstellung", "Wirkung"], [
        ["Kalkulation", "Zuschlag Material, Zuschlag Fertigung, Gewinn",
         "Herstellkosten = Material × (1 + Zuschlag Material) + Fertigung × (1 + Zuschlag Fertigung); "
         "Verkaufspreis = Herstellkosten × (1 + Gewinn)."],
        ["Kalkulation", "Rüstzeit je Abmessung [min]",
         "je verschiedenem Profil im Auftrag, über den Stundensatz der Maschine mit Zuschlägen gerechnet"],
        ["Kalkulation", "Pauschale je Abmessung [€], Auftragsaufschlag je Auftrag [€]",
         "fester Betrag ohne Zuschläge auf den Preis; verteilt auf die Teile"],
        ["Auftrag", "Standard-Maschine, Standard-Stangenlänge", "Vorgabe für neue Aufträge"],
        ["Auftrag", "Letzte Auftragsnummer", "Ein neuer Auftrag bekommt die nächste Nummer (A-2026-0041 → "
                                             "A-2026-0042)."],
        ["Angebot", "Briefkopf Zeile 1–4, MwSt.-Satz, Gültigkeit, Bedingungen", "Kopf und Text des Angebots-PDF"],
        ["Ablage", "Ablageordner", "Ziel für PDF und Excel-Export; leer = Ordner <i>Aufträge</i> neben dem "
                                   "Programm. Auch ein Netzlaufwerk ist möglich."],
        ["Auswahllisten", "Profilformen", "Einträge der Auswahl „Profilform“ in den Profilen"]], [28, 80, 157])


def kapitel_auftraege(i):
    i.kapitel("Aufträge verwalten")
    i.text("Der Reiter <i>Aufträge</i> listet alle Aufträge, die neuesten oben. Doppelklick öffnet einen Auftrag in "
           "einem eigenen Reiter.")
    i.bild("auftraege", "Reiter Aufträge", hoehe=125 * mm, legende=[
        (1, "Reiter <b>Aufträge</b>: Übersicht mit Positionen, Teilen und Zeitpunkt der letzten Optimierung."),
        (2, "<b>Neuer Auftrag</b>: legt einen Auftrag mit der nächsten Nummer, dem heutigen Datum, der "
            "Standard-Maschine und -Stangenlänge an und öffnet ihn."),
        (3, "<b>Kopieren</b>: Kopie des markierten Auftrags mit neuer Nummer, z. B. für eine Nachbestellung. "
            "Daneben <b>Öffnen</b> und <b>Löschen</b> (die tägliche Sicherung enthält gelöschte Aufträge weiter)."),
        (4, "<b>Auftrag aus Excel-Mappe übernehmen</b>: Kopf, Positionen und Staffeln einer abgelegten "
            "Auftragsmappe."),
        (5, "<b>Suchen</b> nach Auftragsnummer, Kunde, Kundennummer, Bemerkung, Artikelnummer oder Bezeichnung.")])


def kapitel_auftrag(i):
    i.kapitel("Auftrag bearbeiten")
    i.text("Ein geöffneter Auftrag zeigt oben den Kopf und die Übersicht, darunter die Knopfleisten und die Reiter "
           "mit Positionen und Ergebnissen.")
    i.bild("auftrag_positionen", "Auftrag A-2026-0041 vor dem Optimieren", hoehe=125 * mm, legende=[
        (1, "<b>Auftragskopf</b>: Nummer, Kunde, Datum, Maschine, Standard-Stangenlänge, Bemerkung, Frachtkosten. "
            "Darunter grau die Werte der gewählten Maschine."),
        (2, "<b>Übersicht</b>: Stand der Optimierung, Anzahl Positionen und Fehler, Teile, Gewicht, Kosten und "
            "Verkaufspreis des Auftrags."),
        (3, "<b>Positionen</b>: eine Zeile je Teil mit Stückzahl, Spalte Status ganz rechts."),
        (4, "<b>Neue Position</b> / <b>Positionen löschen</b> (markierte Zeilen)."),
        (5, "<b>STEP importieren</b>: Positionen aus Konstruktionsdaten (Kapitel 7)."),
        (6, "<b>Optimieren</b>: Stangen planen und Kalkulation rechnen (Kapitel 8)."),
        (7, "<b>Berechnete Werte</b> und <b>STEP-Werte</b> blenden weitere Spalten ein.")])
    i.abschnitt("Auftragskopf")
    i.liste("<b>Maschine</b> bestimmt Endbeschnitt, Greiferrest, Schnittverlust, Konturgrenzen, Stundensatz und die "
            "Schneiddaten.",
            "<b>Standard-Stangenlänge</b> gilt für alle Positionen ohne abweichende Stangenlänge.",
            "<b>Frachtkosten</b> kommen ohne Zuschläge auf den Auftragspreis.")
    i.abschnitt("Positionen")
    i.tabelle(["Spalte", "Eintrag"], [
        ["Pos., Artikelnummer, Bezeichnung", "frei; die Artikelnummer erscheint in Angebot und Werkstattpapieren"],
        ["Profil-ID, Werkstoff-ID", "aus der Auswahlliste der Stammdaten (Pflicht). Optimiert wird je Profil + "
                                    "Werkstoff + Stangenlänge, nie gemischt."],
        ["Teilelänge [mm], Stückzahl", "Pflicht"],
        ["Schneidweg je Teil [mm], Einstiche je Teil", "für die Laserzeit; der STEP-Import füllt sie aus"],
        ["Stangenlänge abweichend", "nur wenn diese Position aus einer anderen Stangenlänge geschnitten wird"],
        ["Satz, Stück je Satz", "Zusammengehörige Teile (z. B. ein Gestell) für Staffelpreise je Satz (Kapitel 9)"],
        ["Materialpreis abweichend [€/m]", "Sonderpreis nur für diesen Auftrag; geht vor Preise und Tonnenpreis"],
        ["Gewinde geprüft", "z. B. <i>4xM6; 2xM8</i>. Nur was hier steht, wird als Gewinde gerechnet."]],
        [75, 190])
    i.bild("auftrag_berechnet", "Mit Häkchen „Berechnete Werte“: Gewicht, Laserzeit, Stück- und Positionspreis je "
                                "Zeile", hoehe=125 * mm)


def kapitel_step(i):
    i.kapitel("STEP-Import")
    i.text("Der STEP-Import liest Konstruktionsdaten (.step/.stp, ein oder mehrere Rohre je Datei) und legt je "
           "Rohr eine Position an. Gemessen werden Profil, Teilelänge, Schneidweg, Einstiche, Anfangs- und "
           "Endschnitt (gerade oder schräg), Innenkonturen nach Größe, Gravuren, Bohrungen und ein "
           "Gewinde-Vorschlag. Die Messung übernimmt das Programm <i>STEP-Import.exe</i> im Ordner "
           "<i>STEP-Import</i> neben dem Programm.")
    i.liste("Im Auftrag auf <b>STEP importieren …</b> klicken und die Dateien wählen (Mehrfachauswahl mit Strg oder "
            "Umschalt).",
            "Werkstoff und Stückzahl für alle Teile angeben oder leer lassen und später eintragen.",
            "Fehlen Profile in den Stammdaten, fragt das Programm, ob sie aus den Messwerten angelegt werden sollen "
            "(danach im Reiter <i>Profile</i> prüfen). Stehen Artikel schon im Auftrag, fragt es vor dem doppelten "
            "Eintragen.",
            "Am Ende meldet es, wie viele Positionen übernommen wurden; <i>Details</i> zeigt den Bericht je Datei.",
            nummeriert=True)
    i.bilder_nebeneinander(["step_dialog"], "Werte für alle importierten Teile", hoehe=30 * mm)
    i.bild("step_positionen", "Übernommene Positionen mit eingeblendeten STEP-Werten", hoehe=125 * mm, legende=[
        (1, "<b>STEP-Werte</b> zeigt Anfangs-/Endschnitt, Innenkonturen nach Größe, Gravur, Bohrungen und den "
            "Gewinde-Vorschlag.")])
    i.hinweis("Gewinde werden nur vorgeschlagen (Status HINWEIS: Gewinde-Vorschlag prüfen). Erst wenn das Gewinde "
              "nach Prüfung der Zeichnung in die Spalte <b>Gewinde geprüft</b> eingetragen ist, wird es gerechnet.")
    i.bild("step_protokoll", "Reiter STEP-Protokoll: alle Messwerte je Datei und Körper", hoehe=80 * mm)
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
           "rechnet die Kalkulation. Danach zeigt die Übersicht <b>Stand Optimierung: aktuell</b> (grün).")
    i.abschnitt("Regeln der Optimierung")
    i.liste("Je Profil + Werkstoff + Stangenlänge getrennt, ohne Vermischung.",
            "Belegung einer Stange = Endbeschnitt + Teile + Trennschnitte + Schnittverlust des letzten Schnitts; "
            "der Greiferrest muss frei bleiben.",
            "Zwei Teile mit geraden, aneinanderliegenden Enden teilen sich einen Schnitt (einmal Schnittverlust, ein "
            "Einstich gespart). Sonst zwei Schnitte mit dem Abstand aus <i>Maschinen</i>. Teile werden dafür "
            "gedreht; schräge Enden kommen an Stangenanfang oder -ende.",
            "Verfahren: First-Fit und Best-Fit, danach Nachbesserung; bei Gruppen bis 60 Teile zusätzlich eine "
            "exakte Suche, die beweist, ob es mit weniger Stangen ginge.",
            "Keine Restverwaltung: Reste zählen als Verschnitt.")
    i.abschnitt("Optimierung veraltet")
    i.text("Ändert sich danach etwas am Auftrag oder an den Stammdaten, zeigt die Übersicht <b>VERALTET</b>. Die "
           "Ergebnisse gelten dann nicht mehr; einfach neu optimieren. Vor einer Ausgabe mit veraltetem Stand fragt "
           "das Programm nach.")
    i.bild("auftrag_veraltet", "Nach einer Änderung der Stückzahl: Stand VERALTET", hoehe=125 * mm,
           legende=[(1, "Stand der Optimierung: grün aktuell, gelb noch nicht optimiert, rot VERALTET.")])
    i.abschnitt("Kalkulation")
    i.text("Der Reiter <i>Kalkulation</i> zeigt oben die Summen des Auftrags und darunter je Position Material, "
           "Laserzeit, Gewinde, Rüsten, Herstellkosten und Verkaufspreis je Teil und je Position.")
    i.bild("erg_kalkulation", "Reiter Kalkulation", hoehe=80 * mm)
    i.liste("<b>Material</b>: Kosten der geplanten Stangen je Gruppe, nach Längenanteil auf die Positionen verteilt "
            "(Verschnitt ist enthalten). Preis: abweichender Preis der Position, sonst <i>Preise</i>, sonst "
            "Tonnenpreis des Werkstoffs.",
            "<b>Laser</b>: Schneidweg je Konturklasse durch deren Vorschub, Gravur mit eigenem Vorschub, plus "
            "Einstiche × Einstechzeit; gemeinsame Schnitte sind abgezogen.",
            "<b>Rüsten</b>: Rüstzeit je Auftrag (Maschine), Rüstzeit je Abmessung (Einstellungen) und "
            "Stangenwechsel je Stange, gleichmäßig auf alle Teile verteilt.",
            "<b>Pauschale je Abmessung, Auftragsaufschlag, Fracht</b>: ohne Zuschläge auf den Preis.")
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
           "eigener Auftrag neu optimiert und kalkuliert, weil Rüsten, Stangenwechsel und Verschnitt je Menge neu "
           "anfallen. Der eigentliche Auftrag bleibt unverändert.")
    i.bild("staffeln_vorher", "Mengenstufen für den Satz „MG 2000“ (ein Maschinengestell)", hoehe=80 * mm, legende=[
        (1, "<b>Neue Stufe</b> fügt eine Zeile an; <b>Stufen löschen</b> entfernt die markierten."),
        (2, "Je Zeile: <b>Satz oder Pos.</b> (Satzbezeichnung aus der Spalte Satz der Positionen oder eine "
            "Positionsnummer), <b>Menge</b> in Sätzen bzw. Stück, Bemerkung. Die Prüfung zeigt, was erkannt wurde."),
        (3, "<b>Staffelpreise rechnen</b> rechnet alle Stufen.")])
    i.text("Für Sätze in den Positionen die Spalten <b>Satz</b> (gleicher Name für alle Teile des Satzes) und "
           "<b>Stück je Satz</b> ausfüllen. Im Beispiel gehören zu einem Gestell 4 Stiele, 4 lange Riegel, "
           "8 kurze Riegel, 16 Streben, 2 Holme und 3 Traversen.")
    i.bild("staffeln", "Ergebnis: der Preis je Gestell sinkt mit der Menge, weil Rüsten und Verschnitt sich "
                       "auf mehr Teile verteilen",
           hoehe=85 * mm)
    i.text("Die Staffelpreise erscheinen im Angebot als Preistreppe unter den Positionen. Ändert sich danach etwas am "
           "Auftrag, zeigt der Reiter VERALTET; das Angebot rechnet veraltete Staffelpreise selbst neu.")


def kapitel_ausgabe(i, seiten, ablage):
    i.kapitel("Ausgabe: Angebot, Werkstattpapiere, Kalkulation")
    i.text("Die Leiste <b>Ausgabe</b> im Auftrag erzeugt die Unterlagen. Jede Datei wird im Ablageordner gespeichert "
           "und gleich geöffnet. Ist die Optimierung veraltet, fragt das Programm vorher.")
    i.bild("ausgabe_leiste", hoehe=60 * mm, legende=[
        (1, "<b>Angebot (PDF)</b>: Briefkopf, Positionen mit Bezeichnung, Stück- und Gesamtpreis, Sätze, Summe "
            "mit MwSt., Preistreppe der Staffeln, Bedingungen."),
        (2, "<b>Werkstattpapiere (PDF)</b>: Materialliste und je Stangenmuster der Schnittplan zum Abhaken, "
            "danach das Stangenbild."),
        (3, "<b>Kalkulation (PDF)</b>: alle Kalkulationswerte je Position für die interne Ablage."),
        (4, "<b>Excel-Export</b>: alle Ergebnisse als Werte in einer .xlsx-Datei."),
        (5, "<b>Ablage öffnen</b>: zeigt den Ablageordner im Explorer.")])
    i.text("Die Dateien heißen nach der Auftragsnummer, z. B.: " + ", ".join(f"<i>{a}</i>" for a in ablage) + ".")
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
         "Es wurden noch keine eigenen Stammdaten übernommen. Kapitel 3.1."],
        ["Position mit <b>FEHLER: Profil fehlt</b> o. ä.",
         "Profil-ID oder Werkstoff-ID steht nicht in den Stammdaten oder ist falsch geschrieben. Aus der "
         "Auswahlliste wählen oder in den Stammdaten anlegen."],
        ["Teil unter <b>nicht eingeplante Teile</b>",
         "Teil länger als die Nutzlänge (Stange − Endbeschnitt − Greiferrest), Profil über max. Hüllkreis oder "
         "Metergewicht der Maschine, oder Pflichtangaben fehlen. Grund steht in der Auswertung."],
        ["Übersicht zeigt <b>VERALTET</b>", "Nach der letzten Optimierung wurde etwas geändert. Neu optimieren."],
        ["<b>STEP-Import.exe wurde nicht gefunden</b>",
         "Der Ordner <i>STEP-Import</i> muss im Programmordner neben <i>Rohrlaser-Kalkulation.exe</i> liegen. "
         "Neu aus dem ZIP entpacken."],
        ["STEP: <b>Profil fehlt in den Stammdaten</b>",
         "Mit Ja aus den Messwerten anlegen lassen, danach im Reiter Profile prüfen (Bemerkung, Preis)."],
        ["Gewinde wird nicht gerechnet", "Nur Einträge in <b>Gewinde geprüft</b> zählen, nicht der Vorschlag."],
        ["<b>WARNUNG: kein gültiger Materialpreis</b>", "Weder Preis noch Tonnenpreis für Profil + Werkstoff "
                                                        "hinterlegt. Reiter Preise oder Werkstoffe ergänzen."],
        ["<b>WARNUNG: Stückzahl ist kein Vielfaches von Stück je Satz</b>",
         "Stückzahl und Stück je Satz der Position passen nicht zusammen (z. B. 7 Teile bei 2 je Satz)."],
        ["Ablageordner lässt sich nicht öffnen", "Pfad in den Einstellungen prüfen (Netzlaufwerk verbunden?). Leer "
                                                 "lassen = Ordner Aufträge neben dem Programm."],
        ["Daten versehentlich gelöscht oder Datendatei beschädigt",
         "Programm schließen, Sicherung aus <i>Daten\\Sicherung</i> zurückkopieren (Kapitel 2.3)."]], [85, 180])


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
                    kapitel_auftraege, kapitel_auftrag, kapitel_step, kapitel_optimieren, kapitel_staffeln):
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
