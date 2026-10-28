"""E-Mail einer Anfrage lesen (Patrick 28.10.2026: „Outlook-Datei auslesen“): aus Outlook gezogene .msg-Dateien
(Compound File, gelesen mit olefile) und .eml-Dateien (Standard-E-Mail). Ergebnis je Mail: Absender (Name und Adresse),
Datum, Betreff, Text (bei reinen HTML-Mails ohne Tags) und Anhänge. Weitergeleitete Mails im Anhang und ZIP-Archive
werden mit ausgepackt; deren Text hängt unten am Text an. Robust (Patrick 28.10.2026 „noch robuster“): Mails nur im
RTF-Format (komprimiertes RTF, auch mit eingebettetem HTML) werden entpackt, winmail.dat (TNEF, von Outlook an
andere Programme) wird ausgepackt, ein kaputter Anhang verdirbt nicht die ganze Mail, und eine Datei wird nur einmal
gelesen, solange sie sich nicht ändert. Ohne Qt."""
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
BETREFF, TEXT, HTML_TEXT, RTF_TEXT = 0x0037, 0x1000, 0x1013, 0x1009
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


_GELESEN = {}               # (Pfad, Größe, Änderungszeit) -> Mail: Liste, Auspacken und Auswerten lesen nur einmal
CACHE_MAX, CACHE_BIS = 8, 30 * 2 ** 20


def lesen(pfad):
    """Mail aus einer .msg- oder .eml-Datei. Ergebnis Mail oder None (keine Mail, kaputt oder nicht lesbar).
    Zwischengespeichert, solange sich die Datei nicht ändert (große Mails ab CACHE_BIS nicht)."""
    pfad = Path(pfad)
    try:
        st = pfad.stat()
        schl = (str(pfad), st.st_size, st.st_mtime_ns)
        if schl in _GELESEN:
            return _GELESEN[schl]
        daten = pfad.read_bytes()
    except OSError:
        return None
    m = aus_bytes(daten, pfad.suffix.lower())
    if st.st_size <= CACHE_BIS:
        if len(_GELESEN) >= CACHE_MAX:
            _GELESEN.pop(next(iter(_GELESEN)))
        _GELESEN[schl] = m
    return m


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
    if not text.strip():                # nur RTF (ältere Outlook-Versionen, Mails aus Word)
        roh = e(RTF_TEXT)
        if isinstance(roh, bytes):
            try:
                text = rtf_text(rtf_entpacken(roh))
            except Exception:
                text = ""
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
        try:
            _msg_anhang(ole, list(eintrag), m, zs)
        except Exception:           # kaputter Anhang: der Rest der Mail zählt trotzdem
            continue
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
        try:
            n = a.get_filename()
            daten = a.get_payload(decode=True)
        except Exception:           # kaputter Anhang: der Rest der Mail zählt trotzdem
            continue
        if a.get_content_type() == "application/ms-tnef" and not n:
            n = "winmail.dat"
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
        elif ist_tnef(name, daten):
            neu.extend(tnef_anhaenge(daten))
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
    if n.split(".")[0].upper() in WINDOWS_RESERVIERT:      # CON.step, PRN.pdf … lassen sich nicht anlegen
        n = "_" + n
    if len(n) > 150:                                        # Endung behalten
        stamm, punkt, endung = n.rpartition(".")
        n = (stamm[:140] + "." + endung[:9]) if punkt and len(endung) <= 9 else n[:150]
    return n


WINDOWS_RESERVIERT = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}


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


# Beginn älterer Nachrichten im Text (Antwort, Weiterleitung): darunter steht der Verlauf
VERLAUF = re.compile(r"^\s*(?:-{2,}\s*(?:Ursprüngliche Nachricht|Original Message|Weitergeleitete Nachricht|Forwarded "
                     r"message)|_{10,}\s*$|(?:Am|On)\s.{5,120}\s(?:schrieb|wrote)\s*.{0,80}:\s*$)", re.I | re.M)
VON_ZEILE = re.compile(r"^\s*(?:Von|From)\s*:.*\n(?:.*\n){0,3}?\s*(?:Gesendet|Sent|Datum|Date)\s*:", re.I | re.M)


