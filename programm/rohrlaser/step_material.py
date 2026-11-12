"""Werkstoff aus den Material-Einträgen einer STEP-Datei als Vorschlag (CAD-Entwicklungsplan Paket 2, 12.11.2026).

Manche CAD-Systeme schreiben je Bauteil einen Werkstoffnamen in die STEP-Datei (PROPERTY_DEFINITION 'material
property' → REPRESENTATION 'material name' → DESCRIPTIVE_REPRESENTATION_ITEM). material_namen() liest sie je
Bauteilname, vorschlag() sucht dazu den Werkstoff der Stammdaten. Nur eindeutige Angaben werden ein Vorschlag
(Werkstoffnummer 1.4301, Stahlsorte S355, Aluminium 6060, AISI 304 …); eine allgemeine Angabe wie „Steel“ oder ein
unbekannter Name bleibt ein Hinweis – ein Werkstoff wird nie geraten.
"""
import re

_CACHE = {}
_EINTRAG = re.compile(rb"#(\d+)\s*=\s*([A-Z_]+)\s*\(([^;]*?)\)\s*;", re.DOTALL)
_ARTEN = (b"PROPERTY_DEFINITION_REPRESENTATION", b"PROPERTY_DEFINITION", b"REPRESENTATION",
          b"DESCRIPTIVE_REPRESENTATION_ITEM", b"PRODUCT_DEFINITION_SHAPE", b"PRODUCT_DEFINITION",
          b"PRODUCT_DEFINITION_FORMATION", b"PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE", b"PRODUCT")
_TEXT = re.compile(r"'((?:[^']|'')*)'")
_REF = re.compile(r"#(\d+)")

# AISI-/Handelsnamen nichtrostender Stähle -> Werkstoffnummer (allgemein übliche Zuordnung)
AISI = {"304": "1.4301", "304L": "1.4307", "316L": "1.4404", "316TI": "1.4571", "321": "1.4541", "430": "1.4016",
        "441": "1.4509", "V2A": "1.4301", "V4A": "1.4404"}
ALLGEMEIN = ("STEEL", "STAHL", "STAINLESS", "EDELSTAHL", "ALUMINIUM", "ALUMINUM", "ALU", "METAL", "METALL", "GENERIC",
             "DEFAULT", "STANDARD", "BAUSTAHL", "MILD STEEL", "CARBON STEEL")


def _dec(b):
    from .importprofil import _text
    try:
        return _text(b.decode("utf-8"))
    except UnicodeDecodeError:
        return _text(b.decode("latin-1"))


