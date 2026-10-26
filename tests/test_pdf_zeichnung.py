"""PDF-Zeichnung eines Rohrteils -> Position im Rohr-Editor (Plan W7 Stufe 1, Patrick 26.10.2026: Testfunktion,
Einstellung pdf_zeichnung):
- Z1 Schriftfeld nach DIN EN ISO 7200 (Beschriftung klein, Wert darunter): Profil aus Halbzeug, Werkstoff, Benennung,
  Zeichnungsnummer, Stückzahl; Länge als größte Maßzahl außerhalb des Schriftfelds (mit Hinweis).
- Z2 Text auf dem Blatt: „Rechteckrohr 60x40x3 L = 1250“, Beschriftung links und Wert rechts, „Ø 42,4 x 2 - 600 lg“,
  ohne Profil kein Rohr, Profil ohne Kurzwort im Feld Halbzeug, vierter Wert am Profil = Länge.
- Z3 Scan (300 dpi, Tesseract): dasselbe wie Z1, auch mit einem falsch gelesenen Buchstaben in der Beschriftung.
- Z4 Oberfläche: Neue Position „Aus PDF-Zeichnung“ nur mit der Einstellung; Rohr-Editor vorbelegt, Position angelegt.
- Z5 (Patricks Scan 26.10.2026: englisches Schriftfeld, Profil nur als Maße am Schnitt): Title/DWG No./Quantity,
  Benennung als größte Schrift im Schriftfeld, 50×30 aus waagrechter und senkrechter Maßzahl am Schnitt, Wandstärke
  aus den passenden Profilen der Stammdaten gewählt (eines ohne Frage, sonst Auswahl, keins: das ähnlichste).

Aufruf: python tests/test_pdf_zeichnung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from reportlab.lib.pagesizes import A4, landscape  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import ocr, pdf_zeichnung as pz  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())


def zeichnung(pfad, felder, blatt=(), schrift=6):
    """A4 quer mit Rohr (Rechteck), Maßzahlen blatt [(x, y, Text)] und Schriftfeld rechts unten (Beschriftung klein,
    Wert darunter)."""
    c = canvas.Canvas(str(pfad), pagesize=landscape(A4))
    c.rect(150, 300, 500, 40)
    c.line(150, 360, 650, 360)
    c.setFont("Helvetica", 10)
    for x, y, t in blatt:
        c.drawString(x, y, t)
    x0, y0 = 500, 20
    c.rect(x0, y0, 320, 100)
    for i, (lab, wert) in enumerate(felder):
        x, y = x0 + 4 + (i % 2) * 160, y0 + 70 - (i // 2) * 32
        c.setFont("Helvetica", schrift)
        c.drawString(x, y + 18, lab)
        c.setFont("Helvetica", 10)
        c.drawString(x, y + 4, wert)
    c.save()
    return pfad


FELDER = [("Benennung", "Stiel links"), ("Zeichnungsnummer", "MG-4711-01"), ("Werkstoff", "S235JRH"),
          ("Halbzeug", "QR 40x40x3 EN 10219"), ("Maßstab", "1:5"), ("Stückzahl", "20")]
BLATT = [(380, 365, "860"), (660, 315, "40"), (60, 200, "Datum 25.10.2026")]

# ------------------------------------------------------------------ Z1 Schriftfeld
z1 = zeichnung(tmp / "Stiel.pdf", FELDER, BLATT)
e = pz.erkennen(z1)
assert e["ok"] and e["profil"] == dict(form="Quadratrohr", a=40, b=40, wand=3), e
assert (e["laenge"], e["artikel"], e["name"], e["werkstoff_text"], e["stueck"]) == \
    (860, "MG-4711-01", "Stiel links", "S235JRH", 20), e
assert any("größte Maßzahl" in w for w in e["warnungen"]) and not e["ocr"]
assert e["eingaben"]["konturen"] == [] and e["eingaben"]["a"] == {} and e["eingaben"]["pdf"] == "Stiel.pdf"
# eine Jahreszahl im Schriftfeld ist keine Länge
z1b = zeichnung(tmp / "jahr.pdf", FELDER + [("Datum", "2026")], [(380, 365, "860")])
assert pz.erkennen(z1b)["laenge"] == 860
ok("Z1 Schriftfeld: QR 40x40x3, S235JRH, Stiel links, MG-4711-01, 20 Stück, Länge 860 (größte Maßzahl, Hinweis)")

# ------------------------------------------------------------------ Z2 Text
c = canvas.Canvas(str(tmp / "re.pdf"))
c.drawString(50, 800, "Rechteckrohr 60x40x3   L = 1250")
c.drawString(50, 760, "Material:")
c.drawString(140, 760, "1.4301")
c.drawString(50, 740, "Artikel-Nr.")
c.drawString(140, 740, "A-77")
c.save()
e = pz.erkennen(tmp / "re.pdf")
assert e["profil"] == dict(form="Rechteckrohr", a=60, b=40, wand=3) and e["laenge"] == 1250, e
assert (e["werkstoff_text"], e["artikel"], e["stueck"]) == ("1.4301", "A-77", None), e
assert not any("größte" in w for w in e["warnungen"])
c = canvas.Canvas(str(tmp / "rund.pdf"))
c.drawString(50, 800, "Ø 42,4 x 2 - 600 lg")
c.save()
e = pz.erkennen(tmp / "rund.pdf")
assert e["profil"] == dict(form="Rundrohr", a=42.4, b=42.4, wand=2) and e["laenge"] == 600, e
assert e["artikel"] == "rund" and any("Dateinamen" in h for h in e["hinweise"])
c = canvas.Canvas(str(tmp / "blech.pdf"))
c.drawString(50, 800, "Blech 3 mm, 200 x 100")
c.save()
e = pz.erkennen(tmp / "blech.pdf")
assert not e["ok"] and "Kein Rohrprofil" in e["warnungen"][0]
assert pz._profil("40x40x3") == (dict(form="Quadratrohr", a=40, b=40, wand=3), None)
assert pz._profil("QR 40x40x3x1500") == (dict(form="Quadratrohr", a=40, b=40, wand=3), 1500)
assert pz._profil("RE 80 x 40 x 4") == (dict(form="Rechteckrohr", a=80, b=40, wand=4), None)
assert pz._profil("Maßstab 1:5") == (None, None) and pz._profil("200 x 100") == (None, None)
assert pz._label("Materialnummer 4711", pz.FELDER["werkstoff"]) is None
assert pz._label("Zerchnungsnummer", pz.FELDER["artikel"], ocr=True) == ""
assert pz._label("Zerchnungsnummer", pz.FELDER["artikel"]) is None
ok("Z2 Text: Rechteckrohr mit L =, Feld rechts daneben, Ø … lg, kein Rohr bei Blech, Profil ohne Kurzwort, "
   "vierter Wert = Länge")

# ------------------------------------------------------------------ Z3 Scan
if ocr.programm() is None:
    assert not os.environ.get("CI"), "tesseract fehlt im CI (paket.yml: tesseract-ocr tesseract-ocr-deu)"
    print("HINWEIS Tesseract nicht installiert: Scan-Teil übersprungen")
else:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(zeichnung(tmp / "scan.pdf", FELDER, BLATT, schrift=7)))
    bild = pdf[0].render(scale=300 / 72).to_pil().convert("L").rotate(0.5, expand=True, fillcolor=255)
    pdf.close()
    bild.save(tmp / "Scan Stiel.png")
    e = pz.erkennen(tmp / "Scan Stiel.png")
    assert e["ok"] and e["ocr"] and e["profil"] == dict(form="Quadratrohr", a=40, b=40, wand=3), e
    assert (e["laenge"], e["artikel"], e["stueck"]) == (860, "MG-4711-01", 20), e
    assert e["werkstoff_text"] == "S235JRH" and e["name"] == "Stiel links", e
    assert any("Scan" in w for w in e["warnungen"])
    ok("Z3 Scan 300 dpi: dieselben Werte wie das PDF, Hinweis Texterkennung")

# ------------------------------------------------------------------ Z4 Oberfläche
from rohrlaser import neue_position, schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

db = Datenbank(tmp / "rohrlaser.db")
assert db.einstellung("pdf_zeichnung") == "nein"
from PySide6.QtWidgets import QPushButton  # noqa: E402

assert neue_position.PDF not in [b.text() for b in neue_position.TypDialog().findChildren(QPushButton)]
assert neue_position.PDF in [b.text() for b in neue_position.TypDialog(pdf=True).findChildren(QPushButton)]
a = db.angebot_neu(dict(kunde="Test", maschine="T03"))
fenster = Hauptfenster(db, stumm=True)
s = fenster.angebot_oeffnen(a)
gesehen = {}


def rohr_ok(d):
    gesehen.update(profil=d.k_profil.currentText(), laenge=d.k_laenge.value(), bez=d.k_bezeichnung.text(),
                   artikel=d.k_artikel.text(), wst=d.k_werkstoff.currentText(), info=d.step_info.text())
    return QDialog.Accepted


assert s.rohr_aus_pdf([str(z1)], dialog=rohr_ok, zuordnung=lambda d: QDialog.Rejected) == 1
assert gesehen["profil"] == "QR 40x40x3" and gesehen["laenge"] == 860, gesehen
assert (gesehen["bez"], gesehen["artikel"]) == ("Stiel links", "MG-4711-01") and gesehen["wst"].startswith("S235")
assert "Aus PDF-Zeichnung" in gesehen["info"], gesehen["info"]
pos = db.positionen(a)
assert len(pos) == 1 and pos[0]["profil_id"] == "QR 40x40x3" and pos[0]["laenge"] == 860 and pos[0]["stueck"] == 20
assert sw.lesen(pos[0]["technik"])["konturen"] == []
assert s.rohr_aus_pdf([str(tmp / "blech.pdf")], dialog=rohr_ok, zuordnung=lambda d: QDialog.Rejected) == 0 and len(db.positionen(a)) == 1
ok("Z4 Oberfläche: Typ nur mit Einstellung, Rohr-Editor mit Profil, Länge, Benennung, Artikel, Werkstoff und Bericht; "
   "Position mit 20 Stück; ohne Rohr keine Position")

# ------------------------------------------------------------------ Z5 englisch, Profil aus dem Schnitt
def schnitt_pdf(pfad, felder, titel_gross=None):
    c = canvas.Canvas(str(pfad), pagesize=landscape(A4))
    c.rect(100, 380, 50, 30)                                    # Schnitt 50 x 30 (1:1 in pt, egal)
    c.setFont("Helvetica", 10)
    c.drawString(118, 418, "50")
    c.saveState()
    c.translate(92, 388)
    c.rotate(90)
    c.drawString(0, 0, "30")
    c.restoreState()
    c.rect(250, 380, 400, 30)                                   # Ansicht mit Bohrungsmaßen
    for x, t in ((280, "40"), (340, "50"), (420, "180")):
        c.drawString(x, 360, t)
    x0, y0 = 500, 20
    c.rect(x0, y0, 320, 100)
    for i, (lab, wert) in enumerate(felder):
        x, y = x0 + 4 + (i % 2) * 160, y0 + 70 - (i // 2) * 32
        c.setFont("Helvetica", 6)
        c.drawString(x, y + 18, lab)
        c.setFont("Helvetica", 10)
        c.drawString(x, y + 4, wert)
    if titel_gross:
        c.setFont("Helvetica", 16)
        c.drawString(x0 + 4, y0 + 40, titel_gross)
    c.save()
    return pfad


e = pz.erkennen(schnitt_pdf(tmp / "en.pdf", [("Title", "Bracket left"), ("DWG No.", "DW-1001"),
                                             ("Material", "S355J2H"), ("Quantity", "8")]))
assert e["ok"] and e["profil"] == dict(form="Rechteckrohr", a=50, b=30, wand=None), e
assert (e["name"], e["artikel"], e["werkstoff_text"], e["stueck"]) == ("Bracket left", "DW-1001", "S355J2H", 8), e
assert e["laenge"] == 180 and any("Maßen am Schnitt" in w for w in e["warnungen"]), e
e = pz.erkennen(schnitt_pdf(tmp / "titel.pdf", [("Created by", "19.10.2024"), ("Document type", "")],
                            titel_gross="Visualisierung bemaßung"))
assert e["name"] == "Visualisierung bemaßung" and e["profil"]["a"] == 50, e
assert pz._durchmesser_als_8("815", dict(a=50)) and not pz._durchmesser_als_8("860", dict(a=40))
ok("Z5 englisches Schriftfeld, Benennung als größte Schrift, Profil 50×30 aus den Maßen am Schnitt ohne Wand")

ein = dict(form="Rechteckrohr", a=50.0, b=30.0, wand=None)
s.k.profile.update({"RE 50x30x2": dict(form="Rechteckrohr", a=50, b=30, wand=2),
                    "RE 50x30x3": dict(form="Rechteckrohr", a=50, b=30, wand=3)})
gefragt = []
erg = dict(profil=dict(ein), warnungen=[])
assert s._wand_waehlen(erg, "x.pdf", wand=lambda liste: gefragt.append(liste) or liste[1])
assert gefragt == [["RE 50x30x2", "RE 50x30x3"]] and erg["profil"]["wand"] == 3
erg = dict(profil=dict(ein), warnungen=[])
assert not s._wand_waehlen(erg, "x.pdf", wand=lambda liste: None)           # Abbruch
del s.k.profile["RE 50x30x3"]
erg = dict(profil=dict(ein), warnungen=[])
assert s._wand_waehlen(erg, "x.pdf", wand=lambda liste: 1 / 0) and erg["profil"]["wand"] == 2   # eines: ohne Frage
del s.k.profile["RE 50x30x2"]
erg = dict(profil=dict(ein), warnungen=[])
assert s._wand_waehlen(erg, "x.pdf") and erg["profil"]["form"] == "Rechteckrohr" and "ähnlichste" in erg["warnungen"][0]
n0 = len(db.positionen(a))
assert s.rohr_aus_pdf([str(tmp / "en.pdf")], dialog=rohr_ok, zuordnung=lambda d: QDialog.Rejected) == 1 and len(db.positionen(a)) == n0 + 1
assert db.positionen(a)[-1]["stueck"] == 8 and gesehen["artikel"] == "DW-1001"
ok("Z5 Wandstärke: Auswahl bei zwei Profilen, Abbruch, eines ohne Frage, sonst das ähnlichste; Position mit 8 Stück")
print("Alle Tests PDF-Zeichnung bestanden.")
