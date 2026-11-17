"""Zeichnungen und Anfrageformulare besser erkennen und auslesen (Patrick 17.11.2026: „Werkstoffe Stückzahl Gewinde
Senkungen etc“, Empfehlungen F1-F4 a):
- Zeichnungstext: Senkung für eine Schraube („2x Senkung DIN 74 M6“) ist kein Gewinde, „beidseitig“ verdoppelt,
  „angesenkt“ = Gewinde + Senkung, Zollgewinde und Gewinde ohne Größe nur als Hinweis.
- Formular-Tabelle: Spalte Bemerkung/Bearbeitung, Gewinde und Senkungen je Zeile am passenden Teil (F2 a), Staffel
  „50/100/250“ = erste Menge, unsicher, mit Hinweis (F3 a), Liefertermin beendet die Tabelle.
- Zeichnung weicht vom Formular ab: Formular gilt, Zeichnungswert als „abweichend“ (F4 a).
- Word (.docx) und LibreOffice (.odt) als Anfrageformular (F1 a), alte .doc nur mit Hinweis.
- Stückliste auf einer Baugruppen-Zeichnung: Werkstoff und Bearbeitung je Teil, Menge nur „je Baugruppe“.
Alle Formulare und Zeichnungen sind erfunden und werden hier erzeugt.

Aufruf: python tests/test_zeichnung_formular_auslesen.py   (QT_QPA_PLATFORM=offscreen)
"""
import os
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from reportlab.lib.pagesizes import A3, A4, landscape  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from rohrlaser import formular, formular_office, pdf_art  # noqa: E402
from rohrlaser import zeichnung_hinweise as zh  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402

MM = 72 / 25.4
tmp = Path(tempfile.mkdtemp())
WS = Datenbank(tmp / "x.db").zeilen("werkstoffe")


def ok(text):
    print("OK    ", text)


def kurz(text):
    return [(h["art"], h["gewinde"], h["anzahl"]) for h in zh.lesen(text)]


# ------------------------------------------------------------------ 1. Zeichnungstext
FAELLE = {
    "2x Senkung DIN 74-A M6": [("Senkung", "M6", 2)],
    "4x Zylindersenkung DIN 974 für M8": [("Senkung", "M8", 4)],
    "4x M6 gesenkt": [("Senkung", "M6", 4)],
    "3x Kegelsenkung 90° Ø12,4": [("Senkung", None, 3)],
    "4x M8 durchgehend": [("Gewinde", "M8", 4)],
    "Gewinde M10 beidseitig": [("Gewinde", "M10", 2)],
    "2x M8 beidseitig angesenkt": [("Gewinde", "M8", 4), ("Senkung", None, 4)],
    "Gewinde M8 mit Senkung": [("Gewinde", "M8", None), ("Senkung", None, None)],
    "2x Gewinde M10x1,5 (Sackloch)": [("Gewinde", "M10", 2)],
    "Flowdrill M8 (4x)": [("Flowdrill", "M8", 4)],
    "Einnietmutter M6 4 Stk": [("Einnietmutter", "M6", 4)],
    "4-fach M5": [("Gewinde", "M5", 4)],
    '2x G 1/4" Gewinde': [("Zollgewinde", "1/4", 2)],
    "4x Gewinde": [("Gewinde", None, 4)],
    "ohne Gewinde": [],
}
for t, soll in FAELLE.items():
    ist = kurz(t)
    assert ist == soll, (t, ist, soll)
