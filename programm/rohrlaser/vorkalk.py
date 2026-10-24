"""Vorkalkulation einer Schweißbaugruppe (Plan Vorkalkulation, Patrick 24.10.2026, Freigabe „alles a außer 8b“):
Rüsten, Positionieren, Wenden, Heften und Verputzen aus Struktur, Einzelteilen und den Regeln der Stammdaten
(Tabelle schweiss_regeln) als Vorschläge.

Rechenweg (alle Werte aus schweiss_regeln, kursiv im Plan):
  Positionierhilfe   je Einzelteil die beste aus Steckverbindung (Stecker oder Aufnahme einer Steckverbindung der
                     Baugruppe), Vorrichtung (Arbeitsgang 'Vorrichtung' an seiner Unterbaugruppe), Gravur (Zukaufteil
                     in einer Unterbaugruppe, deren Rohre so viele Anbauteile mit Umriss, Positions- oder Punktmarke
                     tragen, wie das Teil Stück hat), sonst frei; Spalte bg_hilfe der Position = bestätigt bzw. von Hand
  Rüsten einmalig    Grundrüstzeit + Zeit je Teilenummer × Einzelteil-Positionen (+ Vorrichtung, wenn die Baugruppe
                     einen Arbeitsgang 'Vorrichtung' hat), Umlage je Auftrag
  Positionieren      je Unterbaugruppe (und Baugruppe selbst) × Menge bis zur Baugruppe: ein Stück des ersten
                     Einzelteils (Pos.) als Basisteil, alle übrigen Stück × Zeit ihrer Positionierhilfe; eingebaute
                     Unterbaugruppen zählen als Teil 'frei'
  Wenden             Wendevorgänge je Baugruppe (bg['wenden']) × Zeit je Wenden × Faktor nach Gewicht (Gewicht der
                     Baugruppe aus den Stammdaten der Baugruppe)
  Heften             je Naht max(Mindestzahl, aufrunden(Nahtlänge ÷ Heftabstand)); Heftabstand nach der kleineren
                     Wanddicke (Nahtgruppe 'dicke', bei Stumpf- und Ecknaht das Maß), gesteckt × Faktor; Mindestzahl
                     gerade, rundum (Umfangsnaht) bzw. gesteckt
  Verputzen          Σ Nahtgruppen Naht [m] × min/m der Nacharbeitsstufe × Faktor Zugänglichkeit × Menge bis zur
                     Baugruppe; Stufe aus Qualität (erhöht = verschleifen, Sichtnaht = bündig) und Oberfläche der
                     Baugruppe (beschichtet, verzinkt = Spritzer entfernen), sonst keine

Jeder Wert ist ein Vorschlag mit Begründung (Nahtgruppe bzw. Arbeitsgang: Schlüssel 'vk'). Der gemerkte Wert erkennt
Änderungen von Hand: weicht das Feld davon ab, gilt es als 'hand' und eine neue Vorkalkulation lässt es stehen, ebenso
'bestätigt'. Fehlt eine Regel, gibt es keinen Vorschlag, sondern einen Hinweis (nichts erfinden). Gerechnet wird
weiter nur in baugruppe.rechnen: die Vorschläge sind gewöhnliche Heftpunkte und Arbeitsgänge.
"""
import math

from . import anbau, baugruppe
from .stammdaten import NACHARBEIT_STUFEN, POSITIONIERHILFEN

VORSCHLAG, BESTAETIGT, HAND = "vorschlag", "bestätigt", "hand"
BASISTEIL = "Basisteil"
RUESTEN, POSITIONIEREN, WENDEN, VERPUTZEN = "ruesten", "positionieren", "wenden", "verputzen"
AG_NAMEN = {RUESTEN: "Rüsten Schweißplatz", POSITIONIEREN: "Teile positionieren", WENDEN: "Wenden / Umspannen",
            VERPUTZEN: "Verputzen"}
