"""Staffelpreise: jede Mengenstufe als eigenes Angebot neu rechnen, mit eigenen Zuschlägen je Stufe.

Eine Stufe hat einen Schlüssel (Satzbezeichnung aus der Spalte 'Satz' oder eine Positionsnummer) und
eine Menge (Anzahl Sätze bzw. Stück, „Menge ab“). Im Rechenlauf sind nur die Positionen dieser Stufe besetzt:
bei einem Satz Menge × 'Stück je Satz', bei einer Position die Menge selbst. Alle anderen Stückzahlen
sind leer. So fallen Rüsten, Stangenwechsel und Verschnitt je Stufe neu an, ebenso Programmierkosten, Rüstzeit und Pauschale
je Abmessung, Angebotsaufschlag und Fracht (jede Stufe ist ein eigenes Angebot).

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
      Skonto eingerechnet; MwSt = Netto gesamt × MwSt-Satz
  Ohne Werte in der Stufe ergibt das genau den Verkaufspreis der Kalkulation (rechnen.kalkulation).
"""
import hashlib
import json

from . import fracht_angebot, rechnen
from .angebot import aktiv as position_aktiv
from .ausgabe import kaufm_runden
from .stammdaten import Feld, kontext_aus

SPALTEN = ("schluessel", "bezeichnung", "einheit", "menge", "teile", "stangen", "material", "laser", "ruesten",
           "herstell", "herstell_einheit", "preis_einheit", "preis_gesamt", "hinweis")
MAX_STUFEN = 200
VERSION = 2          # 2: Bausteine je Stufe und Preisschicht; ältere gespeicherte Staffelpreise gelten als veraltet

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
# unter 'Erweiterte Einstellungen' (ausgeblendet, solange keine Stufe einen Wert hat)
ERWEITERT = ("bis", "verlust", "mat_grundpreis", "zuschlag_fertigung", "ruesten", "arbeitsgang", "arbeitsgang_min",
             "arbeitsgang_satz", "arbeitsgang_eur", "neben_einheit", "neben_pauschal", "rabatt")
AUSWAHL = {"zuschlag_art": [PROZENT, EURO], "ruesten": [UMLEGEN, SEPARAT], "janein": ["ja", "nein"]}
# Einstellungen, die in den Mengenlauf eingehen (Zuschläge und Gewinn wirken erst in der Preisschicht)
EINST_LAUF = ("ruesten_abmessung", "pauschale_abmessung", "programmierung_teil", "angebotsaufschlag")


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
    fracht_felder = ("fracht_modus", "fracht_umlage", "fracht_sendung")
    return [{f: kopf.get(f) for f in felder + tuple(n for n in fracht_felder if kopf.get(n) is not None)},
            [{a: b for a, b in p.items() if a not in ("id", "angebot_id", "nr", "zeile")} for p in positionen],
            [k.profile, k.werkstoffe, k.maschinen, k.oberflaechen], tabellen, {n: einst.get(n) for n in EINST_LAUF},
            VERSION]


def _hash(daten):
    return hashlib.sha1(json.dumps(daten, default=str, sort_keys=True).encode()).hexdigest()


def stufe_kennung(gemeinsam, schl, menge):
    """Prüfsumme eines Mengenlaufs: gemeinsame Eingaben (_gemeinsam bzw. deren Hash), Schlüssel und Menge."""
    g = gemeinsam if isinstance(gemeinsam, str) else _hash(gemeinsam)
    return _hash([g, txt(schl), menge])