def material_namen(pfad):
    """{Bauteilname: Werkstoffname} aus den Material-Einträgen der STEP-Datei; '' als Schlüssel = einziger
    Werkstoffname der ganzen Datei (gilt für alle Körper). Ohne Einträge oder unlesbar: {}."""
    import os
    if not pfad:
        return {}
    try:
        st = os.stat(pfad)
    except OSError:
        return {}
    schl = (str(pfad), st.st_mtime_ns, st.st_size)
    if schl in _CACHE:
        return _CACHE[schl]
    out = {}
    try:
        import mmap
        with open(pfad, "rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as daten:
            if daten.find(b"material name") >= 0:
                e = {}
                for t in _EINTRAG.finditer(daten):
                    if t.group(2) in _ARTEN:
                        e[int(t.group(1))] = (t.group(2).decode(), _dec(t.group(3)))
                out = _auswerten(e)
    except (OSError, ValueError):
        out = {}
    _CACHE[schl] = out
    return out


def _auswerten(e):
    def refs(nr):
        return [int(x) for x in _REF.findall(_TEXT.sub("''", e[nr][1]))] if nr in e else []

    def texte(nr):
        return [x.replace("''", "'") for x in _TEXT.findall(e[nr][1])] if nr in e else []

    def produkt(nr, tiefe=0):
        """Bauteilname zu einem Verweis (PRODUCT_DEFINITION_SHAPE → PRODUCT_DEFINITION → FORMATION → PRODUCT)."""
        if nr not in e or tiefe > 4:
            return None
        art = e[nr][0]
        if art == "PRODUCT":
            t = texte(nr)
            return ((t[1] if len(t) > 1 else "") or (t[0] if t else "")).strip() or None
        for r in refs(nr):
            if r in e and e[r][0].startswith("PRODUCT"):
                name = produkt(r, tiefe + 1)
                if name:
                    return name
        return None

    out, alle = {}, set()
    for nr, (art, _) in e.items():
        if art != "PROPERTY_DEFINITION_REPRESENTATION":
            continue
        r = refs(nr)
        if len(r) < 2 or r[1] not in e or e[r[1]][0] != "REPRESENTATION":
            continue
        if (texte(r[1]) or [""])[0].strip().lower() != "material name":
            continue
        wert = next((t for i in refs(r[1]) if i in e and e[i][0] == "DESCRIPTIVE_REPRESENTATION_ITEM"
                     for t in reversed(texte(i)) if t.strip()), "").strip()
        if not wert:
            continue
        alle.add(wert)
        name = next((produkt(z) for z in refs(r[0]) if produkt(z)), None) if r[0] in e else None
        if name:
            out.setdefault(name, wert)
    if len(alle) == 1:
        out[""] = next(iter(alle))
    return out


def vorschlag(material, werkstoffe, vorgabe=None):
    """(Werkstoff-ID oder None, Text) zu einem Werkstoffnamen aus der STEP. werkstoffe: {ID: Zeile} der Stammdaten.
    Mehrere passende (S235 → S235-10219, S235-10210): die Vorgabe, wenn sie dabei ist, sonst kein Vorschlag."""
    text = str(material or "").strip()
    if not text:
        return None, ""
    gross = text.upper().replace("_", " ")
    suchen = []
    suchen += re.findall(r"(?<![0-9.])([1-3]\.[0-9]{4})(?![0-9])", gross)
    suchen += [AISI[a] for a in re.findall(r"(?<![A-Z0-9])(304L|316L|316TI|304|321|430|441|V2A|V4A)(?![A-Z0-9])", gross)]
    suchen += re.findall(r"(?<![A-Z0-9])([SEP][0-9]{3})(?![0-9])", gross)
    suchen += re.findall(r"(?<![0-9])(6060|6063|6082|6061|6005A?|5754|5083)(?![0-9])", gross)
    treffer = []
    for s in dict.fromkeys(suchen):
        for wid, z in werkstoffe.items():
            felder = " ".join(str(z.get(f) or "") for f in ("werkstoff_id", "werkstoff", "werkstoff_nr")).upper()
            if re.search(rf"(?<![A-Z0-9.]){re.escape(s)}(?![0-9])", felder) and wid not in treffer:
                treffer.append(wid)
        if treffer:
            break
    if len(treffer) == 1:
        return treffer[0], f"Werkstoff laut STEP: {text} → Vorschlag {treffer[0]}"
    if vorgabe in treffer:
        return vorgabe, f"Werkstoff laut STEP: {text} → passt zur Vorgabe {vorgabe}"
    if treffer:
        return None, (f"Werkstoff laut STEP: {text} – mehrere Werkstoffe passen ({', '.join(treffer[:4])}), "
                      "bitte wählen")
    if any(re.search(rf"(?<![A-Z]){re.escape(a)}(?![A-Z])", gross) for a in ALLGEMEIN) and not suchen:
        return None, f"Werkstoff laut STEP: {text} (allgemeine Angabe, kein Vorschlag)"
    return None, f"Werkstoff laut STEP: {text} (kein passender Werkstoff in den Stammdaten)"


def anwenden(messwerte, werkstoffe, vorgabe=None):
    """Werkstoff aus der STEP je Körper: _werkstoff_step (Name aus der Datei), _werkstoff_text (Hinweis) und, wenn
    eindeutig, _werkstoff_vorschlag. Rohre und Profile ohne eigene Wahl bekommen den Vorschlag als Werkstoff
    vorbelegt (_werkstoff; Bleche haben eigene Werkstoffe und bekommen nur den Hinweis). Ergebnis: Anzahl Körper
    mit Werkstoffangabe."""
    from . import step
    n = 0
    for m in messwerte:
        if m.get("fehler") or not m.get("_pfad"):
            continue
        namen = material_namen(m["_pfad"])
        if not namen:
            continue
        name = str(m.get("bauteil") or "").strip()
        material = namen.get(name) or namen.get(re.sub(r"(?::\d+|<\d+>)$", "", name)) or namen.get("")
        if not material:
            continue
        wid, text = vorschlag(material, werkstoffe, vorgabe)
        m["_werkstoff_step"], m["_werkstoff_text"] = material, text
        n += 1
        if wid:
            m["_werkstoff_vorschlag"] = wid
            if "_werkstoff" not in m and step.blech(m) is None and not m.get("_normteil"):
                m["_werkstoff"] = wid
        else:
            m.pop("_werkstoff_vorschlag", None)
    return n
