"""Sicherheit des Preises einer Schweißbaugruppe (Plan Schweißbaugruppe Teil 2, 13.11.2026, G8): woher kommen die
Kosten der Fertigung (Schweißen, Arbeitsgänge, Fremdleistung) und wie weit kann der Preis danebenliegen?

Jede Zeile der Rechnung (baugruppe.rechnen) zählt mit ihren Kosten zu einer Quelle:
  von Hand      Zeit von Hand an der Nahtgruppe, Arbeitsgang von Hand, Zeitvorgabe der Baugruppe
  geprüft       geprüfte Kennwerte bzw. bestätigter Vorschlag
  Richtwert     Kennwert oder Regel mit Status Richtwert
  Vorschlag     offener (gelber) Vorschlag der Vorkalkulation
Jede Quelle hat eine übliche Streuung (SPANNE, in % der Kosten); die Spanne der Baugruppe ist das nach Kosten
gewichtete Mittel. Liegt eine Ist-Zeit derselben oder einer ähnlichen Baugruppe vor (bg_erfahrung), wird ihre
Abweichung dazu genannt. Reine Anzeige: der Preis ändert sich dadurch nicht."""
from . import bg_vorgabe

HAND, GEPRUEFT, RICHTWERT, VORSCHLAG = "von Hand", "geprüft", "Richtwert", "Vorschlag offen"
QUELLEN = (HAND, GEPRUEFT, RICHTWERT, VORSCHLAG)
SPANNE = {HAND: 5.0, GEPRUEFT: 10.0, RICHTWERT: 25.0, VORSCHLAG: 30.0}
GRUEN_BIS, GELB_BIS = 12.0, 20.0


def quelle(zeile):
    """Quelle einer Zeile aus baugruppe.rechnen()['zeilen']."""
    w = zeile.get("werte") or {}
    if zeile.get("art") == "Naht":
        if w.get("hand"):
            return HAND
        if zeile.get("vorschlag"):
            return VORSCHLAG
        return RICHTWERT if w.get("richtwert") else GEPRUEFT
    if zeile.get("vorschlag"):
        return VORSCHLAG
    return GEPRUEFT if zeile.get("vk_status") == "bestätigt" else HAND      # eigener bzw. geänderter Arbeitsgang


def bewerten(bg, erg, erfahrung=None):
    """dict(anteile {Quelle: Anteil 0..1}, spanne (± %), ampel 'grün'|'gelb'|'rot', kurz, text) oder None ohne
    Kosten. erfahrung = bg_erfahrung.letzte(...) oder None."""
    zeilen = (erg or {}).get("zeilen") or ()
    summen = dict.fromkeys(QUELLEN, 0.0)
    hand_bg = bool(((erg or {}).get("zeiten") or {}).get("hand")) or bg_vorgabe.hat_vorgabe(bg or {})
    for z in zeilen:
        k = abs(z.get("kosten") or 0.0) + abs(z.get("einmal") or 0.0)
        if k <= 0:
            continue
        q = quelle(z)
        if hand_bg and not z.get("fremd") and q != HAND:
            q = HAND                    # Zeitvorgabe von Hand ersetzt die berechnete Zeit der eigenen Arbeit
        summen[q] += k
    gesamt = sum(summen.values())
    if gesamt <= 0:
        return None
    anteile = {q: summen[q] / gesamt for q in QUELLEN}
    spanne = sum(anteile[q] * SPANNE[q] for q in QUELLEN)
    ampel = "grün" if spanne <= GRUEN_BIS + 1e-9 else "gelb" if spanne <= GELB_BIS + 1e-9 else "rot"
    teile = [f"{round(anteile[q] * 100)} % {q}" for q in QUELLEN if anteile[q] >= 0.005]
    text = (f"Sicherheit der Fertigungskosten: etwa ± {round(spanne)} % ({ampel}). Herkunft nach Kosten: "
            + ", ".join(teile) + ". Übliche Streuung je Herkunft: "
            + ", ".join(f"{q} ± {round(SPANNE[q])} %" for q in QUELLEN) + ".")
    if erfahrung and erfahrung.get("faktor"):
        ab = (erfahrung["faktor"] - 1) * 100
        text += (f" Nachkalkulation ({erfahrung.get('art')} Baugruppe, {erfahrung.get('angebot') or ''}): Ist "
                 f"{'+' if ab >= 0 else '−'}{abs(round(ab))} % gegenüber der berechneten Zeit.")
    return dict(anteile=anteile, spanne=spanne, ampel=ampel, kurz=f"± {round(spanne)} %", text=text)
