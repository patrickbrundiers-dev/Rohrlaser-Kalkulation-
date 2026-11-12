"""Zeitvorgabe von Hand, Rüst- und Stückzeit und Bereiche einer Schweißbaugruppe (Patrick 12.11.2026, Konzept
„Schweißbaugruppen-Kalkulation flexibel“, Freigabe „Alle Empfehlungen“).

Die automatische Rechnung (baugruppe.rechnen) bleibt unverändert und wird immer mitgerechnet. Diese Datei sortiert
ihre Zeiten nach Bereichen und Zeitart und legt eine Vorgabe von Hand darüber:

  Rüstzeit        einmal je Auftrag (alle Lose): Rüstzeiten der Arbeitsgänge × Lose × Umlage
  Stückzeit       je Baugruppe: Nahtgruppen (Heften, Schweißen) und laufende Arbeitsgänge, ohne Fremdleistung
  Gesamtzeit      Rüstzeit + Stückzeit × Anzahl Baugruppen
  Bereiche        Vorbereitung, Heften, Schweißen, Nachbearbeitung, Weitere (eigene Leistungen), Fremdleistung
                  (nur €). Arbeitsgang: Feld 'bereich', sonst aus der Vorkalkulation bzw. dem Namen
  Komplexität     bg['komplex'] = {faktor, gruende}; Faktor auf die automatische Stückzeit der eigenen Leistungen
                  (nicht Rüsten, nicht auf eine Zeit von Hand; F3 a). Vorgabe 1 = wie bisher
  Vorgabe         bg['vorgabe'] = {stueck_min, ruest_min, bereiche {Bereich: min}, satz_id, grund, am, auto_damals};
                  leer = automatisch. Eine Stückzeit von Hand geht vor den Bereichen. Die Kosten folgen anteilig:
                  Faktor = Zeit von Hand ÷ automatische Zeit auf die Lohnkosten der betroffenen Zeilen, so bleibt die
                  Mischung der Stundensätze (F1 a). Ohne automatische Zeit gilt der Stundensatz der Vorgabe (satz_id,
                  sonst der der meisten Schweißzeit, sonst 'Schweißen'). Fremdleistungen, Kosten je Einheit,
                  Einmalbeträge, Schweißdraht und Gas bleiben.
Ohne Vorgabe und mit Faktor 1 ändert sich nichts (bitgleich wie vor dem 12.11.2026).
"""
import math
import re

VORBEREITUNG, HEFTEN, SCHWEISSEN, NACHBEARBEITUNG, WEITERE = ("Vorbereitung", "Heften", "Schweißen",
                                                             "Nachbearbeitung", "Weitere")
FREMD = "Fremdleistung"
BEREICHE = (VORBEREITUNG, HEFTEN, SCHWEISSEN, NACHBEARBEITUNG, WEITERE)
# Vorschläge der Vorkalkulation (vorkalk.AG_NAMEN) haben ihren Bereich fest
BEREICH_VK = {"ruesten": VORBEREITUNG, "positionieren": VORBEREITUNG, "fase": VORBEREITUNG, "wenden": SCHWEISSEN,
              "verputzen": NACHBEARBEITUNG, "beizen": NACHBEARBEITUNG, "richten": NACHBEARBEITUNG,
              "pruefen": NACHBEARBEITUNG}
# Wortteile im Namen eines Arbeitsgangs, in dieser Reihenfolge geprüft (erste Treffer gilt)
BEREICH_WOERTER = (
    (NACHBEARBEITUNG, ("verputz", "schleif", "bürst", "buerst", "beiz", "passiv", "richten", "sichtprüf", "pruef",
                       "prüf", "kontroll", "nacharbeit", "polier", "spritzer", "glätt")),
    (VORBEREITUNG, ("bereitstell", "sortier", "entgrat", "reinig", "anpass", "vorbereit", "vorricht", "positionier",
                    "fase", "rüst", "ruest", "kommission", "spann", "zusammenstell")),
    (HEFTEN, ("heft",)),
    (SCHWEISSEN, ("schweiß", "schweiss", "wenden", "umspann", "naht")),
)
KOMPLEX_GRUENDE = ("schwierige Zugänglichkeit", "viele Einzelteile", "aufwendige Positionierung",
                   "mehrere Schweißlagen", "häufiges Wenden", "hohe Maßanforderungen")


