"""Menü „Bearbeiten“ der Konturen im Teile-Editor (Rohr und Blech, Patrick 19.11.2026 erweiterter Auftrag 3D-Editor).

Die Werkzeuge stehen in kontur_werkzeuge.py (ohne Fenster); hier nur Abfrage, Anwenden auf alle markierten
Konturzeilen und die Meldung. Jede Aktion ist ein Schritt für Rückgängig. Eingaben dürfen Rechnungen sein
(„L/2“), wie in den Maßfeldern. Beim Rohr bleiben die STEP-Messungen aller nicht geänderten Konturen erhalten."""
from PySide6.QtWidgets import QInputDialog, QMenu

from . import einblendung
from . import kontur_werkzeuge as kw

TIPP = ("Markierte Konturen bearbeiten: drehen, versetzen (Offset), verlängern/kürzen, Richtung umkehren, Reihe mit "
        "verschiedenen Abständen, gleiche Konturen wählen; neue Formen Ellipse und Vieleck; Artikelnummer gravieren")


def _groessen(rahmen):
    try:
        return rahmen.eigenschaften.groessen()
    except (AttributeError, TypeError, ValueError):
        return {}


def setzen(rahmen, konturen, e=None):
    """Konturen in den Editor schreiben, rechnen, Ansicht auffrischen (ein Schritt für Rückgängig)."""
    d = rahmen.d
    e = d.eingaben() if e is None else e
    if rahmen.art == "rohr":
        d.eingaben_setzen(dict(e, konturen=konturen), mit_messung=True)
    else:
        d.eingaben_setzen(dict(e, konturen=konturen))
    d.rechnen()
    rahmen.aktualisieren()


def _markieren(rahmen, zeilen):
    from PySide6.QtCore import QItemSelectionModel
    t = rahmen.d.tabelle
    t.clearSelection()
    for z in zeilen:
        if 0 <= z < t.rowCount():
            t.selectionModel().select(t.model().index(z, 0), QItemSelectionModel.Select | QItemSelectionModel.Rows)


def anwenden(rahmen, werkzeug, zeilen=None):
    """werkzeug(konturzeile) -> neue Zeile auf alle markierten Zeilen; Fehler einzelner Zeilen werden gemeldet, die
    übrigen trotzdem geändert. Ergebnis: Anzahl geänderter Zeilen."""
    d = rahmen.d
    zeilen = rahmen.markierte_zeilen() if zeilen is None else zeilen
    if not zeilen:
        einblendung.melden(d, "Erst eine oder mehrere Konturen wählen.")
        return 0
    e = d.eingaben()
    konturen = list(e.get("konturen") or [])
    fehler, n = [], 0
    for z in zeilen:
        if 0 <= z < len(konturen):
            try:
                konturen[z] = werkzeug(konturen[z])
                n += 1
            except ValueError as f:
                fehler.append(str(f))
    if n:
        setzen(rahmen, konturen, e)
        _markieren(rahmen, zeilen)
    if fehler:
        einblendung.melden(d, fehler[0] + (f" (und {len(fehler) - 1} weitere)" if len(fehler) > 1 else ""))
    return n


def _frage(rahmen, titel, text, vorgabe=""):
    """Zahl oder Rechnung abfragen; None bei Abbruch oder Fehler (gemeldet)."""
    t, ok = QInputDialog.getText(rahmen.d, titel, text + "\n(Zahl oder Rechnung, z. B. L/2)", text=vorgabe)
    if not ok or not t.strip():
        return None
    try:
        return kw.zahl(t, _groessen(rahmen))
    except ValueError as f:
        einblendung.melden(rahmen.d, str(f))
        return None


def drehen(rahmen, winkel=None):
    winkel = _frage(rahmen, "Konturen drehen", "Drehen um [°] (+ = gegen den Uhrzeiger)", "90") \
        if winkel is None else winkel
    return 0 if winkel is None else anwenden(rahmen, lambda z: kw.drehen(z, winkel))


