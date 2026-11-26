"""Artikelnummer, Revision und Zusätze aus Datei- und Teilenamen (Patrick 25.11.2026, Master-Auftrag Outlook-Import).

Kunden schicken STEP-Dateien und Zeichnungen oft mit Anhängen an der Artikelnummer: „123456_A“, „123456_final“,
„123456_neu“, „123456_Bearbeitet“, „123456-02“, „123456_002“, „123456_REV02“, „123456 Rev_A“, „123456_V02“. Dieses
Modul trennt einheitlich (ein Ort statt eigener Regeln je Stelle):

zerlegen(name, bekannte=())   -> Teile(grund, revision, rev, zusatz, roh): grund = Grundartikelnummer, revision = der
                                 Revisionsanhang wie geschrieben („REV02“, „Rev_A“, „-02“), rev = sein Kern groß
                                 („02“, „A“), zusatz = Wörter wie final/neu/Bearbeitet.
schluessel(name)              Vergleichsform der Grundnummer (wie formular.ohne_zeichen).
zuordnen(nummern, dateien)    je Artikelnummer: Status eindeutig / mehrdeutig / nicht zugeordnet und die Datei(en).
rev_schluessel(rev)           Sortierung von Revisionen (Zahlen nach Wert, Buchstaben nach Alphabet).

Vorsicht bei reinen Zahlenanhängen: „4711-020“ ist selbst eine Artikelnummer. Ziffern- und Einzelbuchstaben-Anhänge
(-02, _002, _A) gelten deshalb nur als Revision, wenn die Grundnummer eindeutig ist: sie steht in bekannte (z. B. die
Artikelnummern aus PDF/Mail) oder ist eine lange Nummer (mind. 5 Ziffern, außer Trennern nur Ziffern). Ausdrückliche
Revisionen (Rev, Index, V, Version, Stand, Änderung) und Zusatzwörter gelten immer. Ohne Qt."""
import re
from collections import namedtuple
from pathlib import Path

Teile = namedtuple("Teile", "grund revision rev zusatz roh")

EINDEUTIG, MEHRDEUTIG, KEINE = "eindeutig", "mehrdeutig", "nicht zugeordnet"
STATUS_TEXT = {EINDEUTIG: "zugeordnet", MEHRDEUTIG: "mehrdeutig – bitte wählen", KEINE: "nicht zugeordnet"}

_ENDUNG = re.compile(r"\.(?:step|stp|igs|iges|pdf|dxf|dwg|tif|tiff|png|jpe?g|sat|x_t|ipt|sldprt|artube|bpf|tubx)$",
                     re.I)
_KOPIE = re.compile(r"(?:\s*[-_]\s*(?:kopie|copy)(?:\s*\(\d+\))?|\s+\(\d+\))$", re.I)
_ZUSATZ = re.compile(r"[\s_.-]+(final|endg(?:ü|ue)ltig|neu|new|bearbeitet|ge(?:ä|ae)ndert|korr(?:igiert)?|aktuell|"
                     r"alt|old|update|(?:ü|ue)berarbeitet|freigabe|freigegeben|fertig|ok)$", re.I)
_REV_WORT = re.compile(r"[\s_.(-]+((?:rev(?:ision)?|index|idx|ind|stand|(?:ä|ae)nderung|(?:ä|ae)nd)\.?[\s_.-]*"
                       r"([a-z]{1,2}\d{0,2}|\d{1,3}))\)?$", re.I)
_REV_V = re.compile(r"[\s_.(-]+((?:version|ver|v)\.?[\s_.-]*(\d{1,3}))\)?$", re.I)
_REV_ZAHL = re.compile(r"(?:_(\d{1,3})|-(\d{2}))$")             # „_002“, „_02“, „-02“ (nicht „-020“)
_REV_BUCHSTABE = re.compile(r"_([a-z])$", re.I)                  # „_A“


def ohne_zeichen(text):
    from .formular import ohne_zeichen as oz
    return oz(text)


def _stamm(name):
    s = Path(str(name or "")).name.strip()
    alt = None
    while s != alt:
        alt = s
        s = _ENDUNG.sub("", s).strip()
        s = _KOPIE.sub("", s).strip()
    return s


def _lange_nummer(s):
    """Klar eine Artikelnummer: mind. 5 Ziffern, außer Trennern (- _ . /) nur Ziffern."""
    return bool(re.fullmatch(r"\d[\d._/-]*\d", s or "")) and sum(c.isdigit() for c in s) >= 5


