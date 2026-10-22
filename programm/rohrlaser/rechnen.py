"""Rechnungen eines Angebots: Positionswerte und Status, Stangenoptimierung, Schnittplan, Kalkulation.

Positionswerte und Status, Schnittplan, Stangenbelegung, Auswertung und Kalkulation. Die Optimierung
selbst steht in optimierung.py; tests/test_abnahme.py rechnet die Ergebnisse unabhängig nach.

Eingaben: kopf (dict: maschine, stange, …), positionen (Liste von dicts, Reihenfolge = Zeilen im
Angebot), k (stammdaten.Kontext), tabellen (dict mit 'preise', 'schneiddaten', 'gewinde' und
'zusatzarbeiten': Zeilen; fehlen die Zusatzarbeiten, gibt es keine).
"""
import hashlib
import math
import json
import re

from .stammdaten import (GASE, ROH, SATZ_MASCHINE, SCHRITTE_FEST, ZEITEINHEITEN, ZUSATZ_EINHEIT, flaeche_berechnet,
                         flaeche_wirksam, huellkreis, wand_schneiden)
from . import optimierung as opt
from .angebot import KUNDENMATERIAL, aktiv as position_aktiv, ist_zukaufteil
from . import fracht_angebot
from . import naht, zukauf

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


def beigestellt(p):
    """True, wenn der Kunde das Material der Position beistellt (Spalte Material: Kunde beigestellt)."""
    return (p or {}).get("material_herkunft") == KUNDENMATERIAL


def gruppe_von(p, kopf):
    """Stangengruppe einer Position: (Profil, Werkstoff, Oberfläche, Stangenlänge), bei Kundenmaterial zusätzlich
    'Kunde' (eigenes und beigestelltes Material nie auf einer Stange)."""
    return (p.get("profil_id"), p.get("werkstoff_id"), oberflaeche_von(p), stange_wirksam(p, kopf)) + \
        (("Kunde",) if beigestellt(p) else ())


def gruppe_der_stange(s):
    """Stangengruppe einer Stange oder Auswertungszeile (gespeicherte Ergebnisse ohne Oberfläche = roh, ohne
    Beistellung = eigenes Material). Mit einer anderen Lieferlänge geplante Stangen gehören zur Gruppe ihrer
    Positionen (grundlaenge)."""
    return (s["profil"], s["werkstoff"], s.get("oberflaeche") or "", s.get("grundlaenge") or s["stange"]) + \
        ((s["beistellung"],) if s.get("beistellung") else ())


def beladungen(stangen):
    """Anzahl Beladungen der Maschine: je Stange eine, je zugeschnittener Lieferstange eine je Werkstück."""
    return sum(len(s.get("werkstuecke") or [None]) for s in stangen)


def beladungen_sn(stangen):
    """Beladungen mit mindestens einem Teil mit fester Schweißnaht-Lage (Naht ausrichten): sie rechnen mit dem
    Stangenwechsel SN der Maschine. Bei zugeschnittenen Lieferstangen zählt jedes Werkstück für sich."""
    n = 0
    for s in stangen:
        fest = {t.get("werkstueck") for t in s.get("teile") or () if t.get("drehfreigabe") == opt.FEST}
        n += sum(1 for w in s["werkstuecke"] if w["nr"] in fest) if s.get("werkstuecke") else bool(fest)
    return n