def versatz(rahmen, o=None):
    o = _frage(rahmen, "Konturen versetzen (Offset)", "Versatz [mm] (+ = größer nach außen, − = nach innen)", "1") \
        if o is None else o
    return 0 if o is None else anwenden(rahmen, lambda z: kw.versatz(z, o))


def verlaengern(rahmen, delta=None):
    delta = _frage(rahmen, "Konturen verlängern / kürzen", "Länge ändern um [mm] (− = kürzen)", "5") \
        if delta is None else delta
    return 0 if delta is None else anwenden(rahmen, lambda z: kw.verlaengern(z, delta))


def umkehren(rahmen):
    return anwenden(rahmen, kw.umkehren)


def reihe(rahmen, text=None, achse=None):
    """Gewählte Kontur als Reihe mit verschiedenen Abständen (neue Zeilen)."""
    d = rahmen.d
    zeilen = rahmen.markierte_zeilen()
    if len(zeilen) != 1:
        einblendung.melden(d, "Reihe: Genau eine Kontur wählen.")
        return 0
    if text is None:
        text, ok = QInputDialog.getText(d, "Reihe mit Abständen", "Abstände nacheinander [mm], mit ; getrennt\n"
                                        "z. B. 20; 35; 50 (Rechnungen erlaubt)", text="20; 35; 50")
        if not ok:
            return 0
    if achse is None:
        achse = "x"
        if rahmen.art != "rohr":
            wahl, ok = QInputDialog.getItem(d, "Reihe mit Abständen", "Richtung", ["x", "y"], 0, False)
            if not ok:
                return 0
            achse = wahl
    try:
        abst = kw.abstaende_lesen(text, _groessen(rahmen))
    except ValueError as f:
        einblendung.melden(d, str(f))
        return 0
    e = d.eingaben()
    konturen = list(e.get("konturen") or [])
    r = zeilen[0]
    konturen[r], neu = kw.reihe(konturen[r], abst, achse)
    setzen(rahmen, konturen + neu, e)
    _markieren(rahmen, [r] + list(range(len(konturen), len(konturen) + len(neu))))
    return len(neu)


def gleiche_waehlen(rahmen, wie="art"):
    d = rahmen.d
    zeilen = rahmen.markierte_zeilen()
    if not zeilen:
        einblendung.melden(d, "Erst eine Kontur wählen.")
        return []
    neu = kw.gleiche(d.eingaben().get("konturen") or [], zeilen[0], wie)
    _markieren(rahmen, neu)
    return neu


def form_einfuegen(rahmen, form, masse=None):
    """Ellipse (a, b) oder Vieleck (n, d) als Polygonzeile anhängen und wählen."""
    d = rahmen.d
    if masse is None:
        if form == "ellipse":
            t, ok = QInputDialog.getText(d, "Ellipse einfügen", "Achsen a × b [mm] (a längs, b quer)", text="40 x 20")
        else:
            t, ok = QInputDialog.getText(d, "Vieleck einfügen", "Ecken und Umkreis-Ø, z. B. 6 x 30", text="6 x 30")
        if not ok:
            return False
        teile = t.lower().replace("×", "x").replace("*", "x").split("x")
        try:
            masse = [kw.zahl(s, _groessen(rahmen)) for s in teile]
        except ValueError as f:
            einblendung.melden(d, str(f))
            return False
        if len(masse) != 2 or None in masse:
            einblendung.melden(d, "Bitte zwei Werte eingeben, z. B. 40 x 20.")
            return False
    try:
        lage = dict(x=round(rahmen.teil_laenge() / 2, 1)) if rahmen.art == "rohr" else {}
        z = kw.ellipse(*masse, **lage) if form == "ellipse" else kw.vieleck(int(masse[0]), masse[1], **lage)
    except ValueError as f:
        einblendung.melden(d, str(f))
        return False
    (d.zeile_neu if rahmen.art == "rohr" else d.kontur_neu)(z)
    d.rechnen()
    r = d.tabelle.rowCount() - 1
    rahmen.aktualisieren()
    d.tabelle.selectRow(r)
    rahmen.waehlen(f"kontur:{r}")
    return True


