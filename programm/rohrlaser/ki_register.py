"""KI 4: Modell-Register – jede Version eines Sprachmodells mit Herkunft, Prüfsumme, Lizenz, Trainingsdaten, Prüfergebnis
und Status (Master-Prompt Patrick 21.11.2026 „Eigenes lokales KI-Modell“, Punkte 4, 11, 12; Plan
https://claude.ai/artifact/88Dk7571GLveJM3Kq3MofA).

Status: test (neu, noch nicht produktiv) → produktiv (für eine oder mehrere Rollen aktiv) → archiv (abgelöst, kann
zurückgeholt werden). Keine KI ändert sich selbst: produktiv wird eine Version nur über aktivieren(), und das nur mit
bestandenem fachlichem Prüfsatz (ki_pruefsatz), der mindestens so gut ist wie die bisherige Version der Rolle; sonst
nur mit ausdrücklicher Bestätigung. zuruecksetzen() holt die zuletzt abgelöste Version einer Rolle zurück.

Gespeichert als Einstellung REGISTER (geht mit den Admin-Vorgaben, Bereich „KI-Plattform“, auf alle PCs). Ohne Qt,
ohne Internet."""
import hashlib
from pathlib import Path

from . import protokoll
from .zahlen import jetzt_text as _jetzt  # Audit 26.11.2026 R-01: gemeinsame Hilfsfunktion

REGISTER = "ki_modell_register"
TRAININGSDATEN = "ki_trainingsdaten"        # Liste der Exporte (ki_training)
TEST, PRODUKTIV, ARCHIV = "test", "produktiv", "archiv"
STATUS_TITEL = {TEST: "Test", PRODUKTIV: "Produktiv", ARCHIV: "Archiv"}
MINDEST_QUOTE = 0.7                         # Prüfsatz: so viel muss ein Modell mindestens schaffen
VERLAUF_MAX = 200

# Lizenz nach Modellfamilie (Name); unbekannt = vor dem Einsatz prüfen
LIZENZEN = (("qwen", "Apache-2.0 (kommerziell frei)"), ("mistral", "Apache-2.0 (kommerziell frei)"),
            ("nomic", "Apache-2.0 (kommerziell frei)"), ("phi", "MIT (kommerziell frei)"),
            ("granite", "Apache-2.0 (kommerziell frei)"), ("bge", "MIT (kommerziell frei)"),
            ("llama", "Llama Community License (Auflagen beachten)"), ("gemma", "Gemma Terms of Use (Auflagen beachten)"),
            ("deepseek", "MIT bzw. DeepSeek License (prüfen)"))
UNBEKANNT = "unbekannt – vor dem Einsatz prüfen"


class BestaetigungNoetig(ValueError):
    """Aktivieren ohne (bestandenen, gleich guten) Prüfsatz: nur mit erzwingen=True."""


def lizenz(name):
    n = str(name or "").casefold()
    for wort, text in LIZENZEN:
        if wort in n:
            return text
    return UNBEKANNT


def _lesen(db):
    try:
        w = db.einstellung(REGISTER)
    except Exception:           # noqa: BLE001 – ohne Datenbank: leer
        protokoll.warnung("ki_register: Register nicht lesbar")
        return dict(eintraege=[], verlauf=[])
    if not isinstance(w, dict):
        return dict(eintraege=[], verlauf=[])
    return dict(eintraege=list(w.get("eintraege") or []), verlauf=list(w.get("verlauf") or []))


def _schreiben(db, r):
    r["verlauf"] = r["verlauf"][-VERLAUF_MAX:]
    db.einstellung_setzen(REGISTER, r)


def _protokoll(db, aktion, text, modell=""):
    try:
        from . import ki_protokoll
        ki_protokoll.schreiben(db, "Modell-Register", aktion, ergebnis=text, modell=modell)
    except Exception:           # noqa: BLE001 – Protokoll darf nie stören
        protokoll.warnung("ki_register: Protokoll nicht geschrieben")


def liste(db):
    """Alle Versionen, neueste zuerst."""
    return sorted(_lesen(db)["eintraege"], key=lambda e: e.get("angelegt") or "", reverse=True)


def verlauf(db):
    return list(reversed(_lesen(db)["verlauf"]))


def finden(db, eid):
    return next((e for e in _lesen(db)["eintraege"] if e.get("id") == eid), None)


def _basisname(name):
    return str(name or "").split(":")[0]


