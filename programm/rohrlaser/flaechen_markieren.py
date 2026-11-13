"""Flächen im 3D markieren (CAD-008, Plan Phase 3 und 4, Patrick 13.11.2026 „Alles einbauen“): gewählte Flächen
(Auswahl im 3D, Filter Fläche) als Sichtfläche, Abkleben oder Schweißfläche markieren. Daraus wird ein
Zusatzarbeit-Vorschlag mit dem Flächeninhalt als Menge (bei €/m²), Herkunft „aus 3D: Sichtfläche 0,012 m²“:

  Sichtfläche   → „Sichtfläche schützen“ (z. B. Schutzfolie, vorsichtig handhaben)
  Abkleben      → „Abkleben/Abdecken“ (Fläche beim Beschichten abdecken)
  Schweißfläche → „Abkleben/Abdecken“ mit „Schweißfläche freihalten“ (bleibt für die Naht ohne Beschichtung)

Ohne gewählte Fläche gilt die Markierung für das ganze Teil (Menge automatisch = Außenfläche). Wie bei der
Zusatzarbeit per Rechtsklick (zusatz_3d.py) erst mit OK in die Position geschrieben. Fehlt die Zusatzarbeit in den
Stammdaten (eigene gelöscht), gibt es nur einen Hinweis. Ohne Qt (außer dem Hinweis in markieren)."""
from . import zusatz_3d

SICHT, ABKLEBEN, SCHWEISS = "Sichtfläche", "Abkleben", "Schweißfläche"
MARKEN = (SICHT, ABKLEBEN, SCHWEISS)
ZUSATZ = {SICHT: "Sichtfläche schützen", ABKLEBEN: "Abkleben/Abdecken", SCHWEISS: "Abkleben/Abdecken"}
TEXT = {SICHT: "Sichtfläche", ABKLEBEN: "abkleben", SCHWEISS: "Schweißfläche freihalten"}
MENUE = "Fläche markieren als"
TIPP = ("Gewählte Flächen (Auswahl im 3D, Filter Fläche) als Sichtfläche, Abkleben oder Schweißfläche markieren: "
        "ergibt eine Zusatzarbeit mit dem Flächeninhalt als Menge; ohne gewählte Fläche für das ganze Teil")


def flaechen(ansicht):
    """Gewählte Flächen der Ansicht (auswahl3d, art Fläche) als Liste, [] ohne Auswahl."""
    w = getattr(ansicht, "wahl", None)
    if w is None or not getattr(w, "an", False):
        return []
    from .auswahl3d import FLAECHE
    return [g for g in getattr(w, "gewaehlt", None) or () if g.get("art") == FLAECHE]


def inhalt_m2(gewaehlt):
    """Flächeninhalt der gewählten Flächen in m² (0 ohne)."""
    return sum(float(g.get("flaeche") or 0.0) for g in gewaehlt or ()) / 1e6


def _zahl(x):
    return (f"{x:.4f}".rstrip("0").rstrip(",.") if x < 1 else f"{x:.2f}").replace(".", ",")


def eintrag(marke, katalog, m2=0.0):
    """Zusatzarbeit-Eintrag zur Marke (wie zusatz_3d.eintrag, Herkunft „aus 3D: …“) oder None, wenn die Zusatzarbeit
    in den Stammdaten fehlt bzw. aus ist. Menge = m² bei €/m², 1 bei €/Stück, sonst automatisch."""
    name = ZUSATZ.get(marke)
    z = next((z for z in katalog or () if z.get("name") == name and z.get("aktiv") != "nein"), None)
    if z is None:
        return None
    text = TEXT[marke] + (f" {_zahl(m2)} m²" if m2 > 0 else " (ganzes Teil)")
    e = zusatz_3d.eintrag(z, 1, text)
    if z.get("art") == "€/m²":
        e["menge"] = round(m2, 6) if m2 > 0 else None
    return e


def fehlt_text(marke):
    return (f"Zusatzarbeit „{ZUSATZ.get(marke)}“ fehlt in den Stammdaten (Einstellungen › Zusatzarbeiten) – "
            "die Markierung wurde nicht übernommen.")


def markieren(ziel, aufruf, parent=None):
    """Menüaktion: aufruf() ausführen (flaeche_markieren / flaeche_teil); fehlt die Zusatzarbeit, den Hinweis zeigen."""
    e = aufruf()
    if e is None and getattr(ziel, "flaeche_hinweis", None):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(parent, "Fläche markieren", ziel.flaeche_hinweis)
    return e
