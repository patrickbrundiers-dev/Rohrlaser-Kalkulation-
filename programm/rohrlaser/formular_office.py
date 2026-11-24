"""Anfrageformulare aus Word und LibreOffice (Patrick 17.11.2026: „das erkennen von Zeichnung und Anfrageformular
verbessern und dessen auslesen verbessern“, F1 a).

Ein Anfrageformular als Word-Datei (.docx, .docm) oder LibreOffice-Text (.odt) wird wie ein PDF-Formular gelesen:
Absätze (auch Kopf-/Fußzeilen und Textfelder) als Text für Anfrage-Nr., Stückzahlen und Werkstoff, die erste Tabelle
mit erkennbarer Kopfzeile (Pos., Artikel-/Zeichnungs-Nr., Bezeichnung, Werkstoff, Menge, Bemerkung – dieselben
Begriffe wie formular.SPALTEN) direkt als Positionen. LibreOffice-Tabellen (.ods) und Excel mit Makros (.xlsm) gehen
wie eine Kunden-Stückliste (stueckliste.py). Alte Formate (.doc, .xls) lassen sich ohne Office nicht sicher lesen:
sie bekommen nur einen Hinweis (bitte als PDF oder .docx/.xlsx anfordern). Word ist nie eine Zeichnung.
Ohne Qt, ohne zusätzliche Bibliothek (zipfile + ElementTree), Makros werden nie ausgeführt."""
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

WORD = {".docx", ".docm", ".odt"}
TABELLE = {".ods", ".xlsm"}                     # wie stueckliste (Zellen)
ALT = {".doc", ".xls"}                          # nur Hinweis
ENDUNGEN = WORD | TABELLE
GRUND = "Anfrageformular (Word/LibreOffice)"
ALT_HINWEIS = ("{name}: altes Office-Format, wird nicht ausgelesen – bitte als PDF oder .docx/.xlsx anfordern bzw. "
               "Stückzahlen und Werkstoff von Hand prüfen.")

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
O_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
O_TAB = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
O_OFF = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
MAX_BYTES = 30 * 1024 * 1024                    # entpackte XML-Teile darüber werden nicht gelesen (Schutz)


def _xml(z, name):
    info = z.getinfo(name)
    if info.file_size > MAX_BYTES:
        raise ValueError("zu groß")
    return ElementTree.fromstring(z.read(name))


def _w_text(el):
    """Text eines Word-Elements: w:t, Tabulator/Zeilenumbruch als Leerzeichen."""
    teile = []
    for x in el.iter():
        if x.tag == W + "t" and x.text:
            teile.append(x.text)
        elif x.tag in (W + "tab", W + "br", W + "cr"):
            teile.append(" ")
    return re.sub(r"[ \t]+", " ", "".join(teile)).strip()


def _w_koerper(wurzel):
    """(Zeilen, Tabellen) eines Word-Teils in Lesereihenfolge; Tabellen [[Zelltext]], verschachtelte Tabellen zählen
    als Text ihrer Zelle."""
    zeilen, tabellen = [], []

    def gehe(el):
        for kind in el:
            if kind.tag == W + "p":
                t = _w_text(kind)
                if t:
                    zeilen.append(t)
            elif kind.tag == W + "tbl":
                tab = []
                for tr in kind.iter(W + "tr"):
                    zellen = [_w_text(tc) for tc in tr.findall(W + "tc")]
                    if any(zellen):
                        tab.append(zellen)
                        zeilen.append(" ".join(z for z in zellen if z))
                if tab:
                    tabellen.append(tab)
            elif kind.tag in (W + "sdt", W + "sdtContent", W + "body", W + "hdr", W + "ftr", W + "txbxContent"):
                gehe(kind)
            else:
                for tb in kind.iter(W + "txbxContent"):          # Textfelder (Formular-Kopf oft darin)
                    gehe(tb)
    gehe(wurzel)
    return zeilen, tabellen