def _zahl(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def bereich(ag):
    """Bereich eines Arbeitsgangs (dict aus bg['arbeitsgaenge']): Fremdleistung, Feld 'bereich', Art der
    Vorkalkulation, Wortteil im Namen, sonst Weitere."""
    if ag.get("fremd"):
        return FREMD
    if ag.get("bereich") in BEREICHE:
        return ag["bereich"]
    art = (ag.get("vk") or {}).get("art")
    if art in BEREICH_VK:
        return BEREICH_VK[art]
    name = str(ag.get("name") or "").lower()
    for b, woerter in BEREICH_WOERTER:
        if any(w in name for w in woerter):
            return b
    return WEITERE


# ------------------------------------------------------------------ Zeit lesen und schreiben
class Fehler(ValueError):
    """Zeit nicht lesbar; der Text ist für den Benutzer."""


_EINHEIT = {"h": 60.0, "std": 60.0, "std.": 60.0, "stunde": 60.0, "stunden": 60.0, "st": 60.0,
            "min": 1.0, "min.": 1.0, "minute": 1.0, "minuten": 1.0, "m": 1.0, "'": 1.0,
            "s": 1 / 60, "sek": 1 / 60, "sek.": 1 / 60, "sekunden": 1 / 60, "": None}
_TEIL = re.compile(r"(\d+(?:[.,]\d+)?)\s*([a-zäöü.']*)")


def zeit_lesen(text):
    """Minuten aus einer Eingabe oder None (leer): 55, 55 min, 12,5, 0:55, 1:30 h, 1,5 h, 1 h 20, 1 h 20 min, 90 s.
    Eine Zahl ohne Einheit sind Minuten; '1 h 20' = 1 h 20 min. Fehler bei unlesbarem Text oder negativ."""
    t = str(text or "").strip().lower().replace("und", " ")
    if not t:
        return None
    if t.startswith("-"):
        raise Fehler("Zeit darf nicht negativ sein")
    m = re.fullmatch(r"(\d+):(\d{1,2})(?::(\d{1,2}))?\s*(h|std\.?|stunden?)?", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2)) + (int(m.group(3)) / 60 if m.group(3) else 0)
    pos, summe, teile = 0, 0.0, []
    for x in _TEIL.finditer(t):
        if t[pos:x.start()].strip():
            raise Fehler(f"„{text}“ ist keine Zeit (z. B. 55 min, 1,5 h, 1:20 oder 1 h 20 min)")
        teile.append((float(x.group(1).replace(",", ".")), x.group(2)))
        pos = x.end()
    if t[pos:].strip() or not teile:
        raise Fehler(f"„{text}“ ist keine Zeit (z. B. 55 min, 1,5 h, 1:20 oder 1 h 20 min)")
    for w, e in teile:
        if e not in _EINHEIT:
            raise Fehler(f"Einheit „{e}“ unbekannt (h, min oder s)")
        f = _EINHEIT[e]
        if f is None:       # ohne Einheit: Minuten, nach einer Stundenangabe ebenfalls Minuten
            f = 1.0
        summe += w * f
    return summe


def zeit_text(minuten, lang=False):
    """'55 min', '1 h 20 min' (ab 60 min), '12,5 min'; lang: zusätzlich Stunden '(0,92 h)'."""
    if not _zahl(minuten):
        return ""
    v = round(float(minuten), 1)
    if abs(v) < 60:
        t = f"{v:g}".replace(".", ",") + " min"
    else:
        h, m = divmod(round(abs(v)), 60)
        t = ("−" if v < 0 else "") + f"{h} h {m:02d} min"
    if lang:
        t += " (" + f"{minuten / 60:.2f}".replace(".", ",") + " h)"
    return t