def eintragen(db, name, herkunft="", sha256="", basis="", datensatz="", groesse_gb=None, notiz="", kuerzel=""):
    """Neue Version (Status test) oder die vorhandene mit gleichem Namen und gleicher Prüfsumme."""
    r = _lesen(db)
    n = _basisname(name)
    for e in r["eintraege"]:
        if e["name"] == n and (e.get("sha256") or "") == (sha256 or ""):
            return e
    nr = 1 + sum(1 for e in r["eintraege"] if e["name"] == n)
    for alt in r["eintraege"]:      # gleicher Name, andere Datei: Ollama hat die alte überschrieben (nicht zurückholbar)
        if alt["name"] == n and sha256 and alt.get("sha256") and alt.get("sha256") != sha256:
            alt["ueberschrieben"] = True
    e = dict(id=f"{n}#{nr}", name=n, version=nr, herkunft=str(herkunft or ""), sha256=sha256 or "",
             basis=basis or n, lizenz=lizenz(basis or n), datensatz=datensatz or "", groesse_gb=groesse_gb,
             status=TEST, rollen=[], war_rollen=[], pruefung=None, angelegt=_jetzt(), von=kuerzel, notiz=notiz)
    r["eintraege"].append(e)
    r["verlauf"].append(dict(zeit=e["angelegt"], wer=kuerzel, was=f"{e['id']} eingetragen ({herkunft or 'Ollama'})"))
    _schreiben(db, r)
    _protokoll(db, "eintragen", f"{e['id']} eingetragen", n)
    return e


def vorhandene_eintragen(db, modelle, kuerzel=""):
    """Alle Modelle eines Servers ins Register, die dort noch fehlen (Status test); Anzahl neu."""
    da = {e["name"] for e in _lesen(db)["eintraege"]}
    neu = 0
    for m in modelle or ():
        n = _basisname(m.get("name"))
        if n and n not in da:
            eintragen(db, n, herkunft=f"{m.get('server') or 'Ollama'}", groesse_gb=m.get("groesse_gb"), kuerzel=kuerzel)
            da.add(n)
            neu += 1
    return neu


def angaben_setzen(db, eid, basis=None, datensatz=None, notiz=None, kuerzel=""):
    """Basismodell (bestimmt die Lizenz), Trainingsdaten-Version und Notiz einer Version nachtragen (eigene Modelle)."""
    r = _lesen(db)
    for e in r["eintraege"]:
        if e["id"] == eid:
            if basis is not None:
                e["basis"] = str(basis).strip() or e["name"]
                e["lizenz"] = lizenz(e["basis"])
            if datensatz is not None:
                e["datensatz"] = str(datensatz).strip()
            if notiz is not None:
                e["notiz"] = str(notiz)
            r["verlauf"].append(dict(zeit=_jetzt(), wer=kuerzel, was=f"{eid}: Basis {e['basis']}, Datensatz "
                                     f"{e.get('datensatz') or '–'}"))
            _schreiben(db, r)
            return e
    return None


def pruefung_speichern(db, eid, ergebnis):
    """Ergebnis des fachlichen Prüfsatzes an die Version hängen (ohne die Einzelantworten)."""
    r = _lesen(db)
    for e in r["eintraege"]:
        if e["id"] == eid:
            e["pruefung"] = {k: ergebnis.get(k) for k in ("punkte", "max", "quote", "je_art", "dauer_s", "zeit",
                                                         "pruefsatz", "fehler")}
            e["pruefung"]["zeit"] = e["pruefung"].get("zeit") or _jetzt()
            r["verlauf"].append(dict(zeit=_jetzt(), wer="", was=f"{eid} geprüft: {ergebnis.get('punkte')}/"
                                     f"{ergebnis.get('max')} Punkte"))
            _schreiben(db, r)
            return e
    return None


def produktiv(db, rolle):
    """Die produktive Version einer Rolle oder None."""
    return next((e for e in _lesen(db)["eintraege"] if e.get("status") == PRODUKTIV and rolle in (e.get("rollen") or ())),
                None)


def freigabe_pruefen(db, eid, rollen):
    """(ok, Grund): darf diese Version für die Rollen produktiv werden?"""
    e = finden(db, eid)
    if e is None:
        return False, "Version nicht gefunden."
    p = e.get("pruefung") or {}
    if not p:
        return False, "Noch nicht mit dem fachlichen Prüfsatz geprüft."
    q = p.get("quote") or 0
    if q < MINDEST_QUOTE:
        return False, f"Prüfsatz {q:.0%} – mindestens {MINDEST_QUOTE:.0%} nötig."
    for rolle in rollen:
        alt = produktiv(db, rolle)
        if alt and alt["id"] != eid:
            qa = (alt.get("pruefung") or {}).get("quote") or 0
            if q < qa:
                return False, f"Prüfsatz {q:.0%} schlechter als die produktive Version {alt['id']} ({qa:.0%})."
    if e.get("lizenz") == UNBEKANNT:
        return False, "Lizenz unbekannt – bitte vor dem Einsatz prüfen."
    return True, f"Prüfsatz {q:.0%} bestanden."


def _rollen_text(rollen):
    from .ki_modelle import ROLLEN
    t = {r: tt for r, tt, _ in ROLLEN}
    return ", ".join(f"„{t.get(r, r)}“" for r in rollen)


