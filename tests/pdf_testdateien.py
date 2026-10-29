"""Test-PDFs für die Einordnung Zeichnung/Formular (tests/test_pdf_art.py): Anfrageformulare wie aus einem ERP oder
Word, Zeichnungen wie ein CAD sie druckt (Patricks DXF-Zeichnungen aus tests/dxf, Linien und Maßzahlen, dazu ein
Schriftfeld), Blechzeichnungen nur mit Kontur und Maßen, gemischte PDFs und Scans. Es gibt keine echten Anfragen;
Firmen und Personen sind erfunden."""
import math
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
from rohrlaser import dxf_import as di, dxf_rohr  # noqa: E402

MM = 72 / 25.4
FORMULAR = ["Metallbau Krüger GmbH · Hafenstraße 3 · 28195 Bremen", "An: Muster Rohrlaser GmbH", "",
            "Angebotsanfrage", "Anfrage-Nr.: AN-2026-0815          Datum: 25.10.2026", "",
            "Sehr geehrte Damen und Herren,", "bitte bieten Sie uns folgende Teile an. Liefertermin KW 50.", "",
            "Pos  Artikel-Nr.        Bezeichnung          Menge",
            "10   MG-01              Stiel                20 Stk", "20   MG 02              Riegel lang          8",
            "30   T01_RR42-4x2_L1250   Rundrohr   25 Stück", "", "Mit freundlichen Grüßen", "Max Muster, Einkauf"]


def _formular(c, zeilen):
    c.setPageSize(A4)
    y = 800
    for z in zeilen:
        c.drawString(50, y, z)
        y -= 16
    c.showPage()


def _dxf(c, dxf, schriftfeld=None):
    roh = di.roh_lesen(di.datei_lesen(dxf))
    roh["entitaeten"] = di._polylinien_zusammen(roh["entitaeten"])
    els = di.elemente(roh)
    pk = [p for el in els for p in ([el[2]] + ([el[3]] if el[0] == "S" else []))]
    x0, y0 = min(p[0] for p in pk) - 10, min(p[1] for p in pk) - 10
    x1, y1 = max(p[0] for p in pk) + 10, max(p[1] for p in pk) + 10
    c.setPageSize(((x1 - x0) * MM, (y1 - y0) * MM))
    c.saveState()
    c.translate(-x0 * MM, -y0 * MM)
    c.scale(MM, MM)
    for el in els:
        if el[0] == "T":
            _, layer, p, h, w, t, _s = el
            c.saveState()
            c.translate(*p)
            c.rotate(w or 0)
            c.setFont("Helvetica", h / 0.72)
            c.drawString(0, 0, t.replace("%%c", "Ø").replace("%%C", "Ø"))
            c.restoreState()
            continue
        c.setLineWidth(0.7 if di.layer_art(el[1]) == "schnitt" else 0.25)
        c.setDash([3, 1.5] if di._hat(el[1], dxf_rohr.VERDECKT_WORTE) else [])
        if el[0] == "K":
            c.circle(el[2][0], el[2][1], el[3], stroke=1, fill=0)
            continue
        p, q, b = el[2], el[3], el[4]
        path = c.beginPath()
        if b:
            m, r = di._bogen_mitte(p, q, b)
            path.arc(m[0] - r, m[1] - r, m[0] + r, m[1] + r, math.degrees(math.atan2(p[1] - m[1], p[0] - m[0])),
                     math.degrees(4 * math.atan(b)))
        else:
            path.moveTo(*p)
            path.lineTo(*q)
        c.drawPath(path, stroke=1, fill=0)
    if schriftfeld:
        c.setFont("Helvetica", 3.5 / 0.72)
        for i, z in enumerate(schriftfeld):
            c.drawString(x0 + 5, y1 - 8 - 5 * i, z)
    c.restoreState()
    c.showPage()


def _blech(c, schriftfeld):
    """Blechzeichnung (Querformat A4): Kontur mit Ausschnitt und Bohrungen, Bemaßung, Schriftfeld."""
    c.setPageSize(landscape(A4))
    c.setLineWidth(1.2)
    c.rect(100, 150, 400, 250)
    c.rect(180, 220, 120, 80)
    for x in (130, 470):
        for y in (180, 370):
            c.circle(x, y, 8)
    c.setLineWidth(0.3)
    c.setFont("Helvetica", 9)
    for x, y, t in ((300, 410, "400"), (510, 275, "250"), (240, 310, "120"), (305, 255, "80"), (140, 190, "Ø16"),
                    (480, 190, "Ø16"), (120, 410, "30"), (470, 410, "30"), (90, 175, "30"), (90, 370, "30"),
                    (200, 140, "80"), (260, 140, "120")):
        c.line(x - 20, y - 4, x + 20, y - 4)
        c.drawString(x - 8, y, t)
    c.rect(520, 30, 300, 90)
    for i, z in enumerate(schriftfeld):
        c.drawString(530, 105 - 13 * i, z)
    c.showPage()


def pdf(pfad, seiten):
    """PDF mit Seiten [('formular', Zeilen) | ('zeichnung', DXF-Pfad, Schriftfeldzeilen) | ('blech', Zeilen)]."""
    c = canvas.Canvas(str(pfad))
    for s in seiten:
        if s[0] == "formular":
            _formular(c, s[1])
        elif s[0] == "zeichnung":
            _dxf(c, s[1], s[2] if len(s) > 2 else None)
        else:
            _blech(c, s[1])
    c.save()
    return pfad


def scan(pfad_pdf, ziel, seite=0, dpi=200):
    """Eine Seite als Scan (Graustufen, leicht schief) als PNG bzw. Bild-PDF."""
    import pypdfium2 as pdfium
    p = pdfium.PdfDocument(str(pfad_pdf))
    bild = p[seite].render(scale=dpi / 72).to_pil().convert("L").rotate(0.8, expand=True, fillcolor=255)
    p.close()
    bild.save(ziel, resolution=dpi) if ziel.suffix == ".pdf" else bild.save(ziel)
    return ziel


SCHRIFTFELD_ROHR = ["Benennung: Stiel", "Zeichnungs-Nr.: ST-77", "Werkstoff: 1.4301", "Stückzahl: 12",
                    "Maßstab 1:1   Blatt 1 von 1", "Gezeichnet: PB   Geprüft: MM", "Allgemeintoleranz ISO 2768-m"]
SCHRIFTFELD_BLECH = ["Benennung: Deckel", "Zeichnungs-Nr.: BL-200", "Werkstoff: 1.4571", "Stückzahl: 4",
                     "Maßstab 1:5   Blatt 1 von 1", "Gezeichnet: PB   Geprüft: MM", "Allgemeintoleranz ISO 2768-m"]
