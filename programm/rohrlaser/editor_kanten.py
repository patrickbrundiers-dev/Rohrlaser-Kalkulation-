"""Editor-Teil von Paket 6 (CAD-Entwicklungsplan 4.2, 4.4 und 5.2): im Rohr- und Blech-Editor (auch aus Baugruppe
und Satz in 3D, die diese Editoren öffnen) gewählte Kanten als Kontur übernehmen, eine Kontur skalieren und die zur
3D-Auswahl passenden Knöpfe in der Eigenschaften-Tafel. Rechnung in kanten_kontur."""
from . import auswahl3d, blech, editor_ausschnitt, einblendung, kanten_kontur

TIPP_KANTEN = ("Im 3D mit „Auswahl“ (Filter Kante) die Kanten einer Kontur anklicken (Strg für mehrere) und hier "
               "übernehmen: das Programm verbindet sie, prüft, ob die Kontur geschlossen ist und sich nicht selbst "
               "überschneidet, und legt sie als Sonderkontur (Rohr) bzw. Polygon (Blech) genau an der Stelle an; ein "
               "einzelner Kreis wird eine Bohrung")
TIPP_SKALIEREN = ("Gewählte Kontur um einen Faktor vergrößern oder verkleinern (um ihre Mitte; Lage, Seite und Tiefe "
                  "bleiben): Maße, Polygonpunkte und Umriss werden gestreckt")


def _kanten(rahmen):
    a = rahmen.ansicht()
    if a is None:
        return []
    return [g for g in a.wahl.gewaehlt if g.get("art") == auswahl3d.KANTE]


def kontur(rahmen, kanten=None):
    """Konturzeile aus den gewählten Kanten (ValueError mit Grund)."""
    d = rahmen.d
    kanten = _kanten(rahmen) if kanten is None else kanten
    if rahmen.art == "rohr":
        return kanten_kontur.rohr(d.qs, kanten)
    e = d.eingaben()
    return kanten_kontur.blech(e, blech.zuschnitt(e), kanten)


def aus_kanten(rahmen, kanten=None):
    """Gewählte Kanten als neue Konturzeile anhängen und wählen. Ergebnis: Zeilennummer oder None (Grund gemeldet)."""
    d = rahmen.d
    try:
        z = kontur(rahmen, kanten)
    except ValueError as f:
        einblendung.melden(d, str(f))
        return None
    if rahmen.art == "rohr":
        d.zeile_neu(z)
    else:
        d.kontur_neu(z)
    r = d.tabelle.rowCount() - 1
    d.rechnen()
    rahmen.aktualisieren()
    a = rahmen.ansicht()
    if a is not None:
        a.wahl.waehlen([])
    rahmen.waehlen(f"kontur:{r}")
    return r


def skalieren(rahmen, faktor=None, r=None):
    """Gewählte Konturzeile mit dem Faktor (1.5 = 150 %) skalieren; ohne Faktor fragen. Ergebnis: True/False."""
    d = rahmen.d
    r = rahmen._gewaehlte_zeile() if r is None else r
    e = d.eingaben()
    konturen = list(e.get("konturen") or [])
    if r is None or not 0 <= r < len(konturen):
        einblendung.melden(d, "Skalieren: Erst eine Kontur wählen.")
        return False
    if faktor is None:
        from PySide6.QtWidgets import QInputDialog
        proz, ok = QInputDialog.getDouble(d, "Kontur skalieren", "Größe in % (100 = gleich, 200 = doppelt so groß)",
                                          100.0, 1.0, 10000.0, 1)
        if not ok:
            return False
        faktor = proz / 100.0
    try:
        konturen[r] = kanten_kontur.skalieren(konturen[r], faktor)
    except ValueError as f:
        einblendung.melden(d, str(f))
        return False
    d.eingaben_setzen(dict(e, konturen=konturen))
    d.rechnen()
    rahmen.aktualisieren()
    rahmen.waehlen(f"kontur:{r}")
    return True


def aktionen(rahmen, gewaehlt):
    """Knöpfe der Eigenschaften-Tafel zur 3D-Auswahl im Editor: [(Text, Funktion, Tipp)]."""
    out = []
    kanten = [g for g in gewaehlt if g.get("art") == auswahl3d.KANTE]
    flaechen = [g for g in gewaehlt if g.get("art") == auswahl3d.FLAECHE]
    if kanten and len(kanten) == len(gewaehlt):
        out.append(("Kontur aus Kanten", lambda: aus_kanten(rahmen), TIPP_KANTEN))
    if len(flaechen) == 1 and len(gewaehlt) == 1:
        if rahmen.art == "rohr":
            out.append(("Ausschnitt mit Tiefe hier", lambda: editor_ausschnitt.einfuegen(rahmen),
                        editor_ausschnitt.TIPP_ROHR))
        else:
            out.append((editor_ausschnitt.TITEL + " …", lambda: editor_ausschnitt.blech_dialog(rahmen),
                        editor_ausschnitt.TIPP_BLECH))
    return out
