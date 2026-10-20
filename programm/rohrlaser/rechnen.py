"""Rechnungen eines Angebots: Positionswerte und Status, Stangenoptimierung, Schnittplan, Kalkulation.

Positionswerte und Status, Schnittplan, Stangenbelegung, Auswertung und Kalkulation. Die Optimierung
selbst steht in optimierung.py; tests/test_abnahme.py rechnet die Ergebnisse unabhängig nach.

Eingaben: kopf (dict: maschine, stange, …), positionen (Liste von dicts, Reihenfolge = Zeilen im
Angebot), k (stammdaten.Kontext), tabellen (dict mit 'preise', 'schneiddaten', 'gewinde' und
'zusatzarbeiten': Zeilen; fehlen die Zusatzarbeiten, gibt es keine).
"""
import hashlib
import json

from .stammdaten import (GASE, ROH, SATZ_MASCHINE, SCHRITTE_FEST, ZEITEINHEITEN, ZUSATZ_EINHEIT, flaeche_berechnet,
                         flaeche_wirksam, huellkreis)
from . import optimierung as opt
from .angebot import aktiv as position_aktiv, ist_zukaufteil
from . import fracht_angebot
from . import zukauf

EPS = opt.EPS
ZEILE0 = 13   # Teil.zeile = ZEILE0 + Index der Position (so stehen sie in gespeicherten Ergebnissen)


def _n(v):
    """Zahl oder 0."""
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _leer(v):
    return v is None or v == ""


def schluessel(p, i):
    """Bezug eines eingeplanten Teils auf seine Position: Datenbank-ID, sonst Zeilenindex."""
    return f"id{p['id']}" if p.get("id") is not None else f"ix{i}"


def maschine(kopf, k):
    return k.maschinen.get(kopf.get("maschine"))


def stange_wirksam(p, kopf):
    """Angebot Q: abweichende Stangenlänge der Position, sonst Standard aus dem Kopf."""
    return p.get("stange") if not _leer(p.get("stange")) else kopf.get("stange")


def oberflaeche_von(p):
    """Oberfläche einer Position; leer und 'roh' sind gleich ('')."""
    o = str(p.get("oberflaeche") or "").strip()
    return "" if o.lower() == ROH else o


def gruppe_von(p, kopf):
    """Stangengruppe einer Position: (Profil, Werkstoff, Oberfläche, Stangenlänge)."""
    return (p.get("profil_id"), p.get("werkstoff_id"), oberflaeche_von(p), stange_wirksam(p, kopf))


def gruppe_der_stange(s):
    """Stangengruppe einer Stange oder Auswertungszeile (gespeicherte Ergebnisse ohne Oberfläche = roh)."""
    return (s["profil"], s["werkstoff"], s.get("oberflaeche") or "", s["stange"])


def material_text(werkstoff, oberflaeche):
    """'1.4301' bzw. '1.4301 K240' für Listen und Papiere."""
    return f"{werkstoff} {oberflaeche}" if oberflaeche else str(werkstoff or "")


def kategorie(werkstoff_id, k):
    return (k.werkstoffe.get(werkstoff_id) or {}).get("kategorie")


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


# ------------------------------------------------------------------ Positionswerte
def position_werte(p, kopf, k, tabellen):
    """Berechnete Spalten einer Position."""
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
    w["gas"] = None
    if ist_zukaufteil(p):        # eingekauftes Teil: nur Gewicht (Fracht), keine Fertigungswerte
        g = p.get("gewicht_teil")
        w["gewicht"] = g if isinstance(g, (int, float)) and g > 0 else None
        w["gewicht_position"] = (w["gewicht"] * p["stueck"] if w["gewicht"] is not None and not _leer(p.get("stueck"))
                                 else None)
        return w
    if w["wand"] is not None and not _leer(p.get("werkstoff_id")) and not _leer(kopf.get("maschine")):
        sd = schneiddaten(kopf.get("maschine"), p["werkstoff_id"], w["wand"], tabellen,
                          kategorie(p["werkstoff_id"], k))
        w["vorschub"] = _n(sd.get("vorschub_gross")) if sd else None
        w["gas"] = sd.get("gas") if sd else None
    return w


def preis_zeile(profil_id, werkstoff_id, k, tabellen):
    """Gültige Zeile aus 'Preise' (Prüfung OK) für Profil + Werkstoff, sonst None."""
    from .stammdaten import PREISE, pruefen
    for z in tabellen["preise"]:
        if z.get("profil_id") == profil_id and z.get("werkstoff_id") == werkstoff_id and pruefen(PREISE, z, k) == "OK":
            return z
    return None


def schneiddaten(maschinen_id, werkstoff_id, wand, tabellen, kategorie=None):
    """Schneiddaten-Zeile für Maschine + Werkstoff und Wandstärke, sonst None.
    Zuerst die Zeilen des Werkstoffs, ohne passende die Zeilen seiner Kategorie (Werkstoff-ID leer). Je Schneidgas
    gilt die Zeile mit der kleinsten 'Wandstärke bis' ≥ wand; N₂ geht vor O₂, Zeilen ohne Gas zuletzt. So endet N₂
    dort, wo die N₂-Zeilen enden, darüber gilt O₂."""
    zeilen = [z for z in tabellen["schneiddaten"] if z.get("maschinen_id") == maschinen_id
              and z.get("wand_bis") is not None and z["wand_bis"] >= wand]
    eigene = [z for z in zeilen if z.get("werkstoff_id") == werkstoff_id and not _leer(werkstoff_id)]
    kat = [z for z in zeilen if _leer(z.get("werkstoff_id")) and not _leer(kategorie) and z.get("kategorie") == kategorie]
    for kandidaten in (eigene, kat):
        for gas in GASE + (None,):
            je_gas = [z for z in kandidaten if (z.get("gas") or None) == gas]
            if je_gas:
                return min(je_gas, key=lambda z: z["wand_bis"])
    return None


# ------------------------------------------------------------------ Status
def zukaufteil_status(p):
    """Status einer Zukaufteil-Position: Stückzahl, Zukaufartikel und Einkaufspreis (0 € zählt nicht)."""
    if _leer(p.get("stueck")) or p["stueck"] < 1:
        return "FEHLER: Stückzahl fehlt"
    eintraege = zukauf.eintraege(p)
    if not eintraege:
        return "FEHLER: Zukaufartikel fehlt (Zukaufteile …)"
    for e in eintraege:
        if zukauf.ek_fehlt(dict(bezuege=[(e.get("stand") or {}).get("bezug") or {}])):
            return "WARNUNG: EK fehlt (Zukaufteil ohne Einkaufspreis)"
    if not _leer(p.get("satz")) and _n(p.get("je_satz")) > 0 and _n(p.get("stueck")) % p["je_satz"] != 0:
        return "WARNUNG: Stückzahl ist kein Vielfaches von Stück je Satz"
    return "OK"


