"""Staffelpreise: jede Stufe als eigener Auftrag neu rechnen, mit eigenen Einstellungen je Stufe.

Eine Stufe (Tabelle staffel_stufen, Schema 36) hat Einstellungen wie das Hauptangebot (Gewinn, Zuschlag
Fremdleistung, Rüstzeit und Pauschale je Abmessung, Programmierkosten, Angebotsaufschlag, Handling Kundenmaterial,
Fracht, Skonto, Materialpreis €/m je Abmessung; leer = Wert des Angebots) und Mengenzeilen (Tabelle staffeln):
je Zeile ein Schlüssel (Satzbezeichnung aus der Spalte 'Satz' oder eine Positionsnummer) und eine Menge (Anzahl
Sätze bzw. Stück, „Menge ab“). Im Rechenlauf einer Stufe sind genau die Positionen ihrer Mengenzeilen besetzt
(Satz: Menge × 'Stück je Satz', Position: die Menge), alle anderen Stückzahlen sind leer. Die Stufe wird
gemeinsam optimiert und kalkuliert wie ein Auftrag: Rüsten, Stangenwechsel, Verschnitt, Programmierkosten,
Pauschalen, Angebotsaufschlag, Fracht und Mindestpreis verteilen sich auf alle Positionen der Stufe wie im
Hauptangebot. Hat eine Stufe dieselben Mengen wie das Hauptangebot und keine eigenen Werte, ergibt sie genau
dessen Preise. Mengenzeilen ohne Stufe (ältere Aufrufe) rechnen je Zeile als eigene Stufe.

Zwei Rechenschichten:
- Mengenlauf (stufe_rechnen, langsam): Optimierung und Kalkulation der Stufe. Ergebnis sind die Kostenbausteine
  ohne Zuschläge (bausteine), dazu Teile, Stangen und Hinweise. Eine Prüfsumme je Stufe (stufe_kennung) sagt,
  ob der Lauf noch zu den Eingaben passt.
- Preisschicht (preise, sofort): wendet die Werte der Stufe (leer = Wert des Angebots) auf die Bausteine an.
  Rechenreihenfolge, alle Beträge ungerundet bis zur Ausgabe:
    1 Material-Grundkosten M0 (Stangenkosten inkl. echtem Verschnitt) oder Grundpreis abweichend × Menge
    2 Materialverlust: M1 = M0 × (1 + Verlust)
    3 Materialzuschlag: M2 = M1 × (1 + Zuschlag %) oder M1 + Zuschlag € × Menge  (ersetzt 'Zuschlag Material')
    4 Fertigung (Zeit × Stundensatz je Arbeitsschritt, laufend) und Rüsten (einmal je Stufe) getrennt
    5 Gemeinkosten = (Fertigung + Rüsten) × Zuschlag Fertigung, Fremdleistung × Zuschlag Fremdleistung
    6 Selbstkosten = M2 + Fertigung + Rüsten + Gemeinkosten + Fremdleistung + Nebenkosten
    7 Gewinn = Selbstkosten × Gewinn
    8 Netto = Selbstkosten + Gewinn + Pauschalen, Programmierung, Aufschlag, Fracht (ohne Zuschläge)
      + Zukaufteile (Einstand + Aufschlag nach der Regel des Artikels, Staffel nach dem Verbrauch der Stufe),
      Skonto eingerechnet; liegt Netto unter dem Mindestpreis, gilt der Mindestpreis (Stückpreis aufgerundet);
      MwSt = Netto gesamt × MwSt-Satz
  Ohne Werte in der Stufe ergibt das genau den Verkaufspreis der Kalkulation (rechnen.kalkulation).

Blechteile aus dem Blech-Editor (Patrick 22.10.2026): weicht die Stückzahl in der Stufe von der des Angebots ab,
gilt der EK aus dem Einkauf (Staffelzeile des Preisstands ab ≤ Stückzahl, nicht vom Blech-Editor), sonst wird der
Richtpreis für die Stückzahl der Stufe neu gerechnet (Rüsten verteilt sich auf mehr oder weniger Teile; blech_stand).
"""
import hashlib
import json

from . import blech, fracht_angebot, rechnen, zukauf
from .angebot import KALKULATION, ZAHLUNG, KOPF as ANGEBOT_KOPF
from .angebot import aktiv as position_aktiv
from .ausgabe import aufrunden, kaufm_runden
from .stammdaten import Feld, kontext_aus

SPALTEN = ("schluessel", "bezeichnung", "einheit", "menge", "teile", "stangen", "material", "laser", "ruesten",
           "herstell", "herstell_einheit", "preis_einheit", "preis_gesamt", "hinweis")
MAX_STUFEN = 200
VERSION = 4          # 2: Bausteine je Stufe und Preisschicht; 3: Stufen mit mehreren Mengenzeilen als ein Auftrag;
                     # 4: Schnittschema je Stufe (ältere gespeicherte Staffelpreise gelten als veraltet)

PROZENT, EURO = "%", "€/Einheit"
UMLEGEN, SEPARAT = "umlegen", "separat"
# Felder einer Stufe (Tabelle staffeln). Leere Werte = Wert des Angebots.
STUFE_FELDER = (
    Feld("schluessel", "Satz oder Pos.", pflicht=True, breite=120),
    Feld("menge", "Menge ab [Sätze bzw. Stück]", "ganz", 1, 10000000, pflicht=True, breite=95),
    Feld("bis", "Menge bis", "ganz", 1, 10000000, breite=75),
    Feld("mat_zuschlag", "Materialzuschlag", "zahl", -100000, 100000, stellen=2, breite=90),
    Feld("mat_art", "Zuschlag in", "auswahl", auswahl="zuschlag_art", breite=80),
    Feld("gewinn", "Gewinn [%]", "zahl", -100, 500, stellen=1, breite=70),
    Feld("verlust", "Materialverlust / Ausschuss [%]", "zahl", 0, 100, stellen=1, breite=95),
    Feld("mat_grundpreis", "Material-Grundpreis abweichend [€/Einheit]", "zahl", 0, 1000000, stellen=2, breite=110),
    Feld("zuschlag_fertigung", "Gemeinkosten Fertigung [%]", "zahl", 0, 500, stellen=1, breite=95),
    Feld("ruesten", "Rüstkosten", "auswahl", auswahl="ruesten", breite=80),
    Feld("arbeitsgang", "Zusätzlicher Arbeitsgang", breite=140),
    Feld("arbeitsgang_min", "Arbeitsgang [min/Einheit]", "zahl", 0, 100000, stellen=2, breite=90),
    Feld("arbeitsgang_satz", "Arbeitsgang Stundensatz [€/h]", "zahl", 0, 10000, stellen=2, breite=95),
    Feld("arbeitsgang_eur", "Arbeitsgang [€/Einheit]", "zahl", 0, 1000000, stellen=2, breite=90),
    Feld("neben_einheit", "Verpackung / Nebenkosten [€/Einheit]", "zahl", 0, 1000000, stellen=2, breite=110),
    Feld("neben_pauschal", "Nebenkosten pauschal [€]", "zahl", 0, 1000000, stellen=2, breite=95),
    Feld("rabatt", "Rabatt erlaubt", "auswahl", auswahl="janein", breite=70),
    Feld("bemerkung", "Bemerkung", breite=200),
)
STUFE_FELD = {f.name: f for f in STUFE_FELDER}
# Mengenzeile einer Stufe (Tabelle staffeln; die übrigen Spalten der Tabelle stammen aus Schema 13–35)
MENGE_FELDER = tuple(STUFE_FELD[n] for n in ("schluessel", "menge", "bis"))
# Einstellungen einer Stufe (Tabelle staffel_stufen): wie im Angebot, dazu die Sonderwerte der Preisschicht
_KOPF_FELD = {f.name: f for f in ANGEBOT_KOPF}
EINSTELLUNG_FELDER = (
    Feld("bezeichnung", "Bezeichnung", breite=160),
    STUFE_FELD["gewinn"],
    *[f for f in KALKULATION if f.name != "gewinn"],
    _KOPF_FELD["fracht"], _KOPF_FELD["skonto"],
    *(STUFE_FELD[n] for n in ("mat_zuschlag", "mat_art", "verlust", "mat_grundpreis", "zuschlag_fertigung", "ruesten",
                              "arbeitsgang", "arbeitsgang_min", "arbeitsgang_satz", "arbeitsgang_eur", "neben_einheit",
                              "neben_pauschal", "rabatt", "bemerkung")),
    Feld("laenge_auto", "Lieferlänge je Stufe wählen", "auswahl", auswahl="janein", breite=80),
    Feld("meterpreise", "Materialpreis je Abmessung [€/m]"),     # JSON {Abmessung: €/m}
)
EINSTELLUNG_FELD = {f.name: f for f in EINSTELLUNG_FELDER}
# gehen in den Mengenlauf (Kalkulation) ein; die übrigen wirken sofort in der Preisschicht
LAUF_FELDER = ("ruesten_abmessung", "pauschale_abmessung", "programmierung_zeit", "programmierung_kontur", "programmierung_teil",
               "angebotsaufschlag", "handling_beistellung", "fracht", "skonto", "meterpreise", "laenge_auto")
