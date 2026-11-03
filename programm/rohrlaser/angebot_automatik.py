"""Automationen bei der Angebotserstellung (Paket D, 03.11.2026, Freigabe Patrick „Auch mit einbauen“).

Nach dem STEP-Import eines neuen Angebots (nach_import, aufgerufen aus AngebotSeite.step_importieren):
- E6 Beistellung und Oberfläche aus der Mail: „Material wird beigestellt“, „Kundenmaterial“ … setzt Material = Kunde
  für alle Rohrlaserteile; eine Oberfläche aus den Stammdaten, die die Mail eindeutig nennt (z. B. „gebeizt“), wird
  an den Rohrlaserteilen gesetzt. Beides mit Rückgängig; Beschichtungen (verzinkt, pulverbeschichtet RAL …) schlägt
  der Import schon als Zusatzarbeit vor.
- E3 Günstigste Maschine: ist eine andere Maschine mehr als 5 % günstiger und kann alle Teile, stellt das Programm sie
  ein und rechnet neu (Rückgängig in der Einblendung und im Automatik-Protokoll).
- E4 Liefertermin aus der Kapazität: nennt der Kunde keinen Termin, wird die Lieferzeit auf die Kalenderwoche des
  frühesten Termins (Maschinenauslastung + Material-Lieferzeit, terminplan) gesetzt; nennt er einen, der nicht
  machbar ist, erscheint eine Warnung.
- E8 Rückfrage vorbereiten: fehlen Angaben (rueckfrage.punkte), bietet die Einblendung „Rückfrage öffnen …“ an.

fertigstellen (E1): Angebots-PDF (mit Optimieren und Angebots-Check), Outlook-Antwort auf die Anfrage-Mail mit PDF,
Vorgang Verschickt und Wiedervorlage in einem Zug; danach (E2) „Nächste Anfrage“ (die dringendste offene).
Gesendet wird nur in Outlook. Was das Programm von selbst tut, steht im Automatik-Protokoll.
"""
import datetime
import re

GUENSTIGER_AB = 0.05            # E3: andere Maschine mehr als 5 % günstiger
BEISTELLUNG = re.compile(r"(material\s+(?:wird|werden)\s+(?:von\s+uns\s+)?beigestellt|beigestellte[sn]?\s+material|"
                         r"beistellung|kundenmaterial|material\s+(?:stellen|liefern)\s+wir|"
                         r"(?:rohre|material)\s+(?:kommt|kommen)\s+von\s+uns|wir\s+stellen\s+(?:das\s+)?material)",
                         re.I)
NICHT_BEISTELLUNG = re.compile(r"(keine?\s+beistellung|ohne\s+beistellung|nicht\s+beigestellt|"
                               r"kein\s+kundenmaterial)", re.I)


def beistellung(text):
    """True, wenn die Anfrage Kundenmaterial nennt („Material wird beigestellt“ …) und es nicht verneint."""
    from . import mail
    t = mail.neuester_teil(text or "")
    return bool(BEISTELLUNG.search(t)) and not NICHT_BEISTELLUNG.search(t)


def oberflaeche(text, namen):
    """Oberfläche aus den Stammdaten, die der Text als eigenes Wort nennt; None bei keiner oder mehreren. 'roh' zählt
    nicht (zu allgemein)."""
    from . import mail
    t = mail.neuester_teil(text or "")
    treffer = {n for n in namen if n and len(n) >= 3 and n.lower() != "roh"
               and re.search(rf"(?<![\w-]){re.escape(n)}(?![\w-])", t, re.I)}
    return treffer.pop() if len(treffer) == 1 else None


def _protokoll(seite, art, text, rueck=None):
    from . import automatik
    automatik.merken(seite.db, art, f"Angebot {seite.kopf.get('nummer')}: {text}", seite.id, rueck)


