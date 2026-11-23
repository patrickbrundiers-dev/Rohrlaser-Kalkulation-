"""Wichtig zuerst: Reihenfolge der offenen Anfragen mit Gründen (Patrick 23.11.2026, Stufe 2 Punkt 2).

Punkte je Akte (punkte), jeder Teil mit Grund, damit die Reihenfolge nachvollziehbar bleibt:
  - Antwortfrist: überfällig +40, heute fällig +25
  - Priorität: Eilt +30, Hoch +15, Niedrig −10
  - Mail-Art: Bestellung +35, Reklamation +30, Auftragsänderung +25, Nachfrage/Änderung zum Angebot +15,
    Liefertermin +10, technische Rückfrage +5, Allgemein −10, Werbung −50
  - Kunde: erwarteter Auftragswert (Trefferquote × üblicher Angebotswert, vertrieb.wichtigkeit) bis +20
  - Menge: größte genannte Stückzahl ab 100 Stück +5, ab 500 Stück +10
  - Rückfrage nachzufassen +10; wartet auf den Kunden (Rückfrage offen, noch nicht fällig) −20
Erledigte Anfragen haben keinen Platz. sortieren() ordnet nach Punkten, bei Gleichstand ältere zuerst.
Nur Anzeige und Sortierung, nichts wird geändert. Ohne Qt."""
from . import anfrage_art as aa
from . import anfragen_akten as ak

FRIST = {"rot": (40, "Antwortfrist überschritten"), "gelb": (25, "heute fällig")}
PRIO = {"eilt": (30, "Priorität Eilt"), "hoch": (15, "Priorität Hoch"), "niedrig": (-10, "Priorität Niedrig")}
ART = {aa.BESTELLUNG: 35, aa.REKLAMATION: 30, aa.AUFTRAG_AENDERUNG: 25, aa.NACHFRAGE: 15, aa.AENDERUNG: 15,
       aa.LIEFERTERMIN: 10, aa.TECHNIK: 5, aa.ALLGEMEIN: -10, aa.WERBUNG: -50}
KUNDE_MAX, KUNDE_JE = 20, 500.0         # je 500 € erwarteter Wert 1 Punkt, höchstens 20
MENGE = ((500, 10), (100, 5))
NACHFASSEN, WARTET = 10, -20


def _menge(technik):
    best = 0
    for t in technik or ():
        if t.get("feld") != "stueckzahl":
            continue
        try:
            best = max(best, int(str(t.get("wert") or "").replace(".", "").split()[0]))
        except (ValueError, IndexError):
            continue
    return best


def punkte(akte, ampel=None, einordnung=None, technik=(), wert=(0.0, ""), nachfassen=None):
    """(Punkte, [(Punkte, Grund)]) oder (None, []) für erledigte Anfragen. ampel: Stufe 'rot'/'gelb'/…;
    einordnung: Mail-Art (kompakt); wert: vertrieb.wichtigkeit; nachfassen: anfrage_nachfassen.stand."""
    if akte.status == ak.ERLEDIGT or akte.aussortiert:
        return None, []
    teile = []
    if ampel in FRIST:
        teile.append(FRIST[ampel])
    if akte.prioritaet in PRIO:
        teile.append(PRIO[akte.prioritaet])
    art = (einordnung or {}).get("art")
    if art in ART:
        teile.append((ART[art], aa.ARTEN.get(art, art)))
    w, grund = wert or (0.0, "")
    if w > 0:
        p = min(KUNDE_MAX, int(w // KUNDE_JE))
        if p:
            teile.append((p, grund or "wertvoller Kunde"))
    n = _menge(technik)
    for ab, p in MENGE:
        if n >= ab:
            teile.append((p, f"{n} Stück"))
            break
    if nachfassen and nachfassen.get("faellig_ist"):
        teile.append((NACHFASSEN, "Rückfrage nachfassen"))
    elif akte.stand.get("rueckfrage"):
        teile.append((WARTET, "wartet auf den Kunden"))
    return sum(p for p, _ in teile), teile


def text(teile):
    return ", ".join(f"{g} ({'+' if p > 0 else '−'}{abs(p)})" for p, g in teile) or "keine Besonderheit"


def sortieren(akten, je):
    """akten nach Punkten (je: {Nummer: (Punkte, Teile)}), höchste zuerst; ohne Punkte (erledigt) ans Ende; bei
    Gleichstand ältere zuerst."""
    def schluessel(a):
        p = (je.get(a.nr) or (None,))[0]
        e = a.eingang.isoformat() if a.eingang else "9999"
        return (p is None, -(p or 0), e)
    return sorted(akten, key=schluessel)
