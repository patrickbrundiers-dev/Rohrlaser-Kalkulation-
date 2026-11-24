"""Rückfragen nur mit Preiswirkung (OFFER-021, Patrick 12.11.2026 „Alle Empfehlungen“ zum Bericht
Entwicklungspotenziale).

Eine offene Frage an einer Position steht im Feld „Offene Frage (Antworten)“, z. B.
    Werkstoff: 1.4301 oder 1.4404
    Oberfläche: ohne oder pulverbeschichtet
    Stückzahl: 50 oder 100
mehrere Fragen mit „;“ getrennt. Feld = Titel oder Name eines Positionsfelds (Werkstoff, Werkstoff-ID, Oberfläche,
Stückzahl, Profil-ID, Teilelänge, Qualitätsstufe, Material), Antworten mit „oder“ bzw. „|“; „ohne“ = leer.
Für jede Antwort rechnet das Programm das ganze Angebot neu (optimiert und kalkuliert) und vergleicht die Netto-
Summe. Gefragt wird nur, wenn sich die Antworten um mindestens die Schwelle unterscheiden (Einstellung, Vorgabe
3 %), sortiert nach € Unterschied. Fragen, die sich nicht rechnen lassen (unbekanntes Feld, Wert ohne Stammdaten),
und die übrigen offenen Punkte (Angebots-Check) bleiben ungefiltert in der Liste. Ohne Qt."""
import re

from . import rechnen

SCHWELLE = 0.03
FELD = "offene_frage"
NAMEN = {"werkstoff": "werkstoff_id", "werkstoff-id": "werkstoff_id", "material": "werkstoff_id",
         "oberfläche": "oberflaeche", "oberflaeche": "oberflaeche", "stückzahl": "stueck", "stueck": "stueck",
         "stück": "stueck", "menge": "stueck", "profil": "profil_id", "profil-id": "profil_id",
         "länge": "laenge", "teilelänge": "laenge", "teilelänge [mm]": "laenge", "qualität": "qualitaet",
         "qualitätsstufe": "qualitaet"}
ZAHL = {"stueck": int, "laenge": float}
OHNE = ("ohne", "keine", "kein", "-", "")


def fragen(text):
    """[(Feld, Titel, [Antworten])] aus dem Feldtext; Feld None = unbekannt (bleibt ungefiltert)."""
    out = []
    for teil in re.split(r"[;\n]", text or ""):
        if ":" not in teil:
            if teil.strip():
                out.append((None, teil.strip(), []))
            continue
        name, rest = teil.split(":", 1)
        antworten = [a.strip() for a in re.split(r"\s+oder\s+|\|", rest.strip()) if a is not None]
        feld = NAMEN.get(name.strip().lower())
        out.append((feld, name.strip(), antworten))
    return out


def _wert(feld, a):
    if a.strip().lower() in OHNE:
        return None
    if feld in ZAHL:
        try:
            return ZAHL[feld](float(a.replace(".", "").replace(",", ".")) if feld == "stueck" else
                              float(a.replace(",", ".")))
        except ValueError:
            return a
    return a


def _bekannt(feld, wert, k):
    if wert is None or feld in ZAHL:
        return not isinstance(wert, str)
    menge = {"werkstoff_id": k.werkstoffe, "oberflaeche": getattr(k, "oberflaechen", {}),
             "profil_id": k.profile}.get(feld)
    return menge is None or wert in menge


def wirkung(kopf, positionen, k, tabellen, einst_db, schwelle=SCHWELLE):
    """dict(fragen=[dict(pos, titel, antworten=[(Antwort, Netto €)], unterschied €, anteil, fragen bool)],
    offen=[Texte, die sich nicht rechnen lassen]). Sortiert: größter Unterschied zuerst."""
    einst = rechnen.einstellungen_angebot(kopf, einst_db)

    def netto(pos):
        erg = rechnen.optimieren(kopf, pos, k, tabellen, einst_db)
        return rechnen.kalkulation(kopf, pos, erg, k, tabellen, einst)[1]["verkauf"]

    out, offen = [], []
    for i, p in enumerate(positionen):
        for feld, titel, antworten in fragen(p.get(FELD)):
            name = f"Pos. {p.get('pos')}: {titel}" + (f" ({' oder '.join(antworten)})" if antworten else "")
            werte = [_wert(feld, a) for a in antworten] if feld else []
            if not feld or len(werte) < 2 or not all(_bekannt(feld, w, k) for w in werte):
                offen.append(name + "?")
                continue
            preise = []
            for a, w in zip(antworten, werte):
                pos = [dict(x) for x in positionen]
                pos[i][feld] = w
                try:
                    preise.append((a, float(netto(pos) or 0)))
                except Exception:           # nicht rechenbar: ungefiltert fragen
                    preise = None
                    break
            if not preise:
                offen.append(name + "?")
                continue
            lo, hi = min(x[1] for x in preise), max(x[1] for x in preise)
            anteil = (hi - lo) / lo if lo > 0 else (1.0 if hi > 0 else 0.0)
            out.append(dict(pos=p.get("pos"), titel=titel, text=name, antworten=preise, unterschied=hi - lo,
                            anteil=anteil, fragen=anteil >= schwelle))
    out.sort(key=lambda f: -f["unterschied"])
    return dict(fragen=out, offen=offen)


def texte(w):
    """Texte für die Mail an den Kunden (ohne Preise): gefragte Fragen nach € Unterschied, dann die nicht
    rechenbaren."""
    return [f["text"] + "?" for f in w["fragen"] if f["fragen"]] + list(w["offen"])


def bericht(w, schwelle=SCHWELLE):
    """Interne Zeilen mit Preiswirkung (Meldung, nicht für den Kunden)."""
    z = rechnen.zahl
    out = []
    for f in w["fragen"]:
        preise = ", ".join(f"{a}: {z(e)} €" for a, e in f["antworten"])
        out.append(f"{'gefragt' if f['fragen'] else 'nicht gefragt'}: {f['text']} – {preise}, Unterschied "
                   f"{z(f['unterschied'])} € ({z(100 * f['anteil'], 1)} %, Schwelle {z(100 * schwelle, 1)} %)")
    return out


def nicht_gefragt(w):
    return [f for f in w["fragen"] if not f["fragen"]]
