"""Automatische Zuordnung von Dateien im Austauschordner (Austauschordner 2.0, Abschnitt 4). Ohne Qt.

Woran eine Datei erkannt wird (in dieser Reihenfolge, jede Fundstelle mit Grund):
- Ordner: Anfragen-Akte A-JJJJ-NNNNN (Kunde und Bearbeiter aus der Akte), Angebotsordner der Ablage
  „2026-00042 Kunde“, Angebotsordner der PPEASE-Ablage (PPEASE-Nummer, Angebot mit dieser PPEASE-Nummer).
- Name und Pfad: Angebotsnummer JJJJ-NNNNN, Auftragsnummer AU-JJJJ-NNNNN, AB-Nummer, Anfrage A-JJJJ-NNNNN,
  Kundennummer (nur mit „Kd“, „Kunde“ oder „KdNr“ davor oder als eigener Ordnername), Kundenname als Ordnername,
  Artikelnummer einer Position (Dateiname = Artikelnummer).
- Folgerungen: Angebot sicher → Kunde des Angebots sicher, Bearbeiter des Angebots als Vorschlag; Auftrag sicher →
  Kunde des Auftrags.

Sicher heißt: die Nummer gibt es in der Datenbank genau so (oder der Ordner gehört eindeutig dazu). Sicheres wird
gesetzt, wenn das Feld noch leer ist; Unsicheres (Nummer nicht in der Datenbank, Kundenname nur ähnlich, JJJJ-NNNNN
passt zu Angebot UND PPEASE) kommt in die Vorschläge und muss bestätigt werden. Nie wird ein von Hand gesetzter Wert
überschrieben."""
import json
import re
from pathlib import Path

from . import austausch_dateien as ad

ANGEBOT = re.compile(r"(?<![0-9A-Za-z-])(\d{4}-\d{5})(?!\d)")
AUFTRAG = re.compile(r"(?<![0-9A-Za-z-])(AU-\d{4}-\d{5})(?!\d)", re.I)
AB = re.compile(r"(?<![0-9A-Za-z-])AB-(\d{4}-\d{5})(?!\d)", re.I)
ANFRAGE = re.compile(r"(?<![0-9A-Za-z-])(A-\d{4}-\d{5})(?!\d)", re.I)
KUNDENNR = re.compile(r"(?:\bKd\.?\s*-?\s*Nr\.?|\bKdNr|\bKunde(?:nnr\.?|nnummer)?|\bKd)\s*[-_:#]?\s*(\d{4,8})\b", re.I)


class Kontext:
    """Nachschlagewerte aus der Datenbank, einmal je Lauf gelesen."""

    def __init__(self, db):
        self.db = db
        self.angebote = {}          # Nummer -> dict(kundennr, bearbeiter, ppease)
        self.ppease = {}            # PPEASE-Nummer -> Angebotsnummer
        for nr, kd, bearb, zusatz in db.con.execute(
                "SELECT nummer, kundennr, bearbeiter, zusatz FROM angebote WHERE nummer IS NOT NULL"):
            pp = ""
            if zusatz:
                try:
                    pp = str((json.loads(zusatz).get("ppease") or {}).get("nummer") or "")
                except (ValueError, AttributeError):
                    pp = ""
            self.angebote[nr] = dict(kundennr=kd or "", bearbeiter=bearb or "", ppease=pp)
            if pp:
                self.ppease.setdefault(pp, nr)
        self.auftraege = {}
        try:
            for nr, daten in db.con.execute("SELECT nummer, daten FROM auftrag_kopf WHERE nummer IS NOT NULL"):
                try:
                    d = json.loads(daten or "{}")
                except ValueError:
                    d = {}
                self.auftraege[nr] = dict(kundennr=str(d.get("kundennr") or ""), projekt=d.get("projekt") or "")
        except Exception:           # noqa: BLE001 – ohne Auftragsverwaltung
            pass
        self.kunden = {}            # Kundennr -> Name
        for kd, name in db.con.execute("SELECT kundennr, name FROM kunden"):
            if kd:
                self.kunden[str(kd)] = name or ""
        self.kunden_name = {}       # suchtext(Name) -> Kundennr (nur eindeutige, ab 4 Zeichen)
        doppelt = set()
        for kd, name in self.kunden.items():
            n = ad.suchtext(name).strip()
            if len(n) < 4:
                continue
            if n in self.kunden_name:
                doppelt.add(n)
            self.kunden_name[n] = kd
        for n in doppelt:
            del self.kunden_name[n]
        self.artikel = {}           # suchtext(Artikelnummer) -> Angebotsnummer (nur eindeutige)
        try:
            doppelt = set()
            for art, nr in db.con.execute(
                    "SELECT p.artikel, a.nummer FROM positionen p JOIN angebote a ON a.id=p.angebot_id "
                    "WHERE p.artikel IS NOT NULL AND p.artikel<>''"):
                k = ad.suchtext(art).strip()
                if len(k) < 4:
                    continue
                if k in self.artikel and self.artikel[k][1] != nr:
                    doppelt.add(k)
                self.artikel[k] = (art, nr)
            for k in doppelt:
                self.artikel[k] = (self.artikel[k][0], None)
        except Exception:           # noqa: BLE001
            pass


