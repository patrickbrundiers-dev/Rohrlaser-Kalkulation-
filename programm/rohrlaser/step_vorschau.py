"""Übersicht vor dem Messen (CAD-Entwicklungsplan Paket 5, Abschnitt 1.2 „Importvorschau“): liest nur den Text der
STEP-Dateien (ohne Geometrie-Bibliothek, Sekundenbruchteile je MB) und zählt Baugruppen, Bauteile, Einbauten, gleiche
Teile, Körper und vermutete Zukaufteile (nur aus dem Bauteilnamen); dazu die Längeneinheit und eine geschätzte
Messzeit aus der Zahl der Flächen. Nichts davon ersetzt die Messung: die Zahlen sind ein Überblick, bevor sie startet.

Struktur in AP203/AP214/AP242: PRODUCT('id','name',…) ← PRODUCT_DEFINITION_FORMATION ← PRODUCT_DEFINITION;
NEXT_ASSEMBLY_USAGE_OCCURRENCE('id','name','',#Eltern,#Kind,…) verbindet Produktdefinitionen (Eltern enthält Kind).
Bauteil = Produktdefinition ohne Kinder, Baugruppe = mit Kindern. Einbauten zählen die Vorkommen über den Baum von den
Wurzeln aus (ein Bauteil in einer zweimal eingebauten Unterbaugruppe zählt doppelt)."""
import re
from pathlib import Path

from . import zukaufteile

# Messzeit = fester Anteil je Datei + Sekunden je Fläche (ADVANCED_FACE) + Sekunden je Körperform, angepasst an die
# Messreihe vom 12.11.2026 (22 Baugruppen von 70 bis 6800 Flächen, 3 s bis 10 min, Messprogramm mit 4 Kernen). Die
# Schätzung trifft im Mittel bis auf den Faktor 1,75, darum nennt die Anzeige die Spanne halb bis doppelt so lang.
S_JE_DATEI = 2.0
S_JE_FLAECHE = 0.073
S_JE_KOERPER = 0.71

_ENT = re.compile(r"#(\d+)\s*=\s*([A-Z_0-9]+)\s*\((.*?)\)\s*;", re.S)
_REF = re.compile(r"#(\d+)")
_TEXT = re.compile(r"'((?:[^']|'')*)'")
_EINHEIT = re.compile(r"SI_UNIT\s*\(\s*(\.[A-Z]+\.|\$)\s*,\s*\.METRE\.\s*\)")
_ZOLL = re.compile(r"CONVERSION_BASED_UNIT\s*\(\s*'(INCH|FOOT)'", re.I)
_VORSATZ = {".MILLI.": "mm", ".CENTI.": "cm", ".DECI.": "dm", ".KILO.": "km", "$": "m", ".MICRO.": "µm"}


def _texte(args):
    return [t.replace("''", "'") for t in _TEXT.findall(args)]


