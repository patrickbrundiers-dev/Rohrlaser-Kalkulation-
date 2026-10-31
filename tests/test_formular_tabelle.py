"""PDF-Anfrageformular besser auswerten (Patrick 31.10.2026: „Anfragenummer, Stückzahlen, Werkstoff“, Freigabe „Alle
Empfehlungen“): Tabelle über die Lage der Textstücke (PDF mit Text und Scan), Anfrage-Nr. aus Kopftabellen und
weiteren Bezeichnungen (nie ein Datum), Stückzahlen mit Tausenderpunkt, Menge eine Zeile tiefer, Positionsnummer und
Längen nie als Menge, Artikel-Nr. als Teil des STEP-Namens (F2 a, gelb), Werkstoff je Position (F1 a, gelb mit
Quelle). Die Formulare sind erfunden und werden hier mit reportlab erzeugt (typische ERP-Layouts).

Aufruf: python tests/test_formular_tabelle.py
"""
import os
import sys
import tempfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from rohrlaser import formular, ocr, pdf_art  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402


def ok(text):
    print("OK    ", text)


tmp = Path(tempfile.mkdtemp())
WS = Datenbank(tmp / "x.db").zeilen("werkstoffe")


def formular_pdf(name, kopf, zeilen, spalten, unten=(), schrift=10):
    """PDF mit Kopfzeilen (Text, x, y) und einer Tabelle: spalten [(Titel, x)], zeilen [[Zellen]] (eine Zelle mit
    „\\n“ = zweizeilig)."""
    pfad = tmp / name
    c = canvas.Canvas(str(pfad), pagesize=A4)
    c.setFont("Helvetica", schrift)
    for t, x, y in kopf:
        c.drawString(x, y, t)
    y = 640
    for titel, x in spalten:
        c.drawString(x, y, titel)
    y -= 20
    for z in zeilen:
        hoehe = 1
        for zelle, (_, x) in zip(z, spalten):
            for k, teil in enumerate(str(zelle).split("\n")):
                c.drawString(x, y - k * 13, teil)
                hoehe = max(hoehe, k + 1)
        y -= 13 * hoehe + 6
    for k, t in enumerate(unten):
        c.drawString(50, y - 20 - k * 14, t)
    c.save()
    return pfad


SPALTEN = [("Pos.", 50), ("Artikel-Nr.", 90), ("Bezeichnung", 190), ("Werkstoff", 330), ("Menge", 420), ("ME", 480)]
KOPF = [("Stahlbau Neumann GmbH · Industriestr. 5 · 44135 Dortmund", 50, 800), ("Bestellanfrage", 50, 760),
        ("Anfrage-Nr.", 50, 730), ("Datum", 200, 730), ("Kunden-Nr.", 330, 730),
        ("AN-2026-0815", 50, 715), ("28.10.2026", 200, 715), ("10023", 330, 715)]
ZEILEN = [["10", "MG-01", "Stiel 40x40x3\nL = 1250 mm", "S235JRH", "1.000", "ST"],
          ["20", "MG-02", "Riegel", "1.4301", "8,000", "ST"],
          ["30", "4711-07", "Lasche", "", "25", "Stk"]]
NAMEN = ["MG-01.stp", "MG-02.stp", "4711-07 Lasche gebogen.step"]

d = formular.datei_lesen(formular_pdf("erp.pdf", KOPF, ZEILEN, SPALTEN, ["Mit freundlichen Grüßen"]))
tab = d["tabelle"]
assert [z.get("artikel") for z in tab] == ["MG-01", "MG-02", "4711-07"], tab
assert tab[0]["bezeichnung"] == "Stiel 40x40x3 L = 1250 mm" and tab[0]["werkstoff"] == "S235JRH", tab[0]
assert tab[1]["menge"] == "8,000" and tab[2]["me"] == "Stk", tab
ok("Tabelle über die Lage: Spalten aus der Kopfzeile, zweizeilige Zelle zusammengefügt, Ende am Gruß")

assert formular.nummer_aus([d]) == "AN-2026-0815"
assert formular.anfragenummer("Anfrage-Nr.   Datum   Kunden-Nr.\nA-4711   28.10.2026   10023") == "A-4711"
assert formular.anfragenummer("Beleg-Nr.: 2026-0815") == "2026-0815"
assert formular.anfragenummer("Vorgangsnummer 88123") == "88123"
assert formular.anfragenummer("Unser Zeichen: AN-332") == "AN-332"
assert formular.anfragenummer("Anfrage vom 28.10.2026") is None
assert formular.anfragenummer("Anfrage: 28.10.2026") is None
ok("Anfrage-Nr.: Wert unter der Beschriftung (Lage und Text), Beleg-Nr., Vorgang, Unser Zeichen; nie ein Datum")

