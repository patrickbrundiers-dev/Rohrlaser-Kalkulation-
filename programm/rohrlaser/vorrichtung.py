"""Vorrichtungskosten vorschlagen (ASM-006, Plan N4 vom 16.11.2026, Patrick „Alle Empfehlungen“).

Vorschlag für den Einmalbetrag einer Schweißvorrichtung, nur als Vorschlag (eingetragen wird erst mit Klick):
    Betrag = (Grundbetrag + Betrag je Teil × Anzahl Teile) × Größenfaktor × (Faktor enge Toleranz, wenn angehakt)
Anzahl Teile = Einzelteile je Baugruppe (mit Stück je Unterbaugruppe), ohne Normteile/Zukauf (Bleche zählen).
Größe = größtes Maß der Baugruppe: aus dem Stammfeld „Abmessungen“ (größte Zahl in mm), sonst das längste Einzelteil
(Rohrlänge, Blech Länge/Breite). Größenfaktor: bis „Größe klein bis“ × 1, bis „Größe mittel bis“ × „Faktor mittel“,
darüber × „Faktor groß“. Die Werte stehen in den Stammdaten der Schweißbaugruppe (Tabelle schweiss_regeln, Art
„Vorrichtung“); fehlen sie, gelten die Richtwerte unten (Status Richtwert).

Wiederholauftrag (F3 a): hatte derselbe Kunde dieselbe Baugruppe (gleiche Artikelnummer, sonst gleiche Bezeichnung)
schon beauftragt und dort eine Vorrichtung mit Einmalbetrag, kommt ein Hinweis mit Knopf „Übernehmen“: die Vorrichtung
wird als „wiederverwendbar“ gerechnet (kein Einmalbetrag). Ohne Qt.
"""
import re

from . import baugruppe, blech
from .angebot import BAUGRUPPE, ist_zukaufteil

ART = "Vorrichtung"
GRUND, JE_TEIL = "Grundbetrag", "Betrag je Teil"
KLEIN_BIS, MITTEL_BIS = "Größe klein bis", "Größe mittel bis"
F_MITTEL, F_GROSS, F_ENG = "Faktor mittel", "Faktor groß", "Faktor enge Toleranz"
RICHTWERTE = (            # Art, Ausprägung, bis, Wert, Einheit (wie vorkalk.RICHTWERTE)
    (ART, GRUND, None, 150.0, "€ je Vorrichtung"),
    (ART, JE_TEIL, None, 25.0, "€ je Teil"),
    (ART, KLEIN_BIS, None, 500.0, "mm größtes Maß (Faktor 1)"),
    (ART, MITTEL_BIS, None, 1500.0, "mm größtes Maß"),
    (ART, F_MITTEL, None, 1.5, "× bis Größe mittel"),
    (ART, F_GROSS, None, 2.0, "× darüber"),
    (ART, F_ENG, None, 1.5, "× bei enger Toleranz"),
)
TOLERANZ = "toleranz_eng"           # Haken in der Baugruppe (bg[TOLERANZ] = True)


