"""Windows-Tastenkürzel: Liste für Menü, Hilfe und Anleitung sowie Kopieren/Einfügen in Tabellen.

Die Kürzel hängen als Aktionen am Menü Bearbeiten des Hauptfensters (fenster.Hauptfenster._menue). Welche
Seite sie ausführt, richtet sich nach der Stelle mit dem Eingabefokus: Seiten nennen ihre Ziele in
KUERZEL = {Name: Methodenname oder (Methodenname, Attribut der Tabelle, in der der Fokus stehen muss)}.
In Textfeldern behalten Strg+Z, Strg+C, Strg+V, Strg+X, Entf usw. ihre gewohnte Wirkung im Text.
"""
from PySide6.QtCore import QEvent, QObject, QSortFilterProxyModel, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QAbstractItemView

# (Taste, Wirkung, wo) – Reihenfolge wie im Menü; Hilfe → Tastenkürzel und der Anhang der Anleitung zeigen sie
UEBERSICHT = [
    ("Strg+Z", "Rückgängig: letzte Änderung am Angebot zurücknehmen (bis zu 100 Schritte)", "geöffnetes Angebot"),
    ("Strg+Y", "Wiederholen: zurückgenommene Änderung wiederherstellen (auch Strg+Umschalt+Z)", "geöffnetes Angebot"),
    ("Strg+Z / Strg+Y", "Rückgängig / Wiederholen der Eingaben im Teile-Editor", "Schneidweg-Rechner, Blech-Editor"),
    ("Strg+X", "Ausschneiden: markierte Zellen kopieren und leeren", "Tabellen"),
    ("Strg+C", "Kopieren: markierte Zellen (auch mehrere) für Excel oder eine andere Tabelle", "alle Tabellen"),
    ("Strg+V", "Einfügen ab der aktuellen Zelle, auch Blöcke aus Excel", "Tabellen"),
    ("Entf", "Markierte Positionen, Zeilen, Staffeln oder Angebote löschen (im Angebot ohne Rückfrage, mit "
             "Rückgängig in der Einblendung; Angebote und Stammdaten mit Rückfrage)", "Tabellen"),
    ("Strg+A", "Alles markieren", "Tabellen"),
    ("Strg+N", "Neu: Angebot, Position, Zeile, Staffel oder Artikel – je nach Seite", "überall"),
    ("Strg+F", "Suchfeld der Seite", "Angebote, Kunden, Stammdaten, Zukauf"),
    ("Strg+K", "Suchen und ausführen: Angebot, Kunde, Profil, Werkstoff, Einstellung oder Befehl suchen, Enter "
               "öffnet bzw. führt aus", "überall"),
    ("Strg+S", "Eingabe abschließen und speichern (das Programm speichert jede Eingabe sofort)", "überall"),
    ("Strg+P", "Angebot als PDF", "geöffnetes Angebot"),
    ("Strg+Umschalt+P", "Werkstattpapiere als PDF", "geöffnetes Angebot"),
    ("Strg+Umschalt+K", "Kalkulation als PDF", "geöffnetes Angebot"),
    ("Strg+I", "STEP-Dateien importieren", "geöffnetes Angebot"),
    ("F9", "Optimieren", "geöffnetes Angebot"),
    ("F8", "Staffelpreise rechnen", "geöffnetes Angebot"),
    ("Strg+Umschalt+S", "Stückzahl ändern: markierte (ohne Markierung alle) Positionen × Faktor oder = Wert",
     "geöffnetes Angebot"),
    ("Strg+Umschalt+M", "Materialanfrage (E-Mail) an den Lieferanten", "geöffnetes Angebot"),
    ("F5", "Aktualisieren: Seite neu laden und rechnen", "überall"),
    ("F2", "Zelle bearbeiten", "Tabellen"),
    ("Eingabe", "Zur nächsten Zelle (nach unten oder rechts, Einstellung „Positionsliste: Eingabe springt“); in "
                "der letzten Zeile neue Position", "Positionsliste"),
    ("↓", "In der letzten Zeile: neue Position anlegen", "Positionsliste"),
    ("Strg+D", "Wert der Zeile darüber in die markierten Zellen übernehmen (mehrere Zeilen: die oberste füllt die "
               "übrigen)", "Positionsliste"),
    ("Eingabe", "Markiertes Angebot öffnen", "Angebote"),
    ("Esc", "Eingabe abbrechen; im Suchfeld: Suche leeren", "Tabellen, Suchfelder"),
    ("Esc", "Fenster Abwicklung bzw. Querschnitt schließen, der Editor bleibt offen", "Teile-Editor"),
    ("Enter", "Eingabe im Feld bestätigen – schließt nie das Fenster; in Tabellen eine Zeile weiter. Übernehmen "
              "und schließen nur mit dem Knopf (Ausnahme: reine Ja/Nein-Fragen)", "alle Fenster und Dialoge"),
    ("Strg+Enter", "Fenster übernehmen und schließen (wie der Knopf OK bzw. Übernehmen)", "alle Fenster und Dialoge"),
    ("Strg+W", "Geöffnetes Angebot schließen (auch Strg+F4)", "geöffnetes Angebot"),
    ("Strg+Tab", "Nächster Hauptreiter, z. B. zum nächsten offenen Angebot (Strg+Umschalt+Tab: vorheriger)",
     "überall"),
    ("Strg+Bild↓", "Nächster Unterreiter, z. B. Positionen → Kalkulation (Strg+Bild↑: vorheriger, wie in Excel)",
     "Angebot, Einstellungen, Zukauf, Fracht"),
    ("Strg+Umschalt+A", "Mit den Kollegen abgleichen (Angebote und Stammdaten, gemeinsamer Ordner)", "überall"),
    ("F1", "Bedienungsanleitung", "überall"),
    ("Alt+F4", "Programm beenden", "überall"),
]


