"""Preiswächter für offene Angebote (Automationen 03.11.2026, Vorschlag 9a).

Ändern sich Materialpreise, Tonnenpreise, Schneiddaten, Maschinen oder Stundensätze (Lieferantenangebot übernommen,
Preisimport, von Hand), läuft die Sammel-Preisprüfung (sammel_preis.pruefen) einmal von selbst. Die Startseite
meldet dann z. B. „3 offene Angebote liegen mehr als 3 % unter dem aktuellen Preis“ mit Verweis auf Datei → Offene
Angebote prüfen …; Angebote ändern sich nie von allein. Ob sich etwas geändert hat, zeigt ein Fingerabdruck der
betroffenen Stammdaten (Einstellung 'preiswaechter_stand', nur dieser Arbeitsplatz); das Ergebnis steht in
'preiswaechter_ergebnis'. Ohne Qt."""
import datetime
import hashlib
import json

TABELLEN = ("preise", "werkstoffe", "oberflaechen", "lieferlaengen", "maschinen", "schneiddaten", "stundensaetze")
STAND, ERGEBNIS = "preiswaechter_stand", "preiswaechter_ergebnis"


def fingerabdruck(db):
    h = hashlib.sha256()
    for t in TABELLEN:
        try:
            for r in db.con.execute(f'SELECT * FROM "{t}" ORDER BY id'):
                h.update(json.dumps(list(r), default=str, ensure_ascii=False).encode("utf-8"))
        except Exception:
            continue
    return h.hexdigest()[:24]


def noetig(db):
    """True, wenn sich die Preis-Stammdaten seit der letzten Prüfung geändert haben (beim allerersten Mal nur merken,
    damit nicht jeder Start eine Prüfung auslöst)."""
    alt = db.einstellung(STAND)
    neu = fingerabdruck(db)
    if not alt:
        _setzen(db, STAND, neu)
        return False
    return alt != neu


def _setzen(db, name, wert):
    if getattr(db, "nur_lesen", None):
        return
    try:
        db.einstellung_setzen(name, wert)
    except Exception:
        pass


def pruefen(db, heute=None):
    """Sammel-Preisprüfung ausführen und Ergebnis merken. Ergebnis: dict(am, schwelle, angebote=[{id, nummer,
    prozent}])."""
    from . import automatik, sammel_preis
    schwelle = db.einstellung("preiswaechter_schwelle")
    schwelle = 0.03 if schwelle in (None, "") else float(schwelle)
    liste = sammel_preis.pruefen(db, heute)
    treffer = [dict(id=r["id"], nummer=r["nummer"], prozent=r["prozent"]) for r in liste
               if r["prozent"] is not None and r["prozent"] > schwelle]
    erg = dict(am=datetime.datetime.now().isoformat(timespec="seconds"), schwelle=schwelle, angebote=treffer)
    _setzen(db, ERGEBNIS, erg)
    _setzen(db, STAND, fingerabdruck(db))
    if treffer:
        automatik.merken(db, "preiswaechter", text_aus(erg))
    return erg


def text_aus(erg):
    if not erg or not erg.get("angebote"):
        return ""
    n = len(erg["angebote"])
    return (f"{n} offene{'s' if n == 1 else ''} Angebot{'e' if n != 1 else ''} lieg{'t' if n == 1 else 'en'} mehr als "
            f"{round(100 * erg['schwelle'])} % unter dem aktuellen Preis ("
            + ", ".join(a["nummer"] or "?" for a in erg["angebote"][:4]) + (" …" if n > 4 else "")
            + ") – Datei → Offene Angebote prüfen …")


def text(db):
    """Hinweis für die Startseite oder ''. Ein Ergebnis gilt nur für Angebote, die noch verschickt sind."""
    erg = db.einstellung(ERGEBNIS)
    if not isinstance(erg, dict) or not erg.get("angebote"):
        return ""
    offen = {a["id"] for a in db.angebote() if a.get("vorgang") == "Verschickt"}
    erg = dict(erg, angebote=[a for a in erg["angebote"] if a["id"] in offen])
    return text_aus(erg)
