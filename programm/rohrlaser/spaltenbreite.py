"""Spaltenbreite und Zeilenhöhe der Tabellen automatisch an den Inhalt anpassen.

Regeln (für alle Tabellen gleich, damit das Layout ruhig und übersichtlich bleibt):
- Spalte so breit wie Inhalt bzw. Kopf (Kopf höchstens zweizeilig, kein Wort abgeschnitten), höchstens MAX_BREITE.
- Beim ersten Füllen werden alle Spalten eingepasst, danach wachsen sie nur noch (nie schmaler), damit die Tabelle
  beim Tippen nicht springt.
- Eine Spalte, die der Benutzer mit der Maus breiter oder schmaler zieht, bleibt so – auch nach einem Neustart
  (Layout-Plan L15): die Breite wird je Tabelle und Spaltentitel in der Einstellung SPEICHER_NAME gemerkt (nur
  dieser Arbeitsplatz). Rechtsklick auf den Spaltenkopf → „Spaltenbreiten zurücksetzen“ passt wieder alles an.
- Zeilen mit langem Text werden höher (Text umgebrochen), höchstens MAX_ZEILEN Textzeilen; der Rest wird mit …
  gekürzt und steht vollständig im Tooltip. Zeilen ohne langen Text bleiben einzeilig, damit wenig gescrollt wird.
- Bei sehr vielen Zeilen (über MAX_ANZAHL) bleiben die Zeilen einzeilig (Geschwindigkeit).
- Eine Tabelle, die gerade nicht zu sehen ist (anderer Reiter), wird erst beim Zeigen eingepasst (Performance-Audit
  22.10.2026: das Einpassen verdeckter Tabellen kostete beim Angebots-PDF eines Angebots mit 200 Positionen ~20 s).
"""
from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtGui import QAction, QFont, QFontMetrics, QGuiApplication

MAX_BREITE = 260
MIN_BREITE = 40
MAX_ZEILEN = 3
MAX_ANZAHL = 500
SPEICHER_NAME = "ansicht_spaltenbreiten"     # {Tabelle: {Spaltentitel: Breite}}; keine EINSTELLUNG, daher nie geteilt
_db = None                                   # Datenbank fürs Merken, setzt das Hauptfenster (speicher_setzen)


def speicher_setzen(db):
    global _db
    _db = db


def _gemerkt():
    try:
        return dict(_db.einstellung(SPEICHER_NAME) or {}) if _db is not None else {}
    except Exception:           # z. B. Datendatei gerade nicht lesbar: dann eben ohne gemerkte Breiten
        return {}


def _merken(schluessel, breiten):
    if _db is None or getattr(_db, "nur_lesen", False):
        return
    alle = _gemerkt()
    if breiten:
        alle[schluessel] = breiten
    else:
        alle.pop(schluessel, None)
    try:
        _db.einstellung_setzen(SPEICHER_NAME, alle)
    except Exception:
        pass


def tabellen_schluessel(ansicht):
    """Kennung einer Tabelle fürs Merken: Name der Ansicht, sonst Modellklasse und Titel der ersten Spalte."""
    if ansicht.objectName():
        return ansicht.objectName()
    m = ansicht.model()
    quelle = m.sourceModel() if hasattr(m, "sourceModel") and m.sourceModel() is not None else m
    return f"{type(quelle).__name__}:{m.headerData(0, Qt.Horizontal, Qt.DisplayRole) or ''}"


def _titel(ansicht, c):
    return str(ansicht.model().headerData(c, Qt.Horizontal, Qt.DisplayRole) or "")


def kopfbreite(ansicht, c):
    """Breite, die der Spaltenkopf mindestens braucht: höchstens zweizeilig, kein Wort abgeschnitten."""
    schrift = QFont(ansicht.horizontalHeader().font())
    schrift.setBold(True)           # Spaltenköpfe sind fett (STIL), sonst wird der Kopf abgeschnitten
    fm = QFontMetrics(schrift)
    titel = str(ansicht.model().headerData(c, Qt.Horizontal, Qt.DisplayRole) or "")
    woerter = [fm.horizontalAdvance(w) for w in titel.split()] or [0]
    return max(max(woerter), fm.horizontalAdvance(titel) / 2) + 20


