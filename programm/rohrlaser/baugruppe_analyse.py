"""Baugruppen zerlegen (Importengine, Laserhub-Vergleich, Patrick 20.11.2026, Abschnitt 5 „Baugruppen automatisch
zerlegen“): je STEP-Datei eine vollständige Bauteilliste aus den Messwerten, ohne neue Messung.

1. Baugruppe analysieren: Baumstruktur der STEP (m["_struktur"] aus STEP-Import.exe, Knoten mit Menge und Eltern)
2. Einzelteile: jeder gemessene Körper
3. Rohrprofile: Kategorie je Teil aus bauteil_analyse
4. identische Teile gruppieren: dieselbe Regel wie der Prüfdialog (step.teile_gruppen; Lage im Raum egal)
5. Stückzahlen: Anzahl gleicher Körper (je Satz)
6. Einzelteilabmessungen und 7. Bearbeitungsmerkmale: bauteil_analyse.kennzahlen/merkmale
8. Schweißverbindungen und Überschneidungen: Nahtkandidaten der Messung (m["_nahtkandidaten"]: Teile, Stoßart, Länge)
9. vollständige Bauteilliste: positionen() mit Knoten, Varianten, Verbindungen, Materialbedarf je Profil
10. Übernahme in die Kalkulation macht weiter step.uebernehmen (Einzelpositionen bzw. Satz, Baugruppe mit Struktur) –
    hier wird nichts angelegt, die Liste ist die Kontrolle davor.

Varianten: Gruppen mit gleichem Profil (Form, Abmessungen, Wand), aber anderer Länge oder anderen Bearbeitungen –
das sind verschiedene Positionen, die beim Optimieren auf dieselbe Stange dürfen. Ohne Qt.
"""
from collections import Counter
from pathlib import Path

from . import bauteil_analyse as ba


def _z(m, n):
    try:
        return float(m.get(n) or 0)
    except (TypeError, ValueError):
        return 0.0


def profil_text(m):
    form = m.get("profilform") or ""
    a, b, s = _z(m, "abm_a"), _z(m, "abm_b"), _z(m, "wandstaerke")
    if not form or m.get("fehler"):
        return ""
    masse = f"{a:g}" + (f"x{b:g}" if b > 0 else "") + (f"x{round(s, 2):g}" if s > 0 else "")
    return f"{form} {masse}".replace(".", ",").strip()


def _profil_schluessel(m):
    return (m.get("profilform") or "", round(_z(m, "abm_a"), 1), round(_z(m, "abm_b"), 1),
            round(_z(m, "wandstaerke"), 2))


def _knoten_pfad(struktur, knoten_id):
    if not struktur or not knoten_id:
        return ""
    k = {x["id"]: x for x in struktur.get("knoten") or ()}
    namen, kid, schutz = [], knoten_id, 0
    while kid in k and schutz < 50:
        namen.append(str(k[kid].get("name") or kid))
        kid, schutz = k[kid].get("eltern"), schutz + 1
    return " › ".join(reversed(namen))


