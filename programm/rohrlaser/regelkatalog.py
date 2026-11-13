"""Regelkatalog aller Prüfungen des Angebots-Checks (QA-006, Patrick 12.11.2026 „Alle Empfehlungen“ zum Bericht
Entwicklungspotenziale).

Eine Liste der Regeln mit ID, Stufe, Grund und Ort (Datei der Prüfung). Erkannt wird ein Punkt des Checks an seinem
Text (muster, regulärer Ausdruck). WARNUNG und HINWEIS sind einstellbar (WARNUNG, HINWEIS oder aus), eine Regel mit
der Stufe FEHLER nie: sie bleibt FEHLER und lässt sich nicht abschalten. Die Einstellung steht unter
STUFEN_EINSTELLUNG als {ID: Stufe}. Punkte ohne Regel im Katalog bleiben, wie sie sind. Ohne Qt."""
import re
from dataclasses import dataclass

FEHLER, WARNUNG, HINWEIS, AUS = "FEHLER", "WARNUNG", "HINWEIS", "aus"
STUFEN_EINSTELLUNG = "regel_stufen"
WAEHLBAR = (WARNUNG, HINWEIS, AUS)


@dataclass(frozen=True)
class Regel:
    id: str
    stufe: str
    titel: str
    grund: str
    ort: str
    muster: str
    beispiel: str           # Text eines Punkts, den die Regel erkennt (Test)


REGELN = (
    Regel("CHK-001", FEHLER, "Keine Positionen", "ohne Positionen gibt es kein Angebot", "angebot_check.py",
          r"^keine Positionen$", "keine Positionen"),
    Regel("CHK-002", WARNUNG, "Kein Kunde", "Angebot ohne Empfänger", "angebot_check.py",
          r"^kein Kunde eingetragen", "kein Kunde eingetragen"),
    Regel("CHK-003", WARNUNG, "Schnittplan nicht aktuell", "Preis passt nicht zum Schnittplan", "angebot_check.py",
          r"^Schnittplan nicht aktuell", "Schnittplan nicht aktuell: wird vor dem Angebot neu optimiert"),
    Regel("CHK-004", HINWEIS, "STEP vereinfacht gemessen", "Zeitlimit beim Import, Maße können abweichen",
          "angebot_check.py", r"vereinfacht gemessen", "2 Teile vereinfacht gemessen (Zeitlimit): Art und Maße prüfen"),
    Regel("CHK-005", HINWEIS, "STEP-Import ungeprüft", "gelbe Werte aus dem Import nicht bestätigt",
          "angebot_check.py", r"aus dem STEP-Import ungeprüft", "1 Teil aus dem STEP-Import ungeprüft (gelb), z. B. Länge"),
    Regel("CHK-006", HINWEIS, "STEP-Merkmale prüfen", "erkannte Merkmale offen", "angebot_check.py",
          r"STEP-Merkmale zu prüfen", "Pos. 10: STEP-Merkmale zu prüfen (z. B. Gewinde)"),
    Regel("CHK-007", HINWEIS, "Dreh-/Frästeil-Richtpreis", "Einkaufspreis geschätzt", "angebot_check.py",
          r"EK der Dreh-/Frästeile ist ein Richtpreis", "Pos. 10: EK der Dreh-/Frästeile ist ein Richtpreis (Schätzung), "
          "Fremdangebot einholen"),
    Regel("CHK-008", WARNUNG, "Hinweis in der Kalkulation", "Position rechnet unvollständig", "angebot_check.py",
          r"mit Hinweis in der Kalkulation", "2 Positionen mit Hinweis in der Kalkulation, z. B. „keine Schneiddaten“"),
    Regel("CHK-009", WARNUNG, "Zukaufteil ohne Einkaufspreis", "Zukauf fehlt im Preis", "angebot_check.py",
          r"Zukaufteil ohne Einkaufspreis", "Pos. 10: Zukaufteil ohne Einkaufspreis"),
    Regel("CHK-010", WARNUNG, "Fracht nicht gerechnet", "Fracht fehlt im Preis", "angebot_check.py",
          r"^Fracht: ", "Fracht: PLZ fehlt"),
    Regel("CHK-011", WARNUNG, "Staffelpreis widerspricht", "Angebots-PDF zeigt zwei Preise", "angebot_check.py",
          r"^Staffelpreis widerspricht", "Staffelpreis widerspricht dem Angebotspreis (1 Zeile): Pos. 10"),
    Regel("CHK-012", WARNUNG, "Staffeln veraltet", "Staffel ohne Preis fehlt im Angebot", "angebot_check.py",
          r"Staffelstufe\(n\) veraltet", "2 Staffelstufe(n) veraltet oder nicht gerechnet: ohne Preis, nicht im Angebot"),
    Regel("CHK-013", HINWEIS, "Werkstoff am Rohrlaser", "Hinweis zum Schneiden des Werkstoffs", "rechnen.py",
          r"^Werkstoff \S+: ", "Werkstoff 1.4301: N₂ für oxidfreie Kante"),
    Regel("CHK-014", HINWEIS, "Mindestauftragswert", "Preis angehoben", "angebot_check.py",
          r"^Mindestauftragswert greift", "Mindestauftragswert greift: Preis wurde auf 150,00 € angehoben (+20,00 €)"),
    Regel("CHK-015", HINWEIS, "Stammdaten seit Festschreiben geändert", "Angebot rechnet mit alten Preisen",
          "angebot_check.py", r"^Stammdaten seit dem Festschreiben geändert",
          "Stammdaten seit dem Festschreiben geändert (2 Werte): „Aktuelle Preise übernehmen …“ rechnet mit den neuen"),
    Regel("CHK-016", HINWEIS, "Kunde ohne E-Mail", "Versand per Mail nicht möglich", "angebot_check.py",
          r"^Kunde ohne E-Mail-Adresse", "Kunde ohne E-Mail-Adresse"),
    Regel("CHK-017", HINWEIS, "Lieferzeit leer", "es gilt der Text der Bedingungen", "angebot_check.py",
          r"^Lieferzeit leer", "Lieferzeit leer (es gilt der Text der Bedingungen)"),
    Regel("CHK-018", HINWEIS, "Kundenreferenz leer", "Anfrage des Kunden nicht genannt", "angebot_check.py",
          r"^Kundenreferenz \(Anfrage des Kunden\) leer", "Kundenreferenz (Anfrage des Kunden) leer"),
    Regel("CHK-019", HINWEIS, "Gültigkeit abgelaufen", "verschicktes Angebot nicht mehr gültig", "angebot_check.py",
          r"^Gültigkeit abgelaufen", "Gültigkeit abgelaufen (01.11.2026)"),
    Regel("CHK-020", HINWEIS, "Unsicherer Anteil am Preis", "Werte ohne sichere Herkunft (CALC-028)", "herkunft.py",
          r"^Unsicherer Anteil am Preis", "Unsicherer Anteil am Preis: Sicher 90 %, …"),
    Regel("CHK-021", HINWEIS, "Normteil ohne Einkaufspreis", "Normteil fehlt im Preis", "angebot_fenster.py",
          r"Normteile? ohne Einkaufspreis", "2 Normteile ohne Einkaufspreis – im Zukauf ergänzen"),
)
REGEL = {r.id: r for r in REGELN}
assert len(REGEL) == len(REGELN), "Regel-ID doppelt"
_MUSTER = [(r, re.compile(r.muster)) for r in REGELN]


