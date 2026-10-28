"""E-Mail einer Anfrage lesen (Patrick 28.10.2026: „Outlook-Datei auslesen“): aus Outlook gezogene .msg-Dateien
(Compound File, gelesen mit olefile) und .eml-Dateien (Standard-E-Mail). Ergebnis je Mail: Absender (Name und Adresse),
Datum, Betreff, Text (bei reinen HTML-Mails ohne Tags) und Anhänge. Weitergeleitete Mails im Anhang und ZIP-Archive
werden mit ausgepackt; deren Text hängt unten am Text an. Mails im RTF-Format ohne Text (selten, sehr alte Outlook-
Versionen) liefern nur Betreff und Anhänge. Ohne Qt."""
import datetime
import email
import email.message
import email.policy
import email.utils
import html
import io
import re
import struct
import zipfile
from pathlib import Path, PurePath

ENDUNGEN = {".msg", ".eml"}
TIEFE = 3                   # weitergeleitete Mails bzw. ZIP-Archive ineinander: so tief wird ausgepackt
ZIP_MAX = 200 * 2 ** 20     # größere entpackte ZIP-Inhalte werden übersprungen (Schutz vor ZIP-Bomben)

# MAPI-Eigenschaften (MS-OXPROPS) in .msg-Dateien
BETREFF, TEXT, HTML_TEXT = 0x0037, 0x1000, 0x1013
ABSENDER_NAME, ABSENDER_ADRESSE, ABSENDER_SMTP, ABSENDER_ART = 0x0C1A, 0x0C1F, 0x5D01, 0x0C1E
KOPFZEILEN, ZEICHENSATZ = 0x007D, 0x3FFD
GESENDET, ZUGESTELLT = 0x0039, 0x0E06
ANHANG_NAME_LANG, ANHANG_NAME, ANHANG_DATEN, ANHANG_ANZEIGE = 0x3707, 0x3704, 0x3701, 0x3001


class Mail:
    """Eine gelesene E-Mail: absender_name, absender (Adresse, klein), datum (datetime oder None), betreff, text,
    anhaenge [(Dateiname, bytes)]."""

    def __init__(self, absender_name="", absender="", datum=None, betreff="", text="", anhaenge=None):
        self.absender_name, self.absender = (absender_name or "").strip(), (absender or "").strip().lower()
        self.datum, self.betreff, self.text = datum, (betreff or "").strip(), text or ""
        self.anhaenge = list(anhaenge or [])

    @property
    def domain(self):
        return self.absender.rpartition("@")[2] if "@" in self.absender else ""

    def volltext(self):
        """Betreff und Text für die Auswertung (Anfrage-Nr., Stückzahlen …)."""
        return f"Betreff: {self.betreff}\n{self.text}" if self.betreff else self.text

    def __repr__(self):
        return f"Mail({self.betreff!r} von {self.absender!r}, {len(self.anhaenge)} Anhänge)"


def lesen(pfad):
    """Mail aus einer .msg- oder .eml-Datei. Ergebnis Mail oder None (keine Mail, kaputt oder nicht lesbar)."""
    pfad = Path(pfad)
    try:
        daten = pfad.read_bytes()
    except OSError:
        return None
    return aus_bytes(daten, pfad.suffix.lower())