def rechnen_alle(kopf, positionen, stufen, k, tabellen, einst, fortschritt=None, alt=None, ohne_lauf=False):
    """Alle gültigen Stufen rechnen. Ergebnis: Liste von dicts (Spalten aus SPALTEN, bausteine, Preise).
    alt: bisherige Zeilen; Stufen mit unveränderter Prüfsumme werden übernommen statt neu optimiert.
    ohne_lauf: nur die Preisschicht; Stufen ohne passenden Mengenlauf bekommen eine Zeile 'VERALTET'.
    fortschritt(i, n) wird vor jedem Mengenlauf aufgerufen und kann mit False abbrechen (Ergebnis dann None)."""
    stufen = gueltige(stufen)
    g = _hash(_gemeinsam(kopf, positionen, k, tabellen, einst))
    vorher = {z.get("kennung_stufe"): z for z in alt or () if z.get("bausteine") or z.get("hinweis")}
    neu = [st for st in stufen if stufe_kennung(g, st["schluessel"], st["menge"]) not in vorher]
    zeilen, n = [], 0
    for st in stufen:
        kenn = stufe_kennung(g, st["schluessel"], st["menge"])
        if kenn in vorher:
            z = dict(vorher[kenn])
        elif ohne_lauf:
            ist_satz = any(txt(p.get("satz")) == txt(st["schluessel"]) for p in positionen)
            z = dict.fromkeys(SPALTEN)
            z.update(schluessel=txt(st["schluessel"]), menge=st["menge"], einheit="Satz" if ist_satz else "Stück",
                     bausteine=None, hinweis="VERALTET – wird neu gerechnet")
        else:
            if fortschritt and fortschritt(n, len(neu)) is False:
                return None
            n += 1
            z = stufe_rechnen(kopf, positionen, txt(st["schluessel"]), st["menge"], k, tabellen, einst, mit_preis=False)
            z["kennung_stufe"] = kenn
        z["stufe_id"] = st.get("id")
        zeilen.append(preise_anwenden(z, st, einst, stufen, positionen))
    return zeilen


def stufe_rechnen(kopf, positionen, schl, menge, k, tabellen, einst, mit_preis=True, stufe=None):
    """Mengenlauf einer Stufe; mit_preis: gleich mit den Werten der Stufe (stufe, leer = Angebot) bepreisen."""
    ist_satz, mengen, bez = szenario(schl, menge, positionen)
    z = dict.fromkeys(SPALTEN)
    z.update(schluessel=schl, einheit="Satz" if ist_satz else "Stück", menge=menge, bausteine=None)
    if not mengen:
        z.update(bezeichnung="", hinweis="FEHLER: Satz/Pos. nicht im Angebot")
        return z
    z["bezeichnung"] = bez
    lauf = [dict(p, stueck=mengen.get(i)) for i, p in enumerate(positionen)]
    werte = [rechnen.position_werte(p, kopf, k, tabellen) if position_aktiv(p) else None for p in lauf]
    betrag, fracht_text, fracht_fehler = fracht_angebot.stufe(kopf, lauf, werte)
    if fracht_fehler:           # nie still mit 0 € Fracht rechnen
        z.update(hinweis=fracht_fehler)
        return z
    kopf = dict(kopf, fracht=betrag)
    erg = rechnen.optimieren(kopf, lauf, k)
    if erg["neue_profile"]:      # Profil aus dem Namen gilt für diesen Lauf als angelegt
        k = kontext_aus({"profile": list(k.profile.values()) + erg["neue_profile"],
                         "werkstoffe": list(k.werkstoffe.values()), "maschinen": list(k.maschinen.values()),
                         "oberflaechen": list(k.oberflaechen.values())}, k.profilformen, k.kategorien)
    kz, summen = rechnen.kalkulation(kopf, lauf, erg, k, tabellen, einst)
    z.update(teile=summen["teile"], stangen=summen["stangen"], material=summen["material"], laser=summen["laser"],
             ruesten=summen["ruesten"])
    hinweise = offen = ohne_preis = 0
    for i in mengen:
        if kz[i] is None:
            continue
        if kz[i]["hinweis"]:
            hinweise += 1
        offen += _zahl(kz[i]["nicht_eingeplant"])
        if not kz[i]["material_gruppe"] and not kz[i].get("zukaufteil"):
            ohne_preis += 1
    z["bausteine"] = bausteine(summen, ohne_preis)
    text = f"WARNUNG: {offen:.0f} Teile nicht eingeplant" if offen > 0 else ""
    if hinweise:
        text += ("; " if text else "") + f"{hinweise} Hinweis(e) in der Kalkulation"
    if summen.get("fracht_hinweis"):
        text += ("; " if text else "") + summen["fracht_hinweis"]
    if fracht_text:
        text += ("; " if text else "") + fracht_text
    z["hinweis"] = text or None
    return preise_anwenden(z, stufe or {}, einst) if mit_preis else z


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
    return dict(material=summen["material"], material_fehlt=ohne_materialpreis, fertigung=fert, ruesten=ruest,
                fremd=summen["zusatz_fremd"], pauschalen=summen["pauschalen"],
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
                neben_pauschal=_zahl(w("neben_pauschal")), mwst=_zahl(einst.get("mwst")))


