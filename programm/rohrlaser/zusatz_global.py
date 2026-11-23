"""Allgemeine Zusatzarbeiten eines Angebots (Master-Auftrag „Flexible Zusatzarbeiten-Kalkulation“, Patrick 23.11.2026).

Neben den Zusatzarbeiten je Position (rechnen.zusatz_werte, Dialog zusatz_dialog.py) kann ein Angebot Leistungen für
das ganze Angebot tragen: Verpackung 45 € pauschal, Sonderbearbeitung 3 h × 65 €/h, Qualitätskontrolle, ein
prozentualer Zuschlag usw. Sie stehen im Angebot als eigene Zeilen unter den Positionen.

Gespeichert im Angebot (angebote.zusatz, JSON, Schlüssel ``zusatzarbeiten``; kein neues Datenbankfeld) als Liste von
Einträgen::

    {id, name, katalog, menge, einheit, preis, beschreibung, kosten, zeit_min, basis, stand}

- ``preis`` ist der **Verkaufspreis je Einheit** (netto), Gesamt = Menge × Preis (kaufmännisch auf den Cent).
- ``einheit`` = Stück, m, m², h, min, kg, pauschal oder % (bei % ist ``menge`` der Prozentsatz und ``basis`` die
  Grundlage: „Positionen“ = Summe der Positionen, „Positionen und Zusatzarbeiten“ = dazu die übrigen allgemeinen
  Zusatzarbeiten ohne %).
- ``kosten`` [€ je Einheit] und ``zeit_min`` [min je Einheit] sind intern (Marge, Akte), nie im Kundenangebot.
- ``katalog`` = Name der Zusatzarbeit aus Einstellungen → Zusatzarbeiten, aus der der Vorschlag stammt (oder leer);
  ``stand`` = Standardpreis und Datum beim Übernehmen. Spätere Änderungen der Stammdaten ändern den Eintrag nicht
  (Snapshot); „Standardpreis übernehmen“ holt den aktuellen Preis bewusst neu.

Rechnung: rechnen._kalkulation_gestaffelt ruft anwenden() nach der Preisschicht auf. Die Summe kommt als Kostenart
``zusatz_global`` in den Verkaufspreis (Netto, MwSt, Brutto, Angebotsliste), die internen Kosten als
``zusatz_global_kosten`` in die Kosten der Marge (marge.kosten). Rabatt, Skonto, Mindestauftragswert und Staffelpreise
gelten nur für die Positionen. Ohne Einträge bleibt jede Zahl bitgleich.

Darstellung im Kundenangebot (Schlüssel ``zusatz_darstellung`` im Angebot): „zusammengefasst“ (Vorgabe, wie bisher:
Zusatzarbeiten der Position als „inkl. …“ im Text, allgemeine je Zeile), „detailliert“ (je Position eine Aufstellung
Leistung, Menge, Einheitspreis, Gesamt und der Positionspreis einschließlich Zusatzarbeiten; allgemeine mit
Beschreibung) oder „nur Gesamtpreis“ (keine Zusatzarbeiten im Positionstext, allgemeine als eine Summenzeile).
Ohne Qt."""
import json
import uuid

EINHEITEN = ("Stück", "m", "m²", "h", "min", "kg", "pauschal", "%")
PROZENT, PAUSCHAL = "%", "pauschal"
BASIS = ("Positionen", "Positionen und Zusatzarbeiten")
DARSTELLUNGEN = ("zusammengefasst", "detailliert", "nur Gesamtpreis")
ZUSAMMEN, DETAIL, NUR_GESAMT = DARSTELLUNGEN
SCHLUESSEL, SCHLUESSEL_DARSTELLUNG = "zusatzarbeiten", "zusatz_darstellung"
# Einheit im Angebot zur Abrechnung der Stammdaten (Vorschlag aus der zentralen Verwaltung)
EINHEIT_AUS_ART = {"€/Stück": "Stück", "€/m": "m", "€/m²": "m²", "€/h": "h", "€/kg": "kg", "€/Angebot": PAUSCHAL}
# Einheit im Angebotstext (PDF)
EINHEIT_TEXT = {"Stück": "Stk.", "pauschal": "pausch.", "%": "pausch."}
# Übertragen auf Positionen: Abrechnung der Position je Einheit und Faktor der Menge je Teil
ART_AUS_EINHEIT = {"Stück": ("€/Stück", 1.0), "m": ("€/m", 1.0), "m²": ("€/m²", 1.0), "kg": ("€/kg", 1.0),
                   "h": ("€/h", 3600.0), "min": ("€/h", 60.0), PAUSCHAL: ("€/Angebot", 1.0)}


