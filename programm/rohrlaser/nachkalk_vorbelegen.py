"""Nachkalkulation automatisch vorbelegen (Automationen 03.11.2026, Vorschlag 10a).

Wird ein Auftrag auf „Versendet“ gesetzt (Reiter Versand), füllt das Programm die Nachkalkulation vor, wenn noch
keine Ist-Werte erfasst sind: Ist-Laserzeit aus den Scans Laser Start/Ende (etiketten.laserzeit, H4b), alles andere
wie geplant (nachkalkulation.rest_wie_geplant). Weicht der Deckungsbeitrag dann mehr als die Einstellung
'nachkalk_schwelle' (Vorgabe 10 %) vom Soll ab, erscheint der Auftrag auf der Startseite unter „Nachkalkulation
prüfen“, bis die Nachkalkulation im Angebot geöffnet und gespeichert wird. Rückgängig über das Automatik-Protokoll.
Zusatzdaten 'nachkalk_vorbelegt' = dict(am, abweichung, laser_ist, geprueft). Ohne Qt."""
import datetime

SCHLUESSEL = "nachkalk_vorbelegt"


def _schwelle(db):
    w = db.einstellung("nachkalk_schwelle")
    return 0.10 if w in (None, "") else float(w)


def vorbelegen(db, angebot_id):
    """Ergebnis: dict(abweichung, laser_ist) oder None (schon Ist-Werte, kein Schnittplan, nicht rechenbar)."""
    from . import automatik, etiketten, nachkalkulation as nk, preis_simulator
    a = db.angebot(angebot_id)
    if not a or a.get("fremd") or a.get("nachkalkulation") or not a.get("ergebnis"):
        return None
    pos = db.positionen(angebot_id)
    try:
        k, tab, e = preis_simulator.grundlage(db, a)
        ist = {}
        lz = etiketten.laserzeit(db, angebot_id)
        quelle = "Laserzeit aus den Scans"
        if lz and not lz.get("offen"):
            ist["laser_h"] = round(lz["stunden"], 3)
        else:           # Schnittstelle 11.11.2026: Ist-Laserzeit aus der Rückmeldung der Rohrlaser Auslastung
            from . import auslastung_austausch
            try:
                h = auslastung_austausch.ist_laser_h(db, a.get("nummer"))
            except Exception:
                h = None
            if h:
                ist["laser_h"] = round(h, 3)
                quelle = "Laserzeit aus der Rohrlaser Auslastung"
        v = nk.vergleich(a, pos, a["ergebnis"], k, tab, e, ist)
        ist, _ = nk.rest_wie_geplant(v, ist)
        ist["am"] = datetime.date.today().isoformat()
        ist["bemerkung"] = f"automatisch vorbelegt beim Versand ({quelle}, Rest wie geplant)"
        v2 = nk.vergleich(a, pos, a["ergebnis"], k, tab, e, ist)
    except (ValueError, KeyError, TypeError, ZeroDivisionError, AttributeError):
        return None
    try:            # Soll-Stand wie beim Speichern im Angebot (Auswertung, Kennwert-Vorschläge)
        ist["soll"] = nk.soll_stand(v2, a, pos, a["ergebnis"], k)
    except Exception:
        pass
    soll_db, ist_db = v2["db"]["soll"], v2["db"]["ist"]
    abw = (ist_db - soll_db) / abs(soll_db) if soll_db else None
    alt_zusatz = db.zusatz(angebot_id, SCHLUESSEL)
    db.nachkalkulation_speichern(angebot_id, ist)
    info = dict(am=ist["am"], abweichung=abw, laser_ist=ist.get("laser_h") if lz else None, geprueft=False)
    db.zusatz_setzen(angebot_id, SCHLUESSEL, info)
    automatik.merken(db, "nachkalk", f"Angebot {a.get('nummer')}: Nachkalkulation vorbelegt"
                     + (f", Deckungsbeitrag {abw * 100:+.0f} % gegen Soll" if abw is not None else ""), angebot_id,
                     dict(art="nachkalk", angebot_id=angebot_id, alt=None, zusatz_alt=alt_zusatz))
    return info


def geprueft(db, angebot_id):
    """Nachkalkulation wurde im Angebot gespeichert: nicht mehr auf der Startseite zeigen."""
    info = db.zusatz(angebot_id, SCHLUESSEL)
    if isinstance(info, dict) and not info.get("geprueft"):
        db.zusatz_setzen(angebot_id, SCHLUESSEL, dict(info, geprueft=True))


def zu_pruefen(db):
    """[dict(angebot_id, nummer, text)] vorbelegter Nachkalkulationen mit Abweichung über der Schwelle."""
    s = _schwelle(db)
    out = []
    for aid, nummer in db.con.execute("SELECT id, nummer FROM angebote WHERE zusatz LIKE '%nachkalk_vorbelegt%' "
                                      "AND COALESCE(fremd, '')=''"):
        info = db.zusatz(aid, SCHLUESSEL)
        if not isinstance(info, dict) or info.get("geprueft") or info.get("abweichung") is None:
            continue
        if abs(info["abweichung"]) > s:
            out.append(dict(angebot_id=aid, nummer=nummer,
                            text=f"Deckungsbeitrag {info['abweichung'] * 100:+.0f} % gegen Soll"
                                 + (f" (Laserzeit Ist {info['laser_ist']:.2f} h)".replace(".", ",")
                                    if info.get("laser_ist") else "")))
    return out
