"""Anfragen ohne STEP (Patrick 17.11.2026: „Emails die keine Daten sondern nur PDF oder ohne Anhang sind sollen trotzdem
als Anfrage bzw. Angebot angelegt werden können“, Freigabe „Alle Empfehlungen“ = F1-F5 a).

  F1 a  Mails nur mit PDF, nur mit DXF oder ganz ohne Anhang werden eine normale Anfrage (Liste, Akte, Ampel) mit
        Kennzeichen „📄 nur PDF“, „DXF ohne STEP“ bzw. „✉ ohne Anhang“ (anfragen.Anfrage.art, Akte.daten_art).
  F2 a  „Öffnen“ bzw. „Kalkulieren“ legt ein Angebot ohne Positionen an: Kunde, Anfrage-Nr., Wunschtermin und
        Bemerkung aus Mail und Formular; Mail und Dateien kommen in den Angebotsordner, Angebot und Anfrage sind
        verknüpft. Aus einer Zeichnung entsteht nie von selbst eine Position (Regel 28.10.2026).
  F3 a  Gelbe Leiste im Angebot mit „Dateien der Anfrage …“: je PDF bzw. DXF „Als Position übernehmen“ (Rohr-Editor
        aus der PDF-Zeichnung bzw. DXF-Import), erst auf Knopfdruck.
  F4 a  „STEP anfragen …“ öffnet die Rückfrage an den Kunden; schickt er die STEP nach (Antwort landet in der Akte),
        zeigt die Leiste „STEP einlesen“ und „Kalkulieren“ liest sie in dieses Angebot statt in ein neues.
  F5 a  Eine DXF zählt als Daten: ohne STEP öffnet gleich der DXF-Import (Bleche bzw. Rohr aus Ansichten).

Der Stand steht im Angebot (Zusatz ZUSATZ): dateien [{name, art, uebernommen}], hinweis [Zeilen aus der Mail],
status offen | step (STEP eingelesen) | aus (ausgeblendet), eingelesen [SHA-256 der eingelesenen STEP-Dateien].
Ohne Qt."""
import hashlib
from pathlib import Path

ZUSATZ = "anfrage_ohne_step"
OFFEN, STEP, AUS = "offen", "step", "aus"
ZEICHNUNG = {".pdf": "pdf", ".dxf": "dxf", ".png": "bild", ".jpg": "bild", ".jpeg": "bild", ".tif": "bild",
             ".tiff": "bild", ".xlsx": "excel", ".csv": "excel"}
UEBERNEHMBAR = ("pdf", "dxf", "bild")       # Rohr-Editor aus PDF/Scan, DXF-Import
ART_TEXT = {"pdf": "PDF", "dxf": "DXF", "bild": "Scan/Bild", "excel": "Stückliste"}


def eintraege(pfade):
    """Dateien der Anfrage, die im Angebot zur Hand sein sollen (Zeichnungen, DXF, Scans, Stücklisten)."""
    out, namen = [], set()
    for p in pfade:
        p = Path(p)
        a = ZEICHNUNG.get(p.suffix.lower())
        if a and p.name not in namen:
            namen.add(p.name)
            out.append(dict(name=p.name, art=a, uebernommen=False))
    return out


def merken(db, angebot_id, pfade, hinweis=()):
    """Angebot als „aus Anfrage ohne STEP“ kennzeichnen. Ergebnis: der gespeicherte Stand."""
    st = dict(dateien=eintraege(pfade), hinweis=[str(h) for h in hinweis or () if h], status=OFFEN, eingelesen=[])
    db.zusatz_setzen(angebot_id, ZUSATZ, st)
    return st


def stand(db, angebot_id):
    """Gespeicherter Stand oder None (Angebot nicht aus einer Anfrage ohne STEP)."""
    try:
        st = db.zusatz(angebot_id, ZUSATZ)
    except Exception:       # noqa: BLE001
        return None
    return st if isinstance(st, dict) else None


def _setzen(db, angebot_id, **werte):
    st = stand(db, angebot_id)
    if st is None:
        return None
    st.update(werte)
    db.zusatz_setzen(angebot_id, ZUSATZ, st)
    return st


def uebernommen(db, angebot_id, name):
    """Datei name als Position übernommen (Haken in der Liste)."""
    st = stand(db, angebot_id)
    if st is None:
        return None
    for d in st.get("dateien") or ():
        if d.get("name") == name:
            d["uebernommen"] = True
    db.zusatz_setzen(angebot_id, ZUSATZ, st)
    return st


