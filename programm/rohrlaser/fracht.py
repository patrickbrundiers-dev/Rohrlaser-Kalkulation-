"""Rechenkern der Frachtkosten (ohne Oberfläche): Zone, Tarifwahl, Gewicht, Ladehilfsmittel, Grundfracht,
Mindestfracht, Zuschläge, Währung, Rundung und Snapshot.

Eingaben:
- daten: Fracht-Stammdaten {Kurzname: [Zeilen]} (fracht_daten.KURZ), z. B. aus Datenbank.fracht_daten()
- sendung: dict mit datum (ISO), land, plz, absender_land, absender_plz, versandart, kundennr, dienstleister,
  tarif_id (von Hand gewählt, sonst automatisch), lieferbedingung, netto [kg], verpackung [kg, leer = Eigengewicht
  der Ladungsträger], frachtpflichtig [kg, leer = nach Tarif], lht [{lht_id, anzahl, gewicht = brutto je Stück
  (optional)}], km, max_laenge [mm, längstes Teil], leistungen {Zuschlag-ID: Menge} (gewählte Zuschläge).

Rechenreihenfolge (alle Beträge ungerundet bis zur Ausgabe, dann jede Zeile auf Cent):
 1 Zone der Empfänger-PLZ (und der Absender-PLZ) nach Rangfolge der PLZ-Regeln, sonst Standardzone
 2 Tarife: aktiv, gültig am Datum, Land/Zone/Versandart/Dienstleister/Kunde passen; Kundentarif vor Rahmenvertrag vor
   Sondertarif vor Standardtarif, dann Priorität; Gleichstand -> keine stille Wahl (Status 'auswahl')
 3 Gewicht: Brutto = Netto + Verpackung (bzw. Summe der Bruttogewichte je Ladungsträger); frachtpflichtig = Höchstwert
   aus Brutto und den Faktoren, die der Tarif nutzt (m³, Stellplatz, Lademeter), aufgerundet nach Tarif
 4 Grundfracht aus den Preisstaffeln (je Bezugseinheit und Ladehilfsmittel die Stufe, in die die Menge fällt)
 5 Tarifrabatt, danach Anhebung auf die Mindestfracht
 6 Zuschläge Stufe 1 (Euro-Beträge), Stufe 2 (Prozent und Dieselstaffel auf ihre Grundlage), Mindest/Höchst
 7 Umrechnung der Tarifbeträge in EUR (Kurs aus Währungen)
"""
import datetime
import math

from .ausgabe import kaufm_runden
from .fracht_daten import OHNE_FRACHT, liste, plz_schluessel
from .stammdaten import zahl_als_text

VERSION = 1
EPS = 1e-9
RANG = {"Kundentarif": 0, "Rahmenvertrag": 1, "Sondertarif": 2, "Standardtarif": 3, None: 3, "": 3,
        "interner Verrechnungstarif": 9}
ERLAUBT = {"Gewichtstarif": {"Sendung", "kg", "100 kg"},
           "Palettentarif": {"Sendung", "Ladungsträger", "Stellplatz"},
           "Gitterboxtarif": {"Sendung", "Ladungsträger", "Stellplatz"}}
