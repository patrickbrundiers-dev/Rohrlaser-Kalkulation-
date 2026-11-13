"""Schnittstelle zur Kalkulation, Format 2 (Plan 2.8, Patrick 11.11.2026 „Alle Empfehlungen“, F1a bis F6a). Ohne Qt.

Beschreibung beider Richtungen: docs/schnittstelle-auslastung.md, Beispiele in docs/schnittstelle-beispiel/.

Richtung 1 (Kalkulation -> Auslastung): eine CSV-Datei je Auftrag im Übergabe-Ordner, Spalte Format = 2, Spalte Art
= Position, Zusatzarbeit, Stangen, Lieferung oder Storno. lesen() liefert dasselbe Ergebnis wie austausch.lesen() und
dazu storno und freigaben; austausch.uebernehmen() speichert beides.

Regeln (F2a): Zeiten, Material, Termin und Zusatzarbeiten kommen aus der Kalkulation. Was aus der Werkstatt kommt,
bleibt: Maschine eines schon eingeplanten Auftrags, gelaufene Zeit, Start, fertig gemeldete Arbeitsgänge, fester
Platz, Reihenfolge. Fertig gemeldete Aufträge ändert die Datei nicht mehr. F3a: Zusatzzeit aus der Kalkulation, die
Richtzeiten nur, wo keine Zeit kommt.

Richtung 2 (Auslastung -> Kalkulation): Rueckmeldung.csv mit Ist-Zeiten je Auftrag und Arbeitsgang, freier Kapazität
je Maschine und Woche und dem frühesten Fertig-Tag für 1, 4, 8 und 16 Stunden (rueckmeldung_schreiben)."""
import csv
import datetime
import json
import os
import re
from pathlib import Path

from rohrlaser import einlastung

from . import daten as D
from . import rechnung
from . import zusatz as Z

FORMAT = "2"
POSITION, ZUSATZ, STANGEN, LIEFERUNG, STORNO = "position", "zusatzarbeit", "stangen", "lieferung", "storno"
ARTEN = (POSITION, ZUSATZ, STANGEN, LIEFERUNG, STORNO)
SPALTEN = ("Format", "Art", "Auftragsnummer", "Freigabe", "Kundenauftrag", "Kunde", "Kundennr", "Maschine",
           "Liefertermin", "Pos", "Artikel", "Bezeichnung", "Stückzahl", "Profilform", "Maß a [mm]", "Maß b [mm]",
           "Wand [mm]", "Werkstoff", "Teilelänge [mm]", "Material", "Laserzeit [min]", "Rüstzeit [min]", "Arbeit",
           "Anzahl je Teil", "Zeit [min]", "Fremdleistung", "Arbeitstage", "Stangen", "Stangenlänge [mm]",
           "Nutzlänge [mm]", "Material da ab", "Termin")
FREIGABEN = "schnittstelle_freigabe"      # Einstellung: {Auftragsnummer: [Freigabe, Zeitstempel der Datei]}
FREMD_TAGE = 5                            # Fremdleistung ohne Arbeitstage und ohne Richtzeit
_STEMPEL = re.compile(r"(\d{8}-\d{6})")


def ist_format2(zeilen):
    """Kopfzeile mit den Spalten Format und Art?"""
    kopf = {str(t).strip().casefold() for t in (zeilen[0] if zeilen else ())}
    return "format" in kopf and "art" in kopf


def stempel(name):
    m = _STEMPEL.search(str(name or ""))
    return m.group(1) if m else ""


def freigaben(db):
    try:
        x = json.loads(db.einstellung(FREIGABEN) or "{}")
    except ValueError:
        x = {}
    return x if isinstance(x, dict) else {}


def freigaben_merken(db, neu):
    if not neu:
        return
    alle = freigaben(db)
    alle.update(neu)
    if len(alle) > 3000:                  # alte Aufträge fallen weg
        alle = dict(list(alle.items())[-2000:])
    db.einstellung_setzen(FREIGABEN, json.dumps(alle, ensure_ascii=False))


def _zahl(text, name, pflicht=False):
    t = str(text or "").strip().replace(" ", "")
    if not t:
        if pflicht:
            raise D.Fehler(f"{name} fehlt.")
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        z = float(t)
    except ValueError:
        raise D.Fehler(f"{name} „{text}“ ist keine Zahl.") from None
    if z < 0:
        raise D.Fehler(f"{name} darf nicht negativ sein.")
    return z


def _mm(z):
    return "" if z is None else (f"{z:g}".replace(".", ","))


