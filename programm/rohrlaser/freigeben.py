"""Speicher geschlossener Fenster wirklich freigeben (Systemcheck vor dem Sammel-Update, Patrick 19.11.2026).

Befund: Ein geschlossenes Angebot blieb mit allen Daten (Positionen, Ergebnisse, 3D-Netze) im Speicher, je Öffnen und
Schließen eines Angebots mit 33 STEP-Teilen rund 29 MB mehr. Ursache: Die Qt-Objekte der Seite werden gelöscht, ihre
Python-Hüllen bleiben aber in Ringen stehen (Seite -> Modell -> Seite), und Ringe mit PySide-Hüllen räumt die
Speicherbereinigung von Python nicht ab. Dazu kamen Modelle ohne Qt-Eltern (Tabellenmodelle, Bote der Staffeln), die
gar nicht gelöscht wurden.

nach_loeschen(widget) vor widget.deleteLater(): Modelle ohne Eltern, die das Fenster oder seine Unterobjekte halten,
bekommen das Fenster als Eltern (werden mit ihm gelöscht); nach dem Löschen werden die Python-Attribute aller nun
gelöschten Hüllen geleert. Damit ist der Ring aufgelöst und Python gibt die Daten frei. Geleert wird nur, was Qt
schon gelöscht hat – ein noch lebendes Objekt (z. B. das Hauptfenster) wird nie
angefasst.
"""
from PySide6.QtCore import QAbstractItemModel, QObject, QTimer

zaehler = {"freigegeben": 0, "geleert": 0}


def _lebt(o):
    """Qt-Objekt noch nicht gelöscht (wie shiboken6.isValid, ohne eigenes Paket im Windows-Bau)."""
    try:
        o.objectName()
        return True
    except RuntimeError:            # „Internal C++ object … already deleted“
        return False


def _eigene(o):
    """QObject-Werte in den Attributen von o (eine Ebene, auch in Listen/Tupeln)."""
    try:
        werte = list(vars(o).values())
    except TypeError:
        return []
    out = []
    for w in werte:
        if isinstance(w, QObject):
            out.append(w)
        elif isinstance(w, (list, tuple)) and len(w) < 200:
            out.extend(x for x in w if isinstance(x, QObject))
    return out


def nach_loeschen(widget):
    """Vor widget.deleteLater() aufrufen. Ergebnis: Anzahl erfasster Objekte."""
    if widget is None or not _lebt(widget):
        return 0
    objekte = {id(widget): widget}
    for c in widget.findChildren(QObject):
        objekte[id(c)] = c
    for o in list(objekte.values()):
        for w in _eigene(o):
            if id(w) in objekte or not _lebt(w):
                continue
            # Modell bzw. Bote ohne Eltern, das nur dieses Fenster benutzt: mit dem Fenster löschen
            if w.parent() is None and (isinstance(w, QAbstractItemModel) or type(w).__name__ == "_Bote"):
                w.setParent(widget)
                objekte[id(w)] = w
    liste = list(objekte.values())

    def leeren():
        n = 0
        for o in liste:
            if _lebt(o):
                continue                # lebt noch (nie anfassen)
            try:
                d = o.__dict__
            except AttributeError:
                continue
            if d:
                d.clear()
                n += 1
        liste.clear()
        zaehler["freigegeben"] += 1
        zaehler["geleert"] += n

    # „destroyed“ kommt zu Beginn des Löschens; geleert wird danach, wenn auch alle Unterobjekte gelöscht sind
    widget.destroyed.connect(lambda *_: QTimer.singleShot(0, leeren))
    return len(liste)