ok(f"Zeichnungstext: {len(FAELLE)} Fälle (Senkung ≠ Gewinde, beidseitig, angesenkt, Zoll, ohne Größe)")
h = zh.lesen("2x Senkung DIN 74 M6\n4x M8")
assert zh.gewinde_vorschlag(h) == "4xM8", zh.gewinde_vorschlag(h)       # Senkung kommt nicht ins Gewinde
assert zh.zusatz_mengen(h, mit_bohrbild=False) == {"Senken": 2}, zh.zusatz_mengen(h, mit_bohrbild=False)
assert "Zollgewinde 1/4" in (zh.nicht_abgedeckt(zh.lesen('2x G 1/4"')) or "")
assert "Gewinde ohne Größe" in (zh.nicht_abgedeckt(zh.lesen("4x Gewinde")) or "")
ok("Senkung nicht im Gewinde-Vorschlag, Senken als Zusatzarbeit, Zoll/ohne Größe im Bericht")


# ------------------------------------------------------------------ 2. Formular mit Bemerkung und Staffel
def formular_pdf(name):
    pfad = tmp / name
    c = canvas.Canvas(str(pfad), pagesize=A4)
    y = 800
    for z in ["Stahlbau Weber GmbH · Industriestr. 12 · 44137 Dortmund", "", "Anfrage",
              "Anfrage-Nr. 2026-1188    Datum 17.11.2026", "", "Sehr geehrte Damen und Herren,",
              "bitte um Angebot für folgende Laserteile:"]:
        c.drawString(50, y, z)
        y -= 16
    y -= 10
    cols = [40, 65, 150, 245, 320, 395]
    for x, t in zip(cols, ["Pos", "Zeichnungs-Nr.", "Benennung", "Werkstoff", "Menge", "Bemerkung"]):
        c.drawString(x, y, t)
    y -= 16
    for r in [["1", "4711-020-03", "Halter links", "1.4301", "25 Stk", "4x M8"],
              ["2", "4711-020-04", "Halter rechts", "1.4571", "1.000", "2x Senkung M6"],
              ["3", "4711-021-01", "Strebe", "1.4301", "50/100/250", "verzinkt"],
              ["4", "4711-022-00", "Rohr Ø42,4x2", "1.4301", "12", "Gewinde M10 beidseitig"]]:
        for x, t in zip(cols, r):
            c.drawString(x, y, t)
        y -= 16
    y -= 20
    for z in ["Liefertermin: KW 3/2027", "Mit freundlichen Grüßen", "i. A. Petra Weber"]:
        c.drawString(50, y, z)
        y -= 16
    c.showPage()
    c.save()
    return pfad


def zeichnung_pdf(name, artikel, werkstoff, stueck, hinweise=(), stueckliste=()):
    pfad = tmp / name
    c = canvas.Canvas(str(pfad), pagesize=landscape(A3))
    w, _ = landscape(A3)
    c.rect(60 * MM, 150 * MM, 250 * MM, 40 * MM)
    for x in range(70, 300, 40):
        c.circle(x * MM, 170 * MM, 4 * MM)
    c.setFont("Helvetica", 10)
    for i, t in enumerate(["860", "40", "20", "120", "45", "Ø8,5", "25", "R2"]):
        c.drawString((80 + i * 25) * MM, 200 * MM, t)
    for i, t in enumerate(hinweise):
        c.drawString(60 * MM, (130 - 6 * i) * MM, t)
    if stueckliste:
        y = 110
        for x, t in zip((60, 75, 95, 150, 200), ("Pos", "Menge", "Benennung", "Zeichnungs-Nr.", "Werkstoff")):
            c.drawString(x * MM, y * MM, t)
        for r in stueckliste:
            y -= 6
            for x, t in zip((60, 75, 95, 150, 200), r):
                c.drawString(x * MM, y * MM, t)
    x0, y0 = w - 190 * MM, 10 * MM
    c.rect(x0, y0, 180 * MM, 50 * MM)
    for lab, wert, dx, dy in [("Benennung", "Halter", 0, 40), ("Zeichnungsnummer", artikel, 90, 40),
                              ("Werkstoff", werkstoff, 0, 25), ("Stückzahl", stueck, 90, 25),
                              ("Halbzeug", "QR 40x40x3", 0, 10), ("Maßstab", "1:2", 90, 10),
                              ("Gezeichnet", "Müller", 130, 10), ("Allgemeintoleranz", "ISO 2768-mK", 130, 25)]:
        c.setFont("Helvetica", 6)
        c.drawString(x0 + (dx + 2) * MM, y0 + (dy + 8) * MM, lab)
        c.setFont("Helvetica", 11)
        c.drawString(x0 + (dx + 2) * MM, y0 + (dy + 2) * MM, wert)
    c.showPage()
    c.save()
    return pfad