def _quelle(ansicht, index):
    """(Quellmodell, Quellindex) – Sortier-/Filtermodelle werden durchgereicht."""
    modell = ansicht.model()
    while isinstance(modell, QSortFilterProxyModel):
        index = modell.mapToSource(index)
        modell = modell.sourceModel()
    return modell, index


def _bereich(ansicht):
    """Markierte Zellen als Zeilen/Spalten der Ansicht (nur sichtbare Spalten)."""
    zellen = [i for i in ansicht.selectionModel().selectedIndexes() if not ansicht.isColumnHidden(i.column())]
    if not zellen and ansicht.currentIndex().isValid():
        zellen = [ansicht.currentIndex()]
    return zellen


def text_der_auswahl(ansicht):
    """Markierte Zellen als Text mit Tabulatoren und Zeilenumbrüchen (wie Excel)."""
    zellen = _bereich(ansicht)
    if not zellen:
        return ""
    zeilen = sorted({i.row() for i in zellen})
    spalten = sorted({i.column() for i in zellen}, key=ansicht.horizontalHeader().visualIndex)
    werte = {(i.row(), i.column()): i.data(Qt.DisplayRole) for i in zellen}
    def text(w):
        return "" if w is None else str(w).replace("\t", " ").replace("\n", " ")
    return "\n".join("\t".join(text(werte.get((r, c))) for c in spalten) for r in zeilen)


def kopieren(ansicht):
    text = text_der_auswahl(ansicht)
    if text:
        QGuiApplication.clipboard().setText(text)
    return text


def _editierbar(ansicht, r, c):
    i = ansicht.model().index(r, c)
    return i.isValid() and bool(i.flags() & Qt.ItemIsEditable)


