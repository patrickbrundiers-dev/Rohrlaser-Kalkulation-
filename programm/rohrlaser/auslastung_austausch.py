"""Schnittstelle Kalkulation ↔ Rohrlaser Auslastung, Format 2 (Plan 11.11.2026, Freigabe Patrick „Alle Empfehlungen“).

Beschreibung beider Seiten: docs/schnittstelle-auslastung.md. Austausch über Dateien in einem gemeinsamen Ordner
(Einstellung 'auslastung_ordner', leer = Unterordner „Auslastung“ neben der Datenbank; 'auslastung_austausch' = nein
schaltet alles ab). Kein gemeinsamer Code mit programm/rl_auslastung (Test R6), nur das Dateiformat.

Richtung 1 (hier geschrieben): je Auftrag eine Datei Auftrag-<Nr>-<JJJJMMTT-HHMMSS>.csv, automatisch beim
Beauftragen, bei jeder Änderung danach (neue Freigabe, nur wenn sich der Inhalt geändert hat) und über den Knopf
„Übergabe …“ (Nachzügler). Zeilen Position / Zusatzarbeit / Stangen, bei Storno nur eine Zeile Storno.
Laserzeit [min] + Rüstzeit [min] über alle Positionen = kalkulierte Maschinenzeit (auslastung.maschinenzeit):
„Rüsten Maschine“ auf der ersten Position, „Rüsten je Abmessung“ auf der ersten Position jeder Abmessung,
Stangenwechsel anteilig in der Laserzeit. Positionen ohne Laser (Zukauf, Bleche) fehlen, eine Schweißbaugruppe kommt
mit Laserzeit 0 und der Zusatzarbeit „Schweißen“.

Richtung 2 (hier gelesen): Rueckmeldung.csv mit Ist-Zeiten je Auftrag/Arbeitsgang, freier Kapazität je Maschine und
Woche und dem frühesten Fertig-Tag für 1/4/8/16 h. Genutzt für die Nachkalkulation (Ist-Laserzeit, wenn es keine
Scans gibt) und den Liefertermin-Vorschlag (terminplan.fruehester, Einstellung 'termin_aus_auslastung').
Optional (CAM-004, Plan Phase 3 und 4, 13.11.2026): Zeilen Art „Stangen“ mit den tatsächlich verbrauchten Stangen
je Abmessung (Spalten wie die Stangen-Zeilen aus Richtung 1, Stangen = Ist); sie gehen als Ist-Stangen in die
Nachkalkulation (ist_stangen).

Fehler hier dürfen nie das Beauftragen oder Speichern verhindern: die Aufrufer fangen alles ab. Ohne Qt."""
import csv
import datetime
import hashlib
import json
import re
from pathlib import Path

FORMAT = "2"
SPALTEN = ("Format", "Art", "Auftragsnummer", "Freigabe", "Kundenauftrag", "Kunde", "Kundennr", "Maschine",
           "Liefertermin", "Pos", "Artikel", "Bezeichnung", "Stückzahl", "Profilform", "Maß a [mm]", "Maß b [mm]",
           "Wand [mm]", "Werkstoff", "Teilelänge [mm]", "Material", "Laserzeit [min]", "Rüstzeit [min]", "Arbeit",
           "Anzahl je Teil", "Zeit [min]", "Fremdleistung", "Arbeitstage", "Stangen", "Stangenlänge [mm]",
           "Nutzlänge [mm]", "Material da ab", "Termin")