def status(p, w, kopf, k, eingeplant=None):
    """Status einer Position. eingeplant = Anzahl eingeplanter Teile laut Optimierung (oder None)."""
    if ist_zukaufteil(p):
        return zukaufteil_status(p)
    if all(_leer(p.get(f)) for f in ("profil_id", "werkstoff_id", "laenge", "stueck")):
        return ""
    m = maschine(kopf, k)
    if p.get("profil_id") not in k.profile:
        return "FEHLER: Profil unbekannt"
    if p.get("werkstoff_id") not in k.werkstoffe:
        return "FEHLER: Werkstoff unbekannt"
    ob = oberflaeche_von(p)
    if ob and ob not in k.oberflaechen:
        return "FEHLER: Oberfläche unbekannt"
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
    kat_o = (k.oberflaechen.get(ob) or {}).get("kategorie") if ob else None
    if kat_o and kat_o != kategorie(p.get("werkstoff_id"), k):
        return f"WARNUNG: Oberfläche {ob} ist für {kat_o}"
    if not _leer(p.get("satz")) and _n(p.get("je_satz")) > 0 and _n(p.get("stueck")) % p["je_satz"] != 0:
        return "WARNUNG: Stückzahl ist kein Vielfaches von Stück je Satz"
    unbekannt = zusatz_unbekannt(p, w.get("zusatzarbeiten"))
    if unbekannt:
        return f"WARNUNG: Zusatzarbeit '{unbekannt}' unbekannt"
    manuell = not _leer(p.get("zeit_manuell"))
    kontur = konturen_pruefen(p)
    if kontur and not manuell:
        return "WARNUNG: " + kontur
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
    """Optimierungsgruppen (Profil + Werkstoff + Oberfläche + Stangenlänge) aus den Positionen.
    Ergebnis: (gruppen, fehler, neue_profile). Unbekannte Profile, deren ID dem Schema entspricht
    (z. B. 'RR 42,4x2,0'), werden aus dem Namen angelegt: sie stehen in neue_profile
    und zählen hier schon als vorhanden."""
    profile = {pid: dict(form=z.get("form"), a=_n(z.get("a")), b=z.get("b"), wand=z.get("wand"),
                         end=z.get("endbeschnitt"), greif=z.get("greiferrest"), flaeche=flaeche_wirksam(z))
               for pid, z in k.profile.items()}
    neue_profile = []
    for p in positionen:
        pid = p.get("profil_id")
        if not _leer(pid) and pid not in profile:
            d = opt.profil_aus_name(pid)
            if d is not None:
                profile[pid] = dict(form=d["form"], a=d["a"], b=d["b"], wand=d["wand"], end=None, greif=None,
                                    flaeche=d.get("flaeche_manuell") or flaeche_berechnet(dict(d, profil_id=pid)))
                neue_profile.append(dict(profil_id=str(pid), form=d["form"], a=d["a"], b=d["b"], wand=d["wand"],
                                         flaeche_manuell=d.get("flaeche_manuell"),
                                         bemerkung="automatisch aus Profil-ID angelegt"))
    m = maschine(kopf, k)
    if m is None:
        raise ValueError(f"Maschine '{kopf.get('maschine') or ''}' im Angebotskopf ist nicht in den Stammdaten.")
    me = dict(end=_n(m.get("endbeschnitt")), greif=_n(m.get("greiferrest")), kerf=_n(m.get("schnittverlust")),
              maxlen=m.get("max_stange"), abstand=_n(m.get("abstand")))
    std = kopf.get("stange") if isinstance(kopf.get("stange"), (int, float)) else None
    gruppen, fehler = {}, []
    for i, p in enumerate(positionen):
        r = ZEILE0 + i
        pid, wst, laenge, stk = p.get("profil_id"), p.get("werkstoff_id"), p.get("laenge"), p.get("stueck")
        laenge = laenge if isinstance(laenge, (int, float)) else None
        if ist_zukaufteil(p) or all(_leer(v) for v in (pid, wst, laenge, stk)):
            continue
        name = p.get("artikel") or f"Zeile {i + 1}"
        stk_n = int(stk) if isinstance(stk, (int, float)) and stk >= 1 and int(stk) == stk else 0

        def fehl(grund):
            fehler.append(dict(index=i, pos=p.get("pos"), artikel=name, anzahl=stk_n, grund=grund))
        if pid not in profile:
            fehl("Profil unbekannt"); continue
        if wst not in k.werkstoffe:
            fehl("Werkstoff unbekannt"); continue
        ob = oberflaeche_von(p)
        if ob and ob not in k.oberflaechen:
            fehl("Oberfläche unbekannt"); continue
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
        key = (pid, wst, ob, stange)
        g = gruppen.setdefault(key, opt.Gruppe(pid, wst, stange, end, greif, me["kerf"], me["abstand"], ob))
        a_ger = p.get("a_gerade") != "nein"
        b_ger = p.get("b_gerade") != "nein"
        u = opt.schnittlaenge(pr["form"], pr["a"], pr["b"], pr["wand"], pr["flaeche"])
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
    ist die Optimierung veraltet."""
    try:
        gruppen, fehler, neue = gruppen_bilden(kopf, positionen, k)
    except ValueError as e:
        return "fehler:" + str(e)
    # Oberfläche nur, wenn gesetzt: ältere Angebote ohne Oberfläche bleiben aktuell
    daten = [[(g.profil, g.werkstoff, g.stange, g.endbeschnitt, g.greiferrest, g.kerf, g.abstand,
               [tuple(t.__dict__.values()) for t in g.teile]) + ((g.oberflaeche,) if g.oberflaeche else ())
              for g in gruppen],
             [sorted(f.items()) for f in fehler], [sorted(n.items()) for n in neue]]
    return hashlib.sha1(json.dumps(daten, default=str, sort_keys=True).encode()).hexdigest()


def optimieren(kopf, positionen, k):
    """Optimiert das Angebot. Ergebnis (als JSON speicherbar):
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
            stangen.append(dict(nr=nr, profil=g.profil, werkstoff=g.werkstoff, oberflaeche=g.oberflaeche,
                                stange=g.stange, end=g.endbeschnitt,
                                greif=g.greiferrest, verlust=round(verlust, 2), trennungen=len(folge),
                                gemeinsam=n_gem, belegung=" | ".join(belegung), teile=teile))
        man = opt.manuell(g)
        auswertung.append(dict(profil=g.profil, werkstoff=g.werkstoff, oberflaeche=g.oberflaeche, stange=g.stange,
                               teile=len(g.teile),
                               stangen=len(folgen), manuell=len(man), untergrenze=opt.untergrenze(g),
                               ausnutzung_manuell=(sum(t.laenge for t in g.teile) / (len(man) * g.stange)
                                                   if man else 0),
                               gemeinsam=sum(opt.gemeinsame_schnitte(f) for f in folgen),
                               bewertung=opt.bewertung(g, len(folgen))))
    return dict(stangen=stangen, auswertung=auswertung, fehler=fehler, neue_profile=neue_profile,
                kennung=eingabe_kennung(kopf, positionen, k))


# ------------------------------------------------------------------ Schnittplan-Werte
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
    """Materialkosten einer Stange: Preis €/m im Angebot > 'Preise' > Tonnenpreis; zu den beiden letzten kommt der
    Aufpreis der Oberfläche je m."""
    ab = [p["preis_m"] for p in positionen if _n(p.get("preis_m")) and gruppe_von(p, kopf) == gruppe_der_stange(s)]
    if ab and max(ab) > 0:
        return max(ab) * s["stange"] / 1000
    aufpreis = _n((k.oberflaechen.get(s.get("oberflaeche") or "") or {}).get("aufpreis_m")) * s["stange"] / 1000
    z = preis_zeile(s["profil"], s["werkstoff"], k, tabellen)
    if z is not None:
        if z["basis"] == "€/kg":
            return _n(gewicht) * z["preis"] + aufpreis
        if z["basis"] == "€/m":
            return z["preis"] * s["stange"] / 1000 + aufpreis
        if z["basis"] == "€/Stange":
            return z["preis"] * s["stange"] / z["lieferlaenge"] + aufpreis
    tonne = _n((k.werkstoffe.get(s["werkstoff"]) or {}).get("tonnenpreis"))
    return _n(gewicht) * tonne / 1000 + aufpreis


# ------------------------------------------------------------------ Kalkulation
def gewinde_anzahl(text, gewinde):
    """{Gewinde: Anzahl je Teil} aus 'Gewinde geprüft' (z. B. '4xM6; 2xM8')."""
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
    """Erste Zusatzarbeit der Position, die weder einen gespeicherten Preisstand hat noch in den Stammdaten steht."""
    namen = {z.get("name") for z in katalog or ()}
    return next((z["name"] for z in zusatz_liste(p) if z["name"] not in namen and not isinstance(z.get("stand"), dict)),
                None)


def stundensaetze(tabellen):
    """{Stundensatz-ID: €/h} aus den Stammdaten Stundensätze."""
    return {z["satz_id"]: z.get("satz") for z in (tabellen.get("stundensaetze") or ()) if z.get("satz_id")}


def zusatz_preis(z, saetze=None):
    """Preis je Einheit einer Zusatzarbeit (Stammdatenzeile) und seine Bestandteile:
    Preis = Festpreis + Arbeit + Material inkl. Zuschlag + weiterer Zuschlag, mit
    Arbeit = Zeitaufwand [h] × Stundensatz (Stammdaten Stundensätze oder eigener Satz),
    Material inkl. = Material × (1 + Zuschlag %) bzw. Material + Zuschlag €,
    weiterer Zuschlag = % auf Arbeit, auf Material inkl. oder auf beides.
    Leere Felder zählen 0; ohne die Felder ab Schema 15 ist der Preis der Festpreis (wie bisher). Bei s/Stück ist
    'preis' die Zeit je Stück in s, alles andere zählt nicht.
    Ergebnis: dict(fest, zeit_s, satz, arbeit, material, zuschlag_material, material_inkl, weitere, preis)."""
    fest = _n(z.get("preis"))
    if z.get("art") == "s/Stück":
        return dict(fest=fest, zeit_s=0.0, satz=None, arbeit=0.0, material=0.0, zuschlag_material=0.0,
                    material_inkl=0.0, weitere=0.0, preis=fest)
    zeit_s = _n(z.get("zeit")) * ZEITEINHEITEN.get(z.get("zeit_einheit") or "min", 60)
    if not _leer(z.get("satz_id")):
        satz = (saetze or {}).get(z["satz_id"])
    else:
        satz = z.get("satz")
    arbeit = zeit_s / 3600 * _n(satz)
    material = _n(z.get("material"))
    zm = _n(z.get("zuschlag_material"))
    zuschlag_m = zm if z.get("zuschlag_material_art") == "€" else material * zm / 100
    material_inkl = material + zuschlag_m
    basis = {"Arbeit": arbeit, "Material": material_inkl}.get(z.get("zuschlag_weitere_basis"), arbeit + material_inkl)
    weitere = basis * _n(z.get("zuschlag_weitere")) / 100
    return dict(fest=fest, zeit_s=zeit_s, satz=satz, arbeit=arbeit, material=material, zuschlag_material=zuschlag_m,
                material_inkl=material_inkl, weitere=weitere, preis=fest + arbeit + material_inkl + weitere)


def zusatz_stand(z, saetze=None, datum=None):
    """Preisstand einer Zusatzarbeit für die Position (beim Hinzufügen gespeichert, damit spätere Änderungen der
    Stammdaten alte Angebote nicht verändern): Abrechnung, Preis je Einheit, Mindestbetrag, Fremdleistung,
    Angebotstext und Datum."""
    import datetime
    return dict(art=z.get("art"), preis=zusatz_preis(z, saetze)["preis"], mindest=z.get("mindest"),
                fremd=z.get("fremd"), angebotstext=z.get("angebotstext"),
                datum=datum or datetime.date.today().isoformat())


