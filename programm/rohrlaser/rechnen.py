"""Rechnungen eines Auftrags: Positionswerte und Status, Stangenoptimierung, Schnittplan, Kalkulation.

Jede Funktion bildet die entsprechenden Formeln bzw. Makros der Mappe nach (Blätter Auftrag,
Schnittplan, Stangenbelegung, Auswertung, Kalkulation in tools/build_mappe.py). Die Optimierung selbst
ist dieselbe wie in der Mappe (tools/optimierung.py). tests/test_programm_mappe.py vergleicht die
Ergebnisse mit der in LibreOffice gerechneten Mappe.

Eingaben: kopf (dict: maschine, stange, …), positionen (Liste von dicts, Reihenfolge = Zeilen im
Auftrag), k (stammdaten.Kontext), tabellen (dict mit 'preise', 'schneiddaten', 'gewinde' und
'zusatzarbeiten': Zeilen; fehlen die Zusatzarbeiten, gibt es keine).
"""
import hashlib
import json

from .stammdaten import ZUSATZ_EINHEIT, flaeche_berechnet, flaeche_wirksam, huellkreis
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


def grenze_ueberschritten(m, profil, kgm):
    """Prüfung gegen die Maschinengrenzen max. Hüllkreis-Ø und max. Metergewicht (leer = keine Grenze).
    profil: Profilzeile (form, a, b), kgm: kg/m oder None. Ergebnis: Grund als Text oder None."""
    hk = huellkreis(profil) if profil else None
    if _n(m.get("max_huellkreis")) > 0 and hk is not None and hk > m["max_huellkreis"] + EPS:
        return "Hüllkreis größer als Maschine zulässt"
    if _n(m.get("max_kg_m")) > 0 and kgm is not None and kgm > m["max_kg_m"] + EPS:
        return "Metergewicht über Maschinengrenze"
    return None


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
    w["huellkreis"] = huellkreis(pr) if pr else None
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
    w["zusatzarbeiten"] = tabellen.get("zusatzarbeiten")
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
    grenze = grenze_ueberschritten(m, k.profile.get(p.get("profil_id")), w["kg_m"])
    if grenze:
        return "FEHLER: " + grenze
    if w["nutz"] is None or p["laenge"] + _n(m.get("schnittverlust")) > w["nutz"]:
        return "FEHLER: Teil länger als Nutzlänge"
    if eingeplant is not None and _n(p.get("stueck")) - eingeplant > 0:
        return "WARNUNG: nicht vollständig eingeplant"
    if w["preis_hinterlegt"] is False:
        return "WARNUNG: kein gültiger Materialpreis"
    if not _leer(p.get("satz")) and _n(p.get("je_satz")) > 0 and _n(p.get("stueck")) % p["je_satz"] != 0:
        return "WARNUNG: Stückzahl ist kein Vielfaches von Stück je Satz"
    unbekannt = zusatz_unbekannt(p, w.get("zusatzarbeiten"))
    if unbekannt:
        return f"WARNUNG: Zusatzarbeit '{unbekannt}' unbekannt"
    manuell = not _leer(p.get("zeit_manuell"))
    if _leer(p.get("schneidweg")) and not manuell:
        return "HINWEIS: Schneidweg fehlt"
    if w["vorschub"] is None and not manuell:
        return "HINWEIS: keine Schneiddaten"
    if not _leer(p.get("gewinde_vorschlag")) and _leer(p.get("gewinde")):
        return "HINWEIS: Gewinde-Vorschlag prüfen"
    if manuell:
        return "HINWEIS: Schneidzeit manuell"
    return "OK"


# ------------------------------------------------------------------ Optimierung
def gruppen_bilden(kopf, positionen, k):
    """Wie lies_auftrag in tools/optimierung.py, aber aus den Daten des Programms.
    Ergebnis: (gruppen, fehler, neue_profile). Unbekannte Profile, deren ID dem Schema entspricht
    (z. B. 'RR 42,4x2,0'), werden wie in der Mappe aus dem Namen angelegt: sie stehen in neue_profile
    und zählen hier schon als vorhanden."""
    profile = {pid: dict(form=z.get("form"), a=_n(z.get("a")), b=z.get("b"), end=z.get("endbeschnitt"),
                         greif=z.get("greiferrest"), flaeche=flaeche_wirksam(z)) for pid, z in k.profile.items()}
    neue_profile = []
    for p in positionen:
        pid = p.get("profil_id")
        if not _leer(pid) and pid not in profile:
            d = opt.profil_aus_name(pid)
            if d is not None:
                profile[pid] = dict(form=d["form"], a=d["a"], b=d["b"], end=None, greif=None,
                                    flaeche=flaeche_berechnet(dict(d, profil_id=pid)))
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
        dichte = (k.werkstoffe.get(wst) or {}).get("dichte")
        grenze = grenze_ueberschritten(m, pr, pr["flaeche"] * dichte / 1000
                                       if pr["flaeche"] is not None and dichte is not None else None)
        if grenze:
            fehl(grenze); continue
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
def gewinde_anzahl(text, gewinde):
    """{Gewinde: Anzahl je Teil} aus 'Gewinde geprüft' (z. B. '4xM6; 2xM8') wie Kalkulation P der Mappe."""
    t = ";" + str(text or "").upper().replace(" ", "") + ";"
    n = {}
    try:
        for g in gewinde:
            kenn = "X" + str(g.get("gewinde") or "").upper() + ";"
            s = t + kenn
            vor = s[:s.find(kenn)]
            teil = vor.split(";")[-1].strip()
            n[g.get("gewinde")] = float("0" + teil)
    except ValueError:
        return {}
    return n