POSITION, ZUSATZ, STANGEN, LIEFERUNG, STORNO = "Position", "Zusatzarbeit", "Stangen", "Lieferung", "Storno"
UNTERORDNER = "Auslastung"
RUECKMELDUNG = "Rueckmeldung.csv"
STAND = "auslastung_export_stand"      # Einstellung: JSON {Angebots-ID: {nummer, freigabe, hash, storno}}
FRISCH_TAGE = 3                         # ältere Rückmeldung: kein Liefertermin-Vorschlag
MASCHINE_INTERN = "_maschine"           # Maschine einer Zeile (nur intern, für die Teilaufträge; nie in der Datei)
TEIL = " @ "                            # Teilauftrag einer abweichenden Maschine: „<Auftragsnummer> @ <Maschine>“
SCHWEISSEN = "Schweißen"
ZUSATZ_AUSSER = ("Laser schneiden", "Zukaufteil", "Zukaufartikel", "Schweißbaugruppe")


def _n(w):
    try:
        return float(w) if w not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def zahl(w, stellen=1):
    """12,5 / 20 (Komma, ohne unnötige Nachkommastellen); None und '' bleiben leer."""
    if w in (None, ""):
        return ""
    t = f"{float(w):.{stellen}f}"
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return "0" if t in ("-0", "") else t.replace(".", ",")


def datum(iso):
    try:
        return datetime.date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y") if iso else ""
    except ValueError:
        return ""


