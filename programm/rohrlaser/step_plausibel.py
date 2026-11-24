"""Plausibilitätsprüfung des STEP-Imports (Auftrag Patrick 21.11.2026 „KI-gestützten STEP-Import analysieren, optimieren
und erweitern“, Punkt 3C): ungewöhnliche Wandstärken, nicht geschlossene Körper, Maße, die nicht zueinander passen, und
Konturen ohne erkennbare Bearbeitung – BEVOR kalkuliert wird.

Grundsätze:
- Nur aus den Messwerten der STEP-Messung (STEP-Import.exe) und den Stammdaten; keine neue Geometrie-Rechnung, kein
  Maß wird geschätzt oder geändert. Jeder Befund nennt seine Datenbasis ("basis": die Werte, aus denen er folgt).
- Nur Hinweise (Stufe "Hinweis" oder "prüfen"), nie rot: die Messung bleibt gültig, der Anwender entscheidet.
- Ohne Qt, ohne KI. Die lokale KI (ki_agenten, Agent "import") formuliert daraus nur Text.

markieren(messwerte, profile) merkt die Befunde je Teil in m["_plausibel"]; step.ampel zeigt sie als Gründe.
"""
import json
import math
import re

VERSION = 1

# Normwandstärken (EN 10219/10305 und Lagerreihen der Rohrhändler), mm
NORM_WAENDE = (0.8, 1.0, 1.2, 1.5, 1.6, 1.8, 2.0, 2.3, 2.5, 2.6, 2.9, 3.0, 3.2, 3.6, 4.0, 4.5, 5.0, 5.6, 6.0, 6.3, 7.1,
               8.0, 8.8, 10.0, 11.0, 12.0, 12.5, 14.2, 16.0)
TOL_WAND = 0.06          # mm: so nah muss eine gemessene Wand an einer Norm- bzw. Stammdatenwand liegen
TOL_MASS = 0.15          # mm: Außenmaß gleich (wie step.TOL_MASS)
STREUUNG_WAND = 0.15     # mm: Einzelmessungen der Wand dürfen so weit auseinander liegen
TOL_INNEN = 0.2          # mm: Innenmaß = Außenmaß − 2 × Wand
WAND_DUENN = 0.01        # Wand / kleineres Außenmaß darunter: ungewöhnlich dünn
WAND_DICK = 0.25         # Wand / kleineres Außenmaß darüber: ungewöhnlich dick (fast Vollmaterial)
LAENGE_MAX = 12500.0     # mm: länger als jede übliche Stange
HOHL = ("Rundrohr", "Quadratrohr", "Rechteckrohr", "Flachoval", "Halbflachoval", "Elliptisch")

W_NORM, W_STAMM, W_STREU, W_INNEN, W_VERH, OFFEN, LANG, KONTUR, NAME = (
    "wand_norm", "wand_stammdaten", "wand_streuung", "innenmass", "wand_verhaeltnis", "nicht_geschlossen",
    "laenge", "kontur_ohne_form", "name_abweichung")
TOL_NAME = 0.5           # mm: Maß im Datei-/Bauteilnamen gilt als dasselbe wie gemessen
TITEL = {W_NORM: "Wandstärke kein Normmaß", W_STAMM: "Wandstärke nicht in den Stammdaten",
         W_STREU: "Wandstärke ungleichmäßig", W_INNEN: "Innenmaß passt nicht", W_VERH: "Wand ungewöhnlich",
         OFFEN: "Körper nicht geschlossen", LANG: "Länge ungewöhnlich", KONTUR: "Kontur ohne Grundform",
         NAME: "Name passt nicht zur Messung"}


def _f(v, leer=0.0):
    try:
        x = float(str(v).replace(",", "."))
        return x if math.isfinite(x) else leer
    except (TypeError, ValueError):
        return leer


def _z(x):
    return f"{x:.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _befund(regel, text, stufe="Hinweis", **basis):
    return dict(regel=regel, titel=TITEL.get(regel, regel), text=text, stufe=stufe,
                basis={k: (round(v, 3) if isinstance(v, float) else v) for k, v in basis.items()})


def _wand_einzel(m):
    """Einzelmessungen der Wand aus der Spalte wand_messungen ('z:x:y:wand:richtung|…')."""
    out = []
    for teil in str(m.get("wand_messungen") or "").split("|"):
        f = teil.split(":")
        if len(f) >= 4:
            w = _f(f[3], None)
            if w is not None and w > 0:
                out.append(w)
    return out


def _konturen(m):
    k = m.get("konturen_liste")
    try:
        k = json.loads(k) if isinstance(k, str) else (k or [])
    except (TypeError, ValueError):
        return []
    return [d for d in k if isinstance(d, dict)]


