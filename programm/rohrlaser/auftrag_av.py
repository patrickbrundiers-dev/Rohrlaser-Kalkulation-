"""Arbeitsvorbereitung eines Auftrags (Plan Auftragsworkflow 13.11.2026, Paket 3). Ohne Qt.

Arbeitsgänge je Position: Vorlage sind die Produktionsschritte aus den Einstellungen (Vorgabe Patricks 8 Schritte:
Materialbereitstellung, Rohrlaser, Entgraten, Bohren / Nachbearbeitung, Schweißbaugruppe, Montage,
Qualitätskontrolle, Verpackung). Aus der übernommenen Kalkulation wird vorbelegt, welche davon die Position braucht
(Laserzeit → Rohrlaser, Zusatzarbeiten → Entgraten/Bohren/Montage …, Schweißzeit oder Baugruppe → Schweißbaugruppe),
mit Sollzeit, Sollmenge und Maschine. Die übrigen Schritte stehen abgewählt dabei. Je Position lassen sich Schritte
an- und abwählen, verschieben, ergänzen und mit Mitarbeiter, Maschine, geplantem Start/Ende und Bemerkung versehen.
Jede Änderung ist ein Ereignis „Arbeitsgänge festgelegt“ mit der vollständigen Liste (alt → neu in der Historie).

Prüfliste mit Ampel (Freigabe „Produktionsbereit“): Zeichnungen vorhanden, Material verfügbar oder bestellt,
Zukauf-/Normteile geklärt, Fertigungsinformationen vollständig, Arbeitsgänge definiert. Was das Programm selbst
prüfen kann, prüft es (Dateien, Felder, Arbeitsgänge); Material und Zukauf bestätigt die Arbeitsvorbereitung von Hand
(Ereignis „Arbeitsvorbereitung geprüft“). Produktionsbereit geht nur bei Grün oder als Sonderfreigabe mit Grund.
"""
import uuid

from . import auftraege as au

GRUEN, GELB, ROT = "grün", "gelb", "rot"

VORGABE_SCHRITTE = ("Materialbereitstellung", "Rohrlaser", "Entgraten", "Bohren / Nachbearbeitung",
                    "Schweißbaugruppe", "Montage", "Qualitätskontrolle", "Verpackung")
# Schritt -> Stichworte in den Zusatzarbeiten der Position, die ihn aktiv machen
STICHWORTE = {"entgraten": ("entgrat", "gleitschleif", "bürst", "schleif"),
              "bohren": ("bohr", "gewinde", "senk", "flowdrill", "fräs", "kernloch", "nachbearbeit"),
              "montage": ("montage", "einpress", "nieten", "verschraub", "einsetzen"),
              "schweiß": ("schweiß", "heft", "naht"),
              "verpack": ("verpack",), "qualität": ("prüf", "mess", "qualität")}
IMMER = ("material", "qualität", "verpack")        # Schritte, die jede Position hat (Teil kommt rein, wird geprüft, geht raus)

# Prüfpunkte (Schlüssel, Titel, von Hand bestätigbar)
PUNKTE = (("zeichnungen", "Zeichnungen vorhanden"), ("material", "Material verfügbar oder bestellt"),
          ("zukauf", "Zukauf- und Normteile geklärt"), ("fertigungsinfo", "Fertigungsinformationen vollständig"),
          ("arbeitsgaenge", "Arbeitsgänge definiert"))
PUNKT_TITEL = dict(PUNKTE)
MATERIAL_WERTE = ("verfügbar", "bestellt", "fehlt")
OK = "geklärt"                  # Handbestätigung der übrigen Punkte
ZURUECK = "offen"               # Bestätigung zurücknehmen

FELDER = ("name", "aktiv", "maschine", "mitarbeiter", "start", "ende", "sollzeit", "sollmenge", "bemerkung")