def zerlegen(name, bekannte=()):
    """Teile(grund, revision, rev, zusatz, roh) des Namens; ohne erkennbaren Anhang ist grund der Name (ohne Endung).
    bekannte: Artikelnummern aus PDF/Mail; steht eine davon am Anfang und folgt nur ein Trenner mit Anhang, ist sie die
    Grundnummer."""
    roh = _stamm(name)
    s, revision, rev, zusatz = roh, "", "", []
    bek = sorted({ohne_zeichen(b) for b in bekannte or () if len(ohne_zeichen(b)) >= 3}, key=len, reverse=True)
    for _ in range(4):          # mehrere Anhänge: „123456_REV02_final“
        if (m := _ZUSATZ.search(s)) and s[:m.start()].strip(" _.-"):
            zusatz.insert(0, m.group(1))
            s = s[:m.start()]
            continue
        if not revision:
            m = _REV_WORT.search(s) or _REV_V.search(s)
            if m and s[:m.start()].strip(" _.-"):
                revision, rev, s = m.group(1), m.group(2).upper(), s[:m.start()]
                continue
            vorn = None
            m = _REV_ZAHL.search(s) or _REV_BUCHSTABE.search(s)
            if m:
                vorn = s[:m.start()].strip(" _.-")
                if vorn and (_lange_nummer(vorn) or ohne_zeichen(vorn) in bek):
                    revision, rev, s = m.group(0).lstrip("_-"), next(g for g in m.groups() if g).upper(), vorn
                    continue
        break
    grund = s.strip(" _.-") or roh
    if bek and ohne_zeichen(grund) not in bek:       # bekannte Nummer am Anfang, Rest ein unbekannter Anhang
        k = ohne_zeichen(grund)
        for b in bek:
            if k.startswith(b) and _getrennt(grund, b):
                grund = _vorn(grund, b)
                break
    return Teile(grund, revision, rev, zusatz, roh)


def _getrennt(text, schl):
    """Endet schl (Vergleichsform) in text an einem Trenner (nicht mitten in einer Zahl/einem Wort)?"""
    vorn = _vorn(text, schl)
    rest = text[len(vorn):]
    return bool(vorn) and (not rest or rest[0] in " _.-(")


def _vorn(text, schl):
    """Kürzester Anfang von text, dessen Vergleichsform schl ist ('' wenn keiner)."""
    for i in range(1, len(text) + 1):
        if ohne_zeichen(text[:i]) == schl:
            return text[:i]
    return ""


def grund(name, bekannte=()):
    return zerlegen(name, bekannte).grund


def schluessel(name, bekannte=()):
    """Vergleichsform der Grundnummer („123456_REV02.step“ -> „123456“)."""
    return ohne_zeichen(zerlegen(name, bekannte).grund)


def rev_schluessel(r):
    """Sortierschlüssel einer Revision: ohne zuerst, dann Zahlen nach Wert, dann Buchstaben."""
    r = str(r or "").upper()
    if not r:
        return (0, 0, "")
    if r.isdigit():
        return (1, int(r), "")
    return (2, 0, r)


def zuordnen(nummern, dateien):
    """Artikelnummern (aus PDF/Mail) den Dateien zuordnen. Genau gleicher Name geht vor; sonst über die Grundnummer.
    Ergebnis {nummer: dict(status, dateien [Namen], datei (eindeutig bzw. neueste Revision als Vorschlag), revision)}.
    Mehrere Dateien zur selben Grundnummer: mehrdeutig (Auswahl bzw. Revisionsprüfung), nie still die falsche."""
    nummern = [str(n) for n in nummern or () if str(n or "").strip()]
    dateien = [str(d) for d in dateien or ()]
    teile = {d: zerlegen(d, nummern) for d in dateien}
    out = {}
    for n in nummern:
        k = ohne_zeichen(n)
        genau = [d for d in dateien if ohne_zeichen(teile[d].roh) == k]
        if len(genau) == 1:
            out[n] = dict(status=EINDEUTIG, dateien=genau, datei=genau[0], revision=teile[genau[0]].revision)
            continue
        kn = schluessel(n)
        passend = genau or [d for d in dateien if ohne_zeichen(teile[d].grund) in (k, kn)]
        if not passend:
            out[n] = dict(status=KEINE, dateien=[], datei="", revision="")
        elif len(passend) == 1:
            out[n] = dict(status=EINDEUTIG, dateien=passend, datei=passend[0], revision=teile[passend[0]].revision)
        else:
            neu = max(passend, key=lambda d: rev_schluessel(teile[d].rev))
            out[n] = dict(status=MEHRDEUTIG, dateien=passend, datei=neu, revision=teile[neu].revision)
    return out


_REV_IM_TEXT = re.compile(r"[\s_.(-]*(?:(?:rev(?:ision)?|index|idx|ind|stand|version|ver|v)\.?[\s_.-]*([a-z]{1,2}\d{0,2}|\d{1,3})"
                          r"|[_-](\d{1,3})(?![\d,.])|_([a-z])\b)\)?", re.I)


def im_text(grund_schl, zeile):
    """Steht die Grundnummer (Vergleichsform) frei in der Textzeile – nicht als Teil einer längeren Nummer? Ergebnis
    (Anfang, Ende inkl. Revisionsanhang, Revision groß oder '') bzw. None."""
    if len(grund_schl) < 3:
        return None
    muster = r"[\s_.\-/]*".join(re.escape(c) for c in grund_schl)
    for m in re.finditer(rf"(?<![0-9a-zäöüß]){muster}(?![0-9a-zäöüß])", zeile, re.I):
        ende, rev = m.end(), ""
        if (r := _REV_IM_TEXT.match(zeile, ende)) and r.group(0):
            ende, rev = r.end(), next((g for g in r.groups() if g), "").upper()
        return m.start(), ende, rev
    return None


def gruppen(dateien, bekannte=()):
    """{Grundschlüssel: [Dateien]} nur für Grundnummern mit mehreren Dateien (Revisionen/Varianten desselben Teils)."""
    je = {}
    for d in dateien or ():
        k = schluessel(d, bekannte)
        if len(k) >= 3:
            je.setdefault(k, []).append(d)
    return {k: v for k, v in je.items() if len(v) > 1}