def aus_bytes(daten, endung=".msg", tiefe=0):
    try:
        if daten[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":     # Compound File (Outlook), egal welche Endung
            m = _msg(daten)
        elif endung == ".msg":
            return None
        else:
            m = _eml(daten)
    except Exception:           # kaputte Datei: wie keine Mail
        return None
    if m is not None:
        _auspacken(m, tiefe)
    return m


def anhang_namen(pfad):
    """Nur die Namen der Anhänge (nach dem Auspacken), [] wenn nicht lesbar."""
    m = lesen(pfad)
    return [n for n, _ in m.anhaenge] if m else []


# ---------------------------------------------------------------- .msg (Outlook)

def _msg(daten):
    import olefile
    ole = olefile.OleFileIO(io.BytesIO(daten))
    try:
        return _msg_lesen(ole, [])
    finally:
        ole.close()


def _strom(ole, pfad):
    try:
        return ole.openstream(pfad).read() if ole.exists("/".join(pfad)) else None
    except OSError:
        return None


def _eigenschaft(ole, wurzel, nr, zeichensatz="cp1252"):
    """Text- oder Binärwert der Eigenschaft nr im Speicher wurzel (Liste der Pfadteile) oder None."""
    for art in ("001F", "001E", "0102"):
        roh = _strom(ole, wurzel + [f"__substg1.0_{nr:04X}{art}"])
        if roh is None:
            continue
        if art == "001F":
            return roh.decode("utf-16-le", "replace").rstrip("\x00")
        if art == "001E":
            return roh.decode(zeichensatz, "replace").rstrip("\x00")
        return roh
    return None


def _feste(ole, wurzel, kopf):
    """Feste Eigenschaften (Zahlen, Zeiten) aus __properties_version1.0: {nr: (art, 8 Bytes)}. kopf: Länge des Kopfes
    (32 Mail, 24 eingebettete Mail, 8 Anhang)."""
    roh = _strom(ole, wurzel + ["__properties_version1.0"]) or b""
    out = {}
    for i in range(kopf, len(roh) - 15, 16):
        tag, = struct.unpack_from("<I", roh, i)
        out[tag >> 16] = (tag & 0xFFFF, roh[i + 8:i + 16])
    return out


def _zeit(wert):
    """FILETIME (100 ns seit 1601) als lokale Uhrzeit ohne Zeitzone."""
    if not wert or wert[0] != 0x0040:
        return None
    n, = struct.unpack("<Q", wert[1])
    if not n:
        return None
    utc = datetime.datetime(1601, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(microseconds=n // 10)
    return utc.astimezone().replace(tzinfo=None)


def _zeichensatz(feste):
    w = feste.get(ZEICHENSATZ)
    if w and w[0] == 0x0003:
        cp, = struct.unpack_from("<I", w[1])
        name = {65001: "utf-8", 28591: "latin-1", 20127: "ascii"}.get(cp, f"cp{cp}")
        try:
            "".encode(name)
            return name
        except LookupError:
            pass
    return "cp1252"


def _msg_lesen(ole, wurzel):
    feste = _feste(ole, wurzel, 32 if not wurzel else 24)
    zs = _zeichensatz(feste)
    e = lambda nr: _eigenschaft(ole, wurzel, nr, zs)     # noqa: E731
    text = e(TEXT)
    if not isinstance(text, str) or not text.strip():
        h = e(HTML_TEXT)
        text = html_text(h.decode(_html_zeichensatz(h, zs), "replace") if isinstance(h, bytes) else h or "")
    adresse = e(ABSENDER_SMTP) or ""
    if not adresse or "@" not in str(adresse):
        a = e(ABSENDER_ADRESSE) or ""
        adresse = a if "@" in str(a) else ""
    kopf = e(KOPFZEILEN)
    datum = _zeit(feste.get(GESENDET)) or _zeit(feste.get(ZUGESTELLT))
    if isinstance(kopf, str) and kopf.strip():
        k = email.message_from_string(kopf, policy=email.policy.compat32)
        if not adresse:
            adresse = email.utils.parseaddr(k.get("From", ""))[1]
        if not datum:
            datum = _kopf_datum(k.get("Date"))
    m = Mail(str(e(ABSENDER_NAME) or ""), str(adresse or ""), datum, str(e(BETREFF) or ""), str(text or ""))
    for eintrag in sorted({tuple(p[:len(wurzel) + 1]) for p in ole.listdir(streams=True, storages=True)
                           if len(p) > len(wurzel) and p[:len(wurzel)] == wurzel
                           and p[len(wurzel)].startswith("__attach_version1.0_")}):
        _msg_anhang(ole, list(eintrag), m, zs)
    return m


def _msg_anhang(ole, wurzel, m, zs):
    e = lambda nr: _eigenschaft(ole, wurzel, nr, zs)     # noqa: E731
    name = e(ANHANG_NAME_LANG) or e(ANHANG_NAME) or e(ANHANG_ANZEIGE) or ""
    eingebettet = wurzel + ["__substg1.0_3701000D"]
    if ole.exists("/".join(eingebettet)) and ole.get_type("/".join(eingebettet)) == 1:     # weitergeleitete Mail
        m.anhaenge.append(("\x00msg", _msg_lesen(ole, eingebettet)))
        return
    daten = e(ANHANG_DATEN)
    if isinstance(daten, bytes) and str(name).strip():
        m.anhaenge.append((sauber(str(name)), daten))


# ---------------------------------------------------------------- .eml

def _eml(daten):
    nachricht = email.message_from_bytes(daten, policy=email.policy.default)
    if not any(nachricht.get(k) for k in ("From", "Subject", "Date", "To")):
        return None
    return _eml_lesen(nachricht)


def _eml_lesen(nachricht):
    name, adresse = email.utils.parseaddr(str(nachricht.get("From", "")))
    text = ""
    teil = nachricht.get_body(preferencelist=("plain", "html"))
    if teil is not None:
        try:
            inhalt = teil.get_content()
        except (LookupError, ValueError):
            inhalt = (teil.get_payload(decode=True) or b"").decode("latin-1", "replace")
        text = html_text(inhalt) if teil.get_content_type() == "text/html" else inhalt
    m = Mail(name, adresse, _kopf_datum(nachricht.get("Date")), str(nachricht.get("Subject", "")), text)
    for a in nachricht.iter_attachments():
        if a.get_content_type() == "message/rfc822":
            innen = a.get_payload()
            innen = innen[0] if isinstance(innen, list) and innen else innen
            if isinstance(innen, email.message.Message):
                m.anhaenge.append(("\x00msg", _eml_lesen(innen)))
            continue
        n = a.get_filename()
        daten = a.get_payload(decode=True)
        if n and isinstance(daten, bytes):
            m.anhaenge.append((sauber(n), daten))
    return m


def _kopf_datum(wert):
    try:
        d = email.utils.parsedate_to_datetime(str(wert)) if wert else None
    except (TypeError, ValueError, IndexError):
        return None
    return d.astimezone().replace(tzinfo=None) if d and d.tzinfo else d


# ---------------------------------------------------------------- Anhänge auspacken

def _auspacken(m, tiefe):
    """Weitergeleitete Mails, .msg/.eml- und ZIP-Anhänge auspacken: deren Anhänge kommen zu m.anhaenge, der Text der
    weitergeleiteten Mail unten an m.text."""
    neu = []
    for name, daten in m.anhaenge:
        innen = None
        if name == "\x00msg":
            innen = daten
            if tiefe < TIEFE:
                _auspacken(innen, tiefe + 1)
        elif Path(name).suffix.lower() in ENDUNGEN and tiefe < TIEFE:
            innen = aus_bytes(daten, Path(name).suffix.lower(), tiefe + 1)
            if innen is None:
                neu.append((name, daten))
        elif Path(name).suffix.lower() == ".zip" and tiefe < TIEFE:
            neu.extend(zip_inhalt(daten, tiefe))
        else:
            neu.append((name, daten))
        if innen is not None:
            von = " ".join(x for x in (innen.absender_name, f"<{innen.absender}>" if innen.absender else "") if x)
            m.text += f"\n\n----- Weitergeleitete Nachricht -----\nVon: {von}\nBetreff: {innen.betreff}\n{innen.text}"
            neu.extend(innen.anhaenge)
    m.anhaenge = neu


def zip_inhalt(daten, tiefe=0):
    """Dateien eines ZIP-Archivs [(Name ohne Ordner, bytes)]; Mails und ZIPs darin werden mit ausgepackt."""
    out = []
    try:
        z = zipfile.ZipFile(io.BytesIO(daten))
        summe = 0
        for info in z.infolist():
            if info.is_dir() or info.file_size > ZIP_MAX or summe + info.file_size > ZIP_MAX:
                continue
            name = sauber(_zip_name(info))
            if not name or name.startswith(("__MACOSX", "._")):
                continue
            summe += info.file_size
            inhalt = z.read(info)
            endung = Path(name).suffix.lower()
            if endung == ".zip" and tiefe + 1 < TIEFE:
                out.extend(zip_inhalt(inhalt, tiefe + 1))
            elif endung in ENDUNGEN and tiefe + 1 < TIEFE and (innen := aus_bytes(inhalt, endung, tiefe + 1)):
                out.extend(innen.anhaenge)
            else:
                out.append((name, inhalt))
    except (zipfile.BadZipFile, OSError, RuntimeError, ValueError, NotImplementedError):
        return out
    return out


def _zip_name(info):
    n = info.filename
    if not info.flag_bits & 0x800:      # ohne UTF-8-Kennung: Windows-Explorer schreibt cp437/cp850
        try:
            n = n.encode("cp437").decode("cp850")
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return PurePath(n.replace("\\", "/")).name


def sauber(name):
    """Dateiname ohne Pfad und ohne Zeichen, die Windows nicht erlaubt."""
    n = PurePath(str(name).replace("\\", "/")).name
    n = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", n).strip(" .")
    return n[:150]


# ---------------------------------------------------------------- HTML

def _html_zeichensatz(roh, vorgabe):
    m = re.search(rb'charset\s*=\s*["\']?([\w-]+)', roh[:2000], re.I)
    if m:
        name = m.group(1).decode("ascii", "ignore")
        try:
            "".encode(name)
            return name
        except LookupError:
            pass
    return vorgabe


def html_text(h):
    """HTML als Text: Zeilen bei Absätzen, Umbrüchen und Tabellenzeilen, Zellen mit Tab getrennt."""
    h = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", h or "")
    h = re.sub(r"(?is)<!--.*?-->", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d|table)>", "\n", h)
    h = re.sub(r"(?i)</t[dh]>", "\t", h)
    h = re.sub(r"(?s)<[^>]+>", "", h)
    h = html.unescape(h).replace("\xa0", " ")
    zeilen = [re.sub(r"[ \t]*\t[ \t]*", "\t", re.sub(r" {2,}", " ", z)).strip() for z in h.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(zeilen)).strip()


# ---------------------------------------------------------------- Anfrage auswerten (Kunde, Termin, Werkstoff)

# Domains von Freemail-Anbietern: dort sagt die Domain nichts über den Kunden (nur die genaue Adresse zählt)
FREEMAIL = {"gmail.com", "googlemail.com", "web.de", "gmx.de", "gmx.net", "gmx.at", "gmx.ch", "t-online.de",
            "outlook.com", "outlook.de", "hotmail.com", "hotmail.de", "live.com", "live.de", "yahoo.com", "yahoo.de",
            "icloud.com", "me.com", "aol.com", "freenet.de", "arcor.de", "mail.de", "posteo.de", "online.de",
            "1und1.de", "vodafone.de", "email.de", "protonmail.com", "proton.me"}
ADRESSE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}", re.I)


def _domain(adresse):
    return str(adresse or "").rpartition("@")[2].lower().strip()


def eigene_domains(texte):
    """Domains der eigenen Firma aus Briefkopf und Benutzer-E-Mail (zählen nie als Kunde)."""
    return {_domain(a) for t in texte if t for a in ADRESSE.findall(str(t))}


def adressen(m, eigene=()):
    """Absenderadressen in sinnvoller Reihenfolge, ohne eigene Domains: Absender, Absender weitergeleiteter Mails
    (stehen als „Von: … <adresse>“ im Text), dann Adressen in „Von:/From:“-Zeilen zitierter Mails."""
    out = []
    kandidaten = [m.absender] + [a for z in m.text.split("\n") if re.match(r"\s*(von|from)\s*:", z, re.I)
                                 for a in ADRESSE.findall(z)]
    for a in kandidaten:
        a = str(a or "").lower().strip()
        if a and "@" in a and _domain(a) not in eigene and a not in out:
            out.append(a)
    return out


def kunde(m, kunden, eigene=()):
    """(Kundennummer, wie) über die Absenderadresse: erst genau gleiche Adresse im Kundenstamm (Feld E-Mail, mehrere
    mit ; oder , getrennt), dann gleiche Domain (nicht bei Freemail). Passt eine Adresse zu mehreren Kunden, entscheidet
    das Programm nicht (None). Sonst (None, '')."""
    stamm = []
    for k in kunden or ():
        for a in ADRESSE.findall(str(k.get("email") or "")):
            stamm.append((a.lower(), k["kundennr"]))
    for a in adressen(m, eigene):
        genau = {nr for s, nr in stamm if s == a}
        if len(genau) == 1:
            return genau.pop(), f"Absender {a}"
        d = _domain(a)
        if d in FREEMAIL or genau:
            continue
        gleich = {nr for s, nr in stamm if _domain(s) == d}
        if len(gleich) == 1:
            return gleich.pop(), f"Domain @{d}"
    return None, ""


# Wunschtermin: nur in Sätzen über Lieferung/Bedarf (nicht „Angebot bis …“)
TERMIN_WORT = re.compile(r"liefer|termin|benötig|bedarf|fertig|anliefer|zustell|brauche|wunsch|deadline|delivery",
                         re.I)
KW = re.compile(r"\b(?:KW|Kalenderwoche)\s*(\d{1,2})(?:\s*[/.\-]\s*(\d{4}|\d{2}))?\b", re.I)
DATUM = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})?(?![\d])")