def oberflaeche(p, k):
    """Außenfläche eines Teils [m²] = Umfang × Länge (ohne Stirnflächen und Innenseite)."""
    pr = k.profile.get(p.get("profil_id"))
    if not pr or _leer(p.get("laenge")) or pr.get("a") is None:
        return None
    u = opt.umfang(pr.get("form"), pr["a"], pr.get("b"), pr.get("wand"), flaeche_wirksam(pr))
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
    saetze = stundensaetze(tabellen)
    out = []
    for e in zusatz_liste(p):
        stand = e.get("stand") if isinstance(e.get("stand"), dict) else None   # Preisstand beim Hinzufügen
        kz = stand or katalog.get(e["name"])
        if kz is None:
            continue
        art = kz.get("art")
        menge = e.get("menge") if isinstance(e.get("menge"), (int, float)) else zusatz_menge_auto(art, p, k)
        if isinstance(e.get("preis"), (int, float)):
            preis = e["preis"]
        else:
            preis = _n(kz.get("preis")) if stand else zusatz_preis(kz, saetze)["preis"]
        wert = _n(menge) * preis
        out.append(dict(name=e["name"], art=art, einheit=ZUSATZ_EINHEIT.get(art, ""), menge=menge, preis=preis,
                        betrag=0.0 if art in ("s/Stück", "€/Angebot") else wert,
                        pauschal=wert if art == "€/Angebot" else 0.0, zeit=wert if art == "s/Stück" else 0.0,
                        fremd=kz.get("fremd") == "ja", text=e.get("text"), mindest=_n(kz.get("mindest")),
                        angebotstext=kz.get("angebotstext") or e["name"]))
    return out


def zahl(w, stellen=2):
    """Kurze Zahl für Texte: 2,35 / 1 (ohne unnötige Nachkommastellen)."""
    if not isinstance(w, (int, float)):
        return "?"
    t = f"{w:.{stellen}f}"
    return (t.rstrip("0").rstrip(".") if "." in t else t).replace(".", ",")


KONTUR_TOL = 0.5     # mm, STEP-Teilwerte sind je auf 0,1 mm gerundet
KONTUR_GRENZEN = (10.0, 50.0)       # Vorgabe klein bis / mittel bis [mm], wenn die Maschine keine Werte hat
KLASSEN_FELDER = ("klein_n", "klein_mm", "mittel_n", "mittel_mm", "gross_n", "gross_mm")


def kontur_grenzen(m):
    """(klein bis, mittel bis) [mm] der Maschine; ohne gültige Werte die Vorgabe. Zweites Ergebnis: True = Vorgabe."""
    kl, mi = (m or {}).get("kontur_klein"), (m or {}).get("kontur_mittel")
    if isinstance(kl, (int, float)) and isinstance(mi, (int, float)) and 0 < kl < mi:
        return (float(kl), float(mi)), False
    return KONTUR_GRENZEN, True


def grenzen_text(grenzen):
    return "/".join(zahl(g, 1) for g in grenzen)


def konturen_text(liste, enden=()):
    """[(Hüllmaß, Schnittweg)] -> '10x31,4; 40x91,4' (Spalte Konturen der Position); enden = [('A' oder 'E',
    Hüllmaß, Schnittweg)] für Anfangs- und Endschnitt stehen vorn: 'A:40x149,7; E:40x149,7; 10x31,4'."""
    teile = [f"{a}:{zahl(round(g, 2))}x{zahl(round(lg, 1), 1)}" for a, g, lg in enden]
    return "; ".join(teile + [f"{zahl(round(g, 2))}x{zahl(round(lg, 1), 1)}" for g, lg in liste])


def konturen_lesen(text, mit_art=False):
    """'A:40x149,7; 10x31,4' -> [(40.0, 149.7), (10.0, 31.4)], mit_art: [('A', 40.0, 149.7), ('', 10.0, 31.4)]
    (A = Anfangsschnitt, E = Endschnitt, '' = Innenkontur); unlesbare Teile werden übergangen."""
    out = []
    for teil in str(text or "").replace("×", "x").split(";"):
        art, _, rest = teil.strip().rpartition(":")
        a, _, b = rest.partition("x")
        try:
            g, lg = float(a.replace(",", ".")), float(b.replace(",", "."))
        except ValueError:
            continue
        art = art.strip().upper()
        out.append((art if art in ("A", "E") else "", g, lg) if mit_art else (g, lg))
    return out


def grenzen_lesen(text):
    """'8/45' -> (8.0, 45.0) oder None."""
    try:
        a, b = (float(x.replace(",", ".")) for x in str(text or "").split("/"))
        return (a, b) if 0 < a < b else None
    except ValueError:
        return None


def ende_vorschub(p, vorschuebe, grenzen):
    """Vorschub für eingesparte gemeinsame Schnitte: Klasse des Endes aus der Konturliste (gerades Ende zuerst, nur
    gerade Enden werden geteilt); ohne Enden in der Konturliste Vorschub groß. vorschuebe = (groß, mittel, klein)."""
    h, i_, j = vorschuebe
    enden = {a: g for a, g, _ in konturen_lesen(p.get("konturen"), True) if a}
    if not enden:
        return h
    seite = "A" if p.get("a_gerade") == "ja" or "E" not in enden else "E" if p.get("b_gerade") == "ja" else "A"
    g = round(enden.get(seite, next(iter(enden.values()))), 2)
    grenzen = grenzen_lesen(p.get("kontur_grenzen")) or grenzen
    return j if g <= grenzen[0] else i_ if g <= grenzen[1] else h


def konturklassen(liste, grenzen):
    """Innenkonturen [(Hüllmaß, Schnittweg)] nach Hüllmaß einteilen: klein ≤ klein bis < mittel ≤ mittel bis < groß.
    Ergebnis: Felder klein_n, klein_mm, mittel_n, mittel_mm, gross_n, gross_mm (mm auf 0,1 gerundet)."""
    kl = [[0, 0.0], [0, 0.0], [0, 0.0]]
    for groesse, laenge in liste:
        g = round(groesse, 2)   # Ø10 genau auf der Grenze zählt als klein
        c = 0 if g <= grenzen[0] else 1 if g <= grenzen[1] else 2
        kl[c][0] += 1
        kl[c][1] += laenge
    out = {}
    for name, (n, lg) in zip(("klein", "mittel", "gross"), kl):
        out[f"{name}_n"], out[f"{name}_mm"] = n, round(lg, 1)
    return out


def konturklassen_neu(p, m):
    """Neue Einteilung einer Position, deren Konturliste mit anderen Grenzen eingeteilt wurde als die der Maschine:
    dict mit den Klassenfeldern und kontur_grenzen, sonst None (keine Konturliste oder Grenzen gleich)."""
    if _leer(p.get("konturen")) or ist_zukaufteil(p):
        return None
    grenzen = kontur_grenzen(m)[0]
    if p.get("kontur_grenzen") == grenzen_text(grenzen):
        return None
    return dict(konturklassen(konturen_lesen(p["konturen"]), grenzen), kontur_grenzen=grenzen_text(grenzen))


def gross_rest(p):
    """Schneidweg mit Vorschub groß [mm]: Schneidweg − Konturen klein und mittel, nie unter 0 (große Konturen,
    Anfangs-/Endschnitt ohne Klasse und von Hand ergänzter Schneidweg)."""
    return max(0.0, _n(p.get("schneidweg")) - _n(p.get("klein_mm")) - _n(p.get("mittel_mm")))


def konturen_pruefen(p):
    """Widerspruch zwischen Konturklassen und Schneidweg bzw. Innenkonturen (Text) oder None."""
    km = _n(p.get("klein_mm")) + _n(p.get("mittel_mm"))
    if km <= 0 and _n(p.get("gross_mm")) <= 0:
        return None
    if not _leer(p.get("schneidweg")) and km > _n(p["schneidweg"]) + KONTUR_TOL:
        return "Konturen klein + mittel länger als Schneidweg"
    summe = km + _n(p.get("gross_mm"))
    if not _leer(p.get("innen")) and summe > _n(p["innen"]) + _n(p.get("a_schnitt")) + _n(p.get("b_schnitt")) \
            + KONTUR_TOL:
        return "Konturklassen länger als Innenkonturen + Anfangs-/Endschnitt"
    return None


def schneidzeit(p, kopf, wand, tabellen, k=None):
    """Berechnete Schneidzeit je Teil [s] aus Schneidweg, Konturklassen, Gravur und Einstichen (ohne Einsparung
    gemeinsamer Schnitte und ohne Zusatzzeiten). Ergebnis: (Schneiddaten-Zeile, (Vorschub groß, mittel, klein,
    Gravur, Einstechzeit), Zeit oder None ohne Schneiddaten)."""
    sd = schneiddaten(kopf.get("maschine"), p.get("werkstoff_id"), _n(wand), tabellen,
                      kategorie(p.get("werkstoff_id"), k) if k else None)
    if sd and sd.get("wand_bis"):
        h = _n(sd.get("vorschub_gross"))
        i_ = _n(sd.get("vorschub_mittel")) or h
        j = _n(sd.get("vorschub_klein")) or i_
        kv = _n(sd.get("vorschub_gravur")) or h
        l = _n(sd.get("einstechzeit"))
    else:
        h = i_ = j = kv = l = None
    anteile = zeitanteile(p, (h, i_, j, kv, l))
    return sd, (h, i_, j, kv, l), sum(anteile.values()) if anteile else None


ZEITANTEILE = ("gross", "mittel", "klein", "gravur", "einstiche")


def zeitanteile(p, vorschuebe):
    """Schneidzeit je Teil [s] aufgeteilt: {gross (große Konturen und Rest des Schneidwegs), mittel, klein, gravur,
    einstiche}; None ohne Vorschub groß. vorschuebe = (groß, mittel, klein, Gravur, Einstechzeit) wie schneidzeit."""
    h, i_, j, kv, l = vorschuebe
    if not h:
        return None
    try:
        return dict(gross=60 * gross_rest(p) / h, mittel=60 * _n(p.get("mittel_mm")) / i_,
                    klein=60 * _n(p.get("klein_mm")) / j, gravur=60 * _n(p.get("gravur")) / kv,
                    einstiche=_n(p.get("einstiche")) * _n(l))
    except ZeroDivisionError:
        return None


# ------------------------------------------------------------------ Stundensätze und Zeitvorgaben
MASCHINE_ZEIT = ("stundensatz", "ruestzeit", "stangenwechsel")
SCHRITT_FELDER = ("schritt", "satz", "art", "parallel", "ruestzeit", "ruest_bezug", "zeit", "bezug")


