"""CSV einlesen und speichern (Schritt 4): Aufträge aus einer Datei übernehmen – von Hand geschrieben, aus einem
anderen System oder als Übergabedatei aus der Kalkulation – und die Auftragsliste als Datei ausgeben. Ohne Qt.

Die erste Zeile nennt die Spalten; Reihenfolge und Schreibweise sind frei (SPALTEN). Trennzeichen Semikolon, Komma
oder Tabulator. Pflicht sind Auftragsnummer, Maschine und kalkulierte Laufzeit. Die Laufzeit wird in allen
Schreibweisen von laufzeit.lesen gelesen. Spalten, die wie ein Zusatzfeld heißen, füllen dieses Feld.

Ab 2.2 (Plan N1) auch Excel-Dateien (.xlsx, erstes Blatt, ohne Zusatzpaket: die Datei ist ein ZIP mit XML) und
Zeilen, die aus Excel kopiert und eingefügt werden (Text mit Tabulatoren)."""
import csv
import datetime
import io
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from . import daten as D
from . import laufzeit

SPALTEN = {
    "nummer": ("auftragsnummer", "auftrag", "auftragsnr", "auftrags-nr", "auftrags-nr.", "nummer", "nr", "nr.",
               "angebot", "angebotsnummer"),
    "maschine": ("maschine", "anlage", "laser"),
    "kalk": ("kalkulierte laufzeit", "kalkulierte laufzeit [h:mm]", "laufzeit", "laufzeit kalkuliert", "laserzeit",
             "kalkuliert", "sollzeit", "soll", "zeit"),
    "termin": ("liefertermin", "termin", "lieferdatum", "liefertermin ab werk"),
    "kunde": ("kunde", "kundenname", "firma"),
    "bemerkung": ("bemerkung", "notiz", "hinweis", "kommentar"),
    "ist": ("tatsächliche laufzeit", "istzeit", "ist", "laufzeit tatsächlich"),
    "fertig": ("fertig am", "fertig", "fertigstellung"),
    "material": ("material da ab", "material ab", "material da", "materialeingang", "wareneingang"),
}
KOPF = ("Auftragsnummer", "Kunde", "Maschine", "Kalkulierte Laufzeit", "Liefertermin", "Status",
        "Tatsächliche Laufzeit", "Fertig am", "Bemerkung", "Material da ab")


def _text(pfad):
    roh = Path(pfad).read_bytes()
    for code in ("utf-8-sig", "cp1252"):
        try:
            return roh.decode(code)
        except UnicodeDecodeError:
            continue
    return roh.decode("latin-1")


_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
# eingebaute Zahlenformate von Excel: Datum bzw. Uhrzeit/Dauer
_DATUM_ID, _ZEIT_ID = {14, 15, 16, 17, 22}, {18, 19, 20, 21, 45, 46, 47}


def _art(code):
    """'datum', 'zeit' oder '' für einen Zahlenformat-Text von Excel."""
    c = re.sub(r'"[^"]*"|\\.|\[[^\]]*[^hms\]]\]', "", code.lower())   # Text, Escapes, Farben weg; [h] bleibt
    if "[h" in code.lower() or "[m" in code.lower():
        return "zeit"
    if any(z in c for z in ("d", "y", "j", "t")):
        return "datum"
    if "h" in c or "s" in c:
        return "zeit"
    return ""


def _zahl_text(wert, art):
    """Zahl aus Excel als Text, den lesen() versteht: Datum TT.MM.JJJJ, Dauer h:mm, sonst die Zahl."""
    if art == "datum":
        tag = datetime.date(1899, 12, 30) + datetime.timedelta(days=int(float(wert)))
        return tag.strftime("%d.%m.%Y")
    if art == "zeit":
        minuten = round(float(wert) * 24 * 60)
        return f"{minuten // 60}:{minuten % 60:02d}"
    z = float(wert)
    return str(int(z)) if z == int(z) else str(z).replace(".", ",")