def gewindezeit(text, gewinde):
    """Gewindezeit je Teil [s] für Gewinde ohne festen Preis (Zeit je Gewinde × Anzahl)."""
    anz = gewinde_anzahl(text, gewinde)
    return sum(anz.get(g.get("gewinde"), 0) * _n(g.get("zeit")) for g in gewinde if _leer(g.get("preis")))


def gewinde_preis(text, gewinde):
    """Festpreis der Gewinde je Teil [€]: Anzahl × Preis je Gewinde (nur Gewinde mit Preis)."""
    anz = gewinde_anzahl(text, gewinde)
    return sum(anz.get(g.get("gewinde"), 0) * _n(g.get("preis")) for g in gewinde if not _leer(g.get("preis")))


# ------------------------------------------------------------------ Zusatzarbeiten
def zusatz_liste(p):
    """Gewählte Zusatzarbeiten einer Position: [{name, menge, preis, text}] (leere Werte = automatisch)."""
    roh = p.get("zusatz")
    if not roh:
        return []
    try:
        liste = json.loads(roh) if isinstance(roh, str) else roh
    except ValueError:
        return []
    return [z for z in liste if isinstance(z, dict) and z.get("name")] if isinstance(liste, list) else []


def zusatz_text(p):
    """Kurzanzeige in der Positionstabelle, z. B. 'Feuerverzinken; Pulverbeschichten RAL 7016'."""
    return "; ".join(z["name"] + (f" {z['text']}" if z.get("text") else "") for z in zusatz_liste(p))


def zusatz_unbekannt(p, katalog):
    namen = {z.get("name") for z in katalog or ()}
    return next((z["name"] for z in zusatz_liste(p) if z["name"] not in namen), None)


def oberflaeche(p, k):
    """Außenfläche eines Teils [m²] = Umfang × Länge (ohne Stirnflächen und Innenseite)."""
    pr = k.profile.get(p.get("profil_id"))
    if not pr or _leer(p.get("laenge")) or pr.get("a") is None:
        return None
    u = opt.umfang(pr.get("form"), pr["a"], pr.get("b"))
    return u * p["laenge"] / 1e6 if u else None


def zusatz_menge_auto(art, p, k):
    """Vorschlag Menge je Teil: kg = Teilegewicht, m² = Außenfläche, m = Teilelänge, sonst 1 Stück."""
    if art == "€/kg":
        kgm = kg_je_m(p.get("profil_id"), p.get("werkstoff_id"), k)
        return kgm * p["laenge"] / 1000 if kgm is not None and not _leer(p.get("laenge")) else None
    if art == "€/m²":
        return oberflaeche(p, k)
    if art == "€/m":
        return p["laenge"] / 1000 if not _leer(p.get("laenge")) else None
    return 1.0


def zusatz_werte(p, k, tabellen):
    """Zusatzarbeiten einer Position je Teil: [{name, art, einheit, menge, preis, betrag, zeit, fremd, text,
    angebotstext, mindest}]. betrag = € je Teil (ohne Mindestbetrag), zeit = s je Teil (Art s/Stück).
    Unbekannte Namen werden ausgelassen (Status zeigt eine Warnung)."""
    katalog = {z.get("name"): z for z in tabellen.get("zusatzarbeiten") or ()}
    out = []
    for e in zusatz_liste(p):
        kz = katalog.get(e["name"])
        if kz is None:
            continue
        art = kz.get("art")
        menge = e.get("menge") if isinstance(e.get("menge"), (int, float)) else zusatz_menge_auto(art, p, k)
        preis = e.get("preis") if isinstance(e.get("preis"), (int, float)) else _n(kz.get("preis"))
        wert = _n(menge) * preis
        out.append(dict(name=e["name"], art=art, einheit=ZUSATZ_EINHEIT.get(art, ""), menge=menge, preis=preis,
                        betrag=0.0 if art == "s/Stück" else wert, zeit=wert if art == "s/Stück" else 0.0,
                        fremd=kz.get("fremd") == "ja", text=e.get("text"), mindest=_n(kz.get("mindest")),
                        angebotstext=kz.get("angebotstext") or e["name"]))
    return out