def _stamm_waende(m, profile):
    """Wände der Stammdatenprofile mit derselben Form und demselben Außenmaß (leer: keins vorhanden)."""
    form, a, b = m.get("profilform"), _f(m.get("abm_a")), _f(m.get("abm_b"))
    gr, kl = max(a, b), min(a, b)
    out = set()
    for p in profile or ():
        if p.get("form") != form:
            continue
        pa, pb = _f(p.get("a")), _f(p.get("b")) or _f(p.get("a"))
        if abs(max(pa, pb) - gr) <= TOL_MASS and abs(min(pa, pb) - (kl if form != "Rundrohr" else gr)) <= TOL_MASS:
            if _f(p.get("wand")) > 0:
                out.add(round(_f(p.get("wand")), 2))
    return sorted(out)


_ZAHL = r"(\d+(?:[.,]\d+)?)"
_MASS = re.compile(r"(?<![\d.,x×X*])" + _ZAHL + r"\s*[x×X*]\s*" + _ZAHL + r"(?:\s*[x×X*]\s*" + _ZAHL + r")?"
                   r"(?![\d.,]|\s*[x×X*]\s*\d)")


def _namen(m):
    import os
    return [os.path.splitext(os.path.basename(str(m.get("datei") or "")))[0], str(m.get("koerper") or "")]


def name_vergleich(m):
    """Maße aus Datei- und Bauteilname („QR40x40x2“, „Rohr_60x40x3“, „RR42,4x2“) gegen die Messung (nur Hohlprofile).
    Meldet nur, wenn die Außenmaße aus dem Namen zur Messung passen und die Wand nicht: dann ist sicher dasselbe
    Profil gemeint und der Name oder die Zeichnung ist veraltet. Die Messung gilt immer – der Name ändert nichts."""
    form = m.get("profilform") or ""
    a, b, w = _f(m.get("abm_a")), _f(m.get("abm_b")), _f(m.get("wandstaerke"))
    out = []
    if form not in HOHL or a <= 0:
        return out
    aussen = sorted([a, b if b > 0 else a])
    gesehen = set()
    for name in _namen(m):
        text = re.sub(r"(\d)-(\d)(?=\s*[x×X*])", r"\1.\2", name)     # „RR42-4x2“ = 42,4 × 2
        text = re.sub(r"(?<=[x×X*])(\d+)-(\d)(?!\d)", r"\1.\2", text)  # „RR33-7x2-6“ = 33,7 × 2,6
        for t in _MASS.finditer(text.replace("-", " ")):
            z = [_f(x) for x in t.groups() if x]
            if len(z) == 3:
                na, nw = sorted(z[:2]), z[2]
            elif len(z) == 2 and form == "Rundrohr":
                na, nw = [z[0], z[0]], z[1]
            else:
                continue
            if any(abs(x - y) > TOL_NAME for x, y in zip(na, aussen)) or w <= 0 or abs(nw - w) <= TOL_WAND:
                continue
            if nw >= min(aussen) / 2 or (round(nw, 2), name) in gesehen:
                continue
            gesehen.add((round(nw, 2), name))
            out.append(_befund(NAME, f"Name „{name}“ nennt Wand {_z(nw)} mm, gemessen {_z(w)} mm – die Messung gilt; "
                               "Zeichnung/Name veraltet?", "prüfen", name=name, wand_name=nw, wand=w))
    return out


