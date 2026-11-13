"""Angebot genauer (Roadmap Kalkulation Phase 2, Paket 2d; Freigabe Patrick 13.11.2026 „Ganze Phase 2 nach
Empfehlung“). Nur Hinweise und Vorschläge, nichts wird von selbst umgestellt; neue Einstellungen leer = aus. Ohne Qt.

OFFER-009 Preisband ähnlicher Teile: €/kg früher verschickter Teile mit gleicher Abmessung und ähnlicher Länge,
          getrennt nach beauftragt und abgelehnt; Hinweis, wenn der Preis über dem beauftragten Band liegt.
OFFER-011 Zielpreis rückwärts: Liste der Hebel (Gewinn, doppelte Menge, ohne Fremdleistungen, ohne Eilzuschlag) mit
          ihrer Wirkung auf den Angebotspreis.
OFFER-013 Rabattstaffel je Kunde nach Jahresumsatz (Kundenvorgabe „ab Umsatz = %“): Vorschlag im Angebots-Check.
OFFER-016 Drei Liefertermine mit Preis: Express (früher, mit Eilzuschlag Stufe 1), Standard, flexibel (später, mit
          Abschlag); Hinweis im Angebots-Check und Satz im Angebots-PDF.
PART-007  Lieferzeit der Zukaufteile gegen den zugesagten Termin.
CALC-009  Arbeitsplan je Position: feste Reihenfolge Laser → Nachbearbeitung → Montage → Oberfläche → Prüfung →
          Verpackung mit Liegezeit zwischen den Arbeitsgängen und der Lieferzeit der Fremdleistungen."""
import datetime
import statistics

EPS = 1e-9