def _richtzeit(arbeit, richtzeiten):
    """Richtzeit zum Namen einer Zusatzarbeit der Kalkulation (ganzer Name, sonst ein Wort davon) oder None."""
    r = Z.stichwort(arbeit, richtzeiten)
    if r is None:
        for w in re.split(r"[\s/,;()]+", arbeit):
            if w and (r := Z.stichwort(w, richtzeiten)) is not None:
                break
    return r


def _begonnen(a):
    return any(t["start_am"] or t["gelaufen_min"] or t["status"] == D.FERTIG for t in (a["gaenge"] or [a]))


def lesen(db, zeilen, name=""):
    """Format 2 prüfen, noch nichts speichern. Ergebnis wie austausch.lesen() und dazu storno=[dict(id, nummer)] und
    freigaben={Auftragsnummer: [Freigabe, Zeitstempel]} (gelesene Freigaben, übernehmen merkt sie)."""
    out = dict(neu=[], geaendert=[], gleich=0, fehler=[], uebersprungen=[], maschinen_neu=[], spalten_fremd=[],
               storno=[], freigaben={})
    kopf = [str(t).strip() for t in zeilen[0]]
    spalte = {}
    for i, t in enumerate(kopf):
        spalte.setdefault(t.casefold(), i)
    felder = {f["name"].casefold(): f["name"] for f in db.zusatzfelder()}
    bekannt = {s.casefold() for s in SPALTEN}
    out["spalten_fremd"] = [t for t in kopf if t and t.casefold() not in bekannt and t.casefold() not in felder]
    gruppen = {}
    for nr, z in enumerate(zeilen[1:], start=2):
        if not any(str(c).strip() for c in z):
            continue

        def wert(name, z=z):
            i = spalte.get(name.casefold())
            return str(z[i]).strip() if i is not None and i < len(z) else ""
        fmt, art, nummer = wert("Format"), wert("Art").casefold(), wert("Auftragsnummer")
        if fmt != FORMAT:
            out["fehler"].append(f"Zeile {nr}: Format „{fmt}“ ist unbekannt (erwartet {FORMAT}).")
        elif art not in ARTEN:
            out["fehler"].append(f"Zeile {nr}: Art „{wert('Art')}“ ist unbekannt.")
        elif not nummer:
            out["fehler"].append(f"Zeile {nr}: Auftragsnummer fehlt.")
        else:
            gruppen.setdefault(nummer, []).append((nr, art, wert))
    gemerkt = freigaben(db)
    maschinen = {m["name"] for m in db.maschinen()}
    for nummer, reihe in gruppen.items():
        try:
            _auftrag(db, nummer, reihe, stempel(name), gemerkt, maschinen, felder, out)
        except D.Fehler as e:
            out["fehler"].append(f"Auftrag {nummer} (ab Zeile {reihe[0][0]}): {e}")
    return out