f = pdf_art.lesen(formular_pdf("anfrage.pdf"))
assert f["seiten"][0]["art"] == pdf_art.FORMULAR
tab = f["tabelle"]
assert len(tab) == 4, tab                       # „Liefertermin …“ ist keine Zeile mehr
assert tab[0]["menge"] == "25 Stk" and tab[0]["bemerkung"] == "4x M8", tab[0]
assert tab[2]["menge"] == "50/100/250", tab[2]
assert formular.staffel("50/100/250") == [50, 100, 250] and formular.staffel("1.000") == [] \
    and formular.staffel("100/50") == [] and formular._menge_zelle("50/100/250") == 50
ok("Formular-Tabelle: Spalte Bemerkung, Menge ohne Bearbeitung, Staffel erkannt, Liefertermin beendet die Tabelle")

TEILE = ["4711-020-03", "4711-020-04", "4711-021-01", "4711-022-00"]


def messwerte():
    return [dict(artikel=a, datei=f"{a}.stp") for a in TEILE]


mw = messwerte()
erg = pdf_art.anwenden(mw, [f], None, WS)
je = {m["artikel"]: m for m in mw}
assert erg["formular"] == 4 and erg["bearbeitung"] == 3 and erg["werkstoff"] == 4, erg
assert je["4711-020-04"]["_stueck"] == 1000 and je["4711-020-04"]["_werkstoff"] == "1.4571"
assert je["4711-021-01"]["_stueck"] == 50 and je["4711-021-01"]["_stueck_formular"] is True
assert je["4711-021-01"]["_stueck_staffel_sicher"] is True
assert je["4711-021-01"]["_stueck_staffel"] == [50, 100, 250]
assert [x[:3] for x in [(h["art"], h["gewinde"], h["anzahl"]) for h in zh.lesen(je["4711-020-04"]["_zeichnung_text"])]] \
    == [("Senkung", "M6", 2)], je["4711-020-04"]["_zeichnung_text"]
assert kurz(je["4711-020-03"]["_zeichnung_text"]) == [("Gewinde", "M8", 4)]      # „25 Stk“ zählt nicht als Anzahl
assert kurz(je["4711-022-00"]["_zeichnung_text"]) == [("Gewinde", "M10", 2)]
assert je["4711-020-03"]["_zeichnung_quelle"] == "Anfrageformular anfrage.pdf Pos. 1"
assert "verzinkt" in je["4711-021-01"]["_zeichnung_text"]           # geht in die Zusatzarbeiten-Erkennung
ok("Bearbeitung je Teil aus der Formularzeile (Gewinde, Senkung, beidseitig, verzinkt), Staffel mit Hinweis")

# erneut anwenden (Umschalten im Prüfdialog): nichts doppelt, Felder zurückgenommen
erg2 = pdf_art.anwenden(mw, [f], None, WS)
assert kurz(je["4711-020-03"]["_zeichnung_text"]) == [("Gewinde", "M8", 4)], je["4711-020-03"]["_zeichnung_text"]
pdf_art.anwenden(mw, [], None, WS)
assert not any(k in je["4711-021-01"] for k in ("_stueck_staffel", "_zeichnung_text", "_bearbeitung_formular"))
ok("Erneutes Anwenden ohne Doppelte, ohne Formular alles zurückgenommen")