def _n(w):
    try:
        return float(w) if w not in (None, "") and not isinstance(w, bool) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _runden(x):
    from .ausgabe import kaufm_runden
    return kaufm_runden(x, 2)


def _zusatz(kopf):
    z = (kopf or {}).get("zusatz")
    if isinstance(z, str):
        try:
            z = json.loads(z) if z else {}
        except ValueError:
            z = {}
    return z if isinstance(z, dict) else {}


def liste(kopf):
    """Allgemeine Zusatzarbeiten des Angebots (Kopie der gespeicherten Einträge, ungültige ausgelassen)."""
    roh = _zusatz(kopf).get(SCHLUESSEL) or []
    return [dict(e) for e in roh if isinstance(e, dict) and str(e.get("name") or "").strip()] \
        if isinstance(roh, list) else []


def darstellung(kopf, einst=None):
    """Darstellung der Zusatzarbeiten im Kundenangebot: Wert des Angebots, sonst Einstellung, sonst zusammengefasst."""
    w = _zusatz(kopf).get(SCHLUESSEL_DARSTELLUNG) or (einst or {}).get("zusatz_darstellung")
    return w if w in DARSTELLUNGEN else ZUSAMMEN


def ohne(kopf):
    """Kopf ohne allgemeine Zusatzarbeiten (Staffeln: Stückpreise der Stufen nur aus den Positionen)."""
    z = _zusatz(kopf)
    if not z.get(SCHLUESSEL):
        return kopf
    return dict(kopf, zusatz={n: w for n, w in z.items() if n != SCHLUESSEL})


def neu(name, menge=1.0, einheit="Stück", preis=0.0, beschreibung="", kosten=None, zeit_min=None, katalog=None,
        basis=None, stand=None):
    """Neuer Eintrag (eigene id für die Oberfläche)."""
    if einheit not in EINHEITEN:
        raise ValueError(f"Einheit '{einheit}' unbekannt (erlaubt: {', '.join(EINHEITEN)}).")
    e = dict(id=uuid.uuid4().hex[:12], name=str(name).strip(), katalog=katalog or None, menge=float(menge),
             einheit=einheit, preis=float(preis or 0), beschreibung=beschreibung or "",
             kosten=None if kosten is None else float(kosten), zeit_min=None if zeit_min is None else float(zeit_min))
    if einheit == PROZENT:
        e["basis"] = basis if basis in BASIS else BASIS[0]
        e["preis"] = 0.0
    if stand:
        e["stand"] = stand
    return e


def vorschlag(z, einst=None, saetze=None, datum=None):
    """Eintrag aus einer Zusatzarbeit der zentralen Verwaltung (Stammdatenzeile): Einheit aus der Abrechnung,
    interne Kosten je Einheit = Preis je Einheit der Stammdaten (rechnen.zusatz_preis), Verkaufspreis je Einheit =
    Kosten × (1 + Zuschlag Fertigung bzw. Fremdleistung) × (1 + Gewinn) aus den Kalkulationswerten (wie im Angebot),
    gerundet auf den Cent. Zeit je Einheit aus dem Zeitaufwand der Stammdaten. Der Preis bleibt änderbar."""
    import datetime
    from . import rechnen
    art = z.get("art")
    einheit = EINHEIT_AUS_ART.get(art, "Stück")
    pr = rechnen.zusatz_preis(z, saetze)
    kosten = _n(pr["preis"])
    fremd = z.get("fremd") == "ja"
    e = einst or {}
    zuschlag = _n(e.get("zuschlag_fremdleistung") if fremd else e.get("zuschlag_fertigung"))
    vk = _runden(kosten * (1 + zuschlag) * (1 + _n(e.get("gewinn"))))
    zeit_min = (60.0 if art == "€/h" else _n(pr.get("zeit_s")) / 60) or None
    tag = datum or datetime.date.today().isoformat()
    return neu(z.get("name"), 1.0, einheit, vk, "", kosten=kosten, zeit_min=zeit_min,
               katalog=z.get("name"), stand=dict(preis=vk, kosten=kosten, art=art, datum=tag))


def zeit_je_einheit(e):
    """Interne Zeit je Einheit [min]: Feld zeit_min, sonst 60 bei h und 1 bei min, sonst 0."""
    if e.get("zeit_min") not in (None, ""):
        return _n(e.get("zeit_min"))
    return {"h": 60.0, "min": 1.0}.get(e.get("einheit"), 0.0)


