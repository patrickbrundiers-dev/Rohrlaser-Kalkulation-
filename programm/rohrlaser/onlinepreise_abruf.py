"""Abruf der Online-Preise (manuell und automatisch), mit Protokoll, Schutz vor doppelten Abrufen und Cache.
Entwicklungsauftrag Patrick 18.11.2026, Phase 5. Ohne Qt.

- Je Lieferant läuft höchstens ein Abruf gleichzeitig (Sperre im Prozess); gleichzeitige Abrufe verschiedener
  Lieferanten sind erlaubt. Über mehrere Plätze schützt die Prüfsumme gelesener Preislisten (geteilte Einstellung
  online_dateien) und der Mindestabstand je Lieferant (onlinepreise.faellig).
- OCI-Hintergrundsuchen merkt sich das Programm eine Stunde je Suchtext (CACHE_S): dieselbe Suche geht in der Zeit
  nicht noch einmal an den Lieferanten.
- Ist ein Lieferant nicht erreichbar oder eine Datei kaputt, bleibt jeder zuletzt erfolgreich abgerufene Preis
  unverändert; das Protokoll sagt, was passiert ist.
- „Nur verwendete Materialien“: nur Preise zu Profil + Werkstoff, die in Angeboten der letzten 6 Monate vorkommen
  (und beim Öffnen eines Angebots dessen Abmessungen)."""
import threading
import time
from pathlib import Path

from . import onlinepreise as op
from . import onlinepreise_adapter as ad

CACHE_S = 3600
MAX_SUCHEN = 30           # OCI-Hintergrundsuchen je Abruf (gegen unnötige Anfragen)
_SPERREN = {}
_SPERREN_LOCK = threading.Lock()
_CACHE = {}               # (Lieferant, Suchtext) -> (Zeit, (eintraege, meldungen))


def _sperre(name):
    with _SPERREN_LOCK:
        return _SPERREN.setdefault(name, threading.Lock())


def laeuft(name):
    return _sperre(name).locked()


def cache_leeren():
    _CACHE.clear()


def holen_oci(lief, zugang, suchtexte, oeffnen=None, jetzt=None):
    """OCI-Hintergrundsuche je Suchtext (ohne Datenbank, darf in einem Hilfsfaden laufen). Ergebnis [(eintraege,
    quelle)], meldungen. Bricht nicht ab, wenn eine Suche scheitert."""
    jetzt = jetzt or time.time()
    out, meldungen = [], []
    if not zugang:
        return out, ["Kein OCI-Zugang hinterlegt."]
    for text in list(dict.fromkeys(suchtexte))[:MAX_SUCHEN]:
        schl = (lief["name"], text)
        c = _CACHE.get(schl)
        if c and jetzt - c[0] < CACHE_S:
            eintraege, m = c[1]
        else:
            try:
                eintraege, m = ad.oci_hintergrund(lief["oci_adresse"], zugang[0], zugang[1], text, oeffnen)
            except Exception as f:            # Netz, Zertifikat, Antwort: Preise bleiben wie sie sind
                meldungen.append(f"Suche „{text}“: {f}")
                continue
            _CACHE[schl] = (jetzt, (eintraege, m))
        meldungen += m
        out.append((eintraege, f"OCI-Hintergrundsuche „{text}“"))
    return out, meldungen


def speichern(db, lief, pakete, k, anlass, nur=None, benutzer=None, weg=None, t0=None, meldungen=()):
    """Geholte Preisstände [(eintraege, quelle)] eintragen und protokollieren. nur = {(profil, werkstoff)} oder None.
    Ergebnis dict(ergebnis, anzahl, neu, geaendert, gleich, uebersprungen, meldungen)."""
    t0 = t0 or time.time()
    erg = dict(ergebnis="ok", anzahl=0, neu=0, geaendert=0, gleich=0, uebersprungen=0, meldungen=list(meldungen))
    best = op.bestaetigungen(db)
    for eintraege, quelle in pakete:
        for e in eintraege:
            if nur is not None:
                zu = op.zuordnen(e, k, best.get((lief["name"], op.kennung(e))))
                if (zu["profil_id"], zu["werkstoff_id"]) not in nur:
                    erg["uebersprungen"] += 1
                    continue
            try:
                art, _ = op.eintragen(db, lief["name"], e, quelle, k, benutzer=benutzer,
                                      bestaetigt=best.get((lief["name"], op.kennung(e))))
            except ValueError as f:
                erg["meldungen"].append(f"{e.get('artikelnr') or e.get('bezeichnung') or '?'}: {f}")
                continue
            erg["anzahl"] += 1
            erg[{"neu": "neu", "geändert": "geaendert"}.get(art, "gleich")] += 1
    if not pakete and erg["meldungen"]:
        erg["ergebnis"] = "fehler"
    op.protokollieren(db, lief["name"], weg or lief.get("weg"), anlass, erg["ergebnis"], erg["anzahl"], erg["neu"],
                      erg["geaendert"], "; ".join(erg["meldungen"][:20]), time.time() - t0)
    return erg


