"""Kennwerte aus der Nachkalkulation lernen (Verbesserung P4, gemeinsame Schnittstelle mit 'Intelligenteres
Programm'): Quellen liefern Fälle Soll/Ist aus nachkalkulierten Angeboten, daraus werden Vorschläge (Median von
Ist ÷ Soll, Ausreißer über 3 × MAD ausgeschlossen); geändert wird nur nach Freigabe in den Einstellungen, mit Datum,
Begründung und Version, und jede Freigabe lässt sich zurücknehmen (Historie in der Tabelle kennwerte_historie).

Schnittstelle:
- register_quelle(name, titel, funktion, anwenden=None): funktion(db) -> [Fall]; Fall = dict(schluessel=tuple,
  soll=float, ist=float, angebot=Nummer, datum=Text). anwenden(db, schluessel, faktor) -> [(Tabelle, Zeilen-ID,
  Feld, alt, neu)] schreibt die Freigabe (ohne anwenden: nur Vorschlag, keine Freigabe).
- vorschlaege(db, mindest_n=5) -> [dict(quelle, titel, schluessel, faktor, n, streuung, ausreisser, faelle, status)];
  status 'ok' oder 'zu wenig Daten' (weniger als mindest_n Fälle nach den Ausreißern).
- freigeben(db, vorschlag, begruendung, version) -> ID der Historie; zuruecknehmen(db, historie_id) -> Anzahl Werte.

Eingebaute Quelle 'schweissen': Schweißzeit je Baugruppe (Soll aus den Nahtgruppen, Ist aus der Nachkalkulation)
je Verfahren und Nahtart; nur Baugruppen, deren berechnete Nahtgruppen alle dasselbe Verfahren und dieselbe Nahtart
haben (keine Zeit von Hand). Freigabe: alle Kennwerte dieses Verfahrens und dieser Nahtart × Faktor.
"""
import datetime
import json
import statistics

from .stammdaten import Feld, Tabelle

HISTORIE = Tabelle(
    "kennwerte_historie", "Kennwerte: Freigaben",
    (Feld("datum", "Freigegeben am", breite=130),
     Feld("quelle", "Quelle", breite=110),
     Feld("schluessel", "Schlüssel", breite=160),          # JSON-Liste
     Feld("faktor", "Faktor Ist ÷ Soll", "zahl", stellen=3, breite=80),
     Feld("n", "Fälle", "ganz", breite=50),
     Feld("streuung", "Streuung (MAD)", "zahl", stellen=3, breite=80),
     Feld("begruendung", "Begründung", breite=260),
     Feld("version", "Programmversion", breite=80),
     Feld("aenderungen", "Änderungen", breite=200),         # JSON [[Tabelle, ID, Feld, alt, neu]]
     Feld("zurueck", "Zurückgenommen am", breite=130)),
    (),
    "Freigegebene Kennwert-Vorschläge aus der Nachkalkulation mit den alten Werten zum Zurücknehmen.")

MAD_GRENZE = 3.0
QUELLEN = {}                # Name: (Titel, funktion, anwenden)


def register_quelle(name, titel, funktion, anwenden=None):
    QUELLEN[name] = (titel, funktion, anwenden)


def _verhaeltnisse(faelle):
    return [f["ist"] / f["soll"] for f in faelle if isinstance(f.get("soll"), (int, float)) and f["soll"] > 0
            and isinstance(f.get("ist"), (int, float)) and f["ist"] >= 0]


def auswerten(faelle, mindest_n=5):
    """Median von Ist ÷ Soll ohne Ausreißer (Abstand zum Median > 3 × MAD). Ergebnis: dict(faktor, n, streuung,
    ausreisser [Fall], faelle [Fall], status)."""
    gueltig = [f for f in faelle if _verhaeltnisse([f])]
    if not gueltig:
        return dict(faktor=None, n=0, streuung=None, ausreisser=[], faelle=[], status="zu wenig Daten")
    q = _verhaeltnisse(gueltig)
    med = statistics.median(q)
    mad = statistics.median(abs(x - med) for x in q)
    if mad > 0:
        drin = [f for f, x in zip(gueltig, q, strict=True) if abs(x - med) <= MAD_GRENZE * mad]
        raus = [f for f, x in zip(gueltig, q, strict=True) if abs(x - med) > MAD_GRENZE * mad]
    else:
        drin, raus = gueltig, []
    q = _verhaeltnisse(drin)
    med = statistics.median(q)
    mad = statistics.median(abs(x - med) for x in q)
    return dict(faktor=med, n=len(drin), streuung=mad, ausreisser=raus, faelle=drin,
                status="ok" if len(drin) >= mindest_n else "zu wenig Daten")


def vorschlaege(db, mindest_n=5):
    from . import nachkalkulation  # noqa: F401  (registriert die Quellen Laserzeit und Rüsten)
    out = []
    for name, (titel, funktion, _) in QUELLEN.items():
        gruppen = {}
        for f in funktion(db):
            gruppen.setdefault(tuple(f["schluessel"]), []).append(f)
        for schl, faelle in sorted(gruppen.items(), key=lambda x: [str(t) for t in x[0]]):
            out.append(dict(quelle=name, titel=titel, schluessel=schl, **auswerten(faelle, mindest_n)))
    return out


