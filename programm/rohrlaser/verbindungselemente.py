"""Normteile und Verbindungselemente in Baugruppen (Plan Phase 3 und 4, Paket C, Patrick 13.11.2026 „Alles einbauen“).

C1 CALC-017 Montagezeit aus den Verbindungselementen: Schrauben, Muttern, Scheiben, Stifte … unter den
   Zukaufteilen einer Position (Normteile nach PART-004, normteil.py) ergeben den Vorschlag „Montage
   Verbindungselemente“ (€/Stück, Menge = Elemente je Teil; der Beispielpreis entspricht einer Richtzeit je Element).
C2 CALC-012 Bolzenschweißen und Einpressen je Element: Schweißbolzen ergeben „Bolzenschweißen“, Einpressmuttern und
   -bolzen „Einpressmuttern setzen“, Endkappen und Stopfen „Endkappen/Stopfen einsetzen“ (je €/Stück).
C3 PART-006 Einpresselemente aus dem Lochbild eines Blechs: runde Löcher ohne Gewinde mit dem Durchmesser der
   Einpressbohrung (Tabelle EINPRESS_BOHRUNG) ergeben „Einpressmuttern setzen“ mit der Anzahl der Löcher.
C4 PART-010 Bohrungen ohne Schraube: ein Satz, dessen Teile Durchgangsbohrungen haben, aber kein Verbindungselement
   (Hinweis im Angebots-Check, nur ein Hinweis).
C5 PART-012 Endkappen: Rohrteile (Rund-, Quadrat-, Rechteckrohr) mit zwei geraden Enden außerhalb von Sätzen und
   Baugruppen, ohne Endkappe: Hinweis im Angebots-Check (Einstellung endkappen_hinweis, Vorgabe ja).

Alles sind Vorschläge (gelb, „Erkannt: Zukaufteile …“ bzw. „Erkannt: Lochbild …“) und kostet erst mit Übernehmen;
nichts ändert Konturen oder Lage. Ohne Qt.
"""
import json
import re

from . import normteil

MONTAGE = "Montage Verbindungselemente"
BOLZEN = "Bolzenschweißen"
EINPRESS = "Einpressmuttern setzen"
ENDKAPPE = "Endkappen/Stopfen einsetzen"
QUELLE_ZUKAUF = "Zukaufteile"
QUELLE_LOCH = "Lochbild"

# Bohrung im Blech für Einpressmuttern (Herstellerkatalog selbstsichernder Einpressmuttern, metrisch, Bohrung
# +0,08 mm): Gewinde -> Ø [mm]. Nur Vorschlag; die Werkstatt prüft Blechdicke und Typ.
EINPRESS_BOHRUNG = {"M3": 4.22, "M4": 5.41, "M5": 6.35, "M6": 8.75, "M8": 10.5}
TOLERANZ = 0.1              # mm um den Katalogwert
ROHRPROFILE = ("Rundrohr", "Quadratrohr", "Rechteckrohr")

_BOLZEN = re.compile(r"schwei(ß|ss)bolzen|bolzenschwei|\bISO\s*13918\b|\bDIN\s*32501\b|gewindebolzen\s+zum\s+schwei", re.I)
_EINPRESS = re.compile(r"einpress|\bPEM\b|\bclinch|einpressbolzen|einpressmutter", re.I)
_ENDKAPPE = re.compile(r"endkappe|stopfen|lamellenstopfen|abschlusskappe|rohrkappe", re.I)
_VERBINDER = re.compile(r"schraube|mutter|scheibe|\bstift|niet|sicherungsring|splint|gewindestange|unterlegscheibe",
                        re.I)


def art(bezeichnung, kategorie=None):
    """Art eines Zukaufteils: BOLZEN, EINPRESS, ENDKAPPE, MONTAGE (Verbindungselement) oder None."""
    t = str(bezeichnung or "")
    if _BOLZEN.search(t):
        return BOLZEN
    if _EINPRESS.search(t):
        return EINPRESS
    if _ENDKAPPE.search(t):
        return ENDKAPPE
    m = normteil.merkmale(t)
    if _VERBINDER.search(t) or (m.get("norm") and m.get("groesse")) or str(kategorie or "").lower() == "normteile":
        return MONTAGE
    return None


def _zukauf(p):
    try:
        liste = json.loads(p.get("zukauf") or "[]")
    except (TypeError, ValueError):
        return []
    return [e for e in liste if isinstance(e, dict)] if isinstance(liste, list) else []


def elemente(p):
    """{Art: (Anzahl je Teil, [Bezeichnung …])} aus den Zukaufteilen der Position; nur Einträge je Teil mit Menge."""
    out = {}
    for e in _zukauf(p):
        st = e.get("stand") or {}
        a = art(st.get("bezeichnung"), st.get("kategorie"))
        menge = e.get("menge")
        if a is None or (e.get("je") or "Teil") != "Teil" or not isinstance(menge, (int, float)) or menge <= 0:
            continue
        n, namen = out.get(a, (0, []))
        out[a] = (n + menge, namen + [str(st.get("bezeichnung") or st.get("artikelnr") or "?")])
    return out