def abweichung_text(minuten):
    """'+15 min', '−5 min', '±0 min'."""
    if not _zahl(minuten):
        return ""
    if abs(minuten) < 0.05:
        return "±0 min"
    return ("+" if minuten > 0 else "−") + zeit_text(abs(minuten))


# ------------------------------------------------------------------ Daten der Baugruppe
def vorgabe(bg):
    """Vorgabe von Hand der Baugruppe: dict(stueck_min, ruest_min, bereiche, satz_id, grund, am, auto_damals); nur
    gültige Zahlen ≥ 0, sonst None bzw. {}."""
    v = (bg or {}).get("vorgabe")
    v = v if isinstance(v, dict) else {}
    ber = v.get("bereiche") if isinstance(v.get("bereiche"), dict) else {}
    return dict(stueck_min=v["stueck_min"] if _zahl(v.get("stueck_min")) and v["stueck_min"] >= 0 else None,
                ruest_min=v["ruest_min"] if _zahl(v.get("ruest_min")) and v["ruest_min"] >= 0 else None,
                bereiche={b: w for b, w in ber.items() if b in BEREICHE and _zahl(w) and w >= 0},
                satz_id=v.get("satz_id") or None, grund=v.get("grund") or "", am=v.get("am") or "",
                auto_damals=v.get("auto_damals") if isinstance(v.get("auto_damals"), dict) else {})


def hat_vorgabe(bg):
    v = vorgabe(bg)
    return v["stueck_min"] is not None or v["ruest_min"] is not None or bool(v["bereiche"])


def komplex(bg):
    """(Faktor, Gründe) des Komplexitätsfaktors; ohne Eintrag (1.0, [])."""
    k = (bg or {}).get("komplex")
    k = k if isinstance(k, dict) else {}
    f = k.get("faktor")
    f = f if _zahl(f) and f > 0 else 1.0
    return f, [g for g in k.get("gruende") or () if isinstance(g, str)]


def schnell(bg):
    """Pauschalen der Schnellkalkulation je Baugruppe (bg['schnell']): dict(material_eur, zukauf_eur), leer = 0.
    Material zählt wie Material (mit Gewinn), Zukauf wie Zukaufteile (ohne Gewinn, ohne Aufschlag); gedacht für
    Baugruppen ohne Einzelteile (der Status warnt bei beidem)."""
    x = (bg or {}).get("schnell")
    x = x if isinstance(x, dict) else {}
    return {n: float(x[n]) if _zahl(x.get(n)) and x[n] > 0 else 0.0 for n in ("material_eur", "zukauf_eur")}


def schnell_setzen(bg, material_eur=None, zukauf_eur=None):
    x = {n: w for n, w in (("material_eur", material_eur), ("zukauf_eur", zukauf_eur)) if _zahl(w) and w > 0}
    if x:
        bg["schnell"] = x
    else:
        bg.pop("schnell", None)
    return bg


def preis_hand(bg, anzahl):
    """Verkaufspreis je Baugruppe von Hand (inkl. Einzelteile, F4 a) für diese Anzahl, sonst None. Gespeichert als
    bg['preis_hand'] = {preis, menge}: gilt nur bei derselben Anzahl Baugruppen (Staffelstufen rechnen normal)."""
    x = (bg or {}).get("preis_hand")
    if not isinstance(x, dict) or not _zahl(x.get("preis")) or x["preis"] < 0:
        return None
    if _zahl(x.get("menge")) and _zahl(anzahl) and abs(x["menge"] - anzahl) > 1e-9:
        return None
    return float(x["preis"])


