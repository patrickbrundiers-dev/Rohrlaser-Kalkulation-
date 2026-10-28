"""Test-Mails ohne Outlook erzeugen (für tests/test_mail.py und test_anfragen.py): .msg als Compound File
(MS-CFB, Version 3, mit Mini-Stream) mit den MAPI-Eigenschaften, die Outlook beim Ziehen einer Mail auf den Desktop
schreibt (Betreff, Text, Absender, Sendezeit, Anhänge, weitergeleitete Mail als eingebettete Nachricht), und .eml über
das email-Paket. Es gibt keine echten Mails von Patrick; der Aufbau folgt MS-OXMSG."""
import datetime
import struct
from email.message import EmailMessage

FREI, ENDE, FAT_SEKTOR = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD
SEKTOR, MINI, GRENZE = 512, 64, 4096


def _vergleich(name):
    return len(name), name.upper()


class _Eintrag:
    def __init__(self, name, art, daten=b""):
        self.name, self.art, self.daten = name, art, daten       # art 1 Speicher, 2 Strom, 5 Wurzel
        self.kinder, self.links, self.rechts, self.kind = [], FREI, FREI, FREI
        self.start, self.nr = ENDE, 0


def cfb(stroeme):
    """Compound File aus {'Speicher/Unter/Strom': bytes}; Speicher entstehen aus den Pfaden."""
    wurzel = _Eintrag("Root Entry", 5)
    alle = [wurzel]
    speicher = {"": wurzel}
    for pfad in sorted(stroeme):
        teile = pfad.split("/")
        for i in range(1, len(teile)):
            schl = "/".join(teile[:i])
            if schl not in speicher:
                e = _Eintrag(teile[i - 1], 1)
                speicher["/".join(teile[:i - 1])].kinder.append(e)
                speicher[schl] = e
                alle.append(e)
        e = _Eintrag(teile[-1], 2, stroeme[pfad])
        speicher["/".join(teile[:-1])].kinder.append(e)
        alle.append(e)
    for i, e in enumerate(alle):
        e.nr = i
    for e in alle:          # Kinder als entarteter Suchbaum über rechte Nachbarn (gültige Reihenfolge)
        k = sorted(e.kinder, key=lambda x: _vergleich(x.name))
        if k:
            e.kind = k[0].nr
            for a, b in zip(k, k[1:]):
                a.rechts = b.nr
    # Mini-Stream für kleine Ströme
    mini, mini_fat = bytearray(), []
    for e in alle:
        if e.art == 2 and len(e.daten) < GRENZE and e.daten:
            e.start = len(mini) // MINI
            n = -(-len(e.daten) // MINI)
            mini_fat += [e.start + j + 1 for j in range(n - 1)] + [ENDE]
            mini += e.daten + b"\x00" * (n * MINI - len(e.daten))
    sektoren, fat = [], []

    def ablegen(daten):
        if not daten:
            return ENDE
        start = len(sektoren)
        n = -(-len(daten) // SEKTOR)
        for j in range(n):
            sektoren.append(bytes(daten[j * SEKTOR:(j + 1) * SEKTOR]).ljust(SEKTOR, b"\x00"))
            fat.append(start + j + 1 if j < n - 1 else ENDE)
        return start

    for e in alle:
        if e.art == 2 and len(e.daten) >= GRENZE:
            e.start = ablegen(e.daten)
    wurzel.daten = bytes(mini)
    wurzel.start = ablegen(mini) if mini else ENDE
    mini_fat_start = ablegen(b"".join(struct.pack("<I", x) for x in mini_fat)) if mini_fat else ENDE
    mini_fat_n = -(-len(mini_fat) * 4 // SEKTOR) if mini_fat else 0
    verz = bytearray()
    for e in alle:
        name = e.name.encode("utf-16-le") + b"\x00\x00"
        groesse = len(e.daten) if e.art in (2, 5) else 0
        verz += (name.ljust(64, b"\x00") + struct.pack("<HBB", len(name), e.art, 1)
                 + struct.pack("<III", e.links, e.rechts, e.kind) + b"\x00" * 16 + b"\x00" * 4 + b"\x00" * 16
                 + struct.pack("<IQ", e.start if (e.art != 1) else 0, groesse))
    while len(verz) % SEKTOR:
        verz += (b"\x00" * 64 + struct.pack("<HBB", 0, 0, 0) + struct.pack("<III", FREI, FREI, FREI)
                 + b"\x00" * 36 + struct.pack("<IQ", 0, 0))
    verz_start = ablegen(verz)
    n_fat = 1
    while (len(sektoren) + n_fat) > n_fat * (SEKTOR // 4):
        n_fat += 1
    fat_start = len(sektoren)
    fat += [FAT_SEKTOR] * n_fat
    fat += [FREI] * (n_fat * SEKTOR // 4 - len(fat))
    fat_bytes = b"".join(struct.pack("<I", x) for x in fat)
    for j in range(n_fat):
        sektoren.append(fat_bytes[j * SEKTOR:(j + 1) * SEKTOR])
    difat = [fat_start + j for j in range(n_fat)] + [FREI] * (109 - n_fat)
    kopf = (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 16 + struct.pack("<HHHHH", 0x3E, 3, 0xFFFE, 9, 6)
            + b"\x00" * 6 + struct.pack("<IIIIIIIII", 0, n_fat, verz_start, 0, GRENZE, mini_fat_start, mini_fat_n,
                                        ENDE, 0)
            + b"".join(struct.pack("<I", x) for x in difat))
    return kopf + b"".join(sektoren)


def _filetime(d):
    utc = d.replace(tzinfo=datetime.timezone.utc) if d.tzinfo is None else d
    return int((utc - datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds() * 10 ** 7)


def _text(nr, wert):
    return f"__substg1.0_{nr:04X}001F", wert.encode("utf-16-le")


def _nachricht(betreff, text, absender_name, absender, datum, anhaenge, html=None, kopf=32, ansi=False):
    stroeme = {}
    if ansi:
        stroeme["__substg1.0_0037001E"] = betreff.encode("cp1252")
        stroeme["__substg1.0_1000001E"] = text.encode("cp1252")
    else:
        for nr, w in ((0x0037, betreff), (0x0C1A, absender_name), (0x5D01, absender), (0x0C1F, absender)):
            k, v = _text(nr, w)
            stroeme[k] = v
        if text is not None:
            k, v = _text(0x1000, text)
            stroeme[k] = v
    if html is not None:
        stroeme["__substg1.0_10130102"] = html.encode("utf-8")
    props = b"\x00" * kopf
    if datum:
        props += struct.pack("<IIQ", (0x0039 << 16) | 0x0040, 6, _filetime(datum))
    props += struct.pack("<IIQ", (0x3FFD << 16) | 0x0003, 6, 1252 if ansi else 65001)
    stroeme["__properties_version1.0"] = props
    for i, (name, daten) in enumerate(anhaenge):
        w = f"__attach_version1.0_#{i:08X}"
        stroeme[f"{w}/__properties_version1.0"] = b"\x00" * 8
        k, v = _text(0x3707, name)
        stroeme[f"{w}/{k}"] = v
        if isinstance(daten, dict):         # eingebettete Mail (weitergeleitet)
            innen = _nachricht(kopf=24, **daten)
            for p, inhalt in innen.items():
                stroeme[f"{w}/__substg1.0_3701000D/{p}"] = inhalt
        else:
            stroeme[f"{w}/__substg1.0_37010102"] = daten
    return stroeme


def msg(betreff="", text="", absender_name="", absender="", datum=None, anhaenge=(), html=None, ansi=False):
    """.msg-Datei als bytes. anhaenge: [(Name, bytes)] oder [(Name, dict wie die Argumente hier)] für eine
    weitergeleitete Mail; text=None und html: reine HTML-Mail; ansi: alte Outlook-Datei mit cp1252-Text."""
    return cfb(_nachricht(betreff, text, absender_name, absender, datum, list(anhaenge), html, ansi=ansi))


def eml(betreff="", text="", absender_name="", absender="", datum=None, anhaenge=(), html=None):
    m = EmailMessage()
    m["From"] = f"{absender_name} <{absender}>" if absender_name else absender
    m["To"] = "anfrage@laser.example"
    m["Subject"] = betreff
    if datum:
        from email.utils import format_datetime
        m["Date"] = format_datetime(datum.astimezone())
    if text is not None:
        m.set_content(text)
        if html:
            m.add_alternative(html, subtype="html")
    else:
        m.set_content(html or "", subtype="html")
    for name, daten in anhaenge:
        if isinstance(name, str) and name.lower().endswith(".eml") and isinstance(daten, EmailMessage):
            m.add_attachment(daten)
        else:
            m.add_attachment(daten, maintype="application", subtype="octet-stream", filename=name)
    return bytes(m)


def tnef(anhaenge, lang=True):
    """winmail.dat mit Anhängen [(Name, bytes)]: Titel als 8.3-Kurzname, langer Name in den MAPI-Eigenschaften
    (wie Outlook); lang=False: nur der Titel."""
    def attr(stufe, kennung, art, wert):
        return struct.pack("<BII", stufe, (art << 16) | kennung, len(wert)) + wert + struct.pack("<H", sum(wert) & 0xFFFF)
    out = struct.pack("<IH", 0x223E9F78, 0x0001)
    out += attr(1, 0x9006, 0x0006, b"\x00\x00\x00\x00")          # attTnefVersion (Nachricht)
    for name, daten in anhaenge:
        kurz = (name.split(".")[0][:6].upper() + "~1." + name.rsplit(".", 1)[-1][:3].upper()).encode("cp1252") + b"\0"
        out += attr(2, 0x9002, 0x0006, b"\x00" * 14)               # attAttachRendData
        out += attr(2, 0x8010, 0x0001, kurz)                        # attAttachTitle
        out += attr(2, 0x800F, 0x0006, daten)                       # attAttachData
        if lang:
            n = name.encode("utf-16-le") + b"\0\0"
            mapi = struct.pack("<I", 2)
            mapi += struct.pack("<HH", 0x0003, 0x0E21) + struct.pack("<I", 0)        # PidTagAttachNumber (PT_LONG)
            mapi += struct.pack("<HH", 0x001F, 0x3707) + struct.pack("<II", 1, len(n)) + n + b"\0" * (-len(n) % 4)
            out += attr(2, 0x9005, 0x0006, mapi)                    # attAttachment
    return out


def rtf_mela(rtf):
    """Unkomprimiertes RTF im Format von PidTagRtfCompressed ('MELA')."""
    return struct.pack("<IIII", len(rtf) + 12, len(rtf), 0x414C454D, 0) + rtf


def msg_rtf(betreff, rtf_stream, anhaenge=()):
    """.msg ohne Text und HTML, nur mit RTF-Strom (ältere Outlook-Versionen)."""
    stroeme = _nachricht(betreff, None, "Alt Kunde", "alt@kunde-alt.de", None, list(anhaenge))
    stroeme["__substg1.0_10090102"] = rtf_stream
    return cfb(stroeme)