def _schreiben(ansicht, ziele):
    """ziele: [(Zeile, Spalte der Ansicht, Text)] -> Anzahl geänderter Zellen. Die Zellen werden vorher auf das
    Quellmodell umgerechnet, damit Neuladen oder Sortieren nach der ersten Zelle nichts verschiebt."""
    quelle = []
    for r, c, text in ziele:
        if _editierbar(ansicht, r, c):
            modell, i = _quelle(ansicht, ansicht.model().index(r, c))
            quelle.append((modell, i.row(), i.column(), text))
    n = 0
    for modell, r, c, text in quelle:
        if r < modell.rowCount() and modell.setData(modell.index(r, c), text, Qt.EditRole):
            n += 1
    return n


def einfuegen(ansicht, text=None):
    """Text aus der Zwischenablage (Tabulatoren/Zeilen) ab der aktuellen Zelle einfügen; ein einzelner Wert
    füllt alle markierten Zellen. Ergebnis: Anzahl geänderter Zellen."""
    if text is None:
        text = QGuiApplication.clipboard().text()
    if not text:
        return 0
    block = [z.split("\t") for z in text.rstrip("\r\n").replace("\r\n", "\n").split("\n")]
    if len(block) == 1 and len(block[0]) == 1:
        zellen = _bereich(ansicht)
        return _schreiben(ansicht, [(i.row(), i.column(), block[0][0]) for i in zellen])
    start = ansicht.currentIndex()
    if not start.isValid():
        return 0
    kopf = ansicht.horizontalHeader()
    sichtbar = [kopf.logicalIndex(v) for v in range(kopf.visualIndex(start.column()), kopf.count())]
    sichtbar = [c for c in sichtbar if not ansicht.isColumnHidden(c)]
    ziele = [(start.row() + dr, sichtbar[dc], wert) for dr, zeile in enumerate(block) for dc, wert in enumerate(zeile)
             if start.row() + dr < ansicht.model().rowCount() and dc < len(sichtbar)]
    return _schreiben(ansicht, ziele)


def leeren(ansicht):
    """Markierte bearbeitbare Zellen leeren. Ergebnis: Anzahl geänderter Zellen."""
    return _schreiben(ansicht, [(i.row(), i.column(), "") for i in _bereich(ansicht)])


def ist_tabelle(w):
    return isinstance(w, QAbstractItemView)


def suche_esc(feld):
    """Esc im Suchfeld leert die Suche."""
    k = QShortcut(QKeySequence(Qt.Key_Escape), feld, feld.clear)
    k.setContext(Qt.WidgetShortcut)
    return k


TASTEN_ENTER = (Qt.Key_Return, Qt.Key_Enter)


def enter_schliesst(dialog):
    """Ausnahmen der Enter-Regel: reine Bestätigungen (Ja/Nein-Fragen, Hinweise mit OK), Dateiauswahl, Fortschritt und Fenster, deren
    Sinn Enter ist (Klassenattribut ENTER_SCHLIESST = True, z. B. Suchen und ausführen)."""
    from PySide6.QtWidgets import QColorDialog, QFileDialog, QFontDialog, QMessageBox, QProgressDialog
    return isinstance(dialog, (QMessageBox, QFileDialog, QProgressDialog, QColorDialog, QFontDialog)) \
        or bool(getattr(dialog, "ENTER_SCHLIESST", False))


def dialog_von(w):
    """Der nächste Dialog, in dem w steht (w selbst eingeschlossen; auch eingebettete Dialoge), sonst None."""
    from PySide6.QtWidgets import QDialog, QWidget
    while isinstance(w, QWidget):
        if isinstance(w, QDialog):
            return w
        w = w.parentWidget()
    return None


def _geregelt(w):
    """Der Dialog, in dem w steht und für den die Enter-Regel gilt, sonst None."""
    d = dialog_von(w)
    return d if d is not None and not enter_schliesst(d) else None


