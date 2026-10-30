"""Kalkulations-PDF überarbeitet (Patrick 30.10.2026, „Kalkulations PDF überarbeiten … Werte die fehlen oder überflüssig
sind“, Freigabe „Alle Empfehlungen umsetzten“).

Ein Angebot mit Schweißbaugruppe, Zukaufteilen, Edelstahl mit Gewinde, Musterteil, zweiter Profilform, ermitteltem
Stundensatz, Schneidgas, Ausschuss, Schrotterlös, gestaffeltem Gewinn, Fracht und Staffeln:
- F1 Kostenarten stehen auf Seite 1 (nicht leer), F2 keine Zahl in der Positionstabelle umgebrochen, Tabellen in der
  Breite, F3 keine Baugruppe in der Schneidzeit.
- U1 Kasten „Rüsten und Mengen“ ersetzt durch „Kennzahlen“, U2 Schritte ohne Zeit unter eigenem Strich.
- M1–M10 Kopf (Datum, Kunden-Nr., Stundensatz), Kachel Selbstkosten, Stundensatz-Rechenweg, Gewinnstufe, Fracht,
  Abruf-Abschnitt, Staffeln, Schneiddaten je Teil, Zukaufteile, Warnungen der Preis-Gegenprobe.
- Die Rechnung ändert sich nicht (Preis wie ohne PDF).

Aufruf: python tests/test_kalkulation_pdf.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
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
from PySide6.QtWidgets import QApplication  # noqa: E402

import beispiel_baugruppe as bsp  # noqa: E402
from rohrlaser import pdf, rechnen  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
from rohrlaser.stammdaten import ABRUF_LAGER  # noqa: E402


def ok(text):
    print("OK    ", text)


def seiten_text(pfad):
    """[(Text der Seite, Zeichen außerhalb des Blatts)] je Seite."""
    out = []
    d = pdfium.PdfDocument(str(pfad))
    for i in range(len(d)):
        s = d[i]
        b, _ = s.get_size()
        tp = s.get_textpage()
        aussen = 0
        for j in range(tp.count_chars()):
            if tp.get_text_range(j, 1).strip():
                x0, _, x1, _ = tp.get_charbox(j)
                aussen += x0 < 3 or x1 > b - 3
        out.append((" ".join(tp.get_text_range().split()), aussen))
    d.close()
    return out


STUFEN = dict(gewinn_bis_1=500, gewinn_satz_1=0.30, gewinn_bis_2=2000, gewinn_satz_2=0.20, gewinn_bis_3=10000,
              gewinn_satz_3=0.12, gewinn_satz_4=0.08)
PLAN = dict(anschaffung=650000, nutzungsdauer=10, flaeche=60, instandhaltung=3, wartung=8000, leistung_kw=30,
            verschleiss=4, bediener_anteil=50, schicht_stunden=15)
app = QApplication.instance() or QApplication([])


def angebot(kopf=None, ein=None):
    tmp = Path(tempfile.mkdtemp())
    db = Datenbank(tmp / "r.db")
    for n, w in dict(dict(STUFEN, gaspreis_n2=0.9, ausschuss=0.02, schrott_anteil=0.10), **(ein or {})).items():
        db.einstellung_setzen(n, w)
    for x in db.zeilen("schneiddaten"):
        if x.get("gas") == "N₂":
            db.aendern("schneiddaten", x["id"], "duese", 2.0)
            db.aendern("schneiddaten", x["id"], "gasdruck", 15.0)
    for x in db.zeilen("maschinen"):
        for n, w in dict(PLAN, zeit_teil=4.0, gas_o2=3.0, ruest_form=20, satz_art="ermittelt").items():
            db.aendern("maschinen", x["id"], n, w)
    a = bsp.anlegen(db)
    for n, w in dict(dict(fracht=60, fracht_modus="manuell", skonto=2), **(kopf or {})).items():
        db.angebot_aendern(a, n, w)
    for p in (dict(pos=200, artikel="VA-1", bezeichnung="Halter Edelstahl", profil_id="RR 42,4x2,0",
                   werkstoff_id="1.4301", laenge=720, stueck=40, schneidweg=290, einstiche=2, gewinde="2xM8"),
              dict(pos=210, artikel="VA-2", bezeichnung="Muster", profil_id="RR 42,4x2,0", werkstoff_id="1.4301",
                   laenge=380, stueck=6, schneidweg=310, einstiche=4, muster="ja"),
              dict(pos=220, artikel="ST-3", bezeichnung="Stütze", profil_id="RE 60x40x3", werkstoff_id="S355-10219",
                   laenge=1795.5, stueck=16, schneidweg=618.2, einstiche=4)):
        db.position_neu(a, p)
    s = Hauptfenster(db, tmp, stumm=True).angebot_oeffnen(a)
    assert s.optimieren()
    return s, tmp


# ------------------------------------------------------------------ alles in einem Angebot
s, tmp = angebot()
s.staffelpreise_rechnen()
verkauf = s._rechnung()[1]["verkauf"]
ziel = tmp / "kalk.pdf"
s._ziel = lambda *a: ziel
assert s.kalkulation_pdf()
assert abs(s._rechnung()[1]["verkauf"] - verkauf) < 1e-9, "das PDF ändert keine Rechnung"
seiten = seiten_text(ziel)
text = " ".join(t for t, _ in seiten)
eins = seiten[0][0]
assert "Kostenart" in eins and "Herstellkosten" in eins and "Kennzahlen" in eins, eins[:600]
assert all(a == 0 for _, a in seiten), [a for _, a in seiten]
ok("F1 Kostenarten und Kennzahlen auf Seite 1; F2 nichts ragt aus dem Blatt")
assert "Rüsten und Mengen" not in text
for wort in ("Stundensatz Maschine", "Zeitbasis", "Verkaufspreis je kg Rohr", "Ertrag je Maschinenstunde",
             "ohne Zeit (Festpreis, Fremdleistung, Gas)"):
    assert wort in text, wort
ok("U1 Kennzahlen statt „Rüsten und Mengen“, U2 Schritte ohne Zeit unter eigenem Strich")
for wort in ("Kunden-Nr.", "97,60 €/h ermittelt", "Selbstkosten", "Stundensatz Maschine: Rechenweg", "Abschreibung",
             "Stufe bis 2.000 € = 20,0 %", "von Hand eingetragen", "m³ aus Düse und Gasdruck",
             "Staffelpreise je Mengenstufe", "Zukaufteile", "Schraube M8x25", "Kategorie Edelstahl",
             "Musterteil, auf die Serie umgelegt", "Halter Edelstahl", "Kalkulation je Position: Preisaufbau"):
    assert wort in text, wort
assert "Rahmenbedingungen" not in text and "Abrufe je Jahr" not in text
ok("M1–M9: Kopf, Selbstkosten, Rechenweg, Gewinnstufe, Fracht, Gas, Staffeln, Zukaufteile, Schneiddaten, Muster")
schneid = text[text.index("Schneidzeit je Teil"):]
assert "R1" not in schneid.split("Schneiddaten =")[0], "F3: Baugruppe nicht in der Schneidzeit"
ok("F3 Schweißbaugruppe steht nicht in „Schneidzeit je Teil“")

# F2: jede Spalte der Positionstabellen mindestens so breit wie ihre längste Zahl
zeilen, summen = s._rechnung()
liste = pdf._zeilen_kalk(zeilen, s.positionen, summen)
for spalten in (pdf.KALK_KOSTEN, pdf.KALK_PREIS, pdf.SCHNEID):
    tab = pdf._spalten_tabelle(spalten, liste, 273 * pdf.mm)
    assert sum(tab._colWidths) <= 273 * pdf.mm + 0.5, sum(tab._colWidths) / pdf.mm
    groesse = tab._cellStyles[1][0].fontsize
    for r in tab._cellvalues[1:]:
        for c, w in zip(r, tab._colWidths):
            if isinstance(c, str) and c:
                assert pdf.stringWidth(c, pdf.FETT, groesse) <= w - 5, (c, w)
ok("F2 Positionstabellen in zwei Teilen, keine Zahl umgebrochen, in der Breite")

# M10 Warnung der Preis-Gegenprobe oben
p2 = tmp / "warnung.pdf"
pdf.kalkulation_pdf(p2, s.kopf, zeilen, summen, s.einst,
                    plausi=[("WARNUNG", "Preis unter den Materialkosten (z. B. Pos. 10)", 1)])
assert "WARNUNG: Preis unter den Materialkosten" in seiten_text(p2)[0][0]
ok("M10 Warnungen der Preis-Gegenprobe stehen auf Seite 1")

# ------------------------------------------------------------------ Abruf, Stundensatz von Hand, fester Gewinn
s, tmp = angebot(dict(abruf="ja", abruf_jahr_von=4000, abruf_jahr_bis=6000, abruf_von=400, abruf_bis=600,
                      abruf_laufzeit=12, abruf_material=ABRUF_LAGER, abruf_lagerzins=8.0),
                 dict(gewinn_bis_1=0))
for x in s.db.zeilen("maschinen"):
    s.db.aendern("maschinen", x["id"], "satz_art", None)
ziel = tmp / "abruf.pdf"
s._ziel = lambda *a: ziel
assert s.kalkulation_pdf()
text = " ".join(t for t, _ in seiten_text(ziel))
for wort in ("Abruf-/Rahmenangebot", "Abrufe je Jahr", "Jahresbedarf bevorratet", "Lagerzins 8,0 % p. a.",
             "je Abruf"):
    assert wort in text, wort
assert "Stufe bis" not in text
ok("M6 Abschnitt Abruf-/Rahmenangebot mit Jahresmenge, Abrufen, Lagerzins und Einmalkosten je Abruf")

assert rechnen.KOSTENARTEN and pdf.kennzahlen(s.kopf, s._rechnung()[1], s.einst)
print("OK: Kalkulations-PDF")