def neuester_teil(text):
    """Nur die neueste Nachricht (bis zum ersten Zitat-/Weiterleitungskopf); ohne Kopf der ganze Text."""
    text = text or ""
    treffer = [m.start() for m in (VERLAUF.search(text), VON_ZEILE.search(text)) if m]
    return text[:min(treffer)] if treffer and min(treffer) > 0 else text


def termin(text, heute=None):
    """Wunschtermin aus dem Text: ('Kalenderwoche', '46/2026'), ('Lieferdatum', '2026-11-20'), ('Wochen', '3') bzw.
    ('Arbeitstage', '10') und der gefundene Satz, oder (None, None, '') wenn keiner oder mehrere verschiedene genannt
    sind. Nur Sätze mit einem Wort wie Liefertermin, benötigt, Bedarf; Sätze über das Angebot selbst zählen nicht.
    Termine in der Vergangenheit fallen weg. Die neueste Nachricht geht vor dem Verlauf darunter (ältere Termine
    im zitierten Verlauf zählen nur, wenn oben keiner steht)."""
    neu = neuester_teil(text)
    if neu != (text or ""):
        erg = _termin(neu, heute)
        if erg[0]:
            return erg
    return _termin(text, heute)


DAUER = re.compile(r"(?:in|innerhalb(?:\s+von)?|binnen|von|ca\.?|max\.?|maximal|spätestens\s+in)\s+(\d{1,3})\s*"
                   r"(Arbeitstag(?:en|e)?|Werktag(?:en|e)?|AT\b|Wochen?|Wo\.)", re.I)


def _termin(text, heute=None):
    from .angebot import lieferzeit_wert
    from .stammdaten import ARBEITSTAGE, KALENDERWOCHE, LIEFERDATUM, WOCHEN
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
        for mz in DAUER.finditer(s):            # „Lieferung in 3 Wochen“, „innerhalb von 10 Arbeitstagen“
            n, einheit = int(mz.group(1)), mz.group(2).lower()
            art = WOCHEN if einheit.startswith("wo") else ARBEITSTAGE
            if 1 <= n <= (52 if art == WOCHEN else 250):
                gefunden.setdefault((art, str(n)), s.strip())
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
    neu = neuester_teil(text)
    if neu != (text or ""):             # neueste Nachricht vor dem zitierten Verlauf
        erg = _werkstoff(neu, werkstoffe, vorgabe)
        if erg[1]:
            return erg
    return _werkstoff(text, werkstoffe, vorgabe)


def _werkstoff(text, werkstoffe, vorgabe=None):
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


def _kompakt(t):
    """Vergleichsform für Firmennamen: Kleinbuchstaben ohne Leer-/Sonderzeichen, Umlaute ausgeschrieben."""
    t = str(t or "").lower().translate(str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}))
    return re.sub(r"[^0-9a-z]+", "", t)


FIRMA_ZUSATZ = {"gmbh", "mbh", "ag", "kg", "co", "ohg", "ug", "ek", "gbr", "se", "www", "mail", "info", "de", "com",
                "eu", "net", "org", "at", "ch", "group", "gruppe"}


def kunde_aus_domain(m, kunden, eigene=()):
    """(Kundennummer, wie) wenn der Domainname der Absenderadresse zum Namen genau eines Kunden passt
    (krueger-metall.de -> „Metallbau Krüger GmbH“: alle Teile ab 4 Buchstaben stecken im Namen). Sonst (None, '')."""
    for a in adressen(m, eigene):
        d = _domain(a)
        if d in FREEMAIL:
            continue
        teile = [t for t in re.split(r"[.\-_]+", d.rsplit(".", 1)[0]) if len(t) >= 4 and t not in FIRMA_ZUSATZ]
        if not teile:
            continue
        passend = {k["kundennr"] for k in kunden or () if all(_kompakt(t) in _kompakt(k.get("name")) for t in teile)}
        if len(passend) == 1:
            return passend.pop(), f"Domain @{d} passt zum Namen"
    return None, ""


STAFFEL = re.compile(r"(?<![\d,.])(\d{1,6})((?:\s*(?:/|,|;|\+|und|bzw\.?|oder|sowie)\s*\d{1,6}){1,6})\s*"
                     r"(?:stk|stück|stck|st\.|pcs|teile)", re.I)


