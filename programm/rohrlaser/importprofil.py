"""STEP-Import je Kunde: Artikelnummer aus Bauteilnamen, Normteile, Vorgaben des Prüfdialogs (Importprofile).

Die Messung liefert je Körper den Bauteilnamen aus der Konstruktion (Spalte bauteil, ab STEP-JSON 1.13). benennen()
setzt daraus Artikel und Bezeichnung, normteile() markiert Normteile (_normteil: im Prüfdialog abgewählt). Ein
Importprofil (Tabelle importprofile, je Kunde) ändert Benennung, Muster, Normteil-Begriffe und die Vorgaben
Werkstoff, flache Teile und Anbauteile; leere Felder = Einstellungen.
"""
import re

from .stammdaten import BENENNUNGEN


def fuer_kunde(db, kundennr):
    """Importprofil des Kunden oder None."""
    if not kundennr:
        return None
    return next((z for z in db.zeilen("importprofile") if str(z.get("kundennr")) == str(kundennr)), None)


def begriffe(text):
    return [b.strip() for b in re.split(r"[;\n]", text or "") if b.strip()]


def normteil(name, liste):
    """Erster Begriff aus liste, der als eigenes Wort im Namen steht (Groß-/Kleinschreibung egal), sonst None."""
    for b in liste:
        if re.search(r"(?<![0-9A-Za-zÄÖÜäöüß])" + re.escape(b) + r"(?![A-Za-zÄÖÜäöüß])", name or "", re.IGNORECASE):
            return b
    return None


# Was CAD-Systeme an Namen und Dateinamen hängen und nie zur Artikelnummer gehört (Thread Artikelnummer, 28.10.2026)
_ENDUNG = re.compile(r"\.(sldprt|sldasm|ipt|iam|prt|asm|par|psm|catpart|catproduct|stp|step|x_t|x_b|sat|f3d|ifc|"
                     r"dwg|dxf)$", re.IGNORECASE)
_INSTANZ = re.compile(r"(?::\d+|<\d+>)$")                         # Inventor „Rohr:1“, SolidWorks „Teil1<1>“
_KOPIE_VORN = re.compile(r"^(?:kopie\s*(?:\(\d+\)\s*)?von|copy\s*(?:\(\d+\)\s*)?of)\s+", re.IGNORECASE)
_KOPIE_HINTEN = re.compile(r"(?:\s*[-_]\s*(?:kopie|copy)(?:\s*\(\d+\))?|[_ ]kopie\d*|\s+\(\d+\))$", re.IGNORECASE)
# Standardnamen der CAD-Systeme (Teil1, Part1, Body1, PRT0001, OpenCascade COMPOUND …): kein Name, dann der Dateiname
_STANDARD = re.compile(r"^(?:bauteil|teil|part|body|k(?:ö|oe)rper|volumenk(?:ö|oe)rper|solid|component|komponente|"
                       r"baugruppe|assembly|unbenannt|unnamed|untitled|prt|asm|feature|part__feature)\s*[-_]?\s*"
                       r"\d*$|^(?:compound|solid|shell|compsolid|face)$", re.IGNORECASE)
# Revision am Ende (F2 a): „4711-020_Rev B“, „4711 Rev.03“, „4711_v2“, „4711 Index C“, „4711-Idx.B“, „4711 Stand 3“
_REVISION = re.compile(r"[\s_-]+((?:rev(?:ision)?|index|idx|ind|stand)\.?\s*[_-]?\s*[A-Za-z0-9]{1,3}|"
                       r"(?:version|ver|v)\.?\s*[_-]?\s*\d{1,3})$", re.IGNORECASE)
# Nummer im Namen (F3 a): mind. 4 Ziffern (auch mit - . /), frei stehend, nicht nach Norm-Wörtern, keine Abmessung
_NUMMER = re.compile(r"(?<![\w.,/×*-])(\d[\d./-]*\d)(?![\w.,/×*]|-\w)")
_NORM_DAVOR = re.compile(r"(?:iso|din|en|nr\.?\s*din|ral|zchn\.?)\s*$", re.IGNORECASE)