def ok_knopf(dialog):
    """Der Knopf, der den Dialog übernimmt: OK/Übernehmen/Ja der Knopfleiste, sonst der Standardknopf."""
    from PySide6.QtWidgets import QDialogButtonBox, QPushButton
    def bereit(b):
        return dialog_von(b) is dialog and b.isVisible() and b.isEnabled()
    for leiste in dialog.findChildren(QDialogButtonBox):
        for b in leiste.buttons():
            if leiste.buttonRole(b) in (QDialogButtonBox.AcceptRole, QDialogButtonBox.YesRole) and bereit(b):
                return b
    return next((b for b in dialog.findChildren(QPushButton) if b.isDefault() and bereit(b)), None)


def _tabelle_weiter(dialog):
    """Enter in einer bearbeitbaren Tabelle des Dialogs (ohne offene Zelle): eine Zeile weiter wie in Excel."""
    from PySide6.QtWidgets import QApplication
    t = QApplication.focusWidget()
    if not isinstance(t, QAbstractItemView) or dialog_von(t) is not dialog \
            or t.state() == QAbstractItemView.EditingState or t.editTriggers() == QAbstractItemView.NoEditTriggers:
        return
    i = t.currentIndex()
    m = t.model()
    if not i.isValid() or m is None:
        return
    r = i.row() + 1
    while r < m.rowCount(i.parent()) and getattr(t, "isRowHidden", lambda _r: False)(r):
        r += 1
    if r < m.rowCount(i.parent()):
        t.setCurrentIndex(m.index(r, i.column(), i.parent()))


class EnterRegel(QObject):
    """Enter nach einer Eingabe schließt kein Fenster (Patrick 25.10. und 28.10.2026, gilt für alle Dialoge).

    Qt reicht ein Enter, das das Eingabefeld (Zahl, Text, Auswahl, Tabelle) nicht selbst verbraucht, an den Dialog
    weiter, und der drückt dann den Standardknopf (OK) – das Fenster ging zu. Die Regel fängt dieses Enter am Dialog
    ab: das Feld hat die Eingabe schon übernommen, in Tabellen geht es eine Zeile weiter, sonst passiert nichts.
    Strg+Enter übernimmt gezielt (klickt OK). Ein Knopf mit dem Fokus reagiert weiter auf Enter (bewusst angewählt),
    Felder, die Enter selbst nutzen (mehrzeiliger Text, Zeichnen, Suchen und ausführen), bleiben, wie sie sind."""

    def eventFilter(self, obj, e):
        if e.type() != QEvent.KeyPress or e.key() not in TASTEN_ENTER:
            return False
        strg = bool(e.modifiers() & Qt.ControlModifier)
        dialog = _geregelt(obj)
        if dialog is None:
            return False
        if strg:
            knopf = ok_knopf(dialog)
            if knopf is not None:
                knopf.click()
                return True
            return False
        if obj is not dialog:
            return False        # erst das Feld: es übernimmt die Eingabe und reicht Enter ggf. weiter
        e.accept()
        _tabelle_weiter(dialog)
        return True


def einrichten(app):
    """Einmal nach dem Anlegen der QApplication aufrufen: die Enter-Regel gilt dann in allen Dialogen."""
    if getattr(app, "_enter_regel", None) is None:
        app._enter_regel = EnterRegel(app)
        app.installEventFilter(app._enter_regel)
    return app._enter_regel


def enter_sperren(dialog):
    """Editor-Fenster (Rohr, Blech, Baugruppe, Satz): Enter nach einer Eingabe schließt das Fenster nicht mehr
    (Patrick 25.10.2026). Seit 28.10.2026 gilt das über einrichten() für alle Dialoge; hier zusätzlich am Dialog
    selbst, damit die Editoren es auch ohne die Programmeinrichtung (Tests, Einbettung) einhalten."""
    from PySide6.QtWidgets import QPushButton
    for b in dialog.findChildren(QPushButton):
        b.setAutoDefault(False)
        b.setDefault(False)
    sperre = EnterRegel(dialog)
    dialog.installEventFilter(sperre)
    return sperre