def zeitbasis_aus(maschinen_id, k, tabellen):
    """Stundensätze und Zeitvorgaben aus den Stammdaten (für den Snapshot im Angebot):
    {maschine: {maschinen_id, stundensatz, ruestzeit, stangenwechsel}, saetze: {ID: €/h}, schritte: [Zeile]}."""
    m = k.maschinen.get(maschinen_id) or {}
    return dict(maschine=dict({n: m.get(n) for n in MASCHINE_ZEIT}, maschinen_id=maschinen_id if m else None),
                saetze={z["satz_id"]: z.get("satz") for z in (tabellen.get("stundensaetze") or []) if z.get("satz_id")},
                schritte=[{n: z.get(n) for n in SCHRITT_FELDER} for z in (tabellen.get("arbeitsschritte") or [])
                          if z.get("schritt")])


def zeitbasis(kopf, k, tabellen):
    """Gültige Stundensätze und Zeitvorgaben eines Angebots: der beim Anlegen gespeicherte Snapshot
    (kopf['zeitbasis']), sonst (ältere Angebote) die aktuellen Stammdaten. Gehört der Snapshot zu einer anderen
    Maschine als der gewählten, gelten deren aktuelle Werte. Ergebnis wie zeitbasis_aus plus gespeichert=True/False."""
    aktuell = zeitbasis_aus(kopf.get("maschine"), k, tabellen)
    zb = kopf.get("zeitbasis")
    if not isinstance(zb, dict):
        return dict(aktuell, gespeichert=False)
    out = dict(saetze=dict(zb.get("saetze") or {}), schritte=list(zb.get("schritte") or []), gespeichert=True,
               vorgabe_schritte=aktuell["schritte"])
    m = zb.get("maschine") or {}
    out["maschine"] = m if m.get("maschinen_id") == kopf.get("maschine") else aktuell["maschine"]
    return out


# ------------------------------------------------------------------ Preisbasis (festgeschriebene Preise)
PREIS_FELDER = ("profil_id", "werkstoff_id", "basis", "preis", "lieferlaenge", "gueltig_ab", "lieferant")
SCHNEID_FELDER = ("maschinen_id", "werkstoff_id", "kategorie", "gas", "wand_bis", "vorschub_gross", "vorschub_mittel",
                  "vorschub_klein", "einstechzeit", "vorschub_gravur")


def _preis_schl(z):
    return f"{z.get('profil_id')}|{z.get('werkstoff_id')}"


def preisbasis_aus(kopf, positionen, k, tabellen, datum=None):
    """Materialpreise und Schneiddaten, mit denen das Angebot rechnet (für den Snapshot im Angebot):
    {datum, maschine, preise: [Zeile je Profil + Werkstoff der Positionen], schneiddaten: [Zeilen der Maschine für
    die Werkstoffe und Kategorien der Positionen], tonnenpreise: {Werkstoff: €/t}, aufpreise: {Oberfläche: €/m}}.
    k und tabellen sind die gültigen Werte (bei festgeschriebenen Angeboten nach preisbasis_anwenden)."""
    import datetime
    werkstoffe = {p.get("werkstoff_id") for p in positionen if not _leer(p.get("werkstoff_id"))}
    kombis = {(p.get("profil_id"), p.get("werkstoff_id")) for p in positionen
              if not _leer(p.get("profil_id")) and not _leer(p.get("werkstoff_id"))}
    kats = {kategorie(w, k) for w in werkstoffe} - {None, ""}
    preise = []
    for pid, wid in sorted(kombis, key=str):
        z = preis_zeile(pid, wid, k, tabellen)
        # ohne Zeile: Merker (Preisbasis leer = Tonnenpreis), damit eine später angelegte Zeile nicht gilt
        preise.append({n: z.get(n) for n in PREIS_FELDER} if z is not None
                      else dict(profil_id=pid, werkstoff_id=wid, basis=None))
    m = kopf.get("maschine")
    sd = [{n: z.get(n) for n in SCHNEID_FELDER} for z in tabellen["schneiddaten"] if z.get("maschinen_id") == m
          and (z.get("werkstoff_id") in werkstoffe or _leer(z.get("werkstoff_id")) and z.get("kategorie") in kats)]
    ofl = {oberflaeche_von(p) for p in positionen} - {""}
    return dict(datum=datum or datetime.date.today().isoformat(), maschine=m, preise=preise, schneiddaten=sd,
                tonnenpreise={w: (k.werkstoffe.get(w) or {}).get("tonnenpreis") for w in sorted(werkstoffe, key=str)},
                aufpreise={o: (k.oberflaechen.get(o) or {}).get("aufpreis_m") for o in sorted(ofl)})


def preisbasis_anwenden(kopf, k, tabellen):
    """Gültige (k, tabellen) eines Angebots: Werte aus dem Snapshot kopf['preisbasis'] gehen den aktuellen
    Stammdaten vor; was der Snapshot nicht enthält (später hinzugefügte Profile, Werkstoffe, Oberflächen oder eine
    andere Maschine), kommt aus den aktuellen Stammdaten. Ohne Snapshot unverändert."""
    import dataclasses
    pb = kopf.get("preisbasis")
    if not isinstance(pb, dict):
        return k, tabellen
    # Unveränderte Zeilen bleiben die Zeilen der Stammdaten (gleiche Prüfsummen, z. B. für die Staffelpreise).
    tab = dict(tabellen)
    fest = {_preis_schl(z): z for z in pb.get("preise") or []}
    gleich = lambda a, b, felder: all(a.get(n) == b.get(n) for n in felder)
    tab["preise"] = [z if _preis_schl(z) not in fest or gleich(z, fest[_preis_schl(z)], PREIS_FELDER)
                     else fest[_preis_schl(z)] for z in tabellen["preise"]]
    vorhanden = {_preis_schl(z) for z in tabellen["preise"]}
    tab["preise"] += [z for s, z in fest.items() if s not in vorhanden and z.get("basis")]
    if pb.get("maschine") == kopf.get("maschine"):
        sd = pb.get("schneiddaten") or []
        werkstoffe = {z.get("werkstoff_id") for z in sd if not _leer(z.get("werkstoff_id"))} \
            | set(pb.get("tonnenpreise") or {})
        kats = {kategorie(w, k) for w in werkstoffe} - {None, ""}
        # Zeilen der Maschine für die Werkstoffe und Kategorien des Snapshots kommen aus dem Snapshot
        betroffen = lambda z: z.get("maschinen_id") == pb["maschine"] and (
            z.get("werkstoff_id") in werkstoffe or _leer(z.get("werkstoff_id")) and z.get("kategorie") in kats)
        aktuell = [z for z in tabellen["schneiddaten"] if betroffen(z)]
        projektion = lambda zeilen: sorted(json.dumps({n: z.get(n) for n in SCHNEID_FELDER}, sort_keys=True)
                                           for z in zeilen)
        if projektion(aktuell) != projektion(sd):
            tab["schneiddaten"] = sd + [z for z in tabellen["schneiddaten"] if not betroffen(z)]
    ws = {w: dict(z, tonnenpreis=pb["tonnenpreise"][w]) if w in (pb.get("tonnenpreise") or {}) else z
          for w, z in k.werkstoffe.items()}
    of = {o: dict(z, aufpreis_m=pb["aufpreise"][o]) if o in (pb.get("aufpreise") or {}) else z
          for o, z in k.oberflaechen.items()}
    return dataclasses.replace(k, werkstoffe=ws, oberflaechen=of), tab


def _vergleich(pb):
    """Vergleichbarer Inhalt eines Snapshots (ohne Datum), Schneiddaten unabhängig von der Reihenfolge."""
    sd = sorted((json.dumps(z, sort_keys=True) for z in pb.get("schneiddaten") or []))
    return dict(maschine=pb.get("maschine"), preise={_preis_schl(z): z for z in pb.get("preise") or []}, schneiddaten=sd,
                tonnenpreise=pb.get("tonnenpreise") or {}, aufpreise=pb.get("aufpreise") or {})


def preisbasis_gleich(a, b):
    """Gleiche festgeschriebene Werte (Datum zählt nicht)."""
    return _vergleich(a) == _vergleich(b)


def preisbasis_abweichung(kopf, k, tabellen):
    """Was sich in den aktuellen Stammdaten gegenüber den festgeschriebenen Preisen des Angebots geändert hat:
    Liste lesbarer Texte (leer = nichts geändert oder nichts festgeschrieben). k, tabellen: aktuelle Stammdaten."""
    pb = kopf.get("preisbasis")
    if not isinstance(pb, dict):
        return []
    alt = _vergleich(pb)
    # dieselben Profile, Werkstoffe und Oberflächen wie im Snapshot, Werte aus den aktuellen Stammdaten
    umfang = ([dict(profil_id=z.get("profil_id"), werkstoff_id=z.get("werkstoff_id")) for z in pb.get("preise") or []]
              + [dict(werkstoff_id=w) for w in pb.get("tonnenpreise") or {}]
              + [dict(oberflaeche=o) for o in pb.get("aufpreise") or {}])
    neu = _vergleich(preisbasis_aus(dict(kopf, maschine=pb.get("maschine")), umfang, k, tabellen))
    def text(z):
        return f"{zahl(z.get('preis'))} {z['basis']}" if z and z.get("basis") else "Tonnenpreis"

    out = []
    for s, z in alt["preise"].items():
        n = neu["preise"].get(s) or {}
        if (n.get("basis"), n.get("preis"), n.get("lieferlaenge")) != \
                (z.get("basis"), z.get("preis"), z.get("lieferlaenge")):
            out.append(f"Preis {s.replace('|', ' / ')}: {text(z)} → {text(n)}")
    for w, t in alt["tonnenpreise"].items():
        if neu["tonnenpreise"].get(w) != t:
            out.append(f"Tonnenpreis {w}: {zahl(t)} → {zahl(neu['tonnenpreise'].get(w))} €/t")
    for o, a in alt["aufpreise"].items():
        if neu["aufpreise"].get(o) != a:
            out.append(f"Aufpreis {o}: {zahl(a)} → {zahl(neu['aufpreise'].get(o))} €/m")
    if alt["schneiddaten"] != neu["schneiddaten"]:
        out.append(f"Schneiddaten der Maschine {pb.get('maschine')} geändert")
    return out