def _saetze(text):
    for zeile in (text or "").split("\n"):
        if zeile.lstrip().startswith(">"):          # zitierte Zeilen älterer Mails
            continue
        yield from re.split(r"(?<=[!?])\s+|(?<=[a-zäöüß)])\.\s+", zeile)


def termin(text, heute=None):
    """Wunschtermin aus dem Text: ('Kalenderwoche', '46/2026') bzw. ('Lieferdatum', '2026-11-20') und der gefundene
    Satz, oder (None, None, '') wenn keiner oder mehrere verschiedene genannt sind. Nur Sätze mit einem Wort wie
    Liefertermin, benötigt, Bedarf; Sätze über das Angebot selbst zählen nicht. Termine in der Vergangenheit fallen
    weg."""
    from .angebot import lieferzeit_wert
    from .stammdaten import KALENDERWOCHE, LIEFERDATUM
    heute = heute or datetime.date.today()
    gefunden = {}
    for s in _saetze(text):
        if not TERMIN_WORT.search(s) or re.search(r"\bangebot", s, re.I):
            continue
        for mk in KW.finditer(s):
            kw, j = int(mk.group(1)), mk.group(2)
            jahr = (2000 + int(j) if len(j) == 2 else int(j)) if j else heute.isocalendar()[0]
            if not j and heute.isocalendar()[1] - kw > 26:
                jahr += 1                   # „KW 2“ im Dezember: nächstes Jahr
            try:
                w = lieferzeit_wert(KALENDERWOCHE, f"{kw}/{jahr}")
            except ValueError:
                continue
            montag = datetime.date.fromisocalendar(jahr, kw, 1)
            if montag + datetime.timedelta(days=6) >= heute:
                gefunden.setdefault((KALENDERWOCHE, w), s.strip())
        for md in DATUM.finditer(KW.sub(" ", s)):
            t, mo, j = int(md.group(1)), int(md.group(2)), md.group(3)
            jahr = (2000 + int(j) if len(j) == 2 else int(j)) if j else heute.year
            try:
                d = datetime.date(jahr, mo, t)
            except ValueError:
                continue
            if not j and d < heute and (d.replace(year=d.year + 1) - heute).days <= 183:
                d = d.replace(year=d.year + 1)      # „15.01.“ im November: nächstes Jahr
            if heute <= d <= heute + datetime.timedelta(days=730):
                gefunden.setdefault((LIEFERDATUM, d.isoformat()), s.strip())
    if len(gefunden) != 1:
        return None, None, ""
    (art, wert), satz = next(iter(gefunden.items()))
    return art, wert, satz