def _technik(p):
    try:
        t = json.loads(p.get("technik") or "{}")
    except (TypeError, ValueError):
        return {}
    return t if isinstance(t, dict) else {}


def bohrungen(p):
    """[(Ø, Anzahl, Gewinde)] der runden Bohrungen der Position (Konturen aus Schneidweg-Rechner, Editor, STEP)."""
    from . import schneidweg as sw
    out = []
    for z in _technik(p).get("konturen") or ():
        if isinstance(z, dict) and z.get("art") == sw.BOHRUNG:
            try:
                d = float(z.get("d"))
            except (TypeError, ValueError):
                continue
            out.append((d, max(int(z.get("anzahl") or 1), 1), z.get("gewinde")))
    return out


def einpress_loecher(p):
    """{Gewinde: Anzahl} der Löcher ohne Gewinde, deren Ø zur Einpressbohrung passt (PART-006)."""
    out = {}
    for d, n, g in bohrungen(p):
        if g:
            continue
        for gew, soll in EINPRESS_BOHRUNG.items():
            if abs(d - soll) <= TOLERANZ:
                out[gew] = out.get(gew, 0) + n
    return out


def _zahl_text(x):
    return f"{x:g}".replace(".", ",")


def vorschlaege(p, katalog):
    """Vorschläge für zusatz_erkennung.erkannt: [{name, quelle, wort, menge}] für aktive Zusatzarbeiten des Katalogs."""
    aktiv = {z.get("name") for z in katalog or () if z.get("name") and z.get("aktiv") != "nein"}
    out = []
    for a, (n, namen) in elemente(p).items():
        if a in aktiv:
            kurz = ", ".join(dict.fromkeys(namen))
            out.append(dict(name=a, quelle=QUELLE_ZUKAUF, wort=f"{_zahl_text(n)} × {kurz[:80]}", text=None, menge=n))
    if EINPRESS in aktiv and EINPRESS not in {x["name"] for x in out}:
        loecher = einpress_loecher(p)
        if loecher:
            n = sum(loecher.values())
            wort = ", ".join(f"{k} {_zahl_text(c)}× Ø {_zahl_text(EINPRESS_BOHRUNG[g])}"
                             for g, c in loecher.items() for k in (g,))
            out.append(dict(name=EINPRESS, quelle=QUELLE_LOCH, wort=wort + " (Einpressbohrung, bitte prüfen)",
                            text=None, menge=n))
    return out


# ------------------------------------------------------------------ Angebots-Check (C4, C5)
def satz_ohne_schraube(positionen):
    """C4: [(Satz, Bohrungen je Satz)] für Sätze mit Durchgangsbohrungen (ohne Gewinde, Ø 3–30 mm) in ihren Teilen,
    aber ohne Verbindungselement (Zukaufteil Schraube/Mutter/Bolzen/Einpresselement oder Gewinde im Satz)."""
    from .angebot import ist_baugruppe
    saetze = {}
    for p in positionen:
        s = p.get("satz")
        if not s or not str(s).strip():
            continue
        x = saetze.setdefault(s, dict(loecher=0, verbinder=False))
        je = p.get("je_satz") if isinstance(p.get("je_satz"), (int, float)) and p.get("je_satz") > 0 else 1
        for d, n, g in bohrungen(p):
            if g:
                x["verbinder"] = True
            elif 3 <= d <= 30:
                x["loecher"] += n * je
        if any(a in (MONTAGE, BOLZEN, EINPRESS) for a in elemente(p)) or (ist_baugruppe(p) and _zukauf(p)):
            x["verbinder"] = True
    return [(s, x["loecher"]) for s, x in saetze.items() if x["loecher"] and not x["verbinder"]]


def offene_enden(positionen, k):
    """C5: [(Pos., Enden je Teil)] für Rohrteile (Rund-, Quadrat-, Rechteckrohr) mit zwei geraden Enden, nicht in
    einem Satz und nicht in einer Schweißbaugruppe, ohne Endkappe bei den Zukaufteilen."""
    from .angebot import kein_laserteil
    out = []
    for p in positionen:
        if kein_laserteil(p) or p.get("satz") or p.get("baugruppe") or not p.get("profil_id"):
            continue
        form = ((k.profile.get(p.get("profil_id")) or {}) if k is not None else {}).get("form")
        if form not in ROHRPROFILE or ENDKAPPE in elemente(p):
            continue
        if p.get("a_gerade") != "nein" and p.get("b_gerade") != "nein":
            out.append((p.get("pos"), 2))
    return out
