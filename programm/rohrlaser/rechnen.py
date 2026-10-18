"""Rechnungen eines Auftrags: Positionswerte und Status, Stangenoptimierung, Schnittplan, Kalkulation.

Jede Funktion bildet die entsprechenden Formeln bzw. Makros der Mappe nach (Blätter Auftrag,
Schnittplan, Stangenbelegung, Auswertung, Kalkulation in tools/build_mappe.py). Die Optimierung selbst
ist dieselbe wie in der Mappe (tools/optimierung.py). tests/test_programm_mappe.py vergleicht die
Ergebnisse mit der in LibreOffice gerechneten Mappe.

Eingaben: kopf (dict: maschine, stange, …), positionen (Liste von dicts, Reihenfolge = Zeilen im
Auftrag), k (stammdaten.Kontext), tabellen (dict mit 'preise', 'schneiddaten', 'gewinde': Zeilen).
"""
import hashlib
import json

from .stammdaten import flaeche_wirksam
from .werkzeuge import optimierung as opt

EPS = opt.EPS
ZEILE0 = 13   # erste Positionszeile der Mappe: Teil.zeile = ZEILE0 + Index, damit die Reihenfolge gleich ist


def _n(v):
    """Wie N() in Excel: Zahl oder 0."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _leer(v):
    return v is None or v == ""


def schluessel(p, i):
    """Bezug eines eingeplanten Teils auf seine Position: Datenbank-ID, sonst Zeilenindex."""
    return f"id{p['id']}" if p.get("id") is not None else f"ix{i}"


def maschine(kopf, k):
    return k.maschinen.get(kopf.get("maschine"))


def stange_wirksam(p, kopf):
    """Auftrag Q: abweichende Stangenlänge der Position, sonst Standard aus dem Kopf."""
    return p.get("stange") if not _leer(p.get("stange")) else kopf.get("stange")


def kg_je_m(profil_id, werkstoff_id, k):
    p, w = k.profile.get(profil_id), k.werkstoffe.get(werkstoff_id)
    if not p or not w:
        return None
    fl = flaeche_wirksam(p)
    if fl is None or w.get("dichte") is None:
        return None
    return fl * w["dichte"] / 1000


# ------------------------------------------------------------------ Positionswerte (Auftrag K–X)
def position_werte(p, kopf, k, tabellen):
    """Berechnete Spalten einer Position (Auftrag K–V, X)."""
    m = maschine(kopf, k) or {}
    pr = k.profile.get(p.get("profil_id")) if not _leer(p.get("profil_id")) else None
    w = {}
    w["profilform"] = pr.get("form") if pr else None
    w["querschnitt"] = flaeche_wirksam(pr) if pr else None
    w["wand"] = (_n(pr.get("wand")) if pr else None)
    kgm = kg_je_m(p.get("profil_id"), p.get("werkstoff_id"), k) if w["querschnitt"] is not None else None
    w["kg_m"] = kgm
    w["gewicht"] = kgm * p["laenge"] / 1000 if kgm is not None and not _leer(p.get("laenge")) else None
    w["laenge_gesamt"] = (p["laenge"] * p["stueck"] if not _leer(p.get("laenge")) and not _leer(p.get("stueck"))
                          else None)
    w["gewicht_position"] = (w["gewicht"] * p["stueck"] if w["gewicht"] is not None and not _leer(p.get("stueck"))
                             else None)
    if _leer(p.get("profil_id")):
        w["stange"] = w["end"] = w["greif"] = w["nutz"] = None
    else:
        w["stange"] = stange_wirksam(p, kopf)
        w["end"] = pr["endbeschnitt"] if pr and pr.get("endbeschnitt") is not None else (m.get("endbeschnitt") or 0)
        w["greif"] = pr["greiferrest"] if pr and pr.get("greiferrest") is not None else (m.get("greiferrest") or 0)
        w["nutz"] = w["stange"] - w["end"] - w["greif"] if w["stange"] is not None else None
    if _leer(p.get("profil_id")) or _leer(p.get("werkstoff_id")):
        w["preis_hinterlegt"] = None
    else:
        werkstoff = k.werkstoffe.get(p["werkstoff_id"]) or {}
        w["preis_hinterlegt"] = (_n(p.get("preis_m")) > 0 or preis_zeile(p["profil_id"], p["werkstoff_id"], k, tabellen)
                                 is not None or _n(werkstoff.get("tonnenpreis")) > 0)
    w["vorschub"] = None
    if w["wand"] is not None and not _leer(p.get("werkstoff_id")) and not _leer(kopf.get("maschine")):
        sd = schneiddaten(kopf.get("maschine"), p["werkstoff_id"], w["wand"], tabellen)
        w["vorschub"] = _n(sd.get("vorschub_gross")) if sd else None
    return w


def preis_zeile(profil_id, werkstoff_id, k, tabellen):
    """Gültige Zeile aus 'Preise' (Prüfung OK) für Profil + Werkstoff, sonst None."""
    from .stammdaten import PREISE, pruefen
    for z in tabellen["preise"]:
        if z.get("profil_id") == profil_id and z.get("werkstoff_id") == werkstoff_id and pruefen(PREISE, z, k) == "OK":
            return z
    return None


def schneiddaten(maschinen_id, werkstoff_id, wand, tabellen):
    """Zeile mit der kleinsten 'Wandstärke bis' ≥ wand (MINIFS der Mappe), sonst None."""
    kandidaten = [z for z in tabellen["schneiddaten"] if z.get("maschinen_id") == maschinen_id
                  and z.get("werkstoff_id") == werkstoff_id and z.get("wand_bis") is not None
                  and z["wand_bis"] >= wand]
    if not kandidaten:
        return None
    return min(kandidaten, key=lambda z: z["wand_bis"])


# ------------------------------------------------------------------ Status (Auftrag W)
def status(p, w, kopf, k, eingeplant=None):
    """Wie Spalte W der Mappe. eingeplant = Anzahl eingeplanter Teile laut Optimierung (oder None)."""
    if all(_leer(p.get(f)) for f in ("profil_id", "werkstoff_id", "laenge", "stueck")):
        return ""
    m = maschine(kopf, k)
    if p.get("profil_id") not in k.profile:
        return "FEHLER: Profil unbekannt"
    if p.get("werkstoff_id") not in k.werkstoffe:
        return "FEHLER: Werkstoff unbekannt"
    if w["querschnitt"] is None:
        return "FEHLER: Querschnitt fehlt (Profil)"
    if _leer(p.get("laenge")) or p["laenge"] <= 0:
        return "FEHLER: Teilelänge fehlt"
    if _leer(p.get("stueck")) or p["stueck"] < 1:
        return "FEHLER: Stückzahl fehlt"
    if m is None:
        return "FEHLER: Maschine fehlt/unbekannt"
    if m.get("max_stange") and w["stange"] is not None and w["stange"] > m["max_stange"]:
        return "FEHLER: Stange länger als Maschine zulässt"
    if w["nutz"] is None or p["laenge"] + _n(m.get("schnittverlust")) > w["nutz"]:
        return "FEHLER: Teil länger als Nutzlänge"
    if eingeplant is not None and _n(p.get("stueck")) - eingeplant > 0:
        return "WARNUNG: nicht vollständig eingeplant"
    if w["preis_hinterlegt"] is False:
        return "WARNUNG: kein gültiger Materialpreis"
    if not _leer(p.get("satz")) and _n(p.get("je_satz")) > 0 and _n(p.get("stueck")) % p["je_satz"] != 0:
        return "WARNUNG: Stückzahl ist kein Vielfaches von Stück je Satz"
    if _leer(p.get("schneidweg")):
        return "HINWEIS: Schneidweg fehlt"
    if w["vorschub"] is None:
        return "HINWEIS: keine Schneiddaten"
    if not _leer(p.get("gewinde_vorschlag")) and _leer(p.get("gewinde")):
        return "HINWEIS: Gewinde-Vorschlag prüfen"
    return "OK"


# ------------------------------------------------------------------ Optimierung
def gruppen_bilden(kopf, positionen, k):
    """Wie lies_auftrag in tools/optimierung.py, aber aus den Daten des Programms.
    Ergebnis: (gruppen, fehler, neue_profile). Unbekannte Profile, deren ID dem Schema entspricht
    (z. B. 'RR 42,4x2,0'), werden wie in der Mappe aus dem Namen angelegt: sie stehen in neue_profile
    und zählen hier schon als vorhanden."""
    profile = {pid: dict(form=z.get("form"), a=_n(z.get("a")), b=z.get("b"), end=z.get("endbeschnitt"),
                         greif=z.get("greiferrest")) for pid, z in k.profile.items()}
    neue_profile = []
    for p in positionen:
        pid = p.get("profil_id")
        if not _leer(pid) and pid not in profile:
            d = opt.profil_aus_name(pid)
            if d is not None:
                profile[pid] = dict(form=d["form"], a=d["a"], b=d["b"], end=None, greif=None)
                neue_profile.append(dict(profil_id=str(pid), form=d["form"], a=d["a"], b=d["b"], wand=d["wand"],
                                         bemerkung="automatisch aus Profil-ID angelegt"))
    m = maschine(kopf, k)
    if m is None:
        raise ValueError(f"Maschine '{kopf.get('maschine') or ''}' im Auftragskopf ist nicht in den Stammdaten.")
    me = dict(end=_n(m.get("endbeschnitt")), greif=_n(m.get("greiferrest")), kerf=_n(m.get("schnittverlust")),
              maxlen=m.get("max_stange"), abstand=_n(m.get("abstand")))
    std = kopf.get("stange") if isinstance(kopf.get("stange"), (int, float)) else None
    gruppen, fehler = {}, []
    for i, p in enumerate(positionen):
        r = ZEILE0 + i
        pid, wst, laenge, stk = p.get("profil_id"), p.get("werkstoff_id"), p.get("laenge"), p.get("stueck")
        laenge = laenge if isinstance(laenge, (int, float)) else None
        if all(_leer(v) for v in (pid, wst, laenge, stk)):
            continue
        name = p.get("artikel") or f"Zeile {i + 1}"
        stk_n = int(stk) if isinstance(stk, (int, float)) and stk >= 1 and int(stk) == stk else 0

        def fehl(grund):
            fehler.append(dict(index=i, pos=p.get("pos"), artikel=name, anzahl=stk_n, grund=grund))
        if pid not in profile:
            fehl("Profil unbekannt"); continue
        if wst not in k.werkstoffe:
            fehl("Werkstoff unbekannt"); continue
        if not laenge or laenge <= 0:
            fehl("Teilelänge fehlt"); continue
        if not stk_n:
            fehl("Stückzahl fehlt oder ungültig"); continue
        stange = p.get("stange") or std
        if not stange:
            fehl("Stangenlänge fehlt"); continue
        if me["maxlen"] and stange > me["maxlen"]:
            fehl("Stange länger als Maschine zulässt"); continue
        pr = profile[pid]
        end = pr["end"] if pr["end"] is not None else me["end"]
        greif = pr["greif"] if pr["greif"] is not None else me["greif"]
        if end + laenge + me["kerf"] > stange - greif + EPS:
            fehl("Teil länger als Nutzlänge der Stange"); continue
        key = (pid, wst, stange)
        g = gruppen.setdefault(key, opt.Gruppe(pid, wst, stange, end, greif, me["kerf"], me["abstand"]))
        a_ger = p.get("a_gerade") != "nein"
        b_ger = p.get("b_gerade") != "nein"
        u = opt.umfang(pr["form"], pr["a"], pr["b"])
        h = p.get("schneidweg")
        if h:
            u = min(u, h / 2)
        a_s = p.get("a_schnitt") or u
        b_s = p.get("b_schnitt") or u
        for n in range(1, stk_n + 1):
            g.teile.append(opt.Teil(r, p.get("pos"), name, n, laenge, a_ger, b_ger, a_s, b_s))
    return list(gruppen.values()), fehler, neue_profile


def eingabe_kennung(kopf, positionen, k):
    """Prüfsumme über alles, was die Optimierung verwendet. Weicht sie von der gespeicherten ab,
    ist die Optimierung veraltet (wie 'Stand Optimierung' der Mappe)."""
    try:
        gruppen, fehler, neue = gruppen_bilden(kopf, positionen, k)
    except ValueError as e:
        return "fehler:" + str(e)
    daten = [[(g.profil, g.werkstoff, g.stange, g.endbeschnitt, g.greiferrest, g.kerf, g.abstand,
               [tuple(t.__dict__.values()) for t in g.teile]) for g in gruppen],
             [sorted(f.items()) for f in fehler], [sorted(n.items()) for n in neue]]
    return hashlib.sha1(json.dumps(daten, default=str, sort_keys=True).encode()).hexdigest()


def optimieren(kopf, positionen, k):
    """Optimiert den Auftrag. Ergebnis (als JSON speicherbar):
    {'stangen': [...], 'auswertung': [...], 'fehler': [...], 'neue_profile': [...], 'kennung': str}
    Je Stange: nr, profil, werkstoff, stange, end, greif, verlust, trennungen, gemeinsam, belegung (Text),
    teile: [{index, pos, artikel, laenge, von, bis, lage, trennung, eingespart_mm, eingespart_e}]"""
    gruppen, fehler, neue_profile = gruppen_bilden(kopf, positionen, k)
    folgen_je_gruppe = [opt.optimiere(g) for g in gruppen]
    opt.pruefe(gruppen, folgen_je_gruppe)
    stangen, auswertung, nr = [], [], 0
    for g, folgen in zip(gruppen, folgen_je_gruppe):
        for folge in folgen:
            nr += 1
            pos = g.endbeschnitt
            vorher, verlust, teile, belegung, n_gem = None, 0.0, [], [], 0
            for platz, (t, gedreht) in enumerate(folge, start=1):
                a_ger, b_ger, a_s, b_s = opt.lage(t, gedreht)
                eingespart_mm, eingespart_e = 0.0, 0
                if vorher is None:
                    art = "Stangenanfang"
                else:
                    gap = opt.trennung(g.kerf, g.abstand, vorher[0], a_ger)
                    gemeinsam = vorher[0] and a_ger
                    art = "gemeinsamer Schnitt" if gemeinsam else "2 Schnitte"
                    if gemeinsam:
                        n_gem += 1
                        eingespart_mm, eingespart_e = min(vorher[1], a_s), 1
                    pos += gap
                    verlust += gap
                teile.append(dict(index=t.zeile - ZEILE0, ref=schluessel(positionen[t.zeile - ZEILE0], t.zeile - ZEILE0),
                                  pos=t.pos, artikel=t.artikel, laenge=t.laenge,
                                  von=round(pos, 2), bis=round(pos + t.laenge, 2),
                                  lage="gedreht" if gedreht else "normal", trennung=art,
                                  eingespart_mm=round(eingespart_mm, 1), eingespart_e=eingespart_e))
                pos += t.laenge
                vorher = (b_ger, b_s)
                belegung.append(f"{t.pos if t.pos is not None else t.artikel}×{t.laenge:g}")
            verlust += g.kerf
            stangen.append(dict(nr=nr, profil=g.profil, werkstoff=g.werkstoff, stange=g.stange, end=g.endbeschnitt,
                                greif=g.greiferrest, verlust=round(verlust, 2), trennungen=len(folge),
                                gemeinsam=n_gem, belegung=" | ".join(belegung), teile=teile))
        man = opt.manuell(g)
        auswertung.append(dict(profil=g.profil, werkstoff=g.werkstoff, stange=g.stange, teile=len(g.teile),
                               stangen=len(folgen), manuell=len(man), untergrenze=opt.untergrenze(g),
                               ausnutzung_manuell=(sum(t.laenge for t in g.teile) / (len(man) * g.stange)
                                                   if man else 0),
                               gemeinsam=sum(opt.gemeinsame_schnitte(f) for f in folgen),
                               bewertung=opt.bewertung(g, len(folgen))))
    return dict(stangen=stangen, auswertung=auswertung, fehler=fehler, neue_profile=neue_profile,
                kennung=eingabe_kennung(kopf, positionen, k))


# ------------------------------------------------------------------ Schnittplan-Werte (Schnittplan G–R)
def stangen_werte(ergebnis, kopf, positionen, k, tabellen):
    """Berechnete Spalten je Stange: teile, summe, belegt, rest, ausnutzung, pruefung, gewicht, kosten."""
    out = []
    for s in ergebnis["stangen"]:
        summe = sum(t["laenge"] for t in s["teile"])
        belegt = s["end"] + summe + s["verlust"]
        max_bis = max((t["bis"] for t in s["teile"]), default=0)
        kgm = kg_je_m(s["profil"], s["werkstoff"], k)
        gewicht = s["stange"] / 1000 * kgm if kgm is not None else None
        out.append(dict(teile=len(s["teile"]), summe=summe, belegt=belegt, rest=s["stange"] - belegt,
                        ausnutzung=summe / s["stange"],
                        pruefung="ÜBERBELEGT" if (belegt + s["greif"] > s["stange"] + 0.001
                                                  or max_bis > s["stange"] - s["greif"] + 0.001) else "OK",
                        gewicht=gewicht, kosten=stangenkosten(s, gewicht, kopf, positionen, k, tabellen)))
    return out


def stangenkosten(s, gewicht, kopf, positionen, k, tabellen):
    """Materialkosten einer Stange (Schnittplan R): Preis €/m im Auftrag > 'Preise' > Tonnenpreis."""
    ab = [p["preis_m"] for p in positionen if _n(p.get("preis_m")) and p.get("profil_id") == s["profil"]
          and p.get("werkstoff_id") == s["werkstoff"] and stange_wirksam(p, kopf) == s["stange"]]
    if ab and max(ab) > 0:
        return max(ab) * s["stange"] / 1000
    z = preis_zeile(s["profil"], s["werkstoff"], k, tabellen)
    if z is not None:
        if z["basis"] == "€/kg":
            return _n(gewicht) * z["preis"]
        if z["basis"] == "€/m":
            return z["preis"] * s["stange"] / 1000
        if z["basis"] == "€/Stange":
            return z["preis"] * s["stange"] / z["lieferlaenge"]
    tonne = _n((k.werkstoffe.get(s["werkstoff"]) or {}).get("tonnenpreis"))
    return _n(gewicht) * tonne / 1000


# ------------------------------------------------------------------ Kalkulation (Blatt Kalkulation)
def gewindezeit(text, gewinde):
    """Gewindezeit je Teil [s] aus 'Gewinde geprüft' (z. B. '4xM6; 2xM8') wie Kalkulation P."""
    t = ";" + str(text or "").upper().replace(" ", "") + ";"
    summe = 0.0
    try:
        for g in gewinde:
            kenn = "X" + str(g.get("gewinde") or "").upper() + ";"
            s = t + kenn
            vor = s[:s.find(kenn)]
            teil = vor.split(";")[-1].strip()
            summe += float("0" + teil) * _n(g.get("zeit"))
    except ValueError:
        return 0.0
    return summe


def kalkulation(kopf, positionen, ergebnis, k, tabellen, einstellungen):
    """Kalkulation je Position und Summen. Ergebnis: (zeilen, summen); zeilen[i] ist None für
    Positionen ohne Profil (wie leere Zeilen der Mappe)."""
    m = maschine(kopf, k) or {}
    satz_h = _n(m.get("stundensatz"))
    stangen = ergebnis["stangen"] if ergebnis else []
    sw = stangen_werte(ergebnis, kopf, positionen, k, tabellen) if ergebnis else []
    zm, zf, gew = (_n(einstellungen.get(n)) for n in ("zuschlag_material", "zuschlag_fertigung", "gewinn"))
    ruest, wechsel = _n(m.get("ruestzeit")), _n(m.get("stangenwechsel"))
    f7 = (ruest * 60 + wechsel * len(stangen)) / 3600 * satz_h
    aktiv = [i for i, p in enumerate(positionen) if not _leer(p.get("profil_id"))]
    f8 = sum(_n(positionen[i].get("stueck")) for i in aktiv)
    eingespart = {}
    for s in stangen:
        for t in s["teile"]:
            e = eingespart.setdefault(t["ref"], [0, 0.0, 0])
            e[0] += 1
            e[1] += t["eingespart_mm"]
            e[2] += t["eingespart_e"]
    zeilen = [None] * len(positionen)
    for i in aktiv:
        p = positionen[i]
        w = position_werte(p, kopf, k, tabellen)
        c = _n(p.get("stueck"))
        q = stange_wirksam(p, kopf)
        d = sum(x["kosten"] for s, x in zip(stangen, sw) if s["profil"] == p.get("profil_id")
                and s["werkstoff"] == p.get("werkstoff_id") and s["stange"] == q)
        gesamt = sum(_n(x.get("laenge")) * _n(x.get("stueck")) for x in positionen
                     if x.get("profil_id") == p.get("profil_id") and x.get("werkstoff_id") == p.get("werkstoff_id")
                     and stange_wirksam(x, kopf) == q and not _leer(x.get("laenge")) and not _leer(x.get("stueck")))
        e = _n(w["laenge_gesamt"]) / gesamt if gesamt else 0
        f = d * e / c if c else 0
        sd = schneiddaten(kopf.get("maschine"), p.get("werkstoff_id"), _n(w["wand"]), tabellen)
        z = dict(pos=p.get("pos"), artikel=p.get("artikel"), stueck=c, material_gruppe=d, anteil=e,
                 material_teil=f, wand_stufe=sd["wand_bis"] if sd else None)
        if sd and sd.get("wand_bis"):
            h = _n(sd.get("vorschub_gross"))
            i_ = _n(sd.get("vorschub_mittel")) or h
            j = _n(sd.get("vorschub_klein")) or i_
            kv = _n(sd.get("vorschub_gravur")) or h
            l = _n(sd.get("einstechzeit"))
        else:
            h = i_ = j = kv = l = None
        z.update(vorschub_gross=h, vorschub_mittel=i_, vorschub_klein=j, vorschub_gravur=kv, einstechzeit=l)
        if h is None:
            mz = None
        else:
            try:
                mz = 60 * ((_n(p.get("schneidweg")) - _n(p.get("klein_mm")) - _n(p.get("mittel_mm"))) / h
                           + _n(p.get("klein_mm")) / j + _n(p.get("mittel_mm")) / i_ + _n(p.get("gravur")) / kv) \
                    + _n(p.get("einstiche")) * l
            except ZeroDivisionError:
                mz = None
        ein = eingespart.get(schluessel(p, i), [0, 0.0, 0])
        if h is None or c == 0 or not h:
            nz = 0
        else:
            nz = (60 * ein[1] / h + ein[2] * l) / c
        oz = None if mz is None else max(0, mz - nz)
        pz = gewindezeit(p.get("gewinde"), tabellen["gewinde"])
        qz = (_n(oz) + pz) / 3600 * satz_h
        rz = f7 / f8 if f8 else 0
        s_ = f * (1 + zm) + (qz + rz) * (1 + zf)
        t_ = s_ * (1 + gew)
        nicht = c - ein[0] if (stangen and not _leer(p.get("stueck"))) else None
        if _n(nicht) > 0:
            hinweis = "nicht vollständig eingeplant"
        elif d == 0:
            hinweis = "kein Schnittplan oder Preis"
        elif h is None:
            hinweis = "keine Schneiddaten"
        elif not _leer(p.get("gewinde_vorschlag")) and _leer(p.get("gewinde")):
            hinweis = "Gewinde ungeprüft"
        else:
            hinweis = ""
        z.update(laser_brutto=mz, einsparung=nz, laser_netto=oz, gewindezeit=pz, laser_teil=qz, ruesten_teil=rz,
                 herstell_teil=s_, preis_teil=t_, preis_position=t_ * c, herstell_position=s_ * c,
                 material_position=f * c, laser_position=qz * c, hinweis=hinweis, eingeplant=ein[0],
                 nicht_eingeplant=nicht)
        zeilen[i] = z
    summen = dict(ruestzeit=ruest, stangenwechsel=wechsel, stangen=len(stangen), ruesten=f7, teile=f8,
                  material=sum(z["material_position"] for z in zeilen if z),
                  laser=sum(z["laser_position"] for z in zeilen if z),
                  herstell=sum(z["herstell_position"] for z in zeilen if z),
                  verkauf=sum(z["preis_position"] for z in zeilen if z))
    return zeilen, summen


def eingeplant_je_position(ergebnis):
    """{Bezug (schluessel): Anzahl eingeplanter Teile}"""
    n = {}
    for s in (ergebnis or {}).get("stangen", []):
        for t in s["teile"]:
            n[t["ref"]] = n.get(t["ref"], 0) + 1
    return n


def stangenmuster(ergebnis):
    """Gleich belegte Stangen zusammenfassen (Profil, Werkstoff, Stangenlänge, gleiche Teile in gleicher
    Reihenfolge und Lage), wie Werkstattpapier und Stangenbild der Mappe. Ergebnis: [(Stange, [Nummern])]."""
    muster = {}
    for s in (ergebnis or {}).get("stangen", []):
        schl = (s["profil"], s["werkstoff"], s["stange"],
                tuple((t["ref"], t["laenge"], t["lage"]) for t in s["teile"]))
        muster.setdefault(schl, (s, []))[1].append(s["nr"])
    return list(muster.values())
