"""Live-Preis im Editor (Roadmap Kalkulation, Phase 1, CAD-004; Freigabe Patrick 12.11.2026).

Der Editor zeigt laufend den Stückpreis der Position mit den aktuellen Eingaben und die Differenz zum Preis beim
Öffnen. Gerechnet wird mit dem Schnittplan des Angebots (Material wie geplant; Laserzeit, Konturen und Zusatzarbeiten
mit den neuen Werten). Ändert die Eingabe die Länge, stimmt der Materialanteil erst nach dem Neu-Optimieren; der
Tooltip sagt das. Ohne Angebot, ohne Schnittplan oder bei großen Angeboten (über GRENZE_POSITIONEN) nichts. Ohne Qt."""
GRENZE_POSITIONEN = 300


def stueckpreis(seite, p):
    """Stückpreis der Position p (gleiche id) im Angebot der Seite oder None."""
    from . import rechnen
    if seite is None or not p or not p.get("id"):
        return None
    positionen = getattr(seite, "positionen", None)
    ergebnis = getattr(seite, "ergebnis", None)
    if not positionen or not ergebnis or len(positionen) > GRENZE_POSITIONEN:
        return None
    pos = [p if x.get("id") == p.get("id") else x for x in positionen]
    try:
        i = [x.get("id") for x in pos].index(p["id"])
        zeilen, _ = rechnen.kalkulation(seite.kopf, pos, ergebnis, seite.k, seite.tabellen, seite.einst)
    except Exception:           # unvollständige Eingaben: kein Preis, nie den Editor stören
        return None
    z = zeilen[i] if i < len(zeilen) else None
    return z["preis_teil"] if z else None


def text(jetzt, start):
    """('12,34 €', '+0,56 € gegenüber dem Öffnen') für die Kachel."""
    from .stammdaten import zahl_als_text as zahl
    wert = f"{zahl(jetzt, 2)} €"
    if start is None or abs(jetzt - start) < 0.005:
        return wert, "Stückpreis wie beim Öffnen"
    d = jetzt - start
    return f"{wert} ({'+' if d > 0 else '−'}{zahl(abs(d), 2)} €)", \
        f"beim Öffnen {zahl(start, 2)} € je Stück; Material nach dem Schnittplan des Angebots (nach Längenänderung " \
        "erst nach dem Optimieren genau)"