def xlsx_zeilen(pfad):
    """Erstes Blatt einer Excel-Datei als Liste von Zeilen (Texte). Datumszellen werden TT.MM.JJJJ, Zeitzellen
    (Format Uhrzeit oder [h]:mm) h:mm."""
    with zipfile.ZipFile(pfad) as z:
        namen = set(z.namelist())
        geteilt = []
        if "xl/sharedStrings.xml" in namen:
            for si in ElementTree.fromstring(z.read("xl/sharedStrings.xml")).findall("x:si", _NS):
                geteilt.append("".join(t.text or "" for t in si.iter(f"{{{_NS['x']}}}t")))
        stile = []
        if "xl/styles.xml" in namen:
            st = ElementTree.fromstring(z.read("xl/styles.xml"))
            eigene = {int(f.get("numFmtId")): f.get("formatCode") or ""
                      for f in st.findall("x:numFmts/x:numFmt", _NS)}
            for xf in st.findall("x:cellXfs/x:xf", _NS):
                n = int(xf.get("numFmtId") or 0)
                stile.append("datum" if n in _DATUM_ID else "zeit" if n in _ZEIT_ID else _art(eigene.get(n, "")))
        blatt = "xl/worksheets/sheet1.xml"
        if "xl/workbook.xml" in namen and "xl/_rels/workbook.xml.rels" in namen:   # wirklich das erste Blatt
            erstes = ElementTree.fromstring(z.read("xl/workbook.xml")).find("x:sheets/x:sheet", _NS)
            rels = ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            for r in rels:
                if erstes is not None and r.get("Id") == erstes.get(_REL):
                    ziel = r.get("Target").lstrip("/")
                    blatt = ziel if ziel.startswith("xl/") else "xl/" + ziel
        daten = ElementTree.fromstring(z.read(blatt))
    zeilen = []
    for row in daten.iter(f"{{{_NS['x']}}}row"):
        werte = {}
        for c in row.findall("x:c", _NS):
            ref = re.match(r"([A-Z]+)", c.get("r") or "")
            spalte = 0
            for b in (ref.group(1) if ref else ""):
                spalte = spalte * 26 + ord(b) - 64
            spalte = spalte - 1 if ref else len(werte)
            typ, v = c.get("t"), c.find("x:v", _NS)
            if typ == "inlineStr":
                text = "".join(t.text or "" for t in c.iter(f"{{{_NS['x']}}}t"))
            elif v is None or v.text is None:
                text = ""
            elif typ == "s":
                text = geteilt[int(v.text)]
            elif typ in ("str", "e"):
                text = v.text
            elif typ == "b":
                text = "ja" if v.text == "1" else "nein"
            else:
                s = int(c.get("s") or 0)
                text = _zahl_text(v.text, stile[s] if s < len(stile) else "")
            werte[spalte] = text
        if werte:
            n = int(row.get("r") or len(zeilen) + 1) - 1
            while len(zeilen) < n:                # leere Zeilen dazwischen bleiben leer
                zeilen.append([])
            zeilen.append([werte.get(i, "") for i in range(max(werte) + 1)])
    return zeilen


def text_zeilen(text):
    """Text (CSV-Datei oder aus Excel kopiert) als Zeilen; Trennzeichen Semikolon, Tabulator oder Komma."""
    erste = text.splitlines()[0] if text.strip() else ""
    trenner = max((";", "\t", ","), key=erste.count)
    return list(csv.reader(io.StringIO(text), delimiter=trenner))


def datei_zeilen(pfad):
    """Zeilen einer CSV- oder Excel-Datei (.xlsx, .xlsm)."""
    if Path(pfad).suffix.lower() in (".xlsx", ".xlsm"):
        try:
            return xlsx_zeilen(pfad)
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError, ValueError) as e:
            raise OSError(f"keine lesbare Excel-Datei ({e})") from e
    return text_zeilen(_text(pfad))


