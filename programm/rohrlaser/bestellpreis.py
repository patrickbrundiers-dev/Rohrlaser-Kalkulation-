"""Echter Materialpreis zurück in die Kalkulation (Plan Angebotskalkulation 16.11.2026, Paket K3, F4a). Ohne Qt.

Der Bestellpreis ist die gewählte Lieferantenantwort eines Angebots (lieferantenangebote.py, „Übernehmen“), in €/m
umgerechnet. Daraus:

1. Nachkalkulation: Beim Übernehmen der Rückmeldungen (nachkalk_rueckmeldung) wird der Bestellpreis des eigenen
   Angebots als EK-Meterpreis Ist je Stangengruppe eingetragen, wenn dort nichts steht (Herkunft 'bestellung').
2. Auswertung der Aufträge: Material Ist = Material kalkuliert × (Material Ist ÷ Soll der Nachkalkulation), sobald
   ein Bestellpreis oder von Hand eingetragene Ist-Werte vorliegen (sonst wie kalkuliert).
3. Angebots-Check: liegt der letzte Bestellpreis einer Abmessung (über alle Angebote) mehr als SCHWELLE über dem
   Meterpreis, mit dem das Angebot rechnet, kommt ein HINWEIS; „Erledigen“ übernimmt ihn in die Stammdaten Preise
   (wie „Übernehmen“ bei den Lieferantenangeboten). Nur Hinweis: kein Preis ändert sich von selbst.
"""
import datetime

from . import lieferantenangebote as la

SCHWELLE = 0.05
AKTION = "bestellpreis"
QUELLE = "bestellung"


def _datum(t):
    try:
        return datetime.date.fromisoformat(str(t or "")[:10])
    except ValueError:
        return None


def eigene(db, angebot_id, k):
    """{(Profil, Werkstoff): dict(je_m, lieferant, datum)} der gewählten Antworten dieses Angebots."""
    out = {}
    for e in la.liste(db, angebot_id):
        if e.get("gewaehlt"):
            m = la.je_m(e, k)
            if m:
                out[(e["profil_id"], e["werkstoff_id"])] = dict(je_m=m, lieferant=e.get("lieferant") or "",
                                                                datum=e.get("datum") or "")
    return out


def letzte(db, k):
    """{(Profil, Werkstoff): dict(je_m, lieferant, datum, angebot_id, nummer, index)} – jüngste gewählte Antwort
    über alle Angebote."""
    out = {}
    for aid, nummer in db.con.execute("SELECT id, nummer FROM angebote WHERE zusatz LIKE '%lieferantenangebote%'"):
        for i, e in enumerate(la.liste(db, aid)):
            if not e.get("gewaehlt"):
                continue
            m = la.je_m(e, k)
            schl = (e["profil_id"], e["werkstoff_id"])
            if not m or (schl in out and str(out[schl]["datum"]) >= str(e.get("datum") or "")):
                continue
            out[schl] = dict(je_m=m, lieferant=e.get("lieferant") or "", datum=e.get("datum") or "", angebot_id=aid,
                             nummer=nummer, index=i)
    return out


def _schluessel(gruppe):
    """(Profil, Werkstoff) einer Stangengruppe der Nachkalkulation; None bei Oberfläche, Kundenmaterial, Muster."""
    teile = str(gruppe["schluessel"]).split("|")
    return (teile[0], teile[1]) if len(teile) == 3 else None


def in_nachkalkulation(ist, gruppen, bestell):
    """Bestellpreise als EK-Meterpreis Ist in leere Felder (bzw. solche, die schon aus Bestellungen stammen).
    Ergebnis: Anzahl geschriebener Felder."""
    mp = dict(ist.get("meterpreis") or {})
    q = dict((ist.get("quelle") or {}).get("meterpreis") or {})
    n = 0
    for g in gruppen:
        s = _schluessel(g)
        b = bestell.get(s) if s else None
        if not b:
            continue
        key = g["schluessel"]
        if mp.get(key) not in (None, "") and q.get(key) != QUELLE:
            continue
        neu = round(b["je_m"], 4)
        if mp.get(key) != neu:
            n += 1
        mp[key], q[key] = neu, QUELLE
    if mp:
        ist["meterpreis"] = mp
    if q:
        ist.setdefault("quelle", {})["meterpreis"] = q
    return n