def nach_import(seite, werkstoff_text=None, heute=None):
    """Automationen nach dem Import eines neuen Angebots. Ergebnis: dict(texte=[kurze Sätze], aktion=(Knopf, fn)
    oder None, bericht=[Zeilen])."""
    from .angebot import kein_laserteil
    from .stammdaten import EIGENMATERIAL, KUNDENMATERIAL
    db = seite.db
    out = dict(texte=[], aktion=None, bericht=[])
    if seite.fremd() or db.nur_lesen:
        return out
    laser = [p for p in seite.positionen if not kein_laserteil(p) and p.get("profil_id")]
    # E6 Beistellung und Oberfläche aus der Mail
    if werkstoff_text and laser:
        if beistellung(werkstoff_text):
            alt = [(p["id"], p.get("material_herkunft")) for p in laser
                   if (p.get("material_herkunft") or EIGENMATERIAL) != KUNDENMATERIAL]
            for pid, _ in alt:
                db.position_aendern(pid, "material_herkunft", KUNDENMATERIAL)
            if alt:
                out["texte"].append(f"Material beigestellt (laut Mail) bei {len(alt)} Position(en)")
                _protokoll(seite, "angebot_auto", f"Material = Kunde (beigestellt laut Mail) bei {len(alt)} "
                           "Position(en)", dict(art="positionen", angebot_id=seite.id, feld="material_herkunft",
                                                alt=alt))
        ob = oberflaeche(werkstoff_text, list(seite.k.oberflaechen))
        if ob:
            alt = [(p["id"], p.get("oberflaeche")) for p in laser if (p.get("oberflaeche") or "") != ob]
            for pid, _ in alt:
                db.position_aendern(pid, "oberflaeche", ob)
            if alt:
                out["texte"].append(f"Oberfläche {ob} (laut Mail)")
                _protokoll(seite, "angebot_auto", f"Oberfläche {ob} (laut Mail) bei {len(alt)} Position(en)",
                           dict(art="positionen", angebot_id=seite.id, feld="oberflaeche", alt=alt))
        seite.neu_laden()
    if not laser:
        return out
    # Schnittplan für Maschine und Termin
    if seite.stand_optimierung() != "aktuell":
        try:
            seite.optimieren(automatisch=True)
        except Exception:
            return out
    if not seite.ergebnis:
        return out
    # E3 Günstigste Maschine
    try:
        _maschine(seite, out)
    except Exception as e:      # nie am Import scheitern
        out["bericht"].append(f"Maschinenvergleich nicht möglich: {e}")
    # E4 Liefertermin aus der Kapazität
    try:
        _termin(seite, out, heute)
    except Exception as e:
        out["bericht"].append(f"Liefertermin nach Auslastung nicht möglich: {e}")
    # E8 Rückfrage vorbereiten
    try:
        from . import rueckfrage
        zeilen, summen = seite._rechnung()
        punkte = rueckfrage.punkte(seite.freigabe_punkte(summen, zeilen), seite.positionen, zeilen)
    except Exception:
        punkte = []
    if punkte:
        out["texte"].append(f"{len(punkte)} offene Punkt(e) für eine Rückfrage")
        out["bericht"] += ["Offene Punkte für die Rückfrage an den Kunden:"] + [f"- {p}" for p in punkte]
        out["aktion"] = ("Rückfrage öffnen …", lambda: seite.rueckfrage())
    return out


def _maschine(seite, out):
    from . import maschinen_vergleich
    from .angebot import KOPF
    from .stammdaten import zahl_als_text as zahl
    if len(seite.k_aktuell.maschinen) < 2 or len(seite.positionen) > 80:
        return
    alt = seite.kopf.get("maschine")
    g = maschinen_vergleich.guenstiger(seite.maschinen_vergleich_liste(), alt, GUENSTIGER_AB)
    if not g:
        return
    best, anteil = g
    seite._kopf_speichern(next(f for f in KOPF if f.name == "maschine"), best["maschine"])
    seite.optimieren(automatisch=True)
    seite.maschine_automatisch = alt
    text = f"Maschine {best['maschine']} statt {alt or 'Vorgabe'} ({zahl(100 * anteil, 1)} % günstiger)"
    out["texte"].append(text)
    _protokoll(seite, "angebot_auto", text, dict(art="kopf", angebot_id=seite.id, alt=dict(maschine=alt)))
    if out["aktion"] is None:
        out["aktion"] = ("Rückgängig", lambda: maschine_zurueck(seite, alt))


def maschine_zurueck(seite, alt):
    from .angebot import KOPF
    seite._kopf_speichern(next(f for f in KOPF if f.name == "maschine"), alt)
    seite.optimieren(automatisch=True)
    seite.maschine_automatisch = None
    seite.f.meldung(f"Maschine wieder {alt or 'Vorgabe'}.")