def bereinigt(name):
    """Name ohne Dateiendung, Instanzzusatz des CAD und Kopie-Zusätze (Kopie von …, … - Kopie, … (1))."""
    alt = None
    name = (name or "").strip()
    while name != alt:
        alt = name
        name = _ENDUNG.sub("", name).strip()
        name = _INSTANZ.sub("", name).strip()
        name = _KOPIE_VORN.sub("", name).strip()
        name = _KOPIE_HINTEN.sub("", name).strip()
    return name or (alt or "").strip()


def standardname(name):
    """True, wenn der Name nur ein Standardname des CAD-Systems ist (Teil1, Part1, Body1, PRT0001, COMPOUND …)."""
    return bool(_STANDARD.match((name or "").strip()))


def revision(name):
    """(Name ohne Revision, Revision oder "") – „4711-020_Rev B“ -> („4711-020“, „Rev B“)."""
    t = _REVISION.search(name or "")
    if not t or not name[:t.start()].strip():
        return name, ""
    return name[:t.start()].strip(" _-"), t.group(1).strip()


def nummer_im_namen(name):
    """Artikelnummer, die in einem längeren Namen steht („Strebe links 4711-020“ -> „4711-020“), oder "". Nur wenn
    es genau eine solche Ziffernfolge gibt (mind. 4 Ziffern, nicht nach ISO/DIN/EN, keine Abmessung wie 40x40x2)."""
    treffer = []
    for t in _NUMMER.finditer(name or ""):
        z = t.group(1)
        if sum(c.isdigit() for c in z) < 4 or _NORM_DAVOR.search(name[:t.start()]) or re.fullmatch(r"\d\.\d{4}", z):
            continue                # Werkstoffnummer 1.4301 ist keine Artikelnummer
        treffer.append(z)
    if len(treffer) != 1 or treffer[0] == (name or "").strip():
        return ""
    return treffer[0]


def _text(s):
    """Zeichenkette aus der STEP-Datei: '' = ', \\X2\\…\\X0\\ (UTF-16), \\X\\hh (Latin-1), \\S\\c."""
    s = s.replace("''", "'")
    s = re.sub(r"\\X2\\((?:[0-9A-Fa-f]{4})+)\\X0\\",
               lambda t: bytes.fromhex(t.group(1)).decode("utf-16-be", "replace"), s)
    s = re.sub(r"\\X\\([0-9A-Fa-f]{2})", lambda t: bytes.fromhex(t.group(1)).decode("latin-1"), s)
    return re.sub(r"\\S\\(.)", lambda t: chr(ord(t.group(1)) + 128), s)


_PRODUKTE = {}      # (Pfad, Änderungszeit, Größe) -> {Name: Teilenummer}
_PRODUKT = re.compile(rb"(?<![A-Z_])PRODUCT\s*\(\s*'((?:[^']|'')*)'\s*,\s*'((?:[^']|'')*)'")


