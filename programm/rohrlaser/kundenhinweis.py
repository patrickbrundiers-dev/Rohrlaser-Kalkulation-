"""Kundenhinweis (Plan PROfirst-/LogiTRACE-Handbücher 12.11.2026, G1).

Freitext am Kunden (kunden.hinweis), z. B. „nur gebürstet liefern“ oder „Vorkasse“. Er steht groß im Angebotskopf,
sobald ein Angebot dieses Kunden angelegt oder geöffnet wird, und kommt in die Meldung beim Wählen des Kunden. Mit
kunden.hinweis_werkstatt = 'ja' steht er auch oben auf den Werkstattpapieren. Ändert keine Preise."""


def hinweis(kunde):
    """Hinweistext eines Kunden-Datensatzes ('' ohne)."""
    return str((kunde or {}).get("hinweis") or "").strip()


def fuer_angebot(db, kopf):
    """Hinweis des Kunden im Angebotskopf ('' ohne Kunde, ohne Eintrag im Kundenstamm oder ohne Hinweis)."""
    nr = (kopf or {}).get("kundennr")
    if not nr:
        return ""
    try:
        return hinweis(db.kunde(nr))
    except Exception:
        return ""


def fuer_werkstatt(db, kopf):
    """Hinweis für die Werkstattpapiere: nur wenn am Kunden 'Hinweis auf Werkstattpapiere' = ja."""
    nr = (kopf or {}).get("kundennr")
    if not nr:
        return ""
    try:
        k = db.kunde(nr) or {}
    except Exception:
        return ""
    return hinweis(k) if str(k.get("hinweis_werkstatt") or "").lower() == "ja" else ""
