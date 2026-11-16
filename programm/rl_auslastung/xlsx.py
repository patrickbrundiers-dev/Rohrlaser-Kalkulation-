"""Plan 3.3 (Paket D): Excel-Datei (.xlsx) ohne Zusatzpaket schreiben. Je Blatt eine Kopfzeile (fett, fixiert, mit
Filter) und Zeilen aus Text, Zahlen, Datum oder None. Ohne Qt."""
import datetime
import re
import zipfile
from xml.sax.saxutils import escape

_TYPEN = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" '
          'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/styles.xml" '
          'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          '{blaetter}</Types>')
_STILE = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
          '<numFmts count="2"><numFmt numFmtId="164" formatCode="0.0"/><numFmt numFmtId="165" formatCode="dd.mm.yyyy"/>'
          '</numFmts>'
          '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
          '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
          '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/>'
          '</fill></fills><borders count="1"><border/></borders>'
          '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
          '<cellXfs count="4"><xf xfId="0"/><xf fontId="1" xfId="0" applyFont="1"/>'
          '<xf numFmtId="164" xfId="0" applyNumberFormat="1"/><xf numFmtId="165" xfId="0" applyNumberFormat="1"/>'
          '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
          '</styleSheet>')


def _spalte(n):
    t = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        t = chr(65 + r) + t
    return t


def _blattname(name, schon):
    name = re.sub(r"[\[\]:*?/\\\\]", " ", str(name)).strip()[:31] or "Blatt"
    basis, i = name, 2
    while name.casefold() in schon:
        name = f"{basis[:28]} {i}"
        i += 1
    schon.add(name.casefold())
    return name


def _zelle(ref, wert):
    if wert is None or wert == "":
        return ""
    if isinstance(wert, bool):
        wert = "ja" if wert else "nein"
    if isinstance(wert, datetime.date):
        tage = (wert - datetime.date(1899, 12, 30)).days
        return f'<c r="{ref}" s="3"><v>{tage}</v></c>'
    if isinstance(wert, int):
        return f'<c r="{ref}"><v>{wert}</v></c>'
    if isinstance(wert, float):
        return f'<c r="{ref}" s="2"><v>{round(wert, 4)!r}</v></c>'
    return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(wert))}</t></is></c>'


def schreiben(pfad, blaetter):
    """blaetter = [(Name, Kopf (Liste), Zeilen (Liste von Listen))]. Schreibt die Datei pfad (.xlsx)."""
    schon, namen, teile = set(), [], []
    for name, kopf, zeilen in blaetter:
        namen.append(_blattname(name, schon))
        reihen = []
        for r, z in enumerate([list(kopf)] + [list(x) for x in zeilen], start=1):
            zellen = "".join(
                (f'<c r="{_spalte(c)}{r}" s="1" t="inlineStr"><is><t>{escape(str(w))}</t></is></c>' if r == 1
                 else _zelle(f"{_spalte(c)}{r}", w)) for c, w in enumerate(z))
            reihen.append(f'<row r="{r}">{zellen}</row>')
        breite = "".join(f'<col min="{c + 1}" max="{c + 1}" width="{min(60, max(10, len(str(k)) + 4))}" '
                         'customWidth="1"/>' for c, k in enumerate(kopf))
        letzte = f"{_spalte(max(0, len(kopf) - 1))}{len(zeilen) + 1}"
        teile.append('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                     '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft"'
                     ' state="frozen"/></sheetView></sheetViews>'
                     + (f"<cols>{breite}</cols>" if kopf else "")
                     + f'<sheetData>{"".join(reihen)}</sheetData>'
                     + (f'<autoFilter ref="A1:{letzte}"/>' if kopf else "") + '</worksheet>')
    with zipfile.ZipFile(pfad, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _TYPEN.format(blaetter="".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(teile) + 1))))
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
                   'officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   + "".join(f'<sheet name="{escape(n)}" sheetId="{i}" r:id="rId{i}"/>'
                             for i, n in enumerate(namen, start=1)) + '</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   + "".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/'
                             f'2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
                             for i in range(1, len(teile) + 1))
                   + f'<Relationship Id="rId{len(teile) + 1}" Type="http://schemas.openxmlformats.org/'
                   'officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr("xl/styles.xml", _STILE)
        for i, t in enumerate(teile, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", t)