# in der Stufe wie im Angebot (Hauptwerte), die übrigen unter „Erweitert“
HAUPT = ("gewinn", "zuschlag_fremdleistung", "ruesten_abmessung", "pauschale_abmessung", "programmierung_zeit",
         "programmierung_kontur", "angebotsaufschlag", "handling_beistellung", "fracht", "skonto")
assert ZAHLUNG[0] == "skonto"
# unter 'Erweiterte Einstellungen' (ausgeblendet, solange keine Stufe einen Wert hat)
ERWEITERT = ("bis", "programmierung_teil", "verlust", "mat_grundpreis", "zuschlag_fertigung", "ruesten", "arbeitsgang", "arbeitsgang_min",
             "arbeitsgang_satz", "arbeitsgang_eur", "neben_einheit", "neben_pauschal", "rabatt")
AUSWAHL = {"zuschlag_art": [PROZENT, EURO], "ruesten": [UMLEGEN, SEPARAT], "janein": ["ja", "nein"]}
# Einstellungen, die in den Mengenlauf eingehen (Zuschläge und Gewinn wirken erst in der Preisschicht)
EINST_LAUF = ("ruesten_abmessung", "pauschale_abmessung", "programmierung_zeit", "programmierung_kontur", "programmierung_teil", "angebotsaufschlag",
              "handling_beistellung")
EINST_LAENGEN = ("laenge_mindest_eur", "laenge_mindest_anteil", "zuschnitt_verlust", "zuschnitt_puffer", "zuschnitt_kosten",
                 "haendler_mehr_kurz", "haendler_mehr_lang", "haendler_mehr_grenze", "laenge_auto_huellkreis",
                 "laenge_auto", "laenge_vergleich")