def pruefen(m, profile=None):
    """Befunde eines gemessenen Teils (Liste, leer = nichts aufgefallen)."""
    if m.get("fehler"):
        return []
    out = []
    form = m.get("profilform") or ""
    a, b, w, lg = _f(m.get("abm_a")), _f(m.get("abm_b")), _f(m.get("wandstaerke")), _f(m.get("laenge"))
    profil = m.get("bauteiltyp") in ("Profil", "", None) and form
    if str(m.get("gueltig")) in ("0", "False", "nein") or (m.get("koerperart") or "Volumenkörper") != "Volumenkörper":
        out.append(_befund(OFFEN, f"Körper ist nicht geschlossen ({m.get('koerperart') or 'ungültig'}): Flächen fehlen "
                           "oder sind fehlerhaft – Messung prüfen", "prüfen", koerperart=m.get("koerperart"),
                           gueltig=m.get("gueltig")))
    if profil and form in HOHL and w > 0 and a > 0:
        kl = min(a, b) if b > 0 else a
        stamm = _stamm_waende(m, profile)
        if stamm:
            if all(abs(w - s) > TOL_WAND for s in stamm):
                out.append(_befund(W_STAMM, f"Wand {_z(w)} mm: in den Stammdaten gibt es {form} {_z(a)}"
                                   + (f" × {_z(b)}" if b > 0 and form != "Rundrohr" else "")
                                   + f" nur mit {' / '.join(_z(s) for s in stamm)} mm", wand=w, stammdaten=stamm))
        elif all(abs(w - s) > TOL_WAND for s in NORM_WAENDE):
            naechste = sorted(NORM_WAENDE, key=lambda s: abs(s - w))[:2]
            out.append(_befund(W_NORM, f"Wand {_z(w)} mm ist kein übliches Normmaß (nächste: "
                               f"{' / '.join(_z(s) for s in sorted(naechste))} mm)", wand=w, norm=sorted(naechste)))
        verh = w / kl if kl > 0 else 0.0
        if verh > WAND_DICK:
            out.append(_befund(W_VERH, f"Wand {_z(w)} mm ist sehr dick für {_z(kl)} mm Außenmaß (fast Vollmaterial)",
                               wand=w, aussen=kl))
        elif 0 < verh < WAND_DUENN:
            out.append(_befund(W_VERH, f"Wand {_z(w)} mm ist sehr dünn für {_z(kl)} mm Außenmaß", wand=w, aussen=kl))
        einzel = _wand_einzel(m)
        if len(einzel) >= 3 and max(einzel) - min(einzel) > STREUUNG_WAND:
            out.append(_befund(W_STREU, f"Wand an verschiedenen Stellen {_z(min(einzel))} bis {_z(max(einzel))} mm – "
                               "ungleich dick gezeichnet oder Schweißnaht/Anbau im Querschnitt", "prüfen",
                               minimum=min(einzel), maximum=max(einzel), messungen=len(einzel)))
        ia, ib = _f(m.get("innen_a")), _f(m.get("innen_b"))
        if form in ("Quadratrohr", "Rechteckrohr", "Rundrohr") and ia > 0:
            soll = [a - 2 * w] + ([b - 2 * w] if b > 0 and ib > 0 else [])
            ist = [ia] + ([ib] if b > 0 and ib > 0 else [])
            if any(abs(s - i) > TOL_INNEN for s, i in zip(soll, ist)):
                out.append(_befund(W_INNEN, f"Innenmaß {' × '.join(_z(i) for i in ist)} mm passt nicht zu Außenmaß und "
                                   f"Wand (erwartet {' × '.join(_z(s) for s in soll)} mm) – Wand ungleich?", "prüfen",
                                   innen=ist, erwartet=[round(s, 3) for s in soll]))
    if profil and lg > LAENGE_MAX:
        out.append(_befund(LANG, f"Länge {_z(lg)} mm ist länger als jede übliche Stange ({_z(LAENGE_MAX)} mm) – "
                           "Einheit oder Teil prüfen", "prüfen", laenge=lg))
    for d in _konturen(m):
        if d.get("art") == "Sonderkontur":
            sl = _f(d.get("schnittlaenge"))
            out.append(_befund(KONTUR, f"Sonderkontur bei {_z(_f(d.get('z')))} mm (Schnittlänge {_z(sl)} mm) ohne "
                               "Grundform – Bearbeitung und Schneidzeit prüfen", z=_f(d.get("z")), schnittlaenge=sl))
    if profil:
        out.extend(name_vergleich(m))      # Länge im Namen nicht: Nennlänge vs. Schräge/Ausklinkung zu oft anders
    return out


def markieren(messwerte, profile=None):
    """Alle Teile prüfen und das Ergebnis in m["_plausibel"] merken (leere Liste = nichts aufgefallen)."""
    for m in messwerte or ():
        try:
            m["_plausibel"] = pruefen(m, profile)
        except Exception as e:     # noqa: BLE001 – Prüfung ist Zusatz, darf den Import nie stören
            m["_plausibel"] = [_befund("fehler", f"Plausibilität nicht geprüft: {e}")]
    return messwerte


def gruende(m, n=3):
    """Gründe für die Ampel (höchstens n Texte, Rest als Zahl); nur Hinweise, die Ampel wird dadurch nie rot."""
    liste = [b.get("text") for b in (m.get("_plausibel") or ()) if b.get("text")]
    if not liste:
        return []
    kurz = liste[:n]
    if len(liste) > n:
        kurz.append(f"{len(liste) - n} weitere")
    return ["Plausibilität: " + "; ".join(kurz)]


def zusammenfassung(messwerte):
    """{Regel: Anzahl Teile} über alle Teile (für Importbericht und KI-Agent)."""
    from collections import Counter
    c = Counter()
    for m in messwerte or ():
        for r in {b.get("regel") for b in (m.get("_plausibel") or ())}:
            c[r] += 1
    return dict(c)