# ------------------------------------------------------------------ 3. Zeichnung weicht ab (F4 a)
z = pdf_art.lesen(zeichnung_pdf("4711-020-03.pdf", "4711-020-03", "1.4571", "30", ["2x Senkung DIN 74 M6"]))
assert z["zeichnungen"][0]["stueck"] == 30
mw = messwerte()
pdf_art.anwenden(mw, [f, z], WS, WS)
m = mw[0]
assert m["_stueck"] == 25 and m["_werkstoff"] == "1.4301", m        # Formular gilt
assert m["_stueck_zeichnung"] == "Zeichnung 4711-020-03.pdf S. 1: 30", m.get("_stueck_zeichnung")
assert m["_werkstoff_zeichnung"].endswith("1.4571"), m.get("_werkstoff_zeichnung")
assert kurz(m["_zeichnung_text"].split("\n")[0]) == [("Gewinde", "M8", 4)]
assert ("Senkung", "M6", 2) in kurz(m["_zeichnung_text"])
assert "Zeichnung 4711-020-03.pdf S. 1" in m["_zeichnung_quelle"]
ok("Zeichnung nennt andere Stückzahl/Werkstoff: Formular gilt, Zeichnung als „abweichend“, Hinweise aus beiden")

# ohne Formular: Zeichnung setzt Stück und Werkstoff (gelb) wie bisher, keine Abweichung
mw = messwerte()
pdf_art.anwenden(mw, [z], WS, WS)
assert mw[0]["_stueck"] == 30 and mw[0]["_stueck_formular"] is False and mw[0]["_werkstoff"] == "1.4571"
assert "_stueck_zeichnung" not in mw[0] and "_werkstoff_zeichnung" not in mw[0]
ok("Ohne Formular: Werte aus dem Schriftfeld wie bisher")

# ------------------------------------------------------------------ 4. Stückliste auf der Zeichnung
bg = pdf_art.lesen(zeichnung_pdf("BG-100.pdf", "BG-100", "1.4301", "5", stueckliste=[
    ("1", "2", "Stiel", "4711-020-03", "1.4571"), ("2", "4", "Riegel 4x M8", "4711-020-04", "1.4301")]))
sl = [x for x in bg["zeichnungen"] if x.get("stueckliste")]
assert len(sl) == 2 and sl[0]["artikel"] == "4711-020-03" and sl[0]["stueck_je_bg"] == 2, bg["zeichnungen"]
mw = messwerte()
pdf_art.anwenden(mw, [bg], WS, WS)
assert mw[0].get("_werkstoff") == "1.4571" and "Stückliste Pos. 1" in mw[0]["_werkstoff_quelle"], mw[0]
assert "_stueck" not in mw[0] or mw[0].get("_stueck_quelle", "").find("Stückliste") < 0
assert mw[0]["_stueck_je_bg"].endswith("2 je Baugruppe"), mw[0].get("_stueck_je_bg")
assert ("Gewinde", "M8", 4) in kurz(mw[1]["_zeichnung_text"]), mw[1].get("_zeichnung_text")
assert "_stueck_je_bg" not in mw[2]
ok("Stückliste auf der Zeichnung: Werkstoff/Bearbeitung je Teil, Menge nur je Baugruppe (nie als Stückzahl)")


# ------------------------------------------------------------------ 5. Word / LibreOffice
def docx(name, absaetze, tabelle):
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

    def p(t):
        return f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>"
    zeilen = "".join("<w:tr>" + "".join(f"<w:tc>{p(c)}</w:tc>" for c in r) + "</w:tr>" for r in tabelle)
    body = "".join(p(t) for t in absaetze[:3]) + f"<w:tbl>{zeilen}</w:tbl>" + "".join(p(t) for t in absaetze[3:])
    pfad = tmp / name
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("word/document.xml", f'<?xml version="1.0"?><w:document {w}><w:body>{body}</w:body></w:document>')
        z.writestr("word/header1.xml", f'<w:hdr {w}>{p("Anfrage-Nr.: AW-2026-077")}</w:hdr>')
    return pfad


