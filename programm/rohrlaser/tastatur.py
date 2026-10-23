"""Windows-Tastenkürzel: Liste für Menü, Hilfe und Anleitung sowie Kopieren/Einfügen in Tabellen.

Die Kürzel hängen als Aktionen am Menü Bearbeiten des Hauptfensters (fenster.Hauptfenster._menue). Welche
Seite sie ausführt, richtet sich nach der Stelle mit dem Eingabefokus: Seiten nennen ihre Ziele in
KUERZEL = {Name: Methodenname oder (Methodenname, Attribut der Tabelle, in der der Fokus stehen muss)}.
In Textfeldern behalten Strg+Z, Strg+C, Strg+V, Strg+X, Entf usw. ihre gewohnte Wirkung im Text.
"""
from PySide6.QtCore import QSortFilterProxyModel, Qt
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import QAbstractItemView

# (Taste, Wirkung, wo) – Reihenfolge wie im Menü; Hilfe → Tastenkürzel und der Anhang der Anleitung zeigen sie
UEBERSICHT = [
    ("Strg+Z", "Rückgängig: letzte Änderung am Angebot zurücknehmen (bis zu 100 Schritte)", "geöffnetes Angebot"),
    ("Strg+Y", "Wiederholen: zurückgenommene Änderung wiederherstellen (auch Strg+Umschalt+Z)", "geöffnetes Angebot"),
    ("Strg+X", "Ausschneiden: markierte Zellen kopieren und leeren", "Tabellen"),
    ("Strg+C", "Kopieren: markierte Zellen (auch mehrere) für Excel oder eine andere Tabelle", "alle Tabellen"),
    ("Strg+V", "Einfügen ab der aktuellen Zelle, auch Blöcke aus Excel", "Tabellen"),
    ("Entf", "Markierte Positionen, Zeilen, Staffeln oder Angebote löschen (mit Rückfrage)", "Tabellen"),
    ("Strg+A", "Alles markieren", "Tabellen"),
    ("Strg+N", "Neu: Angebot, Position, Zeile, Staffel oder Artikel – je nach Seite", "überall"),
    ("Strg+F", "Suchfeld der Seite", "Angebote, Kunden, Stammdaten, Zukauf"),
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
    ("Eingabe", "Markiertes Angebot öffnen", "Angebote"),
    ("Esc", "Eingabe abbrechen; im Suchfeld: Suche leeren", "Tabellen, Suchfelder"),
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