def schritte(db):
    """Produktionsschritte aus den Einstellungen (eine Zeile oder ; je Schritt), sonst die Vorgabe."""
    roh = str(db.einstellung("produktionsschritte") or "")
    out = [x.strip() for z in roh.splitlines() for x in z.split(";") if x.strip()]
    return list(dict.fromkeys(out)) or list(VORGABE_SCHRITTE)


def _schluessel(name):
    n = str(name or "").lower()
    for k in ("material", "laser", "entgrat", "bohr", "schweiß", "montage", "qualität", "verpack"):
        if k in n:
            return {"entgrat": "entgraten", "bohr": "bohren", "laser": "laser"}.get(k, k)
    return n


def _ist_zukauf(p):
    art = str(p.get("art") or "").lower()
    return "zukauf" in art or "ergänzt" in art or "norm" in art


def vorschlag(p, schritte_, maschine=""):
    """Arbeitsgänge einer übernommenen Position aus Kalkulation und Vorlage: [dict(FELDER, uid)]."""
    zusatz = " ".join(str(x) for x in p.get("zusatz") or ()).lower()
    menge = au._n(p.get("menge"))
    laser = au._n(p.get("laser_min")) + au._n(p.get("ruesten_min"))
    schweissen = au._n(p.get("schweissen_min"))
    gewinde = au._n(p.get("gewinde_min"))
    zusatz_min = au._n(p.get("zusatz_min"))
    zukauf = _ist_zukauf(p)
    bg = "baugruppe" in str(p.get("art") or "").lower() or bool(p.get("baugruppe") and schweissen)
    aktiv_bohren = bool(gewinde) or any(w in zusatz for w in STICHWORTE["bohren"])
    aktiv_entgraten = any(w in zusatz for w in STICHWORTE["entgraten"])
    out = []
    for name in schritte_:
        k = _schluessel(name)
        zeit, masch = 0.0, ""
        if k == "laser":
            aktiv, zeit, masch = (laser > 0 or (not zukauf and str(p.get("profil") or "") != "")), laser, maschine
        elif k == "schweiß":
            aktiv, zeit = bg or schweissen > 0 or any(w in zusatz for w in STICHWORTE["schweiß"]), schweissen
        elif k == "bohren":
            aktiv = aktiv_bohren
            zeit = gewinde + (zusatz_min if not aktiv_entgraten else 0.0)
        elif k == "entgraten":
            aktiv, zeit = aktiv_entgraten, zusatz_min if aktiv_entgraten and not aktiv_bohren else 0.0
        elif k in STICHWORTE and k not in IMMER:
            aktiv = any(w in zusatz for w in STICHWORTE[k])
        elif any(k.startswith(i) for i in IMMER):
            aktiv = True
        else:                   # eigener Schritt aus den Einstellungen: aktiv, wenn eine Zusatzarbeit so heißt
            aktiv = bool(k) and (k in zusatz or any(str(x).lower() in k for x in p.get("zusatz") or () if x))
        if zukauf and k in ("laser", "entgraten", "bohren", "schweiß"):
            aktiv = False
        out.append(dict(uid=uuid.uuid4().hex, name=name, aktiv=bool(aktiv), maschine=masch, mitarbeiter="",
                        start="", ende="", sollzeit=round(zeit, 2), sollmenge=menge, bemerkung=""))
    return out


def arbeitsgaenge(db, a, p):
    """(liste, vorschlag?) der Arbeitsgänge einer Position: festgelegte oder der Vorschlag."""
    if p.get("arbeitsgaenge"):
        return [dict(x) for x in p["arbeitsgaenge"]], False
    return vorschlag(p, schritte(db), (a.get("kopf") or {}).get("maschine") or ""), True


def _kurz(liste):
    """Kurztext für die Historie: aktive Schritte in Reihenfolge."""
    return ", ".join(x["name"] for x in liste or () if x.get("aktiv")) or "keine"


