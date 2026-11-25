"""Rolle und Schneidbarkeit je Kontur (Master-Auftrag Patrick 25.11.2026 „Abwicklungskern für den STEP-/CAD-Import
grundlegend erweitern“, Abschnitte 4 und 5; Plan https://claude.ai/artifact/DpkYezVhUe2Kioe7ZL7CC7, Paket P2).

Kein zweites Erkennungssystem: die Rolle wird nur aus den Messwerten einer Kontur abgeleitet (eine Zeile von
konturen_liste der STEP-Messung, step_geometrie). Es wird nichts neu gemessen und kein Wert geändert; Schnittlänge,
Laserzeit und Preis bleiben, wie sie sind. Die Rolle erklärt, WO am Rohr die Kontur liegt und WAS sie ist, die Stufe,
wie sicher das Programm ist, dass der Laser sie genau so schneidet.

Rollen (ROLLEN):
- Anfangsschnitt  – Ende A (gerade, Gehrung, schräg, Freiform)
- Endeschnitt     – Ende B
- Anschlusskontur – Ende, das an ein Gegenrohr anschließt (Sattel/Fischmaul, Rohrverbindung)
- Innenkontur     – geschlossene Kontur in einer Wand (Bohrung, Langloch)
- Durchbruch      – Kontur, die mit einer zweiten auf der Gegenseite einen Durchgang bildet (gleiche Achse, gleicher Ø)
- Ausschnitt      – rechteckige oder freie Öffnung mit erkannter Grundform
- Freiformkontur  – Kontur ohne erkannte Grundform (nur Schnittlänge aus dem STEP)
- nicht eindeutig – Kontur, deren Lage oder Art die Messung nicht bestimmen konnte

Merkmale, die nicht durchgeschnitten werden (Gravur, Sackbohrung, Fließloch, Fräsung), bekommen eine Rolle nur zur
Anzeige und schnitt=False; sie laufen nicht in den Schneidweg und zählen in zusammenfassung() nicht mit.

Schneidbarkeit (STUFEN, Abschnitt 5 des Auftrags):
1 eindeutig      – Grundform erkannt, durchgehend, Schnittlänge gemessen, Erkennung sicher
2 wahrscheinlich – Form aus den Flächen bekannt (Sattel gegen Gegenrohr, 3D-Bohrung, erkannte Sonderkontur) oder
                   Erkennung des Teils nicht ganz sicher
3 problematisch  – Kontur ohne Grundform, Fase am Ende, Kontur über mehrere Wände, Öffnung kleiner als die Wand
4 nicht sicher   – keine Schnittlänge, Form nicht erkannt, Werte fehlen

Handkorrektur: steht in der Kontur "rolle_hand" (eine der ROLLEN), gilt diese Rolle (hand=True, Grund nennt die
gemessene); die Stufe bleibt die gemessene, denn die Hand ändert nicht, wie gut der Laser die Kontur schneidet.

Problematische Konturen werden nie still übergangen: jede Stufe hat einen Grund (Text), Stufe 3 und 4 erscheinen in der
Importanalyse als „prüfen“.

Ohne Qt.
"""
import math

ANFANG, ENDE, ANSCHLUSS, INNEN, DURCHBRUCH, AUSSCHNITT, FREIFORM, UNKLAR = (
    "Anfangsschnitt", "Endeschnitt", "Anschlusskontur", "Innenkontur", "Durchbruch", "Ausschnitt", "Freiformkontur",
    "nicht eindeutig")
ROLLEN = (ANFANG, ENDE, ANSCHLUSS, INNEN, DURCHBRUCH, AUSSCHNITT, FREIFORM, UNKLAR)

EINDEUTIG, WAHRSCHEINLICH, PROBLEMATISCH, NICHT_SICHER = 1, 2, 3, 4
STUFEN = {EINDEUTIG: "eindeutig", WAHRSCHEINLICH: "wahrscheinlich", PROBLEMATISCH: "problematisch",
          NICHT_SICHER: "nicht sicher"}
PRUEFEN_AB = PROBLEMATISCH          # ab dieser Stufe: in der Importanalyse „bitte prüfen“