def passende_breite(ansicht, c, max_breite=MAX_BREITE):
    inhalt = ansicht.sizeHintForColumn(c) + 8
    return int(min(max(kopfbreite(ansicht, c), inhalt, MIN_BREITE), max_breite))


class AutoGroesse(QObject):
    """Hält Spaltenbreiten und Zeilenhöhen einer QTableView passend zum Inhalt (Regeln oben).
    Wird an die Ansicht gehängt (ansicht.auto_groesse); Änderungen am Modell lösen die Anpassung gesammelt aus."""

    def __init__(self, ansicht, max_breite=MAX_BREITE, max_zeilen=MAX_ZEILEN, max_anzahl=MAX_ANZAHL):
        super().__init__(ansicht)
        self.ansicht, self.max_breite, self.max_zeilen, self.max_anzahl = ansicht, max_breite, max_zeilen, max_anzahl
        self.von_hand = set()          # vom Benutzer gezogene Spalten
        self.eingepasst = False        # erstes Einpassen mit Daten erledigt
        self._selbst = False
        self._offen = False            # Anpassen steht aus, bis die Tabelle zu sehen ist
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.anpassen)
        ansicht.setWordWrap(True)
        ansicht.setAlternatingRowColors(True)      # Zebra-Zeilen wie in den PDF-Listen
        ansicht.setTextElideMode(Qt.ElideRight)
        kopf = ansicht.horizontalHeader()
        kopf.sectionResized.connect(self._gezogen)
        zuruecksetzen = QAction("Spaltenbreiten zurücksetzen", kopf)
        zuruecksetzen.triggered.connect(self.zuruecksetzen)
        kopf.addAction(zuruecksetzen)
        if kopf.contextMenuPolicy() == Qt.DefaultContextMenu:
            kopf.setContextMenuPolicy(Qt.ActionsContextMenu)
        self._merk_timer = QTimer(self)
        self._merk_timer.setSingleShot(True)
        self._merk_timer.setInterval(400)
        self._merk_timer.timeout.connect(self.merken)
        # Köpfe zweizeilig (Regel oben), sonst wird ein langer Kopf trotz passender Breite abgeschnitten
        kopf.setDefaultAlignment(Qt.AlignCenter | Qt.TextWordWrap)
        kopf.setMinimumHeight(max(kopf.minimumHeight(), 2 * kopf.fontMetrics().lineSpacing() + 12))
        m = ansicht.model()
        for signal in (m.modelReset, m.layoutChanged, m.rowsInserted, m.rowsRemoved, m.dataChanged, m.columnsInserted):
            signal.connect(self.spaeter)
        ansicht.auto_groesse = self
        ansicht.installEventFilter(self)
        self.spaeter()

    @staticmethod
    def _maus():
        return QGuiApplication.mouseButtons() != Qt.NoButton

    def _gezogen(self, c, alt, neu):
        # Ein- und Ausblenden (Breite 0) und die gestreckte letzte Spalte sind keine Benutzeränderung
        if self._selbst or not alt or not neu or not self._maus():
            return
        kopf = self.ansicht.horizontalHeader()
        if kopf.stretchLastSection() and c == kopf.logicalIndex(kopf.count() - 1):
            return
        self.von_hand.add(c)
        self._merk_timer.start()

    def merken(self):
        """Breiten der von Hand gezogenen Spalten unter dem Spaltentitel speichern."""
        a = self.ansicht
        if a.model() is None:
            return
        schl = tabellen_schluessel(a)
        breiten = dict(_gemerkt().get(schl) or {})
        for c in self.von_hand:
            if c < a.model().columnCount() and not a.isColumnHidden(c) and _titel(a, c):
                breiten[_titel(a, c)] = a.columnWidth(c)
        _merken(schl, breiten)

    def _gemerkte_anwenden(self):
        a, m = self.ansicht, self.ansicht.model()
        breiten = _gemerkt().get(tabellen_schluessel(a)) or {}
        if not breiten:
            return
        kopf = a.horizontalHeader()
        letzte = kopf.logicalIndex(kopf.count() - 1) if kopf.stretchLastSection() else None
        self._selbst = True
        try:
            for c in range(m.columnCount()):
                b = breiten.get(_titel(a, c))
                if isinstance(b, int) and b > 0 and c != letzte and not a.isColumnHidden(c):
                    a.setColumnWidth(c, max(b, MIN_BREITE // 2))
                    self.von_hand.add(c)
        finally:
            self._selbst = False

    def zuruecksetzen(self):
        """Gemerkte Breiten dieser Tabelle löschen und alle Spalten neu einpassen."""
        self._merk_timer.stop()
        _merken(tabellen_schluessel(self.ansicht), {})
        self.von_hand.clear()
        self.eingepasst = False
        self.anpassen()

    def spaeter(self, *_):
        self._timer.start()

    def eventFilter(self, obj, ereignis):
        if obj is self.ansicht and ereignis.type() == QEvent.Show and self._offen:
            self.anpassen()          # vor dem ersten Zeichnen: die Tabelle erscheint gleich passend
        return False

    def neu_einpassen(self):
        """Alles neu einpassen (auch schmaler); gemerkte Breiten (merken) gelten weiter."""
        self.von_hand.clear()
        self.eingepasst = False
        self.anpassen()

    def einpassen(self, spalten):
        """Nur diese Spalten neu einpassen (auch schmaler), z. B. gerade eingeblendete."""
        self._breiten(set(spalten), wachsen=False)
        self._zeilen()

    def anpassen(self):
        self._timer.stop()
        if self.ansicht.model() is None:
            return
        if not self.ansicht.isVisible():      # verdeckt: beim Zeigen nachholen (eventFilter)
            self._offen = True
            return
        self._offen = False
        if self.ansicht.model().rowCount() == 0:      # leere Tabelle: wenigstens die Spaltenköpfe ganz zeigen
            self._koepfe()
            return
        if not self.eingepasst:
            self._gemerkte_anwenden()
        self._breiten(None, wachsen=self.eingepasst)
        self.eingepasst = True
        self._zeilen()

    def _breiten(self, nur, wachsen):
        a, m = self.ansicht, self.ansicht.model()
        kopf = a.horizontalHeader()
        letzte = kopf.logicalIndex(kopf.count() - 1) if kopf.stretchLastSection() else None
        self._selbst = True
        try:
            for c in range(m.columnCount()):
                if a.isColumnHidden(c) or c in self.von_hand or c == letzte or (nur is not None and c not in nur):
                    continue
                b = passende_breite(a, c, self.max_breite)
                if wachsen:
                    b = max(b, a.columnWidth(c))
                if b != a.columnWidth(c):
                    a.setColumnWidth(c, b)
        finally:
            self._selbst = False

    def _koepfe(self):
        a = self.ansicht
        kopf = a.horizontalHeader()
        letzte = kopf.logicalIndex(kopf.count() - 1) if kopf.stretchLastSection() else None
        self._selbst = True
        try:
            for c in range(a.model().columnCount()):
                if a.isColumnHidden(c) or c in self.von_hand or c == letzte:
                    continue
                b = int(min(max(kopfbreite(a, c), MIN_BREITE), self.max_breite))
                if b > a.columnWidth(c):
                    a.setColumnWidth(c, b)
        finally:
            self._selbst = False

    def _zeilen(self):
        a, m = self.ansicht, self.ansicht.model()
        kopf = a.verticalHeader()
        standard = kopf.defaultSectionSize()
        n = m.rowCount()
        if n > self.max_anzahl:
            return
        hoechst = max(standard, self.max_zeilen * a.fontMetrics().lineSpacing() + 8)
        for r in range(n):
            if a.isRowHidden(r):
                continue
            h = max(standard, min(a.sizeHintForRow(r), hoechst))
            if h != a.rowHeight(r):
                a.setRowHeight(r, h)