def preise(b, menge, w):
    """Preisschicht: Bausteine b eines Mengenlaufs, Menge der Stufe, Werte w (wirksam). Beträge für die ganze
    Stufe, ungerundet; gerundet sind nur preis_einheit, einmalig, preis_gesamt, mwst und brutto.
    Fehler (Materialpreis fehlt, Rabatt zu groß): dict mit 'fehler' und ohne Preise."""
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
    selbst = m0 + verlust + mz + f_sum + r_sum + gk_f + b["fremd"] + gk_fl + neben
    gewinn = selbst * w["gewinn"]
    weitere = b["pauschalen"] + b["programmierung"] + b["angebotsaufschlag"] + b["fracht"]
    zk_e, zk_a = b.get("zukauf_einstand", 0), b.get("zukauf_aufschlag", 0)     # fehlt in älteren Mengenläufen
    sk = min(max(b["skonto_satz"], 0), 50) / 100
    ohne = selbst + gewinn + weitere + zk_e + zk_a
    netto = ohne / (1 - sk)
    einmalig = 0.0
    if w["ruesten"] == SEPARAT:     # Rüsten mit Gemeinkosten, Gewinn und Skonto als einmalige Position
        einmalig = kaufm_runden(r_sum * (1 + w["zuschlag_fertigung"]) * (1 + w["gewinn"]) / (1 - sk), 2)
    preis_einheit = kaufm_runden((netto - einmalig) / menge, 2)
    gesamt = kaufm_runden(preis_einheit * menge + einmalig, 2)
    mwst = kaufm_runden(gesamt * w["mwst"], 2)
    return dict(fehler=None, m_grund=m0, m_verlust=verlust, m_zuschlag=mz, m_gesamt=m1 + mz, fertigung=fert,
                fert_gesamt=f_sum, ruesten=b["ruesten"], ruest_gesamt=r_sum, gk_fertigung=gk_f, fremd=b["fremd"],
                gk_fremd=gk_fl, neben=neben, selbst=selbst, gewinn=gewinn,
                marge=gewinn / netto if netto else None, pauschalen=b["pauschalen"],
                programmierung=b["programmierung"], angebotsaufschlag=b["angebotsaufschlag"], fracht=b["fracht"],
                zukauf_einstand=zk_e, zukauf_aufschlag=zk_a,
                skonto=netto - ohne, netto=netto, einmalig=einmalig, preis_einheit=preis_einheit,
                preis_gesamt=gesamt, mwst=mwst, brutto=kaufm_runden(gesamt + mwst, 2))


def preise_anwenden(z, stufe, einst, alle=None, positionen=None):
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
        p = preise(z["bausteine"], z["menge"], w)
        if p["fehler"]:
            hinweis.insert(0, "FEHLER: " + p["fehler"])
        else:
            z.update(preis=p, herstell=p["selbst"], herstell_einheit=p["selbst"] / z["menge"],
                     preis_einheit=p["preis_einheit"], preis_gesamt=p["preis_gesamt"])
    z["hinweis"] = "; ".join(hinweis) or None
    return z


def kennung(kopf, positionen, stufen, k, tabellen, einst):
    """Prüfsumme über alle Mengenläufe; weicht sie ab, sind die Staffelpreise veraltet. Zuschläge und Gewinn
    gehören nicht dazu: sie wirken sofort über die Preisschicht."""
    g = _hash(_gemeinsam(kopf, positionen, k, tabellen, einst))
    return _hash([g] + [stufe_kennung(g, s["schluessel"], s["menge"]) for s in gueltige(stufen)])


def veraltet(sp, kopf, positionen, stufen, k, tabellen, einst):
    """Anzahl der Stufen, deren Mengenlauf fehlt oder nicht mehr zu den Eingaben passt."""
    g = _hash(_gemeinsam(kopf, positionen, k, tabellen, einst))
    da = {z.get("kennung_stufe") for z in (sp or {}).get("zeilen") or ()}
    return sum(1 for s in gueltige(stufen) if stufe_kennung(g, s["schluessel"], s["menge"]) not in da)