ENDEN = ("Ende A", "Ende B")
GERADE_FORMEN = ("gerade", "Gehrung", "Schrägschnitt zweiachsig")
GRUNDFORMEN = ("Bohrung", "Langloch", "Rechteckausschnitt", "Rechteck")
OHNE_SCHNITT = ("Gravur", "Sackbohrung", "Innenmerkmal", "Fließloch")
OHNE_SCHNITT_TEXT = {"Gravur": "Gravur, nicht durchgeschnitten", "Sackbohrung": "nicht durchgehend, nicht gelasert",
                     "Fließloch": "Fließlochbohrung (Flowdrill), nicht im Schneidweg"}
SCHRAEG_3D = 0.5                    # Grad, wie step_geometrie.SCHRAEG_3D: ab hier ist eine Bohrung ein 3D-Schnitt


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _ergebnis(rolle, stufe, grund, schnitt=True):
    return dict(rolle=rolle, stufe=stufe, stufe_text=STUFEN[stufe], grund=grund, schnitt=schnitt)


def rolle(d, wand=None, sicher=True):
    """Rolle und Schneidbarkeit einer Kontur (dict aus konturen_liste). wand: Wandstärke des Teils in mm (für „Öffnung
    kleiner als die Wand“), sicher: Erkennung der Konturen des Teils sicher (Spalte sicherheit, konturen=sicher).
    Ergebnis: dict(rolle, stufe 1 … 4, stufe_text, grund, schnitt). Wirft nie."""
    try:
        r = _rolle(d or {}, _f(wand), sicher)
        hand = (d or {}).get("rolle_hand")
        if hand in ROLLEN and hand != r["rolle"]:
            # Handkorrektur (Viewer, Rechtsklick „Rolle ändern“): Rolle wie gesetzt, Stufe bleibt die gemessene
            r = dict(r, rolle=hand, hand=True, grund=f"Rolle von Hand gesetzt (gemessen: {r['rolle']}); {r['grund']}")
        return r
    except Exception as e:  # noqa: BLE001 – unerwartete Werte: nie still übergehen, als „nicht sicher“ melden
        return _ergebnis(UNKLAR, NICHT_SICHER, f"Kontur nicht auswertbar ({type(e).__name__})")


def _rolle(d, wand, sicher):
    art = str(d.get("art") or "")
    form = str(d.get("form") or "")
    sl = _f(d.get("schnittlaenge"))
    durch = bool(d.get("durchgehend", True))
    if art in OHNE_SCHNITT or not durch:
        r = INNEN if art != "Innenmerkmal" else UNKLAR
        return _ergebnis(r, EINDEUTIG if art in OHNE_SCHNITT_TEXT else PROBLEMATISCH,
                         OHNE_SCHNITT_TEXT.get(art, "nicht durchgehend, Bearbeitung prüfen"), schnitt=False)
    if not sl or sl <= 0:
        r = (ANFANG if art == "Ende A" else ENDE) if art in ENDEN else UNKLAR
        return _ergebnis(r, NICHT_SICHER, "keine Schnittlänge gemessen")
    if art in ENDEN:
        return _ende(d, art, form, sicher)
    return _innen(d, art, wand, sicher)


def _ende(d, art, form, sicher):
    r = ANFANG if art == "Ende A" else ENDE
    erkannt = (d.get("kontur_erkannt") or {}).get("kontur") if isinstance(d.get("kontur_erkannt"), dict) else None
    if d.get("gegenrohr"):
        g = d["gegenrohr"]
        dm = _f(g.get("d")) if isinstance(g, dict) else None
        text = f"Sattel gegen Gegenrohr Ø {dm:g} mm aus den Schnittflächen" if dm else "Sattel gegen Gegenrohr"
        return _ergebnis(ANSCHLUSS, WAHRSCHEINLICH, text)
    if d.get("fase"):
        return _ergebnis(r, PROBLEMATISCH, "Fase am Ende: Schnitt an der längsten Stelle angenommen")
    if form == "nicht erkannt":
        return _ergebnis(r, NICHT_SICHER, "Endform nicht erkannt")
    if form in GERADE_FORMEN:
        if form == "gerade":
            text = "gerader Schnitt"
        elif form == "Gehrung":
            text = f"Gehrung {_f(d.get('gehrung')) or 0:g}°"
        else:
            text = f"Schrägschnitt in zwei Richtungen, gesamt {_f(d.get('gehrung')) or 0:g}°"
        return _ergebnis(r, EINDEUTIG if sicher else WAHRSCHEINLICH, text + ("" if sicher else
                                                                            ", Erkennung des Teils unsicher"))
    if erkannt:
        return _ergebnis(r, WAHRSCHEINLICH, f"Endkontur {erkannt} aus dem gemessenen Umriss")
    return _ergebnis(r, PROBLEMATISCH, "Endschnitt ohne Grundform (mehrere Flächen), Schnittlänge aus dem STEP")