def teilenummern(pfad):
    """Teilenummern der STEP-Datei (F1 a): PRODUCT('Teilenummer', 'Benennung', …). OpenCascade liefert als
    Bauteilnamen die Benennung (leer: die Teilenummer); Ergebnis {Benennung: Teilenummer} nur, wo beide verschieden
    sind und die Benennung genau eine Teilenummer hat. Unlesbar oder ohne Datei: {}."""
    import os
    if not pfad:
        return {}
    try:
        st = os.stat(pfad)
    except OSError:
        return {}
    schl = (str(pfad), st.st_mtime_ns, st.st_size)
    if schl not in _PRODUKTE:
        import mmap
        out = {}
        nummern = {}
        try:           # über mmap durchsuchen: große STEP-Dateien (100 MB und mehr) nicht ganz in den Speicher lesen
            with open(pfad, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as daten:
                treffer = [(t.group(1), t.group(2)) for t in _PRODUKT.finditer(daten)]
        except (OSError, ValueError):       # ValueError: leere Datei
            treffer = []
        for t in treffer:
            def dec(b):
                try:
                    return _text(b.decode("utf-8"))
                except UnicodeDecodeError:
                    return _text(b.decode("latin-1"))
            nr, name = dec(t[0]).strip(), dec(t[1]).strip()
            nummern.setdefault(name or nr, set()).add(nr)
        for name, nrn in nummern.items():
            nr = next(iter(nrn)) if len(nrn) == 1 else ""
            if nr and nr != name and not standardname(bereinigt(nr)) and not re.fullmatch(r"[0-9A-Fa-f-]{16,}", nr):
                out[name] = nr
        _PRODUKTE[schl] = out
    return _PRODUKTE[schl]


def _datei_artikel(bisher):
    """Artikel aus dem Dateinamen (Messung: Datei bzw. Datei-K2) bereinigt, der Körperzusatz -K2 bleibt."""
    t = re.match(r"^(.*?)(-K\d+)?$", str(bisher or ""))
    return (bereinigt(t.group(1)) + (t.group(2) or "")) if t.group(1) else str(bisher or "")


def bestimmen(m, benennung, muster=""):
    """Artikelnummer eines Körpers aus der STEP-Datei. Rangfolge (Patrick 28.10.2026, alle a): Teilenummer der STEP
    (PRODUCT-ID, F1) > Muster des Importprofils > Bauteilname (Nummer darin automatisch, F3) > Dateiname. Namen
    werden bereinigt (Endung, CAD-Zusatz :1/<1>, Kopie), die Revision abgetrennt (F2), ein CAD-Standardname (Teil1,
    Part1 …) gilt wie kein Name. Ergebnis dict(artikel, bezeichnung (oder None), herkunft (Text), unsicher (bool))."""
    roh = (m.get("bauteil") or "").strip()
    name = bereinigt(roh)
    t = re.match(r"^(.*?)(-K\d+)?$", str(m.get("artikel") or ""))
    datei_nr, datei_rev = revision(bereinigt(t.group(1))) if t.group(1) else (str(m.get("artikel") or ""), "")
    bisher = datei_nr + (t.group(2) or "") if t.group(1) else datei_nr
    notiz = []
    if roh and roh != name:
        notiz.append(f"bereinigt aus „{roh}“")
    standard = standardname(name)
    if standard or not name or benennung == BENENNUNGEN[1]:
        herkunft = "Dateiname"
        if standard and benennung != BENENNUNGEN[1]:
            herkunft += f" (Bauteilname „{name}“ ist ein CAD-Standardname)"
        if datei_rev:
            notiz.append(f"Revision „{datei_rev}“ abgetrennt")
        return dict(artikel=bisher, bezeichnung=bereinigt(t.group(1)) if datei_rev else None,
                    herkunft="; ".join([herkunft] + notiz),
                    unsicher=bool(standard and benennung != BENENNUNGEN[1]))
    nummer, bezeichnung, unsicher = name, None, False
    herkunft = "Bauteilname"
    tn = teilenummern(m.get("_pfad")).get(roh) or teilenummern(m.get("_pfad")).get(name)
    gefunden = False
    if tn:
        nummer, bezeichnung, herkunft = bereinigt(tn), name, "Teilenummer der STEP-Datei"
    elif muster:
        try:
            treffer = re.search(muster, name)
        except re.error:
            treffer = None
        if treffer:
            nummer = (treffer.group(1) if treffer.groups() and treffer.group(1) else treffer.group(0)).strip()
            bezeichnung = name if nummer != name else None
            herkunft, gefunden = "Muster des Importprofils", True
    nummer, rev = revision(nummer)
    if rev:
        notiz.append(f"Revision „{rev}“ abgetrennt")
        bezeichnung = bezeichnung or name
    if not tn and not gefunden:
        im = nummer_im_namen(nummer)
        if im:
            bezeichnung, nummer, unsicher = name, im, True
            herkunft = f"Nummer im Bauteilnamen „{name}“ erkannt"
    if benennung == BENENNUNGEN[2]:
        from pathlib import Path
        nummer = f"{revision(bereinigt(Path(str(m.get('datei') or '')).stem))[0]}-{nummer}"
        herkunft = "Dateiname + " + herkunft
    return dict(artikel=nummer or bisher, bezeichnung=bezeichnung, herkunft="; ".join([herkunft] + notiz),
                unsicher=unsicher)


def artikel_aus(m, benennung, muster=""):
    """(Artikel, Bezeichnung oder None) eines Körpers nach der Benennung (bestimmen)."""
    b = bestimmen(m, benennung, muster)
    return b["artikel"], b["bezeichnung"]


def anwenden(messwerte, profil=None, einstellungen=None):
    """Benennung und Normteile auf die Messwerte anwenden (vor dem Prüfdialog). einstellungen: {step_benennung,
    step_normteile}. Je Körper _artikel_herkunft (Text für den Prüfdialog) und _artikel_unsicher (gelb); eine im
    Prüfdialog geänderte Nummer (_artikel_hand) bleibt. Ergebnis: Anzahl erkannter Normteile."""
    e = einstellungen or {}
    p = profil or {}
    benennung = p.get("benennung") or e.get("step_benennung") or BENENNUNGEN[0]
    liste = begriffe(e.get("step_normteile")) + begriffe(p.get("normteile"))
    n = 0
    for m in messwerte:
        if m.get("fehler"):
            continue
        if "_artikel_gemessen" not in m:
            m["_artikel_gemessen"] = m.get("artikel") or ""
        if not m.get("_artikel_hand"):
            m["artikel"] = m["_artikel_gemessen"]
            b = bestimmen(m, benennung, p.get("muster") or "")
            m["artikel"] = b["artikel"]
            m["_artikel_herkunft"], m["_artikel_unsicher"] = b["herkunft"], b["unsicher"]
            m.pop("_bezeichnung", None)
            if b["bezeichnung"]:
                m["_bezeichnung"] = b["bezeichnung"]
        b = normteil(m.get("bauteil"), liste)
        if b:
            m["_normteil"] = b
            n += 1
        else:
            m.pop("_normteil", None)
    from .step import eindeutige_artikel       # Bauteilname mehrfach vergeben: -2, -3 … (sonst nur einer übernommen)
    gueltig = [m for m in messwerte if not m.get("fehler")]
    vorher = [m.get("artikel") for m in gueltig]
    eindeutige_artikel(gueltig)
    for m, alt in zip(gueltig, vorher):
        if m.get("artikel") != alt and not m.get("_artikel_hand"):
            m["_artikel_herkunft"] = (m.get("_artikel_herkunft") or "") + \
                f"; Zusatz „{str(m['artikel'])[len(str(alt)):]}“: „{alt}“ gehört schon zu einem anderen Teil"
            m["_artikel_unsicher"] = True
    return n


def vorgaben(profil):
    """Vorgaben des Profils für den Import: dict mit werkstoff, flach_als, anbau_weglassen (nur gesetzte)."""
    p = profil or {}
    out = {}
    if p.get("werkstoff_id"):
        out["werkstoff"] = p["werkstoff_id"]
    if p.get("flach_als"):
        out["flach_als"] = p["flach_als"]
    if p.get("anbau_weglassen") in ("ja", "nein"):
        out["anbau_weglassen"] = p["anbau_weglassen"] == "ja"
    if begriffe(p.get("zusatz")):
        out["zusatz"] = begriffe(p.get("zusatz"))
    return out


def korrekturen(messwerte, start, werkstoff_vorgabe, anbau_start=None, anbau_jetzt=None, zusatz_vorgabe=None):
    """Was im Prüfdialog korrigiert wurde und sich als Importprofil des Kunden merken lässt (Plan Bedienung B8).
    start: _uebernehmen je Messwert beim Öffnen. Ergebnis: dict mit werkstoff_id (alle gewählten Rohre/Profile haben
    denselben anderen Werkstoff als die Vorgabe), normteile (Bauteilnamen, die beim Öffnen gewählt waren und
    abgewählt wurden) und anbau_weglassen ('ja'/'nein', wenn umgeschaltet); leer = nichts zu merken."""
    out = {}
    gewaehlt = [m for m in messwerte if m.get("_uebernehmen") and not m.get("fehler") and not m.get("_blech_artikel")
                and m.get("profilform")]
    ws = {m.get("_werkstoff") for m in gewaehlt}
    if len(ws) == 1:
        w = next(iter(ws))
        if w and w != werkstoff_vorgabe:
            out["werkstoff_id"] = w
    namen = []
    for m, vorher in zip(messwerte, start):
        name = (m.get("bauteil") or "").strip()
        if vorher and not m.get("_uebernehmen") and name and name not in namen and m.get("_knick_von") is None:
            namen.append(name)
    if namen:
        out["normteile"] = namen
    if anbau_start is not None and anbau_jetzt is not None and bool(anbau_start) != bool(anbau_jetzt):
        out["anbau_weglassen"] = "ja" if anbau_jetzt else "nein"
    # Zusatzarbeiten, die alle gewählten Teile bekommen und die das Profil noch nicht vorgibt (Plan Angebotsablauf V4)
    alle = [set(m.get("_zusatz") or ()) for m in messwerte if m.get("_uebernehmen") and not m.get("fehler")]
    gemeinsam = set.intersection(*alle) if alle else set()
    neu = sorted(gemeinsam - set(zusatz_vorgabe or ()))
    if neu:
        out["zusatz"] = neu
    return out


def korrekturen_text(k):
    teile = []
    if k.get("werkstoff_id"):
        teile.append(f"Werkstoff {k['werkstoff_id']}")
    if k.get("normteile"):
        teile.append("Normteile " + ", ".join(k["normteile"][:4]) + (" …" if len(k["normteile"]) > 4 else ""))
    if k.get("anbau_weglassen"):
        teile.append("Anbauteile " + ("weglassen" if k["anbau_weglassen"] == "ja" else "übernehmen"))
    if k.get("zusatz"):
        teile.append("Zusatzarbeit " + ", ".join(k["zusatz"]))
    return "; ".join(teile)


def merken(db, kundennr, k):
    """Korrekturen ins Importprofil des Kunden schreiben (anlegen, falls es fehlt); Normteile kommen zu den
    vorhandenen Begriffen dazu. Ergebnis: Text für den Bericht oder None."""
    if not kundennr or not k:
        return None
    profil = fuer_kunde(db, kundennr)
    if profil is None:
        db.neu("importprofile", dict(kundennr=kundennr, bemerkung="aus dem STEP-Prüfdialog gelernt"))
        profil = fuer_kunde(db, kundennr)
    if k.get("werkstoff_id"):
        db.aendern("importprofile", profil["id"], "werkstoff_id", k["werkstoff_id"])
    if k.get("normteile"):
        alt = begriffe(profil.get("normteile"))
        neu = alt + [n for n in k["normteile"] if n.lower() not in {a.lower() for a in alt}]
        db.aendern("importprofile", profil["id"], "normteile", "; ".join(neu))
    if k.get("anbau_weglassen"):
        db.aendern("importprofile", profil["id"], "anbau_weglassen", k["anbau_weglassen"])
    if k.get("zusatz"):
        alt = begriffe(profil.get("zusatz"))
        neu = alt + [n for n in k["zusatz"] if n.lower() not in {a.lower() for a in alt}]
        db.aendern("importprofile", profil["id"], "zusatz", "; ".join(neu))
    return f"Importprofil des Kunden {kundennr} ergänzt: {korrekturen_text(k)}"