def datei_analyse(messwerte, datei):
    """Bauteilliste einer STEP-Datei (dict). messwerte = alle Messwerte des Imports (Indizes wie im Prüfdialog)."""
    from . import step
    ind = [i for i, m in enumerate(messwerte) if m.get("datei") == datei]
    if not ind:
        return None
    gruppen = {e: g for e, g in step.teile_gruppen(messwerte, True).items() if messwerte[e].get("datei") == datei}
    in_gruppe = {i for g in gruppen.values() for i in g}
    for i in ind:       # Teile ohne Gruppe (Fehler, Normteile, Gravurkörper …) einzeln
        if i not in in_gruppe:
            gruppen[i] = [i]
    struktur = next((messwerte[i].get("_struktur") for i in ind if messwerte[i].get("_struktur")), None)
    naht = next((messwerte[i].get("_nahtkandidaten") for i in ind if messwerte[i].get("_nahtkandidaten")), []) or []
    pos, nr_von = [], {}
    for nr, (erster, liste) in enumerate(sorted(gruppen.items()), start=1):
        m = messwerte[erster]
        a = ba.von(m)
        for i in liste:
            nr_von[i] = nr
        knoten = Counter(_knoten_pfad(struktur, messwerte[i].get("knoten")) for i in liste)
        schwach = ba.von(messwerte[min(liste, key=lambda i: ba.von(messwerte[i])["konfidenz"])])
        pos.append(dict(
            nr=nr, indizes=list(liste), anzahl=len(liste), datei=datei,
            bezeichnung=m.get("bauteil") or m.get("artikel") or Path(str(datei)).stem,
            kategorie=a["kategorie"], unterart=a.get("unterart") or "", rohrlaser=a.get("rohrlaser", False),
            profil=profil_text(m), laenge=round(_z(m, "laenge"), 1), konfidenz=schwach["konfidenz"],
            stufe=schwach["stufe"],
            merkmale=dict((a.get("kennzahlen") or {}).get("merkmale") or {}),
            komplexitaet=(a.get("kennzahlen") or {}).get("komplexitaet") or "",
            gewicht_stahl_kg=(a.get("kennzahlen") or {}).get("gewicht_stahl_kg") or 0.0,
            knoten={k: n for k, n in knoten.items() if k}, fehler=m.get("fehler") or ""))
    # Varianten: gleiches Profil, andere Länge oder andere Bearbeitung
    je_profil = {}
    for p in pos:
        m = messwerte[p["indizes"][0]]
        if p["rohrlaser"] and p["profil"]:
            je_profil.setdefault(_profil_schluessel(m), []).append(p)
    varianten = []
    for liste in je_profil.values():
        if len(liste) < 2:
            continue
        basis = max(liste, key=lambda p: p["anzahl"])
        for p in liste:
            if p is basis:
                continue
            unterschied = []
            if abs(p["laenge"] - basis["laenge"]) > 0.1:
                unterschied.append(f"Länge {p['laenge']:g} statt {basis['laenge']:g} mm")
            if p["merkmale"] != basis["merkmale"]:
                unterschied.append("andere Bearbeitungen")
            varianten.append(dict(nr=p["nr"], von=basis["nr"], profil=p["profil"],
                                  text="; ".join(unterschied) or "andere Enden/Konturen"))
    # Verbindungen (Schweißnähte, Überschneidungen) zwischen den Teilen
    verbindungen = []
    for n in naht:
        teile = [t for t in n.get("teile") or () if isinstance(t, int)]
        # teil_index der Messung ist die Körpernummer (1 …) innerhalb der Datei
        nrs = []
        for k in teile:
            i = next((j for j in ind if str(messwerte[j].get("koerper")) == str(k)), None)
            if i is not None and i in nr_von:
                nrs.append(nr_von[i])
        verbindungen.append(dict(positionen=nrs, stossart=n.get("stossart") or "", laenge=n.get("laenge_mm") or 0,
                                 status=n.get("status") or "", aufteilung=n.get("aufteilung") or ""))
    bedarf = {}
    for p in pos:
        if p["rohrlaser"] and p["profil"] and p["laenge"] > 0:
            bedarf[p["profil"]] = bedarf.get(p["profil"], 0.0) + p["laenge"] * p["anzahl"]
    kat = Counter()
    for p in pos:
        kat[p["kategorie"]] += p["anzahl"]
    n_rohr = sum(p["anzahl"] for p in pos if p["rohrlaser"])
    return dict(
        datei=datei, koerper=len(ind), verschiedene=len(pos), positionen=pos, varianten=varianten,
        verbindungen=verbindungen, struktur=struktur or None,
        # Rohrlaser-Baugruppe: mindestens zwei Rohrlaserteile, die sich berühren (Nahtkandidaten der Messung);
        # mehrere lose Teile in einer Datei sind nur „mehrteilig“ (nie automatisch Satz, Patrick 26.10.2026)
        baugruppe=len(ind) > 1, rohrlaser_baugruppe=n_rohr >= 2 and bool(naht),
        kategorien=dict(kat), materialbedarf_mm={k: round(v, 1) for k, v in sorted(bedarf.items())},
        naht_laenge=round(sum(_zf(v["laenge"]) for v in verbindungen), 1),
        gewicht_stahl_kg=round(sum(p["gewicht_stahl_kg"] * p["anzahl"] for p in pos), 2),
        zu_pruefen=sum(p["anzahl"] for p in pos if p["stufe"] != "sicher"))


def _zf(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def alle(messwerte):
    """Bauteilliste je Datei, in der Reihenfolge der Dateien."""
    ba.analysieren(messwerte)
    out = []
    for d in dict.fromkeys(m.get("datei") for m in messwerte):
        x = datei_analyse(messwerte, d)
        if x:
            out.append(x)
    return out


def zusammenfassung(dateien):
    """Gesamtzahlen über alle Dateien (Schrittleiste, Bericht)."""
    kat, zu, koerper, pos = Counter(), 0, 0, 0
    for d in dateien:
        kat.update(d["kategorien"])
        zu += d["zu_pruefen"]
        koerper += d["koerper"]
        pos += d["verschiedene"]
    return dict(dateien=len(dateien), koerper=koerper, verschiedene=pos, zu_pruefen=zu, kategorien=dict(kat),
                baugruppen=sum(1 for d in dateien if d["rohrlaser_baugruppe"]))


CSV_KOPF = ("Datei", "Pos.", "Bezeichnung", "Anzahl", "Kategorie", "Unterart", "Profil", "Länge [mm]",
            "Konfidenz [%]", "Stufe", "Bearbeitungen", "Komplexität", "Baugruppe", "Variante von")


def csv_zeilen(dateien):
    """Bauteilliste aller Dateien als Zeilen (für CSV, Semikolon, deutsche Zahlen)."""
    out = [list(CSV_KOPF)]
    for d in dateien:
        var = {v["nr"]: v for v in d["varianten"]}
        for p in d["positionen"]:
            out.append([d["datei"], p["nr"], p["bezeichnung"], p["anzahl"], p["kategorie"], p["unterart"], p["profil"],
                        f"{p['laenge']:g}".replace(".", ","), p["konfidenz"], p["stufe"],
                        ", ".join(f"{n}× {k}" for k, n in p["merkmale"].items() if k != ba.M_GERADE),
                        p["komplexitaet"], "; ".join(f"{k} ({n}×)" for k, n in p["knoten"].items()),
                        (f"Pos. {var[p['nr']]['von']}: {var[p['nr']]['text']}" if p["nr"] in var else "")])
    return out


def csv_schreiben(dateien, pfad):
    import csv
    with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f, delimiter=";").writerows(csv_zeilen(dateien))
    return pfad