def lesen(db, pfad=None, zeilen=None):
    """Datei (CSV oder Excel) oder schon gelesene Zeilen prüfen, noch nichts speichern. Ergebnis: dict(neu=[Auftrag],
    geaendert=[Auftrag mit id], gleich=Anzahl, fehler=[Text], uebersprungen=[Text], maschinen_neu=[Name],
    spalten_fremd=[Name])."""
    if zeilen is None:
        zeilen = datei_zeilen(pfad)
    zeilen = [z for z in zeilen]
    while zeilen and not any(str(c).strip() for c in zeilen[0]):   # Leerzeilen über der Kopfzeile
        zeilen.pop(0)
    out = dict(neu=[], geaendert=[], gleich=0, fehler=[], uebersprungen=[], maschinen_neu=[], spalten_fremd=[])
    if not zeilen:
        out["fehler"].append("Die Datei ist leer.")
        return out
    zusatz = {f["name"].lower(): f["name"] for f in db.zusatzfelder()}
    bekannt = {name: feld for feld, namen in SPALTEN.items() for name in namen}
    spalte = {}
    for i, titel in enumerate(zeilen[0]):
        t = titel.strip().lower()
        if t in bekannt:
            spalte.setdefault(bekannt[t], i)
        elif t in zusatz:
            spalte[("zusatz", zusatz[t])] = i
        elif t and t != "status":
            out["spalten_fremd"].append(titel.strip())
    fehlt = [n for f, n in (("nummer", "Auftragsnummer"), ("maschine", "Maschine"), ("kalk", "Kalkulierte Laufzeit"))
             if f not in spalte]
    if fehlt:
        out["fehler"].append("In der ersten Zeile fehlt die Spalte " + ", ".join(fehlt) + ".")
        return out
    ohne = db.einstellung("ohne_einheit")
    maschinen = {m["name"] for m in db.maschinen()}
    gesehen = set()
    for nr, z in enumerate(zeilen[1:], start=2):
        if not any(c.strip() for c in z):
            continue

        def wert(feld, z=z):
            i = spalte.get(feld)
            return z[i].strip() if i is not None and i < len(z) else ""
        nummer = wert("nummer")
        try:
            if not nummer:
                raise D.Fehler("Auftragsnummer fehlt.")
            if nummer in gesehen:
                raise D.Fehler(f"Auftragsnummer „{nummer}“ steht mehrfach in der Datei.")
            kalk = laufzeit.lesen(wert("kalk"), ohne)
            if not kalk:
                raise D.Fehler("Kalkulierte Laufzeit fehlt.")
            if not wert("maschine"):
                raise D.Fehler("Maschine fehlt.")
            neu = dict(nummer=nummer, maschine=wert("maschine"), kalk_min=kalk, liefertermin=D._tag(wert("termin")),
                       kunde=wert("kunde"), bemerkung=wert("bemerkung"),
                       zusatz={f[1]: wert(f) for f in spalte if isinstance(f, tuple)})
            if "material" in spalte:
                neu["material_ab"] = D._tag(wert("material"))
            ist = laufzeit.lesen(wert("ist"), ohne)
            if ist:
                neu["ist_min"], neu["fertig_am"] = ist, D._tag(wert("fertig"))
        except (D.Fehler, laufzeit.Fehler) as e:
            out["fehler"].append(f"Zeile {nr}: {e}")
            continue
        gesehen.add(nummer)
        alt = db.auftrag(nummer=nummer)
        mehrteilig = bool(alt and alt["gaenge"])
        if mehrteilig:                            # Arbeitsgänge werden im Programm gepflegt, nicht über die Datei
            if (neu["maschine"], neu["kalk_min"]) != (alt["maschine"], alt["kalk_min"]) or "ist_min" in neu:
                out["uebersprungen"].append(f"Zeile {nr}: Auftrag {nummer} hat mehrere Arbeitsgänge; Maschine, "
                                            "Laufzeit und Fertigmeldung bleiben, wie sie im Programm stehen.")
            neu["maschine"], neu["kalk_min"] = alt["maschine"], alt["kalk_min"]
            neu.pop("ist_min", None)
        elif " + " in neu["maschine"] or " → " in neu["maschine"]:
            out["fehler"].append(f"Zeile {nr}: Auftrag {nummer} hat mehrere Maschinen oder Arbeitsgänge. Bitte im "
                                 "Programm anlegen.")
            continue
        if not mehrteilig and neu["maschine"] not in maschinen and neu["maschine"] not in out["maschinen_neu"]:
            out["maschinen_neu"].append(neu["maschine"])
        if alt is None and db.im_papierkorb(nummer):
            out["uebersprungen"].append(f"Zeile {nr}: Auftrag {nummer} liegt im Papierkorb und wird nicht übernommen.")
        elif alt is None:
            out["neu"].append(neu)
        elif alt["status"] == D.FERTIG:
            out["uebersprungen"].append(f"Zeile {nr}: Auftrag {nummer} ist schon fertig gemeldet und bleibt, wie er ist.")
        else:
            if "kunde" not in spalte:
                neu["kunde"] = alt["kunde"]
            if "bemerkung" not in spalte:
                neu["bemerkung"] = alt["bemerkung"]
            if "termin" not in spalte:
                neu["liefertermin"] = alt["liefertermin"]
            gleich = (all(neu[k] == alt[k] for k in ("maschine", "kalk_min", "liefertermin", "kunde", "bemerkung"))
                      and all(alt["zusatz"].get(k, "") == v for k, v in neu["zusatz"].items()) and "ist_min" not in neu
                      and ("material_ab" not in neu or neu["material_ab"] == (alt.get("material_ab") or None)))
            if gleich:
                out["gleich"] += 1
            else:
                out["geaendert"].append(dict(neu, id=alt["id"]))
    return out