def staffel_mengen(text):
    """Mengen einer gewünschten Staffel („Preise für 10 / 50 / 100 Stk“) als aufsteigende Liste, sonst []. Das
    Programm legt Staffeln nie selbst an (Patrick 26.10.2026), es weist nur darauf hin."""
    for mt in STAFFEL.finditer(neuester_teil(text) or ""):
        zahlen = [int(mt.group(1))] + [int(z) for z in re.findall(r"\d{1,6}", mt.group(2))]
        if len(zahlen) >= 2 and zahlen == sorted(set(zahlen)) and zahlen[0] > 0:
            return zahlen
    return []


def zusatz_erwaehnt(text, namen):
    """Zusatzarbeiten (Namen aus dem Katalog), die im Text vorkommen: ein Wort ab 6 Buchstaben, dessen Anfang (7
    Buchstaben) im Namen steckt („verzinkt“ -> „Feuerverzinken“, „pulverbeschichtet“ -> „Pulverbeschichten“).
    Ergebnis [(Name, Wort)]."""
    worte = {w.lower() for w in re.findall(r"[A-Za-zÄÖÜäöüß]{6,}", neuester_teil(text) or "")}
    out = []
    for n in namen or ():
        kn = _kompakt(n)
        w = next((w for w in sorted(worte) if len(_kompakt(w)) >= 7 and _kompakt(w)[:7] in kn), None)
        if w:
            out.append((n, w))
    return out


def bemerkung(m):
    """Interne Bemerkung zum Angebot: 'E-Mail von Name <adresse> vom 28.10.2026 10:15: Betreff'."""
    von = " ".join(x for x in (m.absender_name, f"<{m.absender}>" if m.absender else "") if x)
    zeit = f" vom {m.datum.strftime('%d.%m.%Y %H:%M')}" if m.datum else ""
    return f"E-Mail{' von ' + von if von else ''}{zeit}" + (f": {m.betreff}" if m.betreff else "")


# ---------------------------------------------------------------- RTF (komprimiert, MS-OXRTFCP)

_RTF_VORGABE = (b"{\\rtf1\\ansi\\mac\\deff0\\deftab720{\\fonttbl;}{\\f0\\fnil \\froman \\fswiss \\fmodern \\fscript "
                b"\\fdecor MS Sans SerifSymbolArialTimes New RomanCourier{\\colortbl\\red0\\green0\\blue0\r\n\\par "
                b"\\pard\\plain\\f0\\fs20\\b\\i\\u\\tab\\tx")


def rtf_entpacken(roh):
    """Komprimiertes RTF (PidTagRtfCompressed, 'LZFu') bzw. unkomprimiert ('MELA') als bytes."""
    if len(roh) < 16:
        return b""
    groesse, roh_groesse, art = struct.unpack_from("<III", roh, 0)
    daten = roh[16:4 + groesse]
    if art == 0x414C454D:               # MELA: nicht komprimiert
        return bytes(daten[:roh_groesse])
    if art != 0x75465A4C:
        raise ValueError("kein komprimiertes RTF")
    buch = bytearray(4096)
    buch[:len(_RTF_VORGABE)] = _RTF_VORGABE
    schreib, out, i = len(_RTF_VORGABE), bytearray(), 0
    while i < len(daten):
        steuer = daten[i]
        i += 1
        for bit in range(8):
            if i >= len(daten):
                break
            if steuer >> bit & 1:
                if i + 1 >= len(daten):
                    return bytes(out)
                wort = daten[i] << 8 | daten[i + 1]
                i += 2
                start, laenge = wort >> 4, (wort & 0xF) + 2
                if start == schreib:            # Ende
                    return bytes(out)
                for k in range(laenge):
                    b = buch[(start + k) % 4096]
                    out.append(b)
                    buch[schreib] = b
                    schreib = (schreib + 1) % 4096
            else:
                b = daten[i]
                i += 1
                out.append(b)
                buch[schreib] = b
                schreib = (schreib + 1) % 4096
    return bytes(out[:roh_groesse] if roh_groesse else out)


_RTF_WEG = {"fonttbl", "colortbl", "stylesheet", "info", "pict", "object", "header", "footer", "listtable",
            "listoverridetable", "rsidtbl", "generator", "themedata", "datastore", "latentstyles", "xmlnstbl"}