def ausblenden(db, angebot_id):
    return _setzen(db, angebot_id, status=AUS)


def pfad(ordner, name):
    """Datei im Angebotsordner: Unterordner Anfrage (anfragen.ZIEL_FORMULAR), sonst irgendwo darin. None: fehlt."""
    from . import anfragen
    if not ordner:
        return None
    o = Path(ordner)
    for p in (o / anfragen.ZIEL_FORMULAR / name, o / name):
        if p.is_file():
            return p
    try:
        return next((p for p in o.rglob(name) if p.is_file()), None)
    except OSError:
        return None


def _summe(p):
    try:
        return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    except OSError:
        return ""


def nachgereicht(db, angebot_id):
    """STEP-Dateien, die der Kunde nachgereicht hat (Antwort in der verknüpften Akte) und die noch nicht in diesem
    Angebot eingelesen sind: [Path]. Ohne Anfragenverwaltung: []."""
    from . import anfragen_akten as ak
    st = stand(db, angebot_id)
    if st is None or not ak.aktiv(db):
        return []
    nummern = ak.akten_zum_angebot(db, angebot_id)
    if not nummern:
        return []
    try:
        abl = ak.ablage(db)
    except Exception:       # noqa: BLE001
        return []
    gelesen, out, namen = set(st.get("eingelesen") or ()), [], set()
    for nr in nummern:
        try:
            akte = abl.lesen(nr)
        except Exception:   # noqa: BLE001
            akte = None
        if akte is None or akte.virus():
            continue
        for d in akte.dateien():
            if d["art"] != "step" or d.get("gesperrt") or not d["pfad"].is_file():
                continue
            h = d.get("sha256") or _summe(d["pfad"])
            if h in gelesen or d["name"].lower() in namen:
                continue
            namen.add(d["name"].lower())
            out.append(d["pfad"])
    return out


def eingelesen(db, angebot_id, pfade):
    """Nachgereichte STEP-Dateien sind eingelesen: merken (Leiste weg, kein zweites Einlesen)."""
    st = stand(db, angebot_id)
    if st is None:
        return None
    st["eingelesen"] = sorted(set(st.get("eingelesen") or ()) | {_summe(p) for p in pfade} - {""})
    st["status"] = STEP
    db.zusatz_setzen(angebot_id, ZUSATZ, st)
    return st


def offene_angebote(db, akte):
    """IDs der Angebote zu dieser Akte, die aus der Anfrage ohne STEP entstanden und noch nicht mit STEP gefüllt
    sind (für „Kalkulieren“ nach der Antwort des Kunden), neueste zuerst."""
    out = []
    for nummer in reversed(akte.stand.get("angebote") or []):
        try:
            r = db.con.execute("SELECT id FROM angebote WHERE nummer=? ORDER BY id DESC LIMIT 1", (nummer,)).fetchone()
        except Exception:   # noqa: BLE001
            r = None
        st = stand(db, r[0]) if r else None
        if st is not None and st.get("status") != STEP:
            out.append(r[0])
    return out


def leiste_text(st, nach=()):
    """Text der gelben Leiste im Angebot oder '' (keine Leiste)."""
    if st is None:
        return ""
    if nach:
        return (f"<b>Der Kunde hat {len(nach)} STEP-Datei{'en' if len(nach) != 1 else ''} nachgereicht</b> "
                f"({', '.join(Path(p).name for p in list(nach)[:3])}{' …' if len(nach) > 3 else ''}): "
                "„STEP einlesen“ übernimmt sie in dieses Angebot.")
    if st.get("status") != OFFEN:
        return ""
    dateien = st.get("dateien") or []
    offen = [d for d in dateien if not d.get("uebernommen")]
    if dateien:
        arten = {}
        for d in dateien:
            arten[ART_TEXT.get(d["art"], d["art"])] = arten.get(ART_TEXT.get(d["art"], d["art"]), 0) + 1
        teile = ", ".join(f"{n} {a}" for a, n in arten.items())
        rest = f", {len(offen)} noch nicht als Position" if offen and len(offen) != len(dateien) else ""
        return (f"<b>Angebot aus einer Anfrage ohne STEP</b> ({teile}{rest}): Positionen von Hand oder mit "
                "„Dateien der Anfrage …“ anlegen, oder die STEP beim Kunden anfragen.")
    return ("<b>Angebot aus einer Anfrage ohne Anhang</b>: Positionen von Hand anlegen oder Zeichnung bzw. STEP beim "
            "Kunden anfragen.")