FELD_TITEL = dict(name="Bezeichnung", aktiv="Aktiv", maschine="Maschine", mitarbeiter="Mitarbeiter",
                  start="Start geplant", ende="Ende geplant", sollzeit="Sollzeit [min]", sollmenge="Sollmenge",
                  bemerkung="Bemerkung")


def _text(f, w):
    if f in ("sollzeit", "sollmenge"):
        return f"{au._n(w):g}".replace(".", ",")
    return str(w or "")


def unterschied(alt, neu, war_vorschlag=False):
    """(feld, alt, neu) für die Historie: Auswahl, Reihenfolge oder das erste geänderte Feld eines Schritts."""
    if war_vorschlag or _kurz(alt) != _kurz(neu):
        return "Arbeitsgänge", "" if war_vorschlag else _kurz(alt), _kurz(neu)
    na, nn = [x["name"] for x in alt], [x["name"] for x in neu]
    if na != nn:
        return "Reihenfolge", " → ".join(na), " → ".join(nn)
    for x, y in zip(alt, neu):
        for f in FELDER:
            if _text(f, x.get(f)) != _text(f, y.get(f)):
                return f"{y['name']}: {FELD_TITEL[f]}", _text(f, x.get(f)), _text(f, y.get(f))
    return "Arbeitsgänge", _kurz(alt), _kurz(neu)


def _sauber(liste):
    out = []
    for x in liste or ():
        name = str(x.get("name") or "").strip()
        if not name:
            raise au.AuftragFehler("Jeder Arbeitsgang braucht eine Bezeichnung.")
        z = dict(uid=x.get("uid") or uuid.uuid4().hex, name=name, aktiv=bool(x.get("aktiv", True)),
                 maschine=str(x.get("maschine") or "").strip(), mitarbeiter=str(x.get("mitarbeiter") or "").strip(),
                 start=str(x.get("start") or "").strip(), ende=str(x.get("ende") or "").strip(),
                 sollzeit=round(max(0.0, au._n(str(x.get("sollzeit") or 0).replace(",", "."))), 2),
                 sollmenge=max(0.0, au._n(str(x.get("sollmenge") or 0).replace(",", "."))),
                 bemerkung=str(x.get("bemerkung") or "").strip())
        if z["start"] and z["ende"] and z["ende"] < z["start"]:
            raise au.AuftragFehler(f"{name}: geplantes Ende liegt vor dem Start.")
        out.append(z)
    return out


def _bearbeitbar(db, a):
    if db.nur_lesen:
        raise au.AuftragFehler(f"Lesemodus – {db.nur_lesen}.")
    if a is None:
        raise au.AuftragFehler("Den Auftrag gibt es nicht mehr.")
    if a["status"] in (au.AUSGELIEFERT, au.ABGESCHLOSSEN):
        raise au.AuftragFehler(f"Der Auftrag ist {a['status'].lower()}; die Arbeitsvorbereitung ist zu.")


def _av_beginnen(db, uid, a):
    """Erste Arbeit in der AV: Status Neu eingegangen -> Arbeitsvorbereitung (automatisch, in der Transaktion)."""
    if (a["status"] or au.NEU) == au.NEU:
        au._ereignis(db, uid, au.STATUS, feld="status", alt=au.NEU, neu=au.AV, bemerkung="automatisch (AV begonnen)")


def setzen(db, uid, position, liste, bemerkung=""):
    """Arbeitsgänge einer Position festlegen (vollständige Liste in Reihenfolge). Kein Ereignis ohne Änderung.
    Ergebnis: True, wenn geändert."""
    a = au.auftrag(db, uid)
    _bearbeitbar(db, a)
    p = next((x for x in a["positionen"] if x["uid"] == position), None)
    if p is None:
        raise au.AuftragFehler("Die Position gibt es im Auftrag nicht.")
    neu = _sauber(liste)
    alt, war_vorschlag = arbeitsgaenge(db, a, p)
    if not war_vorschlag and [{f: x.get(f) for f in FELDER} for x in alt] == [{f: x.get(f) for f in FELDER}
                                                                              for x in neu]:
        return False
    with db.con:
        _av_beginnen(db, uid, a)
        feld, t_alt, t_neu = unterschied(alt, neu, war_vorschlag)
        au._ereignis(db, uid, au.ARBEITSGAENGE, ziel=position, feld=feld, alt=t_alt, neu=t_neu, daten=neu,
                     bemerkung=bemerkung)
    return True


