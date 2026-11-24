"""Kennzeichen „nur kalkuliert“ (Plan PROfirst-/LogiTRACE-Handbücher 12.11.2026, I3).

PROfirst-Regel „Teile, die aus PDF nachgezeichnet und nicht genau gezeichnet sind, dürfen nicht geschnitten werden“:
Positionen, deren Geometrie nur für den Preis gut genug ist, tragen in positionen.geometrie den Wert
„nur kalkuliert“. Das sind Positionen aus einer PDF-Zeichnung oder einem Scan (pdf_zeichnung.py, Texterkennung bzw.
Linien einer Ansicht) und aus dem Schnellpreis (grobe Konturen). Sie bekommen den Status-Hinweis, und die Übergabe an
das CAM (cam_paket.py) baut für sie keine STEP-Datei, bis die Geometrie gesichert ist: STEP/DXF neu einlesen oder
von Hand „Geometrie geprüft“ setzen (Kontextmenü der Position). So bleibt die Grundregel „Konturen 100 % wie STEP“
geschützt.

Werte: leer = normal (STEP, DXF oder von Hand eingegeben), „nur kalkuliert“, „geprüft“ (von Hand bestätigt)."""

NUR_KALKULIERT = "nur kalkuliert"
GEPRUEFT = "geprüft"
WERTE = (NUR_KALKULIERT, GEPRUEFT)
STATUS = "HINWEIS: nur kalkuliert – Geometrie vor der Fertigung sichern (STEP/DXF einlesen oder als geprüft markieren)"


def wert(p):
    """Gespeicherter Wert der Position ('' = normal)."""
    w = str((p or {}).get("geometrie") or "").strip()
    return w if w in WERTE else ""


def nur_kalkuliert(p):
    """True, solange die Geometrie nicht gesichert ist. Wird später eine STEP in die Position eingelesen (Editor:
    STEP einlesen, technik.step_datei), gilt sie als gesichert, auch wenn das Feld noch „nur kalkuliert“ zeigt."""
    if wert(p) != NUR_KALKULIERT:
        return False
    import json
    try:
        e = json.loads((p or {}).get("technik") or "{}")
    except (TypeError, ValueError):
        e = {}
    return not (isinstance(e, dict) and e.get("step_datei"))


def aus_zeichnung(erg):
    """Neue Position aus einer Zeichnung (Ergebnis von pdf_zeichnung bzw. dxf_rohr): PDF und Scan sind nur
    kalkuliert, eine DXF-Datei (Vektor, maßstäblich) gilt als gesichert. Ergebnis: Wert für positionen.geometrie
    oder None."""
    quelle = str((erg or {}).get("quelle_name") or "")
    return NUR_KALKULIERT if "PDF" in quelle or (erg or {}).get("ocr") else None


def umschalten(p, an=None):
    """Neuer Wert beim Umschalten: an=True = als geprüft markieren, False = wieder „nur kalkuliert“, None = je nach
    aktuellem Wert (nur kalkuliert -> geprüft, sonst -> nur kalkuliert)."""
    if an is None:
        an = nur_kalkuliert(p)
    return GEPRUEFT if an else NUR_KALKULIERT


def cam_hinweis(name):
    """Hinweis der CAM-Übergabe für eine nur kalkulierte Position."""
    return (f"{name}: nur kalkuliert (aus PDF-Zeichnung oder Schnellpreis), keine STEP – erst STEP/DXF einlesen "
            "oder die Geometrie als geprüft markieren")


def wenden_erlaubt(p):
    """Plan PROfirst H4 (Ergänzung zu ArTube „Teil wenden“): False, wenn die Position „nicht wenden“ trägt
    (positionen.wenden = 'nein': Sichtseite, Folie, Schliff). Dann legt kein Programmteil ein gedrehtes oder
    gewendetes Duplikat an, auch wenn die Regeln es sonst erlauben würden."""
    return str((p or {}).get("wenden") or "").strip().lower() != "nein"