def vorgabe_setzen(bg, auto=None, **werte):
    """Felder der Vorgabe in bg setzen (None = Feld entfernen); leere Vorgabe fällt weg. auto = zeiten-Ergebnis
    (merkt die automatische Zeit beim ersten Setzen, auto_damals)."""
    v = dict(bg.get("vorgabe") or {}) if isinstance(bg.get("vorgabe"), dict) else {}
    for n, w in werte.items():
        if n == "bereiche":
            ber = {b: x for b, x in (w or {}).items() if b in BEREICHE and _zahl(x)}
            if ber:
                v["bereiche"] = ber
            else:
                v.pop("bereiche", None)
        elif w is None or w == "":
            v.pop(n, None)
        else:
            v[n] = w
    zahlen = [n for n in ("stueck_min", "ruest_min", "bereiche") if n in v]
    if not zahlen:
        bg.pop("vorgabe", None)
        return bg
    if auto is not None:
        v["auto_damals"] = dict(stueck_min=round(auto.get("auto_stueck_min") or 0.0, 2),
                                ruest_min=round(auto.get("auto_ruest_min") or 0.0, 2))
    bg["vorgabe"] = v
    return bg


def komplex_setzen(bg, faktor=None, gruende=None):
    """Komplexitätsfaktor setzen; Faktor 1 bzw. leer ohne Gründe entfernt ihn."""
    k = dict(bg.get("komplex") or {}) if isinstance(bg.get("komplex"), dict) else {}
    if faktor is not None:
        k["faktor"] = faktor
    if gruende is not None:
        k["gruende"] = [g for g in gruende if g]
    if not k.get("gruende"):
        k.pop("gruende", None)
    if not _zahl(k.get("faktor")) or abs(k["faktor"] - 1) < 1e-9:
        k.pop("faktor", None)
    if k:
        bg["komplex"] = k
    else:
        bg.pop("komplex", None)
    return bg


# ------------------------------------------------------------------ Anwenden (aus baugruppe.rechnen)
def _satz_vorgabe(v, saetze, posten):
    if v["satz_id"] and _zahl(saetze.get(v["satz_id"])):
        return v["satz_id"], saetze[v["satz_id"]]
    gewicht = {}
    for p in posten:
        if p["satz_id"] and p["bereich"] in (SCHWEISSEN, HEFTEN):
            gewicht[p["satz_id"]] = gewicht.get(p["satz_id"], 0.0) + p["stueck_min"]
    for sid, _ in sorted(gewicht.items(), key=lambda x: -x[1]):
        if _zahl(saetze.get(sid)):
            return sid, saetze[sid]
    if _zahl(saetze.get("Schweißen")):
        return "Schweißen", saetze["Schweißen"]
    return v["satz_id"], None