def _dekodieren(t):
    """STEP-Zeichenkodierung \\X2\\00E4\\X0\\ (UTF-16 hex) bzw. \\X\\E4 in Klartext."""
    def x2(m):
        h = m.group(1)
        try:
            return "".join(chr(int(h[i:i + 4], 16)) for i in range(0, len(h), 4))
        except ValueError:
            return m.group(0)
    t = re.sub(r"\\X2\\([0-9A-Fa-f]+)\\X0\\", x2, t)
    return re.sub(r"\\X\\([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), t)


def datei(pfad):
    """Übersicht einer STEP-Datei als dict (siehe zusammen); bei einer nicht lesbaren Datei mit 'fehler'."""
    pfad = Path(pfad)
    try:
        roh = pfad.read_bytes().decode("latin-1")
    except OSError as f:
        return dict(datei=pfad.name, fehler=str(f))
    teil = roh.find("DATA;")
    if not roh.lstrip().startswith("ISO-10303-21") or teil < 0:
        return dict(datei=pfad.name, fehler="keine STEP-Datei (ISO-10303-21) oder ohne Datenteil")
    kopf = roh[:teil]
    produkt, formation, definition, nauo = {}, {}, {}, []
    koerper = flaechen = 0
    for m in _ENT.finditer(roh, teil):
        nr, art, args = int(m.group(1)), m.group(2), m.group(3)
        if art == "PRODUCT":
            t = _texte(args)
            produkt[nr] = _dekodieren((t[1] if len(t) > 1 and t[1].strip() else (t[0] if t else "")).strip())
        elif art in ("PRODUCT_DEFINITION_FORMATION", "PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE"):
            r = _REF.findall(args)
            if r:
                formation[nr] = int(r[-1])
        elif art == "PRODUCT_DEFINITION":
            r = _REF.findall(args)
            if r:
                definition[nr] = int(r[0])
        elif art == "NEXT_ASSEMBLY_USAGE_OCCURRENCE":
            r = _REF.findall(args)
            if len(r) >= 2:
                nauo.append((int(r[0]), int(r[1])))
        elif art in ("MANIFOLD_SOLID_BREP", "BREP_WITH_VOIDS"):
            koerper += 1
        elif art == "ADVANCED_FACE":
            flaechen += 1
    # komplexe Entitäten (#n = ( … MANIFOLD_SOLID_BREP(…) … );) fängt _ENT nicht: grob nachzählen
    koerper += len(re.findall(r"=\s*\(\s*[^;]*?MANIFOLD_SOLID_BREP\s*\(", roh[teil:]))

    def name(pd):
        return produkt.get(formation.get(definition.get(pd)), "") or ""

    kinder = {}
    for eltern, kind in nauo:
        kinder.setdefault(eltern, []).append(kind)
    alle = set(definition)
    wurzeln = [pd for pd in alle if pd not in {k for _, k in nauo}] or list(alle)
    vorkommen = {}

    def zaehlen(pd, n, tiefe=0):
        if tiefe > 50:              # Kreis in fehlerhaften Dateien
            return
        if pd not in kinder:
            vorkommen[pd] = vorkommen.get(pd, 0) + n
            return
        for k in kinder[pd]:
            zaehlen(k, n, tiefe + 1)
    for w in wurzeln:
        zaehlen(w, 1)
    baugruppen = sum(1 for pd in alle if pd in kinder)
    einbauten = sum(vorkommen.values())
    zukauf = {}
    for pd, n in vorkommen.items():
        nm = name(pd)
        kat = zukaufteile.norm(nm)[1] or zukaufteile.begriff(nm)[0]
        if kat:
            zukauf[kat] = zukauf.get(kat, 0) + n
    if _ZOLL.search(roh, teil):
        einheit = _ZOLL.search(roh, teil).group(1).lower().replace("inch", "Zoll").replace("foot", "Fuß")
    else:
        e = _EINHEIT.search(roh, teil)
        einheit = _VORSATZ.get(e.group(1), "?") if e else "?"
    schema = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", kopf)
    return dict(datei=pfad.name, mb=round(len(roh) / 1e6, 1), schema=schema.group(1) if schema else "",
                einheit=einheit, baugruppen=baugruppen, bauteile=len(vorkommen), einbauten=einbauten,
                gleiche=max(einbauten - len(vorkommen), 0), koerper=koerper, flaechen=flaechen,
                zukauf=zukauf, messzeit=S_JE_DATEI + S_JE_FLAECHE * flaechen + S_JE_KOERPER * koerper)


def zusammen(pfade):
    """Übersicht mehrerer Dateien: Summen und je Datei (Liste 'dateien'). Schlüssel: dateien, baugruppen, bauteile,
    einbauten, gleiche, koerper, flaechen, zukauf {Kategorie: Anzahl}, messzeit [s], einheiten, fehler [Texte]."""
    je = [datei(p) for p in pfade]
    gut = [d for d in je if "fehler" not in d]
    zk = {}
    for d in gut:
        for k, n in d["zukauf"].items():
            zk[k] = zk.get(k, 0) + n
    summe = {s: sum(d[s] for d in gut) for s in ("baugruppen", "bauteile", "einbauten", "gleiche", "koerper",
                                                    "flaechen", "messzeit")}
    return dict(summe, dateien=je, zukauf=zk, einheiten=sorted({d["einheit"] for d in gut}),
                fehler=[f"{d['datei']}: {d['fehler']}" for d in je if "fehler" in d])


def dauer_text(s):
    """Geschätzte Messzeit als Text: 'unter 10 s', 'etwa 40 s', 'etwa 3 min'."""
    if s < 10:
        return "unter 10 s"
    if s < 90:
        return f"etwa {int(round(s / 10.0)) * 10} s"
    return f"etwa {int(round(s / 60.0))} min"


def zeilen(u):
    """Übersicht als Textzeilen für den Dialog."""
    z = [f"{len(u['dateien'])} Datei(en), Einheit {', '.join(u['einheiten']) or '?'}",
         f"{u['baugruppen']} Baugruppe(n), {u['bauteile']} verschiedene Bauteile, {u['einbauten']} Einbauten"
         + (f" (davon {u['gleiche']} gleiche Teile mehrfach)" if u["gleiche"] else ""),
         f"{u['koerper']} verschiedene Körperformen mit {u['flaechen']} Flächen"]
    if u["zukauf"]:
        z.append("Vermutete Zukaufteile (nur aus dem Namen): "
                 + ", ".join(f"{n} × {k}" for k, n in sorted(u["zukauf"].items(), key=lambda x: -x[1])))
    else:
        z.append("Keine Zukaufteile am Namen erkannt (die Messung prüft zusätzlich die Form)")
    z.append(f"Geschätzte Messzeit: {dauer_text(u['messzeit'])} (je nach Teilen halb bis doppelt so lang)")
    if any(e not in ("mm", "?") for e in u["einheiten"]):
        z.append("Hinweis: Datei nicht in mm, die Messung rechnet die Einheit um")
    z += [f"Nicht lesbar: {f}" for f in u["fehler"]]
    return z


def zeigen_noetig(u, ab_koerper=20, ab_s=30.0):
    """Übersicht nur bei größeren Importen zeigen (sonst stört sie): ab so vielen Körpern bzw. Sekunden oder bei
    einer nicht lesbaren Datei bzw. fremder Einheit."""
    return (u["koerper"] >= ab_koerper or u["messzeit"] >= ab_s or bool(u["fehler"])
            or any(e not in ("mm", "?") for e in u["einheiten"]))