def zeilen(eintraege, basis_positionen):
    """Gerechnete Zeilen: [dict(eintrag, gesamt, kosten_gesamt, zeit_min_gesamt, preis_einheit)]. % zuletzt auf die
    gewählte Grundlage; jeder Betrag auf den Cent gerundet."""
    out, fest = [], 0.0
    for e in eintraege:
        if e.get("einheit") == PROZENT:
            continue
        gesamt = _runden(_n(e.get("menge")) * _n(e.get("preis")))
        fest += gesamt
        out.append(dict(e, gesamt=gesamt, preis_einheit=_n(e.get("preis")),
                        kosten_gesamt=_n(e.get("menge")) * _n(e.get("kosten")),
                        zeit_min_gesamt=_n(e.get("menge")) * zeit_je_einheit(e)))
    for e in eintraege:
        if e.get("einheit") != PROZENT:
            continue
        basis = _n(basis_positionen) + (fest if e.get("basis") == BASIS[1] else 0.0)
        gesamt = _runden(basis * _n(e.get("menge")) / 100)
        out.append(dict(e, gesamt=gesamt, preis_einheit=basis / 100, basis_betrag=basis,
                        kosten_gesamt=_n(e.get("kosten")), zeit_min_gesamt=_n(e.get("zeit_min"))))
    reihenfolge = {id_: i for i, id_ in enumerate(e.get("id") for e in eintraege)}
    out.sort(key=lambda r: reihenfolge.get(r.get("id"), 0))
    return out


def anwenden(kopf, summen):
    """Allgemeine Zusatzarbeiten in die Summen (nach der Preisschicht): zusatz_global (Verkaufspreis), _kosten, _zeit_min,
    _n, _zeilen; Verkaufspreis um die Summe erhöht. Ohne Einträge unverändert."""
    eintraege = liste(kopf)
    if not eintraege:
        return summen
    basis = _n(summen.get("verkauf"))
    z = zeilen(eintraege, basis)
    summe = sum(r["gesamt"] for r in z)
    summen.update(zusatz_global=summe, zusatz_global_kosten=sum(r["kosten_gesamt"] for r in z),
                  zusatz_global_zeit_min=sum(r["zeit_min_gesamt"] for r in z), zusatz_global_n=len(z),
                  zusatz_global_zeilen=z, verkauf_positionen=basis, verkauf=basis + summe)
    return summen


def _schluessel(name):
    return " ".join(str(name or "").casefold().split())


def ueberschneidungen(kopf, positionen):
    """Leistungen, die allgemein und an Positionen stehen (doppelte Berechnung möglich): [(Name, [Pos.-Nr.])]. Gleich
    heißt: gleicher Name bzw. gleiche Zusatzarbeit der Verwaltung, ohne Groß-/Kleinschreibung."""
    from . import rechnen
    out = []
    for e in liste(kopf):
        namen = {_schluessel(e.get("name")), _schluessel(e.get("katalog"))} - {""}
        pos = [p.get("pos") for p in positionen or () if p and any(
            _schluessel(z.get("name")) in namen for z in rechnen.zusatz_liste(p))]
        if pos:
            out.append((e["name"], pos))
    return out


def ueberschneidung_text(treffer):
    if not treffer:
        return ""
    teile = [f"„{n}“ (Pos. {', '.join(str(p) for p in pos if p is not None) or '?'})" for n, pos in treffer]
    return ("Möglicherweise doppelt berechnet: " + "; ".join(teile)
            + " stehen allgemein und an der Position. Bitte nur an einer Stelle führen.")


def an_position(e, katalog=None, menge_je_teil=None):
    """Eintrag für positionen.zusatz aus einer allgemeinen Zusatzarbeit (Zuordnen bzw. auf mehrere Positionen
    übertragen): Preis = Verkaufspreis je Einheit (Haken „Preis = Verkaufspreis“), interne Kosten mit, Preisstand
    aus der Verwaltung bzw. aus dem Eintrag selbst. menge_je_teil: Menge je Teil (leer = Menge des Eintrags; bei h/min
    in Stunden bzw. Minuten). % lässt sich nicht übertragen (ValueError)."""
    if e.get("einheit") not in ART_AUS_EINHEIT:
        raise ValueError("Ein prozentualer Zuschlag gilt für das ganze Angebot und lässt sich keiner Position zuordnen.")
    art, faktor = ART_AUS_EINHEIT[e["einheit"]]
    menge = _n(e.get("menge") if menge_je_teil is None else menge_je_teil) * faktor
    preis = _n(e.get("preis")) * (3600.0 / faktor if art == "€/h" else 1.0)    # €/h: Stundensatz
    kosten = e.get("kosten")
    if kosten is not None and art == "€/h":
        kosten = _n(kosten) * 3600.0 / faktor
    name = (katalog or {}).get("name") or e.get("katalog") or e["name"]
    from . import rechnen
    if katalog:
        stand = rechnen.zusatz_stand(katalog)
    else:
        import datetime
        stand = dict(art=art, preis=_n(kosten) if kosten is not None else preis, mindest=None, fremd=None,
                     angebotstext=e["name"], datum=datetime.date.today().isoformat(), regeln="ja")
    out = dict(name=name, menge=menge, preis=preis, vk="ja", stand=stand)
    if kosten is not None:
        out["kosten"] = float(kosten)
    if e.get("beschreibung"):
        out["text"] = e["beschreibung"]
    return out