def material_faktor(ist):
    """Material Ist ÷ Soll aus dem gespeicherten Soll-Stand der Nachkalkulation, nur wenn ein Ist-Meterpreis oder
    Ist-Stangen eingetragen sind; sonst None."""
    ist = ist or {}
    if not any(v not in (None, "") for n in ("meterpreis", "stangen") for v in (ist.get(n) or {}).values()):
        return None
    for z in ((ist.get("soll") or {}).get("zeilen") or ()):
        if z and z[0] == "Material" and isinstance(z[5], (int, float)) and z[5] > 0 and isinstance(z[6], (int, float)):
            return z[6] / z[5]
    return None


def abweichungen(gruppen, letzte_, eigenes_angebot=None, schwelle=SCHWELLE):
    """[dict(profil_id, werkstoff_id, kalk, bestell, lieferant, datum, nummer, angebot_id, index, prozent)] für
    Abmessungen, deren letzter Bestellpreis mehr als schwelle über dem kalkulierten Meterpreis liegt."""
    out, gesehen = [], set()
    for g in gruppen:
        s = _schluessel(g)
        if not s or s in gesehen or not g.get("meterpreis"):
            continue
        gesehen.add(s)
        b = letzte_.get(s)
        if not b or b["angebot_id"] == eigenes_angebot:
            continue
        if b["je_m"] > g["meterpreis"] * (1 + schwelle):
            out.append(dict(profil_id=s[0], werkstoff_id=s[1], kalk=g["meterpreis"], bestell=b["je_m"],
                            lieferant=b["lieferant"], datum=b["datum"], nummer=b["nummer"], angebot_id=b["angebot_id"],
                            index=b["index"], prozent=b["je_m"] / g["meterpreis"] - 1))
    return out


def punkte(liste):
    from .angebot_check import HINWEIS, Punkt
    from .stammdaten import zahl_als_text as zahl
    out = []
    for x in liste:
        d = _datum(x["datum"])
        out.append(Punkt(HINWEIS, f"{x['profil_id']} {x['werkstoff_id']}: zuletzt für {zahl(x['bestell'], 2)} €/m "
                                  f"bestellt ({x['lieferant']}{', ' + format(d, '%d.%m.%Y') if d else ''}, Angebot "
                                  f"{x['nummer']}), {zahl(100 * x['prozent'], 0)} % über dem kalkulierten "
                                  f"{zahl(x['kalk'], 2)} €/m. „Erledigen“ übernimmt den Bestellpreis in die Preise.",
                         None, aktion=AKTION))
    return out


def uebernehmen(db, liste):
    """Bestellpreise in die Stammdaten Preise (wie Lieferantenangebote „Übernehmen“). Ergebnis: [(Preis-ID, alt)]
    zum Rückgängigmachen (alt = alte Zeile oder None, wenn neu angelegt)."""
    out = []
    for x in liste:
        alt = next((dict(z) for z in db.zeilen("preise") if z.get("profil_id") == x["profil_id"]
                    and z.get("werkstoff_id") == x["werkstoff_id"]), None)
        out.append((la.uebernehmen(db, x["angebot_id"], x["index"]), alt))
    return out


def zurueck(db, aenderungen):
    for pid, alt in aenderungen:
        if alt is None:
            db.loeschen("preise", [pid])
            continue
        for f in ("basis", "preis", "gueltig_ab", "lieferant", "bemerkung", "lieferlaenge"):
            if f in alt:
                db.aendern("preise", pid, f, alt[f])