LHT_BEZUG = ("Ladungsträger", "Stellplatz")
SONDERZONEN = ("Insel", "Randgebiet", "Sondergebiet")
ZUSCHLAG_EBENE = ("Kunde", "Dienstleister", "Tarif", "allgemein")


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _zahl(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def euro(w):
    return zahl_als_text(w, 2) + " €"


def z2(w, stellen=2):
    return zahl_als_text(w, stellen)


def aktiv(z):
    return (z or {}).get("aktiv") != "nein"


def gueltig(z, datum):
    ab, bis = z.get("gueltig_ab"), z.get("gueltig_bis")
    return (not ab or ab <= datum) and (not bis or datum <= bis)


def heute():
    return datetime.date.today().isoformat()


# ------------------------------------------------------------------ PLZ und Zone
def plz_norm(plz):
    return str(plz or "").strip().upper().replace(" ", "")


def plz_aus_text(text):
    """'12345 Musterstadt' -> '12345' (erste Ziffernfolge mit 4 oder 5 Stellen), sonst ''."""
    import re
    m = re.search(r"\b(\d{4,5})\b", str(text or ""))
    return m.group(1) if m else ""


def praefix(r):
    """Präfix der Regel ('80' für '80*' und für eine kurze PLZ von 1–3 Stellen ohne PLZ bis), sonst None."""
    von = plz_norm(r.get("plz_von"))
    if von.endswith("*"):
        return von[:-1]
    if von.isdigit() and len(von) <= 3 and not plz_norm(r.get("plz_bis")):
        return von
    return None


def regel_passt(r, plz):
    von = plz_norm(r.get("plz_von"))
    if not von or not plz:
        return False
    if praefix(r) is not None:
        return plz.startswith(praefix(r))
    bis = plz_norm(r.get("plz_bis")) or von
    if len(plz) != len(von):
        return False
    return plz_schluessel(von) <= plz_schluessel(plz) <= plz_schluessel(bis)


def regel_rang(r):
    """Sortierschlüssel einer PLZ-Regel (kleiner = vorrangig): Ebene (Kunde + Dienstleister, Kunde, Dienstleister,
    allgemein), Art (einzelne PLZ, Bereich nach Breite, Präfix nach Länge), Priorität."""
    ebene = (0 if r.get("dienstleister") else 1) if r.get("kundennr") else (2 if r.get("dienstleister") else 3)
    von, bis = plz_norm(r.get("plz_von")), plz_norm(r.get("plz_bis"))
    if praefix(r) is not None:
        art, weite = 2, -len(praefix(r))
    elif not bis or bis == von:
        art, weite = 0, 0
    else:
        art = 1
        weite = int(bis) - int(von) if von.isdigit() and bis.isdigit() else 0
    return ebene, art, weite, r.get("prioritaet") or 100


def regel_text(r):
    von, bis = r.get("plz_von"), r.get("plz_bis")
    t = f"PLZ {von}–{bis}" if bis and bis != von else (f"PLZ-Präfix {praefix(r)}*" if praefix(r) is not None
                                                       else f"PLZ {von}")
    extra = [x for x in (("Kunde " + r["kundennr"]) if r.get("kundennr") else "",
                         ("Dienstleister " + r["dienstleister"]) if r.get("dienstleister") else "",
                         r.get("richtung") if r.get("richtung") not in (None, "", "beide") else "") if x]
    return t + (f" ({', '.join(extra)})" if extra else "")


def plz_stellen(daten, land):
    """Stellenzahl der PLZ im Land (Länder, Spalte PLZ-Stellen), sonst 5 für DE und 4 für andere Länder."""
    for z in daten.get("laender", []):
        if (z.get("land") or "").upper() == land and z.get("plz_laenge"):
            return int(z["plz_laenge"])
    return 5 if land == "DE" else 4


def regel_im_bereich(r, bereich):
    """Lage einer PLZ-Regel zum PLZ-Bereich (z. B. '25' = alle PLZ mit 25…): 'ganz' (Regel deckt den ganzen
    Bereich), 'teil' (ein Teil des Bereichs) oder None."""
    p = praefix(r)
    if p is not None:
        return "ganz" if bereich.startswith(p) else ("teil" if p.startswith(bereich) else None)
    von, bis = plz_norm(r.get("plz_von")), plz_norm(r.get("plz_bis")) or plz_norm(r.get("plz_von"))
    if not von.isdigit() or not bis.isdigit() or len(von) <= len(bereich):
        return None
    lo, hi = bereich.ljust(len(von), "0"), bereich.ljust(len(von), "9")
    if von <= lo and bis >= hi:
        return "ganz"
    return "teil" if von <= hi and bis >= lo else None


def zone_finden(daten, land, plz, richtung="Empfang", kundennr=None, dienstleister=None):
    """Zone einer PLZ. Ergebnis: {zone (Zeile oder None), regel, status ('ok', 'standard', 'mehrdeutig', 'fehler'),
    text, hinweise, bereich_zonen}. Eine kürzere PLZ als im Land üblich (z. B. '25') ist ein PLZ-Bereich: es zählen
    alle Regeln, die in den Bereich fallen; liegt er in mehreren Zonen, stehen sie in bereich_zonen (rechnen() nimmt
    dann die teurere)."""
    plz = plz_norm(plz)
    land = (land or "DE").strip().upper()
    zonen = {z["zone_id"]: z for z in daten.get("zonen", []) if z.get("zone_id")}
    out = dict(zone=None, regel=None, status="fehler", text="", hinweise=[], land=land, plz=plz, bereich_zonen=[])
    if not plz:
        out["text"] = "PLZ fehlt"
        return out
    if plz.isdigit() and len(plz) < plz_stellen(daten, land):
        return _bereich_finden(daten, land, plz, richtung, kundennr, dienstleister, zonen, out)
    kand, inaktiv = [], []
    for r in daten.get("plz", []):
        if (r.get("land") or "DE") != land or r.get("richtung") not in (None, "", "beide", richtung):
            continue
        if r.get("dienstleister") and r["dienstleister"] != dienstleister:
            continue
        if r.get("kundennr") and r["kundennr"] != kundennr:
            continue
        if not regel_passt(r, plz):
            continue
        z = zonen.get(r.get("zone_id"))
        (kand if z and aktiv(z) else inaktiv).append(r)
    for r in inaktiv:
        out["hinweise"].append(f"{regel_text(r)}: Zone {r.get('zone_id')} inaktiv oder unbekannt, nicht verwendet")
    if kand:
        kand.sort(key=regel_rang)
        erst = kand[0]
        andere = [r for r in kand[1:] if regel_rang(r) == regel_rang(erst) and r["zone_id"] != erst["zone_id"]]
        if andere:
            out.update(status="mehrdeutig", text=f"PLZ {plz} mehrdeutig: " + "; ".join(
                f"Zone {r['zone_id']} ({regel_text(r)})" for r in [erst] + andere)
                + ". Bitte eine Regel ändern oder eine Priorität vergeben.")
            return out
        z = zonen[erst["zone_id"]]
        out.update(zone=z, regel=erst, status="ok",
                   text=f"Zone {z['zone_id']} {z.get('bezeichnung') or ''} ({regel_text(erst)})".replace("  ", " "))
        return out
    std = [z for z in zonen.values() if (z.get("land") or "DE") == land and z.get("standard") == "ja" and aktiv(z)]
    if len(std) == 1:
        z = std[0]
        out.update(zone=z, status="standard",
                   text=f"PLZ {plz} keiner Zone zugeordnet – Standardzone {z['zone_id']} {z.get('bezeichnung') or ''}")
    elif len(std) > 1:
        out["text"] = f"PLZ {plz} keiner Zone zugeordnet und mehrere Standardzonen für {land}: " + ", ".join(
            z["zone_id"] for z in std)
    else:
        out["text"] = f"PLZ {plz} ({land}) keiner Zone zugeordnet und keine Standardzone für {land}"
    return out


def _regeln(daten, land, richtung, kundennr, dienstleister):
    for r in daten.get("plz", []):
        if (r.get("land") or "DE") != land or r.get("richtung") not in (None, "", "beide", richtung):
            continue
        if r.get("dienstleister") and r["dienstleister"] != dienstleister:
            continue
        if r.get("kundennr") and r["kundennr"] != kundennr:
            continue
        yield r


def _standardzonen(zonen, land):
    return [z for z in zonen.values() if (z.get("land") or "DE") == land and z.get("standard") == "ja" and aktiv(z)]


def _bereich_finden(daten, land, bereich, richtung, kundennr, dienstleister, zonen, out):
    """Zone(n) eines PLZ-Bereichs: Regeln der vorrangigen Ebene (Kunde + Dienstleister, Kunde, Dienstleister,
    allgemein), die den Bereich ganz oder teilweise abdecken; deckt keine den ganzen Bereich, gilt für den Rest die
    Standardzone. Mehrere Zonen -> bereich_zonen (teurere gewinnt in rechnen())."""
    kand = []
    for r in _regeln(daten, land, richtung, kundennr, dienstleister):
        lage = regel_im_bereich(r, bereich)
        if not lage:
            continue
        z = zonen.get(r.get("zone_id"))
        if z and aktiv(z):
            kand.append((r, lage))
        else:
            out["hinweise"].append(f"{regel_text(r)}: Zone {r.get('zone_id')} inaktiv oder unbekannt, nicht verwendet")
    if kand:
        ebene = min(regel_rang(r)[0] for r, _ in kand)
        kand = sorted([(r, lage) for r, lage in kand if regel_rang(r)[0] == ebene], key=lambda x: regel_rang(x[0]))
    ganz = [r for r, lage in kand if lage == "ganz"]
    teil = [r for r, lage in kand if lage == "teil"]
    if ganz:     # die engste Regel über den ganzen Bereich, dazu abweichende Teilbereiche
        regeln = [ganz[0]] + teil
    else:
        regeln = teil
    ids = []
    for r in regeln:
        if r["zone_id"] not in ids:
            ids.append(r["zone_id"])
    rest = ""
    if not ganz:
        std = _standardzonen(zonen, land)
        if len(std) == 1 and (std[0]["zone_id"] not in ids):
            ids.append(std[0]["zone_id"])
            rest = f" (Rest des Bereichs: Standardzone {std[0]['zone_id']})"
    if not ids:
        out["text"] = f"PLZ-Bereich {bereich}… ({land}) keiner Zone zugeordnet und keine Standardzone für {land}"
        return out
    erst = zonen[ids[0]]
    regel = next((r for r in regeln if r["zone_id"] == ids[0]), None)
    out.update(zone=erst, regel=regel, status="ok" if regel else "standard", bereich_zonen=[zonen[i] for i in ids])
    if len(ids) == 1:
        out["text"] = (f"PLZ-Bereich {bereich}…: Zone {erst['zone_id']} {erst.get('bezeichnung') or ''} "
                       f"({regel_text(regel)})" if regel else
                       f"PLZ-Bereich {bereich}… keiner Zone zugeordnet – Standardzone {erst['zone_id']} "
                       f"{erst.get('bezeichnung') or ''}").replace("  ", " ")
    else:
        out["text"] = f"PLZ-Bereich {bereich}… liegt in den Zonen {', '.join(ids)}{rest}: es gilt die teurere"
    return out


# ------------------------------------------------------------------ Ladehilfsmittel und Gewicht
def lht_werte(eintraege, lht_zeilen):
    """Ladungsträger der Sendung mit Volumen, Stellplätzen, Lademetern und Eigengewicht.
    Ergebnis: {je: [...], anzahl, volumen (None, wenn ein Maß fehlt), stellplaetze, lademeter, eigengewicht,
    brutto_lht (Summe Bruttogewicht je Stück, nur wenn bei allen angegeben), nutzlast, hinweise}"""
    lht = {z["lht_id"]: z for z in lht_zeilen if z.get("lht_id")}
    je, hinweise = [], []
    for e in eintraege or ():
        n = int(_n(e.get("anzahl")))
        if n <= 0:
            continue
        z = lht.get(e.get("lht_id"))
        if not z:
            hinweise.append(f"Ladehilfsmittel '{e.get('lht_id')}' unbekannt")
            continue
        l, b, h = z.get("laenge"), z.get("breite"), z.get("hoehe")
        stapel = int(z["stapelfaktor"]) if z.get("stapelbar") == "ja" and _n(z.get("stapelfaktor")) > 1 else 1
        plaetze = math.ceil(n / stapel)
        je.append(dict(lht_id=z["lht_id"], art=z.get("art"), bezeichnung=z.get("bezeichnung") or z["lht_id"], anzahl=n,
                       masse=(l, b, h), volumen=l * b * h / 1e9 * n if l and b and h else None,
                       stellplaetze=plaetze * (z.get("stellplaetze") or 1),
                       lademeter=plaetze * l * b / 1e6 / 2.4 if l and b else None,
                       eigengewicht=_n(z.get("eigengewicht")) * n,
                       brutto=_n(e["gewicht"]) * n if _zahl(e.get("gewicht")) else None,
                       nutzlast=_n(z.get("nutzlast")) * n if z.get("nutzlast") else None, stapel=stapel))
    vol = [x["volumen"] for x in je]
    ldm = [x["lademeter"] for x in je]
    return dict(je=je, anzahl=sum(x["anzahl"] for x in je),
                volumen=sum(vol) if je and None not in vol else None,
                stellplaetze=sum(x["stellplaetze"] for x in je),
                lademeter=sum(ldm) if je and None not in ldm else None,
                eigengewicht=sum(x["eigengewicht"] for x in je),
                brutto_lht=sum(x["brutto"] for x in je) if je and all(x["brutto"] is not None for x in je) else None,
                nutzlast=sum(x["nutzlast"] for x in je) if je and all(x["nutzlast"] for x in je) else None,
                hinweise=hinweise)


def packvorschlag(teile, lht_zeilen, standard_id, langgut_id):
    """Vorschlag Ladungsträger aus den Teilen [(Gewicht gesamt kg, Länge mm)]: Teile länger als die max. Teillänge
    des Standard-Ladungsträgers kommen auf Langgut; Anzahl je Ladungsträger = Gewicht / Nutzlast aufgerundet,
    mindestens 1. Ergebnis: ([{lht_id, anzahl}], hinweise)"""
    lht = {z["lht_id"]: z for z in lht_zeilen if z.get("lht_id") and aktiv(z)}
    std, lg = lht.get(standard_id), lht.get(langgut_id)
    hinweise = []
    if not std:
        return [], [f"Ladungsträger für den Packvorschlag '{standard_id or ''}' fehlt (Frachtkosten → Historie und "
                    "Einstellungen); Ladehilfsmittel bitte von Hand eintragen"]
    g_std = g_lg = 0.0
    zu_lang = 0
    for g, laenge in teile:
        if _n(std.get("max_laenge")) and _n(laenge) > std["max_laenge"]:
            if lg:
                g_lg += _n(g)
                if _n(lg.get("max_laenge")) and _n(laenge) > lg["max_laenge"]:
                    zu_lang += 1
            else:
                g_std += _n(g)
                zu_lang += 1
        else:
            g_std += _n(g)
    if zu_lang:
        hinweise.append(f"{zu_lang} Position(en) länger als der Ladungsträger erlaubt: Sonderladung prüfen")
    out = []
    for z, g in ((std, g_std), (lg, g_lg)):
        if z and g > EPS:
            n = math.ceil(g / z["nutzlast"] - EPS) if _n(z.get("nutzlast")) else 1
            out.append(dict(lht_id=z["lht_id"], anzahl=max(1, n)))
    return out, hinweise


def gewicht(sendung, lw):
    """Netto, Verpackung, Brutto der Sendung (ohne Tarifregeln)."""
    netto = _n(sendung.get("netto"))
    verp = sendung.get("verpackung")
    verpackung = _n(verp) if _zahl(verp) else lw["eigengewicht"]
    brutto = lw["brutto_lht"] if lw["brutto_lht"] is not None else netto + verpackung
    return dict(netto=netto, verpackung=verpackung, brutto=brutto,
                quelle="Bruttogewicht je Ladungsträger" if lw["brutto_lht"] is not None else "Netto + Verpackung")


def frachtpflichtig(tarif, g, lw, manuell=None):
    """Frachtpflichtiges Gewicht nach Tarif: Höchstwert aus Brutto und den genutzten Faktoren, dann Rundung.
    Ergebnis: (kg, Erklärung)"""
    if _zahl(manuell) and manuell > 0:
        return manuell, f"von Hand: {z2(manuell, 1)} kg (Brutto {z2(g['brutto'], 1)} kg)"
    teile = [(g["brutto"], f"Brutto {z2(g['brutto'], 1)} kg")]
    if _n(tarif.get("faktor_m3")) and lw["volumen"] is not None:
        teile.append((lw["volumen"] * tarif["faktor_m3"],
                      f"Volumen {z2(lw['volumen'], 3)} m³ × {z2(tarif['faktor_m3'], 0)} kg"))
    if _n(tarif.get("faktor_stellplatz")) and lw["stellplaetze"]:
        teile.append((lw["stellplaetze"] * tarif["faktor_stellplatz"],
                      f"{z2(lw['stellplaetze'], 2)} Stellplätze × {z2(tarif['faktor_stellplatz'], 0)} kg"))
    if _n(tarif.get("faktor_ldm")) and lw["lademeter"]:
        teile.append((lw["lademeter"] * tarif["faktor_ldm"],
                      f"{z2(lw['lademeter'], 2)} Lademeter × {z2(tarif['faktor_ldm'], 0)} kg"))
    kg, wahl = max(teile, key=lambda t: t[0])
    text = wahl if len(teile) == 1 else wahl + " (größter Wert aus " + ", ".join(t[1] for t in teile) + ")"
    r = _n(tarif.get("rundung_kg"))
    if r > 0:
        gerundet = math.ceil(kg / r - 1e-9) * r
        if abs(gerundet - kg) > EPS:
            text += f", aufgerundet auf {z2(r, 1)} kg"
        kg = gerundet
    return kg, text


# ------------------------------------------------------------------ Tarife
def tarif_rang(t):
    art = "Kundentarif" if t.get("kundennr") else t.get("tarifart")
    return RANG.get(art, 3), t.get("prioritaet") or 100


def tarif_passt(t, s, zone):
    """None, wenn der Tarif für die Sendung gilt, sonst der Grund."""
    datum = s.get("datum") or heute()
    if not aktiv(t):
        return "inaktiv"
    if not gueltig(t, datum):
        return "am Datum nicht gültig"
    land = (s.get("land") or "DE").upper()
    if liste(t.get("laender")) and land not in liste(t.get("laender")):
        return f"gilt nicht für {land}"
    if liste(t.get("zonen")) and (not zone or zone["zone_id"] not in liste(t.get("zonen"))):
        return "gilt nicht für diese Zone"
    if t.get("versandart") and s.get("versandart") and t["versandart"] != s["versandart"]:
        return f"Versandart {t['versandart']}"
    if s.get("dienstleister") and t.get("dienstleister") != s["dienstleister"]:
        return "anderer Dienstleister"
    if t.get("kundennr") and t["kundennr"] != s.get("kundennr"):
        return "Tarif eines anderen Kunden"
    if t.get("tarifart") == "Kundentarif" and not t.get("kundennr"):
        return "Kundentarif ohne Kundennummer"
    return None


def tarife_finden(daten, s, zone):
    """Passende Tarife nach Rang. Ergebnis: (passend, gewaehlt oder None, Status 'ok'/'auswahl'/'fehler', Text)."""
    passend = []
    for t in daten.get("tarife", []):
        if not t.get("tarif_id") or tarif_passt(t, s, zone):
            continue
        if RANG.get(t.get("tarifart"), 3) == 9 and t["tarif_id"] != s.get("tarif_id"):
            continue                       # interne Verrechnungstarife nur, wenn ausdrücklich gewählt
        passend.append(t)
    passend.sort(key=lambda t: (tarif_rang(t), t["tarif_id"]))
    if s.get("tarif_id"):
        t = next((t for t in daten.get("tarife", []) if t.get("tarif_id") == s["tarif_id"]), None)
        if t is None:
            return passend, None, "fehler", f"Tarif {s['tarif_id']} unbekannt"
        grund = tarif_passt(t, s, zone)
        if grund:
            return passend, None, "fehler", f"Gewählter Tarif {t['tarif_id']} passt nicht: {grund}"
        return passend, t, "ok", "von Hand gewählt"
    if not passend:
        return [], None, "fehler", "Kein Tarif passt (Land, Zone, Versandart, Dienstleister, Kunde, Datum prüfen)"
    erst = passend[0]
    gleich = [t for t in passend[1:] if tarif_rang(t) == tarif_rang(erst)]
    if gleich:
        return passend, None, "auswahl", ("Mehrere Tarife passen gleich gut: " + ", ".join(
            t["tarif_id"] for t in [erst] + gleich) + ". Bitte einen Tarif wählen oder eine Priorität vergeben.")
    art = "Kundentarif" if erst.get("kundennr") else (erst.get("tarifart") or "Standardtarif")
    return passend, erst, "ok", f"automatisch: {art}" + (
        f", Priorität {erst['prioritaet']}" if erst.get("prioritaet") else "") + (
        f" (vor {len(passend) - 1} weiteren)" if len(passend) > 1 else "")


# ------------------------------------------------------------------ Grundfracht
def grundfracht(tarif, preise, zone, lw, kg, s):
    """Grundfracht aus den Preisstaffeln. Ergebnis: (zeilen [(Text, Betrag, Erklärung)], staffeln [Text],
    warnungen, fehler)"""
    modell = tarif.get("modell") or "Individueller Tarif"
    erlaubt = ERLAUBT.get(modell)
    zid = zone["zone_id"] if zone else None
    gruppen, warnungen, fehler = {}, [], []
    for p in preise:
        if p.get("tarif_id") != tarif["tarif_id"] or not p.get("bezug"):
            continue
        if p.get("zone_id") and p["zone_id"] != zid:
            continue
        if erlaubt is not None and p["bezug"] not in erlaubt:
            warnungen.append(f"Preiszeile mit Bezug {p['bezug']} passt nicht zum {modell} und wird nicht verwendet")
            continue
        bezug = "Gewicht" if p["bezug"] in GEWICHT else p["bezug"]      # kg und 100 kg: eine Staffel, bis in kg
        gruppen.setdefault((bezug, p.get("lht_art") or ""), {}).setdefault(bool(p.get("zone_id")), []).append(p)
    gruppen = {k: v[True] if True in v else v[False] for k, v in gruppen.items()}     # Zone vor 'alle Zonen'
    zeilen, staffeln = [], []
    if not gruppen:
        fehler.append(f"Tarif {tarif['tarif_id']} hat keine Preise für Zone {zid or '–'}")
        return zeilen, staffeln, warnungen, fehler
    if modell == "Gewichtstarif" and not any(b == "Gewicht" for b, _ in gruppen):
        fehler.append(f"Gewichtstarif {tarif['tarif_id']} ohne Gewichtsstaffel für Zone {zid or '–'}")
    lht_gruppen = [(b, a) for b, a in gruppen if b in LHT_BEZUG]
    if modell in ("Palettentarif", "Gitterboxtarif"):
        if not lw["anzahl"]:
            fehler.append(f"{modell}: keine Ladehilfsmittel angegeben")
        if not lht_gruppen:
            fehler.append(f"{modell} {tarif['tarif_id']} ohne Preise je Ladungsträger oder Stellplatz")
    if lht_gruppen:                 # jede Art in der Sendung braucht eine Preiszeile
        abgedeckt = {a for _, a in lht_gruppen}
        for x in lw["je"]:
            if x["art"] not in abgedeckt and "" not in abgedeckt:
                fehler.append(f"Tarif {tarif['tarif_id']} ohne Preis für {x['art']} ({x['anzahl']} Stück)")
    for (bezug, art), zeilen_g in sorted(gruppen.items(), key=lambda kv: (BEZUG_FOLGE.get(kv[0][0], 9), kv[0][1])):
        if bezug in LHT_BEZUG:
            eigene = {a for b, a in gruppen if b in LHT_BEZUG and a}     # eigene Preise in einer LHT-Staffel
            dabei = [x for x in lw["je"] if (x["art"] == art if art else x["art"] not in eigene)]
            if not dabei:
                continue
            m = sum(x["anzahl"] if bezug == "Ladungsträger" else x["stellplaetze"] for x in dabei)
            einheit = ("Stück " + (art or "Ladungsträger")) if bezug == "Ladungsträger" else \
                ("Stellplätze" + (f" {art}" if art else ""))
        elif bezug == "Sendung":
            m, einheit = 1, "Sendung"
        elif bezug == "Gewicht":
            m, einheit = kg, "kg"
        elif bezug == "km":
            km = s.get("km") if _zahl(s.get("km")) else (zone or {}).get("km")
            if not _zahl(km):
                fehler.append("Entfernung fehlt (km in der Sendung oder in der Zone)")
                continue
            m, einheit = km, "km"
        elif bezug == "Lademeter":
            if lw["lademeter"] is None:
                fehler.append("Lademeter fehlen (Maße der Ladungsträger)")
                continue
            m, einheit = lw["lademeter"], "Lademeter"
        else:
            continue
        folge = sorted(zeilen_g, key=lambda p: (p.get("bis") is None, _n(p.get("bis"))))
        stufe = next((p for p in folge if p.get("bis") is None or m <= p["bis"] + EPS), None)
        titel = {"Sendung": "Grundpreis je Sendung"}.get(bezug) or (
            f"Grundfracht {art}" if art else ("Grundfracht" if bezug == "Gewicht" else f"Grundfracht {bezug}"))
        mtext = z2(m, 2 if bezug == "Lademeter" else (1 if bezug == "Gewicht" else 0))
        if stufe is None:
            fehler.append(f"{titel}: {mtext} {einheit} über der letzten Stufe (bis {zahl_als_text(folge[-1]['bis'])}) – "
                          "individuelle Berechnung nötig")
            continue
        grenze = (f"bis {zahl_als_text(stufe['bis'])} {einheit.split()[-1] if bezug != 'Gewicht' else 'kg'}"
                  if stufe.get("bis") is not None else "ohne Obergrenze")
        staffeln.append(f"{titel}: Stufe {grenze}" + (f" (Zone {stufe['zone_id']})" if stufe.get("zone_id")
                                                                else " (alle Zonen)"))
        if stufe.get("preis") is None:
            fehler.append(f"{titel}: Stufe {grenze} ohne Preis – individuelle Berechnung nötig")
            continue
        if stufe.get("preisart") == "je Einheit":
            if stufe["bezug"] == "100 kg":
                betrag = stufe["preis"] * m / 100
                erkl = f"{mtext} kg / 100 × {z2(stufe['preis'])} je 100 kg (Stufe {grenze})"
            else:
                betrag = stufe["preis"] * m
                erkl = f"{mtext} {einheit} × {z2(stufe['preis'])} (Stufe {grenze})"
        else:
            betrag = stufe["preis"]
            erkl = f"{mtext} {einheit}, Festpreis der Stufe {grenze}"
        zeilen.append((titel, betrag, erkl))
    return zeilen, staffeln, warnungen, fehler


GEWICHT = ("kg", "100 kg")
BEZUG_FOLGE = {"Sendung": 0, "Gewicht": 1, "km": 3, "Lademeter": 4, "Stellplatz": 5, "Ladungsträger": 6}


# ------------------------------------------------------------------ Zuschläge
def zuschlag_ebene(z):
    if z.get("kundennr"):
        return 0
    if z.get("dienstleister"):
        return 1
    if liste(z.get("tarife")):
        return 2
    return 3


def zuschlag_kandidat(z, s, tarif, zone):
    """None, wenn der Zuschlag für Sendung, Tarif und Zone in Frage kommt (ohne Mengenbedingungen), sonst Grund."""
    if not aktiv(z) or not z.get("zuschlag_id"):
        return "inaktiv"
    if not gueltig(z, s.get("datum") or heute()):
        return "am Datum nicht gültig"
    land = (s.get("land") or "DE").upper()
    if liste(z.get("laender")) and land not in liste(z.get("laender")):
        return f"gilt nicht für {land}"
    if liste(z.get("zonen")) and (not zone or zone["zone_id"] not in liste(z.get("zonen"))):
        return "gilt nicht für diese Zone"
    if liste(z.get("tarife")) and tarif["tarif_id"] not in liste(z.get("tarife")):
        return "gilt nicht für diesen Tarif"
    if z.get("dienstleister") and z["dienstleister"] != tarif.get("dienstleister"):
        return "gilt für einen anderen Dienstleister"
    if z.get("kundennr") and z["kundennr"] != s.get("kundennr"):
        return "gilt für einen anderen Kunden"
    return None


def bedingung_erfuellt(z, s, kg, zone):
    """(ja/nein, Text) für die Bedingung des Zuschlags."""
    b = z.get("bedingung") or "immer"
    leist = s.get("leistungen") or {}
    if b == "immer":
        return True, ""
    if b == "nur wenn gewählt":
        return z["zuschlag_id"] in leist, "nicht gewählt"
    g = _n(z.get("grenze"))
    if b == "Gewicht unter":
        return kg < g - EPS, f"Gewicht {z2(kg, 1)} kg nicht unter {z2(g, 1)} kg"
    if b == "Gewicht über":
        return kg > g + EPS, f"Gewicht {z2(kg, 1)} kg nicht über {z2(g, 1)} kg"
    if b == "Teillänge über":
        lang = _n(s.get("max_laenge"))
        return lang > g + EPS, f"längstes Teil {z2(lang, 0)} mm nicht über {z2(g, 0)} mm"
    if b.startswith("Zonenart"):
        return bool(zone and zone.get("art") in SONDERZONEN), "keine Insel, kein Rand- oder Sondergebiet"
    return False, f"Bedingung {b} unbekannt"


def dieselpreis(daten, datum):
    """Letzter Dieselpreis bis zum Datum (Zeile) oder None."""
    alle = [d for d in daten.get("dieselpreise", []) if d.get("datum") and d["datum"] <= datum and _zahl(d.get("preis"))]
    return max(alle, key=lambda d: d["datum"]) if alle else None


def zuschlaege(snap, s, kg, lw, grund, leistung_basis=None):
    """Zuschläge berechnen. grund = Grundfracht nach Rabatt und Mindestfracht (EUR).
    Ergebnis: (zeilen [(Text, Betrag, Erklärung, Zuschlag-ID, Stufe)], nicht_angewendet [Text], warnungen)"""
    tarif, zone = snap["tarif"], snap["zone"]
    leist = s.get("leistungen") or {}
    kand, nicht, warnungen = [], [], []
    for z in snap.get("zuschlaege", []):
        ok, grund_n = bedingung_erfuellt(z, s, kg, zone)
        if not ok:
            if (z.get("bedingung") or "immer") != "nur wenn gewählt":
                nicht.append(f"{z.get('bezeichnung') or z['zuschlag_id']}: {grund_n}")
            continue
        kand.append(z)
    # gleicher Typ mehrfach: der speziellere gilt ('sonstiger Zuschlag' nie zusammengefasst)
    beste = {}
    for z in kand:
        if z.get("typ") == "sonstiger Zuschlag":
            continue
        b = beste.get(z.get("typ"))
        if b is None or (zuschlag_ebene(z), z["zuschlag_id"]) < (zuschlag_ebene(b), b["zuschlag_id"]):
            beste[z.get("typ")] = z
    gilt = []
    for z in kand:
        b = beste.get(z.get("typ"))
        if b is not None and b is not z:
            nicht.append(f"{z.get('bezeichnung') or z['zuschlag_id']}: überdeckt durch {b.get('bezeichnung') or b['zuschlag_id']} "
                         f"({ZUSCHLAG_EBENE[zuschlag_ebene(b)]})")
        else:
            gilt.append(z)
    prozent = [z for z in gilt if z.get("berechnung") in ("%", "Dieselstaffel")]
    euro_z = [z for z in gilt if z not in prozent]
    zeilen, betrag = [], {}

    def begrenzen(z, w, erkl):
        if _zahl(z.get("mindest")) and w < z["mindest"]:
            return z["mindest"], erkl + f", angehoben auf Mindestbetrag {euro(z['mindest'])}"
        if _zahl(z.get("hoechst")) and w > z["hoechst"]:
            return z["hoechst"], erkl + f", begrenzt auf Höchstbetrag {euro(z['hoechst'])}"
        return w, erkl

    for z in euro_z:                     # Stufe 1
        art, wert = z.get("berechnung"), _n(z.get("wert"))
        name = z.get("bezeichnung") or z["zuschlag_id"]
        menge, einheit = {"€ je Sendung": (1, "Sendung"), "€ je kg": (kg, "kg"), "€ je 100 kg": (kg / 100, "× 100 kg"),
                          "€ je Ladungsträger": (lw["anzahl"], "Ladungsträger"),
                          "€ je Stellplatz": (lw["stellplaetze"], "Stellplätze")}.get(art, (None, ""))
        if art == "€ je Stunde":
            menge = leist.get(z["zuschlag_id"]) if _zahl(leist.get(z["zuschlag_id"])) else 1
            einheit = "h"
        if menge is None:
            warnungen.append(f"{name}: Berechnungsart {art or '–'} unbekannt")
            continue
        w = wert * menge
        erkl = f"{euro(wert)} je Sendung" if art == "€ je Sendung" else f"{z2(menge, 2)} {einheit} × {euro(wert)}"
        w, erkl = begrenzen(z, w, erkl)
        betrag[z["zuschlag_id"]] = w
        zeilen.append((name, w, erkl, z["zuschlag_id"], 1))
    stufe1 = sum(betrag.values())
    diesel = snap.get("dieselpreis")
    for z in prozent:                    # Stufe 2
        name = z.get("bezeichnung") or z["zuschlag_id"]
        basis = z.get("basis") or "Grundfracht"
        if basis == "Grundfracht":
            b, btext = grund, "Grundfracht"
        elif basis == "Grundfracht + Leistungszuschläge":
            b, btext = grund + stufe1, "Grundfracht + Leistungszuschläge"
        else:
            ids = liste(z.get("basis_liste"))
            falsch = [i for i in ids if i != "Grundfracht" and i not in betrag]
            fremd_prozent = [i for i in falsch if any(p["zuschlag_id"] == i for p in prozent)]
            if fremd_prozent:
                warnungen.append(f"{name}: Prozentzuschlag nicht auf Prozentzuschlag ({', '.join(fremd_prozent)}) – "
                                 "dieser Teil der Grundlage wird nicht verwendet")
            b = (grund if "Grundfracht" in ids else 0) + sum(betrag.get(i, 0) for i in ids)
            btext = " + ".join(ids)
        if z.get("berechnung") == "Dieselstaffel":
            if not diesel:
                warnungen.append(f"{name}: kein Dieselpreis bis zum Datum gepflegt – Zuschlag nicht berechnet")
                continue
            stufen = sorted((d for d in snap.get("dieselstaffel", []) if d.get("zuschlag_id") == z["zuschlag_id"]
                             and _zahl(d.get("preis_ab"))), key=lambda d: d["preis_ab"])
            if not stufen:
                warnungen.append(f"{name}: Dieselstaffel ohne Schwellen – Zuschlag nicht berechnet")
                continue
            treffer = [d for d in stufen if diesel["preis"] >= d["preis_ab"] - EPS]
            if not treffer:
                nicht.append(f"{name}: Dieselpreis {z2(diesel['preis'], 3)} €/l unter der ersten Schwelle")
                continue
            proz = _n(treffer[-1].get("wert"))
            erkl = (f"{z2(proz)} % auf {btext} {euro(b)} (Dieselpreis {z2(diesel['preis'], 3)} €/l vom "
                    f"{_datum(diesel['datum'])}, Schwelle ab {z2(treffer[-1]['preis_ab'], 3)} €/l)")
        else:
            proz = _n(z.get("wert"))
            erkl = f"{z2(proz)} % auf {btext} {euro(b)}"
        w, erkl = begrenzen(z, b * proz / 100, erkl)
        zeilen.append((name, w, erkl, z["zuschlag_id"], 2))
    return zeilen, nicht, warnungen


def _datum(iso):
    try:
        return datetime.date.fromisoformat(iso).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return str(iso or "")


# ------------------------------------------------------------------ Snapshot und Berechnung
def snapshot(daten, s, zone_e, zone_v, tarif):
    """Alle Werte, die eine Berechnung mit diesem Tarif braucht (spätere Änderungen der Stammdaten wirken nicht)."""
    datum = s.get("datum") or heute()
    zus = [dict(z) for z in daten.get("zuschlaege", []) if not zuschlag_kandidat(z, s, tarif, zone_e["zone"])]
    ids = {z["zuschlag_id"] for z in zus}
    waehrung = (tarif.get("waehrung") or "EUR").upper()
    kurs = next((w for w in daten.get("waehrungen", []) if (w.get("waehrung") or "").upper() == waehrung), None)
    return dict(version=VERSION, datum=datum, tarif=dict(tarif),
                preise=[dict(p) for p in daten.get("preise", []) if p.get("tarif_id") == tarif["tarif_id"]],
                zone=zone_e["zone"], zone_text=zone_e["text"], zone_status=zone_e["status"],
                regel=zone_e["regel"], zone_versand=(zone_v or {}).get("zone"),
                zone_versand_text=(zone_v or {}).get("text"),
                zuschlaege=zus, dieselpreis=dieselpreis(daten, datum),
                dieselstaffel=[dict(d) for d in daten.get("dieselstaffel", []) if d.get("zuschlag_id") in ids],
                waehrung=waehrung, kurs=None if waehrung == "EUR" else (kurs or {}).get("kurs"),
                kurs_stand=(kurs or {}).get("stand"), lht=[dict(z) for z in daten.get("lht", [])])


def kalkulieren(snap, s):
    """Berechnung einer Sendung mit einem Snapshot (Zone und Tarif stehen fest). Ergebnis siehe rechnen()."""
    tarif = snap["tarif"]
    warnungen, fehler, hinweise = [], [], []
    lw = lht_werte(s.get("lht"), snap.get("lht", []))
    hinweise += lw["hinweise"]
    g = gewicht(s, lw)
    if lw["nutzlast"] is not None and g["netto"] > lw["nutzlast"] + EPS:
        warnungen.append(f"Nettogewicht {z2(g['netto'], 1)} kg über der Nutzlast der Ladungsträger "
                         f"({z2(lw['nutzlast'], 0)} kg)")
    kg, kg_text = frachtpflichtig(tarif, g, lw, s.get("frachtpflichtig"))
    if g["brutto"] <= EPS and lw["anzahl"] == 0:
        fehler.append("Kein Gewicht und keine Ladehilfsmittel angegeben")
    out = dict(gewicht=dict(g, frachtpflichtig=kg, erklaerung=kg_text), lht=lw, zeilen=[], staffeln=[],
               zuschlaege=[], nicht_angewendet=[], gesamt=None, waehrung=snap.get("waehrung"), kurs=snap.get("kurs"))
    if "BEISPIEL" in (tarif.get("tarif_id") or "") + (tarif.get("bemerkung") or ""):
        warnungen.append("Beispieltarif – keine echten Preise")
    kurs = 1.0
    if snap.get("waehrung") not in (None, "EUR"):
        if not _zahl(snap.get("kurs")) or snap["kurs"] <= 0:
            fehler.append(f"Kein Umrechnungskurs für {snap['waehrung']} (Frachtkosten → Zuschläge → Währungen)")
        else:
            kurs = snap["kurs"]
            hinweise.append(f"Tarif in {snap['waehrung']}, umgerechnet mit 1 {snap['waehrung']} = "
                            f"{z2(kurs, 4)} €" + (f" (Stand {_datum(snap['kurs_stand'])})" if snap.get("kurs_stand")
                                                   else ""))
    gz, staffeln, w2, f2 = grundfracht(tarif, snap["preise"], snap["zone"], lw, kg, s)
    warnungen += w2
    fehler += f2
    out["staffeln"] = staffeln
    tw = snap.get("waehrung") or "EUR"

    def umrechnen(betrag, erkl):
        if kurs == 1.0:
            return betrag, erkl
        return betrag * kurs, erkl + f" = {z2(betrag)} {tw} × {z2(kurs, 4)}"

    zeilen = [(t,) + umrechnen(b, e) for t, b, e in gz]
    grund = sum(b for _, b, _ in zeilen)
    rabatt = _n(tarif.get("rabatt"))
    if rabatt and grund:
        zeilen.append((f"Rabatt {z2(rabatt, 1)} %", -grund * rabatt / 100, f"{z2(rabatt, 1)} % auf {euro(grund)}"))
        grund -= grund * rabatt / 100
    mind = _n(tarif.get("mindestfracht")) * kurs
    if mind and grund < mind - EPS and not f2:
        zeilen.append(("Anhebung auf Mindestfracht", mind - grund, f"Mindestfracht {euro(mind)}"))
        grund = mind
    zus, nicht, w3 = zuschlaege(snap, s, kg, lw, grund)
    warnungen += w3
    out["nicht_angewendet"] = nicht
    out["zuschlaege"] = [dict(name=t, betrag=b, erklaerung=e, zuschlag_id=i, stufe=st) for t, b, e, i, st in zus]
    zeilen += [(t, b, e) for t, b, e, _, _ in zus]
    out["zeilen"] = [dict(text=t, betrag=kaufm_runden(b, 2), erklaerung=e) for t, b, e in zeilen]
    out["grundfracht"] = kaufm_runden(grund, 2)
    if not fehler:
        out["gesamt"] = kaufm_runden(sum(z["betrag"] for z in out["zeilen"]), 2)
    out.update(warnungen=warnungen, fehler=fehler, hinweise=hinweise)
    return out


def rechnen(daten, sendung):
    """Frachtkosten einer Sendung (siehe _rechnen). Liegt ein PLZ-Bereich in mehreren Zonen, wird mit jeder Zone
    gerechnet und die teurere genommen (Hinweis mit allen Beträgen)."""
    s = dict(sendung)
    s["land"] = (s.get("land") or "DE").upper()
    ze = zone_finden(daten, s["land"], s.get("plz"), "Empfang", s.get("kundennr"), s.get("dienstleister"))
    if len(ze["bereich_zonen"]) < 2:
        return _rechnen(daten, s, ze)
    ergebnisse = []
    for z in ze["bereich_zonen"]:
        zi = dict(ze, zone=z, status="ok", bereich_zonen=[], text=f"{ze['text']}: Zone {z['zone_id']} "
                  f"{z.get('bezeichnung') or ''}".rstrip())
        ergebnisse.append(_rechnen(daten, s, zi))
    gerechnet = [e for e in ergebnisse if e.get("gesamt") is not None]
    if not gerechnet:
        return ergebnisse[0]
    out = max(gerechnet, key=lambda e: e["gesamt"])
    out["hinweise"].append("PLZ-Bereich in mehreren Zonen, die teurere gilt: " + "; ".join(
        f"Zone {e['zone_empfang']['zone']['zone_id']} {euro(e['gesamt'])}" if e.get("gesamt") is not None
        else f"Zone {e['zone_empfang']['zone']['zone_id']} nicht berechnet" for e in ergebnisse))
    if len(gerechnet) < len(ergebnisse):
        out["warnungen"].append("In einem Teil des PLZ-Bereichs ist die Fracht nicht berechenbar (siehe Hinweise)")
        out["status"] = "fehler" if out["fehler"] else "warnung"
    return out


def _rechnen(daten, sendung, ze):
    """Frachtkosten einer Sendung. Ergebnis: dict mit status ('ok', 'warnung', 'fehler', 'auswahl'), gesamt (€ oder
    None), zeilen [{text, betrag, erklaerung}], zone_empfang, zone_versand, tarif, tarif_grund, weitere_tarife,
    gewicht, lht, staffeln, zuschlaege, nicht_angewendet, warnungen, fehler, hinweise, snapshot, eingaben."""
    s = dict(sendung)
    s.setdefault("datum", heute())
    s["land"] = (s.get("land") or "DE").upper()
    zv = zone_finden(daten, s.get("absender_land") or "DE", s.get("absender_plz"), "Versand", s.get("kundennr"),
                     s.get("dienstleister")) if s.get("absender_plz") else None
    out = dict(status="fehler", gesamt=None, zeilen=[], zone_empfang=ze, zone_versand=zv, tarif=None, tarif_grund="",
               weitere_tarife=[], gewicht=None, lht=None, staffeln=[], zuschlaege=[], nicht_angewendet=[],
               warnungen=[], fehler=[], hinweise=list(ze["hinweise"]), snapshot=None, eingaben=s, datum=s["datum"],
               version=VERSION)
    if s.get("lieferbedingung") in OHNE_FRACHT:
        out.update(status="ok", gesamt=0.0, hinweise=out["hinweise"] + [
            f"Lieferbedingung {s['lieferbedingung']}: die Fracht trägt der Kunde, Frachtkosten 0 €"])
        return out
    if ze["status"] in ("fehler", "mehrdeutig"):
        out["fehler"].append(ze["text"])
        return out
    if ze["status"] == "standard":
        out["warnungen"].append(ze["text"])
    passend, tarif, st, text = tarife_finden(daten, s, ze["zone"])
    out["tarif_grund"] = text
    weitere = []
    for t in passend:
        if tarif is not None and t["tarif_id"] == tarif["tarif_id"]:
            continue
        e = kalkulieren(snapshot(daten, s, ze, zv, t), s)
        weitere.append(dict(tarif_id=t["tarif_id"], bezeichnung=t.get("bezeichnung"), gesamt=e["gesamt"],
                            fehler=e["fehler"][:1]))
    out["weitere_tarife"] = weitere
    if tarif is None:
        out["status"] = "auswahl" if st == "auswahl" else "fehler"
        out["fehler"].append(text)
        return out
    snap = snapshot(daten, s, ze, zv, tarif)
    e = kalkulieren(snap, s)
    out.update({k: v for k, v in e.items() if k not in ("warnungen", "fehler", "hinweise")})
    out["warnungen"] += e["warnungen"]
    out["fehler"] += e["fehler"]
    out["hinweise"] += e["hinweise"]
    out["tarif"] = dict(tarif_id=tarif["tarif_id"], bezeichnung=tarif.get("bezeichnung"),
                        dienstleister=tarif.get("dienstleister"), version=tarif.get("version"),
                        modell=tarif.get("modell"), tarifart=tarif.get("tarifart") or "Standardtarif")
    out["snapshot"] = snap
    out["status"] = "fehler" if out["fehler"] else ("warnung" if out["warnungen"] else "ok")
    return out


def nachrechnen(snap, sendung):
    """Mit gespeichertem Snapshot neu rechnen (Zone und Tarif wie gespeichert, z. B. je Staffelmenge)."""
    s = dict(sendung)
    s.setdefault("datum", snap.get("datum") or heute())
    if s.get("lieferbedingung") in OHNE_FRACHT:
        return dict(status="ok", gesamt=0.0, zeilen=[], warnungen=[], fehler=[], hinweise=[
            f"Lieferbedingung {s['lieferbedingung']}: die Fracht trägt der Kunde, Frachtkosten 0 €"], snapshot=snap)
    e = kalkulieren(snap, s)
    t = snap["tarif"]
    e.update(tarif=dict(tarif_id=t["tarif_id"], bezeichnung=t.get("bezeichnung"), dienstleister=t.get("dienstleister"),
                        version=t.get("version"), modell=t.get("modell"),
                        tarifart=t.get("tarifart") or "Standardtarif"),
             zone_empfang=dict(zone=snap["zone"], text=snap.get("zone_text"), status=snap.get("zone_status")),
             snapshot=snap, eingaben=s, datum=s["datum"], version=VERSION,
             status="fehler" if e["fehler"] else ("warnung" if e["warnungen"] else "ok"))
    return e


def zusammenfassung(erg):
    """Kurztext eines Ergebnisses für Listen (Historie, Angebot)."""
    if erg.get("gesamt") is None:
        return "nicht berechnet: " + "; ".join(erg.get("fehler") or ["–"])
    t = erg.get("tarif") or {}
    return f"{euro(erg['gesamt'])}" + (f", Tarif {t.get('tarif_id')}" if t.get("tarif_id") else "")