def _schritt_satz(zb, schritt):
    """(Stundensatz-ID, €/h) eines Arbeitsschritts; fehlt er, wie bisher der Maschinenstundensatz."""
    sid = (schritt or {}).get("satz") or SATZ_MASCHINE
    if sid == SATZ_MASCHINE:
        return sid, _n(zb["maschine"].get("stundensatz"))
    return sid, _n(zb["saetze"].get(sid))


def zeit_text(minuten):
    """Zeit für die Anzeige: '45 s', '12,5 min', '2 h 05 min'."""
    if not isinstance(minuten, (int, float)):
        return ""
    if minuten < 1:
        return f"{zahl(minuten * 60, 0)} s"
    if minuten < 60:
        return f"{zahl(minuten, 1)} min"
    h, m = divmod(round(minuten), 60)
    return f"{h} h {m:02d} min"


def einstellungen_angebot(kopf, einst):
    """Einstellungen mit den Kalkulationswerten des Angebots (angebot.KALKULATION); leere Werte im Angebot
    lassen den Wert der Einstellungen stehen. Prozentwerte des Angebots werden zu Anteilen."""
    from .angebot import KALK_PROZENT, KALKULATION
    out = dict(einst)
    for f in KALKULATION:
        w = (kopf or {}).get(f.name)
        if isinstance(w, (int, float)) and not isinstance(w, bool):
            out[f.name] = w / 100 if f.name in KALK_PROZENT else w
    return out


