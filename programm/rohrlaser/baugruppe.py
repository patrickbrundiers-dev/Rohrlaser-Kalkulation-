"""Schweißbaugruppen: Struktur, Mengen, Schweißzeiten, Arbeitsgänge und Einmalkosten (Patrick 23.10.2026, Plan
Schweißbaugruppen, Freigabe „Alles a“).

Eine Schweißbaugruppe ist eine Position der Art 'Schweißbaugruppe' (angebot.BAUGRUPPE). Sie trägt in der Spalte
'baugruppe' (JSON) ihre Stammdaten, die Unterbaugruppen (Knoten), Arbeitsgänge und Nahtgruppen; ihre Stückzahl ist
die Anzahl Baugruppen. Die Einzelteile sind gewöhnliche Positionen (Rohrlaserteil, Zukaufteil), die ihr über die
Spalte 'bg_knoten' ('<Baugruppen-ID>' bzw. '<Baugruppen-ID>/<Knoten-ID>') zugeordnet sind, mit 'je_knoten' Stück je
direkt übergeordneter (Unter-)Baugruppe. So rechnen Einzelteile unverändert über Optimierung und
rechnen.kalkulation (keine Doppelrechnung); die Baugruppe rechnet nur ihre eigenen Leistungen dazu. Satz und
'Stück je Satz' der Teile folgen aus der Struktur (abgleich), damit Angebot, Staffeln und PDF die Baugruppe wie
einen Satz behandeln.

Rechenweg je Baugruppe (alle Beträge je Baugruppe, ungerundet):
  Menge eines Knotens  m(k) = Menge des Knotens × Menge seiner übergeordneten Knoten (Baugruppe selbst: 1)
  Nahtgruppe           Naht [m] = Länge je Naht × Anzahl × (2 bei beidseitig) / 1000
                       Lichtbogenzeit = Naht × Kennwert [min/m] × Faktor Schweißlage × Zugänglichkeit × Qualität
                       Schweißzeit = Lichtbogenzeit ÷ Lichtbogenzeitfaktor + Heftpunkte × Anzahl × Zeit je Heftpunkt
                       (oder die Zeit von Hand), × m(k); Kosten = Zeit × Stundensatz des Verfahrens
  Arbeitsgang          laufend = (Zeit je Einheit × Menge / 60 × Stundensatz + Kosten je Einheit × Menge) × m(k)
                       einmalig = Rüstzeit / 60 × Stundensatz + Einmalbetrag (Vorrichtung, Lehre, Programm …),
                       je Umlage: 'je Auftrag' ganz, 'anteilig' × Anteil %, 'wiederverwendbar' gar nicht; einmal je
                       Auftrag bzw. Staffelstufe, geteilt durch die Anzahl Baugruppen
  Fremdleistung        Arbeitsgänge mit fremd = ja zählen als Fremdleistung (Zuschlag Fremdleistung), alles andere als
                       Fertigung (Zuschlag Fertigung); danach Gewinn, Skonto, Mindestpreis wie jede Position
Kennwerte, Faktoren und Lichtbogenzeitfaktor kommen aus dem Stand der Nahtgruppe (beim Erfassen gemerkt), sonst
aus den Stammdaten; Stundensätze aus der Zeitbasis des Angebots. Nichts wird erfunden: fehlt ein Kennwert oder
Stundensatz, gibt es keine Zeit bzw. keine Kosten und eine Warnung.
"""
import json
import math
import uuid

from .angebot import ist_baugruppe

KNOTEN_TRENNER = "/"
UMLAGE_AUFTRAG, UMLAGE_ANTEILIG, UMLAGE_WIEDER = "je Auftrag", "anteilig", "wiederverwendbar"
UMLAGEN = (UMLAGE_AUFTRAG, UMLAGE_ANTEILIG, UMLAGE_WIEDER)
LAGEN = {"PA": "Wannenlage", "PB": "Horizontal (Kehlnaht)", "PC": "Querposition", "PD": "Horizontal-Überkopf",
         "PE": "Überkopf", "PF": "Steigend", "PG": "Fallend"}