def freigeben(db, vorschlag, begruendung, version):
    """Vorschlag anwenden (nur Status 'ok' und mit anwenden-Funktion der Quelle) und in der Historie merken."""
    if vorschlag.get("status") != "ok" or not vorschlag.get("faktor"):
        raise ValueError("Zu wenig Daten für eine Freigabe.")
    if not (begruendung or "").strip():
        raise ValueError("Bitte eine Begründung eintragen.")
    anwenden = QUELLEN[vorschlag["quelle"]][2]
    if anwenden is None:
        raise ValueError("Diese Quelle macht nur Vorschläge.")
    aend = anwenden(db, vorschlag["schluessel"], vorschlag["faktor"])
    return db.neu(HISTORIE.name, dict(
        datum=datetime.datetime.now().isoformat(timespec="seconds"), quelle=vorschlag["quelle"],
        schluessel=json.dumps(list(vorschlag["schluessel"]), ensure_ascii=False), faktor=vorschlag["faktor"],
        n=vorschlag["n"], streuung=vorschlag["streuung"], begruendung=begruendung.strip(), version=version,
        aenderungen=json.dumps(aend, ensure_ascii=False)))


def historie(db):
    return sorted(db.zeilen(HISTORIE.name), key=lambda z: z.get("datum") or "", reverse=True)


def zuruecknehmen(db, historie_id):
    """Alte Werte einer Freigabe wiederherstellen (nur Werte, die seitdem niemand geändert hat). Ergebnis: Anzahl."""
    z = next((x for x in db.zeilen(HISTORIE.name) if x["id"] == historie_id), None)
    if z is None or z.get("zurueck"):
        return 0
    n = 0
    for tabelle, zid, feld, alt, neu in json.loads(z.get("aenderungen") or "[]"):
        jetzt = next((x for x in db.zeilen(tabelle) if x["id"] == zid), None)
        if jetzt is not None and jetzt.get(feld) == neu:
            db.aendern(tabelle, zid, feld, alt)
            n += 1
    db.aendern(HISTORIE.name, historie_id, "zurueck", datetime.datetime.now().isoformat(timespec="seconds"))
    return n


# ------------------------------------------------------------------ Quelle Schweißen
def _schweiss_faelle(db):
    """Je nachkalkulierte Baugruppe mit Ist-Schweißzeit: (Angebotskopf, Ist, Baugruppe, Rechnung, Soll [h], Ist [h])."""
    from . import baugruppe, rechnen
    from .angebot import ist_baugruppe
    tab = db.tabellen()
    saetze = rechnen.stundensaetze(tab)
    for a in db.angebote():
        if not a.get("nachkalkuliert"):
            continue
        kopf = db.angebot(a["id"])
        ist = kopf.get("nachkalkulation") or {}
        ist_bg = ist.get("baugruppen") or {}
        if not ist_bg:
            continue
        for p in db.positionen(a["id"]):
            bg = baugruppe.lesen(p.get("baugruppe")) if ist_baugruppe(p) else None
            e = ist_bg.get((bg or {}).get("id")) or {}
            if not bg or not isinstance(e.get("schweiss_h"), (int, float)):
                continue
            r = baugruppe.rechnen(p, tab, saetze)
            soll_h = r["schweiss_min"] * (p.get("stueck") or 0) / 60
            yield kopf, ist, bg, r, soll_h, e["schweiss_h"]


def faelle_schweissen(db):
    out = []
    for kopf, ist, bg, r, soll_h, ist_h in _schweiss_faelle(db):
        naehte = [x for x in r["zeilen"] if x["art"] == "Naht" and x["zeit_min"] > 0]
        arten = {(n.get("verfahren"), n.get("nahtart")) for n in bg["naehte"]}
        if not naehte or len(arten) != 1 or any(x["werte"].get("hand") for x in naehte):
            continue
        out.append(dict(schluessel=next(iter(arten)), soll=soll_h, ist=ist_h, angebot=kopf.get("nummer"),
                        datum=ist.get("am")))
    return out


def verlauf_vorlage(db, name):
    """Verlauf der Schweißzeit über die Aufträge mit Baugruppen aus der Vorlage name (D5): [dict(angebot, datum,
    soll, ist, faktor)], älteste zuerst."""
    out = [dict(angebot=kopf.get("nummer"), datum=ist.get("am") or kopf.get("datum") or "", soll=soll_h, ist=ist_h,
                faktor=ist_h / soll_h if soll_h else None)
           for kopf, ist, bg, r, soll_h, ist_h in _schweiss_faelle(db) if name and bg.get("vorlage") == name]
    return sorted(out, key=lambda x: (str(x["datum"]), str(x["angebot"])))


def anwenden_schweissen(db, schluessel, faktor):
    verfahren, nahtart = schluessel
    aend = []
    for z in db.zeilen("schweiss_kennwerte"):
        if z.get("verfahren") == verfahren and z.get("nahtart") == nahtart and isinstance(z.get("min_m"), (int, float)):
            neu = max(0.01, round(z["min_m"] * faktor, 2))
            db.aendern("schweiss_kennwerte", z["id"], "min_m", neu)
            aend.append(["schweiss_kennwerte", z["id"], "min_m", z["min_m"], neu])
    return aend


register_quelle("schweissen", "Schweißzeit (Verfahren, Nahtart)", faelle_schweissen, anwenden_schweissen)