def _artikel(rahmen):
    d = rahmen.d
    for feld in ("k_artikel", "artikelnr"):         # Rohr-Editor bzw. Blech-Editor (Kopf)
        w = getattr(d, feld, None)
        if w is not None and w.text().strip():
            return w.text().strip()
    return str((getattr(d, "p", None) or {}).get("artikel") or "").strip()


def _einstellung(rahmen, name, vorgabe):
    db = getattr(rahmen.d, "db", None)
    try:
        v = db.einstellung(name) if db is not None else None
    except (AttributeError, KeyError):
        v = None
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else vorgabe


def artikel_gravieren(rahmen, hoehe=None):
    """Option „Artikelnummer gravieren“ (Patrick 19.11.2026): Text = Artikelnummer des Artikels, gefragt wird nur die
    Schriftgröße; Lage automatisch mit Sicherheitsabstand (Einstellung gravur_abstand, Vorgabe 3 mm) zu anderen
    Konturen, Enden und Rand. Eine schon vorhandene Artikelnummer-Gravur wird ersetzt. Ergebnis: True, wenn gesetzt."""
    from . import blech, step_export
    from . import schneidweg as sw
    d = rahmen.d
    text = _artikel(rahmen)
    if not text:
        einblendung.melden(d, "Artikelnummer gravieren: Der Artikel hat keine Artikelnummer (Feld Artikel oben).")
        return False
    if hoehe is None:
        hoehe, ok = QInputDialog.getDouble(d, "Artikelnummer gravieren", f"Artikelnummer „{text}“\nSchriftgröße "
                                           "(Schrifthöhe) [mm]", _einstellung(rahmen, "gravur_schrifthoehe", 10.0),
                                           1.0, 200.0, 1)
        if not ok:
            return False
    abstand = _einstellung(rahmen, "gravur_abstand", 3.0)
    e = d.eingaben()
    konturen = [z for z in e.get("konturen") or () if not (z.get("art") == sw.TEXT_GRAVUR and z.get("artikel"))]
    if rahmen.art == "rohr":
        z = step_export.artikel_gravur(d.qs, dict(e, konturen=konturen), rahmen.teil_laenge(), text, float(hoehe),
                                       abstand)
    else:
        z = dict(art=sw.TEXT_GRAVUR, anzahl=1, text=text, hoehe=float(hoehe), winkel=0)
        lage = blech.gravur_lage(dict(e, konturen=konturen), z, mindest=abstand)
        z = dict(z, **{n: lage[n] for n in ("x", "y", "winkel")}) if lage else None
    if not z:
        einblendung.melden(d, f"Artikelnummer gravieren: kein Platz mit {abstand:g} mm Sicherheitsabstand – "
                              "Schrift kleiner wählen oder Abstand in den Einstellungen ändern.")
        return False
    z["artikel"] = True
    setzen(rahmen, konturen + [z], e)
    r = len(konturen)
    _markieren(rahmen, [r])
    return True


def menue(rahmen, parent=None):
    m = QMenu(parent)
    m.setToolTipsVisible(True)
    m.addAction("Artikelnummer gravieren …", lambda: artikel_gravieren(rahmen))
    m.addSeparator()
    m.addAction("Drehen um …", lambda: drehen(rahmen))
    m.addAction("Versatz (Offset) …", lambda: versatz(rahmen))
    m.addAction("Verlängern / Kürzen …", lambda: verlaengern(rahmen))
    m.addAction("Richtung umkehren", lambda: umkehren(rahmen))
    m.addAction("Reihe mit Abständen …", lambda: reihe(rahmen))
    m.addSeparator()
    g = m.addMenu("Gleiche wählen")
    g.addAction("Gleiche Konturart", lambda: gleiche_waehlen(rahmen, "art"))
    g.addAction("Gleiche Art und Maße", lambda: gleiche_waehlen(rahmen, "masse"))
    g.addAction("Gleiche Seite", lambda: gleiche_waehlen(rahmen, "seite"))
    m.addSeparator()
    m.addAction("Ellipse einfügen …", lambda: form_einfuegen(rahmen, "ellipse"))
    m.addAction("Vieleck einfügen …", lambda: form_einfuegen(rahmen, "vieleck"))
    return m