def _auftrag(db, nummer, reihe, stand, gemerkt, maschinen, felder, out):
    w0 = reihe[0][2]
    freigabe = _zahl(w0("Freigabe"), "Freigabe", pflicht=True)
    schluessel = [int(freigabe), stand]
    alt = db.auftrag(nummer=nummer)
    vorher = gemerkt.get(nummer)
    if vorher and schluessel < list(vorher):
        out["uebersprungen"].append(f"Auftrag {nummer}: Freigabe {schluessel[0]} ist älter als die schon gelesene "
                                    f"Freigabe {vorher[0]} und wird übergangen.")
        return
    if vorher and schluessel == list(vorher):
        out["gleich"] += 1
        return
    arten = {}
    for nr, art, w in reihe:
        arten.setdefault(art, []).append((nr, w))
    if STORNO in arten:
        out["freigaben"][nummer] = schluessel
        if alt is None:
            out["gleich"] += 1
        elif alt["status"] == D.FERTIG or _begonnen(alt):
            out["uebersprungen"].append(f"Auftrag {nummer} wurde in der Kalkulation storniert, ist aber schon "
                                        "gelaufen oder fertig und bleibt deshalb stehen. Bitte von Hand prüfen.")
        else:
            out["storno"].append(dict(id=alt["id"], nummer=nummer))
        return
    if alt is None and db.im_papierkorb(nummer):
        out["uebersprungen"].append(f"Auftrag {nummer} liegt im Papierkorb und wird nicht übernommen.")
        return
    if alt is not None and alt["status"] == D.FERTIG:
        out["uebersprungen"].append(f"Auftrag {nummer} ist schon fertig gemeldet und bleibt, wie er ist.")
        out["freigaben"][nummer] = schluessel
        return
    if POSITION not in arten:
        raise D.Fehler("keine Zeile mit Art Position.")
    maschine = w0("Maschine")
    if not maschine:
        raise D.Fehler("Maschine fehlt.")
    if " + " in maschine or " → " in maschine:
        raise D.Fehler("bitte genau eine Maschine angeben.")
    laser = ruest = 0.0
    ruest_da = False
    stueck_pos, profile, mat_ab, durchm, laenge, abm = {}, [], [], 0.0, 0.0, []
    for nr, w in arten[POSITION]:
        pos = w("Pos") or str(nr)
        stk = _zahl(w("Stückzahl"), f"Pos {pos}: Stückzahl", pflicht=True)
        laser += _zahl(w("Laserzeit [min]"), f"Pos {pos}: Laserzeit", pflicht=True)
        r = _zahl(w("Rüstzeit [min]"), f"Pos {pos}: Rüstzeit")
        if r is not None:
            ruest_da, ruest = True, ruest + r
        stueck_pos[pos] = stueck_pos.get(pos, 0) + int(stk)
        a, b, s = (_zahl(w(n), f"Pos {pos}: {n}") for n in ("Maß a [mm]", "Maß b [mm]", "Wand [mm]"))
        if w("Profilform") or a:
            abm.append((w("Profilform"), a or 0.0, b or 0.0, s or 0.0, w("Werkstoff")))
            profile.append(" ".join(x for x in (w("Profilform"), "×".join(_mm(v) for v in (a, b, s) if v),
                                                w("Werkstoff")) if x))
        durchm = max(durchm, a or 0, b or 0)
        laenge = max(laenge, _zahl(w("Teilelänge [mm]"), f"Pos {pos}: Teilelänge") or 0)
        if w("Material da ab"):
            mat_ab.append(D._tag(w("Material da ab")))
    for _nr, w in arten.get(STANGEN, ()):
        if w("Material da ab"):
            mat_ab.append(D._tag(w("Material da ab")))
    kalk = round(laser + ruest)               # Maschinenzeit der Kalkulation
    gaenge, hinweis = _zusatz(db, arten.get(ZUSATZ, ()), stueck_pos, maschine, kalk)
    if hinweis:
        out["uebersprungen"].append(f"Auftrag {nummer}: {hinweis}")
    if kalk <= 0 and len(gaenge) <= 1:
        raise D.Fehler("weder Laserzeit noch Zusatzarbeit mit Zeit.")
    neu = dict(nummer=nummer, maschine=maschine, kalk_min=max(1, kalk), liefertermin=D._tag(w0("Liefertermin")),
               kunde=w0("Kunde"), stueckzahl=max(1, sum(stueck_pos.values())),
               zusatz={felder[t.casefold()]: w0(t) for t in SPALTEN + tuple(felder.values())
                       if t.casefold() in felder and w0(t)})
    if db.funktion("material"):
        neu["material"] = profile[0] if profile and len(set(profile)) == 1 else ""
        einzeln = abm[0] if abm and len(set(abm)) == 1 else ("", 0.0, 0.0, 0.0, "")   # Plan 3.2: fürs Bündeln
        neu.update(zip(D.ABMESSUNG, einzeln))
        neu["durchmesser"], neu["laenge"] = durchm, laenge
        if ruest_da:
            neu["ruest_min"] = 0                  # das Rüsten steckt schon in der Laufzeit der Kalkulation
    if db.funktion("material_ab"):
        neu["material_ab"] = max(mat_ab) if mat_ab else None
    lief = []
    for nr, w in arten.get(LIEFERUNG, ()):
        lief.append(dict(termin=D._tag(w("Termin")), menge=_zahl(w("Stückzahl"), f"Zeile {nr}: Menge", True)))
    if alt is None:
        neu["bemerkung"] = f"Kundenauftrag {w0('Kundenauftrag')}" if w0("Kundenauftrag") else ""
        if kalk <= 0:
            gaenge = gaenge[1:]               # nur Zusatzarbeiten (z. B. Schweißbaugruppe ohne Laser)
        if len(gaenge) > 1 or (gaenge and gaenge[0]["platz"] != maschine):
            neu["gaenge"] = gaenge
        elif len(lief) >= 2 and db.funktion("teillieferungen"):
            neu["lieferungen"] = lief
        if maschine not in maschinen and maschine not in out["maschinen_neu"]:
            out["maschinen_neu"].append(maschine)
        out["neu"].append(neu)
    else:
        neu.update(id=alt["id"], bemerkung=alt["bemerkung"])
        _abgleichen(alt, neu, gaenge, kalk)
        if "gaenge" not in neu and not alt["gaenge"] and len(lief) >= 2 and db.funktion("teillieferungen"):
            neu["lieferungen"] = lief
        out["geaendert"].append(neu)
    out["freigaben"][nummer] = schluessel