_RTF_TOKEN = re.compile(rb"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\(.)|([{}])|([^\\{}\r\n]+)|[\r\n]+", re.S)


def rtf_text(rtf):
    """Text aus RTF; bei Outlook-HTML in RTF (\\fromhtml) das HTML (\\*\\htmltag) als Text."""
    if not rtf:
        return ""
    cp = "cp1252"
    m = re.search(rb"\\ansicpg(\d+)", rtf[:500])
    if m:
        try:
            "".encode(f"cp{int(m.group(1))}")
            cp = f"cp{int(m.group(1))}"
        except LookupError:
            pass
    html = b"\\fromhtml" in rtf[:500]
    out = []
    stapel, weg, roh, htmlrtf, ueber = [], False, False, False, 0
    tag_tiefe = None
    for t in _RTF_TOKEN.finditer(rtf):
        wort, zahl, hexz, zeichen, klammer, text = t.groups()
        if klammer == b"{":
            stapel.append((weg, tag_tiefe))
            continue
        if klammer == b"}":
            weg, tag_tiefe = stapel.pop() if stapel else (False, None)
            continue
        if zeichen == b"*":
            roh = True                  # \\* Ziel: unbekannt = weg (außer htmltag)
            continue
        if wort is not None:
            w = wort.decode("ascii")
            if roh:
                roh = False
                if w == "htmltag" and html:
                    tag_tiefe = len(stapel)
                    continue
                weg = True
                continue
            if w in _RTF_WEG:
                weg = True
            elif w == "htmlrtf":
                htmlrtf = zahl != b"0"
            elif weg or (html and htmlrtf and tag_tiefe is None):
                pass
            elif w in ("par", "line", "row") and not html:
                out.append("\n")
            elif w == "tab" and not html:
                out.append("\t")
            elif w == "cell" and not html:
                out.append("\t")
            elif w == "u" and zahl:
                n = int(zahl)
                out.append(chr(n + 65536 if n < 0 else n))
                ueber = 1
            continue
        if weg or (html and htmlrtf and tag_tiefe is None):
            continue
        if hexz is not None:
            if ueber:
                ueber -= 1
                continue
            out.append(bytes([int(hexz, 16)]).decode(cp, "replace"))
        elif zeichen is not None:
            out.append({b"~": "\xa0", b"-": "", b"_": "-"}.get(zeichen, zeichen.decode("latin-1")))
        elif text is not None:
            if ueber:
                text, ueber = text[1:], 0
            out.append(text.decode(cp, "replace"))
    ergebnis = "".join(out)
    return html_text(ergebnis) if html else re.sub(r"\n{3,}", "\n\n", ergebnis).strip()


# ---------------------------------------------------------------- winmail.dat (TNEF)

TNEF_SIGNATUR = 0x223E9F78


def ist_tnef(name, daten):
    return (name.lower() in ("winmail.dat", "win.dat") or name.lower().endswith(".tnef")) and len(daten) > 6 \
        and struct.unpack_from("<I", daten, 0)[0] == TNEF_SIGNATUR


def tnef_anhaenge(daten):
    """Anhänge aus einer winmail.dat [(Name, bytes)]; langer Dateiname aus den MAPI-Eigenschaften, sonst der Titel."""
    out, aktuell, i = [], None, 6
    while i + 9 <= len(daten):
        stufe = daten[i]
        attr, laenge = struct.unpack_from("<II", daten, i + 1)
        wert = daten[i + 9:i + 9 + laenge]
        i += 9 + laenge + 2
        if stufe != 2:
            continue
        kennung = attr & 0xFFFF
        if kennung == 0x9002:           # attAttachRendData: neuer Anhang
            aktuell = dict(name="", daten=None)
            out.append(aktuell)
        elif aktuell is None:
            continue
        elif kennung == 0x8010:         # attAttachTitle
            aktuell["name"] = aktuell["name"] or wert.split(b"\0")[0].decode("cp1252", "replace")
        elif kennung == 0x800F:         # attAttachData
            aktuell["daten"] = bytes(wert)
        elif kennung == 0x9005:         # attAttachment: MAPI-Eigenschaften
            lang = _tnef_langname(wert)
            if lang:
                aktuell["name"] = lang
    return [(sauber(a["name"]), a["daten"]) for a in out if a["daten"] is not None and a["name"].strip()]


