"""Werte für die Zusatzfenster im Fenster 'Material je Abmessung' (Patrick 23.10.2026, Freigabe 1a–6a): Schnittplan,
Teileliste, Meter-/Gewichtsbilanz und Preis-Aufbau einer Abmessung. Nur Rechnen und Lesen, ohne Oberfläche; die
Fenster stehen in abmessung_fenster.py.

Eine Abmessung ist eine Gruppe aus rechnen.material_abmessungen (Profil, Werkstoff, Oberfläche, Stangenlänge des
Angebots, ggf. Kundenmaterial). Stangen gehören über rechnen.gruppe_der_stange dazu, so wie im Material-Fenster.
"""
from . import naht, rechnen
from .rechnen import _n
from .stammdaten import huellkreis, zahl_als_text


def gruppe_der_stange(s):
    """Gruppe einer Stange in der Schreibweise von material_abmessungen (Kundenmaterial als 'Kunde')."""
    gr = rechnen.gruppe_der_stange(s)
    return gr[:4] + (("Kunde",) if len(gr) > 4 else ())


def stangen(ergebnis, gruppe, sw=None):
    """Stangen der Abmessung so, wie die Maschine sie lädt (rechnen.anzeige_stangen), mit der Nummer aus dem ganzen
    Schnittplan: [(Stange, Werte)] mit sw = stangen_werte(...), sonst Werte None."""
    return [(s, w) for s, w in rechnen.anzeige_stangen(ergebnis, sw) if gruppe_der_stange(s) == gruppe]


def lieferstangen(ergebnis, gruppe, sw):
    """Lieferstangen (wie gerechnet und bezahlt) der Abmessung: [(Stange, Werte)]."""
    return [(s, w) for s, w in zip((ergebnis or {}).get("stangen") or [], sw or [], strict=False) if gruppe_der_stange(s) == gruppe]


def muster(paare):
    """Gleich belegte Stangen zusammengefasst (Reihenfolge wie das Stangenbild): [{nummern, anzahl, stange, teile
    (Text), rest, ausnutzung, kosten (je Stange)}]; paare = stangen(...)."""
    werte = {s["nr"]: w for s, w in paare}
    out = []
    for s, nummern in rechnen.stangenmuster(dict(stangen=[s for s, _ in paare])):
        zaehler = {}
        for t in s["teile"]:
            schl = (t["pos"] if t["pos"] is not None else t["artikel"], t["laenge"])
            zaehler[schl] = zaehler.get(schl, 0) + 1
        teile = " + ".join(f"{n} × Pos. {p} à {zahl_als_text(l, 0 if l == int(l) else 1)}"
                           for (p, l), n in zaehler.items())
        summe = sum(t["laenge"] for t in s["teile"])
        w = werte.get(s["nr"]) or {}
        out.append(dict(nummern=nummern, anzahl=len(nummern), stange=s["stange"], teile=teile,
                        rest=s["stange"] - s["end"] - summe - s["verlust"],
                        ausnutzung=summe / s["stange"] if s["stange"] else 0, kosten=w.get("kosten")))
    return out


def ende_text(p, seite):
    """'gerade', 'Gehrung 45°' oder 'schräg' für Ende a oder b einer Position."""
    if p.get(seite + "_gerade") != "nein":
        return "gerade"
    g = naht.ende_lesen(p.get(seite + "_ende"))
    return f"Gehrung {rechnen.zahl(g[0], 1)}°" if g else "schräg"


