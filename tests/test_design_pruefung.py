"""Design-Prüfung 25.10.2026 (D1–D4): Fußzeile der PDFs kollidiert nicht mit 'Seite x von y', Spalte Lage der
Werkstattpapiere mittig, Übersicht rechts wird nicht abgeschnitten, Angebots-Check meldet Staffelpreise, die dem
Angebotspreis widersprechen.

Aufruf: python tests/test_design_pruefung.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: E402

from rohrlaser import angebot_check as ac, ausgabe, pdf  # noqa: E402
from rohrlaser.angebot_oben import UebersichtRahmen  # noqa: E402


def ok(text):
    print("OK    ", text)


# ------------------------------------------------------------------ D1 Fußzeile
platz = 210 * mm - 24 * mm - stringWidth("Seite 1 von 2", pdf.SCHRIFT, 7.5) - 5 * mm
kurz = "Muster GmbH   |   Angebot A-1"
assert pdf.fuss_zeilen(kurz, platz) == (7.5, [kurz])
lang = ("Muster Rohrlaser GmbH · Industriestraße 12 · 12345 Musterstadt · Tel. 01234 5678-0 · "
        "info@muster-rohrlaser.example   |   Angebot A-2026-0041")
g, zeilen = pdf.fuss_zeilen(lang, platz)
assert all(stringWidth(z, pdf.SCHRIFT, g) <= platz for z in zeilen), (g, zeilen)
assert g >= 6.5 and " ".join(zeilen).replace("  ", " ").count("A-2026-0041") == 1
sehr_lang = " · ".join(["Muster Rohrlaser GmbH Niederlassung Süd"] * 6) + "   |   Angebot A-2026-0041"
g, zeilen = pdf.fuss_zeilen(sehr_lang, platz)
assert len(zeilen) == 2 and zeilen[1].endswith("A-2026-0041"), zeilen
ok("D1 Fußzeile: kurz unverändert, lang kleiner oder zweizeilig, nie unter 'Seite x von y'")

# ------------------------------------------------------------------ D4 Staffel widerspricht Angebotspreis
def satz(preis, menge, stufen):
    return dict(zeilen=[dict(art="satz", text="Satz MG 2000", menge=menge, preis=preis,
                             staffeln=[dict(menge=m, bereich=f"ab {m}", preis=p) for m, p in stufen])])


w = ausgabe.staffel_widersprueche(satz(528.85, 2, [(1, 768.62), (2, 567.64), (5, 475.59)]))
assert len(w) == 1 and "528,85" in w[0] and "567,64" in w[0] and "„ab 2“" in w[0], w
assert ausgabe.staffel_widersprueche(satz(567.64, 2, [(1, 768.62), (2, 567.64), (5, 475.59)])) == []
assert ausgabe.staffel_widersprueche(satz(500.0, 2, [(1, 768.62), (5, 475.59)])) == []      # kleinere Menge teurer: normal
w = ausgabe.staffel_widersprueche(satz(500.0, 2, [(5, 520.0)]))
assert len(w) == 1 and "mehr" in w[0], w
assert ausgabe.staffel_widersprueche(satz(500.0, 2, [(2, 500.004)])) == []                  # Rundung zählt nicht
punkte = ac.punkte(dict(kunde="K", lieferzeit_art="nur Text", kundenreferenz="x"), [dict(pos=10, stueck=1)], ["OK"],
                   "aktuell", {}, staffel_widersprueche=["Satz MG 2000: 2 Satz …"])
p = [p for p in punkte if p.ziel == "staffeln" and p.art == ac.WARNUNG]
assert p and "widerspricht" in p[0].text, punkte
ok("D4 Staffelpreis gegen Angebotspreis: Widerspruch und teurere größere Menge als WARNUNG im Angebots-Check")

# ------------------------------------------------------------------ D3 Übersicht nicht abgeschnitten
app = QApplication.instance() or QApplication([])
inhalt = QWidget()
lay = QVBoxLayout(inhalt)
lab = QLabel("kurz")
lay.addWidget(lab)
rahmen = UebersichtRahmen(inhalt, 320)
rahmen.resize(320, 300)
rahmen.show()
app.processEvents()
assert rahmen.minimumWidth() == 320
lab.setText("+ Gewinn (10 % auf Selbstkosten 932,69 €)   " * 3)
for _ in range(5):
    app.processEvents()
assert rahmen.minimumWidth() > 320 and rahmen.minimumWidth() <= UebersichtRahmen.HOECHSTENS, rahmen.minimumWidth()
assert rahmen.minimumWidth() >= min(UebersichtRahmen.HOECHSTENS, lab.minimumSizeHint().width())
lab.setText("kurz")
for _ in range(5):
    app.processEvents()
assert rahmen.minimumWidth() == 320
ok("D3 Übersicht: Mindestbreite folgt dem Inhalt (höchstens 560 px), wird wieder schmal")

# ------------------------------------------------------------------ D2 Werkstattpapiere
quelle = (HIER.parent / "programm" / "rohrlaser" / "pdf.py").read_text(encoding="utf-8")
assert 'daten[0][7] = _p("Lage", ParagraphStyle("kl", parent=S_KOPF, alignment=1))' in quelle
ok("D2 Werkstattpapiere: Kopf 'Lage' mittig, Spalte breiter")
print("Alle Tests bestanden.")
