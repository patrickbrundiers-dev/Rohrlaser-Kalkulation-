"""Liefertermin nach freier Kapazität (Vorschlag V2, Patrick 31.10.2026).

Frühester Liefertermin eines Angebots: das Material ist nach der Material-Lieferzeit da (Einstellung
'termin_material_tage' in Arbeitstagen; Kundenmaterial bzw. 0 = vorrätig), ab dieser Woche wird die Laserzeit des
Angebots in die freien Stunden der Maschine gelegt (Kapazität minus beauftragte Aufträge, wie in Datei →
Maschinenauslastung, auslastung.py). Die Woche, in der die letzte Stunde Platz findet, plus Vorlauf für Entgraten,
Verpacken, Versand (Einstellung 'auslastung_vorlauf') ergibt den Termin. Gerechnet ab Freitag dieser Woche (nie vor dem Tag,
an dem das Material da ist).

Ergebnis ist nur ein Vorschlag: im Angebotskopf (Knopf „Termin prüfen …“) und im Fenster „Beauftragt“."""
import datetime
from collections import namedtuple

from . import auslastung, feiertage

WOCHEN = 26                    # so weit voraus wird gesucht; danach „später“
Termin = namedtuple("Termin", "datum material_ab laser_h wochen hinweise")    # wochen = [(Montag, frei_h, belegt_h)]


def _f(v, vorgabe=0.0):
    try:
        return float(v) if v not in (None, "") else vorgabe
    except (TypeError, ValueError):
        return vorgabe


def material_ab(heute, tage, land):
    """Tag, an dem das Material da ist: heute + tage Arbeitstage."""
    return feiertage.arbeitstage_spaeter(heute, int(tage), land) if tage and tage > 0 else heute


def verteilen(laser_h, frei, ab_montag):
    """Laserstunden auf die freien Stunden der Wochen ab ab_montag legen. frei = [(Montag, freie h)] aufsteigend.
    Ergebnis: (Montag der letzten belegten Woche oder None = passt nicht, [(Montag, frei, belegt)])."""
    rest, belegt = max(0.0, laser_h), []
    for mo, h in frei:
        if mo < ab_montag:
            continue
        nimm = min(rest, max(0.0, h))
        belegt.append((mo, h, nimm))
        rest -= nimm
        if rest <= 1e-9:
            return mo, belegt
    return None, belegt


def fruehester(db, angebot_id, heute=None, auslast=None):
    """Frühester Liefertermin des Angebots (Termin) oder None, wenn das Angebot keinen Schnittplan hat.
    auslast = Ergebnis von auslastung.berechnen (Tests, mehrfaches Prüfen)."""
    heute = heute or datetime.date.today()
    a = db.angebot(angebot_id) or {}
    laser_h, _ = auslastung.maschinenzeit(db, a)
    if laser_h is None:
        return None
    land = db.einstellung("versand_bundesland") or feiertage.VORGABE
    vorlauf = int(_f(db.einstellung("auslastung_vorlauf"), 2))
    tage = int(_f(db.einstellung("termin_material_tage"), 3))
    from .angebot import KUNDENMATERIAL, aktiv
    pos = [p for p in db.positionen(angebot_id) if aktiv(p) and p.get("profil_id")]
    if pos and all(p.get("material_herkunft") == KUNDENMATERIAL for p in pos):
        tage = 0                     # Kundenmaterial: kein Einkauf
    mat = material_ab(heute, tage, land)
    aus = auslast or auslastung.berechnen(db, heute, wochen=WOCHEN)
    m = a.get("maschine") or "?"
    frei = []
    for _, _, mo in aus["spalten"]:
        if mo is None:
            continue
        kap = aus["kapazitaet"].get((m, mo), 0.0)
        # eigenes Angebot (schon beauftragt) nicht doppelt zählen
        andere = sum(x["h"] for x in aus["auftraege"].get((m, mo), ()) if x["id"] != angebot_id)
        frei.append((mo, kap - andere))
    hinweise = []
    if mat > heute:
        hinweise.append(f"Material ab {mat.strftime('%d.%m.%Y')} (Material-Lieferzeit "
                        f"{tage} Arbeitstage)")
    ueberfaellig = sum(x["h"] for x in aus["auftraege"].get((m, auslastung.UEBERFAELLIG), ()) if x["id"] != angebot_id)
    if ueberfaellig > 0 and frei:            # Rückstand belegt zuerst die laufende Woche und die folgenden
        rest = ueberfaellig
        for i, (mo, h) in enumerate(frei):
            nimm = min(rest, max(0.0, h))
            frei[i] = (mo, h - nimm)
            rest -= nimm
            if rest <= 0:
                break
        hinweise.append(f"{auslastung_text(ueberfaellig)} überfällige Laserzeit vorgezogen")
    woche, belegt = verteilen(laser_h, frei, auslastung.montag(mat))
    voll = [mo for mo, h, _ in belegt if h <= 0.05]
    if voll:
        hinweise.append("ausgebucht: " + ", ".join(f"KW {mo.isocalendar()[1]}" for mo in voll[:6]))
    if woche is None:
        hinweise.append(f"passt nicht in die nächsten {WOCHEN} Wochen")
        return Termin(None, mat, laser_h, belegt, hinweise)
    fertig = max(mat, woche + datetime.timedelta(days=4))       # Freitag der Woche, nicht vor dem Material
    datum = feiertage.arbeitstage_spaeter(fertig, vorlauf, land) if vorlauf > 0 else fertig
    return Termin(datum, mat, laser_h, belegt, hinweise)


def auslastung_text(h):
    return f"{h:.1f} h".replace(".", ",")


def text(t, zugesagt=None):
    """Kurzer Satz für Anzeige und Tooltip; zugesagt = Termin aus der Lieferzeit des Angebots."""
    if t is None:
        return "Termin nach Auslastung: erst optimieren (die Laserzeit kommt aus dem Schnittplan)."
    if t.datum is None:
        s = "Kein Termin in den nächsten Wochen frei."
    else:
        s = (f"Frühestens KW {t.datum.isocalendar()[1]} ({t.datum.strftime('%d.%m.%Y')}), "
             f"Laserzeit {auslastung_text(t.laser_h)}")
    if zugesagt and t.datum and zugesagt < t.datum:
        s += f" – die Lieferzeit im Angebot ({zugesagt.strftime('%d.%m.%Y')}) ist nicht zu halten"
    return s + (". " + "; ".join(t.hinweise) + "." if t.hinweise else ".")


def kw_wert(datum):
    """Wert für die Lieferzeit „Kalenderwoche“ (KW/Jahr)."""
    j, kw, _ = datum.isocalendar()
    return f"{kw}/{j}"


def haltbar(t, zugesagt):
    """True/False: hält die Lieferzeit des Angebots; None = nicht prüfbar."""
    if t is None or zugesagt is None:
        return None
    return t.datum is not None and zugesagt >= t.datum