def aktivieren(db, eid, rollen, kuerzel="", erzwingen=False, begruendung=""):
    """Version für Rollen produktiv setzen (setzt die Rollen in ki_modelle); die bisherigen Versionen dieser Rollen
    gehen ins Archiv und lassen sich mit zuruecksetzen zurückholen. Ohne bestandene Prüfung: BestaetigungNoetig."""
    from . import ki_modelle
    rollen = [r for r in rollen if r]
    if not rollen:
        raise ValueError("Keine Rolle gewählt.")
    ok, grund = freigabe_pruefen(db, eid, rollen)
    if not ok and not erzwingen:
        raise BestaetigungNoetig(grund)
    r = _lesen(db)
    e = next(x for x in r["eintraege"] if x["id"] == eid)
    for x in r["eintraege"]:
        if x is e:
            continue
        weg = [ro for ro in x.get("rollen") or () if ro in rollen]
        if weg:
            x["rollen"] = [ro for ro in x["rollen"] if ro not in rollen]
            x["war_rollen"] = sorted(set(x.get("war_rollen") or ()) | set(weg))
            x["abgeloest"] = dict(zeit=_jetzt(), von=eid)
            if not x["rollen"]:
                x["status"] = ARCHIV
    e["rollen"] = sorted(set(e.get("rollen") or ()) | set(rollen))
    e["status"] = PRODUKTIV
    e["aktiviert"] = dict(zeit=_jetzt(), wer=kuerzel, erzwungen=bool(not ok), grund=grund, begruendung=begruendung)
    r["verlauf"].append(dict(zeit=_jetzt(), wer=kuerzel, was=f"{eid} produktiv für {_rollen_text(rollen)}"
                             + (f" (ohne bestandene Prüfung: {grund}; Begründung: {begruendung})" if not ok else "")))
    _schreiben(db, r)
    for rolle in rollen:
        ki_modelle.rolle_setzen(db, rolle, e["name"])
    _protokoll(db, "aktivieren", f"{eid} produktiv für {_rollen_text(rollen)}", e["name"])
    return e


def zuruecksetzen(db, rolle, kuerzel=""):
    """Die zuletzt für diese Rolle abgelöste Version wieder produktiv setzen (ohne neue Prüfung: sie war es schon).
    Ohne frühere Version: Rolle wieder automatisch (Modellwahl nach Größe). Ergebnis: Version oder None."""
    from . import ki_modelle
    r = _lesen(db)
    aktuell = next((x for x in r["eintraege"] if x.get("status") == PRODUKTIV and rolle in (x.get("rollen") or ())),
                   None)
    frueher = sorted((x for x in r["eintraege"] if rolle in (x.get("war_rollen") or ()) and x is not aktuell
                      and x.get("abgeloest") and not x.get("ueberschrieben")), key=lambda x: x["abgeloest"]["zeit"], reverse=True)
    if aktuell:
        aktuell["rollen"] = [ro for ro in aktuell["rollen"] if ro != rolle]
        aktuell["war_rollen"] = sorted(set(aktuell.get("war_rollen") or ()) | {rolle})
        aktuell["abgeloest"] = dict(zeit=_jetzt(), von=frueher[0]["id"] if frueher else "automatisch")
        if not aktuell["rollen"]:
            aktuell["status"] = ARCHIV
    ziel = frueher[0] if frueher else None
    if ziel:
        ziel["rollen"] = sorted(set(ziel.get("rollen") or ()) | {rolle})
        ziel["status"] = PRODUKTIV
        ziel["aktiviert"] = dict(zeit=_jetzt(), wer=kuerzel, erzwungen=False, grund="zurückgesetzt")
    r["verlauf"].append(dict(zeit=_jetzt(), wer=kuerzel, was=f"Rolle {_rollen_text([rolle])} zurückgesetzt auf "
                             + (ziel["id"] if ziel else "automatische Wahl")))
    _schreiben(db, r)
    ki_modelle.rolle_setzen(db, rolle, ziel["name"] if ziel else None)
    _protokoll(db, "zuruecksetzen", f"{rolle}: {ziel['id'] if ziel else 'automatisch'}", ziel["name"] if ziel else "")
    return ziel


def sha256_datei(pfad, fortschritt=None, abbrechen=None, block=8 * 1024 * 1024):
    """Prüfsumme einer (großen) Modell-Datei; fortschritt(fertig, gesamt)."""
    p = Path(pfad)
    gesamt, fertig = p.stat().st_size, 0
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            if abbrechen and abbrechen():
                return ""
            b = f.read(block)
            if not b:
                break
            h.update(b)
            fertig += len(b)
            if fortschritt:
                fortschritt(fertig, gesamt)
    return h.hexdigest()