def anwenden(out, posten, bg, saetze, n, ohne_hand=False):
    """Bereiche, Rüst-/Stückzeit, Komplexitätsfaktor und Vorgabe auf das Ergebnis von baugruppe.rechnen anwenden.
    posten: je eigener Zeile (Index in out['zeilen']) Anteile dict(zeile, bereich, stueck_min, stueck_eur,
    ruest_min, ruest_eur, satz_id, satz); Minuten je Baugruppe bzw. Rüsten je Auftrag, € reine Lohnkosten.
    ohne_hand: nur automatisch (Kennwerte lernen). Setzt out['zeiten'] und passt Zeilen und Summen an."""
    kf, gruende = komplex(bg)
    v = vorgabe(bg)
    if ohne_hand:
        kf, gruende = 1.0, []
        v = dict(v, stueck_min=None, ruest_min=None, bereiche={})
    ber = {b: dict(bereich=b, auto_stueck=0.0, auto_ruest=0.0, eur_stueck=0.0, eur_ruest=0.0) for b in BEREICHE}
    for p in posten:
        b = ber[p["bereich"]]
        b["auto_stueck"] += p["stueck_min"]
        b["auto_ruest"] += p["ruest_min"]
        b["eur_stueck"] += p["stueck_eur"]
        b["eur_ruest"] += p["ruest_eur"]
    a_stueck = sum(b["auto_stueck"] for b in ber.values())
    a_ruest = sum(b["auto_ruest"] for b in ber.values())
    sid, satz_v = _satz_vorgabe(v, saetze, posten)
    # Faktoren je Bereich (Stück) und für Rüsten; extra = Minuten von Hand ohne automatische Grundlage
    k = {b: kf for b in BEREICHE}
    extra = {}
    hand_b = set()
    if v["stueck_min"] is not None:
        hand_b = set(BEREICHE)
        if a_stueck > 1e-9:
            k = {b: v["stueck_min"] / a_stueck for b in BEREICHE}
        else:
            k = {b: 1.0 for b in BEREICHE}
            if v["stueck_min"] > 0:
                extra[SCHWEISSEN] = v["stueck_min"]
    else:
        for b, w in v["bereiche"].items():
            hand_b.add(b)
            if ber[b]["auto_stueck"] > 1e-9:
                k[b] = w / ber[b]["auto_stueck"]
            else:
                k[b] = 1.0
                if w > 0:
                    extra[b] = w
    k_r = 1.0
    extra_r = None
    if v["ruest_min"] is not None:
        if a_ruest > 1e-9:
            k_r = v["ruest_min"] / a_ruest
        elif v["ruest_min"] > 0:
            extra_r = v["ruest_min"]
    # Zeilen und Summen anpassen (nur wo ein Faktor ≠ 1 wirkt: ohne Vorgabe bleibt alles bitgleich)
    d_stueck_min = d_stueck_eur = d_ruest_min = d_ruest_eur = d_schweiss = 0.0
    zeilen = out["zeilen"]
    for p in posten:
        kb = k[p["bereich"]]
        z = zeilen[p["zeile"]]
        if abs(kb - 1) > 1e-12 and (p["stueck_min"] or p["stueck_eur"]):
            z.setdefault("auto", dict(zeit_min=z["zeit_min"], kosten=z["kosten"], einmal=z["einmal"]))
            dm, de = p["stueck_min"] * (kb - 1), p["stueck_eur"] * (kb - 1)
            z["zeit_min"] += dm
            z["kosten"] += de
            d_stueck_min += dm
            d_stueck_eur += de
            if z["art"] == "Naht":
                d_schweiss += dm
            else:
                w = dict(z["werte"])
                f = z["faktor"] or 1
                w["laufend_min"] = (w.get("laufend_min") or 0) + dm / f
                w["laufend"] = (w.get("laufend") or 0) + de / f
                z["werte"] = w
        if abs(k_r - 1) > 1e-12 and (p["ruest_min"] or p["ruest_eur"]):
            z.setdefault("auto", dict(zeit_min=z["zeit_min"], kosten=z["kosten"], einmal=z["einmal"]))
            dm, de = p["ruest_min"] * (k_r - 1), p["ruest_eur"] * (k_r - 1)
            z["einmal"] += de
            d_ruest_min += dm
            d_ruest_eur += de
            w = dict(z["werte"])
            u = w.get("umlage_faktor") or 0
            if u:
                w["einmal_min"] = (w.get("einmal_min") or 0) + dm / u
                w["einmal"] = (w.get("einmal") or 0) + de / u
            z["werte"] = w
    fehlt_satz = False
    for b, minuten in extra.items():
        eur = minuten / 60 * satz_v if _zahl(satz_v) else 0.0
        fehlt_satz |= not _zahl(satz_v)
        zeilen.append(dict(art="Arbeitsgang", id=f"vorgabe-{b}", name=f"Zeit von Hand ({b})", knoten="", faktor=1,
                           zeit_min=minuten, kosten=eur, einmal=0.0, fremd=False, vorschlag=False, hand=True,
                           bereich=b, werte=dict(satz=satz_v, laufend_min=minuten, laufend=eur, einmal_min=0.0,
                                                 einmal=0.0, umlage="je Auftrag", umlage_faktor=1.0, fremd=False,
                                                 fehlt=None)))
        d_stueck_min += minuten
        d_stueck_eur += eur
        if b in (SCHWEISSEN, HEFTEN):
            d_schweiss += minuten
    if extra_r:
        eur = extra_r / 60 * satz_v if _zahl(satz_v) else 0.0
        fehlt_satz |= not _zahl(satz_v)
        zeilen.append(dict(art="Arbeitsgang", id="vorgabe-ruesten", name="Rüstzeit von Hand", knoten="", faktor=1,
                           zeit_min=0.0, kosten=0.0, einmal=eur, fremd=False, vorschlag=False, hand=True,
                           bereich=VORBEREITUNG,
                           werte=dict(satz=satz_v, laufend_min=0.0, laufend=0.0, einmal_min=extra_r, einmal=eur,
                                      umlage="je Auftrag", umlage_faktor=1.0, fremd=False, fehlt=None)))
        d_ruest_min += extra_r
        d_ruest_eur += eur
    if fehlt_satz:
        out["warnungen"].append("Zeit von Hand: Stundensatz fehlt (an der Vorgabe wählen)")
    if d_stueck_min or d_stueck_eur or d_ruest_min or d_ruest_eur:
        out["zeit_min"] += d_stueck_min + (d_ruest_min / n if n else 0.0)
        out["schweiss_min"] += d_schweiss
        out["eigen"] += d_stueck_eur + (d_ruest_eur / n if n else 0.0)
        out["einmal"] += d_ruest_eur / n if n else 0.0
        out["einmal_gesamt"] += d_ruest_eur
    sc = schnell(bg)
    out["schnell_material"], out["schnell_zukauf"] = sc["material_eur"], sc["zukauf_eur"]
    # Übersicht je Bereich
    liste = []
    for b in BEREICHE:
        x = ber[b]
        stueck = x["auto_stueck"] * k[b] + extra.get(b, 0.0)
        ruest = x["auto_ruest"] * k_r + (extra_r if extra_r and b == VORBEREITUNG else 0.0)
        if not (x["auto_stueck"] or x["auto_ruest"] or stueck or ruest or b in hand_b):
            continue
        liste.append(dict(bereich=b, auto_stueck=x["auto_stueck"], auto_ruest=x["auto_ruest"], stueck=stueck,
                          ruest=ruest, hand=b in hand_b))
    stueck = v["stueck_min"] if v["stueck_min"] is not None else sum(x["stueck"] for x in liste)
    ruest = v["ruest_min"] if v["ruest_min"] is not None else sum(x["ruest"] for x in liste)
    auto_stueck_k = a_stueck * kf
    out["zeiten"] = dict(auto_stueck_min=a_stueck, auto_ruest_min=a_ruest, komplex=kf, komplex_gruende=gruende,
                         auto_komplex_min=auto_stueck_k, stueck_min=stueck, ruest_min=ruest,
                         hand_stueck=v["stueck_min"] is not None, hand_ruest=v["ruest_min"] is not None,
                         hand_bereiche=sorted(v["bereiche"]), hand=bool(hand_b) or v["ruest_min"] is not None,
                         bereiche=liste, satz_id=sid, satz=satz_v, grund=v["grund"], am=v["am"],
                         auto_damals=v["auto_damals"], anzahl=n,
                         gesamt_min=ruest + stueck * n, auto_gesamt_min=a_ruest + a_stueck * n,
                         fremd_eur=out["fremd"])
    return out


def gesamt_text(z):
    """Kurztext für Kopf und Angebotsliste: 'automatisch 40 min' bzw. 'von Hand 55 min (+15 min)'."""
    if not z:
        return ""
    if z["hand"]:
        auto = z["auto_komplex_min"] if not z["hand_stueck"] else z["auto_stueck_min"]
        return f"von Hand {zeit_text(z['stueck_min'])} je BG ({abweichung_text(z['stueck_min'] - auto)})"
    t = f"automatisch {zeit_text(z['stueck_min'])} je BG"
    if abs(z["komplex"] - 1) > 1e-9:
        t += f" (Komplexität ×{z['komplex']:g})".replace(".", ",")
    return t