def _z(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _text(v, stellen=2):
    v = round(float(v), stellen)
    return (f"{int(v)}" if v.is_integer() else f"{v:.{stellen}f}".rstrip("0")).replace(".", ",")


def werte(tabellen):
    """{Ausprägung: (Wert, Richtwert?)} aus schweiss_regeln (Art Vorrichtung), fehlende aus RICHTWERTE."""
    da = {}
    for z in (tabellen or {}).get("schweiss_regeln") or ():
        if z.get("art") == ART and _z(z.get("zahl")) is not None:
            da[str(z.get("wert") or "").strip()] = (z["zahl"], z.get("status") == "Richtwert")
    return {w: da.get(w, (zahl, True)) for _, w, _, zahl, _ in RICHTWERTE}


def teile_anzahl(bg, positionen):
    """Einzelteile je Baugruppe ohne Normteile/Zukauf (Bleche aus dem Blech-Editor zählen)."""
    f0 = baugruppe.faktor(bg, "") or 1
    n = 0.0
    for i in baugruppe.teile(positionen, bg["id"]):
        p = positionen[i]
        if ist_zukaufteil(p) and blech.lesen(p.get("technik")) is None:
            continue
        f = baugruppe.faktor(bg, baugruppe.zuordnung(p)[1])
        if not f:
            continue
        je = p.get("je_knoten") if _z(p.get("je_knoten")) and p["je_knoten"] >= 1 else 1
        n += je * f / f0
    return round(n, 2)


def groesse(bg, positionen):
    """(größtes Maß in mm, Herkunft) oder (None, Text)."""
    zahlen = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", str((bg.get("stamm") or {})
                                                                                    .get("abmessungen") or ""))]
    zahlen = [x for x in zahlen if x > 0]
    if zahlen:
        return max(zahlen), "Abmessungen der Baugruppe"
    best = None
    for i in baugruppe.teile(positionen, bg["id"]):
        p = positionen[i]
        e = blech.lesen(p.get("technik")) if ist_zukaufteil(p) else None
        if e is not None:
            werte_ = [_z(e.get(s)) for s in ("laenge", "breite", "kantlaenge")]
        else:
            werte_ = [_z(p.get("laenge"))]
        for w in werte_:
            if w and (best is None or w > best):
                best = w
    if best:
        return best, "längstes Einzelteil"
    return None, "Größe unbekannt (Abmessungen eintragen)"


def vorschlag(bg, positionen, tabellen):
    """dict(betrag, teile, groesse, faktor_groesse, eng, richtwert, text) oder None (keine Teile)."""
    w = werte(tabellen)
    n = teile_anzahl(bg, positionen)
    if n <= 0:
        return None
    g, herkunft = groesse(bg, positionen)
    if g is None or g <= w[KLEIN_BIS][0]:
        fg = 1.0
    elif g <= w[MITTEL_BIS][0]:
        fg = w[F_MITTEL][0]
    else:
        fg = w[F_GROSS][0]
    eng = bool(bg.get(TOLERANZ))
    fe = w[F_ENG][0] if eng else 1.0
    betrag = round((w[GRUND][0] + w[JE_TEIL][0] * n) * fg * fe, 2)
    benutzt = [GRUND, JE_TEIL] + ([KLEIN_BIS, MITTEL_BIS, F_MITTEL, F_GROSS] if g else []) + ([F_ENG] if eng else [])
    richtwert = any(w[x][1] for x in benutzt)
    text = (f"{_text(w[GRUND][0])} € + {_text(n)} Teile × {_text(w[JE_TEIL][0])} €"
            + (f" × {_text(fg)} (Größe {_text(g, 0)} mm, {herkunft})" if g else f" ({herkunft})")
            + (f" × {_text(fe)} (enge Toleranz)" if eng else "") + f" = {_text(betrag)} €"
            + (" – Richtwerte, in den Stammdaten anpassen" if richtwert else ""))
    return dict(betrag=betrag, teile=n, groesse=g, faktor_groesse=fg, eng=eng, richtwert=richtwert, text=text)


def ist_vorrichtung(ag):
    return "vorrichtung" in str((ag or {}).get("name") or "").lower()


def uebernehmen(bg, betrag, neue_id=None):
    """Vorschlag eintragen: Einmalbetrag der ersten Vorrichtung ohne Umlage 'wiederverwendbar', sonst neuer
    Arbeitsgang Vorrichtung. Ergebnis: ID des Arbeitsgangs."""
    ag = next((a for a in bg["arbeitsgaenge"] if ist_vorrichtung(a) and a.get("umlage") != baugruppe.UMLAGE_WIEDER),
              None)
    if ag is None:
        ag = dict(id=neue_id or baugruppe.neue_id(), name=ART, umlage=baugruppe.UMLAGE_AUFTRAG)
        bg["arbeitsgaenge"].append(ag)
    ag["einmal_eur"] = round(float(betrag), 2)
    return ag["id"]


