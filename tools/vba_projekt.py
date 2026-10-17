"""Erzeugt ein VBA-Projekt (vbaProject.bin) aus Quelltext und baut daraus eine .xlsm.

Excel braucht dafür kein kompiliertes P-Code: Das Projekt enthält nur den Quelltext
(_VBA_PROJECT mit Version 0xFFFF), Excel kompiliert beim ersten Öffnen selbst.
Umgesetzt nach [MS-OVBA] (Kompression, dir-Stream, PROJECT-Stream) und [MS-CFB]
(Compound File, Version 3).

Verwendung:
    projekt = vba_projekt(module, dokumente)   # -> bytes
    xlsm_packen(xlsx, xlsm, projekt, zeichnungen)
"""
import random
import re
import struct
import uuid
import zipfile

CODEPAGE = 1252
BASE_MAPPE = "0{00020819-0000-0000-C000-000000000046}"
BASE_BLATT = "0{00020820-0000-0000-C000-000000000046}"
STDOLE = (r"*\G{00020430-0000-0000-C000-000000000046}#2.0#0#C:\Windows\System32\stdole2.tlb#OLE Automation")


# ------------------------------------------------------------------ MS-OVBA 2.4.1 Kompression
def _copy_token_bits(diff):
    bits = 4
    while (1 << bits) < diff:
        bits += 1
    return bits


def komprimieren(daten):
    out = bytearray(b"\x01")
    for start in range(0, len(daten), 4096):
        chunk = daten[start:start + 4096]
        body = bytearray()
        pos, n = 0, len(chunk)
        while pos < n:
            flag_at = len(body)
            body.append(0)
            flag = 0
            for bit in range(8):
                if pos >= n:
                    break
                bits = _copy_token_bits(pos)
                max_len = (0xFFFF >> bits) + 3
                best_len, best_off = 0, 0
                for cand in range(pos - 1, -1, -1):
                    ln = 0
                    while pos + ln < n and ln < max_len and chunk[cand + ln] == chunk[pos + ln]:
                        ln += 1
                    if ln > best_len:
                        best_len, best_off = ln, pos - cand
                        if ln == max_len:
                            break
                if best_len >= 3:
                    body += struct.pack("<H", ((best_off - 1) << (16 - bits)) | (best_len - 3))
                    flag |= 1 << bit
                    pos += best_len
                else:
                    body.append(chunk[pos])
                    pos += 1
            body[flag_at] = flag
        if len(body) <= 4094:
            out += struct.pack("<H", 0xB000 | (len(body) + 2 - 3)) + body
        else:  # unkomprimiert: genau 4096 Byte
            out += struct.pack("<H", 0x3000 | (4098 - 3)) + chunk.ljust(4096, b"\x00")
    return bytes(out)


def entpacken(daten):
    """Gegenstück zu komprimieren() (für Tests)."""
    assert daten[0] == 1
    out = bytearray()
    i = 1
    while i < len(daten):
        hdr = struct.unpack_from("<H", daten, i)[0]
        size = (hdr & 0x0FFF) + 3
        ende = i + size
        i += 2
        cstart = len(out)
        if not hdr & 0x8000:
            out += daten[i:i + 4096]
            i = ende
            continue
        while i < ende:
            flag = daten[i]
            i += 1
            for bit in range(8):
                if i >= ende:
                    break
                if flag & (1 << bit):
                    tok = struct.unpack_from("<H", daten, i)[0]
                    i += 2
                    bits = _copy_token_bits(len(out) - cstart)
                    off = (tok >> (16 - bits)) + 1
                    ln = (tok & (0xFFFF >> bits)) + 3
                    for _ in range(ln):
                        out.append(out[-off])
                else:
                    out.append(daten[i])
                    i += 1
    return bytes(out)