def teile(gruppe, kopf, positionen, paare, zeilen, k):
    """Teileliste der Abmessung, je Position eine Zeile: zeile (Index), ref, pos, artikel, bezeichnung, laenge, stueck,
    enden, lage (Naht/Drehung), eingeplant, stangen (Nummern), gemeinsam (gemeinsame Schnitte), meter, kg, anteil,
    material_teil, laser_brutto, laser_netto, preis_teil. paare = stangen(...) (aus dem ganzen Schnittplan),
    zeilen = rechnen.kalkulation(...)[0] (gleiche Reihenfolge wie positionen, None erlaubt)."""
    kgm = rechnen.kg_je_m(gruppe["profil"], gruppe["werkstoff"], k)
    ids = set(gruppe["ids"])
    out = []
    for i, p in enumerate(positionen):
        if p.get("id") not in ids or rechnen.gruppe_von(p, kopf) != gruppe["gruppe"]:
            continue
        ref = rechnen.schluessel(p, i)
        nr, lagen, gemeinsam, n = [], [], 0, 0
        for s, _ in paare:
            drin = [t for t in s["teile"] if t["ref"] == ref]
            if drin:
                nr.append(s["nr"])
            for t in drin:
                n += 1
                gemeinsam += t.get("trennung") == "gemeinsamer Schnitt"
                text = rechnen.teil_zeichen(t)[1] or t.get("naht_text") or ""
                if text and text not in lagen:
                    lagen.append(text)
        z = (zeilen[i] if zeilen and i < len(zeilen) else None) or {}
        laenge, stueck = _n(p.get("laenge")), rechnen.rohrstuecke(p)     # Halbschalen: Rohrstücke
        meter = laenge * stueck / 1000
        out.append(dict(zeile=i, ref=ref, pos=p.get("pos"), artikel=p.get("artikel"), bezeichnung=p.get("bezeichnung"),
                        laenge=p.get("laenge"), stueck=p.get("stueck"), rohrstuecke=stueck,
                        enden=f"{ende_text(p, 'a')} / {ende_text(p, 'b')}", lage="; ".join(lagen),
                        eingeplant=n, stangen=nr, gemeinsam=gemeinsam, meter=meter,
                        kg=meter * kgm if kgm is not None else None,
                        anteil=z.get("anteil") if z.get("anteil") is not None else
                        (meter / gruppe["teile_m"] if gruppe["teile_m"] else None),
                        material_teil=z.get("material_teil"), laser_brutto=z.get("laser_brutto"),
                        laser_netto=z.get("laser_netto"), preis_teil=z.get("preis_teil")))
    return out


def nummern_text(nummern):
    """'1, 2, 5' bzw. '1–8' bei fortlaufenden Nummern, leer ohne Stangen."""
    if not nummern:
        return ""
    if len(nummern) > 2 and nummern == list(range(nummern[0], nummern[-1] + 1)):
        return f"{nummern[0]}–{nummern[-1]}"
    return ", ".join(map(str, nummern))


BILANZ = ("Teile", "Schnittfugen", "Endbeschnitt", "Greiferrest", "Rest (Verschnitt)", "Zuschnitt beim Lieferanten")


def bilanz(paare, kgm=None, liefer_m=None):
    """Meter-/Gewichtsbilanz der Abmessung: Lieferlänge gesamt = Teile + Schnittfugen + Endbeschnitt + Greiferrest
    + Rest (+ Sägeschnitte und Rest beim Zuschnitt der Lieferstangen, liefer_m = Meter der Lieferstangen). Ergebnis
    dict(posten=[{name, m, anteil, kg}], gesamt_m, gesamt_kg, gespart_m (Gehrungen ineinander), gemeinsam
    (gemeinsame Schnitte)); paare = stangen(...), kgm = kg/m oder None. Der Zuschnitt erscheint nur, wenn es ihn gibt."""
    summe = dict.fromkeys(BILANZ, 0.0)
    gesamt, gespart, gemeinsam = 0.0, 0.0, 0
    for s, _ in paare:
        teile = sum(t["laenge"] for t in s["teile"])
        if s.get("zugeschnitten"):      # Werkstück einer zugeschnittenen Stange: Rest steckt im Verlust
            rest = max(s["stange"] - s["greif"] - max((t["bis"] for t in s["teile"]), default=s["end"]), 0.0)
            fugen = s["verlust"] - rest
        else:
            fugen = s["verlust"]
            rest = s["stange"] - s["end"] - teile - s["verlust"] - s["greif"]
        for name, w in zip(BILANZ[:-1], (teile, fugen, s["end"], s["greif"], rest), strict=True):  # Zuschnitt unten
            summe[name] += w / 1000
        gesamt += s["stange"] / 1000
        gespart += rechnen.gehrung_gespart(s) / 1000
        gemeinsam += sum(1 for t in s["teile"] if t.get("trennung") == "gemeinsamer Schnitt")
    if liefer_m is not None and liefer_m > gesamt + 1e-6:
        summe[BILANZ[-1]] = liefer_m - gesamt
        gesamt = liefer_m
    posten = [dict(name=n, m=m, anteil=m / gesamt if gesamt else None, kg=m * kgm if kgm is not None else None)
              for n, m in summe.items() if n != BILANZ[-1] or m > 0]
    return dict(posten=posten, gesamt_m=gesamt, gesamt_kg=gesamt * kgm if kgm is not None else None,
                gespart_m=gespart, gemeinsam=gemeinsam)