def _n(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


def _z(w, stellen=2):
    from .stammdaten import zahl_als_text
    return zahl_als_text(w, stellen)


def _datum(text):
    try:
        return datetime.date.fromisoformat(str(text or "")[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------- OFFER-013 Rabattstaffel
def jahresumsatz(zeilen, kundennr, heute=None, tage=365):
    """Summe vk_netto der beauftragten eigenen Angebote des Kunden in den letzten tage Tagen."""
    from .cockpit import _vorgang
    heute = heute or datetime.date.today()
    summe = 0.0
    for z in zeilen or ():
        if z.get("fremd") or str(z.get("kundennr")) != str(kundennr) or _vorgang(z) != "Beauftragt":
            continue
        d = _datum(z.get("datum"))
        if d and 0 <= (heute - d).days <= tage:
            summe += _n(z.get("vk_netto"))
    return summe


def rabatt_vorschlag(staffel, umsatz):
    """Rabatt [%] der Staffel „ab Umsatz = %; …“ für den Umsatz oder None (unter der ersten Stufe, keine Staffel)."""
    from .zusatz_mehr import ab_wert
    return ab_wert(staffel, umsatz)


def rabatt_punkt(kopf, staffel, umsatz):
    """Hinweistext, wenn die Staffel einen anderen Rabatt vorschlägt als das Angebot hat, sonst None."""
    vor = rabatt_vorschlag(staffel, umsatz)
    if vor is None:
        return None
    jetzt = _n((kopf or {}).get("rabatt"))
    if abs(vor - jetzt) < 0.05:
        return None
    return (f"Rabattstaffel des Kunden: Umsatz der letzten 12 Monate {_z(umsatz, 0)} € → {_z(vor, 1)} % Rabatt "
            f"vorgeschlagen, im Angebot {_z(jetzt, 1)} % (Feld Rabatt im Angebotskopf).")


# ---------------------------------------------------------------- PART-007 Lieferzeit der Zukaufteile
def zukauf_lieferzeit(positionen, artikel_von):
    """Größte Lieferzeit [Tage] der Zukaufteile im Angebot und der Artikel: (Tage, Text). artikel_von(id) liefert den
    Zukaufartikel mit 'bezuege' (bevorzugter zuerst) oder None. Freie Einträge: Lieferzeit im Preisstand."""
    from . import zukauf
    beste = (0, "")
    for p in positionen or ():
        if _n(p.get("stueck")) <= 0:
            continue
        for e in zukauf.eintraege(p):
            st = e.get("stand") if isinstance(e.get("stand"), dict) else {}
            tage, name = _n(st.get("lieferzeit")), st.get("bezeichnung") or st.get("artikelnr") or ""
            if e.get("artikel_id") is not None:
                a = artikel_von(e["artikel_id"]) or {}
                name = a.get("bezeichnung") or a.get("artikelnr") or name
                for b in a.get("bezuege") or ():
                    if _n(b.get("lieferzeit")):
                        tage = max(tage, _n(b["lieferzeit"])) if not st.get("lieferzeit") else tage
                        break
            if tage > beste[0]:
                beste = (int(tage), str(name))
    return beste


def lieferzeit_punkt(tage, name, termin, heute=None):
    """Hinweis, wenn heute + Lieferzeit des Zukaufteils nach dem zugesagten Termin liegt, sonst None."""
    if not tage or termin is None:
        return None
    heute = heute or datetime.date.today()
    ankunft = heute + datetime.timedelta(days=int(tage))
    if ankunft <= termin:
        return None
    return (f"Zukaufteil „{name}“ hat {int(tage)} Tage Lieferzeit (da frühestens {ankunft.strftime('%d.%m.%Y')}), "
            f"zugesagt ist der {termin.strftime('%d.%m.%Y')} – Lieferzeit prüfen.")


# ---------------------------------------------------------------- OFFER-016 Drei Liefertermine
def termine(einst, standard_tage):
    """(Express-Arbeitstage, flexibel-Arbeitstage, Abschlag) aus den Einstellungen oder None, wenn beides aus ist.
    standard_tage = Arbeitstage der Lieferzeit des Angebots."""
    e = einst or {}
    weniger, mehr, ab = int(_n(e.get("express_tage"))), int(_n(e.get("flexibel_tage"))), _n(e.get("flexibel_abschlag"))
    if standard_tage is None or standard_tage <= 0 or (weniger <= 0 and (mehr <= 0 or ab <= 0)):
        return None
    express = max(1, standard_tage - weniger) if weniger > 0 and standard_tage - weniger >= 1 else None
    flex = standard_tage + mehr if mehr > 0 and ab > 0 else None
    return express, flex, ab


def standard_tage(kopf):
    """Arbeitstage der Lieferzeit des Angebots (nur Art Arbeitstage bzw. Wochen × 5), sonst None."""
    from .angebot import ARBEITSTAGE, WOCHEN
    k = kopf or {}
    try:
        w = int(str(k.get("lieferzeit_wert") or "").strip())
    except ValueError:
        return None
    if k.get("lieferzeit_art") == ARBEITSTAGE:
        return w
    if k.get("lieferzeit_art") == WOCHEN:
        return 5 * w
    return None


def termine_text(t, preise):
    """Satz für Check und PDF: t = termine(...), preise = dict(express, standard, flexibel) netto."""
    if not t:
        return ""
    express, flex, ab = t
    teile = []
    if express and preise.get("express"):
        teile.append(f"Express in ca. {express} Arbeitstagen {_z(preise['express'])} €")
    teile.append(f"Standard {_z(preise.get('standard') or 0)} €")
    if flex and preise.get("flexibel"):
        teile.append(f"flexibel in ca. {flex} Arbeitstagen {_z(preise['flexibel'])} € (−{_z(ab, 1)} %)")
    return "Liefertermine zur Wahl (netto): " + ", ".join(teile) + "."


# ---------------------------------------------------------------- OFFER-011 Hebel zum Zielpreis
def hebel(ziel, jetzt, varianten):
    """varianten = [(Text, Preis netto oder None)] -> [(Text, Preis, Ersparnis, reicht)] nach Ersparnis, nur echte
    Hebel (Preis kleiner als jetzt)."""
    out = []
    for text, preis in varianten:
        if preis is None or preis >= jetzt - 0.005:
            continue
        out.append((text, preis, jetzt - preis, preis <= ziel + 0.005))
    return sorted(out, key=lambda x: -x[2])


def hebel_text(ziel, jetzt, liste):
    if not liste or jetzt <= ziel + 0.005:
        return ""
    teile = [f"{t}: {_z(p)} € (−{_z(d)} €{', reicht' if r else ''})" for t, p, d, r in liste]
    return f"Hebel bis zum Zielpreis {_z(ziel)} € (jetzt {_z(jetzt)} €): " + "; ".join(teile) + "."


# ---------------------------------------------------------------- OFFER-009 Preisband ähnlicher Teile
BAND_MIN = 3


def band_daten(eintraege):
    """eintraege = [(Vorgang, Versandverlauf)] -> {(profil_id, werkstoff_id): [(Länge, €/kg, beauftragt)]}; je
    Angebot der letzte Versand mit Kennwerten; nur Beauftragt und Abgelehnt."""
    out = {}
    for vorgang, verlauf in eintraege or ():
        if vorgang not in ("Beauftragt", "Abgelehnt"):
            continue
        for e in reversed(verlauf or ()):
            kw = (e or {}).get("kennwerte") or ()
            for w in kw:
                if _n(w.get("eur_kg")) > 0 and _n(w.get("laenge")) > 0:
                    out.setdefault((w.get("profil_id"), w.get("werkstoff_id")), []).append(
                        (w["laenge"], w["eur_kg"], vorgang == "Beauftragt"))
            if kw:
                break
    return out


def band(daten, kennwert):
    """dict(ja=[€/kg], nein=[€/kg]) ähnlicher Teile (gleiche Abmessung, Länge höchstens 1,5-mal anders)."""
    from .plausibel import LAENGE_BAND
    la = _n(kennwert.get("laenge"))
    ja, nein = [], []
    for laenge, eur, auftrag in daten.get((kennwert.get("profil_id"), kennwert.get("werkstoff_id"))) or ():
        if la > 0 and 1 / LAENGE_BAND <= laenge / la <= LAENGE_BAND:
            (ja if auftrag else nein).append(eur)
    return dict(ja=ja, nein=nein)


def band_punkt(pos, kennwert, b):
    """Hinweis, wenn der Preis je kg über dem höchsten beauftragten ähnlicher Teile liegt (mindestens BAND_MIN
    Vergleichsteile), sonst None."""
    ja, nein = b["ja"], b["nein"]
    if len(ja) + len(nein) < BAND_MIN or not ja:
        return None
    eur = _n(kennwert.get("eur_kg"))
    if eur <= max(ja) + EPS:
        return None
    teil = f"beauftragt {_z(min(ja))}–{_z(max(ja))} €/kg (Median {_z(statistics.median(ja))}, {len(ja)} Teil{'e' if len(ja) != 1 else ''})"
    if nein:
        teil += f", abgelehnt Median {_z(statistics.median(nein))} €/kg ({len(nein)} Teil{'e' if len(nein) != 1 else ''})"
    return (f"Pos. {pos}: {_z(eur)} €/kg liegt über dem Preisband ähnlicher Teile: {teil}.")


# ---------------------------------------------------------------- CALC-009 Arbeitsplan
REIHENFOLGE = ("Laser", "Nachbearbeitung", "Montage", "Oberfläche", "Prüfung", "Verpackung")


def arbeitsplan(p, tabellen, liegezeit):
    """[(Arbeitsgang, Kategorie, Fremd-Tage)] in fester Reihenfolge und Durchlauf [Arbeitstage] = Liegezeit je
    Übergang + Lieferzeit der Fremdleistungen + 1 Tag Fertigung. Ergebnis: (Liste, Tage)."""
    from .rechnen import zusatz_liste
    katalog = {z.get("name"): z for z in (tabellen or {}).get("zusatzarbeiten") or ()}
    schritte = [("Laser schneiden", "Laser", 0)]
    for e in zusatz_liste(p):
        kz = katalog.get(e["name"]) or {}
        st = e.get("stand") if isinstance(e.get("stand"), dict) else {}
        kat = kz.get("kategorie") or "Nachbearbeitung"
        schritte.append((e["name"], kat if kat in REIHENFOLGE else "Nachbearbeitung",
                         int(_n(st.get("tage_fremd", kz.get("tage_fremd"))))))
    schritte.sort(key=lambda s: REIHENFOLGE.index(s[1]))
    tage = 1 + max(0, len(schritte) - 1) * max(0.0, _n(liegezeit)) + sum(s[2] for s in schritte)
    return schritte, tage


def arbeitsplan_text(schritte, tage):
    return " → ".join(n + (f" (Fremd, {f} AT)" if f else "") for n, _, f in schritte) + \
        f"; Durchlauf ca. {_z(tage, 0)} Arbeitstage"