def preislisten(db, lief, k, anlass="manuell", dateien=None, nochmal=False, benutzer=None, nur=None):
    """Preislisten lesen: dateien (Pfade) oder alle im Preislisten-Ordner. Schon gelesene Dateien (gleiche
    Prüfsumme, auch an einem anderen Platz) überspringt das Programm, außer nochmal=True."""
    name = lief["name"]
    sp = _sperre(name)
    if not sp.acquire(blocking=False):
        return dict(ergebnis="läuft", anzahl=0, neu=0, geaendert=0, gleich=0, uebersprungen=0,
                    meldungen=["Abruf läuft schon."])
    t0 = time.time()
    try:
        if dateien is None:
            dateien = ad.preislisten_im_ordner(lief.get("preisliste_ordner"))
            if not dateien and not Path(str(lief.get("preisliste_ordner") or "")).is_dir():
                op.protokollieren(db, name, "Preisliste", anlass, "fehler", meldung="Preislisten-Ordner nicht "
                                  "erreichbar; letzte Preise bleiben")
                return dict(ergebnis="fehler", anzahl=0, neu=0, geaendert=0, gleich=0, uebersprungen=0,
                            meldungen=["Preislisten-Ordner nicht erreichbar; die letzten Preise bleiben."])
        pakete, meldungen, gemerkt = [], [], []
        for pfad in dateien:
            pfad = Path(pfad)
            try:
                roh = pfad.read_bytes()
            except OSError as f:
                meldungen.append(f"{pfad.name}: {f}")
                continue
            kenn = op.datei_kennung(roh)
            if op.datei_bekannt(db, kenn) and not nochmal:
                continue
            eintraege, m = ad.preisliste_lesen(roh, pfad.name, lief)
            meldungen += m[:50]
            if eintraege:
                pakete.append((eintraege, f"Preisliste {pfad.name}"))
            gemerkt.append((kenn, pfad.name))
        if not pakete and not meldungen:
            op.protokollieren(db, name, "Preisliste", anlass, "ok", meldung="keine neue Preisliste",
                              dauer=time.time() - t0)
            return dict(ergebnis="ok", anzahl=0, neu=0, geaendert=0, gleich=0, uebersprungen=0,
                        meldungen=["Keine neue Preisliste."])
        if nur is None and op.ja(lief.get("nur_verwendete")):
            nur = op.verwendete(db)
        erg = speichern(db, lief, pakete, k, anlass, nur, benutzer, "Preisliste", t0, meldungen)
        for kenn, n in gemerkt:
            op.datei_merken(db, kenn, n)
        return erg
    finally:
        sp.release()


def oci_speichern(db, lief, k, geholt, anlass, benutzer=None, nur=None, t0=None):
    """Ergebnis von holen_oci bzw. einem OCI-Warenkorb eintragen (unter der Sperre des Lieferanten)."""
    pakete, meldungen = geholt
    sp = _sperre(lief["name"])
    with sp:
        return speichern(db, lief, pakete, k, anlass, nur, benutzer, "OCI-Punchout", t0, meldungen)


def suchtexte(db, k, nur):
    """Suchtexte der OCI-Hintergrundsuche für die Paare (profil, werkstoff)."""
    out = []
    for p, w in sorted(nur or ()):
        pr, ws = k.profile.get(p), k.werkstoffe.get(w)
        if pr:
            out.append(ad.suchtext(pr.get("form"), pr.get("a"), pr.get("b"), pr.get("wand"),
                                   (ws or {}).get("werkstoff"), p))
    return out


def faellige(db, anlass):
    return [z for z in op.lieferanten(db, nur_aktiv=True) if op.faellig(db, z, anlass)]