def zahl(w, stellen=2):
    """Kurze Zahl für Texte: 2,35 / 1 (ohne unnötige Nachkommastellen)."""
    if not isinstance(w, (int, float)):
        return "?"
    return f"{w:.{stellen}f}".rstrip("0").rstrip(".").replace(".", ",")


def kalkulation(kopf, positionen, ergebnis, k, tabellen, einstellungen):
    """Kalkulation je Position und Summen. Ergebnis: (zeilen, summen); zeilen[i] ist None für
    Positionen ohne Profil (wie leere Zeilen der Mappe).

    Über die Mappe hinaus (fehlen die Einstellungen, ist alles 0 und die Rechnung gleich der Mappe):
    - Rüstzeit je Abmessung (Einstellung, min) für jede Abmessung (Profil-ID) mit Stückzahl, mit dem
      Maschinenstundensatz bewertet, umgelegt auf die Teile dieser Abmessung; zählt zu Rüsten und damit zu
      den Herstellkosten (mit Zuschlag Fertigung und Gewinn).
    - Pauschale je Abmessung (€), umgelegt auf die Teile dieser Abmessung, Auftragsaufschlag (€) und
      Frachtkosten aus dem Auftragskopf (€), umgelegt auf alle Teile; gehen ohne Zuschläge in den
      Verkaufspreis ein.
    - Programmierkosten je Teil (Einstellung, €) für jede Position mit Stückzahl, umgelegt auf deren
      Stückzahl, ohne Zuschläge in den Verkaufspreis.
    - Gewinde mit festem Preis (Stammdaten Gewinde) zählen mit dem Preis statt mit der Zeit.
    - Schneidzeit manuell (Position) ersetzt die berechnete Laserzeit netto je Teil.
    - Zusatzarbeiten je Position: Beträge je Teil (€/kg, €/m², €/m, €/Stück) mit Zuschlag Fremdleistung bzw.
      Fertigung; liegt die Summe einer Zusatzarbeit im Auftrag unter ihrem Mindestbetrag, wird sie anteilig
      angehoben. Zeiten (s/Stück) kommen zur Laserzeit, auch zur manuellen."""
    m = maschine(kopf, k) or {}
    satz_h = _n(m.get("stundensatz"))
    stangen = ergebnis["stangen"] if ergebnis else []
    sw = stangen_werte(ergebnis, kopf, positionen, k, tabellen) if ergebnis else []
    zm, zf, gew = (_n(einstellungen.get(n)) for n in ("zuschlag_material", "zuschlag_fertigung", "gewinn"))
    ruest, wechsel = _n(m.get("ruestzeit")), _n(m.get("stangenwechsel"))
    f7 = (ruest * 60 + wechsel * len(stangen)) / 3600 * satz_h
    aktiv = [i for i, p in enumerate(positionen) if not _leer(p.get("profil_id"))]
    f8 = sum(_n(positionen[i].get("stueck")) for i in aktiv)
    teile_abm = {}
    for i in aktiv:
        if _n(positionen[i].get("stueck")) > 0:
            pid = positionen[i]["profil_id"]
            teile_abm[pid] = teile_abm.get(pid, 0) + _n(positionen[i]["stueck"])
    ruest_abm_min = _n(einstellungen.get("ruesten_abmessung"))
    ruest_abm = ruest_abm_min / 60 * satz_h            # € je Abmessung
    pausch_abm = _n(einstellungen.get("pauschale_abmessung"))
    prog = _n(einstellungen.get("programmierung_teil"))   # € je Teil (Position mit Stückzahl), einmal je Auftrag
    zfl = _n(einstellungen.get("zuschlag_fremdleistung"))
    zus = {i: zusatz_werte(positionen[i], k, tabellen) for i in aktiv}
    zus_summe, zus_teile = {}, {}
    for i in aktiv:
        c = _n(positionen[i].get("stueck"))
        for e in zus[i]:
            zus_summe[e["name"]] = zus_summe.get(e["name"], 0.0) + e["betrag"] * c
            zus_teile[e["name"]] = zus_teile.get(e["name"], 0) + c
    for i in aktiv:                   # Mindestbetrag je Auftrag: anteilig anheben
        for e in zus[i]:
            if e["art"] == "s/Stück" or e["mindest"] <= 0 or not zus_teile[e["name"]]:
                e["teil"] = e["betrag"]
            elif zus_summe[e["name"]] <= 0:
                e["teil"] = e["mindest"] / zus_teile[e["name"]]
            else:
                e["teil"] = e["betrag"] * max(1.0, e["mindest"] / zus_summe[e["name"]])
    aufschlag = _n(einstellungen.get("auftragsaufschlag")) if f8 else 0
    fracht = _n(kopf.get("fracht")) if f8 else 0
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
        manuell = not _leer(p.get("zeit_manuell"))
        zeit_extra = sum(e["zeit"] for e in zus[i])
        if manuell:
            oz = _n(p["zeit_manuell"]) + zeit_extra
        else:
            oz = None if mz is None and not zeit_extra else max(0, _n(mz) - nz) + zeit_extra
        pz = gewindezeit(p.get("gewinde"), tabellen["gewinde"])
        gp = gewinde_preis(p.get("gewinde"), tabellen["gewinde"])
        qz = (_n(oz) + pz) / 3600 * satz_h + gp
        ze = sum(e["teil"] for e in zus[i] if not e["fremd"])
        zfr = sum(e["teil"] for e in zus[i] if e["fremd"])
        n_abm = teile_abm.get(p.get("profil_id"), 0)
        rz = (f7 / f8 if f8 else 0) + (ruest_abm / n_abm if n_abm and c else 0)
        uz = (pausch_abm / n_abm if n_abm and c else 0) + ((aufschlag + fracht) / f8 if f8 and c else 0) \
            + (prog / c if c else 0)
        s_ = f * (1 + zm) + (qz + rz + ze) * (1 + zf) + zfr * (1 + zfl)
        t_ = s_ * (1 + gew) + uz
        nicht = c - ein[0] if (stangen and not _leer(p.get("stueck"))) else None
        if _n(nicht) > 0:
            hinweis = "nicht vollständig eingeplant"
        elif d == 0:
            hinweis = "kein Schnittplan oder Preis"
        elif h is None and not manuell:
            hinweis = "keine Schneiddaten"
        elif zusatz_unbekannt(p, tabellen.get("zusatzarbeiten")):
            hinweis = "Zusatzarbeit unbekannt"
        elif not _leer(p.get("gewinde_vorschlag")) and _leer(p.get("gewinde")):
            hinweis = "Gewinde ungeprüft"
        else:
            hinweis = ""
        z.update(zeit_manuell="ja" if manuell else "", zeit_extra=zeit_extra, gewinde_preis=gp,
                 zusatz_teil=ze + zfr, zusatz_position=(ze + zfr) * c, zusatzarbeiten=zus[i],
                 zusatz_text="; ".join(f"{e['name']} {zahl(e['menge'])} {e['einheit']}" for e in zus[i]))
        z.update(laser_brutto=mz, einsparung=nz, laser_netto=oz, gewindezeit=pz, laser_teil=qz, ruesten_teil=rz,
                 herstell_teil=s_, pauschalen_teil=uz, preis_teil=t_, preis_position=t_ * c, herstell_position=s_ * c,
                 material_position=f * c, laser_position=qz * c, hinweis=hinweis, eingeplant=ein[0],
                 nicht_eingeplant=nicht)
        zeilen[i] = z
    n_abm = len(teile_abm)
    summen = dict(ruestzeit=ruest, stangenwechsel=wechsel, stangen=len(stangen), teile=f8,
                  abmessungen=n_abm, ruestzeit_abmessung=ruest_abm_min, ruesten=f7 + ruest_abm * n_abm,
                  pauschalen=pausch_abm * n_abm, auftragsaufschlag=aufschlag, fracht=fracht,
                  programmierung=prog * sum(1 for i in aktiv if _n(positionen[i].get("stueck")) > 0),
                  material=sum(z["material_position"] for z in zeilen if z),
                  laser=sum(z["laser_position"] for z in zeilen if z),
                  zusatz=sum(z["zusatz_position"] for z in zeilen if z),
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


def auswertung_zeilen(ergebnis, sw):
    """Auswertung je Gruppe mit Materialbedarf, Teilelänge und Verschnitt [m] (Blatt Auswertung).
    sw = stangen_werte(...)"""
    out = []
    for a in ergebnis["auswertung"]:
        st_g = [(s, w) for s, w in zip(ergebnis["stangen"], sw)
                if (s["profil"], s["werkstoff"], s["stange"]) == (a["profil"], a["werkstoff"], a["stange"])]
        bedarf = sum(s["stange"] for s, _ in st_g) / 1000
        laenge = sum(w["summe"] for _, w in st_g) / 1000
        out.append(dict(a, bedarf=bedarf, laenge=laenge, verschnitt=bedarf - laenge,
                        ausnutzung=laenge / bedarf if bedarf else 0))
    return out
