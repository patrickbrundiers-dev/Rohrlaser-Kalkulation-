"""Von Hand geänderte STEP-Werte einer Position (Plan 3D-Viewer 18.11.2026, V5): damit nach einer Änderung im Rohr-
oder Blech-Editor überall sichtbar bleibt, dass die Geometrie nicht mehr genau die der STEP-Datei ist.

- Rohr: beim OK im Editor schreibt der Rahmen die Merkmale mit Herkunft „manuell (STEP geändert)“ in die Eingaben
  (Schlüssel 'hand' in positionen.technik: dict(merkmale=[Text, …])); ohne Änderung fällt der Schlüssel weg.
- Blech: die Eingaben tragen die gemessenen Werte schon selbst (e['step'], blech.aus_step); verglichen wird live.

Genutzt von der 3D-Vorschau (Modell aus den Eingaben statt des STEP-Netzes, Hinweis „von Hand geändert“) und von
herkunft.py (Laser: „Geometrie aus STEP, von Hand geändert“). Rechnet nichts. Ohne Qt."""
import json

SCHLUESSEL = "hand"
BLECH_NAMEN = {"konturen": "Innenkonturen", "schenkel": "Biegungen", "biegungen": "Biegungen"}


def eintragen(eingaben, merkmale):
    """Eingaben (Rohr) mit der Liste der von Hand geänderten STEP-Merkmale; leere Liste = Schlüssel weg."""
    out = dict(eingaben)
    texte = [str(t) for t in merkmale or () if t]
    if texte:
        out[SCHLUESSEL] = dict(merkmale=texte)
    else:
        out.pop(SCHLUESSEL, None)
    return out


def _technik(p):
    t = (p or {}).get("technik")
    if isinstance(t, dict):
        return t
    try:
        t = json.loads(t) if t else None
    except (TypeError, ValueError):
        return None
    return t if isinstance(t, dict) else None


def liste(p):
    """Texte der von Hand geänderten STEP-Werte der Position p ([] = wie gemessen bzw. kein STEP)."""
    t = _technik(p)
    if not t:
        return []
    h = t.get(SCHLUESSEL)
    if isinstance(h, dict) and isinstance(h.get("merkmale"), list):
        return [str(x) for x in h["merkmale"]]
    step = t.get("step")
    if isinstance(step, dict):          # Blech/Kantteil: gemessene Werte liegen in den Eingaben
        namen = []
        for k, v in step.items():
            if k in t and t.get(k) != v:
                n = BLECH_NAMEN.get(k, "Zuschnitt")
                if n not in namen:
                    namen.append(n)
        return namen
    return []


def text(p, kurz=False):
    """„von Hand geändert: Ende A, 2. Bohrung“ bzw. "" ohne Änderung."""
    texte = liste(p)
    if not texte:
        return ""
    if kurz or len(texte) > 3:
        return f"von Hand geändert ({len(texte)} {'Stelle' if len(texte) == 1 else 'Stellen'})"
    return "von Hand geändert: " + "; ".join(texte)