def erkennen(datei, ktx, akte=None):
    """Treffer für eine Datei: [dict(feld, wert, sicher, grund)] (je Feld der beste zuerst)."""
    bereich, rel = ad.zerlegen(datei)
    teile = rel.split("/")
    name = teile[-1]
    stamm = Path(name).stem
    out = []

    def dazu(feld, wert, sicher, grund):
        wert = str(wert or "").strip()
        if not wert:
            return
        for x in out:
            if x["feld"] == feld and x["wert"] == wert:
                x["sicher"] = x["sicher"] or sicher
                return
        out.append(dict(feld=feld, wert=wert, sicher=bool(sicher), grund=grund))

    # Ordner der vorhandenen Bereiche
    if bereich == ad.ANFRAGEN:
        m = next((ANFRAGE.search(t) for t in teile if ANFRAGE.search(t)), None)
        if m:
            nr = m.group(1).upper()
            dazu("anfrage", nr, True, "liegt in der Anfrage-Akte")
            if akte is not None:
                if akte.kunde:
                    dazu("kundennr", akte.kunde, True, "Kunde der Anfrage")
                if akte.bearbeiter:
                    dazu("bearbeiter", akte.bearbeiter, False, "Bearbeiter der Anfrage")
    if bereich == ad.ANGEBOTE and len(teile) > 1:
        m = ANGEBOT.match(teile[0])
        if m and m.group(1) in ktx.angebote:
            dazu("angebot", m.group(1), True, f"Angebotsordner {teile[0]}")
    if bereich == ad.PPEASE and len(teile) > 1:
        pp = teile[0].split(" ")[0]
        dazu("ppease", pp, True, f"PPEASE-Angebotsordner {teile[0]}")
        if pp in ktx.ppease:
            dazu("angebot", ktx.ppease[pp], True, f"Angebot mit PPEASE-Nr. {pp}")

    text = " ".join(teile)
    for m in AUFTRAG.finditer(text):
        nr = m.group(1).upper()
        dazu("auftrag", nr, nr in ktx.auftraege, "Auftragsnummer im Namen" +
             ("" if nr in ktx.auftraege else " (nicht in der Datenbank)"))
    for m in AB.finditer(text):
        nr = m.group(1)
        if nr in ktx.angebote:
            dazu("angebot", nr, False, f"AB-Nummer AB-{nr} im Namen")
    if bereich != ad.ANFRAGEN:
        for m in ANFRAGE.finditer(text):
            dazu("anfrage", m.group(1).upper(), False, "Anfragenummer im Namen")
    for m in ANGEBOT.finditer(text):
        nr = m.group(1)
        vor = text[max(0, m.start() - 3):m.start()].upper()
        if vor.endswith(("AU-", "AB-", "A-")):
            continue
        if nr in ktx.angebote and nr in ktx.ppease:
            dazu("angebot", nr, False, "Nummer passt zu einem Angebot und zu einer PPEASE-Nummer")
        elif nr in ktx.angebote:
            dazu("angebot", nr, True, "Angebotsnummer im Namen")
        elif nr in ktx.ppease:
            dazu("ppease", nr, True, "PPEASE-Nummer eines Angebots im Namen")
            dazu("angebot", ktx.ppease[nr], True, f"Angebot mit PPEASE-Nr. {nr}")
        elif bereich != ad.PPEASE:
            dazu("angebot", nr, False, "Nummer im Namen (kein Angebot damit in der Datenbank)")
    for m in KUNDENNR.finditer(text):
        kd = m.group(1)
        dazu("kundennr", kd, kd in ktx.kunden, "Kundennummer im Namen" +
             ("" if kd in ktx.kunden else " (nicht im Kundenstamm)"))
    for t in teile[:-1]:
        if t in ktx.kunden:
            dazu("kundennr", t, True, f"Ordner {t} = Kundennummer")
        kd = ktx.kunden_name.get(ad.suchtext(t).strip())
        if kd:
            dazu("kundennr", kd, False, f"Ordner „{t}“ = Kundenname {ktx.kunden.get(kd)}")
    art = ktx.artikel.get(ad.suchtext(stamm).strip())
    if art:
        dazu("bauteil", art[0], True, "Dateiname = Artikelnummer einer Position")
        if art[1]:
            dazu("angebot", art[1], False, f"Artikel {art[0]} steht im Angebot {art[1]}")

    # Folgerungen
    for x in list(out):
        if x["feld"] == "angebot" and x["sicher"] and x["wert"] in ktx.angebote:
            a = ktx.angebote[x["wert"]]
            if a["kundennr"]:
                dazu("kundennr", a["kundennr"], True, f"Kunde des Angebots {x['wert']}")
            if a["bearbeiter"]:
                dazu("bearbeiter", a["bearbeiter"], False, f"Bearbeiter des Angebots {x['wert']}")
            if a["ppease"]:
                dazu("ppease", a["ppease"], True, f"PPEASE-Nr. des Angebots {x['wert']}")
        if x["feld"] == "auftrag" and x["sicher"] and x["wert"] in ktx.auftraege:
            a = ktx.auftraege[x["wert"]]
            if a["kundennr"]:
                dazu("kundennr", a["kundennr"], True, f"Kunde des Auftrags {x['wert']}")
            if a["projekt"]:
                dazu("projekt", a["projekt"], False, f"Projekt des Auftrags {x['wert']}")
    # je Feld: sicher vor unsicher; zwei verschiedene sichere Werte = beide nur Vorschlag
    je = {}
    for x in out:
        je.setdefault(x["feld"], []).append(x)
    ergebnis = []
    for feld, xs in je.items():
        sichere = {x["wert"] for x in xs if x["sicher"]}
        if len(sichere) > 1:
            for x in xs:
                x["sicher"] = False
                x["grund"] += " (mehrere Treffer, bitte wählen)"
        ergebnis.extend(sorted(xs, key=lambda x: not x["sicher"]))
    return ergebnis