NAHT_FELDER = ("heftpunkte", "nacharbeit")
AG_FELDER = ("zeit_min", "ruest_min", "menge")
MARKEN = tuple(b for b in anbau.BEARBEITUNGEN if b != "keine")       # Gravur, an der ein Teil angelegt wird
BESCHICHTET = ("pulver", "lack", "beschicht", "verzink", "ktl", "eloxi")

# Richtwerte (Knopf 'Richtwerte laden'): übliche Werkstattwerte zum Start, bitte an die eigene Fertigung anpassen
RICHTWERTE = (
    # Art, Ausprägung, bis, Wert, Einheit
    ("Rüsten", "Grundrüstzeit", None, 15.0, "min je Auftrag"),
    ("Rüsten", "je Teilenummer", None, 1.0, "min je Teilenummer"),
    ("Rüsten", "Vorrichtung", None, 10.0, "min je Auftrag"),
    ("Positionieren", BASISTEIL, None, 0.5, "min je Teil"),
    ("Positionieren", "frei", None, 2.0, "min je Teil"),
    ("Positionieren", "Gravur", None, 1.2, "min je Teil"),
    ("Positionieren", "Vorrichtung", None, 0.8, "min je Teil"),
    ("Positionieren", "Steckverbindung", None, 0.5, "min je Teil"),
    ("Heftabstand", "bis 2 mm", 2.0, 40.0, "mm"),
    ("Heftabstand", "bis 4 mm", 4.0, 50.0, "mm"),
    ("Heftabstand", "bis 8 mm", 8.0, 60.0, "mm"),
    ("Heftabstand", "über 8 mm", None, 80.0, "mm"),
    ("Heften", "Mindestzahl gerade", None, 2.0, "Heftpunkte"),
    ("Heften", "Mindestzahl rundum", None, 3.0, "Heftpunkte"),
    ("Heften", "Mindestzahl gesteckt", None, 1.0, "Heftpunkte"),
    ("Heften", "Faktor Abstand gesteckt", None, 2.0, "Faktor"),
    ("Wenden", "Zeit je Wenden", None, 1.5, "min"),
    ("Wenden", "Faktor bis 20 kg", 20.0, 1.0, "Faktor"),
    ("Wenden", "Faktor bis 50 kg", 50.0, 1.5, "Faktor"),
    ("Wenden", "Faktor über 50 kg (Kran)", None, 3.0, "Faktor"),
    ("Nacharbeit", "Spritzer entfernen", None, 1.5, "min je m Naht"),
    ("Nacharbeit", "Naht verschleifen", None, 4.0, "min je m Naht"),
    ("Nacharbeit", "bündig planschleifen", None, 8.0, "min je m Naht"),
)


def richtwerte():
    """Zeilen der Tabelle schweiss_regeln mit Status 'Richtwert'."""
    return [dict(art=a, wert=w, bis=b, zahl=z, einheit=e, status="Richtwert",
                 bemerkung="Richtwert, bitte an die eigene Fertigung anpassen") for a, w, b, z, e in RICHTWERTE]


_zahl, _n, _text = baugruppe._zahl, baugruppe._n, baugruppe._text


class Regeln:
    """Regelwerte aus schweiss_regeln: wert(art, ausprägung) und stufe(art, bis-Wert) (kleinstes 'bis' ≥ x, sonst
    die Zeile ohne 'bis'); richtwert = mindestens ein benutzter Wert ist noch Richtwert."""

    def __init__(self, tabellen):
        self.zeilen = [z for z in (tabellen or {}).get("schweiss_regeln") or () if _zahl(z.get("zahl"))]
        self.richtwert = False

    def _merken(self, z):
        if z is not None and z.get("status") == "Richtwert":
            self.richtwert = True
        return z

    def wert(self, art, auspraegung):
        z = self._merken(next((z for z in self.zeilen if z.get("art") == art
                               and str(z.get("wert") or "").strip() == auspraegung), None))
        return z["zahl"] if z else None

    def stufe(self, art, x, praefix=""):
        """Wert der Zeile mit dem kleinsten 'bis' ≥ x (Heftabstand nach Wanddicke, Wenden nach Gewicht); ohne
        passende Zeile die ohne 'bis'. praefix: nur Ausprägungen, die so beginnen."""
        kand = [z for z in self.zeilen if z.get("art") == art and str(z.get("wert") or "").startswith(praefix)]
        mit = [z for z in kand if _zahl(z.get("bis")) and _zahl(x) and z["bis"] >= x - 1e-9]
        z = min(mit, key=lambda z: z["bis"]) if mit else next((z for z in kand if not _zahl(z.get("bis"))), None)
        z = self._merken(z)
        return (z["zahl"], z.get("wert")) if z else (None, None)


