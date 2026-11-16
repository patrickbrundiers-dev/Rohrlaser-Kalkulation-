"""Ist-Zeiten der Maschine aus einer CSV-Datei (Plan ArTube-Unterlagen E2, Patrick 12.11.2026 „Alles einbauen“).

Die Maschine (oder ihr Leitrechner) schreibt Laufzeiten je Programm oder Teil in eine Tabelle. Ein festes Format
gibt es nicht, deshalb ordnet der Bediener die Spalten zu (das Programm schlägt eine Zuordnung nach den
Spaltenüberschriften vor): Artikel/Programm, Position, Laufzeit, Stückzahl. Jede Zeile wird über die Position oder
den Artikel (auch als Teil des Programmnamens, z. B. „W1_QR40.lst“) einem Laserteil des Angebots zugeordnet; mehrere
Zeilen eines Teils werden gemittelt. Ergebnis: Laufzeit je Teil [s] wie die Spalte „Laufzeit je Teil laut Maschine“
der Nachkalkulation. Ohne Qt."""
import csv
import io
import re

FELDER = (("artikel", "Artikel / Programm"), ("pos", "Position"), ("zeit", "Laufzeit"), ("stueck", "Stückzahl"))
EINHEITEN = ("s", "min", "h")
JE_TEIL = "je Teil"
GESAMT = "gesamt für die Stückzahl"
ZEIT_GILT = (JE_TEIL, GESAMT)
STICHWORTE = {
    "artikel": ("artikel", "programm", "program", "teil", "part", "name", "job", "zeichnung"),
    "pos": ("pos",),
    "zeit": ("laufzeit", "zeit", "time", "dauer", "duration", "schneidzeit", "bearbeitungszeit"),
    "stueck": ("stück", "stueck", "stk", "anzahl", "menge", "qty", "quantity", "count", "teile"),
}
FAKTOR = {"s": 1.0, "sec": 1.0, "sek": 1.0, "min": 60.0, "h": 3600.0, "std": 3600.0}


def lesen(pfad=None, text=None):
    """(Kopfzeile, Zeilen) einer CSV-Datei; Trennzeichen ; , Tab werden erkannt, UTF-8 oder Windows-Zeichensatz."""
    if text is None:
        roh = open(pfad, "rb").read()
        for enc in ("utf-8-sig", "cp1252"):
            try:
                text = roh.decode(enc)
                break
            except UnicodeDecodeError:
                continue
    probe = text[:4096]
    try:
        trenn = csv.Sniffer().sniff(probe, delimiters=";,\t").delimiter
    except csv.Error:
        trenn = ";"
    zeilen = [z for z in csv.reader(io.StringIO(text), delimiter=trenn) if any(c.strip() for c in z)]
    if not zeilen:
        return [], []
    return [c.strip() for c in zeilen[0]], zeilen[1:]


def vorschlag_zuordnung(kopf):
    """{Feld: Spaltennummer oder None} nach den Überschriften; jede Spalte höchstens einmal."""
    frei = list(range(len(kopf)))
    out = {}
    for feld in ("pos", "stueck", "zeit", "artikel"):
        treffer = None
        for i in frei:
            t = kopf[i].lower()
            if feld == "pos" and not re.match(r"^pos(\.|ition|\b|$)", t):
                continue
            if any(w in t for w in STICHWORTE[feld]):
                treffer = i
                break
        out[feld] = treffer
        if treffer is not None:
            frei.remove(treffer)
    return {f: out[f] for f, _ in FELDER}


def zahl(text):
    t = str(text or "").strip().replace(" ", "")
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def zeit_s(text, einheit="s"):
    """Sekunden aus „01:02:03“, „2:30“ (min:s), „95 s“, „1,5 min“, „0,2 h“ oder einer Zahl in der Einheit; None,
    wenn keine Zeit."""
    t = str(text or "").strip().lower()
    if not t:
        return None
    if ":" in t:
        teile = t.split(":")
        try:
            w = [float(x.replace(",", ".")) for x in teile]
        except ValueError:
            return None
        if len(w) == 3:
            return w[0] * 3600 + w[1] * 60 + w[2]
        if len(w) == 2:
            return w[0] * 60 + w[1]
        return None
    m = re.match(r"^([0-9.,]+)\s*([a-z]*)\.?$", t)
    if not m:
        return None
    w = zahl(m.group(1))
    if w is None:
        return None
    f = FAKTOR.get(m.group(2)) if m.group(2) else FAKTOR.get(einheit, 1.0)
    return None if f is None else w * f


def _pos(text):
    w = zahl(text)
    return int(w) if w is not None and w == int(w) else None


def _teil(teile, artikel, pos):
    if pos is not None:
        for t in teile:
            if _pos(t.get("pos")) == pos:
                return t
    a = str(artikel or "").strip().lower()
    if not a:
        return None
    for t in teile:                                        # gleicher Artikel
        if str(t.get("artikel") or "").strip().lower() == a:
            return t
    passend = [t for t in teile if len(str(t.get("artikel") or "")) >= 2
               and re.search(r"(^|[^0-9a-z])" + re.escape(str(t["artikel"]).lower()) + r"($|[^0-9a-z])", a)]
    passend.sort(key=lambda t: -len(str(t["artikel"])))       # längster Artikel im Programmnamen
    return passend[0] if passend else None


def zuordnen(teile, zeilen, zuordnung, einheit="s", gilt=JE_TEIL):
    """({Positions-ID: Laufzeit je Teil [s]}, [nicht zugeordnete Zeilen als Text]). teile wie
    nachkalkulation.teile_soll (id, pos, artikel, stueck)."""
    def zelle(z, feld):
        i = zuordnung.get(feld)
        return z[i] if i is not None and i < len(z) else ""

    summe, anzahl, offen = {}, {}, []
    for z in zeilen:
        s = zeit_s(zelle(z, "zeit"), einheit)
        if s is None:
            continue
        t = _teil(teile, zelle(z, "artikel"), _pos(zelle(z, "pos")))
        if t is None:
            offen.append(" · ".join(c for c in z if c.strip())[:80])
            continue
        stk = zahl(zelle(z, "stueck")) if zuordnung.get("stueck") is not None else None
        if gilt == GESAMT:
            n = stk if stk else (t.get("stueck") or 1)
            summe[t["id"]] = summe.get(t["id"], 0.0) + s
        else:
            n = stk if stk else 1
            summe[t["id"]] = summe.get(t["id"], 0.0) + s * n
        anzahl[t["id"]] = anzahl.get(t["id"], 0.0) + n
    return {i: round(summe[i] / anzahl[i], 1) for i in summe if anzahl[i] > 0}, offen
