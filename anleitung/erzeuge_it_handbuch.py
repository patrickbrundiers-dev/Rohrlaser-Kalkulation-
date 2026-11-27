"""Erzeugt IT-Handbuch_Server.pdf: Voraussetzungen, Einrichtung und Betrieb des zentralen Servers (Serverversion)
für die IT im Unternehmen (Patrick 27.11.2026: „ausführlich und detailliert, ab jetzt bei jeder Änderung mit
aktualisieren“).

Alle technischen Werte (Ports, Verbindungen, Speicher, Zeiten, Befehle, Zertifikat, Sicherung) liest das Skript
direkt aus dem Programm (server_betrieb, server_sicherung, server_rechnen, server_mehrplatz, pg_lokal). Ändert sich
dort etwas, steht es beim nächsten Erzeugen automatisch im Handbuch. Neue Funktionen oder geänderte Abläufe am
Server trägt man unten in den Kapiteln ein; tests/pruefe_anleitung_geaendert.py verlangt das bei jeder Änderung an
den Server-Dateien (oder eine Zeile „IT-Handbuch: unverändert, weil …“ in einer Commit-Nachricht).

    python anleitung/erzeuge_it_handbuch.py [--ziel IT-Handbuch_Server.pdf]

Braucht nur reportlab (keine Qt, keine Datenbank). DejaVu Sans wird genutzt, wenn vorhanden (Pfeile, Sonderzeichen).
"""
import argparse
import datetime
import os
import re
import sys
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Frame, KeepTogether, PageBreak, PageTemplate,
                                Paragraph, Preformatted, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents

HIER = Path(__file__).resolve().parent
WURZEL = HIER.parent
sys.path.insert(0, str(WURZEL / "programm"))
from rohrlaser import NAME, VERSION  # noqa: E402
from rohrlaser import server_betrieb as sb  # noqa: E402
from rohrlaser import server_mehrplatz as sm  # noqa: E402
from rohrlaser import server_rechnen as sr  # noqa: E402
from rohrlaser import server_sicherung as ss  # noqa: E402

SEITE = A4
RAND = 18 * mm
BREITE = SEITE[0] - 2 * RAND
BLAU = colors.HexColor("#1F4E78")
HELLBLAU = colors.HexColor("#EAF1F8")
MITTELBLAU = colors.HexColor("#8EA9C1")
GRAU = colors.HexColor("#595959")
LINIE = colors.HexColor("#D9D9D9")
ORANGE = colors.HexColor("#C55A11")
HELLORANGE = colors.HexColor("#FBE5D6")

# Beispielwerte, die im Handbuch durchgehend verwendet werden (die IT ersetzt sie durch ihre eigenen)
SERVERNAME = "ROHRLASER-SRV"
SERVER_IP = "192.168.1.10"
SUBNETZ = "192.168.1.0/24"
SERVER_ORDNER = r"D:\RohrlaserServer"
PROGRAMM_ORDNER = r"C:\Rohrlaser"
EXE = "Rohrlaser-Angebotskalkulation.exe"
FREIGABE = r"\\ROHRLASER-SRV\Rohrlaser-Ablage"
DIENSTKONTO = r"FIRMA\svc-rohrlaser"
GRUPPE = "GG-Rohrlaser-Benutzer"

# Größen der VM nach Platzzahl: Schätzwerte (Datenbank klein, CPU vor allem für den Rechner-Dienst), bestätigt
# durch den eingebauten Lasttest auf der echten Hardware.
GROESSEN = [
    ("bis 5", "4", "8 GB", "250 GB", "500 GB"),
    ("bis 10 (Empfehlung)", "8", "16 GB", "500 GB", "1 TB"),
    ("bis 25", "12–16", "32 GB", "1 TB", "2 TB"),
]


def pg_version():
    """PostgreSQL-Version des Programmpakets, aus dem Bau-Workflow (Kommentar „Windows-Programme von PostgreSQL X“)."""
    paket = WURZEL / ".github" / "workflows" / "paket.yml"
    try:
        m = re.search(r"Windows-Programme von PostgreSQL ([\d.]+)", paket.read_text(encoding="utf-8"))
        return m.group(1) if m else "16"
    except OSError:
        return "16"


def pg_einstellungen():
    """Die Einstellungen, die der Server in postgresql.conf schreibt (dieselbe Funktion wie beim Einrichten)."""
    server = object.__new__(sb.ZentralerServer)
    server.port = sb.PORT
    werte = {}
    for zeile in server._konfiguration().splitlines():
        m = re.match(r"\s*([a-z_]+)\s*=\s*(.+?)\s*$", zeile)
        if m:
            werte[m.group(1)] = m.group(2).strip("'")
    return werte


def befehle():
    """Befehle des Servers aus der Hilfe von server_betrieb: Liste (Befehl mit Optionen, Beschreibung)."""
    ergebnis, aktuell = [], None
    for zeile in sb.HILFE.splitlines()[1:]:
        if not zeile.strip():
            continue
        if zeile.startswith("  ") and not zeile.startswith("      "):
            teile = re.split(r"\s{2,}", zeile.strip(), maxsplit=1)
            aktuell = [teile[0], teile[1] if len(teile) > 1 else ""]
            ergebnis.append(aktuell)
        elif aktuell is not None:
            aktuell[1] = (aktuell[1] + " " + zeile.strip()).strip()
    return [(b, t) for b, t in ergebnis]


