"""Konturen aus einer PDF-Zeichnung aus dem CAD (Plan W7 Stufe 2, Patrick 26.10.2026: Testfunktion, Einstellung
pdf_zeichnung): Patricks DXF-Zeichnungen werden im Test als PDF gezeichnet, wie ein CAD es druckt (sichtbare Kanten
0,7 mm, verdeckte gestrichelt, Mittellinien Strich-Punkt, Maße schmal, Maßzahlen als Text, Bögen als Bézierkurven).
- V1 pdf_vektor.dxf_text + dxf_rohr.erkennen ergibt dasselbe wie die DXF selbst: Profil, Länge, Enden, Konturen.
- V2 auch mit breit gezeichnetem Rahmen; Kreise aus vier Bögen werden CIRCLE; gleiche Strichstärke überall; ein
  PDF nur mit Text (Stufe 1) oder ein Scan hat keine Linien (None).
- V3 Oberfläche: „Aus PDF-Zeichnung“ nimmt die Linien (Enden und Konturen im Rohr-Editor), Stückzahl aus dem Text.

Aufruf: python tests/test_pdf_vektor.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import math
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

app = QApplication.instance() or QApplication([])
from rohrlaser import dxf_import as di, dxf_rohr, pdf_vektor  # noqa: E402

MM = 72 / 25.4
tmp = Path(tempfile.mkdtemp())


def ok(text):
    print("OK    ", text)


def als_pdf(dxf, pdf, rahmen_breit=False, alle_gleich=False, stueck=None):
    """DXF als PDF zeichnen wie ein CAD-Druck (1:1 in mm)."""
    roh = di.roh_lesen(di.datei_lesen(dxf))
    roh["entitaeten"] = di._polylinien_zusammen(roh["entitaeten"])
    els = di.elemente(roh)
    pk = [p for el in els for p in ([el[2]] + ([el[3]] if el[0] == "S" else []))]
    x0, y0 = min(p[0] for p in pk) - 10, min(p[1] for p in pk) - 10
    x1, y1 = max(p[0] for p in pk) + 10, max(p[1] for p in pk) + 10
    c = canvas.Canvas(str(pdf), pagesize=((x1 - x0) * MM, (y1 - y0) * MM))
    c.translate(-x0 * MM, -y0 * MM)
    c.scale(MM, MM)
    for el in els:
        layer = el[1]
        if el[0] == "T":
            _, layer, p, h, w, t, _s = el
            c.saveState()
            c.translate(*p)
            c.rotate(w or 0)
            c.setFont("Helvetica", h / 0.72)
            c.drawString(0, 0, t.replace("%%c", "Ø").replace("%%C", "Ø"))
            c.restoreState()
            continue
        mass = di._hat(layer, dxf_rohr.MASS_WORTE)
        mittel = di._hat(layer, dxf_rohr.MITTEL_WORTE)
        verdeckt = di._hat(layer, dxf_rohr.VERDECKT_WORTE) or (el[-1] and not mittel and not mass)
        sicht = di.layer_art(layer) == "schnitt" and not el[-1]
        c.setDash([])
        if mittel:
            c.setLineWidth(0.25)
            c.setDash([12, 3, 2, 3])
        elif verdeckt:
            c.setLineWidth(0.35)
            c.setDash([3, 1.5])
        elif sicht or (rahmen_breit and "RAHMEN" in layer.upper()):
            c.setLineWidth(0.7)
        else:
            c.setLineWidth(0.25)
        if alle_gleich:
            c.setLineWidth(0.5)
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
    if stueck:
        c.setFont("Helvetica", 3.5 / 0.72)
        c.drawString(x0 + 15, y0 + 15, f"Stückzahl: {stueck}")
    c.save()
    return pdf


DXF = ["rohr_ansichten_QR40", "rohr_bauteil1_patrick", "rohr_gehrung_QR40_patrick"]


def gleich(name, pdf):
    d = dxf_rohr.erkennen(di.datei_lesen(HIER / "dxf" / f"{name}.dxf"), name)
    e = dxf_rohr.erkennen(pdf_vektor.dxf_text(pdf), name)
    assert e["ok"] and (e["profil"], e["laenge"]) == (d["profil"], d["laenge"]), (name, e["profil"], e["laenge"])
    assert e["eingaben"] == d["eingaben"], (name, e["eingaben"], d["eingaben"])
    return e


# ------------------------------------------------------------------ V1 dasselbe wie die DXF
for n in DXF:
    gleich(n, als_pdf(HIER / "dxf" / f"{n}.dxf", tmp / f"{n}.pdf"))
e = gleich(DXF[2], tmp / f"{DXF[2]}.pdf")
assert e["profil"] == dict(form="Quadratrohr", a=40, b=40, wand=3) and e["laenge"] == 1018.8
assert (e["eingaben"]["a"]["winkel"], e["eingaben"]["b"]["winkel"]) == (20, 30)
assert [k["art"] for k in e["eingaben"]["konturen"]] == ["Bohrung", "Ausklinkung"]
ok("V1 drei Zeichnungen von Patrick als PDF: Profil, Länge, Enden und Konturen wie aus der DXF")

# ------------------------------------------------------------------ V2 Varianten
for n in DXF:
    gleich(n, als_pdf(HIER / "dxf" / f"{n}.dxf", tmp / f"{n}_rahmen.pdf", rahmen_breit=True))
li = pdf_vektor.lesen(tmp / f"{DXF[2]}.pdf")
assert len(li["kreise"]) == 1 and abs(li["kreise"][0][1] - 1.0) < 0.01 and li["kreise"][0][2] == "sicht"
assert not li["gleich_breit"] and {a for *_x, a in li["strecken"]} == {"sicht", "verdeckt", "mittel", "mass"}
assert any(t == "Ø10" for _p, _h, _w, t in li["texte"]) and any(t == "1.018,8" for _p, _h, _w, t in li["texte"])
assert any(abs(w - 90) < 1 and t == "40" for _p, _h, w, t in li["texte"])
li = pdf_vektor.lesen(als_pdf(HIER / "dxf" / f"{DXF[2]}.dxf", tmp / "gleich.pdf", alle_gleich=True))
assert li["gleich_breit"] and "mass" not in {a for *_x, a in li["strecken"]}
c = canvas.Canvas(str(tmp / "text.pdf"))
c.drawString(50, 800, "Rechteckrohr 60x40x3   L = 1250")
c.line(50, 790, 300, 790)
c.save()
assert pdf_vektor.dxf_text(tmp / "text.pdf") is None
ok("V2 breiter Rahmen, Kreis aus Bögen, Texte mit Drehung, gleiche Strichstärke, PDF ohne Zeichnung -> None")

# ------------------------------------------------------------------ V3 Oberfläche
from rohrlaser import schneidweg as sw  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402

db = Datenbank(tmp / "rohrlaser.db")
a = db.angebot_neu(dict(kunde="Test", maschine="T03"))
fenster = Hauptfenster(db, stumm=True)
s = fenster.angebot_oeffnen(a)
gesehen = {}


def rohr_ok(d):
    gesehen.update(profil=d.k_profil.currentText(), laenge=d.k_laenge.value(), info=d.step_info.text())
    return QDialog.Accepted


pdf = als_pdf(HIER / "dxf" / f"{DXF[2]}.dxf", tmp / "Gehrung.pdf", stueck=12)
assert s.rohr_aus_pdf([str(pdf)], dialog=rohr_ok, zuordnung=lambda d: QDialog.Accepted) == 1
assert gesehen["profil"] == "QR 40x40x3" and abs(gesehen["laenge"] - 1018.8) < 0.05, gesehen
assert "PDF-Zeichnung (Linien)" in gesehen["info"], gesehen["info"]
pos = db.positionen(a)
t = sw.lesen(pos[0]["technik"])
assert len(pos) == 1 and pos[0]["stueck"] == 12, pos[0]["stueck"]
assert [k["art"] for k in t["konturen"]] == ["Bohrung", "Ausklinkung"] and t["a"]["winkel"] == 20, t
ok("V3 Oberfläche: Rohr-Editor mit Enden und Konturen aus den Linien, 12 Stück aus dem Text")
print("Alle Tests PDF-Linien bestanden.")