STAMM_FELDER = (("kundenartikel", "Kundenartikelnummer"), ("zeichnung", "Zeichnungsnummer"),
                ("revision", "Revisionsstand"), ("beschreibung", "Beschreibung"), ("werkstoff", "Werkstoff"),
                ("oberflaeche", "Oberfläche / Beschichtung"), ("gewicht", "Gewicht [kg]"),
                ("abmessungen", "Abmessungen"), ("verfahren", "Fertigungsverfahren"), ("bemerkung", "Bemerkungen"),
                ("intern", "Interne Kalkulationshinweise"))


def _n(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _zahl(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def neue_id():
    """Kurze feste Kennung für Baugruppen, Knoten, Arbeitsgänge und Nähte (bleibt beim Kopieren gleich)."""
    return uuid.uuid4().hex[:10]


# ------------------------------------------------------------------ Lesen und Schreiben
def leer():
    """Neue, leere Baugruppe."""
    return dict(id=neue_id(), stamm={}, knoten=[], arbeitsgaenge=[], naehte=[])


def lesen(text):
    """Baugruppe aus der Spalte 'baugruppe' (JSON) mit allen Listen, sonst None (leer oder beschädigt)."""
    if not text:
        return None
    try:
        d = json.loads(text) if isinstance(text, str) else dict(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(d, dict) or not d.get("id"):
        return None
    for n in ("knoten", "arbeitsgaenge", "naehte"):
        d[n] = [x for x in d.get(n) or () if isinstance(x, dict)]
    d["stamm"] = d.get("stamm") if isinstance(d.get("stamm"), dict) else {}
    return d


def speichern(bg):
    return json.dumps(bg, ensure_ascii=False, sort_keys=True)


def zuordnung(p):
    """(Baugruppen-ID, Knoten-ID) eines Einzelteils; Knoten '' = direkt in der Baugruppe; (None, None) ohne."""
    t = str((p or {}).get("bg_knoten") or "").strip()
    if not t:
        return None, None
    bg, _, kn = t.partition(KNOTEN_TRENNER)
    return bg, kn


def zuordnung_text(bg_id, knoten_id=""):
    return bg_id + (KNOTEN_TRENNER + knoten_id if knoten_id else "")


def baugruppen(positionen):
    """{Baugruppen-ID: (Index, Baugruppe)} aller Positionen der Art Schweißbaugruppe mit lesbaren Daten."""
    out = {}
    for i, p in enumerate(positionen):
        if ist_baugruppe(p):
            bg = lesen(p.get("baugruppe"))
            if bg and bg["id"] not in out:
                out[bg["id"]] = (i, bg)
    return out


def name(p, bg=None):
    """Satzbezeichnung der Baugruppe: Bezeichnung, sonst Artikelnummer, sonst 'Baugruppe <Pos.>'."""
    for n in ("bezeichnung", "artikel"):
        t = str((p or {}).get(n) or "").strip()
        if t:
            return t
    return f"Baugruppe {(p or {}).get('pos') or ''}".strip()


# ------------------------------------------------------------------ Struktur
def knoten_map(bg):
    return {k["id"]: k for k in bg["knoten"] if k.get("id")}


def struktur_fehler(bg):
    """Erster Fehler der Knotenstruktur als Text (unbekannter übergeordneter Knoten, Zyklus, Menge < 1), sonst None."""
    km = knoten_map(bg)
    if len(km) != len(bg["knoten"]):
        return "Unterbaugruppe ohne oder mit doppelter Kennung"
    for k in bg["knoten"]:
        if not _zahl(k.get("menge")) or k["menge"] < 1:
            return f"Unterbaugruppe '{k.get('name') or k['id']}': Menge fehlt"
        weg, x = set(), k
        while x.get("parent"):
            if x["id"] in weg:
                return f"Unterbaugruppe '{k.get('name') or k['id']}' enthält sich selbst"
            weg.add(x["id"])
            x = km.get(x["parent"])
            if x is None:
                return f"Unterbaugruppe '{k.get('name') or k['id']}': übergeordnete Baugruppe fehlt"
    return None


def faktor(bg, knoten_id):
    """Menge eines Knotens je Baugruppe (Produkt der Mengen bis zur Baugruppe); '' = Baugruppe selbst = 1. None bei
    unbekanntem Knoten oder Fehler in der Struktur."""
    if not knoten_id:
        return 1
    if struktur_fehler(bg):
        return None
    km = knoten_map(bg)
    k, f = km.get(knoten_id), 1
    if k is None:
        return None
    while k is not None:
        f *= k["menge"]
        k = km.get(k.get("parent")) if k.get("parent") else None
    return f


def darf_unter(bg, knoten_id, neuer_parent):
    """True, wenn Knoten knoten_id unter neuer_parent ('' = Baugruppe) hängen darf, ohne dass ein Zyklus entsteht."""
    km = knoten_map(bg)
    x = neuer_parent
    while x:
        if x == knoten_id:
            return False
        x = (km.get(x) or {}).get("parent")
    return True


def teile(positionen, bg_id):
    """Indizes der Einzelteile einer Baugruppe."""
    return [i for i, p in enumerate(positionen) if not ist_baugruppe(p) and zuordnung(p)[0] == bg_id]


def soll_werte(positionen):
    """{Index: {satz, je_satz, stueck}}: Werte, die Baugruppen-Position und Einzelteile nach der Struktur haben müssen
    (Satz = Name der Baugruppe, Stück je Satz = Stück je Knoten × Menge der Knoten, Stückzahl = Stück je Satz ×
    Anzahl Baugruppen). Teile mit unbekannter Baugruppe oder fehlerhafter Struktur fehlen."""
    out = {}
    for bg_id, (i, bg) in baugruppen(positionen).items():
        p = positionen[i]
        satz = name(p, bg)
        anzahl = p.get("stueck") if _zahl(p.get("stueck")) else None
        out[i] = dict(satz=satz, je_satz=1)
        for j in teile(positionen, bg_id):
            q = positionen[j]
            f = faktor(bg, zuordnung(q)[1])
            je = q.get("je_knoten") if _zahl(q.get("je_knoten")) and q["je_knoten"] >= 1 else 1
            if f is None:
                continue
            je_satz = int(round(je * f))
            out[j] = dict(satz=satz, je_satz=je_satz, stueck=je_satz * anzahl if anzahl is not None else q.get("stueck"))
    return out


def abgleich(positionen):
    """Änderungen [(Index, Feld, Wert)], damit Satz, Stück je Satz und Stückzahl der Struktur folgen."""
    out = []
    for i, soll in sorted(soll_werte(positionen).items()):
        for feld, wert in soll.items():
            if positionen[i].get(feld) != wert:
                out.append((i, feld, wert))
    return out


def teil_pruefen(p, positionen):
    """Text, wenn ein Einzelteil einer Baugruppe zugeordnet ist, die es nicht gibt oder deren Struktur nicht passt."""
    bg_id, kn = zuordnung(p)
    if bg_id is None or positionen is None:
        return None
    alle = baugruppen(positionen)
    if bg_id not in alle:
        return "Baugruppe der Zuordnung fehlt"
    bg = alle[bg_id][1]
    if kn and kn not in knoten_map(bg):
        return "Unterbaugruppe der Zuordnung fehlt"
    soll = soll_werte(positionen).get(next((j for j, q in enumerate(positionen) if q is p), -1))
    if soll and (str(p.get("satz") or "").strip() != soll["satz"] or p.get("je_satz") != soll["je_satz"]
                 or p.get("stueck") != soll["stueck"]):
        return "Stückzahl passt nicht zur Baugruppe (neu abgleichen)"
    return None


# ------------------------------------------------------------------ Schweißkennwerte
def _faktor_zeile(tabellen, art, wert):
    if not wert:
        return None
    return next((z for z in tabellen.get("schweiss_faktoren") or ()
                 if z.get("art") == art and str(z.get("wert") or "").strip() == str(wert).strip()), None)


def kennwert(verfahren, nahtart, mass, tabellen):
    """Kennwertzeile (kleinstes 'bis' ≥ Nahtgröße) für Verfahren und Nahtart, sonst None."""
    if not _zahl(mass):
        return None
    kand = [z for z in tabellen.get("schweiss_kennwerte") or ()
            if z.get("verfahren") == verfahren and z.get("nahtart") == nahtart and _zahl(z.get("mass_bis"))
            and _zahl(z.get("min_m")) and z["mass_bis"] >= mass - 1e-9]
    return min(kand, key=lambda z: z["mass_bis"]) if kand else None


def naht_stand(naht, tabellen, datum=None):
    """Kennwerte einer Nahtgruppe aus den Stammdaten, zum Merken in der Nahtgruppe ('stand'): Lichtbogenzeit je m,
    Faktoren, Lichtbogenzeitfaktor, Zeit je Heftpunkt, Stundensatz-ID und ob ein Wert nur Richtwert ist."""
    import datetime
    v = next((z for z in tabellen.get("schweissverfahren") or () if z.get("verfahren") == naht.get("verfahren")), None)
    kw = kennwert(naht.get("verfahren"), naht.get("nahtart"), naht.get("mass"), tabellen)
    fz = {art: _faktor_zeile(tabellen, art, naht.get(feld))
          for art, feld in (("Schweißlage", "lage"), ("Zugänglichkeit", "zugang"), ("Qualität", "qualitaet"))}
    richt = [z for z in [v, kw, *fz.values()] if z and z.get("status") == "Richtwert"]
    return dict(verfahren=bool(v), min_m=kw["min_m"] if kw else None, mass_bis=kw["mass_bis"] if kw else None,
                lichtbogen=(v or {}).get("lichtbogen"), heft_s=(v or {}).get("heft_s"), satz_id=(v or {}).get("satz_id"),
                f_lage=_n((fz["Schweißlage"] or {}).get("faktor")) or 1.0,
                f_zugang=_n((fz["Zugänglichkeit"] or {}).get("faktor")) or 1.0,
                f_qualitaet=_n((fz["Qualität"] or {}).get("faktor")) or 1.0,
                richtwert=bool(richt), datum=datum or datetime.date.today().isoformat())


def naht_rechnen(naht, tabellen, saetze):
    """Zeit und Kosten einer Nahtgruppe je Stück ihres Knotens: dict(naht_m, lichtbogen_min, heft_min, zeit_min,
    satz, kosten, hand, richtwert, fehlt). Stand der Nahtgruppe, sonst Stammdaten. fehlt = Grund, warum keine Zeit
    berechnet werden kann (dann Zeit 0, außer von Hand)."""
    st = naht.get("stand") if isinstance(naht.get("stand"), dict) else naht_stand(naht, tabellen)
    anzahl = _n(naht.get("anzahl")) if _zahl(naht.get("anzahl")) else 1
    seiten = 2 if naht.get("beidseitig") else 1
    naht_m = _n(naht.get("laenge")) * anzahl * seiten / 1000
    satz_id = st.get("satz_id")
    satz = saetze.get(satz_id) if satz_id else None
    out = dict(naht_m=naht_m, lichtbogen_min=0.0, heft_min=0.0, zeit_min=0.0, satz_id=satz_id, satz=satz, kosten=0.0,
               hand=False, richtwert=bool(st.get("richtwert")), fehlt=None)
    if _zahl(naht.get("zeit_hand")):
        out.update(zeit_min=naht["zeit_hand"], hand=True, richtwert=False)
    else:
        if not st.get("verfahren"):
            out["fehlt"] = f"Verfahren '{naht.get('verfahren') or ''}' unbekannt"
        elif not _zahl(st.get("min_m")):
            out["fehlt"] = (f"kein Kennwert für {naht.get('verfahren')} {naht.get('nahtart') or ''} "
                            f"{_text(naht.get('mass'))} mm")
        elif not _zahl(st.get("lichtbogen")) or st["lichtbogen"] <= 0:
            out["fehlt"] = f"Lichtbogenzeitfaktor fehlt ({naht.get('verfahren')})"
        else:
            lb = naht_m * st["min_m"] * _n(st.get("f_lage") or 1) * _n(st.get("f_zugang") or 1) \
                * _n(st.get("f_qualitaet") or 1)
            heft = _n(naht.get("heftpunkte")) * anzahl * _n(st.get("heft_s")) / 60
            out.update(lichtbogen_min=lb, heft_min=heft, zeit_min=lb / (st["lichtbogen"] / 100) + heft)
    if out["zeit_min"] and not _zahl(satz):
        out["fehlt"] = out["fehlt"] or f"Stundensatz '{satz_id or ''}' fehlt"
    out["kosten"] = out["zeit_min"] / 60 * _n(satz)
    return out


def _text(w):
    if not _zahl(w):
        return ""
    return f"{w:g}".replace(".", ",")


# ------------------------------------------------------------------ Arbeitsgänge
def arbeitsgang_rechnen(ag, saetze):
    """Kosten eines Arbeitsgangs je Stück seines Knotens (laufend) und einmal je Auftrag (vor Umlage):
    dict(satz, laufend_min, laufend, einmal_min, einmal, umlage_faktor, fremd, fehlt)."""
    satz = ag.get("satz") if _zahl(ag.get("satz")) else saetze.get(ag.get("satz_id")) if ag.get("satz_id") else None
    menge = _n(ag.get("menge")) if _zahl(ag.get("menge")) else 1
    laufend_min = _n(ag.get("zeit_min")) * menge
    einmal_min = _n(ag.get("ruest_min"))
    umlage = ag.get("umlage") or UMLAGE_AUFTRAG
    f = {UMLAGE_WIEDER: 0.0, UMLAGE_ANTEILIG: _n(ag.get("anteil")) / 100}.get(umlage, 1.0)
    fehlt = None
    if (laufend_min or einmal_min) and not _zahl(satz):
        fehlt = f"Stundensatz fehlt ({ag.get('name') or 'Arbeitsgang'})"
    return dict(satz=satz, laufend_min=laufend_min,
                laufend=laufend_min / 60 * _n(satz) + _n(ag.get("kosten_einheit")) * menge,
                einmal_min=einmal_min, einmal=einmal_min / 60 * _n(satz) + _n(ag.get("einmal_eur")),
                umlage=umlage, umlage_faktor=f, fremd=bool(ag.get("fremd")), fehlt=fehlt)


# ------------------------------------------------------------------ Baugruppe rechnen
def rechnen(p, tabellen, saetze, anzahl=None):
    """Eigene Leistungen einer Baugruppen-Position je Baugruppe. anzahl = Baugruppen im Auftrag (Stufe), leer = Stückzahl
    der Position. Ergebnis: dict(eigen, fremd, einmal, einmal_gesamt, zeit_min, schweiss_min, naht_m {Verfahren: m},
    zeilen [{art, id, name, knoten, faktor, zeit_min, kosten, einmal, fremd, text}], fehler, warnungen, richtwert).
    eigen/fremd enthalten den umgelegten Einmalanteil (einmal)."""
    bg = lesen(p.get("baugruppe"))
    n = anzahl if anzahl is not None else p.get("stueck")
    n = n if _zahl(n) and n > 0 else 0
    out = dict(eigen=0.0, fremd=0.0, einmal=0.0, einmal_gesamt=0.0, zeit_min=0.0, schweiss_min=0.0, naht_m={},
               zeilen=[], fehler=None, warnungen=[], richtwert=False, wiederverwendbar=0)
    if bg is None:
        out["fehler"] = "Baugruppendaten fehlen"
        return out
    sf = struktur_fehler(bg)
    if sf:
        out["fehler"] = sf
        return out
    km = knoten_map(bg)

    def kname(kid):
        return (km.get(kid) or {}).get("name") or "" if kid else ""

    for nt in bg["naehte"]:
        f = faktor(bg, nt.get("knoten") or "")
        if f is None:
            out["warnungen"].append(f"Nahtgruppe {nt.get('nr') or ''}: Unterbaugruppe fehlt".replace("  ", " "))
            continue
        r = naht_rechnen(nt, tabellen, saetze)
        if r["fehlt"]:
            out["warnungen"].append(f"Nahtgruppe {nt.get('nr') or ''}: {r['fehlt']}".replace("  ", " "))
        out["richtwert"] |= r["richtwert"]
        v = nt.get("verfahren") or "?"
        out["naht_m"][v] = out["naht_m"].get(v, 0.0) + r["naht_m"] * f
        out["zeit_min"] += r["zeit_min"] * f
        out["schweiss_min"] += r["zeit_min"] * f
        out["eigen"] += r["kosten"] * f
        out["zeilen"].append(dict(art="Naht", id=nt.get("id"), name=f"Nahtgruppe {nt.get('nr') or ''}".strip(),
                                  knoten=kname(nt.get("knoten")), faktor=f, zeit_min=r["zeit_min"] * f,
                                  kosten=r["kosten"] * f, einmal=0.0, fremd=False, werte=r))
    for ag in bg["arbeitsgaenge"]:
        f = faktor(bg, ag.get("knoten") or "")
        if f is None:
            out["warnungen"].append(f"{ag.get('name') or 'Arbeitsgang'}: Unterbaugruppe fehlt")
            continue
        r = arbeitsgang_rechnen(ag, saetze)
        if r["fehlt"]:
            out["warnungen"].append(r["fehlt"])
        if r["umlage"] == UMLAGE_WIEDER and r["einmal"]:
            out["wiederverwendbar"] += 1
        einmal = r["einmal"] * r["umlage_faktor"]
        out["einmal_gesamt"] += einmal
        je = r["laufend"] * f + (einmal / n if n else 0.0)
        out["zeit_min"] += r["laufend_min"] * f + (r["einmal_min"] * r["umlage_faktor"] / n if n else 0.0)
        out["einmal"] += einmal / n if n else 0.0
        out["fremd" if r["fremd"] else "eigen"] += je
        out["zeilen"].append(dict(art="Arbeitsgang", id=ag.get("id"), name=ag.get("name") or "Arbeitsgang",
                                  knoten=kname(ag.get("knoten")), faktor=f, zeit_min=r["laufend_min"] * f,
                                  kosten=r["laufend"] * f, einmal=einmal, fremd=r["fremd"], werte=r))
    return out


def status(p, w, positionen=None):
    """Status einer Baugruppen-Position (wie rechnen.status): FEHLER, WARNUNG, HINWEIS oder OK."""
    if not _zahl(p.get("stueck")) or p["stueck"] < 1:
        return "FEHLER: Stückzahl fehlt (Anzahl Baugruppen)"
    bg = lesen(p.get("baugruppe"))
    if bg is None:
        return "FEHLER: Baugruppendaten fehlen"
    sf = struktur_fehler(bg)
    if sf:
        return "FEHLER: " + sf
    for liste, titel in ((bg["naehte"], "Nahtgruppe"), (bg["arbeitsgaenge"], "Arbeitsgang")):
        for x in liste:
            for feld in ("laenge", "anzahl", "mass", "zeit_hand", "heftpunkte", "zeit_min", "ruest_min", "menge",
                         "kosten_einheit", "einmal_eur", "satz", "anteil"):
                if _zahl(x.get(feld)) and x[feld] < 0:
                    return f"FEHLER: {titel} {x.get('nr') or x.get('name') or ''}: negativer Wert".replace("  ", " ")
    r = rechnen(p, (w or {}).get("bg_tabellen") or {}, (w or {}).get("saetze") or {})
    if r["fehler"]:
        return "FEHLER: " + r["fehler"]
    if r["warnungen"]:
        return "WARNUNG: " + r["warnungen"][0]
    if positionen is not None:
        if not teile(positionen, bg["id"]):
            return "WARNUNG: Baugruppe ohne Einzelteile"
        for i, q in enumerate(positionen):
            if not ist_baugruppe(q) and zuordnung(q)[0] == bg["id"] and teil_pruefen(q, positionen):
                return f"WARNUNG: Pos. {q.get('pos') or i + 1}: {teil_pruefen(q, positionen)}"
        doppelt = doppelt_schweissen(p, positionen)
        if doppelt:
            return "WARNUNG: " + doppelt
    if not bg["naehte"] and not bg["arbeitsgaenge"]:
        return "HINWEIS: keine Nahtgruppen und Arbeitsgänge"
    if r["richtwert"]:
        return "HINWEIS: Schweißzeit aus ungeprüften Richtwerten"
    if r["wiederverwendbar"]:
        return "HINWEIS: wiederverwendbare Vorrichtung nicht berechnet"
    return "OK"


def doppelt_schweissen(p, positionen):
    """Text, wenn die Baugruppe Nahtgruppen hat und eines ihrer Teile zusätzlich die Zusatzarbeit Schweißen trägt."""
    bg = lesen(p.get("baugruppe"))
    if not bg or not bg["naehte"]:
        return None
    from .stammdaten import ZUSATZ_SCHWEISSEN
    for j in teile(positionen, bg["id"]):
        q = positionen[j]
        try:
            liste = json.loads(q.get("zusatz") or "[]")
        except (TypeError, ValueError):
            continue
        if any(isinstance(e, dict) and e.get("name") == ZUSATZ_SCHWEISSEN for e in liste):
            return f"Pos. {q.get('pos') or j + 1} hat zusätzlich Zusatzarbeit Schweißen (doppelt?)"
    return None


def text_angebot(p):
    """Zeile der Baugruppen-Position im Angebot (Satzteil): 'Schweißen und Fertigung der Baugruppe'."""
    bg = lesen(p.get("baugruppe")) or {}
    st = bg.get("stamm") or {}
    zeilen = ["Schweißen und Fertigung der Baugruppe"]
    if st.get("zeichnung"):
        zeilen.append(f"Zeichnung {st['zeichnung']}" + (f" Rev. {st['revision']}" if st.get("revision") else ""))
    return "\n".join(zeilen)


# ------------------------------------------------------------------ Richtwerte (Knopf 'Richtwerte laden')
# Herleitung statt Erfahrungszahlen: Lichtbogenzeit = Nahtvolumen × Dichte ÷ Abschmelzleistung. Nahtquerschnitt
# Kehlnaht = a² × 1,1 (Nahtüberhöhung), Stumpf-/Ecknaht (V-Naht 60°, Spalt 1,5 mm, ab 3 mm) = (t² × tan 30° +
# 1,5 × t) × 1,1, bis 3 mm I-Naht = 1,5 × t × 1,1. Abschmelzleistungen sind übliche Handwerte je Verfahren und
# müssen an die eigene Fertigung angepasst werden (Status 'Richtwert').
RICHT_VERFAHREN = (
    # Verfahren, Bezeichnung, Abschmelzleistung kg/h, Dichte kg/dm³, Lichtbogenzeitfaktor %, Heftpunkt s
    ("MAG", "Metall-Aktivgas (Stahl), Hand", 3.5, 7.85, 35, 8),
    ("MIG", "Metall-Inertgas (Aluminium), Hand", 2.0, 2.70, 30, 8),
    ("WIG", "Wolfram-Inertgas, Hand", 0.8, 7.85, 30, 10),
    ("E-Hand", "Lichtbogenhandschweißen mit Stabelektrode", 1.5, 7.85, 25, 12),
    ("Roboter MAG", "Roboterschweißen MAG", 5.0, 7.85, 70, 0),
)
RICHT_MASSE = {"Kehlnaht": (2, 3, 4, 5, 6, 8, 10), "Stumpfnaht": (2, 3, 4, 5, 6, 8, 10, 12, 15, 20),
               "Ecknaht": (2, 3, 4, 5, 6, 8, 10)}
RICHT_FAKTOREN = (("Schweißlage", "PA", 1.0), ("Schweißlage", "PB", 1.0), ("Schweißlage", "PC", 1.2),
                  ("Schweißlage", "PD", 1.4), ("Schweißlage", "PE", 1.6), ("Schweißlage", "PF", 1.3),
                  ("Schweißlage", "PG", 1.1), ("Zugänglichkeit", "gut", 1.0), ("Zugänglichkeit", "eingeschränkt", 1.25),
                  ("Zugänglichkeit", "schlecht", 1.6), ("Qualität", "normal", 1.0), ("Qualität", "erhöht", 1.2),
                  ("Qualität", "Sichtnaht", 1.4))


def nahtquerschnitt(nahtart, mass):
    """Nahtquerschnitt [mm²] für die Richtwerte (siehe oben)."""
    if nahtart == "Kehlnaht":
        return mass * mass * 1.1
    if mass <= 3:
        return 1.5 * mass * 1.1
    return (mass * mass * math.tan(math.radians(30)) + 1.5 * mass) * 1.1


def richtwerte():
    """Zeilen für Schweißverfahren, Schweiß-Kennwerte und Schweiß-Faktoren mit Status 'Richtwert'."""
    verfahren, kennwerte, faktoren = [], [], []
    for v, bez, kg_h, dichte, lb, heft in RICHT_VERFAHREN:
        verfahren.append(dict(verfahren=v, bezeichnung=bez, satz_id="Schweißen", lichtbogen=lb, heft_s=heft or None,
                              aktiv="ja", status="Richtwert",
                              bemerkung=f"Richtwert: Abschmelzleistung {_text(kg_h)} kg/h, Lichtbogenzeit {lb} % "
                                        "der Arbeitszeit, bitte an die eigene Fertigung anpassen"))
        for art, masse in RICHT_MASSE.items():
            for m in masse:
                kg_m = nahtquerschnitt(art, m) * dichte / 1000          # mm² × kg/dm³ / 1000 = kg je m
                kennwerte.append(dict(verfahren=v, nahtart=art, mass_bis=m, min_m=round(kg_m / kg_h * 60, 2),
                                      status="Richtwert",
                                      bemerkung=f"hergeleitet: {_text(round(nahtquerschnitt(art, m), 1))} mm² × "
                                                f"{_text(dichte)} kg/dm³ ÷ {_text(kg_h)} kg/h"))
    for art, wert, f in RICHT_FAKTOREN:
        faktoren.append(dict(art=art, wert=wert, faktor=f, status="Richtwert",
                             bemerkung=(LAGEN.get(wert, "") + ", " if wert in LAGEN else "") + "Richtwert"))
    return dict(schweissverfahren=verfahren, schweiss_kennwerte=kennwerte, schweiss_faktoren=faktoren)


SCHLUESSEL = {"schweissverfahren": ("verfahren",), "schweiss_kennwerte": ("verfahren", "nahtart", "mass_bis"),
              "schweiss_faktoren": ("art", "wert")}


def richtwerte_fehlend(tabellen):
    """Richtwert-Zeilen, die in den Stammdaten noch fehlen (gleicher Schlüssel = vorhanden, wird nie geändert)."""
    out = {}
    for name, zeilen in richtwerte().items():
        da = {tuple(z.get(k) for k in SCHLUESSEL[name]) for z in tabellen.get(name) or ()}
        out[name] = [z for z in zeilen if tuple(z.get(k) for k in SCHLUESSEL[name]) not in da]
    return out


def arbeitsgang_vorlage(z):
    """Arbeitsgang aus einer Zusatzarbeit der Stammdaten (Katalog): Name, Stundensatz-ID oder eigener Satz, Zeit je
    Einheit in min, Kosten je Einheit (Festpreis bei €/Stück, €/kg, €/m², €/m, dazu Material; die Menge in kg, m² bzw.
    m trägt man im Arbeitsgang ein), Einmalbetrag bei €/Angebot, Fremdleistung. Werte, die die Zusatzarbeit nicht hat,
    bleiben leer; s/Stück (Laserzeit) gibt es an der Baugruppe nicht."""
    from .stammdaten import ZEITEINHEITEN
    ag = dict(id=neue_id(), name=z.get("name"), umlage=UMLAGE_AUFTRAG, fremd=z.get("fremd") == "ja" or None,
              vorlage=z.get("name"))
    if z.get("satz_id"):
        ag["satz_id"] = z["satz_id"]
    elif _zahl(z.get("satz")):
        ag["satz"] = z["satz"]
    if _zahl(z.get("zeit")) and z["zeit"] > 0:
        ag["zeit_min"] = round(z["zeit"] * ZEITEINHEITEN.get(z.get("zeit_einheit") or "s", 1) / 60, 4)
    preis = z.get("preis") if _zahl(z.get("preis")) else 0
    kosten = (preis if z.get("art") in ("€/Stück", "€/kg", "€/m²", "€/m") else 0) + _n(z.get("material"))
    if kosten:
        ag["kosten_einheit"] = kosten
    if z.get("art") == "€/Angebot" and preis:
        ag["einmal_eur"] = preis
    return {k: v for k, v in ag.items() if v is not None}