def alle_uebernehmen(db, uid):
    """Vorschläge aller Positionen ohne festgelegte Arbeitsgänge festlegen. Ergebnis: Anzahl Positionen."""
    a = au.auftrag(db, uid)
    _bearbeitbar(db, a)
    n = 0
    for p in a["positionen"]:
        if not p.get("arbeitsgaenge"):
            liste, _ = arbeitsgaenge(db, a, p)
            n += setzen(db, uid, p["uid"], liste, "Vorschlag aus der Kalkulation übernommen")
    return n


def fuer_alle(db, uid, position, nur_aktiv_namen=True):
    """Auswahl und Reihenfolge der Schritte einer Position auf alle anderen übertragen (Zeiten, Mengen, Maschinen
    der Zielpositionen bleiben). Ergebnis: Anzahl geänderter Positionen."""
    a = au.auftrag(db, uid)
    _bearbeitbar(db, a)
    quelle = next((x for x in a["positionen"] if x["uid"] == position), None)
    if quelle is None:
        raise au.AuftragFehler("Die Position gibt es im Auftrag nicht.")
    muster, _ = arbeitsgaenge(db, a, quelle)
    n = 0
    for p in a["positionen"]:
        if p["uid"] == position:
            continue
        eigen, _ = arbeitsgaenge(db, a, p)
        je_name = {x["name"]: x for x in eigen}
        neu = []
        for m in muster:
            x = dict(je_name.get(m["name"]) or dict(m, uid=uuid.uuid4().hex, sollzeit=0.0,
                                                     sollmenge=au._n(p.get("menge"))))
            x["aktiv"] = m["aktiv"]
            neu.append(x)
        neu += [x for x in eigen if x["name"] not in {m["name"] for m in muster}]
        n += setzen(db, uid, p["uid"], neu, f"wie Pos. {quelle.get('nr')} übernommen")
    return n


# ------------------------------------------------------------------ Prüfliste
def bestaetigen(db, uid, punkt, wert, bemerkung=""):
    """Prüfpunkt von Hand setzen: material = verfügbar | bestellt | fehlt | offen; übrige = geklärt | offen."""
    a = au.auftrag(db, uid)
    _bearbeitbar(db, a)
    if punkt not in PUNKT_TITEL:
        raise au.AuftragFehler(f"Prüfpunkt {punkt} gibt es nicht.")
    erlaubt = MATERIAL_WERTE + (ZURUECK,) if punkt == "material" else (OK, ZURUECK)
    if wert not in erlaubt:
        raise au.AuftragFehler(f"Für „{PUNKT_TITEL[punkt]}“ geht nur: {', '.join(erlaubt)}.")
    alt = ((a["kopf"].get("_av") or {}).get(punkt) or {}).get("wert") or ZURUECK
    if alt == wert:
        return False
    if punkt != "material" and wert == OK and not str(bemerkung or "").strip() and punkt in ("zeichnungen",
                                                                                       "fertigungsinfo"):
        luecke = next(x for x in pruefliste(db, a) if x["punkt"] == punkt)
        if luecke["ampel"] != GRUEN:
            raise au.AuftragFehler(f"„{PUNKT_TITEL[punkt]}“ hat Lücken ({luecke['text']}); als geklärt nur mit "
                                   "Bemerkung.")
    with db.con:
        _av_beginnen(db, uid, a)
        au._ereignis(db, uid, au.PRUEFPUNKT, feld=punkt, alt=alt, neu=wert, bemerkung=bemerkung)
        if punkt == "material" and wert == "fehlt" and a["status"] in (au.NEU, au.AV, au.BEREIT):
            au._ereignis(db, uid, au.STATUS, feld="status", alt=a["status"] if a["status"] != au.NEU else au.AV,
                         neu=au.MATERIAL_FEHLT, bemerkung=bemerkung or "automatisch (Material fehlt)")
        elif (punkt == "material" and wert in ("verfügbar", "bestellt") and a["status"] == au.MATERIAL_FEHLT):
            au._ereignis(db, uid, au.STATUS, feld="status", alt=au.MATERIAL_FEHLT, neu=au.AV,
                         bemerkung=f"automatisch (Material {wert})")
    return True


