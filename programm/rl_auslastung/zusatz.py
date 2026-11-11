"""Zusatzschritte mit Zeit aus Anzahl (Plan 2.6, Patrick 11.11.2026). Ohne Qt.

Gewinde schneiden, Senken, Bohren, Nieten und Schweißen sind Arbeitsgänge an eigenen Arbeitsplätzen. Ihre Laufzeit
kennt niemand genau, wohl aber die Anzahl: 4 Gewinde M8 je Teil, 50 Teile. Aus der Tabelle der Richtzeiten (Zeit je
Stück, Rüsten je Auftrag, Handling je Teil) rechnet zeit():

    Laufzeit = Rüsten + Stückzahl × (Handling je Teil + Σ Anzahl je Teil × Zeit je Stück)

Verzinken und Pulverbeschichten sind Fremdarbeit mit fester Dauer in Arbeitstagen; Abholung und Anlieferung nur an
bestimmten Wochentagen (Einstellung fremd_tage, rechnung.planen). Die Startwerte sind Schätzungen (geschaetzt = 1);
vorschlaege() vergleicht sie mit den Fertigmeldungen (Z3)."""
import json
import re
import statistics

FREMD = ""                       # wie daten.FREMD: Arbeitsgang außer Haus
BEARBEITUNG, SCHWEISSEN = "Bearbeitung", "Schweißen"
# (Schritt, Art, Zeit je Stück in s, Rüsten je Auftrag in min, Handling je Teil in s, Arbeitsplatz, Arbeitstage,
# Stichwörter für Schnelleingabe und Excel)
STANDARD = (
    ("Gewinde schneiden", "M3 bis M6", 15, 10, 20, BEARBEITUNG, 0, "m3 m4 m5 m6"),
    ("Gewinde schneiden", "M8 bis M10", 20, 10, 20, BEARBEITUNG, 0, "m8 m10 gewinde"),
    ("Gewinde schneiden", "M12 bis M16", 35, 10, 20, BEARBEITUNG, 0, "m12 m14 m16"),
    ("Senken", "Kegelsenkung", 10, 5, 15, BEARBEITUNG, 0, "senk senken senkung"),
    ("Bohren", "bis Ø 10", 20, 10, 20, BEARBEITUNG, 0, "bohr bohren bohrung"),
    ("Bohren", "über Ø 10", 40, 10, 20, BEARBEITUNG, 0, "bohr>10 bohrung>10"),
    ("Nieten", "Blindniet", 8, 5, 15, BEARBEITUNG, 0, "niet niete nieten blindniet"),
    ("Nieten", "Blindnietmutter", 12, 5, 15, BEARBEITUNG, 0, "nietmutter blindnietmutter mutter"),
    ("Schweißen", "Heftpunkt", 10, 15, 60, SCHWEISSEN, 0, "heft heften heftpunkt"),
    ("Schweißen", "Naht bis 5 cm", 40, 15, 60, SCHWEISSEN, 0, "naht5 kurznaht"),
    ("Schweißen", "Naht bis 20 cm", 90, 15, 60, SCHWEISSEN, 0, "naht naht20"),
    ("Schweißen", "Naht über 20 cm (je 10 cm)", 45, 15, 60, SCHWEISSEN, 0, "naht10cm langnaht"),
    ("Verzinken", "", 0, 0, 0, FREMD, 5, "verzinken verzinkt zink"),
    ("Pulverbeschichten", "", 0, 0, 0, FREMD, 5, "pulvern pulver pulverbeschichten pulverbeschichtet"),
)
FELDER = ("schritt", "art", "je_s", "ruest_min", "handling_s", "platz", "tage", "stichwort")
MINDEST_MELDUNGEN = 3            # Z3: so viele Fertigmeldungen je Schritt und Art, bevor es einen Vorschlag gibt
SCHWELLE = 0.10                  # Z3: Vorschlag erst ab 10 % Abweichung
WOCHENTAGE = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")


def standard():
    """Die Startwerte als Liste von dicts (für die Datenbank)."""
    return [dict(zip(FELDER, z), geschaetzt=1, reihenfolge=i) for i, z in enumerate(STANDARD)]


def fremd(r):
    return (r.get("platz") or "") == FREMD