def _zusatz(db, zeilen, stueck_pos, maschine, kalk):
    """Arbeitsgänge: zuerst der Laser, dann je Zusatzarbeit (über alle Positionen zusammengefasst) ein Gang, in der
    Reihenfolge der Richtzeiten-Tabelle (Gewinde … Schweißen), unbekannte danach, Fremdleistung zuletzt.
    Ergebnis: (Gänge, Hinweis oder '')."""
    gaenge = [dict(name=maschine, platz=maschine, kalk_min=max(1, kalk), tage=0, gleichzeitig=0, zusatz=[])]
    if not zeilen:
        return gaenge, ""
    if not (db.funktion("zusatzschritte") and db.mit_gaengen()):
        return gaenge, ("Zusatzarbeiten nicht übernommen (Arbeitsgänge oder Zusatzschritte sind in den Einstellungen "
                        "aus).")
    R = db.richtzeiten()
    je = {}
    for nr, w in zeilen:
        arbeit = w("Arbeit")
        if not arbeit:
            raise D.Fehler(f"Zeile {nr}: Name der Zusatzarbeit (Spalte Arbeit) fehlt.")
        je.setdefault(arbeit, []).append((nr, w))
    folge = [schritt for schritt, _arten in Z.schritte(R)]
    zusatz = []
    for n, (arbeit, liste) in enumerate(je.items()):
        r = _richtzeit(arbeit, R)
        fremd = any(w("Fremdleistung").casefold() in ("ja", "j", "1", "x") for _nr, w in liste) or (
            r is not None and Z.fremd(r))
        minuten, tage, pos = 0.0, 0, []
        for nr, w in liste:
            anzahl = _zahl(w("Anzahl je Teil"), f"Zeile {nr}: Anzahl je Teil") or 0
            stk = stueck_pos.get(w("Pos"), 0) or 1
            if r is not None and anzahl and not Z.fremd(r):
                pos.append(dict(schritt=r["schritt"], art=r["art"] or "", anzahl=anzahl))
            if fremd:
                tage = max(tage, int(_zahl(w("Arbeitstage"), f"Zeile {nr}: Arbeitstage") or 0))
                continue
            zeit = _zahl(w("Zeit [min]"), f"Zeile {nr}: Zeit")
            if zeit is None:
                if r is None:
                    raise D.Fehler(f"Zeile {nr}: „{arbeit}“ hat keine Zeit, und es gibt keine Richtzeit dazu "
                                   "(Einstellungen → Zusatzschritte).")
                try:
                    zeit = Z.zeit([dict(schritt=r["schritt"], art=r["art"] or "", anzahl=anzahl or 1)], stk, R)[0]
                except ValueError as e:
                    raise D.Fehler(f"Zeile {nr}: {e}") from None
            minuten += zeit
        if fremd:
            tage = tage or (int(r["tage"] or 0) if r is not None and Z.fremd(r) else 0) or FREMD_TAGE
            g = dict(name=arbeit, platz=D.FREMD, kalk_min=0, tage=tage, gleichzeitig=0, zusatz=[])
        else:
            platz = r["platz"] if r is not None and r["platz"] else (
                Z.SCHWEISSEN if "schwei" in arbeit.casefold() else Z.BEARBEITUNG)
            g = dict(name=arbeit, platz=platz, kalk_min=max(1, round(minuten)), tage=0, gleichzeitig=0, zusatz=pos)
        zusatz.append(((fremd, folge.index(r["schritt"]) if r is not None and r["schritt"] in folge else len(folge),
                        n), g))
    return gaenge + [g for _k, g in sorted(zusatz, key=lambda x: x[0])], ""