def uebernehmen(db, ergebnis):
    """Speichert, was lesen() gefunden hat. Ergebnis: Anzahl gespeicherter Aufträge."""
    n = 0
    for a in ergebnis["neu"] + ergebnis["geaendert"]:
        aid = db.auftrag_speichern(a)
        if a.get("ist_min"):
            db.fertig_melden(aid, a["ist_min"], a.get("fertig_am"))
        n += 1
    return n


def zusammenfassung(ergebnis):
    """Text für die Rückfrage vor dem Übernehmen."""
    teile = [f"{len(ergebnis['neu'])} neue Aufträge, {len(ergebnis['geaendert'])} geänderte, "
             f"{ergebnis['gleich']} unverändert."]
    if ergebnis["maschinen_neu"]:
        teile.append("Neue Maschinen werden angelegt (8 Stunden je Tag): " + ", ".join(ergebnis["maschinen_neu"]) + ".")
    if ergebnis["spalten_fremd"]:
        teile.append("Nicht übernommene Spalten (kein Zusatzfeld mit diesem Namen): "
                     + ", ".join(ergebnis["spalten_fremd"]) + ".")
    for liste in (ergebnis["uebersprungen"], ergebnis["fehler"]):
        teile.extend(liste[:12])
        if len(liste) > 12:
            teile.append(f"… und {len(liste) - 12} weitere.")
    return "\n".join(teile)


def _tag(iso):
    return ".".join(reversed(str(iso).split("-"))) if iso else ""


def schreiben(db, pfad, auftraege=None, form=None):
    """Auftragsliste als CSV (Semikolon, für Excel). Die Datei lässt sich mit lesen() wieder einlesen."""
    form = form or db.einstellung("laufzeit_form")
    felder = [f["name"] for f in db.zusatzfelder()]
    with open(pfad, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(KOPF + tuple(felder))
        for a in (db.auftraege() if auftraege is None else auftraege):
            w.writerow([a["nummer"], a["kunde"], a["maschine"], laufzeit.text(a["kalk_min"], form),
                        _tag(a["liefertermin"]), a["status"], laufzeit.text(a["ist_min"], form), _tag(a["fertig_am"]),
                        a["bemerkung"], _tag(a.get("material_ab"))] + [a["zusatz"].get(n, "") for n in felder])
    return pfad


# ---------------------------------------------------------------- Übergabe-Ordner (Erweiterungsplan E9)
GELESEN = "uebergabe_gelesen"


def _merkmal(pfad):
    s = Path(pfad).stat()
    return [int(s.st_mtime), s.st_size]


def neue_dateien(db, ordner=None):
    """CSV-Dateien im Übergabe-Ordner (Einstellung uebergabe_ordner), die noch nicht eingelesen oder seitdem neu
    geschrieben wurden; älteste zuerst. Ordner nicht erreichbar oder nicht eingestellt: leere Liste."""
    ordner = ordner or db.einstellung("uebergabe_ordner")
    if not ordner:
        return []
    try:
        gelesen = json.loads(db.einstellung(GELESEN) or "{}")
    except ValueError:
        gelesen = {}
    neu = []
    try:
        for p in Path(ordner).iterdir():
            if p.suffix.lower() == ".csv" and p.is_file() and gelesen.get(p.name) != _merkmal(p):
                neu.append(p)
    except OSError:
        return []
    return sorted(neu, key=lambda p: (p.stat().st_mtime, p.name))


def gelesen_merken(db, pfad):
    """Diese Datei gilt als erledigt (eingelesen oder abgelehnt), bis sie neu geschrieben wird. Das gilt für alle
    Plätze, die mit derselben Datenbank arbeiten."""
    try:
        gelesen = json.loads(db.einstellung(GELESEN) or "{}")
    except ValueError:
        gelesen = {}
    try:
        gelesen[Path(pfad).name] = _merkmal(pfad)
    except OSError:
        return
    if len(gelesen) > 400:                        # alte Einträge fallen weg
        gelesen = dict(sorted(gelesen.items(), key=lambda x: x[1][0])[-300:])
    db.einstellung_setzen(GELESEN, json.dumps(gelesen))