def kalkulation(kopf, positionen, ergebnis, k, tabellen, einstellungen):
    """Kalkulation je Position und Summen. Ergebnis: (zeilen, summen); zeilen[i] ist None für
    Positionen ohne Profil.

    Zusätzlich zu Material, Laserzeit, Gewinde, Rüsten und Zusatzarbeiten (fehlen die Einstellungen, ist alles 0):
    - Rüstzeit je Abmessung (Einstellung, min) für jede Abmessung (Profil-ID) mit Stückzahl, mit dem
      Maschinenstundensatz bewertet, umgelegt auf die Teile dieser Abmessung; zählt zu Rüsten und damit zu
      den Herstellkosten (mit Zuschlag Fertigung und Gewinn).
    - Pauschale je Abmessung (€), umgelegt auf die Teile dieser Abmessung, Angebotsaufschlag (€), umgelegt auf
      alle Teile, und Frachtkosten (fracht_angebot.wirksam: 0 bei 'keine Fracht' und 'im Artikelpreis enthalten'),
      je Stück oder nach Gewicht verteilt (fracht_angebot.anteile); gehen ohne Zuschläge in den Verkaufspreis ein.
    - Programmierkosten je Teil (Einstellung, €) für jede Position mit Stückzahl, umgelegt auf deren
      Stückzahl, ohne Zuschläge in den Verkaufspreis.
    - Gewinde mit festem Preis (Stammdaten Gewinde) zählen mit dem Preis statt mit der Zeit.
    - Schneidzeit manuell (Position) ersetzt die berechnete Laserzeit netto je Teil.
    - Zusatzarbeiten je Position: Beträge je Teil (€/kg, €/m², €/m, €/Stück) mit Zuschlag Fremdleistung bzw.
      Fertigung; liegt die Summe einer Zusatzarbeit im Angebot unter ihrem Mindestbetrag, wird sie anteilig
      angehoben. €/Angebot zählt einmal je Angebot (höchster Betrag der Positionen, mindestens der Mindestbetrag),
      umgelegt auf deren Teile. Zeiten (s/Stück) kommen zur Laserzeit, auch zur manuellen. Preis je Einheit aus
      dem Preisstand der Position, sonst aus den Stammdaten (zusatz_preis).
    - Zukaufteile je Position (positionen.zukauf mit Preisstand): Verbrauch = Menge je Teil × Stückzahl, gleiche
      Artikel mit gleichem Preisstand werden im Angebot zu einer Bestellung zusammengefasst (Staffel, Mindestmenge,
      VPE und Bezugskosten einmal; zukauf.rechnen). Einstandspreis + Aufschlag nach der Regel des Artikels gehen
      je Teil ohne Zuschläge und ohne Gewinn in den Verkaufspreis ein (der Aufschlag ersetzt beides).
    - Skonto aus dem Angebotskopf (%) wird eingerechnet: Verkaufspreis = Preis ohne Skonto / (1 − Skonto), so bleibt
      nach Abzug des Skontos der Preis ohne Skonto."""
    zb = zeitbasis(kopf, k, tabellen)
    satz_h = _n(zb["maschine"].get("stundensatz"))
    schritt = {z.get("schritt"): z for z in zb["schritte"]}
    satz = {n: _schritt_satz(zb, schritt.get(n)) for n in SCHRITTE_FEST}     # vom Programm gerechnete Schritte
    s_laser, s_gew, s_rm, s_ra, s_sw = (satz[n][1] for n in ("Laser schneiden", "Gewinde", "Rüsten Maschine",
                                                             "Rüsten je Abmessung", "Stangenwechsel"))
    stangen = ergebnis["stangen"] if ergebnis else []
    sw = stangen_werte(ergebnis, kopf, positionen, k, tabellen) if ergebnis else []
    zm, zf, gew = (_n(einstellungen.get(n)) for n in ("zuschlag_material", "zuschlag_fertigung", "gewinn"))
    ruest, wechsel = _n(zb["maschine"].get("ruestzeit")), _n(zb["maschine"].get("stangenwechsel"))
    f7 = ruest / 60 * s_rm + wechsel * len(stangen) / 3600 * s_sw
    aktiv = [i for i, p in enumerate(positionen) if position_aktiv(p)]
    # Zukaufteil-Positionen (z. B. Bleche) tragen nur ihre Zukaufteile und die Fracht; Rüsten, Pauschalen,
    # Programmierung, Angebotsaufschlag und Arbeitsschritte verteilen sich auf die Rohrlaserteile
    laser = [i for i in aktiv if not ist_zukaufteil(positionen[i])]
    zk_pos = [i for i in aktiv if ist_zukaufteil(positionen[i])]
    f8 = sum(_n(positionen[i].get("stueck")) for i in laser)
    teile_abm = {}
    for i in laser:
        if _n(positionen[i].get("stueck")) > 0:
            pid = positionen[i]["profil_id"]
            teile_abm[pid] = teile_abm.get(pid, 0) + _n(positionen[i]["stueck"])
    ruest_abm_min = _n(einstellungen.get("ruesten_abmessung"))
    ruest_abm = ruest_abm_min / 60 * s_ra              # € je Abmessung
    pausch_abm = _n(einstellungen.get("pauschale_abmessung"))
    prog = _n(einstellungen.get("programmierung_teil"))   # € je Teil (Position mit Stückzahl), einmal je Angebot
    zfl = _n(einstellungen.get("zuschlag_fremdleistung"))
    zus = {i: zusatz_werte(positionen[i], k, tabellen) if i in laser else [] for i in aktiv}
    zus_summe, zus_teile, zus_pauschal, zus_mindest = {}, {}, {}, {}
    for i in aktiv:
        c = _n(positionen[i].get("stueck"))
        for e in zus[i]:
            zus_summe[e["name"]] = zus_summe.get(e["name"], 0.0) + e["betrag"] * c
            zus_teile[e["name"]] = zus_teile.get(e["name"], 0) + c
            # ein Mindestbetrag je Zusatzarbeit und Angebot, auch wenn Positionen verschiedene Preisstände haben
            zus_mindest[e["name"]] = max(zus_mindest.get(e["name"], 0.0), e["mindest"])
            if e["art"] == "€/Angebot" and c:          # einmal je Angebot: der höchste Betrag gilt
                zus_pauschal[e["name"]] = max(zus_pauschal.get(e["name"], 0.0), e["pauschal"])
    for i in aktiv:                   # Mindestbetrag je Angebot: anteilig anheben
        for e in zus[i]:
            e["mindest"] = zus_mindest[e["name"]]
            if e["art"] == "€/Angebot":               # pauschal je Angebot: auf die Teile umgelegt
                n = zus_teile[e["name"]]
                e["teil"] = max(zus_pauschal.get(e["name"], 0.0), e["mindest"]) / n if n else 0.0
            elif e["art"] == "s/Stück" or e["mindest"] <= 0 or not zus_teile[e["name"]]:
                e["teil"] = e["betrag"]
            elif zus_summe[e["name"]] <= 0:
                e["teil"] = e["mindest"] / zus_teile[e["name"]]
            else:
                e["teil"] = e["betrag"] * max(1.0, e["mindest"] / zus_summe[e["name"]])
    skonto = min(max(_n(kopf.get("skonto")), 0), 50) / 100
    aufschlag = _n(einstellungen.get("angebotsaufschlag")) if f8 else 0
    werte = [position_werte(p, kopf, k, tabellen) if i in aktiv else None for i, p in enumerate(positionen)]
    fracht = fracht_angebot.wirksam(kopf) if f8 or any(_n(positionen[i].get("stueck")) for i in zk_pos) else 0
    fracht_je, fracht_hinweis, fracht_umlage = fracht_angebot.anteile(positionen, werte, fracht,
                                                                      fracht_angebot.umlage(kopf))
    weitere = weitere_schritte(zb, f8, len(stangen), teile_abm,
                               sum(1 for i in laser if _n(positionen[i].get("stueck")) > 0))
    zk_gruppen, zk_je = zukauf.rechnen([((i, n), e, _n(positionen[i].get("stueck"))) for i in aktiv
                                        for n, e in enumerate(zukauf.eintraege(positionen[i]))])
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
        w = werte[i]
        c = _n(p.get("stueck"))
        if i in zk_pos:
            zeilen[i] = _zukaufteil_zeile(p, c, [zk_je[(i, n)] for n in range(len(zukauf.eintraege(p)))],
                                          fracht_je[i] if c else 0, skonto)
            continue
        gr = gruppe_von(p, kopf)
        d = sum(x["kosten"] for s, x in zip(stangen, sw) if gruppe_der_stange(s) == gr)
        gesamt = sum(_n(x.get("laenge")) * _n(x.get("stueck")) for x in positionen
                     if gruppe_von(x, kopf) == gr and not _leer(x.get("laenge")) and not _leer(x.get("stueck")))
        e = _n(w["laenge_gesamt"]) / gesamt if gesamt else 0
        f = d * e / c if c else 0
        sd, (h, i_, j, kv, l), mz = schneidzeit(p, kopf, w["wand"], tabellen, k)
        z = dict(pos=p.get("pos"), artikel=p.get("artikel"), stueck=c, material_gruppe=d, anteil=e,
                 material_teil=f, wand_stufe=sd["wand_bis"] if sd else None, gas=sd.get("gas") if sd else None)
        z.update(vorschub_gross=h, vorschub_mittel=i_, vorschub_klein=j, vorschub_gravur=kv, einstechzeit=l)
        anteile = zeitanteile(p, (h, i_, j, kv, l)) or {}
        z.update({f"zeit_{n}": anteile.get(n) for n in ZEITANTEILE})
        z.update(mm_gross=gross_rest(p), mm_mittel=_n(p.get("mittel_mm")), mm_klein=_n(p.get("klein_mm")),
                 mm_gravur=_n(p.get("gravur")), einstiche_teil=_n(p.get("einstiche")))
        ein = eingespart.get(schluessel(p, i), [0, 0.0, 0])
        if h is None or c == 0 or not h:
            nz = 0
        else:
            nz = (60 * ein[1] / ende_vorschub(p, (h, i_, j), kontur_grenzen(maschine(kopf, k))[0]) + ein[2] * l) / c
        manuell = not _leer(p.get("zeit_manuell"))
        zeit_extra = sum(e["zeit"] for e in zus[i])
        if manuell:
            oz = _n(p["zeit_manuell"]) + zeit_extra
        else:
            oz = None if mz is None and not zeit_extra else max(0, _n(mz) - nz) + zeit_extra
        pz = gewindezeit(p.get("gewinde"), tabellen["gewinde"])
        gp = gewinde_preis(p.get("gewinde"), tabellen["gewinde"])
        qz = _n(oz) / 3600 * s_laser + pz / 3600 * s_gew + gp
        ze = sum(e["teil"] for e in zus[i] if not e["fremd"])
        zfr = sum(e["teil"] for e in zus[i] if e["fremd"])
        n_abm = teile_abm.get(p.get("profil_id"), 0)
        rz = (f7 / f8 if f8 else 0) + (ruest_abm / n_abm if n_abm and c else 0)
        az = sum(e["teil"](p, c) for e in weitere) if c else 0      # weitere Arbeitsschritte je Teil
        fr = fracht_je[i] if c else 0
        uz = (pausch_abm / n_abm if n_abm and c else 0) + (aufschlag / f8 if f8 and c else 0) + fr \
            + (prog / c if c else 0)
        zk = [zk_je[(i, n)] for n in range(len(zukauf.eintraege(p)))]
        zk_einst = float(sum(x["einstand"] for x in zk)) / c if c else 0
        zk_auf = float(sum(x["aufschlag"] for x in zk)) / c if c else 0
        s_ = f * (1 + zm) + (qz + rz + az + ze) * (1 + zf) + zfr * (1 + zfl)
        ohne = s_ * (1 + gew) + uz + zk_einst + zk_auf
        t_ = ohne / (1 - skonto)
        nicht = c - ein[0] if (stangen and not _leer(p.get("stueck"))) else None
        if _n(nicht) > 0:
            hinweis = "nicht vollständig eingeplant"
        elif d == 0:
            hinweis = "kein Schnittplan oder Preis"
        elif h is None and not manuell:
            hinweis = "keine Schneiddaten"
        elif not manuell and konturen_pruefen(p):
            hinweis = konturen_pruefen(p)
        elif zusatz_unbekannt(p, tabellen.get("zusatzarbeiten")):
            hinweis = "Zusatzarbeit unbekannt"
        elif not _leer(p.get("gewinde_vorschlag")) and _leer(p.get("gewinde")):
            hinweis = "Gewinde ungeprüft"
        elif any(x["fehler"] for x in zk):
            hinweis = "Zukaufteil: " + next(x["fehler"] for x in zk if x["fehler"])
        else:
            hinweis = ""
        z.update(zeit_manuell="ja" if manuell else "", zeit_extra=zeit_extra, gewinde_preis=gp,
                 zusatz_eigen_teil=ze, zusatz_fremd_teil=zfr, zusatz_teil=ze + zfr, zusatz_position=(ze + zfr) * c, zusatzarbeiten=zus[i],
                 zusatz_text="; ".join(f"{e['name']} {zahl(e['menge'])} {e['einheit']}" for e in zus[i]))
        z.update(laser_schneiden_teil=_n(oz) / 3600 * s_laser, gewinde_teil=pz / 3600 * s_gew + gp,
                 gewinde_zeit_teil=pz / 3600 * s_gew, arbeit_teil=az,
                 zuschlag_material_teil=f * zm, zuschlag_fertigung_teil=(qz + rz + az + ze) * zf,
                 zuschlag_fremdleistung_teil=zfr * zfl, gewinn_teil=s_ * gew, skonto_teil=t_ - ohne)
        z.update(laser_brutto=mz, einsparung=nz, laser_netto=oz, gewindezeit=pz, laser_teil=qz, ruesten_teil=rz,
                 zukauf_einstand_teil=zk_einst, zukauf_aufschlag_teil=zk_auf, zukauf_teil=zk_einst + zk_auf,
                 zukauf_fehlt=sum(1 for x in zk if x["fehler"]),
                 herstell_teil=s_, pauschalen_teil=uz, fracht_teil=fr, preis_teil=t_, preis_position=t_ * c, herstell_position=s_ * c,
                 material_position=f * c, laser_position=qz * c, hinweis=hinweis, eingeplant=ein[0],
                 nicht_eingeplant=nicht)
        zeilen[i] = z
    n_abm = len(teile_abm)

    def _summe(n):
        return sum(z[n] * z["stueck"] for z in zeilen if z)

    summen = dict(ruestzeit=ruest, stangenwechsel=wechsel, stangen=len(stangen), teile=f8,
                  abmessungen=n_abm, ruestzeit_abmessung=ruest_abm_min, ruesten=f7 + ruest_abm * n_abm,
                  pauschalen=pausch_abm * n_abm, angebotsaufschlag=aufschlag, fracht=fracht,
                  fracht_modus=fracht_angebot.modus(kopf), fracht_umlage=fracht_umlage, fracht_hinweis=fracht_hinweis,
                  positionen=sum(1 for i in laser if _n(positionen[i].get("stueck")) > 0),
                  programmierung=prog * sum(1 for i in laser if _n(positionen[i].get("stueck")) > 0),
                  zukaufteile=sum(_n(positionen[i].get("stueck")) for i in zk_pos),
                  material=sum(z["material_position"] for z in zeilen if z),
                  laser=sum(z["laser_position"] for z in zeilen if z),
                  zusatz=sum(z["zusatz_position"] for z in zeilen if z),
                  herstell=sum(z["herstell_position"] for z in zeilen if z),
                  verkauf=sum(z["preis_position"] for z in zeilen if z))
    # Einzelne Kostenarten (Material + Laser + Gewinde + Rüsten + Stangenwechsel + Zusatzarbeiten + Zuschläge
    # = Herstellkosten; Herstellkosten + Gewinn + Pauschalen + Programmierung + Aufschlag + Fracht + Zukaufteile
    # + Skonto = Verkaufspreis)
    summen.update(laser_schneiden=_summe("laser_schneiden_teil"), gewinde=_summe("gewinde_teil"),
                  ruesten_maschine=ruest / 60 * s_rm, ruesten_abmessungen=ruest_abm * n_abm,
                  stangenwechsel_kosten=wechsel * len(stangen) / 3600 * s_sw,
                  zuschlag_material=_summe("zuschlag_material_teil"),
                  zuschlag_fertigung=_summe("zuschlag_fertigung_teil"),
                  zuschlag_fremdleistung=_summe("zuschlag_fremdleistung_teil"), gewinn=_summe("gewinn_teil"),
                  skonto=_summe("skonto_teil"), skonto_satz=100 * skonto, arbeitsschritte=_summe("arbeit_teil"),
                  zusatz_eigen=_summe("zusatz_eigen_teil"), zusatz_fremd=_summe("zusatz_fremd_teil"),
                  zukauf_einstand=_summe("zukauf_einstand_teil"), zukauf_aufschlag=_summe("zukauf_aufschlag_teil"),
                  zukauf_fehlt=sum(z["zukauf_fehlt"] for z in zeilen if z), zukauf=zk_gruppen)
    summen.update(satz_laser=s_laser, satz_maschine=satz_h, zeitbasis_gespeichert=zb["gespeichert"])
    summen["zeiten"] = arbeitszeiten(zeilen, positionen, summen, zb, satz, weitere, len(stangen))
    return zeilen, summen


