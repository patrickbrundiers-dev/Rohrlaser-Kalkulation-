"""Vorschau für Anhänge im Programm (Patrick 17.11.2026: „Die Dokumente in der Mail in einem eigenen Viewer im
Programm als Vorschau, nicht extern öffnen“, Freigabe „Alle Empfehlungen a“ und „noch eine Vorschau für Word und
Excel“). Nur selbst erzeugte Testdateien.

  A1 Word (.docx): Überschrift, Absatz, Tabelle; Excel (.xlsx): Blatt mit Text, Zahl, Wahrheitswert
  A2 PDF, Bild, Text, Mail (mit Anhang, der sich in der Vorschau öffnet, ausführbarer nie), DXF, alte .doc ohne Vorschau
  A3 STEP: 3D-Vorschau aus der Messung im Hintergrund (nur wenn die Messung hier verfügbar ist)
  A4 Anfragen-Seite: ein Klick auf einen Anhang öffnet die Vorschau, nicht das externe Programm; gesperrte und
     ausführbare Dateien fehlen in der Liste; „Extern öffnen“ öffnet erst nach dem Knopf
  A5 Angebot (Anfrage ohne STEP): „Ansehen“ öffnet die Vorschau

Aufruf: python tests/test_anhang_vorschau.py   (Oberfläche ohne Bildschirm: QT_QPA_PLATFORM=offscreen)
"""
import datetime
import os
import sys
import tempfile
import zipfile
from pathlib import Path

HIER = Path(__file__).parent
sys.path.insert(0, str(HIER.parent / "programm"))
sys.path.insert(0, str(HIER))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QTabWidget, QTextBrowser  # noqa: E402

import mail_testdateien  # noqa: E402
from rohrlaser import anfragen_akten as ak  # noqa: E402
from rohrlaser import anhang_vorschau as av  # noqa: E402
from rohrlaser import step  # noqa: E402
from rohrlaser.datenbank import Datenbank  # noqa: E402
from rohrlaser.fenster import Hauptfenster  # noqa: E402


def ok(text):
    print("OK    ", text)


app = QApplication.instance() or QApplication([])
tmp = Path(tempfile.mkdtemp())
JETZT = datetime.datetime.now().replace(microsecond=0)
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
S = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
R = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'


def docx(pfad):
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("word/document.xml", f"""<?xml version="1.0"?><w:document {W}><w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Anfrage Gestell</w:t></w:r></w:p>
<w:p><w:r><w:t>Bitte 5 Stück aus S235 anbieten, Gewinde M8.</w:t></w:r></w:p>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Pos</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>Menge</w:t></w:r></w:p></w:tc></w:tr>
<w:tr><w:tc><w:p><w:r><w:t>10</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>5</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
</w:body></w:document>""")
        z.writestr("word/footer1.xml", f'<w:ftr {W}><w:p><w:r><w:t>Muster Metall GmbH</w:t></w:r></w:p></w:ftr>')


def xlsx(pfad):
    with zipfile.ZipFile(pfad, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {S} {R}><sheets><sheet name="Stückliste" sheetId="1" r:id="rId1"/>'
                                      '</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="x"/></Relationships>')
        z.writestr("xl/sharedStrings.xml", f'<sst {S}><si><t>Artikel</t></si><si><t>Stück</t></si>'
                                           '<si><t>Rahmen R-77</t></si></sst>')
        z.writestr("xl/worksheets/sheet1.xml", f"""<worksheet {S}><sheetData>
<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>
<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>12</v></c><c r="D2" t="b"><v>1</v></c><c r="E2"><v>2.5</v></c></row>
</sheetData></worksheet>""")


# ------------------------------------------------------------------ A1 Word und Excel
docx(tmp / "anfrage.docx")
h = av.docx_html(tmp / "anfrage.docx")
assert "<h2>Anfrage Gestell</h2>" in h and "Gewinde M8" in h and "<td>Menge</td>" in h and "Muster Metall" in h, h
xlsx(tmp / "liste.xlsx")
[(name, zeilen)] = av.xlsx_blaetter(tmp / "liste.xlsx")
assert name == "Stückliste" and zeilen == [["Artikel", "Stück"], ["Rahmen R-77", "12", "", "WAHR", "2,5"]], zeilen
assert av.docx_text(tmp / "anfrage.docx").splitlines()[:4] == ["Anfrage Gestell", "Bitte 5 Stück aus S235 anbieten, Gewinde M8.", "Pos\tMenge", "10\t5"]
assert av.art("x.DOCX") == "word" and av.art("x.xlsm") == "excel" and av.art("x.doc") == "keine"
ok("A1 Word: Überschrift, Absatz, Tabelle, Fußzeile; Excel: Blatt mit Text, Zahl, Wahrheitswert, Leerzelle")