# ------------------------------------------------------------------ Positionierhilfe
def _ist_rohr(p):
    return not baugruppe.ist_baugruppe(p) and (p.get("art") or "Rohrlaserteil") == "Rohrlaserteil"


def _schluessel(p):
    """Wie eine Steckverbindung ein Teil nennt: Pos.-Nummer oder Artikelnummer."""
    return {str(p.get("pos") or ""), str(p.get("artikel") or "").strip()} - {""}


def hilfen_vorschlag(bg, positionen, bg_id):
    """{Index: (Positionierhilfe, Begründung)} für alle Einzelteile der Baugruppe nach dem Rechenweg oben."""
    idx = baugruppe.teile(positionen, bg_id)
    gesteckt = set()
    for v in bg.get("steckverbindungen") or ():
        if isinstance(v, dict):
            gesteckt |= {str(v.get("aufnahme") or "").strip(), str(v.get("stecker") or "").strip()} - {""}
    vorrichtung = {ag.get("knoten") or "" for ag in bg["arbeitsgaenge"] if "vorrichtung" in str(ag.get("name") or "").lower()}
    marken = {}                     # Knoten -> Anbauteile mit Marke je Stück des Knotens
    for i in idx:
        p = positionen[i]
        if _ist_rohr(p):
            n = sum(1 for a in anbau.lesen(p.get("anbauteile")) if a.get("bearbeitung") in MARKEN
                    and a.get("status") != anbau.AUSGESCHLOSSEN)
            kn = baugruppe.zuordnung(p)[1]
            marken[kn] = marken.get(kn, 0) + n * (p.get("je_knoten") if _zahl(p.get("je_knoten")) else 1)
    out = {}
    for i in sorted(idx, key=lambda i: (_n(positionen[i].get("pos")), i)):
        p = positionen[i]
        kn = baugruppe.zuordnung(p)[1]
        je = p.get("je_knoten") if _zahl(p.get("je_knoten")) and p["je_knoten"] >= 1 else 1
        if _schluessel(p) & gesteckt:
            out[i] = ("Steckverbindung", "Teil einer Steckverbindung der Baugruppe")
        elif kn in vorrichtung or "" in vorrichtung:
            out[i] = ("Vorrichtung", "Arbeitsgang Vorrichtung an " + ("der Baugruppe" if "" in vorrichtung
                                                                       else "seiner Unterbaugruppe"))
        elif not _ist_rohr(p) and marken.get(kn, 0) >= je:
            marken[kn] -= je
            out[i] = ("Gravur", "Lage auf dem Rohr graviert (Anbauteil mit Umriss bzw. Marke)")
        else:
            out[i] = ("frei", "keine Positionierhilfe erkannt")
    return out


def hilfe(p, vorschlag):
    """(Positionierhilfe, Herkunft, Begründung) eines Einzelteils: Spalte bg_hilfe (bestätigt/von Hand), sonst der
    Vorschlag."""
    if p.get("bg_hilfe") in POSITIONIERHILFEN:
        return p["bg_hilfe"], HAND, "bestätigt bzw. von Hand"
    h, grund = vorschlag or ("frei", "keine Positionierhilfe erkannt")
    return h, VORSCHLAG, grund