def stangenwechsel_zeiten(m):
    """(Stangenwechsel, Stangenwechsel SN) der Maschine in s; SN leer (ältere Dateien, Snapshot) = normaler Wert."""
    wechsel = _n(m.get("stangenwechsel"))
    sn = m.get("stangenwechsel_sn")
    return wechsel, wechsel if sn is None else _n(sn)


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
    w["wand_schneiden"] = wand_schneiden(pr) if pr else None     # größte Wandstärke: Schneiddaten
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
        w["preis_hinterlegt"] = (beigestellt(p) or _n(p.get("preis_m")) > 0 or preis_zeile(p["profil_id"], p["werkstoff_id"], k, tabellen)
                                 is not None or _n(werkstoff.get("tonnenpreis")) > 0)
    w["zusatzarbeiten"] = tabellen.get("zusatzarbeiten")
    w["gewinde_stamm"] = tabellen.get("gewinde")
    w["vorschub"] = None
    w["gas"] = None
    if ist_zukaufteil(p):        # eingekauftes Teil: nur Gewicht (Fracht), keine Fertigungswerte
        g = p.get("gewicht_teil")
        w["gewicht"] = g if isinstance(g, (int, float)) and g > 0 else None
        w["gewicht_position"] = (w["gewicht"] * p["stueck"] if w["gewicht"] is not None and not _leer(p.get("stueck"))
                                 else None)
        return w
    if w["wand_schneiden"] is not None and not _leer(p.get("werkstoff_id")) and not _leer(kopf.get("maschine")):
        sd = schneiddaten(kopf.get("maschine"), p["werkstoff_id"], w["wand_schneiden"], tabellen,
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
def saetze_von(p):
    """Anzahl Sätze einer Position: Stückzahl / Stück je Satz (None ohne Satz oder Stückzahl)."""
    if _leer(p.get("satz")) or _n(p.get("stueck")) <= 0:
        return None
    je = _n(p.get("je_satz"))
    return _n(p["stueck"]) / (je if je >= 1 else 1)


def satz_abweichung(p, positionen):
    """Text, wenn die Positionen des Satzes von p verschiedene Anzahlen Sätze ergeben (das Angebot rechnet den Satz
    mit der größten Anzahl, die Kalkulation mit den Stückzahlen), sonst None."""
    if not positionen or saetze_von(p) is None:
        return None
    satz = str(p.get("satz")).strip()
    n = sorted({saetze_von(q) for q in positionen if position_aktiv(q) and saetze_von(q) is not None
                and str(q.get("satz")).strip() == satz})
    if len(n) < 2:
        return None
    return f"Satz {satz}: unterschiedliche Anzahl Sätze ({' / '.join(zahl(x, 2) for x in n)})"


def wert_negativ(p):
    """Titel des ersten Zahlenfelds der Position, das nicht negativ sein darf, aber negativ ist (z. B. aus einer
    geänderten Datei), sonst None."""
    from .angebot import POSITIONEN
    for f in POSITIONEN.felder:
        if f.art in ("zahl", "ganz") and f.von == 0 and isinstance(p.get(f.name), (int, float)) and p[f.name] < 0:
            return f.titel
    return None


def grunddaten_fehler(p, profile, k):
    """Erste fehlende oder unbekannte Grundangabe einer Rohrlaser-Position (Profil, Werkstoff, Oberfläche,
    Teilelänge, Stückzahl) als Text ohne „FEHLER:“, sonst None. Gemeinsam für status() und gruppen_bilden()
    (Code-Audit D-1); profile = bekannte Profil-IDs."""
    if p.get("profil_id") not in profile:
        return "Profil unbekannt"
    if p.get("werkstoff_id") not in k.werkstoffe:
        return "Werkstoff unbekannt"
    ob = oberflaeche_von(p)
    if ob and ob not in k.oberflaechen:
        return "Oberfläche unbekannt"
    laenge = p.get("laenge")
    if not isinstance(laenge, (int, float)) or laenge <= 0:
        return "Teilelänge fehlt"
    stk = p.get("stueck")
    if not isinstance(stk, (int, float)) or stk < 1 or int(stk) != stk:
        return "Stückzahl fehlt"
    return None


def pruefungen(p, w=None, positionen=None, zusatz=None, gewinde=None):
    """Gemeinsame Einzelprüfungen einer Position (Code-Audit D-1), die status(), zukaufteil_status() und der
    Hinweis der Kalkulation jeweils in ihrer Reihenfolge abfragen: {Schlüssel: Text} nur der zutreffenden Punkte.
    Schlüssel: satz_vielfach, satz, zusatz, gewinde, kontur (nicht bei manueller Schneidzeit), bohrungen.
    zusatz/gewinde = Stammdaten; None = nicht prüfen."""
    erg = {}
    if not _leer(p.get("satz")) and _n(p.get("je_satz")) > 0 and _n(p.get("stueck")) % p["je_satz"] != 0:
        erg["satz_vielfach"] = "Stückzahl ist kein Vielfaches von Stück je Satz"
    abw = satz_abweichung(p, positionen)
    if abw:
        erg["satz"] = abw
    if zusatz is not None:
        u = zusatz_unbekannt(p, zusatz)
        if u:
            erg["zusatz"] = u
    if gewinde is not None and not _leer(p.get("gewinde")):
        g = gewinde_unbekannt(p.get("gewinde"), gewinde)
        if g:
            erg["gewinde"] = g
    if w is not None and _leer(p.get("zeit_manuell")):
        kontur = konturen_pruefen(p, w.get("wand_schneiden"))
        if kontur:
            erg["kontur"] = kontur
    if bohrbild_offen(p):
        erg["bohrungen"] = "Bohrungen ungeprüft"
    return erg


def zukaufteil_status(p, positionen=None):
    """Status einer Zukaufteil-Position: Stückzahl, Zukaufartikel und Einkaufspreis (0 € zählt nicht)."""
    if _leer(p.get("stueck")) or p["stueck"] < 1:
        return "FEHLER: Stückzahl fehlt"
    eintraege = zukauf.eintraege(p)
    if not eintraege:
        return "FEHLER: Zukaufartikel fehlt (Zukaufteile …)"
    for e in eintraege:
        if zukauf.ek_fehlt(dict(bezuege=[(e.get("stand") or {}).get("bezug") or {}])):
            return "WARNUNG: EK fehlt (Zukaufteil ohne Einkaufspreis)"
    pr = pruefungen(p, positionen=positionen)
    for schluessel in ("satz_vielfach", "satz"):
        if schluessel in pr:
            return "WARNUNG: " + pr[schluessel]
    return "OK"


def status(p, w, kopf, k, eingeplant=None, positionen=None):
    """Status einer Position. eingeplant = Anzahl eingeplanter Teile laut Optimierung (oder None), positionen = alle
    Positionen des Angebots (Prüfung der Sätze)."""
    if ist_zukaufteil(p):
        return zukaufteil_status(p, positionen)
    if all(_leer(p.get(f)) for f in ("profil_id", "werkstoff_id", "laenge", "stueck")):
        return ""
    m = maschine(kopf, k)
    ob = oberflaeche_von(p)
    fehler = grunddaten_fehler(p, k.profile, k)
    if fehler in ("Profil unbekannt", "Werkstoff unbekannt", "Oberfläche unbekannt"):
        return "FEHLER: " + fehler
    if w["querschnitt"] is None:
        return "FEHLER: Querschnitt fehlt (Profil)"
    if fehler:
        return "FEHLER: " + fehler
    negativ = wert_negativ(p)
    if negativ:
        return f"FEHLER: {negativ} darf nicht negativ sein"
    if m is None:
        return "FEHLER: Maschine fehlt/unbekannt"
    if m.get("max_stange") and w["stange"] is not None and w["stange"] > m["max_stange"]:
        return "FEHLER: Stange länger als Maschine zulässt"
    grenze = grenze_ueberschritten(m, k.profile.get(p.get("profil_id")), w["kg_m"])
    if grenze:
        return "FEHLER: " + grenze
    if w["nutz"] is None or p["laenge"] + _n(m.get("schnittverlust")) > w["nutz"]:
        return "FEHLER: Teil länger als Nutzlänge"
    naht_status = naht.pruefen(p, k.profile.get(p.get("profil_id")))
    if naht_status and naht_status.startswith("FEHLER"):
        return naht_status
    if eingeplant is not None and _n(p.get("stueck")) - eingeplant > 0:
        return "WARNUNG: nicht vollständig eingeplant"
    if w["preis_hinterlegt"] is False:
        return "WARNUNG: kein gültiger Materialpreis"
    kat_o = (k.oberflaechen.get(ob) or {}).get("kategorie") if ob else None
    if kat_o and kat_o != kategorie(p.get("werkstoff_id"), k):
        return f"WARNUNG: Oberfläche {ob} ist für {kat_o}"
    pr = pruefungen(p, w, positionen, w.get("zusatzarbeiten") or (), w.get("gewinde_stamm"))
    for schluessel in ("satz_vielfach", "satz"):
        if schluessel in pr:
            return "WARNUNG: " + pr[schluessel]
    if "zusatz" in pr:
        return f"WARNUNG: Zusatzarbeit '{pr['zusatz']}' unbekannt"
    if "gewinde" in pr:
        return f"WARNUNG: Gewinde '{pr['gewinde']}' nicht erkannt (Format 4xM6; 2xM8)"
    if naht_status:
        return naht_status
    manuell = not _leer(p.get("zeit_manuell"))
    if "kontur" in pr:
        return "WARNUNG: " + pr["kontur"]
    if _leer(p.get("schneidweg")) and not manuell:
        return "HINWEIS: Schneidweg fehlt"
    if w["vorschub"] is None and not manuell:
        return "HINWEIS: keine Schneiddaten"
    if "bohrungen" in pr:
        return "HINWEIS: Bohrungen prüfen (Doppelklick)"
    if manuell:
        return "HINWEIS: Schneidzeit manuell"
    if _n(p.get("preis_m")) > 0 and not beigestellt(p):
        return "HINWEIS: Meterpreis manuell"
    if beigestellt(p):
        return "HINWEIS: Material vom Kunden beigestellt"
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
        grund = grunddaten_fehler(p, profile, k)
        if grund:
            fehl("Stückzahl fehlt oder ungültig" if grund == "Stückzahl fehlt" else grund); continue
        ob = oberflaeche_von(p)
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
        bs = "Kunde" if beigestellt(p) else ""
        key = (pid, wst, ob, stange) + ((bs,) if bs else ())
        g = gruppen.setdefault(key, opt.Gruppe(pid, wst, stange, end, greif, me["kerf"], me["abstand"], ob,
                                               beistellung=bs, querschnitt=querschnitt_gehrung(pr)))
        a_ger = p.get("a_gerade") != "nein"
        b_ger = p.get("b_gerade") != "nein"
        u = opt.schnittlaenge(pr["form"], pr["a"], pr["b"], pr["wand"], pr["flaeche"])
        h = p.get("schneidweg")
        if h:
            u = min(u, h / 2)
        a_s = p.get("a_schnitt") or u
        b_s = p.get("b_schnitt") or u
        geh = dict(a_gehrung=None if a_ger else naht.ende_lesen(p.get("a_ende")),
                   b_gehrung=None if b_ger else naht.ende_lesen(p.get("b_ende")),
                   drehung={naht.FEST: opt.FEST, naht.UNBEKANNT: opt.UNBEKANNT}.get(naht.vorgabe(p), opt.FREI))
        if geh["drehung"] == opt.FEST:
            try:
                geh["naht"] = naht.normieren(p.get("naht_winkel"))
            except ValueError:
                geh["drehung"] = opt.UNBEKANNT      # feste Naht ohne Winkel (FEHLER im Status): nicht drehen
        for n in range(1, stk_n + 1):
            g.teile.append(opt.Teil(r, p.get("pos"), name, n, laenge, a_ger, b_ger, a_s, b_s, **geh))
    return list(gruppen.values()), fehler, neue_profile


def querschnitt_gehrung(pr):
    """Querschnitt für das Ineinanderlegen von Gehrungen (optimierung.Gruppe.querschnitt): Rechteck- und
    Quadratrohr als Kasten mit der Breitseite oben, Rundrohr als Kreis, andere Profile () = nicht ineinanderlegen."""
    form = naht.form_von(pr)
    if form == "Rundrohr":
        return ("Rund", pr["a"] / 2)
    if form in ("Quadratrohr", "Rechteckrohr"):
        return ("Kasten",) + naht.seitenmasse(pr)
    return ()


def teil_kennung(t):
    """Werte eines Teils für die Prüfsumme. Teile ohne Gehrung, ohne Nahtvorgabe und mit zwei gleichen Enden wie vor
    0.6.23 (ältere Angebote bleiben aktuell); ein schräges und ein gerades Ende zählt mit, weil seit 0.6.23 nie mehr
    gewendet wird."""
    alt = (t.zeile, t.pos, t.artikel, t.nr, t.laenge, t.a_gerade, t.b_gerade, t.a_schnitt, t.b_schnitt)
    neu = (t.a_gehrung, t.b_gehrung, t.drehung, t.naht)
    if neu == (None, None, opt.FREI, None) and t.a_gerade == t.b_gerade:
        return alt
    return alt + neu + ("nie wenden",)


def laengen_eingaben(gruppen, kopf, k, tabellen, einst):
    """Was der Vergleich der Lieferlängen verwendet (für die Prüfsumme); leer ohne Lieferlängen."""
    daten = []
    for g in gruppen:
        info = laengen_der_gruppe(g, k, tabellen, einst)
        if info["zeilen"] or info["ausgenommen"]:
            daten.append([g.profil, g.werkstoff, g.oberflaeche, g.stange, info["ausgenommen"], info["basis_lieferbar"],
                          [[z.get(n) for n in ("laenge", "basis", "preis")] for z in info["zeilen"]]])
    if not daten and not kopf.get("laengenwahl"):
        return []
    m = maschine(kopf, k) or {}
    return [daten, m.get("max_stange"), einstellung_wert(einst, "zuschnitt_verlust"), kopf.get("laengenwahl") or {},
            m.get("min_stange"), einstellung_wert(einst, "zuschnitt_puffer")]


def eingabe_kennung(kopf, positionen, k, tabellen=None, einst=None):
    """Prüfsumme über alles, was die Optimierung verwendet. Weicht sie von der gespeicherten ab,
    ist die Optimierung veraltet."""
    try:
        gruppen, fehler, neue = gruppen_bilden(kopf, positionen, k)
    except ValueError as e:
        return "fehler:" + str(e)
    # Oberfläche nur, wenn gesetzt: ältere Angebote ohne Oberfläche bleiben aktuell
    daten = [[(g.profil, g.werkstoff, g.stange, g.endbeschnitt, g.greiferrest, g.kerf, g.abstand,
               [teil_kennung(t) for t in g.teile]) + ((g.oberflaeche,) if g.oberflaeche else ())
              + ((g.beistellung,) if g.beistellung else ())
              for g in gruppen],
             [sorted(f.items()) for f in fehler], [sorted(n.items()) for n in neue]]
    laengen = laengen_eingaben(gruppen, kopf, k, tabellen, einst)
    if laengen:                  # nur mit Lieferlängen: ältere Angebote bleiben aktuell
        daten.append(laengen)
    return hashlib.sha1(json.dumps(daten, default=str, sort_keys=True).encode()).hexdigest()


def drehung_text(ohne, stangen, gespart):
    """Zusatz zur Bewertung einer Gruppe: Ersparnis durch Drehen und Ineinanderlegen der Gehrungen."""
    if ohne is None:
        return f"; Gehrungen ineinander: {mm_text(gespart)} mm gespart" if gespart > EPS else ""
    if ohne > stangen:
        n = ohne - stangen
        return f"; Drehen spart {n} Stange{'n' if n > 1 else ''}, Gehrungen ineinander {mm_text(gespart)} mm"
    if gespart > EPS:
        return f"; Gehrungen ineinander {mm_text(gespart)} mm, Drehen spart keine Stange"
    return "; Drehen bringt keine Verbesserung"


def naht_text(t):
    """Nahtvorgabe eines Teils für Schnittplan und Werkstattpapiere ('' = frei drehbar)."""
    if t.drehung == opt.UNBEKANNT:
        return "Naht unbekannt, nicht drehen"
    if t.drehung == opt.FEST:
        return f"Naht {t.naht:g}° fest".replace(".", ",") if t.naht is not None else "Naht fest"
    return ""


def teil_zeichen(t):
    """Markierung eines Teils im Stangenbild und in den Werkstattpapieren: (Lage der Naht auf der Stange [°] oder
    None, Kurztext). Lage wie die Naht: Blick von Ende A, 0° oben, 90° rechts (Rechteckrohr mit der Breitseite oben).
    Kurztext leer = frei drehbar und nicht gedreht, nichts anzeigen."""
    dreh = t.get("drehung") or 0
    if t.get("drehfreigabe") == opt.UNBEKANNT:
        return None, "Naht unbekannt, nicht drehen"
    lage, text = None, []
    if t.get("drehfreigabe") == opt.FEST:
        if t.get("naht") is not None:
            lage = (t["naht"] + dreh) % 360
            text.append(f"Naht {lage:g}°".replace(".", ","))
        else:
            text.append("Naht fest")
    if dreh:
        text.append(f"gedreht {dreh:g}°".replace(".", ","))
    return lage, " · ".join(text)


def stange_zeichen(s):
    """Markierung einer Stange im Stangenbild und in den Werkstattpapieren, einmal je Stange statt je Teil
    (Patrick 22.10.2026): (Lage der Naht auf der Stange [°] oder None, Querschnitt oder None, Kurztext; leer =
    nichts anzuzeigen). Die Naht liegt bei allen Teilen mit fester Naht an derselben Stelle der Stange."""
    lagen, text, q = [], [], None
    for t in s["teile"]:
        q = q or t.get("querschnitt")
        lage, _ = teil_zeichen(t)
        if lage is not None:
            lagen.append(lage)
    lage = max(set(lagen), key=lagen.count) if lagen else None
    if lage is not None:
        text.append(f"Naht {lage:g}°".replace(".", ","))
    elif any(t.get("drehfreigabe") == opt.FEST for t in s["teile"]):
        text.append("Naht fest")
    if any(t.get("drehfreigabe") == opt.UNBEKANNT for t in s["teile"]):
        text.append("Naht unbekannt: nicht drehen")
    n = sum(1 for t in s["teile"] if t.get("drehung"))
    if n:
        text.append(f"{n} {'Teil' if n == 1 else 'Teile'} gedreht")
    return lage, q, " · ".join(text)


def symbol_masse(q):
    """(Breite, Höhe) des Querschnitt-Symbols, größere Seite = 1; q wie optimierung.Gruppe.querschnitt."""
    if q and q[0] == "Kasten" and max(q[1], q[2]) > 0:
        return q[1] / max(q[1], q[2]), q[2] / max(q[1], q[2])
    return 1.0, 1.0


def naht_punkt(q, winkel):
    """Lage der Naht auf dem Rand des Querschnitt-Symbols: (x rechts, y oben) ab der Mitte, Maße wie symbol_masse."""
    x, y = math.sin(math.radians(winkel)), math.cos(math.radians(winkel))
    if not q or q[0] != "Kasten":
        return x / 2, y / 2
    b, h = symbol_masse(q)
    f = min(b / 2 / abs(x) if abs(x) > EPS else math.inf, h / 2 / abs(y) if abs(y) > EPS else math.inf)
    return x * f, y * f


def naht_strich(t, oben=0):
    """Naht eines Teils als Strich im Stangenbild (Patrick 22.10.2026): (Höhe von −1 = unten bis 1 = oben,
    sichtbar) oder None ohne feste Naht. oben: Winkel, der im Bild oben liegt (0 von der Seite, 270 von oben);
    sichtbar ist die Seite oben + 90° (von der Seite: 90°, von oben: 0°), die andere gestrichelt."""
    lage, _ = teil_zeichen(t)
    if lage is None:
        return None
    q = t.get("querschnitt")
    if q and q[0] == "Kasten" and oben % 180:
        q = ("Kasten", q[2], q[1])
    x, y = naht_punkt(q, lage - oben)
    return y / (symbol_masse(q)[1] / 2), x > -EPS


def gehrung_gespart(stange):
    """Durch ineinandergelegte Gehrungen gespartes Material einer Stange [mm] (schon in Rest und Ausnutzung)."""
    return sum(t.get("material_gespart") or 0 for t in stange["teile"])


def umriss(t):
    """x-Werte eines Teils im Stangenbild: (oben links, oben rechts, unten rechts, unten links) [mm]."""
    ka, kb = t.get("kante_a") or (0, 0), t.get("kante_b") or (0, 0)
    return t["von"] + ka[0], t["bis"] - kb[0], t["bis"] - kb[1], t["von"] + ka[1]


def _folge_teile(g, folge, positionen, start=0.0):
    """Teile einer Stange bzw. eines Werkstücks ab Position start: (teile, verlust inkl. letztem Schnitt,
    gemeinsame Schnitte, Belegungstexte)."""
    pos = start + g.endbeschnitt
    vorher, verlust, teile, belegung, n_gem = None, 0.0, [], [], 0
    oben = opt.ansicht(g, folge)
    for t, drehung in folge:
        a_ger, b_ger, a_s, b_s = opt.lage(t, drehung)
        eingespart_mm, eingespart_e, ueberlappung = 0.0, 0, 0.0
        if vorher is None:
            art = "Stangenanfang"
        else:
            gap = opt.trennung_teile(g, vorher[2], vorher[3], t, drehung)
            gemeinsam = vorher[0] and a_ger
            art = "gemeinsamer Schnitt" if gemeinsam else "2 Schnitte"
            if gemeinsam:
                n_gem += 1
                eingespart_mm, eingespart_e = min(vorher[1], a_s), 1
            elif opt.ineinander(g, vorher[2], vorher[3], t, drehung):
                art = "Gehrung ineinander"
                ueberlappung = opt.trennung(g.kerf, g.abstand, False, False) - gap
            pos += gap
            verlust += gap
        teile.append(dict(index=t.zeile - ZEILE0, ref=schluessel(positionen[t.zeile - ZEILE0], t.zeile - ZEILE0),
                          pos=t.pos, artikel=t.artikel, laenge=t.laenge,
                          von=round(pos, 2), bis=round(pos + t.laenge, 2),
                          lage=f"gedreht {drehung:g}°" if drehung else "normal", drehung=drehung,
                          drehfreigabe=t.drehung, naht=t.naht, trennung=art,
                          eingespart_mm=round(eingespart_mm, 1), eingespart_e=eingespart_e,
                          material_gespart=round(ueberlappung, 1), naht_text=naht_text(t)))
        if g.querschnitt:                   # Querschnitt-Symbol mit Nahtlage im Stangenbild
            teile[-1]["querschnitt"] = list(g.querschnitt)
        if t.a_gehrung or t.b_gehrung:      # Schräge Enden im Stangenbild (Rücksprung oben/unten)
            teile[-1].update(ansicht="von oben" if oben else "von der Seite",
                             kante_a=[round(x, 1) for x in opt.kante(g, t.a_gehrung, drehung, oben)],
                             kante_b=[round(x, 1) for x in opt.kante(g, t.b_gehrung, drehung, oben)])
        pos += t.laenge
        vorher = (b_ger, b_s, t, drehung)
        belegung.append(f"{t.pos if t.pos is not None else t.artikel}×{t.laenge:g}")
    return teile, verlust + g.kerf, n_gem, belegung


def laenge_waehlen(vg, plaene, kopf, positionen, k, tabellen, einst, auto=False):
    """Lieferlänge, mit der eine Gruppe geplant wird (None = Stangenlänge des Angebots): die im Angebot übernommene
    Länge (kopf['laengenwahl']), ist die Stangenlänge des Angebots nicht lieferbar, die günstigste ausführbare
    andere; auto (Staffelpreise je Menge): die empfohlene."""
    if vg is None:
        return None
    gew = (kopf.get("laengenwahl") or {}).get(vg["schluessel"])
    if auto or not vg["basis_lieferbar"]:
        b = laengen_bewerten(vg, kopf, positionen, k, tabellen, einst)
        if b["empfehlung"] in (LAENGE_ALTERNATIVE, LAENGE_NUR_ALTERNATIVE) or not vg["basis_lieferbar"]:
            return b["beste"] if b["beste"] != vg["stange"] else None
        return None
    if gew is not None and gew in plaene and gew != vg["stange"] and not plaene[gew]["fehler"]:
        return gew
    return None


def _beistellung_markieren(g, zeilen):
    """Stangen und Auswertung einer Gruppe mit Kundenmaterial kennzeichnen (beistellung='Kunde')."""
    if g.beistellung:
        for x in zeilen:
            x["beistellung"] = g.beistellung


class Abbruch(Exception):
    """Optimierung vom Benutzer abgebrochen (fortschritt hat sie ausgelöst); es wird nichts gespeichert."""


def optimieren(kopf, positionen, k, tabellen=None, einst=None, auto=False, fortschritt=None):
    """Optimiert das Angebot. Ergebnis (als JSON speicherbar):
    {'stangen': [...], 'auswertung': [...], 'fehler': [...], 'neue_profile': [...], 'kennung': str,
     'laengen': [Vergleich der Lieferlängen je Gruppe (laengen_vergleich_gruppe) mit 'gewaehlt' = geplante
     Lieferlänge oder None, nur wenn es Lieferlängen gibt]}
    Je Stange: nr, profil, werkstoff, stange, end, greif, verlust, trennungen, gemeinsam, belegung (Text),
    teile: [{index, pos, artikel, laenge, von, bis, lage, trennung, eingespart_mm, eingespart_e, drehung,
    drehfreigabe, naht, naht_text, material_gespart, querschnitt (Rund-, Quadrat- und Rechteckrohr, wie
    optimierung.Gruppe.querschnitt)}], bei schrägen Enden mit Richtung zusätzlich ansicht, kante_a
    und kante_b (Rücksprung der Schnittkante oben/unten im Stangenbild, umriss).
    Mit einer anderen Lieferlänge geplante Stangen haben dazu grundlaenge (Stangenlänge des Angebots, Schlüssel der
    Gruppe); kommen sie vom Lieferanten zugeschnitten, zusätzlich werkstuecke [{nr, von, bis, laenge, end, greif}]
    (je Werkstück eine Beladung der Maschine), zuschnitt (Text) und je Teil werkstueck (Nummer).
    auto: Lieferlänge je Gruppe nach der Empfehlung (Staffelpreise), sonst nur übernommene Längen.
    fortschritt(schritt, schritte, text): wird vor jeder Gruppe aufgerufen (Fortschrittsanzeige); löst sie Abbruch
    aus, endet die Optimierung ohne Ergebnis. Die Rechnung selbst ist dieselbe."""
    gruppen, fehler, neue_profile = gruppen_bilden(kopf, positionen, k)
    melden = fortschritt or (lambda *_: None)
    schritte = 2 * len(gruppen)
    m = maschine(kopf, k)
    saege = _n(einstellung_wert(einst, "zuschnitt_verlust"))
    # Kundenmaterial: kommt in der Stangenlänge des Angebots, kein Vergleich der Lieferlängen
    infos = [laengen_der_gruppe(g, k, tabellen, einst) if tabellen and not g.beistellung else None for g in gruppen]
    folgen_je_gruppe = []
    for n, (g, i) in enumerate(zip(gruppen, infos)):
        melden(n, schritte, f"Schnittplan {g.profil} / {g.werkstoff}")
        folgen_je_gruppe.append(opt.optimiere(g) if i is None or i["basis_lieferbar"] else None)
    mit = [(g, f) for g, f in zip(gruppen, folgen_je_gruppe) if f is not None]
    opt.pruefe([g for g, _ in mit], [f for _, f in mit])
    stangen, auswertung, laengen, nr = [], [], [], 0
    for n, (g, folgen) in enumerate(zip(gruppen, folgen_je_gruppe)):
        melden(len(gruppen) + n, schritte, f"Lieferlängen und Auswertung {g.profil} / {g.werkstoff}")
        s0, a0 = len(stangen), len(auswertung)
        vg, plaene = (laengen_vergleich_gruppe(g, k, tabellen, m, saege, folgen, einst) if tabellen and not g.beistellung
                      else (None, {}))
        gewaehlt = laenge_waehlen(vg, plaene, kopf, positionen, k, tabellen, einst, auto)
        if vg is not None:
            laengen.append(dict(vg, gewaehlt=gewaehlt))
        if folgen is None and gewaehlt is None:          # nichts lieferbar und ausführbar
            for t in g.teile:
                if not any(f["index"] == t.zeile - ZEILE0 for f in fehler):
                    p = positionen[t.zeile - ZEILE0]
                    fehler.append(dict(index=t.zeile - ZEILE0, pos=p.get("pos"), artikel=t.artikel,
                                       anzahl=sum(1 for x in g.teile if x.zeile == t.zeile),
                                       grund="keine lieferbare Stangenlänge ausführbar (Lieferlängen)"))
            continue
        if gewaehlt is None:
            for folge in folgen:
                nr += 1
                teile, verlust, n_gem, belegung = _folge_teile(g, folge, positionen)
                stangen.append(dict(nr=nr, profil=g.profil, werkstoff=g.werkstoff, oberflaeche=g.oberflaeche,
                                    stange=g.stange, end=g.endbeschnitt,
                                    greif=g.greiferrest, verlust=round(verlust, 2), trennungen=len(folge),
                                    gemeinsam=n_gem, belegung=" | ".join(belegung), teile=teile))
            man = opt.manuell(g)
            ohne = opt.ohne_drehung(g)
            gespart = sum(gehrung_gespart(s) for s in stangen[s0:])
            auswertung.append(dict(profil=g.profil, werkstoff=g.werkstoff, oberflaeche=g.oberflaeche, stange=g.stange,
                                   teile=len(g.teile),
                                   stangen=len(folgen), manuell=len(man), untergrenze=opt.untergrenze(g),
                                   ausnutzung_manuell=(sum(t.laenge for t in g.teile) / (len(man) * g.stange)
                                                       if man else 0),
                                   gemeinsam=sum(opt.gemeinsame_schnitte(f) for f in folgen),
                                   bewertung=opt.bewertung(g, len(folgen)) + drehung_text(ohne, len(folgen), gespart),
                                   ohne_drehung=ohne, gehrung_mm=round(gespart, 1) if gespart else None))
            _beistellung_markieren(g, stangen[s0:] + auswertung[a0:])
            continue
        v = plaene[gewaehlt]
        h = opt.replace(g, stange=gewaehlt, teile=list(g.teile))
        n_gem_gruppe = 0
        for lieferstange in v["stangen"]:
            nr += 1
            if not v["zuschnitt"]:
                folge = lieferstange[0][1]
                teile, verlust, n_gem, belegung = _folge_teile(g, folge, positionen)
                n_gem_gruppe += n_gem
                stangen.append(dict(nr=nr, profil=g.profil, werkstoff=g.werkstoff, oberflaeche=g.oberflaeche,
                                    stange=gewaehlt, grundlaenge=g.stange, end=g.endbeschnitt,
                                    greif=g.greiferrest, verlust=round(verlust, 2), trennungen=len(folge),
                                    gemeinsam=n_gem, belegung=" | ".join(belegung), teile=teile))
                continue
            start, teile, verlust, n_gem, belegung, ws = 0.0, [], 0.0, 0, [], []
            for j, (laenge, folge) in enumerate(lieferstange, start=1):
                if j > 1:
                    start += saege
                    verlust += saege
                t_ws, v_ws, g_ws, b_ws = _folge_teile(g, folge, positionen, start)
                for t in t_ws:
                    t["werkstueck"] = j
                # Aufrundung des Werkstücks auf ganze mm zählt zum Verlust; der Greiferrest bleibt frei
                verlust += v_ws + (laenge - g.endbeschnitt - sum(t.laenge for t, _ in folge) - v_ws - g.greiferrest)
                ws.append(dict(nr=j, von=round(start, 2), bis=round(start + laenge, 2), laenge=laenge,
                               end=g.endbeschnitt, greif=g.greiferrest))
                teile += t_ws
                n_gem += g_ws
                belegung.append(f"W{j} {mm_text(laenge)}: " + " | ".join(b_ws))
                start += laenge
            n_gem_gruppe += n_gem
            rest = gewaehlt - start
            stangen.append(dict(nr=nr, profil=g.profil, werkstoff=g.werkstoff, oberflaeche=g.oberflaeche,
                                stange=gewaehlt, grundlaenge=g.stange, end=g.endbeschnitt * len(ws),
                                greif=g.greiferrest * len(ws), verlust=round(verlust, 2), trennungen=len(teile),
                                gemeinsam=n_gem, belegung=" || ".join(belegung), teile=teile, werkstuecke=ws,
                                zuschnitt=f"Zuschnitt beim Lieferanten: {' + '.join(mm_text(w['laenge']) for w in ws)}"
                                          f" mm, Rest {mm_text(max(rest - (saege if rest > saege else rest), 0))} mm"))
        n = len(v["stangen"])
        untergrenze = opt.untergrenze(h) if not v["zuschnitt"] else math.ceil(
            (sum(opt.mindestbedarf(g, t) for t in g.teile) + g.endbeschnitt + g.greiferrest) / gewaehlt - EPS)
        man = opt.manuell(h) if not v["zuschnitt"] else []
        auswertung.append(dict(profil=g.profil, werkstoff=g.werkstoff, oberflaeche=g.oberflaeche, stange=gewaehlt,
                               grundlaenge=g.stange, teile=len(g.teile), stangen=n, manuell=len(man) if man else n,
                               untergrenze=untergrenze,
                               ausnutzung_manuell=(sum(t.laenge for t in g.teile) / (len(man) * gewaehlt)
                                                   if man else 0),
                               gemeinsam=n_gem_gruppe,
                               bewertung=f"Lieferlänge {m_text(gewaehlt)} m"
                                         + (", optimal (Untergrenze erreicht)"
                                            if not v["zuschnitt"] and n <= untergrenze else "")))
        _beistellung_markieren(g, stangen[s0:] + auswertung[a0:])
    out = dict(stangen=stangen, auswertung=auswertung, fehler=fehler, neue_profile=neue_profile,
               kennung=eingabe_kennung(kopf, positionen, k, tabellen, einst))
    if laengen:
        out["laengen"] = laengen
    return out


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
        ueber = belegt + s["greif"] > s["stange"] + 0.001 or max_bis > s["stange"] - s["greif"] + 0.001
        if s.get("werkstuecke"):        # zugeschnittene Lieferstange: jedes Werkstück für sich
            ueber = belegt + s["greif"] > s["stange"] + 0.001 or any(
                w["laenge"] > _n((maschine(kopf, k) or {}).get("max_stange") or w["laenge"]) + 0.001
                or any(t["bis"] > w["bis"] - w["greif"] + 0.001 or t["von"] < w["von"] + w["end"] - 0.001
                       for t in s["teile"] if t.get("werkstueck") == w["nr"]) for w in s["werkstuecke"])
        out.append(dict(teile=len(s["teile"]), summe=summe, belegt=belegt, rest=s["stange"] - belegt,
                        ausnutzung=summe / s["stange"],
                        pruefung="ÜBERBELEGT" if ueber else "OK",
                        gewicht=gewicht, kosten=stangenkosten(s, gewicht, kopf, positionen, k, tabellen)))
    return out


def anzeige_stangen(ergebnis, sw=None):
    """Stangen so, wie die Maschine sie lädt (Schnittplan, Stangenbild, Werkstattpapiere): eine vom Lieferanten
    zugeschnittene Lieferstange (z. B. 12 m) erscheint als ihre Werkstücke, jedes wie eine eigene Stange mit
    Endbeschnitt, Teilen und Greiferrest; der Zuschnitt selbst wird nicht gezeigt. Gerechnet wird weiter mit den
    Lieferstangen (ergebnis['stangen']). Ergebnis: [Stange], mit sw = stangen_werte(...) [(Stange, Werte)]; das
    Gewicht einer Lieferstange wird nach Werkstücklänge auf ihre Werkstücke verteilt, die Kosten aller
    zugeschnittenen Lieferstangen einer Gruppe nach Länge auf alle Werkstücke der Gruppe (Abfall gleichmäßig,
    auch wenn eine Lieferstange nur ein Werkstück trägt)."""
    stangen = (ergebnis or {}).get("stangen", [])
    mit_werten = sw is not None
    sw = sw if mit_werten else [None] * len(stangen)
    topf = {}                           # Gruppe -> [Kosten der Lieferstangen, Länge der Werkstücke]
    for s, w in zip(stangen, sw):
        if s.get("werkstuecke") and w is not None and w["kosten"] is not None:
            t = topf.setdefault((gruppe_der_stange(s), s["stange"]), [0.0, 0.0])
            t[0] += w["kosten"]
            t[1] += sum(x["laenge"] for x in s["werkstuecke"])
    out = []
    for s, w in zip(stangen, sw):
        if not s.get("werkstuecke"):
            out.append((dict(s, nr=len(out) + 1), w))
            continue
        kosten_t, laenge_t = topf.get((gruppe_der_stange(s), s["stange"]), (0.0, 0.0))
        belegung = dict(b.split(": ", 1) for b in s.get("belegung", "").split(" || ") if ": " in b)
        for x in s["werkstuecke"]:
            teile = [dict({n: v for n, v in t.items() if n != "werkstueck"}, von=round(t["von"] - x["von"], 2),
                          bis=round(t["bis"] - x["von"], 2)) for t in s["teile"] if t.get("werkstueck") == x["nr"]]
            summe = sum(t["laenge"] for t in teile)
            verlust = round(x["laenge"] - x["end"] - summe - x["greif"], 2)     # Trennschnitte und Aufrundung
            st = dict(nr=len(out) + 1, profil=s["profil"], werkstoff=s["werkstoff"], oberflaeche=s.get("oberflaeche"),
                      stange=x["laenge"], grundlaenge=s.get("grundlaenge"), end=x["end"], greif=x["greif"],
                      verlust=verlust, trennungen=len(teile), gemeinsam=sum(1 for t in teile if t.get("eingespart_mm")),
                      belegung=belegung.get(f"W{x['nr']} {mm_text(x['laenge'])}", ""), teile=teile)
            if s.get("beistellung"):
                st["beistellung"] = s["beistellung"]
            wx = None
            if mit_werten:
                anteil = x["laenge"] / laenge_t if laenge_t else 0
                belegt = x["end"] + summe + verlust
                wx = dict(teile=len(teile), summe=summe, belegt=belegt, rest=x["laenge"] - belegt,
                          ausnutzung=summe / x["laenge"], pruefung=w["pruefung"],
                          gewicht=w["gewicht"] * x["laenge"] / s["stange"] if w["gewicht"] is not None else None,
                          kosten=kosten_t * anteil if w["kosten"] is not None else None)
            out.append((st, wx))
    return out if mit_werten else [s for s, _ in out]


def stangenkosten(s, gewicht, kopf, positionen, k, tabellen):
    """Materialkosten einer Stange (lieferstange_preis); Kundenmaterial kostet nichts."""
    if s.get("beistellung"):
        return 0.0
    return lieferstange_preis(gruppe_der_stange(s), s["stange"], gewicht, kopf, positionen, k, tabellen)[0]


def haendler_mehrlaenge(laenge, einst=None, tabellen=None):
    """Länge, die der Händler je Stange zusätzlich berechnet (nur Preis, nicht Planung): Einstellungen
    'haendler_mehr_kurz' bis zur Grenze 'haendler_mehr_grenze' (Vorgabe 50 mm bis 6.500 mm), darüber
    'haendler_mehr_lang' (Vorgabe 100 mm, z. B. 12 m). Einstellungen aus einst, sonst aus tabellen['einstellungen']."""
    e = einst if einst is not None else (tabellen or {}).get("einstellungen")
    lang = laenge > _n(einstellung_wert(e, "haendler_mehr_grenze")) + EPS
    return _n(einstellung_wert(e, "haendler_mehr_lang" if lang else "haendler_mehr_kurz"))


def lieferstange_preis(gr, laenge, gewicht, kopf, positionen, k, tabellen, einst=None, mehr=True):
    """Materialkosten einer Stange der Länge laenge für die Gruppe gr (Profil, Werkstoff, Oberfläche, Stangenlänge
    des Angebots): Preis €/m im Angebot > Zeile in 'Lieferlängen' mit dieser Länge und Preis > 'Preise' >
    Tonnenpreis; zu den drei letzten kommt der Aufpreis der Oberfläche je m. Nach Länge oder Gewicht berechnete
    Preise gelten für die Länge + Händler-Mehrlänge (mehr=False: ohne, für den €/m). Ergebnis (€, fehlt): fehlt = Text,
    wenn der Preis nicht belastbar ist (kein Preis; Lieferlänge ohne eigenen Preis bei 'Preise' in €/Stange einer
    anderen Länge), sonst None."""
    profil, werkstoff, ob = gr[:3]
    # berechnete Länge (Händler-Mehrlänge) für Preise nach Länge oder Gewicht; €/Stange bleibt je Stange
    lb = laenge + (haendler_mehrlaenge(laenge, einst, tabellen) if mehr and laenge else 0)
    gb = gewicht * lb / laenge if gewicht is not None and laenge else gewicht
    ab = [p["preis_m"] for p in positionen if _n(p.get("preis_m")) and gruppe_von(p, kopf) == gr]
    if ab and max(ab) > 0:
        return max(ab) * lb / 1000, None
    aufpreis_m = _n((k.oberflaechen.get(ob or "") or {}).get("aufpreis_m"))
    aufpreis = aufpreis_m * lb / 1000
    zl = next((z for z in lieferlaengen(profil, werkstoff, k, tabellen, einst) if z["laenge"] == laenge), None)
    if zl is not None and zl.get("basis"):
        if zl["basis"] == "€/kg":
            return _n(gb) * zl["preis"] + aufpreis, None if gewicht is not None else "Gewicht fehlt"
        if zl["basis"] == "€/m":
            return zl["preis"] * lb / 1000 + aufpreis, None
        return zl["preis"] + aufpreis_m * laenge / 1000, None
    z = preis_zeile(profil, werkstoff, k, tabellen)
    if z is not None:
        if z["basis"] == "€/kg":
            return _n(gb) * z["preis"] + aufpreis, None if gewicht is not None else "Gewicht fehlt"
        if z["basis"] == "€/m":
            return z["preis"] * lb / 1000 + aufpreis, None
        if z["basis"] == "€/Stange":
            fehlt = (f"Preis für {mm_text(laenge)} mm fehlt (Lieferlängen)"
                     if zl is not None and z["lieferlaenge"] != laenge else None)
            return z["preis"] * laenge / z["lieferlaenge"] + aufpreis_m * laenge / 1000, fehlt
    tonne = (k.werkstoffe.get(werkstoff) or {}).get("tonnenpreis")
    return _n(gb) * _n(tonne) / 1000 + aufpreis, None if _n(tonne) > 0 and gewicht is not None \
        else f"kein Materialpreis für {profil} / {werkstoff}"


def meterpreis(p, kopf, positionen, k, tabellen):
    """Materialpreis €/m einer Position für die Anzeige im Angebot: (berechnet, wirksam, fehlt). berechnet = aus
    Lieferlängen/Preise/Tonnenpreis + Aufpreis der Oberfläche für die wirksame Stangenlänge (ohne Preise von Hand),
    wirksam = womit die Stangen der Gruppe rechnen (höchster Preis von Hand einer Position der Gruppe, sonst
    berechnet). None ohne Profil, Werkstoff oder Stangenlänge und bei Zukaufteilen."""
    if ist_zukaufteil(p) or beigestellt(p) or _leer(p.get("profil_id")) or _leer(p.get("werkstoff_id")):
        return None, None, None
    gr = gruppe_von(p, kopf)
    laenge = gr[3]
    if not laenge or laenge <= 0:
        return None, None, None
    kgm = kg_je_m(p["profil_id"], p["werkstoff_id"], k)
    gewicht = laenge / 1000 * kgm if kgm is not None else None
    preis, fehlt = lieferstange_preis(gr, laenge, gewicht, kopf, [], k, tabellen, mehr=False)
    # 'Preis für … fehlt': €/Stange einer anderen Länge anteilig umgerechnet, als Richtwert anzeigen
    berechnet = preis * 1000 / laenge if preis > 0 and (fehlt is None or fehlt.startswith("Preis für")) else None
    wirksam = lieferstange_preis(gr, laenge, gewicht, kopf, positionen, k, tabellen, mehr=False)[0] * 1000 / laenge
    return berechnet, (wirksam if wirksam > 0 else None), fehlt


PREIS_ALT_MONATE = 6      # älter: Hinweis im Tooltip des Meterpreises


def preis_herkunft(p, kopf, k, tabellen, heute=None):
    """Woher der berechnete Meterpreis kommt, als Text für den Tooltip (Prüfbericht C-3): Zeile aus 'Lieferlängen'
    oder 'Preise' mit Preis, Gültig ab und Lieferant, sonst der Tonnenpreis des Werkstoffs; ist der Preis älter als
    PREIS_ALT_MONATE, steht ein Hinweis dabei. None ohne Profil, Werkstoff oder bei Zukaufteilen."""
    import datetime
    if ist_zukaufteil(p) or _leer(p.get("profil_id")) or _leer(p.get("werkstoff_id")):
        return None
    pid, wid, laenge = p["profil_id"], p["werkstoff_id"], gruppe_von(p, kopf)[3]
    z = next((r for r in lieferlaengen(pid, wid, k, tabellen, auto=False) if _n(r.get("laenge")) == _n(laenge)), None)
    quelle = "Lieferlängen"
    if z is None:
        z, quelle = preis_zeile(pid, wid, k, tabellen), "Preise"
    if z is None or _leer(z.get("basis")):
        t = (k.werkstoffe.get(wid) or {}).get("tonnenpreis")
        return f"Herkunft: Tonnenpreis {wid} {zahl(_n(t))} €/t (Werkstoffe)" if t else "Herkunft: kein Preis hinterlegt"
    text = f"Herkunft: {quelle} {zahl(_n(z.get('preis')))} {z.get('basis')}"
    if z.get("lieferant"):
        text += f", Lieferant {z['lieferant']}"
    try:
        ab = datetime.date.fromisoformat(str(z.get("gueltig_ab") or ""))
    except ValueError:
        return text + ", ohne Datum"
    text += f", gültig ab {ab.strftime('%d.%m.%Y')}"
    monate = ((heute or datetime.date.today()) - ab).days / 30.4
    if monate > PREIS_ALT_MONATE:
        text += f" – Achtung: über {PREIS_ALT_MONATE} Monate alt, Preis prüfen"
    return text


# ------------------------------------------------------------------ Lieferlängen (z. B. 6 m gegen 12 m)
# Je Gruppe (Profil + Werkstoff + Oberfläche + Stangenlänge des Angebots) werden die weiteren Lieferlängen aus den
# Stammdaten 'Lieferlängen' unter gleichen Bedingungen geplant (gleiche Teile, Endbeschnitt, Greiferrest,
# Schnittverlust) und mit der Stangenlänge des Angebots verglichen. Längen über der max. Stangenlänge der Maschine
# schneidet der Lieferant in Werkstücke (optimierung.zuschnitt); kein Werkstück ist länger als die Maschine laden
# kann. Reste sind Verschnitt, es entsteht kein Bestand.
LAENGE_STANDARD, LAENGE_ALTERNATIVE, LAENGE_KEIN_VORTEIL, LAENGE_ANGABEN_FEHLEN, LAENGE_NUR_ALTERNATIVE = (
    "standard", "alternative", "kein_vorteil", "angaben_fehlen", "nur_alternative")


def mm_text(w):
    from .stammdaten import zahl_als_text
    return zahl_als_text(w, 0)


def m_text(laenge):
    """12000 -> '12', 6500 -> '6,5'."""
    return zahl(laenge / 1000, 2)


def einstellung_wert(einst, name):
    """Wert einer Einstellung, fehlt sie (Tests, ältere Aufrufe), die Vorgabe."""
    from .stammdaten import EINSTELLUNG
    w = (einst or {}).get(name)
    return w if isinstance(w, (int, float)) and not isinstance(w, bool) else EINSTELLUNG[name].vorgabe


def laengen_schluessel(gr):
    """Schlüssel einer Gruppe (Profil, Werkstoff, Oberfläche, Stangenlänge[, Beistellung]) für die gespeicherte
    Längenwahl."""
    profil, werkstoff, ob, stange = gr[:4]
    bs = gr[4] if len(gr) > 4 and gr[4] else ""
    return f"{profil}|{werkstoff}|{ob or ''}|{int(stange) if float(stange).is_integer() else stange}" + \
        (f"|{bs}" if bs else "")


def lieferlaengen(profil_id, werkstoff_id, k, tabellen, einst=None, auto=True):
    """Gültige Zeilen aus 'Lieferlängen' (Prüfung OK) für Profil + Werkstoff, nach Länge. Ohne Zeile (auto): Profile
    mit Hüllkreis-Ø über der Einstellung laenge_auto_huellkreis (Vorgabe 70 mm, 0 = aus) gelten als in
    laenge_auto (Vorgabe 12.000 mm) lieferbar, Preis wie 'Preise' (Zeile mit automatisch=True)."""
    from .stammdaten import LIEFERLAENGEN, pruefen
    zeilen = [z for z in (tabellen or {}).get("lieferlaengen") or []
              if z.get("profil_id") == profil_id and z.get("werkstoff_id") == werkstoff_id
              and pruefen(LIEFERLAENGEN, z, k) == "OK"]
    if zeilen or not auto:
        return sorted(zeilen, key=lambda z: z["laenge"])
    grenze, laenge = _n(einstellung_wert(einst, "laenge_auto_huellkreis")), _n(einstellung_wert(einst, "laenge_auto"))
    pr = k.profile.get(profil_id)
    hk = huellkreis(pr) if pr else None
    if grenze > 0 and laenge > 0 and hk is not None and hk > grenze + EPS:
        return [dict(profil_id=profil_id, werkstoff_id=werkstoff_id, laenge=laenge, basis=None, preis=None,
                     automatisch=True)]
    return []


def laengen_der_gruppe(g, k, tabellen, einst=None):
    """Lieferbare Längen einer Gruppe: dict(ausgenommen, zeilen, alternativen=[Längen ≠ Stangenlänge des Angebots],
    basis_lieferbar). Ohne Zeilen in 'Lieferlängen' gilt wie bisher nur die Stangenlänge des Angebots, außer bei
    Profilen über dem Hüllkreis-Ø der Einstellung (dann zusätzlich 12 m, lieferlaengen); mit 'Lieferlängen
    vergleichen = nein' am Profil nur die Stangenlänge des Angebots (ausgenommen). Gibt es eigene Zeilen, ist die
    Stangenlänge des Angebots nur lieferbar, wenn sie dort oder als Liefer-Stangenlänge in 'Preise' steht."""
    zeilen = lieferlaengen(g.profil, g.werkstoff, k, tabellen, einst)
    if ((k.profile.get(g.profil) or {}).get("laengenvergleich") or "").strip().lower() == "nein":
        return dict(ausgenommen=True, zeilen=zeilen, alternativen=[], basis_lieferbar=True)
    if not zeilen:
        return dict(ausgenommen=False, zeilen=[], alternativen=[], basis_lieferbar=True)
    z = preis_zeile(g.profil, g.werkstoff, k, tabellen) if tabellen and "preise" in tabellen else None
    lieferbar = {r["laenge"] for r in zeilen} | ({z["lieferlaenge"]} if z and z.get("lieferlaenge") else set())
    return dict(ausgenommen=False, zeilen=zeilen, alternativen=sorted({r["laenge"] for r in zeilen} - {g.stange}),
                basis_lieferbar=g.stange in lieferbar or all(r.get("automatisch") for r in zeilen))


def variante_planen(g, laenge, m, saege, puffer=0):
    """Planung einer Gruppe mit Lieferlänge laenge. Ergebnis dict(laenge, zuschnitt, stangen, fehler):
    stangen = je Lieferstange [(Werkstücklänge, Folge)] (ohne Zuschnitt ein Werkstück = die ganze Stange),
    fehler = Text, wenn die Planung nicht ausführbar ist."""
    maxw = _n((m or {}).get("max_stange"))
    out = dict(laenge=laenge, zuschnitt=bool(maxw and laenge > maxw + EPS), stangen=[], fehler=None)
    if not out["zuschnitt"]:
        h = opt.replace(g, stange=laenge, teile=list(g.teile))
        if any(h.endbeschnitt + t.laenge + h.kerf > h.nutzbar_bis + EPS for t in h.teile):
            out["fehler"] = "Teil länger als Nutzlänge der Stange"
            return out
        folgen = opt.optimiere(h)
        opt.pruefe([h], [folgen])
        out["stangen"] = [[(laenge, f)] for f in folgen]
        return out
    minw = min(_n((m or {}).get("min_stange")), maxw)
    st = opt.zuschnitt(g, laenge, maxw, saege, minw, puffer)
    if st is None:
        out["fehler"] = f"Teil passt in kein Werkstück bis {mm_text(maxw)} mm"
        return out
    opt.pruefe_zuschnitt(g, st, laenge, maxw, saege, minw)
    out["stangen"] = st
    return out


def variante_kennzahlen(g, v, saege):
    """Kennzahlen einer geplanten Variante (zum Speichern im Ergebnis, ohne Kosten)."""
    nutz = sum(t.laenge for t in g.teile)
    n = len(v["stangen"])
    folgen = [f for s in v["stangen"] for _, f in s]
    zuschnitte = sum(len(s) - 1 + (1 if v["laenge"] - opt.zuschnitt_belegt([l for l, _ in s], saege) > saege + EPS
                                   else 0) for s in v["stangen"]) if v["zuschnitt"] else 0
    return dict(laenge=v["laenge"], zuschnitt=v["zuschnitt"], fehler=v["fehler"], lieferstangen=n,
                werkstuecke=len(folgen), zuschnitte=zuschnitte, material_mm=n * v["laenge"], nutz_mm=nutz,
                verschnitt_mm=n * v["laenge"] - nutz if n else 0, gemeinsam=sum(opt.gemeinsame_schnitte(f) for f in folgen),
                werkstueck_laengen=sorted({l for s in v["stangen"] for l, _ in s}, reverse=True) if v["zuschnitt"]
                else [])


def laengen_vergleich_gruppe(g, k, tabellen, m, saege, basis_plan=None, einst=None):
    """Vergleichsdaten einer Gruppe (ohne Kosten) oder None, wenn es für sie keine Lieferlängen gibt.
    basis_plan: schon gerechnete Folgen mit der Stangenlänge des Angebots (spart eine Optimierung).
    Ergebnis dict(schluessel, profil, werkstoff, oberflaeche, stange, ausgenommen, basis_lieferbar,
    varianten=[Kennzahlen, die erste ist die Stangenlänge des Angebots, falls lieferbar]) und die Pläne
    (Länge -> variante_planen) für die Übernahme."""
    info = laengen_der_gruppe(g, k, tabellen, einst)
    if not info["zeilen"] and not info["ausgenommen"]:
        return None, {}
    puffer = _n(einstellung_wert(einst, "zuschnitt_puffer"))
    plaene = {}
    if info["basis_lieferbar"]:
        plaene[g.stange] = (dict(laenge=g.stange, zuschnitt=False, stangen=[[(g.stange, f)] for f in basis_plan],
                                 fehler=None) if basis_plan is not None else variante_planen(g, g.stange, m, saege,
                                                                                             puffer))
    for laenge in info["alternativen"]:
        plaene[laenge] = variante_planen(g, laenge, m, saege, puffer)
    gr = (g.profil, g.werkstoff, g.oberflaeche, g.stange, g.beistellung)
    return dict(schluessel=laengen_schluessel(gr), profil=g.profil, werkstoff=g.werkstoff, oberflaeche=g.oberflaeche,
                stange=g.stange, ausgenommen=info["ausgenommen"], basis_lieferbar=info["basis_lieferbar"],
                naht=any(t.drehung == opt.FEST for t in g.teile),
                automatisch=bool(info["zeilen"]) and all(z.get("automatisch") for z in info["zeilen"]),
                max_werkstueck=(m or {}).get("max_stange"), saege=saege,
                varianten=[variante_kennzahlen(g, v, saege) for v in plaene.values()]), plaene


def je_werkstueck_kosten(kopf, k, tabellen, sn=False):
    """Kosten, die je geladenem Werkstück (Stange auf der Maschine) entstehen: Stangenwechsel der Maschine (sn=True:
    Stangenwechsel SN, Gruppe mit fester Schweißnaht-Lage) und Arbeitsschritte mit Zeit je Stange. Ergebnis (€, fehlt)."""
    zb = zeitbasis(kopf, k, tabellen)
    schritt = {z.get("schritt"): z for z in zb["schritte"]}
    _, s_sw = _schritt_satz(zb, schritt.get("Stangenwechsel"))
    wechsel = zb["maschine"].get("stangenwechsel")
    eur = stangenwechsel_zeiten(zb["maschine"])[1 if sn else 0] / 3600 * s_sw
    for z in zb["schritte"]:
        if z.get("schritt") not in SCHRITTE_FEST and (z.get("bezug") or "Teil") == "Stange":
            eur += _n(z.get("zeit")) / 3600 * _schritt_satz(zb, z)[1]
    return eur, None if wechsel is not None else "Stangenwechsel der Maschine fehlt"


def laengen_bewerten(vg, kopf, positionen, k, tabellen, einst):
    """Kosten je Variante und Empfehlung für eine Gruppe aus laengen_vergleich_gruppe. Gesamtkosten = Material
    (Lieferstangen × Preis der Lieferlänge) + je Werkstück (Stangenwechsel, Arbeitsschritte je Stange) + Zuschnitt
    beim Lieferanten (Anzahl × Kosten je Zuschnitt). Laserzeit, Teile und Schnittwege sind in allen Varianten gleich.
    Ein Reststückwert wird nicht angerechnet (keine Reststückverwaltung). Fehlende Angaben werden nie als 0
    bewertet: dann 'Vergleich nicht möglich'. Ergebnis dict(varianten=[Kennzahlen + material, werkstueck_kosten,
    zuschnitt_kosten, gesamt, fehlt], empfehlung, titel, begruendung, beste=Länge der empfohlenen Variante)."""
    gr = (vg["profil"], vg["werkstoff"], vg["oberflaeche"], vg["stange"])
    kgm = kg_je_m(vg["profil"], vg["werkstoff"], k)
    je_ws, fehlt_ws = je_werkstueck_kosten(kopf, k, tabellen, sn=vg.get("naht", False))
    je_zs = _n(einstellung_wert(einst, "zuschnitt_kosten"))
    varianten = []
    for v in vg["varianten"]:
        v = dict(v)
        preis, fehlt = lieferstange_preis(gr, v["laenge"], v["laenge"] / 1000 * kgm if kgm is not None else None,
                                          kopf, positionen, k, tabellen, einst)
        v["fehlt"] = [f for f in (fehlt,) if f]
        v["material"] = preis * v["lieferstangen"]
        v["werkstueck_kosten"] = je_ws * v["werkstuecke"]
        v["zuschnitt_kosten"] = je_zs * v["zuschnitte"]
        v["gesamt"] = v["material"] + v["werkstueck_kosten"] + v["zuschnitt_kosten"]
        v["verschnitt_anteil"] = v["verschnitt_mm"] / v["material_mm"] if v["material_mm"] else 0
        varianten.append(v)
    out = dict(vg, varianten=varianten)
    basis = next((v for v in varianten if v["laenge"] == vg["stange"]), None)
    alt = [v for v in varianten if v["laenge"] != vg["stange"] and not v["fehler"]]
    std = f"{m_text(vg['stange'])}-m-Stangen empfohlen"
    if vg["ausgenommen"]:
        return dict(out, empfehlung=LAENGE_STANDARD, titel=std, beste=vg["stange"],
                    begruendung="Profil ist vom Vergleich der Lieferlängen ausgenommen (Profile: Lieferlängen "
                                "vergleichen = nein).")
    if not alt:
        grund = ("keine weitere Lieferlänge hinterlegt" if not [v for v in varianten if v is not basis]
                 else "; ".join(f"{m_text(v['laenge'])} m: {v['fehler']}" for v in varianten if v["fehler"]))
        if basis is None:
            return dict(out, empfehlung=LAENGE_ANGABEN_FEHLEN, titel="Vergleich nicht möglich – Angaben fehlen",
                        beste=None, begruendung=f"{m_text(vg['stange'])} m ist nicht lieferbar und keine andere "
                                                f"Lieferlänge ist ausführbar ({grund}).")
        return dict(out, empfehlung=LAENGE_STANDARD, titel=std, beste=vg["stange"],
                    begruendung=f"Keine ausführbare andere Lieferlänge ({grund}).")
    # mehrere Längen: die günstigste; bei gleichen Kosten die mit weniger Material, dann die kürzere
    beste = min(alt, key=lambda v: (v["gesamt"], v["material_mm"], v["laenge"]))
    if basis and fehlt_ws and beste["werkstuecke"] != basis["werkstuecke"]:
        beste["fehlt"].append(fehlt_ws)      # verschieden viele Beladungen, aber Stangenwechsel nicht gepflegt
    if basis is None:
        if beste["fehlt"]:
            return dict(out, empfehlung=LAENGE_ANGABEN_FEHLEN, titel="Vergleich nicht möglich – Angaben fehlen",
                        beste=beste["laenge"], begruendung=f"{m_text(vg['stange'])} m ist nicht lieferbar; "
                                                           + "; ".join(beste["fehlt"]) + ".")
        return dict(out, empfehlung=LAENGE_NUR_ALTERNATIVE, beste=beste["laenge"],
                    titel=f"{m_text(vg['stange'])} m nicht lieferbar – {m_text(beste['laenge'])}-m-Stangen verwenden",
                    begruendung=f"Für {vg['profil']} / {vg['werkstoff']} ist {mm_text(vg['stange'])} mm nicht als "
                                f"Lieferlänge hinterlegt; es gibt keine {m_text(vg['stange'])}-m-Alternative.")
    fehlt = basis["fehlt"] + [f for f in beste["fehlt"] if f not in basis["fehlt"]]
    if fehlt:
        return dict(out, empfehlung=LAENGE_ANGABEN_FEHLEN, titel="Vergleich nicht möglich – Angaben fehlen",
                    beste=vg["stange"], begruendung="; ".join(fehlt) + ". Ohne diese Angaben ist kein belastbarer "
                                                                       "Kostenvergleich möglich.")
    ersparnis = basis["gesamt"] - beste["gesamt"]
    anteil = ersparnis / basis["gesamt"] if basis["gesamt"] > 0 else 0
    min_eur = _n(einstellung_wert(einst, "laenge_mindest_eur"))
    min_anteil = _n(einstellung_wert(einst, "laenge_mindest_anteil"))
    lb = m_text(beste["laenge"])
    zahlen = (f"{lb} m: {zahl(beste['gesamt'])} € statt {zahl(basis['gesamt'])} € "
              f"({beste['lieferstangen']} statt {basis['lieferstangen']} Stangen, {beste['werkstuecke']} statt "
              f"{basis['werkstuecke']} Beladungen"
              + (f", {beste['zuschnitte']} Zuschnitte beim Lieferanten" if beste["zuschnitte"] else "") + ")")
    grenzen = f"Grenzen {zahl(min_eur)} € und {zahl(100 * min_anteil, 1)} %"
    if ersparnis > EPS and ersparnis + EPS >= min_eur and anteil + 1e-9 >= min_anteil:
        return dict(out, empfehlung=LAENGE_ALTERNATIVE, titel=f"{lb}-m-Stangen wirtschaftlich sinnvoll",
                    beste=beste["laenge"], begruendung=f"{zahlen}; Ersparnis {zahl(ersparnis)} € "
                                                       f"({zahl(100 * anteil, 1)} %), {grenzen} erreicht.")
    if ersparnis > EPS:
        warum = f"Ersparnis {zahl(ersparnis)} € ({zahl(100 * anteil, 1)} %) unter den {grenzen}"
    elif ersparnis < -EPS:
        warum = f"{lb} m ist {zahl(-ersparnis)} € teurer"
    else:
        warum = "gleiche Gesamtkosten"
    return dict(out, empfehlung=LAENGE_KEIN_VORTEIL, titel=f"Kein ausreichender Kostenvorteil für {lb} m",
                beste=vg["stange"], begruendung=f"{zahlen}; {warum}.")


# ------------------------------------------------------------------ Kalkulation
def bohrbild_offen(p):
    """Gewinde-Vorschlag, Senkung oder Fließlochbohrung noch nicht bestätigt bzw. abgelehnt (bohrbild.py); ohne
    Bohrbild wie früher: Gewinde-Vorschlag da, Gewinde geprüft leer."""
    if not _leer(p.get("bohrbild")):
        from .bohrbild import lesen, offen
        return offen(lesen(p["bohrbild"])) > 0
    return not _leer(p.get("gewinde_vorschlag")) and _leer(p.get("gewinde"))


GEWINDE_TRENNER = re.compile(r";|,(?!\d)|\n")              # Semikolon, Komma (nicht zwischen Ziffern), Zeilenumbruch
GEWINDE_EINTRAG = re.compile(r"(\d+)\s*[x×X*]\s*(\S+)")


def gewinde_lesen(text, gewinde):
    """'Gewinde geprüft' lesen, z. B. '4xM6; 2xM8', '4 x M6, 2×M8'. Ergebnis: ({Gewinde: Anzahl je Teil}, [nicht
    erkannte Angaben]). Gewinde aus den Stammdaten (Groß-/Kleinschreibung egal); eine Angabe ohne Anzahl, mit
    Kommazahl oder mit einem Gewinde, das es nicht gibt, ist nicht erkannt und zählt nicht."""
    namen = {str(g.get("gewinde") or "").upper().replace(" ", ""): g.get("gewinde") for g in gewinde or ()}
    n, fehlt = {}, []
    for teil in GEWINDE_TRENNER.split(str(text or "")):
        teil = teil.strip()
        if not teil:
            continue
        m = GEWINDE_EINTRAG.fullmatch(teil)
        name = namen.get(m.group(2).upper()) if m else None
        if name is None:
            fehlt.append(teil)
        else:
            n[name] = n.get(name, 0) + float(m.group(1))
    return n, fehlt


def gewinde_anzahl(text, gewinde):
    """{Gewinde: Anzahl je Teil} aus 'Gewinde geprüft' (z. B. '4xM6; 2xM8'); nicht erkannte Angaben zählen nicht
    (gewinde_lesen meldet sie, der Status warnt)."""
    n = gewinde_lesen(text, gewinde)[0]
    return {g.get("gewinde"): n.get(g.get("gewinde"), 0.0) for g in gewinde}


def gewinde_unbekannt(text, gewinde):
    """Erste nicht erkannte Angabe in 'Gewinde geprüft' oder None."""
    fehlt = gewinde_lesen(text, gewinde)[1]
    return fehlt[0] if fehlt else None


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
KONTUR_FAKTOREN = (3.0, 8.0)        # Vorgabe klein bis / mittel bis [× Wandstärke] (Patrick 21.10.2026, B1a/B2a)
KONTUR_MIN_WAND = 0.7               # Kontur ab 0,7 × Wandstärke meist schneidbar, darunter prüfen (Patrick 21.10.2026)
MARKIERLOCH = 0.5                   # Markierloch Ø0,5 (Fließlochbohrung): gewollt kleiner als die Wand, keine Warnung
KONTUR_ZU_KLEIN = "Kontur kleiner als 0,7 × Wandstärke, Schneidbarkeit prüfen (ggf. nur gravieren und aufbohren)"
KLASSEN_FELDER = ("klein_n", "klein_mm", "mittel_n", "mittel_mm", "gross_n", "gross_mm")


def kontur_grenzen(m):
    """(klein bis, mittel bis) [mm] der Maschine; ohne gültige Werte die Vorgabe. Zweites Ergebnis: True = Vorgabe."""
    kl, mi = (m or {}).get("kontur_klein"), (m or {}).get("kontur_mittel")
    if isinstance(kl, (int, float)) and isinstance(mi, (int, float)) and 0 < kl < mi:
        return (float(kl), float(mi)), False
    return KONTUR_GRENZEN, True


def kontur_faktoren(m):
    """(klein bis, mittel bis) [× Wandstärke] der Maschine; ohne gültige Werte die Vorgabe 3 und 8."""
    kl, mi = (m or {}).get("kontur_klein_wand"), (m or {}).get("kontur_mittel_wand")
    if isinstance(kl, (int, float)) and isinstance(mi, (int, float)) and 0 < kl < mi:
        return float(kl), float(mi)
    return KONTUR_FAKTOREN


def kontur_regel(m, wand):
    """Regel der Konturklassen für eine Position: (klein bis, mittel bis [mm], klein bis, mittel bis [× Wand],
    Wandstärke); ohne Wandstärke nur die mm-Grenzen (klein bis, mittel bis)."""
    grenzen = kontur_grenzen(m)[0]
    if not isinstance(wand, (int, float)) or wand <= 0:
        return grenzen
    return grenzen + kontur_faktoren(m) + (round(float(wand), 2),)


def wand_position(p, k):
    """Wandstärke für Schneiddaten und Konturklassen einer Position (größte Wandstärke des Profils) oder None."""
    pr = k.profile.get(p.get("profil_id")) if k and not _leer(p.get("profil_id")) else None
    return wand_schneiden(pr) if pr else None


def kontur_klasse(groesse, regel):
    """0 = klein, 1 = mittel, 2 = groß: die strengere (kleinere, langsamere) Einteilung nach Hüllmaß (mm-Grenzen) und
    nach Hüllmaß ÷ Wandstärke (Faktoren, nur wenn die Regel eine Wandstärke hat), z. B. Ø 20 bei 8 mm Wand: 20 ≤ 3 × 8,
    also klein statt mittel. Genau auf der Grenze zählt die kleinere Klasse."""
    g = round(groesse, 2)   # Ø10 genau auf der Grenze zählt als klein
    c = 0 if g <= regel[0] else 1 if g <= regel[1] else 2
    if len(regel) >= 5 and regel[4] > 0:
        c = min(c, 0 if g <= round(regel[2] * regel[4], 2) else 1 if g <= round(regel[3] * regel[4], 2) else 2)
    return c


def grenzen_text(grenzen):
    """(10, 50) -> '10/50'; mit Faktoren und Wandstärke (10, 50, 3, 8, 4) -> '10/50; 3×/8× Wand 4'."""
    text = "/".join(zahl(g, 1) for g in grenzen[:2])
    if len(grenzen) >= 5:
        text += f"; {zahl(grenzen[2], 1)}×/{zahl(grenzen[3], 1)}× Wand {zahl(grenzen[4])}"
    return text


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
    """'8/45' -> (8.0, 45.0), '10/50; 3×/8× Wand 4' -> (10.0, 50.0, 3.0, 8.0, 4.0), sonst None."""
    zahlen = re.fullmatch(r"\s*([\d.,]+)\s*/\s*([\d.,]+)\s*(?:;\s*([\d.,]+)\s*×\s*/\s*([\d.,]+)\s*×\s*Wand\s*"
                          r"([\d.,]+)\s*)?", str(text or ""))
    if not zahlen:
        return None
    try:
        werte = [float(x.replace(",", ".")) for x in zahlen.groups() if x is not None]
    except ValueError:
        return None
    if not 0 < werte[0] < werte[1] or (len(werte) == 5 and not (0 < werte[2] < werte[3] and werte[4] > 0)):
        return None
    return tuple(werte)


def ende_vorschub(p, vorschuebe, grenzen):
    """Vorschub für eingesparte gemeinsame Schnitte: Klasse des Endes aus der Konturliste (gerades Ende zuerst, nur
    gerade Enden werden geteilt); ohne Enden in der Konturliste Vorschub groß. vorschuebe = (groß, mittel, klein)."""
    h, i_, j = vorschuebe
    enden = {a: g for a, g, _ in konturen_lesen(p.get("konturen"), True) if a}
    if not enden:
        return h
    seite = "A" if p.get("a_gerade") == "ja" or "E" not in enden else "E" if p.get("b_gerade") == "ja" else "A"
    c = kontur_klasse(enden.get(seite, next(iter(enden.values()))), grenzen_lesen(p.get("kontur_grenzen")) or grenzen)
    return (j, i_, h)[c]


def konturklassen(liste, grenzen):
    """Innenkonturen [(Hüllmaß, Schnittweg)] einteilen (kontur_klasse): klein ≤ klein bis < mittel ≤ mittel bis <
    groß, mit Wandstärke in der Regel (kontur_regel) zusätzlich nach Hüllmaß ÷ Wandstärke, die strengere Klasse gilt.
    Ergebnis: Felder klein_n, klein_mm, mittel_n, mittel_mm, gross_n, gross_mm (mm auf 0,1 gerundet)."""
    kl = [[0, 0.0], [0, 0.0], [0, 0.0]]
    for groesse, laenge in liste:
        c = kontur_klasse(groesse, grenzen)
        kl[c][0] += 1
        kl[c][1] += laenge
    out = {}
    for name, (n, lg) in zip(("klein", "mittel", "gross"), kl):
        out[f"{name}_n"], out[f"{name}_mm"] = n, round(lg, 1)
    return out


def konturklassen_neu(p, m, wand=None):
    """Neue Einteilung einer Position, deren Konturliste mit einer anderen Regel eingeteilt wurde als der aktuellen
    (Grenzen und Faktoren der Maschine, Wandstärke des Profils): dict mit den Klassenfeldern und kontur_grenzen,
    sonst None (keine Konturliste oder Regel gleich)."""
    if _leer(p.get("konturen")) or ist_zukaufteil(p):
        return None
    grenzen = kontur_regel(m, wand)
    if p.get("kontur_grenzen") == grenzen_text(grenzen):
        return None
    return dict(konturklassen(konturen_lesen(p["konturen"]), grenzen), kontur_grenzen=grenzen_text(grenzen))


def gross_rest(p):
    """Schneidweg mit Vorschub groß [mm]: Schneidweg − Konturen klein und mittel, nie unter 0 (große Konturen,
    Anfangs-/Endschnitt ohne Klasse und von Hand ergänzter Schneidweg)."""
    return max(0.0, _n(p.get("schneidweg")) - _n(p.get("klein_mm")) - _n(p.get("mittel_mm")))


def konturen_pruefen(p, wand=None):
    """Widerspruch zwischen Konturklassen und Schneidweg bzw. Innenkonturen oder eine Innenkontur kleiner als
    0,7 × Wandstärke (Text) oder None."""
    km = _n(p.get("klein_mm")) + _n(p.get("mittel_mm"))
    gelasert = set()        # in 'Bohrungen prüfen' abgelehnt: der Laser schneidet sie bewusst
    if not _leer(p.get("bohrbild")):
        from .bohrbild import ABGELEHNT, BOHREN, lesen
        gelasert = {round(float(z.get("d") or 0), 1) for z in lesen(p["bohrbild"])
                    if z.get("art") == BOHREN and z.get("status") == ABGELEHNT}
    if isinstance(wand, (int, float)) and wand > 0 and any(
            not a and MARKIERLOCH < round(g, 2) < round(KONTUR_MIN_WAND * wand, 2) and round(g, 1) not in gelasert
            for a, g, _ in konturen_lesen(p.get("konturen"), True)):
        return KONTUR_ZU_KLEIN
    if km <= 0 and _n(p.get("gross_mm")) <= 0:
        return None
    if not _leer(p.get("schneidweg")) and km > _n(p["schneidweg"]) + KONTUR_TOL:
        return "Konturen klein + mittel länger als Schneidweg"
    summe = km + _n(p.get("gross_mm"))
    if not _leer(p.get("innen")) and summe > _n(p["innen"]) + _n(p.get("a_schnitt")) + _n(p.get("b_schnitt")) \
            + KONTUR_TOL:
        return "Konturklassen länger als Innenkonturen + Anfangs-/Endschnitt"
    return None


# Einstiche je Anfangs- bzw. Endschnitt (Patrick 20.10.2026): Träger und U-Profil werden von 4 Seiten, das T-Profil
# von 2 Seiten angeschnitten; alle anderen Profile 1. Der STEP-Import zählt sie in die Einstiche der Position, ein
# gemeinsamer Schnitt spart sie alle.
EINSTICHE_ENDE = {"I-/H-Träger": 4, "U-Profil": 4, "T-Profil": 2}


def einstiche_ende(form):
    return EINSTICHE_ENDE.get(form, 1)


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
MASCHINE_ZEIT = ("stundensatz", "ruestzeit", "stangenwechsel", "stangenwechsel_sn")
SCHRITT_FELDER = ("schritt", "satz", "art", "parallel", "ruestzeit", "ruest_bezug", "zeit", "bezug")


def zeitbasis_aus(maschinen_id, k, tabellen):
    """Stundensätze und Zeitvorgaben aus den Stammdaten (für den Snapshot im Angebot):
    {maschine: {maschinen_id, stundensatz, ruestzeit, stangenwechsel, stangenwechsel_sn}, saetze: {ID: €/h}, schritte: [Zeile]}."""
    m = k.maschinen.get(maschinen_id) or {}
    return dict(maschine=dict({n: m.get(n) for n in MASCHINE_ZEIT}, maschinen_id=maschinen_id if m else None),
                saetze={z["satz_id"]: z.get("satz") for z in (tabellen.get("stundensaetze") or []) if z.get("satz_id")},
                schritte=[{n: z.get(n) for n in SCHRITT_FELDER} for z in (tabellen.get("arbeitsschritte") or [])
                          if z.get("schritt")])


def zeitbasis_abweichungen(zb, vorgabe):
    """Stundensätze und Zeitvorgaben eines Angebots (Snapshot zb), die von den aktuellen Stammdaten (vorgabe =
    zeitbasis_aus) abweichen, als Texte, z. B. 'Stundensatz Maschine 160 statt 150 €/h'. Ohne Snapshot: []."""
    if not isinstance(zb, dict):
        return []
    out = []
    m, mv = zb.get("maschine") or {}, vorgabe.get("maschine") or {}
    if m.get("maschinen_id") == mv.get("maschinen_id"):
        for n, titel, einheit in (("stundensatz", "Stundensatz Maschine", "€/h"), ("ruestzeit", "Rüstzeit Maschine", "min"),
                                  ("stangenwechsel", "Stangenwechsel", "s"),
                                  ("stangenwechsel_sn", "Stangenwechsel SN", "s")):
            if n == "stangenwechsel_sn" and n not in m:     # Snapshot vor 0.8.10: SN wie Stangenwechsel
                continue
            if _n(m.get(n)) != _n(mv.get(n)):
                out.append(f"{titel} {zahl(_n(m.get(n)))} statt {zahl(_n(mv.get(n)))} {einheit}")
    s, sv = zb.get("saetze") or {}, vorgabe.get("saetze") or {}
    for sid in sorted(set(s) | set(sv)):
        if _n(s.get(sid)) != _n(sv.get(sid)):
            out.append(f"Stundensatz {sid} {zahl(_n(s.get(sid)))} statt {zahl(_n(sv.get(sid)))} €/h")
    schr = {z.get("schritt"): z for z in zb.get("schritte") or ()}
    for z in vorgabe.get("schritte") or ():
        a = schr.get(z.get("schritt"))
        if a is None:
            continue
        for n, titel, einheit in (("ruestzeit", "Rüstzeit", "min"), ("zeit", "Zeit je Einheit", "s")):
            if _n(a.get(n)) != _n(z.get(n)):
                out.append(f"{z['schritt']}: {titel} {zahl(_n(a.get(n)))} statt {zahl(_n(z.get(n)))} {einheit}")
    return out


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
LIEFER_FELDER = ("profil_id", "werkstoff_id", "laenge", "basis", "preis", "gueltig_ab", "lieferant")
SCHNEID_FELDER = ("maschinen_id", "werkstoff_id", "kategorie", "gas", "wand_bis", "vorschub_gross", "vorschub_mittel",
                  "vorschub_klein", "einstechzeit", "vorschub_gravur")


# Einstellungen, die den Preis eines Angebots ändern und nicht (nur) im Angebotskopf stehen; die Kalkulationswerte des
# Angebots (angebot.KALKULATION) zählen mit, weil ältere Angebote ohne eigene Werte mit den Einstellungen rechnen.
EINST_FEST = ("zuschlag_material", "zuschlag_fertigung", "mindestpreis", "haendler_mehr_kurz", "haendler_mehr_lang",
              "haendler_mehr_grenze", "zuschlag_fremdleistung", "gewinn", "ruesten_abmessung", "pauschale_abmessung",
              "programmierung_teil", "angebotsaufschlag", "handling_beistellung")


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
    lief = [{n: z.get(n) for n in LIEFER_FELDER} for pid, wid in sorted(kombis, key=str)
            for z in lieferlaengen(pid, wid, k, tabellen, auto=False)]
    profile = sorted({p.get("profil_id") for p in positionen if not _leer(p.get("profil_id"))}, key=str)
    einst = tabellen.get("einstellungen") or {}
    return dict(datum=datum or datetime.date.today().isoformat(), maschine=m, preise=preise, schneiddaten=sd,
                lieferlaengen=lief,
                tonnenpreise={w: (k.werkstoffe.get(w) or {}).get("tonnenpreis") for w in sorted(werkstoffe, key=str)},
                aufpreise={o: (k.oberflaechen.get(o) or {}).get("aufpreis_m") for o in sorted(ofl)},
                # ab 0.7.0: Gewinde, preisrelevante Einstellungen, Profil- und Maschinenzeile (Prüfbericht B-4)
                gewinde=[dict(z) for z in tabellen.get("gewinde") or []],
                einstellungen={n: einst.get(n) for n in EINST_FEST if n in einst},
                profile={pid: dict(k.profile[pid]) for pid in profile if pid in k.profile},
                maschinen={m: dict(k.maschinen[m])} if m in k.maschinen else {})


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
    if "lieferlaengen" in pb:      # Snapshots vor den Lieferlängen: aktuelle Lieferlängen
        projektion = lambda zeilen: sorted(json.dumps({n: z.get(n) for n in LIEFER_FELDER}, sort_keys=True)
                                           for z in zeilen)
        betroffen = lambda z: _preis_schl(z) in fest
        aktuell = [z for z in tabellen.get("lieferlaengen") or [] if betroffen(z)]
        if projektion(aktuell) != projektion(pb["lieferlaengen"]):
            tab["lieferlaengen"] = [z for z in tabellen.get("lieferlaengen") or [] if not betroffen(z)] \
                + [dict(z) for z in pb["lieferlaengen"]]
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
    if "gewinde" in pb and _json_liste(pb["gewinde"]) != _json_liste(tabellen.get("gewinde") or []):
        tab["gewinde"] = [dict(z) for z in pb["gewinde"]]
    if pb.get("einstellungen"):
        e = dict(tabellen.get("einstellungen") or {})
        e.update(pb["einstellungen"])
        tab["einstellungen"] = e
    ws = {w: dict(z, tonnenpreis=pb["tonnenpreise"][w]) if w in (pb.get("tonnenpreise") or {}) else z
          for w, z in k.werkstoffe.items()}
    of = {o: dict(z, aufpreis_m=pb["aufpreise"][o]) if o in (pb.get("aufpreise") or {}) else z
          for o, z in k.oberflaechen.items()}
    pr = {pid: _fest(z, (pb.get("profile") or {}).get(pid)) for pid, z in k.profile.items()}
    ma = {m: _fest(z, (pb.get("maschinen") or {}).get(m)) if m == kopf.get("maschine") else z
          for m, z in k.maschinen.items()}
    return dataclasses.replace(k, werkstoffe=ws, oberflaechen=of, profile=pr, maschinen=ma), tab


def _json_liste(zeilen):
    return sorted(json.dumps(z, sort_keys=True, default=str) for z in zeilen)


def _fest(aktuell, fest):
    """Zeile aus dem Snapshot, wenn sie abweicht (gleiche Zeile bleibt die der Stammdaten), sonst die aktuelle."""
    if not isinstance(fest, dict) or json.dumps(fest, sort_keys=True, default=str) == \
            json.dumps(aktuell, sort_keys=True, default=str):
        return aktuell
    return dict(aktuell, **fest)


def einstellungen_fest(tabellen, einst):
    """Einstellungen eines Angebots: die festgeschriebenen (tabellen nach preisbasis_anwenden) gehen den aktuellen
    vor."""
    out = dict(einst)
    for n in EINST_FEST:
        if n in (tabellen.get("einstellungen") or {}):
            out[n] = tabellen["einstellungen"][n]
    return out


def _vergleich(pb):
    """Vergleichbarer Inhalt eines Snapshots (ohne Datum), Schneiddaten unabhängig von der Reihenfolge."""
    sd = sorted((json.dumps(z, sort_keys=True) for z in pb.get("schneiddaten") or []))
    lief = sorted(json.dumps(z, sort_keys=True) for z in pb.get("lieferlaengen") or [])
    return dict(maschine=pb.get("maschine"), preise={_preis_schl(z): z for z in pb.get("preise") or []}, schneiddaten=sd,
                tonnenpreise=pb.get("tonnenpreise") or {}, aufpreise=pb.get("aufpreise") or {}, lieferlaengen=lief,
                gewinde=_json_liste(pb.get("gewinde") or []), einstellungen=pb.get("einstellungen") or {},
                profile=pb.get("profile") or {}, maschinen=pb.get("maschinen") or {})


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
    if "lieferlaengen" in pb and alt["lieferlaengen"] != neu["lieferlaengen"]:
        out.append("Lieferlängen geändert")
    if "gewinde" in pb and alt["gewinde"] != neu["gewinde"]:
        out.append("Gewinde (Preis oder Zeit) geändert")
    from .stammdaten import EINSTELLUNG
    for n, w in alt["einstellungen"].items():
        eigen = isinstance(kopf.get(n), (int, float)) and not isinstance(kopf.get(n), bool)   # Wert im Angebot gilt
        if neu["einstellungen"].get(n) != w and n in EINSTELLUNG and not eigen:
            e = EINSTELLUNG[n]
            wert = (lambda x: f"{zahl(100 * _n(x))} %") if e.art == "anteil" else (lambda x: zahl(_n(x)))
            out.append(f"Einstellung {e.titel}: {wert(w)} → {wert(neu['einstellungen'].get(n))}")
    for pid, z in alt["profile"].items():
        if json.dumps(z, sort_keys=True, default=str) != json.dumps(neu["profile"].get(pid), sort_keys=True, default=str):
            out.append(f"Profil {pid} geändert")
    for m, z in alt["maschinen"].items():
        if json.dumps(z, sort_keys=True, default=str) != json.dumps(neu["maschinen"].get(m), sort_keys=True, default=str):
            out.append(f"Maschine {m} geändert")
    return out


def verschickt_abweichung(preisbasis, verkauf):
    """Text, wenn der Verkaufspreis netto vom zuletzt verschickten Angebots-PDF abweicht (Positionen oder Werte des
    Angebots geändert), z. B. 'Weicht vom verschickten Angebot (22.10.2026: 487,39 €) ab: +121,22 €'; sonst None."""
    v = (preisbasis or {}).get("verschickt") if isinstance(preisbasis, dict) else None
    if not isinstance(v, dict) or not isinstance(v.get("netto"), (int, float)) or verkauf is None:
        return None
    diff = round(verkauf - v["netto"], 2)
    if abs(diff) < 0.005:
        return None
    from .ausgabe import datum_text
    return (f"Weicht vom verschickten Angebot ({datum_text(v.get('datum'))}: {zahl(v['netto'], 2)} €) ab: "
            f"{'+' if diff > 0 else '−'}{zahl(abs(diff), 2)} €")


def freigabe_punkte(kopf, positionen, status, stand, summen, staffeln_veraltet=0, gueltig_bis=None, heute=None):
    """'Prüfen vor Freigabe' (Prüfbericht C-2, 3.4): alle offenen Punkte vor dem Angebots-PDF in einer Liste
    [(Art, Text)], Art FEHLER, WARNUNG oder HINWEIS. status = Status je Position, stand = Stand der Optimierung,
    summen = kalkulation(...)[1], gueltig_bis = Datum (verschickte Angebote), leer = alles erledigt."""
    import datetime
    out = []
    aktiv = [(p, st) for p, st in zip(positionen, status) if position_aktiv(p)]
    if not aktiv:
        out.append(("FEHLER", "keine Positionen"))
    if _leer(kopf.get("kunde")):
        out.append(("WARNUNG", "kein Kunde eingetragen"))
    if stand != "aktuell":
        out.append(("WARNUNG", "Schnittplan nicht aktuell: vor dem Angebot neu optimieren"))
    for art in ("FEHLER", "WARNUNG"):
        n = sum(1 for _, st in aktiv if str(st).startswith(art))
        if n:
            out.append((art, f"{n} Position{'en' if n > 1 else ''} mit {art} (siehe Meldungen)"))
    n = sum(1 for p, _ in aktiv if bohrbild_offen(p))
    if n:
        out.append(("WARNUNG", f"{n} Position{'en' if n > 1 else ''}: Bohrungen/Gewinde-Vorschlag ungeprüft"))
    if summen.get("fracht_fehler"):
        out.append(("WARNUNG", f"Fracht: {summen['fracht_fehler']}"))
    if staffeln_veraltet:
        out.append(("HINWEIS", f"{staffeln_veraltet} Staffelstufe(n) veraltet (werden vor dem PDF neu gerechnet)"))
    v = verschickt_abweichung(kopf.get("preisbasis"), summen.get("verkauf"))
    if v:
        out.append(("HINWEIS", v))
    if gueltig_bis and kopf.get("vorgang") == "Verschickt" and gueltig_bis < (heute or datetime.date.today()):
        out.append(("HINWEIS", f"Gültigkeit abgelaufen ({gueltig_bis.strftime('%d.%m.%Y')})"))
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


def _zusatz_umlegen(positionen, aktiv, laser, k, tabellen):
    """Zusatzarbeiten je Position (Teil von kalkulation): Beträge je Teil mit Mindestbetrag je Zusatzarbeit und
    Angebot (anteilig angehoben) und €/Angebot einmal je Angebot, auf die Teile umgelegt. Ergebnis {Index: [Einträge
    mit 'teil']}."""
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
    return zus


def _eingespart(stangen):
    """Je Teil-Referenz [Anzahl, eingespart mm, eingesparte Einstiche] aus dem Schnittplan (Teil von kalkulation)."""
    eingespart = {}
    for s in stangen:
        for t in s["teile"]:
            e = eingespart.setdefault(t["ref"], [0, 0.0, 0])
            e[0] += 1
            e[1] += t["eingespart_mm"]
            e[2] += t["eingespart_e"]
    return eingespart


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
    - Zukaufteile je Position (positionen.zukauf mit Preisstand): Verbrauch = Menge je Teil × Stückzahl (bzw. Menge
      je Satz × Sätze = Stückzahl / Stück je Satz), gleiche
      Artikel mit gleichem Preisstand werden im Angebot zu einer Bestellung zusammengefasst (Staffel, Mindestmenge,
      VPE und Bezugskosten einmal; zukauf.rechnen). Einstandspreis + Aufschlag nach der Regel des Artikels gehen
      je Teil ohne Zuschläge und ohne Gewinn in den Verkaufspreis ein (der Aufschlag ersetzt beides).
    - Skonto aus dem Angebotskopf (%) wird eingerechnet: Verkaufspreis = Preis ohne Skonto / (1 − Skonto), so bleibt
      nach Abzug des Skontos der Preis ohne Skonto.
    - Mindestpreis (Einstellung bzw. Angebot, netto): liegt der Verkaufspreis des Angebots darunter, werden alle
      Stückpreise anteilig angehoben (zeilen 'mindestpreis_teil', summen 'mindestpreis_anhebung')."""
    zb = zeitbasis(kopf, k, tabellen)
    satz_h = _n(zb["maschine"].get("stundensatz"))
    schritt = {z.get("schritt"): z for z in zb["schritte"]}
    satz = {n: _schritt_satz(zb, schritt.get(n)) for n in SCHRITTE_FEST}     # vom Programm gerechnete Schritte
    s_laser, s_gew, s_rm, s_ra, s_sw = (satz[n][1] for n in ("Laser schneiden", "Gewinde", "Rüsten Maschine",
                                                             "Rüsten je Abmessung", "Stangenwechsel"))
    stangen = ergebnis["stangen"] if ergebnis else []
    sw = stangen_werte(ergebnis, kopf, positionen, k, tabellen) if ergebnis else []
    zm, zf, gew = (_n(einstellungen.get(n)) for n in ("zuschlag_material", "zuschlag_fertigung", "gewinn"))
    ruest = _n(zb["maschine"].get("ruestzeit"))
    wechsel, wechsel_sn = stangenwechsel_zeiten(zb["maschine"])
    n_lad, n_sn = beladungen(stangen), beladungen_sn(stangen)
    wechsel_s = wechsel * (n_lad - n_sn) + wechsel_sn * n_sn         # Stangen mit fester Naht: Stangenwechsel SN
    aktiv = [i for i, p in enumerate(positionen) if position_aktiv(p)]
    # Zukaufteil-Positionen (z. B. Bleche) tragen nur ihre Zukaufteile und die Fracht; Rüsten, Pauschalen,
    # Programmierung, Angebotsaufschlag und Arbeitsschritte verteilen sich auf die Rohrlaserteile
    laser = [i for i in aktiv if not ist_zukaufteil(positionen[i])]
    zk_pos = [i for i in aktiv if ist_zukaufteil(positionen[i])]
    f8 = sum(_n(positionen[i].get("stueck")) for i in laser)
    if not f8:              # ohne Rohrlaserteile kein Rüsten der Maschine (Übersicht = Preis)
        ruest = 0
    f7 = ruest / 60 * s_rm + wechsel_s / 3600 * s_sw
    teile_abm = {}
    for i in laser:
        if _n(positionen[i].get("stueck")) > 0:
            pid = positionen[i]["profil_id"]
            teile_abm[pid] = teile_abm.get(pid, 0) + _n(positionen[i]["stueck"])
    ruest_abm_min = _n(einstellungen.get("ruesten_abmessung"))
    ruest_abm = ruest_abm_min / 60 * s_ra              # € je Abmessung
    pausch_abm = _n(einstellungen.get("pauschale_abmessung"))
    prog = _n(einstellungen.get("programmierung_teil"))   # € je Teil (Position mit Stückzahl), einmal je Angebot
    handling_kg = _n(einstellungen.get("handling_beistellung"))     # € je kg Kundenmaterial (Stangengewicht)
    zfl = _n(einstellungen.get("zuschlag_fremdleistung"))
    zus = _zusatz_umlegen(positionen, aktiv, laser, k, tabellen)
    skonto = min(max(_n(kopf.get("skonto")), 0), 50) / 100
    aufschlag = _n(einstellungen.get("angebotsaufschlag")) if f8 else 0
    werte = [position_werte(p, kopf, k, tabellen) if i in aktiv else None for i, p in enumerate(positionen)]
    fracht, fracht_text, fracht_fehler = (fracht_angebot.betrag_angebot(kopf, positionen, werte)
                                          if f8 or any(_n(positionen[i].get("stueck")) for i in zk_pos)
                                          else (0, "", ""))
    fracht = fracht or 0
    fracht_je, fracht_hinweis, fracht_umlage = fracht_angebot.anteile(positionen, werte, fracht,
                                                                      fracht_angebot.umlage(kopf))
    weitere = weitere_schritte(zb, f8, n_lad, teile_abm,
                               sum(1 for i in laser if _n(positionen[i].get("stueck")) > 0))
    zk_gruppen, zk_je = zukauf.rechnen([((i, n), e, zukauf.bezugsmenge(e, positionen[i], _n(positionen[i].get("stueck"))))
                                        for i in aktiv for n, e in enumerate(zukauf.eintraege(positionen[i]))])
    eingespart = _eingespart(stangen)
    zeilen = [None] * len(positionen)
    for i in aktiv:
        p = positionen[i]
        w = werte[i]
        c = _n(p.get("stueck"))
        if i in zk_pos:
            zeilen[i] = _zukaufteil_zeile(p, c, [zk_je[(i, n)] for n in range(len(zukauf.eintraege(p)))],
                                          fracht_je[i] if c else 0, skonto,
                                          satz_abweichung(p, positionen))
            continue
        gr = gruppe_von(p, kopf)
        d = sum(x["kosten"] for s, x in zip(stangen, sw) if gruppe_der_stange(s) == gr)
        # Kundenmaterial: Handling je kg der beigestellten Stangen der Gruppe (Prüfen, Einlagern, Transport)
        dh = handling_kg * sum(_n(x["gewicht"]) for s, x in zip(stangen, sw) if gruppe_der_stange(s) == gr) \
            if beigestellt(p) else 0.0
        gesamt = sum(_n(x.get("laenge")) * _n(x.get("stueck")) for x in positionen
                     if gruppe_von(x, kopf) == gr and not _leer(x.get("laenge")) and not _leer(x.get("stueck")))
        e = _n(w["laenge_gesamt"]) / gesamt if gesamt else 0
        f = d * e / c if c else 0
        hz = dh * e / c if c else 0
        sd, (h, i_, j, kv, l), mz = schneidzeit(p, kopf, w["wand_schneiden"], tabellen, k)
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
            nz = (60 * ein[1] / ende_vorschub(p, (h, i_, j), kontur_regel(maschine(kopf, k), w["wand_schneiden"]))
                  + ein[2] * einstiche_ende(w["profilform"]) * l) / c
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
        s_ = f * (1 + zm) + (qz + rz + az + ze + hz) * (1 + zf) + zfr * (1 + zfl)
        ohne = s_ * (1 + gew) + uz + zk_einst + zk_auf
        t_ = ohne / (1 - skonto)
        nicht = c - ein[0] if (stangen and not _leer(p.get("stueck"))) else None
        pr = pruefungen(p, w, positionen, tabellen.get("zusatzarbeiten") or (), tabellen["gewinde"])
        if _n(nicht) > 0:
            hinweis = "nicht vollständig eingeplant"
        elif d == 0 and not (beigestellt(p) and ein[0]):
            hinweis = "kein Schnittplan oder Preis"
        elif h is None and not manuell:
            hinweis = "keine Schneiddaten"
        elif "kontur" in pr:
            hinweis = pr["kontur"]
        elif "zusatz" in pr:
            hinweis = "Zusatzarbeit unbekannt"
        elif "gewinde" in pr:
            hinweis = f"Gewinde '{pr['gewinde']}' nicht erkannt"
        elif "satz" in pr:
            hinweis = pr["satz"]
        elif "bohrungen" in pr:
            hinweis = pr["bohrungen"]
        elif any(x["fehler"] for x in zk):
            hinweis = "Zukaufteil: " + next(x["fehler"] for x in zk if x["fehler"])
        else:
            hinweis = ""
        z.update(zeit_manuell="ja" if manuell else "", zeit_extra=zeit_extra, gewinde_preis=gp,
                 zusatz_eigen_teil=ze, zusatz_fremd_teil=zfr, zusatz_teil=ze + zfr, zusatz_position=(ze + zfr) * c, zusatzarbeiten=zus[i],
                 zusatz_text="; ".join(f"{e['name']} {zahl(e['menge'])} {e['einheit']}" for e in zus[i]))
        z.update(laser_schneiden_teil=_n(oz) / 3600 * s_laser, gewinde_teil=pz / 3600 * s_gew + gp,
                 gewinde_zeit_teil=pz / 3600 * s_gew, arbeit_teil=az,
                 zuschlag_material_teil=f * zm, zuschlag_fertigung_teil=(qz + rz + az + ze + hz) * zf,
                 handling_teil=hz, kundenmaterial="ja" if beigestellt(p) else "",
                 zuschlag_fremdleistung_teil=zfr * zfl, gewinn_teil=s_ * gew, skonto_teil=t_ - ohne)
        # Anteile je Teil (nur Aufteilung von rz und uz, für die Staffelpreise je Satz bzw. Position)
        z.update(ruesten_maschine_teil=(ruest / 60 * s_rm / f8 if f8 else 0),
                 stangenwechsel_teil=(wechsel_s / 3600 * s_sw / f8 if f8 else 0),
                 ruesten_abm_teil=(ruest_abm / n_abm if n_abm and c else 0),
                 pauschale_abm_teil=(pausch_abm / n_abm if n_abm and c else 0),
                 angebotsaufschlag_teil=(aufschlag / f8 if f8 and c else 0), programmierung_anteil=(prog / c if c else 0))
        z.update(laser_brutto=mz, einsparung=nz, laser_netto=oz, gewindezeit=pz, laser_teil=qz, ruesten_teil=rz,
                 zukauf_einstand_teil=zk_einst, zukauf_aufschlag_teil=zk_auf, zukauf_teil=zk_einst + zk_auf,
                 zukauf_fehlt=sum(1 for x in zk if x["fehler"]),
                 herstell_teil=s_, pauschalen_teil=uz, fracht_teil=fr, preis_teil=t_, preis_position=t_ * c, herstell_position=s_ * c,
                 material_position=f * c, laser_position=qz * c, hinweis=hinweis, eingeplant=ein[0],
                 nicht_eingeplant=nicht)
        zeilen[i] = z
    n_abm = len(teile_abm)
    # Mindestpreis netto je Angebot (nach Skonto, vor MwSt): liegt die Summe darunter, steigen alle Stückpreise
    # im gleichen Verhältnis, bis der Mindestpreis erreicht ist (einmal je Angebot, keine zusätzliche Position)
    mindest = _n(einstellungen.get("mindestpreis"))
    kalkuliert = sum(z["preis_position"] for z in zeilen if z)
    faktor = mindest / kalkuliert if mindest > 0 and 0 < kalkuliert < mindest else 1.0
    for z in zeilen:
        if z:
            alt = z["preis_teil"]
            z.update(preis_teil=alt * faktor, preis_position=alt * faktor * z["stueck"],
                     mindestpreis_teil=alt * (faktor - 1))

    def _summe(n):
        return sum(z[n] * z["stueck"] for z in zeilen if z)

    summen = dict(ruestzeit=ruest, stangenwechsel=wechsel, stangenwechsel_sn=wechsel_sn, stangenwechsel_s=wechsel_s,
                  stangen=len(stangen), beladungen=n_lad, beladungen_sn=n_sn, teile=f8,
                  abmessungen=n_abm, ruestzeit_abmessung=ruest_abm_min, ruesten=f7 + ruest_abm * n_abm,
                  pauschalen=pausch_abm * n_abm, angebotsaufschlag=aufschlag, fracht=fracht,
                  fracht_modus=fracht_angebot.modus(kopf), fracht_umlage=fracht_umlage, fracht_hinweis=fracht_hinweis,
                  fracht_text=fracht_text, fracht_fehler=fracht_fehler,
                  positionen=sum(1 for i in laser if _n(positionen[i].get("stueck")) > 0),
                  programmierung=prog * sum(1 for i in laser if _n(positionen[i].get("stueck")) > 0),
                  zukaufteile=sum(_n(positionen[i].get("stueck")) for i in zk_pos),
                  material=sum(z["material_position"] for z in zeilen if z),
                  laser=sum(z["laser_position"] for z in zeilen if z),
                  zusatz=sum(z["zusatz_position"] for z in zeilen if z),
                  handling_beistellung=sum(z.get("handling_teil", 0) * z["stueck"] for z in zeilen if z),
                  herstell=sum(z["herstell_position"] for z in zeilen if z),
                  verkauf=sum(z["preis_position"] for z in zeilen if z))
    # Einzelne Kostenarten (Material + Laser + Gewinde + Rüsten + Stangenwechsel + Zusatzarbeiten + Zuschläge
    # = Herstellkosten; Herstellkosten + Gewinn + Pauschalen + Programmierung + Aufschlag + Fracht + Zukaufteile
    # + Skonto = Verkaufspreis)
    summen.update(laser_schneiden=_summe("laser_schneiden_teil"), gewinde=_summe("gewinde_teil"),
                  ruesten_maschine=ruest / 60 * s_rm, ruesten_abmessungen=ruest_abm * n_abm,
                  stangenwechsel_kosten=wechsel_s / 3600 * s_sw,
                  zuschlag_material=_summe("zuschlag_material_teil"),
                  zuschlag_fertigung=_summe("zuschlag_fertigung_teil"),
                  zuschlag_fremdleistung=_summe("zuschlag_fremdleistung_teil"), gewinn=_summe("gewinn_teil"),
                  skonto=_summe("skonto_teil"), skonto_satz=100 * skonto, arbeitsschritte=_summe("arbeit_teil"),
                  zusatz_eigen=_summe("zusatz_eigen_teil"), zusatz_fremd=_summe("zusatz_fremd_teil"),
                  zukauf_einstand=_summe("zukauf_einstand_teil"), zukauf_aufschlag=_summe("zukauf_aufschlag_teil"),
                  zukauf_fehlt=sum(z["zukauf_fehlt"] for z in zeilen if z), zukauf=zk_gruppen)
    summen.update(verkauf_kalkuliert=kalkuliert, mindestpreis=mindest, mindestpreis_gilt=faktor > 1,
                  mindestpreis_anhebung=summen["verkauf"] - kalkuliert)
    summen.update(satz_laser=s_laser, satz_maschine=satz_h, zeitbasis_gespeichert=zb["gespeichert"])
    summen["zeiten"] = arbeitszeiten(zeilen, positionen, summen, zb, satz, weitere, n_lad)
    return zeilen, summen


def _zukaufteil_zeile(p, c, zk, fr, skonto, satz_text=None):
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
        hinweis = satz_text or ""
    null = dict.fromkeys(("handling_teil", "material_gruppe", "anteil", "material_teil", "zeit_extra", "gewinde_preis",
                          "zusatz_eigen_teil", "zusatz_fremd_teil", "zusatz_teil", "zusatz_position",
                          "laser_schneiden_teil", "gewinde_teil", "gewinde_zeit_teil", "arbeit_teil",
                          "zuschlag_material_teil", "zuschlag_fertigung_teil", "zuschlag_fremdleistung_teil",
                          "gewinn_teil", "einsparung", "gewindezeit", "laser_teil", "ruesten_teil", "herstell_teil",
                          "herstell_position", "material_position", "laser_position", "ruesten_maschine_teil",
                          "stangenwechsel_teil", "ruesten_abm_teil", "pauschale_abm_teil", "angebotsaufschlag_teil",
                          "programmierung_anteil"), 0.0)
    z = dict(null, pos=p.get("pos"), artikel=p.get("artikel"), stueck=c, wand_stufe=None, gas=None,
             vorschub_gross=None, vorschub_mittel=None, vorschub_klein=None, vorschub_gravur=None, einstechzeit=None,
             **{f"zeit_{n}": None for n in ZEITANTEILE}, mm_gross=None, mm_mittel=None, mm_klein=None,
             mm_gravur=None, einstiche_teil=None, zeit_manuell="", zusatzarbeiten=[], zusatz_text="", skonto_teil=t_ - ohne, laser_brutto=None,
             laser_netto=None, zukauf_einstand_teil=zk_einst, zukauf_aufschlag_teil=zk_auf,
             zukauf_teil=zk_einst + zk_auf, zukauf_fehlt=sum(1 for x in zk if x["fehler"]) + (0 if zk else 1),
             pauschalen_teil=fr, fracht_teil=fr, preis_teil=t_, preis_position=t_ * c, hinweis=hinweis,
             eingeplant=None, nicht_eingeplant=None, zukaufteil=True, kundenmaterial="")
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
    n_sn = summen.get("beladungen_sn", 0)
    ws = summen.get("stangenwechsel_s", n_stangen * summen["stangenwechsel"])
    formel = f"{n_stangen - n_sn} × {zahl(summen['stangenwechsel'], 0)} s" if n_stangen > n_sn or not n_sn else ""
    if n_sn:            # Stangen mit fester Schweißnaht-Lage: Stangenwechsel SN
        formel += (" + " if formel else "") + f"{n_sn} × {zahl(summen['stangenwechsel_sn'], 0)} s (SN)"
    out.append(zeile("Stangenwechsel", n_stangen, "Stangen", None, ws / n_stangen if n_stangen else summen["stangenwechsel"],
                     ws / 60, summen["stangenwechsel_kosten"], f"{formel} / 3600 × {zahl(sw, 2)} €/h",
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
    ("Zusatzarbeiten", "zusatz", False), ("Handling Kundenmaterial", "handling_beistellung", False),
    ("Zuschlag Material", "zuschlag_material", False), ("Zuschlag Fertigung", "zuschlag_fertigung", False),
    ("Zuschlag Fremdleistung", "zuschlag_fremdleistung", False), ("Herstellkosten", "herstell", True),
    ("Gewinn", "gewinn", False), ("Pauschale je Abmessung", "pauschalen", False),
    ("Programmierkosten", "programmierung", False), ("Angebotsaufschlag", "angebotsaufschlag", False),
    ("Fracht", "fracht", False), ("Zukaufteile (Einstand)", "zukauf_einstand", False),
    ("Aufschlag Zukaufteile", "zukauf_aufschlag", False), ("Skonto", "skonto", False),
    ("Anhebung auf Mindestpreis", "mindestpreis_anhebung", False), ("Verkaufspreis", "verkauf", True))


# Kostenübersicht im Angebot: Gruppen aus Kostenarten (Titel, Schlüssel, Summenzeile); jede Kostenart genau einmal
KOSTEN_GRUPPEN = (
    ("Material", ("material",), False), ("Laser schneiden", ("laser_schneiden",), False),
    ("Rüsten", ("ruesten_maschine", "ruesten_abmessungen", "stangenwechsel_kosten"), False),
    ("Zusätzliche Bearbeitung", ("gewinde", "arbeitsschritte", "zusatz", "handling_beistellung"), False),
    ("Zuschläge", ("zuschlag_material", "zuschlag_fertigung", "zuschlag_fremdleistung"), False),
    ("Herstellkosten", ("herstell",), True), ("Gewinn", ("gewinn",), False),
    ("Programmierkosten", ("programmierung",), False),
    ("Pauschalen und Aufschläge", ("pauschalen", "angebotsaufschlag", "fracht"), False),
    ("Zukaufteile", ("zukauf_einstand", "zukauf_aufschlag"), False),
    ("Skonto", ("skonto",), False), ("Mindestpreis", ("mindestpreis_anhebung",), False),
    ("Verkaufspreis", ("verkauf",), True))
assert sorted(n for _, ns, _ in KOSTEN_GRUPPEN for n in ns) == sorted(n for _, n, _ in KOSTENARTEN)


def kostenarten(summen, einst):
    """[(Bezeichnung mit Mengenangabe, Betrag, fett)] aller Kostenarten des Angebots, einzeln."""
    z = lambda w, st=1: zahl(w, st)
    zusatz = {
        "ruesten_maschine": f" ({z(summen['ruestzeit'])} min)",
        "ruesten_abmessungen": f" ({summen['abmessungen']} × {z(summen['ruestzeit_abmessung'])} min)",
        "stangenwechsel_kosten": f" ({summen['beladungen']} × {z(summen['stangenwechsel'])} s)",
        "zuschlag_material": f" ({z(100 * _n(einst.get('zuschlag_material')))} %)",
        "zuschlag_fertigung": f" ({z(100 * _n(einst.get('zuschlag_fertigung')))} %)",
        "zuschlag_fremdleistung": f" ({z(100 * _n(einst.get('zuschlag_fremdleistung')))} %)",
        "gewinn": f" ({z(100 * _n(einst.get('gewinn')))} %)",
        "skonto": f" ({z(summen.get('skonto_satz', 0))} % eingerechnet)",
        "pauschalen": f" ({summen['abmessungen']} × {z(_n(einst.get('pauschale_abmessung')), 2)} €)",
        "mindestpreis_anhebung": (f" (kalkuliert {z(summen.get('verkauf_kalkuliert', 0), 2)} €, Mindestpreis "
                                  f"{z(summen.get('mindestpreis', 0), 2)} € netto)" if summen.get("mindestpreis_gilt")
                                  else "")}
    return [(t + zusatz.get(n, ""), summen.get(n, 0.0), fett) for t, n, fett in KOSTENARTEN]


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
        schl = (gruppe_der_stange(s), s["stange"],
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
