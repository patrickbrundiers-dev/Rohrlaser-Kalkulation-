"""Rückfrage an den Kunden (Vorschlag H5a, 02.11.2026): die offenen Punkte des Angebots (Angebots-Check: Fehler und
Warnungen, Hinweise der Positionen) als Mail-Entwurf an den Kunden, als Antwort auf die Anfrage-Mail, wenn sie im
Angebotsordner liegt. Danach „Rückfrage gestellt“ im Versandverlauf und eine Wiedervorlage in WIEDERVORLAGE_TAGE
Tagen. Ohne Qt."""
import datetime

WIEDERVORLAGE_TAGE = 3


def punkte(check, positionen=(), zeilen=()):
    """Texte der offenen Punkte: Check-Punkte FEHLER/WARNUNG und die Hinweise je Position (ohne Doppelte)."""
    out = []
    for p in check or ():
        art = getattr(p, "art", None) or (p[0] if isinstance(p, (tuple, list)) else None)
        text = getattr(p, "text", None) or (p[1] if isinstance(p, (tuple, list)) else str(p))
        if art in ("FEHLER", "WARNUNG") and text and text not in out:
            out.append(text)
    for p, z in zip(positionen, zeilen):
        h = (z or {}).get("hinweis")
        if h:
            t = f"Pos. {p.get('pos')}{' ' + p['artikel'] if p.get('artikel') else ''}: {h}"
            if t not in out:
                out.append(t)
    for t in step_fragen(positionen):
        if t not in out:
            out.append(t)
    return out


def step_fragen(positionen):
    """GEO-018 (Roadmap Kalkulation Phase 1): unklare STEP-Merkmale als Frage an den Kunden – je Position die nicht
    bestätigten Merkmale (Status prüfen/nicht erkannt) bzw. die Gründe, warum der Import gelb war."""
    from . import step_pruefung
    from .angebot import aktiv
    out = []
    for p in positionen or ():
        if not aktiv(p):
            continue
        teile = []
        for m in step_pruefung.offen(p):
            w = f" {m['wert']}" if str(m.get("wert") or "").strip() else ""
            g = f" ({m['grund']})" if str(m.get("grund") or "").strip() else ""
            teile.append(f"{m.get('merkmal')}{w}{g}")
        if not teile:
            teile = [g for g in step_pruefung.gelb_ungeprueft(p) if g != "gelb"]
        if not teile and step_pruefung.vereinfacht(p):
            teile = ["Maße aus dem 3D-Modell nur vereinfacht ermittelt"]
        if teile:
            kopf = f"Pos. {p.get('pos')}{' ' + p['artikel'] if p.get('artikel') else ''}"
            out.append(f"{kopf}: bitte bestätigen – " + "; ".join(dict.fromkeys(teile)))
    return out


def betreff(kopf):
    ref = kopf.get("kundenreferenz")
    return f"Rückfrage zu Ihrer Anfrage{' ' + ref if ref else ''} (Angebot {kopf.get('nummer') or ''})".strip()


def text(kopf, kunde, liste, absender=""):
    anrede = (kunde or {}).get("ansprechpartner")
    zeilen = [f"Guten Tag{' ' + anrede if anrede else ''},", "",
              "für Ihr Angebot benötigen wir noch ein paar Angaben:", ""]
    zeilen += [f"{i}. {t}" for i, t in enumerate(liste, 1)]
    zeilen += ["", "Vielen Dank für Ihre kurze Rückmeldung.", "", "Mit freundlichen Grüßen"]
    if absender:
        zeilen.append(absender)
    return "\n".join(zeilen)


def eintrag(an, anzahl, heute=None):
    heute = heute or datetime.date.today()
    return dict(art="rueckfrage", datum=heute.isoformat(), an=an or "", punkte=anzahl)


def wiedervorlage(heute=None):
    return (heute or datetime.date.today()) + datetime.timedelta(days=WIEDERVORLAGE_TAGE)