def ausgabe_zeilen(kopf, basis_netto, einst=None):
    """Zeilen für das Kundenangebot (ausgabe.angebot): art 'einmal' mit zusatz_global=True; bei „nur Gesamtpreis“ eine
    Summenzeile. basis_netto = Summe der übrigen Angebotszeilen (für %)."""
    z = zeilen(liste(kopf), basis_netto)
    if not z:
        return []
    art = darstellung(kopf, einst)
    if art == NUR_GESAMT:
        summe = _runden(sum(r["gesamt"] for r in z))
        return [dict(art="einmal", pos=None, artikel=None, einheit="pausch.", menge=1, preis=summe, gesamt=summe,
                     zusatz_global=True, text="Allgemeine Zusatzleistungen zum Angebot")]
    from .ausgabe import euro_text
    from .stammdaten import zahl_als_text
    out = []
    for r in z:
        text = r["name"]
        if r.get("einheit") == PROZENT:
            text += (f" ({zahl_als_text(_n(r.get('menge')))} % auf {euro_text(r.get('basis_betrag'))} € "
                     + ("Positionen" if r.get("basis") != BASIS[1] else "Positionen und Zusatzleistungen") + ")")
            menge, preis = 1, r["gesamt"]
        else:
            menge, preis = _n(r.get("menge")), _n(r.get("preis"))
        if art == DETAIL and r.get("beschreibung"):
            text += "\n" + str(r["beschreibung"])
        out.append(dict(art="einmal", pos=None, artikel=None, menge=menge, preis=preis, gesamt=r["gesamt"],
                        einheit=EINHEIT_TEXT.get(r.get("einheit"), r.get("einheit")), zusatz_global=True,
                        text=text))
    return out


def position_aufstellung(z, menge, dezimal=","):
    """Detaillierte Aufstellung der Zusatzarbeiten einer Position fürs Kundenangebot: [(Leistung, Menge, Einheit,
    Einheitspreis, Gesamt)] mit Verkaufspreisen. Feste Verkaufspreise (Haken) exakt, die übrigen mit dem Zuschlag
    und Gewinn der Position (Anteil am Stückpreis: Kostenbetrag × Stückpreis ÷ Selbstkosten), Mengen für die ganze
    Position. z = Kalkulationszeile."""
    if not z:
        return []
    from .ausgabe import kaufm_runden
    zus = [e for e in z.get("zusatzarbeiten") or () if e.get("art") != "s/Stück"]
    if not zus:
        return []
    vk_fest = _n(z.get("zusatz_vk_teil"))
    basis = _n(z.get("selbst_teil")) - _n(z.get("zusatz_vk_kosten_teil"))
    rest = _n(z.get("preis_teil")) - vk_fest
    faktor = rest / basis if basis > 0 else 1.0
    out = []
    c = _n(menge)
    for e in zus:
        teil = _n(e.get("teil")) * (1.0 if e.get("vk") else faktor)
        art = e.get("art")
        if art == "€/Angebot":
            m, einheit, ep = 1.0, "pausch.", kaufm_runden(teil * c, 2)
        elif art == "€/h":
            m, einheit = _n(e.get("menge")) * c / 3600, "h"
            ep = kaufm_runden(teil * c / m, 2) if m else 0.0
        else:
            m = _n(e.get("menge")) * c
            einheit = {"€/Stück": "Stk.", "€/m": "m", "€/m²": "m²", "€/kg": "kg"}.get(art, "Stk.")
            ep = kaufm_runden(teil * c / m, 2) if m else 0.0
        name = (e.get("angebotstext") or e.get("name")) + (f" {e['text']}" if e.get("text") else "")
        name = name[:1].upper() + name[1:]
        out.append((name, m, einheit, ep, kaufm_runden(teil * c, 2)))
    return out