def _hand(a, punkt):
    return (a["kopf"].get("_av") or {}).get(punkt) or {}


def pruefliste(db, a):
    """[dict(punkt, titel, ampel, text, hand)] für die Ampel. hand: Handbestätigung (wert, wer, am, bemerkung)."""
    pos = a["positionen"]
    eigene = [p for p in pos if not _ist_zukauf(p)]
    out = []

    # Zeichnungen: jede gefertigte Position hat eine Zeichnung oder CAD-Datei mit ihrer Artikelnummer
    dateien = [d for x in a["angebote"] for d in (x["stand"].get("dateien") or ())]
    ohne = [p for p in eigene if not p.get("zeichnungen")]
    if not eigene:
        z = (GRUEN, "keine gefertigten Positionen")
    elif not dateien:
        z = (ROT, "keine Zeichnungen oder CAD-Dateien im Angebotsordner")
    elif ohne:
        z = (GELB, "ohne passende Datei: " + ", ".join(f"Pos. {p['nr']} {p.get('artikel') or ''}".strip()
                                                       for p in ohne[:6]) + (" …" if len(ohne) > 6 else ""))
    else:
        z = (GRUEN, f"{len(dateien)} Dateien, jede Position hat eine")
    out.append(_punkt(a, "zeichnungen", *z))

    # Material: bestätigt die AV (verfügbar/bestellt), fehlt = rot
    h = _hand(a, "material")
    w = h.get("wert")
    if w in ("verfügbar", "bestellt"):
        z = (GRUEN, f"Material {w}")
    elif w == "fehlt":
        z = (ROT, "Material fehlt")
    elif not eigene:
        z = (GRUEN, "nur Zukauf, kein Rohmaterial")
    else:
        werk = sorted({f"{p.get('profil') or ''} {p.get('werkstoff') or ''}".strip() for p in eigene} - {""})
        z = (ROT, "nicht bestätigt" + (f" ({', '.join(werk[:4])}{' …' if len(werk) > 4 else ''})" if werk else ""))
    out.append(_punkt(a, "material", *z))

    # Zukauf/Normteile
    zk = [p for p in pos if _ist_zukauf(p)]
    zusatz_zukauf = [p for p in eigene if any("zukauf" in str(x).lower() or "norm" in str(x).lower()
                                              for x in p.get("zusatz") or ())]
    if _hand(a, "zukauf").get("wert") == OK:
        z = (GRUEN, "geklärt")
    elif not zk and not zusatz_zukauf:
        z = (GRUEN, "keine Zukauf- oder Normteile")
    else:
        n = len(zk) + len(zusatz_zukauf)
        z = (GELB, f"{n} {'Position' if n == 1 else 'Positionen'} mit Zukauf/Normteilen, nicht bestätigt")
    out.append(_punkt(a, "zukauf", *z))

    # Fertigungsinformationen: Werkstoff, Abmessung, Länge, Menge je gefertigter Position
    luecken = []
    for p in eigene:
        fehlt = [t for f, t in (("werkstoff", "Werkstoff"), ("profil", "Abmessung"), ("laenge", "Länge"))
                 if p.get("art") in (None, "", "Rohrlaserteil") and not p.get(f)]
        if au._n(p.get("menge")) <= 0:
            fehlt.append("Menge")
        if fehlt:
            luecken.append(f"Pos. {p['nr']}: {', '.join(fehlt)}")
    if not luecken:
        z = (GRUEN, "vollständig")
    else:
        z = (ROT, "; ".join(luecken[:4]) + (" …" if len(luecken) > 4 else ""))
    out.append(_punkt(a, "fertigungsinfo", *z))

    # Arbeitsgänge: jede Position hat festgelegte Arbeitsgänge mit mindestens einem aktiven Schritt
    offen = [p for p in pos if not p.get("arbeitsgaenge")]
    leer = [p for p in pos if p.get("arbeitsgaenge") and not any(x.get("aktiv") for x in p["arbeitsgaenge"])]
    if not pos:
        z = (ROT, "keine Positionen")
    elif offen:
        z = (GELB if len(offen) < len(pos) else ROT,
             f"{len(offen)} von {len(pos)} Positionen nur Vorschlag – „Vorschläge übernehmen“")
    elif leer:
        z = (ROT, "ohne aktiven Arbeitsgang: " + ", ".join(f"Pos. {p['nr']}" for p in leer))
    else:
        z = (GRUEN, f"{sum(sum(1 for x in p['arbeitsgaenge'] if x.get('aktiv')) for p in pos)} Arbeitsgänge")
    out.append(_punkt(a, "arbeitsgaenge", *z))
    return out