def odt(name, absaetze, tabelle):
    ns = ('xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
          'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
          'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0"')
    zeilen = "".join("<table:table-row>" + "".join(f"<table:table-cell><text:p>{c}</text:p></table:table-cell>"
                                                    for c in r) + "</table:table-row>" for r in tabelle)
    body = "".join(f"<text:p>{t}</text:p>" for t in absaetze) + f"<table:table>{zeilen}</table:table>"
    pfad = tmp / name
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("content.xml", f'<?xml version="1.0"?><office:document-content {ns}><office:body><office:text>'
                                  f'{body}</office:text></office:body></office:document-content>')
    return pfad


TAB = [["Pos.", "Artikel-Nr.", "Bezeichnung", "Werkstoff", "Menge", "Bearbeitung"],
       ["1", "4711-020-03", "Halter", "1.4571", "40", "2x Senkung DIN 74 M6"],
       ["2", "4711-020-04", "Halter rechts", "1.4301", "100/200", "4x M8 beidseitig"]]
ABS = ["Metallbau Krüger GmbH", "Sehr geehrte Damen und Herren,", "bitte bieten Sie an:",
       "Liefertermin KW 5", "Mit freundlichen Grüßen"]
for pfad in (docx("Anfrage.docx", ABS, TAB), odt("Anfrage.odt", ABS, TAB)):
    g = pdf_art.lesen(pfad)
    assert g and g["seiten"][0]["art"] == pdf_art.FORMULAR, g
    assert [r["artikel"] for r in g["tabelle"]] == ["4711-020-03", "4711-020-04"], g["tabelle"]
    mw = messwerte()
    erg = pdf_art.anwenden(mw, [g], None, WS)
    assert erg["formular"] == 2 and mw[0]["_stueck"] == 40 and mw[0]["_werkstoff"] == "1.4571", (erg, mw[0])
    assert kurz(mw[0]["_zeichnung_text"]) == [("Senkung", "M6", 2)], mw[0]["_zeichnung_text"]
    assert mw[1]["_stueck"] == 100 and mw[1].get("_stueck_staffel") == [100, 200], (mw[1], g["text"])
    assert kurz(mw[1]["_zeichnung_text"]) == [("Gewinde", "M8", 8)]
    if pfad.suffix == ".docx":
        assert formular.nummer_aus([g]) == "AW-2026-077" or formular.anfragenummer(g["text"]) == "AW-2026-077", \
            g["text"][:200]
ok("Word (.docx mit Kopfzeile) und LibreOffice (.odt): Tabelle, Stück, Werkstoff, Bearbeitung, Staffel, Anfrage-Nr.")

alt = tmp / "Anfrage.doc"
alt.write_bytes(b"\xd0\xcf\x11\xe0 kein echtes Word")
assert pdf_art.lesen(alt) is None
assert "altes Office-Format" in formular_office.ALT_HINWEIS.format(name="Anfrage.doc")
kaputt = tmp / "kaputt.docx"
kaputt.write_bytes(b"PK nicht wirklich")
assert pdf_art.lesen(kaputt) is None
ok("Altes .doc und kaputte .docx: nicht gelesen, kein Absturz")

from rohrlaser import anfragen  # noqa: E402
assert {".docx", ".odt"} <= anfragen.FORMULAR and ".docx" not in anfragen.BILD
from rohrlaser import anfrage_ohne_step as aos  # noqa: E402
assert aos.eintraege([tmp / "Anfrage.docx"])[0]["art"] == "word"
ok("Word-Formulare zählen in der Anfrage als Formular (nicht als Bild), Liste ohne STEP zeigt „Word-Formular“")

# ------------------------------------------------------------------ 6. Tooltip im Prüfdialog
from rohrlaser.step_dialog import _bearbeitung_text  # noqa: E402
t = _bearbeitung_text(dict(_zeichnung_text="2x Senkung DIN 74 M6\n4x M8", _zeichnung_quelle="Anfrageformular a.pdf Pos. 2"))
assert "Anfrageformular a.pdf Pos. 2" in t and "2× Senkung M6" in t and "4× M8" in t, t
assert _bearbeitung_text({}) == ""
ok("Prüfdialog: Bearbeitung mit Quelle im Tooltip")