# ------------------------------------------------------------------ Wiederholauftrag
def _schluessel(t):
    return str(t or "").strip().casefold()


def frueher(db, angebot_id, kundennr, artikel, bezeichnung):
    """Frühere beauftragte Baugruppe desselben Kunden mit Vorrichtung (Einmalbetrag > 0): dict(nummer, datum,
    betrag, name, angebot_id) oder None. Gleiche Artikelnummer, ohne Artikelnummer gleiche Bezeichnung."""
    kn, art, bez = _schluessel(kundennr), _schluessel(artikel), _schluessel(bezeichnung)
    if db is None or not kn or not (art or bez):
        return None
    sql = ("SELECT p.artikel, p.bezeichnung, p.baugruppe, a.id AS aid, a.nummer, a.datum FROM positionen p "
           "JOIN angebote a ON a.id = p.angebot_id WHERE p.art = ? AND a.id != ? AND a.vorgang = 'Beauftragt' "
           "AND LOWER(TRIM(a.kundennr)) = ?")
    try:
        zeilen = [dict(r) for r in db.con.execute(sql, (BAUGRUPPE, angebot_id or -1, kn))]
    except Exception:           # noqa: BLE001 – nur ein Hinweis
        return None
    best = None
    for r in zeilen:
        if art:
            if _schluessel(r["artikel"]) != art:
                continue
        elif _schluessel(r["bezeichnung"]) != bez:
            continue
        bg = baugruppe.lesen(r["baugruppe"]) or {}
        vor = [a for a in bg.get("arbeitsgaenge") or () if ist_vorrichtung(a) and (_z(a.get("einmal_eur")) or 0) > 0
               and a.get("umlage") != baugruppe.UMLAGE_WIEDER]
        if not vor:
            continue
        treffer = dict(nummer=r["nummer"], datum=r["datum"], angebot_id=r["aid"], name=vor[0].get("name"),
                       betrag=round(sum(a["einmal_eur"] for a in vor), 2))
        if best is None or str(treffer["datum"] or "") > str(best["datum"] or ""):
            best = treffer
    return best


def wieder_offen(bg, treffer):
    """Gibt es noch etwas zu tun? True, wenn ein früherer Treffer da ist und die Baugruppe keine Vorrichtung mit Umlage
    'wiederverwendbar' hat."""
    return bool(treffer) and not any(ist_vorrichtung(a) and a.get("umlage") == baugruppe.UMLAGE_WIEDER
                                     for a in bg["arbeitsgaenge"])


def wieder_uebernehmen(bg, treffer, neue_id=None):
    """Vorrichtungen der Baugruppe als 'wiederverwendbar' rechnen (ohne eine: neue Zeile mit dem Betrag von damals zur
    Info). Ergebnis: Anzahl geänderter Arbeitsgänge."""
    n = 0
    for a in bg["arbeitsgaenge"]:
        if ist_vorrichtung(a) and a.get("umlage") != baugruppe.UMLAGE_WIEDER:
            a["umlage"] = baugruppe.UMLAGE_WIEDER
            n += 1
    if not n:
        bg["arbeitsgaenge"].append(dict(id=neue_id or baugruppe.neue_id(), name=ART, umlage=baugruppe.UMLAGE_WIEDER,
                                        einmal_eur=treffer.get("betrag")))
        n = 1
    return n


def _datum(d):
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2}).*", str(d or ""))
    return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else (str(d) if d else "?")


def hinweis_wieder(treffer):
    return (f"Vorrichtung schon vorhanden: Angebot {treffer['nummer']} vom {_datum(treffer.get('datum'))} (beauftragt, "
            f"Einmalbetrag {_text(treffer['betrag'])} €). Als wiederverwendbar rechnen?")
