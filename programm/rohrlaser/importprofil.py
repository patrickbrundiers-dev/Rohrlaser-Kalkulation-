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


def korrekturen(messwerte, start, werkstoff_vorgabe, anbau_start=None, anbau_jetzt=None):
    """Was im Prüfdialog korrigiert wurde und sich als Importprofil des Kunden merken lässt (Plan Bedienung B8).
    start: _uebernehmen je Messwert beim Öffnen. Ergebnis: dict mit werkstoff_id (alle gewählten Rohre/Profile haben
    denselben anderen Werkstoff als die Vorgabe), normteile (Bauteilnamen, die beim Öffnen gewählt waren und
    abgewählt wurden) und anbau_weglassen ('ja'/'nein', wenn umgeschaltet); leer = nichts zu merken."""
    out = {}
    gewaehlt = [m for m in messwerte if m.get("_uebernehmen") and not m.get("fehler") and not m.get("_blech_artikel")
                and m.get("profilform")]
    ws = {m.get("_werkstoff") for m in gewaehlt}
    if len(ws) == 1:
        w = next(iter(ws))
        if w and w != werkstoff_vorgabe:
            out["werkstoff_id"] = w
    namen = []
    for m, vorher in zip(messwerte, start):
        name = (m.get("bauteil") or "").strip()
        if vorher and not m.get("_uebernehmen") and name and name not in namen and m.get("_knick_von") is None:
            namen.append(name)
    if namen:
        out["normteile"] = namen
    if anbau_start is not None and anbau_jetzt is not None and bool(anbau_start) != bool(anbau_jetzt):
        out["anbau_weglassen"] = "ja" if anbau_jetzt else "nein"
    return out


def korrekturen_text(k):
    teile = []
    if k.get("werkstoff_id"):
        teile.append(f"Werkstoff {k['werkstoff_id']}")
    if k.get("normteile"):
        teile.append("Normteile " + ", ".join(k["normteile"][:4]) + (" …" if len(k["normteile"]) > 4 else ""))
    if k.get("anbau_weglassen"):
        teile.append("Anbauteile " + ("weglassen" if k["anbau_weglassen"] == "ja" else "übernehmen"))
    return "; ".join(teile)


def merken(db, kundennr, k):
    """Korrekturen ins Importprofil des Kunden schreiben (anlegen, falls es fehlt); Normteile kommen zu den
    vorhandenen Begriffen dazu. Ergebnis: Text für den Bericht oder None."""
    if not kundennr or not k:
        return None
    profil = fuer_kunde(db, kundennr)
    if profil is None:
        db.neu("importprofile", dict(kundennr=kundennr, bemerkung="aus dem STEP-Prüfdialog gelernt"))
        profil = fuer_kunde(db, kundennr)
    if k.get("werkstoff_id"):
        db.aendern("importprofile", profil["id"], "werkstoff_id", k["werkstoff_id"])
    if k.get("normteile"):
        alt = begriffe(profil.get("normteile"))
        neu = alt + [n for n in k["normteile"] if n.lower() not in {a.lower() for a in alt}]
        db.aendern("importprofile", profil["id"], "normteile", "; ".join(neu))
    if k.get("anbau_weglassen"):
        db.aendern("importprofile", profil["id"], "anbau_weglassen", k["anbau_weglassen"])
    return f"Importprofil des Kunden {kundennr} ergänzt: {korrekturen_text(k)}"