def _tnef_langname(wert):
    """PidTagAttachLongFilename (0x3707) aus einem TNEF-MAPI-Block oder None."""
    try:
        anzahl, = struct.unpack_from("<I", wert, 0)
        i = 4
        for _ in range(anzahl):
            art, nr = struct.unpack_from("<HH", wert, i)
            i += 4
            if nr >= 0x8000:            # benannte Eigenschaft
                i += 16
                sorte, = struct.unpack_from("<I", wert, i)
                i += 4
                if sorte == 0:
                    i += 4
                else:
                    n, = struct.unpack_from("<I", wert, i)
                    i += 4 + n + (-n % 4)
            mehr = bool(art & 0x1000)
            art &= 0x0FFF
            werte = struct.unpack_from("<I", wert, i)[0] if mehr or art in (0x001E, 0x001F, 0x0102, 0x000D) else 1
            if mehr or art in (0x001E, 0x001F, 0x0102, 0x000D):
                i += 4
            for _w in range(werte):
                if art in (0x001E, 0x001F, 0x0102, 0x000D):
                    n, = struct.unpack_from("<I", wert, i)
                    roh = wert[i + 4:i + 4 + n]
                    i += 4 + n + (-n % 4)
                    if nr == 0x3707 and art in (0x001E, 0x001F):
                        return (roh.decode("utf-16-le") if art == 0x001F else roh.decode("cp1252")).rstrip("\0")
                elif art in (0x0014, 0x0005, 0x0007, 0x0040, 0x0006):
                    i += 8
                elif art == 0x0048:
                    i += 16
                else:
                    i += 4
    except (struct.error, UnicodeDecodeError):
        return None
    return None


# ---------------------------------------------------------------- neuer Kunde aus Signatur/Formular (28.10.2026)

GRUSS = re.compile(r"^\s*(?:mit\s+freundlichen\s+gr(?:ü|ue)(?:ß|ss)en|freundliche\s+gr(?:ü|ue)(?:ß|ss)e|viele\s+gr(?:ü|ue)"
                   r"(?:ß|ss)e|beste\s+gr(?:ü|ue)(?:ß|ss)e|(?:mfg|vg|lg|bg)\b|gru(?:ß|ss)|best\s+regards|kind\s+regards|"
                   r"regards)", re.I | re.M)
FIRMA = re.compile(r"\b(?:GmbH|mbH|AG|KG|OHG|UG|GbR|e\.\s?K\.|SE|Co\.|Ltd\.?|S\.?r\.?l\.?|B\.?V\.?|Sp\.\s?z\s?o\.?o\.?)"
                   r"(?=\W|$)")
TELEFON = re.compile(r"(?:^|\s)(?:Tel(?:efon)?|Fon|Phone|T|Mobil|Handy)\.?\s*[:.]?\s*(\+?[\d][\d \t/()\-.]{5,}\d)", re.I)
PLZ_ORT = re.compile(r"(?:^|,\s*|\s{2,})(?:(?:D|DE)\s*-\s*)?(\d{5})\s+([A-ZÄÖÜ][\wäöüß.\- ]{1,40}?)\s*$", re.M)
STRASSE = re.compile(r"^\s*([A-ZÄÖÜ][\wäöüß.\- ]{2,40}?(?:str\.|straße|strasse|weg|platz|allee|ring|gasse|damm|ufer|"
                     r"chaussee|park|feld|hof|berg|[A-ZÄÖÜ][\wäöüß]+)\s+\d{1,4}\s?[a-zA-Z]?(?:\s?-\s?\d{1,4})?)\s*"
                     r"(?:,|$)", re.M)


def _signatur(text):
    """Bereich der Signatur: nach dem letzten Gruß der neuesten Nachricht, sonst deren letzte 15 Zeilen."""
    neu = neuester_teil(text)
    treffer = list(GRUSS.finditer(neu))
    if treffer:
        return neu[treffer[-1].start():]
    return "\n".join(neu.strip().split("\n")[-15:])