def _abgleichen(alt, neu, gaenge, kalk):
    """F2a für einen schon eingeplanten Auftrag: Maschine bleibt (die Werkstatt hat vielleicht umgeplant), fertig
    gemeldete und begonnene Arbeitsgänge bleiben mit ihren Werten, die übrigen bekommen die Zeit der Kalkulation."""
    vorher = alt["gaenge"]
    if not vorher:
        neu["maschine"] = alt["maschine"]
        if len(gaenge) <= 1:
            return
        gaenge[0].update(name=alt["maschine"], platz=alt["maschine"])
        neu["gaenge"] = gaenge if kalk > 0 else gaenge[1:]
        return
    laser_alt = next((g for g in vorher if g["platz"] != D.FREMD and g["name"] not in {x["name"] for x in gaenge[1:]}),
                     None)
    liste = []
    for n, g in enumerate(gaenge):
        x = laser_alt if n == 0 else next((v for v in vorher if v["name"] == g["name"]), None)
        if n == 0:
            if x is None and kalk <= 0:
                continue
            if x is not None:
                g.update(name=x["name"], platz=x["platz"])
        if x is not None:
            g["id"] = x["id"]
            if x["status"] == D.FERTIG or x["start_am"] or x["gelaufen_min"]:
                g.update(platz=x["platz"], tage=x["tage"], gleichzeitig=x["gleichzeitig"],
                         kalk_min=x["kalk_min"] if x["status"] == D.FERTIG else g["kalk_min"])
        liste.append(g)
    genommen = {g.get("id") for g in liste}
    for v in vorher:                          # nicht mehr in der Kalkulation, aber schon in Arbeit: bleibt
        if v["id"] not in genommen and (v["status"] == D.FERTIG or v["start_am"] or v["gelaufen_min"]):
            liste.insert(min(v["pos"], len(liste)), dict(id=v["id"], name=v["name"], platz=v["platz"],
                                                         kalk_min=v["kalk_min"], tage=v["tage"],
                                                         gleichzeitig=v["gleichzeitig"], zusatz=v["zusatz"]))
    if len(liste) == 1 and liste[0]["platz"] != D.FREMD and not (liste[0].get("id") and
                                                                  _begonnen(dict(alt, gaenge=vorher))):
        neu["maschine"], neu["kalk_min"], neu["gaenge"] = liste[0]["platz"], liste[0]["kalk_min"], []
    else:
        neu["gaenge"] = liste


# ---------------------------------------------------------------- Richtung 2: Rückmeldung
RUECKMELDUNG = "Rueckmeldung.csv"
RUECK_SPALTEN = ("Format", "Art", "Stand", "Auftragsnummer", "Pos", "Arbeitsgang", "Maschine", "Kalkuliert [min]",
                 "Tatsächlich [min]", "Fertig am", "Bediener", "Status", "Fertig (Plan)", "Terminrisiko", "Montag",
                 "KW", "Verfügbar [h]", "Verplant [h]", "Frei [h]", "Stunden", "Frühester Fertig-Tag")
STUNDEN = (1, 4, 8, 16)
FERTIG_TAGE = 90                         # fertige Aufträge so viele Tage zurück
RISIKO = {einlastung.OK: "ok", einlastung.KNAPP: "knapp", einlastung.UEBER: "nicht zu halten", einlastung.OHNE: ""}
STAND = "rueckmeldung_stand"             # Einstellung: Tag und Zahl der Fertigmeldungen beim letzten Schreiben


def _t(d):
    if not d:
        return ""
    if isinstance(d, str):
        d = D._tag_iso(d)
    return d.strftime("%d.%m.%Y") if d else ""


def _h(x):
    return f"{x:.1f}".replace(".", ",")


def _bediener(db, a, gang=None):
    for v in db.verlauf(a["id"]):
        if "fertig gemeldet" in v["was"] and (gang is None or v["was"].startswith(f"{gang}:")):
            return v["wer"]
    return ""