def _zukaufteil_zeile(p, c, zk, fr, skonto):
    """Kalkulationszeile einer Zukaufteil-Position: alle Fertigungswerte 0, Preis je Teil = Einstand + Aufschlag der
    Zukaufteile + Frachtanteil, mit Skonto. Fehlt der Einkaufspreis, rechnet sie ohne ihn und meldet es."""
    zk_einst = float(sum(x["einstand"] for x in zk)) / c if c else 0
    zk_auf = float(sum(x["aufschlag"] for x in zk)) / c if c else 0
    ohne = fr + zk_einst + zk_auf
    t_ = ohne / (1 - skonto)
    if not zk:
        hinweis = "Zukaufteil: kein Zukaufartikel"
    elif any(x["fehler"] for x in zk):
        hinweis = "Zukaufteil: " + next(x["fehler"] for x in zk if x["fehler"])
    else:
        hinweis = ""
    null = dict.fromkeys(("material_gruppe", "anteil", "material_teil", "zeit_extra", "gewinde_preis",
                          "zusatz_eigen_teil", "zusatz_fremd_teil", "zusatz_teil", "zusatz_position",
                          "laser_schneiden_teil", "gewinde_teil", "gewinde_zeit_teil", "arbeit_teil",
                          "zuschlag_material_teil", "zuschlag_fertigung_teil", "zuschlag_fremdleistung_teil",
                          "gewinn_teil", "einsparung", "gewindezeit", "laser_teil", "ruesten_teil", "herstell_teil",
                          "herstell_position", "material_position", "laser_position"), 0.0)
    z = dict(null, pos=p.get("pos"), artikel=p.get("artikel"), stueck=c, wand_stufe=None, gas=None,
             vorschub_gross=None, vorschub_mittel=None, vorschub_klein=None, vorschub_gravur=None, einstechzeit=None,
             **{f"zeit_{n}": None for n in ZEITANTEILE}, mm_gross=None, mm_mittel=None, mm_klein=None,
             mm_gravur=None, einstiche_teil=None, zeit_manuell="", zusatzarbeiten=[], zusatz_text="", skonto_teil=t_ - ohne, laser_brutto=None,
             laser_netto=None, zukauf_einstand_teil=zk_einst, zukauf_aufschlag_teil=zk_auf,
             zukauf_teil=zk_einst + zk_auf, zukauf_fehlt=sum(1 for x in zk if x["fehler"]) + (0 if zk else 1),
             pauschalen_teil=fr, fracht_teil=fr, preis_teil=t_, preis_position=t_ * c, hinweis=hinweis,
             eingeplant=None, nicht_eingeplant=None, zukaufteil=True)
    return z


def weitere_schritte(zb, teile, n_stangen, teile_abm, n_positionen):
    """Arbeitsschritte mit Zeitvorgabe (nicht SCHRITTE_FEST) und Zeit > 0: je Schritt Mengen, Zeiten, Kosten und
    die Umlage je Teil teil(p, Stückzahl). Rüstzeit je Angebot und Zeit je Stange werden gleichmäßig auf alle
    Teile verteilt, Rüstzeit je Abmessung auf die Teile dieser Abmessung, Zeit je Position auf deren Teile."""
    out = []
    for z in zb["schritte"]:
        name = z.get("schritt")
        ruest_min, zeit_s = _n(z.get("ruestzeit")), _n(z.get("zeit"))
        if name in SCHRITTE_FEST:
            continue
        sid, satz = _schritt_satz(zb, z)
        bezug = z.get("bezug") or "Teil"
        menge = {"Teil": teile, "Stange": n_stangen, "Position": n_positionen}.get(bezug, teile)
        rb = z.get("ruest_bezug") or "Angebot"
        n_ruest = (len(teile_abm) if rb == "Abmessung" else 1) if teile else 0

        def teil(p, c, ruest_min=ruest_min, zeit_s=zeit_s, satz=satz, bezug=bezug, menge=menge, rb=rb):
            """Kosten dieses Schritts je Teil einer Position mit c Stück."""
            n_abm = teile_abm.get(p.get("profil_id"), 0)
            if not (ruest_min or zeit_s) or not teile:
                return 0
            r = (ruest_min / 60 * satz / n_abm if n_abm else 0) if rb == "Abmessung" else ruest_min / 60 * satz / teile
            if bezug == "Position":
                return r + zeit_s / 3600 * satz / c
            if bezug == "Stange":
                return r + zeit_s * menge / 3600 * satz / teile
            return r + zeit_s / 3600 * satz
        out.append(dict(schritt=name, satz_id=sid, satz=satz, art=z.get("art") or "Personal",
                        parallel=z.get("parallel") == "ja", ruest_min=ruest_min * n_ruest, ruest_einzeln=ruest_min,
                        ruest_bezug=rb, n_ruest=n_ruest, zeit_s=zeit_s, bezug=bezug, menge=menge, teil=teil))
    return out


def arbeitszeiten(zeilen, positionen, summen, zb, satz, weitere, n_stangen):
    """Zeiten und Kosten je Arbeitsschritt aus derselben Rechnung wie die Kalkulation (nichts wird doppelt
    gerechnet): [{schritt, art, parallel, menge, einheit, ruest_min, zeit_einheit_s, gesamt_min, satz_id, satz,
    kosten, formel, quelle, fest}]. gesamt_min None = Betrag ohne Zeit (Festpreis, Pauschale)."""
    teile = summen["teile"]
    zl = [z for z in zeilen if z]
    art = {z.get("schritt"): z for z in zb["schritte"]}

    def zeile(name, menge, einheit, ruest_min, zeit_s, gesamt_min, kosten, formel, quelle, art_=None, sid=None,
              satz_=None, parallel=None, fest=True):
        a = art.get(name) or {}
        return dict(schritt=name, art=art_ or a.get("art") or "Maschine",
                    parallel=parallel if parallel is not None else a.get("parallel") == "ja", menge=menge,
                    einheit=einheit, ruest_min=ruest_min, zeit_einheit_s=zeit_s, gesamt_min=gesamt_min, satz_id=sid,
                    satz=satz_, kosten=kosten, formel=formel, quelle=quelle, fest=fest)
    laser_s = sum(_n(z["laser_netto"]) * z["stueck"] for z in zl)
    manuell = sum(1 for z in zl if z["zeit_manuell"] == "ja")
    step = sum(1 for p in positionen if not _leer(p.get("a_schnitt")) or not _leer(p.get("innen")))
    quelle = "Schneiddaten × Schneidweg" + (f" (STEP bei {step} Pos.)" if step else "")         + (f"; von Hand bei {manuell} Pos." if manuell else "")
    sid, sl = satz["Laser schneiden"]
    out = [zeile("Laser schneiden", teile, "Teile", None, laser_s / teile if teile else None, laser_s / 60,
                 summen["laser_schneiden"], f"{zahl(laser_s / 60, 2)} min / 60 × {zahl(sl, 2)} €/h", quelle,
                 sid=sid, satz_=sl)]
    gew_s = sum(_n(z["gewindezeit"]) * z["stueck"] for z in zl)
    gew_zeit = sum(z["gewinde_zeit_teil"] * z["stueck"] for z in zl)
    sid, sg = satz["Gewinde"]
    out.append(zeile("Gewinde", teile, "Teile", None, gew_s / teile if teile else None, gew_s / 60, gew_zeit,
                     f"{zahl(gew_s / 60, 2)} min / 60 × {zahl(sg, 2)} €/h", "Stammdaten Gewinde (Zeit je Gewinde)",
                     sid=sid, satz_=sg))
    gew_fest = summen["gewinde"] - gew_zeit
    out.append(zeile("Gewinde Festpreis", teile, "Teile", None, None, None, gew_fest, "Anzahl × Preis je Gewinde",
                     "Stammdaten Gewinde (Festpreis)", art_="Fremd/Preis"))
    sid, sr = satz["Rüsten Maschine"]
    rm = summen["ruestzeit"]
    out.append(zeile("Rüsten Maschine", 1, "Angebot", rm, None, rm, summen["ruesten_maschine"],
                     f"{zahl(rm, 1)} min / 60 × {zahl(sr, 2)} €/h",
                     "Maschine (Snapshot)" if zb["gespeichert"] else "Maschine (Stammdaten)", sid=sid, satz_=sr))
    sid, sa = satz["Rüsten je Abmessung"]
    ra = summen["abmessungen"] * summen["ruestzeit_abmessung"]
    out.append(zeile("Rüsten je Abmessung", summen["abmessungen"], "Abmessungen", ra, None, ra,
                     summen["ruesten_abmessungen"],
                     f"{summen['abmessungen']} × {zahl(summen['ruestzeit_abmessung'], 1)} min / 60 × {zahl(sa, 2)} €/h",
                     "Angebot (Vorgabe Einstellungen)", sid=sid, satz_=sa))
    sid, sw = satz["Stangenwechsel"]
    wm = n_stangen * summen["stangenwechsel"] / 60
    out.append(zeile("Stangenwechsel", n_stangen, "Stangen", None, summen["stangenwechsel"], wm,
                     summen["stangenwechsel_kosten"],
                     f"{n_stangen} × {zahl(summen['stangenwechsel'], 0)} s / 3600 × {zahl(sw, 2)} €/h",
                     "Maschine (Snapshot)" if zb["gespeichert"] else "Maschine (Stammdaten)", sid=sid, satz_=sw))
    vorgabe = {z.get("schritt"): z for z in (zb.get("vorgabe_schritte") or [])}
    for e in weitere:
        ges = e["ruest_min"] + e["zeit_s"] / 60 * e["menge"]
        v = vorgabe.get(e["schritt"])
        hand = v is not None and (_n(v.get("ruestzeit")), _n(v.get("zeit"))) != (e["ruest_einzeln"], e["zeit_s"])
        out.append(zeile(e["schritt"], e["menge"], {"Teil": "Teile", "Stange": "Stangen",
                                                    "Position": "Positionen"}[e["bezug"]],
                         e["ruest_min"], e["zeit_s"], ges, ges / 60 * e["satz"],
                         (f"{e['n_ruest']} × {zahl(e['ruest_einzeln'], 1)} min + " if e["ruest_min"] else "")
                         + f"{zahl(e['menge'], 0)} × {zahl(e['zeit_s'], 1)} s = {zahl(ges, 2)} min / 60 × "
                           f"{zahl(e['satz'], 2)} €/h",
                         "von Hand (Angebot)" if hand else "Vorgabe (Arbeitsschritte)", art_=e["art"],
                         sid=e["satz_id"], satz_=e["satz"], parallel=e["parallel"], fest=False))
        out[-1].update(ruest_einzeln=e["ruest_einzeln"], n_ruest=e["n_ruest"], ruest_bezug=e["ruest_bezug"])
    out.append(zeile("Programmierung", summen["positionen"], "Positionen", None, None, None, summen["programmierung"],
        "Programmierkosten je Teil × Positionen (ohne Zuschläge)", "Vorgabe € je Position", art_="Pauschale"))
    out.append(zeile("Zusatzarbeiten (€)", teile, "Teile", None, None, None, summen["zusatz"],
                     "Menge × Preis je Einheit, ggf. Mindestbetrag", "Stammdaten Zusatzarbeiten", art_="Fremd/Preis"))
    return out