def _innen(d, art, wand, sicher):
    groesse = _f(d.get("durchmesser")) or _f(d.get("breite")) or _f(d.get("huellmass"))
    if art == "Bohrung" and d.get("gegenueber"):
        r, text = DURCHBRUCH, "Durchgang durch beide Wände (gleiche Achse, gleicher Ø)"
    elif art in ("Bohrung", "Langloch"):
        r, text = INNEN, art
    elif art == "Senkung":
        r, text = INNEN, "Bohrung mit Senkung (Laser schneidet die Bohrung, Senken ist Nacharbeit)"
    elif art in ("Rechteckausschnitt", "Rechteck", "Ausschnitt", "Polygon"):
        r, text = AUSSCHNITT, "Ausschnitt" if art != "Rechteckausschnitt" else "Rechteckausschnitt"
    elif art == "Sonderkontur":
        erk = d.get("form_erkannt")
        if isinstance(erk, dict):       # Endkonturen-Thread (form_erkennung.py): {typ, …}
            erk = erk.get("typ") or erk.get("form") or ""
        if erk:
            return _ergebnis(AUSSCHNITT, WAHRSCHEINLICH, f"Sonderkontur, Grundform {erk} aus dem Umriss")
        if len(d.get("waende") or ()) > 1:
            return _ergebnis(FREIFORM, PROBLEMATISCH, "Kontur über mehrere Wände, Schnittlänge aus dem STEP")
        return _ergebnis(FREIFORM, PROBLEMATISCH, "Sonderkontur ohne Grundform, Schnittlänge aus dem STEP")
    elif art == "Kontur":
        return _ergebnis(FREIFORM, PROBLEMATISCH, "Form nicht erkannt, nur Schnittlänge übernommen")
    else:
        return _ergebnis(UNKLAR, NICHT_SICHER, f"unbekannte Konturart „{art}“" if art else "Konturart fehlt")
    if d.get("z") is None and d.get("x") is None:
        return _ergebnis(r, NICHT_SICHER, f"{text}: Lage am Rohr nicht bestimmt")
    if wand and groesse and groesse < wand:
        return _ergebnis(r, PROBLEMATISCH, f"{text}: Öffnung {groesse:g} mm kleiner als die Wand {wand:g} mm")
    schraeg = _f(d.get("schraeg")) or 0.0
    if schraeg >= SCHRAEG_3D:
        return _ergebnis(r, WAHRSCHEINLICH, f"{text}, Achse {schraeg:g}° schräg zur Wand (3D-Schnitt)")
    if not sicher:
        return _ergebnis(r, WAHRSCHEINLICH, f"{text}, Erkennung des Teils unsicher")
    return _ergebnis(r, EINDEUTIG, text)


def bewerten(konturen, wand=None, sicher=True):
    """rolle() für jede Kontur einer konturen_liste: [dict(nr, art, rolle, stufe, …)] in derselben Reihenfolge."""
    out = []
    for i, d in enumerate(konturen or ()):
        if isinstance(d, dict):
            out.append(dict(rolle(d, wand, sicher), nr=i, art=str(d.get("art") or "")))
    return out


def zusammenfassung(bewertet):
    """Anzahl je Rolle und je Stufe und die zu prüfenden Konturen: dict(rollen, stufen, pruefen=[nr], schlechteste)."""
    rollen, stufen, pruefen = {}, {}, []
    for b in bewertet or ():
        if not b.get("schnitt", True):
            continue
        rollen[b["rolle"]] = rollen.get(b["rolle"], 0) + 1
        stufen[b["stufe"]] = stufen.get(b["stufe"], 0) + 1
        if b["stufe"] >= PRUEFEN_AB:
            pruefen.append(b.get("nr"))
    return dict(rollen=rollen, stufen=stufen, pruefen=pruefen, schlechteste=max(stufen) if stufen else None)


def text(b):
    """Kurztext für Tabellen und Tooltips: „Endeschnitt · 1 eindeutig (Gehrung 45°)“."""
    if not b:
        return ""
    return f"{b['rolle']} · {b['stufe']} {b['stufe_text']} ({b['grund']})"