# ------------------------------------------------------------------ A2 die übrigen Arten im Fenster
from reportlab.pdfgen import canvas  # noqa: E402
c = canvas.Canvas(str(tmp / "zeichnung.pdf"))
c.drawString(100, 700, "Rahmen R-77, S235, 5 Stück")
c.showPage()
c.drawString(100, 700, "Seite 2")
c.save()
bild = QImage(300, 200, QImage.Format_RGB32)
bild.fill(QColor("orange"))
bild.save(str(tmp / "foto.png"))
(tmp / "notiz.txt").write_text("Bitte bis KW 49.\nGruß", encoding="utf-8")
(tmp / "alt.doc").write_bytes(b"\xd0\xcf\x11\xe0 altes Word")
(tmp / "mail.eml").write_bytes(mail_testdateien.eml(
    "Anfrage Rahmen", "Bitte anbieten.", "Hans Kunde", "kauf@kunde.example", JETZT,
    [("skizze.txt", b"Skizze 1"), ("boese.exe", b"MZ")]))
dxf = HIER / "dxf" / "rohr_ansichten_QR40.dxf"
extern = []
liste = [dict(name=p.name, pfad=p) for p in (tmp / "zeichnung.pdf", tmp / "foto.png", tmp / "notiz.txt",
                                              tmp / "anfrage.docx", tmp / "liste.xlsx", tmp / "mail.eml", dxf,
                                              tmp / "alt.doc")]
v = av.fenster(None, liste, 0, extern.append)
w = v.flaeche.currentWidget()
assert v.inhalt_art == "pdf" and w.seiten == 2 and "1 von 8" in v.titel.text()
v.zoomen(1.25)
assert v.flaeche.currentWidget().seiten == 2 and v.zoom == 1.25
v.zeigen(1)
assert v.inhalt_art == "bild" and v.flaeche.currentWidget().seiten == 1
v.zeigen(2)
assert "KW 49" in v.flaeche.currentWidget().toPlainText()
v.zeigen(3)
assert "Gewinde M8" in v.flaeche.currentWidget().toPlainText()
v.zeigen(4)
t = v.flaeche.currentWidget()
assert isinstance(t, QTabWidget) and t.tabText(0) == "Stückliste" and t.widget(0).item(1, 0).text() == "Rahmen R-77"
v.zeigen(5)
b = v.flaeche.currentWidget()
assert isinstance(b, QTextBrowser) and "Hans Kunde" in b.toPlainText() and "skizze.txt" in b.toPlainText()
mail = __import__("rohrlaser.mail", fromlist=["x"]).lesen(tmp / "mail.eml")
k_exe = next(k for k, (n, _d) in enumerate(mail.anhaenge) if n == "boese.exe")
assert v.mail_anhang(mail, k_exe) is None and "Sicherheitsgründen" in v.hinweis.text() and len(v.eintraege) == 8
k_txt = next(k for k, (n, _d) in enumerate(mail.anhaenge) if n == "skizze.txt")
assert v.mail_anhang(mail, k_txt) is not None and v.i == 6 and "Skizze 1" in v.flaeche.currentWidget().toPlainText()
v.zeigen(7)
assert v.inhalt_art == "dxf" and v.flaeche.currentWidget().d["strecken"], v.inhalt_art
v.flaeche.currentWidget().grab()                          # zeichnen ohne Fehler
v.zeigen(8)
assert "keine Vorschau" in v.flaeche.currentWidget().meldung
v.extern_oeffnen()
assert extern == [tmp / "alt.doc"]
v.zeigen(99)
assert v.i == 8 and not v.vor.isEnabled()
(tmp / "kaputt.pdf").write_bytes(b"%PDF kaputt")
v2 = av.fenster(None, [dict(name="kaputt.pdf", pfad=tmp / "kaputt.pdf")])
assert "nicht lesen" in v2.flaeche.currentWidget().meldung
ok("A2 PDF (2 Seiten, Zoom), Bild, Text, Word, Excel, Mail mit Anhang in der Vorschau (.exe nie), DXF, alte .doc "
   "mit „Extern öffnen“; kaputte Datei = Hinweis")