def regel_zu(text):
    """Regel, deren Muster den Text erkennt, sonst None (erste passende)."""
    for r, m in _MUSTER:
        if m.search(text or ""):
            return r
    return None


def stufe(regel, einstellung):
    """Wirksame Stufe: FEHLER immer FEHLER, sonst die Einstellung (WARNUNG, HINWEIS, aus) oder die Vorgabe."""
    if regel.stufe == FEHLER:
        return FEHLER
    w = (einstellung or {}).get(regel.id)
    return w if w in WAEHLBAR else regel.stufe


def anwenden(punkte, einstellung):
    """Check-Punkte mit den eingestellten Stufen; „aus“ fällt weg, Reihenfolge FEHLER, WARNUNG, HINWEIS."""
    if not einstellung:
        return punkte
    from .angebot_check import ARTEN, Punkt
    out = []
    for p in punkte:
        art, text = (p[0], p[1]) if isinstance(p, (tuple, list)) else (None, str(p))
        r = regel_zu(text)
        neu = stufe(r, einstellung) if r and art != FEHLER else art
        if neu == AUS:
            continue
        if neu != art:
            p = Punkt(neu, text, getattr(p, "ziel", None), getattr(p, "details", ""), getattr(p, "aktion", None))
        out.append(p)
    return sorted(out, key=lambda p: ARTEN.index(p[0]) if p[0] in ARTEN else len(ARTEN))


def laden(db):
    w = db.einstellung(STUFEN_EINSTELLUNG)
    return dict(w) if isinstance(w, dict) else {}


def setzen(db, regel_id, wert):
    """Stufe einer Regel einstellen; FEHLER-Regeln lehnt die Funktion ab (ValueError)."""
    r = REGEL[regel_id]
    if r.stufe == FEHLER:
        raise ValueError(f"{regel_id} ist FEHLER und lässt sich nicht ändern")
    if wert not in WAEHLBAR:
        raise ValueError(f"Stufe {wert!r} nicht wählbar")
    w = laden(db)
    if wert == r.stufe:
        w.pop(regel_id, None)
    else:
        w[regel_id] = wert
    db.einstellung_setzen(STUFEN_EINSTELLUNG, w)