# ------------------------------------------------------------------ Rüsten, Positionieren, Wenden
def ruesten(bg, positionen, bg_id, regeln):
    """(Minuten einmalig je Auftrag, Begründung) oder (None, was fehlt)."""
    grund, je = regeln.wert("Rüsten", "Grundrüstzeit"), regeln.wert("Rüsten", "je Teilenummer")
    if grund is None or je is None:
        return None, "Regel Rüsten (Grundrüstzeit, je Teilenummer) fehlt"
    n = len(baugruppe.teile(positionen, bg_id))
    t, text = grund + je * n, f"{_text(grund)} + {_text(je)} × {n} Teilenummer{'n' if n != 1 else ''}"
    if any("vorrichtung" in str(ag.get("name") or "").lower() for ag in bg["arbeitsgaenge"]):
        v = regeln.wert("Rüsten", "Vorrichtung")
        if v is None:
            return None, "Regel Rüsten Vorrichtung fehlt"
        t, text = t + v, text + f" + {_text(v)} Vorrichtung"
    return t, text + f" = {_text(round(t, 2))} min je Auftrag"


def positionieren(bg, positionen, bg_id, regeln, hilfen):
    """(Minuten je Baugruppe, Begründung) oder (None, was fehlt); hilfen = {Index: Positionierhilfe}."""
    zeiten = {h: regeln.wert("Positionieren", h) for h in POSITIONIERHILFEN + (BASISTEIL,)}
    teile_kn = {}
    for i in sorted(baugruppe.teile(positionen, bg_id), key=lambda i: (_n(positionen[i].get("pos")), i)):
        teile_kn.setdefault(baugruppe.zuordnung(positionen[i])[1], []).append(i)
    kinder = {}
    for k in bg["knoten"]:
        kinder.setdefault(k.get("parent") or "", []).append(k)
    summe, stueck, fehlt = 0.0, {}, set()
    for kn in [""] + [k["id"] for k in bg["knoten"]]:
        f = baugruppe.faktor(bg, kn) or 0
        posten = [(hilfen.get(i, "frei"), positionen[i].get("je_knoten") if _zahl(positionen[i].get("je_knoten"))
                   else 1) for i in teile_kn.get(kn, ())]
        posten += [("frei", _n(k.get("menge")) or 1) for k in kinder.get(kn, ())]
        if not posten:
            continue
        erst, n = posten[0]
        posten = [(BASISTEIL, 1)] + ([(erst, n - 1)] if n > 1 else []) + posten[1:]
        for h, n in posten:
            if zeiten[h] is None:
                fehlt.add(h)
                continue
            summe += zeiten[h] * n * f
            stueck[h] = stueck.get(h, 0) + n * f
    if fehlt:
        return None, "Regel Positionieren fehlt: " + ", ".join(sorted(fehlt))
    if not stueck:
        return None, "keine Einzelteile"
    teile = " + ".join(f"{_text(n)} × {_text(zeiten[h])} ({h})" for h, n in stueck.items())
    return summe, f"{teile} = {_text(round(summe, 2))} min je Baugruppe"


def gewicht(bg):
    """Gewicht der Baugruppe [kg] aus ihren Stammdaten (Feld Gewicht, Komma erlaubt), sonst None."""
    t = str((bg.get("stamm") or {}).get("gewicht") or "").replace(",", ".").split()
    try:
        g = float(t[0]) if t else None
    except ValueError:
        return None
    return g if g is not None and math.isfinite(g) and g > 0 else None


def wenden(bg, regeln):
    """(Minuten je Wenden, Anzahl, Begründung) oder (None, None, was fehlt bzw. None ohne Wendevorgänge)."""
    n = bg.get("wenden")
    if not _zahl(n) or n <= 0:
        return None, None, None
    zeit = regeln.wert("Wenden", "Zeit je Wenden")
    if zeit is None:
        return None, None, "Regel Wenden (Zeit je Wenden) fehlt"
    g = gewicht(bg)
    if g is None:
        return None, None, "Gewicht der Baugruppe fehlt (Stammdaten der Baugruppe) für den Faktor beim Wenden"
    f, stufe = regeln.stufe("Wenden", g, "Faktor")
    if f is None:
        return None, None, "Regel Wenden (Faktor nach Gewicht) fehlt"
    return zeit * f, int(n), f"{int(n)} × {_text(zeit)} min × {_text(f)} ({stufe}, {_text(g)} kg)"