def docx_inhalt(pfad):
    """(Zeilen, Tabellen) einer .docx/.docm: Kopfzeilen, Hauptteil, Fußzeilen. None = nicht lesbar."""
    try:
        with zipfile.ZipFile(pfad) as z:
            namen = z.namelist()
            if "word/document.xml" not in namen:
                return None
            zeilen, tabellen = [], []
            teile = sorted(n for n in namen if re.fullmatch(r"word/header\d*\.xml", n)) + ["word/document.xml"] + \
                sorted(n for n in namen if re.fullmatch(r"word/footer\d*\.xml", n))
            for n in teile:
                zl, tb = _w_koerper(_xml(z, n))
                zeilen += zl
                tabellen += tb
            return zeilen, tabellen
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, ElementTree.ParseError):
        return None


def _o_text(el):
    teile = []
    for x in el.iter():
        if x.text and x.tag in (O_TEXT + "p", O_TEXT + "h", O_TEXT + "span", O_TEXT + "a"):
            teile.append(x.text)
        if x.tag in (O_TEXT + "s", O_TEXT + "tab", O_TEXT + "line-break"):
            teile.append(" ")
        if x.tail and x is not el:
            teile.append(x.tail)
    return re.sub(r"\s+", " ", "".join(teile)).strip()


def _o_wiederholt(el, attr):
    try:
        return max(1, min(int(el.get(O_TAB + attr) or 1), 50))
    except ValueError:
        return 1


def odt_inhalt(pfad):
    """(Zeilen, Tabellen) einer .odt bzw. (für .ods) nur die Tabellen. None = nicht lesbar."""
    try:
        with zipfile.ZipFile(pfad) as z:
            wurzel = _xml(z, "content.xml")
    except (OSError, KeyError, ValueError, zipfile.BadZipFile, ElementTree.ParseError):
        return None
    zeilen, tabellen = [], []

    def gehe(el):
        for kind in el:
            if kind.tag in (O_TEXT + "p", O_TEXT + "h"):
                t = _o_text(kind)
                if t:
                    zeilen.append(t)
            elif kind.tag == O_TAB + "table":
                tab = []
                for tr in kind.iter(O_TAB + "table-row"):
                    zellen = []
                    for tc in tr:
                        if tc.tag in (O_TAB + "table-cell", O_TAB + "covered-table-cell"):
                            zellen += [_o_text(tc)] * _o_wiederholt(tc, "number-columns-repeated")
                    while zellen and not zellen[-1]:
                        zellen.pop()
                    if any(zellen):
                        tab.append(zellen)
                        zeilen.append(" ".join(x for x in zellen if x))
                if tab:
                    tabellen.append(tab)
            else:
                gehe(kind)
    gehe(wurzel)
    return zeilen, tabellen


def inhalt(pfad):
    """(Zeilen, Tabellen) einer Word-/LibreOffice-Datei oder None."""
    pfad = Path(pfad)
    e = pfad.suffix.lower()
    if e in (".docx", ".docm"):
        return docx_inhalt(pfad)
    if e in (".odt", ".ods"):
        return odt_inhalt(pfad)
    if e == ".xlsm":
        from . import stueckliste
        try:
            z = stueckliste.xlsx_zeilen(pfad.read_bytes())
        except (OSError, ValueError, KeyError, zipfile.BadZipFile, ElementTree.ParseError):
            return None
        return [" ".join(x for x in r if x) for r in z if any(r)], [z]
    return None


def lesen(pfad):
    """dict wie pdf_art.lesen (eine Seite, Art Formular, Tabelle direkt, Text für Anfrage-Nr. und Zeilenlogik) oder
    None (nicht lesbar bzw. leer)."""
    from . import pdf_art, stueckliste
    erg = inhalt(pfad)
    if not erg:
        return None
    zeilen, tabellen = erg
    rows = []
    for tab in tabellen:
        rows = stueckliste.tabelle(tab)
        if rows:
            break
    text = "\n".join(zeilen)
    if not text.strip() and not rows:
        return None
    seite = dict(nr=1, text=text, segmente=[], ocr=False, unsicher=set(), linien=0, art=pdf_art.FORMULAR,
                 grund=GRUND + (f", Tabelle mit {len(rows)} Zeile{'n' if len(rows) != 1 else ''}" if rows else ""),
                 tabelle_direkt=rows)
    return pdf_art.zusammen(dict(datei=Path(pfad).name, seiten=[seite], ocr=False))