def positionen(text):
    """Gespeicherte Positionen eines Arbeitsgangs (JSON in gaenge.zusatz) als [dict(schritt, art, anzahl)]."""
    if isinstance(text, list):
        liste = text
    else:
        try:
            liste = json.loads(text or "[]")
        except (TypeError, ValueError):
            liste = []
    out = []
    for p in liste if isinstance(liste, list) else ():
        if isinstance(p, dict) and p.get("schritt"):
            try:
                anzahl = float(p.get("anzahl") or 0)
            except (TypeError, ValueError):
                anzahl = 0.0
            out.append(dict(schritt=str(p["schritt"]), art=str(p.get("art") or ""), anzahl=anzahl))
    return out


def _sek(s):
    s = int(round(s))
    if s < 60:
        return f"{s} s"
    return f"{s // 60} min" + (f" {s % 60} s" if s % 60 else "")


def _zahl(x):
    return f"{x:g}".replace(".", ",")


def zeit(pos, stueck, richtzeiten):
    """Laufzeit eines Zusatzschritts. pos: [dict(schritt, art, anzahl je Teil)] eines Schritts, stueck: Stückzahl,
    richtzeiten: Daten.richtzeiten(). Ergebnis: (Minuten, Arbeitstage, Rechenweg als Text). Fremdarbeit: (0, Tage,
    Text). Unbekannte Art: Fehler (ValueError)."""
    pos = [p for p in positionen(pos) if p["anzahl"] > 0 or fremd(_richt(p, richtzeiten) or {})]
    if not pos:
        raise ValueError("Bitte bei mindestens einer Art eine Anzahl eingeben.")
    stueck = max(1, int(stueck or 1))
    zeilen = [(p, _richt(p, richtzeiten)) for p in pos]
    fehlt = [f"{p['schritt']} {p['art']}".strip() for p, r in zeilen if r is None]
    if fehlt:
        raise ValueError(f"Keine Richtzeit für „{fehlt[0]}“ (Einstellungen → Zusatzschritte).")
    if all(fremd(r) for _p, r in zeilen):
        tage = max(int(r.get("tage") or 0) for _p, r in zeilen)
        return 0, tage, f"Fremdarbeit {tage} Arbeitstage"
    ruest = max(float(r["ruest_min"] or 0) for _p, r in zeilen)
    handling = max(float(r["handling_s"] or 0) for _p, r in zeilen)
    je_teil = sum(p["anzahl"] * float(r["je_s"] or 0) for p, r in zeilen)
    sekunden = ruest * 60 + stueck * (handling + je_teil)
    minuten = max(1, int(sekunden / 60 + 0.999))
    teile = " + ".join(f"{_zahl(p['anzahl'])} × {_sek(float(r['je_s'] or 0))}" + (f" ({p['art']})" if p["art"] else "")
                       for p, r in zeilen)
    text = (f"{_sek(ruest * 60)} Rüsten + {stueck} Teile × ({_sek(handling)} Handling + {teile})"
            + (" — Schätzwert" if any(r.get("geschaetzt") for _p, r in zeilen) else ""))
    return minuten, 0, text


def _richt(p, richtzeiten):
    return next((r for r in richtzeiten if r["schritt"] == p["schritt"] and (r["art"] or "") == (p["art"] or "")),
                None)


def schritte(richtzeiten):
    """Die Schritte in der Reihenfolge der Tabelle: [(Schritt, [Richtzeiten der Arten])]."""
    out = {}
    for r in richtzeiten:
        out.setdefault(r["schritt"], []).append(r)
    return list(out.items())


_STUECK = re.compile(r"^(\d+)\s*(stk\.?|stück|stueck|st\.)$", re.IGNORECASE)
_ANZAHL = re.compile(r"^(\d+(?:[.,]\d+)?)\s*[x×*]\s*(.+)$", re.IGNORECASE)


def stichwort(wort, richtzeiten):
    """Richtzeit zu einem Stichwort (M8, Niete, verzinken, Naht …) oder None."""
    w = wort.casefold().strip(" .,;")
    for r in richtzeiten:
        namen = {x.casefold() for x in (r.get("stichwort") or "").split()}
        namen |= {r["schritt"].casefold(), f"{r['schritt']} {r['art']}".strip().casefold()}
        if (r.get("art") or "").casefold():
            namen.add(r["art"].casefold())
        if w in namen:
            return r
    return None