# Kurzbezeichnungen im Text -> Werkstoff-Nr. (nur eindeutige)
WERKSTOFF_KURZ = {"v2a": "1.4301", "aisi304": "1.4301", "aisi316l": "1.4404", "aisi316ti": "1.4571"}
WERKSTOFF_TOKEN = re.compile(r"(?<![\w.])(1\.\d{4}|[SEP]\s?\d{3}[A-Z0-9+]*|E\s?\d{3}|(?:EN\s?)?AW[-\s]?\d{4}[A-Z]?"
                             r"|V2A|V4A|AISI\s?3\d{2}[A-Z]{0,2}|DX5\dD[+A-Z0-9]*|CuZn\d+|X\d+Cr[A-Za-z0-9-]+)(?![\w])",
                             re.I)


def _norm(t):
    return re.sub(r"[^0-9a-z.]+", "", str(t or "").lower())


def werkstoff(text, werkstoffe, vorgabe=None):
    """(Werkstoff-ID, gefundenes Wort, Kandidaten) aus dem Text: Wörter wie S235, S355J2H, 1.4301, V2A, AW-6060 mit
    Werkstoff-ID, Werkstoff und Werkstoff-Nr. der Stammdaten vergleichen. Eindeutig nur, wenn genau ein Werkstoff
    passt; passen mehrere und die Vorgabe (Importprofil/Einstellung) ist dabei, gilt die Vorgabe. Sonst (None, Wort,
    Kandidaten) – das Programm entscheidet nicht."""
    zeilen = [w for w in werkstoffe or () if w.get("werkstoff_id")]
    treffer, worte = [], []
    for mt in WERKSTOFF_TOKEN.finditer(text or ""):
        wort = mt.group(1)
        t = _norm(wort)
        t = _norm(WERKSTOFF_KURZ.get(t, t))
        passend = []
        for z in zeilen:
            namen = {_norm(z.get(n)) for n in ("werkstoff_id", "werkstoff", "werkstoff_nr")} - {""}
            namen |= {_norm(str(z.get("angebotstext") or "").split(" ")[0])} - {""}
            if t in namen or any(n.startswith(t) and not n[len(t):len(t) + 1].isdigit()
                                 and len(t) >= 4 and not t.startswith("1.") for n in namen):
                passend.append(z["werkstoff_id"])
        if passend:
            worte.append(wort)
            treffer.append(set(passend))
    if not treffer:
        return None, "", []
    alle = set().union(*treffer)
    if len(alle) == 1:
        return next(iter(alle)), worte[0], sorted(alle)
    if vorgabe and all(vorgabe in t for t in treffer):
        return vorgabe, worte[0], sorted(alle)
    return None, ", ".join(dict.fromkeys(worte)), sorted(alle)


def bemerkung(m):
    """Interne Bemerkung zum Angebot: 'E-Mail von Name <adresse> vom 28.10.2026 10:15: Betreff'."""
    von = " ".join(x for x in (m.absender_name, f"<{m.absender}>" if m.absender else "") if x)
    zeit = f" vom {m.datum.strftime('%d.%m.%Y %H:%M')}" if m.datum else ""
    return f"E-Mail{' von ' + von if von else ''}{zeit}" + (f": {m.betreff}" if m.betreff else "")
