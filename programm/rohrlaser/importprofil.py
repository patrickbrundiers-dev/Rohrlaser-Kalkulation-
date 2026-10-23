"""STEP-Import je Kunde: Artikelnummer aus Bauteilnamen, Normteile, Vorgaben des Prüfdialogs (Importprofile).

Die Messung liefert je Körper den Bauteilnamen aus der Konstruktion (Spalte bauteil, ab STEP-JSON 1.13). benennen()
setzt daraus Artikel und Bezeichnung, normteile() markiert Normteile (_normteil: im Prüfdialog abgewählt). Ein
Importprofil (Tabelle importprofile, je Kunde) ändert Benennung, Muster, Normteil-Begriffe und die Vorgaben
Werkstoff, flache Teile und Anbauteile; leere Felder = Einstellungen.
"""
import re

from .stammdaten import BENENNUNGEN


def fuer_kunde(db, kundennr):
    """Importprofil des Kunden oder None."""
    if not kundennr:
        return None
    return next((z for z in db.zeilen("importprofile") if str(z.get("kundennr")) == str(kundennr)), None)


def begriffe(text):
    return [b.strip() for b in re.split(r"[;\n]", text or "") if b.strip()]


def normteil(name, liste):
    """Erster Begriff aus liste, der als eigenes Wort im Namen steht (Groß-/Kleinschreibung egal), sonst None."""
    for b in liste:
        if re.search(r"(?<![0-9A-Za-zÄÖÜäöüß])" + re.escape(b) + r"(?![A-Za-zÄÖÜäöüß])", name or "", re.IGNORECASE):
            return b
    return None


def artikel_aus(m, benennung, muster=""):
    """(Artikel, Bezeichnung oder None) eines Körpers nach der Benennung; ohne Bauteilnamen der bisherige Artikel."""
    name = (m.get("bauteil") or "").strip()
    bisher = m.get("artikel") or ""
    if not name or benennung == BENENNUNGEN[1]:
        return bisher, None
    nummer, bezeichnung = name, None
    if muster:
        try:
            treffer = re.search(muster, name)
        except re.error:
            treffer = None
        if treffer:
            nummer = (treffer.group(1) if treffer.groups() and treffer.group(1) else treffer.group(0)).strip()
            bezeichnung = name if nummer != name else None
    if benennung == BENENNUNGEN[2]:
        from pathlib import Path
        nummer = f"{Path(str(m.get('datei') or '')).stem}-{nummer}"
    return nummer or bisher, bezeichnung


def anwenden(messwerte, profil=None, einstellungen=None):
    """Benennung und Normteile auf die Messwerte anwenden (vor dem Prüfdialog). einstellungen: {step_benennung,
    step_normteile}. Ergebnis: Anzahl erkannter Normteile."""
    e = einstellungen or {}
    p = profil or {}
    benennung = p.get("benennung") or e.get("step_benennung") or BENENNUNGEN[0]
    liste = begriffe(e.get("step_normteile")) + begriffe(p.get("normteile"))
    n = 0
    for m in messwerte:
        if m.get("fehler"):
            continue
        if "_artikel_gemessen" not in m:
            m["_artikel_gemessen"] = m.get("artikel") or ""
        m["artikel"] = m["_artikel_gemessen"]
        artikel, bezeichnung = artikel_aus(m, benennung, p.get("muster") or "")
        m["artikel"] = artikel
        m.pop("_bezeichnung", None)
        if bezeichnung:
            m["_bezeichnung"] = bezeichnung
        b = normteil(m.get("bauteil"), liste)
        if b:
            m["_normteil"] = b
            n += 1
        else:
            m.pop("_normteil", None)
    return n


def vorgaben(profil):
    """Vorgaben des Profils für den Import: dict mit werkstoff, flach_als, anbau_weglassen (nur gesetzte)."""
    p = profil or {}
    out = {}
    if p.get("werkstoff_id"):
        out["werkstoff"] = p["werkstoff_id"]
    if p.get("flach_als"):
        out["flach_als"] = p["flach_als"]
    if p.get("anbau_weglassen") in ("ja", "nein"):
        out["anbau_weglassen"] = p["anbau_weglassen"] == "ja"
    return out