# --------------------------------------------------------------------------------------------- Schrift und Stile
def schrift():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    for ordner in (Path("/usr/share/fonts/truetype/dejavu"), Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"):
        normal, fett = ordner / "DejaVuSans.ttf", ordner / "DejaVuSans-Bold.ttf"
        mono = ordner / "DejaVuSansMono.ttf"
        if normal.is_file():
            pdfmetrics.registerFont(TTFont("IT", str(normal)))
            pdfmetrics.registerFont(TTFont("IT-Fett", str(fett if fett.is_file() else normal)))
            pdfmetrics.registerFontFamily("IT", normal="IT", bold="IT-Fett", italic="IT", boldItalic="IT-Fett")
            if mono.is_file():
                pdfmetrics.registerFont(TTFont("IT-Mono", str(mono)))
                return "IT", "IT-Fett", "IT-Mono"
            return "IT", "IT-Fett", "Courier"
    return "Helvetica", "Helvetica-Bold", "Courier"


NORMAL, FETT, MONO = schrift()
PFEIL = "→" if NORMAL == "IT" else "->"


def _stil(name, **kw):
    basis = dict(fontName=NORMAL, fontSize=9.5, leading=13.5, textColor=colors.black, spaceAfter=4)
    basis.update(kw)
    return ParagraphStyle(name, **basis)


TEXT = _stil("text")
KLEIN = _stil("klein", fontSize=8.5, leading=11.5, textColor=GRAU)
ZELLE = _stil("zelle", fontSize=8.5, leading=11.5, spaceAfter=0)
ZELLE_KOPF = _stil("zellekopf", fontName=FETT, fontSize=8.5, leading=11.5, spaceAfter=0, textColor=colors.white)
H1 = _stil("h1", fontName=FETT, fontSize=17, leading=22, textColor=BLAU, spaceBefore=4, spaceAfter=8)
H2 = _stil("h2", fontName=FETT, fontSize=12, leading=16, textColor=BLAU, spaceBefore=10, spaceAfter=5)
LISTE = _stil("liste", leftIndent=12, bulletIndent=2, spaceAfter=2.5)
CODE = _stil("code", fontName=MONO, fontSize=8, leading=10.5, textColor=colors.black, spaceAfter=0)
HINWEIS = _stil("hinweis", fontSize=9, leading=12.5, spaceAfter=0)
INHALT1 = _stil("inhalt1", fontName=FETT, fontSize=10.5, leading=16, leftIndent=0)
INHALT2 = _stil("inhalt2", fontSize=9, leading=13, leftIndent=14)


def _t(text):
    """Pfeile für Menüwege; ohne DejaVu ASCII."""
    return text.replace("→", PFEIL)


# --------------------------------------------------------------------------------------------- Dokument
class Handbuch(BaseDocTemplate):
    def __init__(self, ziel):
        super().__init__(str(ziel), pagesize=SEITE, leftMargin=RAND, rightMargin=RAND, topMargin=22 * mm,
                         bottomMargin=18 * mm, title="IT-Handbuch Rohrlaser-Server", author=NAME,
                         subject="Voraussetzungen, Einrichtung und Betrieb des zentralen Servers")
        rahmen = Frame(RAND, 18 * mm, BREITE, SEITE[1] - 40 * mm, id="text")
        self.addPageTemplates([PageTemplate("titel", [rahmen], onPage=self._titelseite),
                               PageTemplate("normal", [rahmen], onPageEnd=self._seite)])
        self.kapitel_name = ""

    def afterFlowable(self, f):
        if isinstance(f, Paragraph) and f.style.name in ("h1", "h2"):
            ebene = 0 if f.style.name == "h1" else 1
            text = f.getPlainText()
            if ebene == 0:
                self.kapitel_name = text
            if text == "Inhalt":
                return
            schluessel = f"k{id(f)}"
            self.canv.bookmarkPage(schluessel)
            self.canv.addOutlineEntry(text, schluessel, level=ebene, closed=ebene > 0)
            self.notify("TOCEntry", (ebene, text, self.page, schluessel))

    def beforeDocument(self):
        self.kapitel_name = ""

    def _titelseite(self, c, doc):
        c.saveState()
        c.setFillColor(BLAU)
        c.rect(0, SEITE[1] - 95 * mm, SEITE[0], 95 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont(FETT, 26)
        c.drawString(RAND, SEITE[1] - 45 * mm, "IT-Handbuch Rohrlaser-Server")
        c.setFont(NORMAL, 13)
        c.drawString(RAND, SEITE[1] - 56 * mm, "Voraussetzungen, Einrichtung und Betrieb der Serverversion")
        c.setFont(NORMAL, 10.5)
        c.drawString(RAND, SEITE[1] - 70 * mm, f"{NAME} · Programmversion {VERSION} · "
                                                f"Stand {datetime.date.today():%d.%m.%Y}")
        c.restoreState()

    def _seite(self, c, doc):
        c.saveState()
        c.setFont(NORMAL, 8)
        c.setFillColor(GRAU)
        c.drawString(RAND, SEITE[1] - 13 * mm, "IT-Handbuch Rohrlaser-Server")
        c.drawRightString(SEITE[0] - RAND, SEITE[1] - 13 * mm, self.kapitel_name)
        c.setStrokeColor(LINIE)
        c.line(RAND, SEITE[1] - 15 * mm, SEITE[0] - RAND, SEITE[1] - 15 * mm)
        c.drawString(RAND, 10 * mm, f"Programmversion {VERSION}")
        c.drawRightString(SEITE[0] - RAND, 10 * mm, f"Seite {doc.page}")
        c.restoreState()


class Inhalt:
    """Sammelt die Bausteine (Flowables) des Handbuchs."""

    def __init__(self):
        self.teile = []
        self.nummer = 0
        self.unter = 0

    def kapitel(self, titel):
        self.nummer += 1
        self.unter = 0
        if self.nummer > 1:
            self.teile.append(PageBreak())
        self.teile.append(Paragraph(f"{self.nummer}. {titel}", H1))

    def abschnitt(self, titel):
        self.unter += 1
        self.teile.append(CondPageBreak(30 * mm))
        self.teile.append(Paragraph(f"{self.nummer}.{self.unter} {titel}", H2))

    def text(self, *absaetze):
        for a in absaetze:
            self.teile.append(Paragraph(_t(a), TEXT))

    def klein(self, text):
        self.teile.append(Paragraph(_t(text), KLEIN))

    def liste(self, *punkte, nummeriert=False):
        for i, p in enumerate(punkte, 1):
            zeichen = f"{i}." if nummeriert else "•"
            self.teile.append(Paragraph(_t(p), LISTE, bulletText=zeichen))
        self.teile.append(Spacer(1, 3))

    def haken(self, *punkte):
        for p in punkte:
            self.teile.append(Paragraph(_t(p), LISTE, bulletText="□" if NORMAL == "IT" else "[ ]"))
        self.teile.append(Spacer(1, 3))

    def code(self, text):
        block = Preformatted(text.strip("\n"), CODE)
        t = Table([[block]], colWidths=[BREITE])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F3F3")),
                               ("BOX", (0, 0), (-1, -1), 0.5, LINIE),
                               ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                               ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        self.teile.append(t)
        self.teile.append(Spacer(1, 6))

    def hinweis(self, text, warnung=False):
        t = Table([[Paragraph(_t(text), HINWEIS)]], colWidths=[BREITE])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HELLORANGE if warnung else HELLBLAU),
                               ("LINEBEFORE", (0, 0), (0, -1), 3, ORANGE if warnung else BLAU),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
        self.teile.append(t)
        self.teile.append(Spacer(1, 8))

    def tabelle(self, kopf, zeilen, breiten):
        daten = [[Paragraph(_t(k), ZELLE_KOPF) for k in kopf]]
        daten += [[Paragraph(_t(str(z)), ZELLE) for z in zeile] for zeile in zeilen]
        gesamt = sum(breiten)
        t = Table(daten, colWidths=[b * BREITE / gesamt for b in breiten], repeatRows=1)
        stil = [("BACKGROUND", (0, 0), (-1, 0), BLAU), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINIE),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        stil += [("BACKGROUND", (0, r), (-1, r), HELLBLAU) for r in range(2, len(daten), 2)]
        t.setStyle(TableStyle(stil))
        self.teile.append(t)
        self.teile.append(Spacer(1, 8))

    def bild(self, zeichnung):
        self.teile.append(KeepTogether([zeichnung, Spacer(1, 8)]))


def aufbau_bild():
    """Aufbau: Arbeitsplätze -> Server-VM (Datenbank, Ablage, Rechner-Dienst, Sicherung) -> zweites Ziel."""
    b, h = BREITE, 92 * mm
    d = Drawing(b, h)
    s = b / 760.0

    def y(v):
        return h - v * s

    def kasten(x, yo, w, hh, titel, zeilen, akzent=False, gestrichelt=False, fuellung=None):
        r = Rect(x * s, y(yo + hh), w * s, hh * s, rx=6, ry=6,
                 fillColor=fuellung or (HELLBLAU if akzent else colors.white),
                 strokeColor=BLAU if akzent else MITTELBLAU, strokeWidth=1.6 if akzent else 0.9)
        if gestrichelt:
            r.strokeDashArray = [3, 3]
        d.add(r)
        d.add(String((x + 10) * s, y(yo + 22), titel, fontName=FETT, fontSize=9.5, fillColor=colors.black))
        for i, z in enumerate(zeilen):
            d.add(String((x + 10) * s, y(yo + 40 + 15 * i), z, fontName=NORMAL, fontSize=8, fillColor=GRAU))

    def pfeil(x1, y1, x2, y2, text=None, tx=None, ty=None):
        d.add(Line(x1 * s, y(y1), x2 * s, y(y2), strokeColor=GRAU, strokeWidth=1))
        if y1 == y2:
            d.add(Polygon([x2 * s, y(y2), (x2 - 8) * s, y(y2) + 3.5, (x2 - 8) * s, y(y2) - 3.5],
                          fillColor=GRAU, strokeColor=None))
        else:
            d.add(Polygon([x2 * s, y(y2), x2 * s - 3.5, y(y2 - 8), x2 * s + 3.5, y(y2 - 8)],
                          fillColor=GRAU, strokeColor=None))
        if text:
            d.add(String(tx * s, y(ty), text, fontName=NORMAL, fontSize=7, fillColor=GRAU))

    kasten(10, 60, 210, 170, "Arbeitsplätze", ["Programm in der Serverversion", "Anmeldung je Mitarbeiter",
                                                 "Büro, Werkstatt, Laptop"])
    d.add(Rect(300 * s, y(290), 450 * s, 270 * s, rx=6, ry=6, fillColor=colors.HexColor("#F4F6F8"),
               strokeColor=MITTELBLAU, strokeWidth=0.9))
    d.add(String(312 * s, y(44), f"Server-VM {SERVERNAME} · Windows Server", fontName=FETT, fontSize=10,
                 fillColor=BLAU))
    kasten(312, 60, 205, 95, f"PostgreSQL {pg_version()}", ["Zentrale Datenbank", f"Port {sb.PORT}, nur TLS"],
           akzent=True)
    kasten(533, 60, 205, 95, "Rechner-Dienst", ["Große STEP-Importe", "Vormessung neuer Anfragen"])
    kasten(312, 175, 205, 95, "Ablage", ["Gemeinsame Dateien", "Windows-Freigabe, Port 445"])
    kasten(533, 175, 205, 95, "Sicherung", ["täglich 22:30 Uhr", "mit Rücksicherungsprobe"])
    kasten(533, 320, 205, 70, "NAS / zweites Ziel", ["Kopie Sicherung + Ablage"], gestrichelt=True)
    pfeil(220, 100, 312, 100, f"TCP {sb.PORT}, TLS", 226, 92)
    pfeil(220, 205, 312, 205, "SMB, TCP 445", 226, 197)
    pfeil(635, 270, 635, 320, "täglich, IT", 642, 300)
    return d


# --------------------------------------------------------------------------------------------- Kapitel
def kapitel_ueberblick(i):
    i.kapitel("Zweck und Aufbau")
    i.text(f"Die Serverversion von {NAME} ersetzt die bisherige Datenbank je PC (mit Abgleich über den gemeinsamen "
           "Ordner) durch <b>eine zentrale Datenbank auf einem Server-Rechner im Firmennetz</b>. Ausgelegt ist sie "
           "für 10 bis 25 gleichzeitig arbeitende Mitarbeiter. Das Programm bleibt an jedem Arbeitsplatz installiert "
           "und verbindet sich nur mit dem Server; Oberfläche, Kalkulation und Ergebnisse sind dieselben.",
           "Auf dem Server laufen vier Bausteine: die PostgreSQL-Datenbank, die Dateiablage als Windows-Freigabe, "
           "der Rechner-Dienst für lange Rechnungen und die tägliche Sicherung. Alle vier sind Teil des "
           "Programmpakets; die IT installiert keine zusätzliche Software.")
    i.bild(aufbau_bild())
    i.hinweis("<b>Grundregel: alles lokal im Firmennetz.</b> Der Server braucht keinen Internetzugang, keine Cloud, "
              "keine Portfreigabe nach außen und keine Fernwartung. Auch die eingebaute KI arbeitet nur lokal.")
    i.abschnitt("Wer macht was")
    i.tabelle(["Aufgabe", "Wer", "Abschnitt"], [
        ["VM bereitstellen, Windows, Laufwerke, Netzwerk, Firewall, Virenscanner", "IT", "2–4"],
        ["Dienstkonto, Freigabe der Ablage, Sicherungsziel außerhalb der VM", "IT", "3, 7"],
        ["Server einrichten, Aufgabenplanung, Lasttest, erste Sicherung", "IT mit Verwalter der Kalkulation", "5"],
        ["Mitarbeiter anlegen, Rechte vergeben, Daten übernehmen", "Verwalter der Kalkulation", "5, 6"],
        ["Arbeitsplätze verbinden", "IT oder Mitarbeiter", "6"],
        ["Programm-Updates", "Verwalter + IT", "8"],
        ["Überwachung, Windows-Updates, Wiederherstellungstest", "IT", "7, 8"],
    ], [60, 25, 15])
    i.abschnitt("Begriffe")
    i.tabelle(["Begriff", "Bedeutung"], [
        ["Server-Ordner", f"Ordner auf dem Server, z. B. <i>{SERVER_ORDNER}</i>: Datenbank (pg), Ablage, Sicherung, "
                          "Zertifikate, Zugangsdatei."],
        ["Zugangsdatei", f"<i>{sb.ZUGANG_DATEI}</i>: Adresse, Port und Zertifikat der Zertifizierungsstelle für die "
                         "Arbeitsplätze. Enthält kein Passwort."],
        ["Ablage", "Gemeinsame Dateien (Angebotsordner, PDF, STEP, Anfragen, Austausch, Updates, Rechenergebnisse) "
                   "als Windows-Freigabe."],
        ["Rechner-Dienst", "Rechnet große STEP-Importe und die Vormessung neuer Anfragen für die Arbeitsplätze."],
        ["Verwalter", "Mitarbeiter mit Recht <i>verwalter</i>: legt Zugänge an, hebt die Programmversion des "
                      "Servers."],
        ["Pflichtversion", "Programmversion des Servers. Nur Arbeitsplätze mit genau dieser Version dürfen "
                           "schreiben."],
    ], [22, 78])


def kapitel_voraussetzungen(i):
    pg = pg_einstellungen()
    i.kapitel("Voraussetzungen")
    i.text("Benötigt wird <b>ein Windows-Server oder eine virtuelle Maschine im Firmennetz</b>. Für 10 gleichzeitige "
           "Arbeitsplätze empfehlen wir 8 vCPU, 16 GB RAM und 500 GB SSD.")
    i.abschnitt("Hardware bzw. virtuelle Maschine")
    i.tabelle(["Gleichzeitige Plätze", "vCPU", "RAM", "SSD am Server (System + Daten + Ablage)",
               "Sicherungsziel außerhalb der VM"], GROESSEN, [20, 10, 12, 30, 28])
    i.klein("Die Größen sind Schätzwerte. Die Datenbank selbst bleibt klein (wenige GB); den Platz füllen vor allem "
            "STEP-, PDF- und Mail-Dateien in der Ablage und die täglichen Sicherungen. Der eingebaute Lasttest "
            "(Abschnitt 5) bestätigt die Größe auf der echten Hardware.")
    i.liste("<b>Nur SSD oder NVMe</b>, keine drehenden Platten: die Datenbank schreibt jede Speicherung sofort "
            f"sicher auf die Platte (fsync = {pg.get('fsync', 'on')}, synchronous_commit = "
            f"{pg.get('synchronous_commit', 'on')}).",
            "<b>Zwei Laufwerke</b>: C: für Windows und Programm (mindestens 80 GB), D: für Datenbank, Ablage und "
            "Sicherung. So hält ein volles Systemlaufwerk die Datenbank nicht an.",
            "<b>Rechenleistung</b> braucht vor allem der Rechner-Dienst: große STEP-Importe (ab "
            f"{sr.AUTO_MB:g} MB oder {sr.AUTO_DATEIEN} Dateien) und die Vormessung neuer Anfragen nutzen mehrere "
            "Kerne gleichzeitig. Mit <i>--prozesse N</i> lässt sich das begrenzen.",
            f"<b>Zwischenspeicher der Messung</b> in der Ablage: mindestens {sr.CACHE_MB_MIN / 1000:g} GB frei "
            "einplanen (alle Plätze teilen ihn).")
    i.abschnitt("Datenbank-Einstellungen (fest, keine Anpassung nötig)")
    i.tabelle(["Einstellung", "Wert", "Bedeutung"], [
        ["port", pg.get("port", sb.PORT), "Netzwerkport der Datenbank (beim Einrichten mit --port änderbar)"],
        ["listen_addresses", pg.get("listen_addresses", "*"), "hört auf alle Netzwerkkarten; Einschränkung über die "
                                                               "Firewall (Abschnitt 4)"],
        ["max_connections", pg.get("max_connections", sb.MAX_VERBINDUNGEN),
         "25 Plätze × (Programm, Hintergrund, Sicherung) mit Reserve"],
        ["shared_buffers", pg.get("shared_buffers", ""), "Puffer der Datenbank im Arbeitsspeicher"],
        ["work_mem", pg.get("work_mem", ""), "Arbeitsspeicher je Sortier-/Rechenschritt"],
        ["maintenance_work_mem", pg.get("maintenance_work_mem", ""), "für Wartung und Sicherung"],
        ["ssl", pg.get("ssl", "on"), "nur verschlüsselte Verbindungen"],
        ["ssl_min_protocol_version", pg.get("ssl_min_protocol_version", ""), "ältere TLS-Versionen abgelehnt"],
        ["password_encryption", pg.get("password_encryption", ""), "Passwörter nur als Prüfwert"],
        ["idle_in_transaction_session_timeout", pg.get("idle_in_transaction_session_timeout", ""),
         "hängende Transaktionen werden beendet"],
        ["log_connections / log_disconnections", f"{pg.get('log_connections', 'on')} / "
                                                 f"{pg.get('log_disconnections', 'on')}",
         "An- und Abmeldungen im Protokoll der Datenbank"],
    ], [34, 18, 48])
    i.abschnitt("Betriebssystem")
    i.liste("<b>Windows Server 2019, 2022 oder 2025, 64 Bit</b> (Standard-Edition genügt). Windows 10/11 Pro ist "
            "für kleine Installationen möglich.",
            "Deutsche oder englische Oberfläche, aktuelle Windows-Updates.",
            "Kein Linux: Server, Rechner-Dienst und Sicherung sind das Windows-Programm selbst und laufen über die "
            "Windows-Aufgabenplanung.",
            "Kein .NET, keine Treiber, keine Windows-Dienste und keine Schreibzugriffe auf die Registry durch das "
            "Programm.")
    i.abschnitt("Hypervisor")
    i.liste("Geeignet: <b>Hyper-V, VMware ESXi/vSphere, Proxmox VE</b>.",
            "Arbeitsspeicher <b>fest zuteilen</b> (kein dynamischer Arbeitsspeicher, kein Ballooning).",
            "Virtuelle Platten auf SSD-Storage; Thin Provisioning nur mit ausreichend Reserve.",
            "vCPUs nicht überbuchen, wenn andere rechenintensive VMs auf demselben Host laufen.",
            "VM-Snapshots ersetzen <b>nicht</b> die Programmsicherung (Abschnitt 7). Wenn die VM gesichert wird, dann "
            "anwendungskonsistent (VSS) und nicht während der Programmsicherung.")
    i.abschnitt("Software und Lizenz")
    i.liste(f"<b>PostgreSQL {pg_version()} ist im Programmpaket enthalten</b> (Ordner <i>pgsql</i> neben der .exe). "
            "Keine separate Installation, kein eigener PostgreSQL-Dienst, keine Installation mit Adminrechten.",
            "Die Visual-C++-Laufzeitdateien für PostgreSQL liegen ebenfalls im Paket.",
            f"<b>Programm</b>: portable {NAME} in genau der Version der Arbeitsplätze (Stand dieses Handbuchs: "
            f"{VERSION}).",
            "<b>Lizenz</b>: eine Lizenz der Art <i>Server</i> für diesen Rechner. Aktivierung per Lizenzschlüssel ohne "
            "Internet (Aktivierungsanfrage als Datei an Patrick, Aktivierung zurück einspielen). Neue Hardware oder "
            "Windows-Neuinstallation braucht eine neue Aktivierung.")


def kapitel_vorbereitung(i):
    i.kapitel("Vorbereitung durch die IT")
    i.text("Vor der Einrichtung bereitet die IT sechs Dinge vor: Dienstkonto, Laufwerke und Ordner, Netzwerkfreigabe, "
           "Virenscanner-Ausnahmen, Energie- und Update-Verhalten sowie das Sicherungsziel.")
    i.abschnitt("Dienstkonto")
    i.liste(f"Eigenes Konto anlegen, z. B. <i>{DIENSTKONTO}</i> (Domäne) oder ein lokales Konto auf dem Server.",
            "<b>Passwort läuft nicht ab</b>, sonst starten die geplanten Aufgaben danach nicht mehr. Wird es doch "
            "geändert, die Aufgaben neu eintragen (Befehl <i>aufgaben</i>).",
            "Lokale Administratorrechte auf dem Server für die Einrichtung (Aufgabenplanung). Keine "
            "Domain-Admin-Rechte nötig.",
            "Mit diesem Konto wird der Server eingerichtet: ihm gehört danach der Server-Ordner, unter ihm laufen "
            "Server, Rechner-Dienst und Sicherung, auch ohne Anmeldung am Server.")
    i.abschnitt("Laufwerke und Ordner")
    i.tabelle(["Pfad (Beispiel)", "Zweck", "Zugriff"], [
        [PROGRAMM_ORDNER, "Programm (portable ZIP entpackt), darin pgsql", "Dienstkonto lesen, IT ändern"],
        [SERVER_ORDNER, "Server-Ordner (entsteht beim Einrichten)", "nur Dienstkonto und IT-Admins"],
        [SERVER_ORDNER + r"\pg", "PostgreSQL-Daten", "nur Dienstkonto"],
        [SERVER_ORDNER + r"\Ablage", "gemeinsame Dateien (Freigabe, siehe 3.3)", "alle Mitarbeiter lesen/schreiben"],
        [SERVER_ORDNER + "\\" + ss.ORDNER, "tägliche Sicherungen", "nur Dienstkonto und IT-Admins"],
        [SERVER_ORDNER + r"\ca.key", "Schlüssel der eigenen Zertifizierungsstelle", "nur Dienstkonto; verlässt den "
                                                                                     "Server nie"],
    ], [32, 40, 28])
    i.text("Den Server-Ordner und seine Unterordner legt das Programm beim Einrichten selbst an und setzt die Rechte. "
           "Die IT legt nur das Laufwerk an und gibt dem Dienstkonto dort Vollzugriff.")
    i.abschnitt("Netzwerkfreigabe für die Ablage")
    i.liste(f"Nach der Einrichtung (Schritt 5.3) den Ordner <i>{SERVER_ORDNER}\\Ablage</i> freigeben, z. B. als "
            f"<i>{FREIGABE}</i>.",
            f"Freigabe- und NTFS-Rechte: eine Gruppe, z. B. <i>{GRUPPE}</i>, mit Ändern; Dienstkonto Vollzugriff.",
            "SMB 3 verwenden, SMB 1 deaktiviert lassen. Keine Offline-Dateien für diese Freigabe.",
            "Lange Pfade (über 260 Zeichen) kommen vor, z. B. Mails mit langem Betreff. <i>LongPathsEnabled</i> per "
            "Gruppenrichtlinie aktivieren wird empfohlen.")
    i.code(f"""New-SmbShare -Name "Rohrlaser-Ablage" -Path "{SERVER_ORDNER}\\Ablage" `
  -ChangeAccess "FIRMA\\{GRUPPE}" -FullAccess "{DIENSTKONTO}" """)
    i.abschnitt("Virenscanner")
    i.text("Ausnahmen für die Echtzeitprüfung eintragen, sonst bremst oder blockiert der Scanner die Datenbankdateien:")
    i.liste(f"Ordner <i>{PROGRAMM_ORDNER}\\pgsql</i> und <i>{SERVER_ORDNER}\\pg</i>",
            f"Prozesse <i>postgres.exe, pg_ctl.exe, pg_dump.exe, pg_restore.exe</i> aus <i>{PROGRAMM_ORDNER}\\pgsql\\"
            "bin</i>",
            f"Optional <i>{SERVER_ORDNER}\\{ss.ORDNER}</i> (große Dateien, die nach dem Schreiben geprüft werden)")
    i.hinweis("Die Ablage selbst weiter scannen lassen: Dort liegen Mail-Anhänge von Kunden.", warnung=True)
    i.abschnitt("Energie und Windows-Updates")
    i.liste("Energieprofil „Höchstleistung“, Ruhezustand und Standby aus.",
            "Windows-Updates mit Neustart nur im Wartungsfenster, z. B. Sonntag nachts, nicht zwischen 22:30 und "
            "23:30 Uhr (Sicherung).",
            "Nach jedem Neustart starten Server und Rechner-Dienst automatisch über die Aufgabenplanung.")
    i.abschnitt("Sicherungsziel")
    i.text("Ein Ziel außerhalb der VM festlegen (NAS, anderer Host, Bandsicherung), auf das der Ordner "
           f"<i>{ss.ORDNER}</i> und die Ablage täglich kopiert werden. Einzelheiten in Abschnitt 7.")


def kapitel_netzwerk(i):
    i.kapitel("Netzwerk und Sicherheit")
    i.text(f"Der Server ist <b>nur im Firmennetz erreichbar</b>: Datenbank auf TCP {sb.PORT} und Ablage über SMB "
           "(TCP 445). Es gibt keine Portfreigabe ins Internet, keine Cloud und keine Fernwartung von außen.")
    i.abschnitt("Ports und Firewall")
    i.tabelle(["Dienst", "Port", "Richtung", "Erlaubte Quelle / Ziel"], [
        ["PostgreSQL (Datenbank)", f"TCP {sb.PORT} (beim Einrichten mit --port änderbar)", "eingehend",
         "nur Subnetz/VLAN der Arbeitsplätze"],
        ["Ablage (Windows-Freigabe)", "TCP 445", "eingehend", "nur Subnetz/VLAN der Arbeitsplätze"],
        ["Programm-Update online (optional)", "TCP 443", "ausgehend", "github.com, objects.githubusercontent.com, "
         "release-assets.githubusercontent.com; nur wenn Online-Update gewünscht"],
        ["Alles andere", "–", "–", "gesperrt"],
    ], [26, 22, 14, 38])
    i.text("Beispiel für die Windows-Firewall (PowerShell als Administrator, Subnetz anpassen):")
    i.code(f"""New-NetFirewallRule -DisplayName "Rohrlaser PostgreSQL" -Direction Inbound -Protocol TCP `
  -LocalPort {sb.PORT} -RemoteAddress {SUBNETZ} -Action Allow -Profile Domain,Private""")
    i.text("Die Datenbank hört auf alle Netzwerkkarten (listen_addresses = *). Die Firewall-Regel ist deshalb die "
           "eigentliche Einschränkung auf das Firmennetz. Prüfen vom Arbeitsplatz aus:")
    i.code(f"Test-NetConnection {SERVERNAME} -Port {sb.PORT}")
    i.abschnitt("Adresse und Namen")
    i.liste(f"<b>Feste IP-Adresse</b> (statisch oder DHCP-Reservierung) und ein <b>DNS-Eintrag</b>, z. B. "
            f"<i>{SERVERNAME}</i>.",
            "Beide werden beim Einrichten mit <i>--adresse</i> eingetragen und stehen im Zertifikat. Ändern sie sich, "
            "mit dem Befehl <i>zugang</i> eine neue Zugangsdatei schreiben und an allen Arbeitsplätzen einlesen.",
            "Netzwerk zum Server: 1 Gbit/s kabelgebunden. WLAN geht; bricht die Verbindung ab, wird ein geöffnetes "
            f"Angebot nach {sm.FRISCH_S} Sekunden für Kollegen frei.")
    i.abschnitt("Zertifikat und Verschlüsselung")
    i.liste(f"Beim Einrichten erzeugt der Server <b>eine eigene Zertifizierungsstelle und ein Server-Zertifikat, "
            f"{sb.ZERT_JAHRE} Jahre gültig</b>. Kein Kauf, keine Firmen-PKI, keine Verteilung über den "
            "Windows-Zertifikatsspeicher nötig.",
            "Das Zertifikat enthält die Namen und Adressen aus <i>--adresse</i>, dazu immer den eigenen Rechnernamen, "
            "localhost und 127.0.0.1.",
            f"Die Arbeitsplätze bekommen nur das CA-Zertifikat, über die Zugangsdatei <i>{sb.ZUGANG_DATEI}</i>. Der "
            "Schlüssel der Zertifizierungsstelle verlässt den Server-Ordner nie.",
            "Beim ersten Verbinden vergleicht man den <b>Fingerabdruck</b> mit der Anzeige am Server. Ein fremder "
            "Rechner, der sich als Server ausgibt, wird danach abgewiesen.",
            f"Verbindungen nur mit <b>TLS {pg_einstellungen().get('ssl_min_protocol_version', 'TLSv1.2')[4:]} oder "
            "neuer</b>; unverschlüsselte Verbindungen lehnt der Server ab (pg_hba: hostssl, scram-sha-256).",
            "Passwörter liegen am Server nur als Prüfwert (scram-sha-256).")
    i.abschnitt("Rollen und Rechte")
    i.tabelle(["Ebene", "Wer", "Was"], [
        ["Windows", "Dienstkonto", "führt Server, Rechner-Dienst und Sicherung aus; Eigentümer des Server-Ordners"],
        ["Windows", "IT-Admins", "Zugriff auf Server-Ordner und Sicherung"],
        ["Windows", f"Gruppe {GRUPPE}", "nur die Freigabe Ablage"],
        ["Programm", "verwalter", "Mitarbeiter anlegen/sperren, Programmversion des Servers heben, Ablage eintragen"],
        ["Programm", "bearbeiten", "Angebote anlegen und bearbeiten"],
        ["Programm", "lesen", "nur ansehen (z. B. Werkstatt); setzt der Server selbst durch"],
    ], [15, 25, 60])
    i.text(f"In der Datenbank gibt es die Rollen <i>{sb.ROLLE_APP}</i> (Eigentümer der Tabellen, kein Superuser), "
           f"<i>{sb.ROLLE_LESEN}</i> (nur lesen) und <i>{sb.ROLLE_VERWALTER}</i>. Jeder Mitarbeiter hat einen eigenen "
           f"Login <i>{sb.LOGIN_PRAEFIX}&lt;kürzel&gt;</i> mit Passwort (mindestens 8 Zeichen). An- und Abmeldungen, "
           "Übernahmen, Übergaben und Benutzeränderungen stehen im Serverprotokoll.")


def kapitel_einrichtung(i):
    i.kapitel("Einrichtung Schritt für Schritt")
    i.text("Die Einrichtung dauert rund eine Stunde und läuft in der Eingabeaufforderung des Servers, angemeldet als "
           f"Dienstkonto. Alle Befehle beginnen mit <i>{PROGRAMM_ORDNER}\\{EXE} --server</i>; unten steht dafür "
           "kurz <i>%RL%</i>:")
    i.code(f"set RL={PROGRAMM_ORDNER}\\{EXE} --server")
    i.abschnitt("Programm ablegen und Lizenz aktivieren")
    i.text(f"Portable ZIP in genau der Version der Arbeitsplätze nach <i>{PROGRAMM_ORDNER}</i> entpacken. Programm "
           "einmal starten, <i>Hilfe → Lizenz … → Mit Lizenzschlüssel aktivieren</i>, Server-Lizenz aktivieren.")
    i.abschnitt("Server anlegen")
    i.code(f'%RL% einrichten --ordner {SERVER_ORDNER} --admin PB --name "Firmenname" ^\n'
           f"  --adresse {SERVERNAME} {SERVER_IP}")
    i.text("Das Passwort des ersten Administrators wird abgefragt. Es entstehen Datenbank, Zertifikate, Rollen und "
           f"die Zugangsdatei <i>{SERVER_ORDNER}\\{sb.ZUGANG_DATEI}</i>.")
    i.hinweis("<b>Fingerabdruck notieren</b> (wird angezeigt) und in der IT-Dokumentation ablegen. Die Arbeitsplätze "
              "vergleichen ihn beim ersten Verbinden.")
    i.abschnitt("Ablage freigeben und eintragen")
    i.text("Freigabe wie in 3.3 anlegen, dann den Pfad eintragen, unter dem die Arbeitsplätze sie erreichen:")
    i.code(f"%RL% ablage --ordner {SERVER_ORDNER} --pfad {FREIGABE}")
    i.abschnitt("Automatischen Start und Sicherung einrichten")
    i.code(f"%RL% aufgaben --ordner {SERVER_ORDNER} --uhrzeit 22:30")
    i.text("Trägt drei Aufgaben in die Windows-Aufgabenplanung ein: Server beim Hochfahren starten, Rechner-Dienst "
           "beim Hochfahren starten, täglich sichern. Sie laufen unter dem Konto, das den Server eingerichtet hat, "
           "auch ohne Anmeldung; sein Windows-Passwort wird dafür einmal abgefragt. <i>--konto DOMÄNE\\NAME</i> "
           "nimmt ein anderes Konto mit Zugriff auf den Ordner.")
    i.abschnitt("Starten und prüfen")
    i.code(f"%RL% starten --ordner {SERVER_ORDNER}\n%RL% status --ordner {SERVER_ORDNER}")
    i.text("<i>status</i> zeigt, ob der Server läuft, die Programmversion, die Verbindungen und die Benutzer. Danach "
           "den Server einmal neu starten und prüfen, dass er von selbst wieder läuft.")
    i.abschnitt("Mitarbeiter anlegen")
    i.code(f'%RL% benutzer --ordner {SERVER_ORDNER} --kuerzel AB --recht bearbeiten --name "Anna Becker"')
    i.text("Rechte: <i>bearbeiten</i>, <i>lesen</i> (Werkstatt) oder <i>verwalter</i>. <i>--sperren</i> sperrt einen "
           "Zugang. Später geht das auch im Programm unter <i>Einstellungen → Benutzer und Rollen</i> (nur "
           "Administratoren); ein neuer Benutzer braucht dort gleich ein Passwort.")
    i.abschnitt("Daten übernehmen")
    i.text("Siehe Abschnitt 6.2.")
    i.abschnitt("Lasttest")
    i.code(f"%RL% lasttest --ordner {SERVER_ORDNER} --plaetze 25")
    i.text("Lässt 25 Arbeitsplätze gleichzeitig arbeiten (Anlegen, Reservieren, Positionen, Liste, Notizen). "
           "<b>Bestanden</b>: keine Fehler und 95 % der Aktionen unter 1 Sekunde. Probe-Zugänge und Probe-Angebote "
           "werden danach entfernt, Angebotsnummern nicht verbraucht. Im Labor lagen 95 % unter 641 ms.")
    i.abschnitt("Erste Sicherung mit Probe")
    i.code(f"%RL% sichern --ordner {SERVER_ORDNER}")
    i.hinweis("Danach ist der Server betriebsbereit. Die Abnahme-Checkliste steht in Abschnitt 10.")


def kapitel_arbeitsplaetze(i):
    i.kapitel("Arbeitsplätze anbinden und Daten übernehmen")
    i.text("Jeder Arbeitsplatz wird <b>einmal mit der Zugangsdatei verbunden</b>; danach meldet sich jeder "
           "Mitarbeiter mit Kürzel und Passwort an und kann an jedem Arbeitsplatz arbeiten.")
    i.abschnitt("Voraussetzungen am Arbeitsplatz")
    i.liste("Windows 10/11, 64 Bit. Programm in <b>derselben Version wie der Server</b>.",
            f"Netzwerkzugriff auf {SERVERNAME} Port {sb.PORT} und auf die Freigabe der Ablage.",
            "Keine Adminrechte nötig. Die bisherige lokale Datenbank des Arbeitsplatzes bleibt als Rückweg erhalten.")
    i.abschnitt("Daten übernehmen (einmal beim Umstieg)")
    i.liste("Am Haupt-PC ein letztes Mal abgleichen und unter <i>Datei → Daten exportieren …</i> eine Export-Datei "
            "schreiben (oder eine Sicherung .db nehmen).",
            "Die Datei auf den Server kopieren und einspielen (Befehl unten). Alles kommt in einer Transaktion in den "
            "Server und wird danach Tabelle für Tabelle, Zeile für Zeile verglichen. Bei einer Abweichung kommt der "
            "vorherige Stand zurück und das Programm nennt die Tabellen.",
            "Nur wenn auf anderen PCs seit dem letzten Abgleich gearbeitet wurde: dort exportieren und mit "
            "<i>dazunehmen</i> ergänzen.",
            "Zur Kontrolle mit <i>vergleichen</i> prüfen (ändert nichts).", nummeriert=True)
    i.code(f"""%RL% uebernehmen --ordner {SERVER_ORDNER} --datei D:\\Export.zip
%RL% dazunehmen  --ordner {SERVER_ORDNER} --datei D:\\Export_AB.zip --kuerzel AB
%RL% vergleichen --ordner {SERVER_ORDNER} --datei D:\\Export.zip""")
    i.text("Die Export-Datei muss von derselben Programmversion sein wie der Server. Stehen schon Angebote am Server, "
           "geht <i>uebernehmen</i> nur mit <i>--ersetzen</i>; vorher sichert der Server seinen Stand. Kopien der "
           "Angebote von Kollegen werden deren Angebote (Bearbeiter = Kürzel).")
    i.abschnitt("Arbeitsplatz verbinden")
    i.liste(f"Die Datei <i>{sb.ZUGANG_DATEI}</i> an den Arbeitsplatz geben (z. B. über die Ablage). Sie enthält "
            "Adresse, Port und CA-Zertifikat, aber kein Passwort.",
            "Im Programm <i>Datei → Datenbank … → Mit dem Server verbinden …</i>, Zugangsdatei wählen.",
            "<b>Fingerabdruck mit dem notierten Wert vergleichen.</b> Stimmt er nicht, abbrechen.",
            "Mit Kürzel und Passwort anmelden, Programm neu starten.",
            "Erreicht der Arbeitsplatz die Ablage unter einem anderen Pfad (Laufwerksbuchstabe), unter "
            "<i>Einstellungen → Mein Arbeitsplatz am Server</i> eintragen.", nummeriert=True)
    i.text("Ist der Server nicht erreichbar, bietet das Programm <i>Noch einmal</i>, <i>Lokal arbeiten (eigene Daten "
           "dieses PCs)</i> oder <i>Beenden</i>. <i>Zurück zur lokalen Datenbank …</i> stellt die alte Betriebsart "
           "wieder her.")
    i.abschnitt("Was die Mitarbeiter merken")
    i.tabelle(["Thema", "Verhalten"], [
        ["Anmelden", "Kürzel und Passwort beim Start; die Prüfung macht der Server."],
        ["Gleichzeitig öffnen", "Wer ein Angebot zuerst öffnet, bearbeitet es; Kollegen sehen es nur an, mit Name und "
                                "Arbeitsplatz in einer gelben Leiste."],
        ["Absturz, Netz weg", f"Meldet sich ein Arbeitsplatz {sm.FRISCH_S} Sekunden nicht, werden seine Angebote frei."],
        ["Live", f"Änderungen von Kollegen erscheinen innerhalb von Sekunden; Arbeitsplätze melden sich alle "
                 f"{sm.PULS_S} Sekunden."],
        ["Nummern", "Angebots-, AB-, Auftrags- und Rahmenauftragsnummern vergibt der Server, nie doppelt."],
        ["Lange Rechnungen", f"Große STEP-Importe rechnet der Rechner-Dienst; startet er nicht binnen "
                             f"{sr.WARTEN_START_S} Sekunden, rechnet der Arbeitsplatz selbst."],
    ], [22, 78])


def kapitel_sicherung(i):
    i.kapitel("Sicherung, Wiederherstellung und Notfall")
    i.text("Der Server <b>sichert sich täglich selbst</b> (Vorgabe 22:30 Uhr) und prüft jede Sicherung mit einer "
           "Probe-Rücksicherung. Aufgabe der IT ist die zweite Kopie außerhalb der VM und ein regelmäßiger "
           "Wiederherstellungstest.")
    i.abschnitt("Was die Programmsicherung macht")
    i.liste(f"Sicherung mit festem Stand nach <i>{SERVER_ORDNER}\\{ss.ORDNER}</i>: Datenbank (<i>{ss.ENDUNG}</i>), "
            "Zugänge, Prüfwerte.",
            "Gleich danach: Einspielen in eine Probe-Datenbank und Zeile-für-Zeile-Vergleich. Nur dann gilt die "
            "Sicherung als gut.",
            f"Aufbewahrung: die {ss.BEHALTEN} neuesten täglichen Stände (<i>--behalten N</i>). Sicherungen mit "
            "<i>--anlass vor_Update</i> bleiben dauerhaft.",
            f"Ist die letzte Sicherung älter als {ss.WARNEN_H} Stunden, warnt das Programm die Verwalter.")
    i.code(f"%RL% sichern     --ordner {SERVER_ORDNER}\n%RL% sicherungen --ordner {SERVER_ORDNER}")
    i.abschnitt("Was die IT zusätzlich sichert")
    i.tabelle(["Was", "Wann", "Wohin"], [
        [f"{SERVER_ORDNER}\\{ss.ORDNER}", "täglich nach 23:30 Uhr", "NAS / anderer Host / Band"],
        [f"{SERVER_ORDNER}\\Ablage", "täglich, inkrementell", "NAS / anderer Host / Band"],
        [f"Zugangsdatei {sb.ZUGANG_DATEI} und Fingerabdruck", "einmal nach der Einrichtung", "IT-Dokumentation"],
    ], [42, 28, 30])
    i.text("Beispiel mit Robocopy als geplante Aufgabe:")
    i.code(f"robocopy {SERVER_ORDNER}\\{ss.ORDNER} \\\\NAS\\Backup\\Rohrlaser\\{ss.ORDNER} /MIR /R:2 /W:30 ^\n"
           f"  /LOG:{SERVER_ORDNER}\\robocopy.log")
    i.hinweis("Die Kopie vor fremdem Zugriff schützen: sie enthält die Prüfwerte der Passwörter. <b>Den Ordner pg "
              "nicht direkt kopieren</b>, solange der Server läuft; maßgeblich ist die geprüfte Sicherung.",
              warnung=True)
    i.abschnitt("Wiederherstellen")
    i.code(f"%RL% zurueckholen --ordner {SERVER_ORDNER} --datei {SERVER_ORDNER}\\{ss.ORDNER}\\server_….pgdump")
    i.text("Erst wird der jetzige Stand gesichert, dann die Sicherung in eine neue Datenbank eingespielt und geprüft, "
           "erst danach getauscht. Die Arbeitsplätze verbinden sich von selbst neu; die bisherige Datenbank bleibt "
           "bis zum nächsten Zurückholen erhalten.")
    i.abschnitt("Notfall: Server-Rechner defekt")
    i.liste("Neue VM nach Abschnitt 2 bis 4 vorbereiten, möglichst mit gleicher IP und gleichem DNS-Namen.",
            "Programm in derselben Version ablegen und <i>einrichten</i> wie in 5.2.",
            "Letzte Sicherung vom NAS holen und <i>zurueckholen</i> ausführen. Alle Daten und Zugänge mit Passwörtern "
            "kommen zurück; nur der neu angelegte Administrator behält sein neues Passwort.",
            "Ablage vom NAS zurückkopieren, <i>ablage</i> und <i>aufgaben</i> neu eintragen.",
            "Die neue Zugangsdatei an allen Arbeitsplätzen einlesen (neues Zertifikat, neuer Fingerabdruck).",
            nummeriert=True)
    i.text("Während der Server ausfällt, können Mitarbeiter mit <i>Lokal arbeiten</i> auf ihren alten lokalen "
           "Datenstand zugreifen. Diese Änderungen kommen nicht automatisch in den Server zurück.")


def kapitel_betrieb(i):
    i.kapitel("Updates, laufender Betrieb und Überwachung")
    i.text("<b>Alle Arbeitsplätze arbeiten mit derselben Programmversion wie der Server.</b> Ein Arbeitsplatz mit "
           "anderer Version öffnet nur zum Ansehen, bei geändertem Datenbankaufbau gar nicht. Updates laufen deshalb "
           "immer in dieser Reihenfolge:")
    i.abschnitt("Programm-Update")
    i.liste(f"<i>%RL% sichern --ordner {SERVER_ORDNER} --anlass vor_Update</i>",
            "Rechner-Dienst beenden (Aufgabenplanung), Programm am Server-Rechner aktualisieren.",
            "An einem <b>Verwalter-Arbeitsplatz</b> die neue Version starten: das Programm fragt <i>Server "
            "umstellen</i> und hebt die Pflichtversion.",
            "Rechner-Dienst am Server neu starten.",
            "Alle Arbeitsplätze aktualisieren.", nummeriert=True)
    i.text("<b>Woher kommt das Update?</b> Ohne Internet über eine Update-Datei (<i>.rlupdate</i>, z. B. per USB) oder "
           "einen Netzwerkordner im Firmennetz (Update-Center). Jede Datei ist signiert und wird vor dem Einspielen "
           "geprüft (Signatur und SHA-256); ein Rückschritt auf eine ältere Version ist nicht möglich. Online-Update "
           "nur, wenn Port 443 zu GitHub freigegeben ist (Abschnitt 4.1). Gesperrte Lizenzen erfährt ein Rechner nur "
           "bei der Update-Suche.")
    i.abschnitt("Windows-Updates und Neustarts")
    i.liste("Im Wartungsfenster einspielen, nicht während der Sicherung (22:30 bis 23:30 Uhr).",
            "Beim Herunterfahren beendet sich PostgreSQL sauber. Nach dem Neustart starten Server und Rechner-Dienst "
            "automatisch.",
            "Arbeitsplätze verbinden sich selbst neu; Eingaben, die gerade nicht gespeichert werden konnten, werden "
            "gemerkt und nachgespeichert.")
    i.abschnitt("Überwachung")
    i.tabelle(["Was", "Wie", "Schwelle / Hinweis"], [
        ["Server läuft", f"%RL% status oder Port-Check TCP {sb.PORT}", "Alarm, wenn nicht erreichbar"],
        ["Letzte Sicherung", "Programm: Datei → Datenbank … oder %RL% sicherungen",
         f"Warnung ab {ss.WARNEN_H} Stunden"],
        ["Freier Plattenplatz D:", "Monitoring der VM", "Warnung unter 20 %"],
        ["CPU / RAM der VM", "Monitoring der VM", "dauerhaft über 80 %: VM vergrößern"],
        ["Geplante Aufgaben", "Windows-Aufgabenplanung, letztes Ergebnis", "Ergebnis ungleich 0 prüfen"],
        ["Rechner-Dienst", "Programm: Datei → Datenbank … („Rechner bereit“)",
         f"meldet sich alle {sr.LEBENSZEICHEN_S} s; fehlt er, rechnen die Plätze selbst"],
    ], [24, 40, 36])
    i.text("Im Programm zeigt <i>Datei → Datenbank …</i> außerdem die PostgreSQL-Version, die Größe der Datenbank, "
           "die Verbindungen, wartende Sperren, Abfragen über 5 Sekunden und die letzten langsamen Abfragen. Das "
           "Fenster <i>Kollegen am Server</i> zeigt, wer mit welcher Version an welchem Arbeitsplatz angemeldet ist.")
    i.abschnitt("Regelmäßige Aufgaben der IT")
    i.haken("Wöchentlich: Ergebnis der geplanten Aufgaben und der Kopie auf das NAS prüfen",
            "Monatlich: freier Plattenplatz, Windows-Updates",
            "Nach Änderungen an der VM oder neuer Hardware: Lasttest wiederholen",
            "Jährlich: Wiederherstellung auf einer Test-VM üben (Abschnitt 7.4)",
            "Bei Mitarbeiterwechsel: Zugang im Programm sperren")


def kapitel_stoerungen(i):
    i.kapitel("Störungen und Lösungen")
    i.tabelle(["Meldung / Beobachtung", "Ursache", "Was tun"], [
        ["Arbeitsplatz: Server nicht erreichbar", "Server aus, Aufgabe nicht gestartet, Firewall, falsche Adresse",
         f"%RL% status; Aufgabenplanung prüfen; Test-NetConnection {SERVERNAME} -Port {sb.PORT}"],
        ["Fingerabdruck stimmt nicht", "anderer Rechner antwortet oder Server neu eingerichtet",
         "nicht verbinden; Adresse prüfen; bei Neueinrichtung neue Zugangsdatei verteilen"],
        ["Nur ansehen wegen Programmversion", "Arbeitsplatz hat eine andere Version als der Server",
         "Arbeitsplatz auf die Serverversion aktualisieren (8.1)"],
        ["Ablage nicht erreichbar", "Freigabe, NTFS-Rechte oder Pfad",
         "Freigabe im Explorer öffnen; Gruppe prüfen; Pfad unter Mein Arbeitsplatz am Server"],
        ["PostgreSQL startet nicht", "Virenscanner sperrt Dateien, Platte voll, Rechte am Ordner pg",
         "Ausnahmen (3.4) prüfen, Platz schaffen, Dienstkonto Vollzugriff auf den Server-Ordner"],
        [f"Sicherung älter als {ss.WARNEN_H} Stunden", "Aufgabe fehlgeschlagen, Passwort des Dienstkontos geändert",
         "Aufgabenplanung prüfen; bei neuem Passwort %RL% aufgaben erneut; %RL% sichern von Hand"],
        ["Rücksicherungsprobe misslungen", "Sicherungslaufwerk voll oder defekt",
         "Platz prüfen, %RL% sichern wiederholen; bleibt es, Support-Bericht senden"],
        ["Große STEP-Importe langsam", "Rechner-Dienst läuft nicht oder VM zu klein",
         "Rechner-Aufgabe starten; CPU-Last prüfen, ggf. mehr vCPU"],
        ["Angebot bleibt „bearbeitet von …“", "Arbeitsplatz abgestürzt",
         f"nach {sm.FRISCH_S} Sekunden frei; sonst Übernehmen … im Programm"],
        ["Anmeldung abgelehnt", "falsches Passwort oder Zugang gesperrt",
         "Verwalter setzt das Passwort neu oder entsperrt unter Benutzer und Rollen"],
    ], [27, 33, 40])
    i.text("Für alles andere im Programm <i>Hilfe → Support</i> einen Support-Bericht erzeugen und an Patrick senden.")


def kapitel_abnahme(i):
    i.kapitel("Abnahme-Checkliste und Befehlsreferenz")
    i.abschnitt("Abnahme")
    i.haken("VM nach Tabelle 2.1, Windows Server, SSD, feste IP und DNS-Name",
            "Dienstkonto angelegt, Passwort läuft nicht ab",
            "Virenscanner-Ausnahmen eingetragen",
            f"Firewall: {sb.PORT} und 445 nur aus dem Arbeitsplatz-Subnetz, sonst nichts eingehend",
            "Server-Lizenz aktiviert",
            "einrichten ausgeführt, Fingerabdruck in der IT-Dokumentation notiert",
            "Ablage freigegeben und mit ablage eingetragen",
            "aufgaben eingetragen; nach einem Neustart läuft der Server von selbst",
            "Mitarbeiter angelegt, Rechte geprüft",
            "Daten übernommen, vergleichen ohne Abweichung",
            "lasttest bestanden (95 % unter 1 Sekunde)",
            "erste Sicherung mit erfolgreicher Probe, Kopie auf dem NAS vorhanden",
            "ein Arbeitsplatz verbunden, Angebot angelegt, an einem zweiten Arbeitsplatz sichtbar",
            "ein Angebot an zwei Plätzen gleichzeitig geöffnet: der zweite Platz sieht nur ansehen")
    i.abschnitt("Befehlsreferenz")
    i.text(f"Alle Befehle: <i>{EXE} --server &lt;befehl&gt; --ordner {SERVER_ORDNER} …</i>. Die Liste kommt direkt "
           "aus dem Programm.")
    zeilen = [[b.replace("--ordner ORDNER ", "").replace(" --ordner ORDNER", ""), t] for b, t in befehle()]
    i.tabelle(["Befehl", "Wofür"], zeilen, [40, 60])
    i.text("Ausführlich mit Bildern steht alles in der Bedienungsanleitung, Kapitel „Zentraler Server "
           "(Serverversion)“.")


KAPITEL = [kapitel_ueberblick, kapitel_voraussetzungen, kapitel_vorbereitung, kapitel_netzwerk, kapitel_einrichtung,
           kapitel_arbeitsplaetze, kapitel_sicherung, kapitel_betrieb, kapitel_stoerungen, kapitel_abnahme]


def erzeugen(ziel):
    i = Inhalt()
    inhalt = TableOfContents()
    inhalt.levelStyles = [INHALT1, INHALT2]
    vorne = [Spacer(1, 80 * mm), Paragraph(
        "Dieses Handbuch beschreibt alle Voraussetzungen und Schritte, um den zentralen Server der "
        f"{NAME} im Firmennetz einzurichten und zu betreiben. Es richtet sich an die IT im Unternehmen. "
        "Namen, Adressen und Pfade (z. B. " + SERVERNAME + ", " + SERVER_IP + ", " + SERVER_ORDNER
        + ") sind Beispiele und werden durch die eigenen ersetzt.", TEXT),
        Spacer(1, 4), Paragraph("Alle technischen Werte in diesem Handbuch stammen direkt aus der Programmversion "
                                f"{VERSION}. Mit jeder neuen Version entsteht das Handbuch neu.", KLEIN),
        PageBreak(), Paragraph("Inhalt", H1), inhalt]
    from reportlab.platypus.doctemplate import NextPageTemplate
    vorne.insert(0, NextPageTemplate("normal"))
    for k in KAPITEL:
        k(i)
    doc = Handbuch(ziel)
    doc.multiBuild(vorne + [PageBreak()] + i.teile)
    return Path(ziel)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--ziel", default=str(HIER / "IT-Handbuch_Server.pdf"))
    a = p.parse_args(argv)
    ziel = erzeugen(a.ziel)
    print(f"{ziel} geschrieben ({ziel.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