def preis_aufbau(gruppe, kopf, positionen, ergebnis, sw, zeilen, k, tabellen, einst):
    """Wie das Material einer Abmessung zu seinem Preis kommt. dict(herkunft (Text oder None), berechnet, wirksam,
    manuell (€/m), kunde, laengen=[{laenge, stangen, mehr (Händler-Mehrlänge mm), meter (berechnet), kosten,
    preis_m (€ je berechnetem m)}], einkauf, zuschlag_pct, zuschlag, handling_m, handling, positionen=[{pos, artikel,
    stueck, anteil, material_position, material_teil, zuschlag_teil}])."""
    erste = next((p for p in positionen if p.get("id") in set(gruppe["ids"])), None)
    herkunft = rechnen.preis_herkunft(erste, kopf, k, tabellen) if erste and not gruppe["kunde"] else None
    laengen = {}
    for s, w in lieferstangen(ergebnis, gruppe["gruppe"], sw):
        z = laengen.setdefault(s["stange"], dict(laenge=s["stange"], stangen=0, kosten=0.0,
                                                 mehr=rechnen.haendler_mehrlaenge(s["stange"], einst, tabellen)))
        z["stangen"] += 1
        z["kosten"] += _n(w["kosten"])
    for z in laengen.values():
        z["meter"] = z["stangen"] * (z["laenge"] + z["mehr"]) / 1000
        z["preis_m"] = z["kosten"] / z["meter"] if z["meter"] and not gruppe["kunde"] else None
    einkauf = sum(z["kosten"] for z in laengen.values())
    zpct = _n((einst or {}).get("zuschlag_material"))
    handling_m = _n(kopf.get("handling_beistellung")) if gruppe["kunde"] else 0.0
    meter = sum(z["stangen"] * z["laenge"] for z in laengen.values()) / 1000
    pos = []
    for i, p in enumerate(positionen):
        if p.get("id") not in set(gruppe["ids"]):
            continue
        z = (zeilen[i] if zeilen and i < len(zeilen) else None) or {}
        pos.append(dict(pos=p.get("pos"), artikel=p.get("artikel"), stueck=p.get("stueck"), anteil=z.get("anteil"),
                        material_position=z.get("material_position"), material_teil=z.get("material_teil"),
                        zuschlag_teil=z.get("zuschlag_material_teil")))
    return dict(herkunft=herkunft, berechnet=gruppe["berechnet"], wirksam=gruppe["wirksam"], manuell=gruppe["manuell"],
                kunde=gruppe["kunde"], fehlt=gruppe["fehlt"], laengen=sorted(laengen.values(), key=lambda z: z["laenge"]),
                einkauf=einkauf, zuschlag_pct=zpct, zuschlag=einkauf * zpct, handling_m=handling_m,
                handling=handling_m * meter, positionen=pos)


def profil_info(profil_id, werkstoff_id, k):
    """Kennwerte eines Profils für die Profil-Info: dict(profil, form, a, b, wand, flaeche (mm²), kgm, huellkreis,
    maschinen=[{name, passt, grund}]) oder None ohne Stammdaten."""
    pr = k.profile.get(profil_id)
    if not pr:
        return None
    kgm = rechnen.kg_je_m(profil_id, werkstoff_id, k)
    maschinen = []
    for name, m in sorted(k.maschinen.items()):
        grund = rechnen.grenze_ueberschritten(m, pr, kgm)
        maschinen.append(dict(name=name, passt=grund is None, grund=grund or "",
                              max_stange=m.get("max_stange"), min_stange=m.get("min_stange")))
    return dict(profil=profil_id, form=pr.get("form"), a=pr.get("a"), b=pr.get("b"), wand=pr.get("wand"),
                flaeche=rechnen.flaeche_wirksam(pr), kgm=kgm, huellkreis=huellkreis(pr), maschinen=maschinen)