# ------------------------------------------------------------------ Heften und Nacharbeit
def dicke(naht):
    """Maßgebende (kleinere) Wanddicke einer Nahtgruppe: Feld dicke, bei Stumpf- und Ecknaht sonst das Maß."""
    if _zahl(naht.get("dicke")) and naht["dicke"] > 0:
        return naht["dicke"]
    if naht.get("nahtart") != "Kehlnaht" and _zahl(naht.get("mass")) and naht["mass"] > 0:
        return naht["mass"]
    return None


def heftpunkte(naht, regeln):
    """(Heftpunkte je Naht, Begründung) oder (None, was fehlt)."""
    if not _zahl(naht.get("laenge")) or naht["laenge"] <= 0:
        return None, "Nahtlänge fehlt"
    d = dicke(naht)
    if d is None:
        return None, "Wanddicke fehlt (Spalte Dicke)"
    abstand, stufe = regeln.stufe("Heftabstand", d)
    if not abstand:
        return None, "Regel Heftabstand fehlt"
    art = "gesteckt" if naht.get("gesteckt") else "rundum" if naht.get("rundum") else "gerade"
    mind = regeln.wert("Heften", f"Mindestzahl {art}")
    if mind is None:
        return None, f"Regel Heften Mindestzahl {art} fehlt"
    text = ""
    if art == "gesteckt":
        f = regeln.wert("Heften", "Faktor Abstand gesteckt")
        if f is None:
            return None, "Regel Heften Faktor Abstand gesteckt fehlt"
        abstand, text = abstand * f, f" × {_text(f)} (gesteckt)"
    n = max(int(mind), math.ceil(naht["laenge"] / abstand - 1e-9))
    return n, (f"max({int(mind)}, aufrunden({_text(naht['laenge'])} ÷ {_text(abstand)}))"
               f" = {n}; Heftabstand {stufe}{text}, Wand {_text(d)} mm")


def stufe_vorschlag(naht, bg):
    """(Nacharbeitsstufe, Begründung) aus Qualität der Nahtgruppe und Oberfläche der Baugruppe."""
    q = str(naht.get("qualitaet") or "").strip().lower()
    if q == "sichtnaht":
        return "bündig planschleifen", "Qualität Sichtnaht"
    if q == "erhöht":
        return "Naht verschleifen", "Qualität erhöht"
    ob = str((bg.get("stamm") or {}).get("oberflaeche") or "").lower()
    if any(w in ob for w in BESCHICHTET):
        return "Spritzer entfernen", f"Oberfläche {bg['stamm'].get('oberflaeche')}"
    return "keine", "Oberfläche roh, Qualität normal"


def verputzen(bg, regeln, tabellen):
    """(Minuten je Baugruppe, Begründung) oder (None, was fehlt) aus den Nacharbeitsstufen der Nahtgruppen."""
    summe, teile, fehlt = 0.0, [], set()
    for nt in bg["naehte"]:
        st = nt.get("nacharbeit")
        if not st or st == "keine":
            continue
        min_m = regeln.wert("Nacharbeit", st)
        if min_m is None:
            fehlt.add(st)
            continue
        f = baugruppe.faktor(bg, nt.get("knoten") or "") or 0
        anzahl = _n(nt.get("anzahl")) if _zahl(nt.get("anzahl")) else 1
        m = _n(nt.get("laenge")) * anzahl * (2 if nt.get("beidseitig") else 1) / 1000 * f
        z = baugruppe._faktor_zeile(tabellen or {}, "Zugänglichkeit", nt.get("zugang"))
        fz = _n((z or {}).get("faktor")) or 1.0
        summe += m * min_m * fz
        teile.append(f"{_text(round(m, 3))} m × {_text(min_m)}" + (f" × {_text(fz)}" if fz != 1 else ""))
    if fehlt:
        return None, "Regel Nacharbeit fehlt: " + ", ".join(sorted(fehlt))
    if not teile:
        return None, None
    return summe, " + ".join(teile) + f" = {_text(round(summe, 2))} min je Baugruppe"