# ------------------------------------------------------------------ 7. Sicher erkannte Staffel wird angelegt
from rohrlaser import staffeln  # noqa: E402
P = [dict(pos="1", artikel="A-1", stueck=25, profil_id=1), dict(pos="2", artikel="B-2", stueck=8, profil_id=1)]
st, h = staffeln.aus_anfrage(P, {"A-1": [25, 50, 100]})
assert st == [[("1", 25), ("2", 8)], [("1", 50), ("2", 8)], [("1", 100), ("2", 8)]] and not h, (st, h)
st, h = staffeln.aus_anfrage(P, {"A-1": [25, 50], "B-2": [8, 16, 32]})
assert st == [] and "unterschiedlich" in h
st, h = staffeln.aus_anfrage([dict(P[0], satz="S1"), P[1]], {"A-1": [25, 50]})
assert st == [] and "Satz" in h
st, h = staffeln.aus_anfrage(P, None, [10, 50, 100])
assert st == [[("1", 10), ("2", 10)], [("1", 50), ("2", 50)], [("1", 100), ("2", 100)]]
assert staffeln.aus_anfrage(P, None, [50, 10]) == ([], "")
ok("Staffel aus der Anfrage: Stufen je Menge, andere Teile mit ihrer Menge; unklar (Längen, Satz) nur Hinweis")

from PySide6.QtWidgets import QApplication  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402
app = QApplication.instance() or QApplication([])
db = Datenbank(tmp / "staffel.db")
fenster = Hauptfenster(db, tmp, stumm=True)
STEP = str(HIER / "step" / "T01_RR42-4x2_L1250.step")
g = pdf_art.lesen(docx("Staffel.docx", ABS, [TAB[0], ["1", "T01_RR42-4x2_L1250", "Rundrohr", "1.4301", "10/50/100",
                                                     "2x Senkung M6"]]))
s1 = fenster.angebot_oeffnen(db.angebot_neu(dict(kundennr=None)))
s1.step_importieren([STEP], formulare=[g])
pos = [p for p in s1.positionen if p.get("profil_id")]
assert [p.get("stueck") for p in pos] == [10], [p.get("stueck") for p in s1.positionen]
stufen = db.staffel_stufen(s1.id)
mz = db.staffeln(s1.id)
assert len(stufen) == 3 and sorted(z["menge"] for z in mz) == [10, 50, 100], (stufen, mz)
assert all(staffeln.txt(z["schluessel"]) == staffeln.txt(pos[0]["pos"]) for z in mz), (mz, pos[0]["pos"])
ok("STEP-Import mit Formular-Staffel 10/50/100: Angebot 10 Stück, drei Stufen angelegt")

s2 = fenster.angebot_oeffnen(db.angebot_neu(dict(kundennr=None)))
s2.step_importieren([STEP], werkstoff_text="Bitte Preise für 20 / 100 / 500 Stk nennen.")
assert sorted(z["menge"] for z in db.staffeln(s2.id)) == [20, 100, 500], db.staffeln(s2.id)
anzahl = len(db.staffel_stufen(s2.id))
s2.step_importieren([STEP], werkstoff_text="Bitte Preise für 20 / 100 / 500 Stk nennen.")   # zweiter Import
assert len(db.staffel_stufen(s2.id)) == anzahl == 3
s3 = fenster.angebot_oeffnen(db.angebot_neu(dict(kundennr=None)))
s3.step_importieren([STEP], werkstoff_text="Bitte um Angebot für 20 Stk.")
assert db.staffel_stufen(s3.id) == []
ok("Staffel aus der Mail: Stufen im neuen Angebot, kein zweites Mal, ohne Staffel keine Stufen")

print("Alle Tests bestanden.")