# ------------------------------------------------------------------ MS-OVBA 2.4.3 Datenverschlüsselung
def _verschluesseln(projekt_id, daten, seed=None):
    seed = random.randrange(256) if seed is None else seed
    key = sum(projekt_id.encode("ascii")) & 0xFF
    version = 2
    out = bytearray([seed, seed ^ version, seed ^ key])
    unenc1, enc1, enc2 = key, out[2], out[1]
    for _ in range((seed & 6) // 2):
        temp = 0
        b = temp ^ ((enc2 + unenc1) & 0xFF)
        out.append(b)
        enc2, enc1, unenc1 = enc1, b, temp
    for byte in struct.pack("<I", len(daten)) + bytes(daten):
        b = byte ^ ((enc2 + unenc1) & 0xFF)
        out.append(b)
        enc2, enc1, unenc1 = enc1, b, byte
    return out.hex().upper()


# ------------------------------------------------------------------ dir-Stream
def _rec(rid, daten):
    return struct.pack("<HI", rid, len(daten)) + daten


def _mbcs(s):
    return s.encode("cp1252")


def _uni(s):
    return s.encode("utf-16-le")


def _dir_stream(name, module):
    d = bytearray()
    d += _rec(0x0001, struct.pack("<I", 1))            # SysKind Win32
    d += _rec(0x0002, struct.pack("<I", 0x409))        # LCID
    d += _rec(0x0014, struct.pack("<I", 0x409))        # LCIDINVOKE
    d += _rec(0x0003, struct.pack("<H", CODEPAGE))
    d += _rec(0x0004, _mbcs(name))
    d += _rec(0x0005, b"") + _rec(0x0040, b"")         # DocString
    d += _rec(0x0006, b"") + _rec(0x003D, b"")         # HelpFile
    d += _rec(0x0007, struct.pack("<I", 0))            # HelpContext
    d += _rec(0x0008, struct.pack("<I", 0))            # LibFlags
    d += struct.pack("<HIIH", 0x0009, 4, 1, 0)         # Version (Reserved=4, Major, Minor)
    d += _rec(0x000C, b"") + _rec(0x003C, b"")         # Constants
    # Verweis auf stdole (OLE Automation)
    d += _rec(0x0016, b"stdole") + _rec(0x003E, _uni("stdole"))
    libid = _mbcs(STDOLE)
    d += struct.pack("<HII", 0x000D, 4 + len(libid) + 6, len(libid)) + libid + struct.pack("<IH", 0, 0)
    # Module
    d += struct.pack("<HIH", 0x000F, 2, len(module))
    d += _rec(0x0013, struct.pack("<H", 0xFFFF))
    for m in module:
        d += _rec(0x0019, _mbcs(m["name"])) + _rec(0x0047, _uni(m["name"]))
        d += _rec(0x001A, _mbcs(m["name"])) + _rec(0x0032, _uni(m["name"]))
        d += _rec(0x001C, b"") + _rec(0x0048, b"")
        d += _rec(0x0031, struct.pack("<I", 0))        # Quelltext ab Offset 0 (kein P-Code)
        d += _rec(0x001E, struct.pack("<I", 0))
        d += _rec(0x002C, struct.pack("<H", 0xFFFF))
        d += struct.pack("<HI", 0x0022 if m["dokument"] else 0x0021, 0)
        d += struct.pack("<HI", 0x002B, 0)
    d += struct.pack("<HI", 0x0010, 0)
    return bytes(d)


def _quelltext(m):
    if m["dokument"]:
        kopf = [f'Attribute VB_Name = "{m["name"]}"', f'Attribute VB_Base = "{m["base"]}"',
                "Attribute VB_GlobalNameSpace = False", "Attribute VB_Creatable = False",
                "Attribute VB_PredeclaredId = True", "Attribute VB_Exposed = True",
                "Attribute VB_TemplateDerived = False", "Attribute VB_Customizable = True"]
    else:
        kopf = [f'Attribute VB_Name = "{m["name"]}"']
    code = m["code"].replace("\r\n", "\n").strip("\n")
    text = "\r\n".join(kopf + ([code] if code else [])) + "\r\n"
    return text.encode("cp1252")


def vba_projekt(module, dokumente, name="VBAProject"):
    """module: {Name: Quelltext} (Standardmodule); dokumente: [(CodeName, Quelltext, ist_mappe)].
    Ergebnis: Inhalt von vbaProject.bin."""
    alle = [dict(name=n, code=c, dokument=True, base=BASE_MAPPE if mappe else BASE_BLATT)
            for n, c, mappe in dokumente]
    alle += [dict(name=n, code=c, dokument=False) for n, c in module.items()]
    pid = "{" + str(uuid.UUID(int=random.getrandbits(128))).upper() + "}"
    zeilen = [f'ID="{pid}"']
    zeilen += [f"Document={m['name']}/&H00000000" for m in alle if m["dokument"]]
    zeilen += [f"Module={m['name']}" for m in alle if not m["dokument"]]
    zeilen += [f'Name="{name}"', 'HelpContextID="0"', 'VersionCompatible32="393222000"',
               f'CMG="{_verschluesseln(pid, bytes(4))}"', f'DPB="{_verschluesseln(pid, bytes(1))}"',
               f'GC="{_verschluesseln(pid, bytes([0xFF]))}"', "",
               "[Host Extender Info]", "&H00000001={3832D640-CF90-11CF-8E43-00A0C911005A};VBE;&H00000000", "",
               "[Workspace]"]
    zeilen += [f"{m['name']}=0, 0, 0, 0, C" for m in alle]
    project = ("\r\n".join(zeilen) + "\r\n").encode("cp1252")
    wm = b"".join(_mbcs(m["name"]) + b"\x00" + _uni(m["name"]) + b"\x00\x00" for m in alle) + b"\x00\x00"

    streams = {"PROJECT": project, "PROJECTwm": wm,
               "VBA/_VBA_PROJECT": bytes([0xCC, 0x61, 0xFF, 0xFF, 0x00, 0x00, 0x00]),
               "VBA/dir": komprimieren(_dir_stream(name, alle))}
    for m in alle:
        streams["VBA/" + m["name"]] = komprimieren(_quelltext(m))
    return cfb_schreiben(streams)


# ------------------------------------------------------------------ MS-CFB Version 3
FREESECT, ENDOFCHAIN, FATSECT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD
NOSTREAM = 0xFFFFFFFF


def _cfb_key(name):
    return (len(name), name.upper())


def _baum(namen):
    """Ausgeglichener Suchbaum über die sortierten Namen; Knoten der tiefsten Ebene rot.
    Ergebnis: Wurzel-Index und {Index: (links, rechts, farbe)} bezogen auf die Liste namen."""
    order = sorted(range(len(namen)), key=lambda i: _cfb_key(namen[i]))
    info, tiefe = {}, {}

    def bau(lo, hi, d):
        if lo > hi:
            return None
        mid = (lo + hi) // 2
        i = order[mid]
        tiefe[i] = d
        info[i] = [bau(lo, mid - 1, d + 1), bau(mid + 1, hi, d + 1)]
        return i

    wurzel = bau(0, len(order) - 1, 0)
    if not order:
        return None, {}
    maxd = max(tiefe.values())
    perfekt = len(order) == 2 ** (maxd + 1) - 1
    return wurzel, {i: (l, r, 0 if (tiefe[i] == maxd and not perfekt) else 1) for i, (l, r) in info.items()}


def cfb_schreiben(streams):
    """streams: {"Pfad/Name": bytes}. Speicher (Storages) ergeben sich aus den Pfaden."""
    # Verzeichnis aufbauen
    eintraege = [dict(name="Root Entry", typ=5, kinder=[], daten=b"")]
    speicher = {"": 0}
    for pfad in streams:
        teile = pfad.split("/")
        for k in range(1, len(teile)):
            sp = "/".join(teile[:k])
            if sp not in speicher:
                speicher[sp] = len(eintraege)
                eintraege[speicher["/".join(teile[:k - 1])]]["kinder"].append(len(eintraege))
                eintraege.append(dict(name=teile[k - 1], typ=1, kinder=[], daten=b""))
        eintraege[speicher["/".join(teile[:-1])]]["kinder"].append(len(eintraege))
        eintraege.append(dict(name=teile[-1], typ=2, kinder=[], daten=streams[pfad]))
    for e in eintraege:
        e.update(links=NOSTREAM, rechts=NOSTREAM, kind=NOSTREAM, farbe=1,
                 start=0 if e["typ"] == 1 else ENDOFCHAIN, groesse=0)
    for e in eintraege:
        if e["kinder"]:
            namen = [eintraege[k]["name"] for k in e["kinder"]]
            w, info = _baum(namen)
            e["kind"] = e["kinder"][w]
            for i, (l, r, f) in info.items():
                ke = eintraege[e["kinder"][i]]
                ke["links"] = NOSTREAM if l is None else e["kinder"][l]
                ke["rechts"] = NOSTREAM if r is None else e["kinder"][r]
                ke["farbe"] = f

    # Mini-Stream (Streams < 4096 Byte) und normale Streams
    mini, minifat = bytearray(), []
    gross = []
    for e in eintraege:
        if e["typ"] != 2:
            continue
        e["groesse"] = len(e["daten"])
        if len(e["daten"]) < 4096:
            n = -(-len(e["daten"]) // 64)
            if n == 0:
                continue
            e["start"] = len(minifat)
            minifat += [len(minifat) + i + 1 for i in range(n - 1)] + [ENDOFCHAIN]
            mini += e["daten"].ljust(n * 64, b"\x00")
        else:
            gross.append(e)

    def sektoren(n_bytes):
        return -(-n_bytes // 512)

    n_dir = sektoren(len(eintraege) * 128)
    n_minifat = sektoren(len(minifat) * 4)
    n_mini = sektoren(len(mini))
    n_gross = sum(sektoren(len(e["daten"])) for e in gross)
    n_fat = 1
    while True:
        gesamt = n_fat + n_dir + n_minifat + n_mini + n_gross
        if sektoren(gesamt * 4) <= n_fat:
            break
        n_fat += 1
    assert n_fat <= 109, "Projekt zu groß"
    fat = [FATSECT] * n_fat
    body = bytearray()

    def kette(daten):
        n = sektoren(len(daten))
        start = len(fat)
        for i in range(n):
            fat.append(start + i + 1 if i < n - 1 else ENDOFCHAIN)
        body.extend(daten.ljust(n * 512, b"\x00"))
        return start

    dir_platz = len(fat)
    for _ in range(n_dir):
        fat.append(len(fat) + 1)
    fat[-1] = ENDOFCHAIN
    body.extend(bytes(n_dir * 512))
    minifat_start = kette(struct.pack(f"<{len(minifat)}I", *minifat)) if minifat else ENDOFCHAIN
    if mini:
        eintraege[0]["start"] = kette(bytes(mini))
        eintraege[0]["groesse"] = len(mini)
    for e in gross:
        e["start"] = kette(e["daten"])
    fat += [FREESECT] * (n_fat * 128 - len(fat))

    verz = bytearray()
    for e in eintraege:
        nm = _uni(e["name"]) + b"\x00\x00"
        verz += nm.ljust(64, b"\x00") + struct.pack("<HBBIII", len(nm), e["typ"], e["farbe"],
                                                    e["links"], e["rechts"], e["kind"])
        verz += bytes(16) + bytes(4) + bytes(16) + struct.pack("<IQ", e["start"], e["groesse"])
    verz = verz.ljust(n_dir * 512, b"\x00")
    for off in range(len(eintraege) * 128, len(verz), 128):
        verz[off + 68:off + 80] = struct.pack("<III", NOSTREAM, NOSTREAM, NOSTREAM)
    body[0:n_dir * 512] = verz
    # FAT-Sektoren stehen vor dem Verzeichnis
    fat_bytes = struct.pack(f"<{len(fat)}I", *fat)
    body = fat_bytes + bytes(body)
    difat = list(range(n_fat)) + [FREESECT] * (109 - n_fat)
    kopf = struct.pack("<8s16sHHHHH6sIIIIIIIII", bytes.fromhex("D0CF11E0A1B11AE1"), bytes(16), 0x003E, 0x0003,
                       0xFFFE, 9, 6, bytes(6), 0, n_fat, dir_platz, 0, 4096, minifat_start, n_minifat,
                       ENDOFCHAIN, 0)
    kopf += struct.pack("<109I", *difat)
    return bytes(kopf) + bytes(body)


# ------------------------------------------------------------------ .xlsm packen
REL_VBA = "http://schemas.microsoft.com/office/2006/relationships/vbaProject"
REL_DRAWING = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing"
CT_XLSM = "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
CT_DRAWING = "application/vnd.openxmlformats-officedocument.drawing+xml"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
# Elemente, vor denen <drawing> im Arbeitsblatt stehen muss (Reihenfolge nach CT_Worksheet)
NACH_DRAWING = ("legacyDrawing", "legacyDrawingHF", "drawingHF", "picture", "oleObjects", "controls",
                "webPublishItems", "tableParts", "extLst")


def _blatt_pfade(z):
    """Blattname -> Pfad der Blatt-XML."""
    wb = z.read("xl/workbook.xml").decode()
    rels = z.read("xl/_rels/workbook.xml.rels").decode()
    ziele = dict(re.findall(r'<Relationship[^>]*?Id="([^"]+)"[^>]*?Target="([^"]+)"', rels))
    ziele.update({i: t for t, i in re.findall(r'<Relationship[^>]*?Target="([^"]+)"[^>]*?Id="([^"]+)"', rels)})
    out = {}
    for tag in re.findall(r"<sheet [^>]*/>", wb):
        name = re.search(r'name="([^"]+)"', tag).group(1)
        rid = re.search(r'r:id="([^"]+)"', tag).group(1)
        name = name.replace("&amp;", "&").replace("&quot;", '"').replace("&apos;", "'")
        ziel = ziele[rid].lstrip("/")
        out[name] = ziel if ziel.startswith("xl/") else "xl/" + ziel
    return out


REL_MENUBAND = "http://schemas.microsoft.com/office/2006/relationships/ui/extensibility"


def xlsm_packen(xlsx, xlsm, projekt, zeichnungen=None, menueband=None):
    """xlsx (von openpyxl, CodeNames gesetzt) + vbaProject.bin -> xlsm.
    zeichnungen: {Blattname: DrawingML-XML} für Schaltflächen (nur Blätter ohne eigene Zeichnung).
    menueband: customUI-XML (Schema 2006/01) für eine eigene Registerkarte."""
    zeichnungen = zeichnungen or {}
    with zipfile.ZipFile(xlsx) as z:
        dateien = {n: z.read(n) for n in z.namelist()}
        blaetter = _blatt_pfade(z)
    ct = dateien["[Content_Types].xml"].decode()
    ct = re.sub(r'(PartName="/xl/workbook.xml" ContentType=")[^"]+"', rf'\g<1>{CT_XLSM}"', ct)
    ct = re.sub(r'(ContentType=")[^"]+(" PartName="/xl/workbook.xml")', rf'\g<1>{CT_XLSM}\2', ct)
    if 'Extension="bin"' not in ct:
        ct = ct.replace("<Default ", '<Default Extension="bin" ContentType="application/vnd.ms-office.vbaProject"/><Default ', 1)
    rels = dateien["xl/_rels/workbook.xml.rels"].decode()
    rels = rels.replace("</Relationships>", f'<Relationship Id="rIdVBA1" Type="{REL_VBA}" Target="vbaProject.bin"/></Relationships>')
    dateien["xl/_rels/workbook.xml.rels"] = rels.encode()
    dateien["xl/vbaProject.bin"] = projekt

    for nr, (blatt, xml) in enumerate(zeichnungen.items(), start=1):
        pfad = blaetter[blatt]
        teil = f"xl/drawings/schaltflaechen{nr}.xml"
        assert teil not in dateien
        dateien[teil] = xml.encode("utf-8")
        ct = ct.replace("</Types>", f'<Override PartName="/{teil}" ContentType="{CT_DRAWING}"/></Types>')
        ordner, datei = pfad.rsplit("/", 1)
        rpfad = f"{ordner}/_rels/{datei}.rels"
        if rpfad in dateien:
            r = dateien[rpfad].decode()
            assert REL_DRAWING not in r, f"Blatt {blatt} hat schon eine Zeichnung"
            r = r.replace("</Relationships>", f'<Relationship Id="rIdBtn1" Type="{REL_DRAWING}" Target="/{teil}"/></Relationships>')
        else:
            r = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 f'<Relationship Id="rIdBtn1" Type="{REL_DRAWING}" Target="/{teil}"/></Relationships>')
        dateien[rpfad] = r.encode()
        s = dateien[pfad].decode()
        tag = f'<drawing xmlns:r="{NS_R}" r:id="rIdBtn1"/>'
        m = re.search(r"<(%s)[ >/]" % "|".join(NACH_DRAWING), s)
        s = s[:m.start()] + tag + s[m.start():] if m else s.replace("</worksheet>", tag + "</worksheet>")
        dateien[pfad] = s.encode()
    if menueband:
        dateien["customUI/customUI.xml"] = menueband.encode("utf-8")
        if 'Extension="xml"' not in ct:
            ct = ct.replace("<Default ", '<Default Extension="xml" ContentType="application/xml"/><Default ', 1)
        r = dateien["_rels/.rels"].decode()
        r = r.replace("</Relationships>", f'<Relationship Id="rIdUI1" Type="{REL_MENUBAND}" Target="customUI/customUI.xml"/></Relationships>')
        dateien["_rels/.rels"] = r.encode()
    dateien["[Content_Types].xml"] = ct.encode()

    with zipfile.ZipFile(xlsm, "w", zipfile.ZIP_DEFLATED) as z:
        for n in ["[Content_Types].xml"] + [n for n in dateien if n != "[Content_Types].xml"]:
            z.writestr(n, dateien[n])


def menueband_xml(tab, gruppen):
    """Registerkarte für das Menüband. gruppen: [(Bezeichnung, [(Makro, Beschriftung, imageMso, Tipp)])].
    Die Makros werden mit dem IRibbonControl-Argument aufgerufen."""
    from xml.sax.saxutils import quoteattr
    teile = []
    for g, (titel, knoepfe) in enumerate(gruppen, start=1):
        teile.append(f'<group id="grp{g}" label={quoteattr(titel)}>')
        for k, (makro, text, bild, tipp) in enumerate(knoepfe, start=1):
            teile.append(f'<button id="btn{g}_{k}" label={quoteattr(text)} imageMso="{bild}" size="large" '
                         f'onAction="{makro}" screentip={quoteattr(text)} supertip={quoteattr(tipp)}/>')
        teile.append("</group>")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<customUI xmlns="http://schemas.microsoft.com/office/2006/01/customui">'
            f'<ribbon><tabs><tab id="tabRohrlaser" label={quoteattr(tab)} insertAfterMso="TabHome">'
            + "".join(teile) + "</tab></tabs></ribbon></customUI>")


def schaltflaechen_xml(knoepfe):
    """knoepfe: [(Makroname, Beschriftung, (Spalte0, Zeile0, Spalte1, Zeile1), Farbe)] mit 0-basierten Zellen."""
    teile = []
    for i, (makro, text, (c0, r0, c1, r1), farbe) in enumerate(knoepfe, start=2):
        teile.append(
            f'<xdr:twoCellAnchor editAs="absolute">'
            f'<xdr:from><xdr:col>{c0}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{r0}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from>'
            f'<xdr:to><xdr:col>{c1}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>{r1}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to>'
            f'<xdr:sp macro="[0]!{makro}" textlink="">'
            f'<xdr:nvSpPr><xdr:cNvPr id="{i}" name="Schaltfläche {makro}"/><xdr:cNvSpPr/></xdr:nvSpPr>'
            f'<xdr:spPr><a:prstGeom prst="roundRect"><a:avLst/></a:prstGeom>'
            f'<a:solidFill><a:srgbClr val="{farbe}"/></a:solidFill><a:ln><a:noFill/></a:ln></xdr:spPr>'
            f'<xdr:txBody><a:bodyPr vertOverflow="clip" horzOverflow="clip" rtlCol="0" anchor="ctr"/><a:lstStyle/>'
            f'<a:p><a:pPr algn="ctr"/><a:r><a:rPr lang="de-DE" sz="1100" b="1">'
            f'<a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:latin typeface="Arial"/></a:rPr>'
            f'<a:t>{text}</a:t></a:r></a:p></xdr:txBody></xdr:sp><xdr:clientData/></xdr:twoCellAnchor>')
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">' + "".join(teile) + "</xdr:wsDr>")
