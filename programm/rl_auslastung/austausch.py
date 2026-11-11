"""CSV einlesen und speichern (Schritt 4): Aufträge aus einer Datei übernehmen – von Hand geschrieben, aus einem
anderen System oder als Übergabedatei aus der Kalkulation – und die Auftragsliste als Datei ausgeben. Ohne Qt.

Die erste Zeile nennt die Spalten; Reihenfolge und Schreibweise sind frei (SPALTEN). Trennzeichen Semikolon, Komma
oder Tabulator. Pflicht sind Auftragsnummer, Maschine und kalkulierte Laufzeit. Die Laufzeit wird in allen
Schreibweisen von laufzeit.lesen gelesen. Spalten, die wie ein Zusatzfeld heißen, füllen dieses Feld."""
import csv
import io
from pathlib import Path

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
}
KOPF = ("Auftragsnummer", "Kunde", "Maschine", "Kalkulierte Laufzeit", "Liefertermin", "Status",
        "Tatsächliche Laufzeit", "Fertig am", "Bemerkung")


def _text(pfad):
    roh = Path(pfad).read_bytes()
    for code in ("utf-8-sig", "cp1252"):
        try:
            return roh.decode(code)
        except UnicodeDecodeError:
            continue
    return roh.decode("latin-1")


def lesen(db, pfad):
    """Datei prüfen, noch nichts speichern. Ergebnis: dict(neu=[Auftrag], geaendert=[Auftrag mit id], gleich=Anzahl,
    fehler=[Text], uebersprungen=[Text], maschinen_neu=[Name], spalten_fremd=[Name])."""
    text = _text(pfad)
    erste = text.splitlines()[0] if text.strip() else ""
    trenner = max((";", "\t", ","), key=erste.count)
    zeilen = list(csv.reader(io.StringIO(text), delimiter=trenner))
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
            ist = laufzeit.lesen(wert("ist"), ohne)
            if ist:
                neu["ist_min"], neu["fertig_am"] = ist, D._tag(wert("fertig"))
        except (D.Fehler, laufzeit.Fehler) as e:
            out["fehler"].append(f"Zeile {nr}: {e}")
            continue
        gesehen.add(nummer)
        if neu["maschine"] not in maschinen and neu["maschine"] not in out["maschinen_neu"]:
            out["maschinen_neu"].append(neu["maschine"])
        alt = db.auftrag(nummer=nummer)
        if alt is None:
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
                      and all(alt["zusatz"].get(k, "") == v for k, v in neu["zusatz"].items()) and "ist_min" not in neu)
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
                        a["bemerkung"]] + [a["zusatz"].get(n, "") for n in felder])
    return pfad