def _termin(seite, out, heute=None):
    from . import auftrag, funktionen, terminplan
    from .stammdaten import KALENDERWOCHE
    if not funktionen.an("funktion_auslastung", seite.db):
        return
    t = terminplan.fruehester(seite.db, seite.id)
    if t is None or t.datum is None:
        return
    k = seite.kopf
    if k.get("lieferzeit_art") and k.get("lieferzeit_wert") or k.get("liefertermin"):
        wunsch = auftrag.termin_vorschlag(k, heute)
        if wunsch < t.datum:
            out["texte"].append(f"Wunschtermin {wunsch:%d.%m.} nicht machbar (frühestens KW "
                                f"{t.datum.isocalendar()[1]}) – Termin prüfen …")
            out["warnung"] = True
        return
    wert = terminplan.kw_wert(t.datum)
    seite.db.angebot_aendern(seite.id, "lieferzeit_art", KALENDERWOCHE)
    seite.db.angebot_aendern(seite.id, "lieferzeit_wert", wert)
    seite.neu_laden()
    out["texte"].append(f"Lieferzeit KW {wert} nach Auslastung")
    _protokoll(seite, "angebot_auto", f"Lieferzeit KW {wert} nach Maschinenauslastung und Material-Lieferzeit",
               dict(art="kopf", angebot_id=seite.id, alt=dict(lieferzeit_art=k.get("lieferzeit_art"),
                                                             lieferzeit_wert=k.get("lieferzeit_wert"))))


# ---------------------------------------------------------------------- E1/E2 Fertigstellen
def wiedervorlage_tage(db):
    try:
        return max(1, int(float(db.einstellung("nachfassen_tage") or 7)))
    except (TypeError, ValueError):
        return 7


def fertigstellen(seite, dialog=None, ausfuehren=None, heute=None):
    """E1: Angebots-PDF, Outlook-Antwort mit PDF, Verschickt, Wiedervorlage. dialog/ausfuehren wie angebot_mail
    (Tests). Ergebnis: True, wenn die Mail vorbereitet ist; hält bei einem Fehler im Check an (False)."""
    from . import feiertage
    f = seite.f
    if seite.fremd():
        f.meldung("Fertigstellen nur für eigene Angebote.", fehler=True)
        return False
    d = seite.angebot_mail(dialog=dialog, ausfuehren=ausfuehren)
    if d is None:               # PDF nicht erstellt (Check, Freigabe, abgebrochen): die Kette hält an
        return False
    if not getattr(d, "eintrag", None):
        f.meldung("Fertigstellen: E-Mail nicht vorbereitet – Angebots-PDF liegt in der Ablage.", fehler=True)
        return False
    heute = heute or datetime.date.today()
    if (seite.db.angebot(seite.id) or {}).get("vorgang") in (None, "", "Entwurf"):
        seite.db.vorgang_setzen(seite.id, "Verschickt")
    am = feiertage.arbeitstage_spaeter(heute, wiedervorlage_tage(seite.db), seite.db.einstellung("versand_bundesland"))
    seite.db.wiedervorlage_setzen(seite.id, am)
    f.angebote.neu_laden()
    _protokoll(seite, "angebot_auto", f"fertiggestellt: PDF, Outlook-Antwort, Verschickt, Wiedervorlage {am:%d.%m.%Y}")
    naechste = naechste_anfrage(f)
    f.meldung(f"Angebot {seite.kopf.get('nummer')} fertig: PDF, E-Mail in Outlook, Verschickt, Wiedervorlage am "
              f"{am:%d.%m.%Y}." + (f" Nächste Anfrage: {naechste.name}." if naechste else ""),
              aktion=("Nächste Anfrage", lambda: f.start.anfragen.oeffnen([naechste])) if naechste else None)
    return True


def naechste_anfrage(f):
    """E2: dringendste offene, nicht gesperrte Anfrage (Reihenfolge der Karte = Ampel), eigene Zuweisung zuerst."""
    karte = getattr(getattr(f, "start", None), "anfragen", None)
    if karte is None:
        return None
    try:
        karte.neu_laden()
    except Exception:
        pass
    ich = f.db.einstellung("benutzer_kuerzel") or ""
    frei = [a for a in karte.anfragen if not a.gesperrt and a.zugewiesen.get("an") in (None, "", ich)]
    frei.sort(key=lambda a: a.zugewiesen.get("an") != ich)
    return frei[0] if frei else None