# ------------------------------------------------------------------ Vorschläge setzen, bestätigen, zählen
def _status(gemerkt, aktuell):
    """Herkunft eines Felds: hand, wenn es vom gemerkten Vorschlag abweicht, sonst der gemerkte Status."""
    if not isinstance(gemerkt, dict):
        return None
    if aktuell != gemerkt.get("wert"):
        return HAND
    return gemerkt.get("status") or VORSCHLAG


def naht_status(naht, feld):
    """Herkunft eines Felds einer Nahtgruppe (vorschlag, bestätigt, hand) oder None (nicht vorkalkuliert)."""
    return _status(((naht.get("vk") or {}).get(feld)), naht.get(feld))


def ag_status(ag):
    """Herkunft eines Arbeitsgangs der Vorkalkulation (vorschlag, bestätigt, hand) oder None."""
    vk = ag.get("vk")
    if not isinstance(vk, dict) or not vk.get("art"):
        return None
    werte = vk.get("wert") or {}
    if any(ag.get(f) != werte.get(f) for f in AG_FELDER):
        return HAND
    return vk.get("status") or VORSCHLAG


def _naht_setzen(nt, feld, wert, text, out):
    st = naht_status(nt, feld)
    if st in (HAND, BESTAETIGT) or (st is None and nt.get(feld) not in (None, "")):
        if st is None:           # von Hand eingetragen, bevor vorkalkuliert wurde
            nt.setdefault("vk", {})[feld] = dict(wert=nt.get(feld), status=HAND, text="von Hand")
        elif st == HAND:
            nt["vk"][feld].update(status=HAND)
        return
    if wert is None:
        return
    if nt.get(feld) != wert:
        out.append(f"Nahtgruppe {nt.get('nr') or ''}: {feld} {_text(wert) if _zahl(wert) else wert}".replace("  ", " "))
    nt[feld] = wert
    nt.setdefault("vk", {})[feld] = dict(wert=wert, status=VORSCHLAG, text=text)


def _ag_setzen(bg, art, werte, text, satz_id, richtwert, out):
    ag = next((a for a in bg["arbeitsgaenge"] if (a.get("vk") or {}).get("art") == art), None)
    st = ag_status(ag) if ag else None
    if st in (HAND, BESTAETIGT):
        if st == HAND:
            ag["vk"]["status"] = HAND
        return
    if werte is None:
        if ag is not None:       # Vorschlag ohne Grundlage mehr: entfernen
            bg["arbeitsgaenge"].remove(ag)
            out.append(f"{AG_NAMEN[art]} entfernt")
        return
    if ag is None:
        ag = dict(id=baugruppe.neue_id(), name=AG_NAMEN[art], knoten="", umlage=baugruppe.UMLAGE_AUFTRAG)
        bg["arbeitsgaenge"].append(ag)
    for f in AG_FELDER:
        ag.pop(f, None)
    ag.update({f: w for f, w in werte.items() if w is not None})
    if satz_id:
        ag["satz_id"] = satz_id
        ag.pop("satz", None)
    ag["vk"] = dict(art=art, status=VORSCHLAG, text=text, richtwert=richtwert,
                    wert={f: ag.get(f) for f in AG_FELDER})
    out.append(f"{AG_NAMEN[art]}: {text}")