def kurz_lesen(woerter, richtzeiten):
    """Schnelleingabe und Excel (Z4): Wörter wie „50 Stk“, „4xM8“, „2xNiete“, „verzinken“ herausziehen.
    Ergebnis: (Stückzahl oder None, {Schritt: [dict(schritt, art, anzahl)]} in Reihenfolge, übrige Wörter)."""
    stueck, gaenge, rest = None, {}, []
    i = 0
    woerter = list(woerter)
    while i < len(woerter):
        w = woerter[i]
        if i + 1 < len(woerter) and re.fullmatch(r"\d+", w) and _STUECK.fullmatch(w + " " + woerter[i + 1]):
            stueck = int(w)
            i += 2
            continue
        m = _STUECK.fullmatch(w)
        if m:
            stueck = int(m.group(1))
            i += 1
            continue
        m = _ANZAHL.fullmatch(w)
        r = stichwort(m.group(2), richtzeiten) if m else None
        if r is None and not m:
            r0 = stichwort(w, richtzeiten)
            r = r0 if r0 is not None and fremd(r0) else None
            anzahl = 1.0
        else:
            anzahl = float(m.group(1).replace(",", ".")) if m else 0.0
        if r is not None:
            liste = gaenge.setdefault(r["schritt"], [])
            alt = next((p for p in liste if p["art"] == (r["art"] or "")), None)
            if alt:
                alt["anzahl"] += anzahl
            else:
                liste.append(dict(schritt=r["schritt"], art=r["art"] or "", anzahl=anzahl))
            i += 1
            continue
        rest.append(w)
        i += 1
    return stueck, gaenge, rest


def gaenge_bauen(maschine, kalk_min, stueck, gefunden, richtzeiten):
    """Arbeitsgänge für einen neuen Auftrag: zuerst die Maschine mit ihrer Laufzeit, dann je Schritt ein
    Zusatzschritt (Reihenfolge der Tabelle). [dict(name, platz, kalk_min, tage, gleichzeitig, zusatz)]."""
    out = [dict(name=maschine, platz=maschine, kalk_min=kalk_min, tage=0, gleichzeitig=0, zusatz=[])]
    for schritt, _arten in schritte(richtzeiten):
        if schritt in gefunden:
            pos = gefunden[schritt]
            minuten, tage, _t = zeit(pos, stueck, richtzeiten)
            r = _richt(pos[0], richtzeiten)
            out.append(dict(name=schritt, platz=r["platz"], kalk_min=minuten, tage=tage, gleichzeitig=0, zusatz=pos))
    return out


def vorschlaege(gaenge_fertig, richtzeiten):
    """Z3: aus fertig gemeldeten Zusatzschritten mit nur einer Art die gemessene Zeit je Stück:
    je Stück = (Ist − Rüsten − Stückzahl × Handling) / (Stückzahl × Anzahl). gaenge_fertig: [dict(zusatz, ist_min,
    stueck)]. Ab MINDEST_MELDUNGEN Meldungen und SCHWELLE Abweichung: [dict(id, schritt, art, je_s, gemessen_s,
    anzahl)]."""
    messung = {}
    for g in gaenge_fertig:
        pos = [p for p in positionen(g.get("zusatz")) if p["anzahl"] > 0]
        if len(pos) != 1 or not g.get("ist_min"):
            continue
        r = _richt(pos[0], richtzeiten)
        if r is None or fremd(r):
            continue
        stueck = max(1, int(g.get("stueck") or 1))
        rein = g["ist_min"] * 60 - float(r["ruest_min"] or 0) * 60 - stueck * float(r["handling_s"] or 0)
        messung.setdefault(r["id"], []).append(max(1.0, rein / (stueck * pos[0]["anzahl"])))
    out = []
    for r in richtzeiten:
        werte = messung.get(r.get("id"), [])
        if len(werte) < MINDEST_MELDUNGEN:
            continue
        gemessen = statistics.median(werte)
        alt = float(r["je_s"] or 0)
        if alt <= 0 or abs(gemessen / alt - 1) >= SCHWELLE:
            out.append(dict(id=r["id"], schritt=r["schritt"], art=r["art"], je_s=alt, gemessen_s=round(gemessen),
                            anzahl=len(werte)))
    return out


def vorschlag_text(v):
    return (f"{v['schritt']} {v['art']}".strip() + f": gemessen {_sek(v['gemessen_s'])} statt {_sek(v['je_s'])} "
            f"je Stück ({v['anzahl']} Fertigmeldungen)")


def tage_lesen(text):
    """Einstellung fremd_tage ('0,2' = Mo, Mi) als Menge von Wochentagen; leer = jeder Arbeitstag."""
    out = set()
    for x in str(text or "").replace(";", ",").split(","):
        x = x.strip()
        if x.isdigit() and 0 <= int(x) <= 6:
            out.add(int(x))
    return out


def tage_text(menge):
    return ", ".join(WOCHENTAGE[i] for i in sorted(menge)) if menge else "jeden Arbeitstag"