def txt(v):
    """Schlüssel immer als Text vergleichen; ganze Zahlen ohne Nachkommastellen (Txt in Staffel.bas)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v) == int(v) else repr(float(v))
    return str(v).strip()


def _zahl(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def je_satz(p):
    n = _zahl(p.get("je_satz"))
    return n if n >= 1 else 1


def pruefen(stufe, positionen, alle=None):
    """Prüfspalte der Staffeln: erster Fehler der Stufe oder Art des Schlüssels. alle = alle Stufen des Angebots
    (für doppelte und überlappende Mengenbereiche)."""
    schl = txt(stufe.get("schluessel"))
    if not schl:
        return ""
    fehl = fehler(stufe, positionen, alle)
    if fehl:
        return "FEHLER: " + fehl[0][1]
    n = sum(1 for p in positionen if txt(p.get("satz")) == schl)
    if n:
        return f"Satz mit {n} Positionen"
    return "Position"


def _hat_schluessel(schl, positionen):
    return any(txt(p.get("satz")) == schl for p in positionen) or any(txt(p.get("pos")) == schl for p in positionen)


def _wert(stufe, name):
    w = stufe.get(name)
    return None if w is None or w == "" else w


def bis_wirksam(stufe, alle):
    """Höchstmenge der Stufe: eingetragen oder (leer) nächste Menge ab desselben Schlüssels − 1; None = offen."""
    if isinstance(_wert(stufe, "bis"), (int, float)):
        return stufe["bis"]
    schl, ab = txt(stufe.get("schluessel")), _zahl(stufe.get("menge"))
    naechste = [_zahl(s.get("menge")) for s in alle or () if txt(s.get("schluessel")) == schl
                and _zahl(s.get("menge")) > ab]
    return min(naechste) - 1 if naechste else None


def fehler(stufe, positionen, alle=None):
    """Eingabefehler einer Stufe: [(Feld, Text)]. Leere Liste = in Ordnung."""
    out = []
    schl = txt(stufe.get("schluessel"))
    if schl and not _hat_schluessel(schl, positionen):
        out.append(("schluessel", "Satz/Pos. nicht im Angebot"))
    ab = stufe.get("menge")
    if not isinstance(ab, (int, float)) or ab < 1 or ab != int(ab):
        out.append(("menge", "Menge fehlt"))
        return out
    bis = _wert(stufe, "bis")
    if isinstance(bis, (int, float)) and bis < ab:
        out.append(("bis", "Menge bis kleiner als Menge ab"))
    for f in STUFE_FELDER:          # Zahlen im zulässigen Bereich (z. B. aus einer geänderten Datei)
        w = _wert(stufe, f.name)
        if f.art in ("zahl", "ganz") and w is not None:
            if not isinstance(w, (int, float)) or (f.von is not None and w < f.von) or (f.bis is not None and w > f.bis):
                out.append((f.name, f"{f.titel}: unzulässiger Wert"))
        elif f.art == "auswahl" and w is not None and w not in AUSWAHL[f.auswahl]:
            out.append((f.name, f"{f.titel}: unzulässiger Wert"))
    rabatt = stufe.get("rabatt") == "ja"
    mz = _wert(stufe, "mat_zuschlag")
    if isinstance(mz, (int, float)):
        if mz < 0 and not rabatt:
            out.append(("mat_zuschlag", "negativer Materialzuschlag nur mit 'Rabatt erlaubt'"))
        elif (stufe.get("mat_art") or PROZENT) == PROZENT and not -100 <= mz <= 500:
            out.append(("mat_zuschlag", "Materialzuschlag zwischen −100 % und 500 %"))
    g = _wert(stufe, "gewinn")
    if isinstance(g, (int, float)) and g < 0 and not rabatt:
        out.append(("gewinn", "negativer Gewinn nur mit 'Rabatt erlaubt'"))
    if schl and alle:
        gleich = [s for s in alle if s is not stufe and s.get("id", object()) != stufe.get("id", 0)
                  and txt(s.get("schluessel")) == schl and isinstance(s.get("menge"), (int, float))]
        if any(s["menge"] == ab for s in gleich):
            out.append(("menge", "Menge doppelt"))
        else:
            ende = bis_wirksam(stufe, alle)
            for s in gleich:
                s_ende = bis_wirksam(s, alle)
                if (s["menge"] > ab and ende is not None and ende >= s["menge"]) \
                        or (s["menge"] < ab and s_ende is not None and s_ende >= ab):
                    out.append(("bis", "Mengenbereich überschneidet sich mit einer anderen Stufe"))
                    break
    return out


def auswahl(positionen):
    """Was sich als Stufe wählen lässt: jeder Satz und jede Position ohne Satz (mit Profil oder Zukaufteil).
    Ergebnis: [(Schlüssel, Anzeigetext, aktuelle Menge in Sätzen bzw. Stück oder None)]."""
    saetze, einzeln = {}, []
    for p in positionen:
        if not position_aktiv(p):
            continue
        s = txt(p.get("satz"))
        if s:
            saetze.setdefault(s, []).append(p)
        elif txt(p.get("pos")):
            menge = int(_zahl(p.get("stueck"))) if _zahl(p.get("stueck")) >= 1 else None
            text = f"Pos. {txt(p.get('pos'))}" + "".join(f" – {p[n]}" for n in ("artikel", "bezeichnung") if p.get(n))
            einzeln.append((txt(p.get("pos")), text, menge))
    out = []
    for s, ps in saetze.items():
        mengen = {int(_zahl(p.get("stueck")) // je_satz(p)) for p in ps if _zahl(p.get("stueck")) >= 1}
        menge = mengen.pop() if len(mengen) == 1 else None
        pos = ", ".join(txt(p.get("pos")) for p in ps)
        out.append((s, f"Satz {s} ({len(ps)} Pos.: {pos})", menge or None))
    return out + einzeln


def standard_faktoren(text):
    """Faktoren der Standard-Staffeln aus der Einstellung, z. B. '1; 2; 5' -> [1, 2, 5]. Trennzeichen ; oder
    Leerzeichen, Komma als Dezimalzeichen; ungültige, doppelte und Werte ≤ 0 entfallen, höchstens 10 Faktoren."""
    out = []
    for t in str(text or "").replace(";", " ").split():
        try:
            f = float(t.replace(",", "."))
            f = int(f) if f == int(f) else f
        except (ValueError, OverflowError):        # auch "inf" und "nan"
            continue
        if f > 0 and f not in out:
            out.append(f)
    return out[:10]


def standard_menge(menge, faktor):
    """Menge einer Standard-Staffel: Menge × Faktor, kaufmännisch gerundet, mindestens 1."""
    return max(1, int(menge * faktor + 0.5))


def gueltige(stufen):
    """Stufen, die gerechnet werden: Schlüssel gefüllt und Menge ≥ 1 (höchstens MAX_STUFEN)."""
    return [s for s in stufen if txt(s.get("schluessel")) and _zahl(s.get("menge")) >= 1][:MAX_STUFEN]


def szenario(schl, menge, positionen):
    """Stückzahlen eines Rechenlaufs. Ergebnis: (ist_satz, {Index: Stückzahl}, Bezeichnung)."""
    ist_satz = any(txt(p.get("satz")) == schl for p in positionen) and bool(schl)
    mengen, bez = {}, ""
    for i, p in enumerate(positionen):
        if not position_aktiv(p):
            continue
        if (txt(p.get("satz")) == schl) if ist_satz else (txt(p.get("pos")) == schl):
            mengen[i] = menge * (je_satz(p) if ist_satz else 1)
            if len(bez) < 60:
                if ist_satz:
                    bez += (", " if bez else "Pos. ") + txt(p.get("pos"))
                else:
                    bez = txt(p.get("bezeichnung"))
    return ist_satz, mengen, bez




# ------------------------------------------------------------------ Mengenlauf
def _gemeinsam(kopf, positionen, k, tabellen, einst):
    """Eingaben, die für alle Stufen gleich in den Mengenlauf eingehen."""
    felder = ("maschine", "stange", "fracht", "skonto", "zeitbasis")
    # Frachtfelder nur, wenn gesetzt: ältere Angebote behalten ihre Prüfsumme (keine unnötigen Mengenläufe)
    fracht_felder = ("fracht_modus", "fracht_umlage", "fracht_sendung", "fracht_auto", "fracht_plz", "fracht_land",
                     "laengenwahl")      # übernommene Lieferlängen gelten auch in den Stufen
    # Blech-Daten (Richtpreis je Stufe) nur, wenn ein Blechteil aus dem Blech-Editor im Angebot ist
    if "blech" in tabellen and not any(blech.lesen(p.get("technik")) for p in positionen):
        tabellen = {n: w for n, w in tabellen.items() if n != "blech"}
    return [{f: kopf.get(f) for f in felder + tuple(n for n in fracht_felder if kopf.get(n) is not None)},
            [{a: b for a, b in p.items() if a not in ("id", "angebot_id", "nr", "zeile")} for p in positionen],
            [k.profile, k.werkstoffe, k.maschinen, k.oberflaechen], tabellen,
            {n: einst.get(n) for n in EINST_LAUF + EINST_LAENGEN}, VERSION]


def _hash(daten):
    return hashlib.sha1(json.dumps(daten, default=str, sort_keys=True).encode()).hexdigest()


def gruppieren(mengenzeilen, stufen_daten=None):
    """[(Stufe, [Mengenzeilen])] in der Reihenfolge der Stufen (nur Stufen mit gültigen Mengenzeilen). Mengenzeilen
    ohne bekannte Stufe bilden je eine eigene Stufe mit ihren eigenen Werten (ältere Aufrufe)."""
    nach = {st["id"]: (st, []) for st in sorted(stufen_daten or (), key=lambda x: (_zahl(x.get("nr")), x["id"]))}
    lose = []
    for z in gueltige(mengenzeilen):
        if z.get("stufe_id") in nach:
            nach[z["stufe_id"]][1].append(z)
        else:
            lose.append((z, [z]))
    return [(st, mz) for st, mz in nach.values() if mz] + lose


def stufe_nummern(stufen_daten):
    """{Stufen-ID: laufende Nummer 1, 2, 3 …}."""
    return {st["id"]: n for n, st in enumerate(sorted(stufen_daten or (), key=lambda x: (_zahl(x.get("nr")), x["id"])), 1)}


def abmessung(p):
    """Abmessung für den Materialpreis einer Stufe: 'Profil · Werkstoff' (mit Oberfläche, wenn nicht roh)."""
    ob = rechnen.oberflaeche_von(p)
    return " · ".join([txt(p.get("profil_id")), txt(p.get("werkstoff_id"))] + ([ob] if ob else []))


def abmessungen(positionen):
    """Abmessungen der Rohrlaserteile mit eigenem Material: [(Abmessung, [Positionsnummern])]."""
    out = {}
    for p in positionen:
        if position_aktiv(p) and not rechnen.kein_laserteil(p) and not rechnen.beigestellt(p) and txt(p.get("profil_id")):
            out.setdefault(abmessung(p), []).append(txt(p.get("pos")))
    return list(out.items())


def meterpreise(stufe):
    """Materialpreise der Stufe {Abmessung: €/m} (nur Werte > 0)."""
    m = (stufe or {}).get("meterpreise")
    if isinstance(m, str):
        try:
            m = json.loads(m)
        except ValueError:
            m = None
    return {a: w for a, w in (m or {}).items() if isinstance(w, (int, float)) and not isinstance(w, bool) and w > 0}


def stufe_kopf(kopf, stufe):
    """Angebotskopf mit den Werten der Stufe (leer = Angebot): Kalkulationswerte, Fracht (fester Betrag) und Skonto."""
    k2 = dict(kopf)
    k2.pop("stangen_vorgabe", None)     # von Hand vorgegebene Stangen gelten nur für die Menge des Angebots
    for f in KALKULATION:
        w = (stufe or {}).get(f.name)
        if isinstance(w, (int, float)) and not isinstance(w, bool):
            k2[f.name] = w
    w = (stufe or {}).get("fracht")
    if isinstance(w, (int, float)) and not isinstance(w, bool) and stufe.get("schluessel") is None:
        k2.update(fracht=w, fracht_modus=fracht_angebot.MANUELL, fracht_auto=None)
    w = (stufe or {}).get("skonto")
    if isinstance(w, (int, float)) and not isinstance(w, bool) and stufe.get("schluessel") is None:
        k2["skonto"] = w
    return k2


def stufe_einst(kopf, stufe, einst):
    """Einstellungen einer Stufe: die des Angebots mit den Kalkulationswerten der Stufe."""
    return rechnen.einstellungen_angebot({f.name: (stufe or {}).get(f.name) for f in KALKULATION}, einst)


def lauf_kennung(gemeinsam, stufe, mz):
    """Prüfsumme eines Mengenlaufs: gemeinsame Eingaben, Mengenzeilen und die Werte der Stufe, die in die
    Kalkulation eingehen (LAUF_FELDER)."""
    g = gemeinsam if isinstance(gemeinsam, str) else _hash(gemeinsam)
    werte = {f: stufe.get(f) for f in LAUF_FELDER if stufe.get(f) not in (None, "")} \
        if stufe.get("schluessel") is None else {}
    return _hash([g, sorted((txt(z.get("schluessel")), z.get("menge")) for z in mz), werte])


def stufe_kennung(gemeinsam, schl, menge):
    """Prüfsumme des Mengenlaufs einer einzelnen Mengenzeile (eigene Stufe ohne Werte)."""
    return lauf_kennung(gemeinsam, {"schluessel": schl}, [dict(schluessel=schl, menge=menge)])


def _zusammen(stufe, z):
    """Werte einer Mengenzeile für die Preisschicht: Einstellungen der Stufe + Schlüssel, Menge, bis, ID."""
    if stufe is z:
        return z
    out = {f.name: stufe.get(f.name) for f in EINSTELLUNG_FELDER}
    out.update({n: z.get(n) for n in ("id", "schluessel", "menge", "bis")})
    return out


def rechnen_alle(kopf, positionen, stufen, k, tabellen, einst, fortschritt=None, alt=None, ohne_lauf=False,
                 stufen_daten=None):
    """Alle gültigen Stufen rechnen. stufen = Mengenzeilen (Tabelle staffeln), stufen_daten = Stufen mit ihren
    Einstellungen (Tabelle staffel_stufen). Ergebnis: je Mengenzeile ein dict (Spalten aus SPALTEN, bausteine,
    Preise, stufe_nr, gemeinsam = Stufe mit mehreren Mengenzeilen).
    alt: bisherige Zeilen; Stufen mit unveränderter Prüfsumme werden übernommen statt neu optimiert.
    ohne_lauf: nur die Preisschicht; Stufen ohne passenden Mengenlauf bekommen Zeilen 'VERALTET'.
    fortschritt(i, n) wird vor jedem Mengenlauf aufgerufen und kann mit False abbrechen (Ergebnis dann None)."""
    g = _hash(_gemeinsam(kopf, positionen, k, tabellen, einst))
    vorher = {(z.get("kennung_stufe"), txt(z.get("schluessel")), z.get("menge")): z for z in alt or ()
              if z.get("bausteine") or z.get("hinweis")}
    gruppen = gruppieren(stufen, stufen_daten)
    nummer = stufe_nummern(stufen_daten)

    def da(st, mz):
        kenn = lauf_kennung(g, st, mz)
        return all((kenn, txt(z["schluessel"]), z["menge"]) in vorher for z in mz)
    neu = [x for x in gruppen if not da(*x)]
    # doppelte Mengen und Mengenbereiche nur unter Stufen mit denselben Sätzen und Positionen vergleichen
    art = {id(st): frozenset(txt(z["schluessel"]) for z in mz) for st, mz in gruppen}
    vergleich = {a: [z for st, mz in gruppen if art[id(st)] == a for z in mz] for a in set(art.values())}
    zeilen, n = [], 0
    for lfd, (st, mz) in enumerate(gruppen, 1):
        kenn = lauf_kennung(g, st, mz)
        if da(st, mz):
            lz = [dict(vorher[(kenn, txt(z["schluessel"]), z["menge"])]) for z in mz]
        elif ohne_lauf:
            lz = []
            for z in mz:
                ist_satz = any(txt(p.get("satz")) == txt(z["schluessel"]) for p in positionen)
                x = dict.fromkeys(SPALTEN)
                x.update(schluessel=txt(z["schluessel"]), menge=z["menge"], einheit="Satz" if ist_satz else "Stück",
                         bausteine=None, hinweis="VERALTET – wird neu gerechnet")
                lz.append(x)
        else:
            if fortschritt and fortschritt(n, len(neu)) is False:
                return None
            n += 1
            lz = stufe_lauf(kopf, positionen, st, mz, k, tabellen, einst)
            for x in lz:
                x["kennung_stufe"] = kenn
        for x, z in zip(lz, mz):
            x.update(stufe_id=z.get("id"), stufe=st.get("id") if st is not z else None,
                     stufe_nr=nummer.get(st.get("id"), lfd) if st is not z else lfd, gemeinsam=len(mz) > 1,
                     stufe_name=st.get("bezeichnung") if st is not z else None)
        zeilen += stufe_bepreisen(lz, st, mz, stufe_einst(kopf, st, einst), vergleich[art[id(st)]], positionen)
    return zeilen


def stufe_bepreisen(lz, stufe, mz, einst, alle=None, positionen=None):
    """Preisschicht einer Stufe: jede Mengenzeile mit den Werten der Stufe bepreisen; der Mindestpreis gilt für die
    ganze Stufe (alle Stückpreise anteilig angehoben), Nebenkosten pauschal nach Anteil am Verkaufspreis."""
    vk = [_zahl((x.get("bausteine") or {}).get("verkauf")) for x in lz]
    summe_vk = sum(vk)
    werte = []
    for x, z, v in zip(lz, mz, vk):
        w = _zusammen(stufe, z)
        if len(mz) > 1 and _zahl(w.get("neben_pauschal")):
            w = dict(w, neben_pauschal=w["neben_pauschal"] * (v / summe_vk if summe_vk else 1 / len(mz)))
        werte.append(w)
    ohne = dict(einst, mindestpreis=0)
    erste = [preise_anwenden(x, w, ohne, alle, positionen) for x, w in zip(lz, werte)]
    mindest = _zahl(einst.get("mindestpreis"))
    netto = sum(x["preis"]["netto"] for x in erste if x.get("preis"))
    if not (mindest > 0 and 0 < netto < mindest):
        return [preise_anwenden(x, w, einst, alle, positionen, anhebung=0.0) for x, w in zip(lz, werte)]
    faktor = mindest / netto
    return [preise_anwenden(x, w, einst, alle, positionen,
                            anhebung=(e["preis"]["netto"] * (faktor - 1) if e.get("preis") else 0.0))
            for x, w, e in zip(lz, werte, erste)]


def stufe_rechnen(kopf, positionen, schl, menge, k, tabellen, einst, mit_preis=True, stufe=None):
    """Mengenlauf einer einzelnen Mengenzeile als eigene Stufe; mit_preis: gleich mit den Werten der Stufe (stufe,
    leer = Angebot) bepreisen."""
    z = dict(stufe or {}, schluessel=schl, menge=menge)
    x = stufe_lauf(kopf, positionen, z, [z], k, tabellen, einst)[0]
    return stufe_bepreisen([x], z, [z], stufe_einst(kopf, z, einst))[0] if mit_preis else x


# (Name, Feld je Teil, Erklärung) der Fertigung und des Rüstens je Satz bzw. Position
_FERTIGUNG = (("Laser schneiden", "laser_schneiden_teil", "Schneidzeit × Stundensatz Laser"),
              ("Gewinde", "gewinde_teil", "Gewindezeit × Stundensatz bzw. Festpreis"),
              ("Weitere Arbeitsschritte", "arbeit_teil", "Reiter Zeiten & Arbeitskosten"),
              ("Zusatzarbeiten", "zusatz_eigen_teil", "Stammdaten Zusatzarbeiten"),
              ("Handling Kundenmaterial", "handling_teil", "€/m × Stangenlänge Kundenmaterial"),
              ("Schweißbaugruppe", "bg_laufend_eigen_teil", "Nahtgruppen und Arbeitsgänge der Baugruppe"))
_RUESTEN = (("Rüsten Maschine", "ruesten_maschine_teil", "Rüstzeit der Maschine, auf alle Teile der Stufe umgelegt"),
            ("Rüsten je Abmessung", "ruesten_abm_teil", "Rüstzeit je Abmessung, auf deren Teile umgelegt"),
            ("Stangenwechsel", "stangenwechsel_teil", "Stangenwechsel der Stufe, auf alle Teile umgelegt"),
            ("Schweißbaugruppe einmalig", "bg_einmal_ruesten_teil",
             "Rüstzeit und Einmalbeträge der Arbeitsgänge (Vorrichtung …), einmal je Stufe"))


def _bausteine_teil(kz, idx, summen):
    """Kostenbausteine der Positionen idx (ein Satz bzw. eine Position) aus der Kalkulation der Stufe."""
    zeilen = [kz[i] for i in idx if kz[i] is not None]

    def summe(n):
        return sum(_zahl(z.get(n)) * _zahl(z.get("stueck")) for z in zeilen)
    fert = [(n, summe(f), e) for n, f, e in _FERTIGUNG if n == "Laser schneiden" or abs(summe(f)) >= 0.005]
    ruest = [(n, summe(f), e) for n, f, e in _RUESTEN if n == "Rüsten Maschine" or abs(summe(f)) >= 0.005]
    ohne_preis = sum(1 for z in zeilen if not z["material_gruppe"] and not z.get("zukaufteil") and not z.get("baugruppe")
                     and not (z.get("kundenmaterial") and z["eingeplant"]))      # Kundenmaterial: 0 € ist richtig
    return dict(material=summe("material_teil"), material_fehlt=ohne_preis, fertigung=fert, ruesten=ruest,
                fremd=summe("zusatz_fremd_teil") + summe("bg_fremd_staffel_teil"),
                bg_getrennt=(summe("bg_getrennt_eigen_teil"), summe("bg_getrennt_fremd_teil")),
                pauschalen=summe("pauschale_abm_teil"),
                programmierung=summe("programmierung_anteil"), angebotsaufschlag=summe("angebotsaufschlag_teil"),
                fracht=summe("fracht_teil"), skonto_satz=summen["skonto_satz"], satz_maschine=summen["satz_maschine"],
                zukauf_einstand=summe("zukauf_einstand_teil"), zukauf_aufschlag=summe("zukauf_aufschlag_teil"),
                zukauf_fehlt=sum(_zahl(z.get("zukauf_fehlt")) for z in zeilen), verkauf=summe("preis_teil"))


def richtpreis_zeilen(e, p, daten):
    """Staffelzeilen (ab, Preis) des Preisstands, die vom Blech-Editor stammen: die beim Übernehmen gemerkten
    (e['richtpreise']); ältere Positionen ohne Merkliste: (None, Richtpreis für die Stückzahl der Position) = jede
    Zeile mit diesem Preis."""
    out = {(float(r["ab"]), round(float(r["preis"]), 2)) for r in e.get("richtpreise") or ()
           if isinstance(r, dict) and isinstance(r.get("ab"), (int, float)) and isinstance(r.get("preis"), (int, float))}
    if not out and daten:
        rp = blech.rechnen(dict(e, stueck=p.get("stueck") or e.get("stueck")), daten.get("werkstoffe") or {},
                           daten.get("laser") or [], daten.get("einst")).get("richtpreis")
        if rp:
            out |= {(None, round(rp, 2))}
    return out


def blech_stand(p, stueck, daten):
    """Zukaufliste eines Blechteils aus dem Blech-Editor für die Stückzahl einer Stufe: EK aus dem Einkauf, wenn
    eine Staffelzeile ab ≤ Stückzahl nicht vom Blech-Editor stammt, sonst der Richtpreis für diese Stückzahl neu
    gerechnet (daten = tabellen['blech']: werkstoffe, laser, einst). Ergebnis: (Liste, Hinweis) oder (None, None),
    wenn alles bleibt (gleiche Stückzahl wie im Angebot, kein Blechteil, Daten fehlen)."""
    e = blech.lesen(p.get("technik"))
    liste = zukauf.json_liste(p.get("zukauf"))
    if e is None or not liste or not rechnen.ist_zukaufteil(p) or not stueck or stueck == p.get("stueck"):
        return None, None
    st = dict(liste[0].get("stand") or {})
    bezug = dict(st.get("bezug") or {})
    richt = richtpreis_zeilen(e, p, daten)
    preise_rp = {pr for ab, pr in richt if ab is None}         # nur ältere Positionen: am Preis erkannt

    def vom_editor(z):
        return (float(z["ab"]), round(float(z["preis"]), 2)) in richt or round(float(z["preis"]), 2) in preise_rp
    verbrauch = float(zukauf.dez(liste[0].get("menge")) or 1) * zukauf.bezugsmenge(liste[0], p, stueck)
    einkauf = [z for z in zukauf.staffel_sortiert(bezug.get("preise")) if z["preis"] > 0 and not vom_editor(z)]
    pos = txt(p.get("pos"))
    if any(float(z["ab"]) <= verbrauch for z in einkauf):
        bezug["preise"] = [dict(ab=float(z["ab"]), preis=float(z["preis"])) for z in einkauf]
        z = zukauf.staffel_wahl(einkauf, verbrauch)
        text = f"Pos. {pos} Blech: EK Einkauf ab {rechnen.zahl(float(z['ab']), 0)} St"
    else:
        if not daten:
            return None, None
        erg = blech.rechnen(dict(e, stueck=stueck), daten.get("werkstoffe") or {}, daten.get("laser") or [],
                            daten.get("einst"))
        if not erg.get("richtpreis"):
            return None, None
        # Richtpreis je Stück: ohne Preiseinheit und Rabatt des Lieferanten
        bezug.update(preise=[dict(ab=1, preis=erg["richtpreis"])], preiseinheit=1, rabatt=None)
        text = f"Pos. {pos} Blech: Richtpreis {rechnen.zahl(erg['richtpreis'], 2)} € für {stueck:g} St"
    st["bezug"] = bezug
    return [dict(liste[0], stand=st)] + liste[1:], text


def stufe_lauf(kopf, positionen, stufe, mz, k, tabellen, einst):
    """Mengenlauf einer Stufe: alle Mengenzeilen zusammen optimieren und kalkulieren wie ein Auftrag (mit den
    Werten der Stufe). Ergebnis: je Mengenzeile eine Zeile mit den Bausteinen ihres Satzes bzw. ihrer Position
    (noch ohne Preisschicht)."""
    kopf = stufe_kopf(kopf, stufe)
    einst = stufe_einst(kopf, stufe, einst)
    mengen, je, doppelt = {}, [], set()
    for z in mz:
        schl = txt(z.get("schluessel"))
        ist_satz, m, bez = szenario(schl, z["menge"], positionen)
        doppelt |= set(m) & set(mengen)
        mengen.update(m)
        x = dict.fromkeys(SPALTEN)
        x.update(schluessel=schl, einheit="Satz" if ist_satz else "Stück", menge=z["menge"], bausteine=None,
                 bezeichnung=bez)
        je.append((x, m))

    def alle_mit(hinweis):
        for x, m in je:
            x["hinweis"] = hinweis if m else "FEHLER: Satz/Pos. nicht im Angebot"
        return [x for x, _ in je]
    if not mengen:
        return alle_mit("FEHLER: Satz/Pos. nicht im Angebot")
    if doppelt:
        pos = ", ".join(sorted({txt(positionen[i].get("pos")) for i in doppelt}))
        return alle_mit(f"FEHLER: Pos. {pos} steht in der Stufe doppelt (als Satz und als Position)")
    lauf = [dict(p, stueck=mengen.get(i)) for i, p in enumerate(positionen)]
    blech_text = {}
    for i, p in enumerate(positionen):          # Blechteile: EK aus dem Einkauf oder Richtpreis für die Stufe
        neu, text = blech_stand(p, mengen.get(i), tabellen.get("blech"))
        if neu is not None:
            lauf[i]["zukauf"] = json.dumps(neu, ensure_ascii=False)
            blech_text[i] = text
    mp = meterpreise(stufe) if stufe.get("schluessel") is None else {}
    for p in lauf:                  # Materialpreis der Stufe je Abmessung (statt des Angebots)
        if mp.get(abmessung(p)) and not rechnen.beigestellt(p):
            p["preis_m"] = mp[abmessung(p)]
    werte = [rechnen.position_werte(p, kopf, k, tabellen) if position_aktiv(p) else None for p in lauf]
    betrag, fracht_text, fracht_fehler = fracht_angebot.stufe(kopf, lauf, werte)
    if fracht_fehler:           # nie still mit 0 € Fracht rechnen
        return alle_mit(fracht_fehler)
    kopf = dict(kopf, fracht=betrag)
    # wie das Angebot: dieselben Lieferlängen, damit gleiche Mengen den gleichen Preis ergeben; auf Wunsch je Stufe
    # die empfohlene Lieferlänge (z. B. 12 m erst bei großen Mengen)
    erg = rechnen.optimieren(kopf, lauf, k, tabellen, einst, auto=stufe.get("laenge_auto") == "ja")
    if erg["neue_profile"]:      # Profil aus dem Namen gilt für diesen Lauf als angelegt
        k = kontext_aus({"profile": list(k.profile.values()) + erg["neue_profile"],
                         "werkstoffe": list(k.werkstoffe.values()), "maschinen": list(k.maschinen.values()),
                         "oberflaechen": list(k.oberflaechen.values())}, k.profilformen, k.kategorien)
    kz, summen = rechnen.kalkulation(kopf, lauf, erg, k, tabellen, einst)
    gemeinsam = []
    if summen.get("fracht_hinweis"):
        gemeinsam.append(summen["fracht_hinweis"])
    if fracht_text:
        gemeinsam.append(fracht_text)
    je[0][0]["schnittschema"] = schnittschema(kopf, lauf, erg, k, tabellen)    # einmal je Stufe
    for x, m in je:
        if not m:
            x["hinweis"] = "FEHLER: Satz/Pos. nicht im Angebot"
            continue
        b = _bausteine_teil(kz, m, summen)
        offen = sum(_zahl(kz[i]["nicht_eingeplant"]) for i in m if kz[i] is not None)
        hinweise = sum(1 for i in m if kz[i] is not None and kz[i]["hinweis"])
        text = [f"WARNUNG: {offen:.0f} Teile nicht eingeplant"] if offen > 0 else []
        if hinweise:
            text.append(f"{hinweise} Hinweis(e) in der Kalkulation")
        text += [blech_text[i] for i in sorted(m) if i in blech_text]
        x.update(teile=summen["teile"], stangen=summen["stangen"], material=b["material"],
                 laser=sum(w for _, w, _ in b["fertigung"]), ruesten=sum(w for _, w, _ in b["ruesten"]), bausteine=b,
                 hinweis="; ".join(text + gemeinsam) or None)
    return [x for x, _ in je]


def schnittschema(kopf, positionen, erg, k, tabellen):
    """Schnittschema eines Mengenlaufs (Patrick 26.10.2026: je Staffel sehen, woraus der Materialpreis kommt):
    stangen = Stangen des Schnittplans (wie rechnen.optimieren), werte = rechnen.stangen_werte, abmessungen = je
    Abmessung dict(profil, werkstoff, oberflaeche, stange, kunde, positionen, stangen, laengen [[Länge, Anzahl]],
    meter, nutz_m, kg, preis_m (€/m, mit dem die Stangen rechnen), kosten (Stangenkosten inkl. Verschnitt),
    ausnutzung). None ohne Stangen."""
    if not (erg or {}).get("stangen"):
        return None
    abm = []
    for g in rechnen.material_abmessungen(kopf, positionen, erg, k, tabellen):
        if not g["stangen"]:
            continue
        abm.append(dict(profil=g["profil"], werkstoff=g["werkstoff"], oberflaeche=g["oberflaeche"], stange=g["stange"],
                        kunde=bool(g["kunde"]), positionen=[txt(x) for x in g["positionen"]], stangen=g["stangen"],
                        laengen=sorted([[ln, n] for ln, n in g["laengen"].items()]), meter=g["meter"],
                        nutz_m=g["nutz_m"], kg=g["kg"], preis_m=None if g["kunde"] else g["wirksam"],
                        kosten=g["kosten"], ausnutzung=g["ausnutzung"]))
    return dict(stangen=erg["stangen"], werte=rechnen.stangen_werte(erg, kopf, positionen, k, tabellen),
                abmessungen=abm)


def schema_der_zeile(zeilen, z):
    """Schnittschema der Stufe einer Ergebniszeile (gespeichert an einer Zeile der Stufe) oder None."""
    if z.get("schnittschema"):
        return z["schnittschema"]
    if z.get("stufe") is None:
        return None
    return next((x["schnittschema"] for x in zeilen if x.get("stufe") == z["stufe"] and x.get("schnittschema")), None)


def bausteine(summen, ohne_materialpreis=0):
    """Kostenbausteine eines Mengenlaufs ohne Zuschläge und Gewinn (Beträge für die ganze Stufe).
    fertigung/ruesten: [(Arbeitsschritt, Betrag, Erklärung)]; die Arbeitsschritte kommen aus summen['zeiten'],
    Rüstzeiten der weiteren Arbeitsschritte zählen zum Rüsten, ihre Zeit je Einheit zur Fertigung."""
    fert, ruest = [], []
    for z in summen["zeiten"]:
        if z["schritt"] in ("Programmierung", "Zusatzarbeiten (€)"):
            continue
        texte = rechnen.schritt_texte(z)
        if z["schritt"] in ("Rüsten Maschine", "Rüsten je Abmessung"):
            ruest.append((z["schritt"], z["kosten"], f"{texte[1]} × {texte[4]} €/h"))
        elif z["fest"]:
            fert.append((z["schritt"], z["kosten"], f"{texte[0]}, {texte[2]} je Einheit, {texte[3]}, {texte[4]} €/h"
                         if z["satz"] is not None else "ohne Zeit (Festpreis)"))
        else:
            r = _zahl(z["ruest_min"]) / 60 * _zahl(z["satz"])
            if abs(r) >= 0.005:
                ruest.append((f"{z['schritt']} (Rüsten)", r, f"{texte[1]} × {texte[4]} €/h"))
            if abs(z["kosten"] - r) >= 0.005:
                fert.append((z["schritt"], z["kosten"] - r, f"{texte[0]} × {texte[2]}, {texte[4]} €/h"))
    if abs(summen["zusatz_eigen"]) >= 0.005:
        fert.append(("Zusatzarbeiten", summen["zusatz_eigen"], "Stammdaten Zusatzarbeiten"))
    if abs(summen.get("handling_beistellung", 0)) >= 0.005:
        fert.append(("Handling Kundenmaterial", summen["handling_beistellung"], "€/m × Stangenlänge Kundenmaterial"))
    if abs(summen.get("baugruppe_laufend_eigen", 0)) >= 0.005:
        fert.append(("Schweißbaugruppen", summen["baugruppe_laufend_eigen"], "Nahtgruppen und Arbeitsgänge"))
    if abs(summen.get("baugruppe_einmal_ruesten", 0)) >= 0.005:
        ruest.append(("Schweißbaugruppen einmalig", summen["baugruppe_einmal_ruesten"],
                      "Rüstzeit und Einmalbeträge der Arbeitsgänge"))
    return dict(material=summen["material"], material_fehlt=ohne_materialpreis, fertigung=fert, ruesten=ruest,
                fremd=summen["zusatz_fremd"] + summen.get("baugruppe_fremd_staffel", 0.0),
                bg_getrennt=(summen.get("baugruppe_getrennt_eigen", 0.0), summen.get("baugruppe_getrennt_fremd", 0.0)),
                pauschalen=summen["pauschalen"],
                programmierung=summen["programmierung"], angebotsaufschlag=summen["angebotsaufschlag"],
                fracht=summen["fracht"], skonto_satz=summen["skonto_satz"], satz_maschine=summen["satz_maschine"],
                zukauf_einstand=summen.get("zukauf_einstand", 0), zukauf_aufschlag=summen.get("zukauf_aufschlag", 0),
                zukauf_fehlt=summen.get("zukauf_fehlt", 0), verkauf=summen["verkauf"])


# ------------------------------------------------------------------ Preisschicht
def wirksam(stufe, einst):
    """Werte der Stufe, leere Werte aus dem Angebot (einst = rechnen.einstellungen_angebot, Prozent als Anteil).
    Ergebnis in Anteilen bzw. Euro."""
    w = lambda n: _wert(stufe, n)
    art = w("mat_art") or PROZENT
    mz = w("mat_zuschlag")
    if mz is None:
        art, mz = PROZENT, 100 * _zahl(einst.get("zuschlag_material"))
    return dict(mat_art=art, mat_zuschlag=mz / 100 if art == PROZENT else mz,
                verlust=_zahl(w("verlust")) / 100, mat_grundpreis=w("mat_grundpreis"),
                zuschlag_fertigung=(w("zuschlag_fertigung") / 100 if w("zuschlag_fertigung") is not None
                                    else _zahl(einst.get("zuschlag_fertigung"))),
                zuschlag_fremdleistung=_zahl(einst.get("zuschlag_fremdleistung")),
                gewinn=w("gewinn") / 100 if w("gewinn") is not None else _zahl(einst.get("gewinn")),
                ruesten=w("ruesten") or UMLEGEN, arbeitsgang=w("arbeitsgang"),
                arbeitsgang_min=_zahl(w("arbeitsgang_min")), arbeitsgang_satz=w("arbeitsgang_satz"),
                arbeitsgang_eur=_zahl(w("arbeitsgang_eur")), neben_einheit=_zahl(w("neben_einheit")),
                neben_pauschal=_zahl(w("neben_pauschal")), mwst=_zahl(einst.get("mwst")),
                mindestpreis=_zahl(einst.get("mindestpreis")),
                selbst_basis=rechnen.gewinn_auf_selbstkosten(einst))


def preise(b, menge, w, anhebung=None):
    """Preisschicht: Bausteine b eines Mengenlaufs, Menge der Stufe, Werte w (wirksam). Beträge für die ganze
    Stufe, ungerundet; gerundet sind nur preis_einheit, einmalig, preis_gesamt, mwst und brutto.
    Fehler (Materialpreis fehlt, Rabatt zu groß): dict mit 'fehler' und ohne Preise.
    anhebung: Anhebung auf den Mindestpreis (€, aus stufe_bepreisen für die ganze Stufe); None = Mindestpreis
    für diese Zeile allein."""
    if b["material_fehlt"] and w["mat_grundpreis"] is None:
        return dict(fehler="Materialpreis fehlt (kein Preis in den Stammdaten oder kein Schnittplan)")
    if b.get("zukauf_fehlt"):
        return dict(fehler="Zukaufteil ohne Einkaufspreis")
    m0 = b["material"] if w["mat_grundpreis"] is None else w["mat_grundpreis"] * menge
    verlust = m0 * w["verlust"]
    m1 = m0 + verlust
    mz = m1 * w["mat_zuschlag"] if w["mat_art"] == PROZENT else w["mat_zuschlag"] * menge
    if m1 + mz < -1e-9:
        return dict(fehler="Materialrabatt größer als die Materialkosten")
    fert = [(n, x, e) for n, x, e in b["fertigung"]]
    if w["arbeitsgang_min"] or w["arbeitsgang_eur"]:
        satz = w["arbeitsgang_satz"] if w["arbeitsgang_satz"] is not None else b["satz_maschine"]
        x = w["arbeitsgang_min"] * menge / 60 * _zahl(satz) + w["arbeitsgang_eur"] * menge
        e = (f"{rechnen.zahl(w['arbeitsgang_min'], 2)} min × {rechnen.zahl(menge, 0)} / 60 × {rechnen.zahl(satz, 2)} €/h"
             if w["arbeitsgang_min"] else "") + (" + " if w["arbeitsgang_min"] and w["arbeitsgang_eur"] else "") \
            + (f"{rechnen.zahl(w['arbeitsgang_eur'], 2)} € × {rechnen.zahl(menge, 0)}" if w["arbeitsgang_eur"] else "")
        fert.append((w["arbeitsgang"] or "Zusätzlicher Arbeitsgang", x, e))
    f_sum = sum(x for _, x, _ in fert)
    r_sum = sum(x for _, x, _ in b["ruesten"])
    gk_f = (f_sum + r_sum) * w["zuschlag_fertigung"]
    gk_fl = b["fremd"] * w["zuschlag_fremdleistung"]
    neben = w["neben_einheit"] * menge + w["neben_pauschal"]
    ge, gf = b.get("bg_getrennt") or (0.0, 0.0)          # Einmalkosten der Baugruppen mit eigener Zeile
    bg_selbst = ge * (1 + w["zuschlag_fertigung"]) + gf * (1 + w["zuschlag_fremdleistung"])
    herstell = m0 + verlust + mz + f_sum + r_sum + gk_f + b["fremd"] + gk_fl + neben + bg_selbst
    zk_e, zk_a = b.get("zukauf_einstand", 0), b.get("zukauf_aufschlag", 0)     # fehlt in älteren Mengenläufen
    sk = min(max(b["skonto_satz"], 0), 50) / 100
    # Selbstkosten = Herstellkosten + Pauschalen + Programmierung + Angebotsaufschlag + Zukaufteile; Gewinn darauf,
    # Fracht ohne Gewinn danach (festgeschrieben vor dem 23.10.2026: Gewinn nur auf die Herstellkosten, wie bisher)
    selbst = herstell + b["pauschalen"] + b["programmierung"] + b["angebotsaufschlag"] + zk_e + zk_a
    if w.get("selbst_basis", True):
        gewinn = selbst * w["gewinn"]
        ohne = selbst + gewinn + b["fracht"]
    else:
        gewinn = herstell * w["gewinn"]
        weitere = b["pauschalen"] + b["programmierung"] + b["angebotsaufschlag"] + b["fracht"]
        ohne = herstell + gewinn + weitere + zk_e + zk_a
    netto = ohne / (1 - sk)
    # Mindestpreis netto je Stufe (jede Stufe ist ein eigenes Angebot): Stückpreis anheben, auf den Cent aufgerundet
    if anhebung is None:
        mindest = _zahl(w.get("mindestpreis"))
        anhebung = mindest - netto if mindest > 0 and 0 < netto < mindest else 0.0
    netto += anhebung
    einmalig = 0.0
    if w["ruesten"] == SEPARAT:     # Rüsten mit Gemeinkosten, Gewinn und Skonto als einmalige Position
        einmalig = kaufm_runden(r_sum * (1 + w["zuschlag_fertigung"]) * (1 + w["gewinn"]) / (1 - sk), 2)
    # Einmalkosten von Schweißbaugruppen mit eigener Zeile: immer einmalig, nicht im Stückpreis
    bg_einmalig = kaufm_runden(bg_selbst * (1 + w["gewinn"]) / (1 - sk), 2) if bg_selbst else 0.0
    einmalig += bg_einmalig
    preis_einheit = (aufrunden((netto - einmalig) / menge) if anhebung
                     else kaufm_runden((netto - einmalig) / menge, 2))
    gesamt = kaufm_runden(preis_einheit * menge + einmalig, 2)
    mwst = kaufm_runden(gesamt * w["mwst"], 2)
    return dict(fehler=None, m_grund=m0, m_verlust=verlust, m_zuschlag=mz, m_gesamt=m1 + mz, fertigung=fert,
                fert_gesamt=f_sum, ruesten=b["ruesten"], ruest_gesamt=r_sum, gk_fertigung=gk_f, fremd=b["fremd"],
                gk_fremd=gk_fl, neben=neben, herstell=herstell, selbst=selbst, gewinn=gewinn,
                marge=gewinn / netto if netto else None, pauschalen=b["pauschalen"],
                programmierung=b["programmierung"], angebotsaufschlag=b["angebotsaufschlag"], fracht=b["fracht"],
                zukauf_einstand=zk_e, zukauf_aufschlag=zk_a,
                skonto=netto - anhebung - ohne, mindest_anhebung=anhebung, netto=netto, einmalig=einmalig,
                bg_einmalig=bg_einmalig, preis_einheit=preis_einheit,
                preis_gesamt=gesamt, mwst=mwst, brutto=kaufm_runden(gesamt + mwst, 2))


def preise_anwenden(z, stufe, einst, alle=None, positionen=None, anhebung=None):
    """Zeile eines Mengenlaufs mit den Werten der Stufe bepreisen (ohne neue Optimierung)."""
    z = dict(z)
    w = wirksam(stufe, einst)
    z.update(wirksam=w, preis=None, herstell=None, herstell_einheit=None, preis_einheit=None, preis_gesamt=None,
             bis=bis_wirksam(stufe, alle) if alle is not None else _wert(stufe, "bis"))
    hinweis = [t for t in (z.get("hinweis") or "").split("; ") if t and not t.startswith("FEHLER: ")
               or t == "FEHLER: Satz/Pos. nicht im Angebot"]
    fehl = fehler(stufe, positionen, alle) if positionen is not None else []
    if not z.get("bausteine"):
        z["hinweis"] = "; ".join(hinweis) or None
        return z
    if fehl:
        hinweis.insert(0, "FEHLER: " + fehl[0][1])
    else:
        p = preise(z["bausteine"], z["menge"], w, anhebung)
        if p["fehler"]:
            hinweis.insert(0, "FEHLER: " + p["fehler"])
        else:
            z.update(preis=p, herstell=p["herstell"], herstell_einheit=p["herstell"] / z["menge"],
                     preis_einheit=p["preis_einheit"], preis_gesamt=p["preis_gesamt"])
    z["hinweis"] = "; ".join(hinweis) or None
    return z


def kennung(kopf, positionen, stufen, k, tabellen, einst, stufen_daten=None):
    """Prüfsumme über alle Mengenläufe; weicht sie ab, sind die Staffelpreise veraltet. Zuschläge und Gewinn
    gehören nicht dazu: sie wirken sofort über die Preisschicht."""
    g = _hash(_gemeinsam(kopf, positionen, k, tabellen, einst))
    return _hash([g] + [lauf_kennung(g, st, mz) for st, mz in gruppieren(stufen, stufen_daten)])


def veraltet(sp, kopf, positionen, stufen, k, tabellen, einst, stufen_daten=None):
    """Anzahl der Stufen, deren Mengenlauf fehlt oder nicht mehr zu den Eingaben passt."""
    g = _hash(_gemeinsam(kopf, positionen, k, tabellen, einst))
    da = {(z.get("kennung_stufe"), txt(z.get("schluessel")), z.get("menge")) for z in (sp or {}).get("zeilen") or ()}
    return sum(1 for st, mz in gruppieren(stufen, stufen_daten)
               if any((lauf_kennung(g, st, mz), txt(z["schluessel"]), z["menge"]) not in da for z in mz))