def laengen_indizes(ergebnis, gruppe):
    """Indizes in ergebnis['laengen'] (Vergleich der Lieferlängen), die zur Abmessung gehören; Kundenmaterial: keine."""
    out = []
    if gruppe["kunde"]:         # Kundenmaterial wird nicht verglichen (der Kunde liefert die Stangen)
        return out
    for i, vg in enumerate((ergebnis or {}).get("laengen") or []):
        if (vg["profil"], vg["werkstoff"], vg.get("oberflaeche") or "", vg["stange"]) == tuple(gruppe["gruppe"][:4]):
            out.append(i)
    return out


# Status im Teilebaum (Lantek-Idee L3): alle eingeplant, Teile fehlen, kein Rohrlaserteil, noch nicht optimiert
OK, FEHLT, KEIN, OFFEN = "ok", "fehlt", "kein", "offen"


def teilebaum(kopf, positionen, ergebnis):
    """Teilebaum des Reiters Schnittplan (Lantek-Idee L3, Patrick 24.10.2026): je Abmessung die Positionen mit
    Benötigt, Eingeplant, Offen und Status (OK, FEHLT, KEIN, OFFEN = noch nicht optimiert), Zukaufteile und
    Schweißbaugruppen zuletzt als „Ohne Rohrlaser“. Ergebnis: [dict(titel, benoetigt, eingeplant, offen, status,
    positionen=[dict(zeile, ref, id, pos, artikel, bezeichnung, laenge, benoetigt, eingeplant, offen, status,
    grund)])]; grund = warum nicht eingeplant (Fehlerliste der Optimierung)."""
    from .angebot import kein_laserteil
    ein = rechnen.eingeplant_je_position(ergebnis)
    gruende = {f["index"]: f["grund"] for f in (ergebnis or {}).get("fehler") or ()}
    gruppen, ohne = {}, []
    for i, p in enumerate(positionen):
        if all(rechnen._leer(p.get(f)) for f in ("profil_id", "laenge", "stueck", "artikel")):
            continue
        n = _n(p.get("stueck"))
        x = dict(zeile=i, ref=rechnen.schluessel(p, i), id=p.get("id"), pos=p.get("pos"), artikel=p.get("artikel"),
                 bezeichnung=p.get("bezeichnung"), laenge=p.get("laenge"), benoetigt=n, grund=gruende.get(i))
        if kein_laserteil(p) or rechnen._leer(p.get("profil_id")):
            x.update(eingeplant=None, offen=None, status=KEIN)
            ohne.append(x)
            continue
        e = ein.get(x["ref"], 0)
        x.update(eingeplant=e, offen=max(n - e, 0), status=OFFEN if not ergebnis else OK if e >= n else FEHLT)
        gruppen.setdefault(rechnen.gruppe_von(p, kopf), []).append(x)

    def summe(titel, xs, status):
        return dict(titel=titel, positionen=xs, benoetigt=sum(x["benoetigt"] for x in xs),
                    eingeplant=sum(x["eingeplant"] or 0 for x in xs), offen=sum(x["offen"] or 0 for x in xs),
                    status=status)
    out = []
    for gr, xs in gruppen.items():
        titel = (f"{gr[0]} · {rechnen.material_text(gr[1], gr[2])} · "
                 f"{zahl_als_text(gr[3], 0) + ' mm' if isinstance(gr[3], (int, float)) else 'Stangenlänge fehlt'}"
                 + (" · Kundenmaterial" if len(gr) > 4 else ""))
        status = OFFEN if not ergebnis else FEHLT if any(x["status"] == FEHLT for x in xs) else OK
        out.append(summe(titel, xs, status))
    if ohne:
        out.append(summe("Ohne Rohrlaser (Zukaufteile, Schweißbaugruppen)", ohne, KEIN))
    return out
