"""Layout-Prüfung der PDF-Ausgaben (Patrick 28.10.2026: Dokumente auf Überlappungen und abgeschnittenen Text prüfen).

Ein Angebot mit langen Texten (Briefkopf, Kundenname, Anfrage, Artikelnummern, Umlaute), Staffeln und Satz erzeugt
Angebot, Werkstattpapiere, Kalkulation, Nachkalkulation, Palettenschein und Verladeliste. Geprüft wird jede Seite:
kein Zeichen überdeckt ein anderes, kein Zeichen ragt aus dem Blatt. Dazu die Bausteine einzeln: Fußzeile (bis drei
Zeilen, nie unter 'Seite x von y'), Breite der Kopfangaben, Umbruch zu langer Zellen, Kürzen im Palettenschein.

Aufruf: python tests/test_pdf_layout.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pypdfium2 as pdfium  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: E402
from reportlab.platypus import Paragraph  # noqa: E402

import beispiel_angebot  # noqa: E402
from rohrlaser import palettenschein, pdf  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster, logo_aus_datei  # noqa: E402


def ok(text):
    print("OK    ", text)


def fehler_im_layout(pfad, rand=3):
    """[(Seite, Art, Text)]: Zeichen, die sich überdecken, und Zeichen außerhalb des Blatts."""
    out = []
    d = pdfium.PdfDocument(str(pfad))
    for nr in range(len(d)):
        seite = d[nr]
        b, h = seite.get_size()
        tp = seite.get_textpage()
        zeichen = []
        for i in range(tp.count_chars()):
            c = tp.get_text_range(i, 1)
            if not c.strip():
                continue
            x0, y0, x1, y1 = tp.get_charbox(i)
            if x1 - x0 < 0.3 or y1 - y0 < 0.3:
                continue
            zeichen.append((x0, y0, x1, y1, c))
            if x0 < rand or x1 > b - rand or y0 < rand or y1 > h - rand:
                out.append((nr + 1, "außerhalb", c))
        zeichen.sort()
        for i, a in enumerate(zeichen):
            for z in zeichen[i + 1:]:
                if z[0] >= a[2]:
                    break
                dx = min(a[2], z[2]) - max(a[0], z[0])
                dy = min(a[3], z[3]) - max(a[1], z[1])
                if dx > 0.35 * min(a[2] - a[0], z[2] - z[0]) and dy > 0.4 * min(a[3] - a[1], z[3] - z[1]):
                    out.append((nr + 1, "überlappt", a[4] + z[4]))
    d.close()
    return out


# ------------------------------------------------------------------ L1 Bausteine
platz = 210 * mm - 24 * mm - stringWidth("Seite 1 von 2", pdf.SCHRIFT, 7.5) - 5 * mm
firma = ["Müller & Söhne Präzisions-Rohrlaserbearbeitung GmbH & Co. KG", "Industriestraße 123–125",
         "12345 Großkleinhausen-Überörtlich", "Tel. +49 (0) 1234 / 56789-0", "info@mueller-soehne-rohrlaser.de",
         "USt-IdNr. DE123456789", "HRB 12345 Amtsgericht Großkleinhausen",
         "Geschäftsführer: Dr. Hans-Jürgen Müller-Lüdenscheidt"]
fuss = " · ".join(firma) + "   |   Angebot A-2026-04711"
g, zeilen = pdf.fuss_zeilen(fuss, platz)
assert len(zeilen) == 3 and g >= 5.5, (g, zeilen)
assert all(stringWidth(z, pdf.SCHRIFT, g) <= platz for z in zeilen), (g, zeilen)
assert " ".join(zeilen).count("A-2026-04711") == 1 and "…" not in " ".join(zeilen)
g, zeilen = pdf.fuss_zeilen(" · ".join(firma * 4), platz)
assert len(zeilen) == 3 and all(stringWidth(z, pdf.SCHRIFT, g) <= platz for z in zeilen) and zeilen[-1].endswith("…")
g, zeilen = pdf.fuss_zeilen("X" * 400, platz)           # ohne Trenner: eine gekürzte Zeile
assert len(zeilen) == 1 and stringWidth(zeilen[0], pdf.SCHRIFT, g) <= platz
ok("L1 Fußzeile: langer Briefkopf in drei Zeilen neben 'Seite x von y', notfalls mit '…' gekürzt")

kunde = "Großhandelsgesellschaft für Stahl- und Metallbauerzeugnisse Süd-Westfalen mbH & Co. KG"
breiten = pdf.angaben_breiten(["A-2026-04711", kunde, "T11", "28.10.2026 17:50"], 186 * mm)
assert abs(sum(breiten) - 186 * mm) < 1 and breiten[1] == max(breiten) and breiten[1] > 90 * mm, breiten
assert pdf.angaben_breiten(["A-1", "Kunde", "T11", "28.10.2026"], 186 * mm) == [186 * mm / 4] * 4
assert pdf.angaben_breiten(["A-1", "B", "C"], 273 * mm) == [55 * mm] * 3
ok("L2 Kopfangaben: langer Kundenname bekommt den freien Platz der kurzen Angaben")

tab = pdf._tabelle([pdf._kopfzeile(["A", "B"]), ["kurz", "60 (Programmierung) und noch mehr Text"]], [20 * mm, 20 * mm],
                   rechts=(1,))
zellen = tab._cellvalues[1]
assert zellen[0] == "kurz" and isinstance(zellen[1], Paragraph) and zellen[1].style.alignment == 2
ok("L3 Tabellen: Text breiter als die Spalte wird umbrochen (rechtsbündig bleibt rechtsbündig)")

t = pdf._kuerzen("Befestigungswinkelhalterungsrohrverbindungsstück", pdf.SCHRIFT, 7, 30 * mm)
assert t.endswith("…") and stringWidth(t, pdf.SCHRIFT, 7) <= 30 * mm and pdf._kuerzen("kurz", pdf.SCHRIFT, 7, 30 * mm) == "kurz"
ok("L4 Kürzen: zu langer Text endet mit '…' und passt in die Breite")

# ------------------------------------------------------------------ L5 alle PDFs eines langen Angebots
app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
db = Datenbank(tmp / "rohrlaser.db")
bild = QImage(1200, 400, QImage.Format_ARGB32)
bild.fill(0xFF1F4E78)
bild.save(str(tmp / "logo.png"))
db.einstellung_setzen("logo", logo_aus_datei(tmp / "logo.png"))
db.einstellung_setzen("briefkopf_1", firma[0])
db.einstellung_setzen("briefkopf_2", f"{firma[1]} · {firma[2]}")
db.einstellung_setzen("briefkopf_3", f"{firma[3]} · {firma[4]}")
db.einstellung_setzen("briefkopf_4", " · ".join(firma[5:]))
db.con.execute("INSERT INTO kunden (kundennr, name, strasse, plz_ort, ansprechpartner) VALUES (?,?,?,?,?)",
               ("K-99999", kunde, "Am Überlandkanal 1234 / Gebäude Ä, Tor 7", "98765 Bad Königshofen im Grabfeld",
                "Frau Dr. Änne-Sophie Weißenböck-Schütz"))
db.con.commit()
a = beispiel_angebot.anlegen(db, dict(nummer="A-2026-04711", kundennr="K-99999", kunde=kunde,
                                      kundenreferenz="Anfrage Nr. 2026/ÄÖÜ-123456789 vom 12.10.2026, Projekt "
                                                     "Hallenerweiterung Nord-Ost"))
bez = ["Befestigungswinkelhalterungsrohrverbindungsstück", "Querstrebe für Geländer mit Überlänge und Ausklinkung",
       "Pfosten Ø 42,4 äußere Ecke links/rechts gespiegelt"]
for i in range(9):
    db.position_neu(a, dict(pos=100 + 10 * i, artikel=f"ART-{2026000 + i}-ÄÖÜ-REV{i % 3}-LANGE-NUMMER" if i % 2 == 0
                            else f"47-{i:03d}", bezeichnung=bez[i % 3],
                            profil_id=("RR 42,4x2,0", "QR 40x40x3", "RE 60x40x3")[i % 3],
                            werkstoff_id=("S235-10219", "S355-10219")[i % 2], laenge=350.0 + 397.3 * i,
                            stueck=5 + (i * 7) % 30, schneidweg=300 + i, einstiche=2 + i % 4,
                            gewinde="4xM8" if i % 3 == 0 else None))
fenster = Hauptfenster(db, tmp, stumm=True)
s = fenster.angebot_oeffnen(a)
assert s.optimieren()
s.staffelpreise_rechnen()
pfade = {"Angebot": s.angebot_pdf(), "Werkstattpapiere": s.werkstatt_pdf(), "Kalkulation": s.kalkulation_pdf(),
         "Nachkalkulation": s.nachkalk.pdf()}
z = palettenschein.zusammenstellen(db, a)
seiten = palettenschein.seiten(z["kopf"], z["schein"], z["packliste"], z["gruppen"])
for x in seiten:
    x.update(bestellnummer="BEST-2026-0001234567-ÄÖÜ-PROJEKT-HALLENERWEITERUNG-NORD-OST",
             hinweis="Achtung: Teile vor Feuchtigkeit schützen, nicht stapeln!\nAnlieferung nur Mo–Fr an Tor 7.")
pfade["Palettenschein"] = tmp / "palettenschein.pdf"
pdf.palettenschein_pdf(pfade["Palettenschein"], seiten, db.einstellungen())
pfade["Verladeliste"] = tmp / "verladeliste.pdf"
pdf.verladeliste_pdf(pfade["Verladeliste"], [dict(auftrag="A-2026-04711", kunde=kunde, bestellnummer="BEST-2026-"
                                                 "0001234567-ÄÖÜ", lieferdatum="2026-11-03", paletten=3, stueck=1234,
                                                 gewicht=2345.6, stand="Teilweise gepackt, Rest folgt")],
                     db.einstellungen())
for name, pfad in pfade.items():
    assert pfad and Path(pfad).exists(), name
    f = fehler_im_layout(pfad)
    assert not f, (name, f[:10])
ok(f"L5 {len(pfade)} PDFs mit langen Texten ({', '.join(pfade)}): keine Überlappung, nichts außerhalb des Blatts")
fenster.close()
db.schliessen()
print("PDF-Layout: alle Tests bestanden.")