def _punkt(a, punkt, ampel, text):
    h = _hand(a, punkt)
    if h.get("wert") == OK and ampel != GRUEN:
        ampel, text = GRUEN, f"geklärt von {h.get('wer') or '?'}" + (f": {h['bemerkung']}" if h.get("bemerkung")
                                                                   else "") + f" (Programm: {text})"
    return dict(punkt=punkt, titel=PUNKT_TITEL[punkt], ampel=ampel, text=text, hand=h)


def ampel(liste):
    """Gesamtampel: rot, wenn ein Punkt rot ist, gelb bei gelb, sonst grün."""
    werte = {x["ampel"] for x in liste}
    return ROT if ROT in werte else GELB if GELB in werte else GRUEN


def freigeben(db, uid, grund=""):
    """Auftrag „Produktionsbereit“ melden. Bei nicht grüner Prüfliste nur als Sonderfreigabe mit Grund (steht mit
    den offenen Punkten in der Historie)."""
    a = au.auftrag(db, uid)
    _bearbeitbar(db, a)
    if a["status"] not in (au.NEU, au.AV, au.MATERIAL_FEHLT):
        raise au.AuftragFehler(f"Der Auftrag steht auf „{a['status']}“; freigeben geht nur aus der "
                               "Arbeitsvorbereitung.")
    liste = pruefliste(db, a)
    offen = [f"{x['titel']}: {x['text']}" for x in liste if x["ampel"] != GRUEN]
    grund = str(grund or "").strip()
    if offen and not grund:
        raise au.AuftragFehler("Noch nicht alles grün:\n" + "\n".join(offen) + "\nFreigabe nur als Sonderfreigabe mit "
                               "Grund.")
    with db.con:
        au._ereignis(db, uid, au.FREIGABE, feld="status", alt=a["status"], neu=au.BEREIT,
                     daten=dict(sonder=bool(offen), offen=offen), bemerkung=grund)
    return bool(offen)


def zusammenfassung(db, a):
    """Kurzzeile für die Liste/Detail: (ampel, text)."""
    liste = pruefliste(db, a)
    gruen = sum(1 for x in liste if x["ampel"] == GRUEN)
    return ampel(liste), f"AV {gruen}/{len(liste)}"