# ------------------------------------------------------------------ A3 STEP in 3D
befehl = step.messprogramm(HIER.parent / "programm")
if befehl:
    ref = HIER / "step_referenz" / "REF02_QR40x40x2_L1000.step"
    v3 = av.fenster(None, [dict(name=ref.name, pfad=ref)], 0, None, befehl)
    assert "3D wird berechnet" in v3.flaeche.currentWidget().meldung
    v3.step_warten()
    a3 = v3.flaeche.currentWidget()
    assert type(a3).__name__ == "Ansicht3D" and a3.netz and a3.netz["p"], a3
    ok("A3 STEP: 3D-Vorschau aus der Messung im Hintergrund")
else:
    print("--     A3 übersprungen: keine STEP-Messung in dieser Umgebung")
netz = av.netz_vereint([dict(p=[0, 0, 0, 1, 0, 0, 0, 1, 0], t={"AW": [0, 1, 2]}),
                        dict(p=[0, 0, 0, 1, 0, 0, 0, 1, 0], t={"AW": [0, 1, 2]}, lage=[5, 0, 0, 0, 0, 1, 1, 0, 0])])
assert netz["t"]["AW"] == [0, 1, 2, 3, 4, 5] and netz["p"][9:12] == [5, 0, 0]
ok("A3b mehrere Körper werden in ihrer Einbaulage zu einem Netz")

# ------------------------------------------------------------------ A4 Anfragen-Seite
db = Datenbank(tmp / "prog" / "rohrlaser.db")
db.einstellung_setzen("benutzer_kuerzel", "PB")
abl = ak.OrdnerAblage(tmp / "akten", "PB", platz="BUERO1")
(tmp / "setup.exe").write_bytes(b"MZ")
a, _ = abl.anlegen(dict(quelle="ordner", betreff="Anfrage Gestell", absender="kauf@kunde.example"),
                   [tmp / "zeichnung.pdf", tmp / "anfrage.docx", tmp / "liste.xlsx", tmp / "setup.exe"], "g1")
fenster = Hauptfenster(db, tmp / "prog", stumm=True)
seite = fenster.anfragen_seite
seite._ablage = None
seite.ablage = lambda: abl
geoeffnet = []
fenster.datei_oeffnen = geoeffnet.append
seite.neu_laden()
seite.waehlen(a.nr)
d = next(x for x in abl.neu_lesen(a).dateien() if x["name"] == "anfrage.docx")
from PySide6.QtCore import QUrl  # noqa: E402
seite._link(QUrl(f"datei:{d.get('datei', d['name'])}"))
v4 = seite._vorschau
assert not geoeffnet and v4.eintrag["name"] == "anfrage.docx" and v4.inhalt_art == "word", geoeffnet
assert sorted(e["name"] for e in v4.eintraege) == ["anfrage.docx", "liste.xlsx", "zeichnung.pdf"]   # keine .exe
v4.extern_oeffnen()
assert geoeffnet == [d["pfad"]]
ok("A4 Klick auf einen Anhang öffnet die Vorschau im Programm, ◀ ▶ durch die übrigen (ohne .exe), extern nur per Knopf")

# ------------------------------------------------------------------ A5 Angebot: Dateien der Anfrage ohne STEP
from rohrlaser.anfrage_ohne_step_dialog import DateienDialog  # noqa: E402


class Seite:
    f = fenster
    eintraege = None

    def __init__(self):
        self.st = dict(dateien=[dict(name="zeichnung.pdf", art="pdf"), dict(name="liste.xlsx", art="excel")])

    def anfrage_datei(self, name):
        return tmp / name

    def fremd(self):
        return False


dd = DateienDialog.__new__(DateienDialog)
dd.seite = Seite()
dd.eintraege = dd.seite.st["dateien"]
dd.gewaehlt = lambda: dd.eintraege[1]
QDialog.__init__(dd)
assert dd.ansehen() == tmp / "liste.xlsx"
assert dd.vorschau.inhalt_art == "excel" and len(dd.vorschau.eintraege) == 2 and not geoeffnet[1:]
ok("A5 Angebot (Anfrage ohne STEP): „Ansehen“ öffnet die Vorschau im Programm")
print("Alle Tests bestanden.")