def schritt_sichtbar(z):
    """Arbeitsschritt zeigen (Programm, PDF, CSV): Laser schneiden immer, sonst nur mit Zeit oder Kosten."""
    return z["schritt"] == "Laser schneiden" or abs(z["gesamt_min"] or 0) >= 0.005 or abs(z["kosten"] or 0) >= 0.005


def schritt_texte(z):
    """Anzeigetexte eines Arbeitsschritts: Menge, Rüstzeit, Zeit je Einheit, Gesamtzeit, Stundensatz."""
    menge = f"{zahl(z['menge'], 0)} {z['einheit']}" if z["menge"] is not None else ""
    if not z["ruest_min"]:
        ruest = "–" if z["fest"] else "0 min"
    elif z.get("n_ruest", 1) > 1:
        ruest = f"{z['n_ruest']} × {zeit_text(z['ruest_einzeln'])}"
    else:
        ruest = zeit_text(z["ruest_min"])
    zeit = ("–" if z["fest"] else "0 s") if z["zeit_einheit_s"] is None else f"{zahl(z['zeit_einheit_s'], 1)} s"
    gesamt = zeit_text(z["gesamt_min"]) if z["gesamt_min"] is not None else "ohne Zeit"
    satz = (zahl(z["satz"], 2) + (f" ({z['satz_id']})" if z["satz_id"] else "")) if z["satz"] is not None else "–"
    return menge, ruest, zeit, gesamt, satz


def zeit_summen(zeiten):
    """Kennzahlen aus arbeitszeiten(): Minuten und Kosten nach Art, Durchlaufzeit (parallele Personalzeit nicht
    addiert)."""
    mit = [z for z in zeiten if z["gesamt_min"] is not None]
    m = lambda bed: sum(z["gesamt_min"] for z in mit if bed(z))
    k = lambda bed: sum(z["kosten"] for z in mit if bed(z))
    maschine = lambda z: z["art"] == "Maschine"
    personal = lambda z: z["art"] != "Maschine"
    return dict(maschine_min=m(maschine), personal_min=m(personal), ruest_min=sum(_n(z["ruest_min"]) for z in mit),
                bearbeitung_min=m(lambda z: True),
                durchlauf_min=m(maschine) + m(lambda z: personal(z) and not z["parallel"]),
                arbeitskosten=k(lambda z: True), maschinenkosten=k(maschine), personalkosten=k(personal),
                sonstige=sum(z["kosten"] for z in zeiten if z["gesamt_min"] is None))


KOSTENARTEN = (
    # (Bezeichnung, Schlüssel in summen, fett) in Rechenreihenfolge
    ("Material", "material", False), ("Laser schneiden", "laser_schneiden", False), ("Gewinde", "gewinde", False),
    ("Rüsten Maschine", "ruesten_maschine", False), ("Rüsten je Abmessung", "ruesten_abmessungen", False),
    ("Stangenwechsel", "stangenwechsel_kosten", False), ("Weitere Arbeitsschritte", "arbeitsschritte", False),
    ("Zusatzarbeiten", "zusatz", False),
    ("Zuschlag Material", "zuschlag_material", False), ("Zuschlag Fertigung", "zuschlag_fertigung", False),
    ("Zuschlag Fremdleistung", "zuschlag_fremdleistung", False), ("Herstellkosten", "herstell", True),
    ("Gewinn", "gewinn", False), ("Pauschale je Abmessung", "pauschalen", False),
    ("Programmierkosten", "programmierung", False), ("Angebotsaufschlag", "angebotsaufschlag", False),
    ("Fracht", "fracht", False), ("Zukaufteile (Einstand)", "zukauf_einstand", False),
    ("Aufschlag Zukaufteile", "zukauf_aufschlag", False), ("Skonto", "skonto", False),
    ("Verkaufspreis", "verkauf", True))


# Kostenübersicht im Angebot: Gruppen aus Kostenarten (Titel, Schlüssel, Summenzeile); jede Kostenart genau einmal
KOSTEN_GRUPPEN = (
    ("Material", ("material",), False), ("Laser schneiden", ("laser_schneiden",), False),
    ("Rüsten", ("ruesten_maschine", "ruesten_abmessungen", "stangenwechsel_kosten"), False),
    ("Zusätzliche Bearbeitung", ("gewinde", "arbeitsschritte", "zusatz"), False),
    ("Zuschläge", ("zuschlag_material", "zuschlag_fertigung", "zuschlag_fremdleistung"), False),
    ("Herstellkosten", ("herstell",), True), ("Gewinn", ("gewinn",), False),
    ("Programmierkosten", ("programmierung",), False),
    ("Pauschalen und Aufschläge", ("pauschalen", "angebotsaufschlag", "fracht"), False),
    ("Zukaufteile", ("zukauf_einstand", "zukauf_aufschlag"), False),
    ("Skonto", ("skonto",), False), ("Verkaufspreis", ("verkauf",), True))
assert sorted(n for _, ns, _ in KOSTEN_GRUPPEN for n in ns) == sorted(n for _, n, _ in KOSTENARTEN)


def kostenarten(summen, einst):
    """[(Bezeichnung mit Mengenangabe, Betrag, fett)] aller Kostenarten des Angebots, einzeln."""
    z = lambda w, st=1: zahl(w, st)
    zusatz = {
        "ruesten_maschine": f" ({z(summen['ruestzeit'])} min)",
        "ruesten_abmessungen": f" ({summen['abmessungen']} × {z(summen['ruestzeit_abmessung'])} min)",
        "stangenwechsel_kosten": f" ({summen['stangen']} × {z(summen['stangenwechsel'])} s)",
        "zuschlag_material": f" ({z(100 * _n(einst.get('zuschlag_material')))} %)",
        "zuschlag_fertigung": f" ({z(100 * _n(einst.get('zuschlag_fertigung')))} %)",
        "zuschlag_fremdleistung": f" ({z(100 * _n(einst.get('zuschlag_fremdleistung')))} %)",
        "gewinn": f" ({z(100 * _n(einst.get('gewinn')))} %)",
        "skonto": f" ({z(summen.get('skonto_satz', 0))} % eingerechnet)",
        "pauschalen": f" ({summen['abmessungen']} × {z(_n(einst.get('pauschale_abmessung')), 2)} €)"}
    return [(t + zusatz.get(n, ""), summen[n], fett) for t, n, fett in KOSTENARTEN]


def eingeplant_je_position(ergebnis):
    """{Bezug (schluessel): Anzahl eingeplanter Teile}"""
    n = {}
    for s in (ergebnis or {}).get("stangen", []):
        for t in s["teile"]:
            n[t["ref"]] = n.get(t["ref"], 0) + 1
    return n


def stangenmuster(ergebnis):
    """Gleich belegte Stangen zusammenfassen (Profil, Werkstoff, Stangenlänge, gleiche Teile in gleicher
    Reihenfolge und Lage), für Werkstattpapier und Stangenbild. Ergebnis: [(Stange, [Nummern])]."""
    muster = {}
    for s in (ergebnis or {}).get("stangen", []):
        schl = (gruppe_der_stange(s),
                tuple((t["ref"], t["laenge"], t["lage"]) for t in s["teile"]))
        muster.setdefault(schl, (s, []))[1].append(s["nr"])
    return list(muster.values())


def auswertung_zeilen(ergebnis, sw):
    """Auswertung je Gruppe mit Materialbedarf, Teilelänge und Verschnitt [m].
    sw = stangen_werte(...)"""
    out = []
    for a in ergebnis["auswertung"]:
        st_g = [(s, w) for s, w in zip(ergebnis["stangen"], sw)
                if gruppe_der_stange(s) == gruppe_der_stange(a)]
        bedarf = sum(s["stange"] for s, _ in st_g) / 1000
        laenge = sum(w["summe"] for _, w in st_g) / 1000
        out.append(dict(a, bedarf=bedarf, laenge=laenge, verschnitt=bedarf - laenge,
                        ausnutzung=laenge / bedarf if bedarf else 0))
    return out