def vorkalkulieren(p, positionen, tabellen, einstellungen=None):
    """Vorkalkulation der Baugruppen-Position p (Index in positionen egal, Einzelteile über bg_knoten): setzt in
    ihrer Baugruppe Heftpunkte und Nacharbeitsstufe der Nahtgruppen und die Arbeitsgänge Rüsten, Positionieren,
    Wenden und Verputzen als Vorschläge; Werte von Hand und bestätigte bleiben. Ändert nichts an den Positionen.
    Ergebnis: dict(bg (neue Baugruppe), aenderungen [Text], hinweise [Text], hilfen {Index: (Hilfe, Herkunft,
    Grund)}, richtwert)."""
    einst = einstellungen or {}
    bg = baugruppe.lesen(p.get("baugruppe"))
    if bg is None:
        return dict(bg=None, aenderungen=[], hinweise=["Baugruppendaten fehlen"], hilfen={}, richtwert=False)
    regeln = Regeln(tabellen)
    out, hinweise = [], []
    if not regeln.zeilen:
        hinweise.append("Keine Regeln der Vorkalkulation (Einstellungen → Schweiß-Vorkalkulation, Richtwerte laden)")
    vorschlag = hilfen_vorschlag(bg, positionen, bg["id"])
    hilfen = {i: hilfe(positionen[i], v) for i, v in vorschlag.items()}
    for nt in bg["naehte"]:
        n, text = heftpunkte(nt, regeln)
        if n is None and not _zahl(nt.get("heftpunkte")):
            hinweise.append(f"Nahtgruppe {nt.get('nr') or ''}: Heftpunkte ohne Vorschlag, {text}".replace("  ", " "))
        _naht_setzen(nt, "heftpunkte", n, text, out)
        st, grund = stufe_vorschlag(nt, bg)
        _naht_setzen(nt, "nacharbeit", st, grund, out)
    satz = einst.get("schweiss_vk_satz") or "Schweißen"
    satz_na = einst.get("schweiss_vk_satz_nacharbeit") or satz
    t, text = ruesten(bg, positionen, bg["id"], regeln)
    _ag_setzen(bg, RUESTEN, None if t is None else dict(ruest_min=round(t, 2)), text, satz, regeln.richtwert, out)
    if t is None:
        hinweise.append(text)
    t, text = positionieren(bg, positionen, bg["id"], regeln, {i: h[0] for i, h in hilfen.items()})
    _ag_setzen(bg, POSITIONIEREN, None if t is None else dict(zeit_min=round(t, 4)), text, satz, regeln.richtwert,
               out)
    if t is None:
        hinweise.append(text)
    t, n, text = wenden(bg, regeln)
    _ag_setzen(bg, WENDEN, None if t is None else dict(zeit_min=round(t, 4), menge=n), text, satz, regeln.richtwert,
               out)
    if text and t is None:
        hinweise.append(text)
    t, text = verputzen(bg, regeln, tabellen)
    _ag_setzen(bg, VERPUTZEN, None if t is None else dict(zeit_min=round(t, 4)), text, satz_na, regeln.richtwert,
               out)
    if text and t is None:
        hinweise.append(text)
    return dict(bg=bg, aenderungen=out, hinweise=hinweise, hilfen=hilfen, richtwert=regeln.richtwert)


def bestaetigen(bg):
    """Alle offenen Vorschläge der Baugruppe als bestätigt merken (Werte bleiben). Ergebnis: Anzahl."""
    n = 0
    for nt in bg["naehte"]:
        for feld in NAHT_FELDER:
            if naht_status(nt, feld) == VORSCHLAG:
                nt["vk"][feld]["status"] = BESTAETIGT
                n += 1
    for ag in bg["arbeitsgaenge"]:
        if ag_status(ag) == VORSCHLAG:
            ag["vk"]["status"] = BESTAETIGT
            n += 1
    return n


def offen(bg):
    """Anzahl offener Vorschläge (Nahtgruppen-Felder und Arbeitsgänge) einer Baugruppe."""
    if not bg:
        return 0
    return (sum(1 for nt in bg["naehte"] for feld in NAHT_FELDER if naht_status(nt, feld) == VORSCHLAG)
            + sum(1 for ag in bg["arbeitsgaenge"] if ag_status(ag) == VORSCHLAG))


__all__ = ["vorkalkulieren", "bestaetigen", "offen", "richtwerte", "Regeln", "NACHARBEIT_STUFEN"]