st = formular.stueck_aus([d], NAMEN)
assert st == {"MG-01.stp": (1000, True), "MG-02.stp": (8, True), "4711-07 Lasche gebogen.step": (25, False)}, st
assert formular.stueckzahlen("10 MG-01 Stiel 1.000 Stk", ["MG-01.stp"]) == {"MG-01.stp": (1000, True)}
assert formular.stueckzahlen("Pos Artikel Bezeichnung\n10 MG-01\nStiel 40x40x3\n20,000 ST", ["MG-01.stp"]) == \
    {"MG-01.stp": (20, False)}
assert formular.stueckzahlen("MG-01 Rohr 40x40x3 1250 20", ["MG-01.stp"]) == {"MG-01.stp": (20, False)}
assert formular.stueckzahlen("MG-01 Rohr L=1250 mm 20", ["MG-01.stp"]) == {"MG-01.stp": (20, False)}
assert formular.stueckzahlen("10 MG-01 Stiel 20 Stk", ["MG-01.stp"]) == {"MG-01.stp": (20, True)}
ok("Stückzahlen: 1.000 Stk = 1000, 8,000 = 8, Menge eine Zeile tiefer, Pos.-Nr. und Längen nie; Artikel-Nr. als Teil "
   "des STEP-Namens nur unsicher (gelb)")

ws = formular.werkstoff_je_teil([d], NAMEN, WS)
assert {n: w[0] for n, w in ws.items()} == {"MG-02.stp": "1.4301"}, ws     # S235JRH: zwei Normen -> offen
assert ws["MG-02.stp"][1] == "Anfrageformular erp.pdf Pos. 20", ws
assert "4711-07 Lasche gebogen.step" not in ws
ok("Werkstoff je Position aus der Werkstoffspalte (nur eindeutig), Quelle mit Datei und Pos.")

# im Ablauf: Messwerte bekommen Stückzahl und Werkstoff (gelb), Blech nie einen Werkstoff
messwerte = [dict(datei="MG-01.stp", artikel="MG-01"), dict(datei="MG-02.stp", artikel="MG-02"),
             dict(datei="4711-07 Lasche gebogen.step", artikel="4711-07 Lasche gebogen")]
erg = pdf_art.anwenden(messwerte, [d], None, WS)
assert [m["_stueck"] for m in messwerte] == [1000, 8, 25], messwerte
assert [m["_stueck_formular"] for m in messwerte] == [True, True, False]
assert messwerte[1]["_werkstoff"] == "1.4301" and "Pos. 20" in messwerte[1]["_werkstoff_quelle"]
assert erg["werkstoff"] >= 1 and "_werkstoff" not in messwerte[2], (erg, messwerte[2])
pdf_art.anwenden(messwerte, [d], None, None)            # Umschalten: Werkstoff aus dem Formular wieder weg
assert "_werkstoff" not in messwerte[1]
ok("Ablauf (pdf_art.anwenden): Stückzahl und Werkstoff je Teil gesetzt, beim Umschalten zurückgenommen")

# Tabelle ohne Werkstoffspalte, Werkstoff in der Bezeichnung; Positionen über zwei Zeilen
d2 = formular.datei_lesen(formular_pdf("ohne_ws.pdf", [("Angebotsanfrage", 50, 760), ("Vorgang", 50, 730),
                                                       ("V-7781", 120, 730)],
                                       [["1", "RR-100", "Rohr 60x40x3\nS355J2H", "12"], ["2", "RR-101", "Rohr 1.4301",
                                                                                         "4"]],
                                       [("Pos", 50), ("Teile-Nr.", 90), ("Beschreibung", 190), ("Anzahl", 420)]))
assert formular.nummer_aus([d2]) == "V-7781", formular.nummer_aus([d2])
assert formular.stueck_aus([d2], ["RR-100.stp", "RR-101.stp"]) == {"RR-100.stp": (12, True), "RR-101.stp": (4, True)}
w2 = formular.werkstoff_je_teil([d2], ["RR-100.stp", "RR-101.stp"], WS)
assert w2["RR-101.stp"][0] == "1.4301", w2
ok("Tabelle ohne Werkstoffspalte: Werkstoff aus der Bezeichnung, Anfrage-Nr. rechts neben „Vorgang“")

if ocr.programm() is None:
    assert not os.environ.get("CI"), "tesseract fehlt im CI"
    print("HINWEIS Tesseract nicht installiert: Scan-Teil übersprungen")
else:
    import pypdfium2 as pdfium
    seite = pdfium.PdfDocument(str(tmp / "erp.pdf"))[0]
    seite.render(scale=200 / 72).to_pil().convert("L").save(tmp / "scan.png")
    s = formular.datei_lesen(tmp / "scan.png")
    st = formular.stueck_aus([s], NAMEN)
    assert st.get("MG-01.stp", (0,))[0] == 1000 and st.get("MG-02.stp", (0,))[0] == 8, (st, s.get("tabelle"))
    assert formular.nummer_aus([s]) == "AN-2026-0815", formular.nummer_aus([s])
    ok("Scan: Tabelle und Anfrage-Nr. über die Wortlage aus Tesseract")
print("Alle Tests bestanden.")