def rueckmeldung(db, heute=None, jetzt=None, aus=None, ein=None):
    """Zeilen der Rückmeldung (dicts mit den Spalten aus RUECK_SPALTEN)."""
    heute = heute or datetime.date.today()
    jetzt = jetzt or datetime.datetime.now()
    if aus is None or ein is None:
        aus, ein = rechnung.einlasten(db, heute)
    stand = jetzt.strftime("%d.%m.%Y %H:%M")
    plan = ein.get("plan") or {}
    gang_fertig = {a.get("gang"): a["fertig"] for a in ein["auftraege"] if a.get("gang")}
    zeilen = []

    def zeile(art, **k):
        zeilen.append(dict({s: "" for s in RUECK_SPALTEN}, Format=FORMAT, Art=art, Stand=stand, **k))
    grenze = heute - datetime.timedelta(days=FERTIG_TAGE)
    for a in db.auftraege():
        if a["status"] == D.FERTIG and (D._tag_iso(a["fertig_am"]) or heute) < grenze:
            continue
        p = plan.get(a["id"]) or {}
        risiko = RISIKO.get(p.get("risiko"), "") if a["status"] != D.FERTIG else ""
        if not a["gaenge"]:
            zeile("Auftrag", Auftragsnummer=a["nummer"], Maschine=a["maschine"], **{
                "Kalkuliert [min]": a["kalk_min"] or "", "Tatsächlich [min]": a["ist_min"] or "",
                "Fertig am": _t(a["fertig_am"]), "Bediener": _bediener(db, a) if a["status"] == D.FERTIG else "",
                "Status": a["status"], "Fertig (Plan)": _t(p.get("fertig")) if a["status"] != D.FERTIG else "",
                "Terminrisiko": risiko})
            continue
        for n, g in enumerate(a["gaenge"]):
            status = g["status"] if g["status"] == D.FERTIG else (D.LAEUFT if g["start_am"] else D.OFFEN)
            fremd = g["platz"] == D.FREMD
            zeile("Auftrag", Auftragsnummer=a["nummer"], Arbeitsgang="" if n == 0 and not fremd else g["name"],
                  Maschine=D.FREMD_TEXT if fremd else g["platz"], **{
                      "Kalkuliert [min]": "" if fremd else g["kalk_min"] or "",
                      "Tatsächlich [min]": "" if fremd else g["ist_min"] or "", "Fertig am": _t(g["fertig_am"]),
                      "Bediener": _bediener(db, a, g["name"]) if status == D.FERTIG else "", "Status": status,
                      "Fertig (Plan)": _t(gang_fertig.get(g["id"])) if status != D.FERTIG else "",
                      "Terminrisiko": risiko})
    montage = [mo for mo, _t2, wert in aus["spalten"] if wert is not None][:8]
    for m in ein["maschinen"]:
        for mo in montage:
            kap = ein["wochen_kap"].get((m, mo), 0.0)
            belegt = sum(ein["woche"].get((m, mo), {}).values())
            zeile("Kapazität", Maschine=m, Montag=_t(mo), KW=mo.isocalendar()[1], **{
                "Verfügbar [h]": _h(kap), "Verplant [h]": _h(belegt), "Frei [h]": _h(max(0.0, kap - belegt))})
    for h in STUNDEN:
        for x in rechnung.auskunft(db, h * 60, heute):
            zeile("Frühester", Maschine=x["maschine"], Stunden=h, **{"Frühester Fertig-Tag": _t(x["fertig"])})
    return zeilen


def _fertig_zahl(db):
    return (db.con.execute("SELECT COUNT(*) FROM auftraege WHERE status = ?", (D.FERTIG,)).fetchone()[0]
            + db.con.execute("SELECT COUNT(*) FROM gaenge WHERE status = ?", (D.FERTIG,)).fetchone()[0])


def faellig(db, heute=None):
    """Rückmeldung schreiben? Ja, wenn ein Ordner eingestellt und die Funktion an ist und seit dem letzten Schreiben
    ein Tag vergangen oder etwas fertig gemeldet worden ist (gilt für alle Plätze an derselben Datenbank)."""
    if not db.einstellung("uebergabe_ordner") or not db.funktion("rueckmeldung"):
        return False
    heute = heute or datetime.date.today()
    return db.einstellung(STAND) != f"{heute.isoformat()}:{_fertig_zahl(db)}"


def rueckmeldung_schreiben(db, ordner=None, heute=None, jetzt=None, aus=None, ein=None):
    """Rueckmeldung.csv in den Übergabe-Ordner schreiben (erst .tmp, dann umbenennen). Ergebnis: Pfad oder None
    (kein Ordner, nicht erreichbar)."""
    ordner = ordner or db.einstellung("uebergabe_ordner")
    if not ordner:
        return None
    heute = heute or datetime.date.today()
    ziel = Path(ordner) / RUECKMELDUNG
    tmp = ziel.with_suffix(".tmp")
    zeilen = rueckmeldung(db, heute, jetzt, aus, ein)
    try:
        with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, RUECK_SPALTEN, delimiter=";", lineterminator="\r\n")
            w.writeheader()
            w.writerows(zeilen)
        os.replace(tmp, ziel)
    except OSError:
        return None
    db.einstellung_setzen(STAND, f"{heute.isoformat()}:{_fertig_zahl(db)}")
    return ziel