def _akte(db, datei):
    b, rel = ad.zerlegen(datei)
    if b != ad.ANFRAGEN:
        return None
    m = ANFRAGE.search(rel)
    if not m:
        return None
    try:
        from . import anfragen_akten
        return anfragen_akten.ablage(db).lesen(m.group(1).upper())
    except Exception:           # noqa: BLE001
        return None


def anwenden(db, datei, p=None, ktx=None, treffer=None):
    """Erkennen und eintragen: Sicheres in leere Felder, Unsicheres (und Sicheres, das einem vorhandenen Wert
    widerspricht) als Vorschlag. Ergebnis: (gesetzt {Feld: Wert}, Vorschläge [..])."""
    ktx = ktx or Kontext(db)
    treffer = treffer if treffer is not None else erkennen(datei, ktx, _akte(db, datei))
    m = ad.meta(db, datei)
    gesetzt, vs = {}, []
    for x in treffer:
        vorhanden = m.get(x["feld"]) or gesetzt.get(x["feld"])
        if vorhanden == x["wert"]:
            continue
        if x["sicher"] and not vorhanden and x["feld"] not in gesetzt:
            gesetzt[x["feld"]] = x["wert"]
        elif not any(v["feld"] == x["feld"] and v["wert"] == x["wert"] for v in vs):
            vs.append(dict(feld=x["feld"], wert=x["wert"], grund=x["grund"]))
    alt_vs = ad.vorschlaege(m)
    vs = [v for v in vs if not any(a["feld"] == v["feld"] and a["wert"] == v["wert"] for a in alt_vs)] + alt_vs
    vs = [v for v in vs if (m.get(v["feld"]) or gesetzt.get(v["feld"])) != v["wert"]]
    werte = dict(gesetzt)
    neu_vs = json.dumps(vs, ensure_ascii=False) if vs else None
    if neu_vs != (m.get("vorschlag") or None):
        werte["vorschlag"] = neu_vs
    if werte:
        with db.con:
            ad._meta_schreiben(db, datei, werte)
            for k, v in gesetzt.items():
                ad.ereignis(db, datei, ad.E_FELD, "automatisch erkannt", feld=k, neu=v)
    return gesetzt, vs


def alle_anwenden(db, eintraege, nur_ohne=True):
    """Für viele Dateien (Knopf „Zuordnung erkennen“). nur_ohne: nur Dateien ohne Metadaten. Ergebnis: Anzahl
    Dateien mit neuen Werten oder Vorschlägen."""
    ktx = Kontext(db)
    metas = ad.meta(db)
    n = 0
    for e in eintraege:
        if e.ordner or (nur_ohne and e.datei in metas):
            continue
        g, v = anwenden(db, e.datei, ktx=ktx)
        if g or v:
            n += 1
    return n