def _absender_text(m, eigene):
    """Text der Nachricht des Kunden: bei einer weitergeleiteten Mail (Absender aus der eigenen Firma) der Teil
    nach „Weitergeleitete Nachricht“, sonst die ganze Mail."""
    if _domain(m.absender) in eigene:
        for marke in ("----- Weitergeleitete Nachricht -----", "-----Ursprüngliche Nachricht-----",
                      "-------- Original Message --------"):
            if marke in m.text:
                return m.text.split(marke, 1)[1]
    return m.text


def kunde_daten(m, formular_text="", eigene=()):
    """Stammdaten für einen neuen Kunden aus Absender, Signatur und Kopf des Anfrageformulars: dict mit name,
    ansprechpartner, email, telefon, strasse, plz_ort, plz, land (nur gefundene). Firmenname: eine Zeile mit
    Rechtsform (GmbH, AG, KG …) in Signatur oder Formular, sonst aus der Domain; ohne Absender außerhalb der eigenen
    Firma None."""
    adr = adressen(m, eigene) if m else []
    if not adr and not formular_text:
        return None
    teile = [_signatur(_absender_text(m, eigene)) if m else "", "\n".join((formular_text or "").split("\n")[:30])]
    out = {}
    if adr:
        out["email"] = adr[0]
    person = (m.absender_name if m and _domain(m.absender) not in eigene else "") or ""
    if not person and m and adr:            # weitergeleitet: Name aus „Von: Name <adresse>“
        z = re.search(rf"(?:Von|From)\s*:\s*\"?([^<\"\n]+?)\"?\s*<{re.escape(adr[0])}>", m.text, re.I)
        person = z.group(1).strip() if z else ""
    if person and "@" not in person:
        out["ansprechpartner"] = person
    for t in teile:
        t = re.sub(r"\s+[|•·]\s+", "\n", t)                       # Signatur in einer Zeile: „Firma | Straße | …“
        t = re.sub(r",\s*(?=(?:D-|DE-)?\d{5}\s)", "\n", t)            # „Hauptstr. 5, 12345 Berlin“
        for z in t.split("\n"):
            z = z.strip(" \t|•·-")
            if "name" not in out and FIRMA.search(z) and len(z) <= 80 and "@" not in z:
                out["name"] = re.split(r"\s{2,}|\s[|•·]\s|,\s(?=\D)", z)[0].strip()
        if "telefon" not in out and (mt := TELEFON.search(t)):
            out["telefon"] = re.sub(r"\s+", " ", mt.group(1)).strip()
        if "plz_ort" not in out and (mp := PLZ_ORT.search(t)):
            out.update(plz=mp.group(1), plz_ort=f"{mp.group(1)} {mp.group(2).strip()}", land="DE")
            vorher = t[:mp.start() + 1]
            ms = list(STRASSE.finditer(vorher)) or list(STRASSE.finditer(t[mp.start():mp.end()]))
            if not ms:
                zeile = t[max(0, t.rfind("\n", 0, mp.start()) + 1):mp.end()]
                ms = list(STRASSE.finditer(zeile.split(",")[0])) if "," in zeile else []
            if ms:
                out["strasse"] = ms[-1].group(1).strip()
    if "name" not in out and adr and _domain(adr[0]) not in FREEMAIL:
        teile_d = [t for t in re.split(r"[.\-_]+", _domain(adr[0]).rsplit(".", 1)[0]) if t not in FIRMA_ZUSATZ]
        if teile_d:
            out["name"] = " ".join(t.capitalize() for t in teile_d)
    if "name" not in out and out.get("ansprechpartner"):
        out["name"] = out["ansprechpartner"]
    return out if out.get("name") else None


def neue_kundennr(vorhandene):
    """Nächste freie Kundennummer: höchste Nummer mit Ziffern am Ende + 1 (Vorsilbe und Stellen bleiben), sonst
    '10001'."""
    beste = None
    for nr in vorhandene:
        mt = re.fullmatch(r"(.*?)(\d+)", str(nr or "").strip())
        if mt and (beste is None or int(mt.group(2)) > int(beste.group(2))):
            beste = mt
    vorh = {str(n) for n in vorhandene}
    if not beste:
        nr = 10001
        while str(nr) in vorh:
            nr += 1
        return str(nr)
    n = int(beste.group(2)) + 1
    while (neu := f"{beste.group(1)}{str(n).zfill(len(beste.group(2)))}") in vorh:
        n += 1
    return neu