def _lies_datum(text):
    try:
        return datetime.datetime.strptime(str(text).strip(), "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return None


def _lies_zahl(text):
    t = str(text or "").strip().replace(".", "").replace(",", ".") if "," in str(text or "") else str(text or "").strip()
    try:
        return float(t) if t else None
    except ValueError:
        return None


# ---------------------------------------------------------------------------------------------------- Ordner
def an(db):
    return (db.einstellung("auslastung_austausch") or "ja") != "nein"


def ordner(db, anlegen=False):
    """Gemeinsamer Ordner oder None (Austausch aus). anlegen=True legt den Ordner an."""
    if not an(db):
        return None
    eigen = str(db.einstellung("auslastung_ordner") or "").strip()
    o = Path(eigen) if eigen else Path(db.pfad).parent / UNTERORDNER
    if anlegen:
        o.mkdir(parents=True, exist_ok=True)
    return o


def dateiname(nummer, jetzt):
    sauber = re.sub(r'[\\/:*?"<>|\s]+', "-", str(nummer or "ohne-Nummer")).strip("-") or "ohne-Nummer"
    return f"Auftrag-{sauber}-{jetzt.strftime('%Y%m%d-%H%M%S')}.csv"


# ---------------------------------------------------------------------------------------------------- Richtung 1
def _kopf(a, freigabe, art):
    return {"Format": FORMAT, "Art": art, "Auftragsnummer": a.get("nummer") or str(a.get("id")),
            "Freigabe": str(freigabe), "Kundenauftrag": a.get("auftragsnr") or "", "Kunde": a.get("kunde") or "",
            "Kundennr": a.get("kundennr") or "", "Maschine": a.get("maschine") or "",
            "Liefertermin": datum(a.get("liefertermin"))}


def _material_da(db, angebot_id):
    """{Profil-ID: ISO-Datum} erwarteter Wareneingang offener Lieferantenbestellungen (lieferantenangebote)."""
    try:
        from . import lieferantenangebote
        out = {}
        for e in lieferantenangebote.liste(db, angebot_id):
            if e.get("bestellt") and not e.get("eingang") and e.get("erwartet") and e.get("profil_id"):
                out[e["profil_id"]] = max(out.get(e["profil_id"], ""), str(e["erwartet"]))
        return out
    except Exception:
        return {}


def inhalt(db, a, aktuell=None):
    """Zeilen (ohne Kopf) eines beauftragten Angebots: [dict(Spalte: Text)]; leer ohne Schnittplan."""
    from . import arbeitsgaenge, auslastung, preis_simulator, rechnen
    from .angebot import aktiv, ist_baugruppe, kein_laserteil
    pos = db.positionen(a["id"])
    if not pos or not a.get("ergebnis"):
        return []
    k, tab, e = preis_simulator.grundlage(db, a, aktuell)
    zeilen, summen = rechnen.kalkulation(a, pos, a["ergebnis"], k, tab, e)
    zeiten = {z.get("schritt"): _n(z.get("gesamt_min")) for z in summen.get("zeiten") or ()
              if z.get("schritt") in auslastung.LASER_SCHRITTE}
    da = _material_da(db, a["id"])
    teile = [(i, p, z) for i, (p, z) in enumerate(zip(pos, zeilen)) if z and aktiv(p)
             and (not kein_laserteil(p) and p.get("profil_id") or ist_baugruppe(p))]
    laser = {i: _n(z.get("laser_netto")) * _n(z.get("stueck")) / 60 for i, p, z in teile if not ist_baugruppe(p)}
    gesamt = sum(laser.values())
    wechsel = zeiten.get("Stangenwechsel", 0.0)
    ruest = {}
    erste_abm = {}
    m0 = a.get("maschine") or ""
    mehrere = len(rechnen.maschinen_im_angebot(a, pos)) > 1
    mp = {i: rechnen.maschine_abweichend(p, a) or m0 for i, p, _z in teile}    # Maschine je Position (MACH-006)
    for i, p, _z in teile:
        if i in laser:
            erste_abm.setdefault((p.get("profil_id"), p.get("werkstoff_id"), mp[i] if mehrere else ""), i)
    if laser and not mehrere:
        ruest[min(laser)] = zeiten.get("Rüsten Maschine", 0.0)
    elif laser:     # je Maschine: Rüsten Maschine auf ihrer ersten Position, Stangenwechsel je Position
        for m_ in dict.fromkeys(mp[i] for i in sorted(laser)):
            ii = [i for i in laser if mp[i] == m_]
            ruest[min(ii)] = sum(_n(z.get("zeit_ruest_maschine")) * _n(z.get("stueck")) / 60
                                 for i, p, z in teile if i in ii)
    if laser:
        je = zeiten.get("Rüsten je Abmessung", 0.0) / len(erste_abm) if erste_abm else 0.0
        for i in erste_abm.values():
            ruest[i] = ruest.get(i, 0.0) + je
    out = []
    regeln = [r for r in tab.get("arbeitsgang_regeln") or ()]
    for i, p, z in teile:
        pr = k.profile.get(p.get("profil_id")) or {}
        w = k.werkstoffe.get(p.get("werkstoff_id")) or {}
        bg = ist_baugruppe(p)
        lz = laser.get(i, 0.0)
        if mehrere and lz:
            lz += _n(z.get("zeit_stangenwechsel")) * _n(z.get("stueck")) / 60
        elif gesamt and lz:
            lz += wechsel * lz / gesamt
        stueck = _n(z.get("stueck")) or _n(p.get("stueck"))
        out.append({"Art": POSITION, "Pos": str(p.get("pos") or i + 1), "Artikel": p.get("artikel") or "",
                    "Bezeichnung": p.get("bezeichnung") or "", "Stückzahl": zahl(stueck, 0),
                    "Profilform": "" if bg else pr.get("form") or "", "Maß a [mm]": "" if bg else zahl(pr.get("a")),
                    "Maß b [mm]": "" if bg else zahl(pr.get("b")), "Wand [mm]": "" if bg else zahl(pr.get("wand"), 2),
                    "Werkstoff": "" if bg else w.get("werkstoff") or p.get("werkstoff_id") or "",
                    "Teilelänge [mm]": "" if bg else zahl(p.get("laenge")),
                    "Material": "Kunde" if rechnen.beigestellt(p) else "eigen", "Laserzeit [min]": zahl(lz),
                    "Rüstzeit [min]": zahl(ruest.get(i, 0.0)), "Material da ab": datum(da.get(p.get("profil_id"))),
                    **({MASCHINE_INTERN: mp[i]} if mehrere else {})})
        if bg:
            bz = _n(z.get("bg_zeit_min")) * stueck
            out.append({"Art": ZUSATZ, "Pos": out[-1]["Pos"], "Arbeit": SCHWEISSEN,
                        "Zeit [min]": zahl(bz) if bz else "", "Fremdleistung": "nein",
                        **({MASCHINE_INTERN: mp[i]} if mehrere else {})})
            continue
        gew = [g for g in arbeitsgaenge.position(p, a, k, tab, regeln)
               if g["status"] in (arbeitsgaenge.IM_ANGEBOT, arbeitsgaenge.AUTOMATISCH)
               and g["arbeitsgang"] not in ZUSATZ_AUSSER]
        n_gew = sum(_n(g["menge"]) for g in gew if g["arbeitsgang"].startswith("Gewinde "))
        gew_s = _n(z.get("gewindezeit"))
        for g in gew:
            ist_gewinde = g["arbeitsgang"].startswith("Gewinde ")
            if ist_gewinde:
                sek = gew_s * _n(g["menge"]) / n_gew if n_gew else 0.0
            else:
                sek = _n(g["zeit"])
            minuten = sek * stueck / 60
            fremd = g["kostenart"] == arbeitsgaenge.FREMD
            out.append({"Art": ZUSATZ, "Pos": out[-1]["Pos"] if out else "", "Arbeit": g["arbeitsgang"],
                        "Anzahl je Teil": zahl(g["menge"], 2) if g.get("menge") not in (None, "")
                        and g.get("einheit") in ("Stk", "Stück") else "",
                        "Zeit [min]": zahl(minuten) if minuten > 0 and not fremd else "",
                        "Fremdleistung": "ja" if fremd else "nein", **({MASCHINE_INTERN: mp[i]} if mehrere else {})})
    try:
        werte = rechnen.stangen_werte(a["ergebnis"], a, pos, k, tab)
    except Exception:
        werte = ()
    gruppen = {}
    for s, wv in zip(a["ergebnis"].get("stangen") or (), list(werte) + [None] * len(a["ergebnis"].get("stangen") or ())):
        schl = (s.get("profil"), s.get("werkstoff"), s.get("stange"), (s.get("maschine") or m0) if mehrere else "")
        g = gruppen.setdefault(schl, dict(n=0, nutz=0.0, kunde=bool(s.get("beistellung"))))
        g["n"] += 1
        g["nutz"] += _n((wv or {}).get("belegt"))
    for (profil, werkstoff, laenge, m_), g in gruppen.items():
        pr = k.profile.get(profil) or {}
        w = k.werkstoffe.get(werkstoff) or {}
        out.append({"Art": STANGEN, "Profilform": pr.get("form") or "", "Maß a [mm]": zahl(pr.get("a")),
                    "Maß b [mm]": zahl(pr.get("b")), "Wand [mm]": zahl(pr.get("wand"), 2),
                    "Werkstoff": w.get("werkstoff") or werkstoff or "", "Stangen": str(g["n"]),
                    "Stangenlänge [mm]": zahl(laenge, 0), "Nutzlänge [mm]": zahl(g["nutz"], 0),
                    "Material da ab": "" if g["kunde"] else datum(da.get(profil)),
                    **({MASCHINE_INTERN: m_} if mehrere else {})})
    return out


def teilauftraege(db, a, aktuell=None):
    """Maschine je Position (MACH-006 Paket 2): [(Auftragsnummer, Maschine, Zeilen)]. Ohne abweichende Maschine genau
    ein Eintrag (Nummer und Maschine des Angebots, Zeilen von inhalt). Sonst ein Teilauftrag je Maschine: der Teil der
    Kopf-Maschine unter der Auftragsnummer, die anderen als „<Nummer> @ <Maschine>“; die Rohrlaser Auslastung plant
    jeden Teil als eigenen Auftrag auf seiner Maschine (Format unverändert: eine Maschine je Datei)."""
    rumpf = inhalt(db, a, aktuell)
    nr, m0 = a.get("nummer") or str(a.get("id")), a.get("maschine") or ""
    if not any(MASCHINE_INTERN in r for r in rumpf):
        return [(nr, m0, rumpf)]
    je = {}
    for r in rumpf:
        je.setdefault(r.pop(MASCHINE_INTERN, m0), []).append(r)
    reihe = [m0] + [m_ for m_ in je if m_ != m0]
    return [(nr if m_ == m0 else teil_nummer(nr, m_), m_, je.get(m_, [])) for m_ in reihe]


def teil_nummer(nummer, maschine):
    return f"{nummer}{TEIL}{maschine}"


def gehoert_zu(nummer_rueck, nummer):
    """Zeile der Rückmeldung zum Auftrag nummer: dieselbe Nummer oder ein Teilauftrag „<Nummer> @ <Maschine>“."""
    r, n = str(nummer_rueck or ""), str(nummer or "")
    return bool(n) and (r == n or r.startswith(n + TEIL))


def _stand(db):
    try:
        d = json.loads(db.einstellung(STAND) or "{}")
        return d if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def _stand_setzen(db, d):
    db.einstellung_setzen(STAND, json.dumps(d, ensure_ascii=False, sort_keys=True))


def _schreiben(o, a, freigabe, rumpf, art, jetzt):
    leer = {s: "" for s in SPALTEN}
    zeilen = [{**leer, **_kopf(a, freigabe, art), **r} for r in rumpf] if rumpf else [{**leer, **_kopf(a, freigabe, art)}]
    ziel = o / dateiname(a.get("nummer") or a.get("id"), jetzt)
    while ziel.exists():            # zwei Freigaben in derselben Sekunde: die neuere bekommt die nächste Sekunde
        jetzt += datetime.timedelta(seconds=1)
        ziel = o / dateiname(a.get("nummer") or a.get("id"), jetzt)
    tmp = ziel.with_name(ziel.name + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=SPALTEN, delimiter=";")
        w.writeheader()
        for z in zeilen:
            w.writerow(z)
    tmp.replace(ziel)
    return ziel


def _pruefsumme(a, rumpf):
    kopf = _kopf(a, 0, POSITION)
    return hashlib.sha1(json.dumps([kopf, rumpf], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def schreiben(db, angebot_id, jetzt=None, erzwingen=False, aktuell=None):
    """Auftragsdatei eines beauftragten Angebots. Neue Freigabe nur, wenn sich der Inhalt geändert hat; erzwingen
    (Knopf Übergabe) schreibt auch ohne Änderung (gleiche Freigabe, neuer Zeitstempel). Ergebnis: Pfad oder None.
    Maschine je Position (MACH-006): je abweichender Maschine ein eigener Teilauftrag „<Nummer> @ <Maschine>“ (eigene
    Datei, eigene Freigabe; Ergebnis dann der Pfad des Kopf-Teils oder des ersten geschriebenen); ein Teil, der
    wegfällt, bekommt Storno."""
    a = db.angebot(angebot_id)
    o = ordner(db)
    if not a or o is None or a.get("fremd") or getattr(db, "nur_lesen", False) or a.get("vorgang") != "Beauftragt":
        return None
    teile = teilauftraege(db, a, aktuell)
    if not any(r["Art"] == POSITION for _n, _m, rumpf in teile for r in rumpf):
        return None
    st = _stand(db)
    jetzt = jetzt or datetime.datetime.now()
    pfade = []
    schluessel = set()
    for i, (nr, m_, rumpf) in enumerate(teile):
        sch = str(angebot_id) if i == 0 else f"{angebot_id}{TEIL}{m_}"
        schluessel.add(sch)
        if not any(r["Art"] == POSITION for r in rumpf):
            continue
        teil = dict(a, nummer=nr, maschine=m_) if i else a
        alt = st.get(sch) or {}
        summe = _pruefsumme(teil, rumpf)
        if alt.get("hash") == summe and not alt.get("storno") and not erzwingen:
            continue
        freigabe = int(alt.get("freigabe") or 0) + (0 if alt.get("hash") == summe and not alt.get("storno") else 1)
        o.mkdir(parents=True, exist_ok=True)
        pfade.append(_schreiben(o, teil, max(1, freigabe), rumpf, POSITION, jetzt))
        st[sch] = dict(nummer=nr, freigabe=max(1, freigabe), hash=summe, storno=False)
    for sch in [x for x in st if x.startswith(f"{angebot_id}{TEIL}") and x not in schluessel]:
        p_ = _storno_eintrag(o, a, st, sch, jetzt)    # Position wieder auf der Kopf-Maschine: Teilauftrag storniert
        if p_:
            pfade.append(p_)
    if pfade:
        _stand_setzen(db, st)
    return pfade[0] if pfade else None


def _storno_eintrag(o, a, st, sch, jetzt):
    alt = st.get(sch)
    if not alt or alt.get("storno"):
        return None
    freigabe = int(alt.get("freigabe") or 0) + 1
    o.mkdir(parents=True, exist_ok=True)
    m_ = sch.split(TEIL, 1)[1] if TEIL in sch else a.get("maschine")
    pfad = _schreiben(o, dict(a, nummer=alt.get("nummer") or a.get("nummer"), maschine=m_), freigabe, None, STORNO,
                      jetzt)
    st[sch] = dict(alt, freigabe=freigabe, storno=True, hash=None)
    return pfad


def storno(db, angebot_id, jetzt=None):
    """Storno-Datei für ein schon übergebenes Angebot, das nicht mehr beauftragt ist (auch für seine Teilaufträge je
    Maschine). Ergebnis: Pfad (Kopf-Teil) oder None."""
    a = db.angebot(angebot_id)
    o = ordner(db)
    st = _stand(db)
    if not a or o is None or getattr(db, "nur_lesen", False):
        return None
    jetzt = jetzt or datetime.datetime.now()
    pfad = _storno_eintrag(o, a, st, str(angebot_id), jetzt)
    teile = [_storno_eintrag(o, a, st, sch, jetzt) for sch in [x for x in st if x.startswith(f"{angebot_id}{TEIL}")]]
    if pfad or any(teile):
        _stand_setzen(db, st)
    return pfad or next((p_ for p_ in teile if p_), None)


def abgleich(db, angebot_id, jetzt=None):
    """Nach Vorgang ändern oder Schließen eines Angebots: beauftragt → Auftragsdatei (bei Änderung), vorher übergeben
    und jetzt nicht mehr beauftragt → Storno. Wirft nie (Ergebnis: Pfad oder None)."""
    try:
        a = db.angebot(angebot_id) or {}
        if a.get("vorgang") == "Beauftragt":
            return schreiben(db, angebot_id, jetzt)
        return storno(db, angebot_id, jetzt)
    except Exception:
        return None


def alle(db, ids, jetzt=None):
    """Knopf „Übergabe …“: alle genannten beauftragten Aufträge (auch ohne Änderung). Ergebnis: [Pfad]."""
    out = []
    for i in ids:
        try:
            p = schreiben(db, i, jetzt, erzwingen=True)
        except Exception:
            p = None
        if p:
            out.append(p)
    return out


# ---------------------------------------------------------------------------------------------------- Richtung 2
_MERKER = {}


def rueckmeldung(db, pfad=None):
    """Rueckmeldung.csv gelesen: dict(stand (datetime oder None), auftraege [dict], kapazitaet {(Maschine, Montag):
    frei h}, fruehester {Maschine: [(Stunden, Datum)]}) oder None (keine Datei, Austausch aus, Format unbekannt)."""
    if pfad is None:
        o = ordner(db)
        if o is None:
            return None
        pfad = o / RUECKMELDUNG
    pfad = Path(pfad)
    try:
        st = pfad.stat()
        mtime = (st.st_mtime_ns, st.st_size)
    except OSError:
        return None
    gemerkt = _MERKER.get(str(pfad))
    if gemerkt and gemerkt[0] == mtime:
        return gemerkt[1]
    try:
        with open(pfad, newline="", encoding="utf-8-sig") as f:
            zeilen = list(csv.DictReader(f, delimiter=";"))
    except (OSError, UnicodeDecodeError, csv.Error):
        return None
    out = dict(stand=None, auftraege=[], kapazitaet={}, fruehester={}, stangen=[])
    for z in zeilen:
        z = {str(k or "").strip(): (v or "").strip() if isinstance(v, str) else "" for k, v in z.items()}
        if z.get("Format") != FORMAT:
            continue
        if out["stand"] is None and z.get("Stand"):
            try:
                out["stand"] = datetime.datetime.strptime(z["Stand"], "%d.%m.%Y %H:%M")
            except ValueError:
                pass
        art, m = z.get("Art"), z.get("Maschine") or ""
        if art == "Auftrag":
            out["auftraege"].append(dict(nummer=z.get("Auftragsnummer"), pos=z.get("Pos") or None,
                                         arbeitsgang=z.get("Arbeitsgang") or None, maschine=m,
                                         kalkuliert=_lies_zahl(z.get("Kalkuliert [min]")),
                                         tatsaechlich=_lies_zahl(z.get("Tatsächlich [min]")),
                                         fertig_am=_lies_datum(z.get("Fertig am")), bediener=z.get("Bediener"),
                                         status=z.get("Status"), fertig_plan=_lies_datum(z.get("Fertig (Plan)")),
                                         risiko=z.get("Terminrisiko")))
        elif art == STANGEN:          # CAM-004: verbrauchte Stangen je Abmessung
            n = _lies_zahl(z.get("Stangen"))
            if z.get("Auftragsnummer") and n is not None:
                out["stangen"].append(dict(nummer=z["Auftragsnummer"], schluessel=stangen_schluessel(
                    z.get("Profilform"), z.get("Maß a [mm]"), z.get("Maß b [mm]"), z.get("Wand [mm]"),
                    z.get("Werkstoff"), z.get("Stangenlänge [mm]")), anzahl=int(round(n))))
        elif art == "Kapazität":
            mo, frei = _lies_datum(z.get("Montag")), _lies_zahl(z.get("Frei [h]"))
            if mo and frei is not None:
                out["kapazitaet"][(m, mo)] = frei
        elif art == "Frühester":
            h, d = _lies_zahl(z.get("Stunden")), _lies_datum(z.get("Frühester Fertig-Tag"))
            if h and d:
                out["fruehester"].setdefault(m, []).append((h, d))
    for liste in out["fruehester"].values():
        liste.sort()
    _MERKER[str(pfad)] = (mtime, out)
    return out


def stangen_schluessel(form, a, b, wand, werkstoff, laenge):
    """Vergleichbarer Schlüssel einer Stangen-Zeile (Texte wie im Export, Zahlen normiert)."""
    def zt(w, n):
        x = _lies_zahl(w) if isinstance(w, str) else w
        return zahl(x, n) if x not in (None, "") else ""
    return (str(form or "").strip(), zt(a, 1), zt(b, 1), zt(wand, 2), str(werkstoff or "").strip(), zt(laenge, 0))


def ist_stangen(db, a, k, r=None):
    """CAM-004: {Gruppenschlüssel der Nachkalkulation: verbrauchte Stangen} aus der Rückmeldung für das Angebot a
    (mit Schnittplan); nur Abmessungen, die eindeutig einer Gruppe zugeordnet werden können. {} ohne Rückmeldung."""
    from . import nachkalkulation, rechnen
    r = r if r is not None else rueckmeldung(db)
    zeilen = [z for z in (r or {}).get("stangen") or () if gehoert_zu(z["nummer"], a.get("nummer"))]
    if not zeilen or not (a.get("ergebnis") or {}).get("stangen"):
        return {}
    zu = {}
    for st in a["ergebnis"]["stangen"]:
        pr = k.profile.get(st.get("profil")) or {}
        w = k.werkstoffe.get(st.get("werkstoff")) or {}
        sch = stangen_schluessel(pr.get("form"), pr.get("a"), pr.get("b"), pr.get("wand"),
                                 w.get("werkstoff") or st.get("werkstoff"), st.get("stange"))
        ob = st.get("oberflaeche") or ""
        g = nachkalkulation.gruppenschluessel(st["profil"], st["werkstoff"], st["stange"], ob) + \
            ("|Kunde" if st.get("beistellung") else "") + ("|" + rechnen.MUSTER if st.get("muster") else "")
        zu.setdefault(sch, set()).add(g)
    out = {}
    for z in zeilen:
        gr = zu.get(z["schluessel"]) or set()
        if len(gr) == 1:
            g = next(iter(gr))
            out[g] = out.get(g, 0) + z["anzahl"]
    return out


def frisch(r, jetzt=None):
    jetzt = jetzt or datetime.datetime.now()
    return bool(r and r.get("stand") and jetzt - r["stand"] <= datetime.timedelta(days=FRISCH_TAGE))


def ist_laser_h(db, nummer, r=None):
    """Ist-Laserzeit [h] eines fertig gemeldeten Auftrags aus der Rückmeldung (Arbeitsgang leer = Laser), sonst
    None."""
    r = r if r is not None else rueckmeldung(db)
    for z in (r or {}).get("auftraege") or ():
        if z["nummer"] == nummer and not z["arbeitsgang"] and not z["pos"] and z["status"] == "fertig" \
                and z["tatsaechlich"]:
            teile = [x for x in (r or {}).get("auftraege") or () if gehoert_zu(x["nummer"], nummer)
                     and x["nummer"] != nummer and not x["arbeitsgang"] and not x["pos"]]
            # Teilaufträge je Maschine (MACH-006): Summe erst, wenn alle Teile fertig sind
            if any(x["status"] != "fertig" or not x["tatsaechlich"] for x in teile):
                return None
            return (z["tatsaechlich"] + sum(x["tatsaechlich"] for x in teile)) / 60
    return None


def termin_vorschlag(db, maschine, laser_h, ab, heute=None, r=None):
    """Frühester Tag, an dem die Laserzeit nach dem Plan der Auslastung fertig wäre: (Datum, Text) oder None
    (Einstellung aus, keine oder alte Rückmeldung, Maschine unbekannt). Bis 16 h aus „Frühester“ (nächstgrößere
    Stufe), darüber aus den freien Stunden je Woche („Kapazität“, Freitag der Woche, in der die letzte Stunde Platz
    findet). ab = frühester Start (Material da)."""
    if (db.einstellung("termin_aus_auslastung") or "ja") == "nein":
        return None
    r = r if r is not None else rueckmeldung(db)
    if not frisch(r, datetime.datetime.combine(heute, datetime.time(12)) if heute else None):
        return None
    stand = r["stand"].strftime("%d.%m.%Y %H:%M")
    stufen = r["fruehester"].get(maschine) or []
    passend = [d for h, d in stufen if h >= laser_h - 1e-9]
    if passend:
        return max(ab, passend[0]), f"nach dem Plan der Rohrlaser Auslastung (Stand {stand})"
    from . import terminplan
    frei = sorted((mo, h) for (m, mo), h in r["kapazitaet"].items() if m == maschine)
    if not frei:
        return None
    from .auslastung import montag
    woche, _ = terminplan.verteilen(laser_h, frei, montag(ab))
    if woche is None:
        return None
    return max(ab, woche + datetime.timedelta(days=4)), \
        f"nach den freien Stunden der Rohrlaser Auslastung (Stand {stand})"
