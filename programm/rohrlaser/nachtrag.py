"""Nachtrag automatisch einsortieren (Automationen 03.11.2026, Vorschlag 5a).

Eine Mail ohne STEP mit der Anfrage-Nr. eines vorhandenen Angebots vom Kunden des Angebots (anfragen._ohne_step_namen,
Patrick 28.10.2026 F2) legt das Programm selbst in den Angebotsordner (Unterordner „Anfrage“), vermerkt sie im
Versandverlauf (art 'nachtrag') und im Automatik-Protokoll (mit Rückgängig = Mail zurück in den Anfrage-Ordner).
Was die Mail ändert, wird ausgelesen und beim nächsten Öffnen des Angebots als gelbe Einblendung zum Übernehmen
angeboten – nie ohne Klick:
- Stückzahlen je Artikel (formular.stueckzahlen, nur sichere Angaben „20 Stk“),
- Wunschtermin (mail.termin) als Lieferzeit,
- ein eindeutig genannter Werkstoff (mail.werkstoff), wenn die Positionen einen anderen haben.
Zusatzdaten des Angebots: 'nachtraege' = [dict(datei, zeit, betreff, stueck {Positions-ID: [alt, neu, Artikel]},
lieferzeit [Art, Wert, Satz] oder None, werkstoff [ID, Wort] oder None, status 'offen'/'übernommen'/'abgelehnt')].
Ohne Qt."""
import datetime
from pathlib import Path

SCHLUESSEL = "nachtraege"
UNTERORDNER = "Anfrage"
OFFEN, UEBERNOMMEN, ABGELEHNT = "offen", "übernommen", "abgelehnt"


def aenderungen(db, angebot_id, m):
    """Änderungen der Mail m gegenüber dem Angebot: dict(stueck, lieferzeit, werkstoff) (nur Gefundenes)."""
    from . import formular, mail
    kopf = db.angebot(angebot_id) or {}
    pos = db.positionen(angebot_id)
    text = mail.neuester_teil(m.volltext()) if m else ""
    out = {}
    namen = {str(p.get("artikel")).strip(): p for p in pos if str(p.get("artikel") or "").strip()}
    stueck = {}
    for name, (menge, sicher) in formular.stueckzahlen(text, list(namen)).items():
        p = namen[name]
        if sicher and int(menge) != int(p.get("stueck") or 0):
            stueck[str(p["id"])] = [int(p.get("stueck") or 0), int(menge), name]
    if stueck:
        out["stueck"] = stueck
    art, wert, satz = mail.termin(text)
    if art and (art, str(wert)) != (kopf.get("lieferzeit_art"), str(kopf.get("lieferzeit_wert"))):
        out["lieferzeit"] = [art, wert, satz[:120]]
    ws, wort, _ = mail.werkstoff(text, db.zeilen("werkstoffe"))
    if ws and any(p.get("werkstoff_id") and p.get("werkstoff_id") != ws for p in pos if p.get("profil_id")):
        out["werkstoff"] = [ws, wort]
    return out


def text(e):
    """Kurztext der Änderungen eines Nachtrags (für Einblendung und Protokoll)."""
    from .angebot import lieferzeit_text
    teile = []
    for alt, neu, artikel in (e.get("stueck") or {}).values():
        teile.append(f"{artikel}: {alt} → {neu} Stk")
    if e.get("lieferzeit"):
        teile.append(lieferzeit_text(dict(lieferzeit_art=e["lieferzeit"][0],
                                          lieferzeit_wert=e["lieferzeit"][1])).rstrip("."))
    if e.get("werkstoff"):
        teile.append(f"Werkstoff {e['werkstoff'][0]}")
    return "; ".join(teile)


def einsortieren(db, angebot_id, pfad, ziel, m=None):
    """Mail pfad in ziel/Anfrage verschieben, vermerken und Änderungen merken. Ergebnis: der Eintrag (dict).
    OSError, wenn sich die Datei nicht verschieben lässt."""
    from . import automatik, mail
    m = m if m is not None else mail.lesen(pfad)
    kopf = db.angebot(angebot_id) or {}
    a = aenderungen(db, angebot_id, m) if m else {}
    neu = automatik.verschieben(db, pfad, Path(ziel) / UNTERORDNER, "nachtrag",
                                f"{Path(pfad).name} zu Angebot {kopf.get('nummer')} in den Angebotsordner gelegt"
                                + (f" ({text(a)})" if a else ""), angebot_id)
    e = dict(datei=str(neu), zeit=datetime.datetime.now().isoformat(timespec="seconds"),
             betreff=(m.betreff if m else "") or Path(pfad).name, status=OFFEN if a else UEBERNOMMEN, **a)
    db.zusatz_setzen(angebot_id, SCHLUESSEL, list(db.zusatz(angebot_id, SCHLUESSEL, []) or []) + [e])
    db.versand_merken(angebot_id, dict(art="nachtrag", datum=datetime.date.today().isoformat(),
                                       datei=Path(neu).name, text=text(a)))
    return e


def offene(db, angebot_id):
    """[(Index, Eintrag)] der Nachträge mit Änderungen, die noch nicht übernommen oder abgelehnt sind."""
    return [(i, e) for i, e in enumerate(db.zusatz(angebot_id, SCHLUESSEL, []) or [])
            if isinstance(e, dict) and e.get("status") == OFFEN]


def status_setzen(db, angebot_id, index, status):
    alle = list(db.zusatz(angebot_id, SCHLUESSEL, []) or [])
    if 0 <= index < len(alle):
        alle[index] = dict(alle[index], status=status)
        db.zusatz_setzen(angebot_id, SCHLUESSEL, alle)


def anwenden(db, angebot_id, e):
    """Änderungen eines Nachtrags ins Angebot schreiben (Stückzahlen, Lieferzeit, Werkstoff der Rohrlaserteile).
    Ergebnis: Anzahl geänderter Felder."""
    n = 0
    vorhanden = {str(p["id"]): p for p in db.positionen(angebot_id)}
    for pid, (_, neu, _) in (e.get("stueck") or {}).items():
        if pid in vorhanden:
            db.position_aendern(int(pid), "stueck", int(neu))
            n += 1
    if e.get("lieferzeit"):
        db.angebot_aendern(angebot_id, "lieferzeit_art", e["lieferzeit"][0])
        db.angebot_aendern(angebot_id, "lieferzeit_wert", e["lieferzeit"][1])
        n += 1
    if e.get("werkstoff"):
        for p in vorhanden.values():
            if p.get("profil_id") and p.get("werkstoff_id") and p["werkstoff_id"] != e["werkstoff"][0]:
                db.position_aendern(p["id"], "werkstoff_id", e["werkstoff"][0])
                n += 1
    return n
